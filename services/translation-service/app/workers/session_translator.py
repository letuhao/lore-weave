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
from ..config import settings, DEFAULT_COMPACT_SYSTEM_PROMPT, DEFAULT_COMPACT_USER_PROMPT_TPL
from .chunk_splitter import estimate_tokens, split_chapter
from .content_extractor import extract_content

log = logging.getLogger(__name__)

_JWT_TTL = 4 * 3600  # 4 hours — covers very long chapter translation sessions

# BCP-47 code → human-readable language name (lowercase key lookup)
# Generated from data/language_codes.txt — deduplicated, first occurrence wins.
_LANG_NAMES: dict[str, str] = {
    "aa":          "Afar",
    "ab":          "Abkhazian",
    "af":          "Afrikaans",
    "ak":          "Akan",
    "am":          "Amharic",
    "an":          "Aragonese",
    "ar":          "Arabic",
    "as":          "Assamese",
    "az":          "Azerbaijani",
    "az-arab":     "Azerbaijani",
    "az-cyrl":     "Azerbaijani",
    "az-latn":     "Azerbaijani",
    "ba":          "Bashkir",
    "be":          "Belarusian",
    "be-tarask":   "Belarusian",
    "bg":          "Bulgarian",
    "bm":          "Bambara",
    "bm-nkoo":     "Bambara",
    "bn":          "Bengali",
    "bo":          "Tibetan",
    "br":          "Breton",
    "bs":          "Bosnian",
    "bs-cyrl":     "Bosnian",
    "bs-latn":     "Bosnian",
    "ca":          "Catalan",
    "ce":          "Chechen",
    "co":          "Corsican",
    "cs":          "Czech",
    "cv":          "Chuvash",
    "cy":          "Welsh",
    "da":          "Danish",
    "de":          "German",
    "dv":          "Divehi",
    "dz":          "Dzongkha",
    "ee":          "Ewe",
    "el":          "Greek",
    "el-polyton":  "Greek",
    "en":          "English",
    "eo":          "Esperanto",
    "es":          "Spanish",
    "et":          "Estonian",
    "eu":          "Basque",
    "fa":          "Persian",
    "ff":          "Fulah",
    "ff-adlm":     "Fulah",
    "ff-latn":     "Fulah",
    "fi":          "Finnish",
    "fil-ph":      "Filipino",
    "fo":          "Faroese",
    "fr":          "French",
    "fy":          "Western Frisian",
    "ga":          "Irish",
    "gd":          "Scottish Gaelic",
    "gl":          "Galician",
    "gn":          "Guarani",
    "gu":          "Gujarati",
    "gv":          "Manx",
    "ha":          "Hausa",
    "ha-arab":     "Hausa",
    "he":          "Hebrew",
    "hi":          "Hindi",
    "hi-latn":     "Hindi",
    "hr":          "Croatian",
    "ht":          "Haitian",
    "hu":          "Hungarian",
    "hy":          "Armenian",
    "ia":          "Interlingua",
    "id":          "Indonesian",
    "ie":          "Interlingue",
    "ig":          "Igbo",
    "ii":          "Sichuan Yi",
    "ik":          "Inupiaq",
    "io":          "Ido",
    "is":          "Icelandic",
    "it":          "Italian",
    "iu":          "Inuktitut",
    "iu-latn":     "Inuktitut",
    "ja":          "Japanese",
    "jv":          "Javanese",
    "ka":          "Georgian",
    "ki":          "Kikuyu",
    "kk":          "Kazakh",
    "kk-arab":     "Kazakh",
    "kk-cyrl":     "Kazakh",
    "kl":          "Kalaallisut",
    "km":          "Central Khmer",
    "kn":          "Kannada",
    "ko":          "Korean",
    "ks":          "Kashmiri",
    "ks-arab":     "Kashmiri",
    "ks-deva":     "Kashmiri",
    "ku":          "Kurdish",
    "kw":          "Cornish",
    "ky":          "Kyrgyz",
    "la":          "Latin",
    "lb":          "Luxembourgish",
    "lg":          "Ganda",
    "ln":          "Lingala",
    "lo":          "Lao",
    "lt":          "Lithuanian",
    "lu":          "Luba-Katanga",
    "lv":          "Latvian",
    "mg":          "Malagasy",
    "mi":          "Maori",
    "mk":          "Macedonian",
    "ml":          "Malayalam",
    "mn":          "Mongolian",
    "mn-mong":     "Mongolian",
    "mr":          "Marathi",
    "ms":          "Malay",
    "ms-arab":     "Malay",
    "mt":          "Maltese",
    "my":          "Burmese",
    "nb":          "Norwegian Bokmål",
    "nd":          "North Ndebele",
    "ne":          "Nepali",
    "nl":          "Dutch",
    "nn":          "Norwegian Nynorsk",
    "no":          "Norwegian",
    "nr":          "South Ndebele",
    "nv":          "Navajo",
    "ny":          "Chichewa",
    "oc":          "Occitan",
    "om":          "Oromo",
    "or":          "Oriya",
    "os":          "Ossetian",
    "pa":          "Punjabi",
    "pa-arab":     "Punjabi",
    "pa-guru":     "Punjabi",
    "pl":          "Polish",
    "ps":          "Pashto",
    "pt":          "Portuguese",
    "pt-br":       "Portuguese",
    "qu":          "Quechua",
    "rm":          "Romansh",
    "rn":          "Rundi",
    "ro":          "Romanian",
    "ru":          "Russian",
    "rw":          "Kinyarwanda",
    "sa":          "Sanskrit",
    "sc":          "Sardinian",
    "sd":          "Sindhi",
    "sd-arab":     "Sindhi",
    "sd-deva":     "Sindhi",
    "se":          "Northern Sami",
    "sg":          "Sango",
    "si":          "Sinhala",
    "sk":          "Slovak",
    "sl":          "Slovenian",
    "sn":          "Shona",
    "so":          "Somali",
    "sq":          "Albanian",
    "sr":          "Serbian",
    "sr-cyrl":     "Serbian",
    "sr-latn":     "Serbian",
    "ss":          "Swati",
    "st":          "Southern Sotho",
    "su":          "Sundanese",
    "su-latn":     "Sundanese",
    "sv":          "Swedish",
    "sw":          "Swahili",
    "ta":          "Tamil",
    "te":          "Telugu",
    "tg":          "Tajik",
    "th":          "Thai",
    "ti":          "Tigrinya",
    "tk":          "Turkmen",
    "tl":          "Tagalog",
    "tn":          "Tswana",
    "to":          "Tonga",
    "tr":          "Turkish",
    "ts":          "Tsonga",
    "tt":          "Tatar",
    "ug":          "Uyghur",
    "uk":          "Ukrainian",
    "ur":          "Urdu",
    "uz":          "Uzbek",
    "uz-arab":     "Uzbek",
    "uz-cyrl":     "Uzbek",
    "uz-latn":     "Uzbek",
    "ve":          "Venda",
    "vi":          "Vietnamese",
    "vo":          "Volapük",
    "wa":          "Walloon",
    "wo":          "Wolof",
    "xh":          "Xhosa",
    "yi":          "Yiddish",
    "yo":          "Yoruba",
    "za":          "Zhuang",
    "zh":          "Chinese",
    "zh-hans":     "Chinese Simplified",
    "zh-hant":     "Chinese Traditional",
    "zu":          "Zulu",
}


