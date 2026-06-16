# S4 — Runtime invariant assertions (foundation runtime test plan)

> **Status:** PLAN (awaiting approval). **Size:** L. **Mode:** human-in-loop, per-increment checkpoints, `/review-impl` before commit.
> **Scope decision (user, CLARIFY 2026-06-12):** **full breadth in one L pass** (all six targets, `notrun` where infra genuinely isn't provisionable); pgvector = **a basic live probe**, not design-only.
> **Slice:** S4 of `docs/specs/2026-06-04-foundation-runtime-test-plan.md` §10. Depends on **S1** (conformance runner + catalog) — DONE. Folds new cases into the existing catalog.

## 1. Goal

Assert the **runtime invariants** hold against real DB state, reporting into the S1 verdict contract `{pass|fail|notrun|skip}` (only `fail` breaks the gate). Six targets:

| # | Target | Invariant | Substrate | Off-stack verdict |
|---|---|---|---|---|
| 1 | **VerificationMeta conformance** — every projection table carries the 5-col block (`event_id`, `aggregate_version`, `applied_at`, `last_verified_event_version`, `last_verified_at`) | Q-L3-4 | live (information_schema) | notrun |
| 2 | **CHECK conformance** — expected CHECK constraints present (status/enum/jsonb_typeof/non-negative) | schema integrity | live (information_schema) | notrun |
| 3 | **pgvector probe** — `vector` ext installed + embedding table is `VECTOR(1536)` (or documented BYTEA fallback) | Q-L3I-1 | live | notrun |
| 4 | **I5 reality_registry CHECK** — a bad `db_host`/`db_name` row is rejected (real CHECKs `reality_registry_db_host_format` + `db_name_nonempty` — verified present) | I5 | live (meta DB) | notrun |
| 5 | **I8 meta append-only** — grant a baseline → the migration's REVOKE removes UPDATE/DELETE → assert **INSERT ok AND UPDATE/DELETE denied** | I8 | live (meta DB + **grant-then-migration-revoke**) | notrun |
| 6 | **I9 lifecycle CAS** — `AttemptStateTransition` rejects an illegal transition + a stale-CAS update | I9 | **go-probe binary `metaprobe`** (committed substrate; no SQL fallback) | notrun |
| 7 | **I4 DB-per-service isolation** — **NO in-repo artifact** (the privilege model is the unbuilt provisioner, R4-L1); ships as a documented **notrun placeholder** + deferred | I4 | n/a | **notrun (always)** |
| 8 | **upcaster conformance** — registry round-trips (`npc.said` v1→v2) + **every event whose `_registry.yaml` carries `deprecations[].upcaster_to: N` (or `versions` len>1) has a registered upcaster** | I14 | **go-test (always runs, fail-closed)** | — |

**Honest framing (sharpened by /review-impl on this plan):**
- Targets 1–6 are **live probes** — on a bare CI runner (no `foundation-stack`) they read `notrun`, not vacuous pass; real PASS on a stack-up where the probe provisions what it needs.
- **I8 (#5) is only meaningful with the grant-baseline step.** The migrations contain *only* REVOKEs — nothing grants `app_service_role` any privilege — so a bare-role "UPDATE denied" would pass *vacuously* (denied for lack of any privilege, not the append-only REVOKE). The probe must GRANT INSERT/UPDATE/DELETE, then exercise the migration's REVOKE, then assert INSERT-ok + UPDATE-denied. The probe-supplied GRANT stands in for the (unbuilt) platform provisioning; the migration's REVOKE is the artifact under test.
- **I4 (#7) has no in-repo artifact at all** — cross-DB CONNECT isolation lives in the provisioner (R4-L1, unbuilt). A self-provisioned probe would test its own grants (tautology). Ships as a **notrun placeholder case** documenting the invariant + `D-S4-I4-PROVISIONER`; it becomes a real PASS when the provisioner ships.
- Target 8 (upcaster) is a pure go-test → always runs, fail-closed on a build break.
- The pgvector probe asserts presence+dimension only (not HNSW recall — later perf cycle).

## 2. Design

### 2.1 Case taxonomy (folds into `tests/conformance/catalog/`)

Each case is a probe command that does its own setup, asserts, exits **0=pass / 1=fail (real violation) / 2=notrun (can't provision here)**. Every live probe also supports a `--self-test` mode that runs BOTH polarities (a known-good and a known-bad input) and asserts the bad one exits 1 — so the oracle-bite proof is a **standing, reproducible** check, not a one-time VERIFY demo (finding #6).

**Granularity decision (finding #7):** the three *schema* checks share one DB-setup → one script with a `--check {verification-meta|check-constraints|pgvector}` arg, exposed as **3 thin catalog cases** (cheap: each re-invokes the script, which reuses a prepared DB via `CONFORMANCE_SCHEMA_DSN` if set, else builds one). The *meta-invariant* checks (I5/I8/I9) re-provisioning a meta DB + roles + 32 migrations is expensive, so they collapse into **one bundled `meta-invariants` case** whose output names the failing invariant (`FAIL[I8]: …`) — coarser granularity traded for setup cost, the failing invariant still identified in the tail. I4 is a **separate notrun placeholder case** (no setup).

New catalog files under `tests/conformance/catalog/generic/`:
- `verification-meta-conformance.yaml` · `check-constraint-conformance.yaml` · `pgvector-schema-conformance.yaml` (kind: `live-probe`, requires: `foundation-stack`)
- `meta-invariants.yaml` (I5+I8+I9 bundled; kind: `live-probe`, requires: `foundation-stack`)
- `db-per-service-isolation.yaml` (I4; kind: `live-probe`, **requires: `["provisioner-roles"]`** — a predicate nothing provides today → always notrun until R4-L1)
- `upcaster-conformance.yaml` (kind: `go-test`, requires: `[]`)

### 2.2 Probe substrate

- **Schema probes (1–3):** `scripts/conformance/schema-conformance-smoke.sh --check <name>` creates/reuses a throwaway per-reality DB, applies `contracts/migrations/per_reality/*.up.sql`, runs SQL assertions over `information_schema`:
  - **VerificationMeta (#4 fix):** the projection-table set is **NOT** discovered by a `LIKE '%_projection'` pattern — that silently misses `session_participants` and `npc_session_memory_embedding`. The probe carries the **authoritative 11-table list** (the same set as `tests/workload-gen/internal/projcheck/load.go`; keep them in sync — note the cross-reference in both), asserts each carries all 5 VerificationMeta cols, AND asserts the discovered count == 11 so a new table can't be silently skipped.
  - **CHECK (#5 fix):** asserts a **pinned, named** high-value set (e.g. `pc_projection_status_valid`, `npc_session_facts_is_object`, `region_exits_is_array`, `pc_inventory_qty_nonneg`, `reality_registry_status_enum`) exists in `information_schema.check_constraints` — framed honestly as a **regression-lock** (it pins the constraints the spine relies on; it is not an exhaustive proof every needed CHECK exists). If the pinned set feels arbitrary, the case is dropped rather than shipped tautological.
  - **pgvector:** `pg_extension` has `vector`; `npc_session_memory_embedding.embedding` is `VECTOR`/`USER-DEFINED` dim 1536 (or the documented BYTEA(6144) fallback) — presence + dimension only.
- **Meta-invariant probe (4–6, bundled):** `scripts/conformance/meta-invariants-smoke.sh` creates a throwaway **meta** DB, applies `migrations/meta/*.up.sql`, `CREATE ROLE app_service_role / app_admin_role`, then:
  - **I5:** INSERT `reality_registry` with `db_host='garbage'` → expect CHECK violation (`reality_registry_db_host_format`); a well-formed row → ok.
  - **I8 (#1 fix — non-vacuous):** `GRANT INSERT, UPDATE, DELETE ON meta_write_audit TO app_service_role` (baseline the migrations don't provide), then **re-run 013's REVOKE block** (the artifact under test), then `SET ROLE app_service_role`: a valid INSERT **succeeds** AND an UPDATE/DELETE is **denied**. Asserting both polarities is what makes it non-vacuous.
  - **I9 (#3 fix — committed Go substrate):** a `tests/conformance/cmd/metaprobe` binary opens the meta DB and calls `contracts/meta.AttemptStateTransition` for (a) a legal transition → ok, (b) an illegal transition → rejected, (c) a stale-CAS (wrong `from_state`) → rejected. **No SQL-CHECK fallback** — a CHECK can't model the transition graph/CAS, so it would not cover I9. If `AttemptStateTransition` needs more wiring than the binary can supply, I9 ships `notrun` + `D-S4-I9-FUNCTION-PROBE` (never a non-equivalent green).
- **I4 (7):** a `db-per-service-isolation` case that is a **documented notrun placeholder** — `requires: ["provisioner-roles"]` (unprovided) so it always reads notrun, with a description naming the invariant + `D-S4-I4-PROVISIONER`. No fake self-provisioned setup (that would test the probe, not a platform artifact).
- **Upcaster (8, #8 pin):** a `go-test` case over `contracts/events/upcasters_go` + a coverage assertion: parse `contracts/events/_registry.yaml`, and for every event with `versions` length > 1 (or a `deprecations[].upcaster_to: N`), assert a corresponding upcaster is registered (today: `npc.said` v1→v2). Fails if a future version bump lands without its upcaster.

### 2.3 Verdict mapping leveraged
`exit 2` from a probe = "couldn't provision here" → **notrun** (lenient, not fail). `requires: foundation-stack` gates the live cases to notrun on a bare runner; `requires: ["provisioner-roles"]` gates I4 to notrun until R4-L1. Real invariant violation = **exit 1** = fail (gate-breaking). Build failure in the go-test case = exit ≥2 fail-closed.

## 3. Acceptance gate
- `go test ./tests/conformance/...` green (catalog loads + validates the **7 new cases**; runner unaffected). *(8 targets → 7 cases: 3 schema + 1 bundled meta + 1 I4-placeholder + 1 upcaster; pgvector folds into the schema trio.)*
- Static **upcaster-conformance** PASSes on a bare runner (no stack); its coverage assertion fails if an upcaster is removed.
- On a stack-up: the 4 live schema+meta cases **PASS**; **I4 reads `notrun`** (documented placeholder, not fake-pass).
- **Oracle-bite is standing, not a demo (finding #6):** each live probe's `--self-test` runs both polarities and is exercised in VERIFY; the negative input (CHECK-violating row, denied UPDATE, illegal transition, missing upcaster) makes the probe exit 1. This is reproducible (re-runnable), mirroring S2/C3 corruption-injection discipline.
- **I8 non-vacuity proven (finding #1):** the self-test shows the INSERT-succeeds leg too — so a "denied" result can't be the trivial no-privilege denial.
- `conformance` runner run shows every new case in its summary (pass / notrun — never silent).
- Live-smoke evidence string with the cross-service token.
- Lints: `gofmt`/`go vet`/`shellcheck`(if available)/`language-rule` clean.

## 4. Build increments (human-in-loop — stop after each)
1. **Upcaster conformance** (go-test, no stack) — wrap `upcasters_go` + the `_registry.yaml` coverage assertion (`deprecations[].upcaster_to` / `versions` len>1) + YAML. Fastest, always-on, proves the catalog-add flow.
2. **Schema conformance** (VerificationMeta + CHECK + pgvector) — `schema-conformance-smoke.sh --check <name>` with the authoritative 11-table list + count-assert + pinned named CHECK set + pgvector presence/dim; 3 YAML cases; `--self-test` both polarities; TDD against the real migrated schema.
3. **Meta invariants I5 + I8** — `meta-invariants-smoke.sh`: I5 bad-`db_host` → CHECK violation; I8 **grant-baseline → migration REVOKE → INSERT-ok + UPDATE-denied** (non-vacuous); `--self-test`; bundled `meta-invariants.yaml`.
4. **I9 metaprobe + I4 placeholder** — `tests/conformance/cmd/metaprobe` calling `AttemptStateTransition` (legal/illegal/stale-CAS) folded into the meta-invariants case; `db-per-service-isolation.yaml` as a `requires: ["provisioner-roles"]` notrun placeholder.
5. **Live VERIFY** — stack-up, run the `conformance` runner, confirm the 4 live cases PASS + I4 notrun + each `--self-test` bites; capture evidence.

## 5. Risks / deferrals
- **`D-S4-I4-PROVISIONER`** (finding #2) — DB-per-service isolation (I4) has **no in-repo artifact**; the privilege model is the unbuilt provisioner (R4-L1). Ships as a notrun placeholder. Becomes a real probe when the provisioner + role-bootstrap land. (Supersedes the earlier `D-S4-I4-CROSS-HOST` framing — even same-cluster I4 has nothing to test today.)
- **`D-S4-I9-FUNCTION-PROBE`** — if `AttemptStateTransition` needs more wiring (meta DB handle, clock, seeded resource) than the `metaprobe` binary can cleanly supply, I9 ships `notrun` (NOT a non-equivalent SQL-CHECK green) and the full-function probe is tracked here.
- **`D-S4-PGVECTOR-RECALL`** — the probe asserts presence + dimension only; HNSW recall/comparator quality is S7 perf-cycle work.
- **`D-S4-VERIFMETA-TABLE-SYNC`** — the authoritative 11-table list is duplicated between the schema probe and `projcheck/load.go`; both must update together when a projection table lands. (Same drift class as `D-PROJCHECK-TABLE-DRIFT`; the count-assert makes a miss loud, not silent.)
- **shellcheck** may be unavailable on Windows dev → lint that case notrun locally, runs in CI.
