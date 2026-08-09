//! `DP-K4` — a channel-scoped aggregate cannot be read by the reality-scoped
//! primitive.
//!
//! `Chatter` is `ChannelScope`. `read_projection_reality` is bounded
//! `A: DpAggregate<Scope = RealityScope>`.
//!
//! # Why the bound rather than a runtime check
//!
//! Scope is an ADDRESS, not a permission. A reality-scoped read is served by
//! `reality_id` alone; a channel-scoped one needs a channel to say *which*
//! chatter. There is no correct value for the missing argument, so a runtime
//! check would be reporting a call that should never have been expressible.
//! `DP-A14` calls scope a design-time choice, and this is that choice held by
//! the type checker — the same mechanism `DP-R5` gets on the write side.

use dp::{scope::ChannelScope, tier::T2, DpAggregate, DpError};

struct Chatter;

impl DpAggregate for Chatter {
    type Tier = T2;
    type Scope = ChannelScope;
    type Id = u64;
    type Delta = ();
    type Projection = u32;
    const TYPE_NAME: &'static str = "read_wrong_scope_fixture";
}

impl dp::Decode for Chatter {
    fn decode(_bytes: &[u8]) -> Result<u32, DpError> {
        unimplemented!()
    }
}

struct NoStore;

impl dp::ReadBackend for NoStore {
    fn fetch(&self, _a: &'static str, _k: &str) -> Result<Option<Vec<u8>>, DpError> {
        unimplemented!()
    }
}

fn main() {
    let ctx: &dp::SessionContext = todo!();
    // A channel-scoped aggregate through the reality-scoped door. Must not compile.
    let _ = dp::read_projection_reality::<Chatter, _>(&NoStore, ctx, 0, "k");
}
