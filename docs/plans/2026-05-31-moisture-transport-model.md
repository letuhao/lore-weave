# PLAN — moisture-transport model (DEFERRED #046)

> Size **L**. Session 100 cont. Branch `world-gen-sdk-refactor`. The last lever to
> complete the latitudinal biome gradient: wet continental interiors so the
> dry-Arid / cold-Boreal mid-latitudes become a green **C-group** band (Subtropical
> forest + Temperate plains). climate.rs `moisture_field` only.

## Root cause (#046)

`moisture_field` is a single prevailing-wind sweep that **averages** upwind
neighbours and depletes monotonically inland. Averaging dilutes the wettest route,
so a cell near an upwind coast in a *non-primary* direction dries out — interiors →
~0 → warm-interior Arid / cold-interior Boreal; the wet-mild C-group survives only
in thin windward strips.

## Decision (PO-approved)

**Downwind-directed multi-source transport (MAX-propagation).** A finding during
design: a *pure omni-directional* "distance to nearest sea" base breaks offshore-wind
dryness (the `rain_shadow` east case + real continental dryness). The correct
multi-directional model is **wind-aware**: moisture flows downwind from upwind seas.

## Algorithm (replace the AVG sweep)

Same downwind sweep (proj-sorted), but per cell take the **best (wettest) upwind path**:
```
for i in downwind order:
  if sea: moisture[i] = 1.0; continue
  best = max over upwind nbrs (proj(nb) < proj(i)) of
           moisture[nb] − land_leak − OROGRAPHIC · max(0, (elev[i]−elev[nb])/65535)
  moisture[i] = if any upwind nbr { best.max(0) }
                else /* windward edge = off-map upwind ocean */
                     { (1.0 − OROGRAPHIC · max(0,(elev[i]−sea_level)/65535)).max(0) }
```
- **MAX not AVG** ⇒ a cell is as wet as its wettest upwind route allows → interiors
  near any upwind coast stay wetter (multi-directional within the upwind cone).
- **Upwind-only + windward-edge off-map ocean** ⇒ offshore-wind coasts stay dry,
  rain shadows behind ranges persist (all upwind paths shadowed). Preserved.
- `land_leak` resolution-scaled as today; retune in calibration if needed.

## Tests (climate.rs)

- `rain_shadow_follows_the_wind` — unchanged assertions; traced to still pass (linear
  chain: MAX = the only upwind path).
- `moisture_takes_wettest_upwind_path` (NEW) — a cell with two upwind neighbours
  (one wet near-sea, one dry behind a ridge) takes ~the wet one (MAX), not the
  average — the headline behaviour that wets interiors.
- determinism + existing climate tests unaffected.

## Calibration (empirical)

Regenerate seed-7 mega at spread 0 and 1 (+ Equatorial spread=1). Tune `land_leak`:
- Desert stays ~30–40 % at spread=0 (dry belt is circulation-base-limited, should hold).
- mid-latitude **C-group (Subtropical+Temperate) rises** — a green temperate band
  replaces dry Arid/Boreal; Plain/Forest more abundant.
- Tundra/Polar (from #045) preserved; rain shadows still visible. No literal hash pin.

## Side effects

`content_hash` re-bases (moisture model change → climate → all worlds; intended).

## Out of scope

8-zone mapping change (Dfa/Dfb→Temperate) — a separate classifier lever; real
`winter_frac` Cs/Cw; ocean-current E-W delta.
