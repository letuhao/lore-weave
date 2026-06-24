# Runbook — Per-Reality Orphan Resolution

> **Owner:** Platform SRE
> **Pages:** `lw_orphan_scanner_marked_partial > 0` for > 1h
> **Last verified:** 1970-01-01 (stub — full drill in cycle 7 SR2/SR3 sub-program)
> **Source:** L1.C.9; companion to `services/world-service/src/bin/orphan_scanner.rs`

## What is an orphan?

A per-reality DB whose state has drifted between the meta-side
`reality_registry` row and the shard-side `lw_reality_*` database.
Four canonical drift patterns:

| Class | Meta-side status         | Shard-side DB | Resolution                                           |
|-------|--------------------------|---------------|------------------------------------------------------|
| A     | `provisioning` for > 24h | absent        | Provisioner crashed mid-step. Re-run provisioner (idempotent) |
| B     | `provisioning` for > 24h | present       | Provisioner crashed AFTER step 4. Re-run provisioner |
| C     | `soft_deleted` for ≥ 7d  | present       | Grace expired. Re-run deprovisioner with `force=true` |
| D     | `soft_deleted` for ≥ 7d  | absent        | Drop the registry row (`status=dropped`); audit-only |

The scanner picks A/B (marked partial) + C/D (dropped automatically) in
its nightly run. SRE attention only required for marked-partial cases
that don't self-heal within 1 hour of the next scan window.

## Investigation checklist

1. **Identify the reality.** Pull the row from `reality_registry`:

   ```sql
   SELECT reality_id, db_host, db_name, status, status_changed_at
   FROM reality_registry
   WHERE reality_id = '<id>';
   ```

2. **Confirm the shard-side state.** On the matching shard, check:

   ```sql
   SELECT datname FROM pg_database WHERE datname = '<db_name>';
   -- if present:
   \c <db_name>
   SELECT count(*) FROM events;        -- 0 = empty skeleton
   SELECT * FROM projection_meta;
   ```

3. **Check the provisioner log** for the original attempt:

   ```bash
   kubectl logs -l app=world-service --since=48h | grep <reality_id>
   ```

4. **Choose a path:**
   - Class A or B: re-invoke the provisioner. It's idempotent — every step
     skips itself if it already happened.
   - Class C: invoke `admin reality force-close <reality_id> --reason "<text>"`
     (S5 Tier 2 audit path; available cycle 7+).
   - Class D: invoke `admin reality drop-row <reality_id> --reason "audit_orphan"`
     (also S5 Tier 2; the row stays in `reality_registry.status=dropped`
     forever as the audit record).

## Pre-conditions before you re-invoke the provisioner

- The shard host is healthy (Patroni leader available; see
  `runbooks/meta/failover.md` for the meta-side variant).
- Pgbouncer entry for the shard is registered (cycle 5 L1.G ships the
  per-shard config; check `pgbouncer:6432` is reachable).
- The provisioner has the original `ProvisionRequest` payload, OR you
  reconstruct it from `reality_registry` + the original audit row.

## Post-resolution

- Append a one-line note to `audit/orphan_resolution.log` with the
  reality_id, the class (A/B/C/D), and the action taken.
- If the same `reality_id` orphans twice, raise a `kind=defect` ticket
  against the provisioner — that means a step is non-idempotent.

## Common pitfalls

- **DO NOT** manually `DROP DATABASE` for class A/B realities — the
  provisioner will re-create it idempotently. Manual drop just races
  the scanner.
- **DO NOT** manually `DELETE` the `reality_registry` row — it would
  destroy the audit trail. Always go through the admin CLI's
  state-machine path.
- **DO NOT** lower `SOFT_DELETE_GRACE_DAYS` (7) without a written PR
  rationale. The 7-day window is a customer-facing promise (last chance
  to un-soft-delete a reality before its data is unrecoverable).
