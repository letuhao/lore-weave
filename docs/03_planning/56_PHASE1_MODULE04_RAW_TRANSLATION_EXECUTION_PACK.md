# LoreWeave Phase 1 Module 04 Raw Translation Pipeline Execution Pack

## Document Metadata

- Document ID: LW-M04-56
- Version: 0.1.0
- Status: Approved
- Owner: Product Manager + Solution Architect
- Last Updated: 2026-03-22
- Approved By: Decision Authority
- Approved Date: 2026-03-22
- Summary: Execution governance pack for Module 04: raw chapter translation pipeline using provider gateway, per-user and per-book translation settings, prompt template management, and async job tracking.

## Change History

| Version | Date       | Change                          | Author    |
| ------- | ---------- | ------------------------------- | --------- |
| 0.1.0   | 2026-03-22 | Initial Module 04 execution charter | Assistant |

## 1) Module Charter

### Module Name

Module 04 — Raw Translation Pipeline (Phase 2 Workflow Foundation entry point)

### Objective

Deliver the first AI workflow vertical for LoreWeave:

- users can trigger translation of one or more chapters within a book,
- translation is executed through the M03 provider gateway (adapter-only invocation path),
- per-user translation preferences (model, target language, prompts) are saved and reusable,
- per-book settings can override user defaults,
- translation results are stored per chapter per job and viewable in the UI.

### Positioning in Roadmap

Module 04 is the **Phase 2 entry point** (Workflow Foundation). It intentionally omits:
- RAG retrieval (no context from indexed knowledge),
- `workflow-job-service` (job lifecycle managed internally by `translation-service` for MVP),
- write-back of translated text to `book-service` chapters (results remain in `translation-service` DB).

These are planned for later modules in Phase 2 and Phase 3.

### MVP Policy Lock

- Translation engine: `translation-service` (Python/FastAPI), new service at port 8087.
- Job execution model: **asynchronous** — job created and returned immediately; chapters processed sequentially via `BackgroundTasks`.
- Model invocation: must route through `POST /v1/model-registry/invoke` on `provider-registry-service` — direct provider SDK calls are prohibited.
- Service-to-gateway auth: translation-service mints short-lived user-identity JWTs (TTL 300 s) using shared `JWT_SECRET` to authenticate on behalf of the job owner when calling invoke.
- Chapter source: draft body from `GET /internal/books/{book_id}/chapters/{chapter_id}` (no auth required on internal route).
- Billing: handled automatically inside `provider-registry-service` invoke endpoint — translation-service does not call `usage-billing-service` directly.
- Prompt defaults: platform-provided system prompt and user prompt template; both are user-editable.

## 2) Scope Definition

### In Scope (MVP)

- `translation-service`: new Python/FastAPI service.
  - Per-user translation preferences (target language, model, system prompt, user prompt template).
  - Per-book translation settings (override user defaults).
  - Translation job lifecycle: `pending → running → completed | partial | failed`.
  - Chapter translation results stored per chapter per job.
  - Startup recovery sweep for stale running jobs.
- Gateway registration: `/v1/translation/*` routed through `api-gateway-bff`.
- Frontend:
  - `/m04/translation-settings` — user-level preference page.
  - `/books/:bookId/translation` — per-book settings, chapter selection, translate trigger, job progress, result viewer.
  - `TranslateButton` component with inline progress polling.
  - `ModelSelector` component reusing M03 user model and platform model lists.
  - `PromptEditor` component for system + user prompt templates.
  - `ChapterTranslationPanel` component for viewing per-chapter results.

### Out of Scope (this wave)

- RAG context injection into translation prompts.
- `workflow-job-service` as separate job lifecycle authority.
- Write-back of translations to `book-service` as new language-variant chapters.
- Parallel chapter translation (sequential only in MVP).
- Translation quality scoring or automated evaluation.
- Retry UI controls (users can re-trigger a new job manually).
- Bulk export of translation results.

## 3) Accountability Map

| Work item | Responsible | Accountable | Consulted | Informed |
| --- | --- | --- | --- | --- |
| Service design and contract | SA | SA | BE lead | PM |
| Prompt defaults and UX flow | PM | PM | SA, FE lead | Decision Authority |
| Backend implementation | BE lead | Execution Authority | SA | PM |
| Frontend implementation | FE lead | Execution Authority | PM, SA | QA lead |
| Acceptance test definition | QA lead | QA lead | PM, SA | Decision Authority |
| Rollout and risk controls | SRE | SRE | SA, QA | PM |
| Final readiness decision | Execution Authority | Decision Authority | PM, SA, QA, SRE | Governance Board |

## 4) DoR and DoD

### Definition of Ready (DoR)

- Module 04 contract draft is published and reviewed.
- Frontend flow spec is complete and aligned with contract.
- Risk and dependency doc identifies M03 dependency constraints.
- Service ownership and source structure are documented.
- JWT minting strategy for service-to-gateway auth is explicitly documented.

### Definition of Done (DoD)

- Planning pack `56`–`67` is internally consistent.
- Catalog and roadmap include Module 04 references.
- MVP policy lock (async jobs, adapter-only invocation, JWT minting) is reflected in all M04 docs.
- Readiness gate `67` is complete and decision-ready.

## 5) Governance Gates

| Gate | Trigger | Required evidence | Approver |
| --- | --- | --- | --- |
| Gate A — Contract freeze | `57` complete | Endpoint set, schema set, error taxonomy | SA |
| Gate B — UX flow freeze | `58`, `64`, `65` complete | User journeys, states, validation | PM |
| Gate C — Acceptance freeze | `59` complete | AT matrix, pass criteria, evidence format | QA lead |
| Gate D — Risk and rollout freeze | `60` complete | Risk controls, rollback, escalation | SRE |
| Gate E — Integration freeze | `66` complete | Cross-service sequence and failure paths | SA + BE lead |
| Gate F — Implementation readiness | `67` complete | GO/NO-GO record | Decision Authority |

## 6) Dependencies

- **M01**: auth-service JWT (bearer auth for all `/v1/translation/*` endpoints).
- **M03**: `provider-registry-service` invoke endpoint as execution gateway; `usage-billing-service` receives billing records automatically from invoke.
- `book-service` internal chapter endpoint: `GET /internal/books/{book_id}/chapters/{chapter_id}` (no auth).
- `api-gateway-bff`: new route registration for `/v1/translation/*`.

## 7) Downstream Pack (required before coding)

- `57_MODULE04_API_CONTRACT_DRAFT.md`
- `58_MODULE04_FRONTEND_FLOW_SPEC.md`
- `59_MODULE04_ACCEPTANCE_TEST_PLAN.md`
- `60_MODULE04_RISK_DEPENDENCY_ROLLOUT.md`
- `61_GOVERNANCE_BOARD_REVIEW_CHECKLIST_MODULE04.md`
- `62_MODULE04_MICROSERVICE_SOURCE_STRUCTURE_AMENDMENT.md`
- `63_MODULE04_BACKEND_DETAILED_DESIGN.md`
- `64_MODULE04_FRONTEND_DETAILED_DESIGN.md`
- `65_MODULE04_UI_UX_WIREFRAME_SPEC.md`
- `66_MODULE04_INTEGRATION_SEQUENCE_DIAGRAMS.md`
- `67_MODULE04_IMPLEMENTATION_READINESS_GATE.md`
