//! `A4` — *"give THIS reality a world"*, for a reality that already exists.
//!
//! ## Why this route had to exist before `A4` could finish
//!
//! [`crate::world_seed::seed_world`] had exactly one production caller:
//! `provisioner_live.rs:632`, the `seed_world_structure` step. That step runs
//! **at provision time and only then**. Every reality on this shard was
//! provisioned before the step existed, so for all ten of them the producer was
//! unreachable — not missing, not deferred, *unreachable*, which reads exactly
//! like reachable until someone tries.
//!
//! That left one way to give a running reality a world: hand-written `INSERT`s,
//! which is the thing `I-3` refuses for migrations and which the demo script was
//! already doing under a comment explaining that it was not the seeder path.
//!
//! ## It is the SAME function, not a second implementation
//!
//! This handler validates nothing and writes nothing itself. It binds the
//! reality, opens its pool, and calls `seed_world` — the same call the
//! provisioner makes, so `PF_001` §5, `SPG-A3`'s containment matrix and
//! `DP-Ch1`'s depth are enforced once, in one place, for both callers. A second
//! implementation here would be a second set of rules to drift.
//!
//! ## Idempotent, and it says so in the report rather than in a comment
//!
//! `seed_world` is `ON CONFLICT DO NOTHING` throughout and returns counts of
//! what it actually wrote. A re-seed answers `200` with three zeroes, which is
//! the honest answer — *"nothing to do"* — and is distinguishable by the caller
//! from *"five nodes created"*. `world_seed_live` proves that re-run arm.
//!
//! ## A rejection is a 400 and a database failure is a 500
//!
//! [`SeedError`] already separates the two for exactly this reason: one is the
//! operator's to fix and retrying will refuse again, the other is retryable and
//! not the caller's fault. Collapsing them here would throw that away at the one
//! boundary where a human reads the result.

use axum::Json;
use axum::extract::State;
use axum::extract::rejection::JsonRejection;
use axum::http::StatusCode;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::actor_control_flow::{bind_reality, open_reality_pool};
use crate::server::state::AppState;
use crate::world_seed::{self, NodeDecl, SeedError, SeedReport};
use service_http::ProblemDetails;

/// The largest declaration this surface will accept.
///
/// **Binary capacity, not a world limit** — the same distinction `MAX_SECTION`
/// draws one file over. It bounds what one request may cost this process; a
/// world larger than this is not wrong, it is just not something to push
/// through a single HTTP call. `contracts/world/demo_v1.json` is five nodes.
pub const MAX_NODES: usize = 2000;

/// `POST /internal/v1/world/seed`.
#[derive(Debug, Clone, Deserialize)]
pub struct SeedWorldRequest {
    /// The reality to seed. It must already exist and be bindable.
    pub reality_id: Uuid,
    /// The authored declaration, as `contracts/world/*.json` spells it.
    ///
    /// **No default.** `ProvisionRequest.world` defaults to empty because empty
    /// means *"this provision does not seed"*; here an empty body would mean
    /// *"seed nothing"*, which is a request nobody makes on purpose and which
    /// would answer `200` with three zeroes — indistinguishable from a re-seed.
    pub world: Vec<NodeDecl>,
}

/// What the seed wrote. Three zeroes is the idempotent re-seed, not a failure.
#[derive(Debug, Clone, Serialize)]
pub struct SeedWorldResponse {
    /// Echoed back so a log line carries the subject, not just the counts.
    pub reality_id: Uuid,
    /// `channels_written` / `layouts_written` / `places_written`, flattened.
    #[serde(flatten)]
    pub report: SeedReport,
}

/// `POST /internal/v1/world/seed` — seed an existing reality's world structure.
pub async fn seed_world(
    State(state): State<AppState>,
    body: Result<Json<SeedWorldRequest>, JsonRejection>,
) -> Result<(StatusCode, Json<SeedWorldResponse>), ProblemDetails> {
    let Json(req) = body.map_err(|e| {
        ProblemDetails::new(e.status(), "invalid-body", "Invalid request body", e.body_text())
    })?;

    if req.world.is_empty() {
        return Err(ProblemDetails::bad_request(
            "world is empty; a seed with nothing to seed would answer 200 with three \
             zeroes, which is indistinguishable from a successful re-seed",
        ));
    }
    if req.world.len() > MAX_NODES {
        return Err(ProblemDetails::bad_request(format!(
            "world declares {} nodes, over this surface's ceiling of {MAX_NODES}; \
             refused rather than truncated",
            req.world.len()
        )));
    }

    let reality = bind_reality(&state.meta, &state.effects.meta_allowlist, req.reality_id)
        .await
        .map_err(crate::server::handlers::actor_control::to_problem)?;
    let pool = open_reality_pool(&state.meta, &state.effects, &reality)
        .await
        .map_err(crate::server::handlers::actor_control::to_problem)?;

    let seeded = world_seed::seed_world(&pool, req.reality_id, &req.world).await;
    pool.close().await;

    match seeded {
        Ok(report) => Ok((
            StatusCode::OK,
            Json(SeedWorldResponse { reality_id: req.reality_id, report }),
        )),
        // The operator's to fix. `rule_id` is carried because it names the clause
        // that refused, which is what makes the refusal actionable rather than
        // merely negative.
        Err(SeedError::Rejected(r)) => Err(ProblemDetails::new(
            StatusCode::BAD_REQUEST,
            "world-rejected",
            "The world declaration was refused",
            format!("{} ({r:?})", r.rule_id()),
        )),
        Err(SeedError::Db(e)) => Err(ProblemDetails::new(
            StatusCode::INTERNAL_SERVER_ERROR,
            "database-error",
            "Could not seed the world",
            e.to_string(),
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn an_absent_world_does_not_parse_as_an_empty_one() {
        // `#[serde(default)]` here would turn "I forgot the field" into "seed
        // nothing", answered 200. That is the shape `ProvisionRequest.world`
        // wants and this surface does not, and the difference is only visible
        // if the field is genuinely required.
        let err = serde_json::from_str::<SeedWorldRequest>(
            r#"{"reality_id":"00000000-0000-0000-0000-000000000001"}"#,
        )
        .expect_err("a missing `world` must not parse");
        assert!(format!("{err}").contains("world"), "got {err}");
    }

    #[test]
    fn the_ceiling_is_well_clear_of_the_authored_declaration() {
        // A ceiling that the repo's own declaration approaches is one that gets
        // raised blindly the first time it fires. `demo_v1.json` is five nodes.
        let raw = std::fs::read_to_string(
            std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../../contracts/world/demo_v1.json"),
        )
        .expect("the authored declaration is the fixture");
        let decls: Vec<NodeDecl> = serde_json::from_str(&raw).expect("parses");
        assert!(!decls.is_empty(), "an empty fixture would make this vacuous");
        assert!(MAX_NODES > decls.len() * 100);
    }
}
