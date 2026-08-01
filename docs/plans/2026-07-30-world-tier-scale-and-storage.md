# Plan — world-tier scale, world-data storage, and the applied-amendment rot

> **Date:** 2026-07-30 · **Size:** XL (files=28, logic=13, side_effects=4) · **Track:** LLM_MMO_RPG
> **Branch:** `feat/game-logic` · **Predecessor:** `3864ade0a` (control_binding)
> **PO decisions captured at CLARIFY** — see §0.

This plan covers one coherent effort with four clusters. They are one effort because all four are
blocked on the same thing: **the world tier has no agreed data shape**, and three separate registers
each claim a piece of it while disagreeing about whether the pieces landed.

---

## 0 — PO decisions (CLARIFY, 2026-07-30)

| # | Decision | Note |
|---|---|---|
| **P1** | **Production world scale = `WorldScale::Megaplanet` (16 384 cells)** | Chosen at the **TOP** of GEO_001's `[1024, 16384]` band. PO was told there is no headroom; growing later means amending the validator, not adding a variant. Recorded so that is not a surprise. |
| **P2** | **`Gigaplanet` (501 264 cells) is a generator stress fixture, not a game scale** | It already **violates** GEO_001's own `cell_count_out_of_bounds`. The spec forbade it before this plan existed; the generator is the outlier. |
| **P3** | **Store the full generated payload; do NOT strip derivable data yet** | Measured: **67.6 %** of the payload is recomputable. PO chose simplicity now. The measurement is recorded with a wake-up trigger, **not** silently dropped. |
| **P4** | Design-first; implement only what a decision needs to stop rotting | Carried from the prior arc. Guards and gates count as *mechanism*, not as feature build. |

---

## 1 — What was measured (evidence, not estimate)

`crates/world-gen` built at `--release`, seed 7, every scale:

| Scale | Cells | Payload (pretty) | Provinces | States | Settlements | Routes |
|---|---:|---:|---:|---:|---:|---:|
| Pocket | 1 024 | 0.95 MB | 20 | 5 | 8 | 9 |
| Region | 2 025 | 1.9 MB | 26 | 8 | 10 | 10 |
| Continent | 8 281 | 7.6 MB | 25 | 7 | 11 | 18 |
| SuperContinent | 12 321 | 11.2 MB | 31 | 7 | 13 | 18 |
| **Megaplanet ← P1** | **16 384** | **14.9 MB** | 36 | 8 | 17 | 34 |
| ~~Gigaplanet~~ | 501 264 | **459 MB** (9.4 s) | 121 | 24 | 162 | 362 |

Two facts fall out, and both are load-bearing for the decisions below:

1. **Content barely tracks resolution.** 16× the cells (1 024 → 16 384) buys **1.8×** the provinces
   and 2.1× the settlements — and Continent (8 281) yields *fewer* provinces than Region (2 025),
   i.e. the relation is not even monotonic. Mesh resolution buys **boundary smoothness**, not content.
   This is why P1 is a free choice rather than a capacity trade.
2. **Two thirds of the payload is not data.** Composition at Continent scale, compact JSON:

   | Component | Bytes | Share |
   |---|---:|---:|
   | `vertex_polygon` | 1 907 232 | 50.1 % |
   | `neighbors` + `center` + `is_coast` | 666 534 | 17.5 % |
   | **derivable total** | **2 573 766** | **67.6 %** |
   | irreducible | 1 232 363 | 32.4 % |

   `mesh.rs` states why: *"Fibonacci lattice — quasi-uniform in solid angle, **deterministic given
   `n`**. A seed-driven 3D rotation reorients the whole lattice"*, and its own test asserts *"the
   seed-driven rotation is the **only** source of seed dependence here."* So the whole mesh is
   `fibonacci(n) · R(seed)` — an integer and a quaternion. Adjacency is Quickhull over those centres;
   `is_coast` is `elevation ≥ sea_level ∧ ∃ neighbour < sea_level`.

   Vertices per cell measured **exactly 6.00** — the Euler floor for a sphere tessellation. *"Lesser
   detail polygon"* therefore has only one lever, **cell count**; per-polygon detail is already minimal.

Packed, the irreducible per-cell payload is `elevation u16 + climate u8 + biome u8 + river_flux u16
+ 7 region ids u16` ≈ **20 B/cell** → Megaplanet ≈ **320 KB**. Under P3 we do not do this yet.

---

