# Wave 8 — KG write holes + World Map · IMPLEMENTATION PLAN

> **Plan file:** `docs/plans/2026-07-13-studio-wave-8-kg-world.md`
> **Source spec:** [`docs/specs/2026-07-01-writing-studio/38_kg_and_world.md`](../specs/2026-07-01-writing-studio/38_kg_and_world.md)
> **Master plan:** [`docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](../specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) — §0 SEALED PO decisions · §8.0 panel-id ledger · §8.0b Lane-B homes · §8 GG-8 · §9 collisions · §10 REFUTED claims
> **Drafts (the UI acceptance criterion):** `design-drafts/screens/studio/screen-kg-write-affordances.html` · `design-drafts/screens/studio/screen-world-map.html`
> **Branch:** `feat/context-budget-law` · **Written at HEAD** `9262ed53e` · 2026-07-13
> **Services touched:** `knowledge-service` (Python) · `book-service` (Go) · `frontend` · `chat-service` (enum only). `composition-service` is **UNTOUCHED**.
> **Size: XL** (2 shippable halves: 8a = M, 8b = L). **19 slices, 19 commits.**
> **Panels added: 5** — `world` · `world-map` · `cast` · `character-arc` · `canon-growth`. (Was 2. The
> three KG codex panels were **homeless legacy sub-tabs** with no wave; §5.4 homes them here. Delta is now
> **`N_BEFORE + 5`** — and it is still **asserted as a DELTA, never a literal**.)

---

## 0 · READ THIS FIRST — the policy this plan is written under (binding, quoted from the PO)

1. **This plan is written ONCE, in full, at BUILD DETAIL. After the QC gate, implementation proceeds
   autonomously with no further design checkpoints.** Anything vague becomes a stall or a guess at 3am.
   A slice that says "wire the panel" is a FAILURE; a slice says WHICH FILE, WHAT CHANGE, WHICH TEST.
2. **`/review-impl` runs at the completion of EVERY wave**, and any bug it finds is fixed before the wave
   closes. It is a literal step in the DoD (slice **W8-15**).
3. **DEFERRAL POLICY — "blocked ≠ stopped".** When the build hits a blocker: write a tracked defer row and
   **KEEP GOING**. Do **not** stop, do **not** ask. A blocker is a DEFER by default.
   **Stop and ask ONLY for a CRITICAL blocker**, defined narrowly as exactly one of:
   - a destructive / irreversible action (data loss; a migration that drops or rewrites user rows),
   - a **sealed decision proven wrong** by the code (§0 PO-1..4 of plan 30),
   - a **tenancy / security breach** (cross-user data exposure),
   - a **paid-action defect that would charge the user for nothing**.
   Everything else — a missing route, an awkward refactor, a failing third-party thing, an ugly seam — is a
   **defer row + continue**.
4. Every defer row carries: ID, wave/slice of origin, what, the gate reason (CLAUDE.md's 5 gates), target
   wave/trigger. A defer row is never a silent drop.
5. **CLAUDE.md's anti-laziness rule is in force:** *"missing infrastructure is NOT blocked — it is unbuilt
   work to implement."* A route that does not exist is a route you **WRITE**.

> 🔴 **ADJUDICATION REGISTER — IT EXISTS, IT IS ON DISK, AND IT OUTRANKS THIS PLAN.**
> **[`docs/plans/studio-adjudication/wave-8-decisions.md`](studio-adjudication/wave-8-decisions.md)** — 75
> items, 68 DECIDED, each settled by reading source. The earlier draft of this header said the register "does
> not exist"; **that was wrong** — the adjudicating agent died on a 1.5M-token prompt and the decisions were
> later recovered from the journal. **This plan was written BLIND to them.**
>
> They have now been **folded in** (reconciliation pass, 2026-07-13). Every slice below carries a
> **`▶ DECISIONS FOLDED`** block naming the `Q-38-*` ids it implements. **Where the register and this plan
> disagreed, the REGISTER WON** and the plan was rewritten — the contradictions are listed in §9.0.
> **Do not re-open a decided question. Do not "restore" a paragraph this pass deleted.**
>
> If a slice below is silent on something and the register speaks, **the register is binding** — go read it.

---

## 1 · Header — what this wave is

### 1.1 The gaps it closes

| Gap | Plan 30 § | Verdict | What is actually missing |
|---|---|---|---|
| **G-KG-WRITE-HOLES** (M) | §5.3 | CONFIRMED | The KG panels **read** the graph beautifully and **cannot write to it**: no entity create, no relation create, no way to seed an empty graph, no way to forget a fact — plus **three dead buttons** on `kg-overview` (`onArchive`/`onRestore`/`onDelete` are all `noop`). |
| **G-WORLD-MAPS** (L) | §5.3 | CONFIRMED | A complete CRUD domain (`world_maps` + `map_markers` + `map_regions`, 8 MCP tools, real SQL, owner-scoping, MinIO) with **ZERO public REST routes** and **no UPDATE at any layer**. |

**`G-WORKFLOWS` is DROPPED (plan 30 §0 PO-2 — Track C owns it). DO NOT PLAN OR BUILD IT.** No `workflows`
panel, no `workflow-proposals` panel, no mode-binding control in this wave.

### 1.2 Hard gates — what must be green before Wave 8 starts

| # | Gate | Why | Verify (§2) |
|---|---|---|---|
| **G1** | **Waves 1–6 have landed** (12 panels: `quality-canon-rules`, `quality-corrections`, `quality-heal`, `progress`, `arc-inspector`, `motif-library`, `quality-conformance`, `arc-templates`, `plan-passes`, `style-voice`, `reference-shelf`, `divergence`). Wave 7 adds **0** panels. | The panel-enum baseline is **CUMULATIVE**. Wave 8 is the **LAST** wave: it starts at **69** and ends at **74** (🔴 **+5**, not +2 — §5.4 homes three orphaned legacy sub-tabs), **not** 57→59. **Assert the DELTA, never the literal.** | `P1` |
| **G2** | The three-way panel-id equality holds **before** you start: `py enum == contract enum == openable`. | If it is already drifted, your +2 will look like a regression you caused. | `P2` |
| **G3** | ⚠ **X-2 is NOT a gate for this wave.** Wave 8's two panels use `category: 'storyBible'`, which **IS** in `CATEGORY_ORDER`. Waves 1/3 are the ones blocked on X-2. | Spec 38 §3.2 deliberately refused to invent a `world` category for exactly this reason. **Do not add a category.** | `P3` |
| **G4** | **Track C ownership handoff for the `world` container** (spec 38 M8b.0). | Plan 30 §9 forbids starting 8b without it. | `P4` — **already resolved; see below** |

> 🟢 **G4 IS ALREADY RESOLVED — verified against code on 2026-07-13, do not stall on it.**
> Track C's `docs/plans/2026-07-12-track-c-completion-RUN-STATE.md` **P-5 is PARKED** (`:172-177`, `:212`):
> *"User-facing FE surfaces — workflow rack, binding UI, W8 onboarding fork, **W10 world container**, W11
> reader. Gate #2 (large/structural) — **each is a real product surface with its own design.**"* It has
> **no design** and **no code**: `grep "'world'\|WorldPanel" frontend/src/features/studio/panels/catalog.ts`
> → **ZERO hits**. **Spec 38 HAS the design.** So the handoff resolves in Wave 8's favour by default.
> **W8-00 is a 10-minute doc slice that writes the takeover down** — it is **not** a stall and **not** a
> reason to ask the human. Per the deferral policy, an ownership question is not one of the four CRITICAL
> categories.

### 1.3 What it unblocks downstream

- **GG-4 / spec-16 retirement** — `features/composition/hooks/useWorldMap.ts:129,134` is **the only human
  writer of `knowledgeApi.createEntity` / `createRelation` in the entire frontend**, and it is mounted only
  on the legacy `ChapterEditorPage`. **After slice W8-02/W8-03 the KG panels own that capability**, so
  retiring that page no longer deletes it. (Spec 38 OQ-9.)
- Nothing else. Wave 8 is the **last** wave; it unblocks no other wave.

---

## 2 · Pre-flight — run these EXACTLY, read the output, then start

All commands from the repo root `d:/Works/source/lore-weave-mvp`.

```bash
# P1 — Waves 1–6 landed? 🔴 Expect 14 hits (Wave 6 ships FIVE panels, not three: it also homes the
#      orphaned `compose` and `assemble` sub-tabs as `scene-compose` + `chapter-assemble`).
#      Fewer hits ⇒ a wave did not land. That is NOT a stop-and-ask (§8 has only four of those) —
#      record N_BEFORE from P2, assert the DELTA (+5), and CONTINUE.
grep -c "id: 'quality-canon-rules'\|id: 'quality-corrections'\|id: 'quality-heal'\|id: 'progress'\|id: 'arc-inspector'\|id: 'motif-library'\|id: 'quality-conformance'\|id: 'arc-templates'\|id: 'plan-passes'\|id: 'style-voice'\|id: 'reference-shelf'\|id: 'divergence'\|id: 'scene-compose'\|id: 'chapter-assemble'" frontend/src/features/studio/panels/catalog.ts

# P2 — the three-way equality BEFORE you touch anything. Record N_BEFORE. All three MUST be equal.
python - <<'PY'
import json, re
c = json.load(open('contracts/frontend-tools.contract.json'))
contract_n = len(c['ui_open_studio_panel']['args']['panel_id']['enum'])
s = open('services/chat-service/app/services/frontend_tools.py', encoding='utf-8').read()
m = re.search(r'"panel_id":\s*\{(.*?)\n\s*\},', s, re.S)
py_n = len(re.findall(r'"([a-z0-9\-]+)"', re.search(r'"enum":\s*\[(.*?)\]', m.group(1), re.S).group(1)))
cat = open('frontend/src/features/studio/panels/catalog.ts', encoding='utf-8').read()
openable = cat.count("\n  { id: '") - cat.count('hiddenFromPalette: true')
print(f'py={py_n} contract={contract_n} openable={openable}  -> N_BEFORE={py_n}')
assert py_n == contract_n == openable, 'DRIFT AT BASELINE — fix that first, it is not your +2'
PY
# At HEAD 9262ed53e (pre-wave-1) this printed 57/57/57. After waves 1–6 it MUST print 69/69/69.

# P3 — `storyBible` is in CATEGORY_ORDER (it is; this is a sanity check, not a gate).
grep -n "CATEGORY_ORDER" -A 3 frontend/src/features/studio/palette/useStudioCommands.ts

# P4 — Track C has NOT built a world container (expect ZERO output from both).
grep -rn "'world'\|'world-map'\|WorldPanel" frontend/src/features/studio/panels/catalog.ts
ls frontend/src/features/studio/panels/WorldPanel.tsx 2>/dev/null

# P5 — the engines 8a mirrors DO exist (expect NON-empty from all three).
grep -n "async def project_glossary_entities_to_nodes" services/knowledge-service/app/extraction/anchor_loader.py   # :194
grep -n "async def invalidate_fact" services/knowledge-service/app/db/neo4j_repos/facts.py                          # :675
grep -n "_AUTHORABLE_KINDS" services/knowledge-service/app/routers/public/entities.py                               # :975

# P6 — book-service maps: the tables + tools exist, the public REST does NOT (expect ZERO from the last).
grep -n "CREATE TABLE IF NOT EXISTS world_maps\|map_markers\|map_regions" services/book-service/internal/migrate/migrate.go
grep -c "addTool(srv, \"world_map_" services/book-service/internal/api/mcp_maps.go   # expect 8
grep -rn "worlds/maps" services/book-service/internal/api/server.go                  # expect ONE hit: the /internal image route (:200)
grep -rn "worlds/maps" frontend/src services/api-gateway-bff/src                     # expect ZERO — nothing calls it

# P7 — the gateway needs NO change (worldsProxy already forwards every /v1/worlds* path).
grep -n "worldsProxy" -A 6 services/api-gateway-bff/src/gateway-setup.ts

# P8 — suites green at baseline (record the counts; they are your regression floor).
cd services/knowledge-service && python -m pytest tests -q -n auto --dist loadgroup 2>&1 | tail -3; cd ../..
cd services/book-service && go test ./... 2>&1 | tail -5; cd ../..
cd frontend && npx vitest run --silent 2>&1 | tail -5; cd ..
```

**If P2 fails** — the baseline is already drifted. That is a pre-existing bug from an earlier wave, **not
yours**. Fix it (regenerate the contract), commit it separately, then start.

---

## 3 · Backend prerequisites — the route contracts (these slices come FIRST)

**GG-5: a panel whose backend does not exist is not a panel task.** No FE slice may precede its route slice.

### 3.1 knowledge-service (slice 8a) — 4 items

| # | METHOD + path | Request | Response | Errors | Status |
|---|---|---|---|---|---|
| — | `POST /v1/knowledge/entities` | `{project_id, name, kind}` | `201 Entity` | 401 · 422 | ✅ **EXISTS** `routers/public/entities.py:999` |
| — | `POST /v1/knowledge/relations` | `{subject_id, predicate, object_id}` | `201 Relation` | 401 · 409 (endpoint not the caller's) · 422 (self-loop) | ✅ **EXISTS** `routers/public/relations.py:182` |
| — | `POST /v1/knowledge/relations/{id}/invalidate` · `POST /relations/correct` | | | | ✅ **EXISTS + FE-consumed** `relations.py:63 / 106` |
| — | `GET /v1/knowledge/predicate-labels` | `?language` | `200 {…24 curated codes}` | 401 | ✅ **EXISTS, FE-UNCONSUMED** `routers/public/labels.py:26` → W8-03 consumes it (`Q-38-A2-DO-NOT-FORK-RELATIONDIALOG`) |
| **BE-14a** | `POST /v1/knowledge/projects/{project_id}/project-entities` | `{entity_ids?: string[] (≤1000)}` | `200 {nodes_created, nodes_existing, entities_seen, skipped, nodes_conflicted, truncated, note}` — **every counter key ALWAYS present, zero-filled; `note` is the ONLY nullable key** | 401 · 404 (uniform) · **409** `{code:"KG_PROJECT_NOT_LINKED_TO_BOOK", message}` · **503** (glossary unreachable — **BUILT, see BE-14a2**) | **MUST-BUILD** (W8-05) |
| **BE-14a2** | *(not a route — the engine leg BE-14a's 503 needs)* `ProjectionResult.glossary_unreachable` + `projection_result_to_wire()` in `anchor_loader.py`; the MCP tool uses the SAME mapper | — | — | — | **MUST-BUILD** (W8-05) 🔴 `Q-38-A3-WIRE-NAME-DRIFT` |
| **BE-14b** | `POST /v1/knowledge/facts/{fact_id}/invalidate` | `{}` | **always 200** `{invalidated: bool, fact_id: str, reason: str\|null}` | 401 · miss ⇒ 200 `{invalidated:false, reason:"no matching fact found"}` · **already-forgotten ⇒ 200 `{invalidated:false, reason:"already forgotten"}` AND NO WRITE** (**NOT 404, ever**) | **MUST-BUILD** (W8-05) |
| **BE-14b2** | `POST /v1/knowledge/facts/{fact_id}/restore` 🔴 **NEW — the un-forget** | `{}` | `200 {restored: bool, fact_id}` | 401 · miss ⇒ 404 | **MUST-BUILD** (W8-05) 🔴 `Q-38-OQ4-NO-UN-FORGET` **kills `D-KG-FACT-RESTORE`** |
| **BE-14b3** | `GET /v1/knowledge/entities/{entity_id}/facts?include_invalidated=false` | — | `200` (each `Fact` carries `valid_until`) | 401 | **EDIT the existing route** (`entities.py:635`) — without the flag, a restored/forgotten fact is unreachable and BE-14b2 is dead surface |
| **BE-14c** | `GET /v1/knowledge/entity-kinds` | — | `200 {kinds: ["character","concept","faction","location"]}` (the tuple's **wire order** — do not `sorted(set)` per request) | 401 | **MUST-BUILD** (W8-01) |
| **BE-14d** | *(not a route)* Unify the authorable-kind closed set across **THREE** schema sources, from ONE home: **`services/knowledge-service/app/entity_kinds.py`** | — | — | — | **MUST-BUILD** (W8-01) |
| **BE-14e** | *(not a route)* 🔴 **NEW — schema-validate the predicate on `POST /relations` + `/relations/correct`** | — | — | **422** `{error, predicate, allowed[]}` when the resolved schema is CLOSED and the predicate is off-vocab | **MUST-BUILD** (W8-03) 🔴 `Q-38-OQ6-RELATION-PREDICATE-FREE-STRING-BE` **kills `D-KG-RELATION-PREDICATE-UNCONSTRAINED`** |
| **BE-14f** | `POST /v1/knowledge/entities` — **EDIT the existing route** | `{project_id, name, kind}` | `200\|201 CreateEntityResponse = Entity + {created: bool}` — **`created` ALWAYS present** | 401 · 422 | **MUST-BUILD** (W8-02) 🔴 `Q-38-A1-SCOPED-PROJECT-REQUIRED` (4) — today the route hardcodes `201` over a silent MERGE, so an honest *"already exists — opened it"* is **impossible** |

🔴 **BE-14a's gate is `Depends(require_project_grant(GrantLevel.EDIT))`, NOT the raw JWT.**
`_handle_kg_project_entities_to_nodes` runs under `_resolve_project_owner(ctx, GrantLevel.EDIT)`
(`graph_schema_tools.py:1638`), so **a book collaborator with EDIT can seed the owner's graph through the
agent.** Gate BE-14a on `get_current_user` and the **GUI becomes strictly weaker than the tool** — the same
person could do it by asking the LLM and not by pressing the button. That is a *new* inverse gap created *by
this wave*. `require_project_grant` is already shipped (`app/auth/grant_deps.py:107`) and is used by
`ontology.py:425/468`, `extraction.py`, `drawers.py`. **Use `GrantLevel.EDIT`, matching the tool.**

🟢 **BE-14b's gate IS the raw JWT — and that is correct, not an oversight.** `invalidate_fact` is
owner-keyed by `user_id` in the Cypher (`facts.py:667`, `WHERE f.user_id = $user_id`) and the tool itself
takes no project gate (`executor.py:709-716`, comment: *"no project gate needed — forget operates on a
single fact addressed by id and invalidate_fact is OWNER-keyed"*). A cross-user fact id simply doesn't
match → `{invalidated:false}` — **never an oracle**. Do not add a grant dep here. **Same for BE-14b2
(restore): owner-keyed, raw JWT, no grant dep** (`Q-38-OQ4`).

🔴 **BE-14b — THE DOUBLE-FORGET RE-STAMP (the defect the spec missed; `Q-38-A4-FALSE-INVALIDATED-STATE`).**
`_INVALIDATE_FACT_CYPHER` (`facts.py:666-672`) does `SET f.valid_until = coalesce($valid_until, datetime())`
— it **re-stamps an ALREADY-invalidated fact** and answers `invalidated: true`. A double-forget from a stale
tab therefore **reports success AND moves the original forget timestamp forward**, corrupting the audit
history the soft-delete exists to preserve. **Close the window in the WRITER ROUTE, not in the engine**
(`close-legacy-window-in-writer` — the engine is shared with `memory_forget` and mirrors
`invalidate_relation`). BE-14b's handler is **THREE arms, in order**:
1. `before = await get_fact(session, user_id=str(uid), fact_id=fact_id)` (`facts.py:390` — owner-keyed;
   `None` for missing AND for cross-user ⇒ no oracle) → `None` ⇒ `{invalidated:false, fact_id,
   reason:"no matching fact found"}` (string **verbatim** from the tool).
2. `before.valid_until is not None` ⇒ `{invalidated:false, fact_id, reason:"already forgotten"}` **and
   WRITE NOTHING.**
3. else ⇒ `invalidate_fact(...)` ⇒ `{invalidated:true, fact_id, reason:null}`.

🔴 **BE-14e — the spec's defer reason for the BE predicate check is FALSE against code** (`Q-38-OQ6`). The
"widening the ontology check is a knowledge-service design call" claim is wrong: **the design call was
already made and coded.** `validate_edge()` (`app/ontology/validation.py:111-147`) already implements the
exact rule (in `edge_types` ⇒ check endpoint kinds · not in it **and** `allow_free_edges` ⇒ OK · not in it
**and** closed ⇒ `unknown_edge_type`), and `kg_propose_edge` (`graph_schema_tools.py:1541-1559`) **already
calls it** — so the spec's premise *"an agent can still mint an off-ontology edge"* is **FALSE; the agent
CANNOT.** The only unvalidated direct edge-writes in the whole service are the **two REST endpoints**
(`relations.py:127` correct, `:204` create). **The REST surface is LOOSER than the tool.** Nothing is
missing but ~40 lines of wiring. **`D-KG-RELATION-PREDICATE-UNCONSTRAINED` is RETIRED, not deferred.**

🔴 **BE-14d — `kg_create_node`'s `kind` has THREE schema sources, not one.** The spec says "make
`KgCreateNodeArgs.kind` a `Literal`". That is **one third of the fix**. This repo's
`knowledge-mcp-three-schema-sources-fastmcp-strips` memory is exactly this bug: **FastMCP generates the wire
schema from the function signature and STRIPS the pydantic model's constraints.** All three must change or
the agent can still send `kind:"item"`:

| # | File:line | What it is | The edit |
|---|---|---|---|
| 1 | `app/tools/graph_schema_tools.py:451-463` — `class KgCreateNodeArgs(ProjectScopedArgs)` | the **pydantic validator** the executor runs `tool_args` through | `kind: Literal["character","concept","faction","location"]` (build it from the shared constant) |
| 2 | `app/tools/graph_schema_tools.py:828-850` — the `_tool("kg_create_node", …)` entry in `GRAPH_SCHEMA_TOOL_DEFINITIONS` | the **OpenAI function-calling JSON schema** chat-service hands the LLM | replace `{"type":"string","minLength":1,"maxLength":100,…}` with `{"type":"string","enum":[…]}` |
| 3 | `app/mcp/server.py:1123-1130` — the `@mcp_server.tool(name="kg_create_node")` **function signature** | the **MCP wire schema** FastMCP generates | `kind: Annotated[Literal["character","concept","faction","location"], "the entity kind"]` |

### 3.2 book-service (slice 8b) — 12 REST routes + 3 MCP tools + 1 migration

All under the existing `worldsProxy` prefix ⇒ **ZERO gateway changes** (verified: `gateway-setup.ts:86-90`
`pathFilter: p => p.startsWith('/v1/worlds')`, dispatched at `:592`). All owner-scoped from the **JWT**
(`s.requireUserID(r)`, `server.go:415`). All errors uniform **404** for foreign-or-missing (no enumeration
oracle), mirroring `requireMapOwner` (`mcp_maps.go:43`).

| # | METHOD + path | Request | Response | Errors | Slice |
|---|---|---|---|---|---|
| **BE-15a** | `POST /v1/worlds/{world_id}/maps` | `{name, image_ref?}` | `201 {map}` | 401 · 404 (world not yours) · 422 (blank name) | W8-08 |
| **BE-15b** | `GET /v1/worlds/{world_id}/maps` | — | `200 {maps: [{map_id, world_id, name, image_object_key, image_url, image_w, image_h, marker_count, region_count, version, created_at, updated_at}]}` | 401 · 404 | W8-08 |
| **BE-15c** | `GET /v1/worlds/maps/{map_id}` | — | `200 {map, markers[], regions[]}` — the `world_map_get` shape **plus `version` on the map and `updated_at` on every marker and region** | 401 · 404 | W8-08 |
| **BE-15e** | `DELETE /v1/worlds/maps/{map_id}` | — | `204` | 401 · 404 | W8-08 |
| **BE-15d** | `PATCH /v1/worlds/maps/{map_id}` | `{name}` + **`If-Match: <version>`** | `200 {map}` (version bumped) | 401 · 404 · **428** (no If-Match) · **412** (+ the CURRENT map as the body) · 422 | W8-09 🔴 new semantics |
| **BE-15g** | `POST /v1/worlds/maps/{map_id}/markers` | `{label, x, y, marker_type?, entity_id?}` | `201 {marker}` | 401 · 404 · 422 (coords ∉ [0,1]; blank label) | W8-09 |
| **BE-15h** | `PATCH /v1/worlds/maps/{map_id}/markers/{marker_id}` | `{label?, x?, y?, marker_type?, entity_id?}` — **absent = unchanged · explicit `null` on `entity_id`/`marker_type` = CLEAR** | `200 {marker}` | 401 · **404** (foreign map **OR** marker not on this map) · 422 | W8-09 🔴 new semantics |
| **BE-15i** | `DELETE /v1/worlds/maps/{map_id}/markers/{marker_id}` | — | `204` | 401 · 404 | W8-09 |
| **BE-15j** | `POST /v1/worlds/maps/{map_id}/regions` | `{name, polygon, entity_id?}` | `201 {region}` | 401 · 404 · 422 (<3 points; a point ∉ [0,1]) | W8-09 |
| **BE-15k** | `PATCH /v1/worlds/maps/{map_id}/regions/{region_id}` | `{name?, polygon?, entity_id?}` — `polygon` is **replace-whole** | `200 {region}` | 401 · 404 · 422 | W8-09 🔴 new semantics |
| **BE-15l** | `DELETE /v1/worlds/maps/{map_id}/regions/{region_id}` | — | `204` | 401 · 404 | W8-09 |
| **BE-15f** | `POST /v1/worlds/maps/{map_id}/image` (multipart `file`) | — | `200 {image_object_key, image_url, image_w, image_h}` | 401 · 404 · 413 · 415 · 503 | W8-10 |
| **BE-15m** | 3 new MCP tools: `world_map_update` · `world_map_update_marker` · `world_map_update_region` | Tier-A, reversible | | | W8-11 |

🔴 **THE CHI ROUTE-ORDER TRAP — read this before you mount anything.** `/v1/worlds` already has
`r.Route("/{world_id}", …)` (`server.go:383`). A new `r.Route("/maps", …)` sibling registered under the same
`/v1/worlds` router **must resolve `/v1/worlds/maps/{map_id}` to the maps sub-router, not to
`{world_id}="maps"`.** chi's trie searches **static before param** (`ntStatic < ntParam`), so a static
`"/maps"` segment DOES win — but this is exactly the kind of thing that silently works in dev and 404s
under a different chi version. **W8-08 MUST ship a route test that asserts `GET /v1/worlds/maps/<uuid>`
reaches `getWorldMap` and NOT `getWorld` with `world_id="maps"`.** (Test name given in the slice.)

🔴 **SCOPE GATING ON EVERY CHILD ROUTE — the `gate-must-derive-scope-from-the-loaded-row` trap.** The
existing MCP removes take **only** a `marker_id` (`mcp_maps.go:411`) — the REST routes take **both** `map_id`
and `marker_id` in the path. A marker id from *another* map, addressed under *your* map id, **must 404, not
patch.** Express it in SQL exactly as the existing deletes do (`mcp_maps.go:432`):
```sql
UPDATE map_markers m SET … FROM world_maps wm
WHERE m.id = $1 AND m.map_id = $2 AND m.map_id = wm.id AND wm.owner_user_id = $3
```
— note **both** `m.map_id = $2` (the path's map) **and** the owner join — and treat `RowsAffected() == 0`
as the uniform not-found. Same for regions, and same for the DELETEs.

🔴 **AND THE SAME HOLE IS ON THE *CREATES* — the box above missed it** (`Q-38-CHILD-ROUTE-SCOPE-GATE` §2).
`map_markers` / `map_regions` have **no `owner_user_id` column** (`migrate.go:414-434`); ownership is
derivable **only** through `world_maps`. So a `VALUES` insert with a path-supplied `map_id` writes into
**anyone's** map. **Gate the INSERT with `INSERT … SELECT`, never `VALUES`:**
```sql
INSERT INTO map_markers (map_id, label, x, y, marker_type, entity_id)
SELECT wm.id, $2, $3, $4, $5, $6 FROM world_maps wm
WHERE wm.id = $1 AND wm.owner_user_id = $7
RETURNING id, map_id, label, x, y, marker_type, entity_id, created_at, updated_at;
```
0 rows inserted ⇒ **404**. Same for `map_regions`. **Binding rule for the whole slice: no SQL statement may
name `map_markers`/`map_regions` without joining `world_maps wm` and constraining `wm.owner_user_id`. There
is no pre-check SELECT — the gate IS the single statement** (no TOCTOU, no existence oracle).

🔴 **THE BACKEND NEVER CLAMPS — IT REJECTS (422). THE FRONTEND CLAMPS AT THE SOURCE**
(`Q-38-COORDS-RELATIVE-NEVER-PIXELS`). Write the coord guard in the **positive** form —
`!(x >= 0 && x <= 1)` — so **NaN / ±Inf fail too**; `x > 1` alone lets `NaN` straight through. A BE that
silently clamps `1.4 → 1.0` is a silent-success: the pin lands somewhere the user did not put it and nothing
says so. The canvas clamps the *gesture* (a drag cannot leave the image); the API rejects the *value*.

🔴 **CONTRACT FILE — `contracts/api/book-service/` DOES NOT EXIST.** Three places in the original draft
named it. **The real, live, maintained spec is `contracts/api/books/v1/openapi.yaml`** (`openapi: 3.0.3`,
title *LoreWeave Books API*, 21 paths, `components.securitySchemes.bearerAuth`). It has **no `/v1/worlds`
paths today** — Wave 8 adds them, under a new `worlds` tag. **Slice W8-0C freezes them BEFORE any FE slice
consumes them** (CLAUDE.md: *contract-first*).

---

## 4 · Migration — book-service, forward-only + idempotent

**File:** `services/book-service/internal/migrate/migrate.go` — append to the existing DDL block that
already creates `world_maps` / `map_markers` / `map_regions` (`:401-434`), in the house style.

🔴 **THE ORIGINAL 3-LINE DDL WAS WRONG AND HAS BEEN REPLACED** (`Q-38-MIGRATION-VERSION-UPDATEDAT`). It
added the two child `updated_at`s as `NOT NULL DEFAULT now()` — which **backfills every pre-existing marker
and region as "edited just now"**. §4's own rule then makes the inspector *render* that lie
(*"edited 4m ago"* on a pin nobody has touched in a year), and **`ADD COLUMN IF NOT EXISTS` never revisits
it**. Ship the four-statement form per child table: **add NULLABLE → backfill from `created_at` → default →
NOT NULL.** It is self-gating on re-run (the `IS NULL` predicate matches 0 rows on the second pass), so it
needs no migration marker table.

```sql
-- ═══════════════════════════════════════════════════════════════════════════════
-- Writing Studio Wave 8 / M8b.1 — world-map OCC + child updated_at (spec 38 §4.2)
-- `version`: the OCC baseline for BE-15d's If-Match rename (rare, human-paced,
--   conflict-worthy). Existing maps start at 1 → the FE's first GET can never
--   phantom-412. No backfill needed; DEFAULT 1 is correct for every existing row.
-- Markers/regions get NO version BY DESIGN: a positional write is a DRAG, and OCC
--   over a drag is a 412 storm (instant-commit-control-over-occ-entity-needs-
--   write-serialization). They are last-write-wins, serialized per-object-id on
--   the FE (W8-13).
-- `updated_at` on the CHILD tables: added NULLABLE, BACKFILLED FROM created_at,
--   THEN defaulted + NOT NULL — so a pre-existing marker reads its TRUE age, not
--   "edited just now". A blanket DEFAULT now() would render a false-fresh
--   timestamp in the inspector for every marker that ever existed.
-- ⚠ ADD COLUMN IF NOT EXISTS NEVER REVISITS A BAD DEFAULT — this shape is ONE-SHOT.
-- ═══════════════════════════════════════════════════════════════════════════════
ALTER TABLE world_maps  ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1;

ALTER TABLE map_markers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
UPDATE      map_markers SET updated_at = created_at WHERE updated_at IS NULL;
ALTER TABLE map_markers ALTER COLUMN updated_at SET DEFAULT now();
ALTER TABLE map_markers ALTER COLUMN updated_at SET NOT NULL;

