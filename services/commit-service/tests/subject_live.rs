//! `SEALED-SUBJECT`, live — a granted user drives, a revoked one is refused.
//!
//! The unit suites prove admission cannot be told who is acting. They cannot
//! prove the two-hop resolution actually works, because it spans **two
//! databases in different tiers**: `actor_control_binding` in META (a human
//! exists across realities) and `actors` in the PER-REALITY shard (an
//! `EntityId` is *"identity within a reality"*). A mock of either would be a
//! mock of the exact seam `S-9` recorded as having zero conversion sites.
//!
//! Gated on `SUBJECT_META_TEST_DATABASE_URL` + `SUBJECT_CHANNEL_TEST_DATABASE_URL`;
//! `scripts/live-suites.py --only commit-subject` provisions both. Skips loudly
//! when absent — a live test that passes quietly with no stack is worse than
//! one that is not written.

mod support;

use commit_service::subject::{resolve_subject, SubjectError};
use sqlx::postgres::PgPoolOptions;
use uuid::Uuid;

const META_DSN_VAR: &str = "SUBJECT_META_TEST_DATABASE_URL";
const CHANNEL_DSN_VAR: &str = "SUBJECT_CHANNEL_TEST_DATABASE_URL";

/// Refuse a DSN whose database name does not announce itself as disposable.
///
/// Runs BEFORE anything touches the server. This fixture INSERTs and DELETEs,
/// and the rule it obeys is the one an unscoped `DELETE FROM books` broke once
/// against the real book database.
fn guarded(var: &str) -> Option<String> {
    let raw = std::env::var(var).ok()?;
    let db = raw.rsplit('/').next().unwrap_or("").split('?').next().unwrap_or("");
    assert!(
        ["test", "smoke", "scratch", "throwaway", "sandbox"].iter().any(|m| db.contains(m)),
        "{var} points at `{db}`, which carries no throwaway marker"
    );
    Some(raw)
}

