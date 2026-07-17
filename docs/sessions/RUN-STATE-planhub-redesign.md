# RUN-STATE — Plan Hub redesign build

> The commitment + slice board for this build. Re-read this FIRST after any compaction, then `git log`, then continue.

## GOAL (sealed with the human)
Build the Plan Hub redesign in **both modes** (Simple + Advanced), QC each slice hard, on an
**isolated static FE build served on a dedicated port** — because 4 other sessions run vite-dev in
this same folder and their HMR cross-contaminates a shared dev server (the multi-session-HMR confound).

## HARD CONSTRAINTS (invariants — do not violate)
1. **NEVER QC on `vite dev`.** Build static (`npm run build` → `dist/`) and serve with
   `npx vite preview --port 5290 --strictPort` (preview has the `/v1`→:3123 proxy). Port **5290** is
   THIS session's; the parallel sessions own 5199 and others — do not touch theirs.
2. **QC every slice on the static build** before moving on. Unit-green is not proof (the day's lesson).
3. **Keep the authorship coding** (Lora+amber = authored, Mono+teal = AI) — the panel's unanimous keep.
4. **Simple mode = content-first**: linear chapter list + one "Write a new chapter" door (create
   chapter → open editor). No "arc" jargon in Simple. Same data model (real chapters; unassigned ⇒
   UnplannedTray). Per-user setting (like the shipped MotifSimpleMode). Simple is the DEFAULT.
5. **Advanced = the canvas**: readable cards (kill the 128px truncation), full arc→chapter→scene
   hierarchy, bounded+resizable lanes, wrap; **cut the telemetry chips** (100/340, ⚠gap, N ch).
6. Backend is complete — this is GUI-only (engines-gated-on-GUIs). No schema/route changes.
7. i18n: any new user-facing string → `en` + gap-fill 18 locales via `scripts/i18n_translate.py`.

## DESIGN SOURCE OF TRUTH
- Advanced canvas mockup: `design-drafts/plan-hub-redesign/index.html`
- Simple mode mockup: `design-drafts/plan-hub-redesign/simple-mode.html`
- Spec (origin/create): `docs/specs/2026-07-17-studio-structure-origin.md`
- Panel verdict: Fancy 4/5, Easy 2/5, Sufficient 2/5 → Simple mode is the easy-to-use fix.

## ALREADY SHIPPED (this session, verified live on :5199 before the isolation rule)
- Origin verb "Start with your first arc" (empty state) — arc+Work+KG created ✅
- Toolbar +Arc / +Sub-arc — server-confirmed ✅
- Drawer +Chapter (3-call cross-seam) / +Scene — +Chapter live-verified; +Scene wired+backend-verified
- laneLayout: empty-arc pin-left (no cascade) + leaf header strip — unit tests updated
- 1528 FE tests green; tsc clean; i18n 18/18 parity for studio ns

## SLICE BOARD (done = an evidence string)
- [x] S0 · isolated static build — `vite build` exit 0 + `vite preview :5290` serves 200
- [x] S1 · Mode toggle + per-user setting — `usePlanHubMode` mirrors MotifSimpleMode; toggle in panel, aria-pressed=true for Simple by default
- [x] S2 · Simple list view — QC :5290: default view, 3 chapter rows (no/title/status/→), NO "arc" jargon, tsc 0, 235 plan-hub tests green
- [x] S3 · Write door — QC :5290: click → bookChapterCount 3→4 (real chapter) + Editor tab opened (focusManuscriptUnit). Verified server-side.
- [x] S4 · Advanced card redesign — cardWidth 128→208 + titles wrap (line-clamp-2) not truncate;
      lane header arc name wraps ≤2 lines; telemetry count pill gated on hasMore (cut when fully
      loaded). tsc 0; layout 49 green (updated 2 chapterAtPoint tests to D.* geometry); LaneBandPaging
      updated to new count intent. QC on :5290 pending in S6.
- [~] S5 · DEFERRED with rationale (not "build cho có"):
      · default-expand-on-load → fires a per-arc chapter-window fetch each, violating the documented
        ≤5-request cold-open budget (usePlanHub.ts:76-77). Not safe to rush.
      · full wrap/bounded-resizable lanes → LARGE React-Flow rebuild AND the 3-user panel's plotter
        explicitly found wrap BREAKS the shared x-axis (chapter N stops aligning across arcs), which
        is the whole point of lanes. Contested direction — needs a PO decision (wrap vs true-axis),
        not a rushed build. Both-modes is satisfied without it: Simple (default) + Advanced (readable
        cards + create hierarchy) are built.
- [ ] S6 · VERIFY: full suite + tsc + i18n parity + live smoke BOTH modes on :5290; SESSION+COMMIT
      (commit MY files only — KgOverviewPanel*/OverviewSection/knowledge.json are ANOTHER session's
      in-flight work in this shared checkout; their 8 test fails are NOT my regression).
      NOTE: working tree also carries this session's earlier uncommitted work (docs ARCHITECTURE/
      DATA/FEATURE_INDEX, infra db-ensure + compose 5176 port fix, origin/+Chapter/+Scene, laneLayout
      fixes). S6 must commit in LOGICAL chunks, not one giant commit.

## REGISTERS (append as you go — an empty drift log at the end is dishonest)
### Decisions
- (start) Simple mode is a NEW view alongside the existing canvas; toggle is a per-user setting.
### Parked / blocked
- (none yet)
### Debt
- +Scene live-UI-proof was blocked by chapter-node selection flakiness (Bug C) — re-verify in S5.
### Drift / near-misses
- (record them)
