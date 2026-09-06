//! Shared test support: how an INTEGRATION test obtains a `dp::RealityId`.
//!
//! `3E` made the embedding queue's inward types take `dp::RealityId`, and the
//! only way to hold one is a `SessionContext::bind` against a `ControlPlane`.
//! Production binds against the real one in `bin/embedding_worker.rs`, which
//! already holds a meta pool; these tests run against a throwaway per-reality
//! database with no registry behind it, so they bind against a double.
//!
//! The crate has a `#[cfg(test)]` twin of this in `embedding_queue/mod.rs`. Two
//! copies is not duplication anyone can remove: a `#[cfg(test)]` item is not
//! visible to an integration test, and an integration-test module is not
//! visible to the crate's own unit tests. They are two compilation contexts,
//! and the alternative — exporting a test affordance from the library — would
//! put a bind-anything door in the production surface.

use dp::{BindRequest, ControlPlane, DpError, RealityId, ServiceIdentity, SessionContext, VerifiedBind};
use uuid::Uuid;

/// Grants whatever it is asked for. These tests are about the embedding queue,
/// not about the control plane's refusals — those have their own tests in
/// `meta-rs`, including live ones against a real registry.
struct AlwaysGrants;

impl ControlPlane for AlwaysGrants {
    fn verify_bind(&self, req: &BindRequest) -> Result<VerifiedBind, DpError> {
        Ok(VerifiedBind {
            reality: req.reality,
            session: Uuid::new_v4(),
            capability_secret: "test-double".to_string(),
            // Far enough out that no test's wall-clock reading expires it
            // mid-run, and finite so it is still a real expiry.
            expires_at_ms: u64::MAX / 2,
        })
    }
}

/// Bind `reality` through the double and hand back the verified id.
pub fn verified_reality(reality: Uuid) -> RealityId {
    SessionContext::bind(
        &AlwaysGrants,
        BindRequest {
            reality,
            node: "world-service-test".to_string(),
            service: ServiceIdentity::new("world-service-test").expect("valid identity"),
        },
        0,
    )
    .expect("the double grants every bind")
    .reality_id()
    .to_owned()
}
