"""Selectors for reading memory summaries from Postgres.

K4a (Mode 1) only needs the global (L0) loader — project (L1) comes in
K4b. This module owns the query shape so the Mode builders never touch
the repository directly.
"""

from uuid import UUID

from app.db.models import Summary
from app.db.repositories.summaries import SummariesRepo

__all__ = ["load_global_summary"]


async def load_global_summary(
    repo: SummariesRepo, user_id: UUID
) -> Summary | None:
    """Return the user's global (L0) summary, or None if unset.

    Thin wrapper over SummariesRepo.get(user_id, 'global', None). Lives
    in the selectors layer so the Mode builders never import the
    repository directly — makes future Track-2 caching trivial.
    """
    return await repo.get(user_id, "global", None)
