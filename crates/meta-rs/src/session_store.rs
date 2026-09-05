//! `5B` / `DP-C8` — the capability STORE.
//!
//! # What was wrong before this file
//!
//! `MetaControlPlane` (5A) minted a bearer secret and an expiry, handed both to
//! the caller, and **kept no record of either**. That is not a capability
//! system; it is a random-number generator with a TTL attached. Three things
//! `DP-C8` specifies were unreachable as a direct consequence:
//!
//! * **validation** — nothing could answer *"is this secret one I issued?"*
//! * **revocation** — `DP-C8`'s *"remove the session's row"* has no row to
//!   remove.
//! * **`RefreshCapability`** — extending a grant requires knowing the grant.
//!
//! # The digest, not the secret
//!
//! [`capability_digest`] is SHA-256 over the bearer secret, and the digest is
//! the only form that reaches the database. The control plane hands the secret
//! to the caller once and then cannot recover it — which is the point: a dump
//! of `session_registry`, a row in a support tool, or a stray log of a
//! [`IssuedCapability`] yields nothing a caller could present.
//!
//! This is also what makes the deviation sealed in the RUN-STATE honest.
//! `05_control_plane_spec.md` specifies signed JWTs; we issue opaque bearers
//! validated by lookup. A lookup-validated bearer is only as good as the
//! secrecy of the store, so the store does not hold the secret.
//!
//! # Why this is a trait and not just the Postgres implementation
//!
//! Not for mocking. `meta-rs` is deliberately driver-agnostic — `lib.rs` states
//! that the concrete `sqlx` adapters are caller-supplied and feature-gated — and
//! [`CapabilityStore`] follows the [`crate::metawrite::ConnectionWriter`]
//! pattern that already exists here for exactly that reason. The production
//! implementor ships in the same slice ([`crate::sqlx_pg::PgCapabilityStore`]),
//! so this is not a seam waiting for a subject.

use sha2::{Digest, Sha256};
use uuid::Uuid;

use crate::errors::MetaError;

/// The table every method here addresses.
///
/// Named once, because it is also the string the MetaWrite allowlist matches on
/// — two spellings of it would fail at runtime with a "table not allowlisted"
/// that points at the allowlist rather than at the typo.
pub const SESSION_REGISTRY_TABLE: &str = "session_registry";

/// SHA-256 of a bearer secret — 32 bytes, matching the migration's
/// `octet_length(capability_hash) = 32` CHECK.
pub type CapabilityDigest = [u8; 32];

/// Hash a bearer secret into the form the store keeps.
///
/// A plain digest with no salt and no key stretching, and that is correct here
/// rather than a shortcut: the input is 122 bits of CSPRNG output from
/// [`crate::control_plane::RandomSecret`], not a human-chosen password. Salting
/// defends against precomputation across a shared dictionary, and stretching
/// defends against guessing a low-entropy input — neither threat applies to a
/// v4 UUID, and stretching would put a deliberate delay on the validation path
/// of every SDK entry point.
///
/// The property that must hold is that the digest is unguessable from the
/// stored value and that two secrets do not collide. SHA-256 gives both.
///
/// **If the secret source is ever changed to something a human picks, this
/// comment stops being true and the function must change with it.**
pub fn capability_digest(secret: &str) -> CapabilityDigest {
    let mut h = Sha256::new();
    h.update(secret.as_bytes());
    h.finalize().into()
}

/// A capability the control plane has just issued and must now record.
///
/// Carries the DIGEST, not the secret: by the time an issuance reaches the
/// store, the secret has already left for the caller and this type could not
/// leak it even if something logged the whole struct.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IssuedCapability {
    /// The session this capability belongs to.
    pub session_id: Uuid,
    /// Which reality it addresses.
    pub reality_id: Uuid,
    /// The node the session is pinned to (`GetSessionNode`, `DP-C1`).
    pub node_id: String,
    /// Who asked. See `dp::ServiceIdentity` — attribution, not authorization.
    pub service_identity: String,
    /// SHA-256 of the bearer secret.
    pub capability_hash: CapabilityDigest,
    /// Unix ms at issuance.
    pub issued_at_ms: u64,
    /// Unix ms at which the grant stops being valid.
    pub expires_at_ms: u64,
}

/// What a lookup returns: everything needed to decide whether a presented
/// secret is a live grant, and to whom it belongs.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SessionRecord {
    /// The session.
    pub session_id: Uuid,
    /// The reality it addresses.
    pub reality_id: Uuid,
    /// The node it is pinned to.
    pub node_id: String,
    /// The service it was issued to.
    pub service_identity: String,
    /// Unix ms at which the grant expires.
    pub expires_at_ms: u64,
    /// Unix ms at which it was revoked, if it was.
    pub revoked_at_ms: Option<u64>,
}

impl SessionRecord {
    /// Is this grant usable at `now_ms`?
    ///
    /// The predicate `DP-Ch32`'s `WHERE active = true` names, evaluated rather
    /// than stored — a boolean column would be a second SSOT for a fact the
    /// clock decides, and would be stale the moment a capability expired with
    /// nobody watching. The migration header says the same thing at the schema.
    pub fn is_live(&self, now_ms: u64) -> bool {
        self.revoked_at_ms.is_none() && now_ms < self.expires_at_ms
    }
}

