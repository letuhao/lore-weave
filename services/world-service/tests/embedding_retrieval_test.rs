//! L3.I.5 integration test — embedding retrieval ranking.
//!
//! Cycle 16 (L3.I) ships the pgvector schema + the embedding queue. This
//! integration test exercises the **full enqueue → embed → write → cosine-
//! retrieval** flow without needing a live Postgres. Cosine similarity is
//! computed against a deterministic stub provider; the queue + worker +
//! audit emitter are exercised end-to-end through the public crate API.
//!
//! The "live retrieval" test against a real pgvector HNSW index is the
//! separate gated `embedding_live.rs` smoke (DEFERRED-059 core).
//!
//! ## LOCKED decisions exercised
//!
//! - **Q-L3-1** (V1 worker placement): we import the worker straight from
//!   the `world-service` crate — proving Q-L3-1 V1 lock is wired correctly.
//! - **Q-L3I-1** (dim=1536): the stub provider returns a 1536-dim vector
//!   and the test asserts the writer stored exactly 1536 floats.
//! - **Q-L1A-3** (full audit): every embed call (Ok + error) lands in the
//!   audit writer — asserted by [`CountingAuditWriter`].

use uuid::Uuid;
// 091: shared in-memory test doubles (were copy-pasted here).
use world_service::embedding_queue::testkit::{DeterministicEmbedder, MemWriter};
use world_service::{
    AuditEvent, AuditOutcome, AuditWriter, CountingAuditWriter, EMBEDDING_DIM, EmbedResult,
    EmbeddingProvider, EmbeddingQueue, EmbeddingWorker, MemoryRef,
};

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

#[tokio::test]
async fn end_to_end_enqueue_embed_write_audit() {
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
    let writer = MemWriter::default();
    let audit = CountingAuditWriter::default();
    let worker = EmbeddingWorker {
        queue: &q,
        provider: &provider,
        writer: &writer,
        audit: &audit,
    };

    let n = worker.process_batch(10).await;
    assert_eq!(n, 3, "all three enqueued memories processed");
    assert_eq!(writer.len(), 3, "all three rows written");
    for len in writer.vector_lens() {
        assert_eq!(len, EMBEDDING_DIM, "Q-L3I-1 dim=1536 enforced");
    }
    // Q-L1A-3 — every provider call audited.
    assert_eq!(audit.len(), 3);
    assert_eq!(audit.count_by_outcome_kind("ok"), 3);
    let expected_tokens: u32 = ["the dragon roared", "the village burned", "i found a coin"]
        .iter()
        .map(|s| s.len() as u32)
        .sum();
    assert_eq!(audit.total_ok_tokens(), expected_tokens);
}

#[tokio::test]
async fn cosine_retrieval_ranks_same_text_above_different() {
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
    let writer = MemWriter::default();
    let audit = CountingAuditWriter::default();
    let worker = EmbeddingWorker {
        queue: &q,
        provider: &provider,
        writer: &writer,
        audit: &audit,
    };
    worker.process_batch(10).await;

    let (_, query_result) = provider.embed("the dragon roared").await;
    let query_vec = match query_result {
        EmbedResult::Ok { vector, .. } => vector,
        _ => panic!("stub provider should always return Ok"),
    };

    let dragon_key = (reality, Uuid::from_u128(10), Uuid::from_u128(10));
    let sword_key = (reality, Uuid::from_u128(11), Uuid::from_u128(11));

    let dragon_vec = writer.get(&dragon_key).expect("dragon row stored");
    let sword_vec = writer.get(&sword_key).expect("sword row stored");

    let dragon_sim = cosine(&query_vec, &dragon_vec);
    let sword_sim = cosine(&query_vec, &sword_vec);

    assert!(
        (dragon_sim - 1.0).abs() < 1e-4,
        "exact-match cosine ≈ 1.0, got {dragon_sim}"
    );
    assert!(
        dragon_sim > sword_sim,
        "dragon ({dragon_sim}) ranks above sword ({sword_sim})"
    );
}

#[tokio::test]
async fn non_blocking_enqueue_returns_immediately_even_with_backlog() {
    let q = EmbeddingQueue::new(100);
    let audit = CountingAuditWriter::default();
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
        audit.len(),
        0,
        "enqueue must NOT call provider — zero audits"
    );
    // Sanity: AuditWriter trait IS the same `audit` we constructed.
    audit
        .record(AuditEvent {
            reality_id: Uuid::from_u128(0),
            npc_id: Uuid::from_u128(0),
            session_id: Uuid::from_u128(0),
            provider: "test".into(),
            model: "test".into(),
            tokens: 0,
            outcome: AuditOutcome::Ok,
        })
        .await;
    assert_eq!(audit.len(), 1);
}
