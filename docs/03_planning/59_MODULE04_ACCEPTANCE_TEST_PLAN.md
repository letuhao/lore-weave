# LoreWeave Module 04 Acceptance Test Plan

## Document Metadata

- Document ID: LW-M04-59
- Version: 0.1.0
- Status: Approved
- Owner: QA Lead
- Last Updated: 2026-03-22
- Approved By: Decision Authority
- Approved Date: 2026-03-22
- Summary: Acceptance matrix for Module 04 raw translation pipeline covering settings management, job lifecycle, chapter result retrieval, provider gateway routing, and billing integration.

## Change History

| Version | Date       | Change                                | Author    |
| ------- | ---------- | ------------------------------------- | --------- |
| 0.1.0   | 2026-03-22 | Initial Module 04 acceptance test plan | Assistant |

## 1) Scope

In scope:
- User translation preference CRUD.
- Book translation settings CRUD (override and reset).
- Settings merge logic (book → user prefs → defaults).
- Translation job creation, async execution, status polling.
- Chapter-level translation result storage and retrieval.
- Provider gateway routing invariant (all invocations through M03 adapter).
- Billing integration (billing recorded via invoke endpoint automatically).
- Error handling: missing model, billing rejection, provider failure, chapter not found.

Out of scope:
- RAG context injection (not in M04 scope).
- Result promotion to book-service chapters (not in M04 scope).
- Multi-user sharing of translation results.

## 2) Acceptance Matrix

| Scenario ID | Scenario | Expected result | Evidence |
| --- | --- | --- | --- |
| M04-AT-01 | Save user translation preferences | Preferences persisted; GET returns saved values | API |
| M04-AT-02 | GET preferences with no saved row | Returns synthesized defaults (platform defaults, `model_ref: null`) | API |
| M04-AT-03 | Save book translation settings | Book settings persisted; GET returns saved values with `is_default: false` | API |
| M04-AT-04 | GET book settings with no saved row | Returns synthesized settings from user prefs with `is_default: true` | API |
| M04-AT-05 | GET book settings with no saved row and no user prefs | Returns platform defaults with `is_default: true` | API |
| M04-AT-06 | Create translation job — all chapters | Job created (`pending`), `total_chapters` equals active chapter count for book | API |
| M04-AT-07 | Create translation job — selected chapters | Job created with only specified `chapter_ids` | API |
| M04-AT-08 | Create translation job with no model configured | Returns `TRANSL_NO_MODEL_CONFIGURED` 422 | API negative |
| M04-AT-09 | Job status lifecycle | Job transitions `pending → running → completed`; `completed_chapters == total_chapters` | API polling |
| M04-AT-10 | Partial failure — one chapter chapter-not-found | Job status `partial`; failed chapter has `status: failed`, `error_message: chapter_not_found` | API + DB |
| M04-AT-11 | Billing rejection on a chapter | That chapter marked `failed` with `billing_rejected`; job continues other chapters | API + usage log |
| M04-AT-12 | Provider invoke failure on a chapter | Chapter marked `failed`, `error_message: provider_error`; job continues | API negative |
| M04-AT-13 | Get chapter translation result | `GET /jobs/:id/chapters/:id` returns `translated_body` for completed chapter | API |
| M04-AT-14 | Non-owner cannot access job | Returns `TRANSL_FORBIDDEN` | API negative |
| M04-AT-15 | Non-owner cannot access chapter result | Returns `TRANSL_FORBIDDEN` | API negative |
| M04-AT-16 | Provider gateway routing invariant | All model invocations go through `POST /v1/model-registry/invoke`; no direct provider SDK call from translation-service | integration trace |
| M04-AT-17 | Billing recorded automatically | Each completed chapter has a non-null `usage_log_id`; usage log exists in usage-billing-service | API cross-check |
| M04-AT-18 | Startup recovery sweep | Jobs stuck in `running` older than 1 hour are moved to `failed` on service restart | service restart test |
| M04-AT-19 | Book settings override user prefs | Effective settings for job use book settings when book row exists | API + job detail |
| M04-AT-20 | User prompt template variable substitution | Translated chapter prompt contains actual chapter text, source/target language | integration trace |
| M04-AT-21 | Unauthenticated request rejected | All `/v1/translation/*` endpoints return 401 without Bearer token | API negative |

## 3) Pass Criteria

- All P0 scenarios pass (`M04-AT-01` through `M04-AT-13`, `M04-AT-16`, `M04-AT-17`, `M04-AT-21`).
- No provider SDK calls outside provider-registry-service adapter boundary.
- Billing is recorded for every completed chapter invocation.
- Job status arithmetic is consistent (completed + failed = total at terminal state).

## 4) Evidence Pack Requirements

- API response traces for all matrix scenarios.
- UI recordings for full user BYOK flow: set preferences → go to book → translate → view result.
- Integration evidence showing invoke call path through provider-registry-service.
- Cross-reference: `usage_log_id` on chapter_translation maps to existing record in `GET /v1/model-billing/usage-logs`.
- Service restart test confirming stuck job recovery.

## 5) Test Layer Mapping

| Layer | Required coverage |
| --- | --- |
| Unit | Settings merge logic, prompt template variable substitution, job status arithmetic, JWT minting |
| Integration | End-to-end job: chapter fetch → invoke call → result storage → status poll |
| E2E smoke | User preferences save; per-book settings; translate 1 chapter; view result in UI |

## 6) Deferred-but-Tracked Cases

- Parallel chapter translation with concurrency limit (sequential only in MVP).
- Result export / download.
- Translation quality scoring.
- Cancel job endpoint.
