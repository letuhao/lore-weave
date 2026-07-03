"""kg graph-schema WRITES — adopt (copy-down), sync (diff/apply), per-tier CRUD.

Lane LC of the KG customizable-ontology epic (2026-06-20). The read/resolve
foundation lives in `graph_schemas.py` (lane L1); this module owns every
mutation: deep-copy adopt, tree-granular sync, and the additive +
deprecate-only child CRUD (M3).

Tenancy (CLAUDE.md › User Boundaries): the ROUTER grant-gates before calling
here (Manage on a project schema; owner==caller on a user schema; System tier
is read-only — never mutated through this repo). This repo enforces the scope
key on every write so a caller can never reach across tiers.

Hashing: `content_hash` is computed over the SAME semantic surface shape the
seed uses (`seed_graph_schemas._content_hash`), so a project copy and its
upstream source hash apples-to-apples for Sync. `source_hash` is the upstream
source's `content_hash` frozen at adopt/last-sync — the optimistic-concurrency
token + the change-detection baseline.

Spec: docs/specs/2026-06-20-knowledge-graph-customizable-ontology.md §2 (layer
2 adopt + sync), §3.1/§3.2/§3.2b, §8 M1/M3, §10-A3/A4.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg

from app.db.ontology_models import GraphSchema
from app.db.seed_graph_schemas import _content_hash

__all__ = [
    "OntologyMutationsRepo",
    "AdoptResult",
    "compute_adopt_losses",
    "NeedsGlossaryError",
    "SyncConflictError",
    "SchemaNotWritableError",
    "DuplicateChildError",
    "ChildNotFoundError",
]


# ── domain errors (router maps to HTTP status) ────────────────────────────
class NeedsGlossaryError(Exception):
    """Adopt blocked: glossary missing one or more `required` node-kinds (M1, 422)."""

    def __init__(self, kinds: list[str], book_id: str | None) -> None:
        self.kinds = kinds
        self.book_id = book_id
        super().__init__(f"glossary missing required node-kinds: {kinds}")


class SyncConflictError(Exception):
    """Optimistic-concurrency: upstream moved since /sync/available was read (409)."""


class SchemaNotWritableError(Exception):
    """Write attempted on a System-tier schema, or schema not visible/owned (403/404)."""


class DuplicateChildError(Exception):
    """A child with this code already exists in the schema (409)."""


class ChildNotFoundError(Exception):
    """The targeted child (by code) does not exist in the schema (404)."""


class AdoptResult:
    """The project schema row created by adopt + the optional `optional`-gap warning."""

    def __init__(self, schema: GraphSchema, missing_optional: list[str]) -> None:
        self.schema = schema
        self.missing_optional = missing_optional


# ── helpers ───────────────────────────────────────────────────────────────
_SCHEMA_COLS = """
  schema_id, scope, scope_id, code, name, description, schema_version,
  allow_free_edges, content_hash, source_ref, source_hash, deprecated_at,
  created_at, updated_at
