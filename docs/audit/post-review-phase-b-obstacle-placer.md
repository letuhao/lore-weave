# Scope Guard Post-Review — tilemap-service Phase B: ObstaclePlacer + Biomes

**Verdict: CLEAR**

AMAW Phase 8 (QC) + Phase 9 (POST-REVIEW) conservative final gate. No prior context;
not a line-by-line review (four cold-start Adversary code-review rounds already did
that). Question answered: is this work complete, in-scope, and safe to commit? Yes.

## Live guardrail check

```
python scripts/mcp-query.py check_guardrails \
  "git commit the Phase B ObstaclePlacer + biome system on the mmo-rpg/zone-map-amaw branch"
→ { "pass": true, "rules_checked": 6 }
```

`pass: true`, empty `matched_rules` — no guardrail blocks the commit. (The orchestrator's
pre-load `check_guardrails` also returned `pass: true`.)

## Gate check 1 — Guardrails

PASS. The live check above returned `pass: true` over 6 rules. Not a blocker.

## Gate check 2 — Acceptance criteria (AC-1..AC-11)

Every AC has a real, passing test. No placeholder, no false-green, no `#[ignore]` except
the documented golden regenerator. Test-name → AC spot-check:

| AC | Test(s) | Where |
|----|---------|-------|
| AC-1 | `library_covers_every_land_terrain_with_the_required_object_types`, `water_has_mountain_rock_plant_but_no_tree_or_crater`, `every_biome_set_has_4_to_10_templates`, `library_is_deterministic` | `biome_library.rs` |
| AC-2 | `default_rules_match_tmp005_section_2_3` (asserts 9 rules, counts, priorities, xor) | `biome_library.rs` |
| AC-3 | `selects_only_terrain_matching_biomes_within_count_bounds`, `selection_is_deterministic_for_a_fixed_zone_and_seed`, `xor_pair_yields_all_three_outcomes_never_both`, `xor_realized_water_feature_rate_on_engine_defaults`, `priority_order_is_first_normal_last` | `biome_select.rs` |
| AC-4 | `q3_fallback_fills_a_terrain_with_no_native_biomes`, `sea_zone_gets_trees_via_the_q3_fallback` | `biome_select.rs` |
| AC-5 | `erosion_only_blocks_open_tiles_and_terminates`, `erosion_never_seals_a_gap` (200 random zones, independent `reachable_from` flood-fill), `erosion_keeps_a_two_wide_sole_corridor_passable` (a), `erosion_fully_consumes_a_two_wide_dead_end_appendage` (b), `erosion_preserves_a_multi_component_passable_region` (c) | `obstacle_placer.rs` |
| AC-6 | `fill_places_obstacles_only_in_the_obstacle_region` (full-footprint containment), `fill_is_largest_first` (independent `max_area` anchor + `object_placements.len()` tie) | `obstacle_placer.rs` |
| AC-7 | `mountain_and_lake_biomes_tag_their_object_type` (deterministic Mountain + deterministic hand-built Lake half) | `obstacle_placer.rs` |
| AC-8 | `placement_deserializes_without_biome_object_type`, `obstacle_placement_round_trips_with_biome_object_type`, `zone_spec_deserializes_without_biome_selection_rules`, `zone_spec_round_trips_with_biome_selection_rules`, `biome_selection_rules_serde_round_trip` | `object.rs`, `template.rs`, `biome.rs` |
| AC-9 | `ac4_same_seed_yields_byte_identical_tilemap` (struct + serialize equality, non-empty `object_placements`), `golden_baseline_byte_identical` | `determinism.rs` |
| AC-10 | `ac10_place_tilemap_pipeline_never_splits_a_zone_passable_region` (real `place_tilemap` modificator set, `Walkable ∪ Open`, independent flood-fill, 5 seeds) | `engine/mod.rs` |
| AC-11 | `cargo test --workspace` + `cargo clippy --workspace` — see gate 5 | — |

The lesson-1e524dee / d29dbaba / 9ba274f5 traps are specifically guarded: AC-5/AC-10 use
an independent flood-fill (not the erosion gate's own `would_seal_a_gap`, not a count
delta) on `Walkable ∪ Open`; AC-5 includes the multi-component fixture (c); AC-3's xor
test runs against the production `engine_biome_library()`, not a synthetic one. No AC is
uncovered or false-green.

## Gate check 3 — Scope

PASS. Phase B built exactly §2 "In scope": the TMP_005 §2 biome type family
(`types/biome.rs` — `BiomeSet`, `BiomeObjectType` 9-variant, `BiomeLevel`, `Alignment`,
`BiomeSelectionRules`, `BiomeSelection`); the V1+30d engine library + §2.3 rules
(`biome_library.rs`); the §4.1 selection algorithm (`biome_select.rs`); the
`ObstaclePlacer` modificator with §4.3 erosion + §4.4 largest-first fill
(`obstacle_placer.rs`); §4.5 river-source/sink discoverability via `biome_object_type`;
and the additive schema (`TilemapObjectKind::Obstacle`,
`TilemapObjectPlacement.biome_object_type`, `ZoneSpec.biome_selection_rules`).

