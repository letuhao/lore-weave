# LoreWeave Module 03 API Contract Draft (Provider Registry, Model Catalog, Metering, Billing)

## Document Metadata

- Document ID: LW-M03-45
- Version: 0.3.0
- Status: Draft
- Owner: Solution Architect
- Last Updated: 2026-03-21
- Approved By: Pending
- Approved Date: N/A
- Summary: Contract-first draft for Module 03 APIs covering BYOK provider credentials, strict provider-gateway invocation, user/admin model management, and full encrypted interaction logs with tier quota plus credit overage accounting.

## Change History


| Version | Date       | Change                           | Author    |
| ------- | ---------- | -------------------------------- | --------- |
| 0.3.0   | 2026-03-21 | Added provider-specific model registration semantics (LM/Ollama context length, OpenAI/Anthropic model inventory sync, active/inactive toggles, favorites, tags with notes) | Assistant |
| 0.2.0   | 2026-03-21 | Added strict provider-gateway invocation contract and full encrypted interaction-log list/detail semantics with owner-only decryption access | Assistant |
| 0.1.0   | 2026-03-21 | Initial Module 03 contract draft | Assistant |


## 1) Contract Scope

This draft defines gateway-facing behavior for:

- user provider credential lifecycle (`openai`, `anthropic`, `ollama`, `lm_studio`),
- user model registration mapped to provider credentials,
- admin platform model catalog and pricing controls,
- usage/metering logs per invocation with full encrypted input/output payload persistence,
- billing policy enforcement: `tier quota -> credits overage`.
- strict invocation routing: all AI calls must go through provider registry adapter boundary.

## 2) Proposed OpenAPI Surfaces

Planned source-of-truth paths (to be created in contracts phase):


| API surface                 | Proposed OpenAPI path                          |
| --------------------------- | ---------------------------------------------- |
| Provider and model registry | `contracts/api/model-registry/v1/openapi.yaml` |
| Metering and billing        | `contracts/api/model-billing/v1/openapi.yaml`  |


## 3) Core Endpoint Set (Draft)

### 3.1 User Provider Credentials


| Endpoint                                                       | Method | Auth   | Purpose                                                      |
| -------------------------------------------------------------- | ------ | ------ | ------------------------------------------------------------ |
| `/v1/model-registry/providers`                                 | POST   | Bearer | Register provider credential or local endpoint configuration |
| `/v1/model-registry/providers`                                 | GET    | Bearer | List user provider credentials (redacted secrets)            |
| `/v1/model-registry/providers/{provider_credential_id}`        | PATCH  | Bearer | Rotate key, rename, toggle active                            |
| `/v1/model-registry/providers/{provider_credential_id}`        | DELETE | Bearer | Soft-delete credential                                       |
| `/v1/model-registry/providers/{provider_credential_id}/health` | POST   | Bearer | Validate provider reachability and auth                      |


### 3.2 User Models


| Endpoint                                         | Method | Auth   | Purpose                                |
| ------------------------------------------------ | ------ | ------ | -------------------------------------- |
| `/v1/model-registry/providers/{provider_credential_id}/models` | GET | Bearer | List/sync provider-available model inventory (especially OpenAI/Anthropic) |
| `/v1/model-registry/user-models`                 | POST   | Bearer | Register a model under user credential |
| `/v1/model-registry/user-models`                 | GET    | Bearer | List user models                       |
| `/v1/model-registry/user-models/{user_model_id}` | PATCH  | Bearer | Update model alias/capability flags    |
| `/v1/model-registry/user-models/{user_model_id}/activation` | PATCH | Bearer | Set active/inactive status |
| `/v1/model-registry/user-models/{user_model_id}/favorite` | PATCH | Bearer | Set favorite/unfavorite status |
| `/v1/model-registry/user-models/{user_model_id}/tags` | PUT | Bearer | Replace model tags and notes |
| `/v1/model-registry/user-models/{user_model_id}` | DELETE | Bearer | Archive user model                     |


### 3.3 Platform Models (Admin)


| Endpoint                                                 | Method | Auth           | Purpose                                                     |
| -------------------------------------------------------- | ------ | -------------- | ----------------------------------------------------------- |
| `/v1/model-registry/platform-models`                     | POST   | Bearer (admin) | Create platform managed model with pricing/quoting metadata |
| `/v1/model-registry/platform-models`                     | GET    | Bearer         | List platform models visible to caller                      |
| `/v1/model-registry/platform-models/{platform_model_id}` | PATCH  | Bearer (admin) | Update status, pricing, tier mapping                        |
| `/v1/model-registry/platform-models/{platform_model_id}` | DELETE | Bearer (admin) | Archive platform model                                      |


### 3.4 Metering and Billing


| Endpoint                                 | Method | Auth           | Purpose                                           |
| ---------------------------------------- | ------ | -------------- | ------------------------------------------------- |
| `/v1/model-billing/usage-logs`           | GET    | Bearer         | List per-request logs for current user            |
| `/v1/model-billing/usage-logs/{usage_log_id}` | GET | Bearer | Get decrypted interaction detail for owner (input/output + metadata) |
| `/v1/model-billing/usage-summary`        | GET    | Bearer         | Aggregate usage and cost by period/model/provider |
| `/v1/model-billing/account-balance`      | GET    | Bearer         | Return quota state + remaining credits            |
| `/v1/model-billing/admin/usage-logs`     | GET    | Bearer (admin) | Cross-account usage inspection                    |
| `/v1/model-billing/admin/reconciliation` | POST   | Bearer (admin) | Run reconciliation check over a time window       |

### 3.5 Strict Invocation Gateway

