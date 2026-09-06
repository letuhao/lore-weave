//! `DP-A14` / `DFO-1` — a channel-scoped aggregate cannot be written by the
//! reality-scoped primitive.
//!
//! `Chatter` is `ChannelScope`. `t2_write` is bounded
//! `A: DpAggregate<Tier = T2, Scope = RealityScope>`.
//!
//! # This is the half that was missing, and its absence had a cost
//!
//! The READ side has had this bound since slice 4 —
//! `read_projection_reality` refuses a channel-scoped aggregate, and
//! `tests/ui/read_wrong_scope.rs` pins it. The WRITE side bounded `Tier` and
//! **not** `Scope`, and did no runtime scope check either, so this exact call
//! compiled and ran.
//!
//! It did not fail. `WriteRequest` had no channel field at all, so the write
//! reached the backend addressed to nothing, and per
//! `0014_channel_ordering.up.sql` an event with `channel_id = NULL` is a
//! **reality-scoped event** — a legitimate row that no channel subscriber will
//! ever read. The chat message is written, the channel never sees it, and
//! nothing anywhere reports a problem. A silent wrong answer is worse than the
//! `E0271` this file now pins, which is why the asymmetry was a defect rather
//! than a missing nicety.

use dp::{scope::ChannelScope, tier::T2, DpAggregate, DpError};

struct Chatter;

impl DpAggregate for Chatter {
    type Tier = T2;
    type Scope = ChannelScope;
    type Id = u64;
    type Delta = i64;
    type Projection = ();
    const TYPE_NAME: &'static str = "write_wrong_scope_fixture";
}

// Encode is implemented, so the ONLY thing wrong with the call below is the
// scope. Without this impl the file would still fail to compile -- for the
// wrong reason -- and the pin would stop testing DP-A14.
impl dp::Encode for Chatter {
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
    // A channel-scoped aggregate through the reality-scoped door. Must not compile.
    let _ = dp::t2_write::<Chatter, _>(&NoBackend, ctx, 0, dp::KeyId::from(1u64), "k", 0, 1i64);
}
