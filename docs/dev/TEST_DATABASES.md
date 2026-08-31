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
| `TEST_AGE_DSN` | the AGE repo-layer proof + AGE conformance arm — **115 tests**, and AGE is the DEFAULT backend | a THROWAWAY `loreweave/postgres-knowledge:18`; the same `lw-know-test` container below serves it (`CREATE EXTENSION age`) |

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

### ⚠️ `TEST_AGE_DSN` — verified 2026-08-30, and the recipe CHANGED

This row used to read *"the isolated `knowledge-pg`"*. **These tests create and drop graphs**,
so pointing them at a live stack's database is the hazard `_guard_throwaway` exists to refuse —
and a recipe that names a live DB is one people rightly decline to run, which is how the
DEFAULT BACKEND's own conformance arm came to skip by default.

`lw-know-test` already carries AGE (same image), so one container serves both:

```bash
export TEST_AGE_DSN="postgresql://postgres:throwaway@localhost:7996/loreweave_knowledge_test"
```

**Measured on `services/knowledge-service/tests/integration`, 2026-08-30:**

```
default (nothing set)      238 passed ·  834 skipped
+ the three containers     955 passed ·  117 skipped     <- +717
+ TEST_AGE_DSN            1070 passed ·    2 skipped     <- +115, the AGE conformance arm
```

The last two are correct: `test_shadow_differential` skips when no divergences are RECORDED
for an engine, and there are none. Everything else runs.

## The other services

`test-env-registry-gate` scans **every** `services/*/tests` tree, not just `knowledge-service` —
because it was scoped to one service at first and `composition-service` turned out to be sitting
on **403** skipped tests behind a single variable, in the service that owns QC-5's critic.

| variable | service | un-skips | status |
|---|---|---|---|
| `TEST_COMPOSITION_DB_URL` | composition-service | 403 (`400 passed, 8 skipped` once set) | **VERIFIED 2026-08-23** |
| `TEST_CAMPAIGN_DB_URL` | campaign-service | `184 passed, 20 skipped` -> **`204 passed, 0 skipped`** | **VERIFIED 2026-08-23** |
| `TEST_LORE_ENRICHMENT_DB_URL` | lore-enrichment-service | `1261/162` -> `1403/20` (then `1421/2` with the binaries) | **VERIFIED 2026-08-23** |

```bash
# composition-service — 403 tests. Its conftest guard refuses a DB whose name lacks a
# throwaway marker, BEFORE any pool opens. The db tree takes ~10 min.
docker run -d --name lw-comp-test -e POSTGRES_PASSWORD=throwaway   -e POSTGRES_DB=loreweave_composition_test -p 7997:5432 postgres:18-alpine
export TEST_COMPOSITION_DB_URL="postgresql://postgres:throwaway@localhost:7997/loreweave_composition_test"
```

```bash
# campaign-service (20 tests) and lore-enrichment-service (142). Both carry the same
# _THROWAWAY name guard as the others.
docker run -d --name lw-camp-test -e POSTGRES_PASSWORD=throwaway   -e POSTGRES_DB=loreweave_campaign_test -p 7998:5432 postgres:18-alpine
export TEST_CAMPAIGN_DB_URL="postgresql://postgres:throwaway@localhost:7998/loreweave_campaign_test"

docker run -d --name lw-lore-test -e POSTGRES_PASSWORD=throwaway   -e POSTGRES_DB=loreweave_lore_enrichment_test -p 7999:5432 postgres:18-alpine
export TEST_LORE_ENRICHMENT_DB_URL="postgresql://postgres:throwaway@localhost:7999/loreweave_lore_enrichment_test"
```

✅ **These two said "NOT yet run" for one cycle and now do not.** A predicted command written as
if it were measured is what this document exists to prevent, so they were recorded as owed and
then run: **+20** and **+142** tests, no defects.

## A BUILD ARTIFACT is the other way a suite goes dark

18 lore-enrichment tests skipped for want of two Rust binaries — not a variable, and so invisible
to the first version of this gate. **They take 7.31s to build.** One of those skips says why the
refusal is right, and it is worth keeping: *"treating 'no validator' as 'nothing to validate'
would admit every candidate on a host where the build failed."*

```bash
cargo build -p ruleset-loader --bin progression-pin --bin progression-validate
```

With that, lore-enrichment runs **1421 passed / 2 skipped** — the last two being one vacuous
case and one optional `docx` import.

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
