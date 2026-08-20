//! `SEALED-BINDING` — the actor-control OPERATIONS, with no transport attached.
//!
//! Everything here was inside `server::handlers::actor_control` until a second
//! caller appeared. That file's own header claims *"thin adapters… no control
//! logic lives in this file"*, and by then the claim was false: the reality
//! bind and the actor-exists precondition — the two checks that make a grant
//! safe — lived in the handler, reachable only over HTTP.
//!
//! The `admin reality grant-control` worker cannot go through that route:
//! `admin-cli` has no HTTP invoker (every command is a subprocess or a direct
//! `pgxpool`), and `contracts/service_acl/matrix.yaml` sanctions admin-cli as a
//! caller of **meta-worker**, not of world-service. The sanctioned path is the
//! Go bridge — which has neither check, and cannot have the second one, because
//! `actors` lives in the per-reality database meta-worker does not hold.
//!
//! So the checks moved HERE, where both callers reach them. Duplicating them
//! into the worker would have produced a second set that drifts; skipping them
//! would have given an OPERATOR a weaker grant path than a service gets.
//!
//! The write itself still goes through the Go meta-write bridge: `I8` requires
//! the `meta_write_audit` row and the outbox event to land in the SAME
//! transaction as the binding, and only Go's `MetaWrite` can do that.

use sqlx::PgPool;
use tracing::error;
use uuid::Uuid;

use crate::actor_registry::{self, ActorRow};
use crate::errors::ProvisionerError;
use crate::provision_flow::{EffectsConfig, existing_registration};
use crate::provisioner_live::BridgeClient;

/// What actually happened. Both grant outcomes are successes; the caller
/// renders them differently because "you already had it" is not "you now have
/// it", and an operator re-running a command deserves to know which.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Outcome {
    /// A live binding was created; this user now drives the actor.
    Granted,
    /// This same user already held the live binding. Nothing was written.
    AlreadyGranted,
    /// The live binding was ended; it survives as history, not as a deletion.
    Revoked,
    /// There was no live binding to end. Nothing was written.
    AlreadyRevoked,
}

impl Outcome {
    /// The stable wire word. Both the HTTP response and the worker's stdout
    /// JSON use these, so an operator and a service read the same vocabulary.
    pub fn as_str(self) -> &'static str {
        match self {
            Outcome::Granted => "granted",
            Outcome::AlreadyGranted => "already_granted",
            Outcome::Revoked => "revoked",
            Outcome::AlreadyRevoked => "already_revoked",
        }
    }

    /// Did this call CHANGE anything? `false` means the world already held the
    /// requested state.
    pub fn changed(self) -> bool {
        matches!(self, Outcome::Granted | Outcome::Revoked)
    }
}

/// What a dry run can honestly report.
///
/// Note what is absent: **WHO currently drives the actor.** `RA3` settled the
/// question this struct used to be silent about, and settled it in the middle:
/// the preview reports whether the slot is TAKEN, and never by whom.
///
/// That split is the whole point. "Will my grant be refused?" is the operator's
/// actual question and a bool answers it; "who holds it?" is a per-user fact
/// `034` registered as sensitive, and handing it to every `admin:write` holder
/// would make the dry run a who-holds-what oracle over the one table whose
/// purpose is that mapping. The audit row is a record after the fact, not a
/// limit — so the limit is the shape of this struct.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Preview {
    /// The control plane accepted the reality — it exists and takes commands.
    ///
    /// **`true` by construction on this path**, and said out loud because a
    /// field that cannot vary must not be reported as if it were a
    /// measurement. The bind genuinely can fail — proven live against a frozen
    /// reality — but a failure returns `Err`, so a `Preview` only ever exists
    /// on the far side of a passing bind. It is here to record that the check
    /// RAN, not to carry its result.
    pub reality_accepts_commands: bool,
    /// The actor has a durable identity in this reality's registry. This one
    /// really does vary, and it is the finding that changes what an operator
    /// does next.
    pub actor_exists: bool,
    /// Is the driver slot already TAKEN? `RA3`.
    ///
    /// **A bool, and the type is the access-control decision.** The audited read
    /// behind it returns a `user_ref_id`; the PO ruled that a preview may report
    /// whether the slot is free but must not name who holds it, and the way to
    /// honour that is to make the id unrepresentable here rather than to
    /// remember not to print it. A future edit that wanted to leak the holder
    /// would have to change this type, which is a reviewable act; forgetting a
    /// redaction is not.
    pub actor_is_driven: bool,
}

