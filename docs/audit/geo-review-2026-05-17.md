# GEO World-Map Generator — Human-in-Loop Review (2026-05-17)

A post-build review of the `crates/world-gen/` crate (the 4 GEO phases built
by the prior autonomous AMAW run). Conducted as a **default v2.2 human-in-loop
review** — the project owner at four checkpoints, not autonomous sub-agents.

**Scope chosen:** code + generated-map quality + design fidelity.
**Disposition chosen:** fix every finding, re-verify, commit (local only).

## Stages

| Stage | What | Checkpoint |
|---|---|---|
| 1 | Map quality — 16-config sample matrix, visual inspection | A — approved |
| 2 | Design/algorithm fidelity vs GEO_001–004 + GEO_001b | B — approved |
| 3 | Whole-crate adversarial code review (`/review-impl`) | C — approved |
| 4 | Apply all fixes, re-verify, commit | D — POST-REVIEW |

## Findings

Severity at time of triage. All were fixed in Stage 4 unless marked otherwise.

| ID | Finding | Sev |
|---|---|---|
| A1 | `SeaLane` never generated (0/16 maps); archipelago islands mutually unreachable | HIGH |
| A2 | `MountainPass` barely generated (2 routes, 1/16 maps) | MED |
| A3 | Routes rendered as straight lines — `Route` stored no path | MED |
| A4 | Heightmap looked artificial — concentric blob banding | LOW |
| A5 | No culture-region renderer — culture layer un-inspectable | LOW |
| B1 | SeaLane root cause (refined by C1) | HIGH |
| B2 | MountainPass is a spec violation vs GEO_004 §5.2 | MED |
| B3 | `vertex_polygon` deferred "to Phase 4", never delivered | MED |
| B4 | State clustering used raw Euclidean distance, not TerrainCost (GEO_002 §5.1) | LOW |
| B5 | `world_archetype` is dead input (by design — GEO_001 GEO-D7 defers to V2) | LOW |
| B6 | Heightmap: no erosion pass (GEO_001 §5 stage 2 names Perlin + thermal erosion) | LOW |
| B7 | Per-phase plans diverged from GEO_001–004 without amendment | LOW |
| C1 | SeaLane candidate set (`City && is_coast`) structurally near-unfirable | HIGH |
| C2 | MountainPass Road-path-scan proxy structurally near-unfirable | MED |
| C3 | `compute_hash` field-completeness unguarded; comment misstated the safety net | MED |
| C4 | No test asserted non-Road route kinds are produced | MED |
| C5 | Small scale × Sparse density → `target = 0` settlements | LOW |
| C6 | `State.capital_province` doc comment stale | LOW |
| C7 | Cross-process determinism untested | LOW |
| C8 | Capital/settlement tests covered only the default `CreativeSeed` | LOW |
| C9 | Redundant `placed.contains(&c)` check in settlement placement | COSMETIC |

## Resolution (Stage 4)

**Stage 4a — route network** (commit `b4025bee`)
- **SeaLane** reworked from GEO_004's pairwise coastal-City scheme (which
  cannot connect an archipelago — see C1) to a **per-component-port minimum
  spanning tree**: every inhabited landmass gets a coastal port; a Kruskal MST
  over `{Ocean, Coast}` BFS distances bridges them all. A 5-island archipelago
  now gets a 4-edge SeaLane MST.
- **MountainPass** reworked from the Road-path-scan proxy to GEO_004 §5.2
  spec-faithful **edge-betweenness** over settlement-pair shortest paths;
  top-5 Mountain/Hill chokepoint edges.
- **Route paths**: `Route` now stores the cell `path`; PNG/SVG render routes
  along terrain. `pathfind::bfs_reachable` → `bfs_path`.

**Stage 4b — visual fidelity** (commit `9b718902`)
- **`vertex_polygon`**: `Cell` carries its Voronoi polygon (circumcentres of
  incident Delaunay triangles, angle-ordered). The political SVG renders true
  cell `<polygon>`s.
