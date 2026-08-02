//! The hub itself — hub §3, all five things in one struct.
//!
//! ```text
//! 1  IDENTITY             EntityId                      — shipped: sim-core/src/types.rs:17
//! 2  INTRINSIC QUANTITIES [i32; MAX_DECLARED_QUANTITIES] — 128 B; the domain says how to read a slot
//! 3  EXISTENCE            GoneState                     — shipped: dp-kernel/src/entity_status.rs
//! 4  ATTACHMENT           PluginSet — a u32 bitmask over plugin ordinals
//! 5  THE FOLD             aggregate contributions, and know NOTHING about what they mean
//! ```
//!
//! ## What is NOT here, and why each absence is a decision
//!
//! **No name, no kind, no template, no position, no owner, no inventory.** The
//! scope test decides every one of them:
//!
//! > **身外之物** — strip the actor naked and move them to another world. What
//! > travels? Body, pools, statuses, lifespan, memories travel. Money, items,
//! > rank, reputation, position stay.
//!
//! **No `granted` field.** Quantity `q` is present exactly when the plugin that
//! declares it is attached — one fact, nothing to keep in step (hub §3.4).
//!
//! **No spawn, no archetype, no *"what kind of thing is this"*.** `D-283` and
//! `D-289` ruled these **PREMATURE**, not missing: spawn needs a place to spawn
//! into, a template to spawn from, and a reason to spawn, and **measured, none
//! of the three exists** — no `SpawnPoint` anywhere in `crates/` or `services/`,
//! `struct Place`/`struct Tile` only in `tilemap-service`, and the only
//! `Archetype` type in `world-gen`. Writing them from feature #1's chair would
//! be inventing the second feature's requirements.
//!
//! **No mutation verb for a quantity beyond attachment.** Hub §3.4b says a
//! quantity *begins* at its declared initial value; **what changes it afterwards
//! — damage, regeneration, expenditure, progression — belongs to the feature
//! that declares it**, and every one of those features is unbuilt.

use entity_existence::GoneState;
use ruleset_core::MAX_DECLARED_QUANTITIES;
use sim_core::EntityId;

use crate::fold::fold;
use crate::report::FoldReport;
use crate::ordinal::{PluginOrdinal, QuantityOrdinal};
use crate::plugin_set::PluginSet;
use crate::registry::HubRegistry;
use crate::rows::{DerivationRow, ModifierRow};

/// Why an attachment was refused. **Nothing silent** — the alternative to each
/// of these is a state change nobody asked for.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AttachError {
    /// This reality never declared that plugin, so there is nothing to attach.
    NotDeclared { plugin: u8 },
    /// Already attached. **Refused rather than treated as a no-op**, because
    /// attaching initialises the plugin's quantities and a silent second attach
    /// would reset a being's state to its birth values.
    AlreadyAttached { plugin: u8 },
}

/// Why a detachment was refused.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DetachError {
    /// The plugin is not attached, so there is nothing to detach. See
    /// [`Actor::detach`] for why this is refused rather than ignored.
    NotAttached { plugin: u8 },
}

/// A being.
///
/// `Copy` is deliberately NOT derived: an actor is 144 bytes of state and an
/// accidental copy is a second SSOT for one being's quantities — the exact
/// failure hub §5 names (*"what is forbidden is a plugin's data living inside
/// the actor's struct… only that creates a second SSOT"*). `Clone` is explicit
/// where a caller genuinely wants a snapshot.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Actor {
    id: EntityId,
    existence: GoneState,
    attached: PluginSet,
    quantities: [i32; MAX_DECLARED_QUANTITIES],
}

impl Actor {
    /// A being with an identity, live, and **nothing attached** — so it has no
    /// quantities at all. Not zeroed quantities: **absent** ones.
    pub fn new(id: EntityId) -> Self {
        Self {
            id,
            existence: GoneState::Active,
            attached: PluginSet::EMPTY,
            quantities: [0; MAX_DECLARED_QUANTITIES],
        }
    }

    pub fn id(&self) -> EntityId {
        self.id
    }

