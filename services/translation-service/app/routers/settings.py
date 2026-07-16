from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
import asyncpg

from ..deps import get_current_user, get_db
from ..grant_deps import GrantLevel, require_book_grant
from ..config import settings as app_settings, DEFAULT_SYSTEM_PROMPT, DEFAULT_USER_PROMPT_TPL
from ..languages import normalize_language, is_translation_target
from ..models import (
    PreferencesPayload,
    UserTranslationPreferences,
    BookSettingsPayload,
    BookTranslationSettings,
    ErrorResponse,
)
from ..effective_settings import resolve_effective_settings


def _validate_target_language(value: str | None) -> str | None:
    """D13 — a settings write is a target_language WRITER: normalize + validate against the
    content-language registry so the free-text "Vietnamese" can't be stored here (it later
    became a job's effective language). None = "field not sent" (PATCH keep), so pass it through.
    """
    if value is None:
        return None
    norm = normalize_language(value)
    if not is_translation_target(norm):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_target_language", "message": f"'{value}' is not a supported target language."},
        )
    return norm

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
    payload.target_language = _validate_target_language(payload.target_language) or payload.target_language
    row = await db.fetchrow(
        """
        INSERT INTO user_translation_preferences
          (user_id, target_language, model_source, model_ref,
           system_prompt, user_prompt_tpl,
           compact_model_source, compact_model_ref,
           compact_system_prompt, compact_user_prompt_tpl,
           chunk_size_tokens, invoke_timeout_secs,
           updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, now())
        ON CONFLICT (user_id) DO UPDATE SET
          target_language          = EXCLUDED.target_language,
          model_source             = EXCLUDED.model_source,
          model_ref                = EXCLUDED.model_ref,
          system_prompt            = EXCLUDED.system_prompt,
          user_prompt_tpl          = EXCLUDED.user_prompt_tpl,
          compact_model_source     = EXCLUDED.compact_model_source,
          compact_model_ref        = EXCLUDED.compact_model_ref,
          compact_system_prompt    = EXCLUDED.compact_system_prompt,
          compact_user_prompt_tpl  = EXCLUDED.compact_user_prompt_tpl,
          chunk_size_tokens        = EXCLUDED.chunk_size_tokens,
          invoke_timeout_secs      = EXCLUDED.invoke_timeout_secs,
          updated_at               = now()
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
        payload.compact_system_prompt,
        payload.compact_user_prompt_tpl,
        payload.chunk_size_tokens,
        payload.invoke_timeout_secs,
    )
    return UserTranslationPreferences(**dict(row))


# ── Book settings ─────────────────────────────────────────────────────────────

@router.get("/books/{book_id}/settings", response_model=BookTranslationSettings)
async def get_book_settings(
    book_id: UUID,
    user_id: str = Depends(get_current_user),
    # E0-4a view gate. Settings stay PER-USER (effective_settings resolves the
    # caller's own model — a collaborator gets their own config, not the owner's,
    # because the owner's model_ref won't resolve under the caller's BYOK).
    _grant: UUID = Depends(require_book_grant(GrantLevel.VIEW)),
    db: asyncpg.Pool = Depends(get_db),
):
    import datetime
    uid = UUID(user_id)
    cfg, is_default, updated_at = await resolve_effective_settings(uid, book_id, db)
    return BookTranslationSettings(
        **cfg,
        book_id=book_id,
        user_id=uid,
        owner_user_id=uid,
        is_default=is_default,
        updated_at=updated_at or datetime.datetime.utcnow(),
    )


@router.put("/books/{book_id}/settings", response_model=BookTranslationSettings)
async def put_book_settings(
    book_id: UUID,
    payload: BookSettingsPayload,
    user_id: str = Depends(get_current_user),
    # E0-4a edit gate. NOTE: book_translation_settings.book_id is the PK (one row/
    # book) so a collaborator's PUT overwrites the shared row — tracked as
    # D-E0-4A-SETTINGS-PERUSER (composite PK so each keeps their own config). v1: a
    # collaborator normally uses their user-prefs model; book-settings PUT is rare.
    _grant: UUID = Depends(require_book_grant(GrantLevel.EDIT)),
    db: asyncpg.Pool = Depends(get_db),
):
    uid = UUID(user_id)
    payload.target_language = _validate_target_language(payload.target_language)
    # PATCH-semantics done ATOMICALLY in one statement (no read-modify-write, so no
    # lost-update race between concurrent multi-device writes). A NULL parameter means
    # "field not sent": on INSERT it falls back to the column default, on UPDATE it
    # keeps the existing stored value via COALESCE(param, existing).
    # NOTE: because NULL means "keep", this endpoint cannot null-out a nullable field
    # (model_ref / compact_model_ref / compact_model_source) — acceptable for the
    # current UI; clearing a model would be a separate explicit action.
    row = await db.fetchrow(
        """
        INSERT INTO book_translation_settings
          (book_id, owner_user_id, target_language, model_source, model_ref,
           system_prompt, user_prompt_tpl,
           compact_model_source, compact_model_ref,
           compact_system_prompt, compact_user_prompt_tpl,
           chunk_size_tokens, invoke_timeout_secs,
           updated_at)
        VALUES (
          $1, $2,
          COALESCE($3, 'en'),
          COALESCE($4, 'platform_model'),
          $5,
          COALESCE($6, $14),
          COALESCE($7, $15),
          $8, $9,
          COALESCE($10, ''),
          COALESCE($11, ''),
          COALESCE($12, 2000),
          COALESCE($13, 300),
          now()
        )
        ON CONFLICT (book_id) DO UPDATE SET
          target_language          = COALESCE($3,  book_translation_settings.target_language),
          model_source             = COALESCE($4,  book_translation_settings.model_source),
          model_ref                = COALESCE($5,  book_translation_settings.model_ref),
          system_prompt            = COALESCE($6,  book_translation_settings.system_prompt),
          user_prompt_tpl          = COALESCE($7,  book_translation_settings.user_prompt_tpl),
          compact_model_source     = COALESCE($8,  book_translation_settings.compact_model_source),
          compact_model_ref        = COALESCE($9,  book_translation_settings.compact_model_ref),
          compact_system_prompt    = COALESCE($10, book_translation_settings.compact_system_prompt),
          compact_user_prompt_tpl  = COALESCE($11, book_translation_settings.compact_user_prompt_tpl),
          chunk_size_tokens        = COALESCE($12, book_translation_settings.chunk_size_tokens),
          invoke_timeout_secs      = COALESCE($13, book_translation_settings.invoke_timeout_secs),
          updated_at               = now()
        RETURNING *
        """,
        book_id,
        uid,
        payload.target_language,
        payload.model_source,
        payload.model_ref,
        payload.system_prompt,
        payload.user_prompt_tpl,
        payload.compact_model_source,
        payload.compact_model_ref,
        payload.compact_system_prompt,
        payload.compact_user_prompt_tpl,
        payload.chunk_size_tokens,
        payload.invoke_timeout_secs,
        DEFAULT_SYSTEM_PROMPT,
        DEFAULT_USER_PROMPT_TPL,
    )
    d = dict(row)
    return BookTranslationSettings(**d, user_id=uid, is_default=False)
