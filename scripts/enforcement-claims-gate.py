#!/usr/bin/env python3
"""enforcement-claims-gate.py — a contract with no reader is a claim, not a contract.

## The bug class this exists for

Three defects found on 2026-07-31 were the same disease, and no existing gate could see
any of them, because each was a **guarantee asserted in prose with nothing in code behind
it**:

  · `contracts/canon/guardrail_rules.yaml` said *"roleplay-service constructs YamlGuardrail
    at startup, then calls check_proposed_write for every proposed L3 event BEFORE the
    event is written"*, and `docs/standards/README.md` listed that as the enforcement site.
    `YamlGuardrail` had **zero** production call sites; roleplay-service did not even
    depend on the crate.

  · `campaign-service` swallowed an authorization error into `owned = True`, justified by
    a comment reading *"the dispatch path re-verifies"*. `verify_project_owner` had exactly
    **one** call site — the one making the claim.

  · `python-integration-tests.yml` existed precisely to stop DB-gated suites rotting, and
    its own docstring recorded that the previous rot had cost two production bugs. It
    covered six services and **missed two**, leaving 41 tests that had never run anywhere.

Every one had correct intent, correct design, and correct documentation. What was missing
was anything MECHANICAL checking that reality matched the claim.

## What this gate checks

For every contract file registered in the machine-contract table of
`docs/standards/README.md`: the file exists, and **some non-test source file reads it**.

That is deliberately narrow. It cannot verify that a reader is *correct*, or that it runs
on the right path — but "nobody reads this at all" is the terminal case, it is exactly
what happened, and it is cheaply decidable. A row that is knowingly unwired declares so
with a `NOT WIRED` marker in its enforcement cell, which keeps the honest state visible
instead of letting it read as live.

Usage:
  python scripts/enforcement-claims-gate.py

Exit 0 = every registered contract has a reader (or is declared unwired). Exit 1 = a
contract is claimed to be enforced and nothing reads it.
"""
from __future__ import annotations

import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(REPO_ROOT, "docs", "standards", "README.md")

SEARCH_DIRS = ("services", "sdks", "crates", "frontend", "scripts", "contracts", "tests")
SCAN_EXTS = (".py", ".ts", ".tsx", ".js", ".mjs", ".go", ".rs", ".yml", ".yaml", ".json")
EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv", "target",
    "dist", "build", ".next", ".git", "vendor", "coverage",
}

#: A row whose enforcement cell carries this is declaring the honest state rather than
#: claiming one. Keeping it visible in the index is the point — it must not be deletable
#: by quietly dropping the row.
UNWIRED = re.compile(r"NOT\s+WIRED", re.IGNORECASE)

#: Table rows naming a contract path in the first cell.
ROW = re.compile(r"^\|\s*`?([a-z0-9_./-]+\.(?:ya?ml|json))`?\s*\|(.*)\|(.*)\|\s*$", re.IGNORECASE)


def is_test_path(rel: str) -> bool:
    return (
        "/tests/" in rel or "/test/" in rel or "/__tests__/" in rel
        or os.path.basename(rel).startswith("test_")
        or os.path.basename(rel).endswith(("_test.go", "_test.rs", ".test.ts", ".test.tsx"))
    )


def iter_sources():
    for d in SEARCH_DIRS:
        root = os.path.join(REPO_ROOT, d)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [x for x in dirnames if x not in EXCLUDE_DIRS]
            for fn in filenames:
                if fn.endswith(SCAN_EXTS):
                    full = os.path.join(dirpath, fn)
                    yield full, os.path.relpath(full, REPO_ROOT).replace(os.sep, "/")


def readers_of(contract_rel: str, sources: list[tuple[str, str]]) -> list[str]:
    """Non-test files that mention this contract by path or by basename.

    Basename is enough: a loader usually joins a directory constant with the file name, so
    requiring the full path would produce false 'unread' verdicts — and a gate that cries
    wolf gets switched off, which is the failure mode this whole family is about.
    """
    base = os.path.basename(contract_rel)
    hits: list[str] = []
    for full, rel in sources:
        if rel == contract_rel or is_test_path(rel):
            continue
        # THIS FILE names contracts in its own docstring as examples, and `scripts/` is not
        # a library, so it counted as a live reader of every contract it discussed — the
        # gate satisfied its own check by talking about the problem. Caught by injecting
        # the original fiction and watching it stay green.
        if rel == "scripts/enforcement-claims-gate.py":
            continue
        try:
            with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                body = fh.read()
        except OSError:
            continue
        if base in body or contract_rel in body:
            hits.append(rel)
    return hits


