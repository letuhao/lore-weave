"""LLM re-arch Phase 3 M5 — decoupled video-gen (job-row + terminal-event).

Covers the flag-ON submit/poll endpoints and the worker's ``complete_job`` /
``sweep_once`` terminal-folding logic. The repo + SDK are faked (no live PG /
gateway), mirroring how composition-service unit-tested its worker ops; the
repo's own SQL/CAS is exercised by the live-smoke (D-M5-VIDEOGEN-LIVE-SMOKE).
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.db.repository import VideoGenJob

_MODEL_REF = "019d5e3c-1234-7890-abcd-1344e148bf7c"


def _job(**over) -> VideoGenJob:
    base = dict(
        id=uuid4(),
        user_id=uuid4(),
        provider_job_id=uuid4(),
        status="pending",
        request_json={"prompt": "a cat", "model_source": "user_model", "model_ref": _MODEL_REF},
        video_url=None,
        size_bytes=None,
        content_type=None,
        error_json=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    base.update(over)
    return VideoGenJob(**base)


class _FakeRepo:
    """In-memory stand-in for VideoGenJobsRepo (records calls + CAS state)."""

    def __init__(self, *, created=None, by_pjid=None):
        self._created = created
        self._by_pjid = by_pjid
        self.completed: dict = {}
        self.failed: dict = {}
        self.marked_running = []
        self.stuck: list = []

    async def create(self, *, user_id, provider_job_id, request_json):
        self.create_args = dict(user_id=user_id, provider_job_id=provider_job_id, request_json=request_json)
        return self._created

    async def get(self, user_id, job_id):
        if self._created and self._created.user_id == user_id and self._created.id == job_id:
            return self._created
        return self._by_pjid if (self._by_pjid and self._by_pjid.id == job_id and self._by_pjid.user_id == user_id) else None

    async def get_by_provider_job_id(self, pjid):
        return self._by_pjid if self._by_pjid and self._by_pjid.provider_job_id == pjid else None

    async def mark_running(self, job_id):
        self.marked_running.append(job_id)

    async def complete(self, job_id, *, video_url, size_bytes, content_type):
        self.completed = dict(job_id=job_id, video_url=video_url, size_bytes=size_bytes, content_type=content_type)
        return True

    async def fail(self, job_id, *, status, error):
        self.failed = dict(job_id=job_id, status=status, error=error)
        return True

    async def list_stuck(self, *, timeout_secs, batch):
        return self.stuck


# ── submit endpoint (flag ON) ─────────────────────────────────────────────────


def test_submit_decoupled_returns_202_with_job_id(client, jwt_for_user, monkeypatch):
    """Flag ON: POST /generate submits the gateway job (not generate_video),
    persists a pending row, returns 202 {job_id, status:pending}."""
    from app.routers import generate as gen

    created = _job(user_id=UUID(int=1), status="pending")
    repo = _FakeRepo(created=created)

    mock_client = MagicMock()
    mock_client.submit_job = AsyncMock(return_value=SimpleNamespace(job_id=created.provider_job_id))
    mock_client.aclose = AsyncMock()

    monkeypatch.setattr(gen.settings, "video_gen_decouple_enabled", True)
    monkeypatch.setattr(gen, "get_pool", lambda: object())
    monkeypatch.setattr(gen, "VideoGenJobsRepo", lambda _pool: repo)
    monkeypatch.setattr(gen, "Client", MagicMock(return_value=mock_client))

    resp = client.post(
        "/v1/video-gen/generate",
        json={"prompt": "a cat", "model_source": "user_model", "model_ref": _MODEL_REF,
              "duration_seconds": 5, "aspect_ratio": "9:16"},
        headers={"Authorization": f"Bearer {jwt_for_user('00000000-0000-0000-0000-000000000001')}"},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["job_id"] == str(created.id)
    assert body["video_url"] is None
    # submit_job got operation=video_gen with the aspect→size mapping
    sj = mock_client.submit_job.await_args.args[0]
    assert sj.operation == "video_gen"
    assert sj.input["size"] == "1080x1920"  # 9:16
    # the decoupled path submits (fire-and-forget) — exactly one submit, no wait.
    mock_client.submit_job.assert_awaited_once()
    assert repo.create_args["provider_job_id"] == created.provider_job_id


def test_submit_decoupled_does_not_block_or_download(client, jwt_for_user, monkeypatch):
    """The decoupled submit must NOT call download_and_store/record_usage —
    those move to the worker's terminal completion."""
    from app.routers import generate as gen

    created = _job(user_id=UUID(int=2))
    repo = _FakeRepo(created=created)
    mock_client = MagicMock()
    mock_client.submit_job = AsyncMock(return_value=SimpleNamespace(job_id=created.provider_job_id))
    mock_client.aclose = AsyncMock()

    monkeypatch.setattr(gen.settings, "video_gen_decouple_enabled", True)
    monkeypatch.setattr(gen, "get_pool", lambda: object())
    monkeypatch.setattr(gen, "VideoGenJobsRepo", lambda _pool: repo)
    monkeypatch.setattr(gen, "Client", MagicMock(return_value=mock_client))
    dl = AsyncMock()
    bill = AsyncMock()
    monkeypatch.setattr(gen, "download_and_store", dl)
    monkeypatch.setattr(gen, "record_usage", bill)

    resp = client.post(
        "/v1/video-gen/generate",
        json={"prompt": "a cat", "model_source": "user_model", "model_ref": _MODEL_REF,
              "duration_seconds": 5, "aspect_ratio": "16:9"},
        headers={"Authorization": f"Bearer {jwt_for_user('00000000-0000-0000-0000-000000000002')}"},
    )
    assert resp.status_code == 202, resp.text
    dl.assert_not_awaited()
    bill.assert_not_awaited()


