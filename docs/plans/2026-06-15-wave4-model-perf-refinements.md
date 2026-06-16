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

## Increment order (dependency-aware) — 5 build + 2 defer after plan-review
Plan-review outcome: **W4.5 deferred** (026 is pure membership, already modeled
parametrically — see W4.5). Build order: independent/cheap first (W4.1 unit, W4.4
bounds), then live/infra (W4.2 micro-bench, W4.3 recall), then the load-bearing
centerpiece (W4.6 reference projector — its own `/review-impl`), then W4.7. Deferred:
W4.5 (D-S9-FANOUT-SUBSCRIBER-SOURCE) + D-S11-LIVENESS-TLA.

## W4.1 — USL no-N=1 recovery test `[BE/Go]`
- `tests/perf/usl/usl_test.go`: add `TestFitRecoversKnownCoefficients_NoN1` mirroring
  the existing recovery bite but with concurrency `[2,4,8,16,32,64,128]` (NO N=1).
  Synthesize from KNOWN (γ,α,β) + seeded jitter; assert the fitter still recovers
  γ/α/β/Nmax within (slightly looser) tolerance and `!Degenerate`, R² ≥ 0.97.
- **Why non-vacuous:** without N=1, `guntherSeed` must ESTIMATE X(1) (the linearization
  anchor) rather than read it exactly — a previously-untested seed path. A stub/
  constant fitter fails; a seed that silently mis-estimates X(1) fails the γ tolerance.
