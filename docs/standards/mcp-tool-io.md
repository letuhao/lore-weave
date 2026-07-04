# MCP Tool I/O Standard

**Status:** ACTIVE (consolidation of previously-fragmented rules) · **Date:** 2026-07-04
**Governs:** how every MCP tool an LLM can call defines its **inputs** (so a weak model uses it correctly, with few errors) and shapes its **outputs** (right-sized for the agent, no context bloat). Indexed in [`docs/standards/README.md`](./README.md).

> **Why this exists.** These rules were scattered across four places (Frontend-Tool Contract, the knowledge "4-source discipline", the DRAFT Context Budget Law §6, and the deferred `llm-client-first` memory). An agent building a new MCP tool had to reassemble them and usually missed one — the recurring source of tool-call errors and context bloat. This is now the single source. It **links to the enforcing tests/lints** rather than restating them.

**Applies to:** every tool an LLM invokes — domain MCP tools (knowledge/glossary/composition/… exposed via `ai-gateway` federation), and **frontend tools** (agent→GUI: `ui_open_studio_panel`, `propose_edit`, `confirm_action`, …). Non-agentic LLM *pipelines* (translation, enrichment) are exempt on the input side but still follow the output-serialization rules when they return tool-shaped data.

**The failure mode it defends against:** the tool is a contract joined only by the LLM — often a **weak local model** (LM Studio gemma/qwen). A drift, a free-string arg it guesses wrong, a silent no-op, or a 40K-token dump each passes every isolated unit test yet kills the live loop or blows the budget.

---

## Part 1 — INPUT rules (define the tool so a weak model calls it right)

### IN-1 · Identity & scope come from the envelope, never from LLM args
`user_id` / `session_id` (and the auth principal) are injected from MCP context headers (`X-User-Id`, internal token, admin RS256), **never** tool arguments. Arg models forbid them (`extra="forbid"` rejects a smuggled `user_id`). *(INV-K2, design D3; enforced by `services/knowledge-service/tests/test_mcp_contract.py`.)*

### IN-2 · Pass scope explicitly when the gateway drops the envelope
The `ai-gateway` MCP federation **drops `X-Project-Id`** (memory `gateway-drops-xprojectid-envelope`). So a project-scoped tool takes `project_id` (and a world/multi tool takes `world_id` / `project_ids`) as an **explicit, ownership-checked arg**, not an ambient envelope value. The owner gate confines it to the caller's own resources; a public MCP-key call is owned-only (OD-8).

### IN-3 · A finite value set is an `enum`, never a bare `string`
Any arg whose valid values are a closed, code-known set (panel ids, modes, domains, operations, kinds, `unify` modes) **must** declare `enum` in the machine-readable schema. An enum pins the value AND reinforces the arg name for weak models. Register it in **`CLOSED_SET_ARGS`** (`test_mcp_server.py` for domain tools; `test_frontend_tools_contract.py` for frontend tools) with the value-set it must cover (`CLOSED_SET_VALUES`) — enum *presence* alone lets a silently dropped value ship.

