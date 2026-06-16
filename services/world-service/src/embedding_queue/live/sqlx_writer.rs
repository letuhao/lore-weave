//! [`EmbeddingWriter`] bound to a per-reality `sqlx::PgPool`.
//!
//! Runs the L3.I.3 backfill UPDATE:
//!
//! ```sql
//! UPDATE npc_session_memory_embedding
//!    SET embedding = $1            -- pgvector VECTOR(1536)
//!  WHERE npc_id = $2 AND session_id = $3
//!    AND embedding IS NULL         -- idempotency guard: never clobber
//! ```
//!
//! The pool is per-reality (the DSN routes to that reality's shard DB +
//! schema), mirroring `dp-kernel::PgEventStore`'s wrapped-`PgPool` pattern
//! (Q-L4A-1). The `reality_id` argument is therefore informational for a
//! single-reality writer — the pool IS the reality scope.

use std::sync::Arc;

use async_trait::async_trait;
use pgvector::Vector;
use sqlx::postgres::PgPool;
use uuid::Uuid;

use crate::embedding_queue::{EMBEDDING_DIM, EmbeddingWriter};

/// Production [`EmbeddingWriter`]. Clone-cheap (`Arc<PgPool>`).
#[derive(Clone)]
pub struct SqlxEmbeddingWriter {
    pool: Arc<PgPool>,
}

impl SqlxEmbeddingWriter {
    /// Wrap a pre-built pool.
    pub fn new(pool: PgPool) -> Self {
        Self {
            pool: Arc::new(pool),
        }
    }

    /// Construct from an already-shared pool.
    pub fn from_arc(pool: Arc<PgPool>) -> Self {
        Self { pool }
    }
}

#[async_trait]
impl EmbeddingWriter for SqlxEmbeddingWriter {
    async fn write_embedding(
        &self,
        _reality_id: Uuid,
        npc_id: Uuid,
        session_id: Uuid,
        vector: &[f32],
    ) -> Result<(), String> {
        // Defense in depth — the Worker already guards on EMBEDDING_DIM, but a
        // wrong-length bind would otherwise be rejected by Postgres with an
        // opaque error.
        if vector.len() != EMBEDDING_DIM {
            return Err(format!(
                "refusing to write {}-dim vector (expected {EMBEDDING_DIM})",
                vector.len()
            ));
        }
        let embedding = Vector::from(vector.to_vec());
        sqlx::query(
            r#"
            UPDATE npc_session_memory_embedding
               SET embedding = $1
             WHERE npc_id = $2
               AND session_id = $3
               AND embedding IS NULL
            "#,
        )
        .bind(embedding)
        .bind(npc_id)
        .bind(session_id)
        .execute(&*self.pool)
        .await
        .map_err(|e| e.to_string())?;
        // rows_affected == 0 is NOT an error: it means the row was already
        // embedded (idempotent re-run) or has not been INSERTed yet by the
        // projection. The daily integrity checker re-enqueues stale NULLs
        // (deferred — blocked on dp_kernel::load_aggregate).
        Ok(())
    }
}
