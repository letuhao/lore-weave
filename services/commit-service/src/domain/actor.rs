//! `Actor` — the per-combatant state, and the only thing that crosses an
//! island boundary (`Domain::extract`/`install`).
//!
//! ## What `M1` deleted, and why deletion rather than migration
//!
//! This struct held `hp`, `max_hp`, `av`, `stats` and `snapshot`. All five are
//! gone, and the PO's instruction was explicit that they should be **deleted,
//! not ported**:
//!
//! > *"`hp` and friends are old src, rubbish too. Back then we only built to
//! > prove the kernel and the SDK could work, so dealing with them is right."*
//!
//! The distinction is load-bearing. A port keeps the old vocabulary in a new
//! container — `quantity[0] = "hp"` would have satisfied every structural check
//! and changed nothing, because the engine would still be the thing naming the
//! noun. **What is here instead is a hub actor whose numbers this file cannot
//! name**: the laws ask [`crate::domain::HubBinding`] for a ROLE and get an
//! ordinal, and the reality supplies both the name and the value.
//!
//! | was | is |
//! |---|---|
//! | `hp: i64` | the pool bound to `EngineRole::Vital` |
//! | `max_hp: i64` | that pool's declared `CeilingBinding` |
//! | `av: i64` | the pool bound to `EngineRole::Initiative` |
//! | `turn_slots: i64` | the pool bound to `EngineRole::ActionBudget` |
//! | `stats: CombatStats` | `RealityRules::archetype` — **one per reality**, not one per actor |
//! | `snapshot: StatSnapshot` | **nothing.** Written twice, read nowhere, by its own doc-comment's admission |
//!
//! What did NOT move is as deliberate: `defending`, `stance`, `fled`,
//! `knocked_out` and `status` are the `StatusPropose` door, measured at HEAD as
//! **prose with zero implementation**. Making them quantities would invent that
//! door's shape from a milestone that is not about it.

use actor_hub::WriteError;
use game_rules::combat::{AvStatus, Side};
use sim_core::EntityId;

use super::binding::RealityRules;
use super::payload::Stance;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Actor {
    /// **Items 1-4 of the hub's five**: identity, intrinsic quantities,
    /// existence, attachment. Private, so no caller can reach a quantity except
    /// through a role.
    hub: actor_hub::Actor,
    pub defending: bool,
    pub stance: Option<Stance>,
    pub fled: bool,
    /// COMB_001 Q5 — two sides in V1. Win/lose is evaluated per side, so an
    /// actor with no side could never be counted and the encounter could
    /// never end.
    pub side: Side,
    pub status: AvStatus,
    /// COMB_001: KO is REVIVABLE for a bounded number of rounds — it is not
    /// death. `Some(n)` counts rounds remaining before it becomes permanent.
    pub knocked_out: Option<u8>,
}

// QTY-A12 (doc 35 §6.4) — see the rationale on `StatBlock` in `stats.rs`.
//
// `Actor` is THE dense per-actor struct: one per combatant, cloned across every
// `Domain::extract`/`install` island handoff.
//
// REPIN LOG
// * <= 192, 2026-08-02. 80 of those bytes were `snapshot: StatSnapshot`, noted
//   at the time as "written at construction and read nowhere outside tests".
// * <= 160, 2026-08-06 (`M1`). The five deleted fields freed 8 + 8 + 8 + 64 + 80
//   = 168 bytes and the hub's 144 replaced them, so this went DOWN despite
//   gaining a 128-byte quantity array. The array is the honest cost: it is
//   `MAX_DECLARED_QUANTITIES` wide whether a reality declares three pools or
//   thirty, which QTY-A6.1 accepts as the price of ONE ordinal space.
//
// Non-vacuity: every field is inline (a 144-byte hub struct, three one-byte
// enums, two `Option`s of one byte). Adding a field or widening
// MAX_DECLARED_QUANTITIES moves this number. Boxing the hub to keep it small
// would make the assertion 16 bytes for every n and is forbidden for the reason
// `QTY-A6 ⊥ QTY-A12` gives.
const _: () = assert!(core::mem::size_of::<Actor>() <= 160);

impl Actor {
    /// Spawn a combatant into a reality: attach the feature, and take every
    /// quantity's opening value from that reality's own declarations.
    ///
    /// **There is no `max_hp` parameter, and its absence is the milestone.** An
    /// actor's opening vital is `ResourceDecl::base`, which is content; before
    /// `M1` it was a `i64` a caller passed in, so the same reality produced
    /// actors whose ceiling nothing had declared.
    pub fn spawn(rules: &RealityRules, id: EntityId, side: Side) -> Self {
        let mut hub = actor_hub::Actor::new(id);
        hub.attach(rules.hub().registry(), rules.hub().plugin())
            .expect("the combat feature is declared by construction in RealityRules::resolve");
        Self {
            hub,
            defending: false,
            stance: None,
            fled: false,
            side,
            status: AvStatus::default(),
            knocked_out: None,
        }
    }

