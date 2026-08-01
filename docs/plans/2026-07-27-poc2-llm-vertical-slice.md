# Plan — POC-2: LLM decision vertical slice (full service path)

> XL, spec+plan required. PO chose **full service path** (AskUserQuestion 2026-07-27 00:50) over a
> driver-level harness. Deliverable: a **measured cost/turn** (tokens · latency · $ · validity rate)
> for one LLM-driven NPC decision through the sanctioned chain, plus the production-shaped seed of
> the S3 host. Specs: [`15_commit_service.md`](../03_planning/LLM_MMO_RPG/15_commit_service.md)
> (CS-A1..A6, CS-D1..D10) · [`11_agent_decision_standard.md`](../03_planning/LLM_MMO_RPG/11_agent_decision_standard.md)
> (AGT-A1..A6) · REC-54/55/56/59 resolutions ([`19` §12b](../03_planning/LLM_MMO_RPG/19_reconciliation_register.md)).

## The sanctioned chain (REC-54/55/56 — decision-complete)

```
commit-service (Rust, writer-node role, hosts sim-core natively — CS-A5)
   │  LlmDriver: DecisionContext + vocabulary ref
   ▼
ai-gateway (TS — the LLM-Originator; runs the tool-loop)
   │  chat completion w/ proposal-schema tools
   ▼
provider-registry-service (ONLY provider SDK home; BYOK user_models)
   │
   ▼
model (local lm_studio for $0 smoke; gpt-4o available for a real-$ datapoint)

return path: tool_call = the Decision proposal (AGT-A6 — executes NOTHING)
   → commit-service validates against the closed vocabulary
   → valid: QueuedInput{deadline, fallback=Substitute(Defend)} → sim-core island applies
   → invalid/timeout: AGT-A2 reject → context fallback (Defend) — same machinery S1b built
```

## Scope boundaries (thin, production-shaped)

**IN:** `contracts/agent/` scaffolding (Decision envelope + combat_v1 vocabulary, enum-closed);
`services/commit-service` (Rust): LlmDriver + minimal PocCombatDomain (`Domain` impl) + island
hosting + idempotency via the kernel seen-set + measurement; ai-gateway internal decision-dispatch
surface; `language-rule.yaml` row; **panic="unwind" profile for the commit-service host** (the S3
gate item, solved for real); live smoke with a BYOK lm_studio model → the cost/turn number.

**OUT (S3 proper, tracked):** full EVT-V validator pipeline; proposal bus (Redis Streams)
consume/ack/dead-letter; epoch token + event_log durability; DP-A16 writer handoff; AGT-D5 budget
governor (POC records spend; enforcement is S3); REC-59 ledger wiring.

## ⚠ REC-54c AMENDMENT (surface research, 2026-07-27 01:05) — flag for the register

The service-surface sweep (ai-gateway src, provider-registry router, chat-service client code)
establishes that **ai-gateway has NO LLM surface**: it is MCP tool-federation only (5 controllers:
`/mcp`, `/mcp/admin`, `/internal/tools/execute`, `/internal/context/build`, health). The platform's
real sanctioned chain — used by chat-service (Python SDK) and tilemap-service (Rust SDK) alike — is
**caller → `loreweave_llm` SDK → provider-registry `POST /internal/llm/stream`** (SSE; OpenAI-shaped
`tools` regardless of stream_format; `tool_call` events reassembled caller-side; `X-Internal-Token`
raw + `user_id` as QUERY PARAM). The agentic loop is always the CALLER's code, never a gateway
feature ("module header stating the invariant": chat-service `stream_service.py:1-11`).

**Therefore REC-54/55/56(a,c) "ai-gateway is the LLM-Originator / runs the tool-loop" amends to:
the LlmDriver (commit-service) originates the call via the SDK → provider-registry, the identical
chain every other service uses.** MCP-first is not violated: AGT tools are proposal-schemas that
execute nothing (REC-55d) — there is no tool *execution* to federate; ai-gateway remains the home
for executable federated tools should any ever exist. Provider-gateway invariant is satisfied
directly (single SDK home). Precedent: tilemap-service's forced-tool-call harness
(`services/tilemap-service/src/harness/mod.rs:90-170`) is the exact pattern, incl.
select-tool-call-by-NAME-never-first. **Queued for the register alongside the REC-63 amendment.**

Net effect on scope: **no ai-gateway changes at all** — the slice is commit-service + contracts +
registration + live smoke.

## Design calls (final)

1. **Vocabulary = data, not code** — `contracts/agent/vocabularies/combat_v1.json`, closed set
   `{strike, defend, move, flee}` (COMB_001 action set ∩ POC domain), every closed arg an `enum`
   (Frontend-Tool-Contract discipline applied to agent tools). commit-service validates the
   returned tool_call against this file (single source; ai-gateway serves the same schemas to the
   model — REC-55d "served as schemas by ai-gateway, executed by nobody").
2. **PocCombatDomain is the real combat domain's seed** — actors {hp, defending}, strike/defend/
   move/flee semantics minimal but total; lives in commit-service (domain = rules; sim-core =
   scheduling). NOT `sim`'s TestDomain — that stays a chaos harness.
3. **Deadline + fallback are the S1b mechanisms** — the LLM dispatch races a Tick deadline;
   a late/invalid decision commits `Substitute(Defend)` exactly once (the expiry-dedup fix from
   /review-impl S2 is load-bearing here — this is why it was HIGH).
