# LoreWeave Module 01 Integration Sequence Diagrams

## Document Metadata
- Document ID: LW-M01-21
- Version: 1.1.0
- Status: Draft
- Owner: Solution Architect + QA Lead
- Last Updated: 2026-03-21
- Approved By: Pending
- Approved Date: N/A
- Summary: Integration sequence diagrams for Module 01 happy paths and critical failure paths.

## Change History
| Version | Date | Change | Author |
|---|---|---|---|
| 1.1.0 | 2026-03-21 | Aligned integration sequences with monorepo service roots and shared contract governance | Assistant |
| 1.0.0 | 2026-03-21 | Initial integration sequence diagram document for Module 01 | Assistant |

## 0) Monorepo Integration Context

- `FrontendUI` maps to implementation paths in `frontend/`.
- `ApiGatewayBff` maps to `services/api-gateway-bff/`.
- `AuthService` maps to `services/auth-service/`.
- endpoint and payload expectations are governed by `contracts/api/identity/v1/`.
- monorepo ownership and CI/release controls are authoritative in `17_MODULE01_MICROSERVICE_SOURCE_STRUCTURE.md`.

## 1) Register and Verify (Happy Path)

```mermaid
sequenceDiagram
  participant user as User
  participant ui as FrontendUI
  participant gw as ApiGatewayBff
  participant auth as AuthService

  user->>ui: Submit register form
  ui->>gw: POST /v1/auth/register
  gw->>auth: register request
  auth-->>gw: account created (unverified)
  gw-->>ui: register success + verification_required
  ui-->>user: Show verification prompt
  user->>ui: Confirm verification token
  ui->>gw: POST /v1/auth/verify-email/confirm
  gw->>auth: confirm verification
  auth-->>gw: verified account
  gw-->>ui: verified response
  ui-->>user: Verified state shown
```

## 2) Login and Refresh (Happy Path)

```mermaid
sequenceDiagram
  participant user as User
  participant ui as FrontendUI
  participant gw as ApiGatewayBff
  participant auth as AuthService

  user->>ui: Submit login
  ui->>gw: POST /v1/auth/login
  gw->>auth: authenticate
  auth-->>gw: access + refresh tokens
  gw-->>ui: auth success payload
  ui-->>user: Authenticated experience
  ui->>gw: POST /v1/auth/refresh
  gw->>auth: rotate session
  auth-->>gw: rotated tokens
  gw-->>ui: refresh success
```

## 3) Password Reset (Happy Path)

```mermaid
sequenceDiagram
  participant user as User
  participant ui as FrontendUI
  participant gw as ApiGatewayBff
  participant auth as AuthService

  user->>ui: Request password reset
  ui->>gw: POST /v1/auth/password-reset/request
  gw->>auth: issue reset ticket
  auth-->>gw: accepted (generic response)
  gw-->>ui: reset request accepted
  user->>ui: Submit reset token + new password
  ui->>gw: POST /v1/auth/password-reset/confirm
  gw->>auth: confirm reset
  auth-->>gw: password updated + sessions revoked
  gw-->>ui: reset success
  ui-->>user: Prompt re-login
```

## 4) Profile and Preference Update (Happy Path)

```mermaid
sequenceDiagram
  participant user as User
  participant ui as FrontendUI
  participant gw as ApiGatewayBff
  participant auth as AuthService

  user->>ui: Update profile
  ui->>gw: PATCH /v1/account/profile
  gw->>auth: apply profile update
  auth-->>gw: updated profile
  gw-->>ui: profile update success
  user->>ui: Update security preferences
  ui->>gw: PATCH /v1/account/security/preferences
  gw->>auth: apply preference update
  auth-->>gw: updated preferences
  gw-->>ui: preference update success
```

## 5) Failure Path - Invalid or Expired Session

```mermaid
sequenceDiagram
  participant ui as FrontendUI
  participant gw as ApiGatewayBff
  participant auth as AuthService

  ui->>gw: GET /v1/account/profile with expired token
  gw->>auth: validate token
  auth-->>gw: AUTH_TOKEN_EXPIRED
  gw-->>ui: 401 AUTH_TOKEN_EXPIRED
  ui->>gw: POST /v1/auth/refresh
  gw->>auth: rotate session
  auth-->>gw: AUTH_TOKEN_INVALID
  gw-->>ui: 401 AUTH_TOKEN_INVALID
  ui-->>ui: Clear auth state and route to login
```

## 6) Failure Path - Rate Limited Request

```mermaid
sequenceDiagram
  participant user as User
  participant ui as FrontendUI
  participant gw as ApiGatewayBff
  participant auth as AuthService

  user->>ui: Repeated login attempts
  ui->>gw: POST /v1/auth/login
  gw->>auth: authenticate
  auth-->>gw: AUTH_RATE_LIMITED
  gw-->>ui: 429 AUTH_RATE_LIMITED
  ui-->>user: Show retry timer guidance
```

## 7) Integration Diagram Review Checklist

- [ ] All critical Module 01 journeys have sequence coverage.
- [ ] Failure paths include token expiry and throttling behavior.
- [ ] Actor responsibilities align with gateway/service boundaries.
- [ ] Sequence flows match API contract and frontend design documents.
- [ ] Participant boundaries align with monorepo path ownership and shared contract governance.
