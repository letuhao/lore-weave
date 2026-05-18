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
        Some("bootstrap") => run_bootstrap().await,
        Some("measure") => run_measure().await,
        Some(other) => {
            anyhow::bail!("unknown subcommand '{other}' (known: classify, bootstrap, measure)");
        }
        None => {
            tracing::info!(
                "tilemap-service — `classify` (L3 measurement) | `bootstrap` (small-reality L3 retry-loop demo) | `measure` (continent-scale generation + live L3/L4)"
            );
            tracing::info!("see services/tilemap-service/DESIGN.md + README.md");
            Ok(())
        }
    }
}

/// Gateway client + routing params from env — shared by `classify` and
/// `bootstrap`.
///
/// Env (typically sourced from the gitignored `.local/phase0b.env`):
///   LOREWEAVE_GATEWAY_URL    — gateway base URL (optional; SDK default if unset)
///   LOREWEAVE_INTERNAL_TOKEN — service-to-service token (REQUIRED)
///   LMSTUDIO_MODEL_REF       — registered lmstudio model UUID (REQUIRED)
///   HARNESS_USER_ID          — user UUID the call bills to (REQUIRED)
///   HARNESS_MODEL_SOURCE     — "platform_model" (default) or "user_model"
fn gateway_from_env() -> Result<(GatewayClient, ModelSource, Uuid, Uuid)> {
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
    Ok((client, model_source, model_ref, user_id))
}

/// `tilemap-service classify` — run the Phase 0b L3 measurement harness once
/// against the live gateway and print the report.
async fn run_classify() -> Result<()> {
    let (client, model_source, model_ref, user_id) = gateway_from_env()?;
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

/// `tilemap-service bootstrap` — place a small reality via the Phase 1 engine,
/// then classify a fixture object set through the §5 L3 retry loop. Same env
/// as `classify` (see [`gateway_from_env`]).
async fn run_bootstrap() -> Result<()> {
    let (client, model_source, model_ref, user_id) = gateway_from_env()?;
    tracing::info!(?model_source, %model_ref, "running small-reality bootstrap");
    let report =
        harness::bootstrap::bootstrap_small_reality(&client, model_source, model_ref, user_id, 3)
            .await
            .context("running the small-reality bootstrap")?;
    println!("{}", harness::bootstrap::render_bootstrap_report(&report));
    Ok(())
}

/// `tilemap-service measure` — time continent-scale (256²) generation, then,
/// when the gateway env is present, run the live engine→L3-batched→L4 flow and
/// report token cost + latency. The offline section prints before the (slow)
/// live run starts.
async fn run_measure() -> Result<()> {
    tracing::info!("placing the continent (256²) — the offline generation measurement");
    let (tilemap, offline) =
        harness::continent::measure_offline().context("placing the continent")?;
    println!("{}", harness::continent::render_offline(&offline));

    match gateway_from_env() {
        Ok((client, model_source, model_ref, user_id)) => {
            tracing::info!(
                ?model_source, %model_ref,
                "running the live continent measurement (engine→L3-batched→L4)",
            );
            let live = harness::continent::measure_live(
                &tilemap, &client, model_source, model_ref, user_id,
            )
            .await
            .context("running the live continent measurement")?;
            println!("{}", harness::continent::render_live(&live));
        }
        Err(e) => {
            println!("live measurement skipped — gateway env not set ({e})");
        }
    }
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