    /// **Platform existence — *"is this row reachable?"*** Fiction existence,
    /// alive or dead, is a STATUS and is not here: two beings can both be
    /// `Active` while one is a corpse (hub §3.3).
    pub fn existence(&self) -> GoneState {
        self.existence
    }

    /// Set the platform lifecycle state.
    ///
    /// **The hub does not adjudicate this transition.** `GoneState` ships with a
    /// precedence lattice and terminal states, and *who* may move an entity to
    /// `Dropped` or `UserErased` is the platform's — a GDPR erasure and a reality
    /// archive both write it. The hub carries the field; it does not own the
    /// policy, and it does not pretend to by refusing a transition it has no
    /// basis to judge.
    pub fn set_existence(&mut self, state: GoneState) {
        self.existence = state;
    }

    pub fn attached(&self) -> PluginSet {
        self.attached
    }

    /// Attach a plugin, initialising every quantity it declares to that
    /// plugin's own declared initial value — **hub §3.4b, the hub's whole
    /// obligation.**
    ///
    /// The hub READS `initial`; it does not author it.
    pub fn attach(&mut self, registry: &HubRegistry, p: PluginOrdinal) -> Result<(), AttachError> {
        if !registry.declared_plugins().contains(p) {
            return Err(AttachError::NotDeclared { plugin: p.get() });
        }
        if self.attached.contains(p) {
            return Err(AttachError::AlreadyAttached { plugin: p.get() });
        }
        self.attached = self.attached.attach(p);
        for raw in 0..MAX_DECLARED_QUANTITIES as u16 {
            let Some(q) = QuantityOrdinal::new(raw) else { continue };
            // `owner_of(q) == Some(p)` is what makes this initialise ONLY the
            // attaching plugin's quantities. **It is not observable today**, and
            // saying so is more honest than a test name that claims otherwise: a
            // review measured that relaxing it to `.is_some()` reddens nothing,
            // because the hub has no verb that moves a quantity after attach
            // (its own seam `S-15`), so re-initialising an already-attached
            // plugin's quantity writes the value that is already there. It
            // becomes observable the moment any feature can change one — which
            // is `NV-4` in its benign direction, and the reason this is a
            // comment rather than a claim.
            if registry.owner_of(q) == Some(p)
                && let Some(v) = registry.initial_value(self.attached, q)
            {
                self.quantities[q.index()] = v;
            }
        }
        Ok(())
    }

    /// Detach a plugin. Its quantities become ABSENT again by construction,
    /// because presence is derived from the attachment set.
    ///
    /// **Refuses a plugin that is not attached**, rather than returning quietly.
    /// A review caught this as the one silent verb on the type: `attach` refuses
    /// two cases with a `Result` whose doc says *"nothing silent — the
    /// alternative to each of these is a state change nobody asked for"*, and
    /// `detach` accepted anything. Detaching what was never attached is a caller
    /// bug — a wrong ordinal, a double detach — and swallowing it hides exactly
    /// the mistake the `Result` on the other verb exists to surface.
    ///
    /// **The stored bytes are deliberately left alone**, and that is not an
    /// oversight: whether a value survives a detach/re-attach is `M-2`, ruled
    /// **PREMATURE** by `D-289` — *detach which plugin, when plugin #2 does not
    /// exist?* Re-attaching re-initialises from the declaration
    /// ([`Actor::attach`]), so the observable behaviour today is "begins again
    /// at the declared initial", and the question of a survivable value is
    /// answerable the moment there is a second plugin to ask it about.
    pub fn detach(&mut self, p: PluginOrdinal) -> Result<(), DetachError> {
        if !self.attached.contains(p) {
            return Err(DetachError::NotAttached { plugin: p.get() });
        }
        self.attached = self.attached.detach(p);
        Ok(())
    }

    /// The actor's stored intrinsic value for a quantity — `None` when the
    /// quantity is **ABSENT**, never `Some(0)`.
    ///
    /// > *A village has no hp because combat is not attached; a stone has no qi
    /// > because cultivation is not.*
    pub fn quantity(&self, registry: &HubRegistry, q: QuantityOrdinal) -> Option<i32> {
        registry
            .is_present(self.attached, q)
            .then(|| self.quantities[q.index()])
    }

