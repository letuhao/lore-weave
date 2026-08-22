import asyncio
import logging

import asyncpg
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db.graph_backend import configured_backend
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
            # Which graph engine this process is actually on. Read from
            # `configured_backend()` — the one home for the decision (T54c) — rather than
            # re-reading the env here, so this can never disagree with what the repo layer
            # and the adapters resolved.
            #
            # It is here because it was NOT observable anywhere: `knowledge-graph-backend-
            # live-smoke` takes an `--expect-backend` and had no way to check it, so a stack
            # that fell back to the other engine would have passed the smoke for the wrong
            # engine and said so in its own headline. A cutover you cannot see from outside
            # the container is one you cannot verify in a deployed environment either.
            "graph_backend": configured_backend(),
        },
    )
