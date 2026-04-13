"""Selectors for reading project (L1) context from Postgres.

Thin wrappers on ProjectsRepo + SummariesRepo so the Mode builders
don't have to juggle both directly. Every call enforces the
user_id filter (security is at the repo level, but selectors
re-assert the pattern in their signatures).
"""

from uuid import UUID

from app.context import cache
from app.db.models import Project, Summary
from app.db.repositories.projects import ProjectsRepo
from app.db.repositories.summaries import SummariesRepo

__all__ = ["load_project", "load_project_summary"]


async def load_project(
    repo: ProjectsRepo, user_id: UUID, project_id: UUID
) -> Project | None:
    """Return the project if the user owns it, else None.

    ProjectsRepo.get filters by user_id internally, so a cross-user
    lookup returns None. The caller treats None as 'not found' and
    surfaces a 404.
    """
    return await repo.get(user_id, project_id)


async def load_project_summary(
    repo: SummariesRepo, user_id: UUID, project_id: UUID
) -> Summary | None:
    """Return the project-level L1 summary, or None if not set.

    Cache-first via app.context.cache (K6.2). K6.3 invalidates on
    write from SummariesRepo.upsert/delete so same-process updates
    are immediately visible.
    """
    cached = cache.get_l1(user_id, project_id)
    if cached is cache.MISSING:
        return None
    if cached is not None:
        return cached  # type: ignore[return-value]

    summary = await repo.get(user_id, "project", project_id)
    cache.put_l1(user_id, project_id, summary)
    return summary
