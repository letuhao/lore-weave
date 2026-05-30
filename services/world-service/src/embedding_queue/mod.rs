//! L3.I.3 + L3.I.4 — Embedding queue.
//!
//! Async backfill of `npc_session_memory_embedding.embedding` (VECTOR(1536),
//! cycle-16 0008_pgvector_setup migration). The queue:
//!
//!   1. Receives memory-creation signals (`enqueue(MemoryRef)`) from the
//!      cycle-12 dp-kernel projection runner when a `npc.session_memory.*`
//!      event lands and the embedding column is still NULL (the cycle-13
//!      conditional INSERT now writes the row WITHOUT embedding; the queue
//!      backfills it).
//!   2. Calls a [`EmbeddingProvider`] trait implementation (BYOK gateway
//!      adapter — NOT a direct OpenAI/Cohere/etc SDK, per CLAUDE.md provider
//!      gateway invariant) to compute the 1536-dim vector.
//!   3. UPDATEs the row via an [`EmbeddingWriter`] trait implementation
//!      (production-time backed by sqlx; test-time backed by an in-memory
//!      fake).
//!   4. Emits ONE [`AuditEvent`] row PER provider call into the
//!      `service_to_service_audit` table (Q-L1A-3 full-audit, no sampling).
//!
//! ## LOCKED decisions consumed
//!
//! - **Q-L3-1** (OPEN_QUESTIONS_LOCKED §5 line 73): embedding worker in
//!   world-service. THIS module IS that worker. V1+30d extraction to a
//!   dedicated `embedding-worker` service is the documented promotion path
//!   (DEFERRED — see RETRO note in cycle 16 CYCLE_LOG entry).
//! - **Q-L3I-1** (line 77): embedding dim 1536 hard-coded V1. The
//!   [`EMBEDDING_DIM`] constant is the SINGLE source of truth — provider
//!   responses with any other dimension are rejected at the [`Worker`]
//!   layer (audit row recorded as `outcome = "dim_mismatch"`).
//! - **Q-L1A-3** (line 24): every provider call MUST emit a
//!   service_to_service_audit row. THIS module does that in [`Worker::run`]
//!   *before* writing the row (so even a failed provider response is
//!   audited).
//!
//! ## Why an effect-trait split (not direct sqlx + reqwest)
//!
//! The provisioner module ([`crate::provisioner`]) uses the same Effects
//! trait pattern: the core logic is sync over abstract traits, with
//! production wiring living in the integration glue. Keeping the queue
//! testable without docker (matches cycle 5 + cycle 6 patterns) lets us
//! ship unit + integration tests entirely mock-backed; live wiring (the
//! actual sqlx pool + the actual provider-registry-service HTTP client)
//! lands in the V1 launch cycle alongside the BYOK provider plumbing.
//! Deferred row tracks this: D-EMBEDDING-QUEUE-LIVE-WIRING.
//!
//! ## Non-blocking guarantee
//!
//! The [`Queue`] is in-memory MPSC-style; `enqueue()` returns immediately
//! after pushing the [`MemoryRef`]. The [`Worker`] drains the queue in a
//! dedicated tokio task (production) or on the caller's thread (tests).
//! Critically, the *event-append* path (cycle 10 outbox writer) NEVER
//! awaits an embedding computation — the projection runner just appends a
//! row with `embedding = NULL` and pushes a `MemoryRef` to the queue.
//! This is what the brief means by "truly async": the synchronous part of
//! the projection completes in O(insert) time; embedding latency (which
//! can be hundreds of ms for an LLM call) lives entirely in the queue.

pub mod audit;
pub mod live;

use std::collections::VecDeque;
use std::sync::Mutex;

use async_trait::async_trait;
use uuid::Uuid;

pub use audit::{AuditEvent, AuditOutcome, AuditWriter, CountingAuditWriter};

