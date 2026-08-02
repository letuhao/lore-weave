//! The contribution seam — **the whole plugin contract** (hub §4).
//!
//! ```text
//! ModifierRow    { target: QuantityOrdinal, op, source: PluginOrdinal, fold_layer }
//! DerivationRow  { target: QuantityOrdinal, source_quantity: QuantityOrdinal, op,
//!                  factor_milli, divisor, bound, source: PluginOrdinal, fold_layer }
//! ```
//!
//! **This block is the amended §4** (contract, 2026-08-02). An earlier version of
//! this file carried the pre-amendment text verbatim — a `value` field that does
//! not exist, and `source` typed as a `QuantityOrdinal` when it is a
//! `PluginOrdinal`. The amendment's own stated reason was that *"a reader
//! following the only specification would otherwise read `source` as a quantity
//! and be handed a plugin"*, which is precisely what this file, headed **"the
//! whole plugin contract"**, was doing. **A correction sweeps a CONCEPT, not the
//! location the finding pointed at.**
//!
//! | rule | why |
//! |---|---|
//! | **A contribution is DATA, never executable logic.** | The whole decoupling. A plugin cannot run inside the fold, and the fold cannot run inside a plugin |
//! | **A row addresses an ORDINAL, never a name.** | The address is mechanism; the name is the author's |
//! | **A condition is a declared threshold**, never a predicate grammar | a grammar is code wearing a data costume |
//! | **The hub never inspects `fold_layer` semantically.** | It orders by it and nothing else. If the hub ever needs to know what a layer MEANS, a plugin's vocabulary has leaked in |
//! | **A `DerivationRow` CONTRIBUTES; it never SETS.** | The shipped `derive_move_range` ends in `self.set(…)`, overwriting a value six layers just resolved — so an Equipment `Flat(+2)` on `MoveRange` is accepted and silently discarded today (`S-4`). SET would adopt that defect as a design |
//!
//! ## `fold_layer`, not `layer`
//!
//! `ruleset-loader/src/layer.rs:22` already ships an unrelated `Layer` whose
//! `ALL` is documented at `:44` as *"Ascending priority — the fold order."*
//! **One name, two concepts, avoided** (`S-10`).
//!
//! ## `op` and `value`, and why the two rows spell them differently
//!
//! A `ModifierRow` carries a literal amount, so [`ruleset_core::ModifierOp`]
//! — which carries its value — is exactly right, and it is the one closed set
//! the mechanism/vocabulary discriminator clears (substrate §9).
//!
//! A `DerivationRow`'s amount is **computed** from another quantity's resolved
//! value, so the row stores the *channel* ([`OpKind`]) and the
//! *ratio*, and the op is rebuilt once the amount is known. See
//! `ruleset-core/src/modifier.rs` for why that is the same enum's discriminant
//! rather than a second `Flat | Percent`.

use ruleset_core::{ModifierOp, OpKind};

use crate::ordinal::{PluginOrdinal, QuantityOrdinal};

/// A fold-layer ordinal. **The hub orders by it and nothing else.**
///
/// It has no name here, and that is the point: *which* fold layers exist and
/// what they are called is **declared**, so a plugin adds one without the engine
/// learning its name. If the hub ever needed to know what a layer MEANS, a
/// plugin's vocabulary would have leaked in.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct FoldLayer(pub u8);

impl FoldLayer {
    /// How many distinct fold-layer ordinals exist, **derived from the field's
    /// own type**. `HubRegistry` sizes its declared-layer index with this, so
    /// widening `FoldLayer` widens the index in the same edit — there is no
    /// second constant to keep in step, and therefore no assertion that could
    /// pass while the two disagreed.
    pub const ORDINAL_SPACE: usize = u8::MAX as usize + 1;

    pub const fn get(self) -> u8 {
        self.0
    }
}

/// A literal contribution to one quantity.
///
/// `source` is the **plugin ordinal** that submitted the row — the hub knows
/// plugins by ordinal and by nothing else. It is what makes the explain path
/// (`M-10`) able to answer *"why is this number 47"*, and what lets the fold
/// ignore rows from plugins that are not attached.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ModifierRow {
    pub target: QuantityOrdinal,
    /// The channel **and** the amount — see the module doc.
    pub op: ModifierOp,
    pub source: PluginOrdinal,
    pub fold_layer: FoldLayer,
}

