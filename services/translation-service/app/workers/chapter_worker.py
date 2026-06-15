import json
import logging
from uuid import UUID

import httpx

from ..config import settings
from ..llm_client import LLMClient, set_campaign_id
from ..metrics import record_stage
from .session_translator import translate_chapter

log = logging.getLogger(__name__)

# Default context window used when provider-registry cannot supply one
_FALLBACK_CONTEXT_WINDOW = 8192

# Publish-on-completion SQL (params: $1=chapter_id, $2=chapter_translation_id).
# Promotes a freshly-completed CLEAN version (unresolved_high_count=0, the M5b gate)
# to active even over an existing active one — for BOTH campaign and interactive
# re-translation. The ONE guard: never clobber a HUMAN-edited active version — the
# DO UPDATE WHERE inspects the CURRENTLY-active version's authored_by; if it is
# 'human' (saved via the edit endpoint) the update is skipped. Worker drafts default
# to authored_by='llm', so an llm→llm promote always proceeds. Extracted as a module
# constant so the real-PG regression test executes the EXACT statement the worker runs.
_PROMOTE_ACTIVE_SQL = """
INSERT INTO active_chapter_translation_versions
  (chapter_id, target_language, chapter_translation_id, set_by_user_id)
SELECT $1, ct.target_language, $2, ct.owner_user_id
FROM chapter_translations ct
WHERE ct.id = $2
  AND COALESCE(ct.unresolved_high_count, 0) = 0
ON CONFLICT (chapter_id, target_language) DO UPDATE
  SET chapter_translation_id = EXCLUDED.chapter_translation_id,
      set_by_user_id = EXCLUDED.set_by_user_id,
      set_at = now()
  WHERE COALESCE(
    (SELECT cur.authored_by FROM chapter_translations cur
      WHERE cur.id = active_chapter_translation_versions.chapter_translation_id),
    'llm'
  ) <> 'human'
"""


async def handle_chapter_message(
    msg: dict,
    pool,
    publish_event,
    llm_client: LLMClient,
    retry_count: int = 0,
) -> None:
    """
    Heavy worker: processes exactly one chapter via session-based chunked translation.
    - Splits chapter into chunks (≤ 1/4 of model context window)
    - Maintains rolling conversation history across chunks for style consistency
    - Compacts history with the configured compact model when it grows too large
    - Updates DB atomically after all chunks complete
    - Checks if job is complete after each chapter

    Phase 4c-β: llm_client threaded from worker.py — replaces the
    legacy mint_user_jwt + httpx-direct call to /v1/model-registry/invoke.
    """
    job_id     = UUID(msg["job_id"])
    chapter_id = UUID(msg["chapter_id"])
    user_id    = msg["user_id"]

    # S4a: bind the owning campaign (or clear it) for THIS task before any LLM
    # call, so every provider job submitted while processing this chapter carries
    # campaign_id in its job_meta. Unconditional set (None for non-campaign work)
    # prevents a sequential reuse from inheriting a prior chapter's campaign.
    set_campaign_id(msg.get("campaign_id"))

    try:
        await _process_chapter(msg, job_id, chapter_id, user_id, pool, publish_event, llm_client)
    except _TransientError as exc:
        log.warning("chapter %s: transient error — %s", chapter_id, exc)
        await _fail_chapter_idempotent(pool, job_id, chapter_id, f"transient: {exc}")
        await _emit_chapter_failed_if_circuit_open(pool, msg, chapter_id, exc)
        await _emit_chapter_done(publish_event, user_id, msg, "failed", f"transient: {exc}")
        await _check_job_completion(pool, job_id, user_id, msg, publish_event)
        record_stage("translation.chapter", pipeline=msg.get("pipeline_version", "v2"),
                     status="failed", chapter_id=str(chapter_id), reason=str(exc)[:80])
        raise
    except Exception as exc:
        log.exception("chapter %s: unhandled error — %s", chapter_id, exc)
        await _fail_chapter_idempotent(pool, job_id, chapter_id, f"permanent: {exc}")
        await _emit_chapter_failed_if_circuit_open(pool, msg, chapter_id, exc)
        await _emit_chapter_done(publish_event, user_id, msg, "failed", f"permanent: {exc}")
        await _check_job_completion(pool, job_id, user_id, msg, publish_event)
        record_stage("translation.chapter", pipeline=msg.get("pipeline_version", "v2"),
                     status="failed", chapter_id=str(chapter_id), reason=str(exc)[:80])
        raise


