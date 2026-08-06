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

/// `RealityScoped` — *"if the player walks from cell A to tavern to cell B,
/// does this aggregate move with them?"* **Yes.**
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct RealityScope;

/// `ChannelScoped` — same question, answered **no**: the aggregate belongs to
/// the place, not to the actor passing through it.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct ChannelScope;

impl sealed::SealedScope for RealityScope {}
impl sealed::SealedScope for ChannelScope {}

impl Scope for RealityScope {
    const KIND: ScopeKind = ScopeKind::Reality;
}

impl Scope for ChannelScope {
    const KIND: ScopeKind = ScopeKind::Channel;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scope_markers_are_the_cache_key_form() {
        assert_eq!(ScopeKind::Reality.as_key(), "r");
        assert_eq!(ScopeKind::Channel.as_key(), "c");
    }

    #[test]
    fn only_channel_scope_needs_a_channel() {
        assert!(!ScopeKind::Reality.requires_channel());
        assert!(ScopeKind::Channel.requires_channel());
    }
}
