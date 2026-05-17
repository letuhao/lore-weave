"""Tests for loreweave_obs.setup_tracing (Phase 6c-γ).

OTel's global TracerProvider is set-once, so an autouse module fixture installs
ONE recording provider (with an in-memory exporter) before any test —
setup_tracing's own set_tracer_provider then no-ops, but its instrumentor calls
still route spans into our exporter.

setup_tracing mutates process-global state: it monkey-patches the httpx
transport class and spawns a BatchSpanProcessor export thread. Two autouse
function-scoped fixtures (_no_export_thread, _uninstrument_httpx) keep that from
leaking into the rest of the sdks/python suite. /review-impl(6c-γ) LOW#1.
"""

from pathlib import Path
from unittest import mock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from loreweave_obs import setup_tracing


@pytest.fixture(scope="module", autouse=True)
def span_exporter():
    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": "test"}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return exporter


@pytest.fixture(autouse=True)
def _no_export_thread():
    """setup_tracing's own BatchSpanProcessor spawns a daemon thread that
    retries OTLP delivery to a (dead, in tests) endpoint forever. Stub the
    processor class so the configured-path tests leave no lingering thread.

    Spans the behavioural tests assert on are unaffected: they reach the module
    fixture's SimpleSpanProcessor via the global provider, NOT setup_tracing's
    own processor — whose provider is orphaned anyway (set_tracer_provider is
    set-once, the module fixture already won)."""
    with mock.patch("opentelemetry.sdk.trace.export.BatchSpanProcessor"):
        yield


@pytest.fixture(autouse=True)
def _uninstrument_httpx():
    """HTTPXClientInstrumentor monkey-patches the httpx transport class
    process-wide. Undo it after every test so the patch can't leak into — and
    silently mask a regression in — the rest of the sdks/python suite."""
    yield
    instrumentor = HTTPXClientInstrumentor()
    if getattr(instrumentor, "_is_instrumented_by_opentelemetry", False):
        instrumentor.uninstrument()


def test_setup_tracing_noop_when_endpoint_unset(monkeypatch):
    """No OTEL_EXPORTER_OTLP_ENDPOINT → setup_tracing must instrument nothing."""
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    with mock.patch(
        "opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor"
    ) as httpx_inst:
        setup_tracing("svc-under-test")  # must not raise
    httpx_inst.assert_not_called()


def test_setup_tracing_configured_wires_both_instrumentors(monkeypatch):
    """Endpoint set → setup_tracing wires httpx + (when app given) FastAPI."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    app = FastAPI()
    with mock.patch(
        "opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor"
    ) as httpx_inst, mock.patch(
        "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor"
    ) as fastapi_inst:
        setup_tracing("svc-under-test", app=app)
    httpx_inst.return_value.instrument.assert_called_once()
    fastapi_inst.instrument_app.assert_called_once_with(app)


def test_setup_tracing_fastapi_emits_server_span(monkeypatch, span_exporter):
    """Behavioural (design §9 #3): after setup_tracing(app=...), a request
    emits a SERVER span."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    app = FastAPI()

    @app.get("/ping")
    def ping():
        return {"ok": True}

    setup_tracing("svc-under-test", app=app)

    span_exporter.clear()
    with TestClient(app) as client:
        assert client.get("/ping").status_code == 200
    spans = span_exporter.get_finished_spans()
    assert any(s.kind == trace.SpanKind.SERVER for s in spans), (
        "FastAPI app should emit a SERVER span after setup_tracing(app=...); "
        f"got kinds {[s.kind for s in spans]}"
    )


def test_setup_tracing_httpx_emits_client_span(monkeypatch, span_exporter):
    """Behavioural (design §9 #4): after setup_tracing(), an httpx request
    emits a CLIENT span. HTTPXClientInstrumentor wraps the transport, so the
    span is created and ended around the call whether it succeeds or fails —
    the request here targets a closed port and the connect error is expected
    and irrelevant. This is the test the mock-assertion above cannot be: only
    a real request through the default transport proves the class is patched."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    setup_tracing("svc-under-test")  # no app — httpx instrumentation only

    span_exporter.clear()
    try:
        httpx.get("http://127.0.0.1:1/", timeout=2.0)
    except httpx.HTTPError:
        pass  # connect failure expected; the CLIENT span is emitted regardless
    spans = span_exporter.get_finished_spans()
    assert any(s.kind == trace.SpanKind.CLIENT for s in spans), (
        "httpx request should emit a CLIENT span after setup_tracing(); "
        f"got kinds {[s.kind for s in spans]}"
    )


@pytest.mark.parametrize(
    "service", ["chat-service", "knowledge-service", "video-gen-service", "worker-ai"]
)
def test_python_service_wires_setup_tracing(service):
    """Source-grep regression-lock — each Python service's app/main.py imports
    AND calls setup_tracing. The 3 FastAPI services must pass `app=app` (else
    FastAPIInstrumentor never runs → no inbound SERVER span); worker-ai has no
    HTTP server and must call it with no app. Env-independent: a behavioural
    check can't work here — in the test env OTEL_EXPORTER_OTLP_ENDPOINT is
    unset → setup_tracing no-ops → the service is never instrumented. See
    design §9 #5."""
    repo_root = Path(__file__).resolve().parents[3]
    main_py = repo_root / "services" / service / "app" / "main.py"
    assert main_py.is_file(), f"{main_py} not found"
    src = main_py.read_text(encoding="utf-8")
    assert "from loreweave_obs import setup_tracing" in src, (
        f"{service}/app/main.py must import setup_tracing from loreweave_obs"
    )
    call_lines = [ln for ln in src.splitlines() if "setup_tracing(" in ln]
    assert call_lines, (
        f"{service}/app/main.py must call setup_tracing() — Phase 6c-γ"
    )
    call = call_lines[0]
    if service == "worker-ai":
        assert "app=" not in call, (
            f"worker-ai/app/main.py must call setup_tracing() with no app "
            f"argument — it has no FastAPI app (got {call.strip()!r})"
        )
    else:
        assert "app=app" in call, (
            f"{service}/app/main.py must call setup_tracing(..., app=app) — "
            f"without app=app there is no inbound SERVER span "
            f"(got {call.strip()!r})"
        )


def test_gateway_imports_tracing_first():
    """api-gateway-bff/src/main.ts must `import './tracing'` before any other
    import — Node auto-instrumentation patches modules on require, so a module
    loaded before tracing.ts's NodeSDK.start() is silently missed (design §6).
    A linter reordering imports would break tracing without this lock. The
    assertion is a containment check, not an exact match, so a quote-style
    reformat doesn't false-fail it. /review-impl(6c-γ) COSMETIC#7."""
    repo_root = Path(__file__).resolve().parents[3]
    main_ts = repo_root / "services" / "api-gateway-bff" / "src" / "main.ts"
    assert main_ts.is_file(), f"{main_ts} not found"
    imports = [
        ln.strip()
        for ln in main_ts.read_text(encoding="utf-8").splitlines()
        if ln.strip().startswith("import ")
    ]
    assert imports, "main.ts has no import statements?"
    assert "./tracing" in imports[0], (
        f"main.ts's first import must reference './tracing' (got {imports[0]!r}) "
        "— OpenTelemetry must start before @nestjs/core / http load"
    )
