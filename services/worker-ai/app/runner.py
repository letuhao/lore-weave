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

import asyncio
import functools
import json
import logging
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg
from opentelemetry import trace as _ot_trace
from loreweave_jobs import JobStatus, emit_job_event_safe

from loreweave_extraction import (
    ContextBudget,
    EntityRecoveryConfig,
    PrecisionFilterConfig,
    ResolvedConfig,
    base_default_version,
    config_hash,
    extract_pass2,
    resolve_effective_config,
)
from loreweave_extraction.errors import ExtractionError
from loreweave_extraction.schema_projection import ExtractionSchema
from loreweave_llm.errors import LLMError

from app import fair_sched
from app.clients import (
    BookClient,
    ChapterInfo,
    ChatClient,
    ExtractionResult,
    GlossaryClient,
    GlossaryEntity,
    KnowledgeClient,
    ProviderRegistryClient,
)
from app.llm_client import LLMClient, set_billing_user_id, set_campaign_id
from loreweave_llm.attribution import set_public_key_attribution
from app.metrics import (
    worker_ai_extraction_reasoning_model_advised_total,
    worker_ai_extraction_zero_output_total,
)
from app.outbox_emit import (
    emit_chapter_extracted,
    emit_chapter_extracted_best_effort,
    emit_chapter_failed_best_effort,
    emit_extraction_run,
    emit_extraction_run_best_effort,
)
from app.sample_emit import persist_run_sample_best_effort

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
    # D-WX-PRECISION-FILTER-MODEL-ARCH: the filter MODEL must NOT come from a platform
    # env. A hardcoded env model_ref is cross-tenant — it was submitted as user_model
    # scoped to the CAMPAIGN's user, so provider-registry 404'd "model not found" for
    # every user who didn't own it, leaving the decoupled fold's terminal event
    # un-acked and stalling the chapter forever (D-WX live-smoke finding). The filter
    # is now configured PER-PROJECT via extraction_config.precision_filter
    # (PrecisionFilterOverride: enabled + model_ref + model_source + categories +
    # partial_policy) — FE-set, DB-stored, resolved per-user, merged onto these
    # (now model-less) global defaults in resolve_effective_config(project_overrides=).
    # There is NO global env model source. Behavior knobs without a model are
    # meaningless, so the whole global default is None.
    return None


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

# B2 follow-up — global env knob as default-for-all autocreate.
# Per-project extraction_config.writer_autocreate still supersedes this
# (resolve_effective_config merges it on top).  Setting the env var to
# "true" here makes the knob functional for projects that have no
# per-project override (the previous behaviour was always-False).
_WRITER_AUTOCREATE_DEFAULT: bool = (
    os.environ.get("KNOWLEDGE_EXTRACTION_WRITER_AUTOCREATE_ENABLED", "false").lower()
    in {"1", "true", "yes"}
)

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
    async def wrapper(pool, knowledge_client, llm_client, book_client, glossary_client, chat_client, provider_client, job):
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
                book_client, glossary_client, chat_client, provider_client, job,
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

# FD-27 — only warn about zero-output on SUBSTANTIVE input. Extraction on a
# handful of chars legitimately yielding nothing is not the silent-failure
# signal; a full chapter (thousands of chars) producing nothing is.
_MIN_INPUT_CHARS_FOR_ZERO_OUTPUT_WARN = 40

# FD-27 — best-effort reasoning-model name patterns (substring match, lowercased).
# provider-registry has NO reasoning capability flag, so this is name-based and
# WILL have false negatives on novel models — it drives an advisory WARNING, never
# a hard block. Extraction suppresses thinking via a PROMPT preamble (~95% obey),
# not a hard API param, so a reasoning model still carries elevated empty-output
# risk worth flagging.
_REASONING_MODEL_PATTERNS = (
    "deepseek-r1", "deepseek-reasoner", "qwq", "glm-z", "minimax-m1", "magistral",
    "thinking", "reasoner", "reasoning", "qwen3",
)


