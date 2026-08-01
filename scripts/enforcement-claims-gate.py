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
#:
#: The index writes that cell TWO ways — a backticked path (`contracts/cache/keys.yaml`) and
#: a markdown link ([contracts/language-rule.yaml](../../contracts/language-rule.yaml)) — and
#: this pattern only ever matched the first. It therefore skipped four rows, including BOTH
#: LOCKED contracts (`language-rule.yaml`, `frontend-tools.contract.json`), while reporting
#: "8 registered contract(s)" as though that were the set. A gate that silently narrows its
#: own input is the failure it exists to catch, so the link form is matched explicitly rather
#: than by loosening the path class (which would start swallowing prose).
ROW = re.compile(
    r"^\|\s*(?:`(?P<tick>[a-z0-9_./*-]+\.(?:ya?ml|json))`"
    r"|\[(?P<link>[a-z0-9_./-]+\.(?:ya?ml|json))\]\([^)]*\)"
    r"|(?P<bare>[a-z0-9_./*-]+\.(?:ya?ml|json)))\s*\|(.*)\|(.*)\|\s*$",
    re.IGNORECASE,
)


def row_path(m: "re.Match[str]") -> str:
    return m.group("tick") or m.group("link") or m.group("bare")


#: Concrete gate/test files an enforcement cell may name. Only repo-relative paths with a
#: real extension count — "planned perf-nightly p95 assertion" is prose, not an artifact,
#: and must not be mistaken for one.
_ARTIFACT = re.compile(
    r"(?<![\w/])((?:scripts|tests|sdks|services|frontend|contracts)/[\w./-]+"
    r"\.(?:py|sh|go|rs|ts|tsx|ya?ml|json))"
)


def _mentions(rel: str, contract_path: str) -> bool:
    """Does the file at `rel` reference `contract_path` (by full path or basename)?"""
    try:
        with open(os.path.join(REPO_ROOT, rel.replace("/", os.sep)), encoding="utf-8",
                  errors="ignore") as fh:
            body = fh.read()
    except OSError:
        return False
    return contract_path in body or os.path.basename(contract_path) in body


def enforcement_artifacts(cell: str) -> list[str]:
    """Gate scripts / drift tests the enforcement cell names, de-duplicated in order."""
    out: list[str] = []
    for m in _ARTIFACT.finditer(cell):
        p = m.group(1)
        if p not in out:
            out.append(p)
    return out


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


# ── S12 · every DECLARED enforcement site must resolve, not only the 12 contract rows ────

#: Repo-relative paths the index names. Deliberately restricted to the extensions an
#: enforcement claim actually uses — widening it starts swallowing prose ("see services/foo"),
#: and a gate that manufactures findings is abandoned faster than one that misses some.
_EXT = r"(?:py|sh|ya?ml|json|md|go|rs|ts|tsx)"
_TOP = r"(?:scripts|contracts|docs|services|sdks|crates|frontend|\.github)"

#: A backticked repo-relative path: `scripts/ai-provider-gate.py`.
_NAMED_PATH = re.compile(rf"`(?P<p>{_TOP}/[A-Za-z0-9_./*-]+\.{_EXT})`")

#: A markdown LINK TARGET. This index sits at `docs/standards/`, so most of its links are
#: written `../../contracts/x.yaml` — and a pattern anchored on the repo-relative form matches
#: NONE of them. The first version of this check did exactly that and reported "43 paths, 0
#: missing" while never looking at a single doc link; the teeth test caught it by injecting a
#: broken link and watching the checker stay silent. Targets are resolved against the index's
#: own directory, which is what a reader clicking the link does.
_LINK_TARGET = re.compile(rf"\]\((?P<p>[A-Za-z0-9_./*-]+\.{_EXT})(?:#[^)]*)?\)")

#: A path with a glob cannot be stat'd; `contracts/api/glossary-service/*.yaml` is a real and
#: correct way to name a set. Resolved by directory existence instead of skipped, because
#: "the directory is gone" is the same failure one level up.
_GLOB = "*"


def declared_paths(text: str) -> set[str]:
    """Every path the index names, normalised to repo-relative.

    Two forms, because the index writes both and a checker that sees only one silently halves
    its own input — the exact failure the contract-row regex shipped with.
    """
    out = {m.group("p") for m in _NAMED_PATH.finditer(text)}
    index_dir = os.path.dirname(os.path.relpath(INDEX, REPO_ROOT)).replace(os.sep, "/")
    for m in _LINK_TARGET.finditer(text):
        raw = m.group("p")
        rel = raw if not raw.startswith(("./", "../")) else os.path.normpath(
            os.path.join(index_dir, raw)).replace(os.sep, "/")
        # A target that climbs OUT of the repo is not ours to check.
        if not rel.startswith(".."):
            out.add(rel)
    return out


