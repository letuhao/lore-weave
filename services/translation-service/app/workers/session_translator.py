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

import logging
from typing import Any
from uuid import UUID

from loreweave_llm.errors import (
    LLMAuthFailed,
    LLMDecodeError,
    LLMError,
    LLMInvalidRequest,
    LLMModelNotFound,
    LLMQuotaExceeded,
    LLMStreamNotSupported,
    LLMTransientRetryNeededError,
)
from loreweave_llm.models import Job

from ..config import settings, DEFAULT_COMPACT_SYSTEM_PROMPT, DEFAULT_COMPACT_USER_PROMPT_TPL
from ..llm_client import LLMClient
from .chunk_splitter import estimate_tokens, split_chapter

log = logging.getLogger(__name__)


def _parse_sdk_response(job: Job) -> tuple[str, int, int]:
    """Phase 4c-β — extract (content, input_tokens, output_tokens) from
    a Job returned by the SDK's submit_and_wait for operation='translation'.

    The gateway routes 'translation' to chatAggregator (verified
    aggregator.go:80), so result shape is:
        {"messages": [{"role":"assistant","content":"..."}],
         "usage": {"input_tokens": N, "output_tokens": M}}

    Defensive: handles malformed result (missing keys, wrong types) by
    returning ("", 0, 0). Caller checks job.status before parsing so a
    completed-but-empty job here means the model produced no tokens —
    surface as empty translation upstream.
    """
    result = job.result or {}
    messages_out = result.get("messages") or []
    content = ""
    if isinstance(messages_out, list) and messages_out:
        first = messages_out[0]
        if isinstance(first, dict):
            content = first.get("content", "") or ""
    usage_dict = result.get("usage") or {}
    in_tok = _safe_int(usage_dict.get("input_tokens"))
    out_tok = _safe_int(usage_dict.get("output_tokens"))
    return content, in_tok, out_tok


