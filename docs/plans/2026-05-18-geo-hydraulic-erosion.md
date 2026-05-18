# GEO — Hydraulic erosion (Path B v2)

> **Status:** DESIGN → BUILD. Task size **L** (8 files, model change → `content_hash`).
> Default v2.2 workflow, human-in-loop. Plan: this file.
> CLARIFY sign-off (3 PO questions): stream-power incision · full model
> (incision + diffusion + deposition) · `ErosionStrength` knob on `CreativeSeed`.

## 1 — Problem

Path B's `terrain::height_at` builds ridged mountain ranges and an fBm continent,
but the heightmap is *uncarved*: no valleys cut by running water, no drainage
networks. Real terrain is shaped by erosion — rivers incise dendritic valley
networks, hillslopes creep toward smoothness, and sediment fans out where steep
channels reach flat ground. This is the realism pass the Path B handoff named.

## 2 — Why stream-power incision (not droplet erosion)

The §5 reference cites "O'Leary hydraulic erosion" — a *droplet* algorithm
designed for **regular grids** (bilinear gradient sampling, random droplet
spawns). Our terrain is an **irregular Voronoi mesh** (`neighbors` adjacency
graph). Droplet erosion adapts poorly to a mesh and tends to produce local
gullies rather than the large-scale **dendritic drainage networks** the handoff
asks for.

**Stream-power incision** (the landscape-evolution-model / Fastscape lineage) is
mesh-native: it routes flow over the mesh graph, accumulates drainage area, and
incises each cell proportional to `drainage_area^m · slope^n`. It is *the*
algorithm that produces dendritic valley networks, and it reuses the
priority-flood depression-fill machinery already proven deterministic in
`hydrology.rs`. Deposition uses the **Davy & Lague (2009)** unified
stream-power-with-deposition term, which deposits sediment naturally where flow
slows (valley floors, mountain-front fans).

## 3 — Pipeline integration

Erosion runs **inside `terrain::build`**, on the `f32` `elev` field, *after*
`apply_falloff` and *before* u16-normalization:

```
height_at  →  apply_falloff  →  ★ erosion::apply ★  →  normalize→u16  →  choose_sea_level  →  enforce_coherence
```

Rationale for the f32, pre-normalization slot: iterative erosion takes many small
incision steps; on a quantized `u16` field each step would round to zero. The
rest of `terrain::build` is unchanged — erosion is purely a transform of the
`elev` buffer; normalization, sea-level pick, and coherence enforcement re-run on
the eroded field exactly as before.

`content_hash` changes (intentional model change — `Cell.elevation` feeds
`compute_hash`). The determinism invariant holds: erosion is a pure function,
no RNG, fixed mesh iteration order.

**Archipelago is skipped.** That coastline profile's defining invariant is 5
fixed island discs (`apply_falloff`'s `ARCH` mask; the structural-coherence
test asserts *exactly* 5). Incision carving a strait would dissect a disc, so
`terrain::build` calls `erosion::apply` only for non-Archipelago profiles —
consistent with how `enforce_coherence` and `choose_sea_level` already
special-case Archipelago. Erosion shapes coherent landmasses.

## 4 — Algorithm — `erosion::apply`

```rust
pub fn apply(
    elev: &mut [f32],
    neighbors: &[Vec<u32>],
    land_fraction: f32,
    strength: ErosionStrength,
)
```

`ErosionStrength::None` ⇒ immediate return, `elev` untouched (a true no-op).
(`centers` is not needed — the slope term uses the elevation `drop` directly;
cell spacing on the jittered-grid mesh is ~uniform and folds into `K`.)

**Provisional sea level.** Outlets are cells below a provisional waterline =
the `(1 - land_fraction)` percentile of the current `elev` field (mirrors
`terrain::pick_sea_level`). Sea cells are fixed (underwater — never eroded) and
are the priority-flood seeds; every land cell drains to the sea through them.

**Two phases.** Erosion runs `carve_iters` pure-incision passes (cut the
dendritic valley network) followed by `settle_iters` incision+deposition
passes. This separation is load-bearing (VERIFY finding): if deposition is
active *while* the violent first-pass incision runs, the enormous transient
sediment load blankets and re-fills the valleys faster than they are cut.
Carving first, then settling the (now-mild) sediment, lets deposition build
fans without erasing the carving.

**Per iteration** (counts + coefficients from `erosion::params(strength)`):

