"""Prometheus metrics registry for knowledge-service (K6.5).

Single CollectorRegistry shared across the process. All K6 code paths
import the counters/gauges/histograms from here so /metrics exposes
them via prometheus_client.generate_latest().

The registry is module-level (not the prometheus_client default
REGISTRY) so tests can reset it without disturbing other processes,
and so we don't accidentally export built-in process/GC metrics that
would bloat the scrape.
"""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

__all__ = [
    "registry",
    "layer_timeout_total",
    "cache_hit_total",
    "cache_miss_total",
    "circuit_open",
    "context_build_duration_seconds",
    "evidence_count_drift_fixed_total",
    "injection_pattern_matched_total",
    "pass1_facts_written_total",
    "pass1_candidates_extracted_total",
    "pass1_extraction_duration_seconds",
    "quarantine_auto_invalidated_total",
    "anchor_resolver_hits_total",
    "anchor_resolver_misses_total",
    "anchor_refresh_runs_total",
    "summary_regen_total",
    "summary_regen_duration_seconds",
    "summary_regen_cost_usd_total",
    "summary_regen_tokens_total",
    "reconcile_sweep_total",
    "quarantine_sweep_total",
]

registry = CollectorRegistry()

layer_timeout_total = Counter(
    "knowledge_layer_timeout_total",
    "Number of layer fetches that hit their per-layer timeout",
    ["layer"],
    registry=registry,
)

cache_hit_total = Counter(
    "knowledge_cache_hit_total",
    "TTL cache hits in the context builder",
    ["layer"],
    registry=registry,
)

cache_miss_total = Counter(
    "knowledge_cache_miss_total",
    "TTL cache misses in the context builder",
    ["layer"],
    registry=registry,
)

circuit_open = Gauge(
    "knowledge_circuit_open",
    "Circuit breaker open state (1=open, 0=closed)",
    ["service"],
    registry=registry,
)

# Pre-initialise to 0 so the gauge is visible on first scrape even
# before any failure has moved it.
circuit_open.labels(service="glossary").set(0)

context_build_duration_seconds = Histogram(
    "knowledge_context_build_duration_seconds",
    "End-to-end build_context duration in seconds",
    ["mode"],
    registry=registry,
)

# K11.9 offline reconciler. Monotonic counter: increments by the number
# of nodes whose cached evidence_count was corrected on each run. Non-
# zero means a write-path somewhere missed an increment/decrement and
# should be investigated — the reconciler fixes the symptom, not the
# cause.
evidence_count_drift_fixed_total = Counter(
    "knowledge_evidence_count_drift_fixed_total",
    "Nodes where the K11.9 reconciler corrected drift between cached "
    "evidence_count and actual EVIDENCED_BY edge count",
    ["node_label"],
    registry=registry,
)
for _label in ("Entity", "Event", "Fact"):
    evidence_count_drift_fixed_total.labels(node_label=_label).inc(0)

# K15.6 prompt injection defense (KSA §5.1.5 Defense 2 + Defense 4).
# Monotonic counter: one increment per pattern match in extracted text.
# `project_id` is bounded by user/tenant count; `pattern` is bounded by
# the closed list in injection_defense.INJECTION_PATTERNS (~15 entries).
# Cardinality is acceptable for Track 1 hobby scale.
injection_pattern_matched_total = Counter(
    "knowledge_injection_pattern_matched_total",
    "Number of prompt-injection pattern hits detected by "
    "neutralize_injection at extraction or context-build time",
    ["project_id", "pattern"],
    registry=registry,
)

# K15.7 pattern extraction writer. Counts nodes/edges actually
# persisted to Neo4j by the Pass 1 pattern pipeline, split by kind
# so dashboards can tell whether the bottleneck is entity, relation,
# or fact creation. `kind` cardinality is closed at 3.
pass1_facts_written_total = Counter(
    "knowledge_pass1_facts_written_total",
    "Entities / relations / facts written to Neo4j by the K15.7 "
    "pattern-extraction writer (quarantine confidence 0.5)",
    ["kind"],
    registry=registry,
)
for _kind in ("entity", "relation", "fact"):
    pass1_facts_written_total.labels(kind=_kind).inc(0)

