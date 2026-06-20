"""S-JOBS — MCP server facade for the jobs-service read tools.

Mounts at ``/mcp`` on the existing FastAPI app (``app/main.py``) and exposes the
job-read SSOT (``jobs_list`` / ``jobs_summary`` / ``jobs_get``) over the projection
store as MCP tools, via the shared Python kit ``loreweave_mcp`` (C-KIT-PY).

Design constraints (mirrors the proven knowledge-service `/mcp` facade + the
MCP fan-out plan §3 C-TOOL / §4 S-JOBS):

- All three tools are **Tier R** reads (`_meta.tier="R"`), **user-scoped**
  (`_meta.scope="user"`) — a job is owned by exactly one user (`owner_user_id`)
  with no book_id.
- **Identity comes ONLY from the envelope** (`build_tool_context`: X-Internal-Token
  constant-time check, then X-User-Id from headers) — NEVER from a tool argument.
  The store filters every query on `owner_user_id = ctx.user_id`, so a caller can
  only ever read their OWN jobs: scope is enforced by the store's WHERE clause
  (a non-owner sees an empty list / a 404-equivalent `None`, an anti-oracle).
- Arg models extend ``ForbidExtra`` (`extra="forbid"`) so the LLM cannot smuggle
  an `owner_user_id`/`user_id` past the envelope.
- Every tool carries validated ``_meta`` (`require_meta`) with tier + scope +
  synonyms feeding `find_tools` recall (H6).
- The DB pool is resolved via the same process-singleton `get_pool()` that backs
  the HTTP `/v1/jobs` deps — already initialised by `main.py`'s lifespan, so the
  facade does NOT re-initialise anything.

Dual-run: the bespoke `/v1/jobs` REST API is NOT removed.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import Context as MCPContext
from pydantic import Field

from loreweave_mcp import (
    ForbidExtra,
    build_tool_context,
    make_stateless_fastmcp,
    require_meta,
)

from ..config import settings
from ..contract import derive_control_caps
from ..database import get_pool
from ..projection import store

logger = logging.getLogger(__name__)

__all__ = ["mcp_server", "build_mcp_app"]

# Stateless FastMCP, wired exactly like the knowledge-service facade (stateless,
# path="/" so the mount at "/mcp" yields the endpoint at "/mcp", DNS-rebinding
# protection disabled for this internal token-authed endpoint).
mcp_server = make_stateless_fastmcp("jobs")


def _retryable_flag(job: dict[str, Any]) -> bool | None:
    """The producer-emitted per-job retryability signal off the projection params
    (mirrors the REST router's helper so MCP `control_caps` match the HTTP API)."""
    return (job.get("params") or {}).get("retryable")


def _with_caps(job: dict[str, Any]) -> dict[str, Any]:
    """Attach the state-aware `control_caps` derived from (status, kind), so an
    agent reading a job over MCP sees the SAME cap set the GUI does."""
    job["control_caps"] = [
        c.value
        for c in derive_control_caps(
            job["status"], job["kind"], retryable=_retryable_flag(job)
        )
    ]
    return job


# ── Tool registrations ────────────────────────────────────────────────────────
# Names MUST be `jobs_*` (C-GW prefix map: jobs="jobs_"). Descriptions guide the
# LLM; `_meta` (tier R + scope user + synonyms) is validated at registration time.


@mcp_server.tool(
    name="jobs_list",
    description=(
        "List the current user's background jobs (translation runs, extraction, "
        "media generation, etc.), most-recently-updated first. Use this to answer "
        "'what jobs are running', 'show my tasks', or to find a specific job. "
        "Owner-scoped — only the caller's own jobs are ever returned. Supports "
        "filtering by status / kind / parent job + a free-text search, and cursor "
        "pagination via `cursor` (pass back the returned `next_cursor` for the next "
        "page)."
    ),
    meta=require_meta(
        "R",
        "user",
        synonyms=[
            "jobs",
            "tasks",
            "queue",
            "running jobs",
            "background jobs",
            "my jobs",
            "task list",
        ],
        tool_name="jobs_list",
    ),
)
async def jobs_list(
    ctx: MCPContext,
    status: Annotated[
        str | None,
        "Optional — only jobs in this status (e.g. 'running', 'pending', "
        "'paused', 'completed', 'failed', 'cancelled').",
    ] = None,
    kind: Annotated[
        str | None,
        "Optional — only jobs of this kind (the worker/job type).",
    ] = None,
    parent: Annotated[
        str | None,
        "Optional — a parent job_id; returns that campaign's child jobs (H3). "
        "Omit for top-level jobs only (each with a `child_count`).",
    ] = None,
    search: Annotated[
        str | None,
        "Optional — free-text match across title/kind/service/model and the "
        "job_id (paste a partial id to find one job).",
    ] = None,
    bucket: Annotated[
        Literal["active", "history"] | None,
        "Optional — 'active' (non-terminal jobs) or 'history' (terminal jobs). "
        "Omit for all.",
    ] = None,
    cursor: Annotated[
        str | None,
        "Optional — opaque keyset cursor from a previous call's `next_cursor`.",
    ] = None,
    limit: Annotated[
        int,
        Field(ge=1, le=store.MAX_LIMIT),
        f"Max jobs to return (default {store.DEFAULT_LIMIT}, max {store.MAX_LIMIT}).",
    ] = store.DEFAULT_LIMIT,
) -> dict:
    tool_ctx = build_tool_context(ctx, settings.internal_service_token)
    items, next_cursor = await store.list_jobs(
        get_pool(),
        str(tool_ctx.user_id),
        status=status,
        kind=kind,
        parent=parent,
        q=search,
        bucket=bucket,
        cursor=cursor,
        limit=limit,
    )
    return {
        "items": [_with_caps(j) for j in items],
        "next_cursor": next_cursor,
    }


@mcp_server.tool(
    name="jobs_summary",
    description=(
        "Get the current user's job counts by status — how many are active, "
        "completed, failed, and cancelled (campaign-granularity, top-level jobs). "
        "Use this for a quick 'how many jobs do I have running' answer before "
        "listing them. Owner-scoped."
    ),
    meta=require_meta(
        "R",
        "user",
        synonyms=[
            "job counts",
            "how many jobs",
            "queue summary",
            "active jobs count",
            "job status counts",
        ],
        tool_name="jobs_summary",
    ),
)
async def jobs_summary(ctx: MCPContext) -> dict:
    tool_ctx = build_tool_context(ctx, settings.internal_service_token)
    return await store.count_summary(get_pool(), str(tool_ctx.user_id))


@mcp_server.tool(
    name="jobs_get",
    description=(
        "Get one job's full detail by its service + job_id (progress, status, "
        "error, cost/tokens, params, and the actions currently valid for it). "
        "Owner-scoped — returns 'not found or not accessible' if the job does not "
        "exist OR is not the caller's (an anti-oracle; the two are indistinguishable)."
    ),
    meta=require_meta(
        "R",
        "user",
        synonyms=["job detail", "job status", "get job", "show job"],
        tool_name="jobs_get",
    ),
)
async def jobs_get(
    ctx: MCPContext,
    service: Annotated[
        str,
        "The owning service of the job (e.g. 'translation', 'knowledge', "
        "'composition') — as seen on a job from `jobs_list`.",
    ],
    job_id: Annotated[str, "The job's id (UUID)."],
) -> dict:
    tool_ctx = build_tool_context(ctx, settings.internal_service_token)
    job = await store.get_job(get_pool(), str(tool_ctx.user_id), service, job_id)
    if job is None:
        # H13 anti-oracle: a non-owner / missing job is indistinguishable. Return a
        # structured tool error (not raised) so the chat loop reads "tool refused"
        # cleanly, mirroring the kit's uniform message.
        return {"success": False, "error": "not found or not accessible"}
    return _with_caps(job)


# ── ASGI factory ──────────────────────────────────────────────────────────────


def build_mcp_app():
    """Return the ASGI app to mount at ``/mcp`` in ``main.py``.

    ``FastMCP.streamable_http_app()`` returns a Starlette app whose own lifespan
    runs the StreamableHTTP session manager. Under FastAPI a *mounted* sub-app's
    lifespan is NOT auto-run, so ``main.py`` runs the session manager directly
    inside its own lifespan (``mcp_server.session_manager.run()``)."""
    return mcp_server.streamable_http_app()