async def _process_chapter(msg, job_id, chapter_id, user_id, pool, publish_event, llm_client: LLMClient) -> None:
    log.info("chapter %s [job %s]: starting", chapter_id, job_id)

    # Check for cancellation before doing any work
    async with pool.acquire() as db:
        job_status = await db.fetchval(
            "SELECT status FROM translation_jobs WHERE job_id=$1", job_id
        )
    log.info("chapter %s: job_status=%s", chapter_id, job_status)
    if job_status == "cancelled":
        log.info("chapter %s: job cancelled — skipping", chapter_id)
        await _fail_chapter_idempotent(pool, job_id, chapter_id, "job_cancelled")
        await _emit_chapter_done(publish_event, user_id, msg, "failed", "job_cancelled")
        await _check_job_completion(pool, job_id, user_id, msg, publish_event)
        return

    # Mark chapter running and get its id for chunk rows
    async with pool.acquire() as db:
        ct_row = await db.fetchrow(
            """UPDATE chapter_translations
               SET status='running', started_at=now()
               WHERE job_id=$1 AND chapter_id=$2
               RETURNING id""",
            job_id, chapter_id,
        )
    chapter_translation_id = ct_row["id"] if ct_row else None
    log.info("chapter %s: marked running, chapter_translation_id=%s", chapter_id, chapter_translation_id)

    # Fetch chapter body from book-service
    log.info("chapter %s: fetching body from book-service (book %s)", chapter_id, msg["book_id"])
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=5.0)) as client:
            r = await client.get(
                f"{settings.book_service_internal_url}"
                f"/internal/books/{msg['book_id']}/chapters/{chapter_id}",
                headers={"X-Internal-Token": settings.internal_service_token},
            )
    except httpx.RequestError as exc:
        log.error("chapter %s: book-service request failed: %s", chapter_id, exc)
        raise _TransientError(f"book-service unreachable: {exc}") from exc

    log.info("chapter %s: book-service responded status=%d", chapter_id, r.status_code)
    if r.status_code == 404:
        raise _PermanentError("chapter_not_found")
    if r.status_code >= 500:
        raise _TransientError(f"book-service {r.status_code}")
    r.raise_for_status()

    chapter      = r.json()
    source_lang  = chapter.get("original_language") or "unknown"
    chapter_text = chapter.get("text_content") or ""
    chapter_body = chapter.get("body")  # Tiptap JSONB (dict with "content" key) or None
    # M4d-1: the book-service chapter sort_order is the GLOBAL reading position —
    # the same axis knowledge-service keys event_order on. The V3 timeline memo
    # MUST use this, not the job-local `chapter_index` (= enumerate(chapter_ids)),
    # or a job that doesn't start at chapter 0 would window the wrong events.
    if chapter.get("sort_order") is not None:
        msg["chapter_sort_order"] = chapter["sort_order"]
    log.info(
        "chapter %s: fetched %d chars, source_lang=%s, has_json_body=%s",
        chapter_id, len(chapter_text), source_lang, bool(chapter_body and isinstance(chapter_body, dict)),
    )

    # Fetch model context window from provider-registry (best-effort)
    context_window = await _get_model_context_window(msg)
    log.info("chapter %s: context_window=%d", chapter_id, context_window)

    # V2: Load previous chapter memo for cross-chapter context
    chapter_index = msg.get("chapter_index", 0)
    target_language = msg.get("target_language", "")
    prev_memo = await _load_chapter_memo(pool, msg["book_id"], chapter_index - 1, target_language)
    if prev_memo:
        log.info("chapter %s: loaded memo from chapter %d", chapter_id, chapter_index - 1)
        # M4c: hand the prev-chapter memo to the V3 orchestrator for opportunistic
        # injection into the Translator (§12.1). V2 ignores it → byte-parity.
        msg["prev_memo"] = prev_memo

    # M0: select pipeline implementation by snapshotted flag. Default 'v2'. The v3
    # orchestrator currently delegates to v2 (parity) — M1+ adds the multi-agent loop.
    pipeline_version = msg.get("pipeline_version", "v2")
    if pipeline_version == "v3":
        from .v3.orchestrator import (
            translate_chapter_blocks_v3 as _translate_blocks,
            translate_chapter_v3 as _translate_text,
        )
    else:
        from .session_translator import translate_chapter_blocks as _translate_blocks
        _translate_text = translate_chapter

    # Detect JSON body → use block pipeline, otherwise fall back to text pipeline
    use_block_pipeline = (
        isinstance(chapter_body, dict)
        and isinstance(chapter_body.get("content"), list)
        and len(chapter_body["content"]) > 0
    )

    if use_block_pipeline:
        blocks = chapter_body["content"]
        log.info(
            "chapter %s: using BLOCK pipeline (%d blocks, model=%s/%s)",
            chapter_id, len(blocks), msg.get("model_source"), msg.get("model_ref"),
        )
        block_filter = msg.get("block_index_filter")
        if block_filter:
            # T2-M2 dirty-only re-translate: translate ONLY the dirty block positions
            # synchronously (v2 block path), then overlay onto the seed version's body.
            # Decouple/v3 are skipped for this job kind to bound the blast radius — the
            # whole point is a small, targeted patch, not the full multi-agent loop.
            log.info(
                "chapter %s: PARTIAL re-translate — %d dirty block(s), seed=%s",
                chapter_id, len(block_filter), msg.get("seed_version_id"),
            )
            (translated_blocks, input_tokens, output_tokens, translated_count,
             translatable_count, translated_texts) = await _partial_retranslate_blocks(
                pool=pool, llm_client=llm_client,
                chapter_translation_id=chapter_translation_id, chapter_id=chapter_id,
                blocks=blocks, block_filter=block_filter,
                seed_version_id=msg.get("seed_version_id"),
                source_lang=source_lang, msg=msg, context_window=context_window,
                translate_blocks_fn=_translate_blocks,
            )
        else:
            # LLM re-arch Phase 2b-T3a: event-driven decouple of the v2 BLOCK translate
            # stage. Submit batch 0 + RELEASE; the llm_terminal_consumer drives every
            # subsequent batch/retry off the terminal events and finalizes. (V3
            # verify/correct decouple = 2b-T3b — v3 stays synchronous under this flag.)
            if settings.translation_decouple_enabled and pipeline_version == "v2":
                from .decoupled_block_translate import start_chapter_blocks as _decoupled_start_blocks
                log.info("chapter %s: using DECOUPLED BLOCK pipeline (decouple flag on)", chapter_id)
                submitted = await _decoupled_start_blocks(
                    pool=pool, llm_client=llm_client,
                    chapter_translation_id=chapter_translation_id,
                    blocks=blocks, source_lang=source_lang, msg=msg,
                    context_window=context_window, chapter_text=chapter_text,
                )
                if submitted:
                    return  # released — the consumer finalizes on the terminal events
                # No translatable batches → fall through to the synchronous path, which
                # finalizes the original blocks as the empty-plan case does.
            elif (
                settings.translation_decouple_enabled
                and pipeline_version == "v3"
                # 2b-T3b — full V3 decouple: block translate → (mode-chain) verify/correct loop
                # → defer-finalize. A two_pass cold-start (D-V3-DECOUPLE-COLDSTART-2PASS) is now
                # decoupled too — decoupled_v3_block_start glossary-gates it internally (no
                # glossary → pass-1 → namepair → pass-2 → verify; else normal v3_verify).
            ):
                from .v3.orchestrator import decoupled_v3_block_start
                log.info("chapter %s: using DECOUPLED V3 pipeline (decouple flag on)", chapter_id)
                submitted = await decoupled_v3_block_start(
                    pool=pool, llm_client=llm_client,
                    chapter_translation_id=chapter_translation_id,
                    blocks=blocks, source_lang=source_lang, msg=msg,
                    context_window=context_window, chapter_text=chapter_text,
                )
                if submitted:
                    return  # released — the consumer chains block→v3_verify→finalize
                # No translatable batches → fall through to the synchronous v3 path.
            (translated_blocks, input_tokens, output_tokens, translated_count,
             translatable_count, translated_texts) = (
                await _translate_blocks(
                    blocks=blocks,
                    source_lang=source_lang,
                    msg=msg,
                    pool=pool,
                    chapter_translation_id=chapter_translation_id,
                    llm_client=llm_client,
                    context_window=context_window,
                )
            )
        # Total-failure guard: if the chapter HAD translatable blocks but none
        # were translated, the LLM step failed for every batch (e.g. the gateway
        # rejected the operation). The block pipeline falls each failed block
        # back to its ORIGINAL text, so `translated_blocks` looks complete —
        # persisting it as "completed" is a silent false-success (matrix shows
        # 完了 for an untranslated chapter). Raise so handle_chapter_message marks
        # the chapter FAILED. (TR-4 live acceptance, 2026-05-31.)
        if translatable_count > 0 and translated_count == 0:
            raise _PermanentError(
                f"translation produced no output: 0/{translatable_count} blocks "
                f"translated (LLM step failed for every batch — see worker log)"
            )
        # Store as JSONB
        translated_body_json = json.dumps(translated_blocks)
        translated_body_text = None  # not used for block translations
        translated_body_format = "json"
        # TD1 fix + M4c (D-TRANSL-MEMO-M4): build the cross-chapter memo from the
        # TRANSLATED-ONLY text. `translated_texts` ({idx: text}) excludes blocks
        # that fell back to original on failure, so a failed block's source text
        # no longer pollutes the memo.
        if block_filter:
            # T2-M2 (review-impl LOW-4): a partial re-translate only freshly translates
            # the dirty blocks, so translated_texts covers a few blocks. The cross-chapter
            # memo must reflect the WHOLE chapter (seed-copied + dirty), or the next
            # chapter's context shrinks to just the edited region. Derive it from the
            # full merged body.
            memo_text = "\n".join(
                t for t in (_block_plain_text(b) for b in translated_blocks) if t
            )
        else:
            memo_text = "\n".join(
                translated_texts[i] for i in sorted(translated_texts) if translated_texts[i]
            )
        log.info(
            "chapter %s: block pipeline done — %d blocks, %d/%d translated, in=%s out=%s",
            chapter_id, len(translated_blocks), translated_count, translatable_count,
            input_tokens, output_tokens,
        )
    elif settings.translation_decouple_enabled and pipeline_version == "v2":
        # LLM re-arch Phase 2b-T2: event-driven decouple of the v2 TEXT path.
        # Submit the first chunk + RELEASE this worker coroutine; the
        # llm_terminal_consumer resumes on each `loreweave:events:llm_job_terminal`
        # and finalizes via _finalize_chapter. So a worker isn't pinned for the
        # whole chapter. (Block + V3 decouple is 2b-T3 — still synchronous here.)
        log.info("chapter %s: using DECOUPLED TEXT pipeline (decouple flag on)", chapter_id)
        from .decoupled_translate import start_chapter as _decoupled_start
        await _decoupled_start(
            pool=pool, llm_client=llm_client,
            chapter_translation_id=chapter_translation_id,
            chapter_text=chapter_text, source_lang=source_lang,
            msg=msg, context_window=context_window,
        )
        return  # released — the consumer finalizes when the terminal event arrives
    else:
        log.info(
            "chapter %s: using TEXT pipeline (model=%s/%s)",
            chapter_id, msg.get("model_source"), msg.get("model_ref"),
        )
        translated_body_text, input_tokens, output_tokens = await _translate_text(
            chapter_text=chapter_text,
            source_lang=source_lang,
            msg=msg,
            pool=pool,
            chapter_translation_id=chapter_translation_id,
            llm_client=llm_client,
            context_window=context_window,
        )
        translated_body_json = None
        translated_body_format = "text"
        memo_text = translated_body_text or ""
        log.info(
            "chapter %s: text pipeline done — %d output chars, in=%s out=%s",
            chapter_id, len(translated_body_text or ""), input_tokens, output_tokens,
        )

    await _finalize_chapter(
        pool=pool, publish_event=publish_event, msg=msg,
        job_id=job_id, chapter_id=chapter_id, user_id=user_id,
        chapter_translation_id=chapter_translation_id,
        pipeline_version=pipeline_version, chapter_index=chapter_index,
        target_language=target_language, source_lang=source_lang,
        chapter_text=chapter_text,
        translated_body_text=translated_body_text,
        translated_body_json=translated_body_json,
        translated_body_format=translated_body_format,
        memo_text=memo_text, input_tokens=input_tokens, output_tokens=output_tokens,
    )


