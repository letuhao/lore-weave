# LoreWeave Document Catalog and Reading Order

## Document Metadata

- Document ID: LW-00
- Version: 1.23.0
- Status: Approved
- Owner: Decision Authority + Execution Authority
- Last Updated: 2026-03-22
- Approved By: Governance Board
- Approved Date: 2026-03-21
- Summary: Entry point for documentation navigation, reading order, and migration mapping.

## Change History


| Version | Date       | Change                                                        | Author    |
| ------- | ---------- | ------------------------------------------------------------- | --------- |
| 1.23.0 | 2026-03-22 | Status governance update: approved Module 04 planning documents `56`–`67` by Decision Authority | Assistant |
| 1.22.0 | 2026-03-22 | Registered Module 04 planning pack `56`–`67` (raw translation pipeline — execution pack, API contract, frontend flow, AT plan, risk/rollout, governance checklist, microservice structure, backend design, frontend design, wireframe spec, integration sequences, readiness gate) | Assistant |
| 1.21.0 | 2026-03-22 | Registered `MODULE03_SITUATION_AND_TODO.md` (LW-IMPL-M03-01) — M03 smoke complete, implementation situation and todo backlog | Assistant |
| 1.20.0 | 2026-03-21 | Status governance update: approved Module 03 planning documents `44`-`55` by Decision Authority | Assistant |
| 1.19.0 | 2026-03-21 | Registered Module 03 planning pack `44`-`55` (provider registry, model billing, deep-design, readiness gate) and linked proposed contract domains for model registry/billing | Assistant |
| 1.18.0 | 2026-03-21 | Status governance update: approved Module 02 UI/UX planning documents `36`-`43` by Decision Authority | Assistant |
| 1.17.0 | 2026-03-21 | Registered Module 02 responsive desktop scaling addendum `43_MODULE02_RESPONSIVE_DESKTOP_SCALING_ADDENDUM.md` as planning extension for UI/UX wave `36`-`42` | Assistant |
| 1.16.0 | 2026-03-21 | Registered Module 02 UI/UX improve wave planning pack `37`-`42` (technical decisions, contract amendment, impact, acceptance supplement, risk/rollout update, readiness gate) | Assistant |
| 1.15.0 | 2026-03-21 | Registered docs-only Module 02 UI/UX improvement implementation plan `36_MODULE02_UI_UX_IMPROVEMENT_IMPLEMENTATION_PLAN.md` (planning artifact, no source-code execution) | Assistant |
| 1.14.0 | 2026-03-21 | M02 **recycle bin**: **`lifecycle_state`**, trash/restore/purge, **`GET /v1/books/trash`**; books OpenAPI **1.4.0**; sharing/catalog **1.2.1**; `25` **1.4.0** + cascade 24/26–29/31–33/35 | Assistant |
| 1.13.0 | 2026-03-21 | `30` §5: baseline **Postgres database per microservice** (book / sharing / catalog) | Assistant |
| 1.12.0 | 2026-03-21 | M02 multilingual: **`GET …/chapters`** query **`original_language`**, **`sort_order`**; books OpenAPI **1.3.0**; `25` §7; cascaded 24/26/27/29/31–33/35 | Assistant |
| 1.11.0 | 2026-03-21 | M02: **`original_language`** (book+chapter), chapter **draft + revision** APIs, Postgres VC (not Gitea); OpenAPI **v1.2.0**; planning 24–35 bumped | Assistant |
| 1.10.0 | 2026-03-21 | M02 docs expanded — chapters (txt MVP), cover, summary, object storage/quota; OpenAPI books/sharing/catalog v1.1.0 narrative aligned | Assistant |
| 1.9.0 | 2026-03-21 | Registered Phase 1 Module 02 planning pack (24–35, LW-M02-24..35) and contract paths `contracts/api/{books,sharing,catalog}/v1/` | Assistant |
| 1.8.2 | 2026-03-21 | Registered `MODULE01_DEFERRED_FOLLOWUPS.md` (LW-IMPL-M01-01); noted smoke vs formal acceptance | Assistant |
| 1.8.1 | 2026-03-21 | Noted LW-M01-23 Active: approved UI stack (Tailwind, shadcn/ui, RHF, zod) | Assistant |
| 1.8.0 | 2026-03-21 | Registered Module 01 GUI visual improvement plan (23, LW-M01-23) | Assistant |
| 1.7.1 | 2026-03-21 | Noted Module 01 implementation readiness gate (22) Approved with GO | Assistant |
| 1.7.0 | 2026-03-21 | Registered Module 01 implementation readiness gate document (22) | Assistant |
| 1.6.0 | 2026-03-21 | Added Module 01 monorepo governance note and authoritative document mapping | Assistant |
| 1.5.0 | 2026-03-21 | Added Module 01 deep-design planning references (17-21) | Assistant |
| 1.4.0 | 2026-03-21 | Added Phase 1 Module 01 planning pack references and reading path | Assistant |
| 1.3.0 | 2026-03-21 | Updated approval metadata to Approved with Governance Board sign-off | Assistant |
| 1.2.0   | 2026-03-21 | Standardized metadata policy for Last Updated date format     | Assistant |
| 1.1.0   | 2026-03-21 | Standardized metadata taxonomy for Status, Owner, Approved By | Assistant |
| 1.0.0   | 2026-03-21 | Initial catalog with global numbering and folder organization | Assistant |


