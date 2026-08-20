//! `actor-control` — the actor-control WORKER.
//!
//! The binary the Go `admin reality grant-control` / `revoke-control` /
//! `create-actor` commands exec, in exactly the shape `admin-cli` already uses
//! for `provision` and `rebuilder`: **secrets arrive by env** so they never
//! reach the process table, **identifiers arrive as flags**, **stdout is one
//! JSON object** and nothing else, human diagnostics go to stderr, and the exit
//! code is the verdict.
//!
//! ## Why a worker and not an HTTP call
//!
//! The grant/revoke routes on world-service are `require_internal`-gated —
//! correct for a service-to-service surface, and unreachable by any operator.
//! So `P1`'s writer shipped with no caller: the same orphan shape the feature
//! existed to fix, one tier up. Three facts ruled out the alternatives:
//!
//! 1. **`admin-cli` has no HTTP invoker.** Every command is a subprocess or a
//!    direct `pgxpool`; an HTTP client would be a third pattern.
//! 2. **`contracts/service_acl/matrix.yaml` does not sanction the edge.**
//!    admin-cli calls meta-worker, not world-service.
//! 3. **The sanctioned path — straight to the Go bridge — has neither safety
//!    check**, and cannot have the second: `actors` lives in the per-reality
//!    database meta-worker does not hold.
//!
//! So the checks live in [`world_service::actor_control_flow`] and BOTH callers
//! go through them. This binary contributes no control logic of its own; if it
//! did, an operator and a service would be running different rules.
//!
//! ## Modes
//!
//! `--dry-run` reports what it can prove without writing: the reality accepts
//! commands, and (for a grant) the actor exists. It deliberately does **not**
//! report who currently drives the actor — that is a cross-user read of
//! `actor_control_binding`, a path migration `034` registered as sensitive, and
//! a preview that answered it would be an unaudited way to probe who holds
//! whom. The conflict is decided at write time, inside the transaction, where
//! a CAS has to live anyway.
//!
//! ## Exit codes
//!
//! - `0` — the operation succeeded, or the dry run completed
//! - `1` — refused or failed; stdout JSON carries `error`, and `conflict: true`
//!   when the refusal is a statement about the world (somebody else drives this
//!   actor · the CAS named a user who no longer holds it · the reality is
//!   closed · the actor does not exist) rather than a fault of ours
//! - `2` — setup/config error (missing env, unreachable DB): nothing attempted

use std::process::ExitCode;

use serde_json::{Value, json};
use sqlx::PgPool;
use sqlx::postgres::PgPoolOptions;
use uuid::Uuid;

use world_service::actor_control_flow as flow;
use world_service::errors::ProvisionerError;
use world_service::provision_flow::EffectsConfig;

/// Env vars carrying a DSN, a secret or a path. **No defaults** — a default
/// would silently target the wrong stack. `ACTOR_CONTROL_PG_PASSWORD` is absent
/// on purpose: peer/trust auth is legitimate, so an empty password is a valid
/// configuration rather than a missing one.
const REQUIRED_ENV: [&str; 6] = [
    "ACTOR_CONTROL_META_DSN",
    "ACTOR_CONTROL_BRIDGE_URL",
    "ACTOR_CONTROL_BRIDGE_TOKEN",
    "ACTOR_CONTROL_SHARD_HOSTPORT",
    "ACTOR_CONTROL_PG_USER",
    "ACTOR_CONTROL_META_ALLOWLIST",
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

/// Which operation. A closed set, parsed once, so an unknown `--op` is refused
/// at the boundary rather than falling through to a default that acts.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Op {
    Grant,
    Revoke,
    CreateActor,
}

impl Op {
    fn parse(s: &str) -> Result<Self, String> {
        match s {
            "grant" => Ok(Op::Grant),
            "revoke" => Ok(Op::Revoke),
            "create-actor" => Ok(Op::CreateActor),
            other => Err(format!(
                "--op {other} is not one of: grant, revoke, create-actor"
            )),
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Op::Grant => "grant",
            Op::Revoke => "revoke",
            Op::CreateActor => "create-actor",
        }
    }
}

