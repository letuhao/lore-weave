"""
GEP-BE-09: Extraction worker.

Processes one chapter at a time — fetches chapter text from book-service,
builds prompts from extraction profile, calls LLM, parses output,
posts entities to glossary-service.

Design reference: GLOSSARY_EXTRACTION_PIPELINE.md §6.6, §7
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from uuid import UUID

import httpx

from loreweave_jobs import emit_job_event_safe
from loreweave_llm.attribution import set_public_key_attribution
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
from loreweave_llm.reasoning import ReasoningDirective, reasoning_fields

from ..config import settings
from ..llm_client import LLMClient
from .block_batcher import build_batch_plan
from .cost import resolve_job_cost_usd
from .chunk_splitter import estimate_tokens
from .extraction_cache import (
    RawCacheKey,
    effort_band_for,
    get_cached_batch,
    put_batch,
)
from .extraction_outcomes import (
    EMPTY_VALID,
    LLM_ERROR,
    OK,
    UNPLANNABLE,
    chapter_status_from_outcomes,
    classify_batch,
    compute_event_id,
)
from .extraction_preprocessor import prepare_chapter_text
from .extraction_provenance import stamp_entity_provenance
from .mention_count import count_entity_mentions
from .extraction_prompt import (
    build_extraction_prompt,
    build_known_entities_context,
    build_system_prompt,
    build_user_prompt,
    parse_and_validate_with_stats,
    plan_kind_batches,
)
from .glossary_client import (
    fetch_known_entities,
    post_extracted_entities,
)
from loreweave_llm.reasoning import ReasoningDirective, reasoning_fields

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
# Shared with the route's cost estimate (D-CACHE-PLANNER-WIRING) so the quote + the real run
# resolve the SAME model context. `_get_model_context_window` keeps its internal name here.
from .extraction_model import FALLBACK_CONTEXT_WINDOW as _FALLBACK_CONTEXT_WINDOW  # noqa: E402,F401
from .extraction_model import get_model_context_window as _get_model_context_window  # noqa: E402

_EXTRACTION_OUTPUT_CEILING = 8000  # per-window output cap (entities JSON is small)
_EXTRACTION_OUTPUT_FLOOR = 1024
_CONTEXT_SAFETY_RATIO = 0.15  # mirror the gateway's context-fit safety margin

# Glossary-extraction quality (2026-06-29 ontology analysis, docs/analysis/2026-06-29-
# ontology-extraction-bloat.md): a `relationship` is a KG EDGE (A→B), NOT a discrete named
# entity. Extracting it as a glossary kind yields ~100% `A與B的關係` phrase-"entities"
# (POC reproduced on gemma AND qwen, 6/6 chapters; matches the 4,789 relationship rows /
# 88% phrases observed live). Such kinds are dropped from LLM EXTRACTION — the kind still
# exists in the book ontology for manual/authored use; it just isn't auto-extracted.
_NON_EXTRACTABLE_GLOSSARY_KINDS: frozenset[str] = frozenset({"relationship"})


def drop_non_extractable_kinds(
    extraction_profile: dict, kinds_metadata: list,
) -> tuple[dict, list, list[str]]:
    """Remove non-entity kinds (``_NON_EXTRACTABLE_GLOSSARY_KINDS``) from the extraction
    profile + kinds metadata so the LLM is never asked to extract them. Returns
    ``(filtered_profile, filtered_metadata, dropped_codes)``. A no-op (returns the inputs)
    when none are present, so existing books without such kinds are unaffected."""
    dropped = [k for k in extraction_profile if k in _NON_EXTRACTABLE_GLOSSARY_KINDS]
    if not dropped:
        return extraction_profile, kinds_metadata, []
    profile = {k: v for k, v in extraction_profile.items()
               if k not in _NON_EXTRACTABLE_GLOSSARY_KINDS}
    metadata = [m for m in kinds_metadata
                if m.get("code") not in _NON_EXTRACTABLE_GLOSSARY_KINDS]
    return profile, metadata, dropped

# D-EXTRACTION-BATCH-CONCURRENCY: hard ceiling on the per-chapter LLM-call fan-out
# regardless of the caller's requested concurrency (protects the provider/GPU + the
# glossary per-book advisory lock from a runaway request). 1 ⇒ sequential.
_EXTRACTION_MAX_CONCURRENCY = 16

# bug #3: how often (in chapters) to re-price the live job cost via the provider-registry
# oracle during the run. Tokens update every chapter regardless; cost re-prices on the first
# chapter + every Nth, reusing the last figure between, to bound registry calls + keep a
# degraded registry from injecting its 5s timeout into every chapter of the run.
_COST_REPRICE_EVERY = 5

# D-LLM-FAILURE-RATE #1 — structured-output enforcement. Default ON; set
# EXTRACTION_STRUCTURED_OUTPUT=0 to disable fleet-wide. The per-call
# LLMInvalidRequest fallback already degrades a single unsupported model safely,
# so the flag is only an emergency global off-switch.
_STRUCTURED_OUTPUT_ENABLED = os.getenv(
    "EXTRACTION_STRUCTURED_OUTPUT", "1"
).strip().lower() not in ("0", "false", "no", "off")


def _entity_response_format(kinds: list[str]) -> dict:
    """A LOOSE json_schema for the extraction output: a top-level array whose
    items require ``kind`` (restricted to THIS batch's kinds) + ``name``, with
    attributes left FREE (``additionalProperties``). It forces syntactically-valid
    JSON AND a valid kind — the two clean-finish failure modes behind the residual
    ``completed_with_errors`` (malformed array / wrong-kind rejection) — without
    constraining the per-kind profile fields the model fills in. Passed as
    ``response_format`` to the gateway, which forwards it to LM Studio/vLLM; a model
    that rejects the shape is retried once WITHOUT it (caller fallback)."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "extracted_entities",
            "schema": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": list(kinds)},
                        "name": {"type": "string"},
                    },
                    "required": ["kind", "name"],
                    "additionalProperties": True,
                },
            },
        },
    }


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


