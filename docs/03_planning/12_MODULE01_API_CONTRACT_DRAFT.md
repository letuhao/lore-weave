# LoreWeave Module 01 API Contract Draft

## Document Metadata
- Document ID: LW-M01-12
- Version: 1.2.0
- Status: Approved
- Owner: Solution Architect
- Last Updated: 2026-03-21
- Approved By: Governance Board
- Approved Date: 2026-03-21
- Summary: Draft API contract for Module 01 identity flows including account profile, verification, and reset preferences.

## Change History
| Version | Date | Change | Author |
|---|---|---|---|
| 1.2.0 | 2026-03-21 | Added monorepo contract location and contract-impact governance policy | Assistant |
| 1.1.0 | 2026-03-21 | Updated document status to Approved after Governance Board review | Assistant |
| 1.0.0 | 2026-03-21 | Initial API contract draft for Module 01 | Assistant |

## 1) Contract Scope

This draft defines API behavior for:
- account registration and login
- session refresh and logout
- account profile read/update
- email verification request/confirm
- password reset preference and reset request/confirm

Monorepo assumptions:
- source contract path (future implementation): `contracts/api/identity/v1/`.
- this planning document remains the pre-implementation contract baseline.

## 2) Endpoint Set (Draft)

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `/v1/auth/register` | POST | No | Create account |
| `/v1/auth/login` | POST | No | Sign in account |
| `/v1/auth/refresh` | POST | Refresh token | Rotate access token |
| `/v1/auth/logout` | POST | Access token | Invalidate active session |
| `/v1/account/profile` | GET | Access token | Read account profile |
| `/v1/account/profile` | PATCH | Access token | Update profile fields |
| `/v1/auth/verify-email/request` | POST | Access token | Request verification email |
| `/v1/auth/verify-email/confirm` | POST | No (token) | Confirm email verification token |
| `/v1/auth/password-reset/request` | POST | No | Request reset token |
| `/v1/auth/password-reset/confirm` | POST | No (token) | Confirm reset with new password |
| `/v1/account/security/preferences` | GET | Access token | Read security preferences |
| `/v1/account/security/preferences` | PATCH | Access token | Update reset/verification preferences |

## 3) Core Request/Response Schemas (Draft)

## 3.1 Register
Request:
- `email` (string, required)
- `password` (string, required)
- `display_name` (string, optional)
- `locale` (string, optional)

Response:
- `user_id`
- `email`
- `email_verified` (boolean)
- `created_at`
- `verification_required` (boolean)

## 3.2 Login
Request:
- `email`
- `password`

Response:
- `access_token`
- `refresh_token`
- `expires_in_seconds`
- `user_profile` (minimal object)

## 3.3 Profile Update
Patchable fields:
- `display_name`
- `avatar_url`
- `locale`

Returned payload:
- normalized account profile object
- `updated_at`

## 3.4 Security Preferences
Fields:
- `email_verification_required` (bool, policy-bound)
- `password_reset_method` (enum: `email_link`, `email_code`)
- `session_alerts_enabled` (bool)

## 4) Error Taxonomy (Draft)

| Code | HTTP | Meaning |
|---|---|---|
| `AUTH_INVALID_CREDENTIALS` | 401 | Email/password invalid |
| `AUTH_EMAIL_ALREADY_EXISTS` | 409 | Account already exists |
| `AUTH_EMAIL_NOT_VERIFIED` | 403 | Verification required for restricted actions |
| `AUTH_TOKEN_EXPIRED` | 401 | Access/refresh token expired |
| `AUTH_TOKEN_INVALID` | 401 | Token malformed/invalid/revoked |
| `AUTH_FORBIDDEN` | 403 | Action not allowed |
| `AUTH_RATE_LIMITED` | 429 | Request throttled |
| `AUTH_VALIDATION_ERROR` | 400 | Input schema/validation failed |
| `AUTH_RESET_TOKEN_INVALID` | 400 | Reset token invalid or expired |
| `AUTH_VERIFY_TOKEN_INVALID` | 400 | Verification token invalid or expired |
| `AUTH_CONFLICT_STATE` | 409 | Request conflicts with account state |

## 5) Session and Token Rules (Policy Draft)

- Access token TTL is short-lived; refresh token TTL is longer-lived.
- Refresh rotates both tokens and invalidates prior refresh token.
- Logout invalidates current refresh token and active access token context.
- Password reset confirmation revokes existing sessions.
- Email verification status is reflected in profile and auth claims.

## 6) Compatibility and Versioning Rules

- Prefix all identity endpoints with `/v1`.
- Additive response fields are non-breaking.
- Removing or changing semantics of required fields is breaking.
- New security preference enum values require compatibility review.
- Breaking changes require SA approval and migration note.
- Any change under `contracts/**` requires path-impact review for `services/api-gateway-bff`, `services/auth-service`, and `frontend` identity flows.

## 7) Open Questions (To Resolve Before Freeze)

- Exact token format and cryptographic algorithm.
- Whether session device metadata is exposed in Module 01.
- Final rate-limit thresholds per endpoint class.
- Password policy strictness baseline (length/complexity/denylist).

## 8) Contract Freeze Checklist

- [ ] Endpoint list approved by SA.
- [ ] Request/response schemas reviewed by QAL.
- [ ] Error taxonomy mapped to frontend error handling.
- [ ] Session/token lifecycle agreed by SRE and SCO.
- [ ] Open questions resolved or explicitly deferred with owner.
