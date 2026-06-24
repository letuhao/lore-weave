# P2/101 — MetaWrite → meta-outbox emit layer (D-METAWRITE-OUTBOX-UNWIRED)

**Status:** DESIGN (checkpoint — awaiting human sign-off before BUILD)
**Size:** XL (new migration + new sdk pkg + new relay service + wiring ≥3 call sites + tests)
**Workflow:** /amaw recommended (XL, GDPR-critical, DB migration, multi-system contract). DB migration ⇒ rollback plan + explicit user confirmation required before apply.
**Keystone decision (user, 2026-05-31):** **Option B — dedicated meta-outbox relay** (single-table `meta_outbox` + a focused drain to `lw.meta.events`), cleanly owned by the meta/platform bounded context.

---

## 1. The gap

`MetaWrite` (`contracts/meta/metawrite.go`) is *wired* to emit allowlisted events in the same TX as the data write (`writeOneInTx`, the `if cfg.Outbox != nil` block at L303). `contracts/meta/events_allowlist.yaml` maps 13 meta tables → event names (`user.erased`, `user.consent.revoked`, `user.consent.granted`, `reality.status.changed`, `billing.charge.recorded`, …).

But **no caller sets `cfg.Outbox`**, because:
- **(a)** no production `OutboxAppender` exists;
- **(b)** no meta-DB outbox table exists (`migrations/meta/` has nothing of the kind — `025_scaling_events` is a capacity *audit* table, not an outbox);
- **(c)** nothing drains the meta DB — the publisher (`services/publisher`) builds its drain pools **only** from `reality_registry` active realities; it opens the meta pool solely for heartbeats + registry reads.

Net: every meta event (incl. `user.consent.revoked` from erasure step 7, `user.erased` from crypto-shred) is silently dropped. The DB row state (`revoked_at`, `destroyed_at`) is the only SSOT. This is documented in-code at `services/admin-cli/internal/commands/erasure_pg.go:22-29` and tracked as DEFERRED row 101.

### Confirmed live emit sites (grounded, not guessed)
| Site | Table | Allowlisted event | Fires once `cfg.Outbox` set? |
|---|---|---|---|
| `PgConsentRevoker.RevokeScope` (erasure step 7) | `user_consent_ledger` UPDATE | `user.consent.revoked` | **Yes** — already calls `meta.MetaWrite` |
| admin-cli audit Sink `MetaWriteSink.Write` | `admin_action_audit` INSERT | *(none — `events: []`)* | No event (harmless to wire; keeps Config uniform) |
| crypto-shred KEK destroy (erasure step 3 / piikms `DestroyKEK`) | `pii_kek` UPDATE (`destroyed_at`) | `user.erased` | **NO — bypasses MetaWrite** (resolved §6) |

**Honest scope correction (PLAN finding):** `PgKEKManager.DestroyKEK` (`sdks/go/piikms/kekmanager.go:47`) is a **direct, set-based multi-row** `UPDATE pii_kek SET destroyed_at=now() … WHERE user_ref_id=$1 AND destroyed_at IS NULL RETURNING kek_id, kms_key_ref` — the RETURNING drives the per-CMK KMS `ScheduleKeyDeletion`. It does **not** route through `meta.MetaWrite`, and its multi-row set-UPDATE shape does not fit MetaWrite's single-row-PK + `ExpectedBefore` CAS model. ⇒ **101 does NOT make `user.erased` emit.** 101 lights up `user.consent.revoked` (and any other genuinely MetaWrite-routed allowlisted event) + lays the full meta-outbox→`xreality.user.erased` rail. Emitting `user.erased` requires moving the crypto-shred onto MetaWrite — a security-critical refactor of the most sensitive path — tracked as **D-KEK-DESTROY-VIA-METAWRITE** (§7), NOT silently claimed here.

---

## 2. Architecture: three outbox families already in the tree

