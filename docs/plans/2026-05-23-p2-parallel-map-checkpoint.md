# Plan — P2 Parallel Map + Checkpoint (hierarchical extraction T3)

> **Spec:** [`docs/specs/2026-05-23-p2-parallel-map-checkpoint.md`](../specs/2026-05-23-p2-parallel-map-checkpoint.md).
> **Parent ADR:** [`docs/03_planning/KNOWLEDGE_SERVICE_HIERARCHICAL_EXTRACTION_ADR.md`](../03_planning/KNOWLEDGE_SERVICE_HIERARCHICAL_EXTRACTION_ADR.md).
> **P1 precondition:** [`docs/specs/2026-05-23-p1-structural-decomposer.md`](../specs/2026-05-23-p1-structural-decomposer.md) — `parts`/`scenes` tables + fallback contract.
> **Size:** XL · **Cycle:** session 63 (continuing from session 62).
> **Workflow:** default v2.2 (no `/amaw`).

---

## 1. File-by-file breakdown

### NEW files (12)

| # | File | Purpose | Lines (est) |
|---|---|---|---|
| 1 | `services/knowledge-service/app/db/migrations/p2_extraction_leaves.py` (or extend `migrate.py`) | Schema: `extraction_leaves` + `extraction_leaves_raw` + `knowledge_projects.save_raw_extraction` | ~80 |
| 2 | `services/knowledge-service/app/db/repositories/extraction_leaves.py` | Repo: `fetch_cached`, `claim_pending`, `persist`, `mark_failed`, `delete_by_book`, `reset_stale_claims` | ~220 |
| 3 | `services/knowledge-service/app/jobs/glossary_anchor_cache.py` | In-process LRU keyed strictly by `(book_id, chapter_index)` | ~80 |
| 4 | `services/knowledge-service/app/jobs/leaf_processor.py` | `process_leaf(scene, op, task_id, anchor, model_ref, parent_job_id)` + retry semantics | ~180 |
| 5 | `services/knowledge-service/app/jobs/task_id.py` | `compute_task_id(text, op, extractor_version, model_ref)` with M2 normalization | ~30 |
| 6 | `services/knowledge-service/app/routers/internal_extraction.py` (extend) — NEW handler `invalidate_cache` | `POST /internal/extraction/invalidate-cache/{book_id}` D5 two-step Tx | ~70 |
| 7 | `services/book-service/internal/api/scenes.go` | NEW HTTP handlers: `GET /internal/books/{book_id}/chapters/{chapter_id}/scenes` + `GET .../draft-text` | ~150 |
| 8 | `services/book-service/internal/api/scenes_test.go` | Handler unit tests (4-6 tests) | ~150 |
| 9 | `sdks/python/loreweave_extraction/_version.py` | `__extractor_version__` derived from sha256-of-prompts | ~40 |
| 10 | `services/knowledge-service/tests/unit/test_extraction_leaves_repo.py` | Repo unit tests (6 tests) | ~250 |
| 11 | `services/knowledge-service/tests/unit/test_leaf_processor.py` | leaf_processor unit tests (6 tests) | ~280 |
| 12 | `services/knowledge-service/tests/unit/test_internal_extraction_invalidate.py` | Invalidation endpoint tests (4 tests) | ~150 |

### MODIFY files (8)

| # | File | Change |
|---|---|---|
| M1 | `services/knowledge-service/app/db/migrate.py` | Append P2 schema block (parts/scenes are P1 — P2 adds extraction_leaves + extraction_leaves_raw + knowledge_projects.save_raw_extraction) |
| M2 | `services/knowledge-service/app/db/models.py` | `KnowledgeProject` Pydantic: add `save_raw_extraction: bool = False`. NEW `ExtractionLeaf` Pydantic model |
| M3 | `services/knowledge-service/app/extraction/pass2_orchestrator.py` | `_run_pipeline` refactored: fetch_scenes (with legacy fallback) + pre-dispatch dedup + asyncio.Semaphore fanout + aggregation. Thread `parent_job_id` for billing |
| M4 | `services/knowledge-service/app/clients/book_client.py` | NEW methods `list_scenes_by_chapter(chapter_id)` + `get_chapter_draft_text(chapter_id)` |
| M5 | `services/knowledge-service/app/clients/glossary_client.py` | Extend `list_entities` (rename to `list_known_entities`) with `before_chapter_index`/`recency_window`/`min_frequency`/`limit` params; raise `GlossaryAnchorUnavailable` on 5xx |
| M6 | `sdks/python/loreweave_extraction/__init__.py` | Export `__extractor_version__` from `_version.py` |
| M7 | `services/knowledge-service/tests/unit/test_pass2_orchestrator.py` (existing) | Extend with: legacy-fallback dispatch, parent_job_id threading, pre-dispatch dedup, aggregation shape preservation |
| M8 | `services/book-service/internal/api/server.go` | Wire new scenes.go handlers into the router |

