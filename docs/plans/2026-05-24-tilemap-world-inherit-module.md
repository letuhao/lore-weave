# Plan — tilemap-service `world_inherit` module BUILD

> **Spec:** [`docs/specs/2026-05-24-tilemap-world-inheritance-contract.md`](../specs/2026-05-24-tilemap-world-inheritance-contract.md)
> (ACCEPTED 2026-05-24 — PO sign-off en bloc; §10 migration plan is the seed
> of this PLAN).
> **Size:** L · **Mode:** default v2.2 (human-in-loop) · **Date:** 2026-05-24

## What this plan delivers

The `world_inherit` module + `BiomeBridge` wiring into `biome_select`, so a
tilemap that opts in to world inheritance gets its game-biome choices
constrained by upstream `world-gen` zone biome facts.

**Acceptance (pulled from spec):**

- **AC-WI-1** — `MockFileWorldSource::load_zone(&[2, 1])` against
  `tests/fixtures/world-mock/diverse-biomes.json` returns a
  `WorldZoneSnapshot` with `biome = WorldBiome::Tundra` (zone path `[0, 1]`)
  and tag 1. *(typo guard: this AC references zone `[0, 1]`, the second zone
  of the first plate in diverse-biomes.json; see the fixture.)*
- **AC-WI-2** — All 10 `WorldBiome` variants parse round-trip from
  `diverse-biomes.json`; `minimal.json` parses 6 of 10.
- **AC-WI-3** — `BiomeBridge::validate_pick(WorldBiome::Ice, "hot_desert")`
  returns `Err(BridgeViolation::Disallowed { .. })`.
- **AC-WI-4** — `BiomeBridge::validate_pick(WorldBiome::Tundra, "snow_frost")`
  returns `Ok(())` (assuming the initial table maps Tundra → {snow_frost, ...}).
- **AC-WI-5** — `TilemapTemplate { world_zone: None, .. }` (the existing
  shape) round-trips through serde unchanged; `cargo test --workspace` stays
  green at every chunk boundary.
- **AC-WI-6** — Integration test: load `diverse-biomes.json` → drive
  tilemap generation for a zone whose world biome is `HotDesert` → assert
  the picked game biome appears in the `HotDesert` allow-set.

## Build chunks

Six chunks, dependency-ordered. **TDD**: failing test → implement → `cargo
test --workspace` green before the next. `cargo clippy --workspace
--all-targets -- -D warnings` clean at each boundary.

### Chunk 1 — Module skeleton + types (no logic)

Pure type declarations. No engine touched.

Files:

- `services/tilemap-service/src/world_inherit/mod.rs` (new) — re-exports
- `services/tilemap-service/src/world_inherit/types.rs` (new) —
  `RegionPath`, `WorldZoneSnapshot`, `ZoneClimate`, `WorldBiome` (10
  variants matching upstream `Biome::tag()` 0..9)
- `services/tilemap-service/src/world_inherit/error.rs` (new) —
  `WorldInheritError` (thiserror): `Parse`, `IoLoad`, `UnknownBiomeTag`,
  `MissingZone`
- `services/tilemap-service/src/lib.rs` (mod) — `pub mod world_inherit;`

Tests (in `world_inherit/types.rs` `#[cfg(test)] mod tests`):

- `WorldBiome::from_tag(0..=9)` → `Ok(_)` for valid; `from_tag(10)` → `Err`
- `WorldBiome::tag()` round-trip 0..=9
- `RegionPath` Display formats `[2, 1, 5]` → `/2/1/5`
- `RegionPath` serde JSON round-trip

Pass criteria: types compile, 4 unit tests green, clippy clean.

### Chunk 2 — JSON parser + `MockFileWorldSource`

Wires fixture JSON → typed snapshot.

Files:

- `services/tilemap-service/src/world_inherit/source.rs` (new) —
  `WorldSource` trait + `MockFileWorldSource` impl (caches by file path)
- `services/tilemap-service/src/world_inherit/wire.rs` (new) — serde
  structs mirroring fixture JSON (top-level wrapper + plates/zones/subzones);
  internal `to_snapshot(path: &RegionPath)` projection
- `services/tilemap-service/Cargo.toml` (mod) — keep deps minimal; serde +
  serde_json already in workspace deps

Tests (in `world_inherit/source.rs`):

- **AC-WI-1** — `MockFileWorldSource::new("tests/fixtures/world-mock/diverse-biomes.json").load_zone(&RegionPath(vec![0, 1]))` returns a snapshot with `biome_name == WorldBiome::Tundra`, `biome_tag == 1`
- **AC-WI-2** — Iterate all 10 zones of `diverse-biomes.json`; each parses; the set of `biome_name` values equals all 10 `WorldBiome` variants
- `load_zone(&RegionPath(vec![9, 9]))` (nonexistent) → `Err(WorldInheritError::MissingZone { .. })`
- `MockFileWorldSource::new("/no/such/file.json")` returns construction error or lazy-error on `load_zone` — pick one and pin it; current call: lazy-error on load
- File parse caches: second `load_zone` against same instance does NOT re-open the file (assert via a counter wrapped in a test fixture or via single-open log)

