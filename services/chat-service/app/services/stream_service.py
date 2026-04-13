"""Streaming service — emits AI SDK data stream protocol v1 SSE lines.

Uses OpenAI AsyncClient directly (not LiteLLM) so we get raw delta fields
including reasoning_content from thinking models (Qwen3, DeepSeek-R1).
Falls back to LiteLLM for Anthropic and other non-OpenAI-compatible providers.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator
from uuid import uuid4

import asyncpg
from openai import AsyncOpenAI
from litellm import acompletion

from app.client.billing_client import BillingClient
from app.client.knowledge_client import get_knowledge_client
from app.models import ProviderCredentials
from app.services.output_extractor import extract_outputs

logger = logging.getLogger(__name__)


def _is_openai_compatible(provider_kind: str) -> bool:
    """Providers that speak the OpenAI chat/completions SSE protocol."""
    return provider_kind != "anthropic"


async def _stream_openai_compatible(
    model_name: str,
    messages: list[dict],
    api_key: str,
    base_url: str | None,
    gen_params: dict,
) -> AsyncGenerator[dict, None]:
    """Stream via openai.AsyncOpenAI — preserves reasoning_content."""
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    try:
        kwargs: dict = {
            "model": model_name,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if gen_params.get("temperature") is not None:
            kwargs["temperature"] = gen_params["temperature"]
        if gen_params.get("top_p") is not None:
            kwargs["top_p"] = gen_params["top_p"]
        if gen_params.get("max_tokens") is not None and gen_params["max_tokens"] > 0:
            kwargs["max_tokens"] = gen_params["max_tokens"]

        response = await client.chat.completions.create(**kwargs)
        async for chunk in response:
            if not chunk.choices and not getattr(chunk, "usage", None):
                continue
            # Final chunk may have usage but no choices
            if not chunk.choices:
                yield {
                    "content": "",
                    "reasoning_content": "",
                    "finish_reason": "stop",
                    "usage": getattr(chunk, "usage", None),
                }
                continue
            delta = chunk.choices[0].delta
            # OpenAI SDK preserves extra fields in model_extra
            raw = getattr(delta, "model_extra", {}) or {}
            yield {
                "content": delta.content or "",
                "reasoning_content": raw.get("reasoning_content", "") or "",
                "finish_reason": chunk.choices[0].finish_reason,
                "usage": getattr(chunk, "usage", None),
            }
    finally:
        await client.close()


async def _stream_litellm(
    model: str,
    messages: list[dict],
    api_key: str,
    base_url: str | None,
    gen_params: dict,
) -> AsyncGenerator[dict, None]:
    """Stream via LiteLLM — for Anthropic and non-OpenAI providers."""
    kwargs: dict = {
        "model": model,
        "messages": messages,
        "stream": True,
        "api_key": api_key,
        "base_url": base_url or None,
        "timeout": 300,
    }
    if gen_params.get("temperature") is not None:
        kwargs["temperature"] = gen_params["temperature"]
    if gen_params.get("top_p") is not None:
        kwargs["top_p"] = gen_params["top_p"]
    if gen_params.get("max_tokens") is not None and gen_params["max_tokens"] > 0:
        kwargs["max_tokens"] = gen_params["max_tokens"]

    response = await acompletion(**kwargs)
    async for chunk in response:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        yield {
            "content": delta.content or "",
            "reasoning_content": getattr(delta, "reasoning_content", "") or "",
            "finish_reason": chunk.choices[0].finish_reason,
            "usage": getattr(chunk, "usage", None),
        }


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
    system_parts: list[str] = []
    if kctx.context:
        system_parts.append(kctx.context)
    if system_prompt:
        system_parts.append(system_prompt)
    if system_parts:
        messages.insert(0, {"role": "system", "content": "\n\n".join(system_parts)})

    # Inject per-message context as a system message right before the last user message
    if context:
        messages.insert(-1, {"role": "system", "content": f"The user has attached the following context:\n\n{context}"})

    # ── Resolve model string + base_url ─────────────────────────────────────
    api_key = creds.api_key if creds.api_key else "lw-no-key"
    base_url = creds.base_url or None

    # For OpenAI-compatible providers, use the raw model name with OpenAI SDK
    # For Anthropic, use LiteLLM with anthropic/ prefix
    use_openai_sdk = _is_openai_compatible(creds.provider_kind)

    if creds.provider_kind == "anthropic":
        model_string = f"anthropic/{creds.provider_model_name}"
    elif creds.provider_kind == "openai" and not base_url:
        model_string = creds.provider_model_name
        base_url = "https://api.openai.com/v1"
    else:
        # LM Studio, Ollama, custom — raw model name for OpenAI SDK
        model_string = creds.provider_model_name
        if creds.provider_kind == "lm_studio" and base_url and not base_url.rstrip("/").endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"

    # ── Stream ──────────────────────────────────────────────────────────────
    full_content: list[str] = []
    full_reasoning: list[str] = []
    last_usage = None
    msg_id = str(uuid4())
    import time as _time
    stream_start = _time.monotonic()
    time_to_first_token: float | None = None

    try:
        if use_openai_sdk:
            chunk_stream = _stream_openai_compatible(model_string, messages, api_key, base_url, gen_params)
        else:
            chunk_stream = _stream_litellm(model_string, messages, api_key, base_url, gen_params)

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
        async with pool.acquire() as conn:
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
                    user_message=user_message_content,
                    assistant_message=final_text[:500],
                    model_name=model_string,
                    api_key=api_key,
                    base_url=base_url,
                    pool=pool,
                    use_openai_sdk=use_openai_sdk,
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
    user_message: str,
    assistant_message: str,
    model_name: str,
    api_key: str,
    base_url: str | None,
    pool: asyncpg.Pool,
    use_openai_sdk: bool = True,
) -> None:
    """Generate a short title for the session based on the first exchange."""
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
        if use_openai_sdk:
            client = AsyncOpenAI(api_key=api_key, base_url=base_url)
            resp = await client.chat.completions.create(
                model=model_name,
                messages=title_messages,
                stream=False,
                max_tokens=200,  # Extra budget so thinking models have room for content
                temperature=0.3,
            )
            msg = resp.choices[0].message
            # Thinking models (Qwen3) may put answer in content, or content may be empty
            # if all tokens went to reasoning. Check both.
            raw_content = (msg.content or "").strip()
            raw_extra = getattr(msg, "model_extra", {}) or {}
            raw_reasoning = (raw_extra.get("reasoning_content", "") or "").strip()
            # Prefer content; fall back to last line of reasoning
            if raw_content:
                title = raw_content.strip().strip('"').strip("'")
            elif raw_reasoning:
                # Extract last meaningful line from reasoning as title
                lines = [l.strip() for l in raw_reasoning.split("\n") if l.strip() and not l.strip().startswith("Okay") and not l.strip().startswith("Let me")]
                title = lines[-1].strip().strip('"').strip("'") if lines else ""
            else:
                title = ""
            await client.close()
        else:
            resp = await acompletion(
                model=model_name,
                messages=title_messages,
                stream=False,
                api_key=api_key,
                base_url=base_url,
                max_tokens=100,
                temperature=0.3,
            )
            title = (resp.choices[0].message.content or "").strip().strip('"').strip("'")

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
