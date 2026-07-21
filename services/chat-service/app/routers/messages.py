import json
import logging
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.client.auth_client import resolve_local_date
from app.client.billing_client import get_billing_client
from app.client.provider_client import get_provider_client
from app.config import settings
from app.deps import get_current_user, get_db
from app.models import (
    ChatMessage,
    ContextHistoryPoint,
    ContextHistoryResponse,
    ContextTracePoint,
    ContextTraceResponse,
    LatestContextBudgetResponse,
    MessageListResponse,
    SendMessageRequest,
    ToolResultRequest,
)
from app.services.stream_service import resume_stream_response, stream_response

# ARCH-1 C3 — per-request stream-format negotiation. A multi-device deployment
# serves the legacy frontend and the AG-UI frontend (C4) at once, so the format
# is chosen per request, not by a global flag.
STREAM_FORMAT_HEADER = "x-loreweave-stream-format"
_VALID_STREAM_FORMATS = {"legacy", "agui"}

logger = logging.getLogger(__name__)


def _resolve_stream_format(raw: str | None) -> str:
    """Map the request header to a valid format, falling back to the configured
    default for an absent or unrecognized value."""
    if raw is not None:
        candidate = raw.strip().lower()
        if candidate in _VALID_STREAM_FORMATS:
            return candidate
    return settings.default_stream_format

router = APIRouter(prefix="/v1/chat/sessions", tags=["messages"])


def _parse_content_parts(raw: object) -> object:
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    return raw


def _row_to_message(r: asyncpg.Record) -> ChatMessage:
    return ChatMessage(
        message_id=r["message_id"],
        session_id=r["session_id"],
        owner_user_id=r["owner_user_id"],
        role=r["role"],
        content=r["content"],
        content_parts=_parse_content_parts(r["content_parts"]),
        # K21-C (D-K21B-05): surface the tool-call history. _parse_content_parts
        # is a generic JSONB-string-or-passthrough parser despite the name.
        # `.get()` so a row read before the column's migration ran (or a
        # partial test record) degrades to None instead of a KeyError.
        tool_calls=_parse_content_parts(r.get("tool_calls")),
        sequence_num=r["sequence_num"],
        input_tokens=r["input_tokens"],
        output_tokens=r["output_tokens"],
        model_ref=r["model_ref"],
        is_error=r["is_error"],
        error_detail=r["error_detail"],
        # `.get()` so a row read before the finish_reason migration ran (or a
        # partial test record) degrades to None instead of a KeyError.
        finish_reason=r.get("finish_reason"),
        parent_message_id=r["parent_message_id"],
        created_at=r["created_at"],
    )


