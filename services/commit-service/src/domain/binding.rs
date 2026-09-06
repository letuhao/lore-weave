//! **`M1` — how a reality's declared pools become an actor's quantities.**
//!
//! This file is the whole of the consumer half of the actor hub. It reads
//! `ruleset_core`'s two declaration tables and produces:
//!
//! ```text
//! QuantityTable  (names, hashed, author-assigned)  ->  HubRegistry
//! ResourceTable  (pools + their EngineRole)        ->  the ordinals the laws read
//! ```
//!
//! ## The one property that makes this milestone worth doing
//!
//! > **No quantity NAME appears anywhere in this file, or in any file that
//! > reads it.** The laws ask for a ROLE — *the pool whose exhaustion ends
//! > participation* — and the reality answers with an ordinal. An author may
//! > call their vital `hp`, `qi`, `blood` or `氣`; the engine never learns which.
//!
//! That is `D-2` (*the engine closes on MECHANISM, the manifest closes on
//! VOCABULARY*) as a compile-time fact rather than an intention, and
//! `scripts/engine-vocabulary-gate.py` is what keeps it one.
//!
//! ## Why every absence here is a REFUSAL and never a default
//!
//! A reality that declares no pool for a role leaves an engine law with no
//! number. The tempting fallback — treat it as zero, or skip the law — produces
//! a fight that can never end, discovered by a player rather than by an
//! operator. So [`RealityRules::resolve`] refuses at ISLAND CONSTRUCTION, where
//! the message reaches whoever authored the reality.

use actor_hub::{
    FoldLayer, HubRegistry, PluginDecl, PluginOrdinal, QuantityDecl, QuantityOrdinal,
    RegistryError,
};
use game_rules::combat::CombatStats;
use ruleset_core::{CeilingBinding, EngineRole, Ruleset};

/// The plugin ordinal `M1`'s single feature occupies.
///
/// **One plugin, because there is one feature.** The hub's whole design is that
/// plugin #2 costs nothing extra; inventing its ordinal here from feature #1's
/// chair is what `D-283`/`D-289` ruled premature for spawn and archetypes, and
/// the same answer applies.
const COMBAT_PLUGIN: u8 = 0;

/// The single fold layer this feature declares.
///
/// A layer is a shared ORDERING POSITION (hub §4). One feature contributing at
/// one position needs exactly one, and the hub refuses a row naming a layer
/// nobody declared (`U-7`) — so this is load-bearing rather than ceremonial.
const BASE_LAYER: u8 = 0;

