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
    "tool_calls_total",
    "tool_call_duration_seconds",
    "tool_call_result_size_bytes",
    "memory_remember_rate_limited_total",
    "mode3_intent_classifier_glossary_unavailable_total",
    "mode3_grounding_zero_anchor_total",
    "knowledge_extraction_filter_decisions_total",
    "knowledge_extraction_filter_coverage_ratio",
    "knowledge_extraction_recovery_decisions_total",
    "knowledge_extraction_writer_autocreate_total",
    "knowledge_extraction_filter_reload_total",
    "knowledge_extraction_status_effect_total",
    "correction_emit_failure_total",
]

registry = CollectorRegistry()

layer_timeout_total = Counter(
    "knowledge_layer_timeout_total",
    "Number of layer fetches that hit their per-layer timeout",
    ["layer"],
    registry=registry,
)

# FD-19/053 — correction outbox emit failures, split by kind. `transient`
# (pool/conn/PG) is best-effort-OK (replay backstop applies); `permanent`
# (non-UUID aggregate_id, malformed payload, schema drift) NEVER reached
# outbox_events → zero replay durability → a bug to fix. A non-zero
# `permanent` series is an alert.
correction_emit_failure_total = Counter(
    "knowledge_correction_emit_failure_total",
    "Swallowed correction/config outbox emit failures by kind "
    "(transient = retriable/replayable; permanent = lost, a bug).",
    ["kind"],
    registry=registry,
)
# Pre-seed both series so a dashboard shows `0` (not absent) before the first
# failure — a steady 0 on `permanent` is the healthy signal we want visible.
for _kind in ("transient", "permanent"):
    correction_emit_failure_total.labels(kind=_kind)

# D-P3-INTENT-CLASSIFIER-GLOSSARY-METRIC. Distinct from the general
# layer_timeout_total{layer="glossary"} so a dashboard can split
# "glossary is generally flaky" from "Mode-3 intent classifier
# specifically ran without glossary input". The intent classifier
# falls back to a less-precise heuristic when glossary is unavailable
# (long queries → forced abstract path → unnecessary summary_blend
# cost). A spike here means Mode-3 retrieval quality is degraded.
mode3_intent_classifier_glossary_unavailable_total = Counter(
    "knowledge_mode3_intent_classifier_glossary_unavailable_total",
    "Mode-3 query was classified by the intent heuristic while "
    "glossary input was unavailable (timeout/exception); the classifier "
    "fell back to the less-precise long-query branch",
    registry=registry,
)
# Pre-initialise to 0 so the counter is visible on first scrape.
mode3_intent_classifier_glossary_unavailable_total.inc(0)

# M-recall — a Mode-3 grounding turn resolved ZERO entity anchors after every
# path (classifier + CJK dict-anchor + protagonist role-resolution) → the L2 facts
# layer stayed dark. `question="true"` is the signal that matters: a turn that ASKED
# something but anchored nothing is the candidate "referenced an entity by a form we
# can't resolve" — generic-noun coreference ("那位重生的少年…"), an out-of-graph
# entity, or a typo. This is the deferred generic-noun-coref FREQUENCY meter: measured
# 0/758 on the (unrepresentative) dev corpus, so we defer the fix and let production
# tell us how common it really is before building anything. `question="false"` is the
# expected/uninteresting case (greetings, statements).
mode3_grounding_zero_anchor_total = Counter(
    "knowledge_mode3_grounding_zero_anchor_total",
    "Mode-3 grounding turns that resolved zero entity anchors (L2 facts empty), "
    "split by whether the message looked like a question",
    ["question"],
    registry=registry,
)
# Pre-seed both series so zeros appear before the first occurrence.
for _q in ("true", "false"):
    mode3_grounding_zero_anchor_total.labels(question=_q)

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

