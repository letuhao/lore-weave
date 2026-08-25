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
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field, ValidationError

from loreweave_mcp import (
    validation_directive,
    ForbidExtra,
    apply_response_contract,
    build_tool_context,
    make_stateless_fastmcp,
    require_meta,
)

from .. import control
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


# ── W0 #4b — model-directed validation errors ─────────────────────────────────
# FastMCP surfaces a pydantic arg-validation failure as the RAW multi-line dump
# (with the errors.pydantic.dev URL) — noise a model cannot act on. Intercept at
# the per-server tool-dispatch chokepoint and rewrite to a ONE-LINE directive
# (arg name + what pydantic expected + what was sent) the model can self-correct
# from. Duplicated verbatim in knowledge/translation-service until the
# loreweave_mcp kit absorbs it (kit is outside the W0 change surface).


# W0 #4b — the one-line validation directive now lives in the kit as
# `validation_directive`. It used to be a byte-identical copy in THIS file and in two sibling
# services, and the copy was wrong in a way none of the three noticed: for a `missing` error
# pydantic sets `input` to the PARENT object, so every rendering said "(you sent a dict)" about
# a field that had never been sent. Measured across the corpus: 79 calls, 7 tools, 16 sessions,
# args `{}` in 100% of them — the clause was false every single time it appeared.
#
# The comment that used to sit here said the kit "will absorb the shared copy later". Three
# copies is how one of them drifts, so it absorbed it.
_validation_directive = validation_directive


def _install_validation_error_rewriter(server) -> None:
    """Wrap the FastMCP tool manager's dispatch so a ToolError caused by a
    pydantic ValidationError re-raises with the one-line directive instead of
    the raw dump. Non-validation errors pass through untouched."""
    manager = server._tool_manager
    original = manager.call_tool

    async def call_tool(name, arguments, *args, **kwargs):
        try:
            return await original(name, arguments, *args, **kwargs)
        except ToolError as e:
            cause = e.__cause__
            if isinstance(cause, ValidationError):
                raise ToolError(_validation_directive(name, cause)) from cause
            raise

    manager.call_tool = call_tool


_install_validation_error_rewriter(mcp_server)


# The projection store's closed status set (mirrors store._ACTIVE_STATUSES +
# store._TERMINAL_STATUSES) — advertised as a real JSON-schema enum (W0 #2).
JobStatus = Literal[
    "pending", "running", "paused", "cancelling", "completed", "failed", "cancelled"
]


def _single_value(arg_name: str, value: str | list[str] | None) -> str | None:
    """W0 #3 — models routinely send `[\"running\"]` for filter args. Accept a
    one-element list (coerce to its value); reject a multi-element list with a
    directive naming the fix. None/str pass through."""
    if isinstance(value, list):
        if len(value) == 1:
            return value[0]
        raise ValueError(
            f"`{arg_name}` must be a single value, not a list of {len(value)} — "
            f"pick one and call the tool again"
        )
    return value


def _retryable_flag(job: dict[str, Any]) -> bool | None:
    """The producer-emitted per-job retryability signal off the projection params
    (mirrors the REST router's helper so MCP `control_caps` match the HTTP API)."""
    return (job.get("params") or {}).get("retryable")


# L1/L2 reference-first (Context Budget Law §6b): at detail=summary a job row
# collapses to these fields — the heavy accumulated `params` jsonb + long `error`
# tracebacks (the measured jobs_list bloat) are dropped; fetch them via jobs_get.
# Every scalar status field a "what's running" answer needs is kept.
_JOB_REF_FIELDS = (
    "service", "job_id", "kind", "status", "detail_status", "title", "progress",
    "parent_job_id", "child_count", "control_caps", "job_created_at",
    "job_updated_at", "model", "cost_usd", "tokens_in", "tokens_out",
)


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


