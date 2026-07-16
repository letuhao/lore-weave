# Studio Session S6 — Canon, Quality & Progress — RUN-STATE

> Anchor for the 8-session Writing-Studio completeness build. **Re-read this file FIRST after any
> compaction**, then `git log --oneline -15`, then continue at the first non-DONE slice.
> Framework: docs/plans/2026-07-16-studio-completeness-8-session-orchestration.md (read §2 the bar, §4 your charter, §5 the rules).

## COMMITMENT
S6 is DONE when: canon-rules CRUD, quality-critic+heal, the corrections display and progress are operable — each to the §2 production-ready bar (operable · CRUD · reachable ·
no-silent-fail · agent-parity · loop-connected · live-browser-proven · i18n+responsive · scale).

## SCOPE
- **Persona / files:** features/composition/{canon,quality,polish,corrections,progress}
- **Panels:** quality-canon-rules, quality-corrections, quality-heal, progress (+ flywheel home)
- **Seam / note:** Renders corrections from S1's seam — display only, never duplicate the writer.

## MANDATE (do this, in order)
1. Role-play a real web-novel author using this tool family — what must they DO?
2. Audit the CURRENT surface against that — what works, what's a skeleton, what's a dead button.
3. Per capability decide PORT / ENHANCE / BUILD — record the call, never silently drop a legacy feature.
4. Write your own detailed design (specs 31–38 are reference; the SOURCE is truth — drift is normal).
5. Build to the §2 bar. `/review-impl` at each panel close, fix what it finds.

## RULES (same-folder)
- Build only under your file subtree. Add catalog rows in your block (catalog.ts, the 8-session section).
- Shared registry (enum/contract/i18n): keep enum == openable == contract; regen `WRITE_FRONTEND_CONTRACT=1 pytest`.
- Never `git add -A`. Commit small + often. `git pull --rebase` before push. Scoped tests during BUILD.
- Stop ONLY for the 4 critical classes: destructive/irreversible · a sealed decision proven wrong ·
  tenancy/security breach · a paid action that charges the user for nothing. Everything else = defer + continue.

## SLICE BOARD  (status: TODO / DOING / DONE — DONE requires an EVIDENCE string, not a checkbox)
| slice | status | evidence (test count / live-smoke line / commit sha) |
|---|---|---|
| S6-A1 · audit current surface (role-play user) | DONE | 4-agent parallel audit (canon/critic+heal/corr+prog+flywheel/registry) + user-POV trace. All 5 S6 caps = PORT (components exist in Lane-A legacy CompositionPanel/ChapterEditorPage, unregistered in Studio dock). BE ~fully built. GUI-only user in Studio today: only quality-critic + quality-canon operable; rest reachable only via legacy /edit or MCP. |
| S6-A2 · PORT/ENHANCE/BUILD decisions per capability | DONE | canon-rules=PORT(+ENHANCE delete onError, restore/undo)+BUILD(Lane-B); quality-heal=PORT(+apply-seam); quality-corrections=PORT; progress=PORT(+BE-P2 tenancy goal table); flywheel=PORT(+deep-link retarget, contract-row fix, +Lane-B predicate). Reconcile: draft-cũ ~90% accurate vs HEAD — ONLY BE-11a restore REST route shipped; BE-9a/9c/11b/11c/P2/X-4 still must-build. |
| S6-A3 · design drafts | DONE | screen-flywheel.html CREATED (the missing 5th cap); screen-quality-completion.html verified as existing draft for the other 4 (canon-rules/corrections/heal/progress) — sealed canon=2-panel + progress=category:editor. |
| S6-A4 · detail spec | DONE | docs/specs/2026-07-16-studio-s6-canon-quality-progress.md — 6 deliverables, reconciled vs HEAD, milestone M0-M5, registry plan, test plan. |
| S6-A5 · design REVIEW / edge-case pass | DONE | §14 edge register E1-E9, verified vs HEAD (works.py idempotent · CorrectionStatsTable separable · ManuscriptUnitProvider.version · approve.py async extraction). 2 corrections folded (E2 flywheel timing, E3 F2 intrusiveness). No blocker. |
| **M0 · D0 Work-creation CTA** | DONE | `WorkSetupCta.tsx` (reuse useCreateWork+usePendingWorkResolver, idempotent POST /work); wired into `QualityWorkGate` no-work branch (NOT unavailable) + threaded bookId/token through critic/promises/coverage/hub. 30/30 vitest green (9 new + 21 existing), tsc clean. i18n en keys added. commit `<pending>`. |
| M0 · X-4 compositionEffects | RE-SEQUENCED → M1 | Lane-B ledger is per-FILE all-or-nothing (canon_rule_* + composition_publish + composition_conformance_run); a handler for panels-not-yet-built is the silent-no-op class the ledger kills. Build with canon-rules (M1); PENDING-clear needs publish + conformance predicates (coordinate S4). |
| _(session appends its build slices here)_ | | |

