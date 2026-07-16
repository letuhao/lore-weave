import json
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import asyncpg
from loreweave_jobs import emit_job_event

from ..deps import get_current_user, get_db
from ..llm_client import get_llm_client
from ..config import DEFAULT_COMPACT_SYSTEM_PROMPT, DEFAULT_COMPACT_USER_PROMPT_TPL
from ..models import CreateJobPayload, TranslationJob, ChapterTranslation, ErrorResponse
from ..broker import publish, publish_event
from ..effective_settings import resolve_effective_settings
from ..languages import normalize_language, is_translation_target
from ..model_name import resolve_model_name
from ..grant_deps import (
    GrantLevel, require_book_grant, authorize_book, book_for_chapter, get_grant_client_dep,
)
from ..workers.segment_status import compute_segment_status

router = APIRouter(prefix="/v1/translation", tags=["translation-jobs"])

logger = logging.getLogger("translation.jobs")

#: Unified Job Control Plane P1 — the service id stamped on every emitted JobEvent.
_JOB_SERVICE = "translation"
#: kind stamped on translation_jobs lifecycle events (a translation_jobs row is
#: always a whole/partial-chapter translation run; there is no per-row operation col).
_JOB_KIND = "translation"


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
    # E0-4a: book-grant gate (edit). Replaces the old owner-only book-projection
    # check. Caller-attributed + caller-pays: the job is created under `user_id`
    # (the caller) and the worker resolves the caller's own BYOK model — a
    # collaborator translates on their own key, never the owner's.
    _grant: UUID = Depends(require_book_grant(GrantLevel.EDIT)),
    db: asyncpg.Pool = Depends(get_db),
):
    # S4a: campaign_id is NOT taken from the public body — a user must not be able
    # to tag their job to another user's campaign (which would inflate that
    # campaign's spend and trip its budget pause). Only the internal dispatch
    # endpoint (ownership pre-verified) supplies it.
    #
    # T2-M2 (review-impl LOW-3): block_index_filter/seed_version_id are part of the
    # model so the dedicated retranslate-dirty endpoint can build the payload, but a
    # general create-job must NOT smuggle a partial-retranslate scope (defense in
    # depth beyond the worker's chapter-scoped seed load). Strip them here.
    payload.block_index_filter = None
    payload.seed_version_id = None
    return await _resolve_and_create_job(db, book_id, payload, user_id)


# ── T2-M2: dirty-only re-translate ────────────────────────────────────────────

class RetranslateDirtyPayload(BaseModel):
    target_language: str


@router.post(
    "/chapters/{chapter_id}/retranslate-dirty",
    response_model=TranslationJob,
    status_code=status.HTTP_201_CREATED,
)
async def retranslate_dirty(
    chapter_id: UUID,
    body: RetranslateDirtyPayload,
    user_id: str = Depends(get_current_user),
    gc=Depends(get_grant_client_dep),
    db: asyncpg.Pool = Depends(get_db),
):
    """Re-translate ONLY the segments whose source changed since the last translation
    (T2-M2). Computes the dirty block range, resolves the prior llm version as the
    seed (its unchanged blocks are copied), and enqueues a single-chapter job scoped
    to those blocks — the worker overlays the freshly-translated blocks onto the seed
    and finalizes a normal new version (auto-promote never clobbers a human edit)."""
    book_id = await book_for_chapter(db, chapter_id)
    if book_id is None:
        raise HTTPException(status_code=404, detail={"code": "TRANSL_NOT_FOUND", "message": "Chapter has no translations"})
    await authorize_book(gc, book_id, UUID(user_id), GrantLevel.EDIT)
    return await _retranslate_dirty_core(
        db, chapter_id, body.target_language, user_id, book_id=book_id,
    )


