//! Structured logging + cross-service trace-id propagation.
//!
//! `init_tracing(service)` installs a JSON subscriber that stamps every log
//! line with the service name; `propagate` is an axum middleware that reads
//! (or mints) an `X-Trace-Id`, wraps the request in a span carrying it, and
//! echoes it on the response — so a Rust hop stitches into the platform's
//! cross-service traces (chat → knowledge already propagate this header).

use axum::extract::Request;
use axum::http::{HeaderName, HeaderValue};
use axum::middleware::Next;
use axum::response::Response;
use tracing::Instrument;
use tracing_subscriber::EnvFilter;
use uuid::Uuid;

const TRACE_HEADER: HeaderName = HeaderName::from_static("x-trace-id");

/// The resolved trace id for a request, injected as an extension so handlers
/// / error paths can read it.
#[derive(Clone, Debug)]
pub struct TraceId(pub String);

/// Install the JSON tracing subscriber. `service` is attached to every line
/// (`fields.service`). Idempotent-safe to call once at startup; respects
/// `RUST_LOG`, defaulting to `info`.
pub fn init_tracing(service: &'static str) {
    let filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));
    let _ = tracing_subscriber::fmt()
        .json()
        .with_env_filter(filter)
        .with_current_span(true)
        .with_span_list(false)
        .with_target(true)
        .try_init();
    tracing::info!(service, "tracing initialized (json)");
}

/// Axum middleware: propagate `X-Trace-Id` in and out, wrapping the request
/// in a span carrying the id. Apply once, outermost (so every handler + the
/// access log share the id).
pub async fn propagate(mut req: Request, next: Next) -> Response {
    let trace_id = req
        .headers()
        .get(&TRACE_HEADER)
        .and_then(|v| v.to_str().ok())
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
        .unwrap_or_else(|| Uuid::new_v4().to_string());

    req.extensions_mut().insert(TraceId(trace_id.clone()));

    let method = req.method().clone();
    let path = req.uri().path().to_owned();
    let span = tracing::info_span!("http", trace_id = %trace_id, method = %method, path = %path);

    let mut resp = next.run(req).instrument(span).await;
    if let Ok(value) = HeaderValue::from_str(&trace_id) {
        resp.headers_mut().insert(TRACE_HEADER, value);
    }
    resp
}
