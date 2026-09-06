//! The declaration registry — **`M-11`, the thing none of the three layers
//! owned**, so the hub owns it.
//!
//! The completeness lens found that *plugin → quantity → fold layer* had no
//! home: `ruleset_core::QuantityTable` stores **names only**, the substrate
//! contract stops at ordinals, and no plugin exists yet to own the mapping. It
//! is the hub's, because the hub is the thing that must know **which plugin
//! declares which ordinal** in order to answer hub §3.4b:
//!
//! > **Every quantity of every attached plugin begins at the initial value that
//! > plugin's own declaration supplies. A quantity of an unattached plugin is
//! > ABSENT, not zero.**
//!
//! **The hub READS a declaration; it does not author one.** It has no opinion
//! about what a melee fighter starts with, and `ResourceDecl.base` is already
//! documented as *"the value an actor starts at"*.
//!
//! ## What is refused, and when
//!
//! Two different times, and the distinction is load-bearing:
//!
//! | when | what | verb |
//! |---|---|---|
//! | **build** — once, at reality creation | two plugins claiming one ordinal, an ordinal past the reality's declared table, a duplicate plugin | the registry is **not built** |
//! | **submission** — per row, per fold | an undeclared target, an undeclared fold layer, a zero divisor, a contradictory bound | **the ROW is refused**, the fold continues |
//!
//! **A malformed row refuses the ROW, never the fold** (`M-5`). Refusing the
//! whole fold would kill a live encounter over one author's bad row, and the
//! shipped `intersect_clamps` already made exactly this trade in writing:
//! *"refusing here at RUNTIME instead is the wrong trade: it would kill a live
//! encounter over an author's contradiction."* Nothing is silent either way —
//! substrate §7: **a contribution the fold cannot apply is REFUSED, with an
//! event.**

use ruleset_core::{MAX_DECLARED_QUANTITIES, QuantityTable};

use crate::ordinal::{PluginOrdinal, QuantityOrdinal};
use crate::plugin_set::PluginSet;
use crate::rows::{DerivationRow, FoldLayer, ModifierRow};

/// One quantity a plugin declares, and the value an actor starts at.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct QuantityDecl {
    pub ordinal: QuantityOrdinal,
    /// **The declaring plugin's number, not the hub's** (hub §3.4b).
    pub initial: i32,
}

/// What one plugin declares. **This is the whole of what a plugin tells the
/// hub about itself** — its ordinal, the quantities it owns, and the fold
/// layers it introduces. There is no name, no kind, and no behaviour, because
/// the hub knows nothing about what any of it means.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PluginDecl {
    pub ordinal: PluginOrdinal,
    pub quantities: Vec<QuantityDecl>,
    /// The fold layers this plugin introduces. **A plugin adds a layer without
    /// the engine learning its name** (hub §4).
    pub fold_layers: Vec<FoldLayer>,
}

/// Why a set of declarations could not become a registry.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RegistryError {
    /// Two plugins claim one quantity ordinal.
    ///
    /// Refused rather than resolved by precedence: an ordinal has exactly one
    /// owner, because presence is DERIVED from *"is the declaring plugin
    /// attached"* and two owners make that question ambiguous.
    QuantityClaimedTwice {
        ordinal: u16,
        first: u8,
        second: u8,
    },
    /// The same plugin ordinal appears twice in the declaration set.
    PluginDeclaredTwice { ordinal: u8 },
    /// A plugin declares a quantity ordinal the reality's own
    /// [`QuantityTable`] never assigned.
    ///
    /// **`QTY-A14`: an ordinal is meaningless without its `(reality, digest)`.**
    /// Accepting one past the declared table would let reality A's ordinal 3
    /// resolve against reality B's table and grant the wrong thing forever.
    OrdinalPastDeclaredTable { ordinal: u16, declared: usize },
}

