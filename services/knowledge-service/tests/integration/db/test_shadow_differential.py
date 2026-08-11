"""T43's PROPERTY-BASED differential suite — randomised traffic, both engines, one verdict.

WHY THIS EXISTS SEPARATELY FROM `test_shadow_comparison.py`
-----------------------------------------------------------
That file drives each operation **once**, in a hand-written order. It proves the operations
CAN be compared and agreed on that path — coverage, not confidence. T43's own text asks for
three things: *"Shadow comparison + **property-based differential suite** + coverage floor"*,
and the middle one is this. Two engines that agree on one scripted sequence can still diverge
on the orderings nobody thought to write down, and those are precisely the ones a shadow
comparison is supposed to find before a cutover does.

SEEDED, NOT RANDOM
------------------
A failing seed here is a **reproducible bug report**: the sequence is printed and re-running
with the same seed replays it exactly. A genuinely random suite that fails once a week and
cannot be replayed teaches nothing and gets marked flaky, which is how a differential suite
dies. `hypothesis` is not a dependency of this service and adding one for this would be a
larger decision than the test justifies.

WHAT IS ASSERTED, AND WHAT IS DELIBERATELY NOT
-----------------------------------------------
The property is **agreement**, not correctness. Correctness is `test_graph_store_conformance.py`
— every adapter passes the same behavioural rules — and that is what makes agreement here
meaningful rather than two implementations sharing a bug.

⚠️ **Node ids are excluded from the comparison** and that is not a weakening. Each engine
mints its own, so comparing them would report 100 % divergence and say nothing; the shadow's
identity mapping translates them and `_comparable` compares the identity tuple instead. The
first T43 run learned this the hard way — four operations reported `secondary=None`, none of
which was an engine difference.

    docker run -d --name lw-neo4j-scratch -p 7999:7687 \
      -e NEO4J_AUTH=neo4j/loreweave_dev_neo4j neo4j:5-community
    docker run -d --name lw-age-t43 -e POSTGRES_PASSWORD=x -p 7893:5432 \
      loreweave/postgres-knowledge:18
    TEST_NEO4J_URI=bolt://localhost:7999 \
      TEST_AGE_DSN=postgresql://postgres:x@localhost:7893/postgres \
      pytest tests/integration/db/test_shadow_differential.py
"""
from __future__ import annotations

import os
import random
import uuid

import pytest
import pytest_asyncio

from app.adapters.age_graph_store import AgeGraphStore
from app.adapters.neo4j_graph_store import Neo4jGraphStore
from app.adapters.shadow_graph_store import OPERATIONS, ShadowGraphStore
from app.db.age_bootstrap import create_age_pool, ensure_graph

pytestmark = pytest.mark.asyncio

#: Seeds are FIXED, not drawn from the clock — see the module docstring. Adding a seed is a
#: deliberate act that widens coverage permanently rather than a lottery that occasionally
#: finds something and cannot be replayed.
SEEDS = (1, 7, 42, 1337, 90210)
#: Operations per sequence. Long enough that ordering matters (an archive before a read, a
#: re-merge after an archive), short enough that a failure is readable.
SEQUENCE_LENGTH = 25

_NAMES = ("Kai", "Mira", "Lam", "Vex", "Ora")
_KINDS = ("character", "location", "organization")
_PREDICATES = ("ally_of", "rival_of", "knows", "parent_of")


@pytest_asyncio.fixture
async def shadow(neo4j_driver):
    dsn = os.environ.get("TEST_AGE_DSN")
    if not dsn:
        pytest.skip("TEST_AGE_DSN not set — the differential suite needs BOTH engines")
    pool = await create_age_pool(dsn, min_size=2, max_size=4)
    try:
        async with pool.acquire() as conn:
            gname = await ensure_graph(conn, uuid.uuid4())
        async with neo4j_driver.session() as session:
            yield ShadowGraphStore(Neo4jGraphStore(session), AgeGraphStore(pool, gname))
    finally:
        await pool.close()


