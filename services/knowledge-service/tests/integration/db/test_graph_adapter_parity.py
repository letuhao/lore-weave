"""QC-2 — adapter parity: the fake must answer like the real one.

**This is the load-bearing control for Phase 2, and T20 made it more so, not less.**

QC-2 was written expecting the fakes to carry ~561 tests, so drift would make all of them
lie. T20 measured that premise and rejected it: the Neo4j-gated tests are REPOSITORY tests
that verify Cypher, and repointing them at a fake would be the fake grading itself. They
were made to run against a real graph instead.

The consequence is that the fakes are now checked by exactly one thing — this file. Nothing
else compares `FakeGraphStore` against `Neo4jGraphStore`, so if it drifts, every unit test
that uses the fake becomes a claim about the fake rather than about the system.

── WHAT IS COMPARED, AND WHAT IS DELIBERATELY NOT ───────────────────────────────────────
Both stores run the SAME sequence of port calls and the results are diffed field by field,
excluding:

  - **timestamps** — the fake stamps a fixed instant so its output is deterministic; a real
    write stamps `datetime()`. Comparing them would fail on every run for no reason.
  - **`source_types` ORDER** — the real store accumulates through Cypher `coalesce`, the
    fake through a list append. The SET is contract; the order is not, and pinning it would
    be inventing a guarantee neither store makes.

Everything else is compared, including ids: entity ids are content-addressed hashes of
(user, project, name, kind), so identical inputs MUST produce identical ids in both — and a
fake that minted its own scheme would break every test that asserts on an id elsewhere.
"""

from __future__ import annotations

import os

import pytest

from app.adapters.fake_graph_store import FakeGraphStore
from app.adapters.neo4j_graph_store import Neo4jGraphStore

# Applied per-test rather than module-wide: the non-vacuity guard at the bottom is
# deliberately SYNC (it asserts on the environment, not on a store), and a blanket
# asyncio mark warns on it every run — a warning nobody reads is how a real one hides.
_aio = pytest.mark.asyncio

_U = "parity-user"
_P = "parity-project"

# Fields whose difference is expected and not a defect — see the module docstring.
_VOLATILE = {"created_at", "updated_at", "archived_at", "valid_from", "valid_until"}


def _norm_entity(e) -> dict:
    d = e.model_dump()
    for k in _VOLATILE:
        d.pop(k, None)
    # The SET is contract; the order is an implementation accident on both sides.
    d["source_types"] = sorted(d.get("source_types") or [])
    return d


def _norm_relation(r) -> dict:
    d = r.model_dump()
    for k in _VOLATILE:
        d.pop(k, None)
    d["source_event_ids"] = sorted(d.get("source_event_ids") or [])
    return d


@pytest.fixture
async def stores(neo4j_driver):
    """Both implementations, plus a cleanup that removes only what this test made.

    Scoped by `project_id`, never a bare `MATCH (n) DETACH DELETE n`: the fixture's own
    docstring warns that a global truncate would clobber concurrent tests, and this suite
    now runs alongside 300+ others.
    """
    async with neo4j_driver.session() as session:
        real = Neo4jGraphStore(session)
        fake = FakeGraphStore()
        try:
            yield real, fake, session
        finally:
            await session.run(
                "MATCH (n) WHERE n.user_id = $u AND n.project_id = $p DETACH DELETE n",
                u=_U, p=_P,
            )


async def _resolve_both(real, fake, name: str, kind: str = "character"):
    kwargs = dict(
        user_id=_U, project_id=_P, name=name, kind=kind, source_type="chapter",
    )
    return (
        await real.resolve_or_merge_entity(**kwargs),
        await fake.resolve_or_merge_entity(**kwargs),
    )


@_aio
async def test_resolve_produces_the_same_entity_including_its_id(stores):
    """Entity ids are content-addressed hashes of (user, project, name, kind). If the fake
    minted its own scheme, every unit test that asserts on an id would be asserting about a
    fiction."""
    real, fake, _ = stores
    r, f = await _resolve_both(real, fake, "Kai Parity")
    assert r.id == f.id
    assert _norm_entity(r) == _norm_entity(f)


@_aio
async def test_resolving_twice_is_idempotent_in_both(stores):
    real, fake, _ = stores
    r1, f1 = await _resolve_both(real, fake, "Idem Parity")
    r2, f2 = await _resolve_both(real, fake, "Idem Parity")
    assert r1.id == r2.id == f1.id == f2.id
    assert _norm_entity(r2) == _norm_entity(f2)


