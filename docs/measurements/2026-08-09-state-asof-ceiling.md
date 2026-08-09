# `state@as_of` end-to-end measurement — 2026-08-09

> **Under test:** `GET /internal/books/{book_id}/state?as_of=N` (glossary-service, plan T5)
> and its KAL exposure `GET /v1/kal/books/{book_id}/state?as_of=N` (knowledge-gateway, T6).
> **Plan:** [`docs/plans/2026-08-09-knowledge-architecture-refactor.md`](../plans/2026-08-09-knowledge-architecture-refactor.md) T8
> **Harness:** `scripts/state-asof-live-smoke.sh` (QC-1) — the numbers below are printed by
> its `PERF` block, and the query plan by `EXPLAIN (ANALYZE, BUFFERS)` against the same book.

This is the gate the sealed design named as **most likely to invalidate it**: if reading the
whole cast at a story position is unaffordable per chapter through the KAL, §12's read model
needs rethinking. It is not. The hop costs **~1.5×**, on a read that is single-digit-to-tens
of milliseconds.

---

## Rig

| | |
|---|---|
| Host | the dev workstation — Docker Desktop on Windows 11, WSL2 backend. **Not production.** |
| Postgres | `postgres:18` in `infra-postgres-1`, shared with every other dev service |
| Services | `glossary-service` and `knowledge-gateway`, rebuilt from the working tree immediately before the run (`docker compose build` → `up -d`) |
| Corpus | the real dev glossary: **48 492 facts across 11 books**; the book measured is the largest — **26 192 facts over 1 673 entities**, chapters 0–97 |
| Method | 20 consecutive reads per surface, same book, same `as_of`, warm |
| Durability | `fsync` at the image default (on). No tuning, no `work_mem` override |

**Ratios, not absolutes.** Every absolute below is a property of this laptop. The ratio
between the two surfaces is the thing that transfers, because both hops run on the same host
under the same load.

---

## R-1 — the KAL hop costs ~1.5×, and that is affordable per chapter

| surface | p50 | p95 |
|---|---|---|
| in-process (`glossary /internal/.../state`) | **34.8 ms** | 43.4 ms |
| through the KAL (`gateway /v1/kal/.../state`) | **51.0 ms** | 67.6 ms |
| **ratio** | **×1.47** | **×1.56** |

A second run 90 seconds earlier measured ×1.62 / ×1.65 — so call it **×1.5 ± 0.1**, which is
the resolution this rig supports. The absolute overhead is ~16 ms: one extra HTTP hop plus
JSON re-serialization, exactly what the architecture buys tenancy and contract enforcement
with.

**Against the stop condition** — *"T8 shows the KAL hop makes `state@as_of` unaffordable per
chapter → §12 needs rethinking."* A drafting run resolves the cast **once per chapter**, next
to LLM calls measured in seconds. 51 ms against a 20-second generation is **0.25 %**. The
stop condition does not fire.

Baseline for comparison: the design recorded **8.7 ms flat at 26k facts** for the underlying
fact read. This measurement is of the whole endpoint on a shared dev host including the
`DISTINCT ON`, the join, HTTP, and JSON — a different quantity, not a regression against it.

---

## R-2 — the read plan is `Index Scan + Sort` today, which is precisely what T9 removes

`EXPLAIN (ANALYZE, BUFFERS)` on the largest book at `as_of=50`:

```
Unique (actual rows=8914)                       -- the DISTINCT ON
  -> Sort (actual rows=8938)
       Sort Key: f.entity_id, f.attr_or_predicate, f.valid_from_ordinal DESC
       Sort Method: quicksort  Memory: 1213kB
       -> WindowAgg (actual rows=8938)          -- count(*) OVER () for the log line
            -> Hash Join (actual rows=8938)
                 -> Index Scan using idx_entity_facts_book on entity_facts f
                      Index Cond: (book_id = …)
                      Filter: (invalidated_at IS NULL) AND (valid_from_ordinal <= 50)
                              AND (50 < valid_to_eff) AND (cardinality = 'single')
                      Rows Removed by Filter: 17254
                 -> Bitmap Heap Scan on glossary_entities e (rows=1734)
```

Three numbers matter:

