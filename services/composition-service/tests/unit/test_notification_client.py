"""NotificationClient unit tests (RAID Wave D4) — pins the notification-service
HTTP-ingest contract this client mirrors from translation-service's
chapter_worker producer: POST /internal/notifications, X-Internal-Token header,
{user_id, category, title, metadata} body — and the best-effort guarantee
(every failure swallowed)."""

from __future__ import annotations

import uuid

import httpx

from app.clients.notification_client import NotificationClient


class _CaptureAsyncClient:
    captured: dict = {}

    def __init__(self, timeout=None) -> None:
        _CaptureAsyncClient.captured = {"timeout": timeout}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        _CaptureAsyncClient.captured.update(url=url, json=json, headers=headers)
        return httpx.Response(201)


class _BoomAsyncClient:
    def __init__(self, timeout=None) -> None: ...

    async def __aenter__(self):
        raise RuntimeError("notification-service unreachable")

    async def __aexit__(self, *args):
        return False


async def test_notify_posts_the_ingest_contract(monkeypatch):
    monkeypatch.setattr(
        "app.clients.notification_client.httpx.AsyncClient", _CaptureAsyncClient,
    )
    uid = uuid.uuid4()
    client = NotificationClient(base_url="http://notif:8091/", token="tok")
    await client.notify(
        uid,
        title="Autonomous authoring run complete — 2 chapter(s) drafted",
        metadata={"operation": "autonomous_authoring", "status": "report_ready"},
    )
    cap = _CaptureAsyncClient.captured
    assert cap["url"] == "http://notif:8091/internal/notifications"
    assert cap["headers"] == {"X-Internal-Token": "tok"}
    assert cap["json"] == {
        "user_id": str(uid),
        "category": "system",  # notification-service's allowed-category set
        "title": "Autonomous authoring run complete — 2 chapter(s) drafted",
        "metadata": {"operation": "autonomous_authoring", "status": "report_ready"},
    }
    assert cap["timeout"] == 5.0  # fire-and-forget: short, never blocks a run


async def test_notify_defaults_metadata_to_empty_dict(monkeypatch):
    monkeypatch.setattr(
        "app.clients.notification_client.httpx.AsyncClient", _CaptureAsyncClient,
    )
    await NotificationClient(base_url="http://n", token="t").notify(
        uuid.uuid4(), title="t",
    )
    assert _CaptureAsyncClient.captured["json"]["metadata"] == {}


async def test_notify_swallows_transport_failure(monkeypatch):
    monkeypatch.setattr(
        "app.clients.notification_client.httpx.AsyncClient", _BoomAsyncClient,
    )
    # must NOT raise — best-effort by contract (a notify blip never affects a run)
    await NotificationClient(base_url="http://n", token="t").notify(
        uuid.uuid4(), title="t",
    )
