"""In-memory `OntologyStore` for tests (plan T15).

Holds `GraphSchema` objects and answers from them. The rules it must reproduce are the
VISIBILITY rules, not the SQL: system rows are visible to everyone, user rows only to their
owner, project rows only to a caller that supplies that project id. A fake that returned
everything would let a cross-tenant read pass every test and fail only in production, which
is the failure mode that makes fakes dangerous in the first place.

Two behaviours are copied deliberately because they are easy to get wrong in a fake and
they matter:

- **Not-visible and not-found are indistinguishable.** Both return `None`. If "not
  visible" raised, a caller could enumerate another tenant's schema ids by watching which
  ones raise.
- **`resolve_for_project` never returns `None`.** A project that never adopted resolves to
  the system fallback. A fake that returned `None` would teach every consumer to handle a
  case the real store cannot produce — and hide the one it can: an EMPTY resolution.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.db.ontology_models import GraphSchema, ResolvedSchema

logger = logging.getLogger(__name__)

__all__ = ["FakeOntologyStore"]


class FakeOntologyStore:
    def __init__(self, schemas: list[GraphSchema] | None = None) -> None:
        self._schemas: list[GraphSchema] = list(schemas or [])
        self._summaries: dict[UUID, dict] = {}

    # ── test affordances (not part of the port) ──────────────────────────────

    def add(self, schema: GraphSchema, *, summary: dict | None = None) -> None:
        self._schemas.append(schema)
        if summary is not None:
            self._summaries[schema.schema_id] = summary

    # ── visibility, the rule the port actually turns on ──────────────────────

    def _visible(self, s: GraphSchema, user_id: UUID, project_id: str | None) -> bool:
        if s.scope == "system":
            return True
        if s.scope == "user":
            return s.scope_id == str(user_id)
        if s.scope == "project":
            # A project row is visible ONLY when the caller names that project. The
            # caller is responsible for having been grant-checked on it — the port says
            # so, because no store can verify a grant it was never told about.
            return project_id is not None and s.scope_id == project_id
        return False

    # ── the port ─────────────────────────────────────────────────────────────

    async def list_visible(
        self,
        user_id: UUID,
        *,
        project_id: str | None = None,
        scope: str | None = None,
        include_deprecated: bool = False,
    ) -> list[GraphSchema]:
        out = [s for s in self._schemas if self._visible(s, user_id, project_id)]
        if not include_deprecated:
            out = [s for s in out if s.deprecated_at is None]
        if scope in ("system", "user", "project"):
            out = [s for s in out if s.scope == scope]
        # Same ordering the SQL gives (`ORDER BY scope, code`), so a test that asserts on
        # order is asserting something the real store also guarantees.
        return sorted(out, key=lambda s: (s.scope, s.code))

    async def get_tree(
        self,
        user_id: UUID,
        schema_id: UUID,
        *,
        project_id: str | None = None,
        include_deprecated: bool = False,
    ) -> GraphSchema | None:
        for s in self._schemas:
            if s.schema_id != schema_id:
                continue
            if not self._visible(s, user_id, project_id):
                return None  # NOT an error: invisible must be indistinguishable from absent
            if s.deprecated_at is not None and not include_deprecated:
                return None
            return s
        return None

    async def get_system_template_by_code(self, code: str) -> GraphSchema | None:
        for s in self._schemas:
            if s.scope == "system" and s.code == code:
                return s
        return None

    async def active_project_schema(self, project_id: str) -> GraphSchema | None:
        candidates = [
            s for s in self._schemas
            if s.scope == "project" and s.scope_id == project_id and s.deprecated_at is None
        ]
        if not candidates:
            return None
        # One-active is an invariant adopt maintains; the tiebreaker mirrors the repo's
        # defensive `ORDER BY updated_at DESC, schema_id DESC` so a fixture that violates
        # the invariant resolves the same way in both.
        return sorted(candidates, key=lambda s: (s.updated_at, str(s.schema_id)), reverse=True)[0]

    async def template_summary(self, source_schema_id: UUID, user_id: UUID) -> dict | None:
        for s in self._schemas:
            if s.schema_id != source_schema_id:
                continue
            # System: visible to all. User: owner only. Anything else (a project schema,
            # another user's template) is NOT adoptable and reads as absent.
            if s.scope == "system" or (s.scope == "user" and s.scope_id == str(user_id)):
                return self._summaries.get(source_schema_id, {"code": s.code, "name": s.name})
            return None
        return None

    async def resolve_for_project(
        self, project_id: str, *, fallback_code: str = "general",
    ) -> ResolvedSchema:
        active = await self.active_project_schema(project_id)
        source = active
        if source is None:
            source = await self.get_system_template_by_code(fallback_code)
        if source is None:
            # No adopted schema AND no fallback template. Still not None — the contract
            # says extraction must always get something — but empty, and logged, because
            # an empty ontology extracts nothing and looks like a quiet model failure.
            logger.warning(
                "ontology resolve: project=%s has no schema and no %r fallback — "
                "resolving EMPTY; extraction will produce nothing",
                project_id, fallback_code,
            )
            return ResolvedSchema(project_id=project_id, schema_version=0, allow_free_edges=True)
        return ResolvedSchema(
            project_id=project_id,
            schema_version=source.schema_version,
            allow_free_edges=source.allow_free_edges,
        )
