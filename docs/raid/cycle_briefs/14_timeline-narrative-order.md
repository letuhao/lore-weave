# Cycle 14: Timeline narrative-order + importance (▶ M2)

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Add event **importance (major/pivotal)** + **narrative-order sort** to the knowledge timeline, plus the **timeline rail UI**, rendered **inside the C6 project-detail shell scoped by route** (the per-tab project `<select>` is removed when scoped — G6). Thin BE (importance field + narrative-order sort on the existing timeline endpoint) + FE (the rail with importance badges). This is **milestone M2** — knowledge service "design-complete" vs the 2026-04-13 draft; file the M2 milestone screenshot set with this brief.
- **Acceptance gate:** `scripts/raid/verify-cycle-14.sh` exits 0
- **Top 3 LOCKED decisions consumed:** C14-importance-major-pivotal, C14-narrative-order-sort, G6-scoped-by-route-no-select
- **DPS count:** 2
- **Estimated wall time:** 3–4h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C8
- Files expected to exist (grep-able paths): C8's entities semantic layer rendered inside the C6 project-detail shell; the C6 nested route `/knowledge/projects/:projectId/:section` shell + project-scoped sub-tab nav; the existing knowledge timeline endpoint + `TimelineTab` component.

## Scope (IN)
- **BE (thin):** add event **importance** (`major` / `pivotal`) to the timeline event model/endpoint; add a **narrative-order sort** option to the timeline list endpoint (narrative order, not just chronological/insertion). Additive — existing timeline consumers unaffected when the new sort/field are unset.
- **FE timeline rail:** render the timeline as a rail with **importance badges** (major/pivotal visually distinct) in narrative order, **inside the C6 project-detail shell**, `projectId` from the route. **Remove the per-tab project `<select>`** when scoped (G6); the select survives only on the optional cross-project search surface.
- **M2 milestone:** Playwright screenshot set proving knowledge "design-complete" vs the draft (semantic entities + promote + gap report + proposals inbox + 3-step wizard + target-typed + pinning + narrative timeline all reachable in the shell).
- `scripts/raid/verify-cycle-14.sh` (acceptance gate; runner creates it) + the timeline-rail Playwright screenshot.

## Scope (OUT — explicitly)
- **NO target-typed extraction / pinning** — that is C12/C13; this cycle consumes already-built events, it does not change extraction.
- **NO new timeline data pipeline** — importance + narrative-order are over the existing event store; no re-extraction.
- **NO flat-tab regression** — do NOT re-introduce a project `<select>` inside the scoped timeline tab (G6 removes it); the shell + route come from C6.
- No graph canvas (C19); no world container; no derivative timeline tree (C28).

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass:
  - BE unit: timeline endpoint returns `importance` (major/pivotal) on events; narrative-order sort returns events in narrative order; unset sort/field = existing behavior (back-compat).
  - FE unit: rail renders importance badges; reads `projectId` from route (no `<select>`).
- Lints pass: ruff/black on knowledge-service; eslint/tsc on the frontend.
- **Integration smoke (FE — Playwright):** evidence string contains `playwright: timeline rail renders narrative order with importance badges`. Log in as `claude-test@loreweave.dev`, open a built project's Timeline sub-tab in the C6 shell → screenshot the narrative-order rail with major/pivotal badges. **M2 milestone** screenshot set filed with the brief.

## DPS parallelism plan
- DPS 1 (BE thin): importance field + narrative-order sort on the timeline endpoint + unit tests (return budget: 1500 tokens summary)
- DPS 2 (FE): timeline rail with importance badges inside the C6 shell, route-scoped, `<select>` removed; Playwright shot + M2 milestone set
- **Serial tail (Raid Leader):** `verify-cycle-14.sh` + assemble the M2 milestone screenshot set

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **G6 scoping regression:** the timeline tab still carrying its own project `<select>` instead of reading `projectId` from the route → breaks the book-workspace IA at thousands of projects.
- **Narrative-order vs chronological confusion:** sort labelled "narrative" but actually returning insertion/chronological order → the feature's whole point lost.
- **Importance enum drift:** values other than `major`/`pivotal` leaking through, or a default that mislabels ordinary events as major.
- **Back-compat break:** existing timeline callers broken when the new sort/importance are unset.
- **Milestone evidence gap:** M2 claims "design-complete" but a draft surface (semantic entities / promote / gap / proposals / wizard / pinning / timeline) is not actually reachable in the shell — confirm with the screenshot set.
- **FE state-unmount smell:** conditional unmount of the timeline tab destroying scroll/selection state (CLAUDE.md FE rule) instead of CSS-hidden.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (importance + narrative-order sort + rail UI scoped in C6 shell + M2 screenshot set)
- No OUT items touched (no extraction change, no re-introduced `<select>`, no graph/world/derivative)
- All acceptance criteria met (BE+FE units + lints + Playwright timeline-rail screenshot)
- Cross-cycle invariants not violated (G6 route-scoping; additive BE; back-compat)

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- Cycle row: [CYCLE_DECOMPOSITION.md](../../plans/2026-06-13-creation-unblock/CYCLE_DECOMPOSITION.md) — C14 row (▶ M2) + the G6 book-workspace IA note + M2 milestone definition.
- LOCKED decisions: [OPEN_QUESTIONS_LOCKED.md](../../plans/2026-06-13-creation-unblock/OPEN_QUESTIONS_LOCKED.md) — §Knowledge cycle design "C14 timeline = importance (major/pivotal) + narrative-order"; G6 IA lock (scoped-by-route, `<select>` removed).
- Design detail of the C12/C13 wizard surfaces that complete M2: [DESIGN_C12_C13.md](../../plans/2026-06-13-creation-unblock/DESIGN_C12_C13.md).
- Backend audit: [2026-06-13-knowledge-design-vs-impl-gap.md](../../specs/2026-06-13-knowledge-design-vs-impl-gap.md).

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Top LOCKED 1:** C14 = event **importance (major/pivotal)** + **narrative-order sort** + the rail UI — thin BE, additive.
- 🔴 **Top LOCKED 2:** G6 — render inside the **C6 project-detail shell scoped by route**; **remove** the per-tab project `<select>` when scoped (select survives only on the optional cross-project search surface).
- 🔴 **Top LOCKED 3:** this is **milestone M2** (knowledge design-complete vs the 2026-04-13 draft) — file the M2 Playwright screenshot set with this brief.
- 🔴 **Acceptance MUST include:** the Playwright token `playwright: timeline rail renders narrative order with importance badges` (test account `claude-test@loreweave.dev`).
- 🔴 **Do NOT touch:** extraction (C12/C13) — consume existing events; do NOT re-introduce a project `<select>` in the scoped tab.
- 🔴 **Fresh session reminder:** this is a new `/raid 14` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
