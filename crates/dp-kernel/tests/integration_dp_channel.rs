//! `DF1a` — the SDK's CHANNEL write, end to end against real Postgres.
//!
//! `dp::t2_write_channel` → [`KernelChannelWriteBackend`] → `ChannelWriter` →
//! an `events` row **with its channel columns set** and a `channel_event_index`
//! entry. That last clause is the whole point: `KernelWriteBackend` (the
//! reality backend) writes an `events` row too, with `channel_id = NULL`, which
//! `0014_channel_ordering.up.sql` defines as a reality-scoped event and which
//! no channel subscriber reads.
//!
//! Also covers the first production [`dp::ChannelTree`] — until `DF1a` every
//! implementor in the tree was a `#[cfg(test)]` double, so no production
//! session could enter a channel at all.
//!
//! Gated on `LOREWEAVE_TEST_PG_URL`, same convention as
//! `integration_channel_writer.rs`, and skips cleanly when unset. Requires the
//! same migrations that suite lists (0002 + 0005 + 0013 + 0014 + 0016 + 0020),
//! plus **0019** (`channels`) for the tree, and the `events_y2026m05`
//! partition. Append-only against random reality UUIDs — no destructive
//! statements (db-safety-gate: ok — INSERT/SELECT only, random per-test
//! realities, nothing is deleted).

use std::sync::Arc;

use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use uuid::Uuid;

use dp::{
    scope::ChannelScope, scope::RealityScope, tier::T2, BindRequest, ChannelTree, ControlPlane,
    DpAggregate, DpError, Encode, KeyId, SessionContext, VerifiedBind,
};
use dp_kernel::channel::{acquire_writer_lease, ChannelId, ChannelWriter};
use dp_kernel::dp_channel::{KernelChannelWriteBackend, PgChannelTree};

// ── fixtures ────────────────────────────────────────────────────────────────

/// A channel-scoped T2 aggregate — the shape that could not be written before.
struct Chatter;
impl DpAggregate for Chatter {
    type Tier = T2;
    type Scope = ChannelScope;
    type Id = Uuid;
    type Delta = i32;
    type Projection = ();
    const TYPE_NAME: &'static str = "dp_channel_fixture";
}
impl Encode for Chatter {
    fn encode(d: &i32) -> Result<Vec<u8>, DpError> {
        Ok(d.to_le_bytes().to_vec())
    }
}

/// A channel-scoped aggregate that IS a domain event (`DF1b-i`).
///
/// `npc.said` is a REGISTERED type (`contracts/events/_registry.yaml`), chosen
/// rather than invented: the point of `EVENT_TYPE` is to name an event the
/// registry already knows, not to mint a second vocabulary.
struct NpcSaid;
impl DpAggregate for NpcSaid {
    type Tier = T2;
    type Scope = ChannelScope;
    type Id = Uuid;
    type Delta = serde_json::Value;
    type Projection = ();
    const TYPE_NAME: &'static str = "dp_channel_domain_fixture";
    const EVENT_TYPE: &'static str = "npc.said";
    const PAYLOAD_IS_JSON: bool = true;
}
impl Encode for NpcSaid {
    fn encode(d: &serde_json::Value) -> Result<Vec<u8>, DpError> {
        serde_json::to_vec(d).map_err(|e| DpError::BackendIo(Box::new(e)))
    }
}

/// Declares JSON and produces something that is not — the refusal case.
struct LiesAboutJson;
impl DpAggregate for LiesAboutJson {
    type Tier = T2;
    type Scope = ChannelScope;
    type Id = Uuid;
    type Delta = ();
    type Projection = ();
    const TYPE_NAME: &'static str = "dp_channel_liar_fixture";
    const EVENT_TYPE: &'static str = "npc.said";
    const PAYLOAD_IS_JSON: bool = true;
}
impl Encode for LiesAboutJson {
    fn encode(_d: &()) -> Result<Vec<u8>, DpError> {
        Ok(b"not json at all".to_vec())
    }
}

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

fn bind(reality: Uuid) -> SessionContext {
    SessionContext::bind(
        &Cp,
        BindRequest {
            reality,
            node: "n".into(),
            service: dp::ServiceIdentity::new("dp-kernel-dp-channel-test").expect("valid"),
        },
        0,
    )
    .expect("bind")
}

/// Seed one root channel + one child, so the tree has an ancestor to return.
async fn seed_channels(pool: &PgPool, reality: Uuid, root: i64, child: i64) {
    for (id, parent, depth, level) in
        [(root, None::<i64>, 0i16, "reality"), (child, Some(root), 1i16, "cell")]
    {
        sqlx::query(
            "INSERT INTO channels (reality_id, id, parent, level_name, depth, lifecycle) \
             VALUES ($1, $2, $3, $4, $5, 'active')",
        )
        .bind(reality)
        .bind(id)
        .bind(parent)
        .bind(level)
        .bind(depth)
        .execute(pool)
        .await
        .expect("seed channel");
    }
}

