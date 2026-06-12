# S5 — Standing integrity gate + parallel shards (Battery B)

**Plan date:** 2026-06-13 · **Branch:** `mmo-rpg/foundation-mega-task` · **Size:** L
**Spec:** `docs/specs/2026-06-04-foundation-runtime-test-plan.md` §2.1, §10 (S5) · **Depends on:** S3 ✅
**Build order:** `S1 → S3 → {S2,S2b,S4,S9} → **S5** → S6 → S7 → S8 → S10 → S11`

## Decisions taken at CLARIFY (user, 2026-06-13)
1. **Oracle depth = real B differential.** The gate runs the *actual* integrity-checker
   (`live.Checker`: sample row → `replay-aggregate` bin → `to_jsonb − meta` byte-compare),
   not a re-parallelization of the existing no-orphan / C3-ledger smokes. Closes/advances
   `D-WORKLOAD-GEN-INTEGRITY-DIFF` (the differential was never wired into a seeded smoke).
2. **Standing scope = runnable gate + results store AND the CI nightly cron.** Both the
   locally-verifiable gate and the `conformance-ci.yml` nightly schedule are in scope.

## The one sharp edge (why this is a *gate*, not just a run)
`services/integrity-checker` exits non-zero **only on a reality *error***; **drift→exit 0**
(drift is *persisted* to `projection_drift_state`, never gates the process — it's a
CronJob that pages via Prometheus, not via exit code). A gate must turn drift>0 into a
**failure**. So S5 = run the real binary, then **read its own persisted `drift_count`** as
the gate signal. We reuse the oracle's output; we do not reimplement the oracle.

## Production-shaped flow (`scripts/standing-integrity-gate-smoke.sh`)
Mirrors the proven `ledger-verify-smoke.sh` / `workload-gen-pipeline-smoke.sh` shape
(docker exec psql, prebuilt-binary-with-`go run`-fallback, re-runnable drop/create).

1. Bring up foundation PG; create meta DB `standing_gate_meta`, apply
   `contracts/migrations/meta/*.up.sql` (creates `reality_registry`).
