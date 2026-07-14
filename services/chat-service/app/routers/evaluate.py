"""Interview-practice evaluation endpoint (M6).

`POST /v1/chat/sessions/{id}/evaluate` — a non-agentic pipeline that scores a
finished practice session against its frozen `charter.checklist` (+ optional
template rubric) and stores a `Scorecard` as a ChatOutput.

Tenancy: session-owner scoped (a non-owner gets 404). The working_memory is read
from the knowledge block (SSOT) with the session's own immutable
`working_memory_seed` as the degraded fallback (EC-4); the rubric rides the seed
(written at /start). The evaluator LLM runs on the SESSION's own model (the user
chose it; no separate default capability — same decision as the executive). No
model configured → 409 (EC-10, evaluate unavailable with a clear message).

The output is anchored to the session's LAST message (chat_outputs.message_id is
NOT NULL + ON DELETE CASCADE) so it's cleaned up with the conversation. An empty
transcript (no messages) → 400: there is nothing to score.
"""
from __future__ import annotations

import json
import logging
from uuid import UUID, uuid4

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from loreweave_llm import Client, ReasoningEvent, StreamRequest, TokenEvent

from app.config import settings
from app.client.knowledge_client import get_knowledge_client
from app.deps import get_current_user, get_db
from app.models import EvaluateResponse
from app.services.evaluate import (
    build_eval_messages,
    coerce_scorecard,
    is_partial,
    parse_json_object,
    render_summary_text,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/chat", tags=["evaluate"])


def _jsonb(v):
    return json.loads(v) if isinstance(v, str) else (v or {})


async def _resolve_working_memory(
    session_id: str, user_id: str, seed_raw
) -> tuple[dict, dict, dict | None]:
    """Return (charter, state, rubric).

    Prefer the live knowledge block (SSOT, carries the executive's final state);
    fall back to the immutable seed on any degraded/empty result (EC-4). The
    rubric is not in the knowledge block — it always comes from the seed.
    Raises HTTPException(400) when neither source carries a charter (i.e. this is
    not an interview-practice session)."""
    seed = _jsonb(seed_raw)
    rubric = seed.get("rubric") if isinstance(seed, dict) else None
    if not isinstance(rubric, dict):
        rubric = None

    charter: dict | None = None
    state: dict = {}

    ctx = await get_knowledge_client().build_context(
        user_id=user_id, session_id=session_id, message=""
    )
    if ctx.working_memory:
        try:
            block = json.loads(ctx.working_memory)
            if isinstance(block.get("charter"), dict):
                charter = block["charter"]
                state = block.get("state") or {}
        except (json.JSONDecodeError, ValueError, AttributeError):
            logger.warning("evaluate: knowledge working_memory unparseable for %s", session_id)

    # Degraded / no block → seed fallback (charter is frozen, so identical goal).
    if charter is None and isinstance(seed, dict) and isinstance(seed.get("charter"), dict):
        charter = seed["charter"]
        state = seed.get("state") or {}

    if charter is None:
        raise HTTPException(
            status_code=400,
            detail="session has no interview charter — not an interview-practice session",
        )
    return charter, state, rubric


async def _run_evaluator_llm(
    *, user_id: str, model_source: str, model_ref: str, messages: list[dict]
) -> str:
    """One non-streaming LLM pass via the gateway (accumulate the stream). Mirrors
    the title-generation path: route through loreweave_llm, no direct provider
    SDK, no response_format (lm_studio quirk). Returns the raw reply text."""
    client = Client(
        base_url=settings.provider_registry_internal_url,
        auth_mode="internal",
        internal_token=settings.internal_service_token,
        user_id=user_id,
    )
    try:
        request = StreamRequest(
            model_source=model_source,
            model_ref=model_ref,
            messages=messages,
            temperature=0.0,
            max_tokens=1200,
        )
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        async for ev in client.stream(request):
            if isinstance(ev, TokenEvent):
                content_parts.append(ev.delta)
            elif isinstance(ev, ReasoningEvent):
                # Some thinking models emit the JSON inside the reasoning channel
                # when content comes back empty — keep it as a fallback source.
                reasoning_parts.append(ev.delta)
        content = "".join(content_parts).strip()
        return content or "".join(reasoning_parts).strip()
    finally:
        await client.aclose()


@router.post(
    "/sessions/{session_id}/evaluate",
    status_code=status.HTTP_201_CREATED,
    response_model=EvaluateResponse,
)
async def evaluate_session(
    session_id: UUID,
    user_id: str = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_db),
) -> EvaluateResponse:
    sid = str(session_id)
    row = await pool.fetchrow(
        """
        SELECT session_id, owner_user_id, model_source, model_ref,
               working_memory_seed, title
        FROM chat_sessions WHERE session_id=$1 AND owner_user_id=$2
        """,
        sid, user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="session not found")

    actor_source = row["model_source"]
    actor_ref = row["model_ref"]
    if not actor_source or not actor_ref:
        # EC-10 — no model to evaluate with. A clear, non-hardcoded failure.
        raise HTTPException(
            status_code=409,
            detail="no model configured for this session — cannot evaluate",
        )

    # ── Gate 2 (WS-5.10 / P5) — judge ≠ actor. The session's model PLAYED the roleplay
    # partner; letting it score its own performance is the exact conflict this gate exists
    # to stop. Resolve a distinct CRITIC (the account critic default, falling back to the
    # account chat default), and REFUSE to score if none resolves distinct from the actor —
    # a weak/self judge yields NO score, not a self-flattering one (WS-5.18). The refusal is
    # explicit + actionable (the single-model degraded path — never a silent refuse-all).
    from app.client.provider_client import get_provider_client
    _pc = get_provider_client()
    judge = await _pc.get_default_model("critic", user_id)
    if not judge:
        judge = await _pc.get_default_model("chat", user_id)
    if not judge or str(judge[1]) == str(actor_ref):
        raise HTTPException(
            status_code=409,
            detail=(
                "scoring needs a CRITIC model distinct from this session's model (the session "
                "model played the roleplay partner and must not grade itself). Set a critic model "
                "in Settings › Chat & AI › default models."
            ),
        )
    model_source, model_ref = judge  # the JUDGE drives the evaluator LLM from here on

    charter, state, rubric = await _resolve_working_memory(
        sid, user_id, row["working_memory_seed"]
    )

    # Transcript (non-error turns, in order). Anchor the scorecard to the LAST
    # message so the NOT-NULL FK holds and it cascades on delete.
    msg_rows = await pool.fetch(
        """
        SELECT message_id, role, content FROM chat_messages
        WHERE session_id=$1 AND is_error=false
        ORDER BY sequence_num ASC
        """,
        sid,
    )
    if not msg_rows:
        raise HTTPException(status_code=400, detail="no transcript to evaluate")
    transcript = [{"role": r["role"], "content": r["content"]} for r in msg_rows]
    last_message_id = msg_rows[-1]["message_id"]

    messages, clipped = build_eval_messages(charter, state, rubric, transcript)
    partial = is_partial(state, clipped)

    try:
        reply = await _run_evaluator_llm(
            user_id=user_id,
            model_source=str(model_source),
            model_ref=str(model_ref),
            messages=messages,
        )
        raw = parse_json_object(reply)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("evaluate: LLM/parse failed for %s: %s", sid, exc)
        raise HTTPException(
            status_code=502,
            detail="evaluation model did not return a usable scorecard",
        )

    card = coerce_scorecard(raw, charter, partial=partial)

    output_id = uuid4()
    language = charter.get("language")
    title = f"Scorecard — {row['title']}" if row["title"] else "Interview scorecard"
    await pool.execute(
        """
        INSERT INTO chat_outputs
          (output_id, message_id, session_id, owner_user_id,
           output_type, title, content_text, language, metadata)
        VALUES ($1,$2,$3,$4,'scorecard',$5,$6,$7,$8::jsonb)
        """,
        str(output_id), last_message_id, sid, user_id,
        title, render_summary_text(card, charter), language,
        json.dumps(card.model_dump(mode="json")),
    )

    return EvaluateResponse(
        output_id=output_id,
        session_id=session_id,
        scorecard=card,
        model_source=str(model_source),
        model_ref=str(model_ref),
    )
