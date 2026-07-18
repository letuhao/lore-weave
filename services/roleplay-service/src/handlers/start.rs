//! Start-orchestration — `POST /v1/roleplay/scripts/{id}/start`.
//!
//! roleplay-service is the goal authority: freeze the charter from the script,
//! create the chat-service session carrying the frozen seed FIRST (EC-3 — the
//! chat session owns the id; if the local write then fails, M3 still anchors
//! from the seed and a reconcile can backfill `rp_memory`), then record
//! `rp_sessions` + `rp_memory` in one tx. Returns the chat `session_id` the FE
//! opens in ChatView.

use axum::Json;
use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::Extension;
use serde_json::{Value, json};
use service_http::{HasInternalToken, UserId};
use uuid::Uuid;

use crate::charter;
use crate::error::{Error, Result};
use crate::models::{Script, StartReq, StartResp};
use crate::state::AppState;

use super::SCRIPT_COLS;

pub async fn start(
    State(s): State<AppState>,
    Extension(UserId(uid)): Extension<UserId>,
    Path(id): Path<Uuid>,
    body: Option<Json<StartReq>>,
) -> Result<(StatusCode, Json<StartResp>)> {
    let req = body.map(|Json(b)| b).unwrap_or_default();

    // 1. Load the script the caller may see (System or own), active only.
    let sql = format!(
        "SELECT {SCRIPT_COLS} FROM roleplay_scripts \
         WHERE script_id = $1 AND (owner_user_id IS NULL OR owner_user_id = $2) AND is_active"
    );
    let script = sqlx::query_as::<_, Script>(&sql)
        .bind(id)
        .bind(uid)
        .fetch_optional(&s.pool)
        .await?
        .ok_or(Error::NotFound)?;

    // 2. Resolve the model: request override > script default; both absent → 400.
    let model_source = req.model_source.or_else(|| script.model_source.clone());
    let model_ref = req.model_ref.or(script.model_ref);
    let (Some(model_source), Some(model_ref)) = (model_source, model_ref) else {
        return Err(Error::BadRequest(
            "no model: the script has no default model and none was provided".into(),
        ));
    };

    // 3. Freeze the charter from the scenario (+ optional rubric sidecar).
    let (charter, seed) =
        charter::freeze(&script.scenario, script.rubric.as_ref(), &script.name, &script.genre);

    // 4. Create the chat session FIRST (it owns the session id) — EC-3.
    let payload = json!({
        "owner_user_id": uid.to_string(),
        "title": script.name,
        "model_source": model_source,
        "model_ref": model_ref.to_string(),
        "system_prompt": script.system_prompt,
        "working_memory_seed": seed,
    });
    let resp = s
        .http
        .post(format!("{}/internal/chat/sessions", s.chat_url))
        .header(service_http::auth::INTERNAL_TOKEN_HEADER, s.internal_token())
        .json(&payload)
        .send()
        .await
        .map_err(|e| Error::Upstream(format!("chat-service unreachable: {e}")))?;
    if !resp.status().is_success() {
        return Err(Error::Upstream(format!("chat-service returned status {}", resp.status())));
    }
    let created: Value = resp
        .json()
        .await
        .map_err(|e| Error::Upstream(format!("invalid chat-service response: {e}")))?;
    let session_id = created
        .get("session_id")
        .and_then(Value::as_str)
        .and_then(|v| Uuid::parse_str(v).ok())
        .ok_or_else(|| Error::Upstream("chat-service did not return a session_id".into()))?;

    // 5. Record the session + the durable charter (spec §10.6: the rp_memory row
    //    is the read-back-validated actor-memory store). The chat session ALREADY
    //    exists and carries the seed, so M3 anchoring works regardless of this
    //    write (EC-3) — therefore a failure here must NOT fail the request (that
    //    would make the user retry and create a DUPLICATE chat session, orphaning
    //    this one). Best-effort + idempotent (ON CONFLICT) so a backfill is safe
    //    to repeat; on persistent failure we log a structured, recoverable error
    //    and still return the usable session.
    if let Err(e) = persist_session(&s.pool, session_id, script.script_id, uid, &charter).await {
        tracing::error!(
            %session_id, owner_user_id = %uid, script_id = %script.script_id,
            error = %e, charter = %charter,
            "rp_memory persist failed after chat-session create — session is usable \
             (anchored from the seed); backfill rp_memory for this session_id"
        );
    }

    Ok((StatusCode::CREATED, Json(StartResp { session_id })))
}

/// Persist `rp_sessions` + `rp_memory` for a started session, in one tx.
/// Idempotent: `ON CONFLICT (session_id) DO NOTHING` makes a retry/backfill a
/// no-op, so this can be safely re-invoked to repair a session whose first write
/// failed (the chat session + seed always exist by this point — EC-3).
async fn persist_session(
    pool: &sqlx::PgPool,
    session_id: Uuid,
    script_id: Uuid,
    owner_user_id: Uuid,
    charter: &Value,
) -> Result<()> {
    let mut tx = pool.begin().await?;
    sqlx::query(
        "INSERT INTO rp_sessions (session_id, script_id, owner_user_id) \
         VALUES ($1, $2, $3) ON CONFLICT (session_id) DO NOTHING",
    )
    .bind(session_id)
    .bind(script_id)
    .bind(owner_user_id)
    .execute(&mut *tx)
    .await?;
    sqlx::query(
        "INSERT INTO rp_memory (session_id, charter) VALUES ($1, $2::jsonb) \
         ON CONFLICT (session_id) DO NOTHING",
    )
    .bind(session_id)
    .bind(charter)
    .execute(&mut *tx)
    .await?;
    tx.commit().await?;
    Ok(())
}
