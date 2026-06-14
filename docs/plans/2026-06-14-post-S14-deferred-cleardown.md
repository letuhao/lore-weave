# Post-S14 deferred clear-down — triage + do-now plan

After the S1–S14 foundation test program, this triages every OPEN deferred by **when
it can be done** (now / at-go-live / post-go-live / feature-blocked) and lays out a
prioritized plan to clear the **do-now** set first.

Source ledger: `docs/sessions/SESSION_PATCH.md` Deferred table + the S12–S14 inline
rows. (P1/P2/P3 extraction-track deferreds are a SEPARATE program, not covered here.)

Architecture verdict (recap): **validated, no from-scratch refactor.** The do-now
Category-B items are "principle proven → wire it to production"; the rest are deeper
test coverage. The 3 real defects testing found (I7 XACK, lifecycle-audit atomicity,
+ per-slice review catches) are already fixed.

---

## Triage

### ✅ DO NOW (no prod infra, no go-live, no spend — buildable + testable on dev/rig/Linux-CI)

**B — production wiring (highest value: design proven, not yet wired):**
- D-S13-CAPACITY-ROUTING-GLUE — wire `CapacityPlanner` to read live `shard_utilization`; add the over-subscription DB CHECK
- D-MIGRATE-CLI-LIVE-WIRING — bind the `migrate` CLI to a real MetaWriter + per-reality Applier (the S13 canary-drill pattern, productionized)
- D-S13-CLOSURE-DRAIN — automated R09 closure-drain orchestrator (drain outbox to publisher high-water before `→frozen`)
- D-S13-RELOCATE-FREEZE — write-freeze guard: reject event appends to a reality whose status=`migrating`
- D-S4-I4-PROVISIONER (**core**) — per-reality `CREATE DATABASE` + role/`REVOKE` privilege bootstrap via the real `Effects` impl (pgbouncer/prometheus/backup sub-steps → go-live)

