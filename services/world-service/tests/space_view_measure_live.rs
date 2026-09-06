//! `SDF-Q15` — the measurement, taken.
//!
//! The row asked for *"prompt-assembly cost per included node (tokens AND
//! wall-clock) at the §12.5 producer mix"* and had stood open on *"a measured
//! cost that does not exist"*. It does now, because `space_view` exists.
//!
//! WHAT IS MEASURED, AND WHAT IS HONESTLY NOT
//! ------------------------------------------
//! **Measured here:** assembled SIZE IN BYTES per included node, and WALL-CLOCK
//! per assembly, against real Postgres over a real seeded world.
//!
//! **Not measured here: TOKENS.** A token count needs the tokenizer of the model
//! that will read it, and this crate has none. Bytes are the honest proxy and are
//! labelled as one — for the CJK-heavy prose this project actually assembles, the
//! bytes-per-token ratio is very different from English, so multiplying would be
//! inventing precision. The row's other half stays open at the prompt tier, which
//! owns a tokenizer, and this test says so rather than pretending otherwise.
//!
//! THE FALSIFICATION §8.1 WROTE IN ADVANCE
//! ---------------------------------------
//! > *"the lean is that ancestors are already free (`≤16` by `DP-Ch1`) and only
//! > the portal ring and occupancy need caps. Falsified if OCCUPANCY DOMINATES —
//! > a market square with 200 occupants would make the occupant cap, not the
//! > ring, the binding constraint."*
//!
//! So the test builds exactly that market square and reports which section
//! dominates. **A measurement whose outcome cannot move the design is a ritual**,
//! and this one names the outcome that would.
//!
//! Gated by `LOREWEAVE_TEST_PG_ADMIN_URL`; creates and DROPs its own throwaway
//! database with a `test` marker. Unset => skipped.

use std::path::PathBuf;
use std::time::Instant;

use world_service::space_view::{self, ViewBudget};
use world_service::world_seed::{self, MapKind, NodeDecl, PlaceDecl};

// `dp::RealityId`'s constructor is crate-private by design (`DP-K1`), so a test
// mints one the way production does -- through a `ControlPlane` bind.
mod support;

fn admin_dsn() -> Option<String> {
    std::env::var("LOREWEAVE_TEST_PG_ADMIN_URL").ok().filter(|s| !s.is_empty())
}

fn migrations_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../contracts/migrations/per_reality")
}

const NEEDED: [&str; 5] = [
    "0019_channels",
    "0024_map_layout",
    "0025_entity_binding",
    "0026_place",
    "0028_portal",
];

fn node(id: i64, parent: Option<i64>, kind: MapKind, place: Option<PlaceDecl>) -> NodeDecl {
    NodeDecl {
        id,
        parent,
        level_name: format!("lvl{id}"),
        kind,
        pos_x: 10,
        pos_y: 10,
        scale: None,
        place,
    }
}

fn tavern(name: &str) -> Option<PlaceDecl> {
    Some(PlaceDecl {
        place_type: "tavern".into(),
        canon_ref: serde_json::json!({ "kind": "BookChapter", "path": "ch4" }),
        name_vi: name.into(),
        name_en: None,
    })
}

