# S06 FLAGSHIP re-run — "I have a story in my head" · gemma-4-26b-a4b-qat

**Date / stack / model_ref:** 2026-07-11 · local docker stack (chat-service + ai-gateway
**rebuilt to HEAD** first) · `019ebb72-27a2-72f3-a42d-d2d0e0ded179` (Gemma-4 26B-A4B QAT, 200K).
**Fixture:** a fresh, empty book `019f4f8a-bf66-7e40-9680-345378bbc05e` (origin from nothing),
torn down after. **Permission mode:** write · **enabled_skills:** [] (a naive user pins nothing).
**Driver:** `scripts/eval/run_discoverability_scenario.py` · scenario `S06-flagship.json` (17 turns).
**This closes WS-D6 / DoD #5** (`docs/specs/2026-07-09-mcp-tool-liveness-eval/TRACK-D.md`).

## Verdict: ✅ — the flagship now persists, and the lie is gone

The 2026-07-09 baseline was Track D's founding failure: gemma stayed a pure-conversation co-writer
for all 17 turns, called **ZERO tools**, persisted **nothing**, and *narrated as if it were building*
("I have locked that into the core of the project"). Metrics: `effectful_tool_calls: 0`,
`persist_claims_without_write` non-empty.

The re-run, on the same scenario and model with Track A's mechanism fixes deployed, reverses both:

| Signal | Baseline (07-09) | Re-run (07-11) |
|---|---|---|
| **`persist_claims_without_write`** (the false-"done" lie) | non-empty | **`[]` in 6/6 runs** |
| **`empty_intent_find_tools`** (find_tools thrash) | — | **0 in all runs** |
| **`effectful_tool_calls`** | **0** | **>0 in 4/5 warm runs** (DB-verified) |

## Cold vs warm — the headless-driver artifact, made explicit

A headless driver cannot click an approval card, so a correctly-called Tier-A/W write **suspends**
(`ok:None`) and can never land. The driver documents this; the two passes separate the concerns:

- **COLD (approvals NOT seeded):** `effectful=0`, but **`persist_claims=0`, `empty_intent=0`,
  `discovery=7`**, and **`unresolved_tool_calls: 1` = `plan_propose_spec` suspended on its
  `tool_approval` card.** The mechanism is correct: gemma did `tool_list(plan)` → `tool_load` →
  *called* `plan_propose_spec` with the fixture `book_id`. The suspend is correct product behavior
  (a real user approves in the GUI) — and it satisfies WS-D2's companion requirement (*prove the
  card appears when not allowlisted*).
- **WARM (approvals pre-seeded in `user_tool_approvals`, per WS-D2):** the write executes.
  5 trials → `effectful ∈ {0, 1, 1, 1, 1}`; **`persist_claims=0` in all 5.** The one 0 is gemma
  choosing not to write that run (model non-determinism), not a mechanism failure.

## DB-verified effect (not a metric artifact)

`loreweave_composition.plan_run` for the fixture book carries real rows written by the tool:
`status=proposed`, `mode=llm`, `model_ref=<gemma>`, each with a full premise the model **synthesized
from the naive user's story** — e.g. *"# Story Concept: The Divinity of Erasure … A woman is murdered
by her fiancé, who uses her essence as fuel to ascend to godhood … the terrifying cost of vengeance
and the loss of self."* This is the "vision-to-book" outcome S06 was built to test.

## Selection vs capability (the handoff's carry-forward)

The write **capability** was already proven ($0 sweep: `plan_propose_spec` executes=true). What the
baseline lacked and the re-run demonstrates is **selection under the mechanism fix**: gemma now finds
and drives a real write in the naive flagship flow, without thrash, without lying. Selection remains
non-deterministic (1/5 warm runs wrote nothing) — a model-behavior property, not a platform bug.

## What made the difference

Track A's mechanism work this validates: the `/v1/responses` tool-args-in-`.done` recovery
(the real "weak model can't add entities" cause), the `tool_list`/`tool_load` discovery triad, the
`find_tools` demotion (WS-6), and the tier-gated write hot-path. The stack was rebuilt to HEAD before
the run so the reading is honest (stale image = false green).

## Macro sweep note

S01–S05 (directed scenarios) were available in the same harness; the flagship S06 is the DoD gate and
is the focus of this report. The full product-level N3 go/no-go additionally depends on Track C
(catalog + UI), which is out of Track D's scope — the **D-side** proof (an LLM persists via tools,
honestly) is what this run establishes.
