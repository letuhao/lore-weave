# 07S — Studio Agent Standard (buildable spec)

> **Status:** DESIGN spec (build-to). Elevates [`07R`](07R_chat_agent_industry_research.md) Part 6 into a
> buildable standard for the Writing Studio chat-agent. · **Date:** 2026-07-02
> **Decisions locked (user, 2026-07-02):** compaction = **hybrid** (provider-agnostic base + Anthropic
> overlay when the model is Claude); **write this standard before building**.
> **Principle:** the chat-agent is the load-bearing part of the Studio. A "strong enough" standard here is
> the gate to scaling more panels. Build on what we already have (rack, `find_tools`, Tier gating,
> working_memory, AG-UI, chatStateHub) — this is mostly *unifying fragments*, not net-new.

Grounding note: every section maps to real files (from the codebase inventory). Where a dependency needs
verification it is flagged **[verify]**; per the anti-laziness rule those are *buildable*, not blocked.

---

## 1. The context model — 7 typed buckets + budget

**Standard (07R §3):** the window is partitioned into typed buckets so each is budgeted and evicted
independently, reserving output headroom. We already source most; we just don't *account* for them.

| Bucket | What it is | Sourced from (today) | Evict priority |
|---|---|---|---|
| **`system`** | system prompt + injected skill text | `skill_registry.py`, base prompt | never (floor) |
| **`steering`** | **author-written always-on rules** (style guide, voice, naming conventions) with an *inclusion mode* (always / scene-match / manual) — *authoring instructions*, distinct from RAG world-state | **NEW** (§1a) — a per-book steering store | never (small, taxed every turn → keep tight) |
| **`anchor`** | working-memory charter (goal/phases/state) — *task state* | `working_memory.py` (pinned block + tail) | never (small, pinned) |
| **`world`** | knowledge/RAG context + glossary aliases — *world state* (retrieved) | `knowledge_client.py` per-turn | recompute per turn (not evicted) |
| **`pinned`** | user-pinned ad-hoc context (this character/scene/chapter) + attachments | `ContextBar` (next-msg only, today) → **make persistent** | last (user chose it) |
| **`conversation`** | message history | session messages | after tool-results |
| **`tool_results`** | tool-call outputs | AG-UI TOOL_CALL_RESULT | **first** (biggest, stalest) |

