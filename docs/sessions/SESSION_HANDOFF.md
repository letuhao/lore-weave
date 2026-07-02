# ▶▶ NEXT SESSION STARTS HERE — **AUTONOMOUS RUN (user-mandated, fable-5): ✅ Track 4 salience COMPLETE (P0–P4 shipped flag-gated + eval executed; P5 = trigger-gated decision records, spec §5). NEXT: RAID remainder C5→C4→C1→C2→C6→Wave D (load-bearing ones get Decision Records) → OSS wave (scrub/license/CI/docs; publish button = user's). Contract: local LLM only (LM Studio BYOK; NEVER the gpt-4o probe), push/PR = normal delivery, hard-stops = destructive-ops-outside-test-account + 3-strike. ⚠️ CONCURRENT human-in-loop agent on the same checkout (dockable migration) — stage exact files, check `git status` before every commit.** Spec [`salience-track4`](../specs/2026-07-02-knowledge-salience-track4.md) + [`07S`](../specs/2026-07-01-writing-studio/07S_studio_agent_standard.md) + plan [`studio-agent-raid`](../plans/2026-07-02-studio-agent-raid.md). · 2026-07-02**

> **▶ Track 4 SALIENCE — COMPLETE 2026-07-02 (autonomous run).** All buildable phases shipped flag-gated (defaults =
> byte-identical): **P0** access telemetry (live-proven) · **P1** access blend (eval verdict: KEEP w=0 — explicit-query
> REGRESSION, spec §8b) · **P2** cross-encoder L3 rerank (live-proven e2e via local bge-reranker; per-project opt-in)
> · **P3a** graph-native promotion (evidence/mention/edit-recency) · **P3b** thumbs→entity attribution (user
> challenged the deferral; verification DISPROVED it — consumer existed, 1 additive column sufficed; `4635f3dfb`) ·
> **P4** pointer demotion instead of glossary drop (+`memory_recall_entity` as the expand affordance — no new tool
> needed) + widened 2-hop L2 retry on fact-miss (default ON, kill-switch; `d535293fd`). **P5 = 4 decision records**
> (R-T4-03 prune / 04 auto-merge / 08 metadata / 09 compaction-LFU-bridge), each verified + trigger-gated in spec §5
> — unlike P3b these survive scrutiny (data-safety / no-signal / hot-path-cost reasons, not effort). Salience flip
> gate = ambiguous-query eval (P1's explicit-query set penalizes re-ranking by construction). Eval CLI:
> `python -m eval.run_salience_eval`. Also cleared en route: book `_text` bug class (5 sites), worker skip
> false-green, config write-path, FE PUT-replace clobber.

> **▶ STUDIO DOCKABLE MIGRATION — WAVE 1 SHIPPED 2026-07-02** (spec [`11_dockable_migration.md`](../specs/2026-07-01-writing-studio/11_dockable_migration.md),
> human-in-loop track running IN PARALLEL with the autonomous run — conflict-first ordering per W1-5). Foundation
> seams: **F2 status-bar contribution API** (`registerStatusBarItem`/`useStatusBarItems` — ⚠️ **RAID A3 status-bar
> meter MUST register through this, never edit `StudioStatusBar.tsx` directly**; first consumers shipped: unread
> badge + 24h cost meter, bus-owned `notificationsUnread`), **F1 `openPanel(…, {params})`** deep-link (+
> `updateParameters` when open), **F3 `resolveStudioLink`/`followStudioLink`** (same-book chapter→focus, panel
> paths→openPanel, fallback = NEW TAB — `navigate()` in panels is a defect). Panels: `usage`/`trash` thin wraps
> (TrashPage `embedded` prop), `notifications` (resolver + bus unread sync), `settings` (route tab → `params.tab`).
> `ui_open_studio_panel` enum +4 + contract JSON regen done INSIDE the Track-4 window (W1-7 — later RAID B/C waves
> regen on top, no race). VERIFY: FE 3085/3085 + chat-service frontend-tools 43 green.
> **`D-DOCKW1-LIVE-SMOKE` CLEARED 2026-07-02 (Playwright live browser smoke, vite:5199 + rebuilt chat-service):**
> status-bar badge `99+` + meter `$1.17` live with real data; meter-click → Usage panel (1531 real rows); badge-click
> → Notifications panel; palette lists+opens all 7; Settings 6 tabs (mcp Q-GATE on); Trash embedded (no breadcrumb);
> **agent loop by EFFECT:** gemma-26b (LM Studio) got "mở panel Trash" → `ui_open_studio_panel(trash)` (NEW enum
> value) → Lane-A → dock tab FOCUSED in 6s → model confirmed truthfully. Side-findings (pre-existing, not W1):
> `D-TRASH-GLOSSARY-404` — TrashPage's per-book `GET …/glossary/entities?lifecycle_state=trashed` 404s (glossary
> trash tab dead; gate #1 out-of-module); notification SSE reconnect dies on jwt-expired (`?token=` never refreshes —
> long studio session loses the live badge); **LM Studio queue can WEDGE after a client disconnects mid-stream**
> (`lms ps` says IDLE but completions hang ∞) — fix: `lms unload <model> && lms load <model> --context-length N`.
> **/review-impl (b1dca941b): 2 MED + 2 LOW found + FIXED** — protocol-relative `//` external-origin escape
> (notificationLink + resolver both hardened), settings same-value deep-link swallowed (now `onDidParametersChange`),
> badge pre-fetch-0 clobber (`unreadLoaded` gate), catalog⇄panel import cycle (i18n-convention titleFor). 3089/3089.
> **Side-findings CLEARED (user-mandated fix-before-wave-2):** `D-TRASH-GLOSSARY-404` FIXED — root cause FE-only:
> `useTrashItems` guessed `/v1/books/{id}/glossary/entities?lifecycle_state=trashed` (never existed) while
> glossary-service already ships the FULL recycle-bin API (`/v1/glossary/books/{id}/recycle-bin` + `/{eid}/restore` +
> `DELETE /{eid}`, `permanently_deleted_at` soft-purge + snapshot trigger). 3 URLs re-pointed; live-proven e2e in the
> studio Trash panel (real backlog rows listed; GUI Restore → `deleted_at` NULL; GUI purge → `permanently_deleted_at`
> set). *The "blocked on a missing route that already exists" pattern struck again.*
> **SSE jwt-expiry FIXED** — `useNotificationStream` on error checks the JWT `exp` (fail-open for opaque tokens):
> expired → single-flight `refreshAccessToken()` (now exported from api.ts) → `lw-auth-refreshed` → effect reconnects
> with the fresh token; refresh-fail → idle. No more infinite dead-token reconnect loop in idle studio tabs. +3 tests.
> LM Studio wedge stays an external-tool recipe (memory); a chat-service first-token timeout guard belongs to RAID
> Wave-A's LLM seam if wanted. FE suite 3092/3092.
> **⚠️ Parallel-run lesson (live hit):** Track-4 commit `ab0523df6` swept this track's STAGED F1/F3 files into its
> own commit (shared working tree) — protocol now: `git add … && git commit -- <explicit paths>` in ONE invocation.

