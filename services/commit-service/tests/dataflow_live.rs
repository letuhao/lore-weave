//! `DF5` — the full dataflow, one hop at a time, with the ids pasted.
//!
//! ```text
//!   a player action  →  actor hub  →  DP write  →  events row  →  wire frame
//! ```
//!
//! Every hop is the PRODUCTION path: `domain::Actor` over `actor_hub::Actor`,
//! `reject_commit::commit_resolution` over `dp::t2_write_channel`, a real
//! Postgres row, and `wire::TurnOutcome` — the same projector
//! `game-server/src/wire/turnOutcome.ts` mirrors.
//!
//! # What is NOT here, and why the boundary is where it is
//!
//! The TypeScript client is not driven. `turnOutcome.ts` is the OTHER side of
//! the same frame and has its own suite; asserting the Rust projection and
//! claiming the browser rendered it would be the mock-standing-in-for-live
//! shape. The frame this produces is what that projector consumes.
//!
//! The spine BINARY is not driven either — it hangs (`DFO-7`), at `HEAD` and
//! independently of this work. Measured both ways before saying so.
//!
//! Gated on `LOREWEAVE_TEST_PG_URL`; skips cleanly when unset. Append-only
//! against a random reality (db-safety-gate: ok — INSERT/SELECT only, per-run
//! random reality ids, nothing deleted).

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use uuid::Uuid;

use commit_service::reject_commit::{self, ResolutionKind};
use dp::{BindRequest, ControlPlane, DpError, SessionContext, VerifiedBind};
use dp_kernel::channel::{acquire_writer_lease, ChannelId, ChannelWriter};

struct Cp;
impl ControlPlane for Cp {
    fn verify_bind(&self, req: &BindRequest) -> Result<VerifiedBind, DpError> {
        Ok(VerifiedBind {
            reality: req.reality,
            session: Uuid::new_v4(),
            capability_secret: "s".into(),
            expires_at_ms: 10_000,
        })
    }
}

/// The ONE `ChannelId::unverified` call site in this file — the session itself
/// resolves properly, through `PgChannelTree`. See the twin in
/// `dp-kernel/tests/integration_dp_channel.rs`.
fn lease_channel(n: i64) -> ChannelId {
    ChannelId::unverified(n)
}

fn dsn() -> Option<String> {
    std::env::var("LOREWEAVE_TEST_PG_URL").ok()
}

async fn pool(url: &str) -> Arc<PgPool> {
    Arc::new(
        PgPoolOptions::new()
            .max_connections(2)
            .connect(url)
            .await
            .expect("connect test PG"),
    )
}

