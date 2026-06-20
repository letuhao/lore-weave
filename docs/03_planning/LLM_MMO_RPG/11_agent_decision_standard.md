# 11 — Agent Decision Standard & SDK

> **Status:** DRAFT — 2026-06-20. The **unifying contract** for how *any* controllable actor's
> decisions are produced, bounded, and authorized — so a single actor can be driven by an **LLM agent
> or a cheap "dumb" agent interchangeably** (the cost lever) and the **bounded vocabulary fences LLM
> chaos** (the safety lever). Formalizes a pattern that currently exists only **implicitly, scattered**
> across AIT_001, COMB_001, COMB_002 (TG-A4), NPC_002, PL_002, PL_005, and 05 LLM-safety.
> **Decisions** `AGT-D1..D8`; axioms `AGT-A1..A6`. The existing scattered pieces are declared
> **instances** of this standard (§6), not separate inventions.

---

## 1. Why this exists

Two goals the design *achieves in practice but never standardized*:
1. **Cost** — drive most NPCs with cheap deterministic AI, reserve the LLM for the few that matter, and
   **swap drivers without changing anything downstream**.
2. **Chaos-bounding** — an LLM actor must only ever emit a decision from a **closed, validated set**;
   it can never invent state changes or go off-script.

Today both are handled *locally and repeatedly* — COMB_001's `ActionDecl`, TG-A4's `stance` enum,
PL_002's tool-call allowlist, NPC_002's Pydantic-validated output, AIT_001's per-tier capability matrix,
05's A5 "state changes never from LLM output". Same idea, six reimplementations, no shared contract,
and **disconnected from the MCP-first invariant**. This doc is the missing contract.

---

## 2. The Agent Decision Interface (ADI)

> **AGT-A1 — Every controllable actor decides through one contract:** `decide(DecisionContext) →
> Decision`. A **Decision** is a **tool-call drawn from the context's published allowed set** —
> `{ tool: ToolId, target: Option<TargetRef>, params: BoundedParams }` — never free-form.

```
DecisionContext = {
  actor, role, situation,                  // who, in what capacity, perceivable (AOI-scoped) state
  allowed_tools: Vec<ToolSchema>,           // THE closed set for this (actor, role, context)
  goal_hint,                                // optional drive/personality (IDF_003) for richer drivers
}
Decision = { tool: ToolId ∈ allowed_tools, target, params }   // validated against allowed_tools
```

The `allowed_tools` set is the heart of the standard — it is simultaneously the **chaos limiter**
(an LLM can only pick from it) and the **driver-agnostic surface** (a script picks from the same set).

---

## 3. The bounded vocabulary *is* a tool set (the MCP-first bridge)

> **AGT-A2 — The allowed-tool set per `(actor-role, context)` is defined ONCE as MCP tools on the
> owning domain service** (combat-service, interaction-service, …). A decision outside the set is
> **rejected → context fallback** (the per-context safe default: e.g. `Defend` in combat, silence in
> dialogue). This single mechanism subsumes PL_002's allowlist, AIT_001's capability matrix, COMB's
> `ActionDecl`, TG-A4's `stance`, and 05's A5-D3 (§6).

> **AGT-A4 — MCP-first compliance via one tool contract, four fill methods.** Because the vocabulary
> *is* a tool set, the standard satisfies the enforced **MCP-first invariant** cleanly:
> - **LlmDriver** invokes the tools **through `ai-gateway` as MCP tool-calls** — the LLM's agentic
>   action-selection is federated exactly as the invariant requires.
> - **ScriptDriver / EngineDriver / HumanDriver** call the **same domain tools locally** — they are not
>   agentic LLM logic, so MCP-first does not apply, yet they hit the identical validated contract.
>
> The tool's *schema*, *validation*, and *state effect* live once on the domain service; only the
> **decision source** differs. (No carve-out needed; the PRR-20-style exception is avoided.)

The action vocabularies are **scoped per role + context** — which also clarifies A5-D3: a *player's
narration LLM* gets a non-state-changing set `{speak, gesture, emote}` (can't mutate state — the
confused-deputy guard), while an *NPC's actor-driver* gets that NPC's tier-appropriate set
`{strike, skill, speak, …}` (it legitimately acts, subject to validation). Same mechanism, different set.

