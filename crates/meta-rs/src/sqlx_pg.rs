//! Q1 B2b — the concrete sqlx/Postgres adapter for [`crate::metawrite`].
//!
//! This crate is deliberately driver-agnostic (*"concrete sqlx adapters:
//! caller-supplied"*), and that was right as a deferral and wrong as a
//! permanent answer: the first two callers would have written the same
//! `QueryBuilder` twice, and a `MetaWrite` adapter is precisely the code where
//! two nearly-identical copies is how one of them ends up subtly wrong. It is
//! behind the `sqlx-pg` feature so a caller that does not want sqlx does not
//! get it.
//!
//! ## The typing problem, and why the SQL looks like this
//!
//! [`TransactionExecutor::exec`] hands over `&[serde_json::Value]` — the
//! polyglot intent shape, which carries **no column types**. A JSON string is
//! just a string, and Postgres will not accept a TEXT parameter for a `uuid`
//! column: `column "reality_id" is of type uuid but expression is of type text`.
//! The Go side does not hit this because pgx sends `any` values with an
//! unspecified type OID and lets the server infer; sqlx always sends a concrete
//! OID, so the inference we need has to be asked for explicitly.
//!
//! Three ways out, and the two that were rejected:
//!
//! * **Guess from the JSON shape** — bind a UUID-looking string as `uuid`.
//!   Silently wrong for a TEXT column that happens to hold a UUID, which is a
//!   bug that only appears against real data.
//! * **Read `information_schema.columns`** — correct, but a per-table cache and
//!   a second source of truth for something the database already knows.
//! * **Ask the table.** `jsonb_populate_record(NULL::<table>, $1::jsonb)`
//!   returns a record typed by **the table's own row type**, so every field is
//!   converted by Postgres to that column's type. No cache, no heuristic, and a
//!   column type change cannot drift out from under it.
//!
//! So every statement this builder emits takes **jsonb parameters only**, and
//! `exec` binds every parameter the same way. The column list stays explicit —
//! `INSERT INTO t (a, b) SELECT a, b FROM jsonb_populate_record(...)` rather
//! than `SELECT *` — because `SELECT *` would supply NULL for every column the
//! caller omitted and defeat `DEFAULT now()`.
//!
//! ## Blocking, and the runtime flavour it refuses
//!
//! `TransactionExecutor` is **synchronous** and sqlx is **asynchronous**. The
//! bridge is `block_in_place` + `Handle::block_on`, which works only on a
//! multi-thread runtime — on a current-thread runtime `block_in_place`
//! **panics**. A panic deep inside a write is a terrible way to learn about a
//! configuration mistake, so [`PgConnectionWriter::new`] checks the flavour and
//! returns an error instead. See `refuses_a_current_thread_runtime`.
//!
//! This is acceptable *here* because meta writes are cold: reality creation and
//! epoch switches, not the step path. It would not be acceptable on a hot path,
//! and that is a reason to keep meta writes off one.

use std::sync::{Arc, Mutex};

use serde_json::Value;
use sqlx::postgres::PgPool;
use sqlx::{Postgres, Transaction};
use tokio::runtime::{Handle, RuntimeFlavor};

use crate::audit::{MetaWriteAuditRow, OutboxAppender, OutboxEvent};
use crate::errors::MetaError;
use crate::metawrite::{
    ConnectionWriter, MetaWriteIntent, MetaWriteOp, QueryBuilder, TransactionExecutor, ValueMap,
};

/// A Postgres identifier, quoted and with embedded quotes doubled.
///
/// Every identifier reaching this function comes from an allowlisted table's
/// intent, so it is not attacker-controlled — but "not attacker-controlled
/// today" is a property of the callers, and the callers change. Quoting costs
/// nothing.
fn quote_ident(raw: &str) -> String {
    format!("\"{}\"", raw.replace('"', "\"\""))
}

