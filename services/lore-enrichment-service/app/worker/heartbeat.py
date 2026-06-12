"""Worker liveness heartbeat (LE-062).

The ``lore-enrichment-worker`` is a HEADLESS Redis-stream consumer (``python -m
app.worker``) with no HTTP server, so the service image's HTTP ``/health``
healthcheck is meaningless for it — the container reported ``unhealthy`` forever
even while the consumer drained the stream correctly.

Instead the worker touches a heartbeat file from a BACKGROUND asyncio task on a
fixed interval. The key property: while the event loop is alive the mtime stays
fresh EVEN during a long LLM generation (the consumer is only ``await``-ing httpx,
not blocking the loop), so a STALE heartbeat means a true hang/crash — not mere
busyness. A loop-top touch would instead go stale during every legitimate
multi-second generation and false-flag ``unhealthy``; the background task avoids
that. The compose healthcheck runs ``python -m app.worker.healthcheck`` which
reads the file and exits 0 (fresh) / 1 (stale or missing).
"""

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

DEFAULT_HEARTBEAT_PATH = "/tmp/lore_enrichment_worker_heartbeat"
DEFAULT_INTERVAL_S = 5.0
#: A heartbeat older than this ⟹ unhealthy. Generous vs the touch interval (many
#: ticks) so a slow event-loop scheduling tick never false-flags; a real hang/
#: crash exceeds it. Normal busyness (awaiting a long generation) does NOT, because
#: the background task keeps ticking while the loop is alive.
DEFAULT_MAX_AGE_S = 30.0


def heartbeat_path() -> str:
    """The heartbeat file path (env-overridable for tests / read-only-rootfs)."""
    return os.environ.get("WORKER_HEARTBEAT_PATH", DEFAULT_HEARTBEAT_PATH)


def touch(path: str) -> None:
    """Update the heartbeat file's mtime (create it if absent)."""
    Path(path).touch()


def heartbeat_is_fresh(
    mtime: float | None, now: float, max_age_s: float = DEFAULT_MAX_AGE_S
) -> bool:
    """Pure decision: fresh iff the heartbeat exists and is younger than
    ``max_age_s``. ``mtime`` is the file mtime (epoch seconds) or ``None`` when the
    file is absent (never written → not yet alive → not fresh)."""
    if mtime is None:
        return False
    return (now - mtime) < max_age_s


async def heartbeat_loop(
    path: str | None = None,
    interval_s: float = DEFAULT_INTERVAL_S,
    iterations: int | None = None,
) -> None:
    """Touch ``path`` every ``interval_s`` from the event loop. Touches ONCE
    immediately so liveness is true as soon as the worker starts. Runs forever
    unless ``iterations`` is given (tests). Cancel-safe (the caller cancels it on
    shutdown)."""
    p = path or heartbeat_path()
    n = 0
    while True:
        touch(p)
        n += 1
        if iterations is not None and n >= iterations:
            return
        await asyncio.sleep(interval_s)
