# Studio Session S3 — PlanForge compiler — RUN-STATE

> Anchor for the 8-session Writing-Studio completeness build. **Re-read this file FIRST after any
> compaction**, then `git log --oneline -15`, then continue at the first non-DONE slice.
> Framework: docs/plans/2026-07-16-studio-completeness-8-session-orchestration.md (read §2 the bar, §4 your charter, §5 the rules).

## COMMITMENT
S3 is DONE when: a GUI-only user can drive a plan run through all 7 passes incl. the checkpoints — each to the §2 production-ready bar (operable · CRUD · reachable ·
no-silent-fail · agent-parity · loop-connected · live-browser-proven · i18n+responsive · scale).

## SCOPE
- **Persona / files:** features/plan-forge, features/studio/panels/Plan*
- **Panels:** plan-passes
- **Seam / note:** Proposer already grounded (O-1/G2); the pass rail is the gap.

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

## REFERENCE (already exists — transcribe, do NOT rewrite. Framework §0: source is truth.)
- Pass model (BE, built): docs/specs/2026-07-01-writing-studio/27_planforge_v2_compiler.md
- FE design: docs/specs/2026-07-01-writing-studio/35_planforge_studio.md
- HTML acceptance target (rail + repair): design-drafts/screens/studio/screen-planforge-pass-rail.html
- Wave plan: docs/plans/2026-07-13-studio-wave-5-planforge.md
- **ADJUDICATION (INSTRUCTIONS, not suggestions — this file wins over the wave plan):**
  docs/plans/studio-adjudication/wave-5-decisions.md (47 items · 44 DECIDED · 1 deferred). Re-read
  the relevant Q before each slice; each carries a builder-ready recipe + evidence.

## SLICE BOARD  (status: TODO / DOING / DONE — DONE requires an EVIDENCE string, not a checkbox)
| slice | status | evidence (test count / live-smoke line / commit sha) |
|---|---|---|
| S3-A1 · audit current surface (role-play user) | DONE | 7-pass BE fully built+tested; FE=0; only path today = MCP `plan_run_pass`/`plan_review_checkpoint` or raw REST. api.ts has zero pass/checkpoint methods; no component renders the ledger; planEffects on PENDING allowlist (wave-5). No route reads pass artifact CONTENT ⇒ checkpoint review is blind. Confirmed via grep + Read (this session). |
| S3-A2 · PORT/ENHANCE/BUILD decisions | DONE | see DECISIONS below |
| M4-PRE · AddModelCta studio branch (Q-35-X1) — MUST land before any Pass Rail code | DONE | already landed at HEAD: AddModelCta.tsx:83-96 studio branch via useOptionalStudioHost + followStudioLink (resolves /settings/providers → openPanel); AddModelCta.test.tsx drives the real chain + `queryByRole('link')` null guard. Verified against HEAD, not rebuilt (framework S0 verify-first). |
| BE-3 · GET .../artifacts/{artifact_id} read-route + FE api + PlanArtifact type (Q-35-BE3) | DONE | svc.get_artifact + router GET .../artifacts/{artifact_id} (VIEW, one-404 H13) + FE api.getArtifact + type PlanArtifactDetail. test_plan_forge_router.py 11 passed (added 200 exact-keys / 404 unknown / 404 cross-book≠403). tsc --noEmit clean. Uncommitted — pending per-slice checkpoint. |
| BE-21 · _serialize_run passes package_artifact_id to derive_view (Q-35-BE21) | TODO | |
| BE-22 · fix phantom `plan_bootstrap_seed` msg → re-run cast pass (Q-35-BE22) | TODO | |
| BE-2 · POST .../autofix route (mirror handoff_autofix) (Q-35-BE2) | TODO | |
| B0 · reserve `plan-passes` in catalog/enum/contract/i18n/guideBody (enum +1 == plan-passes; Q-35-PANEL-COUNT) | TODO | |
| FE-1 · json-editor read-only viewer for plan artifacts (Q-35-FE1) | TODO | |
| M4 · Pass Rail panel: ledger + run-pass + freshness/cursor/blocked_at | TODO | |
| M4-CP · blocking-checkpoint review (view artifact via BE-3 → edit → approve/hold) | TODO | |
| planEffects · Lane-B handler + remove planEffects from PENDING_FILES (agent parity §2.5) | TODO | |
| REPAIR · `planner` repair strip (refine/interpret · staleness · failed re-run · relink · autofix) — NO new id | TODO | |
| I18N · 18-locale keys for both surfaces; responsive + 10k-scale | TODO | |
| SMOKE · live-browser: GUI-only drives 1 run through 7 passes + 2 checkpoints; `/review-impl` per panel close | TODO | |

## REGISTERS  (append as you go — an empty DRIFT log at the end is dishonest, not clean)
### DECISIONS
- **D-S3-SCOPE (2026-07-16):** PORT/ENHANCE/BUILD — KEEP `planner` (propose→compile→bootstrap works
  in GUI); BUILD `plan-passes` Pass Rail (the whole gap); BUILD repair as affordances INSIDE `planner`
  + BE `/autofix`; BUILD BE-3 artifact read-route. Only agent/MCP could drive passes before this.
- **D-S3-REPAIR-NO-NEW-ID (2026-07-16):** repair is **NOT** a separate panel. Sealed by HTML draft
  line 10 ("planner repair (no new id)") + Q-35-PANEL-COUNT ("enum +1 whose sole new member is
  `plan-passes`"). PO confirmed aligning to source in this session (initially picked a separate
  panel; corrected once the sealed adjudication was surfaced). Enum grows by exactly one id.
- **D-S3-NO-NEW-SPEC (2026-07-16):** no new spec/HTML draft — 27 + 35 + the pass-rail HTML + wave-5
  adjudication are complete. Detailed design = this RUN-STATE transcribing them. CLARIFY was done at
  source (wave-5-decisions.md); not re-run.

### PARKED  (blocker -> defer row + continue)
- **D-PLANFORGE-PROPOSE-BLIND** (pre-existing, SESSION_HANDOFF.md:102, gate #2): propose ignores an
  existing manuscript. Wave-5 must NOT touch the engine (Q-35-OQ5). Only ship the honesty copy string
  in the planner new-run form ("Proposed from this braindump only. Existing chapters are not read.").

### DEBT
### DRIFT  (near-misses, bars nearly lowered, tests nearly skipped)
- Near-miss (caught): almost built a separate `planner-repair` panel — my CLARIFY question framed it
  as an option, contradicting the sealed "no new id". Caught by re-reading the source before coding,
  not from memory. This is exactly the rule "re-read a sealed decision; don't re-litigate it."
