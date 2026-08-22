//! `A3` — spawn, and the one property that makes it worth having.
//!
//! ## What this proves that a unit test cannot
//!
//! `spawn::site_in_cell` takes a `&mut PgConnection` instead of a `&PgPool` for
//! exactly one reason: **the actor row and its binding must land together or
//! neither does.** That is a statement about a transaction, and a transaction is
//! not observable without a database.
//!
//! The failure it prevents is not hypothetical. `world_seed` refuses to
//! half-write a world, and its stated reason is `orphan_scan` — which exists
//! because a half-provisioned reality sits at `status=provisioning` until a
//! 7-day grace collects it. **An actor with no binding has no collector at
//! all**, so a partial spawn is worse than the case the repo already decided was
//! bad enough to design against.
//!
//! ## THE BITE THIS TEST IS BUILT AROUND
//!
//! Leg 3 sites an actor at a node that does not exist. `0025`'s foreign key is
//! `ON DELETE RESTRICT` against `channels`, so the INSERT is refused — and the
//! question that matters is what happened to the `actors` row written moments
//! earlier in the same call. If the count moved, spawn manufactured an orphan.
//!
//! Gated by `LOREWEAVE_TEST_PG_ADMIN_URL`; creates and DROPs its own throwaway
//! database whose name carries a `test` marker. Unset => skipped.

use std::path::PathBuf;

use world_service::actor_registry;
use world_service::space_view::{self, Whereabouts};
use world_service::spawn::{EntityType, Siting};
use world_service::world_seed::{self, MapKind, NodeDecl};

// `RealityId`'s constructor is crate-private in `dp` by design (`DP-K1`), so a
// test mints one the way production does -- through a `ControlPlane` bind -- and
// no other way. `support` is the one place that knows how.
mod support;

fn admin_dsn() -> Option<String> {
    std::env::var("LOREWEAVE_TEST_PG_ADMIN_URL").ok().filter(|s| !s.is_empty())
}

fn migrations_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../contracts/migrations/per_reality")
}

/// The minimum chain: the skeleton, the tree, the actors table, the map row and
/// the binding.
const NEEDED: [&str; 6] =
    ["0001_initial", "0019_channels", "0022_actors", "0024_map_layout", "0025_entity_binding", "0026_place"];

/// A World, and a Domain under it that CARRIES A PLACE.
///
/// The second node is not decoration: `where_is` reads `place.name_vi`, and a
/// fixture of one placeless `World` would exercise the query while leaving its
/// most interesting column permanently `None`. That is how a join rots -- it
/// keeps working and stops being checked.
fn one_world() -> Vec<NodeDecl> {
    vec![
        NodeDecl {
            id: 1,
            parent: None,
            level_name: "thien-gioi".into(),
            kind: MapKind::World,
            pos_x: 500,
            pos_y: 500,
            place: None,
            scale: None,
        },
        NodeDecl {
            id: 2,
            parent: Some(1),
            level_name: "yen-vu-lau".into(),
            kind: MapKind::Domain,
            pos_x: 480,
            pos_y: 520,
            place: Some(world_service::world_seed::PlaceDecl {
                place_type: "tavern".into(),
                canon_ref: serde_json::json!({ "kind": "BookChapter", "path": "ch1" }),
                name_vi: "Yen Vu Lau".into(),
                name_en: None,
            }),
            scale: None,
        },
    ]
}

async fn actors_count(pool: &sqlx::PgPool) -> i64 {
    sqlx::query_scalar("SELECT count(*) FROM actors").fetch_one(pool).await.expect("count actors")
}

async fn bindings_count(pool: &sqlx::PgPool) -> i64 {
    sqlx::query_scalar("SELECT count(*) FROM entity_binding")
        .fetch_one(pool)
        .await
        .expect("count bindings")
}

