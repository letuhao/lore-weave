# Spec — Tilemap world-inheritance contract

> **Status:** ✅ ACCEPTED 2026-05-24 (PO sign-off received: "approve"). All
> §13 checkboxes implicitly cleared by single-word acceptance. CLARIFY/DESIGN
> phase done; PLAN file required next before BUILD. Branch
> `mmo-rpg/zone-map-amaw`.
> **Workflow:** v2.2 default (architecture review; will reclassify when BUILD is scoped).
> **Sources:**
> - Upstream contract: [`lore-weave-game/docs/plans/2026-05-23-flatworld-region-tree-data-architecture.md`](../../../lore-weave-game/docs/plans/2026-05-23-flatworld-region-tree-data-architecture.md) (sibling repo)
> - This-repo tilemap design: [`features/00_tilemap/TMP_001`..`TMP_009`](../03_planning/LLM_MMO_RPG/features/00_tilemap/_index.md)
> - Session context: PO answers 2026-05-24 (six clarifying questions, all answered)

---

## 1. Problem

`lore-weave-game/world-gen` (sibling repo) shipped a **consumer contract** on
2026-05-24 — §11 of the locked region-tree design. Levels 0-2 (plates + zones +
sub-zones) plus a 10-biome climate classifier are now stable surface that
downstream consumers can build against. The contract document explicitly names
the tilemap track as one of those consumers.

This-repo `tilemap-service` was designed and built (Phase 0a-3 done, ~16k LOC)
**before** that contract existed. It currently:

- Has its own biome taxonomy (e.g. `alpine_dwarf_shrub_cluster`,
  `abyss_chaos_rift`, `grassland_temperate`) in `engine/biome_library.rs`
- Derives zones from an LLM L3 classifier on narrative seeds, not from
  plate/climate geometry
- Has its own determinism contract: `derive_seed(reality_id, channel_id,
  template_id, seed_offset)`
- Has no input layer that accepts macro-world facts

If we proceed to BUILD without reconciling these, tilemap-service will
generate **paradoxical content** — e.g. a `hot_desert` tilemap inside a
world-gen `ice` zone. PO 2026-05-24 verbatim:
*"zone của chúng ta là glacier thì tilemap không thể là hot desert"*.

This spec locks the architecture **before** code so that reconciliation is
deliberate and surface-narrow.

---

## 2. Decision — two-layer inheritance, information-only

Two consumer roles, two data layers. Information flows down; nothing else does.

```
┌──────────────────────────────────────────────────────────────┐
│ WORLD MAP  ─  lore-weave-game/world-gen                       │
│ • Player-facing: strategy menu (economy, trade, war)         │
│ • SSOT for macro facts                                       │
│   - plate identity, drift, base elevation, collision uplift  │
│   - zone polygon (Voronoi cells)                             │
│   - zone climate: temp_mean, precip_annual                   │
│   - zone biome: Whittaker (10 variants)                      │
│ • Stable contract: §11 of upstream doc; mock today, HTTP next│
└──────────────────────────────┬───────────────────────────────┘
                               │
                               │  WorldZoneSnapshot  ── pull, typed
                               │  (no seed, no control flow)
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ TILEMAP  ─  this repo / services/tilemap-service              │
│ • Player-facing: RPG environment, interactive                │
│ • Consumes WorldZoneSnapshot as input                        │
│ • Has own biome taxonomy + selection logic                   │
│ • Validates: BiomeBridge — Whittaker → game biome compat     │
│ • Generates per-tile content INSIDE inherited constraint     │
│ • Own determinism (own seed, own algorithms)                 │
│ • All existing logic survives — adds 1 input layer only      │
└──────────────────────────────────────────────────────────────┘
```

**What flows between the layers:**

- ✅ **Information**: zone biome, climate, base elevation, plate identity, zone
  polygon
- ❌ **Seeds**: each layer keeps its own RNG contract
- ❌ **Control flow**: tilemap does not call world-gen during generation; the
  snapshot is staged ahead of time
- ❌ **Coupling on internals**: tilemap does not import world-gen Rust
  algorithms; it parses the shipped JSON contract only

**PO answers that drove this shape (2026-05-24):**