async def _retranslate_dirty_core(
    db: asyncpg.Pool, chapter_id: UUID, target_language: str, user_id: str,
    *, book_id: UUID | None = None,
    mcp_key_id: str | None = None, spend_cap_usd: float | None = None,
) -> "TranslationJob":
    """Core of the dirty-only re-translate — book ownership is assumed ALREADY
    verified by the caller (the public route authorizes via the E0-4a grant gate;
    the MCP Tier-W confirm route via the kit's `require_book_owner` at mint + the
    user binding in the confirm token). Reused by both so the dirty-set selection,
    seed resolution, and job-create stay byte-identical (no second copy to drift).

    `book_id` is passed by the public route (which already resolved it) to avoid a
    redundant lookup; the MCP confirm path omits it and lets the core resolve it
    from the chapter."""
    if book_id is None:
        book_id = await book_for_chapter(db, chapter_id)
    if book_id is None:
        raise HTTPException(status_code=404, detail={"code": "TRANSL_NOT_FOUND", "message": "Chapter has no translations"})

    lang = target_language
    items = await compute_segment_status(db, chapter_id, lang)
    # "needs" = source-dirty ∪ glossary-stale (T2-M3.2) — every segment that should
    # be re-translated, not just the source-changed ones.
    needed = [it for it in items if it["needs"]]
    if not needed:
        raise HTTPException(
            status_code=409,
            detail={"code": "TRANSL_NO_DIRTY_SEGMENTS", "message": "No segments need re-translation"},
        )
    block_idx = sorted({
        i for it in needed
        for i in range(it["start_block_index"], it["end_block_index"] + 1)
    })

    # Seed = the latest completed MACHINE version for this language (its unchanged
    # blocks are copied). A human version is never the seed (we never re-derive over
    # a human edit); if only a human version exists, the human can re-run a full
    # translation or adopt explicitly.
    seed = await db.fetchval(
        "SELECT id FROM chapter_translations "
        "WHERE chapter_id=$1 AND target_language=$2 AND status='completed' AND authored_by='llm' "
        "ORDER BY version_num DESC LIMIT 1",
        chapter_id, lang,
    )
    if not seed:
        raise HTTPException(
            status_code=409,
            detail={"code": "TRANSL_NO_SEED_VERSION", "message": "No prior machine translation to patch; run a full translation first"},
        )

    payload = CreateJobPayload(
        chapter_ids=[chapter_id],
        target_language=lang,
        force_retranslate=True,  # bypass the chapter-level skip-gate (we know it's dirty per-segment)
        block_index_filter=block_idx,
        seed_version_id=seed,
    )
    return await _resolve_and_create_job(
        db, book_id, payload, user_id,
        mcp_key_id=mcp_key_id, spend_cap_usd=spend_cap_usd,
    )


