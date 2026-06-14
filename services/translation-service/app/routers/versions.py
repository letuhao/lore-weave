import json
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
import asyncpg

from ..deps import get_current_user, get_db
from ..grant_deps import (
    GrantLevel,
    authorize_book,
    book_for_chapter,
    get_grant_client_dep,
)

log = logging.getLogger(__name__)
from ..models import (
    ChapterTranslation,
    ChapterVersionsResponse,
    LanguageVersionGroup,
    VersionSummary,
    ActiveVersionResponse,
    SaveEditedTranslationRequest,
    PatchTranslationBlockRequest,
)

router = APIRouter(prefix="/v1/translation", tags=["translation-versions"])


def _block_text(node: dict) -> str:
    """Plain-text projection of a Tiptap block (mirrors the FE extractText) — used to
    keep the flat `translated_body` consistent after a per-block patch."""
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text") or ""
    if node.get("type") == "hardBreak":
        return "\n"
    return "".join(_block_text(c) for c in (node.get("content") or []))


def _blocks_to_text(blocks: list) -> str:
    return "\n\n".join(_block_text(b) for b in (blocks or []))


def _as_list(v) -> list:
    """asyncpg may hand back JSONB as a str (text protocol) or a parsed list."""
    if v is None:
        return []
    if isinstance(v, str):
        try:
            return json.loads(v) or []
        except (ValueError, TypeError):
            return []
    return v if isinstance(v, list) else []


# ── List all versions for a chapter, grouped by language ───────────────────────

@router.get("/chapters/{chapter_id}/versions", response_model=ChapterVersionsResponse)
async def list_chapter_versions(
    chapter_id: UUID,
    user_id: str = Depends(get_current_user),
    gc=Depends(get_grant_client_dep),
    db: asyncpg.Pool = Depends(get_db),
):
    # E0-4a: a chapter with no translations yet has no book to resolve a grant on
    # → return empty (leak-safe, preserves the prior empty-list behavior for owners
    # too). Once translations exist, gate on the book grant (view) then show ALL
    # versions for the chapter (D-E0-4-F shared per-book view — drop owner_user_id).
    book_id = await book_for_chapter(db, chapter_id)
    if book_id is None:
        return ChapterVersionsResponse(chapter_id=chapter_id, languages=[])
    await authorize_book(gc, book_id, UUID(user_id), GrantLevel.VIEW)

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
        ORDER BY ct.target_language, ct.version_num DESC
        """,
        chapter_id,
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
    gc=Depends(get_grant_client_dep),
    db: asyncpg.Pool = Depends(get_db),
):
    row = await db.fetchrow(
        "SELECT * FROM chapter_translations WHERE id=$1 AND chapter_id=$2",
        version_id, chapter_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail={"code": "TRANSL_NOT_FOUND", "message": "Version not found"})
    # E0-4a view gate (version→book grant); non-grantee → 404 (uniform anti-oracle).
    await authorize_book(gc, row["book_id"], UUID(user_id), GrantLevel.VIEW)

    return ChapterTranslation(**dict(row))


# ── Set active version ────────────────────────────────────────────────────────

@router.put("/chapters/{chapter_id}/versions/{version_id}/active", response_model=ActiveVersionResponse)
async def set_active_version(
    chapter_id: UUID,
    version_id: UUID,
    acknowledge_issues: bool = False,
    user_id: str = Depends(get_current_user),
    gc=Depends(get_grant_client_dep),
    db: asyncpg.Pool = Depends(get_db),
):
    row = await db.fetchrow(
        "SELECT owner_user_id, book_id, target_language, status, unresolved_high_count "
        "FROM chapter_translations WHERE id=$1 AND chapter_id=$2",
        version_id, chapter_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail={"code": "TRANSL_NOT_FOUND", "message": "Version not found"})
    # E0-4a edit gate (version→book) — publishing the active version is an edit
    # action; the published version is per-(chapter,language) shared state. The
    # set_by_user_id below is the caller (caller-attributed). Non-grantee → 404.
    await authorize_book(gc, row["book_id"], UUID(user_id), GrantLevel.EDIT)

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
    gc=Depends(get_grant_client_dep),
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
    # E0-4a edit gate (source-version→book). Saving a human edit creates a new
    # version attributed to the caller; an edit grant on the book authorizes it.
    await authorize_book(gc, src["book_id"], UUID(user_id), GrantLevel.EDIT)
    if src["target_language"] != body.target_language:
        raise HTTPException(
            status_code=422,
            detail={"code": "TRANSL_LANG_MISMATCH", "message": "target_language does not match the source version"},
        )

    # New human version: max(version_num)+1 for (chapter, lang); reuse the source
    # version's job_id/book_id (the edit attaches to the same job — avoids making
    # job_id a nullable FK). E0-4a caller-attribution: owner_user_id is the CALLER
    # ($7), NOT the source's owner — a collaborator's human edit belongs to the
    # collaborator (review-impl MED-1). authored_by='human' + the parent link.
    new = await db.fetchrow(
        """
        INSERT INTO chapter_translations
          (job_id, chapter_id, book_id, owner_user_id, status, target_language,
           translated_body, translated_body_json, translated_body_format,
           version_num, authored_by, edited_from_version_id, finished_at)
        SELECT job_id, chapter_id, book_id, $7::uuid, 'completed', target_language,
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
        UUID(user_id),
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


# ── Patch a single translated block (T1 per-block correction) ─────────────────