def unresolved_paths(text: str) -> list[str]:
    """Paths the standards index names that do not exist on disk.

    THE GENERALISATION S12 ASKS FOR. The contract check above covers section B — 12 rows of a
    125-row index. Sections A, C, D, E and F name gates, lints, specs and source files in their
    enforcement cells, and NOTHING checked that any of them still exist. That is the B3 shape
    exactly: a standard whose enforcement is a script that was renamed, moved, or never
    written, asserted in a document nobody diffs against the tree.

    A missing path is reported, never a missing SYMBOL — this cannot tell whether the named
    script does what the cell claims. "It is not there at all" is the terminal case, it is what
    happened, and it is cheaply decidable.
    """
    out: list[str] = []
    for rel in sorted(declared_paths(text)):
        target = os.path.join(REPO_ROOT, *rel.split("/"))
        if _GLOB in rel:
            # `a/b/*.yaml` → the directory must exist and hold at least one match.
            import glob as _g
            if not _g.glob(target):
                out.append(rel)
            continue
        if not os.path.exists(target):
            out.append(rel)
    return out


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
        path, _purpose, enforcement = row_path(m), m.group(4), m.group(5)
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
        # A row may register a FAMILY (`contracts/admin/registry/*.yaml`) rather than one
        # file. Resolve the glob and require ≥1 match: a registered family that matches
        # nothing is exactly as empty as a missing file, and reporting it as "does not exist"
        # would be true but unactionable.
        if "*" in path:
            import glob as _glob
            hits = _glob.glob(os.path.join(REPO_ROOT, path.replace("/", os.sep)))
            if not hits:
                missing.append(f"{path} (glob matched no files)")
                continue
            if UNWIRED.search(enforcement):
                declared_unwired.append(path)
                continue
            # A family is read if ANY member is.
            rel_hits = [os.path.relpath(h, REPO_ROOT).replace(os.sep, "/") for h in hits]
            if not any(
                any(is_reachable(r, sources) for r in readers_of(h, sources))
                for h in rel_hits
            ):
                unread.append((path, f"none of its {len(rel_hits)} file(s) has a live reader"))
            continue
        full = os.path.join(REPO_ROOT, path.replace("/", os.sep))
        if not os.path.isfile(full):
            missing.append(path)
            continue
        if UNWIRED.search(enforcement):
            declared_unwired.append(path)
            continue
        # A contract can be enforced by a GATE or a DRIFT TEST rather than by a runtime
        # reader, and for some that is the stronger form — `language-rule.yaml` is enforced
        # by `scripts/language-rule-lint.sh`, and `llm-budget.contract.json` by three
        # per-language drift tests; neither is loaded at runtime by design.
        #
        # Both were passing this gate for the WRONG reason: the reader search is a text
        # match, so `language-rule.yaml` "passed" on a perf harness that happens to name it,
        # and `llm-budget.contract.json` on a DOC COMMENT in llmbudget.go. That is the same
        # comment-is-not-linkage false pass this gate was written to kill, reappearing in the
        # gate itself. So an enforcement cell that names a gate/test is verified AS one: the
        # named file must exist.
        named = enforcement_artifacts(enforcement)
        if named:
            absent = [n for n in named
                      if not os.path.isfile(os.path.join(REPO_ROOT, n.replace("/", os.sep)))]
            if absent:
                unread.append((path, "its enforcement cell names "
                                     f"{', '.join(absent)}, which does not exist"))
                continue
            # Existing is not enforcing. The first version of this branch stopped at "the
            # named file is on disk", which would pass a gate that never opens the contract —
            # trading a real check (a live reader) for a weaker one, in the gate whose whole
            # subject is claims with nothing behind them. At least ONE named artifact must
            # actually reference the contract path.
            reads = [n for n in named if _mentions(n, path)]
            if not reads:
                unread.append((path, "its enforcement cell names "
                                     f"{', '.join(named)}, and none of them reference {path}"))
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

    # S12 — the generalisation: every path the index NAMES, in any section, must resolve.
    with open(INDEX, encoding="utf-8") as fh:
        phantom = unresolved_paths(fh.read())
    print(f"  {len(declared_paths(open(INDEX, encoding='utf-8').read()))} path(s) named across "
          f"the whole index; {len(phantom)} do not exist")

    if not missing and not unread and not phantom:
        print("OK — every claimed-enforced contract is backed by a live non-test reader, or by "
              "a gate/drift-test its enforcement cell names and that exists; and every path the "
              "index names resolves on disk")
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
    if phantom:
        print("[the index NAMES these and they do not exist]")
        print("  → a standard whose enforcement is a script that was renamed, moved or never")
        print("    written is worse than an unwritten standard: it reads as covered.")
        print()
        for p in phantom:
            print(f"  {p}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
