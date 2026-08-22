//! `5C` — the whole `DP-C3` non-channel surface, exercised over a REAL socket.
//!
//! # Why a socket and not a direct call on the service struct
//!
//! Calling `ControlPlaneService::bind_session(...)` in-process would test the
//! handler and nothing about gRPC: not the generated codec, not the status
//! codes as they cross the wire, not whether the client and server agree about
//! a field. The whole point of `5C` is the transport, so every test here binds
//! an ephemeral TCP port, serves on it, and connects a real client.
//!
//! The STATE behind the server is in-memory here. That is deliberate and it is
//! the honest division: `crates/meta-rs`'s `pg_live.rs` already proves the same
//! control plane against real Postgres, and repeating that here would be
//! testing the store a second time while adding nothing about the surface.

use std::collections::BTreeSet;
use std::sync::Mutex;

use dp::ControlPlane as _;
use dp_control_plane::client::GrpcControlPlane;
use dp_control_plane::pb::dp_control_plane_client::DpControlPlaneClient;
use dp_control_plane::pb::dp_control_plane_server::DpControlPlaneServer;
use dp_control_plane::server::ControlPlaneService;
use dp_control_plane::{pb, UNIMPLEMENTED_METHODS};
use meta_rs::control_plane::{Clock, MetaControlPlane, SecretSource};
use meta_rs::errors::MetaError;
use meta_rs::routing::{MetaRead, RealityRouting, RealityStatus, TierPolicyRow};
use meta_rs::session_store::{
    CapabilityDigest, CapabilityStore, IssuedCapability, SessionRecord,
};
use uuid::Uuid;

// ── in-memory backends ──────────────────────────────────────────────────────

const REALITY: u128 = 0xA11CE;

struct Meta;
impl MetaRead for Meta {
    /// `DP-C4` (`DF2`). Two rows, deliberately: `GetTierPolicy` filters by
    /// aggregate_type, and a single-row double cannot tell a working filter
    /// from one that ignores its argument and returns everything.
    fn get_tier_policy(
        &self,
        aggregate_type: Option<&str>,
    ) -> Result<Vec<TierPolicyRow>, MetaError> {
        let all = vec![
            TierPolicyRow {
                aggregate_type: "combat_session".into(),
                declared_tier: "T2".into(),
                schema_version: 1,
                feature_owner: "commit-service".into(),
            },
            TierPolicyRow {
                aggregate_type: "player_wallet".into(),
                declared_tier: "T3".into(),
                schema_version: 4,
                feature_owner: "economy-service".into(),
            },
        ];
        Ok(match aggregate_type {
            None => all,
            Some(want) => all.into_iter().filter(|r| r.aggregate_type == want).collect(),
        })
    }

    fn get_reality_routing(&self, id: Uuid) -> Result<Option<RealityRouting>, MetaError> {
        if id != Uuid::from_u128(REALITY) {
            return Ok(None);
        }
        Ok(Some(RealityRouting {
            reality_id: id,
            db_host: "pg-shard-0.internal".into(),
            db_name: "lw_reality_surface".into(),
            status: RealityStatus::Active,
            locale: "en".into(),
            deploy_cohort: 7,
        }))
    }
}

#[derive(Default)]
struct MemStore {
    rows: Mutex<Vec<(CapabilityDigest, SessionRecord)>>,
}

