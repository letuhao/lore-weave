//! `DP-K7` — *"`$tier` must match the tier trait of `$aggregate` — else
//! type-check failure."*
//!
//! That is a claim about rustc, so rustc checks it. `Inventory` is a `T2`
//! aggregate; this file asks `cache_key!` for a `T1` key on it.
//!
//! # Why this is the case worth pinning
//!
//! A wrong tier token does not fail — it SUCCEEDS at building the wrong key.
//! `dp:{reality}:r:t1:cache_key_fixture:{id}` is a perfectly well-formed string
//! that no reader will ever look at, because every legitimate read of a `T2`
//! aggregate computes `t2`. `DP-R4`'s stated violation mode is exactly this:
//! *"the write lands at one key, the read misses elsewhere"*, a silent
//! coherency bug that presents as a stale cache.
//!
//! So the tier is passed as a TYPE PARAMETER, not a string, and
//! `reality_key<A, T> where A: DpAggregate<Tier = T>` makes the mismatch an
//! ordinary type error at the call site.

use dp::{scope::RealityScope, tier::T2, DpAggregate};

struct Inventory;

impl DpAggregate for Inventory {
    type Tier = T2;
    type Scope = RealityScope;
    type Id = uuid::Uuid;
    type Delta = ();
    type Projection = ();
    const TYPE_NAME: &'static str = "cache_key_fixture";
}

struct Session;

fn main() {
    // A `T2` aggregate asked for a `T1` key. Must not compile.
    let _ = dp::cache_key!(todo!() as &dp::SessionContext, T1, Inventory, 1u64);
    let _ = Session;
}
