//! Phase 0b L3 zone-classifier measurement harness.
//!
//! Sends ONE hardcoded L3 zone-classification request (TMP_008b §3 tool +
//! §9.1 few-shot prompt) through the LLM gateway with a forced `tool_choice`,
//! reassembles the streamed `tool_call` fragments, parses + validates the
//! result, and reports tool-use success + token cost vs TMP_008b §12.
//!
//! This is a MEASUREMENT tool, not the production pipeline: the TMP_008b §5
//! per-object retry loop and §6 canonical-default fallback are Phase 2.

pub mod prompt;
pub mod validate;

use anyhow::Context;
use loreweave_llm::{
    ChatStreamRequest, GatewayClient, ModelSource, StreamEvent, StreamFormat, ToolCallAccumulator,
};
use serde_json::json;
use uuid::Uuid;

use validate::{L3ToolArguments, L3ValidationError, validate_l3};

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

/// Run the L3 measurement: build the request, stream it through the gateway,
/// reassemble the tool call, validate, and report. A stream-level error or an
/// unparseable tool call is recorded in `failure` — not an `Err` — so the
/// measurement is always produced.
pub async fn run_l3_measurement(
    client: &GatewayClient,
    model_source: ModelSource,
    model_ref: Uuid,
    user_id: Uuid,
) -> anyhow::Result<L3MeasurementReport> {
    let placeholders = prompt::fixture_placeholders();
    let messages = vec![
        json!({"role": "system", "content": prompt::SYSTEM_PROMPT}),
        json!({"role": "user", "content": prompt::user_payload(&placeholders)}),
    ];
    let request = ChatStreamRequest::new_chat_with_tools(
        model_source,
        model_ref,
        messages,
        vec![prompt::submit_zone_classifications_tool()],
        StreamFormat::Openai,
    )
    .with_tool_choice(prompt::forced_tool_choice());

    let mut handle = client
        .stream(request, user_id)
        .await
        .context("opening the gateway stream")?;

    let mut acc = ToolCallAccumulator::new();
    let mut input_tokens = 0u32;
    let mut output_tokens = 0u32;
    let mut reasoning_tokens = None;
    let mut finish_reason = None;
    let mut failure = None;

    while let Some(ev) = handle.next().await {
        match ev {
            Ok(event) => {
                acc.push(&event);
                match event {
                    StreamEvent::Usage {
                        input_tokens: i,
                        output_tokens: o,
                        reasoning_tokens: r,
                    } => {
                        input_tokens = i;
                        output_tokens = o;
                        reasoning_tokens = r;
                    }
                    StreamEvent::Done {
                        finish_reason: fr, ..
                    } => {
                        finish_reason = fr.map(|f| format!("{f:?}"));
                    }
                    _ => {}
                }
            }
            Err(e) => {
                // Record + stop — finish() below still salvages partial calls.
                failure = Some(format!("stream error: {e}"));
                break;
            }
        }
    }

    // finish() works on an error-terminated stream too (no Done required).
    let calls = acc.finish();
    let tool_calls_seen = calls.len();

    let raw_arguments = calls.first().map(|c| c.arguments.clone()).unwrap_or_default();

    let mut tool_use_success = false;
    let mut classifications_parsed = 0;
    let mut validation_errors = Vec::new();

    match calls.first() {
        None => {
            if failure.is_none() {
                failure = Some("no tool_call events were streamed".to_string());
            }
        }
        Some(call) => match serde_json::from_str::<L3ToolArguments>(&call.arguments) {
            Ok(args) => {
                classifications_parsed = args.classifications.len();
                validation_errors = validate_l3(
                    &args.classifications,
                    &placeholders,
                    &prompt::book_canon_refs(),
                );
                tool_use_success = classifications_parsed > 0;
            }
            Err(e) => {
                failure = Some(format!(
                    "tool-call arguments did not parse as L3 output: {e}"
                ));
            }
        },
    }

    Ok(L3MeasurementReport {
        tool_use_success,
        finish_reason,
        tool_calls_seen,
        classifications_parsed,
        validation_errors,
        input_tokens,
        output_tokens,
        reasoning_tokens,
        raw_arguments,
        failure,
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
