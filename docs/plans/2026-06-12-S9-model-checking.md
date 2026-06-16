# S9 — Model checking (Stateright) of foundation protocols

> **Status:** PLAN (awaiting approval). **Size:** XL. **Mode:** human-in-loop, per-increment checkpoints, `/review-impl` before commit.
> **Scope (user, CLARIFY 2026-06-12):** **all three targets** (#1 lifecycle CAS, #2 outbox, #3 fan-out) **+ attempt liveness** (accepting the Stateright-experimental risk; TLA+ fallback tracked if cyclic paths defeat it).
> **Slice:** S9 of `docs/specs/2026-06-04-foundation-runtime-test-plan.md` §4 + §10. No deps. Closes the `{S2, S2b, S4, S9}` group.
> **De-risk DONE:** a spike (`crates/foundation-model`, a bounded-counter Model) proved stateright 0.31.0 builds on the workspace toolchain and that **safety + liveness both check** (`spawn_bfs().join().assert_properties()`). Increment 1 replaces the spike.

## 1. Goal

Design-altitude verification of three Rust kernel protocols: exhaustively explore the reachable state space and assert safety (no reachable state violates the invariant) + liveness (the good thing eventually happens). This checks the **protocol/state-machine**, NOT the implementation's locking (that's H1-loom, a later slice).