fn idents(cols: &[&String]) -> String {
    cols.iter()
        .map(|c| quote_ident(c))
        .collect::<Vec<_>>()
        .join(", ")
}

/// `a, b, c` qualified to a record alias — the projection out of
/// `jsonb_populate_record`.
fn idents_from(cols: &[&String], alias: &str) -> String {
    cols.iter()
        .map(|c| format!("{alias}.{}", quote_ident(c)))
        .collect::<Vec<_>>()
        .join(", ")
}

fn as_json_object(m: &ValueMap) -> Value {
    Value::Object(m.iter().map(|(k, v)| (k.clone(), v.clone())).collect())
}

/// Builds Postgres SQL whose parameters are **all jsonb**, typed by the target
/// table's own row type. Mirrors `contracts/meta/query_builder.go` in effect,
/// not in text — the Go builder can emit one placeholder per column because pgx
/// defers typing to the server.
#[derive(Debug, Clone, Copy, Default)]
pub struct PgQueryBuilder;

impl PgQueryBuilder {
    fn merged_insert_values(intent: &MetaWriteIntent) -> ValueMap {
        let mut merged = intent.pk.clone();
        for (k, v) in &intent.new_values {
            merged.insert(k.clone(), v.clone());
        }
        merged
    }
}

impl QueryBuilder for PgQueryBuilder {
    fn build_insert(&self, intent: &MetaWriteIntent) -> Result<(String, Vec<Value>), MetaError> {
        let merged = Self::merged_insert_values(intent);
        if merged.is_empty() {
            return Err(MetaError::BadIntent("build_insert needs values".into()));
        }
        let cols: Vec<&String> = merged.keys().collect();
        let table = quote_ident(&intent.table);
        let q = format!(
            "INSERT INTO {table} ({}) SELECT {} FROM jsonb_populate_record(NULL::{table}, $1::jsonb) AS r",
            idents(&cols),
            idents_from(&cols, "r"),
        );
        Ok((q, vec![as_json_object(&merged)]))
    }

    fn build_update(&self, intent: &MetaWriteIntent) -> Result<(String, Vec<Value>), MetaError> {
        if intent.new_values.is_empty() {
            return Err(MetaError::BadIntent("build_update needs new_values".into()));
        }
        if intent.pk.is_empty() {
            return Err(MetaError::BadIntent("build_update needs pk".into()));
        }
        let table = quote_ident(&intent.table);
        let set = intent
            .new_values
            .keys()
            .map(|c| format!("{} = nv.{}", quote_ident(c), quote_ident(c)))
            .collect::<Vec<_>>()
            .join(", ");

        // THE PK AND THE CAS GUARD GET SEPARATE RECORDS, and the first draft's
        // "share one record so the statement needs two params rather than three"
        // was a silent wrong-row write.
        //
        // Merging them meant `key.insert(col, cas_value)` OVERWROTE the primary
        // key whenever a column appeared in both `pk` and `expected_before`.
        // Measured on `pk={reality_id: A}, expected_before={reality_id: B}`:
        //
        //   WHERE t."reality_id" = k."reality_id" AND t."reality_id" = k."reality_id"
        //   k = {"epoch":1,"reality_id":"BBBB"}      <- A is GONE
        //
        // …so the UPDATE targeted whatever row held B. The Go builder binds the
        // two as separate parameters and emits `pk = $2 AND pk = $3`, which
        // matches nothing and surfaces as a CAS conflict — the safe outcome, and
        // the behaviour this must mirror. Saving one parameter is not worth a
        // divergence in which row gets written.
        //
        // A CAS column whose expected value is NULL becomes `IS NULL`: `col =
        // NULL` is never true in SQL, so rendering it as equality would turn
        // "only while unset" into "never".
        let mut where_parts: Vec<String> = intent
            .pk
            .keys()
            .map(|c| format!("t.{} = k.{}", quote_ident(c), quote_ident(c)))
            .collect();
        let mut cas = ValueMap::new();
        for (c, v) in &intent.expected_before {
            if v.is_null() {
                where_parts.push(format!("t.{} IS NULL", quote_ident(c)));
            } else {
                where_parts.push(format!("t.{} = cas.{}", quote_ident(c), quote_ident(c)));
                cas.insert(c.clone(), v.clone());
            }
        }

        let q = format!(
            "UPDATE {table} AS t SET {set} \
             FROM jsonb_populate_record(NULL::{table}, $1::jsonb) AS nv, \
                  jsonb_populate_record(NULL::{table}, $2::jsonb) AS k, \
                  jsonb_populate_record(NULL::{table}, $3::jsonb) AS cas \
             WHERE {}",
            where_parts.join(" AND "),
        );
        Ok((
            q,
            vec![
                as_json_object(&intent.new_values),
                as_json_object(&intent.pk),
                as_json_object(&cas),
            ],
        ))
    }

