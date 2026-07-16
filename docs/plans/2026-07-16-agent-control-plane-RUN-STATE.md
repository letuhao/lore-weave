# RUN-STATE — Agent Control Plane SDK + Practice + First-run

Spec (SEALED): [`docs/specs/2026-07-16-agent-control-plane-sdk.md`](../specs/2026-07-16-agent-control-plane-sdk.md).
Companion (SEALED): [`docs/specs/2026-07-15-agent-task-governance.md`](../specs/2026-07-15-agent-task-governance.md) (the engine; ACP is the socket).

## 0 · Resuming after a compaction — do THIS first
Re-READ this file, then `git log --oneline -12`, then the spec §3 (sealed decisions) + §7 (phases). Never
re-litigate a sealed decision from memory — re-read it here.

## 1 · The commitment (PO-sealed 2026-07-16)
Make the agent control/governance layer a **consumable standard** (contracts + per-language SDK + existing
service surfaces), so chat is its FIRST consumer (dogfood) and roleplay/Practice is the SECOND, with
**zero control logic added to roleplay-service**. Sequencing = **EXTRACT-FIRST** (A0→A3 before A4).

## 2 · Standing invariants (never lower silently)
- **No new god-service** (ACP-7) — extract into contracts + libs + EXISTING services, never a 2nd monolith.
- **Contract machine-checked on EVERY side** (ACP-6) — a renamed charter field REDs Rust + both Python suites.
- **roleplay stays a pure PRODUCER** — it gains charter fields only; no executive/drive/enforcement there.
- **Language rule I3** — Python SDK for chat/knowledge, Rust crate for roleplay/game; HTTP for stateful.
- **Invariants pass-through** (ACP-11) — probes are `/internal` grant-checked reads; tenancy scope-keys required; models per-user via provider-registry; no hardcoded model.
- **Dogfood-or-not-real** (ACP-8) — if chat can't cleanly consume the SDK, fix the SDK, not chat.

## 3 · SLICE BOARD (done = a pasted evidence string, NOT a checkmark)
| Slice | Deliverable | Size | Status | Evidence |
|---|---|---|---|---|
| **A0** | R1 contracts moved→`contracts/agent-control/` (git mv + redirect, ONE commit — RW-1) + **`executive.{init,tick}` + probe-eval schemas (RW-6, the PRIMARY real gap — 2 live consumers)** + `WorkflowDefinition`/`EffectRef`/`Verdict` (governance data-model) · R2 enforce on all 3 sides — knowledge `jsonschema` test + roleplay Rust test on **real `charter::freeze()` output** (RW-8) · spec corrections applied (ACP-5 game-server=TS RV-M2; ACP-11/18 llm_judge per-user RV-M1; ACP-14/15 owner server-pinned RV-M3; RW-9 trust-model RV-M8) | M | ⬜ | DoD: a renamed charter field REDs the Rust test (on real freeze output) AND both Python tests (pasted); executive init/tick contract present + checked; the `executive.tick` contract requires a server-authenticated `user_id` (RV-M8) |
| **A1** | R3 Python SDK `sdks/python/loreweave_agent_control` (verdict machine + anchor render + predicate parse extracted, injected endpoints RW-11); **chat AND knowledge-service both import it** (RV-H1 — `merge_state` lives in knowledge; §4 boundary: `merge_state`=lib fn, `run_executive`/repo stay in knowledge); **checkpoint repo owner-scoped: `update_state` gets `AND user_id=$2`, drop `get(user_id=None)`, owner non-optional** (RV-H4) | M | ⬜ | DoD: chat's WM+rail tests green importing the SDK **+ a characterization golden** byte-identical for `next_actionable_step`/`render_pinned` (chat) AND `merge_state` (knowledge suite) (RW-2/RV-H1, pasted); a checkpoint read/write cross-owner attempt is REJECTED (RV-H4 test, pasted) |
| **A2** | R4 harness (`on_session_start/user_turn/tool_result/yield`) — **verdict-only, consumer owns the loop** (RW-3; RV-H3 `on_yield` carries probe-client+nudge-counters+enforcement, returns `{hold\|release,directive,giving_up,drove}`); **runs the SET of active programs SEQUENCED (exec tick → rail drive), preserving today's both-fire behavior** (RV-H2, not single-active); **voice path wired through the harness tick+drive** (RV-M7, PO: fix now); executive state-write monotonic under a **per-session ADVISORY LOCK** (RV-M6, OCC forbidden by RW-12) | M | ⬜ | DoD (all pasted): a live chat turn drives identically; a **multi-turn drive characterization** nudge→nudge→give-up + escape phrase (RV-H3); a **both-eligible session fires both programs** (RV-H2); a **concurrent double-submit** doesn't clobber state (RV-M6); a **voice** session advances state + wraps (RV-M7); NO migration (RW-12) |
| **A3** | R5 Rust crate `crates/contracts-agent-control` (charter/state types validated vs schema + thin executive/probe HTTP client); roleplay `/start` produces via it | M | ⬜ | DoD: roleplay `/start` round-trips a charter the crate validated vs the shared schema (pasted) |
| **A4** | Practice: `question_target` **OPTIONAL+defaulted**, migration order schema→consumer→producer (RW-7); **add `question_target` to chat's `WorkingMemoryCharter` Pydantic model** (RV-M4 — else `extra='ignore'` drops it) · control-layer enforcement: the **executive computes `question_count`/`elapsed_min`/`wrap` INTO `state`** (schema.json state fields added first, JSONB so no migration); **`render_pinned` reads them from `wm.state`, signature UNCHANGED** (RV-M5, keeps A1 golden valid) · mobile FE (entry, PersonaPicker, timed session + Q-progress, ScorecardView) | L | ⬜ | DoD (pasted): Practice works with ZERO control logic in roleplay (RV-L2: this holds today — it's not the reusability proof); a present `question_target` **round-trips through `parse_working_memory`** into the anchor (RV-M4); a live interview wraps at 5/at-budget in-container (text AND voice, RV-M7); an old charter w/o `question_target` still valid |
| **A5** | R6 `docs/standards` entry + README row · ACP-10 autonomous-mode drive interface + unit-proven park path | S | ⬜ | DoD: standard discoverable; an autonomous-mode hold PARKs (unit-proven, pasted) |
| **FR** | Frame 13 first-run compose (independent track): first-run screen + `assistantFirstRunDone` pref gate + wire existing `DELETE /v1/assistant/data` erase | M | ⬜ | DoD: first-run shows once, consent OFF default, tz-confirm, erase wired; FE tests green (pasted) |