## Purpose

This catalog is the single entry point for LoreWeave documentation.
Use it to:

- follow recommended reading order,
- understand each document purpose,
- locate files by domain folder,
- map old file names to new numbered file names.

## Metadata Taxonomy Standard

Use these values consistently in every document metadata block:

- `Status`:
  - `Draft`: in review, not approved yet
  - `Active`: approved and currently used
  - `Approved`: explicitly approved baseline artifact
  - `Superseded`: replaced by a newer document/version
- `Owner`:
  - use canonical role names (for example: `Product Manager`, `Solution Architect`, `Decision Authority`, `Execution Authority`)
  - for joint ownership, use `Role A + Role B`
- `Approved By`:
  - `Decision Authority`, `Governance Board`, or `Pending`
- `Approved Date`:
  - use `YYYY-MM-DD` in metadata headers
  - use `N/A` when `Approved By` is `Pending`
- `Last Updated`:
  - use `YYYY-MM-DD` in metadata headers
  - update this field whenever document content or metadata changes

## Metadata Compliance Checklist

- [ ] `Document ID` is present and matches the file's sequence.
- [ ] `Version` is incremented when content or metadata changes.
- [ ] `Status`, `Owner`, and `Approved By` use catalog taxonomy values.
- [ ] `Last Updated` and `Approved Date` follow date format policy (`YYYY-MM-DD` or `N/A` when pending).
- [ ] `Change History` includes a new entry for the current update.

## Quick-Start Reading Path

1. Platform context and scope foundation:
  - `01_PROJECT_OVERVIEW.md`
  - `02_PROJECT_ORGANIZATION.md`
  - `03_V1_BOUNDARIES.md`
  - `04_TECHSTACK_SERVICE_MATRIX.md`
2. Governance model and execution controls:
  - `05_WORKING_MODEL_SCRUMBAN.md`
  - `06_OPERATING_RACI.md`
  - `07_TASK_01_PROJECT_CHARTER_AND_SUCCESS_CRITERIA.md`
  - `08_PHASE_0_EXECUTION_PACK.md`
3. Planning artifacts:
  - `09_ROADMAP_OVERVIEW.md`
  - `10_BASIC_TASK_CHECKLIST.md`
4. Market context:
  - `11_LOREWEAVE_MARKET_ANALYSIS.md`
5. Phase 1 module planning pack:
  - `11_PHASE1_MODULE01_IDENTITY_EXECUTION_PACK.md`
  - `12_MODULE01_API_CONTRACT_DRAFT.md`
  - `13_MODULE01_FRONTEND_FLOW_SPEC.md`
  - `14_MODULE01_ACCEPTANCE_TEST_PLAN.md`
  - `15_MODULE01_RISK_DEPENDENCY_ROLLOUT.md`
