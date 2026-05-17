"""K21.3 — internal memory-tool execution endpoint.

POST /internal/tools/execute

Service-to-service surface the chat-service tool-calling loop (K21
Cycle B) calls when the LLM emits a tool call. Authentication is
`X-Internal-Token`; `user_id` is trusted from the body — there is no
end-user JWT on an S2S endpoint, so chat-service passes the id it
authenticated (same trust model as `internal_summarize.py`).

**Module placement** follows the established `app/routers/internal_*.py`
convention — the K21 plan named `app/api/internal/tools.py`, but every
existing internal router lives here (see `internal_summarize.py`'s own
note on the same deviation).

The HTTP envelope is **always 200** with a `success` field carrying
the tool-level outcome. Only an infrastructure failure (Neo4j / repo
crash) maps to 503, so the chat-service loop can tell "the tool said
no" apart from "knowledge-service is down".
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.clients.embedding_client import EmbeddingClient
from app.db.repositories.projects import ProjectsRepo
from app.deps import get_embedding_client, get_projects_repo
from app.middleware.internal_auth import require_internal_token
from app.tools.executor import ToolContext, execute_tool, get_tools_redis

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)


class ToolExecuteRequest(BaseModel):
    """Envelope from chat-service. `user_id` / `project_id` /
    `session_id` are the trusted scope; the LLM only ever influences
    `tool_args` (validated per-tool inside the executor)."""

    user_id: UUID
    project_id: UUID | None = None
    session_id: str = Field(min_length=1, max_length=200)
    tool_name: str = Field(min_length=1, max_length=100)
    tool_args: dict[str, Any] = Field(default_factory=dict)


class ToolExecuteResponse(BaseModel):
    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None


@router.post("/tools/execute", response_model=ToolExecuteResponse)
async def execute_tool_endpoint(
    req: ToolExecuteRequest,
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    embedding_client: EmbeddingClient = Depends(get_embedding_client),
) -> ToolExecuteResponse:
    """K21.3 — execute one LLM memory tool call."""
    ctx = ToolContext(
        user_id=req.user_id,
        project_id=req.project_id,
        session_id=req.session_id,
        projects_repo=projects_repo,
        embedding_client=embedding_client,
        redis=get_tools_redis(),
    )
    try:
        result = await execute_tool(ctx, req.tool_name, req.tool_args)
    except Exception as exc:
        # Infrastructure failure — Neo4j down, an unexpected repo bug.
        # The executor already logged the traceback; surface 503 so the
        # caller retries rather than treating it as a tool refusal.
        logger.error(
            "K21.3: tool %r failed with an infrastructure error: %s",
            req.tool_name, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="tool execution backend is unavailable",
        ) from exc

    return ToolExecuteResponse(
        success=result.success,
        result=result.result,
        error=result.error,
    )
