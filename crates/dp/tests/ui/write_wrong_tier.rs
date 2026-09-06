//! `DP-R5` — *"No cross-tier mixing in a single write operation."*
//!
//! `Ledger` is a `T3` aggregate. This file writes it through `t2_write`.
//!
//! # Why this must be a COMPILE error and not a runtime one
//!
//! `DP-T3` is durable-sync: the ack means the event log has the write and the
//! invalidation has propagated, so a post-ack read on any node sees it.
//! `DP-T2` is durable-async: it acks after a local apply and an outbox append.
//! Sending a `T3` aggregate down the `T2` path therefore does not fail — it
//! **succeeds with a weaker promise than the aggregate was designed for**, and
//! the loss shows up later as a read that should have been impossible.
//!
//! A runtime `TierViolation` would be a fine second line of defence and does
//! exist for dynamic callers. It is the wrong mechanism for feature code, where
//! the tier is known at the call site and rustc can simply refuse.
//!
//! The bound is `A: DpAggregate<Tier = T2>` on `t2_write`, so this is an
//! ordinary associated-type mismatch.

use dp::{scope::RealityScope, tier::T3, DpAggregate, DpError};

struct Ledger;

impl DpAggregate for Ledger {
    type Tier = T3;
    type Scope = RealityScope;
    type Id = u64;
    type Delta = i64;
    type Projection = ();
    const TYPE_NAME: &'static str = "write_wrong_tier_fixture";
}

// Encode is implemented, so the ONLY thing wrong with the call below is the
// tier. Without this impl the file would still fail to compile -- for the wrong
// reason -- and the pin would stop testing DP-R5.
impl dp::Encode for Ledger {
    fn encode(_delta: &i64) -> Result<Vec<u8>, DpError> {
        Ok(Vec::new())
    }
}

struct NoBackend;

impl dp::WriteBackend for NoBackend {
    fn apply(&self, _req: &dp::WriteRequest<'_>) -> Result<dp::WriteAck, dp::DpError> {
        unimplemented!()
    }
}

fn main() {
    let ctx: &dp::SessionContext = todo!();
    // A T3 aggregate down the T2 path. Must not compile.
    let _ = dp::t2_write::<Ledger, _>(&NoBackend, ctx, 0, dp::KeyId::from(1u64), "k", 0, 1i64);
}
