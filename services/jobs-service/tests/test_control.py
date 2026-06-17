"""Control routing (P3) — owner/caps gate + forward + relay + registry."""

from unittest.mock import AsyncMock, patch

import pytest

from app import control
from tests.conftest import TEST_USER

JID = "22222222-2222-2222-2222-222222222222"


def _job(**over):
    base = {
        "service": "knowledge", "job_id": JID, "owner_user_id": TEST_USER,
        "kind": "extraction", "status": "running", "parent_job_id": None,
        "detail_status": None, "progress": None, "title": None, "error": None,
        "created_at": None, "updated_at": None, "child_count": 0,
    }
    base.update(over)
    return base


# ── router: POST /v1/jobs/{service}/{job_id}/{action} ──────────────────────────
def test_control_unknown_action_400(client):
    r = client.post(f"/v1/jobs/knowledge/{JID}/frobnicate", headers={"Authorization": "Bearer x"})
    assert r.status_code == 400


def test_control_not_found_404(client):
    with patch("app.routers.jobs.store.get_job", new=AsyncMock(return_value=None)):
        r = client.post(f"/v1/jobs/knowledge/{JID}/cancel", headers={"Authorization": "Bearer x"})
    assert r.status_code == 404


def test_control_action_not_in_caps_409(client):
    # a completed job offers no control caps → cancel is 409
    with patch("app.routers.jobs.store.get_job", new=AsyncMock(return_value=_job(status="completed"))):
        r = client.post(f"/v1/jobs/knowledge/{JID}/cancel", headers={"Authorization": "Bearer x"})
    assert r.status_code == 409


def test_control_pause_not_offered_for_single_call_kind_409(client):
    # video_gen running → cancel-only; pause is not a cap → 409
    with patch("app.routers.jobs.store.get_job", new=AsyncMock(return_value=_job(service="video_gen", kind="video_gen"))):
        r = client.post(f"/v1/jobs/video_gen/{JID}/pause", headers={"Authorization": "Bearer x"})
    assert r.status_code == 409


def test_control_forwards_and_relays(client):
    fwd = AsyncMock(return_value=control.ControlResult(200, {"job_id": JID, "status": "cancelled"}))
    with (
        patch("app.routers.jobs.store.get_job", new=AsyncMock(return_value=_job())),
        patch("app.routers.jobs.control.forward_control", new=fwd),
    ):
        r = client.post(f"/v1/jobs/knowledge/{JID}/cancel", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    # owner (verified sub) + service/job/action/kind forwarded (kind drives by-table dispatch)
    args = fwd.await_args.args
    assert args == ("knowledge", JID, "cancel", TEST_USER, "extraction")


def test_control_relays_downstream_409(client):
    fwd = AsyncMock(return_value=control.ControlResult(409, {"detail": "status changed"}))
    with (
        patch("app.routers.jobs.store.get_job", new=AsyncMock(return_value=_job())),
        patch("app.routers.jobs.control.forward_control", new=fwd),
    ):
        r = client.post(f"/v1/jobs/knowledge/{JID}/cancel", headers={"Authorization": "Bearer x"})
    assert r.status_code == 409


# ── forwarder / registry ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_forward_unknown_service_501():
    res = await control.forward_control("nope", JID, "cancel", TEST_USER)
    assert res.status_code == 501


@pytest.mark.asyncio
async def test_supported_services_registered_unregistered_501():
    # P3-1..P3-4: all five owning services wired. campaign is deliberately NOT on this
    # plane (it keeps its own monitor + control) → an unregistered service stays 501 (honest).
    for svc in ("knowledge", "composition", "video_gen", "lore_enrichment", "translation"):
        assert control.is_supported(svc) is True
    assert control.is_supported("campaign") is False
    res = await control.forward_control("campaign", JID, "cancel", TEST_USER)
    assert res.status_code == 501


@pytest.mark.asyncio
async def test_forward_builds_per_service_url(monkeypatch):
    """Each registered service forwards to its OWN internal prefix (no cross-wiring)."""
    seen = {}

    class _Resp:
        status_code = 200
        def json(self): return {"job_id": JID, "status": "cancelled"}

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, **kw):
            seen["url"] = url
            return _Resp()

    monkeypatch.setattr(control.httpx, "AsyncClient", _Client)
    await control.forward_control("composition", JID, "cancel", TEST_USER)
    assert seen["url"].endswith(f"/internal/composition/jobs/{JID}/cancel")
    await control.forward_control("video_gen", JID, "cancel", TEST_USER)
    assert seen["url"].endswith(f"/internal/video_gen/jobs/{JID}/cancel")
    await control.forward_control("lore_enrichment", JID, "pause", TEST_USER)
    assert seen["url"].endswith(f"/internal/lore_enrichment/jobs/{JID}/pause")
    # translation uses a distinct control prefix (avoids the campaign-cancel route collision)
    await control.forward_control("translation", JID, "cancel", TEST_USER)
    assert seen["url"].endswith(f"/internal/translation/job-control/{JID}/cancel")


@pytest.mark.asyncio
async def test_forward_relays_downstream(monkeypatch):
    class _Resp:
        status_code = 200
        def json(self): return {"job_id": JID, "status": "paused"}

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, **kw):
            assert url.endswith(f"/internal/knowledge/jobs/{JID}/pause")
            assert kw["json"] == {"owner_user_id": TEST_USER, "kind": "extraction"}
            assert "X-Internal-Token" in kw["headers"]
            return _Resp()

    monkeypatch.setattr(control.httpx, "AsyncClient", _Client)
    res = await control.forward_control("knowledge", JID, "pause", TEST_USER, "extraction")
    assert res.status_code == 200 and res.body["status"] == "paused"


@pytest.mark.asyncio
async def test_forward_downstream_unreachable_502(monkeypatch):
    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): raise control.httpx.ConnectError("down")

    monkeypatch.setattr(control.httpx, "AsyncClient", _Client)
    res = await control.forward_control("knowledge", JID, "cancel", TEST_USER)
    assert res.status_code == 502