6. Phase 1 module deep-design pack:
  - `17_MODULE01_MICROSERVICE_SOURCE_STRUCTURE.md`
  - `18_MODULE01_BACKEND_DETAILED_DESIGN.md`
  - `19_MODULE01_FRONTEND_DETAILED_DESIGN.md`
  - `20_MODULE01_UI_UX_WIREFRAME_SPEC.md`
  - `21_MODULE01_INTEGRATION_SEQUENCE_DIAGRAMS.md`
7. Phase 1 module implementation readiness (before code):
  - `22_MODULE01_IMPLEMENTATION_READINESS_GATE.md`
8. Phase 1 module UI improvement (post-baseline implementation plan):
  - `23_MODULE01_GUI_VISUAL_IMPROVEMENT_PLAN.md`
9. Module 01 implementation notes (runbook + deferred backlog):
  - `docs/implementation/MODULE01_LOCAL_DEV.md`
  - `docs/implementation/MODULE01_DEFERRED_FOLLOWUPS.md`
10. Phase 1 Module 02 — Books & sharing (planning pack **Draft**): book shell + **summary**, **cover** (object storage), **chapters** (`.txt` only MVP), **per-user quota**, sharing/catalog.
  - `24_PHASE1_MODULE02_BOOKS_SHARING_EXECUTION_PACK.md` through `29_GOVERNANCE_BOARD_REVIEW_CHECKLIST_MODULE02.md`
  - OpenAPI: `contracts/api/books/v1/`, `contracts/api/sharing/v1/`, `contracts/api/catalog/v1/`
11. Phase 1 Module 02 — deep-design + readiness gate (**Draft**): MinIO/S3 path, BE/FE tabs, sequences for upload/download.
  - `30_MODULE02_MICROSERVICE_SOURCE_STRUCTURE_AMENDMENT.md` through `35_MODULE02_IMPLEMENTATION_READINESS_GATE.md`
12. Phase 1 Module 02 — UI/UX improvement docs-only implementation plan (planning boundary: markdown-only).
  - `36_MODULE02_UI_UX_IMPROVEMENT_IMPLEMENTATION_PLAN.md`
13. Phase 1 Module 02 — UI/UX improve wave execution-planning pack (docs-only phase complete).
  - `37_MODULE02_ADR_UI_UX_WAVE_TECHNICAL_DECISIONS.md` through `42_MODULE02_UI_UX_WAVE_IMPLEMENTATION_READINESS_GATE.md`
14. Phase 1 Module 02 — responsive desktop scaling addendum (planning extension).
  - `43_MODULE02_RESPONSIVE_DESKTOP_SCALING_ADDENDUM.md`
15. Phase 1 Module 03 — provider registry + model billing planning pack (approved baseline).
  - `44_PHASE1_MODULE03_PROVIDER_REGISTRY_EXECUTION_PACK.md` through `49_GOVERNANCE_BOARD_REVIEW_CHECKLIST_MODULE03.md`
16. Phase 1 Module 03 — deep-design + readiness gate (approved baseline).
  - `50_MODULE03_MICROSERVICE_SOURCE_STRUCTURE_AMENDMENT.md` through `55_MODULE03_IMPLEMENTATION_READINESS_GATE.md`

## Folder Structure

- `docs/00_index/` - entrypoint and navigation
- `docs/01_foundation/` - platform foundation and boundaries
- `docs/02_governance/` - governance operating model and phase controls
- `docs/03_planning/` - roadmap and planning checklist
- `docs/04_analysis/` - market and external context

## Global Reading Order


