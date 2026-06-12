"""LLM re-arch Phase 2b-T3a — event-driven decouple of the v2 BLOCK translate stage.

The block path is the REAL-DATA path (imported novels carry a Tiptap body → block
pipeline; the campaign's v3 translate stage delegates here). This module ports the
synchronous `session_translator.translate_chapter_blocks` + its per-batch
`translate_batch_with_retry` validate/correction loop into a resumable
submit→persist→release state machine driven by the job's terminal event — so a
worker coroutine isn't pinned for the whole chapter, and EVERY LLM call (including
each validation-retry attempt) is a fire-and-forget submit, not a blocking wait.

Reuses the T2 consumer (`llm_terminal_consumer`) + `chapter_worker._finalize_chapter`
unchanged — only the engine + the resume_state shape differ (`mode='block'`).

Like decoupled_translate, this is a PURE state machine (no DB/SDK — unit-tested) +
a thin async shell. Behind the same `translation_decouple_enabled` flag.

V3 verify/correct decouple is a follow-up layer (T3b) — this increment decouples
the translate stage (the dominant LLM cost).
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from ..llm_client import LLMClient
from .chunk_splitter import estimate_tokens
from .session_translator import _parse_sdk_response, validate_translation_output

log = logging.getLogger("translation.decoupled.block")

# ── PURE state machine ────────────────────────────────────────────────────────
# resume_state (JSONB), mode='block':
#   blocks:                  [Tiptap block dict, ...]   original body (for rebuild)
#   batches:                 [{block_indices:[int], combined:str,
#                              input_texts:{str(idx):str}, token_estimate:int}, ...]
#   glossary_prompt_block:   str    appended to the system prompt (stable per chapter)
#   glossary_correction_map: {str:str}   source→target auto-correct rules
#   source_lang / target_code: str
#   translatable_count:      int    (total-failure guard at finalize)
#   max_retries:             int
#   extra_system:            str    (V3 injected context; "" for plain v2)
#   batch_idx:               int    index of the batch being processed
#   attempt:                 int    attempt within the batch (0 = first)
#   correction_hint:         str    "" = first attempt; set on a retry
#   rolling_summary:         str    cross-batch context (last ~5 sentences)
#   translated_texts:        {str(idx):str}   accumulated per-block outputs
#   failed_blocks:           [int]
#   total_input / total_output: int
#   awaiting:                "translate_batch"

_BLOCK_MARKER = "[BLOCK {i}]"


def new_block_resume_state(
    *, blocks: list[dict], batches: list[dict], glossary_prompt_block: str,
    glossary_correction_map: dict[str, str], source_lang: str, target_code: str,
    translatable_count: int, max_retries: int, extra_system: str,
) -> dict[str, Any]:
    return {
        "mode": "block",
        "blocks": blocks,
        "batches": batches,
        "glossary_prompt_block": glossary_prompt_block,
        "glossary_correction_map": glossary_correction_map,
        "source_lang": source_lang,
        "target_code": target_code,
        "translatable_count": translatable_count,
        "max_retries": max_retries,
        "extra_system": extra_system,
        "batch_idx": 0,
        "attempt": 0,
        "correction_hint": "",
        "rolling_summary": "",
        "translated_texts": {},
        "failed_blocks": [],
        "total_input": 0,
        "total_output": 0,
        "awaiting": "translate_batch",
    }


def decide_block_action(rs: dict[str, Any]) -> tuple:
    """Pure: ("translate_batch", batch_idx, attempt) while batches remain, else
    ("finalize",). Stateless-by-construction — apply_batch_result advances batch_idx
    on accept and bumps attempt on a retry."""
    if rs["batch_idx"] >= len(rs["batches"]):
        return ("finalize",)
    return ("translate_batch", rs["batch_idx"], rs["attempt"])


def build_batch_messages(rs: dict[str, Any]) -> list[dict]:
    """Pure: messages for the current (batch_idx, attempt). Mirrors
    translate_chapter_blocks' system/user build + translate_batch_with_retry's
    correction-prompt retry. Uses the CURRENT rolling_summary (so it can't be
    pre-serialized) or the correction_hint on a retry."""
    from .session_translator import _BLOCK_SYSTEM_PROMPT, _SafeFormatMap, _lang_name

    batch = rs["batches"][rs["batch_idx"]]
    combined = batch["combined"]
    block_indices = batch["block_indices"]

    system_content = _BLOCK_SYSTEM_PROMPT.format_map(_SafeFormatMap({
        "source_lang": _lang_name(rs["source_lang"]),
        "source_code": rs["source_lang"],
        "target_lang": _lang_name(rs["target_code"]),
        "target_code": rs["target_code"],
        "block_count": str(len(block_indices)),
    }))
    if rs["glossary_prompt_block"]:
        system_content += "\n\n" + rs["glossary_prompt_block"]
        system_content += (
            "\n\nIMPORTANT: For names and terms listed in the GLOSSARY above, "
            "you MUST use the EXACT translations provided. Do NOT invent your own."
        )
    if rs["extra_system"]:
        system_content += "\n\n" + rs["extra_system"]

    messages = [{"role": "system", "content": system_content}]
    if rs["correction_hint"]:
        messages.append({"role": "assistant", "content": "I understand. Let me fix the output."})
        messages.append({"role": "user", "content": rs["correction_hint"]})
    else:
        user_parts = []
        if rs["rolling_summary"]:
            user_parts.append(
                f"[Summary of previously translated content]\n{rs['rolling_summary']}\n"
            )
        user_parts.append(
            f"Translate the following {len(block_indices)} blocks "
            f"from {_lang_name(rs['source_lang'])} to {_lang_name(rs['target_code'])}:\n\n{combined}"
        )
        messages.append({"role": "user", "content": "\n".join(user_parts)})
    return messages


def _rolling_summary(parsed: dict[int, str]) -> str:
    """Pure: last ~5 sentences of the batch's translated text (verbatim from
    translate_chapter_blocks)."""
    last_translated = " ".join(parsed[idx] for idx in sorted(parsed.keys()))
    sentences = [s.strip() for s in last_translated.replace("\n", ". ").split(".") if s.strip()]
    return ". ".join(sentences[-5:]) + "." if sentences else ""


def _correction_hint(block_indices: list[int], errors: list[str], combined: str) -> str:
    return (
        f"Your previous output had errors: {'; '.join(errors)}. "
        f"Please translate exactly {len(block_indices)} blocks "
        f"with indices {block_indices}. "
        f"Output each block with its [BLOCK N] marker.\n\n{combined}"
    )


def apply_batch_result(
    rs: dict[str, Any], parsed: dict[int, str], in_tok: int, out_tok: int,
    valid: bool, errors: list[str],
) -> dict[str, Any]:
    """Pure: fold one batch ATTEMPT. `parsed` is the (already glossary-corrected)
    {idx:text} output; `valid`/`errors` from validate_translation_output.

    Accept (valid OR out of attempts): merge into translated_texts, refresh the
    rolling summary, record any unparsed blocks as failed (only on a final-attempt
    failure), advance batch_idx, reset attempt/correction_hint.
    Retry (invalid AND attempts left): set correction_hint, bump attempt."""
    out = dict(rs)
    out["total_input"] = rs["total_input"] + in_tok
    out["total_output"] = rs["total_output"] + out_tok
    batch = rs["batches"][rs["batch_idx"]]
    block_indices = batch["block_indices"]
    attempts_left = rs["attempt"] < rs["max_retries"]

    if valid or not attempts_left:
        tt = dict(rs["translated_texts"])
        for idx, text in parsed.items():
            tt[str(idx)] = text
        out["translated_texts"] = tt
        if parsed:
            out["rolling_summary"] = _rolling_summary(parsed)
        if not valid:
            failed = set(rs["failed_blocks"]) | (set(block_indices) - set(parsed.keys()))
            out["failed_blocks"] = sorted(failed)
        out["batch_idx"] = rs["batch_idx"] + 1
        out["attempt"] = 0
        out["correction_hint"] = ""
    else:
        out["attempt"] = rs["attempt"] + 1
        out["correction_hint"] = _correction_hint(block_indices, errors, batch["combined"])
    return out


def reassemble_blocks(rs: dict[str, Any]) -> tuple[list[dict], int]:
    """Pure: rebuild the Tiptap body — translated text where we have it, original
    block otherwise (failed blocks fall back). Returns (blocks, translated_count).
    Mirrors translate_chapter_blocks' reassembly (keyed on block position)."""
    from .block_classifier import rebuild_block

    tt = rs["translated_texts"]
    result: list[dict] = []
    for i, block in enumerate(rs["blocks"]):
        text = tt.get(str(i))
        result.append(rebuild_block(block, text) if text else block)
    return result, len(tt)


