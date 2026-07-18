# F6 — `kg_build_graph` was unreachable by an agent

**Date:** 2026-07-10 · **Track D · WS-D1/D2 follow-up** · Found by the TLE harness (Wave 1),
root-caused and fixed here.

## What the harness reported

```json
"async_poller": { "build_accepted": false,
  "note": "kg_build_graph call failed: unhandled errors in a TaskGroup (1 sub-exception)" }
```

That message is worthless, and it is worth saying why: it is **not** what the server sent.

## What the server actually sent

```
this project has no embedding model configured — run extraction setup once
in the Build Knowledge Graph dialog (it also runs the required benchmark)
```

The MCP layer had reported it correctly, as `isError: true` with a clear message. The harness's
`mcp_direct.call()` raised its `RuntimeError` **inside** two nested `async with` blocks
(`streamablehttp_client`, `ClientSession`) — both anyio task groups. anyio re-raised it as an
`ExceptionGroup`, and the real text was buried. An entire eval cycle reported a meaningless
wrapper for a perfectly actionable error.

**Fix:** capture the tool error inside the context managers, raise `MCPToolError` *after* they
exit, and defensively flatten any genuine `ExceptionGroup`. Proven: the same call now prints the
server's own sentence.

## The real defect underneath

The message told a **tool-calling model** to open a **GUI dialog**. It named no tool. And there
was no tool to name — the agent's chain had a hole in the middle:

```
kg_project_create  ✅ MCP tool
    ↓
configure the project's embedding model   ❌ REST route + Build-KG dialog ONLY
    ↓
kg_run_benchmark   ✅ MCP tool
    ↓
kg_build_graph     ✅ MCP tool
```

So **every project an agent created dead-ended**, and `kg_build_graph` — a flagship agentic
capability, Tier-W + async, the async class's only representative in the probe matrix — could
never run. This is an **MCP-first invariant** violation: the capability existed, but only behind
a bespoke HTTP route a model cannot drive.

Note the contrast that made it obvious: `kg_run_benchmark`'s description already reads *"call
this … **instead of sending the user to the UI**."* Someone had fixed exactly this class of
agent-hostility for the benchmark step and not for the model-configuration step.

## The fix

1. **New MCP tool `kg_project_set_embedding_model`** (Tier A, scope project, owner-only) on
   knowledge-service — the owning domain service, per the MCP-first invariant. It mirrors the
   REST route's guards:
   - probes the model for its vector dimension (`probe_embedding_dimension`) — the caller never
     knows it, and an LLM certainly doesn't;
   - rejects a dimension with no `:Passage` vector index;
   - **set-on-unset only.** *Changing* the model on a project that already has a graph would leave
     its passages in Neo4j tagged with the old model while retrieval queries the new vector space
     — silent zero-recall (`D-EMB-MODEL-REF-04`). That path deletes vectors, so it stays a
     confirm-gated REST operation, and this Tier-A tool refuses it **by name**.
2. **Agent-native error prose** at all three sites (`build_tools.py`, `mcp/server.py`,
   `definitions.py`): name the tools, in order, never a dialog.
3. **Harness:** `MCPToolError` + `ExceptionGroup` flattening; `verify_live.py`'s async poller now
   configures the embedding model first, the way an agent would.

## Live proof (rebuilt images, real `bge-m3`, $0)

| Step | Result |
|---|---|
| `kg_build_graph` on an unconfigured project | `isError: true` — *"call kg_project_set_embedding_model first … then kg_run_benchmark, then retry"* |
| `kg_project_set_embedding_model` | `changed: true`, **`embedding_dimension: 1024`** — probed live from the real model, nothing hardcoded |
| `kg_build_graph` retry | **`proposed: true` + `confirm_token` minted** — precondition passed, Tier-W token pattern intact |
| same-value re-call | `changed: false`, **no write, no probe** |
| independent DB read-back | `019e7f71-…\|1024\|disabled` |

The confirm token was deliberately **not** redeemed: confirming starts a real, paid LLM extraction
job, and proving the blocker is gone does not require spending money. The fixture project was
restored to `embedding_model = NULL` afterwards.

## Regression gates

- `test_agent_can_reach_kg_build_graph_without_leaving_the_tool_surface` — asserts every link of
  the create → configure → benchmark → build chain exists on the tool surface, and that
  `kg_build_graph`'s description names the setup tool and contains no "dialog".
- `test_build_graph_error_names_the_unblocking_tools_not_a_dialog` — the precondition error is the
  only instruction a model gets; it must name tools.
- `test_changing_model_on_a_built_graph_is_refused_not_silently_orphaning` — the zero-recall trap.
- The existing `test_total_tool_count_is_memory_plus_lane_lf` drift-lock caught the new tool (31 →
  32) and forced the count + rationale to be updated. It did its job.

## What this says about the matrix

`kg_build_graph`'s matrix cell was **`G1: RED — "model did not call kg_build_graph"`** (F5,
under-selection). That is *also* true, but it masked the more important fact: even had the model
selected it, the tool **could not have succeeded**. A G1 failure hides every downstream gate. When
CD4's ship gate lands (WS-D3), a RED-G1 tool must not be scored as merely "the model didn't pick
it" — the probe should be re-run deterministically (MCP-direct) to separate *selection* failure
from *capability* failure.