struct Args {
    op: Op,
    reality_id: Uuid,
    /// Required for `grant`. Absent for the other two.
    user_ref_id: Option<Uuid>,
    /// Required for `grant` and `revoke`. Absent for `create-actor`, which
    /// mints it.
    actor_id: Option<Uuid>,
    /// Optional CAS on `revoke`.
    expected_user_ref_id: Option<Uuid>,
    /// Optional on `create-actor`: adopt this island id instead of allocating.
    entity_id: Option<i64>,
    reason: String,
    dry_run: bool,
}

impl Args {
    /// Minimal `--flag value` parser. No clap: this crate does not depend on
    /// it, and the sibling workers parse the same way, so the admin framework
    /// sees one consistent worker CLI.
    fn parse(argv: impl Iterator<Item = String>) -> Result<Self, String> {
        let mut op: Option<Op> = None;
        let mut reality_id: Option<Uuid> = None;
        let mut user_ref_id: Option<Uuid> = None;
        let mut actor_id: Option<Uuid> = None;
        let mut expected_user_ref_id: Option<Uuid> = None;
        let mut entity_id: Option<i64> = None;
        let mut reason: Option<String> = None;
        let mut dry_run = false;

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
                "--op" => op = Some(Op::parse(val)?),
                "--reality-id" => reality_id = Some(uuid_arg(flag, val)?),
                "--user-ref-id" => user_ref_id = Some(uuid_arg(flag, val)?),
                "--actor-id" => actor_id = Some(uuid_arg(flag, val)?),
                "--expected-user-ref-id" => expected_user_ref_id = Some(uuid_arg(flag, val)?),
                "--entity-id" => {
                    entity_id = Some(val.parse().map_err(|e| format!("--entity-id: {e}"))?);
                }
                "--reason" => reason = Some(val.clone()),
                other => return Err(format!("unknown flag {other}")),
            }
            i += 2;
        }

        let op = op.ok_or("--op is required (grant, revoke, create-actor)")?;
        let reality_id = reality_id.ok_or("--reality-id is required")?;
        let reason = reason.ok_or("--reason is required")?;

        // Per-op requirements, checked HERE rather than discovered as a NULL
        // three layers down. A grant with no user would otherwise reach the
        // bridge as a nil uuid, which every CHECK on the table accepts.
        match op {
            Op::Grant => {
                if user_ref_id.is_none() {
                    return Err("--user-ref-id is required for --op grant".to_string());
                }
                if actor_id.is_none() {
                    return Err("--actor-id is required for --op grant".to_string());
                }
            }
            Op::Revoke => {
                if actor_id.is_none() {
                    return Err("--actor-id is required for --op revoke".to_string());
                }
            }
            Op::CreateActor => {
                if actor_id.is_some() {
                    return Err("--actor-id is not accepted for --op create-actor: the \
                                registry MINTS the actor id, and supplying one would \
                                make the caller a second source for it"
                        .to_string());
                }
            }
        }
        Ok(Args {
            op,
            reality_id,
            user_ref_id,
            actor_id,
            expected_user_ref_id,
            entity_id,
            reason,
            dry_run,
        })
    }
}

/// Parse a uuid flag, refusing the nil uuid.
///
/// The nil uuid is not an identifier. Accepting it would write
/// `(00000000-…, reality, actor)` into `actor_control_binding` — a binding held
/// by a user that cannot exist, satisfying every CHECK on the table. Refused
/// rather than treated as absent: an operator who typed a flag meant a value.
fn uuid_arg(flag: &str, val: &str) -> Result<Uuid, String> {
    let id = Uuid::parse_str(val).map_err(|e| format!("{flag}: {e}"))?;
    if id.is_nil() {
        return Err(format!("{flag} must not be the nil UUID"));
    }
    Ok(id)
}

// ─── config ──────────────────────────────────────────────────────────────────

