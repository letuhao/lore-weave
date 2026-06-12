import asyncpg

from app.db.pool import get_pool


async def get_db() -> asyncpg.Pool:
    return get_pool()


__all__ = ["get_db"]
