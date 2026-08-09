//! The tonic server, over `meta_rs::control_plane::MetaControlPlane`.
//!
//! `expect`, not `allow`, and the difference matters: an `expect` FAILS the
//! build the day it stops being needed, so the pragma removes itself. Every
//! signature in this file returns `Result<_, tonic::Status>` because that is
//! what tonic's generated trait declares — the shape is not ours to change, and
//! `Status` is 176 bytes. If tonic ever boxes it, this line becomes an
//! unfulfilled expectation and must go.
#![expect(
    clippy::result_large_err,
    reason = "tonic::Status is 176 bytes and the trait signatures returning it are generated; \
              this expectation goes unfulfilled the day tonic boxes it"
)]

use std::pin::Pin;

use dp::ControlPlane as _;
use meta_rs::control_plane::{Clock, MetaControlPlane, SecretSource};
use meta_rs::routing::MetaRead;
use meta_rs::session_store::CapabilityStore;
use tonic::{Request, Response, Status};

use crate::pb;
use crate::pb::dp_control_plane_server::DpControlPlane;
use crate::unimplemented_reason;

/// The stream type the two streaming RPCs declare.
///
/// Both are `UNIMPLEMENTED`, so no value of this type is ever constructed — but
/// the associated type must still exist, and a `Pin<Box<dyn Stream>>` is the
/// shape a real implementation would use anyway, so `5D` and the tier-policy
/// work do not have to change the signature to start returning rows.
type BoxStream<T> = Pin<Box<dyn tokio_stream::Stream<Item = Result<T, Status>> + Send + 'static>>;

/// `DP-C3`'s surface, backed by the meta control plane.
pub struct ControlPlaneService<R, K, C, S> {
    plane: MetaControlPlane<R, K, C, S>,
}

impl<R, K, C, S> ControlPlaneService<R, K, C, S> {
    /// Wrap a control plane.
    pub fn new(plane: MetaControlPlane<R, K, C, S>) -> Self {
        Self { plane }
    }
}

/// A `DpError` becomes a gRPC status.
///
/// # The mapping is a security decision, not a formatting one
///
/// `SessionNotFound` and `CapabilityExpired` both mean *"this capability does
/// not work"* and both map to `UNAUTHENTICATED` with the SAME message. Telling
/// a caller which one it was distinguishes *"you presented a secret I never
/// issued"* from *"you presented one I issued and then revoked"* — which turns
/// the endpoint into an oracle for whether a guessed secret exists.
///
/// `ControlPlaneUnavailable` stays `UNAVAILABLE` and keeps its reason: it is an
/// operational fact about the server, not about the caller's credential, and a
/// caller needs it to decide whether to retry.
fn to_status(e: dp::DpError) -> Status {
    match e.variant_name() {
        "SessionNotFound" | "CapabilityExpired" => {
            Status::unauthenticated("capability is not valid")
        }
        "RealityMismatch" => Status::failed_precondition(e.to_string()),
        "ControlPlaneUnavailable" => Status::unavailable(e.to_string()),
        _ => Status::internal(e.to_string()),
    }
}

/// `UNIMPLEMENTED`, naming the state that is missing.
fn not_built(method: &str) -> Status {
    match unimplemented_reason(method) {
        Some(why) => Status::unimplemented(format!("{method}: {why}")),
        // A method reaching here that is NOT on the list is a bug in the list,
        // and saying so is more useful than a generic error — the list is
        // supposed to be exhaustive and a test asserts it.
        None => Status::internal(format!(
            "{method} returned UNIMPLEMENTED but is absent from UNIMPLEMENTED_METHODS"
        )),
    }
}

fn parse_uuid(raw: &str, field: &str) -> Result<uuid::Uuid, Status> {
    uuid::Uuid::parse_str(raw)
        .map_err(|_| Status::invalid_argument(format!("{field} is not a uuid: {raw:?}")))
}

