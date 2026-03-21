# Module 01 — deferred follow-ups (backlog)

## Document Metadata

- Document ID: LW-IMPL-M01-01
- Version: 1.0.0
- Status: Active
- Owner: Execution Authority + QA Lead (consulted)
- Last Updated: 2026-03-21
- Approved By: Pending
- Approved Date: N/A
- Summary: Short backlog of Module 01 identity work **not** completed at handoff to Module 02 planning; revisit before formal module closure or production gate.

## Change History

| Version | Date       | Change                          | Author    |
| ------- | ---------- | ------------------------------- | --------- |
| 1.0.0   | 2026-03-21 | Initial deferred-work inventory | Assistant |

## Context

- **Done for now:** UI refresh per `docs/03_planning/23_MODULE01_GUI_VISUAL_IMPROVEMENT_PLAN.md` (Tailwind, shadcn/ui, shell, forms); **manual smoke** on dev/local (register, login, profile/navigation) recorded in `MODULE01_LOCAL_DEV.md` and `14_MODULE01_ACCEPTANCE_TEST_PLAN.md`.
- **Explicitly later:** Formal acceptance test execution, evidence pack, and QA sign-off per `14` §6–§8.

## Deferred items (revisit)

| Area | Item | Reference |
| ---- | ---- | --------- |
| QA / acceptance | Execute full scenario matrix **M01-AT-01 … M01-AT-12** with captured evidence (API + UI where required) | `14_MODULE01_ACCEPTANCE_TEST_PLAN.md` |
| QA / acceptance | Contract conformance checks (§4) and defect log with disposition | `14` §4, §7 |
| UX / design | Systematic pass vs wireframe intent (blocks/states), not only informal review | `20_MODULE01_UI_UX_WIREFRAME_SPEC.md` |
| Docs | Refresh **§4 Current state** in doc 23 to describe **implemented** stack (`index.css`, `AppLayout`, etc.) instead of legacy `styles.css` narrative | `23_MODULE01_GUI_VISUAL_IMPROVEMENT_PLAN.md` |
| FE structure | Optional: move `frontend/src/pages/*` → `src/identity/screens/` and align imports with `19` | `19_MODULE01_FRONTEND_DETAILED_DESIGN.md`, doc 23 §14 |
| UX / resilience | Verify **429 / rate-limit** messaging end-to-end (**M01-AT-11**) | `14`, doc 23 §9 |
| a11y | Focus/labels audit; live regions if feedback becomes toast-only | `23` §10 |
| Tooling | Frontend ESLint/Prettier if team standardizes | ad hoc |
| Out-of-scope (doc 23) | i18n catalogs, dark mode, marketing site — only if product pulls into a later phase | `23` §13 |
| Security / launch | Production hardening, pen test, SRE sign-off (not implied by dev smoke) | `22_MODULE01_IMPLEMENTATION_READINESS_GATE.md` §66–67 |

## Suggested trigger

- Before **formal Module 01 closure** or **production** identity launch, work through this list (or formally waive items with Decision Authority).

## Related

- `docs/implementation/MODULE01_LOCAL_DEV.md` — smoke checks and stack notes
- `docs/03_planning/14_MODULE01_ACCEPTANCE_TEST_PLAN.md` — authoritative acceptance criteria when ready
