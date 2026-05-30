# Chunk B — FE Overlay + Role Breakdown + Viewer Toggle (TMP-Q5)

**Spec:** [`docs/specs/2026-05-30-zone-role-viz.md`](../specs/2026-05-30-zone-role-viz.md)
**Chunk A:** `ae4cd096` (BE wire shape: `RegistryRef.zone_role_colors`)
**Branch:** `mmo-rpg/zone-role-viz`
**Size:** XL (11 files / 5 logic / 0 side effects — FE-only)
**Goal:** Render the chunk-A wire shape as a user-visible zone-role overlay + MetadataPanel role breakdown. Per-tile attribution uses the same `zoneIndexOfPlacement` discipline as TMP-Q4 chunk C so the canvas paint and the breakdown table agree.

## Architecture

### New pure helpers
- `zone-attribution.ts` — `tileMaskGet` + `zoneIndexOfPlacement` (reimplemented on this branch since PR #14 hasn't merged; rebase merges with TMP-Q4 chunk-C's `zone-breakdown.ts`)
- `zone-role-palette.ts` — `zoneRoleColor(role, override?)` + `zoneRoleLabel(role)` + `ZONE_ROLE_DEFAULTS` (4 BE roles) + `ZONE_ROLE_FALLBACK` (gray for unknown)
- `role-breakdown.ts` — `computeRoleBreakdown(view)` returns `ZoneRoleRow[]` sorted by count desc + role asc tiebreaker

### Wire-up
- `viewer-store.ts` — `showZoneRoles: boolean` default false + `setShowZoneRoles`
- `LayerToggles.tsx` — Polish subsection + "Zone roles" checkbox (Polish section didn't exist pre-PR-#14 on main; this chunk adds it)
- `overlay-rt.ts` — `drawZoneRoles` per-tile via `zoneIndexOfPlacement` → `zoneRoleColor` at alpha=0.18; separate RT at depth 53; `setZoneRolesVisible(v)` handle
- `WorldScene.ts` — `applyViewerStoreVisibility` routes `showZoneRoles`
- `MetadataPanel.tsx` — `RoleBreakdown` collapsible with `useMemo` (MED-2 chunk-C precedent); color swatch + role · count rows

### Resolution chain
- `zoneRoleColor` resolution: `override?.[role]` (with `Number.isFinite` defense) → `ZONE_ROLE_DEFAULTS[role]` → `ZONE_ROLE_FALLBACK`
- FE-only roles (capital/arena/mine_camp/town) — not in `ZONE_ROLE_DEFAULTS`, fall through to FALLBACK gray
- `drawZoneCenters` keeps its 8-role `ZONE_CENTER_COLORS` map (handles FE-only variants); the 4 shared BE-wire roles are pinned to match `ZONE_ROLE_DEFAULTS` via a palette-identity test (MED-1 from round-2 /review-impl)

## File list (11 files)

| # | File | Action | Purpose |
|---|---|---|---|
| 1 | `frontend-game/src/components/viewer/zone-attribution.ts` | NEW | `tileMaskGet` + `zoneIndexOfPlacement` |
| 2 | `frontend-game/src/game/render/zone-role-palette.ts` | NEW | `zoneRoleColor` + `zoneRoleLabel` + defaults |
| 3 | `frontend-game/src/components/viewer/role-breakdown.ts` | NEW | `computeRoleBreakdown` |
| 4 | `frontend-game/src/store/viewer-store.ts` | MOD | `showZoneRoles` toggle |
| 5 | `frontend-game/src/components/viewer/LayerToggles.tsx` | MOD | Polish section + checkbox |
| 6 | `frontend-game/src/game/render/overlay-rt.ts` | MOD | `drawZoneRoles` + RT handle + export `ZONE_CENTER_COLORS` |
| 7 | `frontend-game/src/game/scenes/WorldScene.ts` | MOD | Subscribe |
| 8 | `frontend-game/src/components/viewer/MetadataPanel.tsx` | MOD | `RoleBreakdown` section with `useMemo` |
| 9 | `frontend-game/tests/components/zone-attribution.test.ts` | NEW | 7 cases |
| 10 | `frontend-game/tests/game/zone-role-palette.test.ts` | NEW | 10 cases (incl. MED-1 palette identity) |
| 11 | `frontend-game/tests/components/role-breakdown.test.ts` | NEW | 8 cases (incl. LOW-4 sum invariant) |
| 12 | `frontend-game/tests/store/viewer-store.test.ts` | MOD | 3 toggle tests |

## Invariants

1. **Default OFF** — author opts in; depth 53 (between paths 50 and props 100).
2. **Single source of truth for zone-of-tile** — `zoneIndexOfPlacement` shared between overlay paint and (future) per-tile attribution. Panel row attribution uses zone iteration (different shape, but both consume `zoneRoleColor` for color).
3. **Defensive role lookup** — `zoneRoleColor` handles null/undefined/NaN override + unknown roles via FALLBACK.
4. **Sparse overrides honored** — `wilderness: 0xff0000` override applies only to wilderness; hub/forbidden/sea fall back to defaults.
5. **Memoization on view ref** — `RoleBreakdown` `useMemo([view])`.
6. **Palette identity (MED-1 from round-2 /review-impl)** — the 4 shared BE-wire role hex values match between `ZONE_CENTER_COLORS` (dots) and `ZONE_ROLE_DEFAULTS` (overlay tint + panel swatches). Test-pinned.
7. **Sum invariant (LOW-4 from round-2 /review-impl)** — `sum(row.count) == view.zones.length`. Test-pinned.

## Test plan

| Test | File | Verifies |
|---|---|---|
| `tile_mask_get` reads bits + OOB defense + sparse mask | zone-attribution | Bitmap read |
| `zone_index_*` (bitmap + Voronoi + empty) | zone-attribution | Attribution algorithm |
| `zoneRoleColor` defaults + override + sparse + null + undefined + NaN + unknown | zone-role-palette | Helper |
| `palette identity ZONE_CENTER_COLORS == ZONE_ROLE_DEFAULTS` (4 roles) | zone-role-palette | MED-1 from round 2 |
| `compute_role_breakdown` empty + counts + sort + override + sparse + fallback + zone_ids sorted + sum invariant | role-breakdown | Aggregation + LOW-4 |
| `show_zone_roles` default false + flip + independence from layers | viewer-store | Toggle |

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Palette drift between dot map + overlay map | MED-1 identity test |
| Overlay color collision with future treasure-bands (PR #14) | Different depths: roles 53, bands 55 (bands paint over) |
| Zone-attribution helper duplicates PR #14 chunk-C version at rebase | Identical shape; mechanical merge |
| 8-variant FE type vs 4-variant BE wire | FALLBACK gray for unknown roles |
| Sum invariant breaks if future filter is added | LOW-4 test pin |
| testid unused today | Forward-anchor for chunk-C visual goldens |

## Out of scope (chunk C)

- Backend role-aware decoration density bias
- Per-book demo in xianxia_sample.toml
- Playwright visual goldens
- Role-name localization / drill-down
