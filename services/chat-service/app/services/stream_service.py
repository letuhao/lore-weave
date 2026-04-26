"""Streaming service — emits AI SDK data stream protocol v1 SSE lines.

Phase 1c-ii (LLM_PIPELINE_UNIFIED_REFACTOR_PLAN): all LLM streaming flows
through provider-registry's `/internal/llm/stream` via the
`loreweave_llm` SDK. Direct provider-SDK calls (litellm, openai-python,
anthropic) are forbidden per CLAUDE.md gateway invariant.

Anthropic streaming temporarily emits LLM_STREAM_NOT_SUPPORTED until
the anthropic adapter Stream() impl ships (deferral
D-PHASE-1C-ANTHROPIC).
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import AsyncGenerator
from uuid import uuid4

import asyncpg
from loreweave_llm import (
    Client,
    DoneEvent,
    LLMError,
    ReasoningEvent,
    StreamRequest,
    TokenEvent,
    UsageEvent,
)

from app.client.billing_client import BillingClient
from app.client.knowledge_client import get_knowledge_client
from app.config import settings
from app.models import ProviderCredentials
from app.services.output_extractor import extract_outputs

logger = logging.getLogger(__name__)


@dataclass
class _Usage:
    """Mirror the shape of openai's CompletionUsage so existing
    `getattr(last_usage, 'prompt_tokens', None)` call sites keep working
    after the SDK migration."""

    prompt_tokens: int = 0
    completion_tokens: int = 0


async def _stream_via_gateway(
    model_source: str,
    model_ref: str,
    user_id: str,
    messages: list[dict],
    gen_params: dict,
) -> AsyncGenerator[dict, None]:
    """Stream via provider-registry `/internal/llm/stream` using the
    loreweave_llm SDK. Single replacement for the legacy
    `_stream_openai_compatible` and `_stream_litellm` helpers — gateway
    invariant restored.

    Yields dicts of the same shape consumers expected from the legacy
    helpers (`content` / `reasoning_content` / `finish_reason` / `usage`)
    so `stream_response` and `voice_stream_response` don't need
    restructuring.
    """
    client = Client(
        base_url=settings.provider_registry_internal_url,
        auth_mode="internal",
        internal_token=settings.internal_service_token,
        user_id=user_id,
    )
    try:
        max_tokens = gen_params.get("max_tokens")
        if max_tokens is not None and max_tokens <= 0:
            max_tokens = None
        # Build kwargs sparsely so None values don't override SDK schema
        # defaults (StreamRequest.temperature defaults to 0.0; passing
        # None fails pydantic validation).
        request_kwargs: dict = {
            "model_source": model_source,
            "model_ref": model_ref,
            "messages": messages,
        }
        if gen_params.get("temperature") is not None:
            request_kwargs["temperature"] = gen_params["temperature"]
        if max_tokens is not None:
            request_kwargs["max_tokens"] = max_tokens
        request = StreamRequest(**request_kwargs)
        last_usage: _Usage | None = None
        finish_reason: str | None = None
        async for ev in client.stream(request):
            if isinstance(ev, TokenEvent):
                yield {
                    "content": ev.delta,
                    "reasoning_content": "",
                    "finish_reason": None,
                    "usage": None,
                }
            elif isinstance(ev, ReasoningEvent):
                yield {
                    "content": "",
                    "reasoning_content": ev.delta,
                    "finish_reason": None,
                    "usage": None,
                }
            elif isinstance(ev, UsageEvent):
                last_usage = _Usage(
                    prompt_tokens=ev.input_tokens,
                    completion_tokens=ev.output_tokens,
                )
            elif isinstance(ev, DoneEvent):
                finish_reason = ev.finish_reason
        # Trailing chunk so consumer's billing path picks up usage +
        # finish_reason exactly the way the legacy code did.
        yield {
            "content": "",
            "reasoning_content": "",
            "finish_reason": finish_reason or "stop",
            "usage": last_usage,
        }
    finally:
        await client.aclose()


async def stream_response(
    session_id: str,
    user_message_content: str,
    user_id: str,
    model_source: str,
    model_ref: str,
    creds: ProviderCredentials,
    pool: asyncpg.Pool,
    billing: BillingClient,
    parent_message_id: str | None = None,
    context: str | None = None,
    thinking: bool | None = None,
) -> AsyncGenerator[str, None]:
    """Async generator that yields AI SDK data stream protocol v1 SSE lines."""

    # ── Load session settings ───────────────────────────────────────────────
    session_row = await pool.fetchrow(
        "SELECT system_prompt, generation_params, project_id FROM chat_sessions WHERE session_id = $1",
        session_id,
    )
    system_prompt = session_row["system_prompt"] if session_row else None
    gp_raw = session_row["generation_params"] if session_row else {}
    if isinstance(gp_raw, str):
        gp_raw = json.loads(gp_raw)
    gen_params: dict = gp_raw if gp_raw else {}
    # asyncpg.Record supports .get() since 0.27; using it lets test mocks
    # that pass a plain dict without project_id continue to work.
    project_id = session_row.get("project_id") if session_row else None

    # ── K5: build memory block via knowledge-service ────────────────────────
    # Always called — Mode 1 (no project) returns just the user's global
    # bio + a short instruction; Mode 2 (project linked) returns the
    # full L0/L1/glossary block. Failures degrade silently inside the
    # client and return KnowledgeContext(mode="degraded", context="",
    # recent_message_count=50).
    knowledge_client = get_knowledge_client()
    kctx = await knowledge_client.build_context(
        user_id=user_id,
        session_id=session_id,
        project_id=str(project_id) if project_id else None,
        message=user_message_content,
    )

    # ── K-CLEAN-5 (D-K8-04): emit memory_mode to the FE ─────────────────────
    # knowledge-service build_context emits mode="no_project"
    # (Mode 1), mode="static" (Mode 2), or mode="degraded" (client
    # fallback). T01-T19-I1: the original K-CLEAN-5 code checked
    # for "mode_1"/"mode_2" which never matched — every mode
    # silently fell through to the else branch and surfaced as
    # "static", so the FE degraded badge never fired. The e2e
    # suite caught the mismatch. The FE memory_mode vocabulary is
    # already a subset of the backend vocabulary, so forwarding
    # the mode string as-is is both simpler AND the safest fix.
    fe_memory_mode = kctx.mode

    # ── Build message history (size from knowledge_service) ─────────────────
    history_limit = max(1, kctx.recent_message_count)
    rows = await pool.fetch(
        """
        SELECT role, content FROM chat_messages
        WHERE session_id = $1 AND is_error = false AND branch_id = 0
        ORDER BY sequence_num DESC
        LIMIT $2
        """,
        session_id, history_limit,
    )
    messages: list[dict] = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    # ── Compose the system message ──────────────────────────────────────────
    # Order: memory block → session-level system prompt → user's per-message
    # attached context. Memory comes FIRST because it sets durable identity
    # and project state; the session prompt is per-conversation persona on
    # top; per-message context is the most ephemeral.
    #
    # Each part is stripped so a trailing newline in (e.g.) the XML memory
    # block doesn't stack with the "\n\n" separator to produce triple
    # newlines in the final prompt (K5-I3).
    #
    # K18.9 + T2-polish-3 (D-K18.9-01): when the provider is Anthropic
    # AND the memory block came back pre-split by knowledge-service,
    # emit structured system content with `cache_control` markers on
    # BOTH the stable-memory prefix AND the session-level system_prompt.
    # Anthropic allows up to 4 cache breakpoints per request; we use 2:
    #   parts[0]: stable memory (L0 + project + Mode-2/3 prefix up to </project>)
    #     → cached; changes only when L0 / project summary / memory-mode flip
    #   parts[1]: volatile memory (Mode-2/3 glossary + facts + passages)
    #     → NOT cached; changes per-message by intent
    #   parts[2]: session system_prompt (persona / tone / instructions)
    #     → cached; stable per-session, doesn't change between turns
    # Non-Anthropic providers and the degraded / unsplit fallback take
    # the plain-string path.
    use_anthropic_cache = (
        creds.provider_kind == "anthropic"
        and kctx.stable_context.strip() != ""
    )
    if use_anthropic_cache:
        parts: list[dict] = []
        stable = kctx.stable_context.strip()
        parts.append({
            "type": "text",
            "text": stable,
            "cache_control": {"type": "ephemeral"},
        })
        volatile = kctx.volatile_context.strip()
        if volatile:
            parts.append({"type": "text", "text": volatile})
        if system_prompt and system_prompt.strip():
            parts.append({
                "type": "text",
                "text": system_prompt.strip(),
                "cache_control": {"type": "ephemeral"},
            })
        messages.insert(0, {"role": "system", "content": parts})
    else:
        system_parts: list[str] = []
        if kctx.context:
            stripped = kctx.context.strip()
            if stripped:
                system_parts.append(stripped)
        if system_prompt:
            stripped = system_prompt.strip()
            if stripped:
                system_parts.append(stripped)
        if system_parts:
            messages.insert(0, {"role": "system", "content": "\n\n".join(system_parts)})

    # Inject per-message context as a system message right before the last user message
    if context:
        messages.insert(-1, {"role": "system", "content": f"The user has attached the following context:\n\n{context}"})

    # ── Phase 1c-ii: gateway resolves api_key / base_url / model_string
    # internally; service no longer needs them. We keep `creds.provider_kind`
    # for the Anthropic cache_control branch above.

    # ── Stream ──────────────────────────────────────────────────────────────
    full_content: list[str] = []
    full_reasoning: list[str] = []
    last_usage = None
    msg_id = str(uuid4())
    import time as _time
    stream_start = _time.monotonic()
    time_to_first_token: float | None = None

    # K-CLEAN-5 (D-K8-04): emit memory_mode as the FIRST SSE event so the
    # FE can flip the indicator badge before any tokens render. Yielded
    # outside the try/except below so it lands even if the LLM call
    # immediately fails downstream.
    yield f'data: {json.dumps({"type": "memory-mode", "mode": fe_memory_mode})}\n\n'

    try:
        chunk_stream = _stream_via_gateway(
            model_source=model_source,
            model_ref=model_ref,
            user_id=user_id,
            messages=messages,
            gen_params=gen_params,
        )

        async for chunk_data in chunk_stream:
            reasoning = chunk_data["reasoning_content"]
            content = chunk_data["content"]
            if chunk_data.get("usage"):
                last_usage = chunk_data["usage"]

            # Track time to first token (reasoning or content)
            if time_to_first_token is None and (reasoning or content):
                time_to_first_token = (_time.monotonic() - stream_start) * 1000  # ms

            if reasoning:
                full_reasoning.append(reasoning)
                yield f'data: {json.dumps({"type": "reasoning-delta", "delta": reasoning})}\n\n'
            if content:
                full_content.append(content)
                yield f'data: {json.dumps({"type": "text-delta", "delta": content})}\n\n'

        response_time_ms = (_time.monotonic() - stream_start) * 1000
        final_text = "".join(full_content)
        final_reasoning = "".join(full_reasoning)

        # ── Persist assistant message ───────────────────────────────────────
        # K13.2: wrap the three INSERTs + outbox event in one transaction
        # so chat.turn_completed is only emitted when the message persists
        # successfully. Rollback on any error discards both the message and
        # the event.
        async with pool.acquire() as conn:
            async with conn.transaction():
                seq = await conn.fetchval(
                    "SELECT COALESCE(MAX(sequence_num), 0) + 1 FROM chat_messages WHERE session_id = $1",
                    session_id,
                )
                input_tok = getattr(last_usage, "prompt_tokens", None) if last_usage else None
                output_tok = getattr(last_usage, "completion_tokens", None) if last_usage else None

                # Store metadata in content_parts JSONB
                parts: dict = {}
                if final_reasoning:
                    parts["reasoning"] = final_reasoning
                    parts["reasoning_length"] = len(final_reasoning)
                parts["response_time_ms"] = round(response_time_ms)
                if time_to_first_token is not None:
                    parts["time_to_first_token_ms"] = round(time_to_first_token)
                content_parts = json.dumps(parts) if parts else None

                await conn.execute(
                    """
                    INSERT INTO chat_messages
                      (message_id, session_id, owner_user_id, role, content, content_parts,
                       sequence_num, input_tokens, output_tokens, model_ref, parent_message_id, branch_id)
                    VALUES ($1,$2,$3,'assistant',$4,$5::jsonb,$6,$7,$8,$9,$10, 0)
                    """,
                    msg_id, session_id, user_id, final_text, content_parts, seq,
                    input_tok, output_tok, model_ref, parent_message_id,
                )

                # Extract and persist output artifacts
                artifacts = extract_outputs(final_text)
                output_id = str(uuid4())
                for i, artifact in enumerate(artifacts):
                    oid = output_id if i == 0 else str(uuid4())
                    await conn.execute(
                        """
                        INSERT INTO chat_outputs
                          (output_id, message_id, session_id, owner_user_id,
                           output_type, content_text, language, title)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                        """,
                        oid, msg_id, session_id, user_id,
                        artifact.output_type, artifact.content_text,
                        artifact.language, artifact.title,
                    )

                # Update session stats
                await conn.execute(
                    """
                    UPDATE chat_sessions
                    SET message_count = message_count + 1,
                        last_message_at = now(),
                        updated_at = now()
                    WHERE session_id = $1
                    """,
                    session_id,
                )

                # K13.2: emit chat.turn_completed outbox event.
                # aggregate_type drives the Redis Stream name via outbox-relay:
                # 'chat' -> loreweave:events:chat (knowledge-service consumer).
                outbox_payload = {
                    "user_id": str(user_id),
                    "project_id": str(project_id) if project_id else None,
                    "session_id": str(session_id),
                    "message_id": str(msg_id),
                    "user_message_id": str(parent_message_id) if parent_message_id else None,
                    "user_content_len": len(user_message_content) if user_message_content else 0,
                    "assistant_content_len": len(final_text),
                }
                await conn.execute(
                    """
                    INSERT INTO outbox_events
                      (event_type, aggregate_type, aggregate_id, payload)
                    VALUES ('chat.turn_completed', 'chat', $1, $2::jsonb)
                    """,
                    msg_id, json.dumps(outbox_payload),
                )

        # Send custom data annotation (IDs back to frontend)
        data_payload: dict = {"message_id": msg_id}
        if artifacts:
            data_payload["output_id"] = output_id
        if final_reasoning:
            data_payload["has_reasoning"] = True
        yield f'data: {json.dumps({"type": "data", "data": [data_payload]})}\n\n'

        # Finish event — includes timing metrics
        finish = {
            "type": "finish-message",
            "finishReason": "stop",
            "usage": {
                "promptTokens": input_tok or 0,
                "completionTokens": output_tok or 0,
            },
            "timing": {
                "responseTimeMs": round(response_time_ms),
                "timeToFirstTokenMs": round(time_to_first_token) if time_to_first_token is not None else None,
            },
        }
        yield f'data: {json.dumps(finish)}\n\n'

        # Auto-title: generate title after first assistant message
        current_count = await pool.fetchval(
            "SELECT message_count FROM chat_sessions WHERE session_id = $1",
            session_id,
        )
        if current_count is not None and current_count <= 2:
            asyncio.create_task(
                _auto_generate_title(
                    session_id=session_id,
                    user_id=user_id,
                    user_message=user_message_content,
                    assistant_message=final_text[:500],
                    model_source=model_source,
                    model_ref=model_ref,
                    pool=pool,
                )
            )

        # Log usage async (non-blocking)
        if last_usage:
            asyncio.create_task(
                billing.log_usage(
                    user_id=user_id,
                    model_source=model_source,
                    model_ref=model_ref,
                    provider_kind=creds.provider_kind,
                    input_tokens=input_tok or 0,
                    output_tokens=output_tok or 0,
                    session_id=session_id,
                    message_id=msg_id,
                    input_payload={"messages": messages},
                    output_payload={"content": final_text, "reasoning": final_reasoning or None},
                )
            )

    except Exception as exc:
        logger.exception("Stream error for session %s", session_id)
        # Sanitize error message — don't leak internal details
        safe_msg = str(exc)
        if any(kw in safe_msg.lower() for kw in ("traceback", "file ", "/usr/", "password", "secret")):
            safe_msg = "An internal error occurred. Please try again."
        yield f'data: {json.dumps({"type": "error", "errorText": safe_msg})}\n\n'

    yield "data: [DONE]\n\n"


async def _auto_generate_title(
    session_id: str,
    user_id: str,
    user_message: str,
    assistant_message: str,
    model_source: str,
    model_ref: str,
    pool: asyncpg.Pool,
) -> None:
    """Generate a short title via the LLM gateway. Phase 1c-ii: routes
    through `loreweave_llm.Client.stream()` and accumulates tokens
    instead of calling AsyncOpenAI/litellm directly. Title generation is
    short enough (≤200 tokens) that streaming-then-collect is cheap."""
    title_messages = [
        {
            "role": "system",
            "content": "Generate a concise title (max 6 words) for this conversation. "
            "Return ONLY the title, no quotes, no explanation. "
            "Do NOT think or reason — just output the title directly.",
        },
        {"role": "user", "content": user_message[:300]},
        {"role": "assistant", "content": assistant_message[:300] if assistant_message else "(responded)"},
        {"role": "user", "content": "Title:"},
    ]
    try:
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
                messages=title_messages,
                temperature=0.3,
                max_tokens=200,  # Extra budget for thinking models
            )  # noqa — title gen has explicit non-None values, no kwargs sparsity needed
            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            async for ev in client.stream(request):
                if isinstance(ev, TokenEvent):
                    content_parts.append(ev.delta)
                elif isinstance(ev, ReasoningEvent):
                    reasoning_parts.append(ev.delta)
        finally:
            await client.aclose()

        raw_content = "".join(content_parts).strip()
        raw_reasoning = "".join(reasoning_parts).strip()

        # Prefer content; fall back to last meaningful line of reasoning.
        if raw_content:
            title = raw_content.strip().strip('"').strip("'")
        elif raw_reasoning:
            lines = [
                l.strip()
                for l in raw_reasoning.split("\n")
                if l.strip()
                and not l.strip().startswith("Okay")
                and not l.strip().startswith("Let me")
            ]
            title = lines[-1].strip().strip('"').strip("'") if lines else ""
        else:
            title = ""

        if title and len(title) <= 100:
            await pool.execute(
                """
                UPDATE chat_sessions SET title = $2, updated_at = now()
                WHERE session_id = $1 AND title = 'New Chat'
                """,
                session_id, title,
            )
    except Exception:
        logger.debug("Auto-title generation failed for session %s", session_id, exc_info=True)