## 4 · Decisions register (append sealed calls)
- 2026-07-16 · EXTRACT-FIRST sequencing (OQ-3). · Autonomous drive = interface+park now (OQ-4). · Python SDK = new pkg (OQ-1). · Rust = hand-write+validate-in-test (OQ-2).
- 2026-07-16 · The interview "executive" already exists in knowledge-service (Python) — the roleplay `rp_memory` "executive=v2" comment is STALE. A Rust executive would DUPLICATE it → rejected in favour of extend+consume.
- 2026-07-16 · **4-agent web-research pass folded into the spec (ACP-14..20 + §16).** Adopted interface shapes: MemoryStore+CheckpointSaver (tenancy=namespace, tier=enum) · durable-step snapshot-on-outbox (DBOS-piggyback + idempotency + WFQ pause) · 4-part enforcement surface (hooks + wrap-interceptors + guardrail/tripwire + typed run-context) · `effect_verified` as the flagship output-guardrail · OTel `gen_ai.*` + `effect.*` trace/eval schema. **Interface shapes land in A0–A2; heavy impls demand-gated** (D-ACP-DURABLE/MULTIAGENT/TRACE/GRAPH). Validated moat: grounded effect-verification > LLM-judge (the observability tier lacks it).
- **A0–A2 scope note:** A0 contracts now ALSO define the MemoryStore/CheckpointSaver/Guardrail/trace schemas (shape-only); A1 the Python SDK exposes the memory two-contract split + names `consolidate`; A2 the harness carries the 4-part surface + emits OTel `gen_ai.*` + the `effect_verified` guardrail. No heavy durable/A2A/trace-studio impl in A0–A4.
- 2026-07-16 · **PO reviewed a 3-agent cold-start red-team and chose: KEEP EXTRACT-FIRST full scope + FIX the voice executive now** (against the review's re-scope recommendation). ⇒ ALL confirmed findings become BUILD REQUIREMENTS (spec §18, RV-H1..H4 / RV-M1..M8 / RV-L1..L3), not defer-justifications. Voice (RV-M7) is now a build deliverable, not a waiver. The N=1-dogfood-≠-reusability truth (RV-L2) is acknowledged in the DoDs.

## 5 · Parked register (each with a gate)
- **D-ACP-EXT-ADAPTER** — an adapter binding an EXTERNAL agent framework (LangGraph / LangChain / CrewAI /
  Claude-Agent-SDK) onto the ACP hook port (ACP-13). **Gate #4-external:** build ONLY when a real external
  consumer exists — no speculative binding. The SDK port is *designed* adapter-ready now (A1/A2); the adapter
  itself is demand-pulled. Any such adapter stays bound by provider-gateway + MCP-first + tenancy (EC-8).
- **D-ACP-DURABLE** (W1, the top competitive gap) — wire the ACP `ActivePlan` onto the EXISTING durable
  substrate (outbox/saga/WFQ) for resume-at-exact-step + replay, so a crashed background/game agent resumes
  deterministically (LangGraph/Temporal parity). **Gate:** the first AUTONOMOUS consumer (background
  task-agent / game logic). It's WIRING (substrate exists), not greenfield; folds into ACP-10's autonomous path.
- **D-ACP-GRAPH / D-ACP-MULTIAGENT / D-ACP-TRACE** (W2/W3/W5) — WorkflowDefinition-as-DAG · a governed-handoff
  primitive · a replayable run-trace/eval studio. **Gate:** each demand-pulled by a real branchy / multi-agent /
  eval-heavy consumer. Building ahead = the `build-for-an-absent-consumer` anti-pattern.

## 6 · Debt / drift log (append as you go — an empty drift log at the end is dishonest)
- **DRIFT (near-miss caught by review) — the spec over-reached.** I designed a full agent-control-plane SDK standard off 4-agent research, for consumers that don't exist yet (background/game runtimes), and sealed EXTRACT-FIRST — front-loading speculative extraction (verdict-machine, harness, memory/durable/OTel contracts) with N=1 real consumer, ahead of the one real feature (Practice). Three independent cold-start reviews converged: over-scoped, AND the extraction hides real traps (RV-H1 `merge_state` in the wrong service; RV-H2 the two control programs aren't mutually exclusive → the single-`control_program` model was a silent narrowing; RV-H3 `on_yield` is far more entangled than "hold\|release"; RV-H4 checkpoint write not owner-scoped). **Lesson: research-enthusiasm inflated the scope; the cold-start review (isolation = the product) caught what my own anchored analysis (RW-1..12) missed.** PO chose to keep the ambitious scope with every finding folded in as a requirement; the honest de-risk (RV-L3) is that Practice is independently buildable if the extraction stalls.

## 7 · Checkpoints
- PO checkpoint after A3 (SDK extracted + dogfooded) and after A4 (Practice live). Commit per slice with pasted evidence.
