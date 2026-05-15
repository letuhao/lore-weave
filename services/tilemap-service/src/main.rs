//! tilemap-service binary entry.
//!
//! Phase 0b adds the `classify` subcommand — the L3 zone-classifier
//! measurement harness that calls the live LLM gateway. With no subcommand
//! the binary prints scaffold info and exits 0.

use std::env;

use anyhow::{Context, Result};
use tilemap_service::harness;
use tilemap_service::llm::{GatewayClient, ModelSource};
use tracing_subscriber::EnvFilter;
use uuid::Uuid;

#[tokio::main]
async fn main() -> Result<()> {
    init_tracing();

    let args: Vec<String> = env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("classify") => run_classify().await,
        Some(other) => {
            anyhow::bail!("unknown subcommand '{other}' (known: classify)");
        }
        None => {
            tracing::info!(
                "tilemap-service Phase 0b — run `tilemap-service classify` for the L3 measurement harness"
            );
            tracing::info!("see services/tilemap-service/DESIGN.md + README.md");
            Ok(())
        }
    }
}

/// `tilemap-service classify` — run the Phase 0b L3 measurement harness once
/// against the live gateway and print the report.
///
/// Env (typically sourced from the gitignored `.local/phase0b.env`):
///   LOREWEAVE_GATEWAY_URL    — gateway base URL (optional; SDK default if unset)
///   LOREWEAVE_INTERNAL_TOKEN — service-to-service token (REQUIRED)
///   LMSTUDIO_MODEL_REF       — registered lmstudio model UUID (REQUIRED)
///   HARNESS_USER_ID          — user UUID the call bills to (REQUIRED)
///   HARNESS_MODEL_SOURCE     — "platform_model" (default) or "user_model"
async fn run_classify() -> Result<()> {
    let client = GatewayClient::from_env()
        .context("constructing the gateway client (is LOREWEAVE_INTERNAL_TOKEN set?)")?;
    let model_ref = env_uuid("LMSTUDIO_MODEL_REF")?;
    let user_id = env_uuid("HARNESS_USER_ID")?;
    let model_source = match env::var("HARNESS_MODEL_SOURCE").as_deref() {
        Ok("user_model") => ModelSource::UserModel,
        Ok("platform_model") | Err(_) => ModelSource::PlatformModel,
        Ok(other) => anyhow::bail!(
            "HARNESS_MODEL_SOURCE='{other}' invalid (expected platform_model | user_model)"
        ),
    };

    tracing::info!(?model_source, %model_ref, "running L3 measurement harness");
    let report = harness::run_l3_measurement(&client, model_source, model_ref, user_id)
        .await
        .context("running the L3 measurement")?;

    // The report is printed to stdout regardless of tool-use success — a
    // model that cannot do forced tool-use is a measurement FINDING, not a
    // harness error, so this returns Ok either way (exit 0).
    println!("{}", harness::render_report(&report));
    Ok(())
}

/// Read a required env var and parse it as a UUID.
fn env_uuid(key: &str) -> Result<Uuid> {
    let raw = env::var(key).with_context(|| format!("env var {key} is required"))?;
    Uuid::parse_str(raw.trim()).with_context(|| format!("env var {key} is not a valid UUID"))
}

fn init_tracing() {
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info,tilemap_service=debug"));
    tracing_subscriber::fmt()
        .with_env_filter(filter)
        .with_target(true)
        .init();
}