## 2 — Cluster A · World-tier scale (P1 + P2)

> **⚠ A1/A2 were rewritten by `RD-1` at design review (§7).** The first draft put a GEO_001 band
> constant inside `crates/world-gen`, which breaks the crate's stated decoupling *and* would have been
> near-vacuous (a constant compared against a copy of itself). The steps below are the revised ones.

| Step | Change | File |
|---|---|---|
| A1 | Declare the **production scale set** and the cell-count band **in the doc**, in a machine-readable block | `GEO_001` |
| A2 | **Cross-source guard** — a `design-lint` check that parses cell counts from the Rust and the band + production set from the doc, and fails when a declared-production scale falls outside the declared band. Neither side alone can satisfy it. | `scripts/` |
| A3 | Record P1/P2 as `GEO-*` decisions; state Megaplanet sits at the band **ceiling** | `GEO_001`, `GEO_WORLD_TIER_REDESIGN` §9 |
| A4 | Close `GEO_WORLD_TIER_REDESIGN` §9 **Q3** (tier-2 persistence) — its stated trigger *"revisit when tier-2 implementation begins"* has arrived | ditto |

**Why a guard and not a sentence.** A tracked decision needs a mechanism — the rule this project has
paid for twenty-six times. "Gigaplanet is not for production" as prose survives exactly until the next
agent opens `WorldScale` and sees six equal variants. The guard makes that claim **fail**.

**Why cross-source and not a unit test.** A unit test inside the crate can only compare the crate to
itself. The defect being guarded against is **two documents drifting apart**, so the check must read
both. That is also why it cannot be satisfied by editing one side.

**Bite-test obligation (NV-2).** Add `Gigaplanet` to the doc's production set, watch A2 go red, paste
the output, revert.

---

## 3 — Cluster B · World-data storage (new doc 37, `WDS-*`)

### The defect

`GDA-D4` (sealed): *"Seeding emits events, never direct aggregate writes — `PlaceBorn` / `LayoutBorn`
/ `TilemapBorn` / `GeographyBorn`… would bypass the log and leave a reality whose first state has no
causal record — unreplayable from t=0."*

At P1 that is ~33 k genesis events for a payload that **regenerates in ~1 s from a 32-byte seed**;
at the stress scale it was ~1 M events and >1 GB of `event_log`. `RBS-Q1` saw half of this and treated
it as a **budget** problem (*"does a Megaplanet simply take hours?"*), scoped to the wrong scale.

The category is wrong, not the budget. **`GDA-D4` is right for authored content and wrong for
generated bulk, and nothing in the spec distinguishes the two.**

### The resolution

`GDA-D4`'s *reason* survives — nothing enters the world without a causal record. Its *mechanism*
changes for generated content: a **pinned content digest is a causal record, and a stronger one**,
because 33 k events can drift from the generator while a `content_hash` cannot. The repo already
holds this principle one layer over: `EVT-A9` requires EVT-T5 Generated to use *"deterministic RNG
seeded from a stable causal-ref… replay reproduces same output given same input"* — which is exactly
what `generate(seed, CreativeSeed) → WorldMap` + `content_hash` + the CI blake3 pins already are.

| What | Where | Authority |
|---|---|---|
| `(seed, CreativeSeed, generator_version)` | reality row, meta registry | provenance — reproducible, auditable |
| `WorldMap` bytes, addressed by `content_hash` | **`WorldBaselineStore`** — the *same shape as `RulesetStore`*: content-addressed, `put` never overwrites, `get` verifies the hash. Filesystem now, object store later (see `RD-2`) | **SSOT for the t=0 baseline** — immutable; never pruned while referenced |
| `space_node` tree + place/geo rows | Postgres projection | **derived** — rebuildable |
| divergence after t=0 | `event_log` | **SSOT for history** |
| live state while Hot | island memory | authoritative (DP-X1 T1) |

Genesis becomes **O(1), not O(cells)**: one `WorldBaselinePinned { content_hash, seed,
generator_version }` in place of ~33 k `*Born`. `RBS-Q1` dissolves.

### The honest qualification — this one changes the conclusion

The generator uses `f32` noise. **Cross-platform float determinism is not guaranteed**; the blake3
pins hold on the CI platform only. Therefore **the seed alone is NOT sufficient for a live reality**:
the bytes are stored and the digest verifies them; a mismatch is a hard error, never a silent
divergence. Regeneration is the **audit** path, not the **serving** path. `generator_version` is part
of the pin, and a generator version may not be deleted while a reality pins it — the ruleset store's
own rule (*"never pruned while referenced"*). The plan doc records that `content_hash` has already
been re-baselined once on an intentional algorithm change, which is the evidence this matters.

