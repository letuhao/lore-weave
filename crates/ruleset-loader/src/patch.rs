//! A LAYER is a partial override; the resolved ruleset is total.
//!
//! RLS-A3's stack has five layers and an author writes only what they change:
//!
//! ```toml
//! # a reality layer — everything else inherits
//! [combat]
//! max_hit = 250_000
//! ```
//!
//! So a layer deserializes into [`RulesetPatch`], where **every field is
//! `Option`**, and resolution folds patches over `Ruleset::engine_default()` in
//! priority order. Two properties fall out, and both are tested: a fold of *no*
//! layers is exactly the engine default, and an empty patch is an identity.
//!
//! ## Why `deny_unknown_fields`
//!
//! A misspelled key in a rules file is the single most likely authoring error,
//! and the default serde behaviour — ignore it — means the author's edit
//! **silently does nothing**. They then tune the number that had no effect,
//! twice, before suspecting the file. Refusing an unknown key turns twenty
//! minutes of confusion into one line of diagnostic. Same reasoning as RLS-A5's
//! rule that a tombstone against a missing ID is a load error and not a no-op.

use ruleset_core::{CombatRules, QuantityError, ResourceError, Ruleset, SLOT_COUNT, StatRules};

use crate::patch_resource::ResourcePatch;
use serde::Deserialize;

/// One layer's contribution to the combat rules.
#[derive(Debug, Clone, Default, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CombatPatch {
    pub hit_base_pm: Option<i64>,
    pub hit_floor_pm: Option<i64>,
    pub hit_ceiling_pm: Option<i64>,
    pub roll_band_lo_pm: Option<i64>,
    pub roll_band_hi_pm: Option<i64>,
    pub elem_mult_pm: Option<i64>,
    pub resist_pm: Option<i64>,
    pub defend_divisor: Option<i64>,
    pub max_hit: Option<i64>,
    pub ko_duration_rounds: Option<u8>,
    pub av_base: Option<i64>,
    pub av_slowed_pm: Option<i64>,
    pub av_hasted_pm: Option<i64>,
    pub av_stunned_pm: Option<i64>,
    pub av_initiator_first_pm: Option<i64>,
}

impl CombatPatch {
    /// Names of the fields this patch leaves undeclared.
    fn missing_fields(&self, out: &mut Vec<&'static str>) {
        // EXHAUSTIVE destructuring — a new field on `CombatPatch` is a compile
        // error here until the completeness check knows about it. Without that,
        // adding a field would silently shrink what "total" means.
        let Self {
            hit_base_pm,
            hit_floor_pm,
            hit_ceiling_pm,
            roll_band_lo_pm,
            roll_band_hi_pm,
            elem_mult_pm,
            resist_pm,
            defend_divisor,
            max_hit,
            ko_duration_rounds,
            av_base,
            av_slowed_pm,
            av_hasted_pm,
            av_stunned_pm,
            av_initiator_first_pm,
        } = self;
        macro_rules! check {
            ($($f:ident),* $(,)?) => { $( if $f.is_none() { out.push(concat!("combat.", stringify!($f))); } )* };
        }
        check!(
            hit_base_pm,
            hit_floor_pm,
            hit_ceiling_pm,
            roll_band_lo_pm,
            roll_band_hi_pm,
            elem_mult_pm,
            resist_pm,
            defend_divisor,
            max_hit,
            ko_duration_rounds,
            av_base,
            av_slowed_pm,
            av_hasted_pm,
            av_stunned_pm,
            av_initiator_first_pm,
        );
    }

    /// Apply this layer over `base`, higher layer wins per field.
    fn apply(&self, base: &mut CombatRules) {
        // EXHAUSTIVE destructuring, no `..` — the same mechanism `canon` uses.
        // Adding a field to `CombatRules` without teaching the patch about it
        // would otherwise leave it silently un-overridable: the loader would
        // accept a file declaring it (or reject it as unknown) and the value
        // would never reach the ruleset. Here it is a compile error.
        let Self {
            hit_base_pm,
            hit_floor_pm,
            hit_ceiling_pm,
            roll_band_lo_pm,
            roll_band_hi_pm,
            elem_mult_pm,
            resist_pm,
            defend_divisor,
            max_hit,
            ko_duration_rounds,
            av_base,
            av_slowed_pm,
            av_hasted_pm,
            av_stunned_pm,
            av_initiator_first_pm,
        } = self;

        macro_rules! set {
            ($($f:ident),* $(,)?) => { $( if let Some(v) = $f { base.$f = *v; } )* };
        }
        set!(
            hit_base_pm,
            hit_floor_pm,
            hit_ceiling_pm,
            roll_band_lo_pm,
            roll_band_hi_pm,
            elem_mult_pm,
            resist_pm,
            defend_divisor,
            max_hit,
            ko_duration_rounds,
            av_base,
            av_slowed_pm,
            av_hasted_pm,
            av_stunned_pm,
            av_initiator_first_pm,
        );
    }
}

