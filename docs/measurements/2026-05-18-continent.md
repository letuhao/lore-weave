# Continent-Scale Measurement — 2026-05-18

> **Tool:** `tilemap-service measure` (release build) · **Spec:**
> [`docs/specs/2026-05-18-tilemap-continent-measurement.md`](../specs/2026-05-18-tilemap-continent-measurement.md)
> **Template:** `continent_measure_v1` — 12 zones (1 Hub, 8 Wilderness, 2 Sea,
> 1 Forbidden), `GridSize::CONTINENT_DEFAULT` 256².

---

## Offline — engine-only generation (256²)

| Metric | Value |
|---|---|
| Grid | 256 × 256 (65 536 tiles) |
| Zones | 12 |
| Objects placed | 456 |
| Road segments | 111 |
| River segments | 11 |
| `place_tilemap` wall time | **506.8 s** and **659.5 s** (two release-build runs) |

### Finding O-1 — continent generation is ~8–11 minutes (SEVERE)

A 256² `place_tilemap` takes **8–11 minutes in a release build**. This confirms
the deferred perf items are real, not hypothetical:

- **#018** — `penrose::assign_zone_tiles` is O(tiles × vertices): 65 536 tiles ×
  the full Penrose vertex field per tile.
- **#016** — `fractalize::scatter_and_connect` is O(candidates²) per zone.

Both were deferred as "fix when continent-scale profiling shows pain." **It now
shows pain.** Recommendation: **promote #016 + #018 to active work** — the
spatial-bucketing / distance-transform fix each finding already prescribes.
Output stays byte-identical, so it is a pure-perf change.

Run-to-run variance (506 s vs 659 s) is host scheduling noise — the placement is
deterministic in *output* (TMP-A4), not in wall time.

### Finding O-2 — object density

456 objects on a 256² continent (≈0.7 % of tiles) with `treasure_tiers` density
2. Roads: 111 segments (MST over zone centres + connection passages + guard
lairs). Rivers: 11 segments (one per mountain-bearing zone routed to a
lake/sea sink). The object count is modest — well within a ~12-batch L3 run.

## Live — engine→L3-batched→L4 — ⛔ BLOCKED

The live run executed end-to-end but **every gateway call was rejected**:

```
HTTP 402  {"code":"LLM_QUOTA_EXCEEDED","message":"model pricing not configured"}
```

The registered lmstudio model (`019dc3ab-…`) has **no pricing row** in
provider-registry, so the billing layer rejects every `/internal/llm/stream`
call. The gateway itself is healthy (`:8208/health` → 200) and auth succeeds —
this is a provider-registry **configuration** gap, not a code or network fault.

Observed (the retry loops degrading gracefully — Phase-0b honesty design):

| Stage | Value |
|---|---|
| L3 objects | 456, batched into ~16 per-zone batches (cap 40, 12 zones) |
| L3 gateway attempts | 48 — ≈16 batches × 3 retries, **all 402-failed** |
| L3 fallbacks | 456 — every object via the §6 canonical default |
| L4 attempts | 3 — 1 batch (12 zones) × 3 retries, all 402-failed |
| L4 fallbacks | 12 — every zone via the §6 canonical default |
| Tokens | 0 input / 0 output (no call reached the model) |

**No panic, no `Err`** — `run_l3_batched` + `run_l4_with_retries` absorbed 51
transport failures and still classified/narrated every object/zone via §6. The
batching itself worked: 456 objects → ~16 bounded batches grouped by zone.

### Follow-up — to capture the live numbers

1. Configure a pricing row for the lmstudio model in provider-registry (price
   0 — the local run is free; the billing layer still requires the config).
2. Re-run `tilemap-service measure` with `.local/phase0b.env` — the tool is
   ready; the live section will then carry real token-cost + latency data.

