# LoreWeave Phase 1 Module 03 Provider Registry and Model Billing Execution Pack

## Document Metadata

- Document ID: LW-M03-44
- Version: 0.3.0
- Status: Approved
- Owner: Product Manager + Solution Architect
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Execution governance pack for Module 03: user/provider model registration, platform-managed models, usage metering, and billing via subscription tier quota plus credits overage.

## Change History

| Version | Date       | Change                                | Author    |
| ------- | ---------- | ------------------------------------- | --------- |
| 0.3.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 0.2.0   | 2026-03-21 | Added strict provider-gateway policy and full encrypted interaction-log policy with owner-only detail decryption UX baseline | Assistant |
| 0.1.0   | 2026-03-21 | Initial Module 03 execution charter   | Assistant |

## 1) Module Charter

### Module Name

Module 03 - Provider Registry and Model Billing (Platform Core extension)

### Objective

Deliver a unified AI provider control plane where:

- users can register their own providers and models (BYOK),
- admins can register and price platform-managed models,
- the platform records request-level usage and cost data,
- billing policy enforces subscription-tier quota first, then credits overage.

### MVP Policy Lock

- Supported providers in this module: `ollama`, `lm_studio`, `openai`, `anthropic`.
- Platform model charging policy: **tier quota + credits overage**.
- User provider credentials policy: **store server-side encrypted at rest**.
- Interaction logging policy: **store full input/output payloads encrypted at rest** and expose detail view to owner only.
- Invocation security policy: **all AI runtime calls must route through provider gateway/adapters**; direct provider calls from feature services are prohibited.

## 2) Market-Informed Design Baseline

Observed common patterns in current AI platforms:

- Split model sources:
  - user BYOK inventory,
  - platform managed inventory.
- Track request-level accounting as first-class data:
  - prompt/input tokens,
  - completion/output tokens,
  - optional cached/reasoning tokens,
  - cost and latency.
- Provide both dashboard and export-ready usage views.
- Normalize heterogeneous provider error/rate-limit behavior into one API shape.

Module 03 encodes these patterns as product requirements, while adapting to LoreWeave governance and service boundaries.

## 3) Scope Definition

### In Scope (MVP)

- User provider credential registration (OpenAI, Anthropic, Ollama endpoint, LM Studio endpoint).
- User custom model registration mapped to provider credentials.
- Admin platform model catalog management:
  - enable/disable model,
  - provider mapping,
  - pricing metadata and quota category mapping.
- Metering and billing logs for every model invocation:
  - account id, model id, provider, token counts, cost.
- Detailed interaction logs for traceability:
  - full `input_payload` and `output_payload` persisted encrypted at rest,
  - owner-only decrypted detail access with access-audit records.
- Quota and overage policy:
  - consume included subscription quota first,
  - fallback to credits when quota is exceeded and credits remain.
- Usage visibility for users and admins:
  - list/filter usage entries,
  - aggregate by time window.
- Strict provider gateway boundary:
  - all model invocations pass through provider-registry adapter layer for normalization, metering hooks, and policy checks.

### Out of Scope (this wave)

- Physical garbage collector for historical billing rows.
- Full enterprise invoicing and tax reporting.
- Provider auto-provisioning with cloud marketplaces.
- Model benchmark automation and auto-repricing.
- Gitea-backed version control for prompts/model configs.

## 4) Accountability Map

| Work item | Responsible | Accountable | Consulted | Informed |
| --- | --- | --- | --- | --- |
| Provider policy and scope | PM, SA | PM | Security, QA | Decision Authority |
| Contract draft and error model | SA | SA | BE lead, QA | PM |
| Billing and metering acceptance | QA lead | QA lead | PM, SA, FE lead | Decision Authority |
| Rollout and incident controls | SRE | SRE | SA, QA | PM |
| Final readiness decision | Execution Authority | Decision Authority | PM, SA, QA, SRE | Governance Board |

## 5) DoR and DoD

### Definition of Ready (DoR)

- Module 03 contract draft is published and reviewed.
- Frontend flow spec and acceptance matrix are complete.
- Risk and dependency doc identifies security, financial, and outage controls.
- Service ownership and runtime boundaries are explicitly documented.
- Strict provider boundary and encrypted interaction-log access model are explicitly documented.

### Definition of Done (DoD)

- Planning pack `44`-`55` is internally consistent.
- Catalog and roadmap include Module 03 references.
- MVP policy lock (tier+credits, encrypted key storage) is reflected in all Module 03 docs.
- Full encrypted interaction-log behavior and owner-only detailed view are reflected in all Module 03 docs.
- Readiness gate `55` is complete and decision-ready.

## 6) Governance Gates

| Gate | Trigger | Required evidence | Approver |
| --- | --- | --- | --- |
| Gate A - Contract freeze | `45` complete | Endpoint set, schema set, error taxonomy | SA |
| Gate B - UX flow freeze | `46`, `52`, `53` complete | User/admin journeys, states, validation | PM |
| Gate C - Acceptance freeze | `47` complete | AT matrix, pass criteria, evidence format | QA lead |
| Gate D - Risk and rollout freeze | `48` complete | Risk controls, rollback, escalation | SRE |
| Gate E - Integration freeze | `54` complete | Cross-service sequence and failure paths | SA + BE lead |
| Gate F - Implementation readiness | `55` complete | GO/NO-GO record | Decision Authority |

## 7) Dependencies

- Module 01 identity baseline for auth/session and role checks.
- Module 02 ownership and lifecycle patterns for model resource ownership consistency.
- Foundation governance docs: `03`, `04`, `06`, and `17`/`30`.

## 8) Downstream Pack (required before coding)

- `45_MODULE03_API_CONTRACT_DRAFT.md`
- `46_MODULE03_FRONTEND_FLOW_SPEC.md`
- `47_MODULE03_ACCEPTANCE_TEST_PLAN.md`
- `48_MODULE03_RISK_DEPENDENCY_ROLLOUT.md`
- `49_GOVERNANCE_BOARD_REVIEW_CHECKLIST_MODULE03.md`
- `50_MODULE03_MICROSERVICE_SOURCE_STRUCTURE_AMENDMENT.md`
- `51_MODULE03_BACKEND_DETAILED_DESIGN.md`
- `52_MODULE03_FRONTEND_DETAILED_DESIGN.md`
- `53_MODULE03_UI_UX_WIREFRAME_SPEC.md`
- `54_MODULE03_INTEGRATION_SEQUENCE_DIAGRAMS.md`
- `55_MODULE03_IMPLEMENTATION_READINESS_GATE.md`