// ── the end-to-end claim ────────────────────────────────────────────────────

/// A channel-scoped write through the SDK lands ON THE CHANNEL.
///
/// Kill-mutations: the backend ignoring `req.channel` · the write going through
/// `EventStore::append_events` instead of `ChannelWriter` (both would leave
/// `channel_id` NULL and `channel_event_index` empty, and both assertions
/// below would red).
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_channel_write_through_the_sdk_lands_on_the_channel() {
    let Some(url) = dsn() else {
        eprintln!("[skip] LOREWEAVE_TEST_PG_URL not set — dp channel suite skipped");
        return;
    };
    let pool = pool(&url).await;
    let reality = Uuid::new_v4();
    let (root, child) = (1i64, 2i64);
    seed_channels(&pool, reality, root, child).await;

    // The session enters the channel through the REAL tree — the only producer
    // of a verified ChannelId, and until now unimplementable in production.
    let tree = PgChannelTree::new(pool.clone(), reality).expect("multi-thread runtime");
    let ctx = bind(reality).move_to_channel(&tree, child, 0).expect("move_to_channel");
    assert_eq!(
        ctx.current_channel_id().map(|c| c.get()),
        Some(child),
        "the session is addressed to the channel it resolved"
    );
    assert_eq!(
        ctx.ancestor_channels().iter().map(|c| c.get()).collect::<Vec<_>>(),
        vec![root],
        "root-first ancestors, excluding the channel itself"
    );

    let lease = acquire_writer_lease(&pool, reality, ChannelId::unverified(child))
        .await
        .expect("lease");
    let writer = Arc::new(ChannelWriter::new(pool.clone(), reality, lease));
    let backend = KernelChannelWriteBackend::new(writer).expect("multi-thread runtime");

    let id = Uuid::new_v4();
    // `channel:` arm — a channel-scoped aggregate keys through `channel_key`,
    // and the macro refuses the reality arm for it at compile time.
    // `channel_key` returns `Option` because a session with no channel cannot
    // build one — this ctx has been moved into `child`, so it is Some.
    let key = dp::cache_key!(channel: &ctx, T2, Chatter, id)
        .expect("the session is in a channel, so it has a channel key");
    let ack = dp::t2_write_channel::<Chatter, _>(&backend, &ctx, 0, KeyId::from(id), &key, 0, 42)
        .expect("write through the SDK");
    assert_eq!(ack.position, 1, "the channel allocated position 1");

    // DATA — the row itself, not a description of it.
    let (chan, cev, epoch, agg_type): (Option<i64>, Option<i64>, Option<i64>, String) =
        sqlx::query_as(
            "SELECT channel_id, channel_event_id, writer_epoch, aggregate_type \
               FROM events WHERE reality_id = $1 AND aggregate_id = $2",
        )
        .bind(reality)
        .bind(id.to_string())
        .fetch_one(&*pool)
        .await
        .expect("the event row");

    assert_eq!(chan, Some(child), "THE CLAIM: channel_id is set, not NULL");
    assert_eq!(cev, Some(1), "the channel allocated the position the ack reported");
    assert!(epoch.is_some(), "the writer epoch was fenced onto the row");
    assert_eq!(agg_type, "dp_channel_fixture");

    let (indexed,): (i64,) = sqlx::query_as(
        "SELECT COUNT(*) FROM channel_event_index \
          WHERE reality_id = $1 AND channel_id = $2 AND channel_event_id = $3",
    )
    .bind(reality)
    .bind(child)
    .bind(1i64)
    .fetch_one(&*pool)
    .await
    .expect("index count");
    assert_eq!(indexed, 1, "the hard uniqueness backstop got its row in the same tx");
}

