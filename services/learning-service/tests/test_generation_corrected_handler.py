"""V1 slice 2 — composition.generation_corrected handler.

Maps the co-write human-gate event to a `corrections` row (target_type=
generation, op=kind, origin_service=composition). Locks: the H2 gold-kind
filter (accept/unknown → no row), the structural preference encoding, the
R3-W1 empty-outbox-id guard, the owner requirement, and outbox_id dedup keying.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.events.dispatcher import EventData
from app.events.handlers import handle_generation_corrected

# Param index map for the INSERT in _persist_correction (0-based positional).
P_USER_ID = 0
P_PROJECT_ID = 1
P_BOOK_ID = 2
P_TARGET_TYPE = 3
P_TARGET_ID = 4
P_OP = 5
P_BEFORE_STRUCTURAL = 6
P_AFTER_STRUCTURAL = 7
P_DIFF_CLASS = 10
P_ACTOR_TYPE = 14
P_ORIGIN_SERVICE = 16
P_ORIGIN_EVENT_ID = 17


class FakePool:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, *params):
        self.calls.append(params)


def _corr_event(*, outbox_id="ob-1", kind="pick_different", user_id=None,
                job_id=None, project_id=None, book_id=None, winner_index=0,
                chosen_candidate_index=1, candidate_count=3, changed_blocks=None,
                has_guidance=False, has_raw_prose=False, regenerated_to_job_id=None):
    job = job_id or str(uuid.uuid4())
    return EventData(
        stream="loreweave:events:composition",
        message_id="1-0",
        event_type="composition.generation_corrected",
        aggregate_id=project_id or str(uuid.uuid4()),
        payload={
            "correction_id": str(uuid.uuid4()),
            "job_id": job,
            "project_id": project_id or str(uuid.uuid4()),
            "user_id": user_id if user_id is not None else str(uuid.uuid4()),
            "book_id": book_id or str(uuid.uuid4()),
            "kind": kind,
            "winner_index": winner_index,
            "chosen_candidate_index": chosen_candidate_index,
            "candidate_count": candidate_count,
            "changed_blocks": changed_blocks,
            "has_guidance": has_guidance,
            "has_raw_prose": has_raw_prose,
            "regenerated_to_job_id": regenerated_to_job_id,
        },
        source="composition",
        raw={},
        outbox_id=outbox_id,
    )


async def test_pick_different_persists_preference():
    pool = FakePool()
    owner = str(uuid.uuid4())
    job = str(uuid.uuid4())
    ev = _corr_event(outbox_id="ob-pd", kind="pick_different", user_id=owner,
                     job_id=job, winner_index=0, chosen_candidate_index=2, candidate_count=3)
    await handle_generation_corrected(ev, pool=pool)
    assert len(pool.calls) == 1
    p = pool.calls[0]
    assert p[P_TARGET_TYPE] == "generation"
    assert p[P_TARGET_ID] == job
    assert p[P_OP] == "pick_different"
    assert p[P_ACTOR_TYPE] == "user"
    assert p[P_ORIGIN_SERVICE] == "composition"
    assert p[P_ORIGIN_EVENT_ID] == "ob-pd"  # = outbox_id (dedup key), not aggregate_id
    assert str(p[P_USER_ID]) == owner
    # the preference shape: before=winner(i), after=chosen(j) — the direct, non-
    # circular reranker correction
    before = json.loads(p[P_BEFORE_STRUCTURAL])
    after = json.loads(p[P_AFTER_STRUCTURAL])
    assert before == {"role": "winner", "index": 0}
    assert after["role"] == "chosen" and after["index"] == 2 and after["candidate_count"] == 3


async def test_edit_records_change_magnitude():
    pool = FakePool()
    ev = _corr_event(outbox_id="ob-edit", kind="edit", winner_index=0,
                     changed_blocks=4, has_guidance=True)
    await handle_generation_corrected(ev, pool=pool)
    p = pool.calls[0]
    assert p[P_OP] == "edit"
    after = json.loads(p[P_AFTER_STRUCTURAL])
    assert after["changed_blocks"] == 4 and after["has_guidance"] is True


async def test_reject_has_no_after_and_drops():
    pool = FakePool()
    ev = _corr_event(outbox_id="ob-rej", kind="reject", winner_index=1)
    await handle_generation_corrected(ev, pool=pool)
    p = pool.calls[0]
    assert p[P_OP] == "reject"
    assert p[P_AFTER_STRUCTURAL] is None  # whole generation dropped
    assert p[P_DIFF_CLASS] == "spurious-drop"  # before present, after absent


async def test_accept_kind_is_not_persisted():
    # H2: accept-as-is must never become gold (self-reinforcement). composition
    # never emits it, but the handler defends: ack, no row.
    pool = FakePool()
    await handle_generation_corrected(_corr_event(kind="accept"), pool=pool)
    assert pool.calls == []


async def test_unknown_kind_is_not_persisted():
    pool = FakePool()
    await handle_generation_corrected(_corr_event(kind="frobnicate"), pool=pool)
    assert pool.calls == []


async def test_empty_outbox_id_raises_no_write():
    # R3-W1: empty dedup key → fail loud (DLQ), never INSERT with "".
    pool = FakePool()
    with pytest.raises(ValueError):
        await handle_generation_corrected(_corr_event(outbox_id="", kind="reject"), pool=pool)
    assert pool.calls == []


async def test_missing_user_id_raises():
    pool = FakePool()
    with pytest.raises(ValueError):
        await handle_generation_corrected(_corr_event(user_id="", kind="reject"), pool=pool)
    assert pool.calls == []


async def test_same_job_distinct_outbox_id_yields_two_rows():
    # dedup is keyed on outbox_id, NOT the job/aggregate — two corrections on the
    # same job must both persist.
    pool = FakePool()
    job = str(uuid.uuid4())
    await handle_generation_corrected(
        _corr_event(outbox_id="ob-1", kind="edit", job_id=job, changed_blocks=1), pool=pool)
    await handle_generation_corrected(
        _corr_event(outbox_id="ob-2", kind="reject", job_id=job), pool=pool)
    assert len(pool.calls) == 2
    assert pool.calls[0][P_ORIGIN_EVENT_ID] == "ob-1"
    assert pool.calls[1][P_ORIGIN_EVENT_ID] == "ob-2"


def test_handler_registered_in_dispatcher():
    from app.main import build_dispatcher
    d = build_dispatcher()
    assert "composition.generation_corrected" in d.registered_types
