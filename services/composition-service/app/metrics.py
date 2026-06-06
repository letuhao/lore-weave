"""Prometheus metrics registry for composition-service.

Module-level CollectorRegistry (not the prometheus_client default) so tests
can reset without disturbing other processes and the scrape stays lean.
M0 ships only a process-up gauge; milestones add packer/engine counters.
"""

from prometheus_client import CollectorRegistry, Counter, Gauge

__all__ = [
    "registry", "service_up",
    "llm_job_total", "llm_inflight_jobs",
]

registry = CollectorRegistry()

service_up = Gauge(
    "composition_service_up",
    "1 while the composition-service process is serving",
    registry=registry,
)
service_up.set(1)

# LLM gateway job outcomes (M3 llm_client → M6 engine/critic). `outcome` ∈
# {completed, failed, cancelled, transient_retry, http_retry, sdk_error}.
llm_job_total = Counter(
    "composition_llm_job_total",
    "loreweave_llm gateway jobs by operation + terminal outcome",
    ["operation", "outcome"],
    registry=registry,
)
llm_inflight_jobs = Gauge(
    "composition_llm_inflight_jobs",
    "loreweave_llm gateway jobs currently awaiting a terminal status",
    registry=registry,
)
