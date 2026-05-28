# GEO — huge-scale benchmark + `Gigaplanet` scale

> **Status:** DESIGN → BUILD. Task size **L** (creative_seed.rs + main.rs +
> Cargo.toml + new benches/ + structure.rs tests + this plan).
> Default v2.2 workflow, human-in-loop. CLARIFY sign-off (3 PO questions):
> criterion benchmark · push past the 16,384 cap to ~500K cells · render a
> showcase huge map. The geo-type extension (Earth + fantasy terrain) is a
> **separate later discussion** — not this task.

## 1 — Problem

The largest `WorldScale`, `Megaplanet`, is a 128² grid ≈ 16,384 cells — the PO
notes it "feels like a zone, not a big world map". There is also no benchmark
harness, so generator performance is unmeasured. This task adds a genuinely
huge scale and a criterion benchmark, and renders a showcase map — a concrete
performance + visual baseline going into the geo-type discussion.

## 2 — Design

### A. `WorldScale::Gigaplanet` (`creative_seed.rs`)

A sixth `WorldScale` variant — `Gigaplanet`, grid side **708**:
`cell_count = (g-2)² + 4(g-1) = 706² + 4·707 = 501,264` cells (~30× Megaplanet).

- `grid_side()` → `708`; `cell_count()` formula is unchanged (it already
  derives from `grid_side`).
- `tag()` → `5` (stable content-hash discriminant; Megaplanet is `4`).
- The GEO_001 cell-count band `[1024, 16384]` is widened — the doc comment and
  `cell_counts_within_bounds` now allow up to the new `Gigaplanet` count.
- Adding an enum variant is forward-compatible for serde: old config JSON never
  named `Gigaplanet`; new JSON may. No existing scale's `grid_side`/`tag`
  changes, so **no existing map's `content_hash` shifts**.

The `match self` arms in `grid_side`/`cell_count`/`tag` are exhaustive — the
compiler flags the new variant in each.

### B. CLI (`main.rs`)

`ScaleArg` gains `Gigaplanet` + its `From<ScaleArg>` arm, so
`world-gen generate --scale gigaplanet …` works.

### C. Criterion benchmark (`Cargo.toml` + `benches/generate.rs`)

- `Cargo.toml`: `criterion = "0.5"` as a `[dev-dependencies]`; a
  `[[bench]] name = "generate", harness = false` entry.
- `benches/generate.rs`: a criterion group timing `generate(seed, &cs)` across
  every `WorldScale`, `cs` = `CreativeSeed::default()` varied only by scale.
  `generate` at `Gigaplanet` takes seconds, so the group sets
  `sample_size(10)` (criterion's minimum) and a generous `measurement_time`;
  the small scales tolerate that fine. A second group times `relief_image`
  rendering at the largest scale (the other heavy path).
- Run on demand via `cargo bench` — not wired into CI.

### D. Showcase render (VERIFY artifact)

At VERIFY, render a `Gigaplanet` map with the most Earth-like config the
current types allow (`Coastal` — a large continent with a real coastline and
open ocean) to large relief + biome PNGs. The render is a one-shot artifact in
`target/` (git-ignored) — a baseline to look at, not a committed file.

## 3 — Files

| # | File | Change |
|---|------|--------|
| 1 | `crates/world-gen/src/creative_seed.rs` | `Gigaplanet` variant + `grid_side`/`tag` arms + band doc; fix `cell_counts_match_design_table` + `cell_counts_within_bounds` |
| 2 | `crates/world-gen/src/main.rs` | `ScaleArg::Gigaplanet` + `From` arm |
| 3 | `crates/world-gen/Cargo.toml` | `criterion` dev-dep + `[[bench]]` entry |
| 4 | `crates/world-gen/benches/generate.rs` | **NEW** — criterion harness |
| 5 | `crates/world-gen/tests/structure.rs` | **NEW** dedicated `gigaplanet_*` coherence + determinism test (`#[ignore]` — 501k-cell, run with `--ignored`). *Not* added to `cell_count_exact_per_scale` — its `(1024..=16384)` bound + per-scale generate would just duplicate this test's coverage at +10s. |
| 6 | `crates/world-gen/src/author.rs` | `world_scale` schema enum gains `Gigaplanet`; `schema_enums_match_rust_enums` count 5 → 6 (the documented schema↔enum sync contract) |
| 7 | `docs/plans/2026-05-18-geo-huge-scale-benchmark.md` | this plan |

**`structure.rs` `SCALES` is left at 5** — the 134-second `land_coherence_per_profile`
sweep must not pull in a 500K-cell scale (it would balloon to many minutes).
The new scale's correctness is covered by its own single-seed test + the
benchmark exercising `generate` at that scale.

## 4 — Acceptance criteria

1. `WorldScale::Gigaplanet` exists; `cell_count()` = 501,264; `grid_side()` =
   708; `tag()` = 5.
2. `generate()` at `Gigaplanet` produces a valid map — exact cell count, every
   layer populated, and it verifies its own `content_hash`.
3. `generate()` at `Gigaplanet` is deterministic — byte-identical across runs.
4. The five existing scales are untouched — cell counts, hashes and every
   existing test stay green.
5. `cargo bench` runs `benches/generate.rs` and reports `generate` timing for
   each scale.
6. CLI `--scale gigaplanet` generates a map.
7. VERIFY: a `Gigaplanet` showcase map renders to relief + biome PNGs.

## 5 — Build order

1. `creative_seed.rs` — variant + arms + the two test fixes.
2. `main.rs` — `ScaleArg`.
3. `structure.rs` — cell-count row + dedicated `gigaplanet` test.
4. `Cargo.toml` — criterion dev-dep + `[[bench]]`.
5. `benches/generate.rs` — the harness.
6. VERIFY — **first** a timing probe: one CLI `generate --scale gigaplanet`,
   wall-clock it. If `generate` is catastrophically slow (an unspotted O(n²)
   surfacing only at 500K), STOP and report — that is a finding for the
   geo-type discussion, not something to absorb here. If it is reasonable
   (seconds–low minutes), proceed: `cargo test`, `cargo bench`, render the
   showcase map; record the timings.
