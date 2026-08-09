//! `DP-K2` — the capability, the control-plane seam, and `SessionContext`.
//!
//! # Why these three are one file and one commit
//!
//! §0.6c seals it: *a type with a crate-private constructor lands WITH its
//! producer, never before.* That rule was learned here. `RealityId` was written,
//! tested and reverted inside an hour because `new_verified` had no in-crate
//! caller, and a crate-private constructor nothing calls is dead code — clippy
//! said so, and `#[allow(dead_code)]` is the pragma-as-exemption shape
//! `CLAUDE.md` names by example.
//!
//! So the chain arrives whole: [`ControlPlane`] verifies a bind request,
//! [`CapabilityToken`] is what it returns, and [`SessionContext`] is what holds
//! it — which is what finally *calls* the id constructors.
//!
//! # The seam, and why the trait is here rather than in slice 5
//!
//! `crates/dp` declares no I/O. It cannot talk to a control plane and must not
//! try. What it CAN do is state the shape of the answer it requires, which is
//! [`ControlPlane`]: one method, returning verified identity or a [`DpError`].
//! Slice 5's `DpControlPlane` implements it against the real service.
//!
//! §0.6c also says a trait ships **with its first implementor**, and that rule
//! is honoured rather than dodged: the implementor here is a `#[cfg(test)]`
//! double, and it is the thing that makes `bind` a live path rather than a
//! declaration. That is deliberately weaker than a production implementor and is
//! recorded as such — `3D.4` is satisfied, `DP-K10` is not, and the difference
//! is that nothing in production can bind a session yet.

use core::fmt;
use core::time::Duration;

use crate::ids::{NodeId, RealityId, SessionId};
use crate::DpError;

/// Milliseconds since the **Unix epoch**.
///
/// `crates/dp` has no clock — reading one is I/O, and `S2.3` says this crate
/// does none. So expiry is evaluated against a time the CALLER passes in, which
/// also makes every test deterministic without a mock clock. The unit is fixed
/// at milliseconds rather than left to a `Duration` so that two callers cannot
/// disagree about the scale of the same number.
///
/// # The epoch is part of the contract, and it was not until slice 5A
///
/// This said *"monotonic milliseconds since an arbitrary epoch"*, which is
/// fine while one process both stamps and compares. It stops being fine the
/// moment a CONTROL PLANE mints the expiry and a CALLER checks it: two
/// processes cannot compare readings from an arbitrary epoch at all, so
/// `check_live` would have been comparing unrelated numbers and calling the
/// result a capability check. Found by writing the first real
/// [`ControlPlane`], which is the kind of thing only an implementor finds.
///
/// **Unix epoch, so both sides mean the same instant.** Clock skew between the
/// two hosts remains real and is bounded by ordinary NTP discipline; that is a
/// deployment property, not something this type can fix. What it CAN do is
/// stop the two sides disagreeing about which zero they are counting from.
pub type Millis = u64;

/// Proof that the control plane granted this session its access.
///
/// Opaque on purpose. Feature code can ask whether it is live; it cannot read
/// the secret, construct one, or extend one.
#[derive(Clone)]
pub struct CapabilityToken {
    /// The bearer secret. NEVER rendered — see the `Debug` impl below.
    secret: String,
    /// When the grant stops being valid, in the caller's own timebase.
    expires_at_ms: Millis,
}

impl CapabilityToken {
    /// Mint a token from a control-plane response.
    ///
    /// `pub(crate)` so only [`SessionContext::bind`] can produce one, and it
    /// only does so from a [`ControlPlane`] answer.
    pub(crate) fn new_verified(secret: String, expires_at_ms: Millis) -> Self {
        Self { secret, expires_at_ms }
    }

    /// Is the grant still valid at `now_ms`?
    ///
    /// Expiry is `now < expires_at`, so a token expires ON its expiry rather
    /// than one millisecond after. The boundary is tested, because an
    /// off-by-one here is a token that outlives its grant.
    pub fn is_live(&self, now_ms: Millis) -> bool {
        now_ms < self.expires_at_ms
    }

