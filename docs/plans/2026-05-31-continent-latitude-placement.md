# PLAN — continent-latitude placement (terrain track)

> Size **L**. Session 100 cont. Branch `world-gen-sdk-refactor`. The biome-variety
> lever after Köppen (DEFERRED #045 context): seed-7 land clusters at |lat|≈30°
> (nothing above 75° → Tundra=0). Spread continents across latitudes for a full
> latitudinal biome gradient.

## Root cause

[plates.rs:92](../../crates/world-gen/src/plates.rs#L92) seeds plates uniform-random;
[plates.rs:133-140](../../crates/world-gen/src/plates.rs#L133-L140) picks the
continental subset by a random shuffle. Land latitude is an unconstrained draw.

## Decision (PO-approved)

**Approach A** (stratified continental *selection* — no geometry change) + a
**`continent_latitude_spread: f32`** knob, **spread=0 = byte-identical**.

> **Default revised to 0.0 (opt-in) at POST-REVIEW** (was 0.6). Empirical data
> showed default 0.6 drops Desert 36%→8% (undoes the Köppen target) and yields a
> bimodal tropical(54%)/boreal(23%) world with **Tundra still 0** — because the
> full tropics→tundra gradient is gated on DEFERRED #045 (seasonal-amplitude
> squeeze: high-lat land gets warm summers → Boreal not Polar/Tundra). PO chose:
> ship placement opt-in (default world byte-identical), then fix #045 next so the
> gradient is real before making spread the default. The knob is also effectively
> a **threshold switch** at the default plate count (~3 continental plates):
> seed-7 spread 0.15/0.3/0.45 ≡ 0.0; only ≥~0.6 flips. More plates → smoother.

## Algorithm (plates.rs)

Keep the `shuffle` call (preserves RNG stream → downstream motion vectors
byte-identical). Use it as a **rank**: `rank[order[i]] = i`. Then greedily select
`n_cont` continental plates by **farthest-point over signed sin-latitude** `z = seeds[p][2] ∈ [−1,1]`:

```
spread = continent_latitude_spread.clamp(0,1)
cost(p) = (1-spread)*(rank[p]/n) - spread*min_zdist_to_chosen(p)   // min_zdist=0 for first pick
repeat n_cont times: pick unchosen p minimizing (cost, rank[p], p) via total_cmp
mark chosen plates Continental
```

- spread=0 → cost = rank/n → picks `order[0..n_cont]` = **today's set, byte-identical**.
- spread=1 → cost = −min_zdist → farthest-point spread covering both poles + equator.
- **Signed** z (not |lat|) covers the climate-cold +z pole for every hemisphere
  orientation → no terrain↔climate coupling.
- No RNG consumed by the greedy; motion vectors drawn after stay identical.

## Plumbing (the field)

1. `creative_seed.rs` — add `continent_latitude_spread: f32` + `#[serde(default = "default_continent_latitude_spread")]` (0.6) + Default impl entry.
2. `lib.rs::generate` — pass `cs.continent_latitude_spread` to `terrain::build`.
3. `terrain.rs::build` — accept param, thread into `plates::build` (Tectonic arm only).
4. `plates.rs::build` — new `continent_latitude_spread: f32` param + greedy selection.
5. `main.rs` — CLI arg `--continent-latitude-spread` (default 0.6) + literal field at :283.
6. `author.rs` — JSON schema entry (0..1) + system-prompt line + clamp in `parse_creative_seed`.

## Tests

- `plates.rs`: `spread_zero_is_identical_to_legacy_selection` (build with spread=0 vs the
  old shuffle-take set — same continental plate ids); `spread_one_spreads_latitude`
  (continental seed-z spread/range strictly greater at spread=1 than spread=0 on a seed
  where they differ); determinism unchanged.
- `creative_seed`: serde default round-trips (pre-field JSON loads with 0.6).

## VERIFY

cargo test -p world-gen green; clippy clean. Empirical: regenerate Megaplanet seed-7
at spread 0/0.6/1.0, biome histogram — expect Tundra/Boreal/Polar to APPEAR and land
to span more |lat| bands as spread rises. spread=0 hash must equal the pre-change hash
(byte-identical guarantee). Honest: Temperate may stay low (structural, DEFERRED #045).

## Out of scope

Temperate C-band recovery (v2 seasonality, #045); per-plate extent latitude (uses seed
z as proxy); approaches B/C.
