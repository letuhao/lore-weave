"""P2 — per-leaf extraction processor.

Spec: docs/specs/2026-05-23-p2-parallel-map-checkpoint.md §D3 + §D3a + §D4 + §D8.

One leaf = (scene × op). Lifecycle:
  1. Check cache (extraction_leaves_repo.fetch_cached) -> if hit, return
     immediately (NO LLM call, NO billing reserve).
  2. Claim pending row atomically (insert ON CONFLICT DO NOTHING).
  3. Acquire LLM semaphore (bounds intra-chapter concurrency).
  4. Call extractor (LLM via gateway, with parent_job_id for billing
     accumulation per D3a).
  5. Postprocess raw -> candidates.
  6. Persist: candidates_jsonb in extraction_leaves, raw in
     extraction_leaves_raw (when project opted-in via save_raw_extraction).
  7. On any failure: repo.mark_failed(error_message) + increment retried_n.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from uuid import UUID

from app.clients.glossary_client import (
    GlossaryAnchorMalformed,
    GlossaryAnchorUnavailable,
)
from app.db.repositories.extraction_leaves import (
    ExtractionLeaf,
    ExtractionLeavesRepo,
)

logger = logging.getLogger(__name__)

# Retry budget per leaf (D9). Beyond this, the leaf stays 'failed' and
# P3 reduce ignores it.
RETRY_BUDGET = 2


@dataclass
class LeafTaskInput:
    """Per-leaf task payload."""
    book_id: UUID
    chapter_id: UUID  # WS-0.1: the invalidation key; NOT interchangeable with scene_id
    scene_id: UUID
    leaf_path: str
    op: str  # one of: entity, relation, event, fact
    task_id: str
    normalized_leaf_text: str
    parse_version: int
    extractor_version: str
    model_ref: str
    glossary_anchor: list[dict[str, Any]]  # known-entities for this chapter
    parent_job_id: UUID  # D3a: billing accumulator
    save_raw: bool  # D6: opt-in raw response persistence


# Extractor protocol — signature the leaf processor expects to call.
# Concrete impl wraps loreweave_extraction.extract_{entities,relations,events,facts}.
ExtractorFn = Callable[..., Awaitable[tuple[list[dict], dict, dict]]]
# Returns: (candidates, raw_response, raw_token_usage)


class LeafProcessor:
    """Per-leaf orchestration: cache check -> claim -> LLM -> persist."""

    def __init__(
        self,
        repo: ExtractionLeavesRepo,
        extractors: dict[str, ExtractorFn],
        semaphore: asyncio.Semaphore,
        *,
        retry_budget: int = RETRY_BUDGET,
    ):
        """
        extractors: map op name -> async fn that runs the LLM extraction.
                    Expected signature:
                      async def(leaf_text, glossary_anchor, model_ref,
                                parent_job_id)
                            -> (candidates: list[dict], raw_response: dict,
                                raw_token_usage: dict)
        """
        self._repo = repo
        self._extractors = extractors
        self._semaphore = semaphore
        self._retry_budget = retry_budget

    async def process(self, task: LeafTaskInput) -> list[dict]:
        """Process one leaf. Returns its candidates list (cached or fresh).

        Raises only on permanent failure after retry budget exhausted OR
        on GlossaryAnchorMalformed (no retry). All other failures are
        recorded in extraction_leaves.error_message and retried_n.
        """
        # (1) Cache check — no semaphore, no billing, no LLM.
        cached = await self._repo.fetch_cached(task.task_id)
        if cached is not None:
            logger.debug(
                "leaf_processor cache HIT task_id=%s op=%s",
                task.task_id[:12], task.op,
            )
            return cached.candidates_jsonb or []

        # (2) Atomic claim. Race losers proceed to also try (LLM call)
        # but the persist's UPDATE WHERE status='running' will no-op
        # for them — wasted work bounded by # racers (typically 0 or 1).
        await self._repo.claim_pending(
            book_id=task.book_id,
            chapter_id=task.chapter_id,
            scene_id=task.scene_id,
            leaf_path=task.leaf_path,
            op=task.op,
            task_id=task.task_id,
            parse_version=task.parse_version,
            extractor_version=task.extractor_version,
            model_ref=task.model_ref,
        )

        # (3) LLM call gated by semaphore. (4) extractor call. (5) postprocess.
        extractor = self._extractors.get(task.op)
        if extractor is None:
            await self._repo.mark_failed(
                task_id=task.task_id,
                error_message=f"no extractor registered for op={task.op!r}",
            )
            raise ValueError(f"no extractor for op={task.op!r}")

        async with self._semaphore:
            try:
                candidates, raw_response, raw_token_usage = await extractor(
                    leaf_text=task.normalized_leaf_text,
                    glossary_anchor=task.glossary_anchor,
                    model_ref=task.model_ref,
                    parent_job_id=task.parent_job_id,
                )
            except GlossaryAnchorMalformed:
                # Not transient — surface as permanent failure (no retry).
                await self._repo.mark_failed(
                    task_id=task.task_id,
                    error_message="glossary anchor malformed (4xx)",
                )
                raise
            except GlossaryAnchorUnavailable as exc:
                # Transient — retry budget applies.
                retried_n = await self._repo.mark_failed(
                    task_id=task.task_id,
                    error_message=f"glossary unavailable: {exc}",
                )
                if retried_n >= self._retry_budget:
                    logger.warning(
                        "leaf retry budget exhausted task_id=%s op=%s",
                        task.task_id[:12], task.op,
                    )
                raise
            except Exception as exc:  # noqa: BLE001
                # Generic LLM / extraction failure — transient, retry-eligible.
                retried_n = await self._repo.mark_failed(
                    task_id=task.task_id,
                    error_message=f"{type(exc).__name__}: {exc}",
                )
                if retried_n >= self._retry_budget:
                    logger.warning(
                        "leaf retry budget exhausted task_id=%s op=%s",
                        task.task_id[:12], task.op,
                    )
                raise

        # (6) Persist candidates (+ raw if opted-in).
        await self._repo.persist(
            task_id=task.task_id,
            candidates=candidates,
            glossary_anchor_size=len(task.glossary_anchor),
            raw_response=raw_response if task.save_raw else None,
            raw_token_usage=raw_token_usage if task.save_raw else None,
        )
        return candidates


__all__ = ["LeafProcessor", "LeafTaskInput", "RETRY_BUDGET"]
