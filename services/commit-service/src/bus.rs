//! EVT-L proposal-bus rail (Redis Streams) — the consumer half of
//! `07_llm_proposal_bus.md`, mirroring the proven Go rail
//! (`meta-worker/pkg/{redisconsume,consumer}`, `breach-notifier`):
//!
//! - `XGROUP CREATE … MKSTREAM` at startup, tolerating BUSYGROUP (idempotent);
//! - **ACK only after successful processing** — a dispatch error leaves the
//!   entry in the PEL for redelivery (EVT-L2: at-least-once + dedup);
//! - `XAUTOCLAIM` stale-PEL reclaim for consumers that died mid-flight;
//! - batched `XACK` (per-message ack RTT was the measured Go ceiling);
//! - dead-letter after `max_attempts` to `<stream>:dead` with the reason
//!   (EVT-L6; **forbidden: silent drop** — EVT-L5).

use redis::aio::ConnectionManager;
use redis::streams::{
    StreamAutoClaimOptions, StreamAutoClaimReply, StreamId, StreamReadOptions, StreamReadReply,
};
use redis::AsyncCommands;

#[derive(Debug, Clone)]
pub struct BusConfig {
    pub stream: String,
    pub group: String,
    pub consumer: String,
    /// XREADGROUP BLOCK milliseconds (0 = don't block).
    pub block_ms: usize,
    pub batch: usize,
    /// Delivery attempts before dead-lettering (EVT-L6).
    pub max_attempts: usize,
    /// XAUTOCLAIM min-idle before stealing a dead consumer's PEL entry.
    pub reclaim_min_idle_ms: usize,
}

impl BusConfig {
    pub fn dead_stream(&self) -> String {
        format!("{}:dead", self.stream)
    }
}

/// One raw bus entry (stream id + flat field map, as XADD wrote it).
#[derive(Debug, Clone)]
pub struct BusMessage {
    pub id: String,
    pub fields: Vec<(String, String)>,
}

impl BusMessage {
    pub fn field(&self, name: &str) -> Option<&str> {
        self.fields.iter().find(|(k, _)| k == name).map(|(_, v)| v.as_str())
    }

    fn from_stream_id(sid: &StreamId) -> Self {
        let fields = sid
            .map
            .iter()
            .map(|(k, v)| {
                let s = match v {
                    redis::Value::BulkString(b) => String::from_utf8_lossy(b).into_owned(),
                    other => format!("{other:?}"),
                };
                (k.clone(), s)
            })
            .collect();
        Self { id: sid.id.clone(), fields }
    }
}

pub struct ProposalBus {
    conn: ConnectionManager,
    pub cfg: BusConfig,
}

impl ProposalBus {
    pub async fn connect(redis_url: &str, cfg: BusConfig) -> anyhow::Result<Self> {
        let client = redis::Client::open(redis_url)?;
        let conn = ConnectionManager::new(client).await?;
        let mut bus = Self { conn, cfg };
        bus.ensure_group().await?;
        Ok(bus)
    }

    /// Idempotent group bootstrap (BUSYGROUP tolerated — Go rail pattern).
    async fn ensure_group(&mut self) -> anyhow::Result<()> {
        let res: redis::RedisResult<()> = redis::cmd("XGROUP")
            .arg("CREATE")
            .arg(&self.cfg.stream)
            .arg(&self.cfg.group)
            .arg("$")
            .arg("MKSTREAM")
            .query_async(&mut self.conn)
            .await;
        match res {
            Ok(()) => Ok(()),
            Err(e) if e.to_string().contains("BUSYGROUP") => Ok(()),
            Err(e) => Err(e.into()),
        }
    }

