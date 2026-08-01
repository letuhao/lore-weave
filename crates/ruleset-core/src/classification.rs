//! S1a — every rules field carries a classification, and a new field cannot
//! arrive without one.
//!
//! ## What this is, and the finding that shaped it
//!
//! [16a](../../../docs/03_planning/LLM_MMO_RPG/16a_ruleset_field_classification.md)
//! classified all 40 `Ruleset` fields by merge strategy (RLS-A4), lowest
//! permissible layer (RLS-A16) and mutability class (RLS-A17). Doc 26's build
//! order calls wiring that table **S1**, exit criterion *"an over-reaching
//! override is REFUSED, with a test."*
//!
//! **That test cannot fail today, and the reason is structural.** All 40 rows in
//! 16a §3.2 carry floor `pre` — and `preset` is the lowest *authorable* layer,
//! `engine_default` being the totality base. A floor every field already
//! satisfies refuses nothing. The 3 `Frozen` and 13 `AdditiveOnly` fields are
//! collections `Ruleset` does not have (`ruleset-loader`'s own module doc says
//! so). What exists is **20 scalars, every one `Tunable` with floor `pre`**.
//!
//! So a floor-check function here would return *permitted* for every input that
//! can exist — [`NV-2`](../../../docs/standards/non-vacuity.md), *the subject
//! cannot vary*, the first of the four shapes. It is not built. **The
//! enforcement arms are S1b, and their trigger is named:** `Q1` introduces L2
//! declared quantities — an ID-keyed registry whose ordinals are assigned and
//! never reused ([QTY-A5](../../../docs/03_planning/LLM_MMO_RPG/35_quantity_architecture.md))
//! — which is `AdditiveOnly` under another name and the first field a class
//! check will ever be able to refuse.
//!
//! ## What IS built, and why it is not the same thing
//!
//! The **registration mechanism**, with the polarity the other direction.
//!
//! Doc 16 line 652 reads *"Default for an unclassified field: `Tunable`."* That
//! is **default-allow**: the other 44 rows, and every field invented after them,
//! would arrive unclassified and silently become freely mutable. Here a field
//! with no classification is **error E0027 at compile time** — the class table
//! is generated from a pattern that must mention every field, so the table and
//! the struct cannot drift apart.
//!
//! Declared data with a compile-time totality proof **can** fail. A validator
//! that always says yes cannot. That is the whole distinction.

/// Lowest layer permitted to declare a field (RLS-A16).
///
/// Only [`Floor::Preset`] occurs among today's 20 rows; the rest exist because
/// 16a assigns them to fields whose structs land later — `Reality` to the seven
/// instance-keyed WorldContent rows, `Book` to `book_canon_ref`. Transcribing a
/// decided table is data; acting on it is S1b.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Floor {
    EngineDefault,
    Preset,
    Book,
    Reality,
}

/// What an author may do to a field after a reality exists (RLS-A17).
///
/// The deciding question is **not** importance — it is *does stored state
/// reference this declaration by ID?* If yes, redefining or removing it orphans
/// rows. `Frozen` is narrower: a change would **falsify past events**.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mutability {
    /// Nothing stored points at it; a change re-derives and never orphans.
    Tunable,
    /// Append yes; redefine and remove no. Removal downgrades to deprecation.
    AdditiveOnly,
    /// Any edit is rejected at the validator and never tiered.
    Frozen,
}

/// How two layers combine for this field (RLS-A4).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Strategy {
    /// Higher layer replaces the value whole.
    Replace,
    /// Merge by id, higher layer overriding matching entries.
    Union,
    /// A lower layer may impose a bound a higher one cannot loosen.
    ClampMin,
    /// **No layer may declare it at all** — see [`FORBIDDEN_KEYS`].
    Forbidden,
}

