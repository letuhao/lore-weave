# 15_organization — Index

> **Category:** ORG — Organizations / Factions / Guilds / Sects (V3 deferred — pre-staged 2026-04-26 to reserve namespace + capture V1+ hooks)
> **Catalog reference:** `catalog/cat_15_ORG_organization.md` (NOT YET CREATED — defer to V3 actual design start)
> **Purpose:** In-game collective entities (factions / guilds / sects / môn phái / dynasties) with shared treasury + membership + hierarchy + reputation + diplomatic relationships. Foundation for V3 Strategy module.

**Active:** none — folder is V3 reservation placeholder.

**Status:** **V3 RESERVED 2026-04-26.** No design files. No catalog file. No boundary registration. See [`00_V2_RESERVATION.md`](00_V2_RESERVATION.md) for V3 scope sketch.

---

## Why this folder exists pre-design

User confirmed 2026-04-26 that organization system is V3 deferred (full faction/guild system requires faction treasury + hierarchical income + diplomacy from RES_001 V3), BUT requested pre-staging the folder NOW to:
- Reserve `ORG-*` namespace
- Anchor RES_001 EntityRef::Faction(FactionId) variant (V3 reserved enum)
- Capture wuxia/xianxia môn phái patterns + CK3 dynasty pattern for V3 Strategy module
- Document V1 limitations (no factions; only individual NPC reputation V1)

Pattern matches `13_quests/` + `14_crafting/` discipline: minimal V3 reservation, not full design.

---

## Feature list (V3 deferred)

| ID | Conversational name | Title | Status | File | Commit |
|---|---|---|---|---|---|
| (reservation) | **00_V2_RESERVATION.md** — V3 placeholder (filename keeps V2 prefix for consistency; content marks V3) | RESERVED 2026-04-26 | [`00_V2_RESERVATION.md`](00_V2_RESERVATION.md) | (this commit) |
| ORG_001 | (V3 — not designed) | Faction Foundation: Faction aggregate + membership + treasury + hierarchy + diplomatic relations + faction reputation | NOT YET DRAFTED — V3 deferred | (TBD V3) | n/a |

---

## Naming convention

`ORG_<NNN>_<short_name>.md`. Sequence per-category. Reserve ORG_001 for foundation; ORG_002+ for extensions (sect rivalry / political dynasty / merchant guild / mercenary company).

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature". When V3 design begins:
1. Create `catalog/cat_15_ORG_organization.md`
2. Update `_boundaries/01_feature_ownership_matrix.md` Stable-ID prefix ownership row to add `ORG-*`
3. Coordinate with RES_001 V3 deferrals (RES-D19 faction treasury + RES-D20 hierarchical income + RES-D23 tax + RES-D24 diplomatic exchange)
4. Coordinate with PLT_001 Charter (already-locked co-author grants — different concept; ORG is in-fiction collective vs PLT_001 platform-level role)
5. Promote V2_RESERVATION → ORG_001 DRAFT via `[boundaries-lock-claim+release]` commit

---

## Coordination note

**Boundary clarity at design time:**
- **PLT_001 Charter** = platform-level co-author grants (real-world authors collaborating on a reality) — V1 LOCKED
- **ORG_001 (future)** = in-fiction collective entities (NPCs and PCs as members of a sect, guild, dynasty) — V3
- These are DIFFERENT concepts despite both involving "membership." Don't conflate.

ORG is the natural home for wuxia/xianxia môn phái (sects) — central trope in genre, but V3 because it requires full Strategy module substrate.
