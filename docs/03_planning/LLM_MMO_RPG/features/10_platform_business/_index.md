# 10_platform_business — Index

> **Category:** PLT — Platform / Business
> **Catalog reference:** [`catalog/cat_10_PLT_platform_business.md`](../../catalog/cat_10_PLT_platform_business.md) (owns `PLT-*` stable-ID namespace)
> **Purpose:** Platform-level mechanics — (a) **tier system** (free/paid/premium), billing, monetization (DF2), quota management, pricing UX [partially blocked on D1, V1 prototype]; (b) **identity / role / ownership management** (added 2026-04-25 post-WA boundary review): co-author grants, ownership transfer, account-level role lifecycle. These are sibling sub-domains under "platform-level concerns".

**Active:** PLT_001 Charter, PLT_002 Succession (relocated 2026-04-25 from `02_world_authoring/`)

---

## Feature list

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| PLT_001 | **Charter** (CHR) | Co-Author management — invitation lifecycle (7d TTL), accept/decline/cancel/expire, revoke (RealityOwner) + resign (self), JWT-refresh on grant change. 2 aggregates (`coauthor_grant`, `coauthor_invitation`); reuses `forge_audit_log` from WA_003. V1 flat Co-Author role; ownership-transfer in PLT_002. Resolves WA_003 FRG-D5. | DRAFT 2026-04-25 (relocated from `02_world_authoring/`; original drafted as WA_004) | [`PLT_001_charter.md`](PLT_001_charter.md) | 301472f → relocate pending |
| PLT_002 | **Succession** (SUC) | Reality ownership transfer — multi-stage state machine (Pending 14d → Cooldown 7d → Finalized) with recipient acceptance + admin S5 dual-actor approval + 7-day cancel window. T3 atomic Finalize touches `reality_registry` + `coauthor_grant`. 1 aggregate (`ownership_transfer`). V1 recipient must be Co-Author; admin approval mandatory; blocked during Catastrophic/Shattered world stages. Resolves PLT_001 CHR-D1. | DRAFT 2026-04-25 (relocated from `02_world_authoring/`; original drafted as WA_005) | [`PLT_002_succession.md`](PLT_002_succession.md) | 9d8ac58 → relocate pending |

---

## Kernel touchpoints (shared across PLT features)

- `decisions/locked_decisions.md` — V-3 "Both self-hosted + platform-hosted"; D3 self-hosted-vs-platform ACCEPTED
- `02_storage/S06_llm_cost_controls.md` §12V — per-user tier budgets + S6-D1..D8
- `02_storage/S07_queue_abuse.md` §12W — per-tier queue rate limits
- `02_storage/SR08_capacity_scaling.md` §12AK — per-tier capacity budgets + tier multipliers
- `decisions/deferred_DF01_DF15.md` — DF2 (monetization / PC slot purchase) V1+30d
- **D1 OPEN** — LLM cost per user-hour blocks exact pricing; needs V1 prototype data
- **E3 OPEN** — IP ownership legal; blocks platform-mode launch

---

## Naming convention

`PLT_<NNN>_<short_name>.md`. Sequence per-category.

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".
