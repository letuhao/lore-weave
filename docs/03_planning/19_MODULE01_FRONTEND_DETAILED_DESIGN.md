# LoreWeave Module 01 Frontend Detailed Design

## Document Metadata
- Document ID: LW-M01-19
- Version: 1.1.0
- Status: Draft
- Owner: Product Manager + Platform Core Lead
- Last Updated: 2026-03-21
- Approved By: Pending
- Approved Date: N/A
- Summary: Detailed frontend architecture design for Module 01 identity screens, state boundaries, and API integration strategy.

## Change History
| Version | Date | Change | Author |
|---|---|---|---|
| 1.1.0 | 2026-03-21 | Added monorepo frontend path and contract-governance assumptions | Assistant |
| 1.0.0 | 2026-03-21 | Initial frontend detailed design baseline for Module 01 | Assistant |

## 0) Monorepo Placement and Authority

Frontend design assumptions:
- identity UI implementation lives under `frontend/` path domains.
- integrations target gateway interfaces defined by `12_MODULE01_API_CONTRACT_DRAFT.md` and governed contract paths `contracts/api/identity/v1/`.
- ownership and path-based governance are authoritative in `17_MODULE01_MICROSERVICE_SOURCE_STRUCTURE.md`.

## 1) Module Architecture (Frontend)

Identity module layers:
- `identity/screens` (register/login/verify/reset/profile/preferences)
- `identity/components` (form fields, error panels, auth-status badges)
- `identity/state` (auth state + profile state + async actions)
- `identity/api` (request adapters mapped to contract endpoints)
- `identity/validation` (schema and field validators)
- `identity/i18n` (message keys and fallback rules)

## 2) State Management Boundaries

Core state slices:
- `authState`
  - session presence, token freshness, auth status
- `identityProfileState`
  - profile data, security preferences, verification flags
- `identityRequestState`
  - per-action loading/success/error status for submit flows

State transition principles:
- one source of truth per slice
- request status scoped by action ID to prevent UI race conditions
- expired session transitions force safe logout state

## 3) Component Design Baseline

Reusable component groups:
- `IdentityFormShell`
- `AuthFieldInput`
- `AuthSubmitButton`
- `InlineValidationMessage`
- `AuthAlertBanner`
- `SecurityPreferenceToggleRow`

Screen-specific component examples:
- Register screen: policy hints + validation summary
- Login screen: credential form + forgot-password link
- Profile screen: editable fields + save confirmation banner
- Preferences screen: reset method and alert controls

## 4) API Client Integration Strategy

- API adapter layer maps UI payloads to `12_MODULE01_API_CONTRACT_DRAFT.md`.
- Response normalizer converts backend errors to UI-safe typed errors.
- Retry policy:
  - no auto-retry for auth credential errors
  - controlled retry for transient network failures
- All identity actions include correlation ID for traceability.

## 5) Validation and Form Policy

- Client-side validation runs before submit.
- Server-side validation errors remain source of truth on final rejection.
- Field-level and form-level errors are both required.
- Password and reset inputs use masked fields with reveal toggle and policy hints.

## 6) Localization and Messaging Strategy

- Use translation keys for all user-facing identity messages.
- Error text fallback order:
  1. mapped known error key
  2. generic action-level fallback
  3. locale-default generic failure message

## 7) Telemetry and UX Signals (Planning Level)

Track events:
- `identity_register_submit`
- `identity_login_submit`
- `identity_verification_request`
- `identity_reset_request`
- `identity_profile_update`
- `identity_preference_update`

Capture:
- result status
- error category
- duration bucket

## 8) Frontend Detailed Design Gate Checklist

- [ ] Frontend layers and folder strategy are explicit.
- [ ] State boundaries and transitions are defined for all key flows.
- [ ] API adapters and error normalization are contract-traceable.
- [ ] Validation and localization strategy are complete.
- [ ] Telemetry events are listed for identity critical actions.
- [ ] Monorepo path ownership and contract-path assumptions are explicitly referenced.
