"""Arc decompiler (26-D3 / IX-17) — mint kind='arc' `structure_node`s from an imported book's
chapters. THE gap this closes: the SCENE layer is served (`scene_decompile` mints chapter+scene
`outline_node`s at import), but the ARC layer had NOTHING — so an imported book (prose, no plan)
had no arc structure to steer generation, fill the Hub's arc lane, or ground PlanForge (O-1). And
`plan_propose_spec` is a generator, not a reader of prose, so it was never the path for an already
-written book. This is that path: it groups the book's chapters (reading order) into size-aligned
arcs and mints one `structure_node` per group — `source='decompiled'` (never 'authored'/compile,
so a later compile's PF-10 preservation predicate can tell them apart), `status='outline'` (planned
-but-unwritten), and assigns the group's chapters (`outline_node.structure_node_id`).

IDEMPOTENT (re-run safe, mirrors `scene_decompile`): a re-run REUSES the existing decompiled arcs
by position instead of duplicating — the arc layer converges, it does not fork on every call.
"""

from __future__ import annotations

import math
from typing import Any
from uuid import UUID

from app.db.repositories.structure import StructureRepo

# A sensible default arc size for a serialized web-novel; the caller may override. Not platform
# config — a per-decompile authorial choice (a caller that knows the book's cadence passes its own).
DEFAULT_CHAPTERS_PER_ARC = 10


async def decompile_arcs(
    pool, book_id: UUID, *, created_by: UUID, chapters_per_arc: int = DEFAULT_CHAPTERS_PER_ARC,
) -> dict[str, Any]:
    """Mint/refresh the decompiled arc layer for `book_id`. Returns
    ``{arcs, chapters_assigned, arc_ids, reason?}``. A book with no chapters is a no-op (not an
    error — nothing to decompile). Confirm-gating (a Tier-W propose→confirm) is the CALLER's job;
    this is the durable effect the confirm applies."""
    chapters_per_arc = max(1, chapters_per_arc)
    repo = StructureRepo(pool)

    async with pool.acquire() as c:
        chapters = [
            r["id"] for r in await c.fetch(
                "SELECT id FROM outline_node WHERE book_id=$1 AND kind='chapter' AND NOT is_archived "
                'ORDER BY story_order NULLS LAST, rank COLLATE "C", id',
                book_id,
            )
        ]
        # existing decompiled arcs — reuse by position (idempotency), never re-mint over them.
        existing = [
            r["id"] for r in await c.fetch(
                "SELECT id FROM structure_node WHERE book_id=$1 AND kind='arc' "
                'AND source=\'decompiled\' AND NOT is_archived ORDER BY rank COLLATE "C", id',
                book_id,
            )
        ]

    if not chapters:
        return {"arcs": 0, "chapters_assigned": 0, "reason": "no chapters to decompile"}

    n_arcs = math.ceil(len(chapters) / chapters_per_arc)
    arc_ids: list[UUID] = []
    assigned = 0
    for i in range(n_arcs):
        group = chapters[i * chapters_per_arc:(i + 1) * chapters_per_arc]
        if i < len(existing):
            arc_id = existing[i]  # reuse the i-th decompiled arc (idempotent re-run)
        else:
            # create_node owns rank + the depth trigger; source isn't a create_node arg, so stamp
            # it right after (the row is decompiled-provenance, not authored/compiled).
            arc = await repo.create_node(
                book_id, created_by=created_by, kind="arc",
                title=f"Arc {i + 1}", status="outline",
            )
            async with pool.acquire() as c:
                await c.execute(
                    "UPDATE structure_node SET source='decompiled' WHERE id=$1", arc.id,
                )
            arc_id = arc.id
        arc_ids.append(arc_id)
        assigned += await repo.assign_chapters(book_id, arc_id, group)

    return {"arcs": len(arc_ids), "chapters_assigned": assigned, "arc_ids": [str(a) for a in arc_ids]}