| Seq | File                                                 | Folder          | Purpose                                                    |
| --- | ---------------------------------------------------- | --------------- | ---------------------------------------------------------- |
| 01  | `01_PROJECT_OVERVIEW.md`                             | `01_foundation` | Platform vision, architecture direction, and scope context |
| 02  | `02_PROJECT_ORGANIZATION.md`                         | `01_foundation` | Organizational and governance operating model              |
| 03  | `03_V1_BOUNDARIES.md`                                | `01_foundation` | In-scope/out-of-scope and V1 constraints                   |
| 04  | `04_TECHSTACK_SERVICE_MATRIX.md`                     | `01_foundation` | Service ownership and language/runtime assignment          |
| 05  | `05_WORKING_MODEL_SCRUMBAN.md`                       | `02_governance` | 1-manager + 1-executor execution model                     |
| 06  | `06_OPERATING_RACI.md`                               | `02_governance` | Accountability, decision rights, and escalation            |
| 07  | `07_TASK_01_PROJECT_CHARTER_AND_SUCCESS_CRITERIA.md` | `02_governance` | Charter and KPI baseline governance                        |
| 08  | `08_PHASE_0_EXECUTION_PACK.md`                       | `02_governance` | Phase 0 closure package and approval record                |
| 09  | `09_ROADMAP_OVERVIEW.md`                             | `03_planning`   | Phase roadmap and module-output expectations               |
| 10  | `10_BASIC_TASK_CHECKLIST.md`                         | `03_planning`   | Baseline planning checklist by workstream                  |
| 11  | `11_LOREWEAVE_MARKET_ANALYSIS.md`                    | `04_analysis`   | Market comparison and strategic context                    |

## Phase 1 Module Packs (Planning Series)

| Pack Seq | File | Folder | Purpose |
| --- | --- | --- | --- |
| M01-11 | `11_PHASE1_MODULE01_IDENTITY_EXECUTION_PACK.md` | `03_planning` | Module 01 charter, DoR/DoD, governance gates, and sign-off |
| M01-12 | `12_MODULE01_API_CONTRACT_DRAFT.md` | `03_planning` | Contract-first API baseline for identity flows |
| M01-13 | `13_MODULE01_FRONTEND_FLOW_SPEC.md` | `03_planning` | Frontend journeys, state model, validation, and API mapping |
| M01-14 | `14_MODULE01_ACCEPTANCE_TEST_PLAN.md` | `03_planning` | Acceptance matrix, pass criteria, and evidence checklist |
| M01-15 | `15_MODULE01_RISK_DEPENDENCY_ROLLOUT.md` | `03_planning` | Dependency graph, risk controls, rollout and rollback plan |

## Phase 1 Module 02 Packs (Books & sharing) — Draft baseline

| Pack Seq | File | Folder | Purpose |
| --- | --- | --- | --- |
| M02-24 | `24_PHASE1_MODULE02_BOOKS_SHARING_EXECUTION_PACK.md` | `03_planning` | Module 02 charter, DoR/DoD, gates |
| M02-25 | `25_MODULE02_API_CONTRACT_DRAFT.md` | `03_planning` | Contract narrative + links to OpenAPI |
| M02-26 | `26_MODULE02_FRONTEND_FLOW_SPEC.md` | `03_planning` | FE journeys and API mapping |
| M02-27 | `27_MODULE02_ACCEPTANCE_TEST_PLAN.md` | `03_planning` | Acceptance matrix M02-AT-* |
| M02-28 | `28_MODULE02_RISK_DEPENDENCY_ROLLOUT.md` | `03_planning` | Dependencies, risks, rollout |
| M02-29 | `29_GOVERNANCE_BOARD_REVIEW_CHECKLIST_MODULE02.md` | `03_planning` | Governance Board one-session checklist |

## Phase 1 Module 02 Deep-Design + Gate — Draft baseline

