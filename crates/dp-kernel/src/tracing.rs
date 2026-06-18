//! Cycle 32 / L7.G — Rust mirror of `contracts/tracing/`.
//!
//! Q-L4-1 parity goal: W3C `traceparent` wire-form and `SamplingDecision`/
//! `SpanKind`/`Status` enum string-form must be byte-for-byte identical
//! with the Go contracts.
//!
//! Same pattern as the cycle-22 PII SDK mirror: foundation ships the
//! interface; service code binds an OTel SDK adapter at the boundary
//! (Q-L4D-1 OPAQUE-payload pattern).
//!
//! No `tracing` (the OTel-style logging crate) integration here — that
//! would create a dep cycle with the `tracing-subscriber` ecosystem;
//! services wire their own adapter.

use std::sync::Mutex;

// ── TraceContext ───────────────────────────────────────────────────────────

/// Typed view of W3C Trace Context (16-byte trace_id + 8-byte span_id + flags).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct TraceContext {
    pub trace_id: [u8; 16],
    pub span_id: [u8; 8],
    pub flags: u8,
}

impl TraceContext {
    pub fn sampled(&self) -> bool {
        self.flags & 0x01 == 0x01
    }

    pub fn is_zero(&self) -> bool {
        self.trace_id.iter().all(|&b| b == 0) && self.span_id.iter().all(|&b| b == 0)
    }

    pub fn trace_id_hex(&self) -> String {
        hex_encode(&self.trace_id)
    }

    pub fn span_id_hex(&self) -> String {
        hex_encode(&self.span_id)
    }
}

fn hex_encode(b: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(b.len() * 2);
    for &x in b {
        out.push(HEX[(x >> 4) as usize] as char);
        out.push(HEX[(x & 0x0f) as usize] as char);
    }
    out
}

fn hex_decode(s: &str) -> Option<Vec<u8>> {
    if s.len() % 2 != 0 {
        return None;
    }
    let bytes = s.as_bytes();
    let mut out = Vec::with_capacity(s.len() / 2);
    for i in (0..bytes.len()).step_by(2) {
        let hi = decode_nibble(bytes[i])?;
        let lo = decode_nibble(bytes[i + 1])?;
        out.push((hi << 4) | lo);
    }
    Some(out)
}

fn decode_nibble(c: u8) -> Option<u8> {
    match c {
        b'0'..=b'9' => Some(c - b'0'),
        b'a'..=b'f' => Some(c - b'a' + 10),
        // Reject uppercase — W3C requires lowercase.
        _ => None,
    }
}

/// Errors from [`parse_traceparent`].
#[derive(Debug, PartialEq, Eq)]
pub enum TraceParentError {
    Invalid,
    ZeroTraceId,
    ZeroSpanId,
}

impl std::fmt::Display for TraceParentError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Invalid => write!(f, "tracing: invalid W3C traceparent"),
            Self::ZeroTraceId => write!(f, "tracing: trace_id must not be all zeros"),
            Self::ZeroSpanId => write!(f, "tracing: parent_id must not be all zeros"),
        }
    }
}

impl std::error::Error for TraceParentError {}

/// Format a TraceContext into the W3C `traceparent` 55-char wire form.
/// Returns empty string for a zero context.
pub fn format_traceparent(tc: &TraceContext) -> String {
    if tc.is_zero() {
        return String::new();
    }
    format!(
        "00-{}-{}-{:02x}",
        tc.trace_id_hex(),
        tc.span_id_hex(),
        tc.flags
    )
}

/// Parse a 55-char W3C `traceparent` string into a TraceContext.
pub fn parse_traceparent(s: &str) -> Result<TraceContext, TraceParentError> {
    if s.len() != 55 {
        return Err(TraceParentError::Invalid);
    }
    let parts: Vec<&str> = s.split('-').collect();
    if parts.len() != 4 {
        return Err(TraceParentError::Invalid);
    }
    if parts[0] != "00" {
        return Err(TraceParentError::Invalid);
    }
    if parts[1].len() != 32 || parts[2].len() != 16 || parts[3].len() != 2 {
        return Err(TraceParentError::Invalid);
    }
    let tcid = hex_decode(parts[1]).ok_or(TraceParentError::Invalid)?;
    let sid = hex_decode(parts[2]).ok_or(TraceParentError::Invalid)?;
    let flags = hex_decode(parts[3]).ok_or(TraceParentError::Invalid)?;
    let mut tc = TraceContext::default();
    tc.trace_id.copy_from_slice(&tcid);
    tc.span_id.copy_from_slice(&sid);
    tc.flags = flags[0];

    if tc.trace_id.iter().all(|&b| b == 0) {
        return Err(TraceParentError::ZeroTraceId);
    }
    if tc.span_id.iter().all(|&b| b == 0) {
        return Err(TraceParentError::ZeroSpanId);
    }
    Ok(tc)
}

