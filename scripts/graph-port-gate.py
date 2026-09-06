#!/usr/bin/env python3
"""graph-port-gate.py — Cypher belongs in an adapter, nowhere else.

Plan T16 of the knowledge-architecture refactor. Phase 2 puts every storage access behind
a port so the graph engine can be swapped (Phase 7) and so ~561 tests can stop needing a
live Neo4j (T20). None of that survives contact with a codebase where any module can open
a session and write a query — so this gate makes "Cypher lives in an adapter" a property
of the tree rather than a convention people remember.

WHAT COUNTS AS AN ADAPTER
-------------------------
`app/adapters/` and — deliberately — `app/db/graph_repos/`. That package predates the
naming: it IS the Neo4j implementation, complete with the `run_read`/`run_write` tenancy
guards that make its queries safe, and the adapters under `app/adapters/` DELEGATE to it
rather than copying its Cypher (a byte-for-byte copy would be two places to fix a tenant
filter). Allowing both is therefore not a loophole, it is naming the same thing twice —
recorded here and in `app/adapters/__init__.py` because a gate that quietly allowlists a
directory nobody remembers deciding on is how an invariant becomes a formality.

WHY THIS DOES NOT GREP
----------------------
Python files are parsed and only STRING CONSTANTS are examined, with docstrings excluded.
Prose that explains Cypher is not Cypher, and this exact false positive has already bitten
this refactor twice: a migration guard matched its own comment explaining what not to
write, and a module docstring demonstrating literal-injection matched as an injection. A
grep-based version of this gate would have to be argued with; this one cannot be.

THE BASELINE, AND WHY IT SHRINKS
--------------------------------
16 files outside the adapter dirs still carry Cypher at the time this ships (T11-T13
cleared five; T17 sweeps the rest). Shipping the gate as "clean or fail" would mean not
shipping it, and shipping it as a warning would mean nobody notices it. So it ships with an
EXPLICIT, PER-FILE baseline: every one of those files is listed, and anything NOT listed
fails immediately. T17's job is to delete entries from that list.

Two properties make the baseline a ratchet rather than a hiding place:
  - it is per FILE, never per directory — a new file in a listed directory fails;
  - a baseline entry with no violations left is itself an ERROR, so a cleaned file cannot
    stay on the list and silently re-grant permission later.

Usage:
  python scripts/graph-port-gate.py            # full scan (CI / manual)
  python scripts/graph-port-gate.py --staged   # only git-staged files (pre-commit)
  python scripts/graph-port-gate.py --list     # print current violations by file

Exit 0 = clean (or baseline-only). Exit 1 = violation.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_ROOT = os.path.join("services", "knowledge-service", "app")

# Cypher clause openers. `CREATE (` is included even though it also appears in prose —
# the docstring exclusion is what makes that safe, and dropping it would miss node
# creation entirely.
CYPHER_TOKENS = (
    "MATCH (",
    "OPTIONAL MATCH (",
    "MERGE (",
    "CREATE (",
    "DETACH DELETE",
    "CREATE VECTOR INDEX",
    # NOT bare "CREATE INDEX" / "CREATE CONSTRAINT": those are SQL too, and this service
    # runs a Postgres migration DDL blob (app/db/migrate.py) full of them. Including them
    # made the gate report the SQL runner as a Cypher violation on its first run — a gate
    # whose first finding is a false positive is one people learn to skip.
    "SHOW VECTOR INDEXES",
    "CALL db.index.vector",
)

# Adapter territory — see the module docstring for why this is two paths, not one.
ADAPTER_DIRS = (
    os.path.join(SCAN_ROOT, "adapters"),
    os.path.join(SCAN_ROOT, "db", "graph_repos"),
)

# Documented non-adapter exceptions. Each needs a REASON, not just a path.
EXEMPT_FILES = {
    # ⚰️ `db/neo4j_schema.py` WAS here for "startup schema DDL, pre-dates any adapter". The
    # stale-exemption check added with the T54e entry below reported it on its first run and
    # the report was right: that module carries ZERO Cypher — it is a RUNNER that loads the
    # `neo4j_schema.cypher` companion and splits it on `;`. The DDL moved to the .cypher file,
    # which this gate does not scan at all, and the exemption had been standing permission for
    # a file that needed none. Removed 2026-08-24; if a query is ever written there it now
    # fails like any other.
    # T54e. The ONE file whose purpose is to be engine-aware on BOTH sides: it reads a Neo4j
    # graph and writes an AGE one, keyed per label, so its Cypher cannot move into
    # `graph_repos` without the neutral layer growing a "migrate from the other engine"
    # operation that only this script would ever call. Exempt rather than BASELINEd because
    # baseline means "debt T17 will clear" and this is not debt — it is the seam itself.
    os.path.join(SCAN_ROOT, "db", "migrations", "neo4j_to_age.py"):
        "engine-to-engine migration; owns Cypher for BOTH engines by definition (T54e)",
}

# Files that still carry Cypher when this gate shipped (2026-08-10). T17 empties this.
# PER-FILE on purpose: a new file in any of these directories fails immediately.
BASELINE = {
    os.path.join(SCAN_ROOT, "db", "migrations", "backfill_entity_alias_map.py"),
    os.path.join(SCAN_ROOT, "db", "migrations", "backfill_event_date.py"),
    os.path.join(SCAN_ROOT, "db", "migrations", "backfill_orders.py"),
    os.path.join(SCAN_ROOT, "db", "migrations", "backfill_participant_anchors.py"),
    os.path.join(SCAN_ROOT, "db", "migrations", "backfill_status.py"),
    os.path.join(SCAN_ROOT, "db", "migrations", "recanon_honorifics.py"),
}


def _norm(path: str) -> str:
    """Repo-relative, OS-native separators, so the constants above compare on any host."""
    return os.path.normpath(os.path.relpath(os.path.abspath(path), REPO_ROOT))


def _is_adapter(rel: str) -> bool:
    return any(rel.startswith(d + os.sep) for d in ADAPTER_DIRS)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """ids of the string Constants that are docstrings. Excluding these is what lets the
    gate read prose about Cypher without reporting it."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                out.add(id(body[0].value))
    return out


