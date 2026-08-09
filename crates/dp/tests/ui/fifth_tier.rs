//! `S2.2(b)` — a feature crate may not mint a FIFTH tier.
//!
//! `DP-A5`: *"Pick the closer tier; if unsure, pick the safer one (higher tier).
//! Closed taxonomy, **no in-betweens**."* `22 §5`'s anti-pattern table says the
//! same in the imperative: *"❌ Pick a tier 'T1.5' or 'between T2 and T3'."*
//!
//! Both are review-gate sentences. The `Tier` trait is **sealed** — its
//! supertrait `sealed::SealedTier` is `pub(crate)` — so the closed set is held by
//! rustc. This file is a feature crate trying exactly that.
//!
//! # Why the `impl Sealed` line is here and must stay
//!
//! `S3.3`'s bite found this file failing for the **wrong reason**. Without the
//! line below, an author reaching for a fifth tier is stopped by *"the trait
//! bound `T1Point5: SealedTier` is not satisfied"* — which is still a failure, but
//! it is the failure of an **incomplete** impl, not of the seal. Removing the
//! seal did not make it compile, so the case was not testing the seal at all.
//!
//! With the line, the author does what an author would actually do: satisfy the
//! bound. The error then names the real guard — `module 'sealed' is private` —
//! and the bite flips as it must.

use core::time::Duration;
use dp::{Coherency, DpAggregate, RealityScope, Tier, TierLevel};

/// "T2 is too slow and T1 loses data, so we need something in between."
#[derive(Debug, Clone, Copy)]
struct T1Point5;

// The author does the obvious thing to satisfy the supertrait bound. THIS is
// the line the seal refuses.
impl dp::tier::sealed::SealedTier for T1Point5 {}

impl Tier for T1Point5 {
    const LEVEL: TierLevel = TierLevel::T2;
    const COHERENCY: Coherency = Coherency::Snapshot;
    const CACHE_TTL: Option<Duration> = Some(Duration::from_secs(120));
    const WRITE_ACK_P99: Duration = Duration::from_millis(7);
    const SUSTAINED_WRITES_PER_S: Option<u32> = Some(1_500);
    const SURVIVES_STORE_OUTAGE: bool = true;
}

struct Halfway;

impl DpAggregate for Halfway {
    type Tier = T1Point5;
    type Scope = RealityScope;
    type Id = u64;
    type Delta = ();
    type Projection = ();
    const TYPE_NAME: &'static str = "halfway";
}

fn main() {}
