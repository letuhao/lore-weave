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
import re
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
#: 18 -> 19 (2026-08-22, T54): `main.py` imports the provider to build the AGE pool at
#: lifespan. The floor rising on a CUTOVER commit is the point of the floor — T42/T43 shipped
#: an adapter nobody could select, and adoption is the number that would have shown it.
MIN_GRAPHSTORE_ADOPTERS = 19
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
#: 3 -> 2 (2026-08-21, T25 (3)): `routers/public/entities.py` migrated. The bypass is now the
#: BENCHMARK FLOOR and nothing else -- **no production module reads the Neo4j vector indexes**,
#: which is the precondition for deleting their DDL from `neo4j_schema.cypher`.
MAX_VECTOR_BYPASS = 2
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


def _repo_symbols(tree: ast.AST) -> set[str]:
    """Names this file pulls specifically out of `neo4j_repos` — the class-(d) input.

    Narrower than `_imported_symbols`, deliberately: that one returns every `from X import`
    name in the file, so a module importing `merge_entity` from a SERVICE layer would be
    scored as needing a port operation it does not need.

    ⚠️ A SUBMODULE import is resolved to the attributes actually USED, and that correction is
    worth more than it looks. `from app.db.neo4j_repos import maintenance` binds nine
    functions; §1.2 decided five of them stay engine-specific forever and two became port
    operations. Scoring the bare name `maintenance` puts all five janitor callers in class (d)
    — work that spec text says will never be done — which is one of the two errors in the
    hand count this replaces. `maintenance.delete_orphan_extraction_sources` is checkable
    against §1.2 by name; `maintenance` is not.

    A submodule imported and never dereferenced yields the bare name, which stays class (d).
    That is the conservative direction: an unresolvable import counts as work remaining.
    """
    out: set[str] = set()
    subs: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and _CONCRETE in node.module:
            for al in node.names:
                out.add(al.name)
                subs[al.asname or al.name] = al.name
        elif isinstance(node, ast.Import):
            for al in node.names:
                if _CONCRETE in al.name:
                    leaf = al.name.rsplit(".", 1)[-1]
                    out.add(leaf)
                    subs[al.asname or leaf] = leaf
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                and node.value.id in subs:
            real = subs[node.value.id]
            if real in out:
                out.discard(real)
            out.add(f"{real}.{node.attr}")
    return out


