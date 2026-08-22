//! HTTP handlers.
//!
//! Every handler is a thin adapter: decode → call [`crate::provision_flow`] →
//! encode. No provisioning logic lives here (`WS-F1`).

use axum::Json;
use axum::extract::State;
use axum::extract::rejection::JsonRejection;
use axum::http::StatusCode;
use serde::Serialize;
use service_http::ProblemDetails;
use uuid::Uuid;

use crate::errors::ProvisionerError;
use crate::provision_flow::{
    existing_registration, place_and_provision, resume_on_registered_shard,
};
use crate::provisioner::{ProvisionRequest, StepOutcome};
use crate::server::state::AppState;

/// Which of the three paths the request took.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Outcome {
    /// No registry row existed; the reality was placed and provisioned.
    Provisioned,
    /// A row existed in a live state; the flow re-entered pinned to its shard.
    Resumed,
    /// The reality has already moved past provisioning. Nothing was done.
    AlreadyProvisioned,
}

/// Response body for `POST /internal/v1/realities`.
#[derive(Debug, Clone, Serialize)]
pub struct ProvisionResponse {
    /// Which path the request took.
    pub outcome: Outcome,
    /// The reality.
    pub reality_id: Uuid,
    /// The shard it lives on.
    pub shard_id: String,
    /// Its per-reality database.
    pub db_name: String,
    /// Lifecycle status — present only for [`Outcome::AlreadyProvisioned`],
    /// where it is the reason nothing was done.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
    /// The 11 steps — absent for [`Outcome::AlreadyProvisioned`], because no
    /// steps ran. An empty array would claim a run that did not happen.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub steps: Option<Vec<StepOutcome>>,
}

/// `POST /internal/v1/realities` — provision a reality.
///
/// Idempotent by re-entry: the three outcomes above are the three states a
/// caller can be in, and none of them is an error.
pub async fn provision_reality(
    State(state): State<AppState>,
    body: Result<Json<ProvisionRequest>, JsonRejection>,
) -> Result<(StatusCode, Json<ProvisionResponse>), ProblemDetails> {
    // Rendered as problem+json rather than axum's default text/plain, so the
    // contract's "the error body is RFC 7807" is true of a malformed body too.
    //
    // The rejection's OWN status is preserved rather than flattened to 400:
    // axum distinguishes unreadable JSON (400) from JSON that is not a
    // `ProvisionRequest` (422), the contract documents both, and collapsing them
    // would have made one of those two documented codes unreachable.
    let Json(req) = body.map_err(|e| {
        ProblemDetails::new(e.status(), "invalid-body", "Invalid request body", e.body_text())
    })?;

    // Validate BEFORE the flow. `ProvisionerError` cannot distinguish "your
    // input is bad" from "our machinery failed" — `InvalidState` carries both —
    // so the boundary that owns the status code makes the distinction itself.
    req.validate().map_err(|e| ProblemDetails::bad_request(e.to_string()))?;

    let reality_id = req.reality_id;
    let existing = existing_registration(&state.meta, reality_id).await.map_err(to_problem)?;

    match existing {
        Some(reg) if reg.is_settled() => {
            tracing::info!(%reality_id, status = %reg.status, "provision: already settled, no-op");
            Ok((
                StatusCode::OK,
                Json(ProvisionResponse {
                    outcome: Outcome::AlreadyProvisioned,
                    reality_id,
                    shard_id: reg.db_host,
                    db_name: reg.db_name,
                    status: Some(reg.status),
                    steps: None,
                }),
            ))
        }
        Some(reg) => {
            tracing::info!(
                %reality_id, shard = %reg.db_host, status = %reg.status,
                "provision: resuming on the registered shard; placement skipped"
            );
            let report =
                resume_on_registered_shard(&state.meta, &state.shard_admin, req, &reg, &state.effects)
                    .await
                    .map_err(to_problem)?;
            Ok((
                StatusCode::OK,
                Json(ProvisionResponse {
                    outcome: Outcome::Resumed,
                    reality_id: report.reality_id,
                    shard_id: reg.db_host,
                    db_name: report.db_name,
                    status: None,
                    steps: Some(report.steps),
                }),
            ))
        }
        None => {
            let (shard, report) = place_and_provision(
                &state.meta,
                &state.shard_admin,
                &state.planner,
                req,
                &state.effects,
            )
            .await
            .map_err(to_problem)?;
            tracing::info!(
                %reality_id, shard = %shard.as_str(), db = %report.db_name,
                steps = report.steps.len(), "provision: complete"
            );
            Ok((
                StatusCode::CREATED,
                Json(ProvisionResponse {
                    outcome: Outcome::Provisioned,
                    reality_id: report.reality_id,
                    shard_id: shard.as_str().to_string(),
                    db_name: report.db_name,
                    status: None,
                    steps: Some(report.steps),
                }),
            ))
        }
    }
}

/// Map a provisioning failure onto an HTTP status.
///
/// The three 409s are the states where the caller can meaningfully act — free
/// capacity, or reload and decide. Everything else is a fault on our side and
/// must not leak its detail beyond the log.
fn to_problem(err: ProvisionerError) -> ProblemDetails {
    match err {
        ProvisionerError::NoShardCapacity => ProblemDetails::conflict(
            "no shard has capacity; escalate rather than retry",
        ),
        ProvisionerError::AlreadyProvisioned(id) => {
            ProblemDetails::conflict(format!("reality {id} is already provisioned"))
        }
        ProvisionerError::ConcurrentTransition(m) => ProblemDetails::conflict(format!(
            "concurrent transition: {m}; reload and decide, do not blind-retry"
        )),
        other => {
            tracing::error!(error = %other, "provisioning failed");
            ProblemDetails::internal("provisioning failed")
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_three_client_actionable_faults_are_409_and_the_rest_are_500() {
        // Non-vacuity: assert BOTH directions. A test that only checked the
        // 409s would pass if every variant mapped to 409.
        assert_eq!(to_problem(ProvisionerError::NoShardCapacity).status, 409);
        assert_eq!(to_problem(ProvisionerError::AlreadyProvisioned("x".into())).status, 409);
        assert_eq!(to_problem(ProvisionerError::ConcurrentTransition("x".into())).status, 409);
        assert_eq!(to_problem(ProvisionerError::Bridge("x".into())).status, 500);
        assert_eq!(to_problem(ProvisionerError::ShardEffect("x".into())).status, 500);
        assert_eq!(to_problem(ProvisionerError::InvalidState("x".into())).status, 500);
    }

    #[test]
    fn an_internal_fault_does_not_leak_its_detail_to_the_client() {
        let p = to_problem(ProvisionerError::ShardEffect(
            "connect postgres://user:hunter2@shard/db failed".into(),
        ));
        let rendered = serde_json::to_string(&p).expect("serializes");
        assert!(!rendered.contains("hunter2"), "credential leaked into the response: {rendered}");
    }

    #[test]
    fn already_provisioned_reports_no_steps_rather_than_an_empty_run() {
        let body = ProvisionResponse {
            outcome: Outcome::AlreadyProvisioned,
            reality_id: Uuid::nil(),
            shard_id: "s".into(),
            db_name: "d".into(),
            status: Some("active".into()),
            steps: None,
        };
        let json = serde_json::to_string(&body).expect("serializes");
        assert!(!json.contains("steps"), "an absent run must not appear as a run: {json}");
        assert!(json.contains("already_provisioned"), "{json}");
    }
}
