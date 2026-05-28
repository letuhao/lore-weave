# Plan — GEO enhancement: feature naming (LLM)

**Date:** 2026-05-17 · **Task size:** XL (new modules, WorldMap schema change,
`content_hash` carve-out, LLM step, CLI subcommand, SVG labels) ·
**Branch:** geo-generator-amaw · **Mode:** default v2.2.

## Problem

Every feature in a `WorldMap` is anonymous — settlements, provinces, states,
cultures carry ids and cells, no names. And mountain ranges / rivers / seas are
not even discrete entities — only per-cell biome fields. The world is a
heightmap with no places.

## Design — two stages

### Stage 1 — feature extraction (deterministic; joins `generate`)

New `feature.rs`. After biomes, flood-fill the biome field into discrete
entities (index-ordered DFS over the neighbour graph — deterministic, the same
pattern as `terrain::land_components`):

- **Mountain ranges** — connected components of `Mountain`-biome cells.
- **Rivers** — connected components of `River`-biome cells (one connected
  system = one river).
- **Water bodies** — connected components of `Ocean` cells (`Sea`) and `Lake`
  cells (`Lake`).

`WorldMap` gains `mountain_ranges: Vec<MountainRange>`, `rivers: Vec<River>`,
`water_bodies: Vec<WaterBody>`. Each entity: `{ id, cells, name }` (water bodies
also a `WaterBodyKind`). The geometry (`id`, `cells`, `kind`) is deterministic
→ **into `content_hash`**.

### Stage 2 — LLM naming (non-deterministic; separate post-`generate` step)

- `Settlement` / `Province` / `State` / `CultureRegion` + the 3 new entity
  types gain `name: String` (`#[serde(default)]`, empty = unnamed). They lose
  `Copy` (a `String` field) — the ripple `Route` already absorbed.
- New `naming.rs` — `name_world(&mut WorldMap, archetype, llm_url, model)`: one
  json-schema-constrained LLM call (counts in, name lists out), names applied
  by `zip` (LLM short → leftover entities stay unnamed; long → truncated).
- The shared HTTP/extract logic is factored out of `author.rs` into
  `author::llm_json_request` — used by both `request_creative_seed` and naming.
- New CLI subcommand `name --in map.json --out named.json --archetype …
  [--svg labelled.svg]`.

## Determinism

`generate()` stays pure → unnamed map; `content_hash` covers the geometry
**including the new extracted entities** and **excluding every `name` field**.
`compute_hash` doc + the `compute_hash_covers_every_field` test get a
documented names carve-out, plus a positive assertion: tampering a `name`
leaves `verify_hash` true. A named map verifies the *same* hash as the unnamed
one (the geometry is untouched).

## Files

- **NEW** `feature.rs` (extraction), `naming.rs` (LLM naming).
- `world_map.rs` — new structs + `WorldMap` fields + `name` fields +
  `compute_hash`.
- `lib.rs` — extraction stage in `generate`, module decls, re-exports.
- `author.rs` — extract the shared `llm_json_request` helper.
- `main.rs` — `name` subcommand.
- `render.rs` — `political_svg` `<text>` labels (settlements, states, ranges,
  rivers, water bodies; XML-escaped).
- `political.rs` / `settlement.rs` / `culture.rs` — add `name: String::new()`
  to the struct literals.
- tests — extraction (`feature.rs`), hash carve-out (`tests/serde.rs`).

## Verification

- `feature` extraction: components are deterministic, partition their biome
  cells, ids are contiguous.
- Determinism: `generate` byte-identical across runs; the extracted entities
  are in the hash; a `name` tamper does **not** fail `verify_hash`.
- `tests/serde.rs` round-trip with the new fields; existing structure suite
  green; `cargo clippy` clean.
- `name` CLI subcommand end-to-end against LM Studio (the `#[ignore]`
  integration-test tier).

## Out of scope

- **PNG text labels** — need glyph rasterisation (a font dependency); SVG
  labels only for now.
- **Per-feature naming context** — the LLM gets counts + archetype, not each
  feature's biome/role/size. Richer context is a later refinement.
