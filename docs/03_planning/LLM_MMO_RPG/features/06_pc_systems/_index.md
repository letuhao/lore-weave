# 06_pc_systems — Index

> **Category:** PCS — PC Systems
> **Catalog reference:** [`catalog/cat_06_PCS_pc_systems.md`](../../catalog/cat_06_PCS_pc_systems.md) (owns `PCS-*` stable-ID namespace)
> **Purpose:** PC sheet design — identity layers, inventory, relationships, simple state fields (no RPG mechanics per F4 ACCEPTED). Feeds into DF7 PC Stats & Capabilities.

**Active:** (empty — no agent currently editing)

---

## Feature list

| ID | Title | Status | File | Commit |
|---|---|---|---|---|

(No features designed yet. First feature will live at `PCS_001_<name>.md`.)

---

## Kernel touchpoints (shared across PCS features)

- `04_player_character/` (entire subfolder) — PC-A1..E3 decisions already locked
- `decisions/locked_decisions.md` — PC-A1..E3 + PC-C3 "simple state-based" + F4 "minimal RPG mechanics"
- `02_storage/R08_npc_memory_split.md` — `npc_pc_relationship` edge carries PC-side state too
- `02_storage/SR11_turn_ux_reliability.md` — TurnState + PresenceState apply per-PC
- `03_multiverse/` MV12 — fiction_ts snapshots of PC sheet at time-points (PC state changes over fiction-time)

---

## Naming convention

`PCS_<NNN>_<short_name>.md`. Sequence per-category.

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".
