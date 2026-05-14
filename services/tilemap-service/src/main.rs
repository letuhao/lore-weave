//! tilemap-service binary entry. Phase 0a: minimal CLI that prints scaffold info
//! and exits 0. Phase 0b will add real subcommands (`bootstrap`, `generate`, etc.).

use anyhow::Result;
use tracing_subscriber::EnvFilter;

fn main() -> Result<()> {
    init_tracing();

    tracing::info!(
        "tilemap-service Phase 0a — scaffold + types + LLM gateway client skeleton; no network calls yet"
    );
    tracing::info!(
        "see services/tilemap-service/DESIGN.md for module decomposition + Phase 0b roadmap"
    );

    Ok(())
}

fn init_tracing() {
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("info,tilemap_service=debug"));
    tracing_subscriber::fmt()
        .with_env_filter(filter)
        .with_target(true)
        .init();
}
