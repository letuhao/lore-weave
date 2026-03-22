# LoreWeave Governance Board Review Checklist — Module 04

## Document Metadata

- Document ID: LW-M04-61
- Version: 0.1.0
- Status: Approved
- Owner: Decision Authority + Execution Authority
- Last Updated: 2026-03-22
- Approved By: Decision Authority
- Approved Date: 2026-03-22
- Summary: One-session governance board review checklist for Module 04 planning pack gate.

## Change History

| Version | Date       | Change                                    | Author    |
| ------- | ---------- | ----------------------------------------- | --------- |
| 0.1.0   | 2026-03-22 | Initial Module 04 governance board checklist | Assistant |

## 1) Purpose

This checklist is used by the Governance Board in a single review session to confirm that Module 04 planning artifacts are complete, consistent, and ready to proceed to implementation.

## 2) Pre-Review Checklist (SA to prepare)

- [ ] All planning docs `56`–`67` are in `docs/03_planning/` and referenced in `00_DOCUMENT_CATALOG.md`.
- [ ] API contract draft (`57`) is internally consistent with backend design (`63`).
- [ ] Frontend flow spec (`58`) maps to every endpoint in the contract (`57`).
- [ ] Acceptance test plan (`59`) covers all P0 scenarios.
- [ ] Risk register (`60`) identifies M03 dependency and JWT minting risk.
- [ ] Implementation readiness gate (`67`) is filled with GO/NO-GO decision record.

## 3) Scope and Boundaries Review

| Item | Pass criteria | Reviewer |
| --- | --- | --- |
| M04 scope is limited to raw translation (no RAG, no write-back to book-service) | In-scope/out-of-scope explicitly stated in `56` §2 | PM |
| Phase 2 entry-point positioning is acknowledged in docs | `56` §1 references Phase 2 | SA |
| workflow-job-service deferral is explicitly documented | `56` §1 and `62` confirm deferral | SA |

## 4) Contract and Architecture Review

| Item | Pass criteria | Reviewer |
| --- | --- | --- |
| All endpoints in `57` have corresponding handler descriptions in `63` | Cross-reference complete | SA |
| JWT minting strategy is documented (not just referenced) | `63` §7 describes mint logic | SA |
| Provider gateway invariant preserved (no direct SDK calls from translation-service) | `63` §6 and `66` confirm adapter-only path | SA + BE lead |
| Settings merge logic is deterministic and documented | `57` §6 and `63` §5 agree | SA |
| DB schema is consistent between `62`/`63` | Tables, indexes, and FKs match | BE lead |

## 5) Frontend and UX Review

| Item | Pass criteria | Reviewer |
| --- | --- | --- |
| All frontend states have corresponding API calls documented | `58` §11 API mapping table complete | FE lead |
| `TRANSL_NO_MODEL_CONFIGURED` UX is handled | `58` §10 documents error state | PM |
| `TranslateButton` polling state machine is described | `58` §7 complete | FE lead |
| New routes do not conflict with existing routes | `64` route table reviewed against `App.tsx` | FE lead |

## 6) Quality and Risk Review

| Item | Pass criteria | Reviewer |
| --- | --- | --- |
| Acceptance matrix covers all P0 scenarios | `59` §3 pass criteria clear | QA lead |
| M03 hard dependency is explicit in risk register | `60` §1 table references M03 | SRE |
| Startup recovery for stale jobs is documented | `60` §2 R-M04-04 and `63` §9 | SRE |
| Rollback plan does not affect other services | `60` §4 confirms translation-service isolation | SRE |

## 7) Decision Log

| Decision | Outcome | Owner | Date |
| --- | --- | --- | --- |
| Sequential vs parallel chapter processing | | PM | |
| Default polling interval (3 s vs 5 s) | | FE lead | |
| `chapter_ids` defaults to all-active or requires explicit selection | | PM | |
| Cancel job endpoint in MVP scope? | | PM + SA | |

## 8) Board Sign-Off

| Role | Name / Initials | Date | Notes |
| --- | --- | --- | --- |
| Decision Authority | | | |
| Execution Authority | | | |
| Solution Architect | | | |
| Product Manager | | | |
| QA Lead | | | |
| SRE Lead | | | |
