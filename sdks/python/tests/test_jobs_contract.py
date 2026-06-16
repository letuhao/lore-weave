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


def test_jobevent_p4_usage_fields_roundtrip():
    # P4: model (resolved NAME) + cost_usd + tokens + dynamic params survive the
    # payload round-trip the projection consumer + reconcile sweep both rely on.
    ev = JobEvent(
        service="knowledge",
        job_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        owner_user_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        kind="extraction",
        status=JobStatus.RUNNING,
        model="qwen2.5-7b-instruct",
        cost_usd=2.74,
        tokens_in=980142,
        tokens_out=180553,
        params={"model": "qwen2.5-7b-instruct", "concurrency": 4, "scope": "ch 1-4000"},
        occurred_at="2026-06-15T00:03:00+00:00",
    )
    payload = ev.to_payload()
    assert payload["model"] == "qwen2.5-7b-instruct"
    assert payload["cost_usd"] == 2.74
    assert payload["tokens_in"] == 980142 and payload["tokens_out"] == 180553
    assert payload["params"]["concurrency"] == 4
    assert JobEvent.from_payload(payload) == ev


def test_jobevent_p4_fields_default_none():
    # An older producer that never sets the P4 fields → all None, payload null-safe.
    ev = JobEvent(
        service="video_gen", job_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
        owner_user_id="dddddddd-dddd-dddd-dddd-dddddddddddd",
        kind="video_gen", status=JobStatus.PENDING,
    )
    payload = ev.to_payload()
    assert payload["model"] is None and payload["cost_usd"] is None
    assert payload["tokens_in"] is None and payload["tokens_out"] is None
    assert payload["params"] is None
    assert JobEvent.from_payload(payload) == ev


def test_jobrecord_p4_usage_fields_roundtrip():
    rec = JobRecord(
        service="knowledge", job_id="1", owner_user_id="2", kind="extraction",
        status=JobStatus.RUNNING, model="bge-m3", cost_usd=0.21,
        tokens_in=40000, tokens_out=22000, params={"effort": "high"},
    )
    d = rec.to_dict()
    assert d["model"] == "bge-m3" and d["cost_usd"] == 0.21
    assert d["params"] == {"effort": "high"}
    assert JobRecord.from_dict(d) == rec
