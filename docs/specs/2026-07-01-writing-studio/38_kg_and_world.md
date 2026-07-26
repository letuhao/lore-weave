# 38 · Outside composition — KG write holes + the World Map

> **Status:** 📐 SPEC (no code this phase — plan 30 **PO-4**) · 2026-07-12 · branch `feat/context-budget-law`
> **Type:** FS · **Size: XL** → **split into two independently-shippable slices**: **8a** (KG write holes — cheap, mostly FE wiring) and **8b** (the `world` container + `world-map` — a **real backend design**, 12 new REST routes, and **UPDATE semantics that exist at no layer today**).
> **Gaps closed:** `G-KG-WRITE-HOLES` (M) · `G-WORLD-MAPS` (L) — plan [`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) §5.3.
> **Wave:** 8 of plan 30. **`G-WORKFLOWS` is DROPPED from this spec** per **PO-2** (Track C owns it — see §0.1). The plan's placeholder filename `38_kg_world_workflows.md` is therefore retired in favour of **`38_kg_and_world.md`**; update plan 30 §11's table row when this lands.
> **Services:** `knowledge-service` (Python) · `book-service` (Go) · `frontend`. `composition-service` is **untouched**.
> Follows [`docs/standards/dockable-gui.md`](../../standards/dockable-gui.md) (DOCK-1..11) · [`docs/standards/mcp-tool-io.md`](../../standards/mcp-tool-io.md) (IN-1..8 / OUT-1..6) · CLAUDE.md **User Boundaries** + **Settings & Configuration Boundary**.
> **Design drafts (mandatory before BUILD, GG-6):** `design-drafts/screens/studio/screen-kg-write-affordances.html` · `design-drafts/screens/studio/screen-world-map.html` — house style per plan 30 §8.3.

---

## 0 · Preamble

### 0.1 What this spec does NOT cover — and whose job it is

**`G-WORKFLOWS` is out of scope by sealed decision (PO-2).** It is **Track C's** to close (its P-5 explicitly claims *"workflow rack, binding UI"*). Recorded here once so it is neither re-raised as a hole nor silently dropped:

> **The defect is real and is live in production today.** `registry_propose_workflow`'s own tool description tells the model that the user approves the proposal *"in the UI"*. **There is no UI.** The public REST surface for workflows is *empty* — LIST, GET-one, DELETE and the enablement toggle do not exist; only `/internal/workflows` does. So an agent that calls `registry_propose_workflow` today writes a row **no human can ever approve, see, or delete**. That is this repo's own `silent-success-is-a-bug-not-environment` class, shipped. Its sibling defect: `mode_bindings` is labelled **in code** as *"a USER setting"* and has no settings surface — a SET-1..8 *write-only-behavior* violation. **Track C: this paragraph is the handoff.** Plan 30's **BE-16** is the backend prerequisite (3–4 new Go routes on `agent-registry`).

### 0.2 Why 8a and 8b are one spec but **two builds**

They share nothing but a wave number. 8a is ~4 FE affordances over engines that already exist and 2 thin REST mirrors. 8b is a **new public API surface for a domain that has never had one**, plus an update semantics design, plus a migration, plus two panels. Sizing them as one XL task hides the fact that **8a is shippable in a day and 8b is not.** They are ordered 8a → 8b and are independently revertable (GG-7).

---

## 1 · Why this exists

### 1.1 G-KG-WRITE-HOLES — the graph the agent can build and you cannot

`knowledge-service` exposes **12 `kg-*` dock panels** (`catalog.ts:153-164`). They read the graph beautifully. **Nothing in them creates a node, creates an edge, seeds the graph, or forgets a fact.** Four concrete holes, each verified against source:

> 🟢 **One thing that IS already human-writable — do not re-raise it, and do not fork it.** `EntityDetailPanel.tsx:623` mounts **`RelationEditDialog`**, which offers **Mark wrong** → `POST /v1/knowledge/relations/{id}/invalidate` (`relations.py:63`) via `useInvalidateRelation`, and **Correct** → `POST /relations/correct`, both through `hooks/useRelationMutations.ts`. `EntityDetailPanel` is mounted in **BOTH** `EntitiesTab` (→ `kg-entities`) **and** `ProjectGraphView` (→ `kg-graph`). So a relation **can** already be deleted and re-predicated by a human — only **creating** one is missing. This has three consequences the design below MUST honour (§3.1 A2).

| # | The hole | Evidence |
|---|---|---|
| **1** | **No entity create in any KG panel.** `knowledgeApi.createEntity` **exists** (`frontend/src/features/knowledge/api.ts:1600`) and `POST /v1/knowledge/entities` **exists** (`services/knowledge-service/app/routers/public/entities.py:999`, 201, `_AUTHORABLE_KINDS = {"character","location","faction","concept"}` at `:975`). Its **only** caller in the whole frontend is `features/composition/hooks/useWorldMap.ts:129` — a component (`features/composition/components/WorldMap.tsx`) that is mounted **only on the legacy `ChapterEditorPage`**. `grep createEntity frontend/src/features/knowledge/**` → **EMPTY**. The route is built, tested, and reachable only from the page spec 16 slates for deletion (**GG-3**: legacy-only ≠ unbuilt; **GG-4**: retiring that page today deletes this). |
| **2** | **No relation create.** Same story: `knowledgeApi.createRelation` (`api.ts:1610`) → `POST /v1/knowledge/relations` (`relations.py:182`, 201 / 409 / 422). One caller: `useWorldMap.ts:134`. Zero callers in `features/knowledge/**`. |
| **3** | **The empty-graph state has no button — and the agent's own error message tells you to press it.** `kg_propose_edge` fails with *"project the glossary entities into the graph first (`kg_project_entities_to_nodes`)"* (`graph_schema_tools.py:1589-1603`). That tool is **MCP-only**: the engine `project_glossary_entities_to_nodes` is fully built and hardened (`app/extraction/anchor_loader.py:194`, returns `{created, existing, seen, skipped, conflicted, truncated}`) and **has no REST route**. A human staring at an empty graph is told to run a tool they cannot run. |
| **4** | **An agent can forget a fact; a human cannot.** `memory_forget` → `_handle_memory_forget` (`app/tools/executor.py:710`) → `invalidate_fact` (`app/db/neo4j_repos/facts.py:675`, a soft `valid_until` set). **No REST mirror.** The deletes the FE *does* have are `DELETE /entities/{id}` (an *entity* archive), `POST /relations/{id}/invalidate` (via `RelationEditDialog`, above) and `deleteFactType` in `useGraphSchema.ts` (a schema fact **type**, not an instance). **The FACT instance is the one object with no human delete.** The facts list a user *reads* every day (`useEntityFacts.ts` → `GET /entities/{id}/facts`, rendered by `EntityDetailPanel.tsx:135`) has **no row action**. |

And one defect the audit called "a dead delete", which is actually **three dead buttons**:

> `OverviewSection.tsx:56` declares `const noop = () => {}` and passes it as `onArchive` / `onRestore` / `onDelete` (`:67-69`). `ProjectRow.tsx:293-314` renders all three buttons **unconditionally**. So in the shipped `kg-overview` panel (and on the classic `ProjectDetailShell`) the user can click **Archive**, **Restore** and **Delete** on their knowledge project and **nothing happens, with no error**. The in-file comment ("destructive CRUD lives with the list") explains the *intent* — but a button that renders and cannot act is the `silent-success-is-a-bug` class in its purest form.

### 1.2 G-WORLD-MAPS — a complete CRUD domain with **zero** public REST

`book-service` ships **8 world-map MCP tools** (`internal/api/mcp_maps.go:465-515`: `world_map_create` / `_list` / `_get` / `_delete` / `_add_marker` / `_remove_marker` / `_add_region` / `_remove_region`), over **3 real tables** (`internal/migrate/migrate.go:401-434`: `world_maps`, `map_markers`, `map_regions`), with owner-scoping, CASCADE cleanup, MinIO blob handling and an existence-oracle-free error model. It is **good code**. A human cannot touch any of it.

Three facts, each verified:

1. **The public REST surface for maps is ZERO routes.** `server.go:381-391` mounts `/v1/worlds` with create/list/get/patch/delete + books-membership. **No `/maps` anywhere.**
2. **The one map route is unreachable from a browser BY CONSTRUCTION.** `POST /internal/worlds/maps/{map_id}/image` (`server.go:200`) sits inside `r.Route("/internal", …)` behind `r.Use(s.requireInternalToken)` (`:185-186`) and takes the identity from a **`?user_id` query param** (`maps_image.go:35`). The gateway proxies `/v1/worlds*` only (`gateway-setup.ts:86-90`) — `/internal` is not public, and no service anywhere calls it: `grep -rn "worlds/maps" services/ frontend/src` (excluding book-service's own handler) → **zero hits.** **The route is dead on arrival.**
3. 🔴 **UPDATE does not exist at ANY layer.** The tool set is **add/remove-only**. There is no `world_map_update_*`, no `PATCH`, no repo method. **Renaming a map, dragging a pin, or reshaping a region has no implementation.** The degenerate workaround — delete + recreate — is unacceptable for four separate reasons, spelled out in §3.3.

**And there is a name collision that will mislead the next agent**, so it is stated up front:

| "World map" | What it actually is | Where |
|---|---|---|
| **`world_maps` / `map_markers` / `map_regions`** *(this spec)* | a **drawn map**: a base image with pins at relative `[0,1]` coords + polygon regions, world-scoped, owner-scoped | `book-service` (Go) |
| **`composition_work.settings.world_map`** | a **place graph**: node positions + a backdrop URL for a React-Flow canvas over *knowledge* entities | `composition-service` → `useWorldMap.ts` (legacy page) |
| the KG subgraph | the graph itself | `knowledge-service` (Neo4j) |

They are three different things. Plan 30 §10 already refuted *"`useWorldMap.ts` is book-service's world maps"* — **do not re-raise it.** The one live connection between them: **`useWorldMap.ts` is the only human writer of `knowledgeApi.createEntity`** (hole #1 above), which is why 8a and 8b appear in the same wave at all.

---

## 2 · What is already built (be precise — this is what makes the estimate trustworthy)

### 2.1 knowledge-service — already built, only unreachable

| Capability | Status | Source |
|---|---|---|
| `POST /v1/knowledge/entities` (create, 201, idempotent on `(name, kind)` per project, `source_type='manual'`, `provenance='human_authored'`, confidence 1.0) | ✅ **EXISTS** | `routers/public/entities.py:999-1032` |
| `POST /v1/knowledge/relations` (create, 201 · 409 if an endpoint isn't the caller's · 422 self-loop · idempotent on `(user, subject, predicate, object)`) | ✅ **EXISTS** | `routers/public/relations.py:182-218` |
| `GET /v1/knowledge/entities` (list, project/kind/search filters) · `GET /entities/{id}` · `GET /entities/{id}/facts` · `PATCH /entities/{id}` (strict If-Match, 428 without, 412 + current body on mismatch) | ✅ **EXISTS + FE-consumed** | `entities.py:277 / 582 / 631 / 1035`; `useEntityFacts.ts`, `EntityDetailPanel.tsx` |
| `POST /v1/knowledge/relations/{id}/invalidate` (soft-invalidate an edge) · `POST /relations/correct` (re-predicate) | ✅ **EXISTS + FE-consumed** — `RelationEditDialog` ("Mark wrong" / "Correct") via `useRelationMutations.ts`, mounted at `EntityDetailPanel.tsx:623` ⇒ **live in `kg-entities` AND `kg-graph`**. ⚠ Its predicate field is a **free-text `<input>`** — §3.1 A2 closes that. | `relations.py:63 / 106` |
| `project_glossary_entities_to_nodes(...)` engine — idempotent, per-row error tolerant, returns `created / existing / seen / skipped / **conflicted** / truncated` (⚠ the **tool** re-spells these on the wire — §3.1 A3) | ✅ **ENGINE EXISTS** · ❌ no REST | `extraction/anchor_loader.py:194-265` |
| `invalidate_fact(...)` — owner-keyed soft invalidate (`valid_until`) | ✅ **ENGINE EXISTS** · ❌ no REST | `db/neo4j_repos/facts.py:675` |
| Lane-B effect handler for `kg_*` writes | ✅ **ALREADY COVERS the two "missing" tools** — see §7.2 (a **refutation of an X-4 sub-claim**) | `studio/agent/handlers/knowledgeEffects.ts:18` |

**KG entities live in Neo4j, not Postgres.** Both the create route and every read route open a `neo4j_session()` (`entities.py:26, 162, 388, 474, 559, 611`). The two-layer pattern still holds — the *anchored* nodes carry `glossary_entity_id` (written by the projection path); a **manually created node carries no anchor**. That is a design fact with a UI consequence (§3.1.A1).

### 2.2 book-service — the map engine exists, the door does not

| Capability | Status |
|---|---|
| Tables + indexes + CASCADE (`world_maps` → markers/regions; `worlds` → maps) | ✅ `migrate.go:401-434` |
| Ownership resolution + uniform not-found (no enumeration oracle) | ✅ `mcp_maps.go:31-54` (`mapOwnerID`, `requireMapOwner`) |
| Create / list / get(+markers+regions) / delete / add-marker / remove-marker / add-region / remove-region — **all the SQL, all the validation** (coords in `[0,1]`, polygon ≥3 points, sub-query failures are TOOL FAILURES not empty results) | ✅ `mcp_maps.go:93-462` |
| Resolved `image_url` from `image_object_key` | ✅ `withImageURL` (`:83`) |
| Multipart image upload → MinIO + pixel-dim decode + orphan sweep | ✅ `maps_image.go` — but **internal-only + `?user_id`** (§1.2) |
| Public REST · UPDATE (any object) · a `version` column · a GUI | ❌ **NONE** |
| Gateway wiring | ✅ **zero changes needed** — `worldsProxy` forwards every `/v1/worlds*` path (`gateway-setup.ts:86-90, 592`); multipart through the gateway is already proven by `booksApi.uploadChapterMedia` |

### 2.3 frontend — the world domain has pages, the studio has no host

`features/world/**` ships `WorldsBrowser`, `LivingWorldTree`, `WorldRollupGraph`, `WorldTimelineSection`, `WorldLorePanel`, `AddBookToWorldModal`, `useWorlds` / `useWorld` / `useBookWorldLink` / `useWorldSubgraph`, and `worldsApi` (list/get/create/books/link/unlink/**bible entities**). Routed at `/worlds` and `/worlds/:worldId` (`App.tsx:190-191`).

**None of it is a dock panel**, and `studioLinks.ts` has **no `/worlds` mapping** (`PATH_PANELS`, `:45-66`) — so `resolveStudioLink('/worlds/…')` falls through to `{ kind: 'external' }` (`:113`). Today `KgOverviewPanel`'s own "World" backlink (`KgOverviewPanel.tsx:44`) therefore **pops a new browser tab out of the studio.** That is why **the `world` container panel is a prerequisite for `world-map`, not a nice-to-have**: without it, every path into a map is a route hop, i.e. DOCK-7.

---

## 3 · The design

### 3.1 Slice 8a — four write affordances on **existing** panels. **No new panel id.**

DOCK-2 (no fork) and DOCK-8 (no new hub) both hold: every affordance below lands **inside a panel that already exists**, on the component that already renders the read.

#### A1 · Create entity — `kg-entities` (`EntitiesTab`)

- **Trigger:** a `+ New entity` button in `EntitiesTab`'s header, **disabled with an explanatory tooltip when `scopedProjectId` is absent** (a create needs a project; the global cross-project browse has none).
- **Form:** `name` (text, required, ≤200) · `kind` (**a `<select>`, never a free text**).
- **The closed set is BE-owned and must not be duplicated by hand.** `_AUTHORABLE_KINDS` (`entities.py:975`) is the source of truth; the FE reads it from **BE-14c** (`GET /v1/knowledge/entity-kinds`). A hard-coded FE array is exactly the cross-service drift the Frontend-Tool-Contract discipline exists to kill.
- **Write:** `POST /v1/knowledge/entities` → 201. Idempotent: re-creating `(name, kind)` in the same project returns the existing node — the UI says *"already exists — opened it"*, it does **not** claim a create (the `silent-success` rule cuts both ways).
- **States:** empty (no project → `KgNoProjectState`) · submitting · 422 (blank name / kind not in the set — surface the BE message verbatim) · 401 · network error (retry, never a fake success).
- 🔴 **The anchor warning — this must be IN the UI, not just in this spec.** A manually created node has **no `glossary_entity_id`**. It will never join to the glossary layer, and it can *shadow* a glossary entity of the same name that a later projection tries to anchor. The form therefore carries a one-line note + a link: *"Authoring lore? Create it in the **glossary** and press **Seed from glossary** (A3) — that keeps the node anchored. Use this form only for graph-only nodes."* (This is the `kg-glossary-fk-is-globally-unique` bug class, prevented at the point of authoring.)

#### A2 · Create relation — `kg-graph` (`ProjectGraphView`)

- **Trigger:** a `Link entities` button on the graph panel's toolbar; pre-fills `subject` from the currently selected node.
- 🔴 **DO NOT FORK `RelationEditDialog` (DOCK-2).** A relation dialog **already ships** (`components/RelationEditDialog.tsx`, mounted at `EntityDetailPanel.tsx:623`) with **Correct** (re-predicate) + **Mark wrong** (invalidate) over `hooks/useRelationMutations.ts`. **A2 is the missing THIRD verb on that same object.** Implement it by adding a `create` mode to `RelationEditDialog` + a `useCreateRelation` mutation in `useRelationMutations.ts` — one dialog, one hook, three verbs. A second, near-identical "new relation" dialog is a fork and a review finding.
- **Form:** subject (entity picker, scoped to this project) · **predicate (a `<select>` fed from `useGraphSchema().schema.edge_types[].code`** — the resolved project schema the `kg-schema` panel already reads; a free-text predicate would mint an off-ontology edge type) · object (entity picker).
- 🔴 **The predicate control must be UNIFIED across all three verbs, or A2's `<select>` is theatre.** `RelationEditDialog`'s **existing** Correct field is a **free-text `<input maxLength={100}>`** (`RelationEditDialog.tsx:127-134`) — so shipping A2 with a `<select>` beside it leaves *create* closed-set and *correct* free-string **on the same object, in the same dialog**. That split-brain is the exact IN-* violation BE-14d exists to kill. **Convert the Correct field to the same control in this slice** (it is a one-component change and needs zero backend).
- **Write:** `POST /v1/knowledge/relations` → 201. Human-authored ⇒ `confidence 1.0`, `pending_validation false` (`recreate_relation`).
- **States:** 409 *"subject or object entity not found for this user"* → render as *"one of those entities isn't yours"* (no oracle) · 422 self-loop (disable Save when subject === object; the BE guard stays as defense) · optimistic edge added to the canvas **only after** the 201 · 🔴 **EMPTY ONTOLOGY** — a project may have **no adopted schema** (`POST /projects/{id}/schema/blank` exists; adoption is optional — `ontology.py:516, 543`), so `schema.edge_types` can be `[]`. A `<select>` with zero options is a **dead form with no error** — the same silent-no-op class this spec is hunting. Render instead: *"this project has no ontology yet — adopt or create a schema first"* with `host.openPanel('kg-schema')`. **Do NOT fall back to free text here** (that re-opens the split-brain above); the escape hatch is the schema panel.
- **Delete is NOT a hole:** an edge created here is removable via the same dialog's existing **Mark wrong** (§1.1). Nothing new to build — but the `kg-graph` canvas must expose the dialog from an **edge** right-click too, or an edge drawn on the canvas can only be undone from `kg-entities`.
- **This bypasses the triage/propose spine on purpose.** `kg_propose_edge` exists for the *agent* (it proposes; a human confirms). A human writing their own edge **is** the confirmation. Say it here so a reviewer does not "fix" the human path into the proposal queue.

#### A3 · Seed the graph from the glossary — the empty-state CTA

- **Surface:** the **primary** CTA of the empty-graph state in **`kg-graph`** and in **`kg-overview`**'s stats card when `entity_count == 0`. Also available (secondary) from `kg-schema`.
- **Write:** **BE-14a** — `POST /v1/knowledge/projects/{project_id}/project-entities`, body `{ entity_ids?: string[] }` (omit ⇒ the whole active glossary), a REST mirror of `kg_project_entities_to_nodes`.
- 🔴 **THE WIRE NAMES — pinned once, here, and nowhere else.** Three different spellings of these six counters exist in the codebase and it is a live cross-service-normalization trap: the **engine dataclass** (`ProjectionResult`) uses `created/existing/seen/skipped/conflicted/truncated`; the **MCP tool** (`graph_schema_tools.py:1681-1707`) re-maps them to `nodes_created / nodes_existing / entities_seen / skipped`, and **only adds `truncated` / `nodes_conflicted` / `note` WHEN THEY ARE TRUTHY** (a conditional key — an FE that reads `res.conflicted` gets `undefined` and renders nothing). **BE-14a's response is the tool's shape, with every key ALWAYS PRESENT:**
  ```
  200 { nodes_created: int, nodes_existing: int, entities_seen: int,
        skipped: int, nodes_conflicted: int, truncated: bool, note?: string }
  ```
  The route **must not** forward the tool's conditional dict verbatim — it must zero-fill `nodes_conflicted` and default `truncated:false`. The FE renders keys, never branches on their existence.
- **The response must be rendered in full.** The counters exist so a partial projection can *explain itself* (the counting was hardened by `D-KG-GLOSSARY-FK-GLOBAL-UNIQUE`, 2026-07-10). A toast that shows only *"Created N"* re-introduces the bug they were added to expose. Render:
  - `nodes_created` + `nodes_existing` — the success line;
  - `nodes_conflicted > 0` — a **warning** row: *"N entities are already anchored by another knowledge project for this book"*;
  - `truncated` — *"the glossary read hit its page cap; more entities remain — run it again"*;
  - `skipped > 0` — a muted line with the count.
- **States:** idle · running (the projection is synchronous and can take seconds on a large glossary → a disabled button + a spinner, **not** a job) · partial (above) · error · `entities_seen == 0` → *"this book's glossary is empty — add entities there first"* with a deep-link to the `glossary` panel (`host.openPanel('glossary')`) · 🔴 **project not linked to a book** — the engine needs a `book_id` and the tool hard-fails with *"this project isn't linked to a book, so it has no glossary entities to project"* (`graph_schema_tools.py:1643-1647`). BE-14a resolves `book_id` via `projects_repo.project_meta(project_id)` and must surface the **same** message as a **409**, not a 500. Hide the CTA entirely when the project has no `book_id`.
- **No cost gate.** This is deterministic, LLM-free, and idempotent. Do **not** route it through propose→confirm (that spine is for paid Tier-W actions).

#### A4 · Forget a fact — a row action on the facts list

- **Surface:** a `⋯ → Forget` action on each row of the entity facts list rendered by **`EntityDetailPanel`** (`:135`, `useEntityFacts(open ? entityId : null)`). Because `EntityDetailPanel` is mounted by **both** `EntitiesTab` (→ `kg-entities`) **and** `ProjectGraphView` (→ `kg-graph`), **one edit lights the action up in two panels.**
- 🔴 **NOT `kg-bio`.** `kg-bio` (`KgGlobalBioPanel` → `GlobalBioTab`) renders the user's **global bio *summary*** — one long text blob over `useSummaries` (`GlobalBioTab.tsx:7,29`). It has **no facts list, no fact rows, and does not import `useEntityFacts`.** There is nothing there to hang a row action on. *(An earlier draft of this spec named `kg-bio`; that was wrong. Recorded so it is not re-added.)*
- **Write:** **BE-14b** — `POST /v1/knowledge/facts/{fact_id}/invalidate` → `{ invalidated: bool, fact_id }`, a REST mirror of `memory_forget` (soft: sets `valid_until`, keeps audit history).
- **Confirm first** (it removes the fact from every future L2 context load) and **be honest in the copy**: *"Forgetting hides this fact from future context. It is not deleted from history — but **there is no un-forget button** (see OQ-5)."*
- **States:** confirming · in-flight · `{invalidated:false, reason:"no matching fact found"}` → the row is stale ⇒ refetch, show *"already gone"* — **never** report success · error.
- ⚠ **Do not wire this to `POST /pending-facts/{id}/reject`** (the pre-commit triage queue) or to `/internal/admin/…/reject-fact`. Different objects, different lifecycles.

#### A5 · Kill the three dead buttons

Two changes, and the second is the one that matters:

1. **Wire them.** `OverviewSection` already mounts `useProjects(false)` for `createProject` / `updateProject` (`:42`); take `archiveProject` / `deleteProject` from the same hook and pass the real handlers, with `ProjectsBrowser`'s existing confirm dialogs.
   🔴 **There is NO `restoreProject`.** `useProjects` exposes exactly `createProject / updateProject / archiveProject / deleteProject` (`useProjects.ts:144-147`). **Restore is an OCC PATCH**, not a mutation of its own: `ProjectsBrowser.tsx:142-150` does `updateProject({ projectId, payload: { is_archived: false }, expectedVersion: project.version })` — and the `expectedVersion` is **load-bearing** (`D-K8-03`: without it a stale "Show archived" snapshot silently wins over an edit from another device; the BE returns **428** with no If-Match, **412** on a stale one). **Reuse that exact call**, including the version, and handle the 412 by resetting the baseline from the response body. Do **not** invent a `restoreProject`, and do **not** drop the version to make it simpler.
2. 🔴 **Make the props optional in `ProjectRow` and render nothing when a handler is absent.** `onArchive?` / `onRestore?` / `onDelete?`. A button whose handler is a no-op must not exist. Ship it with a vitest that renders `ProjectRow` without `onDelete` and asserts `queryByTitle('projects.card.delete')` is `null` — otherwise the next `noop` re-creates the defect silently (this repo's `checklist-is-self-report-enforce-by-tests` law).

---

### 3.2 Slice 8b, part 1 — the `world` container panel (a **prerequisite**, not a feature)

**Panel id: `world`. Category: `storyBible`. Palette-visible. `guideBodyKey` required.**
*(Deliberately **not** a new `world` category: `CATEGORY_ORDER` is already missing `'quality'` — plan 30 **X-2** — and adding a category before that lands sorts the new group **to the top of the palette** via `indexOf → -1`. Reuse an existing member.)*

**It resolves its own scope — so it is openable by a BARE ID** (this is the answer to plan 30's **X-12**: rather than making the panel `hiddenFromPalette` because it "needs a `world_id`", make it *self-resolving*, exactly as `kg-overview` resolves the book's KG project via `useBookKnowledgeProject`):

> `world` = **the world this book belongs to.** The book row carries `world_id` (`useProjectBacklinks` / `useBookWorldLink` both rely on it). No param needed ⇒ it goes into the `ui_open_studio_panel` enum, the Command Palette, and the User Guide.

**Content (a launcher, per DOCK-8 — it hosts no capability's content):**
- world identity card (name, book count, created);
- member books (the current one marked) — clicking another book's row uses `followStudioLink('/books/{id}/studio')` (a different book = a different studio = correctly external);
- **Maps** — a list of the world's maps (`GET /v1/worlds/{world_id}/maps`) with a thumbnail, name, and marker/region counts; a row opens **`world-map`** with `params.mapId`; a `+ New map` button;
- an "Open the full world workspace" escape hatch (`followStudioLink('/worlds/{id}')` → a new tab; the timeline / rollup-graph / lore sections are **out of scope** and stay on the classic page).

**Every state, rendered:**
| State | What the panel shows |
|---|---|
| loading | skeleton |
| **book is not in a world** | an empty state with a `Link this book to a world` control (world picker + `useBookWorldLink.link`) and a `Create a world` action — **not** a route hop |
| **the book's world is owned by someone else** | 🔴 a real state: worlds have **no collaborators** (`server.go:379-380`), while books do (E0 grants). A collaborator with EDIT on the book will get **404** from every world route. Render *"This book belongs to a world you don't have access to."* — uniform, **no oracle** (do not distinguish missing from foreign) |
| world, no maps | the Maps section's empty state + `+ New map` |
| error / 503 | an error card with retry |

**`studioLinks.ts` gains one mapping — and it is NOT one line.** The rule we want is: `/worlds/{worldId}` → `openPanel('world')` **only when `worldId` is this book's world**; any other id stays `external`. 🔴 **That is not implementable against today's signature.** `resolveStudioLink` is a **pure, synchronous** function (no React, no fetch — by design, `studioLinks.ts:1-11`) and its `StudioLinkContext` carries **only `{ bookId, titleFor? }`** (`:19-24`). It has no way to *learn* the book's world. So the change is three files, all of which must be in the checklist:

1. **`studioLinks.ts`** — add `worldId?: string` to `StudioLinkContext`; add `const WORLD_RE = /^\/worlds\/([^/]+)(?:\/|$)/`; resolve to `openPanel('world')` **only** when `ctx.worldId && id === ctx.worldId`. **When `ctx.worldId` is absent, fall through to `external`** — i.e. today's behaviour exactly, so no caller that doesn't know the world id regresses (degrade-safe, never a silent no-op).
2. **`KgOverviewPanel.tsx:44`** — the call site that *already has* the world id and currently throws it away: `onOpenWorld={(worldId) => followStudioLink('/worlds/'+worldId, host, { bookId: host.bookId })}`. Pass `{ bookId: host.bookId, worldId }` — the id it is about to navigate to **is** the book's world (it came from `useProjectBacklinks`, which reads it off the book row). This is the line that fixes today's pop-a-tab papercut; without it the new rule is dead code.
3. **`host/__tests__/studioLinks.test.ts`** — a case for each branch: matching world ⇒ `studio`; a *different* world id ⇒ `external`; **`worldId` absent from ctx ⇒ `external`** (the degrade path — this is the one a builder will forget).

⚠ **Do not "mirror the `/knowledge/projects/:id` rule" — there isn't one.** `studioLinks.ts:51-57` is a **comment explaining why those routes are deliberately NOT mapped** (an arbitrary `:id` from a link may not be this book's project). It is the *reasoning* to copy, not a rule.

---

### 3.3 Slice 8b, part 2 — `world-map`, and **the UPDATE semantics that do not exist**

**Panel id: `world-map`. Category: `storyBible`. Palette-visible** (params **optional**: `{ mapId? }` — with no param it resolves the book's world and selects the most recent map).

🔴 **"It always lands somewhere real" is FALSE, and the DoD depends on it.** §9.4 has the agent call `ui_open_studio_panel {panel_id:"world-map"}` **bare**. Three resolutions produce nothing to select, and **each must be a rendered state, not a blank panel** (a blank panel after a `shown:true` is the silent-success class this whole plan exists to kill):

| Bare-open resolution | What `world-map` renders |
|---|---|
| the book is **in no world** | the same *"Link this book to a world"* empty state as the `world` panel (reuse the component, don't fork it) — **not** an empty rail |
| the world is **foreign** (owner-only, §3.2) | the uniform *"This book belongs to a world you don't have access to."* card |
| the world has **no maps** | the Maps empty state + a primary `+ New map` CTA, focused |
| `mapId` given but **404** (deleted / not yours) | drop the param, fall back to the rail, and say *"that map is gone"* — **never** silently show a different map as if it were the requested one |

**Layout** (draft: `screen-world-map.html`):
```
┌ WORLD MAP ─────────────────────────────────────────────────────────────┐
│ [maps rail 200px] │ [canvas — flex:1]              │ [inspector 300px] │
│  Bản đồ Bắc Vực   │   base image (image_url)       │  MARKER           │
│  山海圖  ● 12 ▲3  │   + pins  (x,y ∈ [0,1])        │  label  [____]    │
│  + New map        │   + regions (svg polygons)     │  type   [city ▾]  │
│                   │   zoom / pan / fit             │  entity [Ironhold]│
│                   │                                │  x .412  y .688   │
│                   │                                │  [Delete]         │
└────────────────────────────────────────────────────────────────────────┘
```
- **Reads:** `GET /v1/worlds/{world_id}/maps` (rail) · `GET /v1/worlds/maps/{map_id}` (canvas — map + markers + regions in one round-trip, mirroring `world_map_get`).
- **Writes:** create map · rename map · delete map · upload/replace base image · add/move/edit/delete a marker · add/reshape/edit/delete a region.
- **Coords are relative `[0,1]`** — the canvas converts on render, and every write clamps. Never store pixels (the base image can be replaced at a different resolution; that is *why* the schema is relative — `migrate.go:418`).
- **The entity link is a GLOSSARY entity id, not a knowledge one.** `map_markers.entity_id` / `map_regions.entity_id` are **soft cross-service UUIDs into glossary-service** (`migrate.go:416, 429` — "soft cross-service ref → glossary location entity"). The picker's source is the **world's bible book** `location` entities first (the FE already authors those: `worldsApi.createBibleEntity`), then each member book's glossary. It must accept **no link** (the column is nullable). ⚠ Getting this wrong by wiring the *knowledge* entity picker would create a dangling id that nothing validates — the FK is soft **by design**.

#### 3.3.1 🔴 The UPDATE design (this is the load-bearing part of the spec)

**Today: add + remove only, at every layer.** The naive fallback — *delete and recreate* — is **rejected**, for four reasons, each concrete:

1. **It churns ids.** A marker id is the handle for its inspector selection, its deep link, and (once §7.3's update tools land) the agent's undo hint. Recreating on every drag invalidates all three.
2. **It is not atomic.** DELETE succeeds, POST fails (network blip) ⇒ **the user's pin is gone**. There is no transaction across two HTTP calls.
3. **It is a write storm.** A drag is a *continuous* gesture. Delete+create per drop is 2 writes; per drag-frame it is unbounded.
4. **It destroys ordering.** Both children sort by `created_at` (`mcp_maps.go:280, 303`), so a "move" would silently jump the pin to the end of the render order.

**Therefore: real PATCH routes, with partial semantics.**

| Object | Route | Body | Semantics |
|---|---|---|---|
| map | `PATCH /v1/worlds/maps/{map_id}` | `{ name? }` | **If-Match OCC** (see below) |
| marker | `PATCH /v1/worlds/maps/{map_id}/markers/{marker_id}` | `{ label?, x?, y?, marker_type?, entity_id? }` | **partial**: an absent key = unchanged; an explicit **`null`** on `entity_id` / `marker_type` = **clear**. No OCC. |
| region | `PATCH /v1/worlds/maps/{map_id}/regions/{region_id}` | `{ name?, polygon?, entity_id? }` | same; `polygon` is replace-whole (≥3 points, each in `[0,1]`) |

**Concurrency, decided deliberately — not by reflex:**

- **`world_maps` gets `version INT NOT NULL DEFAULT 1`**, bumped on every PATCH, and **rename requires `If-Match`** (428 without it, 412 + the current row on mismatch — the same contract knowledge-service's entity PATCH already uses, `entities.py:1035`). A rename is rare, human-paced and conflict-worthy: a 412 that says *"renamed on another device"* is the right answer.
- **Markers and regions get NO version and NO If-Match.** A positional write is a **drag**. OCC over a drag produces a 412 storm and, per this repo's own `instant-commit-control-over-occ-entity-needs-write-serialization` lesson, self-conflicts on the *second rapid edit of the same object*. Positional updates are **last-write-wins**, and the FE **serializes writes per object id** (chain the next PATCH off the previous one's promise; a debounced save **must capture which marker it is saving** — `debounced-write-must-bind-its-target-entity`). Both tables gain `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()` for observability.
- **A PATCH against a deleted marker returns 404** ⇒ the FE drops its optimistic pin and refetches. It must **not** re-create it.

**Scope gating on every child route** — the trap this repo has already been bitten by (`gate-must-derive-scope-from-the-loaded-row`): the handler must verify **both** `world_maps.owner_user_id == caller` **and** `marker.map_id == {map_id}`. A marker id from *another* map, addressed under *your* map id, must **404** — not patch. Express it in SQL exactly as the existing deletes do (`mcp_maps.go:432`: `DELETE … USING world_maps wm WHERE m.id=$1 AND m.map_id=wm.id AND wm.owner_user_id=$2`) — `UPDATE … FROM world_maps wm WHERE …`, and treat `RowsAffected() == 0` as the uniform not-found.

#### 3.3.2 The base image

- **BE-15f — a PUBLIC upload route:** `POST /v1/worlds/maps/{map_id}/image` (multipart `file`), identity from the **JWT** (`requireUserID`), owner-scoped. Implementation = extract `uploadWorldMapImage`'s body into a handler that takes a `userID uuid.UUID`, and mount it twice (public: JWT; internal: `?user_id`). **The internal route has zero callers repo-wide** — see §10 OQ-3: retire it in the same slice unless a caller turns up.
- **States:** no image (a dropzone over the empty canvas — markers can still exist, since the row is authored independently of the blob) · uploading (progress) · 413 too large · 415 unsupported type (png/jpg/gif/webp only — `maps_image.go`) · replace (the old object is swept server-side).
- ⚠ **WebP stores NULL pixel dims** (no stdlib decoder — `maps_image.go:16-19`). Harmless (coords are relative) but the inspector must not render `image_w × image_h` as *"0 × 0"*.

#### 3.3.3 Interaction + scale

- **Drag a pin** → optimistic move + a **serialized, debounced** PATCH. **The E2E must drive this with CDP mouse events** (`page.mouse`), not `browser_drag` — this repo's `playwright-cdp-mouse-drives-d3-drag` lesson.
- **Draw a region** → click-to-add-vertex, double-click/Enter to close (≥3 points), Esc to cancel. Reshape = drag a vertex → PATCH `polygon` whole.
- **Click empty canvas with the pin tool armed** → add a marker at that point (POST), then focus its label field.
- **Scale:** a map with a few hundred pins renders as absolutely-positioned divs over the image; above ~500 markers, cull to the viewport. Regions render as one `<svg>` with one `<path>` per region. No virtualization needed at expected scale — say so rather than over-engineering.

---

## 4 · Backend prerequisites — **this section is a contract**

**Legend:** `EXISTS` = reachable from a browser today · `MUST-BUILD` = does not exist at the named layer.

### 4.1 knowledge-service (slice 8a)

| # | Route | Request | Response | Errors | Status | Size |
|---|---|---|---|---|---|---|
| — | `POST /v1/knowledge/entities` | `{project_id, name, kind}` | `201 Entity` | 401 · 422 (blank name; `kind` ∉ `_AUTHORABLE_KINDS`) | **EXISTS** (`entities.py:999`) | — |
| — | `POST /v1/knowledge/relations` | `{subject_id, predicate, object_id}` | `201 Relation` | 401 · 409 (endpoint not the caller's) · 422 (self-loop) | **EXISTS** (`relations.py:182`) | — |
| **BE-14a** | `POST /v1/knowledge/projects/{project_id}/project-entities` | `{entity_ids?: string[] (≤1000)}` | `200 {nodes_created, nodes_existing, entities_seen, skipped, nodes_conflicted, truncated, note?}` — **every key always present** (§3.1 A3: the tool omits `nodes_conflicted`/`truncated` when falsy; the route must zero-fill) | 401 · 404 (project not accessible — uniform) · **409** (project has no `book_id` ⇒ nothing to project — the tool's own hard-fail, `graph_schema_tools.py:1643`) · 503 (glossary unreachable ⇒ the engine's all-zero degrade; surface it as *"couldn't read the glossary"*, **not** as *"nothing to project"*) | **MUST-BUILD** — a thin router over `project_glossary_entities_to_nodes` (`anchor_loader.py:194`). 🔴 **Two things the "thin" hides:** (1) the engine takes a **`book_id`**, which the route does not have — resolve it with `projects_repo.project_meta(project_id)`, exactly as the tool does (`:1639-1647`); (2) **gate with `Depends(require_project_grant(GrantLevel.EDIT))`, NOT the raw JWT** — see the note below. | **S** |
| **BE-14b** | `POST /v1/knowledge/facts/{fact_id}/invalidate` | `{}` | `200 {invalidated: bool, fact_id}` | 401 · owner-keyed miss ⇒ `{invalidated:false, reason:"no matching fact found"}` (**200, not 404** — mirror the tool exactly) | **MUST-BUILD** — a thin router over `invalidate_fact` (`facts.py:675`). Owner-keyed by `user_id` (no project in scope) ⇒ the raw JWT **is** correct here; this one has no grant path, and the tool doesn't either (`executor.py:713-716`). | **S** |
| **BE-14c** | `GET /v1/knowledge/entity-kinds` | — | `200 {kinds: ["character","concept","faction","location"]}` | 401 | **MUST-BUILD** — serves `_AUTHORABLE_KINDS` so the FE `<select>` has **one home** for the closed set instead of a hand-copied array. ⚠ **A System-tier, read-only, admin-owned constant** — there is no per-user tier and **no write route** (CLAUDE.md User Boundaries). ⚠ **Name collision:** glossary-service *also* has `entity_kinds`, and those are **per-user/per-book and user-editable** (CLAUDE.md's canonical tenancy bug). Different objects. The `/v1/knowledge/` prefix keeps them apart — do not "unify" them. | **XS** |
| **BE-14d** | 🔴 **Unify the authorable-kind set across transports** | — | — | — | **MUST-BUILD** — `kg_create_node`'s `kind` is a **free string** (`graph_schema_tools.py`, `KgCreateNodeArgs.kind: str, max_length=100`) while REST enforces a 4-value set. **The agent can mint a `kind:"item"` node the human cannot.** Hoist one `AUTHORABLE_ENTITY_KINDS` constant; make `KgCreateNodeArgs.kind` a `Literal[...]` over it and have the REST validator + BE-14c read the same constant. *(A closed-set arg that is a free string is the exact IN-* violation `panel_id` was fixed for.)* | **S** |

🔴 **BE-14a's gate is a GG-2 inverse gap in the making.** `kg_project_entities_to_nodes` runs under `_resolve_project_owner(ctx, GrantLevel.EDIT)` (`graph_schema_tools.py:1638`) — so **a collaborator with EDIT can seed the owner's graph through the agent.** If BE-14a is gated on the raw JWT (`get_current_user`) instead, the **GUI is strictly weaker than the tool**: the same person can do it by asking the LLM and cannot do it by pressing the button. That is precisely the asymmetry §6.3 exists to close, created *by this wave*. knowledge-service already ships the dependency — `require_project_grant(GrantLevel.X)` from `app.auth.grant_deps`, used by `ontology.py:468`, `extraction.py:335+`, `drawers.py:152`. **Use `GrantLevel.EDIT`, matching the tool.** *(This is the same residual plan 30 §10 recorded for `kg_create_node`; do not repeat it on a NEW route.)*

### 4.2 book-service (slice 8b) — **12 routes, not the 8–10 the audit estimated**

All under the existing `worldsProxy` prefix ⇒ **zero gateway changes.** All owner-scoped from the JWT. All errors uniform: **404** for foreign-or-missing (no enumeration oracle), mirroring `requireMapOwner`.

| # | METHOD + path | Request | Response | Errors | Status |
|---|---|---|---|---|---|
| **BE-15a** | `POST /v1/worlds/{world_id}/maps` | `{name, image_ref?}` | `201 {map}` | 401 · 404 (world not yours) · 422 (blank name) | MUST-BUILD |
| **BE-15b** | `GET /v1/worlds/{world_id}/maps` | — | `200 {maps: [{map_id, world_id, name, image_object_key, image_url, marker_count, region_count, version, updated_at}]}` | 401 · 404 | MUST-BUILD *(counts are new — a `LEFT JOIN … GROUP BY`; the rail needs them and a per-map GET-storm is not acceptable)* |
| **BE-15c** | `GET /v1/worlds/maps/{map_id}` | — | `200 {map, markers[], regions[]}` (the `world_map_get` shape, **plus `updated_at` on every marker and region** — see the migration note) | 401 · 404 | MUST-BUILD |
| **BE-15d** | `PATCH /v1/worlds/maps/{map_id}` | `{name?}` + **`If-Match: <version>`** | `200 {map}` | 401 · 404 · **428** (no If-Match) · **412** (+ the current map as body) | MUST-BUILD 🔴 **new semantics** |
| **BE-15e** | `DELETE /v1/worlds/maps/{map_id}` | — | `204` | 401 · 404 | MUST-BUILD *(CASCADE + best-effort blob sweep — lift `toolWorldMapDelete`)* |
| **BE-15f** | `POST /v1/worlds/maps/{map_id}/image` | multipart `file` | `200 {image_object_key, image_url, image_w, image_h}` | 401 · 404 · 413 · 415 · 503 (no MinIO) | MUST-BUILD *(a **public** sibling of the dead internal route — §3.3.2)* |
| **BE-15g** | `POST /v1/worlds/maps/{map_id}/markers` | `{label, x, y, marker_type?, entity_id?}` | `201 {marker}` | 401 · 404 · 422 (coords ∉ [0,1]) | MUST-BUILD |
| **BE-15h** | `PATCH /v1/worlds/maps/{map_id}/markers/{marker_id}` | `{label?, x?, y?, marker_type?, entity_id?}` (absent = unchanged · `null` = clear) | `200 {marker}` | 401 · **404** (foreign map **or** marker not on this map) · 422 | MUST-BUILD 🔴 **new semantics** |
| **BE-15i** | `DELETE /v1/worlds/maps/{map_id}/markers/{marker_id}` | — | `204` | 401 · 404 | MUST-BUILD |
| **BE-15j** | `POST /v1/worlds/maps/{map_id}/regions` | `{name, polygon, entity_id?}` | `201 {region}` | 401 · 404 · 422 (<3 points; a point ∉ [0,1]) | MUST-BUILD |
| **BE-15k** | `PATCH /v1/worlds/maps/{map_id}/regions/{region_id}` | `{name?, polygon?, entity_id?}` | `200 {region}` | 401 · 404 · 422 | MUST-BUILD 🔴 **new semantics** |
| **BE-15l** | `DELETE /v1/worlds/maps/{map_id}/regions/{region_id}` | — | `204` | 401 · 404 | MUST-BUILD |

**Migration (book-service, `migrate.go`, forward-only + idempotent — the house pattern):**
```sql
ALTER TABLE world_maps  ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1;
ALTER TABLE map_markers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE map_regions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
```
⚠ `ADD COLUMN IF NOT EXISTS` **never revisits a bad default on an already-migrated DB** (`add-column-if-not-exists-never-revisits-a-bad-default`) — get the defaults right the first time.
*(`world_maps` **already** carries `updated_at` — `migrate.go:409`. Only `version` is new there. The two child tables have `created_at` only.)*

🔴 **`updated_at` must be READ, or it is a column this spec ships write-only.** "For observability" is not a consumer — a stored-but-unread field is the exact bug class CLAUDE.md bans, and a `PATCH` that never bumps it is a bug no test would catch. Therefore, in the same slice: **(a)** every PATCH handler sets `updated_at = now()`; **(b)** BE-15c returns it on each marker/region; **(c)** the `world-map` inspector renders it (*"edited 4m ago"*) — which is also what makes the drag-PATCH **visible as having landed** rather than merely repainted. A Go test asserts the timestamp **advances** across a PATCH.

**BE-15m — 3 new MCP tools (agent parity, GG-2):** `world_map_update` (rename) · `world_map_update_marker` · `world_map_update_region`, Tier-A, reversible (the inverse patch with the prior values; state it in the description as the existing tools do). **Without these, 8b creates a NEW inverse gap: the human could move a pin and the agent could not.** Size **S** (mirror the REST handlers; the SQL is the same). ⚠ Go MCP tool args carry `jsonschema` tags — `marker_type` stays free-form (it is), but any closed set added later must be an enum.

---

## 5 · Registration checklist (GG-8) — exact files, in order

**Two new panel ids: `world`, `world-map`.** Machine-guard state at HEAD `9262ed53e`: **py enum 57 == contract enum 57 == openable 57, zero drift** (`contracts/frontend-tools.contract.json` → `/ui_open_studio_panel/args/panel_id`, 57 entries; `frontend_tools.py:402`). This wave moves all three by **+2, in lockstep**.

⚠ **Assert the DELTA and the three-way equality — never the literal `59`.** This is **Wave 8, the LAST wave**: Waves 1–6 land **12** panels before it (`quality-canon-rules`, `quality-corrections`, `quality-heal`, `progress`, `arc-inspector`, `motif-library`, `quality-conformance`, `arc-templates`, `plan-passes`, `style-voice`, `reference-shelf`, `divergence`), so the baseline here is **69**, not 57, and the end state is **71**. A DoD pinned to `59 == 59 == 59` sends the next builder hunting a phantom regression. (Wave 7 / [`37`](37_issues_feed.md) adds **no** panel — it wires the existing bottom panel and a lens.)

| # | File | Edit |
|---|---|---|
| 1 | `frontend/src/features/studio/panels/WorldPanel.tsx` | new — root `data-testid="studio-world-panel"` |
| 1b | `frontend/src/features/studio/panels/WorldMapPanel.tsx` | new — root `data-testid="studio-world-map-panel"`; `useStudioPanel('world-map', props.api, { mcpToolPrefixes: ['world_'] })` |
| 2 | `frontend/src/features/studio/panels/catalog.ts` | two `STUDIO_PANELS` rows: `{ id:'world', component:WorldPanel, titleKey:'panels.world.title', descKey:'panels.world.desc', category:'storyBible', guideBodyKey:'panels.world.guideBody' }` and the same shape for `world-map`. **`category` and `guideBodyKey` are both mandatory** (X-2 / X-3 assertions). **Do not add a new category.** |
| 3 | `frontend/src/i18n/locales/en/studio.json` | `panels.world.{title,desc,guideBody}` + `panels.world-map.{title,desc,guideBody}` |
| 4 | `frontend/src/i18n/locales/{ar,bn,de,es,fr,hi,id,ja,ko,ms,pt-BR,ru,th,tr,vi,zh-CN,zh-TW}/studio.json` | same 6 keys × 17 locales — **`python scripts/i18n_translate.py`**, never hand-write |
| 5 | `services/chat-service/app/services/frontend_tools.py` | **two edits** in `UI_OPEN_STUDIO_PANEL_TOOL`: (a) append `"world"`, `"world-map"` to the `panel_id` **enum** (`:402`); (b) append their clauses to the tool **description** prose (`:403+`) — that gloss is the model's only hint. Suggested: *"'world' = the world this book belongs to (member books + its maps); 'world-map' = a drawn world map — pins and regions on a base image."* |
| 6 | `contracts/frontend-tools.contract.json` | **NEVER hand-edit — regenerate:** `cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py`; commit the regenerated JSON **in the same commit** as steps 2 + 5 |
| 7 | `frontend/src/features/studio/host/studioLinks.ts` | **(a)** add `worldId?: string` to **`StudioLinkContext`** (`:19-24` — today it is `{bookId, titleFor?}` and the resolver is a **pure sync fn**, so it *cannot* look the world up); **(b)** add the `/worlds/{worldId}` rule → `openPanel('world')` **only when `ctx.worldId === worldId`**; **(c)** `ctx.worldId` absent ⇒ `external` (today's behaviour — degrade-safe, no regression for callers that don't know it). See §3.2. |
| 7b | `frontend/src/features/studio/panels/KgOverviewPanel.tsx` (`:44`) | **Mandatory, not optional** — `onOpenWorld` currently calls `followStudioLink('/worlds/'+worldId, host, { bookId: host.bookId })` and **throws the world id away**. Pass `{ bookId: host.bookId, worldId }`. **Without this line, step 7's rule is dead code and the papercut it claims to fix is still there.** |
| 7c | `frontend/src/features/studio/host/__tests__/studioLinks.test.ts` | three cases: matching world ⇒ `studio` · a different world id ⇒ `external` · **`worldId` absent ⇒ `external`** (the degrade path a builder forgets). |
| 8 | `frontend/src/features/studio/agent/handlers/worldEffects.ts` (**new**) + `useStudioEffectReconciler.ts` | `registerEffectHandler(/^world_(map_)?(create|delete|update|rename|add_marker|remove_marker|update_marker|add_region|remove_region|update_region|move_book)/, worldEffect)` → invalidate `['world-maps']`, `['world-map-detail']`, `['worlds']`, `['world-books']`. Register it in the reconciler's `useEffect` alongside the other four. **Reads (`world_map_get` / `_list` / `world_get` / `world_list`) must NOT match** — a chatty read loop would thrash the cache. |
| 8b | `frontend/src/features/studio/agent/handlers/knowledgeEffects.ts` | add `registerEffectHandler(/^memory_(remember|forget)$/, knowledgeEffect)` — `KNOWLEDGE_WRITE_PATTERN` is `/^kg_(?!…)/` and **cannot match `memory_forget`** |
| 9 | tours | **skip** — neither panel is a role-tour step |

🔴 **A THIRD machine guard the plan's GG-8 checklist does not name — and both new panels walk straight into it.** `frontend/src/features/studio/panels/__tests__/dockablePanelHygiene.test.ts` **recursively scans every `.tsx` under `panels/**`** and reds on:
- **DOCK-7** — any `useNavigate(`, `useParams<|(`, or `<Link`. The `world` panel's *"Open the full world workspace"* escape hatch is exactly the shape a builder writes as `<Link to="/worlds/{id}">`. **It must be `followStudioLink(...)`** (which `window.open`s a new tab), never a `<Link>`.
- **DOCK-9** — a hand-rolled viewport overlay (`fixed` + `inset-0` as *tokens*, not adjacent — the regex is token-based on purpose). The world picker, the *Create a world* form, the `+ New map` form, the marker/region delete confirms and the image dropzone are **five** dialog surfaces across the two panels. **All must go through `@/components/shared` (`FormDialog` / `ConfirmDialog`) or Radix directly** — the test exempts those two imports and nothing else.

**Verify (all six green; the first two are the drift-locks, the third is the DOCK gate):**
```
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
cd frontend && npx vitest run \
  src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
  src/features/studio/panels/__tests__/dockablePanelHygiene.test.ts \
  src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
  src/features/studio/palette/__tests__/useStudioCommands.test.ts \
  src/features/studio/host/__tests__/studioLinks.test.ts \
  src/features/chat/nav/__tests__/frontendToolContract.test.ts
```
Then **verify by EFFECT** (§9) — a green unit suite has repeatedly hidden *"the FE could not actually execute it."*

---

## 6 · Agent surface

### 6.1 Which tools drive these domains

| Domain | Tools | Transport |
|---|---|---|
| KG nodes/edges | `kg_create_node` · `kg_propose_edge` · `kg_project_entities_to_nodes` · `kg_graph_query` · `kg_schema_read` … (`graph_schema_tools.py:466-495`) | MCP (knowledge-service) |
| Facts | `memory_remember` · `memory_forget` · `memory_search` · `memory_recall_entity` · `memory_timeline` (`executor.py:_HANDLERS`) | MCP |
| Maps | the 8 `world_map_*` tools + the 3 new update tools (BE-15m) | MCP (book-service; the `world_` prefix is book's second federated namespace via `EXTRA_PREFIX_MAP` — `config.ts:128`, `book: ['world_']`. The namespacing law is already satisfied.) |
| **Worlds (the container)** | **`world_create` · `world_get` · `world_list` · `world_move_book`** (`internal/api/**mcp_worlds.go**` — a *different file* from `mcp_maps.go`; **12 `world_*` tools exist in total, not 8**) | MCP (book-service, same `world_` namespace). **These already exist** ⇒ the `world` container panel ships with **full agent parity on day one** — every capability §3.2 gives the human (create a world, list it, read it, link this book into one) the agent already has. **No new container tools are needed.** *(Omitted from an earlier draft of this table, which made the container look agent-less and invited someone to "close" a gap that isn't there.)* |

### 6.2 Lane-B effect handlers (plan 30 **X-4**) — with one **REFUTATION**

🟢 **X-4's claim that `kg_create_node` has no Lane-B handler is REFUTED.** `KNOWLEDGE_WRITE_PATTERN = /^kg_(?!project_list|graph_query|world_query|multi_query|entity_edge_timeline|schema_read|list_templates|sync_available|view_read|triage_list)/` (`knowledgeEffects.ts:18`) is a **negative-lookahead over the whole `kg_` namespace** — so `kg_create_node` **and** `kg_project_entities_to_nodes` already match and already invalidate `['knowledge-entities']`, `['knowledge-subgraph']`, et al. **Do not add a handler for them. Do not "fix" the pattern.**

Genuinely missing, and this spec adds them:
- `memory_forget` / `memory_remember` — outside `^kg_` (checklist 8b);
- `world_map_*` / `world_*` — no handler at all (checklist 8).

### 6.3 Inverse gaps (GG-2) — the agent can do what the human cannot

| # | Asymmetry | Resolution in this spec |
|---|---|---|
| 1 | **Agent can create an entity of ANY `kind`; the human is capped at 4** (`KgCreateNodeArgs.kind: str` vs `_AUTHORABLE_KINDS`) | **BE-14d** — one shared constant, `Literal` on the tool, served by BE-14c. One name, one home. |
| 2 | **Agent can forget a fact; the human cannot** | **BE-14b** |
| 3 | **Agent can seed the graph from the glossary; the human cannot** | **BE-14a** |
| 4 | **After 8b: the human could move a pin and the agent could not** — a *new* inverse gap this wave would otherwise create | **BE-15m** (3 update tools), **in the same slice** |
| 5 | Agent *proposes* an edge (`kg_propose_edge` → triage); the human *writes* one directly (`POST /relations`) | **Not a defect — by design.** A human writing their own edge **is** the confirmation. Recorded so a reviewer does not route the human path into the proposal queue. |
| 6 | 🔴 **Agent can seed the graph as a COLLABORATOR; the human would not be able to** — `kg_project_entities_to_nodes` runs under `_resolve_project_owner(ctx, GrantLevel.EDIT)`, so an EDIT-grantee can project into the owner's graph. A BE-14a gated on the raw JWT would make the button weaker than the sentence. | **BE-14a MUST use `require_project_grant(GrantLevel.EDIT)`** (§4.1). A *new* inverse gap this wave would otherwise create, in the opposite direction from #1–#4. |
| 7 | 🟢 **Worlds: no gap.** `world_create` / `world_get` / `world_list` / `world_move_book` already exist and the `world` panel gives the human the same four. | Nothing to build. Recorded so the container is not "closed" with tools it already has. |

---

## 7 · Tenancy · settings · OCC · cost gates

**Tenancy (CLAUDE.md User Boundaries) — no new tables, so the tiers are inherited and must be honoured:**

| Object | Tier | Scope key | Enforcement |
|---|---|---|---|
| `world_maps` | **Per-user** (worlds have **no collaborators** — `server.go:379-380`) | `owner_user_id` | every query filters it; `requireMapOwner` returns a uniform not-found |
| `map_markers` / `map_regions` | **Per-user, by inheritance** — they carry **no owner column** | `map_id` FK → `world_maps.owner_user_id` | **every child route JOINs to `world_maps` and filters the owner** (§3.3.1). A child route that trusts a bare `marker_id` is a tenancy defect. |
| KG `:Entity` / `:Fact` / relations (Neo4j) | **Per-user** | `user_id` on the node, `project_id` a tag | `merge_entity` / `recreate_relation` / `invalidate_fact` are all owner-keyed; a cross-user id simply doesn't match (→ 409 / "no matching fact"), **never an oracle** |
| knowledge `project` | **Per-user**, book-linked | `owner_user_id` + `book_id` | unchanged |

🔴 **The one live tenancy consequence:** a *book collaborator* (E0 grant) is **not** a world member. The `world` panel must render the "no access" state (§3.2) rather than loop on 404s. **This is not a bug to fix by widening the world routes** — worlds are owner-only on purpose.

**Settings (SET-1..8): this wave adds NO setting.** No toggle, no mode, no threshold, no model choice. Canvas zoom/pan and the selected map id are **per-device UI state** → dock panel `params` / component state, never `localStorage` user data and never a server preference. *(If a later reviewer wants a "default map" per world, that is a per-user setting with a scope key — not an env flag, and not in this spec.)*

**OCC:**
- knowledge entity `PATCH` already enforces strict If-Match (**428** without, **412** + the current entity as the body). Panels that edit an entity must **reset their baseline from the 412 body** — never re-GET, never retry blindly.
- map **rename** gets If-Match (BE-15d) → on 412 the rail shows *"renamed on another device"* + the current name; the user re-applies.
- marker/region positional writes are **LWW by design**, with FE per-id write serialization (§3.3.1). This is a decision, not an omission — it is written here so a reviewer does not "add OCC" and re-create the 412-storm.

**Cost gates: none.** Nothing in this wave spends an LLM token. Entity/relation create, glossary projection, fact invalidation, and every map write are deterministic. **Do not route any of them through `GET /v1/composition/actions/preview` → `POST /actions/confirm`**, and above all **do not invent a per-action estimate route** — plan 30 §3.3 documents three such invented routes that **404 in production today**.

---

## 8 · Milestones

| # | Slice | Scope | Size | DoD |
|---|---|---|---|---|
| **M8a.1** | KG — FE **+ the closed-set pair** | A1 create entity · A2 create relation (a **third verb on the existing `RelationEditDialog`**, + convert its Correct field to the same schema-fed `<select>`) · A5 the three dead buttons (wire — **restore is `updateProject{is_archived:false}` + `expectedVersion`, there is no `restoreProject`** — + make the props optional + the "no handler ⇒ no button" vitest) · **BE-14c + BE-14d** | **M** | vitest + knowledge pytest green; **live browser**: create an entity in `kg-entities`, see it in `kg-graph` after one refetch; click Delete in `kg-overview` and see a real confirm dialog |
| **M8a.2** | KG — BE + FE | BE-14a/b + A3 the seed-from-glossary CTA + A4 the forget-fact row action (on `EntityDetailPanel` — **not `kg-bio`**) + the `memory_*` Lane-B registration | **M** | pytest green (knowledge-service, `-n auto --dist loadgroup`); **cross-service live-smoke**: project a real book's glossary into an empty graph through the gateway and see `nodes_conflicted`/`truncated` rendered |

> 🔴 **Why BE-14c/BE-14d moved into M8a.1** (they were in M8a.2, and that ordering was **broken**): A1's `kind` control is specced — correctly — to read the closed set from **BE-14c**, because a hand-copied FE array is the cross-service drift the Frontend-Tool-Contract discipline exists to kill (§3.1 A1). Shipping A1 one milestone *before* the route it reads leaves M8a.1 with exactly two options, and **both are the bug**: hard-code the array, or ship a `<select>` with no options. BE-14c is **XS** and BE-14d is **S** — pulling them forward costs almost nothing and removes the only way M8a.1 could ship a lie. **M8a.1 is therefore M, not S.**
| **M8b.0** | **GATE — not code** | Written ownership handoff with **Track C** for the `world` container (its P-5 claims "W10 world container") | — | a decision recorded in `docs/sessions/SESSION_HANDOFF.md`. **BUILD does not start without it.** |
| **M8b.1** | Maps — backend | BE-15a…l (12 routes) + the migration + BE-15m (3 update tools) + retire/repoint the dead internal image route | **M** | Go tests incl. the **scope-gate tests** (a marker from another map under your map id ⇒ 404; a foreign map ⇒ 404, identical body); a curl smoke **through the gateway** (`:3123`) for every route |
| **M8b.2** | `world` container panel | the panel + GG-8 registration + the `studioLinks` rule | **M** | contract tests green (**enum 58 == contract 58 == openable 58** at this point); **live browser**: `ui_open_studio_panel {panel_id:"world"}` mounts the dock tab; the not-in-a-world empty state links a book to a world |
| **M8b.3** | `world-map` panel | rail + canvas + inspector + image upload + entity picker + Lane-B `worldEffects` | **L** | all three counts **+2 in lockstep** (delta, not a literal — §Registration); the live smoke in §9 |

---

## 9 · Definition of Done

1. **Every route in §4 exists and is reachable through the gateway** (`:3123`), not just from a unit test.
2. **Machine guards green with zero drift:** `panelCatalogContract.test.ts` (**openable == enum, both `N_before + 2`** — assert the delta, never a literal; both new panels carry `category` ∈ `CATEGORY_ORDER` **and** a `guideBodyKey`) · `test_frontend_tools_contract.py` (the regenerated `contracts/frontend-tools.contract.json` committed **in the same commit** as `catalog.ts` + `frontend_tools.py`).
3. **Unit suites green:** knowledge-service pytest (`-n auto --dist loadgroup`), book-service `go test ./...`, frontend vitest.
4. 🔴 **LIVE BROWSER SMOKE — mandatory, and it is the DoD, not a formality.** This repo's `agent-gui-loop-needs-live-browser-smoke-not-raw-stream` law exists because a green unit suite has repeatedly hidden *"the FE could not actually execute it."* Two new Playwright specs under `frontend/tests/e2e/specs/` (siblings of `studio-compose.spec.ts` / `studio-palette.spec.ts`), run against the **baked** frontend (`:5174` is nginx — a host `vite dev` SHADOWs it; rebuild the image or use `:5199`), with the `claude-test@loreweave.dev` account:
   - **`studio-kg-write.spec.ts`** — open `kg-entities` → create an entity → assert it appears in the list **after a refetch, not from optimistic state** → open `kg-graph` → link it to another entity → **reload the page** and assert both survived → **Mark wrong** on that edge and assert it is gone (the create/delete round-trip, §3.1 A2). Then: seed-from-glossary on an empty project and assert the **counts** are rendered by their **wire names** (`nodes_created` / `nodes_existing` / `entities_seen` / `skipped` / `nodes_conflicted` / `truncated` — §3.1 A3; a spec that renders `created` gets `undefined`).
   - **`studio-world-map.spec.ts`** — open `world` via the Command Palette → create a map → upload a base image → **place a pin** → **drag it with `page.mouse` (CDP-trusted events — `browser_drag`/synthetic events do NOT drive a canvas drag)** → **reload** → assert the pin is at the new coords (this is the only thing that proves the PATCH landed and did not just repaint optimistic state) → rename the map in a second tab and assert the first tab's rename gets a **412** with the current name.
   - **The agent leg, in the browser:** a chat turn that calls `ui_open_studio_panel {panel_id:"world-map"}` **mounts the dock tab** (per plan 30 §8: *"a green unit suite does not prove the loop closed"*). Same for `panel_id:"world"`.
   - 🔴 **The bare-open degraded leg — do NOT skip it.** Run `ui_open_studio_panel {panel_id:"world-map"}` **on a book that is in NO world** and assert the panel renders the *"Link this book to a world"* state (§3.3). A blank panel behind a `shown:true` is a **silent success**, and this is the one path the happy-path smoke above will never touch.
5. **Cross-service live-smoke token in the VERIFY evidence** (this wave touches ≥2 services: `book-service` + `knowledge-service` + `frontend`) — `live smoke: <one-liner>`, per CLAUDE.md Phase 6.
6. **Two design drafts on disk** (GG-6) in the house style (plan 30 §8.3): banner comment with **BACKEND WORK IMPLIED** stated up front, **every claimed state rendered** (including the *Before* — the three dead buttons, the empty map with no route — with `.strike` on the unreachable fields), realistic multilingual content.
7. **Deferred rows filed** for everything in §10 that is not built.
8. **SESSION_HANDOFF updated** in the same commit as the code (work not recorded does not exist).

---

## 10 · Open questions / Deferred

| # | Question | Status |
|---|---|---|
| **OQ-1** | 🔴 **Track C owns "W10 world container" in its P-5.** This spec designs one. **Who builds it?** | **BLOCKING for 8b** (M8b.0). 8a is unaffected and can ship today. |
| **OQ-2** | The marker/region entity picker's source. `map_markers.entity_id` is a **glossary** entity (soft cross-service UUID). A world has many books; glossary entities are per-book. This spec proposes: **the world's bible book first** (`worldsApi.createBibleEntity` + `getInternalWorldBible` prove the world-bible exists), then member books. **I have not read the world-bible entity model end to end.** | **UNVERIFIED** — verify before M8b.3. If the bible model doesn't hold, fall back to "the current book's glossary `location` entities" and note the limitation in the UI. |
| **OQ-3** | `POST /internal/worlds/maps/{map_id}/image` has **zero callers** — `grep -rn "worlds/maps"` across `services/` + `frontend/src` (excluding book-service's own handler) returns nothing. Retire it, or keep it for a future BFF-mediated upload? | Recommend **retire** in M8b.1 once BE-15f lands (a dead internal route is a maintenance liability + an audit false-positive). Verify once more before deleting. |
| **OQ-4** | **No un-forget.** `invalidate_fact` sets `valid_until`; nothing clears it. A mis-clicked Forget is unrecoverable through any surface. | **Deferred → `D-KG-FACT-RESTORE`** (gate #2: it needs a new engine fn + route + tool; a confirm dialog is the v1 mitigation, and the copy must **say** it is one-way). |
| **OQ-5** | A manually created KG node has **no `glossary_entity_id`** and can shadow a glossary entity a later projection tries to anchor (`conflicted`). The v1 mitigation is the UI warning in A1. | Should `POST /entities` optionally accept a `glossary_entity_id` and anchor on create? Real, and **out of scope** (gate #2 — it touches the `entity_glossary_fk_unique` constraint). **Deferred → `D-KG-MANUAL-NODE-ANCHOR`.** |
| **OQ-6** | The `predicate` on `POST /relations` **and** on `POST /relations/correct` is a **free string** (`max_length=100`) — and **a free-text predicate `<input>` is ALREADY SHIPPED in the GUI**: `RelationEditDialog.tsx:127-134`, live in `kg-entities` + `kg-graph` today. So the closed-set breach is not hypothetical; it is in production. | **Split, deliberately.** The **FE half is FIXED IN THIS SLICE** (§3.1 A2: both create *and* correct use the schema-fed `<select>`; zero backend). The **BE half stays open** — an agent or a curl can still mint an off-ontology edge, and widening the ontology check is a knowledge-service design call. **Deferred → `D-KG-RELATION-PREDICATE-UNCONSTRAINED` (BE only).** |
| **OQ-10** | The `kg-graph` canvas gets edge **create** (A2) but the only edge **delete** is inside `EntityDetailPanel`'s relation row (Mark wrong). An edge drawn on the canvas is therefore removable only from the entity detail, not from the canvas. | v1: expose the existing `RelationEditDialog` from an **edge right-click** on the canvas (zero backend, one wiring). If that slips, say so in the UI — do not ship draw-with-no-erase. |
| **OQ-7** | `marker_type` is a free string with no vocabulary anywhere (`'city'`, `'landmark'` appear only in a tool description). The inspector will need *some* set. | v1: a `<select>` with a small FE vocabulary **plus a free-text escape** — and say plainly in the spec's own draft that this is **not** a closed set until the BE owns one. **Deferred → `D-WORLD-MARKER-TYPE-VOCAB`.** |
| **OQ-8** | WebP base images store **NULL** pixel dims (no stdlib decoder — `maps_image.go:16-19`). Harmless for relative coords; the inspector must not render `0 × 0`. | Noted, not a blocker. |
| **OQ-9** | This wave does **not** port `features/composition/components/WorldMap.tsx` (the legacy place-graph). It stays on `ChapterEditorPage` — and it is the **only** human writer of `createEntity`/`createRelation` today. **After M8a.1 the KG panels own that capability**, which is what unblocks GG-4 for this component specifically. | Recorded. Whether the place-graph *itself* is worth a Studio panel is a separate question (it belongs to plan 30's Wave 6 editor-craft ports, not here). |
