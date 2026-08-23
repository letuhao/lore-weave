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

    a module can call `graph_repos.merge_entity(...)`, contain no Cypher of its own,
    satisfy graph-port-gate completely — and still break the moment the engine changes.

Cypher being centralised says the *queries* live in one place. Substitutability says the
*call sites* go through the port. T42 has now built a second adapter (AGE); this gate is
what makes the second adapter reachable rather than merely present.

MEASURED 2026-08-12
-------------------
Modules under `app/`, excluding `app/db/graph_repos/` (the implementation) and
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

# `graph_repos` IS the Neo4j implementation and `adapters/` is where an implementation is
# allowed to be named — the adapters exist precisely to import it. Excluding them is not a
# loophole; including them would make the number measure the architecture working.
EXEMPT_DIRS = (
    os.path.join("db", "graph_repos"),
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
# `graph_repos.passages` when the L3 selector's vector read moved onto `VectorStore`.
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
# rather than reaching for `graph_repos`, so the divergence it reports is measured against
# whichever adapter T43 selects — a detector bound to Neo4j would have to be rewritten by
# the engine swap it is supposed to survive.
#
# **13** — T17 batch: `routers/internal_kg_neighborhood.py` and `routers/internal_wiki.py`.
# Both asked the port's own question (one entity plus its capped one-hop neighbourhood)
# while reaching past it to the same `graph_repos` function, so neither produced a shadow
# observation for T43 to measure. Ceiling 69 -> 67 in the same move.
#
# **14** — `extraction/motif_beat.py`, via `events_in_window(axis="narrative")`.
#
# ⚠️ Note the CEILING did not move with it, and that is not a miss: motif_beat still
# imports the `Event` MODEL from `graph_repos`, which this gate counts as a concrete
# import because it is one. The ceiling cannot reach zero while the port's own types
# live in the concrete layer — `ports/graph_store.py` is itself counted for exactly
# that reason. Moving the models is a separate slice; the number stays honest until
# then rather than being redefined to look better.
# **18** — T17 A10: `jobs/stats_updater.py`.
#: 18 -> 19 (2026-08-22, T54): `main.py` imports the provider to build the AGE pool at
#: lifespan. The floor rising on a CUTOVER commit is the point of the floor — T42/T43 shipped
#: an adapter nobody could select, and adoption is the number that would have shown it.
MIN_GRAPHSTORE_ADOPTERS = 19
_CONCRETE = "graph_repos"

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
#: module-level `graph_repos` count above cannot separate a vector reader from any other
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

    Only `Import` / `ImportFrom` nodes. A docstring that discusses `graph_repos`, or a
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
    a vector reader is invisible inside a 54-module `graph_repos` count."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            out.update(al.name for al in node.names)
    return out


def _repo_symbols(tree: ast.AST) -> set[str]:
    """Names this file pulls specifically out of `graph_repos` — the class-(d) input.

    Narrower than `_imported_symbols`, deliberately: that one returns every `from X import`
    name in the file, so a module importing `merge_entity` from a SERVICE layer would be
    scored as needing a port operation it does not need.

    ⚠️ A SUBMODULE import is resolved to the attributes actually USED, and that correction is
    worth more than it looks. `from app.db.graph_repos import maintenance` binds nine
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

    real = ast.parse("from app.db.graph_repos.entities import merge_entity\n")
    if not any(_CONCRETE in m for m in _imports(real)):
        print("  FAIL — a real `from … graph_repos …` import was not detected")
        ok = False

    prose = ast.parse('"""This used to call graph_repos.merge_entity directly."""\n')
    if any(_CONCRETE in m for m in _imports(prose)):
        print("  FAIL — a docstring mentioning graph_repos was counted as an import")
        ok = False

    comment = ast.parse("# migrated off graph_repos in T17\nx = 1\n")
    if any(_CONCRETE in m for m in _imports(comment)):
        print("  FAIL — a comment mentioning graph_repos was counted as an import")
        ok = False

    port = ast.parse("from app.ports.graph_store import GraphStore\n")
    if not any(m.endswith(".ports") or ".ports." in m for m in _imports(port)):
        print("  FAIL — a port import was not detected")
        ok = False

    # The symbol-level detector, same non-vacuity bar. A docstring that DISCUSSES the
    # migration must not count: `extraction/entity_embedder.py` and `ports/vector_store.py`
    # both name `find_entities_by_vector` in prose and neither is a bypass. Counting prose
    # would report 6 instead of 4 and bury the two real ones in noise.
    vreal = ast.parse("from app.db.graph_repos.entities import find_entities_by_vector" + chr(10))
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

    # ── T25/§9.2 — the backend-declaration scan, validated on cases it did not come from ──
    if scan_backend_declarations({"infra/.env": "KNOWLEDGE_GRAPH_BACKEND=neo4j\n"}) != [
            ("infra/.env", "neo4j")]:
        print("  FAIL — an explicit `neo4j` declaration was not reported; the check that "
              "guards §9.2's DDL-exit condition cannot see the thing it exists for")
        ok = False

    if scan_backend_declarations({"infra/.env": "KNOWLEDGE_GRAPH_BACKEND=age\n"}):
        print("  FAIL — an `age` declaration was reported as non-age; the check would be "
              "unsatisfiable and the ratchet meaningless")
        ok = False

    # The compose form declares by its DEFAULT — what a deployment setting nothing receives.
    compose_bad = "      KNOWLEDGE_GRAPH_BACKEND: ${KNOWLEDGE_GRAPH_BACKEND:-neo4j}" + chr(10)
    if scan_backend_declarations({"infra/docker-compose.yml": compose_bad}) != [
            ("infra/docker-compose.yml", "neo4j")]:
        print("  FAIL — a compose interpolation defaulting to `neo4j` was not reported. The "
              "variable is ABSENT in that deployment, so the default IS the declaration")
        ok = False

    compose_ok = "      KNOWLEDGE_GRAPH_BACKEND: ${KNOWLEDGE_GRAPH_BACKEND:-age}" + chr(10)
    if scan_backend_declarations({"infra/docker-compose.yml": compose_ok}):
        print("  FAIL — the real compose line (defaulting to `age`) was reported as non-age")
        ok = False

    # A file that never mentions it is not a declaration, and must not be invented as one.
    if scan_backend_declarations({"infra/other.yml": "SOME_OTHER_VAR: neo4j" + chr(10)}):
        print("  FAIL — a different variable whose VALUE is 'neo4j' was scored as a backend "
              "declaration")
        ok = False

    # ── A28 — the PARAMETER census, on cases it was not derived from (rule 3) ──
    _port = (chr(10).join([
        "class GraphStore(Protocol):",
        "    async def widget(self, *, user_id: str, colour: str, size: int = 1) -> None: ...",
    ]) + chr(10))

    # The method is CALLED and one parameter is never passed -> reported.
    suite_partial = 'await store.widget(user_id=u, colour="red")' + chr(10)
    total, missing = scan_port_params(_port, suite_partial)
    if (total, missing) != (2, ["widget.size"]):
        print(f"  FAIL — the param census misread a partially-exercised method: "
              f"{(total, missing)}")
        ok = False

    # Both passed -> nothing reported. Without this the check is satisfiable by reporting
    # everything, which is the same defect as reporting nothing.
    suite_full = 'await store.widget(user_id=u, colour="red", size=2)' + chr(10)
    if scan_port_params(_port, suite_full)[1]:
        print("  FAIL — a fully-exercised method was still reported")
        ok = False

    # A method the suite never CALLS belongs to the method ratchet, not this one — counting
    # it here would double-report every uncalled method and drown the parameters that matter.
    if scan_port_params(_port, "nothing here" + chr(10)) != (0, []):
        print("  FAIL — an UNCALLED method was counted by the parameter census")
        ok = False

    # `user_id`/`project_id` ride every call and must never be counted.
    if scan_port_params(_port, suite_full)[0] != 2:
        print("  FAIL — the ubiquitous identity parameters were counted")
        ok = False

    # Every recorded excuse must still describe something the census reports.
    _t, _m = scan_port_params()
    _stale = [q for q in _UNCONFORMABLE if q not in _m]
    if _stale:
        print(f"  FAIL — `_UNCONFORMABLE` names conformed parameter(s): {_stale}")
        ok = False

    # The MAX_CLASS_A ratchet, proven in CI rather than by hand. A hand-bite shows the check
    # can go red once; this shows it goes red for the reason claimed -- a module importing a
    # domain constant THROUGH the repo layer, which is the only way to re-enter class (a).
    regressed = classify({"svc/regress.py": {"STATUS_VALUES"}})
    n_a = len([k for k, v in regressed.items() if v[0] == CLASS_A])
    if not n_a > MAX_CLASS_A:
        print(f"  FAIL — a constant-only binder left class (a) at {n_a} against ceiling "
              f"{MAX_CLASS_A}; the ratchet cannot detect the regression it exists to stop")
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
    submod = ast.parse("from app.db.graph_repos import maintenance" + chr(10))
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
    # the same submodule must still count. §1.2 kept `count_nodes_by_label` in `graph_repos`
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
    src = ("from app.db.graph_repos import maintenance" + chr(10) +
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
    # is an accepted limit inside `graph_repos`, where a docstring naming `ON CREATE SET` is
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

    # A CYPHER `//` comment inside the string is prose too. Derived from `ON CREATE SET`
    # (T78 left three such notes behind); VALIDATED on `FOREACH` and `apoc.`, which the fix
    # was NOT derived from, so a strip that only handled the motivating construct fails here.
    commented = (
        'q = ' + chr(34)*3 + 
        '// this query no longer needs FOREACH or apoc.coll.union' + chr(10) +
        'MERGE (e:E) SET e.a = 1' + chr(34)*3 + chr(10)
    )
    # Through `scan_dialect` ITSELF, not through the regex. A selftest that calls
    # `_CYPHER_COMMENT.sub` directly passes even when nothing CALLS it: bite 7 removed the
    # strip from `scan_dialect`, the ceiling breached at 42/39, and the selftest still said
    # PASS. Injecting the fake at the chokepoint proves the chokepoint exists, not that it
    # is wired, so the probe module goes through the real scanner.
    if scan_dialect({"probe": commented}):
        print("  FAIL — `scan_dialect` counted a construct from a CYPHER comment; it would "
              "hold the ceiling above zero on a query whose branch is already GONE")
        ok = False
    # ...and the strip must not eat real Cypher that merely sits on the same line's right.
    trailing = "q = " + chr(34)*3 + "MERGE (e:E) SET e.at = datetime()  // stamp it" + chr(34)*3 + chr(10)
    if scan_dialect({"probe": trailing}).get("probe", {}).get("datetime()") != 1:
        print("  FAIL — the comment strip ate the statement it was trailing; the backlog "
              "would read lower than it is")
        ok = False

    # ── T89: the port-conformance scanner, driven on FIXTURES ────────────────────────
    # Injected rather than run against the repo, because a scanner checked only against a
    # tree that currently passes reports PASS for the tree's reason, not its own.
    _port = (
        "class GraphStore(Protocol):" + chr(10) +
        "    async def neighborhood(self): ..." + chr(10) +
        "    async def relations_for(self): ..." + chr(10) +
        "    async def _private(self): ..." + chr(10)
    )
    covered_suite = "await store.neighborhood(u)" + chr(10) + "await store.relations_for(u)"
    missing, total = scan_port_conformance(port=_port, suite=covered_suite)
    if missing or total != 2:
        print(f"  FAIL — the port scanner miscounted a fully-covered port: "
              f"missing={missing} total={total} (a leading-underscore method is not "
              f"port surface and must not be demanded)")
        ok = False
    # The case it exists for, and the one it was blind to in production: a method the
    # suite never calls.
    missing, _ = scan_port_conformance(
        port=_port, suite="await store.relations_for(u)")
    if missing != ["neighborhood"]:
        print(f"  FAIL — the port scanner did not SEE an unconformed method: {missing}")
        ok = False
    # A mention that is not a CALL is not coverage. Validated on a case the scanner was not
    # derived from: the real suite names methods in its prose constantly.
    missing, _ = scan_port_conformance(
        port=_port,
        suite="# store.neighborhood is covered elsewhere" + chr(10) +
              "await store.relations_for(u)")
    if missing != ["neighborhood"]:
        print(f"  FAIL — a method named only in a COMMENT counted as conformed: {missing}")
        ok = False

    # ── T91: the procedure scanner, on fixtures ──────────────────────────────────────
    # ⚠️ The FIRST cut of these two patterns shipped with a literal backspace (0x08) where
    # `\\b` was meant — a heredoc ate the escape. The regexes then matched
    # NOTHING, the new ratchet read 0/0, and it would have passed its own bite green. So the
    # first case here is not "does it find one" but "does it find the REAL construct", and
    # the pattern is asserted to carry a word boundary rather than whatever byte survived.
    for _name, _pat in _PROCEDURE_PATTERNS:
        if "\x08" in repr(_pat.pattern) or chr(8) in _pat.pattern:
            print(f"  FAIL — the {_name!r} pattern carries a literal backspace, not a word "
                  f"boundary. It will match nothing and the ceiling will read 0.")
            ok = False
    vec = 'Q = "CALL db.index.vector.queryNodes($i, $n, $v) YIELD node"' + chr(10)
    if scan_procedures({"probe": vec}).get("probe", {}).get("CALL db.*") != 1:
        print("  FAIL — the procedure scanner missed `CALL db.index.vector.queryNodes`, the "
              "construct it exists for")
        ok = False
    # ── A19 — the Neo4j-only GUARD check, validated on cases it was not derived from ──
    # The detector was built from three real leaks. Feeding it those three back would be
    # green by construction (rule 3), so every case below is synthetic and none of them is
    # one of the three.
    leak = (chr(10).join([
        "async def reads(session):",
        '    return await session.run("CALL db.index.vector.queryNodes($i, $n, $v)")',
    ]) + chr(10))
    un, stale = scan_neo4j_only_guards({"probe": leak})
    if un != ["probe.reads"]:
        print(f"  FAIL — an UNGUARDED Neo4j-only reader was not reported: {un}")
        ok = False

    guarded = (chr(10).join([
        "async def reads(session):",
        '    require_neo4j_only(session, "probe.reads", "vector index search")',
        '    return await session.run("CALL db.index.vector.queryNodes($i, $n, $v)")',
    ]) + chr(10))
    if scan_neo4j_only_guards({"probe": guarded})[0]:
        print("  FAIL — a GUARDED reader was still reported; the check cannot tell the cure "
              "from the disease and would be unsatisfiable")
        ok = False

    # The subtle one: the Cypher lives in a module-level CONSTANT, so a line-number rule
    # files it under "module" and the function looks clean. This is how A18's site hid.
    via_const = (chr(10).join([
        'Q = "CALL db.index.vector.queryNodes($i, $n, $v)"',
        "async def reads(session):",
        "    return await session.run(Q)",
    ]) + chr(10))
    if scan_neo4j_only_guards({"probe": via_const})[0] != ["probe.reads"]:
        print("  FAIL — a site reached through a module-level Cypher CONSTANT was not "
              "attributed to the function that uses it; that is exactly how one of the three "
              "leaks hid from the by-hand sweep")
        ok = False

    # A construct named only in a DOCSTRING is prose, not a call site.
    prose = (chr(10).join([
        "async def reads(session):",
        '    """Uses SHOW VECTOR INDEXES on Neo4j; AGE has no such command."""',
        "    return []",
    ]) + chr(10))
    if scan_neo4j_only_guards({"probe": prose})[0]:
        print("  FAIL — a docstring MENTIONING an admin command was scored as a call site")
        ok = False

    # An exemption naming something that no longer exists must be reported, not ignored.
    if not scan_neo4j_only_guards({"probe": "x = 1" + chr(10)})[1]:
        print("  FAIL — stale exemptions went unreported; an exemption for a deleted call "
              "site reads as a considered decision about code that is gone")
        ok = False

    # The two patterns A18 had to add by hand, proven to match real DDL.
    for _src, _fam in ((chr(10).join([
            "async def make(session):",
            '    await session.run("CREATE VECTOR INDEX ix IF NOT EXISTS FOR (p:P) ON (p.e)")',
        ]) + chr(10), "CREATE ... INDEX"),
        (chr(10).join([
            "async def kill(session):",
            '    await session.run("DROP INDEX ix IF EXISTS")',
        ]) + chr(10), "DROP INDEX")):
        if scan_procedures({"probe": _src}).get("probe", {}).get(_fam) != 1:
            print(f"  FAIL — the procedure scanner missed `{_fam}`, which the census read as "
                  f"6-of-9 until A18 widened it")
            ok = False

    show = 'Q = "SHOW VECTOR INDEXES YIELD name"' + chr(10)
    if scan_procedures({"probe": show}).get("probe", {}).get("SHOW ... INDEX") != 1:
        print("  FAIL — the procedure scanner missed `SHOW VECTOR INDEXES`")
        ok = False
    # Validated on cases it was NOT derived from — both are how the number would be held
    # above zero by prose that describes the removal.
    docstring = ('def f():' + chr(10) + '    """Uses `SHOW VECTOR INDEXES` (Neo4j 5+)."""'
                 + chr(10) + '    return 1' + chr(10))
    if scan_procedures({"probe": docstring}):
        print("  FAIL — a procedure named in a DOCSTRING was counted; the ceiling could "
              "never be closed by deleting code")
        ok = False
    commented = ('Q = ' + chr(34)*3 + '// no longer needs CALL db.index.vector.queryNodes'
                 + chr(10) + 'MATCH (e:E) RETURN e' + chr(34)*3 + chr(10))
    if scan_procedures({"probe": commented}):
        print("  FAIL — a procedure named in a CYPHER comment was counted")
        ok = False
    # A property access is not a procedure call. `self.db.execute(...)` must not count.
    if scan_procedures({"probe": 'x = "MATCH (n) RETURN n"' + chr(10) + 'self.db.execute(q)'}):
        print("  FAIL — `self.db.execute` counted as a Neo4j procedure call")
        ok = False

    # A30 — engine-named repo packages, and the SUBSTRING trap that would fake a violation
    if not scan_engine_named_repo_binders(
            {"x.py": "from app.db.neo4j_repos.entities import merge_entity" + chr(10)}):
        print("  FAIL — an `app.db.neo4j_repos` import was not detected")
        ok = False
    neutral = scan_engine_named_repo_binders(
        {"x.py": "from app.db.graph_repos.entities import merge_entity" + chr(10)})
    if neutral:
        print(f"  FAIL — the NEUTRAL package name was flagged: {neutral}")
        ok = False
    sub = scan_engine_named_repo_binders(
        {"x.py": "from app.db.storage_repos.blobs import put" + chr(10) +
                 "from app.db.message_repos.queue import pop" + chr(10)})
    if sub:
        print(f"  FAIL — a SUBSTRING match faked a violation ('age' inside 'storage'/'message'): {sub}")
        ok = False
    if not scan_engine_named_repo_binders({"x.py": "import app.db.kuzu_repos" + chr(10)}):
        print("  FAIL — a plain `import app.db.kuzu_repos` was not detected")
        ok = False
    if scan_engine_named_repo_binders(
            {"x.py": chr(34)*3 + "This used to import app.db.neo4j_repos.entities." + chr(34)*3 + chr(10)}):
        print("  FAIL — a DOCSTRING mentioning the old package was counted")
        ok = False

    # A30/T48: a cross-language PATH reference, which an import scan cannot see
    if not scan_engine_named_repo_paths(
            {"x.ts": "resolve('../services/knowledge-service/app/db/neo4j_repos/entities.py')"}):
        print("  FAIL — a TypeScript path into an engine-named repo package was not detected")
        ok = False
    if scan_engine_named_repo_paths(
            {"x.ts": "resolve('../services/knowledge-service/app/db/graph_repos/entities.py')"}):
        print("  FAIL — the NEUTRAL package path was flagged")
        ok = False
    if scan_engine_named_repo_paths({"x.ts": "const s = 'db/storage_repos/blobs.py'"}):
        print("  FAIL — a SUBSTRING match faked a path violation ('age' inside 'storage')")
        ok = False
    print(f"[port-adoption-gate] SELFTEST {'PASS' if ok else 'FAIL'} — distinguishes a real "
          f"import from a docstring, a PYTHON comment and a CYPHER comment, both ways; and "
          f"an unconformed port method from a covered one; and an ENGINE-NAMED repo "
          f"package from a neutral one, without a substring faking either")
    return 0 if ok else 1


# ── CLASS (d): THE POPULATION THAT ACTUALLY BLOCKS THE ENGINE SWAP ──────────────────────
#
# `MAX_CONCRETE_IMPORTERS` counts every module importing `graph_repos`, and §1.3 is right that
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
_REPO_DIR = os.path.join(SCAN_ROOT, "db", "graph_repos")
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

#: Class (a) is now EMPTY, and this pins it there. A module in (a) binds `graph_repos` for a
#: CONSTANT — a domain fact re-exported by the repo layer, which T17 A5/A6 moved to
#: `app/domain/` and then left every consumer importing through the old path. Seven modules
#: sat that way for nine days, counting as bound to the concrete layer for a tuple of
#: integers. Zero is the honest reading and a ceiling of zero is what keeps it: the next
#: `from app.db.graph_repos.X import SOME_CONSTANT` reopens the class and fails here.
MAX_CLASS_A = 0


def _symbol_home(path: str) -> dict[str, tuple[str, str]]:
    """Every top-level name `graph_repos` exports, as (kind, defining module).

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

    `graph_repos` re-exports them preserving class identity, so importing one is a stale import
    PATH, not a binding to Neo4j. Counting these as engine bindings overstates the work.
    """
    out: set[str] = set()
    for fname in _DOMAIN_FILES:
        out |= _names_in(os.path.join(SCAN_ROOT, "domain", fname))
    return out


def classify(concrete_symbols: dict[str, set[str]]) -> dict[str, tuple[str, list[str], list[str]]]:
    """Split the concrete binders into the classes §1.2 and §1.3 decided, by IMPORTED SYMBOL.

    A module is class (d) if ANY name it still takes from `graph_repos` is an operation the
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
# 85 operations against a port of 21 would make the port a mirror of `graph_repos` with a
# different import path, which its own law forbids ("grows by demand, not by inventory").
# Substitutability lands at two levels instead: the port stays the DOMAIN boundary, and the
# repo layer becomes ENGINE-AGNOSTIC.
#
# That second path needs a number, or it is a plan with no mechanism — the failure this file
# already records twice (the stale 28, the stale vector precondition). This is that number:
# the Neo4j-ONLY dialect sites left inside `graph_repos`.
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
_DIALECT_ROOT = os.path.join(SCAN_ROOT, "db", "graph_repos")
#: T91 — Neo4j SERVER-SIDE procedures and admin commands, counted SEPARATELY from the
#: dialect families above.
#:
#: 🔴 They were not counted at all, and the gate's headline said so wrongly. `scan_dialect`
#: knew `apoc.` but not `db.*`, so `CALL db.index.vector.queryNodes` — the whole of semantic
#: search — sat inside `graph_repos` while the gate printed *"0/0 — the repo layer is
#: ENGINE-AGNOSTIC"*. Measured against AGE 1.7.0 on 2026-08-22, all three shapes are hard
#: syntax errors, not degraded behaviour:
#:
#:     CALL db.index.vector.queryNodes     PostgresSyntaxError: syntax error at or near "."
#:     CALL db.index.fulltext.queryNodes   PostgresSyntaxError: syntax error at or near "."
#:     SHOW VECTOR INDEXES                 PostgresSyntaxError: syntax error at or near "SHOW"
#:
#: They are a SEPARATE number rather than added to `MAX_NEO4J_DIALECT_SITES` because they are
#: not a dialect backlog: there is no AGE equivalent to port them to. Every one is the vector
#: layer, which §3.1 moves to Postgres wholesale — `entities` (2), `passages` (2),
#: `vector_indexes` (2). Folding them into a backlog that means "rewrite this in portable
#: Cypher" would misdescribe the work; hiding them entirely is what was happening before.
#:
#: This is also the honest answer to "why are three repo functions unproven on AGE"
#: (T88): `find_entities_by_vector`, `set_entity_embedding` and `purge_project` reach one of
#: these. It is not a gap in the proof — it is a Neo4j-only capability with a scheduled exit.
#: 6, not the 8 a naive `grep` returns: one `SHOW VECTOR INDEXES` is in a DOCSTRING and one
#: `CALL db.index.vector.queryNodes` is in a PYTHON comment describing the migration. Both
#: are excluded by the same `_code_strings` + `//`-strip that T87 had to add twice, and
#: counting them would make the number un-closable by prose alone.
MAX_VECTOR_PROCEDURE_SITES = 9

_PROCEDURE_PATTERNS = (
    # `db.<anything>` as a CALL target. NOT a bare `db.` match: `self.db.execute` and a
    # docstring saying "the db.index one" must not count, which is why the CALL is required.
    ("CALL db.*", re.compile(r"\bCALL\s+db\.[a-zA-Z_.]+", re.I)),
    # Admin commands. Neo4j-only by definition; AGE rejects the keyword outright.
    ("SHOW ... INDEX", re.compile(r"\bSHOW\s+[A-Z ]*INDEX(ES)?\b", re.I)),
    # ⚠️ These two were MISSING while the comment above already claimed admin commands
    # were in scope, so the census read 6 when the real Neo4j-only surface was 9.
    # `CREATE VECTOR INDEX` and `DROP INDEX` are exactly as unportable as `SHOW`: AGE
    # rejects the keyword. Found by A18's by-hand sweep, which had to widen its own
    # regex to see three of its sites -- a census the gate should have been keeping.
    ("CREATE ... INDEX",
     re.compile(r"\bCREATE\s+(?:VECTOR|FULLTEXT|RANGE|TEXT|POINT)?\s*INDEX\b", re.I)),
    ("DROP INDEX", re.compile(r"\bDROP\s+INDEX\b", re.I)),
)


# ── A19: every Neo4j-only site is GUARDED or exempt WITH A REASON ────────────────────────
#
# A16/A17/A18 found three leaks BY HAND — repo functions reaching a Neo4j-only capability on
# a session that follows the configured backend, which since T54 defaults to AGE. Each one
# failed with a raw `PostgresSyntaxError` that a caller's `except Exception` turned into a
# false statement: "graph orphaned, re-sweep owed" for a graph that was not orphaned,
# `cjk_lexical: "unavailable"` for an engine that can never do it, and a WARNING with a stack
# trace on every Mode 3 request.
#
# Three found by hand is three found by luck. This derives the census instead.

#: Functions that reach a Neo4j-only capability and are NOT guarded — each with the reason a
#: backend-following session cannot reach them. A reason, not a name: "it is fine" is what the
#: hand sweep believed about all three leaks before it read the call sites.
_NEO4J_ONLY_EXEMPT = {
    "entities.find_entities_by_vector":
        "reached only through Neo4jVectorStore (+ benchmarks), which is engine-scoped by "
        "construction — the provider hands entity reads to PgVectorStore when the backend is "
        "AGE, so this body only ever sees a Bolt session",
    "passages.find_passages_by_vector":
        "same: Neo4jVectorStore + benchmark call sites only",
    "vector_indexes.ensure_passage_vector_index":
        "called only by benchmark/flat_knn_rawsearch.py and benchmark/vector_backend_bench.py, "
        "which pin Neo4j deliberately — class (c), out of port scope per §1.3c",
}

MAX_UNGUARDED_NEO4J_ONLY = 0


def scan_neo4j_only_guards(sources=None) -> tuple[list[str], list[str]]:
    """`(unguarded, stale_exemptions)` — which functions reach a Neo4j-only capability
    without refusing by name, and which exemptions no longer correspond to anything.

    Attribution is by AST, and a module-level Cypher CONSTANT is attributed to the functions
    that reference it — `query_summary_index`'s site lives in `_SUMMARY_QUERY_CYPHER`, so a
    line-number-only rule would file it under "module" and miss the leak entirely. That is
    exactly how A18's site hid from the by-hand pass until the constants were followed.
    """
    if sources is None:
        sources = {}
        if os.path.isdir(_DIALECT_ROOT):
            for fname in sorted(os.listdir(_DIALECT_ROOT)):
                if fname.endswith(".py"):
                    try:
                        sources[fname[:-3]] = open(
                            os.path.join(_DIALECT_ROOT, fname), encoding="utf-8",
                            errors="replace").read()
                    except OSError:
                        continue
    unguarded: list[str] = []
    seen: set[str] = set()
    for mod, src in sorted(sources.items()):
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue

        # Docstrings and bare string expressions are PROSE. Collected up front and excluded
        # by identity, because a function whose docstring explains "SHOW VECTOR INDEXES is
        # Neo4j-only" is documenting the rule, not breaking it. The selftest caught this
        # detector scoring exactly that as a call site.
        _prose = {id(n.value) for n in ast.walk(tree)
                  if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                  and isinstance(n.value.value, str)}

        def _hits(node) -> bool:
            """Does this subtree carry a Neo4j-only construct in a CODE string?"""
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Constant) and isinstance(sub.value, str)
                        and id(sub) not in _prose):
                    blob = _CYPHER_COMMENT.sub("", sub.value)
                    if any(pat.search(blob) for _n, pat in _PROCEDURE_PATTERNS):
                        return True
            return False

        # Module-level Cypher constants -> the functions that use them.
        const_owner: dict[str, bool] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and _hits(node.value):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        const_owner[tgt.id] = True

        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body_hits = _hits(fn)
            uses_const = any(isinstance(n, ast.Name) and n.id in const_owner
                             for n in ast.walk(fn))
            if not (body_hits or uses_const):
                continue
            qual = f"{mod}.{fn.name}"
            seen.add(qual)
            guarded = any(
                isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "require_neo4j_only" for n in ast.walk(fn))
            if not guarded and qual not in _NEO4J_ONLY_EXEMPT:
                unguarded.append(qual)
    stale = sorted(k for k in _NEO4J_ONLY_EXEMPT if k not in seen)
    return sorted(unguarded), stale


