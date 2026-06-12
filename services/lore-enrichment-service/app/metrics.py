"""Prometheus metrics registry for lore-enrichment-service (RAID C18).

Single module-level ``CollectorRegistry`` shared across the process. The C14
job runner's event emitter (``app.jobs.events.JobEventEmitter``) increments
these from the LIVE pipeline — they are NOT hardcoded/stubbed: a ``/metrics``
scrape that returns fixed numbers would be a false-green (C18 adversary focus
"metric honesty"). The runner emits one lifecycle event per phase through the
emitter, and the emitter is the single chokepoint that moves the counters, so a
real enrichment job moves jobs/proposals/latency.

Design notes (mirrors knowledge-service ``app/metrics.py`` K6.5):
  * The registry is module-level (NOT the prometheus_client default REGISTRY)
    so tests can construct a fresh one and so we don't bloat the scrape with
    process/GC collectors.
  * Metric and label names carry NO model names, NO secrets, NO raw URLs, NO
    per-job-id high-cardinality labels (C18 adversary focus
    "observability leaking secrets/PII" + "high-cardinality labels are a
    smell"). ``technique`` / ``source_type`` are closed vocabularies (the C2
    technique CHECK + the H0 source_type set), so cardinality stays bounded.
  * Labels are pre-seeded to 0 so panels render before first traffic.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram

__all__ = [
    "registry",
    "jobs_started_total",
    "jobs_completed_total",
    "jobs_failed_total",
    "jobs_paused_total",
    "proposals_created_total",
    "proposals_auto_rejected_total",
    "stage_duration_seconds",
    "cost_cap_pauses_total",
    "llm_calls_total",
    "embed_calls_total",
]

#: Process-wide registry. /metrics exposes only what we register here.
registry = CollectorRegistry()

# ── Job lifecycle counters ───────────────────────────────────────────────────
# One increment per job lifecycle termination, moved by the LIVE C14 runner via
# the event emitter (see app/jobs/events.py). Label-less: bounded cardinality.

jobs_started_total = Counter(
    "lore_enrichment_jobs_started_total",
    "Enrichment jobs that entered the running state (C14 runner job.started)",
    registry=registry,
)
jobs_started_total.inc(0)

jobs_completed_total = Counter(
    "lore_enrichment_jobs_completed_total",
    "Enrichment jobs that reached the completed state (C14 runner job.completed)",
    registry=registry,
)
jobs_completed_total.inc(0)

jobs_failed_total = Counter(
    "lore_enrichment_jobs_failed_total",
    "Enrichment jobs that terminated in the failed state (C14 runner job.failed)",
    registry=registry,
)
jobs_failed_total.inc(0)

jobs_paused_total = Counter(
    "lore_enrichment_jobs_paused_total",
    "Enrichment jobs paused before a gap by the per-job cost cap "
    "(C14 runner job.paused; eval reserve protected)",
    registry=registry,
)
jobs_paused_total.inc(0)

# ── Proposal counter ─────────────────────────────────────────────────────────
# Incremented once per quarantined H0 proposal the runner persists. ``source_type``
# is the H0 origin marker (closed vocab) so a dashboard can split which technique
# tier produced the makeup lore. NOT labelled by job_id / entity (high cardinality).
_SOURCE_TYPES = (
    "enriched:retrieval",
    "enriched:fabrication",
    "enriched:recook",
    "enriched",
)
proposals_created_total = Counter(
    "lore_enrichment_proposals_created_total",
    "Quarantined H0 proposals persisted by the C14 runner, split by source_type "
    "(the origin marker; promote to canon is a separate human gate — NOT counted "
    "here). All values are origin='enrichment' tier markers, never 'glossary'.",
    ["source_type"],
    registry=registry,
)
for _st in _SOURCE_TYPES:
    proposals_created_total.labels(source_type=_st)

# ── Per-stage latency ────────────────────────────────────────────────────────
# Wall-time of a single gap's stage pipeline (retrieval → generate → verify),
# measured by the runner around run_gap and reported as the stage_completed
# event's elapsed_seconds. ``technique`` is a closed vocab (C2 CHECK).
_TECHNIQUES = ("retrieval", "fabrication", "recook")
stage_duration_seconds = Histogram(
    "lore_enrichment_stage_duration_seconds",
    "Wall-time of one gap's stage pipeline (retrieval → generate → verify) in "
    "the C14 runner, labelled by technique",
    ["technique"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
    registry=registry,
)
for _t in _TECHNIQUES:
    stage_duration_seconds.labels(technique=_t)

# ── Cost-cap pauses ──────────────────────────────────────────────────────────
cost_cap_pauses_total = Counter(
    "lore_enrichment_cost_cap_pauses_total",
    "Times the per-job cost cap paused a job before a gap (the working cap was "
    "reached; the eval reserve is held out and never spent here)",
    registry=registry,
)
cost_cap_pauses_total.inc(0)

# ── Auto-reject (C3) ─────────────────────────────────────────────────────────
proposals_auto_rejected_total = Counter(
    "lore_enrichment_proposals_auto_rejected_total",
    "Proposals AUTO-REJECTED as egregious (injection / HIGH contradiction / >=2 "
    "distinct anachronism markers) — persisted as terminal `rejected`, never "
    "surfaced; monitors the false-positive risk of the auto-reject gate (C3)",
    registry=registry,
)
proposals_auto_rejected_total.inc(0)

# ── External-call counts ─────────────────────────────────────────────────────
# LLM completion + embedding calls made by the pipeline, by outcome. These move
# from the client seams (generation/retrieval) so a scrape reflects real provider
# traffic. NO model name appears as a label — the model resolves via
# provider-registry model_ref at runtime; the label is the call OUTCOME only.
_CALL_OUTCOMES = ("ok", "error")

llm_calls_total = Counter(
    "lore_enrichment_llm_calls_total",
    "LLM completion calls dispatched by the generation seam (via provider-registry "
    "model_ref), by outcome. NO model name in the label (closed: ok/error).",
    ["outcome"],
    registry=registry,
)
for _o in _CALL_OUTCOMES:
    llm_calls_total.labels(outcome=_o)

embed_calls_total = Counter(
    "lore_enrichment_embed_calls_total",
    "Embedding calls dispatched by the retrieval seam (via provider-registry "
    "model_ref), by outcome. NO model name in the label (closed: ok/error).",
    ["outcome"],
    registry=registry,
)
for _o in _CALL_OUTCOMES:
    embed_calls_total.labels(outcome=_o)
