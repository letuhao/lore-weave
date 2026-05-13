# DF — Index

> **Purpose:** Big deferred features (DF1..DF15) actively being designed. Each DF gets its own sub-subfolder with multi-file design (spec + UI + data model + interaction flow). Master registry of DF status stays in [`../../decisions/deferred_DF01_DF15.md`](../../decisions/deferred_DF01_DF15.md); this folder holds the **design work** for DFs currently being designed.

**Active:** (empty — no agent currently editing)

---

## Sub-subfolder status

| DF | Feature | V1-blocking? | Subfolder | Status |
|---|---|---|---|---|
| DF1 | Daily Life / Sinh hoạt (NPC routines, PC→NPC conversion) | V2 | — | placeholder in `12_daily_life/` reserved |
| DF2 | Monetization / PC slot purchase | V1+30d | — | not yet designed |
| DF3 | Canonization / Author Review | V2+ | — | pre-spec locked in `02_storage/S13_canonization_pre_spec.md` |
| **DF4** | **World Rules** (per-reality rule engine) | **V1** | [DF04_world_rules/](DF04_world_rules/) | placeholder |
| **DF5** | **Session / Group Chat** | **V1** | [DF05_session_group_chat/](DF05_session_group_chat/) | placeholder |
| DF6 | World Travel | V3+ | — | not yet designed |
| **DF7** | **PC Stats & Capabilities** | **V1** | [DF07_pc_stats/](DF07_pc_stats/) | placeholder |
| DF8 | NPC persona from PC history | V2+ | — | not yet designed |
| DF9 | Admin Ops | V1+30d | — | referenced by R2/R6/R8/R9 |
| DF10 | Event Schema Tooling | V1+30d → V3 | — | referenced by R3 |
| DF11 | DB Fleet + Reality Lifecycle Mgmt | V3+ | — | referenced by R4/C2 |
| ~~DF12~~ | ~~Cross-Reality Analytics & Search~~ | — | — | **WITHDRAWN** (R5 anti-pattern) |
| DF13 | Cross-Session Event Handler | V1 | — | R7-L2 handler pattern referenced |
| DF14 | Vanish Reality Mystery System | V2+ | — | referenced by C1-OW / §12M |
| DF15 | External Integration Auth | V2+ | — | S11.L10 + break-glass referenced |

---

## Sub-subfolder structure (when a DF starts design)

When a DF moves from placeholder to active design, its subfolder expands:

```
DF/DF05_session_group_chat/
├── _index.md                  # status + file list + exported DF5-* IDs
├── 01_spec.md                 # user story + scope + V1 cut
├── 02_ui_flow.md              # wireframes + interaction flow
├── 03_data_model.md           # schema additions; kernel API calls used
├── 04_integration.md          # which services; which events; which contracts/*
├── 05_test_plan.md            # E2E scenarios + chaos-drill coverage (SR7)
└── 06_v1_scope_cut.md         # what ships V1 vs V1+30d vs V2+
```

Each file ~150-250 lines. Not 10-layer strategy.

---

## V1-blocking priorities (from SESSION_HANDOFF agenda)

1. **DF5 Session/Group Chat** — biggest V1 unknown; DF4 + DF7 hang off its session boundaries
2. **DF4 World Rules** — many features reference World Rules; clearer scope after DF5
3. **DF7 PC Stats** — smallest; mostly schema work

Recommend designing in that order.