impl CapabilityStore for MemStore {
    fn record(&self, issued: &IssuedCapability) -> Result<(), MetaError> {
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
    fn find_by_session(&self, session_id: Uuid) -> Result<Option<SessionRecord>, MetaError> {
        let rows = self.rows.lock().expect("poisoned");
        Ok(rows.iter().find(|(_, r)| r.session_id == session_id).map(|(_, r)| r.clone()))
    }
    fn lookup(&self, digest: &CapabilityDigest) -> Result<Option<SessionRecord>, MetaError> {
        let rows = self.rows.lock().expect("poisoned");
        Ok(rows.iter().find(|(d, _)| d == digest).map(|(_, r)| r.clone()))
    }
    fn extend(&self, session_id: Uuid, expected: u64, new_expiry: u64) -> Result<bool, MetaError> {
        let mut rows = self.rows.lock().expect("poisoned");
        match rows.iter_mut().find(|(_, r)| r.session_id == session_id) {
            Some((_, r)) if r.expires_at_ms == expected && r.revoked_at_ms.is_none() => {
                r.expires_at_ms = new_expiry;
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

struct FixedClock(u64);
impl Clock for FixedClock {
    fn now_unix_ms(&self) -> u64 {
        self.0
    }
}

struct CountingSecret(Mutex<u64>);
impl SecretSource for CountingSecret {
    fn mint(&self) -> String {
        let mut n = self.0.lock().expect("poisoned");
        *n += 1;
        format!("surface-secret-{n}")
    }
}

/// Start a server on an ephemeral port and return its endpoint.
///
/// Port 0 rather than a fixed one: two tests running concurrently on a fixed
/// port produce a bind error that reads like a server bug.
async fn serve() -> String {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.expect("bind");
    let addr = listener.local_addr().expect("addr");

    let plane = MetaControlPlane::with_parts(
        Meta,
        MemStore::default(),
        FixedClock(1_000),
        CountingSecret(Mutex::new(0)),
        60_000,
    );
    let svc = DpControlPlaneServer::new(ControlPlaneService::new(plane));

    tokio::spawn(async move {
        tonic::transport::Server::builder()
            .add_service(svc)
            .serve_with_incoming(tokio_stream::wrappers::TcpListenerStream::new(listener))
            .await
            .expect("serve");
    });

    format!("http://{addr}")
}

fn service() -> dp::ServiceIdentity {
    dp::ServiceIdentity::new("surface-test").expect("valid")
}

// ── the tests ───────────────────────────────────────────────────────────────

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn every_unimplemented_method_says_so_and_no_other_does() {
    // The list in `lib.rs` is a CLAIM about the running server. This is the
    // check that makes it a fact: call all fourteen RPCs, collect the ones that
    // answered UNIMPLEMENTED, and compare the SET. Both directions red — a
    // method that got implemented and stayed on the list, and one that returns
    // UNIMPLEMENTED without being on it.
    let endpoint = serve().await;
    let mut c = DpControlPlaneClient::connect(endpoint).await.expect("connect");

    let r = Uuid::from_u128(REALITY).to_string();
    let mut unimplemented: BTreeSet<String> = BTreeSet::new();
    let mut note = |name: &str, code: tonic::Code, msg: String| {
        if code == tonic::Code::Unimplemented {
            unimplemented.insert(name.to_string());
            // The message must NAME what is missing. "unimplemented" alone
            // leaves a caller to guess whether it is coming.
            assert!(
                msg.len() > name.len() + 2,
                "{name}: UNIMPLEMENTED must say what state is missing, got {msg:?}"
            );
        }
    };

    macro_rules! call {
        ($name:literal, $e:expr) => {
            match $e.await {
                Ok(_) => {}
                Err(s) => note($name, s.code(), s.message().to_string()),
            }
        };
    }

    call!("VerifyReality", c.verify_reality(pb::VerifyRealityRequest { reality_id: r.clone() }));
    call!(
        "BindSession",
        c.bind_session(pb::BindSessionRequest {
            reality_id: r.clone(),
            node_id: "pod-1".into(),
            service_identity: "surface-test".into(),
        })
    );
    // Refresh needs a live secret; bind one first so this is not measuring an
    // authentication failure instead of the method's existence.
    let bound = c
        .bind_session(pb::BindSessionRequest {
            reality_id: r.clone(),
            node_id: "pod-1".into(),
            service_identity: "surface-test".into(),
        })
        .await
        .expect("bind")
        .into_inner();
    call!(
        "RefreshCapability",
        c.refresh_capability(pb::RefreshCapabilityRequest {
            capability_secret: bound.capability_secret.clone()
        })
    );
    call!("GetTierPolicy", c.get_tier_policy(pb::GetTierPolicyRequest::default()));
    call!(
        "StreamTierPolicyUpdates",
        c.stream_tier_policy_updates(pb::StreamTierPolicyRequest::default())
    );
    call!("ResolveReality", c.resolve_reality(pb::ResolveRealityRequest { reality_id: r.clone() }));
    call!(
        "StreamRealityTransitions",
        c.stream_reality_transitions(pb::StreamRealityTransitionsRequest::default())
    );
    call!(
        "GetSessionNode",
        c.get_session_node(pb::GetSessionNodeRequest { session_id: bound.session_id.clone() })
    );
    call!(
        // `DP-A11`: this assertion is the trigger. When `npc_binding` gains a
        // migration and this method starts working, this case reds — which is
        // what forces DP-A11 to be re-classified instead of staying absent in
        // silence.
        "GetNpcNode",
        c.get_npc_node(pb::GetNpcNodeRequest {
            reality_id: r.clone(),
            npc_id: Uuid::nil().to_string()
        })
    );
    call!(
        "ReportNodeHandoff",
        c.report_node_handoff(pb::ReportNodeHandoffRequest {
            session_id: bound.session_id.clone(),
            from_node_id: "pod-1".into(),
            to_node_id: "pod-2".into(),
        })
    );
    call!(
        "GetSchemaVersion",
        c.get_schema_version(pb::GetSchemaVersionRequest { reality_id: r.clone() })
    );
    call!(
        "AnnounceMigrationStart",
        c.announce_migration_start(pb::AnnounceMigrationStartRequest {
            reality_id: r.clone(),
            to_version: 2
        })
    );
    call!(
        "AnnounceMigrationComplete",
        c.announce_migration_complete(pb::AnnounceMigrationCompleteRequest {
            reality_id: r.clone(),
            at_version: 2,
            succeeded: true,
        })
    );
    call!("Health", c.health(pb::Empty {}));

    let declared: BTreeSet<String> =
        UNIMPLEMENTED_METHODS.iter().map(|(m, _)| (*m).to_string()).collect();

    assert_eq!(
        unimplemented, declared,
        "\nthe server's UNIMPLEMENTED set and UNIMPLEMENTED_METHODS disagree.\n\
         only the server said so : {:?}\n\
         only the list says so   : {:?}\n",
        unimplemented.difference(&declared).collect::<Vec<_>>(),
        declared.difference(&unimplemented).collect::<Vec<_>>(),
    );
    // 8 until `DF2`. `040_tier_policy` gave `DP-C4` its table and
    // `GetTierPolicy` now answers, so the register shrank by exactly one — and
    // this number is what made that visible rather than quiet. It must only
    // ever go DOWN: a rise means an implemented RPC regressed to UNIMPLEMENTED.
    assert_eq!(declared.len(), 7, "the count is governed too, not just the set");
}

/// `DF2` — `GetTierPolicy` ANSWERS, and answers the question it was asked.
///
/// The register test above proves it stopped returning `UNIMPLEMENTED`. That is
/// not the same as working: a handler returning an empty snapshot would also
/// leave the register — and per `DP-C4`'s registration flow an empty snapshot
/// is a deploy-breaking lie, because a service whose aggregate is absent fails
/// at `DpClient::connect`.
///
/// So this asserts the CONTENT, and asserts the filter with two rows: a handler
/// that ignored `aggregate_type` and returned everything would pass a one-row
/// double.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn get_tier_policy_serves_the_registry_and_honours_its_filter() {
    let endpoint = serve().await;
    let mut c = DpControlPlaneClient::connect(endpoint).await.expect("connect");

    let all = c
        .get_tier_policy(pb::GetTierPolicyRequest { aggregate_type: String::new() })
        .await
        .expect("the whole snapshot")
        .into_inner();
    assert_eq!(all.entries.len(), 2, "an empty aggregate_type means EVERY entry");

    let one = c
        .get_tier_policy(pb::GetTierPolicyRequest {
            aggregate_type: "player_wallet".into(),
        })
        .await
        .expect("one entry")
        .into_inner();
    assert_eq!(one.entries.len(), 1, "the filter is applied, not ignored");
    let e = &one.entries[0];
    assert_eq!(e.aggregate_type, "player_wallet");
    assert_eq!(e.declared_tier, "T3", "the TIER survived the seam");
    assert_eq!(e.schema_version, 4, "and DP-C5's counter with it");
    assert_eq!(e.feature_owner, "economy-service");

    // An aggregate nobody registered is an EMPTY snapshot, not an error: that
    // is what `DpClient::connect` interprets as "you may not touch this".
    let none = c
        .get_tier_policy(pb::GetTierPolicyRequest { aggregate_type: "no_such".into() })
        .await
        .expect("an unregistered type is not an error")
        .into_inner();
    assert!(none.entries.is_empty());

    assert_eq!(
        all.snapshot_version, 0,
        "0 means THIS DEPLOYMENT HAS NO VERSION SEQUENCE — DP-C5's is unbuilt. \
         Asserted so it cannot drift into a fabricated number that a resuming \
         subscriber would treat as a resume token and skip rows from"
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn a_session_binds_over_the_wire_and_the_client_is_a_real_control_plane() {
    // `GrpcControlPlane` implements `dp::ControlPlane`, so `SessionContext::bind`
    // — the one constructor for a `RealityId` — works against a REMOTE control
    // plane. That is the thing 5C exists to make possible.
    let endpoint = serve().await;
    let plane = GrpcControlPlane::connect(endpoint).await.expect("connect");

    let ctx = dp::SessionContext::bind(
        &plane,
        dp::BindRequest {
            reality: Uuid::from_u128(REALITY),
            node: "pod-9".into(),
            service: service(),
        },
        1_000,
    )
    .expect("bind over grpc");

    assert_eq!(ctx.reality_id().as_uuid(), Uuid::from_u128(REALITY));
    assert_eq!(ctx.node_id().as_str(), "pod-9");
    assert!(ctx.check_live(60_999).is_ok(), "inside the TTL minted by the server");
    assert!(ctx.check_live(61_000).is_err(), "at expiry");

    // …and the session is routable by id, without presenting the capability.
    let node = plane.session_node(ctx.session_id().as_uuid()).expect("session_node");
    assert_eq!(node.as_deref(), Some("pod-9"));

    // An unknown session is `None`, not an error.
    assert_eq!(plane.session_node(Uuid::nil()).expect("absent"), None);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn a_refresh_over_the_wire_extends_without_re_issuing() {
    let endpoint = serve().await;
    let plane = GrpcControlPlane::connect(endpoint).await.expect("connect");

    let bound = plane
        .verify_bind(&dp::BindRequest {
            reality: Uuid::from_u128(REALITY),
            node: "pod-3".into(),
            service: service(),
        })
        .expect("bind");
    assert_eq!(bound.expires_at_ms, 61_000, "clock(1000) + ttl(60000)");

    let refreshed = plane
        .refresh_capability(&bound.capability_secret)
        .expect("refresh over grpc");
    assert_eq!(refreshed.session, bound.session);
    assert_eq!(
        refreshed.capability_secret, bound.capability_secret,
        "the secret must not travel a second time"
    );
    // The clock is fixed at 1_000, so a refresh lands on the same expiry — the
    // assertion is that it APPLIED, which the CAS proves by not refusing.
    assert_eq!(refreshed.expires_at_ms, 61_000);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn a_forged_capability_is_refused_without_saying_which_kind_of_wrong_it_is() {
    // The server collapses "never issued" and "revoked" into one
    // UNAUTHENTICATED so the endpoint is not an oracle for whether a guessed
    // secret exists. This asserts the collapse, because a helpful error message
    // added later would undo it silently.
    let endpoint = serve().await;
    let mut c = DpControlPlaneClient::connect(endpoint).await.expect("connect");

    let err = c
        .refresh_capability(pb::RefreshCapabilityRequest {
            capability_secret: "a-secret-nobody-minted".into(),
        })
        .await
        .expect_err("must refuse");

    assert_eq!(err.code(), tonic::Code::Unauthenticated);
    assert_eq!(err.message(), "capability is not valid");
    assert!(
        !err.message().contains("nobody-minted"),
        "the rejected credential must not be echoed back: {}",
        err.message()
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn the_wire_refuses_a_service_identity_the_library_would_refuse() {
    // A request field is whatever the caller typed, so the server validates it
    // with the SAME constructor the in-process path uses. Without this, the
    // anonymous capability `5B` made unrepresentable in Rust would be
    // constructible by anyone who could reach the socket.
    let endpoint = serve().await;
    let mut c = DpControlPlaneClient::connect(endpoint).await.expect("connect");
    let r = Uuid::from_u128(REALITY).to_string();

    for (label, identity) in [
        ("empty", ""),
        ("whitespace-only", "   "),
        ("newline (log injection)", "commit\nservice"),
    ] {
        let err = c
            .bind_session(pb::BindSessionRequest {
                reality_id: r.clone(),
                node_id: "pod-1".into(),
                service_identity: identity.into(),
            })
            .await
            .expect_err(label);
        assert_eq!(err.code(), tonic::Code::InvalidArgument, "{label}: {err}");
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn an_absent_reality_is_a_plain_answer_to_verify_and_not_found_to_resolve() {
    // The two methods differ on purpose: "does this exist and can I use it" has
    // `false` as an ordinary answer, while "give me its endpoints" has no
    // answer at all for a reality that is not there.
    let endpoint = serve().await;
    let mut c = DpControlPlaneClient::connect(endpoint).await.expect("connect");
    let absent = Uuid::nil().to_string();

    let verified = c
        .verify_reality(pb::VerifyRealityRequest { reality_id: absent.clone() })
        .await
        .expect("verify is not an error")
        .into_inner();
    assert!(!verified.bindable);
    assert_eq!(verified.status, "");

    let err = c
        .resolve_reality(pb::ResolveRealityRequest { reality_id: absent })
        .await
        .expect_err("resolve has nothing to return");
    assert_eq!(err.code(), tonic::Code::NotFound);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn resolve_reality_carries_the_registry_row_across_the_wire() {
    let endpoint = serve().await;
    let mut c = DpControlPlaneClient::connect(endpoint).await.expect("connect");

    let e = c
        .resolve_reality(pb::ResolveRealityRequest {
            reality_id: Uuid::from_u128(REALITY).to_string(),
        })
        .await
        .expect("resolve")
        .into_inner();

    assert_eq!(e.db_host, "pg-shard-0.internal");
    assert_eq!(e.db_name, "lw_reality_surface");
    assert_eq!(e.status, "active");
    assert_eq!(e.locale, "en");
    assert_eq!(e.deploy_cohort, 7, "the canary cohort must survive the u8->u32 widening");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn a_non_uuid_reality_id_is_refused_before_any_lookup() {
    let endpoint = serve().await;
    let mut c = DpControlPlaneClient::connect(endpoint).await.expect("connect");
    let err = c
        .verify_reality(pb::VerifyRealityRequest { reality_id: "not-a-uuid".into() })
        .await
        .expect_err("must refuse");
    assert_eq!(err.code(), tonic::Code::InvalidArgument);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn health_reports_reachability_of_the_state_not_merely_of_the_process() {
    let endpoint = serve().await;
    let plane = GrpcControlPlane::connect(endpoint).await.expect("connect");
    let (healthy, detail) = plane.health().expect("health");
    assert!(healthy, "{detail}");
    assert_eq!(detail, "meta reachable");
}