/// One layer's contribution to the stat rules.
#[derive(Debug, Clone, Default, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct StatPatch {
    /// Whole-array override (`ReplaceWhole`, RLS-A4). Per-slot override waits
    /// for the slot set to be ruleset-declared (doc 31 R02, still PROPOSED) —
    /// until then a slot has no stable authored NAME to key an override on,
    /// and keying it on the ordinal would bake an engine ordinal into content.
    pub slot_defaults: Option<[i32; SLOT_COUNT]>,
    pub move_base: Option<i32>,
    pub move_speed_per_tile: Option<i32>,
    pub move_max: Option<i32>,
    pub melee_archetype: Option<[i32; SLOT_COUNT]>,
}

impl StatPatch {
    /// Names of the fields this patch leaves undeclared.
    fn missing_fields(&self, out: &mut Vec<&'static str>) {
        let Self { slot_defaults, move_base, move_speed_per_tile, move_max, melee_archetype } =
            self;
        macro_rules! check {
            ($($f:ident),* $(,)?) => { $( if $f.is_none() { out.push(concat!("stats.", stringify!($f))); } )* };
        }
        check!(slot_defaults, move_base, move_speed_per_tile, move_max, melee_archetype);
    }

    fn apply(&self, base: &mut StatRules) {
        let Self { slot_defaults, move_base, move_speed_per_tile, move_max, melee_archetype } =
            self;
        if let Some(v) = slot_defaults {
            base.slot_defaults = *v;
        }
        if let Some(v) = move_base {
            base.move_base = *v;
        }
        if let Some(v) = move_speed_per_tile {
            base.move_speed_per_tile = *v;
        }
        if let Some(v) = move_max {
            base.move_max = *v;
        }
        if let Some(v) = melee_archetype {
            base.melee_archetype = *v;
        }
    }
}

/// One layer of the RLS-A3 stack, as authored.
// `Eq` dropped when `progression_kinds` landed: the authored form carries
// decimals (a rate is `1.5` in TOML) and `f64` has no `Eq`. The DECLARATION
// the patch produces is fully `Eq`, which is what the digest rests on - the
// decimals exist only between the file and `RLS-A7` normalization.
#[derive(Debug, Clone, Default, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct RulesetPatch {
    #[serde(default)]
    pub combat: CombatPatch,
    #[serde(default)]
    pub stats: StatPatch,
    /// Q1 — the L2 identities this layer declares (QTY-A5).
    ///
    /// **The first COLLECTION in the ruleset**, which is what finally gives
    /// RLS-A4's `UnionByIdOverride` a consumer: F2 deferred it with the reason
    /// *"`Ruleset` has none — building it now would be a mechanism with no
    /// consumer"*. It has one.
    ///
    /// `#[serde(default)]` so a layer that declares nothing writes nothing.
    /// Unlike a scalar, an absent collection is not an omission — it says
    /// "this layer adds no quantities", which is a complete statement.
    #[serde(default)]
    pub quantities: Vec<String>,

    /// `Q2` — which of those identities are POOLS.
    ///
    /// A separate list rather than a field on the quantity entry, because
    /// `quantities` is a flat `Vec<String>` an author writes as
    /// `quantities = ["qi", "mana"]` — the shortest possible form for the
    /// common case. Turning every entry into a table so that a minority can
    /// carry pool policy would tax the majority for the minority's benefit.
    #[serde(default)]
    pub resources: Vec<ResourcePatch>,

    /// `PGN-R2b` — the progression kinds this layer declares.
    ///
    /// **Not applied by [`RulesetPatch::apply`].** Every other field here folds
    /// into a `Ruleset` in memory; a progression kind folds into a TABLE that
    /// has to be stored before the `Ruleset` can carry its digest. So these rows
    /// are read by `resolve_and_pin`, which has a store, and `resolve` refuses a
    /// layer that declares them rather than dropping them.
    #[serde(default)]
    pub progression_kinds: Vec<crate::patch_progression::ProgressionKindPatch>,

    /// `M2` — the verbs this layer declares (`CMD-1`).
    ///
    /// A table of tables like `resources`, and for the same reason: the shape is
    /// irreducibly a record, so a flat list would have nowhere to put the
    /// effect. **Ordinals are assigned in declaration order across the merged
    /// stack and never reused** — see `VerbTable`.
    #[serde(default)]
    pub verbs: Vec<crate::patch_verb::VerbPatch>,
}

