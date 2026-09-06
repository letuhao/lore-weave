//! `A4` — *"what is here"*, over the wire.
//!
//! [`crate::space_view::assemble`] was written for `SDF-Q15`'s measurement and
//! had no caller outside `tests/`. This is the caller.
//!
//! ## Why a POST for a read
//!
//! Every other route on this surface is a POST with a JSON body, and one of them
//! — `/internal/v1/actor-control/subject` — is explicitly *"the OWNER-SCOPED
//! read"*. The reason given there applies here unchanged: the request names the
//! thing it asks about, so on a public edge it would be an oracle. This surface
//! is `Gate::Internal` for that reason and not for symmetry.
//!
//! ## `SDF-A26` — the reader chooses a BUDGET, never a set
//!
//! The request carries caps, not a field list. Which layers render is the layer
//! owner's declaration (`layer_registry.projection`), never the caller's, so
//! there is deliberately no way to ask for "just the occupants".
//!
//! ## AND A BUDGET OVER THE CEILING IS REFUSED, NOT CLAMPED
//!
//! Silently clamping would answer a question the caller did not ask and label it
//! as the answer to the one they did — the same shape as a truncated view that
//! does not say it is truncated, which `SpaceView::truncated` exists to prevent
//! one layer down. A caller who asks for 10 000 occupants gets a `400` naming
//! the ceiling.

use axum::Json;
use axum::extract::State;
use axum::extract::rejection::JsonRejection;
use axum::http::StatusCode;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::actor_control_flow::{bind_reality, open_reality_pool};
use crate::server::state::AppState;
use crate::space_view::{self, SpaceView, ViewBudget, ViewError, Whereabouts};
use service_http::ProblemDetails;

/// The largest budget this surface will accept, per section.
///
/// **Binary capacity, not a world limit.** It bounds what one request may cost
/// this process; it says nothing about how many doors a room may have. The two
/// are different numbers with different audiences, and a world that wants a
/// 40-door plaza is not asking for a bigger request.
///
/// `SDF-Q15` measured `ViewBudget::MEASURED` (12 / 24) at 511 B over 41 nodes.
/// This is roughly eight times that and is a refusal threshold rather than a
/// target — nothing is expected to reach it.
pub const MAX_SECTION: usize = 200;

/// `POST /internal/v1/space/view`.
#[derive(Debug, Clone, Deserialize)]
pub struct SpaceViewRequest {
    pub reality_id: Uuid,
    /// The `channels.id` to look at.
    pub node: i64,
    /// How many portals out of this node to include. Defaults to the measured cap.
    #[serde(default)]
    pub portal_ring: Option<usize>,
    /// How many occupants to include. Defaults to the measured cap.
    #[serde(default)]
    pub occupants: Option<usize>,
}

#[derive(Debug, Clone, Serialize)]
pub struct SpaceViewResponse {
    pub reality_id: Uuid,
    #[serde(flatten)]
    pub view: SpaceView,
}

pub async fn view(
    State(state): State<AppState>,
    body: Result<Json<SpaceViewRequest>, JsonRejection>,
) -> Result<(StatusCode, Json<SpaceViewResponse>), ProblemDetails> {
    let Json(req) = body.map_err(|e| {
        ProblemDetails::new(e.status(), "invalid-body", "Invalid request body", e.body_text())
    })?;

    let budget = ViewBudget {
        portal_ring: req.portal_ring.unwrap_or(ViewBudget::MEASURED.portal_ring),
        occupants: req.occupants.unwrap_or(ViewBudget::MEASURED.occupants),
    };
    for (name, asked) in [("portal_ring", budget.portal_ring), ("occupants", budget.occupants)] {
        if asked > MAX_SECTION {
            return Err(ProblemDetails::bad_request(format!(
                "{name}={asked} exceeds the per-section ceiling of {MAX_SECTION}; \
                 refused rather than clamped, because an answer to a smaller \
                 question labelled as the answer to yours is worse than no answer"
            )));
        }
    }

    // `bind_reality` and `open_reality_pool` live in `actor_control_flow` and are
    // not actor-specific -- they bind a reality and open its database. Called
    // where they are rather than moved, because a rename touching every caller is
    // not this row's work and would bury it.
    let reality = bind_reality(&state.meta, &state.effects.meta_allowlist, req.reality_id)
        .await
        .map_err(crate::server::handlers::actor_control::to_problem)?;
    let pool = open_reality_pool(&state.meta, &state.effects, &reality)
        .await
        .map_err(crate::server::handlers::actor_control::to_problem)?;

    let view = space_view::assemble(&pool, &reality, req.node, budget).await;
    pool.close().await;

    match view {
        Ok(view) => Ok((StatusCode::OK, Json(SpaceViewResponse { reality_id: req.reality_id, view }))),
        // A node that is not in this reality is a statement about the WORLD and
        // the caller can act on it, so it is a 404 and not a 500.
        Err(ViewError::NotFound(n)) => Err(ProblemDetails::new(
            StatusCode::NOT_FOUND,
            "node-not-found",
            "No such node",
            format!("node {n} does not exist in reality {}", req.reality_id),
        )),
        Err(ViewError::Db(e)) => Err(ProblemDetails::new(
            StatusCode::INTERNAL_SERVER_ERROR,
            "database-error",
            "Could not assemble the view",
            e.to_string(),
        )),
    }
}

