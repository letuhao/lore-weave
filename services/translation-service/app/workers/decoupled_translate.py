"""LLM re-arch Phase 2b-T2 — event-driven decouple of the TEXT translate stage.

Replaces the synchronous in-memory `translate_chapter` chunk loop with a
submit→persist→release state machine that resumes on the job's terminal event
(`loreweave:events:llm_job_terminal`), so a worker coroutine is NOT pinned for
the whole chapter and a consumer restart mid-wait doesn't lose the resume.

The running state lives in `chapter_translations.resume_state` (JSONB) — persisted
explicitly rather than reconstructed, because the compaction step is itself an LLM
call whose memo output isn't recoverable from the chunk rows.

This module is split into a PURE state machine (no DB / no SDK — fully unit-tested)
and a thin async shell that does the DB I/O + submit + the consumer's resume.

Behind the `translation_decouple_enabled` flag (default off ⇒ the legacy
session_translator path is unchanged). Block + V3 verify/correct reuse this engine
in follow-ups (2b-T3); this increment proves the engine on the text path.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from ..llm_client import LLMClient
from .chunk_splitter import estimate_tokens, split_chapter
from .session_translator import (
    _build_messages,
    _build_user_content,
    _parse_sdk_response,
)

log = logging.getLogger("translation.decoupled")

# ── PURE state machine ────────────────────────────────────────────────────────
# resume_state (JSONB) schema:
#   chunks:           [str, ...]        the fixed split (so resume is deterministic)
#   chunk_idx:        int               index of the NEXT chunk to translate
#   session_history:  [{role, content}] rolling context since the last compaction
#   compact_memo:     str               the current compacted memo ("" = none)
#   translated_parts: [str, ...]        per-chunk outputs (joined at finalize)
#   total_input:      int
#   total_output:     int
#   awaiting:         "translate" | "compact"   what the in-flight job is
#   source_lang:      str


def new_resume_state(chunks: list[str], source_lang: str) -> dict[str, Any]:
    return {
        "chunks": chunks,
        "chunk_idx": 0,
        "session_history": [],
        "compact_memo": "",
        "translated_parts": [],
        "total_input": 0,
        "total_output": 0,
        "awaiting": "translate",
        "source_lang": source_lang,
    }


def decide_next_action(rs: dict[str, Any], context_window: int) -> tuple:
    """Pure: given the running state, decide the next step.

    Returns one of:
      ("translate", chunk_idx) — submit chunk_idx using the current session
      ("compact",)             — session history exceeds ½ context; compact first
      ("finalize",)            — all chunks translated; aggregate + done

    Stateless by construction: after a translate the history grows → may return
    'compact'; after a compact the history is empty → returns 'translate'. We only
    compact when chunks remain (compacting after the last chunk would be a wasted
    LLM call — the memo would never be used).
    """
    if rs["chunk_idx"] >= len(rs["chunks"]):
        return ("finalize",)
    history_tokens = sum(estimate_tokens(m["content"]) for m in rs["session_history"])
    if history_tokens > context_window // 2:
        return ("compact",)
    return ("translate", rs["chunk_idx"])


def apply_translate_result(
    rs: dict[str, Any], translated: str, in_tok: int, out_tok: int, msg: dict,
) -> dict[str, Any]:
    """Pure: fold a completed chunk translation into the state. Appends the output
    + the user/assistant exchange to the rolling history and advances chunk_idx."""
    idx = rs["chunk_idx"]
    chunk = rs["chunks"][idx]
    total = len(rs["chunks"])
    out = dict(rs)
    out["translated_parts"] = [*rs["translated_parts"], translated]
    out["total_input"] = rs["total_input"] + in_tok
    out["total_output"] = rs["total_output"] + out_tok
    out["session_history"] = [
        *rs["session_history"],
        {"role": "user", "content": _build_user_content(chunk, rs["source_lang"], msg, idx, total)},
        {"role": "assistant", "content": translated},
    ]
    out["chunk_idx"] = idx + 1
    return out


def apply_compact_result(rs: dict[str, Any], new_memo: str) -> dict[str, Any]:
    """Pure: fold a completed compaction — adopt the memo + reset the history."""
    out = dict(rs)
    out["compact_memo"] = new_memo
    out["session_history"] = []
    return out


def build_chunk_messages(rs: dict[str, Any], chunk_idx: int, msg: dict) -> list[dict]:
    """Messages for translating chunk_idx with the current session + memo."""
    return _build_messages(
        rs["chunks"][chunk_idx], rs["source_lang"], msg, chunk_idx, len(rs["chunks"]),
        rs["session_history"], rs["compact_memo"],
    )


def build_compact_messages(rs: dict[str, Any], msg: dict) -> list[dict]:
    """Messages for compacting the current session history into a memo. Mirrors
    session_translator._compact_history's prompt construction."""
    from ..config import (
        DEFAULT_COMPACT_SYSTEM_PROMPT,
        DEFAULT_COMPACT_USER_PROMPT_TPL,
    )
    from .session_translator import _SafeFormatMap

    history_text = "\n\n".join(
        f"[{m['role'].upper()}]\n{m['content']}" for m in rs["session_history"]
    )
    if rs["compact_memo"]:
        history_text = f"[PREVIOUS MEMO]\n{rs['compact_memo']}\n\n[NEW EXCHANGES]\n{history_text}"
    system = msg.get("compact_system_prompt") or DEFAULT_COMPACT_SYSTEM_PROMPT
    user_tpl = msg.get("compact_user_prompt_tpl") or DEFAULT_COMPACT_USER_PROMPT_TPL
    user_msg = user_tpl.format_map(_SafeFormatMap({"history_text": history_text}))
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]


