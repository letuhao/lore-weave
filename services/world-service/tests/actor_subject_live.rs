//! `E5` — the owner-scoped subject route, live, against two real databases.
//!
//! # Why this exists rather than trusting `E1`'s unit tests
//!
//! `E1` shipped with seven bites and a five-arm smoke, and the smoke ran from a
//! scratchpad script against data an earlier slice happened to leave in the dev
//! stack. That is a proof nobody can repeat — tracked as `EO-2` — and a route
//! whose only live evidence is one unrepeatable run is the shape
//! `meta_read_audit` was in for four months: four layers, each correct-looking,
//! and an empty table underneath.
//!
//! # What only a live run can show
//!
//! The resolution spans **two databases in different tiers** — the binding in
//! META (a human exists across realities) and `actors` in the PER-REALITY shard
//! (an `EntityId` is *"identity within a reality"*). A mock of either is a mock
//! of the exact seam `S-9` recorded as having zero conversion sites. And the
//! bind that guards hop 2 goes through the real `MetaControlPlane`, so
//! `dp::RealityId` is minted here the way production mints it and no other way.
//!
//! Driven through the ROUTER, not the flow function: that puts the handler, the
//! `X-Internal-Token` gate, the status codes and the `self` wire key inside the
//! same proof.
//!
//! Gated on `SUBJECT_ROUTE_META_TEST_DATABASE_URL` +
//! `SUBJECT_ROUTE_CHANNEL_TEST_DATABASE_URL`;
//! `scripts/live-suites.py --only world-actor-subject` provisions both. Skips
//! LOUDLY when absent — a live test that passes quietly with no stack is worse
//! than one that was never written.

use axum::body::Body;
use axum::http::{Request, StatusCode};
use sqlx::postgres::PgPoolOptions;
use tower::ServiceExt;
use uuid::Uuid;
use world_service::server::{build_router, AppState, Config};

const META_DSN_VAR: &str = "SUBJECT_ROUTE_META_TEST_DATABASE_URL";
const CHANNEL_DSN_VAR: &str = "SUBJECT_ROUTE_CHANNEL_TEST_DATABASE_URL";
const TOKEN: &str = "actor-subject-live-token";

/// Refuse a DSN whose database name does not announce itself as disposable.
///
/// Runs BEFORE anything touches the server. This fixture INSERTs, and the rule
/// it obeys is the one an unscoped `DELETE FROM books` broke once against the
/// real book database.
fn guarded(var: &str) -> Option<String> {
    let raw = std::env::var(var).ok()?;
    let db = raw.rsplit('/').next().unwrap_or("").split('?').next().unwrap_or("");
    assert!(
        ["test", "smoke", "scratch", "throwaway", "sandbox"].iter().any(|m| db.contains(m)),
        "{var} points at `{db}`, which carries no throwaway marker"
    );
    Some(raw)
}

/// `host:port`, `user` and `password` out of a DSN, for the effects config.
///
/// `open_reality_pool` builds its connection from `PROVISION_SHARD_HOSTPORT` +
/// `PROVISION_PG_USER` + the registry's `db_name`, NOT from a whole DSN — so
/// the test has to hand it the parts, and they must be the parts that reach the
/// same server the channel DSN names, or hop 2 connects somewhere else.
fn parts_of(dsn: &str) -> (String, String, String, String) {
    let rest = dsn.split("://").nth(1).unwrap_or(dsn);
    let (creds, hostpath) = rest.split_once('@').unwrap_or(("postgres:postgres", rest));
    let (user, pass) = creds.split_once(':').unwrap_or((creds, ""));
    let hostport = hostpath.split('/').next().unwrap_or("127.0.0.1:5432");
    let db = hostpath.split('/').nth(1).unwrap_or("").split('?').next().unwrap_or("");
    (hostport.to_string(), user.to_string(), pass.to_string(), db.to_string())
}

