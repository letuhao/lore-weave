# Runbook — Projection table loss / corruption (catastrophic rebuild)

> RAID cycle 14 — L3.H. Owned by SRE on-call. Reach the data-platform Slack
> channel within 5 minutes of paging.

## When to use this runbook

- A projection table is missing (`pg_relation_size` returns 0 unexpectedly)
- Integrity-checker (cycle 15 L3.E) reports drift on ≥ 10% of sampled rows
- A schema migration aborted mid-way and left the table in a half-migrated state
- Bulk corruption suspected (e.g. a buggy projection patch shipped + reverted,
  but already-written rows are wrong)

If the loss is contained to ONE projection on ONE reality, prefer the
non-catastrophic flow: `scripts/freeze-rebuild.sh` (cycle 14 DPS 2).

## Decision tree

```
1. Confirm scope
   ├─ single reality, single projection  → freeze-rebuild.sh  (DPS 2)
   ├─ multiple realities, OR multiple projections → CONTINUE (this runbook)
   └─ unsure → page data-platform lead BEFORE running anything destructive

2. Verify event log integrity (CANNOT rebuild from corrupt source)
   - Run: scripts/raid/verify-cycle-7.sh (event-log invariant check, cycle 7)
   - If event log itself is corrupt → STOP. Restore from L2.J archive first
     (runbooks/archive/restore.md).

3. Trigger catastrophic rebuild
   - Run --dry-run first to confirm scope:
       admin catastrophic-rebuild --scope=all-realities --dry-run \
         --actor "$ME" --reason "TICKET-1234: projection loss"
   - When dry-run summary matches expectations, re-run with --confirm:
       admin catastrophic-rebuild --scope=all-realities --confirm \
         --rolling-concurrency=50 --per-reality-timeout=30m \
         --actor "$ME" --reason "TICKET-1234: projection loss"

4. Monitor
   - Tail the orchestrator log: `lw logs admin-cli --follow`
   - Grafana board "L3.H catastrophic-rebuild progress" (panel:
     in_flight_realities <= 50 invariant)
   - Per-reality failures land in projection_rebuild_errors. Pause and
     inspect if failures > 5% of total.

5. After the run
   - For each reality in projection_rebuild_errors: re-run
     `freeze-rebuild.sh` with --confirm to retry single-reality.
   - Validate with integrity-checker forced sample (cycle 15 L3.E
     `--force-sample` mode).
   - Write a Postmortem in docs/sessions/SESSION_PATCH.md within 24h.
```

## Concurrency invariant

The orchestrator (`services/admin-cli/internal/rolling_rebuild/`) enforces
**MaxConcurrentSeen ≤ RollingConcurrency** at all times. If the metric panel
shows the cap exceeded, immediately:

1. `kill $(pgrep -f catastrophic-rebuild)` (each in-flight reality will
   thaw after timeout)
2. File a P0 against the rolling_rebuild lib — this is a load-bearing R02
   §12B.5 invariant

## Failure modes

| Symptom | Likely cause | Action |
|---|---|---|
| Reality stuck in `rebuilding` state | rebuilder crashed after freeze, before thaw | Inspect projection_rebuild_errors for that reality; once empty (or all dead-letter aggregates re-queued), run `admin thaw --reality <id>` manually |
| Per-reality timeout firing on 10+ realities | event log too large for the configured timeout | Increase `--per-reality-timeout` (max 30m); if still timing out, the reality needs a snapshot-first rebuild (see snapshot runbook) |
| Dead letter table grows during rebuild | per-aggregate `apply_event` failing on real corruption | Inspect failing event payloads with `lw events tail --aggregate <id>`; the upcaster (L2.H) may need a new step |
| MaxConcurrentSeen > cap | orchestrator bug | STOP immediately — see "Concurrency invariant" above |

## Q-IDs honored (cycle 14)

- **Q-L3-3** — Catastrophic rebuild = admin-cli sub-command + rolling_rebuild internal lib (this runbook uses ONLY that surface; no ad-hoc SQL).
- **Q-L3-5** — V1 freeze-rebuild approach (NOT blue-green). Each per-reality rebuild freezes that reality only; we do NOT spin a parallel projection table.

## Related runbooks

- `runbooks/archive/restore.md` — restore event log from MinIO archive
- `runbooks/degraded_mode/recovery.md` — clear post-rebuild degraded mode
- `runbooks/integrity/drift_alert.md` (cycle 15) — integrity-checker drift response
