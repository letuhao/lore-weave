//! Architecture-ceiling harness — the three numbers that stay TRUE after the
//! stubs are filled in.
//!
//! ## Why this exists (and what it deliberately does NOT measure)
//!
//! The game tier is real but incomplete: 10 validator stages are `NotRun`, the
//! POC `CombatDomain` is a 4-tool toy, and there is no island manager. So a
//! "how many players can we host" benchmark today would produce a **flattering
//! number that later collapses** — every missing piece only ADDS work.
//!
//! This harness measures the opposite kind of number: the ones set by the
//! ARCHITECTURE rather than by the domain. Adding validators, a real ruleset,
//! or an island manager can only push the real system BELOW these figures,
//! never above. That is what makes them durable — they are **upper bounds**,
//! and an upper bound measured today is still an upper bound in six months.
//!
//! | Mode | Ceiling | Bottleneck isolated |
//! |---|---|---|
//! | `c1` | turns/sec + latency on ONE channel | PG fsync + the DP-A16 CAS fence |
//! | `c2` | aggregate throughput vs K channels | PG concurrency / contention knee |
//! | `c3` | fan-out leg, XADD → XREADGROUP | Redis + payload size |
//!
//! `c1`/`c2` drive the REAL [`ChannelWriter::append`] — the same CAS-fenced,
//! 4-statement transaction the spine commits through (allocate+fence, `events`,
//! `channel_event_index`, `events_outbox`), not a re-implementation of it. A
//! harness that re-implemented the INSERT would measure a path nothing runs.
//!
//! ## The number is meaningless without the machine
//!
//! Every run prints the durability + hardware context that produced it
//! (`fsync`, `synchronous_commit`, `wal_level`, PG version, CPU count, pool
//! size, and the pre-existing `events` row count). A commit-throughput figure
//! taken with `synchronous_commit=off` is not a durability ceiling at all, and
//! a figure taken against an empty table flatters a figure taken against a
//! populated one. Both are reported so the reader can tell.
//!
//! ## Non-vacuity (the repo's bite discipline)
//!
//! Each ceiling ships a bite that must MOVE the number, proving the harness
//! measures what it claims:
//!   * `c1 --bite-sync-off` — relax `synchronous_commit` for the session.
//!     Throughput must rise sharply. If it does NOT, we were never fsync-bound
//!     and the c1 figure is not a durability ceiling.
//!   * `c2 --bite-pool1` — cap the pool at ONE connection. Aggregate throughput
//!     must then NOT scale with K, proving the c2 curve reflects real database
//!     concurrency rather than an artefact.
//!   * `c3 --bite-fat` — 100× the payload. Throughput must drop, proving we are
//!     measuring Redis work and not loop overhead.
//!
//! ## Safety
//!
//! APPEND-ONLY. This harness issues no `DELETE`, `TRUNCATE` or `DROP`; every
//! run uses a freshly minted random `reality_id`, so it cannot touch another
//! run's rows, let alone anyone's data. Point `LOREWEAVE_TEST_PG_URL` at the
//! throwaway `foundation-dev` stack (`infra/foundation-dev`).
//!
//! Usage:
//!   cargo run -p commit-service --release --bin ceilings -- c1 <n> [--bite-sync-off]
//!   cargo run -p commit-service --release --bin ceilings -- c2 <k> <n> [--bite-pool1]
//!   cargo run -p commit-service --release --bin ceilings -- c3 <n> [--bite-fat]
//!   cargo run -p commit-service --release --bin ceilings -- env
//!
//! Env: `LOREWEAVE_TEST_PG_URL` (c1/c2/env), `LOREWEAVE_TEST_REDIS_URL` (c3).

use std::sync::Arc;
use std::time::{Duration, Instant};

use dp_kernel::channel::{acquire_writer_lease, ChannelId, ChannelWriter};
use dp_kernel::envelope::EventEnvelope;
use redis::AsyncCommands;
use sqlx::postgres::PgPoolOptions;
use sqlx::{PgPool, Row};
use uuid::Uuid;

