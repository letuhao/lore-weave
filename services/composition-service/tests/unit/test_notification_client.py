"""NotificationClient unit tests (RAID Wave D4) — pins the notification-service
HTTP-ingest contract this client mirrors from translation-service's
chapter_worker producer: POST /internal/notifications, {user_id, category, title,
metadata} body — and the best-effort guarantee (every failure swallowed).

P3 SDK-first (W5): the client now builds its transport via
``build_internal_client`` (X-Internal-Token + JSON + timeout baked into the
client), so the token + timeout are asserted on the FACTORY call, not on a
per-request ``headers`` kwarg.
"""

from __future__ import annotations

import uuid

import httpx

from app.clients.notification_client import NotificationClient


class _CaptureClient:
    """Fake AsyncClient returned by the patched build_internal_client."""

    captured: dict = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None):
        _CaptureClient.captured.update(url=url, json=json)
        return httpx.Response(201)


def _fake_factory(base_url, *, internal_token, timeout_s, trace_id_provider=None, **kw):
    _CaptureClient.captured = {
        "base_url": base_url,
        "internal_token": internal_token,
        "timeout_s": timeout_s,
    }
    return _CaptureClient()


class _BoomClient:
    async def __aenter__(self):
        raise RuntimeError("notification-service unreachable")

    async def __aexit__(self, *args):
        return False


async def test_notify_posts_the_ingest_contract(monkeypatch):
    monkeypatch.setattr(
        "app.clients.notification_client.build_internal_client", _fake_factory,
    )
    uid = uuid.uuid4()
    client = NotificationClient(base_url="http://notif:8091/", token="tok")
    await client.notify(
        uid,
        title="Autonomous authoring run complete — 2 chapter(s) drafted",
        metadata={"operation": "autonomous_authoring", "status": "report_ready"},
    )
    cap = _CaptureClient.captured
    assert cap["url"] == "http://notif:8091/internal/notifications"
    # X-Internal-Token is baked into the client by the factory (a default header
    # on every request), not passed per-request.
    assert cap["internal_token"] == "tok"
    assert cap["timeout_s"] == 5.0  # fire-and-forget: short, never blocks a run
    assert cap["json"] == {
        "user_id": str(uid),
        "category": "system",  # notification-service's allowed-category set
        "title": "Autonomous authoring run complete — 2 chapter(s) drafted",
        "metadata": {"operation": "autonomous_authoring", "status": "report_ready"},
    }


async def test_notify_defaults_metadata_to_empty_dict(monkeypatch):
    monkeypatch.setattr(
        "app.clients.notification_client.build_internal_client", _fake_factory,
    )
    await NotificationClient(base_url="http://n", token="t").notify(
        uuid.uuid4(), title="t",
    )
    assert _CaptureClient.captured["json"]["metadata"] == {}


async def test_notify_swallows_transport_failure(monkeypatch):
    monkeypatch.setattr(
        "app.clients.notification_client.build_internal_client",
        lambda *a, **k: _BoomClient(),
    )
    # must NOT raise — best-effort by contract (a notify blip never affects a run)
    await NotificationClient(base_url="http://n", token="t").notify(
        uuid.uuid4(), title="t",
    )
