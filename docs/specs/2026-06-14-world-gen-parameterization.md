# Spec — world-gen parameterization (expose hardcoded tuning → `CreativeSeed`)

> **Task: XL arc (staged P1–P4).** Turn the ~55 hardcoded generation-tuning
> `const`s of the sphere pipeline into **runtime parameters** on `CreativeSeed`
> — granular control + macro "intensity" knobs — plus a render-theme config.
> Goal: a creator can dial any world property per-world (the "omnipotent creator"
> direction) without recompiling. Session 100 cont.
>
> **Inviolable invariant (every stage): byte-identical default baseline.** Every
> new parameter defaults to its *current const value*, so `generate(seed,
> default-CreativeSeed)` produces a **byte-identical `content_hash`** to before
> the refactor, for every seed/scale. Parameterization changes the *surface*, not
> the *output*. (Mirrors the dispatcher-refactor pattern: architecture change,
> zero baseline drift.)

## 0 — Audit (this session — `const` sweep **+ deep inline/enum/table sweep**)

> **Completeness note (spec review):** the first pass swept only `const`
> declarations (~55). A second deep sweep (function bodies, `impl` enum→number
> maps, clamp ranges) found the real tunable surface is **~120–150 values** —
> roughly **2×** — spanning more subsystems (erosion, settlement, hydrology,
> political, culture, routes, hierarchy, and the biome *derivation tables*). Full
> catalog below.

| Group | Examples | Disposition |
|---|---|---|
| **A. Macro/terrain tuning** ~55 const | `plates.rs` (16): orogeny peaks, crust/isostasy, `FAULT_SHEAR_RATIO`, plate-warp · `terrain.rs` const (~27): `TECT_*`, `OCEAN_*`, `SEA_FRAC`/`LAND_FULL`/`OCEAN_FULL`, noise freq/weight, `ARCH_RADIUS` · `climate.rs` const (12): `T_EQ/T_POLE`, `LAPSE_C`, `PRECIP_*`, `AMP_*`, `HIGHLAND_ELEV`, `OROGRAPHIC`, `LAND_LEAK_BASE` | **EXPOSE** (granular + macro) |
| **A2. Inline tuning literals (NOT const)** ~25 | `terrain.rs` smoothstep gates (belt `0.46/0.72`, landness `0.32/0.52`, coastline-profile params), sea-level band `8192/57344` · `climate.rs` **Köppen cutoffs** (`10/18/−3/22 °C`, Med `0.65`, aridity slope `20.0` + offsets) · `hydrology.rs` (river pct `0.96`, lake `150/24`) | **EXPOSE** (these *are* world-shaping knobs) |
| **A3. Enum→number maps + derivation tables** ~60 | `creative_seed.rs`: `SettlementDensity` (cells `800/400/200`, sep `0.08/0.05/0.03`), `CoastlineProfile` (`land_fraction`, dome `0.75`) · `erosion.rs` `ErosionStrength`→{carve/settle iters, erodibility, transport, settle_rate, diffusion} · `biome.rs` elevation tiers (`0.06/0.22/0.55`) + **`terrain_cost`/`culture_barrier`/`population_potential`** tables · `climate.rs` wetness-per-zone + climate-bias deltas · `settlement.rs` burg scoring + role pct + climate-habitability · `political.rs`/`culture.rs` count divisors + spacing · `routes.rs` pass count + tier gates · `hierarchy.rs` subdivision | **EXPOSE as override tables** (see §1f) — incl. the **gameplay/derivation** weights |
| **B. Internal / determinism** ~20 | `SALT_*` (×13), `GOLDEN_ANGLE`, fBm `OFFSET`/`GAIN`, `FRAC_1_SQRT_2`, `CLIPPER_SCALE`, `ARCH_ISLANDS`, array sizes, `NONE` | **KEEP internal** |
| **B2. Clamp ranges / safety rails** | `.clamp(3,24)`, `.clamp(0.1,0.9)`, `.clamp(4,80)`, `8192..=57344` | **KEEP internal** — these are the *guards* on the new params, not params themselves (widened only if a param's exposed range needs it) |
| **C. Render-only** ~25 | `render.rs` colors/palettes, `BACKGROUND`, `SS`, `relief.rs` render | **EXPOSE as `RenderTheme`** (not in `content_hash`) |
| **D. Frozen flat track** | `flatworld.rs`, `flat_climate.rs`, `zonegen.rs` | **DO NOT TOUCH** (CLAUDE.md) |
| **E. Authoring (LLM)** | `author.rs`/`naming.rs` prompts, `civ_adapter.rs` name lists | **Out of scope** |

## 1 — Architecture

### 1a — Granular params (nested, serde-default)

New nested structs on `CreativeSeed`, **every field `#[serde(default)]`**, with a
`Default` impl whose values are **exactly today's consts** (the single source of
truth — the consts are deleted/moved into `Default`):

