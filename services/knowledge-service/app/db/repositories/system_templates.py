"""KM5-M2 — System-tier graph-template WRITES (admin authority only).

The `OntologyMutationsRepo` hard-blocks `scope='system'` on every write
(`_load_writable` raises "system-tier schema is read-only") — that is the
tenancy guard that stops a regular user mutating a shared row (the canonical
kinds bug). System-tier writes therefore live HERE, in a separate repo with the
**inverse** guard (`_load_system` asserts the row IS system), reachable ONLY
from the RS256-gated `auth=admin` confirm branch (INV-T2/T3: every System write
verifies an admin JWT AND is human-confirmed). Do not call this repo from any
grant/owner path.

Scope (M2): template-level create / patch / deprecate (metadata). Child-level
System authoring (add an edge type to a system template) is a later additive
extension of the same descriptor — the auth path is the load-bearing part.

`content_hash` is the tree-surface family (`_compute_content_hash`), same as
project/user rows — NOT the seed-literal family. `create` requires a NEW code,
so admin templates never collide with the two code-seeded bootstrap templates
(`general` / `xianxia-harem`), which the startup seed continues to own.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from app.db.ontology_models import GraphSchema
from app.db.repositories.ontology_mutations import (
    _SCHEMA_COLS,
    _compute_content_hash,
    _row_to_schema,
)

__all__ = [
    "SystemTemplatesRepo",
    "SystemTemplateNotFound",
    "DuplicateSystemTemplate",
]

# Same advisory-lock namespace the seed uses, so an admin create and a concurrent
# startup re-seed serialize on (ns, hashtext(code)) instead of racing to a unique
# violation on idx_kg_graph_schemas_scope_code.
_SEED_LOCK_NS = 0x4B47  # 'KG' (mirror seed_graph_schemas._SEED_LOCK_NS)


class SystemTemplateNotFound(Exception):
    """Target system template is absent or the schema_id is not a system row (404/422)."""


class DuplicateSystemTemplate(Exception):
    """A system template with this code already exists (409)."""


class SystemTemplatesRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_system_template(self, schema_id: UUID) -> GraphSchema | None:
        """Read one system template by id (None if absent OR not a system row).

        Used by the confirm re-validation + preview. A non-system row reads as
        None so the admin path can never address a user/project schema."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_SCHEMA_COLS} FROM kg_graph_schemas "
                f"WHERE schema_id = $1 AND scope = 'system' AND scope_id IS NULL",
                schema_id,
            )
        return _row_to_schema(row) if row else None

    async def list_templates(self, *, include_deprecated: bool = False) -> list[GraphSchema]:
        """All System-tier templates (admin read surface). System tier is global
        read-only to regular users; the admin reads it here over the RS256 gate."""
        where = "scope = 'system' AND scope_id IS NULL"
        if not include_deprecated:
            where += " AND deprecated_at IS NULL"
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {_SCHEMA_COLS} FROM kg_graph_schemas WHERE {where} ORDER BY code"
            )
        return [_row_to_schema(r) for r in rows]

    async def code_exists(self, code: str) -> bool:
        """True iff a system template with this code exists (used by create preview
        to flag a would-be 409 before the admin confirms)."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT 1 FROM kg_graph_schemas "
                "WHERE scope = 'system' AND scope_id IS NULL AND code = $1",
                code,
            ) is not None

    async def create_template(
        self, *, code: str, name: str, description: str = "", allow_free_edges: bool = True
    ) -> GraphSchema:
        """Insert a new (empty-tree) system template. Code must be free across ALL
        system templates (incl. the seeded ones) → `DuplicateSystemTemplate` on
        collision. Children are added later via patch/child-authoring."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock($1, hashtext($2))", _SEED_LOCK_NS, code
                )
                existing = await conn.fetchval(
                    "SELECT 1 FROM kg_graph_schemas "
                    "WHERE scope = 'system' AND scope_id IS NULL AND code = $1",
                    code,
                )
                if existing is not None:
                    raise DuplicateSystemTemplate(code)
                try:
                    new_id = await conn.fetchval(
                        """
                        INSERT INTO kg_graph_schemas
                          (scope, scope_id, code, name, description, allow_free_edges)
                        VALUES ('system', NULL, $1, $2, $3, $4)
                        RETURNING schema_id
                        """,
                        code, name, description, allow_free_edges,
                    )
                except asyncpg.UniqueViolationError as exc:  # race lost the advisory lock window
                    raise DuplicateSystemTemplate(code) from exc
                # content_hash over the (empty) tree surface, tree-surface family.
                chash = await _compute_content_hash(conn, new_id)
                await conn.execute(
                    "UPDATE kg_graph_schemas SET content_hash = $2 WHERE schema_id = $1",
                    new_id, chash,
                )
                row = await conn.fetchrow(
                    f"SELECT {_SCHEMA_COLS} FROM kg_graph_schemas WHERE schema_id = $1", new_id
                )
        return _row_to_schema(row)

    async def patch_template(
        self,
        schema_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        allow_free_edges: bool | None = None,
    ) -> GraphSchema:
        """Edit a system template's metadata, bump schema_version, recompute hash."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._load_system(conn, schema_id)  # asserts it IS a system row
                sets = ["updated_at = now()", "schema_version = schema_version + 1"]
                params: list[Any] = [schema_id]
                if name is not None:
                    params.append(name)
                    sets.append(f"name = ${len(params)}")
                if description is not None:
                    params.append(description)
                    sets.append(f"description = ${len(params)}")
                if allow_free_edges is not None:
                    params.append(allow_free_edges)
                    sets.append(f"allow_free_edges = ${len(params)}")
                await conn.execute(
                    f"UPDATE kg_graph_schemas SET {', '.join(sets)} WHERE schema_id = $1", *params
                )
                chash = await _compute_content_hash(conn, schema_id)
                await conn.execute(
                    "UPDATE kg_graph_schemas SET content_hash = $2 WHERE schema_id = $1",
                    schema_id, chash,
                )
                row = await conn.fetchrow(
                    f"SELECT {_SCHEMA_COLS} FROM kg_graph_schemas WHERE schema_id = $1", schema_id
                )
        return _row_to_schema(row)

    async def deprecate_template(self, schema_id: UUID) -> None:
        """Soft-deprecate a system template (never hard-drop — A4; projects that
        adopted a copy keep working, new adopts/sync just stop seeing it)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._load_system(conn, schema_id)
                await conn.execute(
                    "UPDATE kg_graph_schemas SET deprecated_at = now(), updated_at = now() "
                    "WHERE schema_id = $1 AND deprecated_at IS NULL",
                    schema_id,
                )

    async def _load_system(self, conn: asyncpg.Connection, schema_id: UUID) -> GraphSchema:
        """Lock the row + assert it is a System-tier template. The INVERSE of
        `OntologyMutationsRepo._load_writable`: that one rejects system; this one
        rejects everything BUT system, so the admin path can never reach across
        into a user/project schema."""
        row = await conn.fetchrow(
            f"SELECT {_SCHEMA_COLS} FROM kg_graph_schemas WHERE schema_id = $1 FOR UPDATE", schema_id
        )
        if row is None:
            raise SystemTemplateNotFound("system template not found")
        schema = _row_to_schema(row)
        if schema.scope != "system":
            raise SystemTemplateNotFound("not a system template")
        return schema