### Deferral, with a trigger

P3's stripping of the derivable 67.6 % gets a row naming **what would wake it**: *"the first commit in
which world-payload size or wire bandwidth is measured as a constraint"*. `PROSE_ONLY` in
`scripts/deferral-gate.py` — the gate fails the row once the id becomes mechanised, so it shrinks.

---

## 4 — Cluster C · The applied-amendment rot

### What is actually wrong

`01_feature_ownership_matrix.md:229` claims *"Applied so far: `SPG-R1` · `SPG-R3` · `SPG-R5`"*.
Checked against the three targets:

| Row | Matrix says | Target says | Truth |
|---|---|---|---|
| `SPG-R1` | applied | `MAP_001:20` — *"PROPOSED, not applied… Annotation only"* | **half-applied**: `:94` + `:488` renamed the field, ~70 dependent sites did not |
| `SPG-R3` | applied | `GEO_001:13` — *"until `SPG-R3` is applied"* | **not applied** (annotation only — target is correct) |
| `SPG-R5` | applied | `CSC_001:25` — *"`SPG-R5` is PROPOSED, not applied"* | **not applied** (annotation only — target is correct) |

All three claims are false. Two are honest annotations mislabelled by the matrix; one is the dangerous
state — **a half-rename**, where the file now carries both vocabularies and nothing marks which sites
are outstanding. `ChannelTier` survives at **~91 sites across 22 files** (≈70 live, once the ~21
retirement-annotation sites in doc 36 / REC / `_LOCK` / changelog are excluded), including:

- **`_boundaries/02_extension_contracts.md:834-848`** — the `RealityManifest` **machine contract**, four
  fields keyed by the retired enum (`tilemap_templates`, `grid_size_per_tier`,
  `default_template_per_tier`, `skip_tier`). Its `grid_size_per_tier` default lists **4 values for a
  5-variant enum** — already underspecified before the rename, and `MapKind` has **7** kinds.
- `TMP_001` (10) · `TMP_004` (9) · `PL_005*` (8) · `16a_ruleset_field_classification` (a ruleset field
  key) · `cat_00_MAP` MAP-2 + MAP-26 and `cat_00_TMP` TMP-18, all marked ✅ delivered.
- Two acceptance criteria: **AC-MAP-3** (`match channel_tier` exhaustiveness over 5 variants — now
  vacuous, the enum is gone) and **AC-MAP-11**.

This is the arc's own rot, produced three commits ago and reported at first as a single stale line.

### The genuine design defect underneath

`map.tier_field_mismatch` (`MAP_001:202`, `:518`, AC-MAP-11 `:737`): *"Validator computes tier from DP
channel-tree at write-time and enforces equality with the row's `tier` field."*

Coherent under `ChannelTier` (*"matches DP channel hierarchy"*). **Incoherent under `MapKind`**, because
`DP-A13` states *"DP is agnostic to `level_name` semantics"* — the validator asks DP for a value DP is
forbidden to hold. Two individually-correct decisions jointly break a third: the
**adjacent-decision** shape from `docs/standards/non-vacuity.md`, live.

Note the symmetry, and the miss: `SPG-R2` was retired for pushing `MapKind` **into** DP. The same seam
had a consumer **depending on** DP knowing `MapKind`, and that pass did not look for it.

### Resolution — this is also the answer to `SPG-Q1`

`MapKind` is **authoritative on `map_layout`**, never derived from the channel tree. The denormalisation
reason survives (*"sum-type variant tag isn't directly indexable"*); the cross-check changes target:

- **retire** `map.tier_field_mismatch` (its premise is unobtainable),
- **add** `map.containment_violation` — the write path validates `allowed(parent.kind, child.kind)`
  against the containment matrix (`SPG-A3`),
- **AC-MAP-3** is restated over `MapKind`'s 7 variants; **AC-MAP-11** is replaced by a
  containment-violation scenario.

### Mechanism, so this class cannot recur

Extend `scripts/amendment-rot-gate.py` with **check D — retired-identifier containment**: an identifier
declared RETIRED by a sealed doc may appear only inside a retirement-annotation context. Armed with an
**empty allowlist** — i.e. the ~70 sites are fixed first, and any reappearance reds. An allowlist
seeded with today's 70 would be the *default-uncovered* anti-pattern (NV) and is explicitly rejected.

