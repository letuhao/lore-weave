# LoreWeave Module 02 API Contract UI/UX Wave Amendment

## Document Metadata

- Document ID: LW-M02-38
- Version: 0.2.0
- Status: Approved
- Owner: Solution Architect
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Planning-level contract amendment for Module 02 UI/UX improve wave, defining behavior deltas to support owner UX, editor-first chapter creation, chapter browsing pagination, raw download auth stability, and public reader improvements.

## Change History

| Version | Date       | Change                                           | Author    |
| ------- | ---------- | ------------------------------------------------ | --------- |
| 0.2.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 0.1.0   | 2026-03-21 | Initial UI/UX wave contract amendment narrative  | Assistant |

## 1) Purpose and Boundary

- This document amends contract intent from `25` for the UI/UX improve wave.
- This is narrative planning; OpenAPI file edits are executed in the implementation phase after gate approval.
- Baseline lifecycle policies and security boundaries from `25` remain valid unless explicitly amended here.

## 2) Contract Delta Summary

| Delta ID | Area | Baseline (`25`) | Amendment for wave |
| --- | --- | --- | --- |
| M02-API-DELTA-01 | Owner books list | List does not guarantee embedded sharing visibility field | Owner list response must include sharing visibility to support in-list status rendering. |
| M02-API-DELTA-02 | Chapter list pagination | Filters exist; pagination metadata for chapter list is incomplete | Add `limit`, `offset`, and `total` semantics for chapter browsing component. |
| M02-API-DELTA-03 | Chapter creation | Multipart upload path is baseline | Add JSON editor-first create path without required file upload. |
| M02-API-DELTA-04 | Raw content download | Owner-only endpoint exists but current UX reports auth failure path | Normalize gateway forwarding/auth behavior for stable owner download. |
| M02-API-DELTA-05 | Public reader flow | Public browse/detail exists at book level | Clarify reader-level chapter browsing behavior for public detail journey. |

## 3) Detailed Amendment Items

### 3.1 Owner list must expose sharing status

- Requirement: owner-facing list includes visibility state (`private|unlisted|public`) directly per row.
- Rationale: avoids expensive client fan-out and allows consistent badge rendering.
- Compatibility note: additive response field for owner context; no public data expansion.

### 3.2 Chapter browsing pagination contract

- Requirement: chapter list endpoint supports explicit `limit` and `offset`.
- Response requirement: include `items` and `total` to support paged UI and empty state logic.
- Existing filters (`original_language`, `sort_order`, optional lifecycle) remain available.

### 3.3 Editor-first chapter creation contract

- Requirement: support non-upload create by JSON request for editor-first workflow.
- Required field: `original_language`.
- Optional fields: `title`, `sort_order`, and initial draft body (exact field names to be finalized in OpenAPI phase).
- Upload path remains valid and is not deprecated in this wave.

### 3.4 Raw download auth consistency

- Requirement: authenticated owner download must work through gateway without losing auth context.
- Error semantics:
  - unauthorized/forbidden remains explicit for non-owner.
  - owner flow must not fail due to gateway header/proxy loss.
- Download payload semantics remain unchanged: returns original uploaded content, not current draft.

### 3.5 Public reader detail behavior

- Requirement: public books are viewable in a complete reader journey (book detail + chapter navigation model).
- Visibility invariants:
  - `private`, `trashed`, `purge_pending` are not discoverable via public reader surfaces.
  - unlisted token behavior stays policy-controlled and non-enumerable.

## 4) Backward-Compatibility Policy

- Prefer additive, non-breaking response extensions for owner list and chapter list.
- New JSON create route/mode is additive.
- Any breaking adjustment must be recorded as explicit version bump during OpenAPI execution and linked to release note.

## 5) Open Questions to Freeze Before OpenAPI Update

| OQ ID | Topic | Owner | Decision target |
| --- | --- | --- | --- |
| M02-WAVE-OQ-01 | Final JSON schema for editor-first create payload | SA + BE | Before OpenAPI patch |
| M02-WAVE-OQ-02 | Whether public reader chapter detail lives in catalog contract or dedicated reader surface | SA + PM | Before OpenAPI patch |
| M02-WAVE-OQ-03 | Exact owner list field shape (`visibility` vs nested policy summary) | SA | Before OpenAPI patch |

## 6) Traceability

- Technical decisions: `37_MODULE02_ADR_UI_UX_WAVE_TECHNICAL_DECISIONS.md`
- Base contract: `25_MODULE02_API_CONTRACT_DRAFT.md`
- Impact analysis input: `39_MODULE02_UI_UX_WAVE_CHANGE_IMPACT_AND_COMPATIBILITY.md`
