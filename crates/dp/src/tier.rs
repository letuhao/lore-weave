//! `DP-T0`..`DP-T3` — the four tiers, as **types**.
//!
//! # Why a type and not an enum field
//!
//! [`DP-A9`] says tier assignment is *"design-time only … not chosen at
//! runtime, not configurable per player, not switchable without a
//! design-change"*, and [`DP-A5`] says the taxonomy is **closed**: *"No new
//! tiers, no 'between T1 and T2', no per-feature special cases."*
//!
//! *(The `DP-A9` quote is verbatim from `02_invariants.md`. The `DP-A5` one was
//! not: this header attributed *"pick the closer tier; if unsure, pick the safer
//! one. No in-betweens"* to `DP-A5`, and that sentence is a table row in
//! `22_feature_design_quickstart.md:185` which **cites** `DP-A5`. Same meaning,
//! wrong source — `G11`. A citation nobody can follow is worse than none, and
//! this crate's ~30 citations carry no `#Symbol` anchor, so
//! `source-citation-gate` reaches none of them by design.)*
//!
//! A `tier: TierLevel` **field** cannot say either of those things — a field is
//! exactly the thing that varies at runtime. So the tier is an **associated
//! type** on [`crate::DpAggregate`], and each tier is a distinct zero-sized
//! type implementing the [`Tier`] trait.
//!
//! Two consequences the prose version could only ask for:
//!
//! * **A concrete aggregate impl has exactly one tier, structurally.** Not
//!   *"the derive macro rejects two"* — an associated type has one binding, and
//!   there is nowhere for a second to live. `12_channel_primitives.md` DP-Ch4
//!   asks for exclusivity and delegates it to a macro check; a macro check is
//!   defeated by hand-writing the impl. **The word `concrete` is load-bearing
//!   and was missing until `V1-F1`:** a *generic* impl lifts the tier into a
//!   parameter, and rustc cannot object because each monomorphisation is
//!   consistent on its own. `scripts/dp-aggregate-gate.py` is the mechanism for
//!   that half; [`crate::DpAggregate`] states the split in full.
//! * **`T1.5` does not compile.** [`Tier`] is **sealed** (`sealed::SealedTier` is
//!   private to this crate), so a feature crate cannot mint a fifth tier. That
//!   is `DP-A5`'s closed set, enforced by the compiler rather than by a
//!   reviewer noticing.
//!
//! # The constants are the contract, not documentation
//!
//! Every number below is transcribed from a LOCKED section and cited on the
//! line. They live here so a consumer *reads the tier* instead of re-deriving
//! the budget from prose — and so a change to a budget is a diff in one file
//! rather than a search across twenty-five.
//!
//! [`DP-A5`]: ../../../docs/03_planning/LLM_MMO_RPG/06_data_plane/02_invariants.md
//! [`DP-A9`]: ../../../docs/03_planning/LLM_MMO_RPG/06_data_plane/02_invariants.md

use core::fmt;
use core::time::Duration;

pub(crate) mod sealed {
    //! Private supertraits: only this crate can name them, so only this crate
    //! can implement [`super::Tier`] or [`Scope`](crate::scope::Scope). This is
    //! `DP-A5`'s and `DP-A14`'s closed taxonomies expressed as a visibility
    //! rule.
    //!
    //! **Two traits, not one (`V1-F13`).** A single `Sealed` marker served both,
    //! which made `impl Sealed for X` mean *"X may join either taxonomy"* — a
    //! coupling between two sets that have nothing to do with each other, in the
    //! one place whose entire job is saying what may not be joined. Nothing was
    //! broken by it; it was the shape being wrong, and this crate's subject is
    //! the difference between a guarantee and the shape of one.

    /// Seals [`super::Tier`] — the `DP-A5` four.
    pub trait SealedTier {}

    /// Seals [`Scope`](crate::scope::Scope) — the `DP-A14` two.
    pub trait SealedScope {}
}

/// The closed tier set (`DP-A5`). Runtime-inspectable form of the type-level
/// tier — for telemetry labels, cache keys and log lines, never for dispatch.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum TierLevel {
    T0,
    T1,
    T2,
    T3,
}

impl TierLevel {
    /// Lowercase key form used in `dp:{reality}:{r|c}:{tier}:…` cache keys
    /// (`DP-Ch5`).
    pub const fn as_key(self) -> &'static str {
        match self {
            Self::T0 => "t0",
            Self::T1 => "t1",
            Self::T2 => "t2",
            Self::T3 => "t3",
        }
    }
}

