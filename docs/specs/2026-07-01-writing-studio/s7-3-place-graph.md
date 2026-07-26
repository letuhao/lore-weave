# S7-3 · Place Graph — port the ONE operable World/KG surface into a Studio dock panel

> **Status:** 📐 specced 2026-07-16 · branch `feat/context-budget-law` (studio S7 · Knowledge/World/Cast) · **S** (files≈10, logic≈3, side_effects=1 — the frontend-tool contract enum)
> **Type:** **FE — a PORT, not a build. Zero new backend.** Every dependency (create/link/persist/upload) already ships and is proven.
> **Closes:** the S7-A1/A2 audit's one *positive* anomaly inverted — `docs/plans/2026-07-16-studio-session-S7-RUN-STATE.md` §S7-A1/A2: the KG/World/Cast family is *view-rich / author-poor*, and the sole exception (the world-map **place graph**) is **fully operable but unreachable from the dock**. This makes it reachable.
> **Draft (UI acceptance target + house style):** `design-drafts/screens/studio/screen-place-graph.html`.
> **Leaf being ported:** `frontend/src/features/composition/components/WorldMap.tsx` + `frontend/src/features/composition/hooks/useWorldMap.ts`.
> Follows `docs/standards/dockable-gui.md` (DOCK-1..11) and `docs/standards/mcp-tool-io.md`.
> ⚠ **NOT s7-2's world-map editor.** This is `work.settings.world_map` — a node graph of `location` entities in composition-service, per-(user,book) `Work`, private. s7-2 is book-service `world_maps` — a raster map with pixel pins, per-world, owner-scoped. Different service, different data, different shape (plan 30 §10). They share only the words "world map"; merging them reintroduces the exact confusion S7 exists to end.

---

## 1 · Header — what this closes

| | |
|---|---|
| **Panel id (new)** | `place-graph` (category `knowledge`) |
| **Type / size** | FE-only · **S** |
| **The gap** | A working authoring surface reachable from **no dock panel, no catalog row, no command-palette entry, no agent enum** — a live feature the entire new UI cannot open. Reachability, not capability. |
| **New backend** | **NONE.** Any control here that implies a route is a bug in the draft, not a task (draft `screen-place-graph.html:36-43`). |
| **Migrations** | none |

---

## 2 · Why it exists — the operability gap, with file:line

`WorldMap.tsx` renders the book's **place** entities (glossary `location` kind) and their `location↔location`
relations as a hand-rolled SVG node graph over the shared `<GraphCanvas>` (`WorldMap.tsx:167`). It is the
**one fully-operable authoring surface** in the whole KG/World/Cast family:

| Action | Wire | Source |
|---|---|---|
| **+ Place** | `knowledgeApi.createEntity({ project_id, name, kind:'location' })` | `useWorldMap.ts:127-131` → `api.ts:1607` |
| **Link places** (predicate picker: `contains · borders · route_to`) | `knowledgeApi.createRelation({ subject_id, object_id, predicate })` | `useWorldMap.ts:132-136` → `api.ts:1617` |
| **Drag to arrange** | positions persist **server-side** on `work.settings.world_map.positions` (shared across devices) | `useWorldMap.ts:110-113` → `useSetWorkSettings` (`useWork.ts`) |
| **Backdrop** | `booksApi.uploadChapterMedia` → `work.settings.world_map.backdrop_url` | `useWorldMap.ts:137-140` |
| **Click a node** | opens the place in the Cast codex | `WorldMap.tsx:43-47` → `onViewCast` |

Every button works. **The problem is reachability.** It lives ONLY on the legacy `ChapterEditorPage`'s
`worldmap` sub-tab — mounted at `CompositionPanel.tsx:774-782` as `DockSlot slot('worldmap')`, one of the
26 fixed sub-tabs (`CompositionPanel.tsx:87,450`). A Studio user working in the dock has **no route in**:

- Studio dock → "Open panel…" — no catalog row (`catalog.ts` has no `place-graph`).
- `⌘K` / command palette — not derivable (the palette is `OPENABLE_STUDIO_PANELS`, `catalog.ts:325`).
- `ui_open_studio_panel` — `place-graph` is absent from the `panel_id` enum (`frontend_tools.py:402`).

