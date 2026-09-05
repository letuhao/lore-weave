//! `1b14-01` — the provisioner's re-entry path, against a real database.
//!
//! WHY THIS EXISTS, AND WHY A UNIT TEST COULD NOT HAVE CAUGHT IT
//! ------------------------------------------------------------
//! `provisioner.rs` documents steps 4-8 as re-drivable: *"a partial prior run
//! that crashed between e.g. step 5 and step 6 can be re-driven to completion."*
//! `provisioner::tests::idempotent_reentry_skips_completed_steps` asserts it and
//! is green — against `FakeEffects::apply_migrations`, which is a
//! `HashSet::insert`. **The mock had the property and the live code did not.**
//!
//! When `1b12-05` made the provisioner apply the whole manifest instead of just
//! `0001_initial`, it applied it UNCONDITIONALLY. That is a whole-history replay,
//! and this repo had already written down that whole-history replay fails —
//! `scripts/dp-migration-chain-smoke.py`'s docstring separates it from
//! per-migration retry-safety by name. Measured: the second pass dies at
//! `0001_initial` with *"there is no unique constraint matching given keys for
//! referenced table events"*, because a later migration changed that key. So a
//! reality that crashed mid-provision could never be completed — every retry
//! failed at migration 1 — until the orphan scanner collected it.
//!
//! This test drives `apply_pending` itself, not a re-implementation of it. A
//! second re-implementation inside a test would repeat the exact mistake above.
//!
//! Gated by `LOREWEAVE_TEST_PG_ADMIN_URL` (a maintenance DSN, e.g. `.../postgres`)
//! — the test CREATEs and DROPs its own throwaway database, whose name carries a
//! `test` marker per CLAUDE.md's destructive-ops rule. Unset → skipped.

use std::path::PathBuf;

fn admin_dsn() -> Option<String> {
    std::env::var("LOREWEAVE_TEST_PG_ADMIN_URL").ok().filter(|s| !s.is_empty())
}

fn migrations_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../contracts/migrations/per_reality")
}

fn manifest_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../contracts/migrations/manifest.yaml")
}

/// The ordered `(id, sql)` pairs the provisioner would apply.
fn shipped_migrations() -> Vec<(String, String)> {
    let text = std::fs::read_to_string(manifest_path()).expect("manifest");
    let mut out = Vec::new();
    for line in text.lines().map(str::trim) {
        if line.starts_with('#') {
            continue;
        }
        if let Some(rest) = line.strip_prefix("- id:") {
            if let Some((id, _)) = rest.trim().trim_start_matches('"').split_once('"') {
                let p = migrations_dir().join(format!("{id}.up.sql"));
                let sql = std::fs::read_to_string(&p)
                    .unwrap_or_else(|e| panic!("read {}: {e}", p.display()));
                out.push((id.to_string(), sql));
            }
        }
    }
    out
}

/// The body, returning failures instead of panicking.
///
/// Written this way so the DROP below is UNCONDITIONAL. Found the honest way:
/// biting this test left `ws_reentry_<pid>_test` behind, because a panic never
/// reaches a cleanup that sits after the `.await`. That is `1b7db-12`'s
/// contamination hazard — a stray database that makes the NEXT run look broken —
/// arriving through the failure path of the test written to prove a fix.
async fn check(dsn: &str) -> Result<(), String> {
    let pool = sqlx::PgPool::connect(dsn).await.map_err(|e| format!("reality connect: {e}"))?;
    let migrations = shipped_migrations();
    let out = run(&pool, &migrations).await;
    pool.close().await;
    out
}

async fn run(pool: &sqlx::PgPool, migrations: &[(String, String)]) -> Result<(), String> {
    if migrations.len() < 10 {
        return Err(format!("expected the shipped manifest, got {}", migrations.len()));
    }

    // Pass 1 — a fresh reality applies everything.
    let first = world_service::provisioner_live::apply_pending(pool, migrations)
        .await
        .map_err(|e| format!("first pass must apply cleanly: {e:?}"))?;
    if first != migrations.len() {
        return Err(format!("a fresh reality must apply every migration: {first}"));
    }

    // Pass 2 — THE REGRESSION. Before the ledger this errored at `0001_initial`;
    // the contract is that it is a no-op.
    let second = world_service::provisioner_live::apply_pending(pool, migrations)
        .await
        .map_err(|e| format!("re-entry must not error — this is 1b14-01: {e:?}"))?;
    if second != 0 {
        return Err(format!("a completed reality must re-provision to a no-op: {second}"));
    }

    // NON-VACUITY: the pass above would also read `0` if the loop silently did
    // nothing. Forget ONE migration and exactly that one must re-apply, which
    // proves the ledger is CONSULTED rather than merely written.
    let victim = &migrations.last().expect("at least one migration").0;
    sqlx::query("DELETE FROM schema_migrations WHERE id = $1")
        .bind(victim)
        .execute(pool)
        .await
        .map_err(|e| format!("forget one: {e}"))?;
    let third = world_service::provisioner_live::apply_pending(pool, migrations)
        .await
        .map_err(|e| format!("re-applying one migration is the retry-safe operation: {e:?}"))?;
    if third != 1 {
        return Err(format!("exactly the forgotten migration must re-apply, got {third}"));
    }
    Ok(())
}

#[tokio::test]
async fn a_completed_reality_re_provisions_to_a_no_op() {
    let Some(admin) = admin_dsn() else {
        eprintln!("skipped: LOREWEAVE_TEST_PG_ADMIN_URL unset");
        return;
    };
    let db = format!("ws_reentry_{}_test", std::process::id());
    assert!(db.contains("test"), "throwaway marker required before CREATE/DROP");

    let admin_pool = sqlx::PgPool::connect(&admin).await.expect("admin connect");
    let _ = sqlx::raw_sql(&format!("DROP DATABASE IF EXISTS {db} WITH (FORCE)"))
        .execute(&admin_pool)
        .await;
    sqlx::raw_sql(&format!("CREATE DATABASE {db}")).execute(&admin_pool).await.expect("create db");

    let dsn = {
        let base = admin.rsplit_once('/').expect("dsn has a database segment").0;
        format!("{base}/{db}")
    };

    let result = check(&dsn).await;

    let _ = sqlx::raw_sql(&format!("DROP DATABASE IF EXISTS {db} WITH (FORCE)"))
        .execute(&admin_pool)
        .await;
    admin_pool.close().await;

    if let Err(why) = result {
        panic!("{why}");
    }
}
