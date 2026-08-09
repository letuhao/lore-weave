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

use dp::{BindRequest, ControlPlane, ServiceIdentity, SessionContext};
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

/// Bind a session and return the verified reality with its capability.
///
/// The whole [`SessionContext`] is returned rather than just the `RealityId`,
/// because the context also carries the capability and its expiry — a caller
/// that keeps only the id has silently discarded the grant that made it valid.
pub async fn bind_reality(
    meta_url: Option<&str>,
    meta_allowlist_path: &str,
    reality: Uuid,
) -> Result<SessionContext, Box<dyn std::error::Error>> {
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
    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)?
        .as_millis() as u64;

    let ctx = SessionContext::bind(
        &plane,
        BindRequest { reality, node: node_id(), service },
        now_ms,
    )?;
    Ok(ctx)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn a_missing_meta_url_is_refused_with_a_reason_not_a_default() {
        // The failure this module exists to make loud. Without it, a writer with
        // no registry silently proceeds against an unverified world.
        let err = bind_reality(None, "unused", Uuid::nil()).await.expect_err("must refuse");
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
