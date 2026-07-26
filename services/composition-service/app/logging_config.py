"""composition-service structured logging — thin adapter over the shared installer.

P2·A2a: the RedactFilter / ContextFilter / JSON handler and the canonical
``trace_id_var`` now live ONCE in ``loreweave_obs.logging_setup`` (dual-emitting
the OTel ``otel_trace_id`` alongside the bespoke ``trace_id`` so logs join Tempo).
This module keeps the ``app.logging_config`` import path stable — the client HTTP
wrappers + the TraceIdMiddleware import ``trace_id_var`` / ``new_trace_id`` from
here — and binds the service name to the shared installer.
"""

from loreweave_obs import new_trace_id, trace_id_var
from loreweave_obs import setup_logging as _setup_logging

__all__ = ["setup_logging", "trace_id_var", "new_trace_id"]


def setup_logging(level: str = "INFO") -> None:
    """Install the shared JSON logging handler, bound to this service's name."""
    _setup_logging("composition-service", level=level)
