# diskann rebuild time above the parallel-build threshold — 2026-08-10

> **QC-3a. Complete.** Eight standalone points across the `diskann.min_vectors_for_parallel_build`
> threshold at two memory settings, plus a restore-drill control. Supersedes the PARTIAL version
> of this file, whose single point led to a conclusion the fuller data does not support — see
> *"What the first pass got wrong"* at the bottom, kept deliberately.

## The question QC-3 was given

The T25 restore drill established that **the index rebuild IS the recovery time** — 34.3 s of a
35.3 s restore at 20 000 rows — and fitted `O(n^1.6)` from two points, 5 000 and 20 000. Both sit
**below** `diskann.min_vectors_for_parallel_build = 65536`. Extrapolating a single-threaded curve
across the threshold that switches parallelism on produces a number that reads like an RTO and is
not one. QC-3 was told to measure across it.

**The threshold turned out not to be the interesting variable.** Something else binds four times
earlier, and it is a setting, not a machine.

## Environment, recorded because it decides the answer

`loreweave/postgres-knowledge:18`, vectorscale 0.9.0, 1024-dim (the drill's dim), throwaway DBs.

| setting | value |
|---|---|
| `max_parallel_maintenance_workers` | **2** |
| `max_worker_processes` | 8 |
| `maintenance_work_mem` | **64 MB** (image default) |
| `shared_buffers` | 128 MB |
| host CPUs visible to the container | 32 |

**The image ships the Postgres defaults.** 32 CPUs are visible and at most 2 maintenance workers
may be used, so "above the threshold" does not mean "parallel" in any useful sense.

## Result — `scripts/diskann-rebuild-scale.sh`, standalone `CREATE INDEX`

| rows | parallel-eligible | **64 MB** | **1 GB** | speed-up | builder cache full at |
|---|---|---|---|---|---|
| 20 000 | no | 63.5 s | 65.1 s | **1.00×** | 14 717 / not reached |
| 40 000 | no | 207.0 s | 127.2 s | 1.63× | 14 717 / not reached |
| 70 000 | **yes** | 502.9 s | 252.9 s | **1.99×** | 14 717 / not reached |
| 100 000 | **yes** | 893.3 s | 497.6 s | 1.80× | 14 717 / not reached |

Index size is identical at both settings (11 / 22 / 39 / 56 MB) — this buys time, not space.

## What the numbers say

### 1. The lever is `maintenance_work_mem`, and the threshold is a red herring

At the default, **every** build logs

```
WARNING:  Builder neighbor cache is full after processing 14717 vectors;
          consider increasing maintenance_work_mem
```

— at 14 717 vectors, *identically at every corpus size*, because it is a function of memory alone.
At 1 GB the warning never appears. Crossing 65 536 changes nothing you can see in the table above;
crossing 14 717 changes everything.

**There is a second cache, and it only shows up at the largest size.** At 100 000 rows the builder
also logs

```
WARNING:  Quantized vector cache is full after processing 83887 vectors;
          consider increasing maintenance_work_mem
```

so the 100 000-row build at 64 MB is starved *twice*. At 1 GB neither warning appears. This was
nearly missed: the harness originally reported only the **first** matching warning per build, so
the 100 000-row row named one limit while the build had hit two. The extractor now reports all of
them (`Builder neighbor:14717,Quantized vector:83887`) — an instrument that stops reading at the
first finding under-reports precisely where the effect is largest.

### 2. The benefit is not a constant factor — it tracks how much of the build runs degraded

The cache fills at a fixed vector count, so the **fraction** of the build that runs in the degraded
regime grows with the corpus, and the speed-up grows with it:

| rows | vectors built after the cache fills | share | speed-up at 1 GB |
|---|---|---|---|
| 20 000 | 5 283 | 26 % | 1.00× |
| 40 000 | 25 283 | 63 % | 1.63× |
| 70 000 | 55 283 | 79 % | 1.99× |
| 100 000 | 85 283 | 85 % | 1.80× |

**This is why a 20 000-row measurement could not have found it.** At 20 000 the two settings are
within noise of each other (63.5 s vs 65.1 s), so the drill's own anchor point is nearly blind to
the effect it is most affected by at scale.

### 3. Raising the memory changes the exponent, not just the constant

Fitting each column against its **own** 20 000-row anchor:

| `maintenance_work_mem` | fitted exponent, 20 k → 100 k |
|---|---|
| 64 MB | **1.64** — matches the drill's fitted 1.6 |
| 1 GB | **1.26** |

So the drill's `O(n^1.6)` is a good description **of a memory-starved build**. Fix the memory and
the curve itself gets flatter, which is the difference between a recovery time that grows painfully
with the corpus and one that does not.

### 4. Run-to-run variance is ~18 %, and is reported rather than averaged away

The 40 000-row point at 64 MB measured **175.0 s** in a first partial run and **207.0 s** here;
the drill's 20 000-row rebuild measured **34.3 s** originally and **40.4 s** on re-run today. Every
comparison in this file is between numbers that survive that spread by a wide margin — the 1.99×
at 70 000 is not an 18 % artefact. Single points close together are not treated as different.

## The two harnesses disagree at 20 000 and agree at 100 000

| index rebuild, 64 MB | 20 000 rows | 100 000 rows |
|---|---|---|
| `vector-backup-drill.sh` | 40.4 s | **817.5 s** |
| `diskann-rebuild-scale.sh` | 63.5 s | **893.3 s** |
| ratio | 1.57× | **1.09×** |

The gap at 20 000 looked like a reason to distrust one of them. It is not: at 100 000 the two land
**9 % apart**, inside the ~18 % run-to-run spread. Whatever the small-corpus difference is — most
likely fixed per-build overhead the drill amortises differently — **it vanishes at the sizes an RTO
is actually about**, so the RTO does not depend on which harness you believe. Both are reported.

## The RTO, measured on the recovery path

`scripts/vector-backup-drill.sh --rows 100000 --dim 1024`, **above** the 65 536 parallel threshold —
the measurement T25 said did not exist and without which "there is no defensible RTO":

| 100 000 rows × 1024-dim | 64 MB (image default) | **1 GB** | change |
|---|---|---|---|
| backup | 84.3 s | 69.6 s | — |
| **full restore — this is the RTO** | **1051.1 s** (17.5 min) | **437.6 s** (7.3 min) | **2.40× faster, −10.2 min** |
| index rebuild, timed alone | 817.5 s | 449.6 s | 1.82× |
| integrity checks | passed=6 failed=0 | passed=6 failed=0 | unchanged |

**One setting takes recovery at 100 000 vectors from 17.5 minutes to 7.3.** The 1.82× on the
isolated rebuild matches the standalone harness's 1.80× at the same size — two harnesses that
disagree on absolutes agreeing on the effect.

The 1 GB restore was verified as a restore, not just as a fast number: all six of the drill's
checks passed in both passes, including *every vector byte-identical* and *the exact
nearest-neighbour answer unchanged*.

⚠️ **The drill's own summary line is misleading and should be fixed** (noted here, not silently
worked around). It prints `restore: Xs total (index rebuild alone: Ys)`, which reads as though
Y ⊆ X. It is not: `X` is `pg_restore`'s wall time *including the index build it does itself*, while
`Y` is a **second, later** rebuild after an explicit `DROP INDEX`. In pass A the wording passed
unnoticed because 817.5 < 1051.1; in pass B it produces `restore: 437.6s total (index rebuild
alone: 449.6s)` — a part larger than its whole, which is the only reason anyone would look.

