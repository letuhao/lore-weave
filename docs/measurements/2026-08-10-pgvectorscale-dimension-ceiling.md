# pgvectorscale dimension ceiling — 2026-08-10

> **Gate:** plan [T21](../plans/2026-08-09-knowledge-architecture-refactor.md) — *"Verify
> pgvectorscale dims > 2000. **Blocks T22.**"*
> **Stop condition 2:** *"T21 shows pgvectorscale cannot index 2560/3072 → the vector plan
> changes."*

**It does not fire.** StreamingDiskANN has **no dimension ceiling of its own** — it indexes
every dimension up to pgvector's `vector` type limit of 16 000, which is five times the
largest dimension this codebase uses.

---

## Why the question existed

`SUPPORTED_PASSAGE_DIMS = (384, 1024, 1536, 2560, 3072)` — a closed set, already in the
code. pgvector's own HNSW **documents a 2000-dimension cap** (`vector`; 4000 for
`halfvec`), so two of those five dimensions are already unindexable by HNSW today.
pgvectorscale's StreamingDiskANN has **no documented ceiling at all**, and "undocumented"
is not "unlimited" — the sealed design's own residual note (M1) called this out as a gate
to verify *before* P1 commits.

## Rig

| | |
|---|---|
| Image | `timescale/timescaledb-ha:pg17` — pulled fresh, throwaway container, dropped after |
| Postgres | **17.10** |
| pgvector | **0.8.6** |
| pgvectorscale | **0.9.0** |
| Host | the dev workstation, Docker Desktop / WSL2. **Not production.** |

⚠️ **Tested on PG17, while the design targets PG18.** The readily available image bundling
pgvectorscale is PG17; the design's own M1 note records that pgvectorscale supports PG18
(`--pg18 pg_config`). A dimension ceiling is a property of the **extension's index
implementation**, not of the server version, so this result carries — but it is stated
rather than glossed, because "I tested the thing you're shipping" and "I tested a close
relative of it" are different claims.

---

## R-1 — every supported dimension indexes, and the index is USABLE

```
dim 384    diskann: OK
dim 1024   diskann: OK
dim 1536   diskann: OK
dim 2560   diskann: OK        ← beyond HNSW's cap
dim 3072   diskann: OK        ← beyond HNSW's cap
```

Creating an index on an empty table proves less than it looks like, so 3072 was exercised
with real data:

| | |
|---|---|
| rows | 2 000 × `vector(3072)` |
| index build | **2.0 s** |
| index size | 1 808 kB |
| planner | `Index Scan using f3072_dann … Order By: (emb <=> …)` — the index is **chosen**, not merely present |
| correctness | the nearest neighbour of row 42 **is** row 42 |

## R-2 — the positive control, without which R-1 proves nothing

A harness that reports OK for everything reports OK for a broken backend too. pgvector's
HNSW has a *documented* cap, so it is the control:

```
dim 1536   hnsw: OK
dim 2000   hnsw: OK           ← exactly at the documented cap
dim 2560   hnsw: FAIL — ERROR: column cannot have more than 2000 dimensions for hnsw index
dim 3072   hnsw: FAIL — ERROR: column cannot have more than 2000 dimensions for hnsw index
```

The harness detects a dimension cap, with the exact documented message, at exactly the
documented boundary. So StreamingDiskANN's silence is a real absence of a cap rather than a
test that cannot see one.

⚠️ **The first version of this harness reported FAIL for all five dimensions.** It treated
any output on stderr as failure, and `DROP TABLE IF EXISTS` emits a `NOTICE`. A gate whose
first run is a false negative is a gate that gets argued with; it now keys on the **exit
code** with `ON_ERROR_STOP=1` and silences notices.

## R-3 — the ceiling is the TYPE's, not the index's

Rather than stop at "≥3072", the search continued upward:

```
dim 4000   diskann: OK
dim 8000   diskann: OK
dim 16000  diskann: OK
vector(16001) → ERROR: dimensions for type vector cannot exceed 16000
```

StreamingDiskANN indexed every dimension the `vector` type can hold. **The only ceiling is
pgvector's type limit of 16 000**, which no embedding model in the closed set approaches —
the largest is 3072, and the largest in common use anywhere is 4096.

That turns the answer from *"no problem in our range"* into *"there is no index-side limit
to run into"*, which is what T22 needs in order to commit.

---

## Verdict

**Stop condition 2 does not fire. T22 is unblocked.**

`halfvec` is **not needed for reach** — it exists in the plan (T24) as a
recall-vs-storage trade to be measured, not as a workaround for a dimension cap. That
distinction matters for T24's framing: if halfvec had been the only way to index 3072, its
recall cost would have been a price we had to pay. It is not, so T24 measures it as an
option and is free to reject it.