struct Config {
    meta_dsn: String,
    effects: EffectsConfig,
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
            meta_dsn: get("ACTOR_CONTROL_META_DSN"),
            effects: EffectsConfig {
                bridge_url: get("ACTOR_CONTROL_BRIDGE_URL"),
                bridge_token: get("ACTOR_CONTROL_BRIDGE_TOKEN"),
                shard_hostport: get("ACTOR_CONTROL_SHARD_HOSTPORT"),
                pg_user: get("ACTOR_CONTROL_PG_USER"),
                // May legitimately be empty (peer/trust auth, or a .pgpass), so
                // it is not in REQUIRED_ENV — but it is still read only from
                // env, never a literal.
                pg_pass: std::env::var("ACTOR_CONTROL_PG_PASSWORD").unwrap_or_default(),
                // Structurally required by EffectsConfig and UNUSED on every
                // path this worker takes: `sql_dir` is the migration directory,
                // read only when provisioning creates a database. Left as the
                // repo default rather than invented, so a future path that does
                // read it finds the same value every other caller uses.
                sql_dir: "contracts/migrations/per_reality".to_string(),
                meta_allowlist: get("ACTOR_CONTROL_META_ALLOWLIST"),
            },
        })
    }
}

// ─── run ─────────────────────────────────────────────────────────────────────

async fn run(args: &Args, cfg: &Config) -> Result<ExitCode, String> {
    let meta = connect_meta(&cfg.meta_dsn).await?;
    let result = if args.dry_run {
        dry_run(args, &meta, cfg).await
    } else {
        execute(args, &meta, cfg).await
    };
    Ok(match result {
        Ok(extra) => {
            emit(args, "ok", extra);
            ExitCode::SUCCESS
        }
        Err(e) => {
            let conflict = is_conflict(&e);
            emit(
                args,
                if conflict { "refused" } else { "failed" },
                json!({ "error": e.to_string(), "conflict": conflict }),
            );
            eprintln!(
                "{}: {e}",
                if conflict { "REFUSED" } else { "FAILED" }
            );
            ExitCode::from(1)
        }
    })
}

/// Read-only preview. Writes nothing.
async fn dry_run(args: &Args, meta: &PgPool, cfg: &Config) -> Result<Value, ProvisionerError> {
    match args.op {
        // Revoke does not bind (see `flow::revoke`), so there is nothing it can
        // preview that would not require the sensitive read. Saying so is the
        // honest report; inventing a check to have something to print would be
        // the vacuous one.
        Op::Revoke => Ok(json!({
            "mode": "dry-run",
            "would_revoke": true,
            "note": "the live holder is NOT read here: that is a cross-user read of \
                     actor_control_binding, which only the audited write path may take. \
                     The CAS is evaluated inside the write transaction.",
        })),
        Op::Grant => {
            let actor_id = args.actor_id.expect("--actor-id required for grant, checked in parse");
            let p = flow::preview_grant(meta, &cfg.effects, args.reality_id, actor_id).await?;
            Ok(json!({
                "mode": "dry-run",
                "reality_accepts_commands": p.reality_accepts_commands,
                "actor_exists": p.actor_exists,
                "actor_is_driven": p.actor_is_driven,
                // `RA3`: a grant is refused when the actor is missing OR
                // already driven, so the verdict is both — not just the first.
                "would_grant": p.actor_exists && !p.actor_is_driven,
                "note": "the driver slot IS checked; who holds it is not reported — that \
                         is a per-user fact 034 registers as sensitive. The read behind \
                         this writes a meta_read_audit row.",
            }))
        }
        Op::CreateActor => {
            // Binding proves the reality takes commands; nothing is written.
            flow::bind_reality(meta, &cfg.effects.meta_allowlist, args.reality_id).await?;
            Ok(json!({
                "mode": "dry-run",
                "reality_accepts_commands": true,
                "would_create_actor": true,
                "entity_id_source": if args.entity_id.is_some() { "adopted" } else { "allocated" },
            }))
        }
    }
}