"""


def _as_dict(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, str):
        return json.loads(value)
    return dict(value)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# review-impl MED: serialize per-project adopt/sync so concurrent re-adopt or an
# adopt racing a sync can't leave two active project schemas / mutate a row that
# was just deprecated underneath (TOCTOU). Same primitive as the L1 seed lock.
_ONTOLOGY_LOCK_NS = 0x4B4F  # 'KO' (KG ontology)


async def _lock_project(conn: asyncpg.Connection, project_id: str) -> None:
    await conn.execute(
        "SELECT pg_advisory_xact_lock($1, hashtext($2))", _ONTOLOGY_LOCK_NS, project_id
    )


def _assert_source_adoptable(source: GraphSchema, *, owner_user_id: UUID, project_id: str) -> None:
    """review-impl HIGH: the adopt source must be VISIBLE to the caller, else a
    user could deep-copy (and thus read) another tenant's private user-tier
    template by passing its UUID — the router only grant-gates the DESTINATION
    project. Adoptable sources: System templates · the caller's OWN user-tier
    templates · this project's own rows (re-adopt). Anything else → not-found
    (no existence oracle)."""
    if source.scope == "system":
        return
    if source.scope == "user" and source.scope_id == str(owner_user_id):
        return
    if source.scope == "project" and source.scope_id == project_id:
        return
    raise SchemaNotWritableError("source schema not found")


async def _tree_surface(conn: asyncpg.Connection, schema_id: UUID) -> dict:
    """Build the canonical semantic surface of a schema's tree for adopt/sync hashing.

    This is the ONE hashing surface for adopt/sync: a project's frozen `source_hash`
    and the upstream's recomputed current hash are BOTH `_tree_surface`-based, so
    they compare apples-to-apples (and `sort_keys=True` + SQL `ORDER BY` make it
    order-stable). Deprecated children are excluded (not part of the live surface).

    NOTE (review-impl): this is intentionally NOT identical to the seed's raw
    `_content_hash(template)` — that hashes the template literal (which carries a
    top-level `code` key + authoring order) and is used only as the seed's
    re-seed gate. The two hash families never cross; do not compare a stored
    system `content_hash` (seed-family) against a `_compute_content_hash` result.
    """
    schema = await conn.fetchrow(
        "SELECT name, description, allow_free_edges FROM kg_graph_schemas WHERE schema_id = $1",
        schema_id,
    )
    node_kinds = await conn.fetch(
        "SELECT kind_code, strength FROM kg_schema_node_kinds "
        "WHERE schema_id = $1 AND deprecated_at IS NULL ORDER BY kind_code",
        schema_id,
    )
    edge_types = await conn.fetch(
        """
        SELECT code, label, directed, source_node_kinds, target_node_kinds,
               temporal, provenance_required, cardinality, description
        FROM kg_edge_types WHERE schema_id = $1 AND deprecated_at IS NULL ORDER BY code
        """,
        schema_id,
    )
    fact_types = await conn.fetch(
        "SELECT code, label FROM kg_fact_types "
        "WHERE schema_id = $1 AND deprecated_at IS NULL ORDER BY code",
        schema_id,
    )
    vocab_sets = await conn.fetch(
        "SELECT vocab_set_id, code, label, description, closed FROM kg_vocab_sets "
        "WHERE schema_id = $1 AND deprecated_at IS NULL ORDER BY code",
        schema_id,
    )
    vsets: list[dict] = []
    for vs in vocab_sets:
        vals = await conn.fetch(
            "SELECT code, label, metadata FROM kg_vocab_values "
            "WHERE vocab_set_id = $1 AND deprecated_at IS NULL ORDER BY code",
            vs["vocab_set_id"],
        )
        vsets.append(
            {
                "code": vs["code"],
                "label": vs["label"],
                "description": vs["description"],
                "closed": vs["closed"],
                "values": [
                    [v["code"], v["label"], _as_dict(v["metadata"])] for v in vals
                ],
            }
        )
    return {
        "name": schema["name"],
        "description": schema["description"],
        "allow_free_edges": schema["allow_free_edges"],
        "node_kinds": [[k["kind_code"], k["strength"]] for k in node_kinds],
        "edge_types": [
            {
                "code": e["code"],
                "label": e["label"],
                "directed": e["directed"],
                "source_node_kinds": list(e["source_node_kinds"]),
                "target_node_kinds": list(e["target_node_kinds"]),
                "temporal": e["temporal"],
                "provenance_required": e["provenance_required"],
                "cardinality": e["cardinality"],
                "description": e["description"],
            }
            for e in edge_types
        ],
        "fact_types": [[f["code"], f["label"]] for f in fact_types],
        "vocab_sets": vsets,
    }


async def _compute_content_hash(conn: asyncpg.Connection, schema_id: UUID) -> str:
    return _content_hash(await _tree_surface(conn, schema_id))


def _row_to_schema(row: asyncpg.Record) -> GraphSchema:
    return GraphSchema.model_validate(dict(row))


class OntologyMutationsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ── small reads the router needs for gating ────────────────────────────
    async def get_schema(self, schema_id: UUID) -> GraphSchema | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_SCHEMA_COLS} FROM kg_graph_schemas WHERE schema_id = $1", schema_id
            )
        return _row_to_schema(row) if row else None

    async def required_node_kinds(self, schema_id: UUID) -> list[str]:
        """The `required`-strength node-kind codes the adopt-gate must check (M1)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT kind_code FROM kg_schema_node_kinds "
                "WHERE schema_id = $1 AND strength = 'required' AND deprecated_at IS NULL "
                "ORDER BY kind_code",
                schema_id,
            )
        return [r["kind_code"] for r in rows]

    async def optional_node_kinds(self, schema_id: UUID) -> list[str]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT kind_code FROM kg_schema_node_kinds "
                "WHERE schema_id = $1 AND strength = 'optional' AND deprecated_at IS NULL "
                "ORDER BY kind_code",
                schema_id,
            )
        return [r["kind_code"] for r in rows]

    # ── adopt (copy-down) ──────────────────────────────────────────────────
    async def adopt(
        self,
        *,
        owner_user_id: UUID,
        project_id: str,
        source_schema_id: UUID,
        glossary_kinds: set[str],
        book_id: str | None,
    ) -> AdoptResult:
        """Deep-copy `source_schema_id` (+ all live children) into a project row.

        **Replace-on-adopt** (chosen semantics): a project has ONE active schema
        (the invariant `resolve_for_project` assumes — spec §3.5). Re-adopting
        (e.g. after filling a glossary gap, or switching templates) DEPRECATES
        any prior active project schema, then inserts a fresh copy. This keeps
        the one-active invariant true and makes re-adopt idempotent in effect:
        the project always ends with exactly one active schema copied from the
        chosen source. Old copies are soft-deprecated (history/sync auditability),
        never hard-dropped (M3 / A4).

        Adopt-gate (M1): the CALLER (router) supplies the glossary's known kind
        codes; this method blocks with `NeedsGlossaryError` if any `required`
        source node-kind is absent, and returns the missing `optional` kinds as
        a non-blocking warning.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await _lock_project(conn, project_id)  # serialize adopt/sync (MED)
                src = await conn.fetchrow(
                    f"SELECT {_SCHEMA_COLS} FROM kg_graph_schemas WHERE schema_id = $1 FOR SHARE",
                    source_schema_id,
                )
                if src is None:
                    raise SchemaNotWritableError("source schema not found")
                source = _row_to_schema(src)
                # HIGH: the source must be visible to the caller (no cross-tenant read).
                _assert_source_adoptable(source, owner_user_id=owner_user_id, project_id=project_id)

                # M1 adopt-gate — required must be present in glossary; optional warns.
                req = await conn.fetch(
                    "SELECT kind_code, strength FROM kg_schema_node_kinds "
                    "WHERE schema_id = $1 AND deprecated_at IS NULL",
                    source_schema_id,
                )
                missing_required = sorted(
                    r["kind_code"] for r in req
                    if r["strength"] == "required" and r["kind_code"] not in glossary_kinds
                )
                missing_optional = sorted(
                    r["kind_code"] for r in req
                    if r["strength"] == "optional" and r["kind_code"] not in glossary_kinds
                )
                if missing_required:
                    raise NeedsGlossaryError(missing_required, book_id)

                # Replace-on-adopt: deprecate any existing active project schema(s).
                await conn.execute(
                    """
                    UPDATE kg_graph_schemas SET deprecated_at = now(), updated_at = now()
                    WHERE scope = 'project' AND scope_id = $1 AND deprecated_at IS NULL
                    """,
                    project_id,
                )

                # source_hash = the source's CURRENT content_hash (recompute to be
                # robust against a stale stored hash); source_ref = 'scope:id'.
                source_hash = await _compute_content_hash(conn, source_schema_id)
                source_ref = (
                    f"system:{source.schema_id}"
                    if source.scope == "system"
                    else f"{source.scope}:{source.schema_id}"
                )

                new_id = await conn.fetchval(
                    """
                    INSERT INTO kg_graph_schemas
                      (scope, scope_id, code, name, description, allow_free_edges,
                       source_ref, source_hash)
                    VALUES ('project', $1, $2, $3, $4, $5, $6, $7)
                    RETURNING schema_id
                    """,
                    project_id, source.code, source.name, source.description,
                    source.allow_free_edges, source_ref, source_hash,
                )
                await self._copy_children(conn, source_schema_id, new_id)

                # content_hash of the fresh copy == source_hash (identical surface).
                chash = await _compute_content_hash(conn, new_id)
                await conn.execute(
                    "UPDATE kg_graph_schemas SET content_hash = $2 WHERE schema_id = $1",
                    new_id, chash,
                )
                row = await conn.fetchrow(
                    f"SELECT {_SCHEMA_COLS} FROM kg_graph_schemas WHERE schema_id = $1", new_id
                )
        return AdoptResult(_row_to_schema(row), missing_optional)

    async def _copy_children(
        self, conn: asyncpg.Connection, src_id: UUID, dst_id: UUID
    ) -> None:
        """Deep-copy every LIVE child of `src_id` under `dst_id`."""
        await conn.execute(
            """
            INSERT INTO kg_schema_node_kinds (schema_id, kind_code, strength)
            SELECT $2, kind_code, strength FROM kg_schema_node_kinds
            WHERE schema_id = $1 AND deprecated_at IS NULL
            """,
            src_id, dst_id,
        )
        await conn.execute(
            """
            INSERT INTO kg_edge_types
              (schema_id, code, label, directed, source_node_kinds, target_node_kinds,
               temporal, provenance_required, cardinality, description)
            SELECT $2, code, label, directed, source_node_kinds, target_node_kinds,
                   temporal, provenance_required, cardinality, description
            FROM kg_edge_types WHERE schema_id = $1 AND deprecated_at IS NULL
            """,
            src_id, dst_id,
        )
        await conn.execute(
            """
            INSERT INTO kg_fact_types (schema_id, code, label, description)
            SELECT $2, code, label, description FROM kg_fact_types
            WHERE schema_id = $1 AND deprecated_at IS NULL
            """,
            src_id, dst_id,
        )
        src_sets = await conn.fetch(
            "SELECT vocab_set_id, code, label, description, closed FROM kg_vocab_sets "
            "WHERE schema_id = $1 AND deprecated_at IS NULL",
            src_id,
        )
        for vs in src_sets:
            new_set_id = await conn.fetchval(
                """
                INSERT INTO kg_vocab_sets (schema_id, code, label, description, closed)
                VALUES ($1, $2, $3, $4, $5) RETURNING vocab_set_id
                """,
                dst_id, vs["code"], vs["label"], vs["description"], vs["closed"],
            )
            await conn.execute(
                """
                INSERT INTO kg_vocab_values (vocab_set_id, code, label, metadata)
                SELECT $2, code, label, metadata FROM kg_vocab_values
                WHERE vocab_set_id = $1 AND deprecated_at IS NULL
                """,
                vs["vocab_set_id"], new_set_id,
            )

    # ── re-adopt loss preview (read-only, D-KG-LC-REVADOPT-LOSS) ────────────
    async def compute_adopt_preview(
        self,
        *,
        owner_user_id: UUID,
        project_id: str,
        current_schema_id: UUID | None,
        incoming_source_id: UUID,
    ) -> dict:
        """Preview "what you'll lose" if the project re-adopts `incoming_source_id`.

        Read-only (no write, no lock). `current_schema_id` is the project's active
        schema (None when the project never adopted → nothing to lose). Builds both
        tree surfaces and returns the losing diff (removed_upstream + modified) as
        `would_lose`.

        Tenancy (mirrors adopt): the preview DEEP-READS the source's tree surface,
        so it MUST apply the same visibility gate as adopt — else a caller could read
        another tenant's private user-tier template by passing its UUID (the router
        only grant-gates the DESTINATION project). `_assert_source_adoptable` allows
        only System templates / the caller's own user templates / this project's own
        rows; anything else → SchemaNotWritableError → 404 (no existence oracle)."""
        async with self._pool.acquire() as conn:
            src = await conn.fetchrow(
                f"SELECT {_SCHEMA_COLS} FROM kg_graph_schemas WHERE schema_id = $1",
                incoming_source_id,
            )
            if src is None:
                raise SchemaNotWritableError("source schema not found")
            _assert_source_adoptable(
                _row_to_schema(src), owner_user_id=owner_user_id, project_id=project_id
            )
            if current_schema_id is None:
                return {"has_current": False, "would_lose": []}
            incoming = await _tree_surface(conn, incoming_source_id)
            current = await _tree_surface(conn, current_schema_id)
        return {
            "has_current": True,
            "would_lose": compute_adopt_losses(current=current, incoming=incoming),
        }

    # ── schema metadata patch / deprecate ──────────────────────────────────
    async def patch_schema(
        self,
        schema_id: UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        allow_free_edges: bool | None = None,
    ) -> GraphSchema:
        """Edit user/project schema metadata. System tier is read-only (raise)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._load_writable(conn, schema_id)  # asserts writable tier
                sets = ["updated_at = now()"]
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
                await self._recompute_hash(conn, schema_id)
                row = await conn.fetchrow(
                    f"SELECT {_SCHEMA_COLS} FROM kg_graph_schemas WHERE schema_id = $1", schema_id
                )
        return _row_to_schema(row)

    async def deprecate_schema(self, schema_id: UUID) -> None:
        """Soft-deprecate a user/project schema (recycle bin). System tier raises."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._load_writable(conn, schema_id)
                await conn.execute(
                    "UPDATE kg_graph_schemas SET deprecated_at = now(), updated_at = now() "
                    "WHERE schema_id = $1 AND deprecated_at IS NULL",
                    schema_id,
                )

    # ── child CRUD (additive + deprecate-only, M3) ─────────────────────────
    async def add_edge_type(self, schema_id: UUID, *, code: str, label: str, **kw) -> dict:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._load_writable(conn, schema_id)
                row = await self._revive_or_insert(
                    conn, table="kg_edge_types",
                    key_cols={"schema_id": schema_id, "code": code},
                    attr_cols={
                        "label": label,
                        "directed": kw.get("directed", True),
                        "source_node_kinds": kw.get("source_node_kinds") or [],
                        "target_node_kinds": kw.get("target_node_kinds") or [],
                        "temporal": kw.get("temporal", False),
                        "provenance_required": kw.get("provenance_required", False),
                        "cardinality": kw.get("cardinality") or "multi_active",
                        "description": kw.get("description") or "",
                    },
                    returning="edge_type_id, schema_id, code, label, directed, "
                    "source_node_kinds, target_node_kinds, temporal, "
                    "provenance_required, cardinality, description, deprecated_at",
                )
                await self._bump_and_rehash(conn, schema_id)
        return dict(row)

    async def add_fact_type(self, schema_id: UUID, *, code: str, label: str, description: str = "") -> dict:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._load_writable(conn, schema_id)
                row = await self._revive_or_insert(
                    conn, table="kg_fact_types",
                    key_cols={"schema_id": schema_id, "code": code},
                    attr_cols={"label": label, "description": description},
                    returning="fact_type_id, schema_id, code, label, description, deprecated_at",
                )
                await self._bump_and_rehash(conn, schema_id)
        return dict(row)

    async def add_node_kind(self, schema_id: UUID, *, kind_code: str, strength: str) -> dict:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._load_writable(conn, schema_id)
                row = await self._revive_or_insert(
                    conn, table="kg_schema_node_kinds",
                    key_cols={"schema_id": schema_id, "kind_code": kind_code},
                    attr_cols={"strength": strength},
                    returning="schema_node_kind_id, schema_id, kind_code, strength, deprecated_at",
                )
                await self._bump_and_rehash(conn, schema_id)
        return dict(row)

    async def add_vocab_set(
        self, schema_id: UUID, *, code: str, label: str, description: str = "", closed: bool = True
    ) -> dict:
        """Create a vocab SET (EC — the missing create verb). Revive-on-recreate."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._load_writable(conn, schema_id)
                row = await self._revive_or_insert(
                    conn, table="kg_vocab_sets",
                    key_cols={"schema_id": schema_id, "code": code},
                    attr_cols={"label": label, "description": description, "closed": closed},
                    returning="vocab_set_id, schema_id, code, label, description, closed, deprecated_at",
                )
                await self._bump_and_rehash(conn, schema_id)
        return dict(row)

    async def add_vocab_value(
        self, schema_id: UUID, *, set_code: str, code: str, label: str, metadata: dict | None = None
    ) -> dict:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._load_writable(conn, schema_id)
                vset = await conn.fetchrow(
                    "SELECT vocab_set_id FROM kg_vocab_sets "
                    "WHERE schema_id = $1 AND code = $2 AND deprecated_at IS NULL",
                    schema_id, set_code,
                )
                if vset is None:
                    raise ChildNotFoundError(f"vocab set '{set_code}'")
                row = await self._revive_or_insert(
                    conn, table="kg_vocab_values",
                    key_cols={"vocab_set_id": vset["vocab_set_id"], "code": code},
                    attr_cols={"label": label, "metadata": json.dumps(metadata or {})},
                    returning="vocab_value_id, vocab_set_id, code, label, metadata",
                )
                await self._bump_and_rehash(conn, schema_id)
        out = dict(row)
        out["metadata"] = _as_dict(out["metadata"])
        return out

    # ── PATCH (attribute-only; code is IMMUTABLE — EC-A6) ──────────────────
    async def patch_edge_type(
        self, schema_id: UUID, code: str, *, updates: dict[str, Any]
    ) -> dict:
        """Edit a live edge type's attributes (not its code). `updates` holds only
        the fields the caller set; an empty dict is a no-op fetch (no version bump)."""
        if "cardinality" in updates and updates["cardinality"] not in ("single_active", "multi_active"):
            raise ValueError("cardinality must be single_active|multi_active")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._load_writable(conn, schema_id)
                row, changed = await self._patch_child(
                    conn, "kg_edge_types",
                    where="schema_id = $1 AND code = $2", where_vals=[schema_id, code],
                    updates=updates,
                    returning="edge_type_id, schema_id, code, label, directed, "
                    "source_node_kinds, target_node_kinds, temporal, "
                    "provenance_required, cardinality, description, deprecated_at",
                )
                if changed:
                    await self._bump_and_rehash(conn, schema_id)
        return dict(row)

    async def patch_fact_type(self, schema_id: UUID, code: str, *, updates: dict[str, Any]) -> dict:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._load_writable(conn, schema_id)
                row, changed = await self._patch_child(
                    conn, "kg_fact_types",
                    where="schema_id = $1 AND code = $2", where_vals=[schema_id, code],
                    updates=updates,
                    returning="fact_type_id, schema_id, code, label, description, deprecated_at",
                )
                if changed:
                    await self._bump_and_rehash(conn, schema_id)
        return dict(row)

    async def patch_node_kind(self, schema_id: UUID, kind_code: str, *, strength: str) -> dict:
        if strength not in ("required", "optional"):
            raise ValueError("strength must be required|optional")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._load_writable(conn, schema_id)
                row, changed = await self._patch_child(
                    conn, "kg_schema_node_kinds",
                    where="schema_id = $1 AND kind_code = $2", where_vals=[schema_id, kind_code],
                    updates={"strength": strength},
                    returning="schema_node_kind_id, schema_id, kind_code, strength, deprecated_at",
                )
                if changed:
                    await self._bump_and_rehash(conn, schema_id)
        return dict(row)

    async def patch_vocab_set(self, schema_id: UUID, code: str, *, updates: dict[str, Any]) -> dict:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._load_writable(conn, schema_id)
                row, changed = await self._patch_child(
                    conn, "kg_vocab_sets",
                    where="schema_id = $1 AND code = $2", where_vals=[schema_id, code],
                    updates=updates,
                    returning="vocab_set_id, schema_id, code, label, description, closed, deprecated_at",
                )
                if changed:
                    await self._bump_and_rehash(conn, schema_id)
        return dict(row)

    async def patch_vocab_value(
        self, schema_id: UUID, set_code: str, code: str, *, updates: dict[str, Any]
    ) -> dict:
        # own the JSONB encoding here (mirrors add_vocab_value) so callers pass a raw dict.
        if "metadata" in updates:
            updates = {**updates, "metadata": json.dumps(updates["metadata"] or {})}
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._load_writable(conn, schema_id)
                vset = await conn.fetchval(
                    "SELECT vocab_set_id FROM kg_vocab_sets "
                    "WHERE schema_id = $1 AND code = $2 AND deprecated_at IS NULL",
                    schema_id, set_code,
                )
                if vset is None:
                    raise ChildNotFoundError(f"vocab set '{set_code}'")
                row, changed = await self._patch_child(
                    conn, "kg_vocab_values",
                    where="vocab_set_id = $1 AND code = $2", where_vals=[vset, code],
                    updates=updates,
                    returning="vocab_value_id, vocab_set_id, code, label, metadata",
                )
                if changed:
                    await self._bump_and_rehash(conn, schema_id)
        out = dict(row)
        out["metadata"] = _as_dict(out["metadata"])
        return out

    # ── DELETE (tier-aware: user-tier HARD, project SOFT — EC-A5) ──────────
    _DELETE_TARGET = {
        "edge_type": ("kg_edge_types", "code"),
        "fact_type": ("kg_fact_types", "code"),
        "node_kind": ("kg_schema_node_kinds", "kind_code"),
        "vocab_set": ("kg_vocab_sets", "code"),
    }

    async def delete_child(
        self, schema_id: UUID, *, node_type: str, code: str, parent_set_code: str | None = None
    ) -> None:
        """Delete a schema child. On a USER-tier template the row is HARD-deleted;
        on a PROJECT schema it is SOFT-deprecated (EC-A5 — a project can extract at
        any time, so its types must stay queryable for graph data). A `vocab_set`
        hard-delete cascades its values (FK ON DELETE CASCADE)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                schema = await self._load_writable(conn, schema_id)
                hard = schema.scope == "user"
                if node_type == "vocab_value":
                    if not parent_set_code:
                        raise ChildNotFoundError("vocab value (no set)")
                    vset = await conn.fetchval(
                        "SELECT vocab_set_id FROM kg_vocab_sets "
                        "WHERE schema_id = $1 AND code = $2 AND deprecated_at IS NULL",
                        schema_id, parent_set_code,
                    )
                    if vset is None:
                        raise ChildNotFoundError(f"vocab set '{parent_set_code}'")
                    changed = await self._del_row(
                        conn, "kg_vocab_values", "vocab_set_id = $1 AND code = $2",
                        [vset, code], hard=hard,
                    )
                else:
                    table, code_col = self._DELETE_TARGET[node_type]
                    changed = await self._del_row(
                        conn, table, f"schema_id = $1 AND {code_col} = $2",
                        [schema_id, code], hard=hard,
                    )
                if not changed:
                    raise ChildNotFoundError(code)
                await self._bump_and_rehash(conn, schema_id)

    async def widen_edge_target_kinds(
        self, schema_id: UUID, *, code: str, add_kinds: list[str]
    ) -> dict:
        """Additively widen a live edge type's ``target_node_kinds`` (E3 —
        widen_target_kinds resolution). Union (idempotent) so a kind already
        present is a no-op; raises ChildNotFoundError if the edge type is gone /
        deprecated. Bumps schema_version + rehashes (a schema-shape change).

        Gate assumption: only reachable through the class-C confirm spine
        (kg_actions.confirm_action), which re-checks MANAGE on the schema's
        project before the effect. `_load_writable` additionally refuses a
        System-tier schema. Do NOT add an ungated caller."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._load_writable(conn, schema_id)
                row = await conn.fetchrow(
                    "SELECT target_node_kinds FROM kg_edge_types "
                    "WHERE schema_id = $1 AND code = $2 AND deprecated_at IS NULL FOR UPDATE",
                    schema_id, code,
                )
                if row is None:
                    raise ChildNotFoundError(code)
                current = list(row["target_node_kinds"] or [])
                merged = current + [k for k in add_kinds if k and k not in current]
                if merged != current:
                    await conn.execute(
                        "UPDATE kg_edge_types SET target_node_kinds = $3 "
                        "WHERE schema_id = $1 AND code = $2",
                        schema_id, code, merged,
                    )
                    await self._bump_and_rehash(conn, schema_id)
        return {"code": code, "target_node_kinds": merged}

    async def set_edge_cardinality(
        self, schema_id: UUID, *, code: str, cardinality: str
    ) -> dict:
        """Set a live edge type's ``cardinality`` (E3 — set_multi_active resolution
        flips a single_active type to multi_active so coexisting instances stop
        triaging as cardinality conflicts). Raises ChildNotFoundError if gone;
        bumps schema_version + rehashes.

        Gate assumption: only reachable through the class-C confirm spine
        (kg_actions.confirm_action), which re-checks MANAGE on the schema's
        project before the effect. `_load_writable` additionally refuses a
        System-tier schema. Do NOT add an ungated caller."""
        if cardinality not in ("single_active", "multi_active"):
            raise ValueError("cardinality must be single_active|multi_active")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._load_writable(conn, schema_id)
                res = await conn.execute(
                    "UPDATE kg_edge_types SET cardinality = $3 "
                    "WHERE schema_id = $1 AND code = $2 AND deprecated_at IS NULL",
                    schema_id, code, cardinality,
                )
                if res.endswith(" 0"):
                    raise ChildNotFoundError(code)
                await self._bump_and_rehash(conn, schema_id)
        return {"code": code, "cardinality": cardinality}

    async def deprecate_edge_type(self, schema_id: UUID, code: str) -> None:
        await self._deprecate_child(schema_id, "kg_edge_types", "code", code)

    async def deprecate_fact_type(self, schema_id: UUID, code: str) -> None:
        await self._deprecate_child(schema_id, "kg_fact_types", "code", code)

    async def deprecate_node_kind(self, schema_id: UUID, kind_code: str) -> None:
        await self._deprecate_child(schema_id, "kg_schema_node_kinds", "kind_code", kind_code)

    async def _deprecate_child(
        self, schema_id: UUID, table: str, code_col: str, code: str
    ) -> None:
        """Deprecate-only (M3): never hard-drop a type that may have data (A4)."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await self._load_writable(conn, schema_id)
                res = await conn.execute(
                    f"UPDATE {table} SET deprecated_at = now() "
                    f"WHERE schema_id = $1 AND {code_col} = $2 AND deprecated_at IS NULL",
                    schema_id, code,
                )
                if res.endswith(" 0"):
                    raise ChildNotFoundError(code)
                await self._bump_and_rehash(conn, schema_id)

    # ── sync (tree diff + apply) ───────────────────────────────────────────
    async def sync_diff(self, project_schema_id: UUID) -> dict:
        """Tree-granular diff of a project schema vs its upstream source.

        Compares the project schema's frozen `source_hash` against the source's
        current `content_hash` (recomputed). When they differ, walks both trees
        and emits per-child `added` / `modified` / `removed_upstream` changes.
        `added`/`removed_upstream` are from the UPSTREAM's point of view: a child
        present upstream but not in the project copy is `added` (the user could
        take it); a child the project has but upstream removed is `removed_upstream`.
        """
        async with self._pool.acquire() as conn:
            proj = await conn.fetchrow(
                "SELECT source_ref, source_hash FROM kg_graph_schemas WHERE schema_id = $1",
                project_schema_id,
            )
            if proj is None or not proj["source_ref"]:
                return {
                    "source_ref": proj["source_ref"] if proj else None,
                    "source_hash_current": None,
                    "project_source_hash": proj["source_hash"] if proj else None,
                    "has_updates": False,
                    "changes": [],
                }
            source_id = UUID(proj["source_ref"].split(":", 1)[1])
            src_row = await conn.fetchrow(
                "SELECT schema_id FROM kg_graph_schemas WHERE schema_id = $1", source_id
            )
            if src_row is None:  # upstream source gone — nothing to sync against
                return {
                    "source_ref": proj["source_ref"],
                    "source_hash_current": None,
                    "project_source_hash": proj["source_hash"],
                    "has_updates": False,
                    "changes": [],
                }
            current_hash = await _compute_content_hash(conn, source_id)
            has_updates = current_hash != proj["source_hash"]
            changes: list[dict] = []
            if has_updates:
                up = await _tree_surface(conn, source_id)
                mine = await _tree_surface(conn, project_schema_id)
                changes = _diff_trees(up, mine)
            return {
                "source_ref": proj["source_ref"],
                "source_hash_current": current_hash,
                "project_source_hash": proj["source_hash"],
                "has_updates": has_updates,
                "changes": changes,
            }

    async def sync_apply(
        self, project_schema_id: UUID, *, base_source_hash: str, decisions: list[dict]
    ) -> dict:
        """Apply per-node keep_mine/take_theirs. Forward-only (M3 — no recompute).

        Optimistic-concurrency: if the upstream source's current content_hash no
        longer equals `base_source_hash` (the token from /sync/available), raise
        `SyncConflictError` (409). Otherwise apply `take_theirs` decisions
        (added → copy in; modified → overwrite mine; removed_upstream → deprecate
        mine), then refreeze `source_hash` to the source's current hash and bump
        `schema_version`.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Serialize against a concurrent re-adopt that could deprecate this
                # row + insert a new active one mid-apply (MED, TOCTOU). project_id
                # is the schema's scope_id.
                pid = await conn.fetchval(
                    "SELECT scope_id FROM kg_graph_schemas WHERE schema_id = $1", project_schema_id
                )
                if pid:
                    await _lock_project(conn, pid)
                proj = await conn.fetchrow(
                    "SELECT source_ref, source_hash, deprecated_at FROM kg_graph_schemas "
                    "WHERE schema_id = $1 FOR UPDATE",
                    project_schema_id,
                )
                if proj is None or not proj["source_ref"]:
                    raise SchemaNotWritableError("project schema has no upstream source")
                if proj["deprecated_at"] is not None:
                    # a concurrent re-adopt deprecated this copy — don't mutate a dead row
                    raise SyncConflictError("project schema was replaced (re-adopted)")
                source_id = UUID(proj["source_ref"].split(":", 1)[1])
                current_hash = await _compute_content_hash(conn, source_id)
                if current_hash != base_source_hash:
                    raise SyncConflictError(
                        "upstream moved since /sync/available was read"
                    )
                applied = 0
                for d in decisions:
                    if d.get("choice") != "take_theirs":
                        continue
                    if await self._apply_take_theirs(conn, source_id, project_schema_id, d):
                        applied += 1
                new_version = await conn.fetchval(
                    """
                    UPDATE kg_graph_schemas
                    SET source_hash = $2, schema_version = schema_version + 1, updated_at = now()
                    WHERE schema_id = $1
                    RETURNING schema_version
                    """,
                    project_schema_id, current_hash,
                )
                await self._recompute_hash(conn, project_schema_id)
        return {"schema_version": new_version, "source_hash": current_hash, "applied": applied}

    async def _apply_take_theirs(
        self, conn: asyncpg.Connection, source_id: UUID, dst_id: UUID, decision: dict
    ) -> bool:
        """Apply one take_theirs decision; returns True if a change landed."""
        node_type = decision.get("node_type")
        code = decision.get("code")
        parent_code = decision.get("parent_code")
        if node_type == "edge_type":
            return await self._take_child(
                conn, source_id, dst_id, "kg_edge_types", "code", code,
                ["label", "directed", "source_node_kinds", "target_node_kinds",
                 "temporal", "provenance_required", "cardinality", "description"],
            )
        if node_type == "fact_type":
            return await self._take_child(
                conn, source_id, dst_id, "kg_fact_types", "code", code, ["label", "description"]
            )
        if node_type == "node_kind":
            return await self._take_child(
                conn, source_id, dst_id, "kg_schema_node_kinds", "kind_code", code, ["strength"]
            )
        if node_type == "vocab_set":
            return await self._take_vocab_set(conn, source_id, dst_id, code)
        if node_type == "vocab_value":
            return await self._take_vocab_value(conn, source_id, dst_id, parent_code, code)
        return False

    async def _take_child(
        self,
        conn: asyncpg.Connection,
        source_id: UUID,
        dst_id: UUID,
        table: str,
        code_col: str,
        code: str,
        cols: list[str],
    ) -> bool:
        up = await conn.fetchrow(
            f"SELECT * FROM {table} WHERE schema_id = $1 AND {code_col} = $2", source_id, code
        )
        mine = await conn.fetchrow(
            f"SELECT * FROM {table} WHERE schema_id = $1 AND {code_col} = $2", dst_id, code
        )
        if up is None:
            # removed_upstream → deprecate mine (never hard-drop; A4).
            if mine is not None and mine["deprecated_at"] is None:
                await conn.execute(
                    f"UPDATE {table} SET deprecated_at = now() WHERE schema_id = $1 AND {code_col} = $2",
                    dst_id, code,
                )
                return True
            return False
        if mine is None:
            # added upstream → insert a copy under the project.
            insert_cols = [code_col] + cols
            placeholders = ", ".join(f"${i + 2}" for i in range(len(insert_cols)))
            values = [up[c] for c in insert_cols]
            await conn.execute(
                f"INSERT INTO {table} (schema_id, {', '.join(insert_cols)}) "
                f"VALUES ($1, {placeholders})",
                dst_id, *values,
            )
            return True
        # modified upstream → overwrite mine (+ un-deprecate if reintroduced).
        set_clause = ", ".join(f"{c} = ${i + 3}" for i, c in enumerate(cols))
        await conn.execute(
            f"UPDATE {table} SET {set_clause}, deprecated_at = NULL "
            f"WHERE schema_id = $1 AND {code_col} = $2",
            dst_id, code, *[up[c] for c in cols],
        )
        return True

    async def _take_vocab_set(
        self, conn: asyncpg.Connection, source_id: UUID, dst_id: UUID, code: str
    ) -> bool:
        up = await conn.fetchrow(
            "SELECT label, description, closed FROM kg_vocab_sets WHERE schema_id = $1 AND code = $2",
            source_id, code,
        )
        mine = await conn.fetchrow(
            "SELECT vocab_set_id FROM kg_vocab_sets WHERE schema_id = $1 AND code = $2",
            dst_id, code,
        )
        if up is None:
            if mine is not None:
                await conn.execute(
                    "UPDATE kg_vocab_sets SET deprecated_at = now() WHERE schema_id = $1 AND code = $2",
                    dst_id, code,
                )
                return True
            return False
        if mine is None:
            # HIGH: a newly-added upstream set must bring its VALUES too — else
            # take_theirs inserts an EMPTY closed vocab set and extraction can
            # assign nothing. Copy the set + all its values atomically (mirrors
            # adopt's _copy_children), independent of value-decision ordering.
            new_set_id = await conn.fetchval(
                "INSERT INTO kg_vocab_sets (schema_id, code, label, description, closed) "
                "VALUES ($1, $2, $3, $4, $5) RETURNING vocab_set_id",
                dst_id, code, up["label"], up["description"], up["closed"],
            )
            up_set_id = await conn.fetchval(
                "SELECT vocab_set_id FROM kg_vocab_sets WHERE schema_id = $1 AND code = $2",
                source_id, code,
            )
            await conn.execute(
                """
                INSERT INTO kg_vocab_values (vocab_set_id, code, label, metadata)
                SELECT $1, code, label, metadata FROM kg_vocab_values
                WHERE vocab_set_id = $2 AND deprecated_at IS NULL
                """,
                new_set_id, up_set_id,
            )
            return True
        await conn.execute(
            "UPDATE kg_vocab_sets SET label = $3, description = $4, closed = $5, deprecated_at = NULL "
            "WHERE schema_id = $1 AND code = $2",
            dst_id, code, up["label"], up["description"], up["closed"],
        )
        return True

    async def _take_vocab_value(
        self, conn: asyncpg.Connection, source_id: UUID, dst_id: UUID, set_code: str | None, code: str
    ) -> bool:
        if not set_code:
            return False
        up_set = await conn.fetchval(
            "SELECT vocab_set_id FROM kg_vocab_sets WHERE schema_id = $1 AND code = $2",
            source_id, set_code,
        )
        my_set = await conn.fetchval(
            "SELECT vocab_set_id FROM kg_vocab_sets WHERE schema_id = $1 AND code = $2",
            dst_id, set_code,
        )
        if my_set is None:
            return False  # parent set must be taken first
        up = await conn.fetchrow(
            "SELECT label, metadata FROM kg_vocab_values WHERE vocab_set_id = $1 AND code = $2",
            up_set, code,
        ) if up_set else None
        mine = await conn.fetchrow(
            "SELECT vocab_value_id, deprecated_at FROM kg_vocab_values WHERE vocab_set_id = $1 AND code = $2",
            my_set, code,
        )
        if up is None:
            # HIGH: removed_upstream → DEPRECATE, never hard-DELETE (A4 — graph data
            # may reference this drive value by code; keep it queryable). Mirrors the
            # set/edge/fact removed_upstream paths.
            if mine is not None and mine["deprecated_at"] is None:
                await conn.execute(
                    "UPDATE kg_vocab_values SET deprecated_at = now() WHERE vocab_set_id = $1 AND code = $2",
                    my_set, code,
                )
                return True
            return False
        if mine is None:
            await conn.execute(
                "INSERT INTO kg_vocab_values (vocab_set_id, code, label, metadata) "
                "VALUES ($1, $2, $3, $4)",
                my_set, code, up["label"], up["metadata"],
            )
            return True
        # modified (or reintroduced) → overwrite + un-deprecate.
        await conn.execute(
            "UPDATE kg_vocab_values SET label = $3, metadata = $4, deprecated_at = NULL "
            "WHERE vocab_set_id = $1 AND code = $2",
            my_set, code, up["label"], up["metadata"],
        )
        return True

    # ── internal ───────────────────────────────────────────────────────────
    async def _load_writable(self, conn: asyncpg.Connection, schema_id: UUID) -> GraphSchema:
        """Lock the schema row + assert it is a user/project (writable) tier.

        System rows are read-only over this repo (tenancy). A missing row also
        raises `SchemaNotWritableError` (router maps to 404/403; the grant gate
        already proved scope visibility before we reach here)."""
        row = await conn.fetchrow(
            f"SELECT {_SCHEMA_COLS} FROM kg_graph_schemas WHERE schema_id = $1 FOR UPDATE", schema_id
        )
        if row is None:
            raise SchemaNotWritableError("schema not found")
        schema = _row_to_schema(row)
        if schema.scope == "system":
            raise SchemaNotWritableError("system-tier schema is read-only")
        return schema

    async def _revive_or_insert(
        self,
        conn: asyncpg.Connection,
        *,
        table: str,
        key_cols: dict[str, Any],
        attr_cols: dict[str, Any],
        returning: str,
    ) -> asyncpg.Record:
        """Revive-on-recreate (EC-A1). The child tables keep a TOTAL
        `UNIQUE(schema_id, code)`; re-creating a code whose row was soft-deprecated
        would otherwise 409 forever. So: a LIVE row of this code → DuplicateChildError;
        a DEPRECATED row → un-deprecate + overwrite its attrs (one row per code, the
        stable graph-data reference key); no row → INSERT. `key_cols` identify the row
        (schema_id+code, or vocab_set_id+code for values); `attr_cols` are the mutable
        attributes."""
        key_where = " AND ".join(f"{c} = ${i + 1}" for i, c in enumerate(key_cols))
        key_vals = list(key_cols.values())
        existing = await conn.fetchrow(
            f"SELECT deprecated_at FROM {table} WHERE {key_where}", *key_vals
        )
        if existing is not None and existing["deprecated_at"] is None:
            raise DuplicateChildError(str(key_vals[-1]))
        if existing is not None:  # revive: un-deprecate + overwrite attributes
            set_clause = ", ".join(
                f"{c} = ${len(key_cols) + i + 1}" for i, c in enumerate(attr_cols)
            )
            return await conn.fetchrow(
                f"UPDATE {table} SET {set_clause}, deprecated_at = NULL "
                f"WHERE {key_where} RETURNING {returning}",
                *key_vals, *attr_cols.values(),
            )
        cols = list(key_cols) + list(attr_cols)
        vals = key_vals + list(attr_cols.values())
        placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
        try:
            return await conn.fetchrow(
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
                f"RETURNING {returning}",
                *vals,
            )
        except asyncpg.UniqueViolationError as exc:  # belt-and-suspenders (schema-lock serializes)
            raise DuplicateChildError(str(key_vals[-1])) from exc

    async def _patch_child(
        self,
        conn: asyncpg.Connection,
        table: str,
        *,
        where: str,
        where_vals: list[Any],
        updates: dict[str, Any],
        returning: str,
    ) -> tuple[asyncpg.Record, bool]:
        """PATCH a LIVE child's attributes (code IMMUTABLE, EC-A6). Returns
        (row, changed). Empty `updates` → fetch current (no-op, changed=False).
        A missing/deprecated target → ChildNotFoundError."""
        live = f"{where} AND deprecated_at IS NULL"
        if not updates:
            row = await conn.fetchrow(
                f"SELECT {returning} FROM {table} WHERE {live}", *where_vals
            )
            if row is None:
                raise ChildNotFoundError(str(where_vals[-1]))
            return row, False
        set_clause = ", ".join(
            f"{c} = ${len(where_vals) + i + 1}" for i, c in enumerate(updates)
        )
        row = await conn.fetchrow(
            f"UPDATE {table} SET {set_clause} WHERE {live} RETURNING {returning}",
            *where_vals, *updates.values(),
        )
        if row is None:
            raise ChildNotFoundError(str(where_vals[-1]))
        return row, True

    async def _del_row(
        self, conn: asyncpg.Connection, table: str, where: str, params: list[Any], *, hard: bool
    ) -> bool:
        """Delete one child: HARD `DELETE` on a user-tier template, SOFT deprecate on
        a project schema (EC-A5). Returns True if a row was affected."""
        if hard:
            res = await conn.execute(f"DELETE FROM {table} WHERE {where}", *params)
        else:
            res = await conn.execute(
                f"UPDATE {table} SET deprecated_at = now() WHERE {where} AND deprecated_at IS NULL",
                *params,
            )
        return not res.endswith(" 0")

    async def _bump_and_rehash(self, conn: asyncpg.Connection, schema_id: UUID) -> None:
        await conn.execute(
            "UPDATE kg_graph_schemas SET schema_version = schema_version + 1, updated_at = now() "
            "WHERE schema_id = $1",
            schema_id,
        )
        await self._recompute_hash(conn, schema_id)

    async def _recompute_hash(self, conn: asyncpg.Connection, schema_id: UUID) -> None:
        chash = await _compute_content_hash(conn, schema_id)
        await conn.execute(
            "UPDATE kg_graph_schemas SET content_hash = $2 WHERE schema_id = $1", schema_id, chash
        )


