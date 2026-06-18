# Plan — elevation S5: coupled uplift ⇄ erosion (full rewrite)

> Stage S5 of the elevation-redesign arc
> (`docs/specs/2026-05-31-elevation-redesign.md`). Size **XL**. Fixes **D5**
> (erosion ran as a one-shot post-process on ridged-fBm *noise* mountains, not
> coupled with uplift toward a steady state). **PO chose the full-coupling
> rewrite** (option A) over augment/accept.

## Premise (empirically verified on HEAD, seed sweep Continent)

A slope–area regression over channel cells (drainage ≥ 8) gives concavity
**θ ≈ 0.81** — HEAD's drainage is *already* concave and dendritic, because
stream-power `erosion.rs` already runs (just post-process), and S1 already gates
relief onto the convergent belts (`belts_fill` 85 %+). So the spec's *literal*
S5 acceptance is largely met. **The real D5 gap:** the mountain *relief itself*
is ridged-fBm **noise** gated by uplift — not topography that **emerged** from
uplift being balanced by erosion. θ = 0.81 (steeper than the 0.5 uniform-uplift
steady state) reflects noise-shaped + variable-K relief, not a fluvial equilibrium.

## Design — the coupled landscape-evolution model

Replace `land_relief`'s ridged-fBm ranges + the one-shot `erosion::apply_with`
carve with an **iterated coupled loop** (`dh/dt = U − K·A^m·S^n + D·∇²h`,
detachment-limited, m=0.5 / n=1 fixed):

1. **Initial land surface** = `base + uplift + plains_whisper`. The isostatic
   base + the tectonic uplift skeleton (smooth belts) + the small fBm plains
   texture (drainage seed). **The ridged-fBm "noise mountains" (belt ranges +
   interior uplands) are dropped** — relief now comes from uplift + carving.
2. **Couple loop** (`erosion::couple`, new; reuses `priority_flood` /
   `flow_accumulation` / `incise` / `diffuse`): for `couple_iters` steps —
   - **uplift forcing:** land `elev[c] += couple_uplift_rate · uplift[c].max(0)`
     (replenishes the belts against erosion → they reach a U⇄E balance instead
     of decaying);
   - **flow + incise:** priority-flood → drainage → `incise(settle_rate = 0)`
     (detachment-limited stream-power, already clamped to the receiver drop);
   - **hillslope diffusion** (`couple_diffusion`).
   Toward steady state `U = K·A^m·S^n` → **concave profiles emerge from the
   physics**, ridges/valleys organised by the drainage network (not fractal noise).
3. **Erosion is no longer ruggedness-gated** — the S1 `rugged` field was a hack to
   keep plains flat while eroding noise; in the coupled model plains are flat
   because they have *low uplift* (low U → low steady relief), so K is uniform.
4. **Ocean unchanged** — S4 age bathymetry; sea cells stay fixed outlets.
5. **Profile mode + the frozen flat track untouched** — `height_at`/`apply_falloff`
   + `erosion::apply`/`apply_with` keep their signatures; `couple` is additive.

## Parameters (`ReliefParams`, S5 block)

- `couple_iters` (timesteps, e.g. 25), `couple_uplift_rate` (U scale per step),
  `couple_erodibility` (K), `couple_diffusion` (D). m/n stay fixed math.
- The now-unused Tectonic ridged-relief fields (`tect_belt_lift`,
  `tect_range_weight`, `interior_rugged_cap`, `rugged_freq`, `tect_uplift_lo/hi`)
  are **kept as serde fields** (no param-surface break) but documented as
  Tectonic-legacy / inert in coupled mode; `tec_hill_weight`/`tec_plain_weight`/
  `plain_freq` still drive the plains whisper. (A dead-param cleanup is a tracked
  follow-up, not an S5 break.)

## Tuning (empirical — this is the bulk of the XL work)

S5 deliberately changes default land elevation. Calibrate `couple_*` so the land
mix stays in the established acceptance bands (no catastrophic skew), then re-pin:

- `belts_fill_and_concentrate` (high-relief on convergent belts ≥ 85 % conc /
  ≥ 40 % arc-fill) — should *improve* (relief now is uplift-driven).
- `mountains_stay_a_land_minority` (high ≤ 40 %, lowland ≥ 25 %).
- `terrain_proportions_stay_in_band` (land 18–42 %, Desert 10–35 %, Marsh ≤ 20 %).
- `elevation_histogram_is_bimodal` (S3 lock).
- **New S5 metric:** slope–area concavity θ pulled toward 0.5 (target band, e.g.
  0.4–0.7) — the equilibrium signature, vs HEAD's 0.81.

## Pins to re-capture

- `tests/parameterization.rs::default_profile_is_byte_identical_baseline` (3).
- `src/render.rs::render_output_is_byte_identical_baseline` (8).
- **Unaffected:** `profile_mode_is_byte_identical_baseline` (Profile never uses
  the coupled land path) — verify it stays green.

## Out of scope

S6 (render/export bathymetry + final hypsometry calibration). Transport-limited
deposition / sediment fans (the coupled model is detachment-limited — the
existing settle phase stays available for Profile/flat callers).
