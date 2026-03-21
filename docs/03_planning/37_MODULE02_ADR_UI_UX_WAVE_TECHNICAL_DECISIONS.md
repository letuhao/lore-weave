# LoreWeave Module 02 UI/UX Wave Technical Decisions (ADR Set)

## Document Metadata

- Document ID: LW-M02-37
- Version: 0.2.0
- Status: Approved
- Owner: Solution Architect + Product Designer
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Decision record set for Module 02 UI/UX improvement wave, including Lexical selection, editor-first chapter model, owner list sharing visibility, raw download auth strategy, and public reader boundary.

## Change History

| Version | Date       | Change                                                   | Author    |
| ------- | ---------- | -------------------------------------------------------- | --------- |
| 0.2.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 0.1.0   | 2026-03-21 | Initial technical decision set for M02 improve wave     | Assistant |

## 1) Scope and Boundary

- This document captures technical decisions for the improve wave defined in `36`.
- This is planning-only and does not execute source code changes in this step.
- Decisions here are normative input for `38`-`42`.

## 2) Decision Log

| Decision ID | Title | Status | Decision |
| --- | --- | --- | --- |
| M02-WAVE-DR-01 | Editor library | Accepted | Choose **Lexical** as chapter editor foundation. |
| M02-WAVE-DR-02 | Chapter creation model | Accepted | Support two paths: **editor-first JSON create** and **upload-as-import**. |
| M02-WAVE-DR-03 | Owner book list visibility | Accepted | Owner list payload must expose sharing visibility (`private|unlisted|public`). |
| M02-WAVE-DR-04 | Raw content download auth | Accepted | Gateway must preserve authenticated owner flow for `GET /content` without auth drop. |
| M02-WAVE-DR-05 | Public reader surface | Accepted with condition | Public browse/detail must be complete for public books; private/trashed/purge_pending remain hidden. |
| M02-WAVE-DR-06 | Lifecycle invariant | Accepted | Recycle-bin lifecycle rules in M02 baseline remain unchanged; GC physical deletion stays out of scope. |

## 3) Decision Details

### 3.1 M02-WAVE-DR-01: Lexical as editor foundation

**Context**
- The improve wave requires editor-first chapter creation and better long-form writing UX.
- The team already selected Lexical in `36`.

**Decision**
- Use Lexical and standardize integration through a wrapper component (`ChapterRichEditor`).

**Consequences**
- Positive: better control of editor behavior, plugin extensibility, and multilingual IME handling.
- Tradeoff: initial adapter effort and plugin curation are required.
- Constraint: do not change server-side draft contract in this wave (`body` remains canonical payload).

### 3.2 M02-WAVE-DR-02: Dual-path chapter creation

**Decision**
- Keep current upload path.
- Add editor-first create path without mandatory file upload.

**Consequences**
- Requires contract delta to define JSON create request/response.
- `original_language` remains required in both paths.

### 3.3 M02-WAVE-DR-03: Sharing status on owner list

**Decision**
- Owner list must include visibility state directly in list payload for stable UX and reduced client-side fan-out.

**Consequences**
- API amendment needed in `38`.
- Acceptance evidence required in `40`.

### 3.4 M02-WAVE-DR-04: Raw download auth behavior

**Decision**
- Raw content download remains owner-only and must work through gateway with bearer token propagation.

**Consequences**
- Compatibility and rollout control required in `39` and `41`.
- Explicit negative tests required for unauthorized access in `40`.

### 3.5 M02-WAVE-DR-05: Public reader boundary

**Decision**
- Public reading flow is upgraded only for public books.
- `private`, `trashed`, `purge_pending` continue to resolve as not visible to public/unlisted surfaces according to baseline policies.

**Consequences**
- Contract/flow alignment needed across books/sharing/catalog narratives.
- Non-public chapter content remains outside anonymous reader scope unless explicitly specified by amended contract.

## 4) Non-Goals Confirmed

- No change to GC implementation scope.
- No migration to Git-based revision backend in this wave.
- No non-text chapter MIME expansion in this wave.

## 5) Traceability

- Source plan: `36_MODULE02_UI_UX_IMPROVEMENT_IMPLEMENTATION_PLAN.md`
- Contract baseline: `25_MODULE02_API_CONTRACT_DRAFT.md`
- Acceptance baseline: `27_MODULE02_ACCEPTANCE_TEST_PLAN.md`
- Risk baseline: `28_MODULE02_RISK_DEPENDENCY_ROLLOUT.md`
- Gate baseline: `35_MODULE02_IMPLEMENTATION_READINESS_GATE.md`