    /// Pull fresh entries for this consumer (`>` cursor).
    pub async fn fetch(&mut self) -> anyhow::Result<Vec<BusMessage>> {
        let opts = StreamReadOptions::default()
            .group(&self.cfg.group, &self.cfg.consumer)
            .count(self.cfg.batch)
            .block(self.cfg.block_ms);
        let reply: StreamReadReply = self
            .conn
            .xread_options(&[&self.cfg.stream], &[">"], &opts)
            .await?;
        Ok(reply
            .keys
            .iter()
            .flat_map(|k| k.ids.iter().map(BusMessage::from_stream_id))
            .collect())
    }

    /// Steal stale PEL entries from dead consumers (XAUTOCLAIM rail).
    /// Returns (message, delivery_attempts) so the caller can dead-letter
    /// poison entries instead of spinning on them forever.
    pub async fn reclaim(&mut self) -> anyhow::Result<Vec<(BusMessage, usize)>> {
        let opts = StreamAutoClaimOptions::default().count(self.cfg.batch);
        let reply: StreamAutoClaimReply = self
            .conn
            .xautoclaim_options(
                &self.cfg.stream,
                &self.cfg.group,
                &self.cfg.consumer,
                self.cfg.reclaim_min_idle_ms,
                "0-0",
                opts,
            )
            .await?;
        let mut out = Vec::new();
        for sid in &reply.claimed {
            let msg = BusMessage::from_stream_id(sid);
            // Delivery count comes from XPENDING for exactly this id.
            let pending: redis::Value = redis::cmd("XPENDING")
                .arg(&self.cfg.stream)
                .arg(&self.cfg.group)
                .arg(&msg.id)
                .arg(&msg.id)
                .arg(1)
                .query_async(&mut self.conn)
                .await?;
            let attempts = extract_delivery_count(&pending).unwrap_or(1);
            out.push((msg, attempts));
        }
        Ok(out)
    }

    /// Batched XACK — ONLY call after successful processing (or dead-letter).
    pub async fn ack(&mut self, ids: &[String]) -> anyhow::Result<()> {
        if ids.is_empty() {
            return Ok(());
        }
        let _: usize = self.conn.xack(&self.cfg.stream, &self.cfg.group, ids).await?;
        Ok(())
    }

    /// EVT-L6 dead-letter: copy to `<stream>:dead` WITH the reason, then ack
    /// the original. Replay assigns a new proposal_id (spec) — the dead
    /// entry records the original id for the operator.
    pub async fn dead_letter(&mut self, msg: &BusMessage, reason: &str) -> anyhow::Result<()> {
        let mut fields: Vec<(String, String)> = msg.fields.clone();
        fields.push(("dead_reason".into(), reason.to_string()));
        fields.push(("original_stream_id".into(), msg.id.clone()));
        let _: String = self
            .conn
            .xadd(self.cfg.dead_stream(), "*", &fields)
            .await?;
        self.ack(std::slice::from_ref(&msg.id)).await
    }

    /// Test/ops helper: XADD a proposal onto the stream.
    pub async fn publish(&mut self, fields: &[(String, String)]) -> anyhow::Result<String> {
        Ok(self.conn.xadd(&self.cfg.stream, "*", fields).await?)
    }

    /// PEL depth — the EVT-L5 "lagging" signal.
    pub async fn pel_len(&mut self) -> anyhow::Result<usize> {
        let v: redis::Value = redis::cmd("XPENDING")
            .arg(&self.cfg.stream)
            .arg(&self.cfg.group)
            .query_async(&mut self.conn)
            .await?;
        // Summary form: first element is the count.
        if let redis::Value::Array(items) = &v
            && let Some(redis::Value::Int(n)) = items.first()
        {
            return Ok(*n as usize);
        }
        Ok(0)
    }
}

/// XPENDING extended reply: [[id, consumer, idle, delivery_count], …].
fn extract_delivery_count(v: &redis::Value) -> Option<usize> {
    if let redis::Value::Array(rows) = v
        && let Some(redis::Value::Array(cols)) = rows.first()
        && let Some(redis::Value::Int(n)) = cols.get(3)
    {
        return Some(*n as usize);
    }
    None
}
