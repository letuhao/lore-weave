# Wave 4 — model / perf refinements — spec

Fourth (final) do-now slice of `docs/plans/2026-06-14-post-S14-deferred-cleardown.md`.
Lowest-urgency refinements; user chose **max scope** (2026-06-15): build every item
that is buildable on the dev box / scale rig, defer only what needs a different
toolchain. Plan: `docs/plans/2026-06-15-wave4-model-perf-refinements.md`. Size **XL**.

## Why / acceptance
The S1–S14 + Wave1–3 batteries are complete; Wave 4 sharpens the measurement +
model + oracle surfaces that earlier slices intentionally left at first-pass
fidelity. Each increment must be **non-vacuous** (every check ships a bite that
can fail) and **honest** (no padding — if an item is genuinely blocked, defer with
rationale, don't ship a vacuous check).

## Scope (6 build + 1 defer)
- **W4.1 D-S7-USL-NO-N1** — the USL fitter's Gunther seed is only unit-covered WITH
  an exact N=1 anchor; add a no-N=1 recovery test (seed must estimate X(1)).
- **W4.2 D-S12-T0T1-MICRO** — micro-bench the kernel T0 (event append) + T1 (outbox
  emit) per-call latency; S12 measured aggregate throughput, never the inner tick.
- **W4.3 D-S7-PGVECTOR-RECALL** — the pgvector probe asserts presence+dim only; add
  an HNSW **recall** comparator (approx top-k vs exact, recall ≥ threshold).
- **W4.4 D-S9-MODEL-SCOPE** — raise the Stateright model bounds (lifecycle BUDGET /
  PENDING_CAP, outbox CRASH_BUDGET, fanout R) for a larger verified state space.
- **W4.5 D-S9-FANOUT-SUBSCRIBER-SOURCE** — derive the fan-out subscriber set from the
  real `book_reality_subscription` semantics (migration 026) instead of the
  hand-coded `SUBSCRIBERS = 0b0111`, so model↔schema drift can't hide.
- **W4.6 D-C2-REFERENCE-PROJECTOR** — a from-scratch, independently-derived reference
  projector run as a DIFFERENTIAL oracle vs the production projections — a true
  independent oracle (the C2 golden fixtures are same-author regression-locks that
  can't disagree with the arm contracts).
- **Deferred: D-S11-LIVENESS-TLA** — `sometimes(reachable)` is the honest claim;
  always-eventually under fairness needs a TLA+/TLC port (different toolchain).

## Invariants honored
Non-vacuity bite per check (the [[non-vacuity-bite-test-discipline]] memory); S7
perf discipline = "ship a method + a relative/baseline gate, no absolute pre-baseline
thresholds, every gate has a bite"; conformance verdict `{pass|fail|notrun|skip}`.
