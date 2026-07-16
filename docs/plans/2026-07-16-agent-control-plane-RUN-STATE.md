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
| **A0** ✅ | R1 contracts moved→`contracts/agent-control/` (RW-1, ea6ae3239) + **`executive.{init,tick}` contracts (RW-6, b3fbdee09)** · R2 charter enforced 3 sides (c614d06e2, RW-8). WF/EffectRef/Verdict DEFERRED per RV-M4 (no reader — rail reads raw dicts); probe-eval → A3 (Rust crate is its first cross-lang caller). ACP-5 game-server=TS fixed inline (RV-M2). | M | ✅ | **EVIDENCE (pasted, committed):** chat `test_working_memory` 6 passed (re-pointed path); knowledge `test_executive_contract` 6 passed (real `InitWorkingMemoryRequest`/`TickRequest` vs schema + additionalProperties drift + RV-M8 user_id-required + tick status enum); roleplay `cargo test charter::` 5 passed incl. `freeze_output_conforms_to_working_memory_schema` (real freeze() on 3 presets) + `conformance_check_actually_bites_on_drift`. RW-8 CAUGHT + fixed a real gap (schema never modeled the `rubric` sidecar). ACP-11/14/15 (llm_judge per-user, owner server-pinned) RV-M1/M3 = design instructions on GATED surfaces, applied when built. |
| **A1** ✅ | R3 Python SDK `sdks/python/loreweave_agent_control` — the PURE, stdlib-only pieces: `rail.py` (verdict machine, byte-copy) + `state_merge.py` (`merge_state`+`build_messages`). **chat consumes via a re-export shim** (`rail_progress.py`); **knowledge consumes via import** (`executive.py`) — both are SDK consumers (RV-H1). `run_executive`/repo stay in knowledge. **Checkpoint owner-scoped (RV-H4):** `update_state(session_id, user_id, state)` + `get` owner-required, dead `user_id=None` branch removed. *(Anchor+WorkingMemory-model move deferred to A2 where the harness+A4 render-work live — model-coupled; documented split, not silent narrowing.)* | M | ✅ | **EVIDENCE (pasted):** SDK golden 10 passed (RW-2, pins `next_actionable_step`/`merge_state`/render/`build_messages`); chat rail suite (`test_rail_progress`+`test_rail_drive`) 65 passed via the shim; chat full suite 1693 passed / 7 **pre-existing** fails (proven: identical on clean HEAD — `TestW1ContextBreakdownFrame`+voice-billing = the concurrent context-budget track); knowledge executive+contract 22 passed via SDK import; knowledge unit 3877 passed / 1 pre-existing (migrate DDL). **RV-H4 DB test 1 passed on real Postgres :5555** (cross-owner read→None, cross-owner write→0 rows rejected, owner-write→works). **/review-impl HIGH (FIXED+verified):** the package was missing from `pyproject packages.find include` → `pip install /sdk` would omit it → runtime ImportError → chat+knowledge fail to start (tests hid it via PYTHONPATH). Added the include line; `find_packages` confirms discovery. |
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

