"""Single-DB asyncpg pool for video-gen-service (loreweave_video_gen).

LLM re-arch Phase 3 M5 — the decoupled job-row store. Mirrors
composition-service's pool: only created when the decouple flag is on (the
inline 201 path is stateless and never touches it).
"""

from __future__ import annotations

import asyncpg

_pool: asyncpg.Pool | None = None


async def create_pool(dsn: str) -> asyncpg.Pool:
    global _pool
    _pool = await asyncpg.create_pool(
        dsn,
        min_size=1,
        max_size=10,
        command_timeout=10,
    )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("video-gen pool not initialised")
    return _pool
