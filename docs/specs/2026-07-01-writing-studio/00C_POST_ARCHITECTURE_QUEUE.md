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

> **⚠ SUPERSESSION NOTE (2026-07-12).** This queue is no longer the whole picture. The
> [`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) audit found **22 verified
> tool↔GUI gaps** this file never knew about, and now owns the plan for them (waves 0–8, specs 31–38).
> **Q-1 and Q-3 are folded into it** (Q-3 → spec [`31`](31_quality_completion.md); Q-1 stays plan-30's
> parallel lane). **Q-2 was FALSE and is cleared** (§3). Read 30 first; this file is the remainder.

Ordered by entry condition, not priority — the PO picks order when the time comes.

| # | Item | What it is | Ground truth (2026-07-10) | Entry condition | Spec state |
|---|---|---|---|---|---|
| **Q-1** | **Translation repair build** | The 10 translate-UI defects (T1–T10; T8 critical — the matrix drops chapter select) + design conflicts (modal race, backfill UNIQUE collisions) | [`29_translation_repair.md`](29_translation_repair.md): CLARIFY complete, DESIGN reviewed, PO decisions taken; Phase A is **frontend-only**, Phase C deferred. **Re-confirmed 2026-07-12** by the [`30`](30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) audit (§4): **0 of T1–T10 built** — and it carries a Frontend-Tool-Contract breach (`target_language` is a free string; closed-set ⇒ enum) | **None — unblocked now.** Disjoint files from the whole 00B cluster; can run in parallel with any stage. **Plan 30 keeps it as its own parallel lane** (§7, "the parallel lane") | 📐 [`29`](29_translation_repair.md) — build-ready |
| **Q-2** | ~~Agent Mode / Mission Control build~~ — **CLEARED 2026-07-12 (this row was FALSE)** | — | 🔴 **The "0% frontend" ground truth was wrong**: [`30`](30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) §4 verified `agent-mode` is **in `catalog.ts` AND in the agent panel enum** — the panel is **shipped** (spec 20's own header is likewise stale). The `verify-first` rule this file wrote for itself is exactly what caught it. Residual tail is **not** a queue item: it is plan-30 **X-4** (a Lane-B effect handler for `composition_authoring_run_*` + the now-false comment at `useStudioEffectReconciler.ts:10`) and **X-3** (a missing `guideBodyKey`). ⚠ **One real defect does need a home:** its **L3/L4 autonomous runs ship without 07S's mandatory `compaction_failed` breaker** — raised as a P1 Deferred row in `SESSION_HANDOFF.md`, not here | — | ✅ **moved to §3** |
| **Q-3** | **Quality-hub completion** — the two homeless legacy capabilities | (a) `progress` word-count goals (legacy `ProgressPanel.tsx`, CRUD, 143 LOC); (b) `quality` correction-stats (accept/edit/regenerate/reject rates — **"no Studio equivalent anywhere"**); (c) the `threads` panel consolidation 21 flagged (duplicate of `quality-promises` — **delete, don't port**) | **Superseded by a spec: [`31_quality_completion.md`](31_quality_completion.md)** (plan-30 **Wave 1**, 📐 specced + drafted 2026-07-13). It absorbs Q-3(a)+(b) **and widens the scope the audit proved was bigger**: `G-CANON-RULE-CRUD` (the Studio judges you against canon rules and gives you no way to write one) + `G-POLISH-SELFHEAL` + the **correction-capture seam** (BE-9 — the load-bearing half; today the flywheel only accrues for legacy-page users) | **None — unblocked now**, but sequence behind plan-30 **Wave 0** (X-1/X-2/X-3/X-4 are landmines under every new panel) | 📐 **[`31`](31_quality_completion.md)** — no longer "needs a spec" |
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

- **Q-2 · Agent Mode / Mission Control — cleared 2026-07-12, because it was already built.** The row
  claimed *"0% frontend"*; [`30`](30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) §4 read `catalog.ts` and the agent
  panel enum and found `agent-mode` in **both**. It was never blocked on 00B RB-1. **This is the drift
  rule paying for itself** — the row's own *"Verify first: grep `agent-mode` in `catalog.ts`"* is the
  check that refuted it. Its residual tail lives in plan-30's Wave 0 (X-3, X-4); its one real defect
  (autonomous runs with no `compaction_failed` breaker) is a Deferred row in `SESSION_HANDOFF.md`.
