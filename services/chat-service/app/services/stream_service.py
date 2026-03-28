"""LiteLLM streaming service — emits AI SDK data stream protocol v1."""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator
from uuid import uuid4

import asyncpg
from litellm import acompletion

from app.client.billing_client import BillingClient
from app.models import ProviderCredentials
from app.services.output_extractor import extract_outputs


async def stream_response(
    session_id: str,
    user_message_content: str,
    user_id: str,
    model_source: str,
    model_ref: str,
    creds: ProviderCredentials,
    pool: asyncpg.Pool,
    billing: BillingClient,
) -> AsyncGenerator[str, None]:
    """Async generator that yields AI SDK data stream protocol v1 SSE lines."""

    # Build message history (last 50 to avoid context overflow)
    rows = await pool.fetch(
        """
        SELECT role, content FROM chat_messages
        WHERE session_id = $1 AND is_error = false
        ORDER BY sequence_num DESC
        LIMIT 50
        """,
        session_id,
    )
    messages = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    messages.append({"role": "user", "content": user_message_content})

    # LiteLLM model string
    if creds.provider_kind == "lm_studio":
        model = f"openai/{creds.provider_model_name}"
    else:
        model = f"{creds.provider_kind}/{creds.provider_model_name}"

    full_content: list[str] = []
    last_chunk = None
    msg_id = str(uuid4())

    try:
        response = await acompletion(
            model=model,
            messages=messages,
            stream=True,
            api_key=creds.api_key or None,
            base_url=creds.base_url or None,
            timeout=300,
        )
        async for chunk in response:
            last_chunk = chunk
            delta = ""
            if chunk.choices and chunk.choices[0].delta.content:
                delta = chunk.choices[0].delta.content
            if delta:
                full_content.append(delta)
                yield f'data: {json.dumps({"type": "text-delta", "delta": delta})}\n\n'

        final_text = "".join(full_content)

        # Persist assistant message
        async with pool.acquire() as conn:
            seq = await conn.fetchval(
                "SELECT COALESCE(MAX(sequence_num), 0) + 1 FROM chat_messages WHERE session_id = $1",
                session_id,
            )
            usage = last_chunk.usage if last_chunk and hasattr(last_chunk, "usage") else None
            input_tok = usage.prompt_tokens if usage else None
            output_tok = usage.completion_tokens if usage else None

            await conn.execute(
                """
                INSERT INTO chat_messages
                  (message_id, session_id, owner_user_id, role, content, sequence_num,
                   input_tokens, output_tokens, model_ref)
                VALUES ($1,$2,$3,'assistant',$4,$5,$6,$7,$8)
                """,
                msg_id, session_id, user_id, final_text, seq,
                input_tok, output_tok, model_ref,
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

        # Send custom data annotation (IDs back to frontend) — only if artifacts were extracted
        if artifacts:
            yield f'data: {json.dumps({"type": "data", "data": [{"message_id": msg_id, "output_id": output_id}]})}\n\n'

        # Finish event
        finish = {
            "type": "finish-message",
            "finishReason": "stop",
            "usage": {
                "promptTokens": input_tok or 0,
                "completionTokens": output_tok or 0,
            },
        }
        yield f'data: {json.dumps(finish)}\n\n'

        # Log usage async (non-blocking)
        if usage:
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
                )
            )

    except Exception as exc:
        yield f'data: {json.dumps({"type": "error", "errorText": str(exc)})}\n\n'

    yield "data: [DONE]\n\n"
