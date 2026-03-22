# LoreWeave Module 04 Implementation Readiness Gate

## Document Metadata

- Document ID: LW-M04-67
- Version: 0.1.0
- Status: Approved
- Owner: Decision Authority + Solution Architect
- Last Updated: 2026-03-22
- Approved By: Decision Authority
- Approved Date: 2026-03-22
- Summary: GO/NO-GO implementation readiness gate for Module 04 raw translation pipeline. Records planning pack completeness, open question resolution, and board decision.

## Change History

| Version | Date       | Change                                   | Author    |
| ------- | ---------- | ---------------------------------------- | --------- |
| 0.1.0   | 2026-03-22 | Initial Module 04 implementation readiness gate | Assistant |

---

## 1) Planning Pack Completeness Checklist

| Doc ID | Title | Status |
| --- | --- | --- |
| LW-M04-56 | Phase 1 Module 04 Execution Pack | Draft |
| LW-M04-57 | API Contract Draft | Draft |
| LW-M04-58 | Frontend Flow Spec | Draft |
| LW-M04-59 | Acceptance Test Plan | Draft |
| LW-M04-60 | Risk, Dependency, and Rollout Plan | Draft |
| LW-M04-61 | Governance Board Review Checklist | Draft |
| LW-M04-62 | Microservice Source Structure Amendment | Draft |
| LW-M04-63 | Backend Detailed Design | Draft |
| LW-M04-64 | Frontend Detailed Design | Draft |
| LW-M04-65 | UI/UX Wireframe Spec | Draft |
| LW-M04-66 | Integration Sequence Diagrams | Draft |
| LW-M04-67 | Implementation Readiness Gate (this doc) | Draft |

All 12 documents present: **YES**

---

## 2) Open Question Resolution

From `57_MODULE04_API_CONTRACT_DRAFT.md` §10:

| # | Question | Decision | Owner | Resolved |
| --- | --- | --- | --- | --- |
| OQ-1 | Default polling interval: 3 s vs 5 s? | **5 s** | FE lead | ☑ |
| OQ-2 | `chapter_ids` omitted = all active chapters or validation error? | **Required; UI pre-selects untranslated active chapters** | PM | ☑ |
| OQ-3 | Cancel job endpoint in MVP? | **Yes** — `POST /v1/translation/jobs/{job_id}/cancel` | PM + SA | ☑ |
| OQ-4 | Expose token counts in chapter result or defer to billing cross-ref? | **Both** — expose in API response + keep `usage_log_id`; requires provider-registry invoke response to expose `usage.input_tokens`/`output_tokens` | SA | ☑ |

From `61_GOVERNANCE_BOARD_REVIEW_CHECKLIST_MODULE04.md` §7 Decision Log:

| Decision | Outcome | Owner | Resolved |
| --- | --- | --- | --- |
| Sequential vs parallel chapter processing | Sequential (BackgroundTasks simplicity) | SA | ☑ |
| `chapter_ids` defaults | Required; UI pre-selects untranslated active chapters | PM | ☑ |
| Cancel job scope | In MVP — `POST /v1/translation/jobs/{job_id}/cancel` | PM | ☑ |

---

## 3) Prerequisite Service Readiness

| Prerequisite | Required state | Current state | Gate |
| --- | --- | --- | --- |
| M03 provider-registry-service | Running, `/v1/model-registry/invoke` returns 200 | Smoke test passed | ☐ Confirm |
| M03 usage-billing-service | Running (billing auto-recorded via invoke) | Smoke test passed | ☐ Confirm |
| book-service internal endpoints | `/internal/books/{id}/projection` and `/internal/books/{id}/chapters/{id}` return correct schema | Not verified against M04 schema needs | ☐ Verify |
| loreweave_translation DB | Does not exist yet — bootstrap script ready | Pending infra change | ☐ Pending |
| JWT_SECRET env var | Same value across book-service, provider-registry-service, and translation-service | Configured in docker-compose | ☐ Confirm |

---

## 4) Key Design Decisions — Confirmed in Planning Pack

| Decision | Documented in | Status |
| --- | --- | --- |
| translation-service owns 4 tables; no direct DB coupling to other services | `62` §4 | Confirmed in docs |
| All model invocations via `/v1/model-registry/invoke` only (no SDK imports) | `62` §7, `63` §6 | Confirmed in docs |
| JWT minted by translation-service (TTL 300s, re-mint if <30s remaining) | `63` §7 | Confirmed in docs |
| Settings snapshot at job creation (changes after start do not affect running job) | `62` §7, `63` §5 | Confirmed in docs |
| Sequential chapter processing via FastAPI BackgroundTasks | `63` §8 | Confirmed in docs |
| Startup recovery sweep marks stale jobs failed | `63` §9 | Confirmed in docs |
| Token counts null in MVP (usage_log_id for cross-reference) | `63` §12 | Confirmed in docs |

---

## 5) Implementation Risk Acknowledgement

| Risk ID | Risk | Mitigation | Acknowledged |
| --- | --- | --- | --- |
| R-M04-01 | JWT minting with wrong secret → 401 from provider | Integration test in SEQ-04 / AT-16 covers this | ☐ |
| R-M04-02 | BackgroundTask killed on server restart → job stuck running | Startup sweep (§9 of `63`) handles jobs older than 1 hour | ☐ |
| R-M04-03 | `{chapter_text}` not in prompt template → KeyError at runtime | Validation enforced at PUT settings endpoints | ☐ |
| R-M04-04 | book-service internal schema mismatch | Verify `original_language` field exists in chapter draft response | ☐ |

---

## 6) GO / NO-GO Decision

| Criterion | Result | Notes |
| --- | --- | --- |
| All 12 planning docs present | GO | ✓ |
| Open questions resolved | **PENDING** | OQ-1 through OQ-4 need answers |
| Prerequisite services smoke-tested | **PENDING** | M03 smoke done; internal book endpoints not verified for M04 schema |
| Board sign-off received | **PENDING** | See §7 |

**Current Gate Status: GO — approved by Decision Authority on 2026-03-22**

---

## 7) Board Sign-Off

| Role | Name / Initials | Decision | Date | Notes |
| --- | --- | --- | --- | --- |
| Decision Authority | Decision Authority | GO | 2026-03-22 | |
| Execution Authority | | | | |
| Solution Architect | | | | |
| Product Manager | | | | |
| QA Lead | | | | |

_Gate opens to GO when all open questions are resolved and all roles above have signed off._
