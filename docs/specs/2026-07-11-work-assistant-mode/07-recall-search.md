# 07 · Recall & Search — detailed design

**Date:** 2026-07-11 · **Phase:** P1 · **Status:** DESIGN · Implements **D1, D9, D16**.

---

## Q1. What must recall actually answer?

*"What did Alice say about the Q3 budget last month?"* — that single sentence needs **three** things the
platform did not have:

| Need | Status |
|---|---|
| The fact must **exist** with a speaker and a date | `statement` fact type + structured s/p/o + `event_date` — **net-new** ([`05`](05-work-capture-ontology.md) §Q2) |
| The fact must be **findable by entity** | ⚠️ **it wasn't** — see Q2 |
| The fact must be **filterable by date** | ⚠️ **it wasn't** — see Q2 |

## Q2. 🔴 The headline promise had no query that could answer it (T3)

**Verified.** With `valid_from_ordinal = NULL` (what v2 of the overview recommended):

- `_LIST_FACTS_FOR_ENTITY` filters `AND ($before_order IS NULL OR f.from_order <= $before_order)`. `NULL <= N`
  → **NULL → the row is dropped.** And `$before_order` is **never** None in production
  (*"ALWAYS an int (-1 when unknown) — NEVER None"*).
- `event_date_iso` on `:Fact` is a **sort** key, never a filter (`order_by_event_date` default `False`, no
  production caller passes `True`). The only date **filter** in the codebase is on `:Event`.
- The read also **requires** an `(:Fact)-[:ABOUT]->(:Entity)` edge — which `memory_remember` and the
  pending-facts confirm path **never create**.

**Net: every diary fact would be invisible, and the one surviving read (`list_facts_by_type`) is project-wide,
top-20-by-confidence, and completely date-blind.**

### The fix (D9)

1. **`valid_from_ordinal = days_since_epoch(entry_date)`, NOT NULL.** A diary is perfectly ordinal (one
   `primary` entry per day, strictly ordered). This restores every position-aware path *and* supersession —
   free.
2. **A date-filtered `:Fact` read** — mirror the `:Event` range predicate on `event_date_iso`. **Net-new.**
3. **The diary writer creates the `:ABOUT` edge.**

## Q3. `chat_search_sessions` — the honest week-1 story

Until entries accumulate, the KG is **structurally empty**. Day-1 recall is therefore **raw search over what
the user has told the assistant** — and that is a genuinely good product promise ("I remember everything
you've told me").

New chat-service MCP tool: owner-scoped cross-session search over `chat_messages`.

| Aspect | Decision |
|---|---|
| Scope | default `session_scope='assistant'`; `'all'` **only** from an assistant-bound session (enum'd closed set) |
| Owner filter | the **authenticated** user id — never caller-supplied |
| Injection | results are **capped excerpts wrapped as data-not-instructions** (the capture route's posture). S14 case: a searched-up message containing an instruction must **not** be followed |
| Index | `pg_trgm` + GIN trigram on `content` — the existing GIN is **English tsvector**, useless for VI/CJK. ⚠️ `CREATE EXTENSION` + the index go **outside** the main DDL string as best-effort calls, or a role without CREATE privilege **aborts the migration and chat-service won't start** (T31). No `CONCURRENTLY` inside the transactional migrator |
| Infra | chat-service is only an MCP **host** today — this means its **first MCP server** + an ai-gateway provider registration with a **policed `chat_` prefix** (unprefixed federation shadows tools). Count it in the estimate |

## Q4. 🔴 `memory_*` must not leak the diary (T40 / D16)

`memory_recall_entity` / `memory_timeline` pass `project_id=None` when a session has no linked project — and
the Cypher idiom `($project_id IS NULL OR x.project_id = $project_id)` means **ALL of the user's projects**.
`_GET_ENTITY_WITH_RELATIONS_CYPHER` has **no project filter at all**. `memory_forget` is user-wide by construction.

→ A **novel-writing session would surface the user's colleagues and work decisions.**

**Guards:** `memory_*` **requires an explicit project scope** for diary-tainted data (never the all-projects
fallback); `get_entity_with_relations` gains a project filter. Test: a non-assistant session returns **zero**
diary entities.

## Q5. Contradiction and correction (D17)

Recall is only as good as its ability to be **wrong and fixed**. Today: facts **accumulate** — "launch is
Friday" and "launch is Tuesday" both stay open, both returned; there is **no contradiction detection** in the
write path; `memory_forget` touches one Neo4j node and never PG, so a rebuild **resurrects** the correction;
and a rejected pending fact is a **hard DELETE with no tombstone** (re-proposable immediately).

→ Recall surfaces a **supersession** item ("Mon: Friday → Wed: Tuesday — which is right?") rather than two
independent facts, and says *"it changed"* rather than picking one. Correction goes through **D17's
three-legged write** (amend the entry → re-index → reconcile the graph).

## Q6. Acceptance

*"What did &lt;colleague&gt; **say** about &lt;topic&gt; last month?"* returns the right dated, attributed facts
(not just "decide") · a VI/CJK query matches (trigram, not tsvector) · a stored-injection message is not
followed · a **non-assistant session returns zero diary entities** · contradictory facts surface as a
supersession, not as two truths.
