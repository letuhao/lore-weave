//! `DP-Ch4` / `DP-A14` — aggregate scope, as **types**.
//!
//! An aggregate is identified either by `(reality_id, aggregate_id)` or by
//! `(reality_id, channel_id, aggregate_id)`. `DP-A14` calls that a
//! **design-time choice**, and `DP-Ch4` states the rule as *"an aggregate type
//! implements **exactly one** of these"* — then delegates enforcement to the
//! `#[derive(Aggregate)]` macro.
//!
//! **A macro check is defeated by hand-writing the impl.** So scope is an
//! associated type on [`crate::DpAggregate`], exactly like [`crate::Tier`]: on
//! a **concrete** impl there is one binding and nowhere for a second to live,
//! and no derive is required for that much to hold. A **generic** impl can
//! still carry several scopes under one aggregate name — see
//! [`crate::DpAggregate`] for the full split and for the gate that covers it.
//!
//! Sealed for the same reason the tiers are — there is no third scope, and a
//! feature crate cannot invent one.

use core::fmt;

use crate::tier::sealed;

/// The closed scope set (`DP-A14`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum ScopeKind {
    /// Identified by `(reality_id, aggregate_id)`. Follows the actor across
    /// channels — inventory, achievements, reputation.
    Reality,
    /// Identified by `(reality_id, channel_id, aggregate_id)`. Lives in one
    /// channel — chat, cell scene layout, tavern decor.
    Channel,
}

impl ScopeKind {
    /// The `r` / `c` marker at position 2 of a cache key (`DP-Ch5`), which is
    /// what makes a key self-describing to an operator reading Redis.
    pub const fn as_key(self) -> &'static str {
        match self {
            Self::Reality => "r",
            Self::Channel => "c",
        }
    }

    /// Does a cache key or a read/write call for this scope require a
    /// `ChannelId`? `DP-Ch5` makes passing one for a reality-scoped aggregate —
    /// or omitting it for a channel-scoped one — a **compile** error; this is
    /// the runtime-inspectable form of the same fact, for diagnostics.
    pub const fn requires_channel(self) -> bool {
        matches!(self, Self::Channel)
    }
}

impl fmt::Display for ScopeKind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::Reality => "reality",
            Self::Channel => "channel",
        })
    }
}

/// One scope. Sealed: the set is closed at two (`DP-A14`).
pub trait Scope: sealed::SealedScope + Copy + fmt::Debug + Send + Sync + 'static {
    const KIND: ScopeKind;
}

/// The **one sanctioned door** into the `DP-A14` scope set.
///
/// Scopes were hand-written until `G1`, and that was the difference between the
/// two taxonomies — not a stylistic one. `dp-aggregate-gate` reads the legal
/// scope names by parsing this file, so a hand-written third scope became
/// **legal by being written**: a cold-start completeness pass added `ZoneScope`
/// and got `cargo test` green, `clippy` green, and the gate reporting
/// `OK — every one binds one of ['ChannelScope', 'RealityScope', 'ZoneScope']`.
/// The gate did not miss it; it *printed the widened set and approved it.*
///
/// The tier side was already safe from this, and the reason is exactly the
/// macro: `declare_tier!` is a door, and
/// `spec_oracle::no_tier_is_implemented_outside_the_declare_tier_macro` checks
/// that nobody climbs the window. This is that shape, applied to the taxonomy
/// that did not have it.
macro_rules! declare_scope {
    ($name:ident, $kind:expr, $doc:expr) => {
        #[doc = $doc]
        #[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
        pub struct $name;

        impl sealed::SealedScope for $name {}

        impl Scope for $name {
            const KIND: ScopeKind = $kind;
        }
    };
}

declare_scope!(
    RealityScope,
    ScopeKind::Reality,
    "`RealityScoped` — *\"if the player walks from cell A to tavern to cell B, \
     does this aggregate move with them?\"* **Yes.** Identified by \
     `(reality_id, aggregate_id)`: inventory, achievements, reputation."
);

declare_scope!(
    ChannelScope,
    ScopeKind::Channel,
    "`ChannelScoped` — same question, answered **no**: the aggregate belongs to \
     the place, not to the actor passing through it. Identified by \
     `(reality_id, channel_id, aggregate_id)`: chat, cell scene layout, tavern \
     decor."
);

#[cfg(test)]
mod tests {
    use super::*;

    /// `G9` / `R3-N3` — **`Display` too, not just `as_key`.**
    ///
    /// `V2-F6` found `TierLevel::as_key` pinned for two of its four variants and
    /// fixed it — pinning all four keys *and* all four `Display` forms. The
    /// sibling enum one file over got neither half of that treatment: renaming
    /// `Display`'s `"reality"` to anything at all passed every test in the
    /// crate. Same defect, same commit, adjacent file — which is `BDR-36`'s
    /// shape at its smallest.
    #[test]
    fn scope_markers_are_the_cache_key_form() {
        assert_eq!(ScopeKind::Reality.as_key(), "r");
        assert_eq!(ScopeKind::Channel.as_key(), "c");

        // The `Display` form is what reaches a log line and a metric label.
        assert_eq!(ScopeKind::Reality.to_string(), "reality");
        assert_eq!(ScopeKind::Channel.to_string(), "channel");
        assert_eq!(RealityScope::KIND.to_string(), "reality");
        assert_eq!(ChannelScope::KIND.to_string(), "channel");
    }

    #[test]
    fn only_channel_scope_needs_a_channel() {
        assert!(!ScopeKind::Reality.requires_channel());
        assert!(ScopeKind::Channel.requires_channel());
    }
}
