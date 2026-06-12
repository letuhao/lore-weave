# Runbook — Projection drift alert

**Pager source:** LWProjectionDriftWarning / LWProjectionDriftCritical /
LWProjectionLagWarning / LWProjectionLagCritical / LWProjectionStaleVerification

**Service:** `services/integrity-checker` (L3.E daily + L3.F monthly)

**Source metric**: see alert `source_metric` label.

---

## TL;DR triage (60s)

| Symptom | First check | Action |
|---|---|---|
| `LWProjectionDriftWarning` (drift_count > 0, 3m) | Look at `{{ $labels.table }}` + `{{ $labels.reality_id }}` | Watch for 15m — if it escalates to Critical, page is automatic. Otherwise, file a ticket and triage in business hours. |
| `LWProjectionDriftCritical` (drift_count > 5, 15m) | Same as above + check `last_drifted_aggregate_id` via psql | Triage NOW. Likely projection-runner bug or partial corruption. Mark reality for L3.D parallel rebuilder run. |
| `LWProjectionLagWarning` (lag > 60s, 5m) | Check publisher health (`lw_publisher_*` metrics) + downstream pgbouncer connection saturation | Likely consumer backed up — let it self-heal up to 5m, then escalate if hits Critical. |
| `LWProjectionLagCritical` (lag > 300s, 10m) | Same + check the per-reality DB load + WAL size | Page is correct. Restart the projection runner if pgbouncer/DB is healthy; otherwise escalate to DB on-call. |
| `LWProjectionStaleVerification` (last_check > 7d) | Check the integrity-checker CronJob status: `kubectl get cronjob -n world-platform integrity-checker-daily` | The CHECKER is broken, not the projection. Get the checker running before believing any other alert in this set. |

---

## Drift investigation procedure

When `LWProjectionDriftCritical` fires:

1. **Identify the drifted aggregate(s).** psql into the per-reality DB:
   ```sql
   SELECT table_name, drift_count, last_drifted_aggregate_id, last_drifted_event_id,
          last_verified_at, updated_at, notes
   FROM projection_drift_state
   WHERE drift_count > 0;
   ```

2. **Confirm the drift by re-running the sampler manually** (do not wait
   for the next cron):
   ```bash
   kubectl exec -n world-platform deploy/integrity-checker -- \
     /bin/integrity-checker --config=/etc/integrity-checker/config.yaml \
       --mode-override=daily --reality-id=<reality>
   ```
   If the drift is gone after a manual re-run, it was transient (likely a
   row updated mid-sample). File a ticket but do not page out.

3. **If drift persists, diff the projection vs replay.** psql:
   ```sql
   -- projection state
   SELECT row_to_json(t) FROM <table> t
   WHERE aggregate_id = '<last_drifted_aggregate_id>'
     AND aggregate_version = '<looked up from drift_state>';
   ```
   Then re-run the L3.C `load_aggregate` reader against the same aggregate
   (via the `integrity-checker --debug-aggregate <id>` flag — DEFERRED to
   D-PUBLISHER-LIVE-WIRING; for cycle-15 era, dump the projection row +
   the relevant events from `events` and inspect manually).

4. **Cause classification.** Common causes ranked by frequency:
   - **A. Projection-runner bug** — `apply_event` doesn't match the
     replay reference. FIX in the projection crate, then rebuild via
     L3.D rebuilder.
   - **B. Schema migration mid-flight** — a column was added but
     existing rows haven't been backfilled. Wait until the L3.G
     freeze-rebuild completes, then re-run integrity-check.
   - **C. Direct DB tampering** — someone manually `UPDATE`d the
     projection row (forbidden but possible). Audit the per-reality
     DB connection log, then rebuild via L3.D.
   - **D. Data corruption** — disk error / replication lag. Engage
     DB on-call.

5. **Remediation: L3.D rebuilder.** For cases A, B, C:
   ```bash
   admin-cli rebuild-projection \
     --reality=<reality_id> \
     --table=<table_name> \
     --actor="<oncall>" --reason="LWProjectionDriftCritical alert: <ticket-id>" \
     --confirm
   ```
   See `runbooks/disaster/projection_loss.md` for the L3.D + L3.H details
   (parallel rebuild + freeze-rebuild + catastrophic).

---

## Stale verification recovery

When `LWProjectionStaleVerification` fires (the checker itself is broken):

1. **Check the cronjob.**
   ```bash
   kubectl get cronjob -n world-platform integrity-checker-daily
   kubectl get jobs -n world-platform -l app.kubernetes.io/name=integrity-checker --sort-by=.metadata.creationTimestamp | tail -5
   ```
   Look for "successful=0" or "lastSchedule=<old>".

2. **Inspect the most recent job pod logs.**
   ```bash
   kubectl logs -n world-platform -l app.kubernetes.io/name=integrity-checker --tail=200
   ```
   Common failures:
   - **Config validation** — `FATAL: validate config` → check the
     ConfigMap. Most likely a typo'd table name (allowlist enforcement).
   - **DATABASE_URL not set / not reachable** — check the secret + the
     per-reality DB credentials rotation log.
   - **Cursor stuck** — `full_check: cursor did not advance` → a buggy
     CursorSource binding. File ticket + drop monthly cron until fixed.

3. **Manual run to unstick.**
   ```bash
   kubectl create job --from=cronjob/integrity-checker-daily \
     integrity-checker-manual-$(date +%s) -n world-platform
   ```

4. **If the checker has been broken > 7d:** consider running a FULL check
   manually (mode=monthly) once it's back up, since daily mode only
   samples N rows; we want to verify drift didn't accumulate during the
   blackout.

---

## Inhibit + dependency notes

- **Daily drift WARN is inhibited during monthly full-check runs** (in
  alertmanager config). Monthly mode produces high expected counts during
  schema-migration backfills; we don't want the daily WARN to spam-page.
- **Stale verification is inhibited when the SR02 service-down pipeline
  reports integrity-checker pod down.** No point complaining about
  stale checks when the checker can't run.
- **L3.J alerts cross-reference L3.D rebuilder** — the rebuilder is the
  remediation tool. See `runbooks/disaster/projection_loss.md`.

---

## Source-of-truth references

- Alerts: `infra/prometheus/alerts/projection.yaml`
- Metrics: `services/integrity-checker/pkg/metrics`
- Inventory: `contracts/observability/inventory.yaml` (search `lw_projection_*`)
- Drift table: `contracts/migrations/per_reality/0007_drift_metadata.up.sql`
- Q-L3E-1 LOCKED: `docs/plans/2026-05-29-foundation-mega-task/OPEN_QUESTIONS_LOCKED.md` §5
