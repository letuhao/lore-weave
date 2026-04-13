"""Top-level context dispatcher.

build_context() inspects the request and routes to the right Mode
builder. For Track 1 K4a we only implement Mode 1 (no project). Mode 2
lands in K4b and raises NotImplementedError until then. Mode 3 (full
extraction) is Track 2 scope and will raise NotImplementedError
indefinitely until the extraction pipeline exists.
"""

from uuid import UUID

from app.context.modes.no_project import BuiltContext, build_no_project_mode
from app.db.repositories.summaries import SummariesRepo

__all__ = ["build_context"]


async def build_context(
    summaries_repo: SummariesRepo,
    user_id: UUID,
    project_id: UUID | None,
) -> BuiltContext:
    """Dispatch to the correct mode builder.

    Rules:
      - project_id is None → Mode 1 (no_project)
      - project_id is set  → Mode 2 (static) — K4b
      - extraction_enabled → Mode 3 (full) — Track 2

    For K4a, any project_id raises NotImplementedError. chat-service
    handles the 501 gracefully and falls back to its 50-message replay.
    """
    if project_id is None:
        return await build_no_project_mode(summaries_repo, user_id)
    raise NotImplementedError(
        "context build for projects (Mode 2) is implemented in K4b"
    )
