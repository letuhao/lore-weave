//! L4 narration live-LLM smoke test.
//!
//! Runs the end-to-end Phase 1 engine → L3 classification → L4 narration
//! pipeline (`bootstrap_small_reality`) against a live LLM gateway, and
//! asserts the structural shape of the result. Complements the existing
//! `tests/l4_mock.rs` wiremock tests by exercising the REAL gateway
//! transport — catching regressions that mock-only tests can't (e.g.
//! gateway URL drift, schema-version drift in the tool-call SSE
//! response, model-ref UUID expiry).
//!
//! ## Why a smoke (not a regular test)
//!
//! - LLMs are non-deterministic: this test asserts STRUCTURAL invariants
//!   (zone count, length bands, no duplicates) rather than literal text.
//! - LLMs are billable + slow: gating behind `--ignored` keeps `cargo test`
//!   fast for everyone else; only developers iterating on the L4 loop
//!   opt-in.
//! - LLMs require local config: lmstudio (or another gateway-routable
//!   provider) must be running, and the env vars below must be set.
//!
//! ## Running
//!
//! ```bash
//! cargo test -p tilemap-service --test l4_live_smoke -- --ignored \
//!   --nocapture l4_narration_live_smoke
//! ```
//!
//! ## Required env (typically sourced from gitignored `.local/phase0b.env`)
//!
//! | Var | Required | Purpose |
//! |---|---|---|
//! | `LOREWEAVE_INTERNAL_TOKEN` | yes | Service-to-service Bearer token the gateway client uses |
//! | `LMSTUDIO_MODEL_REF` | yes | Provider-registry model UUID (lmstudio in dev per user preference) |
//! | `HARNESS_USER_ID` | yes | User UUID the call bills to (any valid UUID in dev) |
//! | `LOREWEAVE_GATEWAY_URL` | no | Gateway base URL — SDK default applies when unset |
//! | `HARNESS_MODEL_SOURCE` | no | `platform_model` (default) or `user_model` |
//!
//! When any required var is missing, the test panics with a clear error
//! pointing to this doc — distinguishes "missing env" from "real
//! regression".
//!
//! ## Invariants asserted
//!
//! 1. `bootstrap_small_reality` returns `Ok(report)` (no transport / retry
//!    exhaustion error)
//! 2. `report.l4.narrations.len() >= 4` — every zone of the 4-zone wuxia
//!    bootstrap_template gets narrated exactly once (disjoint union of
//!    LLM-accepted + §6 canonical-default fallback)
//! 3. Every narration is 50-2000 chars (matches `l4_validate.rs` R3
//!    length rule)
//! 4. Zone ids are unique across the narrations vec
//! 5. Each narration is non-empty whitespace (defensive check)
//!
//! Non-invariants (intentionally not asserted):
//!
//! - Specific narration content — LLMs vary run-to-run
//! - `fallback_count` — depends on the model's tool-use stability; both 0
//!   and ≤4 are valid outcomes
//! - Token counts — depend on the model + tokenizer

use std::collections::HashSet;
use std::env;

use tilemap_service::harness::bootstrap::{
    bootstrap_small_reality, render_bootstrap_report,
};
use tilemap_service::llm::{GatewayClient, ModelSource};
use uuid::Uuid;

/// Read a required env var and parse it as a UUID, panicking with an
/// instructive message if missing or malformed. Mirrors the
/// `env_uuid` helper in `main.rs::gateway_from_env`.
fn require_env_uuid(key: &str) -> Uuid {
    let raw = env::var(key).unwrap_or_else(|_| {
        panic!(
            "L4 live smoke requires env var {key}. See the module doc in \
             services/tilemap-service/tests/l4_live_smoke.rs for the full \
             env shape, or set up `.local/phase0b.env` and source it before \
             running."
        )
    });
    Uuid::parse_str(raw.trim())
        .unwrap_or_else(|e| panic!("env var {key} is not a valid UUID: {e}"))
}

