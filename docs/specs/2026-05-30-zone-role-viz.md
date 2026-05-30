# Zone-Role Visualization Polish (TMP-Q5)

**Status:** DRAFT
**Author:** Claude (Opus 4.7) + letuhao1994 (PO)
**Created:** 2026-05-30
**Branch:** `mmo-rpg/zone-role-viz` (fresh off main post PR #14)
**Driver:** TMP-Q4 made treasure value legible at a glance via per-pile badges + zone-tier overlay + breakdown. The complementary half — making the zone's *role* legible — is currently invisible to the viewer. The only visual cue for `ZoneRole` today is a colored dot at `zone_center_position` via `overlay-rt.ts`'s `ZONE_CENTER_COLORS`, which is easy to miss + carries no semantic at zoom-out. PO directive: "now that you can see the value, also see the role."

---

## 1. Goal

Surface `ZoneRole` (Wilderness / Hub / Forbidden / Sea) as a first-class visual + tabular channel:

1. **Zone-role canvas overlay** (toggleable, default OFF) — translucent tint per zone keyed by its `zone_role`. Uses the same per-tile `zoneIndexOfPlacement` attribution as TMP-Q4 chunk C so the overlay is provably "the role breakdown rendered as pixels".
2. **MetadataPanel role breakdown** (collapsible, always visible) — counts zones by role, color swatch per row.
3. **Per-book registry override** — `RegistryRef.zone_role_colors: Option<ZoneRoleColors>` so a xianxia book can ship gold-themed Wilderness, jade Hub, etc. without code changes.
4. **Role-aware decoration density bias** — Wilderness gets +20% decoration density (sense of being wild), Hub gets -30% (cleared roads + market), Forbidden + Sea stay at 0 (already empty per backend invariants). Backend-side only.

## 2. Non-Goals

- Adding ZoneRole variants (the 4-variant enum stays; V2+ multiplayer reserves `AllyHome` / `RivalHome` per TMP_001 §2.1)
- Animated transitions when toggling the overlay (instant ON/OFF)
- Author drag-to-edit role colors via UI (registry TOML only)
- Per-zone color overrides (the override is global per role, not per zone instance)
- Backend visual tests (Playwright covers FE; backend has cargo + http_integration)

## 3. Acceptance Criteria

| ID | Criterion | Verifier |
|---|---|---|
| **AC-ZRV-1** | `RegistryRef.zone_role_colors: Option<ZoneRoleColors>` rides the wire as additive Option with `skip_serializing_if = Option::is_none`. V2 byte-identical preserved when None (default `lw` registry omits). | Backend round-trip test + golden regenerated only for treasure cells |
| **AC-ZRV-2** | Backend validates each declared color is a valid u32 + each role field is independently optional (sparse overrides allowed: declare only wilderness=gold, others fall back to defaults). | Backend `Registry::from_file` test pair (accept + reject) |
| **AC-ZRV-3** | `RegistryRef::with_zone_role_colors(ZoneRoleColors)` builder returns `Result` and validates same constraints as `from_file` (LOW: builder-validation-parity precedent from TMP-Q4 chunk A). | Backend builder test |
| **AC-ZRV-4** | Frontend `RegistryRef.zone_role_colors?: ZoneRoleColors` typed; `zoneRoleColor(role, override?)` pure helper picks override → default. | Vitest unit |
| **AC-ZRV-5** | Viewer-store `showZoneRoles: boolean` default false + `setShowZoneRoles` action; LayerToggles checkbox in Polish subsection (below "Treasure bands"). | Vitest + LayerToggles |
| **AC-ZRV-6** | `drawZoneRoleBands` paints each grid tile with its zone's role color at alpha=0.18 via per-tile `zoneIndexOfPlacement` (same attribution as TMP-Q4 chunk C overlay). | Playwright visual golden |
| **AC-ZRV-7** | MetadataPanel role-breakdown collapsible: rows = role · zone count · color swatch; sorted by count desc with role-name asc tiebreaker. | Vitest helper + chromium DOM assertion |
| **AC-ZRV-8** | DecorationPlacer applies role-aware density multiplier: Wilderness ×1.2, Hub ×0.7, Forbidden ×0 (already all-Obstacle), Sea ×0 (no decorations in water zones). | Backend integration test |
| **AC-ZRV-9** | Per-book override demo: `services/tilemap-service/registry/default.toml` declares an example `[registry.zone_role_colors]` block (commented OUT so default lw is None-on-wire, but example syntax visible). Cross-book demo via xianxia_sample.toml ships gold-themed Wilderness. | Manual + xianxia loader test |
| **AC-ZRV-10** | Visual goldens: zone-role overlay ON + OFF against treasure-demo fixture. | Playwright `toHaveScreenshot` |
| **AC-ZRV-11** | Cross-service live-smoke: backend + FE + chromium /play renders the new wire shape end-to-end. | http_integration test (2 new tests for tier wire + RegistryRef carry) |

## 4. Architecture

### Backend: `RegistryRef.zone_role_colors` shape

```rust
// services/tilemap-service/src/types/registry.rs
#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize, Deserialize)]
pub struct ZoneRoleColors {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub wilderness: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub hub: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub forbidden: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sea: Option<u32>,
}

pub struct RegistryRef {
    pub id: String,
    pub version: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub value_band_thresholds: Option<[u32; 4]>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub zone_role_colors: Option<ZoneRoleColors>,
}
```

Named-field struct (not HashMap) keeps TOML clean + matches the chunk-A TMP-Q4 pattern (`value_band_thresholds: [u32; 4]` is also a fixed-shape additive). Sparse overrides via `Option<u32>` per role.

Validation at `Registry::from_file`:
- Each declared color is a valid u32 (intrinsic — TOML loader guarantees)
- No additional constraint (u32 max is fine; any color is renderable)

Builder parity:
```rust
impl RegistryRef {
    pub fn with_zone_role_colors(
        mut self,
        colors: ZoneRoleColors,
    ) -> Result<Self, ZoneRoleColorsError> {
        // Validation hook (currently a no-op, but the shape lets future
        // constraints like "alpha bits must be unset" land cleanly).
        self.zone_role_colors = Some(colors);
        Ok(self)
    }
}
```

### Frontend: `zoneRoleColor` helper + overlay

`frontend-game/src/game/render/zone-role-palette.ts` (NEW pure helper):
```ts
export const ZONE_ROLE_DEFAULTS = {
  wilderness: 0x4ade80, // emerald-400 (existing ZONE_CENTER_COLORS)
  hub:        0x818cf8, // indigo-400
  forbidden:  0xf87171, // rose-400
  sea:        0x60a5fa, // blue-400
} as const;

export interface ZoneRoleColorsTs {
  wilderness?: number;
  hub?: number;
  forbidden?: number;
  sea?: number;
}

export function zoneRoleColor(
  role: string,
  override?: ZoneRoleColorsTs | null,
): number;
```

Returns `override?.[role] ?? ZONE_ROLE_DEFAULTS[role] ?? FALLBACK_COLOR`.
Handles unknown roles (e.g., FE's extended 8-variant `ZoneRole` type that includes `capital`/`arena`/etc. not in backend's 4) by returning a neutral gray.

`drawZoneRoleBands` in `overlay-rt.ts` (NEW function):
- Iterates the grid, calls `zoneIndexOfPlacement({x,y}, zones)`, looks up zone's `zone_role`, paints tile at `zoneRoleColor(role, view.registry_ref?.zone_role_colors)` × alpha=0.18.
- Same per-tile attribution as TMP-Q4 chunk C — provably consistent with the breakdown.
- Stored in a separate RT at depth 53 (between treasure bands RT 55 and paths RT 50).

### Frontend: MetadataPanel role breakdown

`frontend-game/src/components/viewer/role-breakdown.ts` (NEW pure helper):
```ts
export interface ZoneRoleRow {
  role: string;
  count: number;
  color: number;
}
export function computeRoleBreakdown(view: TilemapView): ZoneRoleRow[];
```

Counts zones per role; sorts by count desc with role-name asc tiebreaker.

`MetadataPanel.tsx` adds a new `<RoleBreakdown view={view} />` collapsible BETWEEN existing "zones" and "treasure breakdown" sections.

### Backend: Role-aware decoration density bias

`DecorationPlacer::process` reads the zone's `ZoneRole` from `ZoneSpec` and applies a multiplier to `density_target`:

```rust
const ROLE_DENSITY_MULTIPLIER: [(ZoneRole, f32); 4] = [
    (ZoneRole::Wilderness, 1.2),
    (ZoneRole::Hub, 0.7),
    (ZoneRole::Forbidden, 0.0), // belt-and-suspenders; already skipped
    (ZoneRole::Sea, 0.0),       // belt-and-suspenders; sea has no decoration mask
];
```

Multiplier applied AFTER `decoration_density.fraction_of_free` computes the base count. The multiplier values are hard-coded constants (not author-tunable) — V1 design choice. Future: expose as `RegistryRef.role_decoration_multipliers` if PO needs per-book tuning.

## 5. Chunk decomposition

| Chunk | Files (~) | Logic | Side effects | Scope |
|---|---:|---:|---:|---|
| **A** | 5 BE + 1 FE + 1 doc = 7 | 3 | 1 (wire-shape additive) | Backend `ZoneRoleColors` struct + `RegistryRef.zone_role_colors` field + validation + builder + tests + TS types extension + http_integration test |
| **B** | 6 FE + 1 doc = 7 | 4 | 0 | Pure helpers (`zone-role-palette.ts`, `role-breakdown.ts`) + viewer-store toggle + LayerToggles + overlay-rt `drawZoneRoleBands` + MetadataPanel RoleBreakdown + vitest |
| **C** | 3 BE + 2 FE + 1 doc = 6 | 2 | 0 | DecorationPlacer role-aware density bias + backend tests + Playwright visual goldens + per-book override demo in xianxia_sample.toml |

Total projected: 20 files / 9 logic / 1 side effect ⇒ XL classification (gate confirmed).

## 6. Test plan (chunk-level rolled up)

| Test | Chunk | Verifies |
|---|---|---|
| `zone_role_colors_round_trips_with_all_fields` | A | Wire shape |
| `zone_role_colors_sparse_round_trip` | A | Sparse override |
| `registry_ref_zone_role_colors_skip_serializing_when_none` | A | V2 byte-identical |
| `registry_ref_builder_with_zone_role_colors` | A | Builder parity |
| `pre_q5_fixture_deserializes_without_zone_role_colors` | A | Backward compat |
| `render_endpoint_emits_zone_role_colors_when_registry_declares` | A | HTTP wire |
| `render_endpoint_omits_zone_role_colors_for_default_registry` | A | HTTP V2 byte-identical |
| `zone_role_color_helper_uses_override` | B | FE pure helper |
| `zone_role_color_helper_falls_back_to_defaults` | B | FE default fallback |
| `zone_role_color_helper_unknown_role_returns_fallback` | B | FE defensive |
| `compute_role_breakdown_counts_per_role` | B | Aggregation |
| `compute_role_breakdown_sorts_desc_with_tiebreaker` | B | Determinism |
| `viewer_store_show_zone_roles_default_false` | B | AC-ZRV-5 default |
| `viewer_store_show_zone_roles_independent_from_other_toggles` | B | Independence |
| `decoration_placer_applies_wilderness_1_2x_multiplier` | C | Backend bias |
| `decoration_placer_applies_hub_0_7x_multiplier` | C | Backend bias |
| `decoration_placer_forbidden_zero_density` | C | Skip invariant |
| `zone-role-visual-regression chromium` | C | 2 Playwright goldens (overlay ON + OFF) |
| `MetadataPanel role-breakdown displays N role rows` | C | DOM assertion gated on overlay test |

## 7. Risks + mitigations

| Risk | Mitigation |
|---|---|
| Decoration bias regression breaks existing AC-DECO-8 fixture (which already has empty treasure_tiers; depends on decoration count threshold) | Bias only applies to Wilderness/Hub zones; if the test fixture uses Wilderness zones, count goes UP not down. Verify in chunk C VERIFY |
| Zone-role overlay color collision with treasure-bands overlay (both at alpha=0.18) | Roles at depth 53, treasure bands at 55 — treasure bands paint OVER roles. Visually layered as expected. Document in chunk B |
| Frontend ZoneRole type covers 8 values but backend wire ships only 4 | `zoneRoleColor` helper handles unknown roles via fallback color. Document the type-vs-wire gap |
| TOML inline-table syntax for `[registry.zone_role_colors]` confuses authors | Provide commented-out example in `default.toml`; xianxia_sample.toml ships a working override |
| Per-book validation might miss invalid color (u32 max is gray-ish but valid) | Accept-and-document: any u32 is renderable; no validation needed beyond TOML parse |
| Visual golden flake across platforms | Same per-platform pin + 2% tolerance as TMP-Q4 chunk C |

## 8. Out of scope

- Additional ZoneRole variants (`AllyHome` / `RivalHome` — V2+ multiplayer per TMP_001 §2.1)
- Role-name display localization
- Animated overlay transitions
- Per-zone role-color overrides (override is global per role)
- LLM-narrated role descriptions ("you enter a hub town" — TMP_008 V2)
- Backend visual tests beyond integration

## 9. Ground-truth verification table

| Reference | File:line | Verified |
|---|---|---|
| `ZoneRole` enum (4 variants) | `services/tilemap-service/src/types/zone.rs:16` | YES |
| `RegistryRef` struct (current shape) | `services/tilemap-service/src/types/registry.rs:185-218` | YES (TMP-Q4 chunk A added value_band_thresholds; TMP-Q5 adds alongside) |
| `Registry::from_file` validation hook | `services/tilemap-service/src/registry.rs:172` | YES |
| `DecorationPlacer::process` | `services/tilemap-service/src/engine/modificators/decoration_placer.rs` | YES (chunk B of TMP-Q1) |
| `ZoneRuntime.zone_role` (FE TS) | `frontend-game/src/types/tilemap.ts` (8-variant union) | YES — wider than backend's 4 |
| `zoneIndexOfPlacement` shared attribution | `frontend-game/src/components/viewer/zone-breakdown.ts` | YES (TMP-Q4 chunk C) |
| `OverlayRtHandle` pattern | `frontend-game/src/game/render/overlay-rt.ts` | YES (chunk C established setTreasureBandsVisible) |
| `MetadataPanel` collapsible section pattern | `frontend-game/src/components/viewer/MetadataPanel.tsx` | YES |
| `LayerToggles` Polish subsection | `frontend-game/src/components/viewer/LayerToggles.tsx` | YES (TMP-Q3 chunk A) |
| `treasure-demo.json` fixture for visual goldens | `frontend-game/public/templates/treasure-demo.json` | YES (TMP-Q4 chunk C) |

**Note on prerequisite branches:** PR #14 (`mmo-rpg/terrain-blend-shader` — TMP-Q3 + TMP-Q4) is open against main. TMP-Q5 starts fresh off main; when PR #14 merges, this branch rebases. Files touched by both (e.g., `viewer-store.ts`, `overlay-rt.ts`, `MetadataPanel.tsx`) will need conflict resolution at rebase time — additive patterns make conflicts mostly mechanical.

## 10. Known limitations

- **Bias multipliers hard-coded** — V1 ships fixed `[1.2, 0.7, 0, 0]` values. Per-book override of these multipliers would require a second `RegistryRef.role_decoration_multipliers` field. Deferred.
- **No author UI for role colors** — TOML edit only. UI editor V3+.
- **Cross-OS goldens** — Windows-x86_64 pinned per chunk-C TMP-Q3 LOW-4 precedent.
- **8-variant FE type vs 4-variant BE wire** — `zoneRoleColor` handles unknown roles via fallback; the type narrowing is a pre-existing gap.
