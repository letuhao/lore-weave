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
    generator_model: str | None = None,
) -> bool:
    """Persist a groundedness verdict as a `source='auto'` quality_scores row keyed to
    the wiki article. The dedup key is ``<run_id>:<article_id>`` so each eval run is a
    distinct judgment (trend), but re-judging an article WITHIN a run is idempotent.
    The rationale + judge model + panel-safety note ride in the comment
    (``panel_safe=False`` — a single online judge, not a disjoint panel).

    D-JUDGE-DISTINCTNESS-UNRECORDED (2026-07-31): `judge_model` was recorded and the model
    that WROTE the article was not, so a score produced by the article's own writer looked
    exactly like one from an independent judge. provider-registry's `critic` role states
    the rule — *"it MUST differ from the session's actor model (else the roleplay partner
    grades its own performance)"* — and `chat-service/app/routers/evaluate.py` is the only
    place in the repo that enforces it.

    Enforcing it here is not yet possible: the caller does not transmit the generator. So
    record the honest three-state answer instead of implying the good one —

        True  — judge and generator are known and differ
        False — they are the SAME model; the article graded itself
        None  — the generator was not supplied, so distinctness is UNVERIFIED

    `None` is the current default for every caller, and that is the point: an unverified
    score must not read as an independent one. A consumer can now filter on it, and the
    fraction of self-graded scores becomes measurable — which is what has to happen before
    a hard refusal can be turned on without failing every default-configured job.
    """
    judge_distinct: bool | None = None
    if generator_model:
        judge_distinct = str(judge_model) != str(generator_model)
    detail = json.dumps(
        {
            "reason": verdict.reason,
            "judge_model": judge_model,
            "generator_model": generator_model,
            "judge_distinct": judge_distinct,
            "panel_safe": False,
        },
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
