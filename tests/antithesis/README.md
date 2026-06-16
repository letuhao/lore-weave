# S11 — Whole-stack DST: Antithesis-readiness (Technique H2)

This directory is the **submit-ready test template** for running the foundation
spine under [Antithesis](https://antithesis.com) — a hosted, deterministic
hypervisor that explores fault schedules over the whole docker-compose stack with
bit-perfect replay. Spec: `docs/specs/2026-06-14-S11-whole-stack-dst.md`.

## Honesty guard — what is and isn't verified here

- **Locally verifiable:** the driver **compiles + `go vet`s** (CI: `antithesis-build`,
  per-PR) and **runs** against a booted foundation-dev stack (the
  `antithesis-sdk-go` `assert`/`lifecycle` calls are **no-ops outside Antithesis**,
  so it behaves as a plain delivery-convergence check, exit 0/1/2).
- **NOT verified here:** that Antithesis *finds bugs*. That requires the actual
  paid run (`D-S11-ANTITHESIS-RUN`) — an account, image instrumentation, and a
  push to their registry. This template makes the system **submit-ready**; it does
  not claim a hypervisor run happened.

The **locally-provable** whole-stack chaos result is the sibling drill
`scripts/chaos/whole-stack-chaos.sh` (conformance `whole-stack-chaos`), which runs
concurrent pg-slow ∥ redis-partition under load via toxiproxy and asserts
delivery-convergence with a real bite.

## What the driver asserts (`driver/main.go`)

The same **fault-sensitive** property as the local drill — **delivery-convergence**
(the publisher drains every emitted event to its Redis stream, no loss,
dedup-able), because in the foundation spine that is the ONE thing faults can break
(projections are rebuild-only; the write path is transactional — see spec §3.1).
It wraps the per-reality no-loss check + C3 in:
- `lifecycle.SetupComplete` — the system is up, start injecting faults.
- `assert.Always(delivery-convergence)` — explored against every fault schedule.
- `assert.Always(C3 ledger integrity)`.
- `assert.Sometimes(progress made)` / `assert.Reachable(cycle completed)`.

The driver **shells the spine binaries** (`wg` for emit/verify) and reads the
event log + Redis stream directly — no reimplemented convergence logic (the bash
drill and the driver agree on the oracle).

## Files

| File | Purpose |
|---|---|
| `driver/` | the singleton test driver (Go module, `antithesis-sdk-go`) |
| `docker-compose.antithesis.yml` | the test-composer: spine services + publisher + the singleton driver |
| `config/Dockerfile.driver` | builds the driver + `wg` |
| `config/Dockerfile.init` | migrates + seeds the shard/meta DBs, emits the initial workload |
| `config/init.sh` | the init entrypoint |

## How to submit (deferred — `D-S11-ANTITHESIS-RUN`)

1. Get an Antithesis account + registry credentials.
2. Build the images **through Antithesis's instrumentation** wrapper (adds the
   coverage/feedback hooks) and push them.
3. Point the composer at the pushed images; submit `docker-compose.antithesis.yml`
   as the test config. Antithesis runs the stack under injected faults and reports
   any `assert.Always` violation with a **replayable** trace.
4. Cost: Antithesis is a paid SaaS (per-run / subscription) — a human spend
   decision, hence deferred.

## What H2 targets that S1–S10 do not

S1–S10 cover correctness (conformance), faults (toxiproxy single-fault drills),
recovery (DR drills), perf (USL), model-checking (Stateright), and kernel-sim DST
(madsim-rejected → VOPR). H2 adds **deterministic whole-stack fault exploration
with bit-perfect replay** across the *entire composed system* — the
near-production tier the local toxiproxy drills approximate but cannot replay.

## Deferred

- `D-S11-ANTITHESIS-RUN` — the actual paid Antithesis run (account + instrumented
  images + submit).
- `D-S11-FULL-APP-STACK` — extend the composer to the *entire LoreWeave app*
  (gateway + all domain services); S11's "whole stack" is the foundation spine.