ALTER TABLE map_regions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
UPDATE      map_regions SET updated_at = created_at WHERE updated_at IS NULL;
ALTER TABLE map_regions ALTER COLUMN updated_at SET DEFAULT now();
ALTER TABLE map_regions ALTER COLUMN updated_at SET NOT NULL;
```

- `world_maps` **already** has `updated_at` (`migrate.go:410`) — **do not re-add it.** `version INT` (not
  BIGINT) is right; renames are human-paced.
- **NO TRIGGER.** book-service maintains `updated_at` **in the handler** (`maps_image.go:108` already does
  `UPDATE world_maps SET … updated_at=now()`). Every new PATCH sets it in the same statement.
- No new enum, no CHECK constraint, no partial unique index ⇒ the other three migration traps
  (backfill-every-CHECK-block · exempt-tombstones · repeat-the-partial-predicate-in-ON-CONFLICT) do not
  apply here. Stated so a reviewer does not go looking.
- 🔴 **The migration test that pins the non-obvious part** (`migrate_test.go`, house pattern at
  `TestSchemaAddsKGIndexingColumns:143` / `TestSchemaC20AdditionsAreIdempotent:318`): seed a `map_markers`
  row with `created_at = now() - interval '3 days'`, re-run `schemaSQL`, assert
  **`updated_at == created_at`, NOT ≈ `now()`**. Plus: apply `schemaSQL` **twice** against real PG → no
  error (idempotence).

🔴 **`updated_at` must be READ, or this ships a write-only column** — the exact bug class CLAUDE.md bans.
In the **same** wave: **(a)** every PATCH handler sets `updated_at = now()`; **(b)** BE-15c returns it on
each marker/region and BE-15b returns `version` per map; **(c)** the `world-map` inspector **renders** it
(*"edited 4m ago"*). A Go test asserts the timestamp **advances** across a PATCH (`W8-09`).

🔴 **IT IS WORSE THAN THAT — THREE COLUMNS ARE *ALREADY* WRITE-ONLY AT HEAD. FIX ALL THREE IN W8-08.**
(`Q-38-UPDATEDAT-MUST-BE-READ` + `Q-38-OQ8-WEBP-NULL-PIXEL-DIMS`.)

| Column | Written by | Read by | Consequence |
|---|---|---|---|
| `world_maps.updated_at` | nobody (`grep -n "updated_at" internal/api/mcp_maps.go` → **ZERO hits**) | nobody | exists since day 1, dead |
| `world_maps.image_w` | `maps_image.go:107-110` | 🔴 **NOBODY.** `worldMapDetail` (`mcp_maps.go:73-79`) has **no `ImageW`/`ImageH` fields**; `world_map_get` (`:264`) and `world_map_list` (`:350`) **never SELECT them** | the upload response is the **only** place dims are ever returned ⇒ the inspector shows them right after upload and **loses them on reload — for EVERY format, not just WebP** |
| `world_maps.image_h` | same | same | same |

**W8-08 must add `Version int`, `UpdatedAt time.Time`, `ImageW *int`, `ImageH *int` to `worldMapDetail` and
put `version, updated_at, image_w, image_h` into BOTH SELECTs.** Pointers on the dims — WebP legitimately
stores NULL (no stdlib decoder, `maps_image.go:16-19`), **and so does every map created via
`world_map_create` with an `image_ref`** (`mcp_maps.go:116-118` inserts the object key with no dims at all).
**NULL dims are NOT webp-specific.**
- 🟢 **WebP decoder: CONSCIOUS WON'T-FIX, and NO defer row** (a row costs more than the finding is worth).
  Do **not** add `golang.org/x/image/webp` — it is not in `go.mod`, and it would **not** eliminate the NULL
  case anyway (see the `image_ref` path above). The FE guard is required **unconditionally**; the decoder
  buys nothing the guard doesn't already handle.
- 🔴 **Never fabricate a fallback dimension** (e.g. `1000×1000`). A made-up dimension is worse than an
  absent one. Coords are relative `[0,1]`; nothing in the render path divides by the dims, so a NULL is
  **never** a correctness hazard — only a cosmetic one.

---
## 5 · THE SLICES — each slice is ONE commit

**Order is dependency order. Do not reorder. A panel slice never precedes its route slice.**

| Slice | Kind | Title | dependsOn |
|---|---|---|---|
| **W8-00** | DOC | Track C ownership write-down (the 8b gate) | — |
| **W8-0C** | 🔴 **CONTRACT** | **Freeze all 16 new routes in OpenAPI — BEFORE any consumer** | — |
| **W8-01** | BE | BE-14c + BE-14d — one authorable-kind set, three schema sources | W8-0C |
| **W8-02** | FE | A1 — create an entity in `kg-entities` (+ BE-14f `created:bool`) | W8-01 |
| **W8-03** | FE+BE | A2 — the third verb on `RelationEditDialog` + `PredicateControl` + **BE-14e** + **OQ-10 edge delete** | W8-01 |
| **W8-04** | FE | A5 — kill the three dead buttons | — |
| **W8-05** | BE | BE-14a + BE-14a2 + BE-14b + **BE-14b2 (restore)** + BE-14b3 | W8-0C |
| **W8-06** | FE | A3 `ProjectionResultCard` + A4 forget/**un-forget** + the `memory_*` Lane-B handler | W8-05 |
| **W8-07** | TEST | `studio-kg-write.spec.ts` — the 8a LIVE BROWSER smoke | W8-02, W8-03, W8-04, W8-06 |
| **W8-08** | BE | book-service: the migration + maps REST reads/create/delete | W8-00, W8-0C |
| **W8-09** | BE | book-service: the UPDATE semantics (PATCH ×3) + marker/region create+delete | W8-08 |
| **W8-10** | BE | BE-15f public image upload + **retire** the dead internal route | W8-08 |
| **W8-11** | BE | BE-15m — 3 new MCP update tools (agent parity, GG-2) | W8-09 |
| **W8-12** | FE | the `world` container panel + `studioLinks` (**4 files**) + GG-8 registration (+1) | W8-08 |
| **W8-13** | FE | the `world-map` panel + GG-8 registration (+1) + `worldEffects` Lane-B | W8-09, W8-10, W8-12 |
| **W8-14** | TEST | `studio-world-map.spec.ts` — the 8b LIVE BROWSER smoke | W8-11, W8-13 |
| **W8-16** | 🔴 **FE** | **the `cast` panel** — CastCodexPanel, homed (§5.4) | W8-02 |
| **W8-17** | 🔴 **FE** | **the `character-arc` panel** — CharacterArcView, homed (§5.4) | W8-16 |
| **W8-18** | 🔴 **FE** | **the `canon-growth` panel** — FlywheelPanel, homed (§5.4) | W8-16 |
| **W8-19** | TEST | `studio-kg-codex.spec.ts` — the codex-trio LIVE BROWSER smoke | W8-16, W8-17, W8-18 |
| **W8-15** | DOC | `/review-impl` on the wave diff + fix everything it finds + SESSION_HANDOFF | **all** (runs LAST) |

⚠ **W8-15 keeps its id but is now the LAST slice** (it depends on *all*, including W8-16..19). The ids are
stable handles, not an ordering — **read the `dependsOn` column, not the number.**

---

### W8-0C · [CONTRACT] 🔴 Freeze the route contracts — **BEFORE** any consumer

**Why this slice exists.** CLAUDE.md: **"Contract-first: API contract frozen before frontend flow."** This
wave adds **~16 new routes** across two services and the original plan touched **zero** contract files —
and it named `contracts/api/book-service/` **three times**. **That directory does not exist.** A completeness
critic caught it; do not re-introduce the phantom path.

**The two real files (verified on disk, 2026-07-13):**

| Service | File | State |
|---|---|---|
| book-service | **`contracts/api/books/v1/openapi.yaml`** | live, `openapi: 3.0.3`, *LoreWeave Books API* v1.5.0, **21 paths**, `bearerAuth` in `components.securitySchemes`, tags `books` + `chapters`. **It has ZERO `/v1/worlds` paths.** Wave 8 adds them under a **new `worlds` tag** and bumps `info.version` to `1.6.0`. |
| knowledge-service | **`contracts/api/knowledge-service/kg_authoring.yaml`** — **NEW FILE** | The dir holds 4 domain-split specs (`benchmark` · `ontology` · `triage` · `views`) and **none** documents `/v1/knowledge/entities`, `/relations`, `/facts` or `/projects/*`. Follow the house split: one new domain file for the **authoring** surface. Copy `views.yaml`'s header shape (`openapi: 3.0.3`, `servers:` → gateway, a prose `description` naming this plan + spec 38, `bearerAuth`). |

> ⚠ **`contracts/api/composition-service/plan-forge.v1.yaml` and `contracts/api/composition/v1/openapi.yaml`
> are NOT ours.** Wave 8 touches **zero** composition contracts. Do not open them.

**What to write — every route, with path · method · request schema · response schema · error codes.**

**A · `contracts/api/books/v1/openapi.yaml`** — add `- name: worlds` to `tags:`, then the 12 BE-15 paths from
§3.2, plus these schemas under `components.schemas`: `WorldMap` (`map_id, world_id, name, image_object_key
(nullable), image_url (nullable), image_w (nullable int), image_h (nullable int), version (int), created_at,
updated_at`) · `WorldMapListItem` (`WorldMap` + `marker_count` + `region_count`) · `MapMarker` (`marker_id,
map_id, label, x (0..1), y (0..1), marker_type (nullable), entity_id (nullable uuid — 🔴 **a GLOSSARY entity
id**), created_at, updated_at`) · `MapRegion` (…, `polygon: array[array[number]]`, ≥3 points) ·
`MapMarkerPatch` / `MapRegionPatch` (🔴 **`nullable: true` on `entity_id` + `marker_type` — an explicit
`null` is the CLEAR verb; an ABSENT key is "unchanged". Say that in the schema `description`, because
OpenAPI cannot express it structurally**) · `WorldMapCreate` · `WorldMapRename`.
- 🔴 On **BE-15d** declare `parameters: [{in: header, name: If-Match, required: true, schema: {type: string}}]`
  and the **`428`** + **`412`** responses. **The 412's body is the CURRENT `WorldMap`, bare** — the same
  schema as the 200, **not** an error envelope. Add `headers: {ETag: {schema: {type: string}}}` to 200/412
  (and to BE-15b/BE-15c, which is where the FE *gets* its baseline).
- 🔴 On **BE-15f** declare `requestBody: multipart/form-data` with a binary `file`, and responses
  `200 · 401 · 404 · 413 · 415 · 503`.
- Error codes, uniform: `401 BOOK_FORBIDDEN` · `404 MAP_NOT_FOUND` / `MARKER_NOT_FOUND` / `REGION_NOT_FOUND`
  / `WORLD_NOT_FOUND` (**one body for foreign-or-missing — no enumeration oracle**) · `422 BOOK_VALIDATION_ERROR`
  / `WORLD_MAP_INVALID` · `428 MAP_PRECONDITION_REQUIRED`.
- **Also DELETE** any documentation of `POST /internal/worlds/maps/{map_id}/image` if it exists (it does not
  today — W8-10 retires the route).

**B · `contracts/api/knowledge-service/kg_authoring.yaml`** (NEW) — the **10** knowledge routes this wave
touches:

| Path | Method | New? |
|---|---|---|
| `/v1/knowledge/entity-kinds` | GET | 🔴 BE-14c |
| `/v1/knowledge/entities` | POST | EDIT — response gains `created: bool` (BE-14f) |
| `/v1/knowledge/entities/{entity_id}/facts` | GET | EDIT — `?include_invalidated` (BE-14b3); `Fact.valid_until` |
| `/v1/knowledge/relations` | POST | EDIT — **422** on an off-schema predicate (BE-14e) |
| `/v1/knowledge/relations/correct` | POST | EDIT — same 422 |
| `/v1/knowledge/relations/{relation_id}` | GET | document the existing route (W8-03 consumes it) |
| `/v1/knowledge/relations/{relation_id}/invalidate` | POST | document the existing route |
| `/v1/knowledge/facts/{fact_id}/invalidate` | POST | 🔴 BE-14b |
| `/v1/knowledge/facts/{fact_id}/restore` | POST | 🔴 BE-14b2 |
| `/v1/knowledge/projects/{project_id}/project-entities` | POST | 🔴 BE-14a |
| `/v1/knowledge/predicate-labels` | GET | document the existing route (W8-03 consumes it) |

Schemas: `EntityKinds {kinds: [string] enum(character|concept|faction|location)}` ·
`CreateEntityResponse` (= `Entity` + **required** `created: boolean`) · `FactInvalidateResponse
{invalidated: boolean (required), fact_id: string (required), reason: string|null}` ·
`FactRestoreResponse {restored, fact_id}` · 🔴 **`ProjectEntitiesResponse` — `nodes_created`,
`nodes_existing`, `entities_seen`, `skipped`, `nodes_conflicted`, `truncated` ALL in `required:`; `note` the
only nullable key.** (`required:` is the contract-level expression of the zero-fill rule that R-6 exists to
protect.) · `PredicateRejected {error, predicate, allowed: [string]}`.
Errors: `401` · `404` (uniform) · `409` `{code: KG_PROJECT_NOT_LINKED_TO_BOOK, message}` · `422` · `503`.

**Tests / verification** (a contract slice still has a DoD — a YAML nobody parses is a lie):
```bash
cd d:/Works/source/lore-weave-mvp
npx @redocly/cli lint contracts/api/books/v1/openapi.yaml
npx @redocly/cli lint contracts/api/knowledge-service/kg_authoring.yaml
# If redocly is unavailable, ANY OpenAPI 3.0 validator is fine (python -m openapi_spec_validator …).
# It MUST parse and MUST resolve every $ref. A spec with a dangling $ref is not frozen, it is decorative.
```
🔴 **Then, at the END of W8-08/09/10 and W8-05, RE-READ this file and diff it against what you actually
built.** A contract written first and never re-checked is the same drift with extra steps. Any divergence:
**the contract is the spec — change the CODE**, unless the code is right and the contract was wrong, in which
case fix the contract **in that slice's commit**.

**DoD evidence:** `"W8-0C: contracts/api/books/v1/openapi.yaml +12 world-map paths under a new 'worlds' tag (incl. If-Match/428/412 + ETag headers on BE-15d and the multipart 413/415/503 on BE-15f); contracts/api/knowledge-service/kg_authoring.yaml NEW with 11 paths (BE-14a/b/b2/b3/c/e/f + the 4 documented-existing). Both lint clean (<validator> — 0 errors, 0 dangling $ref). ProjectEntitiesResponse pins all six counters in `required:`. contracts/api/book-service/ was a PHANTOM path and appears nowhere."`

**dependsOn:** —

---

### W8-00 · [DOC] Track C ownership write-down — the 8b gate

**Why:** plan 30 §9 forbids starting 8b without an explicit ownership handoff for the `world` container
(Track C's P-5 claims "W10 world container"). **This is a write-down, not a negotiation** — the evidence is
already in (§1.2 G4). Do it, commit it, move on. **10 minutes. It is NOT a reason to stop and ask.**

**Files**
- `docs/sessions/SESSION_HANDOFF.md` — **EDIT.** Add to the ▶ NEXT SESSION block:

> **Wave-8 / Track-C ownership — RESOLVED 2026-07-13.** The `world` container panel (Track C P-5's
> "W10 world container") is **built by Writing-Studio Wave 8**, per spec
> `docs/specs/2026-07-01-writing-studio/38_kg_and_world.md` §3.2. Evidence: Track C's P-5 is **PARKED**
> under gate #2 with **no design and no code** (`2026-07-12-track-c-completion-RUN-STATE.md:172-177, :212`;
> `grep "'world'" frontend/src/features/studio/panels/catalog.ts` → zero hits). Spec 38 **has** the design
> (self-resolving from the book's `world_id`, category `storyBible`, bare-id openable). Track C's P-5
> retains: the **workflow rack**, the **binding UI**, the **W8 onboarding fork**, and the **W11 reader** —
> Wave 8 does **not** touch those (plan 30 PO-2).

- `docs/plans/2026-07-12-track-c-completion-RUN-STATE.md` — **EDIT.** In the P-5 row, strike "W10 world
  container" and add `→ taken over by Writing-Studio Wave 8 (spec 38), 2026-07-13`.

**Tests:** none (doc-only).

**DoD evidence:** `"W8-00: ownership write-down committed — SESSION_HANDOFF + Track C RUN-STATE both name Wave 8 as the owner of the world container; Track C keeps workflow rack + binding UI + onboarding fork + reader"`

**dependsOn:** —

---

### W8-01 · [BE] BE-14c + BE-14d — one authorable-kind set, three schema sources

**The bug this closes (GG-2 inverse gap #1):** the **agent** can mint a KG node of **any** `kind`
(`KgCreateNodeArgs.kind: str = Field(min_length=1, max_length=100)`), while the **human** REST route is
capped at 4 (`_AUTHORABLE_KINDS`). The agent can create a `kind:"item"` node the human cannot. And the FE
has no home for the closed set at all.

> **▶ DECISIONS FOLDED:** `Q-38-BE-14c-ENTITY-KINDS-ROUTE` · `Q-38-BE-14d-UNIFY-AUTHORABLE-KINDS` ·
> `Q-38-M8A1-SIZING-REORDER`. 🔴 **CONTRADICTION FIXED:** the draft put the constant in
> `app/tools/argbase.py`. The register says **`app/entity_kinds.py`** — a *top-level leaf module* (beside
> `pricing.py` / `effort.py` / `spoiler_window.py`), because `argbase.py` lives under `tools/` and importing
> it from `routers/` risks a **router↔tools import cycle**. The register also adds a **shared normalizer**
> the draft missed: today the tool **strips** the kind and REST **does not**, so `" Character "` passes one
> transport and 422s the other.

**Files**

1. **`services/knowledge-service/app/entity_kinds.py`** — **NEW FILE.** The ONE HOME. *(Not `argbase.py` —
   see the CONTRADICTION note above.)*
   ```python
   """BE-14d — the ONE closed set of entity kinds a HUMAN (REST) or an AGENT (MCP) may
   author directly into the KG.

   TENANCY: System-tier, admin-owned, READ-ONLY (CLAUDE.md User Boundaries). No per-user
   tier, no write route — ever.

   ⚠ NOT glossary-service's `entity_kinds` (which were RENAMED to `system_kinds` in
   glossary/internal/migrate/migrate.go:23 precisely because of the tenancy bug — those
   are per-user/per-book and EDITABLE). Different object, same word. Do NOT unify them,
   do NOT join them, do NOT name this route /v1/kinds.

   Consumed by: (1) the REST create validator, (2) BE-14c's kinds route, (3)
   kg_create_node's pydantic arg model, (4) kg_create_node's OpenAI JSON schema, (5)
   kg_create_node's FastMCP signature. A 6th hand-copy is a review finding.
   """
   from typing import Literal, get_args

   AuthorableEntityKind = Literal["character", "concept", "faction", "location"]
   AUTHORABLE_ENTITY_KINDS: tuple[str, ...] = get_args(AuthorableEntityKind)  # alphabetical = the WIRE order

   def normalize_entity_kind(v: object) -> object:
       """Pydantic `mode='before'` normalizer — ONE normalization for BOTH transports.
       Today the tool strips and REST does not, so ' Character ' passes one and 422s the other."""
       return v.strip().lower() if isinstance(v, str) else v
   ```
   ⚠ The values are **exactly** today's `_AUTHORABLE_KINDS` (`entities.py:975`) — `{"character","location",
   "faction","concept"}`. **Do not add or remove one.** (`item`, `organization`, `event_ref`, `preference`
   appear in extraction output and in `EntitiesTab.KIND_OPTIONS` — they are **NOT** authorable. See the
   ⚠ box under W8-02.)
   🟢 **NARROW, do not WIDEN** (`Q-38-BE-14d`): `seed_graph_schemas.py:93-103` seeds **8** graph node-kinds
   incl. `item`. **Do not widen `kg_create_node` to those.** For `item`/`event`/`organization` the sanctioned
   path is *author-in-glossary → `kg_project_entities_to_nodes`* — which is also the **anchored** path A1
   already tells the human to prefer. `kg_create_node` is an unblock-an-endpoint escape hatch, **not** the
   lore-authoring door.
   📌 **For the register, not this slice** (gate #1, out of scope — do NOT silently rename anything):
   `faction` is glossary's **alias** for the canonical `organization` (`glossary/internal/migrate/migrate.go:203`
   seeds `('faction','organization')`), and knowledge's `concept` maps to glossary's `terminology`
   (`entity_resolver.py:69-74`). So a manually-authored `faction` node carries a kind_code that will **never
   anchor**. Pre-existing KG↔glossary vocabulary drift. **File it; do not fix it here.**

2. **`services/knowledge-service/app/routers/public/entities.py`** — **EDIT.**
   - `:975` — replace `_AUTHORABLE_KINDS = {...}` with an import of `AUTHORABLE_ENTITY_KINDS` and
     `_AUTHORABLE_KINDS = frozenset(AUTHORABLE_ENTITY_KINDS)`. **Keep the name** so `:992` and the error
     string at `:994` are untouched (the FE surfaces that message verbatim).
   - `CreateEntityRequest` (`:977-996`) — `kind: str = Field(min_length=1, max_length=50)` becomes
     `kind: AuthorableEntityKind` **+** `@field_validator("kind", mode="before")(normalize_entity_kind)`.
     Drop the manual `if self.kind not in …` branch from `_validate` (**keep the blank-name check**). The
     wire text stays a 422 naming the set.
   - **NEW ROUTE (BE-14c)** — add to `entities_router`, **ABOVE** the `/entities/{entity_id}` routes so a
     literal `entity-kinds` segment cannot be swallowed by an `{entity_id}` param:
     ```python
     @entities_router.get("/entity-kinds")
     async def list_authorable_entity_kinds(
         user_id: UUID = Depends(get_current_user),
     ) -> dict:
         """BE-14c — the closed set of kinds a user may author (the `+ New entity` <select>'s ONE
         source of truth; a hand-copied FE array is the cross-service drift the Frontend-Tool-Contract
         discipline exists to kill).

         TENANCY: a **System-tier, read-only, admin-owned constant**. There is no per-user tier and
         **no write route** (CLAUDE.md User Boundaries). ⚠ NAME COLLISION: glossary-service ALSO has
         `entity_kinds`, and THOSE are per-user/per-book and user-EDITABLE (this repo's canonical
         tenancy bug). Different objects. The `/v1/knowledge/` prefix keeps them apart — DO NOT
         "unify" them.
         """
         return {"kinds": list(AUTHORABLE_ENTITY_KINDS)}   # the tuple IS the wire order; do NOT sorted(set) per request
     ```
     Auth = the router-level `Depends(get_current_user)` → 401 without a JWT. **No grant dep** (it is a
     constant, not a project resource). **No `Cache-Control`/ETag** — a 4-element constant behind an authed
     proxy; a normal TanStack cache is enough (`Q-38-BE-14c`, veto-able default).

3. **`services/knowledge-service/app/tools/graph_schema_tools.py`** — **EDIT, TWO places (BE-14d 1/3 + 2/3).**
   - `:451-463` — `class KgCreateNodeArgs`: `kind: str = Field(min_length=1, max_length=100, …)` →
     `kind: AuthorableEntityKind = Field(description="the entity kind (closed set)")` **+ the same
     `@field_validator("kind", mode="before")(normalize_entity_kind)`**. **Drop `min_length`/`max_length`** —
     they are invalid on a `Literal`.
   - `:828-850` (properties) **and `:829-833` (the tool DESCRIPTION prose)** — replace the `kind` property
     `{"type":"string","minLength":1,"maxLength":100,"description":"…e.g. 'character', 'location', 'faction', 'item'"}`
     with `{"type":"string","enum":list(AUTHORABLE_ENTITY_KINDS),"description":"the entity kind (closed set)"}`.
     🔴 **Delete `'item'` from BOTH the property description AND the tool description.** After the `Literal`,
     an `item` example is a **guaranteed 422 the model will walk straight into** — and it was the tell.
   - `:1720-1723` (the handler) — `kind = args.kind` (already normalized). The `not kind` half of the
     non-empty guard is now **dead**; keep the `name` half.

4. **`services/knowledge-service/app/mcp/server.py`** — **EDIT (BE-14d 3/3).** `:1123-1130`, the
   `kg_create_node` function signature — **and delete `'item'` from its description at `:1115-1116` too**:
   ```python
   kind: Annotated[AuthorableEntityKind, "the entity kind — one of: character, concept, faction, location"],
   ```
   🔴 **THIS THIRD EDIT IS THE ONE THAT ACTUALLY BINDS THE WIRE.** FastMCP generates the MCP tool schema
   from the **function signature** and **STRIPS** whatever the pydantic arg model says
   (`knowledge-mcp-three-schema-sources-fastmcp-strips`). Edit 1/3 alone = the executor rejects a bad kind
   *after* the model already sent it. Edit 3/3 = the model is never offered it in the first place.

**Tests** (TDD — write these FIRST, watch them RED)

- **`services/knowledge-service/tests/unit/test_entity_kinds_route.py`** (NEW)
  - `test_entity_kinds_returns_the_four_authorable_kinds` — `GET /v1/knowledge/entity-kinds` → 200, body
    `{"kinds": ["character","concept","faction","location"]}` (sorted, exactly 4).
  - `test_entity_kinds_requires_auth` — no JWT → 401.
  - `test_entity_kinds_route_is_not_shadowed_by_entity_id` — asserts the response is the kinds list, **not**
    a 404/422 from `GET /entities/{entity_id}` trying to parse `entity-kinds` as an id.

- **`services/knowledge-service/tests/unit/test_authorable_kinds_one_home.py`** (NEW) — 🔴 **the drift-lock.
  This is the test that makes BE-14d stick. All four assertions in ONE test.**
  ```python
  import typing
  from app.entity_kinds import AUTHORABLE_ENTITY_KINDS          # ← the ONE home (NOT app.tools.argbase)
  from app.routers.public.entities import _AUTHORABLE_KINDS
  from app.tools.graph_schema_tools import KgCreateNodeArgs, GRAPH_SCHEMA_TOOL_DEFINITIONS
  import app.mcp.server as mcp_server

  def test_rest_and_pydantic_and_json_schema_and_mcp_signature_all_agree():
      expected = set(AUTHORABLE_ENTITY_KINDS)
      assert set(_AUTHORABLE_KINDS) == expected                                                 # 1 REST validator
      assert set(typing.get_args(KgCreateNodeArgs.model_fields["kind"].annotation)) == expected  # 2 pydantic arg model
      tool = next(t for t in GRAPH_SCHEMA_TOOL_DEFINITIONS
                  if t["function"]["name"] == "kg_create_node")
      assert set(tool["function"]["parameters"]["properties"]["kind"]["enum"]) == expected       # 3 OpenAI JSON schema
      hints = typing.get_type_hints(mcp_server.kg_create_node, include_extras=True)
      assert set(typing.get_args(typing.get_args(hints["kind"])[0])) == expected                 # 4 FastMCP signature
      # 5 — and BE-14c's ROUTE must serve the same set (a 5th surface, and the one the FE reads)
  ```
  - `test_kg_create_node_rejects_an_offset_kind` — `execute_tool(ctx, "kg_create_node", {"name":"Sword",
    "kind":"item"})` → `res.success is False` **and the error names the closed set**. Assert through
    `execute_tool`, not just the model — that is the surface the agent actually hits. **Today it SUCCEEDS —
    that is the inverse gap. Watch it go RED first.**
  - 🔴 `test_kind_is_normalized_identically_on_both_transports` (`Q-38-BE-14d` §5) —
    `kg_create_node {"kind": " Character "}` **and** `POST /v1/knowledge/entities {"kind": "Character"}`
    **both succeed** and **both persist `character`**. *(Today the tool strips and REST does not: one passes,
    one 422s. This test is the whole point of `normalize_entity_kind`.)*
  - `test_tool_count_is_unchanged` — BE-14d adds **no** tool; the existing `test_tool_count == 37` must stay
    green.

- **`services/knowledge-service/tests/unit/test_graph_schema_tools.py`** — **EDIT.** Any existing case that
  builds `KgCreateNodeArgs(kind="item"/"thing"/…)` will now red. **Fix the FIXTURE to a real kind — do NOT
  widen the Literal to make the old test pass.**

**Run:** `cd services/knowledge-service && python -m pytest tests -q -n auto --dist loadgroup`

**DoD evidence:** `"W8-01: knowledge pytest <N> passed. test_authorable_kinds_one_home::test_rest_and_pydantic_and_json_schema_and_mcp_signature_all_agree PASSED — all 4 surfaces expose {character,concept,faction,location}. GET /v1/knowledge/entity-kinds → 200 {'kinds':['character','concept','faction','location']}. KgCreateNodeArgs(kind='item') now raises ValidationError."`

**dependsOn:** —

---

### W8-02 · [FE] A1 — create an entity in `kg-entities`

**Surface:** a `+ New entity` button in **`EntitiesTab`**'s header
(`frontend/src/features/knowledge/components/EntitiesTab.tsx`, 322 lines) — the component `kg-entities`
mounts. **NO NEW PANEL ID.** DOCK-2 (no fork) + DOCK-8 (no new hub) both hold.

> **▶ DECISIONS FOLDED:** `Q-38-OQ5-MANUAL-NODE-NO-ANCHOR` (the anchor-warning copy — **the draft's was
> false**) · `Q-38-A1-SCOPED-PROJECT-REQUIRED` (gate on `effectiveProjectId`; **BE-14f `created: bool`**;
> leave `KgNoProjectState` alone) · `Q-38-BE-14c` §6 (the FE `<select>` reads the route, never an array).

> ⚠ **DO NOT REUSE `EntitiesTab.KIND_OPTIONS` FOR THE CREATE FORM.** That array (`EntitiesTab.tsx:24-32`)
> is the **filter** dropdown and holds **SEVEN** values — `character, location, organization, concept, item,
> event_ref, preference`. The **authorable** set is **FOUR** — and note **`faction`**, *not* `organization`.
> They are different sets on purpose (extraction emits kinds a human may not author). Reusing `KIND_OPTIONS`
> here would offer three kinds the BE **422s** on and rename a fourth. **The create `<select>` reads BE-14c
> and nothing else.**
> 🔴 **LEAVE `KIND_OPTIONS` WHERE IT IS — and add a one-line comment saying it is the BROWSE-FILTER
> vocabulary, not the write closed-set** (`Q-38-A1` §3), so `/review-impl` does not read it as the very drift
> BE-14c exists to kill. Same for `composition/components/CastCodexPanel.tsx:11 KIND_ORDER` — that is a
> **display sort order**. Do not touch either.

> 🔴 **DO NOT put `KgNoProjectState` in `EntitiesTab`** (`Q-38-A1` §2). It takes a **required `bookId`**
> (`shell/KgNoProjectState.tsx:15-22`) that `EntitiesTab` does not have and cannot resolve, and
> `KgEntitiesPanel` **intentionally supports global cross-project browse** — a vitest pins that passthrough
> (`panels/__tests__/KgEntitiesPanel.test.tsx:56-59`). The correct empty state in the unscoped tab is **the
> disabled button + its tooltip**. **Leave `KgEntitiesPanel.tsx` untouched.**

**Files**

0. 🔴 **`services/knowledge-service/app/routers/public/entities.py`** — **EDIT (BE-14f — a BE change inside
   an "FE" slice; it lands first).** Make the honest *"already exists"* message **possible**:
   - `class CreateEntityResponse(Entity): created: bool` — **ALWAYS present**, never a conditional key (the
     same wire rule BE-14a's counters live under).
   - In the handler, **inside the existing `neo4j_session()`**, **before** `merge_entity`:
     ```python
     canonical_id = entity_canonical_id(
         user_id=str(user_id), project_id=str(body.project_id),
         name=body.name.strip(), kind=body.kind, canonical_version=1,
     )                                              # import from app.db.neo4j_repos.canonical
     existing = await get_entity(session, user_id=str(user_id), canonical_id=canonical_id)
     created = existing is None
     ```
     `get_entity` is **already imported** at `:41`; `canonicalize_entity_name` is already imported at `:28`.
   - Still call `merge_entity` **unchanged** — 🔴 **DO NOT touch `_MERGE_ENTITY_CYPHER`; the extractors
     depend on it.** Take `response: Response` and set `response.status_code = 200` when `not created`
     (the route default stays 201).
   - `return CreateEntityResponse(**entity.model_dump(exclude={"status"}), created=created)` — `status` is a
     `computed_field`; passing it as a kwarg **raises**.
   - ⚠ **Existing-consumer safety:** `composition/hooks/useWorldMap.ts:129` calls `createEntity` and **ignores
     the body**, so the additive `created` field and the 200-on-existing are backward compatible.
   - ⚠ **Existing test will break:** `tests/unit/test_world_map_authoring_api.py::test_create_entity_happy`
     (`:88`) patches only `merge_entity` — it must **also** patch
     `app.routers.public.entities.get_entity` (`AsyncMock` → `None`) or it hits the noop session. Assert
     `201` + `created is True`, and add the sibling: `get_entity` returns a stub ⇒ `200` + `created is False`.

1. **`frontend/src/features/knowledge/hooks/useAuthorableKinds.ts`** — **NEW** (≤30 lines).
   `useQuery({ queryKey: ['knowledge-entity-kinds'], queryFn: () => knowledgeApi.listAuthorableKinds(token), staleTime: Infinity })`
   — it is a System-tier constant; it does not change at runtime. Returns `{ kinds, isLoading, error }`.

2. **`frontend/src/features/knowledge/api.ts`** — **EDIT.** One method, next to `createEntity` (`:1600`):
   ```ts
   /** BE-14c — the closed set of kinds the manual-create path accepts (System-tier, read-only). */
   listAuthorableKinds(token: string): Promise<{ kinds: string[] }> {
     return apiJson<{ kinds: string[] }>(`${BASE}/entity-kinds`, { token });
   },
   ```

3. **`frontend/src/features/knowledge/hooks/useCreateEntity.ts`** — **NEW** (≤50 lines). Same shape as
   `useRelationMutations.ts` (mutation + `options.onSuccess/onError`).
   - `mutationFn: (payload) => knowledgeApi.createEntity(payload, accessToken!)` — **`createEntity` already
     exists** (`api.ts:1600`). Do **not** rewrite it.
   - `onSuccess` → invalidate **ALL THREE**: `['knowledge-entities']`, `['knowledge-subgraph']`,
     `['knowledge-projects']` (the project stat card's `entity_count`).
     ⚠ **`useRelationMutations`'s `useDetailInvalidation()` invalidates ONLY `['knowledge-entity-detail']` —
     that is NOT enough for a create.** The new node must appear in the **list** and on the **graph canvas**.
     Invalidating the wrong key = a write that lands and a UI that never shows it.

4. **`frontend/src/features/knowledge/components/CreateEntityDialog.tsx`** — **NEW** (≤100 lines).
   **Use `FormDialog` from `@/components/shared`** (the DOCK-9 exemption; `RelationEditDialog.tsx` is the
   skeleton to copy).
   - **Form:** `name` — `<input type="text" maxLength={200}>`, `data-testid="create-entity-name"`.
     `kind` — a **`<select>`** fed from `useAuthorableKinds()`, `data-testid="create-entity-kind"`.
     **Never a free text.**
   - **Submit** — `data-testid="create-entity-submit"`, disabled while `!name.trim() || !kind || busy`.
   - 🔴 **THE ANCHOR WARNING — IT MUST BE IN THE UI, not just in this plan** — and 🔴 **THE DRAFT'S COPY WAS
     FACTUALLY FALSE. SHIP THIS STRING, NOT THAT ONE** (`Q-38-OQ5-MANUAL-NODE-NO-ANCHOR`). Render a
     **persistent one-line note inside the form** (not a toast), above the buttons,
     `data-testid="create-entity-anchor-warning"`, i18n key `knowledge.createEntity.anchorNote`, EN copy
     **EXACTLY**:
     > *"This creates a graph-only node — it carries no glossary link. Authoring lore? Create it in the
     > **glossary** and press **Seed from glossary**, which anchors it. A later seed adopts this node only if
     > the name AND kind match exactly — otherwise you get two nodes for the same thing."*

     …with **glossary** as a button calling `onOpenGlossary()` (a prop; the panel passes
     `() => host.openPanel('glossary')`).

     🔴 **DO NOT say "conflicted". DO NOT say "shadow".** The draft's *"it can SHADOW a glossary entity a
     later projection tries to anchor (→ conflicted)"* is **wrong against the code**, and shipping it puts a
     false claim in front of the user:
     - manual create (`merge_entity`, `entities.py:339-347`) and the projection
       (`upsert_glossary_anchor_counted`, `:568-575`) derive the **SAME**
       `entity_canonical_id(user_id, project_id, canonicalize_entity_name(name), kind, canonical_version)`,
       so a later projection **MERGE-MATCHES the manual node** and its `ON MATCH SET e.glossary_entity_id`
       (`:487-492`) **ADOPTS** it — counted as `existing`, not `conflicted`;
     - `entity_glossary_fk_unique` is **NULL-exempt** (`neo4j_schema.cypher:62-63,71`), so a NULL-FK manual
       node **cannot raise the `ConstraintError` that `conflicted` counts** (`anchor_loader.py:231-244`).
     - **`conflicted` is UNREACHABLE from a manual node.** The real hazard is narrower and the copy above
       names it exactly: a **DUPLICATE** node when the canonical name or the kind differ (and
       `_AUTHORABLE_KINDS` **is** narrower than the glossary's kind set).
     - **SPEC CORRECTION (do it, don't skip it — a false claim in a spec propagates):** edit
       `docs/specs/2026-07-01-writing-studio/38_kg_and_world.md` **line 117** (§3.1 A1) and **line 460**
       (OQ-5) to strike "can shadow … surfacing as `conflicted`" and replace with the code-grounded statement
       above, citing the file:line evidence.

     The form still exposes **only `name` + `kind`** — **no `glossary_entity_id` field.** A vitest asserts the
     submitted body has **no** `glossary_entity_id` key (it guards against a builder "helpfully" adding one).
   - **States, each rendered:**
     | State | Render |
     |---|---|
     | **no project** | the `+ New entity` button is **disabled** with a `title` tooltip: *"Pick a project first — a new entity needs one."* (the cross-project browse has no `scopedProjectId`) |
     | submitting | spinner on Submit, inputs disabled |
     | **an EXISTING node** | 🔴 the route is **IDEMPOTENT** on `(name, kind)` per project. The dialog must say **"already exists — opened it"**, **NOT "created"** — the `silent-success` rule cuts **both ways**. 🔴 **The draft told you to guess from the react-query cache. DO NOT. The BE makes the honest message IMPOSSIBLE today, so BE-14f FIXES THE BE** (`Q-38-A1-SCOPED-PROJECT-REQUIRED` §4): `create_entity_endpoint` (`entities.py:999-1032`) **hardcodes `status_code=201`** over `merge_entity` — a **silent MERGE** with **no created-vs-matched signal** (`_MERGE_ENTITY_CYPHER`, `entities.py:244`). Read **`res.created` from the BODY** (see BE-14f below). `apiJson` **discards the status code**, so the signal MUST ride in the body. |
     | 422 | surface the **BE message verbatim** (`kind must be one of [...]` / `name must not be blank`) |
     | 401 | *"Session expired — sign in again."* |
     | network error | an error line + a **Retry** button. **Never a fake success.** |

5. **`frontend/src/features/knowledge/components/EntitiesTab.tsx`** — **EDIT.**
   - `const [creating, setCreating] = useState(false);`
   - Header row (beside the search box): the `+ New entity` button, `data-testid="kg-entities-new"`,
     `disabled={!effectiveProjectId}` + the tooltip.
   - Mount `<CreateEntityDialog open={creating} onOpenChange={setCreating} projectId={effectiveProjectId}
     onOpenGlossary={onOpenGlossary} onCreated={(e) => setSelectedEntityId(e.id)} />` — selecting the new
     entity opens the **existing** `EntityDetailPanel`, so the user lands *on the thing they just made*.
   - Add `onOpenGlossary?: () => void` to `EntitiesTabProps`.
   - ⚠ **No `useEffect` anywhere in this** (CLAUDE.md: no useEffect for event handling). The dialog opens from
     the click handler; the selection is set from `onCreated`.

6. **`frontend/src/features/studio/panels/KgEntitiesPanel.tsx`** — **EDIT.** Pass
   `onOpenGlossary={() => host.openPanel('glossary')}`. *(If it has no `useStudioHost()` yet, add it —
   mirror `KgOverviewPanel.tsx:17`.)*

**Tests**

- **`frontend/src/features/knowledge/components/__tests__/CreateEntityDialog.test.tsx`** (NEW)
  - `renders a <select> of kinds from the BE, never a free-text input` — mock `useAuthorableKinds` → 4 kinds;
    assert `getByTestId('create-entity-kind').tagName === 'SELECT'` with exactly 4 `<option>`s, and that
    `queryByRole('textbox', { name: /kind/i })` is `null`.
  - 🔴 `an idempotent create does NOT claim a create` — resolve `{…, created: false}`; assert the copy is
    *"already exists — opened it"* and does **not** contain "Created". Then `{…, created: true}` ⇒ *"Created
    «name»"* + the new row is selected. **Branch on `res.created` (the BODY), never on 200-vs-201** —
    `apiJson` (`frontend/src/api.ts:80-100`) **drops the status code**.
  - 🔴 `the kind <select>'s options come from the mocked /entity-kinds` — assert **`faction` is present** and
    **`organization` is ABSENT**. *(That single pair is the `KIND_OPTIONS`-reuse drift guard.)*
  - `the submitted body has NO glossary_entity_id key` (`Q-38-OQ5`).
  - `a 422 surfaces the backend message verbatim` — reject with
    `Error("kind must be one of ['character', 'concept', 'faction', 'location']")`; assert that exact string
    is on screen.
  - `renders the glossary-anchor warning` — `getByTestId('create-entity-anchor-warning')` present.
- **`frontend/src/features/knowledge/components/__tests__/EntitiesTab.test.tsx`** (NEW or EDIT)
  - `the New entity button is disabled with no project` — no `scopedProjectId`, no filter ⇒
    `expect(getByTestId('kg-entities-new')).toBeDisabled()`.

**Run:** `cd frontend && npx vitest run src/features/knowledge`

**DoD evidence:** `"W8-02: vitest <N> passed. CreateEntityDialog renders a 4-option <select> fed from GET /v1/knowledge/entity-kinds (no free text, KIND_OPTIONS NOT reused); the glossary-anchor warning renders; an idempotent 201 does not claim a create; useCreateEntity invalidates knowledge-entities + knowledge-subgraph + knowledge-projects."`

**dependsOn:** W8-01

---
### W8-03 · [FE] A2 — create a relation: the **THIRD VERB** on `RelationEditDialog`

🔴 **DO NOT FORK `RelationEditDialog` (DOCK-2).** A relation dialog **already ships**
(`frontend/src/features/knowledge/components/RelationEditDialog.tsx`, mounted at
`EntityDetailPanel.tsx:621-627`) with **Correct** (re-predicate → `POST /relations/correct`) and **Mark
wrong** (invalidate → `POST /relations/{id}/invalidate`), over `hooks/useRelationMutations.ts`. And because
`EntityDetailPanel` is mounted by **BOTH** `EntitiesTab` (→ `kg-entities`) **and** `ProjectGraphView`
(→ `kg-graph`), that dialog is **already live in two panels**. **A2 is the missing THIRD VERB on that same
object.** One dialog, one hook, three verbs. **A second "new relation" modal is a fork and a review finding.**

#### 🔴 The predicate control — READ ALL OF THIS BEFORE YOU TYPE

**The problem.** `RelationEditDialog`'s **existing** Correct field is a **free-text
`<input maxLength={100}>`** (`RelationEditDialog.tsx:127-134`). Shipping *create* with a `<select>` beside
*correct* as a free string — **same object, same dialog** — is a closed-set/free-string **SPLIT BRAIN**, the
exact IN-\* violation this repo fixed `panel_id` for. **Both verbs use ONE control.**

**What the backend ACTUALLY does — and it is NOT what the spec assumed.** Spec 38 §3.1-A2 says *"a project
may have no adopted schema, so `schema.edge_types` can be `[]`"* and *"do NOT fall back to free text"*.
**Half right. The code says:**

- `GET /v1/knowledge/projects/{id}/schema` → `GraphSchemasRepo.resolve_for_project`
  (`app/db/repositories/graph_schemas.py:227-267`) — **a non-adopted project does NOT resolve to empty.** It
  falls back to the **System `general`** template (`:250-254`), which **has** edge types. So the "no adopted
  schema ⇒ dead `<select>`" fear is **mostly unfounded**.
- The **genuinely** empty case is a **BLANK** schema (`POST /projects/{id}/schema/blank` →
  `create_blank_project_schema`, `ontology.py:505-527`): a `scope='project'` row with **no edge types**;
  `resolve_for_project` finds *it* and returns `edge_types = []`. **Real and reachable.**
- 🔴 **AND `ResolvedSchema` CARRIES `allow_free_edges: boolean`** (FE type: `types/ontology.ts:199`; BE:
  `graph_schemas.py:257,263`). **The spec never accounted for this.** It is the ontology's **own** answer to
  *"may an off-ontology predicate be minted in this project?"* A project whose owner deliberately set
  `allow_free_edges: true`, given a GUI that **forbids** what its own schema **permits**, is a NEW inverse
  gap (the agent's `kg_propose_edge` could still mint one).
- ⚠ `edge_types` is **OPTIONAL** in the TS type (`edge_types?: EdgeType[]`) — handle `undefined`, not just `[]`.

**THE ADJUDICATED RULE — bake it in, do not re-open it:**

> **ONE component — `PredicateControl` — used by BOTH create and correct.** Its behaviour is driven entirely
> by the project's **resolved** schema:
>
> | `edge_types` | `allow_free_edges` | The control renders |
> |---|---|---|
> | non-empty | `false` | a `<select>` of `edge_types[].code`. **Nothing else.** |
> | non-empty | `true` | the same `<select>`, **plus** a final `+ custom predicate…` option that reveals an `<input maxLength={100}>` |
> | empty / `undefined` | `true` | the free-text `<input>` directly, with a muted note: *"This project's schema allows free edges."* |
> | empty / `undefined` | `false` | 🔴 **THE DEAD-FORM GUARD.** Render **NO input at all**. Render: *"This project has no ontology yet — adopt or create a schema first."* + a button `Open the schema panel` → `host.openPanel('kg-schema')`. **A `<select>` with zero options is a dead form with no error — the exact silent-no-op class this whole wave is hunting.** |
>
> This honours the spec's **intent** (one control, closed-set by default, **no split brain** — both verbs get
> identical rules) **without contradicting a shipped backend flag**. The escape hatch for a strict project is
> the schema panel, exactly as the spec says.

