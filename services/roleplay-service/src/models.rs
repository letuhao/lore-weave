//! Wire + row models for scripts and the start-orchestration.
//!
//! `scenario` and `rubric` are kept as `serde_json::Value` so authored fields
//! round-trip losslessly through create/patch (the typed [`Scenario`] view is
//! used only to freeze the charter at `/start`). Identity is NEVER carried in a
//! request body — it comes from the JWT (`Extension<UserId>`).

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

fn default_genre() -> String {
    "roleplay".to_string()
}

/// A roleplay script row (System or Per-user).
#[derive(Debug, Serialize, sqlx::FromRow)]
pub struct Script {
    pub script_id: Uuid,
    pub owner_user_id: Option<Uuid>,
    pub tier: String,
    pub code: String,
    pub name: String,
    pub description: Option<String>,
    pub system_prompt: String,
    pub model_source: Option<String>,
    pub model_ref: Option<Uuid>,
    pub rubric: Option<serde_json::Value>,
    pub scenario: serde_json::Value,
    pub genre: String,
    pub book_id: Option<Uuid>,
    pub reality_id: Option<Uuid>,
    pub attachment_key: Option<String>,
    pub is_active: bool,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

/// Create a Per-user script. `tier`/`owner_user_id` are forced server-side
/// (tier='user', owner=the JWT caller) — never taken from the body (INV-T2).
#[derive(Debug, Deserialize)]
pub struct CreateScriptReq {
    pub code: String,
    pub name: String,
    #[serde(default)]
    pub description: Option<String>,
    pub system_prompt: String,
    #[serde(default)]
    pub model_source: Option<String>,
    #[serde(default)]
    pub model_ref: Option<Uuid>,
    #[serde(default)]
    pub rubric: Option<serde_json::Value>,
    #[serde(default)]
    pub scenario: serde_json::Value,
    #[serde(default = "default_genre")]
    pub genre: String,
}

/// Patch a Per-user script. Absent fields are left unchanged (COALESCE).
#[derive(Debug, Deserialize)]
pub struct PatchScriptReq {
    pub name: Option<String>,
    pub description: Option<String>,
    pub system_prompt: Option<String>,
    pub model_source: Option<String>,
    pub model_ref: Option<Uuid>,
    pub rubric: Option<serde_json::Value>,
    pub scenario: Option<serde_json::Value>,
    pub genre: Option<String>,
    pub is_active: Option<bool>,
}

/// Optional model override at `/start` (else the script's own model is used).
#[derive(Debug, Deserialize, Default)]
pub struct StartReq {
    #[serde(default)]
    pub model_source: Option<String>,
    #[serde(default)]
    pub model_ref: Option<Uuid>,
}

/// The `/start` response — the chat session id the FE opens in ChatView.
#[derive(Debug, Serialize)]
pub struct StartResp {
    pub session_id: Uuid,
}

/// Typed view of the script `scenario` JSON (spec §3 superset). Every field is
/// optional — a pasted scenario may be sparse. Used only to freeze the charter.
#[derive(Debug, Default, Deserialize)]
pub struct Scenario {
    #[serde(default)]
    pub premise: Option<String>,
    #[serde(default)]
    pub setting: Option<String>,
    #[serde(default)]
    pub ai_role: Option<String>,
    #[serde(default)]
    pub user_role: Option<String>,
    #[serde(default)]
    pub opening: Option<String>,
    #[serde(default)]
    pub cast: Vec<serde_json::Value>,
    #[serde(default)]
    pub beats: Vec<String>,
    #[serde(default)]
    pub phases: Vec<String>,
    #[serde(default)]
    pub tone: Option<String>,
    #[serde(default)]
    pub improv_freedom: Option<String>,
    #[serde(default)]
    pub time_budget_min: Option<i32>,
    #[serde(default)]
    pub language: Option<String>,
}