---

## 4. Pluggable drivers — the cost lever

> **AGT-A3 — Four drivers implement `decide()` against the same tool set; the driver is assigned per
> actor/tier and is swappable at runtime.** Swapping LLM ↔ script changes **cost, not contract**.

| Driver | How it decides | Cost | Default tier (AIT_001) |
|---|---|---|---|
| **HumanDriver** | player UI maps gestures → tool-calls | — | PC |
| **LlmDriver** | assemble context + tool schemas → LLM (via ai-gateway MCP) → validated tool-call | $$ tokens | Major NPC |
| **ScriptDriver** | behavior-tree / utility-AI / rule-table picks a tool-call from the allowed set | cheap CPU | Minor NPC |
| **EngineDriver** | statistical bulk-resolve (no per-actor decision) | ≈0 | Untracked NPC / swarm |

**This is the answer to "use LLM agent or dumb AI to reduce cost":** an actor's driver is just a field;
`Major` runs the LlmDriver, `Minor` runs a ScriptDriver that emits the *same* `Decision` shape against
the *same* tools. Nothing downstream (validation, authority, replay, narration) knows or cares which.

> **AGT-A6 — A Decision is a *request*, never a write.** It is emitted as a **Proposal** (EVT-T6); the
> domain validator + commit-service authorize and execute it (**DP-A6**, **EVT-V\***). The driver picks
> intent; the engine owns the effect. This is the same authority spine as 08 RTM-A3 (LLM-zero-state),
> COMB LLM-zero-math, and TG LLM-zero-space — now stated once for all agents.

---

## 5. Cost model — driver assignment & the budget governor

> **AGT-D5 (cost model):**
> - **Tier → driver default:** Untracked=Engine · Minor=Script · Major=Llm · PC=Human (AIT_001).
> - **Dynamic promotion / demotion:** *engagement* promotes an NPC's driver up (an ambient Untracked NPC
>   the player talks to or fights becomes Minor/Major); *disengagement* demotes it back. This is the
>   same sparse-cost principle already locked in **DF05** (95% ambient, zero LLM) and **ILR-A3** (ambient
>   zone-placed vs engaged live).
> - **Budget governor (ties to S6 LLM cost controls):** a per-reality/session **token budget** caps how
>   many actors may run the LlmDriver concurrently; on overflow, lowest-priority Major NPCs **demote to
>   ScriptDriver** (graceful degradation — they keep acting, just cheaply). No actor ever stalls for budget.

The cost lever is therefore continuous, not binary: the world can host millions of EngineDriver actors,
thousands of ScriptDriver actors, and a budget-capped handful of LlmDriver actors — all through one ADI.

---

## 6. Determinism & replay

> **AGT-D6:** ScriptDriver + EngineDriver are **deterministic** (seeded where they roll). The LlmDriver
> is non-deterministic, so its **chosen tool-call is recorded as the canonical Decision** (Proposal →
> validated → committed). **Replay replays the recorded Decision — it never re-prompts the LLM** —
> consistent with EVT-A8 (flavor not in the event log) + the proposal bus. Swapping a driver changes
> *future* decisions only; past committed decisions replay identically (TDIL-A9 preserved).

---

## 7. The existing pieces, declared as instances (`AGT-D8`)

These stop being separate inventions and become **conformant implementations** of this standard:

| Existing | Is an instance of |
|---|---|
| AIT_001 tier capability matrix | the per-`(actor,context)` `allowed_tools` set (AGT-A2) + driver assignment (AGT-A3) |
| COMB_001 `ActionDecl` (5 verbs) + 3-layer AIDecisionLayer | a combat `allowed_tools` set + the driver dispatch (AGT-A1/A3) |
| COMB_002 TG-A4 `stance` enum | a *positioning* tool sub-vocabulary, engine-resolved (AGT-A2) |
| NPC_002 Chorus (AssemblePrompt → validated ActionDecl, fallback Defend) | the **LlmDriver** reference implementation (AGT-A3) + reject-fallback (AGT-A2) |
| PL_002 §7.4 tool-call allowlist | the `allowed_tools` enforcement (AGT-A2) |
| 05 A5-D3 ("state never from LLM output") | role-scoped vocabularies + AGT-A6 authority |

