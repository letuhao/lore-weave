"""Regression tests for the headless worker heartbeat healthcheck."""

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
    assert heartbeat_is_fresh(1000.0, 1000.0, max_age_s=30.0) is True
    assert heartbeat_is_fresh(1000.0, 1029.9, max_age_s=30.0) is True


def test_stale_when_old_or_missing():
    assert heartbeat_is_fresh(1000.0, 1030.0, max_age_s=30.0) is False
    assert heartbeat_is_fresh(1000.0, 5000.0, max_age_s=30.0) is False
    assert heartbeat_is_fresh(None, 1000.0) is False


def test_default_max_age_exceeds_interval():
    assert DEFAULT_MAX_AGE_S >= 15.0


def test_heartbeat_path_env_override(monkeypatch):
    monkeypatch.setenv("WORKER_HEARTBEAT_PATH", "/tmp/custom_video_gen_hb")
    assert heartbeat_path() == "/tmp/custom_video_gen_hb"


@pytest.mark.asyncio
async def test_loop_touches_file(tmp_path):
    path = str(tmp_path / "heartbeat")
    assert not os.path.exists(path)
    await heartbeat_loop(path=path, interval_s=0.0, iterations=1)
    assert os.path.exists(path)


def test_touch_updates_mtime(tmp_path):
    path = str(tmp_path / "heartbeat")
    touch(path)
    first = os.path.getmtime(path)
    os.utime(path, (first - 100, first - 100))
    touch(path)
    assert os.path.getmtime(path) > first - 100
