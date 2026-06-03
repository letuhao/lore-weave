"""Redis Streams job-event contract tests (RAID C14).

Exercises the :class:`JobEventEmitter` against a FAKE Redis producer (the stream
contract is exercised without a real Redis):
  * each lifecycle event serializes to a flat string field map (XADD-safe);
  * the producer is IDEMPOTENT — a re-emit of the same (job, stage[, gap]) is a
    no-op (a crash-resume does not double-publish proposal_created);
  * a down Redis (xadd raises) NEVER fails the emit (best-effort, non-fatal);
  * seeding seen_keys (crash-resume) suppresses already-published events.
"""

from __future__ import annotations

import json

import pytest

from app.jobs.events import (
    LORE_ENRICHMENT_STREAM,
    STREAM_MAXLEN,
    JobEventEmitter,
    JobEventType,
)

pytestmark = pytest.mark.asyncio


class _FakeProducer:
    """Captures xadd calls; the stream contract is asserted on these."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str], int | None]] = []

    async def xadd(self, stream, fields, *, maxlen=None):
        self.calls.append((stream, fields, maxlen))
        return f"0-{len(self.calls)}"


class _BrokenProducer:
    """A down Redis — every xadd raises (the emitter must swallow it)."""

    async def xadd(self, stream, fields, *, maxlen=None):
        raise ConnectionError("redis down")


def _emitter(producer=None, *, seen=None) -> JobEventEmitter:
    return JobEventEmitter(
        producer,
        job_id="job-1",
        project_id="proj-1",
        user_id="user-1",
        seen_keys=seen,
    )


async def test_started_event_serializes_to_string_field_map():
    fake = _FakeProducer()
    em = _emitter(fake)
    ev = await em.emit(JobEventType.STARTED, data={"gap_count": 4, "cap": 100.0})
    assert ev is not None
    stream, fields, maxlen = fake.calls[0]
    assert stream == LORE_ENRICHMENT_STREAM
    assert maxlen == STREAM_MAXLEN
    # all field values are strings (XADD requires a flat string map).
    assert all(isinstance(v, str) for v in fields.values())
    assert fields["event_type"] == JobEventType.STARTED.value
    assert fields["job_id"] == "job-1"
    # nested data round-trips through the JSON-encoded `data` field.
    assert json.loads(fields["data"]) == {"gap_count": 4, "cap": 100.0}


async def test_cjk_payload_round_trips_without_mojibake():
    fake = _FakeProducer()
    em = _emitter(fake)
    await em.emit(
        JobEventType.PROPOSAL_CREATED,
        gap_ref="蓬萊",
        data={"canonical_name": "蓬萊"},
    )
    _stream, fields, _maxlen = fake.calls[0]
    assert "蓬萊" in fields["data"]  # ensure_ascii=False — genuine UTF-8
    assert json.loads(fields["data"])["canonical_name"] == "蓬萊"


async def test_idempotent_same_stage_not_double_emitted():
    fake = _FakeProducer()
    em = _emitter(fake)
    first = await em.emit(JobEventType.PROPOSAL_CREATED, gap_ref="蓬萊")
    dup = await em.emit(JobEventType.PROPOSAL_CREATED, gap_ref="蓬萊")
    assert first is not None
    assert dup is None  # idempotent: same (job, type, gap) → skipped
    assert len(fake.calls) == 1  # only one XADD reached the stream


async def test_per_gap_events_are_distinct():
    fake = _FakeProducer()
    em = _emitter(fake)
    a = await em.emit(JobEventType.PROPOSAL_CREATED, gap_ref="蓬萊")
    b = await em.emit(JobEventType.PROPOSAL_CREATED, gap_ref="玉虛宮")
    assert a is not None and b is not None
    assert len(fake.calls) == 2
    assert a.dedupe_key != b.dedupe_key


async def test_seeded_seen_keys_suppress_resume_duplicate():
    fake = _FakeProducer()
    # crash-resume: the proposal_created for 蓬萊 was already published last run.
    seed_key = "job-1:lore_enrichment.job.proposal_created:蓬萊"
    em = _emitter(fake, seen={seed_key})
    skipped = await em.emit(JobEventType.PROPOSAL_CREATED, gap_ref="蓬萊")
    assert skipped is None
    assert fake.calls == []  # nothing re-published


async def test_down_redis_is_non_fatal():
    em = _emitter(_BrokenProducer())
    ev = await em.emit(JobEventType.COMPLETED, data={"proposals_total": 3})
    # The emit did NOT raise; it recorded the failure but returned the event.
    assert ev is not None
    assert em.emit_failures == 1
    assert len(em.emitted) == 1


async def test_no_producer_is_a_noop_but_records():
    em = _emitter(None)
    ev = await em.emit(JobEventType.STARTED)
    assert ev is not None
    assert em.emit_failures == 0
    assert em.emitted[0].event_type is JobEventType.STARTED
