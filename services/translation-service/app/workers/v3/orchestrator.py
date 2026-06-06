"""V3 orchestrator — M0 skeleton + M1a rule-tier + M1b targeted re-translate.

``translate_chapter_blocks_v3`` delegates the translation to V2, runs the
deterministic Verifier **rule-tier** (M1a), and re-translates HIGH-severity blocks
once (M1b — rule-triggered, single pass; the LLM-verifier loop is M2). Corrections
are spliced back into the returned blocks so the worker persists the fixed output.
See docs/specs/2026-06-06-translation-pipeline-v3-multi-agent.md.

V2 imports are lazy (inside each call) to stay patchable in tests and avoid an
import cycle with session_translator.
"""
from __future__ import annotations

import logging
from uuid import UUID

from ...metrics import record_stage

log = logging.getLogger(__name__)


async def translate_chapter_blocks_v3(
    blocks: list[dict],
    source_lang: str,
    msg: dict,
    pool,
    chapter_translation_id: UUID,
    *,
    llm_client,
    context_window: int = 8192,
):
    """Translate via V2, then verify (M1a) + targeted re-translate (M1b)."""
    from ..session_translator import translate_chapter_blocks
    from .romanization import romanization_instruction
    result = await translate_chapter_blocks(
        blocks, source_lang, msg, pool, chapter_translation_id,
        llm_client=llm_client, context_window=context_window,
        extra_system=romanization_instruction(source_lang, msg.get("target_language", "")),
    )
    # Non-fatal — verification/correction must never fail a translation that
    # already succeeded. Corrections mutate result[0] in place (the worker then
    # persists the corrected blocks).
    try:
        await _verify_correct_persist(
            blocks, result[0], source_lang, msg, pool, chapter_translation_id,
            llm_client=llm_client,
        )
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("v3 verify/correct failed (non-fatal) ct=%s: %s",
                    chapter_translation_id, exc)
    return result


async def translate_chapter_v3(
    chapter_text: str,
    source_lang: str,
    msg: dict,
    pool,
    chapter_translation_id: UUID,
    *,
    llm_client,
    context_window: int = 8192,
):
    """Text (legacy) pipeline — verifies the block pipeline only; delegate as-is."""
    from ..session_translator import translate_chapter
    return await translate_chapter(
        chapter_text, source_lang, msg, pool, chapter_translation_id,
        llm_client=llm_client, context_window=context_window,
    )


# ── M1a verify + M1b correct + persist ────────────────────────────────────────

async def _verify_correct_persist(
    blocks, result_blocks, source_lang, msg, pool, chapter_translation_id, *, llm_client,
) -> None:
    if chapter_translation_id is None:
        return
    from ..block_classifier import classify_block, extract_translatable_text, rebuild_block
    from ..glossary_client import fetch_translation_glossary, build_glossary_context
    from .verifier import verify_rules
    from .corrector import correct_high_severity_blocks

    target = msg.get("target_language", "")

    source_texts: dict[int, str] = {}
    draft_texts: dict[int, str] = {}
    for i, (sb, tb) in enumerate(zip(blocks, result_blocks)):
        if classify_block(sb) == "passthrough":
            continue
        s = extract_translatable_text(sb)
        if not s:
            continue
        source_texts[i] = s
        draft_texts[i] = extract_translatable_text(tb)
    if not draft_texts:
        return

    raw = await fetch_translation_glossary(
        book_id=msg.get("book_id", ""), target_language=target,
        chapter_id=msg.get("chapter_id", ""),
    )
    gctx = build_glossary_context(raw, "\n".join(source_texts.values()), target)
    cmap = gctx.correction_map

    # M1a: detect + persist round 0.
    report0 = verify_rules(source_texts, draft_texts, cmap, target)
    await _persist_issues(pool, chapter_translation_id, report0, 0)

    final = report0
    rounds_used = 0
    flagged = report0.block_indices_with_high()
    if flagged:
        # M1b: re-translate the high-severity blocks once, splice, re-verify.
        rounds_used = 1
        corrected = await correct_high_severity_blocks(
            flagged, source_texts, draft_texts, report0,
            source_lang, target, msg, gctx.prompt_block, llm_client=llm_client,
        )
        for idx, text in corrected.items():
            # keep-if-improved (review-impl MED-1): only accept a correction that
            # REDUCES this block's high-severity count — never persist a worse draft.
            orig_high = sum(1 for i in report0.issues
                            if i.block_index == idx and i.severity == "high")
            new_high = len(verify_rules({idx: source_texts[idx]}, {idx: text}, cmap, target).high)
            if new_high < orig_high:
                draft_texts[idx] = text
                result_blocks[idx] = rebuild_block(blocks[idx], text)  # worker persists this
        final = verify_rules(source_texts, draft_texts, cmap, target)
        await _persist_issues(pool, chapter_translation_id, final, 1)

    await _update_rollup(pool, chapter_translation_id, final, rounds_used)
    record_stage(
        "translation.verify", pipeline="v3", ct=str(chapter_translation_id),
        issues0=len(report0.issues), high0=len(report0.high),
        high_final=len(final.high), rounds=rounds_used, score=final.quality_score(),
    )


async def _persist_issues(pool, chapter_translation_id, report, round_) -> None:
    """Replace the given round's issue rows (idempotent re-run)."""
    async with pool.acquire() as db:
        async with db.transaction():
            await db.execute(
                "DELETE FROM translation_quality_issues "
                "WHERE chapter_translation_id=$1 AND round=$2",
                chapter_translation_id, round_,
            )
            for it in report.issues:
                await db.execute(
                    """INSERT INTO translation_quality_issues
                         (chapter_translation_id, block_index, round, issue_type,
                          severity, detail, expected, detected_by)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
                    chapter_translation_id, it.block_index, round_, it.type,
                    it.severity, it.detail, it.expected, it.detected_by,
                )


async def _update_rollup(pool, chapter_translation_id, report, rounds_used) -> None:
    async with pool.acquire() as db:
        await db.execute(
            """UPDATE chapter_translations
                 SET quality_score=$1, unresolved_high_count=$2, qa_rounds_used=$3
               WHERE id=$4""",
            report.quality_score(), len(report.high), rounds_used, chapter_translation_id,
        )
