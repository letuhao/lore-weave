# Spec + Plan — Motif Graph Canvas (persisted positions) (Wave-4)

> **Status:** ready to build · **Size:** XL (net-new table + migration + repo + routes + OCC + per-viewer tenancy + a new reactflow panel) · **Track:** Wave-4 (was `D-MOTIF-GRAPH-CANVAS`) · **PO decision (2026-07-17):** persisted positions (user drags + saved), each viewer arranges their own view.

## 1 · Problem & scope

Today the motif relationship graph ships as an honest **LIST** — [`MotifGraphSection.tsx`](../../frontend/src/features/composition/motif/components/MotifGraphSection.tsx) renders **one anchor motif's edges** (grouped by `composed_of · precedes · variant_of`) inside the motif detail drawer. There is no multi-node graph, no node objects, no positions. The list was a deliberate, honest v1 ("a list is honest, cheap, keyboard-navigable").

**Wave-4 = a book-wide visual DAG canvas**: the caller's motifs for a book as draggable nodes, `motif_link` edges between them, with **per-viewer persisted positions** (each user arranges their own layout; it survives reload + follows them across devices). The list stays (cheap per-motif view); the canvas is a new first-class surface.

**Why XL:** no existing feature persists reactflow node positions. This composes two separate precedents (reactflow controlled-drag wiring + a persist-on-drag-end data flow) AND adds a net-new positions store (migration + repo + routes + OCC + tenancy gate) + a new registered panel.

### 1.1 · Corrected premises (verified against code — the plan depends on these)
- **reactflow is v11 `reactflow` (`^11.11.4`), NOT `@xyflow/react`.** Imports are `from 'reactflow'` + `'reactflow/dist/style.css'`; the drop-point API is `screenToFlowPosition` (v11.11), `project` is the fallback.
- **The reactflow precedent is [`PlanCanvas.tsx`](../../frontend/src/features/plan-hub/components/PlanCanvas.tsx), and it does NOT persist positions** (every resting `{x,y}` comes from a layout function; RF owns only the transient drag offset). It gives the controlled-drag wiring, not the persistence.
- **The persist-on-drag-end precedent is [`SceneGraphCanvas.tsx`](../../frontend/src/features/composition/components/SceneGraphCanvas.tsx)** (seed-from-store → `localRef` mirror → `onNodeDragEnd → persist`), but it is bespoke SVG + a settings blob (last-write-wins, no debounce, no OCC), and its store (`work.settings`) is **per-WORK** (shared across collaborators) — the wrong tenancy for "arrange my own view".
- **No auto-layout library is installed** (no dagre/elkjs/d3). The only precedent is the bespoke pure `autoLayout` in [`sceneGraphLayout.ts`](../../frontend/src/features/composition/components/sceneGraphLayout.ts). → the initial layout is a **bespoke layered DAG** (edges are already acyclic by the `motif_link_guard`), not a new dependency.

## 2 · Data model

