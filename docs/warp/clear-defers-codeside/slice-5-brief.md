# Slice 5 — observability-substream-and-log

**Write-set:** `services/chat-service/**` AND `services/provider-registry-service/**` only. Two languages (Python + Go), two LOW/cosmetic items. **NEVER edit `infra/docker-compose.yml`.**

## Defers to clear
### D-M3-COMPOSER-SUBSTREAM-OBSERVABILITY (LOW) — chat-service
M3 added `StreamRequest.stream_job_id`: a chat stream MINTS + SENDS a per-stream id so provider-registry persists a billing-neutral observability row (and a disconnect frees the slot via the cancel cascade). The **A2A composer sub-stream** `_stream_compose_prose` does NOT mint a `stream_job_id`, so it has no observability row.
- Find the main chat stream helpers that mint+send `stream_job_id` (grep chat-service for `stream_job_id`). Replicate the mint+send in `_stream_compose_prose` (likely `app/services/composer.py`) so the composer sub-stream gets its own observability row. Disconnect already frees via the aclose cascade — this only adds the row.

### D-CANCEL-FINALIZE-LOG-NOISE (LOW) — provider-registry-service (Go)
On a cancel-race the job worker logs `finalize failed: context canceled` at **Error** level — harmless (the cancel handler already finalized/emitted/freed via the request ctx). Find the `finalize failed` log in `internal/jobs/worker.go` and, when the underlying error is `context.Canceled` (use `errors.Is(err, context.Canceled)`), downgrade to Debug/Info (or skip) — keep Error for genuine finalize failures.

## Acceptance
- `python -m pytest -q` green in `services/chat-service` (existing 342 + any new composer test).
- `go build ./... && go vet ./...` clean in `services/provider-registry-service`.

## Gotchas
- Both are additive/cosmetic — do NOT change billing or the cancel semantics.
- The composer mint+send must match the EXACT `StreamRequest.stream_job_id` mechanism the main chat helpers use (exclude_none so legacy callers unaffected).
- No provider SDKs / hardcoded model names.