1. World map = chiến lược layer; tilemap = RPG layer. Two roles, not
   replacement.
2. Tilemap inherits biome **as information**, not as taxonomy. World biome
   constrains the set of game biomes tilemap may pick.
3. Macro → micro inheritance. Zone info from world is SSOT; tilemap augments.
4. Spatial mapping is flexible — a single tilemap may inhabit a zone, a
   sub-zone, or (impractical) a plate. Decided per-template, not globally.
5. Determinism: information flows down, seeds don't. Tilemap replay needs the
   same `WorldZoneSnapshot` input; if upstream re-generates, tilemap output
   will change (expected — input changed).
6. Existing 16k LOC survives. The change is **additive**: one new input
   layer + one new validation layer.

---

## 3. Mockup-first development

PO 2026-05-24 verbatim: *"bạn tạo mockup data json trước giúp tôi, sau này
chúng ta merge branch thì tính tiếp tới việc wire service"*.

Two mock JSON fixtures land alongside this spec:

| File | Plates × Zones × Sub | Biomes covered | Purpose |
|---|---|---|---|
| [`tests/fixtures/world-mock/minimal.json`](../../services/tilemap-service/tests/fixtures/world-mock/minimal.json) | 3 × 2 × 1 | 6 of 10 | Unit tests, eyeball-able |
| [`tests/fixtures/world-mock/diverse-biomes.json`](../../services/tilemap-service/tests/fixtures/world-mock/diverse-biomes.json) | 5 × 2 × 1 | All 10 | Bridge logic exercise |

Schema, versioning, SSOT-vs-lever boundary, biome tag table, units — see
[`tests/fixtures/world-mock/README.md`](../../services/tilemap-service/tests/fixtures/world-mock/README.md).

Fixtures mirror upstream §11.2 base schema and pre-emptively include two §11.5
levers (`climate` per zone, `boundary` per zone) because tilemap **cannot
function without them**. When upstream ships those levers, mock and wire
converge — additive change, no parser rewrite.

---

## 4. Contract — Rust types tilemap will introduce

These are the **only** new types this contract requires. Everything else is
internal to tilemap and unaffected.

```rust
// src/world_inherit/mod.rs (new module — name tentative)

/// Wire-shaped read of one world-gen zone. Parsed from JSON (mock now, HTTP
/// later). Frozen at tilemap construction time so replay determinism is
/// stable — the snapshot is the only upstream input tilemap sees.
#[derive(Debug, Clone, serde::Deserialize, serde::Serialize)]
pub struct WorldZoneSnapshot {
    pub path: RegionPath,              // e.g. [2, 1] = plate 2, zone 1
    pub site: [f32; 2],                // Voronoi site, world px
    pub base_elevation: f32,           // BASE_LEVEL + collision uplift here
    pub boundary: Vec<[f32; 2]>,       // CCW polygon, world px (lever)
    pub climate: ZoneClimate,          // lever
}

#[derive(Debug, Clone, Copy, serde::Deserialize, serde::Serialize)]
pub struct ZoneClimate {
    pub temp_mean: f32,                // °C, mean annual
    pub precip_annual: f32,            // mm/yr, total annual
    pub biome_tag: u8,                 // 0..9, see WorldBiome
    pub biome_name: WorldBiome,        // typed enum on top of tag
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum WorldBiome {
    Ice,                  // 0
    Tundra,               // 1
    BorealForest,         // 2
    TemperateForest,      // 3
    TemperateGrassland,   // 4
    HotDesert,            // 5
    Savanna,              // 6
    TropicalRainforest,   // 7
    DeciduousForest,      // 8
    Mediterranean,        // 9
}

/// `RegionPath` is the file-path-style address from upstream §2. Stored as
/// a small Vec so depths beyond 2 work transparently when upstream extends.
#[derive(Debug, Clone, PartialEq, Eq, Hash, serde::Deserialize, serde::Serialize)]
pub struct RegionPath(pub Vec<u32>);
```

**`TilemapTemplate` gains one optional field:**

```rust
pub struct TilemapTemplate {
    // ... existing fields unchanged ...
    pub world_zone: Option<WorldZoneSnapshot>,  // None = standalone mode
}
```