/// Why a reality could not be bound to the engine's laws.
///
/// Every variant is a **boot** refusal. None of them can arise mid-encounter,
/// which is the point: the alternative to refusing here is refusing on the
/// first strike, or not refusing at all.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BindingError {
    /// No pool in this reality claims an engine role a law needs.
    ///
    /// Carries the role's authored spelling so the message can tell an author
    /// exactly what to write, rather than naming an internal enum variant.
    RoleUnbound { role: &'static str },
    /// A declared pool names a quantity ordinal outside the reality's own
    /// table, or two pools claim one quantity. Both are already refused by
    /// `ResourceTable::declare`; this arm exists because `HubRegistry::build`
    /// re-checks against the quantity table and its refusal is the one that
    /// would fire if the two tables ever disagreed.
    Registry(RegistryError),
    /// A quantity ordinal that does not fit the hub's ordinal space.
    ///
    /// Reachable only if `MAX_DECLARED_QUANTITIES` and the hub's
    /// `QuantityOrdinal` width ever disagree — which is exactly the drift a
    /// refusal should catch rather than an `unwrap` in a boot path.
    OrdinalTooWide { ordinal: u16 },
    /// A declared verb names a quantity that is not a declared POOL.
    ///
    /// **`VerbTable::declare` cannot catch this** — it validates against the
    /// QUANTITY table, and a quantity becomes readable on an actor only if it
    /// also has a `[[resources]]` row, because the hub plugin is built from the
    /// RESOURCE table. A verb naming a pool-less quantity therefore passed every
    /// build check and reached the substrate, where the write silently did
    /// nothing and **an `Acted` fact was committed anyway, carrying a fabricated
    /// `left`.**
    ///
    /// A silence would have been bad; a committed LIE is worse, and it is the
    /// `QTY-Q5` class that `VerbError::UnknownQuantity`'s own doc says this tier
    /// exists to refuse. Found by a cold-start reviewer, not by the suite.
    VerbNamesUndeclaredPool { verb: String, ordinal: u16 },
    /// A declared verb names the pool bound to `EngineRole::ActionBudget`, in
    /// ANY of its three positions.
    ///
    /// **The engine owns that pool outright** — `IAS-D6`'s turn economy spends
    /// it on every action, which is what stops a driver acting twice in a turn.
    /// All three positions are refused, because each breaks it differently:
    ///
    /// | position | what it did before this refusal |
    /// |---|---|
    /// | `effect` | **unlimited free actions.** The engine deducted 1 and the verb's effect added it back; four submissions with no turn boundary left the budget at 1 |
    /// | `spend` | charged TWICE for one action |
    /// | `requires` | a verb that can NEVER fire — the engine's deduction runs first, so the threshold is already unmet on the verb's own first submission |
    ///
    /// **The first version of this refusal covered only `spend`, and cited the
    /// `requires` incident as its reason.** The symptom it quoted
    /// (`RequirementUnmet` on the first submission) cannot come from a spend at
    /// all — that path returns `CannotAfford`. It was aimed at the wrong arm of
    /// the bug it was written for, and the free-action case was argued away in
    /// prose as *"the EFFECT side is deliberately not refused"* — sound for the
    /// INITIATIVE pool, where a haste effect is exactly what a declared verb is
    /// for, and false for this one.
    VerbTouchesEngineBudget { verb: String, position: &'static str },
}

impl std::fmt::Display for BindingError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::RoleUnbound { role } => write!(
                f,
                "no declared pool claims the engine role `{role}`. A law reads that pool, \
                 and running without it would produce an encounter that cannot resolve - \
                 discovered by a player rather than by you. Add `role = \"{role}\"` to one \
                 of this reality's resource rows"
            ),
            Self::Registry(e) => write!(f, "the hub registry refused this reality: {e:?}"),
            Self::OrdinalTooWide { ordinal } => write!(
                f,
                "quantity ordinal {ordinal} is outside the hub's ordinal space"
            ),
            Self::VerbNamesUndeclaredPool { verb, ordinal } => write!(
                f,
                "verb `{verb}` names quantity ordinal {ordinal}, which this reality declares                  as an identity but NOT as a pool. An actor holds a number only for a                  declared pool, so the verb would write nothing and commit a fact saying it                  had. Add a `[[resources]]` row for it"
            ),
            Self::VerbTouchesEngineBudget { verb, position } => write!(
                f,
                "verb `{verb}`'s `{position}` names the pool bound to the `action_budget`                  role. The engine owns that pool: IAS-D6 spends it on every action, which is                  what stops a driver acting twice in a turn. An `effect` on it grants                  unlimited free actions, a `spend` charges twice, and a `requires` can never                  be met. Use a pool of your own"
            ),
        }
    }
}

impl std::error::Error for BindingError {}

/// Which ordinal each engine law reads, resolved once per reality.
///
/// **Three roles, three laws, and each one is consumed by a law in this same
/// crate** — which is the test `ResourceDecl::role`'s doc sets for earning a
/// hashed field, and the test `deps`/`tags` were refused for failing.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HubBinding {
    registry: HubRegistry,
    plugin: PluginOrdinal,
    layer: FoldLayer,
    vital: QuantityOrdinal,
    vital_ceiling: i32,
    initiative: QuantityOrdinal,
    action_budget: QuantityOrdinal,
    action_budget_base: i32,
}

impl HubBinding {
    pub fn registry(&self) -> &HubRegistry {
        &self.registry
    }

    /// The feature that owns every quantity here — the writer every
    /// `set_quantity` passes.
    pub fn plugin(&self) -> PluginOrdinal {
        self.plugin
    }

    pub fn layer(&self) -> FoldLayer {
        self.layer
    }

    /// **The pool whose exhaustion ends this actor's participation.**
    pub fn vital(&self) -> QuantityOrdinal {
        self.vital
    }