/// A bound on **a derivation's own contribution** — not on the quantity.
///
/// > **This is not a quantity ceiling model.** The ceiling MODEL belongs to
/// > whichever feature first declares a bounded quantity (`U-4`, substrate §5),
/// > and feature #1 does not write it. What this bounds is the *amount this row
/// > contributes*, which the shipped move-range derivation demonstrably needs:
/// > `clamp(base + speed / per_tile, 1, max)` — the `1` and the `max` are part
/// > of the derivation's arithmetic, not a property of `MoveRange`.
///
/// Inclusive on both ends. `min > max` is refused at submission
/// ([`crate::HubRegistry::check_derivation`]) rather than clamped at runtime, because a contradiction
/// an author wrote should not be resolved by whichever bound the code happens to
/// apply last.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ContributionBound {
    pub min: i32,
    pub max: i32,
}

/// A contribution computed from **another quantity's resolved value**.
///
/// ```text
/// amount = source_value × factor_milli / divisor      (bounded, if a bound is declared)
/// ```
///
/// ## Why there is a `divisor` (`U-6`)
///
/// `factor_milli` alone cannot express the shipped move-range derivation.
/// Measured: dividing a speed of `10_000` by `3` gives **3 333**, while the
/// nearest per-mille factor `×333/1000` gives **3 330**. A ratio with a
/// denominator the author chose is not expressible as a per-mille numerator, and
/// silently shipping the 3 330 would be a wrong answer nobody could see.
///
/// `divisor` is `NonZero`-checked at submission; the shipped code's own comment
/// records why (*"a zero here would divide by zero inside `apply` and take the
/// island down"*).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct DerivationRow {
    pub target: QuantityOrdinal,
    /// The quantity this derivation READS. It reads the value resolved from
    /// modifier rows — see [`mod@crate::fold`] for the stated, single-pass limit.
    pub source_quantity: QuantityOrdinal,
    /// Which channel the computed amount lands in.
    pub op: OpKind,
    pub factor_milli: i32,
    /// The denominator. `0` is refused at submission.
    pub divisor: i32,
    pub bound: Option<ContributionBound>,
    pub source: PluginOrdinal,
    pub fold_layer: FoldLayer,
}

impl DerivationRow {
    /// The amount this row contributes, given its source quantity's resolved
    /// value. **Saturating throughout, and never a division by zero** — the
    /// fold is total (`M-6`), so a row that could panic is a row that could take
    /// the island down.
    ///
    /// A `divisor` of zero cannot reach here: submission refuses it
    /// ([`crate::RowRefusal::ZeroDivisor`]). The `if` below is the
    /// belt to that braces, and it returns `0` rather than panicking because a
    /// total function has no other option.
    pub fn amount(&self, source_value: i32) -> ModifierOp {
        self.amount_reported(source_value).0
    }

    /// The unclamped amount, in `i64`, before either clamp.
    ///
    /// This is what a [`crate::Capped`] record needs in order to say what the
    /// author actually asked for: once the value has been squeezed into an `i32`
    /// the number is gone, and a report built from the result understates it.
    ///
    /// **The `saturating_mul` below CANNOT fire, and that is disclosed rather
    /// than dressed up as a guard.** Both operands are `i32` widened into an
    /// `i64`, so the product is at most `2^62`; `checked_mul` returns `Some` for
    /// every `i32 × i32`, and replacing it with a plain `*` leaves the whole
    /// suite green. It is **stronger** than the two `saturating_add`s in
    /// [`mod@crate::fold`] — those need ~2^32 rows, this one is structurally
    /// impossible — and those got a paragraph, so this one does too. What is a
    /// real guard here is the `divisor == 0` branch, which submission also
    /// refuses, and the `i32` squeeze in [`Self::amount_reported`], which fires
    /// on ordinary input and is tested.
    pub fn raw_amount(&self, source_value: i32) -> i64 {
        if self.divisor == 0 {
            0
        } else {
            (source_value as i64).saturating_mul(self.factor_milli as i64) / (self.divisor as i64)
        }
    }

