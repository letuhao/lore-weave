"""T42 — `KuzuGraphStore`'s entity surface, against a REAL Kuzu database.

The conformance suite (T42a) is the real judge and this adapter joins it as a fourth param.
What lives HERE is the handful of rules that are about *Kuzu specifically* — the identity
workaround its PRIMARY KEY forces, and the refusals — because those are not portable rules and
would only clutter a suite whose whole point is that every adapter obeys the same ones.
"""
from __future__ import annotations

import asyncio

import pytest

from app.db.kuzu_bootstrap import close_kuzu, open_kuzu

pytest.importorskip("kuzu", reason="kuzu is an optional T43-candidate dependency")
from app.adapters.kuzu_graph_store import KuzuGraphStore  # noqa: E402

U = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
P = "019f1783-ecca-7331-afab-9543762a8b68"


@pytest.fixture
def store(tmp_path):
    db, conn = open_kuzu(str(tmp_path / "kg"))
    try:
        yield KuzuGraphStore(conn)
    finally:
        close_kuzu(db, conn)


@pytest.mark.asyncio
async def test_the_id_is_OPAQUE_and_not_derived_from_the_name(store):
    """🔴 THE rule this adapter's design turns on. Kuzu demands the primary key in every MERGE,
    and the tempting escape is `PK = hash(user, project, canonical_name, kind)` — which is
    `e.id = hash(name, kind)`, the exact scheme T35 exists to RETIRE. Taking it would have
    introduced the defect as a NEW adapter's design rather than as legacy.

    Two entities differing only in name must not have related ids, and an id must not be
    reconstructible from the identity tuple.
    """
    a = await store.resolve_or_merge_entity(
        user_id=U, project_id=P, name="Kai", kind="character", source_type="chapter")
    b = await store.resolve_or_merge_entity(
        user_id=U, project_id=P, name="Mira", kind="character", source_type="chapter")
    assert a.id != b.id
    for e, nm in ((a, "Kai"), (b, "Mira")):
        assert nm.lower() not in e.id.lower(), "the id leaks the name"
        assert e.canonical_name and e.canonical_name not in e.id


@pytest.mark.asyncio
async def test_resolve_is_idempotent_and_ACCUMULATES_source_types(store):
    """The property that separates an upsert from an adapter rebuilding the object at the same
    key: a re-mention must never NARROW what is already known."""
    first = await store.resolve_or_merge_entity(
        user_id=U, project_id=P, name="Kai", kind="character",
        source_type="chapter", confidence=0.4)
    again = await store.resolve_or_merge_entity(
        user_id=U, project_id=P, name="Kai", kind="character",
        source_type="user_note", confidence=0.9)
    assert again.id == first.id, "a second resolve created a SECOND node"
    assert set(again.source_types) == {"chapter", "user_note"}
    assert again.confidence == 0.9, "confidence must be a MAX across mentions"

    # ...and lowering it again must not win.
    lower = await store.resolve_or_merge_entity(
        user_id=U, project_id=P, name="Kai", kind="character",
        source_type="chapter", confidence=0.1)
    assert lower.confidence == 0.9


@pytest.mark.asyncio
async def test_CONCURRENT_resolves_of_one_name_do_not_double_create(store):
    """🔴 The half the file lock does NOT cover. Kuzu serialises writers across PROCESSES, which
    is what makes MATCH-then-CREATE sound at all — but inside one process two async tasks can
    both miss the lookup and both create, and there is no unique index on the identity tuple to
    catch the duplicate (`UNIQUE(a)` is a parser error in Kuzu). `_identity_lock` is the fix,
    and this is the test that would go red if someone removed it as redundant."""
    made = await asyncio.gather(*[
        store.resolve_or_merge_entity(user_id=U, project_id=P, name="Kai",
                                      kind="character", source_type=f"s{i}")
        for i in range(8)
    ])
    assert len({e.id for e in made}) == 1, "concurrent resolves created duplicate identities"
    found = await store.find_entities_by_name(user_id=U, project_id=P, name="Kai")
    assert len(found) == 1


@pytest.mark.asyncio
async def test_a_DIFFERENT_user_gets_a_different_entity(store):
    """Tenancy, on the identity key rather than on a filter bolted over it."""
    mine = await store.resolve_or_merge_entity(
        user_id=U, project_id=P, name="Kai", kind="character", source_type="chapter")
    theirs = await store.resolve_or_merge_entity(
        user_id="019d49c9-9d33-702d-ae21-5fe2650d9aea", project_id=P, name="Kai",
        kind="character", source_type="chapter")
    assert mine.id != theirs.id
    assert await store.find_entities_by_name(user_id=U, project_id=P, name="Kai") != []
    assert [e.id for e in await store.find_entities_by_name(
        user_id=U, project_id=P, name="Kai")] == [mine.id]


@pytest.mark.asyncio
async def test_archive_hides_by_default_and_restore_brings_it_back(store):
    e = await store.resolve_or_merge_entity(
        user_id=U, project_id=P, name="Kai", kind="character", source_type="chapter")
    assert await store.archive_entity(user_id=U, canonical_id=e.id, reason="merged away")
    assert await store.find_entities_by_name(user_id=U, project_id=P, name="Kai") == []
    still = await store.find_entities_by_name(
        user_id=U, project_id=P, name="Kai", include_archived=True)
    assert [x.id for x in still] == [e.id] and still[0].archive_reason == "merged away"
    assert await store.restore_entity(user_id=U, canonical_id=e.id)
    assert [x.id for x in await store.find_entities_by_name(
        user_id=U, project_id=P, name="Kai")] == [e.id]


@pytest.mark.asyncio
async def test_archiving_someone_elses_entity_is_a_MISS_not_a_write(store):
    e = await store.resolve_or_merge_entity(
        user_id=U, project_id=P, name="Kai", kind="character", source_type="chapter")
    assert await store.archive_entity(
        user_id="019d49c9-9d33-702d-ae21-5fe2650d9aea", canonical_id=e.id, reason="x") is None
    assert await store.find_entities_by_name(user_id=U, project_id=P, name="Kai") != []


@pytest.mark.asyncio
async def test_a_name_full_of_quotes_round_trips_as_DATA(store):
    """The AGE adapter shipped a SQL injection and had to be fixed. Kuzu takes real parameters,
    so there is no string-building here — asserted rather than assumed."""
    nasty = "Kai'; DROP TABLE Entity; --"
    e = await store.resolve_or_merge_entity(
        user_id=U, project_id=P, name=nasty, kind="character", source_type="chapter")
    assert e.name == nasty
    assert [x.id for x in await store.find_entities_by_name(
        user_id=U, project_id=P, name=nasty)] == [e.id]


@pytest.mark.asyncio
async def test_the_unwritten_operations_REFUSE_and_name_their_section(store):
    """Rule 9, and the reason it matters: a skip in the conformance suite must correspond to a
    real refusal, or "Kuzu is skipped here" quietly becomes "Kuzu passed"."""
    # Shrinks as methods land — relations came off this list in the same commit that
    # implemented them, which is the discipline: a stale refusal list is a claim that
    # something is unbuilt when it is not.
    for op in ("merge_fact", "facts_for", "add_evidence",
               "update_event_fields", "status_at_order"):
        with pytest.raises(NotImplementedError, match="T42"):
            await getattr(store, op)()