/// One field's row.
///
/// `parent` names the 16a §3.2 row this field belongs to, because the shipped
/// fields are **finer-grained than 16a's table**: `av_base` is one constant of
/// the row 16a calls `initiative_system`. Recording the parent is what makes
/// the transcription auditable against 16a instead of merely asserted.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FieldClass {
    pub name: &'static str,
    pub floor: Floor,
    pub mutability: Mutability,
    pub strategy: Strategy,
    /// The 16a §3.2 row this field is a constant of.
    pub parent: &'static str,
}

/// Generate a struct's class table **from a pattern that must mention every
/// field**, so the table cannot drift from the struct.
///
/// The proof is `assert_classification_is_total`: `let Self { a, b, c } = self;`
/// with no `..`. Add a field and that pattern becomes incomplete, which is
/// **E0027, a hard error** — not a lint that a busy author can allow away.
///
/// Its *body* is the deliverable, not its behaviour — but it is `pub` and called
/// from a test rather than marked `#[allow(dead_code)]`, because dead code is
/// the kind of thing a tidy-up deletes, and deleting this would take the only
/// guard with it while every test stayed green.
///
/// **The macro destructures the struct; it never generates it.** `CombatRules`
/// and `StatRules` are inside the hashed canonical encoding, and a macro that
/// emitted them could reorder fields and move every reality's digest.
macro_rules! classify {
    ($ty:ty { $($field:ident => $floor:expr, $mutability:expr, $strategy:expr, $parent:literal;)+ }) => {
        impl $ty {
            /// Every field of this struct, classified. Total by construction.
            pub const CLASSES: &'static [FieldClass] = &[
                $(FieldClass {
                    name: stringify!($field),
                    floor: $floor,
                    mutability: $mutability,
                    strategy: $strategy,
                    parent: $parent,
                },)+
            ];

            /// The pattern below IS the totality proof: adding a field makes it
            /// incomplete, which is a hard error.
            ///
            /// It is `pub` and CALLED by a test rather than
            /// `#[allow(dead_code)]`. That allow was itself a quiet risk —
            /// dead code can be deleted by anyone tidying up, and deleting
            /// this takes the only guard with it while every test stays
            /// green. Being called means removing it is a red.
            #[allow(unused_variables)]
            pub fn assert_classification_is_total(&self) {
                let Self { $($field),+ } = self;
            }
        }
    };
}

use crate::combat::CombatRules;
use crate::ruleset::Ruleset;
use crate::stats::StatRules;

classify!(CombatRules {
    hit_base_pm            => Floor::Preset, Mutability::Tunable, Strategy::Replace, "combat_disparity_cap";
    hit_floor_pm           => Floor::Preset, Mutability::Tunable, Strategy::Replace, "combat_disparity_cap";
    hit_ceiling_pm         => Floor::Preset, Mutability::Tunable, Strategy::Replace, "combat_disparity_cap";
    roll_band_lo_pm        => Floor::Preset, Mutability::Tunable, Strategy::Replace, "strike_formula";
    roll_band_hi_pm        => Floor::Preset, Mutability::Tunable, Strategy::Replace, "strike_formula";
    elem_mult_pm           => Floor::Preset, Mutability::Tunable, Strategy::Replace, "strike_formula";
    resist_pm              => Floor::Preset, Mutability::Tunable, Strategy::Replace, "strike_formula";
    defend_divisor         => Floor::Preset, Mutability::Tunable, Strategy::Replace, "strike_formula";
    max_hit                => Floor::Preset, Mutability::Tunable, Strategy::Replace, "strike_formula";
    ko_duration_rounds     => Floor::Preset, Mutability::Tunable, Strategy::Replace, "combat_mortality_config";
    av_base                => Floor::Preset, Mutability::Tunable, Strategy::Replace, "initiative_system";
    av_slowed_pm           => Floor::Preset, Mutability::Tunable, Strategy::Replace, "initiative_system";
    av_hasted_pm           => Floor::Preset, Mutability::Tunable, Strategy::Replace, "initiative_system";
    av_stunned_pm          => Floor::Preset, Mutability::Tunable, Strategy::Replace, "initiative_system";
    av_initiator_first_pm  => Floor::Preset, Mutability::Tunable, Strategy::Replace, "side_default_setup";
});

