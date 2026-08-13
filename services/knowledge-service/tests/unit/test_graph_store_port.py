"""The `GraphStore` port contract (plan T18).

Third port, same two-part shape: the RULES against the fake, plus signature conformance for
both implementations. This fake is the one T20's ~561 tests will lean on hardest, so the
rules it must reproduce are the ones whose absence is SILENT — a cross-tenant read, an
archived entity resurfacing in a resolver, an untimed edge leaking into a timed answer.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest

from app.adapters.age_graph_store import AgeGraphStore
from app.adapters.fake_graph_store import FakeGraphStore
from app.adapters.neo4j_graph_store import Neo4jGraphStore
from app.db.neo4j_repos.events import Event
from app.ports.graph_store import GraphStore

_U = "user-1"
_OTHER = "user-2"
_P = "proj-1"
_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


async def _entity(store, name="Kai", *, user_id=_U, project_id=_P, kind="character"):
    return await store.resolve_or_merge_entity(
        user_id=user_id, project_id=project_id, name=name, kind=kind,
        source_type="chapter",
    )


# ── entities ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolving_the_same_name_twice_returns_the_same_entity():
    """Idempotency is the resolver's whole job. A fake that appended would hide every
    duplicate-minting bug in extraction — which is the defect class the KG has actually
    shipped before."""
    store = FakeGraphStore()
    a = await store.resolve_or_merge_entity(
        user_id=_U, project_id=_P, name="Kai", kind="character", source_type="chapter",
    )
    b = await store.resolve_or_merge_entity(
        user_id=_U, project_id=_P, name="Kai", kind="character", source_type="chat",
    )
    assert a.id == b.id
    assert store.entity_count() == 1
    # The load-bearing assertion: source types ACCUMULATE. Matching id and a count of one
    # both survive a fake that builds a fresh object and stores it at the same key — only
    # this shows the EXISTING entity was returned and updated, which is what idempotent
    # means here. (Measured: the first version of this test passed that bite.)
    assert sorted(b.source_types) == ["chapter", "chat"]


@pytest.mark.asyncio
async def test_the_same_name_in_two_projects_is_two_entities():
    store = FakeGraphStore()
    a = await _entity(store, project_id="proj-1")
    b = await _entity(store, project_id="proj-2")
    assert a.id != b.id


@pytest.mark.asyncio
async def test_another_users_entity_is_not_found_by_name():
    store = FakeGraphStore()
    await _entity(store, user_id=_OTHER)
    assert await store.find_entities_by_name(user_id=_U, project_id=_P, name="Kai") == []


@pytest.mark.asyncio
async def test_an_archived_entity_is_excluded_from_name_resolution_by_default():
    """A resolver that matched an archived entity silently re-anchors extraction onto
    something the author deleted."""
    store = FakeGraphStore()
    e = await _entity(store)
    await store.archive_entity(user_id=_U, canonical_id=e.id, reason="merged away")

    assert await store.find_entities_by_name(user_id=_U, project_id=_P, name="Kai") == []
    found = await store.find_entities_by_name(
        user_id=_U, project_id=_P, name="Kai", include_archived=True,
    )
    assert [x.id for x in found] == [e.id]

    await store.restore_entity(user_id=_U, canonical_id=e.id)
    assert len(await store.find_entities_by_name(user_id=_U, project_id=_P, name="Kai")) == 1


@pytest.mark.asyncio
async def test_archiving_another_users_entity_is_a_miss_not_a_write():
    store = FakeGraphStore()
    e = await _entity(store)
    assert await store.archive_entity(user_id=_OTHER, canonical_id=e.id, reason="x") is None
    assert len(await store.find_entities_by_name(user_id=_U, project_id=_P, name="Kai")) == 1


# ── relations, and the as-of rule ────────────────────────────────────


@pytest.mark.asyncio
async def test_as_of_uses_a_half_open_interval():
    """`valid_from <= N < valid_to`. The off-by-one here decides whether the chapter an
    edge ENDS in still reports it — the same boundary Phase 1 pinned for the glossary."""
    store = FakeGraphStore()
    await store.upsert_relation(
        user_id=_U, subject_id="a", predicate="allied_with", object_id="b",
        confidence=1.0, valid_from_ordinal=10,
    )
    rel = (await store.relations_for(user_id=_U, entity_id="a"))[0]
    rel.valid_to_ordinal = 20

    assert len(await store.relations_for(user_id=_U, entity_id="a", as_of=10)) == 1, "start is inclusive"
    assert len(await store.relations_for(user_id=_U, entity_id="a", as_of=19)) == 1
    assert len(await store.relations_for(user_id=_U, entity_id="a", as_of=20)) == 0, "end is exclusive"
    assert len(await store.relations_for(user_id=_U, entity_id="a", as_of=9)) == 0


@pytest.mark.asyncio
async def test_a_positionless_edge_is_excluded_by_an_as_of_read_but_not_by_a_head_read():
    """The edge case that makes the port worth having. Legacy edges carry no
    `valid_from_ordinal`; an as-of read must NOT return them, or untimed data leaks into
    an answer whose entire value is that it is timed. Cypher gets this from three-valued
    logic; the fake has to say it explicitly, and this test is why."""
    store = FakeGraphStore()
    await store.upsert_relation(
        user_id=_U, subject_id="a", predicate="knows", object_id="b",
        confidence=1.0, valid_from_ordinal=None,
    )
    assert len(await store.relations_for(user_id=_U, entity_id="a")) == 1, "HEAD read keeps it"
    assert await store.relations_for(user_id=_U, entity_id="a", as_of=50) == []


@pytest.mark.asyncio
async def test_direction_narrows_and_both_is_the_default():
    store = FakeGraphStore()
    await store.upsert_relation(user_id=_U, subject_id="a", predicate="p", object_id="b", confidence=1.0)
    await store.upsert_relation(user_id=_U, subject_id="c", predicate="q", object_id="a", confidence=1.0)

    assert len(await store.relations_for(user_id=_U, entity_id="a")) == 2
    out = await store.relations_for(user_id=_U, entity_id="a", direction="outgoing")
    assert [r.predicate for r in out] == ["p"]
    inc = await store.relations_for(user_id=_U, entity_id="a", direction="incoming")
    assert [r.predicate for r in inc] == ["q"]


@pytest.mark.asyncio
async def test_low_confidence_edges_are_filtered_by_default():
    """The default is 0.8, matching the L2 context loader: a low-confidence edge in a
    prompt is a hallucination with provenance."""
    store = FakeGraphStore()
    await store.upsert_relation(user_id=_U, subject_id="a", predicate="p", object_id="b", confidence=0.5)
    assert await store.relations_for(user_id=_U, entity_id="a") == []
    assert len(await store.relations_for(user_id=_U, entity_id="a", min_confidence=0.4)) == 1


@pytest.mark.asyncio
async def test_upserting_the_same_arc_twice_does_not_duplicate_it():
    store = FakeGraphStore()
    await store.upsert_relation(user_id=_U, subject_id="a", predicate="p", object_id="b",
                                confidence=0.9, source_event_id="e1")
    await store.upsert_relation(user_id=_U, subject_id="a", predicate="p", object_id="b",
                                confidence=0.9, source_event_id="e2")
    rels = await store.relations_for(user_id=_U, entity_id="a")
    assert len(rels) == 1
    # Later events ACCUMULATE onto the arc — that is why the read model has a plural
    # `source_event_ids` while the write takes one.
    assert rels[0].source_event_ids == ["e1", "e2"]


# ── status ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_is_a_step_function_the_latest_one_at_or_before_n_wins():
    store = FakeGraphStore()
    store.set_status(user_id=_U, project_id=_P, entity_id="e", from_order=10, status="alive")
    store.set_status(user_id=_U, project_id=_P, entity_id="e", from_order=40, status="gone")

    assert await store.status_at_order(user_id=_U, project_id=_P, entity_ids=["e"], at_order=9) == {}
    assert (await store.status_at_order(user_id=_U, project_id=_P, entity_ids=["e"], at_order=39))["e"] == "alive"
    assert (await store.status_at_order(user_id=_U, project_id=_P, entity_ids=["e"], at_order=40))["e"] == "gone"


@pytest.mark.asyncio
async def test_min_evidence_suppresses_a_single_mention_guess():
    """A status derived from one mention is a guess, and the canon guard acts on it."""
    store = FakeGraphStore()
    store.set_status(user_id=_U, project_id=_P, entity_id="e", from_order=10,
                     status="gone", evidence=1)
    assert await store.status_at_order(
        user_id=_U, project_id=_P, entity_ids=["e"], at_order=20, min_evidence=2,
    ) == {}


# ── events ───────────────────────────────────────────────────────────


def _event(eid: str, *, order=None, chrono=None, date=None) -> Event:
    return Event(
        id=eid, user_id=_U, project_id=_P, title=eid, canonical_title=eid, summary="",
        event_order=order, chronological_order=chrono, event_date_iso=date,
        created_at=_NOW, updated_at=_NOW,
    )


@pytest.mark.asyncio
async def test_the_three_axes_are_three_different_questions():
    """`narrative`, `chronological` and `date` order the same events differently — which is
    the reason the port keeps them apart instead of offering one 'time' parameter."""
    store = FakeGraphStore()
    store.add_event(_event("flashback", order=5, chrono=1, date="1990-01-01"))
    store.add_event(_event("present", order=1, chrono=5, date="2020-01-01"))

    narrative = await store.events_in_window(user_id=_U, project_id=_P, axis="narrative")
    chrono = await store.events_in_window(user_id=_U, project_id=_P, axis="chronological")
    assert [e.id for e in narrative] == ["present", "flashback"]
    assert [e.id for e in chrono] == ["flashback", "present"]


@pytest.mark.asyncio
async def test_an_event_with_no_value_on_the_requested_axis_is_not_in_a_bounded_window():
    """Otherwise "events between 10 and 20" quietly includes every undated one."""
    store = FakeGraphStore()
    store.add_event(_event("placed", order=15))
    store.add_event(_event("unplaced", order=None))

    bounded = await store.events_in_window(user_id=_U, project_id=_P, after=10, before=20)
    assert [e.id for e in bounded] == ["placed"]
    unbounded = await store.events_in_window(user_id=_U, project_id=_P)
    assert {e.id for e in unbounded} == {"placed", "unplaced"}


# ── structural conformance ───────────────────────────────────────────


@pytest.mark.parametrize("impl", [FakeGraphStore, Neo4jGraphStore, AgeGraphStore])
def test_implementations_match_the_port_signatures(impl):
    # ⚠️ T42: this caught the AGE adapter's two guessed signatures — `status_at_order` with
    # `entity_id` singular instead of `entity_ids`, and `events_in_window` missing
    # `include_archived` — while `isinstance(store, GraphStore)` reported **True** for the
    # same object. `runtime_checkable` compares method NAMES, not parameters, so the
    # Protocol alone would have let a mis-shaped adapter into T43's comparison.
    for name in ("resolve_or_merge_entity", "find_entities_by_name", "neighborhood",
                 "archive_entity", "restore_entity", "upsert_relation", "relations_for",
                 # T17 2026-08-12: the port grew by DEMAND. Adding the method to the port
                 # without adding it HERE would leave the new operation unchecked in every
                 # adapter -- the checklist is this tuple, so an omission is silent.
                 "add_evidence",
                 # T17 A1 2026-08-13: the three relation CORRECTION primitives. Listed here
                 # for the same reason `add_evidence` is -- this tuple IS the checklist, so
                 # a method added to the port and forgotten here is unchecked in every
                 # adapter and nothing says so.
                 "get_relation", "invalidate_relation", "recreate_relation",
                 "status_at_order", "events_in_window"):
        port_sig = inspect.signature(getattr(GraphStore, name))
        impl_sig = inspect.signature(getattr(impl, name))
        assert list(impl_sig.parameters) == list(port_sig.parameters), (
            f"{impl.__name__}.{name} parameters {list(impl_sig.parameters)} "
            f"!= port {list(port_sig.parameters)}"
        )
        for pname, pparam in port_sig.parameters.items():
            iparam = impl_sig.parameters[pname]
            assert iparam.kind == pparam.kind, f"{impl.__name__}.{name}({pname}) kind differs"
            assert iparam.default == pparam.default, (
                f"{impl.__name__}.{name}({pname}) defaults to {iparam.default!r}, "
                f"port says {pparam.default!r}"
            )