- **17 254 of 26 192 rows are read and then discarded** by the filter. The book index carries
  `book_id` only, so the as-of predicate cannot be index-served.
- **`Sort … quicksort Memory: 1213kB`** — the sort T9's covering index exists to remove. It
  grows with book length; at the T10 ceiling (~1.08 M facts/book) it spills `work_mem`.
- **8 938 rows in → 8 914 out** of the `DISTINCT ON`. Only 24 rows are collapsed here, which
  is the honest reading of AC2 on this corpus: overlapping intervals are **rare but real**
  (24 of them in one book), so `DISTINCT ON` is not decoration — it is the thing standing
  between a caller and two contradictory values on 24 attributes.

This is T9's before-picture. Its bite is stated there: drop the covering index and the plan
must return to `Sort`.

---

## R-3 — the consumer sees 1 674 entities and renders 1 463 bible rows (FINDING, not a gate)

The QC-1 smoke drives the read through composition's own `KalClient.state()`. On the real
book it returns **1 674 entities**, and `cast_from_state` flattens those to **1 463 canon
bible rows**.

That is a large prompt input, and it is worth being explicit that **T7 did not make it
larger in row count** — the `roster` path it replaced drained the same 1 674 entities. What
changed is per-row width: a bible row used to be a bare name (the roster projection is id+name
by contract), and now carries `role` / `description` / `relationships` where the facts exist.

**No cap was added, deliberately.** Truncating the cast to the first N would be a silent
correctness change dressed as a performance fix, and *which* cast members matter for a given
chapter is a salience question this task has no business answering. Recorded here so the
decision is visible; the context-budget law owns the ceiling, and a per-chapter salience
filter is the shape of any real fix.

---

## Bite

A measurement with no bite reports whatever the rig felt like reporting. Two here:

1. **The PERF block cannot report a flattering ratio by accident** — it times the *same*
   `as_of` on *both* surfaces in the same run, seconds apart. A gateway that silently
   short-circuited (returned a cached or empty body) would show a ratio **below 1**, which is
   the tell. It measured 1.47–1.65 across two runs.
2. **The read demonstrably honours `as_of`** — the smoke asserts `alive` at 9039 and `dead`
   at 9040 on the same entity, through the gateway. An endpoint that ignored the parameter
   returns the head value at both positions and fails the first leg. That is what makes the
   whole file non-vacuous: every other assertion could pass against a stubbed read, but this
   pair cannot.

---

## Verdict (T8)

**No stop condition fires.** The KAL hop is ×1.5 on a per-chapter read costing tens of
milliseconds; §12's read model stands as sealed. T9's covering index is confirmed as
necessary rather than speculative — the plan reads 2.9× the rows it returns and sorts 1.2 MB
to do it, on a book of 97 chapters.

---

# T9/T10 — the covering index and the 4 000-chapter ceiling *(2026-08-10)*

> **Rig:** `scripts/perf/state-asof-ceiling.sh` — builds its own throwaway database, applies
> the real migration chain (so the index under test is the SHIPPED one), seeds
> 1 500 entities × 12 attributes × 60 revisions on one book (**1.08 M facts, ordinals
> 0–3 960**) plus 9 decoy books, and drops the database on exit.

## R-4 — the plan's stated rationale for T9 was wrong in both halves

T9 asked for `(book_id, entity_id, attr_or_predicate, valid_from_ordinal DESC)` to *"remove
the sort … which grows linearly with book length and spills work_mem."* Measured:

- **The sort does not grow with book length.** At one position, exactly one interval per
  (entity, attribute) can match, so the sort input is *cast size × attributes* — not chapter
  count. **2 175 kB at 108 k facts and 2 175 kB at 1.08 M facts.** (It can still spill, on a
  book with a very large *cast*. Different axis, different fix.)
- **The key-only index does not remove the sort either.** The read joins `glossary_entities`
  for the recycle-bin filter, and a join above the scan destroys the index ordering — the
  `Sort` node survives whichever index is chosen. Forcing an ordered path (`enable_sort=off`)
  produces one, at **12× the buffers**, which is why the planner declines it.

What actually costs time is the **heap**: ~558 k random fetches for `value` and `fact_kind`.
`INCLUDE (valid_to_eff, value, fact_kind)` makes the scan **index-only** (`Heap Fetches: 0`).
Five runs, median, at the ceiling:

