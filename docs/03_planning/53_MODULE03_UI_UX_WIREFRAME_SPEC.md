# LoreWeave Module 03 UI and UX Wireframe Specification

## Document Metadata

- Document ID: LW-M03-53
- Version: 0.4.0
- Status: Approved
- Owner: Product Manager + Frontend Lead
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Wireframe-level layout and interaction states for Module 03 provider registration, model management, and usage/cost dashboards.

## Change History

| Version | Date       | Change                           | Author    |
| ------- | ---------- | -------------------------------- | --------- |
| 0.4.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 0.3.0   | 2026-03-21 | Added detailed provider-specific model registration UX (LM/Ollama context length, OpenAI/Anthropic list activation), favorites, tags with notes, and expanded validation/state guardrails | Assistant |
| 0.2.0   | 2026-03-21 | Added usage-log detail panel states for decrypted owner-only payload view and strict invoke UX guardrails | Assistant |
| 0.1.0   | 2026-03-21 | Initial Module 03 wireframe spec | Assistant |

## 1) User Provider Screen (`/m03/providers`)

### Layout blocks

- Header with purpose and security note.
- Provider list table (status, last health check, actions).
- Add provider drawer/modal with provider-type selector.

### Required states

- Empty state with CTA.
- Health-check running state.
- Credential invalid state with remediation hints.

## 2) User Models Screen (`/m03/models/my`)

### Layout blocks

- Model source tabs (`My Models`, `Platform Models` shortcut).
- Add model form and registered model table.
- Row actions: edit alias, archive.

### Required states

- No models yet.
- Provider disconnected warning.

## 2.1) Provider-specific Model Register Variants

### LM Studio / Ollama registration variant

- Required fields:
  - `model_name` (required, exact runtime identifier),
  - `context_length` (required, integer, min/max validated by policy).
- Optional fields:
  - user alias,
  - capability hints.
- Provider connectivity hints:
  - show endpoint/health badge,
  - show last successful discovery sync timestamp.
- Submission outcome:
  - create one user-model record with explicit context-length metadata,
  - return validation error if `model_name` or `context_length` is invalid.

### OpenAI / Anthropic registration variant

- Replace manual model-name entry with provider model inventory list.
- Model inventory block:
  - fetch all available models from provider credential,
  - show model id/name and capability hints.
- Per-model state control:
  - user can toggle `active` / `inactive` for each listed model at any time,
  - inactive models remain visible for re-activation and history traceability.
- Sync controls:
  - `Refresh model list` action to re-fetch provider inventory.

### Required states for model registration

- Loading states:
  - model inventory loading spinner/skeleton for OpenAI/Anthropic list fetch,
  - register-submit pending state for LM/Ollama form.
- Empty states:
  - provider returns zero models,
  - no active models after filtering.
- Error states:
  - provider list fetch failure with retry action,
  - register submit failure with field-level and global message.
- Validation states:
  - missing/invalid `context_length`,
  - duplicate `model_name` under same provider credential,
  - duplicate tag name in same model,
  - tag note too long (policy-defined limit).
- Inactive visual states:
  - inactive rows dimmed with clear `Inactive` badge,
  - runtime action disabled while keeping edit/favorite/tag actions available.

## 3) Platform Models Screen (`/m03/models/platform`)

- Read-only card/table view for users.
- Show provider, capability tags, and pricing hint.
- Badge for quota eligible vs credit-only billing.

## 3.1) Favorites and Tagging UX for User Models

### Favorite models

- Quick favorite action:
  - star icon per model row/card,
  - one-click `favorite` / `unfavorite`.
- Selection optimization:
  - favorites-first sort mode in model selector,
  - optional `Favorites only` filter.
- Visibility behavior:
  - favorite can apply to both user-managed and platform models,
  - inactive favorites remain marked but are not selectable for runtime until re-activated.

### Custom tags with notes

- Tag management per model:
  - user can add/remove free-form tags,
  - each tag supports optional note/description.
- Suggested starter tags:
  - `thinking`,
  - `tts`,
  - `stt`,
  - `computer_vision`.
- Tag UX rendering:
  - tags displayed as chips,
  - note shown by tooltip/expand panel when user clicks a chip.
- Filtering:
  - selector and table support filter by tag name.

## 4) Usage and Cost Screen (`/m03/usage`)

- Top summary cards:
  - quota used/remaining,
  - credits remaining,
  - period cost.
- Filter bar:
  - date range,
  - provider,
  - model source.
- Usage table:
  - timestamp,
  - model,
  - input/output tokens,
  - cost,
  - billing mode.
- Row action:
  - `View Detail` opens usage interaction detail panel/page.

## 4.1) Usage Log Detail Screen (`/m03/usage/:usageLogId`)

- Header:
  - request id,
  - provider/model badge,
  - timestamp and billing mode.
- Metadata block:
  - token counters,
  - latency,
  - computed cost,
  - policy version.
- Payload tabs:
  - `Input Payload` (decrypted owner view),
  - `Output Payload` (decrypted owner view).
- Audit hint:
  - notice that detailed payload access is owner-protected and audited.

### Required states

- Loading/decrypting state.
- Success state with both payload tabs.
- Forbidden state (`M03_LOG_DECRYPT_FORBIDDEN`) with no payload text rendered.
- Ciphertext unavailable state (`M03_CIPHERTEXT_UNAVAILABLE`) with retry/help action.

## 5) Admin Platform Model Screen (`/admin/m03/platform-models`)

- Editable table for model status and pricing.
- Create/edit modal with policy version preview.
- Confirm dialog for destructive/archive action.

## 6) Admin Usage Screen (`/admin/m03/usage`)

- Cross-account filters and summary.
- Reconciliation trigger with async progress indicator.

## 7) Interaction Guardrails

- Critical actions require explicit confirmation.
- Form submit disabled until required fields validate.
- Toast and inline error patterns are consistent across screens.
- Any feature that triggers AI runtime must route through platform invoke action; direct provider URL controls are not exposed in end-user runtime flow.
- Runtime model picker must hide or disable inactive models by default.
- Model source and provider labels are always displayed to prevent ambiguous selection when names are similar.
- User cannot bypass provider-specific registration rules (`context_length` for LM/Ollama, list-based activation for OpenAI/Anthropic).
