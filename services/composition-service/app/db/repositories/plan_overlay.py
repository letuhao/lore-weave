"""plan_overlay repository — the Plan Hub v2 decorations aggregate (24 PH18/PH19,
read surface #3).

ALL of H1.3's raw SQL lives here (the slice owns no other repo). Every query keys
on ``book_id`` (BPS-1/BA8 — the package is per-book); access is decided BEFORE the
repo at the E0 VIEW gate in ``routers/plan_overlay.py`` (25 PM-8), so these reads
never filter on the caller. The router assembles the bounded, partiality-flagged
response from these raw rows via a pure builder (``_build_overlay``) — keeping the
aggregation testable without a DB.

Four sources, all local to composition-service (no cross-service read — the
unplanned-chapters tray needs book-service and is returned empty here, PH21/OQ-8):

  • canon anchors  — active ``canon_rule`` rows tied to a chapter by story-order
                     boundary (``from_order``/``until_order`` == the chapter's
                     ``story_order``). ``canon_rule`` carries no node FK; the story
                     timeline (from/until on ``story_order``) is its only node axis
                     (see ``canon_rules.py``), and the boundary anchor keeps the
                     overlay SPARSE (each rule → its ≤2 boundary chapters) so the
                     ~50-ref cap and the per-node badge stay meaningful. Unbounded
                     world/entity rules (both orders NULL) are book-global, not a
                     per-node problem, and are intentionally not attributed.
  • open threads   — ``narrative_thread`` rows still owed (status open|progressing,
                     not archived), joined to their opening node + that node's arc
                     (chapter → its ``structure_node_id``; scene → its parent
                     chapter's) for the arc-subtree rollup (BA15).
  • tension rollup — per chapter, the DERIVED tension (avg of its scenes' tension,
                     else the chapter's own) — never stored (BPS-3/DA-7/PH17).
  • motif chips    — the ``motif_application`` lockfile: one chip per pinned motif
                     on a node/arc, with the pinned version + the motif's live
                     version (PH19 — the FE renders staleness when live > pinned).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

# ── canon: rules whose story-order boundary lands ON a chapter node ───────────
# A partial index (idx_canon_rule_book) serves the `active AND NOT is_archived`
# predicate; the boundary equality join is over the (sparse) bounded rules only.
_CANON_ANCHORS_SQL = """
SELECT cr.id   AS rule_id,
       cr.text AS rule_text,
       o.id                 AS node_id,
       o.structure_node_id  AS arc_id
FROM canon_rule cr
JOIN outline_node o
  ON o.book_id = cr.book_id
 AND o.kind = 'chapter'
 AND NOT o.is_archived
 AND (o.story_order = cr.from_order OR o.story_order = cr.until_order)
WHERE cr.book_id = $1
  AND cr.active
  AND NOT cr.is_archived
  AND (cr.from_order IS NOT NULL OR cr.until_order IS NOT NULL)
ORDER BY o.story_order NULLS LAST, cr.id
"""

# ── open threads + the node they opened at + that node's arc ──────────────────
# opened_at_node is FK→outline_node (SET NULL on delete → a NULL node is an
# un-anchored thread, skipped from by_node by the builder). A scene's arc rides
# its parent chapter's structure_node_id (structure_node_id lives only on chapters,
# outline_structure_kind CHECK); a chapter carries its own.
_OPEN_THREADS_SQL = """
SELECT nt.id       AS thread_id,
       nt.summary  AS summary,
       nt.trigger  AS trigger,
       nt.kind     AS thread_kind,
       nt.opened_at_node AS node_id,
       o.kind      AS node_kind,
       COALESCE(o.structure_node_id, chap.structure_node_id) AS arc_id
FROM narrative_thread nt
LEFT JOIN outline_node o    ON o.id = nt.opened_at_node
LEFT JOIN outline_node chap ON chap.id = o.parent_id AND o.kind = 'scene'
WHERE nt.book_id = $1
  AND nt.status IN ('open', 'progressing')
  AND NOT nt.is_archived
ORDER BY nt.priority DESC, nt.created_at, nt.id
"""

# ── structure_node parent edges (for the arc-subtree rollup; depth ≤ 2) ───────
_STRUCTURE_PARENTS_SQL = """
SELECT id, parent_id
FROM structure_node
WHERE book_id = $1 AND NOT is_archived
"""

# ── derived per-chapter tension (PH17): scene avg, else the chapter's own ──────
_TENSION_ROLLUP_SQL = """
SELECT c.id AS chapter_node_id,
       c.story_order,
       COALESCE(round(avg(s.tension))::int, c.tension) AS tension
FROM outline_node c
LEFT JOIN outline_node s
  ON s.parent_id = c.id
 AND s.kind = 'scene'
 AND NOT s.is_archived
 AND s.tension IS NOT NULL
WHERE c.book_id = $1 AND c.kind = 'chapter' AND NOT c.is_archived
GROUP BY c.id, c.story_order, c.tension
HAVING COALESCE(round(avg(s.tension))::int, c.tension) IS NOT NULL
ORDER BY c.story_order NULLS LAST, c.id
"""

# ── motif lockfile chips (PH19): pinned version + the motif's live version ─────
# motif_id is FK→motif SET NULL — a chip needs a live motif, so INNER JOIN drops
# rows whose motif was deleted (motif_id NULL). node_ref prefers the outline node
# (per-node chip), else the structure node (arc-lane chip).
_MOTIF_CHIPS_SQL = """
SELECT COALESCE(ma.outline_node_id, ma.structure_node_id) AS node_ref,
       ma.motif_id      AS motif_id,
       ma.motif_version AS pinned_version,
       m.name           AS title,
       m.version        AS live_version
FROM motif_application ma
JOIN motif m ON m.id = ma.motif_id
WHERE ma.book_id = $1
  AND (ma.outline_node_id IS NOT NULL OR ma.structure_node_id IS NOT NULL)
ORDER BY ma.created_at, ma.id
"""


class PlanOverlayRepo:
    """Read-only aggregate over canon_rule / narrative_thread / outline_node /
    motif_application / structure_node (raw SQL; one method per source). Cheap
    per-request wrapper over the shared pool (mirrors CanonRulesRepo)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def _fetch(self, sql: str, book_id: UUID) -> list[dict[str, Any]]:
        async with self._pool.acquire() as c:
            rows = await c.fetch(sql, book_id)
        # dict() so the pure builder can use .get() (asyncpg.Record has no .get).
        return [dict(r) for r in rows]

    async def fetch_canon_anchors(self, book_id: UUID) -> list[dict[str, Any]]:
        return await self._fetch(_CANON_ANCHORS_SQL, book_id)

    async def fetch_open_threads(self, book_id: UUID) -> list[dict[str, Any]]:
        return await self._fetch(_OPEN_THREADS_SQL, book_id)

    async def fetch_structure_parents(self, book_id: UUID) -> list[dict[str, Any]]:
        return await self._fetch(_STRUCTURE_PARENTS_SQL, book_id)

    async def fetch_tension_rollup(self, book_id: UUID) -> list[dict[str, Any]]:
        return await self._fetch(_TENSION_ROLLUP_SQL, book_id)

    async def fetch_motif_chips(self, book_id: UUID) -> list[dict[str, Any]]:
        return await self._fetch(_MOTIF_CHIPS_SQL, book_id)
