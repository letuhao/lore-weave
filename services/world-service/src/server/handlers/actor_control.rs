//! `SEALED-BINDING` — the grant/revoke HTTP surface for `actor_control_binding`.
//!
//! The table has existed since migration `034` with three declared events, one
//! reader (the GDPR erasure cascade) and **no writer at all**. These routes are
//! that writer. Until they existed the only `INSERT` in the tree was a test
//! fixture, so the table was empty by construction — the same state `035`
//! recorded about the table `034` replaced, and the reason that one was dropped
//! rather than kept.
//!
//! Thin adapters, like every handler here: decode → call the flow → encode.
//! **The header used to say that while the reality bind and the actor-exists
//! precondition sat right here**, reachable only over HTTP. They now live in
//! [`crate::actor_control_flow`], where the `admin reality grant-control`
//! worker reaches the same two checks instead of growing its own.

use axum::Json;
use axum::extract::State;
use axum::extract::rejection::JsonRejection;
use axum::http::StatusCode;
use serde::{Deserialize, Serialize};
use service_http::ProblemDetails;
// Imported rather than called fully-qualified: `tracing-completeness-lint`
// reads the IMPORT to decide a handler file is traced, and this file shipped
// with `tracing::error!` and no `use`, which put the tree one over its ratchet.
use tracing::error;
use uuid::Uuid;

use crate::actor_control_flow as flow;
use crate::errors::ProvisionerError;
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
    /// `A3` — WHERE the actor arrives, and as what.
    ///
    /// Optional, and its absence is a real answer rather than a default: an
    /// actor with no siting exists and is nowhere, which is what every actor in
    /// this repo was until now. Supplying it makes the actor row and its
    /// `entity_binding` land in ONE transaction, so the actor cannot exist with
    /// nowhere to be.
    #[serde(default)]
    pub siting: Option<crate::spawn::Siting>,
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
    let Json(req) = body.map_err(invalid_body)?;
    let row = flow::create_actor(
        &state.meta,
        &state.effects,
        req.reality_id,
        req.entity_id,
        req.siting.as_ref(),
    )
    .await
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

