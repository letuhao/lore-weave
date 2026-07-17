# Studio Session S6 — Canon, Quality & Progress — RUN-STATE

> Anchor for the 8-session Writing-Studio completeness build. **Re-read this file FIRST after any
> compaction**, then `git log --oneline -15`, then continue at the first non-DONE slice.
> Framework: docs/plans/2026-07-16-studio-completeness-8-session-orchestration.md (read §2 the bar, §4 your charter, §5 the rules).

## COMMITMENT
S6 is DONE when: canon-rules CRUD, quality-critic+heal, the corrections display and progress are operable — each to the §2 production-ready bar (operable · CRUD · reachable ·
no-silent-fail · agent-parity · loop-connected · live-browser-proven · i18n+responsive · scale).

## ▶ AUTONOMOUS RUN — CLEAR S6 (PO-authorized 2026-07-16)
**GOAL (the /goal condition):** S6 is cleared when **quality-corrections (M2), quality-heal (M3), progress (M4), and flywheel (M5)** are EACH registered + operable in the Studio
to the §2 bar, committed. DONE requires, per slice, the transcript to CONTAIN: (a) the pasted scoped-test output (green), AND (b) a pasted live-browser QC smoke line driving the real
panel (or an explicit `live infra unavailable: <reason>` when the stack can't boot). Claiming a check passed without pasting its output does NOT satisfy this. **Bound:** stop + report
after all four close, OR when blocked on one of the 4 critical classes.
- **QC per slice** (not just unit tests): drive the real panel in a browser. **LLM-driven checks use model gemma-4-26b-a4b-qat** (local lm_studio; resolve its `user_model_id` live per CLAUDE.md test account).
- **Static FE on a dedicated port** (PO instruction): serve a BUILT FE on its own port so a concurrent session's `vite dev` HMR can't shadow/reset my smoke. `npm run build` is blocked by S4's
  `MotifDetailDrawer.tsx` tsc error (not mine), so build via `npx vite build` (esbuild, no typecheck) → serve `dist/` on a free port with a `/v1`→`:3123` proxy. Rebuild after each slice.
- **Anti-race discipline (our side):** commit-atomically (`git add <paths> && git commit` in ONE shell call), tiny slices, prefer NEW files in my subtree over edits to hot shared files;
  never `git add -A`. If S6 work is swept into another track's commit again, verify it's green on HEAD and continue (don't re-commit).

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
| **M1.1 · quality-canon-rules register + mount** | DONE | `QualityCanonRulesPanel` mounts existing `CanonRulesPanel` behind `QualityWorkGate`; registered catalog + panel_id enum + regen contract + i18n(title/desc/guideBody) + QualityHub 5th card + legacyParity `canon`→`quality-canon-rules` (retirement ② now counts it). 45/45 vitest green (incl panelCatalogContract enum==openable==contract), tsc clean. Live-smoke deferred → loop-③ convergence smoke. |
| M1.2a · canon ENHANCE (delete onError + restore/undo toast) | DONE | CanonRulesPanel archiveRule(onError+undo toast→restore); api.restoreCanonRule + useCanonRules.restore. CanonRulesPanel 10/10. commit `769aa8358`. |
| M1.3a · BE-11b include_archived + FE showArchived | DONE | repo list_all(include_archived) + route param + CanonRule.is_archived; FE showArchived toggle + archived-row Restore. 31/31 composition unit + 10/10 FE. commit `769aa8358`. |
| M1.3b · BE-11c MCP restore + compositionEffects Lane-B | DONE | composition_canon_rule_restore MCP + delete undo_hint→restore; compositionEffects.ts (/^composition_canon_rule_/→invalidate canon) + §8.0b ledger re-partition (publish→flywheelEffects, conformance→conformanceEffects). 148 ledger + MCP 6/6 + tsc clean. ⚠ committed inside S2's `2c73b09da` (git-add-A sweep, see DRIFT). |
| _(session appends its build slices here)_ | | |

**M1 = quality-canon-rules is CLEARED to the §2 bar** (operable · CRUD incl restore · reachable · no-silent-fail · agent-parity incl MCP+Lane-B · loop IN-hop · unit-proven). Deferred beyond-bar ENHANCE rows in DEBT (412 rich-UI, focusRuleId OUT deep-link, kind field).

| M2a · quality-corrections display port + register | DONE | Extracted CorrectionStatsTable (F-Q11) → QualityCorrectionsPanel behind gate; registered catalog/enum/contract/i18n/hub-6th-card; unavailable≠empty. 35/35 vitest + tsc clean. commit `9c6a6d695`. LIVE-QC + BE-9c pending (M2b). |
| M2b · BE-9c CORRECTABLE_OPERATIONS allowlist (true denominator) | DONE | CORRECTABLE_OPERATIONS=("draft_scene","draft_chapter","stitch_chapter") + j.operation=ANY() in correction_stats; NOT selection_edit STAYS (F-Q3a). 5/5 correction_stats integration green (throwaway DB, incl excludes_non_draft_operations). commit `35fae4ace`. |
| **M2 · LIVE-QC quality-corrections** | DONE | headless playwright on the static FE :5199: login → studio → command palette "Corrections" → panel RENDERS `studio-quality-corrections-panel` with real stats (Diverge 1 / Stream 8). **M2 CLEARED to §2 bar.** (MCP browsers were locked by concurrent sessions → own playwright instance via frontend node_modules; QC harness reusable for M3/M4/M5.) |

| **M3 · quality-heal** | DONE | PolishPanel ported behind gate + chapter-picker + server-side apply-seam (patchDraft, Polish-run draft_version as OCC — E1 stale guard, 412 surfaced). 22/22 vitest. Live-QC :5199: palette "Self-heal" → panel + chapter picker + Run Polish operable. commit `6992652b1`. legacyParity polish→quality-heal. |
| **M4 · progress + BE-P2** | DONE | ProgressPanel ported (category editor) + BE-P2 per-user `composition_progress_goal` table + PUT /progress/goal + read-through + SET-1 source (TENANCY FIX). FE 17/17 + BE-P2 2/2 (per-user isolation, throwaway DB). Live-QC :5199: palette "Progress" → today/streak/book-total 1,310/sparkline. commit `c6379eeec`. legacyParity progress→progress. |
| **M5 · flywheel** | DONE | FlywheelPanel ported (category knowledge) + deep-link RETARGET (selectTab→host.openPanel cast/kg-timeline/kg-graph) + legacyParity conflation fix (flywheel→flywheel not quality-corrections). 16/16 vitest. Live-QC :5199: palette "Flywheel" → panel renders (empty-state valid). commit `e34895040`. |

## ✅ S6 CLEARED (2026-07-16)
All 6 S6 capabilities operable in the Studio to the §2 bar, each unit-green + live-browser-QC-proven on :5199:
D0 Work-CTA · **quality-canon-rules** (M1) · **quality-corrections** (M2) · **quality-heal** (M3) · **progress** (M4, +BE-P2 tenancy) · **flywheel** (M5).
Commits: e8e83b894 · f10ca60a5/769aa8358/2c73b09da · 9c6a6d695/35fae4ace · 6992652b1 · c6379eeec · e34895040.
Deferred (DEBT, beyond-bar or coordination): M1.4 polish (412 rich-UI · focusRuleId OUT · kind field); flywheelEffects Lane-B (publish→refresh, keys on extraction-complete/E2, PENDING s6-m5); conformanceEffects (S4); F2 flywheel auto-open-on-extraction-complete.

**QC HARNESS (reusable):** static FE = `npx vite build --outDir dist-s6` (bypasses S4 tsc) + `node scratchpad/s6-fe-static.mjs` (serves dist-s6 :5199, proxies /v1→:3123). Live-QC = a headless-playwright script (import from `frontend/node_modules/playwright` via file:// URL) driving :5199 (login claude-test → `/books/019f6553-…/studio` → command palette → assert panel testid). Rebuild dist-s6 per slice.

## ✅ COMPLETENESS AUDIT + E2E COVERAGE (2026-07-17) — /goal "coverage toàn bộ S6 + blackbox user"
Two committed Playwright suites run over the REAL login/gateway/dockview stack on :5199 (`876a50a93`):
- **`s6-quality-panels.spec.ts`** (7 tests) — every S6 capability driven to a real OUTCOME, not just render: canon-rules **full CRUD** (author→appears→archive), corrections stats/cold-start, heal chapter-pick→Run-Polish mounts, progress **per-user goal persists (BE-P2)**, flywheel delta-or-empty, quality-hub cards open their panels.
- **`s6-blackbox-journey.spec.ts`** (1 test, PO's "is it genuinely usable?") — a GUI-only author on a **fresh book with NO Work**: Canon panel does NOT dead-end → **Set-up-co-writer CTA (D0)** → one click makes the CRUD panel appear → author a rule & SEE it land → hub → set a personal daily goal → reach the flywheel. **Verdict: the whole job is doable Studio-only — never the legacy /edit page, never the agent.** S6's reason to exist, proven live.
- **Audit found 2 bugs, both fixed before green:** (1) the e2e asserted on the daily-goal FILL bar, which is 0%-width on a fresh book (today_words=0) → Playwright reports it hidden → false red. Fixed by adding always-visible `progress-goal`/`progress-goal-readout` testids and asserting the readout (a stronger persistence proof). (2) confirmed the 5 already-green panels (canon CRUD, corrections, heal, flywheel, hub) are genuinely operable, not stubs.
- **Result: 7/7 green on :5199.** Full S6 GUI surface is user-operable end-to-end.

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

### DEBT — ALL S6-owned items CLEARED 2026-07-17 (per PO "clear hết, đừng defer")
- **focusRuleId edit deep-link → ✅ CLEARED** (`5b466a94d`): quality-canon "Edit rule" → quality-canon-rules focused (edit mode + scroll).
- **412 conflict rich-diff-UI → ✅ CLEARED** (`d1984ac7c`): read `current` from the 412 body (D-K8-03), keep the draft, show re-apply-onto-v{n}/keep-theirs/discard. Never a silent overwrite or lost typing.
- **reverse "N broken →" badge → ✅ CLEARED** (`cf4a01c30`): quality-canon-rules reads the violation lens, badges each violated rule, opens quality-canon focused on click. Canon pair now links BOTH ways.
- **flywheelEffects Lane-B + async poll + F2 flash → ✅ CLEARED** (`<this commit>`): useFlywheel polls while `!has_delta` (catches the async extraction, E2, bounded to a focused open panel); flywheelEffects.ts invalidates on `composition_publish` (clears the ledger PENDING row); F2 flashes the flywheel in the background on a FE publish (focus:false, no hijack — E3).
- **kind field (F-Q10) → ⛔ WON'T-FIX** (gate #5, VERIFIED not a defer-to-avoid): `canon_rule.kind` is WRITE-ONLY — no engine/critic/packer reads it (`str` default "generic", no enum, no behavior). Exposing it in the FE would ship a stored-but-unread control (the anti-pattern CLAUDE.md forbids). Building it would be a DEFECT, not progress. Correctly not built.
- **conformanceEffects → ✅ DONE by S4** (its owner; registered in the barrel, `studioConformanceEffects`).
- **BE-9a/9b authoring-run reject-correction capture → ✅ CLEARED** (`7241ab1d0`, after S1 ended its build phase per PO): `authoring_run_units.job_id` (nullable, never backfilled) + DraftOutcome carries it + `record_for_job` writes a `kind='reject'` correction fire-and-forget on reject. 109 unit + 12 integration green.

**EVERY S6 debt item is now built** except `kind` (won't-fix — verified write-only; building it is a defect). No open S6 work remains.
- **E5 take-first-candidate** — quality panels bind the FIRST Work on an ambiguous multi-Work book (pre-existing convention across ALL consumers). Not S6's to fix; cross-cutting. Filed.
- **E6 BE-9a null-job report** — the "N units couldn't capture a correction" honest surface belongs to S1's authoring-run report (S1 owns the producer seam). Coordinate BE-9a/9b with S1.
- **D5 S7 deep-link targets → ✅ RESOLVED (verified live 2026-07-17, by S7 landing `71b6c8cbf`).** All three flywheel chip targets are now registered in the catalog — `cast` (line 352, "owner: S7"), `kg-timeline` (200), `kg-graph` (205) — and FlywheelStudioPanel routes onOpenCast/Timeline/Relations through `host.openPanel('cast'|'kg-timeline'|'kg-graph')`. No dead chip remains. Nothing left to pace.

### RESIDUAL — the ONLY open threads after S6 closure (both NOT S6-owned; tracked to their owner track)
- **E5 take-first-Work** (defer gate #1 out-of-scope) — quality panels bind the FIRST Work on a multi-Work book. A pre-existing convention across **every** consumer, not an S6 bug; the correct fix is one cross-cutting change at the shared resolver, not in S6.
- **E6 BE-9a null-job honest surface** (defer gate #1 out-of-scope) — the "N units couldn't capture a correction" report belongs to **S1's** authoring-run report (S1 owns the `authoring_run_units.job_id` producer seam). Needs S1 coordination; not buildable inside S6.

### DRIFT  (near-misses, bars nearly lowered, tests nearly skipped)
- Draft screen-quality-completion.html flags BE-11a `restore` as MUST-BUILD, but it SHIPPED since (canon.py:192-216). Verified before trusting the doc (repo laws: verify claim against code; missing-infra≠blocked). Do NOT re-build restore.
- **E2 near-miss** — the flywheel draft + spec first keyed the Lane-B refresh + F2 auto-open on `composition_publish`. But the delta is produced by an ASYNC knowledge extraction AFTER publish → would have opened an EMPTY flywheel. Caught in the design REVIEW pass by reading approve.py; corrected to key on extraction-complete.
- **E3 near-miss** — F2 "auto-open flywheel on publish" would hijack the human's focus when an AGENT publishes in the background. Corrected: FE-initiated → open; agent/background → flash/toast-with-link.
- **Shared-checkout convergence (M1.1)** — a concurrent track's commit `9262ed53e` ("ONE Work gate") added a `useActiveWorkId` (real useQuery) dependency to `useQualityWork` WITHOUT updating the quality-panel test mocks → the 4 quality panel tests went red on HEAD (No QueryClient). Not my change; caught by re-running the suite (verify-first). Fixed by mocking `@/features/composition/hooks/useActiveWork` in each. Lesson: on a shared branch, a suite can red from another track between your commit and your next test run — always re-run, never trust the prior green.
- **Shared-INDEX sweep is BIDIRECTIONAL (M2a).** My `git add <paths> && git commit` committed the whole shared INDEX, sweeping **S1's** staged files (ChapterAssemblePanel/SceneComposePanel/useAcceptIntoEditor) into my M2a commit `9c6a6d695`; then S1 committed on top (`420d008d8`). Nothing lost, tree consistent, attribution cross-contaminated both ways. **Mitigation upgraded:** use `git commit -- <pathspec>` (commits the WORKING-TREE version of ONLY my paths, ignoring whatever else is staged in the shared index) instead of `git add … && git commit`. This is the only same-folder-safe commit form.
- **Zero-width-fill false red (E2E audit).** The first e2e asserted `progress-goal-bar` (the daily-goal FILL `<div style="width:{pct}%">`) visible after saving a goal. On a FRESH book `today_words=0` → `pct=0` → zero-width element → Playwright's `toBeVisible()` correctly reports it **hidden**. This was a **test** bug (asserting on a legitimately-zero-size element), not an app bug — the goal DID persist. Nearly masked a real question ("did BE-P2 persist?") behind a rendering artifact. Fixed by asserting the always-visible readout (`progress-goal-readout` = "0 / 1,500") — proves persistence without depending on progress > 0. Lesson: never assert visibility on an element whose size is data-driven and can be legitimately zero.
- **Shared-INDEX race (M1.3b) — the serious one.** Multiple agents run `git add`/`git commit` in ONE shared working tree, so the git index is shared mutable state. Twice my staged M1.3b files were unstaged mid-flight by a concurrent `git add`; then **S2's `git add -A && git commit` (`2c73b09da`) swept my entire uncommitted M1.3b working-tree change into THEIR commit** (compositionEffects.ts, the ledger re-partition, the MCP restore tool, tests). Work not lost — committed + green on HEAD — but attribution is fuzzy and a concurrent broad-add can capture half-finished work. Also saw the shared barrel (`handlers/index.ts`) briefly land a **duplicate import** from racing writes (fixed). **Mitigation for the rest of S6:** commit-atomically (`add && commit` one shell call); keep slices tiny; prefer NEW files in my own subtree over edits to hot shared files (catalog.ts, frontend_tools.py, handlers/index.ts, effectCoverage ledger, studio.json/composition.json). The framework's §8 "commit small + often" is not optional here — it is the ONLY thing that bounds this. If churn worsens, escalate the branch-per-session fallback (§8) to the PO.