> 🟢 **THE REGISTER CONFIRMS THIS TABLE** — `Q-38-A2-EMPTY-ONTOLOGY` (the most detailed of the three
> predicate decisions) lands on the **identical** 3-branch rule, including row 4's dead-form guard
> (*"Do NOT fall back to free text in this branch — the schema explicitly forbids it"*). ⚠ The shorter
> `Q-38-OQ6` sketch says *"edge_types empty ⇒ free-text only"*, which would ship a form that **always 422s**
> once **BE-14e** lands (a closed schema with `edge_types: []` rejects **every** predicate). `A2-EMPTY-ONTOLOGY`
> is the binding one. **Recorded so nobody re-opens it.** The register also names the component `PredicateField`;
> we keep **`PredicateControl`** — one name, one concept, and it is the name in the tests below.

> 🔴 **AND THE OPTION SOURCE IS RICHER THAN THE DRAFT KNEW** (`Q-38-A2-DO-NOT-FORK-RELATIONDIALOG` §3 +
> `Q-38-A2-EMPTY-ONTOLOGY` §2). **Two feeds already ship and neither is consumed by the FE:**
> - **`GET /v1/knowledge/predicate-labels`** (`routers/public/labels.py:26`) — the **24-code curated
>   catalogue** (`labels/predicate_labels.py:28`), `?language=` for i18n labels. **No new backend route is
>   needed for the predicate select.** (BE-14c is entity-**kinds** — a different thing.)
> - **`ontologyApi.schemaObserved(projectId)`** (`api/ontology.ts:170-174` → `GET /projects/{id}/schema/observed`)
>   — the predicates **actually used in this project**, with counts.
>
> **Never hand-copy the predicate array into the FE.** In the free-text branch the `<datalist>` options are
> the **union** of `edge_types[].code` ∪ the curated catalogue ∪ the observed codes (sorted by `count` desc)
> — *that* is what kills the `friend_of` vs `is_friend_of` drift a bare input causes.
> 🔴 **AND: in `edit` mode the control MUST include the relation's CURRENT predicate as an option even when
> it is off-catalogue** (legacy free-string edges exist — the BE accepted them until BE-14e). Otherwise
> **opening the dialog silently rewrites an existing edge.**

**Files**