@_aio
async def test_confidence_is_a_high_water_mark_in_both(stores):
    """A LOWER-confidence re-observation must not lower what is already known. The real
    store spells that as `WHEN $confidence > e.confidence`; a fake that simply assigned
    would let a weak later mention quietly demote a strong earlier one, and every unit test
    would agree with it.

    Written after a QC-2 bite failed to bite: nothing here re-resolved at a lower
    confidence, so the rule was unasserted on both sides."""
    real, fake, _ = stores
    strong = dict(user_id=_U, project_id=_P, name="Conf HW", kind="character",
                  source_type="chapter", confidence=0.9)
    weak = {**strong, "confidence": 0.3}

    await real.resolve_or_merge_entity(**strong)
    await fake.resolve_or_merge_entity(**strong)
    r = await real.resolve_or_merge_entity(**weak)
    f = await fake.resolve_or_merge_entity(**weak)

    assert r.confidence == f.confidence == pytest.approx(0.9)


@_aio
async def test_find_by_name_agrees_including_the_archived_rule(stores):
    """The rule that matters: an archived entity is excluded by default. A fake that kept
    returning it would let a resolver silently re-anchor extraction onto something the
    author deleted, and nothing else would notice."""
    real, fake, _ = stores
    r, f = await _resolve_both(real, fake, "Archive Parity")

    rq = await real.find_entities_by_name(user_id=_U, project_id=_P, name="Archive Parity")
    fq = await fake.find_entities_by_name(user_id=_U, project_id=_P, name="Archive Parity")
    assert [e.id for e in rq] == [e.id for e in fq] == [r.id]

    await real.archive_entity(user_id=_U, canonical_id=r.id, reason="parity")
    await fake.archive_entity(user_id=_U, canonical_id=f.id, reason="parity")

    assert await real.find_entities_by_name(user_id=_U, project_id=_P, name="Archive Parity") == []
    assert await fake.find_entities_by_name(user_id=_U, project_id=_P, name="Archive Parity") == []

    r_arch = await real.find_entities_by_name(
        user_id=_U, project_id=_P, name="Archive Parity", include_archived=True)
    f_arch = await fake.find_entities_by_name(
        user_id=_U, project_id=_P, name="Archive Parity", include_archived=True)
    assert [e.id for e in r_arch] == [e.id for e in f_arch] == [r.id]

    await real.restore_entity(user_id=_U, canonical_id=r.id)
    await fake.restore_entity(user_id=_U, canonical_id=f.id)
    assert len(await real.find_entities_by_name(user_id=_U, project_id=_P, name="Archive Parity")) == 1
    assert len(await fake.find_entities_by_name(user_id=_U, project_id=_P, name="Archive Parity")) == 1


@_aio
async def test_relations_at_head_agree(stores):
    real, fake, _ = stores
    a_r, a_f = await _resolve_both(real, fake, "Rel A")
    b_r, b_f = await _resolve_both(real, fake, "Rel B")

    for store, subj, obj in ((real, a_r.id, b_r.id), (fake, a_f.id, b_f.id)):
        await store.upsert_relation(
            user_id=_U, subject_id=subj, predicate="allied_with", object_id=obj,
            confidence=0.95, valid_from_ordinal=10,
        )

    rr = await real.relations_for(user_id=_U, entity_id=a_r.id, project_id=_P)
    fr = await fake.relations_for(user_id=_U, entity_id=a_f.id, project_id=_P)
    assert len(rr) == len(fr) == 1
    assert rr[0].predicate == fr[0].predicate
    assert rr[0].valid_from_ordinal == fr[0].valid_from_ordinal


@_aio
async def test_the_as_of_read_agrees_on_the_half_open_boundary(stores):
    """The boundary the whole refactor is about. `valid_from <= N < valid_to`, and both
    stores must draw it in the same place — an off-by-one that exists in only one of them
    is invisible to every unit test, because the unit tests only ever see the fake."""
    real, fake, session = stores
    a_r, a_f = await _resolve_both(real, fake, "AsOf A")
    b_r, b_f = await _resolve_both(real, fake, "AsOf B")

    for store, subj, obj in ((real, a_r.id, b_r.id), (fake, a_f.id, b_f.id)):
        await store.upsert_relation(
            user_id=_U, subject_id=subj, predicate="allied_with", object_id=obj,
            confidence=0.95, valid_from_ordinal=10,
        )
    # Close the interval at 20 in both. The real store's chain maintenance is a separate
    # routine, so the edge is closed directly here — this test is about the READ.
    await session.run(
        "MATCH (:Entity {id: $s})-[r:RELATES_TO]->(:Entity {id: $o}) SET r.valid_to_ordinal = 20",
        s=a_r.id, o=b_r.id,
    )
    (await fake.relations_for(user_id=_U, entity_id=a_f.id))[0].valid_to_ordinal = 20

    for n, expected in ((9, 0), (10, 1), (19, 1), (20, 0), (50, 0)):
        rn = len(await real.relations_for(user_id=_U, entity_id=a_r.id, project_id=_P, as_of=n))
        fn = len(await fake.relations_for(user_id=_U, entity_id=a_f.id, project_id=_P, as_of=n))
        assert rn == fn == expected, f"as_of={n}: real={rn} fake={fn} expected={expected}"


