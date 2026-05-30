//! `embedding-worker` — L3.I cycle 16 / DEFERRED-059 core.
//!
//! Drains the in-process embedding queue, backfilling
//! `npc_session_memory_embedding.embedding` (VECTOR(1536)) for the configured
//! reality and emitting one `service_to_service_audit` row per provider call.
//!
//! Live wiring bound here:
//!  - [`SqlxEmbeddingWriter`] on the per-reality DB pool (real UPDATE).
//!  - [`MetaAuditWriter`] on the meta DB pool (real audit INSERT), wrapped by
//!    [`MetricsAuditWriter`] for the prometheus surface.
//!  - [`NotWiredProvider`] (fail-closed) — the BYOK provider-gateway binding is
//!    the deferred `D-EMBEDDING-PROVIDER-WIRING` task, so a deployed worker is
//!    observable + drains, but every call is audited as a `ProviderError`
//!    until the provider lands.
//!  - axum `/healthz`+`/readyz`+`/metrics`; tokio ticker; graceful shutdown.
//!
//! NOTE: there is no enqueue source at foundation level yet (no
//! `ProjectionRunner` to call `Queue::enqueue`), so the queue stays empty in
//! production until that domain wiring lands (069/079). The worker is correct
//! and startable today; it does real DB/audit work the moment items arrive.

use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

use sqlx::postgres::PgPoolOptions;
use tokio::sync::watch;
use tracing_subscriber::EnvFilter;

use world_service::embedding_queue::live::{
    AppState, Config, MetaAuditWriter, Metrics, MetricsAuditWriter, NotWiredProvider,
    SqlxEmbeddingWriter, run_worker_loop,
};
use world_service::embedding_queue::{
    AuditWriter, EmbeddingProvider, EmbeddingWriter, Queue as EmbeddingQueue,
};

#[tokio::main]
async fn main() {
    if let Err(e) = run().await {
        eprintln!("[embedding-worker] fatal: {e}");
        std::process::exit(1);
    }
}

async fn run() -> Result<(), String> {
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .init();

    let cfg = Config::from_env()?;

    let reality_pool = PgPoolOptions::new()
        .max_connections(10)
        .connect(&cfg.reality_db_url)
        .await
        .map_err(|e| format!("reality db connect: {e}"))?;
    let meta_pool = PgPoolOptions::new()
        .max_connections(5)
        .connect(&cfg.meta_db_url)
        .await
        .map_err(|e| format!("meta db connect: {e}"))?;

    let queue = Arc::new(EmbeddingQueue::new(cfg.queue_capacity));
    let metrics = Arc::new(Metrics::new());

    let writer: Arc<dyn EmbeddingWriter> = Arc::new(SqlxEmbeddingWriter::new(reality_pool));
    let inner_audit: Arc<dyn AuditWriter> = Arc::new(MetaAuditWriter::new(meta_pool));
    let audit: Arc<dyn AuditWriter> =
        Arc::new(MetricsAuditWriter::new(inner_audit, metrics.clone()));
    let provider: Arc<dyn EmbeddingProvider> = Arc::new(NotWiredProvider);

    let ready = Arc::new(AtomicBool::new(true));
    let app = world_service::embedding_queue::live::router(AppState {
        metrics: metrics.clone(),
        ready: ready.clone(),
    });

    let (shutdown_tx, shutdown_rx) = watch::channel(false);

    // HTTP ops server.
    let listener = tokio::net::TcpListener::bind(cfg.http_addr)
        .await
        .map_err(|e| format!("http bind {}: {e}", cfg.http_addr))?;
    let mut http_shutdown = shutdown_rx.clone();
    let http = tokio::spawn(async move {
        let graceful = async move {
            let _ = http_shutdown.changed().await;
        };
        if let Err(e) = axum::serve(listener, app)
            .with_graceful_shutdown(graceful)
            .await
        {
            tracing::error!(error = %e, "embedding-worker http server");
        }
    });

    // Drain loop.
    let worker = tokio::spawn(run_worker_loop(
        queue.clone(),
        provider,
        writer,
        audit,
        metrics.clone(),
        cfg.tick_interval,
        cfg.batch_size,
        shutdown_rx,
    ));

    tracing::info!(
        reality_id = %cfg.reality_id,
        http_addr = %cfg.http_addr,
        tick_secs = cfg.tick_interval.as_secs(),
        "embedding-worker started (provider NOT wired — D-EMBEDDING-PROVIDER-WIRING)"
    );

    wait_for_signal().await;
    tracing::info!("embedding-worker shutdown signal");
    ready.store(false, Ordering::SeqCst);
    let _ = shutdown_tx.send(true);
    let _ = worker.await;
    let _ = http.await;
    tracing::info!("embedding-worker stopped");
    Ok(())
}

async fn wait_for_signal() {
    #[cfg(unix)]
    {
        use tokio::signal::unix::{SignalKind, signal};
        let mut term = signal(SignalKind::terminate()).expect("install SIGTERM handler");
        let mut intr = signal(SignalKind::interrupt()).expect("install SIGINT handler");
        tokio::select! {
            _ = term.recv() => {},
            _ = intr.recv() => {},
        }
    }
    #[cfg(not(unix))]
    {
        let _ = tokio::signal::ctrl_c().await;
    }
}
