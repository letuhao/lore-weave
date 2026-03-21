# LoreWeave Module 03 Frontend Flow Specification

## Document Metadata

- Document ID: LW-M03-46
- Version: 0.4.0
- Status: Approved
- Owner: Product Manager + Frontend Lead
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Frontend user/admin journeys for Module 03 provider registration, model management, and usage/cost visibility.

## Change History

| Version | Date       | Change                           | Author    |
| ------- | ---------- | -------------------------------- | --------- |
| 0.4.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 0.3.0   | 2026-03-21 | Added provider-specific model registration flow details, model active/inactive controls, favorites, and custom tags with notes | Assistant |
| 0.2.0   | 2026-03-21 | Added usage-log detail UX (decrypted owner view) and strict provider-gateway invocation flow requirements | Assistant |
| 0.1.0   | 2026-03-21 | Initial Module 03 FE flow spec   | Assistant |

## 1) UX Scope

- User screens:
  - Add provider credential (BYOK / local endpoint).
  - Add user model from registered provider.
  - Browse available platform models.
  - View usage logs and cost summary.
  - View usage-log detail with decrypted input/output (owner-only).
- Admin screens:
  - Add/edit platform managed model.
  - Configure pricing and quota mapping.
  - Inspect cross-account usage and reconciliation state.

## 2) Primary User Journeys

### UJ-01 Register Provider Credential

1. User opens `Model Providers` page.
2. User selects provider kind.
3. Form adapts by provider:
   - OpenAI/Anthropic: API key fields.
   - Ollama/LM Studio: endpoint URL + optional auth token.
4. User submits, system runs health check.
5. Success shows `active` credential status.

### UJ-02 Register User Model

1. User chooses active provider credential.
2. Flow branches by provider type:
   - LM Studio/Ollama: user enters `model_name` and required `context_length`.
   - OpenAI/Anthropic: system loads all provider models and user controls per-model active/inactive status.
3. User can set alias/capability flags and optional custom tags with notes.
4. User can mark frequent models as `favorite`.
5. Model appears in `My Models` inventory with status (`active`/`inactive`) and favorite/tag metadata.

### UJ-03 Use Platform Model

1. User opens `Platform Models`.
2. User sees model metadata, pricing hints, and quota tier notes.
3. User selects model for runtime (invocation integration handled by downstream modules).
4. Usage later appears in `Usage & Cost`.

### UJ-04 Inspect Usage and Cost

1. User opens `Usage & Cost`.
2. User filters by date, model source, provider.
3. User sees:
   - input/output token counts,
   - computed cost,
   - quota vs credits consumption mode.

### UJ-05 Inspect Interaction Detail (Owner-only)

1. User opens one row in `Usage & Cost`.
2. UI requests `/v1/model-billing/usage-logs/{usage_log_id}`.
3. If caller is owner, UI shows decrypted:
   - input payload,
   - output payload,
   - model/provider/token/cost metadata.
4. If caller is not owner, UI must show explicit access-denied state without payload leakage.

## 3) Admin Journeys

### AJ-01 Add Platform Model

1. Admin opens `Platform Model Admin`.
2. Admin defines provider model mapping.
3. Admin sets pricing and quota group.
4. Admin activates model for user catalog.

### AJ-02 Update Pricing Policy

1. Admin edits pricing for a platform model.
2. Change stores effective timestamp and policy version.
3. New usage uses updated policy version.

### AJ-03 Usage Oversight

1. Admin filters usage by account/provider/model.
2. Admin exports summary and runs reconciliation check.
3. Admin detail view is metadata-focused by default; decrypted payload access remains owner-only unless governance policy is changed.

## 4) Route Proposal (Draft)

- `/m03/providers`
- `/m03/models/my`
- `/m03/models/platform`
- `/m03/usage`
- `/m03/usage/:usageLogId`
- `/admin/m03/platform-models`
- `/admin/m03/usage`

## 5) FE State and Validation Rules

- Provider form validation:
  - required fields vary by provider type.
  - endpoint URL must be valid for local providers.
- Secret fields are masked and never re-displayed in full.
- Usage table state:
  - loading, empty, error, partial-result states are mandatory.
- Pagination and filter state is URL-serializable.
- Usage detail state:
  - decrypting,
  - decrypted success,
  - forbidden (`M03_LOG_DECRYPT_FORBIDDEN`),
  - ciphertext unavailable (`M03_CIPHERTEXT_UNAVAILABLE`).
- Model register state:
  - provider model list loading/failure/empty (OpenAI/Anthropic),
  - `context_length` validation and duplicate model-name checks (LM/Ollama),
  - active/inactive visual states and favorites-first sorting mode.

## 6) Error and Feedback UX

- Credential test failures show normalized provider error code/message.
- Quota/credit exhaustion state shows current balances and CTA to upgrade/top-up.
- Admin pricing updates show audit confirmation with policy version.
- Usage detail failures show secure error states (no partial plaintext rendering on failed decrypt path).

## 7) Invocation Flow Guardrail

- All runtime AI actions from frontend must call platform invoke API (`/v1/model-registry/invoke` or downstream gateway abstraction).
- Frontend must never call provider endpoints directly, even for local providers.
- Inactive models are non-runnable in runtime picker, but remain editable/reactivable.

## 8) Accessibility and Auditability

- All forms must have explicit labels and keyboard-submit behavior.
- Cost and token values use consistent number formatting.
- Critical actions (delete credential, disable model) require confirm dialog.
- Usage detail view must provide clear section landmarks for input and output payloads to support keyboard and assistive navigation.

## 9) Non-Goals (this spec)

- Final visual design system tokens (covered by wireframe/detailed design docs).
- Runtime inference UX inside authoring/editor surfaces (belongs to downstream module integration).
