//! `DP-K4` — the MIRROR of `read_wrong_scope.rs`: a reality-scoped aggregate
//! cannot be read by the channel-scoped primitive.
//!
//! # Why both directions are pinned rather than one
//!
//! `read_wrong_scope.rs` pins that a channel-scoped aggregate cannot go through
//! `read_projection_reality`. On its own that leaves the other half of the
//! claim untested, and the two functions are not symmetric in an obvious way:
//! the channel one has a RUNTIME check as well (a session with no channel), so
//! it would be easy to assume the runtime check is what does the work and let
//! the bound drift to something weaker.
//!
//! It is the bound that does the work. A reality-scoped aggregate has no
//! channel dimension at all, so reading it "in a channel" would key the same
//! aggregate differently per channel — the same entry, split N ways, which is a
//! cache-coherency bug that presents as a lost write. `DP-A14` calls scope a
//! design-time choice, and this is that choice held by the type checker in the
//! second direction.

use dp::{scope::RealityScope, tier::T2, DpAggregate, DpError};

struct Profile;

impl DpAggregate for Profile {
    type Tier = T2;
    type Scope = RealityScope;
    type Id = u64;
    type Delta = ();
    type Projection = u32;
    const TYPE_NAME: &'static str = "channel_read_wrong_scope_fixture";
}

impl dp::Decode for Profile {
    fn decode(_bytes: &[u8]) -> Result<u32, DpError> {
        unimplemented!()
    }
}

struct NoStore;

impl dp::ReadBackend for NoStore {
    fn fetch(&self, _req: &dp::ReadRequest<'_>) -> Result<Option<Vec<u8>>, DpError> {
        unimplemented!()
    }
}

fn main() {
    let ctx: &dp::SessionContext = todo!();
    // A reality-scoped aggregate through the channel-scoped door. Must not compile.
    let _ = dp::read_projection_channel::<Profile, _>(&NoStore, ctx, 0, dp::KeyId::from(1u64), "k");
}
