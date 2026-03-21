# LoreWeave Module 01 Microservice Source Structure

## Document Metadata
- Document ID: LW-M01-17
- Version: 1.1.0
- Status: Draft
- Owner: Solution Architect
- Last Updated: 2026-03-21
- Approved By: Pending
- Approved Date: N/A
- Summary: Source-structure specification for Module 01 microservices, package boundaries, and shared contract organization.

## Change History
| Version | Date | Change | Author |
|---|---|---|---|
| 1.1.0 | 2026-03-21 | Adopted authoritative polyglot monorepo structure and governance policy for Module 01 | Assistant |
| 1.0.0 | 2026-03-21 | Initial source-structure planning baseline for Module 01 | Assistant |

## 1) Monorepo Decision (Authoritative)

LoreWeave adopts a **single GitHub repository** monorepo model.
All Module 01 identity work is managed inside this repository with polyglot service boundaries.

## 2) Monorepo Root Structure (Authoritative)

Recommended root layout:

```text
repo/
  services/
    api-gateway-bff/          # TypeScript (NestJS)
    auth-service/             # Go
    ...                       # future services (Python/Go/TS)
  frontend/                   # UI workspace (if separated from gateway)
  contracts/
    api/
    events/
  infra/
  deploy/
  scripts/
  tools/
  docs/
```

Root governance rules:
- each service owns its own language-local structure and tests.
- cross-service integration happens via versioned contracts in `contracts/`.
- shared operational rules live in repo-level policies (CI, branch, release, CODEOWNERS).

## 3) Service Boundary Baseline

Primary services for Module 01:
- `api-gateway-bff` (TypeScript): external identity-facing API composition.
- `auth-service` (Go): registration, login, token lifecycle, verification/reset intent.
- Optional ownership split (planning decision gate): keep profile/security preference in `auth-service` for Module 01 baseline.

Boundary rules:
- Gateway handles request shaping and error normalization for clients.
- Auth service owns identity domain logic and persistence decisions.
- No direct frontend-to-service communication outside gateway.

## 4) Recommended Source Layout (Per Service)

## 4.1 `api-gateway-bff`
- `src/modules/identity/routes/`
- `src/modules/identity/controllers/`
- `src/modules/identity/contracts/`
- `src/modules/identity/client/` (service client adapters)
- `src/modules/identity/presenters/`
- `src/shared/middleware/`
- `src/shared/errors/`
- `test/modules/identity/`

## 4.2 `auth-service`
- `cmd/auth-service/` (entrypoint)
- `internal/identity/domain/`
- `internal/identity/usecase/`
- `internal/identity/transport/http/`
- `internal/identity/repository/`
- `internal/identity/security/`
- `internal/shared/errors/`
- `internal/shared/config/`
- `test/identity/`

## 5) Shared Contract Organization

- Source-of-truth contract docs remain in planning artifacts (`12_MODULE01_API_CONTRACT_DRAFT.md`).
- Implementation-ready contract files (future) should be generated into:
  - `contracts/api/identity/v1/`
  - `contracts/events/identity/v1/` (if events introduced)
- Gateway and service consume versioned contract snapshots only.
- Contract changes in `contracts/` trigger path-impact checks for gateway and auth service.

## 6) Ownership and Governance Boundaries

| Scope | Responsible | Accountable | Notes |
|---|---|---|---|
| `services/api-gateway-bff` | Platform API Team | Platform Core Lead | External API composition boundary |
| `services/auth-service` | Core Platform Team | Solution Architect | Identity domain logic boundary |
| `frontend` identity modules | Frontend Team | Product Manager | UX/state and screen behavior |
| `contracts/api/identity` | SA + QA | Solution Architect | Shared contract source-of-truth |
| Repo governance policies | PM + SA + SRE | Decision Authority | Branch/release/quality gate policy |

CODEOWNERS-style planning rule:
- every critical path (`services/*`, `contracts/*`, `frontend/*`) must have explicit reviewer ownership.

## 7) CI/CD in Monorepo (Path-Based Governance)

- Path-based selective pipeline:
  - changes in `services/auth-service/**` trigger auth build/test gates.
  - changes in `services/api-gateway-bff/**` trigger gateway build/test gates.
  - changes in `contracts/**` trigger contract compatibility + dependent service checks.
  - changes in `frontend/**` trigger UI lint/test + integration contract checks.
- Shared gates:
  - contract impact check,
  - integration smoke matrix for Module 01 identity endpoints,
  - governance metadata compliance for planning docs.

## 8) Branch and Release Policy (Planning Level)

- Mainline model:
  - `main` as protected trunk.
  - feature branches per module or service scope.
- Required checks before merge:
  - service-scoped CI by path,
  - contract compatibility checks,
  - required reviewers per ownership map.
- Release tagging approach:
  - module baseline tags (for planning milestones),
  - service-impact annotations in release notes.
- Rollback/revert rule:
  - revert at path/service scope where possible,
  - escalate to Decision Authority for cross-service rollback decisions.

## 9) Naming and Namespace Rules

- Identity error codes use `AUTH_*` namespace.
- Route group prefix: `/v1/auth` and `/v1/account`.
- Domain aggregates use stable names:
  - `UserAccount`
  - `SessionToken`
  - `VerificationState`
  - `ResetPolicyPreference`

## 10) Config and Environment Policy (Planning Level)

- Service config separated by domain:
  - `auth.token.*`
  - `auth.verification.*`
  - `auth.password_reset.*`
- Secrets are environment-provided; never committed in repository docs or source.
- Gateway uses downstream service host/config indirection, not hardcoded URLs.

## 11) Logging and Tracing Placement

- Gateway emits request correlation ID and maps downstream errors.
- Auth service emits domain event logs at usecase boundaries.
- Trace spans should include:
  - register/login/reset/verify action names
  - result status (`success`, `validation_error`, `auth_error`, `rate_limited`)

## 12) Source Structure Gate Checklist

- [ ] Service boundaries are explicit and non-overlapping.
- [ ] Monorepo root layout is accepted as authoritative.
- [ ] Folder layout supports domain/usecase separation.
- [ ] Contract location and versioning approach is agreed.
- [ ] Path-based CI/CD checks are defined for services/contracts/frontend.
- [ ] Branch/release policy and reviewer ownership are explicit.
- [ ] Error namespace and route prefixes are aligned with API contract.
- [ ] Config/logging/tracing organization is accepted by SA and SRE.
