"""
GEP-BE-09: Extraction worker.

Processes one chapter at a time — fetches chapter text from book-service,
builds prompts from extraction profile, calls LLM, parses output,
posts entities to glossary-service.

Design reference: GLOSSARY_EXTRACTION_PIPELINE.md §6.6, §7
"""
from __future__ import annotations

import hashlib
import json
import logging
from uuid import UUID

import httpx

from loreweave_jobs import emit_job_event_safe
from loreweave_llm.errors import (
    LLMAuthFailed,
    LLMDecodeError,
    LLMError,
    LLMInvalidRequest,
    LLMModelNotFound,
    LLMQuotaExceeded,
    LLMStreamNotSupported,
    LLMTransientRetryNeededError,
)

from ..config import settings
from ..llm_client import LLMClient
from .extraction_preprocessor import prepare_chapter_text
from .extraction_provenance import stamp_entity_provenance
from .extraction_prompt import (
    build_extraction_prompt,
    build_known_entities_context,
    build_system_prompt,
    build_user_prompt,
    parse_and_validate,
    plan_kind_batches,
)
from .glossary_client import (
    fetch_known_entities,
    post_extracted_entities,
)
from .llm_thinking import thinking_llm_fields

log = logging.getLogger(__name__)

# Unified Job Control Plane (D-JOBS-GLOSSARY-EXTRACT-UNWIRED): glossary extraction surfaces
# in the unified Jobs screen as service="translation", kind="glossary_extraction". The worker
# emits the lifecycle transitions best-effort post-commit (emit_job_event_safe — a failed
# emit must never fail the job; the reconcile UNION in internal_dispatch.py backstops).
_JOB_SERVICE = "translation"
_JOB_KIND = "glossary_extraction"


async def handle_extraction_job(msg: dict, pool, publish, publish_event, llm_client: LLMClient) -> None:
    """Coordinator: receives extraction job, marks running, processes chapters sequentially.

    Unlike translation jobs which fan out chapters in parallel,
    extraction processes chapters sequentially to accumulate known entities.

    Phase 4c-γ: llm_client threaded from worker.py — replaces the
    legacy /internal/invoke httpx call.
    """
    job_id = UUID(msg["job_id"])
    user_id = msg["user_id"]
    try:
        await _run_extraction_job(msg, job_id, user_id, pool, publish, publish_event, llm_client)
    except Exception as exc:
        log.exception("extraction_worker: job %s failed unexpectedly: %s", job_id, exc)
        async with pool.acquire() as db:
            await db.execute(
                "UPDATE extraction_jobs SET status='failed', error_message=$2, finished_at=now() WHERE job_id=$1",
                job_id, str(exc)[:500],
            )
        await emit_job_event_safe(
            pool, service=_JOB_SERVICE, job_id=str(job_id), owner_user_id=str(user_id),
            kind=_JOB_KIND, status="failed", error={"code": "extraction_failed", "message": str(exc)[:500]},
        )
        await publish_event(user_id, {
            "event": "job.status_changed",
            "job_id": str(job_id),
            "job_type": "extract_glossary",
            "payload": {"status": "failed", "error": str(exc)[:200]},
        })


