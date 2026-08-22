//! `FLOW-19`'s owed half, PROVEN rather than promised.
//!
//! WHAT WAS OWED, AND WHY A SENTENCE WAS NOT ENOUGH
//! -----------------------------------------------
//! `0027_channel_writer_state_fk` adds the foreign key `FLOW-19` had wanted
//! since `1b.9`, and adds it `NOT VALID` — a choice made on a measurement, not
//! on caution: `dp_kernel_test` holds **456 writer-state rows of which 313 are
//! ORPHANS**, both dp-kernel smoke databases are 100 % orphans, and the two live
//! realities are clean. A strict `ADD CONSTRAINT` would refuse to migrate any
//! database that has ever acquired a lease.
//!
//! So the migration left one thing owed: **`VALIDATE CONSTRAINT`, once the
//! historical rows are reconciled.** That was recorded as a deferral with a
//! trigger — and a deferral whose DISCHARGE PROCEDURE has never been run is a
//! promise, not a plan. Three things nobody had checked:
//!
//!   1. does `VALIDATE CONSTRAINT` actually FAIL while an orphan is present, or
//!      does `NOT VALID` make it permanently unvalidatable?
//!   2. does deleting the orphans make it succeed?
//!   3. is the constraint still a RATCHET afterwards — does it still refuse a
//!      NEW orphan once validated?
//!
//! This test answers all three against a real database. **The first is the
//! bite**: a validation that could not fail would make the whole owed item
//! meaningless, because it would "pass" with the defect still present.
//!
//! Gated by `LOREWEAVE_TEST_PG_ADMIN_URL`. Creates and DROPs its own throwaway
//! database whose name carries a `test` marker, per CLAUDE.md's destructive-ops
//! rule. Unset => skipped.

use std::path::PathBuf;

fn admin_dsn() -> Option<String> {
    std::env::var("LOREWEAVE_TEST_PG_ADMIN_URL").ok().filter(|s| !s.is_empty())
}

fn migrations_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../contracts/migrations/per_reality")
}

/// The minimum chain `channel_writer_state` + `channels` + the key need.
const NEEDED: [&str; 5] = [
    "0001_initial",
    "0002_events_table",
    "0014_channel_ordering",
    "0019_channels",
    "0027_channel_writer_state_fk",
];

const CONSTRAINT: &str = "channel_writer_state_channel_fk";

