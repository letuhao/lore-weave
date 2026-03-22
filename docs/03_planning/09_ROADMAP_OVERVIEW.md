# LoreWeave Roadmap Overview (Phase-Based)

## Document Metadata
- Document ID: LW-09
- Version: 1.7.0
- Status: Approved
- Owner: Product Manager + Solution Architect
- Last Updated: 2026-03-22
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Phase roadmap with frontend-backend module delivery principles.

## Change History
| Version | Date | Change | Author |
|---|---|---|---|
| 1.7.0 | 2026-03-22 | Status governance update: approved Module 04 planning pack `56`–`67` by Decision Authority | Assistant |
| 1.6.0 | 2026-03-22 | Added Phase 2 Module 04 (raw translation pipeline) planning checkpoint and doc references 56-67 | Assistant |
| 1.5.0 | 2026-03-21 | Status governance update: Module 03 planning checkpoint docs `44`-`55` approved by Decision Authority | Assistant |
| 1.4.0 | 2026-03-21 | Added Phase 1 Module 03 (provider registry + model billing) planning checkpoint and doc references 44-55 | Assistant |
| 1.3.0 | 2026-03-21 | Added Phase 1 Module 02 (Books & sharing) planning checkpoint and doc references 24–35 | Assistant |
| 1.2.0 | 2026-03-21 | Added Phase 1 Module 01 identity planning checkpoint and pack references | Assistant |
| 1.1.0 | 2026-03-21 | Added governance metadata header and migrated to numbered docs structure | Assistant |
| 1.0.0 | 2026-03-21 | Baseline content established before docs reorganization | Assistant |

## Purpose

This roadmap provides a high-level phase sequence for LoreWeave planning and execution, aligned with current strategy, organization, scope boundaries, and RACI governance.

## Assumptions

- Scope follows `03_V1_BOUNDARIES.md`.
- Governance and accountability follow `02_PROJECT_ORGANIZATION.md` and `06_OPERATING_RACI.md`.
- Roadmap is phase-oriented and not tied to fixed calendar dates at this stage.
- Outputs are planning outcomes and readiness criteria, not code-level deliverables.
- Working model follows `05_WORKING_MODEL_SCRUMBAN.md` (1-manager + 1-executor).
- Frontend-backend planning and delivery progress in parallel by module.

## Cross-Phase Delivery Principle

Each phase must define at least one **frontend-backend vertical module output**.
No phase is considered complete unless its module output is acceptance-ready at governance level.

## Phase Flow

```mermaid
flowchart LR
  phase0[Phase0AlignmentAndGovernance] --> phase1[Phase1PlatformCoreFoundation]
  phase1 --> phase2[Phase2WorkflowAndRagFoundation]
  phase2 --> phase3[Phase3KnowledgeServices]
  phase3 --> phase4[Phase4ContinuationAndCanonSafety]
  phase4 --> phase5[Phase5HardeningAndScaleReadiness]
```

## Phase 0: Alignment and Governance

### Objective
Create a single operating baseline for scope, ownership, and decision control.

### Key Outcomes
- Scope and boundary confirmation.
- Governance meeting cadence and decision log process active.
- Contract and change-control policy active.

### Module Output
- Governance module: approved Scrumban operating model and module-slicing guardrails adopted across core artifacts.

### Major Dependencies
- Approved organization model.
- Approved RACI responsibilities.

### Completion Criteria
- Governance operating model is documented and adopted.
- Role accountability conflicts are resolved.
- Scope and dependency baseline is signed off.

## Phase 1: Platform Core Foundation

### Objective
Establish planning readiness for identity, book lifecycle, sharing, and discovery domains.

### Key Outcomes
- Platform-core domain ownership finalized.
- Core policy model for ownership and visibility finalized.
- Platform-core quality gates defined.

### Module Output
- Identity and book lifecycle module package with synchronized UI flow expectations, API contracts, and governance acceptance criteria.

