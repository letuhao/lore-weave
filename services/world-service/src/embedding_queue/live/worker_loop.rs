//! Tokio drain loop (DEFERRED-059 part 4): interval ticker → `process_batch`,
//! with graceful shutdown via a `watch` channel.

use std::sync::Arc;
use std::time::Duration;

use tokio::sync::watch;
use tokio::time::MissedTickBehavior;

use super::metrics::Metrics;
use crate::embedding_queue::{AuditWriter, EmbeddingProvider, EmbeddingWriter, Queue, Worker};

/// Drain the queue on `interval` until `shutdown` flips to `true` (or the
/// sender is dropped). Each tick refreshes the depth gauge, then drains up to
/// `batch_size` items. A tick that overruns the interval is coalesced
/// (`MissedTickBehavior::Skip`) rather than bursting.
#[allow(clippy::too_many_arguments)]
pub async fn run(
    queue: Arc<Queue>,
    provider: Arc<dyn EmbeddingProvider>,
    writer: Arc<dyn EmbeddingWriter>,
    audit: Arc<dyn AuditWriter>,
    metrics: Arc<Metrics>,
    interval: Duration,
    batch_size: usize,
    mut shutdown: watch::Receiver<bool>,
) {
    let mut ticker = tokio::time::interval(interval);
    ticker.set_missed_tick_behavior(MissedTickBehavior::Skip);

    loop {
        tokio::select! {
            _ = ticker.tick() => {
                metrics.queue_depth.set(queue.depth() as i64);
                let worker = Worker {
                    queue: queue.as_ref(),
                    provider: provider.as_ref(),
                    writer: writer.as_ref(),
                    audit: audit.as_ref(),
                };
                let processed = worker.process_batch(batch_size).await;
                if processed > 0 {
                    tracing::debug!(processed, "embedding batch drained");
                }
            }
            changed = shutdown.changed() => {
                // Err == sender dropped; Ok + true == explicit shutdown signal.
                if changed.is_err() || *shutdown.borrow() {
                    break;
                }
            }
        }
    }
    tracing::info!("embedding worker loop stopped");
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::embedding_queue::live::{MetricsAuditWriter, NotWiredProvider};
    use crate::embedding_queue::testkit::NoopWriter; // 091: shared no-op writer (was inline)
    use crate::embedding_queue::{CountingAuditWriter, MemoryRef};
    use uuid::Uuid;

    #[tokio::test]
    async fn loop_drains_then_stops_on_shutdown() {
        let queue = Arc::new(Queue::new(100));
        // NotWiredProvider → every item is a ProviderError (audited as a failure).
        for i in 0..5 {
            queue
                .enqueue(MemoryRef {
                    reality_id: Uuid::from_u128(1),
                    npc_id: Uuid::from_u128(i + 1),
                    session_id: Uuid::from_u128(i + 100),
                    content_hash: format!("h{i}"),
                    text: format!("memory-{i}"),
                })
                .unwrap();
        }

        let metrics = Arc::new(Metrics::new());
        let inner = Arc::new(CountingAuditWriter::default());
        let audit: Arc<dyn AuditWriter> =
            Arc::new(MetricsAuditWriter::new(inner.clone(), metrics.clone()));
        let provider: Arc<dyn EmbeddingProvider> = Arc::new(NotWiredProvider);
        let writer: Arc<dyn EmbeddingWriter> = Arc::new(NoopWriter);

        let (tx, rx) = watch::channel(false);
        let handle = tokio::spawn(run(
            queue.clone(),
            provider,
            writer,
            audit,
            metrics.clone(),
            Duration::from_millis(5),
            64,
            rx,
        ));

        // Let a few ticks drain the queue.
        for _ in 0..50 {
            if queue.depth() == 0 {
                break;
            }
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
        tx.send(true).unwrap();
        handle.await.unwrap();

        assert_eq!(queue.depth(), 0, "all items drained");
        // 5 NotWired calls → 5 failures audited.
        assert_eq!(inner.len(), 5);
        assert_eq!(metrics.failures_total.get(), 5);
    }
}
