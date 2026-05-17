//! Incremental SSE (`text/event-stream`) decoder — pure, no I/O.
//!
//! Separated from [`crate::client::StreamHandle`] so the byte-level parsing
//! (line buffering across arbitrary chunk boundaries, CRLF tolerance,
//! keep-alive comments, multi-`data:` frames) is unit-testable without a live
//! HTTP connection. `StreamHandle` is then a thin async loop:
//! `resp.chunk()` → [`SseDecoder::feed`] → [`SseDecoder::pop`].

use std::collections::VecDeque;

use crate::errors::LlmError;
use crate::models::StreamEvent;

/// Hard cap on the unparsed line buffer. A well-behaved gateway sends small
/// `data:` lines (each `tool_call` fragment is its own short JSON); a stream
/// that grows the buffer past this without a newline is a broken/hostile
/// upstream — terminate rather than grow toward OOM. Mirrors the Go streamer's
/// `scanner.Buffer(..., 1 MiB)` line cap (16 MiB here — generous headroom for
/// any single event the gateway could legitimately emit).
const MAX_BUFFER_BYTES: usize = 16 * 1024 * 1024;

/// Stateful decoder turning a byte stream into canonical [`StreamEvent`]s.
///
/// The SDK trusts the `event` discriminator INSIDE each frame's JSON payload
/// — not the SSE `event:` line — matching the openapi contract.
#[derive(Debug, Default)]
pub(crate) struct SseDecoder {
    /// Bytes received but not yet split into complete lines.
    buf: Vec<u8>,
    /// SSE `event:` name of the frame being assembled (diagnostic only).
    current_event: String,
    /// Concatenated `data:` payload of the frame being assembled.
    current_data: String,
    /// Whether a `data:` line has been seen for the current frame.
    have_data: bool,
    /// Decoded events ready to hand out — one fed chunk may complete several.
    ready: VecDeque<Result<StreamEvent, LlmError>>,
    /// Set once an `error` event or a parse failure terminated decoding.
    terminated: bool,
}

impl SseDecoder {
    pub(crate) fn new() -> Self {
        Self::default()
    }

    /// Feed a chunk of body bytes. The chunk may split lines or events
    /// anywhere — incomplete lines are retained until the next feed.
    pub(crate) fn feed(&mut self, bytes: &[u8]) {
        if self.terminated {
            return; // already done — drop further bytes
        }
        self.buf.extend_from_slice(bytes);
        while let Some(nl) = self.buf.iter().position(|&b| b == b'\n') {
            let mut line: Vec<u8> = self.buf.drain(..=nl).collect();
            line.pop(); // drop the '\n'
            if line.last() == Some(&b'\r') {
                line.pop(); // tolerate CRLF
            }
            self.process_line(&line);
            // A terminal frame (error event / parse failure) within this
            // chunk ends decoding — drop any remaining buffered lines so no
            // event can be yielded AFTER the terminal `Err`.
            if self.terminated {
                self.buf.clear();
                return;
            }
        }
        // Whatever is left is an incomplete line. If it has grown past the
        // cap the upstream is broken — terminate instead of growing to OOM.
        if self.buf.len() > MAX_BUFFER_BYTES {
            self.ready.push_back(Err(LlmError::StreamParse(format!(
                "SSE line exceeded {MAX_BUFFER_BYTES} bytes with no newline — upstream protocol broken"
            ))));
            self.terminated = true;
            self.buf.clear();
        }
    }

    /// Signal end-of-body: treat any leftover bytes as a final unterminated
    /// line and dispatch a frame still holding `data:`.
    pub(crate) fn finish(&mut self) {
        if self.terminated {
            return; // a terminal frame already ended decoding
        }
        if !self.buf.is_empty() {
            let mut line = std::mem::take(&mut self.buf);
            if line.last() == Some(&b'\r') {
                line.pop();
            }
            self.process_line(&line);
        }
        if self.have_data {
            self.dispatch_frame();
        }
    }

    /// Pop the next decoded event, if one is ready.
    pub(crate) fn pop(&mut self) -> Option<Result<StreamEvent, LlmError>> {
        self.ready.pop_front()
    }

    /// True once an `error` event or a parse failure terminated decoding.
    /// After this, callers should stop reading even if the body has not ended.
    pub(crate) fn terminated(&self) -> bool {
        self.terminated
    }

