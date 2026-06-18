"""Best-effort client for learning-service's on-demand wiki groundedness judge.

D-WIKI-M8-EVAL-PLUS Phase 2 — after a wiki article generates, the orchestrator (when
sampled) posts the fresh article + its FULL context sources here, and learning judges
groundedness + persists a `wiki_llm_judge_groundedness` quality_score (reusing the
SAME endpoint as the on-demand `run_wiki_eval --judge` audit).

Best-effort by contract: every failure returns silently — an auto-judge must NEVER
block or fail generation. The async client is a lazy process singleton (connection
pool); tests substitute `post_wiki_judge` directly.
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.learning_internal_url.rstrip("/"),
            timeout=httpx.Timeout(60.0),
            headers={"X-Internal-Token": settings.internal_service_token},
        )
    return _client


async def post_wiki_judge(
    *,
    article_id: str,
    book_id: UUID,
    user_id: UUID,
    article_text: str,
    sources: list[str],
    judge_model: str,
    model_source: str,
) -> None:
    """Best-effort POST of one article to the learning groundedness judge. Never raises."""
    try:
        await _http().post(
            "/internal/learning/wiki/judge",
            json={
                "judge_model": judge_model,
                "model_source": model_source,
                "articles": [{
                    "article_id": str(article_id),
                    "book_id": str(book_id),
                    "user_id": str(user_id),
                    "article_text": article_text,
                    "sources": sources,
                }],
            },
        )
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("wiki auto-judge post failed (non-fatal): %s", exc)
