# 37 — World Data Storage (design)

> **Prefix:** `WDS-*` (registered 2026-07-30; axioms `WDS-A1..A8`, decisions `WDS-D1..D5`,
> findings `WDS-F1..F3`, open `WDS-Q1..Q2`).
>
> **What this doc is for.** Doc 36 settled the *shape* of space (`MapKind`, the containment matrix,
> `SpaceNode`). It says nothing about where that space's **bytes live**. This doc answers exactly that
> one question, and it exists because the answer already shipped in three mutually-unaware forms:
> `GDA-D4` says seeding emits an event per cell, `GEO_WORLD_TIER_REDESIGN` §9 Q3 deferred the question
> entirely, and `crates/world-gen` was built as a pure function that is *"decoupled… no event sourcing,
> no aggregates"*.
>
> **Origin.** PO objection, 2026-07-30, in these words: *"you cannot make first data build from event
> sourcing / event sourcing only accumulate data."* That is correct, and the rest of this doc is what
> checking it against the corpus produced.

---

## 1 — The finding

### `WDS-F1` — `GDA-D4` does not distinguish authored content from generated bulk

`GDA-D4` (sealed, [`17` §4](17_game_data_architecture.md)):

> *"Seeding emits events, never direct aggregate writes. `PlaceBorn` / `LayoutBorn` / `TilemapBorn` /
> `GeographyBorn` / `EntityBorn`, per EVT-A3… §12R.2's 'create region aggregate' would bypass the log
> and leave a reality whose first state has no causal record — **unreplayable from t=0**."*

The **reason is right**. The **mechanism is right for one of the two kinds of content it covers, and
wrong for the other**, and nothing in the spec names the distinction:

| | **Authored** content | **Generated** content |
|---|---|---|
| Source | a human/LLM decided it — the manifest's `places`, `canonical_actors`, `canonical_settlements` | a deterministic function produced it — `generate(seed, CreativeSeed) → WorldMap` |
| Volume | sparse — tens to hundreds | bulk — one row per cell, ×16 384 at `Megaplanet` |
| Is an event per item a *record*? | **yes** — the event *is* the only account of a decision | **no** — it is a *transcript* of a computation whose inputs are 32 bytes |
| Can it drift from its source? | n/a — it has no other source | **yes**, and that is the danger: 33 k events can disagree with the generator; a digest cannot |

`GDA-D4` applied to generated bulk produces ~33 k genesis events at the production scale
(`GEO-D14`) for a payload that **regenerates in ~1 s**, and produced ~1 M events / >1 GB of
`event_log` at the stress scale before `GEO-D15` removed it from the game path.

### `WDS-F2` — `RBS-Q1` saw half of this, and mis-classified it

[`18` §8](18_reality_bootstrap.md) `RBS-Q1` asks: *"Seeding budget for a `Megaplanet`… ~16k `PlaceBorn`
+ ~16k `LayoutBorn` + tilemaps… Is there a scale cap on synchronous authorability, or does a Megaplanet
simply take hours and report progress?"* — and classifies itself **"product + measurement"**.

It is neither. It is a **category** question. "Hours, with a progress bar" is the answer to *"how do we
survive emitting 33 k events?"*; the question worth asking is *"why are we emitting them at all?"*
`RBS-Q1` is **dissolved**, not answered — see `WDS-A3`.

### `WDS-F3` — the repo already holds the principle, one layer up

[`07_event_model/02_invariants.md`](07_event_model/02_invariants.md) `EVT-A9`:

> *"EVT-T5 Generated events MUST use **deterministic RNG** seeded from a stable causal-ref… Wall-clock
> time, system entropy, or any other non-deterministic source is FORBIDDEN inside generation rules.
> **Replay reproduces same output given same input event log.**"*

The event model already accepts that generated content is defined by **its seed plus determinism**, not
by the enumeration of its output. `crates/world-gen` is precisely that shape and was built independently:
a pure `generate(seed, CreativeSeed) → WorldMap`, a `content_hash` over the result, and blake3 pins in CI
that fail if the bytes move. So emitting the output as 33 k events is **redundant with `EVT-A9`**, not
required by it.