```rust
pub struct CreativeSeed {
    // …existing fields…
    #[serde(default)] pub tectonics: TectonicsParams,  // P1
    #[serde(default)] pub relief: ReliefParams,        // P2
    #[serde(default)] pub climate_params: ClimateParams,// P3
    #[serde(default)] pub render_theme: RenderTheme,    // P4
    #[serde(default)] pub intensity: IntensityKnobs,    // macro, P1+
}
```

Old config JSON (no new fields) → serde fills defaults → **byte-identical** world.

### 1b — Macro intensity knobs (`IntensityKnobs`, all default `1.0` = no-op)

Convenience scalers that multiply *groups* of granular params, so a creator can
swing "vừa ↔ kịch tính" with one number while granular still overrides precisely.
`effective = granular · macro_scale` (default 1·1 = unchanged). Proposed set:

- `orogeny` → scales `fold_peak`, `arc_peak`, `collision_thicken_km`, `cont_iso_slope`, `tect_range_weight` (mountain-building).
- `relief` → scales `tect_belt_lift`, `tec_hill_weight`, `interior_rugged_cap` (detail).
- `ocean_depth` → scales `ocean_abyss`, `ocean_full` (bathymetry).
- `collision_frequency` → inversely scales `fault_shear_ratio` (more/less collision).
- `warmth` → shifts `t_eq`/`t_pole`; `rainfall` → scales `precip_*`; `seasonality` → scales `amp_*`.

### 1c — Validation / clamping

Each param clamps to a documented sane range *on use* (a `TectonicsParams::clamped()`
etc., or per-field clamps), mirroring the existing `continental_fraction.clamp(0.1,0.9)`.
Macro knobs clamp to e.g. `0.0..=3.0`. Out-of-range config never panics — it clamps.

### 1d — Threading

`plates::build` / `terrain::build` / `climate::build` take the relevant params
struct (with macro knobs pre-applied into an `effective`/resolved struct). Render
functions take `&RenderTheme`. The `const`s become the `Default` impls.

### 1e — CLI

`--config <json>` (a full `CreativeSeed`) is the primary path for granular control.
Keep the existing high-level flags. Add a small set of macro-knob flags
(`--orogeny`, `--relief`, `--ocean-depth`, …) for quick CLI dialing. Do **not**
add ~120 granular flags (config-file territory).

### 1f — Enum→number maps, derivation tables, clamp rails (the A3 group)

- **Enum→number maps** (`SettlementDensity`, `CoastlineProfile`, `ErosionStrength`,
  `WorldScale`): keep the enum as the high-level pick; the params struct holds the
  underlying **table** (e.g. `SettlementParams { cells_per_settlement: { sparse,
  medium, dense }, min_separation: {…} }`) defaulting to today's values. The enum
  selects a row; the table is overridable. (Lets a creator keep "Dense" but
  redefine what dense means, or set a fully custom number.)
- **Derivation / gameplay tables** (`biome.rs` `terrain_cost` / `culture_barrier`
  / `population_potential`, `settlement` climate-habitability, `climate` wetness-
  per-zone + bias deltas): exposed as **fixed-size per-enum arrays** (e.g.
  `[u32; 14]` over `BiomeKind`, `[f32; 8]` over `ClimateZone`) — **NOT `Vec`**.
  This is load-bearing: a `Vec` field would strip `CreativeSeed`'s `Copy` derive
  and ripple through every by-value use; fixed arrays keep `CreativeSeed: Copy`
  (review-impl P1, finding 1). These are *gameplay weights* (movement cost,
  habitability, culture spread) — distinct from geometry, but the PO chose
  "expose everything", so they are in scope.
- **Köppen classifier cutoffs** (`climate.rs` `10/18/−3/22 °C`, Med `0.65`, aridity
  slope): exposed in `ClimateParams` — a creator can redefine the climate-zone
  boundaries themselves.
- **Clamp rails** (B2): stay internal — they *guard* the new params (an
  out-of-range config clamps, never panics). Widen a rail only if a param's
  intended exposed range exceeds it.

### 1g — One centralized profile (human **and** LLM authorable) — the end-state

**Yes: `CreativeSeed` *is* the single centralized profile.** It is the one input
to `generate(seed, &cs)` (the `u64` seed is just the dice; the profile is the
creative direction). After the arc it carries **every** tunable, in three tiers —
all `#[serde(default)]`, so any author sets only what they care about and defaults
fill the rest:

- **Tier 1 — high-level enums** (`world_scale`, `coastline_profile`,
  `settlement_density`, …) — already present; the quick "what kind of world".
