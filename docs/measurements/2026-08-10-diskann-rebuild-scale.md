# diskann rebuild time above the parallel-build threshold — 2026-08-10

> **Status: PARTIAL — one of three points measured.** QC-3 owes the rest. The run was cut short
> by a bug in the harness (since fixed) and then by an operator stop, not by a failure of the
> thing being measured. Re-run with `./scripts/diskann-rebuild-scale.sh 40000,70000,100000`.

## Why this measurement was owed

The T25 restore drill established that **the index rebuild IS the recovery time** — 34.3 s of a
35.3 s restore at 20 000 rows — and fitted `O(n^1.6)` from two points, 5 000 and 20 000.

Both sit **below** `diskann.min_vectors_for_parallel_build = 65536`. Extrapolating a
single-threaded curve across the threshold that switches parallelism on produces a number that
reads like an RTO and is not one. This measures across it.

## Environment, recorded because it decides the answer

`loreweave/postgres-knowledge:18`, vectorscale 0.9.0, 1024-dim (the drill's dim), throwaway DB.

| setting | value |
|---|---|
| `max_parallel_maintenance_workers` | **2** |
| `max_worker_processes` | 8 |
| `maintenance_work_mem` | **64 MB** |
| `shared_buffers` | 128 MB |
| host CPUs visible to the container | 32 |

**The image ships the Postgres defaults.** 32 CPUs are visible and at most 2 maintenance
workers may be used, so "above the threshold" does not mean "parallel" in any useful sense. A
rebuild time quoted without these numbers is not reproducible.

## Result

| rows | parallel-eligible | seed | **index build** | index size | `O(n^1.6)` predicted |
|---|---|---|---|---|---|
| 5 000 *(smoke)* | no | 2.2 s | 4.2 s | 2 880 kB | 3.7 s |
| **40 000** | no | 5.1 s | **175.0 s** | 22 MB | **104.0 s** |
| 70 000 | yes | — | not measured | — | 253.1 s |
| 100 000 | yes | — | not measured | — | 447.0 s |

## What the one point already says

**The drill's curve under-predicts by 68 % at 40 000 rows** — 175 s actual against 104 s
predicted — and 40 000 is still *below* the parallel threshold. So the miss is not about
parallelism at all.

The build log says why:

```
WARNING:  Builder neighbor cache is full after processing 14717 vectors;
          consider increasing maintenance_work_mem
```

**The builder's neighbor cache fills at ~14 700 vectors, on 64 MB.** That is below the 20 000-row
point the drill fitted its curve through, and far below the 65 536 threshold this measurement was
commissioned to cross. The `O(n^1.6)` fit therefore spans a regime change it could not see: the
5 000-row point was measured with the cache intact, the 20 000-row point with it already full.

Two consequences, both of which matter more than the parallel threshold:

1. **`maintenance_work_mem` is the lever, not the worker count.** The threshold QC-3 was told to
   cross is downstream of a limit that binds four times earlier.
2. **The published RTO is optimistic in the wrong direction.** Anything extrapolated from that
   curve will under-state recovery time, and recovery estimates that are too low are the ones
   that hurt.

## What is still owed

- The 70 000 and 100 000 points (the actual threshold crossing).
- **A second sweep at a raised `maintenance_work_mem`** — this is now the more interesting
  variable. If 256 MB or 1 GB moves 40 000 rows back toward the predicted 104 s, the fix for the
  RTO is a setting on the image, not a bigger machine.
- Only then a defensible RTO, stated with the settings it was measured under.

## Reproducing

```
./scripts/diskann-rebuild-scale.sh 40000,70000,100000
```

Creates and drops its own throwaway database. It asserts vector distinctness before timing
anything: a seed helper that collapses to one repeated vector produces a fast, meaningless
build, and T24 shipped exactly that bug once (3 000 rows, 1 distinct vector).