async fn run(pool: &sqlx::PgPool) -> Result<(), String> {
    use sqlx::Executor;

    for id in NEEDED {
        let p = migrations_dir().join(format!("{id}.up.sql"));
        let sql = std::fs::read_to_string(&p).map_err(|e| format!("read {}: {e}", p.display()))?;
        pool.execute(sql.as_str()).await.map_err(|e| format!("{id}: {e}"))?;
    }

    let reality = uuid::Uuid::new_v4();

    // A HISTORICAL orphan — writer state for a channel that does not exist.
    // This is what 313 rows in `dp_kernel_test` look like, and `NOT VALID` is
    // exactly what lets it be inserted after the key exists... no: it lets it
    // SURVIVE. Inserting it now would be refused, so it goes in with the
    // constraint dropped, which is the historical situation reproduced.
    sqlx::query(&format!("ALTER TABLE channel_writer_state DROP CONSTRAINT {CONSTRAINT}"))
        .execute(pool)
        .await
        .map_err(|e| format!("drop for setup: {e}"))?;
    sqlx::query("INSERT INTO channel_writer_state (reality_id, channel_id) VALUES ($1, 777)")
        .bind(reality)
        .execute(pool)
        .await
        .map_err(|e| format!("seed orphan: {e}"))?;
    sqlx::query(&format!(
        "ALTER TABLE channel_writer_state ADD CONSTRAINT {CONSTRAINT} \
         FOREIGN KEY (reality_id, channel_id) REFERENCES channels (reality_id, id) NOT VALID"
    ))
    .execute(pool)
    .await
    .map_err(|e| format!("re-add NOT VALID: {e}"))?;

    // ── 1. THE BITE. Validation MUST fail while the orphan is present. A
    //       validation that passed here would make the owed item meaningless.
    let attempt = sqlx::query(&format!(
        "ALTER TABLE channel_writer_state VALIDATE CONSTRAINT {CONSTRAINT}"
    ))
    .execute(pool)
    .await;
    if attempt.is_ok() {
        return Err(format!(
            "VALIDATE CONSTRAINT SUCCEEDED with an orphan present — the owed \
             discharge would certify a database that still holds the defect"
        ));
    }

    // ── 2. Reconciliation: the orphans go. This is the operational step the
    //       deferral names, executed rather than described.
    let removed = sqlx::query(
        "DELETE FROM channel_writer_state w WHERE NOT EXISTS ( \
           SELECT 1 FROM channels c \
            WHERE c.reality_id = w.reality_id AND c.id = w.channel_id)",
    )
    .execute(pool)
    .await
    .map_err(|e| format!("reconcile: {e}"))?;
    if removed.rows_affected() != 1 {
        return Err(format!("reconciliation removed {} rows, wanted 1", removed.rows_affected()));
    }

    // ── 3. Now it validates.
    sqlx::query(&format!(
        "ALTER TABLE channel_writer_state VALIDATE CONSTRAINT {CONSTRAINT}"
    ))
    .execute(pool)
    .await
    .map_err(|e| format!("VALIDATE after reconciliation still failed: {e}"))?;

    // ── 4. And it is STILL A RATCHET. Validation must not relax anything: a new
    //       orphan is refused exactly as it was before.
    sqlx::query("INSERT INTO channel_writer_state (reality_id, channel_id) VALUES ($1, 888)")
        .bind(reality)
        .execute(pool)
        .await
        .err()
        .ok_or("a NEW orphan was ACCEPTED after validation — the key stopped ratcheting")?;

    // ── 5. …and a lease on a channel that exists still works, so the ratchet is
    //       not simply refusing everything.
    sqlx::query(
        "INSERT INTO channels (reality_id, id, parent, level_name, depth, lifecycle) \
         VALUES ($1, 1, NULL, 'thien-gioi', 0, 'active')",
    )
    .bind(reality)
    .execute(pool)
    .await
    .map_err(|e| format!("create channel: {e}"))?;
    sqlx::query("INSERT INTO channel_writer_state (reality_id, channel_id) VALUES ($1, 1)")
        .bind(reality)
        .execute(pool)
        .await
        .map_err(|e| format!("a legitimate lease was refused after validation: {e}"))?;

    Ok(())
}

#[tokio::test]
async fn flow_19_validate_constraint_discharge_path_works() {
    let Some(admin) = admin_dsn() else {
        eprintln!(
            "SKIP: LOREWEAVE_TEST_PG_ADMIN_URL unset -- this suite did NOTHING. \n             A silent skip reads as a pass, which is how a green run once certified \n             an empty one."
        );
        return;
    };
    let db = format!("ws_flow19_{}_test", std::process::id());
    let admin_pool = sqlx::PgPool::connect(&admin).await.expect("admin connect");
    let _ = sqlx::query(&format!("DROP DATABASE IF EXISTS {db}")).execute(&admin_pool).await;
    sqlx::query(&format!("CREATE DATABASE {db}"))
        .execute(&admin_pool)
        .await
        .expect("create throwaway db");

    let dsn = {
        let base = admin.rsplit_once('/').expect("dsn has a database segment").0;
        format!("{base}/{db}")
    };
    let outcome = match sqlx::PgPool::connect(&dsn).await {
        Ok(pool) => {
            let r = run(&pool).await;
            pool.close().await;
            r
        }
        Err(e) => Err(format!("connect: {e}")),
    };

    // UNCONDITIONAL, on the failing path too.
    let _ = sqlx::query(&format!("DROP DATABASE IF EXISTS {db} WITH (FORCE)"))
        .execute(&admin_pool)
        .await;
    admin_pool.close().await;

    if let Err(e) = outcome {
        panic!("{e}");
    }
}
