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
//! `DP-C3` specifies a 26-RPC gRPC service. This is NOT that, and does not
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
use crate::session_store::{capability_digest, CapabilityStore, IssuedCapability, SessionRecord};

/// How long a freshly minted capability is good for.
///
/// A default rather than a knob on every call: `DP-K2` binds once per session,
/// and a caller that could choose its own expiry could choose "never".
/// [`MetaControlPlane::refresh_capability`] is the sanctioned way to extend one,
/// and it applies this same TTL from `now` rather than from the old expiry — so
/// a chain of refreshes cannot accumulate a longer grant than a fresh bind.
///
/// # This number IS the revocation window, and it was 3× the spec
///
/// It shipped at 15 minutes. `05_control_plane_spec.md` says 5, three times and
/// consistently: *"Short expiry (5 min) bounds blast radius"* · *"Continues
/// existing session operations until capabilities expire (5 min)"* · and
/// `DP-C8`'s signing-key rule, *"2× the max capability lifetime (10 minutes)"*,
/// which only resolves if the maximum is 5.
///
/// The drift mattered because of what this number MEANS. `DP-C8` reaches
/// revocation through expiry rather than through a revocation list — `DP-C3`
/// budgets the control plane at ≤100 req/s globally, so validating every write
/// was never the design. **So the TTL is the upper bound on how long a REVOKED
/// session keeps writing**, and at 15 minutes it was three times the bound the
/// spec chose.
pub const DEFAULT_CAPABILITY_TTL_MS: u64 = 5 * 60 * 1000;

/// The refresh lead must be comfortably SHORTER than the TTL.
///
/// `crates/dp` sets the lead and never sees a TTL; this crate chooses the TTL
/// and can see both, so the relationship is asserted where it is checkable.
/// A lead at or above the TTL makes every capability due the instant it is
/// issued — a refresh policy that is really a request amplifier, and one that
/// would look like a control-plane load problem rather than a constant.
const _: () = assert!(
    dp::REFRESH_LEAD_MS * 2 <= DEFAULT_CAPABILITY_TTL_MS,
    "the refresh lead must leave at least as much time again before it is due; \
     raise DEFAULT_CAPABILITY_TTL_MS or lower dp::REFRESH_LEAD_MS"
);

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
///
/// `K` is the capability store (`5B`). It is a required parameter rather than an
/// optional one: a control plane that issues capabilities it does not record can
/// neither validate nor revoke them, and making that state constructible would
/// leave the 5A behaviour reachable by omission.
pub struct MetaControlPlane<R, K, C = SystemClock, S = RandomSecret> {
    meta: R,
    store: K,
    clock: C,
    secrets: S,
    ttl_ms: u64,
}

impl<R: MetaRead, K: CapabilityStore> MetaControlPlane<R, K, SystemClock, RandomSecret> {
    /// The production constructor.
    pub fn new(meta: R, store: K) -> Self {
        Self {
            meta,
            store,
            clock: SystemClock,
            secrets: RandomSecret,
            ttl_ms: DEFAULT_CAPABILITY_TTL_MS,
        }
    }
}