`None` keeps current Phase 0a-3 behavior alive (templates without a world
inheritance — useful for unit tests and synthetic realities). `Some(_)` opts
in to the bridge rules in §5.

---

## 5. BiomeBridge — the only validation rule that matters today

The bridge answers one question: *given world biome X, which tilemap biomes
are allowed?* It is **pure data**, declared once in tilemap config, NOT
inferred at runtime.

```rust
// src/world_inherit/biome_bridge.rs

pub struct BiomeBridge {
    /// For each upstream biome, the set of game-biome ids (strings) tilemap
    /// may pick from. Empty set ⇒ no allowed game biome ⇒ template error.
    pub allow: HashMap<WorldBiome, HashSet<String>>,
}

impl BiomeBridge {
    pub fn validate_pick(&self, world: WorldBiome, game: &str) -> Result<(), BridgeViolation>;
    pub fn allowed_for(&self, world: WorldBiome) -> &HashSet<String>;
}

pub enum BridgeViolation {
    /// Tilemap picked a game biome not in the allowed set for the world biome.
    Disallowed { world: WorldBiome, picked: String, allowed: HashSet<String> },
    /// Bridge declares an empty allow-set for this world biome.
    EmptyAllowSet { world: WorldBiome },
}
```

**Example mapping (illustrative; final mapping is config, not code):**

| Upstream `WorldBiome` | Allowed game biomes (`engine/biome_library.rs` ids) |
|---|---|
| `Ice` | `glacier`, `frozen_waste`, `ice_field` |
| `Tundra` | `snow_frost`, `taiga_edge`, `permafrost_steppe` |
| `BorealForest` | `taiga_dense`, `pine_forest`, `boreal_marsh` |
| `TemperateForest` | `temperate_woodland`, `oak_grove`, `mossy_dell` |
| `TemperateGrassland` | `grassland_temperate`, `windswept_plain` |
| `HotDesert` | `dune_sea`, `red_canyon`, `salt_flats` |
| `Savanna` | `dry_savanna`, `acacia_scrub` |
| `TropicalRainforest` | `jungle_dense`, `mangrove_delta`, `humid_canopy` |
| `DeciduousForest` | `oak_grove`, `autumn_woodland`, `temperate_marsh` |
| `Mediterranean` | `olive_grove`, `chaparral`, `coastal_pine` |
| (any) | `abyss_chaos_rift` — special: bridge MAY allow this anywhere if a "rift" flag is set on the template, modeling reality-warping content that ignores climate |

The actual mapping table is **not finalized in this spec** — it lives in
config and gets refined as `biome_library.rs` evolves. The contract here is
the *mechanism*, not the *table*.

**Where the bridge runs:**

- In `engine/biome_select.rs`, where tilemap picks a game biome for a zone
- Before the L3 classifier emits a candidate, the allow-set narrows
  the search space
- After L3 emits, the validate_pick call enforces the rule (defense in depth)

**What the bridge deliberately does NOT do:**

- Does NOT translate temperature/precip into game stats — those are tilemap's
  own affair. Only `biome` is mapped.
- Does NOT auto-generate the table from Whittaker science — the table is
  authored, expressing game design intent.
- Does NOT collapse upstream biome variants — every `WorldBiome` keeps a
  distinct allow-set even if two have overlapping game biomes.

---

## 6. Spatial frame — where does a tilemap sit in the world

PO answer 4 (2026-05-24): *"không có qui định, vì world map là phân cấp từ
cha tới con, nó là 1 nhánh đệ qui, tilemap của chúng ta có thể là 1 trong
bất cứ zone level nào, kể cả level mảng kiến tạo, nhưng tôi không nghĩ là
chúng ta có thể gen 1 tilemap khổng lồ như vậy"*.

**Decision:** a tilemap is anchored to **one** `RegionPath`. The path
identifies which world region the tilemap inhabits. Depth is per-template,
not global.

- `path = [2, 1]` (zone) — typical case; tilemap is the playable interior of
  one Voronoi zone
- `path = [2, 1, 3]` (sub-zone) — finer-grained; one tilemap per sub-zone of
  one zone
- `path = [2]` (plate) — theoretical; impractical (PO acknowledged)
- `path = []` (world root) — disallowed; templates must anchor

