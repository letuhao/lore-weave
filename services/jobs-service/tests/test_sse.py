"""SSE bridge — payload shape, notifier publish, stream framing (fake redis)."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import sse
from loreweave_jobs import JobEvent, JobStatus

U = "11111111-1111-1111-1111-111111111111"
J = "22222222-2222-2222-2222-222222222222"


def _event(**over):
    base = dict(
        service="knowledge", job_id=J, owner_user_id=U, kind="extraction",
        status=JobStatus.RUNNING, occurred_at="2026-06-15T10:00:00+00:00",
    )
    base.update(over)
    return JobEvent(**base)


def test_event_to_payload_includes_caps_and_string_status():
    p = sse.event_to_payload(_event())
    assert p["status"] == "running"
    assert p["control_caps"] == ["pause", "cancel"]  # running + extraction (multi-unit)
    assert p["job_id"] == J and p["owner_user_id"] == U


def test_event_to_payload_carries_p4_usage_fields():
    p = sse.event_to_payload(_event(
        model="qwen2.5-7b", cost_usd=2.74, tokens_in=980142, tokens_out=180553,
        params={"concurrency": 4},
    ))
    assert p["model"] == "qwen2.5-7b" and p["cost_usd"] == 2.74
    assert p["tokens_in"] == 980142 and p["tokens_out"] == 180553
    assert p["params"] == {"concurrency": 4}


def test_channel_is_per_owner():
    assert sse._channel(U) == f"loreweave:jobs:user:{U}"


@pytest.mark.asyncio
async def test_make_notifier_publishes_to_owner_channel():
    publisher = AsyncMock()
    notify = sse.make_notifier(publisher)
    await notify(_event(status=JobStatus.COMPLETED))
    publisher.publish.assert_awaited_once()
    channel, data = publisher.publish.await_args.args
    assert channel == f"loreweave:jobs:user:{U}"
    assert json.loads(data)["status"] == "completed"


@pytest.mark.asyncio
async def test_stream_emits_connected_then_event_then_heartbeat(monkeypatch):
    # Fake pubsub: one real message, then a None (→ heartbeat).
    msgs = [{"data": json.dumps({"job_id": J, "status": "running"})}, None]
    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.aclose = AsyncMock()
    pubsub.get_message = AsyncMock(side_effect=lambda **kw: msgs.pop(0) if msgs else None)
    client = MagicMock()
    client.pubsub = MagicMock(return_value=pubsub)
    client.aclose = AsyncMock()
    monkeypatch.setattr(sse.aioredis, "from_url", lambda *a, **k: client)

    frames = []
    gen = sse.stream_user_events("redis://x", U)
    async for frame in gen:
        frames.append(frame)
        if len(frames) >= 3:  # connected, data, heartbeat
            break
    await gen.aclose()

    assert frames[0] == ": connected\n\n"
    assert frames[1].startswith("data: ")
    assert json.loads(frames[1][len("data: "):].strip())["job_id"] == J
    assert frames[2] == ": heartbeat\n\n"
    pubsub.subscribe.assert_awaited_once_with(f"loreweave:jobs:user:{U}")
    # generator close → finally tears the subscription down
    pubsub.unsubscribe.assert_awaited()
    client.aclose.assert_awaited()