fn state(meta: sqlx::PgPool, meta_dsn: &str, chan_dsn: &str) -> AppState {
    let (hostport, user, pass, _) = parts_of(chan_dsn);
    let config = Config::from_lookup(|k| {
        Some(
            match k {
                "LOREWEAVE_INTERNAL_TOKEN" => TOKEN.to_string(),
                "PROVISION_META_DSN" => meta_dsn.to_string(),
                "PROVISION_SHARD_ADMIN_DSN" => chan_dsn.to_string(),
                // The route NEVER calls the bridge — resolving a subject is two
                // reads. A real URL here would be a dependency the code under
                // test does not have, and pretending otherwise would hide it.
                "PROVISION_BRIDGE_URL" => "http://127.0.0.1:1".to_string(),
                "PROVISION_BRIDGE_TOKEN" => "unused".to_string(),
                "PROVISION_SHARD_HOSTPORT" => hostport.clone(),
                "PROVISION_PG_USER" => user.clone(),
                "PROVISION_PG_PASSWORD" => pass.clone(),
                // ABSOLUTE, and it has to be. The default
                // (`contracts/meta/events_allowlist.yaml`) is relative to the
                // CWD, and `cargo test` runs from the PACKAGE directory while
                // the binary runs from the repo root — so the bind failed here
                // with a generic 500 while the same code worked from a shell.
                // `CARGO_MANIFEST_DIR` is the only fixed point a test has.
                "PROVISION_META_ALLOWLIST" => format!(
                    "{}/../../contracts/meta/events_allowlist.yaml",
                    env!("CARGO_MANIFEST_DIR").replace('\\', "/")
                ),
                _ => return None,
            },
        )
    })
    .expect("config");
    AppState::new(meta.clone(), meta, &config)
}

async fn ask(
    state: &AppState,
    reality_id: Uuid,
    user_ref_id: Uuid,
    token: &str,
) -> (StatusCode, serde_json::Value) {
    let resp = build_router(state.clone())
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/internal/v1/actor-control/subject")
                .header("content-type", "application/json")
                .header("X-Internal-Token", token)
                .body(Body::from(
                    serde_json::json!({ "reality_id": reality_id, "user_ref_id": user_ref_id })
                        .to_string(),
                ))
                .unwrap(),
        )
        .await
        .expect("router");
    let status = resp.status();
    let bytes = axum::body::to_bytes(resp.into_body(), 1 << 20).await.expect("body");
    let json = serde_json::from_slice(&bytes).unwrap_or(serde_json::Value::Null);
    (status, json)
}