def _lang_name(code: str) -> str:
    """Return the human-readable name for a BCP-47 language code, or the code itself."""
    return _LANG_NAMES.get(code.lower(), code)


class _SafeFormatMap(dict):
    """format_map helper: leaves {unknown_key} intact instead of raising KeyError."""
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"

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
    from ..config import DEFAULT_USER_PROMPT_TPL
    tpl = msg.get("user_prompt_tpl") or DEFAULT_USER_PROMPT_TPL
    target_code = msg.get("target_language", "")
    part_note = f"[Part {chunk_idx + 1}/{total_chunks}]\n" if total_chunks > 1 else ""
    return part_note + tpl.format_map(_SafeFormatMap({
        # New canonical variables
        "source_lang":     _lang_name(source_lang),
        "source_code":     source_lang,
        "target_lang":     _lang_name(target_code),
        "target_code":     target_code,
        # Backward-compat aliases (point to codes, same as before)
        "source_language": source_lang,
        "target_language": target_code,
        # Chapter content
        "chapter_text":    chunk,
    }))


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
    from ..config import DEFAULT_SYSTEM_PROMPT
    target_code = msg.get("target_language", "")
    sys_tpl = msg.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
    system_content = sys_tpl.format_map(_SafeFormatMap({
        "source_lang":     _lang_name(source_lang),
        "source_code":     source_lang,
        "target_lang":     _lang_name(target_code),
        "target_code":     target_code,
        "source_language": source_lang,
        "target_language": target_code,
    }))
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

    compact_system   = msg.get("compact_system_prompt")   or DEFAULT_COMPACT_SYSTEM_PROMPT
    compact_user_tpl = msg.get("compact_user_prompt_tpl") or DEFAULT_COMPACT_USER_PROMPT_TPL
    compact_user_msg = compact_user_tpl.format_map(_SafeFormatMap({"history_text": history_text}))

    compact_payload = {
        "model_source": compact_source,
        "model_ref":    compact_ref,
        "input": {
            "messages": [
                {"role": "system", "content": compact_system},
                {"role": "user",   "content": compact_user_msg},
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


# ══════════════════════════════════════════════════════════════════════════════
# Phase 8F: Block-level translation pipeline
# ══════════════════════════════════════════════════════════════════════════════

_BLOCK_SYSTEM_PROMPT = """You are a professional {source_lang} ({source_code}) to {target_lang} ({target_code}) translator.

CRITICAL RULES:
1. Each text section is labeled [BLOCK N]. You MUST output the EXACT same [BLOCK N] labels in the EXACT same order.
2. Translate ONLY the text after each [BLOCK N] label. Do NOT add, remove, or reorder blocks.
3. Preserve inline formatting: **bold**, *italic*, `code`, ~~strikethrough~~, __underline__, [link text](url).
4. Output ONLY the translated blocks. No explanations, no commentary, no extra text."""


async def translate_chapter_blocks(
    blocks: list[dict],
    source_lang: str,
    msg: dict,
    pool,
    chapter_translation_id: UUID,
    *,
    context_window: int = _FALLBACK_CONTEXT_WINDOW,
) -> tuple[list[dict], int, int]:
    """
    Translate a chapter's Tiptap blocks using the block-level pipeline.

    1. Classify blocks (translate / passthrough / caption_only)
    2. Batch translatable blocks within token budget
    3. Translate each batch via LLM with [BLOCK N] markers
    4. Parse response, rebuild blocks
    5. Reassemble full Tiptap content array

    Args:
        blocks:                 Tiptap content array (list of block dicts).
        source_lang:            Source language code.
        msg:                    Job message with model config, prompts, etc.
        pool:                   asyncpg pool for chunk rows.
        chapter_translation_id: UUID of the chapter_translations row.
        context_window:         Model context window in tokens.

    Returns:
        (translated_blocks, total_input_tokens, total_output_tokens)
    """
    from .block_classifier import classify_block, extract_translatable_text, rebuild_block
    from .block_batcher import build_batch_plan, parse_translated_blocks

    plan = build_batch_plan(blocks, context_window_tokens=context_window)
    log.info(
        "block_translator: %d blocks (%d translate, %d pass, %d caption) → %d batches (ct=%s)",
        len(plan.all_entries), plan.translatable_count, plan.passthrough_count,
        plan.caption_count, len(plan.batches), chapter_translation_id,
    )

    if not plan.batches:
        # All blocks are passthrough — return original
        return blocks, 0, 0

    timeout_secs = msg.get("invoke_timeout_secs") or 300
    read_timeout = float(timeout_secs) if timeout_secs and timeout_secs > 0 else None
    token = mint_user_jwt(msg["user_id"], settings.jwt_secret, ttl_seconds=_JWT_TTL)

    # Build system prompt
    target_code = msg.get("target_language", "")
    system_content = _BLOCK_SYSTEM_PROMPT.format_map(_SafeFormatMap({
        "source_lang": _lang_name(source_lang),
        "source_code": source_lang,
        "target_lang": _lang_name(target_code),
        "target_code": target_code,
    }))

    # Per-block translated texts (index → translated text)
    translated_texts: dict[int, str] = {}
    total_input = 0
    total_output = 0

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, write=60.0, read=read_timeout, pool=5.0)
    ) as client:
        for batch_idx, batch in enumerate(plan.batches):
            combined = batch.combined_text()
            log.info(
                "block_translator: batch %d/%d — %d blocks, ~%d tokens (ct=%s)",
                batch_idx + 1, len(plan.batches), len(batch.entries),
                batch.token_estimate, chapter_translation_id,
            )

            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": f"Translate the following blocks from {_lang_name(source_lang)} to {_lang_name(target_code)}:\n\n{combined}"},
            ]

            invoke_payload = {
                "model_source": msg["model_source"],
                "model_ref": msg["model_ref"],
                "input": {"messages": messages},
            }

            try:
                raw_chunks: list[bytes] = []
                async with client.stream(
                    "POST",
                    f"{settings.provider_registry_service_url}/v1/model-registry/invoke",
                    json=invoke_payload,
                    headers={"Authorization": f"Bearer {token}"},
                ) as resp:
                    if resp.status_code >= 400:
                        log.error("block_translator: batch %d invoke returned %d", batch_idx + 1, resp.status_code)
                        continue  # skip failed batch, blocks will use originals
                    async for raw in resp.aiter_bytes():
                        raw_chunks.append(raw)

                full_response = json.loads(b"".join(raw_chunks))
                response_text = extract_content(full_response.get("output") or {})
                usage = full_response.get("usage") or {}
                total_input += int(usage.get("input_tokens") or 0)
                total_output += int(usage.get("output_tokens") or 0)

                # Parse [BLOCK N] markers
                parsed = parse_translated_blocks(response_text, batch.block_indices)
                translated_texts.update(parsed)

                log.info(
                    "block_translator: batch %d done — parsed %d/%d blocks",
                    batch_idx + 1, len(parsed), len(batch.entries),
                )
            except Exception as exc:
                log.error("block_translator: batch %d failed: %s", batch_idx + 1, exc)
                continue  # skip failed batch

    # Reassemble: for each block, use translated text or keep original
    result_blocks: list[dict] = []
    for entry in plan.all_entries:
        if entry.index in translated_texts:
            result_blocks.append(rebuild_block(entry.block, translated_texts[entry.index]))
        else:
            result_blocks.append(entry.block)

    log.info(
        "block_translator: done — %d blocks, %d translated, in=%d out=%d (ct=%s)",
        len(result_blocks), len(translated_texts), total_input, total_output,
        chapter_translation_id,
    )
    return result_blocks, total_input, total_output
