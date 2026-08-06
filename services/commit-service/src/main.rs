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

use commit_service::admission::{admit_t6, AdmissionOutcome, DedupCache};
use commit_service::combat::Side;
use commit_service::{
    decide, Actor, CombatDomain, CombatState, DecisionContext, RealityRules,
    Vocabulary, COMBAT_V1_JSON,
};
use loreweave_llm::{GatewayClient, ModelSource, ReasoningEffort};
use sim_core::{RulesetEpoch, 
    EntityId, Island, IslandId, Lane, SeenWindow, StepStatus,
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
    // F1 — the reality's resolved ruleset. `engine_default()` is RLS-D2's
    // priority-0 layer; F2 replaces this line with a real resolution through
    // the provider stack (preset -> book -> reality overrides).
    //
    // The island DERIVES its pin from these rules via `Domain::rules_digest`
    // (RLS-A13) — this call site used to pass `RulesetDigest([0u8; 32])`
    // alongside the rules, which was inert AND unchecked: an all-zero digest
    // made two realities with different rules stamp indistinguishable events,
    // and nothing forced the digest passed to describe the rules passed. There
    // is no longer a digest argument to get wrong.
    // `M1` — the PROVING-GROUND preset, not `engine_default`. The engine default
    // declares no quantities and no pools (QTY-A10(c) is why it must not), so it
    // binds none of the three engine roles and a domain built on it has laws
    // with no numbers. `RealityRules::resolve` refuses exactly that, here, where
    // the message is readable.
    let ruleset = std::sync::Arc::new(RealityRules::resolve(
        ruleset_loader::proving_ground().map_err(|e| anyhow::anyhow!("{e}"))?,
    )?);

    let mut state = CombatState::default();
    state.actors.insert(npc, Actor::spawn(&ruleset, npc, Side::A));
    for h in hostiles {
        // Spawned at the reality's declared opening value, then WOUNDED by the
        // feature — which is the division of labour `M1` establishes: content
        // declares what a being starts with, the feature decides what happens
        // to it afterwards. Before `M1` this was a constructor argument, so a
        // caller could hand an actor a ceiling nothing had declared.
        let mut a = Actor::spawn(&ruleset, h, Side::B);
        a.set_vital(&ruleset, 40);
        state.actors.insert(h, a);
    }

    let mut isle: Island<CombatDomain> = Island::new(
        IslandId(1),
        0x00C0_B0A7u64, // fixed seed — replay-exact runs
        // A demo runner with no reality binding at all: it builds
        // `engine_default` in-process, so epoch 1 is the truth here rather
        // than a default that might be wrong. The spine, which DOES have a
        // binding, reads the epoch from it.
        RulesetEpoch(1),
        Arc::clone(&ruleset),
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
    // EVT-L3 dedup, same cache the bus path uses.
    let mut dedup = DedupCache::new(std::time::Duration::from_secs(60));

    println!("== POC-2 LLM decision vertical — {} turns ==", args.turns);
    for turn in 0..args.turns {
        if !isle.state().actors[&npc].alive(&ruleset) {
            println!("turn {turn}: encounter over (npc downed or fled)");
            break;
        }
        let ctx = DecisionContext::from_state(isle.state(), &ruleset, npc, &hostiles);
        if ctx.candidates.is_empty() {
            println!("turn {turn}: encounter over (no live hostiles)");
            break;
        }

        // The LlmDriver dispatch races the SL-A4 deadline.
        let dispatch = match tokio::time::timeout(
            std::time::Duration::from_millis(args.deadline_ms),
            decide(
                &client,
                args.model_source,
                args.model_ref,
                args.user_id,
                &vocab,
                &ruleset.rules().verbs,
                &ctx,
                args.reasoning,
            ),
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

        // Whether the DRIVER produced a usable tool call. Distinct from
        // whether admission accepted it — both are now reported, because a
        // driver that answers and an answer that survives validation are two
        // different success rates and conflating them hid the gap.
        let used_fallback = dispatch.payload.is_none();
        if used_fallback {
            fallbacks += 1;
        }

        // IAS-D3 — the runner used to build a `QueuedInput` and hand it to the
        // island directly, which made this the one path in the service that
        // skipped admission entirely. `Island::submit` now takes an
        // `Admitted<D>` token that only `admission` mints, so the bypass no
        // longer compiles; the decision goes through the same gate the bus
        // path uses. That is also strictly MORE faithful than before, since
        // the raw LLM output is now re-validated at the admission boundary
        // rather than trusted from `decide()`'s in-process check.
        input_seq += 1;
        let proposal = serde_json::json!({
            "producer_service": "poc2-turn-runner",
            "proposal_id": format!("poc2-{input_seq}"),
            "target_channel": 1,
            "actor": npc.0,
            "candidates": ctx.candidates.iter().map(|c| (c.id.0, c.token.clone())).collect::<Vec<_>>(),
            "decision": {
                "vocabulary": "combat_v1",
                "tool": dispatch.raw_tool.clone().unwrap_or_default(),
                "params": serde_json::from_str::<serde_json::Value>(&dispatch.raw_arguments)
                    .unwrap_or(serde_json::json!({})),
            },
        });
        match admit_t6(&proposal.to_string(), &vocab, &ruleset.rules().verbs, &mut dedup).outcome {
            AdmissionOutcome::Admitted(a) => {
                isle.submit(Lane::Live, *a);
            }
            AdmissionOutcome::Rejected { stage, reason } => {
                // AGT-A2 fallback, now reached through the SAME rejection path
                // production uses rather than a parallel in-process branch.
                if !used_fallback {
                    fallbacks += 1; // rejected a driver answer that looked fine
                }
                println!("turn {turn}: admission rejected at {stage}: {reason} — fallback");
                let fb = serde_json::json!({
                    "producer_service": "poc2-turn-runner",
                    "proposal_id": format!("poc2-fb-{input_seq}"),
                    "target_channel": 1,
                    "actor": npc.0,
                    "candidates": Vec::<(u64, String)>::new(),
                    "decision": {"vocabulary": "combat_v1", "tool": "defend", "params": {}},
                });
                if let AdmissionOutcome::Admitted(a) =
                    admit_t6(&fb.to_string(), &vocab, &ruleset.rules().verbs, &mut dedup).outcome
                {
                    isle.submit(Lane::Live, *a);
                }
            }
        }
        while isle.step() != StepStatus::Idle {}

        // Scripted hostile retaliation (same Decision SHAPE, ScriptDriver
        // tier — AGT-A3: swapping the driver changes cost, not contract).
        for h in hostiles {
            if isle.state().actors.get(&h).map(|a| a.alive(&ruleset)).unwrap_or(false) {
                input_seq += 1;
                let hp = serde_json::json!({
                    "producer_service": "poc2-script-driver",
                    "proposal_id": format!("poc2-h-{input_seq}"),
                    "target_channel": 1,
                    "actor": h.0,
                    "candidates": [[npc.0, format!("hostile-{}", npc.0)]],
                    "decision": {
                        "vocabulary": "combat_v1", "tool": "strike",
                        "params": {"target": format!("hostile-{}", npc.0)},
                    },
                });
                if let AdmissionOutcome::Admitted(a) =
                    admit_t6(&hp.to_string(), &vocab, &ruleset.rules().verbs, &mut dedup).outcome
                {
                    isle.submit(Lane::Live, *a);
                }
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
    println!("npc vital             : {:?}", isle.state().actors[&npc].vital(&ruleset));
    Ok(())
}
