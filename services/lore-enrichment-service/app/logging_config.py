"""lore-enrichment-service structured logging — thin adapter over the shared installer.

P2·A2a: the RedactFilter / ContextFilter / JSON handler and the canonical
``trace_id_var`` now live ONCE in ``loreweave_obs.logging_setup`` (dual-emitting
the OTel ``otel_trace_id`` alongside the bespoke ``trace_id`` so logs join Tempo).
The shared installer already merged this service's SUPERSET redactor (the generic
``api-key=…`` / ``token:…`` / ``secret=…`` / ``password:…`` catch-all), so the
redaction logic is no longer duplicated here.

This module keeps the ``app.logging_config`` import path stable — main, the
TraceIdMiddleware and the grant client import ``trace_id_var`` / ``new_trace_id``
from here — and OWNS the two lore-enrichment-specific correlation ContextVars
(``job_id_var`` / ``stage_var``, set by the C14 runner around a job's per-gap
stages), passing them to the shared installer via ``extra_context`` so a single
enrichment job stays followable end-to-end (gap-detect → retrieval → generate →
verify → persist).
"""

from __future__ import annotations

from contextvars import ContextVar

from loreweave_obs import new_trace_id, trace_id_var
from loreweave_obs import setup_logging as _setup_logging

#: Per-job correlation id (set by the C14 runner around a job). Empty otherwise.
#: lore-enrichment-specific — not defined by the shared installer.
job_id_var: ContextVar[str] = ContextVar("job_id", default="")
#: Current pipeline stage (gap-detect / retrieval / generate / verify / persist).
#: lore-enrichment-specific — not defined by the shared installer.
stage_var: ContextVar[str] = ContextVar("stage", default="")

__all__ = ["setup_logging", "trace_id_var", "new_trace_id", "job_id_var", "stage_var"]


def setup_logging(level: str = "INFO") -> None:
    """Install the shared JSON logging handler, bound to this service's name.

    Passes the two lore-enrichment correlation ContextVars via ``extra_context``
    so ``job_id`` / ``stage`` are stamped on every record alongside ``trace_id``.
    """
    _setup_logging(
        "lore-enrichment-service",
        level=level,
        extra_context={"job_id": job_id_var, "stage": stage_var},
    )
