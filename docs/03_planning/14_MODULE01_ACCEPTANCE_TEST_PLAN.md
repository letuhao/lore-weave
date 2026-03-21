# LoreWeave Module 01 Acceptance Test Plan

## Document Metadata

- Document ID: LW-M01-14
- Version: 1.3.0
- Status: Approved
- Owner: QA Lead
- Last Updated: 2026-03-21
- Approved By: Governance Board
- Approved Date: 2026-03-21
- Summary: Acceptance test strategy and closure evidence plan for Module 01 identity vertical slice.

## Change History


| Version | Date       | Change                                                              | Author    |
| ------- | ---------- | ------------------------------------------------------------------- | --------- |
| 1.3.0   | 2026-03-21 | Recorded interim **smoke test** complete; full scenario execution and evidence deferred — see `docs/implementation/MODULE01_DEFERRED_FOLLOWUPS.md` | Assistant |
| 1.2.0   | 2026-03-21 | Added monorepo path-scoped CI evidence requirements for acceptance gates | Assistant |
| 1.1.0   | 2026-03-21 | Updated document status to Approved after Governance Board review   | Assistant |
| 1.0.0   | 2026-03-21 | Initial Module 01 acceptance scenario matrix and evidence checklist | Assistant |


## 1) Acceptance Objective

Validate that Module 01 identity flows meet contract, UX, governance, and risk controls required to pass module closure gates.

## 2) Test Scope

In scope:

- Register, login, refresh, logout
- Profile read/update
- Email verification request/confirm
- Password reset request/confirm
- Security preferences read/update

Out of scope:

- Performance/load benchmarking at production scale
- Penetration testing implementation detail
- Multi-tenant enterprise identity behavior

## 3) Scenario Matrix


| Scenario ID | Scenario                           | Expected Result                               | Evidence Artifact                         |
| ----------- | ---------------------------------- | --------------------------------------------- | ----------------------------------------- |
| M01-AT-01   | Register with valid payload        | Account created, verification status returned | API response capture                      |
| M01-AT-02   | Register existing email            | Conflict error handled safely                 | Error payload + UI error screenshot       |
| M01-AT-03   | Login with valid credentials       | Session tokens issued, auth state active      | API response + state transition log       |
| M01-AT-04   | Login invalid credentials          | Auth error with retry guidance                | Error payload + UX screenshot             |
| M01-AT-05   | Refresh with valid token           | Access token rotated                          | Token lifecycle evidence                  |
| M01-AT-06   | Refresh with expired/invalid token | Session invalidated and re-login required     | Error payload + route transition evidence |
| M01-AT-07   | Profile read/update valid fields   | Profile persisted and returned normalized     | API payload before/after                  |
| M01-AT-08   | Verification request and confirm   | Email verified state updated                  | Verify request + confirm evidence         |
| M01-AT-09   | Password reset request and confirm | Password changed and session policy applied   | Reset flow evidence package               |
| M01-AT-10   | Security preferences update        | Preferences saved and retrievable             | API response + UI confirmation            |
| M01-AT-11   | Rate-limited endpoint behavior     | 429 handled with retry UX                     | Error payload + UX state screenshot       |
| M01-AT-12   | Contract mismatch guard            | Invalid schema rejected predictably           | Validation error payload                  |


## 4) Contract Conformance Checks

- Request body fields match contract names and required/optional flags.
- Response payload contains expected keys and type constraints.
- Error codes align with taxonomy in `12_MODULE01_API_CONTRACT_DRAFT.md`.
- Non-breaking field extensions do not regress existing flows.

## 5) Frontend-Backend Integration Checklist

- Every in-scope frontend action is mapped to a contract endpoint.
- Auth state transitions match expected session lifecycle.
- Error handling behavior is consistent between API and UI messages.
- Verification and reset flows are testable end-to-end.
- Security preferences are persisted and reflected in UI.
- Path-scoped CI evidence exists for changed domains (`services/auth-service`, `services/api-gateway-bff`, `frontend`, `contracts`).

## 6) Exit and Pass Criteria

- All critical scenarios (`M01-AT-01` to `M01-AT-10`) pass.
- No unresolved critical severity defects.
- Contract conformance checks have no blocking mismatch.
- Required evidence artifacts are complete and reviewable by QA/SA/PM.

These criteria remain the **formal target** for Module 01 closure; they are **not** satisfied by smoke testing alone (see §9).

## 7) Defect Severity Policy (Module-Level)


| Severity | Definition                                   | Closure Rule                              |
| -------- | -------------------------------------------- | ----------------------------------------- |
| Critical | Blocks core auth/login/register flow         | Must be resolved before module gate       |
| High     | Breaks profile/security preference integrity | Resolve or approved mitigation required   |
| Medium   | UX error handling inconsistency              | Track with owner and near-term fix plan   |
| Low      | Minor messaging/cosmetic issues              | Can be deferred with documented rationale |


## 8) Evidence Artifact Checklist

- API run logs and representative request/response captures
- UI screenshots for success/error states
- State transition notes for auth/session lifecycle
- Defect log with severity, owner, and disposition
- QA sign-off note referencing pass criteria
- Path-based pipeline result evidence aligned to changed monorepo domains

## 9) Execution status (interim — 2026-03-21)

- **Smoke testing (manual, dev/local):** Core UI flows were exercised at a **lightweight** level after the Tailwind + shadcn/ui rollout (e.g. register, login, profile/navigation). This is **not** a substitute for the scenario matrix or evidence artifacts in §3 and §8.
- **Formal acceptance:** Execution of **M01-AT-01 … M01-AT-12** with full evidence, contract checks (§4), and QA sign-off per §6–§8 is **deferred** to a later pass before formal module closure.
- **Backlog pointer:** Deferred and follow-up items are listed in `docs/implementation/MODULE01_DEFERRED_FOLLOWUPS.md` (LW-IMPL-M01-01).