# ── poll endpoint ─────────────────────────────────────────────────────────────


def test_poll_completed_job_maps_video_url(client, jwt_for_user, monkeypatch):
    from app.routers import generate as gen

    uid = UUID("00000000-0000-0000-0000-000000000003")
    done = _job(user_id=uid, status="completed", video_url="http://minio/v.mp4",
                size_bytes=2048, content_type="video/mp4")
    repo = _FakeRepo(created=done)
    monkeypatch.setattr(gen.settings, "video_gen_decouple_enabled", True)
    monkeypatch.setattr(gen, "get_pool", lambda: object())
    monkeypatch.setattr(gen, "VideoGenJobsRepo", lambda _pool: repo)

    resp = client.get(
        f"/v1/video-gen/jobs/{done.id}",
        headers={"Authorization": f"Bearer {jwt_for_user(str(uid))}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["video_url"] == "http://minio/v.mp4"
    assert body["size_bytes"] == 2048
    assert body["model"] == _MODEL_REF


def test_poll_missing_job_returns_404(client, jwt_for_user, monkeypatch):
    from app.routers import generate as gen
    repo = _FakeRepo()
    monkeypatch.setattr(gen.settings, "video_gen_decouple_enabled", True)
    monkeypatch.setattr(gen, "get_pool", lambda: object())
    monkeypatch.setattr(gen, "VideoGenJobsRepo", lambda _pool: repo)
    resp = client.get(
        f"/v1/video-gen/jobs/{uuid4()}",
        headers={"Authorization": f"Bearer {jwt_for_user('00000000-0000-0000-0000-000000000009')}"},
    )
    assert resp.status_code == 404, resp.text


def test_poll_flag_off_returns_404(client, jwt_for_user, monkeypatch):
    """Flag OFF: no rows exist + the pool isn't initialised → 404, never a 500."""
    from app.routers import generate as gen
    monkeypatch.setattr(gen.settings, "video_gen_decouple_enabled", False)
    resp = client.get(
        f"/v1/video-gen/jobs/{uuid4()}",
        headers={"Authorization": f"Bearer {jwt_for_user('00000000-0000-0000-0000-000000000009')}"},
    )
    assert resp.status_code == 404, resp.text


# ── consumer complete_job ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_complete_job_not_ours_skips():
    from app.worker.consumer import complete_job
    repo = _FakeRepo(by_pjid=None)
    sdk = MagicMock()
    sdk.get_job = AsyncMock()
    with patch("app.worker.consumer.VideoGenJobsRepo", lambda _pool: repo):
        out = await complete_job(object(), sdk, provider_job_id=str(uuid4()), owner_user_id=None)
    assert out == "not_ours"
    sdk.get_job.assert_not_awaited()  # never touched the gateway for a foreign job


@pytest.mark.asyncio
async def test_complete_job_foreign_operation_skips_without_db():
    """A chat/judge/translation terminal on the shared stream is dropped via the
    operation pre-filter — no get_by_provider_job_id DB round-trip."""
    from app.worker.consumer import complete_job
    repo = _FakeRepo(by_pjid=_job())
    repo.get_by_provider_job_id = AsyncMock(side_effect=AssertionError("should not query DB"))
    sdk = MagicMock(); sdk.get_job = AsyncMock()
    with patch("app.worker.consumer.VideoGenJobsRepo", lambda _pool: repo):
        out = await complete_job(object(), sdk, provider_job_id=str(uuid4()),
                                 owner_user_id=None, operation="chat")
    assert out == "not_ours"
    sdk.get_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_complete_job_already_terminal_is_idempotent():
    from app.worker.consumer import complete_job
    row = _job(status="completed")
    repo = _FakeRepo(by_pjid=row)
    sdk = MagicMock(); sdk.get_job = AsyncMock()
    with patch("app.worker.consumer.VideoGenJobsRepo", lambda _pool: repo):
        out = await complete_job(object(), sdk, provider_job_id=str(row.provider_job_id), owner_user_id=None)
    assert out == "already_terminal"
    sdk.get_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_complete_job_downloads_stores_and_bills():
    from app.worker import consumer as cons
    row = _job(status="pending")
    repo = _FakeRepo(by_pjid=row)
    sdk = MagicMock()
    sdk.get_job = AsyncMock(return_value=SimpleNamespace(
        status="completed",
        result={"created": 1, "data": [{"url": "https://cdn/v.mp4"}]},
        error=None,
    ))
    dl = AsyncMock(return_value=("http://minio/v.mp4", 4096, "video/mp4"))
    bill = AsyncMock()
    with patch.object(cons, "VideoGenJobsRepo", lambda _pool: repo), \
         patch.object(cons, "download_and_store", dl), \
         patch.object(cons, "record_usage", bill):
        out = await cons.complete_job(object(), sdk, provider_job_id=str(row.provider_job_id),
                                      owner_user_id=str(row.user_id))
    assert out == "completed"
    assert repo.marked_running == [row.id]
    assert repo.completed["video_url"] == "http://minio/v.mp4"
    assert repo.completed["size_bytes"] == 4096
    bill.assert_awaited_once()  # billed on the winning CAS


@pytest.mark.asyncio
async def test_complete_job_no_url_marks_failed():
    from app.worker import consumer as cons
    row = _job(status="pending")
    repo = _FakeRepo(by_pjid=row)
    sdk = MagicMock()
    sdk.get_job = AsyncMock(return_value=SimpleNamespace(
        status="completed", result={"created": 1, "data": [{"url": None}]}, error=None,
    ))
    with patch.object(cons, "VideoGenJobsRepo", lambda _pool: repo), \
         patch.object(cons, "download_and_store", AsyncMock()) as dl:
        out = await cons.complete_job(object(), sdk, provider_job_id=str(row.provider_job_id), owner_user_id=None)
    assert out == "no_url"
    assert repo.failed["status"] == "failed"
    dl.assert_not_awaited()


@pytest.mark.asyncio
async def test_complete_job_failed_records_error():
    from app.worker import consumer as cons
    row = _job(status="running")
    repo = _FakeRepo(by_pjid=row)
    sdk = MagicMock()
    sdk.get_job = AsyncMock(return_value=SimpleNamespace(
        status="failed", result=None,
        error=SimpleNamespace(code="upstream_error", message="model exploded"),
    ))
    with patch.object(cons, "VideoGenJobsRepo", lambda _pool: repo):
        out = await cons.complete_job(object(), sdk, provider_job_id=str(row.provider_job_id), owner_user_id=None)
    assert out == "failed"
    assert repo.failed["status"] == "failed"
    assert repo.failed["error"]["code"] == "upstream_error"


@pytest.mark.asyncio
async def test_complete_job_cancelled():
    from app.worker import consumer as cons
    row = _job(status="running")
    repo = _FakeRepo(by_pjid=row)
    sdk = MagicMock()
    sdk.get_job = AsyncMock(return_value=SimpleNamespace(status="cancelled", result=None, error=None))
    with patch.object(cons, "VideoGenJobsRepo", lambda _pool: repo):
        out = await cons.complete_job(object(), sdk, provider_job_id=str(row.provider_job_id), owner_user_id=None)
    assert out == "cancelled"
    assert repo.failed["status"] == "cancelled"


# ── sweeper ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sweep_once_redrives_terminal_only():
    """A stuck row whose gateway job is terminal is re-driven; a still-running
    job (slow ≠ stuck) is skipped."""
    from app.worker import consumer as cons
    stuck_done = _job(status="running")
    stuck_slow = _job(status="running")
    repo = _FakeRepo()
    repo.stuck = [stuck_done, stuck_slow]

    def _get_job(pjid, *, user_id=None):
        terminal = str(stuck_done.provider_job_id)
        return SimpleNamespace(
            status="completed" if pjid == terminal else "running",
            is_terminal=lambda: pjid == terminal,
            result={"created": 1, "data": [{"url": "https://cdn/v.mp4"}]},
            error=None,
        )
    sdk = MagicMock()
    sdk.get_job = AsyncMock(side_effect=lambda pjid, user_id=None: _get_job(pjid, user_id=user_id))

    redrive_calls = []

    async def _fake_complete(pool, _sdk, *, provider_job_id, owner_user_id):
        redrive_calls.append(provider_job_id)
        return "completed"

    with patch.object(cons, "VideoGenJobsRepo", lambda _pool: repo), \
         patch.object(cons, "complete_job", _fake_complete):
        n = await cons.sweep_once(object(), sdk, timeout_s=1800, batch=20)
    assert n == 1
    assert redrive_calls == [str(stuck_done.provider_job_id)]
