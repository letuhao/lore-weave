# 00C · Post-Architecture Queue — the writing-studio work that is NOT in 00B

> **Status:** 📋 queue · written 2026-07-10, at the moment the 22–28 cluster was sealed — captured
> now so the return to it happens **without drift**.
> **What this is:** every known writing-studio work item that is *outside* the book-package
> architecture plan ([`00B`](00B_EXECUTION_ROADMAP.md)). When 00B's stages complete, this file is
> the next backlog — nothing else should be hiding.
> **What this is NOT:** the v2+ feature ledger (that is [`00B §9`](00B_EXECUTION_ROADMAP.md) —
> owned there, not duplicated here); other tracks (Track D liveness, the discoverability/S06
> chat-platform work — their own handoffs); or a to-do list to trust blindly.
>
> **⚠ THE DRIFT RULE (why every row carries dated evidence):** this repo has measured that debt
> lists overstate reality by ~40–50% within weeks (`debt-batches-list-is-stale-verify-first`), and
> has twice shipped "blocked" items that already existed. Every row below is ground-truthed
> **2026-07-10**. A future session MUST re-verify a row against code before building it — the row
> tells it exactly what to check. A row that turns out already-done gets moved to §3, never
> silently deleted.

---

## 1. The queue

Ordered by entry condition, not priority — the PO picks order when the time comes.

| # | Item | What it is | Ground truth (2026-07-10) | Entry condition | Spec state |
|---|---|---|---|---|---|
| **Q-1** | **Translation repair build** | The 10 translate-UI defects (T1–T10; T8 critical — the matrix drops chapter select) + design conflicts (modal race, backfill UNIQUE collisions) | [`29_translation_repair.md`](29_translation_repair.md): CLARIFY complete, DESIGN reviewed, PO decisions taken; Phase A is **frontend-only**, Phase C deferred | **None — unblocked now.** Disjoint files from the whole 00B cluster; can run in parallel with any stage | 📐 specced, build-ready |
| **Q-2** | **Agent Mode / Mission Control build** | The `agent-mode` panel (Runs list / New run / Mission control) + `chapter-revision-compare` panel + keyboard triage over the fully-built `authoring_run_service.py` backend; the 11 `composition_authoring_run_*` MCP tools already ship | [`20_agent_mode.md`](20_agent_mode.md): 📐 specced, 0% frontend. **Verify first:** whether any panel work landed since (grep `agent-mode` in `catalog.ts`) | **After 00B RB-1** (25-M3 re-keys `authoring_runs` reads + P-3's VIEW widening — building the panel on pre-re-key tenancy means building it twice) | 📐 specced |
| **Q-3** | **Quality-hub completion** — the two homeless legacy capabilities | (a) `progress` word-count goals (legacy `ProgressPanel.tsx`, CRUD, 143 LOC — the `composition_daily_progress`/`_baseline` tables live outside the package and are untouched by 25); (b) `quality` correction-stats (accept/edit/regenerate/reject rates — [`21`](21_plan_hub.md)'s audit: **"no Studio equivalent anywhere"**); (c) the `threads` panel consolidation 21 flagged (duplicate of `quality-promises` — **delete, don't port**) | 21's audit rows #18/#19/#20, dated 2026-07-07. **Verify first:** grep the Studio catalog for `progress`/correction-stat surfaces — a concurrent cycle may have shipped one | **None — unblocked now.** Small (S/M); touches only Quality-hub + one new panel | ⏳ needs a small spec (the ONE unspecced-but-known feature gap in the track) |
| **Q-4** | **Chapter-editor retirement, remaining phases** | [`16_chapter_editor_parity_and_retirement.md`](16_chapter_editor_parity_and_retirement.md) shipped Phase 1 only | Overview row 16: `🔨 Phase 1 ✅ done`. **Verify first:** read 16's phase table for what Phases 2+ actually contain — do not trust this row's memory of it | Per 16's own phase gates | 📐 specced (later phases) |
| **Q-5** | **OutlineTree retirement** | Remove `OutlineTree.tsx` + its `ChapterEditorPage` mount once the Hub + Plan navigator rail cover its CRUD (P-12 ✅ said: no list toggle in v1, OutlineTree stays *until its retirement cycle* — this is that cycle) | `OutlineTree.tsx` is live and load-bearing today (the only outline drag-reorder GUI until 24-H5) | **After 00B Stage 7** (24-H5 interactions + H6 rail shipped and smoked) | needs a retirement checklist, not a spec |
| **Q-6** | **Legacy CompositionPanel retirement** | Delete the 25-tab legacy panel once every tab is either absorbed by the Hub (per [`24`](24_plan_hub_v2.md) §Package re-map), reassigned and built (Q-3), or consciously killed | 0 of 25 tabs ported verbatim (21's audit); the Hub covers the plan-domain ones at Stage 7; Q-3 covers the last two orphans | **After Stage 7 + Q-3** — the re-map table is the retirement checklist | the re-map table IS the spec |
| **Q-7** | **The overview's ⏳ tail** — Reader/Compare cycle (#12 queue), Search navigation, Jobs/Generation/Issues bottom panels | Named in [`00_OVERVIEW.md`](00_OVERVIEW.md)'s queue row since the track started; no specs exist | **None** — independent of the cluster | ⏳ each needs its own spec when scheduled |

## 2. Explicit non-items (so this file doesn't become a dumping ground)

- **The 14 v2+ feature cuts** (timeline/worldmap modes, canvas plan-agent, draft indexing,
  federation, digest, branching UX, volume proposals, …) — owned by [`00B §9`](00B_EXECUTION_ROADMAP.md)
  with per-row triggers. Consult that ledger; never re-list here.
- **AN-12 `resource_ref`** — owned by [`28`](28_agent_native_studio.md) OQ-8, gated on 24 Phase 4.
- **Other tracks** — Track D (tool liveness), the S06 flagship's chat-platform side (S01–S05
  servant scenarios), enrichment/KG cycles: their own `SESSION_HANDOFF` blocks and specs.
- **Anything discovered during 00B's build** — new findings ride 00B's own stages/defer
  discipline, not this queue.

## 3. Recently cleared

*(empty — move rows here when they're verified done, per the SESSION_HANDOFF convention)*
