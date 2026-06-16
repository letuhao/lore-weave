# S13 — L1/core coverage — implementation plan

Spec: `docs/specs/2026-06-14-S13-l1-core-coverage.md`. Size **XL**, 5 increments,
batch cadence (autonomous → one POST-REVIEW → push-ask). `/review-impl` on this
plan first, then on the impl.

## Guiding constraints
- **Live + fault, not model-check.** S9 already model-checked I9 CAS; S13 proves it
  at runtime against real Postgres under concurrent racers + mid-op faults. Every
  check ships a **non-vacuity bite**.
- **Reuse the S12 scale rig** (`infra/scale/`): meta-pg for lifecycle/capacity;
  the real multi-shard PGs for cross-shard relocation; toxiproxy for fault
  injection. New = the lifecycle-race harness + the relocation drill.
- **Test the L1 contracts, drive them directly.** Where no service exposes the path
  yet, a small harness calls the real contract (`AttemptStateTransition`, the
  migration `runner`) against the meta DB — the same pattern as `metaworker-bench`.
  Test drills carry a loud banner (they are NOT the production provisioner/relocator).
- **Honesty rails:** production durability on the meta DB; concurrency races use
  REAL concurrent transactions (not simulated); relocation verifies with a content
  checksum (event_id+version+payload, per the S12 review fix), not an id-set.

## Increment 1 — Lifecycle CAS race + R09 safe closure (A) `[FS]`
- `tests/perf/lifecycle-race/` (Go): N goroutines call the REAL
  `contracts/meta.AttemptStateTransition` for the SAME `from→to` on one reality →
  assert **exactly one commits**, N−1 get `ErrConcurrentStateTransition`, and
  `lifecycle_transition_audit` has exactly ONE success + N−1
  `concurrent_modification` rows. Drive over the real graph
  (provisioning→active→pending_close→frozen→archived).
  - **Harness wiring (not a one-liner):** build a full `meta.Config` — load
    `contracts/meta/transitions.yaml` (graph), load the meta allowlist (and ensure
    `reality_registry` is allowlisted), bind a pg-backed `meta.DB` adapter
    (`sdks/go/metapg` pattern) + `PostgresQueryBuilder` + Clock + UUIDGen — the same
    Config `cmd/meta-worker` constructs.
- `scripts/perf/l1-lifecycle.sh`: runs the race. **R09 safe-closure — locate first:**
  `AttemptStateTransition` only CASes status; it does NOT drain. Find whether an
  automated closure-drain orchestrator exists. If yes: drill `active→pending_close`
  with un-published outbox → assert nothing stranded before `→frozen`; abort
  (`pending_close→active`) restores. If no: test the transitions + `reality_close_audit`
  and record the drain as a gap (deferred). **Mid-TX kill** (toxiproxy cut on the
  meta path during the transition) → no half-state (status + audit atomic).
- **Bite:** a **raw `UPDATE reality_registry SET status=… ` WITHOUT the CAS
  WHERE-guard** (bypassing `AttemptStateTransition`), run by two racers → both win →
  a double transition the audit/state-count check flags. Proves the CAS holds
  correctness (NOT a re-run of S9's model-check; you cannot feed a stale expected to
  the API — the CAS guard is derived from `req.FromState`).

## Increment 2 — Capacity / provisioning enforcement (B) `[FS]`
- `scripts/perf/l1-capacity.sh`: seed `shard_utilization`; provision realities onto
  a shard up to `session_max_total` / the shard's capacity; assert over-capacity
  provisioning is **rejected or re-routed** (not silently over-subscribed);
  `capacity_override` lifts the cap AND lands a `meta_write_audit` row (I8);
  `shard_utilization` reflects the live count.
