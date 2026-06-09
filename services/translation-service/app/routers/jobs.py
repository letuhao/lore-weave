import json
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
import asyncpg
import httpx

from ..deps import get_current_user, get_db
from ..config import settings as app_settings, DEFAULT_COMPACT_SYSTEM_PROMPT, DEFAULT_COMPACT_USER_PROMPT_TPL
from ..models import CreateJobPayload, TranslationJob, ChapterTranslation, ErrorResponse
from ..broker import publish, publish_event
from ..effective_settings import resolve_effective_settings

router = APIRouter(prefix="/v1/translation", tags=["translation-jobs"])


def _job_row_to_model(row, chapter_rows=None) -> TranslationJob:
    d = dict(row)
    if chapter_rows is not None:
        d["chapter_translations"] = [ChapterTranslation(**dict(r)) for r in chapter_rows]
    return TranslationJob(**d)


# ── Create job ────────────────────────────────────────────────────────────────


async def _verify_book_owner(book_id: UUID, user_id: str) -> None:
    """Verify `user_id` owns `book_id` via book-service. Raises HTTPException on
    not-found (404) / not-owner (403) / book-service error (502)."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(
                f"{app_settings.book_service_internal_url}/internal/books/{book_id}/projection",
                headers={"X-Internal-Token": app_settings.internal_service_token},
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
    await _verify_book_owner(book_id, user_id)
    # S4a: campaign_id is NOT taken from the public body — a user must not be able
    # to tag their job to another user's campaign (which would inflate that
    # campaign's spend and trip its budget pause). Only the internal dispatch
    # endpoint (ownership pre-verified) supplies it.
    return await _resolve_and_create_job(db, book_id, payload, user_id)


async def _resolve_and_create_job(
    db: asyncpg.Pool, book_id: UUID, payload: CreateJobPayload, user_id: str,
    *, campaign_id: UUID | None = None,
) -> TranslationJob:
    """Core job-create: resolve effective settings + overrides, insert the job +
    chapter rows in one transaction, publish to RabbitMQ. Ownership is assumed
    already verified by the caller (public route via JWT+book-service; internal
    dispatch via the asserted-and-reverified user_id — decision A).

    S4a: `campaign_id` is an internal-only attribution tag (None for public
    callers); it is persisted on the job + rides the message chain to every
    provider job's job_meta."""
    uid = UUID(user_id)

    # Resolve effective settings, then overlay any per-job overrides (Fix-C): a one-off
    # translation can carry its own language/model so it does not depend on a prior
    # settings write having succeeded.
    # AUTHZ: a client-supplied model_ref is NOT trusted here — provider-registry resolves
    # it scoped to this user (`WHERE user_model_id=$1 AND owner_user_id=$2 AND is_active`,
    # server.go), so a forged/other-user model_ref resolves to nothing and the job fails.
    eff, _is_default, _updated_at = await resolve_effective_settings(uid, book_id, db)
    if payload.target_language:
        eff["target_language"] = payload.target_language
    if payload.model_source:
        eff["model_source"] = payload.model_source
    if payload.model_ref:
        eff["model_ref"] = payload.model_ref
    if payload.pipeline_version:
        eff["pipeline_version"] = payload.pipeline_version
    if payload.qa_depth:
        eff["qa_depth"] = payload.qa_depth
    if payload.max_qa_rounds is not None:
        eff["max_qa_rounds"] = payload.max_qa_rounds
    if payload.verifier_model_source:
        eff["verifier_model_source"] = payload.verifier_model_source
    if payload.verifier_model_ref:
        eff["verifier_model_ref"] = payload.verifier_model_ref
    if payload.eval_judge_model_source:
        eff["eval_judge_model_source"] = payload.eval_judge_model_source
    if payload.eval_judge_model_ref:
        eff["eval_judge_model_ref"] = payload.eval_judge_model_ref
    if payload.cold_start_mode:
        eff["cold_start_mode"] = payload.cold_start_mode
    if not eff.get("model_ref"):
        raise HTTPException(
            status_code=422,
            detail={"code": "TRANSL_NO_MODEL_CONFIGURED", "message": "No model configured. Set a model in Translation Settings before translating."},
        )

    # ── S2 idempotency gate (G3) ───────────────────────────────────────────
    # Declarative "ensure translated": reduce the requested chapters to the
    # to-do set {never-translated ∪ stale ∪ failed} before any fan-out. A
    # chapter is SKIPPED iff it has a fresh successful active translation for
    # this language (active version → status='completed' AND not glossary-stale).
    # force_retranslate bypasses the skip (explicit re-translate request).
    requested_ids = list(payload.chapter_ids)
    target_language = eff["target_language"]
    skipped_ids: list[UUID] = []
    if payload.force_retranslate:
        chapter_ids = requested_ids
    else:
        # SKIP a chapter iff a completed, non-stale translation EXISTS for this
        # language — NOT keyed on the *active* version. The worker promotes a
        # version to active only on the FIRST completion (`ON CONFLICT DO
        # NOTHING`, chapter_worker.py); a stale re-translation produces a fresh
        # v2 that never becomes active. Keying the gate on the active row would
        # therefore re-translate a stale chapter on EVERY re-run (active stays
        # stale forever) — a re-spend loop. "Exists a fresh completed version"
        # is the true cost-idempotency question and is loop-free: after the
        # stale chapter is re-translated once, the new non-stale row makes
        # subsequent runs skip it (until the next glossary change re-marks it).
        skip_rows = await db.fetch(
            """
            SELECT DISTINCT ct.chapter_id
            FROM chapter_translations ct
            WHERE ct.target_language = $1
              AND ct.chapter_id = ANY($2::uuid[])
              AND ct.status = 'completed'
              AND ct.is_glossary_stale = false
            """,
            target_language, requested_ids,
        )
        skip_set = {r["chapter_id"] for r in skip_rows}
        chapter_ids = [c for c in requested_ids if c not in skip_set]
        skipped_ids = [c for c in requested_ids if c in skip_set]

    # Insert job + chapter rows in ONE transaction (W7): a mid-loop failure must not
    # leave a job with a partial chapter set + mismatched total_chapters (which would
    # then never finalize). Publish only AFTER the commit so a worker never picks up a
    # half-created job.
    async with db.acquire() as conn:
        async with conn.transaction():
            job_row = await conn.fetchrow(
                """
                INSERT INTO translation_jobs
                  (book_id, owner_user_id, status, target_language, model_source, model_ref,
                   system_prompt, user_prompt_tpl,
                   compact_model_source, compact_model_ref,
                   compact_system_prompt, compact_user_prompt_tpl,
                   chunk_size_tokens, invoke_timeout_secs,
                   chapter_ids, total_chapters, pipeline_version,
                   qa_depth, max_qa_rounds, verifier_model_source, verifier_model_ref,
                   cold_start_mode, campaign_id,
                   eval_judge_model_source, eval_judge_model_ref)
                VALUES ($1,$2,'pending',$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,
                        $17,$18,$19,$20,$21,$22,$23,$24)
                RETURNING *
                """,
                book_id, uid,
                eff["target_language"], eff["model_source"], eff["model_ref"],
                eff["system_prompt"], eff["user_prompt_tpl"],
                eff.get("compact_model_source"), eff.get("compact_model_ref"),
                eff.get("compact_system_prompt", DEFAULT_COMPACT_SYSTEM_PROMPT),
                eff.get("compact_user_prompt_tpl", DEFAULT_COMPACT_USER_PROMPT_TPL),
                eff.get("chunk_size_tokens", 2000), eff.get("invoke_timeout_secs", 300),
                chapter_ids, len(chapter_ids), eff.get("pipeline_version", "v2"),
                eff.get("qa_depth", "standard"), eff.get("max_qa_rounds", 2),
                eff.get("verifier_model_source"), eff.get("verifier_model_ref"),
                eff.get("cold_start_mode", "single_pass"), campaign_id,
                eff.get("eval_judge_model_source"), eff.get("eval_judge_model_ref"),
            )

            job_id = job_row["job_id"]

            for chapter_id in chapter_ids:
                await conn.execute(
                    """
                    INSERT INTO chapter_translations
                      (job_id, chapter_id, book_id, owner_user_id, status, target_language, version_num)
                    VALUES ($1, $2, $3, $4, 'pending', $5,
                            COALESCE((SELECT MAX(version_num) FROM chapter_translations
                                      WHERE chapter_id=$2 AND target_language=$5), 0) + 1)
                    """,
                    job_id, chapter_id, book_id, uid, eff["target_language"],
                )

            # S2: emit a per-chapter done-signal for SKIPPED (already-current)
            # chapters so a resumed campaign's projection converges (decision:
            # a DISTINCT `chapter.translation_skipped` — NOT `chapter.translated`
            # — because statistics-service logs a translation_event for every
            # `chapter.translated`; this stays stats- and billing-neutral). Same
            # `chapter` aggregate stream the campaign-collector consumes.
            for cid in skipped_ids:
                await conn.execute(
                    """INSERT INTO outbox_events (event_type, aggregate_type, aggregate_id, payload)
                       VALUES ('chapter.translation_skipped', 'chapter', $1, $2::jsonb)""",
                    cid,
                    json.dumps({
                        "user_id": user_id,
                        "book_id": str(book_id),
                        "chapter_id": str(cid),
                        "target_language": target_language,
                        "status": "already_current",
                    }),
                )

            # All requested chapters already current → no fan-out; finalize now.
            if not chapter_ids:
                await conn.execute(
                    "UPDATE translation_jobs SET status='completed', finished_at=now() WHERE job_id=$1",
                    job_id,
                )

    # Publish the job only when there is work to fan out.
    if chapter_ids:
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
            "pipeline_version":        eff.get("pipeline_version", "v2"),
            "qa_depth":                eff.get("qa_depth", "standard"),
            "max_qa_rounds":           eff.get("max_qa_rounds", 2),
            "verifier_model_source":   eff.get("verifier_model_source"),
            "verifier_model_ref":      str(eff["verifier_model_ref"]) if eff.get("verifier_model_ref") else None,
            "eval_judge_model_source": eff.get("eval_judge_model_source"),
            "eval_judge_model_ref":    str(eff["eval_judge_model_ref"]) if eff.get("eval_judge_model_ref") else None,
            "cold_start_mode":         eff.get("cold_start_mode", "single_pass"),
            # S4a: ride campaign_id through the message chain (job → chapter → job_meta).
            "campaign_id":             str(campaign_id) if campaign_id else None,
        })
    await publish_event(user_id, {
        "event":    "job.created",
        "job_id":   str(job_id),
        "job_type": "translation",
        "payload":  {
            "book_id":        str(book_id),
            "total_chapters": len(chapter_ids),
            "status":         "completed" if not chapter_ids else "pending",
        },
    })

    if not chapter_ids:
        # Reflect the finalized status in the response (job_row was fetched pending).
        job_row = await db.fetchrow(
            "SELECT * FROM translation_jobs WHERE job_id=$1", job_id,
        )
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

async def _cancel_job_core(db: asyncpg.Pool, job_id: UUID, user_id: str) -> None:
    """Cancel core (shared by the public route + the S3c-2 internal endpoint).
    Owner-scoped (404 if not found / not owned), 409 if already terminal."""
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


@router.post("/jobs/{job_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_job(
    job_id: UUID,
    user_id: str = Depends(get_current_user),
    db: asyncpg.Pool = Depends(get_db),
):
    await _cancel_job_core(db, job_id, user_id)
