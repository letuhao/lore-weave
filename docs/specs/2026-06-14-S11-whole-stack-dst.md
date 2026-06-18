# S11 — Whole-stack DST (Technique H2): local chaos-convergence + Antithesis-readiness

**Slice:** S11 — the FINAL slice of the foundation runtime test plan
(`docs/specs/2026-06-04-foundation-runtime-test-plan.md`, §9 H2, §10 roadmap).
**Date:** 2026-06-14 · **Branch:** `mmo-rpg/foundation-mega-task` · **Size:** XL.
**Depends on:** the whole battery — S5 (standing integrity), S6 (fault matrix + toxiproxy), S8 (recovery drills).

---

## 1. Goal & honest framing

H2 (whole-stack DST) in the plan means **Antithesis** — a paid, hosted, deterministic-hypervisor SaaS
that wraps the docker-compose stack and explores fault schedules with bit-perfect replay. **It cannot be
run locally**, and its SDK assertions compile as **no-ops outside the Antithesis environment**. So S11
splits into two honestly-scoped halves (CLARIFY: "local chaos-convergence + Antithesis-readiness"):

1. **Local whole-stack chaos-convergence (BUILDABLE + FULLY VERIFIABLE).** Boot the full foundation spine,
   drive sustained workload through the whole pipeline, inject **CONCURRENT multi-service faults** under
   load, then assert the spine **converges to `B ∧ C ∧ C2 ∧ C3`** after quiesce — with a non-vacuity bite.
   This is the production-shaped, locally-provable deliverable.
2. **Antithesis-readiness (SCAFFOLDING — locally verifiable only as compiles + no-op).** A submit-ready
   test template: an `antithesis-sdk-go` driver embedding `assert_always`/`assert_sometimes`/lifecycle
   signals, the test-composer `docker-compose`, the singleton `config/`, and submission docs. The actual
   **paid run is deferred** (`D-S11-ANTITHESIS-RUN`, needs an account) — and that is stated, not faked.

**Non-vacuity honesty (the project's discipline):** the local half has a real bite (a fault that breaks
convergence is caught). The readiness half's assertions are real `antithesis-sdk` calls but are **no-ops
locally** — so they are NOT claimed to "find bugs" here; only "compile + are inert + the driver runs". The
docs say so plainly.

## 2. What S11 adds beyond S5–S8

| Slice | Fault model | Scope |
|---|---|---|
| S5 | none (rebuild only) | N shards, standing B |
| S6 | **single** fault (pg-down / redis-partition / pg-slow) vs the **publisher** | one component |
| S8 | **single** recovery event (kill / truncate / archive / replay) | one drill at a time |
| **S11 (local)** | **CONCURRENT multi-service faults under sustained load** (pg-slow ∥ redis-partition, staggered) — oracle = **delivery-convergence** (publisher drains outbox→Redis, no-loss/dedup-able) after the multi-fault, the one property faults stress (§3.1) | whole spine delivery path |
| **S11 (Antithesis)** | hypervisor-driven, bit-perfect-replayable, exhaustive | whole compose, near-prod (deferred) |

## 3. Local chaos-convergence — design

### 3.1 What the faults can actually perturb (review HIGH-1)

The fault model must be matched to what is *fault-sensitive* in the spine, or the run is vacuous:
- **B / C / C2 are rebuild-laundered.** The foundation spine has **no live projection consumer**
  (verified: the publisher only drains outbox→Redis `XADD`; the only stream consumers are in *domain*
  services — campaign/glossary — not the spine). Spine projections are built **only by the rebuilder
  (replay-from-events)**. A final rebuild reconstructs them regardless of what faults did during the run →
  B/C/C2 are insensitive to the faults.
- **C3 (log integrity) stays clean under faults.** The write path is **transactional** (S6 proved
  pg-down → emit fails *and rolls back*, no partial). Faults can't tear the event log → C3 passes with or
  without faults.
- **⇒ The ONLY property the concurrent faults stress is DELIVERY:** the publisher draining outbox→Redis
  across a **redis-partition under sustained load + concurrent pg-slow**. That is the load-bearing oracle.

### 3.2 Harness

