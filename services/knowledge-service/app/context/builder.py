"""Top-level context dispatcher.

build_context() inspects the request and routes to the right Mode
builder.

  - project_id is None                     → Mode 1 (no_project, K4.7)
  - project exists, extraction disabled    → Mode 2 (static, K4.9)
  - project exists, extraction enabled     → Mode 3 (full, Track 2)
                                              → NotImplementedError
  - project doesn't exist OR cross-user    → ProjectNotFound
                                              → router maps to 404

The dispatcher is the one place that fetches the Project — Mode
builders receive it already-validated so they don't have to worry
about ownership checks.
"""

from uuid import UUID

from app.clients.glossary_client import GlossaryClient
from app.context.modes.no_project import BuiltContext, build_no_project_mode
from app.context.modes.static import build_static_mode
from app.db.repositories.projects import ProjectsRepo
from app.db.repositories.summaries import SummariesRepo

__all__ = ["ProjectNotFound", "build_context"]


class ProjectNotFound(Exception):
    """Raised when `project_id` doesn't match a project owned by `user_id`.

    Either the project doesn't exist or it belongs to another user. The
    router catches this and returns 404 — we deliberately don't
    distinguish the two cases to avoid a project-enumeration oracle.
    """


async def build_context(
    summaries_repo: SummariesRepo,
    projects_repo: ProjectsRepo,
    glossary_client: GlossaryClient,
    *,
    user_id: UUID,
    project_id: UUID | None,
    message: str,
) -> BuiltContext:
    if project_id is None:
        return await build_no_project_mode(summaries_repo, user_id)

    project = await projects_repo.get(user_id, project_id)
    if project is None:
        raise ProjectNotFound()

    if project.extraction_enabled:
        raise NotImplementedError(
            "Mode 3 (full extraction) is Track 2 scope"
        )

    return await build_static_mode(
        summaries_repo,
        glossary_client,
        user_id=user_id,
        project=project,
        message=message,
    )
