<!-- CHUNK-META
source: FEATURE_CATALOG.ARCHIVED.md
chunk: cat_10_PLT_platform_business.md
byte_range: 62760-64394
sha256: 68b238879fa4d05d529705c2a1b8dccf610b4ca6ad46ba76132aea76914b8b3b
generated_by: scripts/chunk_doc.py
-->

## PLT — Platform / Business

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| PLT-1 | Tier system — 3 tiers (Free BYOK / Paid platform-LLM / Premium) with feature gating mapped to B3/M1/M7/PC-C1/G3 | ✅ | PLT | PO-1 | [01 §D2](01_OPEN_PROBLEMS.md#d2-tier-viability--partial), D2-D1/D4; [103_PLATFORM_MODE_PLAN](../103_PLATFORM_MODE_PLAN.md) |
| PLT-2 | Usage metering (LLM tokens, cost tracking per user, per-session) + V1 measurement protocol feeding D1 | ✅ | PLT | IF-15 | D2-D5; reuse usage-billing-service |
| PLT-3 | PC slot purchase | 📦 | PLT | PO-8 | **DF2** |
| PLT-4 | Free tier = BYOK-only (user supplies LLM keys, zero platform marginal cost) | ✅ | V1 | PO-1, provider-registry | D2-D2 |
| PLT-5 | Per-tier monthly LLM budget cap with 1.5x margin target (exact numbers TBD post-V1) | 🟡 | PLT | PLT-2 | D2-D3/D6 |
| PLT-6 | Scheduled event hosting (author/platform timed events in popular realities) | 📦 | V2 | DF5, PL-1 | [01 §C3](01_OPEN_PROBLEMS.md#c3-cold-start-empty-world-problem--partial), C3-D4 |
| PLT-4 | Fork quota + cost calculation | 📦 | PLT | EM-2 | Related to DF2 |
| PLT-5 | Admin panel (users, realities, content) | 📦 | PLT | — | [103_PLATFORM_MODE_PLAN §7](../103_PLATFORM_MODE_PLAN.md) |
| PLT-6 | Billing integration (Stripe) | 📦 | PLT | PLT-1 | [103_PLATFORM_MODE_PLAN §5](../103_PLATFORM_MODE_PLAN.md) |
| PLT-7 | IP / ToS / DMCA workflow | ❓ | PLT | — | [01 E3/E4](01_OPEN_PROBLEMS.md) |
| PLT-8 | Self-hosted mode (BYOK only, no platform features) | ✅ | INFRA | IF-14 | [103 §1](../103_PLATFORM_MODE_PLAN.md) |

