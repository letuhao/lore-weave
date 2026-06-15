# Wave 4 — model / perf refinements — implementation plan

Spec: `docs/specs/2026-06-15-wave4-model-perf-refinements.md`. Size **XL**, 6 build
increments + 1 documented defer + W4.7 (conformance/CI/SESSION). Batch cadence
(autonomous → one POST-REVIEW → push-ask). `/review-impl` this plan first; W4.6
(reference projector) is the load-bearing centerpiece → `/review-impl` its impl too.

## Guiding constraints
- **Locate-first** each touch point (recon done: foundation-model bounds are
  explicit consts; book_reality_subscription is migration 026; usl fitter +
  recovery-test pattern exist; C2 golden harness runs `apply_one` over 11
  projections vs 21 fixtures).
- **Non-vacuity:** every increment ships a bite that CAN fail. For W4.6 the bite is
  an injected impl-divergence the reference projector CATCHES.
- **No padding / honest defer:** W4.5 builds only if the real subscription semantics
  are encodable; D-S11-LIVENESS-TLA stays deferred (TLA+ toolchain).

## Increment order (dependency-aware)
Independent items first (W4.1 unit, W4.4 bounds — cheap), then the live/infra ones
(W4.2 micro-bench, W4.3 recall), then the model-source (W4.5), then the centerpiece
(W4.6 reference projector), then W4.7.

## W4.1 — USL no-N=1 recovery test `[BE/Go]`
- `tests/perf/usl/usl_test.go`: add `TestFitRecoversKnownCoefficients_NoN1` mirroring
  the existing recovery bite but with concurrency `[2,4,8,16,32,64,128]` (NO N=1).
  Synthesize from KNOWN (γ,α,β) + seeded jitter; assert the fitter still recovers
  γ/α/β/Nmax within (slightly looser) tolerance and `!Degenerate`, R² ≥ 0.97.
- **Why non-vacuous:** without N=1, `guntherSeed` must ESTIMATE X(1) (the linearization
  anchor) rather than read it exactly — a previously-untested seed path. A stub/
  constant fitter fails; a seed that silently mis-estimates X(1) fails the γ tolerance.
- **Bite (already-provable):** flip one assertion target to a wrong value in a scratch
  run to confirm the test bites (then revert). No new infra.

## W4.2 — T0/T1 kernel micro-bench `[BE/Rust+bash]`
- **Locate-first** the append + outbox-emit calls (recon: `dp_kernel::PgEventStore::
  append_events` = T0; `events.OutboxWrite` / `crates/dp-kernel/src/outbox.rs` = T1).
- New `scripts/perf/w4-t0t1-micro.sh` (reuses the rig shard-0, applies 0001/0002/
  0005/0013 + default partition): drive K single-event appends through the REAL
  kernel via a tiny bench bin (or `cargo bench`/criterion in dp-kernel if cheaper),
  measure per-call wall-clock p50/p99 for T0 (append) and T1 (outbox row write).
  **S7 discipline:** ship the METHOD + a captured baseline; the gate is RELATIVE
  (T1 ≤ k·T0, since an outbox row INSERT must be cheaper than a full event append) —
  NOT an absolute µs threshold pre-baseline.
- **Bite:** inject artificial latency into the measured path (e.g. a `pg_sleep` in a
  wrapper, or bench a deliberately-batched-vs-unbatched variant) → the relative gate
  fires. The bite proves the harness measures the real path, not a constant.
- If a clean micro-bench bin is too heavy, FALL BACK to a hyperfine wrapper over an
  existing append-driving bin (e.g. a 1-event `wg -emit`) and document the
  append-vs-emit attribution. Decide at build.

## W4.3 — pgvector HNSW recall comparator `[BE/bash+SQL]`
- New `scripts/perf/w4-pgvector-recall.sh` (foundation-dev pgvector, like w3-generator):
  seed K (e.g. 2000) random 1536-d vectors into a throwaway table with an HNSW index
  (m=16, ef_construction=64 — mirror 0008). For Q query vectors, compute the EXACT
  top-k (brute-force `ORDER BY embedding <-> q LIMIT k`, no index / `SET enable_indexscan=off`)
  vs the APPROX top-k (HNSW, index on). **recall@k = |approx ∩ exact| / k**, averaged
  over Q; assert mean recall ≥ a threshold (e.g. 0.90 at ef_search default).
- **Bite (non-vacuous):** drop `ef_search` (e.g. `SET hnsw.ef_search = 1`) → recall
  collapses well below the threshold → the comparator CATCHES the quality regression.
  A vacuous comparator (e.g. comparing the index to itself) would not move. Restore
  ef_search → recall recovers.
- **Verdict:** NOTRUN if pgvector absent; FAIL if clean recall < threshold OR the
  low-ef bite does NOT drop recall; PASS otherwise.