/// Why one submitted row could not be applied. Substrate §7's **REFUSED**.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RowRefusal {
    /// The row targets a quantity no attached plugin declares — so there is no
    /// slot to contribute to. **Not zero, ABSENT** (hub §3.4b).
    UndeclaredTarget { ordinal: u16 },
    /// A derivation reads a quantity no attached plugin declares.
    UndeclaredSource { ordinal: u16 },
    /// **`U-7`, in its non-vacuous form.** The row names a fold layer **no
    /// plugin in this reality declared**.
    ///
    /// Reality-wide, not attachment-scoped, and that matches the contract:
    /// *"every `fold_layer` value present in a submitted row names a DECLARED
    /// fold layer."* A layer is a shared ordering position, so a row may name
    /// one that a plugin OTHER than the submitter declared — an earlier draft of
    /// this doc said *"no attached plugin"*, which described a stricter check
    /// than the code performs and than the contract asks for.
    ///
    /// This can fail, which is the whole point: a plugin ships a row for a layer
    /// it forgot to declare and the row lands in an order nothing defines. An
    /// earlier draft proposed *"every declared layer is reachable by the
    /// resolver"*, which **cannot fail** once the resolver iterates the
    /// declaration list — a check wearing the costume of evidence.
    UndeclaredFoldLayer { layer: u8 },
    /// The submitting plugin is not attached to this actor.
    SourceNotAttached { plugin: u8 },
    /// A derivation whose denominator is zero. The shipped code records why this
    /// matters: *"a zero here would divide by zero inside `apply` and take the
    /// island down."*
    ZeroDivisor,
    /// A bound whose `min` exceeds its `max` — an empty range. Refused at
    /// submission rather than resolved at runtime, because whichever end the
    /// code applied last would silently become the author's answer.
    ContradictoryBound { min: i32, max: i32 },
}

/// Who declares what, resolved once.
///
/// Dense arrays rather than maps: the space is `0..MAX_DECLARED_QUANTITIES`, the
/// lookup is on the fold path, and `hot-path-gate` refuses a string-keyed lookup
/// there for exactly this reason.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HubRegistry {
    /// Which plugin declares quantity `q`, if any.
    owner: [Option<PluginOrdinal>; MAX_DECLARED_QUANTITIES],
    /// The declaring plugin's initial value for `q`. Meaningless where `owner`
    /// is `None`, and unreachable there.
    initial: [i32; MAX_DECLARED_QUANTITIES],
    /// Whether ANY plugin declared fold layer `l`. Indexed by the layer
    /// ordinal, so the lookup `U-7` needs is `O(1)` and total.
    ///
    /// **The width is [`LAYER_SLOTS`], derived from [`FoldLayer`]'s own integer
    /// type — not a literal `256`.** A review measured the earlier shape: a
    /// `const` assertion said *"the fold-layer index must cover every FoldLayer
    /// value"* while comparing `u8::MAX + 1 == 256`, which is true on every
    /// target forever and **names neither this array nor `FoldLayer`**. Narrowing
    /// the array to 128 compiled, kept the assertion green, passed all 59 tests
    /// — and made `FoldLayer(200)` panic out of bounds inside a fold documented
    /// as total. Deriving the length removes the check rather than fixing it,
    /// which is the stronger move: there is now nothing to keep in step.
    ///
    /// **A flag, not an owner, and the `build_is_order_independent` test is why
    /// this was changed.** The first draft stored *which* plugin declared each
    /// layer — and since a layer is a shared ordering position that two plugins
    /// legitimately declare, "first declarer" is a fact about the ORDER the
    /// declarations arrived in. Two identical realities built from the same
    /// declarations in different orders produced two different registries, and
    /// nothing read the field. **A stored value with no reader that also breaks
    /// an invariant is a defect twice over.**
    declared_layers: [bool; LAYER_SLOTS],
    /// Every declared plugin ordinal — the ones an actor may attach.
    declared_plugins: PluginSet,
}

impl HubRegistry {
    /// Build from a reality's plugin declarations, checked against the
    /// reality's own quantity table.
    ///
    /// Order-independent: the checks are over the whole set, so shuffling the
    /// declaration slice cannot change the outcome.
    pub fn build(table: &QuantityTable, decls: &[PluginDecl]) -> Result<Self, RegistryError> {
        let mut owner: [Option<PluginOrdinal>; MAX_DECLARED_QUANTITIES] =
            [None; MAX_DECLARED_QUANTITIES];
        let mut initial = [0i32; MAX_DECLARED_QUANTITIES];
        let mut declared_layers = [false; LAYER_SLOTS];
        let mut declared_plugins = PluginSet::EMPTY;

        for decl in decls {
            if declared_plugins.contains(decl.ordinal) {
                return Err(RegistryError::PluginDeclaredTwice { ordinal: decl.ordinal.get() });
            }
            declared_plugins = declared_plugins.attach(decl.ordinal);

            for q in &decl.quantities {
                if q.ordinal.index() >= table.len() {
                    return Err(RegistryError::OrdinalPastDeclaredTable {
                        ordinal: q.ordinal.get(),
                        declared: table.len(),
                    });
                }
                if let Some(first) = owner[q.ordinal.index()] {
                    return Err(RegistryError::QuantityClaimedTwice {
                        ordinal: q.ordinal.get(),
                        first: first.get(),
                        second: decl.ordinal.get(),
                    });
                }
                owner[q.ordinal.index()] = Some(decl.ordinal);
                initial[q.ordinal.index()] = q.initial;
            }

            for l in &decl.fold_layers {
                // A layer declared by two plugins is NOT an error. A fold layer
                // is a shared ordering position — "equipment", "status" — and
                // two plugins contributing at the same position is the ordinary
                // case. What must not happen is a row naming a layer NOBODY
                // declared, which is what `U-7` checks.
                declared_layers[l.get() as usize] = true;
            }
        }

        Ok(Self { owner, initial, declared_layers, declared_plugins })
    }

