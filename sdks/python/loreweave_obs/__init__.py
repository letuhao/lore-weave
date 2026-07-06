"""loreweave_obs — the LoreWeave shared OpenTelemetry tracing helper (Phase 6c-γ).

One `setup_tracing()` call per Python service — at FastAPI app creation for the
HTTP services, or at the top of a worker's `main()`. Mirrors the Go
`observability.InitTracer`.
"""

import os

__all__ = [
    "setup_tracing",
    "current_otel_trace_id",
    "setup_logging",
    "trace_id_var",
    "new_trace_id",
    "RedactFilter",
    "ContextFilter",
]


def current_otel_trace_id() -> str:
    """Return the 32-char hex OTel trace id for the in-flight span, or "".

    D-PHASE6C-TRACE-ID-UNIFY companion helper. The service-level
    ``TraceIdMiddleware`` issues its own ``X-Trace-Id`` (uuid4 hex)
    that 500 handlers embed in the response body so a user staring at
    a UI error can grep server logs. That id is UNRELATED to the OTel
    trace id that Grafana Tempo indexes by — copying ``X-Trace-Id``
    off a 500 and pasting it into Tempo finds nothing. This helper
    pulls the OTel trace id so the 500 handler can emit BOTH ids:
    ``trace_id`` (logs) + ``otel_trace_id`` (Tempo).

    Returns "" when:
      - OTel tracing is not configured (``OTEL_EXPORTER_OTLP_ENDPOINT``
        unset → ``setup_tracing`` was a no-op → ``get_current_span``
        returns the NoOp span with an INVALID context). Same return
        path as "called outside any request scope" — callers cannot
        and need not distinguish.
      - ``opentelemetry`` is not installed (defensive import; the SDK
        is normally pulled in by ``setup_tracing``'s lazy imports but
        a stripped-down deployment might skip it).

    Safe to call from any async/sync context; reads the current span
    from the global tracer provider, no I/O.
    """
    try:
        from opentelemetry import trace
    except ImportError:
        return ""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    # `is_valid` is False for the OTel NoOp span (returned when no
    # provider is set OR no span is active). 0 is the sentinel "no
    # trace" value; defensive check survives any future API drift.
    if not ctx.is_valid or ctx.trace_id == 0:
        return ""
    return format(ctx.trace_id, "032x")


def setup_tracing(service_name: str, app=None) -> None:
    """Configure OpenTelemetry tracing for a LoreWeave service.

    No-op when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is unset — dev without the
    observability stack still runs (same contract as Go's ``InitTracer``).

    When configured: installs a ``TracerProvider`` (resource ``service.name``)
    + an OTLP/HTTP span exporter + a ``BatchSpanProcessor``; instruments httpx
    process-wide (covers every service HTTP client AND the ``loreweave_llm``
    SDK's httpx client); and, when ``app`` is a FastAPI instance, instruments
    it for inbound SERVER spans.

    OTel Python's default propagator is already W3C ``tracecontext,baggage`` —
    no explicit propagator install is needed.
    """
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return  # no-op — observability stack not wired

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name})
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    # Patches the httpx transport class process-wide — covers every client,
    # including the loreweave_llm SDK's, regardless of construction order.
    HTTPXClientInstrumentor().instrument()

    if app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)


# Imported at the bottom so current_otel_trace_id / setup_tracing are already
# defined on the package: logging_setup's ContextFilter lazy-imports
# current_otel_trace_id at log time, so no import cycle either way.
from loreweave_obs.logging_setup import (  # noqa: E402
    ContextFilter,
    RedactFilter,
    new_trace_id,
    setup_logging,
    trace_id_var,
)