def _safe_int(value: Any) -> int:
    """Defensive int() coercion — gateway emits ints per chatAggregator
    spec but a wrong-shape future drift would crash the request without
    this. Mirrors knowledge-service's regen helper pattern."""
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

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
    llm_client: LLMClient,
    context_window: int = _FALLBACK_CONTEXT_WINDOW,
) -> tuple[str, int, int]:
    """
    Translate a full chapter using session-based chunking.

    Phase 4c-β: replaces the legacy /v1/model-registry/invoke + JWT
    auth path with the loreweave_llm SDK + internal-token auth.
    Caller (chapter_worker) supplies the llm_client.

    Args:
        chapter_text:           Raw original text.
        source_lang:            Detected source language (e.g. "Chinese").
        msg:                    Full chapter job message (contains model config, prompts, etc.).
        pool:                   asyncpg pool for writing chunk rows.
        chapter_translation_id: UUID of the parent chapter_translations row.
        llm_client:             loreweave_llm SDK wrapper (worker-level singleton).
        context_window:         Model context window in tokens (from provider-registry).

    Returns:
        (translated_body, total_input_tokens, total_output_tokens)
    """
    chunk_size = int(msg.get("chunk_size_tokens") or 2000)
    # Never exceed 1/4 of the model's context window per chunk
    chunk_size = min(chunk_size, context_window // 4)
    chunk_size = max(chunk_size, 100)  # floor to avoid degenerate splits

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
    user_id = msg["user_id"]

    for idx, chunk in enumerate(chunks):
        translated, in_tok, out_tok = await _translate_chunk(
            llm_client=llm_client,
            chunk=chunk,
            chunk_idx=idx,
            total_chunks=len(chunks),
            source_lang=source_lang,
            msg=msg,
            user_id=user_id,
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
                llm_client=llm_client,
                session_history=session_history,
                old_memo=compact_memo,
                msg=msg,
                user_id=user_id,
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
    llm_client: LLMClient,
    chunk: str,
    chunk_idx: int,
    total_chunks: int,
    source_lang: str,
    msg: dict,
    user_id: str,
    session_history: list[dict],
    compact_memo: str,
    pool,
    chapter_translation_id: UUID,
) -> tuple[str, int, int]:
    """
    Invoke the AI model for a single chunk via the loreweave_llm SDK
    (operation='translation'), write the result to
    chapter_translation_chunks, and return
    (translated_text, input_tokens, output_tokens).

    Phase 4c-β: replaces the legacy /v1/model-registry/invoke buffered
    HTTP call. SDK handles transient retry inside submit_and_wait;
    cancelled/failed jobs map to _PermanentError matching the legacy
    billing_rejected / model_not_found / provider_error_* contract.
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

    log.debug(
        "session_translator: invoking model %s/%s for chunk %d/%d (ct=%s)",
        msg["model_source"], msg["model_ref"],
        chunk_idx + 1, total_chunks, chapter_translation_id,
    )
    try:
        sdk_job = await llm_client.submit_and_wait(
            user_id=user_id,
            operation="translation",
            model_source=msg["model_source"],
            model_ref=str(msg["model_ref"]),
            input={"messages": messages},
            chunking=None,  # caller already chunked via split_chapter
            job_meta={
                "chapter_translation_id": str(chapter_translation_id),
                "chunk_idx": chunk_idx,
            },
            transient_retry_budget=1,
        )
    except LLMTransientRetryNeededError as exc:
        log.error(
            "session_translator: transient retry exhausted for chunk %d (ct=%s) code=%s",
            chunk_idx + 1, chapter_translation_id, exc.underlying_code,
        )
        raise _TransientError(f"provider_error_{exc.underlying_code}") from exc
    except LLMQuotaExceeded as exc:
        # /review-impl HIGH#1 — 402 billing/quota: PERMANENT, no retry
        log.error(
            "session_translator: billing_rejected for chunk %d (ct=%s): %s",
            chunk_idx + 1, chapter_translation_id, exc,
        )
        raise _PermanentError("billing_rejected") from exc
    except LLMModelNotFound as exc:
        # /review-impl HIGH#1 — 404 model not found: PERMANENT
        log.error(
            "session_translator: model_not_found for chunk %d (ct=%s): %s",
            chunk_idx + 1, chapter_translation_id, exc,
        )
        raise _PermanentError("model_not_found") from exc
    except (LLMAuthFailed, LLMInvalidRequest, LLMDecodeError, LLMStreamNotSupported) as exc:
        # /review-impl HIGH#1 — auth/validation/decode failures are
        # PERMANENT (config errors won't fix themselves on retry).
        cls = exc.__class__.__name__
        log.error(
            "session_translator: %s for chunk %d (ct=%s): %s",
            cls, chunk_idx + 1, chapter_translation_id, exc,
        )
        raise _PermanentError(f"provider_error_{cls}") from exc
    except LLMError as exc:
        log.error(
            "session_translator: SDK error for chunk %d (ct=%s): %s",
            chunk_idx + 1, chapter_translation_id, exc,
        )
        raise _TransientError(f"invoke unreachable: {exc}") from exc

    log.debug(
        "session_translator: job ended status=%s for chunk %d (ct=%s)",
        sdk_job.status, chunk_idx + 1, chapter_translation_id,
    )

    if sdk_job.status == "cancelled":
        # Operator-initiated LLM-job cancel — surface as permanent so
        # the chapter row stays failed (worker doesn't retry on cancel).
        raise _PermanentError("cancelled")
    if sdk_job.status != "completed":
        # Map gateway error codes to the legacy permanent/transient
        # contract the chapter_worker retry loop expects.
        err_code = sdk_job.error.code if sdk_job.error else "LLM_UNKNOWN_ERROR"
        if err_code in ("LLM_QUOTA_EXCEEDED", "LLM_BILLING_REJECTED"):
            raise _PermanentError("billing_rejected")
        if err_code == "LLM_MODEL_NOT_FOUND":
            raise _PermanentError("model_not_found")
        # 5xx-class upstream errors → transient (worker retries)
        raise _TransientError(f"provider_error_{err_code}")

    translated_text, in_tok, out_tok = _parse_sdk_response(sdk_job)

    await _update_chunk_row(pool, chunk_row_id, translated_text, in_tok, out_tok)
    return translated_text, in_tok, out_tok


async def _compact_history(
    *,
    llm_client: LLMClient,
    session_history: list[dict],
    old_memo: str,
    msg: dict,
    user_id: str,
) -> str:
    """
    Call the compact model to summarise session_history into a Translation Memo.
    Falls back to the translation model if no compact model is configured.
    Returns the memo string (old_memo on any error — translation continues).

    Phase 4c-β: replaces the legacy /v1/model-registry/invoke buffered
    HTTP call. Best-effort contract preserved — any SDK error returns
    old_memo without raising, since compaction is a memory-management
    optimization, not a correctness requirement.
    """
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

    try:
        sdk_job = await llm_client.submit_and_wait(
            user_id=user_id,
            operation="translation",
            model_source=compact_source,
            model_ref=str(compact_ref),
            input={
                "messages": [
                    {"role": "system", "content": compact_system},
                    {"role": "user",   "content": compact_user_msg},
                ],
            },
            chunking=None,
            job_meta={"extractor": "compact_memo"},
            transient_retry_budget=1,
        )
        if sdk_job.status != "completed":
            log.warning(
                "compact model returned status=%s — skipping compaction",
                sdk_job.status,
            )
            return old_memo
        memo, _, _ = _parse_sdk_response(sdk_job)
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
# Phase 8F → V2: Block-level translation pipeline
# ══════════════════════════════════════════════════════════════════════════════

_BLOCK_SYSTEM_PROMPT = """You are a professional {source_lang} ({source_code}) to {target_lang} ({target_code}) translator.

CRITICAL RULES:
1. Each text section is labeled [BLOCK N]. You MUST output the EXACT same [BLOCK N] labels in the EXACT same order.
2. Translate ONLY the text after each [BLOCK N] label. Do NOT add, remove, or reorder blocks.
3. Preserve inline formatting: **bold**, *italic*, `code`, ~~strikethrough~~, __underline__, [link text](url).
4. Output ONLY the translated blocks. No explanations, no commentary, no extra text.
5. You MUST output exactly {block_count} blocks."""

# Max retries per batch when validation fails
_MAX_BATCH_RETRIES = 2


# ── Output validation ────────────────────────────────────────────────────────

class ValidationResult:
    """Result of validating a translated batch output."""
    __slots__ = ("valid", "errors", "warnings")

    def __init__(self) -> None:
        self.valid: bool = True
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.valid = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


def validate_translation_output(
    parsed_blocks: dict[int, str],
    expected_indices: list[int],
    input_texts: dict[int, str],
) -> ValidationResult:
    """Validate LLM translation output for structural correctness.

    Checks:
    1. Block count matches expected
    2. All expected indices present
    3. No unexpected indices
    4. Output length is sane (0.3x-4.0x of input per block)
    """
    result = ValidationResult()

    # Rule 1: Block count
    if len(parsed_blocks) != len(expected_indices):
        result.add_error(
            f"block_count_mismatch: expected {len(expected_indices)}, "
            f"got {len(parsed_blocks)}"
        )

    # Rule 2: All indices present
    missing = set(expected_indices) - set(parsed_blocks.keys())
    if missing:
        result.add_error(f"missing_blocks: {sorted(missing)}")

    # Rule 3: No unexpected indices
    extra = set(parsed_blocks.keys()) - set(expected_indices)
    if extra:
        result.add_error(f"extra_blocks: {sorted(extra)}")

    # Rule 4: Length sanity per block
    for idx, text in parsed_blocks.items():
        if idx in input_texts and input_texts[idx]:
            ratio = len(text) / max(1, len(input_texts[idx]))
            if ratio > 4.0:
                result.add_warning(f"block_{idx}_too_long: {ratio:.1f}x input")
            if ratio < 0.3:
                result.add_warning(f"block_{idx}_too_short: {ratio:.1f}x input")

    return result


# ── Multi-provider token extraction ──────────────────────────────────────────

def extract_token_counts(response: dict) -> tuple[int, int]:
    """Extract input/output token counts from provider response.

    Handles different provider response formats:
    - OpenAI:    {"usage": {"prompt_tokens": N, "completion_tokens": N}}
    - Anthropic: {"usage": {"input_tokens": N, "output_tokens": N}}
    - Ollama:    {"prompt_eval_count": N, "eval_count": N}
    - LM Studio: {"usage": {"prompt_tokens": N, "completion_tokens": N}}
    """
    # Try nested "usage" object first (OpenAI/Anthropic/LM Studio)
    usage = response.get("usage") or {}
    input_tok = (
        usage.get("input_tokens")       # Anthropic
        or usage.get("prompt_tokens")    # OpenAI / LM Studio
        or response.get("prompt_eval_count")  # Ollama (top-level)
        or 0
    )
    output_tok = (
        usage.get("output_tokens")        # Anthropic
        or usage.get("completion_tokens")  # OpenAI / LM Studio
        or response.get("eval_count")      # Ollama (top-level)
        or 0
    )

    input_tok = int(input_tok)
    output_tok = int(output_tok)

    if input_tok == 0 and output_tok == 0:
        log.warning(
            "token_counts_missing: response_keys=%s, usage_keys=%s",
            list(response.keys()), list(usage.keys()),
        )

    return input_tok, output_tok


async def translate_chapter_blocks(
    blocks: list[dict],
    source_lang: str,
    msg: dict,
    pool,
    chapter_translation_id: UUID,
    *,
    llm_client: LLMClient,
    context_window: int = _FALLBACK_CONTEXT_WINDOW,
) -> tuple[list[dict], int, int]:
    """
    Translate a chapter's Tiptap blocks using the block-level pipeline (V2).

    V2 improvements over V1:
    - CJK-aware token estimation
    - Expansion-ratio-aware budget (reserves output + overhead tokens)
    - 40-block hard cap per batch
    - Output validation with retry + correction prompt
    - Multi-provider token extraction (OpenAI/Anthropic/Ollama/LM Studio)
    - Rolling summary context between batches

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
    from .block_classifier import rebuild_block, extract_translatable_text
    from .block_batcher import build_batch_plan, parse_translated_blocks

    target_code = msg.get("target_language", "")

    plan = build_batch_plan(
        blocks,
        context_window_tokens=context_window,
        source_lang=source_lang,
        target_lang=target_code,
    )
    log.info(
        "block_translator_v2: %d blocks (%d translate, %d pass, %d caption) → %d batches (ct=%s)",
        len(plan.all_entries), plan.translatable_count, plan.passthrough_count,
        plan.caption_count, len(plan.batches), chapter_translation_id,
    )

    if not plan.batches:
        return blocks, 0, 0

    user_id = msg["user_id"]

    # V2 P4: Fetch glossary context (once per chapter, stable across all batches)
    from .glossary_client import (
        fetch_translation_glossary, build_glossary_context, auto_correct_glossary,
    )

    # Extract all translatable text for glossary scoring
    all_chapter_text = "\n".join(
        extract_translatable_text(entry.block)
        for entry in plan.all_entries
        if entry.action != "passthrough"
    )

    raw_glossary = await fetch_translation_glossary(
        book_id=msg.get("book_id", ""),
        target_language=target_code,
        chapter_id=msg.get("chapter_id", ""),
    )
    glossary_ctx = build_glossary_context(
        raw_glossary, all_chapter_text, target_code,
    )
    log.info(
        "block_translator_v2: glossary — %d entries, ~%d tokens, %d correction rules (ct=%s)",
        len(glossary_ctx.entries), glossary_ctx.token_estimate,
        len(glossary_ctx.correction_map), chapter_translation_id,
    )

    # Per-block translated texts (index → translated text)
    translated_texts: dict[int, str] = {}
    failed_blocks: set[int] = set()
    total_input = 0
    total_output = 0
    total_glossary_corrections = 0

    # Rolling summary for cross-batch context
    rolling_summary = ""

    for batch_idx, batch in enumerate(plan.batches):
        combined = batch.combined_text()
        # Build input_texts map for validation
        input_texts = {e.index: e.text for e in batch.entries}

        log.info(
            "block_translator_v2: batch %d/%d — %d blocks, ~%d tokens (ct=%s)",
            batch_idx + 1, len(plan.batches), len(batch.entries),
            batch.token_estimate, chapter_translation_id,
        )

        # Build system prompt with block count + glossary
        system_content = _BLOCK_SYSTEM_PROMPT.format_map(_SafeFormatMap({
            "source_lang": _lang_name(source_lang),
            "source_code": source_lang,
            "target_lang": _lang_name(target_code),
            "target_code": target_code,
            "block_count": str(len(batch.entries)),
        }))
        if glossary_ctx.prompt_block:
            system_content += "\n\n" + glossary_ctx.prompt_block
            system_content += (
                "\n\nIMPORTANT: For names and terms listed in the GLOSSARY above, "
                "you MUST use the EXACT translations provided. Do NOT invent your own."
            )

        # Build user message with optional rolling summary
        user_parts = []
        if rolling_summary:
            user_parts.append(
                f"[Summary of previously translated content]\n{rolling_summary}\n"
            )
        user_parts.append(
            f"Translate the following {len(batch.entries)} blocks "
            f"from {_lang_name(source_lang)} to {_lang_name(target_code)}:\n\n{combined}"
        )
        user_content = "\n".join(user_parts)

        # Retry loop with validation
        parsed = None
        correction_hint = ""
        for attempt in range(_MAX_BATCH_RETRIES + 1):
            messages = [
                {"role": "system", "content": system_content},
            ]
            if correction_hint:
                # Add correction as assistant acknowledgment + user re-request
                messages.append({"role": "assistant", "content": "I understand. Let me fix the output."})
                messages.append({"role": "user", "content": correction_hint})
            else:
                messages.append({"role": "user", "content": user_content})

            try:
                # Phase 4c-β: SDK call replaces /v1/model-registry/invoke.
                # `break` on non-completed status preserves the legacy
                # "don't retry on HTTP errors" semantic — SDK handles
                # transient retries internally; reaching here with
                # non-completed means a permanent error.
                sdk_job = await llm_client.submit_and_wait(
                    user_id=user_id,
                    operation="translation",
                    model_source=msg["model_source"],
                    model_ref=str(msg["model_ref"]),
                    input={"messages": messages},
                    chunking=None,
                    job_meta={
                        "chapter_translation_id": str(chapter_translation_id),
                        "batch_idx": batch_idx,
                        "attempt": attempt,
                    },
                    transient_retry_budget=1,
                )
                if sdk_job.status != "completed":
                    err_code = sdk_job.error.code if sdk_job.error else "unknown"
                    log.error(
                        "block_translator_v2: batch %d attempt %d job ended status=%s code=%s",
                        batch_idx + 1, attempt + 1, sdk_job.status, err_code,
                    )
                    break  # don't retry on permanent errors

                response_text, in_tok, out_tok = _parse_sdk_response(sdk_job)
                total_input += in_tok
                total_output += out_tok

                # Parse [BLOCK N] markers
                parsed = parse_translated_blocks(response_text, batch.block_indices)

                # V2: Validate output
                validation = validate_translation_output(
                    parsed, batch.block_indices, input_texts,
                )

                if validation.warnings:
                    log.warning(
                        "block_translator_v2: batch %d warnings: %s",
                        batch_idx + 1, validation.warnings,
                    )

                if validation.valid:
                    log.info(
                        "block_translator_v2: batch %d attempt %d — valid, %d/%d blocks",
                        batch_idx + 1, attempt + 1, len(parsed), len(batch.entries),
                    )
                    break  # success
                else:
                    log.warning(
                        "block_translator_v2: batch %d attempt %d — validation failed: %s",
                        batch_idx + 1, attempt + 1, validation.errors,
                    )
                    if attempt < _MAX_BATCH_RETRIES:
                        # Build correction prompt for retry
                        correction_hint = (
                            f"Your previous output had errors: {'; '.join(validation.errors)}. "
                            f"Please translate exactly {len(batch.entries)} blocks "
                            f"with indices {batch.block_indices}. "
                            f"Output each block with its [BLOCK N] marker.\n\n{combined}"
                        )
                    else:
                        log.error(
                            "block_translator_v2: batch %d failed after %d retries: %s",
                            batch_idx + 1, _MAX_BATCH_RETRIES, validation.errors,
                        )
                        # Mark missing blocks as failed
                        missing = set(batch.block_indices) - set(parsed.keys())
                        failed_blocks.update(missing)

            except (LLMQuotaExceeded, LLMModelNotFound, LLMAuthFailed,
                    LLMInvalidRequest, LLMDecodeError, LLMStreamNotSupported) as exc:
                # /review-impl HIGH#1 — permanent SDK errors won't fix
                # themselves on retry; mark all batch blocks failed
                # immediately + break out of the validation retry loop.
                log.error(
                    "block_translator_v2: batch %d permanent SDK error %s — failing batch",
                    batch_idx + 1, exc.__class__.__name__,
                )
                parsed = None
                failed_blocks.update(batch.block_indices)
                break
            except Exception as exc:
                log.error("block_translator_v2: batch %d attempt %d failed: %s", batch_idx + 1, attempt + 1, exc)
                parsed = None
                if attempt == _MAX_BATCH_RETRIES:
                    failed_blocks.update(batch.block_indices)
                continue

        # Merge successfully parsed blocks + auto-correct glossary
        if parsed:
            # V2 P6: Auto-correct untranslated source terms
            if glossary_ctx.correction_map:
                for idx in list(parsed.keys()):
                    corrected, count = auto_correct_glossary(
                        parsed[idx], glossary_ctx.correction_map,
                    )
                    if count > 0:
                        parsed[idx] = corrected
                        total_glossary_corrections += count

            translated_texts.update(parsed)

            # Update rolling summary (last ~3 sentences of translated text)
            last_translated = " ".join(
                parsed[idx] for idx in sorted(parsed.keys())
            )
            sentences = [s.strip() for s in last_translated.replace("\n", ". ").split(".") if s.strip()]
            rolling_summary = ". ".join(sentences[-5:]) + "." if sentences else ""

    if total_glossary_corrections > 0:
        log.info(
            "block_translator_v2: auto-corrected %d glossary terms (ct=%s)",
            total_glossary_corrections, chapter_translation_id,
        )

    # Reassemble: for each block, use translated text or keep original
    result_blocks: list[dict] = []
    for entry in plan.all_entries:
        if entry.index in translated_texts:
            result_blocks.append(rebuild_block(entry.block, translated_texts[entry.index]))
        else:
            result_blocks.append(entry.block)

    translated_count = len(translated_texts)
    failed_count = len(failed_blocks)
    log.info(
        "block_translator_v2: done — %d blocks, %d translated, %d failed, in=%d out=%d (ct=%s)",
        len(result_blocks), translated_count, failed_count,
        total_input, total_output, chapter_translation_id,
    )
    if failed_blocks:
        log.warning(
            "block_translator_v2: FAILED block indices (fell back to original): %s (ct=%s)",
            sorted(failed_blocks), chapter_translation_id,
        )

    return result_blocks, total_input, total_output
