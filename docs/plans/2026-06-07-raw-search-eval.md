# Plan — Raw-Search Retrieval Evaluation (P3-EVAL)

Spec: [docs/specs/2026-06-07-raw-search-eval.md](../specs/2026-06-07-raw-search-eval.md) · Branch `raw-search/foundation` · XL · executes E0→E4 (E5/E6 deferred).

Build order is **bottom-up** so each step is verifiable before the next depends on it: metrics (pure, TDD) → seed (data) → runner (reads data + metrics) → baselines.

## E2 — Metrics first (pure, TDD)
1. Add to [app/benchmark/metrics.py](../../services/knowledge-service/app/benchmark/metrics.py):
   - `hit_at_k(expected, results, k) -> float` — `1.0` if `set(expected) & set(results[:k])` else `0.0`; empty expected → `1.0`.
   - `ndcg_at_k(graded: Mapping[str,float], results, k) -> float` — `DCG@k/IDCG@k`; `DCG=Σ gain_i/log2(i+2)` (0-based i), gain `graded.get(rid,0.0)`; `IDCG` from sorted gains desc; `0.0` if IDCG==0; raise on `k<=0`.
2. Tests `tests/unit/test_rawsearch_metrics.py`: hit hit/miss/empty/k>len; ndcg perfect-order==1.0, reversed<1.0, empty-graded==0.0, k truncation, partial gains. Run `pytest tests/unit/test_rawsearch_metrics.py`.

## E0 — Corpus ingest
### E0a host seed `scripts/seed_rawsearch_eval.py`
- Const: `SRC_DIR = D:\Works\source\web-crawling\output\万古神帝-51254\chapters`, `N=40`, `BOOK_TITLE="万古神帝 — Raw-Search Eval (40ch)"`, `BGE_MODEL_ID=019e7f71-0271-722f-9c9c-3f049c0b26f4`, `EMB_DIM=1024`.
- `parse_chapter(path)`: drop the repeated-title/date/author header block, keep body paragraphs (split blank lines; the file's body starts after the 2nd title occurrence). Return `(title_from_filename, body)`.
- login claude-test → JWT + user_id. find-or-create book (by title). For i in 1..40: find-or-create chapter (title `NNNN-…`, sort_order=i, original_language=zh, body). Mirror `seed_fengshen_demo.find_or_create_chapters`.
- find-or-create `knowledge_projects` row (psql) for (user_id, book_id) with `embedding_model=BGE_MODEL_ID`, `embedding_dimension=1024`, `extraction_enabled=false`, `extraction_status='disabled'`.
- `docker exec infra-knowledge-service-1 python -m app.benchmark.ingest_rawsearch_corpus --book-id … --project-id … --user-id … --embedding-model BGE_MODEL_ID --embedding-dim 1024` → parse JSON.
- Verify: psql `chapter_blocks` count for book > 0; ingest JSON `passages>0`. Print JSON summary `{book_id, project_id, chapters, blocks, passages}`.
- **R2 probe:** before the 40-loop, create 1 chapter, `docker exec … python -c` (or a `--probe` mode of the ingest module) to confirm `get_chapter_text` returns the posted body and one chunk embeds. Abort with a clear message if draft text is empty.

### E0b container ingest `app/benchmark/ingest_rawsearch_corpus.py`
- argparse: `--book-id --project-id --user-id --embedding-model --embedding-dim [--chapter-id (probe)]`.
- bootstrap like `eval/run_benchmark.py`: imports inside fn; `init_neo4j_driver()`, `init_embedding_client()`, `get_book_client()`.
- list chapters for the book via `book_client` (or accept ids from stdin); for each: `ingest_chapter_passages(session, book_client, embed, user_id, project_id, book_id, chapter_id, chapter_index=sort_order, embedding_model, embedding_dim, revision_id=None)`.
- Print JSON `{chapters_ingested, passages_total, errors:[…]}`. Best-effort per chapter (log+continue).

## E1 — Golden set `app/benchmark/rawsearch_golden.yaml`
- Author **after** E0 (need real chapterIds). Method: pick ~18 distinctive terms from the 40 chapters (names 张若尘/池瑶/秦雅, places, techniques 龙象般若/天心剑法, events), run the lexical oracle (psql `ILIKE`) to list containing chapters; set `expected=[chapterId…]`, `graded={chapterId: rel}` (origin/topic chapter rel 3, mentions 1–2), `band` ∈ {exact, paraphrase, negative}. ≥2 negatives (terms verified absent).
- Schema per query: `q`, `expected: [uuid]`, `graded: {uuid: int}`, `band`. Top-level `book_id`, `project_id`.

## E3 — Runner `scripts/run_rawsearch_eval.py`
- `sys.path.insert(0, 'services/knowledge-service')`; `from app.benchmark.metrics import hit_at_k, recall_at_k, reciprocal_rank, ndcg_at_k, mean`.
- Load golden yaml. login claude-test. For `mode in [lexical, semantic, hybrid]`, `K in [5,10]` (configurable): for each query GET `http://localhost:8216/v1/knowledge/books/{book_id}/search?query=&mode=&limit=K` (Bearer JWT) → `results[].chapterId` ranked. Compute per-query metrics; aggregate `mean` per (mode,K). Track `degraded` reasons seen.
- Print a table: rows=mode, cols=hit@5, recall@5, MRR, ndcg@5 (+K=10). Emit JSON. (R4: if direct :8216 rejects JWT, fall back to gateway `:3123`.)
- Lexical oracle recall: for each query, psql exact-substring chapter set; recall of `mode=lexical` top-K vs that set; print as a column / separate line.

## E4 — Semantic flat-kNN baseline `app/benchmark/flat_knn_rawsearch.py`
- argparse `--project-id --user-id --embedding-model --embedding-dim --query --k`.
- embed query; `find_passages_by_vector(..., include_vectors=True, limit=BIG)` to pull all candidates **with vectors**; compute exact cosine in Python; rank → flat top-k chapterIds. Print JSON.
- Runner compares endpoint `mode=semantic` top-k vs flat top-k → **ANN recall@k** (overlap / k), averaged. (Spawned by E3 per query, or a batch mode.)

## VERIFY (evidence gate, ≥2 services → live-smoke token)
- `pytest tests/unit/test_rawsearch_metrics.py` green (full output).
- Rebuild knowledge image (ships new `app/benchmark/*`): `docker compose build knowledge-service && docker compose up -d knowledge-service` (or `scripts/build-stack.sh`).
- Run `scripts/seed_rawsearch_eval.py` → capture `{chapters:40, blocks>0, passages>0}`.
- Run `scripts/run_rawsearch_eval.py` → capture the per-mode table + oracle recall + ANN recall. Evidence string: `live smoke: rawsearch eval ran 3 modes on 40ch 万古神帝, hybrid hit@5=…`.

## REVIEW(code) 2-stage → QC → POST-REVIEW (STOP) → SESSION → COMMIT → RETRO
- Suggest `/review-impl` (new service-boundary-ish tooling touching book + knowledge + neo4j + embeddings).
- Deferred rows to add: `D-RAWSEARCH-E5-TUNING` (RRF_K/cap/K sweep), `D-RAWSEARCH-E6-FE-KSELECTOR`, `D-RAWSEARCH-EVAL-CI` (threshold gate + persist runs).
