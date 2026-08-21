"""Composition-owned EPUB navigation hierarchy.

The EPUB source tree is intentionally separate from ``structure_node``. The
latter is the existing manuscript-part projection and has a bounded generic
structure model, while a navigation document may be arbitrarily deep.  This
repository stores every selected ToC node losslessly and creates a flat
``structure_node(kind='part')`` projection for nodes that can group Book
chapters.  Book Service remains the sole writer of ``chapters.structure_node_id``.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import asyncpg


_PART_ROLES = frozenset({"volume", "part", "section", "frontmatter", "backmatter", "appendix"})


@dataclass(frozen=True)
class EpubHierarchyInput:
    source_key: str
    parent_source_key: str | None
    role: str
    title: str
    ordinal: int
    depth: int
    chapter_id: UUID | None = None


@dataclass(frozen=True)
class EpubHierarchyMapping:
    source_key: str
    hierarchy_node_id: UUID
    structure_node_id: UUID | None
    chapter_id: UUID | None


class EpubImportHierarchyRepo:
    """Idempotently persists one import job's selected EPUB ToC closure."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def materialize(
        self,
        *,
        book_id: UUID,
        import_job_id: UUID,
        created_by: UUID,
        nodes: list[EpubHierarchyInput],
    ) -> list[EpubHierarchyMapping]:
        """Upsert nodes and return their stable Composition mappings.

        ``structure_node`` is a compatibility projection for Book's established
        manuscript-part assignment. It is purposely flat: the full parent-child
        source topology remains in ``epub_import_hierarchy_node`` and is exposed
        by the internal hierarchy read endpoint.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                supplied_by_key = {node.source_key: node for node in nodes}
                for node in sorted(nodes, key=lambda item: (item.ordinal, item.source_key)):
                    existing = await conn.fetchrow(
                        """
                        SELECT id, structure_node_id
                        FROM epub_import_hierarchy_node
                        WHERE book_id=$1 AND import_job_id=$2 AND source_key=$3
                        FOR UPDATE
                        """,
                        book_id,
                        import_job_id,
                        node.source_key,
                    )
                    structure_node_id = existing["structure_node_id"] if existing else None
                    if structure_node_id is None and node.role in _PART_ROLES:
                        # Keep EPUB-created parts after ordinary authored parts
                        # without taking ownership of their ranks. The rank is
                        # deterministic per import and safely below the eight
                        # digit integer convention's maximum practical range.
                        rank = f"{90_000_000 + node.ordinal:08d}"
                        structure_node_id = await conn.fetchval(
                            """
                            INSERT INTO structure_node(
                              book_id, created_by, parent_id, kind, rank, title,
                              summary, goal, status, tracks, roster, roster_bindings
                            ) VALUES ($1,$2,NULL,'part',$3,$4,'','','outline','[]'::jsonb,'[]'::jsonb,'{}'::jsonb)
                            RETURNING id
                            """,
                            book_id,
                            created_by,
                            rank,
                            node.title,
                        )
                    row = await conn.fetchrow(
                        """
                        INSERT INTO epub_import_hierarchy_node(
                          book_id, import_job_id, source_key, parent_source_key,
                          role, title, ordinal, depth, structure_node_id, created_by
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                        ON CONFLICT (book_id, import_job_id, source_key) DO UPDATE SET
                          parent_source_key=EXCLUDED.parent_source_key,
                          role=EXCLUDED.role,
                          title=EXCLUDED.title,
                          ordinal=EXCLUDED.ordinal,
                          depth=EXCLUDED.depth,
                          structure_node_id=COALESCE(epub_import_hierarchy_node.structure_node_id, EXCLUDED.structure_node_id),
                          updated_at=now()
                        RETURNING id, structure_node_id
                        """,
                        book_id,
                        import_job_id,
                        node.source_key,
                        node.parent_source_key,
                        node.role,
                        node.title,
                        node.ordinal,
                        node.depth,
                        structure_node_id,
                        created_by,
                    )
                rows = await conn.fetch(
                    """
                    SELECT id, source_key, parent_source_key, structure_node_id
                    FROM epub_import_hierarchy_node
                    WHERE book_id=$1 AND import_job_id=$2
                    """,
                    book_id,
                    import_job_id,
                )
                by_key = {row["source_key"]: row for row in rows}

                def nearest_part_id(source_key: str) -> UUID | None:
                    seen: set[str] = set()
                    cursor = by_key.get(source_key)
                    while cursor is not None and cursor["source_key"] not in seen:
                        seen.add(cursor["source_key"])
                        if cursor["structure_node_id"] is not None:
                            return cursor["structure_node_id"]
                        parent = cursor["parent_source_key"]
                        cursor = by_key.get(parent) if parent else None
                    return None

                return [
                    EpubHierarchyMapping(
                        source_key=node.source_key,
                        hierarchy_node_id=by_key[node.source_key]["id"],
                        structure_node_id=nearest_part_id(node.source_key),
                        chapter_id=node.chapter_id,
                    )
                    for node in sorted(supplied_by_key.values(), key=lambda item: (item.ordinal, item.source_key))
                ]

    async def list_nodes(self, *, book_id: UUID, import_job_id: UUID) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, source_key, parent_source_key, role, title, ordinal,
                       depth, structure_node_id
                FROM epub_import_hierarchy_node
                WHERE book_id=$1 AND import_job_id=$2
                ORDER BY ordinal, source_key
                """,
                book_id,
                import_job_id,
            )
        return [dict(row) for row in rows]

    async def rollback(self, *, book_id: UUID, import_job_id: UUID) -> int:
        """Remove this import's lossless tree and archive its projections.

        Only rows keyed by the job are touched. Projection rows are archived
        rather than hard-deleted so a concurrent reader never observes a
        dangling structure reference and the operation remains retry-safe.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                ids = await conn.fetch(
                    """
                    SELECT structure_node_id
                    FROM epub_import_hierarchy_node
                    WHERE book_id=$1 AND import_job_id=$2 AND structure_node_id IS NOT NULL
                    FOR UPDATE
                    """,
                    book_id,
                    import_job_id,
                )
                if ids:
                    await conn.execute(
                        """
                        UPDATE structure_node
                        SET is_archived=TRUE, updated_at=now()
                        WHERE book_id=$1 AND id=ANY($2::uuid[])
                        """,
                        book_id,
                        [row["structure_node_id"] for row in ids],
                    )
                result = await conn.execute(
                    "DELETE FROM epub_import_hierarchy_node WHERE book_id=$1 AND import_job_id=$2",
                    book_id,
                    import_job_id,
                )
        return int(result.split()[-1]) if result else 0
