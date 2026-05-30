# Chunk B — Per-pile badges + Inspector treasure section (TMP-Q4)

**Spec:** [`docs/specs/2026-05-30-value-band-treasures.md`](../specs/2026-05-30-value-band-treasures.md)
**Chunk A:** `33df910d` (wire shape: tier_index + value_band_thresholds + 6 review findings)
**Branch:** stacks on `mmo-rpg/terrain-blend-shader`
**Size:** M (6 files / 4 logic / 0 side effects — FE-only)
**Goal:** Render the wire-shape data (chunk A) as user-visible badges. Each treasure pile + its guard gets a small colored badge encoding the value band; TileInspector shows the value/tier/band-name when shift-clicking a treasure tile. Per-book registries can override the band scale via `RegistryRef.value_band_thresholds`.

## Architecture

### `treasure-badge.ts` (NEW) — pure helper module

```ts
export const VALUE_BAND_DEFAULTS = [500, 2000, 5000, 12000] as const;

// 5 bands matching HoMM3-ish tier reading: low / low-mid / mid / high / gilt.
// Colors chosen from Tailwind palette (matches the rest of the viewer UI).
export const BAND_COLORS = [
  0x9ca3af, // low      — slate-400
  0x10b981, // low-mid  — emerald-500
  0x3b82f6, // mid      — blue-500
  0xa855f7, // high     — purple-500
  0xfbbf24, // gilt     — amber-400
] as const;

export const BAND_LABELS = [
  'low', 'low-mid', 'mid', 'high', 'gilt',
] as const;

/**
 * Pick a 0..4 band index for a treasure pile value.
 *
 * LOW-6 defensive — TS tuple `[number, number, number, number]` doesn't
 * enforce ascending at runtime. The backend validates at registry load,
 * but unit-test stubs or buggy backend builds could still ship invalid
 * arrays. This helper:
 *   1. Coerces NaN / non-finite thresholds to the default scale.
 *   2. Sorts the threshold array ascending in-place (locally) so even
 *      non-ascending input produces a deterministic band assignment.
 *   3. Clamps the input value to a finite u32 range.
 */
export function pickValueBand(
  value: number,
  thresholds?: readonly [number, number, number, number] | null,
): number {
  const safeValue = Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0;
  const raw = thresholds && thresholds.every(Number.isFinite)
    ? [...thresholds]
    : [...VALUE_BAND_DEFAULTS];
  raw.sort((a, b) => a - b);
  for (let i = 0; i < 4; i++) {
    if (safeValue < raw[i]) return i;
  }
  return 4;
}

export function bandLabel(band: number): string {
  const i = Math.max(0, Math.min(4, band));
  return BAND_LABELS[i];
}

export function bandColor(band: number): number {
  const i = Math.max(0, Math.min(4, band));
  return BAND_COLORS[i];
}
```

### `object-overlay.ts` (MOD) — badge graphics

**MED-1 fix from chunk-B self-review:** Badge stamp gates on `kind === 'treasure'` ONLY, NOT on the broader `value !== undefined && tier_index !== undefined` predicate. A `MonsterLair` guard inherits the pile's `tier_index` but its `value` is the guard's *strength* (`pile_value / 10`), not the pile's gold-equivalent. Rendering a band based on strength would mislead — a 12000-gold pile with a 1200-strength guard would show "gilt" pile + "low-mid" guard, breaking the consistent-reading invariant. So: badges only on treasure piles; guards rely on the inspector to surface the tier_index.

For each placement with `kind === 'treasure' && value !== undefined`:
- Compute `band = pickValueBand(p.value, view.registry_ref?.value_band_thresholds ?? null)`
- Add a `Phaser.GameObjects.Arc` (circle) to the chunk's container at sprite top-right corner
- Color = `bandColor(band)`
- Size = `BADGE_RADIUS_PX = 4` (COSMETIC-1: const at top of file)
- Position offset: `(screenX + displayPx * 0.35, screenY - displayPx * 0.85)` — upper-right of the sprite for any tier size
- **LOW-3 fix:** Depth = `BADGE_DEPTH_BASE + p.anchor.y` where `BADGE_DEPTH_BASE = 100_000`. Plant the badge layer well above any sprite-on-row-N depth so adjacent sprites in row N+1 (depth `100 + N+1`) cannot obscure it. Within the badge layer, anchor.y still sorts so closer badges paint on top of farther badges.

