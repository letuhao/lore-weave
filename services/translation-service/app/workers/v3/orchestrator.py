"""V3 orchestrator — M0 skeleton + M1a deterministic rule-tier.

``translate_chapter_blocks_v3`` delegates the actual translation to V2, then runs
the Verifier **rule-tier** and persists its report (detect + observe). M1b adds
targeted re-translation of high-severity blocks; M2 adds the LLM verifier loop.
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
    """Translate via V2, then run + persist the deterministic rule-tier."""
    from ..session_translator import translate_chapter_blocks
    result = await translate_chapter_blocks(
        blocks, source_lang, msg, pool, chapter_translation_id,
        llm_client=llm_client, context_window=context_window,
    )
    # M1a: detect + persist only (targeted re-translate is M1b). Non-fatal —
    # verification must never fail a translation that already succeeded.
    try:
        await _verify_and_persist(blocks, result[0], msg, pool, chapter_translation_id)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("v3 rule-tier verify failed (non-fatal) ct=%s: %s",
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
    """Text (legacy) pipeline — M1a verifies the block pipeline only; delegate as-is."""
    from ..session_translator import translate_chapter
    return await translate_chapter(
        chapter_text, source_lang, msg, pool, chapter_translation_id,
        llm_client=llm_client, context_window=context_window,
    )


# ── M1a: rule-tier verification + persistence ─────────────────────────────────

async def _verify_and_persist(blocks, result_blocks, msg, pool, chapter_translation_id) -> None:
    if chapter_translation_id is None:
        return
    from ..block_classifier import classify_block, extract_translatable_text
    from ..glossary_client import fetch_translation_glossary, build_glossary_context
    from .verifier import verify_rules

    target = msg.get("target_language", "")

    # Per-block source + draft text, index-aligned (translatable blocks only).
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

    # Glossary correction_map (same scoping as the translator; cold start → {}).
    raw = await fetch_translation_glossary(
        book_id=msg.get("book_id", ""),
        target_language=target,
        chapter_id=msg.get("chapter_id", ""),
    )
    correction_map = build_glossary_context(
        raw, "\n".join(source_texts.values()), target,
    ).correction_map

    report = verify_rules(source_texts, draft_texts, correction_map, target)
    await _persist_issues(pool, chapter_translation_id, report)
    record_stage(
        "translation.verify", pipeline="v3", ct=str(chapter_translation_id),
        issues=len(report.issues), high=len(report.high), score=report.quality_score(),
    )


async def _persist_issues(pool, chapter_translation_id, report) -> None:
    """Replace round-0 issues + refresh the chapter rollup (idempotent re-run)."""
    async with pool.acquire() as db:
        async with db.transaction():
            await db.execute(
                "DELETE FROM translation_quality_issues "
                "WHERE chapter_translation_id=$1 AND round=0",
                chapter_translation_id,
            )
            for it in report.issues:
                await db.execute(
                    """INSERT INTO translation_quality_issues
                         (chapter_translation_id, block_index, round, issue_type,
                          severity, detail, expected, detected_by)
                       VALUES ($1,$2,0,$3,$4,$5,$6,$7)""",
                    chapter_translation_id, it.block_index, it.type, it.severity,
                    it.detail, it.expected, it.detected_by,
                )
            await db.execute(
                """UPDATE chapter_translations
                     SET quality_score=$1, unresolved_high_count=$2, qa_rounds_used=0
                   WHERE id=$3""",
                report.quality_score(), len(report.high), chapter_translation_id,
            )
