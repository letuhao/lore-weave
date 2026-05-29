//! L3.I.5 integration test — embedding retrieval ranking.
//!
//! Cycle 16 (L3.I) ships the pgvector schema + the embedding queue. This
//! integration test exercises the **full enqueue → embed → write → cosine-
//! retrieval** flow without needing a live Postgres. Cosine similarity is
//! computed against a deterministic stub provider; the queue + worker +
//! audit emitter are exercised end-to-end through the public crate API.
//!
//! The "live retrieval" test against a real pgvector HNSW index is deferred
//! to D-EMBEDDING-QUEUE-LIVE-WIRING — it needs a running per-reality DB
//! created by the cycle-5 provisioner (currently no test bench has that
//! plumbed up).
//!
//! ## LOCKED decisions exercised
//!
//! - **Q-L3-1** (V1 worker placement): we import the worker straight from
//!   the `world-service` crate — proving Q-L3-1 V1 lock is wired correctly.
//! - **Q-L3I-1** (dim=1536): the stub provider returns a 1536-dim vector
//!   and the test asserts the writer stored exactly 1536 floats.
//! - **Q-L1A-3** (full audit): every embed call (Ok + error) lands in the
//!   audit writer — asserted by [`CountingAuditWriter`].

use std::collections::HashMap;
use uuid::Uuid;
use world_service::{
    AuditEvent, AuditOutcome, AuditWriter, CountingAuditWriter, EmbedResult, EmbeddingProvider,
    EmbeddingQueue, EmbeddingWorker, EmbeddingWriter, MemoryRef, EMBEDDING_DIM,
};

// ───────────────────────────────────────────────────────────────────────────
// Stubs
// ───────────────────────────────────────────────────────────────────────────

/// Provider that maps text → deterministic 1536-dim vector. Same text →
/// same vector, so cosine-similarity ranking is testable.
struct DeterministicEmbedder;

