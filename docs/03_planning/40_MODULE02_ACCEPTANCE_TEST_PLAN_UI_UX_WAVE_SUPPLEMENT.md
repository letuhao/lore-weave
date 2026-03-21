# LoreWeave Module 02 Acceptance Test Plan - UI/UX Wave Supplement

## Document Metadata

- Document ID: LW-M02-40
- Version: 0.2.0
- Status: Approved
- Owner: QA Lead
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Acceptance supplement for Module 02 UI/UX improve wave, adding test scenarios and evidence requirements for owner workspace upgrades, editor-first creation, reader improvements, and gateway download auth correctness.

## Change History


| Version | Date       | Change                                     | Author    |
| ------- | ---------- | ------------------------------------------ | --------- |
| 0.2.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 0.1.0   | 2026-03-21 | Initial acceptance supplement for M02 wave | Assistant |


## 1) Purpose

- Extend baseline acceptance from `27` with wave-specific scenarios.
- Provide explicit evidence requirements before implementation readiness gate `42`.

## 2) Scope

**In scope**

- Sharing status in owner list.
- Sharing save redirect behavior.
- Language picker behavior across create/upload/editor surfaces.
- Book create with description and cover.
- Chapter browsing with pagination and history browsing.
- Editor-first chapter creation using Lexical-based flow.
- Raw download authorization correctness.
- Public reader browse/detail operability.

**Out of scope**

- GC physical deletion execution.
- Non-text chapter MIME expansion.

## 3) Supplement Scenario Matrix


| Scenario ID    | Scenario                                    | Expected result                                                     | Evidence                       |
| -------------- | ------------------------------------------- | ------------------------------------------------------------------- | ------------------------------ |
| M02-WAVE-AT-01 | Owner list renders sharing visibility badge | Each book row shows `private                                        | unlisted                       |
| M02-WAVE-AT-02 | Save sharing policy                         | Save success navigates back to book detail with success feedback    | UI video + network trace       |
| M02-WAVE-AT-03 | Language picker in book create              | Dropdown with code+name and free input fallback works               | UI test + form validation logs |
| M02-WAVE-AT-04 | Language picker in chapter upload/editor    | Same picker behavior is consistent across both entry points         | UI test                        |
| M02-WAVE-AT-05 | Create book with description and cover      | Book persists description and cover metadata                        | API + UI                       |
| M02-WAVE-AT-06 | Chapter browser pagination                  | Page controls and `total`-based navigation work correctly           | UI + API                       |
| M02-WAVE-AT-07 | Chapter filters                             | `original_language` and sort/lifecycle filters return expected rows | UI + API                       |
| M02-WAVE-AT-08 | History browsing                            | Revision list pagination and detail preview are usable              | UI + API                       |
| M02-WAVE-AT-09 | Editor-first create chapter                 | Chapter can be created without file upload and opens in editor flow | UI + API                       |
| M02-WAVE-AT-10 | Upload path non-regression                  | Multipart upload chapter path still works                           | API + UI                       |
| M02-WAVE-AT-11 | Raw download owner success                  | Owner can download original content through gateway                 | API + browser evidence         |
| M02-WAVE-AT-12 | Raw download non-owner deny                 | Non-owner remains blocked with expected code                        | API negative test              |
| M02-WAVE-AT-13 | Public browse list                          | Public books are discoverable in improved browse experience         | UI + API                       |
| M02-WAVE-AT-14 | Public detail and chapter navigation        | Reader can open public detail and navigate chapters                 | UI + API                       |
| M02-WAVE-AT-15 | Visibility/lifecycle invariant              | `private                                                            | trashed                        |


## 4) Pass Criteria

- All M02-WAVE-AT-* scenarios pass in staging-like environment.
- No Critical/High security regression in ownership or visibility controls.
- No regression on baseline M02 scenarios (`27`) directly touched by wave.

## 5) Evidence Pack Requirements

- API evidence:
  - request/response logs for all new/changed scenarios.
  - explicit negative-case evidence for unauthorized access.
- Frontend evidence:
  - UI recordings for primary owner and reader journeys.
  - screenshot bundle for empty/error/loading states.
- Regression evidence:
  - baseline scenarios from `27` that overlap with wave changes.

## 6) Test Layer Mapping


| Layer             | Required coverage                                                           |
| ----------------- | --------------------------------------------------------------------------- |
| Unit tests        | UI state behavior, routing, picker logic, editor wrapper behavior           |
| Integration tests | Gateway auth forwarding, chapter create modes, chapter pagination semantics |
| E2E smoke         | Owner full workflow and reader public workflow                              |


## 7) Traceability

- Wave scope: `36_MODULE02_UI_UX_IMPROVEMENT_IMPLEMENTATION_PLAN.md`
- Decisions: `37_MODULE02_ADR_UI_UX_WAVE_TECHNICAL_DECISIONS.md`
- Contract delta: `38_MODULE02_API_CONTRACT_UI_UX_WAVE_AMENDMENT.md`
- Compatibility: `39_MODULE02_UI_UX_WAVE_CHANGE_IMPACT_AND_COMPATIBILITY.md`
- Baseline acceptance: `27_MODULE02_ACCEPTANCE_TEST_PLAN.md`