Tilemap's own grid (`GridSize` + tile coords) sits in a **local** frame; the
`WorldZoneSnapshot.boundary` gives the world-px polygon where this tilemap is
embedded. Mapping `tilemap_xy ↔ world_xy` is a single affine transform stored
per-template (out of scope for this spec — see future spec on rendering).

---

## 7. Determinism contract — what replay means now

Tilemap's existing determinism contract:

```
seed = derive_seed(reality_id, channel_id, template_id, seed_offset)
TilemapView = generate(template, seed)
```

is **unchanged**. The only addition: `template` now carries the optional
`world_zone: WorldZoneSnapshot`, and the snapshot is part of the input.

**Replay rules:**

- Same `seed` + same `template` (including the embedded `WorldZoneSnapshot`)
  → byte-identical `TilemapView`. Unchanged.
- If upstream regenerates the world with a different seed → snapshot differs
  → input differs → tilemap output legitimately differs. Replay does NOT
  promise stability across world re-generations.

**Optional provenance lever** (deferred — implement when needed): tilemap
manifest stores `blake3(serialized_snapshot)` so a future replay can detect
upstream drift and refuse to mix old tilemap with new world. Not load-bearing
for v1.

**What the bridge does NOT change about determinism:**

- The bridge is pure declarative data — same inputs → same allow-set →
  same picks
- The L3 classifier's existing retry loop is unchanged; the bridge just
  narrows the candidate pool earlier

---

## 8. Integration mode — mockup now, HTTP after merge

PO answer (2026-05-24): *"sau khi merge main branch thì chúng là services
trong compose hiện tại, do đó chúng ta có internal communication giống các
service khác, bạn tạo mockup data json trước giúp tôi, sau này chúng ta merge
branch thì tính tiếp tới việc wire service"*.

**Phase 1 (this branch):** parse JSON from `tests/fixtures/world-mock/`.
Tilemap-service has a `WorldSource` trait with one impl `MockFileWorldSource`
that reads the fixture. CLI + tests pass a path; templates that opt in
declare which fixture path to load.

```rust
// src/world_inherit/source.rs
pub trait WorldSource {
    fn load_zone(&self, path: &RegionPath) -> Result<WorldZoneSnapshot, WorldSourceError>;
}

pub struct MockFileWorldSource { /* parses JSON; caches by file */ }
```

**Phase 2 (post-merge):** `HttpWorldSource` lives next to `MockFileWorldSource`,
implementing the same trait. Service URL via env var
(`WORLD_GEN_SERVICE_URL`); internal-token auth matching the docker-compose
pattern other services use (see `auth-service`, `book-service`). Tilemap
templates and tests don't change — only the `WorldSource` implementation
swaps.

Endpoint shape (proposed; finalized at wire time, not now):

```
GET /internal/v1/worlds/{seed}/zones/{path}
Authorization: Bearer <internal-token>
→ 200 OK + application/json + WorldZoneSnapshot body
  404      if zone path doesn't exist in this world
  401      bad/missing internal token
```

Wire shape mirrors the JSON fixture 1:1 (minus the wrapper fields like
`schema_version`, which become response headers).

**Why this split is safe:**

- Trait-driven — no production code path depends on file-loading
- Mock fixtures stay as test fixtures forever
- Wiring up Phase 2 is purely a new struct + docker-compose entry; no
  contract change

---

## 9. What this spec deliberately does NOT decide

Tracked as future work; do NOT pre-build:

1. **The exact biome bridge table** (§5). Mechanism locked; table is config
   tuned as `biome_library.rs` evolves. Initial table can be naive
   (one-to-one + fallback) and refined per playtest.
2. **Tilemap ↔ world-px coordinate transform** (§6 last paragraph). Decided
   when rendering / first-playable-map work lands; this spec only locks the
   *frame existence*, not the math.
3. **Seam / adjacency consumption** (upstream §5 of the locked design). The
   upstream contract has it deferred too; tilemap consumes it later, jointly
   with upstream lifting it from "locked design" to "shipped".
4. **Climate-to-stat translation** (e.g. precip → encounter table weights).
   Out of scope — this spec is about *constraint*, not *gameplay derivation*.
