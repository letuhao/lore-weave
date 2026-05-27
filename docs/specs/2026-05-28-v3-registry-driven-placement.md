# V3 Registry-Driven Placement Engine (ADR)

> **Branch:** `mmo-rpg/zone-map-v3-spec` (CLARIFY/DESIGN only — no code yet)
> **Builds on:** V2 data model ADR [`2026-05-26-data-model-v2-registry-footprint.md`](2026-05-26-data-model-v2-registry-footprint.md) (closed primitives + open tag registry + footprint metadata, merged to main via PR #6 / commit `2279a307`).
> **Status:** ACCEPTED 2026-05-28 — PO locked D1–D7 same session
> **Sizing estimate:** XL implementation (7–8 commits across services/tilemap-service + schema infra + frontend-game golden tests + docs)

## 1. Why this ADR exists

V2 closed the data-model gap (per-book registries + footprint + primitive metadata on the wire), but **the engine still routes placement via the V1 closed `TilemapObjectKind` enum**:

- [`engine/modificators/obstacle_placer.rs`](../../services/tilemap-service/src/engine/modificators/obstacle_placer.rs#L452) hardcodes `kind: TilemapObjectKind::Obstacle`.
- [`engine/modificators/treasure_placer.rs`](../../services/tilemap-service/src/engine/modificators/treasure_placer.rs) dispatches on `TilemapObjectKind::Treasure` vs `TilemapObjectKind::MonsterLair`.
- A new `xianxia:dao-stone` tag in a per-book registry resolves V2 metadata (primitive=`Blocker`, footprint, properties) **but no placer runs for it** — the routing is still tied to V1 enum variants.

V2 deliberately deferred the engine refactor to V3 to keep the V2 PR additive (byte-identical golden output for the default registry). V3 closes the loop: **engine reads `ObjectPrimitive` + properties from the registry and dispatches accordingly**, so per-book tags become first-class without enum migrations.

## 2. Goals & non-goals

**Goals:**
1. Engine routes placement by `ObjectPrimitive`, not by `TilemapObjectKind`.
2. Per-book registries can introduce new tags (e.g. `xianxia:dao-stone`, `xianxia:qi-spring`) and have them placed correctly without any Rust enum changes.
3. Default registry continues to produce **byte-identical** placement output (determinism golden, the V2 invariant).
4. Property-driven behavior: handlers read `spawn_pool`, `resource_yield`, `loot_table_id`, `interaction_kind`, etc. from registry instead of hardcoded kind-to-behavior maps.

**Non-goals (deferred to sibling V3 ADRs):**
- world-gen ↔ zone-map architectural boundary (separate ADR, foundational).
- Per-channel registry selection at HTTP layer (separate ADR — small scope).
- Footprint-honoring frontend rendering (separate ADR — frontend-only).
- Asset pipeline thaw / per-book prop generation (DEFERRED #037, separate ADR).
- New primitives (Slippery, NPC, etc. — V2 promotion roadmap; not V3).

## 3. Decision — primitive-based dispatch

### 3.1 Routing principle

Replace **closed enum match** with **registry-aware dispatch table**:

```rust
// V1/V2 (current):
for placement in &mut placements {
    if placement.kind == TilemapObjectKind::Treasure {
        treasure_placer::place(placement, ctx);
    } else if placement.kind == TilemapObjectKind::MonsterLair {
        spawner_placer::place(placement, ctx);
    } // … 9 hardcoded branches
}

// V3 (proposed):
for placement in &mut placements {
    let def = ctx.registry.resolve_object_tag(&placement.tag)?;
    match def.primitive {
        ObjectPrimitive::Pickup    => pickup_handler::place(placement, &def, ctx),
        ObjectPrimitive::Spawner   => spawner_handler::place(placement, &def, ctx),
        ObjectPrimitive::Blocker   => blocker_handler::place(placement, &def, ctx),
        // … one handler per primitive
    }
}
```

A new `xianxia:dao-stone` tag with `primitive: Blocker` automatically hits `blocker_handler` — no enum change required.

### 3.2 Handler vs Placer split

The existing 5 placer modules (`obstacle`, `treasure`, `road`, `river`, `connections`) split into two groups:

| Module | V3 role | Reason |
|---|---|---|
| `road_placer` | **Stays** as geometric placer | Roads need MST + Dijkstra path-finding over the tile grid; not per-placement |
| `river_placer` | **Stays** as geometric placer | Rivers need hydrology source/sink + carve algorithm |
| `connections_placer` | **Stays** as geometric placer | Inter-zone passage corridors need flood-fill connectivity |
| `obstacle_placer` | **Splits**: geometric "source placement" + `blocker_handler` | Mountain anchors are dual-gated geometric placement; the blocker rendering/behavior is per-tag |
| `treasure_placer` | **Splits**: geometric "score-first/validate-on-demand" core + `pickup_handler` / `spawner_handler` | The scoring algorithm is shared across all per-tile object placement; only the kind-to-primitive routing changes |

**Net result:** ~5 new `*_handler.rs` modules (one per discrete-placement primitive: `pickup`, `container`, `habitable`, `blocker`, `door`, `trigger`, `vehicle`, `spawner`, `producer`, `plant`, `decoration` — minus the ones not yet used) replace the V1-kind branches inside existing placers. Geometric placers (road/river/connections) stay structurally the same.

### 3.3 Property-driven behavior

Every handler reads its primitive's expected properties from the registry:

| Primitive | Required properties | Handler behavior |
|---|---|---|
| `Pickup` | `harvest_yield: HashMap` (optional) | One-shot consume on walk; spawn yield into player inventory |
| `Container` | `loot_table_id`, `interaction_kind` | Persistent state; UI dispatch by `interaction_kind` |
| `Spawner` | `spawn_pool: Vec<String>`, `tick_interval: u32` | Periodic entity gen; respects pool weights |
| `Blocker` | `transparent: bool` (optional) | Static collision; future LOS hook reads `transparent` |
| `Door` | `locked: bool`, `key_id: Option<String>` | Toggleable; lock check on interact |
| `Producer` | `resource_yield: HashMap`, `tick_interval` | Periodic inventory gen into a sink (settlement / player) |
| `Plant` | `growth_capacity`, `harvest_yield`, `spread_chance` | Growth tick; harvest event; future spread tick |
| `Trigger` | `condition: String`, `destination_event: String` | Evaluate condition on walk/proximity; fire event |
| `Vehicle` | `destination_event: String` | Transport mechanic |
| `Decoration` | `readable: bool`, `text: String` (optional) | UI overlay for signs |
| `Habitable` | `interior_template_id: String` | Drill-down to interior scene (CSC_001 dep) |

Engine ignores unknown properties; books may carry extra metadata the engine doesn't read yet. **Forward-compat: the registry is the contract; handlers are the consumer.**

## 4. Migration path — V1 kind → V3 primitive

### 4.1 Determinism preservation (the load-bearing invariant)

The V2 default registry [`services/tilemap-service/registry/default.toml`] declares the V1-equivalent tags (`lw:obstacle.mountain`, `lw:treasure.pile`, etc.) with the V1-equivalent primitives + properties. A V3 placer dispatched by primitive on the default registry MUST produce the same `TilemapView` output that V1 kind-dispatch produced.

**How:** the V1-equivalent properties are explicit in `default.toml` (or are the implicit handler defaults). Scoring + placement order are unchanged — only the dispatch site changes from `match kind` to `match registry.resolve(tag).primitive`. The existing 433-test determinism golden suite (`services/tilemap-service` integration tests) MUST stay green byte-identical with no rebaseline.

### 4.2 V1 enum lifecycle

`TilemapObjectKind` (Rust enum) stays as a **legacy alias** for one V3 cycle:
- `TilemapObjectKind::Obstacle` ↔ `tag = "lw:obstacle.mountain"` (or whichever default the V1 placer originally produced)
- `TilemapObjectPlacement.kind` field remains on the wire (legacy)
- Default registry tags backfill to V1-equivalent kinds via a `legacy_kind` field in `ObjectKindDef`

After V3 ships and any external consumers migrate to reading `placement.tag` + `placement.primitive`, the `TilemapObjectKind` enum can be deprecated (separate cleanup ADR, V3.1).

### 4.3 Per-book new tags

A book registry adds `xianxia:dao-stone` with `primitive: Blocker`, `legacy_kind: Obstacle`, `tag_properties: { transparent: false }`. V3 placer:
1. Resolves tag via `registry.resolve_object_tag("xianxia:dao-stone")`
2. Dispatches to `blocker_handler` (primitive = Blocker)
3. Writes placement with `tag = "xianxia:dao-stone"`, `kind = Obstacle` (legacy), `primitive = Blocker`

Frontend tile inspector already shows V2 fields (tag, primitive, footprint) — no frontend change needed for new tags to display correctly. Sprite resolution at L4 still goes through V2 path.

## 5. Locked decisions (PO approval 2026-05-28)

| # | Decision | PO lock | Implication |
|---|---|---|---|
| **D1** | Handler module organization | **(a) per-primitive modules** — one file per primitive in `engine/modificators/handlers/` | ~11 handler files; build chunk 3.4 creates skeletons |
| **D2** | `Habitable` primitive in V3? | **(b) defer to V3.1** — CSC_001 interior scenes not yet specified | `interior_template_id` stays as wire-shape field; no handler runs; tag inert until CSC_001 ships |
| **D3** | Property type discipline | **(c) generate types from schema** | Schema infra is a load-bearing dependency: `registry-schemas/object-properties.schema.json` + build script generates typed property structs per primitive. Adds new build chunk 3.4b (schema infra) before handler skeletons can be typed-correct |
| **D4** | New primitives in V3? | **(b) no** — keep V2's 11 only | Scope-cap; Slippery/NPC/Animal/etc. remain V2 §2.1.2 promotion roadmap (separate ADRs gated on game-mechanic ship) |
| **D5** | Test strategy for new tags | **(c) both** — fuzz + hand-written | Adds proptest-based registry fuzzer chunk 3.10 (asserts placement invariants over arbitrary valid registries); xianxia hand-written suite stays at chunk 3.7 |
| **D6** | `TilemapObjectKind` legacy lifecycle | **(a) deprecate in V3.1** — 1-cycle alias | V3 keeps `placement.kind` field via default-registry `legacy_kind`; V3.1 cleanup ADR audits external consumers then removes |
| **D7** | Tick scheduler scope | **(a) V3 writes metadata; scheduler is V3.1** | Spawner/Producer/Plant handlers record `tick_interval`+`spawn_pool`+`resource_yield` on placements but do not tick. Persistence + scheduler is its own V3.1 ADR |

### 5.1 Schema infrastructure (D3 consequences)

D3's choice expands V3 scope by one chunk (3.4b) and one infrastructure surface:

- **Schema location:** `services/tilemap-service/registry-schemas/object-properties.schema.json` (JSON Schema 2020-12 dialect)
- **Generated output:** `services/tilemap-service/src/types/registry_properties.rs` (one struct per primitive, derive `Serialize/Deserialize`, `TryFrom<&HashMap<String, toml::Value>>`)
- **Generator:** Rust `build.rs` script using `typify` (or `schemars` + a small codegen) — must run at `cargo build` time, deterministic output
- **CI:** `cargo check` regenerates types; if drift between checked-in `registry_properties.rs` and freshly generated, CI fails (drift-prevention test)
- **Schema discipline:** every property in §3.3 table is required-or-optional explicitly; `additionalProperties: false` per primitive (engine ignores unknown ⇒ schema enforces unknown rejection at registry-load, not handler-runtime)

### 5.2 Fuzz infrastructure (D5 consequences)

D5's choice adds proptest as a dev-dependency of `services/tilemap-service` (already in workspace? — verify in chunk 3.4b prep) and one new test file:

- **Location:** `services/tilemap-service/tests/registry_fuzz.rs`
- **Strategy:** proptest generates arbitrary valid `Registry` (tags ∈ `Vec<TagDef>` where each TagDef has a valid primitive + valid required properties for that primitive — drawn from the schema)
- **Invariants checked:**
  1. `place_tilemap_with_registry(arbitrary_registry, fixed_seed)` does not panic
  2. Every output placement's `primitive` matches its `tag`'s registry def
  3. Every output placement's `footprint` is within the registry-declared bounds
  4. Determinism: same `(registry, seed)` → byte-identical output across two runs (covers a proptest input case, not just default registry)
- **Out of scope for the fuzzer:** does NOT replace the default-registry determinism golden — those remain the load-bearing invariant. Fuzzer only tests that V3 handles arbitrary registries without regression.

## 6. Phased build chunks (post-PO-lock)

Each chunk = 1 PR; each PR keeps determinism golden green; recommended for `/amaw` on chunks 3.5 + 3.6 (load-bearing dispatch swap).

| Chunk | Scope | Tests | Risk |
|---|---|---|---|
| **3.4a** | Schema infrastructure (D3): `registry-schemas/object-properties.schema.json` + `build.rs` generator + `src/types/registry_properties.rs` (generated, checked in) + drift-prevention test (`cargo check` regenerates → diff fails CI on drift). | Schema-roundtrip unit tests; existing 433 tests still pass | LOW (additive) |
| **3.4b** | Handler module skeletons in `engine/modificators/handlers/{pickup,blocker,spawner,container,door,trigger,vehicle,producer,plant,decoration}.rs` (10 files — Habitable per D2 omitted). Each handler exports `place_with_registry(&mut placement, &def, &mut ctx)` with V1-equivalent logic copied in. Plumbing only — no dispatch swap yet. | All existing tests still pass (no behavior change) | LOW |
| **3.5** | Dispatch swap inside `obstacle_placer`: route `Obstacle` kind via `blocker_handler` by `registry.resolve_object_tag(...).primitive` lookup. | Golden byte-identical for default registry | **MED — load-bearing**; recommend `/amaw` |
| **3.6** | Dispatch swap inside `treasure_placer`: route `Treasure` / `MonsterLair` via `pickup_handler` / `spawner_handler`. | Golden byte-identical | **MED — load-bearing**; recommend `/amaw` |
| **3.7** | Per-book tag activation: `xianxia:dao-stone` + `xianxia:qi-spring` + `xianxia:formation-array` actually place (currently inert). Add `place_tilemap_with_registry(xianxia_sample, seed=1..5)` xianxia regression suite golden. | ~10 hand-written xianxia tests; default golden unchanged | LOW (additive) |
| **3.8** | Typed property struct migration (D3): all handlers refactored to use generated `BlockerProperties` / `SpawnerProperties` / etc. via `TryFrom<&HashMap>`. Remove ad-hoc property lookups. | All handler tests pass with typed access | LOW (pure type-safety pass) |
| **3.9** | Frontend `TileInspector` debug overlay: show handler-applied properties vs registry-declared (e.g. if `Spawner` handler defaults `tick_interval` when omitted, surface the default). | +2 frontend vitest tests; existing inspector tests unchanged | LOW |
| **3.10** | Registry fuzzer (D5): `services/tilemap-service/tests/registry_fuzz.rs` proptest suite asserts §5.2 invariants over arbitrary valid registries. | Proptest minimization reports + CI runs 256 cases by default | LOW (test-only; no behavior change) |

**Total: 8 chunks / PRs** over the V3 placement engine arc. Schedule: 3.4a → 3.4b in parallel with 3.5/3.6 prep; 3.5 and 3.6 sequential (each is the load-bearing dispatch swap); 3.7–3.10 can interleave once 3.6 lands.

Each chunk is reviewable on its own; each preserves determinism. Recommend `/amaw` for 3.5 + 3.6 specifically (load-bearing dispatch on a determinism-golden code path).

## 7. Test strategy

### 7.1 Determinism golden — load-bearing
- `services/tilemap-service` integration determinism tests run the default registry through every chunk's PR.
- Byte-identical golden expectation across all 6 chunks.
- A failure at any chunk = stop, root-cause; do not rebaseline.

### 7.2 Xianxia regression suite (chunk 3.7)
- `place_tilemap_with_registry(xianxia_sample, seed=1..5)` produces stable goldens across seeds.
- Tests assert: `xianxia:dao-stone` placements have `primitive: Blocker`, footprint correct, handler-applied properties carried.
- Five seeds spread across small + medium grids to surface determinism issues that single-seed tests miss.

### 7.3 Property-driven behavior tests (chunks 3.4b–3.8)
- For each handler: a parametric test runs the handler on a fabricated `ObjectKindDef` with property variations and asserts:
  - `Spawner` with `spawn_pool: ["wolf", "wolf", "bear"]` weights wolf 2× bear
  - `Plant` with `growth_capacity: 0.0` doesn't tick (V3.1 scheduler ignores; V3 records metadata)
  - `Container` with missing `loot_table_id` errors at **registry-load** (not handler-runtime) — schema enforces required-or-optional discipline (D3)

### 7.4 Schema drift prevention (chunk 3.4a)
- A unit test runs the schema codegen at test time and diffs the output against the checked-in `src/types/registry_properties.rs`. Any drift fails CI.
- Equivalent test for the schema JSON: a regression test loads the schema and asserts every primitive in §3.3 table has a corresponding property block.

### 7.5 Registry fuzzer (chunk 3.10, D5)
- See §5.2. Proptest-based; 256 cases by default, configurable via `PROPTEST_CASES`.
- Failure mode: proptest minimizer reports the smallest registry that triggers an invariant violation; commit-as-regression-test pattern.

### 7.6 Migration safety
- A unit test asserts `TilemapObjectKind` → `legacy_kind` round-trip through default registry: every V1 kind variant maps to exactly one default tag, and the mapped tag's `legacy_kind` round-trips back.
- V3.1 deprecation cleanup ADR will add a deprecation-warning test before removing the enum.

## 8. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Determinism golden break during dispatch swap (3.5/3.6) | MED | Each chunk runs golden in CI; if break, stop + root-cause before continuing; `/amaw` recommended for these two chunks |
| Hidden V1-kind dependency in non-placer code (e.g. frontend filters, audit log fields) | MED | Pre-3.5 grep audit of `TilemapObjectKind::` across the workspace; any consumer outside placers gets a `placement.kind` legacy field on the wire (already kept by V2) |
| Schema codegen non-deterministic output (`typify` / `schemars` may reorder fields) | MED | Drift-prevention test catches at CI; if generator is non-deterministic, swap to a deterministic codegen or post-process sort |
| Per-book tag explosion creates test-matrix bloat | LOW | Xianxia regression suite is single-registry; per-book registries each test their own; default-registry golden is the cross-cutting invariant |
| Property-typing churn during 3.8 disrupts handler internals | LOW | 3.8 is a pure-typesafety pass; handler behavior unchanged; deferred until 3.5–3.7 are stable |
| Proptest fuzzer flakes the CI by finding "valid" registries that are pathological (huge tag counts, etc.) | LOW | Bound generators: tag count ≤ 50, property values within realistic ranges; document the bounds in the proptest strategy |

## 9. Acceptance criteria

| ID | Criterion |
|---|---|
| AC-V3-PLACER-1 | Engine placer dispatch reads `ObjectPrimitive` from registry; no `match TilemapObjectKind::*` in placement-routing code paths (only in legacy-alias mapper) |
| AC-V3-PLACER-2 | Default registry produces byte-identical `TilemapView` golden vs the V2 reference (`commit 2279a307`) — determinism preserved end-to-end |
| AC-V3-PLACER-3 | Xianxia sample registry produces stable golden with `xianxia:dao-stone` placed via `blocker_handler` (and similar for `xianxia:qi-spring` / `xianxia:formation-array` if those map to non-Decoration primitives) |
| AC-V3-PLACER-4 | Per-handler property-driven test suite passes (≥1 test per primitive in scope) |
| AC-V3-PLACER-5 | `TilemapObjectKind` legacy mapper round-trips all V1 default-registry kinds bidirectionally |
| AC-V3-PLACER-6 | Frontend `TileInspector` displays unchanged for default registry placements; for xianxia placements, primitive + tag + footprint render correctly (V2 wiring; no new frontend work in V3 placement scope) |
| AC-V3-PLACER-7 | All 433 existing tilemap-service tests + 49 frontend-game vitest tests stay green across all 6 chunks |

## 10. Dependencies on sibling V3 ADRs

- **world-gen ↔ zone-map boundary ADR** (foundational, separate): if the boundary spec defines how world-gen Voronoi cells feed into tilemap-service zone generation, V3 placer must respect that contract. Current V2 placer is zone-local (single zone) so boundary doesn't immediately constrain placement-engine refactor — but property-driven handlers (e.g. `Producer.resource_yield` feeding world-gen settlements) will cross the boundary. Track as follow-up.
- **Per-channel registry selection ADR** (separate, smaller): HTTP layer changes to pick the registry. V3 placer just needs the registry passed in via `ModificatorContext` — already wired in V2 (`place_tilemap_with_registry`). No coupling.
- **Footprint-honoring frontend ADR** (separate, frontend-only): V3 placer writes footprint in `TilemapObjectPlacement` (V2 wire shape already carries it). Frontend chooses how to render. No coupling.
- **Asset pipeline thaw ADR** (DEFERRED #037, separate): new tags need new sprites. V3 placer is sprite-agnostic — it produces placements with tags, and the frontend resolves tag → sprite. Coupling is at the tag namespace, not the placement engine.

## 11. Out of scope (explicit)

- Adding new primitives (Slippery, NPC, Animal, etc. per V2 §2.1.2). Each is its own ADR gated on its game-mechanic shipping.
- Tick scheduler implementation (D7). V3 handlers write `tick_interval` metadata; the scheduler is V3.1+.
- World-gen integration (continental Voronoi cells → zone tilemap pipeline). Boundary ADR territory.
- Per-channel registry selection. Sibling ADR.
- Footprint-aware sprite sizing in frontend. Sibling ADR.
- Per-book asset generation pipeline. DEFERRED #037 ADR.

## 12. Next steps (PO lock complete 2026-05-28)

1. ✅ PO locked D1–D7 same session — see §5.
2. Write `docs/plans/2026-05-28-v3-registry-driven-placement-build.md` chunking the 8 build PRs in detail (file lists, ACs per chunk, test deltas, /amaw triggers).
3. Start chunk **3.4a (schema infrastructure)** on a fresh implementation branch `mmo-rpg/zone-map-v3-placement-engine` off main — this is the foundational chunk D3 added; everything else depends on it.
4. Then chunk **3.4b (handler skeletons)** — additive plumbing only.
5. `/amaw` for chunks **3.5 + 3.6** (load-bearing dispatch swap on determinism-golden code path).
6. Chunks 3.7–3.10 interleave once 3.6 lands.