// ── A note the `av_*` rows need, because the obvious reading is wrong ──
//
// 16a marks `initiative_system` **`Frozen`** — "turn-order semantics; V1 has
// exactly one value (HSR action value), so `Frozen` costs nothing now and
// forecloses a V1+ footgun." The five `av_*` fields are NOT that row's value.
// They are tuning constants *inside* the chosen system: changing `av_base`
// re-derives every future action value and falsifies no past event, which is
// the `Tunable` test exactly. The `Frozen` bit belongs to the choice of system,
// which is not a field this struct has — it is the shape of `CombatRules`
// itself. Recorded because assigning `Frozen` here by pattern-matching the
// parent name would brick every reality's ability to retune combat.

classify!(StatRules {
    slot_defaults          => Floor::Preset, Mutability::Tunable, Strategy::Replace, "stat_slots";
    move_base              => Floor::Preset, Mutability::Tunable, Strategy::Replace, "stat_tuning";
    move_speed_per_tile    => Floor::Preset, Mutability::Tunable, Strategy::Replace, "stat_tuning";
    move_max               => Floor::Preset, Mutability::Tunable, Strategy::Replace, "stat_tuning";
    melee_archetype        => Floor::Preset, Mutability::Tunable, Strategy::Replace, "stat_archetypes";
});

// `slot_defaults` / `melee_archetype` are `Replace` and not `Union` on purpose:
// both are whole-array overrides today. Per-slot merge waits for the slot set
// to be ruleset-declared (doc 31 R02) — until a slot has a stable authored
// NAME, keying an override on it would bake an engine ordinal into content.

classify!(Ruleset {
    schema_version => Floor::EngineDefault, Mutability::Frozen, Strategy::Forbidden, "schema_version";
    law_version    => Floor::EngineDefault, Mutability::Frozen, Strategy::Forbidden, "schema_version";
    combat         => Floor::Preset, Mutability::Tunable, Strategy::Replace, "(group)";
    stats          => Floor::Preset, Mutability::Tunable, Strategy::Replace, "(group)";
    quantities     => Floor::Preset, Mutability::AdditiveOnly, Strategy::Union, "(L2 declared)";
    // Q2 — the same class as `quantities`, and for the same reason: a higher
    // layer may DECLARE a pool the layer below did not, and may never take one
    // away. `Union` rather than `Replace` is what makes a reality layer additive
    // over the engine default instead of a wholesale override that could drop a
    // pool an actor's stored `pools[ordinal]` already holds a value in.
    resources      => Floor::Preset, Mutability::AdditiveOnly, Strategy::Union, "(L2 declared)";
    // S-1b — Forbidden, and for the SAME reason as `schema_version`: it is
    // COMPUTED, never authored. A progression pin is the content address of a
    // table, so a layer that wrote one would be naming bytes it did not
    // produce. `AdditiveOnly`/`Union` would have been the wrong call and an
    // actively harmful one: it would add a THIRD S1b subject owing floor and
    // mutability enforcement in a loader that has no authoring form for
    // progression at all - a class the table CLAIMS to govern and nothing
    // enforces, which is exactly what `s1b_subjects_...`'s message warns
    // against. When `PGN-R2` gives the loader a form, this row changes and that
    // test reds.
    progression    => Floor::EngineDefault, Mutability::Frozen, Strategy::Forbidden, "progression_digest";
});

