import asyncio
import logging

import asyncpg
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db.pool import get_glossary_pool, get_knowledge_pool

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
    k_ok = await _ping(get_knowledge_pool())
    g_ok = await _ping(get_glossary_pool())
    status_code = 200 if (k_ok and g_ok) else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if (k_ok and g_ok) else "degraded",
            "db": "ok" if k_ok else "error",
            "glossary_db": "ok" if g_ok else "error",
        },
    )
