"""M7d-2 — online translation-fidelity judge (Channel 3).

When a sampled `translation.quality` event carries the source + translated text
(the M7d-3 worker feed, opt-in) and a judge model is configured, the
translation.quality handler judges fidelity via the provider-registry gateway,
reusing the shared ``loreweave_eval.llm_judge.judge_translation_fidelity`` (the
same JudgeLLMClient seam as the extraction judge). It scores a single [0,1]
fidelity — no gold needed (production chapters have none).
"""

from __future__ import annotations

import json
from uuid import UUID

import asyncpg

from loreweave_eval._client import JudgeLLMClient
from loreweave_eval.llm_judge import FidelityVerdict, judge_translation_fidelity

from app.db.eval_repo import persist_consumed_score

_METRIC = "translation_judge_fidelity"


async def run_translation_judge(
    client: JudgeLLMClient,
    *,
    source_text: str,
    translated_text: str,
    judge_model: str,
    model_source: str,
    user_id: str,
) -> FidelityVerdict | None:
    """One fidelity judgment of a translation vs its source. None on any
    non-usable outcome (best-effort — a single judge hiccup is droppable)."""
    return await judge_translation_fidelity(
        client,
        judge_model=judge_model,
        user_id=user_id,
        model_source=model_source,
        source_text=source_text,
        translated_text=translated_text,
    )


async def persist_translation_judge(
    pool: asyncpg.Pool,
    *,
    ct_id: str,
    user_id: UUID,
    book_id: UUID | None,
    verdict: FidelityVerdict,
    judge_model: str,
    origin_event_id: str,
) -> bool:
    """Persist a fidelity verdict as a `source='auto'` quality_scores row keyed to
    the chapter translation. The dedup key is ``judge:<outbox_id>`` so it does NOT
    collide with M7a's ``translation_quality_score`` row from the SAME
    translation.quality event (which dedups on the bare ``<outbox_id>``). The
    rationale + judge model + panel-safety note ride in the comment
    (``panel_safe=False`` — a single online judge, not a disjoint panel)."""
    detail = json.dumps(
        {"reason": verdict.reason, "judge_model": judge_model, "panel_safe": False},
        ensure_ascii=False,
    )
    return await persist_consumed_score(
        pool,
        target_kind="translation",
        target_id=ct_id,
        user_id=user_id,
        book_id=book_id,
        metric_name=_METRIC,
        value_num=verdict.score,
        source="auto",
        origin_service="translation",
        origin_event_id=f"judge:{origin_event_id}",
        comment=detail,
        judge_model=judge_model,
    )
