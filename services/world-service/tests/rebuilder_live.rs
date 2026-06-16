//! 142 (D-REBUILD-LIVE-SMOKE) — the round-trip proof for the 073 `rebuilder`
//! bin (the FIRST live projection-apply path).
//!
//! Mirrors the admin-cli freeze→**TRUNCATE**→exec→thaw flow: for each case we
//! TRUNCATE the target projection table (the admin-cli `Truncator` step), seed a
//! per-reality `events` log, run the COMPILED `rebuilder` bin as a subprocess
//! (the exact path `commands.NewSubprocessRebuildInvoker` execs), then assert the
//! emitted `RebuildStats` AND that the table now holds exactly the rebuilt rows.
//!
//! Validates what no unit test can: the `ParallelRebuilder` + `SqlxEventSource` +
//! `SqlxProjectionWriter` chain applying real events into real tables end-to-end.
//! Case B (`npc_session_memory_projection`) specifically proves the 147
//! writer-Insert fix in the REBUILDER (not just the replay bin): `session.started`
//! omits the NOT NULL `summary`/`facts` columns, which the old `SELECT *` writer
//! would have failed on.
//!
//! Gated by `LOREWEAVE_TEST_PG_URL` (a per-reality DB that gets `0002`+`0006`
//! applied — `0002` DROPs+recreates `events`, so point this at a DISPOSABLE DB,
//! and run this test binary on its OWN DB: it TRUNCATEs projection tables + drops
//! `events`, so it must not race another live test on the same DB). Unset →
//! prints a skip line and returns green. See
//! `docs/plans/2026-06-03-073-destructive-admin-commands.md` + DEFERRED 142.

use std::process::Command;

use serde_json::{Value, json};
use sqlx::Row;
use sqlx::postgres::{PgPool, PgPoolOptions};
use tokio::runtime::Runtime;
use uuid::Uuid;

// ─── Helpers ───────────────────────────────────────────────────────────────

fn migration(rel: &str) -> String {
    let root = concat!(env!("CARGO_MANIFEST_DIR"), "/../..");
    let path = format!("{root}/{rel}");
    std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("read migration {path}: {e}"))
}

async fn apply(pool: &PgPool, rel: &str) {
    sqlx::raw_sql(&migration(rel))
        .execute(pool)
        .await
        .unwrap_or_else(|e| panic!("apply {rel}: {e}"));
}

/// INSERT one event. `recorded_at` (partition key + per-aggregate replay order)
/// is `date_trunc('month', now()) + idx s` so every row lands in the single
/// current-month partition `0002` creates and version order tracks `idx`.
#[allow(clippy::too_many_arguments)]
async fn seed(
    pool: &PgPool,
    idx: i32,
    reality_id: Uuid,
    event_id: Uuid,
    aggregate_type: &str,
    aggregate_id: &str,
    aggregate_version: i64,
    event_type: &str,
    occurred_at: &str,
    payload: Value,
) {
    sqlx::query(
        "INSERT INTO events \
             (event_id, reality_id, aggregate_type, aggregate_id, aggregate_version, \
              event_type, event_version, payload, occurred_at, recorded_at) \
         VALUES ($1, $2, $3, $4, $5, $6, 1, $7, $8::timestamptz, \
                 date_trunc('month', now()) + ($9 * interval '1 second'))",
    )
    .bind(event_id)
    .bind(reality_id)
    .bind(aggregate_type)
    .bind(aggregate_id)
    .bind(aggregate_version)
    .bind(event_type)
    .bind(&payload)
    .bind(occurred_at)
    .bind(idx)
    .execute(pool)
    .await
    .unwrap_or_else(|e| panic!("seed event {event_id} ({event_type}): {e}"));
}

/// Run the compiled `rebuilder` bin and return its parsed `RebuildStats` JSON.
fn run_rebuilder(db_url: &str, reality_id: Uuid, projection: &str) -> Value {
    let out = Command::new(env!("CARGO_BIN_EXE_rebuilder"))
        .env("REALITY_DB_URL", db_url)
        .args(["--reality-id", &reality_id.to_string()])
        .args(["--projection", projection])
        .output()
        .expect("spawn rebuilder bin");
    assert!(
        out.status.success(),
        "rebuilder exited {:?}\nstderr: {}",
        out.status.code(),
        String::from_utf8_lossy(&out.stderr)
    );
    let stdout = String::from_utf8(out.stdout).expect("utf8 stdout");
    serde_json::from_str(&stdout)
        .unwrap_or_else(|e| panic!("parse rebuilder stdout {stdout:?}: {e}"))
}

