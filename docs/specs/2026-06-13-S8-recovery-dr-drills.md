# S8 — Recovery / DR drills (Technique G)

**Spec date:** 2026-06-13 · **Branch:** `mmo-rpg/foundation-mega-task` · **Size:** L
**Parent plan:** `docs/specs/2026-06-04-foundation-runtime-test-plan.md` §7 (Technique G)
**Depends on:** S2/C (no-orphan) ✅, S2b/C3 (ledger) ✅, S5 (rebuild path) ✅, S6 (publisher + chaos harness + history checker) ✅
**CLARIFY decisions (user, 2026-06-13):** build **all 4 drills** (full Technique G; drill #5 catastrophic-rebuild EXPUNGED per DEFERRED 149); drill #3 = **full Parquet round-trip + C3 byte-match**.

---

## 0. Governing discipline (same as S4–S7)
Every drill is a recovery scenario whose oracle is an existing correctness check (B / C / C2 / C3 / the
S6 history checker). Each ships a **bite-test** proving the oracle can fail (non-vacuity). Verdict
convention from S6: fault/setup couldn't run → **notrun** (exit 2, never flaky-fail); an invariant
violated under recovery → **fail** (exit 1).

## 1. Survey — what already exists (honest scoping)
- **Publisher** (Go, single-goroutine, `FOR UPDATE SKIP LOCKED`, idempotent `published` marking) + the
  S6 chaos harness + **bash history checker** (no-loss/no-dup vs the event log) → reused by G1.
- **`rebuilder`** bin (`--reality-id --projection [--parallel-workers]`) + `rebuilder_live.rs` (the B
  round-trip) → reused by G2 + G4.
- **`archive-worker`** (PG partition → Parquet+ZSTD → MinIO → verify → DETACH+DROP; eligibility =
  `ARCHIVE_CUTOFF`, default 90d) + **`archive-restore`** CLI (`restore --reality <uuid> --month
  YYYY-MM` → downloads Parquet → re-inserts into `events_restore_<YYYYMM>`) → the enabler for G3. The
  spec §7 said this orchestration was "not yet shown to exist"; it **does** now.
- **`restore-drill.sh` is NOT this** — it is the pg_dump/pg_restore *physical-backup* drill
  (backup-scheduler domain, Q-L1H-2), with its live runner deferred (`D-BACKUP-LIVE-RESTORE-RUNNER`).
  S8's drills are the **event-sourcing** recovery path (archive-from-events, rebuild, replay), distinct.
- `oracles`: B = `projection == replay(events)` (wg `-verify` / integrity-checker); C = no-orphan
  (wg `-check-projections`); C2 = from-spec golden; C3 = ledger checksum/global-sequence
  (`tests/workload-gen/internal/ledger`).

## 2. The four drills

### G1 — kill+restart mid-workload → convergence  (`scripts/chaos/recover-kill-restart.sh`)
Emit a workload → start the **real publisher** draining outbox→Redis → **SIGKILL it mid-drain**
(after partial publish) → **restart the same publisher** → wait for quiesce → assert convergence.

**Delivery contract = at-least-once, NOT exactly-once (review HIGH-1).** The publisher XADDs with an
auto-generated stream id (`redisemit.go` sets no `ID`) and marks `published=TRUE` in a *separate*
step. A SIGKILL **between a successful XADD and the mark** therefore legitimately re-XADDs the same
`event_id` (new stream id) on restart — a duplicate is **expected**, not a violation. The consumer
dedups by `event_id`. So the oracle is **no-loss + dedup-able**, never no-dup:
- outbox fully drained (`published=TRUE` for all), **no dead-letter**; C3 (`wg -verify`) clean.
- **history checker (reframed):** `distinct(event_id) == events` — every event present exactly once
  by id (no loss, no spurious id) — and `XLEN >= events` (duplicates allowed, must carry a known
  `event_id`). This is the real DR property: a kill never drops an event, and any duplicate is
  dedup-able by id.
- **Bite:** **XDEL a stream entry** after quiesce → `distinct(event_id) < events` → loss caught (the
  S6 bite). (Injecting a *duplicate* is NOT a bite here — a duplicate is expected at-least-once
  behavior.)

### G2 — rebuild-from-events → B ∧ C ∧ C2  (`scripts/chaos/recover-rebuild.sh`)
Emit → **TRUNCATE the projection tables** (simulate total projection loss) → run `rebuilder` per
populated table → assert **B** (wg `-verify`: projection == replay), **C** (wg `-check-projections`:
no orphan rows), **C2** (from-spec row counts). DR framing: projections are derived state and MUST be
fully reconstructable from the event log alone.
- **Bite:** skip the rebuild step → B fails (empty projection ≠ replay) → proves the drill's oracle bites.

### G3 — restore-from-archive (Parquet round-trip) → C3 byte-match  (`scripts/chaos/recover-archive-restore.sh`)
**Partition routing (review MED-2):** wg emits with a *current* `recorded_at`, which lands in
`events_p_default` — invisible to the archiver's `partition_picker` (it enumerates `events_p_YYYY_MM`
only). So the drill explicitly creates a **last-month** partition
`events_p_<YYYY_MM> PARTITION OF events FOR VALUES FROM ('<lastmonth>-01') TO ('<thismonth>-01')` and
lands rows there with a **backdated `recorded_at`** — cleanest via `INSERT INTO events (…) SELECT …,
'<lastmonth-15>'::timestamptz` from a wg-staged set (avoids cross-partition row movement).