| Endpoint | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/v1/model-registry/invoke` | POST | Bearer | Unified runtime invocation path (gateway routes to provider adapter only) |

Contract rule: feature services and frontend clients must not call provider SDK/HTTP endpoints directly. Invocation requests are valid only through gateway-managed provider routing.


## 4) Core Schemas (Draft)

### ProviderCredential

- `provider_credential_id`
- `owner_user_id`
- `provider_kind` (`openai` | `anthropic` | `ollama` | `lm_studio`)
- `display_name`
- `secret_ref` (vault pointer, never raw key in API response)
- `endpoint_base_url` (required for local providers)
- `status` (`active` | `invalid` | `disabled`)
- timestamps

### UserModel

- `user_model_id`
- `owner_user_id`
- `provider_credential_id`
- `provider_model_name`
- `context_length` (required for LM Studio/Ollama registration path)
- `alias`
- `status`
- `is_active`
- `is_favorite`
- `tags` (`[{ tag_name, note }]`)
- capability flags (`chat`, `embedding`, `tool_calling`)

### PlatformModel

- `platform_model_id`
- `provider_kind`
- `provider_model_name`
- `display_name`
- `pricing_policy` (token unit rates and minimum billable unit)
- `quota_policy_ref` (tier mapping)
- `status` (`active` | `maintenance` | `retired`)

### UsageLog

- `usage_log_id`
- `request_id`
- `account_user_id`
- model reference (`user_model_id` or `platform_model_id`)
- `provider_kind`
- token fields (`input_tokens`, `output_tokens`, `cached_tokens`, optional `reasoning_tokens`)
- `computed_cost_usd`
- `computed_credit_delta`
- `latency_ms`
- `billing_mode` (`tier_quota`, `credits`, `mixed`)
- `input_payload_ciphertext`
- `output_payload_ciphertext`
- `payload_encryption_key_ref`
- `payload_encryption_algo`
- `decrypt_access_audit_count`
- timestamp

### UsageLogDetail (owner view)

- `usage_log_id`
- `request_id`
- `provider_kind`
- `model_ref`
- `input_payload` (decrypted plaintext, owner-only)
- `output_payload` (decrypted plaintext, owner-only)
- token and billing metadata (same as `UsageLog`)
- `viewed_at`

## 5) Billing Policy Contract Rules

- Quota consumption order:
  1. consume monthly tier quota bucket,
  2. if insufficient, consume credits for overage,
  3. reject when both exhausted.
- API responses for billable operations must include usage accounting payload or trace id that resolves to usage log.
- Billing computation version must be logged for reconciliation.
- Interaction payloads are encrypted before persistence and decrypted only for authorized owner-detail reads.
- Invocation records must carry `provider_route_version` for anti-bypass auditing.
- OpenAI/Anthropic model registration must be based on provider inventory records (list/sync endpoint), not arbitrary free-text model id.
- LM Studio/Ollama registration must validate `context_length` against platform policy bounds.

## 6) Security Requirements in Contract

- Provider secrets are write-only from client perspective.
- Key material must be encrypted at rest server-side.
- Admin endpoints require role checks from identity claims.
- Usage logs must store full prompt/response payload encrypted at rest.
- Decrypted interaction detail endpoint is owner-only (or delegated tenant-admin policy if later approved).
- Decryption must be service-managed (passwordless user UX), backed by envelope encryption and KMS-managed keys.
- Every detail-read must be auditable (`viewer_user_id`, `usage_log_id`, `timestamp`, `reason` where applicable).

## 7) Error Taxonomy (Draft)


| Code                       | HTTP    | Meaning                                      |
| -------------------------- | ------- | -------------------------------------------- |
| `M03_VALIDATION_ERROR`     | 400     | Invalid input                                |
| `M03_FORBIDDEN`            | 403     | Missing role/ownership                       |
| `M03_NOT_FOUND`            | 404     | Resource missing or hidden                   |
| `M03_PROVIDER_AUTH_FAILED` | 401     | Provider credential rejected                 |
| `M03_PROVIDER_UNREACHABLE` | 502     | Endpoint unavailable/timeouts                |
| `M03_QUOTA_EXCEEDED`       | 402/409 | Tier quota exhausted and credits unavailable |
| `M03_CREDIT_EXHAUSTED`     | 402/409 | Credits exhausted                            |
| `M03_LOG_DECRYPT_FORBIDDEN` | 403    | Caller is not allowed to decrypt payload detail |
| `M03_CIPHERTEXT_UNAVAILABLE` | 500   | Interaction payload ciphertext/key reference missing or corrupted |
| `M03_PROVIDER_ROUTE_VIOLATION` | 500/409 | Invocation attempted outside provider-gateway contract |
| `M03_CONFLICT`             | 409     | State/version conflict                       |
| `M03_RATE_LIMITED`         | 429     | Rate limit exceeded                          |


## 8) Open Questions


| ID        | Topic                                                     | Owner         | Target                |
| --------- | --------------------------------------------------------- | ------------- | --------------------- |
| OQ-M03-01 | Final domain split: one vs two OpenAPI files              | SA            | Before freeze         |
| OQ-M03-02 | HTTP status policy for billing rejection (`402` vs `409`) | SA + PM       | Before freeze         |
| OQ-M03-03 | Envelope key lifecycle and rotation cadence for interaction payload encryption | Security + SA | Before implementation |
| OQ-M03-04 | Credit precision and rounding policy                      | Finance + SA  | Before implementation |
| OQ-M03-05 | Tag policy constraints (max tags per model, max note length, reserved tag names) | PM + SA | Before implementation |


