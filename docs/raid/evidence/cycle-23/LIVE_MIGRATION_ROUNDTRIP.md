# C23 — Live migration round-trip + GUARD (real composition PG)

**DB:** `loreweave_composition` on infra-postgres-1 (host :5555) — the LIVE dev DB with 165 existing `composition_work` rows (briefed ~163).

**Evidence token:** `migration round-trip clean + null project_id rejected`

## Round-trip on the live DB (up → down → up)

```
PRE: rows=165, null-project=0
AFTER UP:    {source_col:1, branch_col:1, spec_tbl:True,  override_tbl:True,  guard:1}  rows=165
GUARD OK: null project_id derivative rejected   (CheckViolationError on chk_derivative_project_required)
C16 greenfield null insert ACCEPTED (non-derivative null-project row allowed; rolled back)
AFTER DOWN:  {source_col:0, branch_col:0, spec_tbl:False, override_tbl:False, guard:0}
AFTER RE-UP: {source_col:1, branch_col:1, spec_tbl:True,  override_tbl:True,  guard:1}  rows=165
ROUNDTRIP CLEAN: no residue; 165 existing rows preserved
```

## What this proves

1. **Migration up** adds `source_work_id` + `branch_point` columns, `divergence_spec` + `entity_override` tables, and the `chk_derivative_project_required` CHECK — against the 165 live rows (all `source_work_id` NULL → all pass the conditional guard). Row count unchanged.
2. **GUARD enforced at the DB:** a DERIVATIVE row (`source_work_id` set) with `project_id = NULL` is rejected with `CheckViolationError`. This is the cross-project grounding-leak guard (G2/ARCH-REVIEW).
3. **C16 greenfield null-path NOT regressed:** a NON-derivative (`source_work_id` NULL) row with `project_id = NULL` + `pending_project_backfill = true` is still ACCEPTED — the conditional CHECK exempts greenfield. (Inserted under a transaction and rolled back so the live DB is untouched.)
4. **Down SQL (`C23_DOWN_SQL`)** drops the 2 tables + the constraint + the source index + the 2 columns cleanly.
5. **Re-up restores exactly** — identical schema state, 165 rows still preserved, no residue. Idempotent.

## Unit + integration evidence
- `verify-cycle-23.sh` exit 0 (static greps + py_compile + provider-gate + pytest).
- 31 router unit tests (6 new C23 derive tests) pass.
- 12 real-PG integration tests (5 new C23: guard rejects null-project derivative, greenfield null still allowed, create_derivative links source+branch_point, spec/override roundtrip, migration up→down→up clean) pass on the throwaway test DB.
- Full composition unit suite 447 passed; full integration suite 66 passed.
- provider-gate green (composition has no AI imports).