## Recommendation

**Raise `maintenance_work_mem` on `loreweave/postgres-knowledge`.** On the recovery path it takes
the 100 000-vector RTO from **17.5 minutes to 7.3**, with every integrity check still passing and
no change in index size. It is a setting on the image, not a bigger machine — the cheapest kind of
fix an RTO can have.

Two cautions that belong with the recommendation:

- `maintenance_work_mem` is **per maintenance operation**, so a server-wide 1 GB with concurrent
  autovacuum workers is not a free 1 GB. Prefer setting it for the restore session/role that does
  the rebuild over raising the global default.
- The value is not magic. 1 GB was chosen as comfortably above the ~435 MB implied by scaling
  14 717 vectors/64 MB up to 100 000 vectors; it is not a tuned optimum and this file does not
  claim one.

## What the first pass got wrong, kept on purpose

The PARTIAL version of this file had one point (40 000 rows) and concluded that the drill's curve
**under-predicted by 68 %** and that the published RTO was therefore optimistic. Two later
corrections:

1. **The 68 % was an anchor mismatch, not a modelling error.** The comparison put this harness's
   40 000-row time against a curve anchored on the *drill's* 20 000-row time. Re-anchoring the
   64 MB column on **its own** 20 000-row point brings it back to within 8 % of `O(n^1.6)` at every
   size. The drill's *exponent* was right; mixing two harnesses' absolutes made it look wrong.
2. **A mid-run reading was reported here as confirmation and was a coincidence.** At 70 000 rows the
   1 GB build landed within 0.7 % of the drill's prediction, which looked like the curve being
   vindicated. It was two errors cancelling: the drill's anchor is ~1.57× faster than this harness,
   and 1 GB is ~1.99× faster than 64 MB at that size. The agreement was arithmetic, not physics.

Recorded because the failure mode is the point: **a single measurement that confirms a hypothesis
is the easiest kind to over-read**, and both mistakes above came from stopping at one number.

## Reproducing

```
./scripts/diskann-rebuild-scale.sh 20000,40000,70000,100000
VEC_MAINT_MEM=1GB ./scripts/diskann-rebuild-scale.sh 20000,40000,70000,100000
```

The RTO table, on the recovery path (the `ALTER DATABASE` is scoped to the throwaway database, so
the server is never mutated and later measurements stay comparable):

```
docker exec lw-t23-vec psql -U postgres -c "CREATE DATABASE lw_drill_qc3_test"
./scripts/vector-backup-drill.sh --dsn postgresql://postgres:…@localhost:7995/lw_drill_qc3_test \
    --rows 100000 --dim 1024
docker exec lw-t23-vec psql -U postgres \
    -c "ALTER DATABASE lw_drill_qc3_test SET maintenance_work_mem='1GB'"
./scripts/vector-backup-drill.sh --dsn … --rows 100000 --dim 1024   # repeat
```

Creates and drops its own throwaway database, prints the bounding settings first, and reports
`cache_full_at` per row so a memory-bound build is visible rather than inferred. It asserts vector
distinctness before timing anything: a seed helper that collapses to one repeated vector produces a
fast, meaningless build, and T24 shipped exactly that bug once (3 000 rows, 1 distinct vector).
