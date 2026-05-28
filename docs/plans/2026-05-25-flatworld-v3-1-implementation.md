# Plan — Flatworld v3.1 Implementation (v3.1a foundation + v3.1b 3 algos)

> **Spec:** [`../specs/2026-05-25-flatworld-v3-1-shape-dispatcher.md`](../specs/2026-05-25-flatworld-v3-1-shape-dispatcher.md).
> **Roadmap parent:** [`./2026-05-25-phase-a-v3-roadmap.md`](./2026-05-25-phase-a-v3-roadmap.md).
> **Workflow:** v2.2 (human-in-loop). Size = L per phase. State machine: `python scripts/workflow-gate.py`.
> **Branch:** `geo-generator-amaw`. Commits: 2 separate (v3.1a foundation; v3.1b algos).

---

## Strategy

v3.1a guarantees byte-identical render — small diff (`shape/` module + thin refactor of `flatworld::generate` + `Plate.shape_kind` field). PO can sanity-check that NO geometry changed before the v3.1b ship introduces actual visual variety.

v3.1b adds 3 algorithms + `Weighted` dispatch + flips default. Expected ~+1300 LOC across `shape/spine.rs`, `shape/polar.rs`, `shape/csg.rs`, eval-adapt script, tests.

---

## v3.1a — Foundation (~4-5h)

### Chunks

#### C1 — Module skeleton + types (~45min)
1. `crates/world-gen/src/shape/mod.rs` — pub mod declarations + re-exports.
2. Define `ShapeKind` enum (8 variants), `ShapeContext` struct, `ShapeGenerator` trait.
3. `Polygon` type alias re-export (matches `flatworld::Polygon`).
4. Update `crates/world-gen/src/lib.rs` — `pub mod shape;`.
5. Unit test: `shape_kind_all_variants_serialize` (enum has 8 variants, serialise OK).

**Verify:** `cargo build --workspace` clean. `cargo test --workspace` green (no new tests fail; existing 208 still pass).

#### C2 — Registry + dispatch (~1h)
1. `shape/dispatch.rs` — `ShapeRegistry` (BTreeMap for deterministic kinds order), `DispatchMode::{Random, Fixed}`, `select()` impl with single-kind short-circuit.
2. `ShapeRegistry::engine_default()` — placeholder, returns empty until C3 registers Ellipse.
3. Unit tests:
   - `registry_register_get_roundtrip`
   - `dispatch_fixed_returns_kind_no_rng`
   - `dispatch_random_single_kind_no_rng_consumption` (assert `rng.next_u32` call count unchanged after `select`)
   - `dispatch_random_multi_kind_uniform` (with 4 fake generators, 10k samples ~uniform)

**Verify:** new tests pass.

#### C3 — Extract EllipseGenerator (~1h)
1. `shape/ellipse.rs` — `EllipseGenerator` struct + `ShapeGenerator` impl.
2. Move `EDGE_NOISE_AMP/FREQ/OCTAVES`, `JITTER_RESIDUAL_SCALE`, `lerp` from `flatworld.rs` to `shape/ellipse.rs` (or `shape/mod.rs` if shared). Keep `pub(crate)` for back-references.
3. Body is straight port of `flatworld::generate` lines 488–565 — verify per-call RNG ordering matches.
4. Update `ShapeRegistry::engine_default()` to register Ellipse.
5. Unit tests:
   - `ellipse_kind_is_ellipse`
   - `ellipse_centre_inside_polygon` (point-in-polygon at ctx.center returns true)
   - `ellipse_deterministic` (same seed → identical polygon)
   - `ellipse_rng_consumes_known_count` (after `generate` with nv=24, rng advanced by `4 + 2*nv = 52` calls — pins the contract)

**Verify:** new tests pass. `cargo build` clean.

#### C4 — Schema additive + flatworld refactor (~1h)
1. `flatworld.rs` — add `pub shape_kind: ShapeKind` to `Plate` struct.
2. Rewrite the plate-construction closure in `flatworld::generate` to:
   - Build `ShapeContext` from collected per-plate values (rank, center, salts, vertex range, jitter).
   - Call `dispatcher.select(&registry, &ctx, &mut rng)`.
   - Call `registry.get(kind).generate(&ctx, &mut rng)`.
   - Set `Plate.components = polys; Plate.shape_kind = kind`.
