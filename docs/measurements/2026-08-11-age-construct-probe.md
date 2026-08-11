# Apache AGE — the elimination, re-tested against a running AGE

**Date:** 2026-08-11 · **Image:** `apache/age:latest` → AGE **1.7.0** on **PostgreSQL 18.1**
**Container:** `lw-age-probe` (throwaway, port 5599, removed after the run — no dev store touched)

## Why

AGE was the original engine choice for this migration — *"Apache AGE + pgvector/pgvectorscale,
inside the Postgres you already run"* (migration PLAN §4). It was eliminated on 2026-08-09 by
construct audit **M2 → O3 → T1**, on the basis that `datetime()` and
`MERGE … ON CREATE SET / ON MATCH SET` are unsupported.

The PO recalled AGE as the decision and asked for it to be settled by building it rather than by
citing documentation. That is the right instinct: the elimination's basis was recorded as
**`audited`** — a documentation check — while it was the *sole* load-bearing reason AGE is out.
Everything downstream (the Postgres-relational vs Kuzu contest, T42, T43's shadow comparison)
rests on it.

## Result: the elimination HOLDS, and the stated reason was over-broad

| construct | uses in repo | AGE 1.7.0 | |
|---|---|---|---|
| `MERGE … ON CREATE SET` | 19 | `ERROR: syntax error at or near "ON"` | ❌ **fatal** |
| `MERGE … ON MATCH SET` | 14 | `ERROR: syntax error at or near "ON"` | ❌ **fatal** |
| `MERGE` with both clauses | — | `ERROR: syntax error at or near "ON"` | ❌ **fatal** |
| `datetime()` | 157 | `ERROR: function datetime does not exist` | ⚠️ **rename, not fatal — see below** |
| `CALL { … }` | 14 | `ERROR: syntax error at or near "{"` | ❌ |

### Controls — because a negative result with a broken harness is not a result

| control | result |
|---|---|
| plain `MERGE (e:Entity {id:'ctl'})` | ✅ `"ctl"` |
| plain `MATCH … SET e.name` | ✅ `"ok"` |
| `timestamp()` | ✅ `1786464248104` |
| `localtimestamp()` | ❌ does not exist |

Plain `MERGE` and plain `SET` both work, so the failures above are the constructs and not the
setup. **This is the check that makes the whole probe mean anything** — without it, a
misconfigured graph or a bad `search_path` would produce the identical five errors and read as
confirmation.

## The correction: `datetime()` is a rename, and the audit applied two different standards

**AGE has `timestamp()`.** It returns epoch milliseconds, and the 157 `datetime()` sites are
therefore a *mechanical rename* — not a rewrite.

That matters because **it is precisely the finding that revived Kuzu's candidacy.** Audit item
**M8** asked whether Kuzu supports `datetime()`, found `current_timestamp()` instead, and
concluded: *"the 152 `datetime()` sites are a mechanical rename, not a blocker — the construct
that killed AGE."*

The same question was never asked of AGE. For Kuzu the audit looked for an equivalent and found
one; for AGE it stopped at *"`datetime()` unsupported"* and counted it toward elimination. **One
of AGE's two stated disqualifiers dissolves under the standard already applied to its
competitor.**

## What survives, and it is enough

**`MERGE … ON CREATE SET / ON MATCH SET` is a hard syntax error in AGE, and no rename fixes it.**
It is the core entity-anchoring pattern — the write path merges a node and branches on whether it
already existed. Emulating it means MATCH-then-branch or an SQL-side upsert at **every** anchoring
site: the "full query rewrite" the original audit described, which is real.

Kuzu supports it. That single construct — not `datetime()`, and not licensing or PG18 support,
both of which AGE has — is the whole difference.

**Verdict: AGE stays eliminated, now on `measured` basis rather than `audited`.** The conclusion
was right; one of its two reasons was not, and the register should say so.

## If the PO still wants AGE

It is one question, and it is now precisely located: **are ~19 + 14 anchoring sites worth
rewriting as MATCH-then-branch (or SQL upsert) to gain in-Postgres colocation?** That is a cost
decision with a known cost, not a capability unknown. The `datetime()` objection should be dropped
from the argument either way.

## Reproducing

```bash
docker run -d --name lw-age-probe -e POSTGRES_PASSWORD=agetest -e POSTGRES_USER=age \
  -e POSTGRES_DB=agetest -p 5599:5432 apache/age:latest
docker exec -i lw-age-probe psql -U age -d agetest <<'SQL'
LOAD 'age';
SET search_path = ag_catalog, "$user", public;
SELECT create_graph('probe');
SELECT * FROM cypher('probe', $$ MERGE (e:Entity {id:'e1'}) ON CREATE SET e.name='c' RETURN e.name $$) as (v agtype);
SELECT * FROM cypher('probe', $$ RETURN datetime() $$) as (v agtype);
SELECT * FROM cypher('probe', $$ RETURN timestamp() $$) as (v agtype);
SELECT * FROM cypher('probe', $$ MERGE (e:Entity {id:'ctl'}) RETURN e.id $$) as (v agtype);
SQL
docker rm -f lw-age-probe
```
