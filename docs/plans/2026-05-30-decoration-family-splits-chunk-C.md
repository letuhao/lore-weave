# Chunk C — Xianxia Demo + FE Breakdown + Visual Goldens (TMP-Q6)

**Spec:** [`docs/specs/2026-05-30-decoration-family-splits.md`](../specs/2026-05-30-decoration-family-splits.md) §4 chunk C
**Branch:** `mmo-rpg/decoration-family-splits` (stacks on chunk B `f17bf4db`)
**Size:** L (8 files / 5 logic / 1 side effect — xianxia per-book bias activates the resolution chain end-to-end)
**Goal:** Discharge chunk-A xianxia load-bearing tracker; demonstrate end-to-end family bias via xianxia per-book demo; surface family breakdown in FE viewer; bake visual goldens.

## Discharges from prior chunks

- **Chunk A LOW-2 tracker**: `xianxia_sample_per_book_completeness_tracked_for_chunk_b_c` MUST flip from "tracker" to "permanent pin" or be removed once xianxia annotates its 29 entries. Chunk C annotates → tracker becomes a permanent pin (xianxia decorations all have family).
- **Chunk B DEFERRED #045**: end-to-end registry-TOML invalid-bias rejection test. Bundle here.

## Architecture

### Xianxia per-book bias choice

Per spec §1 "PO directive: 'lots of bushes but rare crystal shards' or 'no bones in this book at all'". Xianxia aesthetic: cultivators harvest crystals/spirit-stones, ancient cultivation ruins are common, but skeletons are NOT a xianxia genre staple (compared to European fantasy).

```toml
[registry.decoration_family_density]
rock = 1.8         # cultivators harvest spirit-stones / dao crystals
vegetation = 1.2   # spirit-herbs + cultivation forests slightly elevated
bone = 0.3         # xianxia rarely shows skeletons (genre fit)
structure = 1.0    # baseline
water = 1.0        # baseline
snow = 1.0         # baseline
```

### Frontend breakdown helper

```ts
// frontend-game/src/components/viewer/decoration-family-breakdown.ts
export interface DecorationFamilyRow {
  family: string;        // 'rock' | 'vegetation' | ... | 'none' for unfamilied
  count: number;
  percent: number;       // 0..100, rounded to 1 decimal
}

export function computeDecorationFamilyBreakdown(
  view: TilemapView,
  registry: { object_kinds?: ObjectKindDef[] } | null,
): DecorationFamilyRow[] {
  // 1. Build kind_id → family lookup from registry (Map)
  // 2. Walk view.object_placements, filter primitive==Decoration, group by family
  // 3. Sort desc by count, ties broken alphabetically asc
  // 4. Compute percent against total decoration count
}
```

**Single source of truth** per [[extract-cross-surface-predicate]]. The kind_id→family lookup is reused by future drill-down work (chunk D / future polish).

### Frontend MetadataPanel collapsible

Add `<DecorationFamilyBreakdown>` collapsible BELOW the existing `<RoleBreakdown>` (TMP-Q5 chunk B). Same pattern: `useMemo(() => computeDecorationFamilyBreakdown(view, registry), [view])`, render rows with optional color-swatch (chunk D polish if any), display `family · count (pct%)`.

Section copy:
- Collapsed header: `decoration families (N families · M decorations)`
- Empty state: `no decorations placed yet`

### Visual goldens

Per [[visual-goldens-must-gate-on-content]]: content-gate the screenshot on a unique text assertion BEFORE `toHaveScreenshot`. Use the breakdown's text content (e.g. `"decoration families (6 families · 18 decorations)"` — the exact count depends on the test fixture; use a substring match).

2 goldens:
- `decoration-family-breakdown-collapsed.png` — sidebar with section collapsed
- `decoration-family-breakdown-expanded.png` — sidebar with section expanded showing rows

Per-platform PNG pinned (Windows-x86_64 on dev); cross-platform regen doc mirrors chunk-Q5 chunk C precedent.

## File list (8 files + Playwright artifacts)