3. Add `FlatParams::plate_dispatch: Option<DispatchMode>` (default `None` = `Fixed(ShapeKind::Ellipse)`).
4. Verify motion/zone RNG streams unaffected — they're separate `mrng`/`zrng` streams.

**Verify:**
- `cargo test --workspace`: all 208 + new tests green.
- Byte-identical pin: add `flatworld_v3_0_byte_identical_seeds_1_7_13_42` test that runs `generate(seed=N)` for N in {1,7,13,42}, hashes the resulting `FlatWorld` polygon vertices + zone_sites + velocities, asserts equal to known v3.0 hashes (capture from current f022cf82 head).

#### C5 — Visual + eval verify (~45min)
1. Render seeds 1, 7, 13, 42 via existing render harness (`cargo run -p world-gen -- --seed N --out eval/compare-phase-a/v3.1a-foundation/`).
2. `diff` PNGs against committed v3.0 PNGs (`eval/compare-phase-a/v3.0/`). MUST be identical bytewise.
3. Run climate eval: `python scripts/climate_eval.py --baseline eval/baselines/v5.2.json`. Composite must equal v5.2 mean 85.24.

**Acceptance:** all PNGs match v3.0; eval composite identical to v5.2.

### v3.1a — Phase gate evidence (for workflow-gate.py complete)

| Phase | Evidence |
|-------|----------|
| design | "spec + plan written, byte-identical mechanism specified" |
| review-design | "self-review per Lead role; R1/R2 mitigations confirmed" |
| plan | "5 chunks decomposed, byte-identical snapshot test pinned" |
| build | "5 chunks done; new shape/ module + Ellipse extracted; flatworld routes through registry" |
| verify | "cargo test+clippy green; PNGs bytewise identical to v3.0 at seeds 1,7,13,42; eval composite 85.24 matches v5.2 exactly" |
| review-code | "self-review per Lead: RNG order preserved; clippy 0 new; no scope creep beyond spec §2 v3.1a" |
| qc | "all spec §5.1 acceptance criteria checked off" |
| post-review | "summary presented to PO + visual confirm byte-identical" |
| session | "SESSION_PATCH updated with v3.1a entry" |
| commit | "single commit: feat(flatworld): v3.1a shape dispatcher foundation (byte-identical)" |
| retro | "lesson: bit-exact extraction requires snapshot test on every algo with RNG dependencies" |

---

## v3.1b — 3 Algorithms + Weighted Dispatch (~12-15h)

### Chunks

#### B1 — geo-clipper crate add + spike (~1h)
1. `crates/world-gen/Cargo.toml` — add `geo-clipper = "0.8"` (verify latest from crates.io).
2. `cargo tree -p world-gen --depth 1` — count new transitives. If >5, evaluate alternatives:
   - `geo-booleanop = "0.3"` (BentleyOttmann; depends on `geo`)
   - hand-rolled Sutherland-Hodgman (union-only; loses Ring/Difference)
3. Write throwaway example in `examples/csg_spike.rs`: union of 2 ellipses, render to text-grid. Confirm API ergonomics (f32 vs i64 fixed-point).
4. Delete spike after confirming.

**Verify:** `cargo build` green; crate dep documented in plan.

#### B2 — BezierSpine implementation (~3h)
1. `shape/spine.rs` — `BezierSpineGenerator`, `BezierTemplate` enum, template tables.
2. Bezier eval helpers: `bezier_point`, `bezier_tangent`, `bezier_normal` (no external dep — 4-control-point cubic is 1 line each).
3. Template tables: SCurve / Hook / Boot (per spec §4.6.1).
4. Pick template via `hash(ctx.seed)` → mod 3.
5. Build polygon: 32 stations, 2 boundary points each = 64 vertices.
6. Apply scale-to-envelope, rotation, translation, per-station jitter.
7. Register in `ShapeRegistry::engine_default()`.
8. Tests:
   - `bezier_kind_is_bezier_spine`
   - `bezier_each_template_centre_inside`
   - `bezier_deterministic`
   - `bezier_scale_within_envelope`
   - `bezier_polygon_is_simple`

