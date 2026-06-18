# Observability admission — V1 → V1+30d migration runbook

> **LOCKED:** Q-L6F-1 (foundation ships V1+30d as flag-flip at config; admin can flip earlier).
> **Scope:** All `lw_*` metric emissions across foundation services.
> **Owner:** SRE primary; observability team is consulted.

## 1. What this migration changes

| Stage | Admission mode | Behavior on UNREGISTERED metric |
|---|---|---|
| **V1** (ship date → V1+30d) | `AdmissionWarn` | Warning log + counter increment + breach row written; emission **DROPPED** (not recorded). |
| **V1+30d** (flag flip) | `AdmissionReject` | `ErrUnregisteredMetric` returned to caller + breach row + counter; emission **DROPPED** (same as V1). |

The visible difference is whether the calling service receives an error.
**The drop behavior is identical in both stages** — the inventory is the
source of truth and emissions outside it are never observed downstream.
The 30-day adoption window exists so service authors can find + fix
their inventory typos without their service receiving error returns.

## 2. Time-based flip plan (Q-L6F-1)

Foundation ships with config:

```yaml
# observability.admission.yaml (or equivalent service config)
mode: warn                 # V1 default
auto_flip_after: 720h      # 30 days — corresponds to V1+30d milestone
flip_marker_path: /var/lw/observability/admission-mode  # optional override
```

Service boot reads `mode` from config and instantiates
`observability.NewAdmission(inv, AdmissionWarn, breachWriter)`.

### 2.1 Flip trigger options (in priority order)

1. **Admin flip via SetMode (immediate, runtime).** Operator runs
   `kubectl exec <pod> -- /lw-admin-cli observability admission set --mode=reject`
   and the service's `*Admission` calls `SetMode(AdmissionReject)`
   atomically. Next emission honors the new mode.
2. **Config change + rolling restart.** Bump `mode: reject` in config
   and roll the deployment. Slower; useful when the admin CLI is
   unavailable.
3. **Auto flip at the V1+30d milestone.** When the running clock passes
   the ship-date + 30 days, the admission gate auto-promotes from
   warn → reject. Foundation does NOT implement this auto-flip in
   cycle 30 (would require an extra goroutine + epoch comparison);
   instead the milestone is enforced by the SRE checklist below.

### 2.2 SRE checklist for the V1+30d flip

T-7d before milestone:

- [ ] Query `lw_metric_admission_warn` (or the cycle-30 equivalent) in
      Prometheus. Any series with > 0 over the past 7 days indicates
      a service is emitting metrics outside inventory.
- [ ] For each non-zero series: file a ticket to the owning team to
      add the metric to `contracts/observability/inventory.yaml` OR
      remove the emission.
- [ ] If any tickets remain open within 24h of the milestone — escalate
      to engineering leadership; consider a 7-day extension.

T-0 milestone day:

- [ ] Confirm `lw_metric_admission_warn` is at zero for at least 24h.
- [ ] Run `lw-admin-cli observability admission set --mode=reject` on
      each foundation-owned service. (Or, if config change preferred,
      stage the config bump + roll.)
- [ ] Verify post-flip that `lw_metric_admission_rejections_total` is
      still 0 — non-zero means a service slipped past the cleanup.

T+1d after flip:

- [ ] Monitor service error logs for `ErrUnregisteredMetric`. Any
      occurrence is an emission that escaped detection during the
      30-day warn window — file a P1 ticket to the owning team.
- [ ] Snapshot the breach buffer (Drain to durable store) for the
      postmortem.

## 3. Rollback (warn ← reject)

If hard-reject mode causes service degradation (e.g., an emission
inside a request hot path is rejecting + the caller treats the error
as fatal):

```
lw-admin-cli observability admission set --mode=warn
```

This is **safe** — emissions that were dropping silently in reject
mode will continue to drop in warn mode; the only difference is the
caller no longer sees an error. Use the rollback window to finish
inventory cleanup, then re-promote.

## 4. Implementation references

- Admission decision: `contracts/observability/admission.go` (cycle 19)
- Service wrapper:    `pkg/metrics/admission_lib.go` (cycle 30)
- Breach durable buffer: `contracts/observability/budget_breach_writer.go`
- Inventory source of truth: `contracts/observability/inventory.yaml`
- Cycle-7 lint enforcing inventory presence: `scripts/observability-inventory-lint.sh`

## 5. Q-IDs honored

| Q-ID | Resolution | Where enforced |
|---|---|---|
| Q-L6F-1 | Time-based flip (foundation ships V1+30d as flag-flip; admin can flip earlier) | This runbook §2 + atomic `SetMode` on `*Admission` |
