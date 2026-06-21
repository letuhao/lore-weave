"""
GEP-BE-09: Extraction worker.

Processes one chapter at a time — fetches chapter text from book-service,
builds prompts from extraction profile, calls LLM, parses output,
posts entities to glossary-service.

Design reference: GLOSSARY_EXTRACTION_PIPELINE.md §6.6, §7
"""
from __future__ import annotations

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
from .block_batcher import build_batch_plan
from .chunk_splitter import estimate_tokens
from .extraction_preprocessor import prepare_chapter_text
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

# Context-aware chapter windowing (D-EXTRACTION-CONTEXT-WINDOW). A chapter can be
# larger than the model's context window; we split it into sub-chapter windows that
# fit, extract from each, then accumulate the entities (dedup across windows). This
# reuses the translation pipeline's block batcher (novel-fitted: it packs whole Tiptap
# paragraph blocks up to a token budget — never splitting a paragraph/sentence), so a
# 1MB chapter just becomes N windows. Output budget per window is sized to leave room
# in the context (input + output + safety ≤ context) so the gateway never 400s on
# LLM_CONTEXT_OVERFLOW.
_FALLBACK_CONTEXT_WINDOW = 8192
_EXTRACTION_OUTPUT_CEILING = 8000  # per-window output cap (entities JSON is small)
_EXTRACTION_OUTPUT_FLOOR = 1024
_CONTEXT_SAFETY_RATIO = 0.15  # mirror the gateway's context-fit safety margin


async def _get_model_context_window(model_source: str | None, model_ref: str | None) -> int:
    """Model context window (tokens) via provider-registry — the same endpoint the
    translation chapter worker uses. Falls back when unknown (local models often don't
    publish a context length)."""
    if not model_ref:
        return _FALLBACK_CONTEXT_WINDOW
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{settings.provider_registry_service_url}"
                f"/v1/model-registry/models/{model_ref}/context-window",
                params={"model_source": model_source or "user_model"},
            )
            if r.status_code == 200:
                return int(r.json().get("context_window") or _FALLBACK_CONTEXT_WINDOW)
    except Exception as exc:  # noqa: BLE001 — fall back on any failure
        log.debug("extraction: context_window fetch failed (%s) — fallback %d", exc, _FALLBACK_CONTEXT_WINDOW)
    return _FALLBACK_CONTEXT_WINDOW


def _plan_chapter_windows(chapter: dict, chapter_text: str, context_window: int, source_language: str) -> list[str]:
    """Split a chapter into sub-chapter windows that fit the model context, reusing the
    translation block batcher. Each window is clean prose (block-joined, no [BLOCK N]
    markers — those are translation-alignment artifacts the extractor doesn't need).

    Falls back to a single window (the whole text) when the chapter has no Tiptap block
    array (legacy text_content) or the batcher yields nothing."""
    body = chapter.get("body")
    blocks = body.get("content") if isinstance(body, dict) else None
    if not isinstance(blocks, list) or not blocks:
        return [chapter_text]
    # source_lang == target_lang: extraction doesn't translate, but reusing the
    # expansion-ratio budget is safe (it only RESERVES more output room → smaller, safer
    # windows). build_batch_plan packs whole paragraph blocks up to the input budget.
    plan = build_batch_plan(
        blocks, context_window_tokens=context_window,
        source_lang=source_language, target_lang=source_language,
    )
    windows: list[str] = []
    for bg in plan.batches:
        prose = "\n\n".join(e.text for e in bg.entries if e.text.strip())
        if prose.strip():
            windows.append(prose)
    return windows or [chapter_text]