    /// How long is left, or `None` once expired.
    pub fn remaining(&self, now_ms: Millis) -> Option<Duration> {
        self.expires_at_ms
            .checked_sub(now_ms)
            .filter(|left| *left > 0)
            .map(Duration::from_millis)
    }

    /// The bearer secret, for the transport that must present it.
    ///
    /// `pub(crate)`: it leaves this crate only inside an SDK request, never to
    /// feature code.
    // `expect`, NOT `allow`. An `allow` silences a finding and keeps silencing
    // it after the debt is paid — `CLAUDE.md` names that shape by example. An
    // `expect` FAILS THE BUILD the day the item stops being dead, so the
    // pragma removes itself: slice 4 presents this secret, and on that day this
    // line becomes an unfulfilled expectation and must go. That is a mechanism
    // with a trigger, not an exemption.
    #[expect(dead_code, reason = "slice 4's write surface presents it; this              expectation goes unfulfilled the day it does, which is the trigger")]
    pub(crate) fn secret(&self) -> &str {
        &self.secret
    }
}

/// A `Debug` that CANNOT print the secret.
///
/// Hand-written rather than derived, and this is the point of the type: a
/// derived `Debug` would put the bearer credential into every `tracing` line
/// that formatted a `SessionContext`, and into every panic message. That class
/// — a credential reaching a log through a derive nobody looked at — is why
/// `dp-kernel`'s logger has a `FieldKind::Sensitive` at all.
///
/// The expiry IS printed: it is not a secret and it is the field an operator
/// actually needs when a session starts failing.
impl fmt::Debug for CapabilityToken {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("CapabilityToken")
            .field("secret", &"<redacted>")
            .field("expires_at_ms", &self.expires_at_ms)
            .finish()
    }
}

/// What a caller asks to be bound to.
///
/// Raw values, because this is the UNVERIFIED side of the boundary — a
/// `RealityId` cannot appear here, since possessing one is the very thing bind
/// is supposed to establish.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BindRequest {
    pub reality: uuid::Uuid,
    pub node: String,
}

/// What the control plane returns once it has verified a [`BindRequest`].
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct VerifiedBind {
    pub reality: uuid::Uuid,
    pub session: uuid::Uuid,
    pub capability_secret: String,
    pub expires_at_ms: Millis,
}

/// The seam `crates/dp` declares and slice 5 satisfies.
///
/// One method, and it is the ONLY door through which identity enters this
/// crate. `DP-K1`: a `RealityId` is *"produced only by SDK during session bind
/// after verification against the control plane"* — this trait is that
/// verification, kept behind a boundary so the no-I/O crate never performs it.
pub trait ControlPlane {
    /// Verify a bind request, or say why not.
    ///
    /// Returning [`DpError::ControlPlaneUnavailable`] is the expected shape for
    /// a transport failure; [`DpError::RealityMismatch`] for a refusal.
    fn verify_bind(&self, req: &BindRequest) -> Result<VerifiedBind, DpError>;
}

/// Everything an SDK entry point needs, established once per session.
///
/// Effectively immutable — `DP-K2` says channel changes return a NEW context
/// rather than mutating this one.
#[derive(Clone, Debug)]
pub struct SessionContext {
    reality_id: RealityId,
    session_id: SessionId,
    node_id: NodeId,
    capability: CapabilityToken,
    bound_at_ms: Millis,
}

