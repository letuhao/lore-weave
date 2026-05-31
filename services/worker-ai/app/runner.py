"""K16.6b — Extraction job runner.

Core loop:
  1. Poll for running jobs (status='running')
  2. For each job, enumerate items by scope
  3. For each item: try_spend → extract → advance_cursor
  4. Detect pause/cancel between items
  5. On all items done → complete the job

DB queries are inline (not via shared repo classes) because worker-ai
is a separate service. The queries mirror ExtractionJobsRepo and
ExtractionPendingRepo from knowledge-service but only include the
subset the worker needs.
"""

from __future__ import annotations

import functools
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg
from opentelemetry import trace as _ot_trace

from loreweave_extraction import (
    EntityRecoveryConfig,
    PrecisionFilterConfig,
    ResolvedConfig,
    base_default_version,
    config_hash,
    extract_pass2,
    resolve_effective_config,
)
from loreweave_extraction.errors import ExtractionError

from app.clients import (
    BookClient,
    ChapterInfo,
    ExtractionResult,
    GlossaryClient,
    GlossaryEntity,
    KnowledgeClient,
)
from app.llm_client import LLMClient
from app.outbox_emit import emit_extraction_run, emit_extraction_run_best_effort

__all__ = ["process_job", "poll_and_run"]

logger = logging.getLogger(__name__)


# ── Cycle 72 — precision filter env-driven config ──────────────────────


def _load_precision_filter_config() -> PrecisionFilterConfig | None:
    """Read the cycle-72 precision filter env config.

    Returns:
        ``PrecisionFilterConfig`` when ``WORKER_AI_PRECISION_FILTER_MODEL_REF``
        is set; ``None`` otherwise (filter disabled — default).

    Envs:
        WORKER_AI_PRECISION_FILTER_MODEL_REF: gateway model_ref / UUID
            for the precision filter LLM call. Empty/unset = disabled.
        WORKER_AI_PRECISION_FILTER_PARTIAL_POLICY: ``"keep"`` (default)
            or ``"drop"``. ``"demote"`` raises NotImplementedError per
            spec D4.
        WORKER_AI_PRECISION_FILTER_MODEL_SOURCE: ``"user_model"``
            (default) or ``"platform_model"``.
        WORKER_AI_PRECISION_FILTER_CATEGORIES: comma-separated subset
            of ``{"entity","relation","event"}`` (default
            ``"entity,relation,event"`` for cycle-72 backward-compat;
            cycle-73b ship uses ``"relation"`` for 55% latency
            reduction at near-identical F1).
    """
    model_ref = os.environ.get("WORKER_AI_PRECISION_FILTER_MODEL_REF", "").strip()
    if not model_ref:
        return None
    partial_policy = os.environ.get(
        "WORKER_AI_PRECISION_FILTER_PARTIAL_POLICY", "keep"
    ).strip() or "keep"
    model_source = os.environ.get(
        "WORKER_AI_PRECISION_FILTER_MODEL_SOURCE", "user_model"
    ).strip() or "user_model"
    categories_env = os.environ.get(
        "WORKER_AI_PRECISION_FILTER_CATEGORIES", "entity,relation,event"
    ).strip() or "entity,relation,event"
    categories = tuple(
        c.strip() for c in categories_env.split(",") if c.strip()
    )
    return PrecisionFilterConfig(
        model_ref=model_ref,
        model_source=model_source,  # type: ignore[arg-type]
        partial_policy=partial_policy,  # type: ignore[arg-type]
        categories=categories,  # type: ignore[arg-type]
    )


# Cached at module load; None when env unset = zero-overhead default.
# Cycle 73f: runtime-overridable via Redis pubsub (consume_filter_reload_signal
# below). Module-level rebind is atomic via Python GIL.
_PRECISION_FILTER_CONFIG: PrecisionFilterConfig | None = _load_precision_filter_config()


def set_precision_filter_config(
    new_config: PrecisionFilterConfig | None,
) -> PrecisionFilterConfig | None:
    """Cycle 73f — atomically replace module-level cache from subscriber."""
    global _PRECISION_FILTER_CONFIG
    _PRECISION_FILTER_CONFIG = new_config
    return _PRECISION_FILTER_CONFIG


async def hydrate_precision_filter_config_from_redis(redis_url: str) -> None:
    """Cycle 73f r3 H1 fold — symmetric with KS hydrate. On worker
    startup, GET the Redis key + seed module-level cache. Without this,
    a worker container restart silently drops the ops-override and
    reverts to env defaults until next manual reload POST — defeating
    the cycle's "persistent across restart" promise (asymmetric with
    KS r2 H1 fold which already had hydrate).

    Cycle 73h: bumps `worker_ai_filter_reload_total{outcome=startup}`
    on success or `startup_failed` on exception (replaces cycle 73g
    M4's log-only emission)."""
    import redis.asyncio as aioredis
    from loreweave_extraction import get_filter_config

    from app.metrics import worker_ai_filter_reload_total

    redis_client = aioredis.from_url(redis_url, decode_responses=False)
    try:
        cached = await get_filter_config(redis_client)
        if cached is not None:
            set_precision_filter_config(cached)
            logger.info(
                "WORKER_FILTER_RELOAD outcome=startup active=true "
                "model_ref=%s categories=%s",
                cached.model_ref, cached.categories,
            )
        else:
            logger.info(
                "WORKER_FILTER_RELOAD outcome=startup active=false "
                "reason=redis_key_absent",
            )
        worker_ai_filter_reload_total.labels(outcome="startup").inc()
    except Exception:
        worker_ai_filter_reload_total.labels(outcome="startup_failed").inc()
        logger.exception(
            "WORKER_FILTER_RELOAD outcome=startup_failed reason=exception"
        )
    finally:
        try:
            await redis_client.aclose()
        except Exception:
            pass


async def consume_filter_reload_signal(redis_url: str) -> None:
    """Cycle 73f — subscribe to filter-reload pubsub; on each signal,
    re-read Redis key + atomically swap module-level cache.

    Resilient: SDK's subscribe_filter_reload has outer try/except with
    backoff so this never bubbles into asyncio.gather and kills the
    extraction job loop.
    """
    import redis.asyncio as aioredis
    from loreweave_extraction import (
        get_filter_config,
        subscribe_filter_reload,
    )

    redis_client = aioredis.from_url(redis_url, decode_responses=False)

    async def _on_reload() -> None:
        # Cycle 73h fold (closes cycle 73g M4 stopgap): bump Prometheus
        # counter on each pubsub-driven re-read outcome. Structured log
        # line retained for legacy ops grep tooling.
        from app.metrics import worker_ai_filter_reload_total
        try:
            new_config = await get_filter_config(redis_client)
            if new_config is None:
                # Cycle 74b — key absent (e.g. after a disable=true DELETE)
                # reverts to env config, matching startup-hydrate semantics
                # (hydrate keeps env config when the key is absent). Without
                # this, the runtime path set None (filter OFF) while a restart
                # reloads env config (filter ON) — a silent cross-path
                # divergence surfaced by the cycle-73f live smoke. `_load`
                # itself returns None when no filter env is set, so the
                # genuinely-no-filter deployment still ends at None.
                new_config = _load_precision_filter_config()
            set_precision_filter_config(new_config)
            worker_ai_filter_reload_total.labels(outcome="applied").inc()
            logger.info(
                "WORKER_FILTER_RELOAD outcome=applied active=%s "
                "model_ref=%s",
                new_config is not None,
                new_config.model_ref if new_config else None,
            )
        except Exception:
            worker_ai_filter_reload_total.labels(outcome="failed").inc()
            logger.exception(
                "WORKER_FILTER_RELOAD outcome=failed reason=exception"
            )

    try:
        await subscribe_filter_reload(redis_client, _on_reload)
    finally:
        try:
            await redis_client.aclose()
        except Exception:
            pass


