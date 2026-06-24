"""World rollup — shared membership/project-id resolution.

Both world rollups (the W2 graph subgraph and the D-WORLD-TIMELINE-ROLLUP
timeline) read the SAME set of knowledge partitions: the world-level (bible)
project plus each member book's own canonical project. This helper resolves
that set once so the two unions can never drift apart.

Owner-scoped + partition-safe: membership comes from book-service's internal
``/internal/worlds/{id}/books`` route (keyed by ``user_id``); a project owned by
someone else (a book shared into the world) is skipped — we can't read another
user's partition, so it would contribute nothing anyway (M0: shared-book rollup
is out of scope). We never trust a client-supplied book/project list.
"""

from __future__ import annotations

from uuid import UUID

from app.clients.book_client import BookClient
from app.db.repositories.projects import ProjectsRepo


async def resolve_world_project_ids(
    *,
    world_id: UUID,
    user_id: UUID,
    repo: ProjectsRepo,
    book: BookClient,
) -> list[str]:
    """Return the project_ids that roll up into ``world_id`` for ``user_id``.

    Raises ``WorldNotFound`` / ``BookServiceUnavailable`` (from
    ``book.list_world_books``); the caller maps those to 404 / 503. The result
    is deduped (the world-level project IS the bible book's project, so it would
    otherwise appear twice) and order-stable (world-level first, then members).
    """
    member_books = await book.list_world_books(world_id, user_id)

    project_ids: list[str] = []
    seen: set[str] = set()

    # The world-level (bible) project — the world's own authored-lore partition.
    for p in await repo.list(user_id, world_id=world_id, limit=100):
        pid = str(p.project_id)
        if pid not in seen:
            seen.add(pid)
            project_ids.append(pid)

    # Each member book's canonical project (own-partition; ``get_by_book``
    # excludes ``is_derivative`` — dị bản branches stay out of the canon rollup).
    for b in member_books:
        bid = b.get("book_id")
        if not bid:
            continue
        bp = await repo.get_by_book(UUID(str(bid)))
        if bp is not None and bp.user_id == user_id:
            pid = str(bp.project_id)
            if pid not in seen:
                seen.add(pid)
                project_ids.append(pid)

    return project_ids
