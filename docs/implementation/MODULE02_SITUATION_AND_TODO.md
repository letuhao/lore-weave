# Module 02 — implementation situation and todo backlog

## Document Metadata

- Document ID: LW-IMPL-M02-01
- Version: 1.1.0
- Status: Active
- Owner: Execution Authority + Tech Lead + QA Lead (consulted)
- Last Updated: 2026-03-21
- Approved By: Pending
- Approved Date: N/A
- Summary: Current implementation situation for Module 02 and a practical todo list for future execution waves.

## Change History


| Version | Date       | Change                                                                 | Author    |
| ------- | ---------- | ---------------------------------------------------------------------- | --------- |
| 1.1.0   | 2026-03-21 | Added explicit not-implemented inventory (GC, Gitea, and deferred scope) | Assistant |
| 1.0.0   | 2026-03-21 | Initial situation and todo backlog for M02                             | Assistant |


## Current Situation (Module 02)

- Core M02 execution has started and multiple approved planning deltas (`36`-`43`) are already reflected in codebase.
- Current validation posture is still **smoke-testing centric**; this is useful for quick confidence but is **not** a full acceptance closure.
- Unit tests were expanded for several newly improved areas, but there are still higher-level gaps (cross-service behavior, edge-case matrices, and stronger evidence packaging).
- Some requested capabilities are only partially complete or intentionally deferred, and need follow-up in future implementation waves.

## Testing Reality Check

- **What exists now:** smoke checks and selected unit tests for backend helpers, API client behavior, and key reader pages.
- **What is not complete yet:** full acceptance execution pack according to M02 acceptance supplements and formal GO/NO-GO evidence dossier.
- **Implication:** current state is suitable for iterative dev progress, not a final production-quality closeout.

## Todo Backlog (Future Plan)


| Area                  | Todo item                                                                                                                            | Priority | Target phase        |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | -------- | ------------------- |
| QA / acceptance       | Execute full M02 acceptance matrix with evidence artifacts (API + UI + negative cases)                                               | P0       | Next execution wave |
| QA / integration      | Add end-to-end integration tests for cross-service reader flows (book/sharing/catalog consistency)                                   | P0       | Next execution wave |
| Security / gateway    | Harden and verify raw-download auth behavior under edge conditions (expired token, wrong owner, lifecycle transitions)               | P0       | Next execution wave |
| Backend behavior      | Expand handler-level unit tests (not only helpers) for newly added list/detail chapter reader endpoints                              | P1       | Next execution wave |
| Frontend quality      | Add robust responsive regression tests for desktop/tablet/mobile layout states                                                       | P1       | Next execution wave |
| Frontend UX           | Deepen owner workflow tests (language picker combinations, create-book cover upload failures, chapter paging/filter/sort edge cases) | P1       | Next execution wave |
| Editor experience     | Continue Lexical feature hardening (history UX details, long-content performance, corner-case input handling)                        | P1       | Future wave         |
| Operational readiness | Build formal release checklist and rollback playbook aligned with readiness gate requirements                                        | P1       | Pre-release wave    |


## Deferred / Not Fully Implemented Yet

- Final acceptance evidence pack is not finished.
- Some advanced/non-critical improvements are intentionally deferred to future waves.
- Production-grade rollout governance (formal sign-off chain and release artifact completeness) remains pending.

## Explicitly Not Implemented In This Wave (Inventory)

The following items are intentionally out of scope for the current implementation wave and should be treated as pending backlog:

| Item | Current status | Planned direction |
| ---- | -------------- | ----------------- |
| Physical garbage collector (GC) for `purge_pending` books/chapters and object cleanup | **Not implemented** in current wave (API currently marks lifecycle only) | Add dedicated background GC worker with audit/retry/error handling |
| Gitea integration for chapter version control | **Not implemented** (MVP keeps revisions in Postgres) | Introduce ADR + integration design for Git-backed history model |
| Full acceptance execution and formal evidence pack | **Not completed** (still smoke + selected unit tests) | Execute complete acceptance matrix and produce artifact bundle |
| Handler-level deep unit/integration coverage for all newly added reader endpoints | **Partially implemented** | Expand test matrix (positive/negative/edge) for book/sharing/catalog |
| Non-text chapter formats (`pdf`, `docx`, `html`, image OCR paths) | **Not implemented** (MVP remains txt-only) | Future MIME extension with validation + conversion strategy |
| AI translate workflow for multilingual chapter generation | **Not implemented** (manual per-language chapter rows only) | Future translate pipeline after product/architecture approval |
| AI-generated summary / cover | **Not implemented** | Future AI feature wave with quality and moderation controls |
| Paid storage tiers / billing | **Not implemented** (single free quota policy) | Future monetization wave |
| Dedicated `storage-service` split from `book-service` | **Not implemented** (book-service still owns storage client in MVP) | Re-evaluate service split when boundary pressure justifies it |
| Advanced revision UX (true diff viewer, compare modes, richer restore workflows) | **Partially implemented** | Incremental UX wave after stability pass |
| Production rollout hardening package (SRE, security sign-off, release governance completeness) | **Not completed** | Pre-release gate wave |

## References

- `docs/03_planning/36_MODULE02_UI_UX_IMPROVEMENT_IMPLEMENTATION_PLAN.md`
- `docs/03_planning/37_MODULE02_ADR_UI_UX_WAVE_TECHNICAL_DECISIONS.md`
- `docs/03_planning/38_MODULE02_API_CONTRACT_UI_UX_WAVE_AMENDMENT.md`
- `docs/03_planning/39_MODULE02_UI_UX_WAVE_CHANGE_IMPACT_AND_COMPATIBILITY.md`
- `docs/03_planning/40_MODULE02_ACCEPTANCE_TEST_PLAN_UI_UX_WAVE_SUPPLEMENT.md`
- `docs/03_planning/41_MODULE02_RISK_ROLLOUT_GOVERNANCE_UI_UX_WAVE_UPDATE.md`
- `docs/03_planning/42_MODULE02_UI_UX_WAVE_IMPLEMENTATION_READINESS_GATE.md`
- `docs/03_planning/43_MODULE02_RESPONSIVE_DESKTOP_SCALING_ADDENDUM.md`

