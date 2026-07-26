# S3 CRUD families — 5 unified op-tools (structure_template / outline_node / canon_rule / entity_override / scene_link)

**Date:** 2026-07-25 · **Branch:** `feat/frontend-tools-mcp-migration`

## What shipped

Five clean **single-tier CRUD** families consolidated into one `*_edit(op=…)` tool each — the
proven S3·arc pattern:

| Unified tool | Tier | Ops | Legacy superseded |
|---|---|---|---|
| `composition_structure_template_edit` | A/user | create·update·clone·archive·restore | 5 |
| `composition_outline_node_edit` | A/book | create·update·delete·restore·move | 5 |
| `composition_canon_rule_edit` | A/book | create·update·delete·restore | 4 |
| `composition_entity_override_edit` | A/book | add·update·delete | 3 |
| `composition_scene_link_edit` | A/book | create·delete | 2 |

**19 legacy write tools → 5 unified.** All legacy `visibility=legacy` (callable, hidden from
`tool_list` default). Delegates to the SAME handlers, zero logic moved; `_present` preserves
sub-Args defaults; per-op guards raise `ValueError→isError`.

## Unit — 17 dispatch tests, mutation-verified

Routing + arg construction + default-preservation + validation across all 5 families. Mutation
(outline delete→restore mis-route) reds the matching test. Full composition unit **2373 pass / 1 skip**.

## Live-smoke (real effect, through ai-gateway)

**structure_template** (A/user) — full CRUD, all `isError=false`:
`create → update(name) → clone → archive → restore`.

**Book-scoped families** on a fresh test Work (`project 019f988a…` on *The Ashfall Chronicles*):
- **outline_node**: `create chapter → create scene(v1) → update(partial: synopsis set, TITLE KEPT, v1→v2) → delete → restore` — all `isError=false`. Partial-patch semantics held (title survived).
- **scene_link**: `create(setup_payoff) → delete` — both `isError=false`.
- **canon_rule**: `create(scope=world default) → update(active) → delete → restore` — all `isError=false`.
- **entity_override**: dispatch reaches the handler (a random target → the handler's own
  "not found or not accessible" deny) and `op=add` w/o target → clean `isError`
  ("op=add requires project_id and target_entity_id").

*(An earlier attempt used an orphaned Work whose book had been deleted → the handler correctly
denied with "not accessible"; a fresh Work on an owned book gives the real effect above — proof
the dispatch reaches the real gate either way.)*

## Discovery shrink (scoped `tool_list category=composition`)

Each family shows **1 unified tool visible by default**, its legacy hidden:

| include_deprecated | composition total | per-family visible |
|---|---|---|
| false (default) | **51** | 1 each |
| true | 101 | struct_tmpl 6 · outline 6 · canon 5 · entity_override 4 · scene_link 3 |

Cumulative across all 4 S3 batches (arc + motif + authoring_run + these 5 CRUD): the composition
default-visible surface is now **51** (down from ~96 with every legacy tool shown).

## Conclusion

All 5 families are federated, callable, tier-correct, unit- + mutation-tested, and live-proven
with real CRUD effect (or handler-reachability for entity_override). The op-dispatch pattern —
already agent-eval-proven on arc + motif — extends cleanly to the whole CRUD surface.
