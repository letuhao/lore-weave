"""LLM re-arch Phase 2b-T3b cold-start — decoupled 2-pass cold-start (D-V3-DECOUPLE-COLDSTART-2PASS).

The synchronous `v3/orchestrator._maybe_two_pass_cold_start` runs, for a glossary-less
book in `cold_start_mode='two_pass'`: pass-1 block translate → bilingual name-pair
extraction (1 LLM call) → seed the glossary + RE-TRANSLATE (pass 2) with the harvested
names enforced. This module runs that as decoupled stages chained after the decoupled
pass-1 block translate (mode='v3_coldstart'):

    block(pass-1)  →  [v3_coldstart] namepair extract  →  pairs?
                                                            ├─ no  → v3_verify (from pass-1)
                                                            └─ yes → writeback + block(pass-2) → v3_verify

The glossary-exists decision is made at START (`orchestrator.decoupled_v3_block_start`) —
it's book-level, not pass-1-dependent — so a book WITH a glossary never enters this path
(it takes the normal post_block='v3_verify'). Here we only handle the genuine cold start.

Race-safety mirrors the block engine: the namepair submit happens UNDER the block lock
(advances provider_job_id); the pass-2 start runs OUTSIDE the resume lock (it re-fetches
the glossary over HTTP) but itself advances provider_job_id, so once pass-2 is in flight a
redelivered namepair terminal finds the advanced id and skips. The narrow crash window
(parse→pass-2-start) is backstopped by the Wave-2a sweeper, same class as the rest.
"""
from __future__ import annotations

import logging
from uuid import UUID

from . import decoupled_v3_verify as v3v

log = logging.getLogger(__name__)

_COLD_START_EXTRACT_CHARS = 8000  # mirror orchestrator._COLD_START_EXTRACT_CHARS

# resume_state keys carried from the block_rs so a no-pairs hand-off to v3_verify works
# (v3_verify._seed_v3 reads exactly these — incl. `translated_texts`, which
# memo_from_translated needs at the finalize): the coldstart rs is a SUPERSET of a block_rs.
_BLOCK_RS_KEYS = (
    "blocks", "msg", "source_lang", "target_code", "glossary_prompt_block",
    "total_input", "total_output", "chapter_text", "translated_texts", "v3",
)


def _join_translatable(blocks: list[dict]) -> str:
    from ..block_classifier import classify_block, extract_translatable_text
    return "\n".join(
        extract_translatable_text(b) for b in blocks
        if classify_block(b) != "passthrough"
    )


def _seed_coldstart(block_rs: dict, result_blocks: list[dict],
                    src_text: str, translated_text: str) -> dict:
    rs = {k: block_rs.get(k) for k in _BLOCK_RS_KEYS}
    rs.update(
        mode="v3_coldstart", stage="namepair",
        pass1_result_blocks=result_blocks,
        src_text=src_text, translated_text=translated_text,
        context_window=block_rs.get("context_window", 8192),
        base_extra=block_rs.get("extra_system", ""),
        book_id=block_rs["msg"].get("book_id", ""),
    )
    return rs


async def _persist_coldstart(ex, ct_id: UUID, provider_job_id, rs: dict) -> None:
    import json
    await ex.execute(
        """UPDATE chapter_translations
             SET provider_job_id=$2, pipeline_stage='v3_coldstart', resume_state=$3, updated_at=now()
           WHERE id=$1""",
        ct_id, UUID(str(provider_job_id)), json.dumps(rs),
    )


async def transition_from_block(conn, llm_client, ct_id: UUID, block_rs: dict,
                                result_blocks: list[dict]):
    """Called UNDER the block lock when a v3 cold-start chapter's pass-1 block translate
    completes (`post_block=='v3_coldstart'`). Submits the bilingual name-pair extraction +
    persists the v3_coldstart state (advancing provider_job_id). Returns None (in flight).
    Empty source/translation (nothing to harvest) ⇒ hand straight to v3_verify."""
    src_text = _join_translatable(block_rs["blocks"])[:_COLD_START_EXTRACT_CHARS]
    translated_text = _join_translatable(result_blocks)[:_COLD_START_EXTRACT_CHARS]
    if not src_text or not translated_text:
        return await v3v.transition_from_block(conn, llm_client, ct_id, block_rs, result_blocks)

    from .bilingual_extractor import build_namepair_submit_kwargs
    rs = _seed_coldstart(block_rs, result_blocks, src_text, translated_text)
    msg = block_rs["msg"]
    submit = await llm_client.submit_job(
        user_id=msg["user_id"],
        **build_namepair_submit_kwargs(
            src_text, translated_text, block_rs["source_lang"], block_rs["target_code"],
            (msg["model_source"], msg["model_ref"]),
        ),
    )
    await _persist_coldstart(conn, ct_id, submit.job_id, rs)
    return None


