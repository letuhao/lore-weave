//! Prometheus request metrics + `/metrics` exposition.
//!
//! `record` is an axum middleware counting requests + observing latency,
//! labelled by method + status (NOT path — path is high-cardinality). `render`
//! is the `/metrics` handler wired by [`crate::health::routes`].

use std::sync::OnceLock;
use std::time::Instant;

use axum::extract::Request;
use axum::http::header::CONTENT_TYPE;
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use prometheus::{Encoder, HistogramVec, IntCounterVec, Registry, TextEncoder};

struct Metrics {
    registry: Registry,
    requests: IntCounterVec,
    latency: HistogramVec,
}

static METRICS: OnceLock<Metrics> = OnceLock::new();

fn metrics() -> &'static Metrics {
    METRICS.get_or_init(|| {
        let registry = Registry::new();
        let requests = IntCounterVec::new(
            prometheus::Opts::new("http_requests_total", "Total HTTP requests"),
            &["method", "status"],
        )
        .expect("valid counter");
        let latency = HistogramVec::new(
            prometheus::HistogramOpts::new(
                "http_request_duration_seconds",
                "HTTP request latency in seconds",
            ),
            &["method"],
        )
        .expect("valid histogram");
        registry.register(Box::new(requests.clone())).expect("register counter");
        registry.register(Box::new(latency.clone())).expect("register histogram");
        Metrics { registry, requests, latency }
    })
}

/// Axum middleware: count requests + observe latency. Apply once.
pub async fn record(req: Request, next: Next) -> Response {
    let method = req.method().as_str().to_owned();
    let start = Instant::now();
    let resp = next.run(req).await;
    let status = resp.status().as_u16().to_string();
    let m = metrics();
    m.requests.with_label_values(&[&method, &status]).inc();
    m.latency.with_label_values(&[&method]).observe(start.elapsed().as_secs_f64());
    resp
}

/// `GET /metrics` — prometheus text exposition.
pub async fn render() -> Response {
    let m = metrics();
    let mut buf = Vec::new();
    let encoder = TextEncoder::new();
    if encoder.encode(&m.registry.gather(), &mut buf).is_err() {
        return crate::error::ProblemDetails::internal("failed to encode metrics").into_response();
    }
    ([(CONTENT_TYPE, "text/plain; version=0.0.4")], buf).into_response()
}