### Phase 1 Module 01 Checkpoint (Identity Foundation)
- Module 01 planning pack must be complete before implementation:
  - `11_PHASE1_MODULE01_IDENTITY_EXECUTION_PACK.md`
  - `12_MODULE01_API_CONTRACT_DRAFT.md`
  - `13_MODULE01_FRONTEND_FLOW_SPEC.md`
  - `14_MODULE01_ACCEPTANCE_TEST_PLAN.md`
  - `15_MODULE01_RISK_DEPENDENCY_ROLLOUT.md`
- Contract-first rule applies: API draft is frozen before frontend flow freeze.
- Module closure requires Decision Authority gate outcome based on DoR/DoD evidence.

### Phase 1 Module 02 Checkpoint (Books & sharing)

- **Objective:** Second vertical slice for platform core: owned books, visibility/share policy, public catalog browse — see `03_V1_BOUNDARIES.md` (Platform Core).
- **Planning pack (Approved):**
  - `24_PHASE1_MODULE02_BOOKS_SHARING_EXECUTION_PACK.md`
  - `25_MODULE02_API_CONTRACT_DRAFT.md` and OpenAPI under `contracts/api/books/v1/`, `contracts/api/sharing/v1/`, `contracts/api/catalog/v1/`
  - `26_MODULE02_FRONTEND_FLOW_SPEC.md`
  - `27_MODULE02_ACCEPTANCE_TEST_PLAN.md`
  - `28_MODULE02_RISK_DEPENDENCY_ROLLOUT.md`
  - `29_GOVERNANCE_BOARD_REVIEW_CHECKLIST_MODULE02.md`
- **Deep-design + readiness (Draft):** `30_MODULE02_MICROSERVICE_SOURCE_STRUCTURE_AMENDMENT.md` through `35_MODULE02_IMPLEMENTATION_READINESS_GATE.md`.
- **Prerequisite:** Module 01 identity operational baseline (access tokens); contract-first and gate `35` GO before M02 implementation start.

### Phase 1 Module 03 Checkpoint (Provider registry + model billing)

- **Objective:** Third vertical slice for platform core control plane: user BYOK provider registration, platform-managed model catalog, usage metering, and billing policy (`tier quota + credits overage`).
- **Planning pack (Draft):**
  - `44_PHASE1_MODULE03_PROVIDER_REGISTRY_EXECUTION_PACK.md`
  - `45_MODULE03_API_CONTRACT_DRAFT.md`
  - `46_MODULE03_FRONTEND_FLOW_SPEC.md`
  - `47_MODULE03_ACCEPTANCE_TEST_PLAN.md`
  - `48_MODULE03_RISK_DEPENDENCY_ROLLOUT.md`
  - `49_GOVERNANCE_BOARD_REVIEW_CHECKLIST_MODULE03.md`
- **Deep-design + readiness (Approved):**
  - `50_MODULE03_MICROSERVICE_SOURCE_STRUCTURE_AMENDMENT.md`
  - `51_MODULE03_BACKEND_DETAILED_DESIGN.md`
  - `52_MODULE03_FRONTEND_DETAILED_DESIGN.md`
  - `53_MODULE03_UI_UX_WIREFRAME_SPEC.md`
  - `54_MODULE03_INTEGRATION_SEQUENCE_DIAGRAMS.md`
  - `55_MODULE03_IMPLEMENTATION_READINESS_GATE.md`
- **Prerequisite:** Module 01 auth baseline and Module 02 ownership/visibility baselines are available; contract-first and gate `55` GO before M03 implementation start.

### Major Dependencies
- Phase 0 governance baseline.
- Contract governance baseline.

### Completion Criteria
- Platform-core planning package is approved.
- Core domain dependencies and handoffs are explicit.
- Release-readiness criteria for platform core are approved.

### Phase 2 Module 04 Checkpoint (Raw translation pipeline)

- **Objective:** First Phase 2 vertical slice: per-user and per-book translation settings, async translation job lifecycle, chapter result storage — uses M03 provider gateway as the only model invocation path.
- **Planning pack (Approved):**
  - `56_PHASE1_MODULE04_RAW_TRANSLATION_EXECUTION_PACK.md`
  - `57_MODULE04_API_CONTRACT_DRAFT.md`
  - `58_MODULE04_FRONTEND_FLOW_SPEC.md`
  - `59_MODULE04_ACCEPTANCE_TEST_PLAN.md`
  - `60_MODULE04_RISK_DEPENDENCY_ROLLOUT.md`
  - `61_GOVERNANCE_BOARD_REVIEW_CHECKLIST_MODULE04.md`