async def _finalize_chapter(
    *, pool, publish_event, msg, job_id, chapter_id, user_id,
    chapter_translation_id, pipeline_version, chapter_index, target_language,
    source_lang, chapter_text,
    translated_body_text, translated_body_json, translated_body_format,
    memo_text, input_tokens, output_tokens,
) -> None:
    """Persist + emit the completed-chapter result. Shared by the synchronous
    pipelines (block + text) and the 2b-T2 decoupled consumer's finalize hook.

    Idempotent for at-least-once delivery: the terminal-event relay may deliver a
    chapter's final event twice. The transactional UPDATE is guarded on
    ``status <> 'completed'``; a duplicate sees ``UPDATE 0`` → skips the counter
    increment, the active-version insert, the outbox event AND the post-commit
    emits. (The synchronous path re-marks status='running' upstream before re-entry,
    so the guard is a no-op there — neutral.)"""
    # Persist final result — all writes in one transaction for outbox atomicity
    log.info("chapter %s: persisting completed result to DB", chapter_id)
    async with pool.acquire() as db:
        async with db.transaction():
            res = await db.execute(
                """UPDATE chapter_translations SET
                     status='completed',
                     translated_body=$1,
                     translated_body_json=$2::jsonb,
                     translated_body_format=$3,
                     source_language=$4,
                     input_tokens=$5,
                     output_tokens=$6,
                     finished_at=now()
                   WHERE job_id=$7 AND chapter_id=$8 AND status <> 'completed'""",
                translated_body_text, translated_body_json, translated_body_format,
                source_lang,
                input_tokens or None, output_tokens or None,
                job_id, chapter_id,
            )
            # asyncpg command tag → "UPDATE 0" means the row was already 'completed'
            # (a duplicate terminal-event delivery). Skip the non-idempotent steps.
            # isinstance guard: only a real command-tag str triggers the skip — a
            # non-str (test mock) defaults to "proceed" (the synchronous behaviour).
            already_done = isinstance(res, str) and res.endswith(" 0")
            if already_done:
                log.info("chapter %s: already finalized (duplicate delivery) — skipping", chapter_id)
            else:
                log.info("chapter %s: chapter_translations updated, incrementing job counter", chapter_id)
                await db.execute(
                    "UPDATE translation_jobs SET completed_chapters=completed_chapters+1 WHERE job_id=$1",
                    job_id,
                )
                # Auto-set active (publish-on-completion) — see `_PROMOTE_ACTIVE_SQL`
                # (module top) for the statement, the M5b unresolved-high gate, and the
                # human-edit guard. Promotes a clean re-translation over an existing active
                # version for both campaign and interactive jobs; never clobbers a human edit.
                await db.execute(
                    _PROMOTE_ACTIVE_SQL, chapter_id, chapter_translation_id,
                )
                # Emit outbox event for statistics-service
                await _insert_outbox_event(db, "chapter.translated", chapter_id, {
                    "user_id": str(msg["user_id"]),
                    "book_id": str(msg["book_id"]),
                    "chapter_id": str(chapter_id),
                    "target_language": msg["target_language"],
                    "status": "completed",
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                })
    # Per-chapter telemetry (quality / memo / metric) fires ONCE — skipped on a
    # duplicate delivery to avoid double-emitting. All best-effort.
    if not already_done:
        log.info("chapter %s: DB persist complete", chapter_id)

        # M7a: emit the V3 quality rollup → learning-service (feedback flywheel).
        # POST-commit + best-effort (review-impl MED): a feedback-log failure must
        # never roll back a successful translation. Outbox-atomicity is traded for
        # safety — losing one telemetry event is fine; losing the translation is not.
        try:
            await _emit_translation_quality(
                pool, chapter_translation_id, msg, pipeline_version,
                # M7d-3: feed the judge its inputs (attached only when the feed flag
                # is on). `memo_text` is the translated-only text for BOTH pipelines;
                # for a block chapter `chapter_text` may be empty → the emit skips it.
                source_text=chapter_text, translated_text=memo_text,
            )
        except Exception:  # noqa: BLE001 — telemetry must not break the worker
            log.warning("M7a: failed to emit translation quality (non-fatal)", exc_info=True)

        # V2: Save chapter memo for next chapter's context (TD1: now also populated
        # for the block pipeline via memo_text derived above).
        await _save_chapter_memo(
            pool, msg["book_id"], chapter_index, target_language, memo_text,
        )

        # T2-M2: record per-segment translation status. A full-chapter translation
        # just covered EVERY segment at its current source hash → ensure segments
        # exist, then upsert one segment_translations row each. Best-effort +
        # post-commit (mirrors the memo/quality emits) — status bookkeeping must
        # never roll back or fail a successful translation.
        await _record_segment_status(
            pool, msg["book_id"], chapter_id, target_language, chapter_translation_id,
        )

        record_stage(
            "translation.chapter", pipeline=pipeline_version, status="completed",
            chapter_id=str(chapter_id), in_tokens=input_tokens or 0, out_tokens=output_tokens or 0,
        )

    # Job-level finalization runs ALWAYS — even on a duplicate (review-impl finding 1).
    # If the FIRST delivery committed the status transaction but crashed BEFORE these,
    # the redelivery's idempotency guard (already_done) would otherwise skip them and
    # the JOB would stay 'running' forever (no recovery for a non-campaign job).
    # `_check_job_completion` re-counts (idempotent); `_emit_chapter_done` is a
    # harmless SSE re-emit. Both are cheap and safe to repeat.
    await _emit_chapter_done(publish_event, user_id, msg, "completed", None)
    log.info("chapter %s: chapter_done event emitted", chapter_id)
    await _check_job_completion(pool, job_id, user_id, msg, publish_event)


