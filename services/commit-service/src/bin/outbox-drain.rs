//! DEV outbox drain — `events_outbox` → per-reality Redis stream.
//!
//! ⚠ **This is a development stand-in, not the production publisher.**
//! Production fan-out is `services/publisher` (Go): leader election,
//! heartbeats, retry/dead-letter policy, and per-reality shard resolution
//! through the meta `reality_registry`. Wiring that for a game reality is
//! deployment work (a registry row + shard DSN), deliberately separate from
//! this slice. This binary exists so the committed-event → client-DTO path
//! can be proven end to end TODAY, and it mirrors the publisher's core loop
//! exactly (`poll_loop.go`):
//!
//!   SELECT … FOR UPDATE SKIP LOCKED  →  XADD  →  mark published, one tx.
//!
//! At-least-once by construction: the XADD happens before the commit, so a
//! crash in between re-publishes next tick. Consumers dedup (EVT-L3).
//!
//! Usage:
//! ```text
//! cargo run -p commit-service --bin outbox-drain -- \
//!   --pg-url postgres://… --redis-url redis://127.0.0.1:6399/0 \
//!   --reality <uuid> [--once]
//! ```

use redis::AsyncCommands;
use sqlx::postgres::PgPoolOptions;
use sqlx::Row;
use uuid::Uuid;

struct Args {
    pg_url: String,
    redis_url: String,
    reality: Uuid,
    once: bool,
    batch: i64,
}

fn parse_args() -> anyhow::Result<Args> {
    let (mut pg_url, mut reality) = (None, None);
    let mut redis_url = "redis://127.0.0.1:6399/0".to_string();
    let (mut once, mut batch) = (false, 100i64);
    let argv: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < argv.len() {
        match argv[i].as_str() {
            "--pg-url" => { pg_url = Some(argv[i + 1].clone()); i += 2; }
            "--redis-url" => { redis_url = argv[i + 1].clone(); i += 2; }
            "--reality" => { reality = Some(argv[i + 1].parse()?); i += 2; }
            "--batch" => { batch = argv[i + 1].parse()?; i += 2; }
            "--once" => { once = true; i += 1; }
            other => anyhow::bail!("unknown arg {other}"),
        }
    }
    Ok(Args {
        pg_url: pg_url.ok_or_else(|| anyhow::anyhow!("--pg-url required"))?,
        redis_url,
        reality: reality.ok_or_else(|| anyhow::anyhow!("--reality required"))?,
        once,
        batch,
    })
}

/// The per-reality committed-event stream the room consumer reads.
fn stream_key(reality: Uuid) -> String {
    format!("reality:{reality}:events")
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let args = parse_args()?;
    let pool = PgPoolOptions::new().max_connections(4).connect(&args.pg_url).await?;
    let client = redis::Client::open(args.redis_url.as_str())?;
    let mut conn = redis::aio::ConnectionManager::new(client).await?;
    let stream = stream_key(args.reality);
    let mut total = 0u64;

    loop {
        let mut tx = pool.begin().await?;
        // Join the outbox pointer to its event row. SKIP LOCKED so a second
        // drainer never re-publishes a row this one is mid-flight on.
        let rows = sqlx::query(
            r#"
            SELECT o.event_id, e.event_type, e.channel_id, e.channel_event_id,
                   e.writer_epoch, e.payload, e.metadata
              FROM events_outbox o
              JOIN events e ON e.event_id = o.event_id AND e.reality_id = o.reality_id
             WHERE o.reality_id = $1 AND o.published = FALSE
                   AND o.dead_lettered_at IS NULL
             ORDER BY e.channel_id, e.channel_event_id
             LIMIT $2
               FOR UPDATE OF o SKIP LOCKED
            "#,
        )
        .bind(args.reality)
        .bind(args.batch)
        .fetch_all(&mut *tx)
        .await?;

        if rows.is_empty() {
            tx.rollback().await.ok();
            if args.once {
                break;
            }
            tokio::time::sleep(std::time::Duration::from_millis(500)).await;
            continue;
        }

        for row in &rows {
            let event_id: Uuid = row.try_get("event_id")?;
            let channel_event_id: Option<i64> = row.try_get("channel_event_id")?;
            // The wire shape the room consumer parses. Ids that are BIGINT
            // server-side are emitted as STRINGS (CWC-A2) — this is the
            // producer boundary where the 2^53 rule is applied.
            let envelope = serde_json::json!({
                "event_id": event_id.to_string(),
                "event_type": row.try_get::<String, _>("event_type")?,
                "channel_id": row.try_get::<Option<i64>, _>("channel_id")?.map(|v| v.to_string()),
                "channel_event_id": channel_event_id.map(|v| v.to_string()),
                "writer_epoch": row.try_get::<Option<i64>, _>("writer_epoch")?.map(|v| v.to_string()),
                "payload": row.try_get::<serde_json::Value, _>("payload")?,
                "metadata": row.try_get::<Option<serde_json::Value>, _>("metadata")?,
            });
            let _: String = conn
                .xadd(&stream, "*", &[("event", envelope.to_string())])
                .await?;
            sqlx::query(
                "UPDATE events_outbox
                    SET published = TRUE, attempts = attempts + 1, last_attempt_at = NOW()
                  WHERE event_id = $1",
            )
            .bind(event_id)
            .execute(&mut *tx)
            .await?;
            total += 1;
        }
        tx.commit().await?;
        println!("drained {} row(s) → {stream}", rows.len());
    }

    println!("outbox-drain: {total} event(s) published to {stream}");
    Ok(())
}