1. **Publisher spine** (`contracts/migrations/per_reality/0002,0005`): rich `events` (monthly-partitioned, lz4) + `events_outbox` (SKIP-LOCKED, retry-backoff, dead-letter). Drained by `services/publisher` → `lw.events.<reality>`; cross-reality rows fan out to `xreality.<entity>.<verb>` via `xreality_fanout` → meta-worker (sole xreality consumer, I7).
2. **worker-infra relay** (novel-platform half): single-table `outbox_events` → `loreweave:events:<aggregate_type>`. Different bounded context.
3. **The meta `OutboxAppender` interface** — unimplemented. ← this PR.

## 3. Critical integration constraint — the existing 071 consumer

`services/meta-worker/pkg/user_erased_writer` (the Art.17 per-reality cascade, "071") **already exists** and is wired to consume **`xreality.user.erased`** — its doc says *"triggered by the xreality.user.erased event that admin-cli publishes AFTER the KEK destruction."*

⇒ A meta relay that emits **only** to `lw.meta.events` would strand this consumer. **Resolution (correct-now):** the meta-outbox relay is the *meta-side publisher* — it routes each drained row by class:
- **cross-reality events** (those a per-reality consumer needs: `user.erased`, and any future xreality-flagged meta event) → XADD to the existing **`xreality.<entity>.<verb>`** topic (verbatim convention from `xreality_fanout.TopicFor`), so `user_erased_writer` and friends keep working unchanged.
- **all meta events** → XADD to **`lw.meta.events`** (the dedicated home stream for meta-only consumers: billing dashboards, consent projections, breach delivery, etc.).

The class is declared in the allowlist (§4.3), so routing is data-driven + reviewable, not hard-coded in the relay.

---

## 4. Design

### 4.1 `meta_outbox` table — `migrations/meta/030_meta_outbox.{up,down}.sql`
Single table (the whole point of Option B — no events/events_outbox split). Mirrors the *operational* columns of `events_outbox` (publish-state machine identical, so the relay's drain logic matches the publisher's proven shape) but **self-contains the envelope** (event_name + payload) so there is no `events` join.