def _load_entity_recovery_config() -> EntityRecoveryConfig | None:
    """Cycle 73d — read entity recovery env config.

    Returns:
        ``EntityRecoveryConfig`` when
        ``WORKER_AI_ENTITY_RECOVERY_MODEL_REF`` is set; ``None`` otherwise.

    Envs:
        WORKER_AI_ENTITY_RECOVERY_MODEL_REF: gateway model_ref / UUID
            for the Tier 3 LLM classifier.
        WORKER_AI_ENTITY_RECOVERY_MODEL_SOURCE: default "user_model".
        WORKER_AI_ENTITY_RECOVERY_MAX_BATCH: int (default 5).

    Note: worker-ai has no glossary access; `known_entity_kinds` stays
    empty. Tier 1 (glossary) is never used in this caller; Tier 3 (LLM)
    handles all unmatched names. Knowledge-service callers use the
    glossary-aware variant in pass2_orchestrator.
    """
    model_ref = os.environ.get(
        "WORKER_AI_ENTITY_RECOVERY_MODEL_REF", ""
    ).strip()
    if not model_ref:
        return None
    model_source = os.environ.get(
        "WORKER_AI_ENTITY_RECOVERY_MODEL_SOURCE", "user_model"
    ).strip() or "user_model"
    max_batch_env = os.environ.get(
        "WORKER_AI_ENTITY_RECOVERY_MAX_BATCH", "5"
    ).strip() or "5"
    try:
        max_batch = int(max_batch_env)
    except ValueError:
        max_batch = 5
    return EntityRecoveryConfig(
        model_ref=model_ref,
        model_source=model_source,  # type: ignore[arg-type]
        max_items_per_batch=max(1, max_batch),
    )


_ENTITY_RECOVERY_CONFIG: EntityRecoveryConfig | None = _load_entity_recovery_config()

# D-PHASE6C-WORKERAI-JOB-SPAN. Module-level tracer; when OTel is no-op
# (OTEL_EXPORTER_OTLP_ENDPOINT unset) this is the NoOp tracer and
# `start_as_current_span` is a zero-cost context manager. When
# configured, every loreweave_llm SDK call inside `process_job`
# becomes a CHILD of the parent `worker_ai.process_job` span (httpx
# instrumentor populates the W3C tracecontext on outbound calls) →
# Grafana Tempo shows the whole job lifecycle as one trace instead
# of N disconnected SDK-call traces.
tracer = _ot_trace.get_tracer(__name__)


def _with_job_span(func):
    """Decorator: wrap a `process_job`-shaped coroutine in an OTel parent
    span keyed on the job's identifiers.

    Decorator pattern (vs in-place `with` block) is deliberate — the
    body has ~14 inline `return` statements and the existing outer
    try/except SWALLOWS errors so a `try/finally`-around-body would
    require either re-indenting ~430 lines or refactoring the
    try/except semantic. The decorator approach lets the body stay
    verbatim and the span ends naturally on inner return.

    Span status caveat: because the inner body swallows exceptions and
    calls `_fail_job` itself, this wrapper sees a normal return on
    failed jobs and ends the span with OK status. Operators
    investigating a failure should grep logs for the job_id (still
    structured by the existing logger.exception) to find the trace
    id; the parent span correlates the SDK-call children regardless.
    A future enrichment can have the inner signal failure (e.g. via
    span context attribute) so the wrapper can set ERROR status.
    """
    @functools.wraps(func)
    async def wrapper(pool, knowledge_client, llm_client, book_client, glossary_client, job):
        with tracer.start_as_current_span(
            "worker_ai.process_job",
            attributes={
                "job.id": str(job.job_id),
                "job.scope": job.scope,
                "job.project_id": str(job.project_id),
                "job.user_id": str(job.user_id),
                "job.items_total": job.items_total or 0,
            },
        ):
            return await func(
                pool, knowledge_client, llm_client,
                book_client, glossary_client, job,
            )

    return wrapper

# Default token cost estimate per item for try_spend. The real cost
# is reconciled after the LLM call via the extraction result, but
# try_spend needs an upfront estimate to enforce the budget cap.
_DEFAULT_COST_PER_ITEM = Decimal("0.004")  # ~2000 tokens × $2/M

# C12c-a: glossary_sync items have no LLM call (pure Neo4j MERGE via
# the K15.11 helper). Cost is 0 but we still run them through
# _try_spend so the pause/cancel-detection flow stays uniform.
_GLOSSARY_SYNC_COST_PER_ITEM = Decimal("0.0")

# Max retries per item before skipping. Prevents infinite retry loops
# when a specific item consistently triggers a retryable LLM error.
_MAX_RETRIES_PER_ITEM = 3

# B2-B-b1 — sentinels distinguishing "caller omitted the arg" (use the module
# global) from "caller passed None" (override DISABLES the pass). An `is not
# None` gate would conflate the two (memory sdk-default-arg-dropped-from-wire):
# a project that disables its precision filter must get None, not the global.
_GLOBAL_FILTER_SENTINEL: Any = object()
_GLOBAL_RECOVERY_SENTINEL: Any = object()


# ── B2-A — extraction-run telemetry helpers ────────────────────────────


def _build_run_config(job: JobRow) -> tuple[ResolvedConfig, str, str]:
    """Assemble the effective config snapshot for a job + (config_hash,
    base_default_version).

    Pinned ONCE per job at start (DESIGN self-review #2): a mid-job
    precision-filter Redis reload does NOT change this snapshot, so every
    chapter run of the job attributes to the same config_hash. For every
    project today `extraction_config` is ``{}`` → the snapshot equals the
    global env defaults (behaviour unchanged); B2-B starts populating it.
    """
    global_defaults = {
        "model_ref": job.llm_model,
        "model_source": "user_model",
        "precision_filter": _PRECISION_FILTER_CONFIG,
        "entity_recovery": _ENTITY_RECOVERY_CONFIG,
        "writer_autocreate": False,
    }
    try:
        snapshot = resolve_effective_config(
            global_defaults=global_defaults,
            project_overrides=job.extraction_config or {},
        )
    except Exception:
        # /review-impl MED-3 — a malformed per-project extraction_config (e.g.
        # precision_filter enabled with no model_ref) must NOT fail the whole
        # job from the telemetry path. Degrade to global defaults + warn loudly.
        # Unreachable in B2-A (overrides always {}); B2-B's edit endpoint is the
        # primary guard (reject bad config at write time) — this is the net.
        logger.warning(
            "resolve_effective_config failed for job %s (malformed "
            "extraction_config?) — falling back to global defaults for telemetry",
            job.job_id, exc_info=True,
        )
        snapshot = resolve_effective_config(
            global_defaults=global_defaults, project_overrides={},
        )
    return snapshot, config_hash(snapshot), base_default_version(global_defaults)


