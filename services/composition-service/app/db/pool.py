"""Single-DB asyncpg pool for composition-service (loreweave_composition)."""

import asyncpg

_pool: asyncpg.Pool | None = None


async def create_pool(dsn: str) -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        dsn,
        min_size=2,
        max_size=10,
        command_timeout=5,
    )


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("composition pool not initialised")
    return _pool