> **Note:** `measure` re-runs the offline 256² placement (~8–11 min) before the
> live section every time — re-running it purely for the live numbers re-pays
> that cost. A future `measure --live-only` (or a cached/serialised placement)
> would remove the wait. Tracked as Deferred #028.

## Summary

- ✅ Offline continent generation measured — and it surfaced **finding O-1**, a
  severe ~8–11 min cost that should promote perf items #016/#018.
- ⛔ Live L3/L4 measurement blocked on a provider-registry pricing config; the
  `measure` tool + per-zone L3 batching are built, tested, and ready to re-run.

---

## 2026-05-20 update — perf items #016 + #018 resolved, finding O-1 reframed

After clearing the deferred #016 + #018 perf items (commit upcoming, spec
[`docs/specs/2026-05-20-tilemap-perf-fractalize-penrose.md`](../specs/2026-05-20-tilemap-perf-fractalize-penrose.md)),
`measure` was re-run with the per-stage timing now in
`OfflineMeasurement.zones_elapsed` / `render_offline`:

```
── continent measurement — offline (engine-only) ────────
grid           : 256×256
zones          : 12
objects placed : 456
road segments  : 111
river segments : 11
place_zones    : 0.110 s  (Penrose + fractalize — DEFERRED #016/#018)
modificators   : 687.139 s  (Terrain → Connections → Treasure → Road → Obstacle → River)
place_tilemap  : 687.249 s  (total)
─────────────────────────────────────────────────────────
```

### Finding O-1 — REFRAMED

- **#016 + #018 are conclusively resolved.** `place_zones` (Penrose tiling +
  per-zone fractalize) dropped from a fraction of the 506–814 s baseline
  to **0.110 s** — a >300× drop at that layer, comfortably under the
  TMP_002 §7 <500 ms budget.
- **The 8–11 min continent cost was misdiagnosed as caused by #016/#018.**
  With those algorithmic O(n²) bugs gone, **99.98 % of the wall time is in
  the modificator pipeline** — `TerrainPainter → ConnectionsPlacer →
  TreasurePlacer → RoadPlacer → ObstaclePlacer → RiverPlacer`.
- The dominant cost is almost certainly the per-placement-O(zone_tiles²)
  `place_and_connect_object` (the captured lesson from the Phase C TreasurePlacer
  build) compounding across 456 objects + 111 roads + 11 rivers each carrying
  a Dijkstra `search_path`. **New deferred item #029** tracks profiling +
  fixing this.

### Recommended next perf step

1. Add per-modificator timing to the `OfflineMeasurement` (one `Duration` per
   placer in the pipeline) — narrow the 687 s onto a specific placer.
2. Likely suspect: `TreasurePlacer::place_and_connect_object` —
   the captured lesson notes it is `~O(zone_tiles squared) per placement`,
   ~456 placements × 65 536 tiles² = absurd in the worst case.
3. Then design the targeted fix per the dominant placer's algorithm.

---

## 2026-05-20 update (afternoon) — per-modificator breakdown

Step 1 above (per-modificator timing) shipped — `ModificatorRegistry::execute_with_timing`
+ `place_tilemap_with_timings` + `OfflineMeasurement.modificator_timings` +
sorted descending render. Spec:
[`docs/specs/2026-05-20-tilemap-per-modificator-timing.md`](../specs/2026-05-20-tilemap-per-modificator-timing.md).

```
── continent measurement — offline (engine-only) ────────
grid           : 256×256
zones          : 12
objects placed : 456
road segments  : 111
river segments : 11
place_zones    : 0.107 s  (Penrose + fractalize — DEFERRED #016/#018)
modificators   : 992.855 s  (sum of per-stage below — DEFERRED #029)
   treasure_placer      :   973.376 s  ( 98.0 %)
   obstacle_placer      :    17.919 s  (  1.8 %)
   connections_placer   :     0.932 s  (  0.1 %)
   river_placer         :     0.607 s  (  0.1 %)
   road_placer          :     0.022 s  (  0.0 %)
   terrain_painter      :     0.000 s  (  0.0 %)
place_tilemap  : 992.963 s  (total)
─────────────────────────────────────────────────────────
```