#### B3 — Polar / Superformula implementation (~2.5h)
1. `shape/polar.rs` — `PolarGenerator`, `PolarTemplate` enum.
2. Superformula helper (handles signs / |…| inside power); Cardioid bypass; Rose with |cos| guard.
3. Template tables: Pentagon / Cardioid / Rose / Oval.
4. Self-intersect guard: winding-number check; retry with `jitter*0.5` max 3 times; fallback to Oval.
5. Register in `engine_default`.
6. Tests:
   - `polar_kind_is_polar`
   - `polar_each_template_centre_inside`
   - `polar_pentagon_approx_5_fold`
   - `polar_cardioid_min_radius_at_pi`
   - `polar_rose_simple_after_retry`
   - `polar_deterministic`

#### B4 — Boolean CSG implementation (~3h)
1. `shape/csg.rs` — `BooleanGenerator`, `BooleanTemplate` enum, `safe_boolean` wrapper.
2. f32 ↔ geo-clipper coordinate converter helpers if needed.
3. Sub-ellipse builder (clean ellipsoid, no fbm — `n=24` vertices).
4. Templates: Ring, EllipseUnion, EllipseDifference, WedgeCut.
5. Arc-length resampler `resample_arclength(poly, target_n)` for final vertex count.
6. `largest_component` picker for multi-component clip output.
7. Register in `engine_default`.
8. Tests:
   - `boolean_kind_is_boolean`
   - `boolean_ring_area_smaller_than_outer`
   - `boolean_union_area_lt_sum`
   - `boolean_difference_area_lt_minuend`
   - `boolean_each_template_centre_inside_or_acceptable_fallback`
   - `boolean_safe_fallback_on_empty_result`
   - `boolean_polygon_is_simple_after_resample`

#### B5 — DispatchMode::Weighted + flip default (~1.5h)
1. `shape/dispatch.rs` — add `DispatchMode::Weighted(BTreeMap<SizeRank, Vec<(ShapeKind, f32)>>)` variant. Use `Vec<(kind, weight)>` instead of `HashMap` so iteration is deterministic.
2. `select`: lookup `ctx.size_rank` → list → cumulative weight + `rng.next_f32()` selection. `debug_assert!((weights.sum() - 1.0).abs() < 1e-3)`.
3. `engine_v3_1b_weights() -> BTreeMap<SizeRank, Vec<(ShapeKind, f32)>>` ships with table in spec §4.6.4.
4. Flip `flatworld::generate` default: `FlatParams::plate_dispatch` defaults to `Some(DispatchMode::Weighted(engine_v3_1b_weights()))` (or `None` → use `engine_v3_1b_weights()` at runtime).
5. Tests:
   - `weighted_weights_sum_to_one_per_rank`
   - `weighted_distribution_matches_table` (10k samples per rank within 2% of expected)
   - `weighted_selects_only_registered_kinds`
   - `flatworld_default_uses_weighted` (build with default params, sample 12-plate world, assert ≥1 plate has non-Ellipse `shape_kind` at seeds 7/13/42)

#### B6 — Eval framework adaptation (~2h)
1. `scripts/climate_eval.py` — `compute_lat_banding` rewrite to per-component area distribution.
2. Sanity check: run on v3.0 worlds (Ellipse-only), confirm new metric within ±5% of old centroid-count metric (the "no-elongation baseline" check from spec §4.8 / R9).
3. Run full eval on v3.1b worlds at seeds 1/7/13/42. Capture composite. Commit `eval/baselines/v5.3.json`.
4. No `±5` gate — visual review approves.

#### B7 — Visual render + PO review (~30min + wait)
1. `cargo run -p world-gen -- --seed N --out eval/compare-phase-a/v3.1/` for N in {7, 13, 42}.
2. Generate side-by-side comparison HTML / markdown: v3.0 vs v3.1.
3. **STOP — present to PO. Wait for approval.** Per PO directive Q7 (visual review per phase).
4. If PO requests weight tuning: iterate B5 step 3 weight table, re-render, re-present.

### v3.1b — Phase gate evidence (for workflow-gate.py complete)

