//! `provision` — the reality-creation WORKER.
//!
//! W3. This is the binary the Go `admin reality provision` command execs, in
//! exactly the shape `admin-cli` already uses for the `rebuilder` worker
//! (`SubprocessRebuildInvoker`): **secrets arrive by env** so they never reach
//! the process table, **identifiers arrive as flags**, **stdout is one JSON
//! object** and nothing else, human diagnostics go to stderr, and the exit code
//! is the verdict.
//!
//! ## Why this exists when `provision-drill` already provisions
//!
//! The drill is a drill (RUN-STATE §0.5). Two things make it unfit as the
//! product path, and both are fixed here:
//!
//! 1. **It defaults its credentials** to a scale-rig role (`foundation`), so it
//!    silently targets the wrong stack instead of refusing. This worker has **no
//!    default for any DSN or secret** — a missing one is exit 2, by name. Per
//!    CLAUDE.md: services fail to start when a secret is absent.
//! 2. **It fabricates the capacity snapshot** (`used: 0, total: 100`), so the
//!    one decision provisioning exists to make — *which shard, and is there
//!    room* — is not actually made. This worker routes through
//!    [`capacity_glue::place_reality`], which reads `shard_utilization` +
//!    `reality_registry` live and holds a per-shard advisory lock across the
//!    pick→register critical section. That closes the TOCTOU the glue was
//!    written for and that nothing on the real path had ever exercised.
//!
//! ## Modes
//!
//! `--dry-run` reads live capacity, picks the shard, and reports what a real run
//! WOULD do. It takes no lock and **writes nothing** — no registry row, no
//! `CREATE DATABASE`. R13 §12L.5 requires an operator see the predicted effect
//! of a destructive-ish action before committing to it.
//!
//! Without `--dry-run` the full 11-step `provision_reality` runs, pinned to the
//! shard chosen under the lock.
//!
//! ## Exit codes (same convention as the sibling drills)
//!
//! - `0` — provisioned (or dry-run completed)
//! - `1` — provisioning failed; stdout JSON still carries what is known
//! - `2` — setup/config error (missing env, unreachable DB): nothing was attempted

use std::process::ExitCode;
use std::sync::{Arc, Mutex};

use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use uuid::Uuid;

use world_service::capacity_glue::{live_snapshot, place_reality};
use world_service::capacity_planner::{CapacityPlanner, CapacityThresholds, ShardCapacity};
use world_service::provisioner::{ProvisionRequest, Provisioner};
use world_service::provisioner_live::{BridgeClient, LiveEffects};

/// Env vars carrying a DSN or a secret. **No defaults** — see module docs.
const REQUIRED_ENV: [&str; 6] = [
    "PROVISION_META_DSN",
    "PROVISION_SHARD_ADMIN_DSN",
    "PROVISION_BRIDGE_URL",
    "PROVISION_BRIDGE_TOKEN",
    "PROVISION_SHARD_HOSTPORT",
    "PROVISION_PG_USER",
];

#[tokio::main]
async fn main() -> ExitCode {
    let args = match Args::parse(std::env::args().skip(1)) {
        Ok(a) => a,
        Err(e) => return setup_err(&e),
    };
    let cfg = match Config::from_env() {
        Ok(c) => c,
        Err(e) => return setup_err(&e),
    };
    match run(&args, &cfg).await {
        Ok(code) => code,
        Err(e) => setup_err(&e),
    }
}

// ─── args ────────────────────────────────────────────────────────────────────

struct Args {
    reality_id: Uuid,
    locale: String,
    deploy_cohort: u8,
    reason: String,
    dry_run: bool,
    /// W6 — owning user; absent means the platform owns the reality.
    owner_user_id: Option<Uuid>,
}