---

## 2 — Axioms

### `WDS-A1` — Generated world content is CONTENT, not HISTORY

The `event_log` is the SSOT for *what happened*. A generated baseline is not something that happened —
it is the **initial condition** the history is written against. It enters the world as a **pinned
immutable artefact**, and the log carries only **divergence from it**.

This is Minecraft's model (a seed plus the chunks a player actually changed), and it is what doc 36
already reaches for with `SPG-A14`'s `definition: Option<DefRef>` — OpenUSD's deferred *payload* — and
`SPG-A12`'s `Materialization` ladder. Doc 36 had the vocabulary; it had no store to point it at.

### `WDS-A2` — A pinned digest is a causal record, and a stronger one than the events

`GDA-D4`'s requirement — *nothing enters the world without a causal record* — is **satisfied**, not
waived. The record is `(seed, CreativeSeed, generator_version, content_hash)`.

It is stronger than 33 k events for a reason that is not about size: **the events can be wrong.** A
`*Born` stream is a second, hand-maintained representation of what the generator produces, and nothing
forces the two to agree. A `content_hash` cannot disagree with its own bytes — verifying it is a hash
comparison, and `RulesetStore` already refuses to serve on mismatch. Replacing 33 k mutable
assertions with one verifiable one **raises** the integrity guarantee.

### `WDS-A3` — Genesis is `O(1)` in cells, not `O(cells)`

One event, at the point the baseline is adopted:

```rust
/// EVT-T4 System. Emitted once per world node at seeding, in place of the
/// per-cell `GeographyBorn` / `PlaceBorn` / `LayoutBorn` storm.
struct WorldBaselinePinned {
    node_id: NodeId,              // the MapKind::World node this baseline realises
    content_hash: [u8; 32],       // blake3 of the canonical WorldMap bytes
    seed: u64,
    creative_seed_hash: [u8; 32], // the authored direction, already in GeographyBorn
    generator_version: u32,       // pinned; see WDS-A6
    cell_count: u32,              // must satisfy GEO_001 cell_count_out_of_bounds
}
```

`RBS-Q1`'s *"or does a Megaplanet simply take hours"* resolves to **~1 s and one event**. `RBS-A5`'s
deterministic idempotency keys and `RBS-D3`'s `(phase, item_index)` checkpointing keep their meaning for
the **authored** phases, which is where they were always load-bearing.

> **Authored content is untouched.** `PlaceBorn` for a named palace, `EntityBorn` for a canonical NPC,
> `MemberJoined` at `RBS-D2`'s membership phase — all unchanged. `WDS-A1` narrows `GDA-D4`; it does not
> replace it. The `*Born` events that vanish are exactly the ones whose payload was a copy of a
> computation.

### `WDS-A4` — The store is the one `RulesetStore` already is

Not a new design. [`crates/ruleset-loader/src/store.rs`](../../../crates/ruleset-loader/src/store.rs)
is a **content-addressed store** — `<root>/<digest>.canon`, `put` idempotent and never overwriting,
`get` verifying that the bytes hash to the digest requested:

> *"ruleset store **CORRUPTION**: {} contains bytes that hash to {} — refusing to serve a ruleset under
> a digest it does not match"*

and its own rationale pre-answers the medium question:

> *"Filesystem rather than Postgres **on purpose**: the store's contract is immutable bytes addressed by
> their own hash, which a directory satisfies exactly and a table only satisfies by convention. **Moving
> it behind an object store later changes this file and nothing else** — `put`/`get` is the whole surface."*

`WorldBaselineStore` is that file with a different payload type. In particular the `DigestMismatch`
branch **already is** the hard-fail this design needs (`WDS-A7`); it did not have to be argued for.

> **`WDS-D1` — filesystem now, object store later, and MinIO is not the answer today.** The stores table
> in [`17` §2](17_game_data_architecture.md) gives MinIO *"archived realities, assets"*. A live baseline
> is neither. Following the shipped precedent keeps one story for "immutable bytes addressed by their
> hash" instead of two.

### `WDS-A5` — Five stores, one authority each

