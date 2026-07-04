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

---

## Broader run — 4 fact types, LIGHT target, blind judge (2026-07-04)

The single-fact test above is the best case (one named entity). This broader run stresses
it: **four fact TYPES** (A named entity, B a number pair, C a relationship, D an event)
buried in the brief, **status-op padding** so — with the **T5 gate ON + a Dracula-KG-bound
session** (100 glossary entities populate the known-entity set) — those turns classify
`grounding_needed=False` → the **leaner ~9K light target** (more aggressive than the 14K
heavy). Both arms are gate-ON + Dracula-bound; only the compaction flag differs (clean
isolation). One multi-fact recall turn. Blind judge = a cold-start Agent scoring RUN_A/RUN_B
(unlabeled) on `scripts/eval/judge_prompt.md`.

**Result — mixed (safe but lossy):**

| Arm | Recall budget | Fact-token recall | Confabulation | Judge correctness |
|---|---|---|---|---|
| baseline (raw) | 18,359 tok | **9/9** (incl. "seven star-anchors") | none | **5/5** |
| candidate (light-target compacted) | 5,260 tok (**~69% cut**) | **8/9** — dropped the star-anchor COUNT | **none** | **4/5** |

- Compaction fired at the light target (18,003→**5,643** tok). The FACTS/SYNOPSIS summary
  preserved the name (A), the debt number (B-half), the relationship (C), and the event (D)
  — but **dropped one of the two numbers in fact B** (kept "4,400 salt-marks", lost "seven
  star-anchors"): the summary is lossy under aggressive compaction.
- **Safe failure mode:** the candidate did NOT confabulate — it said *"I do not have
  information regarding how many star-anchors the ritual needs"* rather than inventing a
  number. The blind judge scored `critical_confabulation=false` for both; the
  tokens-down-but-**wrong** trap was avoided.
- **The recovery net went unused:** gemma-4-26b did NOT call `conversation_search` to pull
  the dropped fact back from the raw turns (`tools=[]`). The net exists; the model didn't
  reach for it. **The recovery layer is only as good as the model's propensity to use it.**

**Decision — default STAYS OFF (this run reinforces it, doesn't lift it).** At the aggressive
light target, compaction is *safe* (no confabulation) but *lossy* (a real, if minor,
correctness regression: 4/5 vs 5/5; one buried detail lost). A global default-ON would trade
occasional recall completeness for tokens on every long conversation — a per-deployment
call, not a clear global win. Two concrete unblocks would justify flipping the default:
1. **Prompt the model to use `conversation_search` when compaction has fired this turn** (a
   system hint on the post-compaction turn) — so a dropped fact is recovered, not omitted.
   This is the highest-leverage follow-up (the net is built; the gap is *usage*).
2. A more fact-complete summarizer (larger FACTS budget) — but that costs tokens, eroding
   the win. Measure the tradeoff.

Until then: enable per-deployment where token pressure justifies accepting occasional honest
omissions; the mechanism is proven **safe** (no confabulation) at both the heavy and the
aggressive light target.