def scan() -> tuple[list[str], list[str], list[str], list[str], dict[str, set[str]]]:
    concrete: list[str] = []
    ported: list[str] = []
    graphstore: list[str] = []
    vbypass: list[str] = []
    # ⚠️ ONE walk, ONE population. The class-(d) split below reads these symbols rather
    # than re-scanning: a second scanner is how one concept acquires two readers that
    # disagree, and the number it produces decides whether the engine swap is reachable.
    csyms: dict[str, set[str]] = {}
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
                csyms[rel.replace(os.sep, "/")] = _repo_symbols(tree)
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
    return sorted(concrete), sorted(ported), sorted(graphstore), sorted(vbypass), csyms


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

    # ── the class-(d) split ──────────────────────────────────────────────────────────
    # The distinction this gate now rests on is OPERATION vs CONSTANT, and getting it wrong
    # is not hypothetical: the hand classification it replaces filed whole modules under
    # "vector-layer" because they imported one vector name, and under-reported the blocking
    # population by 14. So the cases below are the MIXED ones, not the clean ones — a module
    # is class (d) if ANY imported name is an unported operation, however much else it takes.
    #
    # Deliberately NOT the symbols this classifier was written against: `link_to_glossary`
    # (a real repo function) and `STATUS_VALUES` (a real repo constant) come from modules the
    # design never looked at, so a pass here is not a pass by construction.
    mixed = classify({"svc/x.py": {"STATUS_VALUES", "link_to_glossary"}})["svc/x.py"]
    if mixed[0] != CLASS_D or "link_to_glossary" not in mixed[1]:
        print(f"  FAIL — a module importing a constant AND an operation scored {mixed[0]}, "
              f"not class (d); that is the exact error the stale hand count made")
        ok = False

    const_only = classify({"svc/x.py": {"STATUS_VALUES"}})["svc/x.py"]
    if const_only[0] == CLASS_D:
        print("  FAIL — a CONSTANT-only importer was scored as needing a port operation; "
              "moving a constant is not growing a port")
        ok = False

    # And the other direction: dropping the operation must move the module OUT. A classifier
    # that only ever adds is a ratchet that can never record progress.
    if const_only[0] == mixed[0]:
        print("  FAIL — removing the operation import did not change the class")
        ok = False

    covered = classify({"svc/x.py": {"relations_for"}})["svc/x.py"]
    if covered[0] == CLASS_D:
        print("  FAIL — an operation the port ALREADY has was counted as missing")
        ok = False

    oneshot = classify({"db/migrations/backfill_x.py": {"link_to_glossary"}})
    if oneshot["db/migrations/backfill_x.py"][0] != CLASS_C:
        print("  FAIL — a one-shot migration script was not classed (c); §1.3 settled that "
              "a script running once against a known engine is not a port caller")
        ok = False

    # `_repo_symbols` must not score a name imported from somewhere ELSE. A service layer
    # with its own `merge_entity` would otherwise inflate class (d) with modules that are
    # not bound to the engine at all.
    foreign = ast.parse("from app.services.entities import merge_entity" + chr(10))
    if _repo_symbols(foreign):
        print("  FAIL — a same-named import from a NON-repo module was scored as a repo symbol")
        ok = False
    submod = ast.parse("from app.db.neo4j_repos import maintenance" + chr(10))
    if "maintenance" not in _repo_symbols(submod):
        print("  FAIL — a whole-SUBMODULE import was missed; it binds every operation in it")
        ok = False

    # ── the two corrections that moved the number ────────────────────────────────────
    # Both are about a module being filed under ONE of its imports. The cases below use
    # symbols the classifier was NOT designed against — `clear_embedding_model_tag` rather
    # than the orphan-source janitor, `find_passages_by_fulltext` rather than the vector
    # readers — so a pass here is not a pass by construction.
    janitor = classify({"jobs/j.py": {"maintenance.clear_embedding_model_tag"}})["jobs/j.py"]
    if janitor[0] != CLASS_OUT:
        print(f"  FAIL — a §1.2 janitor caller scored {janitor[0]}; the spec says destructive "
              f"janitors stay engine-specific FOREVER, so it is not work remaining")
        ok = False

    # The negative that makes the check mean something: a NON-janitor function reached through
    # the same submodule must still count. §1.2 kept `count_nodes_by_label` in `neo4j_repos`
    # as a Neo4j-internal helper — a caller of it is bound to the engine.
    helper = classify({"jobs/j.py": {"maintenance.count_nodes_by_label"}})["jobs/j.py"]
    if helper[0] != CLASS_D:
        print("  FAIL — a NON-janitor function reached through `maintenance` was excused; the "
              "submodule is not the unit of the decision, the function is")
        ok = False

    # An unresolved submodule import (bound, never dereferenced) must stay class (d). The
    # conservative direction: what the classifier cannot read is work, not absence of work.
    opaque = classify({"jobs/j.py": {"maintenance"}})["jobs/j.py"]
    if opaque[0] != CLASS_D:
        print("  FAIL — a submodule bound but never dereferenced was excused rather than "
              "counted; an unreadable import is not a migrated one")
        ok = False

    deleted = classify({"svc/x.py": {"find_passages_by_fulltext"}})["svc/x.py"]
    if deleted[0] == CLASS_D:
        print("  FAIL — a symbol §3.1 DELETES was counted as needing a port operation; "
              "building it would be building the obsolete (A13 refused this by hand)")
        ok = False

    # ⚠️ This case exists because BITE 5 found the hole. Removing the bare-name discard in
    # `_repo_symbols` moved the LIVE count 34 -> 37 while every check above stayed GREEN: they
    # hand `classify` an already-resolved symbol set, so none of them ever ran the resolution.
    # A selftest that cannot see the step it is meant to protect is the "detector validated on
    # the cases that motivated it" shape, and it was green by construction until this line.
    src = ("from app.db.neo4j_repos import maintenance" + chr(10) +
           "async def run(s):" + chr(10) +
           "    await maintenance.clear_embedding_model_tag(s)" + chr(10))
    resolved = _repo_symbols(ast.parse(src))
    if "maintenance" in resolved:
        print("  FAIL — the bare submodule name survived alongside its resolved attribute; "
              "the caller then counts as needing every operation in the module")
        ok = False
    if "maintenance.clear_embedding_model_tag" not in resolved:
        print("  FAIL — the dereferenced attribute was not resolved out of the submodule")
        ok = False
    if classify({"jobs/j.py": resolved})["jobs/j.py"][0] != CLASS_OUT:
        print("  FAIL — a janitor-only caller parsed FROM SOURCE did not reach class (§1.2); "
              "the resolution and the classification disagree end to end")
        ok = False

    # ── the dialect ratchet (§10.1's second path) ────────────────────────────────────
    # These live inside triple-quoted Cypher STRINGS, so the detector is text and its risk is
    # the opposite of the AST ones above: it CANNOT tell a construct from prose about it. That
    # is an accepted limit inside `neo4j_repos`, where a docstring naming `ON CREATE SET` is
    # describing this file's own Cypher — but the counting itself must be right, and the
    # case-insensitive and spacing variants are where a hand-written regex silently misses.
    probe = (
        "q = '''MERGE (e:E {id:1})" + chr(10) +
        "ON  CREATE   SET e.a = datetime()" + chr(10) +
        "on match set e.b = 1" + chr(10) +
        "CALL  { RETURN 1 }" + chr(10) +
        "FOREACH (x IN [1] | SET e.c = 2)" + chr(10) +
        "CALL apoc.coll.union([], [])'''"
    )
    counts = {name: len(pat.findall(probe)) for name, pat in _DIALECT_PATTERNS}
    for name, want in (("ON CREATE SET", 1), ("ON MATCH SET", 1), ("datetime()", 1),
                       ("CALL { }", 1), ("FOREACH", 1), ("apoc.", 1)):
        if counts[name] != want:
            print(f"  FAIL — dialect detector counted {name!r} {counts[name]} times, "
                  f"expected {want} (irregular spacing / lower case are the real forms)")
            ok = False

    # The negative: `datetime(x)` is NOT the zero-arg call AGE lacks a name for, and counting
    # it would inflate a ceiling that is supposed to reach zero.
    if [len(p.findall("f.at = datetime($when)")) for n, p in _DIALECT_PATTERNS if n == "datetime()"][0]:
        print("  FAIL — `datetime($when)` was counted as the zero-arg `datetime()`")
        ok = False

    # The correction that matters most about this detector: PROSE must not count. Its ceiling's
    # target is ZERO, and a docstring explaining the migration would hold the number above the
    # floor forever — the exact defect §1.3 records about the module ceiling above.
    doc_only = (
        '"""This query used to say ON CREATE SET and call datetime().' + chr(10) +
        'It also mentioned apoc.coll.union and a CALL { } subquery."""' + chr(10) +
        "x = 1" + chr(10) +
        "# ON MATCH SET e.a = datetime()" + chr(10)
    )
    if _code_strings(doc_only).strip():
        print("  FAIL — a module docstring and a comment survived `_code_strings`; every "
              "construct named in prose would be counted as unmigrated Cypher")
        ok = False

    # And the other direction, on a case the fix was NOT derived from: a Cypher string assigned
    # to a NAME is code and must survive, including one nested in a function.
    real = (
        '"""doc."""' + chr(10) +
        "def q():" + chr(10) +
        '    """also doc."""' + chr(10) +
        "    return " + chr(34)*3 + "MERGE (e:E) ON CREATE SET e.at = datetime()" + chr(34)*3 + chr(10)
    )
    kept = _code_strings(real)
    if "ON CREATE SET" not in kept or "datetime()" not in kept:
        print("  FAIL — a real Cypher string was dropped as if it were a docstring; the "
              "backlog would read lower than it is")
        ok = False
    if "doc." in kept:
        print("  FAIL — a nested function docstring was kept")
        ok = False

    print(f"[port-adoption-gate] SELFTEST {'PASS' if ok else 'FAIL'} — distinguishes a real "
          f"import from a docstring and a comment, in both directions (non-vacuous)")
    return 0 if ok else 1


