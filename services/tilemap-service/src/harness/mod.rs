//! L3 zone-classifier harness — the single gateway call + the measurement
//! report.
//!
//! [`call_l3_attempt`] sends one L3 zone-classification request (TMP_008b §3
//! tool + §9.1 few-shot prompt) through the LLM gateway with a forced
//! `tool_choice` and reassembles the streamed `tool_call` fragments.
//! [`run_l3_measurement`] wraps it with the §12 token-cost report; the §5
//! per-object retry loop (`retry.rs`) and §6 fallback build on the same call.

pub mod bootstrap;
pub mod keyphrase;
pub mod l4_prompt;
pub mod l4_retry;
pub mod l4_validate;
pub mod prompt;
pub mod retry;
pub mod style;
pub mod validate;

use loreweave_llm::{
    ChatStreamRequest, GatewayClient, ModelSource, StreamEvent, StreamFormat, ToolCallAccumulator,
};
use serde_json::json;
use uuid::Uuid;

use validate::{L3Classification, L3ToolArguments, L3ValidationError, validate_l3};

/// Anthropic Haiku 4.5 hypothetical rates (TMP_008b §12.3) — used only to
/// express the lmstudio token counts as a "what this would cost on Haiku"
/// comparison. The live lmstudio run itself is local + free.
const HAIKU_INPUT_USD_PER_1M: f64 = 1.0;
const HAIKU_OUTPUT_USD_PER_1M: f64 = 5.0;

/// Outcome of one L3 measurement run.
#[derive(Debug)]
pub struct L3MeasurementReport {
    /// True when a tool call was returned, parsed, and yielded ≥1 classification.
    pub tool_use_success: bool,
    /// `finish_reason` from the terminal `done` event, if any.
    pub finish_reason: Option<String>,
    /// Number of distinct `tool_call` indices the gateway streamed.
    pub tool_calls_seen: usize,
    /// Number of classifications parsed from the tool-call arguments.
    pub classifications_parsed: usize,
    /// TMP_008b §4.1 R1-R5 validation failures against the fixture input.
    pub validation_errors: Vec<L3ValidationError>,
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub reasoning_tokens: Option<u32>,
    /// Raw reassembled tool-call arguments JSON (for diagnosis).
    pub raw_arguments: String,
    /// Set when the stream terminated with an error, or the tool call could
    /// not be parsed. Phase 0b records failure honestly — it does not panic.
    pub failure: Option<String>,
}

impl L3MeasurementReport {
    /// Equivalent cost had this run gone through Anthropic Haiku 4.5
    /// (TMP_008b §12 comparison baseline). The live lmstudio run is free.
    pub fn est_haiku_cost_usd(&self) -> f64 {
        (self.input_tokens as f64 / 1_000_000.0) * HAIKU_INPUT_USD_PER_1M
            + (self.output_tokens as f64 / 1_000_000.0) * HAIKU_OUTPUT_USD_PER_1M
    }
}

/// The outcome of a single L3 gateway call ([`call_l3_attempt`]).
///
/// Every failure mode — stream open error, mid-stream error, missing or
/// unparseable tool call — is captured in `failure` with empty
/// `classifications`; the call itself never returns `Err` (the §5 retry loop
/// treats a failed attempt as "nothing classified" — spec D1/D2).
#[derive(Debug, Default)]
pub struct L3Attempt {
    pub classifications: Vec<L3Classification>,
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub reasoning_tokens: Option<u32>,
    pub finish_reason: Option<String>,
    pub tool_calls_seen: usize,
    pub raw_arguments: String,
    pub failure: Option<String>,
}

/// Run ONE L3 gateway call for `placeholders` (TMP_008b §3 tool + forced
/// `tool_choice`). On a retry attempt, `retry_context` carries the §4.2
/// structured error message — appended as an extra user turn so the model sees
/// the exact failing cases. Reassembles the streamed tool call and parses the
/// classifications; all failures land in [`L3Attempt::failure`] (never `Err`).
pub async fn call_l3_attempt(
    client: &GatewayClient,
    model_source: ModelSource,
    model_ref: Uuid,
    user_id: Uuid,
    placeholders: &[prompt::L3Placeholder],
    retry_context: Option<&str>,
) -> L3Attempt {
    let mut messages = vec![
        json!({"role": "system", "content": prompt::SYSTEM_PROMPT}),
        json!({"role": "user", "content": prompt::user_payload(placeholders)}),
    ];
    if let Some(ctx) = retry_context {
        messages.push(json!({"role": "user", "content": ctx}));
    }
    let request = ChatStreamRequest::new_chat_with_tools(
        model_source,
        model_ref,
        messages,
        vec![prompt::submit_zone_classifications_tool()],
        StreamFormat::Openai,
    )
    .with_tool_choice(prompt::forced_tool_choice());

    let mut attempt = L3Attempt::default();

    let mut handle = match client.stream(request, user_id).await {
        Ok(h) => h,
        Err(e) => {
            attempt.failure = Some(format!("opening the gateway stream: {e}"));
            return attempt;
        }
    };

    let mut acc = ToolCallAccumulator::new();
    while let Some(ev) = handle.next().await {
        match ev {
            Ok(event) => {
                acc.push(&event);
                match event {
                    StreamEvent::Usage {
                        input_tokens,
                        output_tokens,
                        reasoning_tokens,
                    } => {
                        attempt.input_tokens = input_tokens;
                        attempt.output_tokens = output_tokens;
                        attempt.reasoning_tokens = reasoning_tokens;
                    }
                    StreamEvent::Done {
                        finish_reason: fr, ..
                    } => {
                        attempt.finish_reason = fr.map(|f| format!("{f:?}"));
                    }
                    _ => {}
                }
            }
            Err(e) => {
                // Record + stop — finish() below still salvages partial calls.
                attempt.failure = Some(format!("stream error: {e}"));
                break;
            }
        }
    }

    // finish() works on an error-terminated stream too (no Done required).
    let calls = acc.finish();
    attempt.tool_calls_seen = calls.len();

    // Select the call by tool NAME — never blindly `.first()`. A provider may
    // stream an extra/echo tool call at a lower index; picking it would
    // silently fold a wrong-tool case into a "parse failure".
    let target = calls
        .iter()
        .find(|c| c.name.as_deref() == Some("submit_zone_classifications"));
    attempt.raw_arguments = target.map(|c| c.arguments.clone()).unwrap_or_default();

    match target {
        None => {
            if attempt.failure.is_none() {
                attempt.failure = Some(if calls.is_empty() {
                    "no tool_call events were streamed".to_string()
                } else {
                    format!(
                        "{} tool call(s) streamed, none named submit_zone_classifications",
                        calls.len()
                    )
                });
            }
        }
        Some(call) => match serde_json::from_str::<L3ToolArguments>(&call.arguments) {
            Ok(args) => attempt.classifications = args.classifications,
            Err(e) => {
                attempt.failure = Some(format!(
                    "tool-call arguments did not parse as L3 output: {e}"
                ));
            }
        },
    }
    attempt
}