A working feature no one in the new UI can open is, functionally, a dead feature. **The port is: wrap the
same leaf in a Studio dock panel `place-graph`, register it, done.** The heavy S7 lifting lives in the
*sibling* surfaces (s7-2's raster editor is nearly all new backend; s7-1's general entity authoring) — not here.

---

## 3 · What is already built (the reconciliation — be precise; this is what makes "zero backend" trustworthy)

**Backend: 100%. No route to build.**

| Capability | Route / mechanism | Status |
|---|---|---|
| create a location entity | `POST /v1/knowledge/entities` (`api.ts:1608`) | ✅ EXISTS |
| link two places | `POST /v1/knowledge/relations` (`api.ts:1618`; 409 if an endpoint isn't the caller's, 422 on self-loop) | ✅ EXISTS |
| list a project's places | `knowledgeApi.listEntities({ project_id, kind:'location', limit:200 })` (`useWorldMap.ts:71`) | ✅ EXISTS |
| a place's edges | `knowledgeApi.getEntityDetail(id)` (`useWorldMap.ts:82`) | ✅ EXISTS |
| persist positions + backdrop | composition `work.settings` PATCH via `useSetWorkSettings` (`useWorldMap.ts:95,106-113`) | ✅ EXISTS |
| backdrop image upload | `booksApi.uploadChapterMedia` (`useWorldMap.ts:138`) | ✅ EXISTS |
| **archive (soft-delete) a place** | `DELETE /v1/knowledge/me/entities/{id}` → `user_archive_entity`, reason `user_archived`, 204/idempotent, preserves edges + glossary anchor (`entities.py:172-216`; `api.ts:1426`) | ✅ EXISTS — **but the base `WorldMap` has no delete affordance today**; see OQ-4 |

**Frontend: the leaf exists and is host-agnostic; the panel wrapper does not.**

