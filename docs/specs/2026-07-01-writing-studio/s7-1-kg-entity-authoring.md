# S7-1 · KG Entity Authoring — a real Create Entity + Create Relation surface, and the enum that lies three ways

> **Status:** 📐 specced 2026-07-16 · branch `feat/context-budget-law` (studio track) · **S** (files≈6, logic≈4, side_effects=2)
> **Type:** **FS — 95% frontend wiring; ONE small backend reconciliation the CLARIFY missed (§5 BE-1).** The relation-builder and delete legs are pure FE. The *entity-create* leg cannot honour the intended kind vocabulary without a backend gate change — proven below, not hand-waved.
> **Closes:** **S7-A1/A2 view-rich, author-poor** — `docs/plans/2026-07-16-studio-session-S7-RUN-STATE.md` §S7-A1/A2. The KG is 13 view panels + edit + merge with **no human Create**.
> **Draft (UI acceptance target + house style):** `design-drafts/screens/studio/screen-kg-entity-authoring.html`.
> Follows [`docs/standards/mcp-tool-io.md`](../../standards/mcp-tool-io.md) (closed-set arg ⇒ enum) and the Frontend-Tool-Contract discipline in `CLAUDE.md`.

---

## 0 · Corrections to the draft and the CLARIFY — read FIRST (source-verified)

The draft and the ALREADY-RESOLVED CLARIFY each carry a factual error about the code. CLAUDE.md is explicit: *never spec against a doc's claim; open the file.* I did. Three corrections are load-bearing and reshape the type from FE to FS:

1. **"Nothing on the backend blocks a non-`location` kind" is FALSE.** `POST /entities` (`services/knowledge-service/app/routers/public/entities.py:1037`, `create_entity_endpoint`) validates the body through `CreateEntityRequest._validate` (`entities.py:1021-1029`), which **422s any kind outside `_AUTHORABLE_KINDS = {"character","location","faction","concept"}`** (`entities.py:1008`). The World Map only ever sends `kind:'location'` (`useWorldMap.ts:129`), so this gate has never been exercised for another kind — but it is real. **A create form offering the 7 browse-filter kinds silently 422s 4 of them.** (Detail in §2.)

2. **"No entity DELETE client exists in `api.ts`" is FALSE.** `knowledgeApi.archiveMyEntity` (`frontend/src/features/knowledge/api.ts:1426`) already calls `DELETE /v1/knowledge/me/entities/{id}` — the soft-archive route (`entities.py:176`, `user_archive_entity`, reason `user_archived`, preserves edges + the `glossary_entity_id` anchor). It is wired today **only** in `PreferencesSection.tsx:42` (the Global-tab preferences), **not** in `EntitiesTab` / `EntityDetailPanel` / `ProjectGraphView`. The draft routed delete through Merge; that is wrong. **Wire the existing `archiveMyEntity` into the detail panel.** (Detail in §3.4 / §5.)

3. **The kind closed set is not one set — it is THREE disagreeing sets.** Browse filter = **7** (`KIND_OPTIONS`, `EntitiesTab.tsx:24`: `character, location, organization, concept, item, event_ref, preference`). Create gate = **4** (`_AUTHORABLE_KINDS`, uses **`faction`** where the filter says **`organization`**). Agent `kg_create_node` = **free string, no gate at all** (`graph_schema_tools.py:1729`). The draft's create form renders a **fourth**, different 6-set. This drift IS the spec's core problem, not a footnote (§2).

Everything else in the draft — the two ready endpoints, the relation error contract, the "no silent success/failure" law — holds and is re-verified below with file:line.

---

## 1 · Why this exists — the operability gap, with file:line

The knowledge graph is **view-rich, author-poor.** A signed-in human can:

- **browse** entities — `EntitiesTab.tsx` (filters: project/kind/status + FTS + semantic), paginated, → `GET /v1/knowledge/entities` (`api.ts:1505`);
- **read one** — `EntityDetailPanel.tsx` slide-over (metadata, facts, 1-hop relations), → `GET /entities/{id}` (`api.ts:1529`);
- **edit** one — `EntityEditDialog.tsx` (name/kind/aliases, OCC via `If-Match`), → `PATCH /entities/{id}` (`api.ts:1627`);
- **merge** two — `EntityMergeDialog`, → `POST /entities/{id}/merge-into/{other}` (`api.ts:1705`);
- **explore** the graph — `ProjectGraphView.tsx` canvas, → `GET /projects/{id}/subgraph` (`api.ts:1564`).

