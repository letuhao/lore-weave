"""Compose-task poll route (LLM re-arch Phase 3 M2).

The two interactive compose LLM calls (profile/suggest, compose/resolve-intent)
now run OFF the request path: the POST creates a 'pending'
:data:`enrichment_compose_task` + returns 202 + task_id, the resume worker runs the
compute, and this route polls the result.

  GET /v1/lore-enrichment/compose-tasks/{task_id}
    → { task_id, kind, status, result, error }

User-scoped: a task that is not the caller's reads as 404 (no cross-user oracle).
``result`` is the draft output (a suggested profile / a resolved intent) on
``status='completed'``, else null; ``error`` carries the message on 'failed'.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.principal import Principal, require_principal
from app.compose.compose_task import load_compose_task
from app.deps import get_db

router = APIRouter(prefix="/v1/lore-enrichment/compose-tasks", tags=["compose"])


@router.get("/{task_id}")
async def get_compose_task(
    task_id: UUID,
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Poll one compose task. 404 when absent OR not the caller's (anti-oracle)."""
    if principal.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required")
    row = await load_compose_task(
        pool, task_id=str(task_id), user_id=str(principal.user_id)
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return {
        "task_id": row["task_id"],
        "kind": row["kind"],
        "status": row["status"],
        "result": row["result"],
        "error": row["error"],
    }