    /// The raw slot array, for the fold. Private state; the accessor above is
    /// the one that respects absence.
    pub(crate) fn stored(&self) -> &[i32; MAX_DECLARED_QUANTITIES] {
        &self.quantities
    }

    /// **Item 5 — the fold.** Aggregate the contributions of attached plugins,
    /// knowing nothing about what any of them mean.
    pub fn fold(
        &self,
        registry: &HubRegistry,
        modifiers: &[ModifierRow],
        derivations: &[DerivationRow],
    ) -> FoldReport {
        fold(self.attached, self.stored(), registry, modifiers, derivations)
    }
}

/// **`M-14` — the `size_of` assertion the completeness lens found missing**, in
/// a repo where four such assertions ship and one carries a four-entry repin log.
///
/// ## Why this one is not vacuous
///
/// The failure shape `docs/standards/non-vacuity.md` names first is *"the
/// subject cannot vary"* — a `size_of` assertion on a **boxed** payload is 16
/// bytes for every possible content, so it asserts the pointer, not the data.
/// Every field here is **inline**: an `EntityId(u64)`, a one-byte enum, a `u32`
/// mask and a `[i32; 32]` array. Add a field, widen `MAX_DECLARED_QUANTITIES`,
/// or replace the inline array with a `Vec`, and this number moves.
///
/// ## The repin log
///
/// | when | value | why |
/// |---|---|---|
/// | 2026-08-02 | **144** | first pin. 8 (`EntityId`) + 1 (`GoneState`) + 4 (`PluginSet`) + 128 (`[i32; 32]`) = 141, padded to 144 by the `u64`'s 8-byte alignment |
///
/// The neighbouring budget is `actor.rs:62`'s `size_of::<Actor>() <= 192` in
/// `commit-service` — a **different** `Actor`, the shipped combat one. Both
/// numbers are stated because the hub's 128-byte array is the whole reason the
/// design chose one `i32` per ordinal over a richer per-quantity struct.
const _: () = assert!(
    core::mem::size_of::<Actor>() == 144,
    "the hub's Actor changed size. It is 8 (EntityId) + 1 (GoneState) + 4 (PluginSet) + \
     128 ([i32; MAX_DECLARED_QUANTITIES]) padded to 144. If this is deliberate — a new field, \
     a wider quantity ceiling — repin it AND add a row to the repin log above, because the \
     per-actor cost is the argument the whole quantity representation rests on."
);

#[cfg(test)]
mod tests {
    use super::*;
    use crate::registry::{PluginDecl, QuantityDecl};
    use crate::rows::FoldLayer;
    use ruleset_core::QuantityTable;

    fn q(raw: u16) -> QuantityOrdinal {
        QuantityOrdinal::new(raw).unwrap()
    }

    fn p(raw: u8) -> PluginOrdinal {
        PluginOrdinal::new(raw).unwrap()
    }

    fn registry() -> HubRegistry {
        let table = QuantityTable::assign(&["hp", "qi", "speed"]).unwrap();
        HubRegistry::build(
            &table,
            &[
                PluginDecl {
                    ordinal: p(0),
                    quantities: vec![
                        QuantityDecl { ordinal: q(0), initial: 100 },
                        QuantityDecl { ordinal: q(2), initial: 30 },
                    ],
                    fold_layers: vec![FoldLayer(10)],
                },
                PluginDecl {
                    ordinal: p(1),
                    quantities: vec![QuantityDecl { ordinal: q(1), initial: 7 }],
                    fold_layers: vec![FoldLayer(20)],
                },
            ],
        )
        .unwrap()
    }

    #[test]
    fn a_new_actor_has_identity_is_live_and_has_no_quantities() {
        let r = registry();
        let a = Actor::new(EntityId(42));
        assert_eq!(a.id(), EntityId(42));
        assert_eq!(a.existence(), GoneState::Active);
        assert!(a.attached().is_empty());
        for raw in 0..3u16 {
            assert_eq!(
                a.quantity(&r, q(raw)),
                None,
                "an actor with nothing attached has ABSENT quantities, not zeroed ones"
            );
        }
    }