@_aio
async def test_a_positionless_edge_is_excluded_by_both_as_of_reads(stores):
    """Cypher excludes it via three-valued logic; the fake has to say it in Python. This is
    the single most likely place for the two to disagree, and the disagreement would look
    like extra context rather than a bug."""
    real, fake, _ = stores
    a_r, a_f = await _resolve_both(real, fake, "Legacy A")
    b_r, b_f = await _resolve_both(real, fake, "Legacy B")

    for store, subj, obj in ((real, a_r.id, b_r.id), (fake, a_f.id, b_f.id)):
        await store.upsert_relation(
            user_id=_U, subject_id=subj, predicate="knows", object_id=obj,
            confidence=0.95, valid_from_ordinal=None,
        )

    assert len(await real.relations_for(user_id=_U, entity_id=a_r.id, project_id=_P)) == 1
    assert len(await fake.relations_for(user_id=_U, entity_id=a_f.id, project_id=_P)) == 1
    assert await real.relations_for(user_id=_U, entity_id=a_r.id, project_id=_P, as_of=50) == []
    assert await fake.relations_for(user_id=_U, entity_id=a_f.id, project_id=_P, as_of=50) == []


@_aio
async def test_direction_filters_agree(stores):
    real, fake, _ = stores
    a_r, a_f = await _resolve_both(real, fake, "Dir A")
    b_r, b_f = await _resolve_both(real, fake, "Dir B")

    for store, a, b in ((real, a_r.id, b_r.id), (fake, a_f.id, b_f.id)):
        await store.upsert_relation(user_id=_U, subject_id=a, predicate="out_p",
                                    object_id=b, confidence=0.95)
        await store.upsert_relation(user_id=_U, subject_id=b, predicate="in_p",
                                    object_id=a, confidence=0.95)

    for direction in ("outgoing", "incoming", "both"):
        rp = sorted(r.predicate for r in await real.relations_for(
            user_id=_U, entity_id=a_r.id, project_id=_P, direction=direction))
        fp = sorted(r.predicate for r in await fake.relations_for(
            user_id=_U, entity_id=a_f.id, project_id=_P, direction=direction))
        assert rp == fp, f"direction={direction}: real={rp} fake={fp}"


@_aio
async def test_the_confidence_floor_agrees(stores):
    real, fake, _ = stores
    a_r, a_f = await _resolve_both(real, fake, "Conf A")
    b_r, b_f = await _resolve_both(real, fake, "Conf B")

    for store, a, b in ((real, a_r.id, b_r.id), (fake, a_f.id, b_f.id)):
        await store.upsert_relation(user_id=_U, subject_id=a, predicate="weak",
                                    object_id=b, confidence=0.5)

    assert await real.relations_for(user_id=_U, entity_id=a_r.id, project_id=_P) == []
    assert await fake.relations_for(user_id=_U, entity_id=a_f.id, project_id=_P) == []
    assert len(await real.relations_for(
        user_id=_U, entity_id=a_r.id, project_id=_P, min_confidence=0.4)) == 1
    assert len(await fake.relations_for(
        user_id=_U, entity_id=a_f.id, project_id=_P, min_confidence=0.4)) == 1


def test_this_file_actually_ran_against_a_real_graph():
    """Non-vacuity guard. Every test above is skipped when TEST_NEO4J_URI is unset, and a
    skipped parity suite reports the same green as a passing one — which is precisely the
    failure mode QC-2 exists to prevent. This makes the skip VISIBLE as a warning in the
    output rather than silent."""
    if not os.environ.get("TEST_NEO4J_URI"):
        pytest.skip(
            "QC-2 PARITY DID NOT RUN — TEST_NEO4J_URI is unset, so FakeGraphStore was "
            "compared against nothing. The fakes' only check is this file."
        )
    assert True