/// Grant control of an actor.
///
/// `201` granted · `200` this user already drives it · `409` somebody else
/// does. The 409 is a normal answer about the world, not a failure of ours —
/// see [`to_problem`].
pub async fn grant_control(
    State(state): State<AppState>,
    body: Result<Json<GrantRequest>, JsonRejection>,
) -> Result<(StatusCode, Json<ControlResponse>), ProblemDetails> {
    let Json(req) = body.map_err(invalid_body)?;
    let outcome = flow::grant(
        &state.meta,
        &state.effects,
        req.user_ref_id,
        req.reality_id,
        req.actor_id,
        req.reason.as_deref().unwrap_or("grant actor control"),
    )
    .await
    .map_err(to_problem)?;
    Ok((
        if outcome.changed() { StatusCode::CREATED } else { StatusCode::OK },
        Json(ControlResponse {
            outcome: outcome.as_str(),
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
    let Json(req) = body.map_err(invalid_body)?;
    let outcome = flow::revoke(
        &state.meta,
        &state.effects,
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
            outcome: outcome.as_str(),
            reality_id: req.reality_id,
            actor_id: req.actor_id,
        }),
    ))
}

/// `POST /internal/v1/actor-control/subject`.
///
/// **The request names the user it is asking ABOUT, and that is the whole
/// reason this route is internal-gated.** It is owner-scoped with respect to
/// the SUBJECT — it answers only "which actor does user U drive", never "who
/// drives actor A" — but the caller is a service (`game-server`), not the human
/// in question, so the scoping is a property of the QUERY, not of an
/// authenticated session. A public edge would make `user_ref_id` an oracle.
#[derive(Debug, Clone, Deserialize)]
pub struct SubjectRequest {
    pub reality_id: Uuid,
    /// WHOSE binding to resolve. The transport takes this from the redeemed WS
    /// ticket, never from anything the client sent — `SEALED-SUBJECT`.
    pub user_ref_id: Uuid,
}

/// What the caller drives, or `null`.
#[derive(Debug, Clone, Serialize)]
pub struct SubjectResponse {
    pub reality_id: Uuid,
    pub user_ref_id: Uuid,
    /// `None` = this user drives nobody in this reality. A normal answer for a
    /// spectator and for the instant after a revoke, which is why it is a
    /// `200` with a null and not a `404`.
    #[serde(rename = "self")]
    pub self_: Option<SubjectBody>,
}

/// The two spellings of the actor, as [`crate::actor_control_flow::Subject`].
#[derive(Debug, Clone, Copy, Serialize)]
pub struct SubjectBody {
    pub actor_id: Uuid,
    pub entity_id: i64,
}

/// Resolve the caller's own subject.
///
/// Always `200` when the question has an answer, including "nobody" — the
/// distinction the transport needs is `self: null` versus a body, not a status
/// code. `400` is reserved for the three cases where the ANSWER WOULD BE A
/// LIE: an unregistered reality, a closed one, and a binding pointing at an
/// actor the registry lost.
pub async fn resolve_subject(
    State(state): State<AppState>,
    body: Result<Json<SubjectRequest>, JsonRejection>,
) -> Result<(StatusCode, Json<SubjectResponse>), ProblemDetails> {
    let Json(req) = body.map_err(invalid_body)?;
    let found = flow::resolve_subject(&state.meta, &state.effects, req.reality_id, req.user_ref_id)
        .await
        .map_err(to_problem)?;
    Ok((
        StatusCode::OK,
        Json(SubjectResponse {
            reality_id: req.reality_id,
            user_ref_id: req.user_ref_id,
            self_: found
                .map(|s| SubjectBody { actor_id: s.actor_id, entity_id: s.entity_id }),
        }),
    ))
}

fn invalid_body(e: JsonRejection) -> ProblemDetails {
    ProblemDetails::new(e.status(), "invalid-body", "Invalid request body", e.body_text())
}

/// Four faults are client-actionable; everything else is ours.
///
/// Each of the four is a statement about the WORLD — somebody else drives this
/// actor, the user you named no longer holds it, the reality is closed, the
/// actor does not exist — and a caller can act on each. Rendering any of them
/// as a `500` would tell an operator the service is broken when it is working
/// exactly as designed, which is the mistake [`ProvisionerError::ActorAlreadyDriven`]
/// exists as its own variant to avoid.
/// `pub(crate)` as of `A4`: the space handler maps the SAME four
/// client-actionable faults, and a second mapping would be a second opinion on
/// which errors are the caller's -- the drift this function's own doc argues
/// against one paragraph down.
pub(crate) fn to_problem(err: ProvisionerError) -> ProblemDetails {
    match err {
        ProvisionerError::ActorAlreadyDriven(actor) => ProblemDetails::conflict(format!(
            "actor {actor} is already driven by another user; revoke first, do not blind-retry"
        )),
        ProvisionerError::ControlCasMismatch(actor) => ProblemDetails::conflict(format!(
            "the expected user no longer holds the binding for actor {actor}; reload and decide"
        )),
        // 400, not 500: the reality is frozen / archived / absent. Nothing here
        // is broken, and the caller is the one who can do something about it.
        ProvisionerError::RealityClosed(reality, why) => ProblemDetails::bad_request(format!(
            "reality {reality} does not accept commands: {why}"
        )),
        ProvisionerError::UnknownActor(actor, reality) => ProblemDetails::bad_request(format!(
            "actor {actor} does not exist in reality {reality} — create it first; a binding to an \
             actor with no durable identity is the dangling pointer S-9 describes"
        )),
        // On THIS surface `NotFound` has exactly one meaning: the reality has
        // no `reality_registry` row. It reaches here from `open_reality_pool`
        // and from the revoke's existence check, and both are the caller
        // naming a world that does not exist — a typo, not an outage.
        ProvisionerError::NotFound(reality) => ProblemDetails::bad_request(format!(
            "reality {reality} is not registered — check the id"
        )),
        other => {
            error!(error = %other, "actor-control write failed");
            ProblemDetails::internal("actor-control write failed")
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The wire word is `self`, and nothing in Rust enforces that.
    ///
    /// The field must be `self_` because `self` is a keyword, so the JSON name
    /// exists only as a `#[serde(rename)]` attribute. Drop it and the response
    /// carries `self_` — the transport's `body.self` is then `undefined`, which
    /// reads as "this user drives nobody". **A silent no-op that fails OPEN
    /// into the wrong answer**: every player becomes a spectator and nothing
    /// logs an error, which is the shape `panel_id` had no enum for.
    ///
    /// `null` is asserted too. `#[serde(skip_serializing_if)]` added later
    /// would OMIT the key, and an absent key and a null one are the same in
    /// JavaScript but not in a schema that declares `self` required.
    #[test]
    fn the_response_spells_the_subject_key_self_and_keeps_it_when_null() {
        let id = Uuid::from_u128(1);
        let none = serde_json::to_string(&SubjectResponse {
            reality_id: id,
            user_ref_id: id,
            self_: None,
        })
        .expect("serialise");
        assert!(none.contains("\"self\":null"), "spectator response is wrong on the wire: {none}");
        assert!(!none.contains("self_"), "the Rust field name leaked to the wire: {none}");

        let some = serde_json::to_string(&SubjectResponse {
            reality_id: id,
            user_ref_id: id,
            self_: Some(SubjectBody { actor_id: id, entity_id: 7 }),
        })
        .expect("serialise");
        assert!(some.contains("\"self\":{"), "driver response is wrong on the wire: {some}");
        assert!(some.contains("\"entity_id\":7"), "the island id must reach the transport: {some}");
    }

    /// Non-vacuity, both directions. A test that only asserted the four
    /// client-actionable faults would pass just as well if EVERY variant
    /// mapped away from 500 — which would turn a bridge outage into
    /// "somebody else drives this actor" and send an operator looking for a
    /// player who does not exist.
    #[test]
    fn the_client_actionable_faults_are_4xx_and_the_rest_are_500() {
        let a = to_problem(ProvisionerError::ActorAlreadyDriven("x".into()));
        let b = to_problem(ProvisionerError::ControlCasMismatch("x".into()));
        assert_eq!(a.status, StatusCode::CONFLICT, "already-driven must be 409");
        assert_eq!(b.status, StatusCode::CONFLICT, "CAS mismatch must be 409");

        // A closed world and a missing actor are the caller's to fix, and both
        // reached this file as ad-hoc strings before they were variants. If
        // either regressed to the wildcard arm it would become a 500 — an
        // outage report for a reality doing exactly what it was told.
        let c = to_problem(ProvisionerError::RealityClosed("r".into(), "frozen".into()));
        let d = to_problem(ProvisionerError::UnknownActor("a".into(), "r".into()));
        assert_eq!(c.status, StatusCode::BAD_REQUEST, "a closed reality must not read as an outage");
        assert_eq!(d.status, StatusCode::BAD_REQUEST, "an unknown actor is the caller's mistake");

        // An UNREGISTERED reality is the caller's typo. It used to land on the
        // wildcard arm as a 500, and on the CLI that same gap let a mistyped
        // --reality-id come back as "already in the requested state" — a
        // tier-1 revoke reporting success for a world that does not exist.
        let e = to_problem(ProvisionerError::NotFound("r".into()));
        assert_eq!(
            e.status,
            StatusCode::BAD_REQUEST,
            "a reality with no registry row is a typo, not an outage"
        );

        for other in [
            ProvisionerError::Bridge("the bridge is down".into()),
            ProvisionerError::NoShardCapacity,
            ProvisionerError::ShardEffect("disk".into()),
            // `E1` — a registry row holding a negative `entity_id` is OUR data
            // being wrong, not the caller's request. It belongs on the 500 side
            // of this split, and it is listed here so that moving it to a 4xx
            // has to be a deliberate edit to a test that says why.
            ProvisionerError::CorruptEntityId("r".into(), -1),
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