4. **Panic profile:** workspace keeps `[profile.release] panic="abort"`; add
   `[profile.release-commit] inherits="release", panic="unwind"` + a runtime canary test in
   commit-service (mirror of the sim chaos canary). Ship rule: commit-service builds with
   `--profile release-commit`.
5. **No hardcoded model/pricing** — model_ref = `user_model_id` UUID resolved live from
   provider-registry; cost computed from the usage+pricing the chain returns, never a literal.
6. **Registration in the same commit as the service** — `contracts/language-rule.yaml`
   `commit-service: rust`; ARCHITECTURE purpose line. (`_boundaries/` CS rows stay with the
   design-track lock queue — repo-side registration only here.)

## Measurements PRODUCED (2026-07-27, live: provider-registry :8208 → lm_studio Gemma-4 26B-A4B QAT, BYOK, $0)

| Question | Number |
|---|---|
| **cost/turn** (REC-59 unit: one dispatch) | **~360 in + ~330 out tokens/turn** (thinking model; reasoning tokens dominate output). $0 local BYOK; for priced models multiply by the provider-registry pricing row — never a literal. |
| decision latency | **p50 ≈ 2.4–3.1 s** local; p95 = the 30 s deadline (thinking-mode outliers are REAL — turn 3 legitimately took 8.2 s / 899 reasoning tokens) |
| validity rate | **83 % (5/6)** after the contract fix — the one miss was a genuine deadline timeout, not an invalid decision |
| fallback rate | 17 % (1/6), all deadline — **the SL-A4 deadline → Defend fallback is load-bearing, proven live twice** |

**Live-smoke finding (round 1 → the fix):** with candidates offered as combined labels
(`"hostile-2 (healthy)"`), validity was **50 %** — the model echoes the IDENTITY token and strips
the state parenthetical, so every strike rejected as target-not-offered. Fix: candidates offer a
bare id token + a SEPARATE `condition` field; `strike.target` matches the id verbatim. Validity
50 % → 83 %. **This is a THR-A4 contract lesson for the real candidate list: identity and state
must be separate fields.** Flagged for COMB_003's candidate-list shape.

**Observed NPC behavior (round 2):** strike → strike → (timeout→Defend) → strike → defend →
defend as hp fell; downed turn 6 in a 2-v-1. Tactically coherent under a 4-tool vocabulary.

## Bug-fix round (2026-07-27 01:26, user: "solve bug we found first")

Both open report findings root-caused and fixed:

1. **Thinking-runaway timeouts → an SDK MIRROR-DRIFT bug.** The Go gateway and Python SDK both
   carry `reasoning_effort` (`none|low|medium|high`) + `chat_template_kwargs` — with the Python
   comment literally documenting `"none"` as the verified LM-Studio off-switch — but the **Rust
   SDK never got the fields**, so no Rust caller could bound thinking (the exact polyglot-drift
   class CLAUDE.md's machine-contract rule warns about). Fixed: `ReasoningEffort` enum + both
   fields + builders in `loreweave_llm` (absent-from-wire when unset — 2 wire-format regression
   tests); driver defaults to `none` + `max_tokens 256`; runner `--reasoning` flag.
2. **Timeout rows averaged in as 0 tokens** → `Dispatch.tokens_unknown`; the report now excludes
   them from token averages and says so (provider still burned them; S3 meters via
   `provider.call.completed`).

**Live round 3 (reasoning=none):** **validity 5/5 (100 %) · fallback 0 % · 434 in + 14 out
tokens/turn (out: 330→14, 23×) · p50 645 ms / p95 763 ms (was 3 071/30 000) · zero timeouts.**
Tactics stayed coherent: 4 strikes → fled at 30 hp in a 2-v-1. **Cost/turn for a bounded
Minor/Major NPC pick: ~450 total tokens, sub-second locally, $0 BYOK.**

## /review notes (2-stage, self)

- Timeout turns record 0 tokens but the provider still burned them server-side (the aborted
  request completes model-side in lm_studio) — the report under-counts on timeouts. Documented;
  the S3 meter must count via `provider.call.completed`, not client-side usage events.
- A NEW tool added to `combat_v1.json` without extending `Vocabulary::validate`'s match
  degrades SAFELY: it validates as `UnknownTool` → fallback, recorded. Drift is visible, never
  silent. (The compile-time `include_str!` embed forces a rebuild on any contract edit.)
- POC bypasses the proposal bus + EVT-V pipeline by declared scope (S3 proper); the validated
  decision enters the island as a stamped ingress item, honoring DP-R7's
  `llm_output → validate → write` order in miniature.

## Registration done in this commit

`contracts/language-rule.yaml` (`commit-service: rust`) · `docs/ARCHITECTURE.md` Rust table row ·
workspace member + **`[profile.release-commit]` (`panic="unwind"`)** + ship-rule comments ·
`contracts/agent/` scaffolded (README + decision envelope + combat_v1). Design-track `_boundaries/`
CS rows remain with the lock queue. **Register flags queued:** REC-63 (`Quarantined` 5th variant) ·
**REC-54c** (ai-gateway has no LLM surface; LlmDriver originates via SDK → provider-registry —
surface-research-backed) · THR-A4 id/state field separation.
