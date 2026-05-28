# world-mock — upstream `world-gen` fixture data

Mock JSON files that pretend to be output from the sibling `lore-weave-game/world-gen` crate. Tilemap-service consumes these during development before the two services are wired through docker-compose (post-merge).

See [`docs/specs/2026-05-24-tilemap-world-inheritance-contract.md`](../../../../../docs/specs/2026-05-24-tilemap-world-inheritance-contract.md) for the full 2-layer architecture context.

## Files

| File | Purpose | Plates × Zones × Subzones | Biomes covered |
|---|---|---|---|
| `minimal.json` | Smallest viable fixture for unit tests. Deterministic, easy to eyeball. | 3 × 2 × 1 (6 zones total) | tundra, boreal_forest, temperate_forest, temperate_grassland, hot_desert, savanna |
| `diverse-biomes.json` | Biome-bridge exercise fixture. Every Whittaker biome appears exactly once. | 5 × 2 × 1 (10 zones total) | All 10 (tags 0-9): ice, tundra, boreal_forest, temperate_forest, temperate_grassland, hot_desert, savanna, tropical_rainforest, deciduous_forest, mediterranean |

## Schema

Top-level wrapper, then upstream-shaped `WorldData`:

```jsonc
{
  "schema_version": "world-gen.v1+climate.v1+polygon.v1",  // see versioning below
  "schema_note": "...",
  "generator": "mock@2026-05-24",                          // who produced this
  "world": {        // §11.2 scalar fields lifted into a sub-object for clarity
    "width", "height", "seed", "plate_count",
    "base_level", "void_level", "collision_gain"
  },
  "plates": [
    {
      "path": [plate_id],
      "center", "velocity",
      "boundary": [[x, y], ...],            // CCW polygon, world px
      "zones": [
        {
          "path": [plate_id, zone_id],
          "site": [x, y],
          "base_elevation": f32,
          "boundary": [[x, y], ...],        // §11.5 lever, see below
          "climate": {                       // §11.5 lever, see below
            "temp_mean": f32,                //   °C
            "precip_annual": f32,            //   mm/yr
            "biome_tag": u8,                 //   0..9 per Biome::tag()
            "biome_name": "snake_case_name"  //   wire-friendly
          },
          "subzones": [
            { "path": [...,...], "site": [x, y] }
          ]
        }
      ]
    }
  ]
}
```

## SSOT fields vs levers (what upstream guarantees vs what we extend)

**Promised by `world-gen` §11.2 today (SSOT — don't reshape):**

- `world.{width, height, seed, plate_count, base_level, void_level, collision_gain}`
- `plates[].{path, center, velocity, boundary}`
- `plates[].zones[].{path, site, base_elevation}`
- `plates[].zones[].subzones[].{path, site}`

**§11.5 levers — `world-gen` lists them as additive future work; we pre-emptively include them because tilemap NEEDS them now:**

- `plates[].zones[].climate.{temp_mean, precip_annual, biome_tag, biome_name}` — required for biome bridge; without it tilemap can't validate "no hot_desert in glacier zone" rule
- `plates[].zones[].boundary` — required to know where each zone sits spatially, so a tilemap can declare which world-zone it inhabits

When `world-gen` extends `ZoneData` to ship these, the mock schema converges (no breaking change expected — fields are additive). If upstream chooses different field names (e.g. `temperature` instead of `temp_mean`), we adapt our parser, not the upstream contract.

**Wrapper fields we add (NOT in upstream contract, mock convenience only):**

- `schema_version` — string the parser checks; reject unknown major versions
- `schema_note`, `generator` — provenance for debugging

These get stripped when wire mode (HTTP) replaces JSON.

## Biome tags (canonical from upstream `Biome::tag()`)

| Tag | Variant | snake_case wire name |
|----:|---|---|
| 0 | `Ice` | `ice` |
| 1 | `Tundra` | `tundra` |
| 2 | `BorealForest` | `boreal_forest` |
| 3 | `TemperateForest` | `temperate_forest` |
| 4 | `TemperateGrassland` | `temperate_grassland` |
| 5 | `HotDesert` | `hot_desert` |
| 6 | `Savanna` | `savanna` |
| 7 | `TropicalRainforest` | `tropical_rainforest` |
| 8 | `DeciduousForest` | `deciduous_forest` |
| 9 | `Mediterranean` | `mediterranean` |

Tags 0-7 are pinned across upstream versions (preserved through v2.1f biome expansion); safe to use as wire bytes. Tags 8-9 were added in v2.1f and may shift if upstream re-tags — bias toward `biome_name` when possible.

## Units & frames

- Coordinates: world pixels in the same frame as upstream render PNGs. Top-left origin, `+x` right, `+y` down.
- Elevations: dimensionless `[0, ~1.0]`. `BASE_LEVEL = 0.35` = land floor, `VOID_LEVEL = 0.0` = ocean/void.
- Polygon winding: CCW in image coords (i.e. `[TL, TR, BR, BL]` rect order). Matches upstream `Plate::contains` convention.
- Temperature: °C, mean annual.
- Precipitation: mm/year, total annual.

## Versioning

`schema_version` is the parser key. Format `world-gen.v{N}+climate.v{N}+polygon.v{N}`:

- `world-gen.v1` — §11.2 base schema (plates/zones/subzones identity, geometry, elevation)
- `climate.v1` — §11.5 climate lever (`temp_mean`, `precip_annual`, `biome_tag`, `biome_name`)
- `polygon.v1` — §11.5 zone polygon lever (`zones[].boundary`)

A parser declares which versions it understands. Unknown future versions like `tectonics.v1` (Adjacency / SeamKind from §5 of the locked design) should be ignored gracefully.

## Extending these fixtures

When tilemap needs new world facts (e.g. seam adjacency, regional tags, plate name), follow this order:

1. **First** check if `world-gen` §11.5 already lists the lever as planned — if yes, use the planned field name.
2. Add the field to BOTH `minimal.json` and `diverse-biomes.json`.
3. Bump the relevant `schema_version` component (or add a new one).
4. Update this README's "SSOT vs levers" section.
5. Cross-reference in `docs/specs/2026-05-24-tilemap-world-inheritance-contract.md`.
6. **Open a corresponding lever request upstream** so the production wire format matches.

When the production wire is ready (post-merge into main branch + docker-compose entry), these fixtures stay around as test-only references. Production reads will go through HTTP to `world-gen-service` per the spec doc.
