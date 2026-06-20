"""kg_graph_schemas read + resolution repository (epic 2026-06-20, lane L1).

READ-ONLY foundation used by the parallel lanes (LA wraps this with caching +
the node-kind source resolution; LC/LD read it for gates/queries). Writes
(adopt / sync / CRUD) live in lane LC's `ontology_mutations.py`.

Tenancy: this repo filters by SCOPE — system rows are visible to everyone,
user rows only to their owner, project rows to a caller who passes the
project_id they've been grant-checked for (the router enforces the grant; the
repo enforces the scope key). Never returns another user's user-tier schema.

Spec: docs/specs/2026-06-20-knowledge-graph-customizable-ontology.md §3.5.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg

from app.db.ontology_models import (
    EdgeType,
    FactType,
    GraphSchema,
    ResolvedSchema,
    SchemaNodeKind,
    VocabSet,
    VocabValue,
)

_SCHEMA_COLS = """
  schema_id, scope, scope_id, code, name, description, schema_version,
  allow_free_edges, content_hash, source_ref, source_hash, deprecated_at,
  created_at, updated_at
"""


def _row_to_schema(row: asyncpg.Record) -> GraphSchema:
    return GraphSchema.model_validate(dict(row))


class GraphSchemasRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ── children ──────────────────────────────────────────────────────
    async def _edge_types(self, conn: asyncpg.Connection, schema_id, *, include_deprecated=False) -> list[EdgeType]:
        rows = await conn.fetch(
            f"""
            SELECT edge_type_id, schema_id, code, label, directed, source_node_kinds,
                   target_node_kinds, temporal, provenance_required, cardinality,
                   description, deprecated_at
            FROM kg_edge_types
            WHERE schema_id = $1 {'' if include_deprecated else 'AND deprecated_at IS NULL'}
            ORDER BY code
            """,
            schema_id,
        )
        return [EdgeType.model_validate(dict(r)) for r in rows]

    async def _fact_types(self, conn: asyncpg.Connection, schema_id, *, include_deprecated=False) -> list[FactType]:
        rows = await conn.fetch(
            f"""
            SELECT fact_type_id, schema_id, code, label, description, deprecated_at
            FROM kg_fact_types
            WHERE schema_id = $1 {'' if include_deprecated else 'AND deprecated_at IS NULL'}
            ORDER BY code
            """,
            schema_id,
        )
        return [FactType.model_validate(dict(r)) for r in rows]

    async def _node_kinds(self, conn: asyncpg.Connection, schema_id, *, include_deprecated=False) -> list[SchemaNodeKind]:
        rows = await conn.fetch(
            f"""
            SELECT schema_node_kind_id, schema_id, kind_code, strength, deprecated_at
            FROM kg_schema_node_kinds
            WHERE schema_id = $1 {'' if include_deprecated else 'AND deprecated_at IS NULL'}
            ORDER BY kind_code
            """,
            schema_id,
        )
        return [SchemaNodeKind.model_validate(dict(r)) for r in rows]

    async def _vocab_sets(self, conn: asyncpg.Connection, schema_id) -> tuple[list[VocabSet], dict[str, list[VocabValue]]]:
        set_rows = await conn.fetch(
            """
            SELECT vocab_set_id, schema_id, code, label, description, closed, deprecated_at
            FROM kg_vocab_sets WHERE schema_id = $1 AND deprecated_at IS NULL ORDER BY code
            """,
            schema_id,
        )
        sets = [VocabSet.model_validate(dict(r)) for r in set_rows]
        values_by_code: dict[str, list[VocabValue]] = {}
        for s in sets:
            val_rows = await conn.fetch(
                """
                SELECT vocab_value_id, vocab_set_id, code, label, metadata
                FROM kg_vocab_values WHERE vocab_set_id = $1 AND deprecated_at IS NULL ORDER BY code
                """,
                s.vocab_set_id,
            )
            values_by_code[s.code] = [
                VocabValue.model_validate({**dict(r), "metadata": _as_dict(r["metadata"])}) for r in val_rows
            ]
        return sets, values_by_code

    # ── reads ─────────────────────────────────────────────────────────
    async def list_visible(
        self,
        user_id: UUID,
        *,
        project_id: str | None = None,
        scope: str | None = None,
        include_deprecated: bool = False,
    ) -> list[GraphSchema]:
        """System (all) + the caller's user templates + (optional) the project's schema."""
        clauses = ["(scope = 'system')", "(scope = 'user' AND scope_id = $1)"]
        params: list = [str(user_id)]
        if project_id is not None:
            params.append(project_id)
            clauses.append(f"(scope = 'project' AND scope_id = ${len(params)})")
        where = "(" + " OR ".join(clauses) + ")"
        if not include_deprecated:
            where += " AND deprecated_at IS NULL"
        if scope in ("system", "user", "project"):
            params.append(scope)
            where += f" AND scope = ${len(params)}"
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(f"SELECT {_SCHEMA_COLS} FROM kg_graph_schemas WHERE {where} ORDER BY scope, code", *params)
        return [_row_to_schema(r) for r in rows]

    async def get_tree(
        self,
        user_id: UUID,
        schema_id: UUID,
        *,
        project_id: str | None = None,
        include_deprecated: bool = False,
    ) -> dict | None:
        """One schema + children, scope-visible to the caller. None if not visible."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(f"SELECT {_SCHEMA_COLS} FROM kg_graph_schemas WHERE schema_id = $1", schema_id)
            if row is None:
                return None
            schema = _row_to_schema(row)
            if not _visible(schema, user_id, project_id):
                return None
            sets, values = await self._vocab_sets(conn, schema_id)
            return {
                "schema": schema,
                "edge_types": await self._edge_types(conn, schema_id, include_deprecated=include_deprecated),
                "fact_types": await self._fact_types(conn, schema_id, include_deprecated=include_deprecated),
                "node_kinds": await self._node_kinds(conn, schema_id, include_deprecated=include_deprecated),
                "vocab_sets": sets,
                "vocab_values": values,
            }

    async def get_system_template_by_code(self, code: str) -> GraphSchema | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_SCHEMA_COLS} FROM kg_graph_schemas WHERE scope = 'system' AND scope_id IS NULL AND code = $1",
                code,
            )
        return _row_to_schema(row) if row else None

    async def active_project_schema(self, project_id: str) -> GraphSchema | None:
        """The project's single active project-scoped schema row (schema_id +
        schema_version), or ``None`` if the project never adopted (resolves to the
        System `general` template). KM6: the confirm-token optimistic-concurrency
        check reads (schema_id, schema_version) here at confirm time to detect drift
        since mint. Mirrors ``resolve_for_project``'s project-row query — the same
        one-active invariant + ORDER BY tiebreaker."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {_SCHEMA_COLS} FROM kg_graph_schemas
                WHERE scope = 'project' AND scope_id = $1 AND deprecated_at IS NULL
                ORDER BY updated_at DESC, schema_id DESC LIMIT 1
                """,
                project_id,
            )
        return _row_to_schema(row) if row else None

    async def resolve_for_project(self, project_id: str, *, fallback_code: str = "general") -> ResolvedSchema:
        """The effective schema for a project (spec §3.5).

        v1 (Q1 LOCKED): one active project-scoped schema — the merge happened at
        adopt. If the project never adopted, resolve to the System `general`
        template (the additive-first fallback → today's behavior).

        TENANCY CONTRACT (review-impl): `project_id` is caller-supplied; this repo
        does NOT verify the caller's grant on it. Every caller (LC/LD routers, the
        extraction path) MUST grant-check the project before calling, exactly like
        the other knowledge repos. The one-active invariant is maintained by adopt
        (LC replaces, never accumulates project rows); the ORDER BY tiebreaker
        below is only a defensive guard against accidental duplicates.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT {_SCHEMA_COLS} FROM kg_graph_schemas
                WHERE scope = 'project' AND scope_id = $1 AND deprecated_at IS NULL
                ORDER BY updated_at DESC, schema_id DESC LIMIT 1
                """,
                project_id,
            )
            if row is None:
                row = await conn.fetchrow(
                    f"SELECT {_SCHEMA_COLS} FROM kg_graph_schemas WHERE scope = 'system' AND scope_id IS NULL AND code = $1",
                    fallback_code,
                )
            if row is None:
                # No project schema and no `general` seed — degenerate empty resolve.
                return ResolvedSchema(project_id=project_id, schema_version=0, allow_free_edges=True)
            schema = _row_to_schema(row)
            sets, values = await self._vocab_sets(conn, schema.schema_id)
            return ResolvedSchema(
                project_id=project_id,
                schema_version=schema.schema_version,
                allow_free_edges=schema.allow_free_edges,
                edge_types=await self._edge_types(conn, schema.schema_id),
                fact_types=await self._fact_types(conn, schema.schema_id),
                vocab_sets=sets,
                vocab_values=values,
                node_kinds=await self._node_kinds(conn, schema.schema_id),
            )


def _visible(schema: GraphSchema, user_id: UUID, project_id: str | None) -> bool:
    if schema.scope == "system":
        return True
    if schema.scope == "user":
        return schema.scope_id == str(user_id)
    if schema.scope == "project":
        # Router enforces the grant; repo confirms the project id matches.
        return project_id is not None and schema.scope_id == project_id
    return False


def _as_dict(value) -> dict:
    """asyncpg returns jsonb as str (no codec) or dict; normalize to dict."""
    if value is None:
        return {}
    if isinstance(value, str):
        import json

        return json.loads(value)
    return dict(value)
