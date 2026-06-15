"""Unified Job Control Plane P1 — `loreweave_jobs.contract` round-trip + invariants."""

from __future__ import annotations

from loreweave_jobs import ControlCap, JobEvent, JobRecord, JobStatus
from loreweave_jobs.contract import (
    JOBS_AGGREGATE_TYPE,
    JOBS_STREAM,
    TERMINAL,
)


def test_jobstatus_terminal_set():
    assert JobStatus.is_terminal(JobStatus.COMPLETED)
    assert JobStatus.is_terminal(JobStatus.FAILED)
    assert JobStatus.is_terminal(JobStatus.CANCELLED)
    assert JobStatus.is_terminal("completed")  # accepts raw string
    assert not JobStatus.is_terminal(JobStatus.RUNNING)
    assert not JobStatus.is_terminal(JobStatus.PAUSED)
    assert not JobStatus.is_terminal(JobStatus.CANCELLING)
    assert TERMINAL == {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}


def test_stream_routing_constants_agree():
    # The relay routes loreweave:events:<aggregate_type>; the constants must agree so a
    # row written with JOBS_AGGREGATE_TYPE lands on JOBS_STREAM.
    assert JOBS_STREAM == f"loreweave:events:{JOBS_AGGREGATE_TYPE}"


def test_jobrecord_roundtrip_full():
    rec = JobRecord(
        service="knowledge",
        job_id="11111111-1111-1111-1111-111111111111",
        owner_user_id="22222222-2222-2222-2222-222222222222",
        kind="extraction",
        status=JobStatus.RUNNING,
        parent_job_id="33333333-3333-3333-3333-333333333333",
        detail_status="summarizing",
        progress={"done": 3, "total": 40},
        control_caps=[ControlCap.PAUSE, ControlCap.CANCEL],
        title="万古神帝 — knowledge extract ch 1-40",
        error=None,
        created_at="2026-06-15T00:00:00+00:00",
        updated_at="2026-06-15T00:01:00+00:00",
    )
    d = rec.to_dict()
    # enums serialised to their string values (JSON-safe)
    assert d["status"] == "running"
    assert d["control_caps"] == ["pause", "cancel"]
    assert d["progress"] == {"done": 3, "total": 40}
    back = JobRecord.from_dict(d)
    assert back == rec


def test_jobrecord_nullable_defaults():
    rec = JobRecord(
        service="video-gen",
        job_id="44444444-4444-4444-4444-444444444444",
        owner_user_id="55555555-5555-5555-5555-555555555555",
        kind="video_gen",
        status=JobStatus.PENDING,
    )
    d = rec.to_dict()
    assert d["parent_job_id"] is None
    assert d["progress"] is None          # single-call job — null-safe for the GUI
    assert d["control_caps"] == []
    assert JobRecord.from_dict(d) == rec


def test_jobrecord_has_no_provider_job_id():
    # H2 — control is domain-level; the record never addresses a provider job.
    rec = JobRecord(
        service="x", job_id="6", owner_user_id="7", kind="k", status=JobStatus.RUNNING,
    )
    assert "provider_job_id" not in rec.to_dict()


def test_jobevent_payload_roundtrip():
    ev = JobEvent(
        service="translation",
        job_id="88888888-8888-8888-8888-888888888888",
        owner_user_id="99999999-9999-9999-9999-999999999999",
        kind="translation",
        status=JobStatus.FAILED,
        error={"code": "timeout", "message": "provider timed out"},
        progress={"done": 1, "total": 2},
        occurred_at="2026-06-15T00:02:00+00:00",
    )
    payload = ev.to_payload()
    assert payload["status"] == "failed"
    assert payload["error"] == {"code": "timeout", "message": "provider timed out"}
    assert JobEvent.from_payload(payload) == ev