/// Why a patch could not be folded. Two sources, kept apart so the loader can
/// name the right one in its error rather than flattening both into "invalid".
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PatchError {
    Quantity(QuantityError),
    Resource(ResourceError),
    /// `M2` — a verb row this layer could not declare.
    Verb(crate::patch_verb::VerbPatchError),
}

impl From<QuantityError> for PatchError {
    fn from(e: QuantityError) -> Self {
        Self::Quantity(e)
    }
}

impl From<ResourceError> for PatchError {
    fn from(e: ResourceError) -> Self {
        Self::Resource(e)
    }
}

impl RulesetPatch {
    /// Fold this layer over `base`.
    ///
    /// Fallible only because of `quantities`: a scalar override cannot fail, but
    /// an identity can be malformed, duplicated within one layer, or push the
    /// set past the engine's ordinal capacity.
    pub fn apply(&self, base: &mut Ruleset) -> Result<(), PatchError> {
        self.combat.apply(&mut base.combat);
        self.stats.apply(&mut base.stats);

        // UNION, in layer-priority order. A quantity's ordinal is fixed by where
        // it FIRST appears across the merged stack, so a later layer restating
        // an existing name changes nothing — and there is no verb for removal,
        // which is how `AdditiveOnly` holds by construction.
        let mut seen_here: Vec<&str> = Vec::new();
        for name in &self.quantities {
            if seen_here.contains(&name.as_str()) {
                // WITHIN one layer a repeat is an authoring error, even though
                // ACROSS layers it is a legitimate no-op: one file listing `qi`
                // twice is a mistake nobody meant, and silently collapsing it
                // is how an author never learns their edit did nothing.
                return Err(PatchError::Quantity(QuantityError::Duplicate { name: name.clone() }));
            }
            seen_here.push(name);
            base.quantities.push(name).map_err(PatchError::Quantity)?;
        }

        // Q2 — pools, AFTER the quantities of this layer are in. That order is
        // load-bearing: a layer may declare `qi` and its pool in one file, and
        // resolving the name to an ordinal before the name exists would refuse
        // the most natural thing an author writes.
        for r in &self.resources {
            let ordinal = base.quantities.ordinal_of(&r.quantity).ok_or_else(|| {
                // Reported as UnknownQuantity with the CURRENT count, so the
                // message tells the author how many identities are actually
                // visible at this point in the fold rather than just "no".
                PatchError::Resource(ResourceError::UnknownQuantity {
                    ordinal: u16::MAX,
                    declared: base.quantities.len(),
                })
            })?;
            let decl = r.to_decl(ordinal).map_err(PatchError::Resource)?;
            base.resources.declare(decl, base.quantities.len()).map_err(PatchError::Resource)?;
        }

        // `M2` — verbs, AFTER the pools, for the reason pools come after the
        // quantities: a layer may declare a quantity, its pool and a verb that
        // spends it in one file, and resolving a name before it exists would
        // refuse the most natural thing an author writes.
        //
        // `offer_registry: false` — CMD-11/CMD-12 are PARKED, so a verb
        // targeting another actor is refused rather than shipped unauthorised.
        // It is a parameter and not a constant inside the table so the refusal
        // disappears by itself the day the registry lands.
        for v in &self.verbs {
            let decl = v.to_decl(&base.quantities).map_err(PatchError::Verb)?;
            base.verbs
                .declare(decl, base.quantities.len(), false)
                .map_err(|e| PatchError::Verb(crate::patch_verb::VerbPatchError::Table(e)))?;
        }
        Ok(())
    }

    pub fn is_empty(&self) -> bool {
        self == &Self::default()
    }

    /// Fields this patch does NOT declare, by name.
    ///
    /// **Only the `engine_default` layer is required to be total**, and this is
    /// how that is checked. Every other layer is a partial override by design.
    ///
    /// It exists because the obvious test was HALF a test: `engine_default.toml`
    /// is applied as a patch over `Ruleset::engine_default()`, so comparing the
    /// two catches a field with the WRONG value and is blind to a field that is
    /// MISSING — a deleted line just inherits the `const fn` and the comparison
    /// still passes. The artifact could be half empty and "match the code".
    /// Found by deleting `hit_base_pm` from the artifact and watching the test
    /// stay green.
    pub fn missing_fields(&self) -> Vec<&'static str> {
        let mut out = Vec::new();
        self.combat.missing_fields(&mut out);
        self.stats.missing_fields(&mut out);
        out
    }
}
