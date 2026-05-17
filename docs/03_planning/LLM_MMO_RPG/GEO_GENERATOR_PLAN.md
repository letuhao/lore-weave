# GEO World-Map Generator — Build Plan

> **Purpose:** a **standalone procedural world-map generator** — `generate(seed, CreativeSeed) → WorldMap`. A Rust **library crate + thin CLI**. Decoupled from the LLM MMO RPG engine: **no DP-kernel, no event sourcing, no aggregates, no foundation tier.**
>
> **Why this exists:** the goal is a *map generator*, not the MMO. The `V1_30D_IMPLEMENTATION_PLAN.md` + the foundation program were scoped to the full event-sourced engine — **superseded** for this goal. The GEO design docs remain the *algorithm spec*; the engine machinery around them is dropped (§1).

---

## Phase status board

| Phase | Title | Status |
|---|---|---|
| 0 | Scaffold (re-purpose the Cycle-0 `world-service` crate) | **DONE** (superseded — Phase 1 created `crates/world-gen` fresh; `services/world-service` + `services/travel-service` left orphaned for human cleanup) |
| 1 | Crate structure + core types + Voronoi mesh + heightmap | **DONE** (2026-05-17) |
| 2 | Climate + biomes + rivers | **DONE** (2026-05-17) |
| 3 | Political + settlement + route + culture | **DONE** (2026-05-17) |
| 4 | Serialization + image export + CLI + LLM CreativeSeed authoring | **DONE** (2026-05-17) |

**All 4 phases complete — the GEO world-map generator is built.** Phases were executed under **AMAW** per the project owner's call — the full 12-phase workflow with cold-start sub-agent reviews + `/review-impl` on each phase.

### Phase 1 — build log (2026-05-17)

`crates/world-gen/` — library `world_gen` + CLI bin `world-gen`. 9 source files + 2 integration tests, 19 tests green, `cargo clippy --all-targets` clean. Voronoi dual-mesh (perimeter ring + jittered interior → `delaunator` Delaunay → degree-repaired adjacency); Azgaar blob+radial-falloff heightmap; blake3+ChaCha8 determinism with a `content_hash` gate. AMAW: 3 design-review rounds (r1/r2 REJECTED → r3 APPROVED_WITH_WARNINGS), 2 code-review rounds (r1 REJECTED — land-coherence held on only some seeds → r2 APPROVED_WITH_WARNINGS), `/review-impl` (1 MED + 4 LOW), Scope Guard CLEAR. Phase 4 LLM authoring will use `ibm/granite-4-h-tiny` via LM Studio. One deferred item: `DEFERRED.md` #013 (land-fraction precision → Phase 2). Phase 4's optional LLM authoring is **in scope** for this run.

### Phase 2 — build log (2026-05-17)

Stages 3–4: `climate.rs` (latitude×elevation×ocean-distance → 8 `ClimateZone`), `hydrology.rs` (Barnes priority-flood depression fill → flow accumulation → `river_flux`; ocean/lake water network), `biome.rs` (14-`BiomeKind` matrix). `CreativeSeed` gained `hemisphere_orientation` + `climate_bias`; `WorldMap` gained `climate`/`biome`/`river_flux`/`is_coast`; CLI `--png` now renders biomes. 40 tests green, clippy clean. **DEFERRED #013 cleared** — connectivity-aware sea-level binary search + a continental base dome for the high-land `Inland` profile. AMAW: 2 design rounds (r1 REJECTED 2 BLOCK → r2 APPROVED_WITH_WARNINGS), 2 code rounds (r1/r2 APPROVED_WITH_WARNINGS — a code-review WARN fix surfaced + fixed a real `Inland` land-fragmentation BLOCK), `/review-impl` (1 MED + 3 LOW), Scope Guard CLEAR.

### Phase 3 — build log (2026-05-17)

