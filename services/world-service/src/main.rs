//! `world-service` — geography substrate service for the LLM MMO RPG.
//!
//! Owns the `world_geometry` aggregate (GEO_001) and the POL/SET/ROUTE
//! activation generators. See the design docs under
//! `docs/03_planning/LLM_MMO_RPG/features/00_geography/` and the build plan
//! `docs/03_planning/LLM_MMO_RPG/V1_30D_IMPLEMENTATION_PLAN.md`.
//!
//! **This binary used to be a 22-line `println!` scaffold** whose header said the
//! HTTP server *"awaits the DP-kernel (cycle 17)"*. That dependency has since
//! landed — `dp` and `dp-kernel` are path dependencies of this crate — so the
//! comment was stale rather than blocking. `WS2` replaced the scaffold with the
//! real thing.
//!
//! Boot sequence: JSON tracing → fail-closed config → connect the meta and
//! shard-admin pools → build the router → serve until SIGTERM.
//!
//! The surface is **internal** (invariant I1): external traffic reaches the
//! platform through `api-gateway-bff`, never here. The **eight** worker/drill
//! binaries beside this one (`provision`, `rebuilder`, `orphan_scanner`,
//! `embedding-worker`, `replay-aggregate`, and the three drills `provision-drill`
//! / `freeze-drill` / `capacity-place`) are unchanged and keep their own entry
//! points — `[[bin]]` count is 9 including this one.

use std::process::ExitCode;

use world_service::server::{AppState, Config, build_router, db};

#[tokio::main]
async fn main() -> ExitCode {
    service_http::init_tracing("world-service");

    let config = match Config::from_env() {
        Ok(c) => c,
        Err(e) => {
            // Config failures are operator errors and must be legible without a
            // log collector, so they go to stderr as well as to tracing.
            eprintln!("world-service: {e}");
            tracing::error!(error = %e, "configuration refused");
            return ExitCode::from(2);
        }
    };

    tracing::info!(bind = %config.bind, "world-service starting");

    let meta = match db::connect(&config.meta_dsn, "meta", 8).await {
        Ok(p) => p,
        Err(e) => return fail(e),
    };
    let shard_admin = match db::connect(&config.shard_admin_dsn, "shard admin", 8).await {
        Ok(p) => p,
        Err(e) => return fail(e),
    };

    let router = build_router(AppState::new(meta, shard_admin, &config));

    if let Err(e) = service_http::serve(config.bind, router).await {
        return fail(format!("serve: {e}"));
    }
    ExitCode::SUCCESS
}

fn fail(msg: String) -> ExitCode {
    eprintln!("world-service: {msg}");
    tracing::error!(error = %msg, "startup failed");
    ExitCode::from(1)
}
