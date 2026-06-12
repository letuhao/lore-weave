# Phase E2 Mining Scaffold — Build Plan

**Date:** 2026-05-31  
**Spec ref:** `docs/specs/2026-05-31-phase-e2-mining-scaffold.md`  
**Workflow state:** DESIGN → REVIEW → PLAN (current)

---

## Sub-tasks

### E2-1 — KS genre field (M)
**Files:** `services/knowledge-service/app/db/migrate.py`, `app/db/models.py`, `app/db/repositories/projects.py`

- [ ] `migrate.py`: `ALTER TABLE knowledge_projects ADD COLUMN IF NOT EXISTS genre TEXT;`
- [ ] `models.py`: `genre: str | None = None` on `Project`, `ProjectCreate`, `ProjectUpdate`
- [ ] `repositories/projects.py`: add `genre` to `_SELECT_COLS`; add `"genre"` to `_UPDATABLE_COLUMNS`; add `"genre"` to `_NULLABLE_UPDATE_COLUMNS` (NULL clears it)
- [ ] Tests: update `test_projects.py` for create/update/get with genre; verify None roundtrip

### E2-2 — worker-ai genre emit (XS)
**Files:** `services/worker-ai/app/runner.py`

- [ ] `JobRow`: add `genre: str | None = None`
- [ ] `_get_running_jobs` SELECT: add `p.genre` to the column list
- [ ] `_get_running_jobs` result map: `genre=r["genre"]`
- [ ] `_build_run_payload` (around line 439): add `"genre": job.genre`
- [ ] Test: `_build_run_payload` forwards `job.genre` → payload key

### E2-3 — learning-service DDL + handler (S)
**Files:** `services/learning-service/app/db/migrate.py`, `app/events/handlers.py`

- [ ] `migrate.py`: `ALTER TABLE extraction_runs ADD COLUMN IF NOT EXISTS genre TEXT;`
  - Also add `CREATE INDEX IF NOT EXISTS idx_runs_genre ON extraction_runs(genre) WHERE genre IS NOT NULL;`
- [ ] `handlers.py → handle_run_completed`: read `payload.get("genre")`, add to INSERT columns + `$N` bind
- [ ] Test: `handle_run_completed` with `genre="Tiên hiệp"` inserts row with correct value; `genre=None` → NULL

### E2-4 — mining query layer (M)
**Files:** `services/learning-service/app/db/mining.py` (new)

- [ ] 4 async query functions: `get_config_quality`, `get_model_matrix`, `get_default_drift`, `get_outcome_recompute`
- [ ] Each takes typed params, returns `list[dict]`
- [ ] Exploration sampling for `get_config_quality`: second query `ORDER BY random()` from beyond top-N
- [ ] Tests: mock asyncpg rows; verify SQL param binding; verify power-user segmentation skips heavy users; verify empty result set on zero rows (cold-start)

### E2-5 — mining router + models (M)
**Files:** `services/learning-service/app/routers/mining.py` (new), `app/models.py`, `app/main.py`

- [ ] Response models: `ConfigQualityRow`, `ModelMatrixRow`, `DriftRow`, `OutcomeRecomputeRow`
- [ ] 4 GET endpoints; all JWT-authenticated; `user_id` filter on every query
- [ ] `exploration_fraction` Query param (default 0.1, range 0–0.5) on config-quality
- [ ] `power_user_threshold` + `segment_power_users` on config-quality
- [ ] Wire `mining.router` into `main.py`
- [ ] Tests: 4 endpoint tests (happy path with mock DB, cold-start empty response, auth missing → 401)

---

## VERIFY criteria

- `pytest services/knowledge-service` passes (genre CRUD tests + existing)
- `pytest services/worker-ai` passes (genre payload test + existing 91)
- `pytest services/learning-service` passes (DDL + handler + query + router tests)
- `python scripts/workflow-gate.py complete build "tests: KS ✓ / worker-ai ✓ / learning ✓; live-smoke deferred (D-E2-LIVE-SMOKE)"`

---

## Deferred

- **FE genre field** (project settings panel) — design separately once API is live
- **FE mining insights panel** — deferred per scope decision
- **Outcome refinement job** (batch UPDATE on extraction_runs from correction-join) — needs volume
- **D-E2-LIVE-SMOKE** — integration smoke across worker-ai → learning → mining endpoint; defer until stack rebuilt with E2 images