impl Args {
    /// Minimal `--flag value` parser. No clap: this crate does not depend on it,
    /// and the sibling workers (`rebuilder`) parse the same way, so the admin
    /// framework sees one consistent worker CLI.
    fn parse(argv: impl Iterator<Item = String>) -> Result<Self, String> {
        let mut reality_id: Option<Uuid> = None;
        let mut locale = "en".to_string();
        let mut deploy_cohort: u8 = 0;
        let mut reason: Option<String> = None;
        let mut dry_run = false;
        let mut owner_user_id: Option<Uuid> = None;

        let argv: Vec<String> = argv.collect();
        let mut i = 0;
        while i < argv.len() {
            let flag = argv[i].as_str();
            // Value-less flag first, so it does not consume the next token.
            if flag == "--dry-run" {
                dry_run = true;
                i += 1;
                continue;
            }
            let val = argv.get(i + 1).ok_or_else(|| format!("{flag} requires a value"))?;
            match flag {
                "--reality-id" => {
                    reality_id = Some(
                        Uuid::parse_str(val).map_err(|e| format!("--reality-id: {e}"))?,
                    );
                }
                "--locale" => locale = val.clone(),
                "--deploy-cohort" => {
                    deploy_cohort =
                        val.parse().map_err(|e| format!("--deploy-cohort: {e}"))?;
                }
                "--reason" => reason = Some(val.clone()),
                "--owner-user-id" => {
                    let oid = Uuid::parse_str(val)
                        .map_err(|e| format!("--owner-user-id: {e}"))?;
                    // The nil UUID is not an owner. Accepting it produced
                    // ('user', 00000000-...) in reality_registry: a reality
                    // owned by a user that cannot exist, which satisfies every
                    // CHECK on the table. Refused rather than treated as
                    // absent -- an operator who typed an owner meant one.
                    if oid.is_nil() {
                        return Err("--owner-user-id must not be the nil UUID \
                                    (omit the flag for a platform-owned reality)"
                            .to_string());
                    }
                    owner_user_id = Some(oid);
                }
                other => return Err(format!("unknown flag {other}")),
            }
            i += 2;
        }

        // reality_id is caller-generated so the admin audit row and the registry
        // row name the SAME uuid (provisioner.rs:54). A worker-generated id
        // would leave the audit trail pointing at nothing on failure.
        let reality_id = reality_id.ok_or("--reality-id is required")?;
        let reason = reason.ok_or("--reason is required")?;
        Ok(Args { reality_id, locale, deploy_cohort, reason, dry_run, owner_user_id })
    }
}

// ─── config ──────────────────────────────────────────────────────────────────

struct Config {
    meta_dsn: String,
    shard_admin_dsn: String,
    bridge_url: String,
    bridge_token: String,
    shard_hostport: String,
    pg_user: String,
    pg_pass: String,
    sql_dir: String,
}

impl Config {
    /// Fail-closed: every entry of [`REQUIRED_ENV`] must be present and
    /// non-empty. Reports ALL missing names at once — an operator fixing env
    /// one round-trip at a time is the failure mode this avoids.
    fn from_env() -> Result<Self, String> {
        let missing: Vec<&str> = REQUIRED_ENV
            .iter()
            .copied()
            .filter(|k| std::env::var(k).map(|v| v.trim().is_empty()).unwrap_or(true))
            .collect();
        if !missing.is_empty() {
            return Err(format!(
                "missing required env: {} (this worker has NO credential defaults — \
                 a default would silently target the wrong stack)",
                missing.join(", ")
            ));
        }
        let get = |k: &str| std::env::var(k).unwrap_or_default();
        Ok(Config {
            meta_dsn: get("PROVISION_META_DSN"),
            shard_admin_dsn: get("PROVISION_SHARD_ADMIN_DSN"),
            bridge_url: get("PROVISION_BRIDGE_URL"),
            bridge_token: get("PROVISION_BRIDGE_TOKEN"),
            shard_hostport: get("PROVISION_SHARD_HOSTPORT"),
            pg_user: get("PROVISION_PG_USER"),
            // The password MAY legitimately be empty (peer/trust auth, or a
            // .pgpass), so it is not in REQUIRED_ENV — but it is still read
            // only from env, never a literal.
            pg_pass: std::env::var("PROVISION_PG_PASSWORD").unwrap_or_default(),
            sql_dir: std::env::var("PROVISION_SQL_DIR")
                .unwrap_or_else(|_| "contracts/migrations/per_reality".to_string()),
        })
    }
}

// ─── run ─────────────────────────────────────────────────────────────────────

async fn run(args: &Args, cfg: &Config) -> Result<ExitCode, String> {
    let meta = connect_meta(&cfg.meta_dsn).await?;
    let planner = CapacityPlanner::new(CapacityThresholds::default());

    if args.dry_run {
        return dry_run(args, &meta, &planner).await;
    }
    provision(args, cfg, &meta, planner).await
}

