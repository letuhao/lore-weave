//! `Q0b B3b + B3c` end to end, against a real Postgres.
//!
//! ```text
//! activate_reality_epoch ──▶ reality_ruleset_binding (meta DB, append-only)
//!                            └─▶ meta_outbox {reality.ruleset.bound}
//!   reconcile_and_commit ──▶ re-reads the BINDING ──▶ island.submit_epoch_switch
//!                        └─▶ ChannelWriter::append ──▶ events (channel DB)
//! ```
//!
//! **Why a live test and not mocks.** Every claim this slice makes is a claim
//! about state that crosses a process boundary:
//!
//! * the switch is decided by re-reading `reality_ruleset_binding`, which is a
//!   QUERY — a fake store returns whatever the test put in it, so it can prove
//!   the branch and not the read;
//! * the append is fenced by a CAS on `channel_writer_state.current_epoch`, so
//!   "only the lease-holder may append" is enforced by Postgres and by nothing
//!   in this process;
//! * the payload has to survive `jsonb`, come back, and still join to the
//!   binding row through `authorised_by`.
//!
//! Two DSNs because production has two databases: the meta DB holds the
//! binding, the per-reality DB holds the channel log. Collapsing them here would
//! test a topology nothing runs.
//!
//! Run via `scripts/epoch-activation-live-smoke.sh`. No DSN ⇒ SKIP, loudly.
//! There is no DELETE/TRUNCATE/DROP in this file: isolation is a fresh reality
//! UUID per test, which `reality_ruleset_binding` being append-only makes
//! mandatory anyway.

use std::sync::Arc;

use commit_service::epoch_commit::{reconcile_and_commit, EpochOutcome};
use commit_service::epoch_signal::authorised_by;
use dp_kernel::channel::{acquire_writer_lease, ChannelId, ChannelWriter};
use ruleset_loader::activate_reality_epoch;
use sim_core::RulesetEpoch;
use sqlx::postgres::PgPoolOptions;
use uuid::Uuid;
use commit_service::RealityRules;

mod epoch_live_common;
use epoch_live_common::{
    activation_rows, boot_for, dsns, island, put_quantities, CHANNEL_DSN_VAR, META_DSN_VAR,
};

/// **The regression guard for the one HIGH `/review-impl` found in this slice.**
///
/// The first version of the payload OMITTED `metadata.turn_number`, reasoning
/// that "absent" was the honest encoding of "a switch is not a turn". It was
/// not. `game-server/src/wire/turnOutcome.ts` calls
/// `toU64String(meta.turn_number, 'turn_number')` **unconditionally**, before it
/// switches on `event_type`, and that call sits OUTSIDE the replay loop's
/// try/catch — so a committed event without the field throws
/// `turn_number: missing` and takes down the entire channel projection, for
/// every client, permanently, because replay meets the same event every time.
///
/// The repo's encoding of "unchanged" is *the same number again* — which is what
/// `proposal.rejected` has always stamped (EVT-V4). This asserts the field is
/// present, is a DECIMAL STRING (CWC-A2), and carries the unadvanced value.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_activation_event_carries_the_unadvanced_turn_number() {
    let Some((meta, channel_dsn)) = dsns() else {
        eprintln!("SKIP: {META_DSN_VAR}/{CHANNEL_DSN_VAR} unset");
        return;
    };
    let boot = boot_for(&meta, "turnno").await;
    let reality = Uuid::new_v4();
    let channel = 4i64;

    let d1 = put_quantities(&boot.store, &["qi"]);
    boot.bindings.create(&reality.to_string(), &d1).expect("epoch 1");
    let (rules, _) = boot.load(&reality.to_string()).expect("load");
    let mut isle = island(Arc::new(RealityRules::resolve(rules).expect("the reality binds every engine role")), RulesetEpoch(1), channel);

    let pool = Arc::new(
        PgPoolOptions::new().max_connections(2).connect(&channel_dsn).await.expect("channel"),
    );
    let lease = acquire_writer_lease(&pool, reality, ChannelId::unverified(channel)).await.expect("lease");
    let writer = ChannelWriter::new(pool.clone(), reality, lease);
    let mut version = 0u64;

    let d2 = put_quantities(&boot.store, &["qi", "karma"]);
    activate_reality_epoch(boot.bindings.as_ref(), &boot.store, &reality.to_string(), &d2, "smoke")
        .expect("switch");

    // 41 turns already played on this channel. The switch must not advance it,
    // and must not drop it either.
    reconcile_and_commit(&boot, reality, channel, &mut isle, &writer, &mut version, 41)
        .await
        .expect("reconcile");

    let rows = activation_rows(&pool, reality).await;
    assert_eq!(rows.len(), 1);
    let metadata = &rows[0].3;
    assert_eq!(
        metadata["event_category"], "T8",
        "EVT-T8 Administrative — a rules change is not gameplay this channel produced"
    );
    let turn = metadata.get("turn_number").unwrap_or_else(|| {
        panic!(
            "metadata has NO turn_number: {metadata}\n\
             game-server parses this field unconditionally, outside its try/catch — \
             an event without it kills the channel projection for every client"
        )
    });
    assert_eq!(
        turn,
        &serde_json::Value::String("41".into()),
        "CWC-A2: a decimal STRING carrying the UNADVANCED counter (EVT-V4)"
    );
}