def _entity_alias_forms(ent: dict) -> list[str]:
    """Extract alias surface forms from a parsed entity dict for mention counting (M7).

    Aliases live under the whitelisted 'aliases' attribute (`ent['attributes']['aliases']`)
    when the kind defines it. The model may emit them as a list OR a delimiter-joined
    string; normalize both to a list of strings. Canonical-name counting is handled by the
    caller (count_entity_mentions takes name + aliases) — this returns aliases only.
    """
    attrs = ent.get("attributes") or {}
    raw = attrs.get("aliases")
    if raw is None:
        return []
    if isinstance(raw, str):
        # Split on the common CJK + ASCII separators a model uses in a flat string.
        parts: list[str] = [raw]
        for sep in ("、", "，", ",", "/", "|", "；", ";"):
            parts = [p for chunk in parts for p in chunk.split(sep)]
        return [p.strip() for p in parts if p.strip()]
    if isinstance(raw, list):
        return [str(a).strip() for a in raw if a is not None and str(a).strip()]
    return []


def _merge_window_entities(entities: list[dict]) -> list[dict]:
    """Accumulate entities found across sub-chapter windows: merge by (kind, normalized
    name), unioning each entity's chapter_links by chapter_id. The glossary bulk-upsert
    also dedups by name, but merging here keeps the chapter_links clean + the posted set
    small. First occurrence wins for the entity's attributes (order-stable).

    M7 — when the SAME entity surfaces in multiple windows of the SAME chapter, each
    window contributes a per-window mention_count; the chapter total is their SUM (the
    same entity mentioned 3× in window A and 2× in window B is 5× in the chapter). So a
    repeat chapter_id link no longer skips — it ADDS its mention_count into the kept link
    (everything else on the link is identical for one chapter, so first-seen wins)."""
    merged: dict[tuple[str, str], dict] = {}
    for ent in entities:
        name = str(ent.get("name", "")).strip()
        if not name:
            continue
        key = (str(ent.get("kind_code", "")), name.lower())
        if key not in merged:
            merged[key] = ent
            continue
        existing = merged[key]
        links_by_chapter: dict = {
            l.get("chapter_id"): l for l in existing.get("chapter_links", [])
        }
        for link in ent.get("chapter_links", []):
            cid = link.get("chapter_id")
            if cid not in links_by_chapter:
                existing.setdefault("chapter_links", []).append(link)
                links_by_chapter[cid] = link
            else:
                # Same (entity, chapter) seen in another window → SUM the per-window counts.
                kept = links_by_chapter[cid]
                kept["mention_count"] = kept.get("mention_count", 0) + link.get("mention_count", 0)
    return list(merged.values())


