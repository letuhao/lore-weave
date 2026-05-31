# P2/113 — `user.erased` via MetaWrite (D-KEK-DESTROY-VIA-METAWRITE)

**Status:** DESIGN (checkpoint — awaiting sign-off + /amaw before BUILD)
**Size:** XL (contracts/meta contract change + crypto-shred refactor + relay + tests across ≥3 modules)
**Workflow:** **/amaw STRONGLY recommended** — this touches the crypto-shred (the most security-critical path) + a cross-system event contract. DB: no new migration (behavioural). No push without approval.
**Direction (user, 2026-05-31):** **Option 1 — MetaWrite custom-payload override.** The shred emits the *canonical domain* event (`XRealityUserErasedV1 {user_id, erased_at}`) at the source; the library stays generic; the relay promotes the domain payload to top-level fields for xreality topics so the existing 071 consumer works unchanged.

---

## 1. Why (the gap 101 left + the recon finding)

101 built the meta-outbox emit→drain→stream rail, but `user.erased` does NOT emit because `PgKEKManager.DestroyKEK` (`sdks/go/piikms/kekmanager.go`) is a **direct** set-based `UPDATE pii_kek … RETURNING` + KMS — it never calls `meta.MetaWrite`. 113 routes the shred through MetaWrite so the allowlisted `pii_kek` UPDATE → `user.erased` fires.

**Recon finding (the reason this is XL, not a one-liner):** a **CDC-vs-domain envelope mismatch**.
- Canonical `xreality.user.erased` = `contracts/events/xreality.go XRealityUserErasedV1 {user_id, erased_at}` (a **domain** event). The **071 consumer** (`meta-worker/user_erased_writer.decodePayload`) reads top-level fields `user_id` (**required**), `erased_at` (or `recorded_at` fallback), `event_id`, `request_id` (optional).
- 101's meta-outbox is **CDC**: `MetaWrite` hardcodes the outbox payload to `{table, operation, pk, after}` and the relay emits `aggregate_id = pkAsString(PK) = kek_id` — **no `user_id`**. So a naive shred-through-MetaWrite would emit an event 071 rejects (`missing field user_id`; `kek_id ≠ user_id`).
- **Nobody currently produces `xreality.user.erased`** — this path is the intended producer.

Option 1 resolves it by letting the *emitting caller* supply the domain payload, keeping the generic CDC default for everything else.

## 2. Design

### 2.1 `contracts/meta` — optional `OutboxPayload` override (additive, back-compat)
- Add `OutboxPayload map[string]any` to `MetaWriteIntent` (optional; nil ⇒ current behaviour).
- In `writeOneInTx`, when emitting (`cfg.Outbox != nil` + allowlist `EmitsEvent`): if `in.OutboxPayload != nil` use it as `OutboxEvent.Payload`; else the generic `{table, operation, pk, after}` (unchanged for all existing callers/tests).
- **Scrubbing note:** the generic payload uses unscrubbed `NewValues` by design (101 finding 114). A caller-supplied `OutboxPayload` is the caller's responsibility — for `user.erased` it's `{user_id, erased_at}` (opaque id + timestamp, no PII). Document that override payloads must not carry PII unless the caller intends it (ties to 114).