/// **The slice's exit criterion.** A binding moves; a running island that never
/// saw a Redis entry switches anyway, because it re-read the table; and the
/// event lands on the channel, joinable back to the row that authorised it.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn an_activated_epoch_reaches_the_channel_log() {
    let Some((meta, channel_dsn)) = dsns() else {
        eprintln!("SKIP: {META_DSN_VAR}/{CHANNEL_DSN_VAR} unset — run scripts/epoch-activation-live-smoke.sh");
        return;
    };
    let boot = boot_for(&meta, "reaches").await;
    let reality = Uuid::new_v4();
    let channel = 1i64;

    let d1 = put_quantities(&boot.store, &["qi"]);
    boot.bindings.create(&reality.to_string(), &d1).expect("epoch 1");
    let (rules, binding) = boot.load(&reality.to_string()).expect("load");
    assert_eq!(binding.epoch, 1);
    let mut isle = island(Arc::new(RealityRules::resolve(rules).expect("the reality binds every engine role")), RulesetEpoch(1), channel);
    let epoch1_digest = isle.digest.to_hex();

    let pool = Arc::new(
        PgPoolOptions::new().max_connections(2).connect(&channel_dsn).await.expect("channel"),
    );
    let lease = acquire_writer_lease(&pool, reality, ChannelId::unverified(channel)).await.expect("lease");
    let writer = ChannelWriter::new(pool.clone(), reality, lease);
    let mut version = 0u64;

    // Nothing has moved yet. This must be a NO-OP, not a refusal: an island
    // already at the bound epoch attempted nothing, so nothing was rejected.
    assert_eq!(
        reconcile_and_commit(&boot, reality, channel, &mut isle, &writer, &mut version, 0)
            .await
            .expect("reconcile"),
        EpochOutcome::AlreadyCurrent
    );
    assert!(activation_rows(&pool, reality).await.is_empty(), "a no-op appended an event");

    // ── the admin act: the binding moves to epoch 2 ──
    let bumps_before = isle.metrics().island_gen_bumps;
    let d2 = put_quantities(&boot.store, &["qi", "karma"]);
    activate_reality_epoch(boot.bindings.as_ref(), &boot.store, &reality.to_string(), &d2, "live smoke")
        .expect("additive switch is permitted");

    // No Redis entry was delivered to this island. It switches anyway, because
    // the decision is a read of the TABLE — which is the property that makes a
    // missed signal survivable.
    let outcome = reconcile_and_commit(&boot, reality, channel, &mut isle, &writer, &mut version, 0)
        .await
        .expect("reconcile");
    let EpochOutcome::Activated { from, to, .. } = outcome else {
        panic!("expected an activation, got {outcome:?}")
    };
    assert_eq!((from.0, to.0), (1, 2));

    // The island is now RUNNING the new rules — not merely announcing them.
    assert_eq!(isle.epoch, RulesetEpoch(2));
    // **RLS-A14: the ORDERED path, and this is what pins it.**
    //
    // `Island::activate_epoch` (out-of-band) and `submit_epoch_switch`
    // (ordered) both leave the island on the new epoch with the new digest, so
    // every other assertion in this file passes either way. The one observable
    // difference is the GENERATION: the out-of-band call bumps it, because
    // items already admitted were validated under rules that no longer apply
    // and must be superseded. The ordered path must not — an item queued before
    // the switch is re-validated at ITS pop, against the rules in force then,
    // which is exactly right and is why the ordered path is the one a host
    // should reach for.
    //
    // Without this line, swapping the call would be invisible to the whole
    // suite.
    assert_eq!(
        isle.metrics().island_gen_bumps,
        bumps_before,
        "the ordered switch must NOT bump the island generation — a bump means \
         `activate_epoch` was called instead of `submit_epoch_switch`, and every \
         input already admitted would be discarded as Superseded"
    );
    assert_ne!(isle.digest.to_hex(), epoch1_digest, "the digest must have moved with the epoch");
    assert_eq!(isle.digest.to_hex(), d2.to_hex(), "and it must be the digest the binding names");

    let rows = activation_rows(&pool, reality).await;
    assert_eq!(rows.len(), 1, "exactly one activation event for one switch");
    let (ty, payload, pinned, _meta) = &rows[0];
    assert_eq!(ty, "ruleset.epoch_activated");
    assert_eq!(payload["from_epoch"], 1);
    assert_eq!(payload["to_epoch"], 2);
    assert_eq!(payload["channel_id"], channel);
    assert_eq!(payload["digest"], d2.to_hex());
    assert_eq!(
        payload["authorised_by"],
        authorised_by(&reality.to_string(), 2),
        "the event must join back to the binding row that authorised it"
    );
    assert_eq!(
        pinned.as_deref(),
        Some(d2.to_hex().as_str()),
        "RLS-A13: the envelope pin is the ruleset the island now runs"
    );
}