    fn build_delete(&self, intent: &MetaWriteIntent) -> Result<(String, Vec<Value>), MetaError> {
        if intent.pk.is_empty() {
            return Err(MetaError::BadIntent("build_delete needs pk".into()));
        }
        let table = quote_ident(&intent.table);
        let where_parts = intent
            .pk
            .keys()
            .map(|c| format!("t.{} = k.{}", quote_ident(c), quote_ident(c)))
            .collect::<Vec<_>>()
            .join(" AND ");
        let q = format!(
            "DELETE FROM {table} AS t \
             USING jsonb_populate_record(NULL::{table}, $1::jsonb) AS k WHERE {where_parts}"
        );
        Ok((q, vec![as_json_object(&intent.pk)]))
    }

    fn build_audit_insert(
        &self,
        row: &MetaWriteAuditRow,
    ) -> Result<(String, Vec<Value>), MetaError> {
        // `scrub_version` is absent from the Rust audit row and the column is
        // `NOT NULL DEFAULT ''` (migration 027), so omitting it from the column
        // list is correct rather than lossy. `created_at` is GENERATED from
        // `created_at_nanos` and must NOT be listed.
        let rec = serde_json::json!({
            "audit_id": row.audit_id.to_string(),
            "table_name": row.table_name,
            "operation": row.operation.as_str(),
            "row_pk": as_json_object(&row.row_pk),
            "before_values": as_json_object(&row.before_values),
            "after_values": as_json_object(&row.after_values),
            "actor_type": row.actor_type.as_str(),
            "actor_id": row.actor_id.clone(),
            "reason": row.reason,
            "request_context": {
                "trace_id": row.request_context.trace_id,
                "request_id": row.request_context.request_id,
                "source_service": row.request_context.source_service,
            },
            "created_at_nanos": row.created_at_nanos,
        });
        let q = "INSERT INTO meta_write_audit \
                 (audit_id, table_name, operation, row_pk, before_values, after_values, \
                  actor_type, actor_id, reason, request_context, created_at_nanos) \
                 SELECT r.audit_id, r.table_name, r.operation, r.row_pk, r.before_values, \
                        r.after_values, r.actor_type, r.actor_id, r.reason, r.request_context, \
                        r.created_at_nanos \
                 FROM jsonb_populate_record(NULL::meta_write_audit, $1::jsonb) AS r"
            .to_string();
        Ok((q, vec![rec]))
    }
}

/// Appends to `meta_outbox` inside the caller's transaction — the same TX as
/// the data row and the audit row, which is the whole point of an outbox.
///
/// **Stamps `xreality_topic`, and the first version did not.** The Go appender
/// (`sdks/go/metaoutbox`) has always taken it from the allowlist so the relay
/// knows to ALSO bridge the event onto a cross-reality Redis topic. Omitting it
/// fails nothing anywhere: the row lands, the relay forwards it to the normal
/// stream, and the cross-reality consumer simply stops hearing about events it
/// used to receive.
///
/// There is no `Default`, deliberately. A zero-argument constructor is exactly
/// how the omission would come back — it would compile, run, and stamp NULL.
#[derive(Debug, Clone)]
pub struct PgOutboxAppender {
    xreality: std::collections::HashMap<String, String>,
}