# ── async shell — DB I/O + submit + resume (driven by the consumer) ────────────

async def start_chapter(
    *, pool, llm_client: LLMClient, chapter_translation_id: UUID,
    chapter_text: str, source_lang: str, msg: dict, context_window: int,
) -> None:
    """Seed resume_state + submit the first chunk. Returns immediately (released).
    The full `msg` + `context_window` are stored IN resume_state so the consumer
    (which only sees a job_id) can resume without re-deriving the job config."""
    chunk_size = max(min(int(msg.get("chunk_size_tokens") or 2000), context_window // 4), 100)
    chunks = split_chapter(chapter_text, chunk_size)
    rs = new_resume_state(chunks, source_lang)
    rs["msg"] = msg
    rs["context_window"] = context_window
    # Stored so the consumer (which only sees a job_id) can pass the ORIGINAL text
    # as the quality-feed source_text at finalize — keeps M7d fidelity-judge parity
    # with the synchronous path. Redundant with `chunks` (a split of this) but the
    # split isn't guaranteed byte-lossless, and the storage cost is trivial.
    rs["chapter_text"] = chapter_text
    await _submit_next(pool=pool, llm_client=llm_client,
                       chapter_translation_id=chapter_translation_id, rs=rs)


async def resume(
    *, pool, llm_client: LLMClient, job, chapter_translation_id: UUID, finalize_cb,
) -> None:
    """Consumer entry: a terminal event for this chapter's in-flight job arrived.
    Fold the result into resume_state, then submit the next step or finalize.

    `job` is the SDK Job (status + result). `finalize_cb(translated_body, in, out)`
    is the caller-supplied hook that runs the post-translate pipeline
    (finalize/emit) — kept in the existing flow for this increment. `msg` +
    `context_window` are read from the persisted resume_state (self-contained)."""
    rs = await _load_resume_state(pool, chapter_translation_id)
    if rs is None:
        log.warning("decoupled resume: no resume_state for ct=%s — dropping", chapter_translation_id)
        return
    msg = rs["msg"]
    context_window = rs["context_window"]

    if job.status != "completed":
        # Best-effort for compaction (keep old memo, continue); hard for translate.
        if rs["awaiting"] == "compact":
            log.warning("decoupled: compact job %s non-terminal-ok — keeping memo", job.job_id)
            rs = apply_compact_result(rs, rs["compact_memo"])
        else:
            await _fail(pool, chapter_translation_id, f"translate job {job.job_id} status={job.status}")
            return
    elif rs["awaiting"] == "translate":
        translated, in_tok, out_tok = _parse_sdk_response(job)
        await _record_chunk(pool, chapter_translation_id, rs["chunk_idx"], translated, in_tok, out_tok)
        rs = apply_translate_result(rs, translated, in_tok, out_tok, msg)
    else:  # compact completed
        memo, _, _ = _parse_sdk_response(job)
        rs = apply_compact_result(rs, memo or rs["compact_memo"])

    action = decide_next_action(rs, context_window)
    if action[0] == "finalize":
        body = "\n\n".join(rs["translated_parts"])
        # Finalize-FIRST, then clear — crash-safe under at-least-once delivery.
        # finalize_cb sets status='completed' (idempotent via its status guard);
        # only after it commits do we clear provider_job_id. If we crash between
        # the two, the terminal event redelivers, finds the row still pointing at
        # this job, re-folds from the (pre-fold) persisted resume_state — yielding
        # the SAME body — and finalize_cb's guard absorbs the duplicate. Clearing
        # first would instead lose the row on redelivery → a translated chapter
        # stuck 'running' until the 2h sweeper marks it failed.
        await finalize_cb(body, rs["total_input"], rs["total_output"])
        await _clear_resume_state(pool, chapter_translation_id)
        return
    await _submit_next(pool=pool, llm_client=llm_client,
                       chapter_translation_id=chapter_translation_id, rs=rs)


async def _submit_next(
    *, pool, llm_client: LLMClient, chapter_translation_id: UUID, rs: dict,
) -> None:
    """Submit the next step (translate or compact) WITHOUT waiting; persist the
    in-flight provider_job_id + the updated resume_state, then return. `msg` +
    `context_window` come from rs (self-contained)."""
    msg = rs["msg"]
    context_window = rs["context_window"]
    action = decide_next_action(rs, context_window)
    if action[0] == "compact":
        rs = dict(rs, awaiting="compact")
        messages = build_compact_messages(rs, msg)
        model_source = msg.get("compact_model_source") or msg["model_source"]
        model_ref = msg.get("compact_model_ref") or msg["model_ref"]
        job_meta = {"chapter_translation_id": str(chapter_translation_id), "decoupled_kind": "compact"}
    else:  # translate
        rs = dict(rs, awaiting="translate")
        messages = build_chunk_messages(rs, rs["chunk_idx"], msg)
        model_source = msg["model_source"]
        model_ref = msg["model_ref"]
        job_meta = {"chapter_translation_id": str(chapter_translation_id),
                    "chunk_idx": rs["chunk_idx"], "decoupled_kind": "translate"}

    submit = await llm_client.submit_job(
        user_id=msg["user_id"], operation="translation",
        model_source=model_source, model_ref=str(model_ref),
        input={"messages": messages}, chunking=None, job_meta=job_meta,
    )
    await _persist_inflight(pool, chapter_translation_id, submit.job_id, rs)


# ── DB helpers (thin) ─────────────────────────────────────────────────────────

async def _persist_inflight(pool, ct_id: UUID, provider_job_id, rs: dict) -> None:
    import json
    await pool.execute(
        """UPDATE chapter_translations
           SET provider_job_id=$2, pipeline_stage='translate', resume_state=$3
           WHERE id=$1""",
        ct_id, UUID(str(provider_job_id)), json.dumps(rs),
    )


async def _load_resume_state(pool, ct_id: UUID) -> dict | None:
    import json
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


async def _record_chunk(pool, ct_id: UUID, chunk_idx: int, translated: str, in_tok: int, out_tok: int) -> None:
    await pool.execute(
        """INSERT INTO chapter_translation_chunks
             (chapter_translation_id, chunk_index, chunk_text, translated_text,
              input_tokens, output_tokens, status)
           VALUES ($1,$2,'',$3,$4,$5,'completed')
           ON CONFLICT (chapter_translation_id, chunk_index) DO UPDATE
             SET translated_text=EXCLUDED.translated_text,
                 input_tokens=EXCLUDED.input_tokens,
                 output_tokens=EXCLUDED.output_tokens, status='completed'""",
        ct_id, chunk_idx, translated, in_tok, out_tok,
    )


async def _fail(pool, ct_id: UUID, reason: str) -> None:
    await pool.execute(
        "UPDATE chapter_translations SET status='failed', error_message=$2, resume_state=NULL, provider_job_id=NULL WHERE id=$1",
        ct_id, reason[:500],
    )
