# QC-3 — recall + latency on the REAL corpus, both backends

**Date:** 2026-08-14 · **Row:** QC-3 (*"re-run against the real corpus on both backends and
publish **recall@10 and latency ratios**, not absolutes"*)

## How it was run

Corpus vectors pulled **READ-ONLY** from the dev graph (`bolt://localhost:7688`,
`vector_backend_bench._from_neo4j`) — real 1024-dim passage embeddings from the largest
project. Indexes built in a **throwaway** Postgres (`vecbench_scratch`, a disposable
`timescaledb-ha:pg17` container with `vector` + `vectorscale`); the harness's own
`_guard_throwaway` refuses any database whose name is not disposable, and it was the thing that
forced the rename.

```
python -m app.benchmark.vector_backend_bench \
  --dsn postgresql://…/vecbench_scratch --source neo4j \
  --project-id 019fefde-… --user-id 019d5e3c-… \
  --rows 556 --dim 1024 --k 10 --queries 25
```

`--rows 556` requested; **377** returned — that is every 1024-dim passage vector the filter
found, and the report says so rather than padding.

## Result — 377 real passages, k=10, 25 queries, `control_ok: true`

| backend | recall@10 | worst query | p50 | ratio vs exact | p95 | build | table |
|---|---|---|---|---|---|---|---|
| `exact` | 1.000 | 1.000 | 3.74 ms | 1.00× | 4.64 ms | 0.00 s | 2.2 MB |
| `halfvec_exact` | 1.000 | 1.000 | 3.34 ms | 0.89× | 3.92 ms | 0.00 s | 1.2 MB |
| **`diskann`** | **0.500** | **0.000** | 2.94 ms | 0.79× | 3.49 ms | 0.15 s | 2.4 MB |
| `hnsw` | 1.000 | 1.000 | 3.68 ms | 0.98× | 4.54 ms | 0.06 s | 5.3 MB |
| **`halfvec_hnsw`** | **1.000** | 1.000 | 3.06 ms | **0.82×** | 3.55 ms | 0.06 s | **2.2 MB** |

## 🔴 The finding: diskann loses half the top-10 on real data, and one query returns nothing right

`recall_at_k 0.500` with `recall_min **0.000**` — at least one of the 25 queries returned **none**
of its true top-10. Not a tail: the *median* query loses half its results.

**`control_ok: true` is what makes this a finding rather than a harness artifact.** The `exact`
arm scores 1.000 against its own ground truth on the same corpus and the same queries, so the
measurement apparatus is sound and the 0.500 belongs to the index.

This is consistent in direction with the 2026-08-11 note (*diskann 0.836 vs HNSW 1.0 @ 556
passages*) and **worse at this size** — which is the expected shape: an approximate graph index
has less to work with as the corpus shrinks, and 377 vectors is far below where diskann's
recall/─speed trade starts paying.

## 🎯 What the ratios say for the cutover

**Latency is not the deciding variable.** Every backend sits between 0.79× and 1.00× of exact at
this corpus size — a spread of under 1 ms — so nothing here is bought with speed.

**`halfvec_hnsw` dominates on the evidence available:** recall 1.000, **0.82×** exact's p50, and
**2.2 MB against hnsw's 5.3 MB** — the same perfect recall at 41 % of the index size.

⚠️ **This does NOT settle the production choice**, and saying so is the point of publishing
ratios: 377 vectors is three orders of magnitude below the scale QC-3a measured index *builds*
at (`docs/measurements/2026-08-10-diskann-rebuild-scale.md`), and diskann exists for corpora
where exact scan stops being free. What it does settle is that **diskann must not serve this
corpus** — a reader would get half the results, and one reader in twenty-five would get none of
the right ones.

## Owed by the ⏸ checkpoint

* the **restore drill** — already recorded, `docs/measurements/2026-08-10-vector-restore-drill.md`
* `/review-impl` — done, QC-3c (no HIGH, 3 MED, one fixed)
* **this recall comparison** — done, above
* the sign-off itself: **present evidence and WAIT**
