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

### Wave 1 — Production wiring (Category B) — ✅ COMPLETE (2026-06-14)
Closed the "design proven but unwired" gap; L1 is now production-runnable. Shipped
as one bundled XL task, 6 increments, each with a live drill + non-vacuity bite +
a `w1-*` conformance case + CI (scale-build/w1-rust-build per-PR; scale-nightly live).
1. ✅ **W1.1 capacity routing glue** (`33bb2e83`) — live snapshot from `shard_utilization` caps × a fresh `reality_registry` count (NOT the unbuilt `current_db_count` metric); per-shard advisory lock around count→recount→register closes the over-subscription TOCTOU. NO snapshot DB CHECK (metrics must observe over-subscription). Bite: lock-off → over-subscription reproduced. **D-S13-CAPACITY-ROUTING-GLUE cleared.**
2. ✅ **W1.2 migrate CLI live wiring** (`6ff491f0`) — `cmd/migrate` bound to pgx SQLApplier + DSN resolver + MetaWrite audit/state (I8); breaking → canary, else → runner. Bite: ignore-canary fans out → guard non-vacuous. **D-MIGRATE-CLI-LIVE-WIRING cleared.**
3. ✅ **W1.3 closure-drain orchestrator** (`d92d8b1b`) — `active→pending_close` (freezes appends via W1.4) → drain outbox to 0 → `→frozen`; drain-timeout aborts to `active` (never forces frozen). Bite: naive close strands events. **D-S13-CLOSURE-DRAIN cleared.**
4. ✅ **W1.4 relocate/closure write-freeze** (`700388ab`) — dp-kernel append rejects frozen states via an UNCACHED meta status read (freeze-settle option b → no settle window). Bite: guard-off append during `migrating` lands. **D-S13-RELOCATE-FREEZE cleared.**
5. ✅ **W1.5 provisioner + Rust→Go meta-write bridge** (`f2364527`) — scoped internal bridge on meta-worker (register/transition, fail-closed token, s2s audit, idempotent, dual-role shutdown) + Rust `LiveEffects` (CREATE DATABASE + `REVOKE CONNECT` I4 + skeleton; register/transitions via the bridge, I8). Live provision-drill end-to-end + REVOKE/I8 bites. **D-S4-I4-PROVISIONER core cleared** (pgbouncer/prometheus/backup stay go-live).
6. ✅ **Inc-6** — 5 `w1-*` conformance cases (requires scale-rig) + CI: `scale-build` (Go build/vet/test) + `w1-rust-build` (Rust bins + unit suites) per-PR, `scale-nightly` live sweep (provision drill cross-language, nightly-only).

### Wave 2 — Spine hardening & fault coverage (Category A) — ✅ COMPLETE (2026-06-15, except clock-skew deferred)
Shipped as one bundled XL task (spec/plan `docs/{specs,plans}/2026-06-15-wave2-spine-hardening.md`).
Each = a live drill + non-vacuity bite + a `w2-*` conformance case + CI (the WSL2-
unverifiable drills are CI-verified on the Linux nightly, honest notrun locally).
6. ✅ **W2.1 sustained-workload generator mode** (`a24cd868`) — `-duration`/`-rate` steady loop (seed-delta per iter → disjoint aggregates). Bite: one-shot burst ≪ floor. **D-S6-SUSTAINED-WORKLOAD cleared.**
7. ✅ **W2.2 history ordering** (`c7515e5e`) — `CheckAggregateMonotonicity` over recorded order. Bite: a reorder fails it while completeness passes. **D-S6-HISTORY-ORDERING cleared.**
8. ✅ **W2.4b partition-boundary rollover** (`fe9dc2af`) — events across a month boundary replay; missing next-month partition is rejected (no default partition). Bite: M+2 INSERT rejected. **D-S6-PARTITION-ROLLOVER cleared.**
9. ✅ **W2.5 async bulkhead shuttle** (`7996d916`) — shuttle model-check of the admission algorithm + over-admission bite. **D-S6-BULKHEAD-SHUTTLE cleared** (literal tokio-bulkhead async check → D-W2-BULKHEAD-SHUTTLE-LITERAL).
10. ✅ **W2.3a service RSS soak + W2.3b disk read-thrash** (Inc-6 commit) — real-publisher RSS plateau (`/proc`) + fio cgroup read-thrash; **Linux-CI-only** (notrun on WSL2; the rss-soak BITE is locally verified). **D-S14-SERVICE-RSS-SOAK + D-S14-DISK-READ-THRASH cleared.**
11. ⏸ **W2.4a clock-skew recovery** (D-S8-CLOCK-SKEW-RECOVERY) — **STILL DEFERRED** (not shipped vacuously): the spine orders by DB-side `now()`, so app-clock skew is a non-event by design; a non-vacuous drill needs libfaketime-wrapped postgres to skew the DB clock (the W2.2 monotonicity check is the ready oracle). Deferred to a Linux session with libfaketime-on-postgres.

