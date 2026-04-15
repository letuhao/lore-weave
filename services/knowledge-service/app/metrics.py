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