| Pack Seq | File | Folder | Purpose |
| --- | --- | --- | --- |
| M02-30 | `30_MODULE02_MICROSERVICE_SOURCE_STRUCTURE_AMENDMENT.md` | `03_planning` | Extends `17` for book/sharing/catalog services, routes, MinIO; **one DB per service** |
| M02-31 | `31_MODULE02_BACKEND_DETAILED_DESIGN.md` | `03_planning` | Book, Chapter, cover asset, quota, usecase ↔ endpoint mapping |
| M02-32 | `32_MODULE02_FRONTEND_DETAILED_DESIGN.md` | `03_planning` | Screens, routes, state |
| M02-33 | `33_MODULE02_UI_UX_WIREFRAME_SPEC.md` | `03_planning` | Wireframes and UI states |
| M02-34 | `34_MODULE02_INTEGRATION_SEQUENCE_DIAGRAMS.md` | `03_planning` | E2E and failure sequences |
| M02-35 | `35_MODULE02_IMPLEMENTATION_READINESS_GATE.md` | `03_planning` | GO/NO-GO before M02 implementation |
| M02-36 | `36_MODULE02_UI_UX_IMPROVEMENT_IMPLEMENTATION_PLAN.md` | `03_planning` | Docs-only UI/UX improvement implementation plan; execution boundary excludes source-code changes in this step |
| M02-37 | `37_MODULE02_ADR_UI_UX_WAVE_TECHNICAL_DECISIONS.md` | `03_planning` | Wave technical decisions set (Lexical, editor-first, visibility/download/public boundaries) |
| M02-38 | `38_MODULE02_API_CONTRACT_UI_UX_WAVE_AMENDMENT.md` | `03_planning` | Planning-level API contract deltas for UI/UX wave |
| M02-39 | `39_MODULE02_UI_UX_WAVE_CHANGE_IMPACT_AND_COMPATIBILITY.md` | `03_planning` | Cross-stack impact, compatibility policy, and rollout ordering |
| M02-40 | `40_MODULE02_ACCEPTANCE_TEST_PLAN_UI_UX_WAVE_SUPPLEMENT.md` | `03_planning` | Wave-specific acceptance scenarios and evidence supplement |
| M02-41 | `41_MODULE02_RISK_ROLLOUT_GOVERNANCE_UI_UX_WAVE_UPDATE.md` | `03_planning` | Wave risk register, rollout slicing, rollback and governance checkpoints |
| M02-42 | `42_MODULE02_UI_UX_WAVE_IMPLEMENTATION_READINESS_GATE.md` | `03_planning` | GO/NO-GO gate for starting UI/UX wave implementation |
| M02-43 | `43_MODULE02_RESPONSIVE_DESKTOP_SCALING_ADDENDUM.md` | `03_planning` | Responsive desktop and viewport scaling addendum for Module 02 UI/UX wave |

## Phase 1 Module 03 Packs (Provider registry + model billing) — Approved baseline

| Pack Seq | File | Folder | Purpose |
| --- | --- | --- | --- |
| M03-44 | `44_PHASE1_MODULE03_PROVIDER_REGISTRY_EXECUTION_PACK.md` | `03_planning` | Module 03 charter, market-informed policy lock, DoR/DoD, governance gates |
| M03-45 | `45_MODULE03_API_CONTRACT_DRAFT.md` | `03_planning` | Contract draft for provider registry, platform models, usage and billing APIs |
| M03-46 | `46_MODULE03_FRONTEND_FLOW_SPEC.md` | `03_planning` | User/admin frontend journeys and validation/error flow expectations |
| M03-47 | `47_MODULE03_ACCEPTANCE_TEST_PLAN.md` | `03_planning` | Acceptance matrix for metering correctness and quota/credit billing behavior |
| M03-48 | `48_MODULE03_RISK_DEPENDENCY_ROLLOUT.md` | `03_planning` | Risk register, dependency map, rollout and rollback controls |
| M03-49 | `49_GOVERNANCE_BOARD_REVIEW_CHECKLIST_MODULE03.md` | `03_planning` | Governance Board review checklist and decision log template |
| M03-50 | `50_MODULE03_MICROSERVICE_SOURCE_STRUCTURE_AMENDMENT.md` | `03_planning` | Source-structure amendment for registry and billing bounded contexts |
| M03-51 | `51_MODULE03_BACKEND_DETAILED_DESIGN.md` | `03_planning` | Backend domain/adapters/vaulting/metering detailed design |
| M03-52 | `52_MODULE03_FRONTEND_DETAILED_DESIGN.md` | `03_planning` | Frontend route/component/state design for Module 03 surfaces |
| M03-53 | `53_MODULE03_UI_UX_WIREFRAME_SPEC.md` | `03_planning` | Wireframe-level layout and state behavior specification |
| M03-54 | `54_MODULE03_INTEGRATION_SEQUENCE_DIAGRAMS.md` | `03_planning` | BYOK and platform-managed model integration sequence diagrams |
| M03-55 | `55_MODULE03_IMPLEMENTATION_READINESS_GATE.md` | `03_planning` | GO/NO-GO gate before starting Module 03 implementation |

