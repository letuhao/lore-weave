<!-- CHUNK-META
source: FEATURE_CATALOG.ARCHIVED.md
chunk: cat_02_WA_world_authoring.md
byte_range: 40975-42130
sha256: d754eaaff6dfc1d0e4f8fc29a64940e7e8b1612a22364cc679813bac40cffc4a
generated_by: scripts/chunk_doc.py
-->

## WA — World Authoring

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| WA-1 | Book → glossary entity derivation (NPC pool, item pool, location pool) | 🟡 | V1 | — | Relies on glossary-service / knowledge-service (in progress) |
| WA-2 | Reality creation by author (first-reality-of-book = fresh seed) | 🟡 | V1 | IF-3 | [03 §5](03_MULTIVERSE_MODEL.md) |
| WA-3 | Canon lock level per attribute (L1 axiomatic vs L2 seeded) | ✅ | V1 | — | [03 §3](03_MULTIVERSE_MODEL.md), MV1 locked |
| WA-4 | Category-based L1 auto-assignment (magic-system, species → L1) | ✅ | V1 | WA-3 | [03 §3 "Category heuristics"](03_MULTIVERSE_MODEL.md); WA4-D1..D5 locked 2026-04-24 |
| WA-5 | Per-reality world rules (death behavior, paradox tolerance, PvP) | 📦 | V2+ | IF-1 | **DF4 — World Rule feature** |
| WA-6 | Author dashboard — canonization nominations, reality overview | 📦 | V3+ | WA-2 | Related to DF3 |
| WA-7 | Import/export books (portable format) | 📦 | V4+ | — | Marker: [100_FUTURE_FEATURE_STRUCTURED_IMPORT_EXPORT_MEDIA](../100_FUTURE_FEATURE_STRUCTURED_IMPORT_EXPORT_MEDIA.md) |