5. **What happens when `world_zone = None`** in non-trivial templates. Today:
   tilemap behaves as before (no constraint). Tomorrow: may warn at template
   load time. Decision deferred until a real consumer pattern emerges.
6. **L3 classifier ↔ bridge interaction** (does L3 also see the world biome
   as prompt context, or only the allow-set?). Decided at BUILD time when the
   L3 prompt is updated.
7. **Server-side world-gen-service shape** — this repo doesn't own it.
   Upstream owns the service; tilemap owns its client.

---

## 10. Migration plan (when BUILD opens)

Surface for the BUILD phase that follows this CLARIFY:

| Step | Files touched | Notes |
|---|---|---|
| 1. Add `world_inherit` module skeleton | `src/world_inherit/{mod, types, source, biome_bridge}.rs` | New module, no existing code changes |
| 2. Parser + `MockFileWorldSource` | `src/world_inherit/source.rs` + unit tests | Reads both fixture files; round-trip test |
| 3. `TilemapTemplate::world_zone: Option<_>` | `src/types/template.rs` | Additive field; default None preserves existing tests |
| 4. `BiomeBridge` declaration | `config/biome_bridge.toml` (new) + loader | Initial table = naive + abyss_chaos_rift "any" |
| 5. Wire bridge into `biome_select` | `src/engine/biome_select.rs` | Allow-set filter; defense-in-depth validate_pick |
| 6. Integration test: load mock → derive constrained tilemap | `tests/world_inherit_integration.rs` | End-to-end across both fixtures |
| 7. Deferred: `HttpWorldSource` | (post-merge) | Same trait, no template change |

Sizing per CLAUDE.md task workflow: this is **L** (6+ files, side effects on
biome selection). PLAN file required before BUILD; sub-phases possible.

---

## 11. Open questions (NOT blocking this DESIGN)

- **Biome bridge config format** — TOML, YAML, or Rust const? TOML is
  consistent with other tilemap config; will assume TOML in BUILD unless PO
  says otherwise.
- **Bridge table authorship workflow** — does PO author it directly, or does
  it ship as a generated stub that PO then edits? Recommend stub.
- **Snapshot caching strategy** — `MockFileWorldSource` caches per file;
  `HttpWorldSource` cache TBD. Defer until wire phase.
- **Multi-zone tilemaps (template inhabits two adjacent world zones)** —
  current schema is one-`RegionPath`-per-template. If multi-zone needs
  appear (e.g. a city straddling two biomes), extend `world_zone` to a list
  later. Out of scope now.

---

## 12. Compliance check

Per CLAUDE.md repo rules:

| Rule | This spec |
|---|---|
| Contract-first | ✅ Mock JSON + Rust types defined before BUILD opens |
| Gateway invariant | ✅ N/A this spec; Phase 2 HTTP will go through standard internal-auth pattern, not LLM gateway |
| Provider gateway invariant | ✅ N/A — no LLM call introduced |
| Language rule | ✅ Rust for this service; no new language |
| No hardcoded secrets | ✅ `WORLD_GEN_SERVICE_URL` + internal token via env in Phase 2 |
| No hardcoded model names | ✅ N/A |
| Each service owns its Postgres DB | ✅ N/A — tilemap doesn't persist world data; reads on demand |
| Frontend MVC rules | ✅ N/A — backend spec |
| No platform lock-in | ✅ Standard HTTP between docker-compose services |

---

## 13. PO sign-off checklist (POST-REVIEW gate)

PO sign-off received 2026-05-24 ("approve"). Acks cleared en bloc:

- [x] Two-layer architecture (§2) is the right shape for "world strategy vs
      tilemap RPG"
- [x] Information-only inheritance (no seeds, no control flow) matches intent
- [x] BiomeBridge mechanism (§5) is the right form of "no hot desert in
      glacier"
- [x] Spatial flexibility (§6) — tilemap-per-zone is the default, plate-level
      is impractical and that's fine
- [x] Determinism story (§7) — replay holds per-(seed, snapshot); world
      re-gen drift is acceptable
- [x] Mockup-now / HTTP-later (§8) is the right phasing
- [x] Migration plan (§10) is sequenced reasonably

CLARIFY/DESIGN phase complete. PLAN file required before BUILD per CLAUDE.md
workflow.
