//! L3.E/F integrity checker — the `replay-aggregate` keystone.
//!
//! Re-derives ONE projection row by replaying its owning event aggregate(s)
//! into a TEMP shadow of the target table, then emits the row's canonical
//! payload (`to_jsonb(t) - meta_keys`) so the Go integrity-checker can
//! byte-compare it against the live projection row. See
//! `docs/plans/2026-06-03-l3ef-integrity-checker.md`.
//!
//! ## Why a temp shadow
//!
//! The 073 [`crate::rebuild::writer::SqlxProjectionWriter`] is reused UNCHANGED:
//! it targets a projection table BY NAME (`INSERT INTO <table>` /
//! `jsonb_populate_record(NULL::<table>, …)`). `CREATE TEMP TABLE <table> (LIKE
//! public.<table> INCLUDING ALL)` puts a same-named table in `pg_temp`, which is
//! first in `search_path`, so the writer transparently writes to the temp copy —
//! the real projection table is never touched. This requires a **single
//! connection** (temp tables are connection-local), so the bin uses a
//! `max_connections(1)` pool.
//!
//! ## Why global-ordered, bounded, multi-aggregate
//!
//! Most rows derive from one aggregate, but `npc_session_memory_projection` is
//! built from BOTH `session.*` and `npc.memory_updated` events — so the bin
//! replays a LIST of aggregates, in global order (`recorded_at, event_id` — the
//! `events` table has no monotonic global sequence), up to the sampled row's
//! boundary event. The row's state at that boundary is what the live projection
//! row should equal.
//!
//! This module holds the PURE, DB-free pieces (SQL builders + identifier safety
//! + the output shape) so they are unit-testable without a Postgres. The bin
//! (`src/bin/replay-aggregate.rs`) does the IO.

use serde::Serialize;

use crate::rebuild::is_known_projection_table;

/// The VerificationMeta + integrity-HWM columns present on EVERY L3.A projection
/// table (`0006_projections`). Stripped from BOTH the replayed row and the live
/// row before comparison, since they are write-instant / verifier bookkeeping —
/// not projected state — and would otherwise always differ.
pub const META_KEYS: &[&str] = &[
    "event_id",
    "aggregate_version",
    "applied_at",
    "last_verified_event_version",
    "last_verified_at",
];

/// One aggregate to replay: its `events.aggregate_type` + `events.aggregate_id`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OwningAggregate {
    /// `events.aggregate_type` (e.g. `"pc"`, `"npc"`, `"session"`, `"world"`).
    pub aggregate_type: String,
    /// `events.aggregate_id` (TEXT in the events table).
    pub aggregate_id: String,
}

/// The bin's stdout contract (one JSON object). The Go `AggregateLoader` parses
/// this; field names are the wire contract.
#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct ReplayOutput {
    /// `true` when the replay produced a row at the requested PK.
    pub found: bool,
    /// Number of events replayed across all requested aggregates (≤ boundary).
    /// `0` ⇒ the aggregate(s) had no in-bound events (pruned / never existed /
    /// boundary missing) ⇒ the caller marks the sample SKIPPED, not drifted.
    pub events_replayed: u64,
    /// `"ok"` on a clean replay; `"error"` (with a non-empty [`Self::error`])
    /// when replay failed ⇒ caller marks SKIPPED, not drifted.
    pub status: String,
    /// The replayed row's canonical payload (`to_jsonb(t) - meta_keys`), or
    /// `null` when `found == false`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub payload: Option<serde_json::Value>,
    /// Populated only when `status == "error"`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

impl ReplayOutput {
    /// A `status:"error"` result (events=0, not found). The caller treats this as
    /// SKIPPED — a replay failure is not projection drift.
    pub fn error(msg: impl Into<String>) -> Self {
        Self {
            found: false,
            events_replayed: 0,
            status: "error".into(),
            payload: None,
            error: Some(msg.into()),
        }
    }
}