# ── T25 residue: §9.2's DDL-exit condition, made checkable ───────────────────────────────
#
# §9.2 decided the ENTITY vector DDL "stays until no deployment can take the Neo4j entity
# path", and called that "mechanical and already written down in `read_scopes`". It is
# mechanical — but nothing measured it, so the condition sat as prose and T25's residue could
# not be evaluated by anyone reading the plan.
#
# It reduces to configuration. `read_scopes` gives entity reads to Postgres only when an
# anchor-score resolver exists, and the provider supplies one ONLY when
# `configured_backend() == "age"`. So a deployment takes the Neo4j entity path exactly when
# its backend is not `age`. That is a property of the declarations in this repo, and it is
# derivable.

#: Where a deployment DECLARES its backend. Globs, not a hand-list: a new compose file or env
#: template must be scanned by existing on disk, not by someone remembering to add it here.
_BACKEND_DECL_GLOBS = ("infra/*.env", "infra/.env", "infra/.env.*", "infra/*.yml",
                       "infra/*.yaml", "docker-compose*.yml")

MAX_NON_AGE_BACKEND_DECLARATIONS = 0


def scan_backend_declarations(sources=None) -> list[tuple[str, str]]:
    """`(where, value)` for every declaration that is NOT `age`.

    A `${KNOWLEDGE_GRAPH_BACKEND:-age}` interpolation counts as its DEFAULT, because that is
    what a deployment setting nothing receives — the compose file is the declaration in that
    case, not the absent variable.
    """
    import glob as _glob

    if sources is None:
        sources = {}
        for pat in _BACKEND_DECL_GLOBS:
            for path in _glob.glob(os.path.join(ROOT, pat)):
                try:
                    sources[os.path.relpath(path, ROOT).replace(os.sep, "/")] = open(
                        path, encoding="utf-8", errors="replace").read()
                except OSError:
                    continue
    bad: list[tuple[str, str]] = []
    for where, text in sorted(sources.items()):
        for m in re.finditer(
                r"KNOWLEDGE_GRAPH_BACKEND\s*[:=]\s*[\"']?(?:\$\{KNOWLEDGE_GRAPH_BACKEND"
                r":-)?([A-Za-z0-9_]+)", text):
            value = m.group(1).strip().lower()
            if value != "age":
                bad.append((where, value))
    return bad


