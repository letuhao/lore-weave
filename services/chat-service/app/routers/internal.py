"""FD-2 — internal service-to-service endpoints (X-Internal-Token).

Exposes a chat turn's text so worker-ai can extract chat knowledge into the KG.
The `chat.turn_completed` outbox event carries only ids + content *lengths* (not
the prose), so the extraction worker must fetch the turn text by id from here.

W1 (folded W0 telemetry) — GET /internal/tool-health: per-tool call/error rates
aggregated from chat_messages.tool_calls so MCP-reliability work is measurable.
"""

import json
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from loreweave_internal_client import build_internal_client
from pydantic import BaseModel

from app.config import settings
from app.deps import get_db
from app.middleware.trace_id import trace_id_var

router = APIRouter(prefix="/internal/chat", tags=["internal"])

# W1 — sibling router WITHOUT the /chat segment so the telemetry route is
# GET /internal/tool-health (the W0/W1 contract), same internal-token guard.
telemetry_router = APIRouter(prefix="/internal", tags=["internal"])


def require_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
    """Guard internal endpoints with the shared service token (same contract the
    chat-service clients use for provider/billing internal calls)."""
    if not settings.internal_service_token or x_internal_token != settings.internal_service_token:
        raise HTTPException(status_code=401, detail="invalid internal token")


class InternalCreateSession(BaseModel):
    """Create a chat session on behalf of a JWT-verified caller (roleplay-service
    start-orchestration). The OWNER is in the body because the caller already
    authenticated the user — the X-Internal-Token gates the trust boundary. The
    `working_memory_seed` is the frozen charter (+ optional rubric sidecar), the
    same shape `/templates/{id}/start` writes."""

    owner_user_id: UUID
    title: str
    model_source: str
    model_ref: UUID
    system_prompt: str | None = None
    working_memory_seed: dict | None = None


@router.post("/sessions", dependencies=[Depends(require_internal_token)], status_code=status.HTTP_201_CREATED)
async def internal_create_session(
    body: InternalCreateSession, db: asyncpg.Pool = Depends(get_db)
) -> dict:
    """Create a `chat_sessions` row carrying a `working_memory_seed`. The exact
    INSERT `/templates/{id}/start` uses — extracted so roleplay-service (the new
    goal authority) can own scripts while chat-service still owns the session +
    turn loop + M3 anchoring + M6 debrief."""
    row = await db.fetchrow(
        """
        INSERT INTO chat_sessions
          (owner_user_id, title, model_source, model_ref, system_prompt,
           project_id, working_memory_seed)
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
        RETURNING session_id
        """,
        str(body.owner_user_id),
        body.title,
        body.model_source,
        str(body.model_ref),
        body.system_prompt,
        None,
        json.dumps(body.working_memory_seed) if body.working_memory_seed is not None else None,
    )
    return {"session_id": str(row["session_id"])}


@router.get("/turns/{message_id}/text", dependencies=[Depends(require_internal_token)])
async def get_turn_text(message_id: UUID, db: asyncpg.Pool = Depends(get_db)) -> dict:
    """Return the full turn text for an ASSISTANT `message_id` — the user question
    (the assistant message's parent) joined with the assistant answer, the
    meaningful unit for chat→KG extraction. `found=false` (+ empty text) when the
    message doesn't exist, so the caller can skip gracefully rather than retry."""
    row = await db.fetchrow(
        "SELECT role, content, parent_message_id FROM chat_messages WHERE message_id = $1",
        message_id,
    )
    if row is None:
        return {"found": False, "text": ""}
    parts: list[str] = []
    # The turn-completed event always carries the ASSISTANT message id (its
    # parent is the user question). Only walk to the parent for an assistant
    # message — guards against a caller passing a user-message id (whose parent
    # would be a *prior* assistant turn, which would wrongly prepend unrelated
    # text). A non-assistant message degrades to its own content only.
    parent_id = row["parent_message_id"] if row["role"] == "assistant" else None
    if parent_id is not None:
        parent = await db.fetchrow(
            "SELECT content FROM chat_messages WHERE message_id = $1", parent_id,
        )
        if parent and (parent["content"] or "").strip():
            parts.append(parent["content"].strip())
    if (row["content"] or "").strip():
        parts.append(row["content"].strip())
    return {"found": True, "text": "\n\n".join(parts)}


