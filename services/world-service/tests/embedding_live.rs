//! DEFERRED-059 live-smoke — the REAL infra path for the embedding queue.
//!
//! Exercises [`SqlxEmbeddingWriter`] against a live per-reality
//! `npc_session_memory_embedding` (pgvector) and [`MetaAuditWriter`] against a
//! live meta `service_to_service_audit`. This is the cross-service-real slice
//! of 059 (the provider gateway + enqueue trigger are deferred — see the live
//! module docs).
//!
//! Gated by env (mirrors `dp-kernel`'s `integration_event_store.rs`):
//!
//! - `LOREWEAVE_TEST_PG_URL`   → per-reality DB (gets 0006 + 0008 applied)
//! - `LOREWEAVE_TEST_META_URL` → meta DB (gets 016 applied)
//!
//! When unset, the test prints a skip line and returns green so dev machines
//! without Postgres still pass `cargo test`.
//!
//! The test applies the REAL migration files (idempotent) via `sqlx::raw_sql`
//! so it is self-contained locally AND in CI — zero schema drift.

use sqlx::Row;
use sqlx::postgres::PgPool;
use uuid::Uuid;

use world_service::embedding_queue::live::{MetaAuditWriter, SqlxEmbeddingWriter};
use world_service::embedding_queue::{
    AuditEvent, AuditOutcome, AuditWriter, EMBEDDING_DIM, EmbeddingWriter,
};

fn migration(rel: &str) -> String {
    let root = concat!(env!("CARGO_MANIFEST_DIR"), "/../..");
    let path = format!("{root}/{rel}");
    std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("read migration {path}: {e}"))
}

async fn apply(pool: &PgPool, rel: &str) {
    let sql = migration(rel);
    sqlx::raw_sql(&sql)
        .execute(pool)
        .await
        .unwrap_or_else(|e| panic!("apply {rel}: {e}"));
}