def memo_from_translated(rs: dict[str, Any]) -> str:
    """Pure: cross-chapter memo = translated-only text in block order (M4c — failed
    blocks fell back to original and must NOT pollute the memo)."""
    tt = rs["translated_texts"]
    return "\n".join(tt[k] for k in sorted(tt, key=int) if tt[k])


# ── async shell — DB I/O + submit + resume (driven by the consumer) ────────────

async def start_chapter_blocks(
    *, pool, llm_client: LLMClient, chapter_translation_id: UUID,
    blocks: list[dict], source_lang: str, msg: dict, context_window: int,
    chapter_text: str = "",
) -> bool:
    """Build the batch plan + glossary context, seed resume_state, submit batch 0.
    Returns True if a batch was submitted (chapter now in-flight → the consumer
    finalizes); False if there were NO translatable batches (the caller falls
    through to the synchronous finalize of the original blocks, matching the sync
    path's empty-plan behaviour). Returns immediately (released)."""
    from .block_batcher import build_batch_plan
    from .block_classifier import extract_translatable_text
    from .glossary_client import build_glossary_context, fetch_translation_glossary

    target_code = msg.get("target_language", "")
    extra_system = msg.get("extra_system", "") or ""
    plan = build_batch_plan(
        blocks, context_window_tokens=context_window, source_lang=source_lang,
        target_lang=target_code, extra_system_tokens=estimate_tokens(extra_system),
    )
    if not plan.batches:
        return False

    all_chapter_text = "\n".join(
        extract_translatable_text(e.block) for e in plan.all_entries if e.action != "passthrough"
    )
    raw_glossary = await fetch_translation_glossary(
        book_id=msg.get("book_id", ""), target_language=target_code,
        chapter_id=msg.get("chapter_id", ""),
    )
    glossary_ctx = build_glossary_context(raw_glossary, all_chapter_text, target_code)
    await _record_glossary_usage(pool, chapter_translation_id, glossary_ctx.used_entity_ids)

    batches = [
        {
            "block_indices": b.block_indices,
            "combined": b.combined_text(),
            "input_texts": {str(e.index): e.text for e in b.entries},
            "token_estimate": b.token_estimate,
        }
        for b in plan.batches
    ]
    from .session_translator import _MAX_BATCH_RETRIES

    rs = new_block_resume_state(
        blocks=blocks, batches=batches,
        glossary_prompt_block=glossary_ctx.prompt_block or "",
        glossary_correction_map=dict(glossary_ctx.correction_map or {}),
        source_lang=source_lang, target_code=target_code,
        translatable_count=plan.translatable_count, max_retries=_MAX_BATCH_RETRIES,
        extra_system=extra_system,
    )
    rs["msg"] = msg
    rs["context_window"] = context_window
    rs["chapter_text"] = chapter_text  # quality-feed source_text at finalize (M7d parity)
    await _submit_next_batch(ex=pool, llm_client=llm_client,
                             chapter_translation_id=chapter_translation_id, rs=rs)
    return True


