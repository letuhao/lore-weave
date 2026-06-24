# Cycle 6: Project detail SHELL (FE — IA backbone, G6)

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Build the **IA backbone** for the G6 book-workspace restructure. Today `KnowledgePage.tsx` is a flat 8-tab shell where Entities/Timeline/Raw each carry their own project `<select>` (breaks at thousands of projects). This cycle adds the nested route **`/knowledge/projects/:projectId/:section`** + a **project-detail SHELL** that reads `projectId` from the **ROUTE** (not a select-box) and hosts the project-scoped sub-tab nav: **Overview** (state + stats + config) · Entities · Timeline · Evidence · Proposals · Gap · Insights · **Build/Explore-graph**. When scoped by route, the per-tab project `<select>` is **REMOVED**. The `complete`-card "Explore graph" CTA + clickable stats deep-link into the shell. C8/C14/Raw will render *inside* this shell (forward-context only — those are other cycles). Mostly re-composition; no new BE.
- **Acceptance gate:** `scripts/raid/verify-cycle-6.sh` exits 0
- **Top 3 LOCKED decisions consumed:** G6 (project-detail-as-home), KN-2/BL-17, KN-20
- **DPS count:** 2
- **Estimated wall time:** 5h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C0
- Files expected to exist (grep-able paths): `frontend/src/pages/KnowledgePage.tsx`, `frontend/src/features/knowledge/components/{EntitiesTab,TimelineTab,RawDrawersTab,ProjectsTab}.tsx`, `frontend/src/features/knowledge/hooks/useProjects.ts`

## Scope (IN)
- New nested route **`/knowledge/projects/:projectId/:section`** registered in the app router; the project-detail SHELL component as its element.
- Shell hosts **project-scoped sub-tab nav** with sections: Overview · Entities · Timeline · Evidence · Proposals · Gap · Insights · Build/Explore-graph. Active section from the `:section` route param.
- **Overview** section: project **state + stats + config** (read existing project data via `useProjects`/project-detail data); the `complete`-card **"Explore graph" CTA** and **clickable stats** deep-link into the relevant sub-section of the shell.
- `projectId` resolved from the **route param**, threaded down as the scope to sub-tabs. When a tab is rendered **scoped**, its own project `<select>` is **REMOVED** (the tabs already accept a `projectFilter` — feed it from the route, hide the dropdown when scoped).
- **`RawDrawersTab` moves into the shell** and loses its project dropdown when scoped (small edit, folded here per the G6 note).
- `scripts/raid/verify-cycle-6.sh` (acceptance gate) + a Playwright MCP screenshot of the detail shell with scoped sub-tabs (no project dropdown) + Explore-graph routing in.

## Scope (OUT — explicitly)
- **NOT the projects browser/home** (`/knowledge/projects` landing search/sort/filter/pagination) — that is **C7** (it routes INTO this shell).
- **NOT** the entities semantic layer (C8), timeline narrative-order (C14), gap report (C10), proposals aggregation (C11) — this cycle builds the SHELL that hosts them; the sub-tab CONTENT lands in those cycles. Stub/placeholder where content isn't yet built is fine.
- The **cross-project "All projects" search surface** stays a demoted secondary surface — do NOT make it the default; the `<select>` survives ONLY there.
- `/knowledge/jobs · /global · /privacy` stay top-level (legitimately cross-project) — do not fold them into the shell.
- No new BE endpoints.

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `frontend` route/unit tests — `/knowledge/projects/:projectId/:section` resolves the shell; the active sub-tab derives from `:section`; a scoped tab renders WITHOUT a project `<select>`; Explore-graph CTA navigates into the shell's graph section.
- Lints pass: `npm run lint` (frontend) clean on touched files.
- Integration smoke: Playwright MCP — click a project → land in the detail shell → switch sub-tabs (all scoped to that project, no dropdown) → click "Explore graph". Screenshot filed with this brief.

## DPS parallelism plan
- DPS 1: route registration (`/knowledge/projects/:projectId/:section`) + shell component + sub-tab nav + Overview (state/stats/config + Explore-graph & clickable-stats deep-links). (return budget: 1500 tokens summary)
- DPS 2: scope-threading — feed `projectId` from route into Entities/Timeline/Raw, hide their project `<select>` when scoped (the `projectFilter` prop already exists). Integrate with DPS 1's shell last.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Select-box not removed:** a sub-tab still renders its own project `<select>` while route-scoped — defeats the whole G6 IA backbone.
- **projectId from state not route:** scope sourced from a context/select instead of the `:projectId` route param → breaks deep-linking and the book-workspace pattern.
- **Cross-project default drift:** making the "All projects" surface the default landing instead of a demoted secondary search (G6 LOCKED keeps it secondary).
- **Stateful-unmount:** conditionally unmounting sub-tab components on section switch (ternary render) destroys hook/query state — use route-driven rendering, not unmount churn (CLAUDE.md FE rule).
- **Folding cross-project tabs in:** wrongly nesting jobs/global/privacy into the project shell.
- **Scope creep into C7/C8/C14:** implementing browser pagination or entity/timeline content here.

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (nested route, shell, Overview, scoped sub-tabs with `<select>` removed, Explore-graph deep-link, Raw moved in)
- No OUT items touched (no browser/home pagination, no C8/C10/C11/C14 content, no jobs/global/privacy folding, no BE)
- All acceptance criteria met (`verify-cycle-6.sh` exits 0; Playwright screenshot filed)
- Cross-cycle invariants not violated (route-sourced projectId; cross-project surface stays secondary; no stateful unmount)

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- CYCLE_DECOMPOSITION.md — **C6** row (Project detail SHELL; verify: click project → detail shell → sub-tabs scoped, no dropdown; Explore-graph routes in) + the "Knowledge IA = book-workspace pattern (G6)" Notes entry.
- OPEN_QUESTIONS_LOCKED.md — **§G6** (Knowledge IA: project-detail home, cross-project demoted to secondary search).
- `docs/specs/2026-06-13-knowledge-service-standalone-ux-review.md` — KN-2 / KN-20 / BL-17.
- `docs/specs/2026-06-13-knowledge-design-vs-impl-gap.md` — design-draft IA parity.

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Top LOCKED 1:** **G6** → `/knowledge/projects/:projectId/:section` project-detail SHELL is HOME for a project; `projectId` from the **ROUTE**, per-tab project `<select>` **REMOVED** when scoped.
- 🔴 **Top LOCKED 2:** G6 cross-project → the "All projects" view is a **demoted secondary search** surface only; never the default landing. The `<select>` survives ONLY there.
- 🔴 **Top LOCKED 3:** KN-2/KN-20 → Overview = state + stats + config; `complete`-card "Explore graph" CTA + clickable stats deep-link INTO the shell.
- 🔴 **Acceptance MUST include:** Playwright MCP screenshot proving scoped sub-tabs with NO project dropdown + Explore-graph routing in; `verify-cycle-6.sh` exits 0.
- 🔴 **Do NOT touch:** C7 browser pagination/home; C8/C10/C11/C14 sub-tab CONTENT (shell only — stubs OK); jobs/global/privacy top-level tabs; backend. No stateful-unmount on section switch.
- 🔴 **Fresh session reminder:** this is a new `/raid 6` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
