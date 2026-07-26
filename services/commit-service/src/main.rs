//! POC-2 turn runner — drives N LLM-decided NPC turns through the full
//! sanctioned chain and prints the numbers the POC exists to produce:
//! tokens/turn · latency p50/p95 · validity rate · fallback rate.
//!
//! Usage (stack up + lm_studio running):
//! ```text
//! LOREWEAVE_INTERNAL_TOKEN=… LOREWEAVE_GATEWAY_URL=http://localhost:8085 \
//!   cargo run -p commit-service --bin poc2-turn-runner -- \
//!   --model-ref <user_model_id uuid> --user-id <owner uuid> [--turns 10]
//! ```
//! `user_id` = the reality OWNER (REC-59: the author pays for NPC spend).

use std::sync::Arc;

use commit_service::{
    decide, Actor, CombatDomain, CombatPayload, CombatRules, CombatState, DecisionContext,
    Vocabulary, COMBAT_V1_JSON,
};
use loreweave_llm::{GatewayClient, ModelSource, ReasoningEffort};
use sim_core::{
    Class, EntityId, Fallback, Gen, InputId, Island, IslandId, Lane, Producer, QueuedInput,
    RulesetDigest, SeenWindow, Seq, StepStatus, Tick,
};
use uuid::Uuid;

struct Args {
    model_ref: Uuid,
    user_id: Uuid,
    turns: u32,
    model_source: ModelSource,
    deadline_ms: u64,
    reasoning: ReasoningEffort,
}