    /// **Hub §3.4b.** Attaching initialises from the plugin's own declaration,
    /// and only the quantities that plugin declares.
    #[test]
    fn attaching_initialises_exactly_its_own_quantities() {
        let r = registry();
        let mut a = Actor::new(EntityId(1));
        a.attach(&r, p(0)).unwrap();
        assert_eq!(a.quantity(&r, q(0)), Some(100));
        assert_eq!(a.quantity(&r, q(2)), Some(30));
        assert_eq!(a.quantity(&r, q(1)), None, "qi belongs to a plugin that is not attached");

        a.attach(&r, p(1)).unwrap();
        assert_eq!(a.quantity(&r, q(1)), Some(7));
    }

    #[test]
    fn attaching_an_undeclared_plugin_is_refused() {
        let r = registry();
        let mut a = Actor::new(EntityId(1));
        assert_eq!(a.attach(&r, p(9)), Err(AttachError::NotDeclared { plugin: 9 }));
        assert!(a.attached().is_empty());
    }

    /// A second attach would silently reset a being to its birth values, so it
    /// is refused rather than swallowed.
    #[test]
    fn attaching_twice_is_refused_not_a_silent_reset() {
        let r = registry();
        let mut a = Actor::new(EntityId(1));
        a.attach(&r, p(0)).unwrap();
        assert_eq!(a.attach(&r, p(0)), Err(AttachError::AlreadyAttached { plugin: 0 }));
    }

    #[test]
    fn detaching_makes_its_quantities_absent_again() {
        let r = registry();
        let mut a = Actor::new(EntityId(1));
        a.attach(&r, p(0)).unwrap();
        a.attach(&r, p(1)).unwrap();
        a.detach(p(1)).unwrap();
        assert_eq!(a.quantity(&r, q(1)), None);
        assert_eq!(a.quantity(&r, q(0)), Some(100), "detaching one plugin left the other alone");
    }

    /// The other half of *"nothing silent"*: detaching what was never
    /// attached is a caller bug, and it is reported rather than swallowed.
    #[test]
    fn detaching_something_that_is_not_attached_is_refused() {
        let r = registry();
        let mut a = Actor::new(EntityId(1));
        assert_eq!(a.detach(p(0)), Err(DetachError::NotAttached { plugin: 0 }));
        a.attach(&r, p(0)).unwrap();
        assert_eq!(a.detach(p(0)), Ok(()));
        assert_eq!(a.detach(p(0)), Err(DetachError::NotAttached { plugin: 0 }));
    }

    #[test]
    fn existence_is_platform_state_and_is_carried_not_adjudicated() {
        let mut a = Actor::new(EntityId(1));
        assert!(a.existence().is_live());
        a.set_existence(GoneState::Archived);
        assert!(!a.existence().is_live());
        assert!(!a.existence().is_terminal());
        a.set_existence(GoneState::UserErased);
        assert!(a.existence().is_terminal());
    }

    /// The five things, folded — item 5 reached through items 1..4.
    #[test]
    fn an_actor_folds_its_attached_plugins_contributions() {
        let r = registry();
        let mut a = Actor::new(EntityId(1));
        a.attach(&r, p(0)).unwrap();
        let rows = [ModifierRow {
            target: q(0),
            op: ruleset_core::ModifierOp::Flat(50),
            source: p(0),
            fold_layer: FoldLayer(10),
        }];
        let out = a.fold(&r, &rows, &[]);
        assert_eq!(out.value(q(0)), Some(150));
        assert_eq!(out.value(q(1)), None);
    }

    /// The pinned size, asserted at runtime as well so the number appears in a
    /// test report and not only in a compile error.
    #[test]
    fn the_actor_is_the_pinned_size() {
        assert_eq!(core::mem::size_of::<Actor>(), 144);
    }
}