# ── re-adopt loss preview (D-KG-LC-REVADOPT-LOSS) ──────────────────────────
# "What will you LOSE if you re-adopt?" — `adopt` deprecates the project's active
# schema and replaces it with a fresh copy of the incoming source. Any child the
# CURRENT copy has but the INCOMING source lacks (or has differently) is silently
# dropped/overwritten. We reuse the sync tree-diff, framing `incoming` as the
# "upstream" the project would move to and `current` as "mine": a child present in
# current-only is `removed_upstream` (vanishes → loss); a child present in both but
# differing is `modified` (overwritten → loss). An `added` change is incoming-only
# (a GAIN) and never a loss.
_LOSS_CHANGES = ("removed_upstream", "modified")


def compute_adopt_losses(*, current: dict, incoming: dict) -> list[dict]:
    """Pure: diff two tree surfaces and return only the losing changes.

    `current`/`incoming` are `_tree_surface`-shaped dicts. Returns the subset of
    `_diff_trees(incoming, current)` whose `change` is removed_upstream/modified —
    i.e. the customizations re-adopt would drop or overwrite.
    """
    return [c for c in _diff_trees(incoming, current) if c["change"] in _LOSS_CHANGES]


# ── pure tree-diff (unit-testable) ─────────────────────────────────────────
def _diff_trees(upstream: dict, mine: dict) -> list[dict]:
    """Per-child diff of two tree surfaces (upstream vs project copy).

    Returns `SyncChange`-shaped dicts. A child upstream-only = `added`;
    project-only = `removed_upstream`; in both but differing = `modified` with
    `fields_changed`. Vocab values diff under their set (`parent_code`).
    """
    changes: list[dict] = []
    changes += _diff_list(upstream["edge_types"], mine["edge_types"], "edge_type", key="code")
    changes += _diff_list(upstream["fact_types"], mine["fact_types"], "fact_type", key=0, pair=True)
    changes += _diff_list(upstream["node_kinds"], mine["node_kinds"], "node_kind", key=0, pair=True, pair_field="strength")
    changes += _diff_vocab(upstream["vocab_sets"], mine["vocab_sets"])
    return changes