/// Read-only preview: live capacity + the shard a real run would choose.
/// Writes nothing, locks nothing.
async fn dry_run(
    args: &Args,
    meta: &PgPool,
    planner: &CapacityPlanner,
) -> Result<ExitCode, String> {
    let snap = live_snapshot(meta).await.map_err(|e| format!("capacity snapshot: {e}"))?;
    let picked = match planner.pick_shard(&snap) {
        Ok(p) => p,
        Err(e) => {
            println!(
                "{}",
                json_obj(&[
                    ("mode", jstr("dry-run")),
                    ("reality_id", jstr(&args.reality_id.to_string())),
                    ("would_provision", "false".into()),
                    ("error", jstr(&e.to_string())),
                    ("shards", jarr(&snap.iter().map(shard_json).collect::<Vec<_>>())),
                ])
            );
            eprintln!("FAIL: no shard could be chosen: {e}");
            return Ok(ExitCode::from(1));
        }
    };
    println!(
        "{}",
        json_obj(&[
            ("mode", jstr("dry-run")),
            ("reality_id", jstr(&args.reality_id.to_string())),
            ("would_provision", "true".into()),
            // Same key as the real run's output so the Go side parses ONE shape.
            ("shard", jstr(picked.shard_id.as_str())),
            ("db_name", jstr(&db_name_preview(args.reality_id))),
            ("locale", jstr(&args.locale)),
            ("deploy_cohort", args.deploy_cohort.to_string()),
            ("shards", jarr(&snap.iter().map(shard_json).collect::<Vec<_>>())),
        ])
    );
    eprintln!(
        "DRY-RUN: would place {} on {} ({}/{} slots used). Nothing was written.",
        args.reality_id,
        picked.shard_id.as_str(),
        picked.used_realities,
        picked.total_realities
    );
    Ok(ExitCode::SUCCESS)
}

/// An existing `reality_registry` row for this reality, if any.
///
/// This read is what makes a RETRY safe, and it closes a split-brain that the
/// first version of this worker created.
///
/// The bridge's register endpoint is idempotent by `reality_id` and
/// **deliberately does not diff the payload** — its own doc says so, and
/// justifies it with *"the single V1 caller (the provisioner) always retries
/// the same intent, so this is safe"* (`bridge.go:47`). That was true of
/// `provision-drill`, which hardcoded its shard. It stopped being true the
/// moment this worker started choosing a shard from LIVE capacity, because a
/// second run sees different counts and can pick a different shard:
///
///   run 1 dies after step 3 → registry says shard A, `status=provisioning`
///   run 2 re-picks → B → register returns 200 `already_registered` (ignored)
///                      → CREATE DATABASE + 15 migrations land on **B**
///                      → transitions succeed (the row IS in `provisioning`)
///
/// leaving the registry naming A, the database living on B, and the command
/// printing a confident success. Every consumer resolves its DSN from
/// `db_host`, so the reality is unreachable.
///
/// So: if a row exists, its shard is authoritative and placement is skipped
/// entirely — the slot was claimed by the first run and re-claiming it would
/// double-count capacity.
async fn existing_registration(
    meta: &PgPool,
    reality_id: Uuid,
) -> Result<Option<(String, String, String)>, String> {
    sqlx::query_as("SELECT db_host, db_name, status FROM reality_registry WHERE reality_id = $1")
        .bind(reality_id)
        .fetch_optional(meta)
        .await
        .map_err(|e| format!("read reality_registry: {e}"))
}

/// Statuses past the point where re-running provisioning is meaningful.
const SETTLED_STATUSES: [&str; 6] = [
    "active",
    "migrating",
    "pending_close",
    "frozen",
    "archived",
    "soft_deleted",
];

