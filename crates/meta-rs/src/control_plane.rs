//! `5A` — the first REAL [`dp::ControlPlane`], over `reality_registry`.
//!
//! # Why this crate, and why this is the whole unblock
//!
//! `dp::RealityId` has a crate-private constructor, so the only way to obtain
//! one is [`dp::SessionContext::bind`], and the only way `bind` produces one is
//! from a `ControlPlane` answer. Until now the sole implementor was a
//! `#[cfg(test)]` double, which means **no production code could hold a
//! `RealityId` at all** — and that, not effort, is why `3E`'s adoption was
//! parked. This type is what unparks it.
//!
//! It lives in `meta-rs` because that is already the crate that answers *"where
//! does this reality live, and is it accepting commands"*:
//! [`MetaRead::get_reality_routing`] and [`RealityRouting::accepts_commands`]
//! both predate this file. Nothing new is being learned about a reality here —
//! it is being turned into a capability.
//!
//! `DP-C3` specifies a 13-RPC gRPC service. This is NOT that, and does not
//! pretend to be: it is the session/capability half, in-process, over the
//! registry this repo already has. `5C` puts a gRPC surface in front.
//!
//! # What it refuses, and why refusal is the interesting half
//!
//! A reality is bindable only if it EXISTS and ACCEPTS COMMANDS. The second is
//! the one worth having: a `Frozen`, `Archived` or `SoftDeleted` reality is a
//! perfectly real row, and handing out a capability for it would let a caller
//! address a world that has been closed. `RealityStatus::accepts_commands` is
//! the existing predicate for exactly that question, so this does not invent a
//! second answer to it.

use dp::{BindRequest, ControlPlane, DpError, VerifiedBind};
use uuid::Uuid;

use crate::routing::MetaRead;

/// How long a freshly minted capability is good for.
///
/// A default rather than a knob on every call: `DP-K2` binds once per session,
/// and a caller that could choose its own expiry could choose "never".
/// `RefreshCapability` (`5B`) is the sanctioned way to extend one.
pub const DEFAULT_CAPABILITY_TTL_MS: u64 = 15 * 60 * 1000;

/// Reads the wall clock. Injected so tests are deterministic without freezing
/// global time, and so the one place this crate touches a clock is visible.
pub trait Clock: Send + Sync {
    /// Milliseconds since the **Unix epoch** — the contract `dp::Millis`
    /// states, and the reason it must state it: this value is minted here and
    /// compared in another process.
    fn now_unix_ms(&self) -> u64;
}

/// The real clock.
#[derive(Debug, Clone, Copy, Default)]
pub struct SystemClock;

impl Clock for SystemClock {
    fn now_unix_ms(&self) -> u64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            // A pre-epoch system clock is absurd, and treating it as 0 would
            // mint an already-expired capability rather than a forged one.
            // Failing toward "expired" is the safe direction.
            .unwrap_or(0)
    }
}

/// Mints capability secrets.
///
/// A trait rather than a hardcoded call so the source is reviewable in one
/// place. The default is a v4 UUID, which the `uuid` crate draws from the OS
/// CSPRNG — 122 bits of entropy, which is a reasonable bearer token and is
/// **not** a claim that this is a signed or verifiable credential. `5B` and
/// `5C` decide what a capability really carries; this is the honest minimum
/// that is unguessable.
pub trait SecretSource: Send + Sync {
    /// Produce one unguessable bearer secret.
    fn mint(&self) -> String;
}

/// v4 UUID from the OS CSPRNG.
#[derive(Debug, Clone, Copy, Default)]
pub struct RandomSecret;

impl SecretSource for RandomSecret {
    fn mint(&self) -> String {
        Uuid::new_v4().to_string()
    }
}

/// A [`dp::ControlPlane`] backed by the meta reality registry.
pub struct MetaControlPlane<R, C = SystemClock, S = RandomSecret> {
    meta: R,
    clock: C,
    secrets: S,
    ttl_ms: u64,
}

impl<R: MetaRead> MetaControlPlane<R, SystemClock, RandomSecret> {
    /// The production constructor.
    pub fn new(meta: R) -> Self {
        Self {
            meta,
            clock: SystemClock,
            secrets: RandomSecret,
            ttl_ms: DEFAULT_CAPABILITY_TTL_MS,
        }
    }
}

impl<R, C, S> MetaControlPlane<R, C, S>
where
    R: MetaRead,
    C: Clock,
    S: SecretSource,
{
    /// Full control, for tests and for a deployment that needs a shorter TTL.
    pub fn with_parts(meta: R, clock: C, secrets: S, ttl_ms: u64) -> Self {
        Self { meta, clock, secrets, ttl_ms }
    }
}