LOD: badges have their own visibility band — hide when `cam.zoom < 0.4` because they're small + unreadable at extreme zoom-out. Implementation: store badges in a separate `badgeArcs` array per chunk and toggle visibility in `update()`.

```ts
const BADGE_RADIUS_PX = 4;
const BADGE_DEPTH_BASE = 100_000;
const BADGE_ALPHA = 0.95;
const BADGE_BORDER_COLOR = 0x0f172a;     // slate-900
const BADGE_BORDER_ALPHA = 0.7;
const BADGE_LOD_MIN_ZOOM = 0.4;

// Inside the placement loop:
if (p.kind === 'treasure' && p.value !== undefined && p.value !== null) {
  const band = pickValueBand(p.value, view.registry_ref?.value_band_thresholds ?? null);
  const badge = scene.add.circle(
    screenX + displayPx * 0.35,
    screenY - displayPx * 0.85,
    BADGE_RADIUS_PX,
    bandColor(band),
    BADGE_ALPHA,
  ).setStrokeStyle(1, BADGE_BORDER_COLOR, BADGE_BORDER_ALPHA);
  badge.setDepth(BADGE_DEPTH_BASE + p.anchor.y);
  entry.container.add(badge);
  entry.badgeArcs.push(badge);
}
```

In `update()`:
```ts
const showBadges = cam.zoom >= BADGE_LOD_MIN_ZOOM;
for (const arc of entry.badgeArcs) {
  arc.visible = visible && showBadges;
}
```

### `viewer-store.ts` (MOD) — pass thresholds to inspector

Add to `InspectorPayload`:
```ts
export interface InspectorPayload {
  // ... existing fields ...
  /** TMP-Q4 — per-book value-band thresholds when the rendered registry
   *  declared them. `null` when the registry omits the field (fallback
   *  to VALUE_BAND_DEFAULTS in the inspector). */
  valueBandThresholds: readonly [number, number, number, number] | null;
}
```

`lookupAt` extracts:
```ts
const valueBandThresholds = view.registry_ref?.value_band_thresholds ?? null;
return { ..., valueBandThresholds };
```

### `TileInspector.tsx` (MOD) — Treasure section

**LOW-1 + LOW-2 fixes from self-review:** the inspector displays differently for treasure piles vs guards even though both carry `tier_index`:
- **Treasure pile (`p.kind === 'treasure'`):** show value (with `gold` unit), tier, and band swatch.
- **Guard (`p.kind === 'monster_lair'`) with `tier_index`:** show tier only (NO band, NO `gold` unit on value — its `value` is strength). The existing generic `value` row already handles `value` without units.

The badge row (color swatch + label) gates on `p.kind === 'treasure'`:

