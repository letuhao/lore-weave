# The `300/200` search-effort defaults, re-measured above 181 rows — 2026-08-11

> **QC-3b.** T24 set `diskann.query_search_list_size = 300` / `diskann.query_rescore = 200` as the
> shipped defaults on the strength of **recall@10 = 1.000 on the real passage corpus**, and flagged
> its own limit: *"⚠️ Measured at 181 rows; QC-3 must re-measure at scale."* This is that
> re-measure. **The defaults do not hold at scale**, and the reason they cannot simply be turned up
> is more interesting than the miss.

## Method

`app/benchmark/vector_backend_bench.py`, synthetic **clustered** corpus (queries drawn from the
corpus distribution, not uniform random — T24 established that uniform queries in 1024 dims are
near-orthogonal to everything and measure nothing), 1024-dim, k=10, 25 queries, on the throwaway
`loreweave_vectors_test`.

**The harness's positive control passed on every run in this file**: the `exact` cell scores
recall@10 = 1.0000 against numpy ground truth computed *outside* the database. Without that, every
number below would be void — a backend graded by another query on the same server shares whatever
that server gets wrong.

## Result 1 — the knobs work, and they only work on diskann

| rows | cell | @100/50 (server default) | @300/200 (shipped) | Δ |
|---|---|---|---|---|
| 5 000 | **diskann** | 0.3920 | **0.6560** | **+0.264** |
| 5 000 | hnsw | 0.4080 | 0.4320 | +0.024 |
| 5 000 | halfvec_hnsw | 0.4080 | 0.4120 | +0.004 |
| 20 000 | **diskann** | 0.2440 | **0.5160** | **+0.272** |
| 20 000 | hnsw | 0.1360 | 0.1680 | +0.032 |
| 20 000 | halfvec_hnsw | 0.1440 | 0.1480 | +0.004 |

T24's decision to set both knobs is **confirmed** — it is worth ~+0.27 recall at both sizes. The
hnsw columns move by ~0.03 under their own knob, which is what tells you the diskann movement is a
real effect and not run-to-run noise in the harness.

## Result 2 — but the number T24 measured does not survive the corpus growing

**recall@10 = 1.000 at 181 rows. recall@10 = 0.516 at 20 000 rows. Same settings.**

At the size a real book reaches, the shipped defaults return **about half of the true top-10**, from
a search that reports success. Nothing errors; the answer is simply missing content.

## Result 3 — it is effort-bound, not a broken corpus, and the effort runs out

The first suspicion was that the synthetic corpus had no findable neighbourhood structure (all ANN
cells collapsing together, `recall_min = 0.00`, exactly T24's documented trap). Raising the effort
settles it — recall climbs monotonically, so the neighbours **are** findable:

| diskann, 20 000 rows | `search_list`/`rescore` | recall@10 | worst query | p50 |
|---|---|---|---|---|
| server default | 100 / 50 | 0.2440 | 0.10 | 5.16 ms |
| **shipped** | **300 / 200** | **0.5160** | — | 9.01 ms |
| | 1000 / 500 | 0.7120 | 0.40 | 14.44 ms |
| ceiling | **4000 / 1000** | **0.8240** | 0.50 | 32.97 ms |
| — | *exact seq-scan* | **1.0000** | 1.00 | 40.87 ms |

Two things fall out of the last two rows, and they are the finding:

1. **`diskann.query_rescore` has a hard ceiling of 1000.** Asking for 2000 is not slow, it is
   refused: `InvalidParameterValueError: 2000 is outside the valid range for parameter
   "diskann.query_rescore" (0 .. 1000)`. So "just raise it until recall is acceptable" is not a
   strategy that continues to exist — at 20 000 rows the knob is already at its limit and still
   only reaches **0.824**.
2. **At that point the index has almost stopped being worth having.** 32.97 ms for 0.824 recall
   against **40.87 ms for a perfect answer** from a sequential scan. The ANN index buys ~20 %
   latency for ~18 % of the correct results missing.

## What this does and does not license

**Does:** the direction of T24's change is right and should stay. 300/200 beats the server defaults
everywhere measured.

**Does not:** it does not license quoting "recall 1.000" as the operating recall of the shipping
configuration. That number belongs to a 181-row corpus and does not survive growth.

⚠️ **The absolute numbers here are from SYNTHETIC data and are a floor, not a verdict** — the same
caveat T24 attached to its own synthetic cells. Real passage embeddings almost certainly have lower
intrinsic dimensionality than the generated corpus, and would score better at the same effort. What
transfers is not the value but the **shape**: at fixed search effort, ANN recall falls as the corpus
grows, and the compensating knob has a ceiling.

### 🔻 DEFERRAL `D-QC3B-NO-REAL-CORPUS-AT-SCALE`

| | |
|---|---|
| **Blocker** | The question QC-3 actually asks — *what is recall on the real corpus at scale* — **cannot be measured today**, because the real passage corpus is **181 rows**. There is no large real corpus to point the harness at, so the only available answer at 20 000 rows is synthetic, and synthetic is explicitly a floor. |
| **Evidence** | `--source neo4j` reads the live corpus; T24 recorded its size as 181 rows and this run found nothing larger. Every number above 181 rows in this file is `--source synthetic`. |
| **To unblock** | A real (or realistically-embedded) corpus in the 10 k–100 k passage range — most plausibly the dogfood book after QC-5's end-to-end re-run, or a corpus built by embedding real text rather than `random()`. |
| **Mechanism** | `app/benchmark/vector_backend_bench.py --source neo4j` already exists and needs no new code; it needs data. The harness refuses to flatter itself — its `exact` control must read 1.0 or the run is void — so re-running it when the corpus grows is a one-command check, not a re-derivation. |
| **Retry when** | The passage corpus exceeds ~5 000 rows on any real book. **Before the vector cutover ships** — this deferral is an input to that decision, not a follow-up to it. |

## Recommendation, stated as a question for the checkpoint

The honest summary is that **the search-effort defaults are a corpus-size-dependent setting being
shipped as a constant.** Options, in increasing order of work:

1. Leave 300/200 and accept degrading recall as books grow — the current, undocumented behaviour.
2. Scale effort with corpus size (a function, not a constant), and pay the latency.
3. Reconsider whether an ANN index is the right structure at this dimensionality until the corpus
   is much larger than 20 000 — at 20 000 the exact scan is 41 ms and perfect.

This belongs to the QC-3 POST-REVIEW checkpoint rather than to a unilateral choice here.

## Reproducing

```
cd services/knowledge-service
python -m app.benchmark.vector_backend_bench \
  --dsn postgresql://postgres:…@localhost:7995/loreweave_vectors_test \
  --source synthetic --rows 5000,20000 --dim 1024 --k 10 --queries 25 \
  --diskann-search-list 300 --diskann-rescore 200
```

Vary `--diskann-search-list` / `--diskann-rescore` for the effort curve. `--source neo4j` reads the
real corpus (181 rows today). The harness refuses a DSN whose database name is not marked
throwaway, before any DDL.
