"""Postgres implementation of the `OntologyStore` port (plan T15).

Delegates to `GraphSchemasRepo`, for the same reason the Neo4j vector adapter delegates to
`graph_repos`: the repo holds the scope-visibility rules, and a second copy of a tenancy
filter is how the two drift and one of them starts leaking another user's templates.

The adapter is thin to the point of looking pointless, and that is the shape a correct one
has here. What it buys is that `resolver.py`, the routers, the MCP server and the
extraction path stop naming a concrete repo — so `FakeOntologyStore` can take its place in
a test, and a future backend can take its place in production, without either of them
touching a consumer.
"""

from __future__ import annotations

import logging
import time
from uuid import UUID

from app.db.ontology_models import GraphSchema, ResolvedSchema
from app.db.repositories.graph_schemas import GraphSchemasRepo

logger = logging.getLogger(__name__)

__all__ = ["PostgresOntologyStore"]


class PostgresOntologyStore:
    def __init__(self, repo: GraphSchemasRepo) -> None:
        self._repo = repo

    async def list_visible(
        self,
        user_id: UUID,
        *,
        project_id: str | None = None,
        scope: str | None = None,
        include_deprecated: bool = False,
    ) -> list[GraphSchema]:
        out = await self._repo.list_visible(
            user_id, project_id=project_id, scope=scope,
            include_deprecated=include_deprecated,
        )
        logger.debug(
            "ontology list_visible: backend=postgres project=%s scope=%s deprecated=%s rows=%d",
            project_id, scope, include_deprecated, len(out),
        )
        return out

    async def get_tree(
        self,
        user_id: UUID,
        schema_id: UUID,
        *,
        project_id: str | None = None,
        include_deprecated: bool = False,
    ) -> GraphSchema | None:
        return await self._repo.get_tree(
            user_id, schema_id, project_id=project_id,
            include_deprecated=include_deprecated,
        )

    async def get_system_template_by_code(self, code: str) -> GraphSchema | None:
        return await self._repo.get_system_template_by_code(code)

    async def active_project_schema(self, project_id: str) -> GraphSchema | None:
        return await self._repo.active_project_schema(project_id)

    async def template_summary(self, source_schema_id: UUID, user_id: UUID) -> dict | None:
        return await self._repo.template_summary(source_schema_id, user_id)

    async def resolve_for_project(
        self, project_id: str, *, fallback_code: str = "general",
    ) -> ResolvedSchema:
        started = time.perf_counter()
        resolved = await self._repo.resolve_for_project(
            project_id, fallback_code=fallback_code
        )
        # The hot path — extraction and validation resolve per run. Logged with the shape
        # of what came back so a project resolving to an EMPTY ontology (every extraction
        # then produces nothing and nobody sees an error) is visible in the logs.
        logger.debug(
            "ontology resolve: backend=postgres project=%s version=%s node_kinds=%d "
            "edge_types=%d fact_types=%d elapsed_ms=%d",
            project_id, resolved.schema_version, len(resolved.node_kinds),
            len(resolved.edge_types), len(resolved.fact_types),
            int((time.perf_counter() - started) * 1000),
        )
        return resolved
