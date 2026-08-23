# The databases the service suites need, and what each one un-skips

A suite that skips is not a suite that passes. On 2026-08-23 the full run reported
**4748 passed / 728 skipped** and read as green — while 24 of those skipped tests covered
`PgVectorStore`, the store T25 cut production passage reads onto. Three of them had been
asserting the StreamingDiskANN design **QC-3 replaced**, and the adapter was still emitting
`SET LOCAL diskann.*` in every search transaction against an index type that no longer existed.
The tests that would have caught it were dark, so the adoption landed against them and nobody
saw either half.

With every database below present the same suite reports **5469 passed / 9 skipped / 0 failed**
— the same code, **721 more tests actually run**, and the only remaining skips are the seven
opt-in `--run-quality` evals (they spend on a provider) and two comparisons with nothing
recorded to compare.

> ⚠️ Every fixture here REFUSES a non-throwaway target before it writes. That is not a
> formality: `kg-integration-tests-truncate-shared-dev-db` records an incident where they did
> not, and `T42a` records a guard that matched `":7688"` as a SUBSTRING and so sailed straight
> past `localhost:27688`. Give them their own instance; do not point them at a dev stack.

| variable | un-skips | how to satisfy it |
|---|---|---|
| `TEST_NEO4J_URI` (+ `_USER`, `_PASSWORD`) | ~411, incl. the conformance suite's **neo4j** arm and the QC-2 fake-parity file | a dedicated instance — see below |
| `TEST_KNOWLEDGE_DB_URL` | ~282 repo/migration tests | a throwaway Postgres whose DB NAME carries `test`/`smoke`/`scratch`/… |
| `TEST_VECTOR_DB_URL` | 24 pgvector tests (`PgVectorStore`) | a throwaway `loreweave/postgres-knowledge:18` |
| `TEST_AGE_DSN` | the AGE repo-layer proof + AGE conformance arm | the isolated `knowledge-pg` (AGE + pgvector) |

## The three containers

```bash
# pgvector — 24 tests. The fixture calls _guard_throwaway(dsn) BEFORE any DROP.
docker run -d --name lw-vec-test -e POSTGRES_PASSWORD=throwaway \
  -e POSTGRES_DB=loreweave_vectors_test -p 7995:5432 loreweave/postgres-knowledge:18
export TEST_VECTOR_DB_URL="postgresql://postgres:throwaway@localhost:7995/loreweave_vectors_test"

# Neo4j — ~411 tests. NOT the dev graph: these CREATE and DETACH DELETE nodes, and the
# fixture refuses ports 7687/7688/27687/27688 (the base stack's AND the isolated stack's
# republication of them) for exactly that reason.
docker run -d --name lw-neo4j-test -e NEO4J_AUTH=neo4j/throwaway_test \
  -p 7690:7687 neo4j:2026.03-community
export TEST_NEO4J_URI="bolt://localhost:7690"
export TEST_NEO4J_USER=neo4j
export TEST_NEO4J_PASSWORD=throwaway_test
```

```bash
# the knowledge repo/migration suite — ~282 tests. The fixture TRUNCATEs, and
# `_guard_throwaway(dsn)` refuses any database whose NAME lacks test/smoke/audit/scratch/…
docker run -d --name lw-know-test -e POSTGRES_PASSWORD=throwaway   -e POSTGRES_DB=loreweave_knowledge_test -p 7996:5432 loreweave/postgres-knowledge:18
export TEST_KNOWLEDGE_DB_URL="postgresql://postgres:throwaway@localhost:7996/loreweave_knowledge_test"
```

## The other services

`test-env-registry-gate` scans **every** `services/*/tests` tree, not just `knowledge-service` —
because it was scoped to one service at first and `composition-service` turned out to be sitting
on **403** skipped tests behind a single variable, in the service that owns QC-5's critic.

| variable | service | un-skips | status |
|---|---|---|---|
| `TEST_COMPOSITION_DB_URL` | composition-service | 403 (`400 passed, 8 skipped` once set) | **VERIFIED 2026-08-23** |
| `TEST_CAMPAIGN_DB_URL` | campaign-service | its `tests/integration` tree | recorded, recipe **NOT yet run** |
| `TEST_LORE_ENRICHMENT_DB_URL` | lore-enrichment-service | its `tests/integration` tree | recorded, recipe **NOT yet run** |

```bash
# composition-service — 403 tests. Its conftest guard refuses a DB whose name lacks a
# throwaway marker, BEFORE any pool opens. The db tree takes ~10 min.
docker run -d --name lw-comp-test -e POSTGRES_PASSWORD=throwaway   -e POSTGRES_DB=loreweave_composition_test -p 7997:5432 postgres:18-alpine
export TEST_COMPOSITION_DB_URL="postgresql://postgres:throwaway@localhost:7997/loreweave_composition_test"
```

⚠️ **The last two rows say "NOT yet run" because they have not been.** Both services carry the
same `_THROWAWAY` name guard, so the shape of the command is predictable — and a predicted
command written as if it were measured is the thing this whole document exists to prevent. The
variable is recorded so the suite is not silently dark; the recipe is owed a run.

`TEST_AGE_DSN` needs no new container — the isolated stack already publishes one:

```bash
export TEST_AGE_DSN="postgresql://loreweave:loreweave_dev@localhost:25556/loreweave_knowledge_vectors"
```

## Why this file is GATED

`handoff-staleness-gate`'s sibling, `test-env-registry-gate`, derives every `TEST_*` variable
named in a `pytest.skip(...)` under `services/knowledge-service/tests/` and requires each to
appear here. A new env-gated suite that forgets this file is a suite that goes dark silently —
which is the whole failure this document exists to stop, and the reason the registry is checked
rather than merely written.