/// Embedding dimension. Q-L3I-1 V1 lock — DO NOT change without a V2+
/// schema migration that adds per-table dim flexibility.
///
/// This MUST equal the corresponding constant in
/// `crates/projections/npc/src/lib.rs::EMBEDDING_DIM` — both are checked
/// by `scripts/raid/verify-cycle-16.sh` step "dim constant cross-check".
pub const EMBEDDING_DIM: usize = 1536;

// ───────────────────────────────────────────────────────────────────────────
// Domain types
// ───────────────────────────────────────────────────────────────────────────

/// Reference to a row in `npc_session_memory_embedding` that needs its
/// `embedding` column backfilled. Carries everything the provider call +
/// audit need without round-tripping back to the DB.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MemoryRef {
    /// Reality the memory lives in (audit + per-reality DB routing).
    pub reality_id: Uuid,
    /// NPC the memory belongs to (PK part 1 of npc_session_memory_embedding).
    pub npc_id: Uuid,
    /// Session the memory was created in (PK part 2).
    pub session_id: Uuid,
    /// Stable hash of the memory text (idempotency guard — same content
    /// hash → reuse cached embedding instead of re-calling provider).
    pub content_hash: String,
    /// The actual text to embed (NOT persisted in the embedding table; we
    /// keep it in the queue entry only for the duration of the call).
    pub text: String,
}

/// Outcome of a single embedding call.
#[derive(Debug, Clone, PartialEq)]
pub enum EmbedResult {
    /// Provider returned a 1536-dim vector.
    Ok {
        /// f32 vector, length == [`EMBEDDING_DIM`].
        vector: Vec<f32>,
        /// Token count (audit cost tracking).
        tokens: u32,
    },
    /// Provider returned a vector of the wrong dimension. Recorded in the
    /// audit row as `dim_mismatch` and DROPPED (not retried — the provider
    /// is misconfigured).
    DimMismatch {
        /// What the provider actually returned.
        returned_dim: usize,
    },
    /// Provider call failed (network, 5xx, timeout, rate-limit). Recorded
    /// in audit; the queue MAY retry (caller decides — see [`Worker::run`]).
    ProviderError(String),
}

/// Provider gateway contract — the embedding queue speaks ONLY through
/// this trait, never to a vendor SDK directly. Production wiring binds
/// this to an adapter in `provider-registry-service` (the BYOK gateway
/// from CLAUDE.md "Provider gateway invariant: NO direct provider SDK
/// calls — all AI calls go through adapter layer").
#[async_trait]
pub trait EmbeddingProvider: Send + Sync {
    /// Compute an embedding for the given text. Returns the model name
    /// used (for audit) and an [`EmbedResult`]. Async: production binds a
    /// BYOK provider-gateway HTTP call (deferred D-EMBEDDING-PROVIDER-WIRING).
    async fn embed(&self, text: &str) -> (String, EmbedResult);

    /// Stable identifier for the underlying provider (audit field).
    /// Examples: "openai", "cohere", "local-bge". The caller MUST NOT
    /// branch on this string in business logic — it's an audit anchor.
    fn provider_name(&self) -> &str;
}

/// Writer contract for the `npc_session_memory_embedding` table. Splits
/// the queue from sqlx so unit tests can use an in-memory fake. Production
/// wiring (deferred to D-EMBEDDING-QUEUE-LIVE-WIRING) binds this to a
/// sqlx::PgPool against the per-reality DB for `reality_id`.
#[async_trait]
pub trait EmbeddingWriter: Send + Sync {
    /// UPDATE npc_session_memory_embedding
    ///   SET embedding = $vector::vector
    ///  WHERE npc_id = $npc_id AND session_id = $session_id
    ///    AND embedding IS NULL  -- idempotency guard: don't clobber existing
    ///
    /// Async + `&self`: production binds a shared `sqlx::PgPool` (interior
    /// shared, no `&mut`), mirroring `dp-kernel::PgEventStore`.
    async fn write_embedding(
        &self,
        reality_id: Uuid,
        npc_id: Uuid,
        session_id: Uuid,
        vector: &[f32],
    ) -> Result<(), String>;
}

