# MCP Tool I/O Standard


**Status:** ACTIVE (consolidation of previously-fragmented rules) · **Date:** 2026-07-04
**Governs:** how every MCP tool an LLM can call defines its **inputs** (so a weak model uses it correctly, with few errors) and shapes its **outputs** (right-sized for the agent, no context bloat). Indexed in [`docs/standards/README.md`](./README.md).

> **Why this exists.** These rules were scattered across four places (Frontend-Tool Contract, the knowledge "4-source discipline", the DRAFT Context Budget Law §6, and the deferred `llm-client-first` memory). An agent building a new MCP tool had to reassemble them and usually missed one — the recurring source of tool-call errors and context bloat. This is now the single source. It **links to the enforcing tests/lints** rather than restating them.

**Applies to:** every tool an LLM invokes — domain MCP tools (knowledge/glossary/composition/… exposed via `ai-gateway` federation), and **frontend tools** (agent→GUI — the three chat-service *intercepts*: `confirm_action`, `glossary_confirm_action`, `glossary_propose_entity_edit`. ⚠ `propose_edit` and the `ui_*` family became **ai-gateway consumer-local** tools on 2026-07-20 and `ui_*` is de-advertised; this line named them as frontend tools until 2026-09-03). Non-agentic LLM *pipelines* (translation, enrichment) are exempt on the input side but still follow the output-serialization rules when they return tool-shaped data.

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
- **Python:** `loreweave_mcp` has no schema-level `additionalProperties` knob (Pydantic, not a JSON-Schema-first kit), so the port is at the model layer — `TolerantArgs` (`sdks/python/loreweave_mcp/errors.py`, `extra="ignore"`), a sibling to `ForbidExtra` (`extra="forbid"`). Same never-declare-identity rule either way; pick `TolerantArgs` for a tool a weak model calls often (first adopted 2026-07-05 by composition-service's `composition_authoring_run_*` family). This was a real, previously-undocumented gap in the Python kit — every existing Python MCP tool used `ForbidExtra` exclusively before this.

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

Change one → update all four → run the drift tests (they go red on divergence). Browser-executed tools have the analogous pair (ai-gateway TS schema + FE resolver) joined by `contracts/browser-tools.contract.json`. **The contract is edited BY HAND.** Its generator regenerated from `chat-service/app/services/frontend_tools.py`, deleted 2026-09-03 with architecture v1; `WRITE_FRONTEND_CONTRACT=1` now raises, because its only remaining input was a frozen test copy and writing from it would have overwritten the SoT with retired shapes. **For the tools that moved to ai-gateway (`propose_edit`, `ui_*`) it is a THREE-source edit**, not two: the contract stays the SoT, and ai-gateway commits a machine-checked TS mirror (`src/mcp/ui-tools.ts` `STUDIO_PANEL_IDS`, drift-tested by `test/ui-tools.spec.ts`) because the image cannot read the repo-root contract at runtime. *(Third source added to this rule 2026-09-03; an author following the 2-source version updated one of two live mirrors.)*

---

## Part 2 — OUTPUT rules (right-sized for the agent, no context bloat)

The design authority for output sizing is the [Context Budget Law §6](../specs/2026-07-03-context-budget-law.md) (L1/L2/L3). Restated here as the tool-edge rules every tool return obeys:

### OUT-1 · Reference-first, content-on-demand (L1)
A tool that returns a **set** returns `{id, title, ≤1-line, version}` per item by default; the full body comes from a `get_by_id`-style tool. **Exemption:** an inherently-small return (a status, a count, a single ≤N-byte item) annotates `@small_return`; the exemption is honesty-checked by the contract-snapshot test, not assumed. *(The 146K-token turn was one `composition_list_outline` dumping every scene synopsis because there was no cheap single-node read — the canonical L1 violation.)*

### OUT-2 · Field selection + detail levels + limit (L2)
A tool returning rich objects offers a detail selector (e.g. `detail: "summary" | "full"`) and honors a `limit`. **Default to the smaller shape** — `detail=summary` AND a small page `limit`, both at once (they compound). `detail=full` and a larger `limit` are explicit opt-ins the caller narrows *up* to, never the default a "what's running" call is handed. Don't return internal/debug fields the agent can't act on.

> **Versioned-default migration — status (K24, 2026-07-24).** T1's transitional rule ("compiler passes `summary`, federated keep `full`") was a *migration state*, not a permanent carve-out — it protected federated consumers *while the shape settled*. That migration is now COMPLETE for `jobs_list` (the measured worst case: a no-arg call was **45.6 KB at `detail=full` × the shared 50-row limit** — 5.7× the 8 KB context-budget warning). It now defaults to `summary` + a small MCP-only `limit` (the shared REST limit stays 50), with `detail=full` kept as an explicit opt-in so the "consumer can still get `full`" criterion holds. **The party OUT-2 protects — the context-constrained agent — IS the federated caller**, so "federated keep full" was handing the heavy shape to exactly whom the Law exists to shield. New/federated list tools follow `jobs_list`: summary + small limit by default. Enforce it per-tool with a **default-reply byte-budget test** (see `services/jobs-service/tests/test_mcp_server.py::test_jobs_list_default_reply_fits_the_context_budget` — seed >1 page of fat rows, call with no args, assert the reply `< result_warn_bytes()`; it reds if either default regresses). This is the first landing of §6b's planned `@small_return` honesty check.

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

## Part 4 — Catalog hygiene: consolidation, visibility & batch

At ~150-160 federated tools, how tools are *composed and exposed as a set* matters as much as any single tool's shape. These rules govern merging/deprecating/batching tools; they don't replace Parts 1-3, they compose with them. *(Origin: `docs/specs/2026-07-06-tool-catalog-simplification.md`, grounded in a live measured bug — a book-scoped surface paying a flat ~24K-token tool-schema tax from whole-domain hot-seeding — and cross-checked against external practice: Anthropic's own "writing tools for agents" guidance, the STRAP/Six-Tool consolidation patterns, RAG-MCP's finding that tool-selection accuracy degrades as action-enum tools grow branchier.)*

### CAT-1 · Merge by implicit discriminator, not by explicit action-enum, when branches diverge
When consolidating several verb-specific tools on one resource (create/update/delete), prefer a **single implicit signal already present in the data** over an explicit `action` string/enum — e.g. an optimistic-lock field (`base_version`) **absent ⇒ create**, **present ⇒ update** (an "upsert"). An explicit `action` enum whose branches need genuinely different required fields (create needs full fields, delete needs just an id) can't be expressed as a flat required-list in JSON Schema without falling back to prose ("required only when action=X") — which violates IN-4. Where verbs share fields cleanly (create+update usually do), merge them; where they don't (delete usually doesn't), keep delete as its own tool.

### CAT-2 · A merge across tools with different safety/confirm behavior must branch explicitly, never assume uniformity
Before merging two tools, check whether they differ in whether they mint a confirm-token (human-in-the-loop write) vs. execute directly (e.g. a book-tier delete that requires confirm vs. a user-tier delete that's a direct, reversible soft-delete). If they differ, the merged tool's **description and schema must state the branching condition explicitly** (e.g. "when `scope=book`, returns a `confirm_token`; when `scope=user`, executes immediately"), and **each branch gets its own test**. Never silently normalize two different safety tiers into one code path by merging their tools.

### CAT-3 · Batch is `items[]`, bounded, and returns per-item results
An array-input tool takes **1..N** items — a single item is just a 1-element array; there is no separate "singular" arg shape to design or maintain. `items` declares `minItems`/`maxItems` in the schema (IN-4). The result is a **per-item** status list (`{code, status, error?}` per item), never an opaque all-or-nothing success — this extends OUT-5 (no silent truncation/failure) to the batch case: a batch call that fails item 7 of 10 must say so, not discard the other 9 successes or fail the whole call.

### CAT-4 · Tool visibility: `_meta.visibility` gates discovery, not existence

> **RETIRED, NOT MERELY DEPRECATED (2026-08-25). `find_tools` is unreachable on every
> surface** — the chat advertise path, the ai-gateway dispatch, the public MCP gateway's
> always-allow and its activation exemption, and the server instructions that used to tell every
> connecting client to call it. It last ran on **2026-07-15**. `tool_list` + `tool_load`
> (deterministic category listing → load-by-name) are the only discovery surface.
>
> **The DRIFT NOTE this replaces was itself the defect.** From 2026-07-22 it said "deprecated" and
> "do NOT reach for it in new work" — while the code kept a docstring calling the path LIVE, the
> public gateway kept advertising it, and the gateway instructions kept recommending it. A
> deprecation notice does not retire anything. See **DIS-3**, which is the rule this cost.

A consolidated or superseded tool is **not deleted** — existing callers (older FE builds, tests, other services) keep working. Instead it's tagged `_meta.visibility: "legacy"` (default, when absent: `"discoverable"`). The advertised TURN CATALOGUE, `tool_list` and any domain hot-seed **exclude `legacy`-tagged tools entirely — unconditionally, whether or not a replacement is on the same wire (see DIS-4; the conditional version left 117 dead tools reachable)** — a legacy tool never appears in a fuzzy-search result and is never hot-seeded, no matter how well its description matches an intent. The **only** path to activating a legacy tool for a session is an explicit, user-initiated pin — a **Settings & Configuration Boundary**-governed per-session choice (SET-1: this is a user setting, not a global unlock), never a blanket "show me everything" mode.

## Part 5 — The durable human gate (ext-tasks) — the KIND-C confirm mechanism

**Status (2026-07-20): the durable ext-tasks gate is the PRIMARY path for high-impact (Tier-W / KIND-C) confirms; the `confirm_token` + `confirm_action` frontend tool is the permanent FALLBACK.** Spec: `docs/specs/2026-07-19-mcp-tasks-durable-gate.md`; plan: `docs/plans/2026-07-20-mcp-tasks-full-activation.md`.

- **GATE-1 · A KIND-C confirm tool returns `GateOrConfirm(ctx/meta, store, descriptor, ownerUserID, payload, inputRequests, confirmFallback)`.** A client that declared the ext-tasks capability (`tasks_gate_enabled`; chat-service does by default) gets a durable, owner-scoped `input_required` **task** (persisted in `mcp_gate_tasks`, multi-replica-safe) rendered by the FE `TaskConfirmCard`. Any other client gets the byte-identical `confirm_token` card (`confirm_action`). The write to run on accept is a **resolver registered by descriptor** — never a closure — so any replica can resolve it from the persisted `{descriptor, ownerUserID, payload}`.
- **GATE-2 · The `confirm_token` fallback is permanent (spec OQ3).** So `confirm_action` / `glossary_confirm_action` are **not retired** — they still render (a) the fallback for non-tasks clients, and (b) the tools that legitimately can't be task-shaped: a confirm whose execute path needs the token itself (a replay-ledger / usage-billing key), a dual-mode tool whose non-confirm branch has a typed output, System-tier admin confirms, and the client-side C1 record-edit (`glossary_propose_entity_edit`) which PATCHes from the browser with no server executor to gate. *(This clause also named `propose_record_edit` until 2026-09-03. That tool was **RETIRED 2026-07-21** in auto-gate M5 — every domain now edits records through its own direct-write MCP tool, and `book_update_details`' diff renders via ConfirmActionCard. It is absent from the live catalogue and from `FRONTEND_TOOL_NAMES`. Naming a retired tool as a live mechanism is the DIS-3 failure this document defines three sections below.)*
- **GATE-3 · The accept-caller MUST equal the task owner.** Go domains enforce this in the resolver (`mcpUserID(ctx) == ownerUserID`); Python domains enforce it in the kit's provide-input tool (`_owner_check` via `build_tool_context`, `register_task_endpoints(internal_token=…)`). A leaked (unguessable) `taskId` must not let another user drive a pending gate.
- **GATE-4 · A Go tool with `Out=any` (a gate tool returns a handle OR a card) — or ANY `any`-typed struct field in its result — MUST carry an explicit `{type:object}` `outputSchema`.** The go-sdk otherwise infers `outputSchema.properties.result` as the bare permissive "any" schema, which the ai-gateway proxy's strict validator REJECTS — failing the whole provider's `list-tools` so **none of its tools route** (a silent, catalog-wide outage; the kit's `RegisterTool`/`RegisterTaskProvideInput` now do this automatically). This is why a gate must be smoke-tested THROUGH the gateway, not only via the raw `/mcp` handler.

---

## Part 6 — DISCOVERY: how a tool gets found, and how a dead one stops being found

> **Every rule here was measured on 2026-08-25**, during a run that spent 39 live turns concluding
> a working tool was "blocked". It was reachable, it ran correctly when reached, and none of that
> was the problem. What follows is what actually was.

### DIS-1 · A tool MUST be reachable by its own name

Answerability matched a tool's **declared synonyms and nothing else**. Sampling 25 tools from the
live catalogue and asking for each by name — *"Please use the `<name>` tool for me"* — **24 of 25
were not answerable.** Naming a tool did not put it on the wire.

Live at K=5, a prompt reading *"Use the `composition_build_cast_and_graph` tool to build the cast
and the knowledge graph"* left that tool **surfaced 0/5**. The model walked a six-call chain
instead and never once called `tool_load` to fetch the thing it had just been told to use. A second
arm asked for the one capability only that tool has — plan a worklist, show it, then build — and
the model **simulated the worklist in prose** rather than finding the tool that does it.

**This is not the name-classifier `CP-4.d` deleted,** and the distinction is the rule. That was a
twelve-verb *substring* test that **inferred a property** (the read/write lane) from *fragments* of
a name — it saw *get* inside `memory_forget`, *view* inside `kg_view_delete`, promoting destructive
tools into the always-advertised safe set, and it disagreed with the declared lane on 29 of the 315
tools in the catalogue **as it stood on 2026-08-25**. C-1 forbids exactly that: *"lane is data at registration, never inferred from a name."*
Nothing is inferred by DIS-1: the **whole identifier** must appear, on **identifier boundaries**,
and the only thing concluded is what the writer said — they named this tool.

Identifier boundaries are not word boundaries. A synonym matcher guarding with
`(?<![a-z0-9])…(?![a-z0-9])` is right for a phrase and **wrong for a name**, because `_` is outside
that class: `book_list` matches inside `book_list_chapters`. Guard names with `_` in the class too.

### DIS-2 · Two UNRELATED tools must not declare the same synonym

Answerability is **additive and ranks by match length**, so an identical string is a tie nothing
downstream can break — there is nothing to break it *with*. Both tools reach the wire
indistinguishable, and whichever the model happens to prefer wins every time.

`composition_build_cast_and_graph` and `kg_build` both declared **"build the knowledge graph"**.
The scenario that tested the first built its prompt from that phrase — sound reasoning, a tool
declaring words verbatim should be reachable by them — and measured **0/10, 0/20 and 0/5** across
three conditions. It was measuring the tie. De-duplicating moved the tool off zero on the first run.

Swept live: **92 phrases were declared by more than one tool.** 75 were a legacy tool sharing with
its successor — *deliberate*, and the point of the R2 rule in `answerable_tools`, so whatever
phrasing reaches the old name also reaches its replacement. **17 were ties between unrelated
tools.**

**Fix by naming what distinguishes the tools — usually their INPUT or their scope — not by picking
a winner.** `kg_build` reads the book's *chapters*; `composition_build_cast_and_graph` reads *prose
the caller hands it*. Neither kept the bare phrase; each says which. And a **generic tool must not
claim a domain phrase**: `jobs_pause` declared "pause the translation", which belongs to
`translation_job_control`, the tool that actually understands a translation job.

*Enforced by `scripts/lint_duplicate_synonyms.py` (`--max-ties 0`), which exempts
legacy↔successor overlap by design.*

⚠️ **When you de-duplicate, check the REPLACEMENT is free.** The first pass at this swapped two
ties for two new ones: "arc structure" was already `composition_arc_suggest`'s.

### DIS-3 · Retirement is TOTAL, or it poisons every reader

`find_tools` was pulled from the model's view by F17 on 2026-07-20 and last actually ran on
**2026-07-15**. Six weeks later it was still, simultaneously:

* described by its own handler as *"the variant the **LIVE** `_stream_with_tools()` tool-loop call
  site awaits"*;
* reached by a `if name == FIND_TOOLS_NAME: _add(FIND_TOOLS_TOOL)` branch that **could never fire**,
  because the name was no longer in the tuple that loop iterates;
* advertised by the public MCP gateway to **every key at any scope**;
* recommended by the ai-gateway's own `SERVER_INSTRUCTIONS`, which told **every connecting client**
  to call it.

An agent read that, believed it, and spent a session diagnosing a cache-key bug in an embedding
path only the dead tool can reach. The bug was real. The finding was worthless.

**A retirement must land on every surface AND every instruction that names the tool** — handler,
always-on list, gateway policy, activation exemptions, server instructions, and the docstrings that
claim liveness. Leave the code and its rationale if you like (deleting loses *why*), but make it
**unreachable**, and have the dispatch return an explicit refusal naming the replacement rather
than a silent empty result a caller will read as *"no such capability"*.

### DIS-4 · `visibility: legacy` means UNREACHABLE — not "unreachable when convenient"

The drop rule removed a legacy tool from a turn catalogue **only when its named replacement
happened to be on the same wire**. That left **31 legacy tools advertised forever** (they name no
`superseded_by` to satisfy) and 86 more advertised on any turn their replacement missed. Measured
against the live catalogue: **315 advertised → 198** (measured 2026-08-25) after the rule was
widened to every legacy tool. *Re-derive, never quote: `python scripts/refresh_tool_catalog_cache.py
--check` then census `contracts/tool-catalog-cache.json`. On 2026-09-03 it is **316 total / 199 live
/ 117 legacy**, and `drop_superseded_tools` withholds all 117.*

The marking is a decision, taken deliberately. **Traffic to a marked tool is rot, not a
requirement** — `find_tools` is what that looks like when it is left to run. If a tool marked
legacy turns out to be load-bearing, **correct the marking**; do not leave a path open around it.

*A companion consequence worth stating: the release denominator and the advertised surface must be
the same set. Before this (2026-08-25), the platform advertised 315 tools while the ledger counted 198 as
shippable — 117 an agent could reach had never been evaluated.*

### DIS-5 · An instrument that reads a cached catalogue must be able to tell that it is stale

`contracts/tool-catalog-cache.json` had **no timestamp, no generator, and five consumers** — three
lints, the answerability probe, and a gate test. Every one silently measured whatever the catalogue
looked like the last time somebody made the file by hand.

Caught the moment the first lint ran: it reported a duplicate synonym that had already been fixed,
deployed and verified gone from the live wire. Refreshing showed **39 tools whose definitions had
drifted**, not the two just edited. *An instrument that measures the past reports a fixed defect as
open — and a new one as absent.*

**And a PARTIAL catalogue is worse than a stale one.** The refresher written to close this gap
immediately wrote one: run ~30s after restarting three services and ai-gateway, it read **274 tools
instead of 315** — every `kg_*` tool "removed", because federation had not finished — and wrote
that without complaint. Tools *disappearing* is the signature of a race, not a retirement: refuse
the write, and require an explicit flag for a real removal.

*`scripts/refresh_tool_catalog_cache.py` regenerates from the live catalogue; `--check` fails when
stale.*

### DIS-6 · A scenario built on a phrase two tools share measures the TIE, not the tool

Before trusting a surfacing measurement, check that the prompt can **discriminate**. A scenario
whose headline phrase is declared by more than one tool cannot test either of them, and will report
the one under test as broken.

Related: a scenario's **falsifier must be reachable by the scenario**. The one here described
post-call safety — no confirm card, `op` must be `start`, no invented `run_id` — while the gate
blocked on selection, so across 39 live runs *the falsifier was never evaluated once*. Split
selection from behaviour: one arm that NAMES the tool and tests what it does, one that tests
whether it gets chosen.

### DIS-7 · A user-facing text filter must never rewrite an IDENTIFIER

The §4 "speak plainly" guard rewrites system jargon in the assistant's output. Its rules are
word-boundary regexes and `-` is a word boundary, so they fired **inside slugs**: 5 of 5 replies
handed the user `story bible-bootstrap` and `element-triage` — names that do not exist, that they
cannot type and that `workflow_load` cannot resolve.

**Translate a WORD; never half-translate a NAME.** Translating a *whole* name is a different act and
stays legal (`vision-to-book` → "book-building" is a deliberate relabel). A residual worth knowing:
a bare identifier that IS a jargon word — six skill slugs are literally `glossary` — cannot be
protected by a hyphen rule.


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
| DIS-1 reachable-by-name | `chat-service/tests/test_a_tool_named_in_the_request_is_answerable.py` |
| DIS-2 no shared synonym between unrelated tools | `scripts/lint_duplicate_synonyms.py --max-ties 0` |
| DIS-4 legacy is unreachable | `chat-service/tests/test_superseded_tool_does_not_compete_with_its_replacement.py` |
| DIS-5 catalogue cache is not stale | `scripts/refresh_tool_catalog_cache.py --check` |
| DIS-7 the plain-speech guard leaves NAMES alone | `chat-service/tests/test_the_plain_speech_guard_does_not_invent_workflow_names.py` |

**Not yet enforced (tracked gaps — candidate work):**
1. **No cross-service "MCP-tool lint"** that fails a *new* tool for: a bare-`string` arg whose description enumerates a finite set (IN-3), a set-returning tool with no `get_by_id` sibling and no `@small_return` (OUT-1), or a tool-result site bypassing `_tool_result_content` in a service the L3 lint doesn't yet cover. Today these are caught per-tool by hand-written tests, so a tool with no test slips. **Partial coverage landed (K37, 2026-07-24):** `scripts/context-budget-defaults-lint.py` (pre-commit) IS a cross-service lint for one OUT-2 rule — a LIST tool (has `detail`+`limit`) must default `detail=summary` + `limit<=25`. It seeds the 14 current offenders as a FLIP-PENDING `ALLOW` (K37 debt) and blocks NEW violations. The IN-3 / OUT-1 dimensions above are still per-tool-test-only.
2. **OUT-1/OUT-2 have no repo-wide contract-snapshot harness yet** — the Context Budget Law §6b names it as planned (per-tool return-shape snapshot + `@small_return` honesty check). **First landing (K36, 2026-07-24):** a per-tool *default-reply byte-budget* test now guards `jobs_list` (`test_jobs_list_default_reply_fits_the_context_budget` — asserts the no-arg reply `< result_warn_bytes()` under >1 page of fat rows). It's per-tool, not yet a cross-service harness, so a *new* set-returning tool with no such test still slips; generalizing it (a fixture that runs every registered list tool through the byte budget) is the remaining work. Until then, reference-first + a hand-written budget test is convention on new list tools.
3. The IN-8 drift-lock exists for the **knowledge** MCP surface; the same discipline for glossary/composition/other domain surfaces is per-service and uneven.
4. **CAT-4 tool visibility — PARTLY CLOSED 2026-08-25, and the remainder is narrower than it was.** The chat-service turn catalogue now drops EVERY `legacy` tool unconditionally (DIS-4), measured 315 → 198 on 2026-08-25 (today 316 → 199; derive, do not quote), pinned by `test_superseded_tool_does_not_compete_with_its_replacement.py`. What is still owed is the *lockstep*: nothing checks that the ai-gateway surface hides exactly the same set, so one surface can still leak what the other correctly hides. `find-tools.ts` is no longer the place to check it — that tool is retired (DIS-3); the check belongs against the advertised catalogue itself.
5. **`invoke_tool`'s `arguments` field is a deliberate, protocol-necessitated IN-3/IN-4 deviation.** `services/mcp-public-gateway/src/scope/invoke-tool.ts` — the public MCP edge's execution facade takes a generic `{name: string, arguments: object}` shape (no closed-set enum on `name`, no per-target schema on `arguments`) because it exists PRECISELY to call a tool the client's cached `tools/list` never described (a standard MCP client fetches `tools/list` once at connect and never re-polls — see `docs/plans/2026-06-29-public-mcp-lazy-tool-loading.md`'s 2026-07-07 amendment). A closed-set `name` enum would have to be the full ~150+ tool catalogue (defeating the lazy-loading token savings this facade exists for); a per-target `arguments` schema is structurally impossible for a single generic tool definition. The real IN-3/IN-4 discipline is enforced one layer up instead: **`tool_load`'s** result carries the target's full description + schema (and is what ACTIVATES a tool for `invoke_tool` — listing alone does not), and the target's OWN schema is still validated server-side once `invoke_tool` unwraps the call into a normal `tools/call`. *Corrected 2026-08-25: this paragraph used to credit `find_tools` with carrying the schema. That tool is retired (DIS-3), and verifying the replacement before rewriting this text is how the retirement was confirmed not to break the public edge.* (every existing per-tool IN-3/IN-4 gate still runs against the real target name/args, unchanged). Accepted, not a candidate for closing — the deviation is the fix, not a gap to lint away.

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
- [ ] Consolidating verbs? Prefer an implicit discriminator over an `action` enum when branches diverge (CAT-1)
- [ ] Merging tools with different confirm/safety behavior? Branch explicitly, test each branch (CAT-2)
- [ ] Multi-item support is `items[]` (1..N, bounded), with per-item results — no separate singular shape (CAT-3)
- [ ] Deprecating a tool? Tag `_meta.visibility:"legacy"`, don't delete — verify it's excluded from discovery on **both** federation surfaces (CAT-4)
- [ ] Reachable by its own NAME, on identifier boundaries (DIS-1)
- [ ] No synonym shared with an UNRELATED tool — `lint_duplicate_synonyms.py --max-ties 0`; check the replacement is free too (DIS-2)
- [ ] Retiring? Every surface AND every instruction that names it, and the dispatch refuses by naming the replacement (DIS-3)
- [ ] Testing surfacing? The prompt must DISCRIMINATE, and the falsifier must be reachable by the scenario (DIS-6)