# ── CLASS (d): THE POPULATION THAT ACTUALLY BLOCKS THE ENGINE SWAP ──────────────────────
#
# `MAX_CONCRETE_IMPORTERS` counts every module importing `neo4j_repos`, and §1.3 is right that
# it never reaches zero: the benchmarks bind the Neo4j backend ON PURPOSE, the one-shot
# migration scripts ran once against a known engine, and §1.2 keeps the destructive janitors
# engine-specific forever. So the ceiling cannot be the cutover criterion. The number that CAN
# be — the modules needing a port OPERATION that does not exist — is derived here.
#
# 🔴 It was carried in PROSE ("28", A13, hand-classified 2026-08-14) and it went stale. A13's
# own check was that the four classes SUM to 54, which is a criterion that cannot fail: any
# partition of 54 sums to 54. Arithmetic was never the risk; the assignment was. Re-derived
# from the AST on 2026-08-22 it is **34**, and those 34 demand ~78 distinct operations against
# a port of 21.
#
# Both halves of the error ran the same way — a module was filed under the class of ONE of its
# imports while other imports still bound it:
#
#   *  A13 counted 17 "vector-layer". Only 5 modules are vector-ONLY; the rest import a §3.1
#      name AND an unported operation, and a module leaves this population when its LAST
#      binding goes, not its first. This gate's own ceiling note records the same correction
#      at 57 — "three call sites became zero and the ceiling fell by only one".
#   *  A13 counted 5 §1.2 janitors. Only 3 are janitor-only; `internal_admin` and
#      `public/extraction` call a janitor AND ten other unported operations between them.
#
# Neither number was checkable by reading, which is the argument for deriving it. A figure that
# decides whether a cutover is reachable does not belong in a sentence.
_REPO_DIR = os.path.join(SCAN_ROOT, "db", "neo4j_repos")
_PORT_FILE = os.path.join(SCAN_ROOT, "ports", "graph_store.py")
_DOMAIN_FILES = ("graph_models.py", "graph_labels.py")

