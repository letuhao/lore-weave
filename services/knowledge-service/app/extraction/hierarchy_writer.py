"""P3 — Neo4j hierarchy writer (spec D2 + D2a Tx boundary).

Writes :Book/:Part/:Chapter/:Scene nodes + :HAS_CHILD edges in a
single Cypher Tx per chapter. Idempotent via MERGE on path string
(P1 paths are deterministic — same input -> same path).

Per spec D2a: this writer runs INSIDE the same Tx as pass2_writer
so partial failure of either rolls back the whole chapter consistently.
Caller (pass2_writer or pass2_orchestrator integration) is responsible
for opening the Tx.

NEW edges added per D2 (preserves existing :EVIDENCED_BY for provenance):
  :Book-[:HAS_CHILD]->:Part-[:HAS_CHILD]->:Chapter-[:HAS_CHILD]->:Scene

The :MENTIONED_IN edge from :Entity -> :Scene (or :Chapter for legacy)
is written by pass2_writer (it knows the entity IDs); hierarchy_writer
just provisions the hierarchy nodes.

D6 no-backfill: when scene_paths is empty (legacy chapter, no P1
decomposition), this writer creates :Chapter + :Part + :Book but NOT
:Scene. pass2_writer's :MENTIONED_IN then targets :Chapter directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.db.neo4j_helpers import CypherSession
from app.db.graph_repos.hierarchy import upsert_hierarchy_chain

logger = logging.getLogger(__name__)

__all__ = ["HierarchyPaths", "upsert_for_chapter"]


@dataclass
class HierarchyPaths:
    """Path strings for one chapter's hierarchy.

    All paths are deterministic from P1's structural decomposition.
    Scene paths can be empty (legacy chapter — D6 fallback).
    """
    book_id: str
    book_path: str          # "book"
    book_title: str | None
    part_id: str
    part_path: str          # "book/part-1"
    part_index: int
    part_title: str | None
    chapter_id: str
    chapter_path: str       # "book/part-1/chapter-3"
    chapter_index: int      # sort_order from book-service
    chapter_title: str | None
    scenes: list[tuple[str, str, int]]  # (scene_id, scene_path, scene_index)


async def upsert_for_chapter(
    session: CypherSession,
    paths: HierarchyPaths,
) -> dict[str, Any]:
    """Idempotent MERGE of Book/Part/Chapter/Scene hierarchy for ONE chapter.

    Returns: {chapter_path, scenes_count, source_label} — source_label is
    'Scene' when scenes existed, 'Chapter' when legacy fallback (no scenes).

    Per D2a: caller MUST run this inside the same Tx as pass2_writer so
    partial failure is atomic. This function does NOT open a Tx itself.

    The MERGE moved to `graph_repos/hierarchy.py` (plan T17); what stays here is the path
    construction and the source-label decision, which are extraction's business.
    """
    await upsert_hierarchy_chain(
        session,
        book_path=paths.book_path,
        book_id=paths.book_id,
        book_title=paths.book_title,
        part_path=paths.part_path,
        part_id=paths.part_id,
        part_index=paths.part_index,
        part_title=paths.part_title,
        chapter_path=paths.chapter_path,
        chapter_id=paths.chapter_id,
        chapter_index=paths.chapter_index,
        chapter_title=paths.chapter_title,
        scenes=[
            {"scene_id": sid, "path": spath, "scene_index": sidx}
            for sid, spath, sidx in paths.scenes
        ],
    )
    source_label = "Scene" if paths.scenes else "Chapter"
    return {
        "chapter_path": paths.chapter_path,
        "scenes_count": len(paths.scenes),
        "source_label": source_label,
    }
