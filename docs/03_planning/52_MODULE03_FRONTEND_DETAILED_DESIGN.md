# LoreWeave Module 03 Frontend Detailed Design

## Document Metadata

- Document ID: LW-M03-52
- Version: 0.3.0
- Status: Approved
- Owner: Frontend Lead
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Frontend architecture and component-level design for Module 03 provider/model management and usage billing views.

## Change History

| Version | Date       | Change                              | Author    |
| ------- | ---------- | ----------------------------------- | --------- |
| 0.3.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 0.2.0   | 2026-03-21 | Added provider-specific model registration component design, favorites/tags UX state, and API surface alignment | Assistant |
| 0.1.0   | 2026-03-21 | Initial Module 03 frontend design   | Assistant |

## 1) Route and Page Structure

- `ProvidersPage` (`/m03/providers`)
- `MyModelsPage` (`/m03/models/my`)
- `PlatformModelsPage` (`/m03/models/platform`)
- `UsageBillingPage` (`/m03/usage`)
- `UsageLogDetailPage` (`/m03/usage/:usageLogId`)
- `AdminPlatformModelsPage` (`/admin/m03/platform-models`)
- `AdminUsagePage` (`/admin/m03/usage`)

## 2) Component Design

- `ProviderForm`:
  - dynamic provider field sets,
  - write-only secret input behavior.
- `ProviderHealthBadge`:
  - status display from health endpoint.
- `UserModelForm` and `UserModelTable`.
- `ProviderModelInventoryPanel`:
  - list/sync OpenAI/Anthropic available models,
  - per-row `active` / `inactive` toggle.
- `LmOllamaModelFormFields`:
  - required `model_name`,
  - required `context_length` validation.
- `FavoriteToggle` and `ModelTagEditor`:
  - favorite pin/unpin,
  - custom tag + note editing.
- `PlatformModelForm` and `PlatformModelTable` (admin).
- `UsageFilterBar`, `UsageTable`, `UsageSummaryCards`.

## 3) State Boundaries

- Query state: pagination/filter/sort in URL.
- Form state: local component + schema validation.
- Shared state:
  - auth role capability,
  - selected model context (if needed by downstream flows).
  - favorites-first and tag filter preferences.

## 4) API Client Surface (M03)

- `listProviders`, `createProvider`, `updateProvider`, `deleteProvider`, `testProviderHealth`
- `listProviderModels`, `syncProviderModels`
- `listUserModels`, `createUserModel`, `updateUserModel`, `setUserModelActive`, `setUserModelFavorite`, `updateUserModelTags`, `deleteUserModel`
- `listPlatformModels`, `createPlatformModel`, `updatePlatformModel`, `deletePlatformModel`
- `listUsageLogs`, `getUsageLogDetail`, `getUsageSummary`, `getAccountBalance`
- `listAdminUsageLogs`, `runReconciliation`

## 5) Validation and Error Handling

- Provider-specific validation schema with conditional required fields.
- Display normalized error codes from M03 taxonomy.
- Distinguish transient provider failures vs credential failures.
- Validate `context_length` bounds for LM/Ollama model register.
- Validate unique tag names per model and note-length limits.

## 6) Security UX Rules

- Never re-render saved secret values.
- Mask sensitive identifiers in tables where needed.
- Admin pages hidden for non-admin users by route guard.
