# Frozen Contracts (§6b.0) — freeze BEFORE the 3 sessions fan out

**Status: FROZEN 2026-07-09.** These are the seams shared across Tracks A/B/C. A session **must not**
unilaterally change a contract — a change here breaks the other two tracks at integration (N1/N2/N3).
To change one: update this file + ping the other tracks (it's a cross-track decision, not a local one).
Everything *not* in this file is a track's own implementation detail, free to design as it sees fit.

Owner of the definitions: **Track A** (it implements the gateway/discovery side). B and C **code against**
these; they do not redefine them.

---

## C1 · Category enum (closed set)

The single closed set of tool categories. **Source of truth: `GROUP_DIRECTORY`** (ai-gateway
`find-tools.ts`), mirrored byte-for-byte in chat-service `tool_discovery.py` and the `Domain` union in
mcp-public-gateway `tool-policy.ts`. Everyone **imports** it; no one re-declares it.

```
book · catalog · composition · glossary · jobs · knowledge · plan · registry · settings · story · translation
+ sentinel: "all"
```
- `knowledge` spans prefixes `kg_` + `memory_` (via `_DOMAIN_ALIASES`).
- **`lore_enrichment`** (the 1 orphan tool `lore_enrichment_auto_enrich`) → **folded into `glossary`**
  (add `lore_enrichment` → `glossary` to `_DOMAIN_ALIASES` / prefix map). Not a new category.
- **`admin`** (RS256-segregated catalog) is **excluded** from the user-facing enum (OQ2) — a separate scope.
- Category resolution stays **prefix-based** (`_domain_of(name)` through the alias map), never
  service-based (`story`/`plan` live in a different service than their name suggests — keep prefix-based).

**Invariant:** the three declarations stay identical, guarded by `find-tools.spec.ts`'s drift-lock test.

## C2 · `tool_list` / `tool_load` I/O + activation

**Visible set (the anti-drift definition):** `visible = catalog ∩ (non-legacy OR include_deprecated) ∩ isToolAllowed(key/scope)`.
A policy-allowed tool **must** appear (kills the 3-registry drift). Deterministic, unranked, no similarity floor.

```
tool_list(category?: <C1 enum>, include_deprecated?: bool = true)
  → { category, count, tools: [ { name, description, tier: "R"|"A"|"W"|"S",
                                  deprecated?: bool, superseded_by?: string } ],
      reason?: "gated: requires <entitlement>" | "no tools" }   # C6-style, for an empty/gated category
```
- omitted `category` or `"all"` → the whole visible catalog, grouped by category.
- deprecated (legacy) tools appear **labeled** (`deprecated:true` + `superseded_by`), never silently
  dropped (OQ5). `include_deprecated:false` filters them.
- gated/empty category returns `reason` so the caller can tell "gated" from "nonexistent" (feedback #6).

```
tool_load(name?: string | names?: string[] | category?: <C1 enum>)
  → { tools: [ { name, description, inputSchema, tier, deprecated?, superseded_by? } ] }
```
- **Pure disclosure — executes nothing.** Returns full `inputSchema`(s).
- **Activation rule:** on the public edge, `tool_load`ed names are added to the session activation set
  (same set `find_tools` populates) → a subsequent raw `tools/call` to any loaded name is permitted.
- loading a deprecated tool succeeds and returns its `superseded_by` pointer.

`find_tools` is **kept but demoted** (OQ1): reworded as optional; `tool_list` advertised first. Semantic
ranking may order a `tool_list` result but is never the sole gate.

## C3 · Workflow `steps` schema (the object Track C authors, Track A's runner executes)

```yaml
slug: <kebab>                      # unique id
title: <human>
tier: system | user | book
surfaces: [chat, book, editor, studio]
description: <one-line, L1 menu>
inputs: { <name>: required | optional }
steps:
  - id: <kebab>
    tool: <exact tool name>        # must be in C1 catalog ∩ policy-allowed
    gate: none | confirm | approval   # confirm ⇒ mint→confirm_action; approval ⇒ Tier-A card
    when?: <predicate over prior step results / inputs>     # optional conditional
    repeat?: none | per_item:<inputs key>                    # optional fan-over
    inputs_map?: { <tool_arg>: <ref to input / prior step output> }
notes_md: <prose the agent reads — gotchas, plain-language framing; NOT executed>
```
Runner semantics (Track A / WS-2b): steps run in order; `gate:confirm|approval` surfaces the **existing**
propose→confirm / Tier-A approval flow (never bypassed); a step whose `tool` starts an async job is marked
`pending` and the "done" message is gated on an observed terminal status (async-honesty, OQ9). A failing
step drops the workflow gracefully with a plain-language explanation, never a stack trace.

## C4 · Error envelope + `content`/`structuredContent` uniformity (normalized centrally at the gateway)

**Every** tool failure, from any layer, is normalized to ONE shape (feedback #10):
```
{ "code": <STABLE_CODE>, "message": <human, actionable>, "detail"?: { ... } }   # with isError:true
```
Stable `code` set (closed; extend via this file): `VALIDATION` · `NOT_FOUND` · `NOT_PERMITTED` ·
`NOT_DISCOVERED` · `CONFIRM_REQUIRED` · `CONFIRM_FAILED` · `BUSINESS_RULE` · `RATE_LIMITED` ·
`UPSTREAM_UNAVAILABLE`. (`NOT_DISCOVERED` is distinct from `NOT_FOUND` so "undiscovered" ≠ "nonexistent".)

**Output uniformity (feedback #9B):** every tool declares an output schema ⇒ every response carries
`structuredContent` (the real JSON, once) + `content[0].text` = a short placeholder
(`"ok — see structuredContent"`). No tool dumps full JSON into `content`; no duplication. Applied centrally
at the gateway so B/C never hand-roll it.

## C5 · New backing-tool signatures (so C's workflows and B's implementations agree)

- **Seed-doc → entities** (WS-4A, glossary): `glossary_extract_entities_from_doc(book_id, source_markdown, kinds_hint?)`
  → `{ candidates: [ { kind, name, attributes: { <code>: <value> } } ] }` (a workflow then calls
  `glossary_propose_entities`). Tier-R (read/derive; no write).
- **Glossary → KG nodes** (WS-4B, knowledge): `kg_project_entities_to_nodes(project_id, entity_ids?)`
  → `{ nodes_created, nodes_existing }` (Tier-A; deterministic projection). Plus **fail-fast edge**:
  `kg_propose_edge` returns `{code:"KG_ENDPOINT_NOT_NODE", detail:{missing:[...]}}` **immediately** when an
  endpoint isn't yet a node (instead of parking + failing at confirm).
- **Auto-capture** (WS-4C): internal — persist chat-established facts as **glossary entities** as they're
  stated (not model-tool-gated); AND admit `source_type="llm_tool_call"` facts into L2 auto-injection (lower
  the 0.8 `min_confidence` gate for that source only). No new model-facing tool required.
- **Entity identity** (WS-4B/scope, glossary): `scope` is a first-class field on an entity (complete the
  in-flight `scope_label` work); dedup key becomes **`(name, kind, scope)`**; name stays clean.
  `glossary_entity_rename(entity_id, name)` and `glossary_entity_delete(entity_id)` (Tier-W) exist and are
  reachable/discoverable.

## C6 · Mode → capability binding record (Track C's UI + Track A's resolve both read)

Stored per-user and per-book; resolved **additively** in `resolve_skills_to_inject()` (never removes a
static default; same `HOT_SEED_TOKEN_BUDGET` ceiling):
```
mode_binding: {
  mode: "ask" | "write" | "plan",
  inject_skills: [ <skill code> ],
  inject_workflows: [ <workflow slug> ],
  seed_tool_categories: [ <C1 enum> ]
}
```
Generalizes today's hardcoded `plan→plan_forge`. Effective binding = System default ∪ per-user ∪ per-book
(tenancy resolution order).

---

### Change log
- 2026-07-09 — initial freeze (all of C1–C6).
- 2026-07-09 — **C5 refinement (Track B, owner of C5) — `glossary_entity_rename`.** Two clarifications
  vs. the frozen line, both to match code reality; **Track C: note for workflow authoring.**
  1. **Signature** is `glossary_entity_rename(book_id, entity_id, name)` (not `(entity_id, name)`) —
     `book_id` is required so the grant is checked on the *named* book first (every sibling entity tool
     takes `book_id`); an `entity_id`-only form forces a pre-grant entity lookup that leaks cross-tenant
     existence (anti-oracle).
  2. **Tier is A, not W.** A rename is reversible (revision history) and non-destructive, and the
     Tier-A `glossary_entity_set_attributes` *already* renames (`name` is just an attr_code) — so a
     propose→confirm gate on rename adds no real safety and would be illusory + inconsistent with this
     service's own tiering rationale (destructive⇒W, reversible⇒A). **`glossary_entity_delete` stays
     Tier-W** (destructive) and already exists/reachable — no change there. Workflow steps calling rename
     use `gate: none`, not `gate: confirm`.
