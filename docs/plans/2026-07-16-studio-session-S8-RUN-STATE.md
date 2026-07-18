# Studio Session S8 — Translation — RUN-STATE

> Anchor for the 8-session Writing-Studio completeness build. **Re-read this file FIRST after any
> compaction**, then `git log --oneline -15`, then continue at the first non-DONE slice.
> Framework: docs/plans/2026-07-16-studio-completeness-8-session-orchestration.md (read §2 the bar, §4 your charter, §5 the rules).

## COMMITMENT
S8 is DONE when: translation repair (spec 29) is operable — coverage, targets, drift; the language SSOT enforced — each to the §2 production-ready bar (operable · CRUD · reachable ·
no-silent-fail · agent-parity · loop-connected · live-browser-proven · i18n+responsive · scale).

## SCOPE
- **Persona / files:** features/translation
- **Panels:** translation-repair
- **Seam / note:** OWNS D-4 (contracts/languages.contract.json) + D-1 (the Vietnamese->vi rekey — PO-GATED, dry-run first, DO NOT execute unattended).

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
| A0 · verify spec-29 defects against HEAD (no rebuild) | DONE | T1/T2/T4/T8 all still live in TranslationTab.tsx HEAD (lines 284-297/271/251-260/300-305); FE registry LANGUAGE_REGISTRY/TRANSLATION_TARGETS exists; NO Python languages.py, NO contracts/languages.contract.json |
| A1 · matrix operable — T1 (header Translate… CTA/D1) + T8 (preselect+lang/D6) + T2 (one-row-per-chapter/D3-D5) | DONE | commit 7901f04a9; 6 new effect-tests (TranslationTab.matrix.test.tsx) green; 69 translation tests no-regress; tsc clean both files |
| A2 · no-wedge — T4+T10 (typed error+Retry/D9) + T5 (modal abort/timeout/seeded/D7-D8) | DONE | commit 9a6ca4037; shared TranslationErrorState+classify+withTimeout; 4 errors + 4 wedge + 6 unit tests; 73 translation tests green; tsc clean |
| — PHASE A COMPLETE (reported bugs T1/T2/T4/T5/T8/T10 + D1/D3-D9) — unit-green, FE-only, live-smoke deferred to §2 sweep | DONE | commits 7901f04a9 + 9a6ca4037 |
| B  · degraded-mode / no-silent-fail — T6, S1, S2, S4, S5, S6, S8 | DONE | commits 32f7b04b2 + b257f8893; +ChapterTranslationsPanel.errors + StepProgress.error + segmentDrilldown S2; 61 tests green |
| B-tail · T7, D10-A, S3, S7, S9, S12, D11 | DONE | T7+D10-A covered (DECISIONS); S3/S7/S9/S12/D11 BUILT (no-defer) commit 87338d13b; 31 tests + dockablePanelHygiene 207 green |
| C1 · language SSOT — D-4 languages.contract.json + Python languages.py mirror + parity + MCP enum + FE consolidate 3 inputs (D13) | DONE | commit 5edd3a06f; SSOT contract + FE parity(2) + Python parity(6 incl MCP Literal) + write-validation at job-create/settings/prefs/MCP-update + LanguagePicker `codes` prop; 55 BE + 16 FE green; tsc clean. S7 BatchTranslateDialog = DEBT (glossary subtree). Route-level 400/201 → §2 live-smoke |
| C2 · grant-gate — book-service my_grant_level + FE disable-with-reason (T9/D10-C) | DONE | commit a85a1ee1a; ANTI-LAZINESS: book-service getBookByID ALREADY returns access_level per-caller (server.go:987) + gateway passthrough → FE-only. Book type += access_level; TranslationTab canEdit gate + view-only banner (disable-with-reason). +2 tests; 31 book-tabs green; tsc clean |
| §2 · i18n 18-locale parity | DONE | commit ca254bdea; node scripts/i18n-parity.cjs clean for translation.json + glossaryTranslate.json across all 17 locales |
| §2 · agent-parity / loop / responsive / scale / User Guide | PARTIAL | agent-parity: translationEffects Lane-B handler EXISTS (S11 resume/retry-via-confirm gap is INFO/scoped); scale: D4 pagination; User Guide: `translation` panel has guideBodyKey. Responsive/mobile + proven = the live-smoke below |
| §2 · live-browser smoke both states | DONE | rebuilt translation-service (build was transient-pip-flaky; clean retry) + FE; commit 09a2d76ed. 5 Playwright e2e green on live :5199 (T1/T2/D1/T8/T4); C1 API: 'Vietnamese'→400, 'VI'→'vi', 'zh_CN'→'zh-CN'; docker stop translation-service → gateway 500 in 5s (no hang) |
| D-1 · Vietnamese→vi backfill | EXECUTED + verified | PO ruled append+newest+keep-vi; atomic tx w/ snapshot + pre/post asserts; 0 Vietnamese remaining across 3 tables; collision chapter → vi v1/v2(active)/v3. D-TRANSL-LANG-BACKFILL CLEARED |

