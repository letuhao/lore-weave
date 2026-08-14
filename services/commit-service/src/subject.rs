//! `SEALED-SUBJECT` — who is acting, resolved instead of asserted.
//!
//! # The defect this closes
//!
//! `admission::Proposal` carried `pub actor: u64`, and `ChannelRoom` supplied
//! it. The producer SIGNATURE was verified; the SUBJECT was not. So the field
//! naming who you are acting as arrived from the party claiming it, which is
//! `PID-D5`'s own argument — *"a field that is not on the wire cannot be
//! forged"* — sitting eleven lines below the field it does not cover.
//!
//! The PO sealed the fix on 2026-08-06:
//!
//! > *"The subject is resolved on the kernel path, not asked for by the
//! > transport… it has to go through the kernel. That is the architecture."*
//! > **"Fixing the transport fixes one instance; moving the resolution kills
//! > the class."**
//!
//! # Two databases, because the two identities live in different tiers
//!
//! `actor_control_binding` is META — a human exists across realities, so the
//! binding cannot live in a per-reality shard without turning character-select
//! into an N-database fan-out and leaving GDPR erasure with rows it cannot find
//! (migration `034`'s four reasons). `actors` is PER-REALITY — an `EntityId` is
//! *"identity within a reality"*.
//!
//! So the resolution is two hops, and it is the conversion `S-9` recorded as
//! having zero instances:
//!
//! ```text
//!   user_ref_id ──meta──▶ actor_control_binding.actor_id (live only)
//!               ──reality──▶ actors.entity_id ──▶ sim_core::EntityId
//! ```

use dp::RealityId;
use sqlx::{PgPool, Row};
use uuid::Uuid;

/// Why a subject could not be resolved.
///
/// Every variant is a REFUSAL, not an error in us — which is why they are
/// distinguished. *"You drive nobody here"* and *"the binding points at an
/// actor this reality does not have"* are different operator problems, and
/// collapsing them would send someone to fix the wrong one.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SubjectError {
    /// No live binding: this user drives nobody in this reality. The ordinary
    /// case for a spectator, and the ordinary case one instant after a revoke.
    NoLiveBinding { user: Uuid },
    /// A live binding names an actor the per-reality registry does not have.
    /// The dangling pointer `S-9` describes — the grant path refuses to create
    /// one, so reaching this means the actor was removed after the grant.
    UnknownActor { actor: Uuid },
    /// `entity_id` is BIGINT and `EntityId` is `u64`. A negative value cannot
    /// be an island id, and silently casting it would produce an enormous
    /// `u64` that resolves to nothing — a wrong subject rather than a refusal.
    NotAnEntityId { entity_id: i64 },
    /// The lookup itself failed. The only variant that is ours.
    Db(String),
}

impl std::fmt::Display for SubjectError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NoLiveBinding { user } => {
                write!(f, "user {user} drives no actor in this reality")
            }
            Self::UnknownActor { actor } => {
                write!(f, "binding names actor {actor}, which this reality has no registry row for")
            }
            Self::NotAnEntityId { entity_id } => {
                write!(f, "entity_id {entity_id} is not a valid island id")
            }
            Self::Db(m) => write!(f, "subject lookup failed: {m}"),
        }
    }
}

impl std::error::Error for SubjectError {}

/// Resolve `(reality, user)` to the island entity that user may act as.
///
/// **The only source of a subject.** A caller that has this does not need the
/// wire to tell it who is acting, which is the entire point — a subject the
/// caller cannot assert cannot be forged.
pub async fn resolve_subject(
    meta: &PgPool,
    reality_pool: &PgPool,
    reality: &RealityId,
    user_ref_id: Uuid,
) -> Result<u64, SubjectError> {
    // Hop 1 — META. `revoked_at IS NULL` is not an optimisation: a revoked
    // binding is history, and treating it as authority is precisely the hole
    // the revoke exists to close.
    let binding = sqlx::query(
        "SELECT actor_id FROM actor_control_binding \
          WHERE reality_id = $1 AND user_ref_id = $2 AND revoked_at IS NULL",
    )
    .bind(reality.as_uuid())
    .bind(user_ref_id)
    .fetch_optional(meta)
    .await
    .map_err(|e| SubjectError::Db(e.to_string()))?
    .ok_or(SubjectError::NoLiveBinding { user: user_ref_id })?;
    let actor_id: Uuid = binding.get("actor_id");

    // Hop 2 — PER-REALITY. The conversion site itself.
    let row = sqlx::query("SELECT entity_id FROM actors WHERE reality_id = $1 AND actor_id = $2")
        .bind(reality.as_uuid())
        .bind(actor_id)
        .fetch_optional(reality_pool)
        .await
        .map_err(|e| SubjectError::Db(e.to_string()))?
        .ok_or(SubjectError::UnknownActor { actor: actor_id })?;
    let entity_id: i64 = row.get("entity_id");

    u64::try_from(entity_id).map_err(|_| SubjectError::NotAnEntityId { entity_id })
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The conversion is CHECKED, and the check is the point.
    ///
    /// `as u64` on a negative `i64` yields something near `u64::MAX` — a
    /// perfectly well-typed number naming an entity that does not exist. That
    /// is a WRONG SUBJECT presented as a valid one, which is worse than the
    /// refusal it replaces and is the whole class this module exists to end.
    #[test]
    fn a_negative_entity_id_is_refused_rather_than_cast() {
        assert_eq!(u64::try_from(-1_i64).ok(), None);
        assert_eq!(u64::try_from(0_i64).ok(), Some(0));
        assert_eq!(u64::try_from(7_i64).ok(), Some(7));
        // What the unchecked version would have produced instead of a refusal.
        assert_eq!(-1_i64 as u64, u64::MAX);
    }

    /// Each refusal says which of three different things went wrong. A single
    /// opaque "denied" would make a revoked player and a corrupted registry
    /// look identical to whoever is on call.
    #[test]
    fn the_three_refusals_are_distinguishable() {
        let u = Uuid::from_u128(1);
        let a = Uuid::from_u128(2);
        let msgs = [
            SubjectError::NoLiveBinding { user: u }.to_string(),
            SubjectError::UnknownActor { actor: a }.to_string(),
            SubjectError::NotAnEntityId { entity_id: -5 }.to_string(),
        ];
        assert!(msgs[0].contains("drives no actor"), "{}", msgs[0]);
        assert!(msgs[1].contains("no registry row"), "{}", msgs[1]);
        assert!(msgs[2].contains("not a valid island id"), "{}", msgs[2]);
        let unique: std::collections::BTreeSet<&str> =
            msgs.iter().map(|s| s.as_str()).collect();
        assert_eq!(unique.len(), 3, "two refusals render identically: {msgs:?}");
    }
}

