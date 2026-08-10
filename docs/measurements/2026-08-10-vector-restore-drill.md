# Vector backup and restore drill — 2026-08-10

> **Gate:** plan [T25](../plans/2026-08-09-knowledge-architecture-refactor.md) — *"Vectors are
> **durable primary data** (decision T4) — restored, never recomputed, because per-project BYOK
> means re-embedding spends **the user's** budget… **an untested restore is not a backup.**"*

Harness: [`scripts/vector-backup-drill.sh`](../../scripts/vector-backup-drill.sh). It does not
check that a dump file exists — it **destroys the table and gets it back**, then verifies three
different things about what came back.

**The restore is sound, and it does not restore the answers.** Every byte of every vector returns
identical and the exact nearest-neighbour query is unchanged — but at 20 000 rows the rebuilt ANN
index returns a **different top-10 (overlap 7/10)** for the same query. `pg_restore` rebuilds the
index from the data rather than copying its pages, so the recovered graph is a different graph.
Data recovery and result recovery are not the same guarantee, and only the first one is promised.

**The index rebuild is the recovery time**, not the data copy: **34.3 s of a 35.3 s restore** at
20 000 rows.

---

## Results

| | 5 000 rows | 20 000 rows |
|---|---|---|
| live table | 31 344 kB | 125 104 kB |
| dump (`-Fc`) | 22 733 kB | 90 917 kB (**≈27 % smaller**) |
| backup | 4.1 s | 15.2 s |
| restore (total) | 4.3 s | 35.3 s |
| — of which **ANN index rebuild** | **3.6 s (84 %)** | **34.3 s (97 %)** |
| rows recovered | 5 000 / 5 000 | 20 000 / 20 000 |
| vector checksum | identical | identical |
| **exact** top-10 | unchanged | unchanged |
| **ANN** top-10 | unchanged | **7/10 overlap** |

1024-dim, `loreweave/postgres-knowledge:18`, throwaway database.

## What each check is for

**The destroy step is what makes the rest mean anything.** The table is dropped and its absence
verified before `pg_restore` runs. A drill that restores over intact data would pass just as
happily if `pg_restore` were a no-op — so that was the bite: replacing the restore with `true`
gives **`passed=2 failed=4`**, exit 1.

**Checksum over every vector, order-independent** (`sum(hashtext(embedding))`). A row count says
20 000 rows came back; it does not say they are the same 20 000 vectors. The sum is
order-independent because a restore is free to change physical row order and that is not a defect.

**Exact vs approximate answers are checked separately, and only the exact one is asserted.** The
exact answer is arithmetic over restored bytes and must be identical — if it drifts, the data is
wrong. The ANN answer is the output of a rebuilt graph and may legitimately differ; asserting it
would make a correct restore look broken, and hiding it would let a real recall regression pass. So
it is measured and printed either way.

**The seed asserts its own distinctness.** T24 found a sibling helper that seeded 3 000 rows holding
one distinct vector, because an uncorrelated subquery is hoisted into an InitPlan however volatile
`random()` is. A drill over identical vectors would "verify" a restore that returned any row at all.

## ⚠️ These numbers cannot be extrapolated to production

The rebuild went 3.6 s → 34.3 s for 4× the rows: **9.5× time for 4× data**, roughly `O(n^1.6)`.
Extrapolating that to 63 M vectors yields an answer measured in months, which is certainly wrong —
and the reason is visible in the server's own settings:

```
diskann.min_vectors_for_parallel_build = 65536
```

**Both measurements are below that threshold, so both were built single-threaded.** Production is
three orders of magnitude above it and would build in parallel. So this drill establishes that the
procedure is *correct*; it establishes nothing about how long it takes at scale, and the superlinear
slope here is an artefact of the regime it was measured in.

**QC-3 owes a rebuild measurement above 65 536 vectors.** Until then there is no defensible RTO for
the vector store.

## Consequences for the runbook

1. **Restore, never re-embed** — decision T4, and the drill shows restore works. Re-embedding 63 M
   passages would spend project owners' BYOK credentials to recover from our failure.
2. **Budget the recovery as an index build.** Data transfer is ~3 % of it. A restore that must be
   fast should restore data first and build the ANN index after, accepting slower (sequential-scan)
   searches during the window rather than a longer outage.
3. **Re-measure recall after any real restore.** The rebuilt graph is a different graph; the 7/10
   overlap at 20 000 rows is normal, but it means post-restore recall is an open question every
   time, not an inherited fact.
4. **The dump must carry the extension.** `pg_restore` re-creates the index DDL, which fails on a
   server without `vectorscale`. The drill asserts the index definition survived; restoring onto a
   stock Postgres would fail at that step, loudly, which is the correct behaviour.

**Reproduce:**

```bash
scripts/vector-backup-drill.sh \
  --dsn postgresql://postgres:…@localhost:7995/loreweave_vectors_test --rows 20000
```