async def _advance_cursor_and_emit_run(
    pool: asyncpg.Pool, user_id: UUID, job_id: UUID, cursor: dict, payload: dict,
) -> None:
    """Advance the cursor + emit the extraction_run ATOMICALLY (B2-A).

    Normal case: one transaction → the run row is guaranteed iff the cursor
    advanced (no silent gaps under normal operation; avoids the §2.4
    selection-bias the run telemetry exists to prevent).

    Failure case (/review-impl MED-1): if the transaction fails (an infra blip
    on the shared knowledge DB), fall back to a plain best-effort cursor-advance
    so the job still PROGRESSES — the chapter's real work already persisted to
    Neo4j, so we must not re-extract (re-spending LLM) nor fail the job. Run
    telemetry is NEVER load-bearing for extraction; the rare, random loss here
    is not systematic and does not bias config-vs-outcome analysis."""
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await _advance_cursor(conn, user_id, job_id, cursor)
                await emit_extraction_run(conn, payload)
    except Exception:
        logger.warning(
            "transactional run-emit failed for job %s; advancing cursor "
            "best-effort (run telemetry lost for this item, non-fatal)",
            job_id, exc_info=True,
        )
        await _advance_cursor(pool, user_id, job_id, cursor)


def _run_payload(
    *,
    job: JobRow,
    book_id: UUID | None,
    chapter_ref: str,
    snapshot: ResolvedConfig,
    cfg_hash: str,
    base_version: str,
    outcome: str,
    result: ExtractionResult | None,
) -> dict:
    """Build a `knowledge.extraction_run_completed` payload for one chapter.

    `resolved_config` carries prompt IDENTITY (prompt_versions), never raw
    prompt text (DESIGN Q5). metrics come from the per-chapter ExtractionResult
    (None on skip/fail → zero counts) + the flat per-item cost estimate.
    """
    metrics: dict[str, Any] = {
        "entities_merged": result.entities_merged if result else 0,
        "relations_created": result.relations_created if result else 0,
        "events_merged": result.events_merged if result else 0,
        "facts_merged": result.facts_merged if result else 0,
        "cost_usd": str(_DEFAULT_COST_PER_ITEM),
    }
    return {
        "run_id": str(uuid4()),
        "user_id": str(job.user_id),
        "project_id": str(job.project_id),
        "book_id": str(book_id) if book_id else None,
        "job_id": str(job.job_id),
        "scope": "chapter",
        "chapter_ref": str(chapter_ref),
        "config_hash": cfg_hash,
        "resolved_config": {
            "model_ref": snapshot.model_ref,
            "model_source": snapshot.model_source,
            "precision_filter": None if snapshot.precision_filter is None else {
                "model_ref": snapshot.precision_filter.model_ref,
                "model_source": snapshot.precision_filter.model_source,
                "categories": sorted(snapshot.precision_filter.categories),
                "partial_policy": snapshot.precision_filter.partial_policy,
            },
            "entity_recovery": None if snapshot.entity_recovery is None else {
                "model_ref": snapshot.entity_recovery.model_ref,
                "model_source": snapshot.entity_recovery.model_source,
            },
            "writer_autocreate": snapshot.writer_autocreate,
        },
        "prompt_versions": snapshot.prompt_versions,
        "base_default_version": base_version,
        "model_ref": snapshot.model_ref,
        "metrics": metrics,
        "outcome": outcome,
        "outcome_source": "pipeline",
        "emitted_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Data types ───────────────────────────────────────────────────────


@dataclass
class JobRow:
    job_id: UUID
    user_id: UUID
    project_id: UUID
    scope: str
    scope_range: dict | None
    status: str
    llm_model: str
    embedding_model: str
    max_spend_usd: Decimal | None
    items_total: int | None
    items_processed: int
    current_cursor: dict | None
    cost_spent_usd: Decimal
    # P3 D-P3-EXTRACTION-CALLER-WIRE-UP — sourced from knowledge_projects
    # (extraction_jobs doesn't carry the dimension; the project's
    # embedding_model UUID + dimension are the per-project vector-space
    # identity). NULL = project has no embedding configured → P3 enqueue
    # silently skipped by the receiving endpoint.
    embedding_dimension: int | None = None
    # B2-A — per-project extraction-config overrides (knowledge_projects
    # JSONB). {} for every project today; resolve_effective_config merges
    # it onto the global defaults to produce the run's config snapshot.
    extraction_config: dict | None = None


# ── DB helpers ───────────────────────────────────────────────────────


async def _get_running_jobs(pool: asyncpg.Pool) -> list[JobRow]:
    """Fetch all jobs in 'running' status.

    P3 D-P3-EXTRACTION-CALLER-WIRE-UP: also pull the project's
    embedding_dimension (kept on knowledge_projects, not on the job)
    so the worker can forward it to /persist-pass2 for summary enqueue.
    """
    rows = await pool.fetch(
        """
        SELECT j.job_id, j.user_id, j.project_id, j.scope, j.scope_range,
               j.status, j.llm_model, j.embedding_model, j.max_spend_usd,
               j.items_total, j.items_processed, j.current_cursor,
               j.cost_spent_usd, p.embedding_dimension, p.extraction_config
        FROM extraction_jobs j
        LEFT JOIN knowledge_projects p
          ON p.user_id = j.user_id AND p.project_id = j.project_id
        WHERE j.status = 'running'
        ORDER BY j.created_at ASC
        """
    )
    result = []
    for r in rows:
        sr = r["scope_range"]
        if isinstance(sr, str):
            sr = json.loads(sr)
        cc = r["current_cursor"]
        if isinstance(cc, str):
            cc = json.loads(cc)
        ec = r["extraction_config"]
        if isinstance(ec, str):
            ec = json.loads(ec)
        result.append(JobRow(
            job_id=r["job_id"],
            user_id=r["user_id"],
            project_id=r["project_id"],
            scope=r["scope"],
            scope_range=sr,
            status=r["status"],
            llm_model=r["llm_model"],
            embedding_model=r["embedding_model"],
            max_spend_usd=r["max_spend_usd"],
            items_total=r["items_total"],
            items_processed=r["items_processed"],
            current_cursor=cc,
            cost_spent_usd=r["cost_spent_usd"],
            embedding_dimension=r["embedding_dimension"],
            extraction_config=ec if isinstance(ec, dict) else None,
        ))
    return result


async def _refresh_job_status(pool: asyncpg.Pool, job_id: UUID) -> str | None:
    """Re-read job status from DB. Returns None if job not found."""
    row = await pool.fetchval(
        "SELECT status FROM extraction_jobs WHERE job_id = $1",
        job_id,
    )
    return row


async def _try_spend(
    pool: asyncpg.Pool, user_id: UUID, job_id: UUID, cost: Decimal,
) -> str:
    """Atomic cost reservation. Returns 'reserved', 'auto_paused', or 'not_running'.

    Mirror of ExtractionJobsRepo.try_spend — see that class for the
    full safety rationale.
    """
    row = await pool.fetchrow(
        """
        UPDATE extraction_jobs
        SET
          cost_spent_usd = cost_spent_usd + $3,
          status = CASE
            WHEN max_spend_usd IS NOT NULL
                 AND cost_spent_usd + $3 >= max_spend_usd
              THEN 'paused'
            ELSE status
          END,
          paused_at = CASE
            WHEN max_spend_usd IS NOT NULL
                 AND cost_spent_usd + $3 >= max_spend_usd
              THEN now()
            ELSE paused_at
          END,
          updated_at = now()
        WHERE user_id = $1 AND job_id = $2 AND status = 'running'
        RETURNING cost_spent_usd, status
        """,
        user_id, job_id, cost,
    )
    if row is None:
        return "not_running"
    return "auto_paused" if row["status"] == "paused" else "reserved"


async def _advance_cursor(
    executor: Any, user_id: UUID, job_id: UUID,
    cursor: dict, items_delta: int = 1,
) -> None:
    """Persist progress so a restart can resume from here.

    `executor` is a Pool (default) OR an asyncpg Connection — the latter lets
    the chapter-success/skip path advance the cursor AND emit the
    extraction_run in ONE transaction (B2-A): the run row is guaranteed iff the
    cursor advanced, and an emit failure rolls back the advance (chapter
    re-processed, never a silently-missing run)."""
    await executor.execute(
        """
        UPDATE extraction_jobs
        SET current_cursor = $3::jsonb,
            items_processed = items_processed + $4,
            updated_at = now()
        WHERE user_id = $1 AND job_id = $2
          AND status IN ('running', 'paused')
        """,
        user_id, job_id, json.dumps(cursor), items_delta,
    )


async def _append_log(
    pool: asyncpg.Pool,
    user_id: UUID,
    job_id: UUID,
    level: str,
    message: str,
    context: dict | None = None,
) -> None:
    """K19b.8 — mirror a key lifecycle event to job_logs so the FE's
    JobLogsPanel can render it. Inlined SQL matches the worker's
    existing `_try_spend` / `_record_spending` pattern (worker owns
    the DB write path to the shared knowledge DB; avoids an HTTP
    round-trip per event).

    Vocabulary: level MUST be one of info/warning/error (enforced by
    the table CHECK constraint). Caller passes an optional JSON
    context (e.g. chapter_id, error text) that's serialised inline.
    Fire-and-forget from the caller's point of view — we don't return
    the log_id; callers don't chain on it.
    """
    await pool.execute(
        """
        INSERT INTO job_logs (job_id, user_id, level, message, context)
        VALUES ($1, $2, $3, $4, $5::jsonb)
        """,
        job_id,
        user_id,
        level,
        message,
        json.dumps(context or {}),
    )


async def _record_spending(
    pool: asyncpg.Pool, user_id: UUID, project_id: UUID, cost: Decimal,
) -> None:
    """D-K16.11-01 — update the per-project monthly + all-time spend
    counters after a successful extraction item.

    Mirrors ``app.jobs.budget.record_spending`` in knowledge-service;
    kept inline here for the same reason ``_try_spend`` is — the worker
    owns the write path to the same DB and avoids an HTTP round-trip
    per item. Handles month rollover atomically via CASE-on-key: if the
    project's ``current_month_key`` doesn't match the current month,
    the counter resets to this cost before adding.

    Not guarded by an atomic budget check — that's ``_try_spend``'s job
    on ``extraction_jobs.max_spend_usd``. This function is strictly
    accounting + rollover.
    """
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    await pool.execute(
        """
        UPDATE knowledge_projects
        SET current_month_spent_usd = CASE
              WHEN current_month_key = $3 THEN current_month_spent_usd + $4
              ELSE $4
            END,
            current_month_key = $3,
            actual_cost_usd = actual_cost_usd + $4,
            updated_at = now()
        WHERE user_id = $1 AND project_id = $2
        """,
        user_id, project_id, month_key, cost,
    )


async def _complete_job(pool: asyncpg.Pool, user_id: UUID, job_id: UUID) -> None:
    """Transition job to 'complete'."""
    await pool.execute(
        """
        UPDATE extraction_jobs
        SET status = 'complete', completed_at = now(), updated_at = now()
        WHERE user_id = $1 AND job_id = $2
          AND status NOT IN ('complete', 'cancelled', 'failed')
        """,
        user_id, job_id,
    )


async def _fail_job(
    pool: asyncpg.Pool, user_id: UUID, job_id: UUID, error: str,
) -> None:
    """Transition job to 'failed' with an error message."""
    await pool.execute(
        """
        UPDATE extraction_jobs
        SET status = 'failed', completed_at = now(), updated_at = now(),
            error_message = $3
        WHERE user_id = $1 AND job_id = $2
          AND status NOT IN ('complete', 'cancelled', 'failed')
        """,
        user_id, job_id, error[:2000],
    )


async def _get_project_book_id(
    pool: asyncpg.Pool, user_id: UUID, project_id: UUID,
) -> UUID | None:
    """Look up the book_id for a project. Returns None if the project
    has no linked book or doesn't exist."""
    row = await pool.fetchval(
        "SELECT book_id FROM knowledge_projects WHERE user_id = $1 AND project_id = $2",
        user_id, project_id,
    )
    return row


async def _set_items_total(
    pool: asyncpg.Pool, user_id: UUID, job_id: UUID, total: int,
) -> None:
    """Set items_total on a job (for progress percentage in UI)."""
    await pool.execute(
        """
        UPDATE extraction_jobs
        SET items_total = $3, updated_at = now()
        WHERE user_id = $1 AND job_id = $2
          AND status NOT IN ('complete', 'cancelled', 'failed')
        """,
        user_id, job_id, total,
    )


async def _update_project_status(
    pool: asyncpg.Pool, user_id: UUID, project_id: UUID,
    extraction_status: str,
) -> None:
    """Update project extraction_status (advisory — job is source of truth)."""
    await pool.execute(
        """
        UPDATE knowledge_projects
        SET extraction_status = $3, updated_at = now()
        WHERE user_id = $1 AND project_id = $2
        """,
        user_id, project_id, extraction_status,
    )


# ── Item enumeration ─────────────────────────────────────────────────


async def _enumerate_chapters(
    book_client: BookClient, book_id: UUID | None, cursor: dict | None,
) -> list[ChapterInfo]:
    """Get chapters to process, respecting cursor for resume."""
    if book_id is None:
        return []
    chapters = await book_client.list_chapters(book_id)
    if chapters is None:
        return []

    # Resume: skip chapters already processed (cursor has last_chapter_id)
    if cursor and cursor.get("last_chapter_id"):
        last_id = cursor["last_chapter_id"]
        found = False
        filtered = []
        for ch in chapters:
            if found:
                filtered.append(ch)
            if ch.chapter_id == last_id:
                found = True
        if not found:
            # Cursor chapter no longer in list (deleted between runs).
            # Process all chapters from scratch rather than silently
            # completing with zero work.
            logger.warning(
                "Cursor chapter %s not found in chapter list — "
                "restarting from beginning",
                last_id,
            )
            return chapters
        return filtered

    return chapters


async def _enumerate_glossary_entities(
    glossary_client: GlossaryClient,
    book_id: UUID | None,
    cursor: dict | None,
) -> tuple[list[GlossaryEntity], bool]:
    """C12c-a — page through a book's glossary entities.

    Aggregates all pages into a single list (books are user-curated,
    hundreds at most — not millions). On resume, skips entities with
    ``entity_id <= cursor.last_glossary_entity_id`` since the
    glossary-service endpoint orders by UUID ASC (total ordering).

    Returns ``(entities, complete)`` where ``complete`` is ``False``
    when glossary-service returned ``None`` mid-enumeration OR the
    HARD_CAP truncation kicked in. The caller uses ``complete`` to
    decide whether to set items_total — an incomplete enumeration
    would underestimate and freeze the progress bar at the wrong
    total (/review-impl LOW#5).

    Graceful-degrade: on ANY glossary-service failure the partial
    list so far is returned; the next job run re-enumerates from
    scratch (resume_after skips what we already synced).

    Hard cap: 5000 entities per job. Books with more are rare and
    the cap prevents a runaway enumeration from blocking the worker
    if the BE endpoint's `next_cursor` logic regresses.
    """
    if book_id is None:
        return [], True
    resume_after: str | None = None
    if cursor and cursor.get("last_glossary_entity_id"):
        resume_after = str(cursor["last_glossary_entity_id"])

    out: list[GlossaryEntity] = []
    page_cursor: str | None = None
    pages_fetched = 0
    HARD_CAP = 5000
    while True:
        page = await glossary_client.list_book_entities(
            book_id, cursor=page_cursor, limit=100,
        )
        if page is None:
            # Graceful-degrade: stop enumerating. Any entities already
            # collected in this pass are kept (the caller will still
            # process them; a future resume retries the failed page).
            logger.warning(
                "Job glossary enumeration partial for book %s "
                "(glossary-service returned None); %d entities collected "
                "so far will process but items_total will not be set",
                book_id, len(out),
            )
            return out, False
        pages_fetched += 1
        for ent in page.items:
            # Resume filter: skip entities we've already synced in a
            # prior worker run. UUID ordering is total, so string
            # compare against the cursor id works.
            if resume_after and ent.entity_id <= resume_after:
                continue
            out.append(ent)
            if len(out) >= HARD_CAP:
                logger.warning(
                    "Job glossary enumeration hit HARD_CAP=%d for book %s "
                    "— truncating this run's sync",
                    HARD_CAP, book_id,
                )
                return out, False
        if not page.next_cursor:
            return out, True
        page_cursor = page.next_cursor
        # Defensive: protect against a pathological loop if BE returns
        # the same cursor repeatedly.
        if pages_fetched > 200:
            logger.warning(
                "Job glossary enumeration hit 200-page ceiling for book %s",
                book_id,
            )
            return out, False


async def _enumerate_pending_chat_turns(
    pool: asyncpg.Pool, user_id: UUID, project_id: UUID,
) -> list[dict]:
    """Fetch unprocessed chat turn events from extraction_pending."""
    rows = await pool.fetch(
        """
        SELECT ep.pending_id, ep.event_id, ep.event_type,
               ep.aggregate_type, ep.aggregate_id
        FROM extraction_pending ep
        JOIN knowledge_projects p
          ON p.project_id = ep.project_id AND p.user_id = $1
        WHERE ep.project_id = $2 AND ep.processed_at IS NULL
        ORDER BY ep.created_at ASC
        LIMIT 1000
        """,
        user_id, project_id,
    )
    return [dict(r) for r in rows]


async def _mark_pending_processed(
    pool: asyncpg.Pool, user_id: UUID, pending_id: UUID,
) -> None:
    """Mark a pending event as processed."""
    await pool.execute(
        """
        UPDATE extraction_pending ep
        SET processed_at = now()
        FROM knowledge_projects p
        WHERE ep.pending_id = $2
          AND ep.processed_at IS NULL
          AND p.project_id = ep.project_id
          AND p.user_id = $1
        """,
        user_id, pending_id,
    )


# ── Phase 4b-γ — extract+persist helper ─────────────────────────────


async def _extract_and_persist(
    *,
    knowledge_client: KnowledgeClient,
    llm_client: LLMClient,
    user_id: UUID,
    project_id: UUID | None,
    source_type: str,
    source_id: str,
    job_id: UUID,
    model_ref: str,
    text: str,
    # B2-B-b1 — per-project resolved config. Default to the module globals so
    # the chat_turn / glossary callers keep the legacy behaviour; the chapter
    # branch passes the job's resolved snapshot so a project's extraction_config
    # override actually drives the pipeline. `_SENTINEL` distinguishes "caller
    # didn't pass" (use global) from "caller passed None" (override = disabled).
    precision_filter: "PrecisionFilterConfig | None" = _GLOBAL_FILTER_SENTINEL,
    entity_recovery: "EntityRecoveryConfig | None" = _GLOBAL_RECOVERY_SENTINEL,
    # B2-B-b2 — per-op raw system-prompt overrides {op: {"system": str}} from
    # the job's resolved snapshot ({} when the project has no custom prompts).
    prompt_overrides: dict | None = None,
    # B2 follow-up — per-project Pass2-writer autocreate override (forwarded to
    # /persist-pass2). None = chat/glossary callers leave the env default.
    writer_autocreate: bool | None = None,
    # P3 D-P3-EXTRACTION-CALLER-WIRE-UP — all optional. Caller (chapter
    # branch) supplies these to opt into hierarchy MERGE + summary
    # enqueue. chat_turn branch keeps the legacy behaviour.
    hierarchy_paths: dict | None = None,
    book_parts: list[tuple[str, str, str]] | None = None,
    is_last_chapter_of_book: bool = False,
    embedding_model_uuid: str | None = None,
    embedding_dimension: int | None = None,
) -> ExtractionResult:
    """Phase 4b-γ — replaces the legacy `knowledge_client.extract_item`.

    Two-step flow:
      1. Worker-ai runs Pass 2 LLM extraction in-process via
         ``loreweave_extraction.extract_pass2`` — no longer blocked by
         knowledge-service's 120s extract_item HTTP timeout.
      2. Resulting candidates are POSTed to knowledge-service's thin
         ``/internal/extraction/persist-pass2`` endpoint, which only
         does Neo4j writes (bounded latency).

    `ExtractionError` from the LLM stage maps to the same retryable /
    non-retryable contract the legacy `extract_item` exposed:
      - stage='provider_exhausted' → retryable=True (worker retries)
      - all other stages → retryable=False (skip / fail per caller)

    Empty / whitespace `text` → empty Pass2Candidates (library
    short-circuits without calling LLM); persist-pass2 still writes
    the source row for idempotency.
    """
    # B2-B-b1 — resolve the effective filter/recovery: a caller that omitted
    # the arg gets the module global (chat_turn/glossary); the chapter branch
    # passes the job's resolved snapshot (which is the global when the project
    # has no override, None when the project disabled it, or a per-project
    # config when overridden).
    eff_filter = (
        _PRECISION_FILTER_CONFIG if precision_filter is _GLOBAL_FILTER_SENTINEL
        else precision_filter
    )
    eff_recovery = (
        _ENTITY_RECOVERY_CONFIG if entity_recovery is _GLOBAL_RECOVERY_SENTINEL
        else entity_recovery
    )
    try:
        candidates = await extract_pass2(
            text=text,
            known_entities=[],
            user_id=str(user_id),
            project_id=str(project_id) if project_id else None,
            model_source="user_model",
            model_ref=model_ref,
            llm_client=llm_client,
            # Cycle 72 / B2-B-b1 — precision filter, now per-project-resolvable.
            # None = no filter; degraded path surfaces via
            # candidates.filter_status without raising.
            precision_filter=eff_filter,
            # Cycle 73d / B2-B-b1 — entity recovery (3-tier), per-project-
            # resolvable. Runs BEFORE filter. Worker-ai has no glossary access
            # so all unmatched names go to the LLM classifier (Tier 3).
            entity_recovery=eff_recovery,
            # B2-B-b2 — per-op raw system-prompt overrides ({} = all defaults).
            prompt_overrides=prompt_overrides,
        )
    except ExtractionError as exc:
        retryable = exc.stage == "provider_exhausted"
        logger.warning(
            "extract_pass2 failed source_id=%s stage=%s retryable=%s: %s",
            source_id, exc.stage, retryable, exc,
        )
        return ExtractionResult(
            source_id=source_id,
            entities_merged=0,
            relations_created=0,
            events_merged=0,
            facts_merged=0,
            retryable=retryable,
            error=f"extraction failed (stage={exc.stage}): {exc}",
        )

    return await knowledge_client.persist_pass2(
        user_id=user_id,
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
        job_id=job_id,
        extraction_model=model_ref,
        entities=candidates.entities,
        relations=candidates.relations,
        events=candidates.events,
        facts=candidates.facts,
        # P3 — pass-through to the receiving endpoint. When None →
        # endpoint skips hierarchy MERGE + summary enqueue.
        hierarchy_paths=hierarchy_paths,
        book_parts=book_parts,
        is_last_chapter_of_book=is_last_chapter_of_book,
        embedding_model_uuid=embedding_model_uuid,
        embedding_dimension=embedding_dimension,
        writer_autocreate=writer_autocreate,
    )


# ── Core job processing ─────────────────────────────────────────────


@_with_job_span
async def process_job(
    pool: asyncpg.Pool,
    knowledge_client: KnowledgeClient,
    llm_client: LLMClient,
    book_client: BookClient,
    glossary_client: GlossaryClient,
    job: JobRow,
) -> None:
    """Process all items for a single extraction job.

    Handles:
      - Item enumeration by scope (chapters, chat, glossary_sync, all)
      - Per-item: try_spend → extract → advance_cursor
      - Pause/cancel detection between items
      - Job completion / failure

    C12c-a: scope='glossary_sync' iterates a book's glossary entities
    via glossary-service pagination, calling knowledge-service's
    glossary-sync-entity endpoint per entity. scope='all' runs this
    tail after chapters+chat.
    """
    logger.info(
        "Processing job %s (scope=%s, project=%s, processed=%d/%s)",
        job.job_id, job.scope, job.project_id,
        job.items_processed, job.items_total or "?",
    )

    items_processed = 0
    try:
        # Resolve book_id from project (project_id ≠ book_id)
        book_id = await _get_project_book_id(pool, job.user_id, job.project_id)

        # B2-A — pin the effective config snapshot ONCE per job (a mid-job
        # filter reload won't change this job's config_hash). Used for the
        # per-chapter extraction_run telemetry; behaviour is unchanged because
        # extract_pass2 still reads the module globals in B2-A (B2-B wires the
        # snapshot into the pipeline).
        run_snapshot, run_cfg_hash, run_base_version = _build_run_config(job)

        # Pre-enumerate items. Done once — the results are reused for
        # both K16.7 items_total counting and the main processing loop,
        # avoiding a second HTTP call to book-service.
        pre_chapters: list[ChapterInfo] | None = None
        pre_pending: list[dict] | None = None
        pre_glossary: list[GlossaryEntity] | None = None
        glossary_enumeration_complete: bool = True

        if job.scope in ("chapters", "all"):
            pre_chapters = await _enumerate_chapters(
                book_client, book_id, job.current_cursor,
            )
        if job.scope in ("chat", "all"):
            pre_pending = await _enumerate_pending_chat_turns(
                pool, job.user_id, job.project_id,
            )
        # C12c-a: pre-enumerate glossary entities for glossary_sync OR
        # all-scope (if the project has a book). Empty / None book_id
        # → skip silently, matching the book-service enumerator.
        if job.scope in ("glossary_sync", "all") and book_id is not None:
            pre_glossary, glossary_enumeration_complete = (
                await _enumerate_glossary_entities(
                    glossary_client, book_id, job.current_cursor,
                )
            )

        # K16.7: if items_total wasn't set by the caller (backfill case),
        # count items now so the UI can show progress percentage.
        # C12c-a /review-impl LOW#5: skip items_total when the glossary
        # enumeration came back partial (glossary-service flake
        # mid-pagination, or HARD_CAP hit) — using the partial count
        # would freeze the progress bar at a wrong total.
        if job.items_total is None and glossary_enumeration_complete:
            total = (
                len(pre_chapters or [])
                + len(pre_pending or [])
                + len(pre_glossary or [])
            )
            await _set_items_total(pool, job.user_id, job.job_id, total)
            logger.info("Job %s: items_total set to %d (chapters=%d, chat=%d)",
                        job.job_id, total,
                        len(pre_chapters or []), len(pre_pending or []))

        # Process items based on scope
        if pre_chapters:
            for ch in pre_chapters:
                # Check job status (pause/cancel detection)
                status = await _refresh_job_status(pool, job.job_id)
                if status != "running":
                    logger.info("Job %s no longer running (status=%s), stopping", job.job_id, status)
                    return

                # Atomic cost reservation
                outcome = await _try_spend(
                    pool, job.user_id, job.job_id, _DEFAULT_COST_PER_ITEM,
                )
                if outcome == "not_running":
                    logger.info("Job %s try_spend returned not_running, stopping", job.job_id)
                    return
                if outcome == "auto_paused":
                    logger.info("Job %s auto-paused by budget cap", job.job_id)
                    await _append_log(
                        pool, job.user_id, job.job_id, "warning",
                        "Job auto-paused: max_spend_usd reached",
                        context={"event": "auto_paused", "scope": "chapters"},
                    )
                    await _update_project_status(pool, job.user_id, job.project_id, "paused")
                    return

                # Get chapter text
                text = await book_client.get_chapter_text(book_id, ch.chapter_id)
                if text is None:
                    logger.warning("Skipping chapter %s — text unavailable", ch.chapter_id)
                    await _append_log(
                        pool, job.user_id, job.job_id, "warning",
                        f"Skipped chapter {ch.chapter_id}: text unavailable",
                        context={
                            "event": "chapter_skipped",
                            "chapter_id": str(ch.chapter_id),
                            "reason": "text_unavailable",
                        },
                    )
                    unavail_payload = _run_payload(
                        job=job, book_id=book_id, chapter_ref=ch.chapter_id,
                        snapshot=run_snapshot, cfg_hash=run_cfg_hash,
                        base_version=run_base_version, outcome="skipped", result=None,
                    )
                    await _advance_cursor_and_emit_run(
                        pool, job.user_id, job.job_id,
                        {"last_chapter_id": ch.chapter_id, "scope": "chapters"},
                        unavail_payload,
                    )
                    continue

                # P3 D-P3-EXTRACTION-CALLER-WIRE-UP — fetch hierarchy
                # info (book/part/chapter/scenes/book_parts) so the
                # /persist-pass2 endpoint can MERGE the hierarchy in
                # the same Tx + enqueue summaries. Best-effort: None
                # response (legacy chapter w/o part_id, or HTTP
                # failure) → skip P3 fields, fall back to the legacy
                # entity-only persist path.
                p3_hierarchy_paths: dict | None = None
                p3_book_parts: list[tuple[str, str, str]] | None = None
                p3_is_last = False
                hierarchy = await book_client.get_chapter_hierarchy(
                    book_id, ch.chapter_id,
                )
                if (
                    hierarchy is not None
                    and hierarchy.part is not None
                    and hierarchy.chapter_path is not None
                    and job.embedding_dimension is not None
                ):
                    p3_hierarchy_paths = {
                        "book_id": hierarchy.book_id,
                        "book_path": hierarchy.book_path,
                        "book_title": hierarchy.book_title,
                        "part_id": hierarchy.part.id,
                        "part_path": hierarchy.part.path,
                        "part_index": hierarchy.part.index,
                        "part_title": hierarchy.part.title,
                        "chapter_id": hierarchy.chapter_id,
                        "chapter_path": hierarchy.chapter_path,
                        "chapter_index": hierarchy.chapter_index,
                        "chapter_title": hierarchy.chapter_title,
                        "scenes": [
                            [s.id, s.path, s.index] for s in hierarchy.scenes
                        ],
                    }
                    p3_book_parts = [
                        [bp.id, bp.path, str(bp.index)]
                        for bp in hierarchy.book_parts
                    ]
                    # is_last when this chapter is the last in the
                    # pre-enumerated chapter list AND no retry — runner
                    # already filters cursor-resumed chapters, so the
                    # tail of pre_chapters is the natural last.
                    p3_is_last = ch.chapter_id == pre_chapters[-1].chapter_id

                # Extract: Phase 4b-γ — worker-ai now runs the LLM
                # stage in-process via loreweave_extraction.extract_pass2,
                # then POSTs candidates to /persist-pass2.
                result = await _extract_and_persist(
                    knowledge_client=knowledge_client,
                    llm_client=llm_client,
                    user_id=job.user_id,
                    project_id=job.project_id,
                    source_type="chapter",
                    source_id=ch.chapter_id,
                    job_id=job.job_id,
                    # B2-B-b1 — the job's resolved snapshot drives extraction:
                    # per-project model + filter + recovery overrides (or the
                    # global defaults when the project has no extraction_config).
                    model_ref=run_snapshot.model_ref,
                    precision_filter=run_snapshot.precision_filter,
                    entity_recovery=run_snapshot.entity_recovery,
                    prompt_overrides=run_snapshot.prompts,
                    writer_autocreate=run_snapshot.writer_autocreate,
                    text=text,
                    hierarchy_paths=p3_hierarchy_paths,
                    book_parts=p3_book_parts,
                    is_last_chapter_of_book=p3_is_last,
                    embedding_model_uuid=(
                        job.embedding_model if p3_hierarchy_paths else None
                    ),
                    embedding_dimension=(
                        job.embedding_dimension if p3_hierarchy_paths else None
                    ),
                )

                if result.error:
                    if not result.retryable:
                        await _append_log(
                            pool, job.user_id, job.job_id, "error",
                            f"Job failed on chapter {ch.chapter_id}: {result.error}",
                            context={
                                "event": "failed",
                                "chapter_id": str(ch.chapter_id),
                                "error": result.error,
                            },
                        )
                        await _fail_job(pool, job.user_id, job.job_id, result.error)
                        await _update_project_status(pool, job.user_id, job.project_id, "failed")
                        # B2-A — record the failed run best-effort (no cursor
                        # advance to ride): a config that reliably crashes must
                        # be visible-as-bad, not invisible to the telemetry.
                        await emit_extraction_run_best_effort(pool, _run_payload(
                            job=job, book_id=book_id, chapter_ref=ch.chapter_id,
                            snapshot=run_snapshot, cfg_hash=run_cfg_hash,
                            base_version=run_base_version, outcome="failed", result=result,
                        ))
                        return
                    # Track retry count in cursor to prevent infinite loops
                    retry_key = f"retry_{ch.chapter_id}"
                    cur = job.current_cursor or {}
                    retries = cur.get(retry_key, 0) + 1
                    if retries >= _MAX_RETRIES_PER_ITEM:
                        logger.warning(
                            "Skipping chapter %s after %d retries: %s",
                            ch.chapter_id, retries, result.error,
                        )
                        await _append_log(
                            pool, job.user_id, job.job_id, "error",
                            f"Chapter {ch.chapter_id} skipped after {retries} retries",
                            context={
                                "event": "retry_exhausted",
                                "chapter_id": str(ch.chapter_id),
                                "retries": retries,
                                "error": result.error,
                            },
                        )
                        skip_payload = _run_payload(
                            job=job, book_id=book_id, chapter_ref=ch.chapter_id,
                            snapshot=run_snapshot, cfg_hash=run_cfg_hash,
                            base_version=run_base_version, outcome="skipped", result=None,
                        )
                        await _advance_cursor_and_emit_run(
                            pool, job.user_id, job.job_id,
                            {"last_chapter_id": ch.chapter_id, "scope": "chapters"},
                            skip_payload,
                        )
                        items_processed += 1
                        continue
                    logger.warning(
                        "Retryable error on chapter %s (attempt %d/%d): %s",
                        ch.chapter_id, retries, _MAX_RETRIES_PER_ITEM, result.error,
                    )
                    # Persist retry count in cursor, don't advance past this item
                    await _advance_cursor(
                        pool, job.user_id, job.job_id,
                        {**cur, retry_key: retries, "scope": "chapters"},
                        items_delta=0,
                    )
                    return  # stop this run, retry on next poll

                # Advance cursor + emit the extraction_run in ONE transaction
                # (B2-A): the run row is guaranteed iff the cursor advanced.
                run_payload = _run_payload(
                    job=job, book_id=book_id, chapter_ref=ch.chapter_id,
                    snapshot=run_snapshot, cfg_hash=run_cfg_hash,
                    base_version=run_base_version, outcome="succeeded", result=result,
                )
                await _advance_cursor_and_emit_run(
                    pool, job.user_id, job.job_id,
                    {"last_chapter_id": ch.chapter_id, "scope": "chapters"},
                    run_payload,
                )
                # D-K16.11-01: bump per-project monthly + all-time spend
                # counters so CostSummary's GET /costs reflects reality.
                await _record_spending(
                    pool, job.user_id, job.project_id, _DEFAULT_COST_PER_ITEM,
                )
                # K19b.8: surface this success to the FE log panel.
                await _append_log(
                    pool, job.user_id, job.job_id, "info",
                    f"Chapter {ch.chapter_id} processed",
                    context={
                        "event": "chapter_processed",
                        "chapter_id": str(ch.chapter_id),
                        "entities_merged": result.entities_merged,
                        "relations_created": result.relations_created,
                    },
                )
                items_processed += 1
                logger.info(
                    "Job %s: chapter %s done (entities=%d, relations=%d)",
                    job.job_id, ch.chapter_id,
                    result.entities_merged, result.relations_created,
                )

        if pre_pending:
            for turn in pre_pending:
                status = await _refresh_job_status(pool, job.job_id)
                if status != "running":
                    logger.info("Job %s no longer running (status=%s), stopping", job.job_id, status)
                    return

                outcome = await _try_spend(
                    pool, job.user_id, job.job_id, _DEFAULT_COST_PER_ITEM,
                )
                if outcome == "not_running":
                    return
                if outcome == "auto_paused":
                    await _update_project_status(pool, job.user_id, job.project_id, "paused")
                    return

                # Chat turns don't have text in extraction_pending — the
                # worker would need to fetch from chat-service. For v1,
                # we pass empty text; loreweave_extraction.extract_pass2
                # short-circuits to empty Pass2Candidates without calling
                # the LLM, then persist-pass2 writes the source row for
                # idempotency. Will be fleshed out when chat-service
                # exposes a message-text endpoint.
                result = await _extract_and_persist(
                    knowledge_client=knowledge_client,
                    llm_client=llm_client,
                    user_id=job.user_id,
                    project_id=job.project_id,
                    source_type="chat_turn",
                    source_id=str(turn["aggregate_id"]),
                    job_id=job.job_id,
                    model_ref=job.llm_model,
                    text="",  # placeholder — needs chat-service integration
                )

                if result.error and not result.retryable:
                    await _fail_job(pool, job.user_id, job.job_id, result.error)
                    await _update_project_status(pool, job.user_id, job.project_id, "failed")
                    return

                await _mark_pending_processed(pool, job.user_id, turn["pending_id"])
                await _advance_cursor(
                    pool, job.user_id, job.job_id,
                    {"last_pending_id": str(turn["pending_id"]), "scope": "chat"},
                )
                # D-K16.11-01: same per-project accounting as the chapters
                # branch, see above.
                await _record_spending(
                    pool, job.user_id, job.project_id, _DEFAULT_COST_PER_ITEM,
                )
                items_processed += 1

        # C12c-a: glossary_sync branch. Fires for scope='glossary_sync'
        # (primary) AND the tail of scope='all'. No LLM call — each
        # entity is MERGEd into Neo4j via knowledge-service's
        # /internal/extraction/glossary-sync-entity handler (which
        # wraps the K15.11 `sync_glossary_entity_to_neo4j` helper).
        # Cost per item = 0 (see _GLOSSARY_SYNC_COST_PER_ITEM) but we
        # still run through _try_spend so pause/cancel detection stays
        # uniform across branches.
        if pre_glossary:
            for ent in pre_glossary:
                status = await _refresh_job_status(pool, job.job_id)
                if status != "running":
                    logger.info(
                        "Job %s no longer running (status=%s), stopping glossary loop",
                        job.job_id, status,
                    )
                    return

                outcome = await _try_spend(
                    pool, job.user_id, job.job_id, _GLOSSARY_SYNC_COST_PER_ITEM,
                )
                if outcome == "not_running":
                    return
                if outcome == "auto_paused":
                    # Shouldn't fire for glossary (cost=0 never crosses
                    # max_spend) but log + return defensively so the
                    # branching story stays uniform with chapters/chat.
                    logger.info("Job %s auto-paused during glossary loop", job.job_id)
                    await _append_log(
                        pool, job.user_id, job.job_id, "warning",
                        "Job auto-paused: max_spend_usd reached",
                        context={"event": "auto_paused", "scope": "glossary_sync"},
                    )
                    return

                result = await knowledge_client.glossary_sync_entity(
                    user_id=job.user_id,
                    project_id=job.project_id,
                    glossary_entity_id=ent.entity_id,
                    name=ent.name,
                    kind=ent.kind_code,
                    aliases=ent.aliases,
                    short_description=ent.short_description,
                )

                if result.error and not result.retryable:
                    await _fail_job(pool, job.user_id, job.job_id, result.error)
                    await _update_project_status(
                        pool, job.user_id, job.project_id, "failed",
                    )
                    return
                # /review-impl MED#3 — bounded retry mirroring the
                # chapters branch. Track retry count per entity in
                # the cursor; on retry_key >= _MAX_RETRIES_PER_ITEM
                # skip the entity (advance cursor past it) so a
                # flapping glossary-service can't loop indefinitely.
                if result.error and result.retryable:
                    retry_key = f"retry_glossary_{ent.entity_id}"
                    cur = job.current_cursor or {}
                    retries = cur.get(retry_key, 0) + 1
                    if retries >= _MAX_RETRIES_PER_ITEM:
                        logger.warning(
                            "Skipping glossary entity %s after %d retries: %s",
                            ent.entity_id, retries, result.error,
                        )
                        await _append_log(
                            pool, job.user_id, job.job_id, "error",
                            f"Glossary entity {ent.entity_id} skipped after {retries} retries",
                            context={
                                "event": "retry_exhausted",
                                "glossary_entity_id": ent.entity_id,
                                "retries": retries,
                                "error": result.error,
                                "scope": "glossary_sync",
                            },
                        )
                        await _advance_cursor(
                            pool, job.user_id, job.job_id,
                            {
                                "last_glossary_entity_id": ent.entity_id,
                                "scope": "glossary_sync",
                            },
                        )
                        items_processed += 1
                        continue
                    logger.warning(
                        "Retryable error on glossary entity %s (attempt %d/%d): %s",
                        ent.entity_id, retries, _MAX_RETRIES_PER_ITEM, result.error,
                    )
                    # Persist retry count; don't advance past this item;
                    # stop this run so next poll retries.
                    await _advance_cursor(
                        pool, job.user_id, job.job_id,
                        {**cur, retry_key: retries, "scope": "glossary_sync"},
                        items_delta=0,
                    )
                    return

                await _advance_cursor(
                    pool, job.user_id, job.job_id,
                    {
                        "last_glossary_entity_id": ent.entity_id,
                        "scope": "glossary_sync",
                    },
                )
                # Record zero spend — keeps the per-project ledger
                # consistent (every item advances it, glossary items
                # advance it by 0).
                await _record_spending(
                    pool, job.user_id, job.project_id,
                    _GLOSSARY_SYNC_COST_PER_ITEM,
                )
                items_processed += 1

        # All items processed — complete the job
        await _complete_job(pool, job.user_id, job.job_id)
        await _update_project_status(pool, job.user_id, job.project_id, "ready")
        logger.info(
            "Job %s completed: %d items processed this run",
            job.job_id, items_processed,
        )

    except Exception as exc:
        logger.exception("Job %s failed with unhandled error: %s", job.job_id, exc)
        await _fail_job(pool, job.user_id, job.job_id, str(exc)[:2000])
        await _update_project_status(pool, job.user_id, job.project_id, "failed")


# ── Poll loop ────────────────────────────────────────────────────────


async def poll_and_run(
    pool: asyncpg.Pool,
    knowledge_client: KnowledgeClient,
    llm_client: LLMClient,
    book_client: BookClient,
    glossary_client: GlossaryClient,
) -> int:
    """One poll cycle: find running jobs and process them.

    Returns the number of jobs processed (for logging/metrics).
    Called repeatedly by the main loop with a sleep interval.
    """
    jobs = await _get_running_jobs(pool)
    if not jobs:
        return 0

    for job in jobs:
        await process_job(
            pool, knowledge_client, llm_client, book_client, glossary_client, job,
        )

    return len(jobs)