    /// Which plugin declares this quantity, if any.
    pub fn owner_of(&self, q: QuantityOrdinal) -> Option<PluginOrdinal> {
        self.owner[q.index()]
    }

    /// **Hub §3.4b.** The value an actor starts this quantity at — `Some` only
    /// when the declaring plugin is attached. **A quantity of an unattached
    /// plugin is ABSENT, not zero**, and the `Option` is what makes the two
    /// distinguishable at the type level rather than by a sentinel.
    pub fn initial_value(&self, attached: PluginSet, q: QuantityOrdinal) -> Option<i32> {
        match self.owner[q.index()] {
            Some(p) if attached.contains(p) => Some(self.initial[q.index()]),
            _ => None,
        }
    }

    /// Is this quantity present on an actor with this attachment set?
    pub fn is_present(&self, attached: PluginSet, q: QuantityOrdinal) -> bool {
        self.initial_value(attached, q).is_some()
    }

    /// Has any plugin declared this fold layer? — the lookup `U-7` needs.
    /// Reality-wide — see [`RowRefusal::UndeclaredFoldLayer`].
    pub fn is_declared_layer(&self, l: FoldLayer) -> bool {
        self.declared_layers[l.get() as usize]
    }

    /// Every plugin this reality declared.
    pub fn declared_plugins(&self) -> PluginSet {
        self.declared_plugins
    }

    /// Check one modifier row against this actor's attachment set.
    ///
    /// `Ok(())` means the fold may apply it. Every other answer is a
    /// [`RowRefusal`] that substrate §7 requires be **recorded**, never dropped.
    pub fn check_modifier(&self, attached: PluginSet, row: &ModifierRow) -> Result<(), RowRefusal> {
        self.check_source(attached, row.source)?;
        self.check_target(attached, row.target)?;
        self.check_layer(row.fold_layer)
    }

    /// Check one derivation row. Everything [`Self::check_modifier`] checks,
    /// plus the source quantity, the divisor and the bound.
    pub fn check_derivation(
        &self,
        attached: PluginSet,
        row: &DerivationRow,
    ) -> Result<(), RowRefusal> {
        self.check_source(attached, row.source)?;
        self.check_target(attached, row.target)?;
        if !self.is_present(attached, row.source_quantity) {
            return Err(RowRefusal::UndeclaredSource { ordinal: row.source_quantity.get() });
        }
        self.check_layer(row.fold_layer)?;
        if row.divisor == 0 {
            return Err(RowRefusal::ZeroDivisor);
        }
        if let Some(b) = row.bound
            && b.min > b.max
        {
            return Err(RowRefusal::ContradictoryBound { min: b.min, max: b.max });
        }
        Ok(())
    }

    fn check_source(&self, attached: PluginSet, plugin: PluginOrdinal) -> Result<(), RowRefusal> {
        if attached.contains(plugin) {
            Ok(())
        } else {
            Err(RowRefusal::SourceNotAttached { plugin: plugin.get() })
        }
    }

    fn check_target(&self, attached: PluginSet, q: QuantityOrdinal) -> Result<(), RowRefusal> {
        if self.is_present(attached, q) {
            Ok(())
        } else {
            Err(RowRefusal::UndeclaredTarget { ordinal: q.get() })
        }
    }

    fn check_layer(&self, l: FoldLayer) -> Result<(), RowRefusal> {
        if self.is_declared_layer(l) {
            Ok(())
        } else {
            Err(RowRefusal::UndeclaredFoldLayer { layer: l.get() })
        }
    }
}

/// How many fold-layer ordinals exist — **derived from the ordinal's own type**,
/// so the index cannot fall behind it.
///
/// If [`FoldLayer`] ever widens to `u16`, this expression follows it and the
/// array grows in the same edit. That is why there is no assertion here: an
/// assertion would be a second thing to keep in step, and the earlier one
/// (`u8::MAX + 1 == 256`) could not fail.
const LAYER_SLOTS: usize = FoldLayer::ORDINAL_SPACE;