impl PgOutboxAppender {
    /// Build from the allowlist, which is the only place topics are declared.
    pub fn new(allowlist: &crate::allowlist::Allowlist) -> Self {
        Self {
            xreality: allowlist.xreality_topics().clone(),
        }
    }
}

impl OutboxAppender<PgTx> for PgOutboxAppender {
    fn append(&self, tx: &mut PgTx, event: OutboxEvent) -> Result<(), MetaError> {
        let rec = serde_json::json!({
            "event_id": event.event_id.to_string(),
            "event_name": event.event_name,
            "aggregate_id": event.aggregate_id,
            "payload": event.payload,
            "xreality_topic": self.xreality.get(&event.event_name),
            "recorded_at_nanos": event.recorded_at_nanos,
        });
        let q = "INSERT INTO meta_outbox \
                 (event_id, event_name, aggregate_id, payload, xreality_topic, \
                  recorded_at_nanos) \
                 SELECT r.event_id, r.event_name, r.aggregate_id, r.payload, \
                        r.xreality_topic, r.recorded_at_nanos \
                 FROM jsonb_populate_record(NULL::meta_outbox, $1::jsonb) AS r";
        tx.exec(q, &[rec]).map(|_| ())
    }
}

/// The live transaction handle. Shared with the commit/rollback closures via an
/// `Arc<Mutex<Option<_>>>` because `Transaction::commit` **consumes** the
/// transaction while [`ConnectionWriter::begin_tx`] hands the handle and the
/// finalizers back as separate values. The `Option` is what "exactly once"
/// looks like: whoever takes it first gets it, and a second finalizer call
/// finds `None` and says so rather than silently succeeding.
pub struct PgTx {
    inner: Arc<Mutex<Option<Transaction<'static, Postgres>>>>,
    handle: Handle,
}

fn lock_poisoned(what: &str) -> MetaError {
    MetaError::BadIntent(format!(
        "meta transaction mutex poisoned during {what}: a previous write panicked \
         while holding it, so this transaction's state is unknown and it must not \
         be committed"
    ))
}

impl TransactionExecutor for PgTx {
    fn exec(&mut self, query: &str, params: &[Value]) -> Result<i64, MetaError> {
        let inner = Arc::clone(&self.inner);
        let handle = self.handle.clone();
        tokio::task::block_in_place(move || {
            let mut guard = inner.lock().map_err(|_| lock_poisoned("exec"))?;
            let tx = guard.as_mut().ok_or_else(|| {
                MetaError::BadIntent(
                    "meta transaction already finalized: a statement was executed after \
                     commit or rollback"
                        .into(),
                )
            })?;
            let mut q = sqlx::query(query);
            for p in params {
                q = q.bind(sqlx::types::Json(p.clone()));
            }
            handle
                .block_on(q.execute(&mut **tx))
                .map(|r| r.rows_affected() as i64)
                .map_err(|e| MetaError::BadIntent(format!("exec failed: {e}")))
        })
    }
}

/// Opens transactions on a [`PgPool`].
pub struct PgConnectionWriter {
    pool: PgPool,
    handle: Handle,
}