async def resume(
    *, pool, llm_client: LLMClient, job, chapter_translation_id: UUID, finalize_cb,
) -> None:
    """Consumer entry: a terminal event for this chapter's in-flight batch job
    arrived. Parse + validate + glossary-correct → fold → submit the next attempt /
    batch, or finalize. `finalize_cb(translated_body_json, in, out, memo_text)`."""
    from .block_batcher import parse_translated_blocks
    from .glossary_client import auto_correct_glossary

    # D-2B-TRANSL-RESUME-RACE — the fold is a read-modify-write on resume_state with no
    # natural dedup (the consumer's _load_for_job gate matches the CURRENT provider_job_id,
    # but the sweeper and multiple replicas can drive the SAME terminal concurrently). We
    # serialise under a row lock and re-verify provider_job_id still equals THIS job; the
    # next-batch submit + its provider_job_id advance happen UNDER the lock, so the loser
    # re-reads the advanced id and skips → no double batch-submit. Finalize stays idempotent
    # and runs AFTER the lock (calling _finalize_chapter — which locks the same row on its
    # own connection — nested inside this tx would deadlock).
    job_uuid = UUID(str(job.job_id))
    finalize_payload = None
    fail_reason = None
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT resume_state, provider_job_id FROM chapter_translations WHERE id=$1 FOR UPDATE",
                chapter_translation_id,
            )
            if row is None or row["resume_state"] is None:
                return  # finalized/cleared by a concurrent resume
            if row["provider_job_id"] != job_uuid:
                return  # this terminal already folded + advanced by a concurrent resume
            rs = row["resume_state"]
            rs = rs if isinstance(rs, dict) else json.loads(rs)

            if job.status != "completed":
                # Permanent batch failure — accept what we have so far as a failed attempt
                # at the LAST attempt boundary (mirrors translate_batch_with_retry's break).
                rs = apply_batch_result(
                    dict(rs, attempt=rs["max_retries"]), parsed={}, in_tok=0, out_tok=0,
                    valid=False, errors=[f"job status={job.status}"],
                )
            else:
                response_text, in_tok, out_tok = _parse_sdk_response(job)
                batch = rs["batches"][rs["batch_idx"]]
                block_indices = batch["block_indices"]
                input_texts = {int(k): v for k, v in batch["input_texts"].items()}
                parsed = parse_translated_blocks(response_text, block_indices)
                validation = validate_translation_output(parsed, block_indices, input_texts)
                # Glossary auto-correct (only matters on an accepted batch; harmless on retry).
                cmap = rs["glossary_correction_map"]
                if cmap and parsed:
                    for idx in list(parsed.keys()):
                        corrected, count = auto_correct_glossary(parsed[idx], cmap)
                        if count > 0:
                            parsed[idx] = corrected
                rs = apply_batch_result(
                    rs, parsed=parsed, in_tok=in_tok, out_tok=out_tok,
                    valid=validation.valid, errors=validation.errors,
                )

            action = decide_block_action(rs)
            if action[0] != "finalize":
                await _submit_next_batch(ex=conn, llm_client=llm_client,
                                         chapter_translation_id=chapter_translation_id, rs=rs)
                return
            result_blocks, translated_count = reassemble_blocks(rs)
            # Total-failure guard (TR-4): translatable blocks existed but none translated
            # → FAIL rather than silently persist all-original as "completed".
            if rs["translatable_count"] > 0 and translated_count == 0:
                fail_reason = (
                    f"translation produced no output: 0/{rs['translatable_count']} blocks translated"
                )
            else:
                finalize_payload = (
                    json.dumps(result_blocks), rs["total_input"], rs["total_output"],
                    memo_from_translated(rs),
                )

    # ── outside the FOR UPDATE lock ──
    if fail_reason is not None:
        await _clear_resume_state(pool, chapter_translation_id)
        await _fail(pool, chapter_translation_id, fail_reason)
        return
    if finalize_payload is not None:
        body_json, total_in, total_out, memo = finalize_payload
        # Finalize-FIRST then clear (crash-safe; idempotent via status<>'completed').
        await finalize_cb(body_json, total_in, total_out, memo)
        await _clear_resume_state(pool, chapter_translation_id)