Every one of those **reads or mutates an entity that already exists.** There is **no Create.** The only paths to a new entity are (a) run extraction over a chapter, or (b) approve an agent proposal. To hand-author a character, a faction, a concept — or a relation that isn't a place-link on the composition World Map — the human is stuck.

And the punchline the draft got right: **the create mechanism already ships.**

```ts
frontend/src/features/knowledge/api.ts:1607  createEntity(payload, token)   → POST /entities   (201)
frontend/src/features/knowledge/api.ts:1617  createRelation(payload, token) → POST /relations  (201)
```

Their **only** human callers are `useWorldMap.ts:129` (`createPlace`, `kind:'location'`) and `:134` (`linkPlaces`). The buttons were never drawn on the KG surface. This spec draws them — and fixes the one place the endpoint is genuinely narrower than the product intent (§5 BE-1).

---

## 2 · What's already built — the reconciliation (be precise)

### 2.1 The two write endpoints (EXIST, proven live by the World Map)

| Client method | Route | Backend | Contract (verified) |
|---|---|---|---|
| `createEntity` (`api.ts:1607`) | `POST /v1/knowledge/entities` | `create_entity_endpoint` (`entities.py:1037`) | Body `{project_id, name, kind}`; 201 → full `Entity`. **`kind` gated to `_AUTHORABLE_KINDS` (4) → 422 otherwise** (`entities.py:1008,1025`). **Idempotent**: `merge_entity` dedups on `(name,kind)` in the project → re-creating returns the **existing** node (`entities.py:1051`, comment `entities.py:1012-1015`). |
| `createRelation` (`api.ts:1617`) | `POST /v1/knowledge/relations` | `create_relation_endpoint` (`relations.py:186`) | Body `{subject_id, object_id, predicate}`; 201 → `Relation`. **`predicate` is a FREE string** `min 1, max 100` (`relations.py:178`) — no closed set on the wire. **422** self-loop (`relations.py:198`); **409** an endpoint isn't the caller's entity (`relations.py:211`). Idempotent on `(user,subject,predicate,object)`. |

### 2.2 The delete/archive endpoint (EXISTS; client EXISTS; unwired on this surface)

| Client method | Route | Backend | Contract (verified) |
|---|---|---|---|
| `archiveMyEntity` (`api.ts:1426`) | `DELETE /v1/knowledge/me/entities/{id}` | `archive_user_entity` (`entities.py:176`) | **Soft archive** via `user_archive_entity(reason="user_archived")` — preserves `RELATES_TO`/`EVIDENCED_BY` edges **and** the `glossary_entity_id` anchor (`entities.py:203-211`). **204** on success, **404** when the id isn't the caller's; both mean "now hidden" (`entities.py:186-192`). **Idempotent** (no `archived_at IS NULL` guard). **No `If-Match`** — a one-way idempotent flag flip, no OCC (contrast the PATCH). Emits an `ENTITY_CORRECTED` `op="delete"` correction (`entities.py:228`). Currently called **only** in `PreferencesSection.tsx:42`. |

⚠ **There is NO restore route wired in the FE.** The archive preserves the anchor *so a future restore can re-show it anchored*, but `api.ts` has no `unarchiveEntity`, and I found no unarchive HTTP route in `entities.py`. Archived rows are *surfaceable* (the `status='archived'` filter, `entities.py:318`) but not *un-archivable* from the GUI. Do not imply otherwise (OQ-4).

### 2.3 The three disagreeing kind sets — the drift this spec must resolve

| Surface | Source | Values | Notes |
|---|---|---|---|
| **Browse filter** | `KIND_OPTIONS`, `EntitiesTab.tsx:24` | `character, location, organization, concept, item, event_ref, preference` (**7**) | The `as const` tuple the FE treats as the vocabulary. Uses **`organization`**. |
| **Create gate** | `_AUTHORABLE_KINDS`, `entities.py:1008` | `character, location, faction, concept` (**4**) | Uses **`faction`**. Rejects `organization`, `item`, `event_ref`, `preference` with **422**. |
| **Agent create** | `KgCreateNodeArgs.kind`, `graph_schema_tools.py:464` → `_handle_kg_create_node`, `:1729` | **any string** (`max 100`, no membership check) | `merge_entity(kind=args.kind.strip())`. The agent can mint `item`, `organization`, `preference`, anything. |
| **Edit dialog** | `EntityEditDialog.tsx:156` | **any string** (free `<input maxLength={100}>`) | The latent drift the draft flagged: `kind:"charcter"` writes silently. |

