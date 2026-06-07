"""Single source of truth for resolving a user/book's effective translation settings.

Both the settings router (GET/PUT book settings) and the jobs router (create job)
need the same fallback chain: book-level row → user preferences → hard-coded defaults.
Keeping it in one place avoids the two copies drifting (they did before — LW-PLAN-MVP-RELEASE T1).
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

import asyncpg

from .config import (
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_USER_PROMPT_TPL,
    DEFAULT_COMPACT_SYSTEM_PROMPT,
    DEFAULT_COMPACT_USER_PROMPT_TPL,
)

# The 11 translation-config fields a job/setting carries (no identity/timestamp columns).
CONFIG_KEYS = (
    "target_language",
    "model_source",
    "model_ref",
    "system_prompt",
    "user_prompt_tpl",
    "compact_model_source",
    "compact_model_ref",
    "compact_system_prompt",
    "compact_user_prompt_tpl",
    "chunk_size_tokens",
    "invoke_timeout_secs",
)


def _normalize(row: dict) -> dict:
    """Project a settings/prefs row (or {}) onto the canonical config dict, filling
    defaults for any absent column. `.get(key, default)` is used (not `or`) so an
    intentionally-empty stored prompt ('') is preserved rather than reset."""
    return {
        "target_language":         row.get("target_language", "en"),
        "model_source":            row.get("model_source", "platform_model"),
        "model_ref":               row.get("model_ref"),
        "system_prompt":           row.get("system_prompt", DEFAULT_SYSTEM_PROMPT),
        "user_prompt_tpl":         row.get("user_prompt_tpl", DEFAULT_USER_PROMPT_TPL),
        "compact_model_source":    row.get("compact_model_source"),
        "compact_model_ref":       row.get("compact_model_ref"),
        "compact_system_prompt":   row.get("compact_system_prompt", DEFAULT_COMPACT_SYSTEM_PROMPT),
        "compact_user_prompt_tpl": row.get("compact_user_prompt_tpl", DEFAULT_COMPACT_USER_PROMPT_TPL),
        "chunk_size_tokens":       row.get("chunk_size_tokens", 2000),
        "invoke_timeout_secs":     row.get("invoke_timeout_secs", 300),
        "pipeline_version":        row.get("pipeline_version", "v2"),
        # V3 QA config (M2 + config-plumbing). Like pipeline_version, these are
        # resolved here + snapshotted onto the job; not in CONFIG_KEYS / book-
        # settings UI yet (D-TRANSL-FLAG-BOOKSETTINGS).
        "qa_depth":                row.get("qa_depth", "standard"),
        "max_qa_rounds":           row.get("max_qa_rounds", 2),
        "verifier_model_source":   row.get("verifier_model_source"),
        "verifier_model_ref":      row.get("verifier_model_ref"),
        # M4d-2c — 2-pass cold-start mode (single_pass default | two_pass).
        "cold_start_mode":         row.get("cold_start_mode", "single_pass"),
    }


async def resolve_effective_settings(
    user_id: UUID, book_id: UUID, db: asyncpg.Pool
) -> tuple[dict, bool, Optional[datetime]]:
    """Resolve effective book translation settings.

    Returns ``(config, is_default, updated_at)`` where:
      - ``config`` is the canonical 11-field dict (see CONFIG_KEYS),
      - ``is_default`` is True when no book-level row exists (prefs or hard defaults),
      - ``updated_at`` is the source row's timestamp, or None for hard defaults.
    """
    row = await db.fetchrow(
        "SELECT * FROM book_translation_settings WHERE book_id=$1 AND owner_user_id=$2",
        book_id, user_id,
    )
    if row:
        d = dict(row)
        return _normalize(d), False, d.get("updated_at")

    row = await db.fetchrow(
        "SELECT * FROM user_translation_preferences WHERE user_id=$1", user_id
    )
    if row:
        d = dict(row)
        return _normalize(d), True, d.get("updated_at")

    return _normalize({}), True, None