/// The real path: capacity-locked placement wrapping the 11-step provision.
async fn provision(
    args: &Args,
    cfg: &Config,
    meta: &PgPool,
    planner: CapacityPlanner,
) -> Result<ExitCode, String> {
    // RESUME BEFORE PLACE. See existing_registration.
    if let Some((host, name, status)) = existing_registration(meta, args.reality_id).await? {
        if SETTLED_STATUSES.contains(&status.as_str()) {
            println!(
                "{}",
                json_obj(&[
                    ("mode", jstr("provision")),
                    ("reality_id", jstr(&args.reality_id.to_string())),
                    ("shard", jstr(&host)),
                    ("db_name", jstr(&name)),
                    ("already_provisioned", "true".into()),
                    ("status", jstr(&status)),
                ])
            );
            eprintln!(
                "NOOP: reality {} is already {status} on {host} as {name}; nothing to do",
                args.reality_id
            );
            return Ok(ExitCode::SUCCESS);
        }
        eprintln!(
            "[provision] resuming reality {} on its REGISTERED shard {host} (status={status}); \
             capacity placement skipped — the slot was claimed by the first attempt",
            args.reality_id
        );
        return resume_on_shard(args, cfg, meta, &host, &name).await;
    }

    let shard_admin = connect_shard_admin(&cfg.shard_admin_dsn).await?;
    let report_slot: Arc<Mutex<Option<world_service::ProvisionReport>>> =
        Arc::new(Mutex::new(None));

    // place_reality holds a per-shard advisory lock across pick → register and
    // recounts under it. We run the WHOLE provision inside that critical
    // section: the registry row (step 3) is what claims the slot, and steps 4+
    // must not run against a shard that filled in between. Provisioning is an
    // admin-gated, low-frequency action, so serialising it per shard is the
    // right trade against an over-subscribed shard.
    let placed = place_reality(meta, &planner, true, |shard_id| {
        let shard_id = shard_id.clone();
        let slot = Arc::clone(&report_slot);
        let meta = meta.clone();
        let shard_admin = shard_admin.clone();
        let bridge = BridgeClient::new(cfg.bridge_url.clone(), cfg.bridge_token.clone());
        let (hostport, user, pass, sql_dir) = (
            cfg.shard_hostport.clone(),
            cfg.pg_user.clone(),
            cfg.pg_pass.clone(),
            cfg.sql_dir.clone(),
        );
        let req = ProvisionRequest {
            reality_id: args.reality_id,
            locale: args.locale.clone(),
            deploy_cohort: args.deploy_cohort,
            reason: args.reason.clone(),
            owner_user_id: args.owner_user_id,
        };
        async move {
            // Re-read live capacity and keep ONLY the shard the lock is held
            // for, so the planner inside provision_reality necessarily returns
            // that shard. A fabricated snapshot here would reintroduce exactly
            // the drill's defect.
            let snap = live_snapshot(&meta).await?;
            let pinned: Vec<ShardCapacity> = snap
                .into_iter()
                .filter(|s| s.shard_id == shard_id)
                .collect();

            let handle = tokio::runtime::Handle::current();
            let out = tokio::task::spawn_blocking(move || {
                let mut effects = LiveEffects::new(
                    handle, bridge, shard_admin, hostport, &user, &pass, &sql_dir,
                );
                Provisioner::new(CapacityThresholds::default())
                    .provision_reality(req, &pinned, &mut effects)
            })
            .await
            .map_err(|e| {
                world_service::ProvisionerError::InvalidState(format!("join: {e}"))
            })??;

            *slot.lock().expect("report slot poisoned") = Some(out);
            Ok(())
        }
    })
    .await;

    let report = report_slot.lock().expect("report slot poisoned").take();
    match (placed, report) {
        (Ok(shard), Some(r)) => {
            println!(
                "{}",
                json_obj(&[
                    ("mode", jstr("provision")),
                    ("reality_id", jstr(&r.reality_id.to_string())),
                    ("shard", jstr(shard.as_str())),
                    ("db_name", jstr(&r.db_name)),
                    ("steps", r.steps.len().to_string()),
                ])
            );
            eprintln!(
                "PASS: reality {} provisioned on {} as {} ({} steps)",
                r.reality_id,
                shard.as_str(),
                r.db_name,
                r.steps.len()
            );
            Ok(ExitCode::SUCCESS)
        }
        (Ok(_), None) => {
            eprintln!("FAIL: placement reported success but no provision report was produced");
            Ok(ExitCode::from(1))
        }
        (Err(e), _) => {
            println!(
                "{}",
                json_obj(&[
                    ("mode", jstr("provision")),
                    ("reality_id", jstr(&args.reality_id.to_string())),
                    ("error", jstr(&e.to_string())),
                ])
            );
            eprintln!("FAIL: {e}");
            Ok(ExitCode::from(1))
        }
    }
}