/// Top-level keys **no layer may declare**, with the reason an author gets told.
///
/// Both identify the ENCODING and the ENGINE, not the rules. They are refused
/// rather than merged because a layer that could set them could make an
/// artifact assert something untrue about itself:
///
/// * `schema_version` selects which codec reads the bytes (`QTY-A11`
///   version dispatch). An author choosing it chooses how their own file is
///   interpreted.
/// * `law_version` is a claim about **which engine laws produced this ruleset**
///   (`QTY-D13`, added by `Q0a`). An author who could set it could ship an
///   artifact claiming laws it was never built with — and since `Q0a` put it
///   inside the hashed bytes, that claim would travel with the digest.
///
/// Today the absence of these keys from `RulesetPatch` already refuses them, as
/// a side effect of `deny_unknown_fields`. That is an **incidental** guarantee,
/// one refactor from gone, and it answers with *"unknown field"* — wrong twice:
/// the field is not unknown, and the author is not told why they may never set
/// it. `NV-4` is precisely a guard defeated by an adjacent decision, so this one
/// is made explicit and tested.
pub const FORBIDDEN_KEYS: &[(&str, &str)] = &[
    (
        "progression",
        "progression is pinned by DIGEST, and the digest is COMPUTED from the table's bytes rather than authored; a layer writing one would be naming bytes it did not produce (RLS-A4 Forbidden). The authoring form lands with the loader, PGN-R2",
    ),
    (
        "schema_version",
        "schema_version identifies the ENCODING (which codec reads these bytes), not the rules; \
         no layer may declare it (RLS-A4 Forbidden)",
    ),
    (
        "law_version",
        "law_version is the engine's claim about which LAWS produced this ruleset (QTY-D13) and \
         is inside the hashed bytes; no layer may declare it (RLS-A4 Forbidden)",
    ),
];

#[cfg(test)]
mod tests {
    use super::*;

    /// The table is generated from an exhaustive pattern, so this asserts the
    /// COUNT a reader can check against the struct — the residual the E0027
    /// proof does not cover is a field bound in the pattern and then given the
    /// wrong row, which `parent` makes auditable against 16a.
    #[test]
    fn every_shipped_field_is_classified() {
        // Calling these is what keeps the totality proofs from being deleted as
        // dead code. Their VALUE is that they compile; the call is what makes
        // their absence a test failure rather than a silent gap.
        Ruleset::engine_default().assert_classification_is_total();
        Ruleset::engine_default().combat.assert_classification_is_total();
        Ruleset::engine_default().stats.assert_classification_is_total();

        assert_eq!(CombatRules::CLASSES.len(), 15);
        assert_eq!(StatRules::CLASSES.len(), 5);
        // S-1b added `progression`. The count is pinned rather than derived so a
        // field added WITHOUT a classify! row reds here even though the macro's
        // exhaustive pattern would have caught it first - two independent proofs
        // of the same property, which is the point.
        assert_eq!(Ruleset::CLASSES.len(), 7);
    }

