import json
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
import asyncpg

from ..deps import get_current_user, get_db

log = logging.getLogger(__name__)
from ..models import (
    ChapterTranslation,
    ChapterVersionsResponse,
    LanguageVersionGroup,
    VersionSummary,
    ActiveVersionResponse,
    SaveEditedTranslationRequest,
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
    acknowledge_issues: bool = False,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    row = await db.fetchrow(
        "SELECT owner_user_id, book_id, target_language, status, unresolved_high_count "
        "FROM chapter_translations WHERE id=$1 AND chapter_id=$2",
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

    # M5b publish quality-gate: hold a version the verifier flagged with unresolved
    # high-severity issues, unless the user explicitly acknowledges. Soft gate —
    # the verifier can false-positive, so the human stays in control.
    unresolved = row["unresolved_high_count"] or 0
    if unresolved > 0 and not acknowledge_issues:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TRANSL_NEEDS_REVIEW",
                "message": (
                    f"This version has {unresolved} unresolved high-severity issue(s) "
                    "flagged by the verifier. Acknowledge to publish it anyway."
                ),
                "unresolved_high_count": unresolved,
            },
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

    # M7b (Channel 1a — human signal): setting a version active is a human-only
    # action (the worker auto-activates via a different path), so it is a genuine
    # "this translation is good enough to publish" judgment → learning source=human.
    # acknowledge_issues=true is the high-value case: the human published DESPITE
    # the verifier's flags (verifier-calibration signal). Best-effort + post-commit
    # (the active version is already set — a feedback-log failure must not 500 the
    # publish). aggregate_type='translation' reuses M7a's stream.
    try:
        await db.execute(
            """INSERT INTO outbox_events (event_type, aggregate_type, aggregate_id, payload)
               VALUES ('translation.reviewed', 'translation', $1, $2::jsonb)""",
            version_id,
            json.dumps({
                "user_id": user_id,
                "book_id": str(row["book_id"]),
                "chapter_id": str(chapter_id),
                "chapter_translation_id": str(version_id),
                "target_language": row["target_language"],
                "acknowledged_issues": bool(acknowledge_issues),
                "unresolved_high_count": unresolved,
            }),
        )
    except Exception:  # noqa: BLE001 — telemetry must not break publish
        log.warning("M7b: failed to emit translation.reviewed (non-fatal)", exc_info=True)

    return ActiveVersionResponse(
        chapter_id=chapter_id,
        target_language=row["target_language"],
        active_id=version_id,
    )


# ── Save a human-edited translation (M7c human-fix gold) ──────────────────────

@router.post(
    "/chapters/{chapter_id}/versions/edit",
    response_model=ChapterTranslation,
    status_code=201,
)
async def save_edited_version(
    chapter_id: UUID,
    body: SaveEditedTranslationRequest,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    """M7c (Channel 1b): save a human-edited translation as a NEW version
    (``authored_by='human'``, linked to the LLM version it was edited from). The
    LLM-draft → human-edit diff is emitted as learning gold (`translation.corrected`,
    before=LLM / after=human) so future tuning can see what the LLM got wrong."""
    src = await db.fetchrow(
        "SELECT owner_user_id, book_id, target_language, version_num, "
        "translated_body, translated_body_json "
        "FROM chapter_translations WHERE id=$1 AND chapter_id=$2",
        body.edited_from_version_id, chapter_id,
    )
    if not src:
        raise HTTPException(status_code=404, detail={"code": "TRANSL_NOT_FOUND", "message": "Source version not found"})
    _assert_owner(src, user_id)
    if src["target_language"] != body.target_language:
        raise HTTPException(
            status_code=422,
            detail={"code": "TRANSL_LANG_MISMATCH", "message": "target_language does not match the source version"},
        )

    # New human version: max(version_num)+1 for (chapter, lang); reuse the source
    # version's job_id/book_id/owner (the edit attaches to the same job — avoids
    # making job_id a nullable FK). authored_by='human' + the parent link.
    new = await db.fetchrow(
        """
        INSERT INTO chapter_translations
          (job_id, chapter_id, book_id, owner_user_id, status, target_language,
           translated_body, translated_body_json, translated_body_format,
           version_num, authored_by, edited_from_version_id, finished_at)
        SELECT job_id, chapter_id, book_id, owner_user_id, 'completed', target_language,
               $3, $4::jsonb, $5,
               COALESCE((SELECT MAX(version_num) FROM chapter_translations
                          WHERE chapter_id=$2 AND target_language=$6), 0) + 1,
               'human', $1, now()
        FROM chapter_translations WHERE id=$1
        RETURNING *
        """,
        body.edited_from_version_id, chapter_id,
        body.translated_body,
        json.dumps(body.translated_body_json) if body.translated_body_json is not None else None,
        body.translated_body_format, body.target_language,
    )

    # M7c gold: emit the LLM→human diff (best-effort post-commit; a feedback-log
    # failure must not lose the user's edit). Raw before/after bodies — PO chose
    # raw-text retention for translation tuning.
    try:
        before_json = src["translated_body_json"]
        if isinstance(before_json, str):
            before_json = json.loads(before_json)
        before_body = before_json if before_json is not None else src["translated_body"]
        after_body = (
            body.translated_body_json
            if body.translated_body_json is not None
            else body.translated_body
        )
        await db.execute(
            """INSERT INTO outbox_events (event_type, aggregate_type, aggregate_id, payload)
               VALUES ('translation.corrected', 'translation', $1, $2::jsonb)""",
            new["id"],
            json.dumps({
                "user_id": user_id,
                "book_id": str(src["book_id"]),
                "chapter_id": str(chapter_id),
                "chapter_translation_id": str(new["id"]),
                "edited_from_version_id": str(body.edited_from_version_id),
                "target_language": body.target_language,
                "before": {"target_language": body.target_language,
                           "version_num": src["version_num"], "body": before_body},
                "after": {"target_language": body.target_language,
                          "version_num": new["version_num"], "body": after_body},
            }),
        )
    except Exception:  # noqa: BLE001 — telemetry must not lose the edit
        log.warning("M7c: failed to emit translation.corrected (non-fatal)", exc_info=True)

    return ChapterTranslation(**dict(new))