- **Tier 2 — macro intensity knobs** (`orogeny`, `relief`, `warmth`, `rainfall`,
  `collision_frequency`, …, default `1.0`) — the **LLM-friendly dials**: a few
  numbers that swing whole behaviours.
- **Tier 3 — granular params + override tables** (the ~120 values) — precise
  human/advanced control.

**Two authoring paths, one profile:**
- **Human** → hand-edit the profile JSON, run `--config profile.json`. To make
  this ergonomic, add a CLI **`dump-config`** that emits the *full default*
  profile as annotated JSON — a ready template showing every knob.
- **LLM** → `author --brief "…"` returns the profile JSON, constrained by
  `creative_seed_schema()` and validated/clamped by `parse_creative_seed`. The LLM
  mostly sets Tier 1 + Tier 2 (the macro knobs are exactly what a prose brief maps
  to); Tier 3 stays available but rarely needed.

**Safety for both:** clamp-on-parse **and** clamp-on-use — a human typo or an LLM
hallucination is clamped to the valid band, never panics.

**Cross-cutting requirement (every stage):** when a stage adds params it MUST also
extend (a) `creative_seed_schema()` (the LLM JSON Schema — guarded by the
`schema_enums_match_rust_enums`-style test), (b) the `author` `SYSTEM_PROMPT`
field descriptions, and (c) `parse_creative_seed` clamps — otherwise the LLM
can't author the new knob. The macro knobs are the priority surface for the LLM;
granular tables can be schema-optional.

## 2 — Staged plan (each stage byte-identical-baseline + tests + commit)

The deep audit ~2×'d the surface, so the arc grows to **8 stages** (grouped by
subsystem; each independently shippable):