#[tokio::test]
#[ignore = "live LLM — requires lmstudio + .local/phase0b.env; run via --ignored"]
async fn l4_narration_live_smoke() {
    // Build the gateway client from env (`LOREWEAVE_INTERNAL_TOKEN` +
    // optional `LOREWEAVE_GATEWAY_URL`). Any missing required env makes
    // this panic with `GatewayClient::from_env`'s message.
    let client = GatewayClient::from_env().unwrap_or_else(|e| {
        panic!(
            "constructing the gateway client failed ({e}). \
             Most likely cause: LOREWEAVE_INTERNAL_TOKEN unset. \
             See services/tilemap-service/tests/l4_live_smoke.rs module \
             doc for the full env shape."
        )
    });
    let model_ref = require_env_uuid("LMSTUDIO_MODEL_REF");
    let user_id = require_env_uuid("HARNESS_USER_ID");
    let model_source = match env::var("HARNESS_MODEL_SOURCE").as_deref() {
        Ok("user_model") => ModelSource::UserModel,
        Ok("platform_model") | Err(_) => ModelSource::PlatformModel,
        Ok(other) => panic!(
            "HARNESS_MODEL_SOURCE='{other}' invalid (expected platform_model | user_model)"
        ),
    };

    // 3 retry attempts per L3/L4 batch — matches the production
    // `tilemap-service bootstrap` CLI invocation in `main.rs:103`. Lets
    // the §5 partial-success retry trigger if the first batch is missing
    // zones, without making the smoke too tolerant of broken models.
    let report = bootstrap_small_reality(&client, model_source, model_ref, user_id, 3)
        .await
        .expect(
            "bootstrap_small_reality returned Err — \
             likely cause: gateway transport failure OR retry exhaustion. \
             Check the gateway is reachable + the lmstudio model is loaded \
             + the model supports forced tool-use.",
        );

    // Print the report so `cargo test -- --nocapture` shows the L4 output
    // to the operator — this smoke is primarily for visual inspection of
    // the narrative voice during loop development. The assertions below
    // are the structural minimums; the report is the qualitative gate.
    eprintln!("\n=== L4 live smoke — bootstrap report ===");
    eprintln!("{}", render_bootstrap_report(&report));

    // Invariant 1: at least 4 zones narrated (the bootstrap_template
    // ships 4 wuxia zones — capital + western_wilds + forbidden_vault +
    // 1 connecting; `run_l4_with_retries` guarantees a narration for
    // every input zone via disjoint LLM+fallback union).
    assert!(
        report.l4.narrations.len() >= 4,
        "expected at least 4 narrations (one per wuxia bootstrap zone), got {}",
        report.l4.narrations.len(),
    );

    // Invariant 2: every narration length is in the validator-blessed
    // band 50-2000 chars (matches `l4_validate.rs` R3). Even §6 fallback
    // narrations must satisfy this since the validator runs on them too.
    for n in &report.l4.narrations {
        let len = n.narration.chars().count();
        assert!(
            (50..=2000).contains(&len),
            "narration for zone {:?} is {} chars, outside the [50, 2000] \
             validator band: {:?}",
            n.zone_id,
            len,
            n.narration,
        );
        assert!(
            !n.narration.trim().is_empty(),
            "narration for zone {:?} is whitespace-only",
            n.zone_id,
        );
    }

    // Invariant 3: zone ids are unique — every zone narrated EXACTLY
    // once (the §5 retry loop's disjoint-union guarantee). If a zone
    // appears twice, the partition logic in `run_l4_with_retries` is
    // broken and double-billing OR loss would follow.
    let mut seen: HashSet<&str> = HashSet::new();
    for n in &report.l4.narrations {
        assert!(
            seen.insert(n.zone_id.as_str()),
            "zone {:?} appears more than once in L4 narrations — disjoint \
             union invariant violated",
            n.zone_id,
        );
    }

    // Invariant 4: every PLACED zone has a narration. The bootstrap
    // template ships 4 zones (the same 4 in `bootstrap_template()` in
    // `bootstrap.rs`); the L4 loop MUST narrate each one. Catches a
    // regression where the retry loop drops zones on the floor instead
    // of falling back to the canonical default.
    let placed_zone_ids: HashSet<&str> = report
        .tilemap
        .zones
        .iter()
        .map(|z| z.zone_id.0.as_str())
        .collect();
    for placed in &placed_zone_ids {
        assert!(
            seen.contains(placed),
            "placed zone {placed:?} has no narration — L4 loop dropped it \
             without falling back to canonical default",
        );
    }
}