async def _resolve_and_create_job(
    db: asyncpg.Pool, book_id: UUID, payload: CreateJobPayload, user_id: str,
    *, campaign_id: UUID | None = None,
    mcp_key_id: str | None = None, spend_cap_usd: float | None = None,
) -> TranslationJob:
    """Core job-create: resolve effective settings + overrides, insert the job +
    chapter rows in one transaction, publish to RabbitMQ. Ownership is assumed
    already verified by the caller (public route via JWT+book-service; internal
    dispatch via the asserted-and-reverified user_id — decision A).

    S4a: `campaign_id` is an internal-only attribution tag (None for public
    callers); it is persisted on the job + rides the message chain to every
    provider job's job_meta.

    D-PMCP-WORKER-CARRIER: `mcp_key_id`/`spend_cap_usd` are the PUBLIC-MCP-key
    attribution (None for first-party callers), set ONLY by the confirm-route
    replay. They persist on the job row + ride the message chain so the background
    chapter worker can re-set the loreweave_llm contextvar before each provider
    call (the in-process contextvar dies at the AMQP hop). Server-set: never read
    from a public-controllable body."""
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

    # D13 — normalize, then validate target_language against the content-language SSOT
    # (contracts/languages.contract.json, mirrored in app/languages.py). A lenient client value
    # is corrected ("VI"→"vi", "zh_CN"→"zh-CN"); anything outside the closed registry is rejected
    # 400. The picker offers exactly the registry, so if you cannot pick it you cannot submit it —
    # this is the writer that first admitted the free-text "Vietnamese". Reads still tolerate
    # unknown legacy codes; this constrains WRITES only.
    raw_lang = eff.get("target_language")
    if not raw_lang:
        raise HTTPException(
            status_code=422,
            detail={"code": "TRANSL_NO_LANGUAGE", "message": "No target language configured. Choose a language before translating."},
        )
    norm_lang = normalize_language(str(raw_lang))
    if not is_translation_target(norm_lang):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_target_language", "message": f"'{raw_lang}' is not a supported target language."},
        )
    eff["target_language"] = norm_lang

    # P4 usage emit — resolve the human model NAME (best-effort, PRE-tx; H1) + assemble a
    # whitelisted params dict for the Jobs GUI. model + params ride the 'pending' create
    # event ONLY; the projection's COALESCE merge preserves them across later events, so
    # the coordinator/finalize emits never need to (and never clobber them with a leaner set).
    _model_name = await resolve_model_name(eff.get("model_source"), str(eff["model_ref"]))
    _job_params = {
        "model": _model_name,
        "model_ref": str(eff["model_ref"]),
        "target_language": eff.get("target_language"),
        "pipeline_version": eff.get("pipeline_version", "v2"),
        "qa_depth": eff.get("qa_depth", "standard"),
        "verifier_enabled": bool(eff.get("verifier_model_ref")),
        "cold_start_mode": eff.get("cold_start_mode", "single_pass"),
    }

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
        # language — NOT keyed on the *active* version. "Exists a fresh completed
        # version" is the true cost-idempotency question and is loop-free: after a
        # stale chapter is re-translated once, the new non-stale row makes
        # subsequent runs skip it (until the next glossary change re-marks it).
        # Keying on the *active* row instead would be unsafe — a re-translation
        # whose promote is held back (e.g. the worker's human-edit guard, or an
        # M5b verifier flag) would leave the active row stale and re-translate on
        # EVERY run (a re-spend loop). The existence check sidesteps that entirely.
        # (Worker promotion policy: chapter_worker.py auto-promotes a clean version
        # over an existing active one unless the active is a human edit — but this
        # gate does not depend on that, by design.)
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
                   eval_judge_model_source, eval_judge_model_ref,
                   block_index_filter, seed_version_id, thinking_enabled,
                   mcp_key_id, spend_cap_usd)
                VALUES ($1,$2,'pending',$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,
                        $17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29)
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
                payload.block_index_filter, payload.seed_version_id,
                payload.thinking_enabled,
                mcp_key_id, spend_cap_usd,
            )

            job_id = job_row["job_id"]

            # Unified Job Control Plane P1 — emit the initial lifecycle event in the
            # SAME tx as the INSERT (transactional outbox H1: row + event commit
            # atomically). Genuinely-new row only — this is an unconditional INSERT
            # (no idempotency replay path here).
            await emit_job_event(
                conn, service=_JOB_SERVICE, job_id=str(job_id),
                owner_user_id=str(job_row["owner_user_id"]), kind=_JOB_KIND,
                status="pending", model=_model_name, params=_job_params,
            )

            # Sorted iteration → deterministic advisory-lock order, so two overlapping jobs
            # can never deadlock on a shared chapter (global lock ordering). The lock
            # serializes concurrent same-(chapter,lang) inserts so the MAX(version_num)+1
            # below cannot collide on idx_ct_version (D-TRANSL-VERSION-NUM-RACE). Same lock
            # key as the edit/patch paths in versions.py. Released at tx commit.
            for chapter_id in sorted(chapter_ids, key=str):
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1)::bigint)",
                    f"{chapter_id}|{eff['target_language']}",
                )
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
                # P1 — terminal transition (all requested chapters already current);
                # same tx as the UPDATE.
                await emit_job_event(
                    conn, service=_JOB_SERVICE, job_id=str(job_id),
                    owner_user_id=str(job_row["owner_user_id"]), kind=_JOB_KIND,
                    status="completed",
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
            # D-TRANSLATE-REASONING-TOGGLE: ride the per-job thinking flag to the worker.
            "thinking_enabled":        payload.thinking_enabled,
            # S4a: ride campaign_id through the message chain (job → chapter → job_meta).
            "campaign_id":             str(campaign_id) if campaign_id else None,
            # D-PMCP-WORKER-CARRIER: ride the public-MCP key + cap through the message
            # chain so the chapter worker re-sets the attribution contextvar.
            "mcp_key_id":              mcp_key_id,
            "spend_cap_usd":           spend_cap_usd,
            # T2-M2: dirty-only re-translate scope (None for whole-chapter jobs).
            "block_index_filter":      payload.block_index_filter,
            "seed_version_id":         str(payload.seed_version_id) if payload.seed_version_id else None,
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
    # E0-4a view gate + D-E0-4-F shared per-book view: drop the owner_user_id
    # predicate so every grantee sees ALL of the book's translation jobs (book_id
    # still scopes → IDOR-safe). Writes stay caller-attributed.
    _grant: UUID = Depends(require_book_grant(GrantLevel.VIEW)),
    db: asyncpg.Pool = Depends(get_db),
):
    rows = await db.fetch(
        """SELECT * FROM translation_jobs
           WHERE book_id=$1
           ORDER BY created_at DESC LIMIT $2 OFFSET $3""",
        book_id, limit, offset,
    )
    return [_job_row_to_model(r) for r in rows]


