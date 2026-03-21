# LoreWeave Module 01 UI/UX Wireframe Specification

## Document Metadata
- Document ID: LW-M01-20
- Version: 1.1.0
- Status: Draft
- Owner: Product Manager + Business Analyst
- Last Updated: 2026-03-21
- Approved By: Pending
- Approved Date: N/A
- Summary: Low-fidelity wireframe specification for Module 01 identity screens and state transitions.

## Change History
| Version | Date | Change | Author |
|---|---|---|---|
| 1.1.0 | 2026-03-21 | Added monorepo alignment notes for frontend path and contract-referenced UI states | Assistant |
| 1.0.0 | 2026-03-21 | Initial low-fidelity wireframe specification for Module 01 | Assistant |

## 0) Monorepo Alignment Notes

- Wireframe targets correspond to frontend implementation paths under `frontend/`.
- Screen actions must remain traceable to contract artifacts governed in `contracts/api/identity/v1/`.
- Ownership and review responsibilities follow the monorepo governance defined in `17_MODULE01_MICROSERVICE_SOURCE_STRUCTURE.md`.

## 1) Wireframe Scope

In-scope low-fi wireframes:
- Register page
- Login page
- Email verification status page
- Forgot password page
- Reset password page
- Account profile page
- Security preferences page

## 2) Page Layout Blocks (Low-Fi)

## 2.1 Register Page
- Header: title + helper text
- Form block: email/password/display name/locale
- Action block: submit + secondary link to login
- Error block: inline and summary error area

## 2.2 Login Page
- Header: title + trust message
- Form block: email/password
- Action block: login + forgot password link
- State block: lock/rate-limit warning area

## 2.3 Verification Status Page
- Status badge block (`verified` / `pending`)
- Action block (resend verification)
- Guidance block (next steps, support message)

## 2.4 Forgot/Reset Pages
- Forgot: email input + request action + generic confirmation state
- Reset: token context + new password + confirm password + submit action
- Security notice block for session revocation behavior

## 2.5 Profile and Preferences Pages
- Profile: editable fields (`display_name`, `avatar_url`, `locale`)
- Preferences: reset method selector and session alert toggle
- Save/Cancel action strip

## 3) State Wireframes

Required visual states per screen:
- empty/default
- loading/submitting
- validation error
- API error
- success confirmation
- disabled (action blocked)

## 4) Navigation and Guard Behavior

- Unauthenticated user:
  - can access register/login/forgot/reset
  - cannot access profile/preferences
- Authenticated unverified user:
  - can access profile with restricted behavior
  - verification prompts shown for gated actions
- Authenticated verified user:
  - full profile/preferences access

## 5) Interaction Notes (Low-Fi)

- Primary actions are single-submit with visible loading state.
- Error feedback appears near field and in form summary for critical actions.
- Success feedback must include explicit next-step guidance.
- Sensitive actions (reset/password change) include confirmation messaging.

## 6) Accessibility Review Checklist

- [ ] Focus order is logical for keyboard navigation.
- [ ] All input fields have visible labels.
- [ ] Error messages are attached to relevant fields and summary region.
- [ ] Status changes (loading/success/error) are perceivable for assistive tech.
- [ ] Contrast and spacing assumptions are captured for future hi-fi design.

## 7) Wireframe Review Checklist

- [ ] Every in-scope journey has a wireframe page/state representation.
- [ ] Page blocks map to frontend component strategy in `19_MODULE01_FRONTEND_DETAILED_DESIGN.md`.
- [ ] Navigation guards align with auth state model.
- [ ] Error/disabled states are included for high-risk actions.
- [ ] Accessibility checklist is complete for low-fi review.
- [ ] Wireframe actions remain consistent with monorepo contract and ownership boundaries.