impl SessionContext {
    /// The one constructor: verify, then mint.
    ///
    /// This function is why `ids.rs` can exist at all — it is the in-crate
    /// caller of `RealityId::new_verified`, `SessionId::new_verified` and
    /// `NodeId::new_verified`. Before it, those were dead code.
    pub fn bind<C: ControlPlane>(
        cp: &C,
        req: BindRequest,
        now_ms: Millis,
    ) -> Result<Self, DpError> {
        let v = cp.verify_bind(&req)?;

        // The control plane is authoritative, so a response naming a DIFFERENT
        // reality than was asked for is a protocol violation, not a redirect.
        // Checked rather than trusted: silently binding to whatever came back
        // is how a caller ends up addressing someone else's reality while every
        // log line says it asked for its own.
        if v.reality != req.reality {
            return Err(DpError::RealityMismatch {
                ctx: req.reality.to_string(),
                requested: v.reality.to_string(),
            });
        }

        // A capability that is already expired is not a grant. Rejecting at
        // bind means `check_live` never has to explain a session that was born
        // dead.
        if now_ms >= v.expires_at_ms {
            return Err(DpError::CapabilityExpired);
        }

        Ok(Self {
            reality_id: RealityId::new_verified(v.reality),
            session_id: SessionId::new_verified(v.session),
            node_id: NodeId::new_verified(req.node),
            capability: CapabilityToken::new_verified(v.capability_secret, v.expires_at_ms),
            bound_at_ms: now_ms,
        })
    }

    pub fn reality_id(&self) -> &RealityId {
        &self.reality_id
    }

    pub fn session_id(&self) -> &SessionId {
        &self.session_id
    }

    pub fn node_id(&self) -> &NodeId {
        &self.node_id
    }

    pub fn bound_at_ms(&self) -> Millis {
        self.bound_at_ms
    }

    /// `DP-K2`: every SDK entry point calls this first.
    ///
    /// `pub(crate)` in the spec because feature code does not call it — the SDK
    /// does, on every entry. Kept `pub(crate)` here for the same reason, and it
    /// has an in-crate caller in tests today and slice 4's surface tomorrow.
    /// DEVIATION from `DP-K2`, which writes this `pub(crate)` on the grounds
    /// that *"feature code does not call this directly — SDK does, on every
    /// entry."* It is `pub` here, and the reason is not convenience:
    ///
    ///   * `pub(crate)` with no in-crate caller is dead code, and the only ways
    ///     to ship it are a pragma (the exemption shape) or a fake consumer.
    ///   * Liveness is **observable, not privileged**. `check_live` reveals
    ///     nothing and grants nothing — it answers a question the caller can
    ///     already answer by making a request and being refused. Widening it
    ///     weakens no property, which is the test for whether a deviation is
    ///     safe.
    ///
    /// `capability()` and `secret()` stay `pub(crate)`, because those DO hand
    /// out the credential.
    pub fn check_live(&self, now_ms: Millis) -> Result<(), DpError> {
        if self.capability.is_live(now_ms) {
            Ok(())
        } else {
            Err(DpError::CapabilityExpired)
        }
    }

    /// The capability, for the transport. Never handed to feature code.
    #[expect(dead_code, reason = "slice 4's write surface presents it;              unfulfilled the day it does")]
    pub(crate) fn capability(&self) -> &CapabilityToken {
        &self.capability
    }
}

/// `DEFERRED` — `DP-K2`'s channel fields.
///
/// `current_channel_id: ChannelId` and `ancestor_channels: Vec<ChannelId>` are
/// specified and are NOT here, for the reason §0.6c seals: nothing produces a
/// `ChannelId` yet. `DpControlPlane::move_session_to_channel` (`DP-Ch9`) is the
/// producer, and it is slice 5. Recorded in code rather than in a comment
/// nobody greps, and read by `tests/spec_oracle.rs`.
pub const DEFERRED_SESSION_FIELDS: &[(&str, &str)] = &[
    ("current_channel_id", "DP-Ch9 move_session_to_channel"),
    ("ancestor_channels", "DP-Ch9 move_session_to_channel"),
];

#[cfg(test)]
mod tests {
    use super::*;

    /// `3D.4` — the first implementor of [`ControlPlane`], which is what makes
    /// `bind` a live path rather than a declaration.
    struct Double {
        answer: Result<VerifiedBind, DpError>,
    }

