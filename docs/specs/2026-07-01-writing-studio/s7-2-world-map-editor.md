# S7·2 · World Map Editor — first-party authoring over book-service's raster map

> **Status:** 📐 specced 2026-07-16 · branch `feat/context-budget-law` (studio S7 · World) · **L** (files≈16, logic≈10, side_effects: 4 — 3 new tables' columns + ~10 new routes + 3 new MCP tools + a migration)
> **Type:** **FS** — the **biggest NEW backend-dependent surface in S7**. This is **not** a port: the reads exist, every write is agent-MCP-only, and **UPDATE exists at NO layer for anyone** (source-verified below). Roughly half this spec is book-service Go.
> **Closes:** **S7-A1 row 5** ("World maps — `WorldMapsSection` — view/select only") and **S7-A2 decision #4** ("BUILD (real BE) — reachable world-map marker/region routes (~8–10; design the missing UPDATE)") — [`docs/plans/2026-07-16-studio-session-S7-RUN-STATE.md:49,61`](../../plans/2026-07-16-studio-session-S7-RUN-STATE.md).
> **Draft (UI acceptance target + house style):** [`design-drafts/screens/studio/screen-world-map-editor.html`](../../../design-drafts/screens/studio/screen-world-map-editor.html).
> **Sibling, do NOT conflate:** the composition **place-graph** (`work.settings.world_map`, a node graph — `screen-place-graph.html`, S7·3). A raster map's regions are **polygons, not graph edges** (plan-30 §10). Merging the two "world maps" reintroduces the exact confusion S7 exists to end.
> Follows [`docs/standards/dockable-gui.md`](../../standards/dockable-gui.md) (DOCK-1..11), [`docs/standards/mcp-tool-io.md`](../../standards/mcp-tool-io.md) (IN-1..8 / OUT-1..6), and the Provider/Tenancy/Settings laws in CLAUDE.md.

---

## 1 · Why this exists — the operability gap

Today a human can **look at** a world map an agent built and **do nothing else**. `WorldMapsSection.tsx`
lists a world's maps, selects one, and overlays pins + regions from normalized coords — and that is the
whole surface:

```tsx
frontend/src/features/world/components/WorldMapsSection.tsx:6-8
  // View-only; the world_map_* agent tools (Tier-W) are the only write path.
frontend/src/features/world/components/WorldMapsSection.tsx:18-23
  // empty state: "No maps yet. Ask the assistant to 'make a map of this world' to create one."
```

That empty-state string is **the tell** (S7-A1): the surface *delegates authoring to the agent because
the human has no form*. The controller confirms it — `useWorldMaps.ts` exposes `{maps, selectedId,
select, detail}` and **not one mutation** (`useWorldMaps.ts:29-38`); `worldsApi` has `listWorldMaps` /
`getWorldMap` and **no writer** (`api.ts:120-135`).

**The write asymmetry, source-verified — this is the load-bearing table of the whole spec.**

| Capability | Agent (MCP) | Human (GUI) | REST route |
|---|:--:|:--:|---|
| list a world's maps | `world_map_list` ✅ | ✅ `WorldMapsSection` | `GET /v1/worlds/{id}/maps` ✅ `server.go:408` |
| open one map (pins+regions) | `world_map_get` ✅ | ✅ | `GET /v1/worlds/{id}/maps/{map_id}` ✅ `server.go:409` |
| **create a map** | `world_map_create` ✅ `mcp_maps.go:466` | ❌ | ❌ **MCP only** |
| **upload a base image** | ❌ (agents can't upload binaries) | ❌ | `POST /internal/worlds/maps/{id}/image` — `requireInternalToken`, browser can't call it (`server.go:206`, `maps_image.go:30`) |
| **add a pin / region** | `world_map_add_marker` / `_add_region` ✅ `mcp_maps.go:475,481` | ❌ | ❌ **MCP only** |
| **rename a map / change its image** | ❌ **NOWHERE** | ❌ | ❌ **NOWHERE** |
| 🔴 **move a pin (drag)** | ❌ **NOWHERE** — only `add`+`remove` | ❌ | ❌ **NOWHERE** |
| **reshape a region / relabel / rebind** | ❌ **NOWHERE** | ❌ | ❌ **NOWHERE** |
| **delete a pin / region** | `world_map_remove_marker` / `_region` ✅ `mcp_maps.go:504,510` | ❌ | ❌ **MCP only** |

**The `UPDATE` hole is the spine of this spec.** There is **no update tool of any kind**
(`registerMapTools`, `mcp_maps.go:465-515` — eight tools, none an update). So today even the **agent**
cannot nudge a misplaced pin: it must `remove_marker` + `add_marker`, which

1. **churns `marker_id`** — a fresh row id, so any `entity_id` tie the old marker carried, and any future
   reference to that marker, is silently dropped; and
2. **is not atomic** — a mid-drag disconnect strands the delete committed and the re-add un-sent (silent
   data loss).

A human editor that **drags pins** is therefore not "just a frontend." It is blocked on an UPDATE
contract that does not exist for anyone. This spec's core job is to **design that missing UPDATE
explicitly** so a later agent does not "fix" drag by looping remove+add.

---

## 2 · What is already built (be precise — this is what makes the estimate trustworthy)

**Backend data layer: 100% complete. Write layer: create/add/remove only, no update, no public REST.**

| Piece | Where | Verdict |
|---|---|---|
| `world_maps` / `map_markers` / `map_regions` tables | `migrate.go:418-451` | ✅ exist; `polygon JSONB`, coords `DOUBLE PRECISION`, `entity_id UUID` **nullable soft ref** |
| MinIO base-image storage + pixel dims | `maps_image.go` | ✅ exist (`image_object_key`, `image_w/h`) |
| 8 MCP tools (create/add_marker/add_region/get/list/delete/remove_marker/remove_region) | `mcp_maps.go:465-515` | ✅ exist, owner-scoped, `[0,1]` validated (`mcp_maps.go:155,203`), TierA |
| the 2 public READ routes (list + detail w/ image URL) | `worlds_maps_rest.go` | ✅ exist, owner+world scoped, strict "sub-read error is a failure not empty" posture |
| image URL resolution | `withImageURL` / `mediaURL` `mcp_maps.go:83` | ✅ reuse |
| FE read path: `worldsApi.listWorldMaps/getWorldMap`, `useWorldMaps`, `WorldMapsSection` | `api.ts:120`, `useWorldMaps.ts`, `WorldMapsSection.tsx` | ✅ reuse the read shape + query keys `['world-maps',worldId]` / `['world-map',worldId,mapId]` |
| FE wire types `WorldMapSummary/Marker/Region/Detail` | `world/types.ts:79-108` | **widen** — add `version` (map) + `updated_at` (marker/region); see §5 |
| gateway `/v1/worlds*` passthrough | `gateway-setup.ts:86-91` | ✅ **generic** `startsWith('/v1/worlds')` — every new nested route is auto-proxied, **NO gateway change** |
| book-service JWT resolution on `/v1/worlds/*` | `requireUserID` `server.go:434` (reads `Authorization: Bearer`), `requireWorldOwner` `worlds.go:333` | ✅ reuse — the new public routes resolve identity **from the JWT the gateway already forwards** (see §5, image-upload correction) |
| `patchWorld`'s dynamic-`SET` partial-update pattern | `worlds.go:258-330` (presence-checked `map[string]any`) | **mirror exactly** for the PATCH routes — it already solves the omitted-vs-null problem (§4.4) |

**Not built, and required:** every write control (create/upload/add/**update**/delete), the three UPDATE
routes + their three MCP tools, the `version`/`updated_at` columns to make update safe to read back, the
`world-map` dock panel + its registration, and the `worldEffects` Lane-B handler.

**No legacy component to move.** `WorldMapsSection` is a viewer; the editor is a new panel that **reuses
its read shape** (same query keys, same overlay math) and adds the write layer. `grep -rn "world-map-editor\|WorldMapEditor" frontend/src` → nothing.

---

## 3 · The design (from the draft)

### 3.1 Panel identity & addressing — how `world-map` resolves its subject

`world-map` is a **detail-editor-over-a-selection**, palette-openable by bare id (like `scene-inspector`
/ `arc-inspector`), category `storyBible`. Its subject is **a (world, map) pair**. The studio is
**book-scoped**, not world-scoped, and a world groups *many* books — so the panel cannot assume a world.
It resolves in this precedence, and **never renders a dead pane**:

1. `props.params.worldId` (+ optional `mapId`) — an in-studio deep-link (from a future `world` panel row,
   or `book-settings`' world link). Same `props.params` seam as `quality-canon` (`QualityCanonPanel.tsx:34`).
2. **derive from the current book** — if the active book belongs to a world (`books.world_id`), preselect it.
3. **an in-panel world picker** (`worldsApi.listWorlds`) → **map rail** (`listWorldMaps`). A bare-id open
   (palette / agent / User Guide) with no context shows the picker + a *"Create a map"* CTA, never blank.

**No new studio-bus slice in v1.** Unlike `arc-inspector`'s `activeArcId`, there is no existing
world-selection event on the bus (`host/types.ts` has chapter/scene/selection/… — no world), and the
book→world derivation + picker cover every entry. **OQ-1** records whether a `world`/`worldId` bus slice
is worth adding when the sibling `world` panel (S7·1) lands; this panel ships without it.

### 3.2 Panel layout — `world-map` (category `storyBible`)

One dock panel over the same owner-scoped tables, mirroring the draft. Regions are polygons; pins are
points; both live at normalized `[0,1]` so the overlay tracks the image at any zoom.

```
┌─ WORLD MAPS — Sơn Hải Di Văn ─────────────────── [⤢ fit] [⤢ pop] [×] ─┐
│  [◆ Select] [◈ Pin] [⬡ Region]   [⭱ Upload base image]   zoom 84% −／＋ │  ← tool rail (mode) + upload
├──────────┬──────────────────────────────────────────────────────────────┤
│ MAPS · 3 │                                                                │
│ ▸ Cửu…   │        ┌────────────────────────────────────────────┐        │
│   12·4   │        │   base image (image_url) or neutral field    │        │  canvas: base + SVG region
│ ▸ Ô Trạch│        │   ◈ pins (abs % coords)  ⬡ regions (polygon) │        │  overlay + abs-positioned pins
│   31·0   │        │   ● drag ghost + live "x 0.62 · y 0.60 →PATCH"│        │
│ ▸ Loạn…  │        └────────────────────────────────────────────┘        │
│ + New map│                                                                │
├──────────┴──────────────────────────────────────────────────────────────┤
│  cursor 0.62,0.60 · 12 pins · 4 regions · owner-scoped                    │  footer: coord + counts
└──────────────────────────────────────────────────────────────────────────┘

   marker-detail popover (anchored to a selected pin):
   ┌ MARKER ─────────────────────── × ┐
   │ Label    [ Thanh Vân Môn        ] │
   │ Bound    [青云门 · location] rebind│  ← entity tie (soft glossary location UUID)
   │ Position [0.300] [0.580]          │  ← numeric fallback for the drag
   │ Type     [ sect                 ] │
   │ [Save] [Cancel]            [🗑]    │
   └───────────────────────────────────┘
```

- **Tool rail** switches interaction mode: **Select** (drag/click to select) · **Pin** (click-to-drop) ·
  **Region** (click-to-add-vertices, close to finish). Vanilla segmented control (`screen-…:354-359`).
- **Map rail** lists the world's maps (`listWorldMaps`) with pin/region counts + a `+ New map` CTA.
- **Canvas** reuses `WorldMapsSection`'s overlay math (`viewBox="0 0 100 100" preserveAspectRatio="none"`
  for regions; abs `left%/top%` for pins). Adds: drag handles, a mid-drag ghost + live coord readout, and
  polygon **vertex handles** for reshape.
- **Marker-detail popover**: relabel · **rebind/unbind** the glossary `location` entity · numeric
  position · `marker_type` · delete. Region-detail mirror: rename · rebind · delete (reshape is on-canvas).

### 3.3 Interaction → route mapping (the load-bearing part)

| Gesture | Persists via | Payload shape | Note |
|---|---|---|---|
| `+ New map` (name) | `POST …/maps` | `{name, image_ref?}` | image attached after, or now if pre-uploaded |
| **Upload base image** | `POST …/maps/{map_id}/image` (multipart) | `file` | **public JWT-resolved wrapper** over the internal core (§5) |
| Rename map | `PATCH …/maps/{map_id}` `If-Match: <version>` | `{name?}` | OCC on the map row |
| **Drop pin** (Pin mode) | `POST …/maps/{map_id}/markers` | `{label, x, y, entity_id?, marker_type?}` | mirror `world_map_add_marker` |
| 🔴 **Drag pin** (`onDragEnd`) | `PATCH …/markers/{marker_id}` | `{x, y}` | **absolute** new coords — stable `marker_id`, no churn |
| Relabel / rebind pin | `PATCH …/markers/{marker_id}` | `{label?}` / `{entity_id: <id>\|null}` | partial; `null` = unbind (§4.4) |
| Delete pin | `DELETE …/markers/{marker_id}` | — | mirror `world_map_remove_marker` |
| Draw region | `POST …/maps/{map_id}/regions` | `{name, polygon:[[x,y]…], entity_id?}` | ≥3 pts (`mcp_maps.go:199`) |
| **Reshape region** (`onDragEnd`) | `PATCH …/regions/{region_id}` | `{polygon:[[x,y]…]}` | vertex edit; whole polygon replace |
| Rename / rebind region | `PATCH …/regions/{region_id}` | `{name?}` / `{entity_id}` | partial |
| Delete region | `DELETE …/regions/{region_id}` | — | mirror `world_map_remove_region` |

🔴 **A pin drag is an UPDATE, not delete+recreate.** The client PATCHes the **absolute** new `(x,y)` to a
**stable** `marker_id`. This preserves the `entity_id` tie and is idempotent (re-applying the same
coordinate is a no-op). The draft renders the live `x 0.620 · y 0.600 → PATCH` readout precisely so the
contract it needs is unmistakable (`screen-…:444,485-488`). **Do NOT** simulate drag as remove+add.

### 3.4 The entity tie stays a SOFT cross-service UUID

A marker/region's `entity_id` points at a glossary `location` entity but carries **no FK** — book-service
and glossary are different services (`migrate.go:434` "soft cross-service ref … (nullable)"). Rebind swaps
the UUID; **unbind clears it**; deleting the glossary entity **must NOT cascade-delete the pin** — the pin
just renders unbound. The editor inherits the exact posture `world_map_add_marker` already takes
(`parseOptionalEntityID`, `mcp_maps.go:56-65`); it does **not** invent a hard link.

### 3.5 Every state, rendered

| State | Trigger | Render |
|---|---|---|
| **empty (no maps)** | world has 0 maps | *"No maps yet — draw the world your story lives in."* + **Create a map** CTA. Never the old "ask the assistant" delegation string. |
| **no world selected** | bare-id open, book has no world | the **world picker**, focused. Not an error. |
| **no base image** | `image_object_key` null | pins/regions on a neutral field (as `WorldMapsSection.tsx:58-62` already does) + an **Upload base image** prompt — never a blank box that reads as broken. |
| **loading** | list/detail in flight | skeleton over the canvas; the map rail stays live |
| **error (5xx/network)** | `getWorldMap` fails | message + **Retry**. Never an empty canvas that looks like an empty map. (Mirrors the read routes' strict-failure posture — a sub-read error is NOT a silently-empty map: `worlds_maps_rest.go:106-128`.) |
| **404** | map deleted/foreign, or world not owned | *"This map is no longer available."* + drop the selection. Owner+world scoped ⇒ **uniform 404, no existence oracle** (`worlds_maps_rest.go:93`) — we cannot distinguish gone-from-foreign and must not guess. |
| **OCC conflict (412) — map rename** | someone (or the agent) renamed first | the 412 body carries the current row; reseed the cache, keep the in-progress name, say *"This map changed elsewhere — reloaded."* Never clobber. |
| **drag mid-flight, then disconnect** | network drop during `onDragEnd` | the pin **snaps back to its last-saved coord** (optimistic-with-rollback); a toast offers retry. Because the write is a single atomic PATCH of a stable id, there is **no stranded-delete half-state** — the whole point of UPDATE over remove+add. |
| **cost gate** | — | **none. This panel spends nothing.** Every action is deterministic CRUD over Postgres/MinIO, $0, no LLM. No propose→confirm; adding one would be a defect. |

### 3.6 Scale

A world has few maps (tens), but a single map can carry **hundreds** of pins + regions. Coords are
normalized so the overlay is zoom-free. Pins **virtualize above ~200**; the polygon editor **caps
interactive vertices and simplifies on save** (Douglas–Peucker at a small epsilon) so a 4000-vertex
hand-drag doesn't ship a megabyte of JSONB. Reads reuse the single-query detail route (`getWorldMapREST`),
so cold-open cost is 2 requests (list + detail), same as `WorldMapsSection` today.

---

## 4 · Backend prerequisites — **the ONE big backend in S7**

Unlike the mostly-frontend S7 ports, this needs a real book-service build: **~10 routes, 3 MCP tools, and
one additive migration.** All are additive/forward-only; none touches an existing write path's behavior.

### 4.1 New public REST routes (book-service, mounted under `/v1/worlds`, auto-proxied)

All are mounted inside the existing `r.Route("/v1/worlds", …){ r.Route("/{world_id}", …) }` subtree
(`server.go:396-410`), so `requireWorldOwner` gates the world from the JWT and the map/marker/region query
re-scopes to `world_id`+`owner_user_id` (uniform 404, no oracle) exactly like the two read routes.

| # | Route | METHOD + path | Request | Response | Errors | Status |
|---|---|---|---|---|---|---|
| **R1** | create map | `POST /v1/worlds/{world_id}/maps` | `{name, image_ref?}` | `201 {map:{map_id,world_id,name,image_object_key,image_url?,version}}` | 400 name/uuid · 404 world · 500 | **MUST-BUILD** (mirror `world_map_create` `mcp_maps.go:93`) |
| **R2** | 🔴 rename map / set image | `PATCH /v1/worlds/{world_id}/maps/{map_id}` `If-Match:<version>` | `{name?, image_object_key?}` (presence-checked) | `200 {map:{…,version}}` | 400 · **428** If-Match absent · 404 · **412** `{code:"MAP_VERSION_CONFLICT",current:{…}}` | **MUST-BUILD — NOWHERE today** |
| **R3** | delete map | `DELETE /v1/worlds/{world_id}/maps/{map_id}` | — | `200 {deleted:true}` | 404 · 500 | **MUST-BUILD** (REST parity for `world_map_delete`; CASCADE + blob sweep already in the tool `mcp_maps.go:378`) |
| **R4** | 🔴 upload base image | `POST /v1/worlds/{world_id}/maps/{map_id}/image` (multipart `file`) | `file` | `200 {image_object_key,image_w,image_h,image_url,version}` | 400 file · 404 · 413 too-large · 415 type · 503 no-MinIO | **MUST-BUILD — public JWT wrapper over the internal core** |
| **R5** | add marker | `POST /v1/worlds/{world_id}/maps/{map_id}/markers` | `{label, x, y, entity_id?, marker_type?}` | `201 {marker:{marker_id,label,x,y,entity_id,marker_type,updated_at}}` | 400 (`x,y∈[0,1]`, label) · 404 · 500 | **MUST-BUILD** (mirror `world_map_add_marker`) |
| **R6** | 🔴 update marker | `PATCH /v1/worlds/{world_id}/maps/{map_id}/markers/{marker_id}` | `{x?, y?, label?, entity_id?\|null, marker_type?}` (presence-checked) | `200 {marker:{…,updated_at}}` | 400 range · 404 · 500 | **MUST-BUILD — THE LOAD-BEARING ROUTE, NOWHERE today** |
| **R7** | delete marker | `DELETE /v1/worlds/{world_id}/maps/{map_id}/markers/{marker_id}` | — | `200 {removed:true}` | 404 · 500 | **MUST-BUILD** (REST parity for `world_map_remove_marker`) |
| **R8** | add region | `POST /v1/worlds/{world_id}/maps/{map_id}/regions` | `{name, polygon:[[x,y]…]≥3, entity_id?}` | `201 {region:{region_id,name,polygon,entity_id,updated_at}}` | 400 (poly<3, range) · 404 · 500 | **MUST-BUILD** (mirror `world_map_add_region`) |
| **R9** | 🔴 update region | `PATCH /v1/worlds/{world_id}/maps/{map_id}/regions/{region_id}` | `{polygon?:[[x,y]…], name?, entity_id?\|null}` | `200 {region:{…,updated_at}}` | 400 · 404 · 500 | **MUST-BUILD — NOWHERE today** |
| **R10** | delete region | `DELETE /v1/worlds/{world_id}/maps/{map_id}/regions/{region_id}` | — | `200 {removed:true}` | 404 · 500 | **MUST-BUILD** (REST parity for `world_map_remove_region`) |

🔴 **R4 correction to the draft's framing.** The draft (and the task brief) call the upload a
"gateway `user_id`-injected wrapper." That is **not** how book-service works: `/v1/worlds/*` handlers
resolve identity **themselves** from the forwarded `Authorization: Bearer` (`requireUserID`,
`server.go:434-449`) — the gateway injects **nothing**. So the correct design is a **new public
book-service route** that resolves `userID` from the JWT and calls the **same multipart core** as the
internal handler. Refactor `uploadWorldMapImage` (`maps_image.go:30`) into
`uploadWorldMapImageCore(ctx, w, r, mapID, ownerID)`; the existing internal handler passes
`ownerID` from `?user_id` (unchanged), the new public handler passes `ownerID` from `requireUserID`. The
internal route stays for trusted callers; **the browser gets a first-party route, not an injected query
param.** Confirm gate: `mapOwnerID`/`requireMapOwner` (`mcp_maps.go:31-54`) already scope a map by owner.

### 4.2 New MCP tools (MCP-first parity for the NEW update capability)

The create/add/remove REST routes above are **parity mirrors of tools that already exist** — no new tool.
But **UPDATE is net-new agentic logic** and MCP-first governs it: each update route needs a `world_map_update_*`
tool sibling so the agent can move a pin it placed wrong (the incident in §1). Register in
`registerMapTools` (`mcp_maps.go:465`), TierA, ScopeNone, mirroring the add tools.

| Tool | Input (Go struct, `jsonschema` tags) | Effect |
|---|---|---|
| **`world_map_update`** | `{map_id, name?, image_ref?}` | rename map / repoint image; owner-gated via `requireMapOwner` |
| 🔴 **`world_map_update_marker`** | `{marker_id, x *float64, y *float64, label *string, entity_id string, clear_entity bool, marker_type *string}` | move / relabel / rebind / retype one marker |
| **`world_map_update_region`** | `{region_id, polygon [][]float64?, name *string, entity_id string, clear_entity bool}` | reshape / rename / rebind one region |

🔴 **Partial-update correctness — the pointer rule (a real bug this prevents).** The **add** tools take
`X float64` (`mcp_maps.go:133`). If the **update** tools copy that, a `world_map_update_marker` that only
means to relabel would send `x=0, y=0` and **teleport the pin to the top-left corner**. So update-tool
numeric/text fields MUST be **pointers** (`*float64`, `*string`): `nil` = "not provided, leave it";
non-nil = "set it". The SQL builds a dynamic `SET` of only the provided columns (mirror `patchWorld`'s
`setClauses`/`paramIdx` loop, `worlds.go:275-300`) — **never** a blanket `UPDATE … SET x=$1,y=$2,label=$3`.
Range-validate `x/y ∈ [0,1]` and `polygon ≥ 3 pts` only when the field is present. This is the
[`chapter-blocks-null-nontext-coalesce`] / [`noop-guard-on-partial-data`] trap in a new costume.

Go MCP is **single-schema-source** (jsonschema struct tags → `addTool`), so the 3-schema-source FastMCP
strip that bites Python tools does **not** apply here — but the pointer rule does, doubly.

### 4.3 The migration — additive, forward-only, and it must be READ

Update needs a freshness signal on each row. Current schema: `world_maps` has `updated_at` but **no
version**; `map_markers` / `map_regions` have **only `created_at`** — no `updated_at`, no version
(`migrate.go:426,439,449`). Append to `schemaSQL` (the boot-idempotent DDL, the file's own convention —
`ALTER TABLE … ADD COLUMN IF NOT EXISTS` is used ~30× already, e.g. `migrate.go:36`) **and** add the
columns to the `CREATE TABLE` literals for fresh DBs:

```sql
ALTER TABLE world_maps  ADD COLUMN IF NOT EXISTS version    INT NOT NULL DEFAULT 1;
ALTER TABLE map_markers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE map_regions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
```

⚠ **Two repo hazards, handled explicitly:**

1. **`ADD COLUMN IF NOT EXISTS` never revisits a bad default** ([`add-column-if-not-exists-never-revisits-a-bad-default`]; the file even warns about it at `migrate.go:1363`). Here the baselines are **correct by construction** — `version=1` is the right first version for every existing map; `updated_at=now()` is the right "last touched ≈ now" for legacy rows. There is **nothing to revisit**, so IF-NOT-EXISTS is safe. (Do **not** later try to "fix" these defaults; there is no bad one.)
2. **A column added but never read is write-only** ([`fixtures-can-seed-a-field-the-writer-never-sets`], and the Settings-law "consumed, proven by effect"). So the **same commit** wires the reads:
   - `map.version` → `SELECT`ed and returned by `getWorldMapREST` / `listWorldMaps` (`worlds_maps_rest.go`) **and** `world_map_get`/`world_map_list` (`mcp_maps.go:263,349`);
   - `marker.updated_at` / `region.updated_at` → added to `markerOut`/`regionOut` (`mcp_maps.go:232-245`) and the REST detail;
   - a test asserts each field **round-trips** (create → read → non-null; PATCH → version bumps / `updated_at` advances). A stored-but-unread column reds.

### 4.4 OCC posture — deliberate, per-object, and documented

- **Map rename/image (R2, `world_map_update`): OCC via `version`, `If-Match` REQUIRED.** A map name is a
  field where a silent clobber is surprising. `If-Match` absent ⇒ **428 Precondition Required** (the
  `arc-inspector` BE-A2 lesson — an *optional* `If-Match` makes a blind clobber a legal request; do not
  repeat it). PATCH bumps `version = version + 1`; a mismatch returns **412** with the current row so the
  client reseeds and re-applies (§3.5).
- **Marker/region (R6, R9): last-write-wins on absolute fields, NO version gate — a CONSCIOUS divergence,
  not the BE-A2 oversight.** Rationale, stated so a reviewer can check it: (a) worlds have **no E0
  sharing** — a map is strictly single-owner (`mcp_maps.go:7`), so the only concurrent writer is the
  owner's **own agent**, whose Lane-B refresh (§6) reseeds the panel; (b) a marker write is an **absolute
  coordinate / a whole-polygon replace** — idempotent, not a delta-on-top, so a "lost update" just means
  the later position wins, which is the correct semantics for a drag; (c) PATCH is **partial-field**
  (§4.2), so a concurrent relabel and rebind touch **disjoint columns** and don't fight. `updated_at` is
  still added + read so the client can show "edited" and Lane-B reconciles. Bolting integer-version OCC
  onto a 60-fps drag would be friction for a race that the tenancy model forbids. **This is the one place
  the spec knowingly diverges from full OCC; it is here in writing precisely so it is not "discovered"
  later as a gap.**
- **omitted-vs-null (unbind):** REST PATCH decodes into `map[string]any` and **presence-checks** keys
  (mirror `patchWorld`, `worlds.go:270-300`): key absent ⇒ leave; `{"entity_id": null}` ⇒ **unbind**;
  `{"entity_id":"<uuid>"}` ⇒ rebind. MCP can't distinguish absent-nil from present-nil in a Go struct, so
  the tools carry an explicit **`clear_entity bool`** alongside `entity_id string` (empty ⇒ untouched
  unless `clear_entity`). This is the [`rest-write-mirror-drops-fields-the-mcp-tool-accepts`] class,
  pre-empted.

---

## 5 · Tenancy · Settings · OCC · Cost — stated, not assumed

**Tenancy (scope key).** `world_maps.owner_user_id` is the scope; **worlds have NO E0 sharing**
(`mcp_maps.go:7`, `worlds.go` has no grant path — only `requireWorldOwner`). Every route/tool filters
`owner_user_id` (markers/regions via a JOIN to `world_maps`, `mcp_maps.go:431-433`), and a
foreign/missing row is a **uniform 404 with no existence oracle**. There is **no System tier**, no
shared user-editable row, no `book_id`/grant here — a map belongs to exactly one user. The new routes add
**no new scope surface**; they inherit `requireWorldOwner` + the map-owner JOIN unchanged. ✅ No tenancy
defect: the classic "any authenticated user can write a shared row" bug cannot occur because there is no
shared row.

**Settings (SET-1..8).** **Zero.** No toggle, mode, threshold, model, or env flag. The tool rail's
Select/Pin/Region is **per-device ephemeral UI mode**, not a persisted setting (like a cursor tool) — it
lives in component state, never in `/v1/me/preferences`, never localStorage-as-data. Nothing to resolve,
nothing to expose a "source tier" for.

**OCC.** Per §4.4: `If-Match`+`version` on the map rename (428 when absent, 412 with current row);
last-write-wins on the single-owner idempotent marker/region writes, with the divergence documented.

**Cost gate.** **None, by construction.** Every action is deterministic CRUD + a MinIO upload — $0, no
LLM, no provider call. There is **no propose→confirm** here and adding one would be a defect. (If a future
agent adds an LLM "auto-place these places on the map" action, it goes through the **generic**
composition/book action-preview→confirm spine, never a bespoke per-action estimate route.)

**Provider law.** N/A — no LLM/embedding/rerank/image-gen call anywhere in this surface. (The base image
is a **user upload**, not a generated asset.)

---

## 6 · Registration checklist (GG-8) — exact files, in order

Panel id **`world-map`** is **openable by bare id** (§3.1), so **every** step applies (no
`hiddenFromPalette` shortcut). Move **py-enum == contract-enum == openable-set** by **+1 in lockstep** —
assert the **delta and the three-way equality**, never a literal count (S7 lands several panels; the
baseline shifts).

| # | File | Change |
|---|---|---|
| 1 | `frontend/src/features/studio/panels/WorldMapEditorPanel.tsx` **(new)** | the dock panel. Root `data-testid="studio-world-map-panel"`. `useStudioPanel('world-map', props.api)`. Reads `props.params as WorldMapFocusParams \| undefined` ({worldId?, mapId?}). Thin — renders the editor body from `features/world`. |
| 1b | `frontend/src/features/world/components/WorldMapEditor.tsx` **(new)** | the editor view (tool rail, map rail, canvas, popovers). Reuses `WorldMapsSection`'s overlay math; **render-only** (MVC). |
| 1c | `frontend/src/features/world/hooks/useWorldMapEditor.ts` **(new)** | the controller — map/world selection, the write mutations (create/upload/add/**update**/delete), optimistic drag + rollback, cache invalidation. No JSX. Extends `useWorldMaps`'s query keys. |
| 1d | `frontend/src/features/world/api.ts` | add the ~10 writer methods (`createMap`, `uploadMapImage`, `patchMap`, `addMarker`, `patchMarker`, `deleteMarker`, `addRegion`, `patchRegion`, `deleteRegion`, `deleteMap`) beside the existing `listWorldMaps`/`getWorldMap`. |
| 1e | `frontend/src/features/world/types.ts` | add `version:number` to `WorldMapSummary`; `updated_at:string` to `WorldMapMarker`/`WorldMapRegion` (§4.3 — the widened wire). |
| 2 | `frontend/src/features/studio/panels/catalog.ts` | one row **in the S7 block** (`catalog.ts:315`): `{ id:'world-map', component:WorldMapEditorPanel, titleKey:'panels.world-map.title', descKey:'panels.world-map.desc', category:'storyBible', guideBodyKey:'panels.world-map.guideBody' }`. `'storyBible'` **is** in `CATEGORY_ORDER` (`useStudioCommands.ts:27`) — verified, no X-2 block. |
| 3 | `frontend/src/i18n/locales/en/studio.json` | `panels.world-map.title` / `.desc` / `.guideBody` |
| 4 | `frontend/src/i18n/locales/{ar,bn,de,es,fr,hi,id,ja,ko,ms,pt-BR,ru,th,tr,vi,zh-CN,zh-TW}/studio.json` | same 3 keys × 17 locales — **`python scripts/i18n_translate.py`**, never hand-written |
| 5 | `services/chat-service/app/services/frontend_tools.py` | **two edits**: (a) append `"world-map"` to the `panel_id` enum (`:402`); (b) append its clause to the description prose (~`:480`) — the model's only hint the panel exists. Suggested: *"'world-map' = create and edit a world's reference map(s) — upload a base image, drop and drag location pins, draw and reshape regions, and bind them to glossary location entities."* |
| 6 | `contracts/frontend-tools.contract.json` | **regenerate, never hand-edit:** `cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py`. Commit the regenerated JSON in the **same commit** as steps 2 + 5. |
| 7 | `frontend/src/features/studio/agent/handlers/worldEffects.ts` **(NEW FILE)** | **MANDATORY (Lane-B / X-4):** `registerEffectHandler(/^world_map_/, worldMapEffect)` → `invalidateQueries(['world-maps'])` + `['world-map']`. Use `unwrapToolResult` (envelope-nested payload). One home for `world_map_*` — a single broad pattern. |
| 8 | `frontend/src/features/studio/agent/handlers/index.ts` | add `registerWorldEffectHandlers` / `_resetWorldEffectHandlers` to the barrel (`index.ts:19-34`) — a handler file not in the barrel is **dead in the app** and the ledger reds. |
| 9 | `frontend/src/features/studio/agent/__tests__/effectCoverage.contract.test.ts` | **delete** `worldEffects: 'wave-8'` from `PENDING_FILES` (`:117`) so the 6 existing `world_map_*` write tools move to **covered**; **add** the 3 NEW tools (`world_map_update`, `_update_marker`, `_update_region`) to `WRITE_TOOLS` so coverage checks them too. ⚠ Drift note: the ledger pre-labels `worldEffects` "wave-8 (spec 38)", but the PO sealed world-map into **S7** — this spec delivers it now; the label is stale, the coverage still holds. |
| — | `frontend/src/features/studio/onboarding/tours.ts` | **skip** — not a role-tour step in v1. |

**Verify (drift-locks green):**
```
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
cd frontend && npx vitest run \
  src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
  src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
  src/features/studio/palette/__tests__/useStudioCommands.test.ts \
  src/features/studio/agent/__tests__/effectCoverage.contract.test.ts \
  src/features/chat/nav/__tests__/frontendToolContract.test.ts
```

**Do NOT touch:** `StudioDock.tsx` / `StudioFrame.tsx` / `useStudioCommands.ts` / `UserGuidePanel.tsx`
(all derive from `catalog.ts`); `gateway-setup.ts` (the `/v1/worlds*` passthrough is generic — new nested
routes ride it for free).

---

## 7 · Agent surface / MCP parity

**Existing tools driving this domain (8, `mcp_maps.go:465-515`):** `world_map_create` · `_add_marker` ·
`_add_region` · `_get` · `_list` · `_delete` · `_remove_marker` · `_remove_region`.

**This spec ADDS 3 (§4.2):** `world_map_update` · `world_map_update_marker` · `world_map_update_region`
— because UPDATE is net-new agentic logic and MCP-first requires the agent to have it too (the "agent
can't move a pin it placed wrong" incident, §1). After this ships there is **no INVERSE gap** (GG-2): the
human and the agent can each create/read/update/delete every map object.

**Lane-B effect handler (X-4) — step 7 above. Mandatory, not conditional.** Without it, the agent moves a
pin and the open editor shows the stale coord; the user's next drag then writes over a position they were
never shown. The handler closes the "agent and human share one map" loop.

**`resource_ref` (deep-link).** If/when spec 28's `resource_ref` lands, `world-map` consumes one variant
`{kind:'world_map', id:'<map_id>', world_id:'<world_id>'}` → `openPanel('world-map', {worldId, mapId})`.
The panel core (book-derivation + picker) ships **without** it — decompose, don't block.

---

## 8 · Milestones / slices (each = one commit, with a DoD evidence string)

| # | Slice | DoD evidence |
|---|---|---|
| **M1** | **Migration + reads** — the 3 columns (§4.3) + wire `version`/`updated_at` into all 4 read doors (REST list/detail + `world_map_get`/`_list`) | `go test ./...` green; a test asserts `version`/`updated_at` **round-trip** (create→read non-null); an existing map after migrate reads `version=1`. No behavior change to writes. Evidence: `book-service go test: N pass; version/updated_at round-trip asserted`. |
| **M2** | **REST parity mirrors** — R1/R3/R5/R7/R8/R10 (create/delete map, add/delete marker, add/delete region) + R4 public image wrapper (refactor `uploadWorldMapImageCore`) | `go test` green incl. owner-scope 404 (foreign map), `[0,1]`/poly≥3 validation, image type/size gates; the internal image route still passes (core unchanged). Evidence: `live smoke: POST /v1/worlds/{w}/maps → 201, upload image → image_url, add marker → 201` on a stacked book-service. |
| **M3** | 🔴 **UPDATE — R2/R6/R9 + `world_map_update{,_marker,_region}`** (the hole) | `go test`: PATCH marker `{x,y}` moves it **keeping `marker_id`**; a **label-only** PATCH does **not** move it (the pointer rule — a non-pointer would teleport to 0,0); map rename **without `If-Match`→428**, stale→**412 with current row**; unbind via `{"entity_id":null}` / `clear_entity`. Evidence + `pytest`/`go test` counts. |
| **M4** | **The panel, read + create/upload** — catalog row + enum + contract regen + i18n×18 + WorldMapEditorPanel/Editor/hook + world/map picker + all states §3.5 + `+ New map` + image upload | the drift-lock suites green (delta+3-way equality). Panel opens from palette **and** `ui_open_studio_panel`. Creates a map, uploads an image, renders real pins/regions. |
| **M5** | **The writes on canvas** — drop pin · **drag pin (`onDragEnd`→PATCH)** · draw/**reshape** region · marker/region popover (relabel/rebind/unbind/delete) · optimistic drag + rollback · `worldEffects.ts` + barrel + PENDING removal | drag persists an **absolute** coord with a **stable `marker_id`** (grep the network tab: one PATCH, no remove+add); an agent `world_map_update_marker` refreshes the open editor without a manual reload. |

---

## 9 · Definition of Done

1. **Suites green** — the 5 drift-lock suites in §6, plus `book-service go test` for M1–M3 and
   `frontend vitest` for the panel/hook.
2. **The `UPDATE` hole is closed at every layer** — `grep`: `PATCH .../markers/` and `world_map_update_marker`
   both resolve; a pin drag issues **one PATCH**, never a `DELETE`+`POST` pair.
3. **The old delegation string is gone** — the editor's empty state no longer says "ask the assistant to
   make a map"; a human can create one.
4. 🔴 **LIVE BROWSER SMOKE — mandatory** ([`agent-gui-loop-needs-live-browser-smoke-not-raw-stream`]).
   Rebuild the image first ([`live-smoke-rebuild-stale-images-first`]), sign in as
   `claude-test@loreweave.dev`, drive dockview via `evaluate`+`data-testid`
   ([`playwright-live-dockview-automation-recipe`]), CDP mouse for the drag
   ([`playwright-cdp-mouse-drives-d3-drag`] — synthetic events won't drive a real drag):
   1. `⌘P` → **Open World Map** → the dock tab mounts;
   2. pick a world → **+ New map** → it appears in the rail **without a manual reload**;
   3. **upload a base image** → the canvas renders it;
   4. **drop a pin**, bind it to a glossary `location` entity → the tie renders (violet);
   5. 🔴 **drag the pin** → on release, **one `PATCH /markers/{id}`** fires (assert via the network log),
      the `marker_id` is **unchanged**, and the `entity_id` tie **survives**;
   6. **draw a region**, then **drag a vertex** to reshape → one `PATCH /regions/{id}`;
   7. **rename the map** → save → force a conflict by `world_map_update` from the agent, save again →
      *"changed elsewhere — reloaded"*, retry succeeds (the map-OCC path);
   8. **the agent leg:** in Compose, `world_map_update_marker {marker_id, x, y}` → the open editor's pin
      **moves without a manual reload** (Lane-B proven by EFFECT, not by a `shown:true` in the raw stream);
   9. `ui_open_studio_panel {panel_id:"world-map"}` → the tab mounts.
5. **No silent-fail** — a transient DB error on the markers sub-read returns an **error state**, not a map
   with pins silently dropped (the read routes already enforce this, `worlds_maps_rest.go:106-128`; the new
   writers must too).
6. **SESSION** — S7 RUN-STATE slice board updated (this panel's build slices appended with evidence
   strings), the `worldEffects` PENDING row cleared, decisions/drift registers appended.
7. **`/review-impl` on the diff** — this is load-bearing (new service routes + a migration + a tenancy
   boundary); run the adversarial pass and fold its findings in before COMMIT.

---

## 10 · Open questions / Deferred

| # | Question | Disposition |
|---|---|---|
| **OQ-1** | Does `world-map` need a studio-bus `activeWorldId`/`activeMapId` slice (like `arc-inspector`'s `activeArcId`) so the sibling `world` panel (S7·1) and the agent's `resource_ref` can point at it? | **DEFERRED — gate #3 (naturally-next-phase).** v1 resolves via `props.params` + book→world derivation + in-panel picker, which covers every entry with no dead pane. Add the slice **when the `world` panel lands** and actually needs to publish a selection; adding it now is speculative. Row: `D-WORLDMAP-BUS-SLICE`. |
| **OQ-2** | Should marker/region get **integer-version OCC** rather than the documented last-write-wins (§4.4)? | **Conscious won't-fix (gate #5) for v1**, with the rationale in §4.4 (single-owner tenancy + absolute idempotent writes + partial-field PATCH). Revisit **only if** worlds ever gain E0 sharing — at which point maps become multi-writer and this decision genuinely changes. Row: `D-WORLDMAP-MARKER-OCC` (trigger: worlds gain sharing). |
| **OQ-3** | Marker↔entity binding: is the target a **glossary `location` entity** or a **KG entity**? The soft `entity_id` is untyped (`migrate.go:434` just says "glossary location entity"). | **CODE-LEANED glossary (CLARIFY-SYNTHESIS 2026-07-16) → NEEDS_PO#2 for final confirm.** The schema documents the intent — `mcp_maps.go:135` jsonschema says "glossary location entity" — and the two-layer law (glossary = authored SSOT; knowledge = derived) points the picker at **glossary `location` entities**. Confirmed there is **no write-side validation** (free cross-service UUID, no FK), so **write stays unenforced** (hard-enforcing a kind would break existing agent-written markers). ⚠ **Cross-spec note:** s7-3's place-graph binds **KG** `location` entities (knowledge-service), while these raster markers bind **glossary** entities — a *by-design* divergence (different services/data, per both specs' headers), but it means a place authored in place-graph is not the same row a world-map marker binds. **🔒 SEALED (PO, 2026-07-16): Option B — BOTH bindable.** The rebind picker offers **glossary `location`
entities AND KG-only entities**. The write stays unenforced (soft untyped `entity_id`, no FK), so existing
agent-written markers still render and no migration is needed. ⚠ The picker must **label the source**
(glossary vs KG) so the user knows which layer a pin ties into — the two-layer distinction is surfaced,
not hidden. The by-design divergence from place-graph (which binds KG `location`) stands and is now
partially bridged: a world-map marker MAY bind the same KG entity a place-graph node created. Row
`D-WORLDMAP-ENTITY-BINDING-SOURCE` → CLOSED (decided). |
| **OQ-4** | Region polygon **simplification epsilon** and the **interactive vertex cap** (§3.6) — what values? | **UNVERIFIED — no existing consumer sets one.** A hand-drawn region can carry thousands of vertices; the cap/epsilon are perf knobs to set from a real trace, not a guess (perf items: fix when profiling shows pain, gate #4). Ship a conservative default (e.g. cap 200 interactive handles, simplify at ε=0.002 of the normalized axis) and tune later. Row: `D-WORLDMAP-POLY-SIMPLIFY`. |
| **OQ-5** | `world_maps.updated_at` **already exists but is never READ** (`migrate.go:427`; no `SELECT` includes it, `worlds_maps_rest.go:35,88`). Should the map use it instead of a new `version`? | **NO — add `version`.** Timestamp OCC is fragile (precision/clock skew) and the repo's OCC pattern is a monotonic `INT` (arc uses `version`). `updated_at` stays as a display/audit field; `version` is the ETag. Resolved in this spec (§4.3), noted so a reviewer doesn't flag the "redundant" column. |
| **OQ-6** | Should `DELETE map` (R3) report the count of markers/regions it CASCADE-dropped? | **Client-derives it from the loaded detail** (it already holds the pin/region counts). The tool response `{deleted:true}` (`mcp_maps.go:406`) is a silent-blast-radius (OUT-5), but the confirm dialog can say *"Delete 'Cửu Châu' and its 12 pins + 4 regions?"* from state. Not worth a response-shape change for one caller. **UNVERIFIED** whether any other consumer wants the count. |