#: §3.1 moves the passage/vector layer to Postgres — these repo modules are DELETED, not
#: ported. Stated as MODULES rather than as a list of names on purpose: the first cut of this
#: classifier hand-listed thirteen symbols and still missed `recent_passage_texts`,
#: `count_passages_by_source_type` and `find_passages_by_fulltext`, because a name only looks
#: like the vector layer once you already know it is. Every one of them lives in `passages.py`.
#: A13 refused `get_chapter_index_for_source` for exactly this reason, by hand, one symbol at a
#: time — "it is passage-layer, and §3.1 moves those to Postgres".
_DELETED_MODULES = ("passages", "vector_indexes")
#: The entity-vector reads §3.1 also moves, which live in `entities.py`/`graph_state.py` beside
#: operations that stay. Module scope cannot separate these, so they are named.
_ENTITY_VECTOR = {
    "find_entities_by_vector", "find_entities_needing_embedding",
    "project_has_embedded_passages",
}
#: §1.2, verbatim: "Destructive janitors stay ENGINE-SPECIFIC and out of the port." A promise
#: to delete orphan nodes in ANY graph engine is a promise about housekeeping, and no cutover
#: measurement depends on who collects the garbage. Reached as `maintenance.<name>`.
_JANITORS = {
    "delete_orphan_extraction_sources", "invalidate_stale_quarantined_facts",
    "reconcile_evidence_count_for_label", "clear_embedding_model_tag",
    "delete_project_nodes_by_label",
}
#: Runs once, against a known engine, at a known version. §1.3(c) declared these out of port
#: scope: substitutability for code that will never be substituted buys nothing.
_ONE_SHOT_PREFIXES = ("benchmark/", "db/migrations/")