/// Re-run the provision pinned to the shard the registry ALREADY names.
///
/// No advisory lock and no placement: the slot is already claimed by the
/// existing row (`capacity_glue::LIVE_STATES` counts `provisioning` and
/// `seeding`), so taking it again would double-count the shard.
async fn resume_on_shard(
    args: &Args,
    cfg: &Config,
    meta: &PgPool,
    host: &str,
    registered_db_name: &str,
) -> Result<ExitCode, String> {
    // `db_name` is derived deterministically from `reality_id`, so a mismatch
    // means the row was written by something using a different naming rule.
    // Refuse rather than create a second database for one reality.
    let expected = db_name_preview(args.reality_id);
    if registered_db_name != expected {
        return Err(format!(
            "registry names database {registered_db_name} for reality {} but this build derives \
             {expected}; refusing to act on a row written under a different naming rule",
            args.reality_id
        ));
    }

    let snap = live_snapshot(meta).await.map_err(|e| format!("capacity snapshot: {e}"))?;
    let pinned: Vec<ShardCapacity> =
        snap.into_iter().filter(|s| s.shard_id.as_str() == host).collect();
    if pinned.is_empty() {
        return Err(format!(
            "reality {} is registered on shard {host}, which is not in shard_utilization; \
             the shard must be re-registered before the provision can be resumed",
            args.reality_id
        ));
    }

    let shard_admin = connect_shard_admin(&cfg.shard_admin_dsn).await?;
    let bridge = BridgeClient::new(cfg.bridge_url.clone(), cfg.bridge_token.clone());
    let (hostport, user, pass, sql_dir) = (
        cfg.shard_hostport.clone(),
        cfg.pg_user.clone(),
        cfg.pg_pass.clone(),
        cfg.sql_dir.clone(),
    );
    let req = ProvisionRequest {
        reality_id: args.reality_id,
        locale: args.locale.clone(),
        deploy_cohort: args.deploy_cohort,
        reason: args.reason.clone(),
        owner_user_id: args.owner_user_id,
    };
    let handle = tokio::runtime::Handle::current();
    let report = tokio::task::spawn_blocking(move || {
        let mut effects =
            LiveEffects::new(handle, bridge, shard_admin, hostport, &user, &pass, &sql_dir);
        Provisioner::new(CapacityThresholds::default()).provision_reality(req, &pinned, &mut effects)
    })
    .await
    .map_err(|e| format!("join: {e}"))?;

    match report {
        Ok(r) => {
            println!(
                "{}",
                json_obj(&[
                    ("mode", jstr("provision")),
                    ("reality_id", jstr(&r.reality_id.to_string())),
                    ("shard", jstr(host)),
                    ("db_name", jstr(&r.db_name)),
                    ("steps", r.steps.len().to_string()),
                    ("resumed", "true".into()),
                ])
            );
            eprintln!(
                "PASS: reality {} resumed on {host} as {} ({} steps)",
                r.reality_id,
                r.db_name,
                r.steps.len()
            );
            Ok(ExitCode::SUCCESS)
        }
        Err(e) => {
            println!(
                "{}",
                json_obj(&[
                    ("mode", jstr("provision")),
                    ("reality_id", jstr(&args.reality_id.to_string())),
                    ("shard", jstr(host)),
                    ("resumed", "true".into()),
                    ("error", jstr(&e.to_string())),
                ])
            );
            eprintln!("FAIL: {e}");
            Ok(ExitCode::from(1))
        }
    }
}

// ─── helpers ─────────────────────────────────────────────────────────────────

/// The database name the real run will create.
///
/// This CALLS the provisioner's own function rather than reimplementing it. The
/// first version hand-copied the formatting and cited
/// `tests/provision_worker.rs::dry_run_db_name_matches_provisioner` as proof the
/// two agreed — **a test that was never written**, in a file that does not
/// exist. A citation is not a mechanism; deleting the second implementation is.
fn db_name_preview(reality_id: Uuid) -> String {
    world_service::provisioner::db_name_for(reality_id)
}

fn shard_json(s: &ShardCapacity) -> String {
    json_obj(&[
        ("shard", jstr(s.shard_id.as_str())),
        ("used", s.used_realities.to_string()),
        ("total", s.total_realities.to_string()),
    ])
}

/// Minimal JSON emitters. serde_json IS a dependency of this crate, but the
/// output here is a flat fixed-shape object and the Go side parses it with
/// encoding/json; keeping it literal avoids deriving Serialize on types that
/// live in the library surface purely for a CLI's benefit.
fn json_obj(fields: &[(&str, String)]) -> String {
    let body: Vec<String> =
        fields.iter().map(|(k, v)| format!("\"{k}\":{v}")).collect();
    format!("{{{}}}", body.join(","))
}

fn jarr(items: &[String]) -> String {
    format!("[{}]", items.join(","))
}

