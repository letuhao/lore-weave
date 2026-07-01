# Studio Agent RAID — CLARIFY + Detailed Design

> **Spec (SSOT):** [`07S_studio_agent_standard.md`](../specs/2026-07-01-writing-studio/07S_studio_agent_standard.md)
> · **Research:** [`07R`](../specs/2026-07-01-writing-studio/07R_chat_agent_industry_research.md)
> **Date:** 2026-07-02 · **Size:** XL (RAID — full A–D + PlanForge takeover, 6 services). **EXECUTING (sequential).**
> **Scope decision (user):** ONE RAID covering P1+P2+P3, run **SEQUENTIALLY (no fan-out) with e2e-test + auto-bug-fix
> quality loops** (this is LLM-heavy → quality verification is essential; **`google/gemma-4-26b-a4b-qat` 200K is
> loaded** for LLM eval). **PlanForge is now IN scope** (the other agent stopped after M3): we **take over** — review-
> impl M1–M3 + implement M4–M5 — as **Phase 0**, since it unblocks Wave B2 (Plan mode).

## 0.0 State reconciliation (2026-07-02, verified vs git)

- **PR #53 merged to main** at `61efc94d6` (studio foundation + 07R). `origin/main` = `4894e7c58` (merge #53).
- **PlanForge M0–M2 committed on `feat/writing-studio`** (`d6d3d79ef` M0/M1, `88a6622fe` M2, `96468dd38` M2-review)
  — **NOT yet on main**. **M3 (HTTP API + persistence) is UNCOMMITTED WIP** (router `plan_forge.py` 250L, repo
  `plan_runs.py` 238L, `services/plan_forge_service.py`, migrate/models/deps/main/worker deltas). **M3 unit tests
  GREEN (38 pass)** but **not review-impl'd / bug-fixed**.
- **Branch:** work continues on **`feat/studio-agent-raid`** cut from the current `feat/writing-studio` tip (which
  carries PlanForge) — NOT off `main` (main lacks PlanForge). A later PR merges PlanForge + RAID to main.
- **Quality loop (per item):** unit → **e2e/live smoke on a real LLM** (`gemma-4-26b-a4b-qat`) → **auto-fix loop**
  (review-impl → fix → re-verify) until green. Especially for LLM-driven items (PlanForge, compaction, autonomy).

---

## 0. CLARIFY

**Goal.** Bring the Studio chat-agent to an industry-strength standard (context budget + compaction, plan-then-act,
steering, tool/skill/MCP depth, HITL modes + checkpoints, memory-for-canon, and an **autonomy dial** that gives
both the mid-loop "vibe" mode and the start/end "agentic" mode) — the load-bearing gate before scaling more panels.

**In scope.** Waves A–D (§2). **Out of scope / non-goals:**
- **PlanForge engine promotion** (B1) — a *separate* track owns it ([[planforge-promoted-by-another-agent-check-compat]]);
  Wave B2 only *wires* the promoted engine and must verify compatibility first.
- Antigravity-style multi-agent "Manager/Inbox" UI — build only the durable-run *seam* (D4), defer the mission-control UI.
- Computer-use / browser-verification, git-native auto-commit, codebase-RAG-index (we have knowledge-service).

**Decisions locked (user, 2026-07-02):** compaction = **hybrid** (agnostic base + Anthropic overlay when Claude) ·
autonomy = **4-level dial** over one pipeline · foreground/background = **per-run toggle** · end-gate = **Run Report +
per-chapter accept/reject + Revert-All**.