def _merge_window_entities(entities: list[dict]) -> list[dict]:
    """Accumulate entities found across sub-chapter windows: merge by (kind, normalized
    name), unioning each entity's chapter_links by chapter_id. The glossary bulk-upsert
    also dedups by name, but merging here keeps the chapter_links clean + the posted set
    small. First occurrence wins for the entity's attributes (order-stable)."""
    merged: dict[tuple[str, str], dict] = {}
    for ent in entities:
        name = str(ent.get("name", "")).strip()
        if not name:
            continue
        key = (str(ent.get("kind", "")), name.lower())
        if key not in merged:
            merged[key] = ent
            continue
        existing = merged[key]
        seen = {l.get("chapter_id") for l in existing.get("chapter_links", [])}
        for link in ent.get("chapter_links", []):
            if link.get("chapter_id") not in seen:
                existing.setdefault("chapter_links", []).append(link)
                seen.add(link.get("chapter_id"))
    return list(merged.values())


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

    # Context-aware windowing (D-EXTRACTION-CONTEXT-WINDOW): split a chapter that exceeds
    # the model context into sub-chapter windows (whole paragraph blocks) that fit, then
    # accumulate the entities. Reuses the translation block batcher (novel-fitted).
    context_window = await _get_model_context_window(model_source, model_ref)
    windows = _plan_chapter_windows(chapter, chapter_text, context_window, source_language)

    # 2. Plan kind-batches (output-schema grouping — same set for every window).
    batches = plan_kind_batches(extraction_profile, kinds_metadata)
    log.info("extraction: chapter %s (index %d) — %d window(s) × %d batch(es), ctx=%d, text_len=%d",
             chapter_id, chapter_index, len(windows), len(batches), context_window, len(chapter_text))

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

    # Per-call output budget sized so input + output + safety ≤ context (so the gateway
    # never 400s on LLM_CONTEXT_OVERFLOW), capped — extraction output (entities JSON) is
    # small, so a modest ceiling avoids reserving context the input needs.
    safety = int(context_window * _CONTEXT_SAFETY_RATIO)
    max_win_tok = max((estimate_tokens(w) for w in windows), default=0)
    out_budget = context_window - max_win_tok - safety - estimate_tokens(known_ctx) - 600
    out_budget = max(_EXTRACTION_OUTPUT_FLOOR, min(_EXTRACTION_OUTPUT_CEILING, out_budget))

    # Flatten window × kind-batch so the existing per-call body is unchanged; window_text
    # replaces the whole-chapter text in the user prompt.
    for window_idx, window_text, batch_idx, batch in (
        (wi, w, bi, b) for wi, w in enumerate(windows) for bi, b in enumerate(batches)
    ):
        # 4. Build prompt
        schema = build_extraction_prompt(batch, extraction_profile, kinds_metadata)
        system_prompt = build_system_prompt(
            dynamic_schema=schema,
            source_language=source_language,
            known_entities_context=known_ctx,
            max_entities_per_kind=max_entities_per_kind,
        )
        user_prompt = build_user_prompt(window_text)

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
                    "max_tokens": out_budget,
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

        log.info("extraction: chapter %s batch %d/%d — in=%d out=%d response=%d chars",
                 chapter_id, batch_idx + 1, len(batches), input_tokens, output_tokens,
                 len(response_text))

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

    # Accumulate across windows: the same entity can surface in multiple sub-chapter
    # windows — merge by (kind, normalized name), unioning chapter_links.
    all_entities = _merge_window_entities(all_entities)

    if not all_entities:
        log.info("extraction: chapter %s done in %.1fs — 0 entities (empty LLM output)", chapter_id, _ch_elapsed)
        return {"created": 0, "updated": 0, "skipped": 0, "entities": [], "input_tokens": total_input_tokens, "output_tokens": total_output_tokens}

    # 7. Post to glossary-service
    upsert_result = await post_extracted_entities(
        book_id=book_id,
        source_language=source_language,
        attribute_actions=extraction_profile,
        entities=all_entities,
    )

    if upsert_result is None:
        raise RuntimeError("glossary-service upsert failed")

    log.info("extraction: chapter %s done in %.1fs — created=%d updated=%d skipped=%d (in=%d out=%d)",
             chapter_id, _ch_elapsed,
             upsert_result.get("created", 0), upsert_result.get("updated", 0), upsert_result.get("skipped", 0),
             total_input_tokens, total_output_tokens)

    upsert_result["input_tokens"] = total_input_tokens
    upsert_result["output_tokens"] = total_output_tokens
    return upsert_result