**Bite-test obligation (NV-2).** Reintroduce `ChannelTier` into one live site, watch check D go red,
paste the output, revert.

---

## 5 — Cluster D · The remaining open questions

| Q | Resolution | Basis |
|---|---|---|
| **SPG-Q1** | Containment matrix is **ruleset data**, engine-validated on write; `map_layout.kind` authoritative | `SPG-A2` already puts the whitelist in ruleset data; §4 above is the same work |
| **SPG-Q2** | The **structural** bound is `DP-Ch1`'s `depth ≤ 16`, which is a **DB CHECK constraint**, not prose — already mechanical. The **semantic** bound is the containment matrix itself: a reality that rejects `Universe → Universe` omits that cell. **No second bound is added** — a rule with no mechanism is what this repo has been paying to remove. | `06_data_plane/12_channel_primitives.md:66` + `:82` |
| **SPG-Q3** | Define `Transform` — currently **used at `36:416` and never defined**. It carries parent-relative `position` + `rotation` **and a per-node unit ratio**, which is the field a scale-skipping edge (`Universe → Domain`) lacks. `f64`, not `f32`: precision must survive accumulation across ≤16 levels — the 64-bit-world lesson doc 36 already cites from Star Citizen, and the same device as OpenUSD's per-layer `metersPerUnit`. | `SPG-A5` accumulation rule |
| **SPG-R10 + WSA-R19** | Land together — `EntityId::Place` (32) and `SpaceNode.holder` (36) are one seam from two directions. `EF_001:67` is still closed to 4 variants and `:131` says so honestly, so this is a real application, not a rot fix. Needs a `_boundaries` lock claim + boundary review, as `WSA-R19` itself requires. | doc 32 `:14-15` |

```rust
/// SPG-Q3 (design revised by `RD-2`/`RD-3` at design review).
/// Parent-relative placement of a node's frame inside its parent (SPG-A5).
pub struct Transform {
    /// Origin of this node's frame, in the PARENT's units.
    pub position: [f64; 3],
    /// Orientation of this node's frame relative to the parent's.
    pub rotation: [f64; 4],           // quaternion
}
```

There is **no single absolute coordinate space**, and `SPG-A5`'s accumulation therefore needs a
stopping condition — which it did not have:

```rust
/// Where accumulation STOPS. A node marked `Root` establishes its own coordinate
/// space; absolute position is defined only up to the nearest enclosing root.
/// A scale-skipping edge (`Universe -> Domain`) is a root boundary by
/// construction: you RE-BASE across it, you never accumulate through it.
pub enum FrameKind { Inherited, Root }
```

`SPG-Q3` asked what the coordinate contract is across an edge that skips scales, noting `SPG-A5` made
it *representable* but not *meaningful*. The answer is that such an edge carries **no** shared metric,
and pretending otherwise is what forced the discarded unit-ratio field. Star Citizen's split (64-bit
within a system; separate systems share no space) is the same device.

---

## 6 — Order, and why it is forced

```
A (scale)  →  B (storage)  →  C (rot + Q1)  →  D (Q2, Q3, R10+R19)
```

- **A before B**: the storage shape is sized by the scale; deciding storage first would size it against
  a stress fixture.
- **B before C**: `map_layout.kind` becoming authoritative (C) is what a projection rebuilt from a
  pinned baseline (B) reads. Reversing them re-opens `SPG-Q1` from the other side.
- **C before D**: `SPG-Q1` *is* the rot fix; `SPG-Q3`'s `Transform` lands on a `SpaceNode` whose
  `kind` field must already be settled.
- **Lock claims**: one claim covering `_boundaries/01_feature_ownership_matrix.md` +
  `02_extension_contracts.md` (C), one covering `EF_001`'s `EntityId` (D). `Owner:` set **before** the
  first edit, released after, evidence in the release note.

## 7 — Design review (Lead self-review, 2026-07-30) — four findings, three of them against my own plan

### `RD-1` — Cluster A's guard would break the crate's stated decoupling ⛔ plan revised

`GEO_GENERATOR_PLAN:3` is explicit: `crates/world-gen` is *"Decoupled from the LLM MMO RPG engine:
**no DP-kernel, no event sourcing, no aggregates, no foundation tier**."* Putting a GEO_001 band
constant inside the crate breaks exactly that, to enforce a rule that is not the crate's business.

