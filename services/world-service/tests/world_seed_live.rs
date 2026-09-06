//! `world_seed` against a real database — the world-structure step of bootstrap,
//! and the claim that a REFUSED seed writes nothing.
//!
//! WHY A UNIT TEST COULD NOT HAVE CAUGHT WHAT THIS DOES
//! ---------------------------------------------------
//! `world_seed::validate` is pure and its nine unit tests are green, including
//! under mutation. None of them touches a database, so none of them can prove
//! the two properties that actually matter to an operator:
//!
//!   1. a REJECTED seed leaves the reality EMPTY -- the module's one documented
//!      deviation from `PF_001` §5 is "validate first, write nothing on
//!      rejection", and a pure validator cannot demonstrate the "write nothing"
//!      half at all;
//!   2. a re-run is a no-op -- `ON CONFLICT DO NOTHING` is a claim about the
//!      database's behaviour, not the validator's.
//!
//! It also ends where the whole round was aimed: an actor is sited in a place
//! that was seeded a moment earlier, and the occupancy query answers.
//!
//! Gated by `LOREWEAVE_TEST_PG_ADMIN_URL` (a maintenance DSN, e.g. `.../postgres`).
//! The test CREATEs and DROPs its own throwaway database whose name carries a
//! `test` marker, per CLAUDE.md's destructive-ops rule. Unset => skipped.

use std::path::PathBuf;

use world_service::world_seed::{self, MapKind, NodeDecl, PlaceDecl, SeedError, SeedReject};

fn admin_dsn() -> Option<String> {
    std::env::var("LOREWEAVE_TEST_PG_ADMIN_URL").ok().filter(|s| !s.is_empty())
}

fn migrations_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../contracts/migrations/per_reality")
}

/// Only the migrations this module's tables need. The full chain is
/// `provisioner_reentry_live`'s subject, not this one.
const NEEDED: [&str; 4] = [
    "0019_channels",
    "0024_map_layout",
    "0025_entity_binding",
    "0026_place",
];

fn place(name: &str) -> Option<PlaceDecl> {
    Some(PlaceDecl {
        place_type: "tavern".into(),
        canon_ref: serde_json::json!({ "kind": "BookChapter", "path": "ch4" }),
        name_vi: name.into(),
        name_en: None,
    })
}

fn node(id: i64, parent: Option<i64>, kind: MapKind, p: Option<PlaceDecl>) -> NodeDecl {
    NodeDecl {
        id,
        parent,
        level_name: format!("lvl{id}"),
        kind,
        pos_x: 100,
        pos_y: 200,
        // `SDF-A19` only bounds a `World` under a `Domain`; nothing here is one,
        // so the generator's default applies and this tier does not choose it.
        scale: None,
        place: p,
    }
}

/// A three-node world: World -> Region -> Domain(tavern).
fn legal_world() -> Vec<NodeDecl> {
    vec![
        node(1, None, MapKind::World, None),
        node(2, Some(1), MapKind::Region, None),
        node(3, Some(2), MapKind::Domain, place("Yen Vu Lau")),
    ]
}

/// The body, returning failures rather than panicking, so the DROP below is
/// UNCONDITIONAL -- the same shape `provisioner_reentry_live` had to adopt after
/// a bite left a stray database behind.
async fn check(dsn: &str) -> Result<(), String> {
    let pool = sqlx::PgPool::connect(dsn).await.map_err(|e| format!("connect: {e}"))?;
    let out = run(&pool).await;
    pool.close().await;
    out
}