# K15.12 pattern-extraction orchestrator counters. Track candidates
# produced *before* K15.7 dedupe/write, so dashboards can distinguish
# "extractor found nothing" from "extractor found plenty but writer
# dropped them as duplicates or missing-endpoint". `kind` cardinality
# is closed at 3 (entity | triple | negation).
#
# **Semantics (K15.12-R1/I1):** this counts *raw extractor work*, not
# unique candidates. Re-extracting the same chat turn / chapter with
# the same job_id is a writer-level no-op (K15.7 dedupes) but still
# increments this counter by the full candidate set. A dashboard
# panel computing "extraction → write conversion ratio" must account
# for re-runs drifting the ratio above 1.0; the intended alerting
# use is "did the extractor do any work at all in window W", not
# "how many unique facts did we harvest".
pass1_candidates_extracted_total = Counter(
    "knowledge_pass1_candidates_extracted_total",
    "Pattern-extractor candidates produced by K15.8/K15.9 orchestrators "
    "before K15.7 writer dedupe (entity / triple / negation)",
    ["kind", "source_kind"],
    registry=registry,
)
# K15.12-R2/I5: split by source_kind so dashboards can compare
# chapter-extractor vs chat-extractor yield per call. Cardinality
# stays bounded at 3 × 2 = 6 series.
for _kind in ("entity", "triple", "negation"):
    for _sk in ("chat_turn", "chapter"):
        pass1_candidates_extracted_total.labels(
            kind=_kind, source_kind=_sk
        ).inc(0)

