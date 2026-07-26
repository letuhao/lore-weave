# Chat Quality & UX Wave — plan (2026-07-03)

**Trigger:** user-mandated quality pass BEFORE the RAID FE tail (C6/C1 panels). 8 pain points:
(1) no context indicator + no compact button, (2) no per-category context-management GUI
("input 50K — WHAT is 50K?"), (3) thinking toggle → effort dropdown, (4) mode toggle → dropdown,
(5) other UX gaps vs the big players, (6) MCP failure rate too high, (7) no trace of which
tools/skills are loaded (state machine + realtime FE), (8) model picker chaos.

**Evidence base (5 parallel investigations, 2026-07-03):** FE current-state map · BE context-assembly
map · live MCP failure audit (real chat DB) · provider-registry data-layer map · web research
(Claude Code /context + compact, Cline context bar, Cursor modes/models, Copilot hover breakdown,
Codex CLI, LibreChat/LobeChat, OpenRouter). Key verified facts:

- `ContextMeter` ALREADY renders in ChatHeader (contextBudget frame consumed end-to-end, agui-only)
  — item 1's gap is only phrasing, hover detail, and the compact button.
- Prompt has **13 distinct categories** assembled in ONE place (`stream_service.stream_response`
  system_parts); **tool schemas are never token-measured anywhere** (likely the biggest hidden bucket).
  knowledge-service computes per-section tokens internally but returns only a total.
- Compaction is **ephemeral** (in-memory per turn; DB never rewritten) → "Compact now" needs a
  persist path. No manual seam exists.
- **MCP hard-error rate 26–30%** (468 calls sampled): #1 hallucinated `base_version` → 409 storm
  (22% of errors), #2 list-vs-string arg shape, #3 closed sets in prose not enum, #4 dead-end error
  messages ("a project must be in scope", gateway "provider error"), #5 pydantic noise leaks.
- `AgentSurfaceTracker` + `agentSurface` frame ALREADY exist (the item-7 state machine) — gap is
  payload richness (per-server grouping, advertised set, schema token cost) + FE grouping + i18n.
- provider-registry ALREADY has `is_favorite` + PATCH route + server-side `?capability=chat`
  (chat also matches undeclared `{}` local models); chat's two pickers just don't pass it.
  No sort_order; `pricing` column exists but not in the list SELECT; `user_default_models`
  whitelist excludes `chat`. FE: ~19 scattered pickers, 2 duplicate API modules/types.