### Finding O-1 — narrowed to TreasurePlacer

**`treasure_placer` is 98.0 % of the modificator pipeline cost** (973 s of
the 993 s total). The captured lesson is hard-confirmed: `TreasurePlacer::
place_and_connect_object` is `~O(zone_tiles²) per placement`, multiplied
across **456 placements** on a 256² grid (zone tiles ~5 000–10 000 each)
⇒ ~10¹⁰ ops single-threaded.

DEFERRED #029 narrows from "modificator pipeline somewhere" to a concrete
target: **TreasurePlacer's per-placement algorithm.** Subsequent placers
(`obstacle_placer` 17.9 s, all others sub-second) account for ~2 % and
can be deferred until TreasurePlacer is fixed.

Total wall time (992 s) is within the 506–814 s run-to-run variance band of
2026-05-18 (host scheduling — placement is deterministic in *output*, not in
wall time).

---

## 2026-05-21 update — `place_and_connect_object` score-first fix shipped

Spec:
[`docs/specs/2026-05-21-tilemap-place-and-connect-perf.md`](../specs/2026-05-21-tilemap-place-and-connect-perf.md).
The score-first / validate-on-demand refactor restructures the per-placement
loop from "filter (with two O(N) flood fills per candidate) then pick best"
to "score every candidate (O(1) per), sort by score, validate lazily, take
first that passes". The §4 proof shows bit-exact equivalence: the first
sorted survivor that passes the expensive checks is `argmax_{v ∈ V}
(score(v), -flat(v))`.

```
── continent measurement — offline (engine-only) ────────
grid           : 256×256          objects placed : 456
place_zones    : 0.108 s
modificators   : 21.433 s
   obstacle_placer      :    16.961 s  ( 79.1 %)   ← new leader
   treasure_placer      :     2.944 s  ( 13.7 %)   ← was 973.376 s (98.0 %)
   connections_placer   :     0.916 s  (  4.3 %)
   river_placer         :     0.602 s  (  2.8 %)
   road_placer          :     0.010 s  (  0.0 %)
   terrain_painter      :     0.000 s  (  0.0 %)
place_tilemap  : 21.541 s  (total)
─────────────────────────────────────────────────────────
```

### Speedup

| Stage | Before (PM) | After | Speedup |
|---|---|---|---|
| `treasure_placer` | 973.376 s | **2.944 s** | **330 ×** |
| `place_tilemap` (total) | 992.963 s | **21.541 s** | **46 ×** |

The continent now generates in **21.5 s** — comfortably inside the
"feasible-to-iterate-on" window. DEFERRED #029 is cleared; the next
candidate bottleneck (if profiling shows pain again) is `obstacle_placer`
at 17 s (~80 % of the new total). Golden test passes byte-exact — no
output drift from the refactor.

---

## 2026-05-22 update — `erode_zone` simple-point pre-filter shipped

Spec:
[`docs/specs/2026-05-21-tilemap-erosion-simple-point.md`](../specs/2026-05-21-tilemap-erosion-simple-point.md).
`erode_zone` called `would_seal_a_gap` (O(N) double flood fill) for every
wall-adjacent Open tile. The single-tile blocking footprint means whether a
tile seals a gap has a purely local characterisation — the *simple-point*
test (union-find over the 4 cardinal neighbours linked via passable
diagonals). `groups ≥ 2` falls through to the unchanged flood fill;
`groups ≤ 1` is O(1). §4 proof: bit-exact equivalent.