/// `POST /internal/v1/space/where-is`.
#[derive(Debug, Clone, Deserialize)]
pub struct WhereIsRequest {
    pub reality_id: Uuid,
    /// The island entity id, as `actors.entity_id` allocates it.
    pub entity_id: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct WhereIsResponse {
    pub reality_id: Uuid,
    /// Three distinct facts, never flattened to a nullable. See [`Whereabouts`].
    pub whereabouts: Whereabouts,
}

/// Answer *"where is entity N"*.
///
/// **`Unbound` is a 200, not a 404**, for the same reason
/// `/actor-control/subject` answers `self: null` with a 200: the resource being
/// described is the BINDING RELATION, and *"this entity is nowhere"* is a fact
/// about it rather than its absence. It is also the ordinary state -- until a
/// world exists to be sited in, every actor is unbound.
pub async fn where_is(
    State(state): State<AppState>,
    body: Result<Json<WhereIsRequest>, JsonRejection>,
) -> Result<(StatusCode, Json<WhereIsResponse>), ProblemDetails> {
    let Json(req) = body.map_err(|e| {
        ProblemDetails::new(e.status(), "invalid-body", "Invalid request body", e.body_text())
    })?;

    let reality = bind_reality(&state.meta, &state.effects.meta_allowlist, req.reality_id)
        .await
        .map_err(crate::server::handlers::actor_control::to_problem)?;
    let pool = open_reality_pool(&state.meta, &state.effects, &reality)
        .await
        .map_err(crate::server::handlers::actor_control::to_problem)?;

    let found = space_view::where_is(&pool, &reality, req.entity_id).await;
    pool.close().await;

    match found {
        Ok(whereabouts) => Ok((
            StatusCode::OK,
            Json(WhereIsResponse { reality_id: req.reality_id, whereabouts }),
        )),
        // A binding pointing at a channel with no `map_layout` row. `0025`'s
        // foreign key guarantees the CHANNEL exists, not that it is on the map.
        Err(ViewError::NotFound(n)) => Err(ProblemDetails::new(
            StatusCode::INTERNAL_SERVER_ERROR,
            "node-not-on-the-map",
            "The entity is bound to a channel that has no map_layout row",
            format!("channel {n} in reality {} is not on the map", req.reality_id),
        )),
        Err(ViewError::Db(e)) => Err(ProblemDetails::new(
            StatusCode::INTERNAL_SERVER_ERROR,
            "database-error",
            "Could not resolve the entity's whereabouts",
            e.to_string(),
        )),
    }
}
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_ceiling_is_well_clear_of_the_measured_budget() {
        // A ceiling below what the service itself ships as a default would refuse
        // its own defaults -- which is the shape of ceiling that gets raised
        // blindly the first time it fires, and then means nothing.
        assert!(MAX_SECTION > ViewBudget::MEASURED.portal_ring * 4);
        assert!(MAX_SECTION > ViewBudget::MEASURED.occupants * 4);
    }

    #[test]
    fn an_absent_budget_falls_back_to_the_measured_one() {
        // Absent must mean "the measured caps", not "unbounded". A `None` that
        // fell through to `usize::MAX` would make the ceiling check the only
        // thing standing between a caller and the whole table.
        let req: SpaceViewRequest = serde_json::from_str(
            r#"{"reality_id":"00000000-0000-0000-0000-000000000001","node":1}"#,
        )
        .expect("parses");
        assert_eq!(req.portal_ring, None);
        assert_eq!(req.occupants, None);
        let budget = ViewBudget {
            portal_ring: req.portal_ring.unwrap_or(ViewBudget::MEASURED.portal_ring),
            occupants: req.occupants.unwrap_or(ViewBudget::MEASURED.occupants),
        };
        assert_eq!(budget.portal_ring, ViewBudget::MEASURED.portal_ring);
        assert_eq!(budget.occupants, ViewBudget::MEASURED.occupants);
    }
}
