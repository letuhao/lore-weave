"""Unit test for K6.5 /metrics endpoint.

Exercises the FastAPI route directly via the router — no DB pool,
no glossary client, no lifespan. Uses FastAPI's TestClient to get a
synchronous HTTP interface over the router.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.metrics import layer_timeout_total
from app.routers.metrics import router as metrics_router


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(metrics_router)
    return app


def test_metrics_endpoint_returns_prometheus_format():
    client = TestClient(_app())
    resp = client.get("/metrics")

    assert resp.status_code == 200
    # prometheus_client emits 'text/plain; version=0.0.4; charset=utf-8'.
    assert resp.headers["content-type"].startswith("text/plain")
    # All K6 metric names should appear in the scrape output, even
    # with zero observations (Counters/Gauges are eagerly registered).
    body = resp.text
    assert "knowledge_layer_timeout_total" in body
    assert "knowledge_cache_hit_total" in body
    assert "knowledge_cache_miss_total" in body
    assert "knowledge_circuit_open" in body
    assert "knowledge_context_build_duration_seconds" in body


def test_metrics_endpoint_reflects_counter_increments():
    client = TestClient(_app())

    layer_timeout_total.labels(layer="l0").inc()
    resp = client.get("/metrics")

    assert resp.status_code == 200
    # After inc(), the counter line for layer="l0" should be >= 1.
    lines = [
        line
        for line in resp.text.splitlines()
        if line.startswith("knowledge_layer_timeout_total{layer=\"l0\"}")
    ]
    assert lines, "expected a knowledge_layer_timeout_total line for layer=l0"
    value = float(lines[-1].rsplit(" ", 1)[-1])
    assert value >= 1.0
