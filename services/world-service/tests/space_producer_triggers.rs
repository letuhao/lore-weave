//! `A5` — the three tables that get a TRIGGER instead of a producer.
//!
//! ## Why this file is a test and not a paragraph
//!
//! `A5` decided that `portal`, `encounter` and `layer_registry` do **not** get
//! producers this run. Each has a named owner in a locked or draft document, and
//! **none of those owners is doing its job yet**. Building a producer for an
//! owner that does not work is the speculative generality `D-3` refuses — and it
//! is `3C`'s lesson again, which this whole run exists because of.
//!
//! But a deferral that only a document remembers is a wish. `deferral-gate`
//! states the rule in its own first line — *"a deferral with no mechanism is a
//! wish, and wishes evaporate"* — and names the shape that counts: **an asserted
//! trigger that REDS ON ARRIVAL. Something that changes colour by itself.**
//!
//! Each test below asserts a named owner has not arrived. **Today they pass;
//! the day the owner arrives they go red and name the table that now needs a
//! producer.** No human has to remember.
//!
//! ## What each is waiting for, MEASURED 2026-08-22 — and one measurement was wrong
//!
//! | table | owner named by | measured state |
//! |---|---|---|
//! | `portal` | `TVL_001` — *"NEW V1+30d service `travel-service`"*, authoritative owner of `actor_travel_state` | **the directory EXISTS**: an 18-line Cycle 0 scaffold |
//! | `encounter` | `COMB_002` (`tactical_grid`) and `combat_session` in the ownership matrix | no such service, scaffold or otherwise |
//! | `layer_registry` | nobody — **and that is the finding** | `LayerDef`'s whole vocabulary is absent from the authorable surface |
//!
//! **The first version of this file asked `path.exists()` and went red on its
//! first run.** `TVL_001` calls `travel-service` a *"NEW V1+30d service"* and I
//! took that as "does not exist"; the filesystem disagreed. It has been there
//! the whole time as a crate whose own header says *"Cycle 0 scaffold. This
//! crate compiles empty and has no behavior."*
//!
//! **A directory is not an owner**, so arrival is BEHAVIOUR — see
//! [`has_arrived`]. The trigger failing immediately is the trigger working: it
//! caught a claim I had read out of a document instead of measuring.
//!
//! ## `layer_registry` is the interesting one: "layer" means two things
//!
//! `RLS-A3`'s **ruleset layer** is a priority stack of authored documents. Doc
//! 41 §4's **feature layer** (`SDF-A5..A12`) is a data layer bound to a
//! `MapKind`. Same word, two concepts — and
//! `contracts/ruleset/authorable-surface.v1.yaml` enumerates only the first:
//! `home_kinds`, `update_policy`, `lifecycle_policy`, `projection` and
//! `edge_policy` appear **zero** times in it.
//!
//! So `layer_registry` is not empty because someone forgot. **It is empty
//! because a map feature layer is not authorable by anyone** — which is the PO's
//! founding thesis pointed back at itself: *"every new feature will probably
//! attach one more data layer onto the map."* The first feature that does is the
//! trigger.

use std::path::PathBuf;

fn repo() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

/// Has a service ARRIVED, or is it just a directory?
///
/// Arrival is behaviour: the crate exists and is no longer announcing itself as
/// a scaffold. The marker is the service's own words, which makes this honest in
/// both directions — a scaffold that grows up stops saying so, and a service
/// that never existed cannot say anything.
fn has_arrived(rel: &str) -> bool {
    let dir = repo().join(rel);
    if !dir.exists() {
        return false;
    }
    match std::fs::read_to_string(dir.join("src/main.rs")) {
        // No `src/main.rs` at all means a lib or something real; either way it
        // is past scaffold.
        Err(_) => true,
        Ok(text) => !text.contains("Cycle 0 scaffold"),
    }
}

/// `D-SPACE-PORTAL-NO-TRAVERSER`
///
/// `0028_portal` ships one row two ends and an unordered-pair uniqueness index.
/// Nothing traverses one. `travel-service` is on disk as a Cycle 0 scaffold and
/// blocked in its own words on the DP-kernel plus the foundation actor
/// substrate.
#[test]
fn d_space_portal_no_traverser_reds_when_travel_service_grows_up() {
    assert!(
        !has_arrived("services/travel-service"),
        "`D-SPACE-PORTAL-NO-TRAVERSER` HAS WOKEN UP: services/travel-service no longer calls itself a Cycle 0 scaffold. `TVL_001` names it the authoritative owner of actor_travel_state, so portal traversal now has somewhere to live -- give `0028_portal` a producer, or re-park this row with the new reason."
    );
}