async def _submit_next_batch(
    *, ex, llm_client: LLMClient, chapter_translation_id: UUID, rs: dict,
) -> None:
    """Submit the current (batch_idx, attempt) WITHOUT waiting; persist
    provider_job_id + resume_state on `ex` (a Pool for the initial submit, or the
    FOR UPDATE connection during a resume), then return."""
    from .session_translator import _TRANSLATION_MAX_OUTPUT_TOKENS

    msg = rs["msg"]
    batch = rs["batches"][rs["batch_idx"]]
    messages = build_batch_messages(rs)
    out_max = min(
        _TRANSLATION_MAX_OUTPUT_TOKENS,
        max(2048, rs["context_window"] - batch["token_estimate"] - 2048),
    )
    submit = await llm_client.submit_job(
        user_id=msg["user_id"], operation="translation",
        model_source=msg["model_source"], model_ref=str(msg["model_ref"]),
        input={
            "messages": messages,
            "max_tokens": out_max,
            "reasoning_effort": "none",
            "chat_template_kwargs": {"enable_thinking": False},
        },
        chunking=None,
        job_meta={
            "chapter_translation_id": str(chapter_translation_id),
            "batch_idx": rs["batch_idx"], "attempt": rs["attempt"],
            "decoupled_kind": "translate_block",
        },
    )
    await _persist_inflight(ex, chapter_translation_id, submit.job_id, rs)


# ── DB helpers (thin) ─────────────────────────────────────────────────────────

async def _record_glossary_usage(pool, ct_id: UUID, used_entity_ids) -> None:
    from .session_translator import _record_glossary_usage as _impl
    await _impl(pool, ct_id, used_entity_ids)


async def _persist_inflight(ex, ct_id: UUID, provider_job_id, rs: dict) -> None:
    # ex is a Pool (initial submit) OR an asyncpg Connection (the resume race-guard
    # persists the advance UNDER the FOR UPDATE lock so a racing resume sees it).
    # updated_at bumped so the Wave-2a resume sweeper's idle-detection reflects real progress.
    await ex.execute(
        """UPDATE chapter_translations
           SET provider_job_id=$2, pipeline_stage='translate', resume_state=$3, updated_at=now()
           WHERE id=$1""",
        ct_id, UUID(str(provider_job_id)), json.dumps(rs),
    )


async def _load_resume_state(pool, ct_id: UUID) -> dict | None:
    row = await pool.fetchrow("SELECT resume_state FROM chapter_translations WHERE id=$1", ct_id)
    if not row or row["resume_state"] is None:
        return None
    rs = row["resume_state"]
    return rs if isinstance(rs, dict) else json.loads(rs)


async def _clear_resume_state(pool, ct_id: UUID) -> None:
    await pool.execute(
        "UPDATE chapter_translations SET resume_state=NULL, provider_job_id=NULL, pipeline_stage='done' WHERE id=$1",
        ct_id,
    )


async def _fail(pool, ct_id: UUID, reason: str) -> None:
    await pool.execute(
        "UPDATE chapter_translations SET status='failed', error_message=$2, resume_state=NULL, provider_job_id=NULL WHERE id=$1",
        ct_id, reason[:500],
    )