**A — spine hardening & coverage (dev-doable test technique):**
- D-S6-HISTORY-ORDERING — per-aggregate version-monotonicity in the history checker
- D-S6-SUSTAINED-WORKLOAD — generator sustained/loop mode → unlocks genuine transient-during-fault
- D-S6-PARTITION-ROLLOVER — time-advancing partition-boundary replay harness
- D-S6-BULKHEAD-SHUTTLE — `shuttle` race-check of the tokio async bulkhead
- D-S8-CLOCK-SKEW-RECOVERY — clock-control (libfaketime/container) recovery drill
- D-S14-SERVICE-RSS-SOAK — soak the real long-lived services (publisher tail / consumers), not a pure-alloc loop
- D-S14-DISK-READ-THRASH — dataset>RAM read thrash via fio + cgroup mem on **Linux CI** (WSL2 can't constrain the page cache)

**A — oracle/generator completeness (un-vacuum existing batteries):**
- D-WORKLOAD-GEN-NPC-REL-EMBED — emit `npc.relationship_changed` + `npc.memory_embedded` (two projection arms get 0 coverage today)
- D-S5-WORLDKV-NETS-EMPTY — a set-without-unset generator variant so `world_kv_projection` has a row to verify
- D-LEDGER-STORED-CHECKSUM — `events.payload_sha256` column + write-path (production byte-rot without a seeded baseline)
- D-LEDGER-PUBLISHED-RECON — reconcile `outbox.published` against the publisher high-water
- D-PROJCHECK-TABLE-DRIFT + D-S4-VERIFMETA-TABLE-SYNC — derive the projection-table list from the live schema (kill the two hardcoded copies)
- D-META-FAKEDB-UUID-ACTOR — UUID actor_ids in the meta fake-DB fixtures (match real schema)
- D-CONFORMANCE-FLEET-MIGRATION — fold the remaining ~26 lints + ~4 live-smokes into the catalog
- D-CONFORMANCE-LIVEPROBE-CONTAINER-CHURN — sibling live-probe scripts stop `compose up` (assume-up + notrun)

**A — model/perf refinements (lower urgency, dev-doable):**
- D-S9-MODEL-SCOPE — raise Stateright bounds / add H1-loom at impl altitude
- D-S9-FANOUT-SUBSCRIBER-SOURCE — derive the subscriber set from the real subscription source
- D-S12-T0T1-MICRO — micro-bench the T0/T1 kernel tick path
- D-S7-USL-NO-N1 — USL robustness when the sweep omits N=1
- D-S7-PGVECTOR-RECALL (= D-S4-PGVECTOR-RECALL) — ANN recall/quality comparator on seeded vectors
- *optional/low-value:* D-S7-FORTIO-WRK2, D-S7-WS-K6-PROTOCOL, D-S9-LIFECYCLE-LIVENESS-TLA, D-C2-REFERENCE-PROJECTOR

### 🚀 AT GO-LIVE (needs production topology / infra / secrets)
- D-S6-META-HA-SPLITBRAIN — HA meta cluster (Patroni + etcd); not in dev compose
- D-S6-MAELSTROM-HISTORY — full Jepsen/Elle; tied to the HA split-brain path
- D-S12-MULTI-HOST — Phase-2 multi-host cluster cert ($)
- D-S7-BENCHER-CI-AUTOMATION — hosted Bencher + bootstrapped token secret in CI
- D-S4-I4-PROVISIONER (**peripheral**) — pgbouncer/prometheus-scrape/backup-policy registration (those subsystems are go-live infra)

### ⏳ POST GO-LIVE (needs accumulated data / live traffic / spend)
- D-S7-BENCHER-CHANGEPOINT — needs a multi-commit perf series to graduate off fixed-%
- D-S12-LLM-LATENCY-AT-SCALE — real registered LLM models under production load
- D-S11-ANTITHESIS-RUN — paid Antithesis run (submit-ready; human spend decision — could be triggered anytime, but it's a $ gate not a dev task)
- *(D-LEDGER-STORED-CHECKSUM's production VALUE is post-go-live, but the build is do-now)*

### 🔒 FEATURE-BLOCKED (do when the dependent feature lands, independent of go-live)
- D-S10-TRAVEL-SIM — when travel aggregates (TVL_001..005) exist
- D-S10-MADSIM-NET — when >1 service has cross-service behavior
- D-S10-SQLX-SIM — the whole-stack DST tier (S11/Antithesis), not H1
- D-C-DETERMINISTIC-REBUILD — when a non-deterministic projection path appears

---

## Do-now plan (4 waves, priority order)

Each item ships the project discipline: spec/plan for L+, `/review-impl` on plan +
impl, a **non-vacuity bite**, conformance case + CI where it's a runtime check.

### Wave 1 — Production wiring (Category B) — START HERE
Closes the "design proven but unwired" gap; makes L1 production-runnable. Highest value.
1. **W1.1 capacity routing glue** — read `shard_utilization` → `ShardCapacity` snapshot → `pick_shard` at provision time; add `current_db_count <= capacity_max_dbs` DB CHECK. Bite: over-subscribe with the read-glue bypassed → caught.
2. **W1.2 migrate CLI live wiring** — bind `cmd/migrate` cmdApply to a real MetaWriter (→ MetaWrite) + per-reality Applier (real migration SQL); breaking → canary, else → runner. Bite: a broken migration aborts at the canary (reuse the S13 abort-path bite live).
3. **W1.3 closure-drain orchestrator** — on `active→pending_close`, drain the reality's outbox to the publisher high-water before allowing `→frozen`; abort restores `→active`. Bite: un-drained outbox + force `→frozen` → caught (closes D-S13-CLOSURE-DRAIN).
4. **W1.4 relocate write-freeze** — reject event appends when `reality_registry.status='migrating'` (or `pending_close`); the relocation/closure paths rely on it. Bite: append during `migrating` succeeds with the guard off → lost-on-flip (closes D-S13-RELOCATE-FREEZE, hardens Inc-4).
5. **W1.5 provisioner core** — real `Effects`: `CREATE DATABASE` on the picked shard + per-service role + `REVOKE CONNECT` privilege bootstrap; register_pending→MetaWrite; transition_to→AttemptStateTransition. Makes the `db-per-service-isolation` conformance case a real probe (closes D-S4-I4-PROVISIONER core; peripheral steps stay go-live).

### Wave 2 — Spine hardening & fault coverage (Category A)
6. **W2.1 sustained-workload generator mode** (D-S6-SUSTAINED-WORKLOAD) — a loop/steady-rate driver; prerequisite for genuine transient-during-fault. Do first in the wave.
7. **W2.2 history ordering** (D-S6-HISTORY-ORDERING) — per-aggregate version monotonicity over the stream.
8. **W2.3 service RSS soak + disk read-thrash** (D-S14-SERVICE-RSS-SOAK, D-S14-DISK-READ-THRASH on Linux CI/fio).
9. **W2.4 clock-skew recovery** (D-S8-CLOCK-SKEW-RECOVERY) + **partition-boundary rollover** (D-S6-PARTITION-ROLLOVER).
10. **W2.5 async bulkhead shuttle** (D-S6-BULKHEAD-SHUTTLE).

### Wave 3 — Oracle / generator completeness (un-vacuum the batteries)
11. **W3.1 generator events** — D-WORKLOAD-GEN-NPC-REL-EMBED + D-S5-WORLDKV-NETS-EMPTY (un-vacuums B/C2 arms).
12. **W3.2 ledger** — D-LEDGER-STORED-CHECKSUM (payload_sha256 + write path) + D-LEDGER-PUBLISHED-RECON.
13. **W3.3 schema-derived table lists** — D-PROJCHECK-TABLE-DRIFT + D-S4-VERIFMETA-TABLE-SYNC.
14. **W3.4 conformance hygiene** — D-META-FAKEDB-UUID-ACTOR + D-CONFORMANCE-FLEET-MIGRATION + D-CONFORMANCE-LIVEPROBE-CONTAINER-CHURN.

### Wave 4 — Model / perf refinements (lowest urgency)
15. D-S9-MODEL-SCOPE, D-S9-FANOUT-SUBSCRIBER-SOURCE, D-S12-T0T1-MICRO, D-S7-USL-NO-N1, D-S7-PGVECTOR-RECALL (+ optional FORTIO/WS-K6/LIVENESS-TLA/C2-REFERENCE-PROJECTOR as appetite allows).

---

## Notes
- **Housekeeping (do alongside Wave 1):** prune the cleared rows from the SESSION_PATCH
  Deferred table (D-WORKLOAD-GEN-REAL-SHARD, D-S7-SOAK-LAG-METRIC, D-S8-MULTI-SHARD-DR
  marked open but cleared in S12; D-S5-SHARD-MULTI-REALITY-ATTRIB cleared S13;
  D-S12-RSS-MEMORY-SOAK cleared S14).
- Wave 1 items are load-bearing (write path, meta, provisioner) → production-shaped,
  `/review-impl` before commit (per [[prefers-production-shaped-on-spine]]).
- Waves are independent; can reorder. Recommended: W1 first (production value), then
  W2/W3 (coverage), W4 last.