#[tokio::test(flavor = "multi_thread")]
async fn a_bound_user_resolves_and_a_revoked_one_does_not() -> Result<(), Box<dyn std::error::Error>>
{
    let (Some(meta_dsn), Some(chan_dsn)) = (guarded(META_DSN_VAR), guarded(CHANNEL_DSN_VAR)) else {
        eprintln!(
            "SKIP actor_subject_live — live infra unavailable: set {META_DSN_VAR} and \
             {CHANNEL_DSN_VAR}, or run scripts/live-suites.py --only world-actor-subject"
        );
        return Ok(());
    };

    let meta = PgPoolOptions::new().max_connections(4).connect(&meta_dsn).await?;
    let reality_pool = PgPoolOptions::new().max_connections(4).connect(&chan_dsn).await?;
    let (_, _, _, chan_db) = parts_of(&chan_dsn);

    // Fresh ids per run, so two runs cannot collide and no cleanup is needed
    // between them. Every statement below is SCOPED to these — there is no bare
    // `DELETE FROM` anywhere in this file.
    let reality_id = Uuid::new_v4();
    let actor_id = Uuid::new_v4();
    let driver = Uuid::new_v4();
    let revoked_user = Uuid::new_v4();
    let stranger = Uuid::new_v4();
    let entity_id: i64 = 4242;

    // ── the reality must be REGISTERED and ACTIVE, or the bind refuses ──
    //
    // `db_name` is the channel database this test is connected to, because that
    // is the half of the row hop 2 uses. Writing anything else would send the
    // second hop to a database that does not exist and the failure would read
    // like a code defect.
    //
    // `db_host` is NOT where anything connects, and the schema says so: a
    // `CHECK` pins it to `^pg-shard-[0-9]+\.(internal|prod|staging)$`, so it is
    // a LOGICAL shard name. `open_reality_pool` builds its connection from
    // `PROVISION_SHARD_HOSTPORT` instead. Learned by putting `localhost` here
    // and watching the constraint refuse it — which is the constraint doing its
    // job, since a real hostname in this column would be a second, silently
    // wrong answer to "where does this reality live".
    sqlx::query(
        "INSERT INTO reality_registry \
           (reality_id, db_host, db_name, status, locale, session_max_pcs, \
            session_max_npcs, session_max_total, deploy_cohort) \
         VALUES ($1, 'pg-shard-0.internal', $2, 'active', 'en-US', 8, 32, 40, 0)",
    )
    .bind(reality_id)
    .bind(&chan_db)
    .execute(&meta)
    .await?;

    sqlx::query("INSERT INTO actors (reality_id, actor_id, entity_id) VALUES ($1, $2, $3)")
        .bind(reality_id)
        .bind(actor_id)
        .bind(entity_id)
        .execute(&reality_pool)
        .await?;

    // Two bindings on the SAME actor: one live, one revoked. That pair is the
    // whole point — a resolver that ignored `revoked_at` answers identically
    // for both, and no assertion over a SQL string can show that it does not.
    sqlx::query(
        "INSERT INTO actor_control_binding (user_ref_id, reality_id, actor_id) VALUES ($1, $2, $3)",
    )
    .bind(driver)
    .bind(reality_id)
    .bind(actor_id)
    .execute(&meta)
    .await?;
    sqlx::query(
        "INSERT INTO actor_control_binding (user_ref_id, reality_id, actor_id, revoked_at) \
         VALUES ($1, $2, $3, now())",
    )
    .bind(revoked_user)
    .bind(reality_id)
    .bind(actor_id)
    .execute(&meta)
    .await?;

    let st = state(meta.clone(), &meta_dsn, &chan_dsn);

    // ── 1 · the driver resolves, through both hops ──────────────────────────
    let (status, body) = ask(&st, reality_id, driver, TOKEN).await;
    assert_eq!(status, StatusCode::OK, "driver lookup: {body}");
    let self_ = &body["self"];
    assert!(!self_.is_null(), "the driver must resolve to an actor: {body}");
    assert_eq!(self_["actor_id"].as_str(), Some(actor_id.to_string().as_str()), "{body}");
    assert_eq!(
        self_["entity_id"].as_i64(),
        Some(entity_id),
        "hop 2 must convert the actor to the ISLAND id: {body}"
    );

    // ── 2 · the revoked user, on the SAME actor, drives nobody ──────────────
    let (status, body) = ask(&st, reality_id, revoked_user, TOKEN).await;
    assert_eq!(status, StatusCode::OK, "a revoked binding is a normal answer: {body}");
    assert!(
        body["self"].is_null(),
        "`revoked_at IS NULL` did not hold — a revoked binding is history, not authority: {body}"
    );

    // ── 3 · a user with no binding at all ───────────────────────────────────
    let (status, body) = ask(&st, reality_id, stranger, TOKEN).await;
    assert_eq!(status, StatusCode::OK);
    assert!(body["self"].is_null(), "a stranger drives nobody: {body}");

    // ── 4 · an UNREGISTERED reality is a 400, never "you drive nobody" ──────
    //
    // Answering `self: null` about a world that does not exist is the bug the
    // revoke path shipped once: a tier-1 command reporting success for a typo.
    let (status, body) = ask(&st, Uuid::new_v4(), driver, TOKEN).await;
    assert_eq!(status, StatusCode::BAD_REQUEST, "a typo'd reality must not read as spectating: {body}");

    // ── 5 · the gate is a gate ──────────────────────────────────────────────
    let (status, _) = ask(&st, reality_id, driver, "not-the-token").await;
    assert_eq!(status, StatusCode::UNAUTHORIZED, "the route must stay internal-gated");

    Ok(())
}
