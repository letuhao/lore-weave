# Apache AGE — the event writes are expressible. **`D-AGE-EVENT-WRITE-UNIMPLEMENTED` is refuted.**

**Date:** 2026-08-22 · **AGE 1.7.0 on PostgreSQL 18** (`loreweave/postgres-knowledge:18`, the
product's own image) · **Graph:** `probe_evt` / `probe_evt2`, created and dropped in the run —
the iso store, never dev.

> This is the second instalment of [`2026-08-11-age-construct-probe.md`](2026-08-11-age-construct-probe.md),
> and it finds the same defect one layer up. That probe replaced a version of itself which had
> tested **Neo4j syntax against AGE** and read the syntax errors as missing capability; the PO
> caught it — *"why did you use your syntax for AGE? you must use its syntax."* Its conclusion
> was: **AGE lives inside Postgres, so a Cypher construct's absence is not a capability gap when
> SQL supplies it.** `D-AGE-EVENT-WRITE-UNIMPLEMENTED` was written on **2026-08-14, three days
> later**, and reasons entirely inside Cypher.

## The claim under test

`D-AGE-EVENT-WRITE-UNIMPLEMENTED`, verbatim:

> `AgeGraphStore.merge_event` and `.update_event_fields` raise `NotImplementedError`. The merge
> needs an ON MATCH branch with min-wins `event_order`, union-merged participants and
> upgrade-not-overwrite `summary`; **AGE has no APOC-free equivalent of that CASE**, and
> `update_event_fields` needs the same-statement pre-edit `before` snapshot the OCC correction
> event is written from.

Its own *To unblock* already concedes half: *"the min/coalesce arithmetic is expressible; it is
the list union that needs care without APOC."*

## Result — all four requirements hold, none of them needs APOC

| requirement | form | verdict |
|---|---|---|
| min-wins `event_order` | plain AGE Cypher `CASE WHEN 300 < e.event_order THEN 300 ELSE e.event_order END` | ✅ `500 → 300` |
| upgrade-not-overwrite `summary` | plain AGE Cypher `CASE WHEN e.summary = '' THEN … ELSE e.summary END` | ✅ `"" → "a real summary"` |
| union-merged participants | SQL host: `jsonb_array_elements_text` ∪ incoming → `array_agg(DISTINCT …)` → bound parameter | ✅ `["a","b"] ∪ ["b","c"] = ["a","b","c"]` |
| pre-edit `before` snapshot | two statements, **one transaction** | ✅ `before="a real summary"`, `after="edited"` |

```
--- ON MATCH: min-wins order + upgrade-not-overwrite summary ---
 event_order |     summary
-------------+------------------
 300         | "a real summary"

--- AFTER: union-merged participants, no APOC, no duplicate b ---
  participants
-----------------
 ["a", "b", "c"]
```

### The one real gotcha, and it is a calling convention

The first attempt failed:

```
ERROR:  third argument of cypher function must be a parameter
```

`cypher(graph, query, params)` will not accept an inline expression as its third argument — the
parameter map must arrive as a **bound statement parameter**. That is a psql inconvenience and a
non-issue for the adapter: **asyncpg binds parameters natively**, so the production form is the
one that works. Re-run through `PREPARE`/`EXECUTE`, the union returns `["a","b","c"]`.

Worth carrying: the union is computed from the **stored** value read in the same transaction, not
from a value the caller guessed, so it is a genuine union rather than an overwrite with a
pre-merged list.

### The `before` snapshot — two statements, deliberately

[`2026-08-11`](2026-08-11-age-construct-probe.md)'s gotcha applies unchanged: folding a pre-read
and a write into one CTE has no guaranteed evaluation order in Postgres (it returned
`was_created = false` for an absent node). **Two statements in one transaction is the correct
form**, and it is what the OCC correction event needs — the deferral's phrase *"same-statement"*
is stricter than the requirement, which is *same-transaction*.

## What this changes

`D-AGE-EVENT-WRITE-UNIMPLEMENTED`'s **Blocker** is refuted; its **Mechanism** was sound and did
its job — the refusal is asserted by
`test_age_REFUSES_the_event_writes_rather_than_answering_wrongly`, so implementing these two
methods will fail that test and force the row to be revisited, exactly as designed.

Downstream, `T43`/`QC-7` recorded that **AGE cannot clear the conformance floor at all** because
it refuses two writes, and that a candidate refusing a write *"makes the floor unmeetable for
every read beneath it"*. That verdict rests on this deferral. It should be re-derived once the
two methods exist — not reversed from this document, which measures **expressibility**, not a
shipped adapter.

**This does not by itself unblock T17 class (d).** Those 34 modules need port *operations*; this
is about two adapter methods. What it does establish is the method that prices class (d)
honestly: reach for the SQL host before concluding AGE cannot express something.

## Reproducing

```bash
docker exec -i lw-iso-knowledge-pg-1 psql -U loreweave -d loreweave_knowledge_vectors <<'SQL'
LOAD 'age'; SET search_path = ag_catalog, "$user", public;
SELECT create_graph('probe_evt2');
SELECT * FROM cypher('probe_evt2', $$ CREATE (e:Event {id:'ev1', participants:['a','b']})
  RETURN e.id $$) AS (id agtype);
PREPARE setp(agtype) AS SELECT * FROM cypher('probe_evt2', $$
  MATCH (e:Event {id:'ev1'}) SET e.participants = $u RETURN e.participants $$, $1)
  AS (participants agtype);
EXECUTE setp('{"u": ["a","b","c"]}');       -- the union is computed in SQL, bound here
SELECT drop_graph('probe_evt2', true);
SQL
```
