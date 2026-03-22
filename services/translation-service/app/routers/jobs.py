from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
import asyncpg
import httpx

from ..deps import get_current_user, get_db
from ..config import settings as app_settings, DEFAULT_SYSTEM_PROMPT, DEFAULT_USER_PROMPT_TPL, DEFAULT_COMPACT_SYSTEM_PROMPT, DEFAULT_COMPACT_USER_PROMPT_TPL
from ..models import CreateJobPayload, TranslationJob, ChapterTranslation, ErrorResponse
from ..broker import publish, publish_event

router = APIRouter(prefix="/v1/translation", tags=["translation-jobs"])


async def _resolve_effective_settings(user_id: UUID, book_id: UUID, db: asyncpg.Pool):
    """Returns (settings_dict, is_default)."""
    row = await db.fetchrow(
        "SELECT * FROM book_translation_settings WHERE book_id=$1 AND owner_user_id=$2",
        book_id, user_id,
    )
    if row:
        return dict(row), False

    row = await db.fetchrow(
        "SELECT * FROM user_translation_preferences WHERE user_id=$1", user_id
    )
    if row:
        return dict(row), True

    return {
        "target_language":       "en",
        "model_source":          "platform_model",
        "model_ref":             None,
        "system_prompt":         DEFAULT_SYSTEM_PROMPT,
        "user_prompt_tpl":       DEFAULT_USER_PROMPT_TPL,
        "compact_model_source":  None,
        "compact_model_ref":     None,
        "compact_system_prompt": DEFAULT_COMPACT_SYSTEM_PROMPT,
        "compact_user_prompt_tpl": DEFAULT_COMPACT_USER_PROMPT_TPL,
        "chunk_size_tokens":     2000,
        "invoke_timeout_secs":   300,
    }, True


def _job_row_to_model(row, chapter_rows=None) -> TranslationJob:
    d = dict(row)
    if chapter_rows is not None:
        d["chapter_translations"] = [ChapterTranslation(**dict(r)) for r in chapter_rows]
    return TranslationJob(**d)


# ── Create job ────────────────────────────────────────────────────────────────

