//! TMP_008b §5/§6 for L4 — `call_l4_attempt` (one gateway call) + the per-zone
//! partial-success retry loop `run_l4_with_retries`. Mirrors the Phase-2 L3
//! `mod.rs::call_l3_attempt` + `retry.rs`; the ContextHub lesson `2c94cf3c`
//! retry-loop holes are closed per spec D1 (subset preamble, `failure`-field
//! discriminator, out-of-subset error filter).

use std::collections::HashSet;

use loreweave_llm::{
    ChatStreamRequest, GatewayClient, ModelSource, StreamFormat, ToolCallAccumulator,
};
use serde_json::json;
use uuid::Uuid;

use super::l4_prompt::{self, ZoneNarrationInput};
use super::l4_validate::{
    L4Narration, L4ToolArguments, L4ValidationError, canonical_default_narration,
    format_l4_errors_for_retry, partition_l4_response,
};
use super::prompt::forced_tool_choice;
use super::style::{NarrationLanguage, NarrationVoice, NarrativeTone};

/// The outcome of one L4 gateway call. Every failure mode — stream open error,
/// mid-stream error, missing/unparseable tool call — is captured in `failure`
/// with empty `narrations`; the call never returns `Err`.
#[derive(Debug, Default)]
pub struct L4Attempt {
    pub narrations: Vec<L4Narration>,
    pub failure: Option<String>,
}

/// Run ONE L4 gateway call for `inputs` (TMP_008b §3.3 tool + forced
/// `tool_choice`). `retry_context`, when set, carries the §4.2-analogue
/// structured error message. All failures land in [`L4Attempt::failure`].
#[allow(clippy::too_many_arguments)]
pub async fn call_l4_attempt(
    client: &GatewayClient,
    model_source: ModelSource,
    model_ref: Uuid,
    user_id: Uuid,
    inputs: &[ZoneNarrationInput],
    language: NarrationLanguage,
    tone: NarrativeTone,
    voice: NarrationVoice,
    retry_context: Option<&str>,
) -> L4Attempt {
    let mut messages = vec![
        json!({"role": "system", "content": l4_prompt::SYSTEM_PROMPT}),
        json!({
            "role": "user",
            "content": l4_prompt::l4_user_payload(inputs, language, tone, voice),
        }),
    ];
    if let Some(ctx) = retry_context {
        messages.push(json!({"role": "user", "content": ctx}));
    }
    let request = ChatStreamRequest::new_chat_with_tools(
        model_source,
        model_ref,
        messages,
        vec![l4_prompt::submit_zone_narrations_tool()],
        StreamFormat::Openai,
    )
    .with_tool_choice(forced_tool_choice());

    let mut attempt = L4Attempt::default();

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
            Ok(event) => acc.push(&event),
            Err(e) => {
                attempt.failure = Some(format!("stream error: {e}"));
                break;
            }
        }
    }

    let calls = acc.finish();
    // Select the call by tool NAME — never blindly `.first()` (a provider may
    // stream an extra/echo tool call; picking it would silently fold a
    // wrong-tool case into a "parse failure").
    match calls
        .iter()
        .find(|c| c.name.as_deref() == Some("submit_zone_narrations"))
    {
        None => {
            if attempt.failure.is_none() {
                attempt.failure = Some(if calls.is_empty() {
                    "no tool_call events were streamed".to_string()
                } else {
                    format!(
                        "{} tool call(s) streamed, none named submit_zone_narrations",
                        calls.len()
                    )
                });
            }
        }
        Some(call) => match serde_json::from_str::<L4ToolArguments>(&call.arguments) {
            Ok(args) => attempt.narrations = args.zone_narrations,
            Err(e) => {
                attempt.failure = Some(format!(
                    "tool-call arguments did not parse as L4 output: {e}"
                ));
            }
        },
    }
    attempt
}

