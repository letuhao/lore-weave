# Spec — Raw-Search Retrieval Evaluation (P3-EVAL)

**Date:** 2026-06-07 · **Branch:** `raw-search/foundation` · **Size:** XL · **Mode:** v2.2 (no /amaw — additive test infra, non-destructive, test-account only)

## Problem

Raw-search shipped (Phase 1–3) with **zero retrieval-quality measurement**. Unit tests are mock-only; the prior "live-smoke PASSED" proved *not-500 + returns something*, never *results are correct / good enough*. For a feature whose entire value is **retrieval over raw chapter text**, that is the wrong kind of green. We need standard IR metrics on a real corpus, across all three modes, with an exact-baseline oracle so a number can't lie.

User asks being answered: e2e fidelity, retrieval metrics (hit@k / recall@k / MRR@k / NDCG@k), brute-force baseline, control-K.

## Data reality (verified on the running stack, 2026-06-07)

- **Lexical:** rich. 47,841 `chapter_blocks` already ingested (incl. a 171-ch zh book). Lexical leg has real data for free.
- **Semantic:** empty. Only 20 synthetic `benchmark_entity` Passages in Neo4j; **zero** `:Passage{source_type:'chapter'}`. No pgvector columns in knowledge Postgres. Existing books were never embedded.
- **Embeddings are FREE here:** `text-embedding-bge-m3` is served **locally** by LM Studio (`http://host.docker.internal:1234`, verified up). The test account `claude-test` (`019d5e3c-…`) **owns** the registered `bge-m3 (local)` user_model `019e7f71-…` (dim 1024). The embed call is user-scoped → owner == book owner == query user, no cross-tenant friction.
- **Embed ≠ LLM extraction.** Semantic raw-search needs only chapter chunks *embedded* (cheap, local), NOT the expensive entity-extraction LLM pipeline. `ingest_chapter_passages()` ([passage_ingester.py](../../services/knowledge-service/app/extraction/passage_ingester.py)) is an existing, directly-callable, embedding-only path; with `revision_id=None` it fetches **draft** text (`get_chapter_text`) — no publish/pin plumbing needed.

Conclusion: importing a small fresh corpus (40 ch of 万古神帝, on disk at `D:\Works\source\web-crawling\output\万古神帝-51254\chapters`) and embedding it locally is **cheap** and unlocks the *full* hybrid eval.

## Goal

A reproducible CLI eval harness that, over a 40-chapter real zh corpus, reports **hit@k / recall@k / MRR@k / NDCG@k** for **each mode (lexical / semantic / hybrid)** at controllable **K**, plus a **brute-force oracle** per leg — so we can prove (a) lexical endpoint loses no true substring match, (b) the Neo4j ANN index loses little vs exact kNN, and (c) **hybrid actually beats each single leg**.

## Scope

### IN (E0–E4)
- **E0 — Corpus ingest.** Import 40 ch → book + 40 chapters (lexical `chapter_blocks`) + knowledge_project (bge-m3, dim 1024) + `ingest_chapter_passages` per chapter → `:Passage{source_type:'chapter'}` (semantic). Idempotent.
- **E1 — Golden set.** ~15–20 zh queries authored by mining the 40 chapters for distinctive terms (names / places / techniques / events), with **expected chapterId(s)** resolved via the exact-substring oracle and **graded relevance (0–3)** for NDCG. Bands: `exact`, `paraphrase`, `negative`.
- **E2 — Metrics.** Extend [metrics.py](../../services/knowledge-service/app/benchmark/metrics.py): add `hit_at_k` and `ndcg_at_k` (graded) beside existing `recall_at_k`, `reciprocal_rank`. Pure, unit-tested.
- **E3 — Runner.** Login as `claude-test` → for each query × mode × K, GET the live orchestrator `…/v1/knowledge/books/{book_id}/search?mode=&limit=` → extract ranked `chapterId`s → compute per-query + aggregate metrics → print a **per-mode comparison table** + JSON. Degradation surfaced (e.g. semantic `not_indexed`).
- **E4 — Brute-force baselines.**
  - *Lexical oracle:* exact `text_content ILIKE '%term%'` scan over the book's `chapter_blocks` = perfect-recall set → recall of the lexical endpoint.
  - *Semantic flat-kNN:* fetch ALL project chapter passages with vectors, exact cosine vs query embedding, rank → compare to the endpoint's (Neo4j ANN) top-k → **ANN recall@k**.

### OUT (deferred — tracked rows; revisit when E3 numbers justify)
- **E5** RRF_K / per-chapter-cap / K tuning sweep. **E6** FE K-selector widget.
- Multi-book / larger corpora. CI threshold-gate wiring. Persisting eval runs to `project_embedding_benchmark_runs`.

## Design

### Endpoint under test
All three modes go through the **knowledge orchestrator** `GET /v1/knowledge/books/{book_id}/search?query=&mode=&limit=` ([raw_search.py](../../services/knowledge-service/app/routers/public/raw_search.py)). It requires a JWT (`get_current_user`) and a project for the book (ownership gate). `mode=lexical` skips semantic; `mode=semantic` skips lexical; `mode=hybrid` runs both + RRF. One endpoint covers the matrix.

