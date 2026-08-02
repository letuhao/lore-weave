//! What a fold PRODUCES — substrate §7's two verbs, and the explain path.
//!
//! > | situation | verb |
//! > |---|---|
//! > | a contribution the fold cannot apply | **REFUSED**, with an event |
//! > | a value bound by a clamp | **CAPPED**, with an event |
//!
//! **The hub writes nothing.** Substrate §2 makes the ledger the SSOT for facts,
//! and a fold produces no fact: it is a pure function of state the caller
//! already holds. What it produces is a [`FoldReport`], and the caller decides
//! what enters the ledger.
//!
//! Split out of `fold.rs` when that file passed `IMP-D3`'s 400-line ceiling. The
//! seam is a real one — this module is the fold's OUTPUT vocabulary and holds no
//! arithmetic.

use ruleset_core::ModifierOp;

use crate::ordinal::{PluginOrdinal, QuantityOrdinal};
use crate::registry::RowRefusal;
use crate::rows::FoldLayer;
use ruleset_core::MAX_DECLARED_QUANTITIES;

/// Which submitted row a record refers to. **Position in the submitted slice**,
/// so a caller can point at the offending row without the hub holding a copy.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RowRef {
    Modifier(usize),
    Derivation(usize),
}

/// Substrate §7 — *a contribution the fold cannot apply is **REFUSED**, with an
/// event.* This is that record; the event is the caller's to write, because the
/// hub is pure and writes nothing.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Refused {
    pub row: RowRef,
    pub reason: RowRefusal,
}

/// Substrate §7 — *a value bound by a clamp is **CAPPED**, with an event.*
///
/// Already the practice this repo states elsewhere: *"a bound ceiling is a fact
/// in the log rather than a number nobody can explain."*
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Capped {
    pub quantity: QuantityOrdinal,
    /// **Where the clamp bit.** Added after a review measured three clamps that
    /// bit silently while §7 requires an event for each — and one report whose
    /// `wanted` understated the true value by roughly 6 000×, because an earlier
    /// saturation had already thrown that value away.
    pub site: CapSite,
    /// What the accumulator held. **Read it with `site`:** on
    /// [`CapSite::Accumulator`] the true value exceeded `i64` and this is the
    /// saturated bound, not the number the author asked for — which is exactly
    /// why the site is recorded rather than the number alone.
    pub wanted: i64,
    /// What the slot could hold.
    pub emitted: i32,
}

/// Which clamp produced a [`Capped`] record.
///
/// **Not a feature's vocabulary:** every member is a place in this fold's own
/// arithmetic, and the fold behaves differently at each — which is the
/// mechanism/vocabulary discriminator's own test (substrate §9).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CapSite {
    /// The `i64` accumulator saturated *before* the emit, so the true value is
    /// not representable and `wanted` is the saturated bound.
    Accumulator,
    /// The resolved value did not fit the quantity's one `i32` slot.
    Emit,
    /// A derivation's computed amount did not fit an `i32`.
    DerivedAmount,
    /// A derivation's own declared [`crate::ContributionBound`] bit. **This one
    /// is the author's intent working**, not a failure — and it is reported for
    /// the same reason as the others: *"a bound ceiling is a fact in the log
    /// rather than a number nobody can explain."*
    DerivedBound,
}

/// Where one contribution came from — the explain path's atom (`M-10`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Contribution {
    pub source: PluginOrdinal,
    pub fold_layer: FoldLayer,
    pub op: ModifierOp,
    pub row: RowRef,
    /// For a derivation: the quantity it read and the value it read. `None` for
    /// a literal modifier row.
    pub derived_from: Option<(QuantityOrdinal, i32)>,
}

/// **`M-10` — the answer to *"why is this number 47"*.**
///
/// The shipped `resolve_block` returns a bare `StatBlock` and discards `source`,
/// so that question has no answer today. Every term of the formula is here, in
/// applied order.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Explanation {
    pub quantity: QuantityOrdinal,
    pub base: i32,
    /// Every applied contribution, **ordered by `(fold_layer, source plugin,
    /// submission index)`**.
    ///
    /// The arithmetic does not depend on this order — both channels are sums,
    /// and a sum is commutative, which is exactly why the design chose summed
    /// percent over chained percent. **The order is fixed anyway**, because an
    /// explanation whose row order varied with input order would not be
    /// comparable between two runs.
    pub contributions: Vec<Contribution>,
    pub flat_sum: i64,
    pub percent_sum: i64,
    /// `max(0, 1000 + Σ pct)`.
    pub factor_milli: i64,
    /// The `i64` accumulator before the emit-time saturation.
    pub pre_emit: i64,
    pub value: i32,
}

/// What one fold produced. **The hub writes nothing** — substrate §2 makes the
/// ledger the SSOT for facts, and a fold produces no fact: it is a pure function
/// of state the caller already holds. What it produces is this report, and the
/// caller decides what enters the ledger.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FoldReport {
    /// `pub(crate)` so [`crate::fold`] can build one; **not `pub`**, because the
    /// distinction it carries — `None` is ABSENT, never `Some(0)` — must be read
    /// through [`FoldReport::value`] rather than indexed around.
    pub(crate) values: [Option<i32>; MAX_DECLARED_QUANTITIES],
    pub refused: Vec<Refused>,
    pub capped: Vec<Capped>,
    pub explanations: Vec<Explanation>,
}

impl FoldReport {
    /// The resolved value of a quantity — `None` when the quantity is ABSENT
    /// (hub §3.4b), never `Some(0)`.
    pub fn value(&self, q: QuantityOrdinal) -> Option<i32> {
        self.values[q.index()]
    }

    /// The explanation for one quantity, if it was folded.
    pub fn explain(&self, q: QuantityOrdinal) -> Option<&Explanation> {
        self.explanations.iter().find(|e| e.quantity == q)
    }
}
