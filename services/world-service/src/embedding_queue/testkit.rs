//! Shared test doubles for the embedding queue (091 D-EMBEDDING-TESTKIT).
//!
//! These in-memory fakes were previously copy-pasted across the
//! `embedding_queue` unit tests, the `worker_loop` tests, and the external
//! `tests/embedding_retrieval_test.rs` integration test — three near-identical
//! interior-mutable (`&self` async-trait → `Mutex`) copies that risked drift.
//! Extracted here behind a `testkit` cargo feature so the external `tests/`
//! crate can use them too (it enables the feature via the self dev-dependency
//! in `Cargo.toml`); the in-crate unit tests see them under `cfg(test)`.

use std::collections::HashMap;
use std::sync::Mutex;

use async_trait::async_trait;
use uuid::Uuid;

use super::{EMBEDDING_DIM, EmbedResult, EmbeddingProvider, EmbeddingWriter};

// ─── Providers ──────────────────────────────────────────────────────────────

/// Provider returning a deterministic 1536-dim linear vector. Configurable
/// name/model/tokens for the happy-path + token-accounting tests.
pub struct StubProvider {
    /// `provider_name()` value.
    pub name: &'static str,
    /// Model id echoed back from `embed()`.
    pub model: &'static str,
    /// Token count echoed back from `embed()`.
    pub tokens: u32,
}

#[async_trait]
impl EmbeddingProvider for StubProvider {
    async fn embed(&self, _text: &str) -> (String, EmbedResult) {
        let mut v = vec![0.0f32; EMBEDDING_DIM];
        for (i, x) in v.iter_mut().enumerate() {
            *x = (i as f32) * 0.001;
        }
        (
            self.model.to_string(),
            EmbedResult::Ok {
                vector: v,
                tokens: self.tokens,
            },
        )
    }

    fn provider_name(&self) -> &str {
        self.name
    }
}

/// Provider mapping text → a deterministic, unit-normalized 1536-dim vector
/// (same text → same vector), so cosine-similarity ranking is testable.
pub struct DeterministicEmbedder;

#[async_trait]
impl EmbeddingProvider for DeterministicEmbedder {
    async fn embed(&self, text: &str) -> (String, EmbedResult) {
        let mut v = vec![0.0f32; EMBEDDING_DIM];
        let mut h: u64 = 5381;
        for b in text.bytes() {
            h = h.wrapping_mul(33) ^ (b as u64);
        }
        for (i, x) in v.iter_mut().enumerate() {
            let scrambled = h.wrapping_mul(1099511628211).wrapping_add(i as u64);
            *x = ((scrambled & 0xffff) as f32) / 65535.0;
        }
        let norm: f32 = v.iter().map(|x| x * x).sum::<f32>().sqrt();
        if norm > 0.0 {
            for x in v.iter_mut() {
                *x /= norm;
            }
        }
        (
            "text-embedding-ada-002".to_string(),
            EmbedResult::Ok {
                vector: v,
                tokens: text.len() as u32,
            },
        )
    }

    fn provider_name(&self) -> &str {
        "openai"
    }
}

/// Provider returning a WRONG-dimension vector (768 ≠ 1536) — exercises the
/// dim-mismatch audit path.
pub struct WrongDimProvider;

#[async_trait]
impl EmbeddingProvider for WrongDimProvider {
    async fn embed(&self, _text: &str) -> (String, EmbedResult) {
        (
            "broken-model".to_string(),
            EmbedResult::Ok {
                vector: vec![0.0; 768],
                tokens: 100,
            },
        )
    }
    fn provider_name(&self) -> &str {
        "broken-provider"
    }
}

/// Provider that always errors — exercises the provider-error audit path.
pub struct ErrorProvider;

#[async_trait]
impl EmbeddingProvider for ErrorProvider {
    async fn embed(&self, _text: &str) -> (String, EmbedResult) {
        (
            "unreachable-model".to_string(),
            EmbedResult::ProviderError("connection refused".to_string()),
        )
    }
    fn provider_name(&self) -> &str {
        "down-provider"
    }
}

// ─── Writers ──────────────────────────────────────────────────────────────

/// In-memory [`EmbeddingWriter`] keyed by `(reality, npc, session)`. Interior-
/// mutable via `Mutex` (the async trait takes `&self`), matching the production
/// sqlx writer which holds a shared `PgPool`. When armed via
/// [`MemWriter::failing`], the FIRST write returns a simulated DB error then
/// disarms (so the retry path can be exercised).
#[derive(Default)]
pub struct MemWriter {
    rows: Mutex<HashMap<(Uuid, Uuid, Uuid), Vec<f32>>>,
    fail_next: Mutex<bool>,
}

impl MemWriter {
    /// A writer whose next write fails once (then succeeds).
    pub fn failing() -> Self {
        Self {
            rows: Mutex::new(HashMap::new()),
            fail_next: Mutex::new(true),
        }
    }

    /// Number of rows written.
    pub fn row_count(&self) -> usize {
        self.rows.lock().unwrap().len()
    }

    /// Alias for [`MemWriter::row_count`] (the retrieval test reads `len()`).
    pub fn len(&self) -> usize {
        self.row_count()
    }

    /// True when no rows have been written.
    pub fn is_empty(&self) -> bool {
        self.row_count() == 0
    }

    /// The stored vector for a `(reality, npc, session)` key, if any.
    pub fn get(&self, key: &(Uuid, Uuid, Uuid)) -> Option<Vec<f32>> {
        self.rows.lock().unwrap().get(key).cloned()
    }

    /// The lengths of every stored vector (used to assert dim=1536).
    pub fn vector_lens(&self) -> Vec<usize> {
        self.rows
            .lock()
            .unwrap()
            .values()
            .map(|v| v.len())
            .collect()
    }
}

#[async_trait]
impl EmbeddingWriter for MemWriter {
    async fn write_embedding(
        &self,
        reality_id: Uuid,
        npc_id: Uuid,
        session_id: Uuid,
        vector: &[f32],
    ) -> Result<(), String> {
        {
            let mut f = self.fail_next.lock().unwrap();
            if *f {
                *f = false;
                return Err("simulated DB error".into());
            }
        }
        self.rows
            .lock()
            .unwrap()
            .insert((reality_id, npc_id, session_id), vector.to_vec());
        Ok(())
    }
}

/// A no-op [`EmbeddingWriter`] for tests that only exercise the drain loop /
/// audit path and don't assert on stored rows.
pub struct NoopWriter;

#[async_trait]
impl EmbeddingWriter for NoopWriter {
    async fn write_embedding(
        &self,
        _reality_id: Uuid,
        _npc_id: Uuid,
        _session_id: Uuid,
        _vector: &[f32],
    ) -> Result<(), String> {
        Ok(())
    }
}
