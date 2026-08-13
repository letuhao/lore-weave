//! `DP-A14` / `DP-Ch14` — the MIRROR: a reality-scoped aggregate cannot be
//! written by the channel-scoped primitive.
//!
//! `Ledger` is `RealityScope`. `t2_write_channel` is bounded
//! `A: DpAggregate<Tier = T2, Scope = ChannelScope>`.
//!
//! # Why both directions, and not just the one that was broken
//!
//! `tests/ui/channel_read_wrong_scope.rs` gives the reason on the read side and
//! it holds identically here: the channel primitive ALSO has a runtime check
//! (a session that is not in a channel is refused), and one direction alone
//! makes it easy to assume the runtime check is what does the work — and to let
//! the type bound drift to something weaker without any test noticing.
//!
//! The runtime check and the bound answer different questions. The bound asks
//! *"is this aggregate addressed by a channel at all?"* — a design-time fact.
//! The runtime check asks *"does this session currently hold one?"* — a fact
//! about the caller's position. Neither substitutes for the other, and a file
//! that pins only one leaves the pair half-guarded.

use dp::{scope::RealityScope, tier::T2, DpAggregate, DpError};

struct Ledger;

impl DpAggregate for Ledger {
    type Tier = T2;
    type Scope = RealityScope;
    type Id = u64;
    type Delta = i64;
    type Projection = ();
    const TYPE_NAME: &'static str = "channel_write_wrong_scope_fixture";
}

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
    // A reality-scoped aggregate through the channel-scoped door. Must not compile.
    let _ =
        dp::t2_write_channel::<Ledger, _>(&NoBackend, ctx, 0, dp::KeyId::from(1u64), "k", 0, 1i64);
}
