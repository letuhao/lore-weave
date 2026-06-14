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

## 0 — Audit (this session, full `const` sweep of `crates/world-gen/src`)

| Group | Examples | Disposition |
|---|---|---|
| **A. Generation tuning (sphere)** ~55 | `plates.rs` (16): `CONT_BASE`, `OCEAN_BASE`, `FOLD_PEAK`, `ARC_PEAK`, `TRENCH_DEPTH`, `ISLAND_ARC_PEAK`, `RIDGE_PEAK`, `RIFT_DEPTH`, `FAULT_PEAK`, `DECAY_HOPS`, `OCEAN_CRUST_KM`, `CONT_CRUST_KM`, `COLLISION_THICKEN_KM`, `PLATEAU_HOPS`, `CONT_ISO_SLOPE`, `FAULT_SHEAR_RATIO`, `PLATE_WARP_{FREQ,AMP,OCTAVES}` · `terrain.rs` (~27): `TECT_UPLIFT_{LO,HI}`, `TECT_BELT_LIFT`, `TECT_RANGE_WEIGHT`, `INTERIOR_RUGGED_CAP`, `TEC_{HILL,PLAIN}_WEIGHT`, `OCEAN_{SHELF,ABYSS,ABYSS_HOPS,RIPPLE_*,ARC_GATE_*}`, `SEA_FRAC`, `LAND_FULL`, `OCEAN_FULL`, `ARCH_RADIUS`, noise `*_FREQ`/`*_OCTAVES`/`*_WEIGHT` · `climate.rs` (12): `T_EQ`, `T_POLE`, `LAPSE_C`, `PRECIP_{EQ,SUBTROPIC,MIDLAT,POLAR}`, `AMP_{EQ,MARITIME,CONT_GAIN}`, `WINTER_FRAC_V1`, `HIGHLAND_ELEV`, `OROGRAPHIC`, `LAND_LEAK_BASE` | **EXPOSE** (granular + macro) |
| **B. Internal / determinism** ~20 | `SALT_*` (×13 noise decorrelation), `GOLDEN_ANGLE`, fBm `OFFSET`/`GAIN`, `FRAC_1_SQRT_2`, `CLIPPER_SCALE`, `ARCH_ISLANDS` (fixed geometry), array sizes, `NONE` sentinels | **KEEP internal** (exposing salts/math is meaningless and would muddy determinism) |
| **C. Render-only** ~25 | `render.rs` colors/palettes, `BACKGROUND`, `SS` supersample, `relief.rs` render (`WARP/DETAIL/RELIEF_*/OCC_*`) | **EXPOSE as `RenderTheme`** (not in `content_hash`; P4) |
| **D. Frozen flat track** | `flatworld.rs`, `flat_climate.rs`, `zonegen.rs` | **DO NOT TOUCH** (CLAUDE.md frozen-track rule) |
| **E. Authoring (LLM)** | `author.rs`/`naming.rs` prompts, `civ_adapter.rs` name lists | **Out of scope** (not generation tuning) |

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
add ~55 granular flags (config-file territory).

## 2 — Staged plan (each stage byte-identical-baseline + tests + commit)

| Stage | Builds | Size |
|---|---|---|
| **P1** | `TectonicsParams` (the 16 `plates.rs` consts) + `IntensityKnobs` scaffold (`orogeny`, `collision_frequency`) threaded into `plates::build`. | L |
| **P2** | `ReliefParams` (the ~27 `terrain.rs` consts: relief, bathymetry, quantize, noise) + `relief`/`ocean_depth` knobs into `terrain::build`. | L |
| **P3** | `ClimateParams` (the 12 `climate.rs` consts) + `warmth`/`rainfall`/`seasonality` knobs into `climate::build`. | L |
| **P4** | `RenderTheme` (render/relief colors, palettes, supersample) + CLI macro flags + a worked example config. | M |

**Order:** P1 → P2 → P3 → P4. Each stage: move its consts into a `Default`,
thread params, add (a) a **byte-identical-baseline test** (default config → same
`content_hash` as a pinned pre-refactor digest *or* the determinism cross-check),
(b) a **knob-does-something test** (a non-default value changes the output), (c)
a **clamp test** (out-of-range input is clamped, no panic). Full 12-phase +
`/review-impl` + PO POST-REVIEW per stage.

## 3 — Cross-cutting rules

- **Byte-identical defaults** is the load-bearing invariant — verified per stage.
- **Determinism preserved** — params feed output values only; salts/math stay
  fixed internal. `content_hash` re-bases only when a param value actually differs.
- **Frozen flat track untouched**; **authoring layer untouched**.
- **No new provider/SDK/secret surface** — pure local compute.
- Backward-compat: every existing `CreativeSeed` JSON + every `author` LLM output
  keeps working (serde default).

## 4 — Out of scope (this arc)

Per-biome/per-feature parameter overrides; a GUI/editor; persisting param presets
server-side; exposing salts/math/`ARCH_ISLANDS`; the frozen flat track.