- **Confirmed sound at plan-review (#6):** `guntherSeed` computes `gamma0 =
  max(throughput/N)` over ALL samples and the OLS SKIPS N≤1; without N=1 the max ratio
  is at N=2, which UNDER-estimates X(1) (USL X(N)/N is decreasing) — exactly the
  "underestimating-seed → Nelder-Mead refine recovers" path the deferred named.
- **Tolerance calibration:** keep tolerances tight enough that a non-recovering /
  constant fit FAILS (the discriminating bite); loosen only as much as the missing
  exact anchor genuinely needs. Confirm by a scratch wrong-target flip (then revert).

## W4.2 — T0/T1 micro-bench (the emit write path) `[BE/Go+bash]`
**Coherent T0/T1 definition (plan-review MED #2).** The kernel `append_events`
writes EVENTS ONLY; the outbox write (T1) is the Go `events.OutboxWrite` path. So the
two ticks live ADJACENTLY in the Go emit path (`tests/workload-gen/internal/emit`),
in ONE TX — that is where we measure, NOT "the kernel" (which has no T1):
  - **T0** = the `INSERT INTO events …` exec latency (now incl the W3.4
    `content_sha256` hash work — the micro-bench captures that cost).
  - **T1** = the `events.OutboxWrite` (`INSERT INTO events_outbox …`) exec latency.
- New tiny Go micro-bench (a `tests/perf/` bench or a `cmd/` harness) that, against
  the rig shard-0 (migrations 0001/0002/0005/0013 + default partition), runs K
  single-event writes and times EACH exec separately (wrap `ExecContext` with a
  per-call timer), reporting p50/p99 for T0 and T1.
- **S7 discipline:** ship the METHOD + a captured baseline; the gate is RELATIVE —
  **T1 p50 < T0 p50** (a 2-3-column outbox INSERT must be cheaper than a full
  many-column event INSERT + jsonb + checksum) — NOT an absolute µs threshold.
- **Bite (non-vacuous):** make T1 artificially expensive (e.g. point the outbox write
  at a variant that also re-hashes a payload, or add a `pg_sleep` wrapper) so
  T1 > T0 → the relative gate FIRES. Proves the harness times the real per-call path,
  not a constant. New `scripts/perf/w4-t0t1-micro.sh` orchestrates + asserts.

## W4.3 — pgvector HNSW recall comparator `[BE/bash+SQL]`
- New `scripts/perf/w4-pgvector-recall.sh` (foundation-dev pgvector, like w3-generator):
  seed K (e.g. 2000) random 1536-d vectors into a throwaway table with an HNSW index
  (m=16, ef_construction=64 — mirror 0008). For Q query vectors, compute the EXACT
  top-k vs the APPROX top-k (HNSW, index on). **recall@k = |approx ∩ exact| / k**,
  averaged over Q; assert mean recall ≥ a threshold (e.g. 0.90 at ef_search default).
- **Exact-pass must genuinely bypass HNSW (plan-review LOW #5).** Force a true
  brute-force for the EXACT set — `SET LOCAL enable_indexscan=off; SET LOCAL
  enable_bitmapscan=off;` (or run the exact pass against a no-index copy) — else the
  "exact" query silently rides the HNSW index and recall reads ~1.0 VACUOUSLY. Confirm
  via `EXPLAIN` the exact pass is a Seq Scan and the approx pass is an Index Scan.
- **Opclass/operator match.** Mirror `0008`'s opclass + the matching distance operator
  (`vector_l2_ops` ↔ `<->`); a mismatched operator silently disables the index.
- **Bite (non-vacuous):** lower `hnsw.ef_search` to a small-but-VALID value (≥ k but
  small, NOT below k — pgvector needs ef_search ≥ k) to degrade recall well below the
  threshold → the comparator CATCHES the quality regression. A vacuous comparator
  (index-vs-itself) would not move. Restore ef_search → recall recovers.
- **Flakiness margin (R3):** average over Q ≥ 20 queries + a comfortable threshold
  margin so a clean run is not borderline; the bite's recall gap is large.
- **Verdict:** NOTRUN if pgvector absent; FAIL if clean recall < threshold OR the
  low-ef bite does NOT drop recall OR EXPLAIN shows the exact pass used the index;
  PASS otherwise.

## W4.4 — raise Stateright model bounds `[BE/Rust]`
- `crates/foundation-model/src/{lifecycle,outbox,fanout}.rs`: raise the bounding
  consts (lifecycle `BUDGET` 10→higher + `PENDING_CAP`; outbox `CRASH_BUDGET` 1→2;
  fanout `R` realities / a larger subscriber universe) to enlarge the verified space.
  Each model already ships a discriminating bite (confirmed at recon:
  `lifecycle.rs:208 bite_broken_cas_violates_legal_hop` + `broken_cas()`; fanout +
  outbox negative tests), so the non-vacuity scaffold exists.
- **Coverage-vs-sampling (plan-review MED #3 — the real correctness condition).**
  Raising a bound only INCREASES coverage if the checker actually explores the new
  states. **Confirm the checker mode at build:** if it is bounded `check_dfs` (BFS/DFS
  exhaustive up to the bound), raising the bound genuinely explores more — done. If it
  is `check_random(_, N)` (sampled), raising the bound with a FIXED N just THINS
  coverage (bigger space, same samples) — so ALSO raise N proportionally, OR switch
  that model to bounded DFS at the new (still-finite) bound. Never `check_dfs(None)`
  on the enlarged model (W2.5 hang lesson). Record the chosen mode + counts.
- **Bite (must still discriminate at the new bounds):** each model's existing negative
  test (the intentional violation) MUST still FAIL the property at the raised bounds —
  proving the larger model is still discriminating, not vacuously passing. A real
  counterexample surfaced by the larger space is a genuine finding, not a pad.
- Keep CI check-time bounded (measure + cap); a model whose enlarged space is too big
  for per-PR time runs nightly instead.

## W4.5 — fan-out subscriber-source `[BE/Rust]` — **DEFERRED (plan-review MED #4)**
Recon settled this at PLAN time: `migrations/meta/026_book_reality_subscription.up.sql`
is a PURE membership table — `PRIMARY KEY (book_id, reality_id)`, the canon_writer's
`SubscribersForBook(book_id)` returns "the reality_ids with a row." There is NO
structural rule beyond set membership. The fan-out model ALREADY captures that
parametrically: `SUBSCRIBERS` is a membership bitmask and the model verifies
"non-subscribers never receive delivery" / "all subscribers eventually do" for that
set — i.e. it is already correct for ANY subscriber set. Loading the SAME membership
set from a fixture instead of a literal adds **no new verified structure** (there is
no rule that could drift). Building it would be padding.
- **Verdict: DEFER** as `D-S9-FANOUT-SUBSCRIBER-SOURCE` with this evidence. Re-open
  only if `book_reality_subscription` gains non-membership semantics (e.g. visibility-
  or cascade-conditioned delivery) that the parametric model does not already cover —
  THEN deriving the rule from the schema would verify something new.

## W4.6 — from-scratch C2 reference projector (differential oracle) `[BE/Rust]` (LOAD-BEARING)
**Independence basis (plan-review HIGH #1 — the whole value hinges on this).** The
reference projector MUST be derived from a DIFFERENT representation than the
production arms, or it is a transcription that agrees by construction (reproducing
exactly the bounded-independence limitation C2 already has). The two independent
sources it derives from — NEVER reading `crates/projections/*`:
  1. the **event contract** — the payload field schema in `contracts/events/`
     (+ `tests/workload-gen/internal/schema` Specs) — what fields an event CARRIES.
  2. the **table DDL** — the projection columns in `0006_projections.up.sql` — what
     a row HOLDS.
It maps payload-field → projection-column by NAME/intent ("`trust_level` payload →
`trust_level` column"), independently of HOW the arm reads it. So an arm that reads
the WRONG payload key, writes the WRONG column, or emits the wrong update KIND
diverges from the contract-derived reference.
- New `crates/projection-reference/` + a **differential harness**
  (`crates/projection-reference/tests/diff.rs`): for every C2 golden fixture's
  envelope (+ generator-produced envelopes), run BOTH the production `apply_one`
  (the 11 projections) and the reference projector; assert agreement on
  (table, pk, fields, kind).
- **Honest framing (plan-review HIGH #1b):** first-run agreement on all fixtures =
  a REGRESSION-LOCK, the SAME class of assurance as C2 — NOT proof of bug-finding.
  The independent VALUE is realized when (a) a future arm change diverges from the
  contract, or (b) a present arm/contract mismatch exists. State this in the harness
  doc; do NOT over-claim "true independent oracle" if it agrees first-run.
- **Strengthened bite (plan-review HIGH #1c — proves independence, not just wiring):**
  the bite is NOT merely "perturb prod, harness flags it" (a transcription passes
  that too). Instead, a cfg/`#[ignore]`-gated test wraps a production arm to read a
  WRONG payload key (the exact class of real bug C2 can't catch) and shows the
  contract-derived reference — reading the RIGHT key — DISAGREES. This demonstrates
  the reference is a genuine second opinion grounded in the contract, not the arm.
- **Scope honesty:** for any arm whose only spec IS the arm code (no independent
  contract/DDL basis for a field — e.g. a derived/computed field), mark that field's
  differential as a CONSISTENCY check, not an independent oracle; cover the
  contract-derivable fields genuinely and document the residue. No silent over-claim.
- Anti-drift: a test asserts the reference projector covers the same event set as the
  golden fixtures (no silent arm gap).

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