    /// The SL-A12 **empty case**: `Domain::extract` is TOTAL, so an entity with
    /// no domain rows must still be able to depart, and this is the portable
    /// that encodes "there was nothing here".
    ///
    /// It takes no `rules`, and that is now enforced by the type rather than by
    /// a comment: a hub actor with **nothing attached** has ABSENT quantities,
    /// not zeroed ones. The old version fabricated `hp = 0`, `max_hp = 0` and a
    /// zeroed stat block — numbers that read as a real actor at death's door.
    /// This one cannot be mistaken for an actor, because it has no numbers at
    /// all.
    ///
    /// **Pre-existing hazard, still NOT fixed here:** installing this on the
    /// arrival island materialises a side-B actor, which `outcome_of` counts as
    /// *present but not standing* — i.e. an empty-case handoff can read as a
    /// Victory. Tracked as `D-EMPTY-PORTABLE-SIDE`.
    pub fn absent(id: EntityId) -> Self {
        Self {
            hub: actor_hub::Actor::new(id),
            defending: false,
            stance: None,
            fled: false,
            side: Side::B,
            status: AvStatus::default(),
            knocked_out: None,
        }
    }

    pub fn id(&self) -> EntityId {
        self.hub.id()
    }

    /// The pool an engine law reads, by ROLE. `None` when the quantity is
    /// ABSENT — which for a hub actor means *the feature is not attached*, the
    /// empty-portable case above.
    fn role_value(&self, rules: &RealityRules, q: actor_hub::QuantityOrdinal) -> Option<i32> {
        self.hub.quantity(rules.hub().registry(), q)
    }

    /// **The vital.** `0` for an absent actor, which is the same answer the old
    /// zeroed portable gave and keeps `alive()` total.
    pub fn vital(&self, rules: &RealityRules) -> i64 {
        self.role_value(rules, rules.hub().vital()).unwrap_or(0) as i64
    }

    /// The vital's ceiling — the reality's, not the actor's.
    pub fn vital_ceiling(&self, rules: &RealityRules) -> i64 {
        rules.hub().vital_ceiling() as i64
    }

    /// **Initiative.** LOWEST acts; reset on act (COMB_001 §4).
    pub fn initiative(&self, rules: &RealityRules) -> i64 {
        self.role_value(rules, rules.hub().initiative()).unwrap_or(0) as i64
    }

    /// **The action budget.** IAS-D6's turn economy, as a declared pool rather
    /// than a field: one slot per actor per turn, spent by an action and
    /// refilled at the round boundary.
    pub fn action_budget(&self, rules: &RealityRules) -> i64 {
        self.role_value(rules, rules.hub().action_budget()).unwrap_or(0) as i64
    }

    /// Write a role's pool. **The FEATURE decides the number; the hub carries
    /// it** — see `actor_hub::Actor::set_quantity`.
    ///
    /// An absent actor (the empty portable) refuses every write, and the caller
    /// treats that as "nothing to do" rather than as an error, because
    /// `Domain::apply` is TOTAL: a cross-island substitute arrives with no
    /// preconditions and must never panic.
    fn set_role(
        &mut self,
        rules: &RealityRules,
        q: actor_hub::QuantityOrdinal,
        v: i64,
    ) -> Result<(), WriteError> {
        self.hub.set_quantity(
            rules.hub().registry(),
            rules.hub().plugin(),
            q,
            v.clamp(i32::MIN as i64, i32::MAX as i64) as i32,
        )
    }

    pub fn set_vital(&mut self, rules: &RealityRules, v: i64) {
        let _ = self.set_role(rules, rules.hub().vital(), v);
    }

    pub fn set_initiative(&mut self, rules: &RealityRules, v: i64) {
        let _ = self.set_role(rules, rules.hub().initiative(), v);
    }

    pub fn set_action_budget(&mut self, rules: &RealityRules, v: i64) {
        let _ = self.set_role(rules, rules.hub().action_budget(), v);
    }

    /// **Item 5 — the fold**, reached from the consumer side.
    ///
    /// Aggregate this actor's stored quantities with whatever contributions are
    /// submitted, and answer with the resolved view.
    ///
    /// **Why the hot path does not call this, and why that is not a dodge.**
    /// `QTY-A4` places a pool's `current` on the ACTOR — it is stored state, not
    /// a derived value — so [`Self::vital`] reading the stored slot is the
    /// design rather than a shortcut around it. What the fold is for is
    /// CONTRIBUTIONS: an equipment bonus, a realm raising a ceiling, a status
    /// scaling a number. `M1` declares no contribution rows, so this returns the
    /// stored values, which is the fold's identity case and is what it is
    /// specified to do with an empty submission. It is exposed now because it is
    /// the door `M2`'s `Delta` primitive walks through, and a door with no
    /// caller is the shape this project already has a gate for.
    pub fn resolved(
        &self,
        rules: &RealityRules,
        modifiers: &[actor_hub::ModifierRow],
        derivations: &[actor_hub::DerivationRow],
    ) -> actor_hub::FoldReport {
        self.hub.fold(rules.hub().registry(), modifiers, derivations)
    }

    /// Able to act. A knocked-out actor is NOT alive for this purpose even
    /// though its KO is revivable — it holds a place in the encounter without
    /// holding a turn.
    pub fn alive(&self, rules: &RealityRules) -> bool {
        self.vital(rules) > 0 && !self.fled && self.knocked_out.is_none()
    }
}