# ── A30: the repo layer's NAME, which §10.1 made a criterion and nothing measured ─────────
#
# §10.1 decided substitutability arrives when "the repo layer becomes ENGINE-AGNOSTIC", and
# named exactly two things binding it: "the Cypher dialect and the session type". Both read
# zero — the dialect since T63/T67, the session since A29 renamed `neo4j_session`. The same
# decision also said the ceiling "counts modules bound to a **Neo4j-named** package, and that
# count must still fall as the layer is renamed".
#
# A30 renamed it, so that count is zero. Nothing measured it, and a criterion a DECISION names
# and no gate reads is one that comes back silently — which is the failure the pinned-session
# ratchet caught in A29 by refusing to credit a counter that fell to 0.
_ENGINE_TOKENS = frozenset({"neo4j", "age", "kuzu", "bolt", "postgres", "pg", "cypher"})
MAX_ENGINE_NAMED_REPO_BINDERS = 0


def _names_an_engine(package: str) -> bool:
    """Whole SEGMENTS, never substrings.

    `age` is a substring of `stor(age)` and `mess(age)`, and `pg` of `pg`-anything; a naive
    `in` test would flag a hypothetical `storage_repos` and read as a violation that is really
    a spelling coincidence. This gate has been bitten by exactly that shape twice — T42a's
    `:7688` matching inside `:27688`, and T48's `TEST_VECTOR_DB_URL` inside `..._RENAMED`.
    """
    return any(seg in _ENGINE_TOKENS for seg in package.lower().split("_"))


