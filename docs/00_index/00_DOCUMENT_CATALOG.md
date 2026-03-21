# LoreWeave Document Catalog and Reading Order

## Document Metadata

- Document ID: LW-00
- Version: 1.6.0
- Status: Approved
- Owner: Decision Authority + Execution Authority
- Last Updated: 2026-03-21
- Approved By: Governance Board
- Approved Date: 2026-03-21
- Summary: Entry point for documentation navigation, reading order, and migration mapping.

## Change History


| Version | Date       | Change                                                        | Author    |
| ------- | ---------- | ------------------------------------------------------------- | --------- |
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

## Phase 1 Module Deep-Design Packs

| Pack Seq | File | Folder | Purpose |
| --- | --- | --- | --- |
| M01-17 | `17_MODULE01_MICROSERVICE_SOURCE_STRUCTURE.md` | `03_planning` | Service boundary and source folder/package strategy |
| M01-18 | `18_MODULE01_BACKEND_DETAILED_DESIGN.md` | `03_planning` | Backend domain model, lifecycle, and endpoint mapping design |
| M01-19 | `19_MODULE01_FRONTEND_DETAILED_DESIGN.md` | `03_planning` | Frontend architecture, state boundaries, and integration strategy |
| M01-20 | `20_MODULE01_UI_UX_WIREFRAME_SPEC.md` | `03_planning` | Low-fidelity wireframe and state behavior specification |
| M01-21 | `21_MODULE01_INTEGRATION_SEQUENCE_DIAGRAMS.md` | `03_planning` | End-to-end sequence diagrams for core and failure flows |

## Module 01 Monorepo Governance Note

- Repository model for Module 01 planning series is **single-repo polyglot monorepo**.
- `17_MODULE01_MICROSERVICE_SOURCE_STRUCTURE.md` is authoritative for:
  - monorepo root layout,
  - ownership boundaries,
  - path-based CI/CD governance,
  - branch and release controls.
- `11`-`16` and `18`-`21` must remain consistent with this model and must not introduce multi-repo assumptions.
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





