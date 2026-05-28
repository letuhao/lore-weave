# GEO — Terrain Coherence Spec: Flat Plains + Localized Relief

> **Status:** DESIGN SPEC (research done; no code yet). Addresses the top
> quality blocker from the Phase-2 quality pass (`ce87bdcb`): the world map is
> **uniformly noisy** — every cell's height jitters, there are no genuinely
> *flat* plains, and the ocean floor is lumpy. The structural foundation
> (sphere mesh, plate tectonics, Earth hypsometry, fast hull) is solid; this
> spec fixes the *noise spectrum*.
>
> **PO directive (2026-05-22):** research game/DEM prior art first, write a
> detailed spec, then implement.

---

## 1 — The problem, measured

From last session's histogram analysis (now correct): sea at 0.40 of range,
land fills 0.60, Earth-like hypsometric *distribution* (62% lowland / 23%
upland / 6.5% mountain). **But the relief is wrong in character:** the
high-frequency fBm (`tectonic_relief`: hills + ridged detail) runs at **full
amplitude everywhere**, gated only by `landness` + a belt mask. So a "lowland"
cell still jitters as much as a mountain cell — there are no macro-flat
regions. The ocean floor gets a uniform abyssal fBm → lumpy, not the flat
abyssal plains of a real ocean.

PO's words: *"không thật sự có đồng bằng mà mọi thứ lồi lõm lộn xộn… kể cả vùng
nước"* — no real plains, everything chaotically bumpy, including the water.

---

## 2 — Research: how the field solves this

### 2a — Musgrave: "statistics by altitude" (THE core technique)

The canonical answer (F. K. Musgrave, *Procedural Fractal Terrains*, and the
`musgrave.c` reference implementation). Real terrain is **not uniformly
rough**: *"low-lying areas tend to fill up with silt and become
topographically smoother, while erosive processes keep higher areas more
jagged."* The procedural realization makes **per-octave detail amplitude
depend on the accumulated elevation**:

- **fBm** (what we use) is *stateless* — every octave contributes equally
  regardless of height → **uniformly rough at all elevations** = our bug:
  ```
  value += noise(p) * weight[i]
  ```
- **HeteroTerrain** — scale each octave by the current accumulated height:
  ```
  increment = (noise(p) + offset) * weight[i]
  increment *= value            // ← feedback: low value ⇒ small increment
  value     += increment
  ```
  Low areas (small `value`) get tiny increments → **smooth/flat**; high areas
  amplify roughness → **jagged**.
- **HybridMultifractal** — multiplicative weight feedback (smooth rolling
  lowlands, jagged detailed peaks):
  ```
  signal  = (noise(p) + offset) * weight[i]
  result += w * signal
  w      *= signal              // ← low signal ⇒ later octaves suppressed
  ```
- **RidgedMultifractal** — `offset − |noise|`, squared → sharp mountain
  ridgelines (we already have `ridged_fbm`).

**Takeaway:** detail amplitude must be a **function of a control variable**
(altitude / ruggedness), not constant. This is the single highest-impact fix.

### 2b — World Machine / Gaea: macro layout + masks + erosion

Industry terrain tools (World Machine, Gaea, World Creator) layer:
1. a **macro layout** (sketched/Voronoi continents + where mountains go) —
   *we have this* (`plates.rs`);
2. **selector masks** by slope/height that gate where detail, texture and
   erosion apply — the practical, art-directable form of Musgrave's
   altitude-feedback;
3. **hydraulic erosion** that carves valleys *and* **deposits sediment in
   basins/valley floors → flattens them** (World Machine exposes a
   "deposition mask"). We have stream-power erosion with a settle phase, but
   it operates on already-too-noisy input.

### 2c — Ocean bathymetry: depth by distance from coast

Real ocean floor is **zoned by distance from the coast**, not noise:
continental **shelf** (gentle, shallow) → **shelf break** (steep slope) →
continental **rise** → **abyssal plain** (deepest, *most level* part of the
ocean). So ocean depth should be a **distance-from-coast → depth curve** with
near-zero variance on the abyssal plain, not a uniform fBm.

---

## 3 — Design for LoreWeave

**Unifying principle:** *amplitude of meso/micro detail = f(ruggedness)*, where
ruggedness is high near mountains / plate belts / steep slopes and ≈0 on
cratonic plains and abyssal floor. This is Musgrave's statistics-by-altitude,
driven by our **tectonic macro** (which we already compute well) instead of
pure-noise feedback — cleaner and art-directable, like World Machine's masks.

### 3a — A continuous `ruggedness` field `r[cell] ∈ [0,1]` (NEW, in `plates.rs` or `terrain.rs`)

Derived from data we already have:
- **Orogeny proximity** — `plates.uplift` already encodes distance-decayed
  boundary belts; its magnitude is a primary ruggedness source (mountains,
  arcs, rifts are rugged).
- **Macro altitude above the platform** — higher continental macro elevation
  ⇒ more rugged (statistics-by-altitude).
- **A low-frequency fBm** (1–2 octaves) for organic large-scale variation so
  ruggedness isn't a clean function of the above (some plains near mountains,
  some rugged plateaus).
- Combine, smoothstep, clamp to `[0,1]`. **Cratonic interiors + abyssal floor
  → r ≈ 0.**

### 3b — Gate the detail by `r` (rework `terrain::tectonic_relief`)