@router.get("/{session_id}/messages", response_model=MessageListResponse)
async def list_messages(
    session_id: UUID,
    limit: int = Query(50, le=200),
    before_seq: int | None = None,
    branch_id: int = Query(0, alias="branch_id"),
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> MessageListResponse:
    # Verify ownership
    exists = await pool.fetchval(
        "SELECT 1 FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="session not found")

    if before_seq is not None:
        rows = await pool.fetch(
            """
            SELECT * FROM chat_messages
            WHERE session_id=$1 AND branch_id=$4 AND sequence_num < $2
            ORDER BY sequence_num ASC
            LIMIT $3
            """,
            str(session_id), before_seq, limit, branch_id,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT * FROM chat_messages
            WHERE session_id=$1 AND branch_id=$3
            ORDER BY sequence_num ASC
            LIMIT $2
            """,
            str(session_id), limit, branch_id,
        )
    return MessageListResponse(items=[_row_to_message(r) for r in rows])


def _extract_breakdown(raw: object) -> dict | None:
    """Pull the per-category `breakdown` sub-map out of a persisted
    context_breakdown JSONB (the full contextBudget frame). Returns None when
    the column is absent/unparseable or carries no breakdown (e.g. a resume-path
    turn that didn't re-measure the parts) — such turns are skipped from the
    series so the chart shows only turns with real per-category data."""
    payload = _parse_content_parts(raw)
    if not isinstance(payload, dict):
        return None
    breakdown = payload.get("breakdown")
    if not isinstance(breakdown, dict) or not breakdown:
        return None
    return breakdown


@router.get("/{session_id}/context-history", response_model=ContextHistoryResponse)
async def context_history(
    session_id: UUID,
    # ge=1 floors the bound: a negative limit reaches Postgres as a negative
    # LIMIT ("must not be negative") → 500. FastAPI rejects it as 422 instead.
    limit: int = Query(100, ge=1, le=200),
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> ContextHistoryResponse:
    """Chat Quality Wave W1-residual — the per-turn token-history series.

    W1 persisted the full contextBudget frame per assistant turn
    (chat_messages.context_breakdown JSONB). This returns the ordered SERIES of
    per-category token costs across the session's assistant turns, so the FE can
    chart how each category evolved (the "History" view of the breakdown panel).
    Owner-gated like the sibling session-scoped routes; windowed to the most
    recent `limit` turns but returned oldest-first for a left-to-right x-axis."""
    exists = await pool.fetchval(
        "SELECT 1 FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="session not found")

    # Window to the most recent `limit` turns (DESC) then re-sort ASC so the
    # chart's x-axis reads oldest→newest. Owner-scoped, active branch only,
    # assistant turns that actually carry a breakdown.
    rows = await pool.fetch(
        """
        SELECT sequence_num, created_at, input_tokens, output_tokens, context_breakdown
        FROM (
            SELECT sequence_num, created_at, input_tokens, output_tokens, context_breakdown
            FROM chat_messages
            -- branch_id=0 pins the live/active branch (edits move superseded
            -- turns to a higher branch) so the chart tracks the current timeline.
            WHERE session_id=$1 AND owner_user_id=$2 AND branch_id=0
              AND role='assistant' AND context_breakdown IS NOT NULL
            ORDER BY sequence_num DESC
            LIMIT $3
        ) t
        ORDER BY sequence_num ASC
        """,
        str(session_id), user_id, limit,
    )

    items: list[ContextHistoryPoint] = []
    for r in rows:
        breakdown = _extract_breakdown(r["context_breakdown"])
        if breakdown is None:
            continue
        items.append(
            ContextHistoryPoint(
                sequence_num=r["sequence_num"],
                created_at=r["created_at"],
                input_tokens=r["input_tokens"],
                output_tokens=r["output_tokens"],
                breakdown=breakdown,
            )
        )
    return ContextHistoryResponse(items=items)


@router.get("/{session_id}/context-budget", response_model=LatestContextBudgetResponse)
async def latest_context_budget(
    session_id: UUID,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> LatestContextBudgetResponse:
    """The LAST assistant turn's persisted contextBudget frame.

    The header context meter previously derived its snapshot ONLY from the live
    per-turn SSE `contextBudget` event, so it rendered nothing on session
    load/switch/reload until the NEXT turn finished (the "sometimes shows,
    sometimes not" gap). This lets the FE SEED the meter from the persisted frame
    on load, so it's visible whenever the session has at least one measured turn.
    Owner-gated like the sibling session-scoped routes; `budget=None` for a
    brand-new session with no measured turn yet."""
    exists = await pool.fetchval(
        "SELECT 1 FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="session not found")

    # The most recent assistant turn on the live branch that actually carried a
    # measured budget (a resume-path turn may persist None). fetchROW (not
    # fetchval) so it mocks independently of the owner-gate fetchval above.
    row = await pool.fetchrow(
        """
        SELECT context_breakdown
        FROM chat_messages
        WHERE session_id=$1 AND owner_user_id=$2 AND branch_id=0
          AND role='assistant' AND context_breakdown IS NOT NULL
        ORDER BY sequence_num DESC
        LIMIT 1
        """,
        str(session_id), user_id,
    )
    frame = _parse_content_parts(row["context_breakdown"]) if row else None
    return LatestContextBudgetResponse(budget=frame if isinstance(frame, dict) else None)


@router.get("/{session_id}/context-trace", response_model=ContextTraceResponse)
async def context_trace(
    session_id: UUID,
    # Window to the most recent `limit` turns. Client-side pagination + status/search
    # filtering run over the returned set (a session's turn count is bounded — not
    # thousands — and the Inspector paginates the loaded series in the browser).
    limit: int = Query(100, ge=1, le=200),
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> ContextTraceResponse:
    """The Context Compiler · Trace Inspector's data source (spec §11).

    Returns the ordered SERIES of per-turn contextBudget frames VERBATIM (raw_tokens,
    reduction_pct, target, status_flags, retrieval_mode, intent, entity_presence, the
    trace spans, the allocation breakdown) plus the user message that drove each turn —
    everything the Inspector renders per turn. Owner-gated like the sibling routes;
    windowed to the most recent `limit` turns, returned oldest-first."""
    exists = await pool.fetchval(
        "SELECT 1 FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="session not found")

    # LEFT JOIN the parent user turn so the Inspector shows what the author typed.
    # branch_id=0 pins the live timeline; only assistant turns carrying a frame.
    rows = await pool.fetch(
        """
        SELECT a.sequence_num, a.created_at, a.input_tokens, a.output_tokens,
               a.context_breakdown, u.content AS user_message
        FROM (
            SELECT sequence_num, created_at, input_tokens, output_tokens,
                   context_breakdown, parent_message_id
            FROM chat_messages
            WHERE session_id=$1 AND owner_user_id=$2 AND branch_id=0
              AND role='assistant' AND context_breakdown IS NOT NULL
            ORDER BY sequence_num DESC
            LIMIT $3
        ) a
        LEFT JOIN chat_messages u ON u.message_id = a.parent_message_id
        ORDER BY a.sequence_num ASC
        """,
        str(session_id), user_id, limit,
    )

    items: list[ContextTracePoint] = []
    for r in rows:
        frame = _parse_content_parts(r["context_breakdown"])
        # Skip resume-path turns that persisted no measured frame (no breakdown) —
        # they have no allocation/telemetry for the Inspector to render.
        if not isinstance(frame, dict) or not frame.get("breakdown"):
            continue
        items.append(
            ContextTracePoint(
                sequence_num=r["sequence_num"],
                created_at=r["created_at"],
                input_tokens=r["input_tokens"],
                output_tokens=r["output_tokens"],
                user_message=r["user_message"],
                frame=frame,
            )
        )
    return ContextTraceResponse(items=items)


@router.get("/{session_id}/branches")
async def list_branches(
    session_id: UUID,
    sequence_num: int = Query(..., description="Fork point sequence number"),
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """List all branch_ids that have messages after the given sequence_num."""
    exists = await pool.fetchval(
        "SELECT 1 FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="session not found")

    rows = await pool.fetch(
        """
        SELECT DISTINCT branch_id,
               MIN(created_at) AS created_at,
               COUNT(*) AS message_count
        FROM chat_messages
        WHERE session_id=$1 AND sequence_num > $2
        GROUP BY branch_id
        ORDER BY branch_id ASC
        """,
        str(session_id), sequence_num,
    )
    return {
        "sequence_num": sequence_num,
        "branches": [
            {
                "branch_id": r["branch_id"],
                "message_count": r["message_count"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
    }


@router.post("/{session_id}/messages")
async def send_message(
    session_id: UUID,
    body: SendMessageRequest,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
    x_loreweave_stream_format: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
) -> StreamingResponse:
    # Verify session ownership and get model info
    session = await pool.fetchrow(
        "SELECT * FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    if session["status"] == "archived":
        raise HTTPException(status_code=409, detail="session is archived")

    model_source = session["model_source"]
    model_ref = str(session["model_ref"])

    # ── Chat & AI settings (M3) — resolve grounding on/off for this turn:
    # session override ▸ account default ▸ system default (ON). OFF short-circuits
    # retrieval + the T4 story-state net (the "grounding always on, no toggle"
    # silent default is now a real, per-user/per-session control).
    _grounding_pref = session.get("grounding_enabled")
    _ctx_override = session.get("context_overrides") or {}
    if isinstance(_ctx_override, str):
        import json as _json
        _ctx_override = _json.loads(_ctx_override) or {}
    _ctx_mode = _ctx_override.get("mode")
    # permission_mode is per-turn (default None ⇒ omitted); fall back to the
    # account default before "write" so the panel's "tool authority" is honored.
    _permission = body.permission_mode
    if _grounding_pref is None or _ctx_mode is None or _permission is None:
        from app.db.user_chat_ai_prefs import get_prefs
        _acct_prefs = await get_prefs(pool, owner_user_id=user_id)
        if _grounding_pref is None:
            _grounding_pref = _acct_prefs.grounding.get("grounding_enabled")
        if _ctx_mode is None:
            _ctx_mode = _acct_prefs.context.get("mode")
        if _permission is None:
            _permission = _acct_prefs.behavior.get("permission_mode")
    turn_permission_mode = _permission or "write"
    turn_grounding_enabled = True if _grounding_pref is None else bool(_grounding_pref)
    # Chat & AI settings (M4) — long-work context mode. 'off' force-disables the
    # context-budget tiers (T5 gate / T4 story-state) for this session regardless
    # of the deploy env default; 'auto'/'on' defer to the env ceiling (§5). The
    # fine-grained per-tier + compaction-path consumption is tracked separately
    # (D-CHATAI-M4-TIER-CONSUMPTION) — these tiers are eval-proven inert + default-off.
    turn_context_mode = _ctx_mode or "auto"

    # ── P4 REG-P4-01: expand a user-authored slash command (/name args) in place —
    # BEFORE the user message is persisted + streamed, so both the transcript and the
    # model see the template. Gated on a leading non-builtin /name so a normal turn
    # never hits the registry; degrades to pass-through (original text) on any failure.
    message_content = body.content
    try:
        from app.client.registry_commands_client import (
            expand_command,
            get_commands_client,
            looks_like_command,
        )

        if looks_like_command(message_content):
            _book_id = str(session["project_id"]) if session["project_id"] else ""
            _cmds = await get_commands_client().get_commands(str(user_id), book_id=_book_id)
            _expanded, _cmd_name = expand_command(message_content, _cmds)
            if _cmd_name:
                message_content = _expanded
    except Exception:  # noqa: BLE001 — a command is enrichment, never load-bearing
        logger.warning("command expansion failed (pass-through)", exc_info=False)

    # Edit flow: move old messages to a branch, insert new on active branch (0).
    # Non-edit flow: simple insert + increment.
    parent_message_id: str | None = None
    branched_count = 0
    # DBT-11 — resolve the local day BEFORE acquiring the connection: resolve_local_date
    # may hit auth on a cache miss, and holding a pooled conn (let alone an open
    # transaction) across an external call risks pool starvation on an auth hiccup.
    local_date = await resolve_local_date(user_id)
    async with pool.acquire() as conn:
        async with conn.transaction():
            if body.edit_from_sequence is not None:
                parent_message_id = await conn.fetchval(
                    """
                    SELECT message_id::text FROM chat_messages
                    WHERE session_id=$1 AND sequence_num=$2 AND branch_id=0
                    """,
                    str(session_id), body.edit_from_sequence,
                )
                # Allocate next branch_id for this session
                next_branch = await conn.fetchval(
                    "SELECT COALESCE(MAX(branch_id), 0) + 1 FROM chat_messages WHERE session_id=$1",
                    str(session_id),
                )
                # Move active messages after edit point to new branch (soft-hide, not delete)
                result = await conn.execute(
                    """
                    UPDATE chat_messages
                    SET branch_id = $3
                    WHERE session_id=$1 AND sequence_num > $2 AND branch_id=0
                    """,
                    str(session_id), body.edit_from_sequence, next_branch,
                )
                # asyncpg returns "UPDATE N" — extract count safely
                try:
                    branched_count = int(result.split()[-1])
                except (ValueError, IndexError):
                    branched_count = 0
                # W3 compact interplay (review-impl H1): editing a message that
                # sits INSIDE the compacted region rewrites the timeline the
                # summary described AND re-anchors new seqs BELOW the boundary
                # (splice would then load zero user messages). Clear the compact
                # in the same transaction — full history is loadable again.
                # (.get works on asyncpg Record and dict test-mocks alike)
                compacted_before = session.get("compacted_before_seq")
                if compacted_before is not None and body.edit_from_sequence < compacted_before:
                    await conn.execute(
                        "UPDATE chat_sessions SET compact_summary = NULL, "
                        "compacted_before_seq = NULL, updated_at = now() "
                        "WHERE session_id = $1",
                        str(session_id),
                    )

            seq = await conn.fetchval(
                """
                SELECT COALESCE(MAX(sequence_num), 0) + 1
                FROM chat_messages WHERE session_id=$1 AND branch_id=0
                """,
                str(session_id),
            )
            await conn.execute(
                """
                INSERT INTO chat_messages
                  (session_id, owner_user_id, role, content, sequence_num, parent_message_id, branch_id, local_date)
                VALUES ($1,$2,'user',$3,$4,$5, 0, $6)
                """,
                str(session_id), user_id, message_content, seq, parent_message_id,
                local_date,  # DBT-11 — bucket by the user's LOCAL day (resolved before acquire)
            )
            # Update message count: subtract branched msgs, add 1 for new user msg
            await conn.execute(
                """
                UPDATE chat_sessions
                SET message_count = GREATEST(message_count - $2 + 1, 0), updated_at = now()
                WHERE session_id = $1
                """,
                str(session_id), branched_count,
            )

    # Resolve credentials
    try:
        creds = await get_provider_client().resolve(model_source, model_ref, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"credential resolution failed: {exc}")

    billing = get_billing_client()

    stream_format = _resolve_stream_format(x_loreweave_stream_format)

    headers = {
        "x-vercel-ai-ui-message-stream": "v1",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        # Echo the negotiated format so the client can confirm what it's parsing.
        STREAM_FORMAT_HEADER: stream_format,
    }
    return StreamingResponse(
        stream_response(
            session_id=str(session_id),
            user_message_content=message_content,
            user_id=user_id,
            model_source=model_source,
            model_ref=model_ref,
            creds=creds,
            pool=pool,
            billing=billing,
            parent_message_id=parent_message_id,
            context=body.context,
            thinking=body.thinking,
            # W4 — granular effort from the input-bar dropdown (fast|standard|deep).
            reasoning_effort=body.reasoning_effort,
            stream_format=stream_format,
            editor_context=body.editor_context.model_dump() if body.editor_context else None,
            book_context=body.book_context.model_dump() if body.book_context else None,
            # T4c: admin surface marker (body) + RS256 admin token (header).
            # The token rides the header only — bearer hygiene (§6.7).
            admin_context=body.admin_context.model_dump() if body.admin_context else None,
            admin_token=x_admin_token,
            disable_tools=body.disable_tools,
            display_language=body.display_language,
            enabled_tools=body.enabled_tools,
            enabled_skills=body.enabled_skills,
            # #09 Lane A — presence enables the studio dock-nav frontend tools.
            studio_context=body.studio_context.model_dump() if body.studio_context else None,
            # RAID Wave C2 (DR-C2) — HITL permission mode, resolved body ▸ account
            # default ▸ "write" (Chat & AI settings).
            permission_mode=turn_permission_mode,
            grounding_enabled=turn_grounding_enabled,
            context_mode=turn_context_mode,
        ),
        media_type="text/event-stream",
        headers=headers,
    )


@router.post("/{session_id}/tool-results")
async def submit_tool_result(
    session_id: UUID,
    body: ToolResultRequest,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
    x_admin_token: str | None = Header(default=None),
) -> StreamingResponse:
    """ARCH-1 C6 — resume a suspended run after the FE executed a frontend tool.

    The editor `<Chat>` calls this once the user applies/dismisses a proposed
    edit; chat-service rehydrates the suspended run, appends the tool result,
    and streams the agent's 2nd pass (same AG-UI SSE contract)."""
    session = await pool.fetchrow(
        "SELECT * FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    try:
        creds = await get_provider_client().resolve(
            session["model_source"], str(session["model_ref"]), user_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"credential resolution failed: {exc}")

    billing = get_billing_client()
    headers = {
        "x-vercel-ai-ui-message-stream": "v1",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        STREAM_FORMAT_HEADER: "agui",  # frontend tools are agui-only
    }
    return StreamingResponse(
        resume_stream_response(
            session_id=str(session_id),
            user_id=user_id,
            run_id=body.run_id,
            tool_call_id=body.tool_call_id,
            outcome=body.outcome,
            applied_text=body.applied_text,
            result=body.result,
            creds=creds,
            pool=pool,
            billing=billing,
            stream_format="agui",
            # T4c: on resume of an admin-surface run, re-present the admin token
            # so a re-proposed System action again routes to /mcp/admin.
            admin_token=x_admin_token,
        ),
        media_type="text/event-stream",
        headers=headers,
    )


@router.delete("/{session_id}/messages/{message_id}", status_code=204)
async def delete_message(
    session_id: UUID,
    message_id: UUID,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> None:
    # Verify ownership
    exists = await pool.fetchval(
        "SELECT 1 FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if not exists:
        raise HTTPException(status_code=404, detail="session not found")

    result = await pool.execute(
        "DELETE FROM chat_messages WHERE message_id=$1 AND session_id=$2 AND owner_user_id=$3",
        str(message_id), str(session_id), user_id,
    )
    try:
        deleted = int(result.split()[-1])
    except (ValueError, IndexError):
        deleted = 0

    if deleted == 0:
        raise HTTPException(status_code=404, detail="message not found")

    # Update session message count
    await pool.execute(
        """
        UPDATE chat_sessions
        SET message_count = GREATEST(message_count - 1, 0), updated_at = now()
        WHERE session_id = $1
        """,
        str(session_id),
    )
