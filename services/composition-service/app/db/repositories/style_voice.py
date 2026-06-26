"""style_profile + voice_profile repositories — LOOM T3.5 prose-style steering.

SECURITY (M5 isolation): every method takes `user_id` first and filters on it —
these are the user's own authoring config (per-user), so a cross-user read is empty.

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

_STYLE_COLS = "user_id, project_id, scope_type, scope_id, density, pace, updated_at"
_VOICE_COLS = "user_id, project_id, entity_id, entity_name, tags, updated_at"

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
        self, user_id: UUID, project_id: UUID, scope_type: str, scope_id: UUID,
        density: int, pace: int,
    ) -> StyleProfile:
        """Set the Density/Pace for one scope (work/chapter/scene). Upsert on the PK
        so re-editing the same scope replaces it in place."""
        query = f"""
        INSERT INTO style_profile (user_id, project_id, scope_type, scope_id, density, pace)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (user_id, project_id, scope_type, scope_id)
        DO UPDATE SET density = EXCLUDED.density, pace = EXCLUDED.pace, updated_at = now()
        RETURNING {_STYLE_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, user_id, project_id, scope_type, scope_id, density, pace)
        return _row_to_style(row)

    async def list_all(self, user_id: UUID, project_id: UUID) -> list[StyleProfile]:
        """Every style row for the Work — the panel shows which scopes are overridden."""
        query = f"""
        SELECT {_STYLE_COLS} FROM style_profile
        WHERE user_id = $1 AND project_id = $2
        ORDER BY {_SCOPE_RANK}, scope_id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, user_id, project_id)
        return [_row_to_style(r) for r in rows]

    async def resolve(
        self, user_id: UUID, project_id: UUID,
        scene_id: UUID | None, chapter_id: UUID | None,
    ) -> StyleProfile | None:
        """The effective style for a scene: the most-specific matching row
        (scene > chapter > work). None when nothing is set (packer stays neutral)."""
        query = f"""
        SELECT {_STYLE_COLS} FROM style_profile
        WHERE user_id = $1 AND project_id = $2 AND (
              (scope_type = 'scene'   AND scope_id = $3)
           OR (scope_type = 'chapter' AND scope_id = $4)
           OR (scope_type = 'work'    AND scope_id = $2)
        )
        ORDER BY {_SCOPE_RANK}
        LIMIT 1
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(query, user_id, project_id, scene_id, chapter_id)
        return _row_to_style(row) if row else None

    async def delete(
        self, user_id: UUID, project_id: UUID, scope_type: str, scope_id: UUID,
    ) -> bool:
        """Clear one scope's override (revert to the next-less-specific). True if a
        row was removed."""
        query = """
        DELETE FROM style_profile
        WHERE user_id = $1 AND project_id = $2 AND scope_type = $3 AND scope_id = $4
        """
        async with self._pool.acquire() as c:
            result = await c.execute(query, user_id, project_id, scope_type, scope_id)
        return result.rsplit(" ", 1)[-1] != "0"


class VoiceProfileRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def upsert(
        self, user_id: UUID, project_id: UUID, entity_id: UUID,
        entity_name: str, tags: list[str],
    ) -> VoiceProfile:
        """Set a character's voice tags. Upsert on (user, project, entity)."""
        query = f"""
        INSERT INTO voice_profile (user_id, project_id, entity_id, entity_name, tags)
        VALUES ($1, $2, $3, $4, $5::jsonb)
        ON CONFLICT (user_id, project_id, entity_id)
        DO UPDATE SET entity_name = EXCLUDED.entity_name, tags = EXCLUDED.tags, updated_at = now()
        RETURNING {_VOICE_COLS}
        """
        async with self._pool.acquire() as c:
            row = await c.fetchrow(
                query, user_id, project_id, entity_id, entity_name, json.dumps(list(tags)),
            )
        return _row_to_voice(row)

    async def list_all(self, user_id: UUID, project_id: UUID) -> list[VoiceProfile]:
        query = f"""
        SELECT {_VOICE_COLS} FROM voice_profile
        WHERE user_id = $1 AND project_id = $2
        ORDER BY entity_name, entity_id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, user_id, project_id)
        return [_row_to_voice(r) for r in rows]

    async def list_for_entities(
        self, user_id: UUID, project_id: UUID, entity_ids: list[UUID],
    ) -> list[VoiceProfile]:
        """The voice profiles for a set of present entities — the packer's present-
        only injection. Empty list when no ids (no query)."""
        if not entity_ids:
            return []
        query = f"""
        SELECT {_VOICE_COLS} FROM voice_profile
        WHERE user_id = $1 AND project_id = $2 AND entity_id = ANY($3::uuid[])
        ORDER BY entity_name, entity_id
        """
        async with self._pool.acquire() as c:
            rows = await c.fetch(query, user_id, project_id, list(entity_ids))
        return [_row_to_voice(r) for r in rows]

    async def delete(self, user_id: UUID, project_id: UUID, entity_id: UUID) -> bool:
        query = """
        DELETE FROM voice_profile
        WHERE user_id = $1 AND project_id = $2 AND entity_id = $3
        """
        async with self._pool.acquire() as c:
            result = await c.execute(query, user_id, project_id, entity_id)
        return result.rsplit(" ", 1)[-1] != "0"