- **Heightmap erosion**: value noise + 3 neighbour-averaging passes break the
  concentric blob banding.
- **Culture renderer**: `render::culture_image` + a `--culture-png` CLI flag.

**Stage 4c–e — fidelity, coverage, docs** (commit `<this commit>`)
- B4: state clustering now uses `multi_source_assign` over TerrainCost.
- B5: `world_archetype` documented as intentionally inert (CLI + code).
- C3: `tests/serde.rs::compute_hash_covers_every_field` tampers each field;
  the misleading comment in `compute_hash` corrected.
- C4: `tests/structure.rs::route_kinds_are_generated`.
- C5: settlement `target` floored at 3.
- C6: `State.capital_province` comment corrected.
- C7: `tests/determinism.rs::cli_is_deterministic_across_processes`.
- C8: capital/settlement tests swept across profiles and densities.
- C9: redundant check removed.
- B7: this document.

## Doc reconciliation (B7)

Divergences between the GEO design docs and the as-built standalone generator.
Most pre-date this review; the GEO_GENERATOR_PLAN §1 already sanctions dropping
the MMO-engine coupling. Recorded here rather than rewriting the large design
docs inline.

| GEO doc says | Code does | Resolution |
|---|---|---|
| GEO_001 §5 stage 2 — Perlin noise + thermal erosion | Azgaar blob seeds + a smoothing erosion pass | Plan substitution; code now has *an* erosion pass (B6). Accept; doc stale. |
| GEO_001 §3 — `river_threshold` default `1000.0` | Self-tuning 96th-percentile of land flux | Plan-sanctioned; the percentile is map-size-robust. Accept; doc stale. |
| GEO_001 §4.2 — per-biome climate hints (Mountain=Highland only; Plain incl. Subtropical/Arid; Hill=Temperate/Mediterranean) | Uniform elevation-tier rule (`high→Mountain`, `mid→Hill`) for all climates | Defensible generalization; the §4.2 comments are descriptive, the function is the contract. Accept; doc stale. |
| GEO_002 §5.1 step 7 — state assignment by TerrainCost path | **Fixed in B4** — now uses TerrainCost | Reconciled. |
| GEO_002 — `state_id: Option` (frontier/stateless provinces) | `Province.state` non-optional; every province assigned | Plan-sanctioned scope reduction. Accept; deferred concept. |
| GEO_004 §5.2 phase 4 — SeaLane = pairwise coastal-City | Per-component-port MST | **Deliberate review deviation** — GEO_004's scheme provably cannot connect an archipelago. The MST does. GEO_004 §5.2 phase 4 + ROUTE-V12 are superseded for this generator. |
| GEO_004 §5.2 phase 5 — MountainPass = settlement-pair edge-betweenness | **Fixed in B2/C2** — now edge-betweenness | Reconciled. |
| GEO_004 §3 — `Route` has `default_fiction_duration`, `seed_source`, `id`, `is_bidirectional` | `Route` has `kind/from/to/distance/path` | Travel-fiction + provenance fields are MMO-engine coupling, dropped per GEO_GENERATOR_PLAN §1. Accept. |
| Phase-3 plan §4 — state clustering by union-find | nearest-state-seed (now TerrainCost) | Plan doc stale since the P3 build; superseded — see Stage 4a/4c. |

## Verification

- `cargo test -p world-gen` — **68 passed, 1 ignored** (the ignored test is the
  live-LM-Studio LLM authoring integration test).
- `cargo clippy --all-targets -- -D warnings` — clean.
- Determinism: in-process (`determinism.rs`) and cross-process
  (`cli_is_deterministic_across_processes`) both green.
- Visual: 16-config sample matrix regenerated and inspected at every checkpoint.

## Decisions recorded

- `services/world-service` + `services/travel-service` (orphaned Cycle-0
  stubs) — **left in place** at the owner's call; out of scope for this review.
- All review commits are **local-only** on `geo-generator-amaw` per the
  standing no-push constraint.
