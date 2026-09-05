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

from typing import Literal

from app.db.cypher_dialect import render
from app.db.neo4j_helpers import engine_of, CypherSession

__all__ = [
    "count_child_chapters",
    "count_child_parts",
    "list_chapter_ids_under_part",
    "top_entity_names_for_book",
    "top_entity_names_for_chapter",
    "top_entity_names_for_part",
    "upsert_hierarchy_chain",
    "write_summary_to_node",
]


# Single Cypher statement that idempotently MERGEs the full chain for ONE
# chapter. MERGE on `path` is the natural unique key (P1 deterministic);
# constraints in neo4j_schema.py enforce uniqueness.
_UPSERT_CYPHER = """
// §10.1/§10.2 — engine-neutral. AGE has no ON CREATE SET, so each create-only field folds
// into the unconditional SET as `coalesce(field, value)`: identical on Neo4j, because
// coalesce keeps the stored value whenever one exists and there is none on create. The
// title/updated_at assignments were ALREADY unconditional and are untouched.
MERGE (b:Book {path: $book_path})
  SET b.book_id    = coalesce(b.book_id, $book_id),
      b.created_at = coalesce(b.created_at, {NOW}),
      b.book_title = $book_title,
      b.updated_at = {NOW}
MERGE (p:Part {path: $part_path})
  SET p.part_id    = coalesce(p.part_id, $part_id),
      p.book_id    = coalesce(p.book_id, $book_id),
      p.part_index = coalesce(p.part_index, $part_index),
      p.created_at = coalesce(p.created_at, {NOW}),
      p.part_title = $part_title,
      p.updated_at = {NOW}
MERGE (b)-[:HAS_CHILD]->(p)
MERGE (c:Chapter {path: $chapter_path})
  SET c.chapter_id    = coalesce(c.chapter_id, $chapter_id),
      c.book_id       = coalesce(c.book_id, $book_id),
      c.chapter_index = coalesce(c.chapter_index, $chapter_index),
      c.created_at    = coalesce(c.created_at, {NOW}),
      c.chapter_title = $chapter_title,
      c.updated_at    = {NOW}
MERGE (p)-[:HAS_CHILD]->(c)
WITH c
UNWIND $scenes AS sc
  MERGE (s:Scene {path: sc.path})
    SET s.scene_id    = coalesce(s.scene_id, sc.scene_id),
        s.book_id     = coalesce(s.book_id, $book_id),
        s.chapter_id  = coalesce(s.chapter_id, $chapter_id),
        s.scene_index = coalesce(s.scene_index, sc.scene_index),
        s.created_at  = coalesce(s.created_at, {NOW}),
        s.updated_at  = {NOW}
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
        render(_UPSERT_CYPHER, engine_of(session)),
        book_path=book_path, book_id=book_id, book_title=book_title,
        part_path=part_path, part_id=part_id, part_index=part_index, part_title=part_title,
        chapter_path=chapter_path, chapter_id=chapter_id,
        chapter_index=chapter_index, chapter_title=chapter_title,
        scenes=scenes,
    )


# ── hierarchy traversals for the summary pipeline (plan T17) ─────────
#
# ⚠️ Like the MERGE above, these carry NO `$user_id`. They match on `chapter_id` /
# `part_id` / `book_id` / `path`, which are globally-unique ids the caller has already
# resolved through a tenant-scoped path. That is the same justification `run_read_any_owner`
# is documented under, and adding a filter would not help: the hierarchy nodes do not carry
# `user_id` at all, so the clause would match nothing and every summary would come back
# empty.

_TOP_ENTITIES_FOR_CHAPTER_CYPHER = """
MATCH (c:Chapter {chapter_id: $chapter_id})<-[:MENTIONED_IN]-(e:Entity)
RETURN e.name AS name
ORDER BY e.confidence DESC
LIMIT $limit
"""

_TOP_ENTITIES_FOR_PART_CYPHER = """
MATCH (p:Part {part_id: $part_id})-[:HAS_CHILD]->(:Chapter)<-[:MENTIONED_IN]-(e:Entity)
WITH e, count(*) AS mentions
ORDER BY mentions DESC
LIMIT $limit
RETURN e.name AS name
"""

_TOP_ENTITIES_FOR_BOOK_CYPHER = """
MATCH (b:Book {book_id: $book_id})-[:HAS_CHILD*..3]->(:Chapter)<-[:MENTIONED_IN]-(e:Entity)
WITH e, count(*) AS mentions
ORDER BY mentions DESC
LIMIT $limit
RETURN e.name AS name
"""

_COUNT_CHILD_CHAPTERS_CYPHER = (
    "MATCH (p:Part {part_id: $part_id})-[:HAS_CHILD]->(c:Chapter) RETURN count(c) AS n"
)

_COUNT_CHILD_PARTS_CYPHER = (
    "MATCH (b:Book {book_id: $book_id})-[:HAS_CHILD]->(p:Part) RETURN count(p) AS n"
)

_CHAPTER_IDS_UNDER_PART_CYPHER = """
MATCH (p:Part {part_id: $part_id})-[:HAS_CHILD]->(c:Chapter)
RETURN c.chapter_id AS chapter_id
"""


async def _names(session: CypherSession, cypher: str, **params) -> list[str]:
    result = await session.run(cypher, **params)
    return [r["name"] async for r in result if r["name"]]


async def top_entity_names_for_chapter(
    session: CypherSession, *, chapter_id: str, limit: int = 30,
) -> list[str]:
    """Entity names mentioned in one chapter, most-confident first — the summary prompt's
    cast hint. Ordered by CONFIDENCE (not mentions) because a chapter is small enough that
    a single confident mention beats several uncertain ones."""
    return await _names(
        session, _TOP_ENTITIES_FOR_CHAPTER_CYPHER, chapter_id=chapter_id, limit=limit,
    )


async def top_entity_names_for_part(
    session: CypherSession, *, part_id: str, limit: int = 30,
) -> list[str]:
    """Entity names across a part's chapters, most-MENTIONED first. The axis flips from
    confidence to frequency here on purpose: across many chapters, recurrence is the better
    signal of who the part is about."""
    return await _names(
        session, _TOP_ENTITIES_FOR_PART_CYPHER, part_id=part_id, limit=limit,
    )


async def top_entity_names_for_book(
    session: CypherSession, *, book_id: str, limit: int = 50,
) -> list[str]:
    """Same, book-wide. The `*..3` bound is what stops a deep hierarchy turning this into
    an unbounded traversal."""
    return await _names(
        session, _TOP_ENTITIES_FOR_BOOK_CYPHER, book_id=book_id, limit=limit,
    )


async def count_child_chapters(session: CypherSession, *, part_id: str) -> int:
    """How many chapters a part HAS — the denominator for "are all children summarised
    yet?". Counting the graph rather than the summaries is the point: it is what makes a
    missing child detectable instead of invisible."""
    result = await session.run(_COUNT_CHILD_CHAPTERS_CYPHER, part_id=part_id)
    async for record in result:
        return int(record["n"])
    return 0


async def count_child_parts(session: CypherSession, *, book_id: str) -> int:
    """How many parts a book HAS. Same role, one level up."""
    result = await session.run(_COUNT_CHILD_PARTS_CYPHER, book_id=book_id)
    async for record in result:
        return int(record["n"])
    return 0


async def list_chapter_ids_under_part(session: CypherSession, *, part_id: str) -> set[str]:
    """The chapter ids under one part, for filtering a book-wide summary list down to it."""
    result = await session.run(_CHAPTER_IDS_UNDER_PART_CYPHER, part_id=part_id)
    return {str(r["chapter_id"]) async for r in result}


# The node label is INTERPOLATED — Cypher cannot parameterise one — so `Level` being a
# closed Literal is the injection barrier, and it is re-checked here rather than trusted
# from the caller's type annotation.
_SUMMARY_LEVELS: tuple[str, ...] = ("chapter", "part", "book")

_WRITE_SUMMARY_CYPHER = """
MATCH (n:{label} {{path: $path}})
SET n.summary_text = $text,
    n.summary_embedding = $embedding,
    n.summary_model_uuid = $model_uuid,
    n.summary_updated_at = {{NOW}}
"""


async def write_summary_to_node(
    session: CypherSession,
    *,
    level: Literal["chapter", "part", "book"],
    node_path: str,
    summary_text: str,
    embedding: list[float],
    embedding_model_uuid: str,
) -> None:
    """Write a summary and its embedding onto one hierarchy node.

    The CALLER ensures the per-(project, embedding_model) vector index exists first
    (H1+M7+SR-2) — that is index lifecycle, which belongs to the vector store, not here.
    """
    if level not in _SUMMARY_LEVELS:
        raise ValueError(f"level must be one of {_SUMMARY_LEVELS}, got {level!r}")
    # T88 — renders for the SESSION's engine. This is a direct `session.run`, so the
    # `run_read`/`run_write` chokepoint does not reach it and the `{NOW}` token would go to the
    # driver intact: Neo4j reads it as a map literal, AGE says `syntax error at or near "}"`.
    # `.format()` FIRST (the template writes `{{NOW}}`), then render — only one order works.
    await session.run(
        render(_WRITE_SUMMARY_CYPHER.format(label=level.capitalize()), engine_of(session)),
        path=node_path, text=summary_text, embedding=embedding,
        model_uuid=embedding_model_uuid,
    )
