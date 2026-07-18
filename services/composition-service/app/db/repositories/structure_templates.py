"""structure_template repository — the story-structure library (§5) + S-01 authoring.

Built-in templates have `owner_user_id IS NULL` (seeded in migrate.py); a user may author their own.
The list a user sees = built-ins + their own. S-01 adds the write side (create/update/archive/restore)
that never existed — the table shipped read-only. Tenancy is partial-unique per tier (a user's names
are unique within their own tier; built-ins among built-ins) so this is never the entity_kinds
global-unique bug. Writes NEVER touch an owner-NULL (built-in) row — a user clones a built-in first.
"""

from __future__ import annotations

import json
from uuid import UUID

import asyncpg

from app.db.models import StructureTemplate

_SELECT_COLS = "id, owner_user_id, name, kind, beats, created_at, updated_at, version, is_archived"


class DuplicateStructureTemplateName(Exception):
    """A user already has a template with this name (partial-unique violation) → 409."""


class StructureTemplateVersionConflict(Exception):
    """The row exists but its version != expected_version (OCC) → 412."""


def _row_to_template(row: asyncpg.Record) -> StructureTemplate:
    data = dict(row)
    beats = data.get("beats")
    if isinstance(beats, str):
        data["beats"] = json.loads(beats)
    return StructureTemplate.model_validate(data)


class StructureTemplatesRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ── reads ────────────────────────────────────────────────────────────────

    async def list_for_user(
        self, user_id: UUID, *, include_archived: bool = False
    ) -> list[StructureTemplate]:
        """Built-in (owner NULL) + the user's own. Built-ins first, then name. Built-ins are never
        archived, so the archived filter only affects the user's own rows."""
        archived_clause = "" if include_archived else " AND NOT is_archived"
        query = f"""
        SELECT {_SELECT_COLS} FROM structure_template
        WHERE (owner_user_id IS NULL OR owner_user_id = $1){archived_clause}
        ORDER BY owner_user_id NULLS FIRST, name
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, user_id)
        return [_row_to_template(r) for r in rows]

    async def get(self, user_id: UUID, template_id: UUID) -> StructureTemplate | None:
        """One template the user may use/edit: a built-in (owner NULL) OR their own — archived
        INCLUDED (so restore can target it). Returns None for a missing id or another user's
        custom template (no cross-user leak; the decompose endpoint maps that to 404)."""
        query = f"""
        SELECT {_SELECT_COLS} FROM structure_template
        WHERE id = $1 AND (owner_user_id IS NULL OR owner_user_id = $2)
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, template_id, user_id)
        return _row_to_template(row) if row is not None else None

    # ── writes (S-01) — all owner-scoped; NEVER touch an owner-NULL built-in ──

    async def create(
        self, user_id: UUID, *, name: str, kind: str = "generic", beats: list[dict] | None = None
    ) -> StructureTemplate:
        query = f"""
        INSERT INTO structure_template (owner_user_id, name, kind, beats)
        VALUES ($1, $2, $3, $4::jsonb)
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            try:
                row = await c.fetchrow(query, user_id, name, kind, json.dumps(beats or []))
            except asyncpg.UniqueViolationError as e:
                raise DuplicateStructureTemplateName(name) from e
        return _row_to_template(row)

    async def clone_builtin(self, user_id: UUID, template_id: UUID, *, name: str | None = None) -> StructureTemplate:
        """S-01 slice B entry-point: copy a built-in (or any visible template) into the user's own
        tier so they have an editable starting structure. A user never edits a built-in in place.

        The default name auto-disambiguates ("(copy)", "(copy 2)", …) so cloning the same built-in
        twice does not 409 on UNIQUE(owner_user_id, name) — a real dead-end a live smoke caught."""
        src = await self.get(user_id, template_id)
        if src is None:
            raise LookupError(f"structure template {template_id} not visible")
        if name is not None:
            return await self.create(user_id, name=name, kind=src.kind, beats=src.beats)
        # find the first non-colliding "(copy [n])" name among the user's own templates
        async with self._pool.acquire() as c:
            taken = {
                r["name"] for r in await c.fetch(
                    "SELECT name FROM structure_template WHERE owner_user_id = $1", user_id,
                )
            }
        candidate = f"{src.name} (copy)"
        n = 2
        while candidate in taken:
            candidate = f"{src.name} (copy {n})"
            n += 1
        return await self.create(user_id, name=candidate, kind=src.kind, beats=src.beats)

    async def update(
        self,
        user_id: UUID,
        template_id: UUID,
        expected_version: int,
        *,
        name: str | None = None,
        kind: str | None = None,
        beats: list[dict] | None = None,
    ) -> StructureTemplate | None:
        """OCC update of the user's OWN template (mirror canon_rule.update). Returns None if the row
        is not the user's / not found; raises VersionConflict if it exists but version mismatches;
        raises Duplicate on a name collision."""
        sets: list[str] = ["version = version + 1", "updated_at = now()"]
        params: list = [user_id, template_id, expected_version]
        if name is not None:
            params.append(name)
            sets.append(f"name = ${len(params)}")
        if kind is not None:
            params.append(kind)
            sets.append(f"kind = ${len(params)}")
        if beats is not None:
            params.append(json.dumps(beats))
            sets.append(f"beats = ${len(params)}::jsonb")
        query = f"""
        UPDATE structure_template SET {", ".join(sets)}
        WHERE owner_user_id = $1 AND id = $2 AND version = $3
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            try:
                row = await c.fetchrow(query, *params)
            except asyncpg.UniqueViolationError as e:
                raise DuplicateStructureTemplateName(name or "") from e
            if row is not None:
                return _row_to_template(row)
            # Distinguish "not the user's / gone" from an OCC mismatch (the add-column-if-not-exists
            # OCC idiom): a follow-up existence check on the owned row.
            exists = await c.fetchval(
                "SELECT 1 FROM structure_template WHERE owner_user_id = $1 AND id = $2",
                user_id, template_id,
            )
        if exists:
            raise StructureTemplateVersionConflict(str(template_id))
        return None

    async def archive(self, user_id: UUID, template_id: UUID) -> StructureTemplate | None:
        query = f"""
        UPDATE structure_template SET is_archived = true, updated_at = now()
        WHERE owner_user_id = $1 AND id = $2 AND NOT is_archived
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, user_id, template_id)
        return _row_to_template(row) if row is not None else None

    async def restore(self, user_id: UUID, template_id: UUID) -> StructureTemplate | None:
        query = f"""
        UPDATE structure_template SET is_archived = false, updated_at = now()
        WHERE owner_user_id = $1 AND id = $2 AND is_archived
        RETURNING {_SELECT_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, user_id, template_id)
        return _row_to_template(row) if row is not None else None