CLASS_D = "(d) needs port operations"
CLASS_C = "(c) one-shot / benchmark — out of port scope (1.3c)"
CLASS_B = "(b) deleted by 3.1, or already ported/moved"
CLASS_A = "(a) constants and types only — a MOVE, not port growth"
CLASS_OUT = "(1.2) engine-specific janitors — out forever"

#: A shrink-only ratchet, same contract as the ceiling above. This is the first DERIVED value;
#: every earlier figure for this population was hand-written prose, and it drifted.
MAX_CLASS_D = 34


def _symbol_home(path: str) -> dict[str, tuple[str, str]]:
    """Every top-level name `neo4j_repos` exports, as (kind, defining module).

    The KIND separates "move a constant" from "grow an operation and write it twice"; the
    MODULE is what §3.1 deletes. Conflating either with the other produced the stale count.
    """
    homes: dict[str, tuple[str, str]] = {}
    if not os.path.isdir(path):
        return homes
    for fname in sorted(os.listdir(path)):
        if not fname.endswith(".py"):
            continue
        mod = fname[:-3]
        try:
            tree = ast.parse(open(os.path.join(path, fname), encoding="utf-8",
                                  errors="replace").read())
        except (OSError, SyntaxError):
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                homes.setdefault(node.name, ("func", mod))
            elif isinstance(node, ast.ClassDef):
                homes.setdefault(node.name, ("class", mod))
            elif isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        homes.setdefault(tgt.id, ("const", mod))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                homes.setdefault(node.target.id, ("const", mod))
        if mod != "__init__":
            homes.setdefault(mod, ("submodule", mod))
    return homes