def scan_engine_named_repo_binders(sources=None) -> list[tuple[str, str]]:
    """`(module, package)` for every import of an `app.db.<engine>_repos` package.

    Derived from the import graph rather than from `_CONCRETE`, deliberately: a gate that
    asserted its own constant would go green by being edited, which is not a measurement.
    """
    if sources is None:
        sources = {}
        for base in ("app", "tests"):
            root = os.path.join(ROOT, "services", "knowledge-service", base)
            for dirpath, _dirs, files in os.walk(root):
                for fn in files:
                    if not fn.endswith(".py"):
                        continue
                    full = os.path.join(dirpath, fn)
                    try:
                        sources[os.path.relpath(
                            full, os.path.join(ROOT, "services", "knowledge-service")
                        ).replace(os.sep, "/")] = open(
                            full, encoding="utf-8", errors="replace").read()
                    except OSError:
                        continue
    found: list[tuple[str, str]] = []
    for where, text in sorted(sources.items()):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.ImportFrom) and node.module:
                mods.append(node.module)
            elif isinstance(node, ast.Import):
                mods.extend(a.name for a in node.names)
            for mod in mods:
                m = re.match(r"^app\.db\.([A-Za-z0-9_]+_repos)\b", mod)
                if m and _names_an_engine(m.group(1)):
                    found.append((where, m.group(1)))
    return sorted(set(found))


#: Source trees a cross-language PATH reference can hide in. `neo4j_repos` survived the A30
#: rename in a TypeScript test that reads a Python file by path — my sweep filtered on
#: `--include=*.py --include=*.sh`, so it never looked at the language most likely to hold one.
_PATH_SCAN_GLOBS = ("frontend/src/**/*.ts", "frontend/src/**/*.tsx", "services/**/*.go",
                    ".github/workflows/*.yml", ".githooks/*")
#: The gate's OWN selftest fixtures must name the old package to prove the detector fires.
_PATH_SCAN_EXEMPT = {"scripts/port-adoption-gate.py"}
MAX_ENGINE_NAMED_REPO_PATHS = 0