| What | Where | Authority | Lifetime |
|---|---|---|---|
| `(seed, CreativeSeed, generator_version)` | reality row, meta registry | **provenance** — reproducible, auditable | forever |
| `WorldMap` canonical bytes, keyed by `content_hash` | **`WorldBaselineStore`** (`WDS-A4`) | **SSOT for the t=0 baseline** — immutable | never pruned while referenced |
| `space_node` tree · place / geo projection rows | per-reality Postgres | **derived** — rebuildable from baseline + log | rebuildable |
| divergence after t=0 | `event_log` | **SSOT for history** (`GDA-A1`) | forever (archive 90d) |
| live state while Hot | island memory | authoritative while Hot (`DP-X1` T1) | dies with the island |

Read top to bottom, that is one sentence: *provenance explains the baseline, the baseline explains t=0,
the log explains everything since, and memory is where it is actually happening.*

### `WDS-A6` — The generator version is part of the pin, and its code may not be deleted

`content_hash` has **already been re-baselined once** on an intentional algorithm change — the sphere
migration ([`GEO_WORLD_TIER_REDESIGN`](GEO_WORLD_TIER_REDESIGN.md) Phase 1: *"`content_hash`
re-baselined intentionally (sphere geometry ⇒ different bytes)"*). So `(seed, CreativeSeed)` alone does
**not** identify a world; `(seed, CreativeSeed, generator_version)` does.

Consequence, inherited verbatim from the ruleset store's rule (*"never pruned while referenced"*): **a
generator version may not be removed while any reality pins it.** This is a real, ongoing cost and it is
stated here so it is not discovered later.

### `WDS-A7` — The bytes are the SSOT. Regeneration is the AUDIT path, never the SERVING path

This is the axiom that changes the design's conclusion, and it is a limitation rather than a feature.

The generator uses `f32` noise (`noise.rs` — Perlin/fBm/ridged, `gradient_noise_3d`). **Cross-platform
floating-point determinism is not guaranteed**, and the blake3 pins in CI hold only on the CI platform.
A server on a different architecture could regenerate *slightly* different bytes from the same seed.

Therefore:

1. **Store the bytes.** The seed alone is not sufficient for a live reality.
2. **Verify on read** against `content_hash` — `RulesetStore`'s existing `DigestMismatch` shape.
3. **A mismatch is a hard error.** Never a silent substitution, never a "close enough" regeneration.
4. **Regeneration is for audit** — proving a year-old world was what it claimed — not for serving, and
   an audit regeneration that mismatches is a *finding*, not a repair.

> **`WDS-D2` — we do not attempt bit-deterministic cross-platform floats.** Soft-float or fixed-point
> would buy portable regeneration at the cost of rewriting the generator's numeric core. Not worth it:
> storing 15 MB is cheap, and `WDS-A7`'s discipline gets the same integrity guarantee without the
> rewrite. Recorded as a conscious won't-fix so it stops resurfacing.

### `WDS-A8` — Two thirds of the payload is derivable, and we are storing it anyway (for now)

Measured 2026-07-30 at `Continent` scale, compact JSON:

| Component | Bytes | Share | Why it is derivable |
|---|---:|---:|---|
| `vertex_polygon` | 1 907 232 | 50.1 % | spherical Voronoi of the centres |
| `center` | 301 336 | 7.9 % | `fibonacci(n) · R(seed)` — `mesh.rs`: *"deterministic given `n`"*, and its own test asserts the rotation is *"the **only** source of seed dependence here"* |
| `neighbors` | — | ~9 % | Quickhull adjacency over the centres |
| `is_coast` | — | <1 % | `elevation ≥ sea_level ∧ ∃ neighbour < sea_level` |
| **derivable total** | **2 573 766** | **67.6 %** | |
| irreducible | 1 232 363 | 32.4 % | `elevation`, `climate`, `biome`, `river_flux`, 7 region ids |

Packed, the irreducible part is ~**20 B/cell** → ~320 KB at `Megaplanet`, against ~15 MB stored.
Measured vertices per cell: **exactly 6.00** — the Euler floor for a sphere tessellation, so "less
detailed polygons" has only one lever, cell count (which is `GEO-D14`).

> **`WDS-D3` — PO chose to store everything and strip nothing, 2026-07-30.** Simplicity now; ~15 MB per
> world is not a constraint at `GEO-D14`. The measurement is **recorded with a wake-up trigger, not
> dropped**: deferral `D-WORLD-PAYLOAD-DERIVABLE`, whose trigger is *"the first commit in which world
> payload size or wire bandwidth is measured as a constraint."* Stripping would also require Quickhull
> on the client and would inherit `WDS-A7`'s float problem on the *read* path, where it is worse — a
> second reason the deferral is the right call and not merely the easy one.

---

## 3 — What this changes elsewhere

| Target | Change | Row |
|---|---|---|
| `17` `GDA-D4` | **narrowed**, not retired: events for authored content, a pinned baseline for generated bulk | `WDS-R1` |
| `18` `RBS-Q1` | **dissolved** — a category error, not a budget question (`WDS-F2`) | `WDS-R2` |
| `18` §3.2 phase DAG | the geometry phase emits **one** `WorldBaselinePinned`, not per-cell `GeographyBorn` | `WDS-R3` |
| `GEO_001` §4 | `GeographyBorn`'s per-continent emission is superseded for the generated layer; `creative_seed_hash` + `generator_pipeline_version` survive **into** the pin | `WDS-R4` |
| `07_event_model` | register `WorldBaselinePinned` as an **EVT-T4 System** sub-type owned by `GEO_001` | `WDS-R5` |
| `36` `SPG-A12`/`A14` | `Materialization` and `DefRef` gain a store to resolve against — `WDS-A4` is where a `DefRef` points | `WDS-R6` |
| `_boundaries` | `WDS-*` prefix row; `WorldBaselineStore` is **not** an aggregate — no aggregate row | `WDS-R7` |

⚠ **`WDS-R1..R7` are PROPOSED, not applied** — the same discipline as docs 32 and 36, and this doc is
being written in an arc whose *first* finding was that a matrix claimed three amendments applied when
two had never been touched and one was half-done. No row here is marked applied until its target is
opened and edited.

> **⚠ `WDS-A5` and `WDS-A6` state RETENTION invariants that have NO MECHANISM, and this note is the
> only honest form that can take today.** *"Never pruned while referenced"* and *"a generator version may
> not be deleted while any reality pins it"* are exactly the shape this corpus has learned to distrust —
> a rule with no check. They are **not** mechanisable yet, for the NV-2 reason: **the subject does not
> exist.** There is no `WorldBaselineStore`, no pruner, and no `generator_version` column, so a check
> would have no possible violation and would report coverage it does not have.
>
> **Trigger, named so it is not re-discovered:** the first commit that adds a **pruner or retention job**
> touching either store. At that point the bite test is stated in advance — *prune a digest a live
> reality still pins, and the job must refuse* — and the same for deleting a pinned generator version.
> Tracked as `D-WORLD-BASELINE-RETENTION`. The ruleset store is the precedent to copy: its `put` already
> refuses to overwrite and its `get` already refuses on digest mismatch, so retention is the one property
> it does **not** yet enforce either.

---

## 4 — Open

| # | Question |
|---|---|
| **WDS-Q1** | **Who writes the baseline into the store, and when?** `RBS-A3`'s reality-scoped writer lease covers *event* emission. A `put` into a content-addressed store is not an event and needs no lease — but it does need an owner and a failure mode when the store and the log disagree about whether the reality is seeded. |
| **WDS-Q2** | **Does a fork share its parent's baseline blob?** Content addressing says yes for free (`RBS-A1`'s `Ancestry` case, and *"200 realities forked from one preset with no"* duplication is the ruleset store's stated payoff). But `GEO-D7`'s *"inherit by reference; deltas don't cascade"* was written about `GeographyDelta`, not about a shared immutable baseline, and the two need to be stated together. |

> Deliberately **not** open: whether the store is a directory or an object store (`WDS-D1` — one file
> changes), whether to chase float determinism (`WDS-D2` — won't-fix), and whether to strip the
> derivable payload (`WDS-D3` — deferred with a trigger). Each is recorded so it stays decided.
