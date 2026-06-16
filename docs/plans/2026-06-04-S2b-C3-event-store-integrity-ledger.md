# S2b / C3 — Event-Store Integrity Ledger (build plan)

> **Slice:** S2b of the foundation runtime test plan (`docs/specs/2026-06-04-foundation-runtime-test-plan.md` §2.4, §10).
> **Status:** PLAN (written; awaiting human review before BUILD).
> **Task size:** **M–L** — a new `ledger` package in the workload-gen module + a `-verify` CLI mode + a conformance live-probe + corruption-injection tests. Side effects (CLI, conformance case). Full 12 phases; `/review-impl` before commit (spine — closes the deepest blind spot).
> **Locked decisions:** Go · in the **`tests/workload-gen` module** (against-ledger mode reuses `gen.Generate` as the deterministic baseline) · **both modes** (self-consistency + against-ledger) · canonical-JSON-hash for payload integrity · a conformance case · corruption-injection tests (prove the oracle works).
> **Build-order context:** `S1 → S3 → {S2/C2, **S2b/C3**, S4, S9}`. C3 closes the gap B+C both miss (they read the same `events` rows; a lost/reordered/byte-rotted event is invisible to both).

---

## 1. CLARIFY — scope & acceptance (grounded)

### Grounded facts
- **`events` DDL** (`0002_events_table.up.sql:64-101`): no global ordinal column, **no checksum column**. A **partial unique index** on `(reality_id, aggregate_type, aggregate_id, aggregate_version)` makes intra-aggregate **duplicates impossible** (DB-enforced) — so C3 hunts **gaps** (a lost event = a missing version), not dups.
- **`events_outbox`** (`0005`): `event_id` PK. The atomicity invariant (I13) is **events ↔ outbox 1:1** — every event has exactly one outbox row.
- No stored payload hash → **byte-rot needs a baseline**. The deterministic S3 generator IS the baseline: regenerate the expected stream from `(seed, profile)` and reconcile.

### In scope (S2b)
1. **`ledger` package** (in the workload-gen module) with **pure-Go check logic over an in-memory `Log`** (fetched event + outbox rows), so every check — and every corruption-injection test — is unit-testable without a DB.
2. **Self-consistency checks** (any data, no baseline):
   - **version-completeness** — per `(reality, aggType, aggID)`: versions are exactly `1..N` (min=1, max=count, no gap).
   - **count-reconciliation** — `len(events) == len(outbox)`; no orphan outbox id (∉ events); no event missing its outbox row.
3. **Against-ledger checks** (seeded data, baseline = `gen.Generate(seed, profile)`):
   - every expected `event_id` is present; no unexpected event_id.
   - per-event **payload hash** (canonical JSON SHA-256) stored == expected → **byte-rot detection**.
   - per-aggregate version + (reality, aggType, aggID, event_type) match the expected.
4. **`LoadLog(ctx, db)`** — thin DB loader: `SELECT … FROM events` + `SELECT event_id FROM events_outbox` → an in-memory `Log`.
5. **CLI** — extend `workload-gen` with `-verify` (regenerates the expected stream from `-seed`/`-profile`, runs self-consistency + against-ledger against `-dsn`, exits non-zero on any violation).
6. **Conformance live-probe** — emit → verify clean (closes into S1; notrun on a stackless runner).
7. **Corruption-injection tests** — on in-memory `Log`s: delete an event → gap caught; flip a payload → hash-mismatch caught; delete an outbox id → count-mismatch caught; drop an expected event → missing caught. Proves the oracle actually fires.