**Acceptance bar (RAID-level).** Each wave ships independently green (unit + a cross-service live-smoke — new
cross-service contracts MUST live-smoke through the consumer, per [[new-cross-service-contract-needs-consumer-live-smoke]]).
Mandatory scenario tests: **VN/CJK compaction smoke** (edge #1), **headless compaction-fail → breaker** (edge #2),
**threaded-chapter dependency accept/reject** (edge #3). No provider SDK outside provider-registry; no hardcoded model names.

**Prerequisite.** Merge PR #53 (`feat/writing-studio`→main) first, then branch **`feat/studio-agent-raid`** off `main`.

---

## 1. Grounding (verified vs code, 2026-07-02)

| Subsystem | Verified fact + hook | Implication |
|---|---|---|
| Budget denominator | `ProviderCredentials.context_length` in chat-service `app/models.py:466` (provider-registry `user_models.context_length`, drives `LLM_CONTEXT_OVERFLOW`) | meter/compaction have a real denominator; NULL → degrade |
| Provider-kind | `ProviderCredentials.provider_kind` `models.py:462` (`openai\|anthropic\|ollama\|lm_studio`) | overlay gate = zero-cost branch |
| Anthropic passthrough | body via `streamRequest.Extra` (`stream_handler.go:91`) → forward in `adapters.go:1117`; beta header add at `anthropic_streamer.go:251` | overlay is additive **in provider-registry** (invariant-safe) |
| MCP resources/prompts | **absent** (tools-only): ai-gateway `src/mcp/handlers.ts`, `proxy-server.factory.ts`, `federation.service.ts`; servers `app/mcp/server.py`; chat client `knowledge_client.py:416,549` | additive, clear insertion points |
| X-Project-Id | **forwarded** by ai-gateway `buildEnvelopeHeaders` (`federation.service.ts:53`); public-edge mints fresh by design | memory `gateway-drops-xprojectid-envelope` is **STALE** — confirm live; no workaround needed |
| Saga reuse | `campaign-service/app/saga/driver.py:50` `next_dispatches()` **stage-agnostic**; `campaign_chapters` status-matrix; HA-claim `FOR UPDATE SKIP LOCKED`+lease; idempotent `mark_stage_dispatched`; **probe-reconcile** breaker (`reconcile.py`), NOT a Redis stream | reuse driver; add run-entity + composition dispatch-stage + budget + run event |
| Checkpoints | `chapter_revisions` **snapshots every PATCH** (book-service draft PATCH: version++ + immutable revision + `chapter.saved` outbox); Tier-4 `revert()`/buffers exist; **restore endpoint absent** | per-chapter revert ≈ add restore endpoint + pre-turn mark |
| Notify | RabbitMQ `loreweave.events` → notification-service consumer → `notifications` table → BFF SSE `/v1/notifications/stream`; user-scoped multi-device fan-out | autonomous-run completion = emit TerminalEvent `operation="autonomous_authoring"` |

**Spec reconciliations (update 07S):** §4 drop the X-Project-Id workaround (stale); §10 generalize breaker from
`knowledge.chapter_failed` XADD → "the saga's failure signal (probe-reconcile)"; §5c note `chapter_revisions`
already gives per-save snapshots (cheaper than assumed).

---

## 2. Wave decomposition (~19 items)

Legend: **Eff** S/M/L · **Dep** = depends-on · **Edge** = §13 edge-cases this item must handle.

### Wave P — PlanForge takeover (Phase 0) · *inherited from a stopped track; unblocks B2*
Plan SSOT: [`2026-07-01-plan-forge-promote.md`](2026-07-01-plan-forge-promote.md) (M0–M5) + blueprint §5–§7.
| Item | What | Key hooks | Eff | Dep | Edge |
|---|---|---|---|---|---|
| **P0** | Commit inherited M3 WIP checkpoint | router `plan_forge.py`(250L) · repo `plan_runs.py`(238L) · `services/plan_forge_service.py` · migrate/models/deps/main/worker deltas; 38 unit tests green | S | — | — |
| **P1** | **review-impl M1–M3 + fix bugs** | adversarial pass over engine port (M1), BYOK LLM adapter + worker (M2), HTTP API + `plan_runs`/`plan_artifacts` persistence + OCC + tenancy (M3); the LLM-heavy paths esp. | M | P0 | tenancy, OCC |
| **P2** | **M4 — MCP `plan_*` tools + chat skill** | 8 tools (blueprint §5) thin wrappers `app/mcp/server.py`→`plan_forge_service`; `chat-service .../plan_forge_skill.py`; D-PF-APPLY-HONESTY (`fidelity_delta==0`→`no_change`) | M | P1 | apply-honesty |
| **P3** | **M5 — Studio planner dock** | `frontend .../plan-forge/` + Studio `planner` panel; model picker required; poll run status; **live browser smoke on gemma-4-26b** (paste fixture→propose→checkpoint→validate→compile) | M | P2 | — |

### Wave A — Context spine (🥇 P1) · *the compaction base every autonomous run relies on*
| Item | What | Key hooks | Eff | Dep | Edge |
|---|---|---|---|---|---|
| **A1** | Script-aware token counter (NOT chars/4) | new `chat-service .../token_budget.py`; per-script factors (CJK≈1, VN-diacritic dense) or tokenizer; `count_tokens` when Claude | M | — | #1 |
| **A2** | Budget accounting + `contextBudget` CUSTOM event | `stream_events.py` (mirror `memoryMode`); used% = promptTokens/(ctx_len−max_tokens−safety); bucket breakdown = *labeled estimate* | S | A1 | #6 #8 |
| **A3** | FE meter | `StudioStatusBar.tsx` + chat header; `chatStateHub` snapshot; bands 70/85; NULL ctx→"—" | S | A2 | — |
| **A4** | Agnostic compaction (micro→full→fail) | `stream_service.py` turn loop; evict tool_results keep-3+exclude; summarize-role; retry→hard-truncate→`compaction_failed`; non-evictable overflow guard | M–L | A2 | #2 #4 |
| **A5** | Anthropic overlay | gate `provider_kind=="anthropic"`; `Extra`→`clear_tool_uses`+memory blocks (`adapters.go:1117`); beta header (`anthropic_streamer.go:251`) | M | A4 | — |
| **A6** | Manual Compact + New-from-summary | FE button + chat-service endpoint; define carry-set (steering/tools/skills/pins/bindings) | S | A4 | LOW |

### Wave B — Plan + web (🥇 P1) · *B1 PlanForge promotion EXCLUDED (external)*
| Item | What | Key hooks | Eff | Dep | Edge |
|---|---|---|---|---|---|
| **B2** | Plan mode (plan→approve→draft) | new mode; research (Ask surface) → PlanForge plan artifact → approve → Write; **verify promoted-PlanForge contract first** | M | *ext PlanForge* | #7 |
| **B3** | Live task checklist | reuse `agentSurface` phase stream → TodoWrite-style render | S | B2 | — |
| **B4** | Web search surfaced | BYOK `web_search` toggle + inline citations + domain allow/deny | S | — | — |

### Wave C — Steering + tools + HITL (🥈 P2)
| Item | What | Key hooks | Eff | Dep | Edge |
|---|---|---|---|---|---|
| **C1** | Steering store | new per-book table `book_steering{name,body,inclusion_mode,match}`; tenancy = owner+E0 grantees; render into `steering` bucket; inclusion modes always/scene_match/manual/auto | M | A2 | #13 |
| **C2** | HITL modes + per-tool approval | extend `tool_surface.py`; Ask=read-only allowlist / Write=confirm non-allowlisted side-effect tool; wire `composeMode` | S–M | — | #5 |
| **C3** | SKILL 3-tier | `skill_registry.py`: L1 metadata always + L2 on-select + L3 scripts | M | — | — |
| **C4** | @-mention loading | FE input `@character/@scene/@chapter/@glossary/@thread` → `ContextPicker` resolver → bucket; size-cap | M | — | #14 |
| **C5** | MCP resources + prompts | ai-gateway handlers+proxy+federation; server decorators; chat client methods; **X-Project-Id confirmed live**; resource LIST owner-only filter | M | — | #14 |
| **C6** | Turn checkpoints + hunk review | book-service **restore endpoint** + pre-turn snapshot mark (reuse `chapter_revisions`); hunk-level accept/reject on propose_edit; dirty-editor (G7) reconcile | M | — | #9 |

### Wave D — Autonomy + memory + durable (🥉 P3) · *the agentic start/end mode*
| Item | What | Key hooks | Eff | Dep | Edge |
|---|---|---|---|---|---|
| **D1** | Memory-for-canon | route persisted facts via existing `memory_remember_confirm`/pending-facts; agnostic write to knowledge-service pre-eviction + A5 memory-tool overlay | M | A5 | — |
| **D2** | Autonomy dial L3–4 | mode FSM; **start-gate** = plan(B2)+scope+budget cap+breaker+**tool allowlist**; during-guardrails; per-run fg/bg toggle | L | A4 B2 C2 | #5 |
| **D3** | Run Report + dependency accept/reject | Quality Report + draft-diff artifact; **dependency-ordered** accept/reject + cascade warning; Revert-All (via C6) | M | C6 D2 | #3 #12 |
| **D4** | Durable background run | reuse saga driver → new "authoring run" entity + composition dispatch-stage + budget model + **per-unit lock** + run-scoped completion → notification-service `operation="autonomous_authoring"`; multi-device runs list | L | D2 | #10 #11 |
| **D5** | Critic sub-agent | continuity/critic parallel, distilled verdict → feeds breaker + Run Report | L | D2 | LOW |

---

## 3. Dependency graph / sequencing

```
P0→P1→P2→P3         (PlanForge takeover: checkpoint→review/fix→M4→M5)
A1→A2→A3            (meter chain)
      A2→A4→A5      (compaction: base→overlay)
         A4→A6
A4 ──────────────► D2,D4   (autonomous NEEDS headless compaction)
P (PlanForge)────► B2       (Plan mode wires the finished engine) ──► D2 (autonomous uses the plan)
C2 ──────────────► D2       (tool allowlist)
C6 ──────────────► D3       (Revert-All uses restore)
D2→D3, D2→D4, D2→D5
```
**Build order (SEQUENTIAL, no fan-out per user):** **P** (PlanForge takeover) → **A** (context spine) → **C** (+ B4)
→ **B2/B3** (wire finished PlanForge) → **D** last (depends on A+B2+C2+C6). Each item runs to green with the
unit → e2e-live-smoke(gemma-4-26b) → auto-fix loop before the next.

---

## 4. Cross-cutting test strategy

- **VN/CJK compaction smoke (edge #1, MANDATORY):** drive the POC book (`Ma Nữ Nghịch Thiên`/`万古神帝`) past the
  trigger on a **local lm_studio model**; assert the estimate ≈ measured promptTokens (not 4–8× off) and compaction fires.
- **Headless compaction-fail (edge #2):** stub the summarizer to fail; assert retry→hard-truncate→`compaction_failed`
  trips the breaker in an autonomous run (no blind drafting).
- **Threaded accept/reject (edge #3):** a 2-chapter threaded run; reject ch1, assert ch2 flagged (cascade), never silent.
- **Provider-agnostic first, overlay second:** every compaction test runs on a local model (base path) AND a Claude
  model (overlay path) — the base must never regress when the overlay is off.
- **Cross-service live-smoke** for every new contract: `contextBudget` event through chatStateHub; MCP resources through
  the gateway (confirm X-Project-Id survives); autonomous-run completion through notification-service SSE; saga
  authoring-run at the dispatch seam ([[campaign-saga-live-smoke-at-dispatch-seam]]).
- **Tenancy:** steering write blocked for a non-grantee collaborator (edge #13); resource LIST owner-filtered (edge #14).
- Gates per milestone: VERIFY evidence, 2-stage REVIEW, `/review-impl` on load-bearing (compaction, autonomy, tenancy).

---

## 5. Risk register

| Risk | Mitigation |
|---|---|
| CJK token estimate wrong → overflow/mis-fire | A1 is a *blocking* prerequisite; VN/CJK smoke gates the wave |
| Headless autonomous run corrupts via bad compaction | A4 failure-mode → breaker; D2 depends on A4 |
| Threaded accept/reject inconsistency | D3 dependency-ordering + cascade (edge #3) |
| Anthropic overlay breaks local path | overlay strictly gated on `provider_kind`; base path tested standalone |
| Provider invariant violation | ALL provider calls stay in provider-registry (A5 additive there); gate `scripts/ai-provider-gate.py` |
| Stale-memory drift (X-Project-Id, saga breaker) | reconciled in §1; confirm both with a live-smoke at build |
| Saga reuse leaks campaign-specific coupling | D4 extracts the stage-agnostic driver; authoring-run is a distinct entity |
| RAID drift / scope creep over ~19 items | checkpoint/commit at each risk boundary (contract, migration, cross-service seam), not per-file |

---

## 6. Branch & workflow (reconciled — see §0.0)

1. Branch **`feat/studio-agent-raid`** off the current `feat/writing-studio` tip (`96468dd38`, carries PlanForge M0–M2).
2. **Execution order (SEQUENTIAL, no fan-out):**
   **Phase 0 — PlanForge takeover** → **Wave A** → **Wave C** (+ B4) → **Wave B2/B3** (wire finished PlanForge) → **Wave D**.
   - **Phase 0:** commit inherited M3 WIP checkpoint → **review-impl M1–M3 + fix** → **M4** (MCP `plan_*` tools + chat
     skill) → **M5** (Studio planner dock) → live smoke on `gemma-4-26b`. (Plan: [`plan-forge-promote`](2026-07-01-plan-forge-promote.md).)
3. Per item/wave: size-gate → BUILD → VERIFY (unit + **e2e live-smoke on gemma-4-26b**) → **auto-fix loop** (review-impl
   → fix → re-verify) → 2-stage REVIEW → POST-REVIEW (PO) at each shippable boundary. Update SESSION_HANDOFF each boundary.
3. **PO checkpoints batched per-boundary** (PlanForge done → A → C → B → D), not per-item.

## 7. Open [verify]-at-build

- (a) A1: pick the tokenizer (tiktoken vs HF vs per-script factors) + validate on VN/CJK against measured usage.
- (b) A5: exact Anthropic beta-header string(s) + `edits`/memory block shape current as of build.
- (c) B2: the promoted PlanForge contract (engine coroutine, plan artifact schema) — compat before wiring.
- (d) C5: live-confirm X-Project-Id survives federation for resources; else fall back to direct `/mcp`.
- (e) D4: exact saga breaker/reconcile hook to reuse; budget model (inherit campaign vs new).