    fn process_line(&mut self, line: &[u8]) {
        if line.is_empty() {
            self.dispatch_frame();
            return;
        }
        if line.first() == Some(&b':') {
            return; // SSE comment / keep-alive — ignore
        }
        let s = String::from_utf8_lossy(line);
        if let Some(rest) = s.strip_prefix("event:") {
            self.current_event = rest.trim().to_string();
        } else if let Some(rest) = s.strip_prefix("data:") {
            // SSE: strip ONE optional leading space; multiple data lines in a
            // frame join with '\n'.
            let rest = rest.strip_prefix(' ').unwrap_or(rest);
            if self.have_data {
                self.current_data.push('\n');
            }
            self.current_data.push_str(rest);
            self.have_data = true;
        }
        // Other SSE fields (`id:`, `retry:`) are not used by this gateway.
    }

    /// Parse the assembled frame's `data:` payload into a `StreamEvent` and
    /// queue it. An `error` event or a parse failure terminates decoding.
    fn dispatch_frame(&mut self) {
        let had_data = self.have_data;
        let data = std::mem::take(&mut self.current_data);
        let event_name = std::mem::take(&mut self.current_event);
        self.have_data = false;
        if !had_data {
            return; // blank-line separator with no data — nothing to dispatch
        }

        let trimmed = data.trim();
        if trimmed.is_empty() {
            return;
        }
        // Defensive: the canonical gateway stream ends with `event: done`, not
        // OpenAI's `[DONE]` sentinel — but skip it rather than fail parsing.
        if trimmed == "[DONE]" {
            return;
        }

        match serde_json::from_str::<StreamEvent>(trimmed) {
            Ok(StreamEvent::Error { code, message }) => {
                self.ready
                    .push_back(Err(LlmError::GatewayErrorEvent { code, message }));
                self.terminated = true;
            }
            Ok(ev) => self.ready.push_back(Ok(ev)),
            Err(e) => {
                self.ready.push_back(Err(LlmError::StreamParse(format!(
                    "event '{event_name}': {e}: {trimmed}"
                ))));
                self.terminated = true;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Drain every event currently ready.
    fn drain(d: &mut SseDecoder) -> Vec<Result<StreamEvent, LlmError>> {
        let mut out = Vec::new();
        while let Some(e) = d.pop() {
            out.push(e);
        }
        out
    }

    #[test]
    fn decodes_a_simple_frame() {
        let mut d = SseDecoder::new();
        d.feed(b"event: token\ndata: {\"event\":\"token\",\"delta\":\"hi\"}\n\n");
        let evs = drain(&mut d);
        assert_eq!(evs.len(), 1);
        assert!(matches!(&evs[0], Ok(StreamEvent::Token { delta, .. }) if delta == "hi"));
    }

    #[test]
    fn buffers_across_chunk_boundaries_mid_line() {
        // A single frame delivered byte-group by byte-group, splitting both a
        // line and the JSON payload across feeds.
        let mut d = SseDecoder::new();
        d.feed(b"data: {\"event\":\"to");
        assert!(drain(&mut d).is_empty(), "no event until the line completes");
        d.feed(b"ken\",\"delta\":\"x\"}");
        assert!(drain(&mut d).is_empty(), "no event until the blank line");
        d.feed(b"\n\n");
        let evs = drain(&mut d);
        assert_eq!(evs.len(), 1);
        assert!(matches!(&evs[0], Ok(StreamEvent::Token { delta, .. }) if delta == "x"));
    }

    #[test]
    fn handles_multiple_events_in_one_feed() {
        let mut d = SseDecoder::new();
        d.feed(
            b"data: {\"event\":\"token\",\"delta\":\"a\"}\n\n\
              data: {\"event\":\"token\",\"delta\":\"b\"}\n\n\
              data: {\"event\":\"done\",\"finish_reason\":\"stop\"}\n\n",
        );
        let evs = drain(&mut d);
        assert_eq!(evs.len(), 3);
        assert!(matches!(&evs[2], Ok(StreamEvent::Done { .. })));
    }

    #[test]
    fn tolerates_crlf_and_keepalive_comments() {
        let mut d = SseDecoder::new();
        d.feed(b": keep-alive ping\r\ndata: {\"event\":\"token\",\"delta\":\"y\"}\r\n\r\n");
        let evs = drain(&mut d);
        assert_eq!(evs.len(), 1);
        assert!(matches!(&evs[0], Ok(StreamEvent::Token { delta, .. }) if delta == "y"));
    }

    #[test]
    fn decodes_tool_call_fragments() {
        let mut d = SseDecoder::new();
        d.feed(b"data: {\"event\":\"tool_call\",\"index\":0,\"id\":\"c1\",\"name\":\"t\",\"arguments_delta\":\"\"}\n\n");
        d.feed(b"data: {\"event\":\"tool_call\",\"arguments_delta\":\"{}\"}\n\n");
        let evs = drain(&mut d);
        assert_eq!(evs.len(), 2);
        assert!(matches!(&evs[0], Ok(StreamEvent::ToolCall { id, .. }) if id.as_deref() == Some("c1")));
        assert!(
            matches!(&evs[1], Ok(StreamEvent::ToolCall { arguments_delta, .. }) if arguments_delta == "{}")
        );
    }

    #[test]
    fn error_event_terminates_with_err() {
        let mut d = SseDecoder::new();
        d.feed(b"data: {\"event\":\"error\",\"code\":\"LLM_RATE_LIMITED\",\"message\":\"slow\"}\n\n");
        let evs = drain(&mut d);
        assert_eq!(evs.len(), 1);
        assert!(matches!(&evs[0], Err(LlmError::GatewayErrorEvent { code, .. }) if code == "LLM_RATE_LIMITED"));
        assert!(d.terminated());
    }

    #[test]
    fn no_events_leak_after_a_terminal_error_in_the_same_chunk() {
        // One chunk carries an `error` frame followed by a `token` frame.
        // The error is terminal — the trailing token must NOT be yielded.
        let mut d = SseDecoder::new();
        d.feed(
            b"data: {\"event\":\"error\",\"code\":\"LLM_X\",\"message\":\"m\"}\n\n\
              data: {\"event\":\"token\",\"delta\":\"leaked?\"}\n\n",
        );
        let evs = drain(&mut d);
        assert_eq!(evs.len(), 1, "only the error — the trailing token must be dropped");
        assert!(matches!(&evs[0], Err(LlmError::GatewayErrorEvent { .. })));
        assert!(d.terminated());
    }

    #[test]
    fn malformed_json_terminates_with_parse_err() {
        let mut d = SseDecoder::new();
        d.feed(b"data: {not json}\n\n");
        let evs = drain(&mut d);
        assert_eq!(evs.len(), 1);
        assert!(matches!(&evs[0], Err(LlmError::StreamParse(_))));
        assert!(d.terminated());
    }

    #[test]
    fn finish_flushes_a_frame_with_no_trailing_blank_line() {
        let mut d = SseDecoder::new();
        d.feed(b"data: {\"event\":\"done\",\"finish_reason\":\"stop\"}");
        assert!(drain(&mut d).is_empty(), "not dispatched until finish()");
        d.finish();
        let evs = drain(&mut d);
        assert_eq!(evs.len(), 1);
        assert!(matches!(&evs[0], Ok(StreamEvent::Done { .. })));
    }

    #[test]
    fn unbounded_line_terminates_instead_of_growing() {
        // A hostile/broken upstream streams past the cap with no newline —
        // the decoder must terminate with an error, not grow toward OOM.
        let mut d = SseDecoder::new();
        d.feed(&vec![b'x'; MAX_BUFFER_BYTES + 1]);
        let evs = drain(&mut d);
        assert_eq!(evs.len(), 1);
        assert!(matches!(&evs[0], Err(LlmError::StreamParse(_))));
        assert!(d.terminated());
        // Once terminated, further feeds are dropped.
        d.feed(b"data: {\"event\":\"token\",\"delta\":\"x\"}\n\n");
        assert!(drain(&mut d).is_empty());
    }

    #[test]
    fn skips_done_sentinel() {
        let mut d = SseDecoder::new();
        d.feed(b"data: [DONE]\n\n");
        assert!(drain(&mut d).is_empty(), "[DONE] sentinel produces no event");
        assert!(!d.terminated(), "[DONE] is not a parse failure");
    }
}