Worse, it would be **near-vacuous**: the band value in the test would be a *copy* of the band value in
the doc, so the check passes forever while the two drift — the adjacent-decision shape again.

**Revised A1/A2.** The crate gains `WorldScale::cell_count()` only (it already has it). The guard moves
to a **design-lint check that joins two independently-maintained sources**: cell counts parsed from
`crates/world-gen/src/creative_seed.rs`, and the band + the production-scale declaration parsed from
`GEO_001`. It fails when a scale the doc calls production falls outside the band the doc declares. It
cannot be satisfied by editing one side alone, which is what makes it worth running.

### `RD-2` — Cluster B's storage medium was a guess, and the precedent is better ⛔ claim withdrawn

I wrote *"MinIO, on the ruleset-store pattern"*. Checked: the ruleset store is **not** in MinIO.
`crates/ruleset-loader/src/store.rs:81` is a **filesystem content-addressed store** — `<root>/<digest>.canon`,
append-only, `put` never overwrites, and `get` verifies the bytes hash to the requested digest:

> *"ruleset store **CORRUPTION**: {} contains bytes that hash to {} — refusing to serve a ruleset under
> a digest it does not match"*

and its own rationale answers the question I was about to re-litigate:

> *"Filesystem rather than Postgres **on purpose**: the store's contract is immutable bytes addressed by
> their own hash, which a directory satisfies exactly and a table only satisfies by convention. **Moving
> it behind an object store later changes this file and nothing else** — `put`/`get` is the whole surface."*

**So the world baseline store is not a new design — it is the same shape, already shipped and proven.**
`WorldBaselineStore::{put,get}`, digest-verified on read, filesystem now, object store later. And the
`DigestMismatch` branch is *already* the "hard error, never a silent divergence" that §3's honest
qualification demanded — it exists rather than needing to be argued for. MinIO stays what the stores
table says it is: archives and assets.

### `RD-3` — Cluster D's `Transform` budgets for a precision problem it should delete ⛔ design replaced

`parent_units_per_local_unit: f64` accumulated across `DP-Ch1`'s ≤16 levels does not survive contact
with real ratios: one light-year → metre edge is `9.46e15`, which alone consumes an `f64`'s ~15–16
significant digits. Two such edges and the accumulated absolute position is noise.

The prior art doc 36 already cites does not do this. Star Citizen uses 64-bit coordinates **within** a
system; separate systems **do not share a coordinate space** at all. OpenUSD's `metersPerUnit` is
per-layer metadata for *interchange*, not a factor composed through a deep chain.

**Replaced design: there is no single absolute coordinate space, and there does not need to be.**
Absolute position is defined only up to the nearest enclosing **coordinate root**. A scale-skipping
edge (`Universe → Domain`) *is* a root boundary: you **re-base**, you do not accumulate through it.
`SpaceNode` gains the root marker; `Transform` keeps `position` + `rotation` and drops the ratio.

This dissolves the problem instead of budgeting for it, removes a field, and makes `SPG-A5`'s
accumulation rule *total* — it now has a stated stopping condition, which it lacked.

### `RD-4` — Cluster C's sweep is not mechanical, so `logic=13` is light ⚠ carried

The rename is not 70 find-and-replaces. At least two sites need judgement rather than substitution:

- `grid_size_per_tier: HashMap<ChannelTier, GridSize>` should **not** become a 7-entry `MapKind` map —
  per `SPG-R9` only `Locale` carries a tilemap, so it collapses to a single `GridSize`.
- `skip_tier: BTreeSet<ChannelTier>` may lose its meaning entirely once tilemaps attach to one kind.

Those are simplifications, not renames. **Per the Anti-Skip rule, if this grows past the classification
during BUILD I stop, reclassify and announce** rather than absorbing it silently.

---

## 8 — Risks

| Risk | Handling |
|---|---|
| **Peer session shares the index** — this arc already lost a commit label to it | Commit by **pathspec in the same shell breath** as the `add`; never `git add -A` |
| Completing `SPG-R1` touches CANDIDATE-LOCK `MAP_001` | Lock claim + the retirement note at `:20` is corrected in the same edit, so the file never again disagrees with itself |
| Check D's allowlist tempts a shortcut | Rejected in writing (§4). Empty allowlist or the gate is theatre |
| `f32` determinism assumed rather than proven | Stated as a limit in doc 37, not designed around; bytes are the SSOT, regeneration is audit-only |