    /// The vital's ceiling, resolved through the reality's stat block if it is
    /// bound to a slot (`QTY-A8` — a realm RAISES a ceiling), or read directly
    /// if it is a constant.
    pub fn vital_ceiling(&self) -> i32 {
        self.vital_ceiling
    }

    /// **The pool that orders turns.**
    pub fn initiative(&self) -> QuantityOrdinal {
        self.initiative
    }

    /// **The pool an action spends to be taken at all.**
    pub fn action_budget(&self) -> QuantityOrdinal {
        self.action_budget
    }

    /// What a turn boundary refills the action budget to — the reality's
    /// declared `base`, not a hardcoded `1`.
    pub fn action_budget_base(&self) -> i32 {
        self.action_budget_base
    }
}

/// A reality's rules **plus** what the laws need in order to read them.
///
/// This is the island's `Domain::Rules`. The binding is DERIVED from the
/// ruleset, so it is not a second source of truth and it never enters the
/// digest — [`Self::digest`] delegates, and `RLS-A13` is unchanged.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RealityRules {
    rules: Ruleset,
    hub: HubBinding,
    /// The reality's resolved archetype, computed once.
    ///
    /// **This was a per-ACTOR field until `M1` measured it.** Every actor's
    /// `stats` came from `CombatStats::archetype_melee(&rules.stats, max_hp)`,
    /// so the only per-actor difference was `CombatStats::max_hp` — and **no
    /// law reads that field.** `resolve_attack`, `action_value` and
    /// `evaluate_outcome` never touch it. So the per-actor copy differed from
    /// its neighbours in a value nothing consumed: 64 bytes per combatant of
    /// duplicated ruleset.
    archetype: CombatStats,
}

impl RealityRules {
    /// Resolve a ruleset into runnable rules, or refuse with a reason an author
    /// can act on.
    pub fn resolve(rules: Ruleset) -> Result<Self, BindingError> {
        // Every declared pool becomes a quantity this feature owns, initialised
        // to the pool's declared `base` — which `ResourceDecl::base` already
        // documents as *"the value an actor starts at"*, the same sentence
        // `QuantityDecl::initial` carries. Two declarations of one fact, joined
        // here rather than restated.
        let mut quantities = Vec::with_capacity(rules.resources.len());
        for row in rules.resources.rows() {
            let ordinal = QuantityOrdinal::new(row.quantity)
                .ok_or(BindingError::OrdinalTooWide { ordinal: row.quantity })?;
            quantities.push(QuantityDecl { ordinal, initial: row.base });
        }

        let plugin = PluginOrdinal::new(COMBAT_PLUGIN).expect("plugin ordinal 0 is in range");
        let layer = FoldLayer(BASE_LAYER);
        let registry = HubRegistry::build(
            &rules.quantities,
            &[PluginDecl { ordinal: plugin, quantities, fold_layers: vec![layer] }],
        )
        .map_err(BindingError::Registry)?;

        let role_ordinal = |role: EngineRole| -> Result<QuantityOrdinal, BindingError> {
            let row = rules
                .resources
                .by_role(role)
                .ok_or(BindingError::RoleUnbound { role: role.as_str() })?;
            QuantityOrdinal::new(row.quantity)
                .ok_or(BindingError::OrdinalTooWide { ordinal: row.quantity })
        };

        let vital = role_ordinal(EngineRole::Vital)?;
        let initiative = role_ordinal(EngineRole::Initiative)?;
        let action_budget = role_ordinal(EngineRole::ActionBudget)?;

        // The archetype resolved through the real DF07 path, so the defaults,
        // the clamps and the MoveRange derivation are exercised even by a bare
        // NPC — the property `CombatStats::archetype_melee` was written to hold.
        //
        // Its `max_hp` argument is the VITAL'S CEILING, which is where that
        // number now comes from: a per-actor constructor parameter before `M1`,
        // a declared `CeilingBinding` after it.
        let vital_row = rules
            .resources
            .by_role(EngineRole::Vital)
            .ok_or(BindingError::RoleUnbound { role: EngineRole::Vital.as_str() })?;
        let vital_ceiling = match vital_row.ceiling {
            // A slot ceiling is resolved by asking the archetype, which is the
            // `QTY-A8` shape: a realm raises the SLOT and the pool's ceiling
            // follows, rather than the pool carrying an editable number.
            CeilingBinding::Slot(s) => {
                CombatStats::archetype_slot(&rules.stats, s)
            }
            CeilingBinding::Fixed(v) => v,
        };

        let action_budget_base = rules
            .resources
            .by_role(EngineRole::ActionBudget)
            .expect("resolved above")
            .base;

        // Every quantity a verb names must be a declared POOL, and none of them
        // may be the engine's own turn budget. Checked HERE because this is the
        // only place that knows the verb table, the resource table AND the role
        // bindings — `VerbTable::declare` sees only the QUANTITY table, which is
        // exactly why it let a pool-less quantity through.
        for v in rules.verbs.rows() {
            let named = [
                (Some(v.effect.quantity), "effect"),
                (v.spend.map(|s| s.quantity), "spend"),
                (v.requires.map(|r| r.quantity), "requires"),
            ];
            for (q, position) in named {
                let Some(q) = q else { continue };
                if rules.resources.for_quantity(q).is_none() {
                    return Err(BindingError::VerbNamesUndeclaredPool {
                        verb: v.name.as_str().to_string(),
                        ordinal: q,
                    });
                }
                if q == action_budget.get() {
                    return Err(BindingError::VerbTouchesEngineBudget {
                        verb: v.name.as_str().to_string(),
                        position,
                    });
                }
            }
        }

        let archetype = CombatStats::archetype_melee(&rules.stats, vital_ceiling as i64);

        Ok(Self {
            rules,
            hub: HubBinding {
                registry,
                plugin,
                layer,
                vital,
                vital_ceiling,
                initiative,
                action_budget,
                action_budget_base,
            },
            archetype,
        })
    }