**Total file count:** 12 NEW + 8 MODIFY = 20 file touches. Reconciles with XL classification (14 logic files declared at workflow-gate; tests + config bring up to 20).

---

## 2. Implementation order (DAG)

```
[Foundation — parallel]
  [1] SDK extractor_version (sdks/python/loreweave_extraction/_version.py)
  [2] book-service scenes endpoint + tests
  [3] knowledge-service schema migration + repos

[Middle — depends on Foundation]
  [4] glossary_anchor_cache + glossary_client extension (depends on glossary anchor contract)
  [5] task_id + leaf_processor (depends on [1] for extractor_version)
  [6] book_client.list_scenes_by_chapter + get_chapter_draft_text (depends on [2] BE endpoint)
  [7] invalidation endpoint handler (depends on [3] repos)

[Top — depends on Middle]
  [8] pass2_orchestrator refactor (depends on [4][5][6])

[Tests — interleaved]
  [T-repo] test_extraction_leaves_repo (depends on [3])
  [T-leaf] test_leaf_processor (depends on [5])
  [T-invalid] test_internal_extraction_invalidate (depends on [7])
  [T-orch] test_pass2_orchestrator (depends on [8])

[Live smoke — last]
  [9] cross-service: extraction-job → leaves persist → re-run cache-hit → invalidate-clears
```

**Suggested commit grain (per step):** 5 commits.
- Commit A: extractor_version SDK + schema migration + repos + book-service scenes endpoint (foundation).
- Commit B: glossary cache + glossary_client extension.
- Commit C: task_id + leaf_processor + invalidation endpoint.
- Commit D: book_client + pass2_orchestrator refactor.
- Commit E: SESSION_PATCH + SESSION_HANDOFF + deferred rows.

If session runs long, split-at-Commit-C is the clean cut.

---

## 3. Test sequencing

| Stage | Command | Expected |
|---|---|---|
| 3a | `pytest sdks/python/tests/test_extractor_version.py -v` | 2-3 tests: prompt-edit-bumps-version, deterministic-across-imports |
| 3b | `cd services/book-service && go test ./internal/api/scenes_test.go` | 4-6 handler tests green |
| 3c | `pytest services/knowledge-service/tests/unit/test_extraction_leaves_repo.py -v` | 6 repo tests green |
| 3d | `pytest services/knowledge-service/tests/unit/test_leaf_processor.py -v` | 6 leaf_processor tests green (cache-hit-skips-LLM, glossary-unavailable-marks-failed, retry-exhausted, etc.) |
| 3e | `pytest services/knowledge-service/tests/unit/test_internal_extraction_invalidate.py -v` | 4 invalidation tests green (deletion counts, op filter, internal-token, idempotent) |
| 3f | `pytest services/knowledge-service/tests/unit/test_pass2_orchestrator.py -v` | All pre-P2 tests preserved + 4-5 new P2 tests (legacy fallback, dedup, parent_job_id, aggregation) |
| 3g | `pytest services/knowledge-service/tests/unit/ -q` | Full knowledge-service unit suite parity (1654 baseline + new P2 = ~1680+) |
| 3h | Live smoke (full extraction run on Alice EPUB) | extraction_leaves rows materialise; re-run 100% cache hit; invalidate-cache clears |

---

## 4. Migration sequence (knowledge-service `migrate.py`)

Appended to existing `DDL` string after the K-cluster blocks.

