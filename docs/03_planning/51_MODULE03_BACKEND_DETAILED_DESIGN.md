# LoreWeave Module 03 Backend Detailed Design

## Document Metadata

- Document ID: LW-M03-51
- Version: 0.4.0
- Status: Approved
- Owner: Solution Architect + Backend Lead
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Detailed backend design for provider adapters, credential vaulting references, model registry workflows, usage metering, and quota-plus-credit billing.

## Change History

| Version | Date       | Change                            | Author    |
| ------- | ---------- | --------------------------------- | --------- |
| 0.4.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 0.3.0   | 2026-03-21 | Added backend model-registration details for provider inventory sync, active/favorite state, and tag+note persistence constraints | Assistant |
| 0.2.0   | 2026-03-21 | Added strict provider-gateway invariant and encrypted full interaction-log storage/decryption design | Assistant |
| 0.1.0   | 2026-03-21 | Initial Module 03 backend design  | Assistant |

## 1) Domain Model

### Registry Domain

- `ProviderCredential`
- `ProviderModelInventory`
- `UserModel`
- `UserModelTag`
- `PlatformModel`
- `ProviderHealthCheckResult`

### Billing Domain

- `UsageLog`
- `UsageLogDetail`
- `UsageSummaryBucket`
- `QuotaLedger`
- `CreditLedger`
- `BillingPolicyVersion`

## 2) Provider Adapter Strategy

- Adapter interface normalizes:
  - model list/discovery,
  - health check,
  - invocation telemetry extraction.
- Adapter interface is the only allowed runtime outbound path to model providers.
- Provider-specific adapters:
  - `openai_adapter`
  - `anthropic_adapter`
  - `ollama_adapter`
  - `lmstudio_adapter` (OpenAI-compatible with local endpoint assumptions)

### Anti-bypass invariant

- Feature/domain services are forbidden from importing provider SDK clients directly.
- Gateway/runtime orchestration must call provider gateway abstraction only.
- Static architecture rule and integration test must fail on direct provider HTTP/SDK usage outside adapter package.

## 3) Credential Vaulting Model

- Client submits secret once.
- Service writes encrypted secret via vault/KMS abstraction.
- Service DB stores only `secret_ref` and metadata.
- Read APIs never return raw key.

## 3.1) Provider-specific Model Registration Rules

- LM Studio / Ollama:
  - `model_name` is required and must be unique under (`owner_user_id`, `provider_credential_id`, `model_name`),
  - `context_length` is required and validated against policy min/max.
- OpenAI / Anthropic:
  - model registration should reference provider inventory cache (`ProviderModelInventory`) from sync/list endpoint,
  - user controls per-model `is_active` without deleting model metadata history.

## 4) Metering and Billing Pipeline

1. Invocation enters provider gateway route and is dispatched to one provider adapter.
2. Adapter returns response payload plus telemetry (`request_id`, tokens, latency, provider/model metadata).
3. `usage-billing-service` validates idempotency on `request_id`.
4. Service computes normalized cost using active policy version.
5. Service applies quota-first and credits-overage transition.
6. Service envelope-encrypts full `input_payload` and `output_payload`.
7. Service persists usage log, usage-log detail ciphertext, and ledger delta atomically.

### Usage log detail table (draft)

- `usage_log_details`
  - `usage_log_id` (FK)
  - `account_user_id`
  - `input_payload_ciphertext`
  - `output_payload_ciphertext`
  - `key_ref`
  - `cipher_algo`
  - `created_at`
  - `updated_at`

Indexes:

- `idx_usage_log_details_owner` on (`account_user_id`, `created_at` desc)
- Unique FK on `usage_log_id`

### User model preference/tag tables (draft)

- `user_model_preferences`
  - `user_model_id` (PK/FK)
  - `owner_user_id`
  - `is_active`
  - `is_favorite`
  - `updated_at`

- `user_model_tags`
  - `user_model_tag_id`
  - `user_model_id` (FK)
  - `owner_user_id`
  - `tag_name`
  - `tag_note`
  - `created_at`
  - `updated_at`

Indexes and constraints:

- Unique (`user_model_id`, `tag_name`)
- `tag_note` length bounded by policy
- Ownership check on all update/delete operations

## 5) Consistency and Idempotency Rules

- Unique index on `usage_logs.request_id`.
- Replayed telemetry with same request id is accepted as no-op.
- Balance endpoint reads latest committed ledger snapshot.
- Decrypt detail endpoint verifies owner before decrypt operation.

## 6) Failure Handling

- Provider timeout/unreachable:
  - record failed usage entry with reason,
  - no billable token charge unless policy explicitly defines a minimum charge.
- Billing persistence failure:
  - fail request accounting transaction and mark reconciliation-needed flag.
- Decrypt path failure:
  - missing key/ciphertext returns `M03_CIPHERTEXT_UNAVAILABLE`,
  - non-owner access returns `M03_LOG_DECRYPT_FORBIDDEN`.
- Provider inventory sync failure:
  - OpenAI/Anthropic model-list refresh returns provider error with retry semantics.
- Registration validation failure:
  - invalid `context_length` or duplicate tag name returns validation error.

## 7) Encryption and Decryption Model

- Envelope encryption:
  - generate per-record data key,
  - encrypt payload fields with data key,
  - wrap data key with KMS tenant/app key,
  - persist ciphertext + wrapped key reference.
- Passwordless owner UX:
  - backend performs decrypt for authorized owner session,
  - user does not manage encryption key material manually.
- Audit requirement:
  - each detail-read emits audit row (`viewer_user_id`, `usage_log_id`, timestamp, result).

## 8) Observability

- Structured logs with correlation ids.
- Metrics:
  - provider health status counts,
  - usage ingestion rate,
  - billing conflict rate,
  - quota-exhaustion and credit-exhaustion counts,
  - decrypt success/failure counts,
  - provider-route violation counts,
  - provider inventory sync success/failure counts,
  - model activation/favorite toggle counts.

## 9) Migration Plan (Draft)

- Create registry tables first.
- Create billing tables and ledgers second.
- Create usage log detail ciphertext table and decrypt-audit table with owner indexes.
- Backfill support not required for this module initial rollout.
