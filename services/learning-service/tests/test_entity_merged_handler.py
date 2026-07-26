"""`glossary.entity_merged` handler — merge→correction mapping, owner guard, dedup.

D-LEARN-ENTITY-MERGED: a user merging duplicate entities is a resolution-quality
correction. The event carries only winner/loser ids (no name/kind snapshot), so the
correction is encoded structurally (before = loser ref, after = winner ref, op =
merge/split ⇒ diff_class "merge"). Same R3-W1 discipline as the sibling glossary
handlers: empty outbox_id → raise; missing owner → raise (→ DLQ).
"""

import uuid

import pytest

from app.events.dispatcher import EventData
from app.events.handlers import handle_glossary_entity_merged

# Positional param index map for the INSERT in _persist_correction (0-based),
# identical to test_handlers.py.
P_USER_ID = 0
P_BOOK_ID = 2
P_TARGET_TYPE = 3
P_TARGET_ID = 4
P_OP = 5
P_BEFORE_STRUCTURAL = 6
P_AFTER_STRUCTURAL = 7
P_DIFF_CLASS = 12
P_ACTOR_TYPE = 16
P_ACTOR_ID = 17
P_ORIGIN_SERVICE = 18
P_ORIGIN_EVENT_ID = 19
P_ORIGIN_EVENT_TYPE = 20


class FakePool:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, *params):
        self.calls.append(params)


def _merged_event(*, outbox_id, op="merged", actor_id=None, winner=None, loser=None,
                  book_id=None):
    winner = winner or str(uuid.uuid4())
    loser = loser or str(uuid.uuid4())
    payload = {
        "book_id": book_id or str(uuid.uuid4()),
        "winner_glossary_id": winner,
        "loser_glossary_id": loser,
        "op": op,
        "emitted_at": "2026-07-02T00:00:00Z",
    }
    if actor_id is not None:
        payload["actor_id"] = actor_id  # producer gap: real payload omits this today
    return EventData(
        stream="loreweave:events:glossary",
        message_id="1-0",
        event_type="glossary.entity_merged",
        aggregate_id=winner,  # glossary emits aggregate_id = winner
        payload=payload,
        source="glossary",
        raw={},
        outbox_id=outbox_id,
    )


async def test_merge_persisted_with_structural_winner_loser_mapping():
    pool = FakePool()
    owner = str(uuid.uuid4())
    winner, loser = str(uuid.uuid4()), str(uuid.uuid4())
    ev = _merged_event(outbox_id="merge-1", actor_id=owner, winner=winner, loser=loser)
    await handle_glossary_entity_merged(ev, pool=pool)

    assert len(pool.calls) == 1
    p = pool.calls[0]
    assert p[P_TARGET_TYPE] == "entity"
    assert p[P_TARGET_ID] == winner  # the surviving canon is the correction target
    assert p[P_OP] == "merge"
    assert p[P_DIFF_CLASS] == "merge"  # derive_diff_class short-circuits on merge op
    assert p[P_ACTOR_TYPE] == "user"
    assert str(p[P_USER_ID]) == owner  # owner == actor (verifyBookOwner)
    assert str(p[P_ACTOR_ID]) == owner
    assert p[P_ORIGIN_SERVICE] == "glossary"
    assert p[P_ORIGIN_EVENT_ID] == "merge-1"  # = outbox_id, NOT aggregate_id
    assert p[P_ORIGIN_EVENT_TYPE] == "glossary.entity_merged"
    # before = absorbed loser ref, after = surviving winner ref (structural jsonb strings)
    assert loser in p[P_BEFORE_STRUCTURAL]
    assert winner in p[P_AFTER_STRUCTURAL]


async def test_unmerge_maps_to_split_still_merge_class():
    pool = FakePool()
    owner = str(uuid.uuid4())
    ev = _merged_event(outbox_id="unmerge-1", op="unmerged", actor_id=owner)
    await handle_glossary_entity_merged(ev, pool=pool)

    p = pool.calls[0]
    assert p[P_OP] == "split"  # codebase-idiomatic un-merge verb (_MERGE_OPS)
    assert p[P_DIFF_CLASS] == "merge"  # split is merge-class in derive_diff_class


async def test_missing_owner_raises_not_silent_insert():
    # Producer-current reality: the entity_merged payload carries no actor_id.
    # With no attributable owner the merge cannot be persisted per-tenant → raise → DLQ.
    pool = FakePool()
    ev = _merged_event(outbox_id="merge-noowner")  # no actor_id
    with pytest.raises(ValueError):
        await handle_glossary_entity_merged(ev, pool=pool)
    assert pool.calls == []


async def test_empty_outbox_id_raises_not_silent_insert():
    # R3-W1: an empty dedup key must fail loud (→ DLQ), never INSERT with "".
    pool = FakePool()
    ev = _merged_event(outbox_id="", actor_id=str(uuid.uuid4()))
    with pytest.raises(ValueError):
        await handle_glossary_entity_merged(ev, pool=pool)
    assert pool.calls == []


async def test_two_merges_distinct_outbox_id_yield_two_inserts():
    # Idempotency keys on outbox_id, not the (winner) aggregate_id.
    pool = FakePool()
    owner = str(uuid.uuid4())
    winner = str(uuid.uuid4())
    ev1 = _merged_event(outbox_id="merge-A", actor_id=owner, winner=winner)
    ev2 = _merged_event(outbox_id="merge-B", actor_id=owner, winner=winner)
    await handle_glossary_entity_merged(ev1, pool=pool)
    await handle_glossary_entity_merged(ev2, pool=pool)

    assert len(pool.calls) == 2
    oid1, oid2 = pool.calls[0][P_ORIGIN_EVENT_ID], pool.calls[1][P_ORIGIN_EVENT_ID]
    assert oid1 == "merge-A" and oid2 == "merge-B"
    assert pool.calls[0][P_ORIGIN_EVENT_ID] != pool.calls[0][P_TARGET_ID]