2. **N shards in parallel** (`SHARDS`, default 4 — CockroachDB 50× lesson: parallel seeded
   shards raise rare-drift frequency, the correct mitigation for a *sampled* oracle). For
   each shard `i`, concurrently (background subshells + `wait`):
   - Create shard DB `standing_gate_shard_$i`; apply per-reality migrations
     `0001,0002,0005,0006,0007_drift_metadata,0008_pgvector,0009_canon` + events DEFAULT partition.
   - Seed `workload-gen -emit -seed $i -profile multi-reality` (distinct seed ⇒ distinct
     stream AND a distinct reality_id — `world.go:74` hashes the seed into every id, so the N
     registry rows never collide on the PK).
   - Rebuild every projection table via `target/debug/rebuilder` (`REALITY_DB_URL=shard DSN`)
     — **reusing the exact table list + invocation `workload-gen-pipeline-smoke.sh` proved
     clean**, incl. the `global`-path rebuild for the multi-aggregate
     `npc_session_memory_projection` (`D-REBUILDER-MULTI-AGG` fix), so a clean run can't go
     red for an unrelated rebuild reason (review-impl #7).
   - Register the shard in the meta DB: `INSERT reality_registry (reality_id=<the shard's
     actual reality_id from events>, db_host='pg-shard-1.internal', db_name='standing_gate_shard_$i',
     status='active', …)`.
   - **Background-job safety (review-impl #4):** `set -e` does NOT cross `( … ) &` boundaries.
     Capture each shard's PID, `wait $pid` per-pid, check each exit code, and abort the whole
     gate on any non-zero — a half-seeded shard must fail FAST with its real cause, not
     surface later as a confusing per-table coverage failure.
3. Run the **real integrity-checker binary** (daily mode) **once**, enumerating all N realities:
   `META_DATABASE_URL=<meta DSN>` · `SHARD_DB_USER/PASSWORD/PORT` ·
   `SHARD_DB_HOST_OVERRIDE='*=127.0.0.1:<PG_PORT>'` · `REPLAY_AGGREGATE_BIN_PATH=target/debug/replay-aggregate`.
   **Env (review-impl #3):** the resolver defaults an empty `SSLMode` to `require`
   (`resolver.go:60`); against the local non-TLS PG that makes every per-reality connect
   fail → reality error → exit 3. **`SHARD_DB_SSLMODE=disable` is mandatory**, not optional.
4. **Gate signal — drift AND coverage, both per-table (review-impl #1, the HIGH).**
   `SUM(drift_count)==0` ALONE is **vacuous**: `0007_drift_metadata` seeds all 10 rows with
   `drift_count DEFAULT 0`, `last_verified_at NULL`, `last_sample_size NULL`, so a table the
   checker never sampled (0 rows, or a seed/rebuild regression that empties it) keeps
   `drift_count=0` and is **invisible in the SUM** — the CockroachDB-2-year / spec-§2.1
   "hide a bug for months" failure mode applied to the gate's own coverage. The bite proves
   *drift detection*; **nothing here proves coverage** unless we assert it explicitly. So the
   gate, **per shard**, asserts ALL of:
   - binary exited 0 (no reality enumeration / connect / replay error), **and**
   - `SUM(drift_count) == 0` across **all N** shard DBs' `projection_drift_state`, **and**
   - **per-table coverage** over an EXPLICIT expected-populated set — for each of the **7**
     tables the generator populates
     (`pc_projection, pc_inventory_projection, npc_projection,
     npc_session_memory_projection, region_projection, world_kv_projection,
     session_participants`): `last_verified_at IS NOT NULL` **AND** `last_sample_size > 0`.
   The **3** L3.A tables the generator provably does NOT populate
   (`pc_relationship_projection, npc_pc_relationship_projection,
   npc_session_memory_embedding`) are a **documented, asserted exclusion** (assert they ARE
   in the seed set but expect 0 samples), never silently uncovered. (`canon_projection` is
   not in the L3.A allowlist at all → correctly outside Battery B.)
5. **Results store (review-impl #8):** write `tests/conformance/results/standing-gate-<runid>.json`
   (repo-root-relative; CWD is the runner's `absRoot`) — per-shard
   `{reality_id, db, tables:[{table, sample_size, last_verified_at, drift_count}], total_drift}`.
   Recording **coverage** (sample_size + last_verified_at), not just drift, is what makes the
   spec's §1/§10 "newly-failing vs chronically-skipped" history actually answerable.

## Non-vacuity — the bite-test (headline; `BITE=1` inline self-test)
Per the bite-test discipline ([[non-vacuity-bite-test-discipline]]): the green gate must be
*able* to go red, with the **byte-compare** (not a structural impossibility) being what
catches drift. After the clean sweep proves total_drift==0, the bite:
- Picks a bite table from the **confirmed-populated 7** and **asserts `rowcount > 0` first**
  — if 0, the harness **fails as a harness error** (exit ≥2 / notrun), NOT a vacuous bite
  "pass" (review-impl #2). Corrupting an empty table would no-op and falsely read non-vacuous.
- **Corrupts the ENTIRE table** in one shard (e.g.
  `UPDATE <table> SET <col> = <col> || '__BITE__'`) — whole table, **not one row**, so the
  daily **sampler cannot miss it** (a single-row corruption would be a flaky bite under
  sampling non-determinism). `<col>` is a text column verified to exist in
  `0006_projections` AND **not** one of the 5 stripped meta keys (`event_id`,
  `aggregate_version`, the verification-HWM cols, …) — else the `to_jsonb − meta` compare
  ignores it and the bite silently passes (review-impl #2).
- Re-runs the checker, asserts `drift_count > 0` for that shard's table → gate goes **red**.
The clean(0)→corrupt(>0) transition is the standing proof the differential has teeth.
A bite that does *not* fire is a harness bug, not a pass.

## Conformance case (`tests/conformance/catalog/generic/standing-integrity-gate.yaml`)
```
id: standing-integrity-gate
invariant: I-projection-equals-replay   (Battery B)
kind: live-probe
command: ["bash", "scripts/standing-integrity-gate-smoke.sh"]
requires: ["foundation-stack"]        # bare runner → notrun (no false green)
fail_closed_on_setup_error: false
```
The smoke runs the bite inline (clean must be 0 **and** corrupt must be >0 within the same
invocation) so the conformance pass *embeds* the non-vacuity proof.

## CI nightly cron (`.github/workflows/conformance-ci.yml`)
Add a second job `standing-integrity-nightly`, `on: schedule: - cron: '0 7 * * *'` +
`workflow_dispatch` (the existing push/PR job stays bare-runner / notrun). It boots
foundation PG+Redis via `infra/foundation-dev/docker-compose.yml`, builds
`rebuilder` + `replay-aggregate` (cargo) + `workload-gen` (go), then runs the conformance
runner over the live battery and uploads `results/`. **Verification honesty (review-impl #5):**
two compounding reasons VERIFY cannot observe this cron fire — (a) it is not bootable on the
Windows dev box, and (b) **GitHub Actions runs `schedule:` only from the default branch**, so
on `mmo-rpg/foundation-mega-task` the nightly is **dormant until merged to `main`**. Confidence
rests *solely* on its steps being a line-for-line mirror of the locally-verified smoke, plus a
**one-time manual `workflow_dispatch` after merge** to confirm it boots. VERIFY records
`live infra unavailable: GH-Actions schedule fires only on main` for the CI portion and carries
the live gate smoke as the real evidence; the plan does NOT claim VERIFY ran the cron.

## Increments (each: BUILD → VERIFY live → checkpoint)
- **Inc 1 — gate smoke:** seed N shards in parallel + meta registry + run real checker +
  drift-sum gate + sample-size floor + results JSON. VERIFY: live, 4 shards, total_drift=0, exit 0.
- **Inc 2 — bite/non-vacuity:** `BITE=1` corrupts a full table → drift>0 detected; clean stays 0.
  VERIFY: both polarities live.
- **Inc 3 — conformance case:** the YAML; VERIFY through the runner via isolated temp catalog
  (pass on stack; notrun on a bare shell).
- **Inc 4 — CI nightly + docs:** the `standing-integrity-nightly` job; SESSION_PATCH; advance
  `D-WORKLOAD-GEN-INTEGRITY-DIFF` (now covered by the seeded differential) + note
  `D-CONFORMANCE-LIVEPROBE-CONTAINER-CHURN` interaction.

## Risks / mitigations
- **A red CLEAN run is a real discovery, not a harness bug (review-impl #6).** This gate is
  the *first* byte-compare of rebuilder output vs `replay-aggregate` over seeded data — the
  exact gap `D-WORKLOAD-GEN-INTEGRITY-DIFF` tracks. If they disagree, the clean sweep is red
  and S5 VERIFY is blocked by a genuine pre-existing differential bug. Correct response:
  **triage** (which table drifts, which side is truth — rebuilder or replay) and treat it as
  the gate doing its job; do NOT loosen the gate to force green.
- **Container churn** (`D-CONFORMANCE-LIVEPROBE-CONTAINER-CHURN`): the gate creates its own
  meta+shard DBs on the shared PG and does **not** `docker compose up` other services, so it
  won't recreate the container mid-run; verify in isolation via `-catalog ./catalog/_tmp`.
- **Sampler vs bite:** corrupt the whole table (above) — the only robust defeat of sampling.
- **replay-aggregate availability:** the gate requires `target/debug/replay-aggregate`
  (built like the rebuilder); absent → exit ≥2 → notrun (not a false green), same as the
  existing pipeline smoke's rebuilder guard.

## Out of scope (tracked, not silently dropped)
- Monthly full-scan (`full_check`) over the shards — daily sampled differential is the S5
  battery; full-scan gate is a later concern.
- True multi-host shards — dev remaps all logical hosts to one PG via `SHARD_DB_HOST_OVERRIDE`
  (the production resolver path is still exercised; only the physical host collapses).
