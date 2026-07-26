"""P3 — Async summary-job processor (consumes extraction.summarize stream).

Spec: docs/specs/2026-05-23-p3-hierarchical-reduce.md §D3 + §D9 + §M4 + §M5.

Pipeline per message:
  1. Compute summary_input_md5 (joined_child_texts + level + extractor_version + model_ref).
  2. find_cached(level, level_id, embedding_model_uuid, md5) → if hit, no LLM.
  3. D9 defensive check (part/book only): verify expected_children == actual
     summary rows; if not ready, re-enqueue per M4 (XADD with retry_at +
     exponential backoff).
  4. Load child content (chapter: scene leaf_texts; part: chapter summaries;
     book: part summaries).
  5. Call summarize_level extractor → get LevelSummary.
  6. Embed via embedding_client → vector.
  7. Persist via LevelSummariesRepo.upsert_summary (M5: handles UniqueViolation).
  8. Update Neo4j: SET hierarchy node's summary_text + summary_embedding;
     ensure per-(project, model) vector index exists (idempotent).

This module owns the Protocol for the message handler; worker-ai wires
the Redis Stream consumer loop separately.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

from app.db.neo4j_helpers import (
    CypherSession,
    ensure_summary_indexes,
    summary_index_name,
)
from app.clients.book_client import get_book_client
from app.clients.context_length import resolve_context_length
from app.db.repositories.level_summaries import (
    Level,
    LevelSummariesRepo,
    UpsertOutcome,
)
from app.jobs.summary_enqueue import (
    SUMMARY_STREAM_NAME,
    SummarizeMessage,
    SummaryEnqueueFn,
    now_epoch,
)
from loreweave_extraction import get_extractor_version, summarize_level

logger = logging.getLogger(__name__)

__all__ = [
    "SummaryProcessResult",
    "process_summarize_message",
    "RETRY_BUDGET",
    "REENQUEUE_BACKOFF_S",
]

# Retry budget per message (M4); after exhaustion, leaf stays unwritten —
# Mode-3 retrieval gracefully returns no summary for that level.
RETRY_BUDGET = 3

# M4 re-enqueue backoff: 30s/60s/120s exponential.
REENQUEUE_BACKOFF_S = (30, 60, 120)

# D-P3-BOOK-SUMMARY-PERSIST-AUDIT fix. Upper bound on the inline sleep
# used when a message's retry_at_epoch is in the future. Set to the
# longest backoff (120s) so the consumer can absorb the full M4 schedule
# without re-enqueueing. KnowledgeClient.summarize_message_timeout_s
# defaults to 300s so a 120s server-side sleep stays well within the
# HTTP budget. Defensive cap on absurd `retry_at_epoch` values (clock
# skew, manual injection) — never sleep longer than this regardless of
# what the message claims.
MAX_INLINE_RETRY_SLEEP_S = 120


@dataclass
class SummaryProcessResult:
    """Result of processing one summarize message."""
    level: Level
    node_id: str
    cache_hit: bool          # True if summary_input_md5 matched existing row → no LLM
    race_winner: bool        # True if our INSERT won race (M5)
    re_enqueued: bool        # True if D9 defensive check failed → re-enqueued
    skipped_retry_exhausted: bool  # True if retried_n >= RETRY_BUDGET → abandoned
    summary_id: UUID | None  # None when re_enqueued or skipped


# Caller-injected dependencies (testability).
@dataclass
class SummaryProcessorDeps:
    """All side-effecting clients required by process_summarize_message.

    Tests construct with mocks; production wires real clients in
    worker-ai's task setup.
    """
    knowledge_pool: asyncpg.Pool
    neo4j_session: CypherSession
    llm_client: Any                  # LLMClientProtocol from SDK
    embedding_client: Any            # exposes embed(text, model_uuid) -> list[float]
    summary_enqueue: SummaryEnqueueFn  # for M4 re-enqueue


# ── E0-3 Phase 2a-2 — BYOK billing identity for the summary provider calls ──
# Gate on billing_user_id (the identity), never a ref alone (review-impl MED-1).
# The STORED embedding_model_uuid tag (search filter / index / cache key) always
# stays msg.embedding_model_uuid — only the GENERATION refs/user swap to billing.
# The embed adapter's user is bound in the /summarize-message endpoint to the
# SAME billing_bill_user, so the embed model_uuid passed here resolves there.


def _bill_user(msg: "SummarizeMessage") -> str:
    return msg.billing_user_id or msg.user_id


def _bill_llm_ref(msg: "SummarizeMessage") -> str:
    return msg.billing_llm_model if msg.billing_user_id else msg.model_ref


def _bill_embed_ref(msg: "SummarizeMessage") -> str:
    return msg.billing_embedding_model if msg.billing_user_id else msg.embedding_model_uuid


async def process_summarize_message(
    msg: SummarizeMessage, deps: SummaryProcessorDeps,
) -> SummaryProcessResult:
    """Process one extraction.summarize message.

    Idempotent: cache hit on summary_input_md5 returns immediately without
    LLM call (D10 re-run cheapness). M5 race losers also short-circuit
    gracefully.
    """
    # 0. M4 retry budget check.
    if msg.retried_n >= RETRY_BUDGET:
        logger.warning(
            "summary.abandoned level=%s node_id=%s retried_n=%d",
            msg.level, msg.node_id, msg.retried_n,
        )
        return SummaryProcessResult(
            level=msg.level, node_id=msg.node_id,
            cache_hit=False, race_winner=False,
            re_enqueued=False, skipped_retry_exhausted=True,
            summary_id=None,
        )

    # 0a. M4 retry_at: if retry_at_epoch is in the future, SLEEP in-process
    # until then, then fall through to normal processing. Do NOT re-enqueue
    # + increment retried_n on this branch.
    #
    # The earlier impl re-enqueued via _reenqueue_with_backoff here, which
    # silently burned the entire retry budget within seconds: Redis Streams
    # have no time-based delivery, so the re-enqueued message was picked up
    # immediately, bumped retried_n, pushed back, and so on — RETRY_BUDGET=3
    # was exhausted in milliseconds. Caught by D-P3-BOOK-SUMMARY-PERSIST-
    # AUDIT (stream archaeology showed retried_n=0→1→2→3 consecutive
    # messages with the wall-clock gap << the intended 30+60+120s window).
    #
    # Inline sleep blocks the consumer worker on this one message for up
    # to 120s; the worker-ai consumer reads up to 10 messages per
    # XREADGROUP and processes them serially, so a busy stream pays the
    # latency. Acceptable for extraction workloads (low per-book volume).
    delay_s = msg.retry_at_epoch - now_epoch()
    if delay_s > 0:
        await asyncio.sleep(min(delay_s, MAX_INLINE_RETRY_SLEEP_S))

    repo = LevelSummariesRepo(deps.knowledge_pool)
    book_id = UUID(msg.book_id)
    node_id = UUID(msg.node_id)
    project_id = UUID(msg.project_id) if msg.project_id else None
    extractor_version = get_extractor_version(op="summarize_level")

    # 1. Load child content + entity names for this level.
    try:
        child_texts, entity_names = await _load_children_for_level(
            level=msg.level,
            node_id=node_id,
            book_id=book_id,
            embedding_model_uuid=msg.embedding_model_uuid,
            repo=repo,
            neo4j_session=deps.neo4j_session,
        )
    except _DefensiveCheckFailed as exc:
        # D9: children not ready yet. Re-enqueue.
        logger.info(
            "summary deferred level=%s node_id=%s reason=%s",
            msg.level, msg.node_id, exc,
        )
        await _reenqueue_with_backoff(deps.summary_enqueue, msg)
        return SummaryProcessResult(
            level=msg.level, node_id=msg.node_id,
            cache_hit=False, race_winner=False,
            re_enqueued=True, skipped_retry_exhausted=False,
            summary_id=None,
        )

    # 2. Compute summary_input_md5 (D10 + SR-4 includes prompt version).
    summary_input_md5 = _compute_md5(
        child_texts=child_texts,
        level=msg.level,
        extractor_version=extractor_version,
        model_ref=msg.model_ref,
    )

    # 3. D10 cache check: skip LLM if existing row's md5 matches.
    cached = await repo.find_cached(
        level=msg.level,
        level_id=node_id,
        embedding_model_uuid=msg.embedding_model_uuid,
        summary_input_md5=summary_input_md5,
    )
    if cached is not None:
        logger.info(
            "summary cache HIT level=%s node_id=%s md5=%s",
            msg.level, msg.node_id, summary_input_md5[:8],
        )
        return SummaryProcessResult(
            level=msg.level, node_id=msg.node_id,
            cache_hit=True, race_winner=False,
            re_enqueued=False, skipped_retry_exhausted=False,
            summary_id=cached.id,
        )

    # 4. Call summarize_level extractor (LLM). E0-3 2a-2: a collaborator-
    # triggered summary resolves the LLM under the CALLER's key + LLM ref.
    project_id_str = msg.project_id or None
    _bill_ref = _bill_llm_ref(msg)
    # Model-context-aware input sizing — a flat 8000-char child-text cap tuned for
    # a mid-size model shouldn't truncate a genuinely bigger model's input the same.
    _context_length = await resolve_context_length("user_model", _bill_ref)
    summary = await summarize_level(
        level=msg.level,
        child_texts=child_texts,
        entity_names=entity_names,
        user_id=_bill_user(msg),
        project_id=project_id_str,
        model_source="user_model",
        model_ref=_bill_ref,
        llm_client=deps.llm_client,
        context_length=_context_length,
    )
    summary_text = summary.summary_text[:500]  # L3 fix: writer truncates

    # 5. Embed the summary. E0-3 2a-2: generate under the caller's embedding ref
    # (the adapter's user is bound to the same billing user in the endpoint);
    # the STORED tag below stays msg.embedding_model_uuid (the project's).
    embedding = await deps.embedding_client.embed(
        text=summary_text,
        model_uuid=_bill_embed_ref(msg),
    )

    # 6. Persist row + write Neo4j hierarchy-node properties.
    outcome: UpsertOutcome = await repo.upsert_summary(
        level=msg.level,
        level_id=node_id,
        book_id=book_id,
        summary_text=summary_text,
        summary_input_md5=summary_input_md5,
        embedding_dimension=msg.embedding_dimension,
        embedding_model_uuid=msg.embedding_model_uuid,
    )

    if outcome.race_winner:
        # Only race winner writes Neo4j (avoid duplicate vector index ops).
        await _write_neo4j_summary(
            neo4j_session=deps.neo4j_session,
            level=msg.level,
            node_path=msg.node_path,
            summary_text=summary_text,
            embedding=embedding,
            project_id=str(project_id) if project_id else "",
            embedding_model_uuid=msg.embedding_model_uuid,
            embedding_dimension=msg.embedding_dimension,
        )

    return SummaryProcessResult(
        level=msg.level, node_id=msg.node_id,
        cache_hit=False, race_winner=outcome.race_winner,
        re_enqueued=False, skipped_retry_exhausted=False,
        summary_id=outcome.summary_id,
    )


# ── helpers ─────────────────────────────────────────────────────────────────


class _DefensiveCheckFailed(Exception):
    """Raised internally when D9 defensive check fails for part/book level."""


def _compute_md5(
    *, child_texts: list[str], level: Level, extractor_version: str,
    model_ref: str,
) -> str:
    """Spec D10 + SR-4: include extractor_version + model_ref so prompt edit
    or model change invalidates cache implicitly."""
    joined = "\n\n".join(child_texts)
    payload = (
        f"{joined}\x1f{level}\x1f{extractor_version}\x1f{model_ref.lower()}"
    ).encode("utf-8")
    return hashlib.md5(payload, usedforsecurity=False).hexdigest()


async def _load_children_for_level(
    *,
    level: Level,
    node_id: UUID,
    book_id: UUID,
    embedding_model_uuid: str,
    repo: LevelSummariesRepo,
    neo4j_session: CypherSession,
) -> tuple[list[str], list[str]]:
    """Return (child_texts, entity_names) for the given level node.

    - chapter: child_texts = real scene leaf_texts from book-service (FD-3);
      entity_names = top entities mentioned in this chapter.
    - part: child_texts = chapter summaries from Postgres summary_chapters;
      entity_names = top entities aggregated across the part's chapters.
    - book: child_texts = part summaries; entity_names = top across book.

    D9 defensive check (part/book only): if expected_children != actual rows,
    raise _DefensiveCheckFailed → caller re-enqueues per M4.
    """
    if level == "chapter":
        # FD-3: load the REAL scene prose from book-service (not Neo4j path stubs).
        scene_texts = await _load_scene_leaf_texts(book_id, node_id)
        if not scene_texts:
            # Legacy chapter w/o :Scene children: spec D6 says Mode-3
            # falls through gracefully; for summary, skip (no content
            # to summarize meaningfully). _DefensiveCheckFailed will
            # re-enqueue once; second attempt also empty → retry budget
            # exhausts → abandoned. Better: log + return empty so caller
            # marks skipped_retry_exhausted directly.
            raise _DefensiveCheckFailed(
                f"chapter {node_id} has no :Scene children (legacy?)"
            )
        entity_names = await _load_top_entities_for_chapter(neo4j_session, node_id)
        return scene_texts, entity_names

    elif level == "part":
        # Defensive: load all chapter summaries for the book; if fewer than
        # the part's children expects, re-enqueue.
        expected_chapters = await _count_expected_chapter_children(
            neo4j_session, node_id,
        )
        chapter_summaries = await repo.list_by_book(
            book_id=book_id, level="chapter",
            embedding_model_uuid=embedding_model_uuid,
        )
        # Filter chapter summaries to ONLY those under this part.
        part_chapter_summaries = await _filter_summaries_under_part(
            neo4j_session, chapter_summaries, part_id=node_id,
        )
        if len(part_chapter_summaries) < expected_chapters:
            raise _DefensiveCheckFailed(
                f"part {node_id}: expected {expected_chapters} chapter "
                f"summaries, found {len(part_chapter_summaries)}"
            )
        child_texts = [s.summary_text for s in part_chapter_summaries]
        entity_names = await _load_top_entities_for_part(neo4j_session, node_id)
        return child_texts, entity_names

    elif level == "book":
        expected_parts = await _count_expected_part_children(
            neo4j_session, node_id,
        )
        part_summaries = await repo.list_by_book(
            book_id=book_id, level="part",
            embedding_model_uuid=embedding_model_uuid,
        )
        if len(part_summaries) < expected_parts:
            raise _DefensiveCheckFailed(
                f"book {node_id}: expected {expected_parts} part "
                f"summaries, found {len(part_summaries)}"
            )
        child_texts = [s.summary_text for s in part_summaries]
        entity_names = await _load_top_entities_for_book(neo4j_session, node_id)
        return child_texts, entity_names

    raise ValueError(f"unknown level {level!r}")


async def _reenqueue_with_backoff(
    enqueue: SummaryEnqueueFn, msg: SummarizeMessage,
) -> None:
    """M4: XADD a new message with retry_at + retried_n+1."""
    next_retry_idx = min(msg.retried_n, len(REENQUEUE_BACKOFF_S) - 1)
    backoff_s = REENQUEUE_BACKOFF_S[next_retry_idx]
    new_msg = SummarizeMessage(
        level=msg.level,
        node_path=msg.node_path,
        node_id=msg.node_id,
        book_id=msg.book_id,
        user_id=msg.user_id,
        project_id=msg.project_id,
        job_id=msg.job_id,
        model_ref=msg.model_ref,
        embedding_model_uuid=msg.embedding_model_uuid,
        embedding_dimension=msg.embedding_dimension,
        retry_at_epoch=now_epoch() + backoff_s,
        retried_n=msg.retried_n + 1,
        # E0-3 2a-2: forward billing identity on retry, else a retried summary
        # would silently fall back to the owner's key.
        billing_user_id=msg.billing_user_id,
        billing_llm_model=msg.billing_llm_model,
        billing_embedding_model=msg.billing_embedding_model,
    )
    await enqueue(new_msg)


# ── Neo4j helpers (stubs — wired to neo4j_repos in worker-ai task setup) ──


async def _load_scene_leaf_texts(book_id: UUID, chapter_id: UUID) -> list[str]:
    """FD-3 — load the REAL per-scene prose for this chapter from book-service
    (was a stub that returned Neo4j `s.path` strings, so summaries were built from
    path noise). Mirrors the proven P2 D8 contract (`pass2_orchestrator
    ._fetch_chapter_leaf_text`):

    - `list_scenes_by_chapter` → None = transport failure → raise
      `_DefensiveCheckFailed` (transient; the caller re-enqueues — never summarize
      on missing prose);
    - a P1-decomposed chapter → the ordered scene `leaf_text`s (real prose);
    - a legacy chapter (empty scenes) or scenes with no usable text → fall back to
      the chapter draft text wrapped as ONE child (so legacy chapters still get a
      real summary instead of being abandoned — PO decision);
    - truly empty (no scenes, no draft) → `[]` (the caller raises → skipped).
    """
    client = get_book_client()
    scenes = await client.list_scenes_by_chapter(book_id, chapter_id)
    if scenes is None:
        raise _DefensiveCheckFailed(
            f"chapter {chapter_id} scenes unavailable from book-service (transient)"
        )
    texts = [t for s in scenes if (t := (s.get("leaf_text") or "").strip())]
    if texts:
        return texts
    # Legacy chapter (NULL structural_path → empty scenes), or scenes carried no
    # text: D8 fallback to the chapter draft (Tiptap→text) as a single unit.
    draft = await client.get_chapter_draft_text(book_id, chapter_id)
    if draft and draft.strip():
        return [draft.strip()]
    return []


async def _load_top_entities_for_chapter(
    session: CypherSession, chapter_id: UUID, limit: int = 30,
) -> list[str]:
    rows = await session.run(
        """
        MATCH (c:Chapter {chapter_id: $chapter_id})<-[:MENTIONED_IN]-(e:Entity)
        RETURN e.name AS name
        ORDER BY e.confidence DESC
        LIMIT $limit
        """,
        chapter_id=str(chapter_id),
        limit=limit,
    )
    names = []
    async for record in rows:
        names.append(record["name"])
    return names


async def _load_top_entities_for_part(
    session: CypherSession, part_id: UUID, limit: int = 30,
) -> list[str]:
    rows = await session.run(
        """
        MATCH (p:Part {part_id: $part_id})-[:HAS_CHILD]->(:Chapter)<-[:MENTIONED_IN]-(e:Entity)
        WITH e, count(*) AS mentions
        ORDER BY mentions DESC
        LIMIT $limit
        RETURN e.name AS name
        """,
        part_id=str(part_id),
        limit=limit,
    )
    names = []
    async for record in rows:
        names.append(record["name"])
    return names


async def _load_top_entities_for_book(
    session: CypherSession, book_id: UUID, limit: int = 50,
) -> list[str]:
    rows = await session.run(
        """
        MATCH (b:Book {book_id: $book_id})-[:HAS_CHILD*..3]->(:Chapter)<-[:MENTIONED_IN]-(e:Entity)
        WITH e, count(*) AS mentions
        ORDER BY mentions DESC
        LIMIT $limit
        RETURN e.name AS name
        """,
        book_id=str(book_id),
        limit=limit,
    )
    names = []
    async for record in rows:
        names.append(record["name"])
    return names


async def _count_expected_chapter_children(
    session: CypherSession, part_id: UUID,
) -> int:
    rows = await session.run(
        "MATCH (p:Part {part_id: $part_id})-[:HAS_CHILD]->(c:Chapter) RETURN count(c) AS n",
        part_id=str(part_id),
    )
    async for record in rows:
        return int(record["n"])
    return 0


async def _count_expected_part_children(
    session: CypherSession, book_id: UUID,
) -> int:
    rows = await session.run(
        "MATCH (b:Book {book_id: $book_id})-[:HAS_CHILD]->(p:Part) RETURN count(p) AS n",
        book_id=str(book_id),
    )
    async for record in rows:
        return int(record["n"])
    return 0


async def _filter_summaries_under_part(
    session: CypherSession, summaries: list, part_id: UUID,
):
    """Filter the book's chapter summaries to ONLY those under this part."""
    rows = await session.run(
        """
        MATCH (p:Part {part_id: $part_id})-[:HAS_CHILD]->(c:Chapter)
        RETURN c.chapter_id AS chapter_id
        """,
        part_id=str(part_id),
    )
    part_chapter_ids: set[str] = set()
    async for record in rows:
        part_chapter_ids.add(str(record["chapter_id"]))
    return [s for s in summaries if str(s.level_id) in part_chapter_ids]


async def _write_neo4j_summary(
    *,
    neo4j_session: CypherSession,
    level: Level,
    node_path: str,
    summary_text: str,
    embedding: list[float],
    project_id: str,
    embedding_model_uuid: str,
    embedding_dimension: int,
) -> None:
    """Write summary_text + summary_embedding to the hierarchy node.

    Ensures the per-(project, embedding_model) vector index exists first
    (H1+M7+SR-2 fix).
    """
    # H1: ensure index family exists for this project + embedding_model.
    if project_id:
        await ensure_summary_indexes(
            neo4j_session,
            project_id=project_id,
            embedding_model_uuid=embedding_model_uuid,
            embedding_dimension=embedding_dimension,
        )
    node_label = level.capitalize()
    await neo4j_session.run(
        f"""
        MATCH (n:{node_label} {{path: $path}})
        SET n.summary_text = $text,
            n.summary_embedding = $embedding,
            n.summary_model_uuid = $model_uuid,
            n.summary_updated_at = datetime()
        """,
        path=node_path,
        text=summary_text,
        embedding=embedding,
        model_uuid=embedding_model_uuid,
    )
