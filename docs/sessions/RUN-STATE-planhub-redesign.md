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
- [x] S5 · RESOLVED 2026-07-18 — the human OVERRODE the plotter's caution and mandated full mockup
      fidelity, no defer ("build all item in the draft html, compare 1 by 1"). Built as a NEW
      CSS-flow Advanced view (`LaneFlowView` + `FlowLane` recursive + `FlowChapterCard`), REPLACING
      the React Flow graph in the Advanced branch. Wrap lanes (62% + resize:horizontal), inset
      sub-arcs, wrapping chapter cards, scene chips (lazy), inline +arc/+sub-arc/+chapter/+scene,
      authorship coding (source column now on the wire), bounded auto-expand (MAX 8 roots — keeps the
      cold-open budget). The x-axis-alignment concern is MOOT: the flow view is a document tree, not a
      shared-axis graph, so there is no cross-arc axis to break. See
      `docs/plans/2026-07-18-plan-hub-mockup-parity.md` for the item-by-item audit. LIVE-QC'd on :5290.
- [x] S6 · DONE — commit `95e3f3b28` (feat/context-budget-law), 48 files. tsc 0; plan-hub+studio my
      tests green; i18n gate 17 locales full parity; BOTH modes live-smoked on the static build :5290
      (Simple: default view + write-door create+editor; Advanced: full arc name legible, toggle works).
      Committed MY files ONLY by explicit path — excluded 4 parallel sessions' work (useManuscriptTree
      S-02b, TriageQueue, services/*, KgOverviewPanel, studio-completeness docs, divergence docs).

## COMPLETENESS AUDIT + FIXES (2026-07-18, commit a45db093b)
Full item-by-item audit: `docs/plans/2026-07-18-plan-hub-mockup-parity.md`. An independent cold-start
review + a user-flagged critical downgrade drove these fixes (all live-QC'd on :5290):
- **Graph restored (the critical downgrade):** Advanced now = **Graph** (React Flow: zoom/pan/drag/
  scene-links; the default) OR **Lane** (the mockup flow view), a per-user toggle (`usePlanAdvancedView`).
  This also un-deads `PlanCanvas` + `usePlanMoves` (DEBT-2 resolved — all move/link fns are consumed again).
- **Authorship color (HIGH):** `src()` only caught `'mined'`; real AI values are `'planforge'`/
  `'decompiled'`/`'imported'`. `normalizeSource` (authored=human, all-else=machine). BE `source`
  projection DEPLOYED; live: planforge→mono/teal, authored→serif/amber, status tints show.
- Cross-book state-leak reset · ch-N dense-ordinal fix · dead-fn delete · cycle guard · unassigned
  fileable group · Lane "move to arc" picker. 270 plan-hub + 1661 plan-hub+studio tests green; tsc 0.
- **DEBT (pending): i18n keys uncommitted.** `planHub.adv.*` + `flow.moveTo`/`unassigned` are in the
  working tree but held out of a45db093b — a sibling session's uncommitted `layout` keys got entangled
  in the same locale files via gap-fill. App works via `t(key, default)` fallbacks; commit when the
  sibling's i18n settles. Target: next session / coordinated i18n commit.
- **GAP (minor, open): no "collapse scenes" affordance** in the Lane view once a chapter's scenes are
  revealed. Low priority.

## DELIVERED
Plan-hub redesign, both modes, committed. Simple mode (new, default) + Advanced readable cards + chip
cut, on top of this arc's origin/+Chapter/+Scene create. QC'd on an isolated static build per the goal.

## STILL UNCOMMITTED (this session, SEPARATE concern — earlier docs-refresh task, ready to commit)
docs/ARCHITECTURE.md, DATA_ARCHITECTURE.md, FEATURE_INDEX.md, README.md, CLAUDE.md,
docs/03_planning/LLM_MMO_RPG/features/_index.md, infra/db-ensure.sh (scheduler DB fix),
infra/docker-compose.yml (5176 port-collision fix). Not part of the plan-hub redesign; commit apart.
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
- NEAR-MISS: cardWidth 128→208 broke 2 `chapterAtPoint` hit-test unit tests that hardcoded pixel
  coords for width=128. Rewrote them to `D.*` geometry (self-correcting under any dimension change).
- NEAR-MISS: the shared checkout carries 4 sessions' work. `git status` showed KG/services/completeness
  files I never touched. Had I `git add -A`'d I'd have swept another session's in-flight work into my
  commit. Avoided by explicit-path staging + a grep-verify that nothing foreign was staged.
- DELIBERATE test change: LaneBandPaging "counter renders even when fully loaded" asserted the OLD
  always-on pill; updated to the new intent (count only when hasMore) — user-panel-driven, not a
  regression. Recorded so it isn't mistaken for one.
- DEFERRED honestly (not "build cho có"): S5 default-expand (cold-open budget) + wrap rebuild (plotter
  said wrap breaks the x-axis). Recorded rather than rushed.
