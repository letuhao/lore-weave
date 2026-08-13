//! S3a spine runner — the 15_commit_service.md §2 loop, live:
//!
//! ```text
//! Redis Stream (proposals) → admission (schema · EVT-L3 dedup · vocabulary
//!   · NotRun-recorded stages) → sim-core island (resolution) →
//!   dp-kernel ChannelWriter (epoch-fenced, channel-ordered commit) → ACK
//! ```
//!
//! Usage (stack up):
//! ```text
//! cargo run -p commit-service --bin spine --profile release-commit -- \
//!   --redis-url redis://127.0.0.1:6399/0 \
//!   --pg-url postgres://loreweave:…@localhost:5555/loreweave_test_channel_smoke \
//!   --reality <uuid> --channel 1 [--drain-once]
//! ```
//! ACK discipline: an entry is acked ONLY after its outcome is durable
//! (committed event or recorded rejection). A crash before that leaves it
//! in the PEL for redelivery; EVT-L3 dedup + the kernel seen-set make the
//! redelivery safe.

use std::sync::Arc;
use std::time::Duration;

use commit_service::admission::{admit_signed, AdmissionOutcome, DedupCache, Verdict};
use commit_service::spine_args::parse_args;
use commit_service::producer::ProducerRegistry;
use commit_service::bus::{BusConfig, ProposalBus};
use commit_service::wire::discard_reason_wire;
// `DF5` — this file builds no event envelope at all now: both commit paths
// go through the SDK, so the aggregate and the node own what it stamped.
use commit_service::{epoch_commit, epoch_signal};
use commit_service::combat::Side;
use commit_service::{Actor, CombatDomain, CombatState, Vocabulary, COMBAT_V1_JSON};
use std::sync::atomic::{AtomicU64, Ordering};

