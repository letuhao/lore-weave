# Plan — 073 admin-cli read-command batch (projection drift-check + archive fetch)

**Task size:** XL (gate-classified; effectively L after 2-cmd deferral — over-rigor kept).
**Cadence:** autonomous → POST-REVIEW (human stop) → push-ask. Set by user this session.
**Workflow:** human-in-loop v2.2 (no /amaw — read-only, no schema migration, no security path).

## Context

073 ships the admin-cli command surface incrementally. `reality stats`, `migration status`,
`archive list` are live (read-only, on the `perRealityPool` pattern). This batch adds the next
tier-3 (informational, read-only) commands. A pre-build investigation (4-agent Workflow) found
**2 of 4 candidate commands are blocked on persistence that does not exist**:

| Command | Backing data | Verdict |
|---|---|---|
| `projection drift-check` | `projection_drift_state` (per_reality `0007`) ✅ | BUILD |
| `archive fetch` | `archive_state` (per_reality `0011`) + MinIO `lw-event-archive` ✅ | BUILD |
| `backup list` | **no** `backup_snapshots`/`backup_manifest` table anywhere ❌ | DEFER |
| `canon conflict-list` | `l1_conflict_reports` **never created**; reporter ships only `InMemoryStore` ❌ | DEFER |

Building the 2 blocked ones "for real" requires a new table + a writer in **another service**
(backup-scheduler / meta-worker) — a schema migration (the user's L+ constraint) and a service
boundary crossing. Out of scope for a read-command batch → deferred with precise rows (below).
User confirmed "build the 2 real, defer the 2 blocked" via AskUserQuestion.

## Design decisions

### D1 — `projection drift-check` is FLEET-WIDE (no contract change)
The registry entry has params `projection_name` (required) + `sample_size` (default 100) and **no
`reality_id`**. `projection_drift_state` is per-reality (one row per projection table, PK
`table_name`, CHECK-fenced to the 10 L3.A tables). With no reality scope in the frozen contract,
the only contract-honest reading is fleet-wide: enumerate realities from `reality_registry`, read
each reality's `projection_drift_state` row for the named projection, aggregate. Also the more
useful operator query ("is `pc_projection` drifting *anywhere*?"). Per-shard read errors are
captured + reported, never fail the whole command (one down shard ≠ command failure).

### D2 — `sample_size` is accepted + validated, NOT silently applied (documented)
Migration `0007` is explicit: `projection_drift_state` is a per-table **summary**; "DO NOT widen
with sample-row payloads. Drift INVESTIGATION queries should be issued live against the projection
tables by SRE." So live re-sampling is NOT this table's job — it's the integrity-checker's
(cycle-14). v1 reports the maintained ledger (incl. each row's recorded `last_sample_size`).
`sample_size` is validated (`>= 1` if set) and its non-application is stated in the output +
deferred (`D-DRIFT-LIVE-RESAMPLE`). Accepting-but-documenting beats silently dropping a param.

### D3 — `projection_name` validated against the 10-table allowlist client-side
Fail fast with the allowed list before any DB work — mirrors the migration's CHECK constraint, and
keeps an arbitrary string from reaching N per-reality queries.

### D4 — `archive fetch` uses admin-cli's OWN thin minio-go wrapper (boundary)
The repo pattern is **each service owns its object-store wrapper** (book-service, provider-registry,
archive-worker each have their own minio-go client; none import another's). admin-cli importing
`services/archive-worker/pkg/*` would be a service→service code dependency (the boundary smell).
Instead admin-cli gets a ~25-line `miniofetch` wrapper (Get only) behind an `ArchiveBlobFetcher`
interface (prod = minio-go; tests = fake). minio-go `v7.0.100` is already used by 5 services.

### D5 — LWP1 header check duplicated (frozen ABI), full row-decode DEFERRED
The blob is the "LWP1 ABI" — `[0:4] magic 'LWP1'`, `[4:8] schema_version=2`, body, `[N-12:N-8]`
row_count, `[N-8:N-4]` body_size, `[N-4:N] 'LWP1'`; documented as "unchanged across the
stub→Parquet swap so archive_state rows stay valid." `archive fetch` validates this header
(magic+version+row_count vs `archive_state.row_count`) — the "decode header" the summary promises.
Duplicating the 3 constants + ~15-line check (vs a cross-service dep on D4) is the lesser evil for a
FROZEN ABI; a comment points to the canonical definition. Full Parquet row-decode is deferred
(`D-ARCHIVE-FETCH-DECODE`) — the command's job is fetch + header-integrity + persist the blob.

### D6 — `archive fetch` output: metadata always; raw blob only with `--out_path`
framework.Run returns `(string, error)` that main prints (newline-appended / JSON-wrapped) — unfit
for raw binary on stdout. So: always fetch + validate header + report metadata (object_key,
byte_size, row_count, archived_at, schema_version, header_valid). With `--out_path`, also write the
raw blob there + report bytes written. Without it, report metadata only + instruct to pass
`--out_path` for the blob (no binary-on-stdout corruption, no surprise files). The registry's
"default stdout" is interpreted as "metadata to stdout"; divergence flagged + `D-ARCHIVE-FETCH-STDOUT-STREAM`.

### D7 — object key built from the frozen shape, queried exactly
`events/<reality_id>/<YYYY>-<MM>.parquet`. `month` validated `^\d{4}-\d{2}$` before use; key built
deterministically; `archive_state` queried `WHERE reality_id=$1 AND object_key=$2` (exact, no
fragile partition_name regex). No row → "not archived for <month>" (not an error-error).

## Files

New (admin-cli, mirror the archive_list quartet):
- `internal/commands/projection_drift_check.go` — `DriftRow`, `ProjectionDriftReader`, `RunProjectionDriftCheck` (allowlist + format + aggregate + sample_size note)
- `internal/commands/projection_drift_check_pg.go` — `PgProjectionDriftReader` (meta pool + injected shard-DSN builder; enumerate realities → per-reality `projection_drift_state` read; per-shard errors captured)
- `internal/commands/projection_drift_check_test.go` — unit (fake reader): allowlist reject, sample_size validate, fleet aggregate, empty
- `internal/commands/projection_drift_check_pg_test.go` — PG-gated (apply 0007 + seed reality_registry + drift rows; override shard host to test DB)
- `internal/commands/archive_fetch.go` — `ArchiveObject`, `ArchiveMetaReader`, `ArchiveBlobFetcher`, `RunArchiveFetch` (resolve key → meta read → blob fetch → header verify → out_path/metadata)
- `internal/commands/archive_fetch_pg.go` — `PgArchiveMetaReader` (per-reality `archive_state` exact-key read)
- `internal/commands/miniofetch/miniofetch.go` — admin-cli's own minio-go Get wrapper (impl of `ArchiveBlobFetcher`)
- `internal/commands/archive_fetch_test.go` — unit (fake meta + fake fetcher): happy path, bad month, missing object, header-magic mismatch, row_count mismatch, out_path write
- `internal/commands/archive_fetch_pg_test.go` — PG-gated (apply 0011 + seed archive_state)

Edited:
- `cmd/admin/main.go` — `buildProjectionDriftCheckHandler()` + `buildArchiveFetchHandler()` (+ minio config from env) + 2 gated registration blocks; expose `buildShardDSN` to the drift reader
- `contracts/service_acl/matrix.yaml` — admin-cli: add `projection_drift_state: [SELECT]`; consolidate the pre-existing duplicate `reality_registry:` key; note `lw-event-archive` GET in prose
- `docs/deferred/DEFERRED.md` + `docs/sessions/SESSION_PATCH.md`

## Deferred rows opened
- `D-073-BACKUP-LIST-PERSISTENCE` (MED) — `backup list` blocked: needs a `backup_snapshots` meta table + backup-scheduler writing snapshot metadata. Read command is trivial once the SSOT exists.
- `D-073-CANON-CONFLICT-PERSISTENCE` (MED) — `canon conflict-list` blocked: `l1_conflict_reports` table + persist the l1_conflict_reporter output (meta-worker) instead of `InMemoryStore`.
- `D-DRIFT-LIVE-RESAMPLE` (LOW) — `projection drift-check --sample_size` live re-replay is the integrity-checker's job (cycle-14); v1 reads the maintained ledger.
- `D-ARCHIVE-FETCH-DECODE` (LOW) — full Parquet row-decode (reuse a shared decoder if a 3rd consumer appears → promote LWP1 ABI to a shared pkg).
- `D-ARCHIVE-FETCH-STDOUT-STREAM` (LOW) — raw blob to stdout when no `--out_path` (binary-safe streaming).

## Verification
- `go build/vet/test` admin-cli; gofmt; language-rule lint.
- Unit (fakes) for both commands; PG-gated tests (`PIIKMS_TEST_PG_URL`) re-run-safe + scoped.
- Live smoke: single-service (admin-cli) — `live infra unavailable` token if full MinIO+shard stack not bootable; else a real `archive fetch` against seeded MinIO.
- Full 15-lint matrix (per the session-59/111 lesson: run the WHOLE matrix, not the per-task subset).
- `/review-impl` (parallel adversarial, per command) before POST-REVIEW.