# K15.12 orchestrator wall-time histogram. `source_kind` is closed at
# 2 (chat_turn | chapter). Buckets target the acceptance envelope from
# KSA §5.1: chat turn <2s, chapter <30s. Coarser than the default
# prom buckets so a laptop-scale p95 doesn't land in the same bucket
# as a degenerate timeout.
pass1_extraction_duration_seconds = Histogram(
    "knowledge_pass1_extraction_duration_seconds",
    "Wall-time of K15.8/K15.9 Pass 1 extraction orchestrator calls",
    ["source_kind"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
    registry=registry,
)
for _sk in ("chat_turn", "chapter"):
    pass1_extraction_duration_seconds.labels(source_kind=_sk)

# K15.10 quarantine cleanup job. Monotonic counter: increments by the
# number of Pass 1 facts whose `pending_validation=true` flag outlived
# the TTL (default 24h) and were soft-invalidated by the cleanup sweep.
# Non-zero means Pass 2 (K17 LLM validator) is not keeping up — either
# worker-ai is down, provider budget is exhausted, or auto-validation
# is disabled. Label-less: cardinality stays bounded regardless of
# tenant count.
quarantine_auto_invalidated_total = Counter(
    "knowledge_quarantine_auto_invalidated_total",
    "Pass 1 facts soft-invalidated by the K15.10 quarantine cleanup "
    "job after exceeding the pending_validation TTL",
    registry=registry,
)
quarantine_auto_invalidated_total.inc(0)

# ── Unified-LLM-pipeline observability (Phase 4a) ────────────────────
#
# Replaces the deleted `provider_chat_completion_*` counters; gateway-
# side equivalents in provider-registry-service cover the HTTP-layer
# detail, and these counters cover the SDK-wrapper layer.

_LLM_JOB_OUTCOMES = (
    "completed",
    "failed",
    "cancelled",
    "transient_retry",   # caller-side retry consumed (D3c bridge)
    "sdk_error",         # LLMError that wasn't a normal terminal
)

knowledge_llm_job_total = Counter(
    "knowledge_llm_job_total",
    "Phase 4a-α — async LLM job terminations dispatched via loreweave_llm SDK. "
    "Async LLM job terminations dispatched via the loreweave_llm SDK.",
    ["operation", "outcome"],
    registry=registry,
)

# Pre-seed common (operation, outcome) pairs so dashboards don't show
# blank panels until first traffic. Operations covered: chat (summaries)
# + entity_extraction (4a-α) + relation_extraction/event_extraction/
# fact_extraction (4a-β placeholder).
for _op in ("chat", "entity_extraction", "relation_extraction", "event_extraction"):
    for _o in _LLM_JOB_OUTCOMES:
        knowledge_llm_job_total.labels(operation=_op, outcome=_o)

knowledge_llm_poll_total = Counter(
    "knowledge_llm_poll_total",
    "Phase 4a-α — wait_terminal poll outcomes. Per /review-impl MED#7 — "
    "polling DB-load measurement so cap decisions become data-driven.",
    ["outcome"],
    registry=registry,
)
for _o in ("terminal", "http_error"):
    knowledge_llm_poll_total.labels(outcome=_o)

# Gauge — current concurrent in-flight jobs initiated by this knowledge-
# service worker process. Per /review-impl MED#9 — visibility into
# per-chapter 3-job burst BEFORE Phase 6a hard cap ships.
knowledge_llm_inflight_jobs = Gauge(
    "knowledge_llm_inflight_jobs",
    "Phase 4a-α — concurrent LLM jobs in flight from this worker process",
    registry=registry,
)

# Per /review-impl Q3 (cross-chunk known_entities / tolerant parser drops)
# — visibility into items dropped by tolerant parser so a quality
# regression surfaces in metrics before users notice missing entities.
knowledge_extraction_dropped_total = Counter(
    "knowledge_extraction_dropped_total",
    "Phase 4a-α — items dropped by tolerant parser (missing required field)",
    ["operation", "reason"],
    registry=registry,
)
for _op in ("entity_extraction", "relation_extraction", "event_extraction"):
    for _r in ("missing_name", "missing_kind", "missing_evidence_passage_id", "validation"):
        knowledge_extraction_dropped_total.labels(operation=_op, reason=_r)

# ── K13.0 anchor resolver ──────────────────────────────────────────

# Hit = extraction candidate matched a glossary anchor → merge_entity
# was skipped and the evidence edge links to the existing anchor.
# Miss = no match → merge_entity ran (existing behavior pre-K13.0).
# The kind label is the GLOSSARY kind (normalized), so dashboards can
# drill into per-kind hit rates.
anchor_resolver_hits_total = Counter(
    "knowledge_anchor_resolver_hits_total",
    "K13.0 anchor hits in resolve_or_merge_entity",
    ["kind"],
    registry=registry,
)
anchor_resolver_misses_total = Counter(
    "knowledge_anchor_resolver_misses_total",
    "K13.0 anchor misses in resolve_or_merge_entity",
    ["kind"],
    registry=registry,
)

# K13.1 anchor_score refresh loop run count + outcome.
anchor_refresh_runs_total = Counter(
    "knowledge_anchor_refresh_runs_total",
    "K13.1 nightly anchor-score refresh loop runs by outcome",
    ["outcome"],
    registry=registry,
)
# Pre-seed labels so zeros appear in /metrics before the first run.
for _outcome in ("ok", "lock_skipped", "error"):
    anchor_refresh_runs_total.labels(outcome=_outcome)


# ── K20α / K20.7 — summary regeneration observability ──────────────

# Status label enumerates every branch of RegenerationResult so the
# counter doubles as the K20.7 `summary_regen_no_op` and
# `summary_user_override_respected` rollups (just filter by status in
# Grafana). Scope label is closed at 2 (global / project).
_REGEN_STATUSES = (
    "regenerated",
    "no_op_similarity",
    "no_op_empty_source",
    "no_op_guardrail",
    "user_edit_lock",
    "regen_concurrent_edit",
)
_REGEN_SCOPES = ("global", "project")

# C2 — trigger label distinguishes human-initiated regens (public
# edge in summaries.py) from loop-initiated ones (K20.3 scheduler).
# Cardinality stays bounded: 2 scopes × 6 statuses × 2 triggers = 24
# pre-seeded series. Grafana queries that don't group by `trigger`
# continue to aggregate over both values — the label is additive.
_REGEN_TRIGGERS = ("manual", "scheduled")

summary_regen_total = Counter(
    "knowledge_summary_regen_total",
    "K20α summary regeneration calls by outcome. Sum over "
    "status='regenerated' → actual regens; status='user_edit_lock' "
    "→ KSA §7.6 `summary_user_override_respected`; status starts "
    "with 'no_op_' → `summary_regen_no_op`. `trigger` splits "
    "public-edge (manual) vs K20.3 scheduler (scheduled).",
    ["scope_type", "status", "trigger"],
    registry=registry,
)
for _scope in _REGEN_SCOPES:
    for _status in _REGEN_STATUSES:
        for _trigger in _REGEN_TRIGGERS:
            summary_regen_total.labels(
                scope_type=_scope, status=_status, trigger=_trigger
            )

# Wall-time of the whole _regenerate_core flow, labelled by scope so
# global vs project can be tracked separately. Buckets scaled for the
# expected shape: LLM call dominates at 0.5-10s; edit-lock /
# empty-source short-circuits at <50ms.
summary_regen_duration_seconds = Histogram(
    "knowledge_summary_regen_duration_seconds",
    "K20α end-to-end regenerate_*_summary duration",
    ["scope_type"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
    registry=registry,
)
for _scope in _REGEN_SCOPES:
    summary_regen_duration_seconds.labels(scope_type=_scope)

# Monotonic USD cost tally per scope. Cost is computed from the LLM
# response's token usage × `pricing.cost_per_token(model_ref)`. Only
# incremented for status='regenerated' — no-op / edit-lock paths cost
# $0 by definition. Cardinality is closed at 2 series.
#
# D-K20α-01 (partial): this is the ops-visibility half of cost
# tracking. The budget-integration half (route regen cost into
# `knowledge_projects.current_month_spent_usd` so user-wide caps
# apply) is still deferred because global-scope regens have no
# project_id to attribute against.
summary_regen_cost_usd_total = Counter(
    "knowledge_summary_regen_cost_usd_total",
    "K20α monotonic USD sum of successful regen LLM costs by scope",
    ["scope_type"],
    registry=registry,
)
for _scope in _REGEN_SCOPES:
    summary_regen_cost_usd_total.labels(scope_type=_scope)

# Token usage split by kind so dashboards can show prompt vs
# completion separately. Useful for sizing context-window pressure.
summary_regen_tokens_total = Counter(
    "knowledge_summary_regen_tokens_total",
    "K20α tokens consumed by regen LLM calls, split by scope + kind",
    ["scope_type", "token_kind"],
    registry=registry,
)
for _scope in _REGEN_SCOPES:
    for _kind in ("prompt", "completion"):
        summary_regen_tokens_total.labels(
            scope_type=_scope, token_kind=_kind
        )


# ── C14a — scheduler sweep outcome counters ──────────────────────────
# One counter per scheduler, labelled by outcome. Lets operators alert
# on e.g. `reconcile_sweep_total{outcome="errored"}` firing unexpectedly.
# Mirrors the observability pattern established by K20.3's
# summary_regen_total (which labels by scope+status).
#
# **Counter semantics** (/review-impl MED#3 clarification):
#   - `completed`     — +1 per sweep that finished without a sweep-
#                       level exception (advisory-lock fetch, user-list
#                       query, etc.). Increments regardless of per-user
#                       errors inside the sweep.
#   - `lock_skipped`  — +1 per sweep that bailed because another
#                       worker/replica held the advisory lock.
#   - `errored`       — +1 per sweep that had ≥1 per-user (reconcile)
#                       or sweep-level (quarantine) error. This is NOT
#                       a per-user error count — a sweep with 5 users
#                       all erroring increments `errored` by 1, not 5.
#                       For per-user error totals, query the sum of
#                       `users_errored` from structured logs.
#
# Useful derived metrics:
#   rate(completed[1d])                — sweep throughput
#   rate(errored[1d]) / rate(completed[1d]) — fraction of sweeps with errors
#   rate(lock_skipped[1d])             — worker contention signal

# K11.9 evidence-count drift reconciler — one sweep = one full scan of
# active users. `errored` fires once per sweep when ≥1 user errored
# (not per user error). Per-user error detail lives in logs.
reconcile_sweep_total = Counter(
    "knowledge_reconcile_sweep_total",
    "C14a reconcile-evidence-count scheduler sweep outcomes. "
    "`errored` fires once per sweep that had ≥1 per-user error "
    "(not per per-user error). See comment in metrics.py for detail.",
    ["outcome"],
    registry=registry,
)
for _outcome in ("completed", "lock_skipped", "errored"):
    reconcile_sweep_total.labels(outcome=_outcome)

# K15.10 quarantine TTL auto-invalidator — one sweep may loop multiple
# Cypher drain iterations under a single advisory lock. `errored`
# fires once if the drain loop or helper raised.
quarantine_sweep_total = Counter(
    "knowledge_quarantine_sweep_total",
    "C14a quarantine-cleanup scheduler sweep outcomes. "
    "`errored` fires once per sweep where the drain loop raised "
    "(not per failed drain iteration). See comment in metrics.py.",
    ["outcome"],
    registry=registry,
)
for _outcome in ("completed", "lock_skipped", "errored"):
    quarantine_sweep_total.labels(outcome=_outcome)
