# Hierarchy Depth & Diversity — DECISION (locked)

> **Status:** ✅ DECISION LOCKED (PO, 2026-05-23). Settles "how many levels do
> we subdivide, and where does terrain diversity come from?" for the flatworld /
> zonegen bottom-up track. Builds on the locked region-tree data architecture
> ([`2026-05-23-flatworld-region-tree-data-architecture.md`](2026-05-23-flatworld-region-tree-data-architecture.md))
> and the seam-features roadmap ([`2026-05-23-seam-features-roadmap.md`](2026-05-23-seam-features-roadmap.md)).

---

## The question

Current hierarchy: **World → Plate → Zone L1 → Zone L2**, rule "each zone is one
terrain type, sub-zones inherit from the parent." Is 2 zone levels enough for
real-world terrain diversity, or must we subdivide deeper?

## The key insight: two orthogonal axes (don't conflate them)

A common proposal is to add more *cell* levels (Z3 "feature", Z4 "tile") to get
diversity. **That conflates two different axes:**

| Axis | What it is | Example |
|---|---|---|
| **A — Area subdivision** | partition area into smaller cells | World → Plate → Z1 → Z2 → … |
| **B — Seam features** | a landform that lives *on the boundary* between two regions | beach, cliff, estuary, fjord |

A beach/cliff/estuary is a **thin strip along an edge**, not a smaller Voronoi
cell. Modelling transitions as "Z3 cells" is the wrong shape. In our data
architecture they are the **`Adjacency`/`Seam`** layer (§5) — and B3/B3b already
started consuming it (typed seam widths: smooth interior vs sharp escarpment vs
graded foothills).

**Therefore: deeper subdivision does NOT create transitions. The seam layer
does.**

---

## DECISION

1. **Area depth: keep 2 zone levels as the default; do NOT lock a fixed global
   depth.** The region tree is recursive + lazy (file/folder). Depth is
   **per-branch, on demand**: a dull ocean plate stays shallow; a complex
   coastal-mountain region subdivides deeper *only there*. Two levels is the
   right default for macro/meso review; finer area cells are added only where a
   region's detail needs them.

2. **Diversity & "giao thoa" come from THREE sources — not from more cell
   levels:**
   - **Seam-feature layer** (axis B): typed boundaries → coast/cliff/beach,
     escarpment, foothills, estuary, fjord. (`Adjacency`/`Seam`; B3b + roadmap.)
   - **Relief + erosion within each zone**: multi-octave class relief (B1) +
     hydraulic erosion (B2) → valleys, canyons, ridgelines. Intra-zone variation
     means "one class per zone" is *not* a flat single type.
   - **Climate / biome overlay** (Köppen, B5): turns a relief *class* into a
     real *biome* (desert/forest/tundra) — the ecological diversity & colour.

3. **The 6-level proposal maps onto our architecture with two reframes:**

   | Proposed level | Our architecture | Note |
   |---|---|---|
   | World | World root + WorldParams | ✓ |
   | Plate | Plate (depth 0) | ✓ coarse elevation |
   | Biome (Z1) | Zone L1 — currently relief CLASS | becomes biome after B5 (climate) |
   | Landscape (Z2) | Zone L2 | ✓ current level |
   | **Feature (Z3)** | **Seam / Adjacency layer (edge, NOT a cell)** | reframe |
   | **Tile (Z4)** | **`TerrainTile` raster per leaf (display/game)** | reframe — rasterization, not a Voronoi level |

---

## Production-ready roadmap (dependency order)

1. **B2 — local erosion** → valleys, then canyons (with rivers). Reuse
   `erosion::apply`. *(next)*
2. **Seam features (axis B), expand B3b** → coast/beach/cliff at plate edges;
   then estuary/fjord/delta (some need water).
3. **Hydrology — rivers + sea/coast model** → unlocks all water transition
   features (estuary, delta, mangrove, fjord, wetland). *Biggest current gap —
   zones are deliberately water-free today.*
4. **B5 — climate / biome (Köppen)** → relief class → real biome (desert/forest/
   tundra); the ecological + colour diversity. = the proposal's "Biome" level.
5. **`TerrainTile` raster per leaf + LOD / lazy expansion** → the "Tile" level;
   enables zoom-in detail + huge worlds.
6. **Cross-plate seams** (currently sharp) + **persistence** (serialize tree /
   tiles to disk).

---

## One-line lock

> Subdivide to **2 zone levels by default, recursive+lazy deeper per-branch as
> needed**; get terrain diversity from the **seam-feature layer + relief/erosion
> + climate/biome**, NOT from forcing more cell levels. "Feature" = a seam (edge)
> concept; "Tile" = a per-leaf raster — neither is another Voronoi subdivision.
