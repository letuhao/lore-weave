"""Selectors for reading memory summaries from Postgres.

K6.2: reads go through the per-process TTL cache in app.context.cache
before falling through to SummariesRepo. Cache is write-through via
K6.3 — SummariesRepo.upsert/delete invalidate the matching key after
the DB write succeeds.
"""

from uuid import UUID

from app.context import cache
from app.db.models import Summary
from app.db.repositories.summaries import SummariesRepo

__all__ = ["load_global_summary"]


async def load_global_summary(
    repo: SummariesRepo, user_id: UUID
) -> Summary | None:
    """Return the user's global (L0) summary, or None if unset.

    Cache-first: hits the TTL cache before touching Postgres. The
    cache stores both positive hits and a MISSING sentinel for known
    absent rows, so repeated turns from a user without a bio don't
    re-query the DB.
    """
    cached = cache.get_l0(user_id)
    if cached is cache.MISSING:
        return None
    if cached is not None:
        return cached  # type: ignore[return-value]

    summary = await repo.get(user_id, "global", None)
    cache.put_l0(user_id, summary)
    return summary