/// Representative committed-turn payload size. A 20-byte payload would flatter
/// the commit figure (less WAL per transaction); a real `turn.resolved` carries
/// the rendered event lines plus the turn number. ~640 B is what the POC
/// combat domain actually emits for a multi-line exchange.
const NARRATION_LINES: usize = 6;

/// Batch size for the pipelined publish leg — matches the Go publisher's
/// outbox drain batch.
const PIPELINE_BATCH: usize = 64;

// ─────────────────────────────── measurement ────────────────────────────────

/// Latency samples in nanoseconds, sorted on `finish()`.
struct Samples(Vec<u128>);

impl Samples {
    fn new(cap: usize) -> Self {
        Self(Vec::with_capacity(cap))
    }
    fn push(&mut self, d: Duration) {
        self.0.push(d.as_nanos());
    }
    fn finish(mut self) -> Stats {
        self.0.sort_unstable();
        let n = self.0.len();
        // Nearest-rank percentile. With n>=100 the difference from linear
        // interpolation is below the run-to-run noise on a live DB.
        let at = |p: f64| -> f64 {
            if n == 0 {
                return f64::NAN;
            }
            let idx = (((p / 100.0) * n as f64).ceil() as usize).clamp(1, n) - 1;
            self.0[idx] as f64 / 1e6
        };
        Stats {
            n,
            p50_ms: at(50.0),
            p95_ms: at(95.0),
            p99_ms: at(99.0),
            max_ms: self.0.last().copied().unwrap_or(0) as f64 / 1e6,
        }
    }
}

struct Stats {
    n: usize,
    p50_ms: f64,
    p95_ms: f64,
    p99_ms: f64,
    max_ms: f64,
}

// ───────────────────────────── environment capture ──────────────────────────

/// The context WITHOUT which a throughput figure is not interpretable.
struct PgEnv {
    version: String,
    fsync: String,
    synchronous_commit: String,
    wal_level: String,
    max_connections: String,
    events_rows: i64,
    /// Median round-trip for a trivial `SELECT 1`. Without it the commit
    /// figure is not portable: `ChannelWriter::append` issues SIX round trips
    /// (BEGIN, CAS, events, index, outbox, COMMIT), so on a link with a fat
    /// RTT — Docker Desktop's WSL2 NAT being the local example — a large slice
    /// of the measured latency is transport, not database work. Reporting it
    /// lets a reader on other hardware rescale rather than quote our number.
    rtt_p50_ms: f64,
}

async fn capture_pg_env(pool: &PgPool) -> PgEnv {
    async fn show(pool: &PgPool, name: &str) -> String {
        sqlx::query(&format!("SHOW {name}"))
            .fetch_one(pool)
            .await
            .map(|r| r.get::<String, _>(0))
            .unwrap_or_else(|_| "?".into())
    }
    // Row count matters: an empty `events` measures faster than a populated
    // one (index maintenance), so two runs are only comparable alongside it.
    let events_rows: i64 = sqlx::query("SELECT COUNT(*)::bigint FROM events")
        .fetch_one(pool)
        .await
        .map(|r| r.get::<i64, _>(0))
        .unwrap_or(-1);
    // Measured on ONE held connection, after a warmup that primes the
    // prepared-statement cache. Sampling via the pool instead would fold the
    // per-call checkout and a statement Parse into the figure and overstate
    // the wire RTT — enough, at these magnitudes, to "prove" a transport cost
    // larger than the whole transaction it is supposed to explain.
    let mut rtt = Samples::new(200);
    if let Ok(mut conn) = pool.acquire().await {
        for i in 0..250 {
            let t = Instant::now();
            let _: i32 = sqlx::query_scalar("SELECT 1")
                .fetch_one(&mut *conn)
                .await
                .unwrap_or(0);
            if i >= 50 {
                rtt.push(t.elapsed());
            }
        }
    }

    PgEnv {
        rtt_p50_ms: rtt.finish().p50_ms,
        version: show(pool, "server_version").await,
        fsync: show(pool, "fsync").await,
        synchronous_commit: show(pool, "synchronous_commit").await,
        wal_level: show(pool, "wal_level").await,
        max_connections: show(pool, "max_connections").await,
        events_rows,
    }
}