impl fmt::Display for TierLevel {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_key())
    }
}

/// Per-tier coherency model (`DP-X1`). *"The model is the contract. There is no
/// runtime flag to upgrade coherency without upgrading tier."*
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Coherency {
    /// T0 — in-process only; nothing to cohere.
    None,
    /// T1 — writer's in-memory copy is authoritative until the next snapshot.
    Snapshot,
    /// T2 — write-through, then invalidate asynchronously.
    WriteThroughAsyncInvalidate,
    /// T3 — the ack does not return until invalidation has fanned out.
    SyncInvalidateBeforeAck,
}

impl Coherency {
    /// The **exact cell text** this variant carries in `DP-X1`'s table.
    ///
    /// `V1-F4` found `Coherency` described as *"prose, so the oracle cannot
    /// cover it"* — while `DP-X1` is a markdown table the oracle's existing
    /// helper parses as-is. It was the one part of a tier that nothing watched.
    ///
    /// It is a transcribed string rather than a derived one on purpose: no
    /// normalisation maps *"Synchronous invalidate-before-ack"* onto
    /// `SyncInvalidateBeforeAck` without inventing rules, and a rule invented to
    /// make two things match is a check that will agree with anything. So the
    /// phrase is quoted once, here, and `tests/spec_oracle.rs` asserts the
    /// document still says it — the same shape as every `Duration` above.
    pub const fn doc_phrase(self) -> &'static str {
        match self {
            Self::None => "No coherency (in-process only)",
            Self::Snapshot => "Snapshot coherency",
            Self::WriteThroughAsyncInvalidate => "Write-through + async invalidate",
            Self::SyncInvalidateBeforeAck => "Synchronous invalidate-before-ack",
        }
    }
}

/// One tier. Sealed: the set is closed at four (`DP-A5`).
pub trait Tier: sealed::SealedTier + Copy + fmt::Debug + Send + Sync + 'static {
    /// Runtime form, for labels and keys.
    const LEVEL: TierLevel;

    /// `DP-X1` — what a reader is promised.
    const COHERENCY: Coherency;

    /// `DP-X7` — default cache TTL. `None` for T0, which is not cached.
    ///
    /// This is also `DP-A4`'s first role — *"shared hot-path cache (T0
    /// ephemeral excluded; T1/T2/T3 cache hits served from Redis)"* — as a
    /// type property rather than a deployment note. `spec_oracle.rs` parses
    /// the TTL column out of the tier spec and compares it to these
    /// constants, so editing T0's cell to a duration reds.
    ///
    /// A4's other two roles (pub/sub invalidation, streams) are infrastructure
    /// behaviour and have no subject in this crate — see the §4 row in the
    /// data-plane coverage run-state rather than a claim here.
    const CACHE_TTL: Option<Duration>;

    /// `DP-S3` — p99 budget from SDK call entry to SDK call return, on write.
    const WRITE_ACK_P99: Duration;

    /// `DP-S5` — sustained writes per second, per reality, at the V3 ceiling.
    /// `None` = unbounded (T0 never leaves the process).
    const SUSTAINED_WRITES_PER_S: Option<u32>;

    /// **`REC-102c`, PO-approved 2026-08-07 — may a write proceed while its
    /// store is unreachable?**
    ///
    /// This is the tier partition that resolved a live contradiction: `DP-F4`
    /// and `DP-F5` said *reject every write on a partition*, while
    /// `02_storage/SR06`'s correction said the island must **buffer and dilate
    /// ticks** rather than *"reject gameplay"*. Both were right about different
    /// tiers.
    ///
    /// * `true` (T0/T1/T2) — the island keeps stepping; ticks stretch. T2's ack
    ///   is on cache + outbox, and the outbox is on the reality's own Postgres.
    ///   **Gameplay does not stop because a sink is unreachable.**
    /// * `false` (T3) — `DP-T3` *is* invalidate-before-ack. A buffered T3 would
    ///   ack a durability promise that has not been kept, on exactly the data
    ///   T3 exists for: currency, canon promotion, permission grants.
    ///
    /// It is a `const` on the tier, and not a runtime policy toggle, for the
    /// same reason the tier itself is a type: `DP-A9`.
    const SURVIVES_STORE_OUTAGE: bool;
}

