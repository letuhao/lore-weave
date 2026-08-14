//! `3E` — how this service obtains a VERIFIED `dp::RealityId`.
//!
//! # What a raw `--reality <uuid>` did not check
//!
//! `spine` took a uuid off the command line and wrote events under it. Nothing
//! confirmed the reality existed, and nothing confirmed it still ACCEPTED
//! COMMANDS — so a writer node pointed at a `Frozen`, `Archived` or
//! `SoftDeleted` reality would append happily to a world that had been closed,
//! and the first sign of trouble would be downstream.
//!
//! `dp::RealityId` cannot be forged: the only way to hold one is to be handed it
//! by `dp::SessionContext::bind`, which gets it from a control plane that made
//! both checks. This module is the one place in `commit-service` where that
//! happens, so "did this process verify its reality?" has a single answer and a
//! single place to read it.
//!
//! # Why the meta URL is REQUIRED here rather than optional
//!
//! `spine`'s `--meta-url` is an `Option` because the RULESET can come from files
//! for offline tools and smokes. Binding a reality is a different question, and
//! its own docstring already states the principle this follows: *"a node with no
//! meta DB reachable should fail loudly at startup, not fall back to a private
//! file and run different rules from its neighbours."* A writer that cannot
//! reach the registry cannot know whether its world is open, and the safe
//! failure is to refuse rather than to write.

use dp::{BindRequest, ServiceIdentity, SessionContext};
use meta_rs::allowlist::Allowlist;
use meta_rs::control_plane::MetaControlPlane;
use meta_rs::metawrite::{Actor, ActorType};
use meta_rs::routing::DefaultMetaRead;
use meta_rs::sqlx_pg::{PgCapabilityStore, PgConnectionReader};
use sqlx::postgres::PgPoolOptions;
use uuid::Uuid;

/// This process's node identity, for `session_registry.node_id`.
///
/// The hostname, so `GetSessionNode` (DP-C1) answers with something an operator
/// can act on. A constant would make every writer node indistinguishable in the
/// registry, which is precisely the question that column exists to answer.
///
/// It lives here rather than in `spine` because it is a fact about how this
/// service presents itself to the CONTROL PLANE, which is this module's whole
/// subject — and because a second binary computing it differently would put two
/// spellings of one node in the registry.
fn node_id() -> String {
    std::env::var("HOSTNAME")
        .or_else(|_| std::env::var("COMPUTERNAME"))
        .unwrap_or_else(|_| format!("spine-{}", std::process::id()))
}

/// This service's identity on the control plane, in one place.
///
/// A literal at each call site would drift, and the identity is what every
/// issued capability is attributed to — see `session_registry.service_identity`.
pub const SERVICE_IDENTITY: &str = "commit-service";

/// The concrete control plane this service binds against.
///
/// Named because [`Bound`] has to hold one: the refresher must OUTLIVE the bind,
/// and the first version of this module dropped it at the end of `bind_reality`.
/// That left the process holding a capability it had no way to renew — which is
/// the same defect as not refreshing at all, arrived at by accident.
pub type CommitControlPlane = MetaControlPlane<DefaultMetaRead<PgConnectionReader>, PgCapabilityStore>;

/// What a successful bind hands back.
///
/// Both halves, because a caller needs both: the session to act with, and the
/// plane to keep it alive. Returning only the `SessionContext` — as this
/// function first did — reads complete and quietly makes `refresh_if_due`
/// uncallable.
pub struct Bound {
    /// The verified session. `mut` in the caller: a refresh replaces it.
    pub session: SessionContext,
    /// The refresher. Implements `dp::CapabilityRefresh`.
    pub plane: CommitControlPlane,
}

