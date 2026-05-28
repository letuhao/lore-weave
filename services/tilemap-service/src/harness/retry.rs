//! TMP_008b §5 — the per-object partial-success L3 retry loop, with the §6
//! canonical-default fallback. Builds on [`super::call_l3_attempt`] (one
//! gateway call) and the pure [`super::validate::partition_response`]
//! accept/narrow core.

use std::collections::{HashMap, HashSet};

use loreweave_llm::{GatewayClient, ModelSource};
use uuid::Uuid;

use super::call_l3_attempt;
use super::prompt::L3Placeholder;
use super::validate::{
    L3Classification, L3ValidationError, canonical_default_classification,
    format_errors_for_retry, partition_response,
};

/// Outcome of [`run_l3_with_retries`] (spec D6).
#[derive(Debug)]
pub struct L3Result {
    /// Every input `obj_id` classified **exactly once** — the disjoint union
    /// of LLM-accepted classifications and §6 canonical-default fallbacks.
    pub classifications: Vec<L3Classification>,
    /// Gateway calls actually issued, including transport-failed ones. `0`
    /// when `max_attempts == 0`; always ≤ `max_attempts`.
    pub llm_attempts: u32,
    /// Count of objects filled by the §6 canonical default.
    pub fallback_count: usize,
    /// Prompt + completion tokens summed across every gateway attempt — the
    /// token-cost measurement input (a transport-failed attempt adds 0).
    pub input_tokens: u32,
    pub output_tokens: u32,
}

/// TMP_008b §5 — classify `placeholders` with a per-object partial-success
/// retry loop, then fill any object still failing with the §6 canonical
/// default. Every input object ends up classified exactly once.
///
/// **Precondition (the sole `Err` path):** every placeholder's
/// `suggested_canon_kind` must be non-empty — checked once at entry, before
/// any gateway call (spec D1; §6 indexes `suggested_canon_kind[0]`).
///
/// Given a valid input the function never returns `Err`: a transport failure
/// on an attempt counts as a gateway call that classified nothing, and the
/// loop proceeds to the always-succeeds §6 fallback. `max_attempts == 0` skips
/// the LLM entirely — every object is a fallback.
pub async fn run_l3_with_retries(
    client: &GatewayClient,
    model_source: ModelSource,
    model_ref: Uuid,
    user_id: Uuid,
    placeholders: &[L3Placeholder],
    book_canon_refs: &[String],
    max_attempts: u32,
) -> crate::Result<L3Result> {
    // D1 precondition — reject malformed input at the door: every placeholder
    // needs a non-empty `suggested_canon_kind` (§6 indexes `[0]`) and a unique
    // `obj_id` (the §5 loop + §6 fallback track objects by id — a duplicate
    // would be silently dropped, violating D6 exactly-once).
    let mut seen_ids: HashSet<&str> = HashSet::new();
    for p in placeholders {
        if p.suggested_canon_kind.is_empty() {
            return Err(crate::Error::Config(format!(
                "L3Placeholder '{}' has an empty suggested_canon_kind — the §6 \
                 canonical-default fallback has no engine default to fall back on",
                p.obj_id
            )));
        }
        if !seen_ids.insert(p.obj_id.as_str()) {
            return Err(crate::Error::Config(format!(
                "duplicate L3Placeholder obj_id '{}' — every object must have a \
                 unique id for the §5 retry loop to track it",
                p.obj_id
            )));
        }
    }

    let mut accepted: Vec<L3Classification> = Vec::new();
    let mut accepted_ids: HashSet<String> = HashSet::new();
    let mut llm_attempts = 0u32;
    let mut input_tokens = 0u32;
    let mut output_tokens = 0u32;
    // Validation errors from the prior attempt — the §4.2 retry context. Empty
    // after a transport failure (no usable response) so the next attempt is a
    // fresh try, not a correction (spec D3).
    let mut last_errors: Vec<L3ValidationError> = Vec::new();

    for attempt in 1..=max_attempts {
        // Still-unaccepted objects, in input order (§5 — narrow each retry).
        let subset: Vec<L3Placeholder> = placeholders
            .iter()
            .filter(|p| !accepted_ids.contains(&p.obj_id))
            .cloned()
            .collect();
        if subset.is_empty() {
            break;
        }

        let retry_ctx = if attempt > 1 && !last_errors.is_empty() {
            format_errors_for_retry(&last_errors)
        } else {
            String::new()
        };
        let ctx = if retry_ctx.is_empty() {
            None
        } else {
            Some(retry_ctx.as_str())
        };

        let outcome =
            call_l3_attempt(client, model_source, model_ref, user_id, &subset, ctx).await;
        llm_attempts += 1;
        input_tokens = input_tokens.saturating_add(outcome.input_tokens);
        output_tokens = output_tokens.saturating_add(outcome.output_tokens);

        let (newly_accepted, mut errors) =
            partition_response(&subset, &outcome.classifications, book_canon_refs);
        for c in newly_accepted {
            if accepted_ids.insert(c.obj_id.clone()) {
                accepted.push(c);
            }
        }
        // Keep only errors about objects actually in this subset. A real LLM
        // re-emits already-accepted objects; their `UnknownObjId` errors must
        // not leak into the next retry context — it would instruct the model
        // to "Remove" correctly-classified objects, contradicting the preamble.
        let subset_ids: HashSet<&str> = subset.iter().map(|p| p.obj_id.as_str()).collect();
        errors.retain(|e| subset_ids.contains(e.obj_id()));
        // Spec D3: after a transport/parse failure (no usable response —
        // `outcome.failure` set) the next attempt retries fresh, with no
        // retry context. A *parsed* response — even an empty
        // `{"classifications":[]}` — is a validation failure: its real errors
        // (every object `[MISSING]`) MUST drive the retry context. Discriminate
        // on `failure`, never on `classifications.is_empty()` (a clean empty
        // response also has no classifications but is a validation failure).
        last_errors = if outcome.failure.is_some() {
            Vec::new()
        } else {
            errors
        };
    }

    // §6 — canonical default for whatever the LLM never classified validly.
    // `fallback_count` is tallied here, at insert time (spec D6 invariant —
    // never derived by subtraction).
    let mut fallback_count = 0usize;
    for p in placeholders {
        if accepted_ids.insert(p.obj_id.clone()) {
            accepted.push(canonical_default_classification(p));
            fallback_count += 1;
        }
    }

    Ok(L3Result {
        classifications: accepted,
        llm_attempts,
        fallback_count,
        input_tokens,
        output_tokens,
    })
}