> **▶ Track 4 SALIENCE (knowledge) — P0+P1+P2 SHIPPED + REVIEWED 2026-07-02.** Spec `85a0fb961`. **P0 substrate**
> (`20cf1e626` + review `e7e96fa13`): `entity_access_log` (tenancy PK user+project+entity), `EntityAccessRepo`
> (fire-and-forget, never raises), `BuiltContext.surfaced_entity_ids`, router records off-latency-path (strong task
> ref — GC footgun fixed), 19 tests. **P2 cross-encoder rerank** (`b514f6282`): step 7b in `select_l3_passages` via
> existing `RerankerClient` (BYOK `extraction_config["cross_encoder_rerank_model"]`), degrade→MMR on any bad shape,
> +8 tests. **P1 salience blend** (`a66f27bd8` + review `b53ed5de0`): `rank' = rank + w·norm(decayed_access)`,
> read-time Ebbinghaus (no cron), `salience_access_weight=0.0` default = byte-identical (no DB read), **pins ALWAYS
> lead** (review caught pin-vs-budget-trim drop), +12 tests. 483 context unit tests green.
> **Eval standup (in progress):** POC book = `019f1783-ebb4` (12ch VN, ~118K chars), knowledge project
> `019f1783-ecca`, embed bge-m3 `019eeb08-8bff` (dim 1024, benchmark PASS r@3=1.0), extraction LLM gemma QAT
> `019ebb72-27a2`. **Found+fixed a HIGH book-service bug class live:** publish guard + revision-text + getRevision +
> compare + canon-search all extracted ONLY the editor `_text` projection → standard-tiptap chapters false-rejected
> from publish AND silently skipped by extraction ("text unavailable") AND invisible to canon search. Fixed with
> `_text ∪ $.**.text` union (`12a702b2d`, `7b9cd4fda`; +4 DB-gated tests vs real PG18, BOOK_TEST_DATABASE_URL).
> Also: worker-ai image was STALE (cancel_check SDK drift — chat-scope job failed) → rebuilt worker-ai +
> knowledge-service. **Eval CLI** `python -m eval.run_salience_eval` seed/measure (`0170a414c`, +9 tests).
> **NEXT: extraction completes → seed (5 passes × 4 focus) → measure → P1/P2 flip decision by data → P3.**
>
> **▶ Track 4 EVAL EXECUTED + reviewed 2026-07-02 (`b1de69a13`, `ab0523df6`).** KG: 40 entities/125 events/181
> passages (re-publish re-armed passage ingest after the `_text` fix window). **P0 LIVE-PROVEN** (20 HTTP builds →
> access-log rows). **P1 verdict: KEEP w=0** — REGRESSION on explicit queries (MRR .531→.513; tier/FTS near-optimal
> when the query names the entity; seed boosts the whole co-surfaced cluster). Revisit trigger: ambiguous-query eval
> or P3 per-entity signals. **P2 LIVE-PROVEN** e2e (build → /internal/rerank 200 local bge-reranker → reorder logged;
> passage-hit .75→.80 n=12) — stays per-project opt-in. Spec §8b has the table. **Review fixes:** config write-path
> was unreachable (extra=forbid) → added; FE editor PUT-replace would silently CLEAR the rerank keys → preserved-on-
> omit/clear-on-explicit-empty (+2 tests). **`D-WORKER-SKIP-FALSE-GREEN` CLEARED (`b24143d2f`, user fix-now):**
> `extraction_jobs.items_skipped` column + `skipped_delta` threaded through `_advance_cursor(_and_emit_run)` (both
> skip sites, tx-fallback preserved) + `_complete_job` stamps error_message when skipped ≥ total ("no work
> performed") — status stays complete (failed would trip campaign breakers). +4 tests, worker-ai 299 green, DDL
> applied live, worker-ai rebuilt.

> **▶ STUDIO AGENT RAID — IN PROGRESS 2026-07-02 (`feat/studio-agent-raid`, autonomous run).** Big RAID: agentic
> chat to industry standard (context meter+compaction, plan-mode, steering, MCP resources/prompts, HITL modes,
> checkpoints, memory-for-canon, autonomy dial). **Wave P (PlanForge takeover) — DONE through M4:** P0 committed
> inherited M3 checkpoint (38 tests); **P1 review-impl** fixed patch no-spec 409→422 (+tests); **M4** shipped 8 MCP
> `plan_*` tools + chat `plan_forge` skill + D-PF-APPLY-HONESTY (`no_change` on unchanged refine) + review_checkpoint
> / handoff_autofix service methods (73 composition MCP + 9 chat skill + 50 plan_forge + provider-gate green).
> composition-service rebuilt. **M5 (Studio planner dock) DONE + browser-smoke-proven** (palette→Planner→paste→
> propose(rules)→run+artifacts→validate→S1-S8 report; a null `fidelity_score.toFixed()` crash was caught live
> and fixed + regression-tested). **Wave P COMPLETE (7 commits).** **NEXT: Wave A — context spine** (A1 script-aware
> tokenizer for VN/CJK → A2 budget + `contextBudget` event → A3 FE meter → A4 hybrid compaction micro→full→fail →
> A5 Anthropic overlay → A6 manual compact). Grounding facts in the RAID plan §1: `context_length` in chat-service
> `models.py:466`, provider_kind at `:462`, Anthropic passthrough via `streamRequest.Extra` + `anthropic_streamer.go:251`.
> Reconciliations: gateway forwards X-Project-Id (memory `gateway-drops-xprojectid-envelope` stale); saga breaker
> is probe-reconcile not XADD.
>
> **▶ Wave A (context spine) — CORE DONE + BROWSER-PROVEN 2026-07-02.** A1 script-aware tokenizer (CJK≈1 tok/char,
> VN denser, ASCII chars/4 — fixes edge #1; 8 tests, Chinese >3× the broken chars/4) → A2 `contextBudget` AG-UI event
> on RUN_FINISHED (used vs `context_length−max_tokens−safety`; NULL→"—") → A3 FE `ContextMeter` in the chat header
> (bands 70/85; 10 tests) → A4 provider-agnostic compaction (`compaction.py`: micro-evict tool-results keep-N+exclude
> web_search → optional summarize → hard-truncate; edge #2 summarize-fail→truncate, edge #4 overflow flag; 9 tests;
> wired GUARDED before the provider call, summarize=None). **LIVE browser proof:** the meter shows "46% · 18056/39488
> tokens" on a real gemma-26b turn; compaction correctly inert at 46%<75% (turn intact). **DEFERRED (tracked):**
> `D-RAID-A5-ANTHROPIC-OVERLAY` (Claude-only context-editing `clear_tool_uses`+memory tool via provider-registry Go
> plumbing — low ROI for the local-model POC that A4 already covers) · `D-RAID-A6-MANUAL-COMPACT` (manual Compact
> button + New-from-summary — enhancement over the working auto-compaction; needs a summarize endpoint). **NEXT: Wave C**
> (C1 steering store · C2 HITL modes+per-tool approval · C3 SKILL 3-tier · C4 @-mention · C5 MCP resources/prompts ·
> C6 turn checkpoints+hunk review), then Wave B (Plan mode — mostly delivered by Wave P PlanForge), then Wave D (autonomy dial).
>
> **▶ Wave C — C3 DONE 2026-07-02; comprehensive VERIFY green.** C3 SKILL 3-tier: L1 available-skills metadata block
> (`skill_metadata_block`, `SkillDef.description`) injected always (cheap discoverability) + the resolved skill's full
> L2 body; wired into both system-prompt paths (Anthropic parts + plain); 12 skill tests. **RAID-so-far VERIFY: BE 183
> (chat-service 110 + composition-service 73) + FE 385 (plan-forge+studio+chat) green; 2 live browser smokes (M5
> planner, A2/A3 meter) with auto-fix loops; provider-gate + tsc + i18n-parity clean.** ~17 commits on `feat/studio-agent-raid`.
> **REMAINING Wave C — classified for the resumer:** SAFE-ADDITIVE (do next): **C5** MCP resources/prompts (ai-gateway
> `src/mcp/handlers.ts`+`proxy-server.factory.ts`+`federation.service.ts` add List/Read handlers; server `@resource`/
> `@prompt` decorators; chat client `knowledge_client.py` add get_resource/read; X-Project-Id IS forwarded — no workaround).
> **C4** @-mention (FE `ContextPicker` inline). LOAD-BEARING (warrant a human POST-REVIEW — tenancy/schema/permission,
> the CLAUDE.md-flagged bug class): **C1** steering store (new `book_steering` table + owner+E0 tenancy + inclusion modes
> + `steering` bucket render), **C2** HITL modes + per-server-tool approval (tool-surface filter — can regress tool
> availability), **C6** turn checkpoints (book-service revision-restore endpoint + hunk review). **Wave D autonomy dial**
> (D2 start/end-gate FSM + guardrails) is the biggest load-bearing piece — reuse campaign-saga + PlanForge + Quality Report.

> **▶ CHECKPOINT — Wave A (context spine) SOLIDIFIED 2026-07-02 (user: "make previous implement solid before we
> continue").** Ran `/review-impl` over the whole context spine (token_budget, compaction, wiring, ContextMeter).
> **Caught + fixed a stale test first:** the A2 `contextBudget` CUSTOM frame was never added to the AG-UI happy-path
> exact-sequence assertion → the FULL chat-service suite was RED (prior "green" was a subset). Fixed (`128941136`),
> full suite now 525. **HIGH bug found + fixed (`42d003f42`):** compaction on the **resume path** (agent→GUI 2nd pass,
> `resume_stream_response` passes the live `working` array w/ assistant `tool_calls` + `role:tool` results) could
> orphan a tool-call/result pair on hard-truncate / summarize tail-slice → provider **400**. Unit tests missed it
> (plain user/assistant msgs). Fix: truncate on whole tool-exchange **atoms** (`_atoms`/`_recent_tail`) — keep/drop
> whole exchanges, never split. +3 TestToolPairSafety. **Summarizer WIRED (`356527c26`, per user decision "wire now"):**
> `compact_messages` now async; tier-2 compresses the droppable MIDDLE via the session's own model
> (`_summarize_for_compaction`, provider-agnostic gateway); failure → hard-truncate (edge #2). Cross-turn history is
> flattened `{role,content}` (no pairs there — safe); memory [[compaction-resume-path-carries-tool-pairs]].
> **LIVE SMOKE PASS (per user decision "do the live smoke"):** in-container against real gemma QAT (200K) — forced
> compaction (10034→~2880 tok), asserted **no orphan**, sent the compacted tool-containing array back to gemma →
> **provider accepted on BOTH paths** (run1 summarize-success w/ real synopsis; run2 summarize-fail→truncate fallback,
> both orphan-free + accepted). chat-service **525 passed**; compaction 13 tests. **Wave A is now solid.**
> **LOW items CLEARED (`2b25bd923`):** (1) the tool loop now re-compacts `working` at the top of EVERY pass
> (atom-grouped, guarded, summarizer=session model; `effective_limit` threaded into `_stream_with_tools`) so a long
> multi-tool turn can't overflow mid-turn — +2 wiring tests (fires per pass with limit / skips when None); (2)
> `estimate_messages_tokens` now counts assistant `tool_calls` (name + arguments JSON) — +1 test. In-loop compaction
> reuses the already-live-proven `compact_messages` (provider-accepts the compacted tool array) — covered transitively,
> not separately live-smoked. **chat-service 528 passed; provider-gate green. Wave A fully closed.**

> **▶ Writing Studio foundation SHIPPED + PROVEN + PR'd 2026-07-02 (`feat/writing-studio`, 130 commits → `main`).**
> Frame + palette (⌘P/⌘⇧P) + share-data (StudioHost/bus/registry #08) + navigator (#02 search/totals) + Compose
> panel (chat AS-IS via `actionBar`) + Tier-4 editor hoist (#04) + navigator→editor + agent Lanes A/B/C. **Live
> Playwright browser smoke** (real stack, gemma-26b, POC book) verified every axis AND caught a real bug the
> unit/integration/raw-stream tests all missed: `ui_open_studio_panel` schema↔resolver drift (model sent `panel`
> not `panel_id`, resolver silent no-op, model hallucinated success — `f1f9e9966`). **Standardized the fix into a
> machine-checked FRONTEND-TOOL CONTRACT (`0df466d15`)**: `contracts/frontend-tools.contract.json` +
> `test_frontend_tools_contract.py` (BE snapshot + closed-set-must-be-enum) + `frontendToolContract.test.ts`
> (FE Proxy-access proves each resolver reads every required arg + no-silent-no-op) + `panelCatalogContract.test.ts`
> (enum ⊆ dock catalog). CLAUDE.md § "Frontend-Tool Contract (LOCKED)". FE 232 chat + full studio green, BE 50 green.
> **NEXT = the agentic-chat deep-dive** — research + standard in [`07R_chat_agent_industry_research.md`](../specs/2026-07-01-writing-studio/07R_chat_agent_industry_research.md)
> (industry map: Claude Code/Cursor/Antigravity/Kiro/Copilot/Zed/Aider/Continue + cross-cutting; LoreWeave gap map;
> 3-tier recommended standard). **Priority 🥇1–3:** context meter + tiered warnings + typed buckets; compaction
> (auto microcompact + manual button; Anthropic context-editing/memory OR provider-agnostic — OPEN Q); web-search
> surfaced. Open questions (07R Part 7): paradigm depth, compaction ownership (BYOK-Claude vs local-model portable),
> bible-as-steering vs charter, sub-agent scope. **Decide the standard doc first, then build.**

> **▶ PlanForge BLUEPRINT SHIPPED 2026-07-01** — POC frozen at `scripts/plan-forge-poc/` (fidelity 1.0, elaboration 1.0, chat HIL I1–I4 100%). **SSOT implement handoff:** [`09_PLANFORGE_BLUEPRINT.md`](../specs/2026-07-01-plan-forge/09_PLANFORGE_BLUEPRINT.md) (acceptable bar tier A/B/C, MCP sketch, M1–M5, deferred). Eval chain: [`04_PO_REVIEW.md`](../specs/2026-07-01-plan-forge/04_PO_REVIEW.md) GO → [`06`](../specs/2026-07-01-plan-forge/06_FIDELITY_POC_EVAL.md)–[`08`](../specs/2026-07-01-plan-forge/08_CHAT_HIL_POC_EVAL.md). **NEXT (PlanForge implement session — not this Writing Studio track):** M1 port engine → `composition-service/app/engine/plan_forge/` per blueprint §6 + [`docs/plans/2026-07-01-plan-forge-promote.md`](../plans/2026-07-01-plan-forge-promote.md). POC CLI kept for regression until M2 green.
>
> **▶ PlanForge Deferred (implement session):** `D-PF-APPLY-HONESTY` (no false success when fidelity_delta=0), `D-PF-NORMALIZE` (placeholder name, VN mechanics), `D-PF-PARTIAL-REFINE` (focus_paths slice), `D-PF-CONVENIENCE-EVAL` (TTAS + Opus vs local), `D-PF-MULTI-DOC` (3 doc profiles). See blueprint §7.

> **▶ #02 Manuscript Navigator — BUILT + solid 2026-07-01 (`feat/writing-studio`, full-stack).** An adaptive
> **arc→chapter→scene** tree that scales to 10k+ chapters (VS Code Explorer recipe: virtualized rows + cursor
> paging + lazy expand). **Chapters spine = book-service keyset cursor** endpoint `GET /chapters/page?cursor&limit`
> (`(sort_order, id)` keyset, UUIDv7 tiebreak, `idx_chapters_keyset`, opaque base64 cursor, `402a92e1a`).
> **Arc/scene overlay = composition lazy-children** `GET /works/{id}/outline/children?parent_id&cursor` (keyset on
> `rank COLLATE "C", id`, `de893dae7`). **FE** `@tanstack/react-virtual` over a flattened row array; two data
> sources behind `useManuscriptTree` (no Work → flat chapters; Work → outline tree); pure `tree.ts` flatten;
> lazy expand + infinite paging + client filter; wired into `StudioSideBar` (`b21ed648e`). **`/review-impl`
> (cold-start) found + fixed:** H1 composition keyset index missing collation → full Sort (added
> `idx_outline_node_children_keyset (parent_id, rank COLLATE "C", id)`); M1 stale-response race on book switch
> (generation guard); L2 collation-qualified the `rank =` equality; C1 keyset default limit 100. M2 adaptive
> degenerate-collapse tracked as spec Debt #4. **Verified:** Go + Python unit tests, FE 19 manuscript unit
> tests (incl. M1 stale-guard, beat-filter, lazy-expand), tsc+eslint+i18n clean, **live E2E through the gateway**
> (rebuilt book+composition) — renders chapters, **keyset page-boundary no gap/dup**, filter. **Debt (spec 02):**
> #1 navigator→dock link (needs #03), #2 server chapter-search (shared `useManuscriptJump`/#06a), #3
> partial-outline merge, #4 adaptive collapse. Outline-path live E2E deferred (needs a parent-linked outline seed helper).

> **▶ Writing Studio (v2) — FRAME SKELETON built 2026-07-01 (`feat/writing-studio`, FE-only).** Incremental
> **build-while-plan** track (inverts plan-then-build): master spec + one file per component, written
> just-in-time — `docs/specs/2026-07-01-writing-studio/` (`00_OVERVIEW.md` + `01_skeleton.md`); frame mockup
> `design-drafts/screens/studio/screen-writing-studio-frame.html`. Shipped the full **fixed frame** as
> `features/studio/` (MVC): `StudioTopBar` (back·title·⌘P palette placeholder·settings), `StudioActivityBar`
> (icon rail: Manuscript/Bible/Search/Quality — switches the navigator; re-click active = collapse),
> `StudioSideBar` (active navigator, **content STUBBED**), `StudioDock` (dockview + Welcome + per-book layout
> persistence), `StudioBottomPanel` (toggle; Jobs/Generation/Issues stubs), `StudioStatusBar` (lang·⌘P·bottom
> toggle). Hooks: `useStudioChrome` (activeView/sidebar/bottom, per-book `lw_studio_chrome_<bookId>`) +
> `useStudioLayout` (dockview onReady+persist). **Verified:** tsc+eslint clean, studio i18n ×4 parity-clean,
> **browser-smoke** — all regions render, activity-switch + sidebar-collapse + bottom-toggle work, **dock never
> remounts** through chrome changes, chrome+layout persist & restore on reload, 0 console errors.
> **Solid (this track's stricter no-defer rule — unit+E2E per component):** 30 unit tests + 7 Playwright E2E
> (frame regions · activity-switch · collapse · bottom-toggle · persistence · **per-book isolation** ·
> **dock-no-remount**) all green; **`/review-impl`** (cold-start) found 2 HIGH — per-book state was frozen to the
> first `bookId` (in-session book switch corrupts the other book's storage) → fixed via a **keyed `StudioFrame`**
> remount — plus MED/LOW (persist-after-seed to dodge the upgrade trap; dropped a misleading disposable; stable
> `studio-dock` testid; removed dead `persist`), all fixed & re-verified. Debt tracked **LIFO** in the spec
> (nav→dock link · two-left-rails · top-bar Generate/Save). **NEXT (#02):**
> Manuscript navigator — real chapters→scenes tree in the Side Bar that opens/focuses a unit in the dock (the
> navigator→dock "wiring"); then #03 Compose panel (first stateful dock panel → wires the D4 state-hoist rule).
> See memory `[[editor-workmode-and-compose-must-keep-editor-mounted]]`.

> **▶ Writing Studio (v2) — BLANK SHELL shipped 2026-07-01 (branch `feat/writing-studio`, FE-only).** A NEW,
> from-scratch surface — does NOT touch `ChapterEditorPage`. **Build-vs-buy decided:** our in-house dock layer
> (`WorkspaceLayoutProvider`/`DockRail`/`FloatingWindow`/`PopoutBridge`) is a single linear tab-rail — it CANNOT
> do VS Code-style multi-region docking (splits, tab groups, nested regions, drag-split-merge). Adopted
> **`dockview-react` v7.0.2** (zero-dep, MIT, React-18, real tab-groups + split grids + floating groups + pop-out
> windows + `toJSON/fromJSON`). **Shipped:** `pages/WritingStudioPage.tsx` (empty dockview shell, `themeAbyss`,
> single Welcome panel, **per-book layout persistence** via `localStorage` `lw_studio_layout_<bookId>` on
> `onDidLayoutChange`); route `/books/:bookId/studio` under `EditorLayout`; **book-level** "Studio" CTA in
> `BookDetailPage` header (opens directly, no chapter needed); new i18n `studio` ns × en/vi/ja/zh-TW +
> `books.detail.open_studio`. **Verified:** tsc + eslint clean, production `vite build` OK (dockview bundles),
> browser-smoke — studio renders, welcome panel, layout persists (1 panel saved), 0 console errors, CTA links
> correctly. **Architecture rule carried forward:** live/in-flight state (co-writer streams, editor docs) must
> live ABOVE dockview; panels are thin views over hoisted state so closing/moving a panel never drops work —
> wire when the first stateful panel lands. **Next:** user directs which panel to add first (compose, planner,
> cast, quality…), one at a time. See memory `[[editor-workmode-and-compose-must-keep-editor-mounted]]`.

> **▶ GUI Workmode overhaul (M0 + M1 + Read) — SHIPPED 2026-07-01 (FE-only).** The chapter editor's
> "three overlapping hidden mode systems" collapse into ONE dropdown: **Write · Translate · Read · Compose**
> (`hooks/useWorkmode.ts` persisted `lw_editor_workmode`; `components/editor/WorkmodeSwitcher.tsx`). Folded
> away the scattered Pen/Sparkles toggle (now a Write-only sub-control), the Co-write bridge, the one-shot
> `handleTranslate` button (deleted), the view-translations Eye button, and the compose right-panel tab.
> **Center swaps by mode:** Write/Compose keep the manuscript editor mounted (Compose shows the studio in the
> right companion panel — the editor MUST stay mounted or the studio's insert/applyPolish ref no-ops:
> regression-tested); Translate embeds the full **`ChapterTranslationsPanel`** (extracted from
> `ChapterTranslationsPage`, which is now a thin wrapper seeding `?lang=`/`?vid=`); **Read** opens the
> existing full `ReaderPage` route (guarded) — reader already reads the draft with TTS/theme/TOC/lang-switch,
> so it's reused, not rebuilt. i18n `editor.workmode.*` × en/vi/ja/zh-TW. E2E page-object `openComposeTab`
> updated to drive the dropdown. **Tests:** useWorkmode 4 + WorkmodeSwitcher 4 + ChapterEditorPage 5 (incl.
> the Compose-keeps-editor-mounted regression guard); translation/composition/editor/pages/hooks **853 green**,
> tsc + eslint clean. **Not done:** live browser-smoke (mocked heavy components ≠ visual proof — do next);
> mobile still uses its own group shell (workmode switch is desktop-only, conscious).

> **▶ Q3 Book-level promise coverage — SHIPPED 2026-07-01.** Reframed from "auto arc-conformance":
> verified `compute_arc_report` hard-requires an `arc_template_id`, and arc templates come ONLY from the
> reference-import (`motif_deconstruct`) / authored path — the mainstream premise→pipeline flow creates
> none (no `work→arc_template` link), so auto arc-conformance is a **no-op for mainstream works** (already
> has a manual Tier-W path). The GUI-free, mainstream-valuable Q3 is the **book-level escalation of the
> promise audit** (v2 API): `quality_report.build_promise_coverage` = `extract_tracked_promises(premise,
> plan_text)` (STABLE set from the SPEC, not the prose) → `score_promise_coverage(full_book)` →
> **paid/progressing/abandoned/absent** + rates. Worker op `promise_coverage` (+ SUPPORTED_OPERATIONS +
> dispatch) + `POST /v1/composition/works/{id}/promise-coverage` (renders `plan_text` from the outline tree
> + assembles every ACTIVE chapter's prose — the ENDPOINT resolves, the worker runs). FE `promiseCoverage`
> api + `useBookPromiseCoverage` + `BookPromiseCoverageSection` in the **project-scoped `QualityPanel`**
> (threaded `modelRef`; NOT the per-chapter Polish gate). Read-only. Also fixed a duplicate `composition-quality`
> testid (QualityReportSection → `composition-quality-report`). **Live smoke** (Gemma-4-26b, vi plan+book):
> 4 tracked promises from the outline; 3 paid + **1 ABSENT** = the outline-promised "missing brother" thread
> the book never delivers — exactly the "does the book pay off the outline?" signal. `err:None`. Tests:
> quality_report 9 + worker_jobs (dispatch+serialize) + FE BookPromiseCoverageSection 5; FE 735 green.
> **Deferred:** `D-QUALITY-COVERAGE-CHUNK` (very long books overflow one score call — window it; gate #4).
> **★ Ceiling note (user):** the rest of the constellation (arc templates, motif library) each need a whole
> **CRUD GUI** — big features to plan separately, not just "wiring". See memory `constellation-wiring-ceiling-crud-guis`.

> **▶ Quality Report in the Polish gate (Q1+Q2) — SHIPPED 2026-07-01.** New track: make the **planner

> **▶ Quality Report in the Polish gate (Q1+Q2) — SHIPPED 2026-07-01.** New track: make the **planner
> exploit its own judges** (audit found the auto-loop runs critic/canon/narrative-thread/motif-conformance
> as advisory-but-BURIED, and `promise_audit` never runs at all). Q1+Q2 surface them as a **read-only
> Quality Report** in the M6 Polish gate: `engine/quality_report.py` runs the 4-dim **critic** +
> **promise_audit** (introduced/resolved/**dropped**) concurrently, degrade-safe; worker op `quality_report`
> (+ SUPPORTED_OPERATIONS + dispatch) + `POST /v1/composition/works/{id}/quality-report` (mirrors self-heal);
> FE `qualityReport` api + `useQualityReport` + `QualityReportSection` mounted in `PolishPanel` (diagnostic,
> NO accept/apply — do-no-harm). **Design:** promises are phrases not spans ⇒ read-only, not an EditProposal;
> Q2 re-runs critic FRESH (stale per-scene `_critic` is wrong after edits) — documented. **Live smoke**
> (composition→ai-gateway→provider-registry→LM Studio, Gemma-4-26b, vi CH1-style): critic scored 4 dims +
> caught the planted pronoun violation; promise audit caught the planted Chekhov's-gun as a **dropped promise
> (rate 1.0)**; both `err:None`. **Also fixed 3 PRE-EXISTING branch reds** (not mine, proven by stash):
> `test_motif_repo_signatures_frozen` (create/patch grew additive kwargs vs its exact-`==` — aligned to the
> file's own `[:N]`+`kw in` convention) + 2 `test_canon_reflect` (SimpleNamespace profile fake missing newer
> `BookProfile` fields → use real `BookProfile`). Plan: `docs/plans/2026-07-01-quality-report-polish-gate.md`.
> Tests: quality_report 4 + worker_jobs (dispatch+serialize) + FE QualityReportSection 5; full BE suite +
> FE 747 green. **Deferred:** `D-QUALITY-MOTIF-ROLLUP` (motif beat-not-realized rollup, gate #2),
> `D-QUALITY-ARC-LEVEL` (arc/book-level promise coverage v2, gate #1/#2).

> **▶ MERGE 2026-06-30: `origin/main` (Temporal-Knowledge / KAL) merged in (55 commits).** The
> knowledge-gateway (**KAL**) unifies glossary/KG reads under INV-KAL: composition's cast-roster read
> moved from `glossary.list_entities` → **`kal.roster()`** (drains the cursor — fixes the ~100-cast
> truncation). Conflict was ONLY `SESSION_HANDOFF.md`; router `plan.py` + `glossary_client.py`
> auto-merged (our `thread_state`/`exit_state`/`seed_entities` survived alongside KAL). Our `seed_entities`
> WRITE (glossary `extract-entities`) passes **both** INV-KAL gates (knowledge-access + http-surface).
> **Verified:** composition unit suite **1209 passed**; `kal.roster()` returns the 10 seeded cast;
> **e2e** on the rebuilt KAL stack — seed → KAL roster → decompose → **34/34 scenes grounded** with
> `present_entity_ids`. Our code is fully on the new standard (roster via KAL; `cast_plan`/`self_heal`
> don't touch glossary directly).


> **What this track is:** the editor/compose UX overhaul **pivoted (PO)** to fixing **output QUALITY first** — POC chapters read as concatenated scenes. Two design docs:
> - **[`docs/specs/2026-06-30-editor-compose-overhaul/`](../specs/2026-06-30-editor-compose-overhaul/)** — the GUI track (validate-first, milestones M0–M5 are a backlog menu, NOT a build order).
> - **[`docs/specs/2026-06-30-chapter-synthesis-self-healing.md`](../specs/2026-06-30-chapter-synthesis-self-healing.md)** — the synthesis track: **Phase 0** (planning connectivity, DO FIRST) → **Phase 2** (multi-pass self-heal). Ordering is locked: garbage-in (disconnected plan) can't be polished out.
>
> **▶ Shipped this session (validated, committed):**
> - **Phase 0 slice 1 (intra-chapter connectivity)** — enriched the decompose prompt (goal·conflict·outcome + causality + ending-guided). Fixed the 3 worst reviewer defects (causeless pursuit, grimoire-from-nowhere, disconnected scenes) at the synopsis level, prompt-only.
> - **Phase 0 slice 2 (cross-chapter threading)** — `engine/plan.py`: typed `ChapterExitState` (Character/World/Plot + `advances`) emitted as a same-call delta, threaded chapter→chapter (`thread_state` flag, **default OFF ⇒ today's concurrent fan-out byte-identical**; sequential when ON: prev-chapter exit = fine-grained backbone + cumulative advances = global anti-repeat). Wired through worker + router (additive optional). **Live worker smoke** (Gemma, `thread_state=True`, 12ch/36sc): chapters now open *"Tiếp nối từ…"* the prior exit-state, **arc repetition gone**. `/review-impl`: **0 HIGH**, 4 findings fixed (inline/worker response parity for `exit_state`; both-flags no-op warning; degrade-path test; advances-cap documented). **Tests:** composition unit suite **1180** + slice tests (test_plan 19, router 16, worker_jobs 18 — fixed 5 pre-existing `cancel_check` fake drift) green.
>
> **▶ Self-heal POC — the whole approach was de-risked this session (see the synthesis spec for the data):**
> - **stitch baseline** — the existing 1-pass `stitch` smooths transitions but is NOT a dedup/repair pass, and it **inflates length +68%** (a prompt cleanup did NOT fix it: Gemma rewrites-and-expands by nature; the token cap isn't a clean lever). ⇒ whole-chapter rewrite is the wrong primitive.
> - **L1 dropped** — the "scene-titles mid-chapter" complaint was a POC HARNESS artifact (`to_tiptap_doc` heading-per-scene), not a pipeline defect.
> - **Satellite editing is the answer (PO insight)** — surgical edit of a SMALL isolated span. Mechanism (2) structural isolation works on a small model: `selection-edit` on a 446-char span → ×1.01 length, motif 2→0, meaning preserved (vs whole-chapter ×1.68). Mechanism (1) trust-the-model fails on small models (the stitch result).
> - **The detector must be an LLM JUDGE, not code** (PO) — POC: Gemma returned **7 real findings** (2 logic holes incl. the fall-physics one, emotion-loop, motif, flat villain), each with a `fix` guide, **7/7 locatable (3 exact + 4 fuzzy)** ⇒ the locate step uses **fuzzy/shingle match, not exact**.
> - ⇒ **Full pipeline proven end-to-end:** `LLM JUDGE → fuzzy-locate (code) → satellite-edit (selection-edit) → splice → re-judge loop`. (POC scripts: `poc/judge_poc.py`, harness phases `satellite`/`stitch`.)
>
> **▶ Orchestrator BUILT + live-validated** — `engine/self_heal.py` (`run_self_heal`): judge→fuzzy-`locate_span`→satellite-edit→splice→re-judge; advisory skips (not-located/overlap/runaway-expansion). 12 unit tests. Live on ch1: 6 findings, **6/6 located, 4 edits, length ×1.014** (vs stitch ×1.68), surgical on-target edits. Fixed a false-zero re-judge bug (degraded re-judge now reports None). NOT yet wired to an endpoint (in-container script POC).
>
> **▶ PIVOT (PO) — re-architect PLANNING before drafting.** Reviewing the committed 12-ch plan surfaced many holes at once (no motif binding, empty cast / scene-presence, anonymous new characters, ch1 telescoped). Root cause = `decompose` is **one-shot** (same anti-pattern as whole-chapter stitch). Fix = a multi-step planning pipeline (decompose-and-refine, ONE arc). Spec: [`docs/specs/2026-06-30-planning-pipeline-architecture.md`](../specs/2026-06-30-planning-pipeline-architecture.md) · Build plan + **capability audit** (planning uses ~2/30 engines — the judge constellation promise_audit/succession_entailment/arc_conformance is idle): [`docs/plans/2026-06-30-planning-pipeline.md`](../plans/2026-06-30-planning-pipeline.md). Stages: 0 cast/world · 1 motif-select · 2 arc+tension · 3 char-arc/intro · 4 grounded decompose · 5 plan self-heal · 6 orchestration+checkpoints. Reuse-heavy (motif retriever, templates, arc_apply, self_heal pattern, the idle judges).
>
> **▶ PLANNING PIPELINE COMPLETE (Stages 0–6, all live-validated)** — replaced the one-shot decompose with a multi-step planner, each stage committed + unit-tested + live-POC'd on the Lâm Uyển premise:
> - **0 cast** (`cast_plan.py` propose_cast + `glossary_client.seed_entities`) — 10 cast (6 named + 4 new), seeded → roster → present_entity_ids.
> - **1 motifs** (`motif_plan.py` select_arc_motifs) — 4 arc motifs with roles (spine/recurring/foil/climax).
> - **2 tension** (`arc_plan.py` shape_tension_curve, deterministic) — fixes ch1=100; 100 only at climax.
> - **3 char-arcs** (`character_plan.py` plan_character_arcs) — arcs + introduction schedule (new chars @ fitting beats).
> - **4 grounded decompose** (`grounded_plan.py` + grounding block in `plan.py`) — feeds cast/motifs/tension/intros into the threaded L2.
> - **5 plan self-heal** (`plan_heal.py`) — plan-judge → satellite-edit a scene synopsis by (chapter,scene).
> - **6 orchestration** (`planning_pipeline.py` run_planning_pipeline) — chains 0→1→L1(once)→3→4→5.
> - **Capstone live POC** (`poc/io/full_pipeline.txt`): cast=10 · motifs=4 · arcs=10 · 12ch/30sc/30-with-present · **plan-heal 7/7 findings edited** (4× cross-chapter repetition, a character-before-introduction, a tension-vs-beat, a dangling setup — all real, all fixed).
>
> **▶ Production hardening DONE + the drive STARTED:**
> - **Task A (wired)** — `DecomposeRequest.pipeline=true` → the `/outline/decompose` endpoint runs `run_planning_pipeline` via the worker (`plan_pipeline` op + dispatch + allowlist). **Live e2e:** endpoint→202→worker→cast=9/motifs=4/12ch·35sc/plan-heal 8-8→committed to the outline.
> - **Task B (D-PLAN-CAST-ATTRS, resolved)** — `cast_attributes` maps role/traits/archetype/relationships/summary → the character kind's attr codes; `seed_entities` sends `attributes`+`attribute_actions`. Live-verified: glossary EAV persists role/personality/relationships/description. Drafting grounding now has DEPTH.
> - **Task C (the drive, in progress)** — the full grounded+healed 12-ch plan was generated + committed through the production endpoint; CH1 drafted (grounded) + chapter self-healed (`engine/self_heal.py`) as the prose sample. **NEXT:** draft + self-heal the remaining chapters (drive identically) for the full-story PO evaluation; optional: wire `self_heal` to its own endpoint (currently a script).
> - review-impl on the pipeline: 0 HIGH, 2 MED fixed (motif unrecognised-role drop; L1-once on degrade).
>
> **▶ Cheap quality stack — judge upgrade (SHIPPED 2026-07-01, `engine/self_heal.py`):** the bare judge
> was blind (0 findings on CH1 while real xưng-hô/canon errors stood; confabulated when prompted broad).
> Root cause = no canon grounding, not model size. POC'd 5 layers on the $0 local Gemma (data:
> `poc/io/poc_stack_out.json`), then implemented the validated subset — all **default-OFF ⇒ legacy
> byte-identical**: `canon` (grounds judge **and** satellite editor in a story bible + 2 false-positive
> guards), `vote_k`/`min_votes` (grounded judge ×K, must-quote folded in), `verify` (skeptical
> refute-or-confirm, fail-open), `prefilter` (dup-word + full-recall pronoun findings), `_snap_to_sentence`
> (edit whole sentences ⇒ no splice artifact). **Lesson:** voting alone does NOT kill *systematic*
> confab — only grounding suppresses it + verify refutes the leak. **CH1 re-healed:** 7 defects → near-zero,
> **x0.997**, incl. the canon contradiction (`từng dốc lòng che chở`→`luôn khinh miệt`) fixed by the grounded
> editor; remaining = 1 cosmetic + 1 borderline repetition left for the human/stronger gate. **Tests:**
> self_heal **21** (12 legacy + 9 new) green; full composition unit suite green. Result file:
> `poc/io/ch01_healed_cheapstack.txt`. Spec §"Cheap quality stack".
>   - **Full-book drive (CH1–12, book-level canon of all 9 cast) — `story-export-v2/` + `poc/io/heal_v2_summary.json`:**
>     **modern pronouns `ông/bà/ông ta/bà ta` = 0 real residuals book-wide** (deterministic prefilter is the
>     reliable workhorse); **no inflation anywhere** (x0.998–1.005). Two honest findings: (1) **verify is
>     stochastic + fail-toward-refute → occasionally drops a real finding** (CH01 `mẫu thân ngươi` regressed
>     vs the dedicated run; refuted=5/5 on CH03) — a precision/recall knob to tune (lower aggression, or vote
>     the verify), the human gate still matters most for the *semantic* findings. (2) **bug FIXED this commit:**
>     the dup-word collapser would flatten VALID Vietnamese reduplication (`chằm chằm`, `rắc rắc`) — now gated
>     OFF for `_REDUP_LANGS` (vi/zh/ja/ko/th/id/ms); only NFD-diacritic luck spared the v2 corpus, so the
>     exported v2 prose is unaffected.
>   - **(A) verify-recall + (B) canon-from-pipeline — SHIPPED 2026-07-01:**
>     **(A)** `run_self_heal(verify_k=…)` VOTES the verify (`_verify_vote`, majority-refute, tie→keep) so a
>     stochastic single refute can't drop a real finding. **(B)** new `engine/heal_canon.py`
>     (`render_canon` / `convention_for` / `canon_from_proposed`) builds the heal bible from the SAME
>     designed cast drafting grounds on; `PipelineResult.canon` now carries it (rendered in
>     `run_planning_pipeline`). **Live-validated on CH1** ($0 local, canon auto-rendered 2701 chars,
>     `verify_k=3`): the CH01 `mẫu thân ngươi` false-refute is **GONE** (residual=False; refuted 4→1), and
>     the rendered canon enabled a new canon catch (Hắc Sát Lão Nhân's role). Tests: self_heal 24 +
>     heal_canon 5.
>   - **⚠ CORRECTION (full-book re-drive, 2026-07-01) — the verify_k=3 "fix" was a lucky dedicated-run
>     sample.** Re-driving CH1–12 (`heal_all_v3.py` → `story-export-v3/` + `poc/io/heal_v3_summary.json`):
>     **pronouns ông/bà = 0 book-wide** (deterministic prefilter — rock-solid), **no inflation** (x0.998–1.007),
>     BUT **CH01 `mẫu thân ngươi` STILL residual** (present in both v2 and v3). Two real findings: (1) the
>     verify-vote was **mis-tuned** — majority-refute on a "default-REFUTED" prompt COMPOUNDS the refute-lean
>     (over-refuted: CH11 4/4, CH12 7/7). **Fixed:** `_verify_vote` now drops only on a **UNANIMOUS** refute
>     (keep if any vote confirms) — recall-biased, the human gate culls the rest. (2) **The verify model has a
>     genuine BLIND SPOT on `mẫu thân ngươi`** — it refutes 3/3 even grounded + recall-biased (0 confirms), so
>     NO vote threshold rescues it. **Conclusion (validates the M6 design):** the cheap stack is reliable on
>     CLOSED-CLASS (pronouns/dup, deterministic); semantic blind-spots are real + bounded → that residue is
>     exactly what the **human gate (M6 Polish) + stronger-model escalation** (deferred, story C7 #4) exist for.
>     Track **D-VERIFY-BLINDSPOT-ESCALATE**: wire the stronger-model gate for verify-refuted-but-real findings.
>   - **★ REDESIGN — DIRECT high-recall propose (PO diagnosis, 2026-07-01): the JUDGE pipeline was the bug,
>     not self-heal.** PO proved a BARE prompt on the same Gemma finds 7 splice-ready `{original,replacement,
>     explanation}` edits where our `judge→vote→verify→satellite` chain kept ~4 (verify default-REFUTED muted
>     real edits → v2≈v3). "The model detects + proposes correctly; only the judge is dumb." **Fix shipped:**
>     `propose_self_heal` now uses **`propose_edits_direct`** — ONE high-recall judge call that emits the
>     replacement inline (`build_direct_judge_messages`/`parse_direct_findings`), must-quote locate + dup-word
>     merge, **NO vote/verify** (the human gate IS the filter). Canon is CONTEXT, not a suppression guardrail.
>     **Live CH1:** 5 splice-ready edits incl. `mẫu thân ngươi`→`của ta` AND the canon contradiction
>     `dốc lòng che chở`→`khinh miệt` — the two cases the old pipeline never fixed — in 1 call (vs vote×5+verify×3).
>     Autonomous `run_self_heal` keeps the conservative `_compute_edits`. Tests: self_heal+worker 49 passed.
>   - **★ "Make the judge smart" — (1) surface rules + (2) comparative re-ranker (2026-07-01).** Smart-judge
>     POC pinned the root cause: the verifier wasn't dumb, it was **UNDERFED** — the rule was BURIED in an
>     800–2700-char bible. Fed the SAME rule concisely + with the example, EVEN the old skeptical judge
>     confirms `mẫu thân ngươi` 3/3 AND refutes the `lão` confab 3/3 (`poc/smart_judge_poc.py`). Two fixes:
>     **(1)** `heal_canon` — terser `render_canon` (description + relationship only, personality dropped) +
>     a NEGATIVE-example line in the convention (`hắn/y/lão/nàng/thị are VALID`) so the rule stands out + confabs
>     are pre-empted. **(2)** `_rerank_edit` — a COMPARATIVE re-ranker ("is the replacement better?", CoT,
>     default-APPLY, surfaced rules) that sets each semantic proposal's `EditProposal.recommended` (UI pre-check)
>     — it **RANKS, never vetoes** (every proposal still shown; recall preserved). `propose_edits_direct(rerank=)`,
>     worker op defaults rerank ON; FE pre-checks `recommended` (+ `rerank_reason`). Tests: self_heal+heal_canon+worker
>     57 + FE 142 vitest, tsc clean. **Live e2e CONFIRMED** (after a `docker compose up` recovered a cascading
>     Postgres→provider-registry/ai-gateway/composition drift): on v3-healed CH1 the direct+rerank returned 4
>     proposals — 3 PRE-CHECKED (`mẫu thân ngươi`→`ta` "violates third-person self-reference"; `che chở`→
>     `khinh miệt` "contradicts the canon Tô Yến never protected her"; dup-`từng`) + 1 UN-checked (a weak edit
>     "emotional weight is lost") — i.e. it RANKS, never vetoes, and each carries a cited reason. The exact case
>     the old verify pipeline refused 3/3 is now pre-checked with the rule cited.
>   - **Re-ranker made OPT-IN (default OFF) + 12-ch compare + no-op filter (2026-07-01).** Cost concern: rerank =
>     one extra LLM call PER semantic edit. **(A)** FE toggle "auto-tick (AI, costs more)", default OFF; worker/
>     endpoint default `rerank=False`; hook holds the toggle. **(B)** 12-ch compare (`poc/compare_rerank.py` +
>     `poc/io/compare_rerank_summary.json`): 55 splice-ready proposals, re-ranker approved 41 / declined 14 — and
>     **~all 14 declines are NO-OPs** (`replacement == original`; the direct auditor emits ~25% of these). The 41
>     approvals are real (pronouns, `mẫu thân ngươi`, canon: CH09 Lâm Tử Hàn/ma công, CH05 `Uyển nhi`-tone,
>     redundancy trims, CH04 bloat-delete x0.827). **(C) Cheap win found → shipped:** `propose_edits_direct` now
>     drops no-op edits (`after==located span`) in CODE (free) — so the human/re-ranker never sees the ~25% no-ops;
>     even without the paid re-ranker the human gets ~41 clean proposals not 55. Tests: self_heal 31 (+noop) + FE
>     PolishPanel 8 (+toggle).
>   - **★ Re-ranker made TYPE-ROUTED (RULE vs CRAFT) — a general judge is weak for novels (2026-07-01).**
>     PO: a general "is it better?" judge is shallow for fiction (quality isn't one axis). POC
>     (`poc/typerouted_compare.py` + `poc/io/typerouted_compare.log`) ran BOTH on all 50 proposals: the
>     **general judge APPLYed 47/50 (94%) — a rubber stamp that would AUTO-DELETE CH04's 8 passages**; the
>     type-routed auto-approved only **10 RULE** fixes (pronouns, `mẫu thân ngươi`, role/genre-term/typo) and
>     deferred **39 CRAFT** to the author + flagged 1 BAD. **Wired:** `_RERANK_SYSTEM` now classifies
>     **RULE** (objective convention/canon/typo/dup-word/grammar → auto-tick) vs **CRAFT** (rephrase/trim/
>     DELETE-passage/pacing/tone → author decides) vs **BAD**; `recommended = (verdict==RULE)`; degrade →
>     not-pre-checked (safe). Passage-deletion forced to CRAFT; RULE bucket widened to include typos (fixed
>     the POC's `món món` miss). Live CH1: all 5 = RULE, each citing the rule. Errs SAFE (defers borderline).
>     Tests: self_heal 31. **NEXT:** stronger-model escalate for the rare true blind spot.
>   - **M6 Polish — BE done (M6.1 engine + M6.2 wiring), 2026-07-01:**
>     **M6.1** (`c4db3792`) — `_compute_edits` shared step ⇒ `propose_self_heal` returns `EditProposal[]`
>     (id/tier deterministic|semantic/start/end/before/after) WITHOUT splicing; `apply_self_heal_edits(accepted_ids)`
>     splices the accepted subset; `run_self_heal` = propose+apply-all (byte-identical).
>     **M6.2** — worker op `self_heal_propose` (+ SUPPORTED_OPERATIONS + dispatch) + REST endpoint
>     `POST /v1/composition/projects/{id}/self-heal/propose` (resolve draft Tiptap→text + canon [override
>     or roster+convention] → propose → proposals; worker/inline like `plan_pipeline`). **Apply reuses the
>     existing `composition_write_prose`** — no new write tool / no confirm-token surgery. **Live-smoke:**
>     resolve path proven on the stack (get_draft `body` key + draft_version=2 → 7473-char prose; KAL roster
>     12 cast → 823-char canon); propose engine separately live-validated. Tests: self_heal 27 + worker_jobs
>     (dispatch + serialize).
>   - **M6.3 FE — DONE (Polish panel), 2026-07-01:** `PolishPanel` + `usePolishProposals` hook + `api.proposeSelfHeal`
>     / `applySelfHealEdits` (JS mirror of the engine splice); registered `polish` in the **Quality** group
>     (`workspace/types.ts` + `CompositionPanel` SubTab/stripIds/DockSlot, no-remount preserved); accept/reject
>     diff list (deterministic pre-checked, semantic unchecked); Apply → `ChapterEditorPage.handleApplyPolish`
>     replaces the doc via `setContent` (mirrors `handleTranslate`). Endpoint path fixed `/projects`→`/works`.
>     i18n `polish` label ×4 locales. Tests: tsc clean + **722 composition vitest** (incl. 6 new).
>     **NEXT:** re-drive CH1–12 with `verify_k=3` to refresh `story-export-v2/`.
>   - **Deferred D-POLISH-FE-BROWSER-SMOKE** (gate #4, needs FE image rebuild) — full click-through (open
>     chapter → Polish tab → Run → proposals → Apply) on a rebuilt FE image (running infra-frontend is the
>     old baked build). BE resolve-path + propose engine already live-smoked; FE↔BE call is typed + unit-tested.
>   - **/review-impl on M6 (2026-07-01):** **HIGH fixed** — stale cross-chapter proposals would Apply onto the
>     wrong chapter; fixed by `key={chapterId}` on PolishPanel (remount resets the snapshot). **MED fixed** —
>     FE `applySelfHealEdits` UTF-16-sliced Python code-point offsets; added a fail-safe (skip when
>     `slice≠before`). Tests: PolishPanel 7 + tsc clean. **Two MED deferred for a PO decision (snapshot
>     tradeoffs of whole-doc replace):** **D-POLISH-OCC** — Apply uses the propose-time `source_text` +
>     ignores `draft_version`, so edits made after Run (incl. unsaved buffer) are lost → compare version &
>     warn, or apply spans to the live doc. **D-POLISH-MARKS** — Apply rebuilds plain paragraphs ⇒ strips
>     inline marks (AI-provenance/bold) chapter-wide (same shape as handleTranslate). Plus LOW: no router
>     test for the propose endpoint.
>   - **Deferred D-SELFHEAL-CANON-ATTRS** (gate #2, structural) — heal canon is currently convention +
>     roster NAMES (KAL roster is names-only); rich per-character canon (descriptions → catches canon
>     contradictions like Tô Yến "che chở") needs a glossary "full cast WITH attributes" read. The
>     convention already grounds the dominant xưng-hô class; attribute-canon is the enrichment follow-up.
>
> **▶ Broader evaluation pass — DONE 2026-07-01 (`tests/e2e/eval_compose_quality.py` + `docs/specs/2026-06-30-editor-compose-overhaul/eval/2026-07-01-quality-eval.md`).** Drove all 3 surfaces × 12 real chapters + book coverage. Verdict: **critic** (10/10 violations real, 0 FP) + **book coverage** (v2, after windowing) are trustworthy; **self-heal** good (49 props, 0 no-ops) but hides its objective wins; the **per-chapter "dropped promises" is a false-positive machine** (30 flagged vs 0 abandoned book-wide — v1 audit mislabels still-*progressing* threads as dropped; the LLM's own "chưa/not-yet" annotations prove it). Ranked backlog below.
>
> **▶ Deferred (this track):**
> - ~~**D-QUALITY-DROPPED-FP**~~ — **RESOLVED 2026-07-01 (backlog #1).** The per-chapter Quality Report promise section is reframed from the misleading "dropped promises" alarm to **"threads RAISED in this chapter"** (informational) + any RESOLVED here; the false-positive "dropped" verdict is gone, and the book-level coverage owns paid/abandoned. `quality_report` now returns `{critic, threads:{raised, resolved, raised_count, resolved_count}}` (was `{critic, promises:{...dropped...}}`); `_chapter_threads` reshapes the audit; FE `QualityThreads` + `QualityReportSection` render "N thread(s) raised" (neutral) + "M paid off here" (green). E2E-confirmed (`raised` present, `dropped` absent). Tests: quality_report + worker + FE QualityReportSection updated green.
> - ~~**D-QUALITY-HONORIFIC-PRECHECK**~~ — **RESOLVED 2026-07-01 (backlog #2).** Data-driven: re-ran the eval with rerank=ON — the LLM re-ranker only pre-checked **8/15** honorific fixes (misclassifies ~half as CRAFT) at the cost of 49 extra calls. So "default rerank ON" was the WRONG fix. Instead: `self_heal._is_convention_fix(type)` code-detects the objective xưng-hô/address/typo class (a closed convention the auditor labels) and pre-checks it **deterministically + FREE** — even with rerank OFF, and it short-circuits the re-ranker when ON. E2E-confirmed on real ch1: 4/4 ADDRESS/HONORIFIC pre-checked, LOGIC/REPEATED (CRAFT) left unchecked. Tests: self_heal 34 (+3: _is_convention_fix, precheck-without/with-rerank).
> - ~~**D-QUALITY-CRITIC-HEAL-LINK**~~ — **RESOLVED 2026-07-01 (backlog #3).** The critic's canon violations ≈ self-heal's honorific edits (same issue, shown as diagnostic AND edit). `QualityReportSection` now takes the current `proposals` and marks each critic violation whose `span` overlaps a proposal's `before` with a **"fix proposed ↓"** badge (`_hasProposedFix`, normalized substring-either-way, min-len guard) — so the author sees "this violation already has a fix below" instead of double-counting. FE-only; PolishPanel passes `p.proposals`. Tests: QualityReportSection +2 (match / no-match); FE composition 737.
> - **D-QUALITY-COVERAGE-VARIANCE — LOW, DEFERRED (backlog #5, conscious).** Book-coverage paid↔progressing flips run-to-run (LM Studio/Gemma isn't fully deterministic even at temp 0). Stabilizing = a multi-sample majority vote per window = 3× the LLM cost for marginal gain on an ADVISORY signal. Gate #4 — fix only if the variance ever misleads a real decision. Trigger: a user reports a promise's verdict flipping confusingly.
> - **D-QUALITY-CH4-REGEN — LOW, NOT-A-CODE-FIX (backlog #4, conscious).** ch4's draft has a repetition LOOP; both critic (coh=2, "looping") and self-heal (10 "repeated") correctly flagged it — i.e. the TOOLS WORK. The resolution is regenerating ch4's DATA (a generation op), not a code change; near-zero product value on one POC chapter. Won't-fix as code; regenerate the draft opportunistically if the POC book is re-driven.
> - **D-QUALITY-MOTIF-ROLLUP** — surface `motif_conformance` beat-not-realized per chapter in the Quality Report (needs per-outline-node motif bindings aggregated across scenes). Gate #2 (structural). Target: a Q-follow-on to the Quality Report track.
> - ~~**D-QUALITY-COVERAGE-CHUNK**~~ — **RESOLVED 2026-07-01** (found by E2E → fixed → E2E-confirmed, the full loop). `build_promise_coverage` now WINDOWS the book (`_split_windows`, 12K-char paragraph-aligned) and scores each window against the same fixed promise set, MERGING per-promise by strongest engagement (paid > progressing > abandoned > absent); all windows failing → honest `coverage_unavailable`. **E2E-confirmed on the real 12-ch book:** was `coverage_unavailable` + all-10-absent → now `error:None`, 9 promises all **"progressing"** (a sensible read of a setup-heavy opening: promises live, none resolved/dropped yet). Tests: quality_report 12 (+3 windowing) + an E2E regression guard (`error != coverage_unavailable`).
>
> **▶ E2E harness — SHIPPED 2026-07-01 (`9687f6910`), replaces live-smoke/POC (per user).** `tests/e2e/quality_harness.py` + `tests/e2e/test_compose_quality_e2e.py`: drives the REAL `/v1/composition/*` quality endpoints through the gateway as the claude-test account, discovering a real target black-box (books → work → a DRAFTED chapter → chat model) + job-poll. 4 E2E green. First run surfaced (a) a STALE-IMAGE trap (running composition image predated the endpoints → 404; rebuilt composition-service+worker) and (b) the coverage-chunk bug above — both invisible to a crafted-input smoke. **Methodology (LOCKED, see memory `prefer-e2e-and-evaluation-over-live-smoke-poc`):** validate compose-quality via real E2E + evaluation analysis over the real book, not hand-fed smoke. **NEXT:** either fix D-QUALITY-COVERAGE-CHUNK (make Q3 work on real books) or run a broader evaluation pass across all 3 surfaces × 12 chapters to build the improvement backlog.
> - **D-ARC-TEMPLATE-CRUD-GUI / D-MOTIF-LIBRARY-CRUD-GUI** — auto arc-conformance + the motif-library judges are gated on GUI-managed artifacts (arc templates only from reference-import/authored; no `work→arc_template` link). Making them useful needs whole CRUD GUIs — big features. Gate #2 (structural). Target: discuss + plan as their own features.
> - **Recently cleared:** ~~D-QUALITY-ARC-LEVEL~~ — SHIPPED as Q3 (book-level promise coverage, 2026-07-01).
> - **D-THREAD-MOTIF-COMBINED** — `thread_state` + `motifs_enabled` together: typed-state threading is skipped on the motif path (motif `prev_effects` carry used; warned, not silent). Gate #2 (needs interleaving the motif sequential select with the threaded invent loop). Target: when motifs + threading are both wanted in one run.
> - **Book-service universal formatter** (slice 01: `tiptap.go`/`server.go` markdown→Tiptap) — built, **uncommitted**, awaiting the PO's read-mode test before a separate commit.
> - GUI milestones M0–M5 — paused behind the synthesis track (output quality first).

> ---

# ▶▶ (merged from origin/main 2026-06-30) **Temporal Knowledge — COMPLETE (foundation + close_fact + full fanout X1–X7 + FE temporal surfaces + REAL per-episode translation); branch ready for review/merge** · branch `feat/temporal-knowledge-architecture` · HEAD `pending` · 2026-06-30

> **▶ PER-EPISODE TRANSLATION — now a REAL feature (this run), not a degrade.** The §7.6 surface translates the
> entity's as-of folded canonical into the reader's display language, on-demand + cached immutable per (content,
> language) — mirror of KG-TL M3. NEW: glossary migration **0050** `canonical_snapshot_translations` (single-flight
> claim + background fill), `translation_client.go` (→ translation-service `/internal/translation/translate-text`,
> BYOK via provider-registry — no LLM in glossary), `canonical_translation_handler.go`; KAL read
> `GET …/canonical-translation?lang=&as_of=` + contract `CanonicalTranslation`; FE `useCanonicalTranslation` (polls
> while `translating`) + rewritten `EpisodeTranslationPanel` (language selector reuses the shared per-book
> `useGlossaryDisplayLanguage` → lockstep with the glossary browser; picks original ⇒ shows original, no LLM).
> **Verified:** glossary go tests (incl. state-machine integration on the real `loreweave_glossary` DB) · KAL jest
> 19 · FE 45 + tsc clean · both INV-KAL lints + provider-gate PASS · **live-smoke** FE→BFF→KAL→glossary→translation
> →provider-registry→lm_studio: zh canonical → `ready/translated/cached` real EN translation, single-flight = 1 call.
> Plan: `docs/plans/2026-06-30-per-episode-translation-surface.md`.
> **/review-impl pass (1 MED + 2 LOW, all fixed):** a per-user config error (no_model/no_user) no longer poisons the
> shared book-tier row / exhausts the retry budget — it's caller-specific + costs no LLM, so a configured viewer
> always heals it (provider/quota failures still respect `foldRetryBudget`); success-UPDATE got the `status='pending'`
> guard; added a heal-path integration test. **User-mode e2e through the BFF** (real login JWT → KAL dual-auth + book
> grant): owned book → `ready` real EN translation, no-auth → 401, non-granted book → 403.

> **▶▶ ENTIRE EFFORT COMPLETE — the Incremental Temporal Knowledge Architecture is built, verified, and
> committed end-to-end (F0–F4 foundation + close_fact + X1–X7 fanout + X6 FE). The branch is production-ready
> for review/merge.**
> - **Foundation** (bi-temporal `entity_facts` SSOT, `maintain_chain` single writer, episodes, fold loop, KG
>   ordinal valid-time, KAL service) — hardened across **4 /review-impl passes** (4 HIGH + 6 MED + LOWs fixed, e2e green).
> - **close_fact** — pinned valid-time close (0049 pin-aware maintain_chain); reviewed + live-smoked.
> - **Fanout:** X1 composition / X2 lore-enrichment / X5 translation → KAL (consumers read bi-temporal knowledge
>   through the KAL); X3 wiki / X4 chat verified no-ops; **X7 — BOTH INV-KAL lints ENFORCED** (table-read +
>   HTTP-surface); cross-service smoke green.
> - **X6 FE:** KAL **dual-auth** (JWT + book grant-check, anti-spoof) + BFF `/v1/kal` route (reviewed + live-verified
>   200/403/401); **6 temporal surfaces** (canonical card, time slider, change timeline, diff, retrieval,
>   per-episode translation) — 45 tests, tsc clean, real-KAL shapes validated, mounted in the entity panel's
>   "Temporal" tab.
> - **Honest limitations (not bugs, future enhancements):** per-episode translation is now REAL (built this run —
>   see the block above); KG `as_of` honored (F3 landed). A full browser/Playwright smoke of the Temporal tab is the
>   one remaining nice-to-have (shapes + the FE→BFF→KAL path + 45 component tests + the HTTP-chain live-smoke are verified).



> **▶ FOUNDATION COMPLETE — all verified (real DB / build / tests):** F0 KAL contract · F1a-h substrate
> (entity_facts/maintain_chain/episodes/cold-start) · F1d producer (facts flow from extraction, idempotent) ·
> F1f fact-chain merge + split · F1g bi-temporal name/aliases + as-of-name (0048 reconcile) · F2 canonical
> versioned-cache + the **fold loop** (glossary dirty/fetch/snapshot/degrade + the translation fold worker, LLM via
> provider-registry) · F3 KG ordinal valid-time + in-story dates · F4 KAL NestJS service (auth-guarded) with the full
> read surface (facts/timeline/attr-values/roster/canonical) + write surface (episode/append/close/retract/merge/
> resolve/split/fold) + the INV-KAL table-read lint (pre-commit). Three /review-impl passes, all HIGH/MED fixed
> (security: KAL inbound auth; tenancy: fact book-scoping; correctness: same-ordinal supersede, merge attr-set).
>
> **▶ PRE-FANOUT HARDENING REVIEW (this run) — 5 parallel adversarial reviewers over the whole foundation; 4 HIGH +
> 6 MED + LOWs found and ALL FIXED (15 files, 4 services), cross-service e2e GREEN on the rebuilt glossary image:**
> - HIGH: split cross-book leak (`internalSplitEntity` had no `entityInBook(source)` guard) · KG same-ordinal
>   `[base,base)` empty-interval data loss (4 cypher blocks → strictly-greater, mirrors PG core) · KAL `fold` write
>   unroutable → built the `internalTriggerFold` glossary backing + route (live-smoked HTTP 200) · KAL `facts/close`
>   doubled path. · MED: fold fingerprint lexical-vs-numeric max **livelock** (now numeric, live fingerprint `1638578`) ·
>   NULL-unsafe staleness probe · degrade-read book-scope + `refreshEAVProjection` hardcoded `'zh'` · 0048 re-run cold-start
>   scope · KAL downstream abort-signal + non-JSON-2xx guard + strict array coercion + NaN guard. · LOWs: fold worker
>   model_ref skip / cancelled≠backoff / prompt-injection delimiting. (The summary's `_cast_roster` drain bug = phantom.)
> - Verify: Go build/vet + 12 temporal Go tests (real DB) · jest 5/5 · fold pytest 3/3 · KG 15/15. E2E: KAL→glossary
>   forwards incl. the new fold write route + 401 auth guard, as-of reads, degrade-to-canon — all green.
> - **close_fact — DONE** `1e80637e` (PO: build-now): the frozen KAL close verb is now backed. Migration 0049 adds
>   `valid_to_pinned` + a pin-aware maintain_chain (CREATE OR REPLACE) — a manual close is an authored INPUT the single
>   deriver RESPECTS, never a competing deriver (the LOCKED §12.3.3 invariant holds). closeFact core + internalCloseFact
>   (book-scoped, validates in-book + valid_to > valid_from). Live-smoked: as-of 30 present, as-of 60 absent, 422/404 guards.
> - **/review-impl on close_fact — DONE** `fb3a34ed` (PO: commit-then-review): 3 MED found + fixed — overlap guard
>   (close past a successor → 422, was a double-value hole), split now PRESERVES the pin (`valid_to_ordinal`+`valid_to_pinned`
>   copied), and TestFactsHTTP regression-locks close half-open + overlap-422 + cross-book-404.
>
> **▶ FOUNDATION FULLY HARDENED + COMPLETE (incl. close_fact).**
>
> **▶ BACKEND FANOUT COMPLETE (X1–X5, X7) — consumers now read bi-temporal knowledge through the KAL; both
> INV-KAL lints ENFORCED:**
> - **X1 composition** `ae4016ea` — `KalClient.roster` DRAINS `next_cursor` (fixes the D4 truncation-at-100 bug);
>   `_cast_roster` migrated; dead `list_entities` removed. 1181 tests green.
> - **X2 lore-enrichment** `9af1c255` — `KalClient` (roster drain + facts/canonical/search); full-book cast from
>   the drained roster. Residual: `kind`/`short_description` supplemented from the authored entity-list (catalog,
>   not bi-temporal — out of INV-KAL scope, like the table-read gate's `glossary_entities` exemption).
> - **X5 translation** `0471b48c` — `KalClient` (get_facts/get_canonical) with **as-of-N inject** (threads
>   `chapter_sort_order`) + **immutable-once cache** (keyed on chapter content-hash + as-of). Default (no
>   `KNOWLEDGE_GATEWAY_URL`) byte-identical to today.
> - **X3 wiki / X4 chat — verified NO-OPs:** wiki is owner-side (glossary, lint-exempt); chat's entity reads are
>   MCP tools federated by name through ai-gateway (MCP-first invariant — must stay that way). No dead code added.
> - **X7** `7fb6e692` — built the INV-KAL **HTTP-surface lint** (was DEFERRED `D-KAL-HTTP-SURFACE-LINT`); BOTH
>   halves now ENFORCED in pre-commit. Both lints PASS full-scan (zero direct bi-temporal knowledge reads in consumers).
> - **KAL in docker-compose** `b695ab7d` — built + healthy in-stack; cross-service smoke: composition container →
>   `knowledge-gateway:3000` roster returns the contract shape.
>
> **▶ X6a/b — FE→KAL bridge DONE + live-verified** `bf772913` (PO: dual-auth chosen):
> - **KAL dual-auth** (read surface; writes stay internal-only): SERVICE mode (X-Internal-Token) OR USER mode —
>   validate the platform HS256 Bearer JWT (Node crypto, no dep; rejects alg=none/wrong-sig/expired, timing-safe) +
>   GRANT-CHECK the book against book-service (`/internal/books/{id}/access`) since the BFF is a dumb proxy. X-User-Id
>   PINNED from the JWT sub (anti-spoof). Fail-closed + 5s grant timeout + bounded positive-grant cache.
> - **BFF** `/v1/kal` → knowledge-gateway (dumb JWT passthrough, 503-on-down). KAL compose env: JWT_SECRET + BOOK_SERVICE_URL.
> - **Reviewed** (/review-impl: MED grant-timeout + LOW cache-bound fixed) + **live-smoked** the full FE path with a
>   REAL login JWT: owned-book→200, non-granted→403, no-auth/garbage→401, service-mode→200. KAL jest 17 green.
>
> **▶ ONLY REMAINING: X6c — the net-new FE TEMPORAL SURFACES (React, this branch):** canonical card (as-of folded
> canonical), time/version slider (scrub chapter ordinal), change timeline w/ citations, diff view (state between two
> ordinals), retrieval-not-scroll, per-episode translation (§7). Reads go through the BFF `/v1/kal/*` (now live).
>
> **▶ REMAINING = the consumer/FE FANOUT (parallel worktree agents, the locked strategy):**
> X1 composition→KAL (+fix `_cast_roster` cursor drain) · X2 lore-enrichment→KAL · X3 wiki→KAL (kill direct-EAV) ·
> X4 chat→KAL · X5 translation→KAL (as-of inject + immutable-once cache) · X6 FE temporal surfaces (canonical card,
> time slider, change timeline, diff, retrieval) + migrate FE reads to KAL · X7 flip BOTH INV-KAL lints (table-read +
> the new HTTP-surface lint) to ENFORCING. Each binds ONLY to the frozen `kal.v1.yaml` → provably disjoint, parallel-safe.

> **▶ Shipped this run (production-ready, all verified on real DB / build / tests):**
> - **F1d (producer)** `d5662b64` — facts FLOW from extraction: translation worker passes `chapter_ordinal`,
>   glossary writeback ingests the episode + opens append-only facts per written attr, idempotent. (`TestBulkExtract_EmitsTemporalFacts`)
> - **F4-live core** `c13d11bb` — glossary `/internal/facts/*`: GET facts/timeline/attr-values (bounded, as-of) + POST
>   episode/append/retract; KAL paths aligned. (`TestFactsHTTP`: append supersedes, retract restitches over the router)
> - **F4-writes** `41070247` — internal merge/resolve-entity/split routes + KAL wiring (resolve-or-create idempotent).
> - **in-story dates** `a5d0d80e` (merged) — `event_date_iso` additive valid-time on KG facts/relations (19 tests; chapter-ordinal stays primary).
> - **prod bugfix** `94caea91` — world-timeline `NameError: q` (pre-existing crash) fixed.
>
> **▶ Remaining foundation (then fanout):**
> - **F2-app — fold handler:** dirty queue + canonical_snapshot write + lazy rebuild-on-read + ordinal-bucketed re-ground
>   (B1) + compare-and-clear + backoff. LLM via provider-registry (likely a worker/knowledge pass like #26/#7 summarize).
>   Makes `get_canonical` return the FOLDED canonical (today it serves canon-content). Adds the KAL `fold` route.
> - **F1g — bi-temporal names:** name as `fact_kind='name'` (single) + aliases as `'alias'` (multi); as-of-name; resolver
>   matches the across-time alias set. RECONCILE: migration 0048 converts the cold-start/F1d `attribute` name/aliases
>   facts → name/alias kind, and `refreshEAVProjection` + the D5 check must project name-kind facts to the name EAV.
> - then **fanout X1–X7** (parallel worktree agents per the locked strategy).


> **What this branch is:** implementing the Incremental Temporal Knowledge Architecture
> ([spec](../specs/2026-06-29-incremental-temporal-knowledge-architecture.md) §12/§12.7.8 govern;
> [plan](../plans/2026-06-30-temporal-knowledge-architecture-impl.md)). Append-only bi-temporal facts as the
> sole SSOT (INV-FACTS §12.0); everything else a rebuildable cache. Execution = **serial foundation → parallel
> fanout** (user-directed: build foundation serially, checkpoint, then fan out consumer migrations).
>
> **▶ Shipped this session — the SSOT substrate spine, all real-DB verified on `loreweave_glossary`:**
> - **F0** `fc4c9a80` — froze the **KAL v1 contract** (`contracts/api/knowledge-gateway/kal.v1.yaml`), the keystone
>   every consumer binds to; `knowledge-gateway: missing` row in `language-rule.yaml` (→ typescript at F4 scaffold).
> - **F1a** `ae6f17fd` — `0044` **entity_facts + episodes** bi-temporal SSOT schema (content-addressed natural key,
>   `valid_to_eff` INT64_MAX null-sink, `coverage_xid` xid8, merge_journal fact/episode-move cols). Idempotent 2×.
> - **F1b** `728efaf9` — `0045` **maintain_chain** the single `valid_to` writer (§12.3.3). Verified all 3 scenarios:
>   out-of-order backfill (A2), retract restitch (A3), oscillation (A4).
> - **F1c** `8a2b8e6d` — **fact core** Go (`facts.go`): appendFact (idempotent NK), retractFacts (restitch),
>   ingestEpisode, refreshEAVProjection (repair/cutover), per-(entity,attr) chain lock. `TestFactCore` PASSES (real DB).
> - **F1h** `8eb419f9` — `0046` **cold-start seed**: 22,056 facts seeded from live EAV; **projection==flat_eav 0 mismatches** (§12.5.4/D5).
> - **F2 schema** `fdf6c0d8` — `0047` **canonical versioned-cache** tables (canonical_snapshot + canonical_fold_state), §12.1.
>
> ⚠ Migrations **0044–0047 are applied to the running dev `loreweave_glossary`** (by F1c's `RunChain`); a fresh stack
> picks them up from the ledger on boot.
>
> **▶ PARALLEL track (background agent, worktree):** **F3 — KG ordinal valid-time unify** in `knowledge-service`
> (Python/Neo4j) — substrate-independent from glossary. Ordinal valid-time unified with `from_order`, ordinal-aware
> close (A2 on the KG side), extraction-driven invalidate/retract, quote-on-citation, per-entity ordinal snapshot.
> **Merge its worktree branch at the integration node before F4.**
>
> **▶ F3 — KG ordinal valid-time unify — MERGED `f2d5ca3e`** (was a parallel worktree agent); 24 F3 unit tests
> re-verified green post-merge. All under `services/knowledge-service/` (disjoint from glossary).
>
> **▶ F1f — fact-chain merge + split (DONE):** `ecc7e587` **merge** (§12.4.1, `mergeFactChains`/`revertFactChains`,
> journal `repointed_fact_ids`+`invalidated_fact_ids`, same-ordinal tiebreak, chain locks both sides) +
> `f52e50f7` **split** (§12.4.2, `splitFactsByEpisode` re-attribute-by-provenance, originals reason='split').
> `TestMergeFactChains`/`TestSplitFactsByEpisode` green; existing Merge/Revert/Dedup suites green (no regression).
>
> **▶ F4 — KAL gateway service + INV-KAL lint (DONE, structure):**
> - `2ab5f710` **KAL NestJS service** (`services/knowledge-gateway`) implementing `kal.v1.yaml`: config/main/health +
>   `KalReadController` (get_canonical/get_facts/timeline/list_attr_values/roster/search/neighborhood/retrieve, each with
>   per-substrate `temporal_capability`, KG `as_of` dropped when `temporal_unsupported`) + `KalWriteController`
>   (append/close/retract/merge/split/fold/ingest_episode/resolve_entity forwarding to glossary `/internal/facts/*`).
>   **Verified: npm install + nest build clean; boots + serves /health + /health/ready (kgTemporal=ordinal_valid_time),
>   16 routes mapped.** `language-rule.yaml` `missing`→`typescript`; lint PASS.
> - `434894d8` **INV-KAL table-read lint** (`scripts/knowledge-access-gate.py`, wired into `.githooks/pre-commit`): no
>   consumer reads the glossary EAV / Neo4j directly. Full-scan PASS.
>
> **▶ NEXT — F4-FOLLOW-ON + remaining foundation, then fanout:**
> 1. **F4-follow-on (live writes):** add the glossary **`/internal/facts/*` HTTP routes** (Go handlers wrapping the F1c/F1f
>    fact core — appendFact/retract/mergeFactChains/splitFactsByEpisode/fold) so the KAL write verbs hit a real target;
>    then a **cross-service live-smoke** (KAL → glossary fact route → DB) + verify the read endpoints' downstream path
>    mapping against the actual glossary/KG routes. (KAL reads/writes build + the service boots; full delegation is the
>    cross-service smoke, currently unverified end-to-end.)
> 2. **F2 app** — the fold handler: lazy rebuild-on-read + ordinal-bucketed re-ground (B1) + compare-and-clear + backoff
>    (needs a provider-registry LLM call). Enhances `get_canonical` behind the frozen contract.
> 3. **F1g** — bi-temporal name/aliases (§12.4.3) + as-of-name. **Value partly gated on F1d** (deferred writeback wiring);
>    reconciles `D-TK-F1G-NAME-RECONCILE`.
> 4. **CHECKPOINT** → then parallel **fanout** X1–X7 (consumer migrations onto the KAL, FE temporal surfaces).
>
> **▶ SCOPE (locked 2026-06-30): this branch is the PRODUCTION-READY refactor — NO deferrals.** Everything below is
> in-branch work to COMPLETE (the repo adopts the KAL immediately after merge, so nothing core may be stubbed/parked).
> Includes the full consumer + FE fanout (X1–X7) and both INV-KAL lints flipped to ENFORCING. The items that were
> "deferred" are now must-complete work:
> - **F1d — writeback Path-A emission (must complete):** wire fact emission into the glossary writeback; extend the
>   bulk-extract request with `chapter_ordinal` and update the translation-service extraction caller to pass it.
> - **F4-live — glossary `/internal/facts/*` HTTP routes** wrapping the Go fact core (append/close/retract/merge/split/
>   fold/ingest_episode/resolve_entity) so the KAL writes are real; cross-service KAL→glossary→DB live-smoke.
> - **F2-app — fold handler:** lazy rebuild-on-read + ordinal-bucketed re-ground (B1) + compare-and-clear + backoff (LLM via provider-registry).
> - **F1g — bi-temporal name/aliases** (§12.4.3) + as-of-name + RECONCILE the cold-start name/aliases representation
>   (supersede the cold-start `attribute` name/alias facts → `name`/`alias` kind facts; the old `D-TK-F1G-NAME-RECONCILE`).
> - **In-story dates (must build — user pulled into v1):** detected in-story time (`event_date_iso`) as an additional KG
>   valid-time source (spec §9 dec-3). Knowledge-service.
> - **Fanout X1–X7 (in-branch):** migrate composition, chat, lore-enrichment, translation, wiki, FE to read/write through
>   the KAL; kill every direct EAV/KG read; flip BOTH INV-KAL lints (table-read + HTTP-surface) to ENFORCING.
>
> **▶ /review-impl (2026-06-30) — 7 findings, ALL FIXED (no HIGH):** MED-1 same-ordinal single-valued conflict → last-write-wins supersede + deterministic projection tiebreak (`TestFactSameOrdinalConflict`); MED-2 unenforced chain-lock → strengthened contract doc + `TestFactChainLockSerializes` (same-chain blocks, disjoint free); LOW-2 cold-start ordinal `0→-1` (chapter_index is 0-based); LOW-5 targeted `ON CONFLICT` on the natural-key expression index; LOW-3 `refreshEAVProjection` attr_def_id-coupling doc; LOW-4 `reconcileEpisode` F1d-obligation doc + now exercised; LOW-1 → `D-TK-F1G-NAME-RECONCILE` above. All 3 facts tests green on real DB; cold-start re-verified `projection==flat_eav` 0 mismatches with the `-1` sentinel.

---

# ▶▶ (prior) **Motif book-collaboration tier (model B) + shared-graph links + MCP edit SHIPPED** · branch `feat/narrative-pattern-library` · HEAD `8c4c45c2`+ · 2026-06-29

> **▶ MERGE 2026-06-29:** `origin/main` merged into this branch (179 commits — the **public-MCP gateway + lazy tool-loading** track, critical-UX fixes, glossary/knowledge/campaign work). Conflicts resolved (composition `actions.py` confirm = JWT-identity ∪ public-MCP spend-attribution; engine `plan.py`/`stitch.py` signatures = both; studio panels = `canonview` ∪ `motifs`/`conformance`; gateway test `mcpPublicGatewayUrl`). The motif MCP tools are exposed to the public-MCP gateway: `find_tools` (lazy discovery) picks them up dynamically from the federation catalog, and they are classified in the edge `TOOL_POLICY` allowlist (commit `2aa65765`). Below is this branch's motif work; the merged-in main tracks + all prior history are archived (see the pointer at the bottom).

> **▶ Follow-up this session (2nd commit) — both model-B deferrals CLOSED:** `D-MOTIF-LINK-SHARED-TIER` (shared-graph link editing — guard rewrite + repo/MCP book_id paths) and `D-MOTIF-MCP-PATCH-SHARED` (the `composition_motif_patch` MCP edit tool). Details in the "Deferred … BOTH NOW CLEARED" block below. 150 motif unit tests + 38 motif DB integration tests green; migration re-smoked idempotent on real `loreweave_composition`; provider-gate clean.

> **▶ Shipped this session — the two NEW future-feature rows (now CLOSED):**
> - **`D-MOTIF-ADOPT-BOOK-COLLAB-TIER` (model B) — a THIRD tenancy tier (the book SHARED library).** Spec: [docs/specs/2026-06-29-motif-book-collab-tier.md](../specs/2026-06-29-motif-book-collab-tier.md). A `motif.book_shared=true` row is owned by its creator (attribution) but VISIBLE to the book's VIEW-grantees and WRITABLE by its EDIT-grantees — access is the **book grant resolved at the caller**, never row ownership. User decisions (this session): **context-scoped reads** (per-book gate, no global "all my books"), **any-EDIT-grantee writes** (edit + archive), **adopt + create + mine** all produce shared rows. The base read predicate is **UNCHANGED** (a foreign shared row is fail-closed invisible to get_visible/list_for_caller/catalog/get_by_codes); shared rows surface ONLY through the gated book-context methods. Touch-points: schema (`book_shared` col + `motif_book_shared_shape` CHECK [shared ⇒ book+owner+private, the public-catalog-orthogonality guard] + per-book `uq_motif_book_shared` + re-narrowed `uq_motif_user_book WHERE …AND NOT book_shared`); repo (`clone/adopt/create/_clone_with_code` thread book_shared; new `list_in_book/get_in_book/patch_shared/archive_shared`; adopt locks per-BOOK + dedups per-(book,code) for the shared tier); MCP (`adopt target=book_shared`, `create target=book_shared`, `mine promote_target=book_shared`, `archive book_id=`, new `composition_motif_book_list`); confirm dispatch (`book_shared` rides the payload, re-gated EDIT); FE (3rd adopt target "Share with collaborators" + `Shared` badge).
> - **`D-MOTIF-HTTP-ADOPT-BOOK` — HTTP parity.** `POST /motifs/{id}/adopt` now takes `target=user|book|book_shared`+`book_id`, **EDIT-gated before the clone** (no softer than MCP); `GET /motifs/book/{id}` (VIEW-gated list); `PATCH`/`DELETE …?book_id=` (EDIT-gated shared edit/archive, visibility-flip refused 400). A book-shared pattern root does NOT auto-adopt its members (the half-shared-pattern guard).
>
> **VERIFY:** 90 motif unit tests + new repo/mcp/router cases green; **integration (real PG)**: new `test_motif_book_shared_db.py` (shape CHECK, per-book dedup, list/get scoping, any-grantee patch/archive) + 32 existing motif DB tests pass on a throwaway DB; **migration live-smoked idempotent on the REAL existing model-A `loreweave_composition`** (added book_shared col + CHECK + uq_motif_book_shared + re-narrowed uq_motif_user_book; two runs, no error). FE 152 motif tests + tsc + provider-gate clean. **`/review-impl` adversarial tenancy review: 0 HIGH / 0 MED** — all 9 read/write/leak/confirm/dedup checks PASS with file:line evidence; 3 LOW/COSMETIC notes (deferred below).
>
> **▶ Deferred (from the model-B review — BOTH NOW CLEARED 2026-06-29):**
> - ✅ **`D-MOTIF-LINK-SHARED-TIER`** — **CLEARED:** the `motif_link_guard` was rewritten (NULL-safe) to a precise 3-arm same-tier rule — both SYSTEM, or both the SAME book's SHARED tier (owners may differ — the point of a collaborator graph), or both the SAME user's PRIVATE tier. A shared↔private/system/cross-book link is rejected at the DB. Repo `list_links/create_link/delete_link` gained a `book_id` path (anchor via get_in_book; both endpoints must be `book_shared AND book_id`); MCP link tools take `book_id` (VIEW for list, EDIT for create/delete). Live-PG tested (same-book allowed, 3 cross-tier rejections, 3rd-grantee list/delete) + migration re-smoked idempotent on real `loreweave_composition`. **Caught+fixed a SQL three-valued-logic bug**: `owner = owner` with a NULL operand yields NULL so `IF NOT NULL` wouldn't fire (a user→system link would have slipped) — every arm is now NULL-guarded.
> - ✅ **`D-MOTIF-MCP-PATCH-SHARED`** — **CLEARED:** new `composition_motif_patch` MCP tool (Tier-A) — owner-keyed by default, or a SHARED-tier edit with `book_id` (EDIT-gated → patch_shared). Optimistic-lock `expected_version` (stale → applied_conflict), visibility/publish deliberately NOT editable (separate flow), honest undo that patches changed fields back to prior values. Owner path denies a foreign row before any write; shared path confirms the row is shared-in-this-book.
>
> ---
>
> # ▶▶ (prior) **Motif library COMPLETE — audit 7/7 closed (WI-1…WI-6)** · HEAD `04bab448`+ · 2026-06-29

> **What this branch is:** the narrative-pattern (motif/arc) library — Tier-W cost-gated MCP flows for mining, conformance, adopt, and 3-way publish-sync, fronted by the FE→MCP-tool bridge. The feature body landed across prior sessions; this session closed the **completeness-audit tail** AND shipped **WI-5 per-book adopt**.
>
> **▶ Shipped this session (all green — 1083+ backend unit + 151 FE motif tests, tsc + provider-gate clean):**
> - **Audit tail (committed `f1157b25`…`b8f0ddb3`):** BYOK model_ref threading through `motif_mine`/`arc_import`; the **tag-beats LLM extractor** (knowledge `POST /internal/extraction/tag-beats` → composition mine pre-pass; cross-tenant injection neutralized); **WI-3 arc semantic retrieve** (`composition_arc_suggest`); **WI-1/WI-2/WI-4 FE** (mine panel, full editor, publish-sync); `/review-impl` fixes (arc back-fill scoped to own/system; editor edit-loss). Completeness audit: [`docs/reports/2026-06-29-motif-completeness-audit.md`](../reports/2026-06-29-motif-completeness-audit.md).
> - **WI-5 per-book adopt (`D-MOTIF-ADOPT-PER-BOOK`) — model A "book-scoped filter" (user-chosen, NOT the tier-reversal):** `motif.book_id` is a per-book LABEL on a clone the adopter still owns. The read predicate + 2-tier tenancy are **UNCHANGED** (book_id only narrows the owner's view, never widens visibility). Design: [`docs/plans/2026-06-29-motif-adopt-per-book.md`](../plans/2026-06-29-motif-adopt-per-book.md). Touch-points: schema (`book_id` col + `uq_motif_user` scoped to `book_id IS NULL` + new `uq_motif_user_book` partial + `idx_motif_book`); `MotifRepo.clone/adopt/_clone_with_code/list_for_caller`; `_MotifAdoptArgs.target=Literal['user','book']`+`book_id` (EDIT-gated at propose **and** confirm); FE adopt-to-book toggle (api/hook/AdoptTargetModal/MotifLibraryView). **Live-smoked** on real `loreweave_composition`: migration idempotent; global+per-book coexist; same-book dup blocked by `uq_motif_user_book`; 0 leaked rows.
> - **WI-6 motif_link edge-walk (`D-MOTIF-LINK-EDGEWALK`) — the FINAL §5 gap, closing the audit 7/7:** 3 MCP tools — `composition_motif_link_list` (R, traverse out/in/both with neighbor code+name), `composition_motif_link_create` + `_delete` (A). User-scoped; WRITE requires **BOTH endpoints owned by the caller** (the system↔system hole the DB `motif_link_guard` same-tier check misses — a user may never reshape the shared graph). `MotifRepo.list_links/create_link/delete_link`. **Live-smoked**: own→own create/list/delete OK; own→system rejected by the guard; 0 leaked rows. The completeness audit is now **7/7 closed, nothing deferred**.
>
> **⚠ Two already-built misfires earlier this session** (memory [[verify-built-before-building]]): `D-W8-MOTIF-BEAT-EXTRACTOR` and `D-MOTIF-SYNC-3WAY-BASE` backend were **already shipped** — I rebuilt a duplicate sync router and reverted it (`a24d99ea`). **Before building ANY "missing"/deferred motif item: `git grep` the route/module/test first.**
>
> **▶ NEXT:** **PR `feat/narrative-pattern-library` → main** — the feature body + audit tail + WI-5 are complete, green, and live-smoked. (Note: the WI-5 migration was applied to the *running* dev `loreweave_composition` by the live-smoke; a fresh stack picks it up from `migrate.py` on boot.)
>
> **▶ Deferred (motif — the §5 audit tail is 7/7 CLOSED; these were NEW future-feature rows):**
> - ✅ **`D-MOTIF-ADOPT-BOOK-COLLAB-TIER`** — **CLEARED (2026-06-29):** model B shipped (see the top block). The shared book tier landed with a 0-HIGH/0-MED adversarial tenancy review.
> - ✅ **`D-MOTIF-HTTP-ADOPT-BOOK`** — **CLEARED (2026-06-29):** the HTTP adopt route exposes `target`+`book_id`, EDIT-gated (see the top block).

---

> **▶ Archived 2026-06-30** — older / other-track handoffs moved to [`SESSION_ARCHIVE.md`](SESSION_ARCHIVE.md) to keep this file to the **active branch** only. The 2026-06-29 merge pulled in main's `Critical UX` + `Public MCP` tracks and all prior session history (glossary / composition / roleplay / extraction / KG / campaign / Sessions 66–71); all of it (incl. each track's open-defer register) lives in the archive and on its own branch + `main`. Search `SESSION_ARCHIVE.md` for a `D-…` id if you need a prior-track defer.