async def _persist_batch_outcomes(pool, job_id, owner_user_id, book_id, chapter_id,
                                  outcomes: list[dict]) -> None:
    """Persist the per-batch outcome SSOT rows (INV-O12: these rows ARE the observability
    truth; a reconciliation sweep re-derives job stats from them).

    Best-effort relative to the job: the batches already did their real work, so a failure
    to record observability must NEVER fail the chapter — log and move on. All rows for the
    chapter share ONE transaction; UNIQUE(event_id) makes a redelivered batch an idempotent
    no-op (INV-O13). The same-txn OUTBOX projection (events as a fan-out of these rows) is
    deliberately NOT emitted yet — there is no consumer, and routing it onto an existing
    stream would mis-deliver: tracked `D-OBS-BATCH-OUTCOME-PROJECTION` to wire with a
    dedicated stream + a bound consumer. detail/kinds carry counts + status only (REDACTED
    by construction — no raw_response, no secrets; INV-T6/§8.7).
    """
    if not outcomes:
        return
    try:
        async with pool.acquire() as db:
            async with db.transaction():
                for o in outcomes:
                    await db.execute(
                        """INSERT INTO extraction_batch_outcomes
                           (job_id, owner_user_id, book_id, chapter_id, batch_idx, status,
                            finish_reason, kinds, entities_found, entities_written,
                            validation_rejected_count, input_tokens, output_tokens,
                            error_code, event_id)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                           ON CONFLICT (event_id) DO NOTHING""",
                        job_id, owner_user_id, book_id, chapter_id,
                        o["batch_idx"], o["status"], o.get("finish_reason"),
                        o.get("kinds", []), o.get("entities_found", 0), 0,
                        o.get("validation_rejected_count", 0),
                        o.get("input_tokens", 0), o.get("output_tokens", 0),
                        o.get("error_code"), o["event_id"],
                    )
    except Exception as exc:  # noqa: BLE001 — observability must not fail the job
        log.warning("extraction: failed to persist batch outcomes for chapter %s: %s", chapter_id, exc)


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
    # Drop non-entity kinds (e.g. `relationship` → a KG edge) from LLM extraction so they
    # can't flood the glossary with `A與B的關係` phrase-rows. The kind row is untouched.
    extraction_profile, kinds_metadata, _dropped = drop_non_extractable_kinds(
        msg.get("extraction_profile", {}), msg.get("kinds_metadata", []))
    if _dropped:
        log.info("extraction: skipping non-entity kinds %s (relationships are KG edges) book=%s",
                 _dropped, book_id)
    context_filters = msg.get("context_filters", {})
    source_language = msg.get("source_language", "zh")
    model_source = msg.get("model_source", "platform_model")
    model_ref = msg.get("model_ref")
    max_entities_per_kind = msg.get("max_entities_per_kind", 30)
    thinking_enabled = bool(msg.get("thinking_enabled", False))
    # D-RE-WORKER-GRADED-EFFORT: the clamped graded effort (none|low|medium|high). Absent on a
    # message minted before this field (back-compat) → fall back to the thinking_enabled bool.
    reasoning_effort = msg.get("reasoning_effort") or ("medium" if thinking_enabled else "none")
    # D-EXTRACTION-BATCH-CONCURRENCY: per-chapter LLM-call fan-out cap. Absent/None on a
    # pre-field message ⇒ 1 (sequential, prior behavior). Clamped to a hard ceiling.
    concurrency = max(1, min(_EXTRACTION_MAX_CONCURRENCY, int(msg.get("concurrency") or 1)))

    # D-PMCP-WORKER-CARRIER: re-set the public-MCP-key attribution for THIS task so
    # every provider job submitted while extracting tags job_meta with the agent's
    # key (+ cap) — the confirm-route contextvar died at the AMQP hop. Unconditional
    # (None clears) so a pooled task never inherits a prior job's key.
    set_public_key_attribution(msg.get("mcp_key_id"), msg.get("spend_cap_usd"))

    log.info("extraction_worker: job %s — %d chapters (concurrency=%d)", job_id, len(chapter_ids), concurrency)

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
    # A chapter is "done" (skipped on resume) when it reached ANY terminal status —
    # 'completed', the new OBS 'completed_with_errors' (finished, but some batch failed),
    # or 'failed'. Omitting completed_with_errors here would re-run + re-spend LLM on a
    # chapter that already finished, and break convergence (it'd never count as done).
    async with pool.acquire() as db:
        done_rows = await db.fetch(
            "SELECT chapter_id, status, COALESCE(input_tokens,0) AS it, "
            "COALESCE(output_tokens,0) AS ot FROM extraction_chapter_results "
            "WHERE job_id=$1 AND status IN ('completed','completed_with_errors','failed')",
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
    # `completed` counts every FINISHED chapter (clean or with-errors) for convergence;
    # `chapters_with_errors` tracks the with-errors subset so the JOB rollup surfaces them
    # (else the chapter taxonomy would be recorded but the job would still read clean).
    completed = sum(1 for r in done_rows if r["status"] in ("completed", "completed_with_errors"))
    chapters_with_errors = sum(1 for r in done_rows if r["status"] == "completed_with_errors")
    failed = sum(1 for r in done_rows if r["status"] == "failed")
    # bug #37 — realized LLM-call count (one per executed window×batch = one BatchOutcome row,
    # the SAME unit the planner's estimated_llm_calls counts). Seed from the outcomes already
    # persisted on prior deliveries so the GUI counter is MONOTONIC across a resume (the loop
    # below only processes not-yet-done chapters, so it never double-counts). Best-effort.
    try:
        async with pool.acquire() as db:
            _seed_calls = await db.fetchval(
                "SELECT count(*) FROM extraction_batch_outcomes WHERE job_id=$1", job_id
            )
        # isinstance gate: a real count is an int; tolerate a mocked/odd value → 0.
        total_llm_calls = _seed_calls if isinstance(_seed_calls, int) else 0
    except Exception:  # noqa: BLE001 — a display counter must never fail the run
        total_llm_calls = 0

    # D-JOBS-EXTRACT-LIVE-PROGRESS (bug #2): mirror per-chapter progress onto the UNIFIED
    # jobs-service stream so the /jobs detail page advances live. The translation-service
    # `publish_event` channel only reaches the legacy translation UI; the unified Job detail
    # page (JobMonitor) subscribes to the jobs-service SSE overlay, which previously saw only
    # the single 'running' transition + the terminal event — so its progress bar/detail_status
    # sat frozen for the whole run. Each emit carries a fresh occurred_at, so the monotonic
    # projection applies it (forward-in-time) and pushes an SSE frame. Best-effort: a failed
    # emit never disturbs the run (the terminal rollup + reconcile sweep backstop accuracy).
    # bug #3: carry live tokens + a derived cost so the /jobs detail Cost & Usage panel
    # updates as the run advances instead of only at completion. TOKENS ride every emit (free
    # — already summed). COST needs the provider-registry pricing oracle (the gateway `usage`
    # has no cost; same call cost.py uses for actuals — D-JOBS-P4), which is NETWORK I/O on a
    # 5s timeout. Repricing every chapter would couple the run's latency to registry health (a
    # degraded registry → up to 5s added PER chapter). So we reprice only periodically and
    # REUSE the last good figure between: tokens stay fully live, cost advances in steps, and
    # registry calls are bounded to ~chapters/_COST_REPRICE_EVERY. Best-effort throughout: a
    # None reprice keeps the last cost; a fresh 0-token call skips the HTTP entirely.
    _last_cost: float | None = None

    async def _emit_unified_progress(reprice: bool = True) -> None:
        nonlocal _last_cost
        done = completed + failed
        if reprice:
            priced = await resolve_job_cost_usd(
                owner_user_id=str(user_id), model_source=model_source, model_ref=model_ref,
                input_tokens=total_input_tokens, output_tokens=total_output_tokens,
            )
            if priced is not None:
                _last_cost = priced
        await emit_job_event_safe(
            pool, service=_JOB_SERVICE, job_id=str(job_id), owner_user_id=str(user_id),
            kind=_JOB_KIND, status="running",
            progress={"done": done, "total": len(chapter_ids)},
            detail_status=f"{done}/{len(chapter_ids)} chapters",
            # bug #37 — advance the realized LLM-call count on the Jobs GUI (paired with the
            # create event's estimated_llm_calls). COALESCE-merged on the projection.
            params={"llm_calls_done": total_llm_calls},
            cost_usd=_last_cost,
            tokens_in=total_input_tokens or None, tokens_out=total_output_tokens or None,
        )

    await _emit_unified_progress()  # baseline (0/N fresh, or k/N on resume) before the loop

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
                reasoning_effort=reasoning_effort,
                concurrency=concurrency,
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
            # bug #37 — realized LLM calls = one per executed batch (BatchOutcome row), the
            # same unit estimated_llm_calls counts. Advances the Jobs-GUI "done / total".
            total_llm_calls += len(result.get("batch_outcomes") or [])
            completed += 1
            # OBS/M2 — the chapter status is DERIVED from its batch outcomes (INV-F15):
            # 'completed' only if every batch was clean, else 'completed_with_errors'. This
            # is the fix for the silent-failure bug — a chapter whose batches all rejected /
            # truncated no longer records as a clean success.
            ch_status = result.get("chapter_status", "completed")
            if ch_status == "completed_with_errors":
                chapters_with_errors += 1

            async with pool.acquire() as db:
                await db.execute(
                    """UPDATE extraction_chapter_results
                       SET status=$6, entities_found=$3,
                           input_tokens=$4, output_tokens=$5, completed_at=now()
                       WHERE job_id=$1 AND chapter_id=$2""",
                    job_id, chapter_id, ch_created + ch_updated,
                    ch_input_tokens, ch_output_tokens, ch_status,
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

        # Mirror the same advance onto the unified jobs-service stream (bug #2 — live progress
        # on the /jobs detail page). Reprice cost on the first processed chapter (so cost
        # appears early even for small jobs) and then every _COST_REPRICE_EVERY chapters;
        # tokens still update on every emit. See _emit_unified_progress above (bug #3).
        await _emit_unified_progress(reprice=(idx == 0 or (idx + 1) % _COST_REPRICE_EVERY == 0))

    # Job complete. OBS/M2 — the job is 'completed' only when nothing failed AND no chapter
    # finished with batch errors; a chapter that finished completed_with_errors now bubbles
    # up so the job rollup reflects the per-batch taxonomy instead of masking it.
    if completed == 0:
        final_status = "failed"
    elif failed == 0 and chapters_with_errors == 0:
        final_status = "completed"
    else:
        final_status = "completed_with_errors"
    # bug #34 (live-smoke D-CANCEL-IMMEDIATE) — a mid-chapter cancel that lands on the LAST
    # chapter aborts that chapter's in-flight LLM calls (the cancel_check → DELETE → upstream
    # abort) but never re-enters the per-chapter cooperative gate above (no chapter left to
    # gate), so the loop falls through to here with the job still 'cancelling'. Honor the
    # user's intent: report 'cancelled' (already-completed chapters are kept — the documented
    # "discards in-progress, keeps completed parts" semantics) instead of letting the
    # chapter-aggregate mask the cancel as 'completed_with_errors'.
    async with pool.acquire() as db:
        _cur_status = await db.fetchval(
            "SELECT status FROM extraction_jobs WHERE job_id=$1", job_id
        )
    if _cur_status in ("cancelling", "cancelled"):
        final_status = "cancelled"
    # bug #3 / D-JOBS-P4: derive the ACTUAL job cost from the summed tokens via the
    # provider-registry pricing oracle (the gateway `usage` carries only tokens). Resolved
    # out-of-tx (network I/O), best-effort (None on an unpriced model / registry blip), and
    # folded into the finalize UPDATE + the terminal job event so the GET endpoint and the
    # unified Jobs detail page both show the final cost.
    _final_cost = await resolve_job_cost_usd(
        owner_user_id=str(user_id), model_source=model_source, model_ref=model_ref,
        input_tokens=total_input_tokens, output_tokens=total_output_tokens,
    )
    async with pool.acquire() as db:
        await db.execute(
            "UPDATE extraction_jobs SET status=$2, finished_at=now(), "
            "cost_usd=COALESCE($3, cost_usd) WHERE job_id=$1",
            job_id, final_status, _final_cost,
        )

    # OBS/M2 (INV-O14) — the JOB-TERMINAL rollup. The per-batch outcome rows are the SSOT;
    # the notification sink gets ONLY this debounced job-level summary (never per-batch), so
    # the user sees an actionable "N batches truncated — raise the model / shrink the batch"
    # instead of a silent 0-entities success. Derived from the SSOT at finalize (best-effort:
    # a query failure just omits the summary). This is the consumer-side realization of the
    # batch-outcome SSOT — a per-batch projection to an external stream is intentionally NOT
    # emitted (no subscriber); the rollup here + the /reconcile sweep cover observability.
    batch_summary: dict[str, int] = {}
    try:
        async with pool.acquire() as db:
            srows = await db.fetch(
                "SELECT status, count(*) AS n FROM extraction_batch_outcomes "
                "WHERE job_id=$1 GROUP BY status", job_id)
        batch_summary = {r["status"]: r["n"] for r in srows}
    except Exception as exc:  # noqa: BLE001 — the summary is advisory, never fail finalize
        log.warning("extraction_worker: job %s batch-summary rollup failed: %s", job_id, exc)

    # P1 terminal emit (best-effort). 'completed_with_errors' has no canonical JobStatus →
    # map to 'completed' (the job DID finish; per-chapter failures are tracked on the row).
    # A late cancel (above) emits the canonical 'cancelled', mirroring the per-chapter
    # cooperative-gate path so the unified jobs stream agrees with the row status.
    if final_status == "cancelled":
        _canon = "cancelled"
    else:
        _canon = "completed" if final_status in ("completed", "completed_with_errors") else "failed"
    await emit_job_event_safe(
        pool, service=_JOB_SERVICE, job_id=str(job_id), owner_user_id=str(user_id),
        kind=_JOB_KIND, status=_canon,
        cost_usd=_final_cost,
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
            # INV-O14 rollup: a count per batch-outcome status across the whole job. A
            # non-empty truncated/validation_rejected/llm_error count is the actionable
            # signal (the 26-scenario bug was this being invisible).
            "batch_summary": batch_summary,
        },
    })

    if batch_summary.get("truncated") or batch_summary.get("validation_rejected") or batch_summary.get("llm_error"):
        log.warning(
            "extraction_worker: job %s finished with batch issues — %s (consider a smaller "
            "batch / larger model)", job_id, batch_summary,
        )

    log.info(
        "extraction_worker: job %s complete — created=%d updated=%d skipped=%d failed_chapters=%d",
        job_id, total_created, total_updated, total_skipped, failed,
    )

    # #26/#7 — end-of-job canonical resynthesis for `summarize`-mode attributes. The
    # writeback flagged each changed summarize attr canonical_dirty; now (after the job
    # terminal state, never for a cancelled job) batch-rewrite their accumulated raw
    # mentions into one deduped canonical value via the SAME provider-registry path this
    # job used. BEST-EFFORT + fully decoupled: the extraction already committed, so a
    # resummarize problem is logged and swallowed — it never changes the job's outcome.
    if final_status in ("completed", "completed_with_errors"):
        try:
            from .resummarize import run_resummarize_pass

            summary = await run_resummarize_pass(
                book_id=book_id, owner_user_id=str(user_id),
                model_source=model_source, model_ref=model_ref,
                source_language=source_language, llm_client=llm_client,
            )
            if summary.get("dirty"):
                log.info("extraction_worker: job %s resummarize — %s", job_id, summary)
        except Exception as exc:  # noqa: BLE001 — resummarize must never fail the job
            log.warning("extraction_worker: job %s resummarize pass failed (non-fatal): %s",
                        job_id, exc)


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
    reasoning_effort: str = "none",
    concurrency: int = 1,
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
    # OBS/M2 — per-batch outcome rows (the SSOT, INV-F15). Each batch contributes one
    # row with its classified status so a silent all-rejected/truncated/errored batch is
    # no longer invisible; the chapter status is then DERIVED from these (not from a bare
    # entity count). Persisted post-loop, idempotent on a stable event_id (INV-O13).
    batch_outcomes: list[dict] = []

    def _record_outcome(call_idx: int, batch: list, status: str, *, finish_reason=None,
                        entities_found=0, validation_rejected_count=0,
                        input_tokens=0, output_tokens=0, error_code=None):
        # call_idx is the unique per-chapter call index (window × kind-batch flattened), so the
        # row + event_id are unique even when the same kind-batch runs across multiple windows.
        batch_outcomes.append({
            "batch_idx": call_idx,
            "kinds": list(batch),
            "status": status,
            "finish_reason": finish_reason,
            "entities_found": entities_found,
            "validation_rejected_count": validation_rejected_count,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "error_code": error_code,
            "event_id": compute_event_id(str(job_id), str(chapter_id), call_idx, content_hash),
        })

    def _accept(entities: list[dict], window_text: str = "") -> None:
        # Attach this chapter's link to each entity (fresh per run — NOT cached, since the
        # chapter_index is per-job) and merge into the chapter's accumulated entities.
        #
        # M7 — per-chapter mention_count: count this entity's surface forms (canonical +
        # alias) in THIS window's text with a CJK-aware longest-match scan (span-deduped,
        # fold-insensitive). Presence-gated by construction: we only count for an entity we
        # just accepted as present in this chapter. _merge_window_entities SUMs the count
        # across windows of the same chapter_id, so a window-local count is correct here.
        chapter_title = chapter.get("title", "")
        for ent in entities:
            mention_count = count_entity_mentions(
                window_text, ent.get("name", ""), _entity_alias_forms(ent),
            ) if window_text else 0
            ent["chapter_links"] = [{
                "chapter_id": str(chapter_id),
                "chapter_title": chapter_title,
                "chapter_index": chapter_index,
                "relevance": ent.get("relevance", "appears"),
                "mention_count": mention_count,
            }]
        all_entities.extend(entities)

    _effort_band = effort_band_for(thinking_enabled, reasoning_effort)

    # Per-call output budget sized so input + output + safety ≤ context (so the gateway
    # never 400s on LLM_CONTEXT_OVERFLOW), capped — extraction output (entities JSON) is
    # small, so a modest ceiling avoids reserving context the input needs.
    safety = int(context_window * _CONTEXT_SAFETY_RATIO)
    max_win_tok = max((estimate_tokens(w) for w in windows), default=0)
    known_ctx_tok = estimate_tokens(known_ctx)
    out_budget = context_window - max_win_tok - safety - known_ctx_tok - 600
    out_budget = max(_EXTRACTION_OUTPUT_FLOOR, min(_EXTRACTION_OUTPUT_CEILING, out_budget))

    # D-CACHE-PLANNER-WIRING Part 2 — pre-flight FEASIBILITY gate (Option B, spec
    # docs/specs/2026-06-22-planner-executor-wiring-part2.md). The block-windower packs WHOLE
    # paragraph blocks; a single block bigger than the context can't be split further, so it
    # becomes an oversized window that TRUNCATES mid-output (entities silently LOST — the S1–S5
    # class) with no signal. Run the two-phase planner over the ACTUAL windows×batches and flag
    # any unit that can't fit even alone; the loop then records it `unplannable` + SKIPS its LLM
    # call (don't spend tokens to truncate). Units are splittable=False — a window is already the
    # finest block-join the executor can emit — and the unit id IS the (window,batch) coordinate,
    # so there's no remap onto the cache/OBS keys. The gate fires only when input doesn't fit with
    # the minimum output reservation (output_ceiling=floor, budget_ratio=1−safety) — EXACTLY the
    # condition under which the executor would truncate, so it never false-positives a window that
    # fits. Effort is irrelevant to INPUT feasibility (it spends within the output budget), so the
    # gate is effort-independent. Best-effort: any planner failure leaves it ungated (prior path).
    unplannable_keys: set[tuple[int, int]] = set()
    try:
        from loreweave_extraction import ModelCaps, PlanRequest, Policy, Unit, plan

        gate_units = []
        for wi, w in enumerate(windows):
            win_tok = estimate_tokens(w)
            for bi, b in enumerate(batches):
                schema_tok = sum(20 + len(extraction_profile.get(k, {})) * 40 for k in b)
                gate_units.append(Unit(
                    id=f"{wi}:{bi}", kind="extract",
                    est_input=win_tok + schema_tok + known_ctx_tok + 600,
                    est_output=_EXTRACTION_OUTPUT_FLOOR, splittable=False,
                    group=str(chapter_id),
                ))
        gate_plan = plan(PlanRequest(
            pipeline="extraction", units=gate_units,
            model=ModelCaps(context_window=context_window, output_ceiling=_EXTRACTION_OUTPUT_FLOOR),
            policy=Policy(budget_ratio=1.0 - _CONTEXT_SAFETY_RATIO, max_units_per_call=1),
        ))
        for up in gate_plan.unplannable:
            wi_s, _, bi_s = up.unit.id.partition(":")
            unplannable_keys.add((int(wi_s), int(bi_s)))
        if gate_plan.model_fit_warning:
            log.warning("extraction: chapter %s — %s", chapter_id, gate_plan.model_fit_warning)
        if unplannable_keys:
            log.warning("extraction: chapter %s — %d (window×batch) unit(s) UNPLANNABLE "
                        "(oversized block); skipping their LLM calls", chapter_id, len(unplannable_keys))
    except ImportError as exc:
        # Expected on a pre-planner image (before the SDK ships plan()) — ungated = prior path.
        log.debug("extraction: chapter %s planner gate unavailable (%s) — ungated", chapter_id, exc)
    except Exception as exc:  # noqa: BLE001 — gate is best-effort; ungated = prior behaviour
        # NOT an ImportError: a genuine gate failure (a plan() contract drift, a unit-id parse
        # error from a future splittable change, …). On a deployed stack the planner IS present,
        # so this is unexpected and means the gate SILENTLY reverted to the truncating path —
        # surface it loudly (WARNING, not DEBUG) so a broken gate can't hide. Mirrors the Part 1
        # cost-estimate fallback.
        log.warning("extraction: chapter %s planner gate FAILED (%s) — ungated (oversized blocks "
                    "will hit the LLM and may truncate)", chapter_id, exc)

    # Flatten window × kind-batch into one call sequence. `call_idx` is the unique per-chapter
    # call index — it keys the OBS event_id (so two windows' batch-0 don't collide), while the
    # CACHE key uses `chunk_idx`=window_idx + the real `batch_idx` so each window's parse caches
    # independently. `window_text` replaces the whole-chapter text in the prompt.
    total_calls = len(windows) * len(batches)

    # D-EXTRACTION-BATCH-CONCURRENCY — the per-(window,batch) unit body, extracted into a
    # coroutine so the units can run CONCURRENTLY under a semaphore (see the driver below).
    # asyncio is single-threaded, so the shared collectors mutate safely between awaits;
    # only the token sums are reassigned (nonlocal). Each unit owns a stable `call_idx`,
    # so OBS event_ids never collide. `continue` (loop control) → `return` (unit exit).
    async def _run_unit(call_idx, window_idx, window_text, batch_idx, batch):
        nonlocal total_input_tokens, total_output_tokens
        # Part 2 gate: a unit the planner refused as UNPLANNABLE (an oversized block that can't
        # fit even alone) — record the outcome + SKIP its LLM call. The chapter then derives
        # `completed_with_errors` (INV-F15), so the un-fittable batch is VISIBLE instead of
        # silently truncating; the entities from the fitting windows/batches still land.
        if (window_idx, batch_idx) in unplannable_keys:
            _record_outcome(call_idx, batch, UNPLANNABLE)
            log.warning("extraction: chapter %s call %d/%d (win %d batch %d) — UNPLANNABLE, "
                        "skipped LLM (block exceeds context)",
                        chapter_id, call_idx + 1, total_calls, window_idx, batch_idx)
            return

        # CACHE/M6 — LLM-skip gate (the EXECUTE ledger). If this exact (tenant, chapter
        # content, effort band, window, batch) was already extracted, reuse the cached parse
        # instead of re-spending tokens. Best-effort: a miss/error falls through to the call.
        cache_key = RawCacheKey(
            owner_user_id=str(owner_user_id) if owner_user_id else "",
            book_id=book_id, chapter_id=str(chapter_id), content_hash=content_hash,
            batch_idx=batch_idx, chunk_idx=window_idx, profile_hash=profile_hash,
            effort_band=_effort_band,
        )
        cached = await get_cached_batch(pool, cache_key) if owner_user_id else None
        # D-CACHE-MODEL-KEY: opt-in bust-on-model-change. The cache is content-addressed (model
        # NOT in the key), so a hit may carry a DIFFERENT model's parse. When the flag is on, a
        # hit whose stored model_ref differs from the resolved model is treated as a miss → a live
        # re-extraction on the new model (default off keeps the content-addressed reuse). `_busted`
        # is threaded to put_batch so the live re-extraction OVERWRITES the stale row (the key has
        # no model, so a plain DO-NOTHING put could never refresh it → every run would re-bust).
        _busted = False
        if (cached is not None and settings.extraction_cache_bust_on_model_change
                and cached.get("model_ref") and model_ref
                and str(cached["model_ref"]) != str(model_ref)):
            log.info("extraction: chapter %s call %d (win %d batch %d) — cache model %s ≠ current "
                     "%s; busting (re-extract on model change)",
                     chapter_id, call_idx + 1, window_idx, batch_idx, cached["model_ref"], model_ref)
            cached = None
            _busted = True
        if cached is not None:
            entities = cached["parsed_entities"]
            # Replay the cached batch outcome (status stored at first extraction); 0 NEW tokens
            # are spent (the cost was already paid + billed on the original run).
            _record_outcome(
                call_idx, batch, cached.get("parse_status") or "ok",
                finish_reason=cached.get("finish_reason"), entities_found=len(entities),
            )
            log.info("extraction: chapter %s call %d/%d (win %d) — CACHE HIT (%d entities, 0 tokens, effort=%s)",
                     chapter_id, call_idx + 1, total_calls, window_idx, len(entities), _effort_band)
            _accept(entities, window_text)
            return

        # 4. Build prompt
        _block_hints = settings.extraction_evidence_block_hints
        schema = build_extraction_prompt(batch, extraction_profile, kinds_metadata, block_hints=_block_hints)
        system_prompt = build_system_prompt(
            dynamic_schema=schema,
            source_language=source_language,
            known_entities_context=known_ctx,
            max_entities_per_kind=max_entities_per_kind,
        )
        user_prompt = build_user_prompt(window_text, block_hints=_block_hints)

        # 5. LLM call via SDK (replaces /internal/invoke).
        # Phase 4c-γ: HIGH#1 lesson from cycle 11 applied — catch
        # permanent SDK subclasses BEFORE generic LLMError so a
        # misconfigured BYOK doesn't poison the whole batch loop.
        call_input: dict = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            # Output ceiling — generous headroom so an entity-dense chapter completes
            # instead of truncating at finish_reason=length; if a batch still
            # truncates, the parser repairs the partial array.
            "max_tokens": out_budget,
            # D-RE-WORKER-GRADED-EFFORT: graded reasoning effort (none disables hidden
            # thinking so reasoning_tokens don't burn the output budget).
            **reasoning_fields(ReasoningDirective(
                effort=reasoning_effort, passthrough=False, source="user")),
        }
        # D-LLM-FAILURE-RATE #1 — force a valid JSON array of valid-kind entities
        # (kills the clean-finish malformed/wrong-kind residual). Gateway forwards it
        # to LM Studio/vLLM; a model/server that rejects the shape raises
        # LLMInvalidRequest and is retried ONCE without it (below), so structured
        # output never breaks a working model in a heterogeneous local fleet.
        if _STRUCTURED_OUTPUT_ENABLED:
            call_input["response_format"] = _entity_response_format(batch)

        async def _is_cancelled() -> bool:
            # bug #34: poll the parent extraction job's status so an in-flight LLM
            # call is aborted (DELETE'd at the gateway) the moment the user cancels
            # — instead of burning tokens until the call finishes naturally. A read
            # failure returns False so a transient DB blip never spuriously cancels a
            # healthy job (the SDK also tolerates a raising check; this is belt+braces).
            try:
                async with pool.acquire() as db:
                    st = await db.fetchval(
                        "SELECT status FROM extraction_jobs WHERE job_id=$1", job_id
                    )
                return st in ("cancelling", "cancelled")
            except Exception:  # noqa: BLE001 — never let a status read abort healthy work
                return False

        async def _submit(_inp: dict):
            return await llm_client.submit_and_wait(
                user_id=str(owner_user_id),
                # operation="chat" routes to the chatAggregator (chat-shaped result
                # we parse). bug #24: the Usage-GUI billing label rides
                # job_meta.usage_purpose so it reads "glossary_extraction", not "chat".
                operation="chat",
                model_source=model_source,
                model_ref=str(model_ref),
                input=_inp,
                chunking=None,
                job_meta={
                    "usage_purpose": "glossary_extraction",
                    "extractor": "glossary",
                    "extraction_job_id": str(job_id),
                    "chapter_id": str(chapter_id),
                    "batch_idx": batch_idx,
                },
                transient_retry_budget=1,
                cancel_check=_is_cancelled,
            )

        try:
            try:
                sdk_job = await _submit(call_input)
            except LLMInvalidRequest:
                # Most likely the model/server rejected response_format — degrade to
                # the prior (unstructured) behavior for this call rather than failing
                # the batch. A second 4xx propagates as a real permanent error below.
                if "response_format" not in call_input:
                    raise
                log.warning(
                    "extraction: response_format rejected for chapter %s batch %d/%d — retrying without structured output",
                    chapter_id, batch_idx + 1, len(batches),
                )
                call_input.pop("response_format", None)
                sdk_job = await _submit(call_input)
        except (LLMQuotaExceeded, LLMModelNotFound, LLMAuthFailed,
                LLMInvalidRequest, LLMDecodeError, LLMStreamNotSupported) as exc:
            log.error(
                "extraction: permanent SDK error %s for chapter %s batch %d/%d — failing batch",
                exc.__class__.__name__, chapter_id, batch_idx + 1, len(batches),
            )
            # OBS — the batch failed at the LLM; record it so the chapter can't read as
            # clean (was: a bare `continue` that silently dropped the batch).
            _record_outcome(call_idx, batch, LLM_ERROR, error_code=exc.__class__.__name__)
            return
        except (LLMTransientRetryNeededError, LLMError) as exc:
            log.error(
                "extraction: transient SDK error for chapter %s batch %d/%d: %s",
                chapter_id, batch_idx + 1, len(batches), exc,
            )
            _record_outcome(call_idx, batch, LLM_ERROR, error_code=exc.__class__.__name__)
            return

        if sdk_job.status != "completed":
            err_code = sdk_job.error.code if sdk_job.error else "unknown"
            log.error(
                "extraction: LLM job ended status=%s code=%s for chapter %s batch %d/%d — skipping batch (kinds: %s)",
                sdk_job.status, err_code, chapter_id, batch_idx + 1, len(batches), batch,
            )
            _record_outcome(call_idx, batch, LLM_ERROR, error_code=err_code)
            return

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

        # 6. Parse + validate (with stats so the batch outcome can be classified)
        entities, pstats = parse_and_validate_with_stats(response_text, batch, extraction_profile)

        # OBS/M2 — classify this batch. `truncated` (finish=length) wins over ok even when
        # some entities were salvaged (later ones were lost); a non-empty raw array with 0
        # survivors is `validation_rejected` (the all-kind-mismatch case), an empty array is
        # `empty_valid`. Recorded as the SSOT row; the chapter status derives from these.
        rejected = max(0, pstats.raw_count - len(entities))
        status = classify_batch(
            llm_errored=False,
            parse_ok=pstats.parse_ok,
            raw_entity_count=pstats.raw_count,
            validated_count=len(entities),
            finish_reason=finish_reason,
        )
        _record_outcome(
            call_idx, batch, status, finish_reason=finish_reason,
            entities_found=len(entities), validation_rejected_count=rejected,
            input_tokens=input_tokens, output_tokens=output_tokens,
        )

        # CACHE/M6 — record the EXECUTE-ledger row (LLM-skip on a future re-run). Only CLEAN
        # batches are cached ({ok, empty_valid}): a `truncated` (entities lost) or
        # `validation_rejected` batch must NOT become sticky — a re-run is exactly how the user
        # RECOVERS those, and a cache hit would return the same bad result forever (and short-
        # circuit the §8.3 re-plan-smaller signal). Stored PRE-chapter-links (the pure parse;
        # links are per-job, re-attached each run). parse_status carries the outcome so a hit
        # replays the taxonomy. Best-effort + idempotent (ON CONFLICT).
        if owner_user_id and status in (OK, EMPTY_VALID):
            await put_batch(
                pool, cache_key, job_id=str(job_id), kinds_requested=list(batch),
                model_source=model_source, model_ref=str(model_ref),
                reasoning_effort=_effort_band, input_tokens=input_tokens, output_tokens=output_tokens,
                finish_reason=finish_reason, raw_response=response_text,
                parsed_entities=entities, parse_status=status,
                # D-CACHE-MODEL-KEY: on a model-change bust, OVERWRITE the stale row so the cache
                # holds the new model's parse (else the next run re-busts forever).
                overwrite=_busted,
            )

        _accept(entities, window_text)

    # D-EXTRACTION-BATCH-CONCURRENCY — drive the per-(window,batch) units. Build the flat
    # unit list (call_idx = stable per-chapter index → OBS event_id), then run them under an
    # asyncio.Semaphore(concurrency). concurrency<=1 keeps the EXACT prior sequential path
    # (no gather/semaphore overhead — back-compat for tests + single-call models). Chapters
    # stay sequential (the caller loops chapters to accumulate known-entities); only THIS
    # chapter's batches fan out, up to `concurrency` concurrent LLM calls.
    _units = list(enumerate(
        (wi, w, bi, b) for wi, w in enumerate(windows) for bi, b in enumerate(batches)
    ))
    if concurrency <= 1:
        for _ci, (_wi, _w, _bi, _b) in _units:
            await _run_unit(_ci, _wi, _w, _bi, _b)
    else:
        _sem = asyncio.Semaphore(concurrency)

        async def _bounded(_ci, _wi, _w, _bi, _b):
            async with _sem:
                await _run_unit(_ci, _wi, _w, _bi, _b)

        await asyncio.gather(*[
            _bounded(_ci, _wi, _w, _bi, _b) for _ci, (_wi, _w, _bi, _b) in _units
        ])

    _ch_elapsed = _time.monotonic() - _ch_start

    # Accumulate across windows: the same entity can surface in multiple sub-chapter windows
    # — merge by (kind, normalized name), unioning chapter_links (context-window feature).
    all_entities = _merge_window_entities(all_entities)

    # OBS/M2 — persist the per-call outcome SSOT once the calls are done, BEFORE any downstream
    # early-return, so the empty/stale/success paths all record what each call actually did.
    # Best-effort (never fails the chapter). The chapter status is DERIVED from these (INV-F15)
    # so an all-rejected/truncated chapter no longer reads as a clean 'completed'.
    await _persist_batch_outcomes(pool, job_id, owner_user_id, book_id, chapter_id, batch_outcomes)
    chapter_status = chapter_status_from_outcomes([o["status"] for o in batch_outcomes])

    if not all_entities:
        log.info("extraction: chapter %s done in %.1fs — 0 entities (status=%s)",
                 chapter_id, _ch_elapsed, chapter_status)
        return {"created": 0, "updated": 0, "skipped": 0, "entities": [],
                "input_tokens": total_input_tokens, "output_tokens": total_output_tokens,
                "batch_finish_reasons": batch_finish_reasons,
                "batch_outcomes": batch_outcomes, "chapter_status": chapter_status}

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
                        "batch_finish_reasons": batch_finish_reasons,
                        "batch_outcomes": batch_outcomes, "chapter_status": chapter_status,
                        "stale_skipped": True}
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
        # Temporal-knowledge Path A (§12): pass the chapter's story-time ordinal so glossary
        # opens append-only bi-temporal facts valid-from this chapter (the SSOT producer).
        chapter_ordinal=chapter_index,
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
    upsert_result["batch_outcomes"] = batch_outcomes
    upsert_result["chapter_status"] = chapter_status
    return upsert_result
