# Cycle 7: Projects browser = HOME + build polish (FE) — ▶ M1

## 🎯 TL;DR (30 seconds — TOP critical info)
- **Scope:** Make **`/knowledge/projects`** the **landing browser** (HOME) for the knowledge service — completing the G6 book-workspace IA. The browser list gets **search / sort / filter-by-state / real pagination** (wire the BE cursor; today `useProjects` is a single 100-row page). Each row **routes into the C6 project-detail shell** (`/knowledge/projects/:projectId/:section`). Plus build-flow polish: post-submit feedback (a submit → a visible job), destructive-action copy, raise-cap inline, retry-in-error, and label/ETA on running builds. This is milestone **M1** — build + browse a knowledge graph end-to-end. No new BE — wire the existing cursor pagination the backend already supports.
- **Acceptance gate:** `scripts/raid/verify-cycle-7.sh` exits 0
- **Top 3 LOCKED decisions consumed:** G6 (projects-browser = home), KN-20, KN-5..12
- **DPS count:** 2
- **Estimated wall time:** 5h

## Dependencies (must show DONE in CYCLE_LOG.md)
- Cycles: C5, C6
- Files expected to exist (grep-able paths): `frontend/src/features/knowledge/components/ProjectsTab.tsx`, `frontend/src/features/knowledge/hooks/useProjects.ts`, the C6 detail-shell route `/knowledge/projects/:projectId/:section`

## Scope (IN)
- `/knowledge/projects` becomes the **landing browser**: grid/list of projects with **search** (by name), **sort**, **filter-by-state**, and **real pagination** — replace the `useProjects` single-100-row page by **wiring the BE cursor** (the backend already supports cursor pagination; the FE just stops capping at one page).
- Each browser **row routes into the C6 detail shell** (`/knowledge/projects/:projectId/overview` or equivalent default section).
- Build-flow polish (KN-5..12): **post-submit feedback** (a submit produces a visible job/row), **destructive-action copy** (clearer archive/delete wording), **raise-cap inline**, **retry-in-error**, **label/ETA** on a running build.
- `scripts/raid/verify-cycle-7.sh` (acceptance gate) + a Playwright MCP screenshot of: search/sort/filter narrowing the list, paginating past 100, and a row click landing in the C6 detail shell.

## Scope (OUT — explicitly)
- **NOT the detail shell itself** (route + sub-tab nav + Overview) — that is **C6**; this cycle only makes rows route INTO it.
- **NOT** the entities/timeline/gap/proposals sub-tab CONTENT (C8/C10/C11/C14) — those render inside C6's shell.
- **No new BE endpoint** — cursor pagination already exists server-side; wire it, do not build it. (If a list param is genuinely missing, record a finding; do not add a new endpoint here.)
- The cross-project "All projects" semantic-search surface stays a demoted secondary surface — not part of this home browser's default.
- No build/extraction contract changes (targets/concurrency/pinning = C12/C13).

## Acceptance criteria (CI gates — exit code 0 = pass)
- Tests pass: `frontend` unit tests — search/sort/filter-by-state narrow the rendered list; cursor pagination loads beyond the first page; a row click navigates to `/knowledge/projects/:projectId/...`; post-submit shows a visible job.
- Lints pass: `npm run lint` (frontend) clean on touched files.
- Integration smoke (▶ M1): Playwright MCP — search/sort/filter narrow; >100 projects paginate; click a row → C6 detail shell; submit a build → visible job. Screenshot filed with this brief (M1 milestone shot).

## DPS parallelism plan
- DPS 1: browser home — search/sort/filter-by-state UI + `useProjects` cursor-pagination wiring + row→C6-shell routing (worktree: `ProjectsTab.tsx`, `useProjects.ts`). (return budget: 1500 tokens summary)
- DPS 2: build polish — post-submit feedback, destructive copy, raise-cap inline, retry-in-error, label/ETA (worktree: build dialog + job-row components). Integrate with DPS 1 last.

## Adversary review focus (cold-start sub-agent — return budget 2000 tokens)
- **Fake pagination:** "load more" that still caps at 100 / ignores `next_cursor` — the LOCKED requirement is REAL cursor pagination wired to BE.
- **Row doesn't route to shell:** a row that opens a modal or a flat tab instead of navigating into the C6 `/knowledge/projects/:projectId/:section` shell.
- **New BE endpoint:** adding a server route when cursor pagination already exists (out of scope — wire, don't build).
- **Cross-project default drift:** turning the home browser into the "All projects" entity view rather than the project browser (G6 keeps cross-project secondary).
- **useEffect-for-events:** reacting to filter/sort changes via useEffect instead of explicit handlers (CLAUDE.md FE rule).
- **Lost build feedback:** a submit with no visible resulting job (KN-5..12 polish).

## Scope Guard CLEAR criteria (cold-start sub-agent — return budget 500 tokens)
- All scope items present (search/sort/filter-by-state, real cursor pagination, row→C6 routing, build polish set)
- No OUT items touched (no detail-shell build, no C8/C10/C11/C14 content, no new BE endpoint, no extraction-contract change)
- All acceptance criteria met (`verify-cycle-7.sh` exits 0; M1 Playwright screenshot filed)
- Cross-cycle invariants not violated (real pagination not faked; rows route into C6; cross-project stays secondary)

## Cross-references (for deep-read IF Raid Leader needs to FOCUS mode)
- CYCLE_DECOMPOSITION.md — **C7** row (Projects browser = HOME + build polish; ▶ M1; verify: search/sort/filter narrow; >100 paginate; click row → C6 detail; submit→visible job) + the "Knowledge IA = book-workspace pattern (G6)" Notes entry.
- OPEN_QUESTIONS_LOCKED.md — **§G6** (`/knowledge/projects` = HOME browser; rows route into C6; cross-project demoted to secondary search).
- `docs/specs/2026-06-13-knowledge-service-standalone-ux-review.md` — KN-20 / KN-5..12.
- `docs/specs/2026-06-13-knowledge-design-vs-impl-gap.md` — browser/build polish parity.

## ⚠️ REMINDERS (BOTTOM — re-stated critical info, anti-lost-in-middle)
- 🔴 **Top LOCKED 1:** **G6** → `/knowledge/projects` is the **HOME browser**; rows route into the C6 `/knowledge/projects/:projectId/:section` detail shell.
- 🔴 **Top LOCKED 2:** KN-20 → the browser needs search + sort + filter-by-state + **REAL cursor pagination** (wire the BE cursor; `useProjects` no longer caps at 100).
- 🔴 **Top LOCKED 3:** KN-5..12 → build polish — post-submit feedback (visible job), destructive copy, raise-cap inline, retry-in-error, label/ETA.
- 🔴 **Acceptance MUST include:** this is **M1** — Playwright MCP screenshot of search/sort/filter + paginate-past-100 + row→C6-shell + submit→visible-job; `verify-cycle-7.sh` exits 0.
- 🔴 **Do NOT touch:** the C6 shell internals; C8/C10/C11/C14 sub-tab content; no NEW BE endpoint (cursor pagination already exists — wire it); cross-project surface stays secondary.
- 🔴 **Fresh session reminder:** this is a new `/raid 7` invocation; no carry-over from prior cycles. Read CYCLE_LOG.md + this brief + LOCKED file ONLY.