| # | File | Action |
|---|---|---|
| 1 | `services/tilemap-service/registry/xianxia_sample.toml` | MOD — 29 family annotations (matching default.toml's order 1:1) + `decoration_family_density` block |
| 2 | `services/tilemap-service/src/registry.rs` | MOD — discharge chunk-A `xianxia_sample_per_book_completeness_tracked_for_chunk_b_c` tracker → flip to permanent pin that xianxia decorations all have family AND xianxia's decoration_family_density block is well-formed; add a positive load-test for the bias block |
| 3 | `services/tilemap-service/tests/http_integration.rs` | MOD — HTTP wire test (AC-DFS-11): POST to /v1/place_tilemap with xianxia registry + bias declared, assert response wire shape carries `decoration_family_density` block on the embedded `registry_ref` |
| 4 | `services/tilemap-service/tests/decoration_placer.rs` | MOD — DEFERRED #045 discharge: registry-TOML with invalid bias (negative multiplier in registry, malformed family-name key) rejects at `Registry::from_file` |
| 5 | `frontend-game/src/types/tilemap.ts` | MOD — `ObjectKindDef.family?`, `TilemapTemplate.decoration_family_density?`, `RegistryRef.decoration_family_density?` |
| 6 | `frontend-game/src/components/viewer/decoration-family-breakdown.ts` | NEW — `computeDecorationFamilyBreakdown(view, registry): DecorationFamilyRow[]` pure helper + 6 vitest cases (empty, single-family, multi-family sort, percent rounding, unfamilied-as-`none`, registry-null) |
| 7 | `frontend-game/src/components/viewer/MetadataPanel.tsx` | MOD — `<DecorationFamilyBreakdown>` collapsible section + `data-testid` for goldens |
| 8 | `frontend-game/e2e/decoration-family-visual-regression.spec.ts` | NEW — 2 Playwright goldens (collapsed + expanded), content-gated per [[visual-goldens-must-gate-on-content]] |
| 9 | `docs/plans/2026-05-30-decoration-family-splits-chunk-C.md` | NEW — this plan |

## Invariants

1. **Xianxia 29 decorations all carry `family`** — discharges chunk-A tracker (`xianxia_sample_per_book_completeness_tracked_for_chunk_b_c` becomes a permanent invariant pin)
2. **Xianxia bias block validates at registry load** — uses shared `validate_decoration_family_density` from chunk B
3. **HTTP wire shape transports `decoration_family_density` on `registry_ref`** — AC-DFS-11
4. **Registry-TOML with malformed bias rejects at `Registry::from_file`** — DEFERRED #045 discharge
5. **FE `computeDecorationFamilyBreakdown` is a pure function** — no API calls, no side effects, deterministic given (view, registry)
6. **Unfamilied placements bucket as `"none"`** — visible in the breakdown for legacy / TYPE-marker entries; spec §4 chunk-A precedent
7. **Visual goldens are content-gated** — text-content assertion BEFORE `toHaveScreenshot` per [[visual-goldens-must-gate-on-content]]
8. **MetadataPanel `<DecorationFamilyBreakdown>` mirrors `<RoleBreakdown>` interaction shape** — collapsible default-collapsed, useMemo on view+registry, no API calls

## Test plan

| Test | Verifies |
|---|---|
| **Backend** | |
| `xianxia_sample_decorations_all_have_family` (renamed from tracker) | All 29 xianxia decoration entries declare `family` |
| `xianxia_decoration_family_density_loads_and_round_trips` | Xianxia bias block loads + serializes back |
| `xianxia_decoration_family_density_uses_documented_v1_families` | Bias keys all in V1 family set {rock,vegetation,structure,bone,water,snow} — prevents typo at author time |
| `xianxia_high_rock_low_bone_bias_observable_in_placement` | Run xianxia template through placer, assert rock proportion > baseline, bone proportion < baseline |
| `registry_toml_with_negative_multiplier_rejects_at_load` (DEFERRED #045) | Inline TOML with `rock = -1.0` rejects |
| `registry_toml_with_malformed_family_key_rejects_at_load` (DEFERRED #045) | Inline TOML with `Rock = 1.0` (uppercase) rejects |
| `http_place_tilemap_with_xianxia_emits_decoration_family_density_on_wire` (AC-DFS-11) | POST + 200 + body contains the bias block on registry_ref |
| **Frontend** | |
| `decoration_family_breakdown_empty_view_yields_empty_array` | Sanity boundary |
| `decoration_family_breakdown_single_family` | Single bucket |
| `decoration_family_breakdown_multi_family_sorted_by_count_desc` | Ordering invariant |
| `decoration_family_breakdown_ties_broken_alphabetically_asc` | Determinism in display |
| `decoration_family_breakdown_percent_rounds_to_1_decimal` | Display invariant |
| `decoration_family_breakdown_buckets_unfamilied_as_none` | Legacy / TYPE-marker handling |
| `decoration_family_breakdown_renders_collapsible_in_metadata_panel` | DOM + interaction |
| **E2E** | |
| `decoration_family_breakdown_visual_regression_collapsed` | Golden + content gate |
| `decoration_family_breakdown_visual_regression_expanded` | Golden + content gate |

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Xianxia bias shifts visual goldens for unrelated tests | Goldens are NEW for chunk C; existing zone-role goldens use default registry (no xianxia). Chunk-Q5 chunk C goldens stay unchanged. |
| TS-Rust type drift for `decoration_family_density` | TS shape `Partial<Record<string, number>>` matches Rust `HashMap<String, f32>` for JSON wire purposes; existing precedent in `ZoneRoleColors` shape |
| Playwright cross-platform PNG drift | Per-platform commit (Windows-x86_64 on dev); regen-on-mac doc same as chunk-Q5 chunk C |
| `count_decorations_by_family` helper duplicated between FE + BE integration tests | FE helper (`computeDecorationFamilyBreakdown`) is the canonical FE-side; backend integ test has its own `count_decorations_by_family` (chunk B introduced). These are two different APIs serving different surfaces — no extraction needed. Document precedence in helper doc-comments. |
| Tracker test rename could confuse git blame | Use git-aware rename in the same commit; comment in test docs explains the chunk-A → chunk-C transition |

## Out of scope (chunk D / future polish)

- Color-swatch per family in MetadataPanel (chunk D polish)
- Drill-down from family row to highlight matching decorations on canvas (V3 polish per spec §5)
- Per-family icon symbology (V3 polish)
- Localization / pretty-printing of family names (spec §5)
