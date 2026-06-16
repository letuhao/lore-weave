# Runbook — Monthly full integrity check failure

**Pager source:** LWProjectionMonthlyDriftDetected

**Service:** `services/integrity-checker` (L3.F monthly mode)

---

## What this alert means

The MONTHLY full-scan integrity check (L3.F) walks EVERY row of EVERY
L3.A projection table for a reality. Unlike the daily L3.E sampler
(20-row sample per table), monthly is supposed to be ALL-GREEN. Any
non-zero drift in monthly is load-bearing.

A `mode="monthly"` error increment on `lw_projection_check_runs_total`
means either:

1. **Real drift detected at full scan.** The daily sampler missed it
   because the drifted rows weren't sampled. This is the worst case —
   investigate immediately.

2. **Full scan ran out of time** (>1h activeDeadline). The cronjob is
   killed and counted as error. May indicate the reality grew larger
   than estimated; bump the `FullScanBatchSize` config or scale the
   cronjob CPU.

3. **Cursor source bug** (`cursor did not advance`). Hard fail in
   `pkg/full_check`. Should not happen in production once live-wired;
   file a ticket against the integrity-checker code.

---

## Triage flow

1. **Identify the cause.** Check the monthly pod logs:
   ```bash
   kubectl logs -n world-platform -l app.kubernetes.io/component=monthly --tail=300
   ```
   Look for:
   - `full_check: cursor did not advance` → cause 3
   - `cancelled mid-scan after N rows` → cause 2 (deadline)
   - `drift_count = K (K > 0)` → cause 1 (real drift)

2. **For cause 1 (real drift):** follow `runbooks/integrity/drift_alert.md`
   procedure step 1+. The per-table `projection_drift_state` row holds
   `last_drifted_aggregate_id` for investigation.

3. **For cause 2 (deadline):** check the row count of the offending
   reality's projections:
   ```sql
   SELECT relname, n_live_tup
   FROM pg_stat_user_tables
   WHERE relname LIKE '%_projection'
     OR relname IN ('session_participants', 'npc_session_memory_embedding')
   ORDER BY n_live_tup DESC;
   ```
   If a table exceeds the L3.F acceptance bar (10K aggregates), tune
   `contracts/integrity/config.yaml` `full_scan_batch_size` UP (eg 500 → 2000)
   and/or bump the CronJob's `activeDeadlineSeconds`.

4. **For cause 3 (cursor bug):** see the integrity-checker source +
   open a P1 ticket against the integrity-checker code. The bug is
   serious — every monthly run will fail until fixed.

---

## Mitigation

- **Disable the monthly cron temporarily** (do NOT disable daily):
  ```bash
  kubectl patch cronjob integrity-checker-monthly -n world-platform \
    -p '{"spec":{"suspend":true}}'
  ```
  Then file a ticket + fix root cause.

- **Re-run monthly manually after fix:**
  ```bash
  kubectl create job --from=cronjob/integrity-checker-monthly \
    integrity-checker-monthly-manual-$(date +%s) -n world-platform
  ```

- **Force a rebuild if monthly drift > L3.H threshold:**
  ```bash
  admin-cli catastrophic-rebuild --scope=reality --reality-id=<id> --confirm
  ```
  See `runbooks/disaster/projection_loss.md`.

---

## Source references

- `services/integrity-checker/pkg/full_check`
- `contracts/integrity/config.yaml` — `full_check_interval_days`, per-table
  `full_scan_batch_size`
- `infra/k8s/integrity-checker-cronjob.yaml` — `activeDeadlineSeconds`
- L3.F spec: `docs/plans/2026-05-29-foundation-mega-task/L3_snapshot_projection.md`
- Q-L3E-1 LOCKED: same binary as daily, just different cron + mode override
