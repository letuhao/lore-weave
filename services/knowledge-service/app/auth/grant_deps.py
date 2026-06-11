"""E0-3 collaboration access layer for knowledge-service.

**Resolve-to-owner**: knowledge-service authorizes by project owner at the repo
layer (`WHERE user_id=$1`). To let a book collaborator reach a book's knowledge
project WITHOUT widening (and risking IDOR on) every repo query, these FastAPI
dependencies authorize the caller against the project's book grant and then hand
the repo the project's **owner** user_id. The repo runs unchanged as the owner;
the grant check is the single gate.

For a book-bound project ``project.user_id == book.owner_user_id`` (project
creation is book-owner-only), so ``require_project_grant(GrantLevel.OWNER)`` is
exactly owner-only, and a book-less project (book_id is None) is owner-only at
every tier (the R1 fallback).

Anti-oracle: a missing project, a non-grantee, and a book-less-non-owner all map
to **404** (uniform with the existing cross-user 404, KSA §6.4); a grantee under
the required tier gets **403**.
"""

from collections.abc import Awaitable, Callable
from typing import NamedTuple
from uuid import UUID

from fastapi import Depends, HTTPException, status

from app.clients.grant_client import GrantClient, GrantLevel
from app.db.repositories.extraction_jobs import ExtractionJobsRepo
from app.db.repositories.projects import ProjectsRepo
from app.deps import get_extraction_jobs_repo, get_grant_client, get_projects_repo
from app.middleware.jwt_auth import get_current_user

__all__ = [
    "GrantLevel",
    "Principals",
    "ProjectMeta",
    "project_meta_dep",
    "job_meta_dep",
    "require_project_grant",
    "require_project_principals",
    "require_book_grant",
    "require_job_grant",
]


class Principals(NamedTuple):
    """E0-3 Phase 2b — the two identities a project-scoped write needs under the
    BYOK dual-identity model. ``owner`` is the project owner (graph partition,
    project budget, canonical embedding tag); ``caller`` is the authenticated
    requester (their key + budget pay for provider calls). ``owner == caller``
    for an owner-triggered request (legacy single-identity path)."""

    owner: UUID
    caller: UUID

# (owner_user_id, book_id|None) — the two ids the grant gate needs. None means
# the project/job does not exist.
ProjectMeta = tuple[UUID, UUID | None]


async def project_meta_dep(
    project_id: UUID, repo: ProjectsRepo = Depends(get_projects_repo)
) -> ProjectMeta | None:
    """Resolve a project's (owner, book_id) — the authz bootstrap for
    ``/projects/{project_id}/…`` routes. A named dependency so tests can override
    it once (globally) instead of teaching every fake repo about project_meta."""
    return await repo.project_meta(project_id)


async def job_meta_dep(
    job_id: UUID,
    jobs: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
    repo: ProjectsRepo = Depends(get_projects_repo),
) -> ProjectMeta | None:
    """Resolve a job's project (owner, book_id) for ``/extraction/jobs/{job_id}…``
    routes, so a collaborator with grant on the project's book can watch its jobs."""
    project_id = await jobs.project_for_job(job_id)
    if project_id is None:
        return None
    return await repo.project_meta(project_id)


def _not_found() -> HTTPException:
    # Uniform with the repo's cross-user 404 — never leak a project/book's existence.
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")


def _forbidden() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient access")


async def _resolve_owner(
    caller: UUID, owner: UUID, book_id: UUID | None, need: GrantLevel, gc: GrantClient
) -> UUID:
    """Shared gate: return the project owner if the caller is the owner or holds
    >= need on the project's book; else raise 404/403. Fail-closed."""
    if caller == owner:
        return owner
    if book_id is None:
        raise _not_found()  # book-less project → owner-only (R1)
    lvl = await gc.resolve_grant(book_id, caller)
    if lvl == GrantLevel.NONE:
        raise _not_found()  # non-grantee → 404 (no existence oracle)
    if not lvl.at_least(need):
        raise _forbidden()  # has access, under tier → 403
    return owner


def require_project_grant(need: GrantLevel) -> Callable[..., Awaitable[UUID]]:
    """Dependency factory for ``/projects/{project_id}/…`` routes. Returns the
    project's **owner** user_id to pass to the repo (resolve-to-owner)."""

    async def _dep(
        meta: ProjectMeta | None = Depends(project_meta_dep),
        caller: UUID = Depends(get_current_user),
        gc: GrantClient = Depends(get_grant_client),
    ) -> UUID:
        if meta is None:
            raise _not_found()
        owner, book_id = meta
        return await _resolve_owner(caller, owner, book_id, need, gc)

    return _dep


def require_project_principals(
    need: GrantLevel,
) -> Callable[..., Awaitable[Principals]]:
    """E0-3 Phase 2b dependency factory for project writes that must bill the
    CALLER under BYOK (extraction). Same gate as ``require_project_grant`` (the
    caller must be owner or hold >= need on the project's book), but returns
    BOTH identities so the handler can partition graph/budget by the owner while
    billing provider calls to the caller. Fail-closed (404/403 via the gate)."""

    async def _dep(
        meta: ProjectMeta | None = Depends(project_meta_dep),
        caller: UUID = Depends(get_current_user),
        gc: GrantClient = Depends(get_grant_client),
    ) -> Principals:
        if meta is None:
            raise _not_found()
        owner, book_id = meta
        # Reuse the exact gate (raises 404/403); discard the returned owner —
        # we already have it — and pair it with the caller.
        await _resolve_owner(caller, owner, book_id, need, gc)
        return Principals(owner=owner, caller=caller)

    return _dep


def require_book_grant(need: GrantLevel) -> Callable[..., Awaitable[UUID]]:
    """Dependency factory for book-scoped routes (``/books/{book_id}/…``). Returns
    the caller's id (the route operates on book-scoped data, not owner-substituted).
    Use for raw-search etc. where the path carries ``book_id`` directly."""

    async def _dep(
        book_id: UUID,
        caller: UUID = Depends(get_current_user),
        gc: GrantClient = Depends(get_grant_client),
    ) -> UUID:
        lvl = await gc.resolve_grant(book_id, caller)
        if lvl == GrantLevel.NONE:
            raise _not_found()
        if not lvl.at_least(need):
            raise _forbidden()
        return caller

    return _dep


def require_job_grant(need: GrantLevel) -> Callable[..., Awaitable[UUID]]:
    """Dependency factory for job-scoped routes (``/extraction/jobs/{job_id}…``).
    Resolves the job's project, then applies the project gate so a collaborator with
    grant on the project's book can watch its jobs. Returns the project owner."""

    async def _dep(
        meta: ProjectMeta | None = Depends(job_meta_dep),
        caller: UUID = Depends(get_current_user),
        gc: GrantClient = Depends(get_grant_client),
    ) -> UUID:
        if meta is None:
            raise _not_found()
        owner, book_id = meta
        return await _resolve_owner(caller, owner, book_id, need, gc)

    return _dep
