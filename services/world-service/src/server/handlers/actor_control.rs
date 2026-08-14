//! `SEALED-BINDING` — the grant/revoke surface for `actor_control_binding`.
//!
//! The table has existed since migration `034` with three declared events, one
//! reader (the GDPR erasure cascade) and **no writer at all**. These two routes
//! are that writer. Until they existed the only `INSERT` in the tree was a test
//! fixture, so the table was empty by construction — the same state `035`
//! recorded about the table `034` replaced, and the reason that one was dropped
//! rather than kept.
//!
//! Thin adapters, like every handler here: decode → call the bridge → encode.
//! No control logic lives in this file. The write itself goes through the Go
//! meta-write bridge because `I8` requires the `meta_write_audit` row and the
//! outbox event to land in the SAME transaction as the binding, and only Go's
//! `MetaWrite` can do that.

use axum::Json;
use axum::extract::State;
use axum::extract::rejection::JsonRejection;
use axum::http::StatusCode;
use serde::{Deserialize, Serialize};
use service_http::ProblemDetails;
use uuid::Uuid;

use crate::actor_registry;
use crate::errors::ProvisionerError;
use crate::provision_flow::existing_registration;
use crate::provisioner_live::BridgeClient;
use crate::server::state::AppState;

/// `POST /internal/v1/actor-control/grant`.
#[derive(Debug, Clone, Deserialize)]
pub struct GrantRequest {
    /// WHO drives. Opaque; the only user reference in the binding.
    pub user_ref_id: Uuid,
    pub reality_id: Uuid,
    /// The per-reality actor identity. Deliberately unconstrained here — its FK
    /// lives in the per-reality database, which is `034`'s reason 3.
    pub actor_id: Uuid,
    #[serde(default)]
    pub reason: Option<String>,
}