| Piece | Where | Reuse verdict |
|---|---|---|
| the whole surface (`<WorldMap>`) | `WorldMap.tsx` | **reuse verbatim** (DOCK-2 one-implementation-two-hosts) — the leaf takes `{ work, bookId, chapterId, token, onViewCast }` as plain props; it is NOT coupled to `ChapterEditorPage`. |
| the controller (`useWorldMap`) | `useWorldMap.ts` | **reuse verbatim** — resolves the knowledge project by book (`useKnowledgeProjectId`, `:65`), owns the two-writer `wmRef` merge (`:105-113`), the create/link/upload mutations, the grid auto-layout + drag persist. |
| `PLACE_LINK_PREDICATES` closed set | `useWorldMap.ts:18` | **preserve exactly** — the FE `<select>` (`WorldMap.tsx:126`) and the agent's `createRelation` must stay in agreement. |
| `buildPlaceGraph` location-only rule | `useWorldMap.ts:38-59` (drops any edge whose endpoint isn't a `location`, `:49`) | **preserve** — this panel is location-only by construction (§4 scope). |
| the panel-scaffold pattern | `SceneInspectorPanel.tsx:80-85` (`useStudioPanel(id, props.api)` + `useStudioHost()` + `useAuth().accessToken`) | **mirror** for the new wrapper. |
| the Work + `activeChapterId` resolution | `ManuscriptUnitProvider.tsx:134-140` (`useWorkResolution(bookId, token)` → extract `work` from the `{status,work,candidates}` envelope) + bus `activeChapterId` (`host/types.ts:74`) | **mirror** — the wrapper resolves these itself; **no new bus slice** (contrast arc-inspector, which needed `activeArcId`). |
| the deep-link precedent | `QualityCanonPanel.tsx:33` (`props.params as …`) + `host.openPanel(id, { params })` (`StudioHostProvider.tsx:52`) | **the seam** for onViewCast → `cast` and the "author other kinds" link. |

**Not built, and required:** (1) `PlaceGraphPanel.tsx` — the ~40-line dock wrapper; (2) the catalog/enum/
contract/i18n registration; (3) the Lane-B effect handler that refreshes the panel on an *agent* KG write.
That is the whole deliverable.

---

## 4 · The design (from the draft)

### 4.1 Layout — one leaf, one frame

`place-graph` is a **thin host** around `<WorldMap>`, exactly like `ComposePanel` hosts `<Chat>`. No fork,
no re-implemented toolbar. The panel:

1. `useStudioPanel('place-graph', props.api)` + self-titles the tab (`SceneInspectorPanel.tsx:81`, `ComposePanel.tsx:67`).
2. reads `bookId` from `useStudioHost()`, `accessToken` from `useAuth()`.
3. resolves the composition `Work` via `useWorkResolution(bookId, accessToken)` and extracts it from the
   `{status,work,candidates}` envelope (`ManuscriptUnitProvider.tsx:135-140`).
4. reads `activeChapterId` from the bus (`useStudioBusSelector((s) => s.activeChapterId)`) — used ONLY for
   the backdrop upload bucket (`uploadChapterMedia` is chapter-scoped, `useWorldMap.ts:138`).
5. renders `<WorldMap work={work} bookId={bookId} chapterId={activeChapterId ?? ''} token={accessToken} onViewCast={…} />`.
6. routes `onViewCast(name)` → `host.openPanel('cast', { params: { search: name } })` (the S7 `cast` sibling;
   the legacy did `setCastSearch(name) + selectTab('cast')`, `CompositionPanel.tsx:780`). See OQ-1 for the
   param-key coordination.

### 4.2 Every state — rendered, none hand-waved

The leaf already renders most of these (WorldMap's own Hints); the **wrapper adds the two states the leaf
assumes away** (no `Work`, no active chapter).

| State | Trigger | Render | Owner |
|---|---|---|---|
| **loading** | project or places query in flight | *"Loading world map…"* Hint | leaf (`WorldMap.tsx:160`) |
| **no knowledge project** | book never extracted | *"No knowledge graph yet — extract this book to populate places."* | leaf (`WorldMap.tsx:162`) |
| **empty** | project exists, 0 places | *"No places yet — add one above, or extract this book to discover locations."* + the toolbar stays live so **+ Place** works | leaf (`WorldMap.tsx:164`, `worldmap-empty`) |
| **no `Work`** ⭐NEW | book has no composition `Work` | the leaf assumes `work` is non-null (`useWorldMap.ts:94` reads `work.settings.world_map`). The **wrapper** intercepts: a Hint *"Set up the co-writer in Compose to arrange places"* + a button that `host.openPanel('compose')`. **Never mount `<WorldMap>` with a null `work`.** | wrapper |
| **backdrop w/o chapter** ⭐NEW | `activeChapterId == null` | the **Backdrop** control is disabled with a hint *"Open a chapter to set a backdrop."* (media upload needs a chapter bucket). A small **backward-compatible** guard in the leaf (§4.3). | leaf guard |
| **add/link error** | `createEntity` / `createRelation` rejects | `toast.error` (existing: `WorldMap.tsx:54,66-68`) | leaf |
| **link 409** | an endpoint place was archived meanwhile | *"One of those places no longer exists."* (existing: `WorldMap.tsx:66-67`) | leaf |
| **drag persist (mid-drag flag)** | `onNodeDragEnd` | `persistPositions` → `work.settings.world_map.positions` PATCH (`WorldMap.tsx:177` → `useWorldMap.ts:110`) — the draft's *"↳ PATCH work.settings.world_map.positions"* flag | leaf |
| **OCC-conflict** | — | **N/A — there is no OCC here.** `createEntity`/`createRelation` are POST (create, no `If-Match`); `work.settings` PATCH is last-write-wins, mitigated only by the `wmRef` sub-key merge (`useWorldMap.ts:100-113`). This port **introduces no OCC and removes none.** See OQ-3 for the cross-device gap this leaves. |
| **cost gate** | — | **NONE, by construction.** Every action is deterministic $0 CRUD, no LLM, no propose→confirm. Adding one would be a defect. |

### 4.3 The ONE tiny leaf change — degrade backdrop when there is no chapter

`WorldMap`'s Backdrop button is always enabled (`WorldMap.tsx:146-155`); `useWorldMap.uploadBackdrop`
calls `uploadChapterMedia(token, bookId, chapterId, file)` (`useWorldMap.ts:138`). On the legacy page a
chapter is always open, so this never fails there. In the standalone panel `chapterId` can be empty, and an
upload against `''` 404s. **Fix in the shared leaf, backward-compatibly:** gate the Backdrop control on a
truthy `chapterId` (disable + hint when falsy). Legacy behavior is unchanged (it always has a chapter); the
panel degrades gracefully. This is a bug-fix to the leaf, not a fork.

⚠ **Do NOT** work around this by passing a "first chapter" the panel fetches — that is a second data path
for a cosmetic bucket id. Disable the control; the graph itself needs no chapter.

---

## 5 · Backend prerequisites

**None. Every row already ships.** Stated as a table only to prove the claim (mirrors the draft's "NONE" assertion).

| Route | METHOD + path | Request | Response | Errors | Status |
|---|---|---|---|---|---|
| create place | `POST /v1/knowledge/entities` | `{ project_id, name, kind:"location" }` | `201 Entity` | 401 | **EXISTS** (`api.ts:1607`) |
| link places | `POST /v1/knowledge/relations` | `{ subject_id, object_id, predicate ∈ {contains,borders,route_to} }` | `201 EntityRelation` | 409 (endpoint not caller's), 422 (self-loop) | **EXISTS** (`api.ts:1617`) |
| list places | `GET /v1/knowledge/entities?project_id&kind=location&limit=200` | — | `EntitiesResponse` | 401 | **EXISTS** (`useWorldMap.ts:71`) |
| place detail (edges) | `GET /v1/knowledge/entities/{id}` | — | `EntityDetail` | 404 | **EXISTS** (`useWorldMap.ts:82`) |
| persist positions/backdrop | composition `Work` settings PATCH (`useSetWorkSettings`) | `{ world_map: { positions?, backdrop_url? } }` merged | updated `Work` | 401/404 | **EXISTS** (`useWorldMap.ts:95`) |
| backdrop upload | `booksApi.uploadChapterMedia` | multipart image | `{ url }` | 404 (bad chapter) | **EXISTS** (`useWorldMap.ts:138`) |
| archive a place (unused by base) | `DELETE /v1/knowledge/me/entities/{id}` | — | `204` (idempotent) | 404 (not caller's) | **EXISTS** (`entities.py:172`); **not wired in this port** — OQ-4 |

**Nothing is MUST-BUILD.** No new engine, no schema, no migration, no gateway change.

---

## 6 · Registration checklist (GG-8) — keep enum == openable == contract

`place-graph` is **openable by bare id** (it resolves its own `Work` from `bookId` — no selection arg),
so **every** step applies (none of the `hiddenFromPalette` shortcuts). ⚠ **Assert the DELTA (+1) and the
three-way equality (py enum == contract enum == openable-set), never a literal count** — the S7 session
lands 5 panels (`world`, `world-map`, `place-graph`, `cast`, `character-arc`) and neighbouring sessions
move the baseline; a DoD pinned to a literal sends the next builder hunting a phantom regression. Baseline
per the orchestration ledger (`docs/plans/2026-07-16-studio-completeness-8-session-orchestration.md` §4/§8.0).

| # | File | Change |
|---|---|---|
| 1 | `frontend/src/features/studio/panels/PlaceGraphPanel.tsx` **(new)** | the ~40-line wrapper (§4.1). Root `data-testid="studio-place-graph-panel"`. `useStudioPanel('place-graph', props.api)`. |
| 2 | `frontend/src/features/studio/panels/catalog.ts` | one row **in the S7 block** (`:315`): `{ id: 'place-graph', component: PlaceGraphPanel, titleKey: 'panels.place-graph.title', descKey: 'panels.place-graph.desc', category: 'knowledge', guideBodyKey: 'panels.place-graph.guideBody' }`. `'knowledge'` **is** a member of the category union (`catalog.ts:82`) and of `CATEGORY_ORDER` (verified — the kg-* panels use it), so X-2 does not block us. |
| 3 | `frontend/src/features/studio/panels/__tests__/…` imports | none — `PlaceGraphPanel` is imported at the top of `catalog.ts` alongside the other S7 panels. |
| 4 | `services/chat-service/app/services/frontend_tools.py` | **two edits:** (a) append `"place-graph"` to the `panel_id` enum (`:402`); (b) append its clause to the description prose (`:479`, next to the KG panels): *"'place-graph' = the book's places (locations) as a draggable node graph — add a place, link two places (contains/borders/route_to), arrange them (saved server-side), set a backdrop; location entities only."* That gloss is the model's ONLY hint the panel exists. |
| 5 | `contracts/frontend-tools.contract.json` | **NEVER hand-edit — regenerate:** `cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py`. Commit the regenerated JSON in the **same commit** as steps 2 + 4. |
| 6 | `frontend/src/i18n/locales/en/studio.json` | `panels.place-graph.title` / `.desc` / `.guideBody`. |
| 7 | `frontend/src/i18n/locales/{ar,bn,de,es,fr,hi,id,ja,ko,ms,pt-BR,ru,th,tr,vi,zh-CN,zh-TW}/studio.json` | same 3 keys × 17 locales — **`python scripts/i18n_translate.py`**, never hand-written. |
| 8 | `frontend/src/features/studio/agent/handlers/worldEffects.ts` **(new)** + `handlers/index.ts` | the Lane-B handler — §7. |
| — | `host/types.ts` | **skip** — no new bus slice; the panel resolves its own `Work` and reads the existing `activeChapterId` slice. |
| — | `onboarding/tours.ts` / `host/studioLinks.ts` | **skip** — not a role-tour step; no external URL resolves to it. |

**Verify (the drift-locks):**
```
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
cd frontend && npx vitest run \
  src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
  src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
  src/features/studio/palette/__tests__/useStudioCommands.test.ts \
  src/features/chat/nav/__tests__/frontendToolContract.test.ts \
  src/features/studio/agent/handlers/__tests__/effectCoverage.contract.test.ts
```
**Do NOT touch:** `StudioDock.tsx`, `StudioFrame.tsx`, `useStudioCommands.ts`, `UserGuidePanel.tsx` (all
derive from `catalog.ts`); `studioUiNav.ts` / `useStudioUiToolExecutor.ts` (panel-id-agnostic).

---

## 7 · Agent surface / MCP parity — and the Lane-B handler

**MCP-first is already satisfied — for AGENTIC logic.** The agent authors places via `kg_create_node`
(`knowledge …/mcp/server.py:1121`) + `kg_view_upsert`; relations via the kg edge tools. MCP-first governs
LLM-decides-actions logic, **not** a user GUI button, so the GUI's `createEntity`/`createRelation` REST
calls are correct (CLARIFY, resolved). **This spec adds no MCP tool** — the *human* side was the hole.

**The Lane-B effect handler (X-4) — MANDATORY, the one non-registration line of real logic.**

The GUI's own mutations already refresh the open panel (`useWorldMap.invalidatePlaces` on success,
`:122-125`). The gap is **agent** writes: when the agent runs `kg_create_node` for a location, the open
`place-graph` panel reads `['composition','worldmap','places', projectId]` (`useWorldMap.ts:70`) and
`['composition','worldmap','detail', id]` (`:81`) — query keys that **no existing handler invalidates.**
`knowledgeEffects.ts` fires on every `kg_*` write but invalidates only `knowledge-*` / `kg-*` keys
(`knowledgeEffects.ts:24-44`), never the composition worldmap keys. So without a handler, an agent adds a
place and the user's open graph stays stale.

**Ship `worldEffects.ts` (S7-owned) — a DISJOINT handler, not an edit to the kg file.**

- Register `registerEffectHandler(KNOWLEDGE_WRITE_PATTERN, worldEffect)` reusing the same
  mutation-detecting pattern (`knowledgeEffects.ts:16`), but invalidate **only** the two composition
  worldmap keys — `['composition','worldmap','places']` + `['composition','worldmap','detail']`.
- `matchEffectHandlers` returns **all** matching handlers and `runEffectHandlers` awaits **all** of them
  (`effectRegistry.ts:45`), so `worldEffects` and `knowledgeEffects` both fire on a `kg_*` write — each
  invalidating a **disjoint** key set. This is **not** the "two homes for one concept" anti-pattern the
  arc spec warns against: `knowledgeEffects` owns the kg keys, `worldEffects` owns the worldmap keys;
  neither re-invalidates the other's. Keeping the S7 change in an S7-owned file avoids a cross-track edit
  to the 14_kg_panels-owned handler.
- Use `unwrapToolResult` (the live stream nests the domain payload in the `{ok,result}` envelope,
  `resultEnvelope.ts`) and register the pair in `handlers/index.ts:12-24`
  (`registerAllStudioEffectHandlers` + `_resetAll…`), then delete its PENDING row from
  `effectCoverage.contract.test.ts` (the ledger reds until you do — `handlers/index.ts:1-11`).

**Agent-open by bare id** works the moment the enum row (step 4) ships: `ui_open_studio_panel
{panel_id:"place-graph"}` mounts the tab; the panel resolves its own `Work` — never a dead pane. No
`params` on `ui_open_studio_panel`, no `resource_ref` variant needed for v1 (a "point the agent at THIS
place" deep-link would be a later X-6 leg — decompose, don't block).

---

## 8 · Compliance — stated, not assumed

**Tenancy (scope key).** No new table, no shared user-editable row.
- `location` **entities/relations** are the caller's own knowledge-graph rows, resolved by book →
  `useKnowledgeProjectId(bookId)` (`useWorldMap.ts:65`); `createRelation` 409s if an endpoint isn't the
  caller's (`api.ts:1615`) — cross-tenant writes fail closed. **Per-user / per-book (via the book's
  knowledge project).**
- **positions + backdrop** persist on the composition `Work.settings.world_map` — a per-(user,book) `Work`,
  **private** (`useWorldMap.ts:94`). One user's arrangement never touches another's; a collaborator with a
  grant on the book shares the book's one `Work`, by design.
- **No System tier, no `UNIQUE(code)`-on-a-shared-table smell.** Nothing here is globally mutable.

**Settings (SET-1..8).** The panel introduces **zero** settings, toggles, or env flags. `world_map`
(`{positions, backdrop_url}`) is **data**, not configuration — it lives **server-side** (SET: not
localStorage), is consumed by effect (the graph renders from it), and has **one home** (`work.settings`,
merged through the `wmRef` so two writers never clobber each other's sub-key, `useWorldMap.ts:100-113`).
The predicate `<select>` default (`'borders'`, `WorldMap.tsx:32`) is ephemeral per-interaction UI state,
not a persisted preference.

**OCC (If-Match).** **None — and correctly so for creates.** `createEntity`/`createRelation` are POST.
`work.settings` PATCH is last-write-wins with the sub-key merge as its only guard; this port neither adds
nor removes versioning (OQ-3 records the residual cross-device drag-race).

**Cost gate.** **None, by construction** — every action is deterministic, $0, no LLM. If a later agent
adds an LLM action here (e.g. "suggest connections") it must go through the **generic**
`/v1/composition/actions/preview` → `/confirm` spine, never a bespoke per-action estimate route.

---

## 9 · Milestones / slices — each one commit, with a DoD evidence string

| # | Slice | DoD evidence |
|---|---|---|
| **S1** | **The panel, reachable + operable** — `PlaceGraphPanel.tsx` (wrapper + the no-`Work` / no-project / empty / loading states, §4.2) + the §4.3 backdrop-no-chapter leaf guard + registration (catalog row + enum + contract regen + i18n×18). | The 5 drift-lock suites in §6 green (`Δ=+1`, py==contract==openable). `WorldMap.test.tsx` + `useWorldMap.test.tsx` still green (leaf guard is backward-compatible). Palette **and** `ui_open_studio_panel {panel_id:"place-graph"}` both mount the tab; a real book's places render. |
| **S2** | **Lane-B `worldEffects.ts`** — disjoint handler + barrel registration + delete its `effectCoverage` PENDING row. | `effectCoverage.contract.test.ts` green. A unit test: a `kg_create_node` result invalidates `['composition','worldmap','places']` **and** `['composition','worldmap','detail']` and does **not** duplicate `knowledgeEffects`' kg-key invalidations. |
| **S3** | **Deep-links** — `onViewCast(name)` → `host.openPanel('cast', { params:{ search:name } })`; the "Author other kinds →" affordance (draft state ③) → the s7-1 general entity-authoring panel. | Clicking a node (non-link mode) opens the `cast` panel; the "author other kinds" button opens s7-1's surface. (Both degrade to a graceful no-op/toast if the sibling panel isn't registered — OQ-1/OQ-2.) |

*(The live browser smoke + `/review-impl` are the DoD gate below, not a separate commit.)*

---

## 10 · Definition of Done

1. **Unit/contract suites green** — the five drift-locks (§6) + `WorldMap`/`useWorldMap`/`worldEffects` tests.
2. **The palette + agent enum both open it.** `grep` shows `place-graph` in `catalog.ts`, the
   `frontend_tools.py` enum, and the regenerated `contracts/frontend-tools.contract.json`.
3. 🔴 **LIVE BROWSER SMOKE — mandatory, not negotiable** (a green unit suite has repeatedly hidden "the FE
   could not actually execute it" — `agent-gui-loop-needs-live-browser-smoke-not-raw-stream`). Drive a
   **real browser** against a **rebuilt** image (`live-smoke-rebuild-stale-images-first`), signed in as
   `claude-test@loreweave.dev`:
   1. studio → `⌘P` → **Open Place Graph** → the dock tab mounts (verify by EFFECT — a dock tab, not a
      `shown:true` in the raw stream);
   2. type a name → **+ Place** → the node appears (a real `POST /entities`);
   3. **Link places** → select two → pick `route_to` → **link** → the predicate-coloured edge renders
      (a real `POST /relations`);
   4. **drag** a node → reload the panel → the position **persisted** (the `work.settings.world_map` PATCH
      round-tripped, shared-across-devices);
   5. **the agent leg:** from Compose, `kg_create_node` a location → the **open** place-graph shows the new
      node **without a manual reload** (proves `worldEffects` is wired — the whole point of §7);
   6. with **no chapter open**, the **Backdrop** control is disabled with its hint (the §4.3 guard);
   7. click a node → the **cast** panel opens (the onViewCast deep-link).
   Drive dockview via `evaluate` + `data-testid` (refs go stale — `playwright-live-dockview-automation-recipe`).
4. **`/review-impl` on the diff** — this touches a shared leaf (`WorldMap`), a cross-service contract
   (the frontend-tool enum), and a Lane-B handler; run the adversarial pass before COMMIT.
5. **SESSION_HANDOFF + the S7 RUN-STATE updated** — the place-graph row moved to done in the S7 slice board;
   the orchestration ledger's panel-id count reconciled.

---

## 11 · Open questions / Deferred — honest, code-checked

| # | Question | Disposition |
|---|---|---|
| **OQ-1** | `onViewCast(name)` needs the S7 `cast` panel to accept a prefill param. Is the key `params.search`? | **CODE-SETTLED (CLARIFY-SYNTHESIS 2026-07-16) — `params.search` is correct; coordination fix lands in s7-4.** `CastCodexPanel` **already accepts a `search` prop** built for exactly this — `CastCodexPanel.tsx:32,39-41`: *"optionally control the search from the parent (World Map click → prefill this place's name)"*, with `search = searchProp ?? localSearch` (`:48`). So the leaf seam exists. The only gap: **s7-4's `CastPanel` wrapper must read `props.params.search` and pass it as the `search` prop** (s7-4 §6 step 1 does not yet mention this — flagged to that spec). Ship `openPanel('cast', { params:{ search:name } })`; it degrades to unfiltered if the wrapper wiring lands later. **Action for s7-4:** add `props.params.search` → `<CastCodexPanel search={…}>`. |
| **OQ-2** | The draft's "Author other kinds →" deep-link targets s7-1's general entity-authoring surface. Which **panel id**? | **CODE-SETTLED (CLARIFY-SYNTHESIS 2026-07-16) — target is the EXISTING `kg-entities` panel, NOT a new S7 id.** s7-1 (KG Entity Authoring) explicitly adds **NO new panel** — it mounts Create Entity / Create Relation as dialogs **inside the already-registered `kg-entities` / `kg-graph` panels** (s7-1 §2.5, §5). `kg-entities` is already in `catalog.ts:180` and the `panel_id` enum. **RESOLUTION:** wire "Author other kinds →" to `host.openPanel('kg-entities')` (already openable; degrades to a graceful no-op only if a future refactor removes it). ⚠ **The catalog:315 comment listing a `world` panel and any reference to an "s7-1 panel id" is stale** — see the cross-spec note in this report; s7-1 delivers zero panels. |
| **OQ-3** | `work.settings.world_map` has **no version/If-Match** — two devices dragging concurrently are last-write-wins (only the `wmRef` sub-key merge protects positions-vs-backdrop, not position-vs-position). | **DEFERRED — gate #2 (structural).** A real fix needs an OCC contract on the composition `Work.settings` PATCH, which is a cross-cutting change to every settings writer, not a place-graph concern. This port neither introduces nor worsens the gap. **Row it as `D-WORK-SETTINGS-OCC`** if not already tracked. |
| **OQ-4** | A "delete/archive place" affordance: `DELETE /v1/knowledge/me/entities/{id}` exists (`entities.py:172`), but the base `WorldMap` has no delete button — and the project-listed `location` entity id (from `listEntities`, project-scoped) ↔ the `me/entities` canonical id used by the archive route is **not proven equivalent**. | **OUT OF BASE SCOPE — do not add on a guess.** The port is faithful to `WorldMap`'s current surface (create/link/drag/backdrop). Adding archive is a small follow-on that first **must verify** the id equivalence with a live call; if they diverge, it needs the project-scoped delete path, not `me/entities`. Recorded so a later agent doesn't wire archive blindly (the kg-authoring draft already mis-routed archival through Merge — CLARIFY). |
| **OQ-5** | Category: `place-graph` uses `'knowledge'`. Should the S7 World/Cast panels share `'knowledge'`, or warrant a new category for palette grouping? | **CODE-CHECKED (CLARIFY-SYNTHESIS 2026-07-16) — real inconsistency found; recommend unify on `storyBible`, no new category.** Both `'storyBible'` and `'knowledge'` already exist in `ALL_CATEGORIES` + the union (`catalog.ts:84-85,100-101`); no new category needed (avoid the X-2 surface). **The inconsistency:** s7-2 `world-map` → `storyBible`, s7-4 `cast`/`character-arc` → `storyBible`, but this spec's `place-graph` → `knowledge`. The 12 analytical `kg-*` panels are `knowledge`; the lore-authoring surfaces (glossary/wiki) are `storyBible`. **RECOMMENDATION:** these four are world/cast **authoring** surfaces beside glossary/wiki → put **all four in `storyBible`** (change `place-graph` from `knowledge`→`storyBible`) so the palette groups the S7 family together. Low-stakes + reversible (one field) — builder confirms in the shared registration pass; not a PO blocker. |

---

### Risks

| Risk | Mitigation |
|---|---|
| A reviewer reads a control here as implying a backend route | §5 enumerates every dependency as **EXISTS**; the draft asserts NONE (`screen-place-graph.html:36-43`). If a new route seems needed, it's a draft bug. |
| Someone forks `WorldMap` into a studio copy | DOCK-2: the wrapper hosts the **same** leaf (like `ComposePanel`↔`Chat`). The only leaf edit is the backward-compatible backdrop guard (§4.3). |
| `worldEffects` double-invalidates the kg keys | It invalidates a **disjoint** key set (worldmap only); `knowledgeEffects` keeps the kg keys. Both fire, neither duplicates. |
| The panel mounts `<WorldMap>` with a null `Work` and crashes on `work.settings.world_map` | The wrapper intercepts the no-`Work` state (§4.2) and never mounts the leaf without a resolved `Work`. |
| This gets conflated with s7-2's raster world-map editor | Header + §1 + OQ boundaries state the split (composition node-graph vs book-service raster pins). |