Flow: build the backdated partition → **C3 digest the window** → run `archive-worker` with
**`ARCHIVE_CUTOFF=0`** (the last-month partition is then eligible) → it writes
Parquet→MinIO→verifies→**DROPs the partition** → `archive-restore restore --reality --month` → rows
land in `events_restore_<YYYYMM>` → **C3 digest the restored rows** → assert pre==post.
- **C3 digest mechanism (review MED-4):** a deterministic SQL digest over a FIXED column list, NOT
  the Go ledger package (no bash CLI) nor `wg -verify` (reconciles vs a *seed*, not arbitrary rows):
  `SELECT md5(coalesce(string_agg(event_id::text || '|' || payload::text, '|' ORDER BY global_seq),''))`
  computed pre-archive on `events` (window-filtered) and post-restore on `events_restore_<YYYYMM>`.
  The column list must be the intersection present in BOTH tables (review LOW-5): `event_id`,
  `payload`, `global_seq`(or the ordering key), `reality_id` — verified at BUILD.
- **Bite:** after restore, mutate one restored row's `payload` (or delete a row) → post digest ≠ pre
  → fail. (Blob-corruption is the stronger bite if cheap; else a post-restore row mutation.)
- **MinIO** is required → the script checks MinIO reachability and **notruns** if absent (the
  `foundation-stack` predicate only covers PG+Redis).

### G4 — replay determinism across two rebuilds  (`scripts/chaos/recover-replay-determinism.sh`)
Rebuild a projection → snapshot → TRUNCATE → rebuild **again** → snapshot → **assert the two
snapshots are byte-identical**. This is the *deterministic-replay* facet of C; **do NOT double-count
with H0** (the cross-language Go-write/Rust-replay differential) — this is same-engine run-to-run
determinism.
- **Deterministic columns only (review MED-3):** the snapshot must EXCLUDE any per-run
  non-deterministic column the rebuilder writes (`updated_at`/`rebuilt_at`/serial surrogate) — else
  two rebuilds differ on a timestamp and G4 falsely fails. Build the snapshot over a fixed
  deterministic projection of columns (verify `pc_projection`'s schema at BUILD; if it carries a
  rebuild timestamp, project `to_jsonb(t) - 'updated_at' - …`, else snapshot the whole row and
  document that no non-deterministic column exists). Order by PK.
- **Bite:** compare rebuild(seed A) against rebuild(seed B) → snapshots **differ** → proves the
  byte-compare has teeth (a no-op compare that always passes would fail this).

## 3. Conformance + CI
- 4 live-probe catalog cases (`recover-kill-restart`, `recover-rebuild`, `recover-archive-restore`,
  `recover-replay-determinism`), `requires:[foundation-stack]` (G3 additionally self-checks MinIO →
  notrun). Verdict mapping per S6.
- CI: add a **`recovery-nightly`** job (schedule/workflow_dispatch) that boots the stack (PG+Redis+
  MinIO), builds the binaries (`rebuilder`, `wg`, `ic`, `pub`, `archive-worker`, `archive-restore`),
  and runs the 4 drills — mirroring the S5/S6 nightly pattern (dormant on this branch until merge).

## 4. Out of scope / deferred
| ID | Item |
|---|---|
| (expunged) | Drill #5 catastrophic-rebuild — DEFERRED 149, removed from the backlog per §7. |
| `D-S8-CLOCK-SKEW-RECOVERY` | Recovery under clock skew (NTP step during drain) — needs a clock-control harness, not in G. |
| `D-S8-MULTI-SHARD-DR` | Whole-system quarterly DR (N shards restored together) — runbook-driven, manual; out of the per-drill automation scope. |
| `D-BACKUP-LIVE-RESTORE-RUNNER` | (pre-existing) the pg_dump physical-restore live runner — separate from S8's event-sourcing drills. |

## 5. Acceptance
- G1 converges after SIGKILL+restart: **no-loss + dedup-able** (`distinct(event_id)==events`,
  `XLEN>=events`) + C3 clean; bite (**XDEL → loss**) caught. (At-least-once: duplicates are expected,
  not a violation.)
- G2 rebuild restores B∧C∧C2 from events alone; bite (skip rebuild) caught.
- G3 Parquet round-trip restores byte-matching events (C3); bite (corruption) caught; MinIO-absent → notrun.
- G4 two rebuilds byte-identical; bite (different seed) caught.
- 4 conformance cases pass through the runner (notrun where stack/MinIO absent); `recovery-nightly` wired.
- No absolute numbers asserted; the oracles (B/C/C2/C3/history) are the pass/fail signal.
