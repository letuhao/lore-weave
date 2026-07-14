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


def _jsonb(value: object) -> dict:
    """asyncpg hands JSONB back as a str on some codecs and a dict on others."""
    if isinstance(value, str):
        return json.loads(value)
    return dict(value) if value else {}


def _merged_override(existing: object, patch: dict | None) -> str | None:
    """Deep-merge a session override blob, or None to CLEAR the whole category.

    Delegates to `settings_resolution.apply_patch` — the exact merge the account blob
    uses, so a null leaf clears that leaf and nested dicts recurse. Returns the JSON
    string to store (the caller decides whether to write it at all, via fields_set)."""
    if patch is None:
        return None
    from app.services.settings_resolution import apply_patch

    return json.dumps(apply_patch(_jsonb(existing), patch))


def _row_to_session(r: asyncpg.Record) -> ChatSession:
    gp = r["generation_params"]
    if isinstance(gp, str):
        gp = json.loads(gp)
    # WS-1.6 — the persisted per-turn capture decision (JSONB → dict). asyncpg may hand it
    # back as a str; parse it so the home strip reads {"fire", "reason"}, not a raw string.
    cap = r.get("capture_status")
    if isinstance(cap, str):
        cap = json.loads(cap)
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
        session_kind=r.get("session_kind") or "chat",
        project_ids=project_ids,
        memory_mode=memory_mode,
        capture_status=cap,
        composer_model_source=r.get("composer_model_source"),
        composer_model_ref=r.get("composer_model_ref"),
        planner_model_source=r.get("planner_model_source"),
        planner_model_ref=r.get("planner_model_ref"),
        enabled_tools=list(r.get("enabled_tools") or []),
        enabled_skills=list(r.get("enabled_skills") or []),
        activated_tools=list(r.get("activated_tools") or []),
        pinned_legacy_tools=list(r.get("pinned_legacy_tools") or []),
        # Chat & AI settings, SESSION tier — the RAW session override, not the
        # resolved cascade. `None`/`{}` means "no override here → inherited", which
        # is exactly what the panel's tier chip needs to distinguish.
        grounding_enabled=r.get("grounding_enabled"),
        voice_overrides=_jsonb(r.get("voice_overrides")),
        context_overrides=_jsonb(r.get("context_overrides")),
        # W3 — the FE "compacted through message N" indicator.
        compacted_before_seq=r.get("compacted_before_seq"),
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ChatSession)
async def create_session(
    body: CreateSessionRequest,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> ChatSession:
    # Chat & AI settings — seed a new session's behavior from the user's ACCOUNT
    # defaults (user_chat_ai_prefs.behavior) so a setting made in the Chat & AI
    # panel actually takes effect for new sessions (the intended account→session
    # inheritance). The request body always WINS (an explicit per-session choice);
    # the account fills only the gaps. Without this the account Behavior settings
    # would be write-only. (/review-impl HIGH fix.)
    from app.db.user_chat_ai_prefs import get_prefs
    _acct_behavior = (await get_prefs(pool, owner_user_id=user_id)).behavior or {}
    _seed_gp: dict = {}
    for _k in ("temperature", "top_p", "max_tokens", "reasoning_effort"):
        if _acct_behavior.get(_k) is not None:
            _seed_gp[_k] = _acct_behavior[_k]
    if body.generation_params:
        _seed_gp.update(body.generation_params.model_dump(exclude_unset=True))  # body wins
    gp = json.dumps(_seed_gp)
    _system_prompt = body.system_prompt if body.system_prompt is not None else _acct_behavior.get("system_prompt")
    row = await pool.fetchrow(
        """
        INSERT INTO chat_sessions (owner_user_id, title, model_source, model_ref, system_prompt, generation_params, project_id, composer_model_source, composer_model_ref, planner_model_source, planner_model_ref, project_ids, book_id, session_kind)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11, $12::uuid[], $13, $14)
        RETURNING *
        """,
        user_id, body.title, body.model_source, str(body.model_ref), _system_prompt, gp,
        str(body.project_id) if body.project_id else None,
        body.composer_model_source,
        str(body.composer_model_ref) if body.composer_model_ref else None,
        body.planner_model_source,
        str(body.planner_model_ref) if body.planner_model_ref else None,
        [str(p) for p in body.project_ids] if body.project_ids else [],
        str(body.book_id) if body.book_id else None,
        body.session_kind,
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

    # CAT-4 Part D — pinned_legacy_tools: SET-6 closed-set validation against
    # the LIVE catalog at write time (never trust a client-supplied name). An
    # unknown/non-legacy name is rejected with a self-correcting message
    # (IN-6) naming exactly which names were bad, not a generic 400.
    # Chat & AI settings, SESSION tier (spec 2026-07-05 §3.5). Same 3-state contract
    # as project_id: omitted ⇒ untouched, explicit null ⇒ CLEAR the override (inherit),
    # value ⇒ override. Until now these columns were read by the effective-settings
    # resolver and by the turn, but nothing could write them — the tier was dead.
    set_grounding_enabled = "grounding_enabled" in body.model_fields_set
    grounding_enabled_value = body.grounding_enabled

    # The two JSONB overrides deep-merge through the SAME `apply_patch` the account
    # blob uses (null leaf = clear that leaf, nested dicts recurse). One merge rule for
    # both write doors — a second, subtly-different rule here is how tiers drift.
    # Read-modify-write: a session is edited by one user through one debounced panel,
    # so concurrent patches to the same category are last-writer-wins by design.
    set_voice_overrides = "voice_overrides" in body.model_fields_set
    # Normalize voice source vocab (legacy 'ai_model' → 'user_model') + reject an
    # unknown source at THIS door too — the account door isn't the only way in
    # (D-CHATAI-VOICE-TWO-STORES; one merge rule, one vocabulary, both doors).
    from app.services.settings_resolution import normalize_voice_sources
    try:
        _voice_patch = normalize_voice_sources(body.voice_overrides)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    voice_overrides_value = _merged_override(row["voice_overrides"], _voice_patch)
    set_context_overrides = "context_overrides" in body.model_fields_set
    context_overrides_value = _merged_override(row["context_overrides"], body.context_overrides)

    set_pinned_legacy_tools = "pinned_legacy_tools" in body.model_fields_set
    pinned_legacy_tools_value = list(body.pinned_legacy_tools or [])
    if set_pinned_legacy_tools and pinned_legacy_tools_value:
        from app.client.knowledge_client import get_knowledge_client
        from app.services.tool_discovery import unknown_pinned_legacy_names

        live_catalog = await get_knowledge_client().get_tool_definitions(user_id=user_id)
        unknown = unknown_pinned_legacy_names(live_catalog, pinned_legacy_tools_value)
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"not a pinnable legacy tool: {', '.join(unknown)} — "
                    "see GET /v1/chat/tools/catalog?visibility=legacy for the valid set"
                ),
            )

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
          pinned_legacy_tools   = CASE WHEN $26::boolean THEN $27::text[] ELSE pinned_legacy_tools END,
          grounding_enabled     = CASE WHEN $28::boolean THEN $29::boolean ELSE grounding_enabled END,
          voice_overrides       = CASE WHEN $30::boolean THEN $31::jsonb ELSE voice_overrides END,
          context_overrides     = CASE WHEN $32::boolean THEN $33::jsonb ELSE context_overrides END,
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
        set_pinned_legacy_tools, pinned_legacy_tools_value,
        set_grounding_enabled, grounding_enabled_value,
        set_voice_overrides, voice_overrides_value,
        set_context_overrides, context_overrides_value,
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
