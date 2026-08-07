//! `DP-K1` — the aggregate contract, and the one place tier meets scope.

use core::fmt::Debug;
use core::hash::Hash;
use core::time::Duration;

use crate::scope::{Scope, ScopeKind};
use crate::tier::{Coherency, Tier, TierLevel};

/// An aggregate as the DP access surface sees it.
///
/// # This is NOT `dp_kernel::Aggregate`, and the difference is the point
///
/// `crates/dp-kernel` already exports a trait called `Aggregate`, and a derive
/// macro called `Aggregate`. That one is about **rebuilding state from an event
/// log** — `apply(envelope)`, consumed by `load_aggregate`. This one is about
/// **how the access surface reaches a value**: which tier's guarantees apply,
/// which scope key addresses it, what its cache key looks like.
///
/// They are different concerns and one type may want both, so they are two
/// traits with two names. This is recorded rather than quietly worked around
/// because the collision is a **class**, not an accident (`REC-100`,
/// `FLOW-24`): `dp-kernel` itself, `CircuitOpen`/`RateLimited`,
/// `deploy_cohort`, and `ChannelId` are four more cases of one word meaning two
/// things in this workspace. The rule this crate follows: **name a thing for
/// what it is, and when a name is taken, take a different one and say so.**
///
/// # Exclusivity — exactly what holds, and exactly what does not
///
/// `DP-Ch4` asks that an aggregate implement *"exactly one"* scope marker and
/// delegates that to a derive macro. Here `Scope` and `Tier` are **associated
/// types** instead, which is stronger in one direction and — this is the part
/// that was overclaimed to the PO on 2026-08-07 and corrected by a cold-start
/// refuter (`V1-F1`) — **not a guarantee at all in another.**
///
/// **Holds in the type system:**
/// * A **concrete, non-generic** `impl DpAggregate` binds exactly one tier and
///   one scope. A second binding is not rejected, it is unrepresentable
///   (`E0201`); a second impl for the same type is `E0119`.
/// * The tier and scope sets are **closed against every crate, including one
///   outside this repo**, because both traits are sealed. Verified against the
///   `#[fundamental]` `&T` orphan escape, which `rustc` also refuses.
/// * A tier cannot **vary at runtime**: `TierLevel` is not a `Tier`, so no
///   value can stand where a tier type is required (`tests/ui/`).
///
/// **Does NOT hold in the type system — enforced by `scripts/dp-aggregate-gate.py`
/// instead:**
/// * The impl may be **generic over its tier** — `impl<T: Tier> DpAggregate for
///   Wallet<T>` with one [`TYPE_NAME`](DpAggregate::TYPE_NAME) — so a single
///   aggregate name can carry four tiers, selected by the caller per request.
/// * Two separate impls may **share a `TYPE_NAME`**.
///
/// Both of those put two coherency contracts (and two answers to
/// [`Tier::SURVIVES_STORE_OUTAGE`]) under one `DP-Ch5` cache-key token. The type
/// checker cannot see either, **by construction**: each monomorphisation is
/// individually consistent and the contradiction lives *across* them, which is
/// the one comparison a type checker never makes. So it is checked over the
/// source, in-repo, and that scope limit is the honest boundary of the claim.
///
/// [`Tier::SURVIVES_STORE_OUTAGE`]: crate::Tier::SURVIVES_STORE_OUTAGE
pub trait DpAggregate: Send + Sync + 'static {
    /// Design-time, not runtime (`DP-A9`).
    type Tier: Tier;

    /// Design-time, not runtime (`DP-A14`).
    type Scope: Scope;

    /// This aggregate's own id type — typically a newtype over `Uuid` or `i64`.
    type Id: Clone + Eq + Hash + Debug + Send + Sync + 'static;

    /// Stable name used in cache keys and telemetry labels (`DP-Ch5`,
    /// `DP-K8`). Must be `snake_case` and stable across releases: it is part of
    /// a cache key, so changing it silently orphans every cached entry.
    const TYPE_NAME: &'static str;
}

/// The `DP-R2` tier table, for one aggregate, derived from its types.
///
/// `DP-R2` requires a feature design doc to carry a tier table and blocks
/// review without it — *"every aggregate, read tier, write tier, rationale"*
/// (`22_feature_design_quickstart.md:203`, the checklist row that states the
/// requirement; the header used to attribute the phrase to `DP-R2` itself,
/// which is where the rule lives but not where those words are — `G11`).
///
/// That table has always been hand-written prose checked by a human. This is
/// the machine-readable half: everything except the rationale is now **read off
/// the type**, so a table and the code cannot disagree.
///
/// # The fields are private, and that is the entire value of the type
///
/// They were `pub` until `V1-F5`, and the refuter's break took one expression:
/// a `T3` row hand-built with `Coherency::None`, a **24-hour** TTL — the `const`
/// block in [`crate::tier`] asserts ≤ 1 h — and `survives_store_outage: true`,
/// which is the `REC-102c` verdict inverted for the one tier that must never
/// buffer. It compiled, because a struct literal is not a derivation.
///
/// **A table that can be written by hand is the hand-written table it was meant
/// to replace.** So the only constructor **in safe Rust** is [`tier_row`], which
/// reads every field off `A`'s types and can therefore only ever produce a row
/// that agrees with the tier. Reading is by `const fn` accessor, so a caller
/// loses nothing: a row is still usable in a `const` context.
///
/// *"In safe Rust"* is the honest qualifier and was missing (`R2-11`): a caller
/// writing `unsafe { transmute(..) }` forged a `T3` row with a 24-hour TTL. It
/// is UB — the layout is `repr(Rust)` — and `#![forbid(unsafe_code)]` binds this
/// crate, not its consumers. Every private-field invariant in Rust has this
/// same boundary; stating it costs a line and stops the claim being absolute.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TierRow {
    type_name: &'static str,
    tier: TierLevel,
    scope: ScopeKind,
    coherency: Coherency,
    cache_ttl: Option<Duration>,
    write_ack_p99: Duration,
    survives_store_outage: bool,
}

