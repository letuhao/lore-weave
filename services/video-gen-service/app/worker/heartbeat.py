"""Liveness heartbeat for the headless video-generation worker."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

__all__ = [
    "DEFAULT_HEARTBEAT_PATH",
    "DEFAULT_INTERVAL_S",
    "DEFAULT_MAX_AGE_S",
    "heartbeat_path",
    "heartbeat_is_fresh",
    "touch",
    "heartbeat_loop",
]

DEFAULT_HEARTBEAT_PATH = "/tmp/video_gen_worker_heartbeat"
DEFAULT_INTERVAL_S = 5.0
DEFAULT_MAX_AGE_S = 30.0


def heartbeat_path() -> str:
    """Return the heartbeat path, allowing tests to override it."""
    return os.environ.get("WORKER_HEARTBEAT_PATH", DEFAULT_HEARTBEAT_PATH)


def touch(path: str) -> None:
    """Create the heartbeat file or update its modification time."""
    Path(path).touch()


def heartbeat_is_fresh(
    mtime: float | None, now: float, max_age_s: float = DEFAULT_MAX_AGE_S
) -> bool:
    """Return whether an existing heartbeat is newer than ``max_age_s`` seconds."""
    if mtime is None:
        return False
    return (now - mtime) < max_age_s


async def heartbeat_loop(
    path: str | None = None,
    interval_s: float = DEFAULT_INTERVAL_S,
    iterations: int | None = None,
) -> None:
    """Touch the heartbeat immediately and periodically until cancelled."""
    heartbeat = path or heartbeat_path()
    count = 0
    while True:
        touch(heartbeat)
        count += 1
        if iterations is not None and count >= iterations:
            return
        await asyncio.sleep(interval_s)