- **A0 RW-8 find (real latent gap, fixed):** the both-sides discipline caught that `charter::freeze()` emits a top-level `rubric` sidecar for interview presets — and `/evaluate` reads it (`evaluate.py:61` "rubric always comes from the seed") — yet the shared schema forbade it via `additionalProperties:false`. Chat's own conformance test never caught it (chat's `WorkingMemory` has `extra='ignore'`, so its dump carries no rubric). Only validating the REAL producer output (roleplay's `freeze`, RW-8) surfaced it. Fixed: added `rubric` as an optional schema property. **Lesson: a both-sides contract test that validates a fixture (or a consumer that silently drops fields) hides producer/schema drift — validate the actual producer output.**

- **A1 /review-impl HIGH (caught + fixed) — the extraction was runtime-broken while every test was green.** The SDK package `loreweave_agent_control` was NOT in `sdks/python/pyproject.toml`'s `[tool.setuptools.packages.find] include` allowlist, so `pip install /sdk` (how chat+knowledge Dockerfiles install SDKs) would have OMITTED it → the shim's `import loreweave_agent_control` fails at RUNTIME → both services fail to start. The whole test suite passed because tests import via `PYTHONPATH=sdks/python`, which ignores the install allowlist. Fixed by adding the include line (the exact `loreweave_crypto` lesson, verbatim). **Lesson: a green Python suite does NOT prove a new SDK package is installable — the manifest allowlist is a separate gate the tests bypass; the /review-impl runtime-importability check is what caught it.**
- **A1 pre-existing failures (NOT mine — proven, out of scope):** 7 chat (`TestW1ContextBreakdownFrame` token-accounting + `test_voice_billing`) + 1 knowledge (`test_pending_facts_fact_type_check_constraint` migrate DDL) fail. Proven pre-existing by clean-stashing ALL A1 work and reproducing them identically on HEAD. They belong to the concurrent `feat/context-budget-law` track, not A1. Not fixed here (different track); recorded for honesty.

## 6b · A2 build plan (teed up — the next focused slice; sequence its sub-pieces)
A2 is large; build + test + review each sub-piece, commit A2 as one slice once all green:
- **A2.1 ✅ (aead4b271) · RV-M6 advisory lock — DONE.** `apply_state_update` under `pg_advisory_xact_lock`; executive unit 14 passed; real-DB concurrent double-submit 2 passed (both covered items survive). **NEXT: A2.2 (the harness).**
- ~~A2.1~~ `run_executive` did an unlocked
  read-modify-write (`repo.get` → `merge_state` → `repo.update_state`); two overlapping ticks
  last-writer-wins on `phase`. Fix: after the LLM returns, do the get→merge→write under a
  `pg_advisory_xact_lock(hashtextextended(session_id::text,0))` in ONE txn — add
  `WorkingMemoryRepo.apply_state_update(session_id, user_id, charter, llm_state, merger)` that
  re-reads state under the lock, merges, writes. run_executive calls it instead of update_state.
  Test: real-DB concurrent double-submit doesn't clobber (both covered items survive).
- **A2.2 ✅ (c3096218b harness + 99a1cb669 wiring) · The harness — DONE.** SDK `harness.py`
  `decide_rail_drive` unifies drive+enforcement into a verdict (probe injected); `stream_service`
  calls it + owns the loop mechanics; dead `_maybe_redrive_rail` removed; `test_rail_drive` migrated.
  SDK 16 passed; chat rail 62 passed; stream_service collects clean. **NEXT: A2.4 (voice) — RV-H2 (A2.3)
  is already satisfied: I kept the rail-drive and the executive-tick as SEPARATE code paths (never
  conflated into a single control_program), so today's both-fire is preserved; a both-eligible +
  full-loop live-smoke rides A4/A5 in-container.**
- ~~A2.2~~ SDK `harness.py`: `decide_rail_drive(*, probe_fn (injected,
  RW-11), rail_specs, book_id, user_id, turn_start_counts, turn_succeeded, async_tools, nudged_out,
  nudge_counts, enforcement_strength, user_message) -> DriveVerdict{action, slug, step, directive_text,
  giving_up, drove}` — UNIFIES `_maybe_redrive_rail` (drive decision) + the inline enforcement at
  stream_service:1806-1861 (nudge caps, `enforcement_for`, `user_abandoned_rail`, directive vs
  give-up). Returns a VERDICT; chat OWNS the loop mechanics (inject `role=user` directive, drop the
  stateful chain head `response_id=None`). Read stream_service:1771-1870 for the exact enforcement.
- **A2.3 · RV-H2 program SET.** The executive tick (`is_roleplay`) + rail drive (`rail_specs`) are
  INDEPENDENT gates — a session can fire BOTH. The harness runs the SET, SEQUENCED (exec tick →
  rail drive), preserving today's behavior. Add a both-eligible test.
- **A2.4 · RV-M7 voice.** `voice_stream_service` has the anchor but NO tick/drive (dead executive on
  voice — "the real use"). Wire voice through the harness tick+drive. Voice live-smoke.
- **A2.5 · anchor + WorkingMemory-model move** (deferred from A1): move `parse_working_memory`/
  `render_pinned`/`render_tail`/`resolve_anchor` + the WorkingMemory/Charter/State models to the SDK;
  chat `working_memory.py` + `models.py` re-export (shim). Golden for `render_pinned`/`render_tail`.
- **Smokes (4):** multi-turn drive (nudge→nudge→give-up + escape phrase); both-eligible; concurrent
  double-submit (A2.1); voice. NO migration (RW-12) — the lock is a runtime advisory lock, not DDL.

## 7 · Checkpoints
- PO checkpoint after A3 (SDK extracted + dogfooded) and after A4 (Practice live). Commit per slice with pasted evidence.
- **A0 DONE 2026-07-16** — the contract-enforcement foundation. Commits ea6ae3239 (move) · b3fbdee09 (executive) · c614d06e2 (charter 3-side + rubric fix). Next: A1 (Python SDK extraction + characterization goldens + checkpoint owner-scope).
