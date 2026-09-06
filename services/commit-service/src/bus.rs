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
    /// XREADGROUP BLOCK milliseconds. **`0` = don't block** — and that is true
    /// because [`BusConfig::read_options`] omits the argument, NOT because the
    /// server reads `BLOCK 0` that way (it reads it as *wait forever*). This
    /// sentence was here, and false, for the whole life of `DFO-7`.
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

    /// The exact `XREADGROUP` options [`ProposalBus::fetch`] issues.
    ///
    /// Extracted so a check can read the SAME construction the production call
    /// uses. A test that rebuilt these options itself would be a second copy of
    /// the decision, and the day the two disagreed the check would be watching
    /// the copy with no defect — which is precisely how `DFO-7` survived.
    ///
    /// # `block_ms: 0` OMITS the argument — it does not pass `BLOCK 0`
    ///
    /// `DFO-7`. In the stream protocol **`BLOCK 0` means wait indefinitely**;
    /// the way to not block is to leave the argument off. This built it
    /// unconditionally, so the one call site that asked for *"never block"* —
    /// the binding-signal rail, under a comment saying exactly that — asked for
    /// *"block forever"* instead, and `spine --drain-once` hung on the first
    /// statement of its first iteration.
    ///
    /// Two doc comments described the intended behaviour correctly and neither
    /// was ever executed against a server. So the branch lives HERE, at the one
    /// place the value becomes a command, rather than as a rule each call site
    /// is trusted to remember.
    pub fn read_options(&self) -> StreamReadOptions {
        let opts = StreamReadOptions::default()
            .group(&self.group, &self.consumer)
            .count(self.batch);
        if self.block_ms == 0 {
            opts
        } else {
            opts.block(self.block_ms)
        }
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
        let opts = self.cfg.read_options();
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

#[cfg(test)]
mod read_options_tests {
    use super::BusConfig;
    use redis::ToRedisArgs;

    fn cfg(block_ms: usize) -> BusConfig {
        BusConfig {
            stream: "s".into(),
            group: "g".into(),
            consumer: "c".into(),
            block_ms,
            batch: 8,
            max_attempts: 5,
            reclaim_min_idle_ms: 30_000,
        }
    }

    /// The args `fetch` will actually put on the wire, read off the SAME
    /// builder rather than re-derived here.
    fn args(block_ms: usize) -> Vec<String> {
        cfg(block_ms)
            .read_options()
            .to_redis_args()
            .into_iter()
            .map(|a| String::from_utf8_lossy(&a).into_owned())
            .collect()
    }

    fn block_value(a: &[String]) -> Option<String> {
        a.iter().position(|x| x == "BLOCK").map(|i| a[i + 1].clone())
    }

    /// `DFO-7`. **`BLOCK 0` is Redis for *wait forever*, not for *do not
    /// wait*** — and two doc comments in this repo said the opposite while the
    /// binding-signal rail passed exactly `0`. `drain_and_reconcile` is the
    /// first statement of the spine's loop and reads a stream that is empty
    /// almost always, so `spine --drain-once` blocked on iteration one, before
    /// it ever saw a proposal, and never reached its `break`.
    ///
    /// Measured against a live server, on an empty group, the argument being
    /// the only difference: `BLOCK 0` → killed at 5s (`rc=124`); the same read
    /// with no `BLOCK` at all → returned, `rc=0`.
    ///
    /// The way to not block is to OMIT the argument. So `0` omits it.
    #[test]
    fn block_ms_zero_does_not_put_block_on_the_wire() {
        let a = args(0);
        assert!(
            block_value(&a).is_none(),
            "block_ms 0 must emit no BLOCK argument at all — `BLOCK 0` blocks \
             FOREVER, which is the DFO-7 hang. Got: {a:?}"
        );
    }

    /// The other direction, and it is not decoration: a fix that simply stopped
    /// emitting `BLOCK` would satisfy the arm above and silently turn the
    /// proposal rail into a hot spin at 100% CPU.
    #[test]
    fn a_real_timeout_is_still_sent() {
        assert_eq!(block_value(&args(250)).as_deref(), Some("250"));
        assert_eq!(block_value(&args(2_000)).as_deref(), Some("2000"));
    }

    /// And the rest of the command is unchanged by either decision.
    #[test]
    fn the_group_and_count_survive_both_ways() {
        for ms in [0, 250] {
            let a = args(ms);
            assert!(a.contains(&"GROUP".to_string()), "{a:?}");
            assert!(a.contains(&"g".to_string()) && a.contains(&"c".to_string()), "{a:?}");
            assert_eq!(
                a.iter().position(|x| x == "COUNT").map(|i| a[i + 1].clone()),
                Some("8".to_string())
            );
        }
    }
}
