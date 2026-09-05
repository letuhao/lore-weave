// A feature crate reaching the kernel directly. The lint MUST fire here.
use sqlx::PgPool;

pub fn takes(_p: &PgPool) {}
