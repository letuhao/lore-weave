//! The AGT-A3 **LlmDriver** — `decide(ctx) → Decision`, dispatched through
//! the platform's sanctioned chain: `loreweave_llm` SDK →
//! provider-registry `/internal/llm/stream` (the REC-54c amendment: the
//! caller originates; ai-gateway is tool-federation only and has no LLM
//! surface).
//!
//! Pattern mirrored from `tilemap-service/src/harness/mod.rs` — incl.
//! select-the-tool-call-by-NAME-never-`.first()` (a provider may stream an
//! echo call at a lower index).
//!
//! The driver returns a PROPOSAL (AGT-A6): nothing here executes. The caller
//! validates → submits to the island; on reject/timeout the vocabulary
//! fallback commits instead (AGT-A2), via the same S1b Substitute machinery.

use std::time::Instant;

use loreweave_llm::{
    ChatStreamRequest, GatewayClient, ModelSource, ReasoningEffort, StreamEvent, StreamFormat,
    ToolCallAccumulator,
};
use serde_json::json;
use sim_core::EntityId;
use uuid::Uuid;

use crate::domain::{CombatPayload, CombatState, RealityRules};
use crate::vocabulary::{Reject, Vocabulary};

/// What the engine offers the model (THR-A4 shape: vague labels, no raw
/// state — the model cannot name an entity it was not offered).
#[derive(Debug, Clone)]
pub struct DecisionContext {
    pub actor: EntityId,
    pub actor_label: String,
    pub actor_hp: (i64, i64),
    pub defending: bool,
    /// The ONLY legal strike targets this turn (THR-A4: engine offers,
    /// model chooses).
    pub candidates: Vec<Candidate>,
}

/// One offered target. `token` is BARE identity (`hostile-2`) — the value
/// `strike.target` must echo verbatim; `condition` travels beside it in the
/// prompt, never inside it (live-smoke finding: a combined label made every
/// strike reject because the model echoes identity and drops state).
#[derive(Debug, Clone)]
pub struct Candidate {
    pub id: EntityId,
    pub token: String,
    pub condition: &'static str,
}

/// The hp-band descriptor offered NEXT TO an id token (never inside it).
pub fn hp_band(hp: i64, max_hp: i64) -> &'static str {
    match (hp * 100) / max_hp.max(1) {
        67.. => "healthy",
        34..=66 => "wounded",
        _ => "critical",
    }
}

impl DecisionContext {
    /// Build the context from island state. Candidates are offered as a
    /// clean ID TOKEN plus a SEPARATE hp-band descriptor ("healthy" /
    /// "wounded" / "critical" — never numeric, flat token cost).
    ///
    /// Live-smoke finding (POC-2 run 1): a combined label
    /// `"hostile-2 (healthy)"` made every strike reject — the model
    /// naturally echoes the identity token and strips the state
    /// parenthetical. Identity and state must be separate fields; `target`
    /// matches the id token alone.
    pub fn from_state(
        state: &CombatState,
        rules: &RealityRules,
        actor: EntityId,
        hostiles: &[EntityId],
    ) -> Self {
        let a = &state.actors[&actor];
        let candidates = hostiles
            .iter()
            .filter_map(|id| {
                let h = state.actors.get(id)?;
                if !h.alive(rules) {
                    return None;
                }
                Some(Candidate {
                    id: *id,
                    token: format!("hostile-{}", id.0),
                    condition: hp_band(h.vital(rules), h.vital_ceiling(rules)),
                })
            })
            .collect();
        Self {
            actor,
            actor_label: format!("npc-{}", actor.0),
            actor_hp: (a.vital(rules), a.vital_ceiling(rules)),
            defending: a.defending,
            candidates,
        }
    }
}

/// Everything one dispatch produced — the decision (if valid) plus the
/// numbers POC-2 exists to measure. Failure is DATA here, never an `Err`:
/// a reject/timeout resolves through the fallback, and the incident is the
/// metric (mirrors tilemap's `L3Attempt` discipline).
#[derive(Debug, Default)]
pub struct Dispatch {
    pub payload: Option<CombatPayload>,
    pub reject: Option<String>,
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub reasoning_tokens: Option<u32>,
    pub latency_ms: u128,
    pub finish_reason: Option<String>,
    pub raw_tool: Option<String>,
    pub raw_arguments: String,
    /// True when the dispatch was cut off client-side (deadline). Token
    /// counts are then UNKNOWN, not zero — the provider still burned them
    /// server-side; reports must exclude these rows from token averages
    /// (the S3 meter counts via `provider.call.completed` instead).
    pub tokens_unknown: bool,
}

