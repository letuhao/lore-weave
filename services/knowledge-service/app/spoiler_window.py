"""T2.1 — spoiler-window resolution shared by the Cast & Codex reads.

A book chapter_id → the inclusive reading-axis ceiling so status / facts / events
can be windowed to "everything established through the current chapter, nothing
after". The reading axis is ``event_order`` = ``chapter_sort_order ×
EVENT_ORDER_CHAPTER_STRIDE + within_chapter_idx`` (pass2_writer), so the ceiling
for chapter with sort_order ``s`` is ``(s + 1) × STRIDE − 1`` — it covers all of
chapter ``s`` (idx 0..STRIDE-1) and excludes chapter ``s+1`` onward.

**FAIL-CLOSED** is the whole point: if book-service can't resolve the chapter
(down, unknown id, outside any active job's range), we return a *restrictive*
window (``-1`` → no events/facts pass; status defaults ``active``) + ``available=
False`` so the FE can say "couldn't pin the reading position" rather than silently
leaking future reveals. This deliberately INVERTS ``book_client.get_chapter_sort_
orders``' own fail-OPEN posture (which over-ingests on failure — correct for
ingestion, wrong for a spoiler gate).
"""

from __future__ import annotations

from uuid import UUID

from app.clients.book_client import BookClient
from app.db.neo4j_repos.events import EVENT_ORDER_CHAPTER_STRIDE

# The restrictive window used when the chapter order can't be resolved: nothing
# has from_order <= -1 (orders are >= 0), so status → all 'active', no events/facts.
FAIL_CLOSED_BEFORE_ORDER = -1


async def resolve_before_order(
    book_client: BookClient, chapter_id: UUID | None,
) -> tuple[int, bool]:
    """Return ``(before_order, available)``. See module docstring."""
    if chapter_id is None:
        return FAIL_CLOSED_BEFORE_ORDER, False
    sort_orders = await book_client.get_chapter_sort_orders([chapter_id])
    sort_order = sort_orders.get(chapter_id)
    if sort_order is None:
        return FAIL_CLOSED_BEFORE_ORDER, False
    return (sort_order + 1) * EVENT_ORDER_CHAPTER_STRIDE - 1, True