async def _run_extraction_job(msg: dict, job_id: UUID, user_id: str, pool, publish, publish_event, llm_client: LLMClient) -> None:
    """Inner extraction job runner — separated for top-level error handling."""
    book_id = msg["book_id"]
    chapter_ids = msg["chapter_ids"]
    extraction_profile = msg.get("extraction_profile", {})
    kinds_metadata = msg.get("kinds_metadata", [])
    context_filters = msg.get("context_filters", {})
    source_language = msg.get("source_language", "zh")
    model_source = msg.get("model_source", "platform_model")
    model_ref = msg.get("model_ref")
    max_entities_per_kind = msg.get("max_entities_per_kind", 30)
    thinking_enabled = bool(msg.get("thinking_enabled", False))

    log.info("extraction_worker: job %s — %d chapters", job_id, len(chapter_ids))

    # Cancel-safe claim: only start a job that is NOT already cancelled/terminal.
    # The cancel endpoint sets status='cancelling'; an unconditional "SET status='running'"
    # here CLOBBERED that on every redelivery, so the per-chapter cancel check below never
    # saw it and the job ran forever despite being cancelled (the runaway we hit). If the
    # guarded UPDATE matches nothing, the job was cancelled/terminal → settle it and RETURN
    # so `message.process()` ACKs and drops the message — this is what finally stops the
    # redelivery loop for a cancelled job.
    async with pool.acquire() as db:
        claimed = await db.fetchval(
            "UPDATE extraction_jobs SET status='running', started_at=now() "
            "WHERE job_id=$1 AND status NOT IN "
            "('cancelled','cancelling','completed','completed_with_errors','failed') "
            "RETURNING job_id",
            job_id,
        )
    if claimed is None:
        async with pool.acquire() as db:
            settled = await db.fetchval(
                "UPDATE extraction_jobs SET status='cancelled', finished_at=now() "
                "WHERE job_id=$1 AND status='cancelling' RETURNING job_id",
                job_id,
            )
        log.info("extraction_worker: job %s not runnable (cancelled/terminal) — acking, no work", job_id)
        # Emit 'cancelled' ONLY if we actually flipped a cancelling row — an already-terminal
        # job (completed/failed) matched nothing and must not be re-marked cancelled.
        if settled is not None:
            await emit_job_event_safe(
                pool, service=_JOB_SERVICE, job_id=str(job_id), owner_user_id=str(user_id),
                kind=_JOB_KIND, status="cancelled",
            )
        await publish_event(user_id, {
            "event": "job.status_changed",
            "job_id": str(job_id),
            "job_type": "extract_glossary",
            "payload": {"status": "cancelled"},
        })
        return

    # P1 — claimed pending→running: emit the running transition (best-effort, post-claim).
    await emit_job_event_safe(
        pool, service=_JOB_SERVICE, job_id=str(job_id), owner_user_id=str(user_id),
        kind=_JOB_KIND, status="running",
    )

    # Resume from checkpoint: skip chapters already finished on a PRIOR delivery. The
    # extraction message can be redelivered (a connection drop during the long sequential
    # run, a worker restart, etc.). Without resume, the loop restarts at chapter 0, re-spends
    # LLM on done chapters, and — because completed/failed reset to 0 each delivery — never
    # reaches total_chapters, so the job never finalizes and the message redelivers forever
    # (the second half of the runaway). Resuming makes each delivery advance, so the job
    # converges to a terminal state and the message is finally ACKed.
    async with pool.acquire() as db:
        done_rows = await db.fetch(
            "SELECT chapter_id, status, COALESCE(input_tokens,0) AS it, "
            "COALESCE(output_tokens,0) AS ot FROM extraction_chapter_results "
            "WHERE job_id=$1 AND status IN ('completed','failed')",
            job_id,
        )
    done_ids = {str(r["chapter_id"]) for r in done_rows}

    await publish_event(user_id, {
        "event": "job.status_changed",
        "job_id": str(job_id),
        "job_type": "extract_glossary",
        "payload": {"status": "running", "completed_chapters": len(done_ids)},
    })

    # Fetch initial known entities (smart-filtered)
    known_entities = await fetch_known_entities(
        book_id,
        alive=context_filters.get("alive", True),
        min_frequency=context_filters.get("min_frequency", 2),
        recency_window=context_filters.get("recency_window", 100),
        limit=context_filters.get("limit", 50),
    )

    total_created = 0
    total_updated = 0
    total_skipped = 0
    # Seed token totals + completed/failed counts from the checkpoint so the columns
    # ACCUMULATE across redeliveries (the convergence-critical part — completed/failed
    # must reach total_chapters for the job to finalize). entity created/updated/skipped
    # stats reflect only the current delivery's NEW chapters (a minor display under-count
    # on a multi-pass resume); correctness of finalize + cost rides on the counts/tokens.
    total_input_tokens = sum(r["it"] for r in done_rows)
    total_output_tokens = sum(r["ot"] for r in done_rows)
    completed = sum(1 for r in done_rows if r["status"] == "completed")
    failed = sum(1 for r in done_rows if r["status"] == "failed")

    for idx, chapter_id_str in enumerate(chapter_ids):
        chapter_id = UUID(chapter_id_str) if isinstance(chapter_id_str, str) else chapter_id_str

        # Resume: a chapter finished on a prior delivery is skipped (its entities were
        # already posted to glossary-service; re-running would re-spend LLM for nothing).
        if str(chapter_id) in done_ids:
            continue

        # Cooperative cancellation check
        async with pool.acquire() as db:
            job_status = await db.fetchval(
                "SELECT status FROM extraction_jobs WHERE job_id=$1", job_id
            )
        if job_status in ("cancelled", "cancelling"):
            log.info("extraction_worker: job %s cancelled — stopping at chapter %d/%d", job_id, idx, len(chapter_ids))
            async with pool.acquire() as db:
                await db.execute(
                    "UPDATE extraction_jobs SET status='cancelled', finished_at=now() WHERE job_id=$1",
                    job_id,
                )
            await emit_job_event_safe(
                pool, service=_JOB_SERVICE, job_id=str(job_id), owner_user_id=str(user_id),
                kind=_JOB_KIND, status="cancelled",
            )
            await publish_event(user_id, {
                "event": "job.status_changed",
                "job_id": str(job_id),
                "job_type": "extract_glossary",
                "payload": {"status": "cancelled"},
            })
            return

        # Mark chapter as running
        async with pool.acquire() as db:
            await db.execute(
                "UPDATE extraction_chapter_results SET status='running', started_at=now() WHERE job_id=$1 AND chapter_id=$2",
                job_id, chapter_id,
            )

        try:
            result = await _process_extraction_chapter(
                job_id=job_id,
                book_id=book_id,
                chapter_id=chapter_id,
                chapter_index=idx,
                extraction_profile=extraction_profile,
                kinds_metadata=kinds_metadata,
                known_entities=known_entities,
                source_language=source_language,
                model_source=model_source,
                model_ref=model_ref,
                max_entities_per_kind=max_entities_per_kind,
                thinking_enabled=thinking_enabled,
                pool=pool,
                llm_client=llm_client,
            )
            # Update known entities with newly created entities (capped at 200 to prevent
            # unbounded prompt growth — design §7 says ~50 entities ≈ 250 tokens)
            _KNOWN_ENTITIES_CAP = 200
            for ent in result.get("entities", []):
                if ent.get("status") == "created" and len(known_entities) < _KNOWN_ENTITIES_CAP:
                    known_entities.append({
                        "name": ent["name"],
                        "kind_code": ent["kind_code"],
                        "aliases": [],
                        "frequency": 1,
                    })

            ch_created = result.get("created", 0)
            ch_updated = result.get("updated", 0)
            ch_skipped = result.get("skipped", 0)
            ch_input_tokens = result.get("input_tokens", 0)
            ch_output_tokens = result.get("output_tokens", 0)

            total_created += ch_created
            total_updated += ch_updated
            total_skipped += ch_skipped
            total_input_tokens += ch_input_tokens
            total_output_tokens += ch_output_tokens
            completed += 1

            async with pool.acquire() as db:
                await db.execute(
                    """UPDATE extraction_chapter_results
                       SET status='completed', entities_found=$3,
                           input_tokens=$4, output_tokens=$5, completed_at=now()
                       WHERE job_id=$1 AND chapter_id=$2""",
                    job_id, chapter_id, ch_created + ch_updated,
                    ch_input_tokens, ch_output_tokens,
                )

        except Exception as exc:
            log.exception("extraction_worker: chapter %s failed: %s", chapter_id, exc)
            failed += 1
            async with pool.acquire() as db:
                await db.execute(
                    """UPDATE extraction_chapter_results
                       SET status='failed', error_message=$3, completed_at=now()
                       WHERE job_id=$1 AND chapter_id=$2""",
                    job_id, chapter_id, str(exc)[:500],
                )

        # Update job progress
        async with pool.acquire() as db:
            await db.execute(
                """UPDATE extraction_jobs
                   SET completed_chapters=$2, failed_chapters=$3,
                       entities_created=$4, entities_updated=$5, entities_skipped=$6,
                       total_input_tokens=$7, total_output_tokens=$8
                   WHERE job_id=$1""",
                job_id, completed, failed,
                total_created, total_updated, total_skipped,
                total_input_tokens, total_output_tokens,
            )

        await publish_event(user_id, {
            "event": "job.progress",
            "job_id": str(job_id),
            "job_type": "extract_glossary",
            "payload": {
                "completed_chapters": completed,
                "failed_chapters": failed,
                "total_chapters": len(chapter_ids),
                "entities_created": total_created,
                "entities_updated": total_updated,
                "entities_skipped": total_skipped,
            },
        })

    # Job complete
    final_status = "completed" if failed == 0 else ("failed" if completed == 0 else "completed_with_errors")
    async with pool.acquire() as db:
        await db.execute(
            "UPDATE extraction_jobs SET status=$2, finished_at=now() WHERE job_id=$1",
            job_id, final_status,
        )

    # P1 terminal emit (best-effort). 'completed_with_errors' has no canonical JobStatus →
    # map to 'completed' (the job DID finish; per-chapter failures are tracked on the row).
    _canon = "completed" if final_status in ("completed", "completed_with_errors") else "failed"
    await emit_job_event_safe(
        pool, service=_JOB_SERVICE, job_id=str(job_id), owner_user_id=str(user_id),
        kind=_JOB_KIND, status=_canon,
        tokens_in=total_input_tokens or None, tokens_out=total_output_tokens or None,
    )

    await publish_event(user_id, {
        "event": "job.status_changed",
        "job_id": str(job_id),
        "job_type": "extract_glossary",
        "payload": {
            "status": final_status,
            "entities_created": total_created,
            "entities_updated": total_updated,
            "entities_skipped": total_skipped,
        },
    })

    log.info(
        "extraction_worker: job %s complete — created=%d updated=%d skipped=%d failed_chapters=%d",
        job_id, total_created, total_updated, total_skipped, failed,
    )