- **Boot** `infra/foundation-dev` (postgres + redis + minio + **toxiproxy**), create PG + Redis proxies.
- **Persistent publisher (review MED-1):** start the publisher as a **long-running process** for the whole
  run, draining outbox→Redis through the **Redis proxy**. It MUST survive/retry the partition (confirm the
  Go publisher's reconnect loop) or be **restarted** after the fault — the harness confirms it is actively
  draining before asserting, else the outbox never empties and every run is a silent `notrun`.
- **Sustained workload:** a loop of `wg -emit` rounds through the **PG proxy**. Rounds may **fail under
  pg-slow** (transactional rollback — *expected*, review LOW-1); the loop counts **successful** emits as
  the delivery baseline and never fails on a fault-induced rollback.
- **Concurrent faults under load:** inject **pg-slow** (latency) **∥** **redis-partition** (timeout),
  staggered/overlapping (S6 `toxic.sh` primitives), then clear.

### 3.3 Convergence oracle

- **PRIMARY — delivery-convergence (fault-sensitive).** After the partition clears and the publisher
  drains, assert **no-loss + dedup-able** (the at-least-once contract, per S8 G1) over the events emitted
  by *successful* rounds: `distinct(event_id) in Redis == events appended`, `XLEN >= events`, outbox
  **fully drained** (pending==0). Asserted **BEFORE** the laundering rebuild.
- **SECONDARY (sanity, acknowledged rebuild-laundered):** C3 (`wg -verify` ledger integrity) + a
  post-rebuild B (integrity-checker `drift==0`) + C2 (counts>0). Documented as not fault-sensitive — they
  confirm the end state is well-formed, they are not what the chaos proves.
- **Bite (non-vacuity, review HIGH-2) — targets DELIVERY, not the integrity-checker:** after a clean run,
  `XDEL` a delivered event from its Redis stream (simulate a lost delivery) → the no-loss check
  (`distinct == events`) MUST fail. (A non-vacuity proof of the *delivery* oracle, not the shared
  integrity-checker which S5/S8 already bite.)
- **Verdict:** fault-couldn't-inject / publisher-not-draining → `notrun` (2); delivery-convergence (or C3)
  violated → `fail` (1); clean → `pass` (0).

## 4. Antithesis-readiness — design

Concentrated in **`tests/antithesis/`** — **touches no production service**:
- **`driver/` (Go, `antithesis-sdk-go`)** — the "test template" entrypoint Antithesis would drive: runs an
  emit→publish→rebuild→integrity-check cycle against the up stack and records
  `assert_always(drift==0)` / `assert_sometimes(recovered after a fault)` / `assert_reachable(quiesce)` +
  `lifecycle.SetupComplete`. Outside Antithesis these are inert; the driver still runs the cycle and
  exits 0/1 so it is **locally runnable** (verifies it builds + the cycle works + assertions are no-ops).
- **`docker-compose.antithesis.yml`** — the test-composer: foundation-dev services + the driver as the
  singleton workload container.
- **`config/`** — the Antithesis singleton-driver layout + `antithesis.yaml`-style metadata.
- **`README.md`** — how to submit (push images → Antithesis), cost note, what H2 targets vs S1–S10, and the
  explicit `D-S11-ANTITHESIS-RUN` deferral.

## 5. Out of scope (tracked)

- `D-S11-ANTITHESIS-RUN` — the actual paid Antithesis run (needs an account + image push).
- `D-S11-FULL-APP-STACK` — chaos over the *entire LoreWeave app* (gateway + all domain services); S11's
  "whole stack" is the **foundation spine** (PG/Redis/MinIO + the spine workers), not the app fleet.

## 6. Acceptance criteria

- [ ] Local whole-stack chaos run: concurrent multi-service faults under load → **delivery-convergence**
      (no-loss/dedup-able, outbox drained) holds, asserted before the rebuild; C3 + post-rebuild B as
      sanity; the **delivery bite** (XDEL → no-loss fails) fires; persistent publisher survives the
      partition; re-runnable; verdict `{pass|fail|notrun}`.
- [ ] Conformance case + CI (nightly, live) wired; Antithesis driver `go build` gated per-PR (review LOW-3).
- [ ] `tests/antithesis/` driver builds + runs locally (assertions no-op; **shells the spine binaries**,
      review LOW-2); composer + config + docs present; `D-S11-ANTITHESIS-RUN` recorded.
- [ ] `/review-impl` on the plan AND the impl; findings folded.
- [ ] **Battery S1–S11 declared COMPLETE** in SESSION.