impl<R, C, S> ControlPlane for MetaControlPlane<R, C, S>
where
    R: MetaRead + Send + Sync,
    C: Clock,
    S: SecretSource,
{
    fn verify_bind(&self, req: &BindRequest) -> Result<VerifiedBind, DpError> {
        let routing = self
            .meta
            .get_reality_routing(req.reality)
            // A meta read that FAILED is not a reality that is absent. Reporting
            // a transport fault as "no such reality" would tell a caller its
            // world is gone during a database blip.
            .map_err(|e| DpError::ControlPlaneUnavailable { reason: e.to_string() })?
            .ok_or_else(|| DpError::RealityMismatch {
                ctx: req.reality.to_string(),
                requested: "no such reality".to_string(),
            })?;

        // EXISTS is not ENOUGH. A frozen, archived or soft-deleted reality is a
        // real row, and a capability for it would let a caller address a closed
        // world.
        if !routing.accepts_commands() {
            return Err(DpError::RealityMismatch {
                ctx: req.reality.to_string(),
                requested: format!("status {:?} does not accept commands", routing.status),
            });
        }

        let now = self.clock.now_unix_ms();
        Ok(VerifiedBind {
            reality: req.reality,
            session: Uuid::new_v4(),
            capability_secret: self.secrets.mint(),
            expires_at_ms: now.saturating_add(self.ttl_ms),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::errors::MetaError;
    use crate::routing::{RealityRouting, RealityStatus};

    struct FixedClock(u64);
    impl Clock for FixedClock {
        fn now_unix_ms(&self) -> u64 {
            self.0
        }
    }

    struct FixedSecret;
    impl SecretSource for FixedSecret {
        fn mint(&self) -> String {
            "fixed".to_string()
        }
    }

    enum Answer {
        Row(RealityStatus),
        Absent,
        Broken,
    }

    struct Meta(Answer);
    impl MetaRead for Meta {
        fn get_reality_routing(&self, id: Uuid) -> Result<Option<RealityRouting>, MetaError> {
            match &self.0 {
                // `Backend` is meta-rs's transport-fault variant — the shape a
                // real database blip takes, which is the case this test is for.
                Answer::Broken => Err(MetaError::Backend("simulated read failure".into())),
                Answer::Absent => Ok(None),
                Answer::Row(status) => Ok(Some(RealityRouting {
                    reality_id: id,
                    db_host: "pg-shard-0.internal".into(),
                    db_name: "lw_reality_test".into(),
                    status: *status,
                    locale: "en".into(),
                    deploy_cohort: 0,
                })),
            }
        }
    }

    fn cp(a: Answer) -> MetaControlPlane<Meta, FixedClock, FixedSecret> {
        MetaControlPlane::with_parts(Meta(a), FixedClock(1_000), FixedSecret, 60_000)
    }

    fn req() -> BindRequest {
        BindRequest { reality: Uuid::from_u128(42), node: "pod-1".into() }
    }

    #[test]
    fn an_active_reality_binds_and_the_expiry_is_now_plus_ttl() {
        let v = cp(Answer::Row(RealityStatus::Active)).verify_bind(&req()).expect("bind");
        assert_eq!(v.reality, Uuid::from_u128(42));
        assert_eq!(v.expires_at_ms, 61_000, "now(1000) + ttl(60000)");
        assert_eq!(v.capability_secret, "fixed");
    }

    #[test]
    fn pending_close_still_binds_because_it_still_accepts_commands() {
        // Not an arbitrary choice: RealityRouting::accepts_commands already
        // says Active | PendingClose, and this must not invent a second answer.
        assert!(cp(Answer::Row(RealityStatus::PendingClose)).verify_bind(&req()).is_ok());
    }

    #[test]
    fn a_closed_reality_is_refused_even_though_its_row_exists() {
        for status in [
            RealityStatus::Frozen,
            RealityStatus::Archived,
            RealityStatus::SoftDeleted,
            RealityStatus::Dropped,
            RealityStatus::Provisioning,
        ] {
            let e = cp(Answer::Row(status)).verify_bind(&req()).expect_err("must refuse");
            assert_eq!(e.variant_name(), "RealityMismatch", "status {status:?}");
            assert!(
                e.to_string().contains("does not accept commands"),
                "status {status:?}: {e}"
            );
        }
    }

    #[test]
    fn an_unknown_reality_is_a_mismatch_not_an_outage() {
        let e = cp(Answer::Absent).verify_bind(&req()).expect_err("absent");
        assert_eq!(e.variant_name(), "RealityMismatch");
    }

    #[test]
    fn a_failed_meta_read_is_an_outage_not_a_missing_reality() {
        // The distinction that matters operationally: reporting a database blip
        // as "no such reality" tells a caller its world is gone.
        let e = cp(Answer::Broken).verify_bind(&req()).expect_err("broken");
        assert_eq!(e.variant_name(), "ControlPlaneUnavailable");
    }

    #[test]
    fn two_binds_get_different_sessions_and_different_secrets() {
        let plane = MetaControlPlane::new(Meta(Answer::Row(RealityStatus::Active)));
        let a = plane.verify_bind(&req()).expect("a");
        let b = plane.verify_bind(&req()).expect("b");
        assert_ne!(a.session, b.session, "session ids must not repeat");
        assert_ne!(a.capability_secret, b.capability_secret, "secrets must not repeat");
    }

    /// The end-to-end shape: a real ControlPlane produces a real `RealityId`.
    /// This is the thing that was impossible before this file existed.
    #[test]
    fn bind_through_this_plane_yields_a_usable_session_context() {
        let plane = cp(Answer::Row(RealityStatus::Active));
        let ctx = dp::SessionContext::bind(&plane, req(), 1_000).expect("bind");
        assert_eq!(ctx.reality_id().as_uuid(), Uuid::from_u128(42));
        assert!(ctx.check_live(60_999).is_ok(), "inside the TTL");
        assert!(ctx.check_live(61_000).is_err(), "at expiry");
    }
}
