"""Top-level context dispatcher.

build_context() inspects the request and routes to the right Mode
builder.

  - project_id is None                     → Mode 1 (no_project, K4.7)
  - project exists, extraction disabled    → Mode 2 (static, K4.9)
  - project exists, extraction enabled     → Mode 3 (full, K18.x)
  - project doesn't exist OR cross-user    → ProjectNotFound
                                              → router maps to 404

The dispatcher is the one place that fetches the Project — Mode
builders receive it already-validated so they don't have to worry
about ownership checks.

K18.8: Mode 3 now flipped on. Callers must supply an `embedding_client`
if they want the L3 passage layer to function — a `None` value makes
Mode 3 run without L3 (empty `<passages>` block), which is still a
valid block.
"""

from uuid import UUID

from app.clients.embedding_client import EmbeddingClient
from app.clients.glossary_client import GlossaryClient
from app.clients.llm_client import LLMClient
from app.context.modes.full import build_full_mode
from app.context.modes.multi_project import build_multi_project_mode
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
    embedding_client: EmbeddingClient | None = None,
    llm_client: LLMClient | None = None,
    language: str | None = None,
    entity_access_repo=None,
    project_ids: list[UUID] | None = None,
    grounding: bool = True,
) -> BuiltContext:
    # Track B B1(2) — normalize the requested project set. `project_ids` (multi-KG)
    # takes precedence; else the single `project_id` (back-compat). Order-preserving
    # dedup; owner-scoped resolution below filters stale/foreign ids (the caller owns
    # the set, so a deleted id is skipped, not fatal — unless NONE resolve).
    ids: list[UUID] = list(project_ids) if project_ids else ([project_id] if project_id else [])
    _seen: set[UUID] = set()
    ids = [i for i in ids if not (i in _seen or _seen.add(i))]

    if not ids:
        return await build_no_project_mode(summaries_repo, user_id)

    resolved = []
    for pid in ids:
        p = await projects_repo.get(user_id, pid)
        if p is not None:
            resolved.append(p)

    if not resolved:
        # None of the requested projects exist for this user (all stale/foreign).
        raise ProjectNotFound()

    # T5 (Context Budget Law D2) — grounding intent gate. chat-service decided this
    # turn references NO book lore (entity-presence heuristic), so skip the EXPENSIVE
    # retrieval (passage vector search + semantic glossary + LLM summarization) and
    # serve the LIGHT project-aware path (static: glossary badges + summaries +
    # instruction, no vectors/LLM). The always-on story_state block (chat-side, D4)
    # remains the safety net, so a false-negative gate never strips loaded lore. For
    # a multi-KG union we serve the light path for the first resolved project (the
    # union's expensive cross-project rank is exactly what the gate is skipping).
    if not grounding:
        return await build_static_mode(
            summaries_repo,
            glossary_client,
            user_id=user_id,
            project=resolved[0],
            message=message,
            language=language,
            entity_access_repo=entity_access_repo,
        )

    if len(resolved) >= 2:
        # ≥2 readable projects → the multi-KG union (shared budget, cross-project
        # dedup + rank). A static (no-graph) member contributes glossary only; the
        # L2/L3 selectors degrade to empty for it.
        return await build_multi_project_mode(
            summaries_repo,
            glossary_client,
            user_id=user_id,
            projects=resolved,
            message=message,
            embedding_client=embedding_client,
            llm_client=llm_client,
            language=language,
            entity_access_repo=entity_access_repo,
        )

    project = resolved[0]
    if project.extraction_enabled:
        return await build_full_mode(
            summaries_repo,
            glossary_client,
            user_id=user_id,
            project=project,
            message=message,
            embedding_client=embedding_client,
            llm_client=llm_client,
            language=language,
            entity_access_repo=entity_access_repo,
        )

    return await build_static_mode(
        summaries_repo,
        glossary_client,
        user_id=user_id,
        project=project,
        message=message,
        language=language,
        entity_access_repo=entity_access_repo,
    )
