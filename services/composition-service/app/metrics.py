"""Prometheus metrics registry for composition-service.

Module-level CollectorRegistry (not the prometheus_client default) so tests
can reset without disturbing other processes and the scrape stays lean.
M0 ships only a process-up gauge; milestones add packer/engine counters.
"""

from prometheus_client import CollectorRegistry, Gauge

__all__ = ["registry", "service_up"]

registry = CollectorRegistry()

service_up = Gauge(
    "composition_service_up",
    "1 while the composition-service process is serving",
    registry=registry,
)
service_up.set(1)
