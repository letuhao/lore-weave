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
# **64** (2026-08-13) — the domain models moved to `app/domain/graph_models.py`, so
# `ports/graph_store.py` STOPPED COUNTING ITSELF: the port had been importing `Entity`,
# `Relation` and `Event` from the implementation it exists to abstract. Two model-only
# importers followed. This is the ceiling becoming ABLE to fall — before it, no amount of
# call-site migration could reach zero.
# **58** (2026-08-13, T24b-b) — `context/selectors/passages.py` stopped importing
# `neo4j_repos.passages` when the L3 selector's vector read moved onto `VectorStore`.
# The first ceiling drop from a READ-PATH migration rather than a model move: the
# other two migrated readers still import the module for non-vector names
# (`SUPPORTED_PASSAGE_DIMS`, `KNOWN_SOURCE_TYPES`, the CJK lexical leg), which is why
# three call sites became zero and the ceiling fell by only one.
# **57** (2026-08-13, A9) — `context/selectors/glossary.py` reaches ENTITY vectors through
# `VectorStore` now. Measured first (rule 8): repointing the two shared CONSTANTS
# (`SUPPORTED_PASSAGE_DIMS`, `EVENT_ORDER_CHAPTER_STRIDE`) out of the repo layer would have
# moved this number by ZERO — all eleven importers keep other repo names — which is what
# the A6 note predicted and why class (a) is not a batch on its own. A module falls off
# only when its LAST repo import goes.
# **56** (2026-08-14, A10) — `jobs/stats_updater.py` reconciles the project stats card
# through `GraphStore.project_graph_stats` instead of `maintenance.count_nodes_by_label`,
# and the two label vocabularies moved to `app/domain/graph_labels.py` (spec §1.2).
# **54** (2026-08-14, A11) — the two benchmark modules whose calls `VectorStore` already
# covers: `mode3_query_runner` (retrieval-quality MRR) onto `search`, `fixture_loader` onto
# `upsert`. NO port growth. Their two siblings stay on the repo deliberately — they measure the
# BACKEND (ANN recall, a per-engine corpus dump) and need `oversample_factor`, which the port
# refuses to expose because it is one engine's weakness rather than a domain concept.
MAX_CONCRETE_IMPORTERS = 54

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
#
# **11** — `mirror/glossary_mirror.py`, the glossary→KG mirror detector
# (D-GLOSSARY-KG-MIRROR-HAS-NO-RECONCILER). It asks presence through `neighborhood()`
# rather than reaching for `neo4j_repos`, so the divergence it reports is measured against
# whichever adapter T43 selects — a detector bound to Neo4j would have to be rewritten by
# the engine swap it is supposed to survive.
#
# **13** — T17 batch: `routers/internal_kg_neighborhood.py` and `routers/internal_wiki.py`.
# Both asked the port's own question (one entity plus its capped one-hop neighbourhood)
# while reaching past it to the same `neo4j_repos` function, so neither produced a shadow
# observation for T43 to measure. Ceiling 69 -> 67 in the same move.
#
# **14** — `extraction/motif_beat.py`, via `events_in_window(axis="narrative")`.
#
# ⚠️ Note the CEILING did not move with it, and that is not a miss: motif_beat still
# imports the `Event` MODEL from `neo4j_repos`, which this gate counts as a concrete
# import because it is one. The ceiling cannot reach zero while the port's own types
# live in the concrete layer — `ports/graph_store.py` is itself counted for exactly
# that reason. Moving the models is a separate slice; the number stays honest until
# then rather than being redefined to look better.
# **18** — T17 A10: `jobs/stats_updater.py`.
MIN_GRAPHSTORE_ADOPTERS = 18

_CONCRETE = "neo4j_repos"

#: T25 (3)'s REAL precondition, and it is not a database operation.
#:
#: The grant (PO 2026-08-21, §7.1) authorised dropping the Neo4j vector indexes. Measured the
#: same day: a graph-only DROP is COSMETIC. `neo4j_schema.cypher` declares all of them with
#: `CREATE VECTOR INDEX ... IF NOT EXISTS` and `main.py:167` runs the schema at lifespan start,
#: so the index comes back. PROVEN on lw-iso, not read: dropped `entity_embeddings_384`,
#: restarted the service, and it was ONLINE again within four seconds.
#:
#: So retiring the indexes means deleting their DDL, and that cannot land while production
#: still queries them. These are the modules that do -- by IMPORTED SYMBOL, because the
#: module-level `neo4j_repos` count above cannot separate a vector reader from any other
#: caller, and it was the count everyone was watching.
#:
#:   benchmark/flat_knn_rawsearch.py    FLOOR -- benchmarks the Neo4j backend ON PURPOSE
#:   benchmark/vector_backend_bench.py  FLOOR -- same; comparing backends is the point
#:   routers/public/entities.py:584     LIVE  -- public semantic entity search
#:   tools/executor.py:494              LIVE  -- the memory-search tool's semantic leg
#:
#: The two LIVE ones must reach zero before the DDL can go. Neither was in §3.1's reader
#: list, which named three and missed these two.
_VECTOR_SYMS = {"find_entities_by_vector", "find_passages_by_vector"}
#: the adapter is the sanctioned caller -- it IS the port's Neo4j implementation
_VECTOR_EXEMPT = {"adapters/neo4j_vector_store.py"}
#: 4 -> 3 (2026-08-21, T25 (3)): `tools/executor.py` migrated onto the port. Its test doubles
#: moved with it -- from stubbing `find_passages_by_vector` to stubbing `get_vector_store`,
#: because a double shaped like the OLD return keeps passing while production calls something
#: else. `routers/public/entities.py` is the one LIVE reader left.
MAX_VECTOR_BYPASS = 3
#: benchmarks stay; a floor of 2 says so out loud rather than leaving a future reader to
#: "finish the job" by deleting the only thing that can compare the two backends.
MIN_VECTOR_BYPASS = 2

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


