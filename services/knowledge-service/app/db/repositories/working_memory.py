"""session_working_memory repository (M4) — the goal-state block SSOT.

The pinned goal-state block for a roleplay/interview session. `charter` and
`state` are separate columns: this repo exposes `init_charter` (the goal-
authority write path, idempotent + frozen) and `update_state` (the executive's
write path, M5) but **no update_charter** — so the summarizing executive can
structurally never corrupt the goal.

docs/specs/2026-06-23-interview-roleplay.md.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

__all__ = ["WorkingMemoryRepo"]


def _as_dict(v: Any) -> dict[str, Any]:
    if isinstance(v, str):
        return json.loads(v)
    if isinstance(v, dict):
        return v
    return {}


class WorkingMemoryRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def init_charter(self, session_id: UUID, user_id: UUID, charter: dict) -> None:
        """Goal-authority write path: seed the frozen charter ONCE.

        ON CONFLICT DO NOTHING — the charter is immutable, so a re-init never
        overwrites it and never clobbers accumulated `state`. (For roleplay this
        is where the world model would write a dynamic charter instead.)
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO session_working_memory (session_id, user_id, charter)
                VALUES ($1, $2, $3::jsonb)
                ON CONFLICT (session_id) DO NOTHING
                """,
                session_id, user_id, json.dumps(charter),
            )

    async def get(self, session_id: UUID, user_id: UUID | None = None) -> dict | None:
        """Return the assembled block {version, charter, state}, or None.

        Scopes by user_id when given (tenant safety) — a caller must own the
        session to read its working memory.
        """
        async with self._pool.acquire() as conn:
            if user_id is not None:
                row = await conn.fetchrow(
                    "SELECT charter, state FROM session_working_memory "
                    "WHERE session_id = $1 AND user_id = $2",
                    session_id, user_id,
                )
            else:
                row = await conn.fetchrow(
                    "SELECT charter, state FROM session_working_memory WHERE session_id = $1",
                    session_id,
                )
        if row is None:
            return None
        return {
            "version": 1,
            "charter": _as_dict(row["charter"]),
            "state": _as_dict(row["state"]),
        }

    async def update_state(self, session_id: UUID, state: dict) -> bool:
        """Executive write path (M5): replace `state` only. Never touches
        `charter`. Returns False if the session has no block (no-op)."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE session_working_memory
                SET state = $2::jsonb, updated_at = now()
                WHERE session_id = $1
                """,
                session_id, json.dumps(state),
            )
        return result != "UPDATE 0"
