"""D-WIKI-M8-EVAL-PLUS — on-demand wiki groundedness judge endpoint (Phase 1).

POST /internal/learning/wiki/judge — driven by knowledge's `run_wiki_eval --judge`
(the human-controlled audit plan). The caller provides each AI article's text + the
source snippets it cited; this judges groundedness via the provider-registry gateway
and persists a `wiki_llm_judge_groundedness` quality_score. Inert (scored=0) unless a
judge model is configured (`wiki_llm_judge_enabled` + a model) OR supplied in the
request (an explicit human opt-in even with the global flag off).

Internal-token auth (service-to-service): there is no per-user JWT here — each article's
owner travels in the payload so a multi-tenant batch bills each judge to its owner.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.deps import get_db

logger = logging.getLogger(__name__)


def _uuid_or_none(value: Any) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


async def require_internal_token(x_internal_token: str = Header(default="")) -> None:
    if not settings.internal_service_token or x_internal_token != settings.internal_service_token:
        raise HTTPException(status_code=401, detail="invalid internal token")


router = APIRouter(
    prefix="/internal/learning/wiki",
    tags=["learning-wiki-judge"],
    dependencies=[Depends(require_internal_token)],
)


class WikiJudgeArticle(BaseModel):
    article_id: str
    book_id: str | None = None
    user_id: str | None = None  # the content owner (bills the BYOK judge + attributes the score)
    article_text: str
    sources: list[str] = Field(default_factory=list)


class WikiJudgeRequest(BaseModel):
    run_id: str | None = None       # one audit run; repeated runs accrue a trend
    judge_model: str | None = None  # explicit model = opt-in even with the global flag off
    model_source: str | None = None
    articles: list[WikiJudgeArticle] = Field(default_factory=list)


class WikiJudgeScore(BaseModel):
    article_id: str
    score: float
    reason: str


class WikiJudgeResponse(BaseModel):
    enabled: bool
    run_id: str
    scored: int
    scores: list[WikiJudgeScore]


@router.post("/judge", response_model=WikiJudgeResponse)
async def judge_wiki_articles(
    req: WikiJudgeRequest, pool: asyncpg.Pool = Depends(get_db),
) -> WikiJudgeResponse:
    # Resolve the judge model: an explicit request model opts in even with the global
    # flag off (the human audit plan); else the configured model only when enabled.
    judge_model = req.judge_model or (
        settings.wiki_llm_judge_model_ref if settings.wiki_llm_judge_enabled else ""
    )
    model_source = req.model_source or settings.wiki_llm_judge_model_source
    run_id = req.run_id or uuid.uuid4().hex
    if not judge_model:
        return WikiJudgeResponse(enabled=False, run_id=run_id, scored=0, scores=[])

    from app.clients.llm_client import build_judge_client
    from app.db.online_wiki_judge import persist_wiki_judge, run_wiki_judge

    client = build_judge_client(
        base_url=settings.provider_registry_internal_url,
        internal_token=settings.internal_service_token,
    )
    scores: list[WikiJudgeScore] = []
    for art in req.articles:
        owner = _uuid_or_none(art.user_id) or _uuid_or_none(settings.wiki_llm_judge_user_id)
        if owner is None:
            continue  # no owner to attribute/bill → skip (don't spend a judge call)
        try:
            verdict = await run_wiki_judge(
                client,
                article_text=art.article_text,
                sources=art.sources,
                judge_model=judge_model,
                model_source=model_source,
                user_id=str(owner),
            )
        except Exception:  # noqa: BLE001 — the judge is best-effort; one miss isn't fatal
            logger.warning("wiki judge failed for %s (non-fatal)", art.article_id, exc_info=True)
            continue
        if verdict is None:
            continue
        await persist_wiki_judge(
            pool,
            article_id=art.article_id,
            user_id=owner,
            book_id=_uuid_or_none(art.book_id),
            verdict=verdict,
            judge_model=judge_model,
            run_id=run_id,
        )
        scores.append(
            WikiJudgeScore(article_id=art.article_id, score=verdict.score, reason=verdict.reason)
        )
    return WikiJudgeResponse(enabled=True, run_id=run_id, scored=len(scores), scores=scores)