### Execution-context constraint (verified)
The knowledge **Dockerfile copies `app/` + `tests/` only** — `eval/` does NOT ship in the image. Code that needs app modules (embedding client, neo4j upsert, `find_passages_by_vector`) at the stack must therefore live under **`app/benchmark/`** (already shipped — `metrics.py`, `golden_set.yaml`, `core.py` are there) and run via `docker exec infra-knowledge-service-1 python -m app.benchmark.<mod>`. Pure host scripts (HTTP + psql) live in `scripts/`. The host runner imports the pure `app.benchmark.metrics` (math-only, no `app.config`) via `PYTHONPATH=services/knowledge-service`. **Rebuild the knowledge image once** before live-smoke so new `app/benchmark/*` modules land in the running container.

### Components & files
| # | File | Ctx | Role |
|---|------|-----|------|
| E0a | `scripts/seed_rawsearch_eval.py` | host | login → create book + 40 chapters (book-service HTTP, draft body) → find-or-create knowledge_project (psql) w/ bge-m3 + dim 1024 → `docker exec` the ingest step → verify counts |
| E0b | `services/knowledge-service/app/benchmark/ingest_rawsearch_corpus.py` | container | for each chapter: `ingest_chapter_passages(revision_id=None)` → embed via lm_studio → upsert `:Passage`. Mirrors `run_benchmark.py` bootstrap (imports inside fn; reads `KNOWLEDGE_DB_URL` etc. from container env) |
| E1 | `services/knowledge-service/app/benchmark/rawsearch_golden.yaml` | data | queries + expected chapterIds + graded rels + bands |
| E2 | `services/knowledge-service/app/benchmark/metrics.py` (edit) | pure | `+ hit_at_k`, `+ ndcg_at_k` |
| E3 | `scripts/run_rawsearch_eval.py` | host | runner: login → 3 modes × K → import `app.benchmark.metrics` → per-mode table + JSON; lexical oracle (psql); shells E4b for ANN-recall |
| E4b | `services/knowledge-service/app/benchmark/flat_knn_rawsearch.py` | container | exact cosine over all project chapter passages (`find_passages_by_vector(include_vectors=True)`) → flat top-k for ANN-recall vs endpoint |
| T | `services/knowledge-service/tests/unit/test_rawsearch_metrics.py` | pure | unit tests for E2 |

### Golden-set authoring method (anti-cheat)
Queries are **derived from the corpus**, not invented: for each candidate term, run the exact-substring oracle to (a) confirm it occurs and (b) record the chapter(s) that contain it. The chapter whose *title/topic* is the term gets graded rel 3; chapters that merely mention it get 1–2; absent → negative-control. This guarantees ground truth is real and removes author bias on "expected".

### Metric definitions (additions)
- `hit_at_k(expected, results, k)` → `1.0` if any expected id ∈ top-k else `0.0` (a.k.a. success@k). Empty expected → `1.0` (negative-control handled by score/score-absence, not hit).
- `ndcg_at_k(graded, results, k)` → `DCG@k / IDCG@k`, `DCG = Σ rel_i / log2(i+1)` over ranked results (gain from `graded[result_id]`, default 0), `IDCG` from the ideal descending-rel ordering. `0.0` when IDCG == 0.

### Multi-tenant / safety
- All writes are under `claude-test`, a fresh book (additive). No deletion of existing data. `ingest_chapter_passages` is idempotent (deletes only *this* chapter's stale passages before re-upsert). Re-running the seed is safe.

## Acceptance criteria
1. Seed creates the book + 40 chapters (lexical blocks > 0) + `:Passage{source_type:'chapter'}` count > 0 for the project. Idempotent on re-run.
2. Golden set ≥ 15 queries, every non-negative `expected` verified present by the oracle; ≥ 2 negative controls.
3. `hit_at_k` + `ndcg_at_k` implemented, pure, unit-tested (incl. empty-expected, IDCG==0, k>len edge cases).
4. Runner emits a per-mode table (lexical/semantic/hybrid) of hit@k, recall@k, MRR, NDCG@k at ≥1 K, against the **live** stack.
5. Lexical-oracle recall reported; semantic flat-kNN ANN-recall reported.
6. **Live-smoke evidence** (≥2 services: book + knowledge): a real run of the runner against the stack, numbers captured.

## Risks
- **R1 — LM Studio must stay up during ingest.** Mitigation: verified up; ingest is best-effort per-chunk; seed re-runnable.
- **R2 — draft `get_chapter_text` returns the body we POSTed.** Verify at BUILD with one chapter before bulk.
- **R3 — bge-m3 dim 1024 ∈ `SUPPORTED_PASSAGE_DIMS`.** Benchmark already runs 1024; verify import doesn't early-return on dim guard.
- **R4 — orchestrator JWT acceptance** for knowledge-service direct call. Mitigation: auth-service JWT is shared; if direct call rejects, route via gateway.
- **R5 — semantic numbers low because hybrid value needs tuning.** That's the *point* — measure first; tuning is deferred E5.