```sql
-- ═══════════════════════════════════════════════════════════════
-- P2 (hierarchical extraction T3) - 2026-05-23
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS extraction_leaves (
  id                 UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id            UUID NOT NULL,
  scene_id           UUID NOT NULL,
  leaf_path          TEXT NOT NULL,
  op                 TEXT NOT NULL CHECK (op IN ('entity','relation','event','fact')),
  task_id            TEXT NOT NULL,
  status             TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','running','completed','failed')),
  candidates_jsonb   JSONB,
  retried_n          INT  NOT NULL DEFAULT 0,
  error_message      TEXT,
  parse_version      INT  NOT NULL DEFAULT 1,
  extractor_version  TEXT NOT NULL,
  model_ref          TEXT NOT NULL,
  glossary_anchor_size INT,
  started_at         TIMESTAMPTZ,
  completed_at       TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (book_id, leaf_path, op)
);

CREATE INDEX IF NOT EXISTS idx_extraction_leaves_task_id ON extraction_leaves(task_id);
CREATE INDEX IF NOT EXISTS idx_extraction_leaves_pending
  ON extraction_leaves(book_id, status) WHERE status IN ('pending','running');
CREATE INDEX IF NOT EXISTS idx_extraction_leaves_book ON extraction_leaves(book_id);

CREATE TABLE IF NOT EXISTS extraction_leaves_raw (
  extraction_leaf_id UUID PRIMARY KEY REFERENCES extraction_leaves(id) ON DELETE CASCADE,
  raw_response_jsonb JSONB NOT NULL,
  raw_token_usage    JSONB NOT NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE knowledge_projects ADD COLUMN IF NOT EXISTS save_raw_extraction BOOLEAN NOT NULL DEFAULT false;
```

**Idempotent re-run:** all CREATE/ALTER are IF NOT EXISTS. Safe to run on every startup.

**Test (`test_p2_migration.py`):** 5 tests for schema presence + index presence + idempotency + cascade FK.

---

## 5. Open implementation questions (resolve at BUILD)

- **IQ-P2-1**: `pass2_orchestrator` currently lives in `app/extraction/`. The new P2 jobs live in `app/jobs/`. Should P2's leaf-level code go in `app/extraction/` (cohesion with extractor logic) or `app/jobs/` (cohesion with worker-loop infrastructure)? **Recommend: `app/jobs/leaf_processor.py`** — it's worker-loop infrastructure (claims, retries, status writes), not extractor logic.
- **IQ-P2-2**: `extractor_version` constant — should `loreweave_extraction.__init__` recompute on every `import` (current spec) or cache via `functools.cache`? Module-level constant is already cached by Python's import system. **Recommend: keep simple module-level constant.**
- **IQ-P2-3**: Glossary `list_known_entities` — current `glossary_client.list_entities` has a different signature. **Plan**: rename to `list_known_entities` (more accurate; matches BE endpoint name) + keep old `list_entities` as a deprecated alias for one cycle to avoid breaking other callers. Audit at BUILD: grep for `glossary_client.list_entities` uses.

---

## 6. Risk-driven sequencing notes

- **Step 1 (extractor_version) first** because: tiny pure-Python add, no infra, but everything else depends on it for task_id. Land + commit + done.
- **Step 2 (book-service scenes) parallel** because: independent of knowledge-service; Go service rebuild + smoke is fast.
- **Step 3 (schema) parallel** because: schema migration is forward-only + idempotent. Safe to run before code uses it.
- **Step 8 (orchestrator refactor) LAST** because: it's the load-bearing integration point + needs all of 4/5/6/7 ready. The existing `test_pass2_orchestrator.py` regression-protects the legacy behavior through this refactor.

---

## 7. Estimated effort

- Step 1-3 (foundation, parallel): ~3h
- Step 4-7 (middle, parallel): ~4h
- Step 8 (orchestrator refactor): ~3h
- Tests interleaved: ~3h
- Live smoke: ~1h

**Total: ~14h.** Likely needs split across 2 sessions if doing it carefully. Clean cut at end of Commit C (steps 1-7 done, step 8 = next session's BUILD).