/// Bind the reality through the control plane, or refuse.
///
/// [`dp::RealityId`] has NO public constructor — it is only ever the output of
/// `SessionContext::bind`, so holding one is proof the control plane confirmed
/// the reality exists and ACCEPTS COMMANDS. `MetaControlPlane` refuses
/// `Provisioning`, `Frozen`, `Archived`, `SoftDeleted` and `Dropped`.
///
/// That is why this is not a naming exercise. Granting a human control of an
/// actor in a FROZEN reality is exactly what should not happen, and before the
/// bind existed this code could not even ask the question.
pub async fn bind_reality(
    meta: &PgPool,
    allowlist_path: &str,
    reality_id: Uuid,
) -> Result<dp::RealityId, ProvisionerError> {
    let reader = meta_rs::sqlx_pg::PgConnectionReader::new(meta.clone())
        .map_err(|e| ProvisionerError::Bridge(format!("meta reader: {e}")))?;
    let store = meta_rs::sqlx_pg::PgCapabilityStore::new(
        meta.clone(),
        meta_rs::allowlist::Allowlist::load(allowlist_path)
            .map_err(|e| ProvisionerError::Bridge(format!("allowlist: {e}")))?,
        meta_rs::metawrite::Actor {
            actor_type: meta_rs::metawrite::ActorType::System,
            id: "world-service".to_string(),
            svid: None,
        },
    )
    .map_err(|e| ProvisionerError::Bridge(format!("capability store: {e}")))?;
    let plane = meta_rs::control_plane::MetaControlPlane::new(
        meta_rs::routing::DefaultMetaRead::new(reader),
        store,
    );
    let service = dp::ServiceIdentity::new("world-service")
        .ok_or_else(|| ProvisionerError::Bridge("service identity".to_string()))?;
    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|_| ProvisionerError::Bridge("clock before the epoch".to_string()))?
        .as_millis() as u64;
    let ctx = dp::SessionContext::bind(
        &plane,
        dp::BindRequest { reality: reality_id, node: "world-service".to_string(), service },
        now_ms,
    )
    .map_err(|e| classify_bind_failure(reality_id, e))?;
    Ok(ctx.reality_id().to_owned())
}

/// Split a bind refusal into "the world is closed" and "we are broken".
///
/// **Both come back from the same call, and the first version of this code
/// reported them identically.** The live smoke found it immediately: the dev
/// meta database was missing migration `039`, and
/// `relation "session_registry" does not exist` reached an operator as
/// *"REFUSED — reload and decide"*, with `conflict: true`. That is an outage
/// wearing the costume of a normal answer, and it invites someone to go looking
/// for a reality that is doing exactly what it was told.
///
/// The split is a real one, made upstream:
///
/// * [`dp::DpError::RealityMismatch`] is what `MetaControlPlane` raises when
///   `routing.accepts_commands()` is false — frozen, archived, soft-deleted,
///   dropped, provisioning. A statement about the WORLD; the caller can act.
/// * [`dp::DpError::ControlPlaneUnavailable`] is every read that failed —
///   an unreachable store, a missing table, a bad allowlist. Ours.
///
/// This is exactly the distinction [`ProvisionerError::ActorAlreadyDriven`]
/// exists as its own variant to preserve, and it was lost one layer up.
fn classify_bind_failure(reality_id: Uuid, e: dp::DpError) -> ProvisionerError {
    match e {
        dp::DpError::RealityMismatch { .. } => {
            ProvisionerError::RealityClosed(reality_id.to_string(), e.to_string())
        }
        other => ProvisionerError::Bridge(format!("control plane: {other}")),
    }
}

