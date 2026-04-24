<!-- CHUNK-META
source: FEATURE_CATALOG.ARCHIVED.md
chunk: cat_12_DL_daily_life.md
byte_range: 68671-70021
sha256: a957eb9a193559916ae9e8008ab7d37e6182e658b322ab35885ded2860c766f0
generated_by: scripts/chunk_doc.py
-->

## DL — Daily Life (DF1 umbrella)

Scoped for clarity. Everything here is `📦 Deferred` under DF1.

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| DL-1 | NPC daily routines (sleep, work, travel, socialize) | 📦 | V3 | NPC-1 | DF1 |
| DL-2 | Converted PC behavior (when PC becomes NPC) | 📦 | V2 | PCS-7 | DF1 |
| DL-3 | NPC memory decay / periodic summarization | 📦 | V1/V2 | NPC-3 | Partially required for V1 (bounded memory) — design in DF1 |
| DL-4 | PC reclaim UX | 📦 | V2 | PCS-7 | DF1 |
| DL-5 | World simulation tick — 3-mode framework (frozen V1 default / lazy-when-visited V2 / scheduled V3), per-reality World Rule configurable, daily budget cap, platform-tier aware | ✅ | V1 (frozen) · V2 (lazy) · V3 (scheduled) | DF4 World Rules | [01 B3](01_OPEN_PROBLEMS.md#b3-world-simulation-tick--partial), B3-D1..D5 |
| DL-5a | Reality clock (`reality_registry.reality_time`, 1:5 real-to-in-world ratio default) | ✅ | V1 | IF-3 | B3-D4 |
| DL-5b | Lazy-when-visited summary (LLM 1-call per region visit after gap threshold) | 📦 | V2 | DL-5, roleplay-service | B3-D2 |
| DL-5c | Scheduled-tick cron with daily budget cap + idle-skip | 📦 | V3 | DL-5, meta-worker | B3-D3 |
| DL-6 | NPC persona generation from PC history | 📦 | V2 | PCS-10 | DF8, part of DF1 |

---

