# #32 — LLM-call full logging (every call + request/response payloads)

**Date:** 2026-06-28 · branch `fix/critical-ux-bugs` · size XL · billing/load-bearing

## Verified architecture (RC was wrong — storage layer EXISTS)

usage-billing `writeUsageLog` already persists, encrypted (AES-256-GCM, per-row session
key, audited decrypt): `request_status`, `input_payload_ciphertext`,
`output_payload_ciphertext`, `purpose`. `parseUsageEvent` already reads `request_status`.
The gaps are pure **plumbing in provider-registry**:

- **(a)** `usage_outbox` rows are written ONLY for `status=="completed"`
  (repo.go `FinalizeWithUsageOutbox` ~412) → failed/cancelled never reach usage-billing.
  And `usage_relay.buildUsageFields` HARDCODES `request_status:"success"` (~134).
- **(b)** `UsageOutbox` carries no payload fields → consumer writes empty `{}` payloads.

`llm_jobs.input` (request, immutable) + `result` (response) are both on the row.
`request_id == job_id`. The finalize UPDATE already `RETURNING job_meta` — add `input`.

## Plan

### provider-registry
1. **migrate.go** — `ALTER TABLE usage_outbox ADD COLUMN IF NOT EXISTS request_status TEXT`,
   `request_payload TEXT`, `response_payload TEXT` (idempotent, matches existing style).
2. **repo.go** — `UsageOutbox` +`RequestStatus,RequestPayload,ResponsePayload string`.
   `FinalizeWithUsageOutbox`: UPDATE `RETURNING job_meta, input`; emit a `usage_outbox` row
   for ALL terminal statuses (drop the `status=="completed"` gate; usage built by the
   worker for every status); INSERT the 3 new columns.
3. **worker.go** `finalizeAndNotify` — build `UsageOutbox` for every terminal status:
   `RequestStatus` = `success` (completed) | the status (failed/cancelled); tokens/cost as
   resolvable (0/nil for non-completed); `RequestPayload`=truncated `input`,
   `ResponsePayload`=truncated `result`. Cap each payload at
   `LLM_USAGE_PAYLOAD_CAP_BYTES` (default 16384) with a `…[truncated]` marker.
4. **usage_relay.go** — `drainOnce` SELECT +3 cols; `buildUsageFields` emits
   `request_status` from the row (not hardcoded) + `request_payload`/`response_payload`.

### usage-billing
5. **usage_consumer.go** `parseUsageEvent` — read `request_payload`/`response_payload`
   into `usageLogParams.InputPayload`/`OutputPayload` (strings). `writeUsageLog` already
   encrypts+stores them. No schema change (columns exist).

## Risk boundaries / checkpoints
- **Commit 1:** provider-registry (migration + emit + relay) — compiles, unit tests.
- **Commit 2:** usage-billing consumer + cross-service note.

## Decisions
- Payloads stored for EVERY call (user chose option 3), capped (volume/PII bound).
- Failed/cancelled audit rows: cost 0, `request_status` distinguishes from billable
  (usage_logs is audit-only; enforcement is the guardrail, untouched).
- Truncated JSON stored as a STRING (tracing artifact, not re-parsed).