```sql
CREATE TABLE IF NOT EXISTS meta_outbox (
    event_id          UUID        NOT NULL PRIMARY KEY,   -- = OutboxEvent.EventID (cfg.UUIDGen)
    event_name        TEXT        NOT NULL,               -- allowlist event_name (e.g. user.consent.revoked)
    aggregate_id      TEXT        NOT NULL,               -- pkAsString(intent.PK)
    payload           JSONB       NOT NULL,               -- {table, operation, pk, after}
    xreality_topic    TEXT        NULL,                   -- set when cross-reality (relay XADDs here too)
    published         BOOLEAN     NOT NULL DEFAULT FALSE,
    attempts          INTEGER     NOT NULL DEFAULT 0,
    last_error        TEXT        NULL,
    last_attempt_at   TIMESTAMPTZ NULL,
    dead_lettered_at  TIMESTAMPTZ NULL,
    enqueued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    recorded_at       TIMESTAMPTZ NOT NULL,               -- = OutboxEvent.RecordedAt (cfg.Clock)
    CONSTRAINT meta_outbox_attempts_nonneg CHECK (attempts >= 0),
    CONSTRAINT meta_outbox_payload_is_object CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT meta_outbox_published_consistency CHECK (
        published = FALSE OR (published = TRUE AND attempts >= 1 AND last_attempt_at IS NOT NULL)),
    CONSTRAINT meta_outbox_dead_letter_consistency CHECK (
        dead_lettered_at IS NULL OR (dead_lettered_at IS NOT NULL AND attempts >= 1))
);
CREATE INDEX meta_outbox_pending_idx ON meta_outbox (enqueued_at)
    WHERE published = FALSE AND dead_lettered_at IS NULL;
CREATE INDEX meta_outbox_dead_letter_idx ON meta_outbox (dead_lettered_at)
    WHERE dead_lettered_at IS NOT NULL;
```
**PII / retention header** (S08 §12X.4 — the payload can carry PII `after`-values): `@pii_sensitivity: low` (opaque IDs + table/op; the relay forwards, doesn't persist long-term), `@retention_class: ephemeral` (pruned post-publish), `@erasure_method: crypto_shred_actor` via the user_ref the payload references, `@legal_basis: legitimate_interest`. The relay **prunes** published rows after a grace window (mirrors events_outbox pruning intent) → bounded PII residency. *(Pruner is a relay concern; cross-check §7 deferral.)*
**down.sql:** `DROP TABLE IF EXISTS meta_outbox;`

### 4.2 Production `OutboxAppender` — `sdks/go/metaoutbox/appender.go` (new pkg)
Implements `meta.OutboxAppender`. `Append(ctx, tx, ev)` runs ONE parameterized INSERT into `meta_outbox` **using the supplied `meta.Tx`** (so it lands in MetaWrite's TX — atomic with the data + audit rows). Resolves `xreality_topic` from an injected `XRealityRouter` (built from the allowlist §4.3). No pool of its own; driver-agnostic (only needs `meta.Tx.Exec`), so it builds clean for any caller.

### 4.3 Allowlist xreality routing — extend `events_allowlist.yaml`
Add an optional per-event `xreality_topic:` to the events that have per-reality consumers. Initial set (conservative — only what a consumer exists for today):
```yaml
- table: pii_kek
  events:
    - op: UPDATE
      event_name: user.erased
      xreality_topic: xreality.user.erased   # ← consumed by meta-worker/user_erased_writer (071)
```
A loader surfaces `event_name → xreality_topic`. Absent ⇒ the event is meta-only (`lw.meta.events` only). This keeps the cross-reality surface explicit + CODEOWNER-reviewable (the allowlist is platform/security-owned).

### 4.4 Wire `cfg.Outbox` at construction sites
- `services/admin-cli/cmd/admin/main.go` `buildErasureHandler` — construct `metaoutbox.New(...)`, set `cfg.Outbox`. ⇒ erasure step 7 emits `user.consent.revoked`.
- admin-cli audit Sink Config (`NewMetaWriteSink`) — set `cfg.Outbox` for uniformity (admin_action_audit emits nothing, so a no-op today, but prevents a future allowlisted admin table from silently dropping).
- crypto-shred KEK-destroy Config (§6 open item) — set `cfg.Outbox` ⇒ emits `user.erased` → bridged to `xreality.user.erased`.

### 4.5 The relay — `services/meta-outbox-relay` (new, small Go service)
Mirrors the publisher's proven drain loop, single-DB + single-table:
1. Connect meta DB pool + Redis (env: `META_DB_URL`, `REDIS_URL`, `POLL_INTERVAL`, `BATCH_SIZE`, `STREAM_MAXLEN`, `META_EVENTS_STREAM` default `lw.meta.events`, `HTTP_ADDR`).
2. Poll loop: `SELECT … FROM meta_outbox WHERE published=FALSE AND dead_lettered_at IS NULL ORDER BY enqueued_at LIMIT $1 FOR UPDATE SKIP LOCKED` in one tx.
3. Per row: XADD envelope to `lw.meta.events`; if `xreality_topic` set, ALSO XADD to that topic (the 071 bridge). Classify via **reused** `publisher/pkg/retry.Policy` → MarkPublished / MarkRetry / MarkDeadLetter (same backoff/dead-letter semantics as the spine). Same-tx UPDATE, then commit (at-least-once; consumers idempotent on `event_id`).
4. Health (`/healthz` `/readyz`) + Prometheus (`/metrics`: `lw_meta_outbox_{published,retried,dead_lettered,iteration_errors}_total`).
5. V1 single-replica (no-op leader, like publisher Q-L2-5); SKIP-LOCKED keeps it V2-safe.

**Reuse, not re-implement:** `publisher/pkg/retry` (backoff + Classify) is generic — import it. The Source/Batch pattern is small enough to write focused for the single table (the publisher's is events-join-specific).

---

## 5. Files
**New:** `migrations/meta/030_meta_outbox.{up,down}.sql` · `sdks/go/metaoutbox/{appender,router}.go` + `_test.go` (+ `_pg_test.go` PG-gated) · `services/meta-outbox-relay/{cmd/meta-outbox-relay/main.go, pkg/drain/*.go, go.mod}` + tests.
**Edit:** `contracts/meta/events_allowlist.yaml` (+`xreality_topic`) + its loader (`contracts/meta/allowlist*.go`) · `services/admin-cli/cmd/admin/main.go` (wire Outbox ×2–3) · `contracts/service_acl/matrix.yaml` (new `meta-outbox-relay`: `meta_outbox` SELECT+UPDATE) · `contracts/observability/inventory.yaml` (+4 relay metrics) · `contracts/language-rule.yaml` (map `meta-outbox-relay` → Go) · `docs/sessions/SESSION_PATCH.md` + `docs/deferred/DEFERRED.md`.

## 6. Open design items — RESOLVED in PLAN
- **Crypto-shred emit path → RESOLVED:** `DestroyKEK` is a direct set-based multi-row UPDATE (kekmanager.go:47), NOT MetaWrite. `user.erased` does NOT emit from 101. Deferred as **D-KEK-DESTROY-VIA-METAWRITE** (§7). See §1 honest-scope correction.
- **Allowlist loader → RESOLVED:** struct-typed (`meta.EventBinding{Op, EventName}`; `AllowlistEntry`/`AllowlistFile`/`EventBinding` all exported). Plan: add additive `XRealityTopic string \`yaml:"xreality_topic"\`` to `EventBinding` (absent ⇒ "") + a non-breaking exported `meta.LoadXRealityTopics(path) (map[string]string, error)` helper. **No `Allowlist` interface change** (fakes untouched). The **appender** stamps the resolved `xreality_topic` column at write-time → relay is a pure transport.

## 7. Scope — REAL vs DEFERRED
| Piece | Status |
|---|---|
| `meta_outbox` table + down migration | **REAL** |
| `metaoutbox` OutboxAppender + xreality router | **REAL** |
| `events_allowlist.yaml` xreality_topic + loader | **REAL** |
| Wire `cfg.Outbox` (erasure handler + audit Sink) | **REAL** |
| `meta-outbox-relay` service (drain → `lw.meta.events` + xreality bridge) | **REAL** |
| Published-row **pruner** (bounded PII residency) | **DEFERRED** `D-META-OUTBOX-PRUNE` (mirror events_outbox D-OUTBOX-PRUNE) |
| Crypto-shred `user.erased` onto MetaWrite | **DEFERRED** `D-KEK-DESTROY-VIA-METAWRITE` — multi-row set-UPDATE-with-RETURNING + KMS side-effect; security-critical refactor of the shred path; out of 101 scope (§1, §6) |
| `lw.meta.events` **consumers** (breach delivery, consent projection) | **DEFERRED** (106/108 + 071) — 101 is the producer/drain layer only |
| Relay leader-election (V2 multi-replica) | **DEFERRED** (SKIP-LOCKED already V2-safe; leader is optimization) |

## 8. Verification plan
- `go build/vet/test` for `sdks/go/metaoutbox`, `services/meta-outbox-relay`, `contracts/meta`, `services/admin-cli`; gofmt; `language-rule-lint`; `service-acl-matrix` + `observability-inventory` + `meta-write-discipline` lints GREEN.
- Unit: appender INSERT shape (args, jsonb payload, xreality_topic set/nil); router resolution from allowlist; relay drain (fake source/redis: published/retry/dead-letter classification; xreality double-XADD only when topic set; at-least-once on commit-fail).
- PG-gated (`PIIKMS_TEST_PG_URL`): apply 030 → MetaWrite a `user_consent_ledger` UPDATE with Outbox set → assert ONE `meta_outbox` row in the SAME tx as the data + `meta_write_audit` rows (atomicity); relay drains it → row `published=TRUE`.
- **Live smoke (≥2 services):** admin-cli erasure consent-revoke on a live meta DB → `meta_outbox` row appears → start `meta-outbox-relay` → assert XADD on `lw.meta.events` (+ `xreality.user.erased` for the KEK path). Token: `live smoke:` or `live infra unavailable:` per VERIFY gate.

## 9. Gate before BUILD
DB migration (030) ⇒ **/amaw + rollback plan + explicit user confirmation** required before any apply. Rollback = `030_meta_outbox.down.sql` (`DROP TABLE meta_outbox`); the table is additive + ephemeral (no FKs into it, no data backfill), so rollback is clean and non-destructive to existing data. No push without explicit approval.
