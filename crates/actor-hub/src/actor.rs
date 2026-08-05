//! The hub itself — hub §3, all five things in one struct.
//!
//! ```text
//! 1  IDENTITY             EntityId                      — shipped: sim-core/src/types.rs#EntityId
//! 2  INTRINSIC QUANTITIES [i32; MAX_DECLARED_QUANTITIES] — 128 B; the domain says how to read a slot
//! 3  EXISTENCE            GoneState                     — shipped: entity-existence/src/lib.rs#GoneState
//!                                                         (`source-citation-gate` now holds this: the
//!                                                          `#Symbol` must be DEFINED there, not re-exported)
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
//! **The mutation verb is [`Actor::set_quantity`], and it CARRIES rather than
//! decides.** Hub §3.4b says a quantity *begins* at its declared initial value;
//! **what changes it afterwards — damage, regeneration, expenditure,
//! progression — belongs to the feature that declares it.** That is still true:
//! the hub takes a value it is given, refuses a writer that does not own the
//! quantity, and has no opinion about the number. It is the same shape as
//! [`Actor::set_existence`] — carry the state, adjudicate nothing.
//!
//! **This paragraph used to say there was no such verb**, on the ground that
//! *"every one of those features is unbuilt"*. `M1` built the first one, and
//! the hub's own array is the only place a per-actor number lives — so the
//! alternative to a guarded write was a feature keeping a second copy of the
//! number beside the hub's, which is precisely the second SSOT hub §5 forbids.

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

/// Why a write to a quantity was refused. **Nothing silent**, for the reason
/// [`AttachError`] gives: the alternative to each of these is a number changing
/// where nobody could see that it should not have.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WriteError {
    /// The quantity is **ABSENT** on this actor — the plugin that declares it is
    /// not attached, so there is no slot to write. Distinct from writing zero:
    /// *a village has no hp because combat is not attached.*
    Absent { ordinal: u16 },
    /// The writer is not the plugin that DECLARES this quantity.
    ///
    /// **This is the whole reason the verb takes a writer.** Hub §3.4 makes the
    /// declaring plugin the owner of its quantities' meaning; a second plugin
    /// writing one would be changing a number under semantics it does not own,
    /// and the hub — which knows nothing about what any quantity means — is in
    /// no position to judge whether that was reasonable. So it refuses on
    /// OWNERSHIP, which it can check, rather than on intent, which it cannot.
    ///
    /// `owner` is `None` when no plugin in this reality declares the ordinal at
    /// all; that is reachable only for an ordinal inside the actor's array width
    /// but outside the reality's table, and reporting it as *"you are not the
    /// owner"* with no owner named is more honest than folding it into
    /// [`Absent`](Self::Absent).
    NotOwner { ordinal: u16, owner: Option<u8>, writer: u8 },
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
            // attaching plugin's quantities. **It is now observable, and the
            // test that observes it is
            // `attaching_a_SECOND_plugin_does_not_reset_the_first`.**
            //
            // This comment used to say the opposite, and recording the
            // transition is the point: a review measured that relaxing this to
            // `.is_some()` reddened nothing, because the hub had no verb that
            // moved a quantity after attach — so re-initialising an
            // already-attached plugin's quantity wrote back the value that was
            // already there. It said the guard *"becomes observable the moment
            // any feature can change one"*. `set_quantity` is that moment, and
            // the prediction held on the first try: relaxing the condition now
            // reverts a wounded actor to full health when an unrelated plugin
            // attaches. `NV-4` in its benign direction, discharged.
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

    /// **Write an intrinsic quantity — the verb `M1` needed and the door `M2`'s
    /// `Delta` primitive goes through.**
    ///
    /// The hub CARRIES the value; the declaring feature decides it. Refuses a
    /// write to an absent quantity and a write by a plugin that does not own the
    /// ordinal — see [`WriteError`] for why ownership is the thing it can check.
    ///
    /// **No clamping, deliberately.** A ceiling is `ResourceDecl::ceiling`,
    /// which is the RULESET's and is bound to a derived stat a realm can raise
    /// (`QTY-A8`) — the hub cannot see it and must not guess one. Clamping to a
    /// bound it invented would be the hub deciding a number's meaning, which is
    /// the one thing it exists not to do. The caller clamps.
    pub fn set_quantity(
        &mut self,
        registry: &HubRegistry,
        by: PluginOrdinal,
        q: QuantityOrdinal,
        value: i32,
    ) -> Result<(), WriteError> {
        match registry.owner_of(q) {
            Some(owner) if owner == by => {}
            owner => {
                return Err(WriteError::NotOwner {
                    ordinal: q.get(),
                    owner: owner.map(|o| o.get()),
                    writer: by.get(),
                })
            }
        }
        // Ownership is not presence: the declaring plugin may own the ordinal in
        // this reality and still not be attached to THIS actor. Checked
        // separately so the two refusals stay distinguishable — a caller
        // debugging "my damage did nothing" needs to know which it was.
        if !registry.is_present(self.attached, q) {
            return Err(WriteError::Absent { ordinal: q.get() });
        }
        self.quantities[q.index()] = value;
        Ok(())
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
