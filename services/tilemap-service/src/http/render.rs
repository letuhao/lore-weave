//! POST /internal/v1/tilemaps/render — the only endpoint today.
//!
//! Stateless: the request body carries the full `TilemapTemplate`; the
//! service combines it with channel + tier + grid + seed to call
//! [`crate::engine::place_tilemap`] (CPU-bound, sync — wrapped in
//! `spawn_blocking` to keep the tokio reactor responsive).
//!
//! Errors map per spec §3.4 — see [`super::error::ProblemDetails`].

use axum::Json;
use axum::extract::{FromRequest, Request, State, rejection::JsonRejection};
use serde::Deserialize;

use crate::engine::place_tilemap;
use crate::seed::TilemapSeed;
use crate::types::{ChannelId, ChannelTier, GridSize};
use crate::types::template::TilemapTemplate;
use crate::types::tilemap::TilemapView;

use super::auth::AppState;
use super::error::ProblemDetails;

/// Maximum tile_count we accept. 65_536 = 256² = the spec-documented
/// Continent default. Anything larger likely indicates a misconfigured
/// client or an attempted memory-exhaustion DoS and is rejected with
/// 413 before `place_tilemap` allocates the grid.
pub const MAX_GRID_TILES: usize = 65_536;

/// Maximum zones per template. Existing fixtures cap at ~10; 256 is a
/// comfortable upper bound that future authors can hit without surprise.
pub const MAX_ZONES: usize = 256;

/// Body-size limit for the render endpoint (applied as an axum layer in
/// `router.rs`). 1 MiB easily fits a maximal `TilemapTemplate` JSON while
/// stopping multi-MB body floods from reaching the deserializer.
pub const MAX_BODY_BYTES: usize = 1024 * 1024;

/// MED-2 fix from /review-impl: a thin wrapper around `axum::Json<T>` that
/// converts every `JsonRejection` variant into a `ProblemDetails` so the
/// wire promise ("every error is RFC 7807 problem+json") holds for axum
/// framework rejections too (oversized body, wrong Content-Type, syntax
/// errors, …).
#[derive(Debug)]
pub struct JsonProblem<T>(pub T);

impl<T, S> FromRequest<S> for JsonProblem<T>
where
    T: serde::de::DeserializeOwned,
    S: Send + Sync,
{
    type Rejection = ProblemDetails;

    async fn from_request(req: Request, state: &S) -> Result<Self, Self::Rejection> {
        match Json::<T>::from_request(req, state).await {
            Ok(Json(value)) => Ok(Self(value)),
            Err(rej) => Err(json_rejection_to_problem(rej)),
        }
    }
}

fn json_rejection_to_problem(rej: JsonRejection) -> ProblemDetails {
    use axum::http::StatusCode;
    let detail = rej.body_text();
    match rej.status() {
        StatusCode::PAYLOAD_TOO_LARGE => ProblemDetails::request_too_large(detail),
        StatusCode::UNSUPPORTED_MEDIA_TYPE => {
            let mut p = ProblemDetails::bad_request(detail);
            p.status = StatusCode::UNSUPPORTED_MEDIA_TYPE.as_u16();
            p
        }
        _ => ProblemDetails::bad_request(detail),
    }
}

/// Wire shape for the POST body. All fields required.
///
/// The serde defaults of nested types preserve the additive-field contract
/// — a template that predates `world_zone` still deserializes, with the
/// field falling back to `None`.
#[derive(Debug, Deserialize)]
pub struct RenderRequest {
    pub template: TilemapTemplate,
    pub channel_id: ChannelId,
    pub tier: ChannelTier,
    pub grid_size: GridSize,
    pub seed: u64,
}

/// `POST /internal/v1/tilemaps/render` handler.
///
/// The compute is CPU-bound; we hand it to `spawn_blocking` so other
/// tokio tasks (the HTTP listener, health checks, …) keep running.
pub async fn render(
    State(_state): State<AppState>,
    JsonProblem(req): JsonProblem<RenderRequest>,
) -> Result<Json<TilemapView>, ProblemDetails> {
    let RenderRequest { template, channel_id, tier, grid_size, seed } = req;

    // MED-1 from /review-impl: reject oversized requests BEFORE
    // spawn_blocking allocates the grid. Internal Bearer auth limits the
    // attack surface, but a single misconfigured client must not be able
    // to OOM the service.
    let tiles = grid_size.tile_count();
    if tiles > MAX_GRID_TILES {
        tracing::warn!(width = grid_size.width, height = grid_size.height, tiles, "rejecting oversized grid");
        return Err(ProblemDetails::request_too_large(format!(
            "grid_size {}×{} = {} tiles exceeds maximum {}",
            grid_size.width, grid_size.height, tiles, MAX_GRID_TILES
        )));
    }
    if template.zones.len() > MAX_ZONES {
        tracing::warn!(zones = template.zones.len(), "rejecting oversized template");
        return Err(ProblemDetails::request_too_large(format!(
            "template.zones.len() = {} exceeds maximum {}",
            template.zones.len(),
            MAX_ZONES
        )));
    }

    tracing::debug!(
        template_id = %template.template_id.0,
        zones = template.zones.len(),
        tiles,
        seed,
        "render request accepted"
    );

    let view = tokio::task::spawn_blocking(move || {
        place_tilemap(&template, channel_id, tier, grid_size, TilemapSeed(seed))
    })
    .await
    .map_err(|err| {
        // JoinError = panic inside the blocking task. Surfaces as 500.
        ProblemDetails::internal(format!("background task failed: {err}"))
    })??;
    Ok(Json(view))
}
