//! `ModifierOp` — **how a contribution combines**, and the one closed set in
//! this repo that the mechanism/vocabulary discriminator genuinely clears.
//!
//! > **A closed set is MECHANISM if the engine's arithmetic DIFFERS PER MEMBER.
//! > It is a feature's vocabulary in costume if the engine treats members
//! > UNIFORMLY and only one feature knows their names.**
//! > — engine substrate §9
//!
//! Applied to this enum the verdict is **cleared**: `Flat` is summed into the
//! addend and `Percent` is summed into the multiplier, and those are two
//! different arithmetics in the same fold — `game-rules/src/stats/resolve.rs`
//! adds at one line and multiplies at another. Nineteen closed sets were
//! measured; `ModifierSource` and `StatSlot` were convicted and this one was
//! not.
//!
//! ## Why it lives HERE and not with the laws
//!
//! It was defined in `game-rules::stats::modifier` and moved down on 2026-08-02
//! when the actor hub (feature #1) needed the same op set for its contribution
//! rows. The hub sits **beneath** the features, and combat is a feature — so a
//! hub → `game-rules` dependency becomes a cycle the day combat is rewritten as
//! a plugin. `game-rules` re-exports it, so `game_rules::stats::ModifierOp`
//! still names this type and no law changed.
//!
//! **One definition, two consumers.** The alternative considered and rejected
//! was a second `Flat | Percent` enum in the hub, which is one concept with two
//! names — the exact rot this repo deletes rather than layers over.

/// How one contribution combines into a resolved value.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ModifierOp {
    /// An addend, in the quantity's own units.
    Flat(i32),
    /// Per-mille percentage. **DF7-A5 — percent contributions SUM into one
    /// factor rather than chaining multiplicatively**, which makes the result
    /// order-independent by construction and kills exponential buff stacking.
    ///
    /// A chained product would need a deterministic sort as a patch; a sum needs
    /// nothing, because addition is commutative.
    Percent(i32),
}

/// Which channel a contribution lands in, **without a value**.
///
/// ## Why this exists, and why it is not a second vocabulary
///
/// The actor hub's contribution seam has two row shapes, and they need the op
/// differently:
///
/// | row | needs |
/// |---|---|
/// | `ModifierRow` | the channel **and** the value — `ModifierOp` carries both |
/// | `DerivationRow` | the channel **only**; its amount is COMPUTED from another quantity's resolved value times `factor_milli / divisor` |
///
/// Storing a `ModifierOp` on a derivation row would mean carrying a payload
/// nothing reads — an inexpressible-state hole of the kind that lets two
/// encodings mean one thing. Storing a hand-written `enum { Flat, Percent }`
/// beside `ModifierOp` would be **one concept with two names**, which is the rot
/// this repo deletes rather than layers over.
///
/// So this is the *discriminant of the same enum*, and
/// [`ModifierOp::kind`] / [`ModifierOp::with_value`] tie the two together so
/// they cannot drift: adding a third `ModifierOp` variant is a compile error in
/// both directions (neither `match` has a wildcard arm).
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum OpKind {
    Flat,
    Percent,
}

impl OpKind {
    /// How many channels there are. Naming it ties [`OpKind::ALL`]'s length to
    /// something a reader must also change — see `closed-set-gate`.
    pub const COUNT: usize = 2;

    pub const ALL: [OpKind; Self::COUNT] = [OpKind::Flat, OpKind::Percent];
}

impl ModifierOp {
    /// The channel this contribution lands in, discarding the value.
    ///
    /// Exhaustive with no wildcard arm: a third variant is a compile error here.
    pub const fn kind(self) -> OpKind {
        match self {
            ModifierOp::Flat(_) => OpKind::Flat,
            ModifierOp::Percent(_) => OpKind::Percent,
        }
    }

    /// Rebuild a full op from a channel and a computed amount — the inverse of
    /// [`ModifierOp::kind`], and what a derivation row uses once its amount is
    /// known.
    pub const fn with_value(kind: OpKind, value: i32) -> Self {
        match kind {
            OpKind::Flat => ModifierOp::Flat(value),
            OpKind::Percent => ModifierOp::Percent(value),
        }
    }

    /// The value this contribution carries, in the units of its channel.
    pub const fn value(self) -> i32 {
        match self {
            ModifierOp::Flat(v) | ModifierOp::Percent(v) => v,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The discriminator's claim, asserted rather than repeated: the two
    /// members are not interchangeable, so a fold that treated them uniformly
    /// would be wrong.
    #[test]
    fn the_two_members_are_distinct_values() {
        assert_ne!(ModifierOp::Flat(100), ModifierOp::Percent(100));
        assert_eq!(ModifierOp::Flat(100), ModifierOp::Flat(100));
    }

    /// `kind` and `with_value` must be inverses for **every** channel and a
    /// representative spread of values, or a derivation row's computed amount
    /// could land in the wrong channel — silently, since both are `i32`.
    #[test]
    fn kind_and_with_value_round_trip_for_every_channel() {
        for kind in OpKind::ALL {
            for v in [i32::MIN, -1000, -1, 0, 1, 1000, i32::MAX] {
                let op = ModifierOp::with_value(kind, v);
                assert_eq!(op.kind(), kind, "channel changed for {kind:?}/{v}");
                assert_eq!(op.value(), v, "value changed for {kind:?}/{v}");
            }
        }
    }

    /// `ALL` must list every channel. Rust forces a `match` to HANDLE every
    /// variant but cannot force an array to CONTAIN every variant — the exact
    /// hole `closed-set-gate` exists for, asserted here as well because this
    /// list is small enough to check by construction.
    #[test]
    fn all_covers_every_channel() {
        // NOT asserted: `OpKind::ALL.len() == OpKind::COUNT`. `ALL` is declared
        // `[OpKind; Self::COUNT]`, so its length IS the constant and the
        // comparison cannot fail — a review named it as a vacuous arm sitting
        // inside a test that otherwise bites. The dedup below is the arm that
        // does the work: `ALL = [Flat, Flat]` reddens it.
        let mut seen = OpKind::ALL.to_vec();
        seen.sort_unstable();
        seen.dedup();
        assert_eq!(seen.len(), OpKind::COUNT, "OpKind::ALL repeats a channel");
        // Every channel is reachable from a real op, so a variant nobody points
        // at cannot hide in the list.
        assert!(seen.contains(&ModifierOp::Flat(0).kind()));
        assert!(seen.contains(&ModifierOp::Percent(0).kind()));
    }
}
