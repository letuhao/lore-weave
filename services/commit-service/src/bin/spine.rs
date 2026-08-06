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
use commit_service::producer::ProducerRegistry;
use commit_service::bus::{BusConfig, ProposalBus};
use commit_service::hostclock::now_rfc3339;
use commit_service::wire::discard_reason_wire;
use commit_service::{epoch_commit, epoch_signal};
use commit_service::combat::Side;
use commit_service::{Actor, CombatDomain, CombatState, Vocabulary, COMBAT_V1_JSON};
use dp_kernel::channel::{acquire_writer_lease, ChannelId, ChannelWriter};
use dp_kernel::envelope::EventEnvelope;
use sim_core::{EntityId, Island, IslandId, Lane, Outcome, SeenWindow, StepStatus};
use sqlx::postgres::PgPoolOptions;
use uuid::Uuid;

struct Args {
    redis_url: String,
    pg_url: String,
    reality: Uuid,
    channel: i64,
    drain_once: bool,
    /// F2 — the reality layer's TOML. Absent = the engine default, which is
    /// the bootstrap floor, NOT a silent fallback: the digest still describes
    /// exactly the rules in force, and the startup line says which.
    ruleset: Option<String>,
    /// Root for the ruleset state: `<root>/content` (immutable, content-
    /// addressed) and `<root>/bindings` (mutable `reality -> digest`). The two
    /// are separate directories on purpose — a binding MOVES on an epoch switch,
    /// and mutable state inside a content-addressed store is a category error.
    ruleset_state: Option<String>,
    /// The META DB. Present ⇒ the reality's ruleset binding lives in
    /// `reality_ruleset_binding` (Q1 B2, append-only, one row per epoch) instead
    /// of a TOML file. Absent ⇒ files, which is what every offline tool and the
    /// existing smokes want and is why this is an OPTION rather than a
    /// replacement: a node with no meta DB reachable should fail loudly at
    /// startup, not fall back to a private file and run different rules from its
    /// neighbours.
    meta_url: Option<String>,
    /// The polyglot allowlist SoT that MetaWrite validates against.
    meta_allowlist: String,
    /// Resolve the layer stack, store it, and bind this reality to it — ONCE.
    /// Without this flag the binary only LOADS, which is what a running node
    /// does.
    create_reality: bool,
}