/// `POST /internal/v1/actor-control/revoke`.
#[derive(Debug, Clone, Deserialize)]
pub struct RevokeRequest {
    pub reality_id: Uuid,
    pub actor_id: Uuid,
    /// Optional CAS. When present the revoke applies only while this user still
    /// holds the binding; otherwise `409`. A caller acting on a stale character
    /// list MUST send it, or it will revoke whoever took over instead.
    #[serde(default)]
    pub expected_user_ref_id: Option<Uuid>,
    #[serde(default)]
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ControlResponse {
    /// `granted` · `already_granted` · `revoked` · `already_revoked`.
    pub outcome: &'static str,
    pub reality_id: Uuid,
    pub actor_id: Uuid,
}

/// `POST /internal/v1/actors`.
#[derive(Debug, Clone, Deserialize)]
pub struct CreateActorRequest {
    pub reality_id: Uuid,
    /// Optional. Omit and the registry ALLOCATES the island id — which is the
    /// normal path and the reason the registry is the SSOT for that number.
    /// Supply one only to ADOPT an entity the island already has (the spine's
    /// hardcoded `EntityId(1..3)`), which is the case that would otherwise make
    /// every existing island undrivable by this feature.
    #[serde(default)]
    pub entity_id: Option<i64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct CreateActorResponse {
    pub reality_id: Uuid,
    /// The PLATFORM identity — what a binding points at.
    pub actor_id: Uuid,
    /// The ISLAND identity — what the simulation acts on.
    pub entity_id: i64,
}

/// Create (or adopt) an actor in a reality.
///
/// This is `actor_control_binding`'s missing precondition. Until it existed the
/// binding pointed at a uuid with no durable home — `S-9`, measured: after
/// `0017` dropped the `pc_*`/`npc_*` projections, no per-reality actor table
/// survived at all.
pub async fn create_actor(
    State(state): State<AppState>,
    body: Result<Json<CreateActorRequest>, JsonRejection>,
) -> Result<(StatusCode, Json<CreateActorResponse>), ProblemDetails> {
    let Json(req) = body.map_err(|e| {
        ProblemDetails::new(e.status(), "invalid-body", "Invalid request body", e.body_text())
    })?;
    let reality = bind(&state, req.reality_id).await?;
    let pool = reality_pool(&state, &reality).await?;
    let row = match req.entity_id {
        None => actor_registry::create_actor(&pool, &reality).await,
        Some(e) => actor_registry::adopt_actor(&pool, &reality, e).await,
    }
    .map_err(to_problem)?;
    Ok((
        StatusCode::CREATED,
        Json(CreateActorResponse {
            reality_id: req.reality_id,
            actor_id: row.actor_id,
            entity_id: row.entity_id,
        }),
    ))
}

/// Open a pool on the reality's own database.
///
/// Per request rather than cached: this is a control-plane route taken once per
/// grant, not a hot path, and a pool cache keyed by reality is state with a
/// lifecycle nobody has designed. When it becomes a hot path it should be
/// cached deliberately, with an eviction rule, rather than by accident now.
async fn reality_pool(state: &AppState, reality: &dp::RealityId) -> Result<sqlx::PgPool, ProblemDetails> {
    let reality_id = reality.as_uuid();
    let reg = existing_registration(&state.meta, reality_id)
        .await
        .map_err(to_problem)?
        .ok_or_else(|| ProblemDetails::bad_request(format!("reality {reality_id} is not registered")))?;
    let dsn = format!(
        "postgres://{}:{}@{}/{}?sslmode=disable",
        state.effects.pg_user, state.effects.pg_pass, state.effects.shard_hostport, reg.db_name
    );
    sqlx::PgPool::connect(&dsn).await.map_err(|e| {
        tracing::error!(error = %e, %reality_id, "reality pool connect failed");
        ProblemDetails::internal("could not reach the reality database")
    })
}

/// Grant control of an actor.
///
/// `201` granted · `200` this user already drives it · `409` somebody else
/// does. The 409 is a normal answer about the world, not a failure of ours —
/// see [`to_problem`].
pub async fn grant_control(
    State(state): State<AppState>,
    body: Result<Json<GrantRequest>, JsonRejection>,
) -> Result<(StatusCode, Json<ControlResponse>), ProblemDetails> {
    let Json(req) = body.map_err(|e| {
        ProblemDetails::new(e.status(), "invalid-body", "Invalid request body", e.body_text())
    })?;
    // THE ACTOR MUST EXIST. `034` left `actor_id` unconstrained because its FK
    // lives in another database — a correct reason to have no foreign key and a
    // bad reason to skip the check. This process can reach both databases, so
    // it is the one place the check can happen at the write edge instead of
    // being discovered by a resolver at turn time.
    let reality = bind(&state, req.reality_id).await?;
    let pool = reality_pool(&state, &reality).await?;
    if !actor_registry::actor_exists(&pool, &reality, req.actor_id)
        .await
        .map_err(to_problem)?
    {
        return Err(ProblemDetails::bad_request(format!(
            "actor {} does not exist in reality {} — create it first; a binding to an \
             actor with no durable identity is the dangling pointer S-9 describes",
            req.actor_id, req.reality_id
        )));
    }

    let granted = bridge(&state)
        .grant_actor_control(
            req.user_ref_id,
            req.reality_id,
            req.actor_id,
            req.reason.as_deref().unwrap_or("grant actor control"),
        )
        .await
        .map_err(to_problem)?;
    Ok((
        if granted { StatusCode::CREATED } else { StatusCode::OK },
        Json(ControlResponse {
            outcome: if granted { "granted" } else { "already_granted" },
            reality_id: req.reality_id,
            actor_id: req.actor_id,
        }),
    ))
}

/// Revoke control of an actor.
///
/// Always `200` when it succeeds, because both outcomes are the end state the
/// caller asked for; the body says which happened. `409` only when the CAS
/// names a user who no longer holds the binding.
pub async fn revoke_control(
    State(state): State<AppState>,
    body: Result<Json<RevokeRequest>, JsonRejection>,
) -> Result<(StatusCode, Json<ControlResponse>), ProblemDetails> {
    let Json(req) = body.map_err(|e| {
        ProblemDetails::new(e.status(), "invalid-body", "Invalid request body", e.body_text())
    })?;
    let revoked = bridge(&state)
        .revoke_actor_control(
            req.reality_id,
            req.actor_id,
            req.expected_user_ref_id,
            req.reason.as_deref().unwrap_or("revoke actor control"),
        )
        .await
        .map_err(to_problem)?;
    Ok((
        StatusCode::OK,
        Json(ControlResponse {
            outcome: if revoked { "revoked" } else { "already_revoked" },
            reality_id: req.reality_id,
            actor_id: req.actor_id,
        }),
    ))
}

/// Bind the reality through the control plane, or refuse.
///
/// `dp::RealityId` has NO public constructor — it is only ever the output of
/// `SessionContext::bind`, so holding one is proof the control plane confirmed
/// the reality exists and ACCEPTS COMMANDS. `MetaControlPlane` refuses
/// `Provisioning`, `Frozen`, `Archived`, `SoftDeleted` and `Dropped`.
///
/// That is why this is not a naming exercise. Granting a human control of an
/// actor in a FROZEN reality is exactly what should not happen, and before the
/// bind existed this code could not even ask the question.
async fn bind(state: &AppState, reality_id: Uuid) -> Result<dp::RealityId, ProblemDetails> {
    let reader = meta_rs::sqlx_pg::PgConnectionReader::new(state.meta.clone())
        .map_err(|e| { tracing::error!(error = %e, "meta reader"); ProblemDetails::internal("control plane unavailable") })?;
    let store = meta_rs::sqlx_pg::PgCapabilityStore::new(
        state.meta.clone(),
        meta_rs::allowlist::Allowlist::load(&state.effects.meta_allowlist)
            .map_err(|e| { tracing::error!(error = %e, "allowlist"); ProblemDetails::internal("control plane unavailable") })?,
        meta_rs::metawrite::Actor {
            actor_type: meta_rs::metawrite::ActorType::System,
            id: "world-service".to_string(),
            svid: None,
        },
    )
    .map_err(|e| { tracing::error!(error = %e, "capability store"); ProblemDetails::internal("control plane unavailable") })?;
    let plane = meta_rs::control_plane::MetaControlPlane::new(
        meta_rs::routing::DefaultMetaRead::new(reader), store);
    let service = dp::ServiceIdentity::new("world-service")
        .ok_or_else(|| ProblemDetails::internal("service identity"))?;
    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|_| ProblemDetails::internal("clock"))?
        .as_millis() as u64;
    let ctx = dp::SessionContext::bind(
        &plane,
        dp::BindRequest { reality: reality_id, node: "world-service".to_string(), service },
        now_ms,
    )
    .map_err(|e| {
        // A refusal here is a statement about the WORLD: the reality is frozen,
        // archived, dropped, or does not exist. The caller can act on that.
        ProblemDetails::bad_request(format!(
            "reality {reality_id} does not accept commands: {e}"
        ))
    })?;
    Ok(ctx.reality_id().to_owned())
}

fn bridge(state: &AppState) -> BridgeClient {
    BridgeClient::new(state.effects.bridge_url.clone(), state.effects.bridge_token.clone())
}

/// The two client-actionable faults are `409`; everything else is ours.
///
/// Both of them are statements about the WORLD — somebody else drives this
/// actor, or the user you named no longer holds it — and a caller can act on
/// each. Rendering either as a 500 would tell an operator the service is broken
/// when it is working exactly as designed, which is the mistake
/// [`ProvisionerError::ActorAlreadyDriven`] exists as its own variant to avoid.
fn to_problem(err: ProvisionerError) -> ProblemDetails {
    match err {
        ProvisionerError::ActorAlreadyDriven(actor) => ProblemDetails::conflict(format!(
            "actor {actor} is already driven by another user; revoke first, do not blind-retry"
        )),
        ProvisionerError::ControlCasMismatch(actor) => ProblemDetails::conflict(format!(
            "the expected user no longer holds the binding for actor {actor}; reload and decide"
        )),
        other => {
            tracing::error!(error = %other, "actor-control write failed");
            ProblemDetails::internal("actor-control write failed")
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Non-vacuity, both directions. A test that only asserted the two 409s
    /// would pass just as well if EVERY variant mapped to 409 — which would
    /// turn a bridge outage into "somebody else drives this actor" and send an
    /// operator looking for a player who does not exist.
    #[test]
    fn the_two_client_actionable_faults_are_409_and_the_rest_are_500() {
        let a = to_problem(ProvisionerError::ActorAlreadyDriven("x".into()));
        let b = to_problem(ProvisionerError::ControlCasMismatch("x".into()));
        assert_eq!(a.status, StatusCode::CONFLICT, "already-driven must be 409");
        assert_eq!(b.status, StatusCode::CONFLICT, "CAS mismatch must be 409");

        for other in [
            ProvisionerError::Bridge("the bridge is down".into()),
            ProvisionerError::NotFound("r".into()),
            ProvisionerError::NoShardCapacity,
        ] {
            let p = to_problem(other);
            assert_eq!(
                p.status,
                StatusCode::INTERNAL_SERVER_ERROR,
                "a fault the client cannot act on must not be reported as a conflict"
            );
        }
    }
}
