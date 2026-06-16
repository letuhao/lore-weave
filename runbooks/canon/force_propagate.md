# Runbook — Canon Force-Propagate (L5.H)

> **Owner:** Platform SRE + Governance
> **Pages:** `lw_force_propagate_in_flight > 50` for > 10 min OR
> `admin.canon.override.requested` rate spike (>10/h)
> **Last verified:** 2026-05-29 (cycle 27 ship date — full drill in cycle 7+ SR sub-program)
> **Source:** L5.H.6; companion to
> `services/meta-worker/pkg/force_propagate/` (Go orchestrator) +
> `contracts/events/admin_canon_override.go` (event family)

## What "force-propagate" means

A force-propagate is an admin/author/governance request to push a canon
edit through to per-reality `canon_projection` even when the reality has
L3 history that would otherwise be shielded. It follows the **3-gate
flow** per M4 §9.8.3:

```
gate 1 (opt-in)   →   admin.canon.override.requested emitted
gate 2 (consent)  →   per reality: ACK (consented) | VETO (vetoed) | TIMEOUT (Q-L5H-1 default-to-consent)
gate 3 (R13 audit)→   every event audited to meta_write_audit (Q-L1A-3, no sampling)
```

Each reality that consented (explicit or default) receives a
**compensating L3 event** (`admin.canon.override.compensating`) that
applies the canon edit to its `canon_projection`. Vetoed realities are
SKIPPED.

## LOCKED behaviors

| ID | Behavior |
|---|---|
| Q-L5H-1 | Consent timeout = 24h; default-to-consent on no-response |
| Q-L1A-3 | Every consent/veto/compensating event audited; no sampling |
| Q-L1A-2 | Per-reality `canon_projection` ONLY; glossary SSOT untouched |
| Q-L5-3  | `canon_layer` enum `L1_axiom` / `L2_seeded` carried verbatim |

## Investigation checklist

1. **Identify the override.** Pull the requested event:

   ```sql
   SELECT * FROM meta_write_audit
   WHERE event_type = 'admin.canon.override.requested'
     AND override_id = '<id>'
   ORDER BY at DESC LIMIT 5;
   ```

2. **Reconstruct per-reality outcomes.** Filter audit by override_id:

   ```sql
   SELECT reality_id, event_type, default_consent, written_at
   FROM meta_write_audit
   WHERE override_id = '<id>'
   ORDER BY written_at;
   ```

   Expected sequence per reality:
   - `admin.canon.override.consented` (default_consent=true if Q-L5H-1 fired)
   - `admin.canon.override.compensating`

   OR
   - `admin.canon.override.vetoed` (no compensating row)

3. **Cross-check projection state.** For each consented reality:

   ```sql
   -- in the reality DB
   SELECT * FROM canon_projection
   WHERE canon_entry_id = '<entry-id>';
   ```

   `source_event_id` MUST equal the `override_id` (the orchestrator sets
   `SourceEventID` from the request).

## Resolution table

| Symptom | Likely cause | Action |
|---|---|---|
| Reality stuck in `consent_pending` past 24h | Q-L5H-1 default-to-consent didn't fire — collector loop stalled | Restart meta-worker; reprocess override_id from audit; default-to-consent will fire on next Collect call |
| Compensating event emitted but `canon_projection` row unchanged | DB write succeeded but reader cache holds stale row | Manually call `canon_writer.Invalidate(reality_id, canon_entry_id)` (cycle 25 L5.E) |
| Per-reality DB error — audit row but no compensating event | Cycle 7 L1.J degraded mode | Wait for DB recovery + re-dispatch override via admin-cli |
| Audit row missing for consented reality | Q-L1A-3 VIOLATION | Escalate — never silently skip an audit row |

## Idempotent re-drive

Force-propagate orchestration is idempotent on `(override_id, reality_id)`:
- The `UpsertCanon` on `canon_projection` is keyed on `canon_entry_id` (cycle 23 PK).
- The audit writer captures every attempt (Q-L1A-3).

Safe re-drive command:

```bash
admin-cli canon override re-drive --override-id <id>
```

This re-emits the per-reality consent collection + compensating event
emission. Existing rows are no-ops (UPSERT on PK).

## Watchpoint metrics

| Metric | Threshold | Page |
|---|---|---|
| `lw_force_propagate_in_flight` | > 50 for 10m | warn |
| `lw_force_propagate_default_consent_total` | > 10/h | warn (Q-L5H-1 fallback firing more than expected) |
| `lw_force_propagate_veto_total` | > 5/h | info |
| `lw_force_propagate_db_failure_total` | > 0 | page |

## Escalation

1. On-call SRE for projection / DB issues.
2. Governance lead for consent timeout / default-consent spike analysis
   (Q-L5H-1 governance lock review).
3. Author / book owner for veto rate analysis.