# WS-1.8 (spec 06 §Q10) — the distiller's day-window read. The map-reduce worker has no user
# JWT, so it fetches a day's assistant conversation over the internal-token trust boundary. Two
# safety properties are enforced HERE, server-side, not left to the caller:
#   1. ASSISTANT-ONLY (spec 02 §Q1 discriminator): filtered to sessions bound to the caller-named
#      diary `book_id`. A user's novel/roleplay chats (a different book_id, or NULL) are never
#      returned — the distiller cannot accidentally journal non-assistant conversation.
#   2. WINDOW-CAPPED: `limit`-bounded with a hard ceiling, and `truncated` signalled, so an
#      enormous day can never stream unbounded rows into the worker (T20/T38 cost containment).
# owner_user_id is required and filtered on the message row itself (defense in depth alongside the
# session join). Ordered chronologically ACROSS sessions (created_at, then sequence_num) because a
# single local day may span several assistant sessions. Per-message `tool_names` are returned so
# the map step can apply the self-feeding guard (§Q9 — skip assistant turns that quoted recall).
#
# DISCRIMINATOR (sealed T-4): the assistant-only property is `s.session_kind = 'assistant'` — an
# EXPLICIT column, not a book_id=diary derivation (the day-window read, the voice gate, and search
# scoping all key off the same flag; an explicit flag is self-describing and future-proofs a coach
# session that is assistant-family but not diary-bound). Cross-USER reads are fully blocked by the
# owner_user_id filter. `book_id` is an OPTIONAL extra scope (the distiller passes the diary book so
# a user with multiple assistant contexts is disambiguated); the diary-kind taint is enforced
# authoritatively at the WRITE seam (book-service rejects an entry to any non-diary/other-owner book).
DAY_WINDOW_DEFAULT_LIMIT = 5000
DAY_WINDOW_MAX_LIMIT = 50000