    /// The shipped **proving-ground** preset, resolved.
    ///
    /// One constructor for the demo binary and every domain test, so a test
    /// cannot quietly run on a reality the binary does not. It goes through the
    /// real layer stack (`ruleset_loader::proving_ground`) rather than building
    /// a `Ruleset` by hand, which is the difference between exercising the
    /// authoring path and asserting against a fixture that bypasses it.
    ///
    /// Panics only on a defect in the shipped artifact itself — a preset that
    /// does not parse or does not bind its roles is a broken build, not a
    /// runtime condition a caller could handle.
    pub fn proving_ground() -> Self {
        let rules = ruleset_loader::proving_ground()
            .expect("the shipped proving-ground preset resolves");
        Self::resolve(rules).expect("the shipped proving-ground preset binds every engine role")
    }

    pub fn rules(&self) -> &Ruleset {
        &self.rules
    }

    pub fn hub(&self) -> &HubBinding {
        &self.hub
    }

    /// **The declared bounds of a pool, resolved** — `[min, ceiling]`.
    ///
    /// `None` when the ordinal is not a declared pool, which after
    /// [`BindingError::VerbNamesUndeclaredPool`] no declared verb can name.
    ///
    /// **This exists because `EffectRow::amount`'s doc claimed a clamp that did
    /// not happen.** It said *"the engine clamps against the pool's own declared
    /// bounds"*, and the substrate did `(before + amount).max(0)` — a hardcoded
    /// floor of zero that ignored `ResourceDecl::min` and had no ceiling at all.
    /// A cold-start reviewer drove a `vitality` of ceiling 100 to **15100**.
    pub fn pool_bounds(&self, ordinal: u16) -> Option<(i32, i32)> {
        let row = self.rules.resources.for_quantity(ordinal)?;
        let ceiling = match row.ceiling {
            CeilingBinding::Slot(s) => CombatStats::archetype_slot(&self.rules.stats, s),
            CeilingBinding::Fixed(v) => v,
        };
        Some((row.min, ceiling))
    }

    /// The reality's resolved combat archetype — one block, not one per actor.
    pub fn archetype(&self) -> &CombatStats {
        &self.archetype
    }

    /// `RLS-A13`, unchanged: the pin is over the RULES, and the binding is
    /// derived from them. A digest that covered the binding would move when a
    /// refactor changed how the binding is computed, which is exactly the
    /// *"rules change that changes no rule"* `state.rs` deleted a field to
    /// avoid.
    pub fn digest(&self) -> sim_core::RulesetDigest {
        self.rules.digest()
    }
}