/// Open a pool on the reality's own database.
///
/// Per call rather than cached: this is a control-plane operation taken once
/// per grant, not a hot path, and a pool cache keyed by reality is state with a
/// lifecycle nobody has designed. When it becomes a hot path it should be
/// cached deliberately, with an eviction rule, rather than by accident now.
pub async fn open_reality_pool(
    meta: &PgPool,
    cfg: &EffectsConfig,
    reality: &dp::RealityId,
) -> Result<PgPool, ProvisionerError> {
    let reality_id = reality.as_uuid();
    let reg = existing_registration(meta, reality_id)
        .await?
        .ok_or_else(|| ProvisionerError::NotFound(reality_id.to_string()))?;

    // Built from OPTIONS, not from `format!("postgres://{user}:{pass}@…")`.
    //
    // The string form is what this code inherited, and it is wrong for a value
    // nobody controls: a password containing `@`, `/`, `?` or `#` silently
    // produces a DSN that parses into a DIFFERENT host and database, and the
    // failure surfaces as an authentication error against a server the
    // operator never named. `PgConnectOptions` takes the parts as parts, so
    // there is no escaping to get right and no string for a secret to leak
    // into. The one copy this replaces is gone; the remaining copies belong to
    // the provisioner and are that track's to fix.
    let (host, port) = split_hostport(&cfg.shard_hostport)?;
    let opts = sqlx::postgres::PgConnectOptions::new()
        .host(host)
        .port(port)
        .username(&cfg.pg_user)
        .password(&cfg.pg_pass)
        .database(&reg.db_name)
        .ssl_mode(sqlx::postgres::PgSslMode::Disable);

    PgPool::connect_with(opts).await.map_err(|e| {
        // Log the reality, never the connection details.
        error!(error = %e, %reality_id, "reality pool connect failed");
        ProvisionerError::Bridge(format!("could not reach the database for reality {reality_id}"))
    })
}

/// Split `host:port`, defaulting to 5432 when the port is absent.
///
/// `rsplit_once` rather than `split_once`: an IPv6 literal is full of colons,
/// and splitting on the FIRST one turns `[::1]:5432` into host `[` — a lookup
/// that fails with a name resolution error naming a bracket.
fn split_hostport(hostport: &str) -> Result<(&str, u16), ProvisionerError> {
    match hostport.rsplit_once(':') {
        None => Ok((hostport, 5432)),
        Some((host, port)) => {
            let port = port.parse::<u16>().map_err(|_| {
                ProvisionerError::Bridge(format!(
                    "shard hostport {hostport:?} does not end in a port number"
                ))
            })?;
            Ok((host, port))
        }
    }
}

/// Create (or adopt) an actor in a reality.
///
/// `entity_id` absent means the registry ALLOCATES — the normal path, and the
/// reason the registry is the SSOT for that number. Supplying one ADOPTS an
/// entity the island already has (the spine's hardcoded `EntityId(1..3)`),
/// which is the case that would otherwise make every existing island undrivable
/// by this feature.
pub async fn create_actor(
    meta: &PgPool,
    cfg: &EffectsConfig,
    reality_id: Uuid,
    entity_id: Option<i64>,
) -> Result<ActorRow, ProvisionerError> {
    let reality = bind_reality(meta, &cfg.meta_allowlist, reality_id).await?;
    let pool = open_reality_pool(meta, cfg, &reality).await?;
    match entity_id {
        None => actor_registry::create_actor(&pool, &reality).await,
        Some(e) => actor_registry::adopt_actor(&pool, &reality, e).await,
    }
}

/// Preview a grant without writing: bind the reality, check the actor exists.
///
/// See [`Preview`] for the fact this deliberately does not gather.
pub async fn preview_grant(
    meta: &PgPool,
    cfg: &EffectsConfig,
    reality_id: Uuid,
    actor_id: Uuid,
) -> Result<Preview, ProvisionerError> {
    let reality = bind_reality(meta, &cfg.meta_allowlist, reality_id).await?;
    let pool = open_reality_pool(meta, cfg, &reality).await?;
    let actor_exists = actor_registry::actor_exists(&pool, &reality, actor_id).await?;
    // `RA3` — the audited read, reduced to a bool AT THE BOUNDARY.
    //
    // Only asked when the actor exists: an actor with no registry row cannot
    // have a live binding, so the read would be a guaranteed miss, and a
    // sensitive read taken for a question already answered is a probe with no
    // purpose. The audit row would still be written, which is precisely why not
    // taking it matters.
    let actor_is_driven = if actor_exists {
        current_driver(cfg, reality_id, actor_id).await?.is_some()
    } else {
        false
    };
    Ok(Preview { reality_accepts_commands: true, actor_exists, actor_is_driven })
}

