//! Q1 B2b — `RLS-A3` bindings in the meta DB instead of on disk.
//!
//! `ruleset-loader::binding` said, in its own doc comment:
//!
//! > *"Where it will eventually live: `reality_registry` in the meta DB … It is
//! > a file here because `commit-service`'s spine has no meta pool, and
//! > inventing that wiring to store two fields would be the larger change. The
//! > surface is `create` / `load`; moving it behind a table touches this file."*
//!
//! This is the move, with one correction: **not `reality_registry`**. That is
//! one row per reality, and the epoch history is the thing `QTY-A5`'s
//! never-reuse rule is recomputed over — a mutable column would destroy exactly
//! what it needs. The table is `reality_ruleset_binding`, one row per epoch,
//! append-only (`migrations/meta/033`), which closed `QTY-Q6`.
//!
//! ## Why the implementation is HERE and not in the loader
//!
//! `ruleset-loader` has three dependencies (`ruleset-core`, `serde`, `toml`) and
//! `crate-purity-gate` cares about what the tier can reach. Putting sqlx and
//! tokio there to store two fields would widen the whole game-logic tier's
//! dependency surface for one caller's benefit. `commit-service` is the host; it
//! already owns the pool, the runtime and the connection string.
//!
//! ## Every write goes through `MetaWrite`
//!
//! Not style — `I8`, and `scripts/meta-write-discipline-lint.sh` scans `crates/`
//! and `services/` for a literal `INSERT INTO reality_ruleset_binding` outside
//! `contracts/meta` and `crates/meta-rs`. There is no SQL in this file at all:
//! the statement is built by `meta-rs`'s `PgQueryBuilder`, so the data row, the
//! `meta_write_audit` row and the `meta_outbox` event are one transaction.

use std::sync::Arc;

use meta_rs::allowlist::Allowlist;
use meta_rs::audit::{AuditClock, AuditUuidGen};
use meta_rs::metawrite::{meta_write, Actor, ActorType, MetaWriteConfig};
use meta_rs::sqlx_pg::{bind_ruleset_intent, PgConnectionWriter, PgOutboxAppender, PgQueryBuilder};
use ruleset_core::RulesetDigest;
use ruleset_loader::{BindingError, BindingStore, RealityBinding};
use sqlx::PgPool;
use uuid::Uuid;

/// Host wall clock. The kernel never sees it — audit timestamps are the host's
/// job, the same split `spine`'s `now_rfc3339` already makes.
struct HostClock;
impl AuditClock for HostClock {
    fn now_unix_nanos(&self) -> i64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("clock after epoch")
            .as_nanos() as i64
    }
}

struct V4Uuid;
impl AuditUuidGen for V4Uuid {
    fn new_uuid(&self) -> Uuid {
        Uuid::new_v4()
    }
}

/// A [`BindingStore`] backed by `reality_ruleset_binding` in the meta DB.
pub struct PgBindingStore {
    pool: PgPool,
    allowlist: Arc<Allowlist>,
    actor_id: String,
}

impl PgBindingStore {
    /// `allowlist_path` is `contracts/meta/events_allowlist.yaml` — the polyglot
    /// SoT. Loaded once at construction rather than per write, and a failure to
    /// load is fatal here rather than degrading to "skip the check": the
    /// allowlist IS the defence-in-depth, and a store that quietly ran without
    /// one would write to any table an intent named.
    pub fn new(
        pool: PgPool,
        allowlist_path: &str,
        actor_id: impl Into<String>,
    ) -> Result<Self, String> {
        let allowlist = Allowlist::load(allowlist_path)
            .map_err(|e| format!("meta allowlist {allowlist_path}: {e}"))?;
        Ok(Self {
            pool,
            allowlist: Arc::new(allowlist),
            actor_id: actor_id.into(),
        })
    }

    fn actor(&self) -> Actor {
        Actor {
            // Reality creation has no human in the loop: it is the node acting
            // on a deployment's behalf, which is exactly `system` rather than
            // `owner` or `admin`.
            actor_type: ActorType::System,
            id: self.actor_id.clone(),
            svid: None,
        }
    }