use commit_service::{reality_bind, reject_commit};
use dp_kernel::channel::{acquire_writer_lease, ChannelId, ChannelWriter};
use sim_core::{EntityId, Island, IslandId, Lane, Outcome, SeenWindow, StepStatus};
use sqlx::postgres::PgPoolOptions;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let args = parse_args()?;
    let vocab = Vocabulary::from_json(COMBAT_V1_JSON)?;

    // ── 3E: VERIFY the reality FIRST — before the pool, before the lease.
    // There is no point acquiring a writer lease on a world we may not write.
    // See `reality_bind` for what a raw `--reality <uuid>` did not check.
    let commit_service::reality_bind::Bound { mut session, plane } =
        commit_service::reality_bind::bind_reality(args.meta_url.as_deref(), &args.meta_allowlist, args.reality)
            .await
            .map_err(|e| anyhow::anyhow!("{e}"))?;
    let (r, sid, exp) = (session.reality_id(), session.session_id(), session.expires_at_ms());
    println!("bound reality {r} as session {sid} (capability expires at {exp})");

    // ── durability side: lease + fenced writer (dp-kernel SDK) ──
    let pool = Arc::new(PgPoolOptions::new().max_connections(4).connect(&args.pg_url).await?);
    let lease = acquire_writer_lease(&pool, args.reality, ChannelId::unverified(args.channel)).await?;
    let writer = Arc::new(ChannelWriter::new(pool.clone(), args.reality, lease));
    println!("lease acquired: channel {} epoch {}", args.channel, lease.epoch);

    // ── resolution side: the island (encounter demo state) ──
    let npc = EntityId(1);
    // ── F2: where this node's rules come from ─────────────────────────────
    //
    // RLS-A3 EARLY BINDING: the stack is resolved ONCE at creation, validated,
    // hashed and then immutable. A later edit to the file never touches a
    // reality that is already running, so replay-safety is STRUCTURAL rather
    // than procedural. The two columns live in `ruleset_boot` — see its module
    // doc for why creation and load must not be one function.
    let (boot, ruleset, reality_epoch) = commit_service::ruleset_boot::boot_reality(
        args.ruleset_state.as_deref().unwrap_or(".loreweave/rulesets"),
        args.meta_url.as_deref(),
        &args.meta_allowlist,
        &args.reality.to_string(),
        args.create_reality,
        args.ruleset.as_deref(),
    )
    .await?;

    // The island DERIVES its pin from these rules via `Domain::rules_digest`,
    // so it cannot report a digest for rules it is not running.
    let mut state = CombatState::default();
    state.actors.insert(npc, Actor::spawn(&ruleset, npc, Side::A));
    for h in [EntityId(2), EntityId(3)] {
        let mut a = Actor::spawn(&ruleset, h, Side::B);
        a.set_vital(&ruleset, 40);
        state.actors.insert(h, a);
    }
    // THE EPOCH COMES FROM THE BINDING, never a default. An island that
    // started at 1 for a reality bound at 5 would compute RLS-I1 monotonicity
    // against the wrong number, and a redelivered switch to an epoch BETWEEN
    // them would be accepted.
    let mut isle: Island<CombatDomain> = Island::new(
        IslandId(args.channel as u64),
        0x53A5_71DE,
        reality_epoch,
        Arc::clone(&ruleset),
        SeenWindow::TtlTicks(300),
        state,
    );
    isle.spawn_entity(npc);
    isle.spawn_entity(EntityId(2));
    isle.spawn_entity(EntityId(3));

    // ── CNC-D2: recover what the last writer knew, from the log ──
    //
    // This runs at LEASE ACQUISITION because that is precisely the moment the
    // bug fires: taking over a channel is the one event after which a
    // redelivered PEL entry meets a writer with no memory of it. Before this,
    // the seen-set started empty on every start and the same intent could
    // apply twice (audit CNC-F6).
    let recovered = commit_service::recovery::recover_writer_state(
        &pool,
        session.reality_id().to_owned(),
        args.channel,
        commit_service::recovery::RECOVERY_TAIL,
    )
    .await?;
    let at = isle.tick_now();
    commit_service::recovery::seed_seen(&mut isle, &recovered.seen_input_ids, at);
    println!(
        "recovered: {} seen ids · turn_number {} · aggregate_version {}",
        recovered.seen_input_ids.len(),
        recovered.turn_number,
        recovered.aggregate_version
    );

    // ── bus side: the EVT-L rail ──
    let cfg = BusConfig {
        stream: format!("reality:{}:cell:{}:proposals", args.reality, args.channel),
        group: format!("reality:{}", args.reality),
        consumer: format!("writer-ch{}", args.channel),
        block_ms: if args.drain_once { 250 } else { 2_000 },
        batch: 16,
        max_attempts: 5,
        reclaim_min_idle_ms: 30_000,
    };
    println!("consuming {} as {}/{}", cfg.stream, cfg.group, cfg.consumer);
    let mut bus = ProposalBus::connect(&args.redis_url, cfg).await?;
    let mut dedup = DedupCache::new(Duration::from_secs(60));
    // PID-A4 — producer identity. An EMPTY registry means identity is not
    // enforced (the pre-PID behaviour), which is why the state is announced
    // rather than assumed: an operator who forgot the keys would otherwise
    // run a bus that accepts anything, and see nothing unusual in the logs.
    let producers = ProducerRegistry::from_env();
    if producers.is_empty() {
        println!(
            "WARNING: no LW_PRODUCER_KEY_* configured — producer identity is NOT enforced;              any writer that can reach Redis may claim any tier"
        );
    } else {
        println!("producer identity: ENFORCED (default-DENY)");
    }

    // ── Q0b B3b: the binding-signal rail, on its OWN consumer group ──
    // A group is a work-SPLITTING primitive, so two channels sharing one would
    // each get a different subset of the binding events and the one that missed
    // the entry would never switch. See `epoch_signal`'s module doc.
    let mut signals =
        epoch_signal::connect_signal_bus(&args.redis_url, &args.reality.to_string(), args.channel)
            .await?;
    println!("epoch signals: {} as {}", epoch_signal::META_STREAM, signals.cfg.group);

    let (mut consumed, mut admitted, mut rejected, mut committed) = (0u64, 0u64, 0u64, 0u64);
    // Continues the channel's existing version line rather than colliding at 1.
    let mut aggregate_version: u64 = recovered.aggregate_version;
    // DP-A17 turn counter: an APPLIED resolution advances it, a rejection
    // NEVER does (EVT-V4). SEEDED FROM RECOVERY like `aggregate_version` — it
    // read `= 0` while `WriterRecovery::turn_number` was queried, printed and
    // dropped, so restarts rewound it (DFO-5; recovered_values_are_consumed).
    let turn_number = Arc::new(AtomicU64::new(recovered.turn_number));

    // `DF1b-ii` — session enters its channel; node declares its facts.
    let (chan_ctx, dp_backend) = reject_commit::wire(
        pool.clone(), &session, args.channel,
        reality_bind::now_ms().map_err(|e| anyhow::anyhow!("{e}"))?,
        isle.digest.to_hex(), turn_number.clone(), writer.clone(),
    )
    .map_err(|e| anyhow::anyhow!("{e}"))?;

    loop {
        // DP-K10 step 4. The `?` is the mechanism: a REVOKED session comes
        // back refused and this writer stops. See `reality_bind::refresh_if_due`.
        if let Some(r) = commit_service::reality_bind::refresh_if_due(&session, &plane)
            .map_err(|e| anyhow::anyhow!("{e}"))?
        {
            println!("capability refreshed, now expires at {}", r.expires_at_ms());
            session = r;
        }

        // BEFORE the proposals, every iteration including the first. Ahead of
        // them because an epoch switch changes the rules the batch about to be
        // stepped will be validated against, and running the reconcile on the
        // FIRST iteration is what closes the boot race — the consumer group was
        // created at `$`, so an activation between the boot read and the group's
        // creation reaches this node only through the table.
        // `3E`: the VERIFIED id from the session this loop holds — not
        // `args.reality`, the raw CLI text the bind consumed. Read off
        // `session` so the `plane` that refreshes it stays alive (`BDR-54`).
        epoch_commit::drain_and_reconcile(
            &mut signals, &boot, session.reality_id(), args.channel, &mut isle, &writer,
            &mut aggregate_version, turn_number.load(Ordering::SeqCst),
        )
        .await?;

        // Reclaim stale PEL entries first (dead prior consumers), then fresh.
        let reclaimed = bus.reclaim().await?;
        let mut work: Vec<(commit_service::bus::BusMessage, usize)> =
            reclaimed.into_iter().collect();
        for m in bus.fetch().await? {
            work.push((m, 1));
        }
        if work.is_empty() {
            if args.drain_once {
                break;
            }
            continue;
        }

        let mut to_ack: Vec<String> = Vec::new();
        for (msg, attempts) in work {
            consumed += 1;
            if attempts > bus.cfg.max_attempts {
                bus.dead_letter(&msg, "max delivery attempts exceeded").await?;
                continue;
            }
            let Some(body) = msg.field("proposal") else {
                bus.dead_letter(&msg, "missing 'proposal' field").await?;
                continue;
            };

            // The signature is a SIBLING stream field, so the verifier hashes
            // the exact bytes the producer sent (PID-D2).
            let sig = msg.field("producer_sig");
            let record = admit_signed(body, sig, &producers, &vocab, &ruleset.rules().verbs, &mut dedup);
            match record.outcome {
                AdmissionOutcome::Rejected { stage, ref reason } => {
                    rejected += 1;
                    // S3b / CS-A4: a validator rejection is COMMITTED, not
                    // just logged — and since `DF1b-ii` it is committed THROUGH
                    // THE SDK, which is what its own "t2_write" comment always
                    // claimed. `event_type`, the JSON body, `event_category` and
                    // the RLS-A13 digest all now come from the aggregate's
                    // declaration and the writer node, not from this call site
                    // remembering to stamp four things.
                    //
                    // It does NOT advance turn_number (EVT-V4); the backend
                    // stamps the counter's current value.
                    let pos = reject_commit::commit_rejection(
                        &dp_backend,
                        &chan_ctx,
                        reality_bind::now_ms().map_err(|e| anyhow::anyhow!("{e}"))?,
                        args.channel,
                        aggregate_version,
                        stage,
                        reason,
                    )
                    .map_err(|e| anyhow::anyhow!("{e}"))?;
                    aggregate_version += 1;
                    println!(
                        "REJECT-COMMIT [{stage}] {} → channel_event_id {pos} (turn stays {}) — {reason}",
                        msg.id,
                        turn_number.load(Ordering::SeqCst)
                    );
                    to_ack.push(msg.id.clone());
                }
                AdmissionOutcome::Admitted(input) => {
                    admitted += 1;
                    let input_id = input.input().input_id;
                    isle.submit(Lane::Live, *input);
                    // `Poisoned` is not `Idle`, so the original `!= Idle` spun
                    // forever at 100% CPU the moment an `apply` panicked
                    // (SC-A8 poison-not-resume — `step` returns `Poisoned` from
                    // then on, every time). Pre-existing; found by
                    // `/review-impl` on the epoch path, which had copied the
                    // same loop, and fixed in both places rather than only in
                    // the new one — the same defect in two siblings is how the
                    // non-vacuity register's first three rows happened.
                    while !matches!(isle.step(), StepStatus::Idle | StepStatus::Poisoned) {}
                    if isle.is_poisoned() {
                        anyhow::bail!(
                            "island {} POISONED (SC-A8: poison-not-resume) — the host must \
                             rebuild it. Stopping rather than looping: this writer can no \
                             longer resolve anything, and its lease must go to a node that can",
                            args.channel
                        );
                    }
                    isle.tick(1);

                    // Commit the resolution — one event per outcome, fenced.
                    let (seq, outcome) =
                        isle.outcomes().last().expect("stepped once").clone();
                    let notrun: Vec<&str> = record
                        .stages
                        .iter()
                        .filter(|(_, v)| matches!(v, Verdict::NotRun))
                        .map(|(n, _)| *n)
                        .collect();
                    // DP-A17: only an APPLIED resolution consumes the turn.
                    if matches!(outcome, Outcome::Applied { .. }) {
                        turn_number.fetch_add(1, Ordering::SeqCst);
                    }
                    // `DF5` — THROUGH THE SDK, like the refusal path above.
                    //
                    // This is the hop the ACTOR HUB is on: `events` is its fold
                    // made durable — `domain::Actor` holds an
                    // `actor_hub::Actor`, the island resolves against it, and
                    // what comes out is what this writes.
                    let kind = match &outcome {
                        Outcome::Applied { .. } => reject_commit::ResolutionKind::Applied,
                        Outcome::Discarded { .. } => reject_commit::ResolutionKind::Discarded,
                        Outcome::Buffered => reject_commit::ResolutionKind::Buffered,
                    };
                    // D1 — STRUCTURED domain facts, never a Debug string: a
                    // `{:?}` rendering has no stability guarantee, and this
                    // payload is read directly by the browser.
                    let payload = serde_json::json!({
                        "island_seq": seq.0.to_string(), // CWC-A2
                        "events": match &outcome {
                            Outcome::Applied { events } => serde_json::to_value(events)?,
                            _ => serde_json::json!([]),
                        },
                        "discard_reason": match &outcome {
                            Outcome::Discarded { reason } => {
                                serde_json::json!(discard_reason_wire(reason))
                            }
                            _ => serde_json::Value::Null,
                        },
                    });
                    // The PER-WRITE half. `event_category`, the digest and the
                    // turn counter are no longer stamped here — the aggregate
                    // and the node own those now, so a forgotten one is
                    // impossible rather than unlikely.
                    let meta = serde_json::json!({
                        "input_id": input_id.0.to_string(),
                        "admission_notrun_stages": notrun,
                    });
                    let pos = reject_commit::commit_resolution(
                        &dp_backend,
                        &chan_ctx,
                        reality_bind::now_ms().map_err(|e| anyhow::anyhow!("{e}"))?,
                        args.channel,
                        aggregate_version,
                        kind,
                        payload,
                        &meta,
                    )
                    .map_err(|e| anyhow::anyhow!("{e}"))?;
                    aggregate_version += 1;
                    committed += 1;
                    println!(
                        "COMMIT {} → channel_event_id {pos} ({:?})",
                        msg.id, kind
                    );
                    to_ack.push(msg.id.clone());
                }
            }
        }
        bus.ack(&to_ack).await?;
        if args.drain_once {
            break;
        }
    }

    println!("\n== spine report ==");
    println!("consumed  : {consumed}");
    println!("admitted  : {admitted}");
    println!("rejected  : {rejected} (schema/dedup/vocabulary — acked, recorded)");
    println!("committed : {committed} channel-ordered events under epoch {}", writer.lease().epoch);
    println!("turn      : {} (rejections advanced NOTHING — EVT-V4)",
             turn_number.load(Ordering::SeqCst));
    println!("pel depth : {}", bus.pel_len().await?);
    println!("island    : applied={} metrics-accounted={}", isle.metrics().applied, isle.metrics().accounted());
    Ok(())
}
