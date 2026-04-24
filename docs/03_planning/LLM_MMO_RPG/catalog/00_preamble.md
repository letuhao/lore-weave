<!-- CHUNK-META
source: FEATURE_CATALOG.ARCHIVED.md
chunk: 00_preamble.md
byte_range: 0-2681
sha256: 445fe98c83513a532c7541f0f4d75b157b76d2cabcfb7743d791dbb197c265ed
generated_by: scripts/chunk_doc.py
-->

# Feature Catalog

> **Status:** Living reference — updated as features are discovered or designed.
> **Purpose:** Bird's-eye view of every feature touching this product. Provides stable IDs for cross-reference across design docs. Use this to answer "what does the product actually include?" without having to read every doc.
> **Created:** 2026-04-23

---

## How to use this file

- **Every feature has a stable ID** (e.g. `NPC-3`). Cross-reference from other docs via ID.
- **Status** tells you where the feature stands:
  - ✅ **Designed** — has a concrete design in one of the numbered docs
  - 🟡 **Partial** — designed in broad strokes, has pending decisions
  - 📦 **Deferred** — known, explicitly pushed to a future design doc (tied to a `DF*` in [OPEN_DECISIONS.md](OPEN_DECISIONS.md))
  - ❓ **Open** — identified but no design yet
  - 🚫 **Out of scope** — considered and rejected
- **Tier** tells you when the feature is needed:
  - `V1` — required for first solo RP prototype
  - `V2` — coop scene (2–4 players in one reality)
  - `V3` — full persistent multiverse MMO
  - `V4+` — future vision, exploratory
  - `INFRA` — infrastructure, no tier (always needed)
  - `PLT` — platform-hosted only (self-hosted can skip)
- **Dep** lists upstream features that must exist for this one to work.
- **Design ref** points to the doc section that owns the design detail.

When adding new features:
1. Assign the next ID in its category
2. Set status + tier + dep
3. Point `Design ref` to where the detail lives (or `TBD`)
4. Mark deferred ones with a `DF` tag from [OPEN_DECISIONS.md](OPEN_DECISIONS.md)

---

## Category map

| Code | Category | What it covers |
|---|---|---|
| **IF** | Infrastructure | Storage, sharding, realtime transport — invisible to users |
| **WA** | World Authoring | Book → glossary → reality pipeline; author-side tools |
| **PO** | Player Onboarding | Account, reality discovery, PC creation |
| **PL** | Play Loop | Session, turn, prompt, LLM inference, event broadcast |
| **NPC** | NPC Systems | NPC persona, memory, behavior, canon-faithfulness |
| **PCS** | PC Systems | PC state, lifecycle, offline behavior |
| **SOC** | Social | Session mechanics, PvP, group chat, moderation |
| **NAR** | Narrative / Canon | Canon layers, canonization, world rules |
| **EM** | Emergent / Advanced | Fork, travel, rebase, reality lifecycle |
| **PLT** | Platform | Tiers, billing, admin, moderation at platform level |
| **CC** | Cross-cutting | UI, i18n, accessibility, observability |
| **DL** | Daily Life | Offline PC/NPC routines (DF1 umbrella) |

---