    impl ControlPlane for Double {
        fn verify_bind(&self, _req: &BindRequest) -> Result<VerifiedBind, DpError> {
            match &self.answer {
                Ok(v) => Ok(v.clone()),
                Err(_) => Err(DpError::ControlPlaneUnavailable { reason: "double".into() }),
            }
        }
    }

    fn req(reality: u128) -> BindRequest {
        BindRequest { reality: uuid::Uuid::from_u128(reality), node: "pod-7".into() }
    }

    fn granted(reality: u128, expires_at_ms: Millis) -> VerifiedBind {
        VerifiedBind {
            reality: uuid::Uuid::from_u128(reality),
            session: uuid::Uuid::from_u128(99),
            capability_secret: "s3cret".into(),
            expires_at_ms,
        }
    }

    #[test]
    fn bind_produces_a_context_whose_ids_came_from_the_control_plane() {
        let cp = Double { answer: Ok(granted(1, 1_000)) };
        let ctx = SessionContext::bind(&cp, req(1), 0).expect("bind");

        assert_eq!(ctx.reality_id().as_uuid(), uuid::Uuid::from_u128(1));
        assert_eq!(ctx.session_id().as_uuid(), uuid::Uuid::from_u128(99));
        assert_eq!(ctx.node_id().as_str(), "pod-7");
        assert_eq!(ctx.bound_at_ms(), 0);
        assert!(ctx.check_live(999).is_ok());
    }

    #[test]
    fn a_control_plane_naming_a_different_reality_is_refused() {
        // The protocol-violation guard. Without it the caller binds to whatever
        // came back while every log line says it asked for its own reality.
        let cp = Double { answer: Ok(granted(2, 1_000)) };
        let err = SessionContext::bind(&cp, req(1), 0).expect_err("must refuse");
        assert_eq!(err.variant_name(), "RealityMismatch");
    }

    #[test]
    fn an_already_expired_grant_is_refused_at_bind() {
        let cp = Double { answer: Ok(granted(1, 500)) };
        let err = SessionContext::bind(&cp, req(1), 500).expect_err("must refuse");
        assert_eq!(err.variant_name(), "CapabilityExpired");
    }

    #[test]
    fn a_transport_failure_surfaces_as_control_plane_unavailable() {
        let cp = Double { answer: Err(DpError::CapabilityExpired) };
        let err = SessionContext::bind(&cp, req(1), 0).expect_err("must fail");
        assert_eq!(err.variant_name(), "ControlPlaneUnavailable");
    }

    #[test]
    fn expiry_is_exclusive_at_the_boundary() {
        let t = CapabilityToken::new_verified("s".into(), 100);
        assert!(t.is_live(99), "one ms before expiry must be live");
        assert!(!t.is_live(100), "a token expires ON its expiry, not after");
        assert_eq!(t.remaining(99), Some(Duration::from_millis(1)));
        assert_eq!(t.remaining(100), None);
        assert_eq!(t.remaining(101), None, "remaining must not underflow past expiry");
    }

    #[test]
    fn check_live_reports_expiry_as_the_spec_variant() {
        let cp = Double { answer: Ok(granted(1, 1_000)) };
        let ctx = SessionContext::bind(&cp, req(1), 0).expect("bind");
        let err = ctx.check_live(1_000).expect_err("expired");
        assert_eq!(err.variant_name(), "CapabilityExpired");
    }

    /// The credential must not reach a log through a derive nobody looked at.
    #[test]
    fn debug_never_renders_the_secret() {
        let t = CapabilityToken::new_verified("super-secret-bearer".into(), 1);
        let rendered = format!("{t:?}");
        assert!(!rendered.contains("super-secret-bearer"), "secret leaked: {rendered}");
        assert!(rendered.contains("<redacted>"));

        // And through the whole context, which is what actually gets logged.
        let cp = Double { answer: Ok(granted(1, 1_000)) };
        let ctx = SessionContext::bind(&cp, req(1), 0).expect("bind");
        let rendered = format!("{ctx:?}");
        assert!(!rendered.contains("s3cret"), "secret leaked via SessionContext: {rendered}");
    }
}