const SYSTEM_PROMPT: &str = "You are the combat decision-maker for one NPC in a turn-based RPG. \
You MUST respond with exactly one tool call chosen from the provided tools — no prose. \
Pick tactically: strike when a target is exposed, defend when hurt and pressed, \
move to reposition, flee only when critical. \
For strike, `target` MUST be copied verbatim from the offered candidates list.";

/// One LlmDriver dispatch: context → sanctioned chain → validated proposal.
/// `reasoning` bounds the provider's hidden thinking — `None` (the default
/// for Minor/Major NPC combat picks) is the AGT-D5 cost lever at the
/// request level.
pub async fn decide(
    client: &GatewayClient,
    model_source: ModelSource,
    model_ref: Uuid,
    user_id: Uuid,
    vocab: &Vocabulary,
    verbs: &ruleset_core::VerbTable,
    ctx: &DecisionContext,
    reasoning: ReasoningEffort,
) -> Dispatch {
    let user_payload = json!({
        "you": {
            "id": ctx.actor_label,
            "condition": hp_band(ctx.actor_hp.0, ctx.actor_hp.1),
            "defending": ctx.defending,
        },
        // id and state as SEPARATE fields — `strike.target` must equal `id`
        // verbatim (live-smoke finding: a combined label made every strike
        // reject because the model echoes identity and drops the state).
        "hostiles": ctx.candidates.iter()
            .map(|c| json!({"id": c.token, "condition": c.condition}))
            .collect::<Vec<_>>(),
        "instruction": "Choose exactly one action tool now. For strike, target must equal a hostile id verbatim.",
    });
    let request = ChatStreamRequest::new_chat_with_tools(
        model_source,
        model_ref,
        vec![
            json!({"role": "system", "content": SYSTEM_PROMPT}),
            json!({"role": "user", "content": user_payload.to_string()}),
        ],
        vocab.openai_tools(),
        StreamFormat::Openai,
    )
    // "required": the model must call SOME tool but chooses which — that is
    // the whole point of a bounded vocabulary (vs tilemap's forced single).
    .with_tool_choice(json!("required"))
    // A 4-tool combat pick needs no hidden essay: unbounded thinking burned
    // 150–900 reasoning tokens per decision and occasionally blew the 30 s
    // deadline (POC-2 rounds 1–2). `none` is the verified LM-Studio
    // off-switch; the kwargs toggle covers llama.cpp/vLLM-style backends.
    .with_reasoning_effort(reasoning)
    .with_chat_template_kwargs(json!({
        "enable_thinking": !matches!(reasoning, ReasoningEffort::None)
    }))
    // Belt-and-braces against runaway generation regardless of reasoning.
    .with_max_tokens(256)
    .normalize();

    let mut out = Dispatch::default();
    let started = Instant::now();

    let mut handle = match client.stream(request, user_id).await {
        Ok(h) => h,
        Err(e) => {
            out.reject = Some(format!("opening the gateway stream: {e}"));
            out.latency_ms = started.elapsed().as_millis();
            return out;
        }
    };

    let mut acc = ToolCallAccumulator::new();
    while let Some(ev) = handle.next().await {
        match ev {
            Ok(event) => {
                acc.push(&event);
                match event {
                    StreamEvent::Usage { input_tokens, output_tokens, reasoning_tokens } => {
                        out.input_tokens = input_tokens;
                        out.output_tokens = output_tokens;
                        out.reasoning_tokens = reasoning_tokens;
                    }
                    StreamEvent::Done { finish_reason } => {
                        out.finish_reason = finish_reason.map(|f| format!("{f:?}"));
                    }
                    _ => {}
                }
            }
            Err(e) => {
                out.reject = Some(format!("stream error: {e}"));
                break;
            }
        }
    }
    out.latency_ms = started.elapsed().as_millis();

    // Select by NAME within the closed set — never `.first()`.
    let calls = acc.finish();
    let call = calls
        .iter()
        .find(|c| c.name.as_deref().is_some_and(|n| vocab.contains(n)));
    let Some(call) = call else {
        if out.reject.is_none() {
            let seen: Vec<_> = calls.iter().filter_map(|c| c.name.clone()).collect();
            out.reject = Some(
                Reject::NoToolCall(format!(
                    "{:?}; off-vocabulary calls: {seen:?}",
                    out.finish_reason
                ))
                .to_string(),
            );
        }
        return out;
    };

    out.raw_tool = call.name.clone();
    out.raw_arguments = call.arguments.clone();
    let offered: Vec<(EntityId, String)> =
        ctx.candidates.iter().map(|c| (c.id, c.token.clone())).collect();
    match vocab.validate(
        ctx.actor,
        call.name.as_deref().unwrap_or_default(),
        &call.arguments,
        &offered,
        verbs,
    ) {
        Ok(payload) => out.payload = Some(payload),
        Err(reject) => out.reject = Some(reject.to_string()),
    }
    out
}