fn cpus() -> usize {
    std::thread::available_parallelism().map(|n| n.get()).unwrap_or(0)
}

fn print_env(e: &PgEnv, pool_max: u32) {
    println!(
        "env: pg_version={} fsync={} synchronous_commit={} wal_level={} \
         pg_max_connections={} pool_max={} host_cpus={} events_rows_before={} \
         rtt_p50_ms={:.3} append_roundtrips=6",
        e.version,
        e.fsync,
        e.synchronous_commit,
        e.wal_level,
        e.max_connections,
        pool_max,
        cpus(),
        e.events_rows,
        e.rtt_p50_ms
    );
    if e.fsync != "on" || e.synchronous_commit != "on" {
        // Loud, because a reader who misses this will quote a number that
        // describes a database making no durability promise.
        println!(
            "WARN: durability is RELAXED (fsync={} synchronous_commit={}) — \
             this run is NOT a durable-commit ceiling",
            e.fsync, e.synchronous_commit
        );
    }
}

// ──────────────────────────────── PG plumbing ───────────────────────────────

fn pg_url() -> String {
    std::env::var("LOREWEAVE_TEST_PG_URL")
        .expect("LOREWEAVE_TEST_PG_URL must be set (the throwaway foundation-dev PG)")
}

/// Throwaway-name guard, run before the first INSERT.
///
/// This harness issues nothing destructive, so the repo's `EnsureThrowawayDB`
/// rule does not strictly bite — but "append-only" is not the same as "safe"
/// in an EVENT-SOURCED store. A misdirected `LOREWEAVE_TEST_PG_URL` would
/// inject tens of thousands of synthetic `turn.resolved` events into a real
/// reality's `events` table, where they are by definition permanent and would
/// feed every replay and projection built from it. That is unrecoverable in a
/// quieter way than a `DELETE`, which is exactly why it deserves a guard.
///
/// Refuses anything that does not carry a throwaway marker. The escape hatch
/// must name the database EXACTLY, so it cannot be satisfied by accident.
fn guard_throwaway_db(url: &str) {
    // Database name = last path segment, minus any ?query.
    let name = url
        .rsplit('/')
        .next()
        .unwrap_or("")
        .split('?')
        .next()
        .unwrap_or("")
        .to_ascii_lowercase();

    const MARKERS: [&str; 6] = ["test", "smoke", "audit", "scratch", "bench", "ceiling"];
    // `foundation` IS the throwaway stack (infra/foundation-dev) — an isolated
    // compose project with its own volume, ports and credentials.
    let ok = name == "foundation"
        || name.starts_with("foundation_")
        || MARKERS.iter().any(|m| name.contains(m))
        || std::env::var("CEILINGS_ALLOW_DB").is_ok_and(|allowed| allowed == name);

    if !ok {
        eprintln!(
            "REFUSED: database {name:?} carries no throwaway marker ({}), and is not the \
             foundation-dev stack.\n\
             This harness writes tens of thousands of synthetic events; in an event-sourced \
             store that is permanent.\n\
             Point LOREWEAVE_TEST_PG_URL at infra/foundation-dev, or set \
             CEILINGS_ALLOW_DB={name} if you are certain.",
            MARKERS.join("/")
        );
        std::process::exit(3);
    }
}

/// Pool whose connections optionally relax `synchronous_commit` — the c1 bite.
async fn connect(url: &str, max: u32, sync_off: bool) -> Arc<PgPool> {
    guard_throwaway_db(url);
    let opts = PgPoolOptions::new().max_connections(max);
    let opts = if sync_off {
        opts.after_connect(|conn, _| {
            Box::pin(async move {
                sqlx::query("SET synchronous_commit = off").execute(conn).await?;
                Ok(())
            })
        })
    } else {
        opts
    };
    Arc::new(opts.connect(url).await.expect("connect PG"))
}