async def _record_segment_status(
    pool, book_id, chapter_id, target_language: str, chapter_translation_id,
) -> None:
    """T2-M2: ensure the chapter's source segments exist, then mark them all as
    translated at their current source hash for `target_language`. Best-effort —
    swallows everything (a status-bookkeeping failure must not break the worker).
    `target_language` may be empty for a legacy text job with no segment concept;
    skip then (nothing to key the rows on)."""
    if not target_language:
        return
    try:
        from .segment_store import ensure_chapter_segments
        from .segment_status import record_segment_translations
        # Record against the segments AS THEY ALREADY EXIST (built at backfill / the
        # rebuild endpoint) — no book-service fetch on the hot path. Rebuilding here
        # would also be wrong: a source edit landing mid-translation would be captured
        # at finalize and falsely recorded as "translated". Only when a chapter has no
        # segments yet (never backfilled) do we build them once, then record.
        async with pool.acquire() as db:
            n = await record_segment_translations(
                db, chapter_id, target_language, chapter_translation_id,
            )
        if n == 0:
            await ensure_chapter_segments(pool, book_id, chapter_id)
            async with pool.acquire() as db:
                await record_segment_translations(
                    db, chapter_id, target_language, chapter_translation_id,
                )
    except Exception:  # noqa: BLE001 — segment status is best-effort telemetry
        log.warning("T2-M2: failed to record segment status (non-fatal)", exc_info=True)

    # T2-M3.2: refresh per-segment glossary usage (independent best-effort — a
    # glossary-fetch failure must not undo the status record above).
    await _record_segment_glossary_usage(pool, book_id, chapter_id, target_language)