def _library_of(rel: str) -> str | None:
    """The self-contained library a reader lives in, if any — `crates/<n>` or `sdks/<a>/<b>`.

    A reader inside a SERVICE is live by construction: the service is deployed and runs.
    A reader inside a LIBRARY is not: a crate or SDK module only executes when something
    outside it calls in. That distinction is the whole second hop.
    """
    parts = rel.split("/")
    if len(parts) >= 2 and parts[0] == "crates":
        return "/".join(parts[:2])
    if len(parts) >= 3 and parts[0] == "sdks":
        return "/".join(parts[:3])
    return None


def is_reachable(reader_rel: str, sources: list[tuple[str, str]]) -> bool:
    """Does anything OUTSIDE the reader's own library depend on that library?

    The first version of this gate stopped at `readers_of` and went GREEN on the exact
    defect it was written for: `crates/contracts-prompt` reads
    `contracts/canon/guardrail_rules.yaml`, so "it has a reader" was true — and
    `YamlGuardrail` still had zero production call sites, because nothing depends on the
    crate. A contract read by code nobody calls is enforced by nobody.
    """
    lib = _library_of(reader_rel)
    if lib is None:
        return True  # inside a service — deployed, therefore live
    name = lib.split("/")[-1]
    snake = name.replace("-", "_")

    # A bare mention is NOT a dependency, and both false positives here were bare
    # mentions: the workspace root Cargo.toml lists the crate as a MEMBER (membership is
    # not linkage), and a sibling crate names its path in a doc comment. Require real
    # import/dependency syntax.
    use_re = re.compile(
        rf"(?:^\s*use\s+{re.escape(snake)}\b"           # rust  use contracts_prompt::…
        rf"|^\s*(?:from|import)\s+{re.escape(snake)}\b"  # python
        rf"|['\"]{re.escape(name)}['\"]\s*:)",           # ts/json dependency entry
        re.MULTILINE,
    )
    dep_re = re.compile(rf"^\s*{re.escape(name)}\s*=", re.MULTILINE)  # Cargo [dependencies]

    for full, rel in sources:
        if rel.startswith(lib + "/") or is_test_path(rel):
            continue
        # The workspace root manifest lists every crate as a member; that says the crate is
        # BUILT, not that anything links it. Exactly how a dead crate looks alive.
        if rel in ("Cargo.toml", "package.json"):
            continue
        try:
            with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                body = fh.read()
        except OSError:
            continue
        if use_re.search(body) or (rel.endswith("Cargo.toml") and dep_re.search(body)):
            return True
    return False


def main() -> int:
    if not os.path.isfile(INDEX):
        print(f"enforcement-claims-gate: standards index not found at {INDEX}")
        return 1

    with open(INDEX, "r", encoding="utf-8") as fh:
        lines = fh.readlines()

    rows: list[tuple[str, str]] = []
    for line in lines:
        m = ROW.match(line.strip())
        if not m:
            continue
        path, _purpose, enforcement = m.group(1), m.group(2), m.group(3)
        rows.append((path, enforcement))

    if not rows:
        print("enforcement-claims-gate: no contract rows parsed — the index format changed;")
        print("  fix the ROW pattern rather than leaving the gate silently vacuous.")
        return 1

    sources = list(iter_sources())
    missing: list[str] = []
    unread: list[tuple[str, str]] = []
    declared_unwired: list[str] = []

    for path, enforcement in rows:
        full = os.path.join(REPO_ROOT, path.replace("/", os.sep))
        if not os.path.isfile(full):
            missing.append(path)
            continue
        if UNWIRED.search(enforcement):
            declared_unwired.append(path)
            continue
        readers = readers_of(path, sources)
        live = [r for r in readers if is_reachable(r, sources)]
        if not live:
            why = ("nothing reads it" if not readers else
                   f"read only by {', '.join(readers)}, and nothing outside that library "
                   "depends on it — the reader itself is never called")
            unread.append((path, f"{enforcement.strip()}   [{why}]"))

    print(f"enforcement-claims-gate: {len(rows)} registered contract(s)")
    if declared_unwired:
        print(f"  {len(declared_unwired)} declared NOT WIRED (honest, not a failure):")
        for p in declared_unwired:
            print(f"    · {p}")

    if not missing and not unread:
        print("OK — every claimed-enforced contract has a non-test reader")
        return 0

    print()
    if missing:
        print("[registered contract file does not exist]")
        for p in missing:
            print(f"  {p}")
        print()
    if unread:
        print("[claimed enforced, but NOTHING reads it]")
        print("  → this is the D-GUARDRAIL-CLAIMED-NOT-WIRED shape: a contract, an")
        print("    implementation and an index row that all agree, and no call site.")
        print("    Wire it, or mark the enforcement cell NOT WIRED and say what blocks it.\n")
        for p, enf in unread:
            print(f"  {p}")
            print(f"      index claims: {enf}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