impl PgConnectionWriter {
    /// Wrap a pool. **Refuses a current-thread runtime**: the executor bridges
    /// sync to async with `block_in_place`, which panics there. Failing at
    /// construction turns a panic in the middle of a write into an error before
    /// one starts.
    pub fn new(pool: PgPool) -> Result<Self, MetaError> {
        let handle = Handle::try_current().map_err(|_| {
            MetaError::ConfigInvalid(
                "PgConnectionWriter must be constructed inside a tokio runtime — it bridges \
                 the synchronous MetaWrite traits onto async sqlx"
                    .into(),
            )
        })?;
        if handle.runtime_flavor() != RuntimeFlavor::MultiThread {
            return Err(MetaError::ConfigInvalid(
                "PgConnectionWriter requires a MULTI-THREAD tokio runtime: MetaWrite's \
                 TransactionExecutor is synchronous, so the adapter blocks with \
                 block_in_place, which panics on a current-thread runtime. Use \
                 #[tokio::main] (multi_thread is its default) or \
                 Builder::new_multi_thread()."
                    .into(),
            ))
        }
        Ok(Self { pool, handle })
    }
}

impl ConnectionWriter for PgConnectionWriter {
    type Tx = PgTx;

    fn begin_tx(
        &mut self,
    ) -> Result<
        (
            Self::Tx,
            Box<dyn FnOnce() -> Result<(), MetaError> + Send>,
            Box<dyn FnOnce() -> Result<(), MetaError> + Send>,
        ),
        MetaError,
    > {
        let pool = self.pool.clone();
        let handle = self.handle.clone();
        let tx = tokio::task::block_in_place(|| handle.block_on(pool.begin()))
            .map_err(|e| MetaError::BadIntent(format!("begin: {e}")))?;
        let inner = Arc::new(Mutex::new(Some(tx)));

        let commit_inner = Arc::clone(&inner);
        let commit_handle = self.handle.clone();
        let commit = Box::new(move || -> Result<(), MetaError> {
            let tx = commit_inner
                .lock()
                .map_err(|_| lock_poisoned("commit"))?
                .take()
                .ok_or_else(|| {
                    MetaError::BadIntent("meta transaction already finalized: commit".into())
                })?;
            tokio::task::block_in_place(|| commit_handle.block_on(tx.commit()))
                .map_err(|e| MetaError::BadIntent(format!("commit: {e}")))
        });

        let rollback_inner = Arc::clone(&inner);
        let rollback_handle = self.handle.clone();
        let rollback = Box::new(move || -> Result<(), MetaError> {
            // Rollback is idempotent on purpose. `meta_write` drops the
            // rollback box on the error path (the transaction unwinds when the
            // connection returns to the pool), so this being callable twice —
            // or not at all — must not be a second failure on top of the first.
            let taken = rollback_inner
                .lock()
                .map_err(|_| lock_poisoned("rollback"))?
                .take();
            match taken {
                Some(tx) => tokio::task::block_in_place(|| rollback_handle.block_on(tx.rollback()))
                    .map_err(|e| MetaError::BadIntent(format!("rollback: {e}"))),
                None => Ok(()),
            }
        });

        Ok((
            PgTx {
                inner,
                handle: self.handle.clone(),
            },
            commit,
            rollback,
        ))
    }
}

