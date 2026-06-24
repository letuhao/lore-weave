"""divergence_spec + entity_override repository (C23 — dị bản M0).

The COW delta substrate for a DERIVATIVE Work: one `divergence_spec` (taxonomy +
optional pov_anchor + added canon_rule[]) and zero-or-more `entity_override` rows
(per-entity FIELD overrides — M0 scope; relationship/event overrides DEFERRED).

SECURITY RULE (M5 isolation): every method takes `user_id` and every read filters
`user_id = $1`. These rows are PERSISTED here; the packer applies the overrides at
retrieval in C25 (this cycle does NOT apply them — COW persist-only).
"""

from __future__ import annotations

import json
from uuid import UUID

import asyncpg

from app.db.models import DivergenceSpec, EntityOverride

_SPEC_COLS = "id, user_id, project_id, work_id, taxonomy, pov_anchor, canon_rule, created_at"
_OVERRIDE_COLS = (
    "id, user_id, project_id, work_id, target_entity_id, overridden_fields, created_at"
)


def _row_to_override(row: asyncpg.Record) -> EntityOverride:
    data = dict(row)
    f = data.get("overridden_fields")
    if isinstance(f, str):
        data["overridden_fields"] = json.loads(f)
    return EntityOverride.model_validate(data)


class DerivativesRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create_spec(
        self, spec: DivergenceSpec, *, conn: asyncpg.Connection | None = None
    ) -> DivergenceSpec:
        """Insert the divergence_spec for a derivative Work."""
        query = f"""
        INSERT INTO divergence_spec
          (user_id, project_id, work_id, taxonomy, pov_anchor, canon_rule)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING {_SPEC_COLS}
        """
        args = (
            spec.user_id, spec.project_id, spec.work_id, spec.taxonomy,
            spec.pov_anchor, list(spec.canon_rule),
        )
        if conn is not None:
            row = await conn.fetchrow(query, *args)
        else:
            async with self._pool.acquire() as c:
                row = await c.fetchrow(query, *args)
        return DivergenceSpec.model_validate(dict(row))

    async def create_override(
        self, override: EntityOverride, *, conn: asyncpg.Connection | None = None
    ) -> EntityOverride:
        """Insert one entity_override (entity-field delta) for a derivative Work."""
        query = f"""
        INSERT INTO entity_override
          (user_id, project_id, work_id, target_entity_id, overridden_fields)
        VALUES ($1, $2, $3, $4, $5::jsonb)
        RETURNING {_OVERRIDE_COLS}
        """
        args = (
            override.user_id, override.project_id, override.work_id,
            override.target_entity_id, json.dumps(override.overridden_fields or {}),
        )
        if conn is not None:
            row = await conn.fetchrow(query, *args)
        else:
            async with self._pool.acquire() as c:
                row = await c.fetchrow(query, *args)
        return _row_to_override(row)

    async def get_spec_for_work(
        self, user_id: UUID, work_id: UUID
    ) -> DivergenceSpec | None:
        query = f"""
        SELECT {_SPEC_COLS} FROM divergence_spec
        WHERE user_id = $1 AND work_id = $2
        ORDER BY created_at
        LIMIT 1
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, user_id, work_id)
        return DivergenceSpec.model_validate(dict(row)) if row else None

    async def list_overrides_for_work(
        self, user_id: UUID, work_id: UUID
    ) -> list[EntityOverride]:
        query = f"""
        SELECT {_OVERRIDE_COLS} FROM entity_override
        WHERE user_id = $1 AND work_id = $2
        ORDER BY created_at
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, user_id, work_id)
        return [_row_to_override(r) for r in rows]