No "Out of scope" item leaked in: no TreasurePlacer / ConnectionsPlacer / Road / River
(grep confirms ObstaclePlacer + TerrainPainter are the only registered modificators); no
15% decoration variant; no faction/alignment filtering (the schema fields exist but the
library leaves `factions`/`alignments` empty — exactly as §2/D3 specify); no
`BiomeLevel::Underground` biomes. No scope creep, no missing in-scope item.

## Gate check 4 — Review findings resolved

PASS. Four code-review rounds, every finding resolved:

- **r1** — REJECTED, 2 BLOCK + 1 WARN. Resolution: all 3 fixed. F1 (BLOCK — §9 Q3
  fallback unimplemented) fixed in `biome_select.rs`; F2/F3 (BLOCK/WARN — false-green
  tests) fixed.
- **r2** — REJECTED, 1 BLOCK + 2 WARN. Resolution: all 3 fixed. F1 (BLOCK — AC-10 tested
  the inert `Walkable` skeleton with the wrong oracle) — inert test removed, real AC-10
  test relocated to `engine/mod.rs`.
- **r3** — REJECTED, 1 BLOCK + 2 WARN. Resolution: all 3 fixed. F1 (BLOCK — `Crater`
  never stocked, water features under-deliver) fixed by stocking `Crater` for all 7 land
  terrains; golden rebaselined.
- **r4** — APPROVED_WITH_WARNINGS, 0 BLOCK + 3 WARN. The 3 WARNs closed with test +
  doc-only edits (xor realized-rate test, `BiomeSelectionRules` serde round-trip,
  multi-component erosion fixture). Ends the adversarial loop — APPROVED_WITH_WARNINGS is
  the AMAW stop condition.

No unresolved BLOCK. r1/r2/r3 BLOCKs verified resolved by the next round in turn; r4 is
APPROVED_WITH_WARNINGS with all 3 WARNs addressed. I spot-confirmed the fixes are live in
the source: the §9 Q3 fallback is in `select_biomes` (`by_type.get` → `None` branch
drops the terrain filter); `engine_biome_library()` stocks `Crater` for the 7 land
terrains and the golden carries 8 `crater` obstacle placements; AC-10 lives in
`engine/mod.rs` and loops 5 seeds.

## Gate check 5 — Evidence (test + clippy)

PASS. Run fresh, output read:

- `cargo test --workspace` — green. `tilemap_service` lib **178 passed, 0 failed**;
  `determinism` integration **6 passed, 0 failed, 1 ignored**. The 1 ignored is
  `regenerate_golden_baseline` — the documented deliberate-rebaseline tool, the only
  permitted `#[ignore]`. All other suites (loreweave_llm 22, wire_format 22, l4_mock 8,
  retry_mock 9, smoke 5, gateway/harness mocks) also green.
- `cargo clippy --workspace --all-targets` — clean, `Finished` with zero warnings and
  zero errors.
- Golden: `tests/golden/tilemap_baseline.json` is the rebaselined Phase-B artifact
  (5757 lines, 112 obstacle placements, `biome_object_type` tags spanning
  crater/mountain/tree/rock/plant); `golden_baseline_byte_identical` reproduces it.

No red test, no clippy warning.

## Residual risk

Carried forward — none of this blocks the commit; all is documented:

- **Out-of-scope deferrals (§2):** 15% decoration variant, faction/alignment biome
  filtering, `BiomeLevel::Underground` biomes, seasonal/LLM biomes, `Forge:EditBiome`
  overrides — all consciously deferred to V2+/V3 or later phases.
- **D7 river-footprint reference:** `TilemapObjectPlacement` carries the obstacle's
  `anchor`, not its footprint extent. Whether Phase-E RiverPlacer needs the full extent
  is a Phase-E decision; adding a footprint/template reference would be an additive
  Phase-E change. Logged as a Deferred item per the spec D7 scope note and the plan's
  SESSION-deferred note.
- **r4 WARN residuals:** the three r4 WARNs were closed by test + doc edits (production
  code unchanged that round). No residual code risk — the WARNs were coverage/clarity
  gaps, now covered. APPROVED_WITH_WARNINGS-grade, not a blocker.
- **AC-10 seed corpus:** the integrated-pipeline connectivity test loops 5 fixed seeds
  rather than exhaustively — a reproducible, multi-geometry corpus (the r3 WARN-2 fix).
  Erosion itself is separately covered by 200 random zones + 3 topology fixtures. Normal
  APPROVED_WITH_WARNINGS residual, not a blocker.
- Line-ending note: `git` reports LF→CRLF normalization for the touched files on a
  Windows checkout. The `golden_baseline_byte_identical` test passes, so the committed
  golden and the freshly-serialized engine output match — the normalization is cosmetic
  and does not affect the byte-identity gate.

## Conclusion

Phase B is complete, strictly in-scope, every AC has a real passing test, all four
code-review rounds are resolved (r4 APPROVED_WITH_WARNINGS), `cargo test`/`cargo clippy`
are green, and the live guardrail check passes — **CLEAR to proceed to SESSION + COMMIT**.