# ── Get job detail ────────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}", response_model=TranslationJob)
async def get_job(
    job_id: UUID,
    user_id: str = Depends(get_current_user),
    gc=Depends(get_grant_client_dep),
    db: asyncpg.Pool = Depends(get_db),
):
    row = await db.fetchrow("SELECT * FROM translation_jobs WHERE job_id=$1", job_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "TRANSL_NOT_FOUND", "message": "Job not found"})
    # E0-4a view gate (job→book grant). authorize_book raises 404 for a non-grantee
    # — uniform with the missing-job 404 above (no existence oracle). Inline (reuses
    # the row's book_id) rather than a pre-fetch dep.
    await authorize_book(gc, row["book_id"], UUID(user_id), GrantLevel.VIEW)

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
    gc=Depends(get_grant_client_dep),
    db: asyncpg.Pool = Depends(get_db),
):
    row = await db.fetchrow(
        "SELECT * FROM chapter_translations WHERE job_id=$1 AND chapter_id=$2",
        job_id, chapter_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail={"code": "TRANSL_NOT_FOUND", "message": "Chapter translation not found"})
    # E0-4a view gate (chapter→book grant); non-grantee → 404 (uniform anti-oracle).
    await authorize_book(gc, row["book_id"], UUID(user_id), GrantLevel.VIEW)

    return ChapterTranslation(**dict(row))


# ── Cancel job ────────────────────────────────────────────────────────────────

async def _cancel_job_core(db: asyncpg.Pool, job_id: UUID, user_id: str) -> None:
    """Owner-scoped cancel — used by the S3c-2 INTERNAL dispatch endpoint, which
    asserts a `user_id` (the campaign's verified caller). 404 if not found / not
    owned, 409 if already terminal. (The PUBLIC route authorizes via the E0-4a
    grant gate instead — see `cancel_job` + `_cancel_job_transition`.)"""
    row = await db.fetchrow(
        "SELECT owner_user_id, status FROM translation_jobs WHERE job_id=$1", job_id
    )
    if not row or str(row["owner_user_id"]) != user_id:
        raise HTTPException(status_code=404, detail={"code": "TRANSL_NOT_FOUND", "message": "Job not found"})
    _assert_cancellable(row["status"])
    await _do_cancel(db, job_id)


def _assert_cancellable(job_status: str) -> None:
    if job_status not in ("pending", "running"):
        raise HTTPException(
            status_code=409,
            detail={"code": "TRANSL_CANNOT_CANCEL", "message": f"Job is already {job_status}"},
        )


async def _do_cancel(db: asyncpg.Pool, job_id: UUID) -> None:
    # P1 — terminal cancel transition. Acquire our own conn + tx so the UPDATE and
    # the JobEvent emit commit atomically (H1). RETURNING owner_user_id so the event
    # carries the right owner without a second read.
    async with db.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "UPDATE translation_jobs SET status='cancelled', finished_at=now() "
                "WHERE job_id=$1 RETURNING owner_user_id",
                job_id,
            )
            if row is None:
                return  # already gone / nothing matched — no event for a no-op
            await emit_job_event(
                conn, service=_JOB_SERVICE, job_id=str(job_id),
                owner_user_id=str(row["owner_user_id"]), kind=_JOB_KIND,
                status="cancelled",
            )
    # bug #34 (D-CANCEL-IMMEDIATE-TRANSLATION-DECOUPLED) — abort the in-flight provider
    # call(s) NOW so the user's cancel stops token-burn immediately on the decoupled path
    # (which never sits in wait_terminal(cancel_check)). Outside the status tx: a DELETE is
    # network I/O (must not run inside the finalize tx) and is best-effort — the
    # terminal-consumer cancel-gate is the correctness backstop if a DELETE fails.
    await _abort_inflight_provider_jobs(db, job_id)


async def _abort_inflight_provider_jobs(db: asyncpg.Pool, job_id: UUID) -> None:
    """bug #34 — the decoupled translate path submits one provider LLM job per chapter and
    RELEASES (the wait + resume happen in the terminal-consumer, not in
    wait_terminal(cancel_check)), so a user-cancel can't abort the in-flight upstream call
    the way the synchronous path does. DELETE every in-flight provider job for this
    translation job's non-terminal chapters → provider-registry aborts the upstream call
    immediately (the SAME DELETE the sync path's cancel_check issues). Best-effort per job:
    a failure just falls back to the consumer's cancel-gate (cooperative stop at the next
    batch boundary). No-op for the synchronous path (provider_job_id is decoupled-only)."""
    rows = await db.fetch(
        "SELECT provider_job_id, owner_user_id FROM chapter_translations "
        "WHERE job_id=$1 AND provider_job_id IS NOT NULL "
        "AND status NOT IN ('completed', 'failed')",
        job_id,
    )
    if not rows:
        return
    llm = get_llm_client()
    for r in rows:
        try:
            await llm.sdk.cancel_job(
                str(r["provider_job_id"]), user_id=str(r["owner_user_id"]),
            )
        except Exception:  # noqa: BLE001 — best-effort; the consumer cancel-gate still stops it
            logger.warning(
                "translation cancel: aborting in-flight provider job %s failed — will stop "
                "cooperatively at the terminal-consumer", r["provider_job_id"], exc_info=True,
            )


