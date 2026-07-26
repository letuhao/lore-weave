"""OntologyResolver — the cached resolve seam for extraction/query/validation.

Wraps `GraphSchemasRepo.resolve_for_project` with a short-TTL in-process cache
(resolution is called per-extraction-call; a 30s TTL collapses the repeated DB
reads of one extraction run while staying fresh enough that an adopt/sync is
picked up almost immediately — callers may also `invalidate(project_id)` right
after a mutation).

It also resolves the **node-kind source** (spec §3.5 / M1): the resolved schema
declares *expected* node-kinds (`kg_schema_node_kinds`), but the SSOT for which
kinds actually exist is glossary. So the resolver cross-checks the schema's
node-kinds against the glossary source:

  * project has a ``book_id`` → book ontology (glossary `/internal/books/...`);
  * else (translation/code/general) → the user's glossary standards.

The result (`ResolvedNodeKinds`) exposes the schema-expected kinds (code +
strength) and the set actually present in glossary, so a *missing* expected
kind is detectable (the adopt-gate / triage in LC/LH/LH consume this — this
lane only computes it, never blocks).

TENANCY CONTRACT: ``resolve(project_id)`` acts on the caller's behalf. The
eventual router grant-gates the project before calling (mirrors
`GraphSchemasRepo.resolve_for_project`'s docstring). This resolver does NOT
grant-check and never mutates anything.

Spec: docs/specs/2026-06-20-knowledge-graph-customizable-ontology.md §3.5, M1.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from uuid import UUID

from app.clients.glossary_ontology_client import GlossaryOntologyClient
from app.db.ontology_models import ResolvedSchema, SchemaNodeKind
from app.db.repositories.graph_schemas import GraphSchemasRepo
from app.db.repositories.projects import ProjectsRepo

__all__ = ["ResolvedNodeKinds", "OntologyResolver"]

_DEFAULT_TTL_S = 30.0


@dataclass(frozen=True)
class ResolvedNodeKinds:
    """The schema's expected node-kinds cross-checked against glossary (M1).

    ``expected`` are the schema's ``kg_schema_node_kinds`` rows (code +
    strength). ``glossary_codes`` is the kind set the glossary source returns
    (``None`` when the source was unavailable — distinct from "empty set", so a
    caller never mistakes glossary-down for "no kinds"). ``source`` records
    which variant resolved (``book`` / ``user_standards`` / ``unavailable``).
    """

    expected: list[SchemaNodeKind]
    glossary_codes: frozenset[str] | None
    source: str
    book_id: UUID | None = None

    @property
    def expected_codes(self) -> frozenset[str]:
        return frozenset(nk.kind_code for nk in self.expected)

    def missing(self, *, strength: str | None = None) -> frozenset[str]:
        """Expected kinds absent from glossary (optionally filtered by strength).

        Empty when the glossary source was unavailable — a missing-source can't
        prove absence, so we report nothing missing rather than a false gate.
        """
        if self.glossary_codes is None:
            return frozenset()
        wanted = [
            nk.kind_code
            for nk in self.expected
            if strength is None or nk.strength == strength
        ]
        return frozenset(c for c in wanted if c not in self.glossary_codes)


@dataclass
class _CacheEntry:
    schema: ResolvedSchema
    expires_at: float


@dataclass
class OntologyResolver:
    """Per-process cached resolver. Construct once (lifespan), share per request.

    The cache is keyed by ``project_id`` with a short TTL; ``invalidate`` clears
    one project (call after an adopt/sync/CRUD so the next resolve is fresh).
    Node-kind source resolution is NOT cached here — it is a cross-service read
    the glossary client itself is responsible for caching (D1 "read-hot →
    cache"), and it is only needed at adopt/triage time, not the extraction hot
    loop.
    """

    schemas: GraphSchemasRepo
    projects: ProjectsRepo
    glossary: GlossaryOntologyClient
    ttl_s: float = _DEFAULT_TTL_S
    _cache: dict[str, _CacheEntry] = field(default_factory=dict)

    async def resolve(self, project_id: str) -> ResolvedSchema:
        """The effective schema for a project (cached, §3.5).

        Returns the merged project-active-else-`general` schema. Cache hit
        within the TTL skips the DB round-trip; a miss/expiry repopulates.
        """
        now = time.monotonic()
        entry = self._cache.get(project_id)
        if entry is not None and entry.expires_at > now:
            return entry.schema
        schema = await self.schemas.resolve_for_project(project_id)
        self._cache[project_id] = _CacheEntry(schema=schema, expires_at=now + self.ttl_s)
        return schema

    def invalidate(self, project_id: str) -> None:
        """Drop a project's cached resolution (call after a schema mutation)."""
        self._cache.pop(project_id, None)

    def clear(self) -> None:
        """Drop the whole cache (test hygiene / global schema reseed)."""
        self._cache.clear()

    async def resolve_node_kinds(self, project_id: str) -> ResolvedNodeKinds:
        """Cross-check the schema's expected node-kinds against glossary (M1).

        Selects the node-kind source by project shape (book → book ontology;
        no book → user glossary standards), reads the kind set from glossary,
        and pairs it with the resolved schema's expected kinds so the caller
        (adopt-gate, kind picker, triage) can detect a missing kind.

        Never raises: a glossary read failure yields ``glossary_codes=None``
        (source ``unavailable``); a project the repo can't find yields the
        ``general`` schema's (all-optional) expected kinds with no glossary
        cross-check.
        """
        schema = await self.resolve(project_id)
        expected = schema.node_kinds

        meta = await self._project_meta(project_id)
        if meta is None:
            # Unknown project — resolve still returned a schema (general);
            # we have no owner/book to resolve a glossary source against.
            return ResolvedNodeKinds(expected=expected, glossary_codes=None, source="unavailable")

        owner_user_id, book_id = meta
        if book_id is not None:
            kinds = await self.glossary.get_book_ontology(book_id, owner_user_id)
            source = "book"
        else:
            kinds = await self.glossary.get_user_standards(owner_user_id)
            source = "user_standards"

        if kinds is None:
            return ResolvedNodeKinds(
                expected=expected, glossary_codes=None, source="unavailable", book_id=book_id,
            )
        return ResolvedNodeKinds(
            expected=expected,
            glossary_codes=frozenset(kinds.codes()),
            source=source,
            book_id=book_id,
        )

    async def _project_meta(self, project_id: str) -> tuple[UUID, UUID | None] | None:
        """``(owner_user_id, book_id)`` for the project, or None if unknown.

        ``knowledge_projects.project_id`` is a UUID; the kg-schema tier stores
        ``scope_id`` as TEXT. A non-UUID project_id (a synthetic test id) simply
        has no owner/book to resolve a glossary source from → None.
        """
        try:
            pid = UUID(project_id)
        except (ValueError, TypeError):
            return None
        return await self.projects.project_meta(pid)
