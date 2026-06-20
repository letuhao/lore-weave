# Plan — Glossary migration ledger (clears `D-GKA-G4-SEED-CLEANUP`)

**Date:** 2026-06-20 · **Size:** L (load-bearing: migration infra + existing-DB transition) · **Service:** glossary-service

## Problem

The glossary migration chain is **ledger-free**: `cmd/glossary-service/main.go` calls ~27 idempotent
migrate funcs **every boot**, and `execGuarded` has no applied-ledger (see `migrate.go:1957`). So every
step replays each startup. The visible symptom (`D-GKA-G4-SEED-CLEANUP`) is that the legacy
`system_kind_attributes` table is **CREATE'd → seeded → DROP'd on every boot** — harmless whole-table
recycle (no `pg_attribute` slot leak), but pure churn. It can't be removed in isolation because the table
is consumed *between* create and drop each boot (extraction_audit_log FK `migrate.go:103`; the pre-cutover
snapshot fn JOINs it at `1053`/`1085`/`1095`/`324`).

## Approach (chosen by user): a real `schema_migrations` ledger

Each step runs **exactly once** and is recorded; subsequent boots skip applied steps. This eliminates
ALL per-boot churn (DDL replay, backfill rescans, and the create-then-drop), not just this one table.

**Key safety property — purely additive wrapping.** We change **zero migration SQL / function bodies**.
We only wrap each existing call in an apply-once check. Every step is already idempotent (the precondition
that makes ledger-adoption safe) and every destructive step keeps its **own internal guard** (e.g. the
cutover's `glossary_entities_kind_id_fkey`-existence TRUNCATE guard) as defense-in-depth independent of the
ledger.

### Acceptance criteria

1. **Fresh DB:** `RunChain` applies all steps once → tiered tables present, `system_kind_attributes` GONE,
   `schema_migrations` has one row per step. A 2nd `RunChain` is a no-op and does **not** recreate
   `system_kind_attributes`.
2. **Idempotent replay:** `RunChain` ×N → identical end state, no errors.
3. **Existing (pre-ledger) DB transition:** first post-ledger boot runs each step **one** final idempotent
   pass (ledger empty), records them, then quiesces. The cutover's TRUNCATE does **not** fire on an
   already-cutover DB (internal FK-guard, unchanged) → **no data loss**.
4. **Crash-safety:** a crash between a step's success and its ledger write re-runs the step next boot
   (harmless — idempotent). Concurrent multi-instance startup is serialized + dedup'd (PK `ON CONFLICT`).
5. Existing migrate tests still pass (they call `Up`/`Seed` directly — unchanged public funcs).

### Design

New `internal/migrate/ledger.go`:
- `EnsureLedger(ctx, pool)` — `CREATE TABLE IF NOT EXISTS schema_migrations(name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())`.
- `type Step struct { Name string; Fn func(context.Context, *pgxpool.Pool) error }`.
- `ApplyOnce(ctx, pool, name, fn)` — SELECT-applied → skip; else run fn; then `INSERT … ON CONFLICT DO NOTHING`.
- `var chain []Step` — the ordered list, names `0001_schema … 0029_glossary_drop_legacy_g4`, **exact same order** as today's main.go.
- `RunChain(ctx, pool)` — `EnsureLedger` then `ApplyOnce` over `chain`.

`main.go`: replace the ~27 `if err := migrate.UpX(...)` blocks with a single `migrate.RunChain(ctx, pool)`.
The **two async background backfills** (`BackfillShortDescription` always; `BackfillEntityRevisions` when
Redis set) stay as goroutines in main.go — they are self-limiting (process only unprocessed rows),
non-blocking, and ledgering cancellable async work adds risk for marginal gain. Documented as an explicit
scope boundary.

**Seeds (`Seed`, `SeedKindAliases`, `SeedGenreKindAttr`) ARE ledgered** (run once) per the "exactly once"
mandate. Behavior change: new `DefaultKinds` seed data now needs a **new migration row**, not auto-pickup
on deploy. Kept idempotent (`ON CONFLICT`) as a manual-rerun safety net; documented loudly in code +
handoff.

### Tests (VERIFY evidence — needs `GLOSSARY_TEST_DB_URL`)

`ledger_test.go` (ephemeral DB, mirrors the rename-test pattern):
- `TestRunChain_FreshThenNoChurn` — RunChain ×1 → ledger full + `system_kind_attributes` absent; capture
  `to_regclass`; RunChain ×2 → still absent (no recreate), ledger row-count unchanged, no error.
- `TestRunChain_Idempotent` — RunChain ×3 → system standards intact (7 genres / 13 kinds), entities table
  present, no error.
- `TestApplyOnce_SkipsApplied` — a counting fn wrapped in ApplyOnce runs once across two RunChain-style passes.

Live-smoke: boot glossary-service against the existing dev DB (no ledger yet) → confirm transition boot
succeeds + `system_kind_attributes` dropped; restart → confirm it is NOT recreated and `schema_migrations`
is populated.

### Out of scope / deferred
- The two async backfills stay per-boot (self-limiting). Track as `D-GLOSSARY-LEDGER-ASYNC-BACKFILLS` (LOW)
  only if it ever shows in startup profiling.