Future features (dialogue trees, quests, economy sim, faction politics, daily-life routines) get the
ADI for free — define their `allowed_tools` set as domain MCP tools, pick a driver per actor, done.

---

## 8. SDK shape

The contract is **language-neutral**, defined in `contracts/agent/` (sibling to `contracts/prompt/`,
`contracts/events/`), with per-language driver implementations (Rust kernel/engine, Python roleplay,
TS game-server) — matching the language rule:

```
// contracts/agent/  (schema; shared)
ToolSchema { id, params_schema, target_kinds, domain_service }
DecisionContext { actor, role, situation, allowed_tools, goal_hint }
Decision { tool, target, params }

trait Driver { fn decide(ctx: DecisionContext) -> Decision }   // 4 impls
   LlmDriver    (python/roleplay) -> ai-gateway MCP tool-call
   ScriptDriver (rust/engine)     -> local behavior-tree/utility-AI
   EngineDriver (rust/engine)     -> local statistical bulk-resolve
   HumanDriver  (ts/game-server)  -> UI gesture → tool-call

// every Decision -> Proposal (EVT-T6) -> EVT-V* validate -> commit (DP-A6)
```

---

## 9. Decisions (RESOLVED 2026-06-20)

| # | Decision | Resolution |
|---|---|---|
| **AGT-D1** | Unified decision interface | ✅ `decide(DecisionContext) → Decision`; Decision = validated tool-call from the context's allowed set (AGT-A1). |
| **AGT-D2** | Bounded vocabulary | ✅ Per-`(actor-role, context)` closed tool set = the chaos limiter; reject → context fallback (AGT-A2). |
| **AGT-D3** | Pluggable drivers | ✅ Llm / Script / Engine / Human; per-tier, runtime-swappable = the cost lever (AGT-A3). |
| **AGT-D4** | MCP-first bridge | ✅ **Decision interface = tool interface** — LlmDriver via ai-gateway MCP; others call same domain tools locally. No carve-out (AGT-A4). |
| **AGT-D5** | Cost model | ✅ Tier→driver default + engagement promote/demote (DF05/ILR-A3) + S6 budget governor (overflow → demote to Script). |
| **AGT-D6** | Determinism | ✅ Script/Engine seeded; LlmDriver decision **recorded & replayed, never re-prompted**; swaps future-only. |
| **AGT-D7** | Authority | ✅ Decision is a Proposal; commit-service authorizes/executes (DP-A6, EVT-V\*); driver never writes state (AGT-A6). |
| **AGT-D8** | Subsumes existing | ✅ AIT_001 / COMB_001 / COMB_002 / NPC_002 / PL_002 / 05-A5 declared instances (§7). |

---

## 10. Cross-references

- AI tiers / capability matrix — [`features/16_ai_tier/`](features/16_ai_tier/) (AIT_001)
- Combat decision layer / vocabularies — [`features/18_combat/`](features/18_combat/) (COMB_001 §4, COMB_002 TG-A4)
- NPC LLM driver reference — `features/05_npc_systems/` (NPC_002 Chorus)
- Command allowlist — [`features/04_play_loop/PL_002_command_grammar.md`](features/04_play_loop/PL_002_command_grammar.md)
- LLM safety / A5 — [`05_llm_safety/`](05_llm_safety/)
- Authority spine — [`07_event_model/`](07_event_model/) (DP-A6, EVT-T6, EVT-V\*) · [`08_realtime_movement_authority.md`](08_realtime_movement_authority.md) (RTM-A3)
- LLM cost controls — [`02_storage/S06_llm_cost_controls.md`](02_storage/S06_llm_cost_controls.md)
- MCP-first invariant — root `CLAUDE.md`
- Decisions / IDs — [`decisions/locked_decisions.md`](decisions/locked_decisions.md) · [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md)