fn parse_args() -> anyhow::Result<Args> {
    let mut redis_url = "redis://127.0.0.1:6399/0".to_string();
    let mut pg_url = None;
    let mut reality = None;
    let mut channel = 1i64;
    let mut drain_once = false;
    let mut ruleset = None;
    let mut ruleset_state = None;
    let mut create_reality = false;
    let mut meta_url = None;
    let mut meta_allowlist = "contracts/meta/events_allowlist.yaml".to_string();
    let argv: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < argv.len() {
        match argv[i].as_str() {
            "--redis-url" => { redis_url = argv[i + 1].clone(); i += 2; }
            "--pg-url" => { pg_url = Some(argv[i + 1].clone()); i += 2; }
            "--reality" => { reality = Some(argv[i + 1].parse()?); i += 2; }
            "--channel" => { channel = argv[i + 1].parse()?; i += 2; }
            "--drain-once" => { drain_once = true; i += 1; }
            "--ruleset" => { ruleset = Some(argv[i + 1].clone()); i += 2; }
            "--ruleset-state" => { ruleset_state = Some(argv[i + 1].clone()); i += 2; }
            "--create-reality" => { create_reality = true; i += 1; }
            "--meta-url" => { meta_url = Some(argv[i + 1].clone()); i += 2; }
            "--meta-allowlist" => { meta_allowlist = argv[i + 1].clone(); i += 2; }
            other => anyhow::bail!("unknown arg {other}"),
        }
    }
    Ok(Args {
        redis_url,
        pg_url: pg_url.ok_or_else(|| anyhow::anyhow!("--pg-url required"))?,
        reality: reality.ok_or_else(|| anyhow::anyhow!("--reality <uuid> required"))?,
        channel,
        ruleset,
        ruleset_state,
        create_reality,
        meta_url,
        meta_allowlist,
        drain_once,
    })
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let args = parse_args()?;
    let vocab = Vocabulary::from_json(COMBAT_V1_JSON)?;

    // ── durability side: lease + fenced writer (dp-kernel SDK) ──
    let pool = Arc::new(PgPoolOptions::new().max_connections(4).connect(&args.pg_url).await?);
    let lease = acquire_writer_lease(&pool, args.reality, ChannelId::unverified(args.channel)).await?;
    let writer = ChannelWriter::new(pool.clone(), args.reality, lease);
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
        args.reality,
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
    // DP-A17 turn counter for this channel: an APPLIED resolution advances
    // it; a validator rejection NEVER does (EVT-V4 — "turn_number /
    // fiction_clock do NOT advance"; the player retries without burning a
    // turn slot). Seeded 0 = "never advanced".
    let mut turn_number: u64 = 0;

    loop {
        // BEFORE the proposals, every iteration including the first. Ahead of
        // them because an epoch switch changes the rules the batch about to be
        // stepped will be validated against, and running the reconcile on the
        // FIRST iteration is what closes the boot race — the consumer group was
        // created at `$`, so an activation between the boot read and the group's
        // creation reaches this node only through the table.
        epoch_commit::drain_and_reconcile(
            &mut signals, &boot, args.reality, args.channel, &mut isle, &writer,
            &mut aggregate_version, turn_number,
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
                    // just logged — the doc-15 "t2_write" outcome. It rides
                    // the channel's audit order but does NOT advance
                    // turn_number (EVT-V4).
                    aggregate_version += 1;
                    let env = EventEnvelope {
                        event_id: Uuid::new_v4(),
                        event_type: "proposal.rejected".into(),
                        event_version: 1,
                        aggregate_id: format!("enc-{}", args.channel),
                        aggregate_type: "combat_session".into(),
                        aggregate_version,
                        reality_id: args.reality,
                        occurred_at: now_rfc3339(),
                        recorded_at: now_rfc3339(),
                        payload: serde_json::json!({
                            "rejected_at_stage": stage,
                            "reason": reason,
                        }),
                        metadata: Some(serde_json::json!({
                            "event_category": "T6",
                            // CWC-A2 — u64 leaves as a decimal STRING (the
                            // browser consuming this via the publisher loses
                            // precision on a JSON number past 2^53).
                            "turn_number": turn_number.to_string(), // NOT advanced
                        })),
                        // RLS-A13 — the pin, taken from the island that produced
                        // this, not from a config value that could describe a
                        // different ruleset. `isle.digest` is DERIVED from the
                        // rules the island actually runs (Domain::rules_digest),
                        // so the value written here cannot describe anything else.
                        ruleset_digest: Some(isle.digest.to_hex()),
                    };
                    let appended = writer.append(&env, &serde_json::json!([])).await?;
                    println!(
                        "REJECT-COMMIT [{stage}] {} → channel_event_id {} (turn stays {turn_number}) — {reason}",
                        msg.id, appended.channel_event_id
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
                    aggregate_version += 1;
                    // DP-A17: only an APPLIED resolution consumes the turn.
                    if matches!(outcome, Outcome::Applied { .. }) {
                        turn_number += 1;
                    }
                    let env = EventEnvelope {
                        event_id: Uuid::new_v4(),
                        event_type: match &outcome {
                            Outcome::Applied { .. } => "turn.resolved".into(),
                            Outcome::Discarded { .. } => "turn.discarded".into(),
                            Outcome::Buffered => "turn.buffered".into(),
                        },
                        event_version: 1,
                        aggregate_id: format!("enc-{}", args.channel),
                        aggregate_type: "combat_session".into(),
                        aggregate_version,
                        reality_id: args.reality,
                        occurred_at: now_rfc3339(),
                        recorded_at: now_rfc3339(),
                        // D1 — STRUCTURED domain facts, never a Debug string.
                        // A `{:?}` rendering has no stability guarantee, so a
                        // consumer parsing one is parsing a bug; this payload
                        // is read directly by the browser.
                        payload: serde_json::json!({
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
                        }),
                        // D4: EVT envelope fields ride metadata until v2.
                        metadata: Some(serde_json::json!({
                            "event_category": "T6",
                            "input_id": input_id.0.to_string(),
                            "admission_notrun_stages": notrun,
                            // CWC-A2 — decimal string, never a number.
                            "turn_number": turn_number.to_string(),
                        })),
                        // RLS-A13 — see the reject path above. Same island, same
                        // derived pin: every event this writer commits carries the
                        // digest of the rules that actually resolved it.
                        ruleset_digest: Some(isle.digest.to_hex()),
                    };
                    let appended = writer.append(&env, &serde_json::json!([])).await?;
                    committed += 1;
                    println!(
                        "COMMIT {} → channel_event_id {} ({})",
                        msg.id, appended.channel_event_id, env.event_type
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
    println!("turn      : {turn_number} (rejections advanced NOTHING — EVT-V4)");
    println!("pel depth : {}", bus.pel_len().await?);
    println!("island    : applied={} metrics-accounted={}", isle.metrics().applied, isle.metrics().accounted());
    Ok(())
}
