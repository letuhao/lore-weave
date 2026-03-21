# LoreWeave Governance Board Review Checklist — Module 02

## Document Metadata

- Document ID: LW-M02-29
- Version: 1.4.0
- Status: Approved
- Owner: Product Manager + Solution Architect
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Governance Board checklist for Module 02 including **`original_language`**, **draft/revisions**, **recycle bin / lifecycle**, storage, sharing.

## Change History

| Version | Date       | Change                                              | Author    |
| ------- | ---------- | --------------------------------------------------- | --------- |
| 1.4.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 1.0.0   | 2026-03-21 | Initial M02 checklist                               | Assistant |
| 1.1.0   | 2026-03-21 | Gates for cover/chapter/MinIO/quota/catalog privacy | Assistant |
| 1.2.0   | 2026-03-21 | Draft/revision + `original_language` + breaking rename | Assistant |
| 1.3.0   | 2026-03-21 | Multilingual list: **`GET …/chapters`** query **`original_language`**, **`sort_order`**; `25` §7 review; books OpenAPI **1.3.0** | Assistant |
| 1.4.0   | 2026-03-21 | Recycle bin: **`lifecycle_state`**, trash/restore/purge, **`GET /v1/books/trash`**; books **1.4.0**, sharing/catalog **1.2.1** | Assistant |

## Review Scope (Module 02 Pack)

- `24_PHASE1_MODULE02_BOOKS_SHARING_EXECUTION_PACK.md`
- `25_MODULE02_API_CONTRACT_DRAFT.md`
- `contracts/api/books/v1/openapi.yaml`
- `contracts/api/sharing/v1/openapi.yaml`
- `contracts/api/catalog/v1/openapi.yaml`
- `26_MODULE02_FRONTEND_FLOW_SPEC.md`
- `27_MODULE02_ACCEPTANCE_TEST_PLAN.md`
- `28_MODULE02_RISK_DEPENDENCY_ROLLOUT.md`
- `30_MODULE02_MICROSERVICE_SOURCE_STRUCTURE_AMENDMENT.md`
- `31_MODULE02_BACKEND_DETAILED_DESIGN.md`
- `32_MODULE02_FRONTEND_DETAILED_DESIGN.md`
- `33_MODULE02_UI_UX_WIREFRAME_SPEC.md`
- `34_MODULE02_INTEGRATION_SEQUENCE_DIAGRAMS.md`
- `35_MODULE02_IMPLEMENTATION_READINESS_GATE.md` (complete before code start)

## Session Goal

Approve or return with conditions the Module 02 planning + deep-design pack in one session, using explicit gates.

## Fast Gate Checklist (Tick-Based)

### Gate A — Scope and governance

- [ ] Module objective, in-scope, and out-of-scope are clear and non-conflicting with `03_V1_BOUNDARIES.md` (including **AI deferred**, **txt-only chapters** for MVP).
- [ ] DoR/DoD and gate list in `24` are actionable.
- [ ] Sign-off placeholders are present for closure and readiness.

### Gate B — Contract and UX

- [ ] Books, sharing, and catalog OpenAPI cover MVP endpoints in `25`, including **cover**, **chapters** (list with optional **`lifecycle_state`**, **`original_language`**, **`sort_order`**), **draft**, **revisions**, **storage usage**, **download original**, **recycle bin** (**`GET /v1/books/trash`**, **`DELETE`** trash, **`POST …/restore`**, **`DELETE …/purge`**), and **`original_language`** (no `primary_language`).
- [ ] Frontend flows in `26` map to paths (upload, **editor**, **history/restore**, quota, chapter list/reorder, **recycle bin**, optional per-locale chapter list).
- [ ] Error envelope matches Module 01 pattern (`code`, `message`), including **415** / **507** / **409** draft conflict where applicable.

### Gate C — Acceptance and quality

- [ ] `27` covers **draft/revision**, **UTF-8 seed**, **raw vs draft download**, **`original_language`**, **list-chapter query filters** (M02-AT-33–35), **recycle bin** (M02-AT-36–45), owner isolation, catalog/unlisted safety for **trashed** books.
- [ ] Pass criteria and evidence artifacts are defined.

### Gate D — Risk and rollout

- [ ] `28` lists dependencies on Module 01, gateway routing, and **MinIO/S3**.
- [ ] High-impact risks (leak, IDOR, **quota bypass**, **object key exposure**) have owners and mitigations.

### Gate E — Cross-document consistency

- [ ] Terminology (`visibility`, `unlisted_access_token`, `owner`, `chapter`, `cover`, `quota`, **`original_language`**, **`lifecycle_state`**, **trash** / **purge_pending**, **draft**, **revision**, **raw upload**) consistent across `25`–`34`.
- [ ] Metadata taxonomy compliant on all new docs.

### Gate F — Monorepo and contracts

- [ ] `30` extends repo layout without contradicting `17` baseline; **bucket/env** narrative present.
- [ ] Contract-impact policy for `contracts/api/{books,sharing,catalog}/v1/` acknowledged.

### Gate G — Implementation readiness (before code)

- [ ] `35_MODULE02_IMPLEMENTATION_READINESS_GATE.md` preconditions satisfied (MinIO/Compose or documented interim).
- [ ] GO / NO-GO / GO with conditions recorded with Decision Authority.
- [ ] Deferred items from `25` Open Questions have owner and target date.

## Decision Record (fill during review)

| Field | Value |
| ----- | ----- |
| Review session date | |
| Outcome | Approved / Approved with conditions / Rework required |
| Conditions | |
| Blocking items | |
| Follow-up actions | |
| Re-review date | |

## References

- `16_GOVERNANCE_BOARD_REVIEW_CHECKLIST_MODULE01.md` (pattern)
- `24_PHASE1_MODULE02_BOOKS_SHARING_EXECUTION_PACK.md`
