# Agent Decision Contract (`contracts/agent/`)

The shared contract behind the **Agent Decision Standard**
([`docs/03_planning/LLM_MMO_RPG/11_agent_decision_standard.md`](../../docs/03_planning/LLM_MMO_RPG/11_agent_decision_standard.md),
AGT-A1..A6) and the REC-55(d) resolution: **the bounded vocabularies are proposal-schemas —
declared here, served as tool schemas to the model by `ai-gateway`, executed by NOBODY.**
A tool-call never runs anything; it *is* the Decision proposal (EVT-T6 payload), validated at
admission by `commit-service` and resolved by `sim-core`.

## Files

| File | What |
|---|---|
| [`decision.schema.json`](decision.schema.json) | The `Decision` envelope every driver emits (AGT-A1: `decide(ctx) → Decision`) |
| [`vocabularies/combat_v1.json`](vocabularies/combat_v1.json) | The combat closed tool set (COMB_001 action set; TG-A4 stances engine-resolved) |

## Rules (LOCKED by the standard)

1. **Closed set** — a Decision naming a tool outside its context's vocabulary is REJECTED and the
   context fallback commits instead (`fallback_tool`, e.g. `defend` in combat). Never silent.
2. **Closed args** — every argument with a finite value set is an `enum` in the schema
   (the Frontend-Tool-Contract lesson applied to agent tools: a free string where an enum belongs
   is how `panel:"editor"` silently no-oped).
3. **One vocabulary, four drivers** — LlmDriver receives these as model tool schemas via
   ai-gateway; Script/Engine/Human drivers emit the same `Decision` shape locally. Swapping a
   driver changes cost, never contract (AGT-A3).
4. **Proposal, not effect** (AGT-A6) — nothing in this directory is an executable endpoint.
   Validation + effect live with commit-service/sim-core (DP-A6, EVT-V*).
5. **Versioned vocabularies** — a vocabulary file is immutable once consumed; changes ship as
   `*_v2.json`. The consumer pins the version it validated against.