def _names_in(path: str) -> set[str]:
    out: set[str] = set()
    try:
        tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())
    except (OSError, SyntaxError):
        return out
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            out.add(node.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    out.add(tgt.id)
    return out


def _port_operations() -> set[str]:
    ops: set[str] = set()
    try:
        tree = ast.parse(open(_PORT_FILE, encoding="utf-8", errors="replace").read())
    except (OSError, SyntaxError):
        return ops
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                not node.name.startswith("_"):
            ops.add(node.name)
    return ops


def _domain_symbols() -> set[str]:
    """Models and label vocabularies already MOVED out of the engine layer (T17, §1.2).

    `neo4j_repos` re-exports them preserving class identity, so importing one is a stale import
    PATH, not a binding to Neo4j. Counting these as engine bindings overstates the work.
    """
    out: set[str] = set()
    for fname in _DOMAIN_FILES:
        out |= _names_in(os.path.join(SCAN_ROOT, "domain", fname))
    return out


def classify(concrete_symbols: dict[str, set[str]]) -> dict[str, tuple[str, list[str], list[str]]]:
    """Split the concrete binders into the classes §1.2 and §1.3 decided, by IMPORTED SYMBOL.

    A module is class (d) if ANY name it still takes from `neo4j_repos` is an operation the
    port does not have and no decision retires. One is enough — that is the whole correction
    over the hand count, which filed modules under their most memorable import.
    """
    homes = _symbol_home(_REPO_DIR)
    port_ops = _port_operations()
    domain = _domain_symbols()
    out: dict[str, tuple[str, list[str], list[str]]] = {}
    for rel, syms in concrete_symbols.items():
        slash = rel.replace(os.sep, "/")
        ops: set[str] = set()
        types: set[str] = set()
        for sym in syms:
            sub, _, leaf = sym.partition(".")
            bare = leaf or sub
            kind, home = homes.get(bare, ("unknown", ""))
            if leaf:
                home = sub          # a dotted name's home is the submodule it came through
            if bare in domain or bare in port_ops:
                continue            # already moved, or the port already answers it
            if home in _DELETED_MODULES or bare in _ENTITY_VECTOR:
                continue            # §3.1 deletes it; porting it would be building the obsolete
            if bare in _JANITORS:
                types.add("1.2:" + bare)    # recorded, never a reason to grow the port
                continue
            if kind in ("func", "submodule"):
                ops.add(sym)
            else:
                types.add(sym)
        if slash.startswith(_ONE_SHOT_PREFIXES):
            cls = CLASS_C
        elif ops:
            cls = CLASS_D
        elif types and all(x.startswith("1.2:") for x in types):
            cls = CLASS_OUT
        elif types:
            cls = CLASS_A
        else:
            cls = CLASS_B
        out[slash] = (cls, sorted(ops), sorted(types))
    return out


# ── THE SECOND PATH TO ZERO (spec §10.1) ────────────────────────────────────────────────
#
# §10.1 decided that class (d) does NOT reach zero by growing `GraphStore` to 106 methods —
# 85 operations against a port of 21 would make the port a mirror of `neo4j_repos` with a
# different import path, which its own law forbids ("grows by demand, not by inventory").
# Substitutability lands at two levels instead: the port stays the DOMAIN boundary, and the
# repo layer becomes ENGINE-AGNOSTIC.
#
# That second path needs a number, or it is a plan with no mechanism — the failure this file
# already records twice (the stale 28, the stale vector precondition). This is that number:
# the Neo4j-ONLY dialect sites left inside `neo4j_repos`.
#
# Each is a construct AGE rejects and has a measured equivalent for
# (`docs/measurements/2026-08-11-age-construct-probe.md`, extended by T57–T59):
#
#   ON CREATE SET  ->  SET x = coalesce(x, v)
#   ON MATCH SET   ->  unconditional SET
#   datetime()     ->  timestamp()
#   CALL { }       ->  SQL CTE / LATERAL          (AGE lives in Postgres; the host supplies it)
#   FOREACH        ->  two statements in one transaction   (T58)
#   apoc.          ->  no AGE equivalent at all; must be expressed another way
#
# ⚠️ A COUNT, not a proof. Zero here means no *known* Neo4j-only construct remains, NOT that
# the layer runs on AGE — that is what the conformance suite and the shadow differential are
# for, and they are the ones with teeth. This number exists so the translation cannot stall
# silently, the way class (d) sat at "28" for eight days.
_DIALECT_ROOT = os.path.join(SCAN_ROOT, "db", "neo4j_repos")
_DIALECT_PATTERNS = (
    ("ON CREATE SET", re.compile(r"ON\s+CREATE\s+SET", re.I)),
    ("ON MATCH SET", re.compile(r"ON\s+MATCH\s+SET", re.I)),
    ("datetime()", re.compile(r"\bdatetime\s*\(\s*\)")),
    ("CALL { }", re.compile(r"CALL\s*\{")),
    ("FOREACH", re.compile(r"\bFOREACH\s*\(")),
    ("apoc.", re.compile(r"\bapoc\.")),
)

#: Shrink-only, like every other number here. 161 measured 2026-08-22 (T62), the first time
#: this backlog was counted rather than estimated. The 2026-08-11 probe predicted "~33
#: anchoring rewrites + 157 renames + 14 CALL{}"; measured inside the repo layer it is 37
#: anchoring, 106 renames, 14 CALL{}, plus 3 FOREACH and 1 apoc the probe did not look for.
MAX_NEO4J_DIALECT_SITES = 65


def _code_strings(src: str) -> str:
    """Every string literal in the module that is NOT a docstring, joined.

    ⚠️ The first cut of this detector matched the RAW FILE TEXT, and it over-counted by 10:
    a docstring naming `ON CREATE SET` was scored as Cypher, and the single `apoc.` hit in the
    whole layer turned out to be a COMMENT — there is no APOC dependency left in `neo4j_repos`
    at all. Shipped 2026-08-22 as an "accepted limit"; corrected the same day, because it was
    not one. **This ceiling's target is ZERO, and prose can never reach zero** — a document
    explaining the migration would have held the number above the floor forever, which is the
    exact defect §1.3 records about `port-adoption-gate`'s own ceiling.

    Comments never appear as AST nodes, so they are excluded for free. Docstrings are excluded
    by identity, not by heuristic.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    docs: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and isinstance(node.body[0], ast.Expr) \
                    and isinstance(node.body[0].value, ast.Constant) \
                    and isinstance(node.body[0].value.value, str):
                docs.add(id(node.body[0].value))
    return "\n".join(
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs
    )


def scan_dialect() -> dict[str, dict[str, int]]:
    """Neo4j-only Cypher constructs per repo module, counted in CODE STRINGS only.

    The constructs live inside triple-quoted Cypher strings, so the match itself is textual —
    but it runs over `_code_strings`, not the raw file, so a docstring describing the
    migration is not counted as the migration being incomplete."""
    out: dict[str, dict[str, int]] = {}
    if not os.path.isdir(_DIALECT_ROOT):
        return out
    for fname in sorted(os.listdir(_DIALECT_ROOT)):
        if not fname.endswith(".py"):
            continue
        try:
            src = open(os.path.join(_DIALECT_ROOT, fname), encoding="utf-8",
                       errors="replace").read()
        except OSError:
            continue
        blob = _code_strings(src)
        hits = {name: len(pat.findall(blob)) for name, pat in _DIALECT_PATTERNS}
        hits = {k: v for k, v in hits.items() if v}
        if hits:
            out[fname[:-3]] = hits
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="show the modules")
    ap.add_argument("--dialect", action="store_true",
                    help="list the Neo4j-only Cypher constructs left in the repo layer")
    ap.add_argument("--classify", action="store_true",
                    help="split the concrete binders into the four classes of §1.3")
    ap.add_argument("--selftest", action="store_true", help="prove this gate can go red")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not os.path.isdir(SCAN_ROOT):
        print(f"[port-adoption-gate] SKIP — {SCAN_ROOT} not present")
        return 0

    concrete, ported, graphstore, vbypass, csyms = scan()

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

    classes = classify(csyms)
    class_d = sorted(k for k, v in classes.items() if v[0] == CLASS_D)

    if args.classify:
        demand: dict[str, int] = {}
        buckets: dict[str, list[str]] = {}
        for rel, (cls, ops, types) in sorted(classes.items()):
            buckets.setdefault(cls, []).append(rel)
        for cls in (CLASS_D, CLASS_A, CLASS_B, CLASS_C, CLASS_OUT):
            print(f"  {len(buckets.get(cls, [])):3d}  {cls}")
        print()
        for cls in (CLASS_D, CLASS_A, CLASS_B, CLASS_C, CLASS_OUT):
            print(f"===== {cls} ({len(buckets.get(cls, []))}) =====")
            for rel in buckets.get(cls, []):
                _, ops, types = classes[rel]
                print(f"  {rel}")
                if ops:
                    print(f"        ops:   {chr(44).join(ops)}")
                    if cls == CLASS_D:
                        for o in ops:
                            demand[o] = demand.get(o, 0) + 1
                if types:
                    print(f"        types: {chr(44).join(types)}")
            print()
        port_ops = _port_operations()
        print(f"  class (d) demands {len(demand)} distinct operations; the port has "
              f"{len(port_ops)}. Every one costs a Neo4j impl, an AGE impl, a fake and")
        print("  a conformance case, so this is the number that prices the cutover.")
        for op, n in sorted(demand.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"    {n:3d}  {op}")
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
    # `< MAX`, NOT `MIN < len < MAX`. The two-sided form left a hole the size of the whole
    # point: with MAX=3 and MIN=2, a count of 2 matched no branch at all and the gate printed
    # NOTHING and returned 0 -- it went silent exactly when the migration finished, and a
    # regression back to 3 would also have matched no branch. Found 2026-08-21 the moment the
    # second reader landed and the bypass line vanished from the output.
    if len(vbypass) < MAX_VECTOR_BYPASS:
        print(f"[port-adoption-gate] FAIL — vector bypass IMPROVED to {len(vbypass)} but the "
              f"ceiling still says {MAX_VECTOR_BYPASS}.")
        print("  Lower it in the same commit. That is T25 (3) progress and recording it is the")
        print("  point — a stale ceiling leaves headroom a NEW bypass can occupy unnoticed,")
        print("  which is exactly how these two got past the module-level count.")
        return 1
    live = [v for v in vbypass if not v.startswith("benchmark/")]
    print(f"[port-adoption-gate] vector bypass {len(vbypass)}/{MAX_VECTOR_BYPASS} "
          f"(floor {MIN_VECTOR_BYPASS})"
          + (f" — {len(live)} LIVE reader(s) still block T25 (3): {live}" if live
             else " — no LIVE reader left; the remainder is the benchmark floor"))
    # Two explicit branches, never `MIN < n < MAX`. The vector bypass carried the
    # two-sided form and went SILENT at exactly the count that mattered — see the note
    # above it. A ratchet that prints nothing on success cannot be trusted on failure.
    if len(class_d) > MAX_CLASS_D:
        print(f"{chr(10)}[port-adoption-gate] FAIL — class (d) GREW to {len(class_d)} "
              f"(ceiling {MAX_CLASS_D}).{chr(10)}")
        print("  A module now needs a port operation that does not exist. This is the")
        print("  population that blocks AGE-as-the-only-engine: while it is non-empty the")
        print("  graph is split across two stores inside one service — measured on dev")
        print("  2026-08-22, 19 adopters reading an EMPTY AGE while 54 binders read a")
        print("  populated Neo4j. Run --classify to see which module and which operation.")
        return 1
    if len(class_d) < MAX_CLASS_D:
        print(f"{chr(10)}[port-adoption-gate] FAIL — class (d) IMPROVED to {len(class_d)} "
              f"but the ceiling still says {MAX_CLASS_D}.{chr(10)}")
        print("  Lower it in the same commit (rule 5). This number is the cutover")
        print("  criterion and the last one to be carried in prose went stale by 14.")
        return 1
    print(f"[port-adoption-gate] class (d) {len(class_d)}/{MAX_CLASS_D} — modules needing "
          f"a port operation that does not exist; AGE cannot be the only engine until 0")
    dialect = scan_dialect()
    dsites = sum(sum(v.values()) for v in dialect.values())

    if args.dialect:
        print(f"[port-adoption-gate] {dsites} Neo4j-only dialect site(s) in the repo layer"
              f" (ceiling {MAX_NEO4J_DIALECT_SITES})")
        for mod in sorted(dialect, key=lambda m: -sum(dialect[m].values())):
            hits = dialect[mod]
            detail = ", ".join(f"{k} x{v}" for k, v in sorted(hits.items()))
            print(f"  {sum(hits.values()):4d}  {mod:22s} {detail}")
        return 0

    if dsites > MAX_NEO4J_DIALECT_SITES:
        print(f"{chr(10)}[port-adoption-gate] FAIL — Neo4j-only dialect GREW to {dsites} "
              f"(ceiling {MAX_NEO4J_DIALECT_SITES}).{chr(10)}")
        print("  A new `ON CREATE SET` / `datetime()` / `CALL {}` / `FOREACH` / `apoc.` was")
        print("  added inside `neo4j_repos`. Spec §10.1 makes the repo layer ENGINE-AGNOSTIC;")
        print("  every one of these has a measured AGE equivalent (2026-08-11 probe, T57-T59).")
        print("  Run --dialect to see where.")
        return 1
    if dsites < MAX_NEO4J_DIALECT_SITES:
        print(f"{chr(10)}[port-adoption-gate] FAIL — dialect IMPROVED to {dsites} but the "
              f"ceiling still says {MAX_NEO4J_DIALECT_SITES}.{chr(10)}")
        print("  Lower it in the same commit (rule 5). This is the SECOND path to class (d)")
        print("  zero and the one §10.1 chose; a stale ceiling is how the first one sat at 28.")
        return 1
    print(f"[port-adoption-gate] Neo4j-only dialect {dsites}/{MAX_NEO4J_DIALECT_SITES} in the "
          f"repo layer — §10.1's second path to class (d) zero")
    print("[port-adoption-gate] PASS — exactly at the ceiling; it can only fall")
    return 0


if __name__ == "__main__":
    sys.exit(main())