#[tokio::test(flavor = "multi_thread")]
async fn a_granted_user_drives_and_a_revoked_one_is_refused() -> anyhow::Result<()> {
    let (Some(meta_dsn), Some(chan_dsn)) = (guarded(META_DSN_VAR), guarded(CHANNEL_DSN_VAR)) else {
        eprintln!(
            "SKIP subject_live — live infra unavailable: set {META_DSN_VAR} and \
             {CHANNEL_DSN_VAR}, or run scripts/live-suites.py --only commit-subject"
        );
        return Ok(());
    };

    let meta = PgPoolOptions::new().max_connections(2).connect(&meta_dsn).await?;
    let reality_pool = PgPoolOptions::new().max_connections(2).connect(&chan_dsn).await?;

    // Fresh ids per run, so two runs cannot collide and no cleanup is needed
    // between them. Every statement below is SCOPED to these — there is no
    // bare `DELETE FROM` anywhere in this file.
    let reality_id = Uuid::new_v4();
    // A verified id through the SAME control-plane double the other live
    // suites use (`tests/support`). `dp::RealityId` has no public
    // constructor, which is the property that makes it worth holding; a test
    // gets one the way production does, through a bind.
    let reality = support::verified_reality(reality_id);
    let user = Uuid::new_v4();
    let stranger = Uuid::new_v4();
    let actor_id = Uuid::new_v4();
    const ENTITY: i64 = 4242;

    // ── the registry: the actor exists, with both identities ────────────────
    sqlx::query("INSERT INTO actors (reality_id, actor_id, entity_id) VALUES ($1, $2, $3)")
        .bind(reality_id)
        .bind(actor_id)
        .bind(ENTITY)
        .execute(&reality_pool)
        .await?;

    // ── before any grant: this user drives nobody ───────────────────────────
    //
    // Asserted FIRST so the pass below cannot be a false positive from a row
    // some earlier run left behind.
    match resolve_subject(&meta, &reality_pool, &reality, user).await {
        Err(SubjectError::NoLiveBinding { .. }) => {}
        other => panic!("expected NoLiveBinding before the grant, got {other:?}"),
    }

    // ── GRANT ───────────────────────────────────────────────────────────────
    sqlx::query(
        "INSERT INTO actor_control_binding (user_ref_id, reality_id, actor_id) VALUES ($1, $2, $3)",
    )
    .bind(user)
    .bind(reality_id)
    .bind(actor_id)
    .execute(&meta)
    .await?;

    let resolved = resolve_subject(&meta, &reality_pool, &reality, user).await;
    assert_eq!(
        resolved.as_ref().ok().copied(),
        Some(ENTITY as u64),
        "a GRANTED user must resolve to the island entity they drive, got {resolved:?}"
    );
    println!("GRANTED   user {user} -> EntityId({ENTITY})");

    // ── a stranger with no binding still drives nobody ──────────────────────
    //
    // The grant is per USER, not per reality: one live binding must not make
    // the reality drivable by anyone who asks.
    match resolve_subject(&meta, &reality_pool, &reality, stranger).await {
        Err(SubjectError::NoLiveBinding { .. }) => {}
        other => panic!("a stranger resolved to something: {other:?}"),
    }
    println!("STRANGER  user {stranger} -> refused (no live binding)");

    // ── REVOKE ──────────────────────────────────────────────────────────────
    let revoked = sqlx::query(
        "UPDATE actor_control_binding SET revoked_at = now() \
          WHERE reality_id = $1 AND actor_id = $2 AND revoked_at IS NULL",
    )
    .bind(reality_id)
    .bind(actor_id)
    .execute(&meta)
    .await?;
    assert_eq!(revoked.rows_affected(), 1, "the revoke must have hit the live row");

    match resolve_subject(&meta, &reality_pool, &reality, user).await {
        Err(SubjectError::NoLiveBinding { .. }) => {}
        other => panic!("a REVOKED user still resolved: {other:?}"),
    }
    println!("REVOKED   user {user} -> refused (binding is history)");

    // ── HANDOFF: the actor is drivable again, which `034`'s PK forbade ──────
    //
    // Under `PRIMARY KEY (reality_id, actor_id)` this INSERT was impossible and
    // revoke was terminal. Migration `041` made the uniqueness apply to LIVE
    // rows only; this is that repair, exercised end to end.
    let heir = Uuid::new_v4();
    sqlx::query(
        "INSERT INTO actor_control_binding (user_ref_id, reality_id, actor_id) VALUES ($1, $2, $3)",
    )
    .bind(heir)
    .bind(reality_id)
    .bind(actor_id)
    .execute(&meta)
    .await?;
    assert_eq!(
        resolve_subject(&meta, &reality_pool, &reality, heir).await.ok(),
        Some(ENTITY as u64),
        "after a handoff the new driver must resolve to the same entity"
    );
    println!("HANDOFF   user {heir} -> EntityId({ENTITY})");

    // ── a binding pointing at an actor the registry does not have ───────────
    //
    // `S-9`'s dangling pointer. The grant route refuses to create one, so this
    // is constructed directly to prove the resolver names it rather than
    // returning a wrong subject.
    let ghost_actor = Uuid::new_v4();
    let ghost_user = Uuid::new_v4();
    sqlx::query(
        "INSERT INTO actor_control_binding (user_ref_id, reality_id, actor_id) VALUES ($1, $2, $3)",
    )
    .bind(ghost_user)
    .bind(reality_id)
    .bind(ghost_actor)
    .execute(&meta)
    .await?;
    match resolve_subject(&meta, &reality_pool, &reality, ghost_user).await {
        Err(SubjectError::UnknownActor { actor }) => assert_eq!(actor, ghost_actor),
        other => panic!("a dangling binding did not report UnknownActor: {other:?}"),
    }
    println!("DANGLING  actor {ghost_actor} -> refused (no registry row)");

    // Scoped cleanup — every statement names this run's own ids. No bare
    // DELETE, per the rule and `scripts/db-safety-gate.py`.
    sqlx::query("DELETE FROM actor_control_binding WHERE reality_id = $1")
        .bind(reality_id)
        .execute(&meta)
        .await?;
    sqlx::query("DELETE FROM actors WHERE reality_id = $1")
        .bind(reality_id)
        .execute(&reality_pool)
        .await?;
    Ok(())
}
