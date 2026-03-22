"""
Session-based chapter translation.

Pipeline for one chapter:
  1. Split text into chunks (chunk_splitter)
  2. Translate each chunk sequentially, passing the rolling conversation history
     so the model stays consistent with names, tone, and terminology
  3. When history token-estimate exceeds 50 % of the context window, call the
     compact model to condense history into a short Translation Memo, then flush
  4. Write each chunk result to chapter_translation_chunks (observability)
  5. Return the concatenated translation + aggregated token counts

Errors bubble up as _TransientError / _PermanentError (defined in chapter_worker).
"""
from __future__ import annotations

import json
import logging
from uuid import UUID

import httpx

from ..auth import mint_user_jwt
from ..config import settings
from .chunk_splitter import estimate_tokens, split_chapter
from .content_extractor import extract_content

log = logging.getLogger(__name__)

_JWT_TTL = 4 * 3600  # 4 hours — covers very long chapter translation sessions

_DEFAULT_COMPACT_SYSTEM = (
    "You are a translation assistant. Summarise the following translation session history "
    "into a concise Translation Memo (200 words max). Include: key character names and "
    "their translations, recurring terminology, tone/style notes. "
    "Output ONLY the memo, no other text."
)

# Minimum context window to assume when we cannot determine the real value
_FALLBACK_CONTEXT_WINDOW = 8192


async def translate_chapter(
    chapter_text: str,
    source_lang: str,
    msg: dict,
    pool,
    chapter_translation_id: UUID,
    *,
    context_window: int = _FALLBACK_CONTEXT_WINDOW,
) -> tuple[str, int, int]:
    """
    Translate a full chapter using session-based chunking.

    Args:
        chapter_text:           Raw original text.
        source_lang:            Detected source language (e.g. "Chinese").
        msg:                    Full chapter job message (contains model config, prompts, etc.).
        pool:                   asyncpg pool for writing chunk rows.
        chapter_translation_id: UUID of the parent chapter_translations row.
        context_window:         Model context window in tokens (from provider-registry).

    Returns:
        (translated_body, total_input_tokens, total_output_tokens)
    """
    chunk_size = int(msg.get("chunk_size_tokens") or 2000)
    # Never exceed 1/4 of the model's context window per chunk
    chunk_size = min(chunk_size, context_window // 4)
    chunk_size = max(chunk_size, 100)  # floor to avoid degenerate splits

    timeout_secs = msg.get("invoke_timeout_secs") or 300
    # 0 means unlimited — map to None for httpx
    read_timeout = float(timeout_secs) if timeout_secs and timeout_secs > 0 else None

    chunks = split_chapter(chapter_text, chunk_size)
    log.info(
        "session_translator: chapter_translation=%s, %d chunks (chunk_size=%d, context=%d)",
        chapter_translation_id, len(chunks), chunk_size, context_window,
    )

    session_history: list[dict] = []
    compact_memo: str = ""
    translated_parts: list[str] = []
    total_input  = 0
    total_output = 0

    token = mint_user_jwt(msg["user_id"], settings.jwt_secret, ttl_seconds=_JWT_TTL)

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, write=60.0, read=read_timeout, pool=5.0)
    ) as client:
        for idx, chunk in enumerate(chunks):
            translated, in_tok, out_tok = await _translate_chunk(
                client=client,
                chunk=chunk,
                chunk_idx=idx,
                total_chunks=len(chunks),
                source_lang=source_lang,
                msg=msg,
                token=token,
                session_history=session_history,
                compact_memo=compact_memo,
                pool=pool,
                chapter_translation_id=chapter_translation_id,
            )
            log.info(
                "session_translator: chunk %d/%d done — %d chars, in=%d out=%d (ct=%s)",
                idx + 1, len(chunks), len(translated), in_tok, out_tok, chapter_translation_id,
            )
            translated_parts.append(translated)
            total_input  += in_tok
            total_output += out_tok

            # Extend session history with this exchange
            session_history.append({
                "role": "user",
                "content": _build_user_content(chunk, source_lang, msg, idx, len(chunks)),
            })
            session_history.append({"role": "assistant", "content": translated})

            # Compact when history consumes > 50 % of context window
            history_tokens = sum(estimate_tokens(m["content"]) for m in session_history)
            if history_tokens > context_window // 2:
                log.info(
                    "session_translator: compacting history (%d tokens) for chapter_translation=%s",
                    history_tokens, chapter_translation_id,
                )
                compact_memo = await _compact_history(
                    client=client,
                    session_history=session_history,
                    old_memo=compact_memo,
                    msg=msg,
                    token=token,
                )
                session_history = []

    return "\n\n".join(translated_parts), total_input, total_output


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_user_content(
    chunk: str,
    source_lang: str,
    msg: dict,
    chunk_idx: int,
    total_chunks: int,
) -> str:
    """Render the user-facing content for one chunk using the job's prompt template."""
    tpl = msg.get("user_prompt_tpl") or (
        "Translate the following {source_language} text into {target_language}. "
        "Output only the translated text, nothing else.\n\n{chapter_text}"
    )
    part_note = f"[Part {chunk_idx + 1}/{total_chunks}]\n" if total_chunks > 1 else ""
    return part_note + tpl.format_map({
        "source_language": source_lang,
        "target_language": msg.get("target_language", ""),
        "chapter_text":    chunk,
    })


