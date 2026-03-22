from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
import asyncpg

from ..deps import get_current_user, get_db
from ..config import settings as app_settings, DEFAULT_SYSTEM_PROMPT, DEFAULT_USER_PROMPT_TPL
from ..models import (
    PreferencesPayload,
    UserTranslationPreferences,
    BookSettingsPayload,
    BookTranslationSettings,
    ErrorResponse,
)

router = APIRouter(prefix="/v1/translation", tags=["translation-settings"])


# ── User preferences ──────────────────────────────────────────────────────────

@router.get("/preferences", response_model=UserTranslationPreferences)
async def get_preferences(
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    row = await db.fetchrow(
        "SELECT * FROM user_translation_preferences WHERE user_id = $1",
        UUID(user_id),
    )
    if row:
        return UserTranslationPreferences(**dict(row))
    # Return synthesized defaults
    return UserTranslationPreferences(
        user_id=UUID(user_id),
        target_language="en",
        model_source="platform_model",
        model_ref=None,
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_prompt_tpl=DEFAULT_USER_PROMPT_TPL,
        updated_at=__import__("datetime").datetime.utcnow(),
    )


@router.put("/preferences", response_model=UserTranslationPreferences)
async def put_preferences(
    payload: PreferencesPayload,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    row = await db.fetchrow(
        """
        INSERT INTO user_translation_preferences
          (user_id, target_language, model_source, model_ref,
           system_prompt, user_prompt_tpl,
           compact_model_source, compact_model_ref,
           chunk_size_tokens, invoke_timeout_secs,
           updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, now())
        ON CONFLICT (user_id) DO UPDATE SET
          target_language      = EXCLUDED.target_language,
          model_source         = EXCLUDED.model_source,
          model_ref            = EXCLUDED.model_ref,
          system_prompt        = EXCLUDED.system_prompt,
          user_prompt_tpl      = EXCLUDED.user_prompt_tpl,
          compact_model_source = EXCLUDED.compact_model_source,
          compact_model_ref    = EXCLUDED.compact_model_ref,
          chunk_size_tokens    = EXCLUDED.chunk_size_tokens,
          invoke_timeout_secs  = EXCLUDED.invoke_timeout_secs,
          updated_at           = now()
        RETURNING *
        """,
        UUID(user_id),
        payload.target_language,
        payload.model_source,
        payload.model_ref,
        payload.system_prompt,
        payload.user_prompt_tpl,
        payload.compact_model_source,
        payload.compact_model_ref,
        payload.chunk_size_tokens,
        payload.invoke_timeout_secs,
    )
    return UserTranslationPreferences(**dict(row))


# ── Book settings ─────────────────────────────────────────────────────────────

@router.get("/books/{book_id}/settings", response_model=BookTranslationSettings)
async def get_book_settings(
    book_id: UUID,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    # Try book-level row first
    row = await db.fetchrow(
        "SELECT * FROM book_translation_settings WHERE book_id = $1 AND owner_user_id = $2",
        book_id, UUID(user_id),
    )
    if row:
        d = dict(row)
        return BookTranslationSettings(**d, user_id=UUID(user_id), is_default=False)

    # Fall back to user preferences
    pref_row = await db.fetchrow(
        "SELECT * FROM user_translation_preferences WHERE user_id = $1",
        UUID(user_id),
    )
    if pref_row:
        d = dict(pref_row)
        return BookTranslationSettings(
            book_id=book_id,
            user_id=UUID(user_id),
            owner_user_id=UUID(user_id),
            is_default=True,
            target_language=d["target_language"],
            model_source=d["model_source"],
            model_ref=d["model_ref"],
            system_prompt=d["system_prompt"],
            user_prompt_tpl=d["user_prompt_tpl"],
            compact_model_source=d.get("compact_model_source"),
            compact_model_ref=d.get("compact_model_ref"),
            chunk_size_tokens=d.get("chunk_size_tokens", 2000),
            invoke_timeout_secs=d.get("invoke_timeout_secs", 300),
            updated_at=d["updated_at"],
        )

    # Fall back to hard-coded defaults
    import datetime
    return BookTranslationSettings(
        book_id=book_id,
        user_id=UUID(user_id),
        owner_user_id=UUID(user_id),
        target_language="en",
        model_source="platform_model",
        model_ref=None,
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_prompt_tpl=DEFAULT_USER_PROMPT_TPL,
        updated_at=datetime.datetime.utcnow(),
        is_default=True,
    )


@router.put("/books/{book_id}/settings", response_model=BookTranslationSettings)
async def put_book_settings(
    book_id: UUID,
    payload: BookSettingsPayload,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    row = await db.fetchrow(
        """
        INSERT INTO book_translation_settings
          (book_id, owner_user_id, target_language, model_source, model_ref,
           system_prompt, user_prompt_tpl,
           compact_model_source, compact_model_ref,
           chunk_size_tokens, invoke_timeout_secs,
           updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, now())
        ON CONFLICT (book_id) DO UPDATE SET
          target_language      = EXCLUDED.target_language,
          model_source         = EXCLUDED.model_source,
          model_ref            = EXCLUDED.model_ref,
          system_prompt        = EXCLUDED.system_prompt,
          user_prompt_tpl      = EXCLUDED.user_prompt_tpl,
          compact_model_source = EXCLUDED.compact_model_source,
          compact_model_ref    = EXCLUDED.compact_model_ref,
          chunk_size_tokens    = EXCLUDED.chunk_size_tokens,
          invoke_timeout_secs  = EXCLUDED.invoke_timeout_secs,
          updated_at           = now()
        RETURNING *
        """,
        book_id,
        UUID(user_id),
        payload.target_language,
        payload.model_source,
        payload.model_ref,
        payload.system_prompt,
        payload.user_prompt_tpl,
        payload.compact_model_source,
        payload.compact_model_ref,
        payload.chunk_size_tokens,
        payload.invoke_timeout_secs,
    )
    d = dict(row)
    return BookTranslationSettings(**d, user_id=UUID(user_id), is_default=False)