# K24/K36 (2026-07-24) — the MCP `jobs_list` default limit is DELIBERATELY smaller than
# the shared store.DEFAULT_LIMIT (50). 50 fat rows measured 45.6 KB at detail=full — 5.7×
# the kit's 8 KB context-budget warning, on the DEFAULT no-arg call. The REST list view
# (routers/jobs.py) legitimately renders 50, so we do NOT lower the shared constant; the
# LLM caller — the party the Context Budget Law exists to protect — gets a context-sized
# page and pulls more via `cursor`. 10 summary rows ≈ 4.4 KB, comfortably under the warn.
MCP_LIST_DEFAULT_LIMIT = 10


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
        "page). Returns a lightweight summary by default (each job's heavy "
        "`params`/`error` dropped) — pass `detail=full` for every field, or fetch the "
        "heavy fields for ONE job via jobs_get. Defaults to a small page; raise `limit` "
        "or page with `cursor` for more."
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
        JobStatus | list[JobStatus] | None,
        "Optional — only jobs in this status. Pass ONE status value as a plain "
        "string (a one-element list is tolerated and unwrapped).",
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
        f"Max jobs to return (default {MCP_LIST_DEFAULT_LIMIT}, max {store.MAX_LIMIT}). "
        "Kept small so the default reply fits the caller's context; page with `cursor`.",
    ] = MCP_LIST_DEFAULT_LIMIT,
    detail: Annotated[
        Literal["summary", "full"],
        "summary (default) = drop each job's heavy params/error; full = every field.",
    ] = "summary",
) -> dict:
    tool_ctx = build_tool_context(ctx, settings.internal_service_token)
    items, next_cursor = await store.list_jobs(
        get_pool(),
        str(tool_ctx.user_id),
        status=_single_value("status", status),
        kind=kind,
        parent=parent,
        q=search,
        bucket=bucket,
        cursor=cursor,
        limit=limit,
    )
    # Cursor pagination already bounds the count → apply only the detail
    # projection here (no second limit/truncation, which would confuse next_cursor).
    projected, _ = apply_response_contract(
        [_with_caps(j) for j in items], ref_fields=_JOB_REF_FIELDS, detail=detail,
    )
    # 🔴 A PAGE READ AS A TOTAL. MEASURED LIVE 2026-08-14 (batch 7, K=3): asked "What background
    # jobs do I have running right now?", the model called this tool, received 10 items plus a
    # next_cursor, and answered "You currently have 10 background jobs running". jobs_summary on
    # the same account reports 31 active. The payload carried the page signal (`next_cursor`) and
    # nothing that says the ITEM COUNT is not the total, so the model reported the page size.
    #
    # world_list is the control and it is already built this way — it returns
    # `page: {total, returned, has_more, next_offset}` plus a one-line guidance, and its live
    # answer on the same day was correct ("You have 28 worlds in total"). Same class as
    # `always_available` on tool_list and `degraded` on story_search: a response that omits must
    # SAY it omits, in a field a caller cannot skim past.
    #
    # A `total` is deliberately NOT computed here — it would be a second query on every list, and
    # jobs_summary exists precisely to answer "how many". So the guidance NAMES that tool rather
    # than guessing a number.
    out: dict = {
        "items": projected,
        "returned": len(projected),
        "next_cursor": next_cursor,
        "detail": detail,
    }
    if next_cursor:
        out["page"] = {"returned": len(projected), "has_more": True}
        out["guidance"] = (
            f"This is ONE PAGE of {len(projected)} job(s), NOT the total — more exist. "
            "Do not report this number as how many jobs there are. "
            "Pass `next_cursor` to continue, or call jobs_summary for the counts by status."
        )
    return out


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
        synonyms=["job detail", "job status", "get job", "show job", "detail of my job", "my most recent job", "how is the job going", "job cost"],
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


# ── Control tools (Tier-A, P4 slice E / H-N) ──────────────────────────────────
# An agent that STARTED a (possibly priced) job must be able to STOP a runaway over
# MCP — today control was REST/FE-only. These two tools are **Tier-A** (free,
# reversible: cancel/pause never spends) on the `jobs` scope.
#
# Ownership is enforced EXACTLY as the REST `control_job` route does (and never via
# a tool arg beyond the job_id selector):
#   1. identity comes ONLY from the envelope (`build_tool_context`); the lookup
#      `store.get_job(..., owner_user_id, ...)` is scoped to the authorized owner →
#      a non-owned / nonexistent job returns the SAME anti-oracle "not found or not
#      accessible" (the two are indistinguishable; the worker-loaded-id rule —
#      a client-supplied job_id MUST be scoped to the authorized owner).
#   2. the state-aware `control_caps` gate rejects an action invalid for the job's
#      current status (mirrors the GUI / REST cap gate).
#   3. `control.forward_control` re-forwards to the owning service over internal-token,
#      which RE-VERIFIES ownership on the actual row (spec M4) — the projection is a
#      possibly-stale mirror, never the authority for a mutation. 501 if the owning
#      service ships no control endpoint.


async def _control(ctx: MCPContext, service: str, job_id: str, action: str) -> dict:
    """Shared owner-scoped control path for `jobs_cancel` / `jobs_pause`."""
    tool_ctx = build_tool_context(ctx, settings.internal_service_token)
    owner = str(tool_ctx.user_id)
    job = await store.get_job(get_pool(), owner, service, job_id)
    if job is None:
        # Anti-oracle: a non-owned OR nonexistent job is indistinguishable. NEVER
        # reveal existence of another owner's job.
        return {"success": False, "error": "not found or not accessible"}
    caps = [
        c.value
        for c in derive_control_caps(
            job["status"], job["kind"], retryable=_retryable_flag(job)
        )
    ]
    if action not in caps:
        return {
            "success": False,
            "error": f"action '{action}' not valid for status '{job['status']}'",
        }
    result = await control.forward_control(service, job_id, action, owner, job["kind"])
    ok = 200 <= result.status_code < 300
    return {"success": ok, "status_code": result.status_code, "result": result.body}


