#!/usr/bin/env python3
"""port-adoption-gate — sealed B1's *substitutability* half, which nothing else guards.

WHY THIS EXISTS, AND WHY `graph-port-gate` IS NOT IT
----------------------------------------------------
Sealed **B1**: *"Two boundaries, both required — KAL (cross-service door) + Ports
(intra-service substitutability)."*

`scripts/graph-port-gate.py` enforces that **Cypher STRING CONSTANTS** do not appear outside
the adapter directories. That is a real invariant and it passes. It is **not** B1's
substitutability claim, and conflating them is how this refactor nearly walked into a swap
it could not perform:

    a module can call `neo4j_repos.merge_entity(...)`, contain no Cypher of its own,
    satisfy graph-port-gate completely — and still break the moment the engine changes.

Cypher being centralised says the *queries* live in one place. Substitutability says the
*call sites* go through the port. T42 has now built a second adapter (AGE); this gate is
what makes the second adapter reachable rather than merely present.

MEASURED 2026-08-12
-------------------
Modules under `app/`, excluding `app/db/neo4j_repos/` (the implementation) and
`app/adapters/` (legitimate adapter territory), that IMPORT the Neo4j repository layer —
against modules that import a port. The ratio is the honest statement of where B1 stands.

⚠️ **Counted by AST, not by grep, and the difference is not pedantry.** A `grep -l` for the
same token reported **84**, then **75**; the AST count is lower because the rest are
comments, docstrings and prose *about* the migration. `/aif-improve +check` caught the first
of those numbers, and this repo has already been wrong by 36x (77 -> 2819 stale ids) on a
number of exactly that shape. `derived-entity-id-gate` strips comments for the same reason
and its baseline fell from ELEVEN to FIVE when it started doing so.

WHAT "SHRINK-ONLY" MEANS HERE
-----------------------------
The baseline is a COUNT, not a file list — deliberately, and unlike this repo's other
shrink-only gates. T17 is migrating these modules in batches, so a pinned file list would
need editing on every batch and would mostly measure churn. What must not happen is a NEW
module binding the concrete layer, and a count catches that while staying quiet during a
migration that is going the right way.

    python scripts/port-adoption-gate.py            # gate
    python scripts/port-adoption-gate.py --list     # which modules, and which import a port
    python scripts/port-adoption-gate.py --selftest # prove it can go red

Exit 0 = adoption unchanged or better · 1 = it regressed, or the baseline is stale.
"""
from __future__ import annotations

import argparse
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_ROOT = os.path.join(ROOT, "services", "knowledge-service", "app")

# `neo4j_repos` IS the Neo4j implementation and `adapters/` is where an implementation is
# allowed to be named — the adapters exist precisely to import it. Excluding them is not a
# loophole; including them would make the number measure the architecture working.
EXEMPT_DIRS = (
    os.path.join("db", "neo4j_repos"),
    "adapters",
)

# The ceiling can only fall. Raising it is a deliberate act with a reason, not a fix for a
# red build — that is the whole contract of a shrink-only gate.
MAX_CONCRETE_IMPORTERS = 70

# ── THE NUMBER THAT MATTERS ─────────────────────────────────────────────────────────────
# A FLOOR, not a ceiling: `GraphStore` adopters may only increase.
#
# It was **ZERO** when this gate was written (2026-08-12): three conforming adapters —
# fake, Neo4j, AGE (T42) — and not one call site. The four modules importing a port were
# all `VectorStore` consumers from T25a.
#
# That is what blocks T43. Its shadow comparison compares two adapters **on real traffic**,
# and with no callers every operation sits at zero observations, so the plan's coverage
# floor (*"no cutover while any port operation has zero shadow observations"*) cannot be
# satisfied by waiting — only by adoption. T17's migration is therefore the precondition
# for choosing an engine by measurement at all, which is what X3 implied by making the
# engine layer 1. See `D-T42D-GRAPHSTORE-HAS-NO-CALLERS`.
#
# **4** as of T17 batch 3: `wiki/context.py` (KG facts) · `events/handlers.py`
# (lifecycle archive) · `routers/public/entities.py` (user restore) ·
# `context/selectors/facts.py` (5 sites) · `tools/executor.py` (2) ·
# `routers/internal_admin.py` (3).  **`find_relations_for_entity` now has ZERO direct
# callers outside the adapters** — that half of the migration is complete.
MIN_GRAPHSTORE_ADOPTERS = 10

_CONCRETE = "neo4j_repos"
_PORTS = "ports"