/// PG's own `now()` — keeps `recorded_at` inside the month partition that
/// migration 0002 created, without pulling a clock dependency into the harness.
async fn db_now(pool: &PgPool) -> String {
    sqlx::query("SELECT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')")
        .fetch_one(pool)
        .await
        .map(|r| r.get::<String, _>(0))
        .expect("SELECT now()")
}

/// A committed-turn envelope shaped like what the spine actually writes
/// (`turn.resolved`, decimal-string turn number, rendered narration lines).
fn turn_envelope(reality: Uuid, encounter: &str, version: u64, ts: &str) -> EventEnvelope {
    let events: Vec<String> = (0..NARRATION_LINES)
        .map(|i| {
            format!(
                "entity-{i} strikes entity-{} for {} damage ({} hp remaining)",
                i + 1,
                10 + i,
                30 - i
            )
        })
        .collect();
    EventEnvelope {
        event_id: Uuid::new_v4(),
        event_type: "turn.resolved".into(),
        event_version: 1,
        aggregate_id: encounter.into(),
        aggregate_type: "combat_session".into(),
        aggregate_version: version,
        reality_id: reality,
        occurred_at: ts.into(),
        recorded_at: ts.into(),
        payload: serde_json::json!({ "turn_number": version.to_string(), "events": events }),
        metadata: Some(serde_json::json!({ "producer_service": "ceilings-harness" })),
    }
}

// ───────────────────────────────── C1 ───────────────────────────────────────

/// ONE channel, serial appends — exactly the shape the design mandates (one
/// writer per channel, one turn resolved at a time). Concurrency inside a
/// channel is not a thing we may buy back later, so this IS the per-channel
/// ceiling, not a pessimistic sample of it.
async fn c1(n: usize, sync_off: bool) {
    let url = pg_url();
    let pool = connect(&url, 2, sync_off).await;
    let env = capture_pg_env(&pool).await;
    print_env(&env, 2);

    let reality = Uuid::new_v4();
    let ch = ChannelId(1);
    let ts = db_now(&pool).await;
    let lease = acquire_writer_lease(&pool, reality, ch).await.expect("lease");
    let writer = ChannelWriter::new(pool.clone(), reality, lease);
    let refs = serde_json::json!([]);

    // Warm the pool + plan caches so the first sample is not an outlier that
    // drags p99 for a short run.
    for v in 1..=3u64 {
        writer
            .append(&turn_envelope(reality, "warm", v, &ts), &refs)
            .await
            .expect("warmup append");
    }

    let mut s = Samples::new(n);
    let wall = Instant::now();
    for v in 1..=n as u64 {
        let env = turn_envelope(reality, "enc-1", v, &ts);
        let t = Instant::now();
        writer.append(&env, &refs).await.expect("append");
        s.push(t.elapsed());
    }
    let elapsed = wall.elapsed();
    let st = s.finish();
    let tps = st.n as f64 / elapsed.as_secs_f64();

    println!(
        "c1 mode={} n={} elapsed_s={:.3} COMMITS_PER_SEC={:.1} \
         p50_ms={:.3} p95_ms={:.3} p99_ms={:.3} max_ms={:.3}",
        if sync_off { "bite-sync-off" } else { "clean" },
        st.n,
        elapsed.as_secs_f64(),
        tps,
        st.p50_ms,
        st.p95_ms,
        st.p99_ms,
        st.max_ms
    );
}

// ───────────────────────────────── C2 ───────────────────────────────────────