### Wave 3 — Oracle / generator completeness (un-vacuum the batteries) — ✅ COMPLETE (2026-06-15)
> Implemented as 6 increments (`docs/plans/2026-06-15-wave3-oracle-generator-completeness.md`), batch cadence, /review-impl on the plan AND on the load-bearing W3.4 impl. Commits: W3.1 `48d380cf`, W3.2 `5a3c16af`, W3.3 `3f5e549a`, W3.4 `0b099d79`. W3.5 (published-recon) → documented DEFER (no crisp high-water source). W3.6 → conformance `w3-*` cases + CI (scale-build W3 go-test + bash -n; scale-nightly live sweep incl gated kernel checksum test; lint-foundation `meta-actor-uuid-lint`).
11. **W3.1 generator events** — ✅ D-WORKLOAD-GEN-NPC-REL-EMBED (generator+embed; rel-projection-row → D-W3-NPC-REL-PROJECTION-UPSERT) + ✅ D-S5-WORLDKV-NETS-EMPTY.
12. **W3.4 ledger** — ✅ D-LEDGER-STORED-CHECKSUM (content_sha256 over payload+metadata; dp-kernel append + Go emit write path; LOAD-BEARING /review-impl folded — extended coverage to metadata, vacuity guard, exact-count bites) + ⏸ D-LEDGER-PUBLISHED-RECON (DEFER — no crisp high-water).
13. **W3.2 schema-derived table lists** — ✅ D-PROJCHECK-TABLE-DRIFT + ✅ D-S4-VERIFMETA-TABLE-SYNC (N/A-with-evidence: tablemap is guarded-curated).
14. **W3.3 conformance hygiene** — ✅ D-META-FAKEDB-UUID-ACTOR (lifecycle UUID fixtures + CI lint w/ selftest bite) + D-CONFORMANCE-FLEET-MIGRATION / D-CONFORMANCE-LIVEPROBE-CONTAINER-CHURN (folded — W3 cases follow the established assume-up/notrun + requires-gated convention).
> New Wave-3 deferred (tracked in SESSION_PATCH): D-W3-NPC-REL-PROJECTION-UPSERT, D-MANIFEST-0009-0012-UNREGISTERED, D-CHECKSUM-PROVISIONING-APPLY, D-CHECKSUM-EXPR-CROSS-LANG-DRIFT, D-CHECKSUM-PG-VERSION-STABILITY, D-LEDGER-PUBLISHED-RECON.

### Wave 4 — Model / perf refinements (lowest urgency) — ✅ COMPLETE (2026-06-15)
> Max scope (user-chosen); `docs/plans/2026-06-15-wave4-model-perf-refinements.md` (plan /review-impl'd `c08dd790`). 5 build + 2 defer.
15. ✅ D-S7-USL-NO-N1 (W4.1) · ✅ D-S12-T0T1-MICRO (W4.2) · ✅ D-S7-PGVECTOR-RECALL (W4.3) · ✅ D-S9-MODEL-SCOPE (W4.4) · ✅ **D-C2-REFERENCE-PROJECTOR** (W4.6, the optional reference projector — BUILT as a DDL+contract conformance oracle + reproduction reference, LOAD-BEARING /review-impl folded) · W4.7 conformance(`w4-*`)/CI.
> Deferred-with-evidence: ⏸ D-S9-FANOUT-SUBSCRIBER-SOURCE (W4.5 — 026 is pure membership, already modeled parametrically) · ⏸ D-S11-LIVENESS-TLA (needs TLA+/TLC). New: D-PROJREF-COLUMN-DDL-DRIFT.

> **▶ The entire post-S14 deferred-cleardown (Wave 1–4) is COMPLETE.** Wave 1 (production wiring), Wave 2 (spine hardening), Wave 3 (oracle/generator completeness + the upsert hardening), Wave 4 (model/perf refinements) all shipped with non-vacuity bites + conformance(`w1/w2/w3/w4-*`)/CI. Remaining deferred rows are go-live/infra/research items (none do-now).

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
