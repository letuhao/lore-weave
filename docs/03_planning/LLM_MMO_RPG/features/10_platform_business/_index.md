# 10_platform_business — Index

> **Category:** PLT — Platform / Business
> **Catalog reference:** [`catalog/cat_10_PLT_platform_business.md`](../../catalog/cat_10_PLT_platform_business.md) (owns `PLT-*` stable-ID namespace)
> **Purpose:** Platform-level business mechanics — tier system (free/paid/premium), billing, monetization (DF2), quota management, pricing UX. Partially blocked on D1 (LLM cost per user-hour) pending V1 prototype data.

**Active:** (empty — no agent currently editing)

---

## Feature list

| ID | Title | Status | File | Commit |
|---|---|---|---|---|

(No features designed yet. First feature will live at `PLT_001_<name>.md`.)

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