macro_rules! declare_tier {
    ($name:ident, $level:expr, $coherency:expr, $ttl:expr, $ack:expr, $rate:expr, $survives:expr, $doc:expr) => {
        #[doc = $doc]
        #[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
        pub struct $name;

        impl sealed::SealedTier for $name {}

        impl Tier for $name {
            const LEVEL: TierLevel = $level;
            const COHERENCY: Coherency = $coherency;
            const CACHE_TTL: Option<Duration> = $ttl;
            const WRITE_ACK_P99: Duration = $ack;
            const SUSTAINED_WRITES_PER_S: Option<u32> = $rate;
            const SURVIVES_STORE_OUTAGE: bool = $survives;
        }
    };
}

declare_tier!(
    T0,
    TierLevel::T0,
    Coherency::None,
    None,
    Duration::from_millis(1),
    None,
    true,
    "**Ephemeral** — in-process, lost on restart, invisible to every other \
     process. Eligible only if losing every instance on restart causes no \
     user-visible problem, nothing else ever reads it, and its lifetime is \
     bounded by one session (`DP-T0`)."
);

declare_tier!(
    T1,
    TierLevel::T1,
    Coherency::Snapshot,
    Some(Duration::from_secs(60)),
    Duration::from_millis(10),
    Some(5_000),
    true,
    "**Volatile** — in-memory live state, snapshotted to Redis; a crash may \
     lose up to 30s. Eligible if that loss is acceptable and the data is \
     high-churn or explicitly transient (`DP-T1`, eligibility revised in \
     Phase 4: the old \"at least 1/s sustained\" rule was a pre-channel-model \
     MMO assumption and was dropped)."
);

declare_tier!(
    T2,
    TierLevel::T2,
    Coherency::WriteThroughAsyncInvalidate,
    Some(Duration::from_secs(5 * 60)),
    Duration::from_millis(5),
    Some(500),
    true,
    "**Durable-async** — the default for most game data. Ack lands on cache + \
     outbox; the projection catches up asynchronously (`DP-T2`). When unsure \
     between tiers, this is the answer."
);

declare_tier!(
    T3,
    TierLevel::T3,
    Coherency::SyncInvalidateBeforeAck,
    Some(Duration::from_secs(10 * 60)),
    Duration::from_millis(50),
    Some(50),
    false,
    "**Durable-sync** — the ack returns only after invalidation has fanned \
     out, so every reader sees the new value before the writer is told it \
     succeeded (`DP-T3`). For money-adjacent and canon-critical writes only: \
     `DP-S3` prices it at 10x T2's ack and `DP-S5` at a tenth of its \
     throughput. A feature that hits T3 every tick is a design error."
);

/// The tier invariants, **checked by rustc rather than by a test binary.**
///
/// Every claim below is over `const`s, so a `#[test]` asserting them would be
/// asserting on constants — which clippy refuses, correctly: the assertion
/// belongs where the constant does. In a `const` block a violation is a **build
/// failure**, which is strictly stronger than a red test, and it means a
/// mis-tuned budget cannot reach a consumer even once.
const _: () = {
    // `REC-102c`, PO-approved: the degraded-mode partition. This block is where
    // the decision lives — prose in `07` is what the contradiction was made of.
    //
    // Stated as a COUNT plus a NAMED exception rather than four booleans, for
    // two reasons: `assert!(SOME_CONST_BOOL)` is a no-op clippy rightly refuses,
    // and the count is the actual invariant — *"exactly one tier refuses, and it
    // is the one whose definition IS invalidate-before-ack."* Flip any tier and
    // the sum moves; flip two and it still moves.
    //
    // **STATED LIMIT (`R2-9`): this sum is written over four NAMED tiers, so it
    // does not extend by itself.** A fifth tier that buffers would leave
    // `survivors == 3` false and this block silent about it, because the fifth
    // is not in the sum. Two mechanisms cover that gap and neither is here:
    // `spec_oracle::the_tier_set_in_source_matches_the_taxonomy_doc` reds when
    // the declared set stops matching `03_tier_taxonomy.md`, and
    // `no_tier_is_implemented_outside_the_declare_tier_macro` reds on a tier
    // hand-written past the macro. Written down rather than left implied,
    // because a reader arriving at a `const` block that names every tier will
    // reasonably assume it covers every tier.
    let survivors = T0::SURVIVES_STORE_OUTAGE as u8
        + T1::SURVIVES_STORE_OUTAGE as u8
        + T2::SURVIVES_STORE_OUTAGE as u8
        + T3::SURVIVES_STORE_OUTAGE as u8;
    assert!(
        survivors == 3,
        "exactly three tiers may buffer-and-dilate while their store is down"
    );
    assert!(
        (T3::SURVIVES_STORE_OUTAGE as u8) == 0,
        "and the refusing one must be T3: buffering a T3 acks a promise not kept"
    );

    // `DP-S3`'s ordering is not decorative — it is why T3's own doc says a
    // feature hitting T3 every tick is a design error. Invert it and the
    // taxonomy has stopped meaning anything. (`as_millis` is const; `PartialOrd`
    // for `Duration` is not.)
    assert!(T0::WRITE_ACK_P99.as_millis() < T1::WRITE_ACK_P99.as_millis());
    assert!(T2::WRITE_ACK_P99.as_millis() < T3::WRITE_ACK_P99.as_millis());
    assert!(T3::WRITE_ACK_P99.as_millis() >= T2::WRITE_ACK_P99.as_millis() * 10);

    // `DP-S5`: throughput falls as durability rises; T0 is unbounded because it
    // never leaves the process.
    assert!(T0::SUSTAINED_WRITES_PER_S.is_none());
    let (t1, t2, t3) = (
        T1::SUSTAINED_WRITES_PER_S.unwrap(),
        T2::SUSTAINED_WRITES_PER_S.unwrap(),
        T3::SUSTAINED_WRITES_PER_S.unwrap(),
    );
    assert!(t1 > t2 && t2 > t3);

    // `DP-X7`: *"No infinite TTL. An invalidation loss plus an infinite TTL =
    // permanent stale read."* Cap is 1h even for overrides.
    assert!(T0::CACHE_TTL.is_none());
    assert!(T1::CACHE_TTL.is_some() && T1::CACHE_TTL.unwrap().as_secs() <= 3600);
    assert!(T2::CACHE_TTL.is_some() && T2::CACHE_TTL.unwrap().as_secs() <= 3600);
    assert!(T3::CACHE_TTL.is_some() && T3::CACHE_TTL.unwrap().as_secs() <= 3600);
};