Stages 5–8 (task size **XL**), pure-procedural: `pathfind.rs` (deterministic integer-cost multi/single-source Dijkstra, BFS, largest-remainder apportionment, union-find), `political.rs` (province terrain-cost flood-fill + nearest-state-seed clustering), `settlement.rs` (burg-score Poisson-disk + role assignment), `routes.rs` (Road MST+augmentation, Trail, SeaLane, MountainPass, RiverNavigation), `culture.rs` (barrier flood-fill). `CreativeSeed` gained `settlement_density` + `culture_count`; `WorldMap` gained `province_of`/`provinces`/`states`/`settlements`/`routes`/`culture_of`/`culture_regions`; CLI gained `--political-png`. 50 tests green, clippy clean. AMAW: 3 design rounds (r1/r2 REJECTED — archipelago multi-component + quota apportionment → r3 APPROVED_WITH_WARNINGS), 2 code rounds (both APPROVED_WITH_WARNINGS), `/review-impl` (1 MED + 3 LOW). A union-find-on-distance state-clustering bug (degenerate to 1 state) was caught at VERIFY by the political-map render and fixed with nearest-state-seed assignment. Scope Guard CLEAR.

### Phase 4 — build log (2026-05-17)

`WorldMap` ⇄ JSON round-trip with `compute_hash`/`verify_hash` (a loaded map is verified, not trusted — a hand-edited JSON fails the check); `render::political_svg` vector export; CLI restructured into `generate` / `author` clap subcommands with `--config` (load a `CreativeSeed` JSON) + `--svg`; `author.rs` — LLM CreativeSeed authoring via a `reqwest::blocking` call to an OpenAI-compatible endpoint with a `json_schema` response constraint, default `ibm/granite-4-h-tiny` at LM Studio. 65 tests + 1 `#[ignore]` LLM integration test (passes against LM Studio), clippy clean. AMAW: 3 design rounds (r1/r2 REJECTED — hash not re-derived after load, hash-move under-specified → r3 APPROVED_WITH_WARNINGS), 2 code rounds (r1 REJECTED — missing acceptance-criteria tests → r2 APPROVED_WITH_WARNINGS), `/review-impl` (3 LOW), Scope Guard CLEAR. The `author`→`generate --config` chain was verified end-to-end: a prose brief produced a schema-valid `CreativeSeed` that generated a valid map.

---

## §1 — Scope: kept vs dropped

**KEPT** — from GEO_001 / GEO_001b / POL_001 / SET_001 / ROUTE_001, the *algorithms and data*:
- The 8-stage generation pipeline (Voronoi → heightmap → climate → biome+rivers → political → settlement → route → culture).
- The closed enums: `ClimateZone` (8), `BiomeKind` (14), `WorldArchetype` (12), `WorldScale` (5), `RouteKind` (5), `SettlementRole`.
- The `CreativeSeed` creative-direction input model.
- The algorithmic baseline: Patel dual-mesh, Azgaar pipeline, O'Leary erosion (§5).

**DROPPED** — the MMO-engine coupling (the reason the foundation program was ever needed):
- The event-sourced `world_geometry` *aggregate* (T2/Channel) → replaced by a plain `WorldMap` value.
- `GeographyDelta` / delta-overlay editing, `geography.*` reject namespace, the validator pipeline, `schema_version`, snapshot-fork / multiverse, RealityManifest coupling, capability claims.
- The `world-service` *network service* framing → a **library crate + CLI** instead.

**The one invariant carried over:** **regeneration-determinism** — `generate(seed, creative_seed)` is a pure function; same inputs → byte-identical `WorldMap`. This is the core CI gate of every phase.

---

## §2 — Architecture

A library crate **`world_gen`** + a thin CLI bin **`world-gen`**. Re-purpose the Cycle-0 `services/world-service/` scaffold; Phase 1 may move it to `crates/world-gen/` (it is a library, not a service — recommended) or keep it in place — a Phase 1 call. *(The Cycle-0 `travel-service` scaffold is unrelated to this generator — leave it or delete it; orthogonal.)*

```
world_gen (lib)
  creative_seed   — the CreativeSeed input model (grows per phase)
  world_map       — the WorldMap output value + Cell + the closed enums
  mesh            — Voronoi dual-mesh partition + adjacency
  terrain         — heightmap · climate · biome · rivers
  political       — provinces · states
  settlement      — burg placement · role assignment
  routes          — road/trail/sealane/mountainpass/river network
  culture         — culture-region spread
  serde           — WorldMap (de)serialization
world-gen (bin)   — CLI: generate a map from a seed + config, dump JSON / image
```