/// Default per-batch object cap for [`run_l3_batched`] — a local model handles
/// roughly this many objects per structured tool call comfortably.
pub const L3_BATCH_SIZE: usize = 40;

/// TMP_008b §5 at continent scale — classify `placeholders` zone-by-zone in
/// bounded batches. Groups by `zone_id` (first-appearance order), sub-chunks
/// any zone larger than `batch_size`, runs [`run_l3_with_retries`] once per
/// batch, and aggregates: `classifications` concatenated, `llm_attempts` /
/// `fallback_count` / token counts summed.
///
/// The batches are a disjoint partition of the input, so every object is still
/// classified **exactly once** (spec D6) across the union.
///
/// `Err` only on the [`run_l3_with_retries`] precondition — but checked here
/// **globally** before batching, since a cross-batch duplicate `obj_id` would
/// slip the per-batch check. Panics if `batch_size == 0` (a caller bug).
#[allow(clippy::too_many_arguments)]
pub async fn run_l3_batched(
    client: &GatewayClient,
    model_source: ModelSource,
    model_ref: Uuid,
    user_id: Uuid,
    placeholders: &[L3Placeholder],
    book_canon_refs: &[String],
    max_attempts: u32,
    batch_size: usize,
) -> crate::Result<L3Result> {
    assert!(batch_size > 0, "run_l3_batched: batch_size must be > 0");

    // Global precondition (mirrors run_l3_with_retries, applied across batches).
    let mut seen_ids: HashSet<&str> = HashSet::new();
    for p in placeholders {
        if p.suggested_canon_kind.is_empty() {
            return Err(crate::Error::Config(format!(
                "L3Placeholder '{}' has an empty suggested_canon_kind — the §6 \
                 canonical-default fallback has no engine default to fall back on",
                p.obj_id
            )));
        }
        if !seen_ids.insert(p.obj_id.as_str()) {
            return Err(crate::Error::Config(format!(
                "duplicate L3Placeholder obj_id '{}' across the batched input",
                p.obj_id
            )));
        }
    }

    // Group by zone_id in first-appearance order — deterministic batching.
    let mut zone_order: Vec<&str> = Vec::new();
    let mut by_zone: HashMap<&str, Vec<L3Placeholder>> = HashMap::new();
    for p in placeholders {
        let zid = p.zone_id.as_str();
        if !by_zone.contains_key(zid) {
            zone_order.push(zid);
        }
        by_zone.entry(zid).or_default().push(p.clone());
    }

    let mut result = L3Result {
        classifications: Vec::new(),
        llm_attempts: 0,
        fallback_count: 0,
        input_tokens: 0,
        output_tokens: 0,
    };
    for zid in zone_order {
        for batch in by_zone[zid].chunks(batch_size) {
            let r = run_l3_with_retries(
                client, model_source, model_ref, user_id, batch, book_canon_refs, max_attempts,
            )
            .await?;
            result.classifications.extend(r.classifications);
            result.llm_attempts = result.llm_attempts.saturating_add(r.llm_attempts);
            result.fallback_count += r.fallback_count;
            result.input_tokens = result.input_tokens.saturating_add(r.input_tokens);
            result.output_tokens = result.output_tokens.saturating_add(r.output_tokens);
        }
    }
    Ok(result)
}
