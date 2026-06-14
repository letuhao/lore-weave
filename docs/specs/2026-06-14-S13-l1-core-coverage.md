# S13 — L1/core coverage (lifecycle · capacity · migration), live + fault

**Slice:** S13 — bring the **L1 provisioning/sharding layer** into the same live
conformance + fault battery the S1–S11 spine got. Split out of S12 (review round-3
MED-3); the foundation's correctness arc isn't complete until L1 is exercised at
runtime, not just unit-tested + (for I9 CAS) model-checked.
**Date:** 2026-06-14 · **Branch:** `mmo-rpg/foundation-mega-task` · **Size:** XL.
**CLARIFY (user, 2026-06-14):** **all three** L1 areas · **full battery + live
cross-shard** (Jepsen-style fault mid-operation + a REAL reality relocation
shard→shard on the S12 scale rig), every check with a non-vacuity bite.
**Anchors:** lifecycle CAS `docs/03_planning/LLM_MMO_RPG/02_storage/C05_lifecycle_cas.md`
+ `contracts/meta/lifecycle.go` + `contracts/meta/transitions.yaml`; safe closure
`…/R09_safe_reality_closure.md`; capacity `…/SR08_capacity_scaling.md` +
`shard_utilization` (meta 024) + `capacity_override`; migration
`services/migration-orchestrator/` (canary/runner/manifest) + `reality_migration_audit`
(meta 007). Invariants I8 (MetaWrite), I9 (AttemptStateTransition, CAS).

---

## 1. What L1 is + the reality lifecycle (the runtime surface)

L1 owns **where a reality lives and what state it is in**. The reality lifecycle
(`transitions.yaml`) is a CAS-protected state machine:

```
provisioning → {active, dropped}
active       → {pending_close, migrating}
pending_close→ {active, frozen}        migrating → {active, frozen}
frozen       → archived → archived_verified
```

Every transition goes through `AttemptStateTransition` (I9): validate against the
graph, CAS on the current state, write a `lifecycle_transition_audit` row in the
SAME TX. This is the concurrency-critical L1 path — **"concurrency is a nightmare"
lives here** (two operators / two controllers racing a transition).

## 2. What is already covered vs what S13 adds

- **I9 lifecycle CAS** was **model-checked** in S9 (Stateright) — the *logic* is
  proven. S13 adds the **runtime/live** proof: the real `AttemptStateTransition`
  against real Postgres under **concurrent racers**, under **fault** (the writer
  killed mid-TX), and the **R09 safe-closure** drain semantics end-to-end.
