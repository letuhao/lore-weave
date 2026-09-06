# Apache AGE — re-tested in AGE's own idiom. **The elimination does not hold.**

**Date:** 2026-08-11 · **Image:** `apache/age:latest` → AGE **1.7.0** on **PostgreSQL 18.1**
**Container:** `lw-age-probe`, throwaway, removed after the run — no dev store touched.

> ⛔ **This document replaces an earlier version of itself that reached the opposite conclusion.**
> The first run tested **Neo4j Cypher syntax against AGE** and read the syntax errors as missing
> capability. The PO caught it: *"why did you use your syntax for AGE? you must use its syntax."*
> That objection is correct, and the first version's verdict — *"AGE stays eliminated, now on
> measured basis"* — was **wrong and is retracted**. Testing dialect A against engine B measures
> **portability**, not capability. It is the same error the 2026-08-09 audit made from
> documentation; running it in a container gave a wrong answer the authority of a measurement.

## The question, stated correctly

Not *"does Neo4j Cypher run unchanged on AGE?"* — it does not, and nobody expected it to.
The migration question is: **can AGE express the operations this system performs?**

## Result: all three stated disqualifiers dissolve

| construct | Neo4j form on AGE | AGE-native form | verdict |
|---|---|---|---|
| `MERGE … ON CREATE SET` (19) | `syntax error at or near "ON"` | `SET x = coalesce(x, v)` | ✅ **expressible** |
| `MERGE … ON MATCH SET` (14) | `syntax error at or near "ON"` | unconditional `SET` | ✅ **expressible** |
| `datetime()` (157) | `function does not exist` | **`timestamp()`** | ✅ **mechanical rename** |
| `CALL { … }` (14) | `syntax error at or near "{"` | SQL `CTE` / `LATERAL` | ✅ **expressible, arguably better** |

### 1 · The anchoring pattern, including `__was_created`

`_UPSERT_ANCHOR_CYPHER` is the hard case: create-only fields, match-only fields, and a
`__was_created` flag whose comment explicitly rejects a `created_at == updated_at` heuristic.

**Create-only semantics → `coalesce`.** Same `MERGE` run twice:

```
pass 1:  was_created = t   name="first"    cnt=0
pass 2:  was_created = f   name="second"   cnt=0        ← preserved
         created_at = updated_at → false                ← created_at NOT re-stamped
```

**`__was_created` → a pre-`MATCH` count in the same transaction**, which is exact, not a heuristic:

```sql
BEGIN;
  SELECT count(*) = 0 AS was_created
    FROM cypher('g', $$ MATCH (e:Entity {id:'y1'}) RETURN e $$) as (v agtype);
  SELECT * FROM cypher('g', $$ MERGE (e:Entity {id:'y1'})
    SET e.created_at = coalesce(e.created_at, timestamp()),
        e.cnt        = coalesce(e.cnt, 0),
        e.name       = 'second',
        e.updated_at = timestamp()
    RETURN e.name, e.cnt $$) as (name agtype, cnt agtype);
COMMIT;
```

⚠️ **Gotcha worth carrying into the adapter:** folding this into a **single statement** with a CTE
(`WITH pre AS (…count…), merged AS (…MERGE…)`) returned `was_created = false` on a node that did
not exist. Postgres does not guarantee the evaluation order there, so the pre-count can be read
after the merge. **Two statements in one transaction is the correct form**; the one-statement CTE
is a fragile heuristic of exactly the kind the existing code comment warns against.

### 2 · `CALL { }` — composition moves to SQL, where it is stronger

`cypher()` is a table-valued function, so subqueries are ordinary SQL:

```
CTE     : WITH ents AS (SELECT * FROM cypher(…)) SELECT … → 3 rows ✅
LATERAL : FROM cypher(…) o CROSS JOIN LATERAL (SELECT count(*) FROM cypher(…)) sub → ✅
```

`LATERAL` is the *right* tool for the per-row correlated subquery `CALL { }` is usually used for.
**This is the point the original audit missed entirely:** AGE lives inside Postgres, so a Cypher
construct's absence is not a capability gap when SQL supplies it. The audit compared Cypher
dialects and never considered that half the surface moves to the host language.

### 3 · Controls — the probe is not just broken

| control | result |
|---|---|
| plain `MERGE` | ✅ `"ctl"` |
| plain `MATCH … SET` | ✅ `"ok"` |
| `timestamp()` | ✅ `1786465987257` |
| `MATCH` on an absent node | ✅ `0` rows |
| single-char graph name `'p'` | ❌ `graph name is invalid` — an AGE quirk, not a finding |

## What is actually true about AGE

**The capability claim is refuted. The cost claim is not.** The original audit's sentence
*"AGE requires a full query rewrite"* is **correct** — the query layer must be rewritten to AGE
idiom: ~33 anchoring sites onto `coalesce` + pre-`MATCH`, 157 `datetime()` → `timestamp()`
renames, 14 `CALL { }` → `LATERAL`/CTE.

What does **not** follow is the next clause: *"so its only advantage over other candidates is
gone."* That inference assumed AGE's only advantage was Cypher portability. **Its real advantage
is colocation** — one Postgres holding graph, vectors (already going to pgvector/pgvectorscale per
T3) and truth, with one backup story and one set of ops. That advantage is untouched by a dialect
difference, and eliminating AGE on a capability claim retired it without ever pricing it.

### Against the alternatives, on the same standard

| | dialect cost | operational shape |
|---|---|---|
| **AGE** | ~33 anchoring rewrites + 157 renames + 14 `CALL{}` → `LATERAL` | **same Postgres** as vectors and truth |
| **Kuzu** | 14 `CALL{}` rewrites + 152 renames (`current_timestamp()`) | embedded, one DB file per project, second store to back up |
| **Postgres-relational** | full rewrite — no Cypher at all | same Postgres |

Kuzu's dialect cost is smaller. AGE's operational story is better. **That is a real trade to
decide, which is what the sealed design said should happen — by shadow comparison (T43), not by
argument.** The 2026-08-09 audit removed one contender from that comparison on a claim that a
container now refutes.

## Recommendation — for the PO, not decided here

**`O3` / `T1` / `T2` rest on a refuted premise and should be re-opened.** The register is sealed;
a sealed decision is re-opened by the PO with evidence, never worked around — this is the
evidence. Decision **X1** already requires building *both* candidates and letting T43 choose. If
AGE returns to the shortlist, the honest candidate set is **AGE vs Kuzu vs Postgres-relational**,
and T42 builds two of them.

## Reproducing

```bash
docker run -d --name lw-age-probe -e POSTGRES_PASSWORD=agetest -e POSTGRES_USER=age \
  -e POSTGRES_DB=agetest apache/age:latest
docker exec -i lw-age-probe psql -U age -d agetest <<'SQL'
LOAD 'age'; SET search_path = ag_catalog, "$user", public;
SELECT create_graph('probe');          -- NB: single-character graph names are rejected
BEGIN;
  SELECT count(*) = 0 AS was_created
    FROM cypher('probe', $$ MATCH (e:Entity {id:'y1'}) RETURN e $$) as (v agtype);
  SELECT * FROM cypher('probe', $$ MERGE (e:Entity {id:'y1'})
    SET e.created_at = coalesce(e.created_at, timestamp()), e.cnt = coalesce(e.cnt,0),
        e.name = 'first', e.updated_at = timestamp()
    RETURN e.name, e.cnt $$) as (name agtype, cnt agtype);
COMMIT;
SQL
docker rm -f lw-age-probe
```