# A2-S1b (Cycle 11 / DEFERRED 066) — outcome of each event status_effect the
# Pass-2 writer consumes. `persisted` = an :EntityStatus was merged; the two
# `skipped_*` outcomes were previously LOG-ONLY (silent on dashboards), which is
# exactly the 066 "status unresolved silently" gap — surface them as a metric so
# a producer regression (no event_order threaded / entity_ref never resolves) is
# visible as a non-zero skip rate, not buried in logs.
knowledge_extraction_status_effect_total = Counter(
    "knowledge_extraction_status_effect_total",
    "A2-S1b event status_effect outcomes in the Pass-2 writer",
    ["outcome"],
    registry=registry,
)
for _outcome in ("persisted", "skipped_no_event_order", "skipped_unresolved"):
    knowledge_extraction_status_effect_total.labels(outcome=_outcome)

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


# ── K21 — LLM memory tool calls ──────────────────────────────────────
# One counter per tool call, labelled by tool + outcome:
#   ok          — handler returned a result
#   tool_error  — bad args / business rejection (rate limit, no project
#                 in scope); the endpoint still returns HTTP 200
#   infra_error — Neo4j / Redis / unexpected failure → endpoint 503
_TOOL_NAMES = (
    "memory_search",
    "memory_recall_entity",
    "memory_timeline",
    "memory_remember",
    "memory_forget",
)
_TOOL_OUTCOMES = ("ok", "tool_error", "infra_error")

tool_calls_total = Counter(
    "knowledge_tool_calls_total",
    "K21 LLM memory tool-call terminations by tool name + outcome",
    ["tool_name", "outcome"],
    registry=registry,
)
for _t in _TOOL_NAMES:
    for _o in _TOOL_OUTCOMES:
        tool_calls_total.labels(tool_name=_t, outcome=_o)