1. **Priority-flood depression fill** (Barnes 2014) — seed the min-heap with all
   sea cells (closed at push), pop ascending; each land cell, when first
   reached, records `receiver[c]` = the cell it drains into and a *filled*
   elevation `max(elev[c], parent_filled)`. Result: a receiver tree where every
   land cell drains monotonically to the sea, plus `order[]` (pop order). The
   heap key is `f32` ordered by `total_cmp` (no `u16` quantization). The pass
   returns the filled field, which erosion **adopts** — a raw heightmap is
   riddled with local pits, and incising it directly leaves most cells at a
   zero drop; the filled field gives every cell a non-negative drop.
2. **Flow accumulation** — `drainage[c]` = upstream cell count draining through
   `c` (uniform rainfall: each cell contributes `1.0`). Summed in reverse pop
   order, so a cell is complete before its receiver consumes it.
3. **Stream-power incision + transport-capacity deposition** — one
   reverse-pop-order pass. For each land cell `c` with receiver `r`:
   - `drop   = max(0, elev[c] − elev[r])`
   - `area   = drainage[c] / n`  (normalized → erosion is world-scale-invariant)
   - `stream = area^m · drop`  (`m = 0.5`; slope exponent `n = 1`)
   - **erosion** `e = K · stream`, clamped `≤ drop` (elevation never falls below
     the receiver → tree stays monotone, elevations stay `≥ 0`)
   - **deposition** — the channel carries `capacity = Kc · stream` of sediment;
     `settle_rate` of the load above capacity is dropped here:
     `d = settle_rate · max(0, flux − capacity)`, where `flux = sediment_in + e`,
     clamped `≤ flux`. `settle_rate` is `0` in the carve phase ⇒ pure incision.
     Below 1 in the settle phase so a transient over-supply flows on through
     and only a *persistent* low-capacity spot (valley floor, mountain front)
     accumulates a fan.
   - `elev[c] += d − e`
   - sediment is conserved: `sediment_out = flux − d ≥ 0`, added to
     `sediment_in[r]`. Sediment reaching a sea cell leaves the system.
4. **Hillslope diffusion** — thermal/creep smoothing: `elev[c] += D · (mean of
   neighbour elevations − elev[c])`, simultaneous update via a scratch buffer.
   Rounds the sharp ridge crests incision leaves untouched. `D` is kept small —
   a large coefficient erases the cell-scale valleys incision just cut. Sea
   cells excluded.

All passes iterate the mesh in fixed index / pop order with no parallelism and
no RNG → bit-reproducible `f32` output.

### Tuning — `erosion::params(strength)`

Final constants, tuned at VERIFY against the raw heightmap raster + relief PNG.

| Strength | carve | settle | `K` erod. | `Kc` transport | `settle_rate` | `D` diffusion |
|----------|------:|-------:|----------:|---------------:|--------------:|--------------:|
| None     | 0     | 0      | —         | —              | —             | —             |
| Light    | 14    | 6      | 2.0       | 4.0            | 0.15          | 0.010         |
| Moderate | 18    | 8      | 3.0       | 4.0            | 0.18          | 0.012         |
| Heavy    | 22    | 10     | 4.0       | 4.0            | 0.20          | 0.012         |

`None` is the no-op. `Moderate` is the `CreativeSeed` default.

### Determinism / stability notes

- **No RNG, fixed order** — priority-flood pops a unique `(key, cell)` per cell;
  flow/incision/deposition iterate `order`; diffusion iterates cell index.
- **Heap key** — `f32` wrapped in a newtype ordered by `total_cmp` (correct for
  all `f32`; no reliance on positive-float bit monotonicity).
- **Stability** — incision is clamped to the available `drop`, so `elev[c]`
  never crosses its receiver; deposition is clamped `≤ flux`. Output stays
  finite and `≥ 0` (the receiver chain bottoms at a non-eroded sea cell).
- **Degenerate guards** — `apply` returns early for `None` (zero iterations)
  and for `elev.len() < 2`; a profile with zero sea cells (none below the
  provisional waterline) yields no priority-flood seeds → incision is skipped
  and only diffusion runs (bounded, safe).
- **Land coherence** — a channel carved below the final sea level becomes a
  fjord/inlet; in the rare case erosion splits the landmass, the existing
  `enforce_coherence` safety net submerges the smaller component as before.
- **Reused, not shared** — `erosion` has its own priority-flood rather than
  reusing `hydrology::priority_flood`: the latter is `u16`-keyed, runs
  post-climate with climate-weighted rainfall, and seeds from the *final* sea
  level. Erosion's is `f32`, pre-normalization, uniform-rain, provisional-sea
  seeded. Genuinely different instantiations — duplicating ~30 well-understood
  lines beats a generic abstraction threaded across two pipeline stages.