async def _pause_job_core(db: asyncpg.Pool, job_id: UUID, owner_user_id: UUID) -> dict:
    """B2 stop-dispatch PAUSE (D-JOBS-P3-TRANSLATION-PAUSE) — owner-scoped. running→paused;
    the chapter worker drops paused units at its start gate so no NEW chapter work begins,
    while chapters already in-flight drain. 404 if not found/owned, 409 if not running."""
    async with db.acquire() as conn:
        async with conn.transaction():  # UPDATE + emit atomic (H1)
            row = await conn.fetchrow(
                "UPDATE translation_jobs SET status='paused' "
                "WHERE job_id=$1 AND owner_user_id=$2 AND status='running' "
                "RETURNING owner_user_id",
                job_id, owner_user_id,
            )
            if row is not None:
                await emit_job_event(
                    conn, service=_JOB_SERVICE, job_id=str(job_id),
                    owner_user_id=str(row["owner_user_id"]), kind=_JOB_KIND, status="paused",
                )
                return {"job_id": str(job_id), "status": "paused"}
    # No transition — disambiguate owner-scoped (404 not owned/found vs 409 wrong state).
    cur = await db.fetchrow(
        "SELECT status FROM translation_jobs WHERE job_id=$1 AND owner_user_id=$2",
        job_id, owner_user_id,
    )
    if cur is None:
        raise HTTPException(status_code=404, detail={"code": "TRANSL_NOT_FOUND", "message": "Job not found"})
    raise HTTPException(
        status_code=409,
        detail={"code": "TRANSL_CANNOT_PAUSE", "message": f"Job is {cur['status']}, not running"},
    )


def _job_message_from_row(row, chapter_ids: list) -> dict:
    """Rebuild the `translation.job` coordinator message from a stored `translation_jobs`
    row (every field is persisted at create) + a chapter subset. Mirrors the create-time
    publish in `_resolve_and_create_job` so the coordinator fans out identically. All UUIDs
    are str()'d for the JSON body; block_index_filter (INT[]) is already JSON-serializable."""
    return {
        "job_id":                  str(row["job_id"]),
        "user_id":                 str(row["owner_user_id"]),
        "book_id":                 str(row["book_id"]),
        "chapter_ids":             [str(c) for c in chapter_ids],
        "model_source":            row["model_source"],
        "model_ref":               str(row["model_ref"]),
        "system_prompt":           row["system_prompt"],
        "user_prompt_tpl":         row["user_prompt_tpl"],
        "target_language":         row["target_language"],
        "compact_model_source":    row["compact_model_source"],
        "compact_model_ref":       str(row["compact_model_ref"]) if row["compact_model_ref"] else None,
        "compact_system_prompt":   row["compact_system_prompt"],
        "compact_user_prompt_tpl": row["compact_user_prompt_tpl"],
        "chunk_size_tokens":       row["chunk_size_tokens"],
        "invoke_timeout_secs":     row["invoke_timeout_secs"],
        "pipeline_version":        row["pipeline_version"],
        "qa_depth":                row["qa_depth"],
        "max_qa_rounds":           row["max_qa_rounds"],
        "verifier_model_source":   row["verifier_model_source"],
        "verifier_model_ref":      str(row["verifier_model_ref"]) if row["verifier_model_ref"] else None,
        "eval_judge_model_source": row["eval_judge_model_source"],
        "eval_judge_model_ref":    str(row["eval_judge_model_ref"]) if row["eval_judge_model_ref"] else None,
        "cold_start_mode":         row["cold_start_mode"],
        # D-TRANSLATE-REASONING-TOGGLE: rebuilt from the row so resume keeps the setting.
        "thinking_enabled":        row["thinking_enabled"],
        "campaign_id":             str(row["campaign_id"]) if row["campaign_id"] else None,
        # D-PMCP-WORKER-CARRIER: rebuilt from the row so a resume/retry of a
        # public-key job keeps attributing the re-spend to the agent's key. The column
        # is DOUBLE PRECISION → already a float; the coalesce keeps NULL as None.
        "mcp_key_id":              row["mcp_key_id"],
        "spend_cap_usd":           float(row["spend_cap_usd"]) if row["spend_cap_usd"] is not None else None,
        "block_index_filter":      row["block_index_filter"],
        "seed_version_id":         str(row["seed_version_id"]) if row["seed_version_id"] else None,
    }