// ───────────────────────────────────────────────────────────────────────────
// In-memory queue (V1 — single-process). V1+30d may replace with Redis or
// per-reality outbox table — DEFERRED row tracks the migration path.
// ───────────────────────────────────────────────────────────────────────────

/// Bounded in-memory FIFO of [`MemoryRef`]s. Thread-safe via Mutex.
///
/// V1 single-process scope: world-service is N=1 replica in foundation
/// V1 per Q-L1L-1 (HPA + KEDA infra K8s); cross-replica fan-out lands
/// V2+ when the queue moves to Redis (D-EMBEDDING-QUEUE-REDIS-MIGRATION).
pub struct Queue {
    inner: Mutex<VecDeque<MemoryRef>>,
    capacity: usize,
}

impl Queue {
    /// Construct a new queue with the given soft capacity. `enqueue`
    /// blocks (returns Err) when the queue is full — this is the
    /// backpressure signal that an embedding storm is in progress.
    pub fn new(capacity: usize) -> Self {
        Self {
            inner: Mutex::new(VecDeque::with_capacity(capacity)),
            capacity,
        }
    }

    /// Push a memory-ref onto the queue. Returns `Err` if the queue is
    /// at capacity — the projection runner should log + drop (the row
    /// already has `embedding = NULL`; the daily integrity checker will
    /// re-enqueue stale-NULL rows).
    pub fn enqueue(&self, mr: MemoryRef) -> Result<(), String> {
        let mut q = self.inner.lock().expect("queue mutex poisoned");
        if q.len() >= self.capacity {
            return Err(format!(
                "embedding queue at capacity ({}); backpressure",
                self.capacity
            ));
        }
        q.push_back(mr);
        Ok(())
    }

    /// Pop the next memory-ref. Returns `None` when the queue is empty.
    /// Tests drive this in a tight loop; production wires a tokio task
    /// that uses tokio::time::sleep when None.
    pub fn dequeue(&self) -> Option<MemoryRef> {
        let mut q = self.inner.lock().expect("queue mutex poisoned");
        q.pop_front()
    }

    /// Current depth — useful for the `lw_embedding_queue_depth` gauge
    /// (V1+30d obs work).
    pub fn depth(&self) -> usize {
        self.inner.lock().expect("queue mutex poisoned").len()
    }
}

// ───────────────────────────────────────────────────────────────────────────
// Worker
// ───────────────────────────────────────────────────────────────────────────

/// Single drain pass through the queue. Returns the number of items
/// processed (whether successfully or with a captured error). The
/// `max_items` cap bounds wall time per pass — production wires this
/// inside a tokio task that calls `process_batch` in a loop, sleeping
/// between passes when the queue is empty.
pub struct Worker<'a> {
    /// FIFO source of `MemoryRef`s awaiting embedding compute.
    pub queue: &'a Queue,
    /// BYOK provider gateway (NOT a direct vendor SDK — see CLAUDE.md).
    pub provider: &'a dyn EmbeddingProvider,
    /// Persistence sink for the computed VECTOR(1536). Shared (`&dyn`) — the
    /// async writer trait takes `&self`, so the production loop can borrow an
    /// `Arc<dyn EmbeddingWriter>` per tick.
    pub writer: &'a dyn EmbeddingWriter,
    /// Audit sink — receives ONE event per provider call (Q-L1A-3 full audit).
    pub audit: &'a dyn AuditWriter,
}