#[tonic::async_trait]
impl<R, K, C, S> DpControlPlane for ControlPlaneService<R, K, C, S>
where
    R: MetaRead + Send + Sync + 'static,
    K: CapabilityStore + 'static,
    C: Clock + Send + Sync + 'static,
    S: SecretSource + Send + Sync + 'static,
{
    // ── Group A: session + capability ───────────────────────────────────────

    async fn verify_reality(
        &self,
        request: Request<pb::VerifyRealityRequest>,
    ) -> Result<Response<pb::VerifyRealityResponse>, Status> {
        let reality = parse_uuid(&request.into_inner().reality_id, "reality_id")?;
        let routing = self
            .plane
            .reality_routing(reality)
            .map_err(|e| Status::unavailable(e.to_string()))?;
        Ok(Response::new(match routing {
            // An ABSENT reality is `bindable = false` with an empty status, not
            // an error: "does this exist and can I use it" is exactly the
            // question, and NOT_FOUND would make the caller handle the ordinary
            // answer as a failure.
            None => pb::VerifyRealityResponse { bindable: false, status: String::new() },
            Some(r) => pb::VerifyRealityResponse {
                bindable: r.accepts_commands(),
                status: r.status.as_str().to_string(),
            },
        }))
    }

    async fn bind_session(
        &self,
        request: Request<pb::BindSessionRequest>,
    ) -> Result<Response<pb::BindSessionResponse>, Status> {
        let req = request.into_inner();
        let reality = parse_uuid(&req.reality_id, "reality_id")?;

        // The identity is validated HERE rather than trusted, because a request
        // field is whatever the caller typed. `ServiceIdentity::new` is the same
        // constructor the in-process path uses, so the wire cannot admit a name
        // the library would refuse.
        let service = dp::ServiceIdentity::new(req.service_identity.clone()).ok_or_else(|| {
            Status::invalid_argument(
                "service_identity must be non-blank, at most 128 chars, and free of control characters",
            )
        })?;

        let v = self
            .plane
            .verify_bind(&dp::BindRequest { reality, node: req.node_id, service })
            .map_err(to_status)?;

        Ok(Response::new(pb::BindSessionResponse {
            reality_id: v.reality.to_string(),
            session_id: v.session.to_string(),
            capability_secret: v.capability_secret,
            expires_at_ms: v.expires_at_ms,
        }))
    }

    async fn refresh_capability(
        &self,
        request: Request<pb::RefreshCapabilityRequest>,
    ) -> Result<Response<pb::RefreshCapabilityResponse>, Status> {
        let secret = request.into_inner().capability_secret;
        let now = self.plane.now_unix_ms();
        let v = self.plane.refresh_capability(&secret, now).map_err(to_status)?;
        Ok(Response::new(pb::RefreshCapabilityResponse {
            reality_id: v.reality.to_string(),
            session_id: v.session.to_string(),
            expires_at_ms: v.expires_at_ms,
        }))
    }

    // ── Group B: tier policy — no `tier_policy` table exists ────────────────

    async fn get_tier_policy(
        &self,
        _request: Request<pb::GetTierPolicyRequest>,
    ) -> Result<Response<pb::TierPolicySnapshot>, Status> {
        Err(not_built("GetTierPolicy"))
    }

    type StreamTierPolicyUpdatesStream = BoxStream<pb::TierPolicyDelta>;

    async fn stream_tier_policy_updates(
        &self,
        _request: Request<pb::StreamTierPolicyRequest>,
    ) -> Result<Response<Self::StreamTierPolicyUpdatesStream>, Status> {
        Err(not_built("StreamTierPolicyUpdates"))
    }

    // ── Group C: reality registry ───────────────────────────────────────────

    async fn resolve_reality(
        &self,
        request: Request<pb::ResolveRealityRequest>,
    ) -> Result<Response<pb::RealityEndpoints>, Status> {
        let reality = parse_uuid(&request.into_inner().reality_id, "reality_id")?;
        let routing = self
            .plane
            .reality_routing(reality)
            .map_err(|e| Status::unavailable(e.to_string()))?
            // Here NOT_FOUND is right, and the contrast with `VerifyReality`
            // above is deliberate: resolve is asked for endpoints, and there is
            // no such thing as the endpoints of a reality that does not exist.
            .ok_or_else(|| Status::not_found(format!("no such reality: {reality}")))?;

        Ok(Response::new(pb::RealityEndpoints {
            reality_id: routing.reality_id.to_string(),
            db_host: routing.db_host,
            db_name: routing.db_name,
            status: routing.status.as_str().to_string(),
            locale: routing.locale,
            deploy_cohort: u32::from(routing.deploy_cohort),
        }))
    }

    type StreamRealityTransitionsStream = BoxStream<pb::RealityTransition>;

    async fn stream_reality_transitions(
        &self,
        _request: Request<pb::StreamRealityTransitionsRequest>,
    ) -> Result<Response<Self::StreamRealityTransitionsStream>, Status> {
        Err(not_built("StreamRealityTransitions"))
    }

    // ── Group D: session stickiness + NPC binding ───────────────────────────

    async fn get_session_node(
        &self,
        request: Request<pb::GetSessionNodeRequest>,
    ) -> Result<Response<pb::NodeAssignment>, Status> {
        let session = parse_uuid(&request.into_inner().session_id, "session_id")?;
        let found = self
            .plane
            .session_node(session)
            .map_err(|e| Status::unavailable(e.to_string()))?;
        Ok(Response::new(match found {
            // `assigned: false` rather than NOT_FOUND, and rather than an empty
            // node_id: an unbound session is an ordinary answer, and `""` would
            // read as "assigned to the node named empty-string".
            None => pb::NodeAssignment { node_id: String::new(), assigned: false },
            Some(node_id) => pb::NodeAssignment { node_id, assigned: true },
        }))
    }

    async fn get_npc_node(
        &self,
        _request: Request<pb::GetNpcNodeRequest>,
    ) -> Result<Response<pb::NodeAssignment>, Status> {
        Err(not_built("GetNpcNode"))
    }

    async fn report_node_handoff(
        &self,
        _request: Request<pb::ReportNodeHandoffRequest>,
    ) -> Result<Response<pb::Empty>, Status> {
        Err(not_built("ReportNodeHandoff"))
    }

    // ── Group E: schema + migration — no `schema_version` table exists ──────

    async fn get_schema_version(
        &self,
        _request: Request<pb::GetSchemaVersionRequest>,
    ) -> Result<Response<pb::SchemaVersion>, Status> {
        Err(not_built("GetSchemaVersion"))
    }

    async fn announce_migration_start(
        &self,
        _request: Request<pb::AnnounceMigrationStartRequest>,
    ) -> Result<Response<pb::Empty>, Status> {
        Err(not_built("AnnounceMigrationStart"))
    }

    async fn announce_migration_complete(
        &self,
        _request: Request<pb::AnnounceMigrationCompleteRequest>,
    ) -> Result<Response<pb::Empty>, Status> {
        Err(not_built("AnnounceMigrationComplete"))
    }

    // ── Group F: health ─────────────────────────────────────────────────────

    async fn health(&self, _request: Request<pb::Empty>) -> Result<Response<pb::HealthReport>, Status> {
        // Health is not "the process is up" — the process answering at all
        // proves that. It is "can I reach the state I serve from", which is the
        // question an operator is actually asking, and the only way to answer it
        // is to touch the store.
        let (healthy, detail) = match self.plane.reality_routing(uuid::Uuid::nil()) {
            // The nil uuid is not in the registry, so `Ok(None)` IS the healthy
            // answer: the query ran and the row is absent. `Ok(Some(_))` would
            // be a surprise but is equally proof the read path works.
            Ok(_) => (true, "meta reachable".to_string()),
            Err(e) => (false, format!("meta unreachable: {e}")),
        };
        Ok(Response::new(pb::HealthReport { healthy, detail }))
    }
}
