# 32 · Arc Inspector — CRUD for the spec tree that steers every generation

> **Status:** 📐 specced 2026-07-13 · branch `feat/context-budget-law` (studio track) · **M** (files≈12, logic≈6, side_effects=2)
> **Type:** FS — **~90% frontend port-and-build; 3 small backend fixes the audit missed** (§5).
> **Closes:** **G-ARC-SPEC-CRUD** (P0, CONFIRMED) — [`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) §5.1. **Wave 2** of that plan.
> **This IS** [`23_book_architecture.md`](23_book_architecture.md)'s **C3**, tracked as **DBT-06** in `docs/plans/2026-07-12-book-package-RUN-STATE.md:216` ("#4 genuinely-upstream").
> **Unblocks:** [`24_plan_hub_v2.md`](24_plan_hub_v2.md) **H3.1** — `PlanDrawer.tsx:351` renders a visible in-UI note saying this inspector is not built.
> **Consumes:** plan-30 **X-6** (`resource_ref`) for the agent deep-link · plan-30 **X-4** (Lane-B handlers) for agent-write freshness.
> Follows [`docs/standards/dockable-gui.md`](../../standards/dockable-gui.md) (DOCK-1..11) and [`docs/standards/mcp-tool-io.md`](../../standards/mcp-tool-io.md) (IN-1..8 / OUT-1..6).

---

## 1 · Why this exists

`structure_node` — the saga→arc→sub-arc **spec tree** — is not decoration. It is **read into every
generation prompt**:

```
services/composition-service/app/packer/lenses.py:257
  async def gather_arc(structure_repo, structure_node_id, *, story_order, ...)
    """23 BA12 — the ARC lens: the durable spec layer (`structure_node`) reaching
       the prompt. This is the anti-write-only proof for the whole spec — a chapter
       assigned to an arc must STEER generation, and the D2 effect test asserts this
       frame CHANGES when the arc's `tracks` change."""
```

**Which fields actually reach the prompt — read from `gather_arc`, not assumed.** This precision is
load-bearing: it is the difference between an editor and a *write-only* editor (the motif-packer-lens
bug class CLAUDE.md bans). `gather_arc` (`lenses.py:257-360`) resolves **exactly** these:

| Field | Reaches the prompt? | The consumer |
|---|---|---|
| `title` (of **every** node in the chain) | ✅ | `gather_arc` — *"Arc chain: saga "X" → arc "Y""* |
| `goal` | ✅ **of the LEAF node only** (`chain[-1].goal`, `lenses.py:303`) | an ancestor saga's `goal` is **dropped** |
| `tracks` (merged) | ✅ | `resolve_tracks` → *"Tracks: revenge: …"* |
| **`roster_bindings`** (merged) | ✅ | `resolve_roster_bindings` → *"Cast bindings: protagonist → …"* |
| `span` / `open_promises` | ✅ (derived) | pacing % + the promise rollup |
| **`roster`** (the abstract slot list) | ❌ **NOT a packer input.** `resolve_roster` is **never called by the packer** | its real consumer is `extract_template_from_arc` (`arc_apply.py:564`) — it is the *schema* the bindings fill, and Wave 4's template extractor reads it |
| **`summary`** | ❌ **no engine consumer at all** | a human-read field (the picker, the Hub drawer) |
| `status` | ❌ no engine consumer (OQ-5) | an author's label |

⚠ **Do not say "roster reaches the prompt" — `roster_bindings` does.** Do not tell the user `summary`
steers generation; it does not. Both halves of this table are honest, and **both** are worth a GUI —
but only the ✅ rows get the anti-write-only proof (DoD #5).

And a human cannot write any of them.

| Capability | Agent (MCP) | Human (GUI) |
|---|:--:|:--:|
| list the tree | `composition_arc_list` ✅ | ✅ `plan-hub` (`plan-hub/api.ts:20`) |
| **read one arc, enriched** | `composition_arc_get` ✅ | ❌ **no caller anywhere** |
| **create an arc/saga** | `composition_arc_create` ✅ | ❌ |
| **edit title/goal/summary/status/tracks/roster/bindings** | `composition_arc_update` ✅ | ❌ |
| **archive an arc** | `composition_arc_delete` ✅ | ❌ |
| **restore an archived arc** | `composition_arc_restore` ✅ | ❌ |
| move/reparent | `composition_arc_move` ✅ | ✅ `plan-hub/api.ts:190` |
| assign chapters | `composition_arc_assign_chapters` ✅ | ✅ `plan-hub/api.ts:241` |

**The FE consumes 3 of 8 tools and 3 of 8 REST routes.** Every one of the 5 missing routes exists,
is grant-gated, is OCC'd, and has **zero frontend consumers** (verified by grep across
`frontend/src`, and by `inv-composition-rest.md:69-73`).

The product this ships today: *the agent can author the object that steers your prose; you can only
drag it around.* That is GG-1's law violated on the sharpest possible object — and the Hub **says so
in the UI**:

```tsx
frontend/src/features/plan-hub/components/PlanDrawer.tsx:351
  <p data-testid="plan-drawer-arc-gap" …>
    The full arc inspector (Structure · Roster · Chapters · Conformance · Provenance — 23 C3) is not
    built yet; this is a minimal summary.
  </p>
```

**This is not a port.** Unlike Wave 1's canon rules or Wave 3's motif library, there is **no legacy
component to move** — `grep -rn "arc-inspector\|ArcInspector" frontend/src` → nothing. The arc
inspector has never existed on any surface. This spec builds it.

---

## 2 · What is already built (be precise — this is what makes the estimate trustworthy)

**Backend: 100% of CRUD, minus 3 defects (§5).** Read from source, not from the audit.

| Route | File | Status |
|---|---|---|
| `GET /v1/composition/books/{book_id}/arcs` | `app/routers/arc.py:413` | ✅ tree + derived block, one query, no N+1 |
| `GET /v1/composition/arcs/{node_id}` | `arc.py:438` | ✅ **enriched**: `resolved.{tracks,roster,roster_bindings}` + `span` + `open_promises` |
| `POST /v1/composition/books/{book_id}/arcs` | `arc.py:466` | ✅ 201, `created_by` server-stamped |
| `PATCH /v1/composition/arcs/{node_id}` | `arc.py:489` | ✅ OCC → 412 returns the **current row** — ⚠ but `If-Match` is **optional** (§5 BE-A2) |
| `DELETE /v1/composition/arcs/{node_id}` | `arc.py:516` | ✅ soft archive, **cascades to the subtree** (`structure.py:404`) |
| `POST /v1/composition/arcs/{node_id}/restore` | `arc.py:528` | ✅ restores subtree **and reconnects the archived ancestor chain** (`structure.py:426`) |
| `POST /v1/composition/arcs/{node_id}/move` | `arc.py:540` | ✅ consumed by the Hub |
| `POST /v1/composition/books/{book_id}/arcs/assign-chapters` | `arc.py:560` | ✅ consumed — ⚠ **add-only, no unassign** (§5 BE-A3) |

Gating is uniform and already correct: `_gate_arc` (`arc.py:383`) resolves the arc's book **from the
row** then gates the caller's E0 grant on **its** `book_id` — the `worker-loaded-id-needs-parent-scoping`
pattern. A missing node and a denied grant return the **same** uniform 404 (no existence oracle).

**Frontend: the seams exist, the panel does not.**

| Piece | Where | Reuse verdict |
|---|---|---|
| `getArcs` shell + `['plan-hub','arcs',bookId]` cache | `plan-hub/api.ts:20` | **reuse** — the inspector reads the same cache (no second fetch) |
| the OCC write pattern (If-Match → 412 → "changed elsewhere — reloaded" + `setQueryData` re-seed) | `plan-hub/hooks/usePlanNodeWrites.ts:55-78` | **mirror exactly** — it already carries the `instant-commit-control-over-occ-entity` fix |
| the serialized-write chain (back-to-back edits on one OCC row) | `panels/useSceneInspector.ts:43-45` | **mirror exactly** |
| `props.params` deep-link seam on a palette-openable panel | `panels/QualityCanonPanel.tsx:34` (`props.params as CanonFocusParams`) | **the precedent that kills X-12** — see §3.1 |
| per-arc conformance badge (`ConformanceStatus.arcs[].{dirty,dirty_reasons,stale_chapters}`) | `panels/useConformanceStatus.ts` | **reuse — zero new backend** |
| entity-name resolution for `roster_bindings` | `composition/hooks/useGlossaryRoster.ts` | **reuse** |
| arc-template title for provenance | `composition/motif/arcApi.ts:26` (`arcApi.get`) | **reuse the API layer only** (it is a plain typed fetch, not legacy-page-coupled) |

**Not built, and required:** an `activeArcId` bus slice. `host/types.ts:43-66` has `chapter`,
`scene`, `selection`, `qualityIssue`, `planFocusNode` — **no arc**. §3.1 adds one.

---

## 3 · The design

### 3.1 The addressing decision — and why `arc-inspector` is NOT an X-12 panel

Plan-30 §8.2 **X-12** warns: *"panels that need `params` are structurally OUTSIDE the agent enum"*,
because `ui_open_studio_panel` carries a **bare `panel_id` and nothing else**
(`frontend_tools.py:484` — `"required": ["panel_id"]`, `additionalProperties: false`). It names
`arc-inspector` as an example, and concludes it must be `hiddenFromPalette`.

**That conclusion is wrong, and the counter-example is already shipped.** `scene-inspector` needs a
scene id, is **in the enum**, **in the palette**, and **in the User Guide** — because it takes its
subject from the **studio bus**, not from a tool arg:

```ts
frontend/src/features/studio/panels/useSceneInspector.ts:24
  const activeSceneId = useStudioBusSelector((s) => s.activeSceneId);
```

`quality-canon` proves the other half: it is enum-listed **and** accepts an optional in-studio
`props.params.focusRuleId` for the deep-link from `plan-hub` (`PlanHubPanel.tsx:72`).

**AI-1 (LOCKED). `arc-inspector` is a detail-pane-over-a-selection, exactly like `scene-inspector`.**
It is **palette-openable by bare id**, goes **into the enum**, and resolves its subject in this
precedence:

1. `props.params.arcId` — an in-studio deep-link (`plan-hub` row → inspector; `manuscript-navigator`
   arc header → inspector). Same seam as `quality-canon`'s `focusRuleId`.
2. `bus.activeArcId` — the **new** bus slice (below). This is what an agent's `resource_ref` lands on.
3. **an in-panel arc picker** — a `<select>` over the shell tree, so a bare-id open (palette, agent,
   User Guide) is **never a dead panel**. Opening with no selection shows the picker + a *"Create the
   first arc"* CTA, never a blank pane.

**The bus slice (additive, `host/types.ts`):**

```ts
// StudioBusEvent
| { type: 'arc'; arcId: string }
// StudioBusSnapshot
activeArcId?: string;
// applyBusEvent
case 'arc': return { ...base, activeArcId: e.arcId };
```

`plan-hub` publishes it on an arc/saga node selection; the inspector subscribes. This is the same
one-line-per-slice shape as `scene`, and it is the **only** studio-internal transport the agent needs
(§7).

⚠ **Do NOT extend `ui_open_studio_panel` with a `params` arg for this panel.** That is a
Frontend-Tool-Contract change (schema + `CLOSED_SET_ARGS` + regen + **both** resolvers) with a real
free-string hazard, and this panel does not need it. If Wave 3's `motif-editor` genuinely needs a
by-id open, decide it there, on its own evidence.

### 3.2 Panel layout — `arc-inspector` (category `editor`)

One column, ~470px, mirroring `scene-inspector`'s section rhythm. Every section states which route
feeds it.

```
┌─ ARC INSPECTOR ────────────────────────── [⟳] [⤢] [×] ─┐
│ ▾ [ Arc 3 · The Betrayal at Cold Harbor      ▾ ]  ← picker (shell tree, indented by depth)
│   SAGA › ARC › SUB-ARC breadcrumb (ancestor_chain)      │
│   [outline ▾]  v7   ⟳ dirty · 4 stale chapters          │  ← status select (OCC) + conformance badge
├─ IDENTITY ──────────────────────────────────────────────┤  GET /arcs/{id}
│   Title       [ …                                    ]  │  → prompt (whole chain)
│   Goal        [ …                                    ]  │  → prompt (LEAF only — say so)
│   Summary     [ …                                    ]  │  human-read label — NOT a prompt input
├─ TRACKS ───────────────────────── own ⊕ inherited ──────┤  resolved.tracks → PROMPT
│   ● revenge      Revenge line          own              │  key + label, add/edit/remove
│   ○ romance      The Cold Harbor girl  ← from saga      │  inherited: greyed, "override" action
│   [+ track]                                             │
├─ ROSTER ───────────────────────── own ⊕ inherited ──────┤  resolved.roster (slots — NOT a prompt
│   protagonist  Actant: hero    → 沈墨  [change] [unbind]│   input; read by the template extractor)
│   traitor      Actant: shifter → — not bound —  [bind]  │  + resolved.roster_bindings → PROMPT
│   [+ role]                                              │  binding resolves via useGlossaryRoster
├─ CHAPTERS (span 41–58 · 18 chapters) ───────────────────┤  span + assign-chapters
│   ⚠ Non-contiguous — 3 gaps in the reading order        │  is_contiguous (warn-only, BA6)
│   41 · Cold Harbor at dawn                    [remove]  │  ← remove needs BE-A3
│   … (virtualized above ~200)                            │
│   [+ assign chapters…]                                  │
├─ OPEN PROMISES (5) ─────────────────────────────────────┤  open_promises rollup
│   ▲ 90  promise   "the sword's true owner"   → open     │  → deep-link to `quality-promises`
├─ PROVENANCE ────────────────────────────────────────────┤  arc_template_id / template_version
│   From template: 复仇双线 (Twin Revenge) · v3  [open]   │  resolve title via arcApi.get
│   — or —  Authored from conversation (no template)      │  BA13: null provenance is NORMAL
├─ DANGER ────────────────────────────────────────────────┤
│   [Archive arc]   ⚠ also archives 2 sub-arcs            │  blast radius computed CLIENT-side (§3.4)
└─────────────────────────────────────────────────────────┘
```

**Create.** A `+ New arc` / `+ New saga` action in the header, and the empty state's CTA. Body:
`{kind, parent_arc_id, title, summary, goal, status}` → `POST /books/{bid}/arcs`. Tracks/roster are
edited **after** create (a create form with a nested track editor is a form nobody finishes).

⚠ **`kind` is a CLOSED SET OF TWO: `'saga' | 'arc'`.** There is **no `sub_arc` kind** — the DB CHECK is
`kind IN ('saga','arc')` (`migrate.py:1102`) and the REST body is `Literal["saga","arc"]`
(`arc.py:333`). A **sub-arc is an `arc` whose parent is an `arc`** (`depth == 2`); "sub-arc" is a
*depth label*, not a kind. A picker offering `sub_arc` 422s. The panel therefore renders **Kind
∈ {saga, arc}** and derives the sub-arc reading from `parent_id`/`depth`. A `saga` with a parent is
rejected by `structure_saga_is_root` → the verbatim `STRUCTURE_CONSTRAINT` 400 (below).

### 3.3 The cascade must be rendered as a cascade — not flattened

`GET /arcs/{node_id}` returns **`resolved`** — the root→leaf merge (`structure.py:599-616`), leaf
shadowing by `key` / `role_key`. The **node's own** `tracks`/`roster`/`roster_bindings` are the
top-level fields on the same payload.

**AI-2 (LOCKED). The panel renders both, and marks which is which.** A track shown without saying it
is *inherited from the saga* invites the user to "edit" it — and the PATCH writes the **arc's own**
`tracks` array, silently forking a copy of the saga's track that then stops tracking the saga. That is
the write-only/shadow-copy bug class in a new costume.

- **own** entries: editable in place.
- **inherited** entries: greyed, read-only, with one action — **Override here**, which copies the
  entry into this node's own `tracks` (same `key` ⇒ it shadows) and *says so*.
- The **effective** set (what `gather_arc` actually injects) is what the section header counts.

**AI-3 (LOCKED). A track/role `key` is required, non-empty, and unique within the node.**
`StructureRepo._merge_by` (`structure.py:586-597`) keys on `it.get(key_field, id(it))`:
- a **missing** key ⇒ the entry is kept but **can never be shadowed or overridden** — permanently
  un-editable-by-cascade garbage;
- an **empty-string** key ⇒ every empty-keyed entry across the whole ancestor chain **collides on
  `""`** and the leaf silently eats the root's.

Neither the REST schema (`ArcCreate.tracks: list[dict[str, Any]]`, `arc.py:339`) nor the MCP tool
validates this — both take a free-form blob. **The panel is the only thing standing between the user
and a corrupt cascade**, so it validates on write and refuses with an inline message. (Tightening the
server schema is filed as an open question, §11 OQ-2 — it would break the agent's existing writes.)

### 3.4 Every state, rendered

| State | Trigger | Render |
|---|---|---|
| **empty** | book has no arcs | *"No arcs yet — the spec tree is what steers generation."* + **Create the first saga** + a link to `plan-hub`'s decompiler CTA. Never a blank pane. |
| **no selection** | bare-id open, empty bus | the arc **picker**, focused. Not an error. |
| **loading** | `GET /arcs/{id}` in flight | skeleton over the sections; the header keeps the picker live |
| **error** | 5xx / network | the message + **Retry**. Never an empty inspector that looks like an empty arc. |
| **403** | VIEW but not EDIT | **read-only**: every control unmounted, one line — *"You have view access to this book."* Mirrors `PlanDrawer`'s `writes`-omitted contract (`PlanDrawer.tsx:47-55`) — **never render a control that would 403.** |
| **404** | arc archived/deleted elsewhere, or grant revoked | *"This arc is no longer accessible."* + clear the bus slice. The uniform-404 means we **cannot** distinguish gone-from-denied and must not guess. |
| **OCC conflict (412)** | someone else (or the agent) wrote first | the 412 body **carries the current row** (`arc.py:505-508`, `{code:"STRUCTURE_VERSION_CONFLICT", current:{…}}`). Seed it straight into the cache, keep the user's in-progress text in the field, and say *"This arc changed elsewhere — reloaded. Re-apply your edit."* **Never** silently clobber; **never** blame the user. |
| **archived** | `is_archived` | the whole body dims, a banner: *"Archived — restore to edit."* + **Restore**. Reachable from the picker with *Show archived* (`GET /books/{bid}/arcs?include_archived=true`); `StructureRepo.get()` does **not** filter archived, so the detail route serves an archived node 200 (verified — the state is reachable). `derived_blocks` returns rows for **live nodes only** (`structure.py:255`), so after BE-A1 the archived detail block is **null** — span/chapters render **"—", never a computed 0**. ⚠ **The panel gates the "—" on `is_archived`, not on falsiness**: `0` and `null` must not collapse (`chapter-blocks-null-nontext-coalesce`). ⚠ **Archiving does NOT unassign the member chapters** — `archive()` (`structure.py:404`) flips `is_archived` on `structure_node` only; `outline_node.structure_node_id` is untouched, and `?unassigned=true` is `structure_node_id IS NULL` (`outline.py:849`). So an archived arc's chapters appear in **neither** the arc lane nor the unassigned tray until the user (or the agent) unassigns them — **BE-A3 is their only escape hatch.** The archive confirm must not promise otherwise. |
| **structure conflict (400)** | a move/create that would nest past depth 2, cycle, cross books, or parent a saga | the server's clean `STRUCTURE_CONSTRAINT` message (`arc.py:397`), rendered verbatim. The client does **not** re-implement the rules. |
| **cost gate** | — | **none. This panel spends nothing.** Every action is deterministic CRUD, $0, no LLM. There is no propose→confirm here — and adding one would be a defect. *(An LLM "suggest an arc for this premise" button is **Wave 4 / G-MOTIF-SUGGEST**, not this spec — §11.)* |
| **archive blast radius** | archiving a node with children | `DELETE` cascades to the subtree (`structure.py:404`) and the response `{id, archived:true}` **does not say how many nodes it took**. So the panel computes the descendant count **from the shell tree it already holds** and puts it in the confirm: *"Archive 'Book One' and its 2 sub-arcs?"* — and does **not** trust the response for the count. |

### 3.5 The PlanDrawer embed (24-H3.1) — and how it lands without a collision

⚠ `PlanDrawer.tsx` is owned by the **Book-Package track (specs 22–28)**, which declared **complete
2026-07-12** (plan-30 §9). DBT-06 is in that track's own debt table as *"#4 genuinely-upstream"* — it
is **handed to us**, not contested. Still, the edit is designed to be **surgical and revert-safe**:

**AI-4 (LOCKED). The embed is a DELETION plus a one-line mount.**

1. `ArcFacets` (`PlanDrawer.tsx:305-357`, ~50 lines) is **deleted**, along with `rosterKeysOf`
   (`:299`) and the `plan-drawer-arc-gap` note (`:351`).
2. `DrawerBody`'s arc branch (`:391-394`) becomes:
   ```tsx
   if (view.kind === 'arc' || view.kind === 'saga') {
     if (!view.arcNode) return <Centered testid="plan-drawer-empty">Arc not found in the shell.</Centered>;
     return <ArcInspectorBody arcId={view.arcNode.id} bookId={bookId} writes={writes} />;
   }
   ```
   ⚠ **`bookId` must be threaded into `DrawerBody`** — it is on `PlanDrawerProps` (`:33`) but is
   **not** a `DrawerBody` prop today (`:360-370` takes only `view/overlay/onOpenRef/writes/chapters/
   onOpenInEditor`), and `selectedId` is not in scope there either. One added prop + one added
   pass-through at the `<DrawerBody …>` call site. The id comes from `view.arcNode.id`, which the
   branch already guards.
   — the **same component** the dock panel renders, in its embedded variant (no panel chrome, no
   picker; the drawer supplies the id). **DOCK-2: one implementation, two hosts.** A second arc
   renderer inside the drawer would be exactly the fork DOCK-2 forbids.
3. `usePlanNode`'s `arcNode` (from the **shell**, `usePlanNode.ts:84`) stops being the drawer's arc
   source. The body fetches `GET /arcs/{id}` itself — which is the whole point: the shell has **no**
   `resolved`, **no** `open_promises`, and a **different** `span` (§5 BE-A1).

**Conflict surface: one file, ~55 lines deleted, ~6 added (incl. the `bookId` pass-through), no
shared symbols moved.** If the Book-Package track re-opens, this reverts cleanly. Announce before
editing; do not `git add -A`.

**Also fixed by this deletion:** `PlanDrawer.tsx:346` currently renders the raw `arc_template_id`
**UUID** as the Provenance value — an unclickable 36-character hex string presented to a novelist.
The inspector resolves it to the template's title via `arcApi.get`, and links out.

### 3.6 Widen `ArcListNode` (the type that lies)

`plan-hub/types.ts:36-57` declares 12 node fields (+ 4 derived). The wire carries **20**
(`StructureNode`, `app/db/models.py:194-228`). The missing 8 are exactly the ones this spec edits:
`book_id`, `created_by`, `tracks`, `roster`, `roster_bindings`, `is_archived`, `created_at`,
`updated_at`.

`PlanDrawer.tsx:308` already works around it:
```tsx
// The wire carries tracks/roster/roster_bindings (types.ts note) though the FE ArcListNode subset
// doesn't declare them — read them defensively without redefining the H2-owned type.
const extra = arc as ArcListNode & { tracks?: unknown; roster?: unknown };
```
A cast that re-declares two fields as `unknown` **because the type is wrong** is a type lying about
the wire. **Widen `ArcListNode` to the full `StructureNode` shape** (+ the derived block) and delete
the cast. `laneLayout`'s `ArcShellNode` subset is unaffected — it structurally destructures.

---

## 4 · Data the panel reads

| # | Source | Route | Notes |
|---|---|---|---|
| 1 | shell tree (picker, blast radius, breadcrumb) | `GET /books/{bid}/arcs` | **shared cache** `['plan-hub','arcs',bookId]` — no second fetch |
| 2 | the arc detail | `GET /arcs/{node_id}` | `resolved` + `span` + `open_promises` + `version` |
| 3 | member chapters | `GET /books/{bid}/outline/children?structure_node_id=…` | keyset-paged (`plan-hub/api.ts:33`), **virtualize above ~200** |
| 4 | conformance badge | `GET /books/{bid}/conformance/status` | `useConformanceStatus` — `arcs[].structure_node_id` is the join key |
| 5 | entity names for `roster_bindings` | `useGlossaryRoster` | shared cache with `scene-inspector` |
| 6 | provenance template title | `GET /arc-templates/{id}` | `arcApi.get` |

**Read-set discipline:** #1 and #4 are already in memory whenever the Hub is open. Only #2 is
per-selection. Cold-open cost for the dock panel: 2 requests.

---

## 5 · Backend prerequisites — **the audit said NONE. It is wrong on three counts.**

Plan-30 §5.1 records **BE? NONE** for this gap. Verifying against source found three defects. All
three are **XS/S** and all three become **live bugs the moment this panel ships**. Fix-now, not
deferred.

🔴 **One correction to the tempting framing.** "These routes are NO-FE-CONSUMER, so there is nothing
to break" is true of the **routes** and **false of the repo methods behind them**.
`StructureRepo.span()` is called by the **packer** (`lenses.py:322` → every generation prompt), and
`StructureRepo.assign_chapters()` is called by the shipped Hub. **Fix the ROUTES; do not "tidy" the
repo methods.** Each row below names its blast radius explicitly.

| # | Route | Defect | Shape of the fix | Errors | Size | Status |
|---|---|---|---|---|---|---|
| **BE-A1** | `GET /v1/composition/arcs/{node_id}` **and** `composition_arc_get` (MCP) | 🔴 **`span` has a different SHAPE *and a different UNIT* than the same-named field on the list route.** `arc.py:455` returns `StructureRepo.span()` = `{min_story_order, max_story_order, chapter_count, is_contiguous}` in **RAW strided units** (`STORY_ORDER_CHAPTER_STRIDE = 1000`, `chapter_gen.py:21`). The list route (`arc.py:429`) returns `derived_blocks()` = `{span:{from_order,to_order}, is_contiguous, chapter_count, first_story_order}` in **dense-ranked ORDINALS**, *and its own SQL comment says exactly why*: *"raw min/max would report a 3-chapter arc as span 1000..3000 … every arc would read non-contiguous"* (`structure.py:270-277`). **The detail route never got that fix.** An inspector that renders `span.min_story_order`–`span.max_story_order` prints **"Chapters 41000–58000"**. ⚠ **The MCP door has the SAME defect** (`server.py:4255` — `out["span"] = await structures.span(node.id)`), so the agent reads the same broken unit. | 🔴 **FIX AT THE ROUTE, NOT IN THE REPO.** `StructureRepo.span()` has **THREE** callers, and the third is the packer: `lenses.py:322` — `gather_arc` calls `span()` per chain node and feeds `min_story_order`/`max_story_order` to `_arc_position` (`lenses.py:241-254`), which compares them against the scene's **raw strided** `story_order`. **Dense-ranking `span()`, or renaming/removing its raw keys, silently corrupts EVERY generation prompt** — `story_order` (e.g. 45000) vs a dense-ranked `hi` (18) clamps the pacing to *"~100% through arc X"* forever, or (via `_arc_position`'s `.get`) drops the Pacing line entirely; `gather_arc`'s degrade-safe posture would swallow it and the unit suite stays green. **So: leave `span()` exactly as it is.** In **both** doors (`arc.py:455` **and** `server.py:4255`) replace the `span()` call with `(await structures.derived_blocks(node.book_id)).get(node.id)` — one query, and both routes already have `node.book_id`. For an **archived** node `derived_blocks` returns **no key**: emit `span: null, chapter_count: null, is_contiguous: null` (**never the list route's `empty` block — its `chapter_count: 0` is exactly the "a null that means *not computed* is not a zero" trap §3.4 renders**). Tests: `list[i].span == get(i).span` for the same node; the MCP tool returns the same shape as REST; an archived node's detail returns a **null** block, not `0`; and a `gather_arc` pacing test pinning `span()`'s raw keys so a future "cleanup" reds. | — | **S** | **MUST-FIX** |
| **BE-A2** | `PATCH /v1/composition/arcs/{node_id}` | 🔴 **`If-Match` is OPTIONAL ⇒ a blind clobber is a legal request.** `arc.py:495`: `if_match: str \| None = Header(default=None)` → `_parse_if_match(None)` → `None` → `StructureRepo.update(expected_version=None)` (`structure.py:379`) skips the version clause entirely. **The MCP tool requires it** (`_ArcUpdateArgs.expected_version: int`, `server.py:4333` — not optional). So the **REST door is weaker than the MCP door on the same repo method**, on the object that steers generation. ⚠ **It is worse than "skips the version clause":** `structure.py:379-382` appends `version = version + 1` **only inside** the `expected_version is not None` branch — so a blind write **does not bump `version` at all**. A concurrent holder of v7 then still succeeds with `If-Match: 7` against a row whose *content* someone else replaced. | Make `If-Match` **required**: absent ⇒ **428 Precondition Required**. Zero existing callers (NO-FE-CONSUMER). Add the test. *(Do not "fix" this in the client only — the next caller will forget.)* With both doors requiring it, `expected_version=None` becomes unreachable — leave the repo branch, but do **not** reuse it. | `428` | **XS** | **MUST-FIX** |
| **BE-A3** | `POST /v1/composition/books/{bid}/arcs/assign-chapters` | 🟠 **Add-only: there is no UNASSIGN at any layer.** `ArcAssignChapters.structure_node_id: UUID` (`arc.py:364`, non-null) and `StructureRepo.assign_chapters` (`structure.py:540`) does `SET structure_node_id = $1` with an `EXISTS` guard. A chapter, once bound, can only be **moved to another arc** — never returned to the unassigned pool. Yet the children route **reads** that pool (`?unassigned=true`, `plan-hub/api.ts:35`) and the Hub renders it. **We can read a state no writer can produce** (post-decompile only). The inspector's *"remove chapter from arc"* is therefore unbuildable today. | `structure_node_id: UUID \| None` on the REST body **and** on `_ArcAssignChaptersArgs` (`server.py:4508`); `None` ⇒ `SET structure_node_id = NULL` (drop the `EXISTS` guard on that branch, keep the `book_id` + `kind='chapter'` guard). **Do both doors** — a GUI-only unassign is an INVERSE gap (GG-2). ⚠ **3-schema-source FastMCP caveat** applies to the tool arg. | — | **S** | **MUST-BUILD** |

Everything else — create, read-detail, update, delete, restore, move, the cascade resolution, the
derived span, the open-promise rollup, the grant gate, the 412 body, the depth/cycle trigger — **EXISTS
and is correct.** No new engine, no schema change, no migration, no gateway change (the composition
proxy's `pathFilter` is generic — `gateway-setup.ts:354`).

---

## 6 · Registration checklist (GG-8) — exact files, in order

Drift-lock state at HEAD `9262ed53e`: **py enum 57 == contract enum 57 == openable 57.** This panel
moves all three by **+1, in lockstep**. ⚠ **Assert the DELTA and the three-way equality — never the
literal `58`.** [`31`](31_quality_completion.md) (Wave 1) lands **4** panels before this wave starts, so
the baseline here is **61**, not 57. A DoD pinned to `58 == 58 == 58` sends the next builder hunting a
phantom regression. `arc-inspector` is **openable by bare id** (AI-1), so **every** step applies — none
of the `hiddenFromPalette` shortcuts.

| # | File | Change |
|---|---|---|
| 1 | `frontend/src/features/studio/panels/ArcInspectorPanel.tsx` (new) | the panel. Root `data-testid="studio-arc-inspector-panel"`. Calls `useStudioPanel('arc-inspector', props.api)`. Reads `props.params as ArcFocusParams \| undefined`. |
| 1b | `frontend/src/features/studio/panels/ArcInspectorBody.tsx` (new) | the **shared** body (dock panel **and** PlanDrawer embed — AI-4). No panel chrome, no picker. |
| 1c | `frontend/src/features/studio/panels/useArcInspector.ts` (new) | the controller — detail fetch, OCC write chain, cascade merge, blast-radius derivation. No JSX. |
| 2 | `frontend/src/features/studio/panels/catalog.ts` | one row: `{ id: 'arc-inspector', component: ArcInspectorPanel, titleKey: 'panels.arc-inspector.title', descKey: 'panels.arc-inspector.desc', category: 'editor', guideBodyKey: 'panels.arc-inspector.guideBody' }`. `'editor'` **is** a member of `CATEGORY_ORDER` (`useStudioCommands.ts:20`) — verified, so X-2 does not block us. *(X-2 is still real: `'quality'` is missing from that list. Not ours to fix here.)* |
| 3 | `frontend/src/i18n/locales/en/studio.json` | `panels.arc-inspector.title` / `.desc` / `.guideBody` |
| 4 | `frontend/src/i18n/locales/{ar,bn,de,es,fr,hi,id,ja,ko,ms,pt-BR,ru,th,tr,vi,zh-CN,zh-TW}/studio.json` | same 3 keys × 17 locales — **`python scripts/i18n_translate.py`**, never hand-written |
| 5 | `services/chat-service/app/services/frontend_tools.py` | **two edits**: (a) append `"arc-inspector"` to the `panel_id` enum (`:402`); (b) append its clause to the description prose (~`:448`, next to `plan-hub`) — that gloss is the model's **only** hint the panel exists. Suggested: *"'arc-inspector' = read/edit ONE arc or saga of the book's spec tree — title/goal/status, the cascade-resolved plot tracks and cast roster, its chapter span, its open promises, and its template provenance. This is the structure that steers every generation."* |
| 6 | `contracts/frontend-tools.contract.json` | **NEVER hand-edit — regenerate:** `cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py`. Commit the regenerated JSON in the **same commit** as steps 2 + 5. |
| 7 | `frontend/src/features/studio/host/types.ts` | the `arc` bus event + `activeArcId` snapshot key + the `applyBusEvent` case (AI-1) |
| 8 | `frontend/src/features/studio/agent/handlers/arcEffects.ts` **(NEW FILE — this wave creates it)** | **MANDATORY (X-4):** `registerEffectHandler(/^composition_arc_/, arcEffect)` → `invalidateQueries(['plan-hub'])` + `['composition','arcs', bookId]`. Register it in the same barrel as `bookEffects` / `glossaryEffects` / `knowledgeEffects` / `translationEffects`, and use `unwrapToolResult` (the live stream nests the domain payload in the `{ok, result}` envelope). Without it, the agent edits an arc and the open inspector shows the **stale** row — and the user's next save 412s against a version they were never shown. **This handler is the difference between "the agent and the human share one object" and "they fight over it."**<br><br>🔴 **ONE HOME FOR `composition_arc_*` — do NOT put this in `bookEffects.ts`.** [`34`](34_arc_templates_and_deconstruct.md) §6 step 8 (Wave 4) registers `/^composition_arc_(…\|apply\|extract_template)/` in an **`arcEffects.ts`**. `matchEffectHandlers` ([`effectRegistry.ts:45`](../../../frontend/src/features/studio/agent/effectRegistry.ts#L45)) returns **every** matching handler and `runEffectHandlers` awaits **all** of them — so two overlapping registrations in two files would both fire on every arc write: double invalidation, two homes for one concept, and a second place for the next agent to forget. **Wave 2 (this spec) CREATES `arcEffects.ts` with the single broad `/^composition_arc_/` pattern; Wave 4 EXTENDS the same file's handler body** (adding the `arc-templates` query keys) rather than registering a second pattern. |
| 9 | `frontend/src/features/studio/onboarding/tours.ts` | **skip** — not a role-tour step in v1. |
| — | `frontend/src/features/studio/host/studioLinks.ts` | **skip** — no external URL resolves to an arc today. |

**Verify (all four green — the first two are the drift-locks):**
```
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
cd frontend && npx vitest run \
  src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
  src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
  src/features/studio/palette/__tests__/useStudioCommands.test.ts \
  src/features/chat/nav/__tests__/frontendToolContract.test.ts
```

**Do NOT touch:** `StudioDock.tsx`, `StudioFrame.tsx`, `useStudioCommands.ts`, `UserGuidePanel.tsx`
(all derive from `catalog.ts`); `studioUiNav.ts` / `useStudioUiToolExecutor.ts` (panel-id-agnostic).

---

## 7 · Agent surface

**MCP tools driving this domain (all 8 exist, `server.py:4191-4543`):** `composition_arc_list` ·
`_get` · `_create` · `_update` · `_delete` · `_restore` · `_move` · `_assign_chapters`.
**This spec adds none.** MCP-first is already satisfied; the *human* side was the hole.

**Lane-B effect handler (X-4) — step 8 above. Mandatory, not conditional.**

**`resource_ref` (X-6 / spec 28 AN-12 / OQ-8) — what this panel needs from it.** Today it is an
**unwritten OQ** (`28_agent_native_studio.md:545`). The arc-inspector consumes exactly one variant:

```
{ kind: 'structure', id: '<structure_node.id>', version?: <int> }
```

The FE resolver maps it to `bus.publish({type:'arc', arcId: ref.id})` (+ `openPanel('arc-inspector')`
if closed). That is the **whole** contract this panel needs — no `params` on `ui_open_studio_panel`,
no new tool. **X-6 gates the "agent points at this arc" leg only**; the panel core (picker + deep-link
from `plan-hub`) ships without it. Decompose, don't block.

**INVERSE gaps (agent can, human still cannot) after this ships:** ✅ **none for arcs.** All 8 tools
gain a human equivalent. *(`composition_arc_apply` / `_template_drift` are `_pending_engine` stubs — the
**agent** cannot apply a template although the human can. That is **Wave 4 / BE-8**, not this spec.)*

---

## 8 · Compliance — stated, not assumed

**Tenancy.** No new table, no new row, no new scope key. `structure_node` is **Per-book** (BA8:
`book_id` is the scope; there is no `project_id`, no `user_id`, no `owner_user_id`). Every route gates
on the **E0 book grant**, resolved **from the row** (`_gate_arc`, `arc.py:383`) — VIEW to read, EDIT to
write. `created_by` is an **actor stamp, never a scope key** (`models.py:211`, PM-5/DA-11) — the panel
displays it and **never filters on it**. There is no System tier here and no shared user-editable row:
an arc belongs to exactly one book. **A collaborator with EDIT shares one spec tree with the owner** —
that is BA8's deliberate design (a team shares one `main.tf`), not a leak.

**Settings (SET-1..8).** This panel introduces **zero** settings, **zero** toggles, **zero** env flags.
The one thing that *looks* like a setting — an arc's **inherited vs own** track/role — is not one: it
is a data cascade, and AI-2 requires the panel to show the **effective value + its source tier**
(own / inherited-from-`<ancestor title>`), which is SET-1's spirit applied to data. A silently
flattened cascade would be the "grounding always-on / reasoning silently-off" bug in a new domain.

**OCC.** Every content write is `PATCH /arcs/{node_id}` with `If-Match: <version>` (required after
BE-A2). A 412 returns the **current row**, so the recovery is *seed-and-say*, never a clobber (§3.4).
Two hard rules from this repo's own scars:
- **Serialize the write chain** (`instant-commit-control-over-occ-entity-needs-write-serialization`):
  a roster chip and a status `<select>` both commit instantly; two rapid edits would both send
  `If-Match: v1`, the second 412s, and we'd blame a phantom collaborator for the user's own keystroke.
  Chain the writes (`useSceneInspector.ts:43-45`) **and** re-seed the fresh row synchronously on
  success (`usePlanNodeWrites.ts:73-75`).
- `move`, `archive`, `restore`, `assign-chapters` carry **no** version and need none — they are
  idempotent or guarded by DB constraints, exactly as the existing Hub writes are.

**Cost gates.** **None, by construction.** Every action here is deterministic, $0, no LLM (§3.4). If a
later agent adds an LLM action to this panel it goes through the **generic** `GET
/v1/composition/actions/preview` → `POST /v1/composition/actions/confirm` spine — **never** a bespoke
per-action estimate route. Three such invented routes **404 in production today** (plan-30 §3.3); do
not make it four.

---

## 9 · Milestones

Each is independently shippable and independently revertable.

| # | Slice | DoD |
|---|---|---|
| **M1** | **BE-A1 + BE-A2** (the two backend fixes — **both doors, REST + MCP**) | `pytest` green, incl.: `list_arcs()[i].span == get_arc(i).span == composition_arc_get(i)["span"]` for the same node; an **archived** node's detail block is **null**, not `0`; `PATCH /arcs/{id}` **without** `If-Match` → **428**; and 🔴 **a `gather_arc` pacing test that pins `StructureRepo.span()`'s RAW keys** (`min_story_order`/`max_story_order`) so the "obvious cleanup" that would corrupt every prompt reds instead of shipping. No FE change. |
| **M2** | **The panel, read-only** — catalog row + enum + contract regen + i18n × 18 + the bus slice + the picker + all 6 read sections + every state in §3.4 | The 4 drift-lock suites green (58==58==58). Panel opens from the palette **and** from `ui_open_studio_panel`. Renders a real arc's resolved tracks/roster/bindings/span/promises/provenance. |
| **M3** | **The writes** — create · patch (OCC) · archive (with the client-derived blast radius) · restore · the AI-2 own-vs-inherited override · AI-3 key validation | A 412 renders *"changed elsewhere — reloaded"* and the **next** edit succeeds (the serialization test). Archiving a saga confirms with the real sub-arc count. |
| **M4** | **Membership** — BE-A3 (unassign, both doors) + the Chapters section's assign/remove | A chapter removed from an arc appears in the Hub's `?unassigned=true` tray. The **agent** can unassign too (no INVERSE gap). |
| **M5** | **The PlanDrawer embed (24-H3.1)** + `ArcListNode` widening + delete the `plan-drawer-arc-gap` note + the X-4 Lane-B handler | `plan-drawer-arc-gap` returns **zero** grep hits repo-wide. The drawer and the dock panel render the **same component**. An agent `composition_arc_update` refreshes an open inspector without a manual reload. |

---

## 10 · Definition of Done

1. **Unit/contract suites green** — the four listed in §6, plus composition-service `pytest` for M1/M4.
2. **`grep -rn "plan-drawer-arc-gap" frontend/src` → nothing.** The UI no longer tells the user this
   feature is missing.
3. **The 5 NO-FE-CONSUMER routes have a consumer.** `grep -rn "arcs/\${" frontend/src` finds
   create/get/patch/delete/restore.
4. 🔴 **LIVE BROWSER SMOKE — mandatory, not negotiable.** A green unit suite has repeatedly hidden
   *"the FE could not actually execute it"* (`agent-gui-loop-needs-live-browser-smoke-not-raw-stream`;
   spec 24's own H8.2 DoD was **never met** — no Playwright targets `plan-hub` anywhere, and its
   "smoke" was curl). Drive a **real browser** against a **rebuilt** image
   (`live-smoke-rebuild-stale-images-first`), signed in as `claude-test@loreweave.dev`:
   1. open the studio → `⌘P` → **Open Arc Inspector** → the dock tab mounts;
   2. **create** a saga → it appears in `plan-hub`'s lanes **without a manual reload**;
   3. create a sub-arc under it → add a track on the saga → open the sub-arc → **the track renders as
      *inherited*, and `resolved.tracks` contains it** (this is the cascade proving itself end-to-end);
   4. edit the sub-arc's title → save → **edit again immediately** → **no 412** (the serialization fix);
   5. force a conflict: `composition_arc_update` the same node from the agent, then save from the
      panel → the panel says *"changed elsewhere — reloaded"* and the **retry succeeds**;
   6. assign a chapter, then **remove** it → it lands in the Hub's unplanned/unassigned tray;
   7. archive the saga → the confirm names the **real** sub-arc count → restore → the subtree **and the
      ancestor chain** come back;
   8. **the agent leg:** in Compose, `ui_open_studio_panel {panel_id:"arc-inspector"}` → the tab mounts
      (**verify by EFFECT — a dock tab, not a `shown:true` in the raw stream**).
   Drive dockview via `evaluate` + `data-testid` (refs go stale —
   `playwright-live-dockview-automation-recipe`).
5. **The generation loop closes — for BOTH prompt-bearing writes.** Set an arc's `tracks` in the panel
   → run a draft on a member chapter → assert the prompt **changed** (the BA12/D2 effect test's shape,
   `test_pack_arc_wired.py`). **Then do it again for `roster_bindings`** — bind a role to a glossary
   entity and assert the *"Cast bindings: …"* line appears (`lenses.py:337-344`). These are the panel's
   **only two** prompt-bearing writes (§1) and each needs its own proof; a `tracks`-only test would
   leave the entire Roster/binding editor — the panel's second-biggest write surface — unproven, which
   is the **write-only-behavior** bug CLAUDE.md bans wearing the costume of a green suite.
   ⚠ **`roster` (the abstract slot list) and `summary` have NO packer consumer** (§1). Do **not**
   write a pack-effect test for them and do **not** tell the user they steer generation. `roster`'s
   real consumer is `extract_template_from_arc` (`arc_apply.py:564`) — assert *that* instead: a slot
   added in the panel appears in a template extracted from the arc. `summary`/`status` are
   human-read labels, proven by the Hub rendering them, and are labelled as such in the UI copy.
6. **SESSION_HANDOFF updated**, **DBT-06 moved to "Recently cleared"** in the Book-Package RUN-STATE,
   and plan-30's Wave 2 row closed.

---

## 11 · Open questions / Deferred

| # | Question | Disposition |
|---|---|---|
| **OQ-1** | Should the panel offer *"Suggest an arc for this premise"* (`composition_arc_suggest`, `server.py:2272`)? | **NO — out of scope.** It is **G-MOTIF-SUGGEST**, Wave 4, and it is **not FE-only**: the tool has no REST route, so the browser gets a **403 from the BFF `FE_BRIDGE_TOOL_ALLOWLIST`** (`tools.controller.ts:24`) and fails closed at integration time. Adding a paid, cross-service, allowlist-gated action to a $0 deterministic panel would also drag the propose→confirm spine in for one button. **Its landing site is `arc-inspector`'s header — but it lands in Wave 4, with its backend.** |
| **OQ-2** | Should `tracks`/`roster` get a real server-side schema (they are `list[dict[str, Any]]` — a free-form blob at **both** doors)? | **DEFERRED — gate #2 (structural).** AI-3 makes the *panel* safe today. Tightening the server rejects writes the **agent already makes**, and `roster` entries carry `constraints[]` whose vocabulary is unsettled. Needs its own small spec + a migration audit of existing rows. **Row it in DEFERRED as `D-ARC-TRACKS-ROSTER-SCHEMA`.** |
| **OQ-3** | `DELETE /arcs/{id}` returns `{id, archived:true}` with **no count** of the subtree it archived. Should it report one? | **Client-derives it (§3.4) — good enough, and honest.** But the response *is* a silent-blast-radius (OUT-5). **UNVERIFIED whether any other consumer wants the count.** If a second consumer appears, add `archived_ids[]` then. Not worth a route change for one caller that already holds the tree. |
| **OQ-4** | `PlanDrawer.tsx:287` still says `composition_find_references` is *"not built yet"* — but the Book-Package RUN-STATE marks **DBT-08 CLEARED** (`a3abc05a6`, the tool shipped and is live-proven). | **NOT OURS — but it is a live lie in the file we are editing.** The tool exists on **MCP only** (no REST route — plan-30 §5.2 G-DIAGNOSTICS), so the FE facet **still cannot call it**; the *reason* in the copy is stale, the *emptiness* is not. **Leave the facet, do not "fix" the copy from the RUN-STATE alone.** Flagged for **Wave 7**, which owns the backlinks lens. |
| **OQ-5** | Should the arc's `status` (`empty\|outline\|drafting\|done`) be **derived** from its member chapters instead of hand-set? | **UNVERIFIED — no consumer found.** `grep` shows no engine branching on `structure_node.status`. It is currently an author's label. **Do not derive it on a guess**; if a consumer appears, that is the moment to decide. Recorded so the next agent does not "helpfully" auto-compute it. |
| **OQ-6** | X-12's premise (*"a panel needing an id is out of the enum"*) | **REFUTED by this spec (AI-1)** — `scene-inspector` (bus) and `quality-canon` (`props.params`) are both in the enum. **Amend plan-30 §8.2's X-12 row to name the two precedents**, or the next spec will re-litigate it. *(It may still hold for `motif-editor` / `workflow-editor` — decide there, on their own evidence.)* ⚠ AI-1 answers **half** of plan-30 §11's still-open PO decision (a): *"do NOT extend `ui_open_studio_panel` with `params`"*. It says **nothing** about the other half (`ui_show_panel` — retire vs enum, X-5). This panel does not depend on either outcome; **PO ratification of AI-1 is a formality, not a gate.** |
| **OQ-7** | `summary` and `roster` (the slot list) have **no packer consumer** (§1). Is the panel shipping an editor for fields nothing reads? | **NO — and this is the finding that nearly made it one.** Both have real, *non-packer* consumers: `roster` → `extract_template_from_arc` (`arc_apply.py:564`, Wave 4's template extractor) and it is the **schema the bindings fill**; `summary` → the picker, the Hub drawer, the Chapter Browser's arc headers (human-read). **The defect would have been the COPY, not the feature**: the first draft of this spec (and the mock's create form) told the user `summary` *"reaches the prompt"*. It does not. **Label honestly, prove only what the packer reads (DoD #5), and never dress a human-read label as a generation knob.** No deferral — fixed in this spec. |
| **OQ-8** | Archiving an arc **strands its chapters**: `archive()` does not null `outline_node.structure_node_id`, so the members appear in neither the (archived) arc lane nor the `?unassigned=true` tray (§3.4). | **NOT a blocker, and NOT silently accepted.** BE-A3's unassign is the escape hatch, and the archive confirm must **say** what happens (*"18 chapters stay bound to the archived arc; unassign them first to return them to the pool"*) rather than promise a pool return that no writer performs. Whether `archive()` should *cascade* an unassign is a real question with a real cost (restore could not put them back) — **row it as `D-ARC-ARCHIVE-CHAPTER-STRANDING`, gate #2 (structural: it changes restore's contract).** |

---

## Risks

| Risk | Mitigation |
|---|---|
| A future agent renders `span.min_story_order` and ships "Chapters 41000–58000" | BE-A1 stops the two **detail doors** from *serving* the raw block (they serve `derived_blocks` instead), and the test pins list==detail==MCP. The unit never reaches a client. |
| 🔴 **A future agent "cleans up" `StructureRepo.span()` to match** — and silently breaks every prompt | `span()` is the **packer's** input (`lenses.py:322` → `_arc_position`), which needs the **raw strided** axis. BE-A1 **forbids touching it** and adds a pacing test that reds on a key rename. This is the one edit in this spec that could ship a generation-quality regression with a green suite. |
| A future agent adds an LLM button here and invents `/actions/arc_suggest/estimate` | §8 names the three routes that **404 in production today** for exactly this reason. |
| The Book-Package track re-opens and collides on `PlanDrawer.tsx` | AI-4 makes the edit a **deletion + a one-line mount** (~55 lines out, 4 in, no moved symbols). Announce before editing; enumerate files on commit, **never `git add -A`**. |
| The cascade is flattened and a user "edits" an inherited track, forking a silent copy | AI-2 renders own-vs-inherited and makes **Override** an explicit, named action. |
| Two rapid edits 412 and blame a phantom collaborator | The serialized write chain + the synchronous re-seed. Both are **existing, shipped fixes** in sibling hooks — mirror, don't re-derive. |
| Shipping a beautiful editor for a field nothing reads | DoD #5 asserts the **prompt changes**. `gather_arc` already reads `tracks` — this panel is safe from the write-only class *if and only if we prove it*. |
