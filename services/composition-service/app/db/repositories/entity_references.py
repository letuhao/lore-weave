"""28 AN-3 — `EntityReferencesRepo`: the INVERSE query. "Where is this entity used?"

Composition is the only service where this query did not exist at all. The prose side has
`glossary_list_chapter_links`; the graph side has `kg_entity_edge_timeline`. The spec side — which
outline nodes have this character as POV, which scenes have them present, which arc roster binds
them, which motifs and canon rules and promises name them — had no inverse index and no tool.

NAMING (a deliberate deviation from 28's shorthand, which says "ReferencesRepo.find_by_entity").
`ReferencesRepo` ALREADY EXISTS in this package and means something else entirely: the author's
REFERENCE SHELF (LOOM T3.6) — a library of source documents with embeddings and a cosine search.
Hanging an entity-backlink query off that class would put two unrelated concepts behind one name,
which is precisely the drift the MCP Tool I/O standard's one-name-one-concept rule exists to stop.
So: `EntityReferencesRepo`, its own module, and the tool keeps the spec's name
(`composition_find_references`) because THAT name is unambiguous at the tool layer.

Eight sources, each a real join against a column that exists. Two were not where the spec's
shorthand suggested, and the difference is load-bearing:

  * There is no `scenes` table in this database — the prose scenes live in book-service. But
    `outline_node` holds BOTH chapters and scenes (`kind`), so the pov/present pair splits by kind.
    That is what AN-1 means by "the outline pov/present pair splits", and it keeps the tool
    composition-scoped, exactly as AN-3 requires (no federation in v1).
  * `narrative_thread` carries no entity column at all. A promise is opened AT A NODE
    (`opened_at_node`), so an entity's threads are the promises opened where that entity appears.
    A genuine join, not a stand-in — and it is the question an author actually asks: "what did I
    promise in her scenes?"

Counts are EXACT; rows are capped (OUT-5). The agent reasons about the number and only samples the
rows, so capping the count would make it reason about a lie.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

#: NO `project_id` ANYWHERE IN THIS FILE, deliberately. Every one of the eight sources is
#: BOOK-scoped (`outline_node`, `structure_node`, `motif_application`, `canon_rule` and
#: `narrative_thread` all carry `book_id`), and the E0 gate is on the book. Threading a project_id
#: through and never using it was worse than useless: the tool was passing `pid or book_id` — a BOOK
#: id in a project slot — so the first person to add a project-keyed source would have silently
#: scoped it by the wrong key.
#:
#: Chapters and scenes are the same table, told apart by `kind`.
_NODE_KIND = {
    "outline_pov": "chapter", "outline_present": "chapter",
    "scene_pov": "scene", "scene_present": "scene",
}


class EntityReferencesRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def find(
        self, source: str, *, book_id: UUID, entity_id: UUID, limit: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        """`(exact_count, capped_refs)` for ONE source.

        RAISES on an unknown source. A closed-set arg that quietly returned `(0, [])` for a typo
        would read as "this entity is used nowhere" — the worst possible lie for a find-references
        tool, because the agent's next move on that answer is to delete something.
        """
        fn = {
            "outline_pov": self._pov,
            "outline_present": self._present,
            "scene_pov": self._pov,
            "scene_present": self._present,
            "structure_roster": self._structure_roster,
            "motif_application": self._motif_application,
            "canon_rule": self._canon_rule,
            "narrative_thread": self._narrative_thread,
        }.get(source)
        if fn is None:
            raise ValueError(f"unknown reference source: {source}")
        if source in _NODE_KIND:
            return await fn(book_id, entity_id, limit, kind=_NODE_KIND[source], source=source)
        return await fn(book_id, entity_id, limit)

    # ── outline_node — chapters AND scenes, split by kind ────────────────────────────────────
    async def _pov(
        self, book_id: UUID, entity_id: UUID, limit: int, *, kind: str, source: str,
    ) -> tuple[int, list[dict[str, Any]]]:
        where = "book_id = $1 AND kind = $2 AND pov_entity_id = $3 AND NOT is_archived"
        async with self._pool.acquire() as c:
            count = await c.fetchval(
                f"SELECT count(*) FROM outline_node WHERE {where}", book_id, kind, entity_id,
            )
            rows = await c.fetch(
                f"SELECT id, title FROM outline_node WHERE {where}"
                " ORDER BY story_order NULLS LAST LIMIT $4",
                book_id, kind, entity_id, limit,
            )
        return count or 0, [_ref(source, kind, r, "point of view") for r in rows]

    async def _present(
        self, book_id: UUID, entity_id: UUID, limit: int, *, kind: str, source: str,
    ) -> tuple[int, list[dict[str, Any]]]:
        where = (
            "book_id = $1 AND kind = $2 AND present_entity_ids @> ARRAY[$3::uuid]"
            " AND NOT is_archived"
        )
        async with self._pool.acquire() as c:
            count = await c.fetchval(
                f"SELECT count(*) FROM outline_node WHERE {where}", book_id, kind, entity_id,
            )
            rows = await c.fetch(
                f"SELECT id, title FROM outline_node WHERE {where}"
                " ORDER BY story_order NULLS LAST LIMIT $4",
                book_id, kind, entity_id, limit,
            )
        return count or 0, [_ref(source, kind, r, "present in the scene") for r in rows]

    # ── structure_node.roster_bindings — {role_key: entity_id} ───────────────────────────────
    async def _structure_roster(
        self, book_id: UUID, entity_id: UUID, limit: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        """PF-13's symbol table, read the other way round: which arcs cast this person, and as what?

        The binding is a JSONB VALUE, so the match runs over `jsonb_each_text`.
        """
        q = """
        SELECT n.id, n.title, n.kind, n.rank, b.key AS role_key
          FROM structure_node n, jsonb_each_text(n.roster_bindings) AS b(key, value)
         WHERE n.book_id = $1 AND b.value = $2 AND NOT n.is_archived
        """
        async with self._pool.acquire() as c:
            count = await c.fetchval(f"SELECT count(*) FROM ({q}) t", book_id, str(entity_id))
            rows = await c.fetch(f"{q} ORDER BY n.rank LIMIT $3", book_id, str(entity_id), limit)
        return count or 0, [
            {
                "source": "structure_roster",
                "node_ref": {"kind": r["kind"], "id": str(r["id"]), "title": r["title"]},
                "detail": f'cast as "{r["role_key"]}"',
            }
            for r in rows
        ]

    # ── motif_application.role_bindings ──────────────────────────────────────────────────────
    async def _motif_application(
        self, book_id: UUID, entity_id: UUID, limit: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        q = """
        SELECT a.id, a.motif_id, a.created_at, b.key AS role_key
          FROM motif_application a, jsonb_each_text(a.role_bindings) AS b(key, value)
         WHERE a.book_id = $1 AND b.value = $2
        """
        async with self._pool.acquire() as c:
            count = await c.fetchval(f"SELECT count(*) FROM ({q}) t", book_id, str(entity_id))
            rows = await c.fetch(
                f"{q} ORDER BY a.created_at DESC LIMIT $3", book_id, str(entity_id), limit,
            )
        return count or 0, [
            {
                "source": "motif_application",
                "node_ref": {"kind": "motif_application", "id": str(r["id"]), "title": None},
                "detail": f'plays "{r["role_key"]}" in motif {r["motif_id"]}',
            }
            for r in rows
        ]

    # ── canon_rule.entity_id ─────────────────────────────────────────────────────────────────
    async def _canon_rule(
        self, book_id: UUID, entity_id: UUID, limit: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        async with self._pool.acquire() as c:
            count = await c.fetchval(
                "SELECT count(*) FROM canon_rule"
                " WHERE book_id = $1 AND entity_id = $2 AND NOT is_archived",
                book_id, entity_id,
            )
            rows = await c.fetch(
                "SELECT id, text FROM canon_rule"
                " WHERE book_id = $1 AND entity_id = $2 AND NOT is_archived"
                " ORDER BY created_at DESC LIMIT $3",
                book_id, entity_id, limit,
            )
        return count or 0, [
            {
                "source": "canon_rule",
                "node_ref": {"kind": "canon_rule", "id": str(r["id"]), "title": None},
                "detail": str(r["text"] or "")[:140],
            }
            for r in rows
        ]

    # ── narrative_thread — via the NODE the promise was opened at ────────────────────────────
    async def _narrative_thread(
        self, book_id: UUID, entity_id: UUID, limit: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        q = """
        SELECT t.id, t.summary, t.status, t.priority, t.created_at
          FROM narrative_thread t
          JOIN outline_node n ON n.id = t.opened_at_node
         WHERE t.book_id = $1 AND NOT t.is_archived AND NOT n.is_archived
           AND (n.pov_entity_id = $2 OR n.present_entity_ids @> ARRAY[$2::uuid])
        """
        async with self._pool.acquire() as c:
            count = await c.fetchval(f"SELECT count(*) FROM ({q}) t2", book_id, entity_id)
            rows = await c.fetch(
                f"{q} ORDER BY t.priority DESC, t.created_at LIMIT $3",
                book_id, entity_id, limit,
            )
        return count or 0, [
            {
                "source": "narrative_thread",
                "node_ref": {"kind": "narrative_thread", "id": str(r["id"]), "title": None},
                "detail": f'{r["status"]}: {str(r["summary"] or "")[:110]}',
            }
            for r in rows
        ]


def _ref(source: str, kind: str, r: Any, why: str) -> dict[str, Any]:
    return {
        "source": source,
        "node_ref": {"kind": kind, "id": str(r["id"]), "title": r["title"]},
        "detail": why,
    }