async fn count(pool: &PgPool, table: &str) -> i64 {
    sqlx::query(&format!("SELECT count(*) AS c FROM {table}"))
        .fetch_one(pool)
        .await
        .expect("count query")
        .get::<i64, _>("c")
}

// ─── The rebuild round-trip test ─────────────────────────────────────────────

#[test]
fn rebuilder_round_trip_live_smoke() {
    let Ok(db_url) = std::env::var("LOREWEAVE_TEST_PG_URL") else {
        eprintln!("SKIP rebuilder_live: set LOREWEAVE_TEST_PG_URL to run");
        return;
    };

    let rt = Runtime::new().expect("tokio runtime");
    let pool = rt
        .block_on(PgPoolOptions::new().max_connections(5).connect(&db_url))
        .expect("connect test DB");

    rt.block_on(apply(
        &pool,
        "contracts/migrations/per_reality/0002_events_table.up.sql",
    ));
    rt.block_on(apply(
        &pool,
        "contracts/migrations/per_reality/0006_projections.up.sql",
    ));

    // ══ Case A — pc, single-aggregate, TRUNCATE→rebuild ══════════════════════
    let reality_a = Uuid::new_v4();
    let pc_id = Uuid::new_v4();
    let user_id = Uuid::new_v4();
    let region_1 = Uuid::new_v4();
    let region_2 = Uuid::new_v4();
    rt.block_on(async {
        // The admin-cli `Truncator` step the bin assumes ran.
        sqlx::query("TRUNCATE pc_projection")
            .execute(&pool)
            .await
            .expect("truncate pc_projection");
        seed(
            &pool,
            0,
            reality_a,
            Uuid::new_v4(),
            "pc",
            &pc_id.to_string(),
            1,
            "pc.spawned",
            "2026-06-15T12:00:00Z",
            json!({
                "user_id": user_id.to_string(), "name": "Aria",
                "spawn_region_id": region_1.to_string(), "stats": { "hp": 100 },
            }),
        )
        .await;
        seed(
            &pool,
            1,
            reality_a,
            Uuid::new_v4(),
            "pc",
            &pc_id.to_string(),
            2,
            "pc.moved",
            "2026-06-15T12:05:00Z",
            json!({ "to_region_id": region_2.to_string() }),
        )
        .await;
    });

    let stats = run_rebuilder(&db_url, reality_a, "pc_projection");
    assert_eq!(
        stats["aggregates_failed"], 0,
        "pc rebuild had no failed aggregates: {stats}"
    );
    assert_eq!(
        stats["aggregates_rebuilt"], 1,
        "pc reality has exactly 1 aggregate: {stats}"
    );
    assert_eq!(
        stats["events_replayed"], 2,
        "pc rebuild replayed both events: {stats}"
    );

    rt.block_on(async {
        assert_eq!(
            count(&pool, "pc_projection").await,
            1,
            "exactly one rebuilt pc row"
        );
        let row = sqlx::query(
            "SELECT current_region_id, last_event_version, name, status, user_id, stats \
               FROM pc_projection WHERE pc_id = $1",
        )
        .bind(pc_id)
        .fetch_one(&pool)
        .await
        .expect("rebuilt pc row exists");
        assert_eq!(
            row.get::<Uuid, _>("current_region_id"),
            region_2,
            "pc.moved applied"
        );
        assert_eq!(row.get::<i64, _>("last_event_version"), 2);
        assert_eq!(row.get::<String, _>("name"), "Aria");
        assert_eq!(row.get::<String, _>("status"), "active");
        assert_eq!(row.get::<Uuid, _>("user_id"), user_id);
        assert_eq!(row.get::<Value, _>("stats"), json!({ "hp": 100 }));
    });

    // ══ Case B — npc_session_memory_projection, TRUNCATE→rebuild ═════════════
    // Proves the 147 writer-Insert fix in the REBUILDER: session.started omits
    // NOT NULL summary/facts → the old `SELECT *` writer would NULL-violate.
    let reality_b = Uuid::new_v4();
    let npc_id = Uuid::new_v4();
    let session_id = Uuid::new_v4();
    let synthetic_agg = Uuid::new_v4();
    rt.block_on(async {
        sqlx::query("TRUNCATE npc_session_memory_projection")
            .execute(&pool)
            .await
            .expect("truncate npc_session_memory_projection");
        seed(
            &pool,
            0,
            reality_b,
            Uuid::new_v4(),
            "session",
            &session_id.to_string(),
            1,
            "session.started",
            "2026-06-15T14:00:00Z",
            json!({
                "npc_id": npc_id.to_string(), "session_id": session_id.to_string(),
                "aggregate_id": synthetic_agg.to_string(),
            }),
        )
        .await;
        seed(
            &pool,
            1,
            reality_b,
            Uuid::new_v4(),
            "session",
            &session_id.to_string(),
            2,
            "session.ended",
            "2026-06-15T14:30:00Z",
            json!({ "npc_id": npc_id.to_string(), "session_id": session_id.to_string() }),
        )
        .await;
    });

    let stats_b = run_rebuilder(&db_url, reality_b, "npc_session_memory_projection");
    assert_eq!(
        stats_b["aggregates_failed"], 0,
        "session rebuild had no failed aggregates: {stats_b}"
    );
    assert_eq!(
        stats_b["aggregates_rebuilt"], 1,
        "session reality has exactly 1 aggregate: {stats_b}"
    );
    assert_eq!(
        stats_b["events_replayed"], 2,
        "session rebuild replayed both events: {stats_b}"
    );

    rt.block_on(async {
        assert_eq!(
            count(&pool, "npc_session_memory_projection").await,
            1,
            "exactly one rebuilt session row"
        );
        let row = sqlx::query(
            "SELECT archive_status, summary, facts, interaction_count, \
                    session_ended_at IS NOT NULL AS ended \
               FROM npc_session_memory_projection WHERE npc_id = $1 AND session_id = $2",
        )
        .bind(npc_id)
        .bind(session_id)
        .fetch_one(&pool)
        .await
        .expect("rebuilt session row exists");
        // session.ended Update applied on top of session.started Insert.
        assert_eq!(row.get::<String, _>("archive_status"), "faded");
        assert!(
            row.get::<bool, _>("ended"),
            "session_ended_at set by session.ended"
        );
        // The writer-fix payoff: omitted NOT NULL cols took their schema DEFAULT.
        assert_eq!(
            row.get::<String, _>("summary"),
            "",
            "summary took its '' DEFAULT"
        );
        assert_eq!(
            row.get::<Value, _>("facts"),
            json!({}),
            "facts took its {{}} DEFAULT"
        );
        assert_eq!(row.get::<i32, _>("interaction_count"), 0);
    });

    // ══ Case C — MULTI-aggregate, exercises the ParallelRebuilder concurrency ══
    // The default RebuildConfig has parallel_workers=8, so a reality with >1
    // aggregate replays them CONCURRENTLY (spawn_blocking workers each re-entering
    // db_rt via Handle::block_on + each acquiring a pool connection + all writing
    // the SAME target table). Cases A/B had one aggregate each → that path never
    // ran. A real catastrophic-rebuild (now first-class after 141) hits it on any
    // many-aggregate reality, so smoke it: two pc aggregates → rebuilt=2, 2 rows.
    let reality_c = Uuid::new_v4();
    let pc_a = Uuid::new_v4();
    let pc_b = Uuid::new_v4();
    let region = Uuid::new_v4();
    rt.block_on(async {
        sqlx::query("TRUNCATE pc_projection")
            .execute(&pool)
            .await
            .expect("truncate pc_projection (case C)");
        for (i, pc) in [pc_a, pc_b].iter().enumerate() {
            seed(
                &pool,
                i as i32,
                reality_c,
                Uuid::new_v4(),
                "pc",
                &pc.to_string(),
                1,
                "pc.spawned",
                "2026-06-15T16:00:00Z",
                json!({
                    "user_id": Uuid::new_v4().to_string(),
                    "name": format!("PC-{i}"),
                    "spawn_region_id": region.to_string(),
                    "stats": {},
                }),
            )
            .await;
        }
    });

    let stats_c = run_rebuilder(&db_url, reality_c, "pc_projection");
    assert_eq!(
        stats_c["aggregates_failed"], 0,
        "multi-aggregate rebuild had no failed aggregates: {stats_c}"
    );
    assert_eq!(
        stats_c["aggregates_rebuilt"], 2,
        "both pc aggregates rebuilt concurrently: {stats_c}"
    );
    assert_eq!(
        stats_c["events_replayed"], 2,
        "one pc.spawned per aggregate: {stats_c}"
    );

    rt.block_on(async {
        assert_eq!(
            count(&pool, "pc_projection").await,
            2,
            "both rebuilt pc rows present"
        );
        for pc in [pc_a, pc_b] {
            let region_id: Uuid =
                sqlx::query_scalar("SELECT current_region_id FROM pc_projection WHERE pc_id = $1")
                    .bind(pc)
                    .fetch_one(&pool)
                    .await
                    .unwrap_or_else(|e| panic!("rebuilt pc row {pc} missing: {e}"));
            assert_eq!(region_id, region, "pc {pc} spawn region applied");
        }
    });
}
