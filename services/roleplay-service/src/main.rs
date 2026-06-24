//! roleplay-service binary entry.
//!
//! Boot sequence: init JSON tracing → read fail-closed config → connect the
//! Postgres pool + run migrations → build the router → serve until SIGTERM.

use anyhow::Context;

use roleplay_service::{AppState, Config, build_router};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    service_http::init_tracing("roleplay-service");

    let config = Config::from_env().context("loading roleplay-service config")?;
    tracing::info!(bind = %config.bind, "roleplay-service starting");

    let pool = service_http::db::init(&config.database_url, sqlx::migrate!("./migrations"))
        .await
        .context("connecting loreweave_roleplay + running migrations")?;

    let state = AppState::new(pool, &config);
    let router = build_router(state);

    service_http::serve(config.bind, router).await?;
    Ok(())
}