## Phase 2 Module 04 Planning Pack (Approved)

| Pack Seq | File | Folder | Purpose |
| --- | --- | --- | --- |
| M04-56 | `56_PHASE1_MODULE04_RAW_TRANSLATION_EXECUTION_PACK.md` | `03_planning` | Module 04 charter, scope, accountability, DoR/DoD, governance gates |
| M04-57 | `57_MODULE04_API_CONTRACT_DRAFT.md` | `03_planning` | REST API contract for translation settings, jobs, and chapter results |
| M04-58 | `58_MODULE04_FRONTEND_FLOW_SPEC.md` | `03_planning` | Routes, components, state machine, and API mapping for M04 frontend |
| M04-59 | `59_MODULE04_ACCEPTANCE_TEST_PLAN.md` | `03_planning` | 21-scenario AT matrix for translation pipeline (P0/P1/P2) |
| M04-60 | `60_MODULE04_RISK_DEPENDENCY_ROLLOUT.md` | `03_planning` | Risk register, rollout sequence, and rollback plan for M04 |
| M04-61 | `61_GOVERNANCE_BOARD_REVIEW_CHECKLIST_MODULE04.md` | `03_planning` | Governance board review checklist for M04 planning pack gate |
| M04-62 | `62_MODULE04_MICROSERVICE_SOURCE_STRUCTURE_AMENDMENT.md` | `03_planning` | New translation-service source layout and integration boundaries |
| M04-63 | `63_MODULE04_BACKEND_DETAILED_DESIGN.md` | `03_planning` | DB schema, settings merge, JWT minting, job execution flow design |
| M04-64 | `64_MODULE04_FRONTEND_DETAILED_DESIGN.md` | `03_planning` | Frontend types, API functions, component specs, page designs, zod schemas |
| M04-65 | `65_MODULE04_UI_UX_WIREFRAME_SPEC.md` | `03_planning` | ASCII wireframes and UI state tables for translation pages |
| M04-66 | `66_MODULE04_INTEGRATION_SEQUENCE_DIAGRAMS.md` | `03_planning` | Cross-service sequence diagrams for settings, job creation, execution, and failures |
| M04-67 | `67_MODULE04_IMPLEMENTATION_READINESS_GATE.md` | `03_planning` | GO/NO-GO gate before starting Module 04 implementation (Pending) |

## Phase 1 Module Deep-Design Packs

| Pack Seq | File | Folder | Purpose |
| --- | --- | --- | --- |
| M01-17 | `17_MODULE01_MICROSERVICE_SOURCE_STRUCTURE.md` | `03_planning` | Service boundary and source folder/package strategy |
| M01-18 | `18_MODULE01_BACKEND_DETAILED_DESIGN.md` | `03_planning` | Backend domain model, lifecycle, and endpoint mapping design |
| M01-19 | `19_MODULE01_FRONTEND_DETAILED_DESIGN.md` | `03_planning` | Frontend architecture, state boundaries, and integration strategy |
| M01-20 | `20_MODULE01_UI_UX_WIREFRAME_SPEC.md` | `03_planning` | Low-fidelity wireframe and state behavior specification |
| M01-21 | `21_MODULE01_INTEGRATION_SEQUENCE_DIAGRAMS.md` | `03_planning` | End-to-end sequence diagrams for core and failure flows |

## Phase 1 Module Implementation Gates

| Pack Seq | File | Folder | Purpose |
| --- | --- | --- | --- |
| M01-22 | `22_MODULE01_IMPLEMENTATION_READINESS_GATE.md` | `03_planning` | Single-page GO/NO-GO gate before starting Module 01 implementation (**Approved**, GO 2026-03-21) |

## Phase 1 Module UI improvement plan

| Pack Seq | File | Folder | Purpose |
| --- | --- | --- | --- |
| M01-23 | `23_MODULE01_GUI_VISUAL_IMPROVEMENT_PLAN.md` | `03_planning` | GUI visual improvement (**Active**): Tailwind + shadcn/ui + Radix + lucide-react + react-hook-form + zod; aligns with 19/20 |

## Module 01 implementation adjunct (runbook + backlog)

