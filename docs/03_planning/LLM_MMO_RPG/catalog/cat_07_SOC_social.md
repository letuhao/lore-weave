<!-- CHUNK-META
source: FEATURE_CATALOG.ARCHIVED.md
chunk: cat_07_SOC_social.md
byte_range: 54550-55586
sha256: 7e5dfed2b4c37ff75cd20b7e7ff8604c7341e59474daf76a754ab855a5cb562d
generated_by: scripts/chunk_doc.py
-->

## SOC — Social

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| SOC-1 | Session as social unit (N PCs + M NPCs in one context) | 📦 | V1 | PL-1 | **DF5 — Session feature** |
| SOC-2 | Public session (in-region, all co-located participants join) | 📦 | V1 | SOC-1 | DF5 |
| SOC-3 | Private session (invite-only) | 📦 | V2 | SOC-1 | DF5 |
| SOC-4 | Whisper (1-to-1 private within session or across) | 📦 | V2 | SOC-1 | DF5 |
| SOC-5 | PvP within session | 📦 | V2 | SOC-1, WA-5 | DF5 + DF4 consent |
| SOC-6 | Multi-PC parties / raids / guilds | 🚫 | — | — | Explicitly rejected — sessions replace parties (PC-D1) |
| SOC-7 | Global chat | 🚫 | — | — | Explicitly rejected — session only (PC-D3) |
| SOC-8 | User reporting / content moderation UI | 📦 | PLT | SOC-1 | Standard platform feature |
| SOC-9 | Shadow-ban / sanctions | 📦 | PLT | SOC-8 | Standard |
| SOC-10 | NSFW opt-in / age verification | 📦 | PLT | — | [01 E2](01_OPEN_PROBLEMS.md) |