tool_call_duration_seconds = Histogram(
    "knowledge_tool_call_duration_seconds",
    "K21 wall-time of a memory tool call",
    ["tool_name"],
    buckets=(0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
    registry=registry,
)
for _t in _TOOL_NAMES:
    tool_call_duration_seconds.labels(tool_name=_t)

tool_call_result_size_bytes = Histogram(
    "knowledge_tool_call_result_size_bytes",
    "K21 JSON-serialized byte size of a successful memory tool result",
    ["tool_name"],
    buckets=(64, 256, 1024, 4096, 16384, 65536),
    registry=registry,
)
for _t in _TOOL_NAMES:
    tool_call_result_size_bytes.labels(tool_name=_t)

# K21.7 — incremented once per memory_remember call rejected by the
# per-chat-session rate limit. Label-less: bounded cardinality.
memory_remember_rate_limited_total = Counter(
    "knowledge_memory_remember_rate_limited_total",
    "K21.7 memory_remember calls rejected by the per-session rate limit",
    registry=registry,
)
memory_remember_rate_limited_total.inc(0)


# ── Cycle 72 — Pass2 precision filter observability ────────────────────
#
# `category` cardinality is closed at 3 (entity / relation / event).
# `verdict` cardinality is closed at 5 (supported / partial / unsupported
# / unjudged / failed) — covers every value the filter can record.
# Total series: 3 × 5 = 15. Coverage gauge is 1 series per category.
knowledge_extraction_filter_decisions_total = Counter(
    "knowledge_extraction_filter_decisions_total",
    "Cycle 72 Pass2 precision filter — per-item verdicts emitted by "
    "the filter LLM (or 'unjudged' when verdict missing, 'failed' on "
    "filter degradation).",
    ["category", "verdict"],
    registry=registry,
)
for _cat in ("entity", "relation", "event"):
    for _v in ("supported", "partial", "unsupported", "unjudged", "failed"):
        knowledge_extraction_filter_decisions_total.labels(
            category=_cat, verdict=_v
        )

knowledge_extraction_filter_coverage_ratio = Gauge(
    "knowledge_extraction_filter_coverage_ratio",
    "Cycle 72 Pass2 precision filter — last-observed coverage ratio "
    "(verdicts returned / items submitted) per category. <0.9 suggests "
    "the per-batch reasoning-token budget needs tuning.",
    ["category"],
    registry=registry,
)
for _cat in ("entity", "relation", "event"):
    knowledge_extraction_filter_coverage_ratio.labels(category=_cat).set(1.0)


# ── Cycle 73d — entity recovery (3-tier) observability ────────────────
#
# `source` cardinality is closed at 4 (glossary / hints / llm / unmatched).
# `verdict` cardinality is closed at 3 (entity / abstract / unjudged).
# Total series: 4 × 3 = 12.
knowledge_extraction_recovery_decisions_total = Counter(
    "knowledge_extraction_recovery_decisions_total",
    "Cycle 73d entity recovery — per-name resolution outcomes. Source "
    "tells which tier resolved (glossary lookup, author hints, LLM "
    "classifier, or unjudged-due-to-LLM-failure). Verdict 'abstract' "
    "drops referencing relations; 'entity' promotes a new :Entity.",
    ["source", "verdict"],
    registry=registry,
)
for _src in ("glossary", "hints", "llm", "unmatched"):
    for _v in ("entity", "abstract", "unjudged"):
        knowledge_extraction_recovery_decisions_total.labels(
            source=_src, verdict=_v,
        )


# ── Cycle 73f — Pass2 precision filter runtime reload observability ──
#
# `source` cardinality is closed at 3 (api / pubsub / startup).
# `outcome` cardinality is closed at 3 (applied / rejected / failed).
# Total series: 3 × 3 = 9.
knowledge_extraction_filter_reload_total = Counter(
    "knowledge_extraction_filter_reload_total",
    "Cycle 73f Pass2 precision filter reload — per-source/outcome counts. "
    "Source: api (POST /internal/admin/precision-filter/reload), pubsub "
    "(filter-reload signal from another service), startup (lifespan GET "
    "from Redis on container boot). Outcome: applied (cache swap success), "
    "rejected (validation failure / unknown schema_version), failed "
    "(Redis I/O error / serialization error).",
    ["source", "outcome"],
    registry=registry,
)
for _src in ("api", "pubsub", "startup"):
    for _out in ("applied", "rejected", "failed"):
        knowledge_extraction_filter_reload_total.labels(
            source=_src, outcome=_out,
        )


# ── Cycle 73e — Pass2 writer autocreate observability ────────────────
#
# `role` cardinality is closed at 2 (subject / object).
# `outcome` cardinality is closed at 9:
#   - tier_a_name_repair     : in-memory chapter map matched (Tier A.1)
#   - tier_a_anchor_repair   : anchor index matched (Tier A.2; entity pre-existed)
#   - tier_b_autocreated     : Neo4j MERGE minted a new :Entity (Tier B)
#   - kind_ambiguous         : Tier A multi-kind collision; skip Tier B too
#   - noise_skipped          : char-length OR word-count heuristic fired
#   - cap_exhausted          : per-chapter cap reached; cascade-skip
#   - cap_exhausted_high_conf: cap reached AND relation confidence > 0.8 (tuning signal)
#   - invalid_name           : canonicalize_entity_name returned empty
#   - error                  : resolve_or_merge_entity raised; cascade-skip + warn
# Total series: 2 × 9 = 18.
knowledge_extraction_writer_autocreate_total = Counter(
    "knowledge_extraction_writer_autocreate_total",
    "Cycle 73e Pass2 writer autocreate — per-endpoint resolution outcomes. "
    "Role identifies subject vs object position in the relation; outcome "
    "tells which tier resolved or why we skipped. Only 'tier_b_autocreated' "
    "represents a new :Entity write to Neo4j; the rest are repairs or skips.",
    ["role", "outcome"],
    registry=registry,
)
for _role in ("subject", "object"):
    for _out in (
        "tier_a_name_repair",
        "tier_a_anchor_repair",
        "tier_b_autocreated",
        "kind_ambiguous",
        "noise_skipped",
        "cap_exhausted",
        "cap_exhausted_high_conf",
        "invalid_name",
        "error",
    ):
        knowledge_extraction_writer_autocreate_total.labels(
            role=_role, outcome=_out,
        )