@router.get("/messages/day-window", dependencies=[Depends(require_internal_token)])
async def day_window(
    user_id: UUID = Query(...),
    local_date: date = Query(..., description="the LOCAL calendar day to distill (chat_messages.local_date)"),
    book_id: UUID | None = Query(None, description="optional extra scope: the diary book to restrict to"),
    limit: int = Query(default=DAY_WINDOW_DEFAULT_LIMIT, ge=1, le=DAY_WINDOW_MAX_LIMIT),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Return one user's assistant-session messages for one local day, chronologically, capped.

    Non-error messages only (an error turn is not journalable content). `truncated=true` means the
    day exceeded `limit` — the returned window is the OLDEST `limit` messages (ORDER BY … LIMIT), so
    a huge day degrades to a bounded prefix rather than failing; the caller decides how to proceed
    (period-digest / attach-as-document paths live in the worker, spec §Q4/§T38)."""
    rows = await db.fetch(
        """
        SELECT m.message_id, m.session_id, m.role, m.content, m.sequence_num,
               m.local_date, m.created_at,
               (
                 SELECT array_agg(tc->>'tool')
                 FROM jsonb_array_elements(COALESCE(m.tool_calls, '[]'::jsonb)) AS tc
                 WHERE tc->>'tool' IS NOT NULL
               ) AS tool_names
        FROM chat_messages m
        JOIN chat_sessions s ON s.session_id = m.session_id
        WHERE m.owner_user_id = $1
          AND s.session_kind = 'assistant'
          AND ($2::uuid IS NULL OR s.book_id = $2)
          AND m.local_date = $3
          AND m.is_error = false
          -- WS-2.9 (spec 09 §Q6) — a "don't remember this" turn (grounding off) is NOT distilled.
          AND m.exclude_from_memory = false
        ORDER BY m.created_at, m.sequence_num
        LIMIT $4
        """,
        str(user_id),
        str(book_id) if book_id else None,
        local_date,
        limit + 1,  # fetch one extra to detect truncation without a second COUNT query
    )
    truncated = len(rows) > limit
    rows = rows[:limit]
    messages = [
        {
            "message_id": str(r["message_id"]),
            "session_id": str(r["session_id"]),
            "role": r["role"],
            "content": r["content"] or "",
            "sequence_num": r["sequence_num"],
            "local_date": r["local_date"].isoformat() if r["local_date"] else None,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "tool_names": list(r["tool_names"]) if r["tool_names"] else [],
        }
        for r in rows
    ]
    return {
        "user_id": str(user_id),
        "book_id": str(book_id) if book_id else None,
        "local_date": local_date.isoformat(),
        "message_count": len(messages),
        "truncated": truncated,
        "messages": messages,
    }


class DistillTrigger(BaseModel):
    """A1 / P-10 / WS-3.0 — the "End my day" trigger body. `book_id`, `model_source`, `model_ref`,
    `entry_zone` are now OPTIONAL and resolve SERVER-SIDE when omitted (D-B1), so a HEADLESS scheduled
    run (WS-3.2) can POST only `{user_id}`. A caller that supplies them (the FE "End my day") is
    unchanged. `entry_date`/`entry_zone` default server-side (D-R14: never trust a client calendar day)."""

    user_id: UUID
    # Optional (WS-3.0): omitted → resolve the user's diary book / their default distill model / their tz.
    book_id: UUID | None = None
    model_source: str | None = None
    model_ref: UUID | None = None
    language: str = "en"
    # entry_date is OPTIONAL for internal/catch-up use (the P-10 sweep distills a specific past day
    # and computes that date SERVER-side). ⚠️ CONTRACT (review LOW-4): when the public "End my day"
    # is wired, the gateway MUST compute entry_date server-side and NEVER forward a user-supplied
    # value — a client-controlled calendar day could overwrite/mis-bucket a historical entry. Today
    # this route is X-Internal-Token-only with no public caller, so it is a contract note, not a hole.
    entry_date: date | None = None  # default: today in entry_zone (server-computed on omission)
    entry_zone: str | None = None   # omitted → resolve the user's IANA zone from prefs.timezone (else UTC)


@router.post("/assistant/distill", dependencies=[Depends(require_internal_token)], status_code=status.HTTP_202_ACCEPTED)
async def trigger_distill(body: DistillTrigger) -> dict:
    """Enqueue an `assistant.distill` job — the "End my day" trigger. worker-ai's DistillConsumer
    runs the map-reduce → diary-entry pipeline. Returns 202 with the enqueued entry_date + message id.

    `entry_date` is SERVER-authoritative (D-R14): if the caller omits it we stamp today's date in
    `entry_zone` — a client-controlled calendar day could otherwise mis-bucket or overwrite history.

    WS-3.0 (D-B1) — `book_id`/`model`/`entry_zone` resolve SERVER-SIDE when omitted, so a headless
    scheduled run (WS-3.2) posts only `{user_id}`: the diary book from book-service, the distill model
    from provider-registry (the user's `distill` default, falling back to `chat`), the zone from auth."""
    from app.events.distill_enqueue import enqueue_distill

    book_id, model_source, model_ref, entry_zone = await _resolve_distill_context(body)

    entry_date = body.entry_date or datetime.now(timezone.utc).date()
    try:
        msg_id = await enqueue_distill(
            user_id=str(body.user_id),
            book_id=book_id,
            entry_date=entry_date.isoformat(),
            entry_zone=entry_zone,
            language=body.language or "en",
            model_source=model_source,
            model_ref=model_ref,
        )
    except Exception as exc:  # noqa: BLE001 — a lost enqueue = a silently un-journaled day; surface it.
        raise HTTPException(status_code=503, detail=f"failed to enqueue distill: {exc}") from exc
    return {"enqueued": True, "entry_date": entry_date.isoformat(), "message_id": msg_id}


async def _resolve_distill_context(body: "DistillTrigger") -> tuple[str, str, str, str]:
    """WS-3.0 (D-B1) — resolve (book_id, model_source, model_ref, entry_zone) for a distill, filling any
    field the caller omitted from server-side sources. Returns strings ready for the enqueue. Raises 422
    when a REQUIRED piece can't be resolved (no diary / no distill model) — a scheduled tick must log +
    skip that user, never silently enqueue a job that can't run (silent-success is a bug)."""
    from app.client.auth_client import get_auth_client
    from app.client.provider_client import get_provider_client

    user_id = str(body.user_id)

    # 1. book_id — the caller's diary. book-service resolves it for ANY lifecycle without creating one.
    book_id = str(body.book_id) if body.book_id else None
    if book_id is None:
        try:
            async with build_internal_client(
                settings.book_service_url, internal_token=settings.internal_service_token,
                timeout_s=5, trace_id_provider=trace_id_var.get,
            ) as client:
                resp = await client.get("/internal/books/diary", params={"user_id": user_id})
            if resp.status_code == 200:
                book_id = resp.json().get("book_id")
        except Exception:  # noqa: BLE001 — treated as unresolved below (422), never a 500 into the tick.
            book_id = None
        if not book_id:
            raise HTTPException(status_code=422, detail="no diary book for user (provision the assistant first)")

    # 2. model — the caller's supplied model, else the user's `distill` default, else the `chat` default.
    model_source = body.model_source
    model_ref = str(body.model_ref) if body.model_ref else None
    if not model_ref:
        provider = get_provider_client()
        resolved = await provider.get_default_model("distill", user_id) \
            or await provider.get_default_model("chat", user_id)
        if resolved is None:
            raise HTTPException(status_code=422,
                                detail="no distill/chat default model configured for user")
        model_source, model_ref = resolved
    model_source = model_source or "user_model"

    # 3. entry_zone — the user's IANA zone (best-effort; UTC on any miss — the day bucket degrades safely).
    entry_zone = body.entry_zone
    if not entry_zone:
        entry_zone = await get_auth_client().get_user_timezone(user_id) or "UTC"

    return book_id, model_source, model_ref, entry_zone


class ReextractTrigger(BaseModel):
    """WS-2.6a legs 2+3 (D17) — the CORRECTION re-extract trigger body. The gateway `/v1/assistant/correct`
    calls this AFTER book-service amends the day's entry (leg 1); it forwards the corrected `body` (the
    same text it sent to amend) + the server-authoritative `entry_date` the amend returned, so the
    re-extract reconciles exactly the day that was corrected."""

    user_id: UUID
    book_id: UUID
    entry_date: date          # the corrected day — server-authoritative (from the amend response)
    body: str                 # the corrected entry text
    model_source: str
    model_ref: UUID
    language: str = "en"


@router.post("/assistant/reextract", dependencies=[Depends(require_internal_token)], status_code=status.HTTP_202_ACCEPTED)
async def trigger_reextract(body: ReextractTrigger) -> dict:
    """WS-2.6a legs 2+3 (D17) — enqueue an `assistant.reextract` job so worker-ai re-extracts the
    corrected entry's facts to the inbox (leg 2) and invalidates the day's superseded facts (leg 3).
    Returns 202 with the entry_date + message id. A lost enqueue means the correction never reconciles,
    so a Redis failure surfaces as 503 (not swallowed)."""
    from app.events.distill_enqueue import enqueue_reextract

    corrected = (body.body or "").strip()
    if not corrected:
        raise HTTPException(status_code=422, detail="body required (a correction must have text)")
    try:
        msg_id = await enqueue_reextract(
            user_id=str(body.user_id),
            book_id=str(body.book_id),
            entry_date=body.entry_date.isoformat(),
            body=corrected,
            language=body.language or "en",
            model_source=body.model_source,
            model_ref=str(body.model_ref),
        )
    except Exception as exc:  # noqa: BLE001 — a lost enqueue = a correction that never reconciles.
        raise HTTPException(status_code=503, detail=f"failed to enqueue reextract: {exc}") from exc
    return {"enqueued": True, "entry_date": body.entry_date.isoformat(), "message_id": msg_id}


class WeeklyRollupTrigger(BaseModel):
    """WS-3.7 — the scheduler posts ONLY {user_id}; book/model/tz resolve server-side (WS-3.0) and the
    week defaults to the last 7 completed days (ending yesterday, server-authoritative — D-R14)."""

    user_id: UUID
    book_id: UUID | None = None
    model_source: str | None = None
    model_ref: UUID | None = None
    language: str = "en"
    week_start: date | None = None
    week_end: date | None = None


@router.post("/assistant/weekly-rollup", dependencies=[Depends(require_internal_token)], status_code=status.HTTP_202_ACCEPTED)
async def trigger_weekly_rollup(body: WeeklyRollupTrigger) -> dict:
    """WS-3.7 — enqueue a weekly-rollup job (a summary DRAFT over the week's confirmed diary facts).
    Resolves book/model/tz server-side (WS-3.0); the week defaults to yesterday-minus-6 .. yesterday."""
    from app.events.distill_enqueue import enqueue_weekly_rollup

    # Reuse the WS-3.0 headless resolution (book + distill model + tz) — a DistillTrigger-shaped view.
    ctx = DistillTrigger(user_id=body.user_id, book_id=body.book_id,
                         model_source=body.model_source, model_ref=body.model_ref, language=body.language)
    book_id, model_source, model_ref, entry_zone = await _resolve_distill_context(ctx)

    today = datetime.now(timezone.utc).date()
    week_end = body.week_end or (today - timedelta(days=1))
    week_start = body.week_start or (week_end - timedelta(days=6))
    try:
        msg_id = await enqueue_weekly_rollup(
            user_id=str(body.user_id), book_id=book_id,
            week_start=week_start.isoformat(), week_end=week_end.isoformat(),
            entry_zone=entry_zone, language=body.language or "en",
            model_source=model_source, model_ref=model_ref,
        )
    except Exception as exc:  # noqa: BLE001 — a lost enqueue = a missed weekly review.
        raise HTTPException(status_code=503, detail=f"failed to enqueue weekly rollup: {exc}") from exc
    return {"enqueued": True, "week_start": week_start.isoformat(), "week_end": week_end.isoformat(),
            "message_id": msg_id}


@router.delete("/assistant/data", dependencies=[Depends(require_internal_token)])
async def erase_assistant_data(
    user_id: UUID = Query(...),
    book_id: UUID | None = Query(None, description="restrict to one diary book's assistant sessions"),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """D-R27 (human-authorized) — HARD-delete a user's ASSISTANT chat sessions (+ their messages, via
    ON DELETE CASCADE on chat_messages/chat_session_blocks/chat_suspended_runs). The distiller re-reads
    these messages (the day-window) to rebuild a diary entry, so erasing them is precisely what makes
    the erasure 're-index CAN'T resurrect': after this, a re-distill of ANY day finds no source
    messages → empty_day → no entry. SCOPED to `session_kind='assistant'` (a user's normal chat is
    NEVER touched) + `owner_user_id`; optionally to one diary `book_id`. Internal-token only."""
    if book_id is not None:
        result = await db.execute(
            "DELETE FROM chat_sessions WHERE owner_user_id=$1 AND session_kind='assistant' AND book_id=$2",
            str(user_id), str(book_id),
        )
    else:
        result = await db.execute(
            "DELETE FROM chat_sessions WHERE owner_user_id=$1 AND session_kind='assistant'",
            str(user_id),
        )
    # asyncpg returns a status string like "DELETE 3".
    deleted = int(result.split()[-1]) if result and result.startswith("DELETE") else 0
    return {"deleted_sessions": deleted}


@telemetry_router.get("/tool-health", dependencies=[Depends(require_internal_token)])
async def tool_health(
    days: int = Query(default=7, ge=1, le=90),
    db: asyncpg.Pool = Depends(get_db),
) -> dict:
    """W1 (W0 §7) — per-tool health over the last `days`: calls / errors /
    error_rate, unnested from `chat_messages.tool_calls` JSONB (entries carry
    {tool, ok, error}). This is the measurement loop for the MCP-reliability
    work: run before/after a fix wave, target hard-error rate < 10%.

    Cross-tenant aggregate (no per-user filter) → internal-token only.
    """
    rows = await db.fetch(
        """
        SELECT tc->>'tool'                                   AS tool,
               COUNT(*)::bigint                              AS calls,
               COUNT(*) FILTER (
                 WHERE NOT COALESCE((tc->>'ok')::boolean, false)
               )::bigint                                     AS errors
        FROM chat_messages m
        CROSS JOIN LATERAL jsonb_array_elements(m.tool_calls) AS tc
        WHERE m.tool_calls IS NOT NULL
          AND m.created_at >= now() - make_interval(days => $1)
          AND tc->>'tool' IS NOT NULL
        GROUP BY 1
        ORDER BY errors DESC, calls DESC
        """,
        days,
    )
    tools = [
        {
            "tool": r["tool"],
            "calls": int(r["calls"]),
            "errors": int(r["errors"]),
            "error_rate": round(int(r["errors"]) / int(r["calls"]), 4) if int(r["calls"]) else 0.0,
        }
        for r in rows
    ]
    total_calls = sum(t["calls"] for t in tools)
    total_errors = sum(t["errors"] for t in tools)
    return {
        "days": days,
        "total_calls": total_calls,
        "total_errors": total_errors,
        "error_rate": round(total_errors / total_calls, 4) if total_calls else 0.0,
        "tools": tools,
    }
