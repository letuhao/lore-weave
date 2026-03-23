# Module 04 — implementation situation and todo backlog

## Document Metadata

- Document ID: LW-IMPL-M04-01
- Version: 1.0.0
- Status: Active
- Owner: Execution Authority + Tech Lead + QA Lead (consulted)
- Last Updated: 2026-03-23
- Approved By: Pending
- Approved Date: N/A
- Summary: Current implementation situation for Module 04 (raw translation pipeline) and a practical todo list for future execution waves.

## Change History

| Version | Date       | Change                                             | Author    |
| ------- | ---------- | -------------------------------------------------- | --------- |
| 1.0.0   | 2026-03-23 | Initial situation and todo backlog for M04         | Assistant |

## Current Situation (Module 04)

- The `translation-service` backend is fully coded: 4 routers (settings, jobs, versions, coverage), 15+ endpoints, 6 database tables (DDL V1–V3), 5 worker modules (chapter orchestrator, streaming session translator, chunk splitter, content extractor, coordinator), and RabbitMQ broker integration.
- Per-user and per-book translation preferences (model, language, prompts, compact model, chunk size, timeout) are implemented including LW-73 compact-prompt customisation fields (V3 schema).
- Async job lifecycle (pending → running → completed / partial / failed) with startup recovery sweep is implemented.
- Chapter-level translation results, version management, active-version tracking, and book-level coverage matrix are implemented.
- Provider invocation routes exclusively through the M03 provider-registry-service adapter (`POST /v1/model-registry/invoke`).
- Frontend is near-complete: `BookTranslationPage`, `ChapterTranslationsPage`, 22 translation components (workflow, status display, advanced settings, version sidebar, split-compare view, jobs/settings drawers), and full `translationApi` / `versionsApi` client modules.
- 16 backend test files and 9 frontend test/spec files exist covering handlers, workers, crypto helpers, API clients, and selected UI components.
- Current validation posture is **smoke-testing only**; formal acceptance matrix (`M04-AT-01` through `M04-AT-21`) has not been executed.
- Several job-lifecycle, billing-integration, and security invariants require integration-level evidence to close the acceptance gate.

## Testing Reality Check

- **What exists now:** smoke checks, unit tests for handler validation/auth guards, worker logic (chapter scheduling, chunk splitting, compact memo, content extraction, startup recovery), API client mocking, and selected component renders.
- **What is not complete yet:** full acceptance matrix execution, integration traces proving all provider invocations route through M03 and bypass is blocked, book-service internal-endpoint schema compatibility verification, formal evidence pack for QA sign-off.
- **Implication:** current state is suitable for iterative development progress, not formal acceptance closure or production release gate.

## Todo Backlog (Future Plan)

| Area | Todo item | Priority | Target phase |
| --- | --- | --- | --- |
| QA / acceptance | Execute full M04 acceptance matrix M04-AT-01 through M04-AT-21 with captured evidence (API traces, UI screenshots, DB checks where required) | P0 | Next execution wave |
| QA / smoke | Create M04-specific E2E smoke test script (user prefs → book settings → create job → poll completion → view chapter result in UI), modelled on `scripts/smoke-module01.ps1` | P0 | Next execution wave |
| Integration / book-service | Verify `POST /internal/books/{id}/projection` in book-service returns the expected schema (chapter text + metadata) for M04 content extractor — capture API trace as evidence | P0 | Next execution wave |
| Security / routing | Add integration test proving all model invocations route through M03 adapter and direct-SDK bypass attempts are blocked (M04-AT-16) | P0 | Next execution wave |
| Security / access | Verify non-owner requests to job detail and chapter result return 403 with no payload leakage (M04-AT-14, M04-AT-15) | P0 | Next execution wave |
| Billing / correctness | Integration test confirming `usage_log_id` is recorded per completed chapter and billing rejection on exhausted quota propagates as `partial` job status (M04-AT-11, M04-AT-17) | P0 | Next execution wave |
| Job lifecycle | Integration trace for full status arc (pending → running → completed) and startup recovery sweep on stale running jobs (M04-AT-09, M04-AT-18) | P0 | Next execution wave |
| QA / acceptance | Produce reconciliation sample: at least one E2E trace (create job → chunk log → version row → active version) per evidence pack requirements | P0 | Next execution wave |
| Frontend / coverage | Add unit/render tests for `BookTranslationPage` and `ChapterTranslationsPage` (no page-level test files exist yet) | P1 | Next execution wave |
| Frontend / coverage | Add render tests for `TranslateModal`, `SettingsDrawer`, `JobsDrawer`, and `VersionSidebar` (currently no test files for these components) | P1 | Next execution wave |
| Backend / observability | Implement structured metrics per design doc `63` §8: job throughput counters, chunk error rates, compact memo trigger counts, provider invoke latency histograms | P1 | Future wave |
| Backend / reliability | Add dead-letter queue (DLQ) handling for permanently-failed RabbitMQ messages; currently permanent errors are acked and logged but not routed to a DLQ for manual review | P1 | Future wave |
| Operational readiness | Build formal release checklist and rollback playbook aligned with readiness gate `67` requirements | P1 | Pre-release wave |
| Frontend / UX | Implement re-translate confirmation dialog that surfaces cost estimate before creating a new job over an existing completed version | P2 | Future wave |
| Backend / performance | Add streaming (SSE / WebSocket) progress events from worker to frontend per design doc `66` sequence diagrams; current implementation polls job status | P2 | Future wave |