- First **locate the enforcement point** (CHECK constraint vs app routing); if
  app-level routing enforcement is absent, test the CHECK + override + utilization
  and record the routing-enforcement gap as a deferred row (don't fake a pass).
- **Bite:** provision past capacity with the guard disabled → over-subscription the
  check catches.

## Increment 3 — Migration canary-gated rollout (C1) `[FS]`
- `scripts/perf/l1-migration.sh` + a small driver wiring the REAL `canary.Orchestrator`
  + `runner` (real Applier running migration SQL on real per-reality DBs). The
  `VerificationGate` is an injected interface (no production verifier yet) → "live" =
  real runner + real SQL + real per-reality isolation, gate injected.
- **Two DISTINCT abort paths (`canary.go:206` Phase-1 apply, `:217` Phase-2 gate) —
  they are not the same and need separate bites:**
  - **Phase-1 apply-fail:** canary `Apply` fails → abort `canary_apply_failed`
    *before the gate is reached*; fanout MUST NOT run. **Bite:** ignore
    `CanaryResult.Succeeded` → fanout runs on a broken canary → caught.
  - **Phase-2 verification gate:** canary applies OK but `VerificationGate.wait`
    returns false → abort `canary_verification_*`; fanout MUST NOT run. **Bite:** stub
    the gate to PASS when verification should fail → fanout proceeds → caught.
- Plus per-reality isolation: a failure on ONE fanout reality dead-letters
  (`reality_migration_audit.migration_failed`, retry/backoff exhausted) while the rest
  succeed; runner concurrency cap intact.

## Increment 4 — Cross-shard reality relocation (C2, the headline) `[FS]`
- `scripts/perf/l1-relocate.sh` (reuses the multi-shard rig): relocate a reality
  shard-0→shard-1 — `active→migrating` (CAS), copy events (pg_dump/restore),
  **content-checksum** (event_id+version+payload) target==source, then
  `migrating→active` carrying the new `db_host` as **`Payload` on that transition**
  (CAS-guarded on `status` — `db_host` is NOT the state column, it rides as a payload
  override in the same `AttemptStateTransition`), decommission source.
- **Fault:** kill between data-copy and the registry update → assert **(a) complete
  data at the target** (`db_host` never points at a shard lacking the full event set)
  and **(b) no orphan source** (old shard decommissioned, not left readable). NOTE the
  registry cannot "split-brain" — one `db_host` per `reality_id` (PK); the real risks
  are premature-flip LOSS (a) + orphan-LEFTOVER (b). The half-done relocation must
  roll forward or back, never both-live.
- **Bite:** update `db_host` BEFORE the data lands on the target → reads route to an
  empty/short target → the content-checksum verify catches it.

## Increment 5 — conformance + CI + SESSION (D) `[FS]`
- `l1-{lifecycle,capacity,migration,relocate}` conformance cases (`requires`-gated
  like `s12-*`), an `l1-nightly` CI job (small live sweep with bites) + an `l1-build`
  per-PR anti-bit-rot job (build/vet the new Go harness, `bash -n` the scripts).
- Close `D-S5-SHARD-MULTI-REALITY-ATTRIB` (real one-reality-per-DB exists now).
- SESSION + memory + remember; short coverage note; roadmap → S14 next.

## Risks
- **R1 enforcement-point unknown (capacity).** Capacity may be enforced in an
  unbuilt provisioner, not a contract. Mitigation: Inc-2 first locates it; tests
  what exists (CHECK/override/utilization) and records any routing-enforcement gap
  as a deferred row rather than faking coverage.
- **R2 no production relocation tool.** Inc-4 builds a TEST relocation drill
  (loud-bannered) modeling the procedure; the production cross-shard relocator is a
  later L1 feature — the drill proves the *invariants* (complete-data-at-target +
  no-orphan-source, no loss), not a shipped tool.
- **R3 CAS race needs real concurrency.** lifecycle-race uses N real goroutines +
  real transactions; the bite is a **raw `UPDATE` without the CAS WHERE-guard** (you
  cannot feed a stale expected to the API — the guard is derived from `req.FromState`)
  → proves the CAS is what holds correctness.
- **R4 meta DB connection limits.** Keep racer/relocation concurrency modest
  (rig meta-pg `max_connections`); scale is S12/S14's concern, not S13's.
- **R5 mid-op kill timing flakiness.** Use toxiproxy cut + a deterministic “catch
  mid-op” poll (like the S11 mid-drain catch); notrun if the window is missed
  (never a flaky fail).
- **R6 R09 closure-drain mechanism unknown.** `AttemptStateTransition` does NOT
  drain. Inc-1 locates whether an automated closure-drain orchestrator exists; if
  not, it tests the transitions + `reality_close_audit` and records the drain as a
  deferred gap (same discipline as R1) — never asserts an unimplemented drain.