/// Do the thing.
async fn execute(args: &Args, meta: &PgPool, cfg: &Config) -> Result<Value, ProvisionerError> {
    match args.op {
        Op::Grant => {
            let outcome = flow::grant(
                meta,
                &cfg.effects,
                args.user_ref_id.expect("--user-ref-id required for grant, checked in parse"),
                args.reality_id,
                args.actor_id.expect("--actor-id required for grant, checked in parse"),
                &args.reason,
            )
            .await?;
            Ok(json!({
                "mode": "live",
                "outcome": outcome.as_str(),
                "changed": outcome.changed(),
            }))
        }
        Op::Revoke => {
            let outcome = flow::revoke(
                meta,
                &cfg.effects,
                args.reality_id,
                args.actor_id.expect("--actor-id required for revoke, checked in parse"),
                args.expected_user_ref_id,
                &args.reason,
            )
            .await?;
            Ok(json!({
                "mode": "live",
                "outcome": outcome.as_str(),
                "changed": outcome.changed(),
            }))
        }
        Op::CreateActor => {
            let row =
                flow::create_actor(meta, &cfg.effects, args.reality_id, args.entity_id).await?;
            Ok(json!({
                "mode": "live",
                "outcome": "actor_created",
                "changed": true,
                "created_actor_id": row.actor_id.to_string(),
                "entity_id": row.entity_id,
            }))
        }
    }
}

/// Is this refusal a statement about the WORLD rather than a fault of ours?
///
/// The distinction is the whole reason these are separate variants. An operator
/// who sees `conflict: true` should reload and decide; one who sees `false`
/// should look at the bridge. Collapsing them would send someone hunting for a
/// player who does not exist while the real problem is an outage — and would
/// make a blind retry look reasonable when it is not.
fn is_conflict(e: &ProvisionerError) -> bool {
    matches!(
        e,
        ProvisionerError::ActorAlreadyDriven(_)
            | ProvisionerError::ControlCasMismatch(_)
            | ProvisionerError::RealityClosed(_, _)
            | ProvisionerError::UnknownActor(_, _)
            // A reality with no registry row: the caller named a world that
            // does not exist. Before this arm, a mistyped --reality-id on a
            // REVOKE found no live binding and reported "already in the
            // requested state" with exit 0 — a tier-1 destructive command
            // claiming success while the real driver kept driving.
            | ProvisionerError::NotFound(_)
    )
}

/// One JSON object on stdout, and nothing else.
///
/// The identifying keys are written HERE, once, so every branch reports the op
/// and the ids it acted on. The Go side checks the echoed `reality_id` against
/// the one it asked for; a branch that forgot to include it would defeat that
/// check by making it vacuous rather than by failing it.
fn emit(args: &Args, status: &str, extra: Value) {
    let mut out = json!({
        "op": args.op.as_str(),
        "status": status,
        "reality_id": args.reality_id.to_string(),
        "dry_run": args.dry_run,
    });
    if let Some(a) = args.actor_id {
        out["actor_id"] = Value::String(a.to_string());
    }
    if let (Some(o), Some(e)) = (out.as_object_mut(), extra.as_object()) {
        for (k, v) in e {
            o.insert(k.clone(), v.clone());
        }
    }
    println!("{out}");
}

async fn connect_meta(dsn: &str) -> Result<PgPool, String> {
    PgPoolOptions::new()
        .max_connections(4)
        .connect(dsn)
        // The DSN carries a password; report the failure, never the string.
        .await
        .map_err(|e| format!("connect meta: {e}"))
}

/// Exit 2 — nothing was attempted.
fn setup_err(msg: &str) -> ExitCode {
    eprintln!("SETUP: {msg}");
    ExitCode::from(2)
}

#[cfg(test)]
mod tests {
    use super::*;

    const RID: &str = "11111111-1111-4111-8111-111111111111";
    const AID: &str = "22222222-2222-4222-8222-222222222222";
    const UID: &str = "33333333-3333-4333-8333-333333333333";

    fn args(v: &[&str]) -> Result<Args, String> {
        Args::parse(v.iter().map(|s| s.to_string()))
    }