#[cfg(test)]
mod tests {
    use super::*;

    /// The `const _` block above is the real check; this exists so a reader
    /// running `cargo test` sees the numbers rather than only their absence.
    #[test]
    fn the_const_block_above_holds_and_here_are_its_values() {
        println!("T0 ack={:?} ttl={:?} rate={:?} survives={}",
            T0::WRITE_ACK_P99, T0::CACHE_TTL, T0::SUSTAINED_WRITES_PER_S, T0::SURVIVES_STORE_OUTAGE);
        println!("T1 ack={:?} ttl={:?} rate={:?} survives={}",
            T1::WRITE_ACK_P99, T1::CACHE_TTL, T1::SUSTAINED_WRITES_PER_S, T1::SURVIVES_STORE_OUTAGE);
        println!("T2 ack={:?} ttl={:?} rate={:?} survives={}",
            T2::WRITE_ACK_P99, T2::CACHE_TTL, T2::SUSTAINED_WRITES_PER_S, T2::SURVIVES_STORE_OUTAGE);
        println!("T3 ack={:?} ttl={:?} rate={:?} survives={}",
            T3::WRITE_ACK_P99, T3::CACHE_TTL, T3::SUSTAINED_WRITES_PER_S, T3::SURVIVES_STORE_OUTAGE);
    }

    /// `V2-F6` — **all four, not two.** This pinned `T2` and `T3` only, so
    /// renaming `T0`'s key to `"TIER_ZERO"` and `T1`'s to `"TIER_ONE"` passed
    /// every one of the crate's twenty tests. `as_key` is the tier token of the
    /// `DP-Ch5` cache key `dp:{reality}:{r|c}:{tier}:…`, so half the enum was a
    /// cache-key format nothing checked.
    ///
    /// The list is written out rather than looped, because a loop over
    /// `[T0,T1,T2,T3]` comparing `as_key()` to a lowercased `Debug` would be
    /// asserting that two spellings of the same match arm agree — which they
    /// would, always. The value of a pin is that it is a SECOND statement of
    /// the same fact, made in a different place.
    #[test]
    fn tier_keys_are_the_cache_key_form() {
        assert_eq!(TierLevel::T0.as_key(), "t0");
        assert_eq!(TierLevel::T1.as_key(), "t1");
        assert_eq!(TierLevel::T2.as_key(), "t2");
        assert_eq!(TierLevel::T3.as_key(), "t3");

        // ...and `Display` must agree with `as_key` for every tier, since the
        // two reach the same key by different routes.
        assert_eq!(T0::LEVEL.to_string(), "t0");
        assert_eq!(T1::LEVEL.to_string(), "t1");
        assert_eq!(T2::LEVEL.to_string(), "t2");
        assert_eq!(T3::LEVEL.to_string(), "t3");
    }
}