def _is_likely_reasoning_model(name: str | None) -> bool:
    """Best-effort: does this model NAME look like a reasoning/thinking model?
    Name heuristics only (no capability flag exists) — advisory, not a gate."""
    if not name:
        return False
    n = name.lower()
    # OpenAI o-series as a token (o1/o3/o4/o5) without matching e.g. gpt-4o.
    if re.search(r"(?:^|[^a-z0-9])o[1345](?:-|$|[^a-z0-9])", n):
        return True
    return any(p in n for p in _REASONING_MODEL_PATTERNS)

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
        "writer_autocreate": _WRITER_AUTOCREATE_DEFAULT,
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
    *, chapter_extracted: dict | None = None, skipped_delta: int = 0,
) -> None:
    """Advance the cursor + emit the extraction_run ATOMICALLY (B2-A), and — when
    `chapter_extracted` is supplied (a chapter's successful extraction) — emit the
    campaign's `knowledge.chapter_extracted` completion event in the SAME tx
    (D-CAMPAIGN-BESTEFFORT-EMIT-REDIS).

    Normal case: one transaction → the run row (and, when given, the chapter
    completion event) is guaranteed iff the cursor advanced. Folding the chapter
    event in here closes the prior silent-loss window: it was a standalone
    best-effort insert AFTER this call, so a failed insert left the cursor advanced
    with no event → the campaign stalled `dispatched` forever.

    Failure case (/review-impl MED-1): if the transaction fails (an infra blip
    on the shared knowledge DB), fall back to a plain best-effort cursor-advance
    so the job still PROGRESSES — the chapter's real work already persisted to
    Neo4j, so we must not re-extract (re-spending LLM) nor fail the job. Run
    telemetry is NEVER load-bearing; on this path we still BEST-EFFORT emit the
    chapter event (the campaign's stuck-reconcile is the backstop for residual loss)."""
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await _advance_cursor(conn, user_id, job_id, cursor, skipped_delta=skipped_delta)
                await emit_extraction_run(conn, payload)
                if chapter_extracted is not None:
                    await emit_chapter_extracted(conn, **chapter_extracted)
    except Exception:
        logger.warning(
            "transactional run-emit failed for job %s; advancing cursor "
            "best-effort (run telemetry lost for this item, non-fatal)",
            job_id, exc_info=True,
        )
        await _advance_cursor(pool, user_id, job_id, cursor, skipped_delta=skipped_delta)
        if chapter_extracted is not None:
            await emit_chapter_extracted_best_effort(pool, **chapter_extracted)


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
    run_id: str | None = None,
) -> dict:
    """Build a `knowledge.extraction_run_completed` payload for one chapter.

    `resolved_config` carries prompt IDENTITY (prompt_versions), never raw
    prompt text (DESIGN Q5). metrics come from the per-chapter ExtractionResult
    (None on skip/fail → zero counts) + the flat per-item cost estimate.

    Q4b-feed: pass `run_id` so the caller can key an extraction_run_sample by
    the SAME id that lands in the event (parity is load-bearing — the online
    judge fetches the sample by the event's run_id). Defaults to a fresh uuid4
    for the skip/fail callers that don't sample.
    """
    metrics: dict[str, Any] = {
        "entities_merged": result.entities_merged if result else 0,
        "relations_created": result.relations_created if result else 0,
        "events_merged": result.events_merged if result else 0,
        "facts_merged": result.facts_merged if result else 0,
        "cost_usd": str(_DEFAULT_COST_PER_ITEM),
    }
    return {
        "run_id": run_id or str(uuid4()),
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
        "genre": job.genre,
        # Q4b-feed — structural metadata (NOT content): tells the eval-runner
        # whether a run-sample exists to fetch, so it skips the knowledge call
        # for non-opted projects. Redact-safe (a bool, no novel text).
        "save_raw_extraction": job.save_raw_extraction,
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
    # S4a — Auto-Draft Factory cost attribution: the owning campaign (NULL for
    # user-initiated jobs). process_job binds it as a contextvar so every
    # provider job_meta carries it (see app.llm_client.set_campaign_id).
    campaign_id: UUID | None = None
    # E0-3 Phase 2a — BYOK dual-identity billing. When set (collaborator-
    # triggered extraction), provider calls (LLM + embeddings) resolve under the
    # CALLER's key + refs; graph partition (user_id) and the stored
    # embedding_model search tag stay the project owner's. NULL ⇒ owner-
    # triggered ⇒ single-identity legacy path. Use eff_billing_user / eff_llm_ref
    # / eff_embed_ref ONLY at provider-call sites — never for graph/cursor/status.
    billing_user_id: UUID | None = None
    billing_embedding_model: str | None = None
    billing_llm_model: str | None = None
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
    # E2 — user-set genre tag; copied from knowledge_projects.genre at
    # job-fetch time and forwarded into the run-completed payload so
    # extraction_runs.genre is populated for genre-segment mining.
    genre: str | None = None
    # Q4b-feed — the project's raw-retention opt-in (knowledge_projects.
    # save_raw_extraction, default OFF). When True, the chapter loop persists
    # an extraction_run_sample {run_id, items, source} for the online LLM
    # judge; when False, nothing is stored (redact-by-default).
    save_raw_extraction: bool = False
    # C12 — target-typed extraction. The subset of Pass-2 passes this job
    # runs (entities/relations/events/facts/summaries). None ⇒ all (the
    # column is NOT NULL DEFAULT all-five, so a real row always carries a
    # concrete set; None only on synthetic/test rows ⇒ treated as all).
    targets: list[str] | None = None
    # C12 — passthrough cap on parallel LLM calls. None ⇒ unbounded (current).
    concurrency_level: int | None = None
    # C13 — glossary pinning. The glossary entity ids the user pinned; the
    # runner batch-fetches their names and force-injects them into EVERY
    # extraction window's known_entities. None/empty ⇒ no pins (back-compat —
    # the column is JSONB NULL by default).
    pinned_entity_ids: list[str] | None = None
    # D-KG-WORKER-GRADED-EFFORT — the graded reasoning effort stored on the row
    # (knowledge-side clamp at mint, Wave 4). The runner reads it and threads it
    # through extract_pass2 → the SDK submit builders → the LLM input. The column
    # is NOT NULL DEFAULT 'none', so a real row always carries a concrete value;
    # the default here only covers synthetic/test rows. No re-clamp (already
    # clamped at mint — the runner is single-purpose + trusted).
    reasoning_effort: str = "none"
    # D-PMCP-WORKER-CARRIER — the public-MCP key id + per-key spend ceiling that
    # priced this extraction (kg_build_graph confirm route → extraction_jobs row).
    # The in-process attribution contextvar dies at the job-row boundary (knowledge
    # extraction is poll-based), so the carrier rides the row → resume_state →
    # process_job re-sets set_public_key_attribution before any provider call.
    # NULL ⇒ a first-party (non-public-MCP) job. spend_cap_usd is DOUBLE PRECISION
    # (float8) so asyncpg binds the float natively — see the migration note.
    mcp_key_id: str | None = None
    spend_cap_usd: float | None = None


# ── E0-3 Phase 2a — BYOK dual-identity billing resolution ────────────
#
# Use these THREE helpers at provider-call sites ONLY (LLM + embeddings). Every
# graph/cursor/status/telemetry site keeps job.user_id / job.embedding_model —
# the project owner's identity is the partition key and the canonical search
# tag, and must never be swapped for the billing identity. NULL billing fields
# ⇒ the helper returns the owner's value ⇒ the legacy single-identity path.


class BillingConfigError(Exception):
    """Fail-safe (E0-3 Phase 2a §6): a job carries billing_user_id but a billing
    ref is NULL. The worker MUST fail the job rather than silently fall back to
    the owner's key (which would charge a key its owner did not authorize)."""


def eff_billing_user(job: JobRow) -> UUID:
    """The user under whom provider calls (key + budget) resolve."""
    return job.billing_user_id or job.user_id


def eff_llm_ref(job: JobRow) -> str:
    """The LLM model_ref for the provider call (caller's when billing-set).

    Gated on billing_user_id (the IDENTITY), not on billing_llm_model alone:
    a billing ref is only meaningful paired with the billing user it resolves
    under (the contextvar that overrides submit_and_wait keys off the same
    billing_user_id). This keeps the ref and the resolving user coherent even if
    a row ever carries an orphan ref without a user (review-impl MED-1)."""
    return job.billing_llm_model if job.billing_user_id else job.llm_model


def eff_embed_ref(job: JobRow) -> str:
    """The embedding model_ref for the provider call (caller's when billing-set).
    Gated on billing_user_id (see eff_llm_ref). NOTE: the STORED passage tag
    stays job.embedding_model (the project's canonical UUID — the search
    filter), never this value."""
    return job.billing_embedding_model if job.billing_user_id else job.embedding_model


def assert_billing_complete(job: JobRow) -> None:
    """Fail-safe guard: when billing_user_id is set, BOTH billing refs must be
    present. A partial billing identity would resolve one provider call under the
    caller and the other under the owner — a BYOK breach. Raise so process_job
    fails the job before any provider call runs."""
    if job.billing_user_id is None:
        return
    missing = [
        name
        for name, val in (
            ("billing_embedding_model", job.billing_embedding_model),
            ("billing_llm_model", job.billing_llm_model),
        )
        if not val
    ]
    if missing:
        raise BillingConfigError(
            f"job {job.job_id} has billing_user_id but missing {', '.join(missing)} "
            "— refusing to fall back to the owner's key (BYOK fail-safe)"
        )


# ── DB helpers ───────────────────────────────────────────────────────


def _decode_pinned(raw: object) -> list[str] | None:
    """C13 — normalise extraction_jobs.pinned_entity_ids (JSONB). asyncpg may
    hand back a raw JSON str or an already-decoded list. NULL ⇒ None (no pins).
    A non-list / malformed value degrades to None (the job runs un-pinned rather
    than crashing the poll loop)."""
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return None
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return None


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
               j.cost_spent_usd, j.campaign_id,
               j.billing_user_id, j.billing_embedding_model, j.billing_llm_model,
               j.targets, j.concurrency_level, j.pinned_entity_ids,
               j.reasoning_effort, j.mcp_key_id, j.spend_cap_usd,
               p.embedding_dimension,
               p.extraction_config, p.genre, p.save_raw_extraction
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
            campaign_id=r["campaign_id"],
            billing_user_id=r["billing_user_id"],
            billing_embedding_model=r["billing_embedding_model"],
            billing_llm_model=r["billing_llm_model"],
            embedding_dimension=r["embedding_dimension"],
            extraction_config=ec if isinstance(ec, dict) else None,
            genre=r["genre"],
            save_raw_extraction=bool(r["save_raw_extraction"]),
            # C12 — asyncpg returns a TEXT[] as a python list already.
            targets=list(r["targets"]) if r["targets"] is not None else None,
            concurrency_level=r["concurrency_level"],
            # C13 — pinned_entity_ids is JSONB; asyncpg returns it as a str (raw
            # JSON) or a decoded list depending on the codec. Normalise both.
            pinned_entity_ids=_decode_pinned(r["pinned_entity_ids"]),
            # D-KG-WORKER-GRADED-EFFORT — TEXT NOT NULL DEFAULT 'none'; coerce a
            # stray NULL (synthetic row / pre-migration replica) to "none".
            reasoning_effort=r["reasoning_effort"] or "none",
            # D-PMCP-WORKER-CARRIER — public-MCP key + per-key cap (NULL on a
            # first-party job). spend_cap_usd is float8 → asyncpg returns a float.
            mcp_key_id=r["mcp_key_id"],
            spend_cap_usd=r["spend_cap_usd"],
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
    cursor: dict, items_delta: int = 1, skipped_delta: int = 0,
) -> None:
    """Persist progress so a restart can resume from here.

    `executor` is a Pool (default) OR an asyncpg Connection — the latter lets
    the chapter-success/skip path advance the cursor AND emit the
    extraction_run in ONE transaction (B2-A): the run row is guaranteed iff the
    cursor advanced, and an emit failure rolls back the advance (chapter
    re-processed, never a silently-missing run).

    D-WORKER-SKIP-FALSE-GREEN: `skipped_delta` counts items that advanced the
    cursor WITHOUT doing any work (text unavailable, retry-exhausted) into
    `items_skipped`, so a job whose items were all skipped no longer reads as
    an indistinguishable "complete N/N" success."""
    await executor.execute(
        """
        UPDATE extraction_jobs
        SET current_cursor = $3::jsonb,
            items_processed = items_processed + $4,
            items_skipped = items_skipped + $5,
            updated_at = now()
        WHERE user_id = $1 AND job_id = $2
          AND status IN ('running', 'paused')
        """,
        user_id, job_id, json.dumps(cursor), items_delta, skipped_delta,
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
    ex: Any, user_id: UUID, project_id: UUID, cost: Decimal,
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

    ``ex`` is a Pool (default) OR an asyncpg Connection — the latter lets the
    decoupled-extraction finalize fold the spend into the SAME tx as the
    cursor-advance + resume-clear, so a crash can't leave spend recorded with
    resume_state still present (D-WX-PERSIST-DOUBLE-SPEND)."""
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    await ex.execute(
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


#: Unified Job Control Plane P1 — extraction jobs live in the knowledge DB + outbox
#: (worker-ai shares it); the canonical JobEvent service is the domain owner, "knowledge",
#: so the projection sees ONE service for the job's whole lifecycle regardless of which
#: process (knowledge API start/cancel, worker-ai complete/fail) wrote the transition.
_JOB_SERVICE = "knowledge"
_JOB_KIND = "extraction"


async def _complete_job(pool: asyncpg.Pool, user_id: UUID, job_id: UUID) -> None:
    """Transition job to 'complete'. The conditional UPDATE only fires once (not if
    already terminal) and the RETURNING row gates the emit, so a redelivered/duplicate
    completion that no-ops the UPDATE can't emit a duplicate terminal event.

    /review-impl MED: the JobEvent emit is **best-effort** (post-commit ``_safe``), NOT
    in-tx. ``_complete_job`` is called inside ``process_job``'s try whose ``except`` marks
    the job FAILED — so an in-tx emit that raised (e.g. a transient ``outbox_events``
    INSERT blip) would roll back the completion AND derail a fully-persisted extraction
    into a false ``failed``. A terminal status is the source of truth P2's reconcile sweep
    re-derives, so a best-effort emit (status commits regardless; reconcile backstops a
    lost event) is the correct trade — the completion must never be lost to an emit error."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE extraction_jobs
            SET status = 'complete', completed_at = now(), updated_at = now(),
                -- D-WORKER-SKIP-FALSE-GREEN: a job whose EVERY item was skipped
                -- must not read as an indistinguishable success ("complete N/N"
                -- masked the _text extraction bug). Status stays 'complete'
                -- (skips are per-item terminal by design; 'failed' would trip
                -- campaign breakers), but the row now says so out loud.
                error_message = CASE
                  WHEN items_skipped > 0 AND items_total > 0 AND items_skipped >= items_total
                    THEN 'completed with ALL ' || items_total || ' items skipped — no work performed (see job logs)'
                  -- D-EXTRACTION-SILENT-NOOP: a job that PROCESSED items (not skipped) but
                  -- made ZERO LLM calls did no extraction — the LLM is what identifies
                  -- entities/relations/facts. Reporting a bare 'complete' let a silent
                  -- no-op (no graph schema kinds / provider unreachable) masquerade as a
                  -- built graph. Same convention as the skip case: status stays 'complete'
                  -- (no campaign-breaker trip) but the row says so out loud.
                  WHEN items_processed > 0 AND COALESCE(llm_calls_made, 0) = 0
                    THEN 'completed but made 0 LLM calls over ' || items_processed ||
                         ' processed item(s) — no extraction performed (no usable graph schema kinds, or the extraction provider was unreachable)'
                  ELSE error_message
                END
            WHERE user_id = $1 AND job_id = $2
              AND status NOT IN ('complete', 'cancelled', 'failed')
            RETURNING job_id, cost_spent_usd, items_skipped, items_total,
                      items_processed, COALESCE(llm_calls_made, 0) AS llm_calls_made
            """,
            user_id, job_id,
        )
        _skipped = row.get("items_skipped") if row is not None else None
        _total = row.get("items_total") if row is not None else None
        if _skipped and _total and _skipped >= _total:
            logger.warning(
                "Job %s completed but ALL %d items were skipped — no work performed",
                job_id, _total,
            )
        elif row is not None and row.get("items_processed") and not row.get("llm_calls_made"):
            # D-EXTRACTION-SILENT-NOOP — a processed-but-no-LLM completion is a silent
            # no-op; surface it loudly (the error_message above + this warning) so an
            # empty graph never reads as a successful build.
            logger.warning(
                "Job %s completed but made 0 LLM calls over %d processed item(s) — "
                "no extraction performed (check the project's graph schema kinds / the "
                "extraction provider)", job_id, row.get("items_processed"),
            )
        if row is not None:
            # P4 — carry the final cumulative cost on the terminal event (the changing
            # field); model + params were set on 'running' and kept via the projection's
            # COALESCE merge.
            _cost = row["cost_spent_usd"]
            await emit_job_event_safe(
                conn, service=_JOB_SERVICE, job_id=str(job_id),
                owner_user_id=str(user_id), kind=_JOB_KIND, status=JobStatus.COMPLETED,
                cost_usd=float(_cost) if _cost is not None else None,
            )


async def _fail_job(
    pool: asyncpg.Pool, user_id: UUID, job_id: UUID, error: str,
) -> None:
    """Transition job to 'failed' with an error message (same once-only RETURNING gate +
    best-effort post-commit emit as ``_complete_job`` — a failed-status write must commit
    regardless of an emit blip; reconcile backstops a lost event)."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE extraction_jobs
            SET status = 'failed', completed_at = now(), updated_at = now(),
                error_message = $3
            WHERE user_id = $1 AND job_id = $2
              AND status NOT IN ('complete', 'cancelled', 'failed')
            RETURNING job_id, cost_spent_usd
            """,
            user_id, job_id, error[:2000],
        )
        if row is not None:
            _cost = row["cost_spent_usd"]
            await emit_job_event_safe(
                conn, service=_JOB_SERVICE, job_id=str(job_id),
                owner_user_id=str(user_id), kind=_JOB_KIND, status=JobStatus.FAILED,
                cost_usd=float(_cost) if _cost is not None else None,
                error={"code": "extraction_failed", "message": error[:500]},
            )


async def sweep_stalled_jobs(pool: asyncpg.Pool, *, stall_minutes: int) -> int:
    """D-EXTRACTION-SILENT-NOOP gap #3 — the generic STALL backstop.

    `updated_at` is bumped on every progress step (cursor advance, items_total set,
    stage change), so a job that is still `status='running'` with `updated_at` older
    than `stall_minutes` made NO progress that whole time — its runner/provider died or
    hung mid-loop, and without this it would sit 'running' forever, looking healthy.

    Fails such jobs via `_fail_job` (so the terminal event fires and the row stops
    lying). Deliberately COMPLEMENTS the Wave-1b resume-sweeper (which only re-drives
    DECOUPLED rows with resume_state, and is off by default): `stall_minutes` is
    configured generously (> the resume timeout) so a recoverable row is re-driven
    first and a long-but-live LLM call is never wrongly failed. `stall_minutes<=0` ⇒
    disabled. Returns the number swept."""
    if stall_minutes <= 0:
        return 0
    rows = await pool.fetch(
        """
        SELECT user_id, job_id
        FROM extraction_jobs
        WHERE status = 'running'
          AND updated_at < now() - make_interval(mins => $1)
        ORDER BY updated_at ASC
        LIMIT 50
        """,
        stall_minutes,
    )
    for r in rows:
        logger.warning(
            "STALL sweep: extraction job %s made no progress for >%d min — failing it "
            "(runner/provider died or hung; re-dispatch to retry)",
            r["job_id"], stall_minutes,
        )
        await _fail_job(
            pool, r["user_id"], r["job_id"],
            f"stalled: no progress for {stall_minutes}+ min "
            "(the runner or extraction provider died/hung mid-stage) — re-dispatch to retry",
        )
    return len(rows)


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
    scope_range: dict | None = None,
) -> list[ChapterInfo]:
    """Get chapters to process, respecting cursor for resume.

    WS-0.6 — the KG-membership gate (spec 2026-07-11-publish-independent-kg-indexing
    §3.5, red-team P0-2). This REPLACES the old CM3c canon=published gate.

    The whole-book rebuild extracts the chapters the user actually put in their
    KNOWLEDGE GRAPH — not the chapters they published. Those are different sets now:
    a draft can be indexed (and a kind='diary' book never publishes at all). Filtering
    server-side on `editorial_status='published'` would enumerate ZERO of a user's 50
    explicitly-indexed drafts, and this job would report success having extracted
    nothing — the user's explicit act silently undone by an unrelated button.

    Each chapter is read at its PINNED revision (`ChapterInfo.revision_id` ←
    `kg_indexed_revision_id`). The no-pinned-revision skip is KEPT and is load-bearing:
    with `revision_id=None` the per-chapter fetch falls back to `get_chapter_text()` =
    the LIVE DRAFT, which would extract unreviewed prose and break the pinned-revision
    guarantee. It stays a WARNING, never a silent drop.
    """
    if book_id is None:
        return []
    chapters = await book_client.list_chapters(book_id, kg_indexed=True)
    if chapters is None:
        return []

    gated: list[ChapterInfo] = []
    for ch in chapters:
        if ch.revision_id is None:
            logger.warning(
                "WS-0.6: chapter %s is in the knowledge graph but has no pinned "
                "revision (kg_indexed_revision_id NULL) — skipping rather than falling "
                "back to live draft text; re-index it to pin a revision",
                ch.chapter_id,
            )
            continue
        gated.append(ch)
    chapters = gated

    # S2 (D-K16.2-02b): honour scope_range.chapter_range = [lo, hi] on sort_order
    # so a campaign/user can extract a chapter SUBSET. Until now only the cost-
    # estimate ranged (via book_client.count_chapters); the runner dropped it,
    # so the actual job processed the whole book. This aligns the two. Applied
    # BEFORE the resume-cursor filter so resume stays within the range.
    if scope_range and scope_range.get("chapter_range"):
        rng = scope_range["chapter_range"]
        if isinstance(rng, (list, tuple)) and len(rng) == 2:
            lo, hi = int(rng[0]), int(rng[1])
            chapters = [ch for ch in chapters if lo <= ch.sort_order <= hi]

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
    """Fetch unprocessed chat turn events from extraction_pending.

    Canon Model CM3b (B7): filter `aggregate_type = 'chat'` — the queue now
    also holds `chapter` rows (chapter.published), and without this filter the
    chat-scope drain would mis-consume chapter rows as empty chat turns
    (source_type='chat_message', text=''). The chapter drainer reads
    `aggregate_type='chapter'`; the two never cross.
    """
    rows = await pool.fetch(
        """
        SELECT ep.pending_id, ep.event_id, ep.event_type,
               ep.aggregate_type, ep.aggregate_id
        FROM extraction_pending ep
        JOIN knowledge_projects p
          ON p.project_id = ep.project_id AND p.user_id = $1
        WHERE ep.project_id = $2 AND ep.processed_at IS NULL
          AND ep.aggregate_type = 'chat'
          -- ── WS-1.3 · the D6 gate, ENFORCED ON BOTH SIDES (review-impl P1) ──
          -- knowledge-service's handle_chat_turn gates at ENQUEUE, but a one-sided gate
          -- is a silent-success bug (spec 09 says so explicitly, and I wrote a comment
          -- claiming both sides were covered — they were not). A row can be enqueued and
          -- THEN the project flipped to assistant, or the extraction re-run over an old
          -- row. This is the same derived predicate (fail-closed): the ASSISTANT never
          -- extracts per turn (its facts come once a day from the confirmed entry), and a
          -- project with per-turn extraction disabled is skipped. A NULL is_assistant or
          -- flag cannot pass (both are NOT NULL columns, so this reads as false-safe).
          AND p.is_assistant = false
          AND p.chat_turn_extraction_enabled = true
        ORDER BY ep.created_at ASC
        LIMIT 1000
        """,
        user_id, project_id,
    )
    return [dict(r) for r in rows]


async def _mark_pending_processed(
    pool: asyncpg.Pool, user_id: UUID, pending_id: UUID,
    *, revision_id: str | None = None,
) -> None:
    """Mark a pending event as processed.

    CM3b /review-impl MED-1 (re-publish-during-drain race): when `revision_id`
    is given (chapter drain), mark ONLY if the row STILL pins that revision. If
    a re-publish reset the row to a new revision (`upsert_chapter_pending` sets
    revision_id=NEW, processed_at=NULL) while this drain was extracting the OLD
    one, the match fails (0 rows) → the row stays unprocessed at NEW → re-drained
    at the latest revision (instead of being marked done at the stale revision).
    """
    await pool.execute(
        """
        UPDATE extraction_pending ep
        SET processed_at = now()
        FROM knowledge_projects p
        WHERE ep.pending_id = $2
          AND ep.processed_at IS NULL
          AND ($3::uuid IS NULL OR ep.revision_id = $3)
          AND p.project_id = ep.project_id
          AND p.user_id = $1
        """,
        user_id, pending_id, revision_id,
    )


async def _enumerate_pending_chapters(
    pool: asyncpg.Pool, user_id: UUID, project_id: UUID,
) -> list[ChapterInfo]:
    """Canon Model CM3b — chapters queued by chapter.published, to extract at
    their PINNED published revision. `aggregate_type='chapter'` keeps this
    disjoint from the chat drain (B7). Each row → ChapterInfo carrying
    revision_id + pending_id so the loop fetches revision text (not the live
    draft) and marks the row processed afterward.
    """
    rows = await pool.fetch(
        """
        SELECT ep.pending_id, ep.aggregate_id, ep.revision_id
        FROM extraction_pending ep
        JOIN knowledge_projects p
          ON p.project_id = ep.project_id AND p.user_id = $1
        WHERE ep.project_id = $2 AND ep.processed_at IS NULL
          AND ep.aggregate_type = 'chapter'
        ORDER BY ep.created_at ASC
        LIMIT 1000
        """,
        user_id, project_id,
    )
    out: list[ChapterInfo] = []
    for r in rows:
        if r["revision_id"] is None:
            # A pending chapter row without a pinned revision (legacy/malformed)
            # — skip rather than fall back to the live draft, which would
            # violate canon=published. Mark it processed so it doesn't re-loop.
            logger.warning(
                "CM3b: pending chapter %s has no revision_id — skipping + marking",
                r["aggregate_id"],
            )
            await _mark_pending_processed(pool, user_id, r["pending_id"])
            continue
        out.append(
            ChapterInfo(
                chapter_id=str(r["aggregate_id"]),
                title="",
                sort_order=0,
                revision_id=str(r["revision_id"]),
                pending_id=r["pending_id"],
            )
        )
    return out


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
    # L7 (Milestone B) — the project's ADVISORY extraction schema, resolved once
    # per job. Threaded into extract_pass2 so the LLM emits the project's vocab.
    # None ⇒ static prompt. allow_free_edges is forced True server-side, so the
    # SDK never pre-drops — /persist-pass2 stays the sole enforce+park point.
    schema: ExtractionSchema | None = None,
    # B2 follow-up — per-project Pass2-writer autocreate override (forwarded to
    # /persist-pass2). None = chat/glossary callers leave the env default.
    writer_autocreate: bool | None = None,
    # P3 D-P3-EXTRACTION-CALLER-WIRE-UP — all optional. Caller (chapter
    # branch) supplies these to opt into hierarchy MERGE + summary
    # enqueue. chat_turn branch keeps the legacy behaviour.
    hierarchy_paths: dict | None = None,
    # FD-4 (066 fix): chapter reading-order ordinal (sort_order), threaded
    # independent of hierarchy_paths so a flat book (no part) still gets a
    # dense event_order → status_effects/timeline aren't silently dropped.
    chapter_index: int | None = None,
    book_parts: list[tuple[str, str, str]] | None = None,
    is_last_chapter_of_book: bool = False,
    embedding_model_uuid: str | None = None,
    embedding_dimension: int | None = None,
    # E0-3 Phase 2a-2 — BYOK billing identity forwarded onto the summary
    # pipeline enqueued by /persist-pass2 (None ⇒ owner-triggered/legacy).
    billing_user_id: str | None = None,
    billing_llm_model: str | None = None,
    billing_embedding_model: str | None = None,
    # C12 — target-typed extraction. None ⇒ all passes (chat_turn / glossary
    # callers omit it → full extraction, unchanged). A concrete list runs only
    # the requested SDK passes; `summaries` is stripped before the SDK (it's
    # an orchestrator op, gated on the persist side instead).
    targets: list[str] | None = None,
    # C12 — cap on parallel LLM calls in the SDK R/E/F gather. None ⇒ unbounded.
    concurrency_level: int | None = None,
    # C13 — pinned glossary names force-injected into THIS window's
    # known_entities (replaces the legacy hardcoded []). None ⇒ [] (back-compat:
    # chat_turn / glossary callers leave it unset → no pins).
    pinned_names: list[str] | None = None,
    # D-KG-WORKER-GRADED-EFFORT — the job's graded reasoning effort, threaded
    # into the SDK's core extraction LLM calls. Default "none" ⇒ no reasoning
    # wire fields (chat_turn / glossary callers omit it → unchanged).
    reasoning_effort: str = "none",
    # bug #34 — optional immediate-cancel hook threaded into extract_pass2 so an
    # in-flight extraction LLM call is aborted the moment the KG-build job is
    # cancelled. None (default) ⇒ no cancellation polling (back-compat).
    cancel_check: "Callable[[], Awaitable[bool]] | None" = None,
    # Model-context-aware chunk sizing. None (default — chat_turn/glossary
    # callers) keeps the legacy flat 15-paragraph chunk size. The chapter branch
    # resolves the target model's real context window via ProviderRegistryClient
    # and passes a ContextBudget so chunk size scales with the model in use.
    context_budget: "ContextBudget | None" = None,
) -> tuple[ExtractionResult, "Pass2Candidates | None"]:
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

    Q4b-feed: also returns the in-memory `Pass2Candidates` (or None on the
    LLM-error path) so the chapter loop can persist a run-sample for the
    online judge — the ONLY place run_id + items + source coexist. The
    returned `ExtractionResult` stays counts-only (the event/telemetry shape).

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
    # C12 — the SDK target set. None ⇒ None (SDK runs all). A concrete list is
    # passed straight through; the SDK ignores `summaries` (orchestrator op) and
    # auto-includes `entities` for dependent targets. `summaries` is honoured by
    # persist-pass2's enqueue gate (via the `targets` field below), NOT here.
    sdk_targets = set(targets) if targets else None
    try:
        candidates = await extract_pass2(
            text=text,
            # C13 — force-inject the pinned glossary names. Replaces the legacy
            # hardcoded [] ("worker-ai has no glossary access"). None ⇒ [].
            known_entities=list(pinned_names or []),
            user_id=str(user_id),
            project_id=str(project_id) if project_id else None,
            model_source="user_model",
            model_ref=model_ref,
            llm_client=llm_client,
            # C12 — gate which Pass-2 passes run (None ⇒ all) + cap parallelism.
            targets=sdk_targets,
            concurrency_level=concurrency_level,
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
            # L7 (Milestone B) — advisory project schema (None ⇒ static prompt).
            schema=schema,
            # D-KG-WORKER-GRADED-EFFORT — graded effort → core extraction LLM
            # calls ("none" ⇒ no wire fields; recovery/filter stay force-off).
            reasoning_effort=reasoning_effort,
            # bug #34 — immediate-cancel hook → core extraction submit_and_wait
            # calls so an in-flight LLM call aborts on job cancellation.
            cancel_check=cancel_check,
            context_budget=context_budget,
        )
    except ExtractionError as exc:
        retryable = exc.stage == "provider_exhausted"
        # S3c-2b: surface the underlying LLM error code (LLM_CIRCUIT_OPEN) from
        # the chained cause so the runner can signal a circuit-open for campaign
        # auto-pause. ExtractionError itself has no `.code`; it's on last_error.
        error_code = getattr(exc.last_error, "code", None)
        logger.warning(
            "extract_pass2 failed source_id=%s stage=%s retryable=%s code=%s: %s",
            source_id, exc.stage, retryable, error_code, exc,
        )
        return ExtractionResult(
            source_id=source_id,
            entities_merged=0,
            relations_created=0,
            events_merged=0,
            facts_merged=0,
            retryable=retryable,
            error=f"extraction failed (stage={exc.stage}): {exc}",
            error_code=error_code,
        ), None

    # FD-27 — silent zero-output guard. Non-empty (substantive) input that the
    # LLM turned into ZERO candidates is the "extraction did nothing" symptom —
    # dominant cause is a reasoning model swallowing the JSON in reasoning
    # tokens, but cause-agnostic. Observability only (warn + metric); the empty
    # persist below still writes the source row for idempotency.
    if len(text.strip()) >= _MIN_INPUT_CHARS_FOR_ZERO_OUTPUT_WARN and candidates.is_empty():
        logger.warning(
            "EXTRACTION_ZERO_OUTPUT source_type=%s source_id=%s: non-empty input "
            "(%d chars) produced 0 candidates — if using a reasoning model, set "
            "reasoning_effort=none / disable thinking (output may be swallowed by "
            "reasoning tokens).",
            source_type, source_id, len(text),
        )
        worker_ai_extraction_zero_output_total.labels(source_type=source_type).inc()

    persist_result = await knowledge_client.persist_pass2(
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
        chapter_index=chapter_index,  # FD-4 (066) — event_order for flat books
        book_parts=book_parts,
        is_last_chapter_of_book=is_last_chapter_of_book,
        embedding_model_uuid=embedding_model_uuid,
        embedding_dimension=embedding_dimension,
        writer_autocreate=writer_autocreate,
        billing_user_id=billing_user_id,
        billing_llm_model=billing_llm_model,
        billing_embedding_model=billing_embedding_model,
        # C12 — forward the target set so persist-pass2 gates the summary
        # enqueue on `summaries ∈ targets` (None ⇒ all ⇒ enqueue, back-compat).
        targets=targets,
    )
    return persist_result, candidates


def _decouple_enabled() -> bool:
    """WX-T3b flag, read from the env (runner.py uses os.environ, not the pydantic
    settings object — matches the same EXTRACTION_DECOUPLE_ENABLED that app.main's
    settings.extraction_decouple_enabled reads, so worker + consumer stay coherent)."""
    return os.environ.get("EXTRACTION_DECOUPLE_ENABLED", "").strip().lower() in ("1", "true", "yes")


async def _start_decoupled_chunk(
    pool: asyncpg.Pool, llm_client: LLMClient, *,
    job: "JobRow", ch, text: str, book_id, run_snapshot, run_cfg_hash: str,
    run_base_version: str, p3_hierarchy_paths, p3_chapter_index,
    p3_book_parts, p3_is_last: bool,
    # C13 — pinned glossary names to force-inject into this chunk's
    # known_entities. [] ⇒ no pins (back-compat).
    pinned_names: list[str] | None = None,
    # P5 — the WFQ lease token acquired for this chunk (None when P5 off). Stashed in
    # resume_state so the decoupled consumer can release the exact slot at the chunk
    # terminal; released here on submit-failure (no chunk ends up in flight).
    p5_token: str | None = None,
    # L7 (Milestone B) — the project's ADVISORY extraction schema (None ⇒ static
    # prompt). Stashed in resume_state so the consumer rebuilds it for build_*_system.
    extraction_schema: ExtractionSchema | None = None,
    # Model-context-aware chunk sizing — resolves the target model's real context
    # window so the entity/trio submits (assembled later by decoupled_extract.py,
    # possibly after a process restart) can build a ContextBudget instead of
    # assuming a flat window. None (only in tests that don't wire a client) ⇒ the
    # resolution is skipped and chunk size falls back to the SDK's legacy default.
    provider_client: "ProviderRegistryClient | None" = None,
) -> None:
    """WX-T3b — seed resume_state for one chapter + submit its entity job, then
    return (released). The llm_extract_consumer folds the terminal events through
    entity→trio→persist. The full per-chapter persist + cursor + spend context is
    serialized into resume_state so the consumer (which only sees a job_id) can
    finalize without the loop locals. run_payload is pre-built here (metrics zeroed —
    the consumer fills counts from the persist result). Campaign + BYOK attribution
    flow through the contextvars process_job already bound (submit_job stamps them)."""
    from app import decoupled_extract as dx

    eff_model_ref = job.billing_llm_model if job.billing_user_id else run_snapshot.model_ref
    # Resolved ONCE here (not re-fetched on every fold) and stashed into resume_state
    # alongside model_ref — decoupled_extract.py's assemble_* functions are pure
    # (no I/O) and read it back to build a ContextBudget per submit.
    context_length = (
        await provider_client.get_context_length("user_model", str(eff_model_ref))
        if provider_client is not None else None
    )
    # WX Wave 4 — recovery/filter are now decoupled fan-out stages (no sync fallback).
    eff_recovery = run_snapshot.entity_recovery
    eff_filter = run_snapshot.precision_filter
    # C12 LOCK — recovery/precision-filter auto-disable when `entities` was not
    # explicitly requested (they refine the canonical entity set; pointless on
    # an R/E/F-only build where entities run only as anchors). None/empty
    # targets ⇒ entities requested ⇒ enabled (back-compat).
    entities_requested = (not job.targets) or ("entities" in job.targets)
    rs = dx.new_extract_state(
        # C13 — force-inject the pinned glossary names into THIS chunk's
        # known_entities (the decoupled consumer threads it into the entity +
        # R/E/F extractor calls). Replaces the legacy hardcoded []. None ⇒ [].
        chunk_text=text, known_entities=list(pinned_names or []),
        has_recovery=(eff_recovery is not None) and entities_requested,
        has_filter=(eff_filter is not None) and entities_requested,
        # C12 — the job's pass subset; reduced to the requested trio ops.
        targets=job.targets,
    )
    # C13 — per-window proof that the pinned names reach THIS chapter's
    # known_entities even when the chapter text never mentions them. Silent when
    # nothing is pinned (the common case). Load-bearing for the live-smoke.
    if pinned_names:
        logger.info(
            "C13 pinned-injection: chapter %s (idx=%s) known_entities <- %s",
            ch.chapter_id, p3_chapter_index, pinned_names,
        )
    rs.update(
        user_id=str(job.user_id), project_id=str(job.project_id),
        model_source="user_model", model_ref=str(eff_model_ref),
        # Model-context-aware chunk sizing — stashed alongside model_ref so
        # decoupled_extract.py's assemble_* functions build a ContextBudget on
        # both the initial submit AND resume (a process restart never re-resolves
        # it, matching the reasoning_effort stash pattern below). None ⇒ the SDK
        # falls back to its legacy flat chunk size — never guessed here.
        context_length=context_length,
        # D-KG-WORKER-GRADED-EFFORT — stash the job's graded effort in
        # resume_state alongside model_ref so the decoupled consumer rebuilds the
        # entity + trio submits with the SAME effort on resume. Missing it here
        # would silently drop graded effort on the async/resume path.
        reasoning_effort=job.reasoning_effort,
        prompt_overrides=run_snapshot.prompts or {},
        # C12 (D-C12-CONCURRENCY-DECOUPLED) — carry the job's cap on parallel
        # LLM calls into the decoupled state so the consumer bounds the trio /
        # recovery / filter submit fan-outs (an asyncio.Semaphore in
        # _submit_map). None ⇒ unbounded (back-compat with the sync gather).
        concurrency_level=job.concurrency_level,
        campaign_id=(str(job.campaign_id) if job.campaign_id else None),
        billing_user_id=(str(job.billing_user_id) if job.billing_user_id else None),
        # D-PMCP-WORKER-CARRIER: seed the public-MCP key + cap so the decoupled
        # terminal-event consumer re-sets the attribution contextvar on resume
        # (parity with billing_user_id; both ride resume_state across the process hop).
        mcp_key_id=job.mcp_key_id,
        spend_cap_usd=job.spend_cap_usd,
        # D-WX-RUN-SAMPLE-DECOUPLE — the project's raw-retention opt-in, seeded so
        # the consumer's terminal persist can write the extraction_run_sample at
        # parity with the sync chapter loop (keyed by run_payload's run_id).
        save_raw_extraction=bool(job.save_raw_extraction),
        persist_ctx={
            "source_type": "chapter", "source_id": str(ch.chapter_id),
            "job_id": str(job.job_id), "project_id": str(job.project_id),
            "extraction_model": str(eff_model_ref),
            "hierarchy_paths": p3_hierarchy_paths, "chapter_index": p3_chapter_index,
            "book_parts": p3_book_parts, "is_last_chapter_of_book": p3_is_last,
            "embedding_model_uuid": (job.embedding_model if p3_hierarchy_paths else None),
            "embedding_dimension": (job.embedding_dimension if p3_hierarchy_paths else None),
            "writer_autocreate": run_snapshot.writer_autocreate,
            "billing_user_id": (str(job.billing_user_id) if job.billing_user_id else None),
            "billing_llm_model": job.billing_llm_model,
            "billing_embedding_model": job.billing_embedding_model,
            # C12 — the job's pass subset, forwarded so the decoupled persist
            # gates the summary enqueue on `summaries ∈ targets` (None ⇒ all).
            "targets": job.targets,
        },
        run_payload=_run_payload(
            job=job, book_id=book_id, chapter_ref=ch.chapter_id, snapshot=run_snapshot,
            cfg_hash=run_cfg_hash, base_version=run_base_version,
            outcome="succeeded", result=None,
        ),
        chapter_extracted={
            "user_id": str(job.user_id), "project_id": str(job.project_id),
            "book_id": str(book_id) if book_id else None,
            "chapter_id": str(ch.chapter_id),
        },
        cursor_to_set={"last_chapter_id": str(ch.chapter_id), "scope": "chapters"},
    )
    # P5 — carry the WFQ lease token in resume_state so the consumer's terminal finalize
    # (_persist_chunk) releases the exact slot this chunk leased. Absent when P5 is off.
    if p5_token:
        rs["_p5_tok"] = p5_token
    # WX Wave 4 — serialize the recovery/filter configs into resume_state so the consumer
    # (which only sees a job_id) can drive the Tier-3 + category×batch fan-outs over the
    # WX-T2c seams. worker-ai has no glossary access ⇒ known_entity_kinds is empty ⇒ all
    # unmatched names go to the Tier-3 LLM classifier (matches the sync path there).
    if eff_recovery is not None:
        rs["_recovery_cfg"] = {
            "model_ref": eff_recovery.model_ref,
            "model_source": eff_recovery.model_source,
            "max_items_per_batch": eff_recovery.max_items_per_batch,
            "transient_retry_budget": eff_recovery.transient_retry_budget,
            "known_entity_kinds": dict(eff_recovery.known_entity_kinds),
        }
    if eff_filter is not None:
        rs["_filter_cfg"] = {
            "model_ref": eff_filter.model_ref,
            "model_source": eff_filter.model_source,
            "partial_policy": eff_filter.partial_policy,
            "categories": list(eff_filter.categories),
            "max_items_per_batch": eff_filter.max_items_per_batch,
            "transient_retry_budget": eff_filter.transient_retry_budget,
        }
    # L7 (Milestone B) — stash the advisory schema projection so the consumer
    # rebuilds it for build_*_system (vocab hint in the prompt). allow_free_edges
    # is True (advisory) → never pre-drops; /persist-pass2 stays the enforce+park
    # point. Absent when the project has no resolved schema.
    if extraction_schema is not None:
        rs["_schema"] = {
            "entity_kinds": list(extraction_schema.entity_kinds),
            "edge_predicates": list(extraction_schema.edge_predicates),
            "event_kinds": list(extraction_schema.event_kinds),
            "fact_types": list(extraction_schema.fact_types),
            "allow_free_edges": extraction_schema.allow_free_edges,
            "label": extraction_schema.label,
            "schema_version": extraction_schema.schema_version,
        }
    # Bounded transient-retry on the entity submit — mirrors submit_and_wait's
    # resilience. A fire-and-forget submit_job has no retry, so without this a single
    # transient transport blip to provider-registry would PERMANENTLY fail the job
    # (worse than the sync path). Genuine provider-down (all attempts fail) → raise →
    # the job fails → the poll / campaign reconcile re-dispatches.
    entity_kwargs = dx.assemble_entity_submit(rs)
    submit = None
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            submit = await llm_client.submit_job(user_id=str(job.user_id), **entity_kwargs)
            break
        except LLMError as exc:
            last_exc = exc
            logger.warning(
                "decoupled entity submit attempt %d/3 failed (transient?) chapter=%s: %s",
                attempt + 1, ch.chapter_id, exc,
            )
            await asyncio.sleep(1.0 * (attempt + 1))
    if submit is None:
        # P5 — the chunk never went in flight; free the slot now (the consumer will never
        # see this chunk, so it can't release it). The job then fails via the caller's
        # outer except. No-op when P5 off / token None.
        await fair_sched.release_chunk(job.user_id, p5_token)
        raise last_exc if last_exc else RuntimeError("decoupled entity submit failed")
    await pool.execute(
        """UPDATE extraction_jobs
           SET resume_state=$2::jsonb, provider_job_ids=$3::jsonb, pipeline_stage=$4,
               -- bug #37 — count the entity submit (the chunk's first LLM call); the
               -- consumer's _submit_map bumps the trio/recovery/filter fan-outs.
               llm_calls_made = llm_calls_made + 1,
               updated_at=now()
           WHERE job_id=$1""",
        job.job_id, json.dumps(rs), json.dumps([str(submit.job_id)]), rs["stage"],
    )


# ── Core job processing ─────────────────────────────────────────────


@_with_job_span
async def process_job(
    pool: asyncpg.Pool,
    knowledge_client: KnowledgeClient,
    llm_client: LLMClient,
    book_client: BookClient,
    glossary_client: GlossaryClient,
    chat_client: ChatClient,
    provider_client: ProviderRegistryClient,
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

    # S4a: bind the owning campaign (or clear it) for this job's task before any
    # extraction LLM call, so every provider job submitted while processing this
    # job carries campaign_id in its job_meta. process_job runs as its own task
    # per job (poll_and_run), so the ContextVar is task-local — concurrent jobs
    # for different campaigns never cross-contaminate.
    set_campaign_id(str(job.campaign_id) if job.campaign_id else None)
    # D-PMCP-WORKER-CARRIER: bind the public-MCP key + cap for THIS job task so every
    # provider call made while extracting tags job_meta with the agent's key (the
    # in-process contextvar set at the kg confirm route died at the job-row boundary;
    # knowledge extraction is poll-based, so the id rides the row). task-local, like
    # campaign_id; None ⇒ first-party job.
    set_public_key_attribution(job.mcp_key_id, job.spend_cap_usd)

    # bug #34 — immediate-cancel hook for in-flight extraction LLM calls.
    # Polled by loreweave_llm.Client.wait_terminal (threaded down via
    # extract_pass2) so a cancelled KG-build job aborts its current LLM call
    # at once, rather than only between items via _refresh_job_status. Mirrors
    # _refresh_job_status's query/acquire idiom. FAIL-SOFT: any read error
    # returns False so a transient DB blip never spuriously cancels healthy work.
    async def cancel_check() -> bool:
        try:
            status = await pool.fetchval(
                "SELECT status FROM extraction_jobs WHERE job_id = $1",
                job.job_id,
            )
        except Exception:
            return False
        return status == "cancelled"

    # LLM re-arch Phase 2b WX-T3b — decoupled-extraction in-flight guard. If a chunk
    # is already in flight (the llm_extract_consumer is driving it off terminal
    # events), do NOT re-enter: the consumer advances the cursor + clears
    # resume_state when the chunk persists, and the next poll picks up the FOLLOWING
    # chapter. Without this, the poll loop would re-submit the in-flight chapter every
    # cycle. (Flag off ⇒ resume_state is always NULL ⇒ this never fires.)
    if _decouple_enabled():
        _inflight = await pool.fetchval(
            "SELECT resume_state IS NOT NULL FROM extraction_jobs WHERE job_id=$1",
            job.job_id,
        )
        if _inflight:
            logger.debug("Job %s: a chunk is in-flight (decoupled) — consumer driving; skip poll", job.job_id)
            return

    # FD-27 — reasoning-model advisory (once per job, best-effort). A reasoning
    # model used for extraction risks empty output (thinking suppression is a
    # ~95% prompt preamble, not a hard guarantee). None model name (lookup
    # failed / non-user_model) → silently skip; never blocks the job.
    # Gated to scopes that actually run LLM extraction — `glossary_sync` is a
    # pure Neo4j MERGE (no LLM), so the model's reasoning-ness is irrelevant and
    # warning there would be a false advisory (/review-impl MED).
    try:
        if job.scope != "glossary_sync":
            model_name = await provider_client.get_model_name("user_model", job.llm_model)
        else:
            model_name = None
        if _is_likely_reasoning_model(model_name):
            logger.warning(
                "EXTRACTION_REASONING_MODEL job=%s model=%s looks like a reasoning "
                "model — extraction reliability depends on prompt-level thinking "
                "suppression (~95%%); prefer a non-reasoning model or "
                "reasoning_effort=none for extraction.",
                job.job_id, model_name,
            )
            worker_ai_extraction_reasoning_model_advised_total.inc()
    except Exception:
        logger.debug("FD-27 reasoning-model advisory skipped (non-fatal)", exc_info=True)

    items_processed = 0
    try:
        # E0-3 Phase 2a (BYOK caller-pays): inside the try so the fail-safe
        # fails the JOB (not the poll loop). assert FIRST — a job with a partial
        # billing identity must never run (it would resolve one provider call
        # under the caller and the other under the owner). Then bind the billing
        # user so every LLM provider call on this task resolves under the
        # collaborator's key + budget (task-local, like campaign_id). None ⇒
        # owner-triggered ⇒ legacy single-identity path.
        assert_billing_complete(job)
        set_billing_user_id(str(job.billing_user_id) if job.billing_user_id else None)

        # Resolve book_id from project (project_id ≠ book_id)
        book_id = await _get_project_book_id(pool, job.user_id, job.project_id)

        # C13 — glossary pinning. Resolve the pinned glossary entity NAMES ONCE
        # per job (not per chapter) and force-inject them into EVERY extraction
        # window's known_entities below, so sparse-but-critical entities stay
        # anchored even in chapters that never mention them. Reuses the existing
        # X-Internal-Token GlossaryClient (no new secret). Best-effort: a
        # glossary outage / no book_id → [] → the job runs un-pinned, never
        # blocks. THE GAP this cycle closes: the runner previously passed an
        # empty known_entities ("worker-ai has no glossary access").
        pinned_names: list[str] = []
        if job.pinned_entity_ids and book_id is not None:
            pinned_names = await glossary_client.fetch_entities_by_ids(
                book_id, job.pinned_entity_ids,
            )
            logger.info(
                "Job %s: C13 pinning — %d pinned id(s) resolved to %d name(s)",
                job.job_id, len(job.pinned_entity_ids), len(pinned_names),
            )

        # B2-A — pin the effective config snapshot ONCE per job (a mid-job
        # filter reload won't change this job's config_hash). Used for the
        # per-chapter extraction_run telemetry; behaviour is unchanged because
        # extract_pass2 still reads the module globals in B2-A (B2-B wires the
        # snapshot into the pipeline).
        run_snapshot, run_cfg_hash, run_base_version = _build_run_config(job)

        # L7 (Milestone B) — resolve the project's ADVISORY extraction schema ONCE
        # per job (pinned like the config snapshot). Threaded into extract_pass2 so
        # the LLM emits the project's vocab. None (no project / resolve failure /
        # un-adopted → general@v1 with no custom vocab) ⇒ static prompt. The
        # writer (/persist-pass2) resolves the AUTHORITATIVE schema server-side and
        # stays the sole closed-set enforce+park point — so this advisory copy
        # never pre-drops an off-schema edge (the R3 reconciliation).
        extraction_schema = await knowledge_client.resolve_extraction_schema(
            user_id=job.user_id, project_id=job.project_id,
        )

        # Pre-enumerate items. Done once — the results are reused for
        # both K16.7 items_total counting and the main processing loop,
        # avoiding a second HTTP call to book-service.
        pre_chapters: list[ChapterInfo] | None = None
        pre_pending: list[dict] | None = None
        pre_glossary: list[GlossaryEntity] | None = None
        glossary_enumeration_complete: bool = True

        if job.scope in ("chapters", "all"):
            pre_chapters = await _enumerate_chapters(
                book_client, book_id, job.current_cursor, job.scope_range,
            )
        # Canon Model CM3b — coalescing drainer: extract the chapters queued by
        # chapter.published, each at its PINNED revision. Shares the per-chapter
        # loop below (text-fetch + mark branch on ch.revision_id/pending_id).
        if job.scope == "chapters_pending":
            pre_chapters = await _enumerate_pending_chapters(
                pool, job.user_id, job.project_id,
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

                # P5 WFQ — gate this owner's next in-flight decoupled chunk BEFORE reserving
                # cost (a deferred chunk must not inflate cost_spent_usd). Only the decoupled
                # chapters path holds a cross-poll lease (released by the consumer at the
                # chunk terminal — that's what bounds real in-flight LLM concurrency per
                # owner). At cap ⇒ defer the whole chunk to a later poll; the slot frees when
                # an in-flight chunk finalizes. P5 off ⇒ (True, None) ⇒ proceeds un-capped.
                _p5_decoupled = _decouple_enabled() and job.scope in ("chapters", "all")
                _p5_token: str | None = None
                if _p5_decoupled:
                    _p5_allowed, _p5_token = await fair_sched.try_acquire_chunk(job.user_id)
                    if not _p5_allowed:
                        logger.info(
                            "Job %s: owner %s at P5 cap — deferring next chunk to a later poll",
                            job.job_id, job.user_id,
                        )
                        return

                # Atomic cost reservation
                outcome = await _try_spend(
                    pool, job.user_id, job.job_id, _DEFAULT_COST_PER_ITEM,
                )
                if outcome == "not_running":
                    logger.info("Job %s try_spend returned not_running, stopping", job.job_id)
                    await fair_sched.release_chunk(job.user_id, _p5_token)
                    return
                if outcome == "auto_paused":
                    logger.info("Job %s auto-paused by budget cap", job.job_id)
                    await fair_sched.release_chunk(job.user_id, _p5_token)
                    await _append_log(
                        pool, job.user_id, job.job_id, "warning",
                        "Job auto-paused: max_spend_usd reached",
                        context={"event": "auto_paused", "scope": "chapters"},
                    )
                    await _update_project_status(pool, job.user_id, job.project_id, "paused")
                    return

                # Get chapter text. CM3b: chapters_pending drains the PINNED
                # PUBLISHED revision (canon = published); the normal path uses
                # the live-draft text.
                if ch.revision_id is not None:
                    text = await book_client.get_chapter_revision_text(
                        book_id, ch.chapter_id, ch.revision_id,
                    )
                else:
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
                    # D-CM3B-DEAD-REVISION-LOOP: for a chapters_pending drain, a
                    # None text means the PINNED revision is permanently gone (404 —
                    # the client RAISES on transient errors, so this isn't a blip).
                    # Mark the pending row processed (revision-guarded) so it stops
                    # re-arming a fresh drain job on every poll. Without this, an
                    # orphaned pending row (deleted chapter/revision) loops forever,
                    # emitting a skipped extraction_run each ~poll. A future
                    # re-publish re-arms the row at a NEW revision_id.
                    if ch.pending_id is not None:
                        await _mark_pending_processed(
                            pool, job.user_id, ch.pending_id, revision_id=ch.revision_id,
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
                        skipped_delta=1,  # D-WORKER-SKIP-FALSE-GREEN
                    )
                    # P5 — this chapter did no LLM work; free its slot before the next
                    # iteration (which re-acquires). No-op when P5 off / token None.
                    await fair_sched.release_chunk(job.user_id, _p5_token)
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
                # FD-4 (066 fix): capture the chapter's reading-order ordinal
                # INDEPENDENT of the part gate below. hierarchy.chapter_index is
                # the book-service sort_order and is present even for a flat book
                # (no part); without threading it, no-part books got
                # event_order=None → status_effects + timeline silently dropped.
                p3_chapter_index: int | None = (
                    hierarchy.chapter_index if hierarchy is not None else None
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
                    # CM3c (R2-BLOCK#1): only a genuine whole-book pass
                    # ('chapters'/'all') may assert is_last. The
                    # 'chapters_pending' drain processes a COALESCED SUBSET of
                    # re-published chapters, so its tail is NOT the book tail —
                    # asserting is_last there would spuriously re-roll the
                    # whole-book L0 summary on every incremental re-publish.
                    p3_is_last = (
                        job.scope in ("chapters", "all")
                        and ch.chapter_id == pre_chapters[-1].chapter_id
                    )
                elif (not job.targets) or ("summaries" in job.targets):
                    # D-KG-SUMMARIES-TARGET-NOOP — de-silence the skip: a
                    # requested summary pass built NO p3_hierarchy_paths, so no
                    # chapter summary will enqueue. Book-service now synthesizes
                    # an implicit part for undecomposed chapters, so the usual
                    # remaining cause is a project with no embedding model
                    # (embedding_dimension None) or a hierarchy fetch failure —
                    # both were previously invisible ([[silent-success-is-a-bug]]).
                    logger.warning(
                        "summary enqueue SKIPPED chapter=%s book=%s: "
                        "hierarchy_present=%s chapter_path_present=%s "
                        "embedding_dimension=%s — no chapter summary generated",
                        ch.chapter_id, book_id,
                        hierarchy is not None,
                        (hierarchy is not None and hierarchy.chapter_path is not None),
                        job.embedding_dimension,
                    )

                # LLM re-arch Phase 2b WX-T3b — event-driven decouple of the chapter
                # extraction. Submit the entity job + RELEASE (return); the
                # llm_extract_consumer drives entity→trio→[recovery]→[filter]→persist off
                # the terminal events and advances the cursor + emits chapter_extracted.
                # WX Wave 4 — recovery/filter are now decoupled fan-out stages too, so the
                # branch is no longer gated to projects without them (the prior gate is
                # dropped). The next poll (resume_state cleared by the consumer) handles
                # the next chapter.
                if (
                    _decouple_enabled()
                    and job.scope in ("chapters", "all")
                ):
                    await _start_decoupled_chunk(
                        pool, llm_client, job=job, ch=ch, text=text, book_id=book_id,
                        run_snapshot=run_snapshot, run_cfg_hash=run_cfg_hash,
                        run_base_version=run_base_version,
                        p3_hierarchy_paths=p3_hierarchy_paths,
                        p3_chapter_index=p3_chapter_index,
                        p3_book_parts=p3_book_parts, p3_is_last=p3_is_last,
                        # C13 — pinned names resolved once per job above.
                        pinned_names=pinned_names,
                        # P5 — the WFQ lease for this chunk; stashed in resume_state so the
                        # consumer releases it at the chunk terminal. None when P5 off.
                        p5_token=_p5_token,
                        # L7 (Milestone B) — advisory project schema (None ⇒ static prompt).
                        extraction_schema=extraction_schema,
                        # Model-context-aware chunk sizing (resolved once, stashed in
                        # resume_state for decoupled_extract.py's assemble_* functions).
                        provider_client=provider_client,
                    )
                    logger.info(
                        "Job %s: chapter %s submitted via DECOUPLED extraction (released)",
                        job.job_id, ch.chapter_id,
                    )
                    return  # release — the consumer drives this chapter to persist

                # Extract: Phase 4b-γ — worker-ai now runs the LLM
                # stage in-process via loreweave_extraction.extract_pass2,
                # then POSTs candidates to /persist-pass2.
                # Q4b-feed: candidates captured for the run-sample write below.
                _eff_model_ref = (
                    job.billing_llm_model if job.billing_user_id
                    else run_snapshot.model_ref
                )
                # Model-context-aware chunk sizing — resolve the ACTUAL model's
                # context window (never a flat assumption) so extraction chunk
                # size scales with the model in use. None (unresolved) keeps the
                # SDK's legacy flat 15-paragraph chunk size — never guess here.
                _ctx_len = await provider_client.get_context_length("user_model", _eff_model_ref)
                _chapter_context_budget = ContextBudget(model_context=_ctx_len) if _ctx_len else None
                result, candidates = await _extract_and_persist(
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
                    # E0-3 Phase 2a — a collaborator-triggered job uses the
                    # CALLER's billing LLM ref (their key); the per-project
                    # snapshot ref applies only on the owner path. Gated on
                    # billing_user_id (the identity), not the ref alone, to stay
                    # coherent with the submit_and_wait contextvar (MED-1).
                    model_ref=_eff_model_ref,
                    context_budget=_chapter_context_budget,
                    precision_filter=run_snapshot.precision_filter,
                    entity_recovery=run_snapshot.entity_recovery,
                    prompt_overrides=run_snapshot.prompts,
                    writer_autocreate=run_snapshot.writer_autocreate,
                    # L7 (Milestone B) — advisory project schema (None ⇒ static).
                    schema=extraction_schema,
                    text=text,
                    hierarchy_paths=p3_hierarchy_paths,
                    chapter_index=p3_chapter_index,  # FD-4 (066) — flat-book event_order
                    book_parts=p3_book_parts,
                    is_last_chapter_of_book=p3_is_last,
                    embedding_model_uuid=(
                        job.embedding_model if p3_hierarchy_paths else None
                    ),
                    embedding_dimension=(
                        job.embedding_dimension if p3_hierarchy_paths else None
                    ),
                    # E0-3 2a-2 — forward the job's billing identity so the
                    # summary pipeline this persist enqueues bills the caller
                    # (None on the owner path → legacy). Storage tag stays the
                    # project's embedding_model above.
                    billing_user_id=(
                        str(job.billing_user_id) if job.billing_user_id else None
                    ),
                    billing_llm_model=job.billing_llm_model,
                    billing_embedding_model=job.billing_embedding_model,
                    # C12 — target-typed extraction: the job's chosen pass subset.
                    # None ⇒ all passes (back-compat). The SDK strips `summaries`
                    # (orchestrator-gated); persist-pass2 honours it for the
                    # summary enqueue gate.
                    targets=job.targets,
                    # C12 — cap parallel R/E/F LLM calls (None ⇒ unbounded).
                    concurrency_level=job.concurrency_level,
                    # C13 — pinned names resolved once per job above; injected
                    # into this window's known_entities.
                    pinned_names=pinned_names,
                    # D-KG-WORKER-GRADED-EFFORT — the job's stored graded effort.
                    reasoning_effort=job.reasoning_effort,
                    # bug #34 — abort an in-flight LLM call on job cancellation.
                    cancel_check=cancel_check,
                )

                if result.error:
                    # S3c-2b: a provider circuit-open (retryable or not) signals
                    # the provider is down → tell campaign-service to auto-pause.
                    if result.error_code == "LLM_CIRCUIT_OPEN":
                        await emit_chapter_failed_best_effort(
                            pool,
                            user_id=str(job.user_id),
                            project_id=str(job.project_id),
                            book_id=str(book_id) if book_id else None,
                            chapter_id=str(ch.chapter_id),
                            error_code="LLM_CIRCUIT_OPEN",
                        )
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
                            skipped_delta=1,  # D-WORKER-SKIP-FALSE-GREEN
                        )
                        # CM3b: retry-exhausted is terminal — clear the queue row
                        # so the drainer doesn't re-process it forever. Mark-by-
                        # revision (MED-1): don't clobber a concurrent re-publish.
                        if ch.pending_id is not None:
                            await _mark_pending_processed(
                                pool, job.user_id, ch.pending_id,
                                revision_id=ch.revision_id,
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
                # Q4b-feed: generate run_id ONCE here and pass it to both the
                # payload and the run-sample below — parity is load-bearing
                # (the online judge fetches the sample by the event's run_id).
                run_id = str(uuid4())
                # Q4b-feed: persist the items+source run-sample for the online
                # LLM judge — ONLY for opted-in projects (save_raw_extraction),
                # keyed by the SAME run_id as the event. Written BEFORE the event
                # is emitted (/review-impl MED#1): the eval-runner fetches the
                # sample by the event's run_id, so the sample must be committed
                # before the event is consumable — else a fast consumer 404s and
                # silently falls back to structural-only. Best-effort: a lost
                # sample only drops a (droppable) judging opportunity; it must
                # never fail the extraction. Non-opted → write nothing.
                if job.save_raw_extraction and candidates is not None:
                    await persist_run_sample_best_effort(
                        pool, run_id=run_id, user_id=job.user_id,
                        project_id=job.project_id, book_id=book_id,
                        config_hash=run_cfg_hash, candidates=candidates,
                        source_text=text,
                    )
                run_payload = _run_payload(
                    job=job, book_id=book_id, chapter_ref=ch.chapter_id,
                    snapshot=run_snapshot, cfg_hash=run_cfg_hash,
                    base_version=run_base_version, outcome="succeeded", result=result,
                    run_id=run_id,
                )
                # Auto-Draft Factory S1 (decision H): per-chapter knowledge
                # completion for campaign-service's projection. Emitted in the SAME
                # tx as the cursor advance (D-CAMPAIGN-BESTEFFORT-EMIT-REDIS) so a
                # chapter whose cursor advanced ALWAYS has its completion event —
                # closing the silent-loss window that stalled campaigns `dispatched`.
                await _advance_cursor_and_emit_run(
                    pool, job.user_id, job.job_id,
                    {"last_chapter_id": ch.chapter_id, "scope": "chapters"},
                    run_payload,
                    chapter_extracted={
                        "user_id": str(job.user_id),
                        "project_id": str(job.project_id),
                        "book_id": str(book_id) if book_id else None,
                        "chapter_id": str(ch.chapter_id),
                    },
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
                # CM3b: clear the pending queue row (chapters_pending drain).
                # Mark-by-revision (MED-1): a concurrent re-publish that re-armed
                # the row at a new revision must NOT be marked done here.
                if ch.pending_id is not None:
                    await _mark_pending_processed(
                        pool, job.user_id, ch.pending_id, revision_id=ch.revision_id,
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

                # FD-2: fetch the REAL turn text (user question + assistant answer)
                # from chat-service by the assistant message id (the event's
                # aggregate_id). None (404 / empty / transport) → "" → extract_pass2
                # short-circuits to empty WITHOUT an LLM call, persist-pass2 still
                # writes the source row for idempotency — the same graceful no-op
                # the path always had, now with real extraction when text exists.
                turn_text = await chat_client.get_turn_text(turn["aggregate_id"]) or ""
                result, _ = await _extract_and_persist(
                    knowledge_client=knowledge_client,
                    llm_client=llm_client,
                    user_id=job.user_id,
                    project_id=job.project_id,
                    source_type="chat_message",
                    source_id=str(turn["aggregate_id"]),
                    job_id=job.job_id,
                    # E0-3 Phase 2a — caller's billing LLM ref on the
                    # collaborator path; job.llm_model (owner's) when billing NULL.
                    model_ref=eff_llm_ref(job),
                    text=turn_text,
                    # C13 — pins reach EVERY extraction window, chat turns
                    # included (the cost estimate's num_windows counts chat turns,
                    # so the injection must too). Resolved once per job above.
                    pinned_names=pinned_names,
                    # L7 (Milestone B) — advisory project schema (None ⇒ static).
                    schema=extraction_schema,
                    # D-KG-WORKER-GRADED-EFFORT — the job's stored graded effort.
                    reasoning_effort=job.reasoning_effort,
                    # bug #34 — abort an in-flight LLM call on job cancellation.
                    cancel_check=cancel_check,
                )

                if result.error and not result.retryable:
                    await _fail_job(pool, job.user_id, job.job_id, result.error)
                    await _update_project_status(pool, job.user_id, job.project_id, "failed")
                    return

                await _mark_pending_processed(pool, job.user_id, turn["pending_id"])
                # D-EXTRACTION-SILENT-NOOP: a chat turn whose text is gone/empty
                # (deleted session, a tool-only turn with no prose) does NO extraction —
                # extract_pass2 short-circuited WITHOUT an LLM call. Count it SKIPPED
                # (mirroring the chapter D-WORKER-SKIP-FALSE-GREEN), NOT a fake
                # 'processed', and don't charge for a no-op. This keeps items_processed
                # honest AND stops the 0-LLM-call completion flag from false-positiving
                # on a legitimately-empty turn (the all-skipped flag covers that case).
                _empty_turn = not turn_text.strip()
                await _advance_cursor(
                    pool, job.user_id, job.job_id,
                    {"last_pending_id": str(turn["pending_id"]), "scope": "chat"},
                    items_delta=0 if _empty_turn else 1,
                    skipped_delta=1 if _empty_turn else 0,
                )
                if not _empty_turn:
                    # D-K16.11-01: same per-project accounting as the chapters branch.
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


async def _ensure_chapters_pending_jobs(pool: asyncpg.Pool) -> int:
    """Canon Model CM3b — create a 'chapters_pending' drain job for each
    project that has unprocessed chapter pending rows AND no active job.

    REUSES the project's last job's models: `_build_run_config` sets
    `run_snapshot.model_ref = job.llm_model`, so the drain job's `llm_model`
    IS the extraction model — a placeholder would break extraction. A project
    with no prior job is skipped (a manual /extraction/start whole-book run
    bootstraps it; subsequent publishes then auto-drain). Idempotent via the
    one-active-job-per-project unique index — swallow the 409 (an active job
    will drain the queued rows; the poll re-creates a drain job once it ends if
    rows remain, so nothing is lost).
    """
    rows = await pool.fetch(
        """
        SELECT DISTINCT p.user_id, ep.project_id
        FROM extraction_pending ep
        JOIN knowledge_projects p ON p.project_id = ep.project_id
        WHERE ep.aggregate_type = 'chapter' AND ep.processed_at IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM extraction_jobs j
            WHERE j.project_id = ep.project_id
              AND j.status IN ('pending', 'running', 'paused')
          )
          -- MED-2: don't recreate a drain within 1h of a FAILED drain (e.g. a
          -- deleted/invalid model_ref) — else it loops fail→recreate every poll.
          -- Fail-stop + eventual retry; the failed job is visible for the user
          -- to fix the model. (A transient failure retries after the window.)
          AND NOT EXISTS (
            SELECT 1 FROM extraction_jobs j2
            WHERE j2.project_id = ep.project_id
              AND j2.scope = 'chapters_pending'
              AND j2.status = 'failed'
              AND j2.updated_at > now() - interval '1 hour'
          )
        """
    )
    created = 0
    for r in rows:
        user_id, project_id = r["user_id"], r["project_id"]
        last = await pool.fetchrow(
            """
            SELECT llm_model, embedding_model, max_spend_usd FROM extraction_jobs
            WHERE project_id = $1 ORDER BY created_at DESC LIMIT 1
            """,
            project_id,
        )
        if last is None:
            continue  # no prior job → manual whole-book run bootstraps it
        try:
            # Reuse the last job's max_spend_usd as the drain's cap. The drain is
            # created via raw INSERT (bypasses start_extraction_job's monthly-budget
            # pre-check), so without a cap an auto-drain would be unbounded; reusing
            # the user's last cap bounds it (paused-on-cap is visible + resumable,
            # vs silent unbounded spend).
            await pool.execute(
                """
                INSERT INTO extraction_jobs
                  (user_id, project_id, scope, status, llm_model, embedding_model,
                   max_spend_usd, started_at, updated_at)
                VALUES ($1, $2, 'chapters_pending', 'running', $3, $4, $5, now(), now())
                """,
                user_id, project_id,
                last["llm_model"], last["embedding_model"], last["max_spend_usd"],
            )
            created += 1
            logger.info(
                "CM3b: created chapters_pending drain job for project=%s", project_id,
            )
        except asyncpg.UniqueViolationError:
            # An active job appeared concurrently — it will drain the queue.
            pass
    return created


async def _ensure_chat_pending_jobs(pool: asyncpg.Pool) -> int:
    """FD-2 — create a 'chat' drain job for each project that has unprocessed
    chat turn pending rows (`aggregate_type='chat'`) AND no active job.

    Mirror of `_ensure_chapters_pending_jobs` for the chat→KG path: without it,
    `chat.turn_completed` rows accumulate in `extraction_pending` and only drain
    when the user manually triggers a full extraction — chat knowledge would
    never extract in near-real-time the way published chapters do. The
    `scope='chat'` job's turn loop fetches each turn's real text via ChatClient
    and extracts it. Same guards as the chapter drainer:
      - skip projects with an active job (one-active-job-per-project unique
        index makes the INSERT idempotent — 409 swallowed; an active chapter
        OR chat drain will progress, and the next poll re-arms if rows remain),
      - reuse the project's last job's models + spend cap (a placeholder model
        would break extraction; an uncapped auto-drain could spend unbounded),
      - 1h backoff after a FAILED chat drain (else fail→recreate every poll).
    A project with no prior job is skipped (a manual /extraction/start
    bootstraps it; subsequent chat turns then auto-drain).
    """
    rows = await pool.fetch(
        """
        SELECT DISTINCT p.user_id, ep.project_id
        FROM extraction_pending ep
        JOIN knowledge_projects p ON p.project_id = ep.project_id
        WHERE ep.aggregate_type = 'chat' AND ep.processed_at IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM extraction_jobs j
            WHERE j.project_id = ep.project_id
              AND j.status IN ('pending', 'running', 'paused')
          )
          AND NOT EXISTS (
            SELECT 1 FROM extraction_jobs j2
            WHERE j2.project_id = ep.project_id
              AND j2.scope = 'chat'
              AND j2.status = 'failed'
              AND j2.updated_at > now() - interval '1 hour'
          )
        """
    )
    created = 0
    for r in rows:
        user_id, project_id = r["user_id"], r["project_id"]
        last = await pool.fetchrow(
            """
            SELECT llm_model, embedding_model, max_spend_usd FROM extraction_jobs
            WHERE project_id = $1 ORDER BY created_at DESC LIMIT 1
            """,
            project_id,
        )
        if last is None:
            continue  # no prior job → manual run bootstraps it
        try:
            await pool.execute(
                """
                INSERT INTO extraction_jobs
                  (user_id, project_id, scope, status, llm_model, embedding_model,
                   max_spend_usd, started_at, updated_at)
                VALUES ($1, $2, 'chat', 'running', $3, $4, $5, now(), now())
                """,
                user_id, project_id,
                last["llm_model"], last["embedding_model"], last["max_spend_usd"],
            )
            created += 1
            logger.info("FD-2: created chat drain job for project=%s", project_id)
        except asyncpg.UniqueViolationError:
            # An active job appeared concurrently — it will drain the queue,
            # and the next poll re-arms a chat drain if rows still remain.
            pass
    return created


async def poll_and_run(
    pool: asyncpg.Pool,
    knowledge_client: KnowledgeClient,
    llm_client: LLMClient,
    book_client: BookClient,
    glossary_client: GlossaryClient,
    chat_client: ChatClient,
    provider_client: ProviderRegistryClient,
) -> int:
    """One poll cycle: find running jobs and process them.

    Returns the number of jobs processed (for logging/metrics).
    Called repeatedly by the main loop with a sleep interval.
    """
    # CM3b: create drain jobs for projects with queued published chapters
    # BEFORE picking up running jobs, so a freshly-created one runs this cycle.
    try:
        await _ensure_chapters_pending_jobs(pool)
    except Exception:
        logger.warning(
            "CM3b: ensure chapters_pending jobs failed — non-fatal", exc_info=True
        )
    # FD-2: same for queued chat turns (chat→KG auto-drain). Runs after the
    # chapter ensurer; the one-active-job-per-project index serializes the two
    # (chat re-arms next poll if a chapter drain is currently active).
    try:
        await _ensure_chat_pending_jobs(pool)
    except Exception:
        logger.warning(
            "FD-2: ensure chat pending jobs failed — non-fatal", exc_info=True
        )
    jobs = await _get_running_jobs(pool)
    if not jobs:
        return 0

    # P5 WFQ — when fair scheduling is on, interleave jobs across owners (round-robin)
    # instead of strict created_at, so a new owner's job isn't stuck behind one owner's
    # giant book. Also periodically reclaim expired leases (crash-leak backstop). Both
    # are no-ops when P5 is off (created_at order preserved). Best-effort: a scheduler/
    # redis blip must never block the poll cycle.
    if fair_sched.enabled():
        try:
            await fair_sched.reclaim()
            jobs = fair_sched.round_robin_by_owner(jobs)
        except Exception:  # noqa: BLE001 — fairness must not block extraction
            logger.warning("P5: poll-loop WFQ ordering/reclaim failed — created_at order", exc_info=True)

    for job in jobs:
        await process_job(
            pool, knowledge_client, llm_client, book_client, glossary_client,
            chat_client, provider_client, job,
        )

    return len(jobs)
