"""Chat & AI settings — per-user Account-tier prefs blob (spec §4.1/§4.5).

Plain async functions (chat-service has no repository layer). TENANCY (LOCKED):
keyed by owner_user_id (Per-user tier); every read/write filters owner_user_id.
Model account defaults are NOT here — they stay in provider-registry
`user_default_models` (one SoT per fact). This blob covers behavior / grounding
/ voice / context only.

PATCH is a **deep field-merge** with an optimistic-concurrency `version` guard,
never a whole-blob last-write-wins — so a two-device concurrent edit of two
different leaves both survive.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from uuid import UUID

import asyncpg

from app.services.settings_resolution import apply_patch

_CATEGORIES = ("behavior", "grounding", "voice", "context", "assistant")
_DEFAULT_CONTEXT = {"mode": "auto"}


@dataclass
class AiPrefs:
    behavior: dict = field(default_factory=dict)
    grounding: dict = field(default_factory=dict)
    voice: dict = field(default_factory=dict)
    context: dict = field(default_factory=lambda: dict(_DEFAULT_CONTEXT))
    assistant: dict = field(default_factory=dict)  # WS-5.4 — coaching_enabled (default OFF)
    version: int = 0
    persisted: bool = False  # False = defaults, no row yet


def _uuid(v) -> UUID:
    return v if isinstance(v, UUID) else UUID(str(v))


def _loads(v) -> dict:
    if v is None:
        return {}
    if isinstance(v, str):
        return json.loads(v)
    return dict(v)


def _row_to_prefs(row) -> AiPrefs:
    # Defensive .get(): a real user_chat_ai_prefs row always carries every column,
    # but a mislabelled/partial row (e.g. a shared mock pool returning a session
    # record) must degrade to empty defaults, never KeyError into a 500.
    get = row.get if hasattr(row, "get") else (lambda k, d=None: row[k])
    return AiPrefs(
        behavior=_loads(get("behavior")),
        grounding=_loads(get("grounding")),
        voice=_loads(get("voice")),
        context=_loads(get("context")) or dict(_DEFAULT_CONTEXT),
        assistant=_loads(get("assistant")),
        version=int(get("version", 0) or 0),
        persisted=True,
    )


async def get_prefs(pool: asyncpg.Pool, *, owner_user_id) -> AiPrefs:
    """Return the user's prefs, or the unpersisted defaults if no row exists yet."""
    row = await pool.fetchrow(
        "SELECT behavior, grounding, voice, context, assistant, version "
        "FROM user_chat_ai_prefs WHERE owner_user_id = $1",
        _uuid(owner_user_id),
    )
    if row is None:
        return AiPrefs()
    return _row_to_prefs(row)


class VersionConflict(Exception):
    """Raised on an If-Match version mismatch (concurrent edit) → HTTP 412."""


async def patch_prefs(
    pool: asyncpg.Pool,
    *,
    owner_user_id,
    patch: dict,
    expected_version: int | None = None,
) -> AiPrefs:
    """Deep field-merge `patch` (a partial {behavior?,grounding?,voice?,context?})
    into the user's prefs and persist. A null leaf clears that key ("inherit"),
    an absent key is untouched. If `expected_version` is given and does not match
    the stored version, raises `VersionConflict` (no silent clobber).

    Runs inside a transaction: read-merge-write is atomic against a concurrent
    writer for the SAME row; the `version` bump + WHERE guard makes a lost update
    impossible.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT behavior, grounding, voice, context, assistant, version "
                "FROM user_chat_ai_prefs WHERE owner_user_id = $1 FOR UPDATE",
                _uuid(owner_user_id),
            )
            current = _row_to_prefs(row) if row is not None else AiPrefs()
            if expected_version is not None and expected_version != current.version:
                raise VersionConflict(
                    f"version {expected_version} != current {current.version}"
                )

            merged = {
                cat: apply_patch(getattr(current, cat), patch[cat])
                for cat in _CATEGORIES
                if cat in patch and isinstance(patch[cat], dict)
            }
            # unspecified categories keep their current value
            for cat in _CATEGORIES:
                merged.setdefault(cat, getattr(current, cat))

            new_version = current.version + 1
            await conn.execute(
                """
                INSERT INTO user_chat_ai_prefs
                  (owner_user_id, behavior, grounding, voice, context, assistant, version, updated_at)
                VALUES ($1, $2::jsonb, $3::jsonb, $4::jsonb, $5::jsonb, $6::jsonb, $7, now())
                ON CONFLICT (owner_user_id) DO UPDATE SET
                  behavior = EXCLUDED.behavior,
                  grounding = EXCLUDED.grounding,
                  voice = EXCLUDED.voice,
                  context = EXCLUDED.context,
                  assistant = EXCLUDED.assistant,
                  version = EXCLUDED.version,
                  updated_at = now()
                """,
                _uuid(owner_user_id),
                json.dumps(merged["behavior"]),
                json.dumps(merged["grounding"]),
                json.dumps(merged["voice"]),
                json.dumps(merged["context"]),
                json.dumps(merged["assistant"]),
                new_version,
            )
            return AiPrefs(
                behavior=merged["behavior"],
                grounding=merged["grounding"],
                voice=merged["voice"],
                context=merged["context"] or dict(_DEFAULT_CONTEXT),
                assistant=merged["assistant"],
                version=new_version,
                persisted=True,
            )
