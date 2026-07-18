"""Work resolution (§6.2) — map a book to its composition Work.

Composition's `composition_work` table only stores MARKED works (marker-by-
presence). To tell "no Work yet but a book project exists" apart from "no book
project at all", resolution cross-references the knowledge-service projects for
the book (via the JWT-forwarding KnowledgeClient — see its module docstring).

This is the M2 slice the PO pulled forward from M3. It is router-free: it takes
the caller's `bearer` token as a plain parameter (the future M3/M7 router
extracts it from the request and passes it), so it is fully unit-testable with a
mock works-repo + mock knowledge-client.

§6.2 branches → WorkResolution.status:
  found              — exactly 1 marked Work (return it)
  candidates         — >1 marked Works (FE picks)
  unmarked_single    — 0 marked, exactly 1 book project (FE confirms → POST /work
                       ensures the marker; that ensure-create is M7)
  unmarked_candidates— 0 marked, >1 book projects (FE picks which to mark)
  none               — 0 marked, 0 book projects (FE offers create)
  unavailable        — knowledge-service unreachable (don't silent-thin, §13 C3a)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol
from uuid import UUID

from app.db.models import CompositionWork

ResolutionStatus = Literal[
    "found", "candidates", "unmarked_single", "unmarked_candidates",
    "none", "unavailable",
]


@dataclass(frozen=True)
class WorkResolution:
    status: ResolutionStatus
    work: CompositionWork | None = None
    works: list[CompositionWork] = field(default_factory=list)
    book_project_id: UUID | None = None
    book_project_ids: list[UUID] = field(default_factory=list)


class _WorksRepo(Protocol):
    async def resolve_by_book(self, book_id: UUID) -> list[CompositionWork]: ...


class _KnowledgeClient(Protocol):
    async def list_projects_for_book(
        self, book_id: UUID, bearer: str
    ) -> list[dict[str, Any]] | None: ...


def _book_project_ids(projects: list[dict[str, Any]], book_id: UUID) -> list[UUID]:
    """Non-archived knowledge projects linked to this book.

    Match on `book_id` ONLY — deliberately NOT on `project_type == 'book'`.
    Verified against the platform (2026-06-04): a book's real grounding project
    is bound by `book_id` alone (the editor AI panel resolves
    `listProjects({book_id, limit:1})` with no type filter, and the FE
    create-form defaults `project_type='general'`). Filtering by type here would
    miss that project and make POST /work create a DUPLICATE empty 'book'
    project — composition would then ground on an empty graph. So we mirror the
    platform's book_id-only binding."""
    out: list[UUID] = []
    for p in projects:
        if p.get("is_archived"):
            continue
        if str(p.get("book_id")) != str(book_id):
            continue
        pid = p.get("project_id")
        if pid is None:
            continue
        out.append(pid if isinstance(pid, UUID) else UUID(str(pid)))
    return out


async def resolve_work(
    book_id: UUID,
    *,
    bearer: str,
    works_repo: _WorksRepo,
    knowledge_client: _KnowledgeClient,
) -> WorkResolution:
    """Resolve a book to its Work per §6.2. See module docstring for branches.

    BOOK-driven, caller-independent (PM-9, spec 25): Work rows are per-book, so
    resolution takes no user id — the caller's access is decided upstream at the
    E0 book-grant gate. The `bearer` still forwards the CALLER's JWT to
    knowledge-service (actor identity, not scope)."""
    marked = await works_repo.resolve_by_book(book_id)
    if len(marked) == 1:
        return WorkResolution(status="found", work=marked[0])
    if len(marked) > 1:
        return WorkResolution(status="candidates", works=marked)

    # 0 marked → consult knowledge for book-typed projects.
    projects = await knowledge_client.list_projects_for_book(book_id, bearer)
    if projects is None:
        return WorkResolution(status="unavailable")

    book_ids = _book_project_ids(projects, book_id)
    if not book_ids:
        return WorkResolution(status="none")
    if len(book_ids) == 1:
        return WorkResolution(status="unmarked_single", book_project_id=book_ids[0])
    return WorkResolution(status="unmarked_candidates", book_project_ids=book_ids)