/// `CREATE TEMP TABLE <table> (LIKE public.<table> INCLUDING ALL)` for an
/// allowlisted projection table. `public.` is qualified so `LIKE` copies the
/// REAL table (not, recursively, the temp shadow being created). The temp name
/// shadows `public.<table>` in `pg_temp` (first in `search_path`), so the reused
/// writer's unqualified `<table>` references hit the temp copy.
///
/// NOTE: no `ON COMMIT DROP` — the writer commits per batch, so the temp must
/// survive across the replay's transactions (it is dropped when the connection /
/// process ends).
pub fn temp_shadow_ddl(table: &str) -> Result<String, String> {
    ensure_known_table(table)?;
    Ok(format!(
        "CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL)"
    ))
}

/// The bounded, global-ordered, multi-aggregate events query. Returns the SQL
/// for `num_aggregates` aggregates (each contributing a `(aggregate_type,
/// aggregate_id)` pair). Binds: `$1` reality_id, `$2` boundary_event_id (used
/// both to resolve the boundary `recorded_at` via a sub-select AND as the
/// tie-break in the row-comparison — so NO timestamp needs binding), then the
/// aggregate pairs `$3,$4 , $5,$6 , …`.
///
/// `(recorded_at, event_id) <= (boundary_recorded_at, boundary_event_id)` is a
/// Postgres row-value comparison; if the boundary event is missing the
/// sub-select yields NULL and the predicate matches nothing (0 events → SKIP).
pub fn events_query_sql(num_aggregates: usize) -> Result<String, String> {
    if num_aggregates == 0 {
        return Err("replay-aggregate: at least one aggregate is required".into());
    }
    // Aggregate pairs start at $3.
    let mut pairs = Vec::with_capacity(num_aggregates);
    for i in 0..num_aggregates {
        let t = 3 + i * 2;
        let id = t + 1;
        pairs.push(format!("(${t}, ${id})"));
    }
    let in_list = pairs.join(", ");
    Ok(format!(
        "SELECT event_id, event_type, event_version, aggregate_id, aggregate_type, \
                aggregate_version, reality_id, \
                to_char(occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS occurred_at, \
                to_char(recorded_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') AS recorded_at, \
                payload, metadata \
           FROM events \
          WHERE reality_id = $1 \
            AND (aggregate_type, aggregate_id) IN ({in_list}) \
            AND (recorded_at, event_id) <= ( \
                  (SELECT b.recorded_at FROM events b WHERE b.reality_id = $1 AND b.event_id = $2 LIMIT 1), \
                  $2 \
                ) \
          ORDER BY recorded_at, event_id"
    ))
}

/// `SELECT to_jsonb(t) - <meta keys> AS payload FROM <table> t WHERE <pk> LIMIT 1`.
///
/// `pk_columns` are the row's primary-key columns IN ORDER; each is matched
/// `t.<col>::text = $N` (binds start at `$1`, in column order). The `::text` cast
/// canonicalizes the PK value regardless of its real type (all L3.A pk columns
/// are `UUID` or `TEXT`), so the caller binds plain strings. Every column is
/// identifier-validated (the name is interpolated into SQL).
pub fn payload_select_sql(table: &str, pk_columns: &[&str]) -> Result<String, String> {
    ensure_known_table(table)?;
    if pk_columns.is_empty() {
        return Err("replay-aggregate: pk_columns must be non-empty".into());
    }
    let minus_meta = META_KEYS
        .iter()
        .map(|k| format!(" - '{k}'"))
        .collect::<String>();
    let mut preds = Vec::with_capacity(pk_columns.len());
    for (i, col) in pk_columns.iter().enumerate() {
        ensure_ident(col)?;
        preds.push(format!("t.{col}::text = ${}", i + 1));
    }
    let where_clause = preds.join(" AND ");
    Ok(format!(
        "SELECT to_jsonb(t){minus_meta} AS payload FROM {table} t WHERE {where_clause} LIMIT 1"
    ))
}

fn ensure_known_table(table: &str) -> Result<(), String> {
    if is_known_projection_table(table) {
        Ok(())
    } else {
        Err(format!(
            "replay-aggregate: unknown projection table {table:?} (not in the L3.A allowlist)"
        ))
    }
}