## Deferred / Not Fully Implemented Yet

- Full acceptance evidence pack is not produced.
- Formal GO/NO-GO decision record in gate `67` has not been filled (outcome is still `Pending`).
- M04-specific smoke test script does not yet exist (only M01 smoke script present).
- Book-service internal endpoint schema compatibility has not been verified via a live integration trace.
- Dead-letter queue routing for permanently failed translation messages is not implemented.
- Real-time streaming progress events (SSE / WebSocket push from worker) are not implemented; frontend polls instead.

## Explicitly Not Implemented In This Wave (Inventory)

| Item | Current status | Planned direction |
| ---- | -------------- | ----------------- |
| Formal acceptance evidence pack (API traces, UI screenshots, DB audit, reconciliation sample) | **Not produced** (smoke only) | Execute AT matrix and produce artifact bundle per `59` §4 |
| M04-specific E2E smoke test script | **Not implemented** (M01 smoke only) | Create PowerShell or shell script covering full translate workflow |
| Book-service internal endpoint compatibility verification | **Not verified** (assumed compatible) | Capture live API trace from `content_extractor` → book-service `/internal` route |
| Integration test for M03 anti-bypass routing invariant (M04 context) | **Not implemented** (unit guards only) | Add integration trace proving all invocations route through provider-registry |
| Dead-letter queue for permanent worker failures | **Not implemented** (ack + log only) | Add DLQ routing in broker and ops runbook for manual replay |
| Real-time progress streaming (SSE / WebSocket) | **Not implemented** (frontend polls) | Add SSE endpoint in translation-service and `useTranslationEvents` hook per `66` §3 |
| Page-level frontend tests for `BookTranslationPage`, `ChapterTranslationsPage` | **Not implemented** | Add React Testing Library render + interaction tests |
| Component tests for `TranslateModal`, `SettingsDrawer`, `JobsDrawer`, `VersionSidebar` | **Not implemented** | Add render and interaction tests |
| Observability metrics (Prometheus/OTEL counters) | **Not implemented** | Add alongside pre-release hardening per `63` §8 |
| Cost-estimate confirmation dialog on re-translate | **Not implemented** (no cost estimate shown before job creation) | Future UX wave aligned with billing surface work |
| Chapter-level translation export (EPUB/DOCX output) | **Not implemented** (out of scope per `56` §3) | Future export wave |
| Multi-language batch job (single job, multiple target languages) | **Not implemented** (one language per job) | Future platform wave |
| Provider auto-retry with exponential backoff at worker level | **Partial** (transient vs. permanent error distinction exists; no backoff scheduler) | Future reliability wave |

## References

- `docs/03_planning/56_PHASE1_MODULE04_RAW_TRANSLATION_EXECUTION_PACK.md`
- `docs/03_planning/57_MODULE04_API_CONTRACT_DRAFT.md`
- `docs/03_planning/58_MODULE04_FRONTEND_FLOW_SPEC.md`
- `docs/03_planning/59_MODULE04_ACCEPTANCE_TEST_PLAN.md`
- `docs/03_planning/60_MODULE04_RISK_DEPENDENCY_ROLLOUT.md`
- `docs/03_planning/61_GOVERNANCE_BOARD_REVIEW_CHECKLIST_MODULE04.md`
- `docs/03_planning/62_MODULE04_MICROSERVICE_SOURCE_STRUCTURE_AMENDMENT.md`
- `docs/03_planning/63_MODULE04_BACKEND_DETAILED_DESIGN.md`
- `docs/03_planning/64_MODULE04_FRONTEND_DETAILED_DESIGN.md`
- `docs/03_planning/65_MODULE04_UI_UX_WIREFRAME_SPEC.md`
- `docs/03_planning/66_MODULE04_INTEGRATION_SEQUENCE_DIAGRAMS.md`
- `docs/03_planning/67_MODULE04_IMPLEMENTATION_READINESS_GATE.md`
