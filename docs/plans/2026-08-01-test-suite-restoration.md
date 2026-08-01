# Test-suite restoration + parallelisation — the measured plan

**Parked by the author 2026-08-01** (*"lên plan đổi khôi phục mấy gate skipped hoặc sửa lại và
qui hoạch lại test theo chỉnh sửa cho mấy cái suite chậm như rùa đó"*). Every number below was
measured on this machine today; nothing here is estimated.

---

## The finding that reframes the whole thing

**CI arms every gated suite.** `python-integration-tests.yml` sets `TEST_COMPOSITION_DB_URL`,
`TEST_KNOWLEDGE_DB_URL`, `TEST_LORE_ENRICHMENT_DB_URL`, `TEST_CAMPAIGN_DB_URL` and
`JOBS_TEST_PG_DSN`. So the skips are **not a coverage hole** — they are a *local-dev* gap.

That changes what "restore the skipped gates" means. Nothing is unprotected in CI. What is
broken is that a developer running `pytest` sees green while 12% of the suite never executed,
which is how a defect reaches CI in the first place.

---

## Measured state

| suite | tests | local, no env | local, armed | note |
|---|---:|---|---|---|
| composition | 3843 | 8 skipped, **107s** | — | already treated (3dd803c96) |
| knowledge | 4659 | 4098 passed, **561 skipped**, 24s | `tests/integration` **627 passed, 0 skipped, 119s** | needs 4 vars + serial |
| lore-enrichment | 1006 | not yet measured | — | `TEST_LORE_ENRICHMENT_DB_URL` |
| campaign | 15 files | — | — | `TEST_CAMPAIGN_DB_URL` |
| jobs | 12 files | — | — | `JOBS_TEST_PG_DSN` |
| translation | 91 files | no DB gate | — | |

**Knowledge's 561 skips break down as:** 280 `TEST_NEO4J_URI not set`, 7 opt-in eval
(`--run-quality`), the rest gated on `TEST_KNOWLEDGE_DB_URL`.

**Both dependencies already run in the dev stack.** Postgres on :5555, Neo4j on :7688
(`NEO4J_AUTH=neo4j/loreweave_dev_neo4j` — *not* the Postgres password; using the wrong one was
worth ten minutes today).

### The recipe that works, verified

```bash
docker exec -i infra-postgres-1 psql -U loreweave -d postgres \
  -c "CREATE DATABASE loreweave_knowledge_devtest"

cd services/knowledge-service
TEST_KNOWLEDGE_DB_URL="postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_knowledge_devtest" \
TEST_NEO4J_URI="bolt://localhost:7688" \
TEST_NEO4J_USER=neo4j TEST_NEO4J_PASSWORD=loreweave_dev_neo4j \
python -m pytest tests/integration -q -p no:cacheprovider
# 627 passed in 119.21s
```

### The trap, also verified

The same command with `-n auto --dist loadgroup` gives **12 failed, 398 passed, 118 errors**.
Knowledge has exactly the defect composition had before 3dd803c96: many xdist workers, one
shared database, migrations racing. It is not slow — it is *unsafe in parallel*, and the
failure mode is a wall of `asyncpg` errors that reads like a product defect.

---

## The plan, in dependency order

### 1 · Port composition's conftest pattern to knowledge (highest value)

`services/composition-service/tests/conftest.py` already solves this and is proven:
**508s → 107s (4.7×)**, same pass/fail set. Two mechanisms, both needed:

- **one database per xdist worker** — rewrite `TEST_*_DB_URL` to `…_gw0`/`…_gw1` at conftest
  import (before test modules read it), creating the DB on demand. No-ops when
  `PYTEST_XDIST_WORKER` is unset, so CI's serial run is untouched.
- **a fingerprinted migration memo** — skip `run_migrations` when the schema fingerprint
  (table count + max oid in `public`) is unchanged. Fingerprinted, not a plain seen-set,
  because several fixtures `DROP TABLE` and rebuild.

Expected outcome for knowledge: `-n auto` becomes SAFE (the 118 errors are races on one DB),
and the 119s serial run drops toward 30s. **Both halves must be re-measured, not assumed** —
composition's 4.7× came mostly from parallelisation, and knowledge's shape may differ.

⚠ One thing composition's version needs before porting: an escape hatch already exists
(`run_migrations_uncached`) for the one test whose subject IS the migration runner. Knowledge
will need the same audit — grep for tests that mutate migration bookkeeping.

### 2 · Make a bare `pytest` run everything locally

The 561 skips exist because a dev has no `TEST_*_DB_URL`. The conftest from step 1 already
creates databases on demand; extend it to also SUPPLY the base DSN when the var is unset,
deriving `<service>_devtest` (the name carries the `test` marker the db-safety guard requires,
and is never a production DB name).

CI is unaffected — it sets the var explicitly, and an explicit value always wins.

For knowledge, do the same for `TEST_NEO4J_URI` from the compose default. That alone recovers
280 tests.

**Do NOT** default a DSN by falling back to a production `*_DB_URL`. That is the exact incident
CLAUDE.md's destructive-ops rule exists for.

### 3 · Roll to the remaining services

lore-enrichment (1006 tests), campaign, jobs. Same two mechanisms. Measure each before and
after rather than assuming the composition ratio.

### 4 · A gate, so this cannot rot back

A repo-level check that every service with a `TEST_*_DB_URL`-gated suite has the conftest
pattern, ratcheted like `llm-budget-ssot-gate`'s two axes. Without one, the next service added
starts at 561-skips-and-nobody-notices, which is where knowledge is today.

---

## What this plan does NOT claim

- **No estimate of the total win.** Composition's 4.7× is one data point on one suite; I have
  not measured lore-enrichment, campaign or jobs at all.
- **Knowledge's 12 failures + 118 errors under `-n auto` are ASSUMED to be shared-DB races**
  because the shape matches composition's, and because the same tests pass serially. I did not
  isolate a single one to prove the mechanism.
- **The 561→0 claim covers `tests/integration` only.** The full `tests` tree armed still showed
  skips I did not chase; the unit tree has its own gates.
- Nothing here addresses the glossary Go suite (12 min, and a flaky PP-4 pair fixed today to
  stop it blaming production for fixture state).
