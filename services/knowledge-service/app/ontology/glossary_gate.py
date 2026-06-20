"""Shared adopt glossary-gate resolution (KM6-M2).

The M1 adopt-gate needs the project's glossary node-kind source (book ontology when the
project has a book, else the owner's glossary standards) so `OntologyMutationsRepo.adopt`
can block on a missing *required* kind. This resolution is shared by the human adopt
route (`routers/public/ontology.py`) and the agent confirm effect (`adopt_effect.py`) —
one source so the gate semantics can't drift between the two paths.

Fail-OPEN on a glossary outage: if the glossary source is unavailable we cannot prove a
required kind is missing, so we feed the source's own required kinds back in (treated as
present) rather than false-gate; a genuine runtime mismatch parks to triage later.
"""

from __future__ import annotations

from uuid import UUID

from app.clients.glossary_ontology_client import GlossaryOntologyClient
from app.db.repositories.ontology_mutations import OntologyMutationsRepo
from app.db.repositories.projects import ProjectsRepo

__all__ = ["resolve_adopt_glossary_codes"]


async def resolve_adopt_glossary_codes(
    projects: ProjectsRepo,
    glossary: GlossaryOntologyClient,
    mutations: OntologyMutationsRepo,
    *,
    owner: UUID,
    project_id: str,
    source_schema_id: UUID,
) -> tuple[str | None, set[str]]:
    """Return ``(book_id, glossary_codes)`` for the adopt-gate.

    A project with a book resolves the book ontology; a book-less project resolves the
    owner's glossary standards. A glossary outage → the source's own required kinds
    (fail-open, no false gate). An unknown project → ``(None, set())`` (the gate then
    blocks on any required kind — the caller maps that to a clear error)."""
    try:
        meta = await projects.project_meta(UUID(project_id))
    except (ValueError, TypeError):
        meta = None
    if meta is None:
        return None, set()

    _owner, book_uuid = meta
    book_id: str | None = None
    if book_uuid is not None:
        book_id = str(book_uuid)
        kinds = await glossary.get_book_ontology(book_uuid, owner)
    else:
        kinds = await glossary.get_user_standards(owner)

    if kinds is not None:
        return book_id, set(kinds.codes())
    # Glossary unavailable — fail open (treat the source's required kinds as present).
    return book_id, set(await mutations.required_node_kinds(source_schema_id))