/// K channels appending CONCURRENTLY against one Postgres. Each gets its own
/// `channel_writer_state` row, so they never contend on the CAS itself — what
/// this finds is where the shared database (WAL, connections, CPU) stops
/// scaling. That knee is the per-Postgres island budget.
async fn c2(k: usize, per_channel: usize, pool1: bool) {
    let url = pg_url();
    // Pool must be >= K or we measure pool starvation instead of the database.
    // Capping it at 1 is precisely the bite.
    let pool_max: u32 = if pool1 { 1 } else { (k as u32) + 2 };
    let pool = connect(&url, pool_max, false).await;
    let env = capture_pg_env(&pool).await;
    print_env(&env, pool_max);

    let reality = Uuid::new_v4();
    let ts = db_now(&pool).await;

    // Leases first, serially — acquisition is not part of the steady state.
    let mut writers = Vec::with_capacity(k);
    for c in 0..k {
        let ch = ChannelId(c as i64 + 1);
        let lease = acquire_writer_lease(&pool, reality, ch).await.expect("lease");
        writers.push(ChannelWriter::new(pool.clone(), reality, lease));
    }

    let wall = Instant::now();
    let mut tasks = Vec::with_capacity(k);
    for (c, writer) in writers.into_iter().enumerate() {
        let ts = ts.clone();
        tasks.push(tokio::spawn(async move {
            let refs = serde_json::json!([]);
            let mut s = Samples::new(per_channel);
            for v in 1..=per_channel as u64 {
                let env = turn_envelope(reality, &format!("enc-{c}"), v, &ts);
                let t = Instant::now();
                writer.append(&env, &refs).await.expect("append");
                s.push(t.elapsed());
            }
            s.finish()
        }));
    }

    // Per-channel p95s, not a pooled sample set: what a player experiences is
    // their OWN channel's tail, so the honest summary is the worst channel's
    // p95 (plus the median channel, to show whether the tail is one straggler
    // or the whole fleet degrading together).
    let mut p95s: Vec<f64> = Vec::with_capacity(k);
    let mut total = 0usize;
    for t in tasks {
        let st = t.await.expect("join");
        total += st.n;
        p95s.push(st.p95_ms);
    }
    let elapsed = wall.elapsed();
    // `total_cmp`, not `partial_cmp().expect()` — an empty per-channel sample
    // set yields NaN, and a harness that PANICS while summarising is a harness
    // that loses the run it just spent minutes measuring.
    p95s.sort_by(f64::total_cmp);
    let worst_p95 = p95s.last().copied().unwrap_or(f64::NAN);
    let median_p95 = p95s.get(p95s.len() / 2).copied().unwrap_or(f64::NAN);
    let tps = total as f64 / elapsed.as_secs_f64();

    println!(
        "c2 mode={} k={} per_channel={} n={} elapsed_s={:.3} \
         AGGREGATE_COMMITS_PER_SEC={:.1} PER_CHANNEL_COMMITS_PER_SEC={:.1} \
         worst_channel_p95_ms={:.3} median_channel_p95_ms={:.3}",
        if pool1 { "bite-pool1" } else { "clean" },
        k,
        per_channel,
        total,
        elapsed.as_secs_f64(),
        tps,
        tps / k as f64,
        worst_p95,
        median_p95
    );
}

// ───────────────────────────────── C3 ───────────────────────────────────────

