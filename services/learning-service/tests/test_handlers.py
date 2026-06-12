"""Correction handlers — persist mapping, actor filter, dedup key, R3-W1 guard."""

import uuid

import pytest

from app.events.dispatcher import EventData
from app.events.handlers import (
    handle_glossary_entity_updated,
    handle_knowledge_corrected,
)

# Param index map for the INSERT in _persist_correction (0-based positional).
P_USER_ID = 0
P_TARGET_TYPE = 3
P_TARGET_ID = 4
P_OP = 5
# FD-19/052 added before/after_description_content_hash at positions 10,11 →
# everything from diff_class onward shifts +2.
P_BEFORE_DESC_HASH = 10
P_AFTER_DESC_HASH = 11
P_DIFF_CLASS = 12
P_ACTOR_TYPE = 16
P_ORIGIN_SERVICE = 18
P_ORIGIN_EVENT_ID = 19


class FakePool:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, *params):
        self.calls.append(params)


def _glossary_event(*, outbox_id, actor_type="user", actor_id=None, glossary_id=None,
                    before=None, after=None, op="updated", book_id=None):
    actor_id = actor_id or str(uuid.uuid4())
    glossary_id = glossary_id or str(uuid.uuid4())
    return EventData(
        stream="loreweave:events:glossary",
        message_id="1-0",
        event_type="glossary.entity_updated",
        aggregate_id=glossary_id,
        payload={
            "actor_type": actor_type,
            "actor_id": actor_id,
            "op": op,
            "glossary_entity_id": glossary_id,
            "book_id": book_id or str(uuid.uuid4()),
            "before": before,
            "after": after,
            "emitted_at": "2026-05-31T00:00:00Z",
        },
        source="glossary",
        raw={},
        outbox_id=outbox_id,
    )


async def test_glossary_user_correction_persisted_with_mapping():
    pool = FakePool()
    ev = _glossary_event(
        outbox_id="outbox-1",
        before={"name": "Lizzy", "kind": "person", "aliases": [], "short_description": "old"},
        after={"name": "Lizzy", "kind": "person", "aliases": [], "short_description": "new"},
    )
    await handle_glossary_entity_updated(ev, pool=pool)

    assert len(pool.calls) == 1
    p = pool.calls[0]
    assert p[P_TARGET_TYPE] == "entity"
    assert p[P_OP] == "update"
    assert p[P_ACTOR_TYPE] == "user"
    assert p[P_ORIGIN_SERVICE] == "glossary"
    assert p[P_ORIGIN_EVENT_ID] == "outbox-1"  # = outbox_id, NOT aggregate_id
    # FD-19/052: a description-ONLY edit (name/aliases unchanged) is no longer
    # mis-classed as `boundary` (a rename signal) — it's `other` (the description
    # change moves description_hash, not content_hash).
    assert p[P_DIFF_CLASS] == "other"
    # …AND the description change IS still recorded (separate hash, the point of
    # 052 vs simply dropping short_description): both hashes present + differ.
    assert p[P_BEFORE_DESC_HASH] and p[P_AFTER_DESC_HASH]
    assert p[P_BEFORE_DESC_HASH] != p[P_AFTER_DESC_HASH]
    assert p[P_USER_ID] is not None  # owner == actor (today)


async def test_glossary_pipeline_event_not_persisted():
    pool = FakePool()
    ev = _glossary_event(outbox_id="outbox-2", actor_type="pipeline",
                         after={"name": "X", "kind": "person", "aliases": [], "short_description": ""})
    await handle_glossary_entity_updated(ev, pool=pool)
    assert pool.calls == []  # pipeline writes are the original output, not corrections


async def test_empty_outbox_id_raises_not_silent_insert():
    # R3-W1: an empty dedup key must fail loud (→ DLQ), never INSERT with "".
    pool = FakePool()
    ev = _glossary_event(outbox_id="",
                         after={"name": "X", "kind": "person", "aliases": [], "short_description": ""})
    with pytest.raises(ValueError):
        await handle_glossary_entity_updated(ev, pool=pool)
    assert pool.calls == []


async def test_two_edits_same_target_distinct_outbox_id_yield_two_inserts():
    # F2 regression-lock: two edits of the SAME entity (same aggregate_id /
    # glossary_entity_id) but different outbox_id must produce TWO rows — proves
    # we key dedup on outbox_id, NOT the reused aggregate_id.
    pool = FakePool()
    gid = str(uuid.uuid4())
    snap = {"name": "A", "kind": "person", "aliases": [], "short_description": "v1"}
    ev1 = _glossary_event(outbox_id="outbox-A", glossary_id=gid, after=snap)
    ev2 = _glossary_event(outbox_id="outbox-B", glossary_id=gid,
                          after={**snap, "short_description": "v2"})
    await handle_glossary_entity_updated(ev1, pool=pool)
    await handle_glossary_entity_updated(ev2, pool=pool)

    assert len(pool.calls) == 2
    oid1, oid2 = pool.calls[0][P_ORIGIN_EVENT_ID], pool.calls[1][P_ORIGIN_EVENT_ID]
    assert oid1 == "outbox-A" and oid2 == "outbox-B"
    assert oid1 != oid2
    # And the dedup key is NOT the (reused) target id:
    assert pool.calls[0][P_ORIGIN_EVENT_ID] != pool.calls[0][P_TARGET_ID]


async def test_knowledge_corrected_maps_payload_owner():
    pool = FakePool()
    owner = str(uuid.uuid4())
    ev = EventData(
        stream="loreweave:events:knowledge",
        message_id="1-0",
        event_type="knowledge.relation_corrected",
        aggregate_id="rel-123",
        payload={
            "user_id": owner,
            "target_type": "relation",
            "target_id": "rel-123",
            "op": "invalidate",
            "before": {"subject_id": "s", "object_id": "o", "predicate": "ally_of"},
            "after": None,
            "actor_type": "user",
            "actor_id": owner,
            "emitted_at": "2026-05-31T00:00:00Z",
        },
        source="knowledge",
        raw={},
        outbox_id="k-outbox-1",
    )
    await handle_knowledge_corrected(ev, pool=pool)

    assert len(pool.calls) == 1
    p = pool.calls[0]
    assert p[P_TARGET_TYPE] == "relation"
    assert p[P_OP] == "invalidate"
    assert p[P_DIFF_CLASS] == "spurious-drop"  # after absent
    assert p[P_ORIGIN_SERVICE] == "knowledge"
    assert p[P_ORIGIN_EVENT_ID] == "k-outbox-1"
    assert str(p[P_USER_ID]) == owner