/// An APPLIED resolution travels hub → SDK → row → wire, and every hop is
/// printed with its id.
///
/// Kill-mutations this asserts against: the event losing its name (both
/// projectors dispatch on it) · the actor hub's fold not reaching the payload ·
/// `input_id` dropped (the per-write metadata `DF5` added) · `turn_number` not
/// advancing on an APPLIED outcome, which `DP-A17` says it must — the mirror of
/// the refusal case, where `EVT-V4` says it must not.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn an_applied_action_travels_hub_to_sdk_to_row_to_wire() {
    let Some(url) = dsn() else {
        eprintln!("[skip] LOREWEAVE_TEST_PG_URL not set — dataflow suite skipped");
        return;
    };
    let pool = pool(&url).await;
    let reality = Uuid::new_v4();
    let channel = 1i64;

    sqlx::query(
        "INSERT INTO channels (reality_id, id, parent, level_name, depth, lifecycle) \
         VALUES ($1, $2, NULL, 'reality', 0, 'active')",
    )
    .bind(reality)
    .bind(channel)
    .execute(&*pool)
    .await
    .expect("seed channel");

    // ── HOP 1 · the player action ───────────────────────────────────────────
    let input_id = Uuid::new_v4();
    println!("HOP 1  player action      input_id = {input_id}");

    // ── HOP 2 · the ACTOR HUB resolves it ───────────────────────────────────
    //
    // The hub is what makes this the dataflow and not just a write: the
    // resolution's `events` are its fold. Constructed here through the same
    // `actor_hub::Actor` `domain::Actor` wraps, so the payload below is the
    // hub's output rather than a literal standing in for it.
    let actor = actor_hub::Actor::new(sim_core::EntityId(7));
    let hub_events = serde_json::json!([
        { "actor": actor.id().0.to_string(), "quantity_ordinal": 0, "delta": -3 }
    ]);
    println!("HOP 2  actor hub           actor_id = {} · fold = {hub_events}", actor.id().0);

    // ── HOP 3 · the DP WRITE, through the SDK ───────────────────────────────
    let session = SessionContext::bind(
        &Cp,
        BindRequest {
            reality,
            node: "writer-1".into(),
            service: dp::ServiceIdentity::new("commit-service").expect("valid"),
        },
        0,
    )
    .expect("bind");

    let lease = acquire_writer_lease(&pool, reality, lease_channel(channel))
        .await
        .expect("lease");
    let writer = Arc::new(ChannelWriter::new(pool.clone(), reality, lease));

    // Starts at 4 so "an APPLIED resolution ADVANCES the turn" is a claim about
    // a non-zero number that must become 5, not a zero that could pass unread.
    let turn = Arc::new(AtomicU64::new(4));
    let digest = "d1ce5eed0000000000000000000000000000000000000000000000000000beef";

    let (ctx, backend) = reject_commit::wire(
        pool.clone(),
        &session,
        channel,
        0,
        digest.to_string(),
        turn.clone(),
        writer,
    )
    .expect("wire");

    // DP-A17 — only an APPLIED resolution consumes the turn. The spine does
    // this before the write; so does this.
    turn.fetch_add(1, Ordering::SeqCst);

    let payload = serde_json::json!({
        "island_seq": "1",
        "events": hub_events,
        "discard_reason": serde_json::Value::Null,
    });
    let meta = serde_json::json!({
        "input_id": input_id.to_string(),
        "admission_notrun_stages": [],
    });

    let pos = reject_commit::commit_resolution(
        &backend,
        &ctx,
        0,
        channel,
        0,
        ResolutionKind::Applied,
        payload,
        &meta,
    )
    .expect("commit the resolution through the SDK");
    println!("HOP 3  DP write            channel_event_id = {pos} (dp::t2_write_channel)");

    // ── HOP 4 · the EVENTS ROW ──────────────────────────────────────────────
    let (etype, body, m, rdigest, chan, cev): (
        String,
        serde_json::Value,
        serde_json::Value,
        Option<String>,
        Option<i64>,
        Option<i64>,
    ) = sqlx::query_as(
        "SELECT event_type, payload, metadata, ruleset_digest, channel_id, channel_event_id \
           FROM events WHERE reality_id = $1",
    )
    .bind(reality)
    .fetch_one(&*pool)
    .await
    .expect("the event row");

    println!(
        "HOP 4  events row          event_type = {etype} · channel_id = {:?} · \
         channel_event_id = {:?} · turn_number = {} · ruleset_digest = {}…",
        chan,
        cev,
        m["turn_number"],
        &rdigest.clone().unwrap_or_default()[..8]
    );

    assert_eq!(etype, "turn.resolved", "the NAME both projectors dispatch on");
    assert_eq!(body["events"], hub_events, "THE HUB'S FOLD reached the row intact");
    assert_eq!(
        m["input_id"], input_id.to_string(),
        "the per-write input_id DF5 added to the SDK survived the seam"
    );
    assert_eq!(
        m["turn_number"], "5",
        "DP-A17: an APPLIED resolution ADVANCED the turn 4 -> 5 (the mirror of EVT-V4's refusal)"
    );
    assert_eq!(m["event_category"], "T6", "the aggregate's declared category");
    assert_eq!(rdigest.as_deref(), Some(digest), "RLS-A13's pin");
    assert_eq!(chan, Some(channel));
    assert_eq!(cev, Some(1));

    // ── HOP 5 · the WIRE FRAME ──────────────────────────────────────────────
    //
    // `TurnOutcome` is what a client receives. Projected from the committed
    // fact, which is the direction that matters: the frame is DERIVED from the
    // row, never assembled beside it.
    let narration: Vec<String> = body["events"]
        .as_array()
        .expect("the hub's fold is an array")
        .iter()
        .map(|e| e.to_string())
        .collect();
    let frame = commit_service::wire::TurnOutcome::from_resolution(
        cev.expect("channel_event_id"),
        m["turn_number"].as_str().expect("decimal string").parse().expect("u64"),
        true,
        narration.clone(),
        None,
    );
    let json = serde_json::to_value(&frame).expect("serialise the frame");
    println!("HOP 5  wire frame          {json}");

    assert_eq!(
        json["turn_number"], "5",
        "CWC-A2: the frame carries it as a decimal STRING — a browser loses precision past 2^53"
    );
    assert_eq!(
        json["detail"]["events"],
        serde_json::to_value(&narration).expect("narration"),
        "and the hub's fold reached the client frame"
    );
}
