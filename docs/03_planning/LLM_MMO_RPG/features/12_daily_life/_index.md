# 12_daily_life — Index

> **Category:** DL — Daily Life (DF1 umbrella)
> **Catalog reference:** [`catalog/cat_12_DL_daily_life.md`](../../catalog/cat_12_DL_daily_life.md) (owns `DL-*` stable-ID namespace)
> **Purpose:** NPC daily routines, world ambient activity, PC → NPC conversion (hidden PC becomes NPC), sinh hoạt. Umbrella for DF1 big feature.
>
> ⚠️ **RE-SCOPED 2026-07-26 — V2 → V1 (PO decision, AUD-F13).** This index previously read *"Umbrella for DF1 big feature (V2). V1 scope probably minimal."* That is superseded: **daily life ships in V1**, split by cost rather than by phase (DL-A1) — deterministic ambient simulation in V1, generative simulation still V2+/V3+ under B3-D2/B3-D3 unchanged. See [`DL_001_daily_life_foundation.md`](DL_001_daily_life_foundation.md) §1.

**Active:** (empty — no agent currently editing)

---

## Feature list

| ID | Title | Status | File | Commit |
|---|---|---|---|---|
| DL_001 | Daily Life Foundation ("Sinh hoạt") | **DRAFT 2026-07-26** | [`DL_001_daily_life_foundation.md`](DL_001_daily_life_foundation.md) | pending |

**Exported IDs:** `DL-A1..A8` axioms · `DL-D1..D15` decisions · `DL-DF1..DF6` deferrals · `DL-Q4` open (`Q1..Q3` resolved) · `AC-DL-1..18`.
**Closes:** DF1 · DF8 (merged) · AUD-F13. **Amends:** B3-D1 (narrowly — §1.1). **Interacts:** AUD-F11 (ambient vs player-facing economy boundary).

---

## Kernel touchpoints (shared across DL features)

- `decisions/deferred_DF01_DF15.md` — DF1 Daily Life (V2 target)
- `decisions/locked_decisions.md` — PC-B2 (offline PC visible + vulnerable + no action) · PC-B3 (prolonged hidden PC → NPC conversion)
- `03_multiverse/` MV12 — fiction_ts advancement; NPC routines scheduled against fiction_ts
- `02_storage/SR06_dependency_failure.md` §12AI — autonomous NPC events during 0-players (SR6-D2 / MV12-D4 integration)
- `05_npc_systems/` — NPC persona template governs what "routine" looks like

---

## V1 scope note

> ⚠️ **SUPERSEDED 2026-07-26 by AUD-F13 + DL-A1.** Retained below for traceability.

The reasoning that dated this note is worth naming, because it is the same stale premise the
medium correction (docs `08`–`10`) has been unwinding elsewhere: **"V1 is solo-RP"** predates the
2026-06-20 correction to a rendered 2D/2.5D **MMO**. Daily life was deferred because a solo text-RP V1
does not need it — a persistent multiplayer world does.

**MV12-D4 is no longer an obstacle** (rather than being overridden): it says a V1 reality is *paused*
when 0 players, which would matter only to a system that ticks NPCs forward. DL-D1 evaluates routines
**on read** as a function of `fiction_time`, so a paused reality and a running one return the same
answer. Zero offline compute — B3-D1's *"no between-session activity"* is preserved literally.

<details>
<summary>Original note (2026-04-23 era)</summary>

V1 is solo-RP per V-1 roadmap; daily life is heaviest when multi-user/multi-reality (V2+). Most DL features deferred. V1 may include minimal NPC-routine scaffolding (when Elena's shift ends at the teahouse) but not full day/night sim.

Per MV12-D4: V1 reality is paused when 0 players — so offline NPC-routine simulation is V1+30d at earliest. V1 solo-RP doesn't need routines that tick during offline.

</details>

---

## Naming convention

`DL_<NNN>_<short_name>.md`. Sequence per-category.

## How to add a feature

See root [`../_index.md`](../_index.md) § "How to add a new feature".