/// The two pools a subject resolution needs, plus the admission call that uses
/// it — so a caller cannot admit a proposal without having resolved one.
///
/// # Why the admission call lives here
///
/// `bin/spine.rs` sits exactly on its `IMP-D3` ceiling, and the cap's own
/// comment says why raising it is not the answer: *"a cap left at its old value
/// after a split is a silent licence to regrow into it."* The precedent it
/// cites is the one followed here — when the binary gained a new startup
/// responsibility, the RESPONSIBILITY moved (`ruleset_boot`, `spine_args`,
/// `reject_commit`). Subject resolution is the fourth.
///
/// It is also the better boundary regardless of line counts: peek, resolve and
/// admit are one decision — *"may this submitter act, and as whom?"* — and
/// splitting them across a binary and a module is how one of the three ends up
/// skipped on some path.
pub struct SubjectSource {
    meta: PgPool,
    reality_pool: PgPool,
    /// The VERIFIED reality. `dp::RealityId` has no public constructor — the
    /// spine gets one from `reality_bind::bind_reality`, so holding it is proof
    /// the control plane confirmed this world accepts commands. Taking a bare
    /// `Uuid` here would have discarded a fact the caller already had.
    reality: RealityId,
}

impl SubjectSource {
    /// Open the meta pool; the reality pool is the one the caller already has.
    ///
    /// `meta_url` is REQUIRED, and the error says so rather than degrading:
    /// a spine that cannot reach `actor_control_binding` cannot resolve a
    /// subject, and one that ran anyway would have to get the subject from
    /// somewhere — which is the wire, which is the defect.
    pub async fn connect(
        meta_url: Option<&str>,
        reality_pool: PgPool,
        reality: RealityId,
    ) -> Result<Self, SubjectError> {
        let url = meta_url.ok_or_else(|| {
            SubjectError::Db(
                "--meta-url is required: the subject is resolved from actor_control_binding, \
                 and a writer that cannot read it would have to trust the wire"
                    .into(),
            )
        })?;
        let meta = sqlx::postgres::PgPoolOptions::new()
            .max_connections(2)
            .connect(url)
            .await
            .map_err(|e| SubjectError::Db(format!("meta pool: {e}")))?;
        Ok(Self { meta, reality_pool, reality })
    }

    /// Resolve `(reality, user)` to the island entity that user may act as.
    pub async fn resolve(&self, user_ref_id: Uuid) -> Result<u64, SubjectError> {
        resolve_subject(&self.meta, &self.reality_pool, &self.reality, user_ref_id).await
    }

    /// Peek the submitter, resolve the subject, then admit — or REFUSE.
    ///
    /// A refusal is returned as an `AdmissionRecord`, not as an error, because
    /// the spine's contract is that every consumed message produces a durable
    /// outcome: *"an entry is acked ONLY after its outcome is durable
    /// (committed event or recorded rejection)"*. A subject that cannot be
    /// resolved is a rejection with a reason, recorded like any other — not a
    /// message quietly dropped.
    pub async fn admit(
        &self,
        raw_json: &str,
        sig_hex: Option<&str>,
        registry: &crate::producer::ProducerRegistry,
        vocab: &crate::Vocabulary,
        verbs: &ruleset_core::VerbTable,
        dedup: &mut crate::admission::DedupCache,
    ) -> crate::admission::AdmissionRecord {
        let Some(user) = crate::admission::peek_user_ref_id(raw_json) else {
            return crate::admission::AdmissionRecord::rejected(
                "subject",
                "proposal carries no `user_ref_id`; the subject is resolved, never asserted",
            );
        };
        match self.resolve(user).await {
            Ok(entity) => crate::admission::admit_signed(
                raw_json,
                sig_hex,
                sim_core::EntityId(entity),
                registry,
                vocab,
                verbs,
                dedup,
            ),
            Err(why) => crate::admission::AdmissionRecord::rejected("subject", &why.to_string()),
        }
    }
}
