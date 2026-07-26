//! Postgres pool bootstrap + startup migrations — the per-service-DB pattern
//! for LoreWeave Rust services (a normal platform-plane DB like `loreweave_chat`,
//! NOT the kernel services' per-reality sidecar `.sql` model).
//!
//! The `Migrator` is passed IN (not built here) because `sqlx::migrate!()`
//! resolves its path relative to the *calling* crate — the consumer writes
//! `service_http::db::init(url, sqlx::migrate!("./migrations"))`.

use std::time::Duration;

use sqlx::migrate::Migrator;
use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;

/// Connect a bounded pool and run pending migrations. Fails fast (used at
/// startup before `serve`).
pub async fn init(url: &str, migrator: Migrator) -> anyhow::Result<PgPool> {
    let pool = PgPoolOptions::new()
        .max_connections(20)
        .acquire_timeout(Duration::from_secs(10))
        .connect(url)
        .await?;
    migrator.run(&pool).await?;
    Ok(pool)
}