/// Run the L3 measurement: one [`call_l3_attempt`] against the fixture,
/// validate, and report. A stream error or an unparseable tool call is
/// recorded in `failure` — never an `Err` — so the measurement is always
/// produced. (`anyhow::Result` is kept for caller-API stability; it is always
/// `Ok` now.)
pub async fn run_l3_measurement(
    client: &GatewayClient,
    model_source: ModelSource,
    model_ref: Uuid,
    user_id: Uuid,
) -> anyhow::Result<L3MeasurementReport> {
    let placeholders = prompt::fixture_placeholders();
    let attempt =
        call_l3_attempt(client, model_source, model_ref, user_id, &placeholders, None).await;

    let classifications_parsed = attempt.classifications.len();
    let validation_errors = if classifications_parsed > 0 {
        validate_l3(
            &attempt.classifications,
            &placeholders,
            &prompt::book_canon_refs(),
        )
    } else {
        Vec::new()
    };

    Ok(L3MeasurementReport {
        tool_use_success: classifications_parsed > 0,
        finish_reason: attempt.finish_reason,
        tool_calls_seen: attempt.tool_calls_seen,
        classifications_parsed,
        validation_errors,
        input_tokens: attempt.input_tokens,
        output_tokens: attempt.output_tokens,
        reasoning_tokens: attempt.reasoning_tokens,
        raw_arguments: attempt.raw_arguments,
        failure: attempt.failure,
    })
}

/// Render the report as a human-readable block for the CLI / findings doc.
pub fn render_report(r: &L3MeasurementReport) -> String {
    let mut s = String::from("── Phase 0b L3 measurement ──────────────────────────────\n");
    s.push_str(&format!(
        "tool_use_success : {}\n",
        if r.tool_use_success { "YES" } else { "NO" }
    ));
    s.push_str(&format!(
        "finish_reason    : {}\n",
        r.finish_reason.as_deref().unwrap_or("(none)")
    ));
    s.push_str(&format!("tool_calls_seen  : {}\n", r.tool_calls_seen));
    if r.tool_calls_seen > 1 {
        // Measurement-honesty caveat: classifications / validation / raw
        // arguments below all derive from call[0] only. The fixture forces
        // exactly one tool, so >1 is itself a finding worth surfacing.
        s.push_str(
            "  NOTE: >1 tool call streamed — metrics below reflect call[0] ONLY\n",
        );
    }
    s.push_str(&format!(
        "classifications  : {} parsed (fixture has {} objects)\n",
        r.classifications_parsed,
        prompt::fixture_placeholders().len()
    ));
    s.push_str(&format!(
        "tokens           : input={} output={} reasoning={}\n",
        r.input_tokens,
        r.output_tokens,
        r.reasoning_tokens
            .map(|n| n.to_string())
            .unwrap_or_else(|| "-".to_string()),
    ));
    s.push_str(&format!(
        "TMP_008b §12 est : ${:.5} equivalent on Haiku 4.5 (lmstudio run is free)\n",
        r.est_haiku_cost_usd()
    ));
    if r.validation_errors.is_empty() {
        s.push_str("validation       : 0 errors (R1-R5 clean)\n");
    } else {
        s.push_str(&format!(
            "validation       : {} error(s) —\n",
            r.validation_errors.len()
        ));
        for e in &r.validation_errors {
            s.push_str(&format!("  - {}\n", e.describe()));
        }
    }
    if let Some(f) = &r.failure {
        s.push_str(&format!("FAILURE          : {f}\n"));
    }
    if !r.raw_arguments.is_empty() {
        s.push_str(&format!("raw arguments    : {}\n", r.raw_arguments));
    }
    s.push_str("─────────────────────────────────────────────────────────\n");
    s
}