One seeded RNG (`blake3`-derived per the design docs' determinism note) threaded through every stage. `WorldMap` carries a stable content hash for the determinism test.

---

## §3 — The 4 build phases

### Phase 1 — Crate structure + core types + mesh + heightmap
- **Builds:** the `world_gen` lib + `world-gen` CLI skeleton; `CreativeSeed` (geometry-relevant fields) + `WorldMap` + `Cell` + `WorldScale`/`WorldArchetype` enums; **Voronoi dual-mesh** partition (~1k–16k cells per `WorldScale`) + cell adjacency; **heightmap** (u16 elevation, Azgaar-style blob seeds + falloff) + land/sea threshold.
- **Design ref:** GEO_001 §5 stages 1–2.
- **Verify:** determinism (same seed → byte-identical mesh + heightmap); cell count within `WorldScale` bounds; neighbour degree 3–12; the CLI dumps a land/sea image showing a coherent continent.

### Phase 2 — Climate + biomes + rivers
- **Builds:** `ClimateZone` (8) from latitude (hemisphere) × elevation; rainfall → downhill flow accumulation → **rivers**; `BiomeKind` (14) from (climate × heightmap × river_flux) per the GEO_001 §5 derivation matrix.
- **Design ref:** GEO_001 §5 stages 3–4.
- **Verify:** determinism; biome derivation matches the matrix; rivers descend monotonically to sea/lake; no incoherent biome adjacency (GEO_001's HIGH-1 coherence concern); CLI dumps a biome-coloured map.

### Phase 3 — Political + settlement + route + culture
- **Builds:** stage 5 **provinces** (flood-fill from seeds) + **states**; stage 6 **settlements** (burg-score Poisson-disk weighted by habitability + role assignment Hamlet→Capital); stage 7 **routes** (Road via Dijkstra · Trail · SeaLane · MountainPass · RiverNavigation); stage 8 **culture-region** spread. `CreativeSeed` gains its political/culture fields.
- **Design ref:** GEO_002 POL_001 · GEO_003 SET_001 · GEO_004 ROUTE_001 (algorithm sections only).
- **Verify:** determinism; provinces partition the land totally; every state has exactly one capital; one-route-per-pair; roads connect settlements; CLI dumps a full political/road map.

### Phase 4 — Serialization + export + CLI + (optional) LLM authoring
- **Builds:** `WorldMap` ⇄ JSON (round-trip stable); image/SVG export; the full CLI (`world-gen --seed S --config creative_seed.json --out map.json [--png]`); **optional** GEO_001b authoring — `loreweave_llm` turns a prose brief into a schema-valid `CreativeSeed` JSON.
- **Design ref:** GEO_001 §6 (CreativeSeed) · GEO_001b.
- **Verify:** JSON round-trip identity; CLI end-to-end on a fixture seed; (optional) LLM authoring yields a `CreativeSeed` that re-generates a valid map.

---

## §4 — Per-phase workflow

Each phase runs the default 12-phase v2.2 workflow. The non-negotiables per `CLAUDE.md`:
- **Phase 6 VERIFY** — run the determinism test + the structural checks above with fresh evidence.
- **Phase 7 REVIEW** — 2-stage (spec compliance + code quality).
- **`/review-impl`** after BUILD — adversarial pass (the prior arc's discipline).
- **Phase 11 COMMIT** — set the phase `Status=DONE` on the board in the same commit.

Determinism is the load-bearing CI gate: a test that asserts `generate(seed, cfg)` is byte-identical across two runs, for every fixture seed, every phase.

---

## §5 — Algorithm references (all permissively licensed — per the GEO_001 2026-05-13 survey)

- **Patel dual-mesh** (Apache 2.0) — Voronoi/Delaunay mesh; Rust crates: `delaunator` / `spade`.
- **Azgaar Fantasy Map Generator pipeline** (MIT) — the heightmap → climate → biome → burg → route stage structure.
- **O'Leary hydraulic erosion** (MIT) — optional heightmap refinement.
- LLM-image-to-map approaches were **rejected** at design time (no regeneration-stability / adjacency-correctness) — the generator is structured-procedural, not generative-image.

---

## §6 — Relationship to the design track

- The GEO_001 / GEO_001b / POL / SET / ROUTE design docs stay as the **algorithm spec**; their event/aggregate/delta sections are simply not implemented here.
- `V1_30D_IMPLEMENTATION_PLAN.md` + `V1_30D_CYCLE_LOG.md` are **superseded for this goal** — retained only as a record, relevant only if the full event-sourced MMO is ever built.
- If the MMO is later built, this `world_gen` library is reusable as-is — the engine's `world_geometry` aggregate would *wrap* it (call `generate()` for the base, layer deltas on top). Building the standalone generator first is the right order regardless.
