<!-- CHUNK-META
source: FEATURE_CATALOG.ARCHIVED.md
chunk: cat_06_PCS_pc_systems.md
byte_range: 53160-54550
sha256: 11469db62fbb63f65698658eb550a5bd56940b565d1981854969dc950658510e
generated_by: scripts/chunk_doc.py
-->

## PCS — PC Systems

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| PCS-1 | PC state projection (location, status, stats, inventory) | ✅ | V1 | IF-1 | [02 §5.1](02_STORAGE_ARCHITECTURE.md), [04 §8](04_PLAYER_CHARACTER_DESIGN.md) |
| PCS-2 | PC inventory + item origin reality | ✅ | V1 | PCS-1 | [02 §5.1](02_STORAGE_ARCHITECTURE.md) (MV5 primitive P5) |
| PCS-3 | PC ↔ NPC relationship tracking | 🟡 | V1 | PCS-1 | [02 §5.1](02_STORAGE_ARCHITECTURE.md) |
| PCS-4 | PC stats model (simple state-based, no RPG mechanics) | 🟡 | V1 | PCS-1 | [04 §5.3](04_PLAYER_CHARACTER_DESIGN.md), PC-C3 locked, **DF7** concrete schema |
| PCS-5 | PC offline mode (visible + vulnerable) | 🟡 | V1 | PCS-1 | [04 §4.2](04_PLAYER_CHARACTER_DESIGN.md), PC-B2 locked |
| PCS-6 | PC `/hide` command + hidden status | 🟡 | V1 | PCS-5 | [04 §4.2](04_PLAYER_CHARACTER_DESIGN.md) |
| PCS-7 | PC-as-NPC conversion after prolonged hiding | 📦 | V2 | PCS-6, NPC-8 | **DF1 — Daily Life** |
| PCS-8 | PC death (event emission, per-reality outcome) | 🟡 | V1 | PCS-1, WA-5 | [04 §4.1](04_PLAYER_CHARACTER_DESIGN.md), PC-B1 locked; outcomes in **DF4** |
| PCS-9 | PC reclaim from NPC mode | 📦 | V2 | PCS-7 | **DF1** |
| PCS-10 | PC persona generation (LLM persona for NPC mode) | 📦 | V2 | PCS-7 | **DF8 — NPC persona from PC history** |

