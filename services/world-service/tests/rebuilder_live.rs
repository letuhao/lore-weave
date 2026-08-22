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
//! Case B specifically proves the 147 writer-Insert fix in the REBUILDER (not just
//! the replay bin): the projector's Insert row omits the NOT NULL `applied_at`
//! column, which the old `SELECT *` writer would have written as an explicit NULL
//! and failed on.
//!
//! **Retargeted twice on 2026-08-05, and the second move is the one that matters.**
//! These cases ran against `pc_projection` until `0017`, which left them MEASURABLY
//! BROKEN (`unknown projection table "pc_projection"`, exit 2) with nobody to see
//! it, because the gate is an env var. They were moved to `region_projection` /
//! `session_participants` — and then the orphan gate learned to read `#[cfg(test)]`
//! modules, which showed those two had no producer either. `0018` removed them, and
//! the fixtures landed on `canon_projection`: the only projection anything writes.
//! Not one property here was ever about the vocabulary, which is why it could move
//! three times without an assertion changing meaning.
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
    // 0009 creates canon_projection — the only projection left after `0018`,
    // and it was never in 0006.
    rt.block_on(apply(
        &pool,
        "contracts/migrations/per_reality/0009_canon_projection.up.sql",
    ));
    // 0016 adds `events.ruleset_digest`, and THE EVENT SOURCE READS IT
    // (`event_source.rs`'s `EVENT_COLUMNS`). Without it every rebuild failed
    // with `event source: events row decode: no column found for name:
    // ruleset_digest` — and the bin printed only `failed=1`, so the reason was
    // invisible until it was made to print.
    //
    // This list is the reason the failure looked environmental for three
    // rounds: it is a HAND-MAINTAINED subset of a growing migration tree, so a
    // migration that adds a column the decoder reads breaks this test and
    // nothing connects the two. `0013` is included for the same class —
    // `content_sha256` is written by the channel path and a future decoder
    // change would need it.
    rt.block_on(apply(
        &pool,
        "contracts/migrations/per_reality/0013_events_content_sha256.up.sql",
    ));
    rt.block_on(apply(
        &pool,
        "contracts/migrations/per_reality/0016_events_ruleset_digest.up.sql",
    ));

    // ══ Case A — pc, single-aggregate, TRUNCATE→rebuild ══════════════════════
    let reality_a = Uuid::new_v4();
    let canon_id = Uuid::new_v4();
    let book_id = Uuid::new_v4();
    rt.block_on(async {
        // The admin-cli `Truncator` step the bin assumes ran.
        sqlx::query("TRUNCATE canon_projection")
            .execute(&pool)
            .await
            .expect("truncate canon_projection");
        seed(
            &pool,
            0,
            reality_a,
            Uuid::new_v4(),
            "canon",
            &canon_id.to_string(),
            1,
            "canon.entry.created",
            "2026-06-15T12:00:00Z",
            json!({
                "canon_entry_id": canon_id.to_string(),
                "book_id": book_id.to_string(),
                "attribute_path": "characters/aria/race",
                "value": "elf",
                "canon_layer": "L2_seeded",
                "lock_level": "soft",
            }),
        )
        .await;
        seed(
            &pool,
            1,
            reality_a,
            Uuid::new_v4(),
            "canon",
            &canon_id.to_string(),
            2,
            "canon.entry.updated",
            "2026-06-15T12:05:00Z",
            json!({
                "canon_entry_id": canon_id.to_string(),
                "new_value": "high elf",
                "canon_layer": "L2_seeded",
            }),
        )
        .await;
    });

    let stats = run_rebuilder(&db_url, reality_a, "canon_projection");
    assert_eq!(
        stats["aggregates_failed"], 0,
        "canon rebuild had no failed aggregates: {stats}"
    );
    assert_eq!(
        stats["aggregates_rebuilt"], 1,
        "canon reality has exactly 1 aggregate: {stats}"
    );
    assert_eq!(
        stats["events_replayed"], 2,
        "canon rebuild replayed both events: {stats}"
    );

    rt.block_on(async {
        assert_eq!(
            count(&pool, "canon_projection").await,
            1,
            "exactly one rebuilt canon row"
        );
        let row = sqlx::query(
            "SELECT value, attribute_path, book_id, canon_layer, lock_level \
               FROM canon_projection WHERE canon_entry_id = $1",
        )
        .bind(canon_id)
        .fetch_one(&pool)
        .await
        .expect("rebuilt canon row exists");
        assert_eq!(
            row.get::<Value, _>("value"),
            json!("high elf"),
            "canon.entry.updated applied ON TOP of canon.entry.created"
        );
        assert_eq!(row.get::<String, _>("attribute_path"), "characters/aria/race");
        assert_eq!(row.get::<Uuid, _>("book_id"), book_id);
        assert_eq!(row.get::<String, _>("canon_layer"), "L2_seeded");
        assert_eq!(row.get::<String, _>("lock_level"), "soft");
    });

    // ══ Case B — the writer-Insert fix, on its own reality ═══════════════════
    // Proves the 147 writer-Insert fix in the REBUILDER. The projector's Insert
    // row OMITS `applied_at`, which is `TIMESTAMPTZ NOT NULL DEFAULT NOW()`; the
    // old `SELECT *` writer turned every absent key into an explicit NULL and so
    // violated the NOT NULL. The defect is the same one Case B always tested; only
    // the omitted column changed as the fixture moved off npc, then off session.
    let reality_b = Uuid::new_v4();
    let canon_b = Uuid::new_v4();
    rt.block_on(async {
        sqlx::query("TRUNCATE canon_projection")
            .execute(&pool)
            .await
            .expect("truncate canon_projection (case B)");
        seed(
            &pool,
            0,
            reality_b,
            Uuid::new_v4(),
            "canon",
            &canon_b.to_string(),
            1,
            "canon.entry.created",
            "2026-06-15T14:00:00Z",
            json!({
                "canon_entry_id": canon_b.to_string(),
                "book_id": Uuid::new_v4().to_string(),
                "attribute_path": "regions/vault/climate",
                "value": "cold",
                "canon_layer": "L2_seeded",
            }),
        )
        .await;
        seed(
            &pool,
            1,
            reality_b,
            Uuid::new_v4(),
            "canon",
            &canon_b.to_string(),
            2,
            "canon.entry.promoted",
            "2026-06-15T14:30:00Z",
            json!({
                "canon_entry_id": canon_b.to_string(),
                // `to_layer`, NOT `canon_layer` — the promoted arm reads a
                // different key from the created arm, and the value must be one
                // the canon_projection_layer_valid CHECK admits.
                "to_layer": "L1_axiom",
            }),
        )
        .await;
    });

    let stats_b = run_rebuilder(&db_url, reality_b, "canon_projection");
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
            count(&pool, "canon_projection").await,
            1,
            "exactly one rebuilt canon row"
        );
        let row = sqlx::query(
            "SELECT canon_layer, applied_at IS NOT NULL AS applied_defaulted \
               FROM canon_projection WHERE canon_entry_id = $1",
        )
        .bind(canon_b)
        .fetch_one(&pool)
        .await
        .expect("rebuilt canon row exists");
        // The promoted Update applied on top of the created Insert.
        assert_eq!(row.get::<String, _>("canon_layer"), "L1_axiom");
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
    // many-aggregate reality, so smoke it: two canon aggregates → rebuilt=2, 2 rows.
    let reality_c = Uuid::new_v4();
    let canon_c1 = Uuid::new_v4();
    let canon_c2 = Uuid::new_v4();
    rt.block_on(async {
        sqlx::query("TRUNCATE canon_projection")
            .execute(&pool)
            .await
            .expect("truncate canon_projection (case C)");
        for (i, c) in [canon_c1, canon_c2].iter().enumerate() {
            seed(
                &pool,
                i as i32,
                reality_c,
                Uuid::new_v4(),
                "canon",
                &c.to_string(),
                1,
                "canon.entry.created",
                "2026-06-15T16:00:00Z",
                json!({
                    "canon_entry_id": c.to_string(),
                    "book_id": Uuid::new_v4().to_string(),
                    "attribute_path": format!("things/t{i}/kind"),
                    "value": format!("kind-{i}"),
                    "canon_layer": "L2_seeded",
                }),
            )
            .await;
        }
    });

    let stats_c = run_rebuilder(&db_url, reality_c, "canon_projection");
    assert_eq!(
        stats_c["aggregates_failed"], 0,
        "multi-aggregate rebuild had no failed aggregates: {stats_c}"
    );
    assert_eq!(
        stats_c["aggregates_rebuilt"], 2,
        "both canon aggregates rebuilt concurrently: {stats_c}"
    );
    assert_eq!(
        stats_c["events_replayed"], 2,
        "one canon.entry.created per aggregate: {stats_c}"
    );

    rt.block_on(async {
        assert_eq!(
            count(&pool, "canon_projection").await,
            2,
            "both rebuilt canon rows present"
        );
        for (i, c) in [canon_c1, canon_c2].iter().enumerate() {
            let path: String = sqlx::query_scalar(
                "SELECT attribute_path FROM canon_projection WHERE canon_entry_id = $1",
            )
            .bind(c)
            .fetch_one(&pool)
            .await
            .unwrap_or_else(|e| panic!("rebuilt canon row {c} missing: {e}"));
            assert_eq!(path, format!("things/t{i}/kind"), "canon {c} payload applied");
        }
    });
}