def violations_in(path: str) -> list[tuple[int, str]]:
    """(line, token) for each Cypher clause in a non-docstring string constant."""
    try:
        source = open(path, encoding="utf-8").read()
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        # Unreadable or unparseable: not this gate's business to fail the commit for it —
        # the formatter/linter owns that, and failing here would be a confusing message.
        return []
    docstrings = _docstring_nodes(tree)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in docstrings:
            continue
        for token in CYPHER_TOKENS:
            if token in node.value:
                found.append((getattr(node, "lineno", 0), token))
                break
    return found


def _candidate_files(staged_only: bool) -> list[str]:
    if staged_only:
        try:
            out = subprocess.run(
                ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                cwd=REPO_ROOT, capture_output=True, text=True, check=True,
            ).stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []
        files = [os.path.join(REPO_ROOT, p.strip()) for p in out.splitlines() if p.strip()]
        return [f for f in files if f.endswith(".py") and os.path.exists(f)
                and _norm(f).startswith(SCAN_ROOT + os.sep)]

    root = os.path.join(REPO_ROOT, SCAN_ROOT)
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__", ".venv", "node_modules"}]
        files.extend(os.path.join(dirpath, f) for f in filenames if f.endswith(".py"))
    return files


def stale_excusals(offenders, exempt_still_using, baseline, exempt) -> list[str]:
    """Excusals with nothing left to excuse — from BOTH lists.

    🔴 **`EXEMPT_FILES` was checked for nothing until 2026-08-24.** The baseline half already
    existed with the reason spelled out in the gate's own failure text — *"a stale entry
    re-grants permission silently"* — and the exemption half, which grants a STRONGER
    permission (permanent, not "T17 will clear it"), had no such check at all. It found a real
    one on its first run: `db/neo4j_schema.py` was exempt as *"startup schema DDL"* and carries
    zero Cypher, because the DDL had long since moved to the `.cypher` companion the gate does
    not scan.

    Split on purpose: never `staged_only`. A staged run sees a fraction of the tree, so every
    untouched excusal would look stale and the gate would fail every partial commit.
    """
    out = sorted(b for b in baseline if b not in offenders)
    out += sorted(f"{rel} (EXEMPT)" for rel in exempt if rel not in exempt_still_using)
    return out