| # | Target | Invariant | Safety | Liveness |
|---|---|---|---|---|
| 1 | **Lifecycle CAS** | I9 | every reachable status is a valid graph node; every applied transition is a legal (graph + non-mutex) edge; **no two concurrent attempts from the same from-state both commit** (CAS exclusivity) | from any non-terminal state, some transition eventually commits or the system reaches a terminal state |
| 2 | **Outbox → publisher → consumer** | I13 | **atomicity** (state and outbox always agree); **no-loss** (every committed event reaches the consumer's applied set); **no permanent dup** (idempotent consumer → each event applied once despite redelivery) — all under crash injection | every committed event is eventually consumed |
| 3 | **Cross-reality fan-out** | I7 | an `xreality.*` event reaches **exactly** the subscribed reality set — no leak to non-subscribers, no miss of a subscriber | every emitted event eventually reaches all subscribers |

**No-drift principle:** Model #1 loads the **real `contracts/meta/transitions.yaml`** via `crates/meta-rs`'s `TransitionGraph` — so it checks the SAME graph the production code uses. A graph edit is automatically re-checked; the model can't silently diverge from the impl.

## 2. Design

### 2.1 Crate
`crates/foundation-model/` (already a workspace member). Layout:
- `src/lifecycle.rs` — Model #1 + properties + tests (incl. a bite-test).
- `src/outbox.rs` — Model #2.
- `src/fanout.rs` — Model #3.
- `src/lib.rs` — module wiring + shared helpers (checker-run + assert).
Dep on `meta-rs` (workspace path) for `TransitionGraph` in #1.

### 2.2 Model #1 — lifecycle CAS (the read-modify-write race, modeled honestly)
A single-action model checker makes each action atomic, so a CAS race must be modeled as **two steps** (read, then commit) with the read result carried in state:
- **State:** `{ status: String, pending: Vec<Attempt>, last_transition: Option<(String, String)> }` where `Attempt { from: String, to: String }` records "an actor observed `status==from` and intends `→to`". **`last_transition` records the ACTUAL hop a commit applied** — `(status_at_commit, to)` — which is what makes a CAS violation OBSERVABLE (review #3: `{status, pending}` alone cannot express the property).
- **Actions:** (a) **read+intend** — any legal edge `(status, to)` enqueues an `Attempt { from: status, to }` (models an actor reading the current state and deciding); (b) **commit** — pop an `Attempt`: if `status == attempt.from` (CAS) → set `last_transition = (status, attempt.to)` and advance `status = attempt.to`; else drop it (CAS lost). The CAS check is the mechanism under test — NOT an action-set restriction.
- **Safety (non-vacuous — the model CAN reach a violation, the CAS prevents it):** `status` always ∈ graph nodes; **`last_transition` is always a legal (graph + non-mutex) edge**. With broken CAS (the bite), two attempts from `active` both apply: status goes `active→X→Y` where the 2nd hop `(X, Y)` was computed from stale `active`, so `last_transition=(X,Y)` is an illegal edge → property fires. Bound `pending` length (e.g. ≤3 concurrent) to keep the space finite.
- **Liveness (cycle-robust — review #4):** NOT "eventually terminal" (false on the cyclic active↔frozen↔migrating graph). Instead: **every enqueued `Attempt` is eventually resolved** (`pending` does not grow unboundedly / each attempt eventually commits-or-drops) — bounded + achievable regardless of cycles. If even this is defeated by Stateright's experimental liveness, fall back to a safety-encoded "no attempt starves" check + `D-S9-LIFECYCLE-LIVENESS-TLA`.
- **Bite-test:** a variant whose commit step SKIPS the `status == from` check must produce an illegal `last_transition` → the safety property reports a discovery (counterexample). Asserts the checker CATCHES a real CAS bug, not just that the correct model passes.

### 2.3 Model #2 — outbox under crash (the trickiest)
Bounded to 1–2 events + a **finite crash budget** (review #4 — unbounded crashes make every liveness property trivially false). Phases mirror the real pipeline. **Atomicity is modeled non-vacuously (review #2):** the state write and the outbox write are SEPARATE steps, so a crash can land between them — the *same-tx* guarantee is modeled as an atomic state+outbox pair, and the property verifies it vs. a non-atomic bite variant.
- **State:** `{ state_written: Set<EventId>, outbox: Set<EventId> (durable), published: Set<EventId> (volatile stream), applied: Set<EventId> (durable), crashes_left: u8 }`.
- **Actions:** **write-state** (add to `state_written`); **write-outbox** (add to `outbox`) — in the correct (same-tx) model these are ONE atomic action `write = state_written ∪ {e}, outbox ∪ {e}`; in the bite they are two separate actions a crash can split; publish (`outbox \ published` → `published`, at-least-once, may re-publish); consume (`published` → `applied`, idempotent set union); **crash** (only while `crashes_left > 0`; decrement, drop volatile `published`, keep durable `state_written`/`outbox`/`applied`).
- **Safety:** **atomicity** — `state_written == outbox` in every reachable state (the correct same-tx model holds it; the non-atomic bite reaches a state where they differ → fires); **no-permanent-dup** — `applied` is a set (redelivery absorbed); **no-loss** is the liveness side below.
- **Liveness (with finite-crash fairness):** once `crashes_left == 0`, `eventually applied == outbox` (every durably-committed event is consumed). The crash budget is the fairness assumption (crashes don't recur forever).
- **Bite-tests:** (a) **non-atomic write** (separate steps, crash between) reaches `state_written != outbox` → violates atomicity; (b) **lossy publish** (drop a `committed` event) → violates no-loss.

### 2.4 Model #3 — cross-reality fan-out (non-vacuous — review #1)
The dispatch DECISION is what's under test, so the action set must be ABLE to mis-dispatch; the subscription lookup is the mechanism that prevents a leak. Dispatching only-to-subscribers by construction would make no-leak vacuously true.
- **State:** `{ emitted: bool, delivered: Set<RealityId> }` over a fixed universe `all_realities` partitioned into `subscribers` + `non_subscribers`.
- **Actions:** emit; **dispatch-to(r)** for ANY `r ∈ all_realities` that the meta-worker's **subscription check** admits — i.e. `dispatch-to(r)` is available iff `r ∈ subscribers` (the lookup). The action ranges over the WHOLE universe; the guard (subscription membership) is the mechanism. The bite removes/inverts the guard so `dispatch-to(r)` is available for a non-subscriber.
- **Safety:** `delivered ⊆ subscribers` (no leak) always — non-vacuous because the action ranges over `all_realities` and only the subscription guard keeps it in-bounds.
- **Liveness:** `eventually delivered == subscribers` (no miss).
- **Bite-test:** a variant whose dispatch guard admits a non-subscriber reaches `delivered ⊄ subscribers` → violates no-leak (counterexample reported).

### 2.5 Conformance wiring
A `model-checking` catalog case (`kind: rust-test`, `requires: []` — no stack, pure CPU): `command: ["cargo", "test", "-p", "foundation-model"]`. Folds S9 into the S1 catalog like S4. `rust-test` fail-closes on a build/compile error (a model that won't compile must not pass the gate).

## 3. Acceptance gate
- `cargo test -p foundation-model` green: all 3 models' safety **and** liveness properties hold (`assert_properties()` passes).
- Each model loads/uses the real source where one exists (#1 ← `transitions.yaml`).
- **Non-vacuity is the headline requirement (the /review-impl through-line):** each main model's action set must be ABLE to reach a violating state — the protocol mechanism (CAS check / same-tx / subscription guard), not an action-set restriction, is what prevents it. **Each model has a passing bite-test** where a variant with the mechanism removed REACHES a violation, asserted via Stateright's **discovery API** (a counterexample exists for the named property) — not just `assert_properties()`. Mirrors the S4/I8 vacuous-pass lesson.
- The explored **state-space size is logged/asserted non-trivial** (e.g. > N states) so we know coverage isn't a 3-state toy.
- `model-checking` conformance case passes via the runner.
- `cargo build --workspace` + `cargo fmt --check` + `clippy` (if wired) clean.

## 4. Build increments (human-in-loop — stop after each)
1. **Lifecycle CAS (#1)** — FIRST **spike the negative-assertion API** (review #5: confirm `checker.discovery(name)` / `.discoveries()` lets a bite-test assert a counterexample EXISTS — the bite-tests across all 3 models depend on it). Then replace the spike with `lifecycle.rs`: load the real graph (meta-rs), the read+intend/commit CAS model with `last_transition`, legal-edge safety + cycle-robust liveness, bite-test (no-CAS variant produces an illegal `last_transition`).
2. **Outbox (#2)** — `outbox.rs`: write/publish/consume/crash, atomicity+no-loss+no-dup safety, liveness, bite-test (lossy publish violates no-loss).
3. **Fan-out (#3)** — `fanout.rs`: emit/dispatch, no-leak safety, no-miss liveness, bite-test (non-subscriber dispatch violates no-leak).
4. **Conformance wiring + VERIFY** — `model-checking.yaml` (rust-test) + consolidated `cargo test -p foundation-model` + runner run; capture state-space sizes.

## 5. Risks / deferrals
- **Non-vacuity is the #1 build risk (the /review-impl through-line):** the easiest way to ship a green-but-worthless model is to restrict the action set so the bad state is unreachable. Every model's bite-test exists to prove the opposite — the mechanism, not the action set, holds the invariant. Treat a bite-test that DOESN'T fire as a model bug, not a pass.
- **Crash/cycle fairness:** liveness `eventually` properties are trivially false under unbounded crashes (#2) or infinite legal cycles (#1). #2 uses a finite crash budget; #1 uses a cycle-robust "every attempt resolved" predicate instead of "eventually terminal." If Stateright's experimental liveness still chokes, encode the liveness as a safety property over a step-bounded run.
- **`D-S9-LIFECYCLE-LIVENESS-TLA`** — if Stateright's experimental liveness can't handle the lifecycle's cyclic paths even with the cycle-robust predicate, track a TLA+ port of the liveness claim.
- **`D-S9-MODEL-SCOPE`** — the models are design-altitude + bounded (≤3 concurrent attempts, 1–2 events, fixed reality set). They verify the PROTOCOL, not the implementation's real locking/SQL (that's H1-loom, a later slice) nor unbounded scale. Documented in each model.
- **`D-S9-FANOUT-SUBSCRIBER-SOURCE`** — Model #3's subscriber set is hand-specified, not loaded from a real subscription source (the `book_reality_subscription` table semantics). Tighten when the real subscription model is exercised.
- **state explosion** — if a model's space blows up, reduce the bound (fewer actors/events) + log the cap (no silent truncation).