0. 🔴 **`services/knowledge-service/app/routers/public/relations.py`** — **EDIT (BE-14e — the BE half; ~40
   LOC).** Add `_assert_predicate_on_schema(session, *, user_id, subject_id, object_id, predicate)` and call
   it from **BOTH** `correct_relation_endpoint` (`:106`) **and** `create_relation_endpoint` (`:186`),
   **BEFORE** `recreate_relation`:
   1. Load the subject + object entity nodes for `user_id` (they already carry `project_id` —
      `neo4j_repos/entities.py:95,248` — and `kind`). **Subject's `project_id` IS NULL ⇒ return** (no schema
      in scope; accept — today's behaviour, unchanged).
   2. `resolved = await ontology_resolver.resolve(project_id)` — inject the **SAME** `OntologyResolver` the
      tool uses (`app/ontology/resolver.py`) via a `Depends`, **so the TTL cache is shared**. Do **not** call
      `GraphSchemasRepo` directly.
   3. `issue = validate_edge(resolved, predicate=predicate, source_kind=subject.kind, target_kind=object.kind)`.
   4. `issue is not None` ⇒ **HTTP 422** with
      `detail={"error": issue.item_type, "predicate": predicate, "allowed": [e.code for e in resolved.edge_types]}`.
      **Comment WHY this diverges from the fail-soft extraction path:** extraction / `kg_propose_edge` **parks
      to triage** because an LLM pass must not lose work; **a REST write is a deliberate assertion by a human
      who can pick a valid predicate ⇒ hard reject.** This mirrors entity `kind` **exactly** (REST enforces
      `_AUTHORABLE_KINDS`; extraction triages).
   5. 🔴 **Validation runs BEFORE the recreate**, so `/relations/correct` keeps its **no-half-applied-state**
      property (`relations.py:123-127` deliberately orders recreate-before-invalidate) — **a 422 must leave
      the OLD edge live.**

   🟢 **NON-BREAKING BY CONSTRUCTION — it rejects NOTHING today.** `allow_free_edges` defaults **TRUE**
   (`migrate.py:1279`, `seed_graph_schemas.py:45,92`) and the degenerate resolve returns
   `allow_free_edges=True` (`graph_schemas.py:257`). It bites **only** for a project whose owner
   **deliberately closed** their schema. **No migration.**

   **Tests** — `services/knowledge-service/tests/test_relations_public_schema.py` (**NEW**;
   `pytestmark = pytest.mark.xdist_group("pg")`): (a) open schema + garbage predicate ⇒ **201**
   *[regression guard: today's behaviour preserved]*; (b) closed schema + off-vocab ⇒ **422**, body carries
   `allowed`; (c) closed schema + valid predicate but wrong endpoint kinds ⇒ 422 `edge_kind_mismatch`;
   (d) `/relations/correct` closed + off-vocab ⇒ 422 **AND the old edge is STILL valid**
   (`valid_until IS NULL`); (e) entity with `project_id = NULL` ⇒ 201.

1. **`frontend/src/features/knowledge/components/PredicateControl.tsx`** — **NEW** (≤90 lines).
   Props: `{ projectId: string | null; value: string; onChange: (v: string) => void; onOpenSchema: () => void }`.
   Reads **`useResolvedSchema(projectId)`** — 🔴 **NOT `useGraphSchema`.** (`useGraphSchema(schemaId)` reads
   ONE schema *tree* by id; the per-project **effective** schema is `useResolvedSchema`
   — `hooks/useResolvedSchema.ts:9`, which **already exists** and whose own comment says *"Always resolves to
   something (system defaults even before adopt), so the inspector never dead-ends"*. **The spec names the
   wrong hook.**) Also reads `usePredicateLabels()` + `schemaObserved` for the datalist union.
   testids: `predicate-control-select` · `predicate-control-free` · `predicate-control-no-ontology`.

2. **`frontend/src/features/knowledge/components/RelationEditDialog.tsx`** — **EDIT.**
   - **Add a `create` mode.** Today `relation: EntityRelation` is required. Make it a discriminated union:
     ```ts
     export type RelationEditDialogProps = {
       open: boolean;
       onOpenChange: (open: boolean) => void;
       projectId: string | null;
       onOpenSchema: () => void;
     } & (
       | { mode: 'edit';   relation: EntityRelation }
       | { mode: 'create'; subjectId?: string; subjectName?: string }
     );
     ```
   - **`mode: 'create'`** renders: subject **EntityPicker** · `<PredicateControl>` · object **EntityPicker** ·
     Save. Pre-fill subject from `subjectId`. **Hide the "Mark wrong" block** (there is nothing to invalidate).
   - **`mode: 'edit'`** renders exactly what it renders today — **EXCEPT** the free-text predicate `<input>`
     at `:127-134` is **REPLACED** by `<PredicateControl>`. Same control, same rules. **This is the
     split-brain fix, and it costs ZERO backend.**
   - **Disable Save when `subject === object`.** (The BE's 422 self-loop guard at `relations.py:199` stays as
     defense in depth — **do not remove it**.)
   - Keep `FormDialog` (DOCK-9-clean).

3. **`frontend/src/features/knowledge/components/EntityPicker.tsx`** — **NEW** (≤80 lines). A combobox over
   `useEntities({ project_id, search })` (the hook `EntitiesTab` already uses), debounced 300ms (copy
   `EntitiesTab`'s `useDebounced`). testids `entity-picker-subject` / `entity-picker-object`. Renders
   `name` + a kind badge; value = `entity.id`.

4. **`frontend/src/features/knowledge/hooks/useRelationMutations.ts`** — **EDIT.** Add `useCreateRelation()`,
   in the **same shape** as `useCorrectRelation`:
   - `mutationFn: (payload: CreateRelationPayload) => knowledgeApi.createRelation(payload, accessToken!)` —
     **`createRelation` already exists** (`api.ts:1610`).
   - `onSuccess` → `invalidateDetail()` **AND**
     `queryClient.invalidateQueries({ queryKey: ['knowledge-subgraph'] })`.
     🔴 **`useDetailInvalidation()` ALONE IS NOT ENOUGH.** It invalidates only
     `['knowledge-entity-detail']`. A new edge must appear **on the graph canvas**, which reads
     `['knowledge-subgraph']` (`useProjectSubgraph`). **Invalidating the wrong key = a write that lands and a
     UI that never shows it.**
   - **Errors:** 409 → *"one of those entities isn't yours"* (**no oracle** — do **NOT** echo the BE's
     "subject or object entity not found for this user" as a hint about **which**). 422 → the self-loop message.

5. **`frontend/src/features/knowledge/components/ProjectGraphView.tsx`** — **EDIT** (204 lines).
   - Toolbar button **`Link entities`**, `data-testid="kg-graph-link-entities"` → opens the dialog in
     `mode="create"` with `subjectId` = the currently-selected node (if any).
   - **OQ-10 — EDGE DELETE FROM THE CANVAS.** The canvas gets edge **create**; today the only edge **delete**
     is inside `EntityDetailPanel`'s relation row. **Ship it. Do NOT ship draw-with-no-erase.**
     Per `Q-38-OQ10-EDGE-DELETE-FROM-CANVAS`, **two corrections to the draft:**
     - 🔴 **(a) Bind BOTH `onClick` AND `onContextMenu`, not right-click only.** Right-click is **unreachable
       on touch**, and a left-click on an edge is a **no-op today**, so there is no conflict. The handler
       target is the **existing fat transparent hit-line** in `RelationEdge.tsx:26-28` (the *visible* line is
       `pointerEvents="none"` — it is not a target). Add an **OPTIONAL** `onSelect?: (edge, ev) => void` prop:
       `onClick`/`onContextMenu` → `ev.stopPropagation()` / `ev.preventDefault()` → `onSelect(edge, ev)`;
       `style={{ cursor: onSelect ? 'pointer' : 'help' }}`. 🔴 **The prop MUST be optional** — the other
       three call sites (`RelationshipMap.tsx:100`, `WorldMap.tsx:194`, `WorldRollupGraph.tsx:156`) pass
       nothing and **stay read-only**.
     - 🔴 **(b) IT IS NOT "ZERO BACKEND, ONE WIRING" — IT IS ONE WIRING *PLUS A CACHE-COHERENCE FIX*, and
       without it the edge STAYS DRAWN after you delete it.** `useRelationMutations.ts:17-26` invalidates
       **only** `['knowledge-entity-detail', userId]`, while the canvas renders
       `['knowledge-subgraph', userId, projectId]` **MERGED WITH a hand-rolled `useState` `accreted`**
       (`useProjectSubgraph.ts:98`, merged at `:133`). **`invalidateQueries` cannot reach hand-rolled state**
       (`invalidatequeries-cannot-reach-hand-rolled-state`). ⚠ **This is ALREADY LATENT TODAY** for Mark-wrong
       via the canvas's own `EntityDetailPanel` mount (`ProjectGraphView.tsx:170`). Add
       **`dropEdge(edgeId)`** to `useProjectSubgraph`, and it must do **all three**:
       1. `setAccreted(prev => ({ ...prev, edges: prev.edges.filter(e => e.id !== edgeId) }))`;
       2. **prune the react-query caches** — `queryClient.setQueriesData({ queryKey: ['knowledge-subgraph', userId] }, …)`
          **and** the `['knowledge-subgraph-ego', userId]` prefix (a cached ego payload inside its **30s
          staleTime** would otherwise **re-inject the dead edge** on the next expand);
       3. `void baseQuery.refetch()` — a **Correct mints a NEW edge id**, and only the refetch brings it in.

       **And add `['knowledge-subgraph', userId]` to the prefix list invalidated by `useDetailInvalidation()`**
       — that fixes the already-latent case.
     - ⚠ The canvas's `GraphEdge` is `{id, from, to, predicate, confidence}` — **not** an `EntityRelation`.
       **Fetch the real row** via the **existing** `GET /v1/knowledge/relations/{relation_id}`
       (`relations.py:48` — it exists *precisely* "for the FE correction dialog"). **Prefer the GET over
       hand-mapping** — it cannot drift.
     - Wire the dialog's `onMutated?: (rel, verb: 'create'|'correct'|'invalidate')` (reuse A2's callback — do
       **not** add a second): `invalidate` ⇒ `dropEdge(rel.id)`; `correct` ⇒ `dropEdge(oldEdgeId)` and the
       refetch brings the new one in.
     - 🔴 **The toolbar hint** (`ProjectGraphView.tsx:127`, key `graph.hint`) is **SHARED with
       `WorldRollupGraph.tsx:132`.** Give the graph panel its **own** key `graph.hintEditable` — **do not
       mutate the shared one** (`css-var-duplicated-across-two-consumers-drifts`).
   - **Optimistic edge:** add it to the canvas **ONLY after the 201.** Never before.

6. **`frontend/src/features/studio/panels/KgGraphPanel.tsx`** — **EDIT.** Pass
   `onOpenSchema={() => host.openPanel('kg-schema')}` through to `ProjectGraphView`.

7. **`frontend/src/features/knowledge/components/EntityDetailPanel.tsx`** — **EDIT (minimal).** The existing
   `<RelationEditDialog … relation={editingRelation} />` mount (`:621-627`) now needs `mode="edit"`,
   `projectId`, and `onOpenSchema`. Thread `projectId` in as a new prop on `EntityDetailPanelProps` — **both**
   call sites (`EntitiesTab`, `ProjectGraphView`) already have it.

> 🟢 **Delete is NOT a hole and this slice does not build one.** An edge created here is removable via the
> same dialog's existing **Mark wrong**. Recorded so a reviewer does not "add" a delete.
> 🟢 **This bypasses the triage/propose spine ON PURPOSE.** `kg_propose_edge` exists for the *agent* (it
> proposes; a human confirms). **A human writing their own edge IS the confirmation.** Do not "fix" the human
> path into the proposal queue.

**Tests**

- **`.../components/__tests__/PredicateControl.test.tsx`** (NEW) — **one case per row of the table**, and the
  fourth is the one that matters:
  - `edge_types present + allow_free_edges false ⇒ a <select>, no text input`
  - `edge_types present + allow_free_edges true ⇒ a <select> WITH a "+ custom" escape`
  - `edge_types empty + allow_free_edges true ⇒ a free-text input`
  - 🔴 `edge_types empty + allow_free_edges false ⇒ NO input, and a link to the schema panel` — assert
    `queryByTestId('predicate-control-select')` is **null**, `queryByRole('textbox')` is **null**, and
    `getByTestId('predicate-control-no-ontology')` is present and its button calls `onOpenSchema`.
    **Without this test, the dead form ships.**
  - `edge_types UNDEFINED (not []) behaves like empty` — the TS type says `edge_types?`.
- **`.../components/__tests__/RelationEditDialog.test.tsx`** (NEW or EDIT)
  - `create mode: Save is disabled when subject === object`
  - `create mode: a 409 renders "one of those entities isn't yours" and does NOT name which` — assert the
    rendered text contains neither `subject` nor `object`.
  - 🔴 `edit mode uses the SAME PredicateControl as create (no free-text <input> survives)` — render
    `mode="edit"` with a schema that has edge types + `allow_free_edges: false`; assert
    `queryByTestId('relation-edit-predicate')` (today's free-text input) **is null** and
    `getByTestId('predicate-control-select')` is present. **This is the split-brain regression lock.**
  - 🔴 `edit mode keeps an OFF-CATALOGUE legacy predicate as a selected option` — render `mode="edit"` with
    `relation.predicate = "was_mentor_to"` and a schema/catalogue that does **not** contain it; assert it is
    the **selected** option. **Without this, opening the dialog silently rewrites the edge.**
- **`.../hooks/__tests__/useRelationMutations.test.ts`** (NEW or EDIT)
  - 🔴 `useCreateRelation invalidates BOTH knowledge-entity-detail AND knowledge-subgraph` — spy on
    `queryClient.invalidateQueries`; assert **both** keys. *(The one-key version is the bug.)*
- **`.../components/__tests__/ProjectGraphView.test.tsx`** (EDIT) — 🔴 **THE CACHE-COHERENCE LOCK.**
  `fireEvent.contextMenu` **AND** `fireEvent.click` on the edge hit-line each open the dialog with the
  predicate prefilled; then click `relation-edit-invalidate` (stub `window.confirm` → true) and assert
  `screen.queryAllByTestId('relmap-edge')` goes **1 → 0 WHILE THE MOCKED BASE QUERY STILL RETURNS THE EDGE.**
  🔴 **That last clause is the whole point** — it proves `dropEdge` pruned the accreted/cached copy, and not
  merely that a refetch happened. **A test that also changes the mocked payload proves NOTHING.**
- **`frontend/src/features/composition/components/__tests__/RelationshipMap.test.tsx`** (EDIT) — assert
  **no-handler ⇒ `contextMenu` on the edge does NOT `preventDefault` and opens nothing** (the other three
  `RelationEdge` call sites stay read-only).

**Run:** `cd frontend && npx vitest run src/features/knowledge src/features/composition` **and**
`cd services/knowledge-service && python -m pytest tests -q -n auto --dist loadgroup` (BE-14e is in this slice).

**DoD evidence:** `"W8-03: vitest <N> passed + knowledge pytest <N> passed. RelationEditDialog carries 3 verbs on ONE dialog; PredicateControl is used by create AND correct (the free-text <input> at RelationEditDialog.tsx:127 is GONE — asserted null) and its datalist unions edge_types ∪ /predicate-labels ∪ schema/observed; an off-catalogue legacy predicate survives as the selected option in edit mode; empty-ontology + !allow_free_edges renders the schema-panel escape, not a dead <select>. BE-14e: a CLOSED schema 422s an off-vocab predicate on BOTH /relations and /relations/correct and the OLD edge stays live (asserted); an OPEN schema still 201s garbage (regression guard) — D-KG-RELATION-PREDICATE-UNCONSTRAINED is RETIRED. kg-graph edges open the dialog on click AND contextmenu; Mark-wrong un-draws the edge WHILE THE MOCKED BASE QUERY STILL RETURNS IT (dropEdge prunes accreted + the ego cache)."`

**dependsOn:** W8-01

---
### W8-04 · [FE] A5 — kill the three dead buttons

**The bug (verified in code):** `frontend/src/features/knowledge/components/shell/OverviewSection.tsx:56`
declares `const noop = () => {};` and passes it as **`onArchive`**, **`onRestore`** AND **`onDelete`**
(`:66-69`). `ProjectRow.tsx:288-319` renders those buttons **unconditionally**. So in the shipped
`kg-overview` panel (and on the classic `ProjectDetailShell`) the user clicks **Archive** / **Restore** /
**Delete** on their knowledge project and **NOTHING HAPPENS, WITH NO ERROR.** That is
`silent-success-is-a-bug` in its purest form.

**Two changes — and the second is the one that matters.**

**Files**

1. **`frontend/src/features/knowledge/components/ProjectRow.tsx`** — **EDIT.**
   🔴 **Make the handler props OPTIONAL and render NOTHING when a handler is absent.**
   ```ts
   onArchive?: (p: Project) => void;
   onRestore?: (p: Project) => void;
   onDelete?:  (p: Project) => void;
   ```
   - `:288-311` — gate the archive/restore branch: `{onArchive && !isArchived && (…)}` /
     `{onRestore && isArchived && (…)}`.
   - `:312-319` — gate Delete: `{onDelete && (…)}`.
   - **A button whose handler is a no-op MUST NOT EXIST.** This is the change that makes the defect
     *unrepeatable*: the next `noop` now produces a **missing button** (visible, reviewable) instead of a
     **dead button** (invisible, shipped).

2. **`frontend/src/features/knowledge/components/shell/OverviewSection.tsx`** — **EDIT.** Delete
   `const noop = () => {};` (`:56`) and wire the real handlers.
   - It **already** mounts `useProjects(false)` for `createProject` / `updateProject` (`:42`). Take
     `archiveProject` and `deleteProject` from the **same** hook call — same react-query cache, **no extra
     fetch** (dedup by queryKey).
   - Add `ConfirmDialog` (from `@/components/shared` — `ProjectRow` already imports it, so DOCK-9 is fine) for
     archive and for delete, with the same copy `ProjectsBrowser` uses (`projects.toast.archived` /
     `.deleted` / `.archiveFailed` / `.deleteFailed`).
   - 🔴 **THERE IS NO `restoreProject`. DO NOT INVENT ONE.** `useProjects` exposes exactly
     `createProject / updateProject / archiveProject / deleteProject` (`useProjects.ts:144-147`).
     **Restore is an OCC PATCH.** Copy `ProjectsBrowser.tsx:142-155` **verbatim, including the version**:
     ```ts
     const handleRestore = async (project: Project) => {
       try {
         await updateProject({
           projectId: project.project_id,
           payload: { is_archived: false },
           // D-K8-03: the captured version is LOAD-BEARING. Without it a stale "Show archived"
           // snapshot silently wins over an edit from another device. BE: 428 with no If-Match,
           // 412 on a stale one.
           expectedVersion: project.version,
         });
         toast.success(t('projects.toast.restored'));
       } catch (err) {
         toast.error(err instanceof Error ? err.message : t('projects.toast.restoreFailed'));
       }
     };
     ```
     **Do NOT drop `expectedVersion` to make it simpler.** On a **412**, reset the baseline from the response
     body — do **not** re-GET, do **not** blind-retry.

3. 🔴 **`frontend/src/features/knowledge/lib/projectRestore.ts`** — **NEW** (`Q-38-A5-NO-RESTORE-PROJECT`).
   A plain **composed function**, **not** a mutation and **not** an api method — so it does **not** violate
   *"there is no `restoreProject`"*; it just wraps the existing `updateProject` call **so the two call sites
   share the 412 logic instead of forking it** (`css-var-duplicated-across-two-consumers-drifts`).
   ```ts
   /** Restore = an OCC PATCH of is_archived. The captured `version` is LOAD-BEARING (D-K8-03).
    *  On 412 the BE returns the CURRENT project as the body — reset the baseline FROM IT and
    *  re-apply ONCE. Never re-GET. Never blind-retry. Never drop expectedVersion. */
   export async function restoreProject(project, updateProject, t): Promise<'restored'|'conflict'> { … }
   ```
   - 🔴 **Use it in BOTH `OverviewSection.tsx` AND `ProjectsBrowser.tsx`.** Today
     `ProjectsBrowser.tsx:151-153` **swallows a 412 as a generic `restoreFailed` toast** — a real (if minor)
     bug. **Fix it in the same slice** so the two copies stay byte-identical. On 412 the copy is
     *"changed on another device — reloaded, try again"* **with the current name from the 412 body**, not a
     generic failure.
   - Also copy `ProjectsBrowser.tsx:109-116`'s **`lastArchiveName` / `lastDeleteName` ref trick** into the
     `ConfirmDialog`s — **Radix keeps the dialog mounted during its exit animation**, so the name blanks
     mid-fade without it.

**Tests**

- **`.../components/__tests__/ProjectRow.test.tsx`** (NEW) — 🔴 **this test IS the point of the slice**
  (`checklist-is-self-report-enforce-by-tests`):
  - `renders NO delete button when onDelete is absent` — `expect(queryByTitle('projects.card.delete')).toBeNull()`
  - `renders NO archive button when onArchive is absent`
  - `renders NO restore button when onRestore is absent` (render with `is_archived: true`)
  - `renders all three when the handlers ARE supplied`
  **Without these four, the next `noop` re-creates the defect silently.**
- **`.../components/shell/__tests__/OverviewSection.test.tsx`** (NEW)
  - `Delete opens a real confirm dialog and calls deleteProject on confirm`
  - 🔴 `Restore calls updateProject with is_archived:false AND expectedVersion` — spy on `updateProject`;
    assert it was called with `{ projectId, payload: { is_archived: false }, expectedVersion: <project.version> }`.
    **Assert the version is present** — a restore that drops it is the D-K8-03 regression.
  - `no noop survives in this file` — a cheap source assertion is fine and appropriate here:
    `expect(readFileSync(<OverviewSection path>, 'utf-8')).not.toMatch(/const noop/)`.

**Run:** `cd frontend && npx vitest run src/features/knowledge`

**DoD evidence:** `"W8-04: vitest <N> passed. ProjectRow renders 0 of 3 destructive buttons when its handlers are absent (4 cases); OverviewSection's const noop is gone (asserted); restore goes through updateProject with expectedVersion (D-K8-03 asserted)."`

**dependsOn:** —

---
### W8-05 · [BE] BE-14a + BE-14b — the two thin route mirrors

> **▶ DECISIONS FOLDED:** `Q-38-BE-14a-PROJECT-ENTITIES-ROUTE` · `Q-38-BE-14a-GRANT-LEVEL` ·
> `Q-38-A3-WIRE-NAME-DRIFT` · `Q-38-A3-SYNC-NOT-A-JOB` · `Q-38-A3-NO-BOOK-LINK-409` ·
> `Q-38-BE-14b-FACT-INVALIDATE-ROUTE` · `Q-38-A4-FALSE-INVALIDATED-STATE` · **`Q-38-OQ4-NO-UN-FORGET`**.
>
> 🔴 **THREE CONTRADICTIONS FIXED. The register wins on all three:**
> 1. **`D-KG-PROJECTION-DEGRADE-OPAQUE` is DELETED, not deferred.** The draft said *"disambiguating needs an
>    engine change ⇒ file the row; do not build it."* That is exactly CLAUDE.md's **anti-laziness** case —
>    *"missing infrastructure is NOT blocked, it is unbuilt work."* **BUILD IT (BE-14a2, below): ~6 lines.**
>    Without it, a glossary **outage** renders as *"this book's glossary is empty"* — a **silent-success lie**.
> 2. **`D-KG-FACT-RESTORE` is DELETED, not deferred.** The draft shipped copy that says *"there is no
>    un-forget button"* and filed a gate-#2 row. **The register BUILDS restore (BE-14b2): ~60 BE lines in the
>    files BE-14b already opens, plus an undo toast.** A confirm dialog is not a mitigation for an
>    unrecoverable mis-click when the fix is an afternoon.
> 3. **The draft's route DROPS THE STAT RECOUNT.** It calls the engine directly. `reconcile_project_stats` is
>    called from **exactly ONE place in production** — the MCP tool (`graph_schema_tools.py:1669-1673`) — and
>    it is **the only writer of `stat_updated_at`** (`D-KG-STAT-CACHE-DEAD`). A route that skips it leaves
>    `entity_count` **UNKNOWN** and **stalls the seed-from-glossary rail at `STOP_UNKNOWN` for GUI users but
>    not for agent users.** (This repo's `guard-stalls-on-artifact-from-dead-code` lesson, re-run.) **Share
>    ONE effect function.**

Both are **thin routers over engines that already exist, are hardened, and are tested.** **Do not
re-implement either engine** — but **do** extract the shared effect, and **do** build the two ~6-line engine
legs the routes' own error contracts are impossible without.

**Files**

0. 🔴 **`services/knowledge-service/app/extraction/anchor_loader.py`** — **EDIT (BE-14a2 — build this FIRST;
   the route's 503 and its wire shape are both impossible without it).**
   - **(a) THE SHARED WIRE MAPPER** — kill the **three spellings** of six counters with **one producer**.
     Add directly under `ProjectionResult` (`:166-192`):
     ```python
     def projection_result_to_wire(res: ProjectionResult) -> dict:
         """THE wire shape for a glossary→nodes projection. Every counter key is ALWAYS
         PRESENT (zero-filled); `note` is the only optional key."""
         notes: list[str] = []
         if res.truncated:
             notes.append("the book has more entities than one projection pass could read; "
                          "re-run with explicit entity_ids to project the remainder")
         if res.conflicted:
             notes.append(f"{res.conflicted} entit{'y' if res.conflicted == 1 else 'ies'} could not be "
                          "added because another node in this project already owns them in the graph")
         return {
             "nodes_created":    res.created,
             "nodes_existing":   res.existing,
             "entities_seen":    res.seen,
             "skipped":          res.skipped,
             "nodes_conflicted": res.conflicted,   # ALWAYS present (0, not omitted)
             "truncated":        res.truncated,    # ALWAYS present (false, not omitted)
             **({"note": " · ".join(notes)} if notes else {}),
         }
     ```
     Then 🔴 **REPLACE `graph_schema_tools.py:1681-1707`** (the `out: dict = {...}` block **and its three
     `if res.*:` conditional-key branches**) with `return projection_result_to_wire(res)`. **Now BE-14a and
     the tool CANNOT drift — there is one producer.** Additive keys are safe for the LLM (`truncated: false`
     is strictly more informative than an absent key). ⚠ In
     `tests/unit/test_graph_schema_tools.py`, any assertion of the form `"truncated" not in out` /
     `"nodes_conflicted" not in out` **flips** to `out["truncated"] is False` / `out["nodes_conflicted"] == 0`.
   - **(b) MAKE 503 POSSIBLE** — `_load_projection_rows` **SWALLOWS** a glossary read failure
     (`anchor_loader.py:308-315`: `if page is None: log.warning(...); return out, False`), so *"glossary
     unreachable"* and *"glossary is empty"* **both** produce an all-zero `ProjectionResult`. Fix
     **additively**: add `glossary_unreachable: bool = False` to `ProjectionResult` (defaulted ⇒ **no caller
     breaks**); set it `True` on the `page is None` branch (the `list_all_entities` first-page failure) and
     wrap the by-ids `fetch_entities_by_ids` call (`:299-303`) in `try/except` ⇒ `True`; thread it out.
     ⚠ The `entity_ids` **subset** path stays as-is otherwise (`fetch_entities_by_ids` returns `[]`
     best-effort **by contract** — `glossary_client.py:527`), so 0 rows there legitimately means *"those ids
     aren't in the glossary"*. 🔴 **`glossary_unreachable` is an ERROR SIGNAL, not a wire key** — the 200 body
     stays exactly the 6+1 shape. Surface it in the MCP tool as a `note` so tool and route tell the **same
     story**.

0b. 🔴 **`services/knowledge-service/app/kg/project_entities.py`** — **NEW FILE (the SHARED EFFECT).**
   ```python
   async def run_project_entities_to_nodes(pool, glossary_client, *, owner: UUID, project_id: UUID,
                                           book_id: UUID, entity_ids: list[str] | None) -> ProjectionResult:
       """The ONE effect behind BOTH kg_project_entities_to_nodes (MCP) and BE-14a (REST).

       Lifted verbatim from _handle_kg_project_entities_to_nodes (graph_schema_tools.py:1648-1680):
       open neo4j_session() → project_glossary_entities_to_nodes(...) → then BEST-EFFORT
       reconcile_project_stats(pool, session, owner, project_id) inside try/except (log-and-continue).

       🔴 THE RECOUNT IS NOT OPTIONAL. reconcile_project_stats is the ONLY production writer of
       stat_updated_at (D-KG-STAT-CACHE-DEAD). If the REST route calls the engine directly it leaves
       entity_count UNKNOWN and the seed-from-glossary rail stalls at STOP_UNKNOWN for GUI users but
       NOT for agent users. Sharing one effect fn is the only way both paths keep the recount.
       A recount failure must NEVER fail a successful projection.
       """
   ```
   **Rewrite `_handle_kg_project_entities_to_nodes` to call it.** *(A nil-tolerant best-effort wrapper needs a
   **wiring test** or the recount silently drops out again — see the spy test below.)*

1. **`services/knowledge-service/app/routers/public/projects.py`** — **EDIT.** Add **BE-14a**:
   ```python
   class ProjectEntitiesRequest(BaseModel):
       entity_ids: list[str] | None = Field(default=None, max_length=1000)

   class ProjectEntitiesResponse(BaseModel):     # 🔴 the BELT to the mapper's BRACES — FastAPI cannot
       nodes_created:    int                     #    leak an omitted key through a required-int model
       nodes_existing:   int
       entities_seen:    int
       skipped:          int
       nodes_conflicted: int = 0
       truncated:        bool = False
       note:             str | None = None       # the ONLY key the FE may branch on

   @router.post("/{project_id}/project-entities", response_model=ProjectEntitiesResponse)
   async def project_glossary_entities(
       body: ProjectEntitiesRequest,
       project_id: UUID = Path(),
       owner: UUID = Depends(require_project_grant(GrantLevel.EDIT)),   # 🔴 NOT get_current_user
       meta: ProjectMeta | None = Depends(project_meta_dep),            # FastAPI CACHES the dep → ONE call
       pool = Depends(get_knowledge_pool),
       glossary = Depends(get_glossary_client),
   ):
       """BE-14a — REST mirror of `kg_project_entities_to_nodes`. Deterministically project the
       book's glossary entities into the KG as canonical :Entity nodes (the "seed the graph"
       empty-state CTA). LLM-free, idempotent, NO cost gate, NO job, NO confirm_token.

       GATE: EDIT, matching the tool (`graph_schema_tools.py:1638`
       `_resolve_project_owner(ctx, GrantLevel.EDIT)`). Gating this on the raw JWT would make the
       BUTTON strictly weaker than the SENTENCE — a collaborator could seed the owner's graph by
       ASKING THE LLM and not by CLICKING. That is the inverse gap §6.3 exists to close, created by
       this very wave.

       🔴 `require_project_grant` IS RESOLVE-TO-OWNER (grant_deps.py:108-122): it returns the PROJECT
       OWNER's user_id, NOT the caller's. Pass it straight through as the graph partition key —
       exactly as the tool does (graph_schema_tools.py:1638 → :1660 `user_id=str(owner)`). Passing
       the CALLER's id instead lands an EDIT-collaborator's projection in the WRONG graph partition:
       a SILENT DATA BUG on top of the authz one, and a status-code-only test cannot see it.

       🔴 DO NOT use require_project_principals — that factory (grant_deps.py:125-147) exists for
       BYOK dual-identity BILLING. BE-14a makes ZERO provider calls. One identity: the owner.
       """
       if meta is None:
           raise HTTPException(404, "not found")            # uniform, no oracle (the gate already covered it)
       _, book_id = meta                                    # 🔴 from the CACHED dep — do NOT re-fetch
       if book_id is None:
           # The tool's own hard-fail. A 409, NEVER a 500, and NEVER a bare string —
           # the FE must distinguish this from the 503 WITHOUT string-matching.
           raise HTTPException(409, detail={"code": "KG_PROJECT_NOT_LINKED_TO_BOOK",
                                            "message": NO_BOOK_LINK_MSG})
       ids = [e.strip() for e in (body.entity_ids or []) if e and e.strip()] or None
       res = await run_project_entities_to_nodes(          # 🔴 the SHARED effect — it carries the RECOUNT
           pool, glossary, owner=owner, project_id=project_id, book_id=book_id, entity_ids=ids,
       )
       if res.glossary_unreachable:                        # 🔴 BE-14a2 — NOT "nothing to project"
           raise HTTPException(503, "couldn't read the glossary — try again in a moment")
       return projection_result_to_wire(res)               # 🔴 the SHARED mapper — one producer, no drift
   ```
   - 🔴 **`NO_BOOK_LINK_MSG` + the error code — hoist them, don't duplicate them** (`Q-38-A3-NO-BOOK-LINK-409`).
     In `graph_schema_tools.py:1643-1647`, export the message as a module constant `NO_BOOK_LINK_MSG` and give
     the raise a **stable code**: `raise ToolExecutionError(NO_BOOK_LINK_MSG, code="KG_PROJECT_NOT_LINKED_TO_BOOK")`
     (`ToolExecutionError` already accepts `code`/`detail` — `executor.py:202-221`). Keep the message string
     **byte-identical**. The route **imports** it. **The tool and the button must not tell two stories.**
   - 🟢 **FREE ERROR SEMANTICS — inherit them, do not re-implement them.** `require_project_grant` already
     gives you: missing project / non-grantee / book-less-non-owner ⇒ uniform **404**; grantee below EDIT ⇒
     **403** (`grant_deps.py:82-105`, anti-oracle). **Only the `book_id is None` 409 is hand-written.**
   - 🟢 **SYNCHRONOUS, NO JOB, NO COST GATE** (`Q-38-A3-SYNC-NOT-A-JOB` — confirmed at code). The tool is
     documented **Tier-A: idempotent + reversible** (`graph_schema_tools.py:438-448`) and its handler runs the
     engine **INLINE**, minting **no `confirm_token`** — unlike every cost-gated sibling (`kg_build_graph` →
     `build_tools.py:118`). The engine is pure Neo4j upserts + **one** glossary HTTP read (zero LLM calls),
     **paged with a `truncated` flag**, `entity_ids` capped at 1000 ⇒ **bounded work, safe in-request.**
     **NO enqueue · NO job row · NO propose→confirm · NO `estimated_cost` · NO spend-guardrail check.** Guard
     it with a test (below) so a reviewer cannot "fix" it back.

2. **`services/knowledge-service/app/routers/public/facts.py`** — 🔴 **NEW file** (**NOT** appended to
   `pending_facts.py` — that is a **different object with a different lifecycle**). Copy the router shape of
   `routers/public/relations.py:41-46`:
   `facts_router = APIRouter(prefix="/v1/knowledge", tags=["facts"], dependencies=[Depends(get_current_user)])`.
   Register in `app/main.py` next to `public_relations.relations_router` (`:771`; import next to the siblings
   at `~:56`). **NO gateway change** — `gateway-setup.ts:206-207,645` already proxies all `/v1/knowledge/*`.
   **Emit NO outbox event from either route** — there is **no `FACT_CORRECTED` type**
   (`outbox_emit.py:63-65` has entity/relation/event only) and `memory_forget` emits none today. **Do not
   invent one.**

   **BE-14b — `POST /facts/{fact_id}/invalidate` — THREE ARMS, and arm 2 is the one the draft missed:**
   ```python
   class FactInvalidateResponse(BaseModel):
       invalidated: bool
       fact_id: str                      # 🔴 ALWAYS echoed, even on a miss — the FE row action needs to
       reason: str | None = None         #    know WHICH row the response belongs to (the tool omits it)

   @facts_router.post("/facts/{fact_id}/invalidate", response_model=FactInvalidateResponse)
   async def invalidate_fact_endpoint(
       fact_id: str = Path(min_length=1, max_length=200),
       user_id: UUID = Depends(get_current_user),      # 🟢 the raw JWT IS correct here
   ):
       """BE-14b — REST mirror of `memory_forget`. Soft-invalidate ONE fact (sets `valid_until`;
       audit history is KEPT).

       GATE: the raw JWT, DELIBERATELY. `invalidate_fact` is OWNER-keyed in the Cypher
       (facts.py:667 `WHERE f.user_id = $user_id`) and the tool takes no project gate either
       (executor.py:709-716). A cross-user fact id simply does not match → {invalidated: false}.
       NEVER an oracle. DO NOT add a grant dep.

       🔴 ALWAYS 200 — an owner-keyed MISS is 200 {invalidated:false}, NEVER 404. Do NOT copy
       relations.py's `raise HTTPException(404)`: that is the ONE line that must differ from the
       template. (Missing/invalid JWT is still 401, from the router-level dep.)

       🔴 ARM 2 — THE DOUBLE-FORGET RE-STAMP (the defect the spec missed, §3.1):
       _INVALIDATE_FACT_CYPHER does `SET f.valid_until = coalesce($valid_until, datetime())`, so a
       second forget RE-STAMPS an already-forgotten fact and answers invalidated:true — reporting
       success AND moving the original forget timestamp forward, corrupting the audit history the
       soft-delete exists to keep. Close the window HERE, in the writer route — NOT in
       invalidate_fact (that engine is SHARED with memory_forget and mirrors invalidate_relation).
       """
       async with neo4j_session() as session:
           before = await get_fact(session, user_id=str(user_id), fact_id=fact_id)   # facts.py:390
           if before is None:
               return FactInvalidateResponse(invalidated=False, fact_id=fact_id,
                                             reason="no matching fact found")        # string VERBATIM from the tool
           if before.valid_until is not None:
               return FactInvalidateResponse(invalidated=False, fact_id=fact_id,
                                             reason="already forgotten")             # 🔴 AND WRITE NOTHING
           fact = await invalidate_fact(session, user_id=str(user_id), fact_id=fact_id)
       return FactInvalidateResponse(invalidated=True, fact_id=fact.id, reason=None)
   ```

3. 🔴 **BE-14b2 — `POST /facts/{fact_id}/restore` — THE UN-FORGET. BUILD IT. It is ~60 lines**
   (`Q-38-OQ4-NO-UN-FORGET`; **`D-KG-FACT-RESTORE` is RETIRED**). Same file, same router.
   - **(a) ENGINE** — `services/knowledge-service/app/db/neo4j_repos/facts.py`, **immediately after
     `invalidate_fact`** (which ends at `:700`). The exact mirror:
     ```python
     _RESTORE_FACT_CYPHER = (
         "MATCH (f:Fact {id: $id}) WHERE f.user_id = $user_id "
         "SET f.valid_until = NULL, f.updated_at = datetime() RETURN f"
     )
     async def restore_fact(session, *, user_id: str, fact_id: str) -> Fact | None: ...
     ```
     `ValueError` on an empty `fact_id`; `None` when no row (⇒ 404); **idempotent** (restoring a live fact
     returns it unchanged). Add `"restore_fact"` to `__all__` (`facts.py:56`).
     🔴 **HARD CONSTRAINT: restore touches ONLY `valid_until`** — the transaction-time axis `invalidate_fact`
     closed. **Do NOT touch `archived_at`** (the entity-archive axis) and **do NOT touch
     `valid_to_ordinal` / `valid_to_ordinal_eff`** (the **story-time chain** owned by
     `temporal.maintain_chain`, `facts.py:186-191`). **Reopening those CORRUPTS the interval chain.**
   - **(b) ROUTE** — `POST /facts/{fact_id}/restore` → `200 {restored: true, fact_id}`; a miss ⇒ **404**
     (owner-keyed off the JWT, so cross-user collapses to 404 — same reasoning as `executor.py:713-716`).
   - **(c) BE-14b3 — MAKE FORGOTTEN FACTS REACHABLE, or the restore route is DEAD SURFACE.** In
     `facts.py` `_LIST_FACTS_FOR_ENTITY_BODY`, change `:599` from `AND f.valid_until IS NULL` to
     `AND ($include_invalidated OR f.valid_until IS NULL)`; add `include_invalidated: bool = False` to
     `list_facts_for_entity` (**default False = byte-identical current behaviour for the L2 loader**) and
     thread it through. Add `include_invalidated: bool = Query(default=False)` to
     `GET /entities/{entity_id}/facts` (`entities.py:635-659`). The `Fact` model **already carries
     `valid_until`** (`facts.py:114`), so the FE gets the flag for free.
   - **(d) 🔴 A SEPARATE BUG THIS EXPOSES — FIX IT IN THE SAME SLICE (one line, `silent-success-is-a-bug`).**
     `merge_fact`'s `ON MATCH` (`facts.py:200-243`) does **NOT** clear `valid_until`, while
     `create_relation`'s `ON MATCH` **does** (`relations.py:1292-1299` — *"RESURRECTS a previously-invalidated
     tuple"*). Because the fact id is **content-keyed** (`facts.py:307`), **re-remembering a forgotten fact
     hits the same invalidated node and `memory_remember` still answers `{"remembered": true}`
     (`executor.py:702-707`) though the fact STAYS HIDDEN FOREVER.**
     🔴 **Do NOT blanket-resurrect in the extraction path** — that would let re-extraction **silently undo a
     human's Forget** (the F5 rule relations already respects). Instead: add a `resurrect: bool = False`
     kwarg to `merge_fact` whose `ON MATCH` sets
     `f.valid_until = CASE WHEN $resurrect THEN NULL ELSE f.valid_until END`, and pass `resurrect=True`
     **ONLY** from `_handle_memory_remember` (`executor.py:692-701`) — a human/agent **explicitly
     re-asserting** the fact is the same intent as `recreate_relation`.
   - **(e) 🟢 NO MCP `memory_restore` TOOL IN v1** (veto-able default). Un-forget is a **human mis-click
     recovery**, not agent logic; the MCP-first invariant governs **agentic** capabilities, and the REST
     mirror is the sanctioned GUI path. The engine fn is there if an agent ever needs it — the tool would be
     a 10-line handler.

   ⚠ **DO NOT wire any of this to** `POST /v1/knowledge/pending-facts/{id}/confirm|reject` (the pre-commit
   triage queue) or to
       `/internal/admin/.../reject-fact`. Different objects, different lifecycles.
       """
       async with neo4j_session() as session:
           fact = await invalidate_fact(session, user_id=str(user_id), fact_id=fact_id)
       if fact is None:
           # 200, NOT 404 — mirror the tool EXACTLY (executor.py:722).
           return {"invalidated": False, "reason": "no matching fact found"}
       return {"invalidated": True, "fact_id": fact.id}
   ```
   Register the router in `app/main.py` alongside the other public routers.

3. **`contracts/api/knowledge-service/*.yaml`** — **EDIT.** Add the three new routes (BE-14a, BE-14b, and
   BE-14c from W8-01). **Contract-first is a repo rule.**

**Tests**

- **`services/knowledge-service/tests/unit/test_project_entities_route.py`** (NEW — mirror the
  `dependency_overrides` pattern in `tests/unit/test_public_graph_views.py` + `tests/conftest.py`, which
  already override `project_meta_dep`)
  - 🔴 `test_all_six_counters_are_always_present_even_when_zero` — **THE key test.** Stub the engine to return
    `ProjectionResult(created=0, existing=0, seen=0, skipped=0, truncated=False, conflicted=0)`; assert the
    JSON body carries **all six** keys, with `nodes_conflicted == 0` and `truncated is False`.
    *(The MCP tool would have OMITTED both. An FE reading `res.nodes_conflicted` gets `undefined` and renders
    nothing. **The zero case is where the conditional-key bug hides** — so this is the assertion that must
    exist.)*
  - `test_conflicted_and_truncated_are_forwarded_when_nonzero` — **+ a `note`**.
  - `test_project_without_a_book_returns_409_not_500` — `project_meta` → `(owner, None)`; assert **409**, the
    code `KG_PROJECT_NOT_LINKED_TO_BOOK`, and that the message **is the shared `NO_BOOK_LINK_MSG` constant**
    (assert against the import, not a copied literal).
  - 🔴 `test_gate_is_edit_grant_not_raw_jwt` — a collaborator holding **EDIT** on the project's book gets
    **200** ⋯ 🔴 **AND THE ENGINE IS CALLED WITH `user_id == OWNER`, NOT THE CALLER.** *(Assert on the spy's
    kwargs. **A status-code-only test cannot see the resolve-to-owner mistake** — and that mistake writes an
    EDIT-collaborator's projection into the WRONG graph partition. This assertion is the point of the test.)*
    A **VIEW** grantee ⇒ **403**; a stranger ⇒ **404**.
  - 🔴 `test_glossary_unreachable_is_503_not_a_zero_200` — stub `list_all_entities` → `None`; assert **503**
    **and that the body is NOT the all-zero "nothing to project" 200.** *(This is the test that kills
    `D-KG-PROJECTION-DEGRADE-OPAQUE`.)*
  - 🔴 `test_the_route_path_invokes_reconcile_project_stats` — **a SPY.** *(A nil-tolerant best-effort wrapper
    needs a wiring test, or the recount silently drops out again and the rail re-stalls at `STOP_UNKNOWN` for
    GUI users only.)*
  - 🔴 `test_the_response_carries_no_confirm_token_and_no_job_id` — pins *"sync, not a job"* so a reviewer
    cannot "fix" it into the propose→confirm spine.
  - `test_missing_project_is_404_uniform`
- **`services/knowledge-service/tests/unit/test_anchor_loader.py`** (EDIT) — one case for the new
  `glossary_unreachable` flag.
- **`services/knowledge-service/tests/unit/test_graph_schema_tools.py`** (EDIT) — 🔴 the tool now returns
  `projection_result_to_wire(res)`, so every `"truncated" not in out` / `"nodes_conflicted" not in out`
  assertion **FLIPS** to `out["truncated"] is False` / `out["nodes_conflicted"] == 0`. **Fix the assertions;
  do not restore the conditional keys.**
- **`services/knowledge-service/tests/unit/test_public_facts_invalidate.py`** (NEW — model it on
  `tests/unit/test_relation_correction.py`: `TestClient` + `patch("app.routers.public.facts.invalidate_fact",
  AsyncMock(...))` + `patch(...neo4j_session)` with an `asynccontextmanager`)
  - `test_invalidate_returns_true_and_the_fact_id` — **and assert `invalidate_fact` was called with
    `user_id=str(jwt_user)`** (owner keying **is** the tenancy boundary — assert the kwarg).
  - 🔴 `test_a_miss_returns_200_with_invalidated_false` — **assert `status_code == 200`, NOT 404.** Add the
    comment `# regression-lock: MISS is 200, not 404 — mirrors executor.py:718`.
  - `test_a_cross_user_fact_id_is_a_miss_not_an_oracle` — a **byte-identical** body to the unknown-id case.
  - 🔴 `test_double_forget_is_already_forgotten_and_does_NOT_restamp` — forget, then forget again ⇒ 200
    `{invalidated:false, reason:"already forgotten"}` **AND `valid_until` is UNCHANGED (assert the
    timestamp).** *(This is the arm that regresses.)*
- **`services/knowledge-service/tests/unit/test_public_facts_restore.py`** (NEW — BE-14b2)
  - `restore_fact` returns `None` for an unknown / cross-user id ⇒ **404**.
  - **restore is idempotent** — restoring a live fact returns it unchanged.
  - 🔴 `restore does NOT mutate archived_at or valid_to_ordinal` — **the interval-chain guard.**
  - 🔴 `merge_fact(resurrect=True) clears valid_until; the default does NOT` — then the round-trip:
    **forget → `memory_remember` the same text → the fact is LIVE again and appears in
    `list_facts_for_entity`.** *(Without `resurrect`, `memory_remember` answers `{"remembered": true}` while
    the fact stays hidden forever — a shipped silent-success.)*
- **`services/knowledge-service/tests/integration/db/test_facts_repo.py`** (EDIT — next to
  `test_k11_7_invalidate_fact_sets_valid_until` at `:327`) — **invalidate → restore → the fact reappears in
  `list_facts_for_entity` with DEFAULT filters.**
  🔴 `pytestmark = pytest.mark.xdist_group("pg")` — **it hits the shared dev DB.**
- ⚠ **Any NEW test touching the real dev Postgres/Neo4j MUST carry
  `pytestmark = pytest.mark.xdist_group("pg")`** or parallel xdist workers interleave and the counts lie. The
  unit tests above are stub-level and do **not** need it — **the integration one DOES.**

**Run:** `cd services/knowledge-service && python -m pytest tests -q -n auto --dist loadgroup`

**Cross-service live smoke (this slice's own, not W8-07's):** project a **real** book's glossary through the
**gateway** (`:3123`) into an **empty** graph with the test account's JWT, and confirm `nodes_conflicted` /
`truncated` come back on the wire.

**DoD evidence:** `"W8-05: knowledge pytest <N> passed. POST /projects/{id}/project-entities returns all SIX counters ALWAYS-PRESENT (nodes_conflicted:0, truncated:false asserted on a ZERO result, via the SHARED projection_result_to_wire — the MCP tool now uses the same producer, so its 3 conditional keys are gone); 409 {code:KG_PROJECT_NOT_LINKED_TO_BOOK} on a book-less project; 503 (NOT a zero-200) when the glossary is unreachable — D-KG-PROJECTION-DEGRADE-OPAQUE is BUILT, not deferred; gated on require_project_grant(EDIT) AND the engine is called with user_id==OWNER not the caller (spy-asserted); reconcile_project_stats IS invoked on the ROUTE path (spy-asserted — the stat cache does not go dead for GUI users). POST /facts/{id}/invalidate: 200 {invalidated:false} on a miss (NOT 404) and a DOUBLE forget returns 'already forgotten' WITHOUT re-stamping valid_until. POST /facts/{id}/restore EXISTS — invalidate→restore→the fact is back in list_facts_for_entity (integration, xdist_group pg); merge_fact(resurrect=True) un-hides a re-remembered fact. D-KG-FACT-RESTORE is RETIRED. live smoke: seeded a real book's glossary through the gateway :3123."`

**dependsOn:** W8-0C

---
### W8-06 · [FE] A3 seed-from-glossary + A4 forget-a-fact + the `memory_*` Lane-B handler

#### A3 — the empty-graph CTA. **The agent's own error message tells you to press a button that does not exist.**

`kg_propose_edge` fails with *"project the glossary entities into the graph first
(`kg_project_entities_to_nodes`)"* (`graph_schema_tools.py:1589-1603`) — and that tool is **MCP-only**. A
human staring at an empty graph is told to run a tool they cannot run. **BE-14a (W8-05) is the button.**

**Files**

1. **`frontend/src/features/knowledge/api.ts`** — **EDIT.** Two methods + one type:
   ```ts
   export interface ProjectionCounts {
     nodes_created: number; nodes_existing: number; entities_seen: number;
     skipped: number; nodes_conflicted: number; truncated: boolean; note?: string;
   }

   /** BE-14a — seed the graph from the book's glossary. Deterministic, LLM-free, idempotent. */
   projectEntities(projectId: string, entityIds: string[] | null, token: string): Promise<ProjectionCounts> {
     return apiJson<ProjectionCounts>(`${BASE}/projects/${projectId}/project-entities`, {
       method: 'POST', body: JSON.stringify({ entity_ids: entityIds }), token,
     });
   },
   /** BE-14b — forget a fact (soft: sets valid_until; audit history kept). */
   invalidateFact(factId: string, token: string): Promise<{ invalidated: boolean; fact_id?: string; reason?: string }> {
     return apiJson(`${BASE}/facts/${encodeURIComponent(factId)}/invalidate`, { method: 'POST', body: '{}', token });
   },
   ```
   🔴 **Six REQUIRED keys on `ProjectionCounts`** — not optional. The route guarantees them (W8-05). If you
   mark them optional, TypeScript stops protecting you from the `undefined` bug this whole design exists to
   prevent.

2. **`frontend/src/features/knowledge/hooks/useProjectEntities.ts`** — **NEW** (≤60 lines). A mutation.
   `onSuccess` → invalidate `['knowledge-entities']`, `['knowledge-subgraph']`, `['knowledge-projects']`.
   Exposes `{ run, isPending, result: ProjectionCounts | null, error }`.
   ⚠ **The projection is SYNCHRONOUS and can take seconds on a large glossary** ⇒ a **disabled button + a
   spinner**, **NOT a job**. Do not enqueue anything. Do not poll anything. There is no job id.

3. **`frontend/src/features/knowledge/components/SeedFromGlossaryCard.tsx`** + 🔴
   **`ProjectionResultCard.tsx`** — **NEW** (≤100 lines each; mirror the existing `DrawerResultCard.tsx`
   pattern). The **primary CTA** of the empty-graph state. `data-testid="kg-seed-from-glossary"`.

   🔴 **RENDER THE RESPONSE IN FULL — BY THE WIRE NAMES.** The counters exist so a **partial** projection can
   **explain itself**; they were hardened by `D-KG-GLOSSARY-FK-GLOBAL-UNIQUE` (2026-07-10). **A toast that
   shows only "Created N" re-introduces the exact bug they were added to expose.**

   🔴 **A PERSISTENT CARD, NOT A TOAST** (`Q-38-A3-FULL-RESPONSE-RENDER`). It renders **inline in the panel
   that fired the CTA** and **persists until dismissed or re-run**. **A toast auto-dismisses — and that is
   EXACTLY how a partial projection gets missed.**

   | Field | Render | testid |
   |---|---|---|
   | `nodes_created` + `nodes_existing` | always: *"Seeded {nodes_created} new · {nodes_existing} already in the graph"* | `proj-success` |
   | `nodes_conflicted > 0` | an **amber WARNING** row — 🔴 **and NOT the spec's string, which is STALE** (see below) | `proj-conflicted` |
   | `truncated === true` | *"the glossary read hit its page cap; more entities remain — run it again"* **+ a `Run again` button** | `proj-truncated` |
   | `skipped > 0` | a muted line: *"{n} rows skipped"* | `proj-skipped` |
   | `entities_seen === 0` | **replaces ALL of the above**: *"this book's glossary is empty — add entities there first"* + a button → `host.openPanel('glossary')` | `proj-empty` |

   🔴 **FIX THE CONFLICTED COPY — THE SPEC'S STRING IS FALSE AGAINST HEAD.** The spec (and
   `graph_schema_tools.py:1694-1706`) says *"already anchored by **another knowledge project** for this
   book"*. That was true under the **GLOBAL** FK — which was **DROPPED on 2026-07-10**
   (`neo4j_schema.cypher:69`). The live constraint is per **`(user_id, project_id, glossary_entity_id)`**
   (`:71-72`), and `anchor_loader.py:180-190` states a conflict is now an ***in-project* duplicate**. **Ship
   this instead:**
   > *"{n} entities couldn't be anchored — this project already has a node claiming them. Their data is
   > unchanged; open the entity to reconcile."*

   🔴 **AND FIX THE SAME STALE STRING IN THE BACKEND, IN THIS SLICE** (one file, root-cause clear ⇒ it
   **fails** CLAUDE.md's defer gate): correct the note in `graph_schema_tools.py:1694-1706` — which now lives
   inside `projection_result_to_wire()` (W8-05). **Leaving it means the AGENT tells the user a false reason
   while the GUI tells the true one** — a cross-service split-brain **on the very counters this exists to
   protect.**

   **States:** idle · running (button disabled + spinner) · partial (above) · **503** (*"couldn't read the
   glossary — try again in a moment"*, from BE-14a2 — 🔴 **distinct from "the glossary is empty"**) ·
   **409** (surface `detail.message`; **never a generic "something went wrong"**) · error.
   🔴 **HIDE THE CTA ENTIRELY when the project has no `book_id`.** The engine needs one; BE-14a **409s**
   without it. `Project.book_id` is already on the row (`OverviewSection.tsx:114` reads it). **Do not render a
   button that is guaranteed to fail.**
   **NO COST GATE.** Deterministic, LLM-free, idempotent. **Do NOT** route it through
   `GET /actions/preview` → `POST /actions/confirm` (that spine is for **paid Tier-W** actions), and **DO NOT
   INVENT A PER-ACTION ESTIMATE ROUTE** — plan 30 §3.3 documents **three** invented estimate routes that
   **404 in production today**.

4. **Mount it in three places** — it is **ONE component** (DOCK-2, no forks):
   - **`ProjectGraphView.tsx`** — the empty-graph state (`sg.nodes.length === 0`). **PRIMARY.**
   - **`OverviewSection.tsx`** — in the stats card when `entity_count === 0`. **PRIMARY.**
   - **`KgSchemaPanel`** / the schema view — **secondary**, a small link. Optional: if it costs more than
     10 minutes, skip it and say so in the commit message.

#### A4 — forget a fact

**Surface:** a `⋯ → Forget` row action on the entity facts list rendered by **`EntityDetailPanel`**
(`:507-538`; `useEntityFacts(open ? entityId : null)` at `:135`). Because `EntityDetailPanel` is mounted by
**BOTH** `EntitiesTab` (→ `kg-entities`) **and** `ProjectGraphView` (→ `kg-graph`), **one edit lights the
action up in TWO panels.**

🔴 **NOT `kg-bio`.** `kg-bio` (`KgGlobalBioPanel` → `GlobalBioTab`) renders the user's global bio **summary**
— one long text blob over `useSummaries`. It has **no facts list, no fact rows, and does not import
`useEntityFacts`.** **There is nothing there to hang a row action on.** *(An earlier draft of the spec named
`kg-bio`; that was wrong. Recorded so it is not re-added.)*

**Files**

5. **`frontend/src/features/knowledge/hooks/useFactMutations.ts`** — **NEW** (≤80 lines; shaped **exactly**
   like `useRelationMutations.ts:34-56`). Exports **`useForgetFact`** *and* 🔴 **`useRestoreFact`**.
   🔴 **`onSuccess` MUST BRANCH ON THE BODY, NEVER ON THE HTTP STATUS.** `{invalidated: false}` **is a 200,
   and it is NOT a success:**
   | body | UI |
   |---|---|
   | `{invalidated: true}` | success toast |
   | `{invalidated: false, reason: "no matching fact found"}` | 🔴 **no success toast.** `toast.info("This fact is already gone — the list was out of date.")` **+ refetch** |
   | `{invalidated: false, reason: "already forgotten"}` | 🔴 **no success toast.** Same info-toast + refetch |
   Both arms invalidate `['knowledge-entity-facts', userId, entityId]` (the **exact** key from
   `useEntityFacts.ts:31-32`) **and** the `['knowledge-entity-detail', userId]` prefix.
   (`silent-success-is-a-bug-not-environment`.)

6. **`frontend/src/features/knowledge/components/FactRow.tsx`** — **NEW** (≤90 lines).
   **EXTRACT** the inline `<li>` at `EntityDetailPanel.tsx:513-536` into a component — mirroring the existing
   **`RelationRow`** (`EntityDetailPanel.tsx:60-122`), which is the file's own established pattern.
   `EntityDetailPanel` is already 640+ lines; **do not grow it.**
   - Add the `⋯ → Forget` action, `data-testid="entity-detail-fact-forget"`.
   - **CONFIRM FIRST** — an `AlertDialog` (**not `window.confirm`**: it is destructive and the copy is two
     lines).
   - 🔴 **THE COPY CHANGES. THE DRAFT'S STRING IS NOW A LIE** (`Q-38-OQ4` §5): W8-05 **BUILDS** restore, so
     *"there is no un-forget button"* would ship a **false claim**. Body string, **verbatim**:
     > *"Forgetting hides this fact from future context loads. It is not deleted — you can restore it from
     > **Show forgotten**."*
   - 🔴 **AND SHIP THE UN-FORGET UI, or BE-14b2 is dead surface:**
     - on a successful forget ⇒ an **UNDO TOAST (10s)** that **closes over the `fact_id`** and calls
       `restoreFact`, then invalidates `['knowledge-entity-facts', userId, entityId]`;
     - a **"Show forgotten"** checkbox on the facts list that flips `include_invalidated` (BE-14b3) —
       🔴 **put it in the query key** or the flip is a no-op against a warm cache;
     - forgotten rows render **muted** with a **Restore** button.
   - ⚠ **Do NOT wire this to `POST /pending-facts/{id}/reject`** (the pre-commit triage queue) or to
     `/internal/admin/.../reject-fact`. **Different objects, different lifecycles.**

7. **`frontend/src/features/knowledge/components/EntityDetailPanel.tsx`** — **EDIT.** Replace the inline `<li>`
   (`:513-536`) with `<FactRow key={f.id} fact={f} />`. Nothing else in this file changes for A4.
   🔴 **IT IS THREE SURFACES, NOT TWO** (`Q-38-A4-NOT-KG-BIO` §2 — the spec undercounted). `EntityDetailPanel`
   is mounted by `EntitiesTab.tsx:312` (→ **`kg-entities`**), `ProjectGraphView.tsx:171` (→ **`kg-graph`**)
   **AND `frontend/src/features/world/components/WorldRollupGraph.tsx:176`** (→ the **`world`** rollup graph,
   which imports it from `@/features/knowledge/components/EntityDetailPanel`). **Keep the action owned
   entirely by `EntityDetailPanel`** — **no per-mount props, no per-mount handler** — so all **three** inherit
   it from one edit. *(And note the third mount lands inside the very `world` panel W8-12 builds.)*

7b. **`frontend/src/features/knowledge/api.ts` + `hooks/useEntityFacts.ts`** — **EDIT.** Add
   `invalidateFact(factId, token)` **and `restoreFact(factId, token)`** next to `invalidateRelation`
   (`api.ts:1721-1727`); add `valid_until?: string | null` to `EntityFact`; thread `include_invalidated`
   through `getEntityFacts` (`api.ts:1903-1914`) **and into `useEntityFacts`'s queryKey**.

#### The Lane-B handler (GG-8 checklist step 8b)

8. **`frontend/src/features/studio/agent/handlers/knowledgeEffects.ts`** — **EDIT.** Add to
   `registerKnowledgeEffectHandlers()`:
   ```ts
   // `memory_forget` / `memory_remember` write the SAME graph the kg-* panels read, but they sit
   // OUTSIDE the ^kg_ namespace, so KNOWLEDGE_WRITE_PATTERN (a negative-lookahead over ^kg_)
   // CANNOT match them. Same handler, second pattern — ONE FILE PER DOMAIN (plan 30 §8.0b).
   // The trailing `$` EXCLUDES the three reads (memory_search / memory_recall_entity /
   // memory_timeline) BY CONSTRUCTION — a chatty read loop must never thrash the cache.
   export const MEMORY_WRITE_PATTERN = /^memory_(remember|forget)$/;
   registerEffectHandler(MEMORY_WRITE_PATTERN, knowledgeEffect);
   ```
   Put it **INSIDE the existing `registerKnowledgeEffectHandlers()`** (it is already idempotent-guarded by its
   `registered` flag). `knowledgeEffect` **already** invalidates `['knowledge-entity-facts']` +
   `['knowledge-summaries']` (`:29`) — **the body needs NO change.** Only the registration is missing.

   > 🟢 **REFUTATION — DO NOT "FIX" `KNOWLEDGE_WRITE_PATTERN`.** Plan 30's **X-4** claims `kg_create_node` has
   > no Lane-B handler. **REFUTED.** `KNOWLEDGE_WRITE_PATTERN` (`knowledgeEffects.ts:18`) is a **negative
   > lookahead over the whole `kg_` namespace** —
   > `/^kg_(?!project_list|graph_query|world_query|multi_query|entity_edge_timeline|schema_read|list_templates|sync_available|view_read|triage_list)/`
   > — so `kg_create_node` **and** `kg_project_entities_to_nodes` **ALREADY MATCH** and already invalidate
   > `['knowledge-entities']` / `['knowledge-subgraph']`. **Do not add a handler for them. Do not touch the
   > pattern.**
   >
   > 🔴 **A `RegExp`, NOT a string.** `registerEffectHandler`'s string branch is
   > `tool === p || tool.startsWith(p)` (`effectRegistry.ts:41`) — **not** a pattern match.
   > `registerEffectHandler('memory_(remember|forget)', …)` **as a string** would match **NOTHING** and ship a
   > **silent no-op handler** that no unit test (which registers and calls its own fake) could ever catch.
   > **Use the RegExp above, exactly.** (This is the trap plan 30 §8.0b records spec 36 falling into.)

**Tests**

- **`.../components/__tests__/ProjectionResultCard.test.tsx`** (NEW) — 🔴 the render-the-counters lock
  (`checklist-is-self-report-enforce-by-tests` — **without it, a builder "simplifying" it back to a toast
  reds nothing**):
  - feed `{nodes_created:3, nodes_existing:1, entities_seen:9, skipped:2, nodes_conflicted:2, truncated:true}`
    ⇒ assert **ALL FOUR** testids present (`proj-success` · `proj-conflicted` · `proj-truncated` ·
    `proj-skipped`);
  - feed `{…, nodes_conflicted:0, skipped:0, truncated:false}` ⇒ assert `proj-conflicted` / `proj-truncated` /
    `proj-skipped` are **null** while `proj-success` renders.
  - `the conflicted copy is the IN-PROJECT one` — assert the text does **not** contain *"another knowledge
    project"* (the stale global-FK string).
- **`.../components/__tests__/SeedFromGlossaryCard.test.tsx`** (NEW)
  - `entities_seen === 0 renders the empty-glossary state with a glossary deep-link` (`proj-empty`)
  - 🔴 `a 503 renders "couldn't read the glossary", NOT "the glossary is empty"` — **the whole reason
    BE-14a2 exists.**
  - `the CTA is not rendered at all when the project has no book_id` (the signal is **already on the wire**:
    `Project.book_id` — `frontend/src/features/knowledge/types.ts:23`. **No new field, no new route.**)
  - `a 409 surfaces detail.message inline and hides the CTA` — **never a generic "something went wrong".**
- **`.../components/__tests__/FactRow.test.tsx`** (NEW)
  - 🔴 `the confirm copy points at "Show forgotten" and does NOT claim it is one-way` — assert the text does
    **NOT** contain *"no un-forget"* / *"cannot be undone"*. **The draft's copy is now false.**
  - 🔴 `{invalidated:false} does NOT report success` — mock the API to resolve
    `{invalidated:false, reason:'no matching fact found'}`; assert the UI shows *"already gone"*, **no**
    success toast, and that a **refetch fired**.
  - `{invalidated:false, reason:'already forgotten'}` — same, no success toast.
  - 🔴 `the undo toast calls restoreFact with THAT row's fact_id and refetches`
  - 🔴 `"Show forgotten" flips include_invalidated AND it is in the query key` — a warm cache must not
    swallow the flip.
- **`frontend/src/features/studio/agent/handlers/__tests__/knowledgeEffects.test.ts`** (NEW or EDIT)
  - 🔴 `memory_forget matches a registered handler` — `matchEffectHandlers('memory_forget').length > 0`.
    **This is the test that catches a string-vs-RegExp registration** (a string returns 0 matches; this reds).
  - `memory_remember matches`
  - 🔴 `memory_search / memory_recall_entity / memory_timeline DO NOT match` — the trailing-`$` guard.
  - 🔴 `kg_create_node ALREADY matches (the X-4 refutation lock)` —
    `matchEffectHandlers('kg_create_node').length > 0`. **Pins the refutation so nobody "fixes" the pattern.**
  - `kg_graph_query does NOT match (a chatty read must not thrash the cache)`

**Run:** `cd frontend && npx vitest run src/features/knowledge src/features/studio/agent`

**DoD evidence:** `"W8-06: vitest <N> passed. ProjectionResultCard is a PERSISTENT inline card (not a toast) rendering ALL SIX wire-named counters (nodes_created/nodes_existing/entities_seen/skipped/nodes_conflicted/truncated), zeros included; its conflicted copy is the IN-PROJECT one (the stale 'another knowledge project' string is gone from BOTH the card AND graph_schema_tools.py); a 503 renders 'couldn't read the glossary' and NOT 'the glossary is empty'; the CTA hides itself when project.book_id is null. FactRow: the confirm copy points at Show-forgotten (it no longer claims one-way); {invalidated:false} shows 'already gone' and NOT success; the undo toast calls restoreFact with that row's id; Show-forgotten flips include_invalidated and is IN the query key. matchEffectHandlers('memory_forget').length > 0 (RegExp, not string) and memory_search/recall_entity/timeline do NOT match; kg_create_node still matches (X-4 refutation pinned)."`

**dependsOn:** W8-05

---

### W8-07 · [TEST] `studio-kg-write.spec.ts` — the 8a LIVE BROWSER smoke

🔴 **This is the DoD, not a formality.** This repo's `agent-gui-loop-needs-live-browser-smoke-not-raw-stream`
law exists because **a green unit suite has repeatedly hidden "the FE could not actually execute it."**

**Files**

- **`frontend/tests/e2e/specs/studio-kg-write.spec.ts`** — **NEW.** A sibling of `studio-compose.spec.ts` /
  `kg-panels.spec.ts`. **The harness already exists — use it:**
  - `tests/e2e/helpers/auth.ts` → `loginViaUI(page)`
  - `tests/e2e/helpers/api.ts` → `getAccessToken`, `createBook`, `createChapter`, **`createKnowledgeProject`**,
    **`createKnowledgeEntity`**, `trashBook` — **all four already exist**; do not write new ones.
  - `tests/e2e/pages/StudioPage.ts` → `goto(bookId)`, `openPanel(panelId, searchTerm)`
- Account: **`claude-test@loreweave.dev` / `Claude@Test2026`**.
- 🔴 **Run against the BAKED frontend.** `:5174` is the **nginx prod build** — a host `vite dev` **SHADOWS**
  it (`frontend-5174-is-baked-prod-nginx-not-vite`). **Rebuild the image, or use `vite dev` on `:5199`.**
  A stale image = a **false green** (`live-smoke-rebuild-stale-images-first`).
- ⚠ **Refs go stale in dockview.** Drive via `page.evaluate` + `data-testid`
  (`playwright-live-dockview-automation-recipe`).

**The cases — all five, in order:**

1. **`create an entity in kg-entities and see it AFTER A REFETCH`** — open `kg-entities` → `+ New entity` →
   name + a kind from the `<select>` → Submit → 🔴 **`await page.reload()`** → assert the entity is in the
   list. **From the server, not from optimistic state.**
2. **`create a relation in kg-graph, and it survives a reload`** — open `kg-graph` → `Link entities` → pick
   subject + a predicate from the `<select>` + object → Save → **reload** → assert the edge is on the canvas.
3. **`Mark wrong on that edge removes it`** — right-click the edge (or its label) → the dialog opens in
   `edit` mode → **Mark wrong** → confirm → assert the edge is gone. *(The create/delete round-trip — §3.1 A2
   + OQ-10. This is what proves the canvas is not draw-with-no-erase.)*
4. 🔴 **`seed-from-glossary renders the counters BY THEIR WIRE NAMES`** — on a project with an **empty** graph
   and a **non-empty** glossary: press the CTA → assert `seed-result-created` is visible and its numbers came
   from `nodes_created` / `nodes_existing` / `entities_seen`. **A spec that renders `created` gets
   `undefined`** — this case is what catches it.
5. **`Delete in kg-overview opens a REAL confirm dialog`** — open `kg-overview` → click Delete → assert a
   confirm dialog appears. *(Today: **nothing happens, silently.** This case is the regression lock on the
   three dead buttons.)*

**Run:** `cd frontend && npx playwright test tests/e2e/specs/studio-kg-write.spec.ts`

**DoD evidence:** `"W8-07: live smoke: studio-kg-write.spec.ts 5 passed against the BAKED FE (image rebuilt) with claude-test@loreweave.dev — created an entity in kg-entities and it survived a page reload; drew an edge in kg-graph, reloaded, Mark-wrong'd it away from the canvas; seed-from-glossary rendered nodes_created/nodes_existing/entities_seen; kg-overview's Delete opened a real confirm dialog (it was a silent noop before)."`

**dependsOn:** W8-02, W8-03, W8-04, W8-06

---
### W8-08 · [BE] book-service — the migration + the maps REST reads/create/delete

**The gap:** `book-service` ships **8 world-map MCP tools** (`mcp_maps.go:465-515`) over **3 real tables**
(`migrate.go:401-434`) with owner-scoping, CASCADE cleanup, MinIO blob handling and an
enumeration-oracle-free error model. **It is good code. A human cannot touch any of it.** The public REST
surface for maps is **ZERO routes** (`server.go:381-391` mounts `/v1/worlds` with create/list/get/patch/
delete + books-membership — **no `/maps` anywhere**).

**This slice writes the door.** It builds **BE-15a/b/c/e** + the migration. The PATCHes are W8-09.

**Files**

1. **`services/book-service/internal/migrate/migrate.go`** — **EDIT.** Append the three `ALTER TABLE`s from
   §4 of this plan, with the comment block, immediately after the existing map DDL (`:434`).

2. **`services/book-service/internal/api/maps.go`** — **NEW FILE** (the REST handlers; the MCP tools stay in
   `mcp_maps.go` — **do not merge them**). Handlers:

   - **`func (s *Server) createWorldMap(w, r)`** — **BE-15a**. `s.requireUserID(r)` → 401.
     `parseUUIDParam(r, "world_id")`. Body `{name, image_ref?}`; trim `name`, 422 if blank.
     Owner-check the world with the **exact** query `toolWorldMapCreate` uses
     (`mcp_maps.go:104`: `SELECT EXISTS(SELECT 1 FROM worlds WHERE id=$1 AND owner_user_id=$2)`) → **404** if
     not. INSERT, return `201 {map}` (with `image_url` resolved via `s.withImageURL`, `mcp_maps.go:83`).
   - **`func (s *Server) listWorldMaps(w, r)`** — **BE-15b**. Owner-check the world
     (`s.requireWorldOwner`, `worlds.go:333` — it already writes the uniform 401 + the no-oracle 404), then:
     🔴 **THE DRAFT'S TWO-WAY `LEFT JOIN … GROUP BY` IS WRONG AND HAS BEEN REPLACED**
     (`Q-38-BE-15b-MAP-LIST-WITH-COUNTS`). Joining **both** child tables in one statement fans out to
     **m × r** rows. `COUNT(DISTINCT …)` *would* patch it — but **the house pattern is a correlated scalar
     subquery** (`worldSelectSQL`, `worlds.go:185-193`, computes `book_count` exactly this way, with **no
     GROUP BY**). **Mirror the repo, do not hand-roll a join:**
     ```sql
     SELECT m.id, m.world_id, m.name, m.image_object_key, m.image_w, m.image_h,
            m.version, m.created_at, m.updated_at,
       COALESCE((SELECT COUNT(*) FROM map_markers mk WHERE mk.map_id = m.id), 0) AS marker_count,
       COALESCE((SELECT COUNT(*) FROM map_regions rg WHERE rg.map_id = m.id), 0) AS region_count
     FROM world_maps m
     WHERE m.world_id = $1 AND m.owner_user_id = $2
     ORDER BY m.created_at DESC
     ```
     Indexes `idx_map_markers_map` (`migrate.go:424`) + `idx_map_regions_map` (`:434`) **already serve these
     — no new index.** One query, one round-trip: the GET-storm is solved.
     Return `200 {"maps": items}` — 🔴 the key is **`maps`** (the FE contract), **not `items`**; and
     `items := make([]…, 0)` so an empty world yields `{"maps": []}`, **never `null`**. Set `image_url` per
     row from `s.mediaURL(key)` — a **pure string builder**, no presign/network call (`mcp_maps.go:83`), so
     per-row is free.
     🔴 **A SCAN ERROR IS A 500, NOT A DROPPED ROW.** Do **not** copy `toolWorldMapList`'s
     `if rows.Scan(...) == nil { append }` (`mcp_maps.go:360`) — that **silently omits a map** when a scan
     fails: this repo's `pgx-discarded-scan-zeroes-row` / silent-success class. Check the scan error
     explicitly **and** `rows.Err()` after the loop; both ⇒ 500. **Fix the same latent bug in
     `toolWorldMapList` while you are in the file** — one line, in-scope, **FIX-NOW**.
     🟢 The counts are **unfiltered raw child counts** (no soft-delete filter) because `map_markers` /
     `map_regions` have **no lifecycle column** — deletes are hard + CASCADE. *(If a tombstone column is ever
     added, the count predicate must be updated with it.)*
   - **`func (s *Server) getWorldMap(w, r)`** — **BE-15c**. 🔴 **ONE LOADER, TWO TRANSPORTS — this is the only
     real design call in the slice, and it is the thing that STOPS the tool/GUI drift every other row of this
     wave is fixing.** Refactor `toolWorldMapGet`'s body (`mcp_maps.go:252-334`) into
     `func (s *Server) loadWorldMap(ctx, mapID, ownerID uuid.UUID) (mapGetOut, error)`; **`toolWorldMapGet`
     becomes a 5-line wrapper over it** and the REST handler calls the **same fn**. *(Do the same for create:
     extract `createMapCore` from `toolWorldMapCreate`, mirroring the existing `createWorldCore` precedent at
     `mcp_worlds.go:31`. Both tools' existing tests must stay green.)*
     It already does the owner-scoped map read + markers + regions in one round-trip with the **right** error
     model (*"a sub-query / scan / iteration error is a TOOL FAILURE, not an empty result — otherwise a
     transient DB error on the markers read returns a map with all its pins silently dropped, presented as
     authoritative"* — `mcp_maps.go:276-278`). **Preserve that.** A markers-read failure is a **500**,
     **never** a map with an empty `markers[]`.
     **ADD to the SELECTs:** `version`, `updated_at`, **`image_w`, `image_h`** on the map (see the write-only
     table in §4); `updated_at` on each marker and each region.
     🟢 **The MCP tool `world_map_get` therefore returns the SAME enriched payload — that is INTENDED, not a
     leak.** The alternative (a REST-only projection) means **two SELECTs that will drift**. Additive fields
     are safe for MCP consumers.
     Return `200 {map, markers[], regions[]}` + an **`ETag: W/"<version>"`** header (BE-15d's `If-Match` has
     **no other way** to learn the current version — **the GET must hand it out**). Same on BE-15b.
   - **`func (s *Server) deleteWorldMap(w, r)`** — **BE-15e**. **Lift `toolWorldMapDelete`** — including the
     **best-effort blob sweep** (`mcp_maps.go:400-406`: *"the row is already gone, so a storage hiccup must
     NOT fail the delete"*). CASCADE drops markers + regions. Return **`204`**.

   **Shared, at the top of the file:**
   ```go
   // requireMapOwnerREST is requireMapOwner's HTTP twin: it resolves the map + confirms the caller
   // owns it, writing a uniform 404 otherwise. A foreign map and a missing map are INDISTINGUISHABLE
   // (no enumeration oracle) — the same contract mcp_maps.go:43 already holds.
   func (s *Server) requireMapOwnerREST(w http.ResponseWriter, r *http.Request, mapID, userID uuid.UUID) bool
   ```

3. **`services/book-service/internal/api/server.go`** — **EDIT.** Mount the maps routes **inside the existing
   `r.Route("/v1/worlds", …)` block** (`:381`), as a **sibling of `r.Route("/{world_id}", …)`**:
   ```go
   r.Route("/v1/worlds", func(r chi.Router) {
       r.Post("/", s.createWorld)
       r.Get("/", s.listWorlds)

       // Wave 8 (BE-15) — the public REST surface for world maps. ⚠ THIS BLOCK MUST BE REGISTERED
       // BESIDE (not inside) the /{world_id} route. chi's trie searches STATIC before PARAM
       // (ntStatic < ntParam), so the literal "maps" segment wins over {world_id}="maps" — but that
       // is load-bearing and NOT obvious, so maps_routing_test.go asserts it.
       r.Route("/maps/{map_id}", func(r chi.Router) {
           r.Get("/",    s.getWorldMap)       // BE-15c
           r.Delete("/", s.deleteWorldMap)    // BE-15e
           // BE-15d/f/g/h/i/j/k/l land here in W8-09 + W8-10.
       })

       r.Route("/{world_id}", func(r chi.Router) {
           r.Get("/", s.getWorld)
           r.Patch("/", s.patchWorld)
           r.Delete("/", s.deleteWorld)
           r.Get("/books", s.listWorldBooks)
           r.Post("/books", s.moveBookIntoWorld)
           r.Delete("/books/{book_id}", s.removeBookFromWorld)
           r.Post("/maps", s.createWorldMap)  // BE-15a
           r.Get("/maps", s.listWorldMaps)    // BE-15b
       })
   })
   ```
   🟢 **ZERO GATEWAY CHANGES.** `worldsProxy` forwards **every** `/v1/worlds*` path
   (`gateway-setup.ts:86-90` `pathFilter: p => p.startsWith('/v1/worlds')`, dispatched at `:592`). Verified.
   **Do not touch the gateway.**

4. **`contracts/api/books/v1/openapi.yaml`** — 🔴 **RE-READ IT AND DIFF IT AGAINST WHAT YOU BUILT.** The
   contract for BE-15a/b/c/e was **frozen in W8-0C**. It is the spec; if the code diverges, **the code is
   wrong** — unless the contract is, in which case **fix the contract in THIS commit.** *(The path
   `contracts/api/book-service/` **does not exist**. Do not create it.)*

**Tests**

- **`services/book-service/internal/api/maps_routing_test.go`** — **NEW.** 🔴 **The chi-order lock:**
  - `TestMapsRouteIsNotSwallowedByWorldIdParam` — build the router, issue
    `GET /v1/worlds/maps/<a-real-uuid>` and assert it reaches **`getWorldMap`** (not `getWorld` with
    `world_id="maps"`). Use a spy/`chi.RouteContext` inspection, or simply assert the handler 404s with
    `MAP_NOT_FOUND` rather than `invalid world_id`.
  - `TestWorldIdRouteStillWorks` — `GET /v1/worlds/<uuid>` still reaches `getWorld`.
- **`services/book-service/internal/api/maps_test.go`** — **NEW** (non-pool unit tests; the
  `worlds_test.go` convention):
  - `TestCreateWorldMap_RequiresName` — blank/whitespace name → 422.
  - `TestCreateWorldMap_RequiresAuth` — no Bearer → 401.
  - `TestGetWorldMap_InvalidUUID` → 400.
- **`services/book-service/internal/api/maps_db_test.go`** — **NEW** (needs `BOOK_TEST_DATABASE_URL`; use the
  existing **`dbTestServer(t)`** helper — `mcp_maps_test.go:174` is the precedent):
  - `TestListWorldMaps_CountsAreNotFannedOut` — 🔴 **MANDATORY.** Create a map with **2 markers AND 3
    regions**; assert `marker_count == 2` and `region_count == 3`. **A two-way LEFT JOIN returns 6 and 6.**
    🔴 **Both children must be populated on the SAME map, or the buggy SQL passes.** This is the test that
    kills the cartesian bug.
  - `TestGetWorldMap_ReturnsMarkersRegionsAndVersion` — the round-trip; assert `version == 1` on a fresh map
    and that every marker/region carries `updated_at`.
  - 🔴 `TestGetWorldMap_ReturnsImageDims` — upload a PNG, then **re-GET**; assert `image_w`/`image_h` are
    **non-nil**. Then a map created with `image_ref` ⇒ **NULL dims** and it still 200s. *(This is the test
    that proves the three write-only columns are now READ. Today the dims are visible only in the upload
    response and are lost on reload — **for every format**.)*
  - 🔴 `TestListWorldMaps_ScanErrorIs500_NotADroppedRow` — the `toolWorldMapList` silent-omit bug, ported
    forward.
  - `TestGetWorldMap_ForeignMapIs404_SameBodyAsMissing` — 🔴 **no enumeration oracle.** Create a map as user
    A; GET it as user B; assert **404** and that the body is **byte-identical** to the 404 for a random,
    non-existent UUID.
  - `TestDeleteWorldMap_CascadesMarkersAndRegions` — 204, then assert both child tables are empty for that
    map id.
  - `TestListWorldMaps_ForeignWorldIs404`
  - ⚠ These hit the shared dev DB. They are Go, so there is no xdist mark — but **do not TRUNCATE**; create
    per-test UUIDs (`shared-dev-db-not-clean-fixture-e2e`).

**Run:** `cd services/book-service && go test ./...`

**DoD evidence:** `"W8-08: book-service go test ./... ok (<N> tests). Migration applied: world_maps.version (DEFAULT 1) + map_markers.updated_at + map_regions.updated_at — BACKFILLED FROM created_at, not DEFAULT now() (a 3-day-old seeded marker reads updated_at == created_at, asserted), and schemaSQL applies TWICE with no error. GET /v1/worlds/maps/<uuid> reaches getWorldMap and NOT getWorld{world_id=maps} (maps_routing_test asserted). marker_count/region_count come from CORRELATED SCALAR SUBQUERIES (the house pattern, worlds.go:185) — a map with 2 markers + 3 regions reports 2 and 3, not 6 and 6. worldMapDetail now carries version/updated_at/image_w/image_h and BOTH SELECTs read them: an uploaded PNG's dims SURVIVE A RE-GET (they were write-only at HEAD, for every format). loadWorldMap/createMapCore are shared by the REST route AND the MCP tool — one SELECT, no drift. A foreign map 404s with a body byte-identical to a missing one."`

**dependsOn:** W8-00, W8-0C

---

### W8-09 · [BE] book-service — **the UPDATE semantics that exist at NO layer**

🔴 **This is the load-bearing slice of 8b.** Today the map tool set is **add/remove only** at **every** layer:
there is no `world_map_update_*`, no `PATCH`, no repo method. **Renaming a map, dragging a pin, or reshaping
a region has NO implementation anywhere.**

**The naive fallback — delete + recreate — is REJECTED, for four concrete reasons. Do not "simplify" back to it:**

1. **It churns ids.** A marker id is the handle for its inspector selection, its deep link, and (once
   BE-15m lands) the agent's undo hint. Recreating on every drag invalidates all three.
2. **It is not atomic.** DELETE succeeds, POST fails (a network blip) ⇒ **the user's pin is GONE.** There is
   no transaction across two HTTP calls.
3. **It is a write storm.** A drag is a *continuous* gesture. Delete+create per drop is 2 writes; per
   drag-frame it is unbounded.
4. **It destroys ordering.** Both children `ORDER BY created_at` (`mcp_maps.go:280, 303`), so a "move" would
   silently jump the pin to the **end** of the render order.

#### The concurrency decision — DELIBERATE, not reflex. Do not "add OCC" to markers.

| Object | OCC? | Why |
|---|---|---|
| **map rename** | ✅ **If-Match on `version`** — **428** without the header, **412 + the current map as the body** on a mismatch (the same contract knowledge-service's entity PATCH already uses, `entities.py:1035`) | A rename is **rare, human-paced and conflict-worthy**. A 412 that says *"renamed on another device"* is the right answer. |
| **marker / region position** | ❌ **NO version, NO If-Match. Last-write-wins.** | A positional write is a **DRAG**. OCC over a drag produces a **412 storm** and — per this repo's own `instant-commit-control-over-occ-entity-needs-write-serialization` lesson — **self-conflicts on the second rapid edit of the same object.** The FE **serializes writes per object id** instead (W8-13). **This is a decision, not an omission. It is written here so a reviewer does not "fix" it into a 412 storm.** |

**Files**

1. **`services/book-service/internal/api/maps.go`** — **EDIT.** Add:

   - **`patchWorldMap`** — **BE-15d.** Read `If-Match`; **absent ⇒ 428** (`PRECONDITION_REQUIRED`). Parse it as
     an int `version`. Then:
     ```sql
     UPDATE world_maps SET name = $1, version = version + 1, updated_at = now()
     WHERE id = $2 AND owner_user_id = $3 AND version = $4
     RETURNING id, world_id, name, image_object_key, image_w, image_h, version, created_at, updated_at
     ```
     - `RowsAffected() == 0` ⇒ **disambiguate**: re-read the row owner-scoped. **Row exists ⇒ 412** with the
       **CURRENT map as the response body** (the FE resets its baseline from it — it must **never** re-GET or
       blind-retry). **Row absent ⇒ 404** (uniform).
     - 422 on a blank name.
   - **`createMarker` (BE-15g)** / **`deleteMarker` (BE-15i)** / **`createRegion` (BE-15j)** /
     **`deleteRegion` (BE-15l)** — **lift the bodies** of `toolWorldMapAddMarker` / `toolWorldMapRemoveMarker`
     / `toolWorldMapAddRegion` / `toolWorldMapRemoveRegion` (`mcp_maps.go:93-462`). **All the validation is
     already written** — coords in `[0,1]`, polygon ≥3 points, each point in `[0,1]`. **Reuse it; do not
     re-derive it.** 422 on a violation.
     🔴 **The REST deletes take BOTH `map_id` and `marker_id` in the path — the MCP tools take only
     `marker_id`.** So the REST SQL needs **one more predicate** than the tool's:
     `AND m.map_id = $2` (the path's map). See the scope-gating box below.
   - **`patchMarker`** — **BE-15h.** 🔴 **PARTIAL semantics — and the decode is the HOUSE pattern, not an
     invention** (`Q-38-BE-15h-MARKER-PATCH`): decode into **`map[string]any`** and branch on **KEY
     PRESENCE**, exactly as **`patchWorld` (`worlds.go:270-292`)** and **`patchBook` (`server.go:1022-1046`)**
     already do. **A `*string` CANNOT distinguish absent from `null`** — `encoding/json` sets both to `nil`.
     ```go
     var in map[string]any
     if err := json.NewDecoder(r.Body).Decode(&in); err != nil { /* 400 BOOK_VALIDATION_ERROR */ }
     setClauses := []string{"updated_at=now()"}      // ALWAYS first
     args := []any{markerID, mapID, ownerID}; paramIdx := 4
     if v, ok := in["label"]; ok { /* present */ }
     ```
     **Per-field rules** (`map_markers`: `label`/`x`/`y` are **NOT NULL**; `entity_id`/`marker_type` are
     **nullable** — `migrate.go:414-424`):
     | field | absent | present + value | present + `null` |
     |---|---|---|---|
     | `label` | unchanged | `TrimSpace` non-empty, else **422** | 🔴 **422** — the column is NOT NULL; `null` is **NOT** a clear here |
     | `x`, `y` | unchanged | must assert to `float64` **and** be in `[0,1]` (positive form ⇒ NaN/±Inf fail), else **422** | 🔴 **422** |
     | `marker_type` | unchanged | set (**free-form, no enum**) | **SET NULL** |
     | `entity_id` | unchanged | `uuid.Parse`, else **422** *(a soft cross-service ref — do **not** validate it against glossary)* | **SET NULL** |
     🔴 **DO NOT reuse `stringFromAny` blindly** (`server.go:1124-1132`): it returns `nil` for a **non-string**,
     which would **silently CLEAR the field on a typo** — the silent-swallow class.
     🔴 **`{}` (no keys) ⇒ 200 with the current marker, `updated_at` bumped.** **Do NOT add a "nothing to do"
     no-op guard and do NOT 422** — **a false no-op is worse than a redundant idempotent write**
     (`noop-guard-on-partial-data-silently-swallows-the-write`).
     - **NO version, NO If-Match** (see the table above) — 🔴 **enforce it BY TEST: a PATCH carrying a bogus
       `If-Match` header must still return 200.** That pins *"no OCC"* as **behaviour**, so a later builder
       cannot "helpfully" add it.
   - **`patchRegion`** — **BE-15k.** Same `map[string]any` presence decode. `polygon` is **REPLACE-WHOLE**
     (≥3 points, each `[x,y]` with both in `[0,1]`; **422** otherwise — reuse the validation lifted from
     `toolWorldMapAddRegion`, `mcp_maps.go:199-206`). 🔴 **`polygon: null` ⇒ 422** (*"polygon cannot be
     cleared"* — the column is `JSONB NOT NULL`, `migrate.go:430`). **There is no per-vertex merge and no
     point-index addressing** — the FE already holds the full ring from BE-15c and re-sends it. *(A
     per-vertex merge across two writers produces a **self-intersecting ring** — strictly worse than LWW.)*
     🔴 **A region (or marker) PATCH must NOT bump `world_maps.version` or `world_maps.updated_at`** — if it
     did, an FE holding an `If-Match` for BE-15d would **spuriously 412 after any drag.**

   - **`parseIfMatch` — BE-15d's header parser** (new `maps_rest.go`; book-service has **ZERO** If-Match code
     today — `grep` finds a single **comment** at `chapter_reorder.go:16`, so this is the **first Go OCC**).
     **Mirror knowledge-service's Python contract verbatim** (`entities.py:90-116`):
     `""` ⇒ the *missing* sentinel ⇒ **428**. 🔴 **Accept `W/"3"`, `"3"`, AND a bare `3`** — be lenient; a
     curl/Go caller sending the bare int **must not 422**. Anything else ⇒ **422**
     `BOOK_VALIDATION_ERROR "If-Match must be an ETag with an integer version"`.
     Emit `etag(v) = fmt.Sprintf("W/\"%d\"", v)` — **weak**, exactly like `entities.py:111-116`.

   🔴 **SCOPE GATING ON EVERY CHILD ROUTE — `gate-must-derive-scope-from-the-loaded-row`.** Every
   marker/region handler must verify **BOTH** `world_maps.owner_user_id == caller` **AND**
   `marker.map_id == {map_id from the path}`. **A marker id from ANOTHER map, addressed under YOUR map id,
   must 404 — not patch.** Express it in SQL exactly as the existing deletes do (`mcp_maps.go:432`):
   ```sql
   UPDATE map_markers m SET label = COALESCE($1, m.label), …, updated_at = now()
   FROM world_maps wm
   WHERE m.id = $A AND m.map_id = $B AND m.map_id = wm.id AND wm.owner_user_id = $C
   RETURNING m.id, m.label, m.x, m.y, m.marker_type, m.entity_id, m.updated_at
   ```
   — note **`m.map_id = $B`** (the path's map) **and** the owner join. `RowsAffected() == 0` ⇒ the **uniform**
   not-found. **Same for regions, and same for the DELETEs.**

2. **`services/book-service/internal/api/server.go`** — **EDIT.** Extend the `/maps/{map_id}` sub-router:
   ```go
   r.Route("/maps/{map_id}", func(r chi.Router) {
       r.Get("/",    s.getWorldMap)     // BE-15c
       r.Patch("/",  s.patchWorldMap)   // BE-15d — If-Match OCC
       r.Delete("/", s.deleteWorldMap)  // BE-15e
       r.Post("/markers", s.createMarker)                       // BE-15g
       r.Patch("/markers/{marker_id}", s.patchMarker)           // BE-15h
       r.Delete("/markers/{marker_id}", s.deleteMarker)         // BE-15i
       r.Post("/regions", s.createRegion)                       // BE-15j
       r.Patch("/regions/{region_id}", s.patchRegion)           // BE-15k
       r.Delete("/regions/{region_id}", s.deleteRegion)         // BE-15l
   })
   ```

3. **`contracts/api/books/v1/openapi.yaml`** — 🔴 **RE-READ + DIFF** (BE-15d/g/h/i/j/k/l were frozen in
   W8-0C). Confirm the `If-Match` header param, the **428**, and the **412-body-is-the-current-map** shape all
   match what you built. *(`contracts/api/book-service/` **does not exist** — do not create it.)*

**Tests** — `services/book-service/internal/api/maps_patch_db_test.go` (**NEW**, `dbTestServer(t)`):

- 🔴 `TestPatchMarker_ForeignMarkerUnderYourMapIs404_NotPatched` — **THE scope-gate test.** Create map A
  (yours) with marker M-A, and map B (also yours) with marker M-B. `PATCH /v1/worlds/maps/{A}/markers/{M-B}`
  ⇒ **404**, and 🔴 **assert M-B is UNCHANGED in the DB.** *(A handler that trusts a bare `marker_id` patches
  it. **Do NOT stop at the status code — a handler that 404s AFTER writing still passes a status-only test.**)*
- 🔴 `TestCreateMarker_ForeignMapIs404_AndNothingWasInserted` — the same hole on the **CREATE** path (the
  `INSERT … SELECT` gate). Assert `SELECT count(*) FROM map_markers WHERE map_id = <victim>` **did not
  increase.**
- `TestPatchMarker_ForeignMapIs404_IdenticalBody` — a map owned by another user; the 404 body is
  byte-identical to a missing-map 404.
- 🔴 `TestPatchMarker_AbsentKeyIsUnchanged_ExplicitNullClears` — **the tri-state test.**
  1. PATCH `{"x": 0.5}` ⇒ `label` and `entity_id` are **unchanged**.
  2. PATCH `{"entity_id": null}` ⇒ `entity_id` **becomes NULL**; `{"entity_id"` **absent** ⇒ it is
     **PRESERVED**. *(Same pair for `marker_type`.)*
  3. PATCH `{"label": null}` ⇒ 🔴 **422** (NOT NULL column — `null` is not a clear here).
  4. PATCH `{}` ⇒ **200**, row unchanged, `updated_at` **advanced** (idempotent touch, **not** 422).
  **A `*string`-only decode fails case 1 or case 2. This test is what forces the `map[string]any` presence
  decode.**
- 🔴 `TestPatchMarker_BogusIfMatchIsStill200` — **pins "NO OCC on children"** as behaviour, so a later
  builder cannot "helpfully" add a 412 storm to a drag.
- 🔴 `TestPatchRegion_DoesNotBumpMapVersion` — a region drag must not 412 an open rename dialog.
- 🔴 `TestPatchMarker_BumpsUpdatedAt` — capture `updated_at`, sleep ~10ms, PATCH, assert the timestamp
  **strictly advanced**. *(Without this, `updated_at` is a write-only column and CLAUDE.md bans it.)*
- `TestPatchRegion_PolygonIsReplaceWhole_AndValidates` — a 2-point polygon ⇒ 422; a point at `1.5` ⇒ 422; a
  valid 4-point polygon replaces the old one entirely.
- 🔴 `TestPatchMap_RenameRequiresIfMatch` — no `If-Match` ⇒ **428**.
- 🔴 `TestPatchMap_StaleIfMatchIs412_AndReturnsTheCurrentMap` — PATCH with `version: 1` twice; the second ⇒
  **412**, and the **response body carries the CURRENT map** (with `version: 2` and the new name), so the FE
  can reset its baseline **without a re-GET**.
- `TestPatchMap_BumpsVersion` — `version` goes 1 → 2 → 3.
- `TestDeleteMarker_ForeignMarkerUnderYourMapIs404` — the same scope gate on DELETE.
- `TestCreateMarker_RejectsOutOfRangeCoords` — x=1.2 ⇒ 422 (mirrors `mcp_maps_test.go:26`).

**Run:** `cd services/book-service && go test ./...`

**DoD evidence:** `"W8-09: book-service go test ./... ok (<N> tests). UPDATE now exists: PATCH map (If-Match → 428 without / 412 + the current row on stale, version bumps 1→2→3), PATCH marker + region (partial: absent=unchanged, explicit null=clear, {} = idempotent 200; updated_at strictly advances — asserted). Scope gate proven: a marker from map B addressed under map A returns 404 AND leaves M-B unchanged in the DB."`

**dependsOn:** W8-08

---
### W8-10 · [BE] BE-15f — the PUBLIC image upload, and retire the dead internal route

**The bug:** the **one** map route that exists today is **unreachable from a browser BY CONSTRUCTION.**
`POST /internal/worlds/maps/{map_id}/image` (`server.go:200`) sits inside `r.Route("/internal", …)` behind
`r.Use(s.requireInternalToken)` (`:185-186`) and takes the identity from a **`?user_id` query param**
(`maps_image.go:35`). The gateway proxies `/v1/worlds*` only — **`/internal` is not public.** And **no
service anywhere calls it**: `grep -rn "worlds/maps" services/ frontend/src` (excluding book-service's own
handler) → **ZERO hits.** **The route is dead on arrival.** *(Re-run that grep in pre-flight P6 before you
delete it — OQ-3 says "verify once more".)*

**Files**

> **▶ DECISIONS FOLDED:** `Q-38-OQ3-RETIRE-DEAD-INTERNAL-IMAGE-ROUTE` · `Q-38-BE-15f-PUBLIC-IMAGE-UPLOAD` ·
> `Q-38-OQ8-WEBP-NULL-PIXEL-DIMS`. 🔴 **CONTRADICTION FIXED:** the draft kept `uploadWorldMapImage` as a
> **`?user_id` shim**. The register says **DELETE IT** — no `?user_id` query param survives **anywhere**.
> A dead internal route that **trusts an identity from a query param** is a standing **tenancy-audit
> false-positive** with **zero callers**. If a BFF-mediated or worker upload ever needs one, re-adding a thin
> `/internal` mount over the extracted core is a **3-line change**.

1. **`services/book-service/internal/api/maps_image.go`** — **EDIT. Extract, then DELETE the old entrypoint.**
   - Refactor the body (currently lines **40–125**) into:
     ```go
     // writeWorldMapImage does the whole upload for an ALREADY-AUTHENTICATED userID:
     // MinIO-nil 503 → owner-scoped SELECT 404 (foreign-or-missing, no oracle) → multipart
     // → content-type gate (png/jpg/gif/webp) 415 → size 413 → pixel-dim decode → PutObject
     // → UPDATE world_maps (image_object_key/w/h + updated_at) → orphan sweep of the prior
     // object → 200 JSON. Every error code/body BYTE-IDENTICAL to today's:
     // MEDIA_UNAVAILABLE/503 · MAP_NOT_FOUND/404 · UNSUPPORTED_MEDIA_TYPE/415 ·
     // MEDIA_TOO_LARGE/413 · MEDIA_UPLOAD_FAILED/500.
     func (s *Server) writeWorldMapImage(w http.ResponseWriter, r *http.Request, mapID, userID uuid.UUID)
     ```
   - **NEW: `func (s *Server) uploadWorldMapImagePublic(w, r)`** — **BE-15f.** `s.requireUserID(r)` (**JWT**,
     not a query param) ⇒ 401 on failure; `parseUUIDParam(r, "map_id")`; call `writeWorldMapImage`.
   - 🔴 **DELETE the old `?user_id`-parsing entry function** (`maps_image.go:30-39`) entirely — **not a
     shim.** The owner-scoped SELECT/UPDATE already filter on `owner_user_id`, so the tenancy guarantee is
     preserved **verbatim** by the extracted core.
   - 🔴 **FIX THE 413 CONTRACT WHILE YOU ARE IN HERE** (`Q-38-BE-15f` §4). Spec 38:299 promises **413**; the
     code returns **400** (`maps_image.go:59-62`). Before `ParseMultipartForm`, set
     `r.Body = http.MaxBytesReader(w, r.Body, int64(maxImageSize)+(1<<20))` and map a `ParseMultipartForm`
     failure to `writeError(w, http.StatusRequestEntityTooLarge, "MEDIA_TOO_LARGE", …)`. Keep the existing
     `fh.Size > maxImageSize` 413 check as-is.
   - 🟢 **The upload bumps `updated_at` but does NOT bump `version`** (`Q-38-MIGRATION-VERSION-UPDATEDAT` §4 —
     **PO veto point, and it OVERRIDES the looser reading in `Q-38-BE-15d` §4**). **An image replace is not a
     competing rename**, and bumping `version` would **412 an in-flight rename for nothing.** Leave
     `maps_image.go:108`'s SQL shape as-is (it already sets `updated_at=now()`).
   - ⚠ **WebP stores NULL pixel dims** — there is **no stdlib webp decoder** (`maps_image.go:16-19`) — **and
     so does every `world_map_create` with an `image_ref`** (`mcp_maps.go:116-118`). **NULL dims are not
     webp-specific.** Harmless (coords are *relative*) — **but the inspector must not render `0 × 0`**
     (W8-13). 🟢 **Conscious won't-fix, NO defer row.** Do **not** add a webp dependency; do **not** reject
     webp; do **not** fabricate a fallback dimension. **Keep the existing explanatory comment at
     `maps_image.go:16-19` — it is accurate.**
   - Update the now-stale docstrings that point at the internal route: `maps_image.go:3-10` and
     **`mcp_maps.go:5`**.

2. **`services/book-service/internal/api/server.go`** — **EDIT.**
   - Mount the public route in the `/maps/{map_id}` sub-router:
     `r.Post("/image", s.uploadWorldMapImagePublic)   // BE-15f`
   - 🔴 **RETIRE the dead internal route** — **DELETE line 200 entirely**
     (`r.Post("/worlds/maps/{map_id}/image", s.uploadWorldMapImage)` inside the `/internal` group).
     **First re-run the grep** (`grep -rn "worlds/maps" services/ frontend/src` excluding book-service's own
     handler) — it is still **ZERO** (re-verified 2026-07-13). Delete `uploadWorldMapImage` **and its
     `?user_id` parsing** with it.
     **If a caller HAS appeared** (it will not have), keep the route over the extracted core and file a defer
     row instead — **that is a defer, not a stop.**
     ⚠ Its 503-when-no-MinIO unit test (`mcp_maps_test.go:160-169`) calls `s.uploadWorldMapImage`
     **directly**. **Repoint it at `uploadWorldMapImagePublic`** — do **not** delete the coverage. And
     `mapImageReq` (`mcp_maps_test.go:~139`) builds `"/internal/worlds/maps/"+mapID+"/image"` — change it to
     `"/v1/worlds/maps/"+mapID+"/image"` with a Bearer JWT and **drop the `?user_id` plumbing**. **Replace**
     `TestUploadWorldMapImage_BadUserID_400` with `TestUploadWorldMapImage_NoJWT_401`.
   - 🔴 **AND ADD A ROUTE-SHADOWING REGRESSION ASSERT:** `GET /v1/worlds/{world_id}` **still** reaches
     `getWorld` — i.e. the new **static `maps` sibling did not shadow the `{world_id}` param route.**

3. **`contracts/api/books/v1/openapi.yaml`** — 🔴 **RE-READ + DIFF** (BE-15f + its `multipart/form-data`
   body and `413`/`415`/`503` were frozen in W8-0C). **Confirm the internal route is documented NOWHERE.**
   *(`contracts/api/book-service/` **does not exist**.)*

**Tests** — `services/book-service/internal/api/maps_image_test.go` (**NEW**) + edits:

- `TestUploadMapImagePublic_RequiresJWT` — no `Authorization: Bearer` ⇒ **401** (**not** a `?user_id` fallback
  — 🔴 assert that passing `?user_id=<someone-else>` **without** a JWT is still **401**. That is the whole
  point of the public route.)
- `TestUploadMapImagePublic_NoMinioIs503` — the repointed existing case.
- `TestUploadMapImagePublic_ForeignMapIs404` (`dbTestServer`) — a map owned by another user ⇒ 404, uniform.
- `TestUploadMapImagePublic_RejectsUnsupportedType` — a `text/plain` part ⇒ **415**.
- 🔴 `TestUploadMapImagePublic_TooLargeIs413` — **it is 400 today.** `MaxBytesReader` + the
  `ParseMultipartForm`-failure mapping is what makes it a **413**, per the spec's own contract.
- 🔴 `TestUploadMapImagePublic_BumpsUpdatedAt_ButNotVersion` — an image replace must **not** 412 an in-flight
  rename.
- 🔴 `TestWorldIdRouteStillWorksAfterMapsSibling` — `GET /v1/worlds/<uuid>` still reaches `getWorld` (the
  static `maps` segment did not shadow the param route).
- 🔴 `TestUploadMapImagePublic_WebpStoresNullDims` (`dbTestServer`, if a webp fixture is cheap) — assert
  `image_w`/`image_h` are **NULL** and the upload still **succeeds (200)**. *(Pins the known limitation so
  nobody "fixes" it into a rejection.)*
- `TestInternalMapImageRouteIsGone` — assert `POST /internal/worlds/maps/<uuid>/image` on the built router
  returns **404** (the route is retired).

**Run:** `cd services/book-service && go test ./...`

**DoD evidence:** `"W8-10: book-service go test ./... ok. POST /v1/worlds/maps/{id}/image is PUBLIC and JWT-gated (a ?user_id without a JWT is 401 — asserted); the dead /internal/worlds/maps/{id}/image route is DELETED (grep for callers: still zero; TestInternalMapImageRouteIsGone asserts 404); webp uploads succeed with NULL dims (pinned)."`

**dependsOn:** W8-08

---

### W8-11 · [BE] BE-15m — 3 new MCP update tools (agent parity, GG-2)

🔴 **WITHOUT THIS SLICE, WAVE 8 CREATES A *NEW* INVERSE GAP: the human could move a pin and the agent could
not.** That is the exact asymmetry this entire plan exists to close, manufactured by the plan itself. **It
ships in the same wave as the REST, not "later".**

**Files**

> **▶ DECISIONS FOLDED:** `Q-38-BE-15m-UPDATE-TOOLS` · `Q-38-CHILD-ROUTE-SCOPE-GATE` §5. 🔴 **"extract a
> shared repo func IF IT IS CLEANER" is NOT optional — it is MANDATORY.** Two copies of this SQL is the
> `css-var-duplicated-across-two-consumers-drifts` class, on a **tenancy-load-bearing** statement.

0. 🔴 **`services/book-service/internal/api/maps_update.go`** — **NEW FILE. ONE SHARED UPDATE CORE, NOT TWO.**
   `updateMapCore` / `updateMarkerCore` / `updateRegionCore(ctx, ownerID, id, patch)`. Each is owner-scoped by
   the existing JOIN pattern (mirror `mcp_maps.go:431-433`'s `… USING world_maps wm … wm.owner_user_id=$2`,
   as an `UPDATE`), sets `updated_at=now()` (**+ `version=version+1` for the map only**), `RETURNING`s the
   row; **`RowsAffected()==0` ⇒ uniform "not found"** (no cross-owner existence oracle).
   **BOTH the REST PATCH handlers (BE-15d/h/k, W8-09) AND the 3 MCP tools call these.**
   Field tri-state: `type fieldPatch struct { Action patchAction /* unchanged | clear | set */; Value string }`.
   **REST** decodes an explicit JSON `null` ⇒ `clear` (via `map[string]any` / `map[string]json.RawMessage`).
   **MCP** maps `""` ⇒ `clear`.
   🔴 **The MCP variants take a bare `marker_id`/`region_id` with NO `map_id`** (same shape as
   `world_map_remove_marker`), so they carry the **owner leg** but **not** the containment leg — *there is
   nothing to contain against.* **The REST variants carry BOTH.** Same law, different arity.

1. **`services/book-service/internal/api/mcp_maps.go`** — **EDIT.** Three new tools over those cores:

   - **`world_map_update`** — rename. In: `{map_id, name, expected_version int \`json:",omitempty"\`}`. Out: `{map}`.
     🔴 **`expected_version` is OPTIONAL** (the shipped precedent is glossary's `book_tools.go:260-281`
     pointer+omitempty+`base_version`): **present and stale** ⇒ the tool **errors** *"map was renamed
     elsewhere (current version N, name 'X') — re-read with world_map_get and retry"*; **omitted** ⇒
     last-write-wins. **REST keeps STRICT `If-Match` (428/412)** because a **GUI tab goes stale for hours**,
     while an agent's `world_map_get` is **seconds old**. It **still bumps `version`**, so a concurrent GUI
     rename correctly gets a 412. *(State all of this in the tool description.)*
     🔴 **To make the arg USABLE, `worldMapDetail` MUST expose `version` + `updated_at`** — W8-08 already adds
     them. **An OCC arg the agent cannot READ is a write-only-field bug.**
   - **`world_map_update_marker`** — In: `{marker_id, label?, x?, y?, marker_type?, entity_id?}`. Out:
     `{marker}`. Owner-scoped by the JOIN to `world_maps`.
   - **`world_map_update_region`** — In: `{region_id, name?, polygon?, entity_id?}`. Out: `{region}`.
     `polygon` present ⇒ **replace-whole**, ≥3 points each in `[0,1]` (reuse `mcp_maps.go:199-206`).
   - 🔴 **ALL THREE: zero fields supplied ⇒ a TOOL ERROR `"nothing to update"`. NEVER a
     `200 {updated:true}`** (`silent-success-is-a-bug`).
     *(⚠ Note this is the **opposite** of the REST `{}` rule — and deliberately so: a REST `{}` from a
     debounced form is an **idempotent touch**, while an agent calling an update tool with **no fields** has
     made a **mistake it needs to be told about**.)*

   **Registration** in `registerMapTools` (`mcp_maps.go:465`), matching the existing style exactly:
   ```go
   addTool(srv, "world_map_update",
       "Rename a map you own. REVERSIBLE: call world_map_update again with the previous name. "+
           "Last-write-wins (no version): a concurrent GUI rename will get a 412 and re-apply.",
       lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeNone, nil, []string{"rename map", "update map"}),
       s.toolWorldMapUpdate)

   addTool(srv, "world_map_update_marker",
       "Move or edit a pin on a map you own (label, x/y in 0.0-1.0, type, linked glossary location "+
           "entity). Only the fields you pass change. REVERSIBLE: call it again with the PREVIOUS "+
           "values (they are in the world_map_get you read before this).",
       lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeNone, nil, []string{"move pin", "edit marker", "rename pin"}),
       s.toolWorldMapUpdateMarker)

   addTool(srv, "world_map_update_region",
       "Reshape or edit a region on a map you own (name, polygon of relative [x,y] points, linked "+
           "glossary location entity). Only the fields you pass change. REVERSIBLE: call it again "+
           "with the PREVIOUS values.",
       lwmcp.NewToolMeta(lwmcp.TierA, lwmcp.ScopeNone, nil, []string{"reshape region", "edit region"}),
       s.toolWorldMapUpdateRegion)
   ```
   **Tier-A, reversible** — say the inverse in the description, exactly as the existing 8 do
   (`mcp_maps.go:502`: *"Undoes world_map_add_marker (re-add it with the same label + coords to restore)"*).

   ⚠ **Go MCP tool args carry `jsonschema` tags** (`worldMapCreateIn` — `mcp_maps.go:68-71`). **`marker_type`
   stays free-form** — 🔴 **and that is NOT an exception to the closed-set discipline; the rule simply does
   not reach here** (`Q-38-OQ7-MARKER-TYPE-VOCAB` §2). The `IN-*` enum rule binds **frontend tools**
   (chat-service `frontend_tools.py` + `contracts/frontend-tools.contract.json`), where an unknown value
   **SILENTLY NO-OPS the GUI** (the `panel_id:"editor"` bug). `world_map_add_marker` is a **book-service
   DOMAIN tool**: its value is **stored verbatim and rendered**, so an unknown value degrades to *"default
   pin"* — **not** a silent no-op. The rule demands an enum **for closed sets**; a worldbuilder's pin kinds
   are **genuinely open**. **No exception is being granted.** *(A closed set added later still MUST be an
   enum tag.)*
   ⚠ **Partial semantics in Go:** an omitted JSON field decodes to the zero value, so `x: 0` (a legitimate
   left-edge coordinate!) is **indistinguishable** from "absent". 🔴 **Use pointer fields** (`X *float64`,
   `Label *string`, …) in the `In` structs so `nil` = absent. **A `float64` field here would make the pin
   un-draggable to the left edge and it would look like a rounding bug.**

2. **`services/book-service/internal/api/mcp_prefix_contract_test.go`** — **CHECK.** It asserts the `world_`
   prefix namespace (`EXTRA_PREFIX_MAP` — `ai-gateway config.ts:128`, `book: ['world_']`). The three new names
   all start with `world_` ⇒ **already satisfied.** If the test counts tools, **update the count.**

**Tests** — `services/book-service/internal/api/mcp_maps_update_test.go` (**NEW**):

- `TestWorldMapUpdateMarker_RejectsOutOfRangeCoords` (no DB — validation short-circuits).
- 🔴 `TestWorldMapUpdateMarker_XZeroIsNotTreatedAsAbsent` (`dbTestServer`) — set a marker to `x = 0.0`;
  assert the DB holds **0.0**, not the previous x. **This is the pointer-field test. Without it, the left
  edge of every map is unreachable by the agent.**
- `TestWorldMapUpdateMarker_ForeignMarkerIsNotFound` — a marker on another user's map ⇒ `"marker not found"`,
  uniform (mirror `toolWorldMapRemoveMarker`'s contract).
- `TestWorldMapUpdate_BumpsVersion` — the rename bumps `version`, so the GUI's next If-Match rename 412s.
- `TestWorldMapUpdateRegion_PolygonValidates` — <3 points / a point outside `[0,1]` ⇒ a tool error.
- 🔴 `TestMapToolCount_IsEleven` — `registerMapTools` now registers **11** (8 + 3). **Pins the agent-parity
  surface** so a later refactor cannot silently drop one.

**Run:** `cd services/book-service && go test ./...`

**DoD evidence:** `"W8-11: book-service go test ./... ok. registerMapTools now registers 11 tools (8 + world_map_update / _update_marker / _update_region), all world_-prefixed (mcp_prefix_contract_test green). GG-2 inverse gap #4 closed IN THE SAME WAVE that created it: the human can move a pin and so can the agent. x=0.0 is stored as 0.0, not treated as absent (pointer fields — asserted)."`

**dependsOn:** W8-09

---
### W8-12 · [FE] the `world` container panel + `studioLinks` + GG-8 registration (+1)

**Why it is a PREREQUISITE, not a feature.** `features/world/**` ships `WorldsBrowser`, `LivingWorldTree`,
`WorldRollupGraph`, `WorldTimelineSection`, `WorldLorePanel`, `AddBookToWorldModal`, `useWorlds`/`useWorld`/
`useBookWorldLink`, and `worldsApi` — routed at `/worlds` and `/worlds/:worldId` (`App.tsx:190-191`).
**NONE of it is a dock panel**, and `studioLinks.ts` has **no `/worlds` mapping** (`PATH_PANELS`, `:45-66`),
so `resolveStudioLink('/worlds/…')` falls through to `{ kind: 'external' }` (`:113`). **Today
`KgOverviewPanel`'s own "World" backlink (`:44`) POPS A NEW BROWSER TAB OUT OF THE STUDIO.** Without a
container, every path into a map is a route hop = **DOCK-7**.

**Panel id: `world`. Category: `storyBible`. Palette-visible. `guideBodyKey` REQUIRED.**

> 🔴 **Do NOT invent a `world` category.** `CATEGORY_ORDER` (`useStudioCommands.ts:20-22`) lists **9**;
> `StudioPanelCategory` (`catalog.ts:81-91`) defines **10**. The missing one is `quality` — that is **X-2**,
> and it is **still open**. An **unlisted** category sorts **FIRST** via `indexOf → -1`. Adding a `world`
> category would sort the new group **above `editor`**. **`storyBible` IS in `CATEGORY_ORDER`. Use it.**

**It resolves its own scope ⇒ it is openable by a BARE ID** — this is spec 38's answer to plan 30's **X-12**.
Rather than marking it `hiddenFromPalette` because it "needs a `world_id`", make it **self-resolving**,
exactly as `kg-overview` resolves the book's KG project via `useBookKnowledgeProject`:

> **`world` = the world THIS BOOK belongs to.** The book row carries `world_id` (`useProjectBacklinks` /
> `useBookWorldLink` both rely on it). **No param needed** ⇒ it goes into the `ui_open_studio_panel` enum, the
> Command Palette, and the User Guide.

**Files**

1. **`frontend/src/features/world/api.ts`** — **EDIT.** Add the maps methods (BE-15a/b/c/d/e/f from W8-08–10):
   `listMaps(worldId)` · `getMap(mapId)` · `createMap(worldId, {name})` · `renameMap(mapId, name, ifMatchVersion)` ·
   `deleteMap(mapId)` · `uploadMapImage(mapId, file)` (multipart — **`booksApi.uploadChapterMedia` already
   proves multipart through the gateway; copy its shape**). Marker/region methods land in W8-13.

2. **`frontend/src/features/world/hooks/useWorldMaps.ts`** — **NEW** (≤80 lines). `useQuery`
   `['world-maps', worldId]` → the rail. Plus the create/rename/delete mutations, each invalidating
   `['world-maps', worldId]`.

3. **`frontend/src/features/world/components/WorldContainerView.tsx`** — **NEW** (≤100 lines). **The launcher
   content** (DOCK-8 — a launcher hosts no capability's content):
   - the world identity card (name, book count, created);
   - **member books** (the current one marked) — clicking another book's row calls
     `onOpenBook(bookId)` (a prop) ⇒ the panel passes
     `followStudioLink('/books/{id}/studio', host, {bookId: host.bookId})`. **A different book = a different
     studio = correctly EXTERNAL.**
   - **Maps** — the world's maps (`useWorldMaps`) with a thumbnail, name, and **marker/region counts** (the
     `COUNT(DISTINCT)` fields from BE-15b). A row calls `onOpenMap(mapId)`; a `+ New map` button opens a
     `FormDialog`.
   - an **"Open the full world workspace"** escape hatch ⇒ `onOpenWorldPage()` (a prop) ⇒
     `followStudioLink('/worlds/{id}')` → **a new tab**. The timeline / rollup-graph / lore sections are **out
     of scope** and stay on the classic page.
   - 🔴 **It must be `followStudioLink(...)`, NEVER a `<Link>`.** `dockablePanelHygiene.test.ts` recursively
     scans `panels/**` and **reds on `useNavigate(` / `useParams<|(` / `<Link`** (DOCK-7). The "Open the full
     world workspace" affordance is **exactly** the shape a builder writes as `<Link to="/worlds/{id}">`.
     *(This component lives in `features/world/`, which the test does not scan — but the rule still applies,
     and the **panel** wrapper is scanned. Do not import react-router anywhere in this tree.)*
   - 🔴 **Five dialog surfaces across the two panels** (the world picker, the *Create a world* form, `+ New
     map`, the marker/region delete confirms, the image dropzone). **ALL of them must go through
     `@/components/shared` (`FormDialog` / `ConfirmDialog`) or Radix directly** — `dockablePanelHygiene`'s
     DOCK-9 check exempts **those two imports and nothing else**, and its regex is **token-based**
     (`\bfixed\b` + `\binset-0\b`, not adjacent) — so `"inset-0 fixed …"` in either order reds.

3b. 🔴 **`frontend/src/features/world/hooks/useBookWorld.ts`** — **NEW** (`Q-38-WORLD-PANEL-SELF-RESOLVING` +
   `Q-38-BARE-OPEN-NOT-ALWAYS-REAL`). Mirror `useBookKnowledgeProject.ts:20` **1:1**:
   `useBookWorld(bookId) → { worldId, isLoading }` — **one** `booksApi.getBook` query,
   `worldId = book?.world_id ?? null`.
   🔴 **Do NOT reuse or rename `useBookWorldLink`** — that is the link/unlink **MUTATION** hook. Different
   thing, same-sounding name.
   🔴 **It MUST inspect the HTTP STATUS, not `isError`** — a **404 (foreign/missing world)** and a **500/503
   (the world service is down)** are **different states** and the panel renders **different cards** for them.
   `isError` collapses both into one, and the 5xx card is the one with the **Retry** button. Return a
   **discriminated union**, and 🔴 **put it in ONE shared states module imported by BOTH `WorldPanel` and
   `WorldMapPanel`** — then **forking the empty states is physically impossible.**

4. **`frontend/src/features/studio/panels/WorldPanel.tsx`** — **NEW** (≤80 lines — a thin wrapper, exactly
   like `KgOverviewPanel.tsx`). Root `data-testid="studio-world-panel"`.
   🔴 **`useStudioPanel('world', props.api, { mcpToolPrefixes: ['world_'] })` MUST be its FIRST hook**
   (`Q-38-REGISTRATION-CHECKLIST` **amendment A** — the spec names this call only for `world-map`, but
   **EVERY** dock panel does it: `GlossaryPanel.tsx:26`, `KgOverviewPanel.tsx:16`). **Omit it and the dock tab
   renders the raw id `"world"` and the panel never registers with the StudioHost agent rack — a SILENT
   HALF-REGISTRATION that no listed test catches.**
   Resolves the world via **`useBookWorld(host.bookId)`** (3b) → `worldId` → `useWorld(worldId)`.

   **EVERY state, rendered — a blank panel behind a `shown:true` is the silent-success class this whole plan
   exists to kill:**

   | State | What it renders | testid |
   |---|---|---|
   | loading | `<Skeleton>` | `world-loading` |
   | **book is not in a world** | an empty state with a **`Link this book to a world`** control (a world picker over `useWorlds` + `useBookWorldLink.link`) **and** a `Create a world` action. **NOT a route hop.** | `world-no-world` |
   | 🔴 **the book's world is owned by SOMEONE ELSE** | *"This book belongs to a world you don't have access to."* — **uniform, NO ORACLE** (do **not** distinguish missing from foreign). **This is a REAL state, not a hypothetical:** worlds have **NO collaborators** (`server.go:378-380`) while books **do** (E0 grants). **A collaborator with EDIT on the book gets a 404 from every world route.** Render the card; **do not loop on 404s.** ⚠ **This is NOT a bug to fix by widening the world routes** — worlds are owner-only **on purpose**. | `world-foreign` |
   | world, **no maps** | the Maps section's empty state + `+ New map` | `world-no-maps` |
   | error / 503 | an error card with **Retry** | `world-error` |

5. **`frontend/src/features/world/components/LinkBookToWorldEmptyState.tsx`** — **NEW** (≤80 lines). 🔴
   **ONE component — `world-map` REUSES it in W8-13. Do NOT fork it.**

#### `studioLinks.ts` — **it is NOT one line. It is THREE files, and all three are mandatory.**

The rule we want: `/worlds/{worldId}` → `openPanel('world')` **only when `worldId` is THIS book's world**;
any other id stays `external`. 🔴 **That is not implementable against today's signature.** `resolveStudioLink`
is a **pure, synchronous** function (no React, no fetch — by design, `studioLinks.ts:1-11`) and its
`StudioLinkContext` carries **only `{ bookId, titleFor? }`** (`:19-24`). **It has no way to LEARN the book's
world.** So:

6. **`frontend/src/features/studio/host/studioLinks.ts`** — **EDIT.**
   - **(a)** add `worldId?: string` to **`StudioLinkContext`**;
   - **(b)** add `const WORLD_RE = /^\/worlds\/([^/]+)(?:\/|$)/;` and resolve to `openPanel('world')` **ONLY**
     when `ctx.worldId && id === ctx.worldId`;
   - **(c)** 🔴 **when `ctx.worldId` is ABSENT ⇒ fall through to `external`** — i.e. **today's behaviour
     exactly**, so no caller that doesn't know the world id regresses. **Degrade-safe, never a silent no-op.**

   ⚠ **Do NOT "mirror the `/knowledge/projects/:id` rule" — THERE ISN'T ONE.** `studioLinks.ts:51-57` is a
   **comment explaining why those routes are deliberately NOT mapped** (an arbitrary `:id` from a link may not
   be this book's project). It is the **reasoning** to copy, not a rule.

7. **`frontend/src/features/studio/panels/KgOverviewPanel.tsx:47-48`** — **EDIT. MANDATORY, NOT OPTIONAL.**
   *(The draft said `:44`; the actual line is **47-48** — `Q-38-REGISTRATION-CHECKLIST` amendment B.)*
   `onOpenWorld` currently calls `followStudioLink('/worlds/'+worldId, host, { bookId: host.bookId })` and
   **THROWS THE WORLD ID AWAY.** Pass `{ bookId: host.bookId, worldId }` — the id it is about to navigate to
   **IS** the book's world (it came from `useProjectBacklinks` → `OverviewSection.tsx:140`, which reads it off
   the book row).
   🔴 **WITHOUT THIS ONE LINE, step 6's rule is DEAD CODE and the pop-a-tab papercut it claims to fix is still
   there.**

7b. 🔴 **`frontend/src/features/studio/panels/BookSettingsPanel.tsx:52`** — **EDIT. THE SPEC AND THE DRAFT
   BOTH MISSED THIS ONE** (`Q-38-STUDIOLINKS-NOT-ONE-LINE` §3). It is the **identical** throw-away and it is
   the ***more likely*** path a user takes to the world backlink:
   `followStudioLink(\`/worlds/${worldId}\`, host, { bookId: host.bookId, worldId })`. The id arrives from
   `SettingsTab.tsx:360` = `book.world_id` — **safe by the same argument.**
   **Leaving this unfixed ships a studio where the SAME world link opens in-panel from `kg-overview` but pops
   a browser tab from `book-settings`** — a *worse* papercut than today's consistent-but-wrong behaviour.
   **⇒ `studioLinks` is FOUR files, not three.**

8. **`frontend/src/features/studio/host/__tests__/studioLinks.test.ts`** — **EDIT.** Four cases:
   - a **matching** world id ⇒ `kind: 'studio'`, effect opens `world`;
   - a **different** world id ⇒ `kind: 'external'`;
   - 🔴 **`worldId` ABSENT from ctx ⇒ `kind: 'external'`** — **the degrade path a builder WILL forget.**
   - bare `/worlds` (no id) ⇒ `external` (`WORLD_RE` requires a segment; **pin it**).

8b. 🔴 **TWO EXISTING TESTS GO RED — FIX THEM IN THE SAME COMMIT** or the wave's suite fails.
   `panels/__tests__/KgOverviewPanel.test.tsx:133` **and** `panels/__tests__/BookSettingsPanel.test.tsx:123`
   both assert `expect(followStudioLink).toHaveBeenCalledWith('/worlds/w1', hostRef, { bookId: 'b1' })`.
   Change **both** to `{ bookId: 'b1', worldId: 'w1' }`. 🔴 **Do NOT weaken them to `expect.anything()`** —
   they are the guard that proves the id is threaded.

8c. ⚠ **ORDERING.** The `world` panel id must **already be registered in the catalog** when step 6 lands, or
   `openPanel('world')` is a **silent no-op** (the exact `mcp-tool-io` OUT-* class this repo shipped once with
   `panel_id`). **Build the panel FIRST inside this slice, then flip `studioLinks`.** *(If the panel ever
   slips, 6–8 still ship green because the degrade path is `external` — but do **not** merge 7/7b ahead of
   the panel.)*
   🟢 **The `world` panel is opened with NO params** — it is **self-resolving** (`world` = the world THIS book
   belongs to, exactly as `kg-overview` self-resolves its project). Passing `{ worldId }` as a param would be
   a **second source of truth for the same fact.**

#### GG-8 registration — `world` (this is **+1**, `world-map` is the other +1 in W8-13)

| # | File | Edit |
|---|---|---|
| 2 | `frontend/src/features/studio/panels/catalog.ts` | ONE `STUDIO_PANELS` row: `{ id:'world', component: WorldPanel, titleKey:'panels.world.title', descKey:'panels.world.desc', category:'storyBible', guideBodyKey:'panels.world.guideBody' }`. **`category` and `guideBodyKey` are BOTH mandatory.** |
| 3 | `frontend/src/i18n/locales/en/studio.json` | `panels.world.{title,desc,guideBody}` |
| 4 | `frontend/src/i18n/locales/{ar,bn,de,es,fr,hi,id,ja,ko,ms,pt-BR,ru,th,tr,vi,zh-CN,zh-TW}/studio.json` | the same 3 keys × **17** locales — **`python scripts/i18n_translate.py`**, **NEVER hand-write** |
| 5 | `services/chat-service/app/services/frontend_tools.py` | **TWO edits** in `UI_OPEN_STUDIO_PANEL_TOOL`: (a) append `"world"` to the `panel_id` **enum** (`:402`); (b) append a clause to the tool **description** prose (`:403+`) — **that gloss is the model's ONLY hint.** Suggested: *"'world' = the world this book belongs to (its member books and its maps)."* |
| 6 | `contracts/frontend-tools.contract.json` | 🔴 **NEVER hand-edit — REGENERATE:** `cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py` — and **commit the regenerated JSON IN THE SAME COMMIT** as steps 2 + 5. |
| 9 | tours | **SKIP** — not a role-tour step. |

**Tests**

- `frontend/src/features/studio/panels/__tests__/WorldPanel.test.tsx` (NEW) — **one case per state row above**,
  including 🔴 `a foreign world renders the no-access card and does NOT retry` and
  🔴 `a book with no world renders LinkBookToWorldEmptyState`.
- `studioLinks.test.ts` — the three cases above.
- **The machine guards (all must be green):**
  ```bash
  cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
  cd frontend && npx vitest run \
    src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
    src/features/studio/panels/__tests__/dockablePanelHygiene.test.ts \
    src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
    src/features/studio/palette/__tests__/useStudioCommands.test.ts \
    src/features/studio/host/__tests__/studioLinks.test.ts \
    src/features/chat/nav/__tests__/frontendToolContract.test.ts
  ```

🔴 **ASSERT THE DELTA + THE THREE-WAY EQUALITY — NEVER A LITERAL.** After this slice all three counts are
`N_BEFORE + 1` (= **70**, if waves 1–6 landed). **A DoD pinned to a literal sends the next builder hunting a
phantom regression** — six of the eight specs got this wrong by each computing from 57.

**DoD evidence:** `"W8-12: py enum == contract enum == openable, all three at N_BEFORE+1 (70). vitest <N> passed incl. panelCatalogContract + dockablePanelHygiene + studioLinks (3 cases: matching world ⇒ studio, different world ⇒ external, worldId ABSENT ⇒ external). KgOverviewPanel now passes worldId into followStudioLink — the World backlink opens the dock tab instead of popping a browser tab. WorldPanel renders all 5 states incl. the foreign-world no-access card."`

**dependsOn:** W8-08

---
### W8-13 · [FE] the `world-map` panel + GG-8 registration (+1) + `worldEffects` Lane-B

**Panel id: `world-map`. Category: `storyBible`. Palette-visible.** Params **OPTIONAL** — `{ mapId? }`. With
no param it resolves the book's world and selects the **most recent** map.

#### 🔴 "It always lands somewhere real" is FALSE, and the DoD depends on it.

The agent can call `ui_open_studio_panel {panel_id:"world-map"}` **BARE**. **Three resolutions produce
nothing to select, and EACH MUST BE A RENDERED STATE, NOT A BLANK PANEL.** *(A blank panel behind a
`shown:true` is the silent-success class this entire plan exists to kill.)*

| Bare-open resolution | What `world-map` renders | testid |
|---|---|---|
| the book is **in no world** | the **SAME** *"Link this book to a world"* empty state as the `world` panel — 🔴 **REUSE `LinkBookToWorldEmptyState` (W8-12). DO NOT FORK IT.** Not an empty rail. | `world-map-no-world` |
| the world is **foreign** (owner-only) | the uniform *"This book belongs to a world you don't have access to."* card | `world-map-foreign` |
| the world has **no maps** | the Maps empty state + a **focused** primary `+ New map` CTA | `world-map-no-maps` |
| `mapId` given but **404** (deleted / not yours) | 🔴 **drop the param, fall back to the rail, and say *"that map is gone"*.** **NEVER silently show a DIFFERENT map as if it were the requested one.** | `world-map-gone` |

#### Layout (the draft `screen-world-map.html` IS the acceptance criterion)

```
┌ WORLD MAP ─────────────────────────────────────────────────────────────┐
│ [maps rail 200px] │ [canvas — flex:1]              │ [inspector 300px] │
│  Bản đồ Bắc Vực   │   base image (image_url)       │  MARKER           │
│  山海圖  ● 12 ▲3  │   + pins  (x,y ∈ [0,1])        │  label  [____]    │
│  + New map        │   + regions (svg polygons)     │  type   [city ▾]  │
│                   │   zoom / pan / fit             │  entity [Ironhold]│
│                   │                                │  x .412  y .688   │
│                   │                                │  edited 4m ago    │
│                   │                                │  [Delete]         │
└────────────────────────────────────────────────────────────────────────┘
```

**Reads:** `GET /v1/worlds/{world_id}/maps` (the rail — with the `marker_count`/`region_count` badges) ·
`GET /v1/worlds/maps/{map_id}` (the canvas — map + markers + regions in ONE round-trip).
**Writes:** create map · rename map · delete map · upload/replace the base image · add/move/edit/delete a
marker · add/reshape/edit/delete a region.

🔴 **COORDS ARE RELATIVE `[0,1]`.** The canvas converts on render; **every write clamps**. **NEVER store
pixels** — the base image can be replaced at a different resolution, and *that is exactly why* the schema is
relative (`migrate.go:418`).

🔴 **THE ENTITY LINK IS A *GLOSSARY* ENTITY ID, NOT A KNOWLEDGE ONE.** `map_markers.entity_id` /
`map_regions.entity_id` are **soft cross-service UUIDs into glossary-service** (`migrate.go:416, 429` —
*"soft cross-service ref → glossary location entity"*). ⚠ **Wiring the KNOWLEDGE entity picker here would
create a dangling id that NOTHING validates — the FK is soft BY DESIGN.**

> 🟢 **OQ-2 IS RESOLVED — the world-bible model holds. Verified against code, do not re-investigate.**
> The bible is a **real `books` row** (`is_bible=true`, `world_id` set), **auto-provisioned with the world in
> one tx** (`worlds.go:51-126`) — so glossary entities are per-book **and** world-level lore at the same time:
> **they live in the bible BOOK.** `World.bible_book_id` is FE-reachable (`features/world/types.ts:18`; and
> `GET /v1/worlds/{id}` already returns it — `worlds.go:188,202`). **No new route.**
>
> **The picker (`Q-38-OQ2-MARKER-ENTITY-PICKER-SOURCE` + `Q-38-MARKER-ENTITY-IS-GLOSSARY-NOT-KG`):**
> 1. **DEFAULT LIST = the world bible's `location` entities.** Reuse the **EXISTING** fn —
>    `glossaryApi.listEntities(bibleBookId, { kindCodes: ['location'], status: 'active', searchQuery: q, limit: 50 }, token)`
>    (`features/glossary/api.ts:85-96`). **Do not write a new api fn.** Do **not** use the internal
>    `/internal/worlds/{id}/bible` (internal-token only).
> 2. 🔴 **SECOND TIER = a "Source" `<select>` in the picker header**, defaulting to **World bible**, whose
>    other options are the world's **member books** from the existing `worldsApi.listWorldBooks(token, worldId)`
>    (`GET /v1/worlds/{world_id}/books` — bible books **already excluded by the BE**, `worlds.go:477`).
>    Selecting one re-runs the **same** `listEntities` call with that `book_id`. 🔴 **LAZY, ONE BOOK AT A
>    TIME — do NOT eagerly fan out over all member books** (there is no cross-book entity route and building
>    one is out of scope). **Bible-first, member books opt-in — never a silent single-book limitation.**
> 3. 🔴 **FILTER BY `kind_codes`, NEVER BY KIND ID.** Kinds are **per-book rows** (`book_kinds`; `createEntity`
>    404s *"kind not found in this book's ontology"* — `entity_handler.go:377`). **A kind UUID from the bible
>    book is MEANINGLESS in a member book.** Never cache or pass a `kind_id` across books.
> 4. **NULL-SAFE BY CONTRACT.** `map_markers.entity_id` / `map_regions.entity_id` are **nullable soft
>    cross-service UUIDs with NO FK** (`migrate.go:416,430`). Offer **"No entity (label only)"** and allow
>    clearing (PATCH `entity_id: null`). On read, a stored `entity_id` that no longer resolves renders the
>    marker's **own `label`** + a muted *"linked entity not found"* hint — **never a blank marker, never an
>    error toast.**
> 5. **EMPTY STATE, NOT ERROR.** A fresh world's bible may have **zero** location entities ⇒ *"No locations in
>    this world's bible yet — add one in the World panel"*, **with the source selector still usable.** A
>    404/empty from glossary is an **empty state**, not a failure.
> 6. 🔴 **NEVER `knowledgeApi`.** The link is a **GLOSSARY** entity id (`migrate.go:416` — *"soft
>    cross-service ref → glossary location entity"*). Wiring the **knowledge** entity picker here creates a
>    **dangling id that NOTHING validates.** *(⚠ `Q-38-OQ9` contains one stray parenthetical suggesting
>    `knowledgeApi.listEntities`. It is an **outlier**: three decisions, the plan, and the **DDL comment
>    itself** say GLOSSARY. **Glossary wins. Recorded so it is not re-opened.**)*
>
> 📌 **A LIVE BUG THIS EXPOSES — not blocking the picker, but file it and fix it in W8-12 if cheap:**
> `frontend/src/features/world/hooks/useWorldLore.ts` feeds `createBibleEntity` a **`kind_id` taken from the
> GLOBAL `/v1/glossary/kinds` list** (a *system*-kind id), while glossary's `createEntity` validates that id
> against **THIS book's `book_kinds`** (`entity_handler.go:363-377`). **That world-lore WRITE path is very
> likely broken today.** Resolve kinds via the bible book's **own** ontology instead. (Rule 3, applied.)

**Files**

1. **`frontend/src/features/world/api.ts`** — **EDIT.** The marker/region methods (BE-15g..l):
   `createMarker(mapId, body)` · `patchMarker(mapId, markerId, partial)` · `deleteMarker(mapId, markerId)` ·
   `createRegion` · `patchRegion` · `deleteRegion`.
   🔴 **`patchMarker`'s payload must be able to send an EXPLICIT `null`** to CLEAR `entity_id`/`marker_type`
   (BE-15h). `JSON.stringify({entity_id: undefined})` **drops the key** (= "unchanged"); `{entity_id: null}`
   sends it (= "clear"). **They are different requests. Do not normalise `null` → `undefined` anywhere in
   this path.**

2. **`frontend/src/features/world/hooks/useWorldMapDetail.ts`** — **NEW** (≤120 lines). The **controller**
   (React MVC — hooks own logic, components render). It owns:
   - `useQuery(['world-map-detail', mapId])` → `{map, markers, regions}`;
   - the marker/region mutations, **each invalidating `['world-map-detail', mapId]` AND
     `['world-maps', worldId]`** (the rail's counts change);
   - 🔴 **PER-OBJECT WRITE SERIALIZATION.** Positional writes are **last-write-wins by design** (no OCC — see
     W8-09). The FE **must chain them per marker id**: keep a `Map<markerId, Promise<unknown>>` and
     `queue.set(id, (queue.get(id) ?? Promise.resolve()).then(() => patchMarker(...)))`. **Two rapid drags of
     the same pin must not race.** *(This repo's `instant-commit-control-over-occ-entity-needs-write-serialization`
     lesson — the exact failure it describes.)*
   - 🔴 **THE DEBOUNCED SAVE MUST CAPTURE *WHICH* MARKER IT IS SAVING.** `debounced-write-must-bind-its-target-entity`:
     a debounce that closes over "the selected marker" saves the **wrong** pin when the user drags A, then
     selects B within the debounce window. **Bind the id at schedule time.**
   - 🔴 **A PATCH against a DELETED marker returns 404** ⇒ **drop the optimistic pin and REFETCH. It must NOT
     re-create it.**

3. **`frontend/src/features/world/components/WorldMapCanvas.tsx`** — **NEW** (≤100 lines — split if it grows).
   - the base image (`image_url`); pins as **absolutely-positioned divs**; regions as **ONE `<svg>` with one
     `<path>` per region**.
   - **Drag a pin** → an **optimistic** move + a **serialized, debounced** PATCH.
   - **Draw a region** → click-to-add-vertex, double-click/Enter to close (**≥3 points**), **Esc to cancel**.
     Reshape = drag a vertex → PATCH `polygon` **whole**.
   - **Click empty canvas with the pin tool armed** → add a marker at that point (POST), then **focus its
     label field**.
   - zoom / pan / fit.
   - **SCALE — 🔴 the "above ~500 markers, cull to the viewport" clause is STRUCK** (`Q-38-SCALE-NO-VIRTUALIZATION`).
     It is **a second, unbuilt, untested render path with ZERO profiling evidence** (CLAUDE.md defer-gate #4:
     perf items get fixed **when profiling shows pain**) — and it culls only **RENDER** while every marker
     still lives in state, so it buys almost nothing. **Render ALL markers, unconditionally:** one
     `React.memo`'d `<MapMarker>` each, `position:absolute; left:${x*100}%; top:${y*100}%`. **No culling, no
     virtualization, no `slice()`.** Regions are **one** `<svg>`. **The no-virtualization decision stands;
     the escape clause does not.**
   - ⚠ **Never conditionally unmount** the canvas (CLAUDE.md) — use CSS `hidden` when switching maps, or key
     it by `mapId` deliberately. And **no `useEffect` for the drag** — the drag handlers are event handlers.

4. **`frontend/src/features/world/components/MapInspector.tsx`** — **NEW** (≤100 lines).
   - label · **type** · **entity** · `x` / `y` (read-only display, 3dp) · **`edited 4m ago`** · Delete.
   - 🔴 **RENDER `updated_at`.** It is **what makes a drag-PATCH visible as having LANDED** rather than merely
     repainted — and a stored-but-unread column is the bug class CLAUDE.md bans (§4).
   - ⚠ **WebP base images store NULL pixel dims** (no stdlib decoder — `maps_image.go:16-19`). Harmless
     (coords are relative) — **but the inspector must NOT render `image_w × image_h` as "0 × 0".** Render
     *"dimensions unavailable"* or nothing.
   - **`marker_type`** — 🔴 **NOT a `<select>` + a "free text…" escape option. THE DRAFT'S CONTROL IS WRONG
     AND `D-WORLD-MARKER-TYPE-VOCAB` IS RETIRED, NOT DEFERRED** (`Q-38-OQ7-MARKER-TYPE-VOCAB` — *"it is
     answered, not deferred. No BE work."*).
     A select-with-escape needs an `isFreeText` mode toggle **and a second input**, and **shadcn `Select`
     cannot do free text at all.** The repo already has a **TESTED native precedent**: `<input list>` +
     `<datalist>` — `features/enrichment/components/compose/ComposeTarget.tsx:74-83` (tests at
     `ComposeTarget.test.tsx:60,87`). **Mirror it exactly. One control = suggestions + free text, zero extra
     state.**
     1. **BE: change NOTHING.** `marker_type` stays nullable free `TEXT` (`migrate.go:421`). **No CHECK
        constraint, no `marker_kinds` table, no MCP enum.**
     2. **THE VOCABULARY — ONE HOME, ONE NAME.** New file
        `frontend/src/features/studio/panels/world/markerTypes.ts`:
        ```ts
        export const MARKER_TYPE_SUGGESTIONS =
          ['city','town','landmark','ruin','stronghold','temple','battle','region'] as const;
        ```
        🔴 **`city` and `landmark` MUST lead and MUST be spelled EXACTLY as in `mcp_maps.go:136`** — otherwise
        **the agent writes `city`, the human picks `City`, and the data forks into two vocabularies.**
        **No other consumer re-declares this list.**
     3. **NORMALIZE ON WRITE:** `trim().toLowerCase()`; **empty string ⇒ send an explicit `null`** (BE-15h:
        *null = clear*), matching `nullableString()` at `mcp_maps.go:169`.
     4. 🔴 **UNION WITH WHAT IS ALREADY ON THE MAP (~3 lines — this is what makes free text actually
        usable):** the datalist options = `MARKER_TYPE_SUGGESTIONS` **∪** the distinct non-null
        `marker_type`s of the markers in the loaded BE-15c payload. **A user's own custom type then reappears
        next session without any BE vocabulary existing.**
     5. **RENDER UNKNOWNS SAFELY:** the pin icon/colour map is keyed on the 8 known values **with a DEFAULT
        fallback** for unknown-or-null. **Never blank, never throw.**
     🟢 **Do NOT add it to `CLOSED_SET_ARGS`** — 🔴 **and note that symbol DOES NOT EXIST in service code**
     (`Q-38-REGISTRATION-CHECKLIST` **amendment C**: `grep` hits only CLAUDE.md and docs). The closed-set rule
     is enforced by `services/chat-service/tests/test_frontend_tools_contract.py` reading the schema.
     **Do not go hunting for a registry list to append to.**

5. **`frontend/src/features/world/components/GlossaryLocationPicker.tsx`** — **NEW** (≤80 lines). The OQ-2
   picker above (all six rules). **Accepts "no link"** (a `— none —` option that sends an explicit `null`).
   🔴 **AND THE "OPEN IN CODEX" ACTION — it is the ONE affordance the retired legacy place-graph had that
   nothing else replaces** (`Q-38-OQ9` §2; `WorldMap.tsx:44-48`'s `onViewCast`). When a marker/region carries
   an `entity_id`, render an **Open in codex** action that opens the **glossary** panel focused on that entity
   via **`followStudioLink(...)`** — 🔴 **NEVER a `<Link>`** (`dockablePanelHygiene` DOCK-7 **reds** on it).
   *(The target is the **glossary** panel, not `cast` — `cast` is a KNOWLEDGE-entity codex and this is a
   GLOSSARY id. Two id spaces. See rule 6 above.)*
   **Tests:** a vitest asserting the picker PATCHes `entity_id`, that a bound marker renders the
   open-in-codex action, and a **Go** handler test that `entity_id` round-trips through BE-15h
   (**absent = unchanged · `null` = clear**).

6. **`frontend/src/features/world/components/MapImageDropzone.tsx`** — **NEW** (≤80 lines).
   **States, each rendered:** no image (a dropzone **over the empty canvas** — 🔴 **markers can still exist**,
   because the row is authored **independently** of the blob) · uploading (progress) · **413** too large ·
   **415** unsupported type (png/jpg/gif/webp only) · **503** no MinIO · replace (the old object is swept
   **server-side**).
   🔴 **Radix/`FormDialog` only — DOCK-9.**

7. **`frontend/src/features/studio/panels/WorldMapPanel.tsx`** — **NEW** (≤100 lines — a thin wrapper). Root
   `data-testid="studio-world-map-panel"`.
   `useStudioPanel('world-map', props.api, { mcpToolPrefixes: ['world_'] })`.
   Resolves: `params.mapId` ?? the most recent map of the book's world. Renders the **four degraded states**
   from the table above, then the rail + canvas + inspector.

8. **`frontend/src/features/studio/agent/handlers/worldEffects.ts`** — **NEW.** 🔴 **This file is the ONE HOME
   for the `world_*` domain (plan 30 §8.0b — `matchEffectHandlers` returns EVERY match and `runEffectHandlers`
   AWAITS ALL of them, so two files registering overlapping patterns DOUBLE-FIRE).**
   🟢 **THE REGEX IS RIGHT** — the register traced all **12** real tool names through it
   (`Q-38-WORLDEFFECTS-LANE-B`). 🔴 **THE DRAFT'S FOUR QUERY KEYS ARE WRONG: THREE OF THEM DO NOT EXIST.**
   `['world-maps']` / `['world-map-detail']` **exist NOWHERE today** (this slice **creates** them) and
   `['world-books']` is a **PHANTOM** — the real key is `['living-world','books',worldId]`. Invalidating dead
   keys = **the map panel silently never refreshes after an agent write**: a false-green (unit tests pass,
   live loop broken).
   ```ts
   // Wave 8 — Lane B for book-service's world/map tools. A RegExp, not a string:
   // registerEffectHandler's string branch is `tool === p || tool.startsWith(p)` — an alternation
   // written as a string matches NOTHING and ships a SILENT NO-OP handler no unit test could catch.
   export const WORLD_WRITE_PATTERN =
     /^world_(map_)?(create|delete|update|rename|add_marker|remove_marker|update_marker|add_region|remove_region|update_region|move_book)/;

   // Verified against the 12 REAL tool names (mcp_worlds.go:295-316 + mcp_maps.go:466-510):
   // it matches all 8 writes and NONE of the 4 reads (world_list/world_get/world_map_get/world_map_list).
   // It over-enumerates verbs that do not exist yet (update/rename/update_marker/update_region/
   // world_delete) — harmless future-proofing; W8-11 lands three of them. Leave them.

   export function worldEffect(ctx: EffectContext): void {
     const { queryClient } = ctx;
     // TanStack matches by key PREFIX, so the short prefixes below cover their sub-keys.
     queryClient.invalidateQueries({ queryKey: ['worlds'] });                  // useWorlds.ts:14
     queryClient.invalidateQueries({ queryKey: ['world'] });                   // ['world', worldId] — useWorld.ts:14
     queryClient.invalidateQueries({ queryKey: ['living-world'] });            // ['living-world','books',id] :55 + ['…','works',id] :68 — THIS is the real "world-books"
     queryClient.invalidateQueries({ queryKey: ['world-subgraph'] });          // useWorldSubgraph.ts:29
     queryClient.invalidateQueries({ queryKey: ['world-timeline'] });          // useWorldTimeline.ts:17
     queryClient.invalidateQueries({ queryKey: ['project-backlink-world'] });  // useProjectBacklinks.ts:24 — stale after world_move_book
     queryClient.invalidateQueries({ queryKey: ['world-maps'] });              // 🔴 NEW — created by THIS slice
     queryClient.invalidateQueries({ queryKey: ['world-map-detail'] });        // 🔴 NEW — created by THIS slice
   }
   ```
   **Why the first six:** `useAddBookToWorld.ts:25-26` is the **REST PRODUCER** of the same write and it
   invalidates `['living-world','books',worldId]` + `['world-subgraph']`. 🔴 **A Lane-B handler must MIRROR
   THE PRODUCER'S OWN INVALIDATE SET — not invent one** (`reconcile-by-truth-mirror-producer-predicate`).
   🔴 **HARD CONSTRAINT:** the new hooks (`useWorldMaps.ts` / `useWorldMapDetail.ts`) **MUST use exactly the
   literals `['world-maps']` and `['world-map-detail', mapId]`.** If they drift, this handler invalidates dead
   keys and **the panel never refreshes after an agent write.**
   🔴 **DO NOT invalidate `['composition','worldmap',*]`** (`useWorldMap.ts:70,81`) — **that is composition's
   PLACES map, a different subsystem.** No `world_*` tool writes it.
   🔴 **The READS must NOT match** — `world_map_get` / `world_map_list` / `world_get` / `world_list`. **A
   chatty read loop would thrash the cache.** The pattern excludes them by construction. **Verify it with a
   table test — that test IS the point of the ticket.**
   Idempotent `registerWorldEffectHandlers()` + `_resetWorldEffectHandlers()`, copying
   `knowledgeEffects.ts:19,47-58` exactly.

9. **`frontend/src/features/studio/agent/useStudioEffectReconciler.ts`** — **EDIT.** Import and call
   `registerWorldEffectHandlers()` in the `useEffect`, **alongside the other four**
   (`registerDefaultEffectHandlers` / `registerGlossaryEffectHandlers` / `registerKnowledgeEffectHandlers` /
   `registerTranslationEffectHandlers` — `:18-21`).

#### GG-8 registration — `world-map` (the second **+1**)

Same 6 steps as W8-12, with:
- **catalog.ts:** `{ id:'world-map', component: WorldMapPanel, titleKey:'panels.world-map.title', descKey:'panels.world-map.desc', category:'storyBible', guideBodyKey:'panels.world-map.guideBody' }`
- **`frontend_tools.py`:** append `"world-map"` to the enum **and** a description clause: *"'world-map' = a
  drawn world map — pins and regions on a base image."*
- **regenerate `contracts/frontend-tools.contract.json`** and commit it **in the same commit**.
- 17 locales via `python scripts/i18n_translate.py`.

**Tests**

- `frontend/src/features/studio/panels/__tests__/WorldMapPanel.test.tsx` (NEW) — 🔴 **one case per degraded
  state**, and the fourth is the one nobody writes:
  - `bare open on a book with NO world renders LinkBookToWorldEmptyState (the SAME component as WorldPanel)`
  - `a foreign world renders the uniform no-access card`
  - `a world with no maps renders the + New map CTA`
  - 🔴 `a mapId that 404s falls back to the rail and says "that map is gone" — it does NOT show a different map`
- `frontend/src/features/world/hooks/__tests__/useWorldMapDetail.test.ts` (NEW):
  - 🔴 `two rapid drags of the SAME marker are SERIALIZED (the second PATCH starts after the first resolves)`
  - 🔴 `a debounced save binds the marker it was scheduled for` — drag A, select B inside the debounce window;
    assert the PATCH went to **A**, not B.
  - 🔴 `a 404 on PATCH drops the optimistic pin and refetches — it does NOT re-create the marker`
- `frontend/src/features/studio/agent/handlers/__tests__/worldEffects.test.ts` (NEW):
  - `world_map_add_marker matches` · `world_map_update_marker matches` · `world_move_book matches`
  - 🔴 `world_map_get does NOT match` · 🔴 `world_map_list does NOT match` · `world_list does NOT match`
  - 🔴 `the pattern is a RegExp, not a string` — `expect(WORLD_WRITE_PATTERN).toBeInstanceOf(RegExp)`
- The **six machine guards** from W8-12 (all green).

🔴 **ASSERT THE DELTA:** all three counts are now `N_BEFORE + 2` (**W8-16/17/18 take it to +5**). **Never a
literal.**

**DoD evidence:** `"W8-13: py enum == contract enum == openable, all three at N_BEFORE+2. vitest <N> passed. WorldMapPanel renders all FOUR bare-open degraded states (no-world reuses LinkBookToWorldEmptyState — not a fork; a 404 mapId falls back to the rail and does NOT show a different map). useWorldMapDetail serializes per-marker writes and binds the debounce to its target marker (both asserted). marker_type is an <input list>+<datalist> (NOT a select — shadcn Select cannot do free text): a custom value round-trips lowercased, clearing sends explicit null, an unknown type renders the DEFAULT pin — D-WORLD-MARKER-TYPE-VOCAB is RETIRED. The entity picker reads GLOSSARY (bible book first, member books via the Source select), never knowledgeApi. worldEffects invalidates the EIGHT REAL keys (mirroring useAddBookToWorld, the REST producer — the draft's ['world-books'] was a PHANTOM) and matches NO reads (world_map_get/_list/world_get/world_list asserted); WORLD_WRITE_PATTERN is a RegExp."`

**dependsOn:** W8-09, W8-10, W8-12

---
### W8-14 · [TEST] `studio-world-map.spec.ts` — the 8b LIVE BROWSER smoke

🔴 **The DoD, not a formality.**

**Files**

- **`frontend/tests/e2e/specs/studio-world-map.spec.ts`** — **NEW.** Harness already exists:
  `helpers/api.ts` → **`createWorld`**, **`moveBookIntoWorld`**, **`listWorlds`**, **`deleteWorld`**,
  `createBook`, `getAccessToken`, `trashBook` — **all present**; do not write new ones.
  `pages/StudioPage.ts` → `goto(bookId)`, `openPanel(panelId, searchTerm)`.
- **BAKED frontend** (rebuild the image, or `vite dev` on `:5199` — `:5174` is nginx and a host vite
  **SHADOWS** it). Account `claude-test@loreweave.dev`.

**The cases:**

1. **`open world via the Command Palette → create a map → upload a base image → place a pin`**
2. 🔴 **`DRAG THE PIN WITH `page.mouse`, RELOAD, AND ASSERT THE NEW COORDS`**
   - **`page.mouse` produces CDP-TRUSTED events. `browser_drag` / synthetic events DO NOT drive a canvas
     drag** (`playwright-cdp-mouse-drives-d3-drag`). Use `page.mouse.move → down → move → up`.
   - **The RELOAD is the whole point:** it is the **only** thing that proves the **PATCH landed** and did not
     just repaint optimistic state. **A test that asserts the pin moved without reloading proves nothing.**
3. 🔴 **`rename the map in a SECOND TAB; the first tab's rename gets a 412 with the current name`** — the only
   OCC in this design, and it is deliberate. Open two contexts; rename in B; rename in A with the stale
   version; assert A shows *"renamed on another device"* + the current name.
4. **`the agent leg, IN THE BROWSER`** — a chat turn calling `ui_open_studio_panel {panel_id:"world-map"}`
   **MOUNTS THE DOCK TAB** (plan 30 §8: *"a green unit suite does not prove the loop closed"*). Same for
   `{panel_id:"world"}`.
5. 🔴 **THE BARE-OPEN DEGRADED LEG — DO NOT SKIP IT.** Run `ui_open_studio_panel {panel_id:"world-map"}` on a
   book that is in **NO world**, and assert the panel renders the **"Link this book to a world"** state.
   **A blank panel behind a `shown:true` is a SILENT SUCCESS, and this is the ONE path the happy-path smoke
   above will NEVER touch.**

**Run:** `cd frontend && npx playwright test tests/e2e/specs/studio-world-map.spec.ts`

**DoD evidence:** `"W8-14: live smoke: studio-world-map.spec.ts 5 passed against the BAKED FE — created a map, uploaded a base image, placed a pin, DRAGGED it with page.mouse (CDP-trusted), RELOADED, and the pin is at the new coords (the PATCH landed, not a repaint); a stale rename got a 412 with the current name; a chat turn's ui_open_studio_panel {panel_id:'world-map'} mounted the dock tab; the SAME tool on a book with NO world rendered the Link-this-book-to-a-world state, not a blank panel."`

**dependsOn:** W8-11, W8-13

---

## 5.4 · 🔴 THE HOMELESS LEGACY SUB-TABS — the GG-4 retirement gate

**The problem.** Seven legacy `CompositionPanel` sub-tabs were **assigned to no wave**. The GG-4 retirement
gate would **DELETE** them. **Three are Wave 8's** (`cast` · `arc` · `flywheel` — knowledge-service surfaces,
and Wave 8 is already inside those files); **one is a reviewed won't-port** (`worldmap`); and **three belong
to Wave 6** (`compose` · `assemble` · `canonview`), which **runs BEFORE this wave** and now carries them as
`W6-M6` (`scene-compose`), `W6-M7` (`chapter-assemble`) and a `scene-inspector` section (M3).

🔴 **ORDERING — read this before you touch the parity map.** **Wave 6 runs FIRST**, so when its
`legacyParityContract.test.ts` lands, this wave's three panels **do not exist yet**. Wave 6 therefore ships
them as **`{ pending: 'Wave 8 / W8-1x' }`** rows (`D-GG4-PARITY-ROWS-PENDING`), and its
`it.fails('GG-4: zero pending rows')` is **RED by design — that is the gate holding.**
**W8-16 / W8-17 / W8-18 each FLIP their row**, and W8-18 converts the `it.fails` to an `it`. ⚠ **§11's
"handoff to Wave 6" is a WRITE-DOWN for the record, not work to schedule** — Wave 6 has already closed by
the time you read this; the fix lands **here**, in W8-16/17/18.

| Legacy sub-tab | Component | Home | Slice |
|---|---|---|---|
| **cast** | `composition/components/CastCodexPanel.tsx` | 🟢 **WAVE 8** — new panel `cast` | **W8-16** |
| **arc** | `composition/components/CharacterArcView.tsx` | 🟢 **WAVE 8** — new panel `character-arc` | **W8-17** |
| **flywheel** | `composition/components/FlywheelPanel.tsx` | 🟢 **WAVE 8** — new panel `canon-growth` | **W8-18** |
| **worldmap** | `composition/components/WorldMap.tsx` (the **place-graph**) | 🔴 **WON'T-PORT — superseded, by adjudication.** `{ retired: … }` in Wave 6's map. See the box below. | — |
| compose · assemble · canonview | `ComposeView` · `ChapterAssembleView` · `CanonAtChapterPanel` | ✅ **WAVE 6 — already carried** | `W6-M6` · `W6-M7` · `W6-M3` |

> ✅ **THE TWO FALSE MAP ROWS ARE ALREADY FIXED IN WAVE 6'S PLAN — do not "re-fix" them.** An earlier cut of
> Wave 6 mapped `flywheel → 'quality-corrections'` and `arc → 'arc-templates'`. **Both were lies that make
> the machine gate GO GREEN on a feature being deleted**, and both are now corrected at source (wave-6
> `LEGACY_SUBTAB_HOME`). They are recorded here **only** so the reasoning is not lost:
> - **`flywheel` is NOT `quality-corrections`.** `quality-corrections` is `CorrectionStatsTable`
>   (**composition** correction *rates*). `FlywheelPanel` is **knowledge-graph growth**
>   (`knowledgeApi.getFlywheel`). **Two services, two datasets. The name collides; the thing does not.**
>   *(Wave 1's own plan says so in writing, at `:2445`.)* ⇒ **`canon-growth` (W8-18).**
> - **`arc` is NOT `arc-templates`.** `arc-templates` (Wave 4) is the structure-TEMPLATE library + 拆文
>   deconstruct; `arc-inspector` (Wave 2) is the narrative arc **SPEC tree**. **Neither is a character's
>   EVENT arc over the knowledge graph.** ⇒ **`character-arc` (W8-17).**
>
> 🔴 **The live hazard is now the OPPOSITE one: a `{pending}` row tempting you to silence it.** If
> `legacyParityContract.test.ts` is red at your pre-flight, **that is Wave 6's gate working as designed.**
> **Flip the rows by BUILDING W8-16/17/18** — never by re-pointing a row at a panel that is not the thing,
> and never by demoting a `pending` to a `retired`.

> 🔴 **`worldmap` (the legacy PLACE-GRAPH) — WON'T-PORT. This is an ADJUDICATED DECISION
> (`Q-38-OQ9-LEGACY-WORLDMAP-PLACE-GRAPH-NOT-PORTED`), and it OVERRIDES the "it dies at GG-4" alarm.**
> The alarm's premise is **doubly false against code:**
> 1. **Its two capabilities are each strictly absorbed by a panel Wave 8 ITSELF ships.**
>    **(a) AUTHORING** (*add place / link places*) → `useWorldMap.ts:129,134` are **the only human callers of
>    `createEntity`/`createRelation` in the whole frontend**, and **W8-02/W8-03 move that capability into the
>    KG panels.** **(b) SPATIAL** (drag positions + backdrop) → the **NEW `world-map` panel** (W8-13) — the
>    same idea on a **better model**: world-scoped + **versioned** + **MCP-paired** (BE-15m) + real
>    `map_markers.entity_id` FKs, vs. the place-graph's **untyped `composition_work.settings.world_map` JSON
>    blob with ZERO MCP tools** (a live GG-2 *inverse* gap). Porting it would put **two panels named "world
>    map" in one dock over two different data models** — the exact *one name for one concept* violation
>    **PO-3 sealed against**.
>    **(c)** its ONE unreplaced affordance — *click a place → open it in the codex* — **IS built**, in the
>    `world-map` inspector (W8-13 file 5).
> 2. 🔴 **GG-4 DOES NOT DELETE IT ANYWAY** (`Q-38-LEGACY-ONLY-NOT-UNBUILT`): **spec 16 REVERSED "delete after
>    soak"** — its Phase 4b (M9, the user's call 2026-07-05) keeps `ChapterEditorPage` **INDEFINITELY**,
>    deprecation-bannered, **no route change.** **Nothing is lost.**
>
> **⇒ DEFER ROW `D-WORLDMAP-PLACE-GRAPH-WONTPORT`** — gate **#5 (conscious won't-fix)**, recorded in §8 so it
> **stops re-surfacing**. `WorldMap.tsx` + `useWorldMap.ts` + `PlaceNode.tsx` + the `settings.world_map` blob
> die **with `ChapterEditorPage`, whenever that happens**. 🟢 **No DB migration is owed** — `settings.world_map`
> is a JSON key on a per-work blob: **orphaned, not corrupting.** 🟢 **And no user content is lost:** the
> location↔location relation **EDGES** (`contains`/`borders`/`route_to`) are **KG data**, not place-graph
> data — they **survive in `kg-graph`**, which renders relations.
> 📌 **SPEC EDIT (do it in W8-00 — the current text is WRONG and is a silent drop):** spec 38 **:465** says
> OQ-9's place-graph *"belongs to plan 30's Wave 6 editor-craft ports."* **It does not — Wave 6 contains no
> place-graph row** (plan 30 `:426-436`). Replace with: *"RESOLVED — won't-port. Superseded by
> `kg-entities`/`kg-graph` (authoring, W8-02/03) + the `world-map` panel (spatial, W8-13). See
> `D-WORLDMAP-PLACE-GRAPH-WONTPORT`."*

---

### W8-16 · [FE] 🔴 the `cast` panel — CastCodexPanel, homed

**Why it is not `kg-entities`.** The closest studio panel, `kg-entities`, is a **thin wrapper over knowledge's
`EntitiesTab`** — a **flat, cross-project entity LIST** with **no kind-grouping** and **no spoiler-safe
story-state join**. **It is not this.** `CastCodexPanel` is the **book's cast as a docked codex**:
**GROUPED BY KIND**, searchable, each row showing its **spoiler-safe current story-state** (it joins knowledge
`entities` ↔ `EntityStatusEntry` — `CastCodexPanel.tsx:7,17`). It is also the **deep-link TARGET** of the
canon-growth entity chips and the **Cast→Arc launcher**.

**Panel id: `cast`. Category: `storyBible`** (🟢 already in `CATEGORY_ORDER` — **G3 confirms it; no X-2
dependency**). **Palette-visible. `guideBodyKey` REQUIRED.**

**Files**

1. **`frontend/src/features/studio/panels/CastPanel.tsx`** — **NEW** (≤100 lines — a thin wrapper).
   Root `data-testid="studio-cast-panel"`. **`useStudioPanel('cast', props.api, { mcpToolPrefixes: ['kg_'] })`
   as its FIRST hook** (amendment A).
   🔴 **LEAF-REUSE `CastCodexPanel` — do NOT mount `<CompositionPanel soloPanel=…>`.** *(Wave 6's own EC-6
   rule: ~20 hooks fire and `WorkspaceLayoutContext` is missing.)*
   **Props:** `bookId` = `host.bookId`; `chapterId` from the **manuscript hoist's active chapter, via the ONE
   convention spec 31 QC-10 locks** (`QualityCriticPanel.tsx:33-59`'s picker — **including the
   `chaptersTruncated` no-silent-cap notice**); `token`; `onViewArc={(entityId) => host.openPanel('character-arc', { entityId })}`.
   🔴 **`search` MUST be LIFTED into panel params** (`CastCodexPanel.tsx:32,40-42` already supports the
   controlled `search`/`onSearchChange` pair) **so the canon-growth deep-links still land.**
2. **`frontend/src/features/composition/components/CastCodexPanel.tsx`** — **EDIT (minimal).** No fork. It
   already takes every prop needed.
3. **GG-8 registration (+1):** the same 6 steps as W8-12 — `catalog.ts` row
   (`category:'storyBible'`, `guideBodyKey` **mandatory**) · `en/studio.json` · **17 locales via
   `python scripts/i18n_translate.py`** (never hand-write) · `frontend_tools.py` **enum + description clause**
   (*"'cast' = the book's characters, places and factions as a codex, with each one's current story-state."*) ·
   **regenerate `contracts/frontend-tools.contract.json`** and commit it **in the same commit**.

4. 🔴 **FLIP THE GG-4 PENDING ROW — `frontend/src/features/studio/panels/__tests__/legacyParityContract.test.ts`**
   (Wave 6 / W6-M5 shipped it). Change `cast: { pending: 'Wave 8 / W8-16 …' }` → **`cast: 'cast'`**.
   **This is not optional bookkeeping — it is the GG-4 gate discharging.** The three pending rows
   (`cast`, `arc`, `flywheel`) are flipped by W8-16/17/18 respectively; when the last one lands,
   `it.fails('GG-4: zero pending rows')` **starts passing** — at which point flip it from `it.fails` to
   `it`. *(Deletion of `ChapterEditorPage` remains blocked on `D-STUDIO-MOBILE-SHELL` / E-3, a PO call.
   The gate going green is a **precondition**, not the authorization.)*

**Tests** — `panels/__tests__/CastPanel.test.tsx` (NEW): renders **grouped by kind** (not a flat list);
a row's story-state renders; `onViewArc` calls `host.openPanel('character-arc', { entityId })`; a `search`
**param** prefills the box; **no book** ⇒ an empty state, **not a blank panel**; **DOCK-7/DOCK-9 hygiene
green.** Plus **`legacyParityContract.test.ts` re-run: the `cast` row is a STRING home and is openable.**

**DoD evidence:** `"W8-16: vitest <N> passed. Panel 'cast' registered — py enum == contract enum == openable, all three at N_BEFORE+3 (assert the DELTA). CastCodexPanel is LEAF-mounted (no <CompositionPanel soloPanel>); rows are GROUPED BY KIND with the spoiler-safe story-state join (kg-entities has neither); search is a panel PARAM so deep-links land; onViewArc opens character-arc with the entityId. legacyParityContract: the cast PENDING row is FLIPPED to a string home and resolves — 2 pending rows remain (arc, flywheel), by design."`

**dependsOn:** W8-02

---

### W8-17 · [FE] 🔴 the `character-arc` panel — CharacterArcView, homed

**Panel id: `character-arc`. Category: `storyBible`. Params: `{ entityId? }`.**
ONE character's events in `event_order` on a compact arc, **spoiler-cut at the current chapter**, with an
active→gone state band and the 1-hop `ArcRelationsStrip`. **Launched with a character preselected from `cast`**
— today that hand-off is `onViewArc`/`setArcEntityId` **inside `CompositionPanel`** (`:112,754,770`) **and it
DIES with it.** The `entityId` **param** is what replaces it.

**Files**

1. **`frontend/src/features/studio/panels/CharacterArcPanel.tsx`** — **NEW** (≤100 lines). Root
   `data-testid="studio-character-arc-panel"`. `useStudioPanel('character-arc', props.api, { mcpToolPrefixes: ['kg_'] })`.
   **Leaf-reuse `CharacterArcView`** (EC-6). `bookId` = `host.bookId`; `chapterId` from the **same QC-10
   chapter picker** as W8-16; `entityId` = `params.entityId ?? null`; `onEntityChange` writes it back to the
   panel params.
   🔴 **BARE-OPEN IS A REAL STATE.** `ui_open_studio_panel {panel_id:"character-arc"}` with **no `entityId`**
   must render **"Pick a character"** — an inline picker **plus** a button → `host.openPanel('cast')`.
   **NOT a blank panel.** *(A blank panel behind a `shown:true` is the silent-success class.)*
2. 🔴 **`frontend/src/features/composition/components/CharacterArcView.tsx`** — **EDIT — MANDATORY, and it is
   the trap in this slice.** It imports **`useNavigate` from `react-router-dom`** and does
   `navigate(\`/books/${bookId}/chapters/${cid}/edit\`)` (**`:9`, `:65`**). **Inside the dock that NAVIGATES
   THE WHOLE APP AWAY AND UNMOUNTS THE STUDIO** — DOCK-7 in spirit, and `dockablePanelHygiene` reds on the
   **wrapper** the moment it re-exports it. **Replace `navigate(...)` with an injected
   `onOpenChapter?: (chapterId: string) => void` prop**; the panel passes
   `(cid) => host.openPanel('editor', { chapterId: cid })`. **The prop is OPTIONAL** — the legacy
   `CompositionPanel` mount passes its own `navigate` and **stays byte-identical.**
3. **GG-8 registration (+1)** — same 6 steps. Description clause: *"'character-arc' = one character's events
   on a timeline, spoiler-cut at the chapter you are reading."*

**Tests** — `panels/__tests__/CharacterArcPanel.test.tsx` (NEW): 🔴 `a BARE open renders the pick-a-character
state and a link to cast, NOT a blank panel`; `entityId in params preselects that character`; 🔴
`clicking a chapter calls host.openPanel('editor', {chapterId}) and does NOT call useNavigate` — **assert the
router mock was NOT called. That is the regression lock on the DOCK-7 trap.** Plus: hygiene green.

🔴 **FLIP THE GG-4 PENDING ROW** (same step 4 as W8-16): in `legacyParityContract.test.ts`,
`arc: { pending: 'Wave 8 / W8-17 …' }` → **`arc: 'character-arc'`**.

**DoD evidence:** `"W8-17: vitest <N> passed. Panel 'character-arc' registered (delta N_BEFORE+4, three-way). CharacterArcView's react-router useNavigate is REPLACED by an injected onOpenChapter — asserted the router mock is NOT called from the dock (it would have unmounted the whole studio). Bare open renders pick-a-character + a link to cast, not a blank panel. cast → host.openPanel('character-arc', {entityId}) lands (the onViewArc/setArcEntityId hand-off that died with CompositionPanel is now a panel PARAM). legacyParityContract: the arc PENDING row is FLIPPED — 1 pending row remains (flywheel)."`

**dependsOn:** W8-16

---

### W8-18 · [FE] 🔴 the `canon-growth` panel — FlywheelPanel, homed

**Panel id: `canon-growth`. Category: `knowledge`.**
After a **publish→extraction** run completes, it shows **"+N entities / +N relations / +N events"** the run
**ADDED to canon**, with named highlights. It reads **`knowledgeApi.getFlywheel`** (`api.ts:1252` →
`GET /projects/{projectId}/flywheel`) — **knowledge-service. Wave 8 is already in these files.**

🔴 **IT IS NOT `quality-corrections`.** That is `CorrectionStatsTable` — **composition** correction *rates*.
**Two services, two datasets.** *(Wave 1's own plan records the refutation at `:2445`; spec 31 `:64` repeats
it. Wave 6's map row is simply wrong — §11.)*

**Files**

1. **`frontend/src/features/studio/panels/CanonGrowthPanel.tsx`** — **NEW** (≤80 lines). Root
   `data-testid="studio-canon-growth-panel"`. `useStudioPanel('canon-growth', props.api, { mcpToolPrefixes: ['kg_'] })`.
   **Leaf-reuse `FlywheelPanel`** (EC-6). Resolves `projectId` from **`useBookKnowledgeProject(host.bookId)`**
   — the **same** self-resolving convention `kg-overview` uses.
   🔴 **REWIRE ITS THREE DEEP-LINKS TO `host.openPanel`** (`FlywheelPanel.tsx:12-16` — today they are
   in-page tab switches that **die with `CompositionPanel`**):
   | prop | today | in the dock |
   |---|---|---|
   | `onOpenCast(name?)` | switches to the `cast` tab | `host.openPanel('cast', { search: name })` — 🔴 **this is WHY `cast` must ship in the SAME wave**, and why W8-16 lifts `search` into params |
   | `onOpenTimeline()` | the `timeline` tab | `host.openPanel('kg-timeline')` |
   | `onOpenRelations()` | the `relations` tab | `host.openPanel('kg-graph')` |
   🟢 It **already** renders a **neutral empty state** before the first extraction (`flywheel-empty`) — **keep
   it. Do not turn it into an error.**
2. **GG-8 registration (+1)** — same 6 steps. Description clause: *"'canon-growth' = what the last extraction
   ADDED to your canon — new entities, relations and events."*
   ⚠ **Category `knowledge`** — confirm it is in `CATEGORY_ORDER` before you write the row. **If it is not,
   use `storyBible`** (which G3 already proved is). 🔴 **DO NOT ADD A CATEGORY** — an **unlisted** category
   sorts **FIRST** (`indexOf → -1`) and would shove the group above `editor`.

**Tests** — `panels/__tests__/CanonGrowthPanel.test.tsx` (NEW): the three counters render from a mocked
`getFlywheel`; 🔴 **an entity chip calls `host.openPanel('cast', { search: <name> })`** (the pairing lock);
the two other stats open `kg-timeline` / `kg-graph`; **no extraction yet ⇒ the neutral empty state, not an
error**; hygiene green.

🔴 **FLIP THE LAST GG-4 PENDING ROW — AND CLOSE THE GATE OUT.** In `legacyParityContract.test.ts`:
`flywheel: { pending: 'Wave 8 / W8-18 …' }` → **`flywheel: 'canon-growth'`**. This is the **third and last**
pending row ⇒ **change `it.fails('GG-4: zero pending rows', …)` to `it(…)`** — it now passes, and the
mechanical GG-4 gate is GREEN for the first time. ⚠ **Green ≠ authorized:** deleting `ChapterEditorPage` is
**still** blocked on `D-STUDIO-MOBILE-SHELL` (E-3, a PO decision) and on spec 16's Phase-4b *"kept
indefinitely"* ruling. **Do NOT delete the page in this wave.**

**DoD evidence:** `"W8-18: vitest <N> passed. Panel 'canon-growth' registered (delta N_BEFORE+5, three-way — the FINAL count). FlywheelPanel is LEAF-mounted and reads knowledgeApi.getFlywheel (knowledge-service — it is NOT quality-corrections/CorrectionStatsTable, which is composition correction RATES). Its 3 deep-links now go through host.openPanel — an entity chip lands in 'cast' WITH the search param (asserted). 🔴 legacyParityContract: the LAST pending row is FLIPPED; 'GG-4: zero pending rows' converted from it.fails to it and PASSES — 25/25 sub-tabs have a real home or a reviewed retirement. ChapterEditorPage is NOT deleted (E-3 open)."`

**dependsOn:** W8-16

---

### W8-19 · [TEST] `studio-kg-codex.spec.ts` — the codex-trio LIVE BROWSER smoke

**Files** — `frontend/tests/e2e/specs/studio-kg-codex.spec.ts` (**NEW**). **BAKED frontend**
(rebuild the image, or `vite dev` on `:5199` — `:5174` is nginx and a host vite **SHADOWS** it). Account
`claude-test@loreweave.dev`.

**The cases:**
1. **`open cast → it is GROUPED BY KIND and a row shows a story-state`** (the thing `kg-entities` cannot do).
2. 🔴 **`cast → View arc → the character-arc panel MOUNTS with that character preselected`** — the
   cross-panel hand-off. *(In `CompositionPanel` this was `setArcEntityId`; it now rides a panel **param**.
   **A unit test cannot see the dock actually mount it.**)*
3. 🔴 **`canon-growth's entity chip opens cast FOCUSED on that entity`** — the deep-link **through the dock**.
4. 🔴 **`a chat turn calling ui_open_studio_panel {panel_id:"character-arc"} BARE mounts the tab and renders
   the pick-a-character state`** — **not a blank panel.** *(The one path the happy-path smoke never touches.)*

**DoD evidence:** `"W8-19: live smoke: studio-kg-codex.spec.ts 4 passed against the BAKED FE — cast renders grouped-by-kind with story-states; cast→View arc mounted character-arc with the character preselected (the param hand-off works in the real dock); canon-growth's entity chip opened cast focused on that entity; a chat turn's bare ui_open_studio_panel {panel_id:'character-arc'} mounted the tab and rendered pick-a-character, not a blank panel."`

**dependsOn:** W8-16, W8-17, W8-18

---

### W8-15 · [DOC] `/review-impl` on the wave diff + fix everything it finds + SESSION_HANDOFF

**This is a MANDATORY slice, quoted from the PO policy: *"`/review-impl` runs at the completion of EVERY
wave, and any bug it finds is fixed before the wave closes."***

**Steps, in order:**

1. **Run the full suites** — the counts go into the evidence:
   ```bash
   cd services/knowledge-service && python -m pytest tests -q -n auto --dist loadgroup
   cd services/book-service && go test ./...
   cd frontend && npx vitest run
   cd frontend && npx playwright test tests/e2e/specs/studio-kg-write.spec.ts \
       tests/e2e/specs/studio-world-map.spec.ts tests/e2e/specs/studio-kg-codex.spec.ts
   ```
2. 🔴 **RE-READ THE CONTRACTS AND DIFF THEM AGAINST WHAT SHIPPED** (`contracts/api/books/v1/openapi.yaml` +
   `contracts/api/knowledge-service/kg_authoring.yaml`, frozen in **W8-0C**). **A contract written first and
   never re-checked is the same drift with extra steps.** Any divergence: **the contract is the spec — change
   the CODE**, unless the contract was wrong, in which case fix it **here**.
3. **Run `/review-impl`** on the wave's diff (`git diff main...HEAD`). **Fix every bug it finds. Do not defer
   a bug it finds into the next wave — there IS no next wave; Wave 8 is the last one.** (A finding that
   genuinely clears the CLAUDE.md defer gate may become a row in §8.1 — but "I'd rather not" is not a gate.)
4. **`docs/sessions/SESSION_HANDOFF.md`** — **EDIT.** Overwrite the ▶ NEXT SESSION block: date, HEAD, the
   wave's outcome, the panel counts (**`N_BEFORE + 5`**), and the **defer rows from §8.1**. 🔴 **Move the FOUR
   RETIRED rows (§8.0) to "Recently cleared"** — `D-KG-FACT-RESTORE`, `D-KG-RELATION-PREDICATE-UNCONSTRAINED`,
   `D-KG-PROJECTION-DEGRADE-OPAQUE`, `D-WORLD-MARKER-TYPE-VOCAB`. **They were BUILT, not deferred.**
5. 🔴 **HAND OFF §11 TO WAVE 6 IN WRITING.** Add a **Decisions** row to `SESSION_HANDOFF.md` naming **H-1**
   (the two false `LEGACY_SUBTAB_HOME` rows), **H-2** (`scene-compose` + `chapter-assemble`), and **H-3**
   (`canonview`'s two homes). **Wave 6's gate goes GREEN on a deleted feature until H-1 lands.**
6. **`docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`** — **EDIT.** In §11's table,
   update the Wave-8 row's filename to `38_kg_and_world.md` (the placeholder `38_kg_world_workflows.md` is
   retired — PO-2 dropped `G-WORKFLOWS`). Mark **G-KG-WRITE-HOLES** and **G-WORLD-MAPS** as CLOSED in §5.3.
   **And record `D-WORLDMAP-PLACE-GRAPH-WONTPORT` in §7's "Consciously OUT OF SCOPE" table** — a won't-fix
   must be an **explicit** row, **never a mislabelled map row.**
7. **Spec 38 corrections** (all mandated by the register; do them once, here or in W8-00): OQ-1 → RESOLVED(a) ·
   OQ-4 → **RESOLVED-BUILT** · OQ-5's false `conflicted` claim (:117, :460) · OQ-7 → resolved, no exception
   granted (:463) · OQ-9 → **won't-port, and it does NOT belong to Wave 6** (:465) · §1.1's stale
   *"spec 16 slates the page for deletion"* sentence (**spec 16 Phase 4b REVERSED that**).
8. **Commit.** ⚠ **NEVER `git add -A`** — this is a **shared checkout with concurrent tracks** (plan 30 §9).
   **Enumerate the files.** And remember: **`git commit -- <path>` commits the WORKING TREE, not the index**
   (`git-commit-pathspec-reads-working-tree-not-index`), and **the index may already carry pre-staged
   unrelated changes** — check `git diff --cached` first (`git-index-may-carry-prestaged-unrelated-changes`).

**DoD evidence:** `"W8-15: /review-impl run on the Wave-8 diff — <N> findings, ALL FIXED (list them). Suites: knowledge pytest <N> passed · book-service go test ok · frontend vitest <N> passed · playwright 14 passed (studio-kg-write 5 + studio-world-map 5 + studio-kg-codex 4). Contracts re-read and diffed against the shipped code: 0 divergences. Panels: N_BEFORE+5, three-way. SESSION_HANDOFF updated in the same commit, with the FOUR retired defer rows moved to Recently-cleared (they were BUILT) and the §11 Wave-6 handoff written into Decisions. Plan 30 §5.3: G-KG-WRITE-HOLES + G-WORLD-MAPS marked CLOSED; §7 carries D-WORLDMAP-PLACE-GRAPH-WONTPORT as an explicit won't-fix row. Spec 38 OQ-1/4/5/7/9 corrected."`

**dependsOn:** **all** (this slice runs LAST — after W8-19)

---

## 6 · The registration checklist per new panel (GG-8) — the running baseline

🔴 **FIVE new panel ids this wave** (was two, before §5.4 homed the orphans): **`world` · `world-map` ·
`cast` · `character-arc` · `canon-growth`.** All `category: 'storyBible'` (✅ in `CATEGORY_ORDER`) except
`canon-growth`, which uses `knowledge` **if and only if it is already in `CATEGORY_ORDER`** — **otherwise
`storyBible`.** All five are **bare-id openable** ⇒ all five enter the enum, the Command Palette and the User
Guide. **None is `hiddenFromPalette`. NONE ADDS A CATEGORY.**

### 🔴 THE ENUM BASELINE IS **CUMULATIVE**. Wave 8 is the LAST wave.

| After wave | Panels added | `OPENABLE` == py enum == contract enum |
|---|---|---|
| HEAD `9262ed53e` (pre-wave-1) | — | **57** |
| 1 (spec 31) | 4 | 61 |
| 2 (spec 32) | 1 | 62 |
| 3 (spec 33) | 2 | 64 |
| 4 (spec 34) | 1 | 65 |
| 5 (spec 35) | 1 | 66 |
| 6 (spec 36) | 🔴 **5** (`style-voice` · `reference-shelf` · `divergence` · **`scene-compose`** · **`chapter-assemble`**) | **71** ← **Wave 8's `N_BEFORE`** |
| 7 (spec 37) | **0** | 71 |
| **8 (this plan)** | 🔴 **5** (`world` · `world-map` · `cast` · `character-arc` · `canon-growth`) | **76** |

⚠ **These are a PLANNING aid, NOT a test assertion. ASSERT `N_BEFORE + 5` AND THE THREE-WAY EQUALITY — NEVER
THE LITERAL `76`.** *(An earlier cut of this table read `6 → 3 → 69 → 74`. It predated §5.4 homing the
orphaned `compose`/`assemble` sub-tabs into Wave 6 — **exactly** the compute-from-a-stale-baseline error this
warning exists to kill. If the literal and the delta ever disagree again, **the delta wins.**)* If a wave is re-ordered or dropped, every literal below it is wrong. **Six of the eight
specs got this wrong by each computing from 57** — that is what this table exists to prevent.
🟢 **AND DO NOT "FIX" THE MACHINE GUARD BY ADDING A COUNT TO IT** (`Q-38-PANEL-COUNT-DELTA-NOT-LITERAL`):
`panelCatalogContract.test.ts` is **already delta-safe** — it contains **zero count literals** and asserts
**three-way SET equality**. **Change nothing about its assertion shape.** The delta lives in the **DoD
strings**, not in the test.

🔴 **Per-slice running delta** (each slice's DoD asserts *its own* cumulative number, as a **delta**):
W8-12 `+1` · W8-13 `+2` · W8-16 `+3` · W8-17 `+4` · W8-18 `+5`.

### The 9 steps, in order (plan 30 §8)

| # | File | Edit |
|---|---|---|
| 1 | `frontend/src/features/studio/panels/WorldPanel.tsx` (W8-12) · `WorldMapPanel.tsx` (W8-13) | new — root `data-testid="studio-world-panel"` / `"studio-world-map-panel"`; `useStudioPanel('<id>', props.api, { mcpToolPrefixes: ['world_'] })` |
| 2 | `frontend/src/features/studio/panels/catalog.ts` | two `STUDIO_PANELS` rows. **`category` AND `guideBodyKey` are BOTH mandatory.** **Do NOT add a category.** |
| 3 | `frontend/src/i18n/locales/en/studio.json` | `panels.world.{title,desc,guideBody}` + `panels.world-map.{title,desc,guideBody}` |
| 4 | `frontend/src/i18n/locales/{ar,bn,de,es,fr,hi,id,ja,ko,ms,pt-BR,ru,th,tr,vi,zh-CN,zh-TW}/studio.json` | the same 6 keys × **17** locales — **`python scripts/i18n_translate.py`**, **never hand-write** |
| 5 | `services/chat-service/app/services/frontend_tools.py` | **TWO edits** in `UI_OPEN_STUDIO_PANEL_TOOL`: (a) append `"world"`, `"world-map"` to the `panel_id` **enum** (`:402`); (b) append their clauses to the **description** prose (`:403+`) — **that gloss is the model's ONLY hint** |
| 6 | `contracts/frontend-tools.contract.json` | 🔴 **NEVER hand-edit — REGENERATE:** `cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py`; **commit the regenerated JSON IN THE SAME COMMIT as steps 2 + 5** |
| 7 | `frontend/src/features/studio/host/studioLinks.ts` | **(a)** `worldId?: string` on `StudioLinkContext`; **(b)** the `/worlds/{worldId}` rule → `openPanel('world')` **only when `ctx.worldId === worldId`**; **(c)** `ctx.worldId` absent ⇒ **`external`** (today's behaviour — degrade-safe) |
| 7b | `frontend/src/features/studio/panels/KgOverviewPanel.tsx:44` | 🔴 **MANDATORY** — pass `{ bookId: host.bookId, worldId }`. **Without this line, step 7's rule is DEAD CODE.** |
| 7c | `frontend/src/features/studio/host/__tests__/studioLinks.test.ts` | 3 cases: matching world ⇒ `studio` · a different world id ⇒ `external` · **`worldId` absent ⇒ `external`** (the degrade path a builder forgets) |
| 8 | `frontend/src/features/studio/agent/handlers/worldEffects.ts` (**NEW**) + `useStudioEffectReconciler.ts` | the `WORLD_WRITE_PATTERN` **RegExp** + `registerWorldEffectHandlers()` in the reconciler's `useEffect` **alongside the other four**. **Reads must NOT match.** |
| 8b | `frontend/src/features/studio/agent/handlers/knowledgeEffects.ts` | add `registerEffectHandler(/^memory_(remember|forget)$/, knowledgeEffect)` — `KNOWLEDGE_WRITE_PATTERN` is `/^kg_(?!…)/` and **CANNOT match `memory_forget`** |
| 9 | tours | **SKIP** — neither panel is a role-tour step |

### 🔴 A THIRD MACHINE GUARD THE GG-8 CHECKLIST DOES NOT NAME — and both new panels walk straight into it

`frontend/src/features/studio/panels/__tests__/dockablePanelHygiene.test.ts` **recursively scans every
`.tsx` under `panels/**`** and reds on:

- **DOCK-7** — any `useNavigate(`, `useParams<|(`, or `<Link`. 🔴 **The `world` panel's *"Open the full world
  workspace"* escape hatch is EXACTLY the shape a builder writes as `<Link to="/worlds/{id}">`. It MUST be
  `followStudioLink(...)`** (which `window.open`s a new tab).
- **DOCK-9** — a hand-rolled viewport overlay (**`fixed` + `inset-0` as TOKENS, not adjacent** — the regex is
  token-based on purpose, because this repo has **no Tailwind class-sorter**, so `"inset-0 fixed …"` is a
  legal, undetected reorder). 🔴 **The world picker, the *Create a world* form, `+ New map`, the
  marker/region delete confirms, and the image dropzone are FIVE dialog surfaces across the two panels. ALL
  must go through `@/components/shared` (`FormDialog` / `ConfirmDialog`) or `@radix-ui/react-dialog`
  directly — the test exempts those two imports and NOTHING ELSE** (`dockablePanelHygiene.test.ts:54`).

### Verify (all six green — the first two are the drift-locks, the third is the DOCK gate)

```bash
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
cd frontend && npx vitest run \
  src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
  src/features/studio/panels/__tests__/dockablePanelHygiene.test.ts \
  src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
  src/features/studio/palette/__tests__/useStudioCommands.test.ts \
  src/features/studio/host/__tests__/studioLinks.test.ts \
  src/features/chat/nav/__tests__/frontendToolContract.test.ts
```

**Then VERIFY BY EFFECT (§7).** A green unit suite has repeatedly hidden *"the FE could not actually execute
it."*

**Do NOT touch:** `StudioDock.tsx`, `StudioFrame.tsx`, `useStudioCommands.ts`, `UserGuidePanel.tsx` (all
derive from `catalog.ts`); `studioUiNav.ts` / `useStudioUiToolExecutor.ts` (panel-id-agnostic).

---

## 7 · Wave Definition of Done — the literal checklist

- [ ] 🔴 **CONTRACT-FIRST HELD (W8-0C).** Every route in §3 is in `contracts/api/books/v1/openapi.yaml` or
      `contracts/api/knowledge-service/kg_authoring.yaml` — **written BEFORE its FE consumer**, both linting
      clean, **and re-diffed against the shipped code at W8-15.** *(`contracts/api/book-service/` **does not
      exist** and appears nowhere in the plan or the diff.)*
- [ ] **Every route in §3 exists and is reachable THROUGH THE GATEWAY** (`:3123`), not just from a unit test.
      A `curl` per route, with the test account's JWT.
- [ ] **Machine guards green with ZERO drift:** `panelCatalogContract.test.ts` (**openable == py enum ==
      contract enum, all at `N_BEFORE + 5`** — **assert the delta, never a literal**; 🔴 **do NOT add a count
      literal to the guard — it is already delta-safe**; all five new panels carry a `category` ∈
      `CATEGORY_ORDER` **and** a `guideBodyKey`) · `test_frontend_tools_contract.py` (the **regenerated**
      `contracts/frontend-tools.contract.json` committed **in the same commit** as `catalog.ts` +
      `frontend_tools.py`) · `dockablePanelHygiene.test.ts` (DOCK-7 + DOCK-9).
- [ ] 🔴 **THE FIVE PANELS ARE REGISTERED AND OPENABLE:** `world` · `world-map` · `cast` · `character-arc` ·
      `canon-growth`. **Three of them are homeless legacy sub-tabs that GG-4 would otherwise DELETE** (§5.4).
- [ ] 🔴 **THE §11 WAVE-6 HANDOFF IS WRITTEN INTO `SESSION_HANDOFF.md`.** Until Wave 6 applies **H-1**, its
      machine gate reports **"homed"** for `flywheel` and `arc` — **two features that are being deleted.**
- [ ] **Unit suites green (name them + the counts):** knowledge-service pytest (`-n auto --dist loadgroup`) ·
      book-service `go test ./...` · frontend `vitest`.
- [ ] 🔴 **LIVE BROWSER SMOKE — THREE Playwright specs, against the BAKED frontend, with
      `claude-test@loreweave.dev`:** *(the third is `studio-kg-codex.spec.ts`, W8-19 — cast grouped-by-kind
      with story-states · cast→arc hand-off through the dock · canon-growth's chip → cast · a BARE
      `character-arc` open renders pick-a-character, not a blank panel)*
      - `studio-kg-write.spec.ts` — create an entity → **reload** → it persisted; draw an edge → **reload** →
        it persisted; **Mark wrong** → it is gone; seed-from-glossary renders the counters **by their wire
        names** (`nodes_created`/`nodes_existing`/`entities_seen`/`skipped`/`nodes_conflicted`/`truncated`);
        `kg-overview`'s Delete opens a **real confirm dialog**.
      - `studio-world-map.spec.ts` — create a map → upload an image → place a pin → **drag it with
        `page.mouse`** (CDP-trusted) → **RELOAD** → the pin is at the new coords; a stale rename → **412** +
        the current name; a chat turn's `ui_open_studio_panel {panel_id:"world-map"}` **mounts the dock tab**;
        and 🔴 **the BARE-OPEN DEGRADED LEG on a book with NO world renders the "Link this book to a world"
        state — not a blank panel.**
- [ ] **Cross-service live-smoke token in the VERIFY evidence** (this wave touches ≥2 services:
      `book-service` + `knowledge-service` + `frontend` + `chat-service`) — `live smoke: <one-liner>`, per
      CLAUDE.md Phase 6.
- [ ] 🔴 **`/review-impl` run on the wave's diff, and EVERY bug it finds FIXED before the wave closes**
      (W8-15). **Wave 8 is the last wave — there is no "next wave" to defer a bug into.**
- [ ] **Defer rows filed** (§8) for everything consciously parked.
- [ ] **`SESSION_HANDOFF.md` updated IN THE SAME COMMIT as the code** — work not recorded does not exist.
- [ ] **Plan 30 amended:** §5.3's G-KG-WRITE-HOLES + G-WORLD-MAPS marked CLOSED; §11's table row renamed to
      `38_kg_and_world.md`.
- [ ] **Committed** — file-enumerated, **never `git add -A`** (shared checkout, concurrent tracks).

---
## 8 · Defer register — the STARTING rows

**The policy:** *"blocked ≠ stopped."* A blocker is a **defer row + KEEP GOING**. Stop and ask **only** for a
CRITICAL blocker (destructive/irreversible · a sealed decision proven wrong · a tenancy/security breach · a
paid-action defect that charges the user for nothing). **A missing route is a route you WRITE, not a blocker.**

Every row below has **earned** its gate. Add new rows to `docs/sessions/SESSION_HANDOFF.md` → Deferred Items
as you go.

### 🔴 8.0 — THREE ROWS ARE **RETIRED**, NOT DEFERRED (the register overruled the draft)

The reconciliation pass **deleted** these three. **Do not re-file them.** Each was a gate-#2 claim the register
**disproved against source** — and CLAUDE.md is explicit: *"missing infrastructure is NOT blocked — it is
unbuilt work to implement"*, and *"if fixing the bug is cheaper than writing + carrying its defer row, just
fix it."*

| RETIRED row | Why it was not eligible | Where it is BUILT |
|---|---|---|
| ~~`D-KG-FACT-RESTORE`~~ | *"needs a new engine fn + route + tool"* — **that is a description of work, not a blocker.** ~60 BE lines **in files BE-14b already opens.** | **W8-05** (BE-14b2 + the `merge_fact` resurrect fix) + **W8-06** (undo toast + Show-forgotten) |
| ~~`D-KG-RELATION-PREDICATE-UNCONSTRAINED`~~ | *"widening the ontology check is a knowledge-service design call"* — **FALSE. The design call was already made and CODED**: `validate_edge()` implements the exact rule and `kg_propose_edge` already calls it. **Only the two REST endpoints were left unwired.** | **W8-03** (BE-14e) |
| ~~`D-KG-PROJECTION-DEGRADE-OPAQUE`~~ | *"the fix is in the ENGINE"* — **yes, and the engine is in this repo.** `glossary_unreachable` is **~6 additive lines** and without it a glossary **outage** renders as *"your glossary is empty"* — **a silent-success lie.** | **W8-05** (BE-14a2) |
| ~~`D-WORLD-MARKER-TYPE-VOCAB`~~ | *"the BE must own a vocabulary before the FE can declare it closed"* — **the FE is not declaring it closed.** `marker_type` is **genuinely open**, the enum rule **does not reach a domain tool**, and the control is an `<input list>`+`<datalist>` with a **tested in-repo precedent.** **Answered, not deferred.** | **W8-13** (`markerTypes.ts`) |

### 8.1 — the rows that DID earn their gate

| ID | Origin | What | Gate (CLAUDE.md 1–5) | Target / trigger |
|---|---|---|---|---|
| **D-KG-MANUAL-NODE-ANCHOR** | W8-02 (A1) | Let a user **bind an existing graph-only node to a glossary entity whose kind/name it does NOT match**. *(⚠ **The rationale is CORRECTED**: its value is **NOT** "prevents a conflict" — `Q-38-OQ5` proves **`conflicted` is unreachable from a manual node**. Its value is the **binding** itself.)* | **#2 large/structural** — the route has **no `book_id`** (it would need `projects_repo.project_meta` **+ a cross-service glossary grant-check** to validate the FK), needs `merge_entity_at_id`-style handling, and must **409** on the `entity_glossary_fk_unique` clash. | Post-wave-8. **v1 mitigation SHIPS in W8-02:** the corrected in-form anchor note + the seed-from-glossary pointer. |
| **D-WORLD-NO-COLLABORATORS** | W8-12 | **Worlds have no collaborators** (`server.go:378-380`) while books **do** (E0 grants). A book collaborator with EDIT gets a **404 from every world route** and therefore cannot see the book's world or its maps. | **#5 conscious won't-fix** — worlds are **owner-only ON PURPOSE**. 🔴 **This is NOT a bug to fix by widening the world routes.** | **Recorded, not scheduled.** W8-12/13 render the uniform *"you don't have access"* card. Revisit only if a product decision changes the world tenancy model. |
| 🔴 **D-WORLDMAP-PLACE-GRAPH-WONTPORT** | §5.4 | `composition/components/WorldMap.tsx` + `useWorldMap.ts` + `PlaceNode.tsx` + the `composition_work.settings.world_map` JSON blob (the legacy **place-graph**) are **NOT ported to a Studio panel — ever.** *(Renames `D-WORLD-MAP-LEGACY-PLACEGRAPH`, whose "belongs to Wave 6" target was **FALSE** — Wave 6 contains no place-graph row.)* | **#5 conscious won't-fix** — **both** capabilities are strictly absorbed: authoring → `kg-entities`/`kg-graph` (W8-02/03); spatial → the `world-map` panel (W8-13); *open-in-codex* → the W8-13 inspector. A port would put **two panels named "world map"** in one dock over **two data models** (a PO-3 violation). | **Trigger:** delete the three files **in the same commit that retires `ChapterEditorPage`** — 🟢 **and spec 16 Phase 4b KEEPS that page INDEFINITELY**, so **nothing is lost before then**. 🟢 **No DB migration owed** (the blob is orphaned, not corrupting). 🟢 **No user content lost** (the location↔location edges are KG data and survive in `kg-graph`). |
| **D-KG-BIO-NO-FACTS** | W8-06 | `kg-bio` renders a bio **summary** blob and has **no facts list** — so the Forget action cannot live there. | **#5 conscious won't-fix** — there is nothing to hang it on. | **Recorded so `kg-bio` is not re-proposed as the A4 home.** A4 lives on `EntityDetailPanel` — which lights it up in **THREE** surfaces (`kg-entities`, `kg-graph`, **and `world`**'s rollup graph). |
| 🔴 **D-KG-GLOSSARY-KIND-ALIAS-DRIFT** | W8-01 (BE-14d) | `faction` is glossary's **alias** for the canonical `organization` (`glossary/migrate.go:203`), and knowledge's `concept` maps to glossary's `terminology` (`entity_resolver.py:69-74`). **So a manually-authored `faction` node carries a kind_code that will NEVER anchor.** | **#1 out of scope** — a pre-existing **KG↔glossary vocabulary drift**. BE-14d must **not silently rename a kind on a shipped REST route.** | Post-wave-8. Recorded by `Q-38-BE-14d`'s own note. |
| 🔴 **D-WORLDLORE-KIND-ID-FROM-GLOBAL-LIST** | W8-13 (OQ-2) | `features/world/hooks/useWorldLore.ts` feeds `createBibleEntity` a `kind_id` from the **GLOBAL** `/v1/glossary/kinds` list, while glossary's `createEntity` validates it against **THIS book's `book_kinds`** (`entity_handler.go:363-377`). **That world-lore WRITE path is very likely broken today.** | **#4 blocked-on-evidence** — *it is one line to fix* **if** the break reproduces. **FIX IT NOW in W8-12 if a 10-minute repro confirms it**; only file the row if it does not reproduce. | W8-12. **A defer row for a one-line fix is the anti-pattern CLAUDE.md kills — reproduce it first.** |

---

## 9.0 · 🔴 THE CONTRADICTION LEDGER — where the REGISTER overruled this plan

**The plan was written blind to
[`docs/plans/studio-adjudication/wave-8-decisions.md`](studio-adjudication/wave-8-decisions.md).** These are
the places it was **WRONG** and has been **REWRITTEN**. **The register wins. Do not restore any of the
left-hand column.**

| # | The plan SAID (deleted) | The register RULES (binding) | Where |
|---|---|---|---|
| **C-1** | *"the register does not exist … the CODE wins over it"* | **It exists. 68 decided items, each adjudicated against source. IT OUTRANKS THIS PLAN.** | §0 |
| **C-2** | `D-KG-FACT-RESTORE` — defer, and ship copy saying *"there is no un-forget button"* | 🔴 **BUILD RESTORE.** `Q-38-OQ4`. ~60 BE lines in files BE-14b already opens. **The copy the draft would have shipped is now a LIE.** | W8-05 · W8-06 |
| **C-3** | `D-KG-PROJECTION-DEGRADE-OPAQUE` — *"file the row; do not build it"* | 🔴 **BUILD `glossary_unreachable` → 503.** `Q-38-A3-WIRE-NAME-DRIFT` §4. A glossary **outage** must not render as *"your glossary is empty."* | W8-05 |
| **C-4** | `D-KG-RELATION-PREDICATE-UNCONSTRAINED` — *"widening the ontology check is a design call"* | 🔴 **FALSE — the design call is already CODED.** `validate_edge()` + `kg_propose_edge` already do it; only the two REST endpoints are unwired. **BUILD BE-14e.** | W8-03 |
| **C-5** | BE-14a calls the engine **directly** | 🔴 **IT DROPS `reconcile_project_stats`** — the **only** writer of `stat_updated_at`. The seed rail then **stalls at `STOP_UNKNOWN` for GUI users but not agent users.** **Share ONE effect fn.** | W8-05 |
| **C-6** | BE-15b: `LEFT JOIN … COUNT(DISTINCT …) … GROUP BY` | 🔴 **Use the HOUSE pattern — correlated scalar subqueries** (`worlds.go:185-193`). No GROUP BY, no fan-out to reason about. | W8-08 |
| **C-7** | Migration: child `updated_at NOT NULL DEFAULT now()` | 🔴 **That backfills EVERY existing marker as "edited just now"** — and the inspector renders it. **ADD NULLABLE → BACKFILL FROM `created_at` → DEFAULT → NOT NULL.** | §4 |
| **C-8** | The kind constant lives in `app/tools/argbase.py` | 🔴 **`app/entity_kinds.py`** — a top-level leaf module; `tools/` ← `routers/` risks an **import cycle**. **Plus a shared `normalize_entity_kind`** (today the tool strips and REST does not). | W8-01 |
| **C-9** | A1's anchor warning: *"it can SHADOW a glossary entity … → `conflicted`"* | 🔴 **FALSE AGAINST CODE.** A same-name+same-kind manual node is **ADOPTED** by a later projection; **`conflicted` is UNREACHABLE from a manual node** (NULL-FK is exempt from the constraint). The real hazard is a **DUPLICATE**. **New copy shipped + the SPEC corrected.** | W8-02 |
| **C-10** | W8-10: keep `uploadWorldMapImage` as a `?user_id` **shim** | 🔴 **DELETE IT.** Zero callers; a `?user_id`-trusting write surface is a standing **tenancy-audit false-positive**. Re-adding an `/internal` mount later is 3 lines. **(Also: the 413 contract is BROKEN today — it returns 400.)** | W8-10 |
| **C-11** | `worldEffects` invalidates `['world-maps'] ['world-map-detail'] ['worlds'] ['world-books']` | 🔴 **THREE OF THE FOUR ARE WRONG.** `['world-books']` is a **PHANTOM**; the real key is `['living-world','books',id]`. **Mirror the REST producer's own invalidate set (8 keys).** Dead keys = the panel **never refreshes after an agent write** — a false-green. | W8-13 |
| **C-12** | `marker_type`: a `<select>` + free-text escape, **and defer `D-WORLD-MARKER-TYPE-VOCAB`** | 🔴 **ANSWERED, NOT DEFERRED.** `<input list>` + `<datalist>` (tested in-repo precedent); vocabulary in **one FE home**; union with the map's own existing types. **shadcn `Select` cannot do free text at all.** | W8-13 |
| **C-13** | `studioLinks` is **three** files | 🔴 **FOUR.** `BookSettingsPanel.tsx:52` is the **second** throw-away and the **more likely** user path. **Two existing tests go RED — fix them in the same commit.** | W8-12 |
| **C-14** | *"above ~500 markers, cull to the viewport"* | 🔴 **STRUCK.** A second, unbuilt, untested render path with **zero profiling evidence** (defer-gate #4). **Render all markers.** | W8-13 |
| **C-15** | *"2 new panels"* + **zero** contract files (`contracts/api/book-service/` named ×3) | 🔴 **FIVE panels** (§5.4 homes three orphans) and **`contracts/api/book-service/` DOES NOT EXIST.** **W8-0C freezes 16 routes in the two REAL specs, BEFORE any consumer.** | §5.4 · W8-0C |

⚠ **Two places the REGISTER contradicts ITSELF. Both are settled here; do not re-open:**
- **The marker entity picker's source.** `Q-38-OQ9` has one stray parenthetical saying `knowledgeApi`.
  **`Q-38-OQ2` + `Q-38-MARKER-ENTITY-IS-GLOSSARY-NOT-KG` + `Q-38-NAME-COLLISION-THREE-WORLD-MAPS` + the DDL
  comment itself all say GLOSSARY.** ⇒ **GLOSSARY.** (4 against 1, and the DDL is dispositive.)
- **Does the image upload bump `version`?** `Q-38-BE-15d` §4 says yes; `Q-38-MIGRATION-VERSION-UPDATEDAT` §4
  says no. ⇒ **NO** — an image replace is **not a competing rename**, and bumping would **412 an in-flight
  rename for nothing.** *(A PO veto point, flagged as such by both.)*
- **The empty-ontology predicate branch.** `Q-38-OQ6`'s 3-row sketch says *"free-text when empty"*;
  `Q-38-A2-EMPTY-ONTOLOGY` (far more detailed) says *"empty **AND closed** ⇒ NO input + the schema-panel
  escape"*. ⇒ **`A2-EMPTY-ONTOLOGY`**, because with BE-14e a closed empty schema **422s every predicate** — a
  free-text box there is a **guaranteed-fail form.**

---

## 9 · Adjudications — the questions this plan RE-DECIDED against the code

> ⚠ **These were written BEFORE the register was recovered.** They are kept because most were **confirmed**
> by it — but 🔴 **where §9.0 says the register overruled the plan, §9.0 wins and the row below is stale.**
> Specifically: **A-7 is WRONG** (marker_type is answered, not deferred — see C-12) and **A-1's framing** is
> superseded by `Q-38-OQ1-WORLD-CONTAINER-OWNER` (which reaches the same conclusion with better evidence).

| # | Question | ADJUDICATED ANSWER | Evidence |
|---|---|---|---|
| **A-1** | Spec 38 M8b.0: is the Track C ownership handoff a **blocker**? | **NO.** Track C's P-5 is **PARKED** with **no design and no code**. Wave 8 takes it, by write-down (**W8-00**, 10 minutes). **Not one of the four CRITICAL stop-and-ask categories.** | `2026-07-12-track-c-completion-RUN-STATE.md:172-177, :212`; `grep "'world'" catalog.ts` → **0 hits** |
| **A-2** | Spec 38 §3.1-A2: *"a project may have no adopted schema ⇒ `edge_types` can be `[]` ⇒ dead `<select>`"* | **HALF WRONG.** A **non-adopted** project falls back to the System **`general`** template, which **HAS** edge types. The genuinely-empty case is a **BLANK** schema. **The guard is still needed — but for the right reason.** | `graph_schemas.py:227-267` (`resolve_for_project`, fallback at `:250-254`); `ontology.py:505-527` (`create_blank_schema`) |
| **A-3** | 🔴 **`ResolvedSchema.allow_free_edges` — the spec never accounted for it.** Does the create/correct predicate control forbid free text unconditionally? | **NO — it is DRIVEN BY THE SCHEMA'S OWN FLAG.** One `PredicateControl`, four states (W8-03's table). A project that **deliberately** allows free edges gets the escape; a strict one gets the schema-panel guard. **The split-brain the spec feared is still killed** (BOTH verbs use the identical control). | `types/ontology.ts:199`; `graph_schemas.py:257, 263` |
| **A-4** | Spec 38 BE-14d: *"make `KgCreateNodeArgs.kind` a `Literal`"* — is that the whole fix? | **NO — that is ONE THIRD.** `kind` has **THREE** schema sources; **FastMCP generates the wire schema from the FUNCTION SIGNATURE and STRIPS the pydantic model.** All three must change or the agent can still send `kind:"item"`. | `graph_schema_tools.py:451` (pydantic) + `:828-850` (OpenAI JSON schema) + `mcp/server.py:1123-1130` (FastMCP signature); memory `knowledge-mcp-three-schema-sources-fastmcp-strips` |
| **A-5** | OQ-2 (spec 38, **UNVERIFIED**): is the world-bible entity model real enough to source the marker entity picker? | 🟢 **YES — VERIFIED. It holds. Do not re-investigate.** `World.bible_book_id` is FE-reachable and `glossaryApi.listEntities(bookId, {kindCodes:['location']})` exists. Picker = the world's **bible book** first, then the current book's glossary. Degrade when `bible_book_id === null`. | `features/world/types.ts:18`; `features/glossary/api.ts:74-99` |
| **A-6** | OQ-3: retire the dead `/internal/worlds/maps/{id}/image` route? | **YES, RETIRE IT** (W8-10) — after re-running the grep. **Zero callers repo-wide.** Keep the coverage by repointing its 503 test at the new public route. | `server.go:200`; `grep -rn "worlds/maps" services/ frontend/src` → 0 (excluding book-service's own handler) |
| ~~**A-7**~~ 🔴 **SUPERSEDED — see C-12** | OQ-7: is `marker_type` a closed set? | **NO — and it is ANSWERED, NOT DEFERRED** (`Q-38-OQ7`). ~~"DEFER `D-WORLD-MARKER-TYPE-VOCAB`"~~ is **wrong**: the row is **RETIRED**. v1 ships an `<input list>`+`<datalist>` (**not a `<select>`** — shadcn `Select` cannot do free text), one FE vocabulary home, union with the map's own types. **No BE work. No exception to the enum rule is being granted — the rule does not reach a domain tool.** | W8-13 · §8.0 |
| **A-8** | OQ-10: does the `kg-graph` canvas get an edge **delete**? | **YES, IN W8-03.** Right-click an edge → the **existing** `RelationEditDialog` in `edit` mode → **Mark wrong**. **Zero backend, one wiring. Do NOT ship draw-with-no-erase.** | `EntityDetailPanel.tsx:621-627`; `relations.py:48` (`GET /relations/{id}` — *"for the FE correction dialog"*) |
| **A-9** | Where does the A4 Forget row action live? | **`EntityDetailPanel`'s facts list — NOT `kg-bio`.** `kg-bio` has no facts list and does not import `useEntityFacts`. One edit lights it up in **two** panels (`kg-entities` + `kg-graph`). | `EntityDetailPanel.tsx:135, :507-538`; `GlobalBioTab.tsx:7, 29` |
| **A-10** | Plan 30 **X-4**: does `kg_create_node` need a Lane-B handler? | 🟢 **REFUTED — IT ALREADY MATCHES.** `KNOWLEDGE_WRITE_PATTERN` is a **negative lookahead over the whole `^kg_` namespace**. **Do NOT add a handler. Do NOT touch the pattern.** Only `memory_*` is genuinely missing. | `knowledgeEffects.ts:18` |
| **A-11** | Does `world`/`world-map` need a new `category`? | **NO. `storyBible` (already in `CATEGORY_ORDER`).** X-2 (`quality` is missing from `CATEGORY_ORDER`) is a gate on Waves 1/3 — **NOT on Wave 8.** An **unlisted** category sorts **FIRST** (`indexOf → -1`). | `useStudioCommands.ts:20-22` (9 entries) vs `catalog.ts:81-91` (10) |
| **A-12** | Is `restore` a mutation on `useProjects`? | **NO — THERE IS NO `restoreProject`.** Restore is an **OCC PATCH**: `updateProject({payload:{is_archived:false}, expectedVersion})`. **The version is LOAD-BEARING (D-K8-03).** | `useProjects.ts:144-147`; `ProjectsBrowser.tsx:142-155` |

---

## 10 · Risks — and the TELL that each has fired

| # | Risk | The **TELL** | Mitigation (already in a slice) |
|---|---|---|---|
| **R-1** | 🔴 **The chi route-order trap.** `/v1/worlds/maps/{id}` gets swallowed by `/{world_id}` ⇒ `world_id="maps"`. | Every map route **400s** with *"invalid world_id"*, or **404s** with a *world*-shaped error instead of a map-shaped one. | **W8-08's `maps_routing_test.go`** asserts `GET /v1/worlds/maps/<uuid>` reaches `getWorldMap`. |
| **R-2** | 🔴 **The `COUNT` fan-out.** Two LEFT JOINs on one parent multiply rows; `marker_count` and `region_count` come back as `markers × regions`. | The rail shows **plausible but wrong** counts — e.g. a map with 2 pins and 3 regions reports **6 and 6**. **Nobody notices, because 6 is a believable number.** | **`COUNT(DISTINCT …)`** + **W8-08's `TestListWorldMaps_CountsAreNotFannedOut`** (2 markers + 3 regions ⇒ 2 and 3). |
| **R-3** | 🔴 **PATCH partial semantics: absent vs explicit `null`.** In Go an omitted field decodes to the **zero value**, so `x: 0` (a legitimate **left-edge** coordinate) is indistinguishable from "absent". | **The left edge of every map is unreachable.** A pin dragged to `x=0` silently snaps back. It looks like a **rounding bug**, so the builder "fixes" the clamp — and it persists. | **Pointer fields** (`X *float64`) + **W8-11's `TestWorldMapUpdateMarker_XZeroIsNotTreatedAsAbsent`** + **W8-09's `TestPatchMarker_AbsentKeyIsUnchanged_ExplicitNullClears`**. |
| **R-4** | 🔴 **The drag PATCH never lands, and the UI never tells you** — it just repaints optimistic state. | The pin "moves" perfectly in the browser. **It is at the old coords after a reload.** A unit test cannot see this. | **W8-14 case 2: drag with `page.mouse` → RELOAD → assert the coords.** Plus the **inspector renders `updated_at`** ("edited 4m ago"), which makes a landed write **visible**. |
| **R-5** | 🔴 **The Lane-B handler is registered as a STRING with an alternation** ⇒ it matches **NOTHING** and ships a **silent no-op**. | An agent writes a map/marker and **the panel never refreshes**. **No unit test catches it** — a handler test registers and calls its own fake. | **A `RegExp`, mandated in W8-06 + W8-13**, with `matchEffectHandlers('memory_forget').length > 0` and `expect(WORLD_WRITE_PATTERN).toBeInstanceOf(RegExp)` as the locks. |
| **R-6** | 🔴 **The projection counters render as `undefined`.** The FE reads the ENGINE's names (`created`/`conflicted`) instead of the WIRE's (`nodes_created`/`nodes_conflicted`). | The seed CTA shows *"Added undefined"* — or worse, **renders nothing for `conflicted`** and reports a partial projection as a complete one. **That is the exact bug the counters were ADDED to expose** (`D-KG-GLOSSARY-FK-GLOBAL-UNIQUE`). | **BE-14a zero-fills and ALWAYS emits all six** (W8-05's `test_all_six_counters_are_always_present_even_when_zero`); the FE type has **six REQUIRED keys**; **W8-07 case 4** asserts the wire names in the browser. |
| **R-7** | 🔴 **The `studioLinks` rule ships as DEAD CODE** — `KgOverviewPanel:44` still throws the `worldId` away. | Everything is green, the rule is written… and clicking **World** in `kg-overview` **still pops a browser tab out of the studio.** The papercut the slice claims to fix is untouched. | **Checklist step 7b is MANDATORY**, and **W8-12's `studioLinks.test.ts`** has the **`worldId`-absent ⇒ external** degrade case. |
| **R-8** | 🔴 **The three dead buttons come back.** A future `noop` re-creates them, silently. | Nothing. **That is the point** — a dead button is invisible. It shipped once already. | **W8-04 makes the props OPTIONAL** ⇒ the next `noop` produces a **missing button** (visible) instead of a **dead** one. **Four vitest cases lock it.** |
| **R-9** | **The enum baseline is computed from 57 instead of 69.** | `panelCatalogContract.test.ts` reds with an off-by-12, and the builder goes hunting a **phantom regression** in Waves 1–6. | **§6's cumulative table** + **"assert the DELTA (`N_BEFORE + 5`) and the three-way equality, NEVER a literal"**, in every DoD string. **Six of the eight specs got this wrong.** 🟢 **And do NOT "harden" the guard by adding a count to it — it is already delta-safe.** |
| 🔴 **R-14** | **A homeless legacy sub-tab is DELETED at GG-4 while the gate reports it "homed".** Wave 6's `LEGACY_SUBTAB_HOME` maps `flywheel → quality-corrections` and `arc → arc-templates`. **Both are wrong** — different components, different services, different datasets. | **Nothing. That is the point.** The machine gate goes **GREEN**. The feature is gone and no test reds. **This is the single most dangerous line in the whole retirement plan.** | **§5.4** homes `cast`/`character-arc`/`canon-growth` in **W8-16/17/18**, and **§11 H-1** tells Wave 6 to fix the two map rows. **W8-15 step 5 writes the handoff into `SESSION_HANDOFF.md` so it cannot evaporate.** |
| 🔴 **R-15** | **A route ships with no contract**, and the FE codes against a shape that was never frozen. | Nothing — until two services disagree in production. **Seven of ten waves add REST routes and touch ZERO contract files.** | **W8-0C** freezes all 16 routes **before** any consumer, in the **two real spec files** — and **W8-15 re-diffs them against the shipped code.** |
| **R-10** | **A foreign/absent world sends the panel into a 404 retry loop** (worlds are owner-only; books are not). | The `world` panel spins forever, or hammers the gateway, for any **book collaborator**. | **W8-12's `world-foreign` state** — a uniform no-access card, **no retry**, **no oracle**. **Do NOT "fix" it by widening the world routes.** |
| **R-11** | **`EntityDetailPanel` (640+ lines) grows further** and the component-size rule erodes one edit at a time. | A 700-line component with 14 concerns; the next reviewer shrugs. | **W8-06 EXTRACTS `FactRow`** (mirroring the file's own `RelationRow` pattern) instead of inlining the action. |
| **R-12** | **A stale FE image false-greens the live smoke.** `:5174` is the **baked nginx build**; a host `vite dev` **SHADOWS** it. | The Playwright spec passes against **code that is not the code you wrote**. | **W8-07 + W8-14 both mandate a REBUILD** (or `vite dev` on `:5199`). `live-smoke-rebuild-stale-images-first`. |
| **R-13** | **A concurrent track's file is clobbered.** This is a **shared checkout** with Track C + the Book-Package track on the **same branch**. | A commit quietly reverts someone else's work. | **NEVER `git add -A`** — enumerate files. Remember `git commit -- <path>` commits the **WORKING TREE**, not the index, and **the index may carry pre-staged unrelated changes** (`git diff --cached` first). **Do NOT touch** `chat-service/app/services/stream_service.py`, `ToolApprovalCard.tsx`, `useChatMessages.ts`, `tool_permissions.py` (Track C, mid-edit — plan 30 §9). |

---

## 11 · 🔴 CROSS-WAVE HANDOFF — three edits **WAVE 6** owes, and they are not optional

**Why this section exists rather than an edit to wave-6's plan file.** `docs/plans/2026-07-13-studio-wave-6-editor-craft.md`
is being reconciled by a **concurrent agent on this shared checkout**. Editing it from here is the exact
concurrent-overwrite class this repo has been bitten by twice (`efc9fa96e`, `a8700878c` are both *"restore
catalog/i18n additions dropped by a concurrent session"*). **So the instructions live here, in a durable file,
and Wave 6 applies them.** 🔴 **If Wave 6 does NOT apply H-1 and H-2, its machine-checked gate goes GREEN on
two features being DELETED.** That is the single most dangerous state in the whole retirement plan.

### H-1 · 🔴 FIX TWO FALSE ROWS IN WAVE 6'S `LEGACY_SUBTAB_HOME` MAP

They are **not** aliases. They are **different components in different services over different datasets** —
and because the map is what the GG-4 gate reads, a wrong row means **the gate reports "homed" for a feature
about to be deleted.**

| wave-6 line | The row today | What it must become | Why |
|---|---|---|---|
| `:1454` | `flywheel: 'quality-corrections'` | 🔴 **`flywheel: 'canon-growth'`** (Wave 8, **W8-18**) | `quality-corrections` = `CorrectionStatsTable` — **composition** correction *rates*. `FlywheelPanel` = **knowledge-graph GROWTH** (`knowledgeApi.getFlywheel`). **Two services, two datasets. The name collides; the thing does not.** *(Wave 1's own plan says exactly this, in writing, at `:2445`; spec 31 `:64` repeats it.)* |
| `:1457` | `arc: 'arc-templates'` | 🔴 **`arc: 'character-arc'`** (Wave 8, **W8-17**) | `arc-templates` (Wave 4) = the structure-TEMPLATE library + 拆文 deconstruct. `arc-inspector` (Wave 2) = the narrative arc **SPEC tree** over book/composition arc rows. **Neither is a character's EVENT arc over the knowledge graph.** |

### H-2 · 🔴 TWO PANELS WAVE 6 MUST ADD (they have no home in ANY wave today)

**Both are `CompositionPanel` sub-tabs. Both die at GG-4 with no replacement.** Both are **leaf-reuse** —
🔴 **mount the LEAF, never `<CompositionPanel soloPanel=…>`** (Wave 6's own **EC-6** rule: ~20 hooks fire and
`WorkspaceLayoutContext` is missing).

**H-2a · panel id `scene-compose`** — a **4th** panel alongside `style-voice` / `reference-shelf` /
`divergence`. Mount **`ComposeView`** as a leaf.
- **The scene-scoped draft loop:** guide box → Generate → **FE-local ghost stream (never autosaved)** →
  `CandidatesView` (diverge→converge rerank) → **Accept** (`onAccept` → editor + provenance mark) → inline
  critic → **`useCorrection` human-gate capture** (edit/regenerate/reject → `POST /jobs/{id}/correction`).
- 🔴 **It carries the ONLY `adapt-from-source` affordance for derivative Works** (`useAdaptFromSource`,
  `canAdapt`/`adaptSourceEmpty`). **It exists on NO other surface.** Retirement **deletes it outright.**
- **Inputs:** `projectId` from `useQualityWork`/`useWork`; `sceneId` **from the studio bus** —
  `host/types.ts:36-37` **already carries `activeSceneId`**; `modelRef` from the shared `ModelPicker`;
  `onAccept` → `ManuscriptUnitProvider.applyProposedEdit(text, ProvenanceAttrs)`.
- 🔴 **The Chat-based `compose` panel is NOT a stand-in for it.**
- 🔴 **If the PO instead rules `ComposeView` superseded by the chat, THAT RULING MUST ALSO NAME A HOME FOR
  `useAdaptFromSource`** — otherwise the ruling silently deletes a shipped capability.

**H-2b · panel id `chapter-assemble`** — leaf-reuse **`ChapterAssembleView`**.
- **Chapter-granularity generation:** single-pass (B2) or **stitch (B3)**, gated on `scenesAllDone`; the
  `assembly_mode` setter; the `CanonGatePanel` result; an **editable preview generated with `persist=false`**
  (**never clobbers the editor draft**); **Accept → `onAccept`**; `useCorrection` human-gate capture →
  `composition.generation_corrected` → learning-service.
- **Inputs:** `projectId` + `bookId` + `chapterId` from the manuscript hoist's active chapter, **using the ONE
  convention spec 31 QC-10 locks** (`QualityCriticPanel.tsx:33-59`'s picker, **including the
  `chaptersTruncated` no-silent-cap notice**); `work.settings` for `assembly_mode`; `scenesAllDone` from
  `useChapterScenes`; `onAccept` → `applyProposedEdit`.
- 🔴 **It is the SECOND producer that spec 30's `G-CORRECTION-FLYWHEEL` row names.** That row says corrections
  are *"written only from the legacy `ComposeView`"* — **which understates it: `ChapterAssembleView` calls
  `useCorrection` too. Wave 1's capture seam is INCOMPLETE while this is homeless.**
- 🔴 **Agent Mode (`authoringRuns/`) is NOT a substitute** — it is an **autonomous multi-chapter runner**, not
  the **interactive stitch-with-human-gate** surface.

🔴 **Wave 6's registration delta moves from `+3` to `+5`.** **Assert `N_before + 5` as a three-way delta —
NEVER a literal.**

### H-3 · `canonview` — **TWO homes, near-zero cost** (`CanonAtChapterPanel`)

It is the **"what does canon KNOW as of chapter N"** inspector: **glossary PRESENCE** and **knowledge
CANON-STATE** for that chapter window, **labelled by source distinctly** (two stores — **they may disagree**),
graded major/appears/mentioned. 🔴 **Do not confuse it with the two canon panels that DO have homes:**
`quality-canon` (shipped) = canon **ISSUES/violations**; `quality-canon-rules` (Wave 1) = canon **RULE
authoring**. **This is neither — it is a read-only canon SNAPSHOT at a chapter boundary.** It is mounted
**two** ways today, and **the second is load-bearing:**

- **(a) 🔴 FOLD IT INTO WAVE 6's M3 (`DivergencePanel`).** Add a file row to M3's table (`:1133-1192`, which
  already ports `DivergenceWizard` + `DivergenceWizardSteps` + `useDivergenceWizard` **VERBATIM**) **plus a
  test that the branch-point step renders the canon-at-branch view.**
  🔴 **If M3's wizard port silently drops it, THE WRITER BRANCHES BLIND.**
- **(b) For the standalone per-scene use, add it as a SECTION inside the existing `scene-inspector` panel** —
  which **already hosts `GroundingPanel`**, the same shape. **No new panel id. No registration-count change.**

### H-4 · What Wave 8 has ALREADY handled (so Wave 6 does not double-build it)

| Legacy sub-tab | Status |
|---|---|
| **cast** | 🟢 **W8-16** — panel `cast` |
| **arc** | 🟢 **W8-17** — panel `character-arc` |
| **flywheel** | 🟢 **W8-18** — panel `canon-growth` |
| **worldmap** | 🟢 **`D-WORLDMAP-PLACE-GRAPH-WONTPORT`** — a **conscious won't-fix by adjudication** (`Q-38-OQ9`), **not** a silent drop. Both capabilities are absorbed by panels Wave 8 ships, **and spec 16 Phase 4b keeps `ChapterEditorPage` indefinitely, so GG-4 deletes nothing.** 🔴 **Wave 6 must NOT re-file it as its own hole** — §5.4 and §8.1 carry it. |