def scan_engine_named_repo_paths(sources=None) -> list[tuple[str, str]]:
    """`(where, package)` for an `db/<engine>_repos/` PATH string outside Python imports.

    A rename verified by two full language suites still broke a cross-language lock, because a
    TypeScript test opened `services/knowledge-service/app/db/neo4j_repos/entities.py` to
    compare a server-side constant against the frontend's copy. No Python suite could see it and
    no import scan could either — it is a string, in another language, naming a path.
    """
    import glob as _glob

    if sources is None:
        sources = {}
        for pat in _PATH_SCAN_GLOBS:
            for path in _glob.glob(os.path.join(ROOT, pat), recursive=True):
                if not os.path.isfile(path):
                    continue
                rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
                if rel in _PATH_SCAN_EXEMPT:
                    continue
                try:
                    sources[rel] = open(path, encoding="utf-8", errors="replace").read()
                except OSError:
                    continue
    found: list[tuple[str, str]] = []
    for where, text in sorted(sources.items()):
        for m in re.finditer(r"db/([A-Za-z0-9_]+_repos)/", text):
            if _names_an_engine(m.group(1)):
                found.append((where, m.group(1)))
    return sorted(set(found))


# ── A28: the port's PARAMETERS, not just its methods ─────────────────────────────────────
#
# `port conformance 21/21 methods have a rule` counts METHODS. A24 established the gap that
# hides behind that number: the rules for `resolve_or_merge_entity` asserted id-stability,
# `source_types` accumulation and isolation, and stopped — so `version`, `auto_created`,
# `provenance` and `job_id` were unconformed against EVERY adapter, and the AGE writer had
# been discarding three of them. A25 turned the same question into a real bug on
# `relations_for(direction)`: a dead comparison returned every relation with its endpoints
# swapped, invisible because no rule ever passed the argument.
#
# So this counts what the METHOD count cannot: parameters no rule has ever passed.

_PORT_FILE = os.path.join(SCAN_ROOT, "ports", "graph_store.py")
_CONFORMANCE = os.path.join(
    SCAN_ROOT, "..", "tests", "integration", "db", "test_graph_store_conformance.py")

#: Never counted: the identity every call carries.
_UBIQUITOUS = {"self", "user_id", "project_id"}

#: Parameters the port ACCEPTS and cannot REPORT, each with the reason. §9.3 records the
#: decision; this is the enforceable half. They are not a backlog — no rule can ever assert
#: them through the port, so a ceiling that demanded zero would be unsatisfiable and the next
#: person would "fix" it by deleting the check.
_UNCONFORMABLE: dict[str, str] = {
    "resolve_or_merge_entity.provenance":
        "accumulates into `e.provenances`, which is NOT a field on the Entity model",
    "merge_fact.provenance":
        "same: written to the graph, absent from the Fact model",
    "add_evidence.quote":
        "`EvidenceWriteResult` carries only created/evidence_count/mention_count",
    "status_at_order.min_evidence":
        "filters status TRANSITIONS, and the port has no status WRITER — a rule cannot "
        "create the precondition it filters on (`set_status` is a fake-only helper)",
}

MAX_UNCONFORMED_PORT_PARAMS = 4


def scan_port_params(port_src: str | None = None, suite_src: str | None = None):
    """`(total, [qualified names never passed by a rule])` — both derived.

    A parameter counts as exercised when the suite writes `name=` anywhere. That is coarse on
    purpose: a stricter reading (the argument must appear in a call to THAT method) would make
    the number depend on how the suite factors its helpers, and a census whose value depends on
    test style is one nobody trusts.
    """
    if port_src is None:
        try:
            port_src = open(_PORT_FILE, encoding="utf-8", errors="replace").read()
        except OSError:
            return 0, []
    if suite_src is None:
        try:
            suite_src = open(_CONFORMANCE, encoding="utf-8", errors="replace").read()
        except OSError:
            return 0, []
    total, missing = 0, []
    try:
        tree = ast.parse(port_src)
    except SyntaxError:
        return 0, []
    for cls in tree.body:
        if not isinstance(cls, ast.ClassDef):
            continue
        for m in cls.body:
            if not isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if f"store.{m.name}(" not in suite_src:
                continue          # an uncalled method is the METHOD ratchet's business
            params = [a.arg for a in list(m.args.args) + list(m.args.kwonlyargs)
                      if a.arg not in _UBIQUITOUS]
            total += len(params)
            for p in params:
                if not re.search(r"\b" + re.escape(p) + r"\s*=", suite_src):
                    missing.append(f"{m.name}.{p}")
    return total, sorted(missing)


def scan_procedures(sources=None) -> dict:
    """`{module: {family: count}}` for Neo4j server-side procedures and admin commands.

    Shares `_CYPHER_COMMENT` stripping with `scan_dialect` for the same reason: a construct
    named in a comment describing its own removal must not hold the number up.
    """
    return _scan_families(_PROCEDURE_PATTERNS, sources)


_DIALECT_PATTERNS = (
    ("ON CREATE SET", re.compile(r"ON\s+CREATE\s+SET", re.I)),
    ("ON MATCH SET", re.compile(r"ON\s+MATCH\s+SET", re.I)),
    ("datetime()", re.compile(r"\bdatetime\s*\(\s*\)")),
    ("CALL { }", re.compile(r"CALL\s*\{")),
    ("FOREACH", re.compile(r"\bFOREACH\s*\(")),
    # T79 — `duration(` was never in this list, so `datetime() - duration({hours: $h})`
    # counted as ONE construct when it is two. It is the only temporal builder besides
    # `datetime()` that appeared in the layer, and unlike `datetime()` it has no {NOW}-style
    # cure: the value it builds is compared and discarded, never stored, so there is no type
    # to preserve. The cutoff is computed in Python and bound instead.
    ("duration(", re.compile(r"\bduration\s*\(")),
    # T87 — two more Neo4j-only families the scan did not look for until a live AGE run found
    # them, exactly as `duration(` was missed until T79:
    #   * a PATTERN comprehension `[(a)-[r]->(b) WHERE … | expr]` — AGE rejects it outright;
    #     the portable form is an OPTIONAL MATCH plus an aggregation.
    #   * the list PREDICATES `any/all/none/single(x IN xs WHERE p)` — the portable form is
    #     `size([x IN xs WHERE p]) > 0`, which is a LIST comprehension and does parse.
    ("pattern comprehension", re.compile(r"\[\s*\(")),
    ("any/all/none/single", re.compile(
        r"\b(any|all|none|single)\s*\([^)]*\bIN\b[^)]*\bWHERE\b", re.I)),
    ("apoc.", re.compile(r"\bapoc\.")),
)

#: Shrink-only, like every other number here. 161 measured 2026-08-22 (T62), the first time
#: this backlog was counted rather than estimated. The 2026-08-11 probe predicted "~33
#: anchoring rewrites + 157 renames + 14 CALL{}"; measured inside the repo layer it is 37
#: anchoring, 106 renames, 14 CALL{}, plus 3 FOREACH and 1 apoc the probe did not look for.
#:
#: **The `ON CREATE SET` / `ON MATCH SET` class is CLOSED at 39** (T78). All 37 anchoring
#: branches are gone.
#:
#: **`datetime()` is CLOSED at 14** (T79) — 25 renamed to `{NOW}`, plus the one `duration(`
#: this list did not even scan for.
#:
#: **`FOREACH` is CLOSED at 11** (T80). The 2026-08-11 probe never looked at it, so its AGE
#: form was asserted rather than measured — and the measurement, when it was finally taken,
#: found the OCC gate the construct implemented was not atomic on NEO4J either. The last
#: class is 11 `CALL {}`, which the probe DID measure (`LATERAL`/CTE).
#:
#: **ZERO as of T82.** Every Neo4j-only construct in `graph_repos` is gone: 37 anchoring
#: branches, 25 `datetime()`, 1 `duration(`, 3 `FOREACH` and 14 `CALL {}`. The ceiling stays
#: here as a RATCHET — its job now is to refuse the next one, not to record a backlog. A
#: non-zero reading is a regression, not progress in the wrong direction.
MAX_NEO4J_DIALECT_SITES = 0


#: Engine names written as a string LITERAL inside the repo layer. Zero as of T83.
#:
#: 🔴 This ratchet exists because the dialect one reached zero WITHOUT the layer becoming
#: engine-agnostic. `MAX_NEO4J_DIALECT_SITES` counts Neo4j-only CONSTRUCTS; it cannot see
#: `render(TEMPLATE, "neo4j")`, and there were **51 of those across 11 modules** when the
#: dialect number first read 0. Running a real repo function against AGE failed immediately on
#: `function datetime does not exist`: the templates were portable and the RENDERING was pinned.
#:
#: The engine now comes from the session (`neo4j_helpers.engine_of`). A literal here puts the
#: pin back, in one line, without moving the dialect number at all — which is exactly the shape
#: of defect §1.3 records about this gate's own ceiling.
MAX_ENGINE_LITERALS = 0

#: `"neo4j"`/`"age"` as a quoted literal. Matched in CODE STRINGS' surroundings rather than in
#: the strings themselves: the name appears legitimately INSIDE Cypher (a `:Neo4j` label would
#: be absurd, but a comment naming the engine is normal), so the scan runs over source lines
#: with comments removed instead of over `_code_strings`.
_ENGINE_LITERAL = re.compile("(?P<q>['\"])(neo4j|age)(?P=q)")


