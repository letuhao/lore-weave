// Byte-identical to fixtures/dp_kernel/src/lib.rs on purpose. If these two
// files ever diverge, the differential stops isolating the marker and starts
// measuring whatever else changed.
use sqlx::PgPool;

pub fn takes(_p: &PgPool) {}