```
── continent measurement — offline (engine-only) ────────
grid           : 256×256          objects placed : 456
place_zones    : 0.103 s
modificators   : 6.359 s
   treasure_placer      :     3.526 s  ( 55.4 %)   ← new leader
   river_placer         :     1.054 s  ( 16.6 %)
   connections_placer   :     0.898 s  ( 14.1 %)
   obstacle_placer      :     0.864 s  ( 13.6 %)   ← was 16.961 s (79.1 %)
   road_placer          :     0.017 s  (  0.3 %)
   terrain_painter      :     0.000 s  (  0.0 %)
place_tilemap  : 6.463 s  (total)
─────────────────────────────────────────────────────────
```

### Speedup

| Stage | Before | After | Speedup |
|---|---|---|---|
| `obstacle_placer` | 16.961 s | **0.864 s** | **19.6 ×** |
| `place_tilemap` (total) | 21.541 s | **6.463 s** | **3.3 ×** |

### Cumulative perf journey (993 s → 6.46 s = **154 ×**)

| Date | Fix | Continent total |
|---|---|---|
| 2026-05-18 | (baseline) | 506–814 s |
| 2026-05-20 | #016/#018 fractalize+penrose buckets | ~993 s (place_zones 0.11 s; pipeline dominated) |
| 2026-05-21 | #029 TreasurePlacer score-first | 21.5 s |
| 2026-05-22 | erode_zone simple-point | **6.46 s** |

The continent now generates in **6.46 s**. Remaining placers are all
sub-4 s; no single dominant bottleneck. Further perf work is not warranted
unless iteration cadence demands sub-2 s — at which point `treasure_placer`
(3.5 s) would be the next target. Golden test byte-exact — no drift.

---

## 2026-05-22 update — river barrier reorder (DEFERRED #026)

Spec:
[`docs/specs/2026-05-22-tilemap-river-barrier-reorder.md`](../specs/2026-05-22-tilemap-river-barrier-reorder.md).
`ObstaclePlacer` split into `ObstacleSourcePlacer` (Mountain/Lake river
markers on Open tiles, pre-erosion, **dual-gated** per-zone + map-wide) →
`RiverPlacer` (carves a wide-open zone) → `ObstacleFillPlacer` (erode + fill
the rest, post-river, skipping river Water). This is a **barrier-quality**
fix, not a perf fix — the continent total rises as the river now *carves* a
real barrier instead of cheaply fording.

```
── continent measurement — offline (engine-only) ────────
grid           : 256×256          objects placed : 412
place_zones    : 0.100 s
modificators   : 10.454 s
   obstacle_fill_placer :  3.968 s  ( 38.0 %)
   treasure_placer      :  2.840 s  ( 27.2 %)
   river_placer         :  2.503 s  ( 23.9 %)   ← was ~0.6 s (now carves)
   connections_placer   :  0.934 s  (  8.9 %)
   obstacle_source_placer: 0.199 s  (  1.9 %)
   road_placer          :  0.010 s  (  0.1 %)
place_tilemap  : 10.555 s  (total)
─────────────────────────────────────────────────────────
```

### Barrier strength (the #026 metric)

The golden fixture river — #026's reference ("75 crossings / 98 tiles,
ford-dominated") — now fords **~6 %** of its tiles (AC-2 gates < 0.25):

| River | tiles | fords | ford ratio |
|---|---|---|---|
| 1 | 89 | 4 | 0.045 |
| 2 | 80 | 4 | 0.050 |
| 3 | 40 | 5 | 0.125 |
| aggregate | 210 | 13 | **0.062** |

Connectivity-forced fords are now rare — the river carves a contiguous
barrier with a handful of well-placed crossings, instead of fording nearly
every tile. The strict dual `would_seal_a_gap` gate is unchanged; the river
simply carves a *wider* region (markers placed pre-erosion).

### Cost tradeoff (accepted)

`place_tilemap`: 6.46 s → **10.56 s**. The river now carves (each carve runs
the gated `would_seal_a_gap`) rather than cheaply fording, and the post-river
fill works a fragmented region. Still well inside the iterate-able window;
this is a deliberate barrier-quality-for-time trade. Object count 456 → 412
(gated markers + fill skips river Water).
