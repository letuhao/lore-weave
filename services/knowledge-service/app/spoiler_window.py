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
# T17 A5 — the reading-axis stride is a fact about the BOOK, so it comes from the domain
# and not from a graph engine. This module computes a spoiler ceiling and touches no
# Cypher at all; importing it from `neo4j_repos` made it count as bound to the concrete
# layer, which was both untrue and indistinguishable — to `port-adoption-gate` — from a
# module that really does need Neo4j.
from app.domain.graph_models import EVENT_ORDER_CHAPTER_STRIDE

# The restrictive window used when the chapter order can't be resolved: nothing
# has from_order <= -1 (orders are >= 0), so status → all 'active', no events/facts.
FAIL_CLOSED_BEFORE_ORDER = -1

# The passage-axis analogue (W11-M1): passages carry ``chapter_index`` = the
# chapter's sort_order, so a passage is visible iff ``chapter_index <=
# before_sort_order``. -1 is restrictive (no passage has chapter_index <= -1).
FAIL_CLOSED_BEFORE_SORT_ORDER = -1


# ── Q8 / D-T32-REVEAL-AXIS — the reveal position, one concept ─────────────────
#
# The spoiler window and the author-curation opt-out were TWO query flags saying one
# thing: how far into the story is this reader allowed to see?
#
#   before_chapter_id=<uuid>   reader — window through that chapter (fail-closed)
#   curation=true              author — no window at all
#
# Two parameters for one axis is how they drift: `curation=true` had to document
# *"when true, before_chapter_id is ignored"*, which is a precedence rule that exists
# only because there are two of them. Q8 (SEALED 2026-08-09) collapses them into
# **"read at reveal position P"**, and the register records the reason: it removes a
# fail-open class — an author view that fails CLOSED renders empty, which is what made
# the opt-out necessary in the first place.
#
# Three states, one parameter:
#
#   absent          → FAIL-CLOSED. A reader with no established position sees nothing.
#   <chapter uuid>  → the reader window through that chapter.
#   "all"           → the unbounded author read, INCLUDING facts with no position at
#                     all. That last clause is why "all" is not simply "+infinity":
#                     an author-written fact carries no `from_order`, so no finite
#                     ceiling ever admits it. Unplaced means "no reveal point", and
#                     only the unbounded read has room for it.
REVEAL_ALL = "all"


def parse_reveal_at(
    reveal_at: str | None, *, before_chapter_id: UUID | None, curation: bool,
) -> tuple[str | None, UUID | None]:
    """Resolve the reveal position from the new parameter and the two legacy flags.

    Returns ``(mode, chapter_id)`` where `mode` is ``"all"``, ``"chapter"`` or ``None``
    (fail-closed).

    The legacy flags are ACCEPTED and mapped rather than removed: the FE ships against
    them today, and a hard cut would break a live surface to prove a point about naming.
    `reveal_at` WINS when both are supplied — a caller that has migrated is stating the
    position it means, and silently preferring the old flag would make the migration
    unobservable.
    """
    if reveal_at is not None:
        value = reveal_at.strip().lower()
        if value == REVEAL_ALL:
            return REVEAL_ALL, None
        try:
            return "chapter", UUID(reveal_at.strip())
        except (ValueError, AttributeError):
            return None, None          # unparseable ⇒ fail-closed, never fail-open
    if curation:
        return REVEAL_ALL, None
    if before_chapter_id is not None:
        return "chapter", before_chapter_id
    return None, None


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


async def resolve_before_sort_order(
    book_client: BookClient, chapter_id: UUID | None,
) -> tuple[int, bool]:
    """Return ``(before_sort_order, available)`` — the cutoff chapter's OWN
    sort_order, the passage-axis cutoff (W11-M1, spec §4.3). This is the reader
    spoiler ceiling for RAG passages (which are chapter-, not event-, ordered).

    Same **FAIL-CLOSED** contract as ``resolve_before_order``: an omitted /
    unresolvable chapter → ``(-1, False)`` so the passage filter keeps nothing,
    rather than leaking a book's whole search corpus to a reader whose position
    couldn't be pinned. Inverts ``get_chapter_sort_orders``' fail-OPEN posture,
    exactly as ``resolve_before_order`` does for the event axis."""
    if chapter_id is None:
        return FAIL_CLOSED_BEFORE_SORT_ORDER, False
    sort_orders = await book_client.get_chapter_sort_orders([chapter_id])
    sort_order = sort_orders.get(chapter_id)
    if sort_order is None:
        return FAIL_CLOSED_BEFORE_SORT_ORDER, False
    return sort_order, True