```tsx
{p.kind === 'treasure' && p.value !== undefined && p.value !== null && (
  <>
    <Row k="treasure value" v={`${p.value} gold`} />
    {p.tier_index !== undefined && p.tier_index !== null && (
      <Row k="treasure tier" v={`tier ${p.tier_index}`} />
    )}
    {(() => {
      const band = pickValueBand(p.value, inspector.valueBandThresholds);
      return (
        <Row
          k="band"
          v={
            <span className="inline-flex items-center gap-1">
              <span
                className="inline-block w-2 h-2 rounded-full"
                style={{
                  backgroundColor: `#${bandColor(band).toString(16).padStart(6, '0')}`,
                }}
              />
              {bandLabel(band)}
            </span>
          }
        />
      );
    })()}
  </>
)}
{p.kind === 'monster_lair' && p.tier_index !== undefined && p.tier_index !== null && (
  <Row k="guard tier" v={`tier ${p.tier_index} (inherited)`} />
)}
```

`Row.v` type widens from `string` to `string | ReactNode`. Existing callers pass strings — backward compatible. The treasure section sits inside the existing `details > "V2 placement detail"` block.

## File list (6 files)

| # | File | Action | Lines (est) | Purpose |
|---|---|---|---|---|
| 1 | `frontend-game/src/game/render/treasure-badge.ts` | NEW | ~70 | Pure helper: constants, pickValueBand, bandColor, bandLabel |
| 2 | `frontend-game/src/game/render/object-overlay.ts` | MOD | ~30 | Badge graphics + LOD cull at zoom < 0.4 |
| 3 | `frontend-game/src/store/viewer-store.ts` | MOD | ~8 | Add valueBandThresholds to InspectorPayload + lookupAt |
| 4 | `frontend-game/src/components/viewer/TileInspector.tsx` | MOD | ~30 | Treasure section with value/tier/band display |
| 5 | `frontend-game/tests/game/treasure-badge.test.ts` | NEW | ~120 | pickValueBand: defaults, custom thresholds, defensive (non-ascending, NaN), bandColor, bandLabel |
| 6 | `frontend-game/tests/store/viewer-store.test.ts` | MOD | ~20 | Extend existing test to assert valueBandThresholds flows from view to inspector |

## Invariants

1. **V0/V1 backward compat** — pre-Q4 placements (no `value`) get no badge. Pre-Q4 placements may have `value` (the existing `value: Option<u32>` was always there) — the badge gate also requires `kind === 'treasure'` so legacy treasures with no `tier_index` still render a band based on value alone.
2. **Badge gate = `kind === 'treasure'` (MED-1)** — guards (`MonsterLair`) inherit `tier_index` but their `value` is strength, not gold. Stamping a band on a guard would mislead. Badge is the pile's, not the guard's.
3. **Defensive clamp** — `pickValueBand` accepts any input without throwing. Non-finite value → 0 (lowest band). Non-finite thresholds → defaults. Non-ascending thresholds → sorted locally.
4. **LOD continuity** — badges visible iff `cam.zoom >= BADGE_LOD_MIN_ZOOM` (0.4). Hiding at extreme zoom-out prevents visual clutter.
5. **Color stability** — `bandColor` / `bandLabel` always return defined values (clamp at index bounds). No undefined / out-of-bounds on band 5+ or -1.
6. **Inspector consistency** — the badge color in object-overlay MUST match the swatch in TileInspector. Both pull from `bandColor(pickValueBand(value, thresholds))` so a future BAND_COLORS change updates both surfaces.
7. **Badge depth above sprites (LOW-3)** — `BADGE_DEPTH_BASE = 100_000` puts the badge layer above every sprite (depth `100 + anchor.y`, max anchor.y = grid_size.height ≪ 100_000). Adjacent sprites cannot obscure a badge regardless of row.

## Test plan

| Test | File | Verifies |
|---|---|---|
| `pickValueBand_default_thresholds_5_bands` | treasure-badge.test.ts | 4 thresholds map to 5 distinct bands; boundary values inclusive vs exclusive |
| `pickValueBand_value_below_first_threshold_returns_0` | same | 0 / 1 / 499 → band 0 |
| `pickValueBand_value_at_threshold_goes_to_higher_band` | same | 500 → band 1 (strictly less than: `value < thresholds[i]`) |
| `pickValueBand_value_above_last_threshold_returns_4` | same | 12000 / 99999 → band 4 (gilt) |
| `pickValueBand_custom_thresholds` | same | xianxia-style `[1000, 5000, 15000, 50000]` produces different bands |
| `pickValueBand_defensive_nan_value` | same | `NaN` / `Infinity` / `-1` clamps to band 0 |
| `pickValueBand_defensive_nan_thresholds` | same | `[NaN, 100, 200, 300]` falls back to defaults |
| `pickValueBand_defensive_non_ascending_thresholds` | same | `[5000, 100, 9999, 1]` sorts locally + still returns deterministic band |
| `bandColor_clamps_at_bounds` | same | `bandColor(-1)` → BAND_COLORS[0]; `bandColor(99)` → BAND_COLORS[4] |
| `bandLabel_clamps_at_bounds` | same | same clamp |
| `viewer_store_inspector_carries_value_band_thresholds_when_registry_declares_them` | viewer-store.test.ts | `view.registry_ref.value_band_thresholds = [...] ` flows into `inspector.valueBandThresholds` |
| `viewer_store_inspector_value_band_thresholds_is_null_when_registry_omits` | same | `view.registry_ref.value_band_thresholds = undefined` → `inspector.valueBandThresholds = null` |

## Design review findings (self-review pass — pre-BUILD)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| **MED-1** | MED | Badge stamping on `MonsterLair` would render a misleading band (guard's strength, not pile's gold value) | Gate badge on `kind === 'treasure'`. Guards rely on inspector tier_index reading |
| **LOW-1** | LOW | TileInspector treasure section needs to distinguish piles vs guards in display | Pile gets value/tier/band rows; guard gets only `guard tier N (inherited)` row |
| **LOW-2** | LOW | "value" Row label was ambiguous for piles vs lairs | Rename to "treasure value" (with `gold` unit) for piles; existing generic `value` row remains for non-treasure placements |
| **LOW-3** | LOW | Badge depth `101 + anchor.y` could be obscured by adjacent-row sprites at depth `100 + anchor.y + 1` | `BADGE_DEPTH_BASE = 100_000` puts badges above all sprite depths unambiguously |
| **COSMETIC-1** | COSMETIC | Magic numbers (4 px radius, 0.95 alpha) scattered in the impl block | Top-of-file consts: `BADGE_RADIUS_PX`, `BADGE_DEPTH_BASE`, `BADGE_ALPHA`, `BADGE_BORDER_COLOR`, `BADGE_BORDER_ALPHA`, `BADGE_LOD_MIN_ZOOM` |

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Badges visually compete with foundation blend (chunk B/C of TMP-Q3) | Small (4 px radius) + bright color + 0.7-alpha slate-900 border. Tested in chunk-C visual regression goldens |
| Phaser circle render perf at Continent tier (~5k placements) | Badges live in the same chunked container as their sprites; LOD culls at zoom < 0.4. Cost ≈ 0 when culled |
| Inspector `Row` widening to ReactNode breaks existing string-typed callers | Search for `<Row k="..." v={...} />` — all current callers pass string. Widening v's type is backward-compatible |
| TS strict — pickValueBand receiving `readonly` tuple needs spread / mutable copy | Use `[...thresholds]` to create a mutable copy locally; never mutate the original |
| Color #-hex string conversion in JSX style | Use `.toString(16).padStart(6, '0')` to pad short hex codes |
| Per-book threshold override could shift band colors mid-game (registry change) | Defer to a future chunk if it becomes a concern; chunk B reads thresholds at inspector-open + at overlay-build, both one-shot |

## Ground-truth verification table

| Reference | File:line | Verified |
|---|---|---|
| `RegistryRef.value_band_thresholds` (TS) | `frontend-game/src/types/tilemap.ts:48-58` | YES (chunk A) |
| `TilemapObjectPlacement.value + tier_index` (TS) | `frontend-game/src/types/tilemap.ts:188-207` | YES (chunk A) |
| `useViewerStore.inspector` payload shape | `frontend-game/src/store/viewer-store.ts:33-43` | YES |
| `TileInspector` V2 placement detail loop | `frontend-game/src/components/viewer/TileInspector.tsx:67-95` | YES |
| `buildObjectOverlay` placement loop | `frontend-game/src/game/render/object-overlay.ts:143-175` | YES |
| `cam.zoom` for LOD | `frontend-game/src/game/render/object-overlay.ts:181` | YES |
| Phaser `Phaser.GameObjects.Arc` | Phaser docs (`scene.add.circle`) | YES (built-in) |

## Out of scope

- Zone-tier overlay (chunk C)
- MetadataPanel zone breakdown (chunk C)
- Visual regression goldens (chunk C)
- ZoneRole-driven badge variations (V3+)
- Badge animation on hover/click (V3+)
- Per-pile decomposition (showing pile constituents — V2 design)
