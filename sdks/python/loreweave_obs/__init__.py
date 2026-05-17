"""loreweave_obs — the LoreWeave shared OpenTelemetry tracing helper (Phase 6c-γ).

One `setup_tracing()` call per Python service — at FastAPI app creation for the
HTTP services, or at the top of a worker's `main()`. Mirrors the Go
`observability.InitTracer`.
"""

import os

__all__ = ["setup_tracing"]


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