/// Grant a user control of an actor.
///
/// Fails with [`ProvisionerError::ActorAlreadyDriven`] when someone else holds
/// the live binding — never an idempotent success, because "you have it now" is
/// false when another human does.
pub async fn grant(
    meta: &PgPool,
    cfg: &EffectsConfig,
    user_ref_id: Uuid,
    reality_id: Uuid,
    actor_id: Uuid,
    reason: &str,
) -> Result<Outcome, ProvisionerError> {
    // THE ACTOR MUST EXIST. `034` left `actor_id` unconstrained because its FK
    // lives in another database — a correct reason to have no foreign key and a
    // bad reason to skip the check. This process can reach both databases, so
    // it is the one place the check can happen at the write edge instead of
    // being discovered by a resolver at turn time.
    let reality = bind_reality(meta, &cfg.meta_allowlist, reality_id).await?;
    let pool = open_reality_pool(meta, cfg, &reality).await?;
    if !actor_registry::actor_exists(&pool, &reality, actor_id).await? {
        return Err(ProvisionerError::UnknownActor(actor_id.to_string(), reality_id.to_string()));
    }
    let granted = bridge(cfg)
        .grant_actor_control(user_ref_id, reality_id, actor_id, reason)
        .await?;
    Ok(if granted { Outcome::Granted } else { Outcome::AlreadyGranted })
}

/// Revoke control of an actor.
///
/// **Deliberately does NOT bind the reality**, unlike [`grant`]. Refusing to
/// revoke a driver in a FROZEN world would strand a player as the driver of a
/// reality under maintenance — the opposite of the harm the bind prevents on
/// the grant side. Revoke is the safe direction and stays available.
///
/// It also does not check the actor exists: the binding is the subject here,
/// and a binding pointing at an actor the registry lost is precisely the
/// dangling row an operator most needs to be able to clear.
///
/// **It DOES check the reality is registered**, and that is not the bind coming
/// back in another form. Without it, a typo in `--reality-id` found no live
/// binding and returned `AlreadyRevoked` — which `admin` printed as *"was
/// ALREADY in the requested state. Nothing was written."* **A tier-1 command
/// whose entire purpose is to take a character away, reporting success for a
/// world that does not exist**, while the real driver kept driving. Measured
/// against the live stack, not reasoned about. A registry lookup answers
/// "does this world exist" without asking "does it accept commands", so the
/// frozen-world asymmetry above survives intact.
pub async fn revoke(
    meta: &PgPool,
    cfg: &EffectsConfig,
    reality_id: Uuid,
    actor_id: Uuid,
    expected_user_ref_id: Option<Uuid>,
    reason: &str,
) -> Result<Outcome, ProvisionerError> {
    if existing_registration(meta, reality_id).await?.is_none() {
        return Err(ProvisionerError::NotFound(reality_id.to_string()));
    }
    let revoked = bridge(cfg)
        .revoke_actor_control(reality_id, actor_id, expected_user_ref_id, reason)
        .await?;
    Ok(if revoked { Outcome::Revoked } else { Outcome::AlreadyRevoked })
}

/// Who currently drives this actor — `None` when nobody does.
///
/// `RA2`. The flow-level door to the audited cross-user read, and the reason
/// [`Preview`] can stay silent about the holder without that silence being
/// permanent: the capability now EXISTS. Whether an operator gets it is `RA3`,
/// a separate decision, because building the pipe and opening it to everyone
/// with `admin:write` are different acts.
///
/// It does **not** bind the reality, for the same reason [`revoke`] does not:
/// asking who drives an actor in a frozen world is a legitimate question — very
/// often the FIRST question, when working out why a world was frozen — and
/// refusing it would make the read useless in exactly the situation that needs
/// it.
///
/// Every call writes a `meta_read_audit` row on the far side. That is not a
/// side effect to be optimised away; it is what makes the read permissible.
pub async fn current_driver(
    cfg: &EffectsConfig,
    reality_id: Uuid,
    actor_id: Uuid,
) -> Result<Option<Uuid>, ProvisionerError> {
    bridge(cfg).read_actor_control(reality_id, actor_id).await
}