/// JSON string literal with the escapes the RFC requires for our value space
/// (identifiers, DSN-free error text).
fn jstr(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// Bound on any single statement issued on the META pool.
///
/// `place_reality` takes a per-shard `pg_advisory_lock`, which **waits
/// indefinitely** by default: a second provision targeting the same shard would
/// block for the full duration of the first (CREATE DATABASE + 15 migrations)
/// with no bound and no output. `statement_timeout` applies to the
/// `SELECT pg_advisory_lock(...)` statement itself, so it converts an unbounded
/// wait into a legible error.
///
/// Set on the meta pool ONLY. The shard-admin pool and the migration pool must
/// NOT carry it — a migration is legitimately long, and killing one midway is
/// the failure this is trying to prevent.
const META_STATEMENT_TIMEOUT_MS: i32 = 120_000;

/// The meta pool: capacity reads + the placement advisory lock.
///
/// `max_connections(4)` is not arbitrary. `place_reality` holds one connection
/// for the whole critical section while the callback's `live_snapshot` acquires
/// a second, so the real path needs **at least 2** concurrently; lowering this
/// to 1 would deadlock silently rather than fail.
async fn connect_meta(dsn: &str) -> Result<PgPool, String> {
    PgPoolOptions::new()
        .max_connections(4)
        .after_connect(|conn, _meta| {
            Box::pin(async move {
                sqlx::query(&format!("SET statement_timeout = {META_STATEMENT_TIMEOUT_MS}"))
                    .execute(conn)
                    .await
                    .map(|_| ())
            })
        })
        .connect(dsn)
        .await
        .map_err(|e| format!("connect failed: {e}"))
}

async fn connect(dsn: &str) -> Result<PgPool, String> {
    PgPoolOptions::new()
        .max_connections(4)
        .connect(dsn)
        .await
        // NEVER interpolate the DSN into the error — it carries the password,
        // and this string reaches the admin audit trail via the Go handler.
        .map_err(|e| format!("connect failed: {e}"))
}

/// Escape hatch for [`connect_shard_admin`]. It must carry a REASON, not be a
/// boolean: a bare `=1` flag records that someone bypassed the check and never
/// why, and outlives the incident that justified it.
const ALLOW_SUPERUSER_ENV: &str = "PROVISION_ALLOW_SUPERUSER_REASON";

/// Connect to the shard, and REFUSE if the role is a superuser.
///
/// `W7` created `loreweave_provisioner` (CREATEDB only) and proved by hand that
/// provisioning works under it. That is not enough: nothing in the repository
/// pointed the worker at it, so the committed configuration still let an
/// operator provision as `loreweave` — `rolsuper` + `rolbypassrls` — and the
/// natural thing to reach for is the credential every other service already
/// uses. A role that exists but is never required is apparatus without a
/// subject; this is the check that gives it one.
///
/// Superuser is what ownership, RLS and per-database GRANTs cannot restrain, so
/// a provisioner bug running under it has the whole cluster in reach. The role
/// needs exactly `CREATEDB`.
async fn connect_shard_admin(dsn: &str) -> Result<PgPool, String> {
    let pool = connect(dsn).await?;
    let (role, is_super): (String, bool) =
        sqlx::query_as("SELECT current_user::text, rolsuper FROM pg_roles WHERE rolname = current_user")
            .fetch_one(&pool)
            .await
            .map_err(|e| format!("could not determine the shard role's privileges: {e}"))?;

    match superuser_verdict(&role, is_super, std::env::var(ALLOW_SUPERUSER_ENV).ok()) {
        Ok(Some(warning)) => eprintln!("{warning}"),
        Ok(None) => {}
        Err(refusal) => return Err(refusal),
    }
    Ok(pool)
}

/// The privilege decision, as a pure function so it is testable without a
/// database — the live check above needs Postgres, and a rule reachable only
/// through a live connection is a rule the suite cannot exercise.
///
/// Returns `Ok(None)` to proceed, `Ok(Some(warning))` to proceed loudly under
/// the escape hatch, `Err` to refuse.
fn superuser_verdict(
    role: &str,
    is_super: bool,
    override_reason: Option<String>,
) -> Result<Option<String>, String> {
    if !is_super {
        return Ok(None);
    }
    // A BLANK reason is not a reason. Treating `=1` or `=""` as consent would
    // make the hatch a boolean again, which is the shape that outlives the
    // incident that justified it.
    if let Some(reason) = override_reason {
        if !reason.trim().is_empty() {
            return Ok(Some(format!(
                "[provision] WARNING: provisioning as SUPERUSER {role} — allowed because \
                 {ALLOW_SUPERUSER_ENV}={reason}"
            )));
        }
    }
    Err(format!(
        "refusing to provision as superuser {role}: creating databases with a role that holds \
         rolsuper puts every other tenant's database in reach of a bug here. Use a CREATEDB-only \
         role (infra/db-ensure.sh creates `loreweave_provisioner`). To override deliberately, set \
         {ALLOW_SUPERUSER_ENV} to a reason"
    ))
}

fn setup_err(msg: &str) -> ExitCode {
    eprintln!("provision: NOTRUN(setup): {msg}");
    ExitCode::from(2)
}

#[cfg(test)]
mod tests {
    use super::*;

    // A cold-start review found this binary had NO tests at all: every one of
    // the 20 tests and 10 bites covering `reality provision` was on the Go side,
    // so the argument parser, the fail-closed config, the JSON the Go side
    // parses, and the name the dry run previews were all unexercised.

    fn args(v: &[&str]) -> Result<Args, String> {
        Args::parse(v.iter().map(|s| s.to_string()))
    }

    const RID: &str = "11111111-1111-4111-8111-111111111111";

    #[test]
    fn parses_a_minimal_invocation() {
        let a = args(&["--reality-id", RID, "--reason", "because"]).expect("should parse");
        assert_eq!(a.reality_id.to_string(), RID);
        assert_eq!(a.reason, "because");
        assert_eq!(a.locale, "en", "locale should default");
        assert_eq!(a.deploy_cohort, 0);
        assert!(!a.dry_run);
    }

    #[test]
    fn requires_reality_id_and_reason() {
        assert!(args(&["--reason", "r"]).is_err(), "missing --reality-id must fail");
        assert!(args(&["--reality-id", RID]).is_err(), "missing --reason must fail");
    }

    #[test]
    fn rejects_a_malformed_uuid_and_an_unknown_flag() {
        assert!(args(&["--reality-id", "nope", "--reason", "r"]).is_err());
        assert!(args(&["--reality-id", RID, "--reason", "r", "--wat", "1"]).is_err());
    }

    #[test]
    fn dry_run_is_valueless_and_does_not_eat_the_next_flag() {
        // The hazard: if `--dry-run` were parsed as a valued flag it would
        // consume `--reason`, and the run would fail for the wrong reason.
        let a = args(&["--dry-run", "--reality-id", RID, "--reason", "r"]).expect("parses");
        assert!(a.dry_run);
        assert_eq!(a.reason, "r");
    }

    #[test]
    fn a_value_beginning_with_dashes_is_still_a_value() {
        // Operator-supplied text reaches argv; a reason that looks like a flag
        // must not be re-parsed as one.
        let a = args(&["--reality-id", RID, "--reason", "--not-a-flag"]).expect("parses");
        assert_eq!(a.reason, "--not-a-flag");
    }

    #[test]
    fn a_trailing_flag_without_a_value_is_an_error_not_a_panic() {
        assert!(args(&["--reality-id", RID, "--reason"]).is_err());
    }

    // W6 — ownership. `None` is a real category (platform-owned), so the parser
    // must distinguish "absent" from "present", not coerce both to a default.
    #[test]
    fn owner_is_optional_and_absent_means_platform_owned() {
        let a = args(&["--reality-id", RID, "--reason", "r"]).unwrap();
        assert!(a.owner_user_id.is_none(), "absent --owner-user-id must stay None");

        const OWNER: &str = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c";
        let b = args(&["--reality-id", RID, "--reason", "r", "--owner-user-id", OWNER]).unwrap();
        assert_eq!(b.owner_user_id.unwrap().to_string(), OWNER);
    }

    // The nil UUID parses fine, so without an explicit check it flows onward
    // and the bridge writes ('user', 00000000-…) — a reality owned by a user
    // that cannot exist.
    #[test]
    fn the_nil_owner_uuid_is_refused() {
        let e = args(&[
            "--reality-id", RID, "--reason", "r",
            "--owner-user-id", "00000000-0000-0000-0000-000000000000",
        ]);
        // Matched rather than unwrap_err()'d: `Args` carries no Debug (and
        // should not -- it holds the operator's reason text), so unwrap_err
        // will not compile.
        match e {
            Err(msg) => assert!(msg.contains("nil UUID"), "wrong error: {msg}"),
            Ok(_) => panic!("the nil UUID must not be accepted as an owner"),
        }
    }

    #[test]
    fn a_malformed_owner_is_refused_not_ignored() {
        // Silently dropping an unparseable owner would record the reality as
        // platform-owned — the tenancy failure this column exists to prevent.
        //
        // Asserts WHICH error, not merely that one occurred. `is_err()` alone
        // could not distinguish this guard from the nil-UUID guard below it:
        // degrading the parse to `unwrap_or(Uuid::nil())` yields a nil owner,
        // the nil check then refuses it, and the test stays green while the
        // guard it names is gone. The bite harness caught exactly that.
        match args(&["--reality-id", RID, "--reason", "r", "--owner-user-id", "nope"]) {
            Err(msg) => assert!(
                msg.contains("--owner-user-id") && !msg.contains("nil UUID"),
                "want a PARSE diagnosis, got: {msg}"
            ),
            Ok(_) => panic!("a malformed owner must be refused"),
        }
    }

    // W7 — provisioning must not run as superuser.
    #[test]
    fn a_non_superuser_role_proceeds() {
        assert_eq!(superuser_verdict("loreweave_provisioner", false, None), Ok(None));
    }

    #[test]
    fn a_superuser_role_is_refused() {
        let v = superuser_verdict("loreweave", true, None);
        assert!(v.is_err(), "superuser must be refused");
        assert!(v.unwrap_err().contains("refusing to provision as superuser"));
    }

    #[test]
    fn the_escape_hatch_needs_a_reason_not_a_flag() {
        // A boolean hatch silences the check and keeps silencing it long after
        // the incident; a blank string must NOT count as consent.
        for blank in [Some(String::new()), Some("   ".into())] {
            assert!(
                superuser_verdict("loreweave", true, blank).is_err(),
                "a blank reason must not open the hatch"
            );
        }
        let opened = superuser_verdict("loreweave", true, Some("restoring after incident 42".into()));
        assert!(matches!(opened, Ok(Some(_))), "a real reason should proceed");
        // ...and it must be LOUD about it.
        assert!(opened.unwrap().unwrap().contains("WARNING"));
    }

    #[test]
    fn a_non_superuser_ignores_the_escape_hatch_entirely() {
        // The hatch must not become a way to change unrelated behaviour.
        assert_eq!(superuser_verdict("prov", false, Some("whatever".into())), Ok(None));
    }

    #[test]
    fn cohort_must_fit_a_u8() {
        assert!(args(&["--reality-id", RID, "--reason", "r", "--deploy-cohort", "300"]).is_err());
        let a = args(&["--reality-id", RID, "--reason", "r", "--deploy-cohort", "7"]).unwrap();
        assert_eq!(a.deploy_cohort, 7);
    }

    // The dry-run preview must name the database the real run creates. Not a
    // reimplementation compared against the original — the SAME function.
    #[test]
    fn preview_names_what_the_provisioner_will_create() {
        let id = Uuid::parse_str(RID).unwrap();
        assert_eq!(db_name_preview(id), world_service::provisioner::db_name_for(id));
        assert!(db_name_preview(id).starts_with("lw_reality_"));
    }

    #[test]
    fn json_strings_escape_what_json_requires() {
        assert_eq!(jstr(r#"a"b"#), r#""a\"b""#);
        assert_eq!(jstr(r"a\b"), r#""a\\b""#);
        assert_eq!(jstr("a\nb"), r#""a\nb""#);
        assert_eq!(jstr("a\tb"), r#""a\tb""#);
        // A control character must be ESCAPED, not dropped and not passed raw:
        // raw, it makes the object the Go side parses invalid.
        assert_eq!(jstr("a\u{1}b"), r#""a\u0001b""#);
    }

    // The Go side parses this with encoding/json; a malformed object there is a
    // "worker produced unparseable output" error with no diagnosis.
    #[test]
    fn report_json_is_well_formed_even_with_hostile_text() {
        let out = json_obj(&[
            ("mode", jstr("provision")),
            ("error", jstr("boom \"quoted\" and \\slashed\\ and\nnewlined")),
            ("steps", 11.to_string()),
        ]);
        let parsed: serde_json::Value =
            serde_json::from_str(&out).expect("emitted JSON must parse");
        assert_eq!(parsed["mode"], "provision");
        assert_eq!(parsed["steps"], 11);
        assert!(parsed["error"].as_str().unwrap().contains("quoted"));
    }

    #[test]
    fn settled_statuses_cover_every_state_past_provisioning() {
        // If a status is live but absent here, a re-run would try to provision
        // over a working reality.
        for s in ["active", "frozen", "migrating", "pending_close"] {
            assert!(SETTLED_STATUSES.contains(&s), "{s} must be treated as settled");
        }
        for s in ["provisioning", "seeding"] {
            assert!(!SETTLED_STATUSES.contains(&s), "{s} must remain resumable");
        }
    }
}