/// The one operation this adapter exists for, spelled out so callers do not
/// hand-roll an intent: bind `reality_id` to `digest` at `epoch`.
///
/// It is a constructor, not a writer — it returns the intent for
/// [`crate::metawrite::meta_write`] to execute. A helper that also performed the
/// write would put a second `INSERT INTO reality_ruleset_binding` in the tree
/// and `meta-write-discipline-lint` would be right to fail it.
pub fn bind_ruleset_intent(
    reality_id: &str,
    epoch: u32,
    digest_hex: &str,
    reason: &str,
    actor: crate::metawrite::Actor,
) -> MetaWriteIntent {
    let mut pk = ValueMap::new();
    pk.insert("reality_id".into(), Value::String(reality_id.to_string()));
    pk.insert("epoch".into(), Value::from(epoch));
    let mut new_values = ValueMap::new();
    new_values.insert(
        "ruleset_digest".into(),
        Value::String(digest_hex.to_string()),
    );
    new_values.insert("reason".into(), Value::String(reason.to_string()));
    MetaWriteIntent {
        table: "reality_ruleset_binding".into(),
        operation: MetaWriteOp::Insert,
        pk,
        expected_before: ValueMap::new(),
        new_values,
        actor,
        reason: reason.to_string(),
        request_context: Default::default(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::metawrite::{Actor, ActorType};

    fn intent() -> MetaWriteIntent {
        bind_ruleset_intent(
            "11111111-1111-4111-8111-111111111111",
            1,
            &"a".repeat(64),
            "reality created",
            Actor {
                actor_type: ActorType::System,
                id: "commit-service".into(),
                svid: None,
            },
        )
    }

    /// The whole reason for `jsonb_populate_record`: **no column is named twice
    /// with a type beside it.** If this ever becomes a `$1, $2, $3` insert, the
    /// adapter has started guessing types and this test is where it shows.
    #[test]
    fn every_parameter_is_jsonb_and_typed_by_the_table() {
        let (q, args) = PgQueryBuilder.build_insert(&intent()).unwrap();
        assert!(
            q.contains("jsonb_populate_record(NULL::\"reality_ruleset_binding\", $1::jsonb)"),
            "{q}"
        );
        assert_eq!(args.len(), 1, "one jsonb record, not one param per column");
        assert!(args[0].is_object());
        assert!(
            !q.contains("$2"),
            "a second placeholder means a column is being bound directly, which is \
             where the uuid-vs-text mistake enters: {q}"
        );
    }

    /// `SELECT *` would supply NULL for every unlisted column and defeat
    /// `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`.
    #[test]
    fn the_column_list_is_explicit_so_defaults_survive() {
        let (q, _) = PgQueryBuilder.build_insert(&intent()).unwrap();
        assert!(!q.contains("SELECT *"), "{q}");
        for col in ["reality_id", "epoch", "ruleset_digest", "reason"] {
            assert!(q.contains(&format!("\"{col}\"")), "missing {col} in {q}");
        }
        assert!(
            !q.contains("created_at"),
            "created_at must be left to its DEFAULT: {q}"
        );
    }

    /// `col = NULL` is never true, so a CAS on an as-yet-unset column has to
    /// render as `IS NULL` or "only while unset" silently becomes "never".
    #[test]
    fn a_null_cas_expectation_becomes_is_null_and_binds_nothing() {
        let mut i = intent();
        i.operation = MetaWriteOp::Update;
        i.expected_before
            .insert("close_reason".into(), Value::Null);
        i.expected_before
            .insert("ruleset_digest".into(), Value::String("x".into()));
        let (q, args) = PgQueryBuilder.build_update(&i).unwrap();
        assert!(q.contains("t.\"close_reason\" IS NULL"), "{q}");
        assert!(q.contains("t.\"ruleset_digest\" = cas.\"ruleset_digest\""), "{q}");
        let key = args[2].as_object().unwrap();
        assert!(
            !key.contains_key("close_reason"),
            "an IS NULL predicate binds no value; carrying one would make \
             jsonb_populate_record produce a NULL field that matches nothing"
        );
        assert!(key.contains_key("ruleset_digest"));
    }


    /// **A column in BOTH `pk` and `expected_before` must not overwrite the
    /// primary key.** The first implementation merged them into one record to
    /// save a parameter, and the CAS value won: the UPDATE silently targeted a
    /// DIFFERENT ROW. Go binds them separately (`pk = $2 AND pk = $3`), matches
    /// nothing, and reports a CAS conflict — the safe outcome this mirrors.
    #[test]
    fn a_cas_on_a_pk_column_does_not_retarget_the_row() {
        let mut i = intent();
        i.operation = MetaWriteOp::Update;
        let pk_value = i.pk["reality_id"].clone();
        i.expected_before
            .insert("reality_id".into(), Value::String("a-different-reality".into()));

        let (q, args) = PgQueryBuilder.build_update(&i).unwrap();
        assert_eq!(
            args[1].as_object().unwrap()["reality_id"], pk_value,
            "the PK record must still carry the PK's OWN value"
        );
        assert_eq!(
            args[2].as_object().unwrap()["reality_id"],
            Value::String("a-different-reality".into()),
            "…and the CAS record carries the expected-before value, separately"
        );
        // Two DIFFERENT records referenced, so the predicate can be unsatisfiable
        // rather than quietly true of the wrong row.
        assert!(q.contains("t.\"reality_id\" = k.\"reality_id\""), "{q}");
        assert!(q.contains("t.\"reality_id\" = cas.\"reality_id\""), "{q}");
    }

    #[test]
    fn an_identifier_with_a_quote_in_it_cannot_escape() {
        let mut i = intent();
        i.table = "evil\"; DROP TABLE x; --".into();
        let (q, _) = PgQueryBuilder.build_insert(&i).unwrap();
        // The embedded quote must be DOUBLED, which is what keeps the whole
        // payload inside one identifier instead of closing it early.
        assert!(q.contains("\"evil\"\"; DROP TABLE x; --\""), "{q}");
        // …and the tell that it did NOT close early: `evil";` — a single quote
        // followed by the semicolon — never appears. Asserting the absence of
        // the payload text itself would be the wrong check: the payload is
        // SUPPOSED to be there, inertly, as part of a quoted name.
        assert!(!q.contains("evil\";"), "identifier closed early: {q}");
    }

    #[test]
    fn the_audit_insert_omits_the_generated_and_defaulted_columns() {
        use crate::audit::MetaWriteAuditRow;
        let row = MetaWriteAuditRow {
            audit_id: uuid::Uuid::nil(),
            table_name: "reality_ruleset_binding".into(),
            operation: MetaWriteOp::Insert,
            row_pk: ValueMap::new(),
            before_values: ValueMap::new(),
            after_values: ValueMap::new(),
            actor_type: ActorType::System,
            actor_id: "commit-service".into(),
            reason: String::new(),
            request_context: Default::default(),
            created_at_nanos: 1_800_000_000_000_000_000,
        };
        let (q, args) = PgQueryBuilder.build_audit_insert(&row).unwrap();
        assert!(
            !q.contains("scrub_version"),
            "the Rust audit row has no scrub_version and the column defaults to '' \
             (migration 027) — listing it would insert NULL into a NOT NULL column: {q}"
        );
        assert!(
            !q.split("FROM").next().unwrap().contains(" created_at,"),
            "created_at is GENERATED from created_at_nanos and cannot be inserted: {q}"
        );
        assert_eq!(args.len(), 1);
    }

    /// A current-thread runtime is where `block_in_place` panics, so the
    /// constructor has to refuse it. Without this test the guard is a comment.
    #[test]
    fn refuses_a_current_thread_runtime() {
        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap();
        let err = rt.block_on(async {
            let pool = sqlx::postgres::PgPoolOptions::new()
                .connect_lazy("postgres://never:used@127.0.0.1:1/none")
                .unwrap();
            PgConnectionWriter::new(pool).err()
        });
        let err = err.expect("a current-thread runtime must be refused, not panicked on");
        let msg = format!("{err}");
        assert!(msg.contains("MULTI-THREAD"), "{msg}");
    }

    /// …and the negative control: the same construction on the runtime the
    /// spine actually uses must SUCCEED, or the test above would pass for an
    /// adapter that refused every runtime.
    #[test]
    fn accepts_a_multi_thread_runtime() {
        let rt = tokio::runtime::Builder::new_multi_thread()
            .worker_threads(1)
            .enable_all()
            .build()
            .unwrap();
        rt.block_on(async {
            let pool = sqlx::postgres::PgPoolOptions::new()
                .connect_lazy("postgres://never:used@127.0.0.1:1/none")
                .unwrap();
            assert!(PgConnectionWriter::new(pool).is_ok());
        });
    }
}