```
platform (flat base)                                  // unchanged
+ orogeny uplift                                      // unchanged (macro belts)
+ r * ( hills(mid-freq) + ridged(high-freq) )         // ← gated detail
+ (1-r) * tiny_low_freq_undulation                    // plains: near-flat, gentle
```
- `r ≈ 0` (plains/craton) → detail vanishes → **macro-flat plains** (just the
  platform + a whisper of low-freq undulation).
- `r ≈ 1` (mountains/belts) → full hills + ridged ranges → **jagged peaks**.
- **Octave-by-ruggedness** (Musgrave 2b/§2a + the "ocean 1–2 oct, mountains
  5–7 oct" guidance): scale octave count / lacunarity contribution by `r` so
  flat regions get only low octaves. Simplest: amplitude-gate as above; richer:
  also fade in higher octaves with `r`.

### 3c — Ocean depth curve (rework the oceanic path)

Replace the uniform abyssal fBm with a **distance-from-coast → depth** model:
- Compute `coast_dist[cell]` for ocean cells via multi-source BFS from coast
  cells (we already identify coast/ocean in `hydrology` / `feature`).
- Map `coast_dist` through a depth curve: **shelf** (0–small dist: shallow,
  gentle ramp) → **slope** (steep) → **abyssal** (far: deep, *flat*, variance
  ≈ 0). Mid-ocean ridges stay as the existing `Ridge`-boundary uplift.
- Net: oceans read as shelf+abyssal, not lumpy noise.

### 3d — Erosion (keep, re-sequence)

Stream-power erosion (`erosion.rs`) already carves valleys + deposits in the
settle phase. With the gated relief feeding it (mountains rugged, plains flat),
its deposition will *reinforce* flat valley floors / plains rather than fight a
noisy input. No rewrite needed; verify it helps post-gating.

### 3e — Domain-warp masked by `r` (minor, §2b/L3)

Scale `warp_point` amplitude by `r` so warping (which adds turbulence) is
strong in mountains and weak on plains — keeps coastlines/plains coherent.

---

## 4 — Implementation steps

| Step | File | Change |
|---|---|---|
| S1 | `plates.rs` | Expose an orogeny-proximity / belt-distance signal usable for ruggedness (the `uplift` BFS already has hop-distance; surface a normalized `belt_proximity[cell]`). |
| S2 | `terrain.rs` | NEW `ruggedness(cell)` = combine belt-proximity + macro-altitude + low-freq fBm → `[0,1]`. |
| S3 | `terrain.rs` | Rework `tectonic_relief`: gate hills + ridged by `r`; plains get only low-freq whisper. Octave fade by `r` (optional richer pass). |
| S4 | `terrain.rs` / `hydrology.rs` | Ocean depth curve from coast-distance BFS (replaces uniform abyssal fBm). |
| S5 | `terrain.rs` | Mask `warp_point` amplitude by `r`. |
| S6 | tests + analysis | Re-run the elevation histogram + a NEW **flatness metric** (see §5); visual smoke. |

`content_hash` rebases (terrain algorithm change) — expected, documented.

---

## 5 — Verification (systematic, like last session)

Don't eyeball — measure. Targets:
1. **Hypsometric distribution** stays Earth-like (≈60% lowland, tail to peaks).
2. **NEW flatness metric:** for "plains" cells (low `r`), the local
   elevation variance (vs neighbours) must be **near zero** (macro-flat);
   for "mountain" cells (high `r`), variance high. Print mean local-slope by
   ruggedness band — plains band should be ~flat, mountain band rugged.
3. **Ocean:** abyssal cells (far from coast) have near-zero variance; shelf
   cells ramp gently. Print depth vs coast-distance.
4. **Visual smoke:** gigaplanet flat + globe — confirm visibly flat plains,
   localized mountain belts, smooth abyssal ocean with shelves.
5. Full test suite green; clippy clean.

---

## 6 — Risks

| Risk | Mitigation |
|---|---|
| Plains *too* flat (look artificial / dead) | keep a low-freq whisper (1 octave, tiny amplitude) on plains; tune by the flatness metric, not by eye. |
| Ruggedness field has hard edges (visible banding) | smoothstep + low-freq fBm blend; the field is continuous. |
| Coast-distance BFS cost at gigaplanet | it's O(N) over the mesh graph (same as the orogeny BFS, ~ms); fine. |
| Over-coupling ruggedness to plate belts (mountains *only* at boundaries) | include the low-freq fBm term so some interior ruggedness/plateaus exist independent of belts. |
| content_hash churn | expected; rebase after the histogram + flatness metrics pass, before baking. |

---

## 7 — Out of scope (later)

- **Phase 3 — Köppen climate / biome colour** (desert/forest/tundra). The
  *colour* diversity still missing vs a real Earth map is climate, not relief;
  do after terrain coherence.
- Rivers as visible features; lakes; full erosion-network realism.
- Two-tier scale (Phase 5); fantasy geo-types (Phase 6).

---

## 8 — Sources (research 2026-05-22)

- Musgrave, *Procedural Fractal Terrains* + `musgrave.c` (HeteroTerrain /
  HybridMultifractal / RidgedMultifractal — statistics-by-altitude).
- World Machine / Gaea / World Creator — macro layout + selector masks +
  hydraulic erosion with deposition masks.
- Ocean-floor bathymetry (NOAA / encyclopedia) — shelf → slope → rise →
  abyssal-plain zonation by distance from coast.
- Hydraulic-erosion references (Job Talle; dandrino/terrain-erosion-3-ways) —
  sediment deposition flattens valley floors / basins.
