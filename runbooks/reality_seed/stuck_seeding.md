# Runbook — Reality Stuck in `seeding` Status

> **Owner:** Platform SRE
> **Pages:** `lw_reality_seeding_failed_total > 0` for > 5 min OR
> `reality_registry.status = 'seeding'` for > 1h on any row
> **Last verified:** 1970-01-01 (stub — full drill in cycle 7+ SR sub-program)
> **Source:** L5.G.10; companion to
> `services/world-service/src/reality_seeder/`

## What "stuck seeding" means

The L5.G reality seeder transitions a reality through:

```
provisioning (cycle-5 step 9) → seeding → active   (happy path)
                                seeding → failed_seeding   (fatal error)
```

Three drift classes warrant SRE attention:

| Class | `reality_registry.status` | Symptom | Likely cause |
|---|---|---|---|
| A | `seeding` for > 1h | seeder process exited mid-flight (crash, OOM, deploy) | Seeder process not running; restart it idempotently |
| B | `failed_seeding` | seeder ran but hit a fatal error before completion | Upstream RPC failure, projection write error, audit sink failure |
| C | `seeding` and `lw_reality_seeding_failed_total` > 0 but no `failed_seeding` row | seeder reported failure but lifecycle transition itself failed | Race on lifecycle CAS; reality stays `seeding` — see §3 |

## Investigation checklist

1. **Identify the reality.** Pull the row from `reality_registry`:

   ```sql
   SELECT reality_id, status, status_changed_at, db_host, db_name
   FROM reality_registry
   WHERE reality_id = '<id>';
   ```

   Confirm `status` and `status_changed_at` (how long has it been
   stuck?).

2. **Read the seeder audit trail.** Production binds the L5.G audit
   sink to `meta_write_audit`; filter by `reality_id`:

   ```sql
   SELECT *
   FROM meta_write_audit
   WHERE reality_id = '<id>'
     AND target_table LIKE 'canon_projection%' OR target_kind = 'seed_phase'
   ORDER BY at DESC
   LIMIT 50;
   ```

   - **No Failure event** but `status='seeding'` → Class A (seeder
     crashed before recording failure). Re-drive (§4).
   - **Failure event present** → read `error` field; classify per §2.

3. **Read the checkpoint.** The seeder persists progress to
   `reality_seed_checkpoint` (migration lands when production wiring
   activates; current cycle ships the trait + tests). The checkpoint
   tells you how far the seeder got:

   ```sql
   SELECT reality_id, book_id, cursor, entries_committed, snapshot_at
   FROM reality_seed_checkpoint
   WHERE reality_id = '<id>';
   ```

   - `cursor IS NULL` + `entries_committed > 0` → seed COMPLETED but
     lifecycle transition didn't land. Re-drive (§4) is safe; the
     seeder will detect `already_seeded` covers everything and
     transition straight to `active`.
   - `cursor IS NOT NULL` → seeder was mid-stream; re-drive resumes
     from the cursor (§4).
   - No row → seeder never reached the first checkpoint. Re-drive
     starts from cursor=None (full re-run; UPSERTs are idempotent).

## Resolution table

| Class | Resolution |
|---|---|
| A | Restart the seeder for this reality_id (§4). Idempotent UPSERT + checkpoint make re-runs safe. |
| B (`SeederError::CanonRpc`) | Check glossary-service health + ACL; the cycle-25 `glossary-service-rpcs` entry must permit world-service. Then re-drive (§4). |
| B (`SeederError::Translation`) | If `reality.locale != book.source_locale`, translation-service is consulted; check `translation-service-rpcs` ACL (cycle 26 L5.G.8) + service health. Then re-drive. |
| B (`SeederError::ProjectionWrite`) | Per-reality DB unreachable; engage the L1.J degraded-mode runbook for the affected shard. Once shard is healthy, re-drive (§4). |
| B (`SeederError::Audit`) | meta_write_audit sink unreachable; engage the meta cluster runbook (Patroni failover if Patroni unhealthy). Then re-drive. |
| B (`SeederError::Lifecycle`) | Lifecycle CAS rejected; another actor moved the reality. Inspect `lifecycle_transition_audit` for the conflicting actor; coordinate. |
| B (`SeederError::InvalidRequest`) | Caller bug (e.g. nil reality_id, locale mismatch with book metadata). NOT auto-retriable; investigate caller. |
| C | Lifecycle transition path is broken — see meta-worker logs around the timestamp in `lw_reality_seeding_failed_total` for the lifecycle write failure. Manual `AttemptStateTransition(reality_id, 'seeding', 'failed_seeding', 'sre-cleanup')` via admin-cli. |

## Re-driving the seeder

The seeder is **idempotent at two layers** (per `mod.rs` header doc):

1. **Canon upsert** — keyed on `canon_entry_id` PK on
   `canon_projection`. Re-running upserts the row in place; no duplicates.
2. **Checkpoint** — keyed on `(reality_id, book_id)`. Re-saving the
   same checkpoint is a no-op; the seeder reads the prior cursor and
   resumes from there.

A re-run after a completed seed produces:
- `report.was_no_op = true`
- `report.canon_entries_written` = the existing total (NOT zero —
  the report includes the running checkpoint count)
- 0 NEW projection writes (verified by audit + by
  `report.canon_entries_translated` if Q-L5-2 applied)

### Command (admin-cli — production wiring lands when seeder binary ships)

```bash
admin-cli reality seeder run \
  --reality-id <id> \
  --reason "sre-manual:incident-<ticket>" \
  --resume
```

`--resume` makes the seeder honor any prior checkpoint;
`--from-scratch` overrides (drops the checkpoint first). Production
default is `--resume`.

### Watchpoints during re-drive

| Metric | Healthy | Action if not |
|---|---|---|
| `lw_reality_seeder_canon_entries_total{reality=<id>}` | monotone increase | Stalled — check seeder process / RPC errors |
| `lw_reality_seeder_audit_writes_total{reality=<id>}` | matches canon_entries_total | Audit sink lag — engage meta cluster |
| `lw_reality_seeder_checkpoint_writes_total{reality=<id>}` | ≥ canon_entries_total / 100 | Checkpoint store unreachable |
| `lw_reality_seeding_failed_total{reality=<id>}` | flat at 0 during re-drive | New fatal error — re-investigate per §2 |

## Escalation

- **Same-reality re-drive fails 3 times** → engage CYCLE 25/26
  on-call. Tagged: `team-foundation` + `team-glossary` (cross-team).
- **Pattern: many realities stuck after a deploy** → likely a
  regression in the seeder binary; roll back the seeder deploy + open
  a bug. Affected realities self-heal on next re-drive against the
  rolled-back binary.

## LOCKED Q-IDs (context for design decisions)

- **Q-L5-2** — translation only when locales differ. If a stuck
  reality has `reality.locale == book.source_locale`, translation is
  NEVER the cause; eliminate that branch from investigation.
- **Q-L5-4** — RPC is HTTP/JSON V1. No gRPC bind issues.
- **Q-L1A-2** — canon SSOT lives in glossary DB. Per-reality
  `canon_projection` is the CACHE; if `canon_projection` is missing
  rows present in glossary, the seeder DID NOT run / failed early.
- **Q-L1A-3** — every write audited (no sampling). Missing audit row
  for a `canon_projection` row is itself a bug — escalate to platform.
- **Q-L5A-1** — glossary-service is NOT modified by foundation
  cycles. If glossary RPC is breaking, the bug is in the cycle-25 RPC
  client OR the glossary-service team's outbox sub-program — NOT in
  the seeder.