## REGISTERS  (append as you go — an empty DRIFT log at the end is dishonest, not clean)
### DECISIONS
- 2026-07-16 · PO: **own & fix `pages/book-tabs/TranslationTab.tsx` + `TranslateModal.tsx` in-place** — outside features/translation subtree but studio wraps them, no other session owns pages/book-tabs, loop-③ Studio-only needs them working. Root-cause fix, not a re-wrap.
- 2026-07-16 · PO: **session drives A+B+C full** to the §2 bar (no-silent-fail=B, language-SSOT/D-4=C are in-scope for the bar).
- 2026-07-16 · PO: **D-1 backfill = dry-run + STOP** for PO review of which-version-wins; do NOT execute unattended.
- 2026-07-16 · spec 29 (2026-07-10) adopted as S8's detailed design (live-verified; more authoritative than 31-38). "translation-repair" panel name is a misnomer — the work repairs the EXISTING registered `translation` panel in place, no new stub panel.
- 2026-07-17 · **T7 (add new target language) — covered, not a separate build.** A1 gave TranslateModal a full language `<select>` (all LANGUAGE_NAMES today; TRANSLATION_TARGETS after C1). VersionSidebar's `onRetranslate` + the "no versions yet → Translate now" CTA both open that modal, so adding a *new* target language is one click. C1's picker-consolidation tightens this to the closed registry.
- 2026-07-17 · **D10 phase-A (readable EDIT-grant 403 toast) — covered.** TranslateModal.submitJob already `toast.error(err.message || …)` on a createJob failure, so a 403 surfaces readably rather than silently. C2 does the phase-C disable-with-reason.
### PARKED  (blocker -> defer row + continue)
_(empty — D11 was built, not parked; PO directive: no defers.)_
### DEBT
_(empty — S3/S7/S9/S12 all built in commit 87338d13b per the no-defer directive.)_
### RECENTLY CLEARED
- **D11** (dock-id dedup, EditorPanel/S1 subtree) · **S3** (settings models load error) · **S7** (BatchTranslateDialog picker) · **S9** (ConfirmNameDialog → FormDialog) · **S12** (GlossaryTranslateWizard View-glossary nav) — all built 2026-07-17, commit 87338d13b. Crossed into settings/glossary/studio subtrees per PO "no defers"; changes are additive and each other session's tests stay green.
### COMPLETENESS AUDIT (cold-start adversarial review, 2026-07-17)
Reviewer found 5 real issues (rest verified sound); ALL fixed (swept into commit c1581e07b via the shared index — see DRIFT):
- MED-1 settings/TranslationTab default-lang → LanguagePicker(TRANSLATION_TARGETS) (was a stale 8-code literal bypassing D13).
- MED-2 _retranslate_dirty_core normalizes target_language BEFORE the seed lookup (raw 'VI' → misleading 409).
- LOW-1 filter-all-deselected → distinct "All languages filtered out" state (was "no translations yet").
- LOW-2 MCP update_settings undo hint omits a legacy target_language the enum would reject.
- LOW-3 put_preferences dead-code `or` cleaned.
### BLACKBOX-USER USABILITY (real app, author role, 2026-07-17)
VERDICT: STRONG POSITIVE — genuinely operable, no dead ends. docs/plans/2026-07-17-studio-S8-blackbox-usability-report.md + 6 screenshots (frontend/s8-journey/). Journey spec + 5 e2e specs green on live :5199.
### DRIFT  (near-misses, bars nearly lowered, tests nearly skipped)
- **SHARED-INDEX SWEEP** (2026-07-17): my audit-fix `git add`+commit collided with a concurrent session's commit on the shared checkout — my 5 audit fixes + all_filtered i18n got absorbed into commit c1581e07b (a plan-forge S3 commit) instead of my own. Code is SAFE + verified in HEAD (git show HEAD:… confirms each fix), but misattributed. Lesson (matches memory [git-index-may-carry-prestaged]): on a shared checkout, stage+commit atomically and fast, or a parallel session's commit sweeps your staged changes. Did NOT rewrite history (destructive on a shared branch).
- A1 T1-unscoped test first clicked the CTA while chapters still loading (disabled → no-op) → false-green risk; caught it, made the test wait for load. The lesson: assert against the *enabled* control, not just its presence.
- B S6/S8 committed without a dedicated test (LOW display/logging fixes). ~~Near-miss~~ **CLEARED 2026-07-17**: SplitCompareView.test.tsx (S6 original-pane fallback) + useConfirmName console.error assertion (S8).
- B-tail S12 (View-glossary navigate) ~~shipped without a dedicated navigate-assertion test~~ **CLEARED 2026-07-17**: GlossaryTranslateWizard.navigate.test.tsx drives config→confirm→progress→results via auto-firing step mocks and asserts navigate('/books/:id/glossary').
- **ALL S8 DEBT/DRIFT test gaps cleared** (2026-07-17, goal "clear all defers"): the 3 LOW test-coverage items above are now covered; the only remaining DRIFT entry is the shared-index-sweep caveat (a history-attribution note, not a code gap).