### IN-4 · Constraints live in the machine-readable schema, not only in prose
Bounds and shapes a model should see up front — `minimum`/`maximum`, `minItems`/`maxItems`, `enum`, array `items` — go in the JSON schema, not just the description or the pydantic `Field`. *(review-impl finding #1: a 1..16 list bound existed only in prose + the model-layer `ValidationError`; the model never saw it. Now asserted by `test_kg_multi_query_advertises_project_ids_bounds`.)*

### IN-5 · Reject smuggled scope; tolerate a harmless extra
Two different needs, don't conflate them:
- **Identity/scope smuggling** (`user_id`, `session_id`, a scope override) → **reject** (`extra="forbid"`).
- A **harmless extra property** a weak model hallucinates on an otherwise-valid call → **tolerate/ignore, don't hard-fail**. The Go MCP SDK infers `additionalProperties:false` on every struct, so a stray field 409'd a valid call (W0 soak: gemma's `old_value` killed `glossary_book_patch`). Fixed via `relaxAdditionalProps` — opens `additionalProperties` on *model-constructed object/array* schemas while **enums stay strict**. Net rule: strict on the closed sets and identity; lenient on unknown leaf properties.

### IN-6 · Errors are self-correcting one-liners, never raw dumps or 5xx
A validation failure must reach the model as **one actionable line** (arg name + what was expected + what was sent + "fix and call again"), not the multi-line `errors.pydantic.dev` dump. A tool-level rejection returns `success=False` with an `error` string — **not** a 500 — so the loop can tell "tool refused, self-correct" from "backend down". *(Enforced by `_validation_directive` + `_install_validation_error_rewriter` in `services/knowledge-service/app/mcp/server.py`; `execute_tool` maps `ValidationError`/`ToolExecutionError` → `success=False`.)*

### IN-7 · One name for one concept across all tools
Don't let `panel` / `page` / `panel_id` mean the same thing in three tools — that collision is what confused the model into `panel:"editor"` against a resolver that silently no-op'd (fixed f1f9e9966). Rename to a single canonical arg name; an alias is a band-aid, not the fix.

### IN-8 · A schema change touches ALL sources + a drift test (the 4-source discipline)
A domain KG/memory MCP tool's schema is duplicated across **four** artifacts that MUST move in lockstep, or a weak model silently loses an arg:
1. the pydantic **arg model** (`ARG_MODELS`, `extra="forbid"`),
2. the hand-written **JSON schema** (`TOOL_DEFINITIONS`),
3. the **FastMCP signature** (`app/mcp/server.py`) — it **advertises + validates + STRIPS** any arg not present in the signature,
4. the committed **snapshot + mirror test** (`test_mcp_server.py`, `test_graph_schema_tools.py`).

Change one → update all four → run the drift tests (they go red on divergence). Frontend tools have the analogous 2-source pair (BE `frontend_tools.py` schema + FE resolver) joined by `contracts/frontend-tools.contract.json`; regenerate with `WRITE_FRONTEND_CONTRACT=1 pytest`.

---

## Part 2 — OUTPUT rules (right-sized for the agent, no context bloat)

The design authority for output sizing is the [Context Budget Law §6](../specs/2026-07-03-context-budget-law.md) (L1/L2/L3). Restated here as the tool-edge rules every tool return obeys:

### OUT-1 · Reference-first, content-on-demand (L1)
A tool that returns a **set** returns `{id, title, ≤1-line, version}` per item by default; the full body comes from a `get_by_id`-style tool. **Exemption:** an inherently-small return (a status, a count, a single ≤N-byte item) annotates `@small_return`; the exemption is honesty-checked by the contract-snapshot test, not assumed. *(The 146K-token turn was one `composition_list_outline` dumping every scene synopsis because there was no cheap single-node read — the canonical L1 violation.)*

### OUT-2 · Field selection + detail levels + limit (L2)
A tool returning rich objects offers a detail selector (e.g. `detail: "summary" | "full"`) and honors a `limit`. Default to the smaller shape. Don't return internal/debug fields the agent can't act on.

### OUT-3 · Concise wire (L3) — the one-helper rule
Every tool-result serialization goes through the **single** `_tool_result_content` helper: `ensure_ascii=False` (a raw `json.dumps` default-`True` inflates Vietnamese/CJK 2–3× via `\uXXXX`) + **drop empty/null** fields. Never hand-roll `json.dumps` at a tool-result site. *(Enforced by `scripts/context-budget-l3-lint.py`.)*

### OUT-4 · Success is a bare payload; error is `{success:false, error}`
On success the tool returns its **payload directly** (no top-level `success:true` wrapper); a failure returns `{"success": false, "error": "<one line>"}`. The MCP client discriminates on the absence/presence of the `success` key. *(Enforced by `test_mcp_contract.py` success-discrimination.)*

### OUT-5 · Never silently truncate — report the cap
If a return is bounded (top-N, node cap, spend cap, oversample, sampling), the result MUST carry an honest partiality flag the agent can read: `node_cap_hit`, `unify_capped`, `unify_embed_skipped`, `partitions_unreadable`, `has_more`, etc. A silent truncation reads to the agent as "this is everything" when it isn't.

### OUT-6 · No data-bearing frontend tools
A frontend (agent→GUI) tool carries **intent**, not data. It never returns domain data for the agent to persist; the reconciler reloads the SSOT from the domain API. *(Agent GUI Reconciliation spec 09.)*

---

## Part 3 — VERIFY by EFFECT, not by tool-call

A raw-stream smoke that sees `TOOL_CALL_START` / `RUN_FINISHED{suspended}` only proves the model *called* the tool — it never runs the resolver/handler. Prove the loop by its **effect**:
- Domain tool → a **live cross-service call** on a rebuilt stack (or a real-DB/Neo4j integration test) asserting the effect landed.
- Frontend tool → a **live browser smoke** (the GUI actually reacted) or its deterministic form (inject a suspended tool-call, assert the host effect).

*(Memories `agent-gui-loop-needs-live-browser-smoke-not-raw-stream`, `new-cross-service-contract-needs-consumer-live-smoke`.)*

---

## Enforcement — current & required

**Enforced today:**

| Rule | Gate |
|---|---|
| IN-1 identity-from-headers · OUT-4 success-discrimination | `services/knowledge-service/tests/test_mcp_contract.py` |
| IN-3 closed-set⇒enum (+ value-set coverage) | `CLOSED_SET_ARGS`/`CLOSED_SET_VALUES` in `test_mcp_server.py` + `test_frontend_tools_contract.py` |
| IN-4 bounds-in-schema | per-tool schema tests (e.g. `test_kg_multi_query_advertises_project_ids_bounds`) |
| IN-6 self-correcting errors | `_validation_directive` + rewriter, exercised in `test_mcp_server.py` |
| IN-8 4-source drift | `test_mcp_server.py` (FastMCP `tools/list` == expected) + `test_graph_schema_tools.py` (schema⇄arg-model) |
| Frontend-tool contract (IN-3/IN-7/OUT-6) | `test_frontend_tools_contract.py` (BE) · `frontendToolContract.test.ts` (FE, proves each resolver reads every required arg + rejects with an error) · `panelCatalogContract.test.ts` |
| OUT-3 concise-wire | `scripts/context-budget-l3-lint.py` |

**Not yet enforced (tracked gaps — candidate work):**
1. **No cross-service "MCP-tool lint"** that fails a *new* tool for: a bare-`string` arg whose description enumerates a finite set (IN-3), a set-returning tool with no `get_by_id` sibling and no `@small_return` (OUT-1), or a tool-result site bypassing `_tool_result_content` in a service the L3 lint doesn't yet cover. Today these are caught per-tool by hand-written tests, so a tool with no test slips.
2. **OUT-1/OUT-2 have no repo-wide contract-snapshot harness yet** — the Context Budget Law §6b names it as planned (per-tool return-shape snapshot + `@small_return` honesty check). Until it lands, reference-first is convention on new tools.
3. The IN-8 drift-lock exists for the **knowledge** MCP surface; the same discipline for glossary/composition/other domain surfaces is per-service and uneven.

---

## Checklist — building a new MCP tool

- [ ] Identity/scope from the envelope; `project_id`/`world_id`/`project_ids` explicit if project-scoped (IN-1, IN-2)
- [ ] Every finite-set arg is an `enum`, registered in `CLOSED_SET_ARGS` with its value-set (IN-3)
- [ ] Bounds/`minItems`/`maxItems`/`items` in the JSON schema, not just prose (IN-4)
- [ ] `extra="forbid"` for identity; harmless extras tolerated, enums strict (IN-5)
- [ ] Rejections are one-line directives, `success=False` not 5xx (IN-6)
- [ ] Arg names are canonical (one-name-one-concept) (IN-7)
- [ ] All schema sources updated + drift test green (IN-8)
- [ ] Set returns are reference-first (or `@small_return`) (OUT-1); detail/limit offered (OUT-2)
- [ ] Serialized through `_tool_result_content` (OUT-3); success = bare payload (OUT-4)
- [ ] Bounded returns carry a partiality flag (OUT-5); frontend tools carry intent only (OUT-6)
- [ ] Proven by **effect** — live cross-service / real-DB / browser smoke (Part 3)
