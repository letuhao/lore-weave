from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
import asyncpg

from ..deps import get_current_user, get_db
from ..models import (
    ChapterTranslation,
    ChapterVersionsResponse,
    LanguageVersionGroup,
    VersionSummary,
    ActiveVersionResponse,
)

router = APIRouter(prefix="/v1/translation", tags=["translation-versions"])


def _assert_owner(row, user_id: str) -> None:
    if not row or str(row["owner_user_id"]) != user_id:
        raise HTTPException(status_code=403, detail={"code": "TRANSL_FORBIDDEN", "message": "Access denied"})


# ── List all versions for a chapter, grouped by language ───────────────────────

@router.get("/chapters/{chapter_id}/versions", response_model=ChapterVersionsResponse)
async def list_chapter_versions(
    chapter_id: UUID,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    # Fetch all chapter_translations for this chapter owned by user, newest first
    rows = await db.fetch(
        """
        SELECT ct.*,
               (actv.chapter_translation_id = ct.id) AS is_active,
               actv.chapter_translation_id           AS active_ct_id
        FROM chapter_translations ct
        LEFT JOIN active_chapter_translation_versions actv
          ON actv.chapter_id = ct.chapter_id
         AND actv.target_language = ct.target_language
        WHERE ct.chapter_id = $1
          AND ct.owner_user_id = $2
        ORDER BY ct.target_language, ct.version_num DESC
        """,
        chapter_id, UUID(user_id),
    )

    if not rows:
        # Return an empty response — not a 404, the chapter just has no translations yet
        return ChapterVersionsResponse(chapter_id=chapter_id, languages=[])

    # Group by language
    lang_map: dict[str, dict] = {}
    for row in rows:
        lang = row["target_language"]
        if lang not in lang_map:
            lang_map[lang] = {
                "target_language": lang,
                "active_id": row["active_ct_id"],
                "versions": [],
            }
        lang_map[lang]["versions"].append(
            VersionSummary(
                id=row["id"],
                version_num=row["version_num"],
                job_id=row["job_id"],
                status=row["status"],
                is_active=bool(row["is_active"]),
                model_source=row["model_source"] if "model_source" in row.keys() else "unknown",
                model_ref=row["model_ref"] if "model_ref" in row.keys() else None,
                input_tokens=row["input_tokens"],
                output_tokens=row["output_tokens"],
                created_at=row["created_at"],
            )
        )

    languages = [
        LanguageVersionGroup(**v) for v in lang_map.values()
    ]
    return ChapterVersionsResponse(chapter_id=chapter_id, languages=languages)


# ── Get single version (includes translated_body) ─────────────────────────────

@router.get("/chapters/{chapter_id}/versions/{version_id}", response_model=ChapterTranslation)
async def get_chapter_version(
    chapter_id: UUID,
    version_id: UUID,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    row = await db.fetchrow(
        "SELECT * FROM chapter_translations WHERE id=$1 AND chapter_id=$2",
        version_id, chapter_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail={"code": "TRANSL_NOT_FOUND", "message": "Version not found"})
    _assert_owner(row, user_id)

    return ChapterTranslation(**dict(row))


# ── Set active version ────────────────────────────────────────────────────────

@router.put("/chapters/{chapter_id}/versions/{version_id}/active", response_model=ActiveVersionResponse)
async def set_active_version(
    chapter_id: UUID,
    version_id: UUID,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    row = await db.fetchrow(
        "SELECT owner_user_id, target_language, status FROM chapter_translations WHERE id=$1 AND chapter_id=$2",
        version_id, chapter_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail={"code": "TRANSL_NOT_FOUND", "message": "Version not found"})
    _assert_owner(row, user_id)

    if row["status"] != "completed":
        raise HTTPException(
            status_code=422,
            detail={"code": "TRANSL_NOT_COMPLETED", "message": "Only completed versions can be set as active"},
        )

    await db.execute(
        """
        INSERT INTO active_chapter_translation_versions
          (chapter_id, target_language, chapter_translation_id, set_by_user_id, set_at)
        VALUES ($1, $2, $3, $4, now())
        ON CONFLICT (chapter_id, target_language)
          DO UPDATE SET chapter_translation_id=$3, set_by_user_id=$4, set_at=now()
        """,
        chapter_id, row["target_language"], version_id, UUID(user_id),
    )

    return ActiveVersionResponse(
        chapter_id=chapter_id,
        target_language=row["target_language"],
        active_id=version_id,
    )