| Doc ID | File | Folder | Purpose |
| --- | --- | --- | --- |
| (runbook) | `MODULE01_LOCAL_DEV.md` | `docs/implementation` | Local ports, stack startup, smoke checklist |
| LW-IMPL-M01-01 | `MODULE01_DEFERRED_FOLLOWUPS.md` | `docs/implementation` | Deferred acceptance and follow-ups before formal M01 closure |

## Module 02 implementation adjunct (backlog)

| Doc ID | File | Folder | Purpose |
| --- | --- | --- | --- |
| LW-IMPL-M02-01 | `MODULE02_SITUATION_AND_TODO.md` | `docs/implementation` | M02 implementation situation, explicitly-not-implemented inventory, and todo backlog |

## Module 03 implementation adjunct (backlog)

| Doc ID | File | Folder | Purpose |
| --- | --- | --- | --- |
| LW-IMPL-M03-01 | `MODULE03_SITUATION_AND_TODO.md` | `docs/implementation` | M03 smoke complete; implementation situation, explicitly-not-implemented inventory, and todo backlog |

## Module 01 Monorepo Governance Note

- Repository model for Module 01 planning series is **single-repo polyglot monorepo**.
- `17_MODULE01_MICROSERVICE_SOURCE_STRUCTURE.md` is authoritative for:
  - monorepo root layout,
  - ownership boundaries,
  - path-based CI/CD governance,
  - branch and release controls.
- `11`-`16` and `18`-`21` must remain consistent with this model and must not introduce multi-repo assumptions.
- `22_MODULE01_IMPLEMENTATION_READINESS_GATE.md` records explicit approval to begin implementation while preserving this monorepo baseline.
- `23_MODULE01_GUI_VISUAL_IMPROVEMENT_PLAN.md` records an **approved** UI stack (see LW-M01-23); it does not supersede contract or readiness gate baselines. Implementation follows that document without changing API contracts.
- Module 02 (**Draft**): planning pack `24`–`35` and `contracts/api/{books,sharing,catalog}/v1/` extend platform core after Module 01 (chapters, **`original_language`**, cover, summary, **draft/revisions**, MinIO/S3 raw files, quota); `35` is the implementation readiness gate before M02 code start.
- Module 03 (**Approved**): planning pack `44`–`55` extends platform core control plane with provider registry, model catalog, usage metering, and billing policy (`tier quota + credits overage`); proposed contract domains: `contracts/api/model-registry/v1/` and `contracts/api/model-billing/v1/`.
- This governance note is planning-only and does not imply implementation of live CI configuration in this phase.


## Migration Map (Old Name -> New Name)


| Old File                                          | New File                                             |
| ------------------------------------------------- | ---------------------------------------------------- |
| `PROJECT_OVERVIEW.md`                             | `01_PROJECT_OVERVIEW.md`                             |
| `PROJECT_ORGANIZATION.md`                         | `02_PROJECT_ORGANIZATION.md`                         |
| `V1_BOUNDARIES.md`                                | `03_V1_BOUNDARIES.md`                                |
| `TECHSTACK_SERVICE_MATRIX.md`                     | `04_TECHSTACK_SERVICE_MATRIX.md`                     |
| `WORKING_MODEL_SCRUMBAN.md`                       | `05_WORKING_MODEL_SCRUMBAN.md`                       |
| `OPERATING_RACI.md`                               | `06_OPERATING_RACI.md`                               |
| `TASK_01_PROJECT_CHARTER_AND_SUCCESS_CRITERIA.md` | `07_TASK_01_PROJECT_CHARTER_AND_SUCCESS_CRITERIA.md` |
| `PHASE_0_EXECUTION_PACK.md`                       | `08_PHASE_0_EXECUTION_PACK.md`                       |
| `ROADMAP_OVERVIEW.md`                             | `09_ROADMAP_OVERVIEW.md`                             |
| `BASIC_TASK_CHECKLIST.md`                         | `10_BASIC_TASK_CHECKLIST.md`                         |
| `loreweave_market_analysis.md`                    | `11_LOREWEAVE_MARKET_ANALYSIS.md`                    |





