//! Script CRUD with per-tier tenancy.
//!
//! Visibility = System (`owner_user_id IS NULL`) ∪ own (`owner_user_id = uid`).
//! Writes are owner-scoped: a System row or another user's row resolves to 404
//! (never an existence oracle). Create forces `tier='user'` + `owner = uid`.

use axum::Json;
use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::Extension;
use service_http::UserId;
use uuid::Uuid;

use crate::error::{Error, Result};
use crate::models::{CreateScriptReq, PatchScriptReq, Script};
use crate::state::AppState;

use super::SCRIPT_COLS;

/// `GET /v1/roleplay/scripts` — System ∪ own, merged by `code` (own shadows
/// System), active only, ordered by name.
pub async fn list(
    State(s): State<AppState>,
    Extension(UserId(uid)): Extension<UserId>,
) -> Result<Json<Vec<Script>>> {
    let sql = format!(
        "SELECT * FROM ( \
           SELECT DISTINCT ON (code) {SCRIPT_COLS} \
           FROM roleplay_scripts \
           WHERE (owner_user_id IS NULL OR owner_user_id = $1) AND is_active \
           ORDER BY code, owner_user_id NULLS LAST \
         ) t ORDER BY name"
    );
    let rows = sqlx::query_as::<_, Script>(&sql).bind(uid).fetch_all(&s.pool).await?;
    Ok(Json(rows))
}

/// `GET /v1/roleplay/scripts/{id}` — visible (System or own) else 404.
pub async fn get_one(
    State(s): State<AppState>,
    Extension(UserId(uid)): Extension<UserId>,
    Path(id): Path<Uuid>,
) -> Result<Json<Script>> {
    let sql = format!(
        "SELECT {SCRIPT_COLS} FROM roleplay_scripts \
         WHERE script_id = $1 AND (owner_user_id IS NULL OR owner_user_id = $2)"
    );
    let row = sqlx::query_as::<_, Script>(&sql).bind(id).bind(uid).fetch_optional(&s.pool).await?;
    row.map(Json).ok_or(Error::NotFound)
}

/// `POST /v1/roleplay/scripts` — create a Per-user script (tier + owner forced).
pub async fn create(
    State(s): State<AppState>,
    Extension(UserId(uid)): Extension<UserId>,
    Json(req): Json<CreateScriptReq>,
) -> Result<(StatusCode, Json<Script>)> {
    if req.code.trim().is_empty() || req.name.trim().is_empty() || req.system_prompt.trim().is_empty() {
        return Err(Error::BadRequest("code, name, and system_prompt are required".into()));
    }
    // `scenario` is optional in the API (OpenAPI default {}), but an omitted
    // field deserializes to JSON null — binding that to the NOT NULL `scenario`
    // column either violates the constraint or stores a `null` scalar instead of
    // the intended {}. Coerce to an empty object.
    let scenario = if req.scenario.is_null() {
        serde_json::json!({})
    } else {
        req.scenario
    };
    let sql = format!(
        "INSERT INTO roleplay_scripts \
           (owner_user_id, tier, code, name, description, system_prompt, \
            model_source, model_ref, rubric, scenario, genre) \
         VALUES ($1, 'user', $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10) \
         RETURNING {SCRIPT_COLS}"
    );
    let row = sqlx::query_as::<_, Script>(&sql)
        .bind(uid)
        .bind(req.code.trim())
        .bind(req.name.trim())
        .bind(req.description)
        .bind(req.system_prompt)
        .bind(req.model_source)
        .bind(req.model_ref)
        .bind(req.rubric)
        .bind(scenario)
        .bind(req.genre)
        .fetch_one(&s.pool)
        .await?;
    Ok((StatusCode::CREATED, Json(row)))
}

/// `PATCH /v1/roleplay/scripts/{id}` — own only (System/other → 404). Absent
/// fields unchanged (COALESCE).
pub async fn patch(
    State(s): State<AppState>,
    Extension(UserId(uid)): Extension<UserId>,
    Path(id): Path<Uuid>,
    Json(req): Json<PatchScriptReq>,
) -> Result<Json<Script>> {
    let sql = format!(
        "UPDATE roleplay_scripts SET \
           name = COALESCE($3, name), \
           description = COALESCE($4, description), \
           system_prompt = COALESCE($5, system_prompt), \
           model_source = COALESCE($6, model_source), \
           model_ref = COALESCE($7, model_ref), \
           rubric = COALESCE($8::jsonb, rubric), \
           scenario = COALESCE($9::jsonb, scenario), \
           genre = COALESCE($10, genre), \
           is_active = COALESCE($11, is_active), \
           updated_at = now() \
         WHERE script_id = $1 AND owner_user_id = $2 \
         RETURNING {SCRIPT_COLS}"
    );
    let row = sqlx::query_as::<_, Script>(&sql)
        .bind(id)
        .bind(uid)
        .bind(req.name)
        .bind(req.description)
        .bind(req.system_prompt)
        .bind(req.model_source)
        .bind(req.model_ref)
        .bind(req.rubric)
        .bind(req.scenario)
        .bind(req.genre)
        .bind(req.is_active)
        .fetch_optional(&s.pool)
        .await?;
    row.map(Json).ok_or(Error::NotFound)
}

/// `DELETE /v1/roleplay/scripts/{id}` — own only (System/other → 404). A script
/// still referenced by sessions → 409 (FK), via the error mapping.
pub async fn del(
    State(s): State<AppState>,
    Extension(UserId(uid)): Extension<UserId>,
    Path(id): Path<Uuid>,
) -> Result<StatusCode> {
    let res = sqlx::query("DELETE FROM roleplay_scripts WHERE script_id = $1 AND owner_user_id = $2")
        .bind(id)
        .bind(uid)
        .execute(&s.pool)
        .await?;
    if res.rows_affected() == 0 {
        return Err(Error::NotFound);
    }
    Ok(StatusCode::NO_CONTENT)
}
