# Vector backend recall and latency — 2026-08-10

> **Gate:** plan [T24](../plans/2026-08-09-knowledge-architecture-refactor.md) — *"Neo4j HNSW vs
> pgvector vs StreamingDiskANN vs halfvec, same corpus, recall@k + latency. **Bite:** halfvec must
> measurably lose recall somewhere; if it never does, the harness is not measuring."*

**Two results change what ships.**

1. **StreamingDiskANN's server defaults return `recall@10 = 0.715` on the real passage corpus** —
   three of ten neighbours simply missing, from a search that reports success. At
   `search_list=300, rescore=200` the same corpus returns **1.000**, and it is not slower.
   T23 wired `query_rescore` and left the value to the server, calling it an optimisation. It is
   not: it is the difference between correct results and quietly wrong ones. `PgVectorStore` now
   sets both knobs itself.
2. **The halfvec bite fires**, in the one cell built to isolate it: fp16 costs **0.5 % mean recall
   (worst query 0.90)** and saves **49 % of storage**. It is a real trade with a real price, not a
   free win and not a workaround.

Harness: `services/knowledge-service/app/benchmark/vector_backend_bench.py`.

---

## The comparison the plan asked for cannot be built

Before designing anything, the opclass catalogue was read:

```
diskann : vector_cosine_ops, vector_ip_ops, vector_l2_ops        ← `vector` ONLY
hnsw    : vector_*, halfvec_*, sparsevec_*, bit_*
ivfflat : vector_*, halfvec_*, bit_hamming_ops
```

**pgvectorscale 0.9.0 has no `halfvec` operator class for diskann.** "StreamingDiskANN vs halfvec"
is not a comparison anyone can run. Run naively — halfvec on HNSW against `vector` on diskann — the
resulting number would have blamed fp16 for a difference between two index *algorithms*.

So the cells isolate one variable each:

| cell | storage | index | isolates |
|---|---|---|---|
| `exact` | `vector` | seq scan | ground truth from the DB · **the positive control** |
| `halfvec_exact` | `halfvec` | seq scan | **storage precision alone** — no index randomness |
| `diskann` | `vector` | diskann | the shipping choice (T22/T23) |
| `hnsw` | `vector` | hnsw | index algorithm, precision held fixed |
| `halfvec_hnsw` | `halfvec` | hnsw | precision, index held fixed |

`halfvec_exact` is the addition that made the bite answerable. `halfvec_hnsw` vs `hnsw` still mixes
precision with the index's own randomness — two HNSW graphs over the same points are not the same
graph — and on that pair halfvec came out *ahead* as often as behind, i.e. noise.

Recall is scored against exact cosine in **numpy, outside the database**. A backend graded by
another query on the same server shares every bug that server has; a wrong distance operator would
score 1.000 against itself. The `exact` cell earns its keep as the control: its recall must be
1.000, and the harness exits non-zero if it is not.

## The first numbers were the harness, not the backends

Every backend initially scored **0.2–0.7** — a devastating-looking verdict on pgvector. It was
wrong, and the cause is worth recording because it would have been easy to publish.

**The queries were uniform random.** In 1024 dimensions a random query is near-orthogonal to the
entire corpus, so its true top-10 is ten near-ties separated by float noise. No index can reproduce
an ordering that is itself arbitrary. Clustering the *corpus* did not help, because the *queries*
were still drawn from the wrong distribution.

A real query is a sentence that lands near the passages it is about. Queries are now drawn as
perturbed corpus points, which is what makes recall a question with an answer.

The random-vector corpus is kept (`--corpus random`) and labelled for what it is: a floor, useful
for showing how a backend degrades into noise, worthless as a verdict.

## R-1 — the real corpus

181 chapter passages, 1024-dim, project `019f1783…`, read-only from the dev graph. k=10, 20 queries.

| cell | recall@10 | worst query | p50 | size |
|---|---|---|---|---|
| `exact` | **1.0000** | 1.0000 | 5.93 ms | 1080 kB |
| `halfvec_exact` | **1.0000** | 1.0000 | 4.50 ms | 584 kB |
| **`diskann` (server defaults)** | **0.7150** | **0.3000** | 5.13 ms | 1200 kB |
| `hnsw` | **1.0000** | 1.0000 | 3.78 ms | 2536 kB |
| `halfvec_hnsw` | **1.0000** | 1.0000 | 4.08 ms | 1080 kB |

