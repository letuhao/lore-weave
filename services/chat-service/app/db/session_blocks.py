"""T4 (Context Budget Law) — chat_session_blocks persistence (Core Memory Blocks).

Plain async functions (chat-service has no repository layer). TENANCY (CLAUDE.md,
LOCKED): every read/write filters `session_id AND owner_user_id` — never join-only.

Two write paths:
  * `refresh_block` — the auto-projected story_state cache: a plain upsert (derived
    data; last-refresh-wins is safe). Skips the write when the source_hash is
    unchanged, avoiding a pointless version bump.
  * `cas_update_block` — the OCC compare-and-set for a FUTURE agent-writable block
    (focus): a stale `expected_version` returns None so the caller self-corrects
    (D9 — never a silent last-writer-wins on authored data).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import asyncpg


@dataclass
class SessionBlock:
    label: str
    value: str
    token_estimate: int
    refreshed_turn: int
    source_hash: str | None
    version: int


def _uuid(v) -> UUID:
    return v if isinstance(v, UUID) else UUID(str(v))


async def get_block(
    pool: asyncpg.Pool, *, session_id, owner_user_id, label: str
) -> SessionBlock | None:
    row = await pool.fetchrow(
        "SELECT label, value, token_estimate, refreshed_turn, source_hash, version "
        "FROM chat_session_blocks "
        "WHERE session_id = $1 AND owner_user_id = $2 AND label = $3",
        _uuid(session_id), _uuid(owner_user_id), label,
    )
    if row is None:
        return None
    return SessionBlock(
        label=row["label"], value=row["value"], token_estimate=row["token_estimate"],
        refreshed_turn=row["refreshed_turn"], source_hash=row["source_hash"],
        version=row["version"],
    )


async def refresh_block(
    pool: asyncpg.Pool,
    *,
    session_id,
    owner_user_id,
    label: str,
    value: str,
    token_estimate: int,
    refreshed_turn: int,
    source_hash: str | None,
) -> int:
    """Upsert the auto-projected cache. Returns the row's version after the write.
    On (session, owner, label) conflict the value/estimate/turn/hash are replaced
    and version bumped — UNLESS the source_hash is unchanged (a no-op refresh), in
    which case only refreshed_turn advances (no version churn).

    LOW-2 (T4 review): this force-upsert bumps `version` outside the OCC discipline,
    so it MUST NOT be used on a CAS-managed (agent-writable) label — it would
    silently clobber the agent's value and desync the OCC token (the D9 anti-pattern).
    Guarded to STORY_STATE_LABEL below; a future agent-writable block writes via
    `cas_update_block` only."""
    from app.services.story_state import STORY_STATE_LABEL

    if label != STORY_STATE_LABEL:
        raise ValueError(
            f"refresh_block is for the auto-projected {STORY_STATE_LABEL!r} cache only; "
            f"agent-writable label {label!r} must use cas_update_block (OCC)."
        )
    row = await pool.fetchrow(
        """
        INSERT INTO chat_session_blocks
          (session_id, owner_user_id, label, value, token_estimate, refreshed_turn, source_hash)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (session_id, owner_user_id, label) DO UPDATE SET
          refreshed_turn = EXCLUDED.refreshed_turn,
          value = CASE WHEN chat_session_blocks.source_hash IS DISTINCT FROM EXCLUDED.source_hash
                       THEN EXCLUDED.value ELSE chat_session_blocks.value END,
          token_estimate = CASE WHEN chat_session_blocks.source_hash IS DISTINCT FROM EXCLUDED.source_hash
                                THEN EXCLUDED.token_estimate ELSE chat_session_blocks.token_estimate END,
          source_hash = EXCLUDED.source_hash,
          version = chat_session_blocks.version
                    + CASE WHEN chat_session_blocks.source_hash IS DISTINCT FROM EXCLUDED.source_hash
                           THEN 1 ELSE 0 END,
          updated_at = now()
        RETURNING version
        """,
        _uuid(session_id), _uuid(owner_user_id), label, value, token_estimate,
        refreshed_turn, source_hash,
    )
    return int(row["version"])


async def project_story_state(
    pool: asyncpg.Pool,
    *,
    session_id,
    owner_user_id,
    stable_context: str,
    full_context: str,
    current_turn: int,
    lore_gate: bool = False,
    scene_change: bool = False,
) -> str:
    """T4 (D4/D5) — maintain the cached `story_state` block and return the text to
    project this turn (``""`` when nothing should be injected).

    Two responsibilities, one round-trip:
      * **Maintain (D5):** refresh the cache from the message-independent grounding prefix
        (`stable_context`), falling back to the full `full_context` for modes that don't
        split the prefix out (`multi_project`/`no_project` set `stable_context=""` and put
        everything in `context`). Refresh only when `should_refresh` fires (no cache yet ·
        the source hash changed · an explicit lore-gate / scene change · `cadence` turns
        elapsed), so an unchanged bible doesn't churn the row every turn.
      * **Project (D4 safety net):** return the CACHED block **only when the live FULL
        grounding (`full_context`) is empty** — knowledge-service degraded (`context=""`),
        or a future T5-gated mode that returns nothing. Keying on `full_context` (not
        `stable_context`) is deliberate: `multi_project` mode has an empty `stable_context`
        yet a full live `context`, so keying on the prefix would false-fire and DUPLICATE
        the live lore. When any live grounding is present it is already in the prompt
        (assembler's `kctx_stable`/`kctx_context`), so we return ``""`` and rely on it. (The
        T5-era "unconditional projection that supersedes the live grounding" is deferred
        with T5.)

    Best-effort by contract: the caller wraps this so any failure degrades the turn to
    "no block", never breaks it. Tenancy is enforced by `get_block`/`refresh_block`
    (session_id AND owner_user_id).
    """
    from app.services.story_state import (
        STORY_STATE_LABEL,
        distill_story_state,
        render_story_state_block,
        should_refresh,
        source_hash,
    )

    cached = await get_block(
        pool, session_id=session_id, owner_user_id=owner_user_id, label=STORY_STATE_LABEL
    )
    refresh_source = (stable_context or "").strip() or (full_context or "").strip()
    if refresh_source:
        new_hash = source_hash(refresh_source)
        if should_refresh(
            cached_turn=cached.refreshed_turn if cached else None,
            current_turn=current_turn,
            cached_hash=cached.source_hash if cached else None,
            new_hash=new_hash,
            lore_gate=lore_gate,
            scene_change=scene_change,
        ):
            value, est = distill_story_state(refresh_source)
            await refresh_block(
                pool,
                session_id=session_id,
                owner_user_id=owner_user_id,
                label=STORY_STATE_LABEL,
                value=value,
                token_estimate=est,
                refreshed_turn=current_turn,
                source_hash=new_hash,
            )
    # Project the last-good bible ONLY when there is no live grounding this turn
    # (degraded / gated-empty). Any live grounding is already in the prompt → no dup.
    if not (full_context or "").strip() and cached and cached.value.strip():
        return render_story_state_block(cached.value)
    return ""


async def cas_update_block(
    pool: asyncpg.Pool,
    *,
    session_id,
    owner_user_id,
    label: str,
    value: str,
    token_estimate: int,
    refreshed_turn: int,
    source_hash: str | None,
    expected_version: int,
) -> int | None:
    """OCC compare-and-set for an agent-writable block (D9). Returns the new version,
    or None when the row is missing OR `expected_version` is stale — the caller must
    re-read + re-apply (self-correcting), never a silent clobber.

    LOW-3 (T4 review): None is ambiguous (missing-row vs stale-version). The wiring
    caller MUST disambiguate — on None, re-read via get_block: a row present ⇒ stale
    (retry with its version); absent ⇒ create-if-absent (do NOT loop retrying CAS,
    which would spin forever on a missing row)."""
    row = await pool.fetchrow(
        """
        UPDATE chat_session_blocks
           SET value = $4, token_estimate = $5, refreshed_turn = $6,
               source_hash = $7, version = version + 1, updated_at = now()
         WHERE session_id = $1 AND owner_user_id = $2 AND label = $3
           AND version = $8
        RETURNING version
        """,
        _uuid(session_id), _uuid(owner_user_id), label, value, token_estimate,
        refreshed_turn, source_hash, expected_version,
    )
    return int(row["version"]) if row is not None else None