@router.post(
    "/books/{book_id}/jobs",
    response_model=TranslationJob,
    status_code=status.HTTP_201_CREATED,
)
async def create_job(
    book_id: UUID,
    payload: CreateJobPayload,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    uid = UUID(user_id)

    # Verify book ownership via book-service internal projection
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(
                f"{app_settings.book_service_internal_url}/internal/books/{book_id}/projection"
            )
        except httpx.RequestError:
            raise HTTPException(status_code=502, detail={"code": "TRANSL_BOOK_SERVICE_UNAVAILABLE", "message": "Book service unavailable"})

    if r.status_code == 404:
        raise HTTPException(status_code=404, detail={"code": "TRANSL_BOOK_NOT_FOUND", "message": "Book not found"})
    if not r.is_success:
        raise HTTPException(status_code=502, detail={"code": "TRANSL_BOOK_SERVICE_ERROR", "message": "Book service error"})

    projection = r.json()
    if str(projection.get("owner_user_id")) != user_id:
        raise HTTPException(status_code=403, detail={"code": "TRANSL_FORBIDDEN", "message": "Not your book"})

    # Resolve effective settings
    eff, _ = await _resolve_effective_settings(uid, book_id, db)
    if not eff.get("model_ref"):
        raise HTTPException(
            status_code=422,
            detail={"code": "TRANSL_NO_MODEL_CONFIGURED", "message": "No model configured. Set a model in Translation Settings before translating."},
        )

    chapter_ids = payload.chapter_ids

    # Insert job + chapter rows
    job_row = await db.fetchrow(
        """
        INSERT INTO translation_jobs
          (book_id, owner_user_id, status, target_language, model_source, model_ref,
           system_prompt, user_prompt_tpl,
           compact_model_source, compact_model_ref,
           compact_system_prompt, compact_user_prompt_tpl,
           chunk_size_tokens, invoke_timeout_secs,
           chapter_ids, total_chapters)
        VALUES ($1,$2,'pending',$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
        RETURNING *
        """,
        book_id, uid,
        eff["target_language"], eff["model_source"], eff["model_ref"],
        eff["system_prompt"], eff["user_prompt_tpl"],
        eff.get("compact_model_source"), eff.get("compact_model_ref"),
        eff.get("compact_system_prompt", DEFAULT_COMPACT_SYSTEM_PROMPT),
        eff.get("compact_user_prompt_tpl", DEFAULT_COMPACT_USER_PROMPT_TPL),
        eff.get("chunk_size_tokens", 2000), eff.get("invoke_timeout_secs", 300),
        chapter_ids, len(chapter_ids),
    )

    job_id = job_row["job_id"]

    for chapter_id in chapter_ids:
        await db.execute(
            """
            INSERT INTO chapter_translations
              (job_id, chapter_id, book_id, owner_user_id, status, target_language, version_num)
            VALUES ($1, $2, $3, $4, 'pending', $5,
                    COALESCE((SELECT MAX(version_num) FROM chapter_translations
                              WHERE chapter_id=$2 AND target_language=$5), 0) + 1)
            """,
            job_id, chapter_id, book_id, uid, eff["target_language"],
        )

    # Publish job to RabbitMQ — worker fans out chapter messages
    await publish("translation.job", {
        "job_id":                  str(job_id),
        "user_id":                 user_id,
        "book_id":                 str(book_id),
        "chapter_ids":             [str(c) for c in chapter_ids],
        "model_source":            eff["model_source"],
        "model_ref":               str(eff["model_ref"]),
        "system_prompt":           eff["system_prompt"],
        "user_prompt_tpl":         eff["user_prompt_tpl"],
        "target_language":         eff["target_language"],
        "compact_model_source":    eff.get("compact_model_source"),
        "compact_model_ref":       str(eff["compact_model_ref"]) if eff.get("compact_model_ref") else None,
        "compact_system_prompt":   eff.get("compact_system_prompt", DEFAULT_COMPACT_SYSTEM_PROMPT),
        "compact_user_prompt_tpl": eff.get("compact_user_prompt_tpl", DEFAULT_COMPACT_USER_PROMPT_TPL),
        "chunk_size_tokens":       eff.get("chunk_size_tokens", 2000),
        "invoke_timeout_secs":     eff.get("invoke_timeout_secs", 300),
    })
    await publish_event(user_id, {
        "event":    "job.created",
        "job_id":   str(job_id),
        "job_type": "translation",
        "payload":  {
            "book_id":        str(book_id),
            "total_chapters": len(chapter_ids),
            "status":         "pending",
        },
    })

    return _job_row_to_model(job_row)


# ── List jobs ─────────────────────────────────────────────────────────────────

@router.get("/books/{book_id}/jobs", response_model=list[TranslationJob])
async def list_jobs(
    book_id: UUID,
    limit: int = 5,
    offset: int = 0,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    rows = await db.fetch(
        """SELECT * FROM translation_jobs
           WHERE book_id=$1 AND owner_user_id=$2
           ORDER BY created_at DESC LIMIT $3 OFFSET $4""",
        book_id, UUID(user_id), limit, offset,
    )
    return [_job_row_to_model(r) for r in rows]


# ── Get job detail ────────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}", response_model=TranslationJob)
async def get_job(
    job_id: UUID,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    row = await db.fetchrow("SELECT * FROM translation_jobs WHERE job_id=$1", job_id)
    if not row or str(row["owner_user_id"]) != user_id:
        raise HTTPException(status_code=404, detail={"code": "TRANSL_NOT_FOUND", "message": "Job not found"})

    chapter_rows = await db.fetch(
        "SELECT * FROM chapter_translations WHERE job_id=$1 ORDER BY created_at",
        job_id,
    )
    return _job_row_to_model(row, chapter_rows)


# ── Get chapter translation ───────────────────────────────────────────────────

@router.get("/jobs/{job_id}/chapters/{chapter_id}", response_model=ChapterTranslation)
async def get_chapter_translation(
    job_id: UUID,
    chapter_id: UUID,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    job = await db.fetchrow(
        "SELECT owner_user_id FROM translation_jobs WHERE job_id=$1", job_id
    )
    if not job or str(job["owner_user_id"]) != user_id:
        raise HTTPException(status_code=403, detail={"code": "TRANSL_FORBIDDEN", "message": "Access denied"})

    row = await db.fetchrow(
        "SELECT * FROM chapter_translations WHERE job_id=$1 AND chapter_id=$2",
        job_id, chapter_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail={"code": "TRANSL_NOT_FOUND", "message": "Chapter translation not found"})

    return ChapterTranslation(**dict(row))


# ── Cancel job ────────────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_job(
    job_id: UUID,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    row = await db.fetchrow(
        "SELECT owner_user_id, status FROM translation_jobs WHERE job_id=$1", job_id
    )
    if not row or str(row["owner_user_id"]) != user_id:
        raise HTTPException(status_code=404, detail={"code": "TRANSL_NOT_FOUND", "message": "Job not found"})

    if row["status"] not in ("pending", "running"):
        raise HTTPException(
            status_code=409,
            detail={"code": "TRANSL_CANNOT_CANCEL", "message": f"Job is already {row['status']}"},
        )

    await db.execute(
        "UPDATE translation_jobs SET status='cancelled', finished_at=now() WHERE job_id=$1",
        job_id,
    )