- **Migration** has unit tests (runner retry/backoff/dead-letter, canary phases).
  S13 adds the **live rollout** (canary apply → verify-gate → fanout with a real
  failure injected) AND the thing nothing has tested: a **real cross-shard reality
  relocation** (move a reality's data shard→shard on the multi-shard rig) with a
  fault injected mid-relocation → **no split-brain, no loss**.
- **Capacity** has the schema (`shard_utilization`, session-max CHECKs) +
  `capacity_override`. S13 adds the **live enforcement** proof (provision to the
  limit; over-capacity rejected/re-routed; override audited).

**Terminology fix (from the S12 plan's "migration 6-phase"):** the real structure
is (a) the **canary-gated schema rollout** — Phase 1 apply-to-canary → Phase 2
verify hard-gate → Phase 3 fanout (`canary.go`) with the runner's retry/dead-letter
— and (b) **reality relocation** via the `active→migrating→active` lifecycle. S13
covers both; there is no single "6-phase" procedure.

## 3. Method (full battery + live cross-shard)

- **Live conformance** against real Postgres (reuse the S12 scale rig — multi-shard
  is exactly what relocation needs; lifecycle/capacity use the meta DB).
- **Jepsen-style fault injection MID-operation** (toxiproxy + process kill): the
  state-transition writer killed mid-TX; the migration runner's shard slowed/killed
  between phases; the relocation killed between data-copy and registry-flip.
- **Non-vacuity bite** on every check (a real defect the check MUST catch).
- **Verdict** `{pass|fail|notrun}` (S6/S8 convention): setup → notrun(2); a real
  violation (split-brain, lost transition, over-subscription, a bite that fails to
  bite) → fail(1); clean → pass(0). Re-runnable.
- **No new model-checking** (S9 owns that); S13 is the live/runtime/fault layer.

## 4. Scope

- **A — Lifecycle CAS + R09 safe closure (I9).** Live: drive the real
  `AttemptStateTransition` over the graph; assert valid transitions commit + audit,
  invalid rejected. **Concurrency drill:** N actors race the SAME `from→to` → exactly
  ONE wins (the CAS is `MetaWrite` with `ExpectedBefore={status:FromState}`; the
  loser gets `ErrConcurrentStateTransition`), `lifecycle_transition_audit` shows ONE
  success + N−1 `concurrent_modification` rows. **R09 safe closure — LOCATE FIRST:**
  `AttemptStateTransition` only CASes `status` + audits; it does NOT drain. So Inc-1
  first finds whether an automated closure-drain orchestrator exists. If it does:
  drill `active→pending_close` with un-published outbox → assert no event stranded
  before `→frozen`; abort (`pending_close→active`) restores cleanly. If it does NOT:
  test what exists (the transitions + `reality_close_audit`) and **record the drain
  as a gap** (don't assert an unimplemented drain). **Fault:** kill the writer
  mid-transition-TX → no half-applied state (status + audit are atomic).
  **Bite:** a **raw `UPDATE status=…` WITHOUT the CAS WHERE-guard** (bypassing
  `AttemptStateTransition`) run by two racers → both "win" → a double transition the
  audit/state-count check flags — proving the CAS is what holds correctness (not a
  re-test of S9's model-check).
- **B — Capacity / provisioning — LOCATE ENFORCEMENT FIRST.** `shard_utilization` is
  append-only **snapshots** (`snapshot_id` PK), not a live counter, and app-level
  over-capacity rejection may live in an unbuilt provisioner. So Inc-2 first finds
  the enforcement point. **If present:** provision up to capacity; assert
  over-capacity is **rejected or re-routed** (not silently over-subscribed); bite =
  guard disabled → over-subscription caught. **If absent:** test what exists (the
  `session_max_*` CHECK constraints + `capacity_override` landing a `meta_write_audit`
  row via I8 + a `shard_utilization` snapshot reflecting the count) and **record the
  missing routing-enforcement as a deferred gap** — never fake a pass.
- **C — Migration: rollout + cross-shard relocation.** (The canary
    `VerificationGate` is an injected interface — there is no production verifier yet
    — so "live" here = the REAL runner + REAL migration SQL on real per-reality DBs +
    real per-reality isolation, with the gate injected.)
  - **Canary-gated rollout — TWO distinct abort paths (`canary.go:206`,`:217`):**
    (1) **Phase-1 apply-fail:** canary's `Apply` fails → abort `canary_apply_failed`
    *before the gate is reached*; fanout MUST NOT run. Bite: ignore
    `CanaryResult.Succeeded` → fanout runs on a broken canary → caught. (2) **Phase-2
    verification gate:** canary applies OK but `VerificationGate.wait` returns false →
    abort `canary_verification_*`; fanout MUST NOT run. Bite: stub the gate to PASS
    when verification should fail → fanout proceeds → caught. Plus: a failure on ONE
    fanout reality dead-letters (`reality_migration_audit.migration_failed`,
    retry/backoff exhausted) while the others succeed (per-reality isolation).
  - **Cross-shard reality relocation (the headline):** `active→migrating` (CAS), copy
    the reality's events shard-0→shard-1 (real separate PGs), **content-checksum**
    (event_id+version+payload) target==source, then `migrating→active` carrying the
    new `db_host` as `Payload` on that transition (CAS-guarded on `status`, NOT a
    state-column change), decommission source. **Fault:** kill between data-copy and
    the registry update → assert **(a) complete data at the target** (`db_host` never
    points at a shard that lacks the full event set) and **(b) no orphan source** (the
    old shard's copy is decommissioned, not left readable). Note the registry CANNOT
    "split-brain" — one `db_host` per `reality_id` (PK) — the real risks are
    premature-flip loss (a) and orphan-leftover (b). **Bite:** update `db_host`
    BEFORE the data lands → reads route to an empty/short target → the checksum
    verify catches it.
- **D — conformance cases + CI + report.** `l1-*` conformance cases (CPU/stack-
  gated like `s12-*`), an `l1-nightly` CI job (small live sweep), and a short
  coverage note folded into SESSION. Close `D-S5-SHARD-MULTI-REALITY-ATTRIB` (real
  one-reality-per-DB now exists via the S12 rig).

## 5. Out of scope (tracked)
- Re-model-checking I9 (S9 owns it) · the full reality provisioner business logic
  (S13 tests the L1 *contracts*, not feature behaviour) · Phase-2 multi-host
  (`D-S12-MULTI-HOST`) · the L4–L7 domain layers.

## 6. Acceptance criteria
- [ ] A: live `AttemptStateTransition` over the real graph; concurrent-race ⇒
      exactly-one-wins (CAS, loser `concurrent_modification`); R09 closure mechanism
      located (drain asserted if it exists, else gap recorded); mid-TX kill leaves no
      half-state; bite (raw-UPDATE-without-CAS ⇒ double transition) fires.
- [ ] B: capacity enforcement located; if present, over-capacity rejected/re-routed
      + bite fires; else CHECK + `capacity_override` audit + utilization snapshot
      tested and the routing-enforcement gap recorded (no faked pass).
- [ ] C: Phase-1 apply-fail aborts before the gate (bite: ignore Succeeded);
      Phase-2 verification-fail aborts fanout (bite: stub gate to pass); one-reality
      failure isolates (dead-letter) without blocking others; **live cross-shard
      relocation with a mid-relocation kill ⇒ complete-data-at-target + no-orphan-
      source, no loss**; all bites fire.
- [ ] D: `l1-*` conformance cases + `l1-nightly` CI; `D-S5-SHARD-MULTI-REALITY-ATTRIB`
      closed; SESSION updated.
- [ ] `/review-impl` on the plan AND the impl; findings folded.
