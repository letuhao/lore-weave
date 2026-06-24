//! HTTP handlers. Identity always comes from `Extension<UserId>` (the JWT),
//! never from a request body (tenancy INV-T2).

pub mod scripts;
pub mod start;

/// The `roleplay_scripts` column list, in `Script` (FromRow) field order.
pub(crate) const SCRIPT_COLS: &str = "script_id, owner_user_id, tier, code, name, \
    description, system_prompt, model_source, model_ref, rubric, scenario, genre, \
    book_id, reality_id, attachment_key, is_active, created_at, updated_at";