Pass criteria: 5+ unit tests green; both `minimal.json` + `diverse-biomes.json` parse without panic; clippy clean.

### Chunk 3 — `TilemapTemplate.world_zone` additive field

The smallest possible touch to the existing template type.

Files:

- `services/tilemap-service/src/types/template.rs` (mod) —
  ```rust
  pub struct TilemapTemplate {
      // ... existing fields unchanged ...
      #[serde(default)]
      pub world_zone: Option<WorldZoneSnapshot>,
  }
  ```
- `services/tilemap-service/src/types/mod.rs` — re-export `world_inherit::types::WorldZoneSnapshot` if needed for downstream callers

Tests (in `types/template.rs` `#[cfg(test)] mod tests`):

- **AC-WI-5** — existing fixture `tests/golden/tilemap_baseline.json` (which has no `world_zone`) still deserializes → `template.world_zone.is_none()`
- New fixture inline: deserialize a JSON literal that includes a fully-populated `world_zone` → `template.world_zone.is_some()`; field values match
- serde round-trip with `world_zone: None` does NOT emit a `"world_zone": null` line (relies on `skip_serializing_if = Option::is_none` — add the attribute)

Pass criteria: 3 unit tests green; existing `cargo test --workspace` still passes (additive field, default None); golden snapshot test in `tests/determinism.rs` unaffected.

### Chunk 4 — `BiomeBridge` declaration + TOML config

Pure data + loader.

Files:

- `services/tilemap-service/src/world_inherit/biome_bridge.rs` (new) —
  `BiomeBridge` struct, `BridgeViolation` enum, `validate_pick`,
  `allowed_for`, `from_toml_str` loader
- `services/tilemap-service/config/biome_bridge.toml` (new) — naive initial
  table mapping each `WorldBiome` to a non-empty set of placeholder game
  biome ids (these will be refined as `biome_library.rs` evolves; current
  ids should overlap with whatever the live library exposes — verify in
  Chunk 5)
- `services/tilemap-service/Cargo.toml` (mod) — add `toml = "0.8"` if not
  already in workspace deps (most likely needs adding)

TOML shape (illustrative; final table is config tuning):

```toml
# config/biome_bridge.toml
schema_version = "biome-bridge.v1"

[allow]
ice                  = ["glacier", "frozen_waste", "ice_field"]
tundra               = ["snow_frost", "taiga_edge", "permafrost_steppe"]
boreal_forest        = ["taiga_dense", "pine_forest", "boreal_marsh"]
temperate_forest     = ["temperate_woodland", "oak_grove", "mossy_dell"]
temperate_grassland  = ["grassland_temperate", "windswept_plain"]
hot_desert           = ["dune_sea", "red_canyon", "salt_flats"]
savanna              = ["dry_savanna", "acacia_scrub"]
tropical_rainforest  = ["jungle_dense", "mangrove_delta", "humid_canopy"]
deciduous_forest     = ["oak_grove", "autumn_woodland", "temperate_marsh"]
mediterranean        = ["olive_grove", "chaparral", "coastal_pine"]

# Special: ignores climate; only matched when template carries a `rift` flag
# (modeling reality-warping content). Mechanism deferred to Chunk 5.
[special]
rift_override = ["abyss_chaos_rift"]
```

Tests (in `world_inherit/biome_bridge.rs`):

- **AC-WI-3** — `validate_pick(WorldBiome::Ice, "hot_desert")` →
  `Err(BridgeViolation::Disallowed)`; `.allowed` field contains the Ice
  allow-set
- **AC-WI-4** — `validate_pick(WorldBiome::Tundra, "snow_frost")` →
  `Ok(())` (assuming `snow_frost` in Tundra allow-set per table above)
- `BiomeBridge::from_toml_str` parses the shipped `biome_bridge.toml` →
  `Ok(_)`; every `WorldBiome` variant has a non-empty allow-set
- Unknown world biome key in TOML → parse error
- Empty allow-set for any `WorldBiome` → `BridgeViolation::EmptyAllowSet`
  is reachable (synthesize via in-memory bridge with one biome cleared)

Pass criteria: 5 unit tests green; TOML loader covers happy path + 1 error
path; clippy clean.

### Chunk 5 — Wire bridge into `engine/biome_select.rs`

The first chunk that touches existing engine code. Defense-in-depth:
narrow the candidate pool BEFORE selection, then validate AFTER selection.

Files:

- `services/tilemap-service/src/engine/biome_select.rs` (mod) — accept an
  optional `&BiomeBridge` + `Option<&WorldZoneSnapshot>` in the picker
  signature; when both present, intersect candidates with
  `bridge.allowed_for(snapshot.climate.biome_name)` before picking; after
  picking, call `bridge.validate_pick` (must succeed by construction —
  defensive assert)