**Market anti-patterns to respect (real user backlash):** never hide the context % once shipped
(Cursor 2.0); terse % text beats a chunky progress bar (Codex #17313); never force thinking-only
(Cursor 3.1.17); modes are load-bearing — don't remove/rename casually (Cursor 2.1).

---

## Milestones (ordered)

### W0 — MCP Reliability Hardening [BE, L] — agent quality first
The 26–30% error rate directly degrades every agent feature; fix before polishing GUIs.
Data-ranked fixes:

1. **`base_version` hallucination trap** (glossary book_tools.go): return the CURRENT version inside
   the 409 error (one-step retry, no ontology re-read); treat an implausible timestamp (< row
   created_at) as "not read" (mirror the existing `changes`-shape shim).
2. **Closed sets ⇒ real JSON-schema `enum`** (`level`, `field_type`, `status`, `scope`, …) across
   glossary/jobs/knowledge/translation MCP servers — the FE-tools LOCKED rule extended to MCP.
   Add a `CLOSED_SET_ARGS`-style contract test per server.
3. **Accept `str | list[str]` on filter-shaped args** (status/scope/model_ref/book_id) or error with
   "a single value, not a list" — kills the observed retry loop.
4. **Model-directed error rewriting at the MCP layer:** intercept pydantic/jsonschema failures →
   one-line directive ("`scope` must be a single string: 'system' or 'user' — not a list"); drop
   pydantic-docs URLs. Audit all "must be in scope" strings → name the arg + how to obtain it
   ("pass `project_id`; find yours with kg_project_list").
5. **Gateway error classification** (ai-gateway handlers.ts): keep URL-leak protection, but classify
   retryable-transport vs rejected-args vs unknown-tool with a sanitized one-liner each.
6. Tail: `glossary_propose_batch` worked example in description (4/4 fail), duplicate-create errors
   point at the patch tool.
7. **Telemetry so improvement is measurable:** a `tool-health` SQL view (or internal route) over
   `chat_messages.tool_calls` jsonb — per-tool calls/errors/7d. Re-run the audit SQL after a soak;
   target: hard-error rate < 10%.

Verify: unit per fix + contract tests; live smoke = gemma driving glossary_book_patch on a stale
version self-corrects in ONE retry; failure-rate SQL before/after.

### W1 — Context-Breakdown Spine [BE, M]
One seam, one frame:
- Measure **per-category tokens at assembly** (stream_response system_parts) + **tool-schema tokens**
  at the advertise chokepoint (`_advertise_discovery_tools`) — split frontend-tools vs MCP-tools.
- knowledge-service `build_context` returns its internal per-section map (glossary/facts/passages/
  summaries) instead of only a total.
- Extend the `contextBudget` CUSTOM frame with `breakdown: {category: tokens}` + `baseline_tokens`
  (fixed overhead before the first user word) + `until_compact_pct` (distance to the 0.75 trigger).
- Emit a new `compaction` CUSTOM frame from the existing `CompactionReport.to_event()` (today it's
  only logged) — feeds the W2 toast.
- Persist `context_breakdown JSONB` on `chat_messages` (per-turn history becomes traceable — the
  "no way to trace" complaint).

### W2 — Context GUI [FE, M]
- ContextMeter: phrase as **"until auto-compact"** (Claude Code), keep the terse %; hover =
  baseline transparency (Copilot: "system + tools: X tok before your first word") + used/limit.
- **Click meter → drill-down panel** (/context style): stacked bar + category rows (system prompt ·
  memory/knowledge (sub-split) · steering · skills · MCP tool schemas · frontend tools · history ·
  tool results · free · compact buffer), each row linking to its manager (rack, session settings).
- **Per-message token footer** (Windsurf): "↑1.2k ↓840 · $0 (local)" under assistant messages —
  data already in `chat_messages.input_tokens/output_tokens`.
- **Compaction toast/badge** on the new `compaction` frame ("earlier turns summarized").

### W3 — Manual Steerable Compact [FS, M]
- BE: `POST /v1/chat/sessions/{id}/compact {instructions?}` → summarize old turns with the session's
  model (reuse `_summarize_for_compaction`), **persist**: `chat_sessions.compact_summary TEXT` +
  `compacted_before_seq INT`; history loader splices summary + post-seq messages. Idempotent re-compact.
- FE: "Compact now" button on the meter/drill-down + optional preservation-instructions field
  ("keep all plot promises and character names" — the novel-domain killer feature per research).

### W4 — Input-bar dropdowns [FE + small BE, S]
- **Effort dropdown** replacing the Think/Fast pill: `Fast / Standard / Deep` (enum
  `reasoning_effort` on the chat request; map per provider-kind — Anthropic budget_tokens, OpenAI
  reasoning_effort, local models degrade to on/off; NEVER force thinking). Investigate the current
  thinking-param path first (small).
- **Mode dropdown** replacing the 3-button Ask/Plan/Write pill: one-word colored label + icon,
  dropdown for discoverability, optional Ctrl+. cycle (Claude Code shift-tab pattern).
- i18n ×4 locales.

### W5 — Shared ModelPicker [FS, M]
- Quick win (can ship with W0): chat's `NewChatDialog` + `SessionSettingsPanel` pass
  `capability: "chat"` — rerankers/embedders disappear (server support exists).
- BE small: add `pricing` to the user-models list SELECT; whitelist `chat` in `user_default_models`;
  favorites-first `ORDER BY is_favorite DESC, created_at DESC`.
- FE: ONE shared `<ModelPicker capability=…>` — search, **favorites pinned on top** (star toggle
  in-row via existing PATCH route), recents (via `/v1/me/preferences` + syncPrefs — no migration),
  grouped by provider, per-row badges: context length · capability icons · "$0 local"/"$" hint ·
  favorite star. Consolidate the 2 duplicate API modules + UserModel types into one.
- Rollout: chat surfaces first → knowledge/composition/plan-forge → the rest of the ~19 call sites.

### W6 — Tool/Skill Loading Visibility [FS, S-M]
- BE: extend `agentSurface` payload — advertised tool names per pass, **per-MCP-server grouping**
  (owner service), schema token cost (from W1), deferred-vs-loaded counts.
- FE: AgentContextRack groups chips by server with status dot + "N tools · X tok" chip; runtime
  inspector shows the live phase transitions (state machine already exists — display only).
- Fix the i18n gap: `rack.*` / `inspector.*` keys are MISSING in all 4 chat.json locales today.

### Backlog (from the market-gap scan, consciously not this wave)
Prompt-cache timer (Windsurf) · block-grid context visualization · intent-based model naming
(Instant/Thinking/Pro) · in-composer "N tools" live chip beyond the rack · per-category history chart.

---

## Cross-cutting rules
- Chat FE files only — no collision with the dockable track's studio/editor seams (verify dirty set
  before each commit; exact-file staging).
- Every stream-frame change: agui + legacy emitter parity (legacy may no-op but must satisfy the
  Protocol — the contextBudget try/except silent-drop is the cautionary precedent).
- Every new closed-set arg ⇒ enum + contract test (both FE-tools AND MCP now).
- Live smoke with a real local model (gemma) per wave-exit; suites full-run fresh.

## PO decisions (2026-07-03, user)
1. **Order: W0 + W1 IN PARALLEL** (disjoint files: W0 = glossary/jobs/knowledge-MCP/translation/
   ai-gateway; W1 = chat-service + knowledge context builder). Fan-out sub-agents, serial
   integration, ONE combined verify (fanout-independent-slices rule).
2. **W3: PERSIST compact into the session** (compact_summary + compacted_before_seq on
   chat_sessions; history loader splices; multi-device consistent).
3. **W5: SWEEP ALL ~19 pickers** this wave (shared component adopted everywhere, duplicate API
   modules/types consolidated).

File-collision guard for the parallel pair: chat-service belongs to W1 EXCLUSIVELY (the W0
tool-health view/route physically lives in chat-service → folded into W1's scope);
knowledge-service split: W0 owns app/mcp/server.py + app/tools/* error strings, W1 owns
app/context/* — no shared files.
