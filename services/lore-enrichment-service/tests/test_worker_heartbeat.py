"""LE-062 — worker liveness heartbeat (background-task freshness).

Pins the pure freshness decision + that the loop actually touches the file, so
the headless worker's compose healthcheck (app/worker/healthcheck.py) can never
silently regress to the old false-`unhealthy` HTTP probe.
"""

from __future__ import annotations

import os

import pytest

from app.worker.heartbeat import (
    DEFAULT_MAX_AGE_S,
    heartbeat_is_fresh,
    heartbeat_loop,
    heartbeat_path,
    touch,
)


def test_fresh_when_recent():
    # mtime == now → age 0 → fresh; just inside the window → fresh.
    assert heartbeat_is_fresh(1000.0, 1000.0, max_age_s=30.0) is True
    assert heartbeat_is_fresh(1000.0, 1029.9, max_age_s=30.0) is True


def test_stale_when_old():
    # exactly at and beyond the window → stale (strict <).
    assert heartbeat_is_fresh(1000.0, 1030.0, max_age_s=30.0) is False
    assert heartbeat_is_fresh(1000.0, 5000.0, max_age_s=30.0) is False


def test_missing_file_is_not_fresh():
    # never written (file absent) → not yet alive → not fresh (fail-closed).
    assert heartbeat_is_fresh(None, 1000.0) is False


def test_default_max_age_is_generous_vs_interval():
    # the window must comfortably exceed a single touch interval so normal
    # busyness never false-flags (regression guard on the constants).
    assert DEFAULT_MAX_AGE_S >= 15.0


def test_heartbeat_path_env_override(monkeypatch):
    monkeypatch.setenv("WORKER_HEARTBEAT_PATH", "/tmp/custom_hb")
    assert heartbeat_path() == "/tmp/custom_hb"
    monkeypatch.delenv("WORKER_HEARTBEAT_PATH", raising=False)


@pytest.mark.asyncio
async def test_loop_touches_file(tmp_path):
    # the loop writes the file on the very first tick (liveness true at startup).
    p = str(tmp_path / "hb")
    assert not os.path.exists(p)
    await heartbeat_loop(path=p, interval_s=0.0, iterations=1)
    assert os.path.exists(p)


def test_touch_creates_then_updates(tmp_path):
    p = str(tmp_path / "hb")
    touch(p)
    assert os.path.exists(p)
    first = os.path.getmtime(p)
    os.utime(p, (first - 100, first - 100))  # backdate
    touch(p)
    assert os.path.getmtime(p) > first - 100  # mtime advanced