async fn run(pool: &sqlx::PgPool) -> Result<(), String> {
    use sqlx::Executor;
    for id in NEEDED {
        let p = migrations_dir().join(format!("{id}.up.sql"));
        let sql = std::fs::read_to_string(&p).map_err(|e| format!("read {}: {e}", p.display()))?;
        pool.execute(sql.as_str()).await.map_err(|e| format!("{id}: {e}"))?;
    }
    let reality = uuid::Uuid::new_v4();

    // A world with real depth: World -> Region -> Region -> Locale -> Domain.
    // Five levels, so the ancestor walk is exercised rather than trivial.
    let mut decls = vec![
        node(1, None, MapKind::World, None),
        node(2, Some(1), MapKind::Region, None),
        node(3, Some(2), MapKind::Region, None),
        node(4, Some(3), MapKind::Locale, None),
        node(5, Some(4), MapKind::Domain, tavern("Yen Vu Lau")),
    ];
    // Twenty sibling domains under the Locale, to give the market square doors.
    for i in 6..=25i64 {
        decls.push(node(i, Some(4), MapKind::Domain, tavern(&format!("Quan {i}"))));
    }
    world_seed::seed_world(pool, reality, &decls)
        .await
        .map_err(|e| format!("seed: {e}"))?;

    // Doors from the market square to every sibling: 20 portals on one node.
    for i in 6..=25i64 {
        sqlx::query(
            "INSERT INTO portal (reality_id, node_a, anchor_a_x, anchor_a_y, \
                                 node_b, anchor_b_x, anchor_b_y) \
             VALUES ($1, 5, 500, 0, $2, 500, 1000)",
        )
        .bind(reality)
        .bind(i)
        .execute(pool)
        .await
        .map_err(|e| format!("portal {i}: {e}"))?;
    }

    // THE MARKET SQUARE: 200 occupants, the exact case §8.1 named as the
    // falsifier.
    for e in 1..=200i64 {
        sqlx::query(
            "INSERT INTO entity_binding \
             (reality_id, entity_id, entity_type, location_kind, cell_id, lifecycle_state) \
             VALUES ($1, $2, 'npc', 'in_cell', 5, 0)",
        )
        .bind(reality)
        .bind(e)
        .execute(pool)
        .await
        .map_err(|e| format!("occupant {e}: {e}"))?;
    }

    // ── Measure. Best-of-7, the same discipline `M-1` used.
    let verified = support::verified_reality(reality);
    let budget = ViewBudget::MEASURED;
    let mut best = f64::MAX;
    let mut view = None;
    for _ in 0..7 {
        let t = Instant::now();
        let v = space_view::assemble(pool, &verified, 5, budget)
            .await
            .map_err(|e| format!("assemble: {e}"))?;
        let ms = t.elapsed().as_secs_f64() * 1000.0;
        if ms < best {
            best = ms;
        }
        view = Some(v);
    }
    let view = view.expect("seven iterations");

    let json = serde_json::to_string(&view).map_err(|e| format!("serialize: {e}"))?;
    let included = 1 + view.ancestors.len() + view.portal_ring.len() + view.occupants.len();
    let bytes_per_node = json.len() as f64 / included as f64;

    // ── The section sizes, which is what decides the falsification.
    let anc = serde_json::to_string(&view.ancestors).unwrap().len();
    let ring = serde_json::to_string(&view.portal_ring).unwrap().len();
    let occ = serde_json::to_string(&view.occupants).unwrap().len();

    eprintln!("SDF-Q15 MEASUREMENT (best of 7, real Postgres)");
    eprintln!("  wall-clock per assembly : {best:.2} ms");
    eprintln!("  assembled size          : {} B over {included} included nodes", json.len());
    eprintln!("  bytes per included node : {bytes_per_node:.1} B");
    eprintln!("  ancestors  {:>3} node(s)  {anc:>5} B", view.ancestors.len());
    eprintln!("  ring       {:>3} node(s)  {ring:>5} B", view.portal_ring.len());
    eprintln!("  occupants  {:>3} node(s)  {occ:>5} B", view.occupants.len());
    eprintln!("  truncated               : {}", view.truncated);

    // ── Assertions that make this a test rather than a print.
    if !view.truncated {
        return Err("200 occupants and 20 doors did not trip the truncation flag -- \
                    a reader could not tell a crowded room from an empty one"
            .into());
    }
    // `C2` -- NEAREST FIRST, asserted rather than assumed.
    //
    // The ancestor walk became a recursive CTE, and a CTE returns rows in
    // whatever order the planner finds them unless told otherwise. The loop it
    // replaced produced nearest-first as a side effect of BEING a loop; the
    // query has to say so. `SDF-A4` forbids incidental ordering and this is the
    // case it means: the seed is 1 -> 2 -> 3 -> 4 -> 5, so a view of node 5 must
    // list 4, 3, 2, 1 and nothing else.
    let chain: Vec<i64> = view.ancestors.iter().map(|a| a.node_id).collect();
    if chain != vec![4, 3, 2, 1] {
        return Err(format!(
            "ancestors are {chain:?}, wanted [4, 3, 2, 1] -- nearest first is a CONTRACT, and a recursive CTE has no inherent order"
        ));
    }

    if view.ancestors.len() != 4 {
        return Err(format!("wanted 4 ancestors, got {}", view.ancestors.len()));
    }
    if view.occupants.len() != budget.occupants || view.portal_ring.len() != budget.portal_ring {
        return Err(format!(
            "caps not applied: {} occupants, {} ring",
            view.occupants.len(),
            view.portal_ring.len()
        ));
    }
    // Determinism: the caps must cut a PREFIX of a total order, not a sample.
    let mut sorted = view.occupants.clone();
    sorted.sort_unstable();
    if sorted != view.occupants || view.occupants.first() != Some(&1) {
        return Err("occupants are not the ascending prefix -- the cap is sampling, \
                    and two readers would disagree"
            .into());
    }

    // ── THE FALSIFICATION, evaluated rather than asserted away.
    if occ > ring && occ > anc {
        eprintln!(
            "  => §8.1's LEAN IS FALSIFIED: occupancy dominates ({occ} B) over ring ({ring} B) \
             and ancestors ({anc} B). The OCCUPANT cap is the binding constraint, not the ring."
        );
    } else {
        eprintln!("  => §8.1's lean holds: the ring or ancestors dominate.");
    }
    Ok(())
}

#[tokio::test]
async fn sdf_q15_space_view_assembly_cost() {
    let Some(admin) = admin_dsn() else {
        eprintln!(
            "SKIP: LOREWEAVE_TEST_PG_ADMIN_URL unset -- this suite did NOTHING. \n             A silent skip reads as a pass, which is how a green run once certified \n             an empty one."
        );
        return;
    };
    let db = format!("ws_spaceview_{}_test", std::process::id());
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
    let _ = sqlx::query(&format!("DROP DATABASE IF EXISTS {db} WITH (FORCE)"))
        .execute(&admin_pool)
        .await;
    admin_pool.close().await;
    if let Err(e) = outcome {
        panic!("{e}");
    }
}