async def _record_segment_glossary_usage(pool, book_id, chapter_id, target_language: str) -> None:
    """T2-M3.2: record which glossary entities each segment's SOURCE references, so a
    later change to an entity can flag only the segments that use it. Best-effort,
    post-commit.

    Usage is language-INDEPENDENT (source terms in source text). The translation-glossary
    endpoint returns the same entity SET for any target_language (it LEFT-JOINs the target
    translation, so an entity with no translation in this language is still returned) — the
    only language input is which we pass. We request the server max (200) so staleness
    covers more than the translate-time top-50, mirroring the entity cap the endpoint
    itself enforces."""
    try:
        from .glossary_client import fetch_translation_glossary
        from .segment_status import scan_glossary_usage, record_segment_glossary_usage
        raw = await fetch_translation_glossary(str(book_id), target_language, str(chapter_id), max_entries=200)
        entity_terms = [
            (str(r["entity_id"]), [t for t in (r.get("zh") or []) if t])
            for r in raw
            if r.get("entity_id") and [t for t in (r.get("zh") or []) if t]
        ]
        if not entity_terms:
            return
        async with pool.acquire() as db:
            seg_rows = await db.fetch(
                "SELECT segment_index, segment_text FROM chapter_segments WHERE chapter_id=$1",
                chapter_id,
            )
            segments = [(r["segment_index"], r["segment_text"]) for r in seg_rows]
            usage = scan_glossary_usage(segments, entity_terms)
            async with db.transaction():
                await record_segment_glossary_usage(db, chapter_id, usage)
    except Exception:  # noqa: BLE001 — best-effort glossary-usage telemetry
        log.warning("T2-M3.2: failed to record segment glossary usage (non-fatal)", exc_info=True)


def _block_plain_text(node) -> str:
    """Plain-text projection of a Tiptap block (mirrors versions._block_text) — used to
    build the full-chapter memo from a partial re-translate's merged body."""
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text") or ""
    if node.get("type") == "hardBreak":
        return "\n"
    return "".join(_block_plain_text(c) for c in (node.get("content") or []))


def _json_blocks(v) -> list:
    """Parse a translated_body_json column (asyncpg may hand it back as str or list)."""
    if v is None:
        return []
    if isinstance(v, str):
        try:
            return json.loads(v) or []
        except (ValueError, TypeError):
            return []
    return v if isinstance(v, list) else []


async def _load_seed_blocks(pool, seed_version_id, chapter_id) -> list:
    """T2-M2: the prior llm version's translated Tiptap blocks — the body whose
    NON-dirty blocks are copied verbatim into a partial re-translate. Returns [] if
    the seed is missing or wasn't a block (json) translation.

    review-impl HIGH: the seed is loaded SCOPED TO THIS chapter (``AND chapter_id``).
    block_index_filter/seed_version_id are public CreateJobPayload fields, so a job
    could carry a seed_version_id for ANOTHER chapter/book; without the scope the
    worker would copy a foreign version's translated blocks into this chapter (a
    cross-chapter read into the caller's own book). The chapter is in the caller's
    EDIT-gated book, so same-chapter scoping ties the seed to that authorization."""
    if not seed_version_id:
        return []
    sid = seed_version_id if isinstance(seed_version_id, UUID) else UUID(str(seed_version_id))
    cid = chapter_id if isinstance(chapter_id, UUID) else UUID(str(chapter_id))
    async with pool.acquire() as db:
        row = await db.fetchrow(
            "SELECT translated_body_json FROM chapter_translations WHERE id=$1 AND chapter_id=$2",
            sid, cid,
        )
    return _json_blocks(row["translated_body_json"]) if row else []