impl<R, K, C, S> MetaControlPlane<R, K, C, S>
where
    R: MetaRead,
    K: CapabilityStore,
    C: Clock,
    S: SecretSource,
{
    /// Full control, for tests and for a deployment that needs a shorter TTL.
    pub fn with_parts(meta: R, store: K, clock: C, secrets: S, ttl_ms: u64) -> Self {
        Self { meta, store, clock, secrets, ttl_ms }
    }

    /// The registry row for a reality, or `None` if there is no such reality.
    ///
    /// Exposed because `DP-C3`'s `VerifyReality` and `ResolveReality` ask the
    /// registry questions that are not binds, and routing a read through
    /// `verify_bind` would mint a capability as a side effect of asking whether
    /// a world exists.
    pub fn reality_routing(
        &self,
        reality: Uuid,
    ) -> Result<Option<crate::routing::RealityRouting>, crate::errors::MetaError> {
        self.meta.get_reality_routing(reality)
    }

    /// Where a session is pinned (`GetSessionNode`, `DP-C1`), or `None`.
    ///
    /// Answers for a REVOKED or EXPIRED session too, and that is deliberate:
    /// routing and authorization are different questions. A node handling a
    /// late-arriving message needs to know where the session lived even after
    /// the grant died, and returning `None` would make a stale route
    /// indistinguishable from a session that never existed.
    pub fn session_node(
        &self,
        session_id: Uuid,
    ) -> Result<Option<String>, crate::errors::MetaError> {
        Ok(self.store.find_by_session(session_id)?.map(|r| r.node_id))
    }

    /// The clock this plane stamps expiries with.
    ///
    /// A transport needs it to evaluate `now` on the SAME clock the expiries
    /// were minted against — reading a second clock is how two components end
    /// up disagreeing about whether a capability is live.
    pub fn now_unix_ms(&self) -> u64 {
        self.clock.now_unix_ms()
    }

    /// Is this presented secret a live capability, and whose?
    ///
    /// The server-side counterpart of `dp::SessionContext::check_live`. The SDK
    /// side can only tell whether its own copy of the expiry has passed; only
    /// this can tell whether the grant was REVOKED, which is the half that
    /// matters during an incident.
    ///
    /// # Why the three outcomes are three different errors
    ///
    /// * a digest with no row — [`DpError::SessionNotFound`]. Includes a
    ///   forged secret, a secret from a wiped store, and a typo.
    /// * a row that exists but is dead — [`DpError::CapabilityExpired`], the
    ///   same variant the SDK raises, so a caller sees one meaning for one fact
    ///   regardless of which side noticed.
    /// * a store that could not be read — [`DpError::ControlPlaneUnavailable`].
    ///   **Never** collapsed into "invalid": a database blip would otherwise
    ///   present as every capability in the system being forged at once, and
    ///   the operator would go looking for an attacker.
    pub fn validate_capability(
        &self,
        presented_secret: &str,
        now_ms: u64,
    ) -> Result<SessionRecord, DpError> {
        let digest = capability_digest(presented_secret);
        let found = self
            .store
            .lookup(&digest)
            .map_err(|e| DpError::ControlPlaneUnavailable { reason: e.to_string() })?;

        let Some(record) = found else {
            // The digest, not the secret, and not even the digest in full: a
            // validation failure is exactly when something is likely to be
            // logged, and a message that echoes what was presented hands the
            // log reader a credential. The session is unknown by construction,
            // so there is nothing more specific to name.
            return Err(DpError::SessionNotFound { session_id: "<unknown capability>".to_string() });
        };

        if !record.is_live(now_ms) {
            return Err(DpError::CapabilityExpired);
        }
        Ok(record)
    }

    /// `RefreshCapability` (`DP-C3`) — extend a live grant without re-issuing.
    ///
    /// The secret does not change. Under a signed-JWT model a refresh must mint
    /// a new token because the expiry is *inside* the signed payload; under
    /// lookup validation the expiry lives in the row, so the refresh is an
    /// UPDATE and the secret never travels a second time. That is a real
    /// consequence of the sealed deviation, and it is the good direction: each
    /// additional transmission of a bearer secret is another chance to leak it.
    ///
    /// # Resurrection is the failure this guards
    ///
    /// A refresh that did not first check liveness would revive an EXPIRED or
    /// REVOKED session by moving its expiry forward — which would make
    /// revocation a suggestion, since a revoked holder could simply refresh.
    /// The liveness check therefore happens here AND in the store's `extend`
    /// (`WHERE revoked_at IS NULL AND expires_at > now`), because this one is a
    /// read followed by a write and the row can change in between.
    pub fn refresh_capability(
        &self,
        presented_secret: &str,
        now_ms: u64,
    ) -> Result<VerifiedBind, DpError> {
        let record = self.validate_capability(presented_secret, now_ms)?;
        let new_expiry = now_ms.saturating_add(self.ttl_ms);

        let extended = self
            .store
            .extend(record.session_id, record.expires_at_ms, new_expiry)
            .map_err(|e| DpError::ControlPlaneUnavailable { reason: e.to_string() })?;

        if !extended {
            // Lost the race: revoked or expired between the read and the write.
            // Reporting success here would hand back an expiry the row does not
            // have, and the caller would trust it until its next call failed.
            return Err(DpError::CapabilityExpired);
        }

        Ok(VerifiedBind {
            reality: record.reality_id,
            session: record.session_id,
            capability_secret: presented_secret.to_string(),
            expires_at_ms: new_expiry,
        })
    }

    /// Revoke a session's capability. Returns `false` if there was nothing live
    /// to revoke.
    ///
    /// This is `DP-C8`'s immediate revocation, and it is where the sealed
    /// deviation pays for itself rather than costing: the spec reaches immediate
    /// revocation only by ROTATING THE SIGNING KEY, which invalidates every
    /// other capability in the system as collateral. A lookup-validated bearer
    /// is revoked by one UPDATE, affecting one session.
    pub fn revoke_session(&self, session_id: Uuid, reason: &str) -> Result<bool, DpError> {
        let now = self.clock.now_unix_ms();
        self.store
            .revoke(session_id, now, reason)
            .map_err(|e| DpError::ControlPlaneUnavailable { reason: e.to_string() })
    }
}

