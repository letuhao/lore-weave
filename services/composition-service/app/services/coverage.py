"""Coverage diff — the ONE "which manuscript chapters has the spec not planned?"
computation (28 OQ-4 / NC-1, sealed 2026-07-10).

    "The coverage diff (unplanned chapters) is a separate, cheaper computation:
     one composition-side helper shared by 24 H1.3's overlay and AN-4."

Two consumers, one implementation — never a second computation:
  • 24 H1.3 `GET /books/{book_id}/plan-overlay` → the PH21 "Unplanned chapters" tray
  • 28 AN-4 `composition_diagnostics` → source (5), severity `info`

Why it is server-side (and why the first cut of H1.3 returning `[]` was wrong):
`24` SC11/PH12 rejects a cross-service **server join** for the per-node two-truths
render — that is a per-node actual-state lookup across thousands of canvas nodes, and
it stays client-side. This is a different animal: ONE bounded set-difference over the
chapter spine, read through the existing internal book client (the `pack.py`
precedent, 28 F-A7/AN-2). And an MCP tool cannot compose an FE-side computation at
all, so a client-only tray could never have satisfied AN-4's "composes, never
recomputes".

Degradation posture (AN-2, verbatim: "absent + a warning, never zero-faked"):
book-service unreachable ⇒ `degraded=True` and the caller OMITS the key. An empty
list would read as "nothing unplanned" — a green-looking zero over an unknown, which
is the `fe-status-default-fallback-signals-backend-field-omission` bug class and the
same absent≠zero law 24 OQ-8 applies to drift.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.clients.book_client import BookClient, BookClientError
from app.db.repositories.outline import OutlineRepo

logger = logging.getLogger(__name__)

# OUT-5: refs capped, counts EXACT. A never-planned 10k-chapter book would otherwise
# put 10k rows in a decorations payload whose whole point is to be small. The tray is
# a "you have drift" signal, not a chapter browser — it renders the first page and
# says how many more there are.
UNPLANNED_CAP = 200

# A title is a short label here, never prose.
_TITLE_MAX = 160


# The manuscript spine read must be EXHAUSTIVE, or `unplanned_count` is a lie. `list_chapters`'s
# `limit` is a real ceiling (it truncates silently), so we ask for more than any real book and then
# CHECK whether we hit it — an upstream truncation that quietly caps the count would make the whole
# exact-count-vs-capped-list contract below meaningless (the classic "a normalization upstream makes
# the defense downstream moot" bug).
_SPINE_LIMIT = 100_000


@dataclass(frozen=True)
class Coverage:
    """The diff, plus its honest partiality flags.

    `degraded=True` means the manuscript spine could not be read — `unplanned` is
    then meaningless and MUST NOT be rendered as an empty tray. Callers omit the key
    and surface `warning`.

    `spine_truncated=True` means we DID read the spine but hit the ceiling, so
    `unplanned_count` is a LOWER BOUND, not the exact figure it normally is. The two
    flags are different facts and the caller renders them differently.
    """

    unplanned: list[dict[str, Any]] = field(default_factory=list)
    # EXACT — unless `spine_truncated`, in which case it is a floor.
    unplanned_count: int = 0
    unplanned_capped: bool = False
    degraded: bool = False
    spine_truncated: bool = False
    warning: str | None = None


def _title(text: str | None) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= _TITLE_MAX else t[: _TITLE_MAX - 1].rstrip() + "…"


def diff_coverage(
    book_chapters: list[dict[str, Any]],
    planned_chapter_ids: set[UUID],
    *,
    spine_truncated: bool = False,
) -> Coverage:
    """PURE — the set difference itself, unit-tested without a DB or a network.

    `book_chapters` is book-service's ACTIVE spine in reading order; a chapter is
    UNPLANNED iff no active spec chapter node points at it. Ordering is preserved
    (the spine is already `sort_order, created_at`), so the tray reads in book order.
    """
    planned = {str(cid) for cid in planned_chapter_ids}
    unplanned: list[dict[str, Any]] = []
    count = 0
    for ch in book_chapters:
        raw = ch.get("chapter_id")
        if raw is None or str(raw) in planned:
            continue
        count += 1
        if len(unplanned) < UNPLANNED_CAP:
            unplanned.append({
                "chapter_id": str(raw),
                "title": _title(ch.get("title")),
                "sort_order": ch.get("sort_order"),
            })
    return Coverage(
        unplanned=unplanned,
        unplanned_count=count,
        unplanned_capped=count > len(unplanned),
        spine_truncated=spine_truncated,
    )


async def compute_coverage(
    book_id: UUID, bearer: str, *, book: BookClient, outline: OutlineRepo,
) -> Coverage:
    """Read both spines and diff them.

    The caller MUST have gated the book already (E0 VIEW) — this issues a
    bearer-forwarded chapter list, so book-service re-checks anyway, but the
    no-oracle 404 is the route's job, not ours.

    `raise_on_404=True` is load-bearing: `list_chapters` otherwise swallows a 404
    into `[]`, and THIS caller reasons about ABSENCE. A book that 404s (trashed
    mid-request, a grant/book-service skew) would come back "0 chapters" and the
    diff would report `unplanned = []` — "nothing is unplanned" — over a book we
    could not read at all. That is exactly the green-looking zero this module
    exists to prevent, arriving through the back door.
    """
    try:
        chapters = await book.list_chapters(
            book_id, bearer, limit=_SPINE_LIMIT, raise_on_404=True,
        )
    except BookClientError as exc:
        logger.warning("coverage diff degraded — book spine unreadable: %s", exc)
        return Coverage(
            degraded=True,
            warning=(
                "the manuscript chapter list could not be read, so unplanned "
                "chapters are unknown for this book (not zero)"
            ),
        )
    # Hitting the ceiling means the spine itself was cut short, so the count below is a FLOOR.
    # Say so rather than presenting a truncated number as the exact one.
    spine_truncated = len(chapters) >= _SPINE_LIMIT
    if spine_truncated:
        logger.warning("coverage diff: book %s spine hit the %d ceiling", book_id, _SPINE_LIMIT)
    planned = await outline.planned_chapter_ids(book_id)
    return diff_coverage(chapters, planned, spine_truncated=spine_truncated)


@dataclass(frozen=True)
class ProseDeleted:
    """26 IX-13 — spec nodes whose chapter no longer exists.

    The INVERSE of the coverage diff: coverage finds chapters with no plan; this finds plan nodes
    pointing at a chapter that has been deleted or trashed. IX-13's law is that the spec SURVIVES a
    prose delete (deleting actual state must never destroy desired state) — so these nodes are real,
    authored, and now dangling, and the author must re-link or archive them explicitly.

    ERROR severity, and that is why omitting it silently was the bug: it is the highest-severity
    class the problems panel has.
    """

    nodes: list[dict[str, Any]] = field(default_factory=list)
    count: int = 0
    degraded: bool = False
    warning: str = ""


async def compute_prose_deleted(
    book_id: UUID, bearer: str, *, book: BookClient, outline: OutlineRepo,
) -> ProseDeleted:
    """Spec nodes whose `chapter_id` no longer resolves to an active chapter.

    A TRUNCATED spine makes this UNANSWERABLE, and saying so is the whole point. If the chapter list
    hit its ceiling, a node whose chapter simply lies beyond the cut would be indistinguishable from
    one whose chapter was deleted — and we would tell the author that a chapter they are still
    writing has been destroyed. That is the `paged-join-against-complete-set-mislabels-not-yet-loaded-
    as-absent` bug, and it is far worse here than a missing answer: the remedy for a prose-deleted
    node is to ARCHIVE it.
    """
    try:
        chapters = await book.list_chapters(
            book_id, bearer, limit=_SPINE_LIMIT, raise_on_404=True,
        )
    except BookClientError as exc:
        logger.warning("prose-deleted scan degraded — book spine unreadable: %s", exc)
        return ProseDeleted(
            degraded=True,
            warning=(
                "the manuscript chapter list could not be read, so prose-deleted spec nodes "
                "are unknown for this book (not zero)"
            ),
        )
    if len(chapters) >= _SPINE_LIMIT:
        return ProseDeleted(
            degraded=True,
            warning=(
                f"this book's chapter spine exceeds the {_SPINE_LIMIT} read ceiling, so a node "
                "whose chapter lies beyond the cut cannot be told apart from one whose chapter was "
                "deleted — prose-deleted nodes are UNKNOWN, not zero"
            ),
        )

    active = {str(c["chapter_id"]) for c in chapters if c.get("chapter_id")}
    linked = await outline.linked_chapter_nodes(book_id)
    dangling = [n for n in linked if str(n["chapter_id"]) not in active]
    return ProseDeleted(nodes=dangling, count=len(dangling))