impl TierRow {
    /// The aggregate token of the `DP-Ch5` cache key.
    pub const fn type_name(&self) -> &'static str {
        self.type_name
    }
    /// `DP-T0`..`DP-T3`.
    pub const fn tier(&self) -> TierLevel {
        self.tier
    }
    /// `DP-A14` — what addresses this aggregate.
    pub const fn scope(&self) -> ScopeKind {
        self.scope
    }
    /// `DP-X1` — the coherency contract this tier promises.
    pub const fn coherency(&self) -> Coherency {
        self.coherency
    }
    /// `DP-X7` — `None` means "not cached", not "cached forever".
    pub const fn cache_ttl(&self) -> Option<Duration> {
        self.cache_ttl
    }
    /// `DP-S3`.
    pub const fn write_ack_p99(&self) -> Duration {
        self.write_ack_p99
    }
    /// `REC-102c` — may this aggregate's writes be buffered while its store is
    /// unreachable, or must the caller be refused?
    pub const fn survives_store_outage(&self) -> bool {
        self.survives_store_outage
    }
}

/// Read an aggregate's `DP-R2` row off its type. The **only** way to build a
/// [`TierRow`] — see that type for why.
pub const fn tier_row<A: DpAggregate>() -> TierRow {
    TierRow {
        type_name: A::TYPE_NAME,
        tier: <A::Tier as Tier>::LEVEL,
        scope: <A::Scope as Scope>::KIND,
        coherency: <A::Tier as Tier>::COHERENCY,
        cache_ttl: <A::Tier as Tier>::CACHE_TTL,
        write_ack_p99: <A::Tier as Tier>::WRITE_ACK_P99,
        survives_store_outage: <A::Tier as Tier>::SURVIVES_STORE_OUTAGE,
    }
}

/// Does reaching this aggregate require a `ChannelId`? (`DP-Ch5`.)
pub const fn requires_channel<A: DpAggregate>() -> bool {
    <A::Scope as Scope>::KIND.requires_channel()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scope::{ChannelScope, RealityScope};
    use crate::tier::{T1, T2, T3};

    /// The two shapes `22 §4.3`'s tier x scope matrix leads with.
    struct PlayerInventory;
    impl DpAggregate for PlayerInventory {
        type Tier = T2;
        type Scope = RealityScope;
        type Id = u64;
        const TYPE_NAME: &'static str = "player_inventory";
    }

    struct ChannelPresence;
    impl DpAggregate for ChannelPresence {
        type Tier = T1;
        type Scope = ChannelScope;
        type Id = u64;
        const TYPE_NAME: &'static str = "channel_presence";
    }

    struct ReputationScore;
    impl DpAggregate for ReputationScore {
        type Tier = T3;
        type Scope = RealityScope;
        type Id = u64;
        const TYPE_NAME: &'static str = "reputation_score";
    }

    #[test]
    fn a_tier_row_is_read_off_the_type() {
        let row = tier_row::<PlayerInventory>();
        assert_eq!(row.type_name(), "player_inventory");
        assert_eq!(row.tier(), TierLevel::T2);
        assert_eq!(row.scope(), ScopeKind::Reality);
        assert_eq!(row.coherency(), Coherency::WriteThroughAsyncInvalidate);
        assert!(row.survives_store_outage());
    }

    /// Tier and scope are orthogonal — `DP-Ch4`: *"all 4 tiers x 2 scopes = 8
    /// combinations, all valid"*. If a change ever coupled them, these three
    /// rows would stop being independently expressible.
    #[test]
    fn tier_and_scope_vary_independently() {
        assert_eq!(tier_row::<ChannelPresence>().tier(), TierLevel::T1);
        assert_eq!(tier_row::<ChannelPresence>().scope(), ScopeKind::Channel);
        assert_eq!(tier_row::<ReputationScore>().tier(), TierLevel::T3);
        assert_eq!(tier_row::<ReputationScore>().scope(), ScopeKind::Reality);
    }

    /// `REC-102c` reaching the caller: the money-adjacent aggregate is the one
    /// that must refuse to proceed while its store is unreachable, and the
    /// presence aggregate is the one that must not stop the game.
    #[test]
    fn the_outage_verdict_follows_the_aggregate_not_the_incident() {
        assert!(tier_row::<ChannelPresence>().survives_store_outage());
        assert!(tier_row::<PlayerInventory>().survives_store_outage());
        assert!(!tier_row::<ReputationScore>().survives_store_outage());
    }

    #[test]
    fn only_channel_scoped_aggregates_need_a_channel() {
        assert!(!requires_channel::<PlayerInventory>());
        assert!(requires_channel::<ChannelPresence>());
    }
}
