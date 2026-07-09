# S00b · `tool_load(name | [names] | category)` — load exact schemas, then call correctly

> ⚙️ **MECHANISM / developer test — white-box BY DESIGN. NOT a black-box user scenario.** Paired with
> S00a; it names the primitive because the primitive is what's under test. `tool_list` tells the model a
> tool *exists*; `tool_load` pulls its exact schema into context (and, on the public edge, activates it
> for raw `tools/call`) so the model calls it right the first time — without a semantic search running.
> The user-observable payoff is proven in the black-box scenarios, not here.

| Field | Value |
|---|---|
| **Scenario id** | S00b |
| **Maps to umbrella** | Phase 1 — the discovery triad, §4.1 — [`../2026-07-09-agent-discoverability-and-workflow-architecture.md`](../2026-07-09-agent-discoverability-and-workflow-architecture.md) |
| **Persona** | any (the model is the subject) |
| **Surface** | chat |
| **Permission mode** | `ask` for the load itself; `write` when the loaded tool is then invoked |
| **Model under test** | `gemma-4-26b-a4b-qat` |
| **Fixture** | book Mị Đế |
| **Status** | ✍️ drafting |
| **Owner** | — |

## 1. User story / intent

> After listing the glossary (S00a), gemma should `tool_load("glossary_propose_entities")` to get its
> exact argument schema, then call it correctly — or `tool_load("glossary")` to pull the whole category's
> schemas at once for a multi-step job — deterministically, by name, no guessing.

## 2. Preconditions / setup

- `tool_load` built (Phase 1); `tool_list` available (S00a).
- On the public edge: `tool_load` marks the loaded names **activated** so a subsequent raw `tools/call`
  is permitted (mirrors today's `find_tools`→activation, but by exact name/category, not by embedding
  match).
- `gemma-4-26b-a4b-qat`.

## 3. The behavior under test

`tool_load` accepts a single name, a list of names, or a whole `category`, and returns each tool's full
`inputSchema` (+ tier/undo metadata). It is **progressive disclosure, not execution** — loading pulls
schemas into context and activates them; it calls nothing.

## 4. Target chat script (EXPECTATION)

| # | User says | Assistant SHOULD do | Tool calls SHOULD be | End state |
|---|---|---|---|---|
| 1 | "Add a character Lâm Uyên." | (already knows the name from S00a) load its schema, then call it. | `tool_load("glossary_propose_entities")` → `glossary_propose_entities([...])` (A). **No `find_tools`.** | Entity created; schema was loaded deterministically. |
| 2 | "I'm going to do a bunch of glossary work — load the tools." | Load the whole category's schemas once. | `tool_load("glossary")` (1 call, category). | All glossary schemas in context + activated; subsequent calls need no reload. |
| 3 | (invokes a loaded tool) | Call it with correct args from the loaded schema. | `<glossary_*>` (A/W with gate). | Correct call, first try; gate honored. |

## 5. Acceptance criteria (measurable)

- [ ] `tool_load(name)` returns the exact `inputSchema`; the immediately-following call **succeeds
      first-try** (no Pydantic "field required" round-trip caused by a guessed schema).
- [ ] `tool_load(category)` loads all schemas in that category and (public edge) activates them — a raw
      `tools/call` to any loaded name is then permitted.
- [ ] `tool_load` **executes nothing** — it is pure disclosure (a loaded write tool does not write).
- [ ] gemma reaches a correct call with **0** `find_tools` calls (list→load→call).
- [ ] Loading a `deprecated` tool works but returns its `superseded_by` pointer so the model can redirect.

## 6. Baseline — CURRENT behavior with gemma (fill via live test)

- _pending — CURRENT system has no `tool_load`; schema disclosure happens implicitly via `find_tools`
  activation on the public edge, or via hot-seeding in chat-service. Baseline: measure how often gemma
  mis-calls a tool (wrong/missing args) because it never saw the exact schema, forcing a
  validation-error retry loop._
- Transcript: `docs/eval/discoverability/YYYY-MM-DD-S00b-gemma.md`

## 7. Gap → required capability

- **Phase 1:** build `tool_load(name|[names]|category)` as an MCP meta-tool returning full schemas from
  the federated catalog; wire `tool_load`→activation on the public gateway (analogous to the
  `find_tools`→`SADD` path); land TS+Py lockstep. Advertise `tool_list`+`tool_load` as the primary
  discovery pair; `find_tools` demoted to optional.

## 8. Re-test gate

✅ when gemma completes list→load→call for entity-create with 0 `find_tools` calls and no schema-guess
validation retries. Together with S00a, this proves the deterministic triad replaces the mandatory
semantic gate.
