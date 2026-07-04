# T2/D3 — task-elastic compaction trigger (live A/B, 2026-07-04)

**Change:** compaction can now fire at the task-elastic **soft target**
(`token_budget.compute_target`, a fraction of the window far below it) instead of only at
the flat `0.75×effective_limit` (near the window). `task_weight` is driven by the T5
intent signal — a grounding turn (lore/continuity) stays roomy (`1.0` → surface_max), a
status-op / smalltalk turn uses `compact_light_task_weight` (leaner). Gated by
`COMPACT_TASK_ELASTIC_ENABLED` (**default OFF** — a behavior change whose safety rests on
the D6 recovery net: FACTS/SYNOPSIS summary + `conversation_search` + the story_state Core
Block).

**The question the handoff flagged:** does compacting *far earlier* preserve answer
quality, or does it drop facts a later turn needs? (The token-thesis was called
"weakened / quality-risky".) This is the live A/B that answers it.

## Setup

- **Model:** `google/gemma-4-26b-a4b-qat` (the always-loaded LM Studio model), driven via
  the **40K-window** registration `019eeb08` (same underlying model, no extra VRAM) so the
  soft target (~14K heavy) is reachable in a short scripted conversation. On the 200K
  registration the target is ~32K — impractical to reach in an eval.
- **Scenario** (`scripts/eval` style, plant→pad→recall): turn 1 is a ~14.5K-token
  worldbuilding brief with a distinctive fact **buried mid-brief** — *"the protagonist's
  secret blade is 'Verithrax', forged on the Third Moon of Kestrel by the smith Oldan
  Vex"*. Turns 2–5 are short creative asks (pad the history past `keep_recent=8` messages
  so the brief exits the verbatim tail and enters the summarizable middle). Turn 6 recalls
  the buried fact.
- **Arms:** baseline = `COMPACT_TASK_ELASTIC_ENABLED=false` (flat 28K trigger); candidate
  = `true` (soft ~14K target). T5 gate OFF → every turn `grounding_needed=True` → the
  **conservative heavy** target (14K), not the leaner light one.

## Result — PASS

| Arm | Compaction | Recall-turn budget | Recall (Verithrax / Third Moon of Kestrel / Oldan Vex) |
|---|---|---|---|
| baseline (flat 28K) | never fired (17K < 28K) | **17,858 tok** | ✅ all three (from the raw brief) |
| candidate (soft 14K) | **fired at turn 4** (17,468→**4,674**) | **4,838 tok** | ✅ all three (from the summary FACTS; `tool_calls=[]`) |

- **~73% fewer context tokens** on the post-compaction turns (17.8K → 4.8K), with **zero
  quality loss** — the buried mid-brief fact survived compaction.
- The candidate recalled it **from the FACTS/SYNOPSIS summary alone** — it did not even
  need `conversation_search` (the recovery net was there as a backstop but the T6/D6
  summarizer already preserved the fact). Compaction latency: the summarizer LLM call added
  ~5s on the single turn it fired.

## A bug the live run caught (fixed)

The flag-ON path referenced `_grounding_presence` at the compaction site, but that local
lives in `stream_response` while compaction runs in `_emit_chat_turn` (a different
function) — `NameError` on every flag-ON turn. Unit tests missed it (none exercise the
flag-ON stream path); the first candidate run surfaced it immediately. Fixed to read
`grounding_needed` from the `entity_presence` telemetry dict `_emit_chat_turn` already
receives (default `True` = roomy/safe). Classic "live proof catches what mocks miss".

## Verdict + why default stays OFF

The **mechanism and the conservative (heavy) target are validated**: compacting at the
soft target preserves a buried named-fact via the summary, for a large token win. Default
stays **OFF** pending a broader gate, because default-ON is a fleet-wide behavior change:

1. **One scenario / one fact type.** Validated a buried *named entity*; numbers,
   relationships, and multi-fact recall need a broader judge run before default-ON.
2. **Light target unvalidated.** The leaner `compact_light_task_weight` target (~9K) —
   which needs the T5 gate ON to engage — compacts even more aggressively and was not
   exercised here.
3. **Summarizer-call frequency = cost/latency.** Firing at ~14–32K instead of ~146K means
   the summarizer LLM call runs on *many more* conversations. That added cost/latency
   across all users needs weighing before a global flip.
4. **Model-dependent value.** On big-window models (200K) the target is ~32K and
   conversations rarely reach it → near-no-op. The real win is on **small-window** models
   / very long sessions.

**Recommendation:** safe to enable **per-deployment**, especially for small-window models;
flip the global default only after a broader multi-fact-type + light-target judge run and a
summarizer-frequency cost check. The wiring is correct, unit-tested, flag-gated, and now
live-proven on the core mechanism.