// ── SpanKind / Status ──────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum SpanKind {
    #[default]
    Internal,
    Server,
    Client,
    Producer,
    Consumer,
}

impl SpanKind {
    /// Stable wire-form. Must match Go `SpanKind.String()`.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Internal => "internal",
            Self::Server => "server",
            Self::Client => "client",
            Self::Producer => "producer",
            Self::Consumer => "consumer",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum Status {
    #[default]
    Unset,
    Ok,
    Error,
}

impl Status {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Unset => "unset",
            Self::Ok => "ok",
            Self::Error => "error",
        }
    }
}

// ── Sampling ───────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SamplingDecision {
    Drop,
    Record,
    RecordAndSample,
}

impl SamplingDecision {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Drop => "drop",
            Self::Record => "record",
            Self::RecordAndSample => "record_and_sample",
        }
    }
}

#[derive(Debug, Clone, Copy, Default)]
pub struct SamplingHint {
    pub force: bool,
    pub drop: bool,
}

pub trait Sampler: Send + Sync {
    fn should_sample(&self, parent: &TraceContext, span_name: &str, hint: SamplingHint) -> SamplingDecision;
}

pub struct AlwaysOnSampler;
impl Sampler for AlwaysOnSampler {
    fn should_sample(&self, _: &TraceContext, _: &str, _: SamplingHint) -> SamplingDecision {
        SamplingDecision::RecordAndSample
    }
}

pub struct AlwaysOffSampler;
impl Sampler for AlwaysOffSampler {
    fn should_sample(&self, _: &TraceContext, _: &str, _: SamplingHint) -> SamplingDecision {
        SamplingDecision::Drop
    }
}

// ── Span name validation ───────────────────────────────────────────────────

/// Validate that name matches the cycle-19 span-name convention:
/// `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$`.
pub fn validate_span_name(name: &str) -> Result<(), &'static str> {
    if name.is_empty() {
        return Err("tracing: span name must not be empty");
    }
    let mut segment_started = false;
    let mut first_in_segment = true;
    for c in name.chars() {
        if c == '.' {
            if !segment_started {
                return Err("tracing: span name has empty segment");
            }
            segment_started = false;
            first_in_segment = true;
            continue;
        }
        segment_started = true;
        if first_in_segment {
            // First char of segment: must be lowercase letter.
            if !(c.is_ascii_lowercase()) {
                return Err("tracing: span name segment must start with lowercase letter");
            }
            first_in_segment = false;
        } else {
            // Subsequent chars: lowercase letter, digit, or underscore.
            if !(c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_') {
                return Err("tracing: span name contains invalid character");
            }
        }
    }
    if !segment_started {
        return Err("tracing: span name has empty trailing segment");
    }
    Ok(())
}

// ── Span / Exporter / Tracer ───────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct SpanSnapshot {
    pub trace_id: [u8; 16],
    pub span_id: [u8; 8],
    pub name: String,
    pub kind: SpanKind,
    pub status: Status,
    pub attributes: Vec<(String, String)>,
}

pub trait Exporter: Send + Sync {
    fn export(&self, snapshot: SpanSnapshot);
}

pub struct NoopExporter;
impl Exporter for NoopExporter {
    fn export(&self, _: SpanSnapshot) {}
}

pub struct InMemoryExporter {
    capacity: usize,
    inner: Mutex<Vec<SpanSnapshot>>,
    dropped: Mutex<usize>,
}

impl InMemoryExporter {
    pub fn new(capacity: usize) -> Self {
        let cap = if capacity == 0 { 1024 } else { capacity };
        Self {
            capacity: cap,
            inner: Mutex::new(Vec::new()),
            dropped: Mutex::new(0),
        }
    }

    pub fn spans(&self) -> Vec<SpanSnapshot> {
        self.inner.lock().unwrap().clone()
    }