**Three *different* memory layers — do not conflate (07R gap-review HIGH #2):** `steering` = author-written
rules (Cursor `.cursor/rules` / Kiro steering / CLAUDE.md analog) · `anchor` = task state · `world` =
retrieved RAG · `pinned` = ad-hoc user pins. The industry taxes `steering` carefully because it is billed
*every* request — keep it small and use inclusion modes to scope it.

### 1a. Steering store (author-written rules) — NEW
A per-book **story-bible-as-steering** store (the Kiro-steering / Cursor-rules analog for fiction):
- **Location:** server-side per-book (multi-device, DB-backed — NOT localStorage, per CLAUDE.md tenancy). A
  `book_id`-scoped table of steering entries `{name, body, inclusion_mode, match?}`.
- **Inclusion modes** (mirrors Kiro `always/fileMatch/manual/auto`): `always` (every turn) · `scene_match`
  (only when the active chapter/scene/POV-entity matches) · `manual` (`#name` in chat) · `auto` (name+desc,
  model pulls when relevant).
- **Distinct from `working_memory` charter:** charter = *task state* (goal/phase, ephemeral per run); steering
  = *durable authoring rules* the author owns. Both render into the prompt but have different lifecycles.

**Acceptance:** an author can write a per-book style rule set to `scene_match`; it appears in context only on
matching scenes and is billed to the `steering` bucket.

**Budget accounting — the numbers already exist:**
- **Denominator** = `user_models.context_length` — **already resolved into chat-service** (`app/models.py:466`;
  provider-registry `user_models.context_length`, used by the `LLM_CONTEXT_OVERFLOW` guardrail in
  `provider-registry .../jobs_handler.go`). NULL for legacy rows → meter shows "unknown", compaction disabled.
- **Numerator (measured)** = `promptTokens` from the last `RUN_FINISHED` usage event (ground truth).
- **Reserve** = `generation_params.max_tokens` + a safety margin (mirror the guardrail's `input + max_tokens
  + safety ≤ context_length`), so the **effective budget** = `context_length − max_tokens − safety`.
- **Pre-send projection** = an estimate of the *next* turn's input so the meter warns *before* a send. **NOT
  a flat `chars/4`** — that is Latin-centric and under-counts our POC content **4–8×** (edge #1): Chinese
  ≈ 1–2 tokens/char, Vietnamese-with-diacritics tokenizes far denser than English. Use a **script-aware
  estimate** (per-script tokens/char factors) or a real tokenizer (tiktoken/HF) for the estimate, and the
  provider's `count_tokens` when the model is Claude. A wrong estimate here mis-fires the meter *and* the
  compaction trigger (§3) — critical for the VN/CJK POC.

**Acceptance:** given a session on a model with `context_length`, the agent can compute `used%` =
`promptTokens / (context_length − max_tokens − safety)` and attribute tokens to buckets (at least
system/anchor/world vs conversation vs tool_results).

---

## 2. Token meter + tiered warnings (🥇 P1)

**Standard:** live `%-used` indicator + tiered warnings at ~70% ("compaction soon") and ~85% ("imminent"),
healthy band 60–80%.

**Design:**
- New AG-UI CUSTOM event **`contextBudget`** `{used_tokens, effective_limit, pct, bucket_breakdown?}` emitted
  by `stream_events.py` on `RUN_FINISHED` (mirror the existing `memoryMode`/`agentSurface`/`composing`
  custom-event pattern). Carried in the `chatStateHub` snapshot alongside usage.
- **FE surface:** a compact meter in the **Studio status bar** (`StudioStatusBar.tsx`) + the chat header
  (`AgentContextRack`/session header). Colour bands 60/80/85. Tooltip = bucket breakdown.
- Reuse the existing usage plumbing (`RunFinishedEvent.promptTokens`) — this is *surfacing*, not new metering.

**Acceptance:** after each turn the meter shows `used%` and flips amber ≥70% / red ≥85%; NULL `context_length`
→ meter shows "—" (no crash).

---

## 3. Compaction — HYBRID (🥇 P1)

**Decision:** provider-agnostic base (works for local lm_studio/Qwen/Gemma of the POC) + an Anthropic overlay
when the resolved model is Claude. Lives in the chat-service turn loop (`stream_service.py`), NOT the FE.

### 3a. Provider-agnostic base (all models)
Three tiers, mirroring the industry standard, keyed off the §1 budget:
1. **Microcompact (no model call):** when `used% ≥ trigger` (default 75% of effective budget), evict the
   oldest `tool_results` first — keep the last **N=3** tool outputs, and **never evict** an exclusion set
   (e.g. `web_search`, the active `propose_edit` args). Replace evicted outputs with a short placeholder
   (`[tool result cleared — {tool} @ {ts}]`). Cheapest, reclaims the most.
2. **Full compact (one model call):** if still over budget after microcompact, summarize the older
   `conversation` into a `<summary>` block that **preserves**: current goal/phase (already in the anchor),
   decisions made, open threads, canon/plot facts touched; **keep verbatim** the last K turns + the `pinned`
   bucket. Drop pre-summary conversation. Use a cheap model (`summarize` role — mirror Continue's role split;
   we already resolve multiple model refs per session: chat/composer/planner).
3. **Manual:** a **"Compact" button** (chat header) → force full-compact now; **"New from summary"** →
   start a fresh session seeded with the summary + the same bindings (knowledge project, pins).

Token counting for the trigger uses measured `promptTokens` (post-turn) + the pre-send estimate (§1).

**Failure mode (edge #2 — MANDATORY, esp. for headless autonomous runs §10):** the full-compact model call
can fail (a local Gemma/Qwen times out or returns garbage). A corrupted summary silently poisons every
downstream turn — catastrophic in a long autonomous run with no human watching. So: **retry once → on repeat
failure, fall back to a deterministic hard-truncate** (keep `system`+`steering`+`anchor`+`pinned` + the last
K turns verbatim, drop the rest — no model call) → if *still* over budget (the non-evictable buckets alone
exceed it, edge #4), **raise `compaction_failed`**: an interactive session surfaces it; an autonomous run
(§10) **trips the breaker and stops** rather than drafting blind. Never continue a turn on a summary the
summarizer errored on.

### 3b. Anthropic overlay (when model is Claude) [verify: detect via provider kind]
Layer on top of 3a — do NOT replace it (so switching to a local model degrades gracefully to 3a):
- **Context editing** `clear_tool_uses_20250919` (`keep:3`, `exclude_tools:[web_search]`) — let Anthropic do
  the tool-result eviction server-side (cache-friendly). Our 3a-microcompact becomes a no-op when the overlay
  is active (guard on provider kind).
- **Memory tool** `memory_20250818` — the agent writes durable notes (canon/plot) *outside* the window before
  eviction; this is the §8 differentiator's substrate. **[verify]** provider-registry passes the beta
  header + our provider adapter forwards the `edits`/memory tool blocks.

**Acceptance:** on a local model, a session driven past 75% auto-microcompacts (tool_results shrink, turn
still coherent) and the manual Compact button works; on a Claude model, `clear_tool_uses` fires server-side
and the manual button still works; both keep input under `context_length − max_tokens − safety` (no overflow
500). A unit test drives the trigger deterministically with a stubbed token count.

---

## 4. Tool & skill management (🥈 P2 — mostly extend, not build)

We already have the mature core (rack `enabled_tools/skills`, `find_tools` = Tool Search, Tier-A/S/W/G
gating, `skill_registry`). Standard gaps to close:
- **SKILL.md 3-tier progressive disclosure (gap-review MED #3):** today `skill_registry` injects the *full*
  skill text every session (always L2). Adopt the industry-standard three tiers: **L1 metadata**
  (name + one-line description) always-on for *all* skills (~tens of tokens each) → **L2 body** loaded only
  when the model selects the skill → **L3 bundled scripts/refs** read on demand. Cuts the skill tax as the
  catalog grows. `enabled_skills` becomes "force L2"; unpinned skills sit at L1 and self-activate.
- **MCP resources + prompts as first-class** (we only have *tools*). **Resources** = the correct "load
  context from other providers" (app-loaded data blocks, not model-invoked) → wire into the `world`/`pinned`
  buckets. **Prompts** = user-selected reusable templates → surface as `/`-commands (we already have a
  template picker in `ChatInputBar`).
  **⚠ Known gateway constraint:** ai-gateway MCP federation **drops `X-Project-Id`** (memory
  `gateway-drops-xprojectid-envelope`) → project-scoped resources/prompts fail *through* the gateway. Design
  resources/prompts to take `project_id`/`book_id` as an **explicit arg**, or resolve them on the owning
  service's `/mcp` directly, not via federation. **[verify]** which MCP servers expose resources/prompts.
- **@-mention context loading (gap-review MED #4):** the dominant "load context" UX is inline `@`-mention
  (Continue's 16 providers, Cursor `@Codebase/@Docs`, Zed `@`-everything incl. prior threads). We only have
  `ContextBar` attachments. Add `@`-mention in the chat input: `@character`, `@scene`, `@chapter`,
  `@glossary`, `@thread` (a prior conversation) → resolves into the `pinned`/`world` bucket. Reuse
  `ContextPicker` as the resolver backend.
- **Per-server-tool approval (gap-review MED #6):** today server-side MCP tools execute silently (only
  frontend tools + Tier-S/W domain-confirm gate). Add the reversibility gate (see §5): **Ask** mode = a
  read-only tool allowlist; **Write** mode = a side-effecting server tool not on the allowlist prompts once.
- **Skill↔tool affinity:** a skill declares the tool prefixes it prefers (we already have `mcpToolPrefixes`
  on the studio registration) so enabling a skill hot-seeds its tools.
- **In-session catalog refresh** so newly-shipped tools appear without reload (minor).

**Acceptance:** all skills cost L1-metadata only until selected; an MCP resource pins into context (with
`book_id` explicit, not via a dropped envelope); `@character` resolves inline; a not-yet-allowlisted
side-effecting server tool prompts in Write mode.

---

## 5. HITL permission modes (🥈 P2)

**Governing principle (07R §6, make it explicit): reversibility determines autonomy** — an undoable action
auto-runs; an action that mutates durable state (publish, delete, spend, cross-service write) is gated behind
a human. This one rule drives Tier gating AND the modes below.

We already have Tier gating (A auto+undo / S·W confirm / G async) and the propose/confirm cards — add the
*mode* layer on top, wired to the existing `composeMode` (Zed Ask/Write/Minimal analog):
- **Ask** — read-only tool allowlist only (research/plan safely; no writes).
- **Write** — all tools, Tier-S/W still confirm-gated; not-yet-allowlisted side-effecting server tools prompt once (§4).
- **Compose** — prose-only, no tools (today's `composeMode`); model drafts, user Applies.

**Acceptance:** switching mode changes the advertised tool surface (Ask = read-only subset); Tier-A undo +
Tier-S/W confirm still hold in Write.

### 5b. Plan-then-act / Plan mode (🥇 P1 — gap-review HIGH #1)

**The strongest convergent pattern across *every* leader** (Cursor Plan Mode→`plan.md`, Claude Code plan mode,
Kiro spec-first + approval gate, Antigravity Planning Mode, Continue read-only Plan) — and 07S had **omitted
it**. For authoring the analog is direct: *plan the chapter/scene before drafting*. We already have the engine
(**PlanForge**, blueprint shipped) — this wires it into the chat agent as a mode.

**Design:**
- A **Plan** mode (sits alongside Ask/Write/Compose, or as a Shift-Tab-style toggle): the agent researches
  (read-only tools, Ask surface) → proposes an **editable outline/plan artifact** (scene beats, POV, promises
  to plant/pay) → the human edits/approves → *then* it drafts. No prose is written until the plan is approved.
- Reuse PlanForge (`composition-service` engine per the PlanForge blueprint) as the planner; render the plan
  as an editable artifact in the compose panel (the `plan.md` analog); "Approve → Draft" transitions to Write.
- **Live task checklist** during execution (the TodoWrite/Cursor-todos analog) so a multi-step draft/revision
  run shows progress — reuse the existing `agentSurface` phase stream to drive it.

**Acceptance:** a "plan this chapter" request produces an editable plan artifact and writes NO prose until the
human approves; on approve, drafting follows the plan; progress shows as a live checklist.

### 5c. Checkpoints & diff review (🥈 P2 — gap-review MED #5)

Today we have Tier-A single-op undo (activity strip) + propose_edit diff cards. The industry standard is
**turn-level checkpoints** (Cursor auto-snapshot + one-click restore; Zed "Restore Checkpoint" per message)
and **hunk-level diff review** (Zed/Kiro per-hunk accept/reject). For a *writing* tool "undo the whole last
AI turn" and "accept only some of the proposed changes" are high-value.
- **Turn checkpoint:** snapshot the affected draft(s) before an agent turn that edits prose; a "Restore" on
  the assistant message reverts to pre-turn. Reuse the draft-version/snapshot infra (`addTextSnapshots`,
  draft versions) the Tier-4 hoist already uses.
- **Hunk-level review:** `propose_edit` / `propose_record_edit` cards gain per-hunk accept/reject (not
  all-or-nothing Apply).

**Acceptance:** a prose-editing turn can be reverted as a unit; a multi-change proposal can be partially applied.

---

## 6. Sub-agents (🥉 P3 — novel-specific, selective)

Not a general fleet — only where subtasks are **large + independent** (07R §4 heuristic). Candidates, each
returning a **distilled verdict** (~1–2K tokens), reusing the existing "idle judges" constellation:
- **Continuity/critic sub-agent** — character/timeline/canon consistency check, runs in parallel, returns
  violations (feeds the Quality Report). 
- **Research sub-agent** — gather world/reference context without bloating the main thread.
Isolation = own context window; only the verdict returns. **Defer until P1/P2 land.**

**Acceptance (when built):** a critic sub-agent runs on a chapter and returns a structured verdict without
its intermediate reads entering the main conversation.

---

## 7. Durable background runs (🥉 P3 — reuse existing infra)

**Standard:** durable checkpoint-and-resume + human-resumable suspension + completion notify. **We already
have the substrate** on the backend (campaign-saga, outbox, `resume_state`, WFQ) — chat just doesn't use it.
- **Two distinct survival layers (don't conflate):** (a) the existing **SharedWorker hub** = *client-side
  live-turn survival* across dock float/close/pop-out **within one browser** (what `windowingEnabled` gives
  the Compose panel today); (b) **durable server-side** = a run that survives **full browser close** and
  multi-day human-approval waits. §7 is (b); it complements, does not replace, (a).
- Background **revision/critique runs** ("revise these 12 chapters, notify when done") ride the saga infra;
  verification artifact = the **Quality Report** (our Antigravity-artifact analog).
- Human-resumable suspension: our frontend-tool suspend/resume is the in-turn version; the durable version
  persists the run server-side. **[verify]** reuse `resume_state` shape.
- **Completion notify:** emit through the existing **notification-service** (the Inbox seam) — not a bespoke
  channel — so it shows wherever the user next opens the app.

**Acceptance (when built):** a background revision run survives a browser close, notifies via
notification-service on completion, and its result opens as a reviewable Quality-Report artifact.

---

## 8. Memory-for-canon (🥉 P3 — the compounding differentiator)

The +39% lever for long stateful documents (07R §2/§6). Wire the §3b **memory tool** (and a provider-agnostic
equivalent: write canon/plot deltas to knowledge-service before eviction) so long authoring sessions never
lose canon. Compounds with the KG we already have (knowledge-service). Cross-links: the ChapterExitState
threading work (`compose-cross-chapter-typed-state-threading`) is the same "carry state across chapters" idea.
- **Reuse the auto-suggest→approve curation loop we ALREADY have (gap-review MED #7):** the Cursor-"Memories"
  pattern (a sidecar suggests a fact, the user approves) is exactly our **`memory_remember_confirm` +
  pending-facts cards** (`usePendingFacts`/`PendingFactsCard`). Memory-for-canon should *route through* that
  existing confirm loop, not invent a new one — a canon fact the agent wants to persist becomes a pending-fact
  the author confirms.

**Acceptance (when built):** a fact established 40 turns ago (past a compaction) is still available to the
agent via memory recall; a persisted canon fact surfaced through the existing pending-facts confirm card.

---

## 9. Web search (🥇 P1 — small)

Surface the already-wired BYOK `web_search` as a first-class tool: session toggle, inline **citations**,
domain allow/deny gate. Reuse the BYOK pattern (memory `web-search-is-a-tool-not-llm-spend`: tool credential,
not LLM spend). **Acceptance:** a turn can call web_search, results render with citations, domain gate honored.

---

## 10. Autonomy modes — the dial (🥇 spine → 🥉 autonomous)

**Decision (user, 2026-07-02): the Studio ships BOTH the mid-loop "vibe" mode AND the start/end "agentic"
mode — as one autonomy DIAL over a shared pipeline, not two systems.** The industry treats autonomy as a
*spectrum* (Kiro Supervised↔Autopilot, Antigravity Planning/Fast, Copilot agent-mode vs coding-agent): higher
levels **move the human gate from mid-flow to start+end** and replace mid-flow approvals with hard guardrails.

**The 4 dial levels** (autonomy semantics = {Compose, Supervised, Autonomous}; Autonomous execution-location
= foreground/background, chosen **per-run** — surfaced as two presets):

| Level | Human gate | Analog | Semantics |
|---|---|---|---|
| **1. Compose** | Apply each draft | — | prose-only, no tools (§5) |
| **2. Supervised** *(vibe)* | per step (propose/confirm) | Continue Ask-First, Zed Supervised | full tools, Tier gating (§5 Write) |
| **3. Autopilot** *(foreground)* | **start (plan) + end (review)** | Kiro Autopilot | autonomous in one session; mid-gates → guardrails |
| **4. Background** *(async)* | start + end, async | Copilot coding agent, Antigravity Inbox | Autopilot semantics, durable via saga, notify |

Levels 3 and 4 are the **same autonomous run** differing only in **where it executes** → also exposed as a
per-run **"run in background"** toggle (a level-3 run can be pushed to background and vice-versa).

**Shared pipeline — ONE build, three gate positions:**

| Stage | Supervised (vibe) | Autonomous (Autopilot/Background) | Existing infra to reuse |
|---|---|---|---|
| **Start** | free prompt | **approve plan + scope + budget cap + breaker policy** | PlanForge (§5b) |
| **During** | approve each tool/edit | autonomous + guardrails | composition engine + **self-heal** |
| **End** | (none) | **Run Report + per-chapter accept/reject + Revert-All** | Quality Report + draft snapshots |
| **Exec** | in-turn | foreground OR background (per-run toggle) | campaign-saga + notification-service |

→ Agentic mode ≈ vibe-mode's parts with the human gate moved to start+end + durable execution + guardrails.
**We are well-positioned:** the whole durable pipeline already exists; this is mostly the start/end-gate UI +
the dial + wiring, not net-new engine work.

**Start-gate (autonomous):** the author approves (a) the PlanForge outline/beats, (b) **scope** (which
chapters/scenes), (c) a **budget cap** (spend guardrail), (d) **breaker policy** (stop after N continuity/
quality failures — *including a `compaction_failed`*, §3), and (e) a **tool allowlist** (edge #5): because
levels 3–4 have no human mid-flow to answer a §4 per-tool approval, the allowed side-effecting tools must be
declared UP FRONT; a tool outside the allowlist trips the breaker rather than auto-running. No prose written
until approved (§5b).

**During-run guardrails (replace the mid-flow gate — MANDATORY at levels 3–4):** budget cap (spend
guardrails) · circuit breaker (saga `knowledge.chapter_failed` + `compaction_failed`) · scope fence (only
approved units, **with a per-unit lock so two runs can't edit the same chapter**, edge #11) · per-unit
snapshot (reversibility) · checkpoint cadence (resume) · **headless auto-compaction** (§3 — the run *must*
compact itself with no human; a compaction failure trips the breaker, never drafts blind). *Autonomy without
these is unsafe.*

**End-gate (user decision: per-chapter granularity):** a **Run Report artifact** (the Antigravity-walkthrough
analog) — "N chapters drafted, M regions self-healed, K continuity flags, promise-coverage X" — with
**per-chapter accept/reject** + **Revert-All**, built on the Quality Report + draft-diff + snapshot-revert.
**Accept/reject is NOT independent when canon is threaded (edge #3):** chapter 6 may have been drafted from
chapter 5's draft (ChapterExitState). Rejecting an upstream chapter MUST flag every downstream chapter that
threaded from it (re-review or re-draft) — the Run Report shows the **dependency order**, and reject
cascades a warning; it never silently leaves ch6 depending on a rejected ch5.

**Multi-device (edge #10):** a level-4 run and its Run Report are **server-side and discoverable from any
device** (a runs list + retrievable report), not just a transient notification — per the multi-device rule.

**Acceptance (when built):** a level-3/4 run gated on plan-approval + budget-cap drafts the approved chapters
autonomously, honors the breaker, and produces a Run Report; the author accepts some chapters and reverts
others; a level-4 run survives a browser close and notifies via notification-service.

**Priority:** levels 1–2 = the P1/P2 spine (Compose/Supervised largely exist + §5). Levels 3–4 = **P3 (L)** but
*cheap for us* — reuse PlanForge + self-heal + Quality Report + saga + snapshots; the new work is the
start/end-gate UI + the dial.

---

## 11. Priority & sequencing

| Tier | Item | Effort | Gate |
|---|---|---|---|
| 🥇 P1 | §2 meter + §1 budget accounting | S | surfacing existing usage |
| 🥇 P1 | §3 compaction (hybrid) | M–L | the core gap; needs token trigger + summary |
| 🥇 P1 | §5b **Plan mode** (wire PlanForge) | M | strongest convergent pattern; engine exists |
| 🥇 P1 | §9 web search surfaced | S | BYOK already wired |
| 🥈 P2 | §1a **steering store** (author rules + inclusion modes) | M | per-book DB table + prompt render |
| 🥈 P2 | §5 HITL modes + §4 per-server-tool approval | S | extends Tier gating + composeMode |
| 🥈 P2 | §4 SKILL 3-tier + @-mention + MCP resources/prompts | M | gateway envelope caveat [verify] |
| 🥈 P2 | §5c turn checkpoints + hunk-level review | M | reuse draft snapshots |
| 🥉 P3 | §8 memory-for-canon (via pending-facts) | M | compounds with KG |
| 🥉 P3 | §10 autonomy dial levels 3–4 (Autopilot/Background) | L | reuse PlanForge + self-heal + Quality Report + saga + snapshots |
| 🥉 P3 | §6 sub-agents · §7 durable bg | L | reuse idle-judges / saga infra |

**Build order:** P1 = meter → compaction → **Plan mode** → web search (first shippable milestone); each
independently verifiable (unit + a live smoke driving a local model past the compaction trigger, and a
plan→approve→draft smoke). Then P2 (steering, modes+approval, skill/@-mention/resources, checkpoints), then P3
(memory-for-canon, then the **autonomy dial levels 3–4** — the agentic start/end mode — since it depends on
P1 Plan mode + the existing durable pipeline). **The autonomy dial (§10) is the spine that unifies vibe
(levels 1–2) and agentic (levels 3–4) into one build.**

## 12. Open items to confirm before build (Part-7 residue + gap-review)
- **Paradigm depth:** chat-in-dock now, but §7 durable-bg is the seam toward an Antigravity-style Inbox — build the seam, defer the Inbox UI.
- **Steering vs charter vs pins (resolved, §1):** three separate layers — `steering` = author-written rules, `anchor`/charter = task state, `pinned` = ad-hoc. Encoded in the bucket model.
- **Plan mode placement:** a fourth *mode* (Ask/Write/Compose/Plan) vs a Shift-Tab pre-phase on any mode — decide at build (§5b).
- **[verify] list:** (a) provider-kind detection for the Anthropic overlay; (b) which MCP servers expose resources/prompts **and the `X-Project-Id`-dropped-envelope workaround** (memory `gateway-drops-xprojectid-envelope`) — take `book_id` as an explicit arg; (c) pre-send token estimate accuracy per provider; (d) memory-tool beta-header plumbing through provider-registry; (e) PlanForge engine promotion status (blueprint → `composition-service`) needed before §5b.

---

## 13. Edge cases & failure modes (build/QA checklist)

Most of these are *interactions between sections* that a single-section design misses — the class that only
shows up when the modes are combined. HIGH = spec-changing (folded into §1/§3/§10 above); MED/LOW = build-time
but must be handled, not discovered in prod.

| # | Sev | Scenario → failure | Handling (where) |
|---|---|---|---|
| 1 | 🔴 | `chars/4` estimate on VN/CJK POC content under-counts 4–8× → meter lies, compaction mis-fires → overflow | script-aware/tokenizer estimate (§1) |
| 2 | 🔴 | Full-compact model call fails/garbles in a headless autonomous run → poisons all downstream prose | retry → hard-truncate → `compaction_failed` breaker (§3, §10) |
| 3 | 🔴 | Reject upstream chapter but accept a downstream one threaded from it → canon contradiction | dependency-ordered accept/reject + cascade warning in Run Report (§10) |
| 4 | 🔴 | `system+steering+anchor+pinned` alone exceed budget → compaction of conversation can't help | soft caps + warn on steering/pinned; last-resort evict oldest pinned (§1/§3) |
| 5 | 🔴 | Autonomous run hits a not-allowlisted side-effecting tool → no human to approve | declare tool allowlist at the start-gate; else breaker (§10, §4) |
| 6 | 🟠 | Model switched mid-session → new `context_length` smaller than current input | recompute meter vs new model; compact immediately if over (§1/§2) |
| 7 | 🟠 | Manuscript changed between plan-approve and draft → stale plan | OCC-style drift check on the plan (base version), like `propose_record_edit` (§5b) |
| 8 | 🟠 | Per-bucket breakdown (estimated) ≠ measured total promptTokens | measured total = truth; breakdown = labeled approximate (§2) |
| 9 | 🟠 | Agent turn starts with a dirty editor buffer → which body does the checkpoint snapshot/revert? | snapshot the working buffer; reconcile with the G7 dirty-guard (§5c) |
| 10 | 🟠 | Browser closed; user reopens on another device → run/report gone | server-side runs list + retrievable Run Report (§7/§10) |
| 11 | 🟠 | Two runs started over the same chapters → conflicting writes | per-unit lock + scope-fence rejects overlap (§10) |
| 12 | 🟠 | Budget cap exhausted mid-run → partial completion | Run Report: "stopped at ch3/8, budget"; partial work saved + reviewable (§10) |
| 13 | 🟠 | Collaborator edits shared per-book steering → affects the owner | steering write-tier = owner + E0 grantees, not any collaborator (§1a) |
| 14 | 🟠 | `@thread` dumps a huge prior conversation; MCP resource enumeration leaks other tenants | size-cap @-mentions; owner-only filter on resource LIST (not just per-resource gate) (§4) |
| — | 🟡 | Compaction while streaming / while a frontend-tool gate is suspended → resume-state must survive | exclude active tool args (done §3a); guard resume-state |
| — | 🟡 | "New from summary" — what carries (steering/tools/skills/pins)? | define the carry-set explicitly (§3) |
| — | 🟡 | Hunk-level accept of an atomic edit (a rename that must apply everywhere) → partial corrupts | mark non-independent hunks all-or-nothing (§5c) |
| — | 🟡 | BYOK credential revoked mid long-run | run checks credential validity at each checkpoint; pause+notify if gone (§7) |
| — | 🟡 | Critic sub-agent finds a violation mid autonomous run → interrupt or report-at-end? | feeds the breaker policy (interrupt on severe; else Run Report) (§6/§10) |

**Acceptance (cross-cutting):** the P1 compaction live-smoke MUST run on a **VN/CJK chapter** (not English)
to catch edge #1; the autonomous-run smoke MUST inject a compaction failure to prove edge #2's breaker; a
threaded-chapter accept/reject test MUST prove edge #3's cascade.

## Changelog
- **2026-07-02 v4 (scenarios & edge cases):** added **§13 Edge cases & failure modes** (14 scenarios, HIGH folded into §1/§3/§10). Key design changes: **script-aware token estimate** (edge #1 — `chars/4` breaks on VN/CJK POC content); **compaction failure-mode** (edge #2 — retry→hard-truncate→breaker, critical for headless autonomous runs); **dependency-ordered per-chapter accept/reject** (edge #3 — threaded canon); **start-gate tool allowlist** (edge #5 — no human mid-flow in autonomous); non-evictable-bucket overflow guard (edge #4); per-unit lock + multi-device run visibility (edges #10/#11). P1 compaction smoke must use VN/CJK content.
- **2026-07-02 v3 (autonomy dial):** added **§10 Autonomy modes** — one dial (Compose/Supervised/Autopilot/Background) unifying the mid-loop "vibe" mode (levels 1–2) and the start/end "agentic" mode (levels 3–4) over a shared pipeline (start-gate = plan+scope+budget+breaker; during = guardrails; end = Run Report + per-chapter accept/reject + Revert-All; per-run foreground/background toggle). Renumbered Priority→§11, Open-items→§12.
- **2026-07-02 v2 (gap-review vs 07R):** promoted **Plan mode (§5b)** to P1 — the strongest omitted convergent pattern; split out a dedicated **`steering` bucket + store (§1/§1a)**; added **SKILL 3-tier, @-mention, per-server-tool approval (§4)**; added **turn checkpoints + hunk review (§5c)**; made **reversibility→autonomy** an explicit principle (§5); routed **memory-for-canon through existing pending-facts (§8)**; clarified **SharedWorker vs durable + notification-service (§7)**; flagged the **gateway `X-Project-Id` envelope** constraint (§4/§11).
- **2026-07-02 v1:** initial spec from 07R Part 6.