### 2.2 `sdks/go/piikms` — route the shred through MetaWrite
`DestroyKEK` becomes (security-preserving):
1. `SELECT kek_id, kms_key_ref FROM pii_kek WHERE user_ref_id=$1 AND destroyed_at IS NULL` — the active set (≤1 by migration 028's UNIQUE partial index; the SELECT is the defense-in-depth enumeration).
2. For each active KEK: `meta.MetaWrite` intent `{Table: pii_kek, Op: UPDATE, PK:{kek_id}, NewValues:{destroyed_at, destroyed_by_ticket, destroyed_reason}, ExpectedBefore:{destroyed_at: nil}, OutboxPayload: XRealityUserErasedV1{user_id, erased_at(=now RFC3339)}}`. The CAS makes a concurrent/double shred an idempotent no-op (mapped like the consent path). Emits `user.erased` + same-TX `meta_write_audit`.
3. Per distinct CMK: `maybeScheduleDeletion` (co-tenant guarded) — **unchanged**, runs after the MetaWrite commits.

**Security analysis (the AMAW-critical part):**
- *Total-shred property* (076 Slice B BLOCK: "erasure must be total"): the UNIQUE partial index guarantees ≤1 active KEK, so enumerating the active set + CAS-UPDATing each is total. A new active KEK cannot be inserted while one exists (the index), and one provisioned *after* the shred belongs to a new consent, not this erasure. Per-row CAS replaces the set-UPDATE's atomicity; equivalent given the index.
- *Authoritative erasure unchanged*: `destroyed_at` is still the SSOT; KMS deletion still best-effort/suppressed-on-co-tenant.
- *New failure mode*: if the MetaWrite outbox append fails, the shred UPDATE rolls back (101's same-TX atomicity) → the KEK is NOT destroyed → erasure fails CLOSED (safe; admin retries). The `probeMetaOutbox` startup guard (101) makes a missing `meta_outbox` fail at deploy, not mid-erasure.
- `NewPgKEKManager` gains a `*meta.Config` (Outbox-wired). The erasure handler (admin-cli `buildErasureHandler`) already builds that cfg for consent-revoke → pass the same one.

### 2.3 `services/meta-outbox-relay` — domain-field promotion for xreality topics
For the **xreality bridge** emit only (home stream stays generic payload-as-json): emit the OutboxPayload's top-level keys as top-level Redis fields + `event_id` + `recorded_at_nanos`. So `xreality.user.erased` carries `user_id`, `erased_at`, `event_id` — exactly what 071 reads. Implementation: the relay already passes `payload` through; for the xreality XADD, additionally spread the (now domain) payload object into fields. Guard: only spread if payload is a flat JSON object.

### 2.4 `meta-worker/user_erased_writer` (071) — verify-unchanged
071 reads `user_id`, `erased_at`/`recorded_at`, `event_id`, `request_id`. With 2.3 emitting `user_id` + `erased_at`(RFC3339) + `event_id`, **071 needs no change**. (Confirm in BUILD; add `request_id` to the payload if we want it populated.)

### 2.5 allowlist
`pii_kek` UPDATE → `user.erased` + `xreality_topic: xreality.user.erased` already exists (101). No change. Drop the "DestroyKEK is direct SQL / does NOT emit" caveat note in the YAML once 113 lands.

## 3. Files
- `contracts/meta/types.go` (+`MetaWriteIntent.OutboxPayload`) + `metawrite.go` (use it) + test.
- `sdks/go/piikms/kekmanager.go` (route through MetaWrite; `NewPgKEKManager` +cfg) + `kekmanager_pg_test.go` (assert `user.erased` meta_outbox row with `{user_id, erased_at}` + total-shred + KMS suppression preserved). piikms go.mod likely already has contracts/meta.
- `services/admin-cli/cmd/admin/main.go` (pass the Outbox-wired cfg into the KEKManager).
- `services/meta-outbox-relay/pkg/{drain,redisemit}` (xreality domain-field promotion) + tests.
- `contracts/meta/events_allowlist.yaml` (drop the stale caveat note).
- Possibly `services/meta-worker/.../user_erased_writer` (only if 2.4 finds a gap).
- docs: SESSION_PATCH, DEFERRED (113 → ADDRESSED; clear the user.erased caveat on 101).

## 4. Verification
- `go build/vet/test` contracts/meta, piikms, admin-cli, meta-outbox-relay, meta-worker; gofmt + lints.
- Unit: OutboxPayload override (custom vs generic default); relay xreality domain-field promotion (flat object spread; home stream unchanged).
- PG-gated: `DestroyKEK` → a real `meta_outbox` row `event_name=user.erased`, `xreality_topic=xreality.user.erased`, payload `{user_id, erased_at}`; total-shred (≤1 active → 0 active after); idempotent re-shred (CAS); KMS suppression on co-tenant (existing tests preserved).
- **Live smoke (≥2 services):** shred on real PG → `meta_outbox` user.erased → relay drains → `xreality.user.erased` stream carries top-level `user_id`+`erased_at`+`event_id` → assert a 071 `decodePayload` parses it (consume the actual stream message through 071's decoder).

## 5. Scope — REAL vs DEFERRED
| Piece | Status |
|---|---|
| MetaWrite OutboxPayload override | REAL |
| DestroyKEK via MetaWrite (emits user.erased domain payload) | REAL |
| Relay xreality domain-field promotion | REAL |
| 071 end-to-end consumability (decoder test) | REAL (verify-unchanged) |
| The per-reality scrub cascade actually wired live (071 service deploy) | DEFERRED 071 (consumer service live-wiring is its own task) |
| Co-tenant TOCTOU | DEFERRED 097 (unchanged) |

## 6. Gate before BUILD
Security-critical crypto-shred path + cross-system contract ⇒ **/amaw** + a slice plan (Slice 1: contracts/meta OutboxPayload + relay promotion [no shred risk]; Slice 2: the DestroyKEK refactor [the sensitive part, full AMAW + /review-impl]). Checkpoint before Slice 2. No push without approval.