- **Deep-design + readiness (Approved):**
  - `62_MODULE04_MICROSERVICE_SOURCE_STRUCTURE_AMENDMENT.md`
  - `63_MODULE04_BACKEND_DETAILED_DESIGN.md`
  - `64_MODULE04_FRONTEND_DETAILED_DESIGN.md`
  - `65_MODULE04_UI_UX_WIREFRAME_SPEC.md`
  - `66_MODULE04_INTEGRATION_SEQUENCE_DIAGRAMS.md`
  - `67_MODULE04_IMPLEMENTATION_READINESS_GATE.md`
- **Prerequisite:** M01 auth, M02 book ownership, M03 provider-registry-service operational; gate `67` GO before M04 implementation start.

## Phase 2: Workflow and RAG Foundation

### Objective
Establish planning readiness for workflow lifecycle and evidence-grounded retrieval.

### Key Outcomes
- Workflow lifecycle governance model finalized.
- RAG ingestion and retrieval governance model finalized.
- Evidence/provenance requirements baseline approved.

### Module Output
- Job orchestration and evidence query module package with aligned frontend-backend journey and contract governance.

### Major Dependencies
- Platform-core planning baseline from Phase 1.
- Contract and event governance maturity.

### Completion Criteria
- Workflow and retrieval operating model is approved.
- Domain handoffs between platform-core and AI workflow are explicit.
- Phase-level quality and reliability gates are defined.

## Phase 3: Knowledge Services

### Objective
Establish planning readiness for story wiki and grounded QA/extraction service operations.

### Key Outcomes
- Story knowledge governance model finalized.
- QA/extraction quality policy and evidence expectations defined.
- Review process for knowledge quality and consistency defined.

### Module Output
- Story wiki and QA module package with integrated UI/API acceptance policy and ownership boundaries.

### Major Dependencies
- Workflow and RAG baseline from Phase 2.
- QA governance baseline.

### Completion Criteria
- Knowledge service operating policies are approved.
- Quality review and confidence governance are documented.
- Ownership and escalation paths are clear.

## Phase 4: Continuation and Canon Safety

### Objective
Establish planning readiness for continuation workflows with canon safety controls.

### Key Outcomes
- Continuation mode policy baseline defined.
- Canon-safety governance and exception handling model defined.
- Review criteria for creative-vs-grounded outputs defined.

### Module Output
- Continuation workflow module package with paired frontend-backend interaction baseline and canon-safety gates.

### Major Dependencies
- Story knowledge service baseline from Phase 3.
- Governance and risk controls from earlier phases.

### Completion Criteria
- Continuation policy model is approved.
- Canon-safety review and escalation process is operationally clear.
- Acceptance criteria for continuation quality are defined.

## Phase 5: Hardening and Scale Readiness

### Objective
Establish operating readiness for reliability, risk control, and scale-oriented execution.

### Key Outcomes
- Reliability and incident governance model strengthened.
- Phase-level KPI monitoring and reporting routine stabilized.
- Scale-readiness checkpoints and transition criteria defined.

### Module Output
- Operational readiness module package covering release observability surfaces (UI), frontend-backend reliability controls, and governance sign-off rules.

### Major Dependencies
- Prior phase completion criteria met.
- Active SRE, QA, and governance reporting cadence.

### Completion Criteria
- SLO/KPI baseline governance is active.
- Release and incident review loops are stable.
- Scale-readiness and next-stage transition criteria are approved.

## Cross-Phase Success Signals

- Governance decisions are made within defined SLAs.
- Role ownership remains unambiguous across phases.
- Quality and risk gates are consistently enforced.
- Planning artifacts remain synchronized across strategy, organization, and RACI documents.

## Exclusions

- This roadmap does not prescribe coding tasks or implementation-level technical detail.
- This roadmap does not lock calendar dates; scheduling will be added after planning stability is confirmed.