async def _run_sequence(store, rng: random.Random, user_id: str, project_id: str) -> list[str]:
    """Drive a randomised operation sequence. Returns the trace, for the failure message."""
    trace: list[str] = []
    known: list[str] = []          # primary entity ids the sequence has created
    ordinal = 0

    for _ in range(SEQUENCE_LENGTH):
        # `resolve_or_merge_entity` is weighted up on purpose: it is the only operation that
        # teaches the shadow an id mapping, so a sequence starved of it would spend most of
        # its calls `unmapped` and quietly measure nothing.
        op = rng.choices(
            ["merge", "find", "relate", "relations", "archive", "restore",
             "status", "events", "neighborhood"],
            weights=[5, 2, 3, 3, 1, 1, 1, 1, 1],
        )[0]

        # ⚠️ A guarded op that cannot run must FALL BACK, not vanish. The first version let
        # the elif-chain fall through when `known` was empty, so an iteration did nothing at
        # all — seed 1337 produced 8 comparisons from 25 calls, and the non-vacuity assertion
        # is what caught it. A generator that silently skips work makes a differential suite
        # report agreement it never tested for.
        if op in ("relations", "archive", "restore", "status") and not known:
            op = "merge"
        elif op == "relate" and len(known) < 2:
            op = "merge"

        if op == "merge":
            name, kind = rng.choice(_NAMES), rng.choice(_KINDS)
            e = await store.resolve_or_merge_entity(
                user_id=user_id, project_id=project_id, name=name, kind=kind,
                source_type=rng.choice(["chapter", "chat", "manual"]))
            if e and e.id not in known:
                known.append(e.id)
            trace.append(f"merge({name},{kind})")

        elif op == "find":
            name = rng.choice(_NAMES)
            await store.find_entities_by_name(
                user_id=user_id, project_id=project_id, name=name,
                include_archived=rng.choice([True, False]))
            trace.append(f"find({name})")

        elif op == "relate":
            s, o = rng.sample(known, 2)
            ordinal += rng.randint(1, 5)
            await store.upsert_relation(
                user_id=user_id, subject_id=s, object_id=o,
                predicate=rng.choice(_PREDICATES),
                confidence=round(rng.uniform(0.0, 1.0), 2),
                valid_from_ordinal=rng.choice([None, ordinal]))
            trace.append(f"relate(->,{ordinal})")

        elif op == "relations":
            await store.relations_for(
                user_id=user_id, entity_id=rng.choice(known), project_id=project_id,
                direction=rng.choice(["outgoing", "incoming", "both"]),
                min_confidence=rng.choice([0.0, 0.5, 0.8]),
                as_of=rng.choice([None, ordinal, ordinal + 10]))
            trace.append("relations()")

        elif op == "archive":
            await store.archive_entity(
                user_id=user_id, canonical_id=rng.choice(known), reason="differential")
            trace.append("archive()")

        elif op == "restore":
            await store.restore_entity(user_id=user_id, canonical_id=rng.choice(known))
            trace.append("restore()")

        elif op == "status":
            await store.status_at_order(
                user_id=user_id, project_id=project_id,
                entity_ids=rng.sample(known, min(len(known), 3)), at_order=ordinal)
            trace.append("status()")

        elif op == "events":
            await store.events_in_window(
                user_id=user_id, project_id=project_id,
                axis=rng.choice(["narrative", "chronological"]))
            trace.append("events()")

        elif op == "neighborhood":
            await store.neighborhood(
                user_id=user_id, glossary_entity_id=f"g-{rng.randint(1, 3)}",
                project_id=project_id)
            trace.append("neighborhood()")

    return trace


@pytest.mark.parametrize("seed", SEEDS)
async def test_the_engines_agree_under_randomised_sequences(shadow, seed):
    """THE property: whatever order the operations arrive in, both engines answer alike.

    A divergence fails with the seed and the trace, so the exact sequence replays.
    """
    rng = random.Random(seed)
    user_id, project_id = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
    trace = await _run_sequence(shadow, rng, user_id, project_id)
    report = shadow.coverage_report()

    diverged = {op: r for op, r in report["operations"].items() if r["diverged"]}
    assert not diverged, (
        f"seed={seed} diverged on {sorted(diverged)}\n"
        f"samples: {report['samples']}\n"
        f"trace: {' '.join(trace)}"
    )

    # Non-vacuity. A sequence that compared nothing would satisfy "no divergence" perfectly,
    # which is the failure mode this whole file is defending against.
    compared = sum(report["operations"][op]["observations"] for op in OPERATIONS)
    assert compared >= SEQUENCE_LENGTH // 2, (
        f"seed={seed} produced only {compared} comparisons from {SEQUENCE_LENGTH} calls — "
        f"the run proved little. unmapped={ {o: r['unmapped'] for o, r in report['operations'].items() if r['unmapped']} }"
    )


async def test_the_seed_corpus_reaches_every_operation(shadow):
    """Coverage of the SUITE, not of one run.

    Any single seed may skip an operation by chance. What must not happen is that the whole
    corpus of seeds never exercises one — an operation absent from every sequence is
    untested while the suite reports green, which is `blocked_by` one level up.
    """
    seen: set[str] = set()
    for seed in SEEDS:
        rng = random.Random(seed)
        u, p = f"u-{uuid.uuid4().hex[:10]}", f"p-{uuid.uuid4().hex[:10]}"
        await _run_sequence(shadow, rng, u, p)
        rep = shadow.coverage_report()
        seen |= {op for op in OPERATIONS if rep["operations"][op]["observations"]}

    missing = set(OPERATIONS) - seen
    assert not missing, (
        f"no seed in {SEEDS} ever compared {sorted(missing)} — add a seed or reweight "
        f"`_run_sequence`, because these operations are untested while the suite is green"
    )
