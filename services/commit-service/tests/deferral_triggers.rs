//! **The MECHANISMS behind this run's deferral rows.**
//!
//! `scripts/deferral-gate.py` refuses an id that is prose and nothing else. A
//! row may instead carry an ASSERTED TRIGGER: a check that reds when its own
//! subject arrives, so the deferral announces its own discharge rather than
//! waiting to be re-read.
//!
//! Split out of `hub_consumer.rs` at `IMP-D3`'s ceiling, and the seam is real:
//! everything there tests what the code DOES, everything here tests what it
//! does NOT do yet. The second kind is meant to be DELETED, and keeping it in
//! one file is what makes that a clean removal.

mod hub_fixture;

use commit_service::combat::Side;
use commit_service::Actor;
use sim_core::EntityId;

const A: EntityId = EntityId(1);

/// **The asserted trigger for `D-PER-ACTOR-STATS-UNEXPRESSIBLE`.**
///
/// `M1` collapsed `Actor.stats` into one archetype per reality, because the
/// per-actor copies differed only in `CombatStats::max_hp` and no law reads that
/// field. The consequence is that **a reality cannot give two actors different
/// speeds today** — and a deferral row is prose unless something reds when its
/// subject arrives.
///
/// This is that something. It fails the moment `StatRules` grows a second
/// archetype, or `Actor` grows anywhere to store per-actor modifiers — which are
/// the only two shapes in which the missing capability can arrive. Whoever makes
/// that change reads this test, and the row goes with it.
#[test]
fn the_reality_declares_exactly_one_archetype() {
    let rules = hub_fixture::rules();

    // ONE archetype in the ruleset. `StatRules` is destructured exhaustively so
    // a new field cannot be added without this line failing to compile —
    // the same mechanism `CanonEncode` uses to keep a field out of the digest.
    let ruleset_core::StatRules {
        slot_defaults: _,
        move_base: _,
        move_speed_per_tile: _,
        move_max: _,
        melee_archetype: _,
    } = rules.rules().stats;

    // …and every actor in the reality resolves to it. Two actors, one block —
    // which IS the deferred limitation, asserted rather than described. When a
    // per-actor stat path lands this equality stops holding, and the row is
    // discharged by the change that broke it.
    let a = Actor::spawn(&rules, A, Side::A);
    let b = Actor::spawn(&rules, EntityId(2), Side::B);
    assert_eq!(
        a.vital_ceiling(&rules),
        b.vital_ceiling(&rules),
        "two actors already differ — per-actor stats exist, so \
         D-PER-ACTOR-STATS-UNEXPRESSIBLE is discharged and this test should go with it"
    );
}

/// **The asserted trigger for `D-ZERO-BEHAVIOUR-UNREAD`.**
///
/// `ZeroBehaviour` is declared, hashed and authorable, and **no law reads it**.
/// A cold-start reviewer measured that while `proving-ground.toml` claimed
/// `block_costs` was *"what it was written for"*. The field is not wrong — it is
/// the right value for that row with no consumer yet, which is
/// `orphan-model-gate`'s shape inside a hashed enum, and `QTY-A10(c)` forbids
/// removing it.
///
/// This test is the row's mechanism. It reads the source and fails the moment a
/// law reads the field, which is when the deferral is discharged and this test
/// should leave with it.
#[test]
fn zero_behaviour_has_no_consumer_yet() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|p| p.parent())
        .expect("repo root");
    // Where the field is DECLARED and ENCODED — reading it there is not
    // consuming it, and excluding them by path is exact rather than a guess.
    let declaration_sites = [
        "crates/ruleset-core/src/resource/mod.rs",
        "crates/ruleset-core/src/resource/table.rs",
        "crates/ruleset-loader/src/patch_resource.rs",
    ];
    let mut readers = Vec::new();
    for tree in ["crates", "services"] {
        let mut stack = vec![root.join(tree)];
        while let Some(dir) = stack.pop() {
            let Ok(entries) = std::fs::read_dir(&dir) else { continue };
            for e in entries.flatten() {
                let path = e.path();
                if path.is_dir() {
                    if path.file_name().is_some_and(|n| n == "target" || n == "node_modules") {
                        continue;
                    }
                    stack.push(path);
                } else if path.extension().is_some_and(|x| x == "rs") {
                    let rel = path
                        .strip_prefix(root)
                        .unwrap()
                        .to_string_lossy()
                        .replace(char::from(92u8), "/");
                    if declaration_sites.contains(&rel.as_str()) || rel.contains("/tests/") {
                        continue;
                    }
                    let src = std::fs::read_to_string(&path).unwrap_or_default();
                    for (i, line) in src.lines().enumerate() {
                        let code = line.split("//").next().unwrap_or("");
                        if code.contains("zero_behaviour") || code.contains("ZeroBehaviour::") {
                            readers.push(format!("{rel}:{}", i + 1));
                        }
                    }
                }
            }
        }
    }
    println!("D-ZERO-BEHAVIOUR-UNREAD  consumers outside the declaration sites: {readers:?}");
    assert!(
        readers.is_empty(),
        "a law now reads `zero_behaviour` — D-ZERO-BEHAVIOUR-UNREAD is DISCHARGED. \
         Remove its registry row and delete this test:\n  {}",
        readers.join("\n  ")
    );
}