#: `graph_session(engine="neo4j")` — call sites PINNED to one engine. Shrink-only.
#:
#: T54's blocker was that `graph_session()` could only return a Bolt session, so flipping
#: `KNOWLEDGE_GRAPH_BACKEND` put the 19 `GraphStore` adopters on AGE and the 54 `graph_repos`
#: binders on Neo4j — one conceptual graph, two stores, one empty, inside one service (T54b,
#: measured on dev and reverted). Since T83/T84 the repo layer runs on either engine and the
#: session follows the configured backend, so the split is closed by construction.
#:
#: What remains PINNED is the class §1.3 puts out of port scope forever: the benchmarks, which
#: exist to COMPARE engines and therefore must name one, and the one-shot migration scripts,
#: which ran against a known engine. 9 call sites across 7 modules, measured 2026-08-22. This
#: number is not aiming at zero — it is aiming at "no SERVICE code names an engine", and it
#: rises only if someone pins a call site that should have followed the configuration.
MAX_PINNED_SESSIONS = 9

_PINNED_SESSION = re.compile(r"""graph_session\(\s*engine\s*=""")


def scan_pinned_sessions() -> dict[str, int]:
    """`{module: count}` for call sites that pin their engine instead of following config."""
    out: dict[str, int] = {}
    root = os.path.join(SCAN_ROOT)
    if not os.path.isdir(root):
        return out
    for dirpath, _dirs, files in os.walk(root):
        for fname in sorted(files):
            if not fname.endswith(".py"):
                continue
            path = os.path.join(dirpath, fname)
            try:
                src = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            n = len(_PINNED_SESSION.findall(src))
            if n:
                out[os.path.relpath(path, SCAN_ROOT).replace(os.sep, "/")] = n
    return out


def scan_engine_literals() -> dict[str, list[str]]:
    """`{module: [offending source lines]}` for engine names hardcoded in the repo layer."""
    out: dict[str, list[str]] = {}
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
        hits = []
        for lineno, line in enumerate(src.splitlines(), 1):
            code = _CYPHER_COMMENT.sub("", line.split("#", 1)[0])
            if _ENGINE_LITERAL.search(code):
                hits.append(f"{lineno}: {line.strip()[:100]}")
        if hits:
            out[fname[:-3]] = hits
    return out


#: Repo functions PROVEN to run on AGE, derived from the committed proof rather than declared.
#: Floor — it may only rise.
#:
#: 🔴 **This exists because class (d)'s printed claim went false.** That number was labelled
#: *"AGE cannot be the only engine until 0"*, which was true while `graph_repos` could only run
#: on Neo4j: a module binding it was pinned to one engine. Since T83/T84 the layer runs on
#: either, and since T54c `graph_session()` follows the configured backend — so a class (d)
#: module is no longer engine-pinned. Class (d) still measures something real (port-adoption
#: debt: operations the port does not have), but it stopped measuring engine readiness, and a
#: number carrying a claim it no longer supports is worse than no number.
#:
#: What DOES track engine readiness is coverage: how much of the repo layer has been RUN
#: against AGE. 21 -> 50 -> 104 -> 116 across waves 3-5, and the ratchet is what
#: made the rise visible — it FAILED on the increase and demanded the floor move in the
#: same commit, which is rule 5 working rather than being remembered. 116 -> 117 at T91,
#: which the ratchet again refused to let land without this line moving.
#:
#: The remaining 2 are `find_entities_by_vector` and `purge_project`, and both are accounted
#: for by `MAX_VECTOR_PROCEDURE_SITES` — they reach a Neo4j-only procedure. T88 named THREE
#: and grouped `set_entity_embedding` with them as "the vector layer"; it reaches no
#: procedure at all, and running it (T91) showed it writes and enforces tenancy on AGE
#: unchanged. Adjacency to the vector layer was doing the work that a measurement should
#: have.
MIN_AGE_PROVEN_FUNCTIONS = 118

_AGE_PROOF = os.path.join(
    SCAN_ROOT, "..", "tests", "integration", "db", "test_repo_layer_runs_on_age.py",
)


#: T89 — port methods with NO rule in the adapter-parameterised conformance suite.
#:
#: The suite runs every rule against four adapters, which reads as thorough and says nothing
#: about the methods no rule ever calls. It stood at 19 of 21 while `neighborhood` was
#: unable to return at all on AGE: it raised `ValidationError` on EVERY call, and a live
#: `/internal/knowledge/wiki-neighborhood` request was the first thing to ever invoke it.
#:
#: Both sides are DERIVED — the port's methods from the Protocol, the covered set from the
#: suite's own `store.<method>(` calls. A hand-kept list of "methods we test" is the artifact
#: that was already wrong; this is the same cure as the KAL guard and the adapter set.
MAX_UNCONFORMED_PORT_METHODS = 0

_PORT = os.path.join(SCAN_ROOT, "ports", "graph_store.py")
_CONFORMANCE = os.path.join(
    SCAN_ROOT, "..", "tests", "integration", "db", "test_graph_store_conformance.py",
)


def scan_port_conformance(port=None, suite=None) -> tuple[list[str], int]:
    """`(uncovered_method_names, total_port_methods)`, both derived from source.

    `port`/`suite` are injectable so the selftest drives it with fixtures rather than with
    the repository's own files — a gate validated only against the tree it lives in is green
    by construction the moment that tree is correct.
    """
    try:
        ptree = ast.parse(
            open(_PORT, encoding="utf-8", errors="replace").read() if port is None else port)
    except (OSError, SyntaxError):
        return [], 0
    methods: list[str] = []
    for cls in ptree.body:
        if not isinstance(cls, ast.ClassDef):
            continue
        for n in cls.body:
            if (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and not n.name.startswith("_")):
                methods.append(n.name)
    try:
        text = (open(_CONFORMANCE, encoding="utf-8", errors="replace").read()
                if suite is None else suite)
    except OSError:
        return methods, len(methods)
    # `store.<name>(` is the suite's single idiom for reaching the adapter under test. A
    # mention in a comment or a docstring does not count as coverage, so the paren is
    # required rather than a bare name match.
    covered = set(re.findall(r"store\.([a-z_]+)\(", text))
    return [m for m in methods if m not in covered], len(methods)


def scan_age_proven() -> tuple[set[str], int]:
    """`({module.function}, total public repo functions)` — both derived, neither listed.

    ⚠️ Counts DISTINCT functions, not invocations. The proof file's own
    `_PROVEN_ON_AGE = 25` counts CALLS — `merge_entity` runs three times in it — and reading
    that as "25 functions" overstates coverage by four. It was written that way in T84's
    evidence and is corrected here.
    """
    proven: set[str] = set()
    try:
        tree = ast.parse(open(_AGE_PROOF, encoding="utf-8", errors="replace").read())
    except (OSError, SyntaxError):
        return proven, 0
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.db.graph_repos":
            for a in node.names:
                aliases[a.asname or a.name] = a.name
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in aliases):
            proven.add(f"{aliases[node.func.value.id]}.{node.func.attr}")

    # ⚠️ The denominator is ENGINE-TOUCHING functions in LIVE modules, not every public
    # function. 152 counted things that cannot fail on an engine and things that are being
    # deleted: 25 in `passages`/`vector_indexes` (§3.1 moves the vector layer to Postgres) and
    # 7 pure helpers with no session at all — `fact_id`, `days_since_epoch`, `event_id`. A
    # coverage percentage over those is a percentage of the wrong thing, and it read 13% when
    # the honest figure was higher. 119, measured 2026-08-22 (T88).
    total = 0
    if os.path.isdir(_REPO_DIR):
        for fname in sorted(os.listdir(_REPO_DIR)):
            if not fname.endswith(".py") or fname == "__init__.py":
                continue
            if fname[:-3] in _DELETED_MODULES:
                continue
            try:
                mod = ast.parse(open(os.path.join(_REPO_DIR, fname),
                                     encoding="utf-8", errors="replace").read())
            except (OSError, SyntaxError):
                continue
            for n in mod.body:
                if not isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)):
                    continue
                if n.name.startswith("_"):
                    continue
                args = [a.arg for a in n.args.args] + [a.arg for a in n.args.kwonlyargs]
                if "session" in args or "tx" in args:
                    total += 1
    return proven, total



