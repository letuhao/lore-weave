# Plan — P3 Hierarchical Reduce + Per-Level Summaries (T4 + T7 stage 1)

> **Spec:** [`docs/specs/2026-05-23-p3-hierarchical-reduce.md`](../specs/2026-05-23-p3-hierarchical-reduce.md).
> **Parent ADR:** [`docs/03_planning/KNOWLEDGE_SERVICE_HIERARCHICAL_EXTRACTION_ADR.md`](../03_planning/KNOWLEDGE_SERVICE_HIERARCHICAL_EXTRACTION_ADR.md).
> **Preconditions:** P1 (`parts`/`scenes` schema, structural decomposer) + P2 (`extraction_leaves` cache, per-chapter cache wrap) committed.
> **Size:** XL · **Cycles:** session 64+ (multi-session per checkpoint pattern).
> **Workflow:** default v2.2 (no `/amaw`).

---

## 1. File-by-file breakdown

### NEW files (14)

| # | File | Purpose | Lines (est) |
|---|---|---|---|
| 1 | `sdks/python/loreweave_extraction/prompts/summarize_level.md` | NEW prompt template per D7 | ~30 |
| 2 | `sdks/python/loreweave_extraction/extractors/summarize.py` | summarize_level extractor (LLM via gateway) returning `LevelSummary` Pydantic | ~120 |
| 3 | `sdks/python/loreweave_extraction/_version.py` (EXTEND) | per-op `get_extractor_version(op=...)` per M3 | ~30 added |
| 4 | `services/knowledge-service/app/extraction/tree_merge.py` | Python deterministic merge (alias UF + canonical_id dedup + per-chapter chunked) per D1 | ~280 |
| 5 | `services/knowledge-service/app/extraction/hierarchy_writer.py` | Cypher MERGE for `:Book/:Part/:Chapter/:Scene` + `:HAS_CHILD` + `:MENTIONED_IN` edges per D2 + D2a | ~180 |
| 6 | `services/knowledge-service/app/db/neo4j_helpers.py` (EXTEND) | `summary_index_name()` + `ensure_summary_indexes()` per H1+M7 fix | ~80 added |
| 7 | `services/knowledge-service/app/db/repositories/summaries.py` (EXTEND) | NEW `SummaryRepo` methods: `upsert_chapter_summary`, `upsert_part_summary`, `upsert_book_summary` with `UniqueViolationError` handling per M5 | ~150 added |
| 8 | `services/knowledge-service/app/jobs/summary_processor.py` | NEW async consumer per D3 + D9 defensive child-readiness check + M4 re-enqueue | ~280 |
| 9 | `services/knowledge-service/app/db/migrate.py` (EXTEND) | 3 NEW Postgres tables (summary_chapters/parts/books) + `extraction_jobs.status` CHECK extension per M1 | ~80 added |
| 10 | `services/knowledge-service/tests/unit/test_tree_merge.py` | 10 tree-merge tests per spec §4.1 | ~400 |
| 11 | `services/knowledge-service/tests/unit/test_hierarchy_writer.py` | 5 writer tests per spec §4.2 | ~250 |
| 12 | `services/knowledge-service/tests/unit/test_summary_processor.py` | 5 processor tests per spec §4.3 | ~280 |
| 13 | `services/knowledge-service/tests/unit/test_mode3_intent.py` | 5 router intent tests per spec §4.4 | ~200 |
| 14 | `sdks/python/tests/test_extraction/test_summarize_level.py` | 3 extractor tests per spec §4.5 | ~150 |

### MODIFY files (4)