/// `DF1b-i` — an aggregate NAMES its domain event, and the row carries it.
///
/// Kill-mutations: the backend ignoring `req.event_type` (the row would read
/// `dp.write.applied` and every projector that dispatches on the name would
/// skip it) · the backend base64ing a declared-JSON payload (the projector
/// would find none of its fields).
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_domain_event_keeps_its_name_and_its_shape() {
    let Some(url) = dsn() else {
        eprintln!("[skip] LOREWEAVE_TEST_PG_URL not set — dp channel suite skipped");
        return;
    };
    let pool = pool(&url).await;
    let reality = Uuid::new_v4();
    seed_channels(&pool, reality, 1, 2).await;

    let tree = PgChannelTree::new(pool.clone(), reality).expect("multi-thread runtime");
    let ctx = bind(reality).move_to_channel(&tree, 2, 0).expect("move_to_channel");
    let lease = acquire_writer_lease(&pool, reality, ChannelId::unverified(2))
        .await
        .expect("lease");
    let writer = Arc::new(ChannelWriter::new(pool.clone(), reality, lease));
    let backend = KernelChannelWriteBackend::new(writer).expect("multi-thread runtime");

    let id = Uuid::new_v4();
    let key = dp::cache_key!(channel: &ctx, T2, NpcSaid, id).expect("channel key");
    let body = serde_json::json!({ "npc_id": "n-1", "utterance": "well met" });
    dp::t2_write_channel::<NpcSaid, _>(&backend, &ctx, 0, KeyId::from(id), &key, 0, body.clone())
        .expect("write through the SDK");

    let (etype, payload): (String, serde_json::Value) = sqlx::query_as(
        "SELECT event_type, payload FROM events WHERE reality_id = $1 AND aggregate_id = $2",
    )
    .bind(reality)
    .bind(id.to_string())
    .fetch_one(&*pool)
    .await
    .expect("the event row");

    assert_eq!(etype, "npc.said", "THE CLAIM: the AGGREGATE named the event, not the backend");
    assert_eq!(payload, body, "the JSON body is the payload, not a base64 blob of it");
    assert!(payload.get("b64").is_none(), "a declared-JSON payload is never wrapped");
}

/// An aggregate that declares JSON and encodes something else is REFUSED.
///
/// The alternative — storing the bytes base64'd — would put an event on the
/// channel whose projector silently finds none of its fields. That is `DF1a`'s
/// NULL-channel write one field over, and it is why this is a refusal rather
/// than a fallback.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_payload_that_lies_about_being_json_is_refused_not_wrapped() {
    let Some(url) = dsn() else {
        eprintln!("[skip] LOREWEAVE_TEST_PG_URL not set — dp channel suite skipped");
        return;
    };
    let pool = pool(&url).await;
    let reality = Uuid::new_v4();
    seed_channels(&pool, reality, 1, 2).await;

    let tree = PgChannelTree::new(pool.clone(), reality).expect("multi-thread runtime");
    let ctx = bind(reality).move_to_channel(&tree, 2, 0).expect("move_to_channel");
    let lease = acquire_writer_lease(&pool, reality, ChannelId::unverified(2))
        .await
        .expect("lease");
    let writer = Arc::new(ChannelWriter::new(pool.clone(), reality, lease));
    let backend = KernelChannelWriteBackend::new(writer).expect("multi-thread runtime");

    let id = Uuid::new_v4();
    let key = dp::cache_key!(channel: &ctx, T2, LiesAboutJson, id).expect("channel key");
    let err = dp::t2_write_channel::<LiesAboutJson, _>(
        &backend, &ctx, 0, KeyId::from(id), &key, 0, (),
    )
    .expect_err("a non-JSON payload under PAYLOAD_IS_JSON must be refused");
    let msg = format!("{err}");
    assert!(
        msg.contains("PAYLOAD_IS_JSON") && msg.contains("dp_channel_liar_fixture"),
        "the refusal names the flag AND the aggregate that lied: {msg}"
    );

    // And nothing was written — a refused write must not half-land.
    let (n,): (i64,) =
        sqlx::query_as("SELECT COUNT(*) FROM events WHERE reality_id = $1 AND aggregate_id = $2")
            .bind(reality)
            .bind(id.to_string())
            .fetch_one(&*pool)
            .await
            .expect("count");
    assert_eq!(n, 0, "the refusal happened BEFORE the append, so no row exists");
}

/// The tree refuses a dissolved channel rather than resolving it.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_tree_refuses_a_dissolved_channel() {
    let Some(url) = dsn() else {
        eprintln!("[skip] LOREWEAVE_TEST_PG_URL not set — dp channel suite skipped");
        return;
    };
    let pool = pool(&url).await;
    let reality = Uuid::new_v4();
    sqlx::query(
        "INSERT INTO channels (reality_id, id, parent, level_name, depth, lifecycle, dissolved_at) \
         VALUES ($1, 9, NULL, 'reality', 0, 'dissolved', now())",
    )
    .bind(reality)
    .execute(&*pool)
    .await
    .expect("seed dissolved channel");

    let tree = PgChannelTree::new(pool.clone(), reality).expect("multi-thread runtime");
    let err = tree.resolve(bind(reality).reality_id(), 9).expect_err("must refuse");
    assert!(
        matches!(err, DpError::ChannelDissolved { .. }),
        "a dissolved channel is ChannelDissolved, not a silent resolution: {err:?}"
    );
}

