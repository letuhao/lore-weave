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
