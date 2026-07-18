"""style_profile + voice_profile repositories — LOOM T3.5 prose-style steering.

SCOPE RULE (package re-key, spec 25 §Repo/service layer + M3.4): profiles are
PACKAGE-scoped, keyed on `project_id` — access is decided BEFORE the repo, at
the gate (E0 grant on the row's `book_id`). Writes stamp `created_by` (a plain
actor stamp — STORED, never filtered on; updated on conflict so it records the
last writer) and derive `book_id` from composition_work inside the INSERT.
Upserts conflict on the M3.4 PKs — (project_id, scope_type, scope_id) /
(project_id, entity_id) — so a grantee's re-edit replaces the shared row in
place instead of minting a second actor-keyed row (DA-11).

StyleProfile: per-scope Density/Pace (0-100). `resolve` returns the MOST SPECIFIC
row for a scene (scene > chapter > work) — the value the packer threads into the
draft prompts. VoiceProfile: per-character voice tags, injected by the packer only
for entities present in the scene (`list_for_entities`).
"""

from __future__ import annotations

import json
from uuid import UUID

import asyncpg

from app.db.models import StyleProfile, VoiceProfile
from app.db.repositories import ReferenceViolationError

_STYLE_COLS = "created_by, project_id, scope_type, scope_id, density, pace, updated_at"
_VOICE_COLS = "created_by, project_id, entity_id, entity_name, tags, updated_at"

# scene beats chapter beats work — the resolution precedence (lower = more specific)
_SCOPE_RANK = "CASE scope_type WHEN 'scene' THEN 0 WHEN 'chapter' THEN 1 ELSE 2 END"


def _row_to_style(row: asyncpg.Record) -> StyleProfile:
    return StyleProfile.model_validate(dict(row))


def _row_to_voice(row: asyncpg.Record) -> VoiceProfile:
    data = dict(row)
    t = data.get("tags")
    if isinstance(t, str):
        data["tags"] = json.loads(t)
    return VoiceProfile.model_validate(data)


class StyleProfileRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def upsert(
        self, project_id: UUID, scope_type: str, scope_id: UUID,
        density: int, pace: int, *, created_by: UUID,
    ) -> StyleProfile:
        """Set the Density/Pace for one scope (work/chapter/scene). Upsert on the
        M3.4 PK (project_id, scope_type, scope_id) so re-editing the same scope
        replaces it in place; `created_by` records the last-writer actor."""
        query = f"""
        INSERT INTO style_profile (created_by, project_id, book_id, scope_type, scope_id, density, pace)
        SELECT $1, $2, w.book_id, $3, $4, $5, $6
        FROM composition_work w WHERE (w.project_id = $2 OR (w.project_id IS NULL AND w.id = $2))
        ON CONFLICT (project_id, scope_type, scope_id)
        DO UPDATE SET density = EXCLUDED.density, pace = EXCLUDED.pace,
                      created_by = EXCLUDED.created_by, updated_at = now()
        RETURNING {_STYLE_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, created_by, project_id, scope_type, scope_id, density, pace)
        if row is None:
            raise ReferenceViolationError(
                f"project {project_id} has no composition work (book scope unresolvable)"
            )
        return _row_to_style(row)

    async def list_all(self, project_id: UUID) -> list[StyleProfile]:
        """Every style row for the Work — the panel shows which scopes are overridden."""
        query = f"""
        SELECT {_STYLE_COLS} FROM style_profile
        WHERE project_id = $1
        ORDER BY {_SCOPE_RANK}, scope_id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, project_id)
        return [_row_to_style(r) for r in rows]

    async def resolve(
        self, project_id: UUID,
        scene_id: UUID | None, chapter_id: UUID | None,
    ) -> StyleProfile | None:
        """The effective style for a scene: the most-specific matching row
        (scene > chapter > work). None when nothing is set (packer stays neutral)."""
        query = f"""
        SELECT {_STYLE_COLS} FROM style_profile
        WHERE project_id = $1 AND (
              (scope_type = 'scene'   AND scope_id = $2)
           OR (scope_type = 'chapter' AND scope_id = $3)
           OR (scope_type = 'work'    AND scope_id = $1)
        )
        ORDER BY {_SCOPE_RANK}
        LIMIT 1
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, project_id, scene_id, chapter_id)
        return _row_to_style(row) if row else None

    async def delete(
        self, project_id: UUID, scope_type: str, scope_id: UUID,
    ) -> bool:
        """Clear one scope's override (revert to the next-less-specific). True if a
        row was removed."""
        query = """
        DELETE FROM style_profile
        WHERE project_id = $1 AND scope_type = $2 AND scope_id = $3
        """
        async with self._pool.acquire() as c:
            result = await c.execute(query, project_id, scope_type, scope_id)
        return result.rsplit(" ", 1)[-1] != "0"


class VoiceProfileRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def upsert(
        self, project_id: UUID, entity_id: UUID,
        entity_name: str, tags: list[str], *, created_by: UUID,
    ) -> VoiceProfile:
        """Set a character's voice tags. Upsert on the M3.4 PK (project_id,
        entity_id); `created_by` records the last-writer actor."""
        query = f"""
        INSERT INTO voice_profile (created_by, project_id, book_id, entity_id, entity_name, tags)
        SELECT $1, $2, w.book_id, $3, $4, $5::jsonb
        FROM composition_work w WHERE (w.project_id = $2 OR (w.project_id IS NULL AND w.id = $2))
        ON CONFLICT (project_id, entity_id)
        DO UPDATE SET entity_name = EXCLUDED.entity_name, tags = EXCLUDED.tags,
                      created_by = EXCLUDED.created_by, updated_at = now()
        RETURNING {_VOICE_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query, created_by, project_id, entity_id, entity_name, json.dumps(list(tags)),
            )
        if row is None:
            raise ReferenceViolationError(
                f"project {project_id} has no composition work (book scope unresolvable)"
            )
        return _row_to_voice(row)

    async def list_all(self, project_id: UUID) -> list[VoiceProfile]:
        query = f"""
        SELECT {_VOICE_COLS} FROM voice_profile
        WHERE project_id = $1
        ORDER BY entity_name, entity_id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, project_id)
        return [_row_to_voice(r) for r in rows]

    async def list_for_entities(
        self, project_id: UUID, entity_ids: list[UUID],
    ) -> list[VoiceProfile]:
        """The voice profiles for a set of present entities — the packer's present-
        only injection. Empty list when no ids (no query)."""
        if not entity_ids:
            return []
        query = f"""
        SELECT {_VOICE_COLS} FROM voice_profile
        WHERE project_id = $1 AND entity_id = ANY($2::uuid[])
        ORDER BY entity_name, entity_id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, project_id, list(entity_ids))
        return [_row_to_voice(r) for r in rows]

    async def delete(self, project_id: UUID, entity_id: UUID) -> bool:
        query = """
        DELETE FROM voice_profile
        WHERE project_id = $1 AND entity_id = $2
        """
        async with self._pool.acquire() as c:
            result = await c.execute(query, project_id, entity_id)
        return result.rsplit(" ", 1)[-1] != "0"