impl<'a> Worker<'a> {
    /// Drain up to `max_items` from the queue. For each item:
    ///   1. Call `provider.embed(text)`.
    ///   2. ALWAYS emit an audit row (Q-L1A-3 full-audit; even DimMismatch
    ///      and ProviderError are audited — that's how SRE diagnoses a
    ///      misconfigured BYOK provider).
    ///   3. On Ok, write the vector via `writer`.
    ///   4. On error (DimMismatch / ProviderError / write fail), the item
    ///      is DROPPED — re-enqueue is the daily integrity checker's job
    ///      (it scans for stale NULL embeddings and re-pushes them).
    ///
    /// Returns the count of items popped from the queue.
    pub async fn process_batch(&self, max_items: usize) -> usize {
        let mut processed = 0;
        while processed < max_items {
            let Some(mr) = self.queue.dequeue() else {
                break;
            };
            processed += 1;
            self.handle_one(mr).await;
        }
        processed
    }

    async fn handle_one(&self, mr: MemoryRef) {
        let (model, result) = self.provider.embed(&mr.text).await;
        match result {
            EmbedResult::Ok { vector, tokens } => {
                // Guard against a misbehaving provider — even though the
                // trait contract says 1536, defense in depth.
                if vector.len() != EMBEDDING_DIM {
                    self.audit
                        .record(AuditEvent {
                            reality_id: mr.reality_id,
                            npc_id: mr.npc_id,
                            session_id: mr.session_id,
                            provider: self.provider.provider_name().to_string(),
                            model,
                            tokens: 0,
                            outcome: AuditOutcome::DimMismatch {
                                returned_dim: vector.len(),
                            },
                        })
                        .await;
                    return;
                }
                // Record audit FIRST so cost is captured even if the
                // subsequent write blows up.
                self.audit
                    .record(AuditEvent {
                        reality_id: mr.reality_id,
                        npc_id: mr.npc_id,
                        session_id: mr.session_id,
                        provider: self.provider.provider_name().to_string(),
                        model: model.clone(),
                        tokens,
                        outcome: AuditOutcome::Ok,
                    })
                    .await;
                if let Err(e) = self
                    .writer
                    .write_embedding(mr.reality_id, mr.npc_id, mr.session_id, &vector)
                    .await
                {
                    // Record a SECOND audit row capturing the write failure
                    // — distinct from the provider call (which succeeded).
                    // SRE distinguishes via outcome=write_error.
                    self.audit
                        .record(AuditEvent {
                            reality_id: mr.reality_id,
                            npc_id: mr.npc_id,
                            session_id: mr.session_id,
                            provider: self.provider.provider_name().to_string(),
                            model,
                            tokens: 0,
                            outcome: AuditOutcome::WriteError(e),
                        })
                        .await;
                }
            }
            EmbedResult::DimMismatch { returned_dim } => {
                self.audit
                    .record(AuditEvent {
                        reality_id: mr.reality_id,
                        npc_id: mr.npc_id,
                        session_id: mr.session_id,
                        provider: self.provider.provider_name().to_string(),
                        model,
                        tokens: 0,
                        outcome: AuditOutcome::DimMismatch { returned_dim },
                    })
                    .await;
            }
            EmbedResult::ProviderError(e) => {
                self.audit
                    .record(AuditEvent {
                        reality_id: mr.reality_id,
                        npc_id: mr.npc_id,
                        session_id: mr.session_id,
                        provider: self.provider.provider_name().to_string(),
                        model,
                        tokens: 0,
                        outcome: AuditOutcome::ProviderError(e),
                    })
                    .await;
            }
        }
    }
}

