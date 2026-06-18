"""Wave 2 remainder — D-2B-DECOUPLE-FLAG-COUPLING worker startup guard.

The worker (worker.py) and the resume consumer + sweeper (app/main.py lifespan) gate on
the SAME translation_decouple_enabled flag but run in SEPARATE containers. The dangerous
mismatch is worker-ON / API-OFF: the worker submits decoupled chapters that never resume.
The startup guard warns loudly (best-effort, never fatal) when the resume consumer group
is absent while the flag is on.
"""
from unittest.mock import AsyncMock

import pytest

import worker


@pytest.mark.asyncio
async def test_guard_noop_when_flag_off(monkeypatch):
    monkeypatch.setattr(worker.settings, "translation_decouple_enabled", False)
    import redis.asyncio as aioredis
    called = {"from_url": False}
    monkeypatch.setattr(aioredis, "from_url",
                        lambda *a, **k: called.__setitem__("from_url", True))
    await worker._assert_decouple_consumer_reachable()
    assert called["from_url"] is False  # flag off ⇒ no Redis touch at all


def _fake_redis(groups):
    r = AsyncMock()
    r.xinfo_groups = AsyncMock(return_value=groups)
    r.aclose = AsyncMock()
    return r


@pytest.mark.asyncio
async def test_guard_warns_when_group_absent(monkeypatch, caplog):
    monkeypatch.setattr(worker.settings, "translation_decouple_enabled", True)
    import redis.asyncio as aioredis
    monkeypatch.setattr(aioredis, "from_url",
                        lambda *a, **k: _fake_redis([{"name": "some-other-group"}]))
    with caplog.at_level("WARNING"):
        await worker._assert_decouple_consumer_reachable()
    assert any("STALL" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_guard_quiet_when_group_present(monkeypatch, caplog):
    monkeypatch.setattr(worker.settings, "translation_decouple_enabled", True)
    import redis.asyncio as aioredis
    monkeypatch.setattr(aioredis, "from_url",
                        lambda *a, **k: _fake_redis([{"name": "translation-llm-resume"}]))
    with caplog.at_level("WARNING"):
        await worker._assert_decouple_consumer_reachable()
    assert not any("STALL" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_guard_never_fatal_on_redis_error(monkeypatch):
    monkeypatch.setattr(worker.settings, "translation_decouple_enabled", True)
    import redis.asyncio as aioredis

    def boom(*a, **k):
        raise RuntimeError("redis down")

    monkeypatch.setattr(aioredis, "from_url", boom)
    # Must not raise — a startup advisory cannot block the worker.
    await worker._assert_decouple_consumer_reachable()
