"""V3 orchestrator — M0 scaffold + M1 (rule-tier/correct/romanization) + M2 (LLM verify + loop) + M3 (semantic batching).

``translate_chapter_blocks_v3`` delegates the translation to V2 (with the M1c
romanization nudge and the M3/G5 dialogue/scene-aware batch grouping), then runs
the QA loop:

  rule-tier verify (+ optional LLM Tier-2)  →  re-translate HIGH-severity blocks
  (keep-if-improved)  →  re-verify  →  repeat up to max_qa_rounds.

Gating (`qa_depth`):
  - rule_only : deterministic rule-tier only (M1 behavior).
  - standard  : rule-tier + ONE LLM verify pass; single correction round (default).
  - thorough  : rule-tier + LLM each round; loop up to max_qa_rounds.

Conservative (§12.2): LLM-only issues are capped at advisory severity, so an LLM
flag never alone reaches the HIGH set that triggers a destructive re-translate;
the keep-if-improved check stays **deterministic** (rule-tier high count).
See docs/specs/2026-06-06-translation-pipeline-v3-multi-agent.md.
"""
from __future__ import annotations

import logging
from uuid import UUID

from ...metrics import record_stage

log = logging.getLogger(__name__)

# Hard ceiling on the verify→correct loop, independent of the configured
# max_qa_rounds (review-impl MED-1) — a misconfigured large value must not run
# unbounded LLM calls.
_MAX_QA_ROUNDS = 5


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
    from ..session_translator import translate_chapter_blocks
    from ..block_classifier import classify_block, extract_translatable_text
    from .romanization import romanization_instruction
    from .semantic_chunker import tag_groups
    from .knowledge_context import build_context_brief

    # M4b/G4 — pronoun/honorific brief from glossary bios + knowledge relations,
    # computed ONCE per chapter and fed to BOTH the Translator and the Verifier
    # (§12.2 #4). Best-effort: a failure here must not fail the translation.
    try:
        chapter_src = "\n".join(
            extract_translatable_text(b) for b in blocks
            if classify_block(b) != "passthrough"
        )
        knowledge_brief = await build_context_brief(
            msg.get("book_id", ""), msg.get("user_id", ""), chapter_src,
        )
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("v3 knowledge brief failed (non-fatal): %s", exc)
        knowledge_brief = ""

    # M4c — opportunistic prev-chapter memo (§12.1): used when chapter N-1's memo
    # already exists; never forces ordering. V3-only (V2 ignores msg["prev_memo"]).
    from .chapter_memo import build_prev_memo_block
    prev_memo_block = build_prev_memo_block(msg.get("prev_memo"))

    extra = romanization_instruction(source_lang, msg.get("target_language", ""))
    for _seg in (knowledge_brief, prev_memo_block):
        if _seg:
            extra = (extra + "\n\n" + _seg).strip()

    result = await translate_chapter_blocks(
        blocks, source_lang, msg, pool, chapter_translation_id,
        llm_client=llm_client, context_window=context_window,
        extra_system=extra,
        group_ids=tag_groups(blocks),  # M3/G5 — dialogue/scene-aware batching (V3 only)
    )
    # Non-fatal — verification/correction must never fail a translation that
    # already succeeded. Corrections mutate result[0] in place.
    try:
        await _verify_correct_persist(
            blocks, result[0], source_lang, msg, pool, chapter_translation_id,
            llm_client=llm_client, knowledge_brief=knowledge_brief,
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


def _verifier_model(msg: dict) -> tuple[str, str]:
    """(source, ref) for the verifier — a nullable verifier model falls back to the translator."""
    return (
        msg.get("verifier_model_source") or msg["model_source"],
        msg.get("verifier_model_ref") or msg["model_ref"],
    )


async def _verify(source_texts, draft_texts, cmap, target, source_lang,
                  use_llm, verifier_model, msg, llm_client, knowledge_brief=""):
    """Rule-tier + (optional) LLM Tier-2. LLM issues are capped at 'med' so an
    LLM-only flag never reaches the HIGH set that triggers re-translate (§12.2).
    The M4b knowledge brief (relations/bios) is fed to the LLM verifier too."""
    from .verifier import verify_rules
    report = verify_rules(source_texts, draft_texts, cmap, target)
    if use_llm:
        from .llm_verifier import llm_verify
        llm_issues = await llm_verify(
            source_texts, draft_texts, source_lang, target, verifier_model, msg,
            llm_client=llm_client, knowledge_brief=knowledge_brief,
        )
        for issue in llm_issues:
            if issue.severity == "high":
                issue.severity = "med"  # conservative gate
            report.issues.append(issue)
    return report


async def _verify_correct_persist(blocks, result_blocks, source_lang, msg, pool,
                                  chapter_translation_id, *, llm_client,
                                  knowledge_brief: str = "") -> None:
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
    # D-TRANSL-M1D trust ladder: the verifier hard-fails (HIGH wrong_name →
    # re-translate) only on canon (verified) glossary translations. The corrector
    # still receives the FULL gctx.prompt_block, so machine/draft names remain
    # soft hints the LLM may use — they just can't force churn.
    cmap = gctx.verified_map

    qa_depth = msg.get("qa_depth", "standard")
    use_llm = qa_depth != "rule_only"
    try:
        configured_rounds = int(msg.get("max_qa_rounds", 2))
    except (TypeError, ValueError):
        configured_rounds = 2
    # Cap regardless of config (review-impl MED-1).
    max_rounds = min(_MAX_QA_ROUNDS, max(1, configured_rounds)) if qa_depth == "thorough" else 1
    verifier_model = _verifier_model(msg)

    # Clean slate (review-impl MED-2): a worker retry re-runs with the SAME ct_id;
    # clear all prior issue rows so a shorter re-run can't leave stale higher-round rows.
    await _clear_issues(pool, chapter_translation_id)
    report = await _verify(source_texts, draft_texts, cmap, target, source_lang,
                           use_llm, verifier_model, msg, llm_client, knowledge_brief)
    await _persist_issues(pool, chapter_translation_id, report, 0)

    rounds_used = 0
    while report.block_indices_with_high() and rounds_used < max_rounds:
        rounds_used += 1
        flagged = report.block_indices_with_high()
        corrected = await correct_high_severity_blocks(
            flagged, source_texts, draft_texts, report,
            source_lang, target, msg, gctx.prompt_block, llm_client=llm_client,
        )
        for idx, text in corrected.items():
            # keep-if-improved stays DETERMINISTIC (rule-tier high count) — the
            # LLM's non-determinism must not drive the accept/reject decision.
            orig_high = sum(1 for i in report.issues
                            if i.block_index == idx and i.severity == "high")
            new_high = len(verify_rules({idx: source_texts[idx]}, {idx: text}, cmap, target).high)
            if new_high < orig_high:
                draft_texts[idx] = text
                result_blocks[idx] = rebuild_block(blocks[idx], text)
        report = await _verify(source_texts, draft_texts, cmap, target, source_lang,
                               use_llm, verifier_model, msg, llm_client, knowledge_brief)
        await _persist_issues(pool, chapter_translation_id, report, rounds_used)

    await _update_rollup(pool, chapter_translation_id, report, rounds_used)
    record_stage(
        "translation.verify", pipeline="v3", ct=str(chapter_translation_id),
        qa_depth=qa_depth, rounds=rounds_used,
        high_final=len(report.high), issues_final=len(report.issues),
        score=report.quality_score(),
    )


async def _clear_issues(pool, chapter_translation_id) -> None:
    """Remove ALL prior issue rows for this chapter_translation (re-run clean slate)."""
    async with pool.acquire() as db:
        await db.execute(
            "DELETE FROM translation_quality_issues WHERE chapter_translation_id=$1",
            chapter_translation_id,
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
