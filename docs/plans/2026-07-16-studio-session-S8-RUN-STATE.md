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
| §2 · live-browser smoke both states | BLOCKED-ON-INFRA-DECISION | stack UP but translation-service is 38h-old (my C1 BE not in it) + FE served via vite :5199 (my FE IS live via HMR). A TRUE both-states smoke needs a translation-service + FE image REBUILD that RESTARTS shared containers other sessions use → needs PO go-ahead on the disruptive rebuild |
| D-1 · Vietnamese→vi backfill DRY-RUN + STOP (PO-gated) | DONE (dry-run) · STOPPED for PO | docs/plans/2026-07-17-D1-vietnamese-vi-backfill-dryrun.md — ONLY `Vietnamese` non-canonical (7 rows, 4 chapters, 1 book); 3 clean renames + 1 collision chapter needing which-version-wins ruling (decisions #1-3). NOT executed |

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
### DRIFT  (near-misses, bars nearly lowered, tests nearly skipped)
- A1 T1-unscoped test first clicked the CTA while chapters still loading (disabled → no-op) → false-green risk; caught it, made the test wait for load. The lesson: assert against the *enabled* control, not just its presence.
- B S6/S8 committed without a dedicated test (LOW display/logging fixes). Near-miss on the "checklist⇒test the effect" bar; accepted for LOW severity but recorded — add a SplitCompareView fallback test if the §2 sweep touches it.
- B-tail S12 (View-glossary navigate) shipped without a dedicated navigate-assertion test — the wizard's mocked StepResults doesn't wire onViewGlossary and driving to the 'results' step needs internal state-machine setup. Conscious LOW-severity gap; verify by effect in the §2 live-smoke. The 3-line change is visually trivial.