def _imports(tree: ast.AST) -> set[str]:
    """Module paths this file actually IMPORTS.

    Only `Import` / `ImportFrom` nodes. A docstring that discusses `neo4j_repos`, or a
    comment explaining why a call was migrated off it, is not an import — and counting those
    is how the first estimate of this number came out ~18% high.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def scan() -> tuple[list[str], list[str], list[str]]:
    concrete: list[str] = []
    ported: list[str] = []
    graphstore: list[str] = []
    for base, subdirs, files in os.walk(SCAN_ROOT):
        subdirs[:] = [s for s in subdirs if s != "__pycache__"]
        rel_dir = os.path.relpath(base, SCAN_ROOT)
        if any(rel_dir == d or rel_dir.startswith(d + os.sep) for d in EXEMPT_DIRS):
            continue
        for f in files:
            if not f.endswith(".py") or f.startswith("test_"):
                continue
            path = os.path.join(base, f)
            rel = os.path.relpath(path, SCAN_ROOT)
            try:
                tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
            except (OSError, SyntaxError):
                continue
            mods = _imports(tree)
            if any(_CONCRETE in m for m in mods):
                concrete.append(rel)
            if any(m == "app.ports" or ".ports." in m or m.endswith(".ports") for m in mods):
                ported.append(rel)
            # Adoption is "reaches the graph through the port BOUNDARY", which includes the
            # sanctioned composition root — `graph_store_provider` is where the adapter is
            # chosen, and a call site importing it is exactly the shape T17 is migrating to.
            #
            # ⚠️ Counting only direct `ports.graph_store` imports (this gate's first cut)
            # reported ZERO for a call site that had genuinely migrated, and would have
            # pushed callers to import the port directly and construct their own adapter —
            # bypassing the composition root, which is worse than what it measures.
            if any("ports.graph_store" in m or "graph_store_provider" in m for m in mods):
                graphstore.append(rel)
    return sorted(concrete), sorted(ported), sorted(graphstore)


def selftest() -> int:
    """Prove the import detector can tell an import from prose, on synthetic source.

    Both directions matter. Missing a real import would let the count drift down for free;
    counting a docstring would inflate the baseline and hide real remaining work inside
    noise — the mistake `derived-entity-id-gate` records, and the one this gate's own
    measurement made twice before AST parsing.
    """
    ok = True

    real = ast.parse("from app.db.neo4j_repos.entities import merge_entity\n")
    if not any(_CONCRETE in m for m in _imports(real)):
        print("  FAIL — a real `from … neo4j_repos …` import was not detected")
        ok = False

    prose = ast.parse('"""This used to call neo4j_repos.merge_entity directly."""\n')
    if any(_CONCRETE in m for m in _imports(prose)):
        print("  FAIL — a docstring mentioning neo4j_repos was counted as an import")
        ok = False

    comment = ast.parse("# migrated off neo4j_repos in T17\nx = 1\n")
    if any(_CONCRETE in m for m in _imports(comment)):
        print("  FAIL — a comment mentioning neo4j_repos was counted as an import")
        ok = False

    port = ast.parse("from app.ports.graph_store import GraphStore\n")
    if not any(m.endswith(".ports") or ".ports." in m for m in _imports(port)):
        print("  FAIL — a port import was not detected")
        ok = False

    print(f"[port-adoption-gate] SELFTEST {'PASS' if ok else 'FAIL'} — distinguishes a real "
          f"import from a docstring and a comment, in both directions (non-vacuous)")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="show the modules")
    ap.add_argument("--selftest", action="store_true", help="prove this gate can go red")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not os.path.isdir(SCAN_ROOT):
        print(f"[port-adoption-gate] SKIP — {SCAN_ROOT} not present")
        return 0

    concrete, ported, graphstore = scan()

    if args.list:
        print(f"[port-adoption-gate] {len(concrete)} import {_CONCRETE}, "
              f"{len(ported)} import a port, {len(graphstore)} import GraphStore\n")
        for p in concrete:
            print(f"  concrete    {p}")
        for p in ported:
            print(f"  port        {p}")
        for p in graphstore:
            print(f"  graphstore  {p}")
        return 0

    print(f"[port-adoption-gate] {len(concrete)} module(s) bind `{_CONCRETE}` directly "
          f"(ceiling {MAX_CONCRETE_IMPORTERS}); {len(ported)} import a port; "
          f"**{len(graphstore)} import GraphStore** (floor {MIN_GRAPHSTORE_ADOPTERS})")

    if len(graphstore) < MIN_GRAPHSTORE_ADOPTERS:
        print(f"\n[port-adoption-gate] FAIL — GraphStore adopters FELL to {len(graphstore)}, "
              f"floor is {MIN_GRAPHSTORE_ADOPTERS}.\n")
        print("  A call site was moved back off the port. The port has three conforming")
        print("  adapters; un-adopting one is the only way to make them unreachable again.")
        return 1

    if len(graphstore) > MIN_GRAPHSTORE_ADOPTERS:
        print(f"\n[port-adoption-gate] FAIL — GraphStore adopters ROSE to {len(graphstore)} "
              f"but the floor still says {MIN_GRAPHSTORE_ADOPTERS}.\n")
        print("  Raise it — adoption is the progress this floor exists to record. (The older")
        print("  message here said T43 was blocked at zero observations; that was true when")
        print("  this gate was written and is not now — T43 compares 9/9 operations.)")
        return 1

    if MIN_GRAPHSTORE_ADOPTERS == 0:
        print("  ⚠️  GraphStore has ZERO callers. T43's shadow comparison has nothing to")
        print("      shadow — see D-T42D-GRAPHSTORE-HAS-NO-CALLERS.")

    if len(concrete) > MAX_CONCRETE_IMPORTERS:
        print(f"\n[port-adoption-gate] FAIL — direct binding GREW to {len(concrete)}.\n")
        print("  Sealed B1 makes the ports the substitutability boundary, and T42 has built")
        print("  a second adapter (AGE) that only reachable code can benefit from. A module")
        print("  importing `neo4j_repos` breaks when the engine changes even if it contains")
        print("  no Cypher — which is why `graph-port-gate` passing is not this check.")
        print("  Import a port instead, or lower the ceiling in the same commit that")
        print("  justifies raising it.")
        return 1

    if len(concrete) < MAX_CONCRETE_IMPORTERS:
        print(f"\n[port-adoption-gate] FAIL — adoption IMPROVED to {len(concrete)} but the "
              f"ceiling still says {MAX_CONCRETE_IMPORTERS}.\n")
        print("  Lower it — that is T17 progress and recording it is the point. A stale")
        print("  ceiling also leaves headroom a future module can occupy unnoticed, which")
        print("  is the failure this gate exists to prevent.")
        return 1

    print("[port-adoption-gate] PASS — exactly at the ceiling; it can only fall")
    return 0


if __name__ == "__main__":
    sys.exit(main())