## 5 — `ErosionStrength` knob

New enum in `creative_seed.rs`, consistent with how `PrevailingWind` was added:

```rust
#[derive(…, Serialize, Deserialize, Default)]
pub enum ErosionStrength { None, Light, #[default] Moderate, Heavy }
```

- `CreativeSeed` gains `#[serde(default)] pub erosion: ErosionStrength` — a
  pre-erosion config JSON (no `erosion` field) still loads, defaulting to
  `Moderate`.
- CLI: `--erosion <none|light|moderate|heavy>` on `generate` (new `ErosionArg`
  `ValueEnum` + `From` impl, mirroring `WindArg`).
- LLM author: `erosion` added to `creative_seed_schema()` `required` +
  `properties`, and to the `SYSTEM_PROMPT` field glossary. The
  `schema_enums_match_rust_enums` test is extended to cover it.
- Tuning coefficients (`iterations`/`K`/`G`/`D`) live in `erosion::params` —
  physics tuning stays with the physics code; `creative_seed.rs` only carries
  the serialized enum.

## 6 — Files (8)

| # | File | Change |
|---|------|--------|
| 1 | `crates/world-gen/src/erosion.rs` | **NEW** — `apply`, `params`, priority-flood, flow accumulation, incision+deposition, diffusion |
| 2 | `crates/world-gen/src/terrain.rs` | `build` gains `erosion: ErosionStrength`; calls `erosion::apply` after `apply_falloff` |
| 3 | `crates/world-gen/src/lib.rs` | `pub mod erosion;`; `generate` passes `cs.erosion` to `terrain::build` |
| 4 | `crates/world-gen/src/creative_seed.rs` | `ErosionStrength` enum + `CreativeSeed.erosion` field + default |
| 5 | `crates/world-gen/src/main.rs` | `ErosionArg` `ValueEnum` + `--erosion` flag + `From` impl + wire-up |
| 6 | `crates/world-gen/src/author.rs` | schema `erosion` enum + prompt glossary + `schema_enums` test |
| 7 | `docs/plans/2026-05-18-geo-hydraulic-erosion.md` | this plan |
| 8 | `docs/03_planning/LLM_MMO_RPG/GEO_GENERATOR_PLAN.md` | build-log entry (SESSION phase) |

## 7 — Acceptance criteria

1. `erosion::apply` is **deterministic** — identical inputs → bit-identical
   `elev` (`f32::to_bits` compare).
2. Output is **finite and `≥ 0`** for every cell, every strength, every
   coastline profile.
3. **Valleys are carved** — after erosion, cells on high-drainage paths sit
   lower than the un-eroded field; a carved-channel metric increases.
4. **Hillslope diffusion smooths** — mean local elevation variance (or max
   neighbour slope) decreases vs. an incision-only run.
5. `ErosionStrength::None` is a **true no-op** — `apply` leaves `elev`
   bit-identical to the input.
6. Erosion is **monotone in strength** — total incised volume
   `Σ max(0, before − after)` is non-decreasing across None ≤ Light ≤
   Moderate ≤ Heavy.
7. `generate` stays deterministic and **verifies its own `content_hash`** with
   erosion in the pipeline (existing `generate_is_deterministic` /
   `generated_map_verifies_its_own_hash` stay green).
8. `ErosionStrength` **round-trips** through `CreativeSeed` JSON; a pre-erosion
   config JSON (no `erosion` field) loads, defaulting to `Moderate`.
9. CLI `--erosion` and the LLM author schema expose `erosion`;
   `schema_enums_match_rust_enums` covers it.

Dendritic-network realism is not unit-assertable directly; criterion 3 is the
testable proxy, and VERIFY confirms the dendritic appearance visually on the
relief PNG.

## 8 — Build order

1. `creative_seed.rs` — `ErosionStrength` enum + field (compiles standalone).
2. `erosion.rs` — module: `params`, priority-flood, flow accumulation,
   incision+deposition, diffusion, `apply` + unit tests.
3. `terrain.rs` — thread `ErosionStrength` into `build`, call `erosion::apply`.
4. `lib.rs` — `pub mod erosion;`, pass `cs.erosion`.
5. `main.rs` — `ErosionArg` + `--erosion` + wire-up.
6. `author.rs` — schema + prompt + `schema_enums` test.
7. VERIFY — `cargo test` + `clippy --all-targets`; render relief PNGs at each
   strength, tune `params` constants against the carved-valley appearance.
```
