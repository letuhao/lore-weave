# PLAN — Köppen v2 seasonality (DEFERRED #045)

> Size **L**. Session 100 cont. Branch `world-gen-sdk-refactor`. The structural
> fix that unblocks the temperate C-band AND polar/tundra band, so the
> continent-latitude placement lever (shipped opt-in) pays off. PO chose the
> **full** fix (amplitude rebalance + cosine insolation).

## Root cause (#045)

`climate.rs::build` uses **linear** insolation (`lerp(28,−15,lat_dist)` — too cold
at mid-lat, 6.5 °C at 45°) and a seasonal amplitude `(AMP_EQ + AMP_LAT·lat_dist)·(1
+ AMP_CONT·cont)` whose **maritime base** (cont=0) reaches 30 °C at the pole. So
maritime high-lat coasts get warm summers (`t_warm≫10` → never Polar/Tundra) and
mid-lat winters plunge (`t_cold≪−3` → never Temperate). The C-band and the polar
band are both skipped.

## Fix (two levers)

1. **Cosine insolation** — `temp_sea = T_POLE + (T_EQ−T_POLE)·cos(lat_dist·π/2)`.
   Concave ⇒ ≥ the linear chord ⇒ warms mid-latitudes (~6.5→15 °C at 45°); exact at
   equator (28) and pole (−15).
2. **Continentality-gated amplitude** — `amp = AMP_EQ + (AMP_MARITIME +
   AMP_CONT_GAIN·cont)·lat_dist`. Maritime (cont≈0) stays low-amp at ALL latitudes
   (→ cold mean + low amp = Polar/Tundra at high lat; mild C-band at mid lat);
   interiors still swing wide (→ Boreal). Start: `AMP_EQ=2, AMP_MARITIME=6,
   AMP_CONT_GAIN=24` (maritime pole 8, continental pole 32, maritime mid 5).

`classify_koppen`, `circulation_precip_mm`, `moisture_field`, the bias, and the
8-zone mapping are **unchanged**. Only `build()`'s temp derivation + `seasonal_amp`
change; add a private `insolation_temp(lat_dist)`.

## Files

`climate.rs` only: replace the `lerp(T_EQ,T_POLE,..)` line with `insolation_temp`;
rewrite `seasonal_amp` + consts (drop `AMP_LAT`/`AMP_CONT`, add `AMP_MARITIME`/
`AMP_CONT_GAIN`); add `insolation_temp`.

## Tests (climate.rs)

- `insolation_warms_midlatitudes` (NEW) — `insolation_temp(0.5)` > the linear
  midpoint `(T_EQ+T_POLE)/2`; endpoints exact (28 / −15).
- `maritime_stays_low_amplitude` (NEW) — `seasonal_amp(1.0, 0.0)` small (< ~10) vs
  `seasonal_amp(1.0, 1.0)` large (> ~25): the headline property.
- `build` composition headline (NEW or extend gradient test) — a maritime mid-lat
  cell (`insolation(0.5)`+low amp, wet) → **Temperate**; maritime high-lat
  (`insolation(0.9)`+low amp) → **Polar**. Proves both bands open.
- existing `build_derives_a_latitude_climate_gradient`, `classify_koppen` tests,
  `all_eight_zones_are_reachable`, determinism — must stay green.

## Calibration (empirical loop)

Regenerate seed-7 megaplanet at **spread=0** (dry-belt land — preserve Köppen
desert) AND **spread=1** (pole-spanning land — Tundra must appear). Tune
`AMP_MARITIME`/`AMP_CONT_GAIN` (+ cosine if needed) until:
- spread=0: Desert ~30–40 % (preserve the Köppen win); **Temperate now > 0**.
- spread=1: **Tundra > 0** at high lat; Boreal + Polar + Temperate all present.
- equator=Tropical, pole=cold; all 8 zones reachable. No literal hash pin.

## Side effects

`content_hash` re-bases for ALL worlds (climate model change — intended;
default-world hash will differ from the placement commit). No literal hash pinned.

## Out of scope

Real `winter_frac` Cs/Cw subtypes (still v2b); 19-subtype palette; ocean-current
E-W delta.