- `services/tilemap-service/src/engine/mod.rs` (mod) — thread the bridge +
  snapshot through to the picker call site; default to `None` for both
  preserves the existing path
- `services/tilemap-service/src/engine/pipeline/` — possibly 1 file change
  to thread the bridge through the pipeline context; identify the smallest
  cut at READ time (don't pre-emptively refactor)

**Important — survival of existing tests:**

- Existing `engine/biome_select.rs` callers that pass `None` / `None` see
  no behavior change → all 332 existing tests stay green
- If a test explicitly opts in (Chunk 6's integration test), behavior
  changes only there

Tests:

- Unit test in `biome_select.rs`: with bridge + snapshot where
  `world_biome = HotDesert`, picker MUST return a game biome from the
  HotDesert allow-set even if a hotter-scoring candidate exists outside
- Unit test: with `world_biome = HotDesert` and ALL biome_library entries
  filtered out (i.e. config table doesn't overlap library), picker returns
  `Err(Placement)` with a clear message; this is the failure mode users
  see when the bridge table and the library drift apart
- Existing `engine/biome_select.rs` tests stay green (defense-in-depth
  validate_pick adds zero overhead in the `None` path)

Pass criteria: existing 332-test baseline holds; 2+ new bridge-aware unit
tests green; clippy clean.

### Chunk 6 — Integration test (end-to-end mock → tilemap)

Closes **AC-WI-6**. Lives in `tests/` (integration test, not unit), so
it goes through the full template → pipeline path.

Files:

- `services/tilemap-service/tests/world_inherit_integration.rs` (new) —
  - Load `tests/fixtures/world-mock/diverse-biomes.json`
  - Extract the zone whose `biome_name = HotDesert` (path `[3, 1]`)
  - Build a `TilemapTemplate` with that `WorldZoneSnapshot` injected
  - Build a `BiomeBridge` from `config/biome_bridge.toml`
  - Run the existing tilemap generation pipeline with bridge + snapshot
  - Assert: the resulting `TilemapView`'s zones use game biomes ONLY from
    the HotDesert allow-set
  - Repeat for `Ice` (path `[0, 0]`), `TropicalRainforest` (path `[4, 1]`),
    and `Mediterranean` (path `[3, 0]`) — covers low/mid/high climate
    extremes

Pass criteria: integration test green; `cargo test --workspace` green;
`cargo clippy --workspace --all-targets -- -D warnings` clean.

## Test count delta

- Chunk 1: +4 unit (types)
- Chunk 2: +5 unit (source)
- Chunk 3: +3 unit (template additive)
- Chunk 4: +5 unit (bridge)
- Chunk 5: +2 unit (bridge wiring)
- Chunk 6: +4 integration (one per world biome variant tested)

Total: ~23 new tests. Existing 332-test baseline stays green throughout.

## Deferred (NOT in this BUILD)

- `HttpWorldSource` — spec §8 Phase 2; deferred until post-merge into main
  branch + docker-compose wiring
- Snapshot provenance hash (spec §7 optional lever) — deferred until a
  drift-detection use case appears
- L3 prompt augmentation with world biome context (spec §9 open question 6)
  — deferred until L3 retry-loop work resumes
- Multi-zone tilemaps (spec §11 open question) — deferred until concrete
  use case (e.g. city straddling biomes)
- Adjacency / seam consumption (spec §9 open question 3) — deferred jointly
  with upstream lifting it from "locked design" to "shipped"

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Bridge table drifts from biome_library.rs (some Tundra game biome doesn't exist) | Chunk 5 second unit test asserts the failure mode is clear; manual cross-check during Chunk 4 vs current biome_library.rs entries |
| Existing 332 tests fail because of additive field deser quirk | Chunk 3 adds `#[serde(default, skip_serializing_if = "Option::is_none")]`; golden snapshot stays byte-identical |
| Chunk 5 wiring touches more pipeline files than expected | Re-classify task XL if files >10; chunk gets paused for re-PLAN |
| TOML loader misses the `[special]` section | Defer `rift_override` parsing to a later chunk; ship Chunk 4 with `[allow]` only |

## Phase progression

| Phase | Status | Evidence target |
|---|---|---|
| CLARIFY | ✅ | spec ACCEPTED 2026-05-24 |
| DESIGN | ✅ | spec §1-§13 |
| REVIEW-DESIGN | ✅ | PO "approve" 2026-05-24 |
| PLAN | (this file) | acceptance criteria + 6 chunks + test count |
| BUILD | next | 6 chunks, TDD, each green before next |
| VERIFY | next | `cargo test --workspace` + `cargo clippy --workspace --all-targets -- -D warnings` |
| REVIEW-CODE | next | self-review pass — spec compliance + code quality + 2-stage |
| QC | next | acceptance criteria check |
| POST-REVIEW | next | present to PO; await ack |
| SESSION | next | SESSION_HANDOFF update |
| COMMIT | next | single commit, stage only changed files |
| RETRO | next | non-obvious lessons → spec §11 if any open question gets resolved |