def _diff_list(
    up: list, mine: list, node_type: str, *, key, pair: bool = False,
    pair_field: str = "label",
) -> list[dict]:
    """Diff two lists of children. `pair=True` => items are `[code, <pair_field>]`
    lists (the 2nd element's name is `pair_field` — "label" for fact_types,
    "strength" for node_kinds; D-KG-SYNC-DIFF-LABEL: hardcoding "label" mislabelled
    a node-kind's strength as a label in the diff); else dicts keyed by `key`."""
    def code_of(item):
        return item[key] if pair else item[key]

    def fields_of(item):
        if pair:
            return {"code": item[0], pair_field: item[1]}
        return dict(item)

    up_by = {code_of(i): fields_of(i) for i in up}
    mine_by = {code_of(i): fields_of(i) for i in mine}
    out: list[dict] = []
    for code, uf in up_by.items():
        if code not in mine_by:
            out.append({
                "node_type": node_type, "parent_code": None, "code": code,
                "change": "added", "fields_changed": sorted(uf.keys()),
                "upstream": uf, "mine": None,
            })
        else:
            mf = mine_by[code]
            changed = sorted(k for k in uf if uf.get(k) != mf.get(k))
            if changed:
                out.append({
                    "node_type": node_type, "parent_code": None, "code": code,
                    "change": "modified", "fields_changed": changed,
                    "upstream": uf, "mine": mf,
                })
    for code, mf in mine_by.items():
        if code not in up_by:
            out.append({
                "node_type": node_type, "parent_code": None, "code": code,
                "change": "removed_upstream", "fields_changed": [],
                "upstream": None, "mine": mf,
            })
    return sorted(out, key=lambda c: (c["code"], c["change"]))