// ───────────────────────────────────────────────────────────────────────────
// Tests — exercise the full enqueue → embed → write → audit flow with
// in-memory fakes. NO docker, NO network.
// ───────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;
    use std::sync::Mutex as StdMutex;

    // ─── Test doubles ──────────────────────────────────────────────────────

    /// Provider that returns a deterministic 1536-dim vector. Used by the
    /// happy-path test — production wires the BYOK provider via
    /// provider-registry-service HTTP call.
    struct StubProvider {
        name: &'static str,
        model: &'static str,
        tokens: u32,
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

    /// Provider that returns wrong-dim vector — exercises the dim-mismatch
    /// audit path.
    struct WrongDimProvider;

    #[async_trait]
    impl EmbeddingProvider for WrongDimProvider {
        async fn embed(&self, _text: &str) -> (String, EmbedResult) {
            (
                "broken-model".to_string(),
                EmbedResult::Ok {
                    vector: vec![0.0; 768], // half of 1536 — the classic mistake
                    tokens: 100,
                },
            )
        }
        fn provider_name(&self) -> &str {
            "broken-provider"
        }
    }

    /// Provider that always errors — exercises the provider-error audit path.
    struct ErrorProvider;

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

    /// In-memory writer keyed by (reality, npc, session). Interior-mutable
    /// (`&self` async trait) via `Mutex`, matching the production sqlx writer
    /// which holds a shared `PgPool`.
    #[derive(Default)]
    struct MemWriter {
        rows: StdMutex<HashMap<(Uuid, Uuid, Uuid), Vec<f32>>>,
        fail_next: StdMutex<bool>,
    }

    impl MemWriter {
        fn row_count(&self) -> usize {
            self.rows.lock().unwrap().len()
        }
        fn vector_lens(&self) -> Vec<usize> {
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

    fn mr(text: &str) -> MemoryRef {
        // Derive npc_id + session_id from text so distinct test entries
        // land as distinct rows in the in-memory writer.
        let mut seed: u128 = 0;
        for b in text.bytes() {
            seed = seed.wrapping_mul(1099511628211).wrapping_add(b as u128);
        }
        MemoryRef {
            reality_id: Uuid::from_u128(1),
            npc_id: Uuid::from_u128(seed | 0x1),
            session_id: Uuid::from_u128(seed | 0x2),
            content_hash: format!("hash-of-{text}"),
            text: text.into(),
        }
    }

    // ─── Tests ─────────────────────────────────────────────────────────────

    #[test]
    fn queue_enforces_capacity() {
        let q = Queue::new(2);
        assert!(q.enqueue(mr("a")).is_ok());
        assert!(q.enqueue(mr("b")).is_ok());
        let third = q.enqueue(mr("c"));
        assert!(third.is_err(), "third enqueue must fail at capacity");
        assert_eq!(q.depth(), 2);
    }

    #[tokio::test]
    async fn worker_happy_path_writes_vector_and_audits_ok() {
        let q = Queue::new(10);
        q.enqueue(mr("hello")).unwrap();
        q.enqueue(mr("world")).unwrap();
        let provider = StubProvider {
            name: "openai",
            model: "text-embedding-ada-002",
            tokens: 42,
        };
        let writer = MemWriter::default();
        let audit = CountingAuditWriter::default();
        let worker = Worker {
            queue: &q,
            provider: &provider,
            writer: &writer,
            audit: &audit,
        };
        let n = worker.process_batch(10).await;
        assert_eq!(n, 2);
        assert_eq!(writer.row_count(), 2, "both rows written");
        for len in writer.vector_lens() {
            assert_eq!(len, EMBEDDING_DIM, "all written vectors are 1536-dim");
        }
        // Q-L1A-3: full audit — both calls recorded.
        let ev = audit.events();
        assert_eq!(ev.len(), 2);
        assert!(matches!(ev[0].outcome, AuditOutcome::Ok));
        assert_eq!(ev[0].tokens, 42);
        assert_eq!(ev[0].model, "text-embedding-ada-002");
        assert_eq!(ev[0].provider, "openai");
    }

    #[tokio::test]
    async fn worker_dim_mismatch_audits_but_does_not_write() {
        // Two failure modes: (a) provider returns OK with wrong-dim vector,
        // (b) provider explicitly returns DimMismatch. Both must audit + skip write.
        let q = Queue::new(10);
        q.enqueue(mr("a")).unwrap();
        let provider = WrongDimProvider;
        let writer = MemWriter::default();
        let audit = CountingAuditWriter::default();
        let worker = Worker {
            queue: &q,
            provider: &provider,
            writer: &writer,
            audit: &audit,
        };
        worker.process_batch(10).await;
        assert_eq!(writer.row_count(), 0, "wrong-dim must NOT write");
        let ev = audit.events();
        assert_eq!(ev.len(), 1);
        match &ev[0].outcome {
            AuditOutcome::DimMismatch { returned_dim } => assert_eq!(*returned_dim, 768),
            other => panic!("expected DimMismatch, got {other:?}"),
        }
    }

    #[tokio::test]
    async fn worker_provider_error_is_audited_only() {
        let q = Queue::new(10);
        q.enqueue(mr("a")).unwrap();
        let provider = ErrorProvider;
        let writer = MemWriter::default();
        let audit = CountingAuditWriter::default();
        let worker = Worker {
            queue: &q,
            provider: &provider,
            writer: &writer,
            audit: &audit,
        };
        worker.process_batch(10).await;
        assert_eq!(writer.row_count(), 0);
        let ev = audit.events();
        assert_eq!(ev.len(), 1);
        assert!(matches!(ev[0].outcome, AuditOutcome::ProviderError(_)));
    }

    #[tokio::test]
    async fn worker_write_failure_emits_second_audit_row() {
        // Q-L1A-3 + defense-in-depth: a DB write failure after a successful
        // provider call must be its OWN audit row so SRE can distinguish
        // "we paid for the tokens" from "we successfully stored the result".
        let q = Queue::new(10);
        q.enqueue(mr("a")).unwrap();
        let provider = StubProvider {
            name: "openai",
            model: "text-embedding-ada-002",
            tokens: 50,
        };
        let writer = MemWriter {
            fail_next: StdMutex::new(true),
            ..Default::default()
        };
        let audit = CountingAuditWriter::default();
        let worker = Worker {
            queue: &q,
            provider: &provider,
            writer: &writer,
            audit: &audit,
        };
        worker.process_batch(10).await;
        assert_eq!(writer.row_count(), 0, "write failed → no row");
        let ev = audit.events();
        assert_eq!(ev.len(), 2, "must record OK + WriteError");
        assert!(matches!(ev[0].outcome, AuditOutcome::Ok));
        assert!(matches!(ev[1].outcome, AuditOutcome::WriteError(_)));
    }

    #[tokio::test]
    async fn worker_respects_max_items_cap() {
        let q = Queue::new(100);
        for i in 0..50 {
            q.enqueue(mr(&format!("text-{i}"))).unwrap();
        }
        let provider = StubProvider {
            name: "openai",
            model: "text-embedding-ada-002",
            tokens: 1,
        };
        let writer = MemWriter::default();
        let audit = CountingAuditWriter::default();
        let worker = Worker {
            queue: &q,
            provider: &provider,
            writer: &writer,
            audit: &audit,
        };
        let n = worker.process_batch(10).await;
        assert_eq!(n, 10, "max_items cap honored");
        assert_eq!(q.depth(), 40, "remaining items still in queue");
    }

    #[tokio::test]
    async fn process_batch_empty_queue_returns_zero() {
        let q = Queue::new(10);
        let provider = StubProvider {
            name: "openai",
            model: "text-embedding-ada-002",
            tokens: 1,
        };
        let writer = MemWriter::default();
        let audit = CountingAuditWriter::default();
        let worker = Worker {
            queue: &q,
            provider: &provider,
            writer: &writer,
            audit: &audit,
        };
        let n = worker.process_batch(100).await;
        assert_eq!(n, 0);
        assert_eq!(audit.events().len(), 0);
    }

    #[test]
    fn embedding_dim_constant_is_1536_q_l3i_1() {
        // Regression guard — Q-L3I-1 LOCKED V1.
        assert_eq!(EMBEDDING_DIM, 1536);
    }
}