diskann is the only cell that loses anything, and on its worst query it returns **three of ten**
correct neighbours.

## R-2 — it is the defaults, not the algorithm

| `search_list` / `rescore` | recall@10 | worst query | p50 |
|---|---|---|---|
| 100 / 50 *(server default)* | 0.7150 | 0.3000 | 5.97 ms |
| **300 / 200** | **1.0000** | **1.0000** | **4.66 ms** |
| 1000 / 500 | 1.0000 | 1.0000 | 5.36 ms |

Full recovery, with **no latency cost** at this scale — the 5.97 → 4.66 ms difference is noise, but
it is certainly not a penalty. So `PgVectorStore.DEFAULT_SEARCH_LIST_SIZE = 300` and
`DEFAULT_QUERY_RESCORE = 200`, set by the adapter rather than left to the server.

⚠️ **Measured at 181 rows.** Whether 300/200 holds at 63 M passage vectors is exactly what QC-3 must
re-measure; these are defaults chosen from evidence, not constants proven at scale.

## R-3 — the halfvec bite, in the cell that can see it

Clustered synthetic, 10 000 rows × 1024 dim, k=10:

| cell | recall@10 | worst query | size |
|---|---|---|---|
| `exact` | 1.0000 | 1.0000 | 54 816 kB |
| **`halfvec_exact`** | **0.9950** | **0.9000** | **27 928 kB** |

Neither cell has an index. The only difference is that one side's vectors were rounded to 16 bits,
so **the loss is fp16 and nothing else**: 0.5 % mean, and on the worst query one of ten neighbours
is wrong — for **49 % less storage**.

On the 181-row real corpus halfvec loses nothing (1.0000). That is not a contradiction, it locates
the cost: fp16 only scrambles orderings whose margins are smaller than its rounding error, so
halfvec's price is paid in the near-tie regime and nowhere else.

**The bite fires.** Had it not, the honest conclusion would have been that the harness could not see
a difference it was built to find.

## R-4 — what the synthetic corpora cannot settle

On the clustered 10 000-row corpus, tuned, every ANN cell sits between 0.575 and 0.650. That corpus
puts ~156 near-identical points in each cluster, so recall@10 is unstable by construction. It is a
stress shape, not a prediction.

**The ANN question is settled by the real corpus, and the real corpus here is 181 rows.** That is
the honest limit of this measurement. QC-3 owns the scaled re-run.

## A defect this found in T23's own test helper

`_seed_two_tenants` built its vectors with an **uncorrelated** subquery and a comment asserting that
`random()`'s volatility made it per-row. It does not: an uncorrelated subquery is hoisted into an
InitPlan and evaluated once, however volatile its body. Measured: `count(*) = 3000`,
`count(DISTINCT embedding) = 1`.

Every distance was therefore zero and every ranking arbitrary. T23's planner assertions survive —
they are about plan shape, which does not depend on the data — but any recall test built on that
helper would have measured nothing while looking healthy. Fixed by correlating on `g`, and the
helper now **asserts its own output is distinct**, because that failure is invisible downstream.

---

## Verdict

**pgvector is not the risk; its defaults were.** With the adapter's settings the real corpus returns
recall 1.000 on both index families, and pgvector's HNSW does so at the server's own defaults —
which is worth remembering as the fallback for dims ≤ 2000 if diskann ever disappoints at scale.

`halfvec` stays **rejected for the default path** and documented as available: 49 % storage for a
measured 0.5 % recall cost is a trade a large deployment may want, and T21 already established it is
not needed for dimension reach. Nothing in Phase 3 depends on it.

**Reproduce:**

```bash
docker run -d --name lw-vec-test -e POSTGRES_PASSWORD=… \
  -e POSTGRES_DB=loreweave_vectors_test -p 7995:5432 loreweave/postgres-knowledge:18

# real corpus (inside the service container — it needs the graph)
docker exec infra-knowledge-service-1 python -m app.benchmark.vector_backend_bench \
  --dsn postgresql://postgres:…@host.docker.internal:7995/loreweave_vectors_test \
  --source neo4j --project-id <uuid> --user-id <uuid> --dim 1024 --k 10 --queries 20

# the halfvec bite
python -m app.benchmark.vector_backend_bench --dsn … \
  --source synthetic --corpus clustered --rows 10000 --dim 1024
```