def _diff_vocab(up_sets: list[dict], mine_sets: list[dict]) -> list[dict]:
    """Diff vocab sets + their values (values carry parent_code = set code)."""
    out: list[dict] = []
    up_by = {s["code"]: s for s in up_sets}
    mine_by = {s["code"]: s for s in mine_sets}
    for code, us in up_by.items():
        ms = mine_by.get(code)
        if ms is None:
            out.append({
                "node_type": "vocab_set", "parent_code": None, "code": code,
                "change": "added", "fields_changed": ["label", "closed", "values"],
                "upstream": {"label": us["label"], "closed": us["closed"]}, "mine": None,
            })
            continue
        set_fields = sorted(
            k for k in ("label", "description", "closed") if us.get(k) != ms.get(k)
        )
        if set_fields:
            out.append({
                "node_type": "vocab_set", "parent_code": None, "code": code,
                "change": "modified", "fields_changed": set_fields,
                "upstream": {k: us.get(k) for k in set_fields},
                "mine": {k: ms.get(k) for k in set_fields},
            })
        out += _diff_vocab_values(code, us["values"], ms["values"])
    for code, ms in mine_by.items():
        if code not in up_by:
            out.append({
                "node_type": "vocab_set", "parent_code": None, "code": code,
                "change": "removed_upstream", "fields_changed": [],
                "upstream": None, "mine": {"label": ms["label"], "closed": ms["closed"]},
            })
    return out


def _diff_vocab_values(set_code: str, up_vals: list, mine_vals: list) -> list[dict]:
    up_by = {v[0]: {"label": v[1], "metadata": v[2]} for v in up_vals}
    mine_by = {v[0]: {"label": v[1], "metadata": v[2]} for v in mine_vals}
    out: list[dict] = []
    for code, uf in up_by.items():
        if code not in mine_by:
            out.append({
                "node_type": "vocab_value", "parent_code": set_code, "code": code,
                "change": "added", "fields_changed": ["label", "metadata"],
                "upstream": uf, "mine": None,
            })
        else:
            mf = mine_by[code]
            changed = sorted(k for k in uf if uf.get(k) != mf.get(k))
            if changed:
                out.append({
                    "node_type": "vocab_value", "parent_code": set_code, "code": code,
                    "change": "modified", "fields_changed": changed,
                    "upstream": uf, "mine": mf,
                })
    for code, mf in mine_by.items():
        if code not in up_by:
            out.append({
                "node_type": "vocab_value", "parent_code": set_code, "code": code,
                "change": "removed_upstream", "fields_changed": [],
                "upstream": None, "mine": mf,
            })
    return out