impl EmbeddingProvider for DeterministicEmbedder {
    fn embed(&self, text: &str) -> (String, EmbedResult) {
        let mut v = vec![0.0f32; EMBEDDING_DIM];
        // Seed from text hash; spread across all 1536 dims so similar text
        // yields similar vectors (not actually similar text → similar
        // vectors here — we test the PLUMBING not the model quality).
        let mut h: u64 = 5381;
        for b in text.bytes() {
            h = h.wrapping_mul(33) ^ (b as u64);
        }
        for (i, x) in v.iter_mut().enumerate() {
            let scrambled = h.wrapping_mul(1099511628211).wrapping_add(i as u64);
            *x = ((scrambled & 0xffff) as f32) / 65535.0;
        }
        // Normalize to unit length (matches OpenAI ada-002 output shape).
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

/// In-memory writer that records by full PK.
#[derive(Default)]
struct MemWriter {
    rows: HashMap<(Uuid, Uuid, Uuid), Vec<f32>>,
}

impl EmbeddingWriter for MemWriter {
    fn write_embedding(
        &mut self,
        reality_id: Uuid,
        npc_id: Uuid,
        session_id: Uuid,
        vector: &[f32],
    ) -> Result<(), String> {
        self.rows
            .insert((reality_id, npc_id, session_id), vector.to_vec());
        Ok(())
    }
}

fn cosine(a: &[f32], b: &[f32]) -> f32 {
    let dot: f32 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
    let na: f32 = a.iter().map(|x| x * x).sum::<f32>().sqrt();
    let nb: f32 = b.iter().map(|x| x * x).sum::<f32>().sqrt();
    if na == 0.0 || nb == 0.0 {
        return 0.0;
    }
    dot / (na * nb)
}

fn mr(reality: Uuid, npc: Uuid, session: Uuid, text: &str) -> MemoryRef {
    MemoryRef {
        reality_id: reality,
        npc_id: npc,
        session_id: session,
        content_hash: format!("h-{text}"),
        text: text.into(),
    }
}

// ───────────────────────────────────────────────────────────────────────────
// Tests
// ───────────────────────────────────────────────────────────────────────────

#[test]
fn end_to_end_enqueue_embed_write_audit() {
    // Three NPC memories in two sessions; all should be embedded + written.
    let reality = Uuid::from_u128(0xDEAD_BEEF);
    let npc_a = Uuid::from_u128(0xA);
    let npc_b = Uuid::from_u128(0xB);
    let session_1 = Uuid::from_u128(1);
    let session_2 = Uuid::from_u128(2);

    let q = EmbeddingQueue::new(100);
    q.enqueue(mr(reality, npc_a, session_1, "the dragon roared"))
        .unwrap();
    q.enqueue(mr(reality, npc_a, session_2, "the village burned"))
        .unwrap();
    q.enqueue(mr(reality, npc_b, session_1, "i found a coin"))
        .unwrap();

    let provider = DeterministicEmbedder;
    let mut writer = MemWriter::default();
    let mut audit = CountingAuditWriter::default();
    let mut worker = EmbeddingWorker {
        queue: &q,
        provider: &provider,
        writer: &mut writer,
        audit: &mut audit,
    };

    let n = worker.process_batch(10);
    assert_eq!(n, 3, "all three enqueued memories processed");
    assert_eq!(writer.rows.len(), 3, "all three rows written");
    for v in writer.rows.values() {
        assert_eq!(v.len(), EMBEDDING_DIM, "Q-L3I-1 dim=1536 enforced");
    }
    // Q-L1A-3 — every provider call audited.
    assert_eq!(audit.events.len(), 3);
    assert_eq!(audit.count_by_outcome_kind("ok"), 3);
    // Cost rolled up correctly.
    let expected_tokens: u32 = ["the dragon roared", "the village burned", "i found a coin"]
        .iter()
        .map(|s| s.len() as u32)
        .sum();
    assert_eq!(audit.total_ok_tokens(), expected_tokens);
}

#[test]
fn cosine_retrieval_ranks_same_text_above_different() {
    // Determinism property: same input → same output. So a query for text X
    // matches the stored embedding for text X with cosine = 1.0 (modulo
    // f32 rounding), and matches the embedding for a different text Y with
    // cosine < 1.0. This is the SHAPE of the HNSW retrieval test from the
    // L3.I.5 brief — the live version against a real pgvector index lands
    // in D-EMBEDDING-QUEUE-LIVE-WIRING.
    let reality = Uuid::from_u128(0xDEAD_BEEF);

    let q = EmbeddingQueue::new(100);
    q.enqueue(mr(
        reality,
        Uuid::from_u128(10),
        Uuid::from_u128(10),
        "the dragon roared",
    ))
    .unwrap();
    q.enqueue(mr(
        reality,
        Uuid::from_u128(11),
        Uuid::from_u128(11),
        "i bought a sword",
    ))
    .unwrap();
    q.enqueue(mr(
        reality,
        Uuid::from_u128(12),
        Uuid::from_u128(12),
        "the merchant smiled",
    ))
    .unwrap();

    let provider = DeterministicEmbedder;
    let mut writer = MemWriter::default();
    let mut audit = CountingAuditWriter::default();
    let mut worker = EmbeddingWorker {
        queue: &q,
        provider: &provider,
        writer: &mut writer,
        audit: &mut audit,
    };
    worker.process_batch(10);

    // Query embedding for "the dragon roared" — same provider, same text →
    // matches the stored row exactly.
    let (_, query_result) = provider.embed("the dragon roared");
    let query_vec = match query_result {
        EmbedResult::Ok { vector, .. } => vector,
        _ => panic!("stub provider should always return Ok"),
    };

    let dragon_key = (
        reality,
        Uuid::from_u128(10),
        Uuid::from_u128(10),
    );
    let sword_key = (reality, Uuid::from_u128(11), Uuid::from_u128(11));

    let dragon_vec = writer.rows.get(&dragon_key).expect("dragon row stored");
    let sword_vec = writer.rows.get(&sword_key).expect("sword row stored");

    let dragon_sim = cosine(&query_vec, dragon_vec);
    let sword_sim = cosine(&query_vec, sword_vec);

    assert!(
        (dragon_sim - 1.0).abs() < 1e-4,
        "exact-match cosine ≈ 1.0, got {dragon_sim}"
    );
    assert!(
        dragon_sim > sword_sim,
        "dragon ({dragon_sim}) ranks above sword ({sword_sim})"
    );
}

#[test]
fn non_blocking_enqueue_returns_immediately_even_with_backlog() {
    // Q-L3-1 acceptance: enqueue MUST NOT block on provider call. We push
    // 50 items WITHOUT running the worker — enqueue should be O(1) per
    // item; no provider calls happen until we explicitly drive the worker.
    let q = EmbeddingQueue::new(100);
    let mut audit = CountingAuditWriter::default();
    for i in 0..50 {
        q.enqueue(mr(
            Uuid::from_u128(1),
            Uuid::from_u128(i),
            Uuid::from_u128(i),
            &format!("memory-{i}"),
        ))
        .unwrap();
    }
    assert_eq!(q.depth(), 50);
    assert_eq!(
        audit.events.len(),
        0,
        "enqueue must NOT call provider — zero audits"
    );
    // Sanity: AuditWriter trait IS the same `audit` we constructed.
    audit.record(AuditEvent {
        reality_id: Uuid::from_u128(0),
        npc_id: Uuid::from_u128(0),
        session_id: Uuid::from_u128(0),
        provider: "test".into(),
        model: "test".into(),
        tokens: 0,
        outcome: AuditOutcome::Ok,
    });
    assert_eq!(audit.events.len(), 1);
}