async def _partial_retranslate_blocks(
    *, pool, llm_client, chapter_translation_id, chapter_id, blocks, block_filter,
    seed_version_id, source_lang, msg, context_window, translate_blocks_fn,
):
    """T2-M2 dirty-only re-translate: translate ONLY the `block_filter` positions of
    `blocks` and overlay the results onto the seed version's body, copying every
    other block verbatim. Returns the same 6-tuple shape as translate_chapter_blocks
    so the caller's finalize path is unchanged.

    `translate_blocks_fn` is the pipeline-selected block translator (review-impl MED):
    the caller passes the SAME v2/v3 function `_process_chapter` chose, so a v3 job's
    dirty re-translate runs the Translator→Verifier→Corrector loop on the dirty blocks
    (and its unresolved-high gate still governs auto-promote) instead of silently
    falling back to a bare v2 translate.

    Safety: the seed must align 1:1 with the CURRENT source blocks (same count) — a
    structural edit (blocks added/removed) invalidates positional overlay, so we fall
    back to a full re-translate (correct, just not cost-optimal)."""
    _translate_blocks = translate_blocks_fn

    seed_blocks = await _load_seed_blocks(pool, seed_version_id, chapter_id)
    if not seed_blocks or len(seed_blocks) != len(blocks):
        log.warning(
            "chapter %s: partial re-translate seed misaligned/foreign (seed=%d src=%d) → full re-translate",
            chapter_id, len(seed_blocks), len(blocks),
        )
        return await _translate_blocks(
            blocks=blocks, source_lang=source_lang, msg=msg, pool=pool,
            chapter_translation_id=chapter_translation_id, llm_client=llm_client,
            context_window=context_window,
        )

    # Valid, de-duplicated dirty positions in ascending order.
    idx_set = sorted({i for i in block_filter if 0 <= i < len(blocks)})
    if not idx_set:
        # Nothing actually dirty (or all out of range) → seed is already current; no LLM spend.
        return (list(seed_blocks), 0, 0, 0, 0, {})

    dirty_blocks = [blocks[i] for i in idx_set]
    (t_blocks, in_tok, out_tok, t_count, t_able, t_texts) = await _translate_blocks(
        blocks=dirty_blocks, source_lang=source_lang, msg=msg, pool=pool,
        chapter_translation_id=chapter_translation_id, llm_client=llm_client,
        context_window=context_window,
    )

    # Overlay: copy the seed body, replace each dirty position with its freshly
    # translated block. translate_chapter_blocks returns result_blocks aligned 1:1
    # with its INPUT list and translated_texts keyed by that same local position.
    merged = list(seed_blocks)
    remapped_texts: dict[int, str] = {}
    for local_i, src_i in enumerate(idx_set):
        if local_i < len(t_blocks):
            merged[src_i] = t_blocks[local_i]
        if local_i in t_texts:
            remapped_texts[src_i] = t_texts[local_i]
    return (merged, in_tok, out_tok, t_count, t_able, remapped_texts)


