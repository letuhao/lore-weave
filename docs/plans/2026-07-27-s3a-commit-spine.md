# Plan — S3a: commit-service spine (bus → admission → island → epoch-fenced commit)

> XL. Follows POC-2 (`e94fb6650`). Spec: [`15_commit_service.md`](../03_planning/LLM_MMO_RPG/15_commit_service.md) §2
> · DP-Ch11/Ch12/Ch13 ([`13_channel_ordering_and_writer.md`](../03_planning/LLM_MMO_RPG/06_data_plane/13_channel_ordering_and_writer.md))
> · EVT-L1..L6 ([`07_llm_proposal_bus.md`](../03_planning/LLM_MMO_RPG/07_event_model/07_llm_proposal_bus.md)).
> Seam research 2026-07-27 01:43 (agent sweep, file:line-verified) established: no channel columns
> exist (`events`, migration 0002), no epoch token anywhere in code, no CP service, no Rust redis
> client in the workspace, and the Go meta rail (meta-worker/breach-notifier/publisher) is the
> proven consumer-pattern source.

## Slice boundary

**IN (S3a):** migration `0014` (channel ordering columns + `channel_writer_state` +
`channel_event_index`); `dp-kernel::channel` (writer lease + CAS-fenced channel append — the
DP-A16 fence REAL at the DB layer); `redis` workspace dep; commit-service proposal-bus consumer
(EVT-L2/L3/L4/L6 rail: mkstream, ack-on-success-only, XAUTOCLAIM reclaim, dead-letter);
admission (schema + EVT-L3 dedup + category subset with **`notrun` recorded for unbuilt
stages** — never a silent skip); spine binary wiring bus → island → epoch-fenced commit;
live smoke incl. the **stale-epoch fence bite**.

**OUT (tracked):** the CP (lease *issuance* is CP-less here — see D3); full EVT-V feature
validators (lex/heresy/canon-drift etc. — feature-owned, unbuilt); envelope v2 (REC-53 bundle);
outbox→bus emission of committed events (S3b with projections); fiction_clock dual-writer
conflict (`_boundaries/01:38`, pre-existing).

## Design decisions

- **D1 — DP-Ch11's `UNIQUE(reality_id, channel_id, channel_event_id)` is UNIMPLEMENTABLE as
  written**: `events` is `PARTITION BY RANGE (recorded_at)` and Postgres requires the partition
  key in any parent unique constraint. Delivered instead as (a) **CAS allocation** on
  `channel_writer_state (reality_id, channel_id, current_epoch, last_event_id)` — one atomic
  `UPDATE … SET last_event_id = last_event_id + 1 WHERE current_epoch = $presented` is BOTH the
  allocator AND the DP-A16 fence (0 rows ⇒ stale epoch ⇒ `WrongChannelWriter`) — and (b) a
  non-partitioned **`channel_event_index`** (`PK (reality_id, channel_id, channel_event_id)`,
  written in the same tx) carrying the hard uniqueness + fast channel-ordered lookup the spec's
  index wanted. **Spec correction → register (REC-80 candidate).**
- **D2 — channel append lives in `dp-kernel`** (`src/channel.rs`): DP-A16's guard is "non-SDK
  paths cannot forge"; the SDK is dp-kernel. Mirrors `AppendGuard`/`PgEventStore` conventions
  (wrapped pool, builder, fail-closed).
- **D3 — CP-less lease issuance, REAL fence.** `acquire_writer_lease` bumps `current_epoch`
  (INSERT..ON CONFLICT..RETURNING). The *fence semantics are exactly DP-Ch13* — an old lease
  dies at the DB the moment a newer one exists; only the *issuer* is simplified (CP later, same
  table, same fence). Recorded so nobody mistakes the stub for the guard.
- **D4 — EVT envelope fields ride `metadata`** (`event_category`, `turn_number`,
  `causal_refs`, `idempotency_key`, …) until envelope v2 lands via the REC-53 bundle;
  `EventMetadata.extra` already flatten-preserves unknowns.
- **D5 — consumer rail mirrors the proven Go shape** (`meta-worker`/`breach-notifier`):
  `XGROUP CREATE … MKSTREAM` tolerant of BUSYGROUP · ACK only after successful commit ·
  XAUTOCLAIM stale-PEL reclaim · attempts + dead-letter stream (`<stream>:dead`) after N.
- **D6 — no silent stage skips**: admission records per-stage verdicts `{pass|fail|notrun|skip}`
  (the conformance-runner verdict contract); unbuilt stages are `notrun` IN THE RECORD.
- **D7 — sim-core `InputId` = hash of the EVT-L3 idempotency triple** (documented hook,
  `sim-core/src/types.rs:19-22`); bus-level 60 s dedup cache is commit-service-owned, the
  kernel seen-set stays the second layer.