    /// **THE S1b TRIGGER FIRED, 2026-07-29, on `Q1`. This is what it became.**
    ///
    /// Its previous form asserted that no rules field was non-`Tunable` and that
    /// no floor sat above `preset` — the two conditions under which a floor or
    /// mutability check could refuse *anything*. While both held, building those
    /// checks would have been `NV-2`: a validator returning *permitted* for every
    /// input that can exist.
    ///
    /// `Q1` added `Ruleset::quantities`, an ID-keyed registry that is
    /// `AdditiveOnly` and **declarable** — the first refusable subject this
    /// ruleset has ever had. The trigger reddened without anyone remembering to
    /// look, which is the whole reason it was written as an assertion instead of
    /// a note.
    ///
    /// What it guards NOW: the two properties S1b's enforcement rests on.
    #[test]
    fn s1b_subjects_are_exactly_the_declarable_non_tunable_fields() {
        // 1. The L1 scalars are still uniformly Tunable/preset. If that ever
        //    stops being true, a per-field check is owed for them too — and this
        //    is what would say so.
        for c in CombatRules::CLASSES.iter().chain(StatRules::CLASSES.iter()) {
            assert_eq!(
                c.mutability,
                Mutability::Tunable,
                "`{}` is no longer Tunable — the L1 scalars were uniform, and a per-field                  mutability check now has a subject among them",
                c.name
            );
            assert_eq!(c.floor, Floor::Preset, "`{}` moved off the preset floor", c.name);
        }

        // 2. Every non-Tunable field on `Ruleset` is either FORBIDDEN (refused
        //    outright, which is stronger than any class check) or is a genuine
        //    S1b subject with enforcement owed. `quantities` is the latter, and
        //    its enforcement lives in the loader:
        //      * floor  — `engine_default` may not declare quantities
        //      * class  — AdditiveOnly, enforced BY CONSTRUCTION: the layer fold
        //                 is a union, so removal is inexpressible rather than
        //                 checked. Proven by `a_lower_layers_declaration_survives_
        //                 every_higher_layer` in ruleset-loader.
        let subjects: Vec<&str> = Ruleset::CLASSES
            .iter()
            .filter(|c| c.mutability != Mutability::Tunable && c.strategy != Strategy::Forbidden)
            .map(|c| c.name)
            .collect();
        assert_eq!(
            subjects,
            // Q2 added `resources`, and it owes the same two enforcements:
            //   * floor  — `resolve` refuses a below-preset layer that declares
            //              one (`a_pool_below_the_preset_floor_is_refused`)
            //   * class  — AdditiveOnly, enforced BY CONSTRUCTION for the same
            //              reason `quantities` is: the fold appends, and
            //              `ResourceTable` has no verb for removal, so a lower
            //              layer's pool cannot be taken away by a higher one.
            vec!["quantities", "resources"],
            "the set of fields needing S1b enforcement changed. Every entry here must have a              floor rule and a mutability rule in `ruleset-loader::validate`, or it is a class              the table CLAIMS to govern and nothing enforces"
        );
    }

    #[test]
    fn forbidden_keys_carry_a_reason_that_names_the_field() {
        // The first draft of this test opened with `assert!(!FORBIDDEN_KEYS.is_empty())`
        // and **clippy caught it**: `FORBIDDEN_KEYS` is a `const`, so the call is
        // folded at compile time and the assertion could never fail — `NV-2`, in
        // the very file that argues against shipping those. Recorded rather than
        // quietly deleted, because the lesson is that intent is no defence: the
        // author had the standard in mind and wrote a vacuous line anyway.
        //
        // What replaces it is a claim that CAN fail: the count is pinned, so
        // deleting a row is a red rather than a silently shorter loop below.
        assert_eq!(
            FORBIDDEN_KEYS.len(),
            3,
            "a refusal key was added or removed — if that was deliberate, update this \
             count and `forbidden_classes_and_refusal_keys_agree` will check the pairing"
        );
        for (key, reason) in FORBIDDEN_KEYS {
            // The loader checks these against the document's TOP-LEVEL table
            // only. A dotted key would therefore be registered here and never
            // refused — a rule with no enforcement, which is worse than no rule
            // because the table says it is covered.
            assert!(
                !key.contains('.'),
                "`{key}` is a nested key, but the loader only scans top-level table keys — \
                 it would be silently unenforced. Teach `parse_layer` to walk sub-tables first."
            );
            assert!(
                reason.contains(key),
                "the diagnostic for `{key}` must name the field it refuses"
            );
            assert!(
                reason.len() > 40,
                "`{key}`'s reason is too short to teach anything: {reason}"
            );
        }
    }

    /// Every `Forbidden` row in the class table has a matching refusal key, and
    /// vice versa. Without this the two could drift: a field marked `Forbidden`
    /// that the loader never checks is a rule with no enforcement.
    #[test]
    fn forbidden_classes_and_refusal_keys_agree() {
        let mut classed: Vec<&str> = Ruleset::CLASSES
            .iter()
            .filter(|c| c.strategy == Strategy::Forbidden)
            .map(|c| c.name)
            .collect();
        let mut keys: Vec<&str> = FORBIDDEN_KEYS.iter().map(|(k, _)| *k).collect();
        classed.sort_unstable();
        keys.sort_unstable();
        assert_eq!(
            classed, keys,
            "a field classified `Forbidden` has no refusal key (or the reverse) — one of the two \
             is unenforced"
        );
    }
}