async fn run(pool: &sqlx::PgPool) -> Result<(), String> {
    use sqlx::Executor;
    for id in NEEDED {
        let p = migrations_dir().join(format!("{id}.up.sql"));
        let sql = std::fs::read_to_string(&p).map_err(|e| format!("read {}: {e}", p.display()))?;
        pool.execute(sql.as_str()).await.map_err(|e| format!("{id}: {e}"))?;
    }

    let raw = uuid::Uuid::new_v4();
    world_seed::seed_world(pool, raw, &one_world()).await.map_err(|e| format!("seed: {e}"))?;
    let reality = support::verified_reality(raw);

    // ── 1. NO SITING is a legitimate outcome, not a degraded one. Every actor
    //       in this repo was in this state until `A3`, and the row must still be
    //       creatable that way or the change is a breaking one wearing a feature.
    let bare = actor_registry::create_actor(pool, &reality, None)
        .await
        .map_err(|e| format!("create bare actor: {e}"))?;
    if actors_count(pool).await != 1 || bindings_count(pool).await != 0 {
        return Err("an unsited actor must create an actor row and NO binding".into());
    }

    // ── 2. WITH a siting, both rows land.
    let siting = Siting { node: 2, entity_type: EntityType::Pc, lifecycle_state: 0 };
    let sited = actor_registry::create_actor(pool, &reality, Some(&siting))
        .await
        .map_err(|e| format!("create sited actor: {e}"))?;
    if actors_count(pool).await != 2 || bindings_count(pool).await != 1 {
        return Err("a sited actor must create BOTH an actor row and a binding".into());
    }
    let where_is: i64 = sqlx::query_scalar(
        "SELECT cell_id FROM entity_binding WHERE reality_id = $1 AND entity_id = $2",
    )
    .bind(raw)
    .bind(sited.entity_id)
    .fetch_one(pool)
    .await
    .map_err(|e| format!("read binding: {e}"))?;
    if where_is != 2 {
        return Err(format!("the actor was sited at {where_is}, not the node asked for"));
    }
    if sited.entity_id == bare.entity_id {
        return Err("two actors got the same island id".into());
    }

    // ── 3. THE BITE. A node that does not exist. The binding must be refused,
    //       AND the actor row written moments earlier must go with it.
    let before = actors_count(pool).await;
    let nowhere = Siting { node: 9_999, entity_type: EntityType::Npc, lifecycle_state: 0 };
    let outcome = actor_registry::create_actor(pool, &reality, Some(&nowhere)).await;
    if outcome.is_ok() {
        return Err("siting at a node that does not exist SUCCEEDED -- `0025`'s foreign \
                    key is not doing what this test assumes"
            .into());
    }
    let after = actors_count(pool).await;
    if after != before {
        return Err(format!(
            "THE ORPHAN IS REAL: the binding was refused but {} actor row(s) survived \
             ({before} -> {after}). An actor that exists with nowhere to be has no \
             collector -- `orphan_scan` does not look at this table",
            after - before
        ));
    }
    if bindings_count(pool).await != 1 {
        return Err("a refused siting left a binding behind".into());
    }

    // ── 4. And the same actor cannot be sited twice. Arriving is not moving:
    //       letting an INSERT double as a move makes them indistinguishable in
    //       the log, which is `R-52`'s evacuate-never-delete losing its subject.
    let mut conn = pool.acquire().await.map_err(|e| format!("acquire: {e}"))?;
    if world_service::spawn::site_in_cell(&mut conn, &reality, sited.entity_id, &siting).await.is_ok() {
        return Err("an already-sited entity was sited a second time -- spawn is \
                    silently acting as move"
            .into());
    }

    // ── 5. `A4` — WHERE IS IT. Three DISTINCT facts, and the point of the test
    //       is that they stay distinct: collapsing `Unbound` and `NotInACell`
    //       into one silence is exactly what `0025`'s sum-type CHECK exists to
    //       prevent one layer down.
    match space_view::where_is(pool, &reality, sited.entity_id).await {
        Ok(Whereabouts::InCell(loc)) => {
            if loc.node != 2
                || loc.node_kind != "domain"
                || loc.place_name.as_deref() != Some("Yen Vu Lau")
            {
                return Err(format!("sited actor resolved to {loc:?}"));
            }
        }
        other => return Err(format!("a sited actor must be InCell, got {other:?}")),
    }
    match space_view::where_is(pool, &reality, bare.entity_id).await {
        Ok(Whereabouts::Unbound) => {}
        other => return Err(format!("an unsited actor must be Unbound, got {other:?}")),
    }

    //       The third arm needs a binding that is NOT a cell. Without it the
    //       enum would have two reachable variants and one that no test ever
    //       produced -- which is how a variant rots into being wrong.
    sqlx::query(
        "INSERT INTO entity_binding \
         (reality_id, entity_id, entity_type, location_kind, holder_entity, lifecycle_state) \
         VALUES ($1, 4242, 'item', 'held_by', $2, 0)",
    )
    .bind(raw)
    .bind(sited.entity_id)
    .execute(pool)
    .await
    .map_err(|e| format!("bind a held item: {e}"))?;
    match space_view::where_is(pool, &reality, 4242).await {
        Ok(Whereabouts::NotInACell { location_kind }) if location_kind == "held_by" => {}
        other => {
            return Err(format!(
                "a HELD item must be NotInACell -- reporting Unbound would say it does \
                 not exist, got {other:?}"
            ));
        }
    }

    eprintln!("A3 SPAWN (real Postgres)");
    eprintln!("  unsited actor          : entity {} , 0 bindings", bare.entity_id);
    eprintln!("  sited actor            : entity {} -> cell {where_is}", sited.entity_id);
    eprintln!("  refused siting         : actors {before} -> {after} (no orphan)");
    eprintln!("  double siting          : refused");
    Ok(())
}

#[tokio::test]
async fn a3_spawn_is_atomic_with_actor_creation() {
    let Some(admin) = admin_dsn() else {
        eprintln!(
            "SKIP: LOREWEAVE_TEST_PG_ADMIN_URL unset -- this suite did NOTHING. \n             A silent skip reads as a pass, which is how a green run once certified \n             an empty one."
        );
        return;
    };
    let db = format!("ws_spawn_{}_test", std::process::id());
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
