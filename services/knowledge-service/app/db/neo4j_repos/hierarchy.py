"""Book/Part/Chapter/Scene hierarchy writes (plan T17).

Moved out of `app/extraction/hierarchy_writer.py`. The caller keeps the path CONSTRUCTION
and the source-label decision; only the MERGE lives here.

⚠️ **This statement carries no `$user_id`, and that is deliberate rather than an oversight.**
It merges on `path`, which is the natural unique key the schema constraints enforce, and the
path is built by the caller from ids it has already tenant-resolved. Adding a user filter
would not make it safer — it would make the MERGE key disagree with the uniqueness
constraint, and two callers with the same path would start creating duplicate nodes.

⚠️ **It does NOT open a transaction, and must not.** Per D2a the caller runs this in the
SAME transaction as the pass-2 writer so a partial failure is atomic. A repo function that
helpfully wrapped itself would silently break that.
"""

from __future__ import annotations

from typing import Any

from app.db.neo4j_helpers import CypherSession

__all__ = ["upsert_hierarchy_chain"]


# Single Cypher statement that idempotently MERGEs the full chain for ONE
# chapter. MERGE on `path` is the natural unique key (P1 deterministic);
# constraints in neo4j_schema.py enforce uniqueness.
_UPSERT_CYPHER = """
MERGE (b:Book {path: $book_path})
  ON CREATE SET b.book_id = $book_id, b.created_at = datetime()
  SET b.book_title = $book_title, b.updated_at = datetime()
MERGE (p:Part {path: $part_path})
  ON CREATE SET p.part_id = $part_id, p.book_id = $book_id,
                p.part_index = $part_index, p.created_at = datetime()
  SET p.part_title = $part_title, p.updated_at = datetime()
MERGE (b)-[:HAS_CHILD]->(p)
MERGE (c:Chapter {path: $chapter_path})
  ON CREATE SET c.chapter_id = $chapter_id, c.book_id = $book_id,
                c.chapter_index = $chapter_index, c.created_at = datetime()
  SET c.chapter_title = $chapter_title, c.updated_at = datetime()
MERGE (p)-[:HAS_CHILD]->(c)
WITH c
UNWIND $scenes AS sc
  MERGE (s:Scene {path: sc.path})
    ON CREATE SET s.scene_id = sc.scene_id, s.book_id = $book_id,
                  s.chapter_id = $chapter_id, s.scene_index = sc.scene_index,
                  s.created_at = datetime()
    SET s.updated_at = datetime()
  MERGE (c)-[:HAS_CHILD]->(s)
RETURN c.path AS chapter_path
"""


async def upsert_hierarchy_chain(
    session: CypherSession,
    *,
    book_path: str,
    book_id: str,
    book_title: str,
    part_path: str,
    part_id: str,
    part_index: int,
    part_title: str,
    chapter_path: str,
    chapter_id: str,
    chapter_index: int,
    chapter_title: str,
    scenes: list[dict[str, Any]],
) -> None:
    """Idempotent MERGE of the Book→Part→Chapter→Scene chain for ONE chapter.

    `scenes` is `[{scene_id, path, scene_index}]`. Runs in the CALLER's transaction — see
    the module docstring.
    """
    await session.run(
        _UPSERT_CYPHER,
        book_path=book_path, book_id=book_id, book_title=book_title,
        part_path=part_path, part_id=part_id, part_index=part_index, part_title=part_title,
        chapter_path=chapter_path, chapter_id=chapter_id,
        chapter_index=chapter_index, chapter_title=chapter_title,
        scenes=scenes,
    )