/// What a user drives, both spellings of it.
///
/// Two ids because the two tiers name an actor differently and the caller needs
/// the island's one. `actor_id` rides along because this is the caller's OWN
/// binding — no cross-user disclosure — and it is the durable id an operator
/// greps for when someone reports the wrong character. Returning only
/// `entity_id` would make that question answerable only by a CROSS-USER read,
/// which is the expensive, audited one.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Subject {
    /// The PLATFORM identity — what `actor_control_binding.actor_id` holds.
    pub actor_id: Uuid,
    /// The ISLAND identity — what the simulation acts on.
    pub entity_id: i64,
}

/// `E1` — which actor does THIS user drive in THIS reality? `None` = nobody.
///
/// The OWNER-SCOPED half of the pair. [`current_driver`] asks *"who drives this
/// actor"* — cross-user, audited, through the Go bridge. This asks *"which
/// actor do I drive"*, which is a question about yourself: unaudited by the
/// same reasoning the GDPR erasure cascade's owner-scoped read is, and the
/// sensitive-path contract says so in the `!=` of its own description.
///
/// # The order of the three checks is the design
///
/// **1 · Is the reality registered?** Before anything else, and for the reason
/// `revoke` learned the hard way: without it a typo'd `reality_id` finds no
/// binding and comes back as *"you drive nobody"* — a confident answer about a
/// world that does not exist. Same mistake, same shape, caught here before it
/// could ship twice.
///
/// **2 · Is there a live binding?** If not, `Ok(None)` and we stop. Nobody
/// drives anybody, and there is nothing in the per-reality database to ask
/// about — so a spectator costs one meta read and never opens a second pool.
///
/// **3 · Only then, the reality.** Hop 2 needs `actors`, which lives in the
/// per-reality database, and reaching it needs a [`dp::RealityId`] — which has
/// no public constructor and can only come from a passing `bind_reality`. That
/// is not a formality to route around: **a driver in a FROZEN reality gets
/// `RealityClosed`, not their entity id.** The alternative was a bypass
/// constructor, and the guarantee `dp::RealityId` carries — *"if you are
/// holding one, the control plane approved this"* — is worth more than a nicer
/// answer during maintenance. Telling a player which entity they drive in a
/// world that refuses commands is a promise the next call breaks anyway.
pub async fn resolve_subject(
    meta: &PgPool,
    cfg: &EffectsConfig,
    reality_id: Uuid,
    user_ref_id: Uuid,
) -> Result<Option<Subject>, ProvisionerError> {
    if existing_registration(meta, reality_id).await?.is_none() {
        return Err(ProvisionerError::NotFound(reality_id.to_string()));
    }

    // Hop 1 — META, through the ONE sanctioned Rust reader. The predicates that
    // make it owner-scoped are asserted on the executed string in `meta-rs`;
    // see `meta_rs::actor_binding::OWNER_SCOPED_SQL`.
    let Some(actor_id) =
        meta_rs::actor_binding::live_binding_actor(meta, reality_id, user_ref_id).await?
    else {
        return Ok(None);
    };

    // Hop 2 — PER-REALITY. `S-9`'s conversion site.
    let reality = bind_reality(meta, &cfg.meta_allowlist, reality_id).await?;
    let pool = open_reality_pool(meta, cfg, &reality).await?;
    let Some(entity_id) = actor_registry::entity_id_for(&pool, &reality, actor_id).await? else {
        // NOT `Ok(None)`. A live binding naming an actor the registry does not
        // have is the dangling pointer `S-9` describes, and reporting it as
        // "you drive nobody" would render a data defect as an ordinary
        // spectator — the player silently demoted, nobody paged.
        return Err(ProvisionerError::UnknownActor(actor_id.to_string(), reality_id.to_string()));
    };
    // The same rule the write edge applies, from the same function — a row
    // that predates `adopt_actor`'s guard must not reach the transport as a
    // valid subject. See `actor_registry::checked_island_id`.
    let entity_id = actor_registry::checked_island_id(&reality, entity_id)?;
    Ok(Some(Subject { actor_id, entity_id }))
}

