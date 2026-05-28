---
name: KNOWLEDGE_SERVICE_K21A_DESIGN
description: Phase K21 Cycle A design — knowledge-service memory tools (definitions + executor + internal /tools/execute endpoint + guardrails + metrics)
type: design
---

# Phase K21-A — Tool Calling: knowledge-service memory tools

> **Status:** DESIGN (2026-05-17, session 57 cycle 13)
> **Authorized by:** PO at CLARIFY — K21 sliced into 3 cycles (A: knowledge-service tools · B: chat-service loop · C: frontend); all 5 tools with guardrails in scope.
> **Closes-on-BUILD:** the knowledge-service slice of [`KNOWLEDGE_SERVICE_TRACK3_IMPLEMENTATION.md`](./KNOWLEDGE_SERVICE_TRACK3_IMPLEMENTATION.md#L1256) Phase K21 — tasks K21.1, K21.2, K21.3, K21.7, K21.8.
> **Size:** L (≈8 files: 4 new prod + 1-2 mod + 3 test).

---

## 1. Scope

**Cycle A — knowledge-service only.** Builds the memory-tool surface so a future
chat-service tool-calling loop (Cycle B) has something to call.

| In scope (Cycle A) | Task |
|---|---|
| 5 tool JSON schemas (OpenAI function-calling format) | K21.1 |
| Tool executor — dispatch + 5 handlers | K21.2 |
| `POST /internal/tools/execute` endpoint | K21.3 |
| `memory_remember` guardrails — confidence, source tag, rate limit | K21.7 (safeguards 1–3) |
| Tool-call metrics | K21.8 |

**NOT in Cycle A:** the chat-service tool-calling loop (K21.4/6/10/11 → Cycle B),
the FE indicator + opt-out toggle (K21.5/12 → Cycle C), and `memory_remember`'s
**user-confirmation** safeguard (K21.7 safeguard 4) — confirmation is inherently
interactive and belongs with the Cycle B chat loop. The `tool_calling_enabled`
project setting (K21.12) lands in Cycle B alongside its chat-service consumer.

---

## 2. What already exists (audit, 2026-05-17)

- **The LLM gateway already supports tool-calling.** [`loreweave_llm` `StreamRequest`](../../sdks/python/loreweave_llm/models.py) carries `tools` + `tool_choice`; `ToolCallEvent` is a first-class stream event; the gateway rejects tools for non-supporting providers (`LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER`). **This benefits Cycle B, not A** — but it means K21's plan note "use LiteLLM's function_calling" is obsolete (LiteLLM was retired in the Phase 4-6 refactor).
- **Every executor target exists** as a repo function:
  - `memory_search` → `find_passages_by_vector` ([passages.py:333](../../services/knowledge-service/app/db/neo4j_repos/passages.py#L333)) — takes a **pre-embedded vector**, so the executor must embed the query first (mirrors `drawers.py`).
  - `memory_recall_entity` → `find_entities_by_name` ([entities.py:624](../../services/knowledge-service/app/db/neo4j_repos/entities.py#L624)) then `get_entity_with_relations` ([entities.py:1458](../../services/knowledge-service/app/db/neo4j_repos/entities.py#L1458)).
  - `memory_timeline` → `list_events_filtered` ([events.py:539](../../services/knowledge-service/app/db/neo4j_repos/events.py#L539)).
  - `memory_remember` → `merge_fact` ([facts.py:165](../../services/knowledge-service/app/db/neo4j_repos/facts.py#L165)).
  - `memory_forget` → `invalidate_fact` ([facts.py:326](../../services/knowledge-service/app/db/neo4j_repos/facts.py#L326)).
- **Internal-auth pattern:** `require_internal_token` ([internal_auth.py:8](../../services/knowledge-service/app/middleware/internal_auth.py#L8)); internal routers are flat `app/routers/internal_*.py` files.
- `merge_fact`'s `source_type` is a free Neo4j list property — **no CHECK constraint**, so `source_type='llm_tool_call'` needs no migration.
- `FACT_TYPES` is a closed `Literal` — `decision · preference · milestone · negation`.

---

## 3. Decisions

### D1 — Module layout

NEW `app/tools/__init__.py`, `app/tools/definitions.py`, `app/tools/executor.py`;
NEW `app/routers/internal_tools.py`. The K21 plan's `app/api/internal/tools.py`
path is **stale** — every internal router lives at `app/routers/internal_*.py`
(`internal_summarize.py`'s own docstring records this exact deviation). Follow
the established convention.

### D2 — `memory_search` replicates the embed flow; `drawers.py` untouched

`memory_search` needs the same embed-query → `find_passages_by_vector` flow as
`drawers.py`. Two options:
- **A** — extract a shared `search_project_passages` service; both call it.
- **B** — the executor replicates the ≈30-line embed flow.

**Decision: B.** The PO sliced K21 into 3 cycles for bounded blast radius;
refactoring the tested K19e `drawers.py` is a separate concern, not a K21 task.
The drawer router's flow is tangled with HTTP specifics (HTTPException 404/502,
response models, facet counts); the executor needs a *different* shape (tool
JSON, never raises). Cycle A stays purely additive. The duplication is logged
as **D-K21A-01** (DRY the embed→vector-search flow) so it is tracked, not lost.

### D3 — `project_id` / `user_id` come from the request envelope, NOT the LLM

The LLM-facing tool schemas expose **only** semantic args (`query`,
`entity_name`, `fact_text`, …). `user_id`, `project_id`, and `session_id` are
supplied by chat-service in the `/internal/tools/execute` envelope and merged in
by the executor. Rationale: the LLM operates within the current chat's project;
letting it pass `project_id`/`user_id` is a needless cross-tenant surface. This
deviates from the plan's schemas (which listed `project_id`/`user_id` as tool
params) — the deviation is deliberate and safer.

**Null project scope** (REVIEW-DESIGN R1) — a chat can have no project
(`project_id` null in the envelope). Per-tool behaviour: `memory_recall_entity`
and `memory_timeline` run cross-project — the repos already treat
`project_id=None` as "all projects + global"; `memory_remember` / `memory_forget`
operate on the user namespace and accept a null project; `memory_search` returns
a `tool_error` ("a project must be in scope to search passages") because
`:Passage` nodes are strictly project-scoped — there is nothing to search.

### D4 — `memory_recall_entity` / `memory_timeline` take entity **names**, not ids

The LLM knows entity *names* ("Kai"), not hash ids. `memory_recall_entity`
resolves `entity_name` via `find_entities_by_name` (matches canonical form +
aliases, pre-ranked), takes the top match → `get_entity_with_relations`. When
>1 entity matches, the result lists the other names so the LLM can disambiguate.
No match → `{found: false}`. `memory_timeline`'s optional `entity_name` resolves
the same way → the entity's `{name, canonical_name, *aliases}` set is passed as
`participant_candidates` (mirrors the C10 timeline router).

### D5 — `memory_remember` guardrails (K21.7 safeguards 1–3)

- `confidence = 0.7` (hardcoded for tool-origin facts; below Pass 2's 0.9 and
  below the L2 loader's default `min_confidence=0.8` — so a tool-written fact
  never silently enters RAG context, only the Entities/Quarantine tab).
- `source_type = 'llm_tool_call'`, `pending_validation = false`.
- **Rate limit:** max 10 `memory_remember` calls per chat session. A Redis
  counter keyed `k21:remember:{session_id}` (INCR + 24h TTL) — `session_id`
  comes from the envelope. **Fail-open:** if Redis is unavailable the call is
  allowed with a WARNING log — the limit is pollution-prevention, not a security
  boundary, and a Redis hiccup must not break chat. Rejection increments
  `knowledge_memory_remember_rate_limited_total`.
- Safeguard 4 (opt-in user confirmation) is **deferred to Cycle B** — it needs
  the interactive chat loop.

### D6 — Internal endpoint contract

`POST /internal/tools/execute`, gated by `require_internal_token`.
Body: `{user_id: UUID, project_id: UUID|null, session_id: str, tool_name: str, tool_args: dict}`
— `session_id` is a required non-empty string (Pydantic `min_length=1`);
chat-service always supplies the active chat session id, which keys the
`memory_remember` rate limiter (D5) (REVIEW-DESIGN R2).
Response: **always 200** with `{success: bool, result: dict|null, error: str|null}`
(the always-200-with-status envelope, matching `internal_summarize.py`). `user_id`
is trusted from the body — there is no end-user JWT on an S2S endpoint; chat-service
passes the id it authenticated (same trust model as `internal_summarize`).

### D7 — Result size caps

Tool results feed back into the LLM's context, so each handler caps output:
`memory_search` `limit ≤ 20` (default 10) + per-passage text truncation (≈500
chars); `memory_recall_entity` uses the existing `rel_cap`; `memory_timeline`
`limit ≤ 50` (default 20). Caps are asserted by tests.

### D8 — Metrics (K21.8)

Process-local Prometheus counters (mirroring the existing service pattern):
`knowledge_tool_calls_total{tool_name, outcome}`,
`knowledge_tool_call_duration_seconds{tool_name}`,
`knowledge_tool_call_result_size_bytes{tool_name}`,
`knowledge_memory_remember_rate_limited_total`. `outcome ∈ {ok, tool_error, infra_error}`.

### D9 — Error wrapping

A tool failure (bad args, repo `ValueError`, entity/fact not found) returns
`{success: false, error: "..."}` at HTTP 200 — never an exception. Only an
infrastructure failure (Neo4j/Redis pool down) raises `503`. This is the plan's
"tool failure doesn't crash chat" AC, enforced at the knowledge-service edge.

---

## 4. Tool schemas (K21.1)

OpenAI function-calling format. `project_id`/`user_id`/`session_id` are NOT in
any schema (D3).

| Tool | LLM-facing params |
|---|---|
| `memory_search` | `query` (str, req), `limit` (int 1-20, def 10), `source_type` (enum chapter/chat/glossary, opt) |
| `memory_recall_entity` | `entity_name` (str, req) |
| `memory_timeline` | `from_date` (str ISO, opt), `to_date` (str ISO, opt), `entity_name` (str, opt), `limit` (int 1-50, def 20) |
| `memory_remember` | `fact_text` (str, req), `fact_type` (enum decision/preference/milestone/negation, req) |
| `memory_forget` | `fact_id` (str, req) |

Note — `memory_forget` needs a `fact_id` the LLM can only have learned from a
prior `memory_remember` result (which returns the new `fact_id`). Surfacing
facts from the read tools is a candidate enhancement, logged as **D-K21A-02**.

---

## 5. Executor design (K21.2)

`executor.py` exposes `execute_tool(tool_name, envelope, tool_args, *, deps) -> ToolResult`.
A dispatch dict maps `tool_name` → handler. Each handler:
1. Validates `tool_args` against a per-tool Pydantic arg model (unknown/invalid → `tool_error`).
2. Opens an `async with neo4j_session()` (and embeds via `EmbeddingClient` for `memory_search`).
3. Calls the repo function, caps the result (D7), returns a plain `dict`.
4. Metrics (D8) + error wrapping (D9) are applied by a shared wrapper, not per handler.

---

## 6. Test plan

- **definitions** — all 5 schemas validate as JSON Schema; enum values match `FACT_TYPES` / source types; no `project_id`/`user_id` leaked into any schema (D3 lock).
- **executor** — each tool: happy path + `tool_error` path (bad args, entity/fact not found); `memory_search` not-indexed + dim-mismatch branches; `memory_remember` writes `confidence=0.7` + `source_type='llm_tool_call'` (asserted on the returned Fact); rate-limit — the 11th `memory_remember` in a session is rejected; rate-limit fail-open when the Redis stub raises.
- **internal endpoint** — 401 without `X-Internal-Token`; each `tool_name` routes; `503` on infra failure; success + error envelopes; unknown `tool_name` → `tool_error`.

---

## 7. Files

**NEW:** `app/tools/__init__.py`, `app/tools/definitions.py`, `app/tools/executor.py`,
`app/routers/internal_tools.py`; `tests/unit/test_tool_definitions.py`,
`tests/unit/test_tool_executor.py`, `tests/integration/test_internal_tools.py`.
**MOD:** `app/main.py` (register `internal_tools.router`), `app/deps.py` (executor
deps if needed), `app/config.py` (rate-limit constant).

---

## 8. Deferred / out of scope

| ID | Note | Target |
|---|---|---|
| D-K21A-01 | DRY the embed→vector-search flow shared by `drawers.py` + `memory_search` (D2). | knowledge-service cleanup cycle |
| D-K21A-02 | Read tools don't surface `fact_id`s, so `memory_forget` is only usable on facts the LLM itself just wrote. Consider returning facts from `memory_recall_entity`. | K21 Cycle B/C or follow-up |
| — | `memory_search` embedding calls don't count toward the K16.11 monthly budget — identical to the existing **D-K19e-γa-02** (drawer search). Not solved here. | (tracked by D-K19e-γa-02) |
| K21.7 safeguard 4 | `memory_remember` opt-in user confirmation — needs the interactive chat loop. | K21 Cycle B |
| K21.12 | `tool_calling_enabled` project setting. | K21 Cycle B (BE) + C (toggle) |