## W4.4 — raise Stateright model bounds `[BE/Rust]`
- `crates/foundation-model/src/{lifecycle,outbox,fanout}.rs`: raise the bounding
  consts (lifecycle `BUDGET` 10→higher + `PENDING_CAP`; outbox `CRASH_BUDGET` 1→2;
  fanout `R` realities / a larger `SUBSCRIBERS` universe) to enlarge the verified
  state space. Keep the runtime bounded (use `check_random(_, N)` where the DFS space
  would explode — mirror W2.5's lesson; never `check_dfs(None)` on a now-larger model).
- **Why non-vacuous:** the existing should-fail / property-violation variants (each
  model already ships a bite that a broken transition would trip) MUST still fire at
  the higher bounds, and the safety/liveness properties MUST still hold over the
  larger space — a real counterexample surfaced here is a genuine finding, not a pad.
- **Bite:** confirm each model's existing negative test (the intentional violation)
  still FAILS the property at the new bounds (proves the larger model is still
  discriminating, not vacuously passing). Measure check time stays sane (CI-friendly).

## W4.5 — fan-out subscriber-source from the real table `[BE/Rust]`
- **Locate-first** `migrations/meta/026_book_reality_subscription.up.sql` semantics
  (which realities subscribe to which book → which get the fan-out). The lifecycle
  model already loads `transitions.yaml`; analogously, derive the fan-out subscriber
  set from the real subscription RULE rather than the hand-coded `SUBSCRIBERS=0b0111`.
- **Build-or-defer:** if the 026 semantics are a clean, encodable rule (a reality is a
  subscriber iff it has a row for the book), encode that as the model's subscriber
  source (a small fixture derived from the schema, or the rule itself) + assert the
  model now checks fan-out against the production rule. If the real semantics need a
  live DB / book-service surface not present in the model's scope, DEFER with the
  rationale (don't fake a "real" source). Decide at build.
- **Bite:** a subscriber-set that DISAGREES with the production rule must make the
  fan-out coverage property fail — prove the model is sensitive to the source.

## W4.6 — from-scratch C2 reference projector (differential oracle) `[BE/Rust]` (LOAD-BEARING)
- New `crates/projection-reference/` (or `tests/projectors/`): an INDEPENDENT
  reimplementation of the projection logic, written from the L3 DESIGN docs / event
  contracts — NOT copied from `crates/projections/*`. It maps an `EventEnvelope` to
  the expected `ProjectionUpdate`s for each L3.A arm.
- **Differential harness** (`crates/projection-reference/tests/diff.rs`): for every C2
  golden fixture's envelope (and/or generated envelopes), run BOTH the production
  `apply_one` (the 11 projections) and the reference projector; assert they agree.
  Because the two are independently authored, a real impl divergence from the design
  intent is CAUGHT (the same-author golden fixtures cannot catch it).
- **Non-vacuity is the whole point (review #1 of this plan):** the oracle MUST be able
  to DISAGREE. Ship a `#[ignore]`d or cfg-gated **injected-divergence bite**: a test
  that perturbs ONE production arm's output (e.g. via a wrapper that drops a field)
  and shows the differential harness FLAGS it — proving the reference projector is a
  real second opinion, not a transcription of the same contracts.
- **Scope honesty:** the reference projector must derive from the design, so for any
  arm where the "design" IS the arm contract (no independent spec exists), state that
  explicitly — that arm's differential is a consistency check, not an independent
  oracle. Cover the arms with a genuine independent design source; document the rest.
- Keep it from drifting: a test asserts the reference projector covers the same event
  set as the golden fixtures (no silent arm gap).

## W4.7 — conformance + CI + SESSION `[FS]`
- New `w4-*` conformance cases (`w4-pgvector-recall`, `w4-t0t1-micro`, +
  `w4-model-bounds` rust-test) `requires:`-gated; the USL no-N1 test + reference
  projector diff ride the existing `cargo test --workspace` / Go test CI.
- CI: scale-build `bash -n` the new `w4-*` scripts + `go test ./perf/usl/...`;
  scale-nightly live sweep for the recall + micro-bench drills; the reference
  projector + model-bounds run per-PR via `cargo test --workspace`.
- SESSION + memory + prune. Close W4 rows (or N/A-with-evidence); keep
  D-S11-LIVENESS-TLA deferred. Check the cleardown Wave-4 box → cleardown COMPLETE.

## Risks
- **R1 reference projector independence (W4.6).** If authored by reading the arm code,
  it's not a true oracle. Mitigation: derive from the L3 design docs + event contracts;
  ship the injected-divergence bite to PROVE it can disagree; honestly mark any
  arm whose only spec is the arm itself.
- **R2 micro-bench attribution (W4.2).** Separating T0 (append) from T1 (outbox) cleanly
  may be hard if they share a TX. Mitigation: measure append-with-outbox vs
  append-only, attribute the delta to T1; the relative gate + bite are the deliverable,
  not an absolute number.
- **R3 recall flakiness (W4.3).** HNSW recall is probabilistic. Mitigation: average over
  Q queries + a comfortable threshold margin; the bite (low ef_search) gives a large
  recall gap so the gate isn't borderline.
- **R4 model blow-up (W4.4).** Raising bounds can explode the DFS state space.
  Mitigation: `check_random(_, N)` sampling (W2.5 lesson), keep CI check time bounded.
- **R5 W4.5 fake-source.** Don't encode a "real" subscriber source that isn't actually
  the 026 rule. Build only if encodable; else defer with evidence.