### 2.1 · Nodes & edges (already exist — BE-M3)
- **Nodes = motifs.** `motif` table ([migrate.py:713-800](../../services/composition-service/app/db/migrate.py#L713)): `id, owner_user_id (NULL=system), book_id, book_shared, code, name, kind, visibility, …`. The graph shows the motifs **visible to the caller within this book's tier** — the same read predicate the link/list routes use (system | public | caller-owned | book_shared-to-this-book). Edges only exist within one tier (the guard forbids cross-tier), so a book's graph is coherent.
- **Edges = `motif_link`** ([migrate.py:810-885](../../services/composition-service/app/db/migrate.py#L810)): `{id, from_motif_id, to_motif_id, kind ∈ {composed_of,precedes,variant_of}, ord}`, `UNIQUE(from,to,kind)`, a BEFORE-INSERT `motif_link_guard` (same-tier + acyclic on `precedes`/`composed_of`). Read via `GET /motifs/{id}/links` / `MotifRepo.list_links`; the graph needs a **book-wide edge fetch** (see §3.1) rather than per-anchor.

### 2.2 · Positions store (NET-NEW) — `motif_graph_layout`
Positions are a **per-VIEWER cosmetic preference** (each user arranges their own view), so they must NOT live on the shared `motif`/`motif_link` rows (one collaborator's drag would move everyone's graph). They are **derived/regenerable** (drop them → auto-layout), so per `scope-separation.md` (SCOPE-3) they are a cache, not authored truth. New table owned by composition-service:

```sql
CREATE TABLE motif_graph_layout (
  owner_user_id UUID NOT NULL,          -- the VIEWER (scope key)
  book_id       UUID NOT NULL,          -- the graph is per-book (scope key)
  positions     JSONB NOT NULL DEFAULT '{}',  -- { "<motif_id>": {"x": number, "y": number} }
  version       INT  NOT NULL DEFAULT 1, -- OCC (multi-device same-user)
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (owner_user_id, book_id)
);
```

- **Scope key `(owner_user_id, book_id)`** — one row per viewer per book. Satisfies User-Boundaries (every user-customizable row carries a scope key; no shared/global row a user mutates for others).
- **Regenerable:** an unknown `motif_id` in `positions` is ignored; a motif with no stored position falls back to the auto-layout slot (`posOf(id) = stored ?? auto ?? default`, the SceneGraphCanvas pattern). Deleting the row = reset to auto-layout.
- **NOT the `work.settings` blob** — that is per-Work/shared (wrong tenancy) and the motif library is book-scoped, not Work-scoped.

## 3 · Backend

### 3.1 · Book-wide graph fetch
Add `GET /books/{book_id}/motif-graph` (composition, VIEW-gated on the book) → `{ nodes: MotifNode[], edges: MotifLinkRow[], layout: {positions, version} }`:
- **nodes** — the caller-visible motifs for the book (reuse the `motif` read predicate; project id/code/name/kind/tier — never embedding). Bounded (a `limit` + an honest "graph truncated, N more" if a book ever exceeds it — the no-silent-cap rule).
- **edges** — all `motif_link` among those node ids (a set-membership query, not per-anchor).
- **layout** — the caller's `motif_graph_layout` row (or `{positions:{}, version:0}` when none yet).

(Alternatively compose from the existing per-motif `list_links` + a nodes list; a single book-graph route is cleaner and one round-trip.)

### 3.2 · Position write — batch-capable PATCH with server-side merge + OCC
`PATCH /books/{book_id}/motif-graph/layout` — body `{ moves: [{motif_id, x, y}], if_version }` (accepts one OR many moves — the FE flushes its whole pending-map in a single call; see §6.5 E1):
- **Server-side merge** (not a whole-blob overwrite): `UPDATE … SET positions = positions || $moves_jsonb, version = version+1 WHERE owner_user_id=$caller AND book_id=$book AND version=$if_version` (upsert the row on first write), where `$moves_jsonb` = `{motif_id:{x,y}, …}` built from `moves`. Merging (not replacing) `positions` means an untouched node keeps its slot even if a concurrent flush raced.
- **OCC:** `if_version` mismatch → **412** with the current `{positions, version}` so the client reseeds (mirrors WorldMap `patchMap` If-Match/412 + reseed). Positions are cosmetic, so OCC only guards the rare multi-device same-user race — fail soft (reseed + retry), never hard-error the drag.
- **Tenancy:** the WHERE clause is scoped to `owner_user_id = caller` — a viewer can only write **their own** layout row; no path writes another viewer's positions. `motif_id` is validated to be a caller-visible motif in the book (else 404, no oracle).
- **MCP:** none. Layout is a GUI cosmetic, not agent logic — no MCP tool (the MCP-first invariant is for agent *decisions*, not cursor positions).

### 3.3 · Repo + tests
`MotifGraphLayoutRepo` (get/upsert-merge) in composition-service; unit tests for the merge (two nodes → both kept), the OCC 412, and the tenancy scope (caller can't write another owner's row). DB-integration test with the `xdist_group("pg")` mark.

## 4 · Frontend

### 4.1 · A new `motif-graph` Studio panel (book-scoped)
A book-wide graph is book-scoped (not motif_id-scoped), so — unlike the per-motif `MotifGraphSection` — it CAN be a first-class dock panel (`host.bookId` is available). **Register a new `motif-graph` panel** (mirror [`MotifLibraryPanel.tsx`](../../frontend/src/features/studio/panels/MotifLibraryPanel.tsx)); keep the cheap per-motif list section as-is.

### 4.2 · The canvas — fuse PlanCanvas wiring + SceneGraphCanvas persist
`MotifGraphCanvas.tsx` — a reactflow (v11) canvas:
- **Controlled nodes + `onNodesChange`** ([PlanCanvas.tsx:229-232,355](../../frontend/src/features/plan-hub/components/PlanCanvas.tsx#L229)) — `useNodesState`, wired so a node moves under the cursor. `nodeDragThreshold={5}` (RF default 0 turns every click into a 0px drag). `nodeTypes` render a motif node (code · name · tier badge); `edges` typed/coloured by `kind` (composed_of/precedes/variant_of), directed.
- **Seed positions** from the fetched `layout.positions`; `posOf(id) = stored ?? auto ?? default` with a bespoke **layered DAG auto-layout** (topo-order by `precedes`/`composed_of`, mirroring `sceneGraphLayout.ts`) for un-positioned nodes.
- **Persist on drag END** ([SceneGraphCanvas.tsx:379-380](../../frontend/src/features/composition/components/SceneGraphCanvas.tsx#L379) pattern) — `onNodeDragStop` reads the cursor drop point (`screenToFlowPosition`) and adds `{motif_id:{x,y}}` to a **pending-map ref**; a **debounced** (≈400ms) flush PATCHes the whole pending map in one call and clears it (§6.5 E1–E4). The flush reads the pending-map + `versionRef` from refs, never captured closures ([[debounced-write-must-bind-its-target-entity]]); it flushes on unmount/blur too (E2).
- **Optimistic + rollback** ([useWorldMapEditor.moveMarker](../../frontend/src/features/world/hooks/useWorldMapEditor.ts#L111)) — `onMutate` sets the local position, `onError` restores, `onSettled` invalidates; a **412** reseeds `positions`+`version` from the response and re-applies the pending move (fail-soft).
- **Edge create/delete** — reuse the existing `useMotifLinks` create/remove (BE-M3) via a link-mode (drag from one node's handle to another → pick a `kind`; the guard 409 renders inline, never a toast — the existing `MotifGraphSection` pattern).
- **Read-only** when the caller lacks EDIT (view another tier): nodes draggable=false, no edge tools.

### 4.3 · Hooks
`useMotifGraph(bookId, token)` — the book-graph query (`['composition','motif-graph',bookId]`) + the layout mutation (optimistic, 412-reseed). `useMotifGraphLayout` may split the mutation out if the file grows (>200 lines → split, the component/hook size rule).

## 5 · Registration (4-part — enforced)
1. **`catalog.ts`** — a `STUDIO_PANELS` row `{ id:'motif-graph', component:MotifGraphPanel, category:'storyBible', titleKey/descKey/guideBodyKey:'panels.motif-graph.*' }` (`guideBodyKey` required).
2. **chat-service `ui_open_studio_panel` panel_id enum** — add `'motif-graph'` ([`frontend_tools.py`](../../services/chat-service/app/services/frontend_tools.py)); enforced by `panelCatalogContract.test.ts` (palette-openable set === backend enum).
3. **`contracts/frontend-tools.contract.json`** — regenerate (`WRITE_FRONTEND_CONTRACT=1 pytest` + update the resolver).
4. **i18n** — `en` `panels.motif-graph.{title,desc,guideBody}` + component strings, then `scripts/i18n_translate.py` to 17 locales.

## 6 · Standards / invariants
- **User Boundaries & Tenancy:** `motif_graph_layout` carries the scope key `(owner_user_id, book_id)`; a viewer writes only their own row; positions are a per-user cache, never a shared/global row. ✅
- **Frontend-Tool Contract:** the new `motif-graph` panel_id is a closed-set enum in both the FE catalog and the chat-service schema, machine-checked by the contract test. ✅
- **MCP-first:** N/A — layout is cosmetic GUI state, not agent logic; no MCP tool.
- **No-silent-fail / no-silent-cap:** the graph truncates loudly if a book exceeds the node cap; a 412 reseeds visibly; the guard 409 renders inline.
- **No localStorage for user data:** positions live server-side (the table), not localStorage — multi-device parity (localStorage is allowed only for per-device view state like zoom/pan, which is fine to keep local).
- **Test-parallelization:** the DB-integration test adds `pytestmark = pytest.mark.xdist_group("pg")`.

## 6.5 · Edge cases & resolutions (design-review pass)

**Persistence / concurrency**
| # | Edge case | Resolution |
|---|---|---|
| E1 | **Debounce coalescing across DIFFERENT nodes** — a single global debounce timer would drop node A's move if node B is dragged before the timer fires. | Keep a **pending map `{motif_id:{x,y}}`**, not a single value. The debounce flush writes **every** pending node (a batch `PATCH …/layout {moves:[{motif_id,x,y}]}` merged server-side, OR one PATCH per pending id). Never coalesce two motif_ids into one write. |
| E2 | **Lost write on unmount / panel close** — drag then close before the debounce fires. | **Flush pending on unmount** (useEffect cleanup) + on `visibilitychange`/blur. The cleanup reads the pending ref (not a captured closure). |
| E3 | **`if_version` staleness in the debounced closure** — a captured version goes stale after the first successful PATCH. | The flush reads `versionRef.current` (bumped on every 200), never a captured value ([[debounced-write-must-bind-its-target-entity]]). |
| E4 | **OCC 412 (multi-device same user)** — another device advanced the version. | On 412: take the server's `{positions, version}`, **re-apply the local pending map on top** (the user's active drag wins over the other device's older state), set `versionRef` to server+1 expectation, and retry the flush. Fail-SOFT — never hard-error or freeze the drag on a cosmetic write. |
| E5 | **StrictMode double-fire of the drag-end persist.** | Mirror the SceneGraphCanvas `localRef` guard so the persist reads the latest ref without a setState side-effect firing twice. |

**Graph data / tenancy**
| # | Edge case | Resolution |
|---|---|---|
| E6 | **Read-only ≠ layout-locked.** A viewer without EDIT on a book_shared graph must still arrange THEIR OWN view (positions are per-viewer). | Read-only gates **EDGE tools** (create/delete links) only; the **layout drag + persist stays enabled** (the viewer writes their own `motif_graph_layout` row). Make this explicit in the panel — a common misread would wrongly freeze the drag. |
| E7 | **Cross-tier edge attempt** — dragging a handle from a system node to an own node (the `motif_link_guard` forbids it). | The create mutation gets a **409** → render inline near the target (transient, toast-free), never a silent no-op (the existing `MotifGraphSection` guard-409 pattern). Same for self-loop / duplicate (UNIQUE + distinct → 409). |
| E8 | **Empty graph** — a book with 0 motifs, or motifs with 0 edges. | Honest empty state + a CTA (adopt / create a motif); a zero-edge graph still renders the nodes (an unconnected scatter is valid), never a blank canvas. |
| E9 | **Node cap truncation** — a book exceeds the node ceiling (~300). | **Deterministic drop order**: keep highest edge-degree + caller-own-tier first; render a loud "graph truncated — N motifs hidden, narrow by tier/search" banner (the no-silent-cap rule). |
| E10 | **Deleted motif with a stored position** — a motif removed after its position was saved. | GET **ignores unknown motif_ids** in `positions` (regenerable); the node is absent from the live fetch so it never renders. A PATCH for a now-invisible motif → **404** (validated caller-visible). No orphan node. |
| E11 | **New motif with no stored position** — created after the layout was seeded. | `posOf(id) = stored ?? auto ?? default` places it at its auto-layout slot; the user can drag+persist from there. |
| E12 | **reactflow v11 gotchas** — clicks read as 0px drags; wrong drop point. | `nodeDragThreshold={5}` (RF default 0 turns every click into a drag); resolve the drop from the **cursor** via `screenToFlowPosition` (v11.11; `project` fallback), not the node corner ([PlanCanvas.tsx:110-126,307-345](../../frontend/src/features/plan-hub/components/PlanCanvas.tsx#L110)). |

## 7 · Plan (phases)

| # | Phase | Work | Gate |
|---|---|---|---|
| 1 | **BE data** | `motif_graph_layout` migration; `MotifGraphLayoutRepo` (get + upsert-merge + version); unit + pg-integration tests (merge keeps both nodes, OCC 412, tenancy scope). | pytest green |
| 2 | **BE routes** | `GET /books/{id}/motif-graph` (nodes+edges+layout, VIEW-gated, bounded); `PATCH …/layout` (per-node merge, OCC 412, owner-scoped). Route tests (gate, 412, foreign-motif 404). | pytest green |
| 3 | **FE canvas** | `MotifGraphCanvas` (reactflow v11: controlled nodes + `onNodesChange` + `nodeDragThreshold` + cursor drop); bespoke layered auto-layout; seed-from-layout + `posOf` fallback; debounced optimistic persist + 412 reseed; edge create/delete via `useMotifLinks`; read-only gating. `useMotifGraph` hook. | vitest + tsc |
| 4 | **Registration** | new `motif-graph` panel (catalog + enum + contract regen + i18n en); `MotifGraphPanel` (mirror `MotifLibraryPanel`). | panelCatalogContract test green |
| 5 | **Tests** | Unit: mirror `PlanCanvasDrag.test.tsx` (mock `reactflow`, capture props, invoke `onNodeDragStop`, assert one debounced `patchLayout` with the right motif_id+version; assert `onNodesChange` wired, threshold>0, read-only freezes drag). Persist test mirrors `WorldMapEditor.test.tsx`. **Live drag (CDP stepped `page.mouse.move→down→move(steps)→up`** — synthetic events don't drive RF d3-drag, the [[playwright-cdp-mouse-drives-d3-drag]] recipe): drag a node → reload → position persisted. | all green + live smoke |
| 6 | **i18n + VERIFY** | `i18n_translate.py --ns studio,composition`; cross-service live-smoke (FE drag → PATCH → DB row → reload persists) since it touches composition BE + FE. | live smoke token |

**Risk / open decisions:**
- **Debounce vs persist-on-dragEnd:** SceneGraphCanvas persists every drag-end (no debounce). For a graph with many nodes, debounce coalesces nudges — but adds the "bind the target entity in the debounced closure" hazard. Decision: debounce ≈400ms, ref-bound target+version. (If it proves fiddly, fall back to persist-on-each-dragEnd — simpler, matches SceneGraphCanvas.)
- **OCC necessity:** positions are cosmetic + single-writer-per-viewer; OCC only guards multi-device same-user. Keep it (cheap `version` column, fail-soft 412 reseed) — but never hard-block a drag on it.
- **Node cap:** pick a sane ceiling (e.g. 300 motifs/book) with a loud truncation; revisit if real books exceed it.
- **Auto-layout quality:** a bespoke layered DAG is "good enough to start"; if it's poor, a `dagre` dep is the follow-up (a dep decision, deferred until the bespoke proves insufficient — YAGNI).

**Out of scope:** cross-book/global motif graph (this is per-book); sharing a layout between collaborators (per-viewer by design); an MCP tool for the graph (cosmetic GUI); auto-layout as a shipped dependency (bespoke first).
