# Plan — GEO enhancement: orographic climate (rain shadow)

**Date:** 2026-05-17 · **Task size:** L (5 source files + tests; new public
`CreativeSeed` field) · **Branch:** geo-generator-amaw · **Mode:** default v2.2.

## Problem

`climate::classify` derives a cell's `dry` value from `ocean_distance` alone —
graph distance to the nearest water. It has **no concept of mountains**: a cell
behind a tall range still reads "wet", so forest grows where a rain shadow
should make desert. Path B made the ranges prominent — the inconsistency is now
visible.

## Design — a wind-driven moisture march

**Wind knob (PO decision):** a new `PrevailingWind` enum — 8 compass directions
(where the wind blows *from*) — and a `CreativeSeed.prevailing_wind` field. CLI
`--wind` + the LLM author both set it. `#[serde(default)]` = `West` so an old
config JSON without the field still loads.

**`climate.rs` — moisture march** (`wetness_field`):

1. Process cells in **downwind order** — sorted ascending by `center · wind`
   (`f32::total_cmp`, tie-break by cell index → deterministic).
2. **Water cell** → air moisture `1.0`, ground wetness `1.0` (the ocean
   replenishes the air).
3. **Land cell** — gather *upwind* neighbours (strictly smaller wind
   projection):
   - `incoming` = mean upwind air moisture (`1.0` at the windward edge);
   - `climb` = normalized rise above the mean upwind elevation;
   - `rained = min(incoming, OROGRAPHIC·climb + BASE_RAIN·incoming)` — orographic
     rain on the climb plus a humidity baseline;
   - ground `wetness = rained`; air carried downwind `= (incoming − rained) ·
     (1 − OVERLAND_LEAK)`.
4. `dry = 1 − wetness` replaces the ocean-distance input to `classify`.

The march subsumes continentality (deep inland = air spent) *and* adds the rain
shadow (lee of a range = air arrived dry). `ocean_distance` is removed.
`classify`'s third parameter is renamed `dist_norm → dryness` (its body already
treats it as dryness; positional callers/tests are unaffected).

Downstream — biomes and rivers — improve for free; they consume `ClimateZone`.

## Files

- `creative_seed.rs` — `PrevailingWind` enum (`vector()`, `tag()`, `Default =
  West`); `CreativeSeed.prevailing_wind` field (`#[serde(default)]`); update
  `Default for CreativeSeed`.
- `climate.rs` — `wetness_field` march; `build` gains the wind arg; remove
  `ocean_distance` + the `VecDeque` import; `classify` param rename.
- `lib.rs` — `pub use` `PrevailingWind`; `generate` passes `cs.prevailing_wind`.
- `main.rs` — `--wind` flag + `WindArg` mirror enum.
- `author.rs` — add `prevailing_wind` to the schema (`required` + 8-variant
  `enum`), the `SYSTEM_PROMPT` field list, and `schema_enums_match_rust_enums`.

## Determinism

`content_hash` changes (intentional — climate changes). The march is
deterministic (total-ordered sweep). `#[serde(default)]` keeps old `CreativeSeed`
JSON loadable.

## Verification

- `climate` unit tests incl. `all_eight_zones_are_reachable`; a new test that a
  lee cell behind a ridge is drier than a windward cell.
- `serde` round-trip with the new field; `schema_enums_match_rust_enums` extended.
- Full `structure.rs` suite stays green; `cargo clippy` clean.
- Regenerate PNGs — a desert/arid band should appear on the lee side of a range.

## Out of scope

Latitude-banded wind belts (trade winds vs westerlies) — single prevailing
direction per world for now. Humidity feedback on temperature.