def _selftest() -> int:
    """Cases the repo's own state cannot supply — a hand-bite is invisible to CI."""
    a, b, c = "a.py", "b.py", "c.py"
    cases = [
        ("a baseline file that still carries Cypher is NOT stale",
         stale_excusals({a}, set(), {a}, {}), []),
        ("a baseline file with nothing left IS stale",
         stale_excusals(set(), set(), {a}, {}), [a]),
        ("an EXEMPT file that still carries Cypher is NOT stale",
         stale_excusals(set(), {b}, set(), {b: "reason"}), []),
        ("an EXEMPT file with nothing left IS stale — the case that found neo4j_schema.py",
         stale_excusals(set(), set(), set(), {b: "reason"}), [f"{b} (EXEMPT)"]),
        ("both lists report independently",
         stale_excusals(set(), set(), {a}, {b: "r"}), [a, f"{b} (EXEMPT)"]),
        ("an offender that is neither baselined nor exempt does not appear here",
         stale_excusals({c}, set(), set(), {}), []),
        ("an EXEMPT file is never reported merely because it is not an OFFENDER",
         stale_excusals(set(), {b}, set(), {b: "r"}), []),
    ]
    failures = 0
    print("graph-port-gate - selftest (offline)")
    for label, got, want in cases:
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f"  got={got} want={want}"))
    print(chr(10) + "  all checks passed" if not failures else chr(10) + f"  {failures} FAILED")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return _selftest()
    staged_only = "--staged" in argv
    listing = "--list" in argv

    offenders: dict[str, list[tuple[int, str]]] = {}
    exempt_still_using: set[str] = set()
    scanned = 0
    for path in _candidate_files(staged_only):
        rel = _norm(path)
        if _is_adapter(rel):
            continue
        found = violations_in(path)
        if rel in EXEMPT_FILES:
            # Scanned anyway, so a stale exemption can be reported below. Not an offender.
            if found:
                exempt_still_using.add(rel)
            continue
        scanned += 1
        if found:
            offenders[rel] = found

    if listing:
        for rel, found in sorted(offenders.items()):
            state = "BASELINE" if rel in BASELINE else "NEW"
            print(f"{state:9} {rel}  ({len(found)} clause(s), first at line {found[0][0]})")
        print(f"\n{len(offenders)} file(s) with Cypher outside adapter territory; "
              f"{len(BASELINE)} baselined.")
        return 0

    new = {rel: v for rel, v in offenders.items() if rel not in BASELINE}

    # A baseline entry with nothing left to excuse must GO. Otherwise a cleaned file keeps
    # standing permission and the next query to land there passes silently — the ratchet
    # slipping backwards without anyone touching the list.
    stale: list[str] = []
    if not staged_only:
        stale = stale_excusals(offenders.keys(), exempt_still_using, BASELINE, EXEMPT_FILES)

    if not new and not stale:
        print(f"[graph-port-gate] PASS — {scanned} file(s) scanned outside adapter dirs; "
              f"{len(offenders)} baselined file(s) still carry Cypher (T17 shrinks that list)")
        return 0

    for rel, found in sorted(new.items()):
        for line, token in found[:5]:
            print(f"{rel}:{line}: Cypher outside an adapter — {token.strip()!r}")
    for rel in stale:
        which = "EXEMPT_FILES" if rel.endswith("(EXEMPT)") else "BASELINE"
        print(f"{rel}: excused for Cypher but has none left — DELETE it from {which} in "
              f"scripts/graph-port-gate.py (a stale entry re-grants permission silently)")

    print(
        f"\n[graph-port-gate] FAIL — {len(new)} file(s) with new Cypher outside "
        f"{' / '.join(ADAPTER_DIRS)}"
        + (f", {len(stale)} stale excusal(s)" if stale else "") + ".\n"
        "Cypher belongs in an adapter so the graph engine can be swapped and the fakes can\n"
        "stand in for it. Move the query into app/db/graph_repos/ (the Neo4j adapter) and\n"
        "call it from here. If this file genuinely owns DDL that predates any adapter, add\n"
        "it to EXEMPT_FILES **with a reason**."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