/// `DP-K10` step 4's server side — the seam `dp::SessionContext::refresh_if_due`
/// calls.
///
/// Thin on purpose: it is [`MetaControlPlane::refresh_capability`] with the
/// clock read here rather than passed in, because a caller that supplied `now`
/// to a REFRESH could hold a dead grant open by supplying a stale one. The bind
/// path takes `now` from the caller for a different reason — `crates/dp` has no
/// clock and the comparison is the caller's — but nothing about liveness on this
/// side should be the caller's to assert.
impl<R, K, C, S> dp::CapabilityRefresh for MetaControlPlane<R, K, C, S>
where
    R: MetaRead + Send + Sync,
    K: CapabilityStore,
    C: Clock,
    S: SecretSource,
{
    fn refresh(&self, capability_secret: &str) -> Result<dp::session::Millis, DpError> {
        let now = self.clock.now_unix_ms();
        Ok(self.refresh_capability(capability_secret, now)?.expires_at_ms)
    }
}

impl<R, K, C, S> ControlPlane for MetaControlPlane<R, K, C, S>
where
    R: MetaRead + Send + Sync,
    K: CapabilityStore,
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
        let session = Uuid::new_v4();
        let secret = self.secrets.mint();
        let expires_at_ms = now.saturating_add(self.ttl_ms);

        // RECORD BEFORE RETURNING, and fail the bind if the record fails.
        //
        // The ordering is the whole point of 5B. A capability returned to a
        // caller but absent from the store is a grant that looks valid to its
        // holder and is unknown to every validator — so it cannot be revoked,
        // cannot be refreshed, and will be rejected at its first use with an
        // error naming the caller rather than the bug. Better to refuse the
        // bind: a caller that did not get a capability knows it did not.
        self.store
            .record(&IssuedCapability {
                session_id: session,
                reality_id: req.reality,
                node_id: req.node.clone(),
                service_identity: req.service.as_str().to_string(),
                capability_hash: capability_digest(&secret),
                issued_at_ms: now,
                expires_at_ms,
            })
            .map_err(|e| DpError::ControlPlaneUnavailable {
                reason: format!("capability store refused the issuance: {e}"),
            })?;

        Ok(VerifiedBind {
            reality: req.reality,
            session,
            capability_secret: secret,
            expires_at_ms,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::errors::MetaError;
    use crate::routing::{RealityRouting, RealityStatus};
    use crate::session_store::CapabilityDigest;
    use std::sync::Mutex;

    struct FixedClock(u64);
    impl Clock for FixedClock {
        fn now_unix_ms(&self) -> u64 {
            self.0
        }
    }

    struct FixedSecret;
    impl SecretSource for FixedSecret {
        fn mint(&self) -> String {
            FIXED_SECRET.to_string()
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

    /// An in-memory [`CapabilityStore`], `#[cfg(test)]` and staying that way.
    ///
    /// Deliberately NOT a public sibling of `cache::InMemoryCache`: a capability
    /// store that forgets on restart is not a degraded production choice, it is
    /// a wrong one, and exporting it would make it reachable by a deployment
    /// that misread it as an option. The production implementor is
    /// `sqlx_pg::PgCapabilityStore`, exercised against a real database in
    /// `tests/capability_store_live.rs`.
    #[derive(Default)]
    struct MemStore {
        /// `(digest, row)`. The digest is STORED, exactly as the `BYTEA` column
        /// stores it — an earlier draft re-derived it from the fixed test
        /// secret, which made every row answer to every digest and would have
        /// hidden a lookup that returned the wrong session.
        rows: Mutex<Vec<(CapabilityDigest, SessionRecord)>>,
        /// Set to make `record` fail, for the bind-must-fail-on-store-failure
        /// case. Nothing else can produce that outcome in memory.
        refuse_writes: bool,
        /// Set to make `lookup` fail, which must NOT read as "invalid".
        refuse_reads: bool,
    }

    impl MemStore {
        fn refusing_writes() -> Self {
            Self { refuse_writes: true, ..Default::default() }
        }
        fn refusing_reads() -> Self {
            Self { refuse_reads: true, ..Default::default() }
        }
        fn len(&self) -> usize {
            self.rows.lock().expect("poisoned").len()
        }
    }

    impl CapabilityStore for MemStore {
        fn record(&self, issued: &IssuedCapability) -> Result<(), MetaError> {
            if self.refuse_writes {
                return Err(MetaError::Backend("simulated store failure".into()));
            }
            self.rows.lock().expect("poisoned").push((
                issued.capability_hash,
                SessionRecord {
                    session_id: issued.session_id,
                    reality_id: issued.reality_id,
                    node_id: issued.node_id.clone(),
                    service_identity: issued.service_identity.clone(),
                    expires_at_ms: issued.expires_at_ms,
                    revoked_at_ms: None,
                },
            ));
            Ok(())
        }

        fn lookup(&self, digest: &CapabilityDigest) -> Result<Option<SessionRecord>, MetaError> {
            if self.refuse_reads {
                return Err(MetaError::Backend("simulated store failure".into()));
            }
            let rows = self.rows.lock().expect("poisoned");
            Ok(rows.iter().find(|(d, _)| d == digest).map(|(_, r)| r.clone()))
        }

        fn find_by_session(&self, session_id: Uuid) -> Result<Option<SessionRecord>, MetaError> {
            if self.refuse_reads {
                return Err(MetaError::Backend("simulated store failure".into()));
            }
            let rows = self.rows.lock().expect("poisoned");
            Ok(rows
                .iter()
                .find(|(_, r)| r.session_id == session_id)
                .map(|(_, r)| r.clone()))
        }

        fn extend(
            &self,
            session_id: Uuid,
            expected_expires_at_ms: u64,
            new_expiry_ms: u64,
        ) -> Result<bool, MetaError> {
            let mut rows = self.rows.lock().expect("poisoned");
            match rows.iter_mut().find(|(_, r)| r.session_id == session_id) {
                // The CAS the SQL performs: the row must still hold the expiry
                // the caller read, and must still be unrevoked. Without the
                // second half, a revocation landing between the read and the
                // write would be undone by the refresh.
                Some((_, r))
                    if r.expires_at_ms == expected_expires_at_ms && r.revoked_at_ms.is_none() =>
                {
                    r.expires_at_ms = new_expiry_ms;
                    Ok(true)
                }
                _ => Ok(false),
            }
        }

        fn revoke(&self, session_id: Uuid, at_ms: u64, _reason: &str) -> Result<bool, MetaError> {
            let mut rows = self.rows.lock().expect("poisoned");
            match rows.iter_mut().find(|(_, r)| r.session_id == session_id) {
                Some((_, r)) if r.revoked_at_ms.is_none() => {
                    r.revoked_at_ms = Some(at_ms);
                    Ok(true)
                }
                _ => Ok(false),
            }
        }
    }

    const FIXED_SECRET: &str = "fixed";

    fn cp(a: Answer) -> MetaControlPlane<Meta, MemStore, FixedClock, FixedSecret> {
        MetaControlPlane::with_parts(Meta(a), MemStore::default(), FixedClock(1_000), FixedSecret, 60_000)
    }

    fn cp_with(
        a: Answer,
        store: MemStore,
    ) -> MetaControlPlane<Meta, MemStore, FixedClock, FixedSecret> {
        MetaControlPlane::with_parts(Meta(a), store, FixedClock(1_000), FixedSecret, 60_000)
    }

    fn req() -> BindRequest {
        BindRequest {
            reality: Uuid::from_u128(42),
            node: "pod-1".into(),
            service: dp::ServiceIdentity::new("commit-service").expect("valid"),
        }
    }

    #[test]
    fn the_default_ttl_is_the_revocation_window_dp_c8_specifies() {
        // This constant IS the upper bound on how long a REVOKED session keeps
        // writing, because DP-C8 reaches revocation through expiry rather than
        // through a revocation list. It shipped at 15 minutes against a spec
        // that says 5 in three places; pinning it here means the next drift is
        // a failing test rather than a number nobody re-reads.
        assert_eq!(
            DEFAULT_CAPABILITY_TTL_MS,
            5 * 60 * 1000,
            "DP-C8: \"Short expiry (5 min) bounds blast radius\""
        );
        // …and the relationship the const-assert above enforces, restated where
        // a reader of the tests will see it.
        assert!(
            dp::REFRESH_LEAD_MS < DEFAULT_CAPABILITY_TTL_MS,
            "a lead at or above the TTL makes every capability due the instant it is issued"
        );
    }

    #[test]
    fn the_fixed_secret_is_what_the_deterministic_tests_assert_on() {
        // FIXED_SECRET has one spelling, used by the minter and by the
        // assertions. Two spellings would let the minter drift while every
        // test that hardcoded the old value kept passing.
        assert_eq!(FixedSecret.mint(), FIXED_SECRET);
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
        let plane = MetaControlPlane::new(Meta(Answer::Row(RealityStatus::Active)), MemStore::default());
        let a = plane.verify_bind(&req()).expect("a");
        let b = plane.verify_bind(&req()).expect("b");
        assert_ne!(a.session, b.session, "session ids must not repeat");
        assert_ne!(a.capability_secret, b.capability_secret, "secrets must not repeat");
    }

    // ── 5B — the capability STORE ───────────────────────────────────────────

    #[test]
    fn a_bind_records_the_capability_it_issued() {
        // The gap 5B closes: 5A minted a secret and kept no record of it.
        let plane = cp(Answer::Row(RealityStatus::Active));
        let v = plane.verify_bind(&req()).expect("bind");

        let found = plane
            .validate_capability(&v.capability_secret, 1_000)
            .expect("the capability it just issued must validate");
        assert_eq!(found.session_id, v.session);
        assert_eq!(found.reality_id, Uuid::from_u128(42));
        assert_eq!(found.node_id, "pod-1");
        assert_eq!(
            found.service_identity, "commit-service",
            "the caller identity must reach the row — an unattributable capability is the hole 5B closes"
        );
    }

    #[test]
    fn the_store_holds_the_digest_and_not_the_secret() {
        // The property that makes a lookup-validated bearer safe to store.
        let plane = cp(Answer::Row(RealityStatus::Active));
        let v = plane.verify_bind(&req()).expect("bind");

        let rows = plane.store.rows.lock().expect("poisoned");
        let (digest, _) = rows.first().expect("one row");
        assert_eq!(*digest, capability_digest(&v.capability_secret));
        assert_ne!(
            digest.as_slice(),
            v.capability_secret.as_bytes(),
            "the secret itself must never be what is stored"
        );
    }

    #[test]
    fn a_bind_whose_record_fails_is_refused_rather_than_returned() {
        // A capability handed out but not recorded cannot be revoked and will
        // be rejected at its first use, blaming the caller for a control-plane
        // bug. Refusing the bind is the only honest outcome.
        let plane = cp_with(Answer::Row(RealityStatus::Active), MemStore::refusing_writes());
        let e = plane.verify_bind(&req()).expect_err("must refuse");
        assert_eq!(e.variant_name(), "ControlPlaneUnavailable");
        assert!(e.to_string().contains("capability store refused"), "{e}");
    }

    #[test]
    fn a_secret_that_was_never_issued_is_not_found() {
        let plane = cp(Answer::Row(RealityStatus::Active));
        plane.verify_bind(&req()).expect("bind");
        let e = plane
            .validate_capability("a-secret-nobody-minted", 1_000)
            .expect_err("must refuse");
        assert_eq!(e.variant_name(), "SessionNotFound");
        assert!(
            !e.to_string().contains("a-secret-nobody-minted"),
            "the rejected credential must not be echoed into the error: {e}"
        );
    }

    #[test]
    fn an_expired_capability_validates_as_expired_not_as_unknown() {
        let plane = cp(Answer::Row(RealityStatus::Active));
        let v = plane.verify_bind(&req()).expect("bind");
        assert!(plane.validate_capability(&v.capability_secret, 60_999).is_ok());
        let e = plane
            .validate_capability(&v.capability_secret, 61_000)
            .expect_err("at expiry");
        assert_eq!(e.variant_name(), "CapabilityExpired");
    }

    #[test]
    fn a_store_outage_is_an_outage_and_not_an_invalid_capability() {
        // Collapsing these would make a database blip look like every
        // capability in the system being forged at once.
        let plane = cp_with(Answer::Row(RealityStatus::Active), MemStore::refusing_reads());
        let e = plane.validate_capability("anything", 1_000).expect_err("must fail");
        assert_eq!(e.variant_name(), "ControlPlaneUnavailable");
    }

    #[test]
    fn revocation_takes_effect_before_the_capability_would_have_expired() {
        let plane = cp(Answer::Row(RealityStatus::Active));
        let v = plane.verify_bind(&req()).expect("bind");
        assert!(plane.validate_capability(&v.capability_secret, 2_000).is_ok());

        assert!(plane.revoke_session(v.session, "incident drill").expect("revoke"));
        let e = plane
            .validate_capability(&v.capability_secret, 2_000)
            .expect_err("revoked");
        assert_eq!(e.variant_name(), "CapabilityExpired");

        // Revoking twice is not an error, but it is not a second revocation.
        assert!(!plane.revoke_session(v.session, "again").expect("idempotent"));
    }

    #[test]
    fn a_refresh_extends_the_grant_without_re_issuing_the_secret() {
        let plane = cp(Answer::Row(RealityStatus::Active));
        let v = plane.verify_bind(&req()).expect("bind");
        assert_eq!(v.expires_at_ms, 61_000, "now(1000) + ttl(60000)");

        // now = 30_000, so the new expiry is now + TTL, not old + TTL.
        let r = plane.refresh_capability(&v.capability_secret, 30_000).expect("refresh");
        assert_eq!(r.expires_at_ms, 90_000);
        assert_eq!(
            r.capability_secret, v.capability_secret,
            "the secret must not travel a second time"
        );
        assert_eq!(r.session, v.session);
        assert!(plane.validate_capability(&v.capability_secret, 89_999).is_ok());
    }

    #[test]
    fn a_revoked_capability_cannot_be_resurrected_by_refreshing_it() {
        // If it could, revocation would be a suggestion: the revoked holder
        // still has the secret, and refresh is the one call that writes.
        let plane = cp(Answer::Row(RealityStatus::Active));
        let v = plane.verify_bind(&req()).expect("bind");
        plane.revoke_session(v.session, "incident").expect("revoke");

        let e = plane
            .refresh_capability(&v.capability_secret, 2_000)
            .expect_err("must not resurrect");
        assert_eq!(e.variant_name(), "CapabilityExpired");
    }

    #[test]
    fn an_expired_capability_cannot_be_refreshed_back_to_life() {
        let plane = cp(Answer::Row(RealityStatus::Active));
        let v = plane.verify_bind(&req()).expect("bind");
        let e = plane
            .refresh_capability(&v.capability_secret, 61_000)
            .expect_err("expired");
        assert_eq!(e.variant_name(), "CapabilityExpired");
    }

    #[test]
    fn the_refresh_cas_refuses_a_stale_expectation() {
        // The read-modify-write race, driven directly at the store because that
        // is the only way to be BETWEEN the read and the write. If this passed
        // with a stale expectation, a revocation landing in that window would be
        // silently undone by the refresh that followed it.
        let plane = cp(Answer::Row(RealityStatus::Active));
        let v = plane.verify_bind(&req()).expect("bind");

        // Someone else refreshed first: the row no longer holds 61_000.
        assert!(plane.store.extend(v.session, 61_000, 70_000).expect("first wins"));
        assert!(
            !plane.store.extend(v.session, 61_000, 99_000).expect("second"),
            "a second writer holding the old expiry must not apply"
        );

        // …and a revoked row does not extend even with a correct expectation.
        plane.revoke_session(v.session, "incident").expect("revoke");
        assert!(!plane.store.extend(v.session, 70_000, 99_000).expect("revoked"));
    }

    #[test]
    fn a_refused_bind_records_nothing() {
        // A capability store that accumulated rows for binds that failed would
        // be a slow leak of grants nobody holds.
        let plane = cp(Answer::Row(RealityStatus::Frozen));
        plane.verify_bind(&req()).expect_err("frozen");
        assert_eq!(plane.store.len(), 0);
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