| # | File | Change |
|---|---|---|
| M1 | `services/knowledge-service/app/extraction/pass2_writer.py` | (a) Accept hierarchy paths (book/part/chapter/scene_path) per entity write; (b) write `:MENTIONED_IN -> :Scene` edge in the SAME Tx; (c) call hierarchy_writer.upsert_for_chapter at Tx start per D2a |
| M2 | `services/knowledge-service/app/extraction/pass2_orchestrator.py` | (a) After per-chapter pass2_writer succeeds: enqueue `summary.chapter` Redis message; (b) on `is_last_chapter=True`: enqueue `summary.part` × N + `summary.book` |
| M3 | `services/knowledge-service/app/db/neo4j_schema.py` | Add hierarchy constraints (scene/chapter/part/book path UNIQUE) at bootstrap |
| M4 | `services/knowledge-service/app/context/modes/full.py` (or NEW `app/context/intent/classifier.py`) | Mode-3 intent classification + multi-index summary query blend per D5 |

**Total file count:** 14 NEW + 4 MODIFY = 18 file touches. Matches XL classification.

---

## 2. Implementation order (DAG across 2-3 sessions)

```
[Session 64 — Foundation, ~5-6h]
  [1] SDK summarize_level.md + extractors/summarize.py + per-op get_extractor_version
  [2] Postgres migration: summary_chapters/parts/books + extraction_jobs.status CHECK
  [3] tree_merge.py (pure Python, fully testable; 10 unit tests)
  [4] hierarchy_writer.py + neo4j_schema.py constraints + neo4j_helpers index helpers
       (5 unit tests with mocked Cypher session)

[Session 65 — Integration + Async Summary, ~5-6h]
  [5] pass2_writer integration: hierarchy_writer call + :MENTIONED_IN edges (M1)
  [6] pass2_orchestrator: summary message enqueue + is_last_chapter flag plumbing (M2)
  [7] SummaryRepo extension with UniqueViolationError handling
  [8] summary_processor.py + worker-ai task registration (5 unit tests + extractor tests)

[Session 66 — Mode-3 Router + Live Smoke, ~3-4h]
  [9] Mode-3 intent classifier + multi-index summary query (5 unit tests)
  [10] Live smoke: full extraction → hierarchy → summary → Mode-3 abstract query
  [11] All deferred rows finalized in SESSION_PATCH
```

**Suggested commit grain (per session, ~3 commits total):**
- Commit A (session 64): Foundation — SDK + migration + tree_merge + hierarchy_writer.
- Commit B (session 65): Integration — pass2_writer/orchestrator changes + summary_processor + worker registration.
- Commit C (session 66): Router + live smoke + session docs.

Per `feedback_xl_cycle_natural_checkpoint_pattern`: clean cuts are end of session 64 (foundation isolated, no integration risk yet) AND end of session 65 (async pipeline complete but Mode-3 router still queries old shape).

---

## 3. Test sequencing

| Stage | Command | Expected |
|---|---|---|
| 3a | `pytest sdks/python/tests/test_extraction/test_summarize_level.py` | 3 extractor tests green |
| 3b | `pytest services/knowledge-service/tests/unit/test_tree_merge.py` | 10 tree-merge tests green |
| 3c | `pytest services/knowledge-service/tests/unit/test_hierarchy_writer.py` | 5 writer tests green |
| 3d | `pytest services/knowledge-service/tests/unit/test_summary_processor.py` | 5 processor tests green |
| 3e | `pytest services/knowledge-service/tests/unit/test_mode3_intent.py` | 5 router tests green |
| 3f | `pytest services/knowledge-service/tests/unit/test_pass2_orchestrator.py` | Existing 11 + 2 new (summary-enqueue + is_last_chapter plumbing) |
| 3g | `pytest services/knowledge-service/tests/unit/` | Full suite (1691 P2-baseline + ~35 new P3 ≈ 1726) |
| 3h | Live smoke (extraction → hierarchy → summary → abstract query) per spec §4.6 | Cross-service evidence per CLAUDE.md soft-WARN |

---

## 4. Migration sequence (knowledge-service `migrate.py`)

Appended to existing DDL string after the P2 block.