fn bridge(cfg: &EffectsConfig) -> BridgeClient {
    BridgeClient::new(cfg.bridge_url.clone(), cfg.bridge_token.clone())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The four words are the wire contract shared by the HTTP response and the
    /// worker's stdout JSON. Asserted as literals, because a rename here is
    /// invisible to the compiler and would silently change what an operator's
    /// script matches on.
    #[test]
    fn the_outcome_words_are_stable() {
        assert_eq!(Outcome::Granted.as_str(), "granted");
        assert_eq!(Outcome::AlreadyGranted.as_str(), "already_granted");
        assert_eq!(Outcome::Revoked.as_str(), "revoked");
        assert_eq!(Outcome::AlreadyRevoked.as_str(), "already_revoked");
    }

    /// The hostport splitter, including the two cases that made it worth
    /// writing instead of `split_once`.
    ///
    /// This exists because the DSN it replaced was built by `format!`, and a
    /// password containing `@` produced a connection string that parsed into a
    /// different host — an authentication failure against a server nobody
    /// named. Moving to `PgConnectOptions` removed the escaping problem and
    /// introduced exactly one thing to get wrong, which is this.
    #[test]
    fn the_hostport_split_survives_a_bare_host_and_an_ipv6_literal() {
        assert_eq!(split_hostport("db.internal:6543").unwrap(), ("db.internal", 6543));
        // No port at all — Postgres' default, not an error.
        assert_eq!(split_hostport("db.internal").unwrap(), ("db.internal", 5432));
        // `rsplit_once`, not `split_once`. Splitting on the FIRST colon makes
        // the host `[` and the "port" `:1]:5432` — a resolution failure naming
        // a bracket, from a config file that was correct.
        assert_eq!(split_hostport("[::1]:5432").unwrap(), ("[::1]", 5432));
        // A trailing garbage port is refused BY NAME rather than silently
        // defaulting to 5432, which would connect to the wrong server on a
        // host that happens to run two.
        let e = split_hostport("db.internal:not-a-port").unwrap_err();
        assert!(
            e.to_string().contains("does not end in a port number"),
            "a malformed port must be named, got {e}"
        );
    }

    /// A closed world and a broken control plane must not read alike.
    ///
    /// This test exists because the code failed it. The first version mapped
    /// EVERY bind failure to `RealityClosed`, and the live smoke printed
    /// `relation "session_registry" does not exist` as *"REFUSED — this is a
    /// statement about the world, not a failure; reload and decide"*. Both
    /// directions are asserted: a classifier that returned `Bridge` for
    /// everything would silence the first half, and one that returned
    /// `RealityClosed` for everything is the bug itself.
    #[test]
    fn a_frozen_world_and_a_broken_control_plane_are_different_answers() {
        let r = Uuid::new_v4();

        let closed = classify_bind_failure(
            r,
            dp::DpError::RealityMismatch {
                ctx: r.to_string(),
                requested: "status Frozen does not accept commands".to_string(),
            },
        );
        assert!(
            matches!(closed, ProvisionerError::RealityClosed(_, _)),
            "a reality that refuses commands is the WORLD's answer, got {closed:?}"
        );

        for ours in [
            dp::DpError::ControlPlaneUnavailable { reason: "session_registry missing".into() },
            dp::DpError::CapabilityExpired,
        ] {
            let got = classify_bind_failure(r, ours);
            assert!(
                matches!(got, ProvisionerError::Bridge(_)),
                "a fault on OUR side must not be reported as a closed world, got {got:?}"
            );
        }
    }

    /// Non-vacuity, both directions. A `changed()` that returned `true` for
    /// everything would pass a test asserting only the two changing cases —
    /// and would make `admin reality grant-control` report a write on a
    /// re-run that wrote nothing.
    #[test]
    fn only_the_two_changing_outcomes_report_a_change() {
        assert!(Outcome::Granted.changed());
        assert!(Outcome::Revoked.changed());
        assert!(!Outcome::AlreadyGranted.changed(), "a no-op grant must not report a write");
        assert!(!Outcome::AlreadyRevoked.changed(), "a no-op revoke must not report a write");
    }
}