/// Record, look up, extend and revoke issued capabilities.
///
/// Every method takes `&self`: [`dp::ControlPlane::verify_bind`] is `&self`, so
/// a store needing `&mut self` could not be held by the control plane that
/// calls it. Implementations that need a mutable driver handle take the lock
/// internally — which is what [`crate::sqlx_pg::PgCapabilityStore`] does, and is
/// affordable for the reason `lib.rs` already gives: meta writes are cold.
pub trait CapabilityStore: Send + Sync {
    /// Persist a freshly issued capability.
    ///
    /// A failure here MUST fail the bind. A capability that was handed out but
    /// not recorded is worse than no capability: it looks valid to the holder
    /// and is unknown to every validator, which is a grant nobody can revoke.
    fn record(&self, issued: &IssuedCapability) -> Result<(), MetaError>;

    /// Find a session by its id, without a capability.
    ///
    /// `DP-C3`'s `GetSessionNode` asks *"where is session S pinned"* — a
    /// ROUTING question asked by a node that does not hold S's capability and
    /// must not need it. Reachable only with the session id, which is not a
    /// credential: knowing it lets a caller learn a node name, not act as the
    /// session.
    ///
    /// Deliberately NOT served by [`Self::lookup`]: that one is keyed by the
    /// digest, and answering a routing question would then require presenting
    /// the secret, which is how a routing table becomes a reason to pass
    /// credentials around.
    fn find_by_session(&self, session_id: Uuid) -> Result<Option<SessionRecord>, MetaError>;

    /// Find the session a presented secret's digest belongs to.
    ///
    /// `Ok(None)` means no such capability was ever issued — distinct from a
    /// backend failure, which must surface as `Err`. Collapsing the two would
    /// turn a database outage into *"your capability is invalid"* for every
    /// caller at once.
    fn lookup(&self, digest: &CapabilityDigest) -> Result<Option<SessionRecord>, MetaError>;

    /// Move a session's expiry forward (`RefreshCapability`) — **compare and
    /// swap**, not a blind write.
    ///
    /// `expected_expires_at_ms` is the expiry the caller READ. The update must
    /// apply only if the row still holds it and is still unrevoked; returns
    /// `false` otherwise.
    ///
    /// # Why CAS and not "extend if live"
    ///
    /// A refresh is a read (is this capability live?) followed by a write, and
    /// the row can change in between — most consequentially by being REVOKED. A
    /// store that only re-checked liveness at write time would still be exposed:
    /// the revocation could land after that check. Carrying the read value
    /// forward as a guard makes the whole read-modify-write one atomic decision,
    /// which is the same machinery `expected_before` already gives every other
    /// meta write in this crate.
    ///
    /// The division of labour is deliberate: the **store** decides whether the
    /// row changed, the **control plane** decides whether the grant was live.
    /// Splitting them the other way would put clock policy in the SQL.
    fn extend(
        &self,
        session_id: Uuid,
        expected_expires_at_ms: u64,
        new_expiry_ms: u64,
    ) -> Result<bool, MetaError>;

    /// Revoke a session's capability.
    ///
    /// Returns whether a row was actually updated — `false` for an unknown or
    /// already-revoked session. `reason` reaches the MetaWrite audit row, which
    /// is the record `DP-C8`'s "remove the row" would have destroyed.
    fn revoke(&self, session_id: Uuid, at_ms: u64, reason: &str) -> Result<bool, MetaError>;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_digest_is_sha256_of_the_secret_and_nothing_else() {
        // RFC-independent but pinned: the SHA-256 of "abc" is a value every
        // implementation agrees on, so this test fails if the hash function is
        // ever silently swapped for a faster one.
        let d = capability_digest("abc");
        let hex: String = d.iter().map(|b| format!("{b:02x}")).collect();
        assert_eq!(
            hex,
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
        assert_eq!(d.len(), 32, "the migration CHECKs octet_length = 32");
    }

    #[test]
    fn two_secrets_do_not_share_a_digest() {
        assert_ne!(capability_digest("a"), capability_digest("b"));
    }

    #[test]
    fn liveness_needs_both_halves_of_the_predicate() {
        let live = SessionRecord {
            session_id: Uuid::from_u128(1),
            reality_id: Uuid::from_u128(2),
            node_id: "pod-1".into(),
            service_identity: "commit-service".into(),
            expires_at_ms: 1_000,
            revoked_at_ms: None,
        };
        assert!(live.is_live(999), "inside the TTL and not revoked");
        assert!(!live.is_live(1_000), "expiry is exclusive, as CapabilityToken's is");

        // Revoked beats unexpired — otherwise revocation would not take effect
        // until the capability would have expired anyway, which is the whole
        // reason immediate revocation is worth having.
        let revoked = SessionRecord { revoked_at_ms: Some(500), ..live };
        assert!(!revoked.is_live(999), "a revoked grant is dead before its expiry");
    }
}
