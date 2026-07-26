# S1 — live-smoke of the 5 unified KG tools (2026-07-23)

**Why this exists.** The KG merges shipped with unit delegation tests + a discoverability
run, but **never an end-to-end call per enum branch**. The glossary incident proved that
gap is exactly where a defect hides: `Items any` passed every unit test, every contract
test, and every visibility test, and still de-federated 54 tools — because it only broke
at the federation boundary. Unit-green is not evidence for a cross-service claim.

**Method.** Every enum branch of all 5 merged tools called for real through **ai-gateway**
(`POST /mcp`, `tools/call`), with the internal token + `X-User-Id` / `X-Project-Id` /
`X-Session-Id` envelope. Fixture: test account, project `019f84ea-…` ("The Salt
Cartographer", book `019f84e1-…`). Local model only (`gemma-4 26b`) ⇒ $0 spend.

---

## Result: 12 branches, **0 defects**

| tool | branch | verdict | evidence |
|---|---|---|---|
| `kg_graph_query` | `scope=project` | ✅ executed | returned graph payload |
| `kg_graph_query` | `scope=multi` | ✅ executed | real nodes returned |
| `kg_graph_query` | `scope=world` | ✅ executed | `partitions_read: 0` + honest note *"this world has no KG partitions you can read"* |
| `kg_build` | `target=wiki` | ✅ executed | `proposed: true` + `confirm_token` (descriptor `kg_build_wiki`, carries `model_ref`) — correctly confirm-gated, nothing applied |
| `kg_build` | `target=graph` | ⚠️ precondition | *"this project has no embedding model configured — call `kg_project_set_embedding_model` first … then `kg_run_benchmark`, then retry"* |
| `kg_ontology_propose` | `op=adopt_template` | ✅ executed | `confirm_token`, descriptor `kg_adopt`, `source_schema_id` echoed |
| `kg_ontology_propose` | `op=schema_edit` | ⚠️ precondition | *"this project has no adopted ontology to edit — adopt a project schema first"* |
| `kg_ontology_propose` | `op=sync_apply` | ⚪ not reachable | `kg_sync_available` → `has_updates: false, adopted: false` — nothing upstream to sync on this fixture |
| `kg_view_edit` | `op=upsert` | ✅ executed | `created: true`, view `019f8ddf-…` |
| `kg_view_edit` | `op=delete` | ✅ executed | `deleted: true` — **full round-trip** |
| `kg_add_nodes` | `mode=manual` | ✅ executed | entity `cb084a70…` created |
| `kg_add_nodes` | `mode=from_glossary` | ✅ executed | **`nodes_created: 16, nodes_existing: 6`** |

**9 executed with real effect · 2 blocked by correct preconditions · 1 not reachable on
this fixture.** No `Items any`-class defect, no mis-routed branch, no silent no-op.

### Why the 2 preconditions still count as evidence
They are not "untested". A broken enum dispatch fails *differently* — unknown op, wrong
handler, missing-arg on the wrong field. Here each `op` produced a **distinct,
op-specific** domain error from its own core:

- `adopt_template` → a valid `confirm_token`
- `schema_edit` → *"no adopted ontology to edit"* (the schema-edit core's own guard)
- `sync_apply` → *"requires base_source_hash"* (the sync core's own guard)

Three ops, three different cores, three different answers ⇒ **the discriminator routes
correctly**. And every error is self-describing with the exact remedy, which is the
`mcp-tool-io` self-correcting-error rule holding in practice.

`op=sync_apply` is recorded as **not reachable on this fixture**, not as a pass — it needs
an adopted ontology with upstream drift. Confirming the adopt token would unblock both it
and `schema_edit`, but KG confirms are redeemed on the review surface (no MCP confirm
tool), so that is a separate GUI/chat-path test.

---

## Side effects on the test fixture (recorded, not hidden)
- `kg_add_nodes mode=from_glossary` created **16 KG nodes** in project `019f84ea-…`.
- `kg_add_nodes mode=manual` created entity `cb084a70…` ("Smoke Test Node").
- `kg_view_edit` created then deleted view `smoke_test_view` (net zero).
- Two `confirm_token`s were minted and **never confirmed** ⇒ no ontology adopted, no wiki built.

## Harness note
Round 1 returned `missing required context header: 'x-session-id'` on all 12 branches —
**my probe's omission, not a tool defect**. Worth keeping: the error named the exact
missing header, which is how it was fixed in one step.