/// `D-SPACE-ENCOUNTER-NO-OPENER`
///
/// `0030_encounter` ships the closure — where a fight is, whether an Arena was
/// carved, the opening-frame digest. Nothing opens one. The ownership matrix
/// names `combat_session` (`COMB_*`) and `tactical_grid` (`COMB_002`).
#[test]
fn d_space_encounter_no_opener_reds_when_a_combat_service_arrives() {
    for c in ["services/combat-service", "services/encounter-service"] {
        assert!(
            !has_arrived(c),
            "`D-SPACE-ENCOUNTER-NO-OPENER` HAS WOKEN UP: {c} has behaviour. `0030_encounter` states that a boundary EXISTS, WHERE it sits and WHAT crosses it; what happens inside is COMB_*'s. Its owner has arrived -- give the table a producer."
        );
    }
}

/// `D-SPACE-LAYER-REGISTRY-NO-AUTHOR`
///
/// `0029_layer_registry` (`T4`) has every policy column `NOT NULL` with no
/// `DEFAULT`, deliberately — a layer must declare its policies. Nothing declares
/// any, because a map feature layer is not authorable at all.
#[test]
fn d_space_layer_registry_no_author_reds_when_a_layer_becomes_authorable() {
    let surface = repo().join("contracts/ruleset/authorable-surface.v1.yaml");
    let text = std::fs::read_to_string(&surface)
        .unwrap_or_else(|e| panic!("read {}: {e}", surface.display()));
    let lower = text.to_lowercase();

    // `LayerDef`'s OWN vocabulary, never the bare word "layer" -- which appears
    // all over that file in the RULESET sense and would make this fire on the
    // wrong concept. That distinction is the whole reason the registry has no
    // author, so a check that could not tell the two apart would be worse than
    // none.
    const LAYER_DEF_VOCAB: [&str; 5] =
        ["home_kinds", "update_policy", "lifecycle_policy", "projection", "edge_policy"];

    let found: Vec<&str> = LAYER_DEF_VOCAB.iter().copied().filter(|k| lower.contains(k)).collect();
    assert!(
        found.is_empty(),
        "`D-SPACE-LAYER-REGISTRY-NO-AUTHOR` HAS WOKEN UP: the authorable surface now carries {found:?}, so a map FEATURE layer (doc 41 §4, not `RLS-A3`'s ruleset layer) has become authorable. `0029_layer_registry` needs a producer."
    );
}

/// The triggers above are worth nothing unless `has_arrived` can tell the two
/// states apart. This proves the MECHANISM, not the deferral.
#[test]
fn has_arrived_distinguishes_a_scaffold_from_a_real_service() {
    // Three arms, because a predicate that answered `false` to everything would
    // make every trigger permanently green -- `NV-1`'s exact shape.
    assert!(
        has_arrived("services/world-service"),
        "a service with real behaviour reads as NOT arrived -- every trigger above is then permanently green and proves nothing"
    );
    assert!(
        !has_arrived("services/travel-service"),
        "the Cycle 0 scaffold reads as arrived -- the marker check is not working, which is what made the first version of this file red on its first run"
    );
    assert!(
        !has_arrived("services/definitely-not-a-service"),
        "a path that does not exist reads as arrived"
    );
}

/// And the surface trigger must be able to see a key that IS present.
#[test]
fn the_authorable_surface_trigger_can_see_a_key_that_is_present() {
    let surface = repo().join("contracts/ruleset/authorable-surface.v1.yaml");
    let lower = std::fs::read_to_string(&surface).expect("read the surface").to_lowercase();
    // `quantity` is authored today (the gate reports 72 authored keys). If the
    // substring search cannot find it, the `LayerDef` search finding nothing
    // means nothing.
    assert!(
        lower.contains("quantity"),
        "the surface trigger found no `quantity` -- it is reading the wrong file, and its LayerDef result is therefore meaningless"
    );
}