def _imported_symbols(tree: ast.AST) -> set[str]:
    """NAMES pulled in by `from X import name`. The module-level scan cannot see these, and
    a vector reader is invisible inside a 54-module `neo4j_repos` count."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            out.update(al.name for al in node.names)
    return out


def scan() -> tuple[list[str], list[str], list[str], list[str]]:
    concrete: list[str] = []
    ported: list[str] = []
    graphstore: list[str] = []
    vbypass: list[str] = []
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
            if (rel.replace(os.sep, "/") not in _VECTOR_EXEMPT
                    and _imported_symbols(tree) & _VECTOR_SYMS):
                vbypass.append(rel.replace(os.sep, "/"))
    return sorted(concrete), sorted(ported), sorted(graphstore), sorted(vbypass)


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

    # The symbol-level detector, same non-vacuity bar. A docstring that DISCUSSES the
    # migration must not count: `extraction/entity_embedder.py` and `ports/vector_store.py`
    # both name `find_entities_by_vector` in prose and neither is a bypass. Counting prose
    # would report 6 instead of 4 and bury the two real ones in noise.
    vreal = ast.parse("from app.db.neo4j_repos.entities import find_entities_by_vector" + chr(10))
    if not (_imported_symbols(vreal) & _VECTOR_SYMS):
        print("  FAIL — a real vector-search import was not detected")
        ok = False
    vprose = ast.parse(chr(34)*3 + "the mui#4 read path (find_entities_by_vector)." + chr(34)*3)
    vcomment = ast.parse("# find_passages_by_vector moved onto the port" + chr(10) + "x = 1")
    if (_imported_symbols(vprose) | _imported_symbols(vcomment)) & _VECTOR_SYMS:
        print("  FAIL — prose mentioning a vector reader was counted as a bypass")
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

    concrete, ported, graphstore, vbypass = scan()

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
        print("  this gate was written and is not now — T43 compares 21/21 operations.)")
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

    if len(vbypass) > MAX_VECTOR_BYPASS:
        print(f"[port-adoption-gate] FAIL — vector-search bypass GREW to {len(vbypass)} "
              f"(ceiling {MAX_VECTOR_BYPASS}): {vbypass}")
        print("  These query the Neo4j vector indexes directly. T25 (3) retires those indexes,")
        print("  and a graph DROP is cosmetic — neo4j_schema.cypher recreates them at startup")
        print("  (proven on lw-iso: dropped, restarted, ONLINE in 4s). Retiring them means")
        print("  deleting the DDL, which breaks every module on this list. Use the port.")
        return 1
    if len(vbypass) < MIN_VECTOR_BYPASS:
        print(f"[port-adoption-gate] FAIL — vector bypass fell to {len(vbypass)}, below the "
              f"floor {MIN_VECTOR_BYPASS}.")
        print("  The floor is the two BENCHMARKS, which call the Neo4j backend deliberately —")
        print("  deleting them removes the only thing that can compare the two backends, which")
        print("  is how a cutover stops being measurable. Lower the floor deliberately or")
        print("  restore the caller.")
        return 1
    if MIN_VECTOR_BYPASS < len(vbypass) < MAX_VECTOR_BYPASS:
        print(f"[port-adoption-gate] FAIL — vector bypass IMPROVED to {len(vbypass)} but the "
              f"ceiling still says {MAX_VECTOR_BYPASS}.")
        print("  Lower it in the same commit. That is T25 (3) progress and recording it is the")
        print("  point — a stale ceiling leaves headroom a NEW bypass can occupy unnoticed,")
        print("  which is exactly how these two got past the module-level count.")
        return 1
    if len(vbypass) > MIN_VECTOR_BYPASS:
        live = [v for v in vbypass if not v.startswith("benchmark/")]
        print(f"[port-adoption-gate] vector bypass {len(vbypass)}/{MAX_VECTOR_BYPASS} — "
              f"{len(live)} LIVE reader(s) still block T25 (3): {live}")
    print("[port-adoption-gate] PASS — exactly at the ceiling; it can only fall")
    return 0


if __name__ == "__main__":
    sys.exit(main())