async fn run(pool: &sqlx::PgPool) -> Result<(), String> {
    for id in NEEDED {
        let p = migrations_dir().join(format!("{id}.up.sql"));
        let sql = std::fs::read_to_string(&p).map_err(|e| format!("read {}: {e}", p.display()))?;
        pool.execute_many_compat(&sql).await.map_err(|e| format!("{id}: {e}"))?;
    }

    let reality = uuid::Uuid::new_v4();

    // ── 1. A REFUSED seed must write NOTHING. This runs FIRST, against a
    //       reality that has never been written, so "nothing" is checkable.
    let mut bad = legal_world();
    bad[2].place = None; // a Domain with no place
    match world_seed::seed_world(pool, reality, &bad).await {
        Err(SeedError::Rejected(SeedReject::MissingPlaceDecl { node: 3 })) => {}
        other => return Err(format!("wanted MissingPlaceDecl{{3}}, got {other:?}")),
    }
    for t in ["channels", "map_layout", "place"] {
        let n: i64 = sqlx::query_scalar(&format!(
            "SELECT count(*) FROM {t} WHERE reality_id = $1"
        ))
        .bind(reality)
        .fetch_one(pool)
        .await
        .map_err(|e| format!("count {t}: {e}"))?;
        if n != 0 {
            return Err(format!(
                "a REJECTED seed wrote {n} row(s) into {t} -- the validate-first \
                 deviation does not hold"
            ));
        }
    }

    // ── 2. A legal world seeds all three tables.
    let rep = world_seed::seed_world(pool, reality, &legal_world())
        .await
        .map_err(|e| format!("legal seed: {e}"))?;
    if (rep.channels_written, rep.layouts_written, rep.places_written) != (3, 3, 1) {
        return Err(format!("wanted 3/3/1 written, got {rep:?}"));
    }

    // The kind actually landed, and on the right node.
    let kind: String = sqlx::query_scalar(
        "SELECT kind FROM map_layout WHERE reality_id = $1 AND channel_id = 3",
    )
    .bind(reality)
    .fetch_one(pool)
    .await
    .map_err(|e| format!("read kind: {e}"))?;
    if kind != "domain" {
        return Err(format!("node 3 kind is {kind:?}, wanted domain"));
    }

    // ── 3. A re-run writes nothing. Idempotency is a database claim.
    let again = world_seed::seed_world(pool, reality, &legal_world())
        .await
        .map_err(|e| format!("re-seed: {e}"))?;
    if (again.channels_written, again.layouts_written, again.places_written) != (0, 0, 0) {
        return Err(format!("re-run was not a no-op: {again:?}"));
    }

    // ── 3b. `A3` — THE AUTHORED DECLARATION, against a real database.
    //
    //     `contracts/world/demo_v1.json` is what `admin reality provision
    //     --world` reads. `world_declarations.rs` proves it VALIDATES; only a
    //     database can prove it SEEDS. The two are different claims: `validate`
    //     is pure and knows nothing about a `CHECK`, a foreign key, or the
    //     `channels_root_single` index.
    let authored: Vec<NodeDecl> = serde_json::from_str(
        &std::fs::read_to_string(
            std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../../contracts/world/demo_v1.json"),
        )
        .map_err(|e| format!("read demo_v1.json: {e}"))?,
    )
    .map_err(|e| format!("demo_v1.json is not a NodeDecl array: {e}"))?;

    let authored_reality = uuid::Uuid::new_v4();
    let rep2 = world_seed::seed_world(pool, authored_reality, &authored)
        .await
        .map_err(|e| format!("seed the AUTHORED world: {e}"))?;
    if rep2.channels_written != authored.len() as u64 {
        return Err(format!(
            "authored world wrote {} channels for {} declared nodes",
            rep2.channels_written,
            authored.len()
        ));
    }
    // Its two places are the point: a Domain without one is refused, so a
    // declaration that seeds proves the 1:1 rule held all the way to the row.
    let placed: i64 = sqlx::query_scalar("SELECT count(*) FROM place WHERE reality_id = $1")
        .bind(authored_reality)
        .fetch_one(pool)
        .await
        .map_err(|e| format!("count authored places: {e}"))?;
    if placed != 2 {
        return Err(format!("authored world seeded {placed} place(s), wanted 2"));
    }
    eprintln!(
        "A3 AUTHORED WORLD: {} nodes, {} places, from contracts/world/demo_v1.json",
        rep2.channels_written, placed
    );

    // ── 4. THE SPAWN. An actor is sited in the place that was just seeded, and
    //       the occupancy query answers -- which is the sentence this whole
    //       round was aimed at.
    sqlx::query(
        "INSERT INTO entity_binding \
         (reality_id, entity_id, entity_type, location_kind, cell_id, lifecycle_state) \
         VALUES ($1, 7, 'pc', 'in_cell', 3, 0)",
    )
    .bind(reality)
    .execute(pool)
    .await
    .map_err(|e| format!("spawn: {e}"))?;

    let (occupant, place_name): (i64, String) = sqlx::query_as(
        "SELECT eb.entity_id, p.name_vi \
         FROM entity_binding eb \
         JOIN place p ON p.reality_id = eb.reality_id AND p.place_id = eb.cell_id \
         WHERE eb.reality_id = $1 AND eb.cell_id = 3",
    )
    .bind(reality)
    .fetch_one(pool)
    .await
    .map_err(|e| format!("occupancy read: {e}"))?;
    if occupant != 7 || place_name != "Yen Vu Lau" {
        return Err(format!("occupancy read got ({occupant}, {place_name:?})"));
    }

    // ── 5. And the node cannot now be deleted out from under its occupant --
    //       `R-52`, enforced by `0025`'s RESTRICT rather than by intention.
    let del = sqlx::query("DELETE FROM channels WHERE reality_id = $1 AND id = 3")
        .bind(reality)
        .execute(pool)
        .await;
    if del.is_ok() {
        return Err("deleting an occupied node SUCCEEDED -- R-52's RESTRICT is not holding".into());
    }

    Ok(())
}

/// `sqlx` has no multi-statement `execute` on a pool in every version this repo
/// pins, so the migration text is split on the statement terminator. The
/// migrations are authored with one statement per `;` at line end, which is what
/// makes this safe here and is asserted by the migrations applying at all.
#[allow(async_fn_in_trait)]
trait ExecuteManyCompat {
    async fn execute_many_compat(&self, sql: &str) -> Result<(), sqlx::Error>;
}

impl ExecuteManyCompat for sqlx::PgPool {
    async fn execute_many_compat(&self, sql: &str) -> Result<(), sqlx::Error> {
        use sqlx::Executor;
        self.execute(sql).await.map(|_| ())
    }
}

#[tokio::test]
async fn world_seed_writes_a_world_and_refuses_without_writing() {
    let Some(admin) = admin_dsn() else {
        eprintln!(
            "SKIP: LOREWEAVE_TEST_PG_ADMIN_URL unset -- this suite did NOTHING. \n             A silent skip reads as a pass, which is how a green run once certified \n             an empty one."
        );
        return;
    };
    let db = format!("ws_worldseed_{}_test", std::process::id());
    let admin_pool = sqlx::PgPool::connect(&admin).await.expect("admin connect");
    let _ = sqlx::query(&format!("DROP DATABASE IF EXISTS {db}"))
        .execute(&admin_pool)
        .await;
    sqlx::query(&format!("CREATE DATABASE {db}"))
        .execute(&admin_pool)
        .await
        .expect("create throwaway db");

    let dsn = {
        let base = admin.rsplit_once('/').expect("dsn has a database segment").0;
        format!("{base}/{db}")
    };
    let outcome = check(&dsn).await;

    // UNCONDITIONAL, on every path including the failing one.
    let _ = sqlx::query(&format!("DROP DATABASE IF EXISTS {db} WITH (FORCE)"))
        .execute(&admin_pool)
        .await;
    admin_pool.close().await;

    if let Err(e) = outcome {
        panic!("{e}");
    }
}