/// The fan-out leg: XADD (what the Go publisher does after draining the
/// outbox) then XREADGROUP (what a `ChannelRoom` does to project a commit).
/// This deliberately excludes the publisher's POLL INTERVAL — that is a tuned
/// latency, not a throughput ceiling, and folding it in here would understate
/// what the transport can carry.
async fn c3(n: usize, fat: bool) {
    let url = std::env::var("LOREWEAVE_TEST_REDIS_URL")
        .expect("LOREWEAVE_TEST_REDIS_URL must be set");
    let client = redis::Client::open(url.as_str()).expect("redis client");
    let mut conn = redis::aio::ConnectionManager::new(client.clone())
        .await
        .expect("redis connect");

    let stream = format!("ceilings:{}", Uuid::new_v4().simple());
    let group = "g1";
    // The bite: 100× the body. If throughput does not move, the loop overhead
    // dominates and this is not a Redis measurement.
    let reps = if fat { 100 } else { 1 };
    let body: String = (0..reps)
        .map(|_| {
            r#"{"kind":"resolved","turn_number":"1","detail":{"events":["entity-1 strikes entity-2 for 10 damage (30 hp remaining)"]}}"#
        })
        .collect::<Vec<_>>()
        .join(",");
    let payload_bytes = body.len();

    let _: Result<String, _> = conn.xgroup_create_mkstream(&stream, group, "0").await;

    // ── publish leg ──
    let mut pub_s = Samples::new(n);
    let t_pub = Instant::now();
    for i in 0..n {
        let t = Instant::now();
        let _: String = conn
            .xadd(
                &stream,
                "*",
                &[("channel_event_id", i.to_string().as_str()), ("payload", body.as_str())],
            )
            .await
            .expect("xadd");
        pub_s.push(t.elapsed());
    }
    let pub_elapsed = t_pub.elapsed();

    // ── pipelined publish leg ──
    // The serial loop above is ONE round trip per event, so it measures the
    // link, not Redis — at a 0.3 ms loopback that caps out near 3 k/s no
    // matter how fast the server is. The real publisher drains the outbox in
    // batches, so the architecturally meaningful figure is the pipelined one:
    // it is what the fan-out transport can actually carry.
    let t_pipe = Instant::now();
    for chunk in 0..(n / PIPELINE_BATCH) {
        let mut pipe = redis::pipe();
        for j in 0..PIPELINE_BATCH {
            pipe.cmd("XADD")
                .arg(&stream)
                .arg("*")
                .arg("channel_event_id")
                .arg((chunk * PIPELINE_BATCH + j).to_string())
                .arg("payload")
                .arg(body.as_str())
                .ignore();
        }
        let _: () = pipe.query_async(&mut conn).await.expect("pipelined xadd");
    }
    let pipe_elapsed = t_pipe.elapsed();
    let piped = (n / PIPELINE_BATCH) * PIPELINE_BATCH;

    // ── consume leg ──
    let opts = redis::streams::StreamReadOptions::default()
        .group(group, "c1")
        .count(64);
    let mut consumed = 0usize;
    let t_con = Instant::now();
    while consumed < n {
        let reply: redis::streams::StreamReadReply = conn
            .xread_options(&[&stream], &[">"], &opts)
            .await
            .expect("xreadgroup");
        let mut ids = Vec::new();
        for key in &reply.keys {
            for id in &key.ids {
                ids.push(id.id.clone());
            }
        }
        if ids.is_empty() {
            break;
        }
        consumed += ids.len();
        // Batched ack — per-message ack RTT was the measured Go ceiling.
        let _: i64 = conn.xack(&stream, group, &ids).await.expect("xack");
    }
    let con_elapsed = t_con.elapsed();

    // Append-only harness: the stream is a fresh random key, left in place.
    // No FLUSHDB, no DEL of anything this run did not create.
    let ps = pub_s.finish();
    println!(
        "c3 mode={} n={} payload_bytes={} \
         XADD_SERIAL_PER_SEC={:.1} xadd_p50_ms={:.3} xadd_p99_ms={:.3} \
         XADD_PIPELINED_PER_SEC={:.1} pipeline_batch={} \
         consumed={} XREADGROUP_PER_SEC={:.1}",
        if fat { "bite-fat" } else { "clean" },
        n,
        payload_bytes,
        ps.n as f64 / pub_elapsed.as_secs_f64(),
        ps.p50_ms,
        ps.p99_ms,
        piped as f64 / pipe_elapsed.as_secs_f64(),
        PIPELINE_BATCH,
        consumed,
        consumed as f64 / con_elapsed.as_secs_f64()
    );
}

// ──────────────────────────────────  main  ──────────────────────────────────

#[tokio::main]
async fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let flag = |name: &str| args.iter().any(|a| a == name);
    let num = |i: usize, d: usize| -> usize {
        args.get(i).and_then(|s| s.parse().ok()).unwrap_or(d)
    };

    match args.first().map(String::as_str) {
        Some("c1") => c1(num(1, 300), flag("--bite-sync-off")).await,
        Some("c2") => c2(num(1, 8), num(2, 100), flag("--bite-pool1")).await,
        Some("c3") => c3(num(1, 5_000), flag("--bite-fat")).await,
        Some("env") => {
            let pool = connect(&pg_url(), 1, false).await;
            let e = capture_pg_env(&pool).await;
            print_env(&e, 1);
        }
        other => {
            eprintln!("unknown mode {other:?} — use c1 | c2 | c3 | env");
            std::process::exit(2);
        }
    }
}