    pub fn len(&self) -> usize {
        self.inner.lock().unwrap().len()
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    pub fn dropped(&self) -> usize {
        *self.dropped.lock().unwrap()
    }
}

impl Exporter for InMemoryExporter {
    fn export(&self, snapshot: SpanSnapshot) {
        let mut inner = self.inner.lock().unwrap();
        if inner.len() >= self.capacity {
            inner.remove(0);
            *self.dropped.lock().unwrap() += 1;
        }
        inner.push(snapshot);
    }
}

// ── Tests ──────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn format_and_parse_traceparent_roundtrip() {
        let tc = TraceContext {
            trace_id: [0x12; 16],
            span_id: [0x34; 8],
            flags: 0x01,
        };
        let s = format_traceparent(&tc);
        assert_eq!(s.len(), 55);
        let parsed = parse_traceparent(&s).unwrap();
        assert_eq!(parsed, tc);
        assert!(parsed.sampled());
    }

    #[test]
    fn format_traceparent_zero_returns_empty() {
        assert_eq!(format_traceparent(&TraceContext::default()), "");
    }

    #[test]
    fn parse_traceparent_rejects() {
        // wrong length
        assert!(parse_traceparent("00-aa-bb-01").is_err());
        // wrong version
        let bad = format!("01-{}-{}-01", "a".repeat(32), "b".repeat(16));
        assert!(parse_traceparent(&bad).is_err());
        // uppercase
        let bad = format!("00-{}-{}-01", "A".repeat(32), "b".repeat(16));
        assert!(parse_traceparent(&bad).is_err());
        // zero trace_id
        let bad = format!("00-{}-{}-01", "0".repeat(32), "b".repeat(16));
        assert_eq!(parse_traceparent(&bad), Err(TraceParentError::ZeroTraceId));
        // zero span_id
        let bad = format!("00-{}-{}-01", "a".repeat(32), "0".repeat(16));
        assert_eq!(parse_traceparent(&bad), Err(TraceParentError::ZeroSpanId));
    }

    // Cross-language wire-form parity tests — these LOCK the strings.
    #[test]
    fn span_kind_as_str_parity_with_go() {
        assert_eq!(SpanKind::Internal.as_str(), "internal");
        assert_eq!(SpanKind::Server.as_str(), "server");
        assert_eq!(SpanKind::Client.as_str(), "client");
        assert_eq!(SpanKind::Producer.as_str(), "producer");
        assert_eq!(SpanKind::Consumer.as_str(), "consumer");
    }

    #[test]
    fn status_as_str_parity_with_go() {
        assert_eq!(Status::Unset.as_str(), "unset");
        assert_eq!(Status::Ok.as_str(), "ok");
        assert_eq!(Status::Error.as_str(), "error");
    }

    #[test]
    fn sampling_decision_as_str_parity_with_go() {
        assert_eq!(SamplingDecision::Drop.as_str(), "drop");
        assert_eq!(SamplingDecision::Record.as_str(), "record");
        assert_eq!(
            SamplingDecision::RecordAndSample.as_str(),
            "record_and_sample"
        );
    }

    #[test]
    fn trace_context_is_zero_and_sampled() {
        assert!(TraceContext::default().is_zero());
        let mut tc = TraceContext::default();
        tc.trace_id[0] = 1;
        assert!(!tc.is_zero());
        assert!(!tc.sampled());
        tc.flags = 0x01;
        assert!(tc.sampled());
    }

    #[test]
    fn validate_span_name_accepts_valid() {
        for n in ["auth.handler.login", "meta_worker.write", "single", "a.b.c"] {
            assert!(validate_span_name(n).is_ok(), "good name rejected: {n}");
        }
    }

    #[test]
    fn validate_span_name_rejects_invalid() {
        for n in [
            "",
            "Auth.handler",
            "auth-handler",
            ".starts.with.dot",
            "ends.with.dot.",
            "two..dots",
            "1starts_with_digit",
        ] {
            assert!(
                validate_span_name(n).is_err(),
                "bad name accepted: {n}"
            );
        }
    }

    #[test]
    fn always_on_sampler() {
        let s = AlwaysOnSampler;
        let d = s.should_sample(&TraceContext::default(), "x.y", SamplingHint::default());
        assert_eq!(d, SamplingDecision::RecordAndSample);
    }

    #[test]
    fn always_off_sampler() {
        let s = AlwaysOffSampler;
        let d = s.should_sample(
            &TraceContext::default(),
            "x.y",
            SamplingHint { force: true, drop: false },
        );
        assert_eq!(d, SamplingDecision::Drop);
    }

    #[test]
    fn in_memory_exporter_ring_eviction() {
        let exp = InMemoryExporter::new(2);
        for _ in 0..5 {
            exp.export(SpanSnapshot {
                trace_id: [0; 16],
                span_id: [0; 8],
                name: "x".to_string(),
                kind: SpanKind::Internal,
                status: Status::Unset,
                attributes: vec![],
            });
        }
        assert_eq!(exp.len(), 2);
        assert_eq!(exp.dropped(), 3);
    }

    #[test]
    fn noop_exporter_no_panic() {
        NoopExporter.export(SpanSnapshot {
            trace_id: [0; 16],
            span_id: [0; 8],
            name: "x".to_string(),
            kind: SpanKind::Internal,
            status: Status::Unset,
            attributes: vec![],
        });
    }

    #[test]
    fn trace_parent_error_display() {
        assert!(TraceParentError::Invalid.to_string().contains("traceparent"));
        assert!(TraceParentError::ZeroTraceId.to_string().contains("zeros"));
        assert!(TraceParentError::ZeroSpanId.to_string().contains("zeros"));
    }
}
