# world-gen config examples

`CreativeSeed` is the single **centralized profile** for a generated world — every
tunable, from plate tectonics to climate to biome cost tables to render colours,
lives in one JSON object that a human *or* an LLM can edit.

## Get a template

`dump-config` emits the full default profile (every field at its byte-identical
default):

```sh
world-gen dump-config --out creative_seed.json   # or omit --out for stdout
```

Every field is `#[serde(default)]`, so a config may set **only** the fields it
cares about and omit the rest — they fall back to the byte-identical defaults.
That's why the example below is short.

## Use a config

```sh
world-gen generate --seed 7 --config creative_seed.json --out map.json
```

A config with all defaults reproduces the exact same `content_hash` as a bare
`generate --seed 7` — parameterization changes the *surface*, not the *output*.

## Three tiers of control

1. **High-level enums** — `world_scale`, `erosion`, `settlement_density`, … (the
   coarse creative direction).
2. **Macro intensity knobs** (`intensity.*`, default `1.0` = no-op) — scale whole
   groups of granular params at once. Also exposed as `generate` flags
   (`--orogeny`, `--warmth`, `--rainfall`, …).
3. **Granular per-stage params** (`tectonics`, `relief_params`, `climate_params`,
   `erosion_params`, `hydrology_params`, `settlement_params`, `route_params`,
   `political_params`, `culture_params`, `hierarchy_params`, `biome_params`) — the
   exact tuning behind each generation stage. Config-file only. Plus
   `render_theme` — the PNG/SVG/glB colour palettes, hypsometric ramps and
   supersample (cosmetic; not part of `content_hash`).

Every value is **clamped at use**, so a human typo or an LLM hallucination is
bounded — generation never panics.

## Example: `cold-rugged-archipelago.json`

A cold, jagged, fractured world: many small plates (`plate_count: 12`,
`continental_fraction: 0.3`) spread pole-to-pole (`continent_latitude_spread:
1.0`), strong mountain-building and relief (`orogeny`/`relief`/`collision_frequency`
> 1), deep oceans, heavy erosion carving the ranges, and a cold, fairly dry,
strongly-seasonal climate (`warmth: 0.7`, `seasonality: 1.4`).

```sh
world-gen generate --seed 7 \
  --config crates/world-gen/examples/cold-rugged-archipelago.json \
  --out cold.json --relief-png cold.png
```