| Stage | Builds | Size |
|---|---|---|
| **P1 ✅** | `TectonicsParams` (19 `plates.rs` consts) + `IntensityKnobs` (`orogeny`, `collision_frequency`) in new `params.rs`; threaded into `plates::build`; LLM `author` schema/prompt/clamp wired. **Byte-identical baseline verified** (3 pinned hashes match pre-refactor). | L |
| **P2 ✅** | `ReliefParams` (34 `terrain.rs` consts: noise freq/octaves/weights, tectonic relief, bathymetry, quantize, archipelago radius) + `relief`/`ocean_depth` knobs → `terrain::build` + helpers; LLM author wired. Byte-identical baseline holds. *(Deferred: the Profile-mode-only inline `height_at` smoothstep gates + `apply_falloff` coastline literals — legacy single-continent path — tracked as a small P2 follow-up.)* | L |
| **P3 ✅** | `ClimateParams` (23 `climate.rs` knobs: temps, precip bands, seasonality, Köppen classifier cutoffs, Highland gate) + `warmth`/`rainfall`/`seasonality` knobs → `climate::build` + classifier helpers; LLM author wired. Byte-identical baseline holds. `/review-impl` follow-ups folded in: documented the seasonality `amp_eq` floor, the clamp-not-validate / dormant-at-default-`winter_frac` cutoff semantics; added an end-to-end histogram-direction test (warmth→more Tropical/fewer Polar, rainfall→more Arid) + climate-params serde/explicit-default parity. *(Deferred P3 follow-up: the moisture-transport consts + the cross-module `ClimateZone::wetness()` / `bias_delta` tables.)* | L |
| **P4 ✅** | `ErosionParams` (the `ErosionStrength` Light/Moderate/Heavy table — 18 fields × 6 per row; `None` stays a hardcoded no-op) + `HydrologyParams` (`river_percentile`, `lake_max_divisor`, `lake_max_floor`) → `erosion::apply_with` + `hydrology::build_with` (config-aware wrappers; the old `apply`/`apply_scaled`/`build` keep their signatures using the default table, so the **frozen** `zonegen.rs` + `civ_adapter` are untouched). Byte-identical baseline holds. The stream-power exponents `m`/`n` stay fixed math (`area.sqrt()`) — not parameterized, per the salts/math-fixed rule. No author/LLM change (the `ErosionStrength` enum is erosion's tier-1 knob). `/review-impl` clean — fixes folded in: `lake_max_floor` wiring test, `river_percentile` direction test (lower ⇒ more River cells), Light/Heavy `row()` wiring test. | M |
| **P5 ✅** | `SettlementParams` (burg water bonuses + threshold, target floor, role-rank percentiles, per-climate habitability — 8 zones) + `RouteParams` (MountainPass count, road/trail population-tier gates, navigable-river min run) → `settlement::build_with` + `routes::build_with` (config-aware wrappers; old `build` keeps its signature using defaults so `civ_adapter` is untouched). The `SettlementDensity` enum stays tier-1. Byte-identical baseline holds. No author/LLM change (density enum is the tier-1 knob). `/review-impl` clean — fixes folded in: `each_route_param_gate_is_wired` test (trail/mountain-pass/river-nav gates each zero out their route kind), plus clamp-not-validate docs (settlement role-percentile ordering; route tier-gate overlap is filter-only/GIGO). | M |
| **P6 ✅** | `PoliticalParams` (the live `build_nested` quota divisors + maxes for province/state/realm + county clamp) + `CultureParams` (hearth spacing coeff + count clamp) + `HierarchyParams` (region-subdivision clamp) → threaded into `political::build_nested` + `hierarchy::build` directly (lib-only) and `culture::build_with` (wrapper keeps `civ_adapter` + the legacy `political::build` on defaults). The region/county/culture *counts* stay `CreativeSeed` tier-1 inputs; only their clamp ceilings + divisors are params. Byte-identical baseline holds. `/review-impl` clean — proactive per-field wiring tests (divisor count-direction + max binding-constraint); fix folded in: updated the now-stale `region_subdivision`/`county_subdivision` field docs (clamp ceiling is now a param). | M |
| **P7 ✅** | `BiomeParams` — elevation tiers (beach/mid/high + wet-low flux frac) + the `terrain_cost`/`culture_barrier`/`population_potential` tables as **fixed `[_;14]` arrays** (Copy preserved, per the P1 finding) indexed by `BiomeKind::tag`. Threaded into `biome::build_with`/`derive_biome` + the live `build_nested` (terrain_cost), `settlement::build_with` (population_potential), `routes::build_with` (terrain_cost), `culture::build_with` (culture_barrier). The `BiomeKind` methods stay as the canonical default (legacy `political::build` + civ_adapter + tests), drift-guarded by a unit test (default table == method ∀ variant). Byte-identical baseline holds. `/review-impl` clean — fixes folded in: `resolved()` now clamps each cost-table entry to a 10 000 ceiling (a `u32::MAX` cost would overflow the Dijkstra accumulator `c + step` → panic; now bounded, with a no-panic test), plus `beach_t`/`mid_t`/`wet_low_flux_frac` tier wiring tests (count-direction). | M |
| **P8a ✅** | The editability capstone: CLI macro-knob flags (`--orogeny`/`--collision-frequency`/`--relief`/`--ocean-depth`/`--warmth`/`--rainfall`/`--seasonality` → `intensity`) + **`dump-config`** subcommand (emits the full default `CreativeSeed` as a JSON template) + made the 7 core identity fields `#[serde(default)]` so a config is fully partial/trim-friendly + a worked example (`examples/cold-rugged-archipelago.json` + README). Round-trip verified: `dump-config` → `--config` reproduces the exact default `content_hash`. Byte-identical baseline holds. | M |
| **P8b** | `RenderTheme` — render/relief colours, palettes, supersample. Larger than first scoped: the per-style hypsometric gradient ramps (`render::water_color`/`land_color`) + biome(14)/culture(16)/boundary(7)/plate/region-realm-border palettes + `SS`/`BACKGROUND`, threaded through ~8 render fns. **Sphere render is NOT `content_hash`ed and has no pins** → add render-hash pins (hash the seed-7 relief/biome/political PNGs) as the byte-identical safety net *before* refactoring. Render math (hillshade/warp/detail in `relief.rs`, the per-style `StyleParams`) stays fixed (the salts/math rule). | L |

**Order:** P1 → … → P8 (independent; can reorder if a subsystem is urgent). Each
stage: move its consts/inline-literals/tables into a `Default`, thread params, add
(a) a **byte-identical-baseline test** (default config → same `content_hash` as a
pinned pre-refactor digest / determinism cross-check), (b) a **knob-does-something
test** (a non-default value changes the output), (c) a **clamp test** (out-of-range
clamps, no panic). Full 12-phase + `/review-impl` + PO POST-REVIEW per stage.

## 3 — Cross-cutting rules

- **Byte-identical defaults** is the load-bearing invariant — verified per stage.
- **Determinism preserved** — params feed output values only; salts/math stay
  fixed internal. `content_hash` re-bases only when a param value actually differs.
- **Frozen flat track untouched**; **authoring layer untouched**.
- **No new provider/SDK/secret surface** — pure local compute.
- Backward-compat: every existing `CreativeSeed` JSON + every `author` LLM output
  keeps working (serde default).
- **One profile, dual authoring (§1g)**: every stage keeps the LLM `author`
  schema/prompt/clamps in sync with its new params, so the single `CreativeSeed`
  profile stays both human- and LLM-authorable end-to-end.

## 4 — Out of scope (this arc)

Per-biome/per-feature parameter overrides; a GUI/editor; persisting param presets
server-side; exposing salts/math/`ARCH_ISLANDS`; the frozen flat track.
