// This crate IS the data plane -- event_store_pg.rs lives here. It holds raw
// clients by design, and 2F-2 is that DP-R3's literal wording would fire on it.
use sqlx::PgPool;

pub fn takes(_p: &PgPool) {}
