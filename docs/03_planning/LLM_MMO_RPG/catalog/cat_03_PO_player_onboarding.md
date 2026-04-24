<!-- CHUNK-META
source: FEATURE_CATALOG.ARCHIVED.md
chunk: cat_03_PO_player_onboarding.md
byte_range: 42130-44878
sha256: a582cea1d2bb27ef9d45b6392f45a0a856bf926abf5d68609aabb4c770ab77ea
generated_by: scripts/chunk_doc.py
-->

## PO — Player Onboarding

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| PO-1 | User account (reuse existing auth-service + JWT) | ✅ | V1 | — | Existing M01 identity |
| PO-2 | Reality discovery UI — 7-layer: smart-funnel entry, composite ranking (friend/density/locale/canon/recency), friend-follow, flat browse with filters, create-new gating, metrics feedback | ✅ | V1 | IF-3, PO-2a, PO-2b, PO-2c | [03 §9.1](03_MULTIVERSE_MODEL.md#91-reality-discovery), M1-D1..D7 |
| PO-2a | Smart-funnel entry flow (resume-PC → friend-match → canon_attempt top → "be the first") | ✅ | V1 | PO-1 | [03 §9.1.1](03_MULTIVERSE_MODEL.md#911-entry-flow--smart-funnel-m1-d1), M1-D1 |
| PO-2b | Composite ranking engine (7 signals, config-driven weights) + metrics loop | ✅ | V1 | auth friend graph | [03 §9.1.2](03_MULTIVERSE_MODEL.md#912-composite-ranking-m1-d2), M1-D2/D7 |
| PO-2c | PC `presence_visibility` field + friend avatars on browse cards | ✅ | V1 | auth-service follow | [03 §9.1.3](03_MULTIVERSE_MODEL.md#913-friend-follow-layer-m1-d3), M1-D3 |
| PO-3 | Canonicality hint badges (canon_attempt / divergent / pure_what_if) | ✅ | V1 | PO-2 | MV3 locked |
| PO-4 | PC creation — fully custom | ✅ | V1 | IF-3 | [04 §3.1](04_PLAYER_CHARACTER_DESIGN.md), PC-A1 locked |
| PO-5 | PC creation — template-assisted | ✅ | V1 | PO-4 | [04 §3.1](04_PLAYER_CHARACTER_DESIGN.md) |
| PO-6 | PC creation — play-as-glossary-entity | ✅ | V1 | PO-4, WA-1 | [04 §3.2](04_PLAYER_CHARACTER_DESIGN.md), PC-A2 locked |
| PO-7 | PC slot quota (5 per user, configurable) | ✅ | V1 | PO-1 | [04 §5.1](04_PLAYER_CHARACTER_DESIGN.md), PC-C1 locked |
| PO-8 | PC slot purchase (buy more than 5) | 📦 | PLT | PO-7 | **DF2 — Monetization** |
| PO-9 | Reality switcher UI (one user navigates across their PCs in different realities) | 🟡 | V3 | PO-2 | Related to IF-4 |
| PO-10 | 3-tier user complexity model (Reader / Player / Author) + soft upgrade triggers | ✅ | V1 | PO-1 | [03 §9.6.2](03_MULTIVERSE_MODEL.md#962-three-tier-complexity-model-m7-d2), M7-D2 |
| PO-11 | 4-step onboarding tutorial (book page → overlay → postcard → tier-upgrade prompt); i18n EN+VI V1 | ✅ | V1 | PO-10 | [03 §9.6.3](03_MULTIVERSE_MODEL.md#963-onboarding-tutorial-m7-d3), M7-D3 |
| PO-12 | Contextual tooltips on multiverse UI elements (canonicality badges, fork CTA, friend avatar, hibernated, forked-from) | ✅ | V1 | PO-2, PO-10 | [03 §9.6.5](03_MULTIVERSE_MODEL.md#965-contextual-helpers-m7-d5), M7-D5 |
| PO-13 | User-facing terminology enforcement via copy style guide governance | ✅ | V1 | — | [UI_COPY_STYLEGUIDE.md](../../02_governance/UI_COPY_STYLEGUIDE.md), M7-D1/D4 |

