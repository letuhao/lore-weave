//! Shared test support: how a TEST obtains a `dp::RealityId`.
//!
//! # Why this exists rather than a copy in each test file
//!
//! `3E` made `Manager` and `recover_writer_state` take a verified
//! `dp::RealityId`, and the only way to hold one is a `SessionContext::bind`
//! against a `ControlPlane`. Production binds against the real one
//! (`commit_service::reality_bind`). A test cannot: these tests run against a
//! throwaway per-reality Postgres with no meta registry behind it, and a reality
//! they invent will never be in one.
//!
//! So they bind against a double. That is the SAME thing `crates/dp`'s own
//! tests and `dp-kernel`'s `dp_backend` tests do, and it is not a weakening of
//! the guarantee: the guarantee is that PRODUCTION code cannot forge one, and
//! production code here goes through `reality_bind` against a real registry. A
//! test's double lives in `tests/`, is compiled only into test targets, and
//! cannot be reached from `src/`.
//!
//! One copy rather than eight, because eight copies of a security-relevant
//! double is eight chances for one of them to quietly start returning something
//! else.

use dp::{BindRequest, ControlPlane, DpError, RealityId, ServiceIdentity, SessionContext, VerifiedBind};
use uuid::Uuid;

/// A control plane that grants whatever it is asked for.
///
/// Deliberately trivial: these tests are about writer leases, recovery and
/// failover, not about the control plane's refusals — those have their own
/// tests in `meta-rs`, including live ones. A double with opinions here would
/// be a second, weaker copy of that logic.
struct AlwaysGrants;

impl ControlPlane for AlwaysGrants {
    fn verify_bind(&self, req: &BindRequest) -> Result<VerifiedBind, DpError> {
        Ok(VerifiedBind {
            reality: req.reality,
            session: Uuid::new_v4(),
            capability_secret: "test-double".to_string(),
            // Far enough out that no test's wall-clock reading expires it
            // mid-run, and finite so it is still a real expiry rather than a
            // disabled check.
            expires_at_ms: u64::MAX / 2,
        })
    }
}

/// Bind `reality` through the double and hand back the verified id.
///
/// Panics rather than returning a `Result`: a test that cannot bind has a
/// broken fixture, and threading an error through every call site would bury
/// the one line that matters.
pub fn verified_reality(reality: Uuid) -> RealityId {
    let ctx = SessionContext::bind(
        &AlwaysGrants,
        BindRequest {
            reality,
            node: "commit-service-test".to_string(),
            service: ServiceIdentity::new("commit-service-test").expect("valid identity"),
        },
        0,
    )
    .expect("the double grants every bind");
    ctx.reality_id().to_owned()
}