/// Reject anything that is not a lowercase snake_case SQL identifier. PK column
/// names come from a trusted per-table map, but they are interpolated into SQL,
/// so validate defensively (mirrors the rebuilder writer's `ensure_ident`).
fn ensure_ident(s: &str) -> Result<(), String> {
    let ok = !s.is_empty()
        && s.len() <= 63
        && s.bytes()
            .enumerate()
            .all(|(i, b)| b == b'_' || b.is_ascii_lowercase() || (i > 0 && b.is_ascii_digit()));
    if ok {
        Ok(())
    } else {
        Err(format!(
            "replay-aggregate: unsafe pk column identifier {s:?}"
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn temp_shadow_ddl_qualifies_public_and_validates_table() {
        let sql = temp_shadow_ddl("pc_projection").unwrap();
        assert_eq!(
            sql,
            "CREATE TEMP TABLE pc_projection (LIKE public.pc_projection INCLUDING ALL)"
        );
        assert!(temp_shadow_ddl("reality_registry").is_err());
        assert!(temp_shadow_ddl("pc_projection; DROP TABLE x").is_err());
    }

    #[test]
    fn events_query_binds_pairs_from_3_and_uses_event_id_twice() {
        let one = events_query_sql(1).unwrap();
        assert!(
            one.contains("(aggregate_type, aggregate_id) IN (($3, $4))"),
            "{one}"
        );
        // boundary uses $2 (the event_id) for BOTH the sub-select and the tie-break.
        assert!(one.contains("b.event_id = $2"), "{one}");
        assert!(one.contains("(recorded_at, event_id) <= ("), "{one}");
        assert!(one.contains("ORDER BY recorded_at, event_id"), "{one}");

        let two = events_query_sql(2).unwrap();
        assert!(two.contains("IN (($3, $4), ($5, $6))"), "{two}");

        assert!(events_query_sql(0).is_err());
    }

    #[test]
    fn payload_select_strips_all_meta_keys_and_casts_pk_to_text() {
        let sql = payload_select_sql("pc_inventory_projection", &["pc_id", "item_code"]).unwrap();
        for k in META_KEYS {
            assert!(
                sql.contains(&format!(" - '{k}'")),
                "missing meta strip {k}: {sql}"
            );
        }
        assert!(sql.contains("FROM pc_inventory_projection t"), "{sql}");
        assert!(sql.contains("t.pc_id::text = $1"), "{sql}");
        assert!(sql.contains("t.item_code::text = $2"), "{sql}");
        assert!(sql.trim_end().ends_with("LIMIT 1"), "{sql}");
    }

    #[test]
    fn payload_select_rejects_unknown_table_and_unsafe_pk() {
        assert!(payload_select_sql("not_a_table", &["pc_id"]).is_err());
        assert!(payload_select_sql("pc_projection", &[]).is_err());
        assert!(payload_select_sql("pc_projection", &["pc_id; DROP TABLE x"]).is_err());
        assert!(payload_select_sql("pc_projection", &["PcId"]).is_err()); // uppercase rejected
    }

    #[test]
    fn meta_keys_match_the_0006_verification_block() {
        // If 0006_projections adds/removes a VerificationMeta column, this list
        // (and the Go-side strip) MUST change in lockstep.
        assert_eq!(META_KEYS.len(), 5);
        assert!(META_KEYS.contains(&"event_id"));
        assert!(META_KEYS.contains(&"last_verified_at"));
    }

    #[test]
    fn replay_output_error_serializes_without_payload() {
        let out = ReplayOutput::error("boom");
        let j = serde_json::to_value(&out).unwrap();
        assert_eq!(j["status"], "error");
        assert_eq!(j["found"], false);
        assert_eq!(j["events_replayed"], 0);
        assert_eq!(j["error"], "boom");
        assert!(j.get("payload").is_none(), "payload omitted when None");
    }

    #[test]
    fn replay_output_found_serializes_payload() {
        let out = ReplayOutput {
            found: true,
            events_replayed: 3,
            status: "ok".into(),
            payload: Some(serde_json::json!({"name": "Aria"})),
            error: None,
        };
        let j = serde_json::to_value(&out).unwrap();
        assert_eq!(j["found"], true);
        assert_eq!(j["payload"]["name"], "Aria");
        assert!(j.get("error").is_none());
    }
}