```sql
-- ═══════════════════════════════════════════════════════════════
-- P3 (hierarchical extraction T4 + T7 stage 1) — 2026-05-23
-- Spec: docs/specs/2026-05-23-p3-hierarchical-reduce.md §D4
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS summary_chapters (
  id                   UUID PRIMARY KEY DEFAULT uuidv7(),
  chapter_id           UUID NOT NULL,
  book_id              UUID NOT NULL,
  summary_text         TEXT NOT NULL,
  summary_input_md5    TEXT NOT NULL,
  embedding_dimension  INT  NOT NULL,
  embedding_model_uuid TEXT NOT NULL,
  generated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (chapter_id, embedding_model_uuid)
);
CREATE INDEX IF NOT EXISTS idx_summary_chapters_book ON summary_chapters(book_id);

CREATE TABLE IF NOT EXISTS summary_parts (
  id                   UUID PRIMARY KEY DEFAULT uuidv7(),
  part_id              UUID NOT NULL,
  book_id              UUID NOT NULL,
  summary_text         TEXT NOT NULL,
  summary_input_md5    TEXT NOT NULL,
  embedding_dimension  INT  NOT NULL,
  embedding_model_uuid TEXT NOT NULL,
  generated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (part_id, embedding_model_uuid)
);

CREATE TABLE IF NOT EXISTS summary_books (
  id                   UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id              UUID NOT NULL,
  summary_text         TEXT NOT NULL,
  summary_input_md5    TEXT NOT NULL,
  embedding_dimension  INT  NOT NULL,
  embedding_model_uuid TEXT NOT NULL,
  generated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (book_id, embedding_model_uuid)
);

-- M1: extend extraction_jobs.status CHECK to include 'summarizing'.
-- Idempotent: drop and re-add the constraint.
DO $$ BEGIN
  ALTER TABLE extraction_jobs DROP CONSTRAINT IF EXISTS extraction_jobs_status_check;
  ALTER TABLE extraction_jobs ADD CONSTRAINT extraction_jobs_status_check
    CHECK (status IN ('pending','running','summarizing','completed','failed'));
EXCEPTION WHEN OTHERS THEN NULL;
END $$;
```

**Test (`test_p3_migrate.py`):** 4 tests — 3 summary tables exist + extraction_jobs status check extended + idempotent re-run.

---

## 5. Open implementation questions (resolve at BUILD)

- **IQ-P3-1**: tree_merge.py location — `app/extraction/` (cohesion with extractor logic) vs `app/jobs/` (cohesion with worker infra)? **Recommend: `app/extraction/`** — tree_merge is pure-Python merge logic, sibling to pass2_writer.
- **IQ-P3-2**: hierarchy_writer Cypher Tx — write all hierarchy nodes in ONE Cypher or one per node? **Recommend: ONE Cypher per chapter** (matches pass2_writer per-chapter Tx; ~5-10 MERGE statements bounded).
- **IQ-P3-3**: summary_processor — separate worker-ai task or shared with extraction-job-processor? **Recommend: separate task** — different lifecycle (async after extraction), different stream, different consumer group; cleaner failure isolation.

---

## 6. Pre-flight checks (before BUILD starts)

- [ ] Confirm P1 + P2 changes deployed (knowledge-service rebuilt + extraction_leaves table verified live in postgres).
- [ ] Confirm `pytest services/knowledge-service/tests/unit/test_pass2_orchestrator.py` is green at HEAD (baseline preservation through P3 changes).
- [ ] Confirm `loreweave_extraction.__extractor_version__` is `v1-6dce61b7` (current — to verify per-op extension doesn't break baseline P2 cache).

---

## 7. Estimated effort

- Session 64 (Foundation: SDK + migration + tree_merge + hierarchy_writer): ~5-6h
- Session 65 (Integration: pass2_writer/orchestrator + summary_processor + SummaryRepo): ~5-6h
- Session 66 (Router + live smoke + session close): ~3-4h

**Total: ~13-16h across 3 sessions.** Matches XL classification + parent ADR §6 P3 acceptance scope.