async def _process_extraction_chapter(
    job_id: UUID,
    book_id: str,
    chapter_id: UUID,
    chapter_index: int,
    extraction_profile: dict,
    kinds_metadata: list,
    known_entities: list,
    source_language: str,
    model_source: str,
    model_ref: str | None,
    max_entities_per_kind: int,
    thinking_enabled: bool,
    pool,
    llm_client: LLMClient,
) -> dict:
    """Extract entities from a single chapter via LLM."""
    import time as _time
    _ch_start = _time.monotonic()

    # 1. Fetch chapter from book-service
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=30, write=30, pool=5)) as client:
        r = await client.get(
            f"{settings.book_service_internal_url}"
            f"/internal/books/{book_id}/chapters/{chapter_id}",
            headers={"X-Internal-Token": settings.internal_service_token},
        )
    if r.status_code != 200:
        raise RuntimeError(f"book-service returned {r.status_code} for chapter {chapter_id}")

    chapter = r.json()
    chapter_text = prepare_chapter_text(chapter)
    if not chapter_text.strip():
        log.warning("extraction: chapter %s has no text content — skipping", chapter_id)
        return {"created": 0, "updated": 0, "skipped": 0, "entities": [], "input_tokens": 0, "output_tokens": 0}

    # 2. Plan batches
    batches = plan_kind_batches(extraction_profile, kinds_metadata)
    log.info("extraction: chapter %s (index %d) — %d batch(es), text_len=%d",
             chapter_id, chapter_index, len(batches), len(chapter_text))

    # M1 (extraction pipeline FND) — content hash of the prepared text (the
    # source-drift precondition + the M6 cache-key dimension) and the whole-chapter
    # writeback idempotency key = hash(book, chapter, content_hash, kinds, profile).
    # The glossary writeback dedupes on this key so a retry/redelivery/concurrent
    # fresh run lands the chapter exactly once (INV-C3).
    content_hash = hashlib.sha256(chapter_text.encode("utf-8")).hexdigest()
    profile_hash = hashlib.sha256(
        json.dumps(extraction_profile, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    all_kinds = sorted({k for batch in batches for k in batch})
    writeback_key = hashlib.sha256(
        "|".join([book_id, str(chapter_id), content_hash, ",".join(all_kinds), profile_hash]).encode("utf-8")
    ).hexdigest()

    # 3. Build known entities context
    known_ctx = build_known_entities_context(known_entities) if known_entities else ""

    # Resolve owner user_id once for internal invoke auth
    async with pool.acquire() as db:
        owner_user_id = await db.fetchval(
            "SELECT owner_user_id FROM extraction_jobs WHERE job_id=$1", job_id
        )

    all_entities: list[dict] = []
    total_input_tokens = 0
    total_output_tokens = 0
    # M0 (extraction pipeline FND) — capture the LLM `finish_reason` per batch.
    # `length` = output-token truncation (the 26-scenario data-loss bug): the
    # model was cut mid-array, so the parser only salvages a partial result.
    # Surfacing it here is the prerequisite for the M2 BatchOutcome taxonomy +
    # the M6 raw-cache (`extraction_raw_outputs.finish_reason`); today the
    # worker never read it (architecture §8.3). Consumed via `.get()` downstream
    # so it is additive/non-breaking on the chapter-result dict.
    batch_finish_reasons: list[dict] = []

    for batch_idx, batch in enumerate(batches):
        # 4. Build prompt
        schema = build_extraction_prompt(batch, extraction_profile, kinds_metadata)
        system_prompt = build_system_prompt(
            dynamic_schema=schema,
            source_language=source_language,
            known_entities_context=known_ctx,
            max_entities_per_kind=max_entities_per_kind,
        )
        user_prompt = build_user_prompt(chapter_text)

        # 5. LLM call via SDK (replaces /internal/invoke).
        # Phase 4c-γ: HIGH#1 lesson from cycle 11 applied — catch
        # permanent SDK subclasses BEFORE generic LLMError so a
        # misconfigured BYOK doesn't poison the whole batch loop.
        try:
            sdk_job = await llm_client.submit_and_wait(
                user_id=str(owner_user_id),
                # /review-impl MED#1 — operation="chat" routes to the
                # SAME chatAggregator as "translation" but accurately
                # labels glossary entity extraction in gateway telemetry/
                # billing dashboards. "translation" would mislabel.
                operation="chat",
                model_source=model_source,
                model_ref=str(model_ref),
                input={
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                    # Output ceiling. A batch is capped at MAX_KINDS_PER_BATCH kinds
                    # (extraction_prompt) so its output stays well under this; the
                    # headroom is generous on purpose (typical model context is tens
                    # of thousands of tokens and the extraction input is only ~4–5k),
                    # so an entity-dense chapter completes instead of truncating at
                    # finish_reason=length. If a batch still truncates, the parser
                    # repairs the partial array rather than dropping every entity.
                    "max_tokens": 20000,
                    **thinking_llm_fields(enabled=thinking_enabled),
                },
                chunking=None,
                job_meta={
                    "extractor": "glossary",
                    "extraction_job_id": str(job_id),
                    "chapter_id": str(chapter_id),
                    "batch_idx": batch_idx,
                },
                transient_retry_budget=1,
            )
        except (LLMQuotaExceeded, LLMModelNotFound, LLMAuthFailed,
                LLMInvalidRequest, LLMDecodeError, LLMStreamNotSupported) as exc:
            log.error(
                "extraction: permanent SDK error %s for chapter %s batch %d/%d — failing batch",
                exc.__class__.__name__, chapter_id, batch_idx + 1, len(batches),
            )
            continue
        except (LLMTransientRetryNeededError, LLMError) as exc:
            log.error(
                "extraction: transient SDK error for chapter %s batch %d/%d: %s",
                chapter_id, batch_idx + 1, len(batches), exc,
            )
            continue

        if sdk_job.status != "completed":
            err_code = sdk_job.error.code if sdk_job.error else "unknown"
            log.error(
                "extraction: LLM job ended status=%s code=%s for chapter %s batch %d/%d — skipping batch (kinds: %s)",
                sdk_job.status, err_code, chapter_id, batch_idx + 1, len(batches), batch,
            )
            continue

        # chatAggregator output: {"messages": [{"role":"assistant","content":...}], "usage": {...}}
        result = sdk_job.result or {}
        messages_out = result.get("messages") or []
        response_text = ""
        if isinstance(messages_out, list) and messages_out:
            first = messages_out[0]
            if isinstance(first, dict):
                response_text = first.get("content", "") or ""
        usage = result.get("usage") or {}
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        total_input_tokens += input_tokens
        total_output_tokens += output_tokens

        # M0 — first-class truncation signal. `finish_reason="length"` means the
        # provider stopped because it hit max_tokens, so `response_text` is a
        # truncated JSON array (the parser salvages the complete-objects prefix
        # but later entities are LOST). Record it per batch for the outcome
        # taxonomy / re-plan-smaller signal (M2) and warn loudly so truncation is
        # no longer invisible in the logs.
        finish_reason = sdk_job.finish_reason
        truncated = finish_reason == "length"
        batch_finish_reasons.append({
            "batch_idx": batch_idx,
            "kinds": list(batch),
            "finish_reason": finish_reason,
            "truncated": truncated,
            "output_tokens": output_tokens,
        })

        log.info("extraction: chapter %s batch %d/%d — in=%d out=%d response=%d chars finish=%s",
                 chapter_id, batch_idx + 1, len(batches), input_tokens, output_tokens,
                 len(response_text), finish_reason or "?")
        if truncated:
            log.warning(
                "extraction: chapter %s batch %d/%d TRUNCATED (finish_reason=length, "
                "out=%d tokens, kinds=%s) — partial salvage only; downstream entities dropped",
                chapter_id, batch_idx + 1, len(batches), output_tokens, batch,
            )

        # 6. Parse + validate
        entities = parse_and_validate(response_text, batch, extraction_profile)

        # Add chapter_links to each entity (use .get() to avoid mutating parsed dict)
        chapter_title = chapter.get("title", "")
        for ent in entities:
            relevance = ent.get("relevance", "appears")
            ent["chapter_links"] = [{
                "chapter_id": str(chapter_id),
                "chapter_title": chapter_title,
                "chapter_index": chapter_index,
                "relevance": relevance,
            }]

        all_entities.extend(entities)

    _ch_elapsed = _time.monotonic() - _ch_start

    if not all_entities:
        log.info("extraction: chapter %s done in %.1fs — 0 entities (empty LLM output)", chapter_id, _ch_elapsed)
        return {"created": 0, "updated": 0, "skipped": 0, "entities": [],
                "input_tokens": total_input_tokens, "output_tokens": total_output_tokens,
                "batch_finish_reasons": batch_finish_reasons}

    # 6b. M1 — content-hash precondition (INV-C4). The LLM calls above took real
    # wall-clock; if the chapter was EDITED meanwhile, these entities were extracted
    # from stale text and must NOT land (a fresh extraction against the new text
    # supersedes them). Re-fetch + re-hash; on drift, skip the writeback. Best-effort:
    # a re-fetch failure does not abort (the writeback_key still guards double-apply).
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=30, write=30, pool=5)) as client:
            rr = await client.get(
                f"{settings.book_service_internal_url}"
                f"/internal/books/{book_id}/chapters/{chapter_id}",
                headers={"X-Internal-Token": settings.internal_service_token},
            )
        if rr.status_code == 200:
            current_hash = hashlib.sha256(prepare_chapter_text(rr.json()).encode("utf-8")).hexdigest()
            if current_hash != content_hash:
                log.warning(
                    "extraction: chapter %s source DRIFTED during extraction "
                    "(hash %s→%s) — skipping stale writeback (will re-extract)",
                    chapter_id, content_hash[:12], current_hash[:12],
                )
                return {"created": 0, "updated": 0, "skipped": 0, "entities": [],
                        "input_tokens": total_input_tokens, "output_tokens": total_output_tokens,
                        "batch_finish_reasons": batch_finish_reasons, "stale_skipped": True}
    except Exception as exc:  # noqa: BLE001 — precondition is best-effort
        log.warning("extraction: chapter %s drift re-check failed (%s) — proceeding", chapter_id, exc)

    # 6c. PROV/M3 — stamp VALIDATED evidence provenance (INV-7 / T1). The model
    # returned an EXACT QUOTE per entity; locate each one in the REAL prepared
    # chapter text and record chapter-relative char offsets + a block index + a
    # trust status. A model offset is a HINT verified before trust; a quote we
    # cannot find keeps its evidence but gets NO fabricated offset. Done once here
    # (the block map is built per-chapter) so glossary persists only validated
    # offsets — it never trusts a raw model number. The offsets index the same
    # prepared text whose `content_hash` guards the writeback, so they stay valid
    # exactly when the writeback lands (a drifted chapter is skipped above).
    stamp_entity_provenance(all_entities, chapter_text)

    # 7. Post to glossary-service (whole-chapter, idempotent, tenant-scoped writeback)
    upsert_result = await post_extracted_entities(
        book_id=book_id,
        source_language=source_language,
        attribute_actions=extraction_profile,
        entities=all_entities,
        chapter_id=str(chapter_id),
        content_hash=content_hash,
        writeback_key=writeback_key,
        owner_user_id=str(owner_user_id) if owner_user_id else None,
    )

    if upsert_result is None:
        raise RuntimeError("glossary-service upsert failed")

    log.info("extraction: chapter %s done in %.1fs — created=%d updated=%d skipped=%d (in=%d out=%d)",
             chapter_id, _ch_elapsed,
             upsert_result.get("created", 0), upsert_result.get("updated", 0), upsert_result.get("skipped", 0),
             total_input_tokens, total_output_tokens)

    upsert_result["input_tokens"] = total_input_tokens
    upsert_result["output_tokens"] = total_output_tokens
    upsert_result["batch_finish_reasons"] = batch_finish_reasons
    return upsert_result
