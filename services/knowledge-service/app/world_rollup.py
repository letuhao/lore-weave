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

from dataclasses import dataclass
from uuid import UUID

from app.clients.book_client import BookClient
from app.db.repositories.projects import ProjectsRepo


@dataclass(frozen=True)
class WorldPartitions:
    """A world's READABLE KG partitions for a user, plus how many member-book
    partitions were skipped because the caller doesn't own them.

    ``project_ids`` = world-level (bible) project(s) + each OWNED member book's
    canonical project (deduped, order-stable: world-level first). ``unreadable_count``
    = member books whose canonical project EXISTS but is owned by someone else (a book
    shared into the world we cannot read). EC-B2: the agent tool REPORTS this rather
    than dropping partitions silently. Books with no canonical KG contribute no
    partition and are NOT counted (they'd add nothing anyway)."""

    project_ids: list[str]
    unreadable_count: int


async def resolve_world_partitions(
    *,
    world_id: UUID,
    user_id: UUID,
    repo: ProjectsRepo,
    book: BookClient,
) -> WorldPartitions:
    """Resolve a world's readable KG partitions for ``user_id`` + the unreadable count.

    Raises ``WorldNotFound`` / ``BookServiceUnavailable`` (from ``book.list_world_books``);
    the caller maps those (endpoints → 404/503; the MCP tool → a self-correcting error).
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

    # Each member book's canonical project (own-partition; ``get_by_book`` excludes
    # ``is_derivative`` — dị bản branches stay out of the canon rollup).
    unreadable = 0
    for b in member_books:
        bid = b.get("book_id")
        if not bid:
            continue
        bp = await repo.get_by_book(UUID(str(bid)))
        if bp is None:
            continue  # no canonical KG → no partition (not "unreadable")
        if bp.user_id == user_id:
            pid = str(bp.project_id)
            if pid not in seen:
                seen.add(pid)
                project_ids.append(pid)
        else:
            unreadable += 1  # exists but another user owns it → an unreadable partition (EC-B2)

    return WorldPartitions(project_ids=project_ids, unreadable_count=unreadable)


async def resolve_world_project_ids(
    *,
    world_id: UUID,
    user_id: UUID,
    repo: ProjectsRepo,
    book: BookClient,
) -> list[str]:
    """Backward-compat shim: just the readable project_ids (byte-identical to the prior
    behaviour). The two world-rollup ENDPOINTS (subgraph, timeline) don't surface the
    unreadable count; the agent MCP tool uses ``resolve_world_partitions`` for the
    EC-B2 report."""
    partitions = await resolve_world_partitions(
        world_id=world_id, user_id=user_id, repo=repo, book=book
    )
    return partitions.project_ids