/// The reconcile is called on EVERY loop iteration, so it runs orders of
/// magnitude more often than a switch happens. Running it again after a switch
/// must produce nothing — not a second event, not a refusal.
///
/// This is the property that makes at-least-once delivery free: the answer comes
/// from the table, so N deliveries collapse to one activation instead of one
/// activation and N-1 `NotMonotonic` refusals an operator has to learn to ignore.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn reconciling_again_appends_nothing() {
    let Some((meta, channel_dsn)) = dsns() else {
        eprintln!("SKIP: {META_DSN_VAR}/{CHANNEL_DSN_VAR} unset");
        return;
    };
    let boot = boot_for(&meta, "again").await;
    let reality = Uuid::new_v4();
    let channel = 2i64;

    let d1 = put_quantities(&boot.store, &["qi"]);
    boot.bindings.create(&reality.to_string(), &d1).expect("epoch 1");
    let (rules, _) = boot.load(&reality.to_string()).expect("load");
    let mut isle = island(Arc::new(RealityRules::resolve(rules).expect("the reality binds every engine role")), RulesetEpoch(1), channel);

    let pool = Arc::new(
        PgPoolOptions::new().max_connections(2).connect(&channel_dsn).await.expect("channel"),
    );
    let lease = acquire_writer_lease(&pool, reality, ChannelId::unverified(channel)).await.expect("lease");
    let writer = ChannelWriter::new(pool.clone(), reality, lease);
    let mut version = 0u64;

    let d2 = put_quantities(&boot.store, &["qi", "karma"]);
    activate_reality_epoch(boot.bindings.as_ref(), &boot.store, &reality.to_string(), &d2, "smoke")
        .expect("switch");

    for _ in 0..5 {
        reconcile_and_commit(&boot, reality, channel, &mut isle, &writer, &mut version, 0)
            .await
            .expect("reconcile");
    }
    assert_eq!(
        activation_rows(&pool, reality).await.len(),
        1,
        "five reconciles over one switch must append ONE event"
    );
}

/// Two switches in a row, with the island only catching up at the end.
///
/// The island jumps 1 → 3 and commits ONE event saying so, because the table
/// names the current epoch rather than replaying the history. Committing an
/// event for epoch 2 as well would announce an activation that never happened on
/// this channel — the log would describe rules this island never ran.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_missed_epoch_is_not_replayed() {
    let Some((meta, channel_dsn)) = dsns() else {
        eprintln!("SKIP: {META_DSN_VAR}/{CHANNEL_DSN_VAR} unset");
        return;
    };
    let boot = boot_for(&meta, "missed").await;
    let reality = Uuid::new_v4();
    let channel = 3i64;

    let d1 = put_quantities(&boot.store, &["qi"]);
    boot.bindings.create(&reality.to_string(), &d1).expect("epoch 1");
    let (rules, _) = boot.load(&reality.to_string()).expect("load");
    let mut isle = island(Arc::new(RealityRules::resolve(rules).expect("the reality binds every engine role")), RulesetEpoch(1), channel);

    let pool = Arc::new(
        PgPoolOptions::new().max_connections(2).connect(&channel_dsn).await.expect("channel"),
    );
    let lease = acquire_writer_lease(&pool, reality, ChannelId::unverified(channel)).await.expect("lease");
    let writer = ChannelWriter::new(pool.clone(), reality, lease);
    let mut version = 0u64;

    let d2 = put_quantities(&boot.store, &["qi", "karma"]);
    let d3 = put_quantities(&boot.store, &["qi", "karma", "fire"]);
    activate_reality_epoch(boot.bindings.as_ref(), &boot.store, &reality.to_string(), &d2, "s2")
        .expect("switch 2");
    activate_reality_epoch(boot.bindings.as_ref(), &boot.store, &reality.to_string(), &d3, "s3")
        .expect("switch 3");

    let outcome = reconcile_and_commit(&boot, reality, channel, &mut isle, &writer, &mut version, 0)
        .await
        .expect("reconcile");
    assert_eq!(
        outcome,
        EpochOutcome::Activated {
            from: RulesetEpoch(1),
            to: RulesetEpoch(3),
            channel_event_id: match outcome {
                EpochOutcome::Activated { channel_event_id, .. } => channel_event_id,
                _ => panic!("expected an activation, got {outcome:?}"),
            },
        }
    );
    assert_eq!(isle.epoch, RulesetEpoch(3));

    let rows = activation_rows(&pool, reality).await;
    assert_eq!(rows.len(), 1, "one catch-up is one event, not one per skipped epoch");
    assert_eq!(rows[0].1["from_epoch"], 1);
    assert_eq!(rows[0].1["to_epoch"], 3);
}
