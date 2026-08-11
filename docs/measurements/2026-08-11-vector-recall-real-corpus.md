# QC-3b — recall on the REAL corpus, first measurement — 2026-08-11

> **Result: on real data, `diskann` — the shipping choice — is worse than `hnsw` on BOTH
> axes.** 0.836 recall@10 against 1.000, and slower (p50 3.91 ms vs 2.69 ms). The `exact`
> positive control reads 1.0000, so the harness is sound and the numbers stand.

Every prior vector number in this repo was `--source synthetic`. `D-QC3B-NO-REAL-CORPUS-AT-SCALE`
recorded that the real corpus was too small to measure. It is still small — but it is now large
enough to measure *something*, and something is what this is.

## The run

```
python -m app.benchmark.vector_backend_bench \
  --dsn postgresql://…@localhost:7995/loreweave_vectors_test \
  --source neo4j --project-id 019fefde-… --user-id 019d5e3c-… \
  --dim 1024 --k 10 --queries 25 --diskann-search-list 300 --diskann-rescore 200
```

Neo4j is read-only here; the pgvector side builds and drops its tables in a throwaway database
the harness refuses to run without. Corpus: the **556 real passages** ingested today from the
100-chapter book (see `2026-08-11-…` corpus note), each with a real `embedding_1024`.

## The numbers

| backend | recall@10 | worst query | p50 | p95 | note |
|---|---:|---:|---:|---:|---|
| `exact` | **1.0000** | 1.000 | 2.75 ms | 3.13 ms | positive control — must be 1.0 or the run is void |
| `halfvec_exact` | 1.0000 | 1.000 | 2.47 ms | 2.84 ms | fp16 storage, exact search |
| **`diskann`** | **0.8360** | **0.500** | **3.91 ms** | 4.55 ms | **the shipping choice** |
| `hnsw` | 1.0000 | 1.000 | 2.69 ms | 3.11 ms | same storage, different index |
| `halfvec_hnsw` | 1.0000 | 1.000 | 3.70 ms | 4.81 ms | fp16 + hnsw, ~41 % of the table bytes |

`control_ok: true`. Ground truth is exact cosine computed in **numpy, outside the database**,
so a backend cannot be graded by another query on the same server that shares its bugs.

## Reading it honestly

**What it does show.** At this corpus size diskann has **no advantage and two costs**: it
returns 16 % fewer of the true top-10, and it is the slowest non-fp16 cell. Its worst query
recalled **half** the correct results. Both alternatives with the same storage precision score
a perfect 1.000. This is a real input to the cutover decision, which is what the deferral said
this measurement was for.

**What it does NOT show.** 556 rows is small, and diskann is built for corpora where HNSW's
index memory becomes the binding constraint — a regime this run does not reach. The crossover
where diskann starts to pay for itself is **not measured here and is not implied**. What the
synthetic runs add is the shape: recall stayed effort-bound at 20 000 rows too
(`2026-08-11-vector-search-effort-at-scale.md`, 0.516 → 0.824 as effort rose, ceiling short of
exact), so "more rows will fix the recall" is not supported by the data either.

**The one thing it settles.** The claim that could not previously be checked — *does diskann's
recall hold on real vectors?* — now has an answer at one real size, and the answer is no.

## What QC-3 still owes

This closes half of *"the recall comparison on the real corpus"*: it is real, and it is a
comparison. It is **not at scale** — the corpus is 1041 passages total, against a 5 000
threshold. `/review-impl` remains unsigned, and `D-T25B-SOAK` independently blocks the cutover,
so nothing here authorises shipping a change.

## Reproducing

Re-run the command above. `control_ok: false` voids the page.
