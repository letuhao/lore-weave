# Plan — Unblock D-PHASE5E + D-S5BEVAL-LEARNING-OUTBOX

**Created:** 2026-06-18 · **Branch:** `feat/auto-draft-factory-gaps` · **Size:** L (long-run `/loom`, 2 milestones)
**Origin:** `docs/deferred/DEBT-BATCHES.md` blocked bucket. PO chose option B (both items; M2 authorized under `/amaw` + migration).

Two coherent unblocks of items that were correctly "blocked" — M1 self-owned (no migration), M2 schema change.
`D-EXTRACTION-RAW-OUTPUT-CACHE` deliberately EXCLUDED (Park bucket: do-not-pick-up-standalone, PO-gated behind world-core-foundation).

---

## M1 — D-PHASE5E: surface image provider_kind + provider_model_name end-to-end

**Why it was blocked:** book-service hard-codes `provider_kind: ""` ([media.go:527](../../services/book-service/internal/api/media.go#L527))
and `ai_model: ""` ([media.go:514](../../services/book-service/internal/api/media.go#L514)) because the Go SDK's
`ImageGenResult` only carries `{created, data}` — the upstream model identity never reaches the consumer.

**Key finding:** the data already exists at the producer. `processImageGenJob`
([worker_image.go:64](../../services/provider-registry-service/internal/jobs/worker_image.go#L64)) resolves BOTH
`providerKind` and `providerModelName`, but `runImageGenJob` is only handed `providerModelName` — and neither is put
into the result map ([worker_image.go:151](../../services/provider-registry-service/internal/jobs/worker_image.go#L151)).
So the unblock is purely additive plumbing, no new lookups.

**Acceptance criteria:**
- A completed `image_gen` `Job.result` carries `provider_kind` + `provider_model_name`.
- book-service persists the real upstream model name in `block_media_versions.ai_model` and sends a non-empty
  `provider_kind` to usage-billing (`purpose=image_generation`).
- Purely additive: existing consumers that ignore the new fields are unaffected; legacy rows unchanged.

**Steps (contract-first, producer → consumer):**
1. **Contract** — `contracts/api/llm-gateway/v1/openapi.yaml` `ImageGenResult`: add optional `provider_kind` (string)
   + `provider_model_name` (string). Keep `required: [created, data]` (additive, backward-compatible).
2. **Go SDK** — `sdks/go/llmgw/models.go` `ImageGenResult`: add `ProviderKind string json:"provider_kind,omitempty"`
   + `ProviderModelName string json:"provider_model_name,omitempty"`. `decodeImageGenResult` needs no change (JSON unmarshal).
3. **Producer** — `services/provider-registry-service/internal/jobs/worker_image.go`: thread `providerKind` into
   `runImageGenJob` (it already has `providerModelName`); add both to the result map at the finalize site.
4. **Consumer** — `services/book-service/internal/api/media.go`: read `result.ProviderModelName` → the
   `block_media_versions.ai_model` insert; read `result.ProviderKind` → the billing payload `provider_kind`.
   Remove the two deferred-tracking comments.
5. **Tests:** provider-registry worker_image (result carries both fields); Go SDK decode test (round-trips the 2 fields);
   book-service media handler test (mock `ImageGenResult` with the fields → asserts they reach the version row + billing).

**Risk boundary / checkpoint:** OpenAPI contract change + 3-service seam (provider-registry → SDK → book-service) =
a shippable milestone. POST-REVIEW + commit here before M2.

**Out of scope (note, don't fold in):** the audio path ([audio.go:496](../../services/book-service/internal/api/audio.go#L496))
has the same `provider_kind: ""` but is a separate result shape (Transcribe/Speak) and a different deferred lineage;
flag as a parallel follow-up if the same SDK gap exists there.

---

## M2 — D-S5BEVAL-LEARNING-OUTBOX: transactional outbox for the eval_judged emit  (under `/amaw`)

**Why it was blocked:** the fidelity-judge result is published via a best-effort `XADD`
([decoupled_judge.py:393](../../services/learning-service/app/judges/decoupled_judge.py#L393), and a mirror in
`handlers.py`) — a lost emit silently drops the campaign's `eval_fidelity_score`. Durability needs a learning-service
outbox table = a schema change → `/amaw` + rollback plan (PO-authorized).

**Baseline facts:**
- learning-service uses an idempotent DDL string (`app/db/migrate.py`, `CREATE TABLE IF NOT EXISTS`, no Alembic) →
  the "migration" is additive + idempotent, no data backfill. Rollback = remove the table from DDL (empty table, no data loss).
- worker-infra `outbox_relay.go` is ALREADY multi-source and reads `outbox_events` (id, event_type, aggregate_type,
  aggregate_id, payload, created_at, published_at, retry_count, last_error) from producer DBs → publishes to a
  Redis stream sized per aggregate_type. learning-service is currently only a *consumer* of this relay.
- The emit ORDERING is already crash-safe (persist → CAS-claim completion → emit; /review-impl MED#1). M2 swaps the
  terminal best-effort XADD for an in-tx `outbox_events` INSERT so it is part of the same tx as the judge persist.

**Acceptance criteria (to refine in M2 DESIGN under /amaw):**
- The `translation.eval_judged` event is written to `outbox_events` in the SAME tx that persists the judge verdict
  (at-least-once, no lost emit on crash between persist and publish).
- worker-infra relay picks up learning-service as an outbox Source and republishes to `loreweave:events:translation_eval`
  (the stream the campaign projection consumes) — verify aggregate_type→stream mapping matches.
- Both emit sites (decoupled_judge + handlers) converted; the at-most-once→at-least-once shift is idempotent downstream
  (campaign projection upserts the score, so a redelivery is safe — confirm).
- Rollback plan documented; migration is additive/idempotent.

**Steps (detail in M2 DESIGN):** add `outbox_events` DDL → write helper that INSERTs in the judge tx → register
learning-service DB as a relay Source in worker-infra → convert both `_emit_eval_judged` paths → tests (in-tx insert,
relay pickup, downstream idempotency) → live-smoke token (≥2 services: learning + worker-infra + campaign).

**`/amaw`:** invoke before M2 BUILD (PO-authorized). Cold-start Adversary on the migration + the at-least-once shift.

---

## Sequencing
M1 (continuous) → POST-REVIEW + commit at the contract/cross-service boundary → `/amaw` → M2 design/build →
POST-REVIEW + commit. Tick both DEBT-BATCHES rows + update SESSION_HANDOFF in the respective commits.