### Out of scope
- Cross-aggregate global ordering / recorded_at-monotonicity beyond per-aggregate (there is no global ordinal; the spine orders by `(recorded_at, event_id)` — a separate concern, note for S6 fault history).
- Modifying the write path to add a stored checksum column (a real option, but a schema change — track as a deferred decision; the against-ledger baseline covers byte-rot for seeded data without it).
- The projection side (that's B/C, already built).

### Acceptance gate (LOCKED)
- All in-scope 1–7.
- `go test ./...` green (incl corruption-injection tests proving each check fires) + `go vet` + `gofmt` clean.
- **Live on real PG:** emit a `single-reality` stream, `-verify` → **clean** (0 violations); then a manual corruption (delete one event row) → `-verify` → **non-zero, names the gap** (demonstrates the oracle catches a real lost event).
- `language-rule-lint` PASS.

---

## 2. DESIGN

```
tests/workload-gen/
  internal/ledger/
    ledger.go    + _test   # Log, Violation, the 3 check families (pure Go)
    load.go      + _test    # LoadLog(ctx, db) — thin DB fetch → Log
  cmd/workload-gen/main.go  # + `-verify` mode (regenerate expected → check)
  ...
tests/conformance/catalog/generic/ledger-integrity.yaml   # live-probe
```

- **`Log`** = `{ Events []EventRow; OutboxIDs []uuid.UUID }`, `EventRow = { EventID, RealityID uuid.UUID; AggType, AggID, EventType string; Version uint64; Payload map[string]any }`.
- **`Violation`** = `{ Kind, Detail string }` (kinds: `version-gap`, `count-mismatch`, `orphan-outbox`, `missing-outbox`, `unexpected-event`, `missing-event`, `payload-mismatch`, `field-mismatch`). A `Report` aggregates; `Report.OK()` ⇔ empty.
- **Check families** (all `func(...) []Violation`, pure):
  - `CheckSelfConsistency(Log)` → version-completeness + count-reconciliation.
  - `CheckAgainstExpected(Log, expected gen.Stream)` → presence + payload-hash + field match.
- **Payload hash**: `sha256(jsonMarshal(payload))` — `encoding/json` sorts map keys → canonical; the same canonicalization for stored + expected, so a byte-rot that changes the logical value flips the hash.
- **`LoadLog`**: `SELECT event_id, reality_id, aggregate_type, aggregate_id, aggregate_version, event_type, payload FROM events ORDER BY recorded_at, event_id` + the outbox ids. Thin; the live-smoke exercises it.
- **CLI**: `workload-gen -verify -seed N -profile P -dsn …` → `LoadLog` → `CheckSelfConsistency` + `CheckAgainstExpected(gen.New(seed).Generate(profile))` → print `Report`, exit 1 on any violation.

---

## 3. PLAN — build increments (TDD)

1. **`ledger.go`** — `Log`/`EventRow`/`Violation`/`Report` + `CheckSelfConsistency`. **Tests first:** clean log → 0; delete-an-event → version-gap; delete-outbox → count + missing-outbox; add orphan outbox id → orphan.
2. **`CheckAgainstExpected`** — presence + payload-hash + field match. **Tests first:** clean vs `gen.Generate` → 0; flip a stored payload → payload-mismatch; drop an expected event → missing-event; add an extra stored event → unexpected-event.
3. **`load.go`** — `LoadLog(ctx, db)`. Tested live (fetch shape) + a small parse test if feasible.
4. **CLI `-verify`** — wire regenerate→load→check→report→exit. `main_test`: unknown profile, verify-needs-dsn, report-OK formatting.
5. **Conformance case** `ledger-integrity.yaml` — emit + verify; extend the pipeline smoke (or a new `scripts/ledger-verify-smoke.sh`).
6. **Live VERIFY** — emit → verify clean; inject a deletion → verify catches it.

### Test plan
unit: self-consistency (clean / version-gap / count / orphan / missing-outbox) · against-expected (clean / payload-mismatch / missing / unexpected / field-mismatch) · report aggregation · hash canonicalization. live: emit→verify clean; delete-one-event→verify names the gap.

### VERIFY gate
`go vet`+`gofmt`+`go test ./...` clean; live emit→verify=0 violations; corruption→verify≥1 violation naming it; `language-rule-lint` PASS.

---

## 4. Risks & open items
- **R1 — JSONB canonicalization drift.** Postgres normalizes JSONB on store (key order, whitespace, number forms). The hash must compare LOGICAL values: marshal the *parsed* `map[string]any` on both sides (not raw bytes). Numbers: JSON round-trips through `float64` — pin that both sides use the same decode path. **Mitigation:** hash `json.Marshal(map[string]any)` after a uniform decode; a test feeds a JSONB-normalized payload vs the generator's and asserts equal hash.
- **R2 — against-ledger only covers seeded data.** Production data has no baseline → only self-consistency applies. **Accept + document** (the stored-checksum-column option is the production path — O1).
- **R3 — recorded_at ordering vs emit order.** C3 checks per-aggregate version, not global order. A cross-aggregate reorder (same recorded_at) isn't a C3 violation. **Note** for S6 (fault history checker).

**Open items**
- **O1** — add a stored `payload_sha256` column to `events` at write (real byte-rot detection for production, not just seeded). Decision: schema change + write-path touch → defer to a dedicated proposal.
- **O2** — should `-verify` also reconcile `published` counts (outbox.published vs a publisher high-water)? Needs the publisher run; defer to S5 (standing gate).

## 5. Deferred-Items to add at COMMIT
- **D-LEDGER-STORED-CHECKSUM** (O1) — `events.payload_sha256` at write for production byte-rot detection. Target: a schema-change proposal.
- **D-LEDGER-PUBLISHED-RECON** (O2) — published/high-water reconciliation. Target: S5.
