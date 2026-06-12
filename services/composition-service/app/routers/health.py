import asyncio
import logging

import asyncpg
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db.pool import get_pool

logger = logging.getLogger(__name__)

router = APIRouter()


async def _ping(pool) -> bool:
    try:
        async with pool.acquire() as conn:
            await asyncio.wait_for(conn.fetchval("SELECT 1"), timeout=1.0)
        return True
    except (asyncpg.PostgresError, asyncio.TimeoutError, OSError, RuntimeError) as exc:
        logger.warning("health ping failed: %s", str(exc))
        return False


@router.get("/health")
async def health() -> JSONResponse:
    db_ok = await _ping(get_pool())
    return JSONResponse(
        status_code=200 if db_ok else 503,
        content={"status": "ok" if db_ok else "degraded", "db": "ok" if db_ok else "error"},
    )