async def _get_model_context_window(msg: dict) -> int:
    """
    Query provider-registry-service for the model's context window.
    Returns _FALLBACK_CONTEXT_WINDOW if the endpoint is unavailable or the
    model doesn't publish a context length (common for local Ollama/LM Studio models).
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{settings.provider_registry_service_url}"
                f"/v1/model-registry/models/{msg['model_ref']}/context-window",
                params={"model_source": msg["model_source"]},
            )
            if r.status_code == 200:
                cw = int(r.json().get("context_window") or _FALLBACK_CONTEXT_WINDOW)
                log.debug("context_window for model %s: %d", msg["model_ref"], cw)
                return cw
            log.debug(
                "context_window endpoint returned %d for model %s — using fallback",
                r.status_code, msg["model_ref"],
            )
    except Exception as exc:
        log.debug("context_window fetch failed (%s) — using fallback %d", exc, _FALLBACK_CONTEXT_WINDOW)
    return _FALLBACK_CONTEXT_WINDOW


async def _check_job_completion(pool, job_id, user_id, msg, publish_event) -> None:
    """
    After each chapter terminal state, atomically check + finalize the job.
    Uses a single UPDATE ... WHERE ... RETURNING to avoid TOCTOU race.
    Only the worker that wins the UPDATE emits the final event.
    """
    async with pool.acquire() as db:
        row = await db.fetchrow(
            """UPDATE translation_jobs SET
                 status = CASE
                   WHEN failed_chapters = 0                  THEN 'completed'
                   WHEN completed_chapters > 0               THEN 'partial'
                   ELSE 'failed'
                 END,
                 finished_at = now()
               WHERE job_id = $1
                 AND status = 'running'
                 AND (completed_chapters + failed_chapters) = total_chapters
               RETURNING status, completed_chapters, failed_chapters""",
            job_id,
        )

    if row is None:
        return  # Job not done yet, or another worker already finalized it

    await publish_event(user_id, {
        "event":    "job.status_changed",
        "job_id":   msg["job_id"],
        "job_type": "translation",
        "payload":  {
            "status":             row["status"],
            "completed_chapters": row["completed_chapters"],
            "failed_chapters":    row["failed_chapters"],
        },
    })

    # Fire-and-forget notification
    await _send_translation_notification(
        user_id, msg.get("job_id", ""), msg.get("book_title", ""),
        row["status"], row["completed_chapters"], row["failed_chapters"],
    )


async def _fail_chapter_idempotent(pool, job_id, chapter_id, reason: str) -> None:
    """
    Mark chapter as failed and increment failed_chapters.
    Guarded by AND status != 'failed' so double-calls don't double-count.
    """
    async with pool.acquire() as db:
        updated = await db.fetchval(
            """UPDATE chapter_translations
               SET status='failed', error_message=$1, finished_at=now()
               WHERE job_id=$2 AND chapter_id=$3 AND status != 'failed'
               RETURNING chapter_id""",
            reason, job_id, chapter_id,
        )
        if updated is not None:
            await db.execute(
                "UPDATE translation_jobs SET failed_chapters=failed_chapters+1 WHERE job_id=$1",
                job_id,
            )


async def _emit_chapter_done(publish_event, user_id, msg, status, error_message) -> None:
    await publish_event(user_id, {
        "event":    "job.chapter_done",
        "job_id":   msg["job_id"],
        "job_type": "translation",
        "payload":  {
            "chapter_id":     msg["chapter_id"],
            "chapter_index":  msg["chapter_index"],
            "total_chapters": msg["total_chapters"],
            "status":         status,
            "error_message":  error_message,
        },
    })


async def _insert_outbox_event(
    db, event_type: str, aggregate_id, payload: dict, aggregate_type: str = "chapter",
) -> None:
    """Insert a transactional outbox event for worker-infra relay to Redis Streams.

    ``aggregate_type`` keys the destination stream (``loreweave:events:<type>``).
    Defaults to 'chapter' (statistics pipeline); M7a uses 'translation' so the
    quality-log event lands on ``loreweave:events:translation`` for learning."""
    await db.execute(
        """INSERT INTO outbox_events (event_type, aggregate_type, aggregate_id, payload)
           VALUES ($1, $2, $3, $4::jsonb)""",
        event_type, aggregate_type, aggregate_id, json.dumps(payload),
    )


async def _emit_chapter_failed_if_circuit_open(pool, msg, chapter_id, exc) -> None:
    """S3c-2b: when a chapter fails because the provider's S3a circuit is OPEN,
    emit `chapter.translation_failed` (error_code=LLM_CIRCUIT_OPEN) so
    campaign-service auto-pauses the campaign. Best-effort + circuit-open-only:
    the campaign pauses solely on that code, and a lost emit just means the
    campaign keeps churning until the breaker self-heals + a retry succeeds. The
    code is carried structurally on `_TransientError.code` (set at the provider
    raise sites in session_translator), so this never depends on the message
    format."""
    if getattr(exc, "code", None) != "LLM_CIRCUIT_OPEN":
        return
    try:
        async with pool.acquire() as db:
            await _insert_outbox_event(db, "chapter.translation_failed", chapter_id, {
                "user_id": str(msg["user_id"]),
                "book_id": str(msg["book_id"]),
                "chapter_id": str(chapter_id),
                "target_language": msg.get("target_language"),
                "error_code": "LLM_CIRCUIT_OPEN",
            })
    except Exception:  # noqa: BLE001 — telemetry/control signal, never fail the worker
        log.warning("S3c-2b: failed to emit chapter.translation_failed (non-fatal)", exc_info=True)


async def _emit_translation_quality(
    conn, chapter_translation_id, msg: dict, pipeline_version: str,
    *, source_text: str = "", translated_text: str = "",
) -> None:
    """M7a (Channel 2 — LLM action log): emit ``translation.quality`` to
    learning-service so the verifier's per-chapter rollup becomes a tunable
    ``source=auto`` signal. Carries the score + per-issue-type counts.

    Skips when there is no V3 quality signal (``quality_score`` NULL — e.g. the V2
    path), so empty rows are never logged. ``aggregate_type='translation'`` routes
    it to ``loreweave:events:translation``. Best-effort + post-commit (called by
    the worker AFTER the persist txn) so a feedback-log failure never rolls back a
    successful translation — ``conn`` may be the pool or a connection.

    review-impl HIGH: the verifier's ``quality_score()`` is an **int in [0, 100]**
    (``quality.py``), but the platform's score_config convention (F1/precision/…)
    is **[0, 1]**; emit the **normalised** ``/100`` value so learning's
    ``translation_quality_score`` ([0,1]) validates it instead of DLQ-ing every
    event.

    M7d-3: when ``translation_judge_feed_enabled`` is on, also carry a truncated
    ``source_text`` + ``translated_text`` so the M7d-2 online fidelity judge has
    inputs. Off by default — the payload is then byte-identical to M7a."""
    row = await conn.fetchrow(
        """SELECT quality_score, unresolved_high_count, qa_rounds_used
           FROM chapter_translations WHERE id = $1""",
        chapter_translation_id,
    )
    if row is None or row["quality_score"] is None:
        return  # V2 / no quality signal → nothing to log
    issue_rows = await conn.fetch(
        """SELECT issue_type, COUNT(*) AS n
           FROM translation_quality_issues
           WHERE chapter_translation_id = $1
           GROUP BY issue_type""",
        chapter_translation_id,
    )
    issue_counts = {r["issue_type"]: r["n"] for r in issue_rows}
    payload = {
        "user_id": str(msg["user_id"]),
        "book_id": str(msg["book_id"]),
        "chapter_id": str(msg["chapter_id"]),
        "chapter_translation_id": str(chapter_translation_id),
        "target_language": msg["target_language"],
        "pipeline_version": pipeline_version,
        "quality_score": float(row["quality_score"]) / 100.0,  # 0-100 int → [0,1]
        "unresolved_high_count": row["unresolved_high_count"] or 0,
        "qa_rounds_used": row["qa_rounds_used"] or 0,
        "issue_counts": issue_counts,
    }
    # M7d-3: opt-in fidelity feed. OFF by default → payload stays byte-identical to
    # M7a (no text shipped). When on, attach a head-sample of BOTH sides under the
    # exact keys the M7d-2 learning hook reads. Require both non-empty so a block
    # chapter with empty text_content simply doesn't feed (keys absent → the
    # consumer judge hook stays inert, no crash).
    #
    # review-impl MED (cross-service-normalization-bug-class): a *character* is not
    # a language-invariant unit — 2000 zh chars cover far more story than 2000 vi
    # chars. Truncating each side independently to the same char count would feed
    # the judge MISALIGNED spans (e.g. 60% of the source vs 25% of the translation)
    # → it reads the translation as "omits the back half" and scores fidelity
    # systematically low for exactly the CJK→Latin pairs this channel tunes. So
    # sample both by the SAME fraction of their own length, with the fraction picked
    # so neither side exceeds the cap. Both samples then cover the same story span
    # AND stay bounded. cap<=0 → skip the feed (don't emit empty strings).
    # S5b-eval: a campaign-chosen eval-judge model rides the event so learning's
    # M7d-2 judge uses it. The campaign pick IS the opt-in — when present, force the
    # text feed for THIS chapter regardless of the service-wide feed flag (otherwise
    # the judge has no inputs). Non-campaign traffic still honours the flag.
    eval_judge_ref = msg.get("eval_judge_model_ref")
    if eval_judge_ref:
        payload["eval_judge_model_source"] = msg.get("eval_judge_model_source")
        payload["eval_judge_model_ref"] = eval_judge_ref
    cap = settings.translation_judge_feed_max_chars
    feed_texts = settings.translation_judge_feed_enabled or bool(eval_judge_ref)
    if feed_texts and source_text and translated_text and cap > 0:
        frac = min(1.0, cap / len(source_text), cap / len(translated_text))
        payload["source_text"] = source_text[: max(1, int(len(source_text) * frac))]
        payload["translated_text"] = translated_text[: max(1, int(len(translated_text) * frac))]
    await _insert_outbox_event(
        conn, "translation.quality", chapter_translation_id, payload,
        aggregate_type="translation",
    )


async def _send_translation_notification(
    user_id, job_id: str, book_title: str, status: str,
    completed_chapters: int, failed_chapters: int,
) -> None:
    """Fire-and-forget notification to notification-service."""
    try:
        category = "translation"
        # `title` is the English fallback; clients localize from i18n_key + params
        # (LW-PLAN notifications i18n Phase 2).
        if status == "completed":
            title = f"Translation complete — {completed_chapters} chapters of \"{book_title}\""
            i18n_key = "notif.translation.completed"
            i18n_params = {"count": completed_chapters, "book": book_title}
        elif status == "partial":
            title = f"Translation partial — {completed_chapters} done, {failed_chapters} failed"
            i18n_key = "notif.translation.partial"
            i18n_params = {"done": completed_chapters, "failed": failed_chapters}
        else:
            title = f"Translation failed — \"{book_title}\""
            i18n_key = "notif.translation.failed"
            i18n_params = {"book": book_title}

        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{settings.notification_service_internal_url}/internal/notifications",
                json={
                    "user_id": str(user_id),
                    "category": category,
                    "title": title,
                    "metadata": {
                        "job_id": str(job_id),
                        "status": status,
                        "type": f"translation_{status}",
                        "i18n_key": i18n_key,
                        "i18n_params": i18n_params,
                    },
                },
                headers={"X-Internal-Token": settings.internal_service_token},
            )
    except Exception as exc:
        log.warning("Failed to send translation notification: %s", exc)


async def _load_chapter_memo(pool, book_id, chapter_index: int, target_language: str) -> dict | None:
    """Load the translation memo from the previous chapter (if any)."""
    if chapter_index < 0:
        return None
    try:
        async with pool.acquire() as db:
            row = await db.fetchrow(
                """SELECT terms_used, story_summary, style_notes
                   FROM translation_chapter_memos
                   WHERE book_id = $1 AND chapter_index = $2 AND target_language = $3""",
                UUID(str(book_id)), chapter_index, target_language,
            )
            if row:
                return {
                    "terms_used": json.loads(row["terms_used"]) if isinstance(row["terms_used"], str) else row["terms_used"],
                    "story_summary": row["story_summary"],
                    "style_notes": row["style_notes"],
                }
    except Exception as exc:
        log.warning("chapter_memo load failed: %s — continuing without memo", exc)
    return None


async def _save_chapter_memo(
    pool, book_id, chapter_index: int, target_language: str, translated_text: str,
) -> None:
    """Save a brief translation memo for the next chapter's context.

    M4c: also persists ``terms_used`` — recurring target-side proper nouns
    harvested from this chapter (the cold-start in-run name record), so the next
    chapter can reuse the exact spelling for cross-chapter name consistency.
    """
    if not translated_text:
        return
    # Extract last ~5 sentences as story summary
    sentences = [s.strip() for s in translated_text.replace("\n", ". ").split(".") if s.strip()]
    story_summary = ". ".join(sentences[-5:]) + "." if sentences else ""
    # Cap at 500 chars
    if len(story_summary) > 500:
        story_summary = story_summary[-500:]

    from .v3.chapter_memo import harvest_names
    terms_used = harvest_names(translated_text, target_language)

    try:
        async with pool.acquire() as db:
            await db.execute(
                """INSERT INTO translation_chapter_memos
                     (book_id, chapter_index, target_language, story_summary, terms_used)
                   VALUES ($1, $2, $3, $4, $5)
                   ON CONFLICT (book_id, chapter_index, target_language)
                   DO UPDATE SET story_summary = EXCLUDED.story_summary,
                                 terms_used = EXCLUDED.terms_used, created_at = now()""",
                UUID(str(book_id)), chapter_index, target_language, story_summary,
                json.dumps(terms_used, ensure_ascii=False),
            )
    except Exception as exc:
        log.warning("chapter_memo save failed: %s — non-fatal", exc)


class _TransientError(Exception):
    """Network blip, service unavailable — safe to retry.

    `code` (S3c-2b) carries the structured upstream error code (e.g.
    LLM_CIRCUIT_OPEN) when the failure originated from a provider job, so the
    circuit-open auto-pause signal doesn't depend on parsing the message string.
    None for non-provider transients (book-service down, etc.)."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class _PermanentError(Exception):
    """Bad data, 404, 402, unrecoverable — retry won't help."""
