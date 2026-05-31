import asyncpg
from fastapi import Depends

from app.db.pool import get_pool
from app.middleware.auth import get_current_user


async def get_db() -> asyncpg.Pool:
    return get_pool()


__all__ = ["get_db", "get_current_user", "Depends"]
