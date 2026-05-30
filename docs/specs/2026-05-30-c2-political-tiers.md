# C-2 — Political tiers (strict geometric nesting) — spec + plan

> **Task size: XL.** C3 arc, sub-phase C-2 (after C-1a model + C-1b render).
> Parent: [`FLAT_TO_3D_MIGRATION_PLAN.md`](../03_planning/LLM_MMO_RPG/FLAT_TO_3D_MIGRATION_PLAN.md).
> PO decisions (session 99): **strict nesting** (political ⊆ geometric) + **keep
> `State`** as the nation tier (no rename).

## Goal

Extend the sphere's political layer from 2 tiers (province → state) to 5,
**strictly nested inside the C-1a geometric frame**:

```
world (root)
 └ realm    ⊆ continent      = cluster of states (nations) within a continent
    └ state ⊆ subcontinent   = cluster of provinces within a subcontinent  [EXISTING type, kept]
       └ province ⊆ region   = terrain-cost flood-fill within a region
          └ county           = subdivide a province (flood-fill within province)
```

`state` IS the existing `State` type (documented as the "nation" tier; no
rename — keeps render/civ_adapter/naming untouched).

## Strict-nesting model (why it is coherent)

Two orthogonal hierarchies — geographic (continent⊃subcontinent⊃region, C-1a)
and political (world⊃realm⊃state⊃province⊃county) — are coupled so the political
one *refines* the geographic one:

- **province ⊆ region**: provinces partition each region's land. A province
  never straddles two regions.
- **state ⊆ subcontinent**: states cluster the provinces of one subcontinent.
  Since province ⊆ region ⊆ subcontinent, every province sits in exactly one
  state, and `state ⊆ subcontinent` holds.
- **realm ⊆ continent**: realms cluster the states of one continent. state ⊆
  subcontinent ⊆ continent, so realm ⊆ continent holds and state ⊆ realm holds.
- **county ⊆ province** (and so ⊆ region): counties subdivide a province.

The political hierarchy (county⊆province⊆state⊆realm) AND the geometric coupling
(province⊆region, state⊆subcontinent, realm⊆continent) both hold simultaneously.

## Reuse (R7) — no new algorithms

Every tier reuses the existing `political.rs` machinery, only changing the
*scope* it runs within:

| Tier | Mechanism | Scope change |
|---|---|---|
| province | `multi_source_assign` terrain-cost flood-fill (exists) | seeds constrained to each **region** |
| county | same flood-fill (exists) | run within each **province** |
| state | farthest-point seed + nearest-seed assign (exists) | cluster per **subcontinent** (was per land-component) |
| realm | same cluster pattern | cluster states per **continent** |
| world | trivial root | one entity |

## Coupling decision — TWO political builders (load-bearing)

`political::build` (the current 2-tier, per-land-component builder) is **kept
unchanged** — the **frozen flat track** (`civ_adapter`) still calls it and must
not change behaviour. A **new** `political::build_nested(...)` is added for the
**sphere** only; it takes the geometric hierarchy
(`continent_of`/`subcontinent_of`/`region_of` + the entity vecs) and produces
the 5-tier strict-nested output. `lib.rs::generate` switches the sphere from
`build` to `build_nested`. The old `build` populates the new Province/State
fields with the `NONE` sentinel (flat has no sphere hierarchy).

## Data model

`world_map.rs`:
- `Province` gains `region: u32` (the region it nests in; `u32::MAX` from the
  flat/old builder).
- `State` gains `subcontinent: u32` and `realm: u32` (sentinels from old
  builder).
- NEW `County { id, capital_cell, province, #[serde(default)] name }` +
  `county_of: Vec<u32>` (per cell; `NONE` for water / non-land).
- NEW `Realm { id, capital_state, continent, #[serde(default)] name }`.
- NEW `World { #[serde(default)] name }` — single root entity (names the world;
  no per-cell vector — the whole map is the world).
- `WorldMap` new fields: `county_of`, `counties`, `realms`, `world` (all
  `#[serde(default)]`).
- `compute_hash` extended; `name` fields excluded (same carve-out).

## Staging

- **C-2a** (this spec, XL): the 5-tier model + `build_nested` + data model +
  hash + partition-invariant tests. **No render, no naming wiring.**
- **C-2b** (S, later): `--realm-png` / tier-coloured political render.
- **C-2c** (S, later): naming integration (LLM names realms/counties; the
  naming layer already names states/provinces).

## C-2a tests (partition invariants — the VERIFY, since no render)

1. **Nesting — province ⊆ region**: every cell's `province`'s `region` ==
   `region_of[cell]`; equivalently all cells of a province share one region.
2. **Nesting — state ⊆ subcontinent**: `states[province.state].subcontinent`
   == `subcontinent_of[cell]` for every land cell.
3. **Nesting — realm ⊆ continent**: `realms[state.realm].continent` ==
   `continent_of[cell]`.
4. **Political nesting**: county.province valid; province.state valid;
   state.realm valid; counts monotone (counties ≥ provinces ≥ states ≥ realms).
5. **No orphan land cell**: every land cell has a valid county/province/state/
   realm (none `NONE`); water cells are all `NONE`.
6. **Determinism**: two generates identical + identical `content_hash`.
7. **Hash coverage**: tamper each new field + parent link (region, subcontinent,
   realm, county.province, realm.continent) ⇒ `verify_hash` fails; names ⇒ true.
8. **Flat unchanged**: old `political::build` output is byte-identical to before
   (new fields = `NONE`); the flat `civ_adapter` determinism test still passes.

## Ripple / risk register

| ID | Risk | Mitigation |
|---|---|---|
| K1 | Changing sphere political re-bases `content_hash` | Expected; run-vs-run determinism only, no literal pins (as C-1a) |
| K2 | Adding fields to Province/State breaks construction | Only `political.rs` constructs them; update both builders |
| K3 | Flat `civ_adapter` behaviour drifts | Old `build` kept verbatim; new fields = `NONE`; assert flat determinism test unchanged |
| K4 | A region with no land seeds → empty province? | Every region has ≥1 land cell by construction (regions come from land cells); seed each region with ≥1 province |
| K5 | A subcontinent/continent with 0 states (tiny) | Guarantee ≥1 state per subcontinent, ≥1 realm per continent (like the existing `.max(1)` quota floors) |
| K6 | county explosion at gigaplanet | counties bounded by a per-province subdivision knob; reuse a clamp |
| K7 | render/civ_adapter read `state`/`province` | Untouched — fields are ADDED, existing fields keep meaning |

## Out of scope (C-2a)

Render (C-2b), naming (C-2c), re-anchoring settlements/routes/culture to the new
tiers, any flat-track change.