## REGISTERS  (append as you go — an empty DRIFT log at the end is dishonest, not clean)
### DECISIONS
- **D-S6-BRANCH** (PO 2026-07-16): NO branch switch — build on shared `feat/context-budget-law` folder (other agents running; cutting a branch breaks them). Same-folder discipline per §5.
- **D-S6-CANON-2-PANEL**: keep `quality-canon` (viewer/issues, shipped) + new `quality-canon-rules` (CRUD) as TWO panels that deep-link each other (draft phương án A; sealed in screen-quality-completion.html).
- **D-S6-PROGRESS-CAT**: `progress` = category `editor` (QC-2), NOT a quality hub card. A word-count streak is not a quality judgment.
- **D-S6-F1-FLYWHEEL-CAT** (PO approve): `flywheel` = category `knowledge` (sits with kg-* it deep-links into).
- **D-S6-F2-FLYWHEEL-HANDOFF** (PO: "mở"): publish-complete AUTO-OPENS/flashes the flywheel panel — reachable→felt, closes the loop reward.
- **D-S6-OQ1-PROPOSE-EDIT** (PO approve): `propose_edit` Apply/Dismiss does NOT record a `generation_correction` in v1 (no job_id; chat-service turn, not composition generation_job). Cross-service → later.
- **D-S6-OQ3-HEAL-ESTIMATE** (PO approve): self-heal cost preview = a descriptor on the GENERIC /actions/preview+confirm spine, NOT a bespoke /self-heal/estimate route (3 invented estimate routes already 404).
- **D-S6-HEAL-APPLY-SEAM**: heal is chapter-scoped — `applyHealedDocument({text, chapterId, expectedDraftVersion})` returning discriminated applied/no-editor/stale (never bare false). Sidesteps the Chat-based Compose buffer. (from screen-quality-completion.html QC-4)
- **D-S6-WORK-CREATION-GUI** (S1-prereq, VERIFIED + PO decided "build" 2026-07-16): ALL S6 caps gate on a composition Work; the GUI-only Work-creation affordance (`useCreateWork`/`usePendingWorkResolver`/`useGuidedFirstRun`) is mounted ONLY in legacy `CompositionPanel.tsx` — NO Studio path. RESOLUTION = **build (option a)**: S6 adds a shared "Set up co-writer" CTA to `QualityWorkGate` no-work state, reusing the EXISTING `useCreateWork` + `usePendingWorkResolver` (knowledge-backfill poll). Makes all S6 panels operable for a fresh book without waiting on S1. Reuse across every S6 panel that gates on a Work.

### PARKED  (blocker -> defer row + continue)
- _(none — all CLARIFY open questions sealed)_

### DEBT
- **E5 take-first-candidate** — quality panels bind the FIRST Work on an ambiguous multi-Work book (pre-existing convention across ALL consumers). Not S6's to fix; cross-cutting. Filed.
- **E6 BE-9a null-job report** — the "N units couldn't capture a correction" honest surface belongs to S1's authoring-run report (S1 owns the producer seam). Coordinate BE-9a/9b with S1.
- **D5 S7 deep-link targets** — flywheel chips open cast/kg-timeline/kg-graph (S7's panels). Pace M5 after S7 registers them; disable-with-reason any not-yet-registered target, never a dead chip.

### DRIFT  (near-misses, bars nearly lowered, tests nearly skipped)
- Draft screen-quality-completion.html flags BE-11a `restore` as MUST-BUILD, but it SHIPPED since (canon.py:192-216). Verified before trusting the doc (repo laws: verify claim against code; missing-infra≠blocked). Do NOT re-build restore.
- **E2 near-miss** — the flywheel draft + spec first keyed the Lane-B refresh + F2 auto-open on `composition_publish`. But the delta is produced by an ASYNC knowledge extraction AFTER publish → would have opened an EMPTY flywheel. Caught in the design REVIEW pass by reading approve.py; corrected to key on extraction-complete.
- **E3 near-miss** — F2 "auto-open flywheel on publish" would hijack the human's focus when an AGENT publishes in the background. Corrected: FE-initiated → open; agent/background → flash/toast-with-link.
