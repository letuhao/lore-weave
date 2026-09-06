//! `DF1b-ii` — the admission refusal, committed through the SDK, against a REAL
//! Postgres, by the PRODUCTION functions.
//!
//! # What is production here and what is not
//!
//! `reject_commit::wire` and `reject_commit::commit_rejection` are the exact
//! functions `bin/spine.rs` calls — not reimplementations. The pool, the writer
//! lease, the channel tree, the backend and the event row are all real. The one
//! double is the `ControlPlane` that mints the session, because the alternative
//! is standing up the meta database inside a unit-test binary; the spine's own
//! `reality_bind` does that part live and is covered separately.
//!
//! That distinction matters for `§0.8`'s wording — *"the resulting row is
//! pasted from Postgres (not from a test double)"*. The ROW is written by
//! production code into a real table. The session's issuer is stubbed.
//!
//! # Why not drive `bin/spine.rs` itself
//!
//! It was tried, and it hangs — **at `HEAD`, without any of this change**. The
//! binary reaches *"epoch signals: lw.meta.events …"* and then blocks past a
//! 120s timeout even with `--drain-once` and a message waiting on the stream.
//! Measured both ways: with `DF1b-ii` applied (`RC=124`) and with the whole
//! change stashed (`HEAD_RC=124`), and the instrumented run showed this
//! change's own code completing (`WIRE: channel resolved`) before the hang.
//! Tracked as `DFO-7`; it is not this change's to fix, and pretending the
//! binary was exercised would be worse than saying which part was.
//!
//! Gated on `LOREWEAVE_TEST_PG_URL`; skips cleanly when unset. Append-only
//! against a random reality (db-safety-gate: ok — INSERT/SELECT only, per-test
//! random reality ids, nothing deleted).

use std::sync::atomic::AtomicU64;
use std::sync::Arc;

use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use uuid::Uuid;

use commit_service::reject_commit;
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

/// The ONE `ChannelId::unverified` call site in this file — see the twin in
/// `dp-kernel/tests/integration_dp_channel.rs`. The SESSION resolves its
/// channel properly, through `PgChannelTree`; `acquire_writer_lease` is the
/// one call that takes a `ChannelId` without a session to resolve it from.
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

/// A refusal, committed through `dp::t2_write_channel`, lands as a
/// `proposal.rejected` row carrying everything its two projectors read.
///
/// Kill-mutations, each of which this asserts against: the event losing its
/// NAME (both projectors dispatch on it) · the payload becoming a base64 blob ·
/// `event_category` dropped · `RLS-A13`'s digest dropped · `turn_number`
/// missing or advanced (`EVT-V4` says a refusal advances nothing).
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_refusal_committed_through_the_sdk_carries_everything_its_projectors_read() {
    let Some(url) = dsn() else {
        eprintln!("[skip] LOREWEAVE_TEST_PG_URL not set — reject_commit live suite skipped");
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

    // The channel's DP-A17 counter, already advanced twice — so "a refusal does
    // not advance the turn" is a claim about a NON-ZERO number. Asserting it at
    // 0 would pass whether or not the counter was read at all.
    let turn = Arc::new(AtomicU64::new(7));
    let digest = "d1ce5eed0000000000000000000000000000000000000000000000000000beef";

    // PRODUCTION FUNCTIONS — the same two `bin/spine.rs` calls.
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

    let pos = reject_commit::commit_rejection(
        &backend,
        &ctx,
        0,
        channel,
        0,
        "vocabulary",
        "verb `definitely_not_a_verb` is not in the reality's vocabulary",
    )
    .expect("commit the refusal through the SDK");
    assert_eq!(pos, 1, "the channel allocated position 1");

    let (etype, payload, meta, rdigest, chan, cev): (
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

    assert_eq!(etype, "proposal.rejected", "the NAME both projectors dispatch on");
    assert_eq!(
        payload["rejected_at_stage"], "vocabulary",
        "a structured body, not a base64 blob"
    );
    assert!(payload.get("b64").is_none(), "never wrapped");
    assert_eq!(meta["event_category"], "T6", "the writer-stamped taxonomy (PID-D5)");
    assert_eq!(
        meta["turn_number"], "7",
        "CWC-A2: a decimal STRING, and EVT-V4: the refusal did NOT advance it"
    );
    assert_eq!(turn.load(std::sync::atomic::Ordering::SeqCst), 7, "counter untouched");
    assert_eq!(rdigest.as_deref(), Some(digest), "RLS-A13's pin survived the seam");
    assert_eq!(chan, Some(channel), "it landed ON the channel");
    assert_eq!(cev, Some(1), "with the position the ack reported");
}
