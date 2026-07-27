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

use commit_service::admission::{admit_t6, AdmissionOutcome, DedupCache, Verdict};
use commit_service::bus::{BusConfig, ProposalBus};
use commit_service::{Actor, CombatDomain, CombatRules, CombatState, Vocabulary, COMBAT_V1_JSON};
use dp_kernel::channel::{acquire_writer_lease, ChannelId, ChannelWriter};
use dp_kernel::envelope::EventEnvelope;
use sim_core::{EntityId, Island, IslandId, Lane, Outcome, RulesetDigest, SeenWindow, StepStatus};
use sqlx::postgres::PgPoolOptions;
use uuid::Uuid;

struct Args {
    redis_url: String,
    pg_url: String,
    reality: Uuid,
    channel: i64,
    drain_once: bool,
}

fn parse_args() -> anyhow::Result<Args> {
    let mut redis_url = "redis://127.0.0.1:6399/0".to_string();
    let mut pg_url = None;
    let mut reality = None;
    let mut channel = 1i64;
    let mut drain_once = false;
    let argv: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < argv.len() {
        match argv[i].as_str() {
            "--redis-url" => { redis_url = argv[i + 1].clone(); i += 2; }
            "--pg-url" => { pg_url = Some(argv[i + 1].clone()); i += 2; }
            "--reality" => { reality = Some(argv[i + 1].parse()?); i += 2; }
            "--channel" => { channel = argv[i + 1].parse()?; i += 2; }
            "--drain-once" => { drain_once = true; i += 1; }
            other => anyhow::bail!("unknown arg {other}"),
        }
    }
    Ok(Args {
        redis_url,
        pg_url: pg_url.ok_or_else(|| anyhow::anyhow!("--pg-url required"))?,
        reality: reality.ok_or_else(|| anyhow::anyhow!("--reality <uuid> required"))?,
        channel,
        drain_once,
    })
}

/// Map the kernel's `DiscardReason` onto the game-wire closed set
/// (`turn.schema.json#/$defs/DiscardDetail`). Exhaustive by construction: a
/// 6th kernel variant fails to compile here rather than reaching a client as
/// an unknown string.
fn discard_reason_wire(r: &sim_core::DiscardReason) -> &'static str {
    use sim_core::DiscardReason as D;
    match r {
        D::Duplicate => "duplicate",
        D::PreconditionFailed(_) => "precondition_failed",
        D::Superseded => "superseded",
        D::Expired => "expired",
        D::Quarantined => "quarantined",
    }
}

fn now_rfc3339() -> String {
    // Host-side wall clock (the kernel never sees it) — commit timestamps
    // are commit-service's job. Seconds precision suffices for the spine.
    let secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .expect("clock after epoch")
        .as_secs();
    let days = secs / 86_400;
    let (mut y, mut rem_days) = (1970i64, days as i64);
    loop {
        let leap = (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;
        let len = if leap { 366 } else { 365 };
        if rem_days < len { break; }
        rem_days -= len;
        y += 1;
    }
    let leap = (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;
    let months = [31, if leap {29} else {28}, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    let mut m = 0;
    while rem_days >= months[m] { rem_days -= months[m]; m += 1; }
    let (h, mi, s) = ((secs / 3600) % 24, (secs / 60) % 60, secs % 60);
    format!("{y:04}-{:02}-{:02}T{h:02}:{mi:02}:{s:02}Z", m + 1, rem_days + 1)
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let args = parse_args()?;
    let vocab = Vocabulary::from_json(COMBAT_V1_JSON)?;

    // ── durability side: lease + fenced writer (dp-kernel SDK) ──
    let pool = Arc::new(PgPoolOptions::new().max_connections(4).connect(&args.pg_url).await?);
    let lease = acquire_writer_lease(&pool, args.reality, ChannelId(args.channel)).await?;
    let writer = ChannelWriter::new(pool.clone(), args.reality, lease);
    println!("lease acquired: channel {} epoch {}", args.channel, lease.epoch);

    // ── resolution side: the island (encounter demo state) ──
    let npc = EntityId(1);
    let mut state = CombatState::default();
    state.actors.insert(npc, Actor::new(100));
    state.actors.insert(EntityId(2), Actor::new(40));
    state.actors.insert(EntityId(3), Actor::new(40));
    let mut isle: Island<CombatDomain> = Island::new(
        IslandId(args.channel as u64),
        0x53A5_71DE,
        Arc::new(CombatRules { strike_damage: 10 }),
        RulesetDigest([0u8; 32]),
        SeenWindow::TtlTicks(300),
        state,
    );
    isle.spawn_entity(npc);
    isle.spawn_entity(EntityId(2));
    isle.spawn_entity(EntityId(3));

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

    let (mut consumed, mut admitted, mut rejected, mut committed, mut aggregate_version) =
        (0u64, 0u64, 0u64, 0u64, 0u64);
    // DP-A17 turn counter for this channel: an APPLIED resolution advances
    // it; a validator rejection NEVER does (EVT-V4 — "turn_number /
    // fiction_clock do NOT advance"; the player retries without burning a
    // turn slot). Seeded 0 = "never advanced".
    let mut turn_number: u64 = 0;

    loop {
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

            let record = admit_t6(body, &vocab, &mut dedup);
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
                    let input_id = input.input_id;
                    isle.submit(Lane::Live, *input);
                    while isle.step() != StepStatus::Idle {}
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