    fn block<F: std::future::Future>(f: F) -> F::Output {
        tokio::task::block_in_place(|| tokio::runtime::Handle::current().block_on(f))
    }
}

/// `BindingError` has no database variant and should not grow one — it is the
/// loader's vocabulary, and the loader has no database. A backend failure is
/// reported as I/O, which is what it is from the caller's side.
fn io(msg: String) -> BindingError {
    BindingError::Io(std::io::Error::other(msg))
}

impl BindingStore for PgBindingStore {
    fn create(
        &self,
        reality_id: &str,
        digest: &RulesetDigest,
    ) -> Result<RealityBinding, BindingError> {
        // Parsed rather than passed through: `reality_id` is a UUID column, and
        // finding that out from a Postgres type error inside a transaction is
        // strictly worse than finding it out here.
        Uuid::parse_str(reality_id)
            .map_err(|_| io(format!("reality id is not a uuid: {reality_id}")))?;

        let epoch = 1u32;
        let mut conn = PgConnectionWriter::new(self.pool.clone())
            .map_err(|e| io(format!("meta connection: {e}")))?;
        let qb = PgQueryBuilder;
        let outbox = PgOutboxAppender;
        let clock = HostClock;
        let uuid = V4Uuid;
        let mut cfg = MetaWriteConfig {
            connection: &mut conn,
            allowlist: &self.allowlist,
            query_builder: &qb,
            outbox: Some(&outbox),
            clock: &clock,
            uuid_gen: &uuid,
        };
        let intent = bind_ruleset_intent(
            reality_id,
            epoch,
            &digest.to_hex(),
            "reality created",
            self.actor(),
        );

        match meta_write(&mut cfg, intent) {
            Ok(_) => Ok(RealityBinding {
                reality_id: reality_id.to_string(),
                epoch,
                digest: digest.to_hex(),
            }),
            Err(e) => {
                // "Already bound" arrives from the DATABASE, not from a
                // read-then-write in this process — migration 033's gapless
                // trigger refuses an epoch that is not `max + 1`, so a second
                // create is refused by the same statement that would have
                // performed it. The file store checks `path.exists()` first and
                // is therefore racy between two nodes; this one cannot be.
                //
                // Recognised by the trigger's own words rather than by SQLSTATE
                // because the refusal is a RAISE, not a constraint violation.
                let msg = format!("{e}");
                if msg.contains("must be epoch") || msg.contains("must be 1") {
                    let existing = self
                        .load(reality_id)
                        .ok()
                        .flatten()
                        .map(|b| format!("{} (epoch {})", b.digest, b.epoch))
                        .unwrap_or_else(|| "<unreadable>".into());
                    return Err(BindingError::AlreadyBound {
                        reality_id: reality_id.to_string(),
                        existing,
                    });
                }
                Err(io(format!("bind reality {reality_id}: {msg}")))
            }
        }
    }

    fn load(&self, reality_id: &str) -> Result<Option<RealityBinding>, BindingError> {
        let id = Uuid::parse_str(reality_id)
            .map_err(|_| io(format!("reality id is not a uuid: {reality_id}")))?;
        // ORDER BY epoch DESC LIMIT 1 — the CURRENT binding is the newest, and
        // the older rows are the history never-reuse is computed over. A load
        // that took `WHERE epoch = 1` would pin every reality to its creation
        // rules forever and an epoch switch would appear to do nothing.
        let row: Option<(i32, String)> = Self::block(
            sqlx::query_as(
                "SELECT epoch, ruleset_digest FROM reality_ruleset_binding \
                 WHERE reality_id = $1 ORDER BY epoch DESC LIMIT 1",
            )
            .bind(id)
            .fetch_optional(&self.pool),
        )
        .map_err(|e| io(format!("read binding for {reality_id}: {e}")))?;

        Ok(row.map(|(epoch, digest)| RealityBinding {
            reality_id: reality_id.to_string(),
            epoch: epoch as u32,
            digest,
        }))
    }
}