Overlap across create-gate ∩ filter = only `{character, location, concept}`. The group-kind is named **two ways** (`faction` vs `organization`). **This is the `rest-write-mirror-drops-fields-the-mcp-tool-accepts` bug class in reverse**: the human REST door is *narrower* than the MCP door on the same `merge_entity`, and the browse UI advertises kinds the human create path 422s. A create form built to the draft (or to the FOCUS's "7-value enum") **ships silent 422s** — the exact closed-set / silent-no-op failure the Frontend-Tool-Contract rule exists to kill.

### 2.4 Agent parity + Lane-B (EXISTS — no new handler needed)

- **MCP create:** `kg_create_node` (`server.py:1121` → `graph_schema_tools.py:1715`) mints one `:Entity` under the project OWNER with EDIT grant (`_resolve_project_owner`). MCP-first is satisfied for entity-create; a human GUI create via REST is correct (MCP-first governs *agentic* logic, not user GUI actions).
- **MCP relation:** the agent's edge path is `kg_propose_edge` → triage inbox → confirm (a proposal flow), *not* a direct create — that is by design; the human's direct `createRelation` is the GUI equivalent.
- **Lane-B effect handler EXISTS and already covers create:** `knowledgeEffect` (`knowledgeEffects.ts:21`) invalidates `['knowledge-entities']`, `['knowledge-entity-detail']`, `['knowledge-subgraph']` (+ more), and its match regex `KNOWLEDGE_WRITE_PATTERN` (`:16`) matches `kg_create_node` (not in the read-exclusion list). **So an agent create already refreshes the open `kg-entities`/`kg-graph` panels with no manual reload.** This spec adds **no** new effect handler (§7).

### 2.5 The panels (EXIST — no new panel id)

`kg-entities` (`catalog.ts:180`, `KgEntitiesPanel` → `EntitiesTab`) and `kg-graph` (`catalog.ts:186`, `KgGraphPanel` → `ProjectGraphView`) are **already registered** dock panels, both `category:'knowledge'`, both `mcpToolPrefixes:['kg_']`. The Create surfaces mount **inside** them as dialogs (peers of `EntityEditDialog`/`EntityMergeDialog`). **No new panel id, no `ui_open_studio_panel` enum change, no contract regen** (§6).

---

## 3 · The design (from the draft, corrected to the source)

### 3.1 Create Entity — a dialog on the `kg-entities` toolbar

A `+ New Entity` button in the `EntitiesTab` toolbar (draft §① — the button the draft struck through) opens a `CreateEntityDialog` (peer of `EntityEditDialog`, same `FormDialog` shell). Fields:

- **Name** — required, free text, `maxLength 200` (matches `CreateEntityRequest.name`, `entities.py:1018`). Trim client-side; the server also `.strip()`s (`entities.py:1055`).
- **Kind** — required, **an enum picker over a CLOSED SET rendered as a radio-grid** (the draft's `.kind-grid`), not a free `<select>` and never a free `<input>`. **The set is a single named constant** consumed by the picker (§3.3, DEC-1).
- **Target project** — required `project_id`. Pre-filled + hidden when the panel is route/book-scoped (`KgEntitiesPanel` passes `scopedProjectId`, `EntitiesTab.tsx:49`); a `<select>` over `useProjects()` otherwise (mirror the existing project filter, `EntitiesTab.tsx:120`).
- **Aliases** — optional, one-per-line, applied via a **follow-up `PATCH`** (create takes name-only; `splitAliases` already exists, `EntityEditDialog.tsx:19`). MVP may defer aliases to the edit path entirely — the draft says so and it is fine.

**LOCKED — DEC-2. New entities are `discovered`, never author-chosen.** `merge_entity` writes `source_type='manual'`, `confidence=1.0`, `provenance='human_authored'`, **no `glossary_entity_id`** (`entities.py:1051-1060`), so the **server-derived** `status` is `discovered` (`ENTITY_STATUSES`, `api.ts:386`; derived from `glossary_entity_id + archived_at`, `api.ts:261-267`). The form **never** offers a status control — `canonical` is earned only by anchoring (the existing Promote flow, `EntityDetailPanel.tsx:411`).

### 3.2 Create Relation — a builder on the `kg-graph` canvas

Draft §③. A per-node **"+ link"** affordance on `ProjectGraphView` (hover badge / right-click context menu — drive via the existing `GraphCanvas` node handlers, not a `useEffect`) seeds the **subject** and opens a `CreateRelationDialog`: **subject → predicate → object**.

- **Subject** — seeded from the node the user acted on (or a table row).
- **Predicate** — required, **enum over a curated closed set** (DEC-1), even though the wire accepts a free string (`relations.py:178`). Seed the vocabulary from what already ships: the place-links `contains/borders/route_to` (`useWorldMap.ts:18`) plus the character/faction predicates the draft lists (`ally_of, enemy_of, member_of, mentor_of, parent_of, located_in, owns, part_of`). **This vocabulary is a GUI convention, not a backend constraint — say so in the code comment** so nobody "tightens" `relations.py` to match and breaks the agent's free-form `kg_propose_edge`.
- **Object** — a **typeahead over the project's own entities** (`listEntities({project_id, search})`, keyset/paged — a project subgraph is thousands of nodes; never a render-all `<select>`). Both endpoints must be the caller's entities or the server 409s.

### 3.3 The enum decision — DEC-1 (LOCKED, but its *value* is a PO/backend call)

**Every closed-set arg is an `enum` behind ONE named constant, machine-checked, never a free string.** That is non-negotiable (Frontend-Tool-Contract). What the kind enum's *values* are is the open decision, because the three sets disagree (§2.3). Two honest options:

- **Option A — FE-only, ship the 4 proven-authorable kinds today.** Kind enum = `_AUTHORABLE_KINDS` = `{character, location, faction, concept}`. Zero backend change; zero 422s. **Cost:** the create picker offers 4 kinds while the filter offers 7, and it says `faction` where the filter says `organization` — a visible, confusing mismatch the user will hit immediately (create a "faction", then filter by "organization" and it's absent).
- **Option B — reconcile the backend gate (RECOMMENDED).** Widen/align `_AUTHORABLE_KINDS` to the canonical KG kind vocabulary so **create == filter == agent** (§5 BE-1). Then the picker is the real 7-set and the naming (`faction` vs `organization`) is settled in one place. This is a small backend edit but it makes the type **FS**, not FE.

**🔒 SEALED (PO, 2026-07-16): Option B, and OQ-1 is RESOLVED — B is UNBLOCKED.** The kind enum is the
**5-kind authorable set `{character, location, organization, concept, item}`** (== the authorable subset
of the 7-value browse filter; `event_ref`/`preference` stay out — not user-authorable). BE-1 proceeds:
widen `_AUTHORABLE_KINDS` (`entities.py:1008`) to these 5 **and** fix `faction`→`organization` (CLARIFY
verified extraction emits `{person→character, place→location, organization, artifact→item,
concept→terminology, event}`; **`faction` exists nowhere and zero `faction` rows can exist** — a pure
one-word rename, no migration), **and** gate `KgCreateNodeArgs.kind` (`graph_schema_tools.py:464`) to the
same 5 (closes the free-string agent path, INV-parity). This makes s7-1 type **FS** (a ~2-line
set-membership edit, no new route/schema/migration). **M3 now ships the 5-kind set directly** — the old
"M3 Option A then M-later flip to B" staging is collapsed. Never a free-string kind.

### 3.4 Wire the existing delete (soft-archive) into the detail panel

Add an **Archive** control to `EntityDetailPanel` (a peer of Edit/Merge, `EntityDetailPanel.tsx:255-276`) calling the **existing** `archiveMyEntity(entity.id)`. It is a soft archive (§2.2): confirm with the truth — *"Hide this entity. Its relations and glossary anchor are kept; it disappears from the active list (surface it again via the Archived filter)."* On success, `onOpenChange(false)` and invalidate `['knowledge-entities', userId]` + `['knowledge-entity-detail', userId, id]`. **No OCC** (the route takes none). **No** Merge-as-delete misdirection.

### 3.5 Every state, rendered (draft §④; W0-S16 — no silent success, no silent failure)

| State | Trigger | Render |
|---|---|---|
| **empty (no entities)** | project has none | `EntitiesTab.tsx:249` already shows `entities.empty`; the `+ New Entity` button is the CTA out of it. |
| **create — submitting** | POST in flight | primary button → spinner/`disabled`; dialog stays open. Mirror `EntityEditDialog` `mutation.isPending` (`:131`). |
| **create — success (201, fresh)** | new node | success toast *"Entity created — {name} ({kind})"*; the list re-fetches (Lane-B keys) and the new **discovered** row appears. Graph node appears after `['knowledge-subgraph']` invalidation. |
| **create — success (201, DEDUP hit)** | `(name,kind)` already exists | ⚠ `merge_entity` returns the **existing** node with its real `mention_count`, **not** a fresh 0-mention row (`entities.py:1051`). The toast must **not** claim "created" unconditionally — see OQ-2. The draft's "fresh row, 0 mentions" render is only the true-new case. |
| **create — 422 bad kind** | kind ∉ gate (Option A window, or a stale client) | error toast with the server message. **This state is designed OUT** by the enum (DEC-1) — a 422 here means the enum drifted from the gate and is a contract-test failure, not a user error. |
| **relation — success (201)** | edge created | success toast; the new edge appears on the canvas (subgraph invalidation) + in both endpoints' detail relation lists (`['knowledge-entity-detail']`). |
| **relation — 409 endpoint not yours** | `relations.py:211` | error toast *"Could not create link — an endpoint isn't one of your entities."* + `409`. |
| **relation — 422 self-loop** | `relations.py:198` | error toast *"An entity cannot relate to itself."* + `422`. |
| **archive — success (204/404)** | both = hidden | success toast *"Entity archived."*; list/detail invalidated; panel closes. |
| **edit — OCC 412** | (existing, unchanged) | `EntityEditDialog.tsx:61` already maps 412 → `entities.edit.conflict` toast + close + detail refetch. The new create dialog needs **no** OCC (create has no version). |
| **loading / error (list, detail, graph)** | (existing) | already handled: `entities-loading`/`entities-error` (`EntitiesTab.tsx:230,239`), `entity-detail-loading`/`-error` (`EntityDetailPanel.tsx:333,342`), `project-graph-error`/`-hint` (`ProjectGraphView.tsx:84,95`). |

**No cost gate.** Every action here is deterministic CRUD, $0, no LLM. There is no propose→confirm; adding one would be a defect.

---

## 4 · Backend prerequisites

| # | Route | METHOD + path | Request | Response | Errors | Status |
|---|---|---|---|---|---|---|
| 1 | create entity | `POST /v1/knowledge/entities` | `{project_id, name, kind}` | 201 `Entity` | 422 kind∉gate; 422 blank name | **EXISTS** (`entities.py:1037`) |
| 2 | create relation | `POST /v1/knowledge/relations` | `{subject_id, object_id, predicate}` | 201 `Relation` | 409 endpoint not caller's; 422 self-loop | **EXISTS** (`relations.py:186`) |
| 3 | archive entity | `DELETE /v1/knowledge/me/entities/{id}` | — | 204 (or 404, both=hidden) | — | **EXISTS** (`entities.py:176`); client EXISTS (`api.ts:1426`) |
| 4 | list (typeahead + refresh) | `GET /v1/knowledge/entities?project_id&kind&search` | query | 200 `{entities,total}` | — | **EXISTS** (`entities.py:277`) |
| 5 | subgraph (graph refresh) | `GET /v1/knowledge/projects/{id}/subgraph` | query | 200 `{nodes,edges,node_cap_hit}` | — | **EXISTS** (`entities.py:783`) |
| **BE-1** | **reconcile create kind gate** | modify `_AUTHORABLE_KINDS` (`entities.py:1008`) | — | — | — | **MUST-BUILD if Option B (§3.3)** — widen/align the frozenset to the canonical KG kind vocabulary so create == filter == agent. Also gate `KgCreateNodeArgs.kind` to the same set (`graph_schema_tools.py:464`) to close the free-string agent path (INV-parity). **S.** Blocked on OQ-1. |

**BE-1 is the only backend work, and it is a set-membership edit, not a new route/schema/migration.** If the PO takes Option A, BE-1 drops and the type is FE-only for real.

---

## 5 · Registration checklist (GG-8)

**No new panel id ⇒ the enum==openable==contract three-way is UNTOUCHED.** The surfaces mount inside the already-registered `kg-entities` / `kg-graph` panels (§2.5) as dialogs. Concretely:

| # | File | Change |
|---|---|---|
| 1 | `frontend/src/features/knowledge/components/CreateEntityDialog.tsx` **(new)** | the create form; `data-testid="entity-create-*"`. Kind enum from the ONE constant (DEC-1). |
| 2 | `frontend/src/features/knowledge/components/CreateRelationDialog.tsx` **(new)** | the relation builder; predicate enum from the ONE constant; object typeahead over `listEntities`. |
| 3 | `frontend/src/features/knowledge/hooks/useEntityMutations.ts` | add `useCreateEntity` + `useCreateRelation` (mirror the existing hooks; invalidate `['knowledge-entities', userId]`, `['knowledge-subgraph', projectId]`, and for relations `['knowledge-entity-detail', userId, <both ids>]`). Add `useArchiveEntity` wrapping `archiveMyEntity`. |
| 4 | `frontend/src/features/knowledge/components/EntitiesTab.tsx` | the `+ New Entity` toolbar button → open `CreateEntityDialog`; pass the scoped/selected `project_id`. |
| 5 | `frontend/src/features/knowledge/components/EntityDetailPanel.tsx` | the **Archive** control (§3.4). |
| 6 | `frontend/src/features/knowledge/components/ProjectGraphView.tsx` | the per-node **"+ link"** affordance → open `CreateRelationDialog` seeding the subject. |
| 7 | `frontend/src/features/knowledge/lib/entityKinds.ts` **(new)** | `AUTHORABLE_ENTITY_KINDS` + `RELATION_PREDICATES` as `as const` tuples — **one home** each; the pickers, the enum badge map, and the contract test import from here. Option A seeds it from the 4 gate kinds; Option B from the reconciled 7. |
| 8 | `frontend/src/features/knowledge/components/EntityEditDialog.tsx` | **enum-drift fix (from the draft):** replace the free `<input>` kind (`:156`) with the same enum `<select>` over `AUTHORABLE_ENTITY_KINDS`. Cheap, in-scope, root-cause-clear ⇒ fix-now, not deferred. |
| 9 | `frontend/src/i18n/locales/en/knowledge.json` + `python scripts/i18n_translate.py` | new keys: `entities.create.*`, `relations.create.*`, `entities.archive.*` × 18 locales — **never hand-write** the non-English locales. |
| — | `services/chat-service/app/services/frontend_tools.py`, `contracts/frontend-tools.contract.json`, `studio/panels/catalog.ts`, `host/types.ts` | **NOT TOUCHED** — no new panel id, no bus slice, no `ui_open_studio_panel` enum member. |

---

## 6 · Agent surface / MCP parity

- **Entity create parity:** `kg_create_node` (`server.py:1121`) ✅ — the agent already creates. No new tool.
- **Relation parity:** `kg_propose_edge` (propose→confirm) is the agent's edge path; the human's direct `createRelation` is the GUI equivalent. No new tool.
- **Lane-B handler:** **already exists and already covers `kg_create_node`** (`knowledgeEffects.ts:16-32` invalidates `['knowledge-entities']`/`['knowledge-subgraph']`). **This spec adds NO new effect handler** (contrast the arc-inspector spec, which had to create one). Verify by test that `kg_create_node` matches `KNOWLEDGE_WRITE_PATTERN` (it does — not in the read-exclusion list).
- **INVERSE-gap note (GG-2):** the agent can mint **any** kind (free-string `kg_create_node`), the human REST create cannot (4-kind gate). BE-1 **closes the gap in BOTH directions**: it widens the human gate AND constrains the agent's free string to the same set — so neither door is silently broader (the `rest-write-mirror` lesson, applied symmetrically).

---

## 7 · Compliance — stated, not assumed

**Tenancy (scope key = the JWT `user_id`, Per-user tier — NOT project).** Every entity/relation route MATCHes `WHERE user_id = $user_id` (`entities.py:1043-1047` states it explicitly: *"`project_id` is just a tag on the user's own node, never a cross-tenant handle"*). `project_id` is a **filter tag**, not a scope key: a caller can only ever create/read/archive **their own** nodes; passing another user's `project_id` mints a tag on the caller's own node, it does not reach across tenants. There is no System-tier row here and no shared user-editable row — so no `entity_kinds`-style tenancy trap. `AUTHORABLE_ENTITY_KINDS` is a **client-side display constant** mirroring a server gate, not a shared DB row, so it carries no tenancy risk (SET-6: closed-set values validated on write, here by the enum + the contract test).

**Settings (SET-1..8).** Zero settings, zero toggles, zero env flags. The kind/predicate vocabularies are **closed-set enums**, not user preferences — one home each (§5 #7), consumed by effect (the picker), validated on write (enum). No `*_ENABLED`/`*_MODE` flag.

**OCC (If-Match).** Create and archive carry **no** version and need none (create mints; archive is a one-way idempotent flip — `entities.py:186-192`). The **existing** edit path keeps its `If-Match: W/"N"` OCC (`api.ts:1640`, 428 without / 412 stale → current row in body). This spec does **not** weaken it.

**Cost gate.** None, by construction (§3.5). $0 deterministic CRUD.

---

## 8 · Milestones / slices — each one commit

| # | Slice | DoD evidence string |
|---|---|---|
| **M1** | **Delete wiring (pure FE)** — `useArchiveEntity` + the Archive control in `EntityDetailPanel`, with the honest soft-archive confirm. | `vitest` green: clicking Archive calls `archiveMyEntity(entity.id)`, invalidates list+detail, closes the panel; 404 treated as success. `grep` proves the old Merge-as-delete misdirection is absent. |
| **M2** | **Create Relation (pure FE)** — `entityKinds.ts` predicate enum + `CreateRelationDialog` + the graph "+ link" affordance + `useCreateRelation`. | `vitest` green: 201 refreshes subgraph + both endpoints' detail; **409** → "endpoint isn't yours" toast; **422** → self-loop toast (no silent failure). Predicate is an enum bound to the ONE constant (a contract test asserts membership). |
| **M3** | **Create Entity (Option A, FE-only)** — kind enum = the 4 authorable kinds + `CreateEntityDialog` + `useCreateEntity` + the `+ New Entity` toolbar button + the `EntityEditDialog` free-text→enum fix. | `vitest` green: create posts `{project_id,name,kind}`, new **discovered** row appears; a kind outside the enum is **unreachable in the UI** (no free string); the edit dialog's kind is now an enum. |
| **M4 (Option B — FS, gated on OQ-1)** | **BE-1 reconciliation** — widen `_AUTHORABLE_KINDS` + gate `KgCreateNodeArgs.kind` to the same set; flip `entityKinds.ts` to the reconciled vocabulary. | `pytest` (knowledge-service) green: create accepts each reconciled kind (201) and 422s a bogus one; `kg_create_node` 422s the same bogus kind (parity). Create picker == filter == agent (a test asserts the three sets are equal). |

M1–M3 ship without M4. M4 lands when the PO ratifies the kind vocabulary (OQ-1).

---

## 9 · Definition of Done

1. **Unit/contract suites green** — `frontend` vitest for the 3 dialogs + hooks + the `entityKinds` membership contract test; `knowledge-service` pytest for M4.
2. **The enum is machine-checked both sides.** A test asserts the create/edit kind picker's options === `AUTHORABLE_ENTITY_KINDS` and (M4) that this tuple === the server gate. **No free-string kind survives** anywhere (`EntityEditDialog` `<input>` is gone).
3. **No silent success / no silent failure (W0-S16).** Tests assert: 201 → success toast + a real refreshed row (not an optimistic fabrication); 409/422 → the specific error toast; the dedup-hit path (§3.5) does not claim "created" falsely (OQ-2 resolution).
4. 🔴 **LIVE BROWSER SMOKE — mandatory.** Rebuilt image (`live-smoke-rebuild-stale-images-first`), signed in as `claude-test@loreweave.dev`, on a project with a linked book and a built graph:
   1. open studio → the `kg-entities` panel → **+ New Entity** → create a `character` → the new **discovered** row appears **without a manual reload**;
   2. open the `kg-graph` panel → right-click a node → **+ link** → pick predicate + object → the new edge renders on the canvas;
   3. force **409**: try to link to an id that isn't yours (or a garbage id) → the "endpoint isn't yours" toast fires, no fake success;
   4. open the new entity's detail → **Archive** → it leaves the active list → the **Archived** status filter surfaces it;
   5. **agent leg (parity):** in Compose, have the agent `kg_create_node` a new entity → the open `kg-entities` panel refreshes via the existing Lane-B handler (verify by **EFFECT** — a new row, not a `shown:true` in the raw stream; `agent-gui-loop-needs-live-browser-smoke-not-raw-stream`).
   Drive dockview via `evaluate` + `data-testid` (`playwright-live-dockview-automation-recipe`).
5. **`/review-impl` on the diff** — this touches a tenancy boundary (user-scoped writes) and a closed-set contract; run the adversarial review before COMMIT, fold findings into POST-REVIEW evidence.
6. **SESSION_HANDOFF + the S7 RUN-STATE §S7-A1/A2** updated; OQ-1's disposition recorded.

---

## 10 · Open questions / Deferred

| # | Question | Disposition |
|---|---|---|
| **OQ-1** | What is the **canonical KG entity-kind vocabulary**, and is `faction` (create gate) vs `organization` (browse filter) a rename or two real kinds? The three sets (§2.3) cannot all be right. | **MOSTLY CODE-SETTLED (CLARIFY-SYNTHESIS 2026-07-16) — one narrow PO nuance remains.** Read `entity_resolver.py:69-84` (`_EXTRACTOR_TO_GLOSSARY_KIND`) + its tests (`test_entity_resolver.py:188-204`): the LLM extractor emits **`{person, place, organization, artifact, concept, other}`**, normalized to glossary `kind_code` **`{character, location, organization, item, terminology, event}`** (person→character, place→location, artifact→item, concept→terminology; **`organization` and `event` already ARE the glossary kind_code**). **`faction` appears NOWHERE in extraction or glossary — it exists ONLY in `_AUTHORABLE_KINDS` (`entities.py:1008`).** So `faction` vs `organization` is **NOT two real kinds — it is an isolated misnomer in the create gate; `organization` is canonical.** And **zero `faction` entities can exist**: the only path that accepts `faction` is the create gate, whose only live caller (`useWorldMap.ts:129`) sends `kind:'location'` — so renaming it is a pure fix, no data migration. **`event_ref`/`preference` (browse filter) are NOT hand-authorable content kinds** (timeline-event refs / chat-derived preference entities). **RESOLUTION:** fix `faction`→`organization` in `_AUTHORABLE_KINDS` **now** (one-word fix — shipping `faction` when it exists nowhere else IS the drift this spec kills), so **Option A ships `{character, location, organization, concept}`** (not `faction`). **Option B** (BE-1) widens to add **`item`** → `{character, location, organization, concept, item}` == the authorable subset of the browse filter. **NARROW PO nuance → NEEDS_PO#1:** confirm `item` should be user-hand-authorable and whether Option B is worth doing at all vs shipping the 4-kind Option A permanently. |
| **OQ-2** | `merge_entity` is idempotent: creating an existing `(name,kind)` returns the **existing** node (201), not a fresh one (`entities.py:1051`). The toast/UX can't trivially tell created-from-deduped. | **Small, fixable now.** Either (a) compare the returned node's `created_at`/`mention_count` to detect a dedup hit and toast *"already existed — showing it"*, or (b) diff the returned `id` against the pre-call list. Not a blocker; pick (a) in M3. Do **not** ship a create toast that lies "created" on a dedup. |
| **OQ-3** | The relation predicate is a **free string** on the wire (`relations.py:178`) but the GUI constrains it to an enum. Should the backend enforce the vocabulary too? | **CODE-SETTLED (CLARIFY-SYNTHESIS 2026-07-16) — DEFERRED stands, no PO.** Confirmed `predicate: str = Field(min_length=1, max_length=100)` (`relations.py:178`) — genuinely free-string, no membership check. Tightening it would reject the agent's free-form `kg_propose_edge` predicates AND existing extraction edges. GUI-enum-only is the correct layer; **no backend change, not a PO call.** Row as `D-KG-PREDICATE-VOCAB` only if a second consumer needs server enforcement. (Same fact as s7-4 OQ-2 — one question, resolved once.) |
| **OQ-4** | No **restore/unarchive** route is wired in the FE (§2.2). A GUI-archived entity is surfaceable (Archived filter) but not un-archivable. | **NOT this spec.** The soft-archive preserves the anchor precisely so a restore can exist later; building the unarchive route is buildable (gate #2, small) but out of this slice's scope. Row as `D-KG-ENTITY-RESTORE`. Do not imply a restore button exists. |
| **OQ-5** | The FOCUS asks for a **"7-value enum + FE-only"** create surface. Those two are **mutually exclusive** given `_AUTHORABLE_KINDS` (§2.3). | **RESOLVED by disclosure, not by silence.** 7 kinds ⇒ BE-1 ⇒ FS (Option B). FE-only ⇒ 4 kinds (Option A). The spec ships A now, B on OQ-1. The contradiction is in the premise, surfaced here rather than papered over with a form that 422s. |
