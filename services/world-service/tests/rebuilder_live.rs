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
//! Case B (`session_participants`) specifically proves the 147 writer-Insert fix
//! in the REBUILDER (not just the replay bin): `session.participant_joined` omits
//! the NOT NULL `applied_at` column, which the old `SELECT *` writer would have
//! written as an explicit NULL and failed on.
//!
//! **Retargeted 2026-08-05.** All three cases ran against `pc_projection` /
//! `npc_session_memory_projection` until `0017` dropped those tables and deleted
//! their projector crates. This smoke was then MEASURABLY BROKEN, not merely
//! stale -- the bin exits 2 with `unknown projection table "pc_projection"` -- and
//! nobody saw it because the gate is an env var. Not one of the properties here
//! was ever about pc or npc, so the fixtures moved and the assertions did not.
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
    let region_id = Uuid::new_v4();
    rt.block_on(async {
        // The admin-cli `Truncator` step the bin assumes ran.
        sqlx::query("TRUNCATE region_projection")
            .execute(&pool)
            .await
            .expect("truncate region_projection");
        seed(
            &pool,
            0,
            reality_a,
            Uuid::new_v4(),
            "region",
            &region_id.to_string(),
            1,
            "region.created",
            "2026-06-15T12:00:00Z",
            json!({
                "code": "azure-vault", "display_name": "The Azure Vault",
                "ambient_state": { "light": "dim" },
            }),
        )
        .await;
        seed(
            &pool,
            1,
            reality_a,
            Uuid::new_v4(),
            "region",
            &region_id.to_string(),
            2,
            "region.ambient_changed",
            "2026-06-15T12:05:00Z",
            json!({ "ambient_state": { "light": "blazing" } }),
        )
        .await;
    });

    let stats = run_rebuilder(&db_url, reality_a, "region_projection");
    assert_eq!(
        stats["aggregates_failed"], 0,
        "region rebuild had no failed aggregates: {stats}"
    );
    assert_eq!(
        stats["aggregates_rebuilt"], 1,
        "region reality has exactly 1 aggregate: {stats}"
    );
    assert_eq!(
        stats["events_replayed"], 2,
        "region rebuild replayed both events: {stats}"
    );

    rt.block_on(async {
        assert_eq!(
            count(&pool, "region_projection").await,
            1,
            "exactly one rebuilt region row"
        );
        let row = sqlx::query(
            "SELECT ambient_state, last_event_version, code, display_name, \
                    description, exits, floor_items \
               FROM region_projection WHERE region_id = $1",
        )
        .bind(region_id)
        .fetch_one(&pool)
        .await
        .expect("rebuilt region row exists");
        assert_eq!(
            row.get::<Value, _>("ambient_state"),
            json!({ "light": "blazing" }),
            "region.ambient_changed applied ON TOP of region.created"
        );
        assert_eq!(row.get::<i64, _>("last_event_version"), 2);
        assert_eq!(row.get::<String, _>("code"), "azure-vault");
        assert_eq!(row.get::<String, _>("display_name"), "The Azure Vault");
        // Absent from the event payload -> the projector's own fallbacks.
        assert_eq!(row.get::<String, _>("description"), "");
        assert_eq!(row.get::<Value, _>("exits"), json!([]));
        assert_eq!(row.get::<Value, _>("floor_items"), json!([]));
    });

    // ══ Case B — session_participants, TRUNCATE→rebuild ══════════════════════
    // Proves the 147 writer-Insert fix in the REBUILDER. The projector's Insert
    // row OMITS `applied_at`, which is `TIMESTAMPTZ NOT NULL DEFAULT NOW()`; the
    // old `SELECT *` writer turned every absent key into an explicit NULL and so
    // violated the NOT NULL. The defect is the same one Case B always tested —
    // only the omitted column changed when the fixture moved off npc vocabulary.
    let reality_b = Uuid::new_v4();
    let session_id = Uuid::new_v4();
    let participant_id = Uuid::new_v4();
    rt.block_on(async {
        sqlx::query("TRUNCATE session_participants")
            .execute(&pool)
            .await
            .expect("truncate session_participants");
        seed(
            &pool,
            0,
            reality_b,
            Uuid::new_v4(),
            "session",
            &session_id.to_string(),
            1,
            "session.participant_joined",
            "2026-06-15T14:00:00Z",
            json!({
                "session_id": session_id.to_string(),
                // 'pc'/'npc' is what session_participants_type_valid still allows.
                // That CHECK is game vocabulary in an engine table — the same shape
                // `0017` removed elsewhere — and changing it is a schema decision,
                // not a test fixture's to make. Noted rather than quietly worked around.
                "participant_type": "pc",
                "participant_id": participant_id.to_string(),
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
            "session.participant_left",
            "2026-06-15T14:30:00Z",
            json!({
                "session_id": session_id.to_string(),
                "participant_type": "pc",
                "participant_id": participant_id.to_string(),
            }),
        )
        .await;
    });

    let stats_b = run_rebuilder(&db_url, reality_b, "session_participants");
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
            count(&pool, "session_participants").await,
            1,
            "exactly one rebuilt participant row"
        );
        let row = sqlx::query(
            "SELECT reality_id, left_at IS NOT NULL AS has_left, \
                    applied_at IS NOT NULL AS applied_defaulted \
               FROM session_participants \
              WHERE session_id = $1 AND participant_id = $2",
        )
        .bind(session_id)
        .bind(participant_id)
        .fetch_one(&pool)
        .await
        .expect("rebuilt participant row exists");
        // The _left Update applied on top of the _joined Insert.
        assert!(
            row.get::<bool, _>("has_left"),
            "left_at set by session.participant_left"
        );
        assert_eq!(row.get::<Uuid, _>("reality_id"), reality_b);
        // The writer-fix payoff: a column ABSENT from the Insert row took its
        // schema DEFAULT instead of an explicit NULL that NOT NULL would reject.
        assert!(
            row.get::<bool, _>("applied_defaulted"),
            "applied_at took its NOW() DEFAULT — the 147 writer-Insert fix"
        );
    });

    // ══ Case C — MULTI-aggregate, exercises the ParallelRebuilder concurrency ══
    // The default RebuildConfig has parallel_workers=8, so a reality with >1
    // aggregate replays them CONCURRENTLY (spawn_blocking workers each re-entering
    // db_rt via Handle::block_on + each acquiring a pool connection + all writing
    // the SAME target table). Cases A/B had one aggregate each → that path never
    // ran. A real catastrophic-rebuild (now first-class after 141) hits it on any
    // many-aggregate reality, so smoke it: two region aggregates → rebuilt=2, 2 rows.
    let reality_c = Uuid::new_v4();
    let region_a = Uuid::new_v4();
    let region_b = Uuid::new_v4();
    rt.block_on(async {
        sqlx::query("TRUNCATE region_projection")
            .execute(&pool)
            .await
            .expect("truncate region_projection (case C)");
        for (i, r) in [region_a, region_b].iter().enumerate() {
            seed(
                &pool,
                i as i32,
                reality_c,
                Uuid::new_v4(),
                "region",
                &r.to_string(),
                1,
                "region.created",
                "2026-06-15T16:00:00Z",
                json!({
                    "code": format!("region-{i}"),
                    "display_name": format!("Region {i}"),
                }),
            )
            .await;
        }
    });

    let stats_c = run_rebuilder(&db_url, reality_c, "region_projection");
    assert_eq!(
        stats_c["aggregates_failed"], 0,
        "multi-aggregate rebuild had no failed aggregates: {stats_c}"
    );
    assert_eq!(
        stats_c["aggregates_rebuilt"], 2,
        "both region aggregates rebuilt concurrently: {stats_c}"
    );
    assert_eq!(
        stats_c["events_replayed"], 2,
        "one region.created per aggregate: {stats_c}"
    );

    rt.block_on(async {
        assert_eq!(
            count(&pool, "region_projection").await,
            2,
            "both rebuilt region rows present"
        );
        for (i, r) in [region_a, region_b].iter().enumerate() {
            let code: String =
                sqlx::query_scalar("SELECT code FROM region_projection WHERE region_id = $1")
                    .bind(r)
                    .fetch_one(&pool)
                    .await
                    .unwrap_or_else(|e| panic!("rebuilt region row {r} missing: {e}"));
            assert_eq!(code, format!("region-{i}"), "region {r} payload applied");
        }
    });
}