async def resume(*, pool, llm_client, job, chapter_translation_id: UUID, finalize_cb) -> None:
    """Consumer entry for the v3_coldstart namepair terminal. Parse harvested pairs →
    no pairs: hand to v3_verify (from pass-1); pairs: start the pass-2 re-translate
    (OUTSIDE the lock — it re-fetches the glossary). FOR UPDATE race-guard like the rest."""
    import json
    from .bilingual_extractor import parse_namepair_job

    job_uuid = UUID(str(job.job_id))
    pairs = None
    rs_for_pass2 = None
    finalize_payload = None
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT resume_state, provider_job_id FROM chapter_translations WHERE id=$1 FOR UPDATE",
                chapter_translation_id,
            )
            if row is None or row["resume_state"] is None:
                return
            if row["provider_job_id"] != job_uuid:
                return  # already folded + advanced by a concurrent resume
            rs = row["resume_state"]
            rs = rs if isinstance(rs, dict) else json.loads(rs)
            if rs.get("mode") != "v3_coldstart":
                return

            parsed = parse_namepair_job(job)
            if not parsed:
                # No recurring names harvested → skip pass 2, verify the pass-1 result.
                # transition submits the first verify UNDER this lock (advances
                # provider_job_id) or returns a finalize payload (rule_only + no HIGH).
                finalize_payload = await v3v.transition_from_block(
                    conn, llm_client, chapter_translation_id, rs, rs["pass1_result_blocks"])
            else:
                pairs = parsed
                rs_for_pass2 = rs

    # ── outside the FOR UPDATE lock ──
    if finalize_payload is not None:
        body_json, total_in, total_out, memo = finalize_payload
        await finalize_cb(body_json, total_in, total_out, memo)
        from ..decoupled_block_translate import _clear_resume_state
        await _clear_resume_state(pool, chapter_translation_id)
    elif pairs:
        await _start_pass2(pool, llm_client, chapter_translation_id, rs_for_pass2, pairs)


async def _start_pass2(pool, llm_client, ct_id: UUID, rs: dict, pairs) -> None:
    """Seed the glossary with the harvested names (best-effort, for future chapters +
    human review) + start the pass-2 decoupled block translate with the names enforced
    in the prompt (post_block='v3_verify' → the verify/correct loop runs on pass 2). The
    submit advances provider_job_id, so a redelivered namepair terminal then skips."""
    from ..decoupled_block_translate import start_chapter_blocks
    from ..glossary_client import writeback_name_pairs
    from .bilingual_extractor import build_namepair_block

    try:
        await writeback_name_pairs(rs["book_id"], rs["source_lang"], rs["target_code"], pairs)
    except Exception as exc:  # noqa: BLE001 — seeding is best-effort; pass 2 still runs
        log.warning("v3 cold-start: glossary writeback failed (non-fatal) ct=%s: %s", ct_id, exc)

    names_block = build_namepair_block(pairs)
    base_extra = rs.get("base_extra", "")
    extra2 = (base_extra + "\n\n" + names_block).strip() if names_block else base_extra
    # Carry the V3 config forward (start_chapter_blocks recomputes cmap from the fresh
    # glossary; post_block='v3_verify' so pass 2 chains into the verify/correct loop).
    v3cfg = {k: v for k, v in (rs.get("v3") or {}).items() if k != "cmap"}
    v3cfg["post_block"] = "v3_verify"
    log.info("v3 cold-start: re-translating ct=%s with %d harvested names (pass 2)",
             ct_id, len(pairs))
    await start_chapter_blocks(
        pool=pool, llm_client=llm_client, chapter_translation_id=ct_id,
        blocks=rs["blocks"], source_lang=rs["source_lang"],
        msg={**rs["msg"], "extra_system": extra2},
        context_window=rs.get("context_window", 8192),
        chapter_text=rs.get("chapter_text", ""), v3=v3cfg,
        # Token parity: the chapter total = pass-1 + pass-2 (matches sync two-pass).
        seed_input=rs.get("total_input", 0), seed_output=rs.get("total_output", 0),
    )