def _code_strings(src: str) -> str:
    """Every string literal in the module that is NOT a docstring, joined.

    ⚠️ The first cut of this detector matched the RAW FILE TEXT, and it over-counted by 10:
    a docstring naming `ON CREATE SET` was scored as Cypher, and the single `apoc.` hit in the
    whole layer turned out to be a COMMENT — there is no APOC dependency left in `graph_repos`
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


#: A Cypher line comment. Stripped before the dialect scan so that DOCUMENTING a
#: construct — including documenting its removal — never counts as using it.
_CYPHER_COMMENT = re.compile(r"//[^\n]*")


def scan_dialect(sources: dict[str, str] | None = None) -> dict[str, dict[str, int]]:
    """Neo4j-only Cypher constructs per repo module, counted in CODE STRINGS only.

    The constructs live inside triple-quoted Cypher strings, so the match itself is textual —
    but it runs over `_code_strings`, not the raw file, so a docstring describing the
    migration is not counted as the migration being incomplete.

    ⚠️ `_code_strings` stops at the PYTHON layer, and that was not far enough. A Cypher `//`
    comment lives INSIDE the string literal, so a note explaining why a query no longer needs
    `ON CREATE SET` was scored as the query still having one. Measured 2026-08-22: 3 of the
    remaining 42 sites were such comments, and the entire `ON CREATE SET` / `ON MATCH SET`
    class read as 3 outstanding when it was actually **zero**. Same defect as the docstring
    one, one level down — the ceiling's target is zero, and prose can never reach zero, so
    the cure for a construct would have held the number above the floor forever.

    Cypher line comments are stripped before matching. No `//` appears inside a string
    literal anywhere in the layer (checked the same day), so this cannot eat real syntax."""
    return _scan_families(_DIALECT_PATTERNS, sources)


def _scan_families(patterns, sources=None) -> dict[str, dict[str, int]]:
    """The shared body of `scan_dialect` and `scan_procedures`.

    Extracted rather than copied: the docstring/`//`-comment stripping above took two
    separate corrections to get right, and a second hand-copied loop would have inherited
    whichever version existed the day it was written and then drifted from it silently.
    """
    out: dict[str, dict[str, int]] = {}
    if sources is None:
        if not os.path.isdir(_DIALECT_ROOT):
            return out
        sources = {}
        for fname in sorted(os.listdir(_DIALECT_ROOT)):
            if not fname.endswith(".py"):
                continue
            try:
                sources[fname[:-3]] = open(
                    os.path.join(_DIALECT_ROOT, fname), encoding="utf-8", errors="replace",
                ).read()
            except OSError:
                continue
    for mod, src in sorted(sources.items()):
        blob = _CYPHER_COMMENT.sub("", _code_strings(src))
        hits = {name: len(pat.findall(blob)) for name, pat in patterns}
        hits = {k: v for k, v in hits.items() if v}
        if hits:
            out[mod] = hits
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
        print("  importing `graph_repos` breaks when the engine changes even if it contains")
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
    class_a = sorted(k for k, v in classes.items() if v[0] == CLASS_A)
    if len(class_a) > MAX_CLASS_A:
        print(f"{chr(10)}[port-adoption-gate] FAIL — class (a) GREW to {len(class_a)} "
              f"(ceiling {MAX_CLASS_A}): {sorted(class_a)}{chr(10)}")
        print("  A module is binding `graph_repos` for a CONSTANT. The constant has a home")
        print("  in app/domain/ — import it from there. Nothing about a tuple of integers")
        print("  needs the concrete layer, and this is the cheapest class to keep at zero.")
        return 1
    print(f"[port-adoption-gate] class (a) {len(class_a)}/{MAX_CLASS_A} — no module binds "
          f"the concrete layer for a constant; every domain fact is imported from its home")
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
    # ⚠️ The claim on this line USED to be "AGE cannot be the only engine until 0". It was
    # true while `graph_repos` ran only on Neo4j; since T83/T84 it runs on either and since
    # T54c the session follows the configured backend, so a class (d) module is not
    # engine-pinned. The number still measures port-adoption debt — it stopped measuring
    # engine readiness, and the coverage line below is what replaced it.
    print(f"[port-adoption-gate] class (d) {len(class_d)}/{MAX_CLASS_D} — modules needing "
          f"a port operation that does not exist (port-adoption debt; NOT an engine "
          f"blocker since T54c)")
    proven, total_fns = scan_age_proven()
    if len(proven) != MIN_AGE_PROVEN_FUNCTIONS:
        verb = "ROSE to" if len(proven) > MIN_AGE_PROVEN_FUNCTIONS else "fell to"
        print(f"{chr(10)}[port-adoption-gate] FAIL — repo functions proven on AGE {verb} "
              f"{len(proven)} (floor {MIN_AGE_PROVEN_FUNCTIONS}).{chr(10)}"
              f"  Coverage is what tracks engine readiness now that the layer is "
              f"engine-agnostic.{chr(10)}  Raise the floor when it rises; a function that "
              f"stops being proven is a regression{chr(10)}  in the claim, not a smaller "
              f"test.{chr(10)}")
        return 1
    pct = (100 * len(proven) // total_fns) if total_fns else 0
    print(f"[port-adoption-gate] AGE coverage {len(proven)}/{total_fns} repo functions "
          f"({pct}%) proven on AGE, floor {MIN_AGE_PROVEN_FUNCTIONS} — DISTINCT functions, "
          f"not invocations")

    unconformed, port_total = scan_port_conformance()
    if len(unconformed) > MAX_UNCONFORMED_PORT_METHODS:
        print(f"{chr(10)}[port-adoption-gate] FAIL — {len(unconformed)} port method(s) have "
              f"NO rule in the conformance suite (ceiling {MAX_UNCONFORMED_PORT_METHODS}):"
              f"{chr(10)}  " + ", ".join(unconformed) + chr(10) +
              f"  A method no rule calls is unconformed against EVERY adapter at once. "
              f"`neighborhood`{chr(10)}  sat here while it raised on every AGE call, and a "
              f"live 500 was what found it.{chr(10)}")
        return 1
    print(f"[port-adoption-gate] port conformance {port_total - len(unconformed)}/"
          f"{port_total} methods have a rule (ceiling {MAX_UNCONFORMED_PORT_METHODS} "
          f"unconformed)")
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
        print("  added inside `graph_repos`. Spec §10.1 makes the repo layer ENGINE-AGNOSTIC;")
        print("  every one of these has a measured AGE equivalent (2026-08-11 probe, T57-T59).")
        print("  Run --dialect to see where.")
        return 1
    if dsites < MAX_NEO4J_DIALECT_SITES:
        print(f"{chr(10)}[port-adoption-gate] FAIL — dialect IMPROVED to {dsites} but the "
              f"ceiling still says {MAX_NEO4J_DIALECT_SITES}.{chr(10)}")
        print("  Lower it in the same commit (rule 5). This is the SECOND path to class (d)")
        print("  zero and the one §10.1 chose; a stale ceiling is how the first one sat at 28.")
        return 1
    if MAX_NEO4J_DIALECT_SITES == 0:
        # The line above prints one of two very different facts and they must not read alike.
        # A backlog at its ceiling is progress; a CLOSED class is a ratchet whose only
        # remaining job is to refuse the next one. "It can only fall" is false at zero.
        print("[port-adoption-gate] Neo4j-only dialect 0/0 — every PORTABLE construct is gone "
              "from the repo layer (§10.1). A RATCHET: any reading above zero is a "
              "regression.")
    else:
        print(f"[port-adoption-gate] Neo4j-only dialect {dsites}/{MAX_NEO4J_DIALECT_SITES} in "
              f"the repo layer — §10.1's second path to class (d) zero")
    # ── A28: the port's PARAMETERS, not just its methods ───────────────────────────────
    n_params, unconformed = scan_port_params()
    unexplained = [q for q in unconformed if q not in _UNCONFORMABLE]
    if unexplained:
        print(f"{chr(10)}[port-adoption-gate] FAIL — {len(unexplained)} port parameter(s) no "
              f"conformance rule passes, and no reason recorded: {unexplained}{chr(10)}")
        print("  A parameter no rule exercises is unconformed against EVERY adapter. A24 found")
        print("  three discarded by the AGE writer that way; A25 found a dead comparison that")
        print("  returned every relation with its endpoints SWAPPED. Add a rule, or add the")
        print("  parameter to `_UNCONFORMABLE` with the reason it cannot be asserted.")
        return 1
    stale_reasons = [q for q in _UNCONFORMABLE if q not in unconformed]
    if stale_reasons:
        print(f"{chr(10)}[port-adoption-gate] FAIL — {len(stale_reasons)} `_UNCONFORMABLE` "
              f"entr(y/ies) name a parameter that IS now conformed: {stale_reasons}{chr(10)}")
        print("  Remove the entry. A recorded excuse for something already fixed reads as a")
        print("  live limitation and is how a settled question comes back.")
        return 1
    if len(unconformed) > MAX_UNCONFORMED_PORT_PARAMS:
        print(f"{chr(10)}[port-adoption-gate] FAIL — unconformed port parameters ROSE to "
              f"{len(unconformed)} (ceiling {MAX_UNCONFORMED_PORT_PARAMS}){chr(10)}")
        return 1
    if len(unconformed) < MAX_UNCONFORMED_PORT_PARAMS:
        print(f"{chr(10)}[port-adoption-gate] FAIL — unconformed port parameters IMPROVED to "
              f"{len(unconformed)}; lower the ceiling in the same commit (rule 5){chr(10)}")
        return 1
    print(f"[port-adoption-gate] port parameters {len(unconformed)}/{n_params} unconformed "
          f"(ceiling {MAX_UNCONFORMED_PORT_PARAMS}) — every one is STRUCTURALLY unassertable "
          f"through the port and carries its reason (§9.3); the method count cannot see this")

    # ── T25 residue: §9.2's DDL-exit condition, as a number ────────────────────────────
    non_age = scan_backend_declarations()
    if len(non_age) > MAX_NON_AGE_BACKEND_DECLARATIONS:
        print(f"{chr(10)}[port-adoption-gate] FAIL — {len(non_age)} deployment declaration(s) "
              f"select a backend other than `age`: {non_age}{chr(10)}")
        print("  §9.2 keeps the ENTITY vector DDL until no deployment can take the Neo4j")
        print("  entity path, and this is that condition. A non-`age` backend gets no")
        print("  anchor-score resolver, so `read_scopes` drops `entity` from the primary and")
        print("  entity reads fall to Neo4jVectorStore -> `entity_embeddings_*`. T25t measured")
        print("  the consequence of deleting the DDL under exactly that config: 52U00 /")
        print("  ProcedureCallFailed. Either keep the declaration and keep the DDL, or move")
        print("  the deployment to `age`.")
        return 1
    print(f"[port-adoption-gate] backend declarations {len(non_age)}/"
          f"{MAX_NON_AGE_BACKEND_DECLARATIONS} non-`age` — §9.2's DDL-exit condition holds for "
          f"every DECLARED deployment; `neo4j` stays SELECTABLE for the T43 harness and the "
          f"two benchmarks, which are declared evaluation-only")

    # ── A30: §10.1's OTHER criterion — the repo layer's NAME ──────────────────────────
    engine_named = scan_engine_named_repo_binders()
    if len(engine_named) > MAX_ENGINE_NAMED_REPO_BINDERS:
        print(f"{chr(10)}[port-adoption-gate] FAIL — {len(engine_named)} module(s) bind an "
              f"ENGINE-NAMED repo package (ceiling {MAX_ENGINE_NAMED_REPO_BINDERS}):")
        for where, pkg in engine_named[:10]:
            print(f"    {where}  ->  app.db.{pkg}")
        print("  §10.1: the repo layer is engine-agnostic in its SEMANTICS, so naming it for one")
        print("  engine is what made 54 modules read as bound to Neo4j. A29 took the last such")
        print("  name off the session, A30 off the package. Do not reintroduce one.")
        return 1
    print(f"[port-adoption-gate] engine-named repo binders {len(engine_named)}/"
          f"{MAX_ENGINE_NAMED_REPO_BINDERS} — §10.1's second criterion, and a RATCHET: the repo "
          f"layer names no engine, so the 54 above bind a NEUTRAL package")

    paths = scan_engine_named_repo_paths()
    if len(paths) > MAX_ENGINE_NAMED_REPO_PATHS:
        print(f"{chr(10)}[port-adoption-gate] FAIL — {len(paths)} cross-language PATH "
              f"reference(s) to an engine-named repo package (ceiling "
              f"{MAX_ENGINE_NAMED_REPO_PATHS}):")
        for where, pkg in paths[:10]:
            print(f"    {where}  ->  db/{pkg}/")
        print("  A rename verified by two full language suites still broke a cross-language")
        print("  lock this way: a TypeScript test opened a Python file BY PATH. An import scan")
        print("  cannot see a string in another language.")
        return 1
    print(f"[port-adoption-gate] engine-named repo PATHS {len(paths)}/"
          f"{MAX_ENGINE_NAMED_REPO_PATHS} — no cross-language reference to a renamed package")
    # ── A19: those sites must REFUSE by name, not leak a SQL parse error ───────────────
    unguarded, stale_exempt = scan_neo4j_only_guards()
    if stale_exempt:
        print(f"{chr(10)}[port-adoption-gate] FAIL — {len(stale_exempt)} Neo4j-only exemption(s) "
              f"name nothing that exists: {stale_exempt}{chr(10)}")
        print("  A stale exemption is worse than none: it reads as a considered decision about")
        print("  a call site that has since moved or been deleted. Remove it in the same commit.")
        return 1
    if len(unguarded) > MAX_UNGUARDED_NEO4J_ONLY:
        print(f"{chr(10)}[port-adoption-gate] FAIL — {len(unguarded)} function(s) reach a "
              f"Neo4j-only capability without refusing by name: {unguarded}{chr(10)}")
        print("  Since T54 the default backend is AGE and `graph_session()` follows it, so a")
        print("  raw `PostgresSyntaxError` from here reaches a caller's `except Exception` and")
        print("  becomes a FALSE statement — A16 reported a graph orphaned that was not, A17")
        print("  reported a permanent gap as an outage, A18 logged a traceback every request.")
        print("  Call `require_neo4j_only(session, operation, capability)` (rule 9), or add an")
        print("  entry to `_NEO4J_ONLY_EXEMPT` saying WHY a backend-following session cannot")
        print("  reach it. A name with no reason is what made all three leaks invisible.")
        return 1
    print(f"[port-adoption-gate] Neo4j-only guards {len(unguarded)}/{MAX_UNGUARDED_NEO4J_ONLY} "
          f"unguarded — every site refuses by name or is exempt with a reason "
          f"({len(_NEO4J_ONLY_EXEMPT)} exempt)")

    # ── Neo4j server-side procedures, counted apart from the dialect backlog ────────────
    procs = scan_procedures()
    n_proc = sum(sum(v.values()) for v in procs.values())
    detail = "; ".join(
        f"{mod} {sum(h.values())}" for mod, h in sorted(procs.items())) or "none"
    if n_proc > MAX_VECTOR_PROCEDURE_SITES:
        print(f"{chr(10)}[port-adoption-gate] FAIL — Neo4j server-side procedure sites GREW "
              f"to {n_proc} (ceiling {MAX_VECTOR_PROCEDURE_SITES}): {detail}.{chr(10)}"
              f"  `CALL db.*` and `SHOW … INDEX` are hard syntax errors on AGE and have no "
              f"portable equivalent.{chr(10)}  A NEW one is a new Neo4j-only capability in "
              f"the repo layer, which §10.1 forbids.{chr(10)}")
        return 1
    if n_proc < MAX_VECTOR_PROCEDURE_SITES:
        print(f"{chr(10)}[port-adoption-gate] FAIL — procedure sites FELL to {n_proc} "
              f"(ceiling {MAX_VECTOR_PROCEDURE_SITES}). Lower the ceiling in this commit "
              f"(rule 5).{chr(10)}")
        return 1
    print(f"[port-adoption-gate] Neo4j procedures {n_proc}/{MAX_VECTOR_PROCEDURE_SITES} — "
          f"the VECTOR layer plus ONE fulltext reader ({detail}); §3.1 moves them to Postgres. "
          f"These sites are "
          f"why `find_entities_by_vector` is unproven on AGE: a "
          f"Neo4j-only capability, not a gap in the proof. NOT `set_entity_embedding`, "
          f"which reaches no procedure and was proven at T91.")

    literals = scan_engine_literals()
    n_lit = sum(len(v) for v in literals.values())
    if n_lit > MAX_ENGINE_LITERALS:
        print(f"{chr(10)}[port-adoption-gate] FAIL — {n_lit} hardcoded engine name(s) in the "
              f"repo layer (ceiling {MAX_ENGINE_LITERALS}).{chr(10)}")
        for mod, hits in literals.items():
            for h in hits:
                print(f"    {mod}.py:{h}")
        print(f"{chr(10)}  The engine belongs to the SESSION — `run_read`/`run_write` render "
              f"with{chr(10)}  `engine_of(session)`. A literal here pins the layer to one "
              f"engine while the{chr(10)}  dialect count still reads zero (T83).{chr(10)}")
        return 1
    if n_lit < MAX_ENGINE_LITERALS:
        print(f"{chr(10)}[port-adoption-gate] FAIL — engine literals fell to {n_lit}, the "
              f"ceiling still says {MAX_ENGINE_LITERALS}.{chr(10)}")
        return 1
    print(f"[port-adoption-gate] engine literals {n_lit}/{MAX_ENGINE_LITERALS} — the repo "
          f"layer names no engine; the session does")

    pinned = scan_pinned_sessions()
    n_pin = sum(pinned.values())
    if n_pin != MAX_PINNED_SESSIONS:
        verb = "GREW to" if n_pin > MAX_PINNED_SESSIONS else "fell to"
        print(f"{chr(10)}[port-adoption-gate] FAIL — engine-pinned session call sites {verb} "
              f"{n_pin} (recorded {MAX_PINNED_SESSIONS}).{chr(10)}")
        for mod, n in sorted(pinned.items()):
            print(f"    {mod}  x{n}")
        print(f"{chr(10)}  `graph_session()` follows KNOWLEDGE_GRAPH_BACKEND. Only the "
              f"benchmarks and the{chr(10)}  one-shot scripts may pin an engine — service code "
              f"that pins one recreates{chr(10)}  the two-store split T54b measured. Move the "
              f"number in the same commit.{chr(10)}")
        return 1
    print(f"[port-adoption-gate] engine-pinned sessions {n_pin}/{MAX_PINNED_SESSIONS} — "
          f"benchmarks and one-shot scripts only; service code follows the configuration")
    print("[port-adoption-gate] PASS — exactly at the ceiling; it can only fall")
    return 0


if __name__ == "__main__":
    sys.exit(main())