/// Outcome of [`run_l4_with_retries`].
#[derive(Debug)]
pub struct L4Result {
    /// Every input zone narrated **exactly once** — the disjoint union of
    /// LLM-accepted narrations and §6 canonical-default fallbacks.
    pub narrations: Vec<L4Narration>,
    /// Gateway calls issued, including transport-failed ones; ≤ `max_attempts`.
    pub llm_attempts: u32,
    /// Count of zones filled by the §6 canonical-default narration.
    pub fallback_count: usize,
}

/// TMP_008b §5/§6 for L4 — narrate `inputs` with a per-zone partial-success
/// retry loop, then fill any zone still failing with the §6 canonical default.
/// Every input zone ends up narrated exactly once.
///
/// **Precondition (the sole `Err`):** `zone_id`s must be unique — checked at
/// entry, before any gateway call. Otherwise never `Err`: a transport failure
/// counts as a gateway call that narrated nothing, and the §6 fallback always
/// succeeds. `max_attempts == 0` → every zone is a fallback.
#[allow(clippy::too_many_arguments)]
pub async fn run_l4_with_retries(
    client: &GatewayClient,
    model_source: ModelSource,
    model_ref: Uuid,
    user_id: Uuid,
    inputs: &[ZoneNarrationInput],
    language: NarrationLanguage,
    tone: NarrativeTone,
    voice: NarrationVoice,
    max_attempts: u32,
) -> crate::Result<L4Result> {
    // D1 precondition — duplicate zone_id rejected before any gateway call.
    let mut seen_ids: HashSet<&str> = HashSet::new();
    for i in inputs {
        if !seen_ids.insert(i.zone_id.as_str()) {
            return Err(crate::Error::Config(format!(
                "duplicate ZoneNarrationInput zone_id '{}' — every zone must be \
                 unique for the L4 retry loop to track it",
                i.zone_id
            )));
        }
    }

    let mut accepted: Vec<L4Narration> = Vec::new();
    let mut accepted_ids: HashSet<String> = HashSet::new();
    let mut llm_attempts = 0u32;
    let mut last_errors: Vec<L4ValidationError> = Vec::new();

    for attempt in 1..=max_attempts {
        let subset: Vec<ZoneNarrationInput> = inputs
            .iter()
            .filter(|i| !accepted_ids.contains(&i.zone_id))
            .cloned()
            .collect();
        if subset.is_empty() {
            break;
        }

        let retry_ctx = if attempt > 1 && !last_errors.is_empty() {
            format_l4_errors_for_retry(&last_errors)
        } else {
            String::new()
        };
        let ctx = if retry_ctx.is_empty() {
            None
        } else {
            Some(retry_ctx.as_str())
        };

        let outcome = call_l4_attempt(
            client, model_source, model_ref, user_id, &subset, language, tone, voice, ctx,
        )
        .await;
        llm_attempts += 1;

        let (newly_accepted, mut errors) =
            partition_l4_response(&subset, &outcome.narrations, language);
        for n in newly_accepted {
            if accepted_ids.insert(n.zone_id.clone()) {
                accepted.push(n);
            }
        }
        // Out-of-subset errors must not leak into the next retry context.
        let subset_ids: HashSet<&str> = subset.iter().map(|i| i.zone_id.as_str()).collect();
        errors.retain(|e| subset_ids.contains(e.zone_id()));
        // A transport/parse failure (no usable response) → retry fresh, no
        // context (spec D1 — discriminate on `failure`, not response emptiness).
        last_errors = if outcome.failure.is_some() {
            Vec::new()
        } else {
            errors
        };
    }

    // §6 — canonical default for whatever the LLM never narrated validly.
    // `fallback_count` is tallied at insert time, never by subtraction.
    let mut fallback_count = 0usize;
    for i in inputs {
        if accepted_ids.insert(i.zone_id.clone()) {
            accepted.push(canonical_default_narration(i));
            fallback_count += 1;
        }
    }

    Ok(L4Result {
        narrations: accepted,
        llm_attempts,
        fallback_count,
    })
}
