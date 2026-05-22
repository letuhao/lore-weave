# Seam-Features Roadmap (flatworld / zonegen bottom-up track)

> **Status:** BACKLOG / roadmap (2026-05-23). Captures the PO's list of
> **interface ("giao thoa") landforms** so it isn't lost, and sorts each item
> by the foundation it needs before it can be built. These are mostly **seam
> features** (landforms *of a boundary*), distinct from **area classes**
> (zone-interior types: plains/hills/plateau/mountains — already built in B1).
>
> Context: B3 makes intra-plate seams *continuous* (smooth blend). The genuine
> next capability is **typed seams** — letting a boundary be smooth OR sharp OR
> a specific landform, driven by `SeamKind` (Interior / Convergent / Divergent /
> Transform / Coast) from the locked region-tree data architecture
> ([`2026-05-23-flatworld-region-tree-data-architecture.md`](2026-05-23-flatworld-region-tree-data-architecture.md) §5).

---

## Key distinction

- **Area class** = what fills a zone. B3's blend already crossfades these.
  Adding more (desert, tundra, …) is variety/polish, NOT a stronger B3 test.
- **Seam feature** = a landform *at* the boundary between two regions. This is
  the next capability beyond B3's continuity. The list below is almost entirely
  this kind.

The strongest test of seam handling is therefore **typed seams** (some sharp,
some smooth), not more area classes.

---

## The list, sorted by required foundation

### A. Achievable now — pure relief (→ B3b "typed seams")
Need only elevation + boundary type; no water/erosion/climate.

| Feature | What it is | Seam type |
|---|---|---|
| **Escarpment** | sharp cliff/step inland (plateau → plain) | sharp elevation step at a zone/plate seam |
| **Foothills / Piedmont** | gentle rolling ramp from mountains down to plain | graded transition band (mountain→plain) |
| **Pass (đèo)** | saddle low-point between two peaks linking valleys | local minimum along a ridge seam |
| **Coast (cliff vs beach)** | plate edge meets void/sea: steep cliff or shallow beach | `Coast` seam: sharp vs ramped by margin type |

### B. Needs erosion first (→ after B2)
| Feature | Needs |
|---|---|
| **Canyon / Gorge** | a river incising a vertical cut — stream-power **erosion (B2)** |

### C. Needs water (rivers + sea) — hydrology phase
Zones are currently LOCAL with **no water by design**; these wait for a
hydrology layer (river routing + a sea/coast model).
| Feature | Needs |
|---|---|
| **Estuary** | river mouth + tidal brackish mixing |
| **Delta** | river deposition fanning into the sea |
| **Mangrove** | tropical tidal land/sea band (also climate) |
| **Wetland / Marsh / Swamp** | water-saturated low ground beside lake/river/sea |
| **Fjord** | glacial U-valley flooded by deep sea (mountain ⨯ ocean) |

### D. Needs climate / biome — Köppen phase (B5)
| Feature | Needs |
|---|---|
| **Treeline / Timberline** | temperature/altitude ecological boundary |
| **Oasis** | desert ⨯ groundwater ecological boundary |

### E. Special / much later
| Feature | Needs |
|---|---|
| **Cenote / Sinkhole** | karst (limestone) + underground caves/rivers model |

---

## Implementation note for B3b (typed seams)

The blend in B3 (`zonegen::blended_height`) currently treats every seam the
same (smooth). B3b makes the **blend width / profile depend on `SeamKind`**:
- Interior (same-class siblings) → wide smooth blend (current behaviour).
- Convergent / front / Escarpment → near-zero blend + a crest/step profile.
- Coast → cliff (sharp) or beach (ramp) depending on the margin.

`SeamKind` + `strength` come from the plate-level tectonics (today's
`collision_strength` sign/magnitude) for cross-plate seams, and from a per-seam
flag for intra-plate escarpments. This is exactly the `Adjacency`/`Seam` record
in the data architecture — B3b is where that record starts being consumed.