@mcp_server.tool(
    name="jobs_cancel",
    description=(
        "Cancel one of the CALLER'S OWN running/pending/paused background jobs by "
        "its service + job_id (e.g. to stop a runaway translation or extraction run). "
        "Free and reversible-by-restart — no spend, no confirm needed. Owner-scoped: "
        "returns 'not found or not accessible' if the job does not exist OR is not the "
        "caller's (an anti-oracle), and refuses if cancel isn't valid for the job's "
        "current state. Find the service + job_id (and whether 'cancel' is a valid "
        "action) via `jobs_list` / `jobs_get` `control_caps`."
    ),
    meta=require_meta(
        "A",
        "user",
        synonyms=[
            "cancel job",
            "stop job",
            "abort job",
            "kill job",
            "stop a running job",
            "cancel my task",
            "stop the translation",
            "stop it",
            "cancel it",
            "stop that one",
        ],
        tool_name="jobs_cancel",
    ),
)
async def jobs_cancel(
    ctx: MCPContext,
    service: Annotated[
        str,
        "The owning service of the job (e.g. 'translation', 'knowledge', "
        "'composition') — as seen on a job from `jobs_list`.",
    ],
    job_id: Annotated[str, "The job's id (UUID) — must be one of the caller's own jobs."],
) -> dict:
    return await _control(ctx, service, job_id, "cancel")


@mcp_server.tool(
    name="jobs_pause",
    description=(
        "Pause one of the CALLER'S OWN multi-unit background jobs by its service + "
        "job_id (stops dispatching new units + drains in-flight; resume later from the "
        "GUI). Free and reversible — no spend, no confirm needed. Only multi-unit jobs "
        "(extraction / campaign / multi-chapter translation / enrichment) can pause; a "
        "single-call job is cancel-only. Owner-scoped: returns 'not found or not "
        "accessible' if the job does not exist OR is not the caller's (an anti-oracle), "
        "and refuses if pause isn't valid for the job's current state (check `jobs_get` "
        "`control_caps`)."
    ),
    meta=require_meta(
        "A",
        "user",
        synonyms=[
            "pause job",
            "hold job",
            "suspend job",
            "pause a running job",
            "pause my task",
            # 🔴 "pause the translation" WAS REMOVED HERE ON 2026-08-25 AND RESTORED THE SAME DAY,
            # BY MEASUREMENT. The argument for removing it was clean — a GENERIC tool must not
            # claim a DOMAIN phrase, and translation_job_control is the tool that actually
            # understands a translation job. The A/B says otherwise, same scenario, same seed:
            #
            #     original wording, build of 2026-07-28   surfaced 5/5   jobs_pause called 5/5
            #     original wording, after the de-dup      surfaced 2/5   jobs_pause called 0/5
            #
            # and translation_job_control did NOT take the calls — 0/5 in both arms. The model
            # ran jobs_list, jobs_get, jobs_summary and paused nothing. So the phrase move did
            # not redirect the request to a better tool, it removed the only tool that was
            # answering it. A tie that has been MEASURED is broken by taking the phrase off the
            # LOSER; taking it off the winner leaves nobody holding the request. Whether the
            # domain-specific tool SHOULD win it is DQ-T41, which is the owner's and is not
            # settled by reverting a regression.
            "pause the translation",
            "pause it",
            "hold it",
            "pause that one",
        ],
        tool_name="jobs_pause",
    ),
)
async def jobs_pause(
    ctx: MCPContext,
    service: Annotated[
        str,
        "The owning service of the job (e.g. 'translation', 'knowledge') — as seen "
        "on a job from `jobs_list`.",
    ],
    job_id: Annotated[str, "The job's id (UUID) — must be one of the caller's own jobs."],
) -> dict:
    return await _control(ctx, service, job_id, "pause")


# ── ASGI factory ──────────────────────────────────────────────────────────────


def build_mcp_app():
    """Return the ASGI app to mount at ``/mcp`` in ``main.py``.

    ``FastMCP.streamable_http_app()`` returns a Starlette app whose own lifespan
    runs the StreamableHTTP session manager. Under FastAPI a *mounted* sub-app's
    lifespan is NOT auto-run, so ``main.py`` runs the session manager directly
    inside its own lifespan (``mcp_server.session_manager.run()``)."""
    return mcp_server.streamable_http_app()
