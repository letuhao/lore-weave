# LoreWeave Module 01 Backend Detailed Design

## Document Metadata
- Document ID: LW-M01-18
- Version: 1.1.0
- Status: Draft
- Owner: Solution Architect + Platform Core Lead
- Last Updated: 2026-03-21
- Approved By: Pending
- Approved Date: N/A
- Summary: Detailed backend design for Module 01 identity domain, state transitions, and endpoint-to-domain mapping.

## Change History
| Version | Date | Change | Author |
|---|---|---|---|
| 1.1.0 | 2026-03-21 | Added monorepo service-root and shared-contract path assumptions for backend design | Assistant |
| 1.0.0 | 2026-03-21 | Initial backend detailed design baseline for Module 01 | Assistant |

## 0) Monorepo Placement and Authority

Backend design assumptions:
- `services/auth-service/` is the identity domain implementation root.
- `services/api-gateway-bff/` is the external API composition root.
- API contract artifacts are governed in `contracts/api/identity/v1/`.
- Root structure, ownership, branch/release, and CI governance are authoritative in `17_MODULE01_MICROSERVICE_SOURCE_STRUCTURE.md`.

## 1) Domain Model

Core entities:
- `UserAccount`
  - `user_id`, `email`, `password_hash`, `display_name`, `locale`, `avatar_url`
  - `email_verified`, `account_status`, `created_at`, `updated_at`
- `SessionToken`
  - `session_id`, `user_id`, `refresh_token_hash`, `issued_at`, `expires_at`, `revoked_at`
- `VerificationTicket`
  - `ticket_id`, `user_id`, `token_hash`, `expires_at`, `consumed_at`
- `ResetTicket`
  - `ticket_id`, `user_id`, `token_hash`, `expires_at`, `consumed_at`
- `SecurityPreference`
  - `user_id`, `password_reset_method`, `session_alerts_enabled`, `verification_policy`

## 2) State and Lifecycle Design

### User Account State
- `registered_unverified`
- `active_verified`
- `locked` (policy-controlled)

Transitions:
- register -> `registered_unverified`
- verify success -> `active_verified`
- policy lock trigger -> `locked`

### Session Lifecycle
- issue on successful login
- rotate on refresh
- revoke on logout
- revoke-all on password reset confirmation

## 3) Endpoint-to-Usecase Mapping

| Endpoint | Usecase | Domain Writes | Domain Reads |
|---|---|---|---|
| `POST /v1/auth/register` | `RegisterAccount` | `UserAccount`, `VerificationTicket` | email uniqueness check |
| `POST /v1/auth/login` | `AuthenticateAccount` | `SessionToken` | `UserAccount`, `SecurityPreference` |
| `POST /v1/auth/refresh` | `RotateSession` | `SessionToken` | existing session |
| `POST /v1/auth/logout` | `RevokeSession` | `SessionToken` | session state |
| `GET /v1/account/profile` | `GetProfile` | none | `UserAccount`, `SecurityPreference` |
| `PATCH /v1/account/profile` | `UpdateProfile` | `UserAccount` | current account |
| `POST /v1/auth/verify-email/request` | `IssueVerificationTicket` | `VerificationTicket` | account state |
| `POST /v1/auth/verify-email/confirm` | `ConfirmVerification` | `UserAccount`, `VerificationTicket` | ticket/account state |
| `POST /v1/auth/password-reset/request` | `IssueResetTicket` | `ResetTicket` | account existence policy |
| `POST /v1/auth/password-reset/confirm` | `ConfirmReset` | `UserAccount`, `ResetTicket`, `SessionToken` | ticket/account/session state |
| `GET/PATCH /v1/account/security/preferences` | `GetSecurityPreference` / `UpdateSecurityPreference` | `SecurityPreference` | `SecurityPreference` |

## 4) Error Mapping Design

Domain-to-API mapping:
- `InvalidCredentialsError` -> `AUTH_INVALID_CREDENTIALS`
- `EmailAlreadyExistsError` -> `AUTH_EMAIL_ALREADY_EXISTS`
- `TokenExpiredError` -> `AUTH_TOKEN_EXPIRED`
- `TokenInvalidError` -> `AUTH_TOKEN_INVALID`
- `StateConflictError` -> `AUTH_CONFLICT_STATE`
- `ValidationError` -> `AUTH_VALIDATION_ERROR`

Gateway mapping rule:
- preserve domain code, normalize message for client safety.

## 5) Security Control Points (Design-Level)

- Password never stored in plain text (hash-only model).
- Reset and verification tokens are hash-compared, never stored raw.
- Session rotation invalidates prior refresh token to prevent replay.
- Sensitive actions require verified session context based on policy.
- Rate-limit and lockout policy hooks are defined at endpoint boundary.

## 6) Persistence and Consistency Notes

- Identity writes should be transaction-bound at usecase scope.
- Session revocation on reset must be atomic with password update.
- Verification and reset tickets must be single-use.
- Audit-friendly timestamps required on account and ticket mutations.

## 7) Backend Design Gate Checklist

- [ ] Domain model aligns with API contract draft.
- [ ] Endpoint-usecase mapping is complete and non-overlapping.
- [ ] State transitions are explicit for account/session/ticket lifecycles.
- [ ] Domain errors map cleanly to API taxonomy.
- [ ] Security control points are present at design level.