async def _resume_job_core(db: asyncpg.Pool, job_id: UUID, owner_user_id: UUID) -> dict:
    """B2 stop-dispatch RESUME (D-JOBS-P3-TRANSLATION-PAUSE) — owner-scoped. paused→running,
    then re-drive the UN-ATTEMPTED chapters (this job's `chapter_translations` rows still
    'pending') by re-publishing `translation.job` for the SAME job_id, rebuilt from the
    stored row.

    ONLY 'pending' is re-dispatched — NOT 'running'/'completed'/'failed':
      - 'running'  — in-flight (or the sweeper's to reclaim); re-dispatching would race a
        live chapter (the one concurrency the stop-dispatch model must avoid).
      - 'completed'— already done.
      - 'failed'   — already counted in `failed_chapters`. Re-running it would increment
        `completed_chapters` WITHOUT decrementing `failed_chapters`, pushing
        completed+failed past total_chapters so the strict `= total_chapters` finalize guard
        never matches → the job would hang at 'running'. Resume = CONTINUE un-attempted work,
        so a failed chapter stays failed and the job finalizes to 'partial' — exactly the
        non-pause semantics. (Re-attempting failures is the separate `retry` action.)

    404 if not found/owned, 409 if not paused. No pending chapters → status flip only (the
    job finalizes via its normal completion path as in-flight chapters drain)."""
    async with db.acquire() as conn:
        async with conn.transaction():  # UPDATE + emit atomic (H1)
            row = await conn.fetchrow(
                "UPDATE translation_jobs SET status='running' "
                "WHERE job_id=$1 AND owner_user_id=$2 AND status='paused' "
                "RETURNING *",
                job_id, owner_user_id,
            )
            if row is not None:
                await emit_job_event(
                    conn, service=_JOB_SERVICE, job_id=str(job_id),
                    owner_user_id=str(row["owner_user_id"]), kind=_JOB_KIND, status="running",
                )
    if row is None:
        cur = await db.fetchrow(
            "SELECT status FROM translation_jobs WHERE job_id=$1 AND owner_user_id=$2",
            job_id, owner_user_id,
        )
        if cur is None:
            raise HTTPException(status_code=404, detail={"code": "TRANSL_NOT_FOUND", "message": "Job not found"})
        raise HTTPException(
            status_code=409,
            detail={"code": "TRANSL_CANNOT_RESUME", "message": f"Job is {cur['status']}, not paused"},
        )

    # Re-drive un-attempted chapters (publish AFTER the status commit, like create).
    # 'pending' ONLY — see the docstring for why 'running'/'completed'/'failed' are excluded
    # (count integrity: re-running a 'failed' chapter would strand the job at 'running').
    undone = await db.fetch(
        "SELECT chapter_id FROM chapter_translations "
        "WHERE job_id=$1 AND status = 'pending'",
        job_id,
    )
    undone_ids = [r["chapter_id"] for r in undone]
    if undone_ids:
        await publish("translation.job", _job_message_from_row(row, undone_ids))
    return {"job_id": str(job_id), "status": "running"}


@router.post("/jobs/{job_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_job(
    job_id: UUID,
    user_id: str = Depends(get_current_user),
    gc=Depends(get_grant_client_dep),
    db: asyncpg.Pool = Depends(get_db),
):
    # E0-4a edit gate (job→book grant): a collaborator with edit can cancel a job on
    # the shared book (shared management). Inline authorize on the row's book_id —
    # a non-grantee gets 404 (uniform anti-oracle), NOT the old owner check.
    row = await db.fetchrow(
        "SELECT book_id, status FROM translation_jobs WHERE job_id=$1", job_id
    )
    if not row:
        raise HTTPException(status_code=404, detail={"code": "TRANSL_NOT_FOUND", "message": "Job not found"})
    await authorize_book(gc, row["book_id"], UUID(user_id), GrantLevel.EDIT)
    _assert_cancellable(row["status"])
    await _do_cancel(db, job_id)
