import json
import logging
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.deps import get_current_user, get_db
from app.models import (
    ChatSession,
    CompactSessionRequest,
    CompactSessionResponse,
    CreateSessionRequest,
    PatchSessionRequest,
    SearchResponse,
    SearchResult,
    SessionListResponse,
)
from app.services.compact_service import summarize_for_compaction
from app.services.compaction import summary_message
from app.services.token_budget import estimate_messages_tokens, estimate_tokens

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/chat/sessions", tags=["sessions"])


def _row_to_session(r: asyncpg.Record) -> ChatSession:
    gp = r["generation_params"]
    if isinstance(gp, str):
        gp = json.loads(gp)
    project_id = r.get("project_id")
    project_ids = list(r.get("project_ids") or [])
    # K-CLEAN-5 (D-K8-04): derive initial memory_mode from the project link.
    # `degraded` is intentionally NOT representable here — it's a
    # per-turn state that only the SSE stream knows. A fresh GET
    # always shows the project-derived state until the FE receives a
    # streaming `memory-mode` event with the actual value.
    # Track B B1(2): a set of ≥2 → "multi"; a single link → "static".
    if len(project_ids) >= 2:
        memory_mode = "multi"
    elif project_id or project_ids:
        memory_mode = "static"
    else:
        memory_mode = "no_project"
    return ChatSession(
        session_id=r["session_id"],
        owner_user_id=r["owner_user_id"],
        title=r["title"],
        model_source=r["model_source"],
        model_ref=r["model_ref"],
        system_prompt=r["system_prompt"],
        generation_params=gp if gp else {},
        is_pinned=r["is_pinned"],
        status=r["status"],
        message_count=r["message_count"],
        last_message_at=r["last_message_at"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
        # asyncpg.Record supports .get() (0.27+); matches the pattern used
        # by stream_service.py for test dict-mock compatibility.
        project_id=project_id,
        book_id=r.get("book_id"),
        project_ids=project_ids,
        memory_mode=memory_mode,
        composer_model_source=r.get("composer_model_source"),
        composer_model_ref=r.get("composer_model_ref"),
        planner_model_source=r.get("planner_model_source"),
        planner_model_ref=r.get("planner_model_ref"),
        enabled_tools=list(r.get("enabled_tools") or []),
        enabled_skills=list(r.get("enabled_skills") or []),
        activated_tools=list(r.get("activated_tools") or []),
        # W3 — the FE "compacted through message N" indicator.
        compacted_before_seq=r.get("compacted_before_seq"),
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ChatSession)
async def create_session(
    body: CreateSessionRequest,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> ChatSession:
    gp = json.dumps(body.generation_params.model_dump(exclude_unset=True)) if body.generation_params else "{}"
    row = await pool.fetchrow(
        """
        INSERT INTO chat_sessions (owner_user_id, title, model_source, model_ref, system_prompt, generation_params, project_id, composer_model_source, composer_model_ref, planner_model_source, planner_model_ref, project_ids, book_id)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11, $12::uuid[], $13)
        RETURNING *
        """,
        user_id, body.title, body.model_source, str(body.model_ref), body.system_prompt, gp,
        str(body.project_id) if body.project_id else None,
        body.composer_model_source,
        str(body.composer_model_ref) if body.composer_model_ref else None,
        body.planner_model_source,
        str(body.planner_model_ref) if body.planner_model_ref else None,
        [str(p) for p in body.project_ids] if body.project_ids else [],
        str(body.book_id) if body.book_id else None,
    )
    return _row_to_session(row)


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    session_status: str = Query("active", alias="status"),
    limit: int = Query(50, le=100),
    cursor: str | None = None,
    book_id: UUID | None = None,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> SessionListResponse:
    # Placeholders are numbered in the order args are appended below, so a
    # filter's position always matches however many args precede it —
    # appending book_id BEFORE cursor (rather than after, unconditionally)
    # would silently shift cursor's $N and misbind it.
    args: list = [user_id, session_status, limit + 1]
    book_filter = ""
    if book_id is not None:
        args.append(str(book_id))
        book_filter = f" AND book_id=${len(args)}"
    cursor_filter = ""
    if cursor:
        args.append(cursor)
        cursor_filter = f" AND last_message_at < ${len(args)}"
    rows = await pool.fetch(
        f"""
        SELECT * FROM chat_sessions
        WHERE owner_user_id=$1 AND status=$2{book_filter}{cursor_filter}
        ORDER BY is_pinned DESC, last_message_at DESC NULLS LAST, session_id DESC
        LIMIT $3
        """,
        *args,
    )
    has_more = len(rows) > limit
    items = [_row_to_session(r) for r in rows[:limit]]
    next_cursor = str(items[-1].last_message_at) if has_more and items else None
    return SessionListResponse(items=items, next_cursor=next_cursor)


@router.get("/search", response_model=SearchResponse)
async def search_messages(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(20, le=50),
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> SearchResponse:
    rows = await pool.fetch(
        """
        SELECT m.session_id, s.title AS session_title,
               m.message_id, m.role,
               ts_headline('english', m.content, plainto_tsquery('english', $2),
                 'StartSel=**, StopSel=**, MaxWords=40, MinWords=20') AS snippet,
               m.created_at
        FROM chat_messages m
        JOIN chat_sessions s ON s.session_id = m.session_id
        WHERE m.owner_user_id = $1
          AND to_tsvector('english', m.content) @@ plainto_tsquery('english', $2)
        ORDER BY m.created_at DESC
        LIMIT $3
        """,
        user_id, q, limit,
    )
    return SearchResponse(items=[
        SearchResult(
            session_id=r["session_id"],
            session_title=r["session_title"],
            message_id=r["message_id"],
            role=r["role"],
            snippet=r["snippet"],
            created_at=r["created_at"],
        )
        for r in rows
    ])


@router.get("/{session_id}", response_model=ChatSession)
async def get_session(
    session_id: UUID,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> ChatSession:
    row = await pool.fetchrow(
        "SELECT * FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="session not found")
    return _row_to_session(row)


@router.patch("/{session_id}", response_model=ChatSession)
async def patch_session(
    session_id: UUID,
    body: PatchSessionRequest,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> ChatSession:
    row = await pool.fetchrow(
        "SELECT * FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="session not found")
    # JSONB merge: existing || new (new keys overwrite, existing keys preserved)
    # Use exclude_unset (not exclude_none) so explicit null values can clear keys
    gp_patch = None
    if body.generation_params is not None:
        gp_patch = json.dumps(body.generation_params.model_dump(exclude_unset=True))

    # K5: project_id has 3-state semantics — explicit None to clear,
    # explicit UUID to set, omitted to leave alone. We can't use
    # COALESCE because COALESCE($X, project_id) treats NULL as "unset"
    # rather than "clear". Detect "field present in body" via Pydantic's
    # model_fields_set.
    set_project = "project_id" in body.model_fields_set
    project_id_value = str(body.project_id) if body.project_id else None

    # A2A phase-2: composer model — same set/clear-via-fields_set semantics.
    # Presence of composer_model_ref in the body drives both columns.
    set_composer = "composer_model_ref" in body.model_fields_set
    composer_source_value = body.composer_model_source
    composer_ref_value = str(body.composer_model_ref) if body.composer_model_ref else None

    # D-PLAN-PLANNER-DEFAULT-FE phase 2: per-session planner model — same semantics.
    set_planner = "planner_model_ref" in body.model_fields_set
    planner_source_value = body.planner_model_source
    planner_ref_value = str(body.planner_model_ref) if body.planner_model_ref else None

    set_enabled_tools = "enabled_tools" in body.model_fields_set
    set_enabled_skills = "enabled_skills" in body.model_fields_set
    set_activated_tools = "activated_tools" in body.model_fields_set

    # Track B B1(2) — multi-KG grounding set. Presence in the body drives the
    # write (explicit [] clears back to single-project); omitted leaves alone.
    set_project_ids = "project_ids" in body.model_fields_set
    project_ids_value = [str(p) for p in body.project_ids] if body.project_ids else []

    row = await pool.fetchrow(
        """
        UPDATE chat_sessions SET
          title                 = COALESCE($3, title),
          system_prompt         = COALESCE($4, system_prompt),
          model_source          = COALESCE($5, model_source),
          model_ref             = COALESCE($6, model_ref),
          status                = COALESCE($7, status),
          generation_params     = CASE WHEN $8::jsonb IS NOT NULL THEN generation_params || $8::jsonb ELSE generation_params END,
          is_pinned             = COALESCE($9, is_pinned),
          project_id            = CASE WHEN $10::boolean THEN $11::uuid ELSE project_id END,
          composer_model_source = CASE WHEN $12::boolean THEN $13 ELSE composer_model_source END,
          composer_model_ref    = CASE WHEN $12::boolean THEN $14::uuid ELSE composer_model_ref END,
          planner_model_source  = CASE WHEN $15::boolean THEN $16 ELSE planner_model_source END,
          planner_model_ref     = CASE WHEN $15::boolean THEN $17::uuid ELSE planner_model_ref END,
          enabled_tools         = CASE WHEN $18::boolean THEN $19::text[] ELSE enabled_tools END,
          enabled_skills        = CASE WHEN $20::boolean THEN $21::text[] ELSE enabled_skills END,
          activated_tools       = CASE WHEN $22::boolean THEN $23::text[] ELSE activated_tools END,
          project_ids           = CASE WHEN $24::boolean THEN $25::uuid[] ELSE project_ids END,
          updated_at            = now()
        WHERE session_id=$1 AND owner_user_id=$2
        RETURNING *
        """,
        str(session_id), user_id,
        body.title, body.system_prompt,
        body.model_source, str(body.model_ref) if body.model_ref else None,
        body.status, gp_patch, body.is_pinned,
        set_project, project_id_value,
        set_composer, composer_source_value, composer_ref_value,
        set_planner, planner_source_value, planner_ref_value,
        set_enabled_tools, body.enabled_tools or [],
        set_enabled_skills, body.enabled_skills or [],
        set_activated_tools, body.activated_tools or [],
        set_project_ids, project_ids_value,
    )
    return _row_to_session(row)


@router.post("/{session_id}/compact", response_model=CompactSessionResponse)
async def compact_session(
    session_id: UUID,
    body: CompactSessionRequest,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> CompactSessionResponse:
    """W3 — manual steerable compact, PERSISTED on the session.

    Summarizes every message older than the last ``keep_recent`` with the
    session's OWN model (the user's ``instructions`` steer what survives) and
    stores {compact_summary, compacted_before_seq} on chat_sessions, so every
    later turn — on every device — loads the summary instead of the old turns.

    Re-compact is idempotent-ish: messages already covered by a previous
    compact are NOT re-read; the previous summary is folded in as the first
    "message" of the new summarizer input, so nothing is lost twice.

    ``{"clear": true}`` (mutually exclusive with instructions/keep_recent)
    wipes the stored compact instead — every later turn loads full history.
    """
    if body.clear and (body.instructions is not None or "keep_recent" in body.model_fields_set):
        raise HTTPException(
            status_code=422,
            detail="clear is mutually exclusive with instructions/keep_recent",
        )

    row = await pool.fetchrow(
        "SELECT model_source, model_ref, compact_summary, compacted_before_seq "
        "FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="session not found")

    prev_summary = row.get("compact_summary")
    prev_before_seq = row.get("compacted_before_seq")

    if body.clear:
        # Clear is idempotent — NULLing an already-clear session is a no-op.
        await pool.execute(
            "UPDATE chat_sessions SET compact_summary=NULL, compacted_before_seq=NULL, "
            "updated_at=now() WHERE session_id=$1 AND owner_user_id=$2",
            str(session_id), user_id,
        )
        return CompactSessionResponse(
            summary_tokens=0,
            compacted_message_count=0,
            compacted_before_seq=None,
            tokens_before_estimate=0,
            tokens_after_estimate=0,
            cleared=True,
        )

    # Everything already covered by a previous compact is represented by
    # prev_summary — load only what that compact did NOT cover.
    if prev_before_seq is not None:
        msg_rows = await pool.fetch(
            """
            SELECT sequence_num, role, content FROM chat_messages
            WHERE session_id = $1 AND is_error = false AND branch_id = 0
              AND sequence_num >= $2
            ORDER BY sequence_num ASC
            """,
            str(session_id), prev_before_seq,
        )
    else:
        msg_rows = await pool.fetch(
            """
            SELECT sequence_num, role, content FROM chat_messages
            WHERE session_id = $1 AND is_error = false AND branch_id = 0
            ORDER BY sequence_num ASC
            """,
            str(session_id),
        )

    # Split: droppable = everything except the last keep_recent messages.
    if len(msg_rows) <= body.keep_recent:
        raise HTTPException(status_code=409, detail="nothing to compact")
    droppable_rows = msg_rows[: len(msg_rows) - body.keep_recent]
    kept_rows = msg_rows[len(msg_rows) - body.keep_recent:]

    droppable: list[dict] = [{"role": r["role"], "content": r["content"]} for r in droppable_rows]
    kept: list[dict] = [{"role": r["role"], "content": r["content"]} for r in kept_rows]
    # Re-compact folds the previous summary in as the first "message" so the
    # new summary covers ALL compacted history (lossless-ish, idempotent).
    if prev_summary:
        droppable.insert(0, summary_message(prev_summary))

    tokens_before = estimate_messages_tokens(droppable + kept)

    try:
        summary = await summarize_for_compaction(
            droppable,
            model_source=row["model_source"],
            model_ref=str(row["model_ref"]),
            user_id=user_id,
            instructions=body.instructions,
        )
    except Exception as exc:  # session unchanged — the user asked for a summary,
        # never persist a truncation-only manual compact.
        logger.warning("manual compact summarizer failed session=%s", session_id, exc_info=True)
        raise HTTPException(status_code=502, detail="summarizer failed — session unchanged") from exc
    if not summary:
        raise HTTPException(status_code=502, detail="summarizer returned empty — session unchanged")

    new_before_seq = int(kept_rows[0]["sequence_num"])  # seq of the first KEPT message
    # Optimistic-concurrency guard: the summarizer call above takes seconds; a
    # concurrent compact may have landed meanwhile. Persist only if the marker
    # still equals the value we read at start (NULL-safe), else 409 — never
    # last-write-wins over a compact whose coverage we didn't fold in.
    result = await pool.execute(
        "UPDATE chat_sessions SET compact_summary=$3, compacted_before_seq=$4, updated_at=now() "
        "WHERE session_id=$1 AND owner_user_id=$2 AND compacted_before_seq IS NOT DISTINCT FROM $5",
        str(session_id), user_id, summary, new_before_seq, prev_before_seq,
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=409, detail="another compact landed — retry")

    return CompactSessionResponse(
        summary_tokens=estimate_tokens(summary),
        compacted_message_count=len(droppable_rows),
        compacted_before_seq=new_before_seq,
        tokens_before_estimate=tokens_before,
        tokens_after_estimate=estimate_messages_tokens([summary_message(summary)] + kept),
    )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: UUID,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> None:
    result = await pool.execute(
        "DELETE FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2",
        str(session_id), user_id,
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="session not found")
