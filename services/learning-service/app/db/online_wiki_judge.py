"""D-WIKI-M8-EVAL-PLUS — wiki-article groundedness judge (Phase 1, on-demand).

Scores how well an AI-generated wiki article's claims are supported by its source
material, via the provider-registry gateway, reusing the shared
``loreweave_eval.llm_judge.judge_wiki_groundedness`` (the same JudgeLLMClient seam as
the translation + extraction judges). A single [0,1] groundedness score, no gold
needed. Persists as a ``source='auto'`` quality_score, keyed per eval run so repeated
audits accrue a trend (idempotent within a run).
"""

from __future__ import annotations

import json
from uuid import UUID

import asyncpg

from loreweave_eval._client import JudgeLLMClient
from loreweave_eval.llm_judge import GroundednessVerdict, judge_wiki_groundedness

from app.db.eval_repo import persist_consumed_score

_METRIC = "wiki_llm_judge_groundedness"


async def run_wiki_judge(
    client: JudgeLLMClient,
    *,
    article_text: str,
    sources: list[str],
    judge_model: str,
    model_source: str,
    user_id: str,
) -> GroundednessVerdict | None:
    """One groundedness judgment of a wiki article vs its sources. None on any
    non-usable outcome (best-effort — a single judge hiccup is droppable)."""
    return await judge_wiki_groundedness(
        client,
        judge_model=judge_model,
        user_id=user_id,
        model_source=model_source,
        article_text=article_text,
        sources=sources,
    )


async def persist_wiki_judge(
    pool: asyncpg.Pool,
    *,
    article_id: str,
    user_id: UUID,
    book_id: UUID | None,
    verdict: GroundednessVerdict,
    judge_model: str,
    run_id: str,
) -> bool:
    """Persist a groundedness verdict as a `source='auto'` quality_scores row keyed to
    the wiki article. The dedup key is ``<run_id>:<article_id>`` so each eval run is a
    distinct judgment (trend), but re-judging an article WITHIN a run is idempotent.
    The rationale + judge model + panel-safety note ride in the comment
    (``panel_safe=False`` — a single online judge, not a disjoint panel)."""
    detail = json.dumps(
        {"reason": verdict.reason, "judge_model": judge_model, "panel_safe": False},
        ensure_ascii=False,
    )
    return await persist_consumed_score(
        pool,
        target_kind="wiki_article",
        target_id=article_id,
        user_id=user_id,
        book_id=book_id,
        metric_name=_METRIC,
        value_num=verdict.score,
        source="auto",
        origin_service="wiki-judge",
        origin_event_id=f"{run_id}:{article_id}",
        comment=detail,
        judge_model=judge_model,
    )