    /// The amount, **plus which clamp bit if one did**.
    ///
    /// Substrate §7 requires an event for *"a value bound by a clamp"*, and a
    /// review measured that both of this row's clamps — the `i32` squeeze and
    /// the author's own [`ContributionBound`] — bit silently. They are separate
    /// sites because they mean different things: one is the representation
    /// failing, the other is the author's declaration working. Only the first is
    /// a defect; each is a fact in the log rather than a number nobody can
    /// explain.
    ///
    /// **When both bite, only the bound is reported**, and the earlier claim that
    /// *"both are facts in the log"* was false in exactly that case — a review
    /// measured it with `factor_milli = 1_000_000, divisor = 1, source = i32::MAX,
    /// bound = {0, 5}`: one record, `site = DerivedBound`.
    ///
    /// The precedence is kept, because the bound is what decided the value the
    /// fold used (`b.max <= i32::MAX` always, so the squeeze can never be the
    /// binding constraint) and `wanted` still carries the unclamped truth. What
    /// changed is the sentence: **one site is reported, and it is the one that
    /// decided the number.**
    pub fn amount_reported(&self, source_value: i32) -> (ModifierOp, Option<crate::CapSite>) {
        let raw = self.raw_amount(source_value);
        let clamped = raw.clamp(i32::MIN as i64, i32::MAX as i64) as i32;
        let squeezed = clamped as i64 != raw;
        let bounded = match self.bound {
            // `min` first, then `max` — but submission has already refused
            // `min > max`, so the order cannot change the answer here.
            Some(b) => clamped.clamp(b.min, b.max),
            None => clamped,
        };
        let site = if bounded != clamped {
            Some(crate::CapSite::DerivedBound)
        } else if squeezed {
            Some(crate::CapSite::DerivedAmount)
        } else {
            None
        };
        (ModifierOp::with_value(self.op, bounded), site)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn q(raw: u16) -> QuantityOrdinal {
        QuantityOrdinal::new(raw).unwrap()
    }

    fn p(raw: u8) -> PluginOrdinal {
        PluginOrdinal::new(raw).unwrap()
    }

    fn row(factor_milli: i32, divisor: i32, bound: Option<ContributionBound>) -> DerivationRow {
        DerivationRow {
            target: q(1),
            source_quantity: q(0),
            op: OpKind::Flat,
            factor_milli,
            divisor,
            bound,
            source: p(0),
            fold_layer: FoldLayer(0),
        }
    }

    /// `U-6`, the measurement that put the divisor on the row. A per-mille
    /// factor CANNOT express a division by three, and the difference is
    /// visible at the first realistic input.
    #[test]
    fn the_divisor_expresses_what_factor_milli_cannot() {
        let exact = row(1, 3, None);
        assert_eq!(exact.amount(10_000).value(), 3_333);

        // The nearest per-mille approximation of 1/3, which is what a row
        // without a divisor would have been forced to use.
        let approximated = row(333, 1_000, None);
        assert_eq!(approximated.amount(10_000).value(), 3_330);

        assert_ne!(
            exact.amount(10_000).value(),
            approximated.amount(10_000).value(),
            "if these agree the divisor bought nothing and U-6 was wrong"
        );
    }

    #[test]
    fn a_bound_clamps_the_contribution_not_the_quantity() {
        let bounded = row(1, 1, Some(ContributionBound { min: 1, max: 5 }));
        assert_eq!(bounded.amount(100).value(), 5);
        assert_eq!(bounded.amount(-100).value(), 1);
        assert_eq!(bounded.amount(3).value(), 3);
    }

    #[test]
    fn the_channel_survives_the_computation() {
        let mut r = row(2, 1, None);
        assert_eq!(r.amount(10), ModifierOp::Flat(20));
        r.op = OpKind::Percent;
        assert_eq!(r.amount(10), ModifierOp::Percent(20));
    }

    /// Totality (`M-6`): no input may panic. Overflow saturates and a zero
    /// divisor yields zero rather than dividing.
    #[test]
    fn amount_is_total_for_every_extreme() {
        for source in [i32::MIN, -1, 0, 1, i32::MAX] {
            for factor in [i32::MIN, -1, 0, 1, i32::MAX] {
                for divisor in [i32::MIN, -1, 0, 1, i32::MAX] {
                    let _ = row(factor, divisor, None).amount(source);
                }
            }
        }
        assert_eq!(row(7, 0, None).amount(i32::MAX).value(), 0);
        // i32::MIN / -1 overflows in two's complement; saturating multiply plus
        // the i64 accumulator is what stops it being a panic.
        assert_eq!(row(1, -1, None).amount(i32::MIN).value(), i32::MAX);
    }

    /// Ordering is by the layer ordinal and by nothing else — the hub never
    /// inspects what a layer means.
    #[test]
    fn fold_layers_order_by_ordinal() {
        let mut layers = [FoldLayer(9), FoldLayer(0), FoldLayer(255), FoldLayer(3)];
        layers.sort();
        assert_eq!(
            layers.map(FoldLayer::get),
            [0, 3, 9, 255],
            "fold layers must be a total order over their ordinals"
        );
    }
}
