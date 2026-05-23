"""P3 D5 — Mode-3 abstract-query summary index blend.

When `is_abstract_query` classifies a Mode-3 query as abstract, this
selector queries the 3 per-project per-level Neo4j vector indexes
(chapter / part / book summaries) in parallel and blends results by
score-weighted summary text.

Cheap-first design: if NO summary rows exist for the project (legacy
graph never re-extracted post-P3), the selector returns [] and Mode-3
falls through to the standard scene-passage path. No-backfill guarantee
per spec D6 + D5.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.db.neo4j_helpers import CypherSession, summary_index_name

logger = logging.getLogger(__name__)

__all__ = ["LevelSummaryHit", "select_summary_blend"]


# Score weights per level — book summary ranked higher because it answers
# overview questions most directly; scene-level still wins specific queries
# (those don't reach this selector).
_LEVEL_WEIGHTS: dict[str, float] = {
    "chapter": 0.30,
    "part": 0.30,
    "book": 0.40,
}

# Per-level top-K from the vector index. Total candidates = sum, then
# weighted-score sorted and truncated to final_top_n.
_PER_LEVEL_TOP_K = 3


@dataclass
class LevelSummaryHit:
    """One scored summary row from a per-level vector query."""
    level: Literal["chapter", "part", "book"]
    node_id: str
    node_path: str
    summary_text: str
    raw_score: float       # cosine similarity from Neo4j
    weighted_score: float  # raw_score × _LEVEL_WEIGHTS[level]


async def select_summary_blend(
    session: CypherSession,
    *,
    project_id: str,
    embedding_model_uuid: str,
    query_embedding: list[float],
    final_top_n: int = 5,
    per_level_top_k: int = _PER_LEVEL_TOP_K,
) -> list[LevelSummaryHit]:
    """Query the 3 per-level Neo4j vector indexes in parallel; blend results.

    Returns a list ordered by weighted_score descending, truncated to
    final_top_n. Empty list when no summaries exist for this project
    (legacy graphs or pre-extraction).

    Failure-soft: per-level query failures degrade gracefully — they
    contribute 0 hits but don't fail the whole blend.
    """
    if not query_embedding:
        return []

    # Per-level Neo4j vector query — runs against the index named by
    # summary_index_name(project_id, embedding_model_uuid, level).
    # Index missing (not yet bootstrapped) → Neo4j raises; we catch + skip.
    chapter_task = _query_one_level(
        session, "chapter", project_id, embedding_model_uuid,
        query_embedding, per_level_top_k,
    )
    part_task = _query_one_level(
        session, "part", project_id, embedding_model_uuid,
        query_embedding, per_level_top_k,
    )
    book_task = _query_one_level(
        session, "book", project_id, embedding_model_uuid,
        query_embedding, per_level_top_k,
    )

    results = await asyncio.gather(
        chapter_task, part_task, book_task, return_exceptions=True,
    )

    all_hits: list[LevelSummaryHit] = []
    for level, result in zip(("chapter", "part", "book"), results, strict=True):
        if isinstance(result, BaseException):
            # Index might not exist yet (project never extracted post-P3),
            # or Neo4j transient — log + skip.
            logger.debug(
                "summary_blend %s-level query failed: %s",
                level, result,
            )
            continue
        all_hits.extend(result)

    if not all_hits:
        return []

    # Sort by weighted_score descending; truncate to final_top_n.
    all_hits.sort(key=lambda h: h.weighted_score, reverse=True)
    return all_hits[:final_top_n]


async def _query_one_level(
    session: CypherSession,
    level: Literal["chapter", "part", "book"],
    project_id: str,
    embedding_model_uuid: str,
    query_embedding: list[float],
    top_k: int,
) -> list[LevelSummaryHit]:
    """Vector-query one level's index. Returns at most top_k hits."""
    idx_name = summary_index_name(project_id, embedding_model_uuid, level)
    node_label = level.capitalize()  # Chapter / Part / Book
    weight = _LEVEL_WEIGHTS[level]

    # Cypher CALL db.index.vector.queryNodes is the canonical Neo4j 5.x +
    # 2026.x vector-index query. Returns (node, score) tuples.
    cypher = (
        f"CALL db.index.vector.queryNodes($idx_name, $top_k, $emb) "
        "YIELD node, score "
        f"WHERE node:{node_label} "
        "RETURN node.path AS path, "
        f"       coalesce(node.{level}_id, node.book_id) AS node_id, "
        "       coalesce(node.summary_text, '') AS summary_text, "
        "       score"
    )
    rows = await session.run(
        cypher,
        idx_name=idx_name,
        top_k=top_k,
        emb=query_embedding,
    )
    hits: list[LevelSummaryHit] = []
    async for record in rows:
        text = record["summary_text"]
        if not text:
            continue
        raw = float(record["score"])
        hits.append(LevelSummaryHit(
            level=level,
            node_id=str(record["node_id"]) if record["node_id"] else "",
            node_path=record["path"],
            summary_text=text,
            raw_score=raw,
            weighted_score=raw * weight,
        ))
    return hits