@router.patch(
    "/chapters/{chapter_id}/versions/blocks",
    response_model=ChapterTranslation,
)
async def patch_translation_block(
    chapter_id: UUID,
    body: PatchTranslationBlockRequest,
    user_id: str = Depends(get_current_user),
    gc=Depends(get_grant_client_dep),
    db: asyncpg.Pool = Depends(get_db),
):
    """T1 (model a): correct ONE translated block in the chapter's single human-version.

    The first patch get-or-creates the human-version (``authored_by='human'``) seeded
    from ``base_version_id`` and makes it active; later patches edit it in place via
    ``jsonb_set`` on just the target index — so concurrent edits to *different* blocks
    merge (the row lock serializes the statements). Per-block LLM→human gold is emitted
    (``translation.corrected`` with ``block_index``). Block (json) format only."""
    base = await db.fetchrow(
        "SELECT owner_user_id, book_id, target_language, status, version_num, "
        "translated_body_json, translated_body_format "
        "FROM chapter_translations WHERE id=$1 AND chapter_id=$2",
        body.base_version_id, chapter_id,
    )
    if not base:
        raise HTTPException(status_code=404, detail={"code": "TRANSL_NOT_FOUND", "message": "Base version not found"})
    # E0-4a edit gate (base-version→book): correcting a block is an edit action; the
    # human-version is per-(chapter,language) shared state, caller-attributed.
    await authorize_book(gc, base["book_id"], UUID(user_id), GrantLevel.EDIT)
    if base["target_language"] != body.target_language:
        raise HTTPException(status_code=422, detail={"code": "TRANSL_LANG_MISMATCH", "message": "target_language does not match the base version"})
    if base["translated_body_format"] != "json":
        raise HTTPException(status_code=422, detail={"code": "TRANSL_NOT_BLOCK_FORMAT", "message": "Per-block correction requires a block (json) format version"})

    base_blocks = _as_list(base["translated_body_json"])
    lang = body.target_language

    async with db.acquire() as conn:
        async with conn.transaction():
            # Serialize get-or-create so two near-simultaneous first-edits (multi-device)
            # can't each INSERT a human-version (no unique-index migration needed).
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1)::bigint)", f"{chapter_id}|{lang}")

            hv = await conn.fetchrow(
                "SELECT id, translated_body_json FROM chapter_translations "
                "WHERE chapter_id=$1 AND target_language=$2 AND authored_by='human' "
                "ORDER BY version_num DESC LIMIT 1",
                chapter_id, lang,
            )
            if not hv:
                # Seed the single human-version from the base LLM version + make it active.
                hv = await conn.fetchrow(
                    """
                    INSERT INTO chapter_translations
                      (job_id, chapter_id, book_id, owner_user_id, status, target_language,
                       translated_body, translated_body_json, translated_body_format,
                       version_num, authored_by, edited_from_version_id, finished_at)
                    SELECT job_id, chapter_id, book_id, $4::uuid, 'completed', target_language,
                           translated_body, translated_body_json, translated_body_format,
                           COALESCE((SELECT MAX(version_num) FROM chapter_translations
                                      WHERE chapter_id=$2 AND target_language=$3), 0) + 1,
                           'human', $1, now()
                    FROM chapter_translations WHERE id=$1
                    RETURNING id, translated_body_json
                    """,
                    body.base_version_id, chapter_id, lang, UUID(user_id),
                )
                await conn.execute(
                    """
                    INSERT INTO active_chapter_translation_versions
                      (chapter_id, target_language, chapter_translation_id, set_by_user_id, set_at)
                    VALUES ($1, $2, $3, $4, now())
                    ON CONFLICT (chapter_id, target_language)
                      DO UPDATE SET chapter_translation_id=$3, set_by_user_id=$4, set_at=now()
                    """,
                    chapter_id, lang, hv["id"], UUID(user_id),
                )

            hv_id = hv["id"]
            hv_blocks = _as_list(hv["translated_body_json"])
            if not (0 <= body.block_index < len(hv_blocks)):
                raise HTTPException(status_code=422, detail={"code": "TRANSL_BLOCK_INDEX_OOR", "message": "block_index out of range"})

            # Patch only the target index (merge-safe under the row lock).
            await conn.execute(
                "UPDATE chapter_translations "
                "SET translated_body_json = jsonb_set(translated_body_json, ARRAY[$2::text], $3::jsonb, false) "
                "WHERE id=$1",
                hv_id, str(body.block_index), json.dumps(body.block),
            )
            # Keep the flat text projection consistent (copy/search/coverage use it).
            new_blocks = list(hv_blocks)
            new_blocks[body.block_index] = body.block
            await conn.execute(
                "UPDATE chapter_translations SET translated_body=$2, finished_at=now() WHERE id=$1",
                hv_id, _blocks_to_text(new_blocks),
            )
            updated = await conn.fetchrow("SELECT * FROM chapter_translations WHERE id=$1", hv_id)

    # Per-block gold (best-effort post-commit): LLM base block → human block.
    try:
        before_block = base_blocks[body.block_index] if body.block_index < len(base_blocks) else None
        await db.execute(
            """INSERT INTO outbox_events (event_type, aggregate_type, aggregate_id, payload)
               VALUES ('translation.corrected', 'translation', $1, $2::jsonb)""",
            updated["id"],
            json.dumps({
                "user_id": user_id,
                "book_id": str(base["book_id"]),
                "chapter_id": str(chapter_id),
                "chapter_translation_id": str(updated["id"]),
                "edited_from_version_id": str(body.base_version_id),
                "target_language": lang,
                "block_index": body.block_index,
                "source_block_text": body.source_block_text,
                "before": {"block": before_block},
                "after": {"block": body.block},
            }),
        )
    except Exception:  # noqa: BLE001 — telemetry must not lose the edit
        log.warning("T1: failed to emit per-block translation.corrected (non-fatal)", exc_info=True)

    return ChapterTranslation(**dict(updated))