/// A channel the tree does not have is `AggregateNotFound`, not an empty walk
/// silently resolving to nothing.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_tree_refuses_an_absent_channel() {
    let Some(url) = dsn() else {
        eprintln!("[skip] LOREWEAVE_TEST_PG_URL not set — dp channel suite skipped");
        return;
    };
    let pool = pool(&url).await;
    let reality = Uuid::new_v4();
    let tree = PgChannelTree::new(pool.clone(), reality).expect("multi-thread runtime");
    let err = tree.resolve(bind(reality).reality_id(), 404).expect_err("must refuse");
    assert!(
        matches!(err, DpError::AggregateNotFound { aggregate: "channel", .. }),
        "an absent channel is AggregateNotFound: {err:?}"
    );
}

// ── the refusals, which need no database ────────────────────────────────────

/// A reality-scoped aggregate reaching the CHANNEL backend is refused.
///
/// Needs no live DB: the guard returns before the pool is touched, which is
/// also the property being asserted. `connect_lazy` therefore never connects.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_channel_backend_refuses_a_request_with_no_channel() {
    struct Ledger;
    impl DpAggregate for Ledger {
        type Tier = T2;
        type Scope = RealityScope;
        type Id = Uuid;
        type Delta = i32;
        type Projection = ();
        const TYPE_NAME: &'static str = "dp_channel_reality_fixture";
    }

    let pool = Arc::new(
        PgPoolOptions::new()
            .connect_lazy("postgres://never:connected@127.0.0.1:1/none")
            .expect("lazy pool"),
    );
    let lease = dp_kernel::channel::WriterLease {
        channel_id: ChannelId::unverified(7),
        epoch: 1,
    };
    let writer = Arc::new(ChannelWriter::new(pool, Uuid::new_v4(), lease));
    let backend = KernelChannelWriteBackend::new(writer).expect("multi-thread runtime");

    // Hand-built, because the type system is what stops feature code doing
    // this — see tests/ui/channel_write_wrong_scope.rs in `dp`. This asserts
    // the backend's own refusal, the second line of defence.
    let reality = bind(Uuid::new_v4());
    let err = dp::WriteBackend::apply(
        &backend,
        &dp::WriteRequest {
            reality: reality.reality_id(),
            aggregate_type: Ledger::TYPE_NAME,
            aggregate_id: KeyId::from(Uuid::new_v4()),
            tier: dp::TierLevel::T2,
            cache_key: "k",
            event_type: dp::DEFAULT_SDK_EVENT_TYPE,
            payload_is_json: false,
            channel: None,
            payload: &[],
            expected_version: 0,
        },
    )
    .expect_err("a channel backend must refuse a channel-less request");
    assert!(
        matches!(err, DpError::SessionNotFound { .. }),
        "refused by naming the missing address: {err:?}"
    );
}

/// A write addressed to a DIFFERENT channel than the held lease is refused —
/// it is not quietly written under this backend's lease.
///
/// This is the guard standing in for `DP-Ch14`'s unbuilt `route_to_writer`. If
/// it ever silently accepted, a write would land on the wrong channel with a
/// valid-looking `channel_event_id`, which no later check could distinguish
/// from a correct one.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_channel_backend_refuses_another_channels_write() {
    let pool = Arc::new(
        PgPoolOptions::new()
            .connect_lazy("postgres://never:connected@127.0.0.1:1/none")
            .expect("lazy pool"),
    );
    let lease = dp_kernel::channel::WriterLease {
        channel_id: ChannelId::unverified(7),
        epoch: 1,
    };
    let writer = Arc::new(ChannelWriter::new(pool, Uuid::new_v4(), lease));
    let backend = KernelChannelWriteBackend::new(writer).expect("multi-thread runtime");

    let reality = bind(Uuid::new_v4());
    let err = dp::WriteBackend::apply(
        &backend,
        &dp::WriteRequest {
            reality: reality.reality_id(),
            aggregate_type: Chatter::TYPE_NAME,
            aggregate_id: KeyId::from(Uuid::new_v4()),
            tier: dp::TierLevel::T2,
            cache_key: "k",
            event_type: dp::DEFAULT_SDK_EVENT_TYPE,
            payload_is_json: false,
            // Channel 8, while the lease is for channel 7.
            channel: Some(ChannelId::unverified(8)),
            payload: &[],
            expected_version: 0,
        },
    )
    .expect_err("a write for another channel must be refused, not re-addressed");
    let msg = format!("{err}");
    assert!(
        msg.contains('8') && msg.contains('7'),
        "the refusal names BOTH channels, or a reader cannot tell which was wrong: {msg}"
    );
}
