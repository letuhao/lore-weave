# Writing Studio (v2) — Master Spec

> **Status:** ACTIVE · branch `feat/writing-studio` · started 2026-07-01
> **Type:** FE, from-scratch. Does **not** touch the current `ChapterEditorPage`.

## What this is

A new, VS Code–style **docking workspace for a whole book** — the successor surface to the
chaotic 24-tab co-writer studio. dockview owns the centre (drag / split / stack / float /
pop-out); a fixed frame of chrome (activity bar, side-bar navigators, top/status bars, a
toggle bottom panel) wraps it. Panels (the real writing tools) are added **one at a time**.

Frame reference mockup: [`design-drafts/screens/studio/screen-writing-studio-frame.html`](../../../design-drafts/screens/studio/screen-writing-studio-frame.html).

## How we work here — build-while-plan (LOCKED)

This track deliberately **inverts** the usual plan-then-build. We build incrementally and
spec **just-in-time**:

- This **master file** holds the durable decisions, the frame architecture, and the
  **component index** (below) with per-component status.
- Each component gets its **own small spec file** (`NN_<component>.md`) written when we start
  it — scope, data, states, done-criteria — not a big upfront plan.
- A component is only as specced as it is built. Specs grow with the code, never ahead of it.

## Locked decisions

| # | Decision | Why |
|---|---|---|
| D1 | **dockview-react v7** owns the centre dock | Our in-house dock layer is a single linear rail — can't do splits/tab-groups/regions. dockview = VS Code-grade, zero-dep, MIT, React-18. |
| D2 | New route `/books/:bookId/studio`, book-level (no chapter needed) | It's a whole-book workspace; a book-level "Studio" CTA opens it. |
| D3 | From scratch — reuse shared components + the state-hoist blueprint, **not** the current editor | Easier to control a clean build than retrofit the editor. |
| D4 | **Live/in-flight state lives ABOVE dockview**; panels are thin views over hoisted state | dockview unmounts a closed panel; hoisting keeps co-writer streams / editor docs alive so closing/moving a panel never drops work. Wire when the first *stateful* panel lands. |
| D5 | Fixed chrome (top bar, activity bar, side bar, status bar) is **never** a dock tab; bottom panel is a toggle | Navigation is the spine — it must never be floated, buried, or accidentally closed. |
| D6 | Layout + chrome UI state persist **per-book** in localStorage (per-device) | `lw_studio_layout_<bookId>` (dockview `toJSON`) + `lw_studio_chrome_<bookId>` (active view / collapses). |
| D7 | **Two palettes**, VS Code–faithful — **⌘P / Ctrl+P** = Quick Open (manuscript locations); **⌘⇧P / Ctrl+Shift+P** = Command Palette (open tool panel + chrome actions) | Sidebar tree = spatial map; Quick Open = global jump from any focus; Command Palette = 25+ dock tools the activity bar cannot hold. Overlap with the sidebar jump box is intentional (same data layer — see [`06a_quick_open.md`](06a_quick_open.md)). |
| D8 | **Studio Tool Registry** — every dock panel/tool **registers** on mount | Incremental tool use: palette ([#06b](06b_command_palette.md)) and chat rack ([#07a](07a_agent_context_rack.md)) only show registered entries; unregistered legacy panels are invisible until ported. |
| D9 | **Studio MCP Host** — FE `StudioContextBus` + `studio_context` on chat turns | VS Code extension-host analogue: panels publish context slices; chat + `ui_*` tools consume. Does **not** replace ai-gateway federation. See [`07c_studio_tool_registry.md`](07c_studio_tool_registry.md). |
| D10 | **Agent Context Rack** above chat input; **Runtime Inspector** below chat header | Rack = user-pinned skills/MCP tools (agent capability). Inspector = lazy-load state machine visibility. Separate from [`ContextBar`](../../../frontend/src/features/chat/context/ContextBar.tsx) (turn attachments). |
| D11 | **Agent surface state machine** exposed in Runtime Inspector | Phases: Idle → Curated → Discovering → Activated → SkillInjected → ToolRunning. Mirrors mcp-public-gateway session activation + chat-service discovery. |
| D12 | **Pinned tools** on session (`enabled_tools` / `enabled_skills`) override discovery subset; empty ⇒ auto-discovery fallback | Aligns with [`04-ai-chat-core`](../../2026-06-30-editor-compose-overhaul/stories/04-ai-chat-core.md) tool curation; Rack is the FE for that persistence. |
| D13 | **Manuscript unit hoist** — Rich (#04a) + Raw (#04b) share `useManuscriptUnit` above dockview | One chapter draft + scene metadata; no divergent copies when dock tabs move/close (D4). |
| D14 | **Raw buffer** = `ManuscriptUnitDocument` JSON (`loreweave.manuscript-unit.v1`) | Chapter Tiptap `body` + composition `scenes[]` metadata in one code-like editor — not plain prose. |
| D15 | **Raw Editor** = editable dock tab with code editor UX (format, validate, ⌘S) | Distinct from legacy read-only [`SourceView`](../../../frontend/src/components/editor/SourceView.tsx) toggle inside Tiptap. |
| D16 | **Navigator / Quick Open** can open Rich, Raw, or Reader per chapter | Registry `editor` + `raw` panels; see [`04b_raw_editor.md`](04b_raw_editor.md). |
| D17 | **Scene prose stays in `chapter.body`**; raw `scenes[]` is outline metadata only | Synopsis, status, `beat_role` — not a second prose store. |
| D18 | **5-tier state model** — local → chrome/layout → host → domain hoists → remote SSOT | No god-store as tool count grows; see [`08_studio_state_architecture.md`](08_studio_state_architecture.md). |
| D19 | **Bus = read-only snapshots**; domain mutation through hoist owner actions only | Panels publish context; never mutate another panel's hoist via bus subscription. |
| D20 | **FSM only for orchestration domains** — session boot, save conflict, agent surface | Navigator tree and chrome toggles do not need XState. |
| D21 | **Selector-based subscriptions**; volatile (SSE/streaming) split from stable host context | Prevents whole-frame re-render on every Tiptap keystroke or chat chunk. |
| D22 | **Panel author checklist** mandatory before merging a new dock tool | Register, hoist owner, bus slice, selectors, lifecycle — [`08`](08_studio_state_architecture.md) §Checklist. |
| D23 | **Three-lane agent→GUI model** — ui intent / MCP reconcile / human-gate | See [`09_agent_gui_reconciliation.md`](09_agent_gui_reconciliation.md). |
| D24 | **No data-bearing frontend tools** — agent must not patch GUI via draft/prose blobs in `ui_*` args | Saves tokens; SSOT via reload. |
| D25 | **`StudioEffectReconciler`** — sole path MCP tool success → GUI data refresh | Handlers in code, not LLM `setState`. |
| D26 | **Human-gate Apply** → domain hoist actions; studio deprecates `editorBridge` write path | `propose_edit` / `confirm_action` per #09. |
| D27 | **Agent lifecycle hooks** — server-side event bus + sandbox scripts (`.loreweave/hooks.json`) | Extends agent loop like VS Code/Kiro; not local shell — see [`10`](10_agent_lifecycle_hooks.md). |
| D28 | **Hook bundles** scoped per-user and per-book (MinIO + Postgres); System-tier admin-only | Tenancy per CLAUDE.md; book collaborators EDIT can write book hooks. |
| D29 | **Hook merge** — System → user → book; all match run; **most restrictive wins** (`deny` > `ask` > `allow`) | Aligns VS Code / Copilot multi-source hooks. |
| D30 | **Sandbox-only execution** — `agent-hook-runner` ephemeral container; hooks never bypass #09 reconciler or Tier-W/S | GUI refresh stays code-owned (H1–H5 in #10). |

## Frame regions

```
┌ Top bar (fixed) ───────────────────────────────────────────────┐
│ Act │ Side bar (fixed) │ Dock area (dockview) ▸ split/float/pop │
│ bar │  active navigator │──────────────────────────────────────│
│     │                   │ Bottom panel (toggle)                 │
├ Status bar (fixed) ────────────────────────────────────────────┤
```

The Side-Bar navigator **drives the dock**: selecting a unit opens/focuses its panel in a
dock group (Explorer → editor-group analogue).

## Component index

> **⚠ STATUS SOURCE OF TRUTH (2026-07-12):** the per-spec status below is copied from
> [`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) **§4**, which ground-truthed
> every spec 00–29 against the code (*"no spec checkbox or status line was trusted"*). Rows 02/03/04/07/08/09
> previously read ⏳/📐 while being substantially built — that staleness was itself an audit finding (X-8).
> **When these disagree, §4 wins.** Do not edit a status here from memory; re-verify against code.

| # | Component | Spec | Status (per 30 §4) |
|---|---|---|---|
| 01 | **Frame skeleton** — all fixed regions + dockview shell, mechanics working, content stubbed | [`01_skeleton.md`](01_skeleton.md) | ✅ built (frame). Bottom-panel Jobs/Generation/Issues are still stub strings — *the stub IS the spec*; Wave 7 (#37) wires them. Top-bar Generate/Save/model never built (Debt #2) |
| 02 | Manuscript navigator (chapters→scenes, drives the dock) | — *(built without a spec)* | 🟡 **built, PARTIAL** — 🔴 the new-chapter `+` is **permanently dead** (`ManuscriptNavigator.tsx:116` `disabled={!onNewChapter}`; `StudioFrame` never passes it). Also missing: reveal-in-tree on jump, exact arc chapter-range badge, partial-outline merge, degenerate-level collapse |
| 03 | Compose panel (co-writer dock tab — embeds upgraded chat per #07) | — | ✅ **BUILT** (`ComposePanel.tsx`) — **spec never written** |
| 04 | **Manuscript editors** (Rich + Raw pair, shared hoist) | [`04_manuscript_editor.md`](04_manuscript_editor.md) | 🟡 **built, PARTIAL** — no `lw_studio_default_editor` pref (D16's Rich/Raw/Reader choice is hard-coded to `editor`); no M2 save-or-discard prompt (auto-saves); no Rich↔Raw live-sync round trip |
| 04a | Rich editor (Tiptap WYSIWYG) | *(in 04)* | ✅ built |
| 04b | **Raw editor** (structured JSON — chapter body + scene metadata) | [`04b_raw_editor.md`](04b_raw_editor.md) | ✅ built (as #12 cycle 1's `manuscript-unit` provider) — json-editor Validate/Copy/Open-Rich buttons unshipped |
| 05 | Story-Bible navigator + detail panel | — | ❌ **navigator half MISSING** — `StudioSideBar.tsx:73` stubs `activeView === 'bible'` **and `'search'`**: two Activity-Bar views lead nowhere. Detail half superseded by #13/#14/#15 |
| 06a | **Quick Open** (⌘P / Ctrl+P) — jump to arc / chapter / scene | [`06a_quick_open.md`](06a_quick_open.md) | ✅ built (no multi-row-per-chapter, recents, arc-expand) |
| 06b | **Command Palette** (⌘⇧P / Ctrl+Shift+P) — open dock tool + chrome actions | [`06b_command_palette.md`](06b_command_palette.md) | ✅ built (no recents group; the 3 deferred commands are blocked on Debt #2) |
| 07 | **Studio agent chat upgrade** (registry + bus + rack + inspector) | [`07_studio_agent_chat.md`](07_studio_agent_chat.md) | 🟡 **built, PARTIAL** — 🔴 `consumer_capabilities` (`chat-service/app/models.py:502`) and `contributeContext()` (`studio/host/types.ts:31`) are **DEAD FIELDS**: declared, read/called by nothing |
| 07a | Agent Context Rack (pin skills + MCP tools) | [`07a_agent_context_rack.md`](07a_agent_context_rack.md) | 🟡 built (no rack pin limits; no "Studio panels" group in the add-browser) |
| 07b | Agent Runtime Inspector (lazy-load state machine) | [`07b_agent_runtime_inspector.md`](07b_agent_runtime_inspector.md) | ✅ built |
| 07c | Studio tool registry + MCP bus | [`07c_studio_tool_registry.md`](07c_studio_tool_registry.md) | ✅ built |
| 07S | **Studio agent standard** (context/compaction/approval law) | [`07S_studio_agent_standard.md`](07S_studio_agent_standard.md) | 🟡 PARTIAL — 🔴 **no microcompact tier, no `hard_truncate`, no `compaction_failed` breaker (0 grep hits)** while Agent Mode's L3/L4 autonomous runs **have shipped**, and this standard's own §3/§10 make the breaker **MANDATORY for headless runs**. Also unshipped: §5c hunk-level accept/reject, §4 per-server-tool approval, §4 MCP resources+prompts, §8 memory-for-canon |
| 08 | **Studio state architecture** (5-tier model, host, bus rules, panel checklist) | [`08_studio_state_architecture.md`](08_studio_state_architecture.md) | 🟡 **built, PARTIAL** — `StudioSessionOrchestrator` **completely absent**; S7: closing a dock tab does **not** prompt save-or-discard on a dirty hoist (no `onWillClose` guard) |
| 09 | **Agent GUI reconciliation** (3-lane: ui intent / MCP reload / human-gate) | [`09_agent_gui_reconciliation.md`](09_agent_gui_reconciliation.md) | 🟡 **built, PARTIAL** — G6's `consumer_capabilities` filter is dead (above); `ui_watch_job` is neither a studio tool nor intercepted → it **route-navigates out of the studio and unmounts the dock** (fixed by 30's X-5) |
| 10 | **Agent lifecycle hooks** (sandbox scripts, pre/post tool events) | [`10_agent_lifecycle_hooks.md`](10_agent_lifecycle_hooks.md) | ❌ **0% BUILT** — zero grep hits for `HookOrchestrator`/`agent-hook-runner`/`agent_hook_bundles`/`preToolUse`/`postToolUse` anywhere. **The single biggest unbuilt block in 00–11** |
| 11 | **Dockable migration wave 1** — foundation seams (openPanel params · status-bar contributions · link resolver) + usage/notifications/settings/trash panels | [`11_dockable_migration.md`](11_dockable_migration.md) | ✅ built + live-smoked |
| 12 | **JSON Document Standard** (4th registry `registerJsonDocumentProvider` + generic `json-editor` panel, CM6+schema) + **per-tool cycle model** (one tool per cycle, 6-point gate incl. live agent→MCP→DB→panel-realtime). Cycle 1 = **chapter editor** (manuscript-unit provider + scene support — makes the navigator scene layer real; absorbs Debt #6/#04b) | [`12_json_document_standard.md`](12_json_document_standard.md) | ✅ built (cycle 1) |
| 13 | **Glossary dockable migration** — cycle-2 of the queue in #12, re-scoped as shared-foundation-then-fanout (7 sub-features + 3 DOCK-standard violations found: DOCK-8 page-replacement, DOCK-9 6× hand-rolled modal, DOCK-10 no entity hoist). **Phase A ✅ + Phase B ✅ built** — all 5 Glossary capabilities are now real dock panels (`glossary`/`glossary-ontology`/`glossary-unknown`/`glossary-ai-suggestions`/`glossary-merge-candidates`, all palette+agent-openable) and all 6 hand-rolled modals are migrated (`FormDialog` for simple templates, raw `Dialog.*` for custom multi-part chrome) | [`13_glossary_panels.md`](13_glossary_panels.md) | ✅ built |
| 14 | **Knowledge/KG dockable migration** — larger than #13 (~4,300 lines, 2 route-driven tab hubs collapsing to ~13 unique panels; 3 genuine DOCK-9 hand-rolled overlays [1 grep hit reclassified as an accepted popover pattern, not a violation], 3 DOCK-7 route-couplings, no book→project hoist; global cross-book hub migrates too, as user-scoped panels per the human's K1 call). **Phase A ✅ + Phase B ✅ built** — all 13 capabilities are now real dock panels (`knowledge` hub + `kg-overview`/`kg-entities`/`kg-timeline`/`kg-evidence`/`kg-gap`/`kg-proposals`/`kg-schema`/`kg-graph`/`kg-insights`/`kg-jobs`/`kg-bio`/`kg-privacy`, all palette+agent-openable); Phase B fanned out as 12 parallel background agents + one serial integration pass. Remaining (deferred, not forgotten): retire the classic routes into thin redirects, Playwright E2E, cross-panel drill-down E2E | [`14_kg_panels.md`](14_kg_panels.md) | ✅ built |
| 15 | **Wiki dockable migration** — narrow surface (no shared-foundation-then-fanout needed): 2 target panels (`wiki`, `wiki-editor`), 2 DOCK-9 hand-rolled modals, zero MCP tool surface (no Lane-B), zero JSON-editable structure worth a document provider. CLARIFY locked: `wiki-editor` is a params-retargeting singleton (editor/book-reader/json-editor precedent), not a modal; no GUI/UX redesign (faithful port only, confirmed with the user). **✅ built** — both panels shipped with a G7 dirty-guard on retarget (the migration's one genuine new-risk finding), 2 DOCK-9 fixes, and a fixed dead History button; `/review-impl` clean | [`15_wiki_panels.md`](15_wiki_panels.md) | ✅ built |
| 16 | **Chapter Editor Parity & Retirement (COHERENCE)** — the "Cursor-for-novels" register's #1 gap: `ChapterEditorPage` (legacy) and Studio v2 are two live, uncoordinated chapter-editing surfaces; a capability audit found 15 legacy-only gaps. User-approved direction: retire the legacy page, Studio becomes the sole surface, phased by risk (data-safety → editor-craft UX → Translate → route retirement). **Phase 1 (data-safety) ✅ complete** — P1 Lane-C `applyProposedEdit` hoist action (`f548859db`), Checkpoints + Revision History + Publish Gate (`16286995e`, `/review-impl` caught + fixed a cross-hook stale-restore-point bug between the two independently-built restore hooks), the `ChaptersTab.tsx` route switch (`f9ca330f3`) — all live-browser-smoke-verified against the real backend. Mobile shell remains an explicit open product decision. **NEXT:** Phase 2 (editor-craft UX) — roadmap only, own capability audit at kickoff | [`16_chapter_editor_parity_and_retirement.md`](16_chapter_editor_parity_and_retirement.md) | 🔨 Phase 1 ✅ done |
| 18 | **Book-open routing + Command Palette domain grouping** — workspace-browser book-open now lands directly in Studio (classic `BookDetailPage` routes kept as fallback, no new UI affordance to them); Command Palette's flat 46-item "Panels" group splits into 9 domain sub-groups via a new `StudioPanelDef.category` field | [`18_book_open_and_palette_grouping.md`](18_book_open_and_palette_grouping.md) | ✅ built |
| 19 | **Studio onboarding fork + catalog-driven User Guide** — role-based overlay (server-synced pref, reuses `@/lib/syncPrefs`) above the mounted dock, role-tailored Welcome dock, a new `user-guide` panel generated from catalog metadata (no hand-authored docs), react-joyride `core` tour + 5 role-specific tours anchored to live DOM via catalog `tourAnchor`. **Wave 1 ✅ + Wave 2 ✅ built** (Wave 1: 25 unit + 4 live E2E + 26 regression E2E, BE enum + contract regen, `/review-impl` fixed an i18n gap + a coverage gap; Wave 2: all 47 panels' `guideBodyKey` × 4 locales via 9+3 parallel agent fanout, 5 role tours, live E2E caught + fixed a cross-hook shared-account-state bug) — 744/744 unit + 18/18 live E2E, tsc/eslint clean | [`19_onboarding_and_user_guide.md`](19_onboarding_and_user_guide.md) | ✅ done |
| 20 | **Agent Mode / Mission Control** — the "Cursor-for-novels" register's #4 (last) gap: 0% frontend + 0 MCP tools over a fully-built backend (`authoring_run_service.py`, 1346 lines) for autonomous multi-chapter drafting runs. CLARIFY confirmed a load-bearing backend fact the first mockup pass got wrong: the driver drafts every unit back-to-back with **no accept/reject gate between units** — review is server-blocked outside `report_ready`/`failed`/`paused`. Locked: one `agent-mode` panel (Runs list/New run/Mission control) + a new `chapter-revision-compare` panel wrapping the existing (already-built) `RevisionCompareView` diff renderer; client-side "auto-pause after each unit" (default ON); a new `composition_authoring_run_*` MCP tool surface (11 tools, spend-triggering ones confirm-gated) so chat can supervise a run; keyboard triage (a/r/←/→) in the review panel. Two-round backend audit (driver advance condition + plan/diff-viewer precedents) before writing the spec — see [`20_agent_mode.md`](20_agent_mode.md)'s Ground-truth table for citations. **⚠ BUILT — the "0% frontend / not yet built" line this row and 00C Q-2 used to carry is FLATLY FALSE** (30 §4): the panel is in `catalog.ts` **and** the agent enum. Unshipped tail: no Lane-B effect handler for `composition_authoring_run_*` (30 X-4), a now-false comment at `useStudioEffectReconciler.ts:10`, and a missing `guideBodyKey`. ⚠ Its L3/L4 autonomous runs ship **without** 07S's mandatory `compaction_failed` breaker. | [`20_agent_mode.md`](20_agent_mode.md) | ✅ shipped (its own header is stale) |
| 21 | **Plan Hub** — the composition-domain "tech tree": a fancy graph-canvas hub (React Flow) unifying arc/chapter/scene/beat/cast/motif, replacing the scattered 25-tab legacy `CompositionPanel` + 56-tool composition-service surface. Audit found **0 of 25 legacy sub-tabs ported verbatim** (the row-103 "planner/quality already ported" assumption was a false positive — both are different backends sharing a label) + 1 outline-navigator gap + 3 tool groups with zero UI anywhere. Phased: **P0** beat canonicalization (2 coexisting beat models today) → **P1** hub v1 (graph render + reused OutlineTree CRUD) → **P2** capability-porting backlog (the real mass, fanout waves like #13/#14) → **P3** net-new UI for the 3 zero-UI tool groups → **P4** AI-edit highlighting on the graph | [`21_plan_hub.md`](21_plan_hub.md) | 📐 CLARIFY roadmap locked, build not started |
| 22 | **Scene — model, CRUD (GUI+MCP), Browser & Inspector** — investigation found *"scene"* names **two disjoint entities** that share a `chapter_id` and never join: `book-service.scenes` (parse leaf, Per-book, **`/internal`-only — no public route at all**) and `composition.outline_node kind='scene'` (12-field authored intent, Per-user). Hence the empty rail on every imported book. Second defect: the model isn't thin, the **exposure** is — `SceneRail` edits 2 fields, MCP writes 4 of 12; `goal` is agent-writable + human-invisible, while `pov_entity_id`/`present_entity_ids`/`tension` are **read-only to everyone** despite gating the packer's voice-tag injection and `adaptive_k`'s `>=70` reasoning policy. **⚠ Amended same-day to the package model** ([`00A`](00A_BOOK_PACKAGE_STRUCTURE.md)): composition's `outline_node` is the **spec** (authored SSOT of intent — it gains the 8 intent columns: setting/time · conflict/outcome/value_shift · stakes/target_words · typed `exit_state`); `book-service.scenes` is the **index** (a parse-derived source map — the anchor INVERTED to a non-unique `scenes.source_scene_id`, its `/v1` surface is 3 read-only routes, and `book_scene_*` MCP tools are read-only). All 5 FK dependents stay put; the greenfield cross-service write on create is deleted. Two new panels: `scene-browser` (the spec∪index union table) + `scene-inspector`. `knowledge-service` + `worker-infra` untouched by design. | [`22_scene_model_and_crud.md`](22_scene_model_and_crud.md) | 📐 specced + amended |
| 00A | **Book Package Structure** — the governing model: a book is a **package** (manifest `composition_work` · registry `deps/` · lockfile `motif_application` · **spec/** · tests/ · manuscript/ · index/ · build-dir `.runs/`); PlanForge is the **compiler**; plan↔prose is desired-state↔actual-state (the terraform relation), never source→binary. 14 invariants (DA-1..14) + a 21-entry Decisions Register (BPS-1..21, incl. the C23 derivative-Work refinements) that closed every open question. | [`00A_BOOK_PACKAGE_STRUCTURE.md`](00A_BOOK_PACKAGE_STRUCTURE.md) | 🗺️ law |
| 23 | **Book architecture — `structure_node`** — the durable spec layer (saga→arc→sub-arc, per-book, tracks/roster/roster_bindings; pacing DERIVED from scene tension). Kills the write-only arc (`kind='arc'` and dead `'beat'` removed); conformance retargets to spec↔prose; full arc MCP surface (create/move/assign/apply/extract); the packer finally READS the spec (BA12 + effect test). E5/E3 (the BPS-20 fixture-constant bug + dead compile payloads) **built + verified 2026-07-10**; migration + link-step execution superseded by 25/27. | [`23_book_architecture.md`](23_book_architecture.md) | 📐 specced (E5/E3 ✅) |
| 24 | **Plan Hub v2** — the package explorer on the graph canvas: `structure_node` lanes as Core, two-truths node cards (spec chip + prose chip), derived pacing sparkline, lockfile chips, problems overlay (canon+threads) + direct IX-14 drift consumption (≤5-request cold-open budget), 29-item re-map, deterministic lane layout, Plan navigator rail. | [`24_plan_hub_v2.md`](24_plan_hub_v2.md) | 📐 specced (multi-agent, reviewed) |
| 25 | **Package migration master** — owns ALL re-key DDL: 12-table per-book re-key with `project_id` as the Work partition key (PM-3, derivative-safe), partial manifest unique (PM-4), two-deploy plan (M0 fail-loud pre-flights → expand → backfill → cutover → structure lift → contract → M6 registered trains), knowledge-service verdict = safe now. | [`25_package_migration_master.md`](25_package_migration_master.md) | 📐 specced (multi-agent, reviewed) |
| 26 | **Structure↔prose indexing** — the source-map lifecycle as a closed state machine (authored→drafted→linked→dirty→orphaned + draft-indexed/unplanned); publish-only re-parse (canon, not drafts); hash-preserving upsert; poll-on-read staleness (no stored dirty bit); decompile write-back stays index-owner-side; ONE conformance read contract (IX-14). | [`26_structure_prose_indexing.md`](26_structure_prose_indexing.md) | 📐 specced (multi-agent, reviewed) |
| 27 | **PlanForge v2 — the multi-pass compiler** — 7 pass contracts (deps→symbols→world→schedule→char-arcs→codegen→lint) over a resumable `plan_run` pass-cursor state machine with make-style downstream invalidation; the LINK STEP (skeleton + scene linkers, run-scoped idempotency PF-10, `source='planforge'`, user-edit preservation PF-11); blocking checkpoints at cast + arc shape; S06 replay as the acceptance gate. | [`27_planforge_v2_compiler.md`](27_planforge_v2_compiler.md) | 📐 specced (multi-agent, reviewed) |
| 28 | **Agent-native studio** — Cursor-parity capability matrix (normative, closed) + the gap layer: `composition_package_tree` (the agent's `ls -R`, ≈2-4K tokens, canonical-Work-scoped), `composition_find_references` (8 sources), `composition_diagnostics` (the problems panel, composes IX-14), `book_steering_*` (the `.cursorrules` analogue), `book_search`, go-to-definition/prose recipes; the edit-discipline safety contract; S06 traced end-to-end. | [`28_agent_native_studio.md`](28_agent_native_studio.md) | 📐 specced (multi-agent, reviewed) |
| 00B | **Execution roadmap** — one dependency-ordered sequence over 22-28 (9 stages, RB-1..8 risk-boundary checkpoints), wave-parallelization plan + shared-file collision registry, the adjudication ledger (15 CF + 4 NC, **all ✅**), 15 consolidated PO-DECIDE items, per-pillar definition-of-done tied to effect tests. | [`00B_EXECUTION_ROADMAP.md`](00B_EXECUTION_ROADMAP.md) | 🗺️ integrated v2 |
| 00C | **Post-Architecture Queue** — everything in this track that is NOT in 00B, drift-proofed with dated ground truth + verify-first rules: translation-repair build (unblocked), Quality-hub completion, the three retirement cycles, the ⏳ tail (Reader/Compare · Search nav · Jobs/Generation/Issues). | [`00C_POST_ARCHITECTURE_QUEUE.md`](00C_POST_ARCHITECTURE_QUEUE.md) | 📋 queue |
| 29 | **Translation repair** — the 10 translate-UI defects (T1–T10; T8 critical: the coverage matrix silently drops the chapter selection) + the `target_language` free-string closed-set⇒enum breach. Phase A is frontend-only. The parallel lane: disjoint from every other track. | [`29_translation_repair.md`](29_translation_repair.md) | 📐 specced · ❌ **0 of T1–T10 built** |
| **30** | **⭐ Tool↔GUI Gap — Audit & Master Plan** — the umbrella. Joins every MCP tool × REST route × table × panel **on the resource**: **22 verified gaps** (18 CONFIRMED / 4 PARTIAL / 0 refuted), **3 live 404s** in shipped FE code, 19 backend prereqs, a completeness-critic pass (+26 items), **§4 = the authoritative status audit of specs 00–29**, and **4 SEALED PO decisions** (§0: AN-12 amended · G-WORKFLOWS → Track C · `ui_show_panel` retired · specs+drafts before any implementation plan). Enforces **GG-1: every backend capability a user owns must have a human surface.** Waves 0–8 + the spec-29 parallel lane. | [`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) | 🗺️ **plan, PO-approved** — build not planned yet |
| 31 | **Quality completion** (Wave 1) — `quality-canon-rules` · `quality-corrections` · `quality-heal` · `progress`. Closes the sharpest read-without-write asymmetry: the Studio *judges* you against canon rules and gives you no way to write one; the correction flywheel only accrues for legacy-page users. | [`31_quality_completion.md`](31_quality_completion.md) | 📐 specced + drafted |
| 32 | **Arc Inspector** (Wave 2) — CRUD for `structure_node`, the spec tree `pack()`'s `gather_arc` lens injects into **every** generation. This IS 23-**C3** / **DBT-06**; unblocks 24-**H3.1**. | [`32_arc_inspector.md`](32_arc_inspector.md) | 📐 specced + drafted |
| 33 | **Motif Studio** (Wave 3, XL→3 milestones) — the 套路/爽点/打脸 layer: `motif-library` + link graph · binding lens · suggest · `quality-conformance` + the 3 live 404 fixes. **HARD GATE: X-7 (`gather_motifs` packer lens) — without it this wave ships decoration** (`pack()` reads no motif today). | [`33_motif_studio.md`](33_motif_studio.md) | 📐 specced + drafted (adversarially reviewed) |
| 34 | **Arc Templates + 拆文** (Wave 4) — `arc-templates` with an Import & Deconstruct section. ⚠ its review found the audit's "BE: NONE" was false: a confirmed deconstruct enqueues a job **nobody can read** (BE-7c). | [`34_arc_templates_and_deconstruct.md`](34_arc_templates_and_deconstruct.md) | 📐 specced + drafted |
| 35 | **PlanForge made human** (Wave 5) — the `plan-passes` Pass Rail (the 7-pass ledger + the two BLOCKING checkpoints a GUI user currently **cannot** advance past) + planner repair. Folds in 27-B1/B2 contract hygiene. | [`35_planforge_studio.md`](35_planforge_studio.md) | 📐 specced + drafted |
| 36 | **Editor-craft ports** (Wave 6) — `style-voice` · `reference-shelf` · `divergence` + a Composition section in `book-settings` + a Beats facet/Decompose action in `plan-hub`. 🔴 **This wave is the GG-4 gate: spec 16's `ChapterEditorPage` retirement may proceed only when it closes** — retiring earlier DELETES shipped features. | [`36_editor_craft_ports.md`](36_editor_craft_ports.md) | 📐 specced + drafted |
| 37 | **Issues feed** (Wave 7) — wires the **existing** `StudioBottomPanel` Issues tab to a REST mirror of `composition_diagnostics` + a `find-references` right-click lens. **Zero new panel ids** (AN-12's architecture honoured; only its "no GUI" clause is amended, per PO-1). | [`37_issues_feed.md`](37_issues_feed.md) | 📐 specced + drafted |
| 38 | **KG write holes + World Map** (Wave 8) — 8a: 4 additive KG affordances (no Create anywhere; 3 dead buttons). 8b: a `world` container + `world-map` — a whole CRUD domain reachable **only by an agent**, whose UPDATE semantics exist at **no** layer. **G-WORKFLOWS is DROPPED here → Track C owns it (PO-2).** | [`38_kg_and_world.md`](38_kg_and_world.md) | 📐 specced + drafted |

*(Rows are added/promoted as we go. Order is a guide, not a contract — the human directs which is next.)*

## Testing discipline (LOCKED — this track is stricter than the rest)

**Build-to-solid, no defer.** Every component ships with tests before we move on:

1. **Unit tests** for each component + hook (states, branches, persistence, guards).
2. **E2E** for each component's user-visible behaviour, via a Playwright spec + page object.
3. **Inter-component links:** build the **data link first** (the wiring in code + unit tests).
   **Defer only the E2E of that link** until the *other* component exists — then add it. Record
   the deferred E2E-link on the **Debt stack** below.
4. Each milestone ends with **`/review-impl`** (adversarial) → fix → re-run all tests.

**Debt is a STACK, not a queue — newest debt is paid FIRST (LIFO).** Every deferral is
recorded here the moment it's created; when we start the next component we clear the top of
the stack before adding new rows.

## Debt stack (LIFO — top = paid next)

> **Refreshed 2026-07-12 against [`30`](30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) §4** — the original 6 rows were
> **stale**: 5 of them had been cleared *by building the thing*, and the stack still read as if #02/#03/#06/#07
> were unbuilt. Cleared rows moved below; the still-open ones are re-stated with today's evidence. The
> **track-wide** unshipped tail now lives in 30 §4 (per-spec) and 30 §7 (waves) — it is **not** re-listed here.

| ▲ | From | Debt | Clears when |
|---|---|---|---|
| 1 | 13 glossary | 🔴 **`AddModelCta` DOCK-7** — a raw `<Link to="/settings/providers">` with **no `useOptionalStudioHost()` branch**, reachable from live dock panels: clicking it **tears down the entire dockview layout**. Every new panel in waves 1–8 renders a ModelPicker whose empty state is this component. | 30 **Wave 0 / X-1** — fix at the **shared component**, not the ~8 call sites (`glossary-translate/StepConfig.tsx` is the shipped precedent) |
| 2 | 01 skeleton | Top-bar **Generate / Save / model** controls **still not built** (the only original row that never cleared) — also blocks 06b's 3 deferred palette commands | the first panel that needs them |
| 3 | 07S standard | 🔴 **No `compaction_failed` breaker / microcompact tier / `hard_truncate`** — while Agent Mode's **L3/L4 autonomous runs have shipped**, and 07S §3/§10 make the breaker **MANDATORY** for headless runs | its own slice — see the Deferred row in `SESSION_HANDOFF.md` (P1 defect, not a nice-to-have) |

**Cleared by building (2026-07-12 audit):** ~~#1 navigator→dock link~~ (#02 drives the dock; the
*reveal-in-tree* remainder is folded into row 02) · ~~#3 Quick Open~~ (✅ #06a) · ~~#4 Command
Palette~~ (✅ #06b) · ~~#5 Agent chat upgrade~~ (✅ #07/07a/07b/07c) · ~~#6 Raw editor~~ (✅ shipped as
#12 cycle 1's `loreweave.manuscript-unit.v1` provider).

**Chrome copy (design intent, not yet wired):** top-bar palette affordance → *"Go to chapter, scene, arc…"* (locations only — tools live in ⌘⇧P). Status bar → show both `⌘P` and `⌘⇧P` hints. Mockups: [`screen-command-palette.html`](../../../design-drafts/screens/studio/screen-command-palette.html) · [`screen-studio-agent-chat.html`](../../../design-drafts/screens/studio/screen-studio-agent-chat.html) · [`screen-studio-raw-editor.html`](../../../design-drafts/screens/studio/screen-studio-raw-editor.html) · [`screen-studio-state-host.html`](../../../design-drafts/screens/studio/screen-studio-state-host.html) · [`screen-studio-agent-gui-bridge.html`](../../../design-drafts/screens/studio/screen-studio-agent-gui-bridge.html) · [`screen-studio-agent-hooks.html`](../../../design-drafts/screens/studio/screen-studio-agent-hooks.html).

**Recently cleared:** ~~Studio inherited `EditorLayout`'s app rail → two left rails~~ → **fixed
2026-07-01**: studio moved to a standalone full-screen `RequireAuth` route (out of `EditorLayout`);
`StudioFrame` root is `h-screen`. The Activity Bar is now the only left rail.

*(Pop the top when starting the next component; push any new deferral on top. Nothing leaves
this table silently — it's cleared by building, not by forgetting.)*

## Out of scope (for now)

Mobile (the studio is desktop-first; small screens fall back to the existing editor); server
sync of layout (localStorage per-device is enough until multi-device studio is needed);
migrating the old co-writer studio (it stays until the new one reaches parity).