def _build_messages(
    chunk: str,
    source_lang: str,
    msg: dict,
    chunk_idx: int,
    total_chunks: int,
    session_history: list[dict],
    compact_memo: str,
) -> list[dict]:
    """
    Construct the full messages array for one chunk invoke call.

    Layout:
      [system]
      (optional) [assistant: compact memo preamble]
      [*session_history alternating user/assistant]
      [user: current chunk]
    """
    system_content = msg.get("system_prompt") or (
        "You are a professional literary translator. "
        "Preserve the style, tone, pacing, and voice of the original text. "
        "Do not add commentary, explanations, or translator notes. "
        "Translate faithfully and naturally."
    )
    messages: list[dict] = [{"role": "system", "content": system_content}]

    # Inject compact memo as the first assistant turn so the model "remembers" context
    if compact_memo:
        messages.append({
            "role": "assistant",
            "content": f"[Translation memo from earlier context]\n{compact_memo}",
        })

    # Rolling history (already-translated prior chunks)
    messages.extend(session_history)

    # Current chunk
    messages.append({
        "role": "user",
        "content": _build_user_content(chunk, source_lang, msg, chunk_idx, total_chunks),
    })
    return messages


async def _translate_chunk(
    *,
    client: httpx.AsyncClient,
    chunk: str,
    chunk_idx: int,
    total_chunks: int,
    source_lang: str,
    msg: dict,
    token: str,
    session_history: list[dict],
    compact_memo: str,
    pool,
    chapter_translation_id: UUID,
) -> tuple[str, int, int]:
    """
    Invoke the AI model for a single chunk, write the result to
    chapter_translation_chunks, and return (translated_text, input_tokens, output_tokens).
    """
    from .chapter_worker import _TransientError, _PermanentError  # local import avoids circular

    # Insert pending chunk row
    chunk_row_id = await _insert_chunk_row(
        pool, chapter_translation_id, chunk_idx, chunk, compact_memo
    )

    messages = _build_messages(
        chunk, source_lang, msg, chunk_idx, total_chunks,
        session_history, compact_memo,
    )
    invoke_payload = {
        "model_source": msg["model_source"],
        "model_ref":    msg["model_ref"],
        "input":        {"messages": messages},
    }

    log.debug(
        "session_translator: invoking model %s/%s for chunk %d/%d (ct=%s)",
        invoke_payload["model_source"], invoke_payload["model_ref"],
        chunk_idx + 1, total_chunks, chapter_translation_id,
    )
    raw_chunks: list[bytes] = []
    try:
        async with client.stream(
            "POST",
            f"{settings.provider_registry_service_url}/v1/model-registry/invoke",
            json=invoke_payload,
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            log.debug(
                "session_translator: invoke response status=%d for chunk %d (ct=%s)",
                resp.status_code, chunk_idx + 1, chapter_translation_id,
            )
            if resp.status_code == 402:
                log.error("session_translator: billing_rejected for chunk %d (ct=%s)", chunk_idx + 1, chapter_translation_id)
                raise _PermanentError("billing_rejected")
            if resp.status_code == 404:
                log.error("session_translator: model_not_found for chunk %d (ct=%s)", chunk_idx + 1, chapter_translation_id)
                raise _PermanentError("model_not_found")
            if resp.status_code >= 500:
                log.error("session_translator: provider_error_%d for chunk %d (ct=%s)", resp.status_code, chunk_idx + 1, chapter_translation_id)
                raise _TransientError(f"provider_error_{resp.status_code}")
            resp.raise_for_status()
            async for raw in resp.aiter_bytes():
                raw_chunks.append(raw)
    except httpx.RequestError as exc:
        log.error("session_translator: invoke unreachable for chunk %d: %s", chunk_idx + 1, exc)
        raise _TransientError(f"invoke unreachable: {exc}") from exc

    full_response   = json.loads(b"".join(raw_chunks))
    translated_text = extract_content(full_response.get("output") or {})
    usage           = full_response.get("usage") or {}
    in_tok          = int(usage.get("input_tokens")  or 0)
    out_tok         = int(usage.get("output_tokens") or 0)

    await _update_chunk_row(pool, chunk_row_id, translated_text, in_tok, out_tok)
    return translated_text, in_tok, out_tok


async def _compact_history(
    *,
    client: httpx.AsyncClient,
    session_history: list[dict],
    old_memo: str,
    msg: dict,
    token: str,
) -> str:
    """
    Call the compact model to summarise session_history into a Translation Memo.
    Falls back to the translation model if no compact model is configured.
    Returns the memo string (empty string on any error — translation continues).
    """
    from .chapter_worker import _TransientError, _PermanentError  # local import

    compact_source = msg.get("compact_model_source") or msg["model_source"]
    compact_ref    = msg.get("compact_model_ref")    or msg["model_ref"]

    history_text = "\n\n".join(
        f"[{m['role'].upper()}]\n{m['content']}" for m in session_history
    )
    if old_memo:
        history_text = f"[PREVIOUS MEMO]\n{old_memo}\n\n[NEW EXCHANGES]\n{history_text}"

    compact_payload = {
        "model_source": compact_source,
        "model_ref":    compact_ref,
        "input": {
            "messages": [
                {"role": "system",  "content": _DEFAULT_COMPACT_SYSTEM},
                {"role": "user",    "content": history_text},
            ]
        },
    }

    try:
        raw_chunks: list[bytes] = []
        async with client.stream(
            "POST",
            f"{settings.provider_registry_service_url}/v1/model-registry/invoke",
            json=compact_payload,
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            if resp.status_code >= 400:
                log.warning("compact model returned %d — skipping compaction", resp.status_code)
                return old_memo
            async for raw in resp.aiter_bytes():
                raw_chunks.append(raw)
        full = json.loads(b"".join(raw_chunks))
        memo = extract_content(full.get("output") or {})
        return memo or old_memo
    except Exception as exc:
        # Compaction is best-effort; a failure must not abort the translation
        log.warning("compact call failed (%s) — keeping old memo", exc)
        return old_memo


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _insert_chunk_row(
    pool, chapter_translation_id: UUID, chunk_idx: int,
    chunk_text: str, compact_memo: str,
) -> UUID:
    row = await pool.fetchrow(
        """
        INSERT INTO chapter_translation_chunks
          (chapter_translation_id, chunk_index, chunk_text, compact_memo_applied, status)
        VALUES ($1, $2, $3, $4, 'running')
        ON CONFLICT (chapter_translation_id, chunk_index) DO UPDATE
          SET status = 'running', compact_memo_applied = EXCLUDED.compact_memo_applied
        RETURNING id
        """,
        chapter_translation_id, chunk_idx, chunk_text, compact_memo or None,
    )
    return row["id"]


async def _update_chunk_row(
    pool, chunk_row_id: UUID, translated_text: str, in_tok: int, out_tok: int,
) -> None:
    await pool.execute(
        """
        UPDATE chapter_translation_chunks
        SET translated_text = $1,
            input_tokens    = $2,
            output_tokens   = $3,
            status          = 'completed'
        WHERE id = $4
        """,
        translated_text, in_tok or None, out_tok or None, chunk_row_id,
    )
