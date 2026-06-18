# Runbook — Recovering accidentally-deleted canon (L2.K.5)

> **Status (cycle 11):** SKELETON. Full per-class classifier (L2.K.3) lands
> incrementally; until then the only auto-delete paths are:
>
>  1. `events_outbox` published+old rows (≥24h after publish) — pruned by
>     `pkg/outbox_pruner`. NEVER affects canon (canon is in `events`, not
>     `events_outbox`).
>  2. `event_audit` rows past per-class threshold — pruned by
>     `scripts/event-audit-retention-cron.sh`. Per-class retention preserves
>     flagged rows 90d.
>
> **NEITHER path can delete canon events.** Canon events are in `events`
> (managed exclusively by archive-worker DETACH→archive→DROP). If canon
> appears to be missing, the most likely cause is mistaken archive +
> mistaken DROP (extremely unlikely; archive_loop's verify-before-record
> + record-before-drop invariants guard against it).

## Symptom

"A canon event I expected is no longer queryable from per-reality DB."

## Diagnostic

1. Confirm the missing event's `recorded_at`:

   ```bash
   psql "$PER_REALITY_DSN" -c "SELECT event_id, recorded_at FROM events
                                  WHERE aggregate_id = '$AGG' ORDER BY recorded_at;"
   ```

   Note any gap. Compute which monthly partition would have held it.

2. Check `archive_state` for that partition:

   ```bash
   psql "$PER_REALITY_DSN" -c "SELECT * FROM archive_state
                                  WHERE partition_name = '$PARTITION_NAME';"
   ```

   - If a row exists with `object_key` → the partition WAS archived; the
     event is in MinIO under `events/$REALITY_ID/$YEAR-$MONTH.parquet`.
     Proceed to **Restore from cold archive**.
   - If NO row exists, the partition was never archived; the event is
     genuinely lost from this DB. Proceed to **Disaster-recovery**.

## Restore from cold archive

See `runbooks/archive/restore.md`. Short version:

```bash
archive-restore fetch --reality $REALITY_ID --month $YEAR-$MONTH
```

V1 ships as a SKELETON that prints expected key shape; manual `mc cp`
follows.

## Disaster-recovery

If the event is in NEITHER `events` NOR cold archive:

1. Check `event_audit` for a matching `audit_ref` — the audit row may
   carry the original payload.
2. Check the original L2.D publisher's Redis Streams (`lw.events.$REALITY_ID`)
   — if the event was published, the consumer-side projection (when L3
   ships) may have a copy.
3. Last resort: re-derive from upstream LLM call (chat-service has the
   request/response log).

## Prevention

- The `outbox_pruner` test `TestEligible_DeadLetterNotEligible` enforces
  that dead-letter rows are NEVER auto-deleted — they carry the
  investigation evidence for any "lost canon" claim.
- The `archive_loop` test `TestRun_FailedVerify_DoesNotDrop` enforces
  that a partition is NEVER DROPped before its archive object is verified
  in MinIO.
- The `archive_loop` test `TestRun_FailedDrop_StatePreservedForRecovery`
  enforces that `archive_state` is written BEFORE the DROP, so a crash
  mid-DROP leaves the archive row recoverable.
