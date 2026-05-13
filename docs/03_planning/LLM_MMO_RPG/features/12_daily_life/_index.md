# 12_daily_life — Index

> **Category:** DL — Daily Life (DF1 umbrella)
> **Catalog reference:** [`catalog/cat_12_DL_daily_life.md`](../../catalog/cat_12_DL_daily_life.md) (owns `DL-*` stable-ID namespace)
> **Purpose:** NPC daily routines, world ambient activity, PC → NPC conversion (hidden PC becomes NPC), sinh hoạt. Umbrella for DF1 big feature (V2). V1 scope probably minimal.

**Active:** (empty — no agent currently editing)

---

## Feature list

| ID | Title | Status | File | Commit |
|---|---|---|---|---|

(No features designed yet. First feature will live at `DL_001_<name>.md`.)

---

## Kernel touchpoints (shared across DL features)

- `decisions/deferred_DF01_DF15.md` — DF1 Daily Life (V2 target)
- `decisions/locked_decisions.md` — PC-B2 (offline PC visible + vulnerable + no action) · PC-B3 (prolonged hidden PC → NPC conversion)
- `03_multiverse/` MV12 — fiction_ts advancement; NPC routines scheduled against fiction_ts
- `02_storage/SR06_dependency_failure.md` §12AI — autonomous NPC events during 0-players (SR6-D2 / MV12-D4 integration)
- `05_npc_systems/` — NPC persona template governs what "routine" looks like

---

## V1 scope note

V1 is solo-RP per V-1 roadmap; daily life is heaviest when multi-user/multi-reality (V2+). Most DL features deferred. V1 may include minimal NPC-routine scaffolding (when Elena's shift ends at the teahouse) but not full day/night sim.

Per MV12-D4: V1 reality is paused when 0 players — so offline NPC-routine simulation is V1+30d at earliest. V1 solo-RP doesn't need routines that tick during offline.

---

## Naming convention

`DL_<NNN>_<short_name>.md`. Sequence per-category.

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".