| Phase | Evidence |
|-------|----------|
| design | "covered in v3.1a spec; PO confirmed at start of v3.1b kickoff" |
| review-design | "minimal — already reviewed under v3.1a" |
| plan | "7 chunks (B1-B7) decomposed" |
| build | "7 chunks done; 3 algos registered; Weighted dispatch flipped on" |
| verify | "cargo test+clippy green; 100-seed simple-polygon assertion green; eval composite reported with adapted lat_banding" |
| review-code | "self-review: per-algo determinism + RNG isolation; geo-clipper failure modes wrapped; no scope creep" |
| qc | "spec §5.2 criteria all checked; eval baselines/v5.3.json present" |
| post-review | "PNGs presented to PO; approval received: <quote>" |
| session | "SESSION_PATCH updated with v3.1b entry + new v5.3 eval baseline" |
| commit | "single commit: feat(flatworld): v3.1b Bezier/Polar/Boolean + Weighted dispatch (+geo-clipper dep)" |
| retro | "lessons: geo-clipper API quirks; per-rank weight tuning iteration count; eval-metric rewrite agreement test" |

---

## Files touched (combined v3.1a + v3.1b)

### v3.1a
- NEW `crates/world-gen/src/shape/mod.rs` (~80 LOC)
- NEW `crates/world-gen/src/shape/dispatch.rs` (~90 LOC for v3.1a; +50 in v3.1b for Weighted)
- NEW `crates/world-gen/src/shape/ellipse.rs` (~70 LOC extracted)
- MOD `crates/world-gen/src/lib.rs` (+1 line: `pub mod shape;`)
- MOD `crates/world-gen/src/flatworld.rs` (Plate struct +1 field; generate() refactor; constants moved to shape/ellipse.rs)
- NEW `tests/byte_identical_v3_0.rs` (or inline) — content_hash pins per seed
- NEW `docs/specs/2026-05-25-flatworld-v3-1-shape-dispatcher.md` (this spec)
- NEW `docs/plans/2026-05-25-flatworld-v3-1-implementation.md` (this plan)

### v3.1b
- MOD `crates/world-gen/Cargo.toml` (+geo-clipper dep)
- NEW `crates/world-gen/src/shape/spine.rs` (~180 LOC)
- NEW `crates/world-gen/src/shape/polar.rs` (~140 LOC)
- NEW `crates/world-gen/src/shape/csg.rs` (~220 LOC)
- MOD `crates/world-gen/src/shape/dispatch.rs` (+Weighted variant)
- MOD `crates/world-gen/src/shape/mod.rs` (+template enum re-exports)
- MOD `scripts/climate_eval.py` (lat_banding rewrite)
- NEW `eval/baselines/v5.3.json` (post-v3.1b composite snapshot)
- NEW `eval/compare-phase-a/v3.1/plates_s{7,13,42}.png` (visual review artifacts)
- MOD `docs/sessions/SESSION_PATCH.md` (combined session entry)

**Total estimated LOC:** v3.1a ~240 (mostly extraction); v3.1b ~590 + 60 test + 100 eval. ~990 LOC new code over both commits, plus ~50 LOC refactor in flatworld.rs.

---

## Workflow-gate phase commands cheat-sheet

```powershell
# v3.1a sequence (after CLARIFY done):
python scripts/workflow-gate.py phase design
python scripts/workflow-gate.py complete design "spec + plan written, byte-identical mechanism specified"
python scripts/workflow-gate.py phase review-design
python scripts/workflow-gate.py complete review-design "self-review per Lead role"
python scripts/workflow-gate.py phase plan
python scripts/workflow-gate.py complete plan "5 chunks decomposed"
python scripts/workflow-gate.py phase build
python scripts/workflow-gate.py complete build "5 chunks done"
python scripts/workflow-gate.py phase verify
python scripts/workflow-gate.py complete verify "cargo test+clippy green; PNGs byte-identical"
python scripts/workflow-gate.py phase review-code
python scripts/workflow-gate.py complete review-code "self-review per Lead"
python scripts/workflow-gate.py phase qc
python scripts/workflow-gate.py complete qc "spec §5.1 criteria all checked"
python scripts/workflow-gate.py phase post-review
python scripts/workflow-gate.py complete post-review "PO confirmed byte-identical"
python scripts/workflow-gate.py phase session
python scripts/workflow-gate.py complete session "SESSION_PATCH updated"
python scripts/workflow-gate.py phase commit
python scripts/workflow-gate.py complete commit "<short SHA>"
python scripts/workflow-gate.py phase retro
python scripts/workflow-gate.py complete retro "lesson captured"

# Reset for v3.1b:
python scripts/workflow-gate.py size L 9 7 1
# (re-walk phases)
```