#[tokio::test]
async fn embedding_writer_and_audit_live_smoke() {
    let (Ok(reality_url), Ok(meta_url)) = (
        std::env::var("LOREWEAVE_TEST_PG_URL"),
        std::env::var("LOREWEAVE_TEST_META_URL"),
    ) else {
        eprintln!(
            "SKIP embedding_live: set LOREWEAVE_TEST_PG_URL + LOREWEAVE_TEST_META_URL to run"
        );
        return;
    };

    let reality_pool = PgPool::connect(&reality_url)
        .await
        .expect("connect reality DB");
    let meta_pool = PgPool::connect(&meta_url).await.expect("connect meta DB");

    // Real schema (idempotent). 0006 creates the table (BYTEA placeholder when
    // pgvector absent), 0008 installs pgvector + ALTERs to VECTOR(1536).
    apply(
        &reality_pool,
        "contracts/migrations/per_reality/0006_projections.up.sql",
    )
    .await;
    apply(
        &reality_pool,
        "contracts/migrations/per_reality/0008_pgvector_setup.up.sql",
    )
    .await;
    apply(
        &meta_pool,
        "migrations/meta/016_service_to_service_audit.up.sql",
    )
    .await;

    // ── Writer path ──────────────────────────────────────────────────────────
    let reality_id = Uuid::new_v4();
    let npc_id = Uuid::new_v4();
    let session_id = Uuid::new_v4();

    // Seed a pending row (embedding NULL) the way the projection would.
    sqlx::query(
        r#"
        INSERT INTO npc_session_memory_embedding
            (npc_id, session_id, content_hash, event_id, aggregate_version)
        VALUES ($1, $2, $3, $4, 1)
        ON CONFLICT (npc_id, session_id) DO NOTHING
        "#,
    )
    .bind(npc_id)
    .bind(session_id)
    .bind(format!("hash-{npc_id}"))
    .bind(Uuid::new_v4())
    .execute(&reality_pool)
    .await
    .expect("seed pending embedding row");

    let writer = SqlxEmbeddingWriter::from_arc(std::sync::Arc::new(reality_pool.clone()));
    let vector: Vec<f32> = (0..EMBEDDING_DIM).map(|i| (i as f32) * 0.0001).collect();
    writer
        .write_embedding(reality_id, npc_id, session_id, &vector)
        .await
        .expect("write_embedding");

    let has_emb: bool = sqlx::query_scalar(
        "SELECT embedding IS NOT NULL FROM npc_session_memory_embedding WHERE npc_id = $1 AND session_id = $2",
    )
    .bind(npc_id)
    .bind(session_id)
    .fetch_one(&reality_pool)
    .await
    .expect("read back embedding");
    assert!(has_emb, "embedding column must be populated after write");

    // Idempotency: a second write must NOT error and must NOT clobber (the
    // `embedding IS NULL` guard means rows_affected == 0 the second time).
    writer
        .write_embedding(reality_id, npc_id, session_id, &vector)
        .await
        .expect("idempotent re-write");
    let still: bool = sqlx::query_scalar(
        "SELECT embedding IS NOT NULL FROM npc_session_memory_embedding WHERE npc_id = $1 AND session_id = $2",
    )
    .bind(npc_id)
    .bind(session_id)
    .fetch_one(&reality_pool)
    .await
    .expect("read back embedding (2)");
    assert!(still, "embedding still populated after idempotent re-write");

    // ── Audit path ───────────────────────────────────────────────────────────
    let audit = MetaAuditWriter::from_arc(std::sync::Arc::new(meta_pool.clone()));
    let before: i64 = audit_count(&meta_pool).await;

    audit
        .record(AuditEvent {
            reality_id,
            npc_id,
            session_id,
            provider: "openai".into(),
            model: "text-embedding-ada-002".into(),
            tokens: 42,
            outcome: AuditOutcome::Ok,
        })
        .await;
    audit
        .record(AuditEvent {
            reality_id,
            npc_id,
            session_id,
            provider: "openai".into(),
            model: "text-embedding-ada-002".into(),
            tokens: 0,
            outcome: AuditOutcome::ProviderError("boom".into()),
        })
        .await;

    let after_ok_err: i64 = audit_count(&meta_pool).await;
    assert_eq!(
        after_ok_err - before,
        2,
        "Ok + ProviderError each insert exactly one edge row"
    );

    // WriteError is NOT a provider-edge event (the provider call already
    // succeeded + was audited by the preceding Ok row), so MetaAuditWriter MUST
    // skip it — one provider call = one edge row, never two.
    audit
        .record(AuditEvent {
            reality_id,
            npc_id,
            session_id,
            provider: "openai".into(),
            model: "text-embedding-ada-002".into(),
            tokens: 0,
            outcome: AuditOutcome::WriteError("db down".into()),
        })
        .await;
    let after_write_err: i64 = audit_count(&meta_pool).await;
    assert_eq!(
        after_write_err - after_ok_err,
        0,
        "WriteError must NOT insert an audit row (would double-count the Embed edge)"
    );

    // Outcome mapping: Ok → result='ok', ProviderError → result='error'.
    let ok_rows: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM service_to_service_audit \
         WHERE caller_service = 'world-service' AND callee_service = 'provider-registry-service' \
           AND rpc_name = 'Embed' AND result = 'ok'",
    )
    .fetch_one(&meta_pool)
    .await
    .expect("count ok rows");
    assert!(ok_rows >= 1, "at least one ok-result audit row");
    let err_rows: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM service_to_service_audit \
         WHERE caller_service = 'world-service' AND callee_service = 'provider-registry-service' \
           AND rpc_name = 'Embed' AND result = 'error'",
    )
    .fetch_one(&meta_pool)
    .await
    .expect("count error rows");
    assert!(err_rows >= 1, "at least one error-result audit row");
}

async fn audit_count(pool: &PgPool) -> i64 {
    sqlx::query(
        "SELECT count(*) AS c FROM service_to_service_audit \
         WHERE caller_service = 'world-service' AND callee_service = 'provider-registry-service'",
    )
    .fetch_one(pool)
    .await
    .expect("count audit rows")
    .get::<i64, _>("c")
}