    #[test]
    fn a_grant_needs_a_user_and_an_actor() {
        // Both missing-arg cases assert WHICH flag is named. `is_err()` alone
        // could not tell the two guards apart, so one could be deleted while
        // the test stayed green.
        let no_user = args(&["--op", "grant", "--reality-id", RID, "--actor-id", AID, "--reason", "r"]);
        assert!(
            no_user.err().is_some_and(|m| m.contains("--user-ref-id")),
            "a grant with no user must name the missing flag"
        );
        let no_actor = args(&["--op", "grant", "--reality-id", RID, "--user-ref-id", UID, "--reason", "r"]);
        assert!(
            no_actor.err().is_some_and(|m| m.contains("--actor-id")),
            "a grant with no actor must name the missing flag"
        );
        // …and the complete form parses, or the two assertions above would pass
        // just as well against a parser that refused everything.
        let ok = args(&[
            "--op", "grant", "--reality-id", RID, "--user-ref-id", UID,
            "--actor-id", AID, "--reason", "r",
        ]);
        assert!(ok.is_ok(), "the complete grant form must parse: {:?}", ok.err());
    }

    #[test]
    fn create_actor_refuses_a_supplied_actor_id() {
        // The registry MINTS the actor id (actor_registry::create_actor). A
        // caller-supplied one would make the CLI a second source for a value
        // with one SSOT — the drift `0022`'s allocation exists to prevent.
        let e = args(&["--op", "create-actor", "--reality-id", RID, "--actor-id", AID, "--reason", "r"]);
        assert!(
            e.err().is_some_and(|m| m.contains("MINTS")),
            "create-actor must refuse a supplied --actor-id"
        );
        assert!(
            args(&["--op", "create-actor", "--reality-id", RID, "--reason", "r"]).is_ok(),
            "create-actor without --actor-id must parse"
        );
    }

    #[test]
    fn the_nil_uuid_is_not_an_identifier() {
        const NIL: &str = "00000000-0000-0000-0000-000000000000";
        let e = args(&[
            "--op", "grant", "--reality-id", RID, "--user-ref-id", NIL,
            "--actor-id", AID, "--reason", "r",
        ]);
        assert!(
            e.err().is_some_and(|m| m.contains("nil UUID")),
            "a nil user_ref_id would write a binding held by a user that cannot exist"
        );
    }

    #[test]
    fn an_unknown_op_is_refused_rather_than_defaulted() {
        let e = args(&["--op", "grnat", "--reality-id", RID, "--reason", "r"]);
        assert!(
            e.err().is_some_and(|m| m.contains("not one of")),
            "a typo'd --op must be refused, not fall through to a default that acts"
        );
        // --op is not optional: omitting it must not pick one.
        assert!(
            args(&["--reality-id", RID, "--reason", "r"])
                .err()
                .is_some_and(|m| m.contains("--op is required")),
            "a missing --op must be refused"
        );
    }

    #[test]
    fn a_reason_is_required_for_every_op() {
        // The reason reaches `meta_write_audit`. A write with no explanation is
        // an audit row that cannot answer the question it exists to answer.
        for op in ["grant", "revoke", "create-actor"] {
            let e = args(&["--op", op, "--reality-id", RID, "--actor-id", AID, "--user-ref-id", UID]);
            assert!(
                e.err().is_some_and(|m| m.contains("--reason")),
                "--op {op} must require a reason"
            );
        }
    }

    /// Non-vacuity, both directions. A `is_conflict` that returned `true` for
    /// everything would make a bridge OUTAGE print "REFUSED" and invite an
    /// operator to reload and decide about a service that is simply down.
    #[test]
    fn only_world_statements_are_conflicts() {
        assert!(is_conflict(&ProvisionerError::ActorAlreadyDriven("a".into())));
        assert!(is_conflict(&ProvisionerError::ControlCasMismatch("a".into())));
        assert!(is_conflict(&ProvisionerError::RealityClosed("r".into(), "frozen".into())));
        assert!(is_conflict(&ProvisionerError::UnknownActor("a".into(), "r".into())));

        assert!(!is_conflict(&ProvisionerError::Bridge("the bridge is down".into())));
        assert!(is_conflict(&ProvisionerError::NotFound("r".into())));
        assert!(!is_conflict(&ProvisionerError::NoShardCapacity));
        assert!(!is_conflict(&ProvisionerError::ShardEffect("disk".into())));
    }
}