/// Bind a session and return the verified reality with its capability.
///
/// The whole [`SessionContext`] is returned rather than just the `RealityId`,
/// because the context also carries the capability and its expiry — a caller
/// that keeps only the id has silently discarded the grant that made it valid.
pub async fn bind_reality(
    meta_url: Option<&str>,
    meta_allowlist_path: &str,
    reality: Uuid,
) -> Result<Bound, Box<dyn std::error::Error>> {
    let meta_url = meta_url.ok_or(
        "--meta-url is required: a writer node must verify with the control plane that its \
         reality exists and still accepts commands before appending to it. Without the meta \
         database that check cannot be made, and writing to a frozen or archived world is \
         worse than refusing to start.",
    )?;

    let meta_pool = PgPoolOptions::new().max_connections(2).connect(meta_url).await?;
    let allowlist = Allowlist::load(meta_allowlist_path)?;

    let reader = PgConnectionReader::new(meta_pool.clone())?;
    let store = PgCapabilityStore::new(
        meta_pool,
        allowlist,
        Actor {
            actor_type: ActorType::System,
            id: SERVICE_IDENTITY.to_string(),
            svid: None,
        },
    )?;

    let plane = MetaControlPlane::new(DefaultMetaRead::new(reader), store);
    let service = ServiceIdentity::new(SERVICE_IDENTITY)
        .ok_or("the service identity constant is not a valid ServiceIdentity")?;

    // `bind` needs `now` in the SAME timebase the control plane stamps its
    // expiry in — Unix epoch milliseconds. Reading a different clock here is how
    // two components end up disagreeing about whether a capability is live.
    let now_ms = now_ms()?;

    let session = SessionContext::bind(
        &plane,
        BindRequest { reality, node: node_id(), service },
        now_ms,
    )?;
    Ok(Bound { session, plane })
}

/// `DP-K10` step 4 — keep the capability alive, and FAIL CLOSED.
///
/// Returns the refreshed session when one was due, `None` when it was not, and
/// an **error the caller must not swallow** when the control plane refused.
///
/// # Why the refusal is the product
///
/// `check_live` compares this process's own copy of an expiry against its own
/// clock, so it catches an honest expiry and cannot catch a REVOCATION. This is
/// the only thing that can: the refresh asks the control plane, and a revoked
/// grant comes back refused. An operator who revokes this session gets a writer
/// that stops — within one TTL (5 minutes, `DP-C8`) at the outside, and at the
/// next refresh in practice.
///
/// It lives here rather than in `spine` for the same reason `node_id` does: it
/// is this service's relationship with the control plane, and a second binary
/// implementing it slightly differently would be a second revocation policy.
pub fn refresh_if_due(
    session: &SessionContext,
    plane: &CommitControlPlane,
) -> Result<Option<SessionContext>, Box<dyn std::error::Error>> {
    Ok(session.refresh_if_due(plane, now_ms()?)?)
}

/// Unix EPOCH milliseconds — the timebase `dp::Millis` specifies.
///
/// One spelling, used by the bind and by every refresh check. Two readings of
/// "now" from two places is how a caller and a control plane end up disagreeing
/// about whether a capability is live.
pub fn now_ms() -> Result<u64, Box<dyn std::error::Error>> {
    Ok(std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)?
        .as_millis() as u64)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn a_missing_meta_url_is_refused_with_a_reason_not_a_default() {
        // The failure this module exists to make loud. Without it, a writer with
        // no registry silently proceeds against an unverified world.
        let err = bind_reality(None, "unused", Uuid::nil()).await.err().expect("must refuse");
        let msg = err.to_string();
        assert!(msg.contains("--meta-url is required"), "{msg}");
        assert!(
            msg.contains("accepts commands"),
            "the refusal must say WHAT could not be checked: {msg}"
        );
    }

    #[test]
    fn the_service_identity_constant_is_a_valid_service_identity() {
        // `ServiceIdentity::new` rejects blank, over-long and control-character
        // names. A constant that failed it would turn every bind into a runtime
        // error at the least convenient moment.
        assert!(ServiceIdentity::new(SERVICE_IDENTITY).is_some());
    }
}
