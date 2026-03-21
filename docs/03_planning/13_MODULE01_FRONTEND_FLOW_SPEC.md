# LoreWeave Module 01 Frontend Flow Specification

## Document Metadata
- Document ID: LW-M01-13
- Version: 1.2.0
- Status: Approved
- Owner: Product Manager + Platform Core Lead
- Last Updated: 2026-03-21
- Approved By: Governance Board
- Approved Date: 2026-03-21
- Summary: Frontend journey, state, validation, and API mapping spec for Module 01 identity flows.

## Change History
| Version | Date | Change | Author |
|---|---|---|---|
| 1.2.0 | 2026-03-21 | Aligned frontend flow assumptions to monorepo path ownership and contract path governance | Assistant |
| 1.1.0 | 2026-03-21 | Updated document status to Approved after Governance Board review | Assistant |
| 1.0.0 | 2026-03-21 | Initial frontend flow and screen-to-API mapping baseline | Assistant |

## 1) UX Scope

Screens in scope:
- Register
- Login
- Email verification status and resend
- Forgot password / reset password
- Account profile (view + edit)
- Security preferences (verification/reset preferences)

Monorepo placement assumptions:
- frontend identity flows are maintained in `frontend/` workspace paths.
- API integration contracts are sourced from `contracts/api/identity/v1/` governance baseline.
- ownership for frontend identity paths follows module owner mapping in `17_MODULE01_MICROSERVICE_SOURCE_STRUCTURE.md`.

## 2) User Journey Definitions

## 2.1 Register Journey
1. User opens register screen.
2. User inputs email/password/display name/locale.
3. Client validates format and password policy hints.
4. Submit to register endpoint.
5. Success state routes to verification prompt or signed-in state based on policy.

## 2.2 Login Journey
1. User opens login screen.
2. Inputs email and password.
3. Submit to login endpoint.
4. On success: tokens persisted (policy-safe storage), user routed to authenticated entry.
5. On unverified account restriction: show verification guidance.

## 2.3 Verification Journey
1. User requests verification email resend.
2. User receives tokenized link/code externally.
3. Verify confirm action updates verified state.
4. UI refreshes account status and unlocks restricted actions.

## 2.4 Forgot/Reset Password Journey
1. User enters email in forgot-password screen.
2. Reset request accepted with generic success message.
3. User opens reset link/code screen.
4. User sets new password and submits confirmation.
5. Session reset policy warning shown (prior sessions revoked).

## 2.5 Profile and Security Preferences Journey
1. Authenticated user opens account profile.
2. User edits allowed fields (`display_name`, `avatar_url`, `locale`).
3. User opens security preferences and updates reset/verification options.
4. Save action returns latest normalized settings and confirmation banner.

## 3) State Model

| State | Description | Allowed Screens |
|---|---|---|
| `unauthenticated` | No valid access token | register, login, forgot password |
| `authenticated_unverified` | Valid session but email not verified | profile (restricted), verification prompt |
| `authenticated_verified` | Valid session and verified email | full profile + preferences |
| `reset_pending` | User entered reset flow | reset password |
| `locked_or_rate_limited` | Temporary lock/rate limit state | error state with retry timer |

## 4) Validation Matrix (Frontend)

| Field | Rules | Error UX |
|---|---|---|
| `email` | required, valid email format | inline + submit-level summary |
| `password` | required, min length, complexity baseline | inline hints + blocking error |
| `display_name` | optional, max length | inline warning |
| `avatar_url` | optional, valid URL format | inline warning |
| `locale` | optional, supported locale enum | fallback to default locale |
| `reset_token` | required when confirming reset | blocking error with retry guidance |

## 5) Screen-to-API Mapping

| Screen/Action | API Endpoint | Method | Success Result | Failure Result |
|---|---|---|---|---|
| Register submit | `/v1/auth/register` | POST | create account + next state | validation/conflict error |
| Login submit | `/v1/auth/login` | POST | create session + route auth state | invalid credentials/lockout |
| Refresh on app resume | `/v1/auth/refresh` | POST | rotate token and continue session | force re-login |
| Logout action | `/v1/auth/logout` | POST | clear local auth state | warning + local safe logout |
| Load profile | `/v1/account/profile` | GET | show account data | auth/session error state |
| Save profile | `/v1/account/profile` | PATCH | show updated profile | validation/conflict error |
| Request verify email | `/v1/auth/verify-email/request` | POST | confirmation toast | rate-limit/retry |
| Confirm verify token | `/v1/auth/verify-email/confirm` | POST | verified status | invalid token state |
| Request password reset | `/v1/auth/password-reset/request` | POST | generic success state | throttled state |
| Confirm password reset | `/v1/auth/password-reset/confirm` | POST | reset success and re-login prompt | invalid token/password error |
| Load security prefs | `/v1/account/security/preferences` | GET | show preference values | auth/session error |
| Save security prefs | `/v1/account/security/preferences` | PATCH | confirm saved preferences | validation/conflict error |

## 6) UX Error Handling Policy

- Display user-safe messages; do not expose internal diagnostics.
- Use generic message for account existence during reset request.
- Prioritize actionable errors: retry, edit input, or contact support path.
- Rate-limited state must show retry timing guidance.

## 7) Accessibility and Localization Minimums

- Keyboard navigation and visible focus states on all identity screens.
- Label and error text must be screen-reader compatible.
- Locale fallback path must be deterministic.
- Error strings and helper text should support translation keys.

## 8) Frontend Flow Freeze Checklist

- [ ] Every in-scope action maps to one contract endpoint.
- [ ] Validation rules align with API schema expectations.
- [ ] State transitions are defined for success and failure paths.
- [ ] Error UX policy reviewed with QA and Security.
- [ ] Accessibility/localization minimums accepted by PM.
- [ ] Monorepo path ownership and contract path references are present and consistent.
