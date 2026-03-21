# LoreWeave Module 03 Acceptance Test Plan

## Document Metadata

- Document ID: LW-M03-47
- Version: 0.2.0
- Status: Draft
- Owner: QA Lead
- Last Updated: 2026-03-21
- Approved By: Pending
- Approved Date: N/A
- Summary: Acceptance matrix for Module 03 provider registry, model catalog, usage accounting, and tier-plus-credits billing behavior.

## Change History


| Version | Date       | Change                            | Author    |
| ------- | ---------- | --------------------------------- | --------- |
| 0.2.0   | 2026-03-21 | Added acceptance coverage for full encrypted interaction logs, owner-only detail decryption, and strict provider-gateway routing invariant | Assistant |
| 0.1.0   | 2026-03-21 | Initial Module 03 acceptance plan | Assistant |


## 1) Scope

In scope:

- Provider credential registration and health checks.
- User model registration and management.
- Admin platform model registration and pricing policy.
- Usage accounting correctness.
- Billing policy correctness (tier quota then credits).
- Full encrypted input/output interaction logging and owner-only detail retrieval.
- Strict provider-gateway routing compliance (no direct provider-call bypass).

Out of scope:

- Final invoice generation and taxation workflow.
- GC jobs and long-term archival mechanics.

## 2) Acceptance Matrix


| Scenario ID | Scenario                                  | Expected result                                        | Evidence                 |
| ----------- | ----------------------------------------- | ------------------------------------------------------ | ------------------------ |
| M03-AT-01   | Add OpenAI credential                     | Credential stored encrypted, status active             | API + DB redaction check |
| M03-AT-02   | Add Anthropic credential with invalid key | Health check fails with normalized error               | API negative             |
| M03-AT-03   | Add Ollama local endpoint                 | Endpoint connectivity validated                        | API + service log        |
| M03-AT-04   | Add LM Studio endpoint                    | OpenAI-compatible model discovery works                | API + UI                 |
| M03-AT-05   | Register user model                       | Model appears in user inventory                        | UI + API                 |
| M03-AT-06   | Edit/archive user model                   | State transition reflected in list and detail          | UI + API                 |
| M03-AT-07   | Admin adds platform model                 | Model visible in user platform catalog                 | Admin UI + user UI       |
| M03-AT-08   | Admin updates pricing policy              | New usage records include new policy version           | API + usage log          |
| M03-AT-09   | Tier quota path                           | Request consumes quota bucket without credit deduction | Usage summary            |
| M03-AT-10   | Quota exhausted with credits available    | Request succeeds and deducts credits                   | Usage summary + balance  |
| M03-AT-11   | Quota and credits exhausted               | Request rejected with billing error                    | API negative             |
| M03-AT-12   | Usage filter by provider/model/date       | Aggregation and pagination correct                     | UI + API                 |
| M03-AT-13   | Admin cross-account usage inspection      | Admin endpoint enforces role and returns scoped data   | API + auth negative      |
| M03-AT-14   | Secret redaction check                    | No raw provider key in read responses/log payloads     | API + log audit          |
| M03-AT-15   | Error normalization                       | Provider-specific failures map to M03 error taxonomy   | API matrix               |
| M03-AT-16   | Full payload encryption at write          | Input/output payloads stored encrypted (not plaintext) | DB + storage audit       |
| M03-AT-17   | Owner detail view decrypt                 | Owner can read decrypted input/output for own log row  | API + UI                 |
| M03-AT-18   | Non-owner detail view                     | Non-owner gets `M03_LOG_DECRYPT_FORBIDDEN` and no plaintext leakage | API negative + UI |
| M03-AT-19   | Ciphertext corruption/missing key path    | API returns `M03_CIPHERTEXT_UNAVAILABLE` and UI secure-failure state | API negative + UI |
| M03-AT-20   | Strict invocation routing                 | All runtime calls observed through provider adapter path, no direct provider call from feature service | integration trace |
| M03-AT-21   | Route violation guard                     | Bypass attempt triggers `M03_PROVIDER_ROUTE_VIOLATION` | API/integration negative |


## 3) Pass Criteria

- All P0 scenarios pass (`M03-AT-01` through `M03-AT-11`, `M03-AT-16` through `M03-AT-21`).
- No critical security findings on secret handling and role boundaries.
- Usage/cost arithmetic is deterministic and reproducible.

## 4) Evidence Pack Requirements

- API traces for all matrix scenarios.
- UI recordings for user/admin critical journeys.
- DB evidence proving secret redaction/encryption behavior.
- Reconciliation sample report for at least one time window.
- Decryption access audit evidence for detail-read operations.

## 5) Test Layer Mapping


| Layer       | Required coverage                                           |
| ----------- | ----------------------------------------------------------- |
| Unit        | pricing arithmetic, quota transitions, error mapping, encryption/decryption policy helpers |
| Integration | provider adapter calls, credential storage, usage pipeline, anti-bypass route enforcement |
| E2E smoke   | user BYOK flow, admin platform-model flow, usage visibility, owner detail decrypt path |


## 6) Deferred-but-Tracked Cases

- Multi-currency billing rendering.
- Invoice export formatting.
- Long-window reconciliation stress runs.