fn parse_args() -> anyhow::Result<Args> {
    let mut model_ref = None;
    let mut user_id = None;
    let mut turns = 10u32;
    let mut model_source = ModelSource::UserModel;
    let mut deadline_ms = 30_000u64;
    let mut reasoning = ReasoningEffort::None;

    let argv: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < argv.len() {
        match argv[i].as_str() {
            "--model-ref" => {
                model_ref = Some(argv.get(i + 1).ok_or_else(|| anyhow::anyhow!("--model-ref needs a value"))?.parse()?);
                i += 2;
            }
            "--user-id" => {
                user_id = Some(argv.get(i + 1).ok_or_else(|| anyhow::anyhow!("--user-id needs a value"))?.parse()?);
                i += 2;
            }
            "--turns" => {
                turns = argv.get(i + 1).ok_or_else(|| anyhow::anyhow!("--turns needs a value"))?.parse()?;
                i += 2;
            }
            "--platform-model" => {
                model_source = ModelSource::PlatformModel;
                i += 1;
            }
            "--deadline-ms" => {
                deadline_ms = argv.get(i + 1).ok_or_else(|| anyhow::anyhow!("--deadline-ms needs a value"))?.parse()?;
                i += 2;
            }
            "--reasoning" => {
                reasoning = match argv.get(i + 1).map(String::as_str) {
                    Some("none") => ReasoningEffort::None,
                    Some("low") => ReasoningEffort::Low,
                    Some("medium") => ReasoningEffort::Medium,
                    Some("high") => ReasoningEffort::High,
                    other => anyhow::bail!("--reasoning must be none|low|medium|high, got {other:?}"),
                };
                i += 2;
            }
            other => anyhow::bail!("unknown arg: {other}"),
        }
    }
    Ok(Args {
        model_ref: model_ref.ok_or_else(|| anyhow::anyhow!("--model-ref <user_model_id uuid> is required (resolve: SELECT user_model_id, alias FROM user_models WHERE owner_user_id=... AND is_active)"))?,
        user_id: user_id.ok_or_else(|| anyhow::anyhow!("--user-id <uuid> is required (the reality owner — REC-59)"))?,
        turns,
        model_source,
        deadline_ms,
        reasoning,
    })
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let args = parse_args()?;
    let client = GatewayClient::from_env()?;
    let vocab = Vocabulary::from_json(COMBAT_V1_JSON)?;

    // Encounter island: 1 LLM-driven NPC vs 2 script-driven hostiles.
    let npc = EntityId(1);
    let hostiles = [EntityId(2), EntityId(3)];
    let mut state = CombatState::default();
    state.actors.insert(npc, Actor::new(100));
    state.actors.insert(hostiles[0], Actor::new(40));
    state.actors.insert(hostiles[1], Actor::new(40));

    let mut isle: Island<CombatDomain> = Island::new(
        IslandId(1),
        0x00C0_B0A7u64, // fixed seed — replay-exact runs
        Arc::new(CombatRules { strike_damage: 10 }),
        RulesetDigest([0u8; 32]),
        SeenWindow::Unbounded,
        state,
    );
    isle.spawn_entity(npc);
    for h in hostiles {
        isle.spawn_entity(h);
    }

    let mut dispatches = Vec::new();
    let mut fallbacks = 0u32;
    let mut input_seq = 0u128;

    println!("== POC-2 LLM decision vertical — {} turns ==", args.turns);
    for turn in 0..args.turns {
        if !isle.state().actors[&npc].alive() {
            println!("turn {turn}: encounter over (npc downed or fled)");
            break;
        }
        let ctx = DecisionContext::from_state(isle.state(), npc, &hostiles);
        if ctx.candidates.is_empty() {
            println!("turn {turn}: encounter over (no live hostiles)");
            break;
        }

        // The LlmDriver dispatch races the SL-A4 deadline.
        let dispatch = match tokio::time::timeout(
            std::time::Duration::from_millis(args.deadline_ms),
            decide(&client, args.model_source, args.model_ref, args.user_id, &vocab, &ctx, args.reasoning),
        )
        .await
        {
            Ok(d) => d,
            Err(_) => commit_service::Dispatch {
                reject: Some(format!("deadline {}ms elapsed (AGT-A2 timeout)", args.deadline_ms)),
                latency_ms: args.deadline_ms as u128,
                tokens_unknown: true,
                ..Default::default()
            },
        };

        // Valid proposal or the vocabulary fallback (AGT-A2) — via the
        // kernel's Substitute machinery either way, so an island-side
        // precondition failure ALSO lands on Defend.
        let (payload, used_fallback) = match &dispatch.payload {
            Some(p) => (p.clone(), false),
            None => {
                fallbacks += 1;
                (vocab.fallback_payload(npc), true)
            }
        };

        input_seq += 1;
        isle.submit(Lane::Live, QueuedInput {
            seq: Seq(u64::MAX),
            input_id: InputId(input_seq),
            class: Class::B,
            source: Producer::LlmDecision,
            payload,
            preconditions: vec![sim_core::Precondition::EntityAlive {
                id: npc,
                generation: isle.entity_gen(npc).unwrap_or(Gen(0)),
            }],
            on_invalid: Fallback::Substitute(vocab.fallback_payload(npc)),
            admitted_gen: Gen(0),
            deadline: Some(Tick(u64::MAX)),
        });
        while isle.step() != StepStatus::Idle {}

        // Scripted hostile retaliation (same Decision SHAPE, ScriptDriver
        // tier — AGT-A3: swapping the driver changes cost, not contract).
        for h in hostiles {
            if isle.state().actors.get(&h).map(|a| a.alive()).unwrap_or(false) {
                input_seq += 1;
                isle.submit(Lane::Live, QueuedInput {
                    seq: Seq(u64::MAX),
                    input_id: InputId(input_seq),
                    class: Class::B,
                    source: Producer::ScriptDecision,
                    payload: CombatPayload::Strike { attacker: h, target: npc },
                    preconditions: vec![],
                    on_invalid: Fallback::Drop,
                    admitted_gen: Gen(0),
                    deadline: None,
                });
            }
        }
        while isle.step() != StepStatus::Idle {}
        isle.tick(1);

        println!(
            "turn {turn}: tool={:?} valid={} fallback={} in={} out={} reasoning={:?} {}ms{}",
            dispatch.raw_tool,
            dispatch.payload.is_some(),
            used_fallback,
            dispatch.input_tokens,
            dispatch.output_tokens,
            dispatch.reasoning_tokens,
            dispatch.latency_ms,
            dispatch.reject.as_ref().map(|r| format!("  REJECT: {r}")).unwrap_or_default(),
        );
        dispatches.push(dispatch);
    }

    // ── the numbers POC-2 exists to produce ──
    // Token averages EXCLUDE timeout rows: their counts are unknown
    // client-side (the provider still burned them), and averaging zeros in
    // silently flatters cost/turn.
    let valid = dispatches.iter().filter(|d| d.payload.is_some()).count();
    let counted: Vec<_> = dispatches.iter().filter(|d| !d.tokens_unknown).collect();
    let n = counted.len().max(1) as u64;
    let unknown = dispatches.len() - counted.len();
    let total_in: u64 = counted.iter().map(|d| d.input_tokens as u64).sum();
    let total_out: u64 = counted.iter().map(|d| d.output_tokens as u64).sum();
    let mut lat: Vec<u128> = dispatches.iter().map(|d| d.latency_ms).collect();
    lat.sort_unstable();
    let p = |q: f64| lat.get(((lat.len() as f64 * q) as usize).min(lat.len().saturating_sub(1))).copied().unwrap_or(0);

    println!("\n== POC-2 report ==");
    println!("turns dispatched      : {}", dispatches.len());
    println!("validity rate         : {}/{} ({:.0}%)", valid, dispatches.len(), 100.0 * valid as f64 / dispatches.len().max(1) as f64);
    println!("fallback rate         : {fallbacks}/{} ({:.0}%)", dispatches.len(), 100.0 * fallbacks as f64 / dispatches.len().max(1) as f64);
    println!("tokens/turn (avg)     : {} in + {} out (over {} measured turns{})",
        total_in / n, total_out / n, counted.len(),
        if unknown > 0 { format!("; {unknown} timeout turn(s) EXCLUDED — tokens unknown client-side, provider still burned them") } else { String::new() });
    println!("tokens total (counted): {} in + {} out", total_in, total_out);
    println!("latency p50 / p95     : {}ms / {}ms", p(0.50), p(0.95));
    println!("cost                  : $0 on a local BYOK model; for priced models multiply tokens by the provider-registry pricing row (never a literal here — no-hardcoded-pricing rule)");
    println!("island outcomes       : applied={} discarded={} substituted={}",
        isle.metrics().applied, isle.metrics().discarded_total(), isle.metrics().substituted);
    println!("npc hp                : {:?}", isle.state().actors[&npc].hp);
    Ok(())
}