| index | median | size | plan |
|---|---|---|---|
| none | 281.1 ms | — | `Index Scan` on the book index + `Sort` |
| **the plan's literal definition** (key columns only) | 197.6 ms | 140 MB | `Index Scan` + `Sort` — the sort it was meant to remove |
| **shipped** (+ `INCLUDE`) | **74.1 ms** | 216 MB | `Index Only Scan`, `Heap Fetches: 0` |

The deviation is recorded in `entity_facts_asof_index.go` and guarded by a test that fails if
the `INCLUDE` list is trimmed.

## R-5 — the index pays where books are one of many, and that is the normal shape

The ceiling rig has one pathology worth naming: its target book is **53 % of the whole
table**, so scanning everything costs only ~2× the necessary work. Real databases hold every
book on the deployment. Both shapes, measured on the same rig:

| shape | with the index | without | verdict |
|---|---|---|---|
| **a normal book — 108 k facts, 5 % of a 2.05 M-row table** | **16.2 ms** (`Index Only Scan`) | 50.2 ms (`Bitmap Heap Scan`) | **index wins ×3.1** |
| one 4 000-chapter book at 53 % of the table | 87.3 ms (`Index Only Scan`) | 64.8 ms (parallel `Seq Scan`) | seq scan wins ×1.35 |

**Ship it.** The second row is the rig's artifact, not a deployment shape — and even there the
cost is 22 ms, against a 34 ms win in the first row that *grows* with the number of books on
the deployment. A database that contains essentially one enormous book is precisely the case
where a sequential scan is near-optimal anyway, and both plans finish under 90 ms.

## R-6 — the ceiling itself is not a ceiling

The question T10 exists to answer is whether `state@as_of` survives a 4 000-chapter book.
**It does, either way: 65–87 ms.** The read returns ~18 000 facts at any position regardless
of book length, because only one interval per (entity, attribute) can cover a given ordinal.
Book length grows the rows *scanned*, never the rows *returned* — which is why this is a scan
problem, and why the index that fixes it is a covering index rather than a sort-avoiding one.

## Build window (the `CONCURRENTLY` conflict, resolved inside T9)

`CREATE INDEX CONCURRENTLY` **cannot run in the chain runner at all** — `execGuarded` wraps
every step in a transaction with `pg_advisory_xact_lock`, and CONCURRENTLY is forbidden
inside one. So the step takes the write-blocking build, with the window measured:

| build | duration at 2.16 M facts |
|---|---|
| plain `CREATE INDEX` (what the step runs; blocks writes) | **2.4 s / 2.8 s** (two runs) |
| `CREATE INDEX CONCURRENTLY` (for comparison) | 3.2 s |

Reads are unaffected throughout; only writes to `entity_facts` queue, for under three seconds
at ~45× the current corpus. An operator who cannot accept even that builds the index
CONCURRENTLY out of band **before** upgrading — `IF NOT EXISTS` then makes the step a no-op.
That route is deliberately not the default: a migration that depends on someone remembering a
manual step is a migration that silently does not exist wherever they forgot.

## Bite

The rig drops the index and re-measures in the same run, and refuses to publish a ratio unless
the planner actually chose the index — a "ratio" between one plan and itself is host noise
wearing a decimal point.

Three harness defects were found and fixed rather than worked around, all of which produced
*plausible* numbers:

1. **The scan-node regex could not match an index name** (`[a-z ]*` excludes `_` and digits),
   so the result table reported the wrong plan for both runs.
2. **`VACUUM` was missing after the bulk seed**, leaving the visibility map unset — an
   `Index Only Scan` is then unavailable and the rig concludes the index does not help.
3. **The index was 40 % bloated** (301 MB vs 205 MB rebuilt) because the chain creates it on
   an empty table and the rig then grows it through a 2 M-row insert landing in seconds. The
   rig now `REINDEX`es and says why: a real deployment writes those facts over months with
   autovacuum running, so that bloat is an artifact of how the rig loads, not of the workload.

Also `python3 -c` exits silently with no output on this Windows host, which printed a bare
`ratio : x`. The script uses a heredoc instead.
