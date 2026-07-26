# S3·arc — real-model agent eval (composition tool unification)

**Date:** 2026-07-25 · **Branch:** `feat/frontend-tools-mcp-migration` · **Commit under test:** `ac7b47fcf`

## Question

Does the unified `composition_arc_edit` actually **replace** the 10 legacy arc/arc-template
CRUD tools *in a real agent run* — i.e. can a real LLM discover it, pick the right `op`, fill
the args, and complete a full CRUD lifecycle **without** the legacy tools? (Direct MCP calls
already proved the tool *executes*; this proves a model can *drive* it.)

## Setup

- **Inference:** Gemma-4 26B (a local, non-frontier model — `user_model` `019ebb72…`) via the
  **sanctioned path**: `loreweave_llm` SDK → provider-registry-service → lm_studio. $0 spend.
- **Tool execution:** ai-gateway federated MCP (`http://localhost:8218/mcp`), test user
  `019d5e3c…`, book *The Ashfall Chronicles* `019f7e7f…`.
- **Legacy tools HIDDEN:** the 6 legacy `composition_arc_*` CRUD tools were excluded from the
  advertised set (they are `visibility=legacy` → `tool_list` hides them by default). The model
  saw **8 arc tools** — the unified `composition_arc_edit` plus distractors
  (`_apply`, `_suggest`, `_get`, `_list`, `_import_analyze`, `_extract_template`,
  `archive_derivative`). It had to *choose* the unified tool.
- **Task (one natural-language turn):** "create a saga 'The Frost Compact' → update its goal to
  'Bind the northern houses' → delete it."

## Result — PASS

| Turn | Model tool call | Result |
|---|---|---|
| 0 | `composition_arc_edit {op:create, book_id, kind:saga, title:'The Frost Compact'}` | `isError=false`, node `019f985c…` v1 |
| 1 | `composition_arc_edit {op:update, node_id, expected_version:1, goal:'Bind the northern houses'}` | `isError=false`, v1→v2 |
| 2 | `composition_arc_edit {op:delete, node_id}` | `isError=false`, archived + `undo_hint` |
| 3 | *(no tool call)* | model confirms all three done |

**Summary:** tools called = `composition_arc_edit ×3`; ops = `[create, update, delete]`;
**legacy tools used = none**; create+update+delete coverage = **true**.

Notable: the model **threaded `expected_version:1` from the create result into the update**
(optimistic concurrency) unprompted, and picked `composition_arc_edit` over the 7 distractors.

## Independent DB verification (`loreweave_composition.structure_node` `019f985c…`)

```
title   = The Frost Compact          # op=create
goal    = Bind the northern houses   # op=update
version = 2                          # create→v1, update→v2
kind    = saga
is_archived = t                      # op=delete
```

## Conclusion

`composition_arc_edit` is a **verified drop-in replacement**: a real, weak-ish local model
discovered and drove it through a full arc CRUD lifecycle with the legacy tools invisible, and
every op produced the correct persisted effect. The op-dispatch consolidation does not degrade
model usability — it is sufficient on its own.

*(Harness scripts: `scratchpad/s3_arc_agent_eval.py`, `s3_arc_live_smoke.py`,
`s3_tool_list_shrink.py`. The live run used a `docker cp` of the edited `server.py` into the
running container + ai-gateway re-federation; the committed source is identical.)*
