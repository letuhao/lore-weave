# D-MEMORY-FACT-STORED-UNSCOPED — a turn's project is never resolved from its book

**Status:** proposal. Investigated 2026-08-14, not yet implemented.

---

## The symptom

A live turn on a book-bound session, K=1, fixture kept so the store could be read before teardown:

```
user:  "Remember this for later: Mira Solene is secretly the Pale Regent's daughter."
tool:  memory_remember  ->  {"remembered": true, "fact_id": "790d92aa…", "confidence": 0.7}
```

The fact is genuinely stored — verified by querying Neo4j directly, the sentence is there. But:

```cypher
MATCH (f:Fact) WHERE f.content CONTAINS 'Pale Regent' RETURN f.project_id
-> NULL
```

And across the whole graph, **339 of 343 Fact nodes carry a `project_id`.** This one is among
the four that do not. A fact stored unscoped is invisible to project-scoped recall, so the user
is told it was remembered and can never be told it again.

The same batch demonstrates the other half of that sentence. Asked *"What do we know about Mira
Solene so far?"*, the reply was **"I don't have any information about Mira Solene"** — while the
glossary held her and a fact about her had just been written.

## The root cause

`project_id` for a turn is read from exactly one place:

```python
# stream_service.py, ~6884
project_id = session_row.get("project_id") if session_row else None
```

`book_id`, ten lines earlier, has a four-step fallback chain — `editor_context` → `book_context`
→ `studio_context` → `session_row.book_id`. Its sibling has none.

From there the consequence is mechanical: no `project_id` → chat-service sends no `X-Project-Id`
header → knowledge-service's `_build_tool_context` reads that header and only that header, so
`ctx.project_id` is `None` → `_handle_memory_remember` computes
`project_id = str(ctx.project_id) if ctx.project_id else None` → `merge_fact(project_id=None)`.

Every step is locally correct. Nothing in the chain is accountable for whether the turn's project
could have been resolved.

## The blast radius, measured

```
1417  chat sessions
 503  bound to a book
 113  carry a project_id
 417  have a book and NO project        <- 83% of book-bound sessions
 448  composition_work rows DO have a resolvable project_id
```

On those 417 sessions, **every tool declaring `ambient_project` is told the project is absent** —
the memory tools, the kg tools, `story_search`. They do not fail; they silently degrade to
unscoped or empty. That is the shape this loop keeps finding: a surface that cannot answer,
answering anyway.

## The invariant

> **An id the platform can resolve from the turn's own context must be resolved before a tool is
> told it is absent** — the same guarantee `book_id` already has.

## The proposed fix

One chokepoint: the single place `project_id` is derived. Give it the chain its sibling has.

```
1.  session_row.project_id                     (today's only source)
2.  studio_context.project_id                  (see below — already read, never used here)
3.  the book's project, from the kg-state probe (see below — already fetched every turn)
4.  else None                                  (fail closed, exactly as today)
```

**Step 2 is already read and discarded.** `_ctx_project_id = (studio_context or {}).get("project_id")`
exists today and is used *only* to write the project id into the model's prose note — "This book's
composition/knowledge project is project_id=…". The turn tells the MODEL the id and does not put
it in its own envelope. That inconsistency is the smell that led here.

**Step 3 costs nothing.** `book_state_probe._connections()` already calls
`GET /internal/books/{book_id}/kg-state` **once per chat turn**, and that endpoint's response
carries `project_id`. The current code reads `entity_count` off it and throws the rest away:

```python
d = await _get_json(..., f"/internal/books/{book_id}/kg-state")
if not d.get("has_projection"):
    return 0
n = d.get("entity_count")     # project_id is right there, unused
```

So the fix adds no service call, no new dependency, and no hot-path cost — it uses a value the
turn has already paid for.

## Why it is safe

* It only fires when the turn **has a book**, and resolves to **that same book's** project. There
  is no cross-scope redirect — the failure mode of a bad id-repair, and the reason
  `_inject_context_ids` refuses to touch a valid-but-unknown UUID.
* A session deliberately not book-bound is untouched: step 3 needs a `book_id` to fire.
* A book with no knowledge project still yields `None` and every tool fails closed exactly as it
  does today. `kg-state` returns 200 with `has_projection: false` for that case by design, so
  cold-start stays a normal state rather than an error.

## The falsifier

> On a book-bound session whose `chat_sessions.project_id` is NULL, `memory_remember` must store
> a fact carrying **that book's** project_id, and `memory_search` on the same session must then
> find it.
>
> Today: stored NULL, and not found.

Measured, not asserted: read `f.project_id` from Neo4j for the fact the turn writes, and re-ask
in the same session. The count-based store diff **cannot** settle this on its own — `merge_fact`
merges by content, so re-remembering the same sentence is idempotent and a count cannot separate
"merged into an existing node" from "wrote nothing". The property to check is the project on the
node, not the number of nodes.

## What this does NOT claim

It does not explain `memory_recall_entity` being surfaced 0/3 — that is a declaration miss ("what
do we know about" is `memory_search`'s phrase, not its own) and belongs to R2, not here. The two
compound in the same reply, and they are separate defects.
