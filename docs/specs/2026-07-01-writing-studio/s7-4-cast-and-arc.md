# S7-4 · Cast Codex + Character Arc — the view-rich, author-poor cast, made operable

> **Status:** 📐 specced 2026-07-16 · branch `feat/context-budget-law` (studio track, session **S7**) · **M** (files≈14, logic≈6, side_effects=1 — FE-only OCC writes over existing routes)
> **Type:** **FE** — a **port + enhance**, not a build. Every write route already exists, ships OCC- or ownership-guarded, and has been live since K19d/T2.5. **Zero new backend routes, zero migrations.** The one non-render change is a Lane-B effect-handler edit (§7) — still FE.
> **Closes:** **S7-A1/A2** — [`docs/plans/2026-07-16-studio-session-S7-RUN-STATE.md:47-48`](../../plans/2026-07-16-studio-session-S7-RUN-STATE.md) (`Cast codex` = *read/navigate only*; `Character-arc` = *pure view, 0 buttons*). The two "❌ ❌ ❌" rows (Create/Edit/Delete) of the operability matrix.
> **Panels:** `cast`, `character-arc` (the S7 catalog block placeholder — [`catalog.ts:315`](../../../frontend/src/features/studio/panels/catalog.ts)).
> **Draft (UI acceptance target + house style):** [`design-drafts/screens/studio/screen-cast-and-arc.html`](../../../design-drafts/screens/studio/screen-cast-and-arc.html).
> Follows [`docs/standards/dockable-gui.md`](../../standards/dockable-gui.md) (DOCK-1..11), [`docs/standards/mcp-tool-io.md`](../../standards/mcp-tool-io.md) (IN/OUT), and the S7 sibling model [`32_arc_inspector.md`](32_arc_inspector.md).

---

## 1 · Why this exists — the gap, with file:line

The S7 black-box audit is blunt: **"view-rich, author-poor. The KG is populate-by-agent-extraction,
not populate-by-user."** (`S7-RUN-STATE.md:40-41`). The two panels this spec ports are the sharpest
face of that:

- **`CastCodexPanel`** (`frontend/src/features/composition/components/CastCodexPanel.tsx`) — grouped,
  searchable, spoiler-safe. **Zero edit affordance.** A row (`CastEntityRow.tsx:34-62`) is a toggle +
  an arc launcher and nothing else; the file makes **0 write calls**.
- **`CharacterArcView`** (`frontend/src/features/composition/components/CharacterArcView.tsx`) — a
  picker, an SVG arc, a relations strip. **0 buttons, 135 LOC.** Nothing you can change.

**The load-bearing fact (`S7-RUN-STATE.md:51-55`):** `knowledgeApi.createEntity` (`api.ts:1607`) and
`createRelation` (`api.ts:1617`) **exist** — but their **only** human caller is `useWorldMap.ts`
(add a *location* via the map). So a character / faction / concept can be **read**, never **authored**
by a human; to rename 李慕白, fix a mis-extracted `kind`, or retire a hallucinated entity, the user's
only path is **agent extraction or approving proposals.** The write API has been sitting ready and
unreachable.

| Capability | Agent (MCP) | Human (GUI) today |
|---|:--:|:--:|
| read the cast, grouped + spoiler-safe | `kg_*` reads ✅ | ✅ but **legacy `ChapterEditorPage` sub-tab only** |
| read one character's arc | `kg_entity_edge_timeline` ✅ | ✅ **same legacy sub-tab** |
| **rename / edit aliases / fix kind** | `kg_view_upsert` / entity write ✅ | ❌ **no surface** |
| **create an entity** | `kg_create_node` ✅ | ❌ (except location-via-map) |
| **create a relation** | edge write ✅ | ❌ (except via-map) |
| **archive (retire) an entity** | ✅ | ❌ |

**This is GG-1's law violated on the cast** — the agent can author the object; the human can only read
it. The port closes the reachability half (dock panels), and the ENHANCE closes the authoring half
(the write API already exists — §3.3).

**This is a PORT + ENHANCE, not a build.** Unlike `arc-inspector` (which had no legacy component), the
leaf components exist and are correct; we move them into the dock (DOCK-2: one implementation, two
hosts) and add the light-edit layer the read paths already support.

---

## 2 · What is already built — the reconciliation (read from source, not the audit)

**Frontend leaves: complete, render-only, reusable as-is.**

| Piece | Where | Reuse verdict |
|---|---|---|
| `CastCodexPanel` — group-by-kind (`groupCast`, `CastCodexPanel.tsx:15`), search (≥2 chars, `useCast.ts:35`), per-row status, empty/loading/no-project states | `CastCodexPanel.tsx` | **reuse whole** — the dock panel is a thin wrapper that supplies `bookId/chapterId/token/onViewArc` |
| `CastEntityRow` — collapsed status dot, lazy relations/events/facts on expand, the `onViewArc` launcher (`:51-62`), navigate-to-chapter (`:92`) | `CastEntityRow.tsx` | **reuse + extend additively** (§3.3 adds optional edit props; legacy callers pass none → no edit UI) |
| `CharacterArcView` — controlled entity (`:24-32`), picker with the past-200-cap fallback (`:56-62`), active→gone band (`:105`), spoiler cut, relations strip | `CharacterArcView.tsx` | **reuse whole** — the dock wrapper supplies `entityId/onEntityChange` |
| `useCast` — knowledge-project resolve (`useCast.ts:12`), list (`limit:200`, `:41`), batch status (`:50`), lazy detail/events/facts | `hooks/useCast.ts` | **reuse whole** |
| `useCharacterArc` — roster (`limit:200`, `:47`), `effectiveEntityId` (`:55`), events (`ARC_LIMIT=100`, `:10`), decoupled spoiler cutoff (`:69`), band split, `focusName` (`:101`) | `hooks/useCharacterArc.ts` | **reuse whole** |

**Backend write routes: 100% built, guarded, and live. No BE work.**

| Route | api.ts | Server | Guarantee |
|---|---|---|---|
| `POST /v1/knowledge/entities` `createEntity` | `:1607` | `entities.py:1037` | `source_type='manual'`, `confidence=1.0`, `provenance='human_authored'`; **idempotent on (name, kind)** in the project; JWT `user_id` is the scope (never cross-tenant) |
| `PATCH /v1/knowledge/entities/{id}` `updateEntity` | `:1627` | `entities.py:1072` | **strict OCC** — `If-Match: W/"<version>"`; **428** without it (`:1093`), **412 + current row + fresh ETag** on stale (`:1109-1116`); sets `user_edited=true` (K19d — extraction stops re-appending removed aliases) |
| `POST /v1/knowledge/relations` `createRelation` | `:1617` | — | **409** if either endpoint isn't the caller's; **422** on a self-loop |
| `DELETE /v1/knowledge/me/entities/{id}` `archiveMyEntity` | `:1426` | `entities.py:176` | **soft archive** (`user_archived`) — **preserves edges + the `glossary_entity_id` anchor**; **idempotent 204**; **404 only cross-user/typo** |
| `POST /v1/knowledge/entities/{id}/promote` `promoteEntity` | `:1669` | `entities.py:1239` | discovered → glossary-canonical (out of scope here, named for completeness) |
| `POST /v1/knowledge/entities/{id}/merge-into/{other}` `mergeEntityInto` | `:1705` | — | de-dup merge (out of scope here) |

**Reuse target for the edit dialog:** `frontend/src/features/knowledge/components/EntityEditDialog.tsx`
**already edits name / kind / aliases** with the OCC path — the codex mounts the same dialog (DOCK-2).

**The panel surface exists; the two rows do not.** `catalog.ts` reserves the S7 block
(`:315` — `cast, character-arc`) but neither id is registered anywhere yet: not in `STUDIO_PANELS`,
not in the `ui_open_studio_panel` enum (`frontend_tools.py:402`), not in the contract. §6 adds them.

---

## 3 · The design (from the draft)

### 3.1 The two dock panels — leaf-reuse wrappers

Both panels follow the `scene-inspector`/`quality-canon` shape: a thin `*Panel.tsx` that calls
`useStudioPanel(id, props.api)` (`QualityCanonPanel.tsx:29`), reads `host.bookId`
(`StudioHostProvider`), resolves the spoiler window from the **bus** (§3.2), and renders the existing
leaf.

```
┌─ CAST — «Book title» ──────────────────── [✎] [⟳] [×] ─┐   `cast`  (category: storyBible)
│ [ 🔍 search cast — name or alias…      ⌘F ]  [+ New ]  │   ← New = POST /entities
│ [All 14] [Characters 6] [Locations 4] [Factions 2] …   │   ← kind chips (client-filter over groups)
├────────────────────────────────────────────────────────┤
│ CHARACTERS (6)                                          │
│  ● 李慕白 · aka Kiếm Si          gone   [📈] [⋯]  ▾     │   ← status DERIVED · row actions = ENHANCE
│    ├ Relations (4) · Recent events · Known facts        │   ← lazy on expand (unchanged)
│  ● Hàn Lập  [ ________ ] v7 [✓][✕]              active  │   ← inline RENAME (PATCH, If-Match)
│  … LOCATIONS · FACTIONS · CONCEPTS …                    │
├────────────────────────────────────────────────────────┤
│ 14 of 14 · state windowed to Ch. 52          limit 200  │
└────────────────────────────────────────────────────────┘

┌─ CHARACTER ARC ────────────────────────── [⤢] [×] ─────┐   `character-arc`  (category: storyBible)
│ Character [ 李慕白 · Kiếm Si ▾ ]  [gone · from Ch.40]  [✎ Edit] │
│  active━━━━━━━━━━━━━┃gone┅┅   ← band + spoiler cut at bus chapter │
│  ●#1 Ch.12 ●#2 Ch.19 ●#3 Ch.28 ◆#4 gone ○#5 ▒#6(dim)    │
├────────────────────────────────────────────────────────┤
│ 1-hop relations · as of Ch.52                           │
│ [HL mentor_of Hàn Lập] [青 member_of …] [+ link entity] │   ← + link = POST /relations
└────────────────────────────────────────────────────────┘
```

**DP-1 (LOCKED). Category is `storyBible`, not `editor`.** The cast/arc are lore surfaces alongside
`glossary`/`wiki` (`catalog.ts:154-165`), not manuscript editors. (The draft's CSS calls them "editor"
panels loosely — the catalog `category` field is `storyBible`.)

### 3.2 The spoiler window comes from the BUS, not a page prop — the port's central wiring change

Today `chapterId` is threaded from `ChapterEditorPage` (the chapter being edited) into both leaves;
that is the reading position that windows status/events (`useCast.ts:33`, `useCharacterArc.ts:38`).
**That source dies when `ChapterEditorPage` retires.** The dock replacement is
`bus.activeChapterId` — the same slice `scene-inspector` reads (`host/types.ts:96`), published by the
editor/compose panels.

- `beforeChapterId = bus.activeChapterId`. When **no chapter is active** (bus empty), it is
  `undefined` → the batch-status route returns `window_available:false` → the **existing**
  `cast-window-hint` banner ("Reading position unknown — state may be incomplete", `CastCodexPanel.tsx:72`)
  renders. **The leaves already handle the unknown window** — no new state to invent.

⚠ **DP-2 (LOCKED). Do NOT invent a chapter picker in these panels.** The spoiler window is a *reading
position*, and its one home is the bus. A second picker here would be a per-device shadow of the
active chapter that silently disagrees with the editor — the "one name for one concept" break.

### 3.3 The ENHANCE — light editing the API already supports

**DP-3 (LOCKED). The edit affordances are ADDITIVE, optional props on `CastEntityRow`.** The legacy
`ChapterEditorPage` mount passes none → renders exactly as today (no edit UI). The dock panel passes
them → the row grows a `[⋯]` kebab + inline rename. **One component, two hosts (DOCK-2)** — never a
forked "editable row."

Three write paths, all through **existing routes**, all through **one OCC hook** `useCastEdit`
(new controller, mirrors `useSceneInspector.ts:44-102`'s serialized-write chain):

| Affordance | Route | Detail |
|---|---|---|
| **Inline rename** | `PATCH /entities/{id}` `{name}` | in-place `<input>`, `If-Match: W/"<version>"`; the version rides the row (`CastRow` **is** `Entity` — `version` at `api.ts:277`, `aliases` at `:253` — no extra fetch) |
| **Edit aliases & kind** (kebab → dialog) | `PATCH /entities/{id}` `{kind?,aliases?}` | **reuse `EntityEditDialog`** — it already edits these with OCC. `kind` is a **closed set** `character\|location\|faction\|concept`, enum-validated (never a free `<input>`) |
| **Archive** (kebab, danger) | `DELETE /me/entities/{id}` | soft archive; on 204 the row leaves the list (invalidate the cast query). Confirm dialog — it's a retire, not a hard delete |

**Create affordances** (panel-level, not per-row):
- **`+ New`** (codex toolbar) → `POST /entities {project_id, name, kind}`. `kind` defaults to the
  active kind-chip's kind, editable in the mini-form. Idempotent on (name, kind) — a duplicate returns
  the existing node (no error, no dup).
- **`+ link entity`** (arc relations strip) → `POST /relations {subject_id, object_id, predicate}`.
  ⚠ **Predicate is a free string server-side** (no enum) — the form offers the common predicates as
  suggestions but does **not** hard-enum them (that vocabulary is unsettled; §11 OQ-2).

**DP-4 (LOCKED). `story-state active|gone` is DERIVED and renders READ-ONLY.** `EntityStatusEntry` is a
spoiler-windowed **projection** of timeline events (`from_order` = the gone-transition's `event_order`,
`useCharacterArc.ts:18-27`). **There is no route that sets it.** Drawing an editable status dropdown
would be the write-only-behavior lie CLAUDE.md bans — a control that stores nothing the reader can
trust. The honest control is *"author the exit event"* — and **event CREATE has no route at any layer**
(only `updateEvent`/`archiveEvent` exist — `api.ts:1751/1770`; no `createEvent`). Event authoring
belongs to `kg-timeline`, not here. **The kebab renders a disabled *"Set state — derived"* row** with
the reason, so the next agent does not wire a fake toggle to "finish" the panel.

### 3.4 The deep-link hand-off — `cast` → `character-arc` (what dies when ChapterEditorPage retires)

Today the arc launcher (`CastEntityRow.tsx:51`) calls `onViewArc(row.id)`; the parent
(`ChapterEditorPage`) lifts it to `selectedEntityId` and flips a sub-tab. As **separate dock panels**
that lift-and-tab-swap is gone; the click becomes a typed host call. This is the exact seam that breaks
**silently** if ported without a payload contract.

**DP-5 (LOCKED). Mirror `arc-inspector`'s AI-1 three-tier precedence.** `character-arc` resolves its
subject in order:

1. **`props.params.entityId`** — an in-studio deep-link on open (the cast-row launcher). Same seam as
   `quality-canon`'s `props.params` (`QualityCanonPanel.tsx:33`).
2. **`bus.activeCastEntityId`** — a **new additive bus slice** (§6 step 7), so the cast codex and the
   arc stay in sync on selection and an agent's future `resource_ref` has a landing slice.
3. **the in-panel picker** — `CharacterArcView` **already has one** (`arc-character-select`,
   `CharacterArcView.tsx:72`), defaulting to `roster[0]`. So a bare-id open (palette, agent, User
   Guide) is **never a dead panel**.

The launcher's real call (correcting the draft's shorthand `host.openPanel('character-arc',{entityId})`)
is the actual `openPanel` signature (`StudioHostProvider.tsx:52`):

```ts
// CastEntityRow's onViewArc, supplied by the dock wrapper:
host.openPanel('character-arc', { params: { entityId: row.id }, focus: true });
bus.publish({ type: 'castEntity', entityId: row.id }); // keeps an already-open arc in sync
```

⚠ **DP-6. Do NOT extend `ui_open_studio_panel` with a `params` arg.** That is a Frontend-Tool-Contract
change with a free-string hazard, and these panels do not need it — the bus slice + `props.params`
(studio-internal) cover the deep-link, exactly as AI-1 ruled for `arc-inspector`.

### 3.5 Every state, rendered (from the draft + the leaves' existing branches)

| State | Trigger | Render |
|---|---|---|
| **empty** | project exists, 0 entities | `codex.empty` — *"No extracted entities yet — publish/extract to populate the codex."* + **`+ New`** CTA (the enhancement makes empty actionable, not a dead end). `CastCodexPanel.tsx:83-88`. |
| **no project** | book has no knowledge project | `codex.noProject` — *"No knowledge graph yet — extract this book…"* (`:81`). `+ New` disabled (nothing to attach to). |
| **loading** | project/list in flight | `codex.loading` hint (`:79`); arc → `chararc.loading` (`CharacterArcView.tsx:94`). |
| **no reading position** | `bus.activeChapterId` empty | the `cast-window-hint` banner (§3.2). Status dots still render (windowed to "now" = no window). |
| **no selection (arc)** | bare-id open, empty bus | the picker, defaulted to `roster[0]` (`useCharacterArc.ts:55`). Not an error. |
| **entity past the 200-cap** | Cast-launched id not in the arc roster | `useCharacterArc.focusName` (`:101`) surfaces it by real name so the `<select value>` never blanks (the T2.2 lesson). |
| **OCC conflict (412)** | someone else / the agent wrote first | the 412 body carries the **current entity** (`entities.py:1112-1114`); seed it into the row, keep the user's in-progress text, say *"changed elsewhere — reloaded."* **Never clobber** — mirror `useSceneInspector.ts:83`. |
| **428** | a PATCH without `If-Match` | cannot happen from the panel (`updateEntity` always sends it, `api.ts:1640`) — but if the version is missing, the hook GETs the row first. Named so no one "simplifies" the header away. |
| **archive → gone from list** | 204 | the row leaves the cast list (list route excludes archived). ⚠ **No UI restore** — see the box below. |
| **relation 409/422** | `+ link` to a non-owned endpoint / self-loop | inline error on the link form (*"that entity isn't yours to link"* / *"can't link an entity to itself"*). |
| **cost gate** | — | **NONE. Every action is deterministic CRUD, $0, no LLM.** No propose→confirm. Adding one would be a defect (§8). |

> 🔴 **ARCHIVE IS ONE-WAY FROM THE UI — state it, don't imply a restore button.** The draft's line 60
> ("…preserves edges + the glossary anchor + restores") is imprecise. `entities.py:158-160` is explicit:
> *"Archived entities are excluded; rollback path is **re-extraction on the next chat turn** rather than
> UI restore."* The archive **preserves** the anchor so a *re-mention* brings it back anchored — there is
> **no restore route** to call. The archive confirm must say *"Retired — it returns if the book mentions
> it again"*, **never** promise an undo button that does not exist. (A UI restore route is §11 OQ-1.)

---

## 4 · Data the panels read (all existing, all reused)

| # | Source | Route (via `knowledgeApi`) | Cache key |
|---|---|---|---|
| 1 | knowledge project for the book | `listProjects({book_id})` | `['composition','cast','project',bookId]` (`useCast.ts:14`) |
| 2 | cast list (`limit:200`) | `listEntities` | `['composition','cast','entities',projectId,kind,search]` (`:39`) |
| 3 | batch spoiler-windowed status | `getEntityStatuses` | `['composition','cast','statuses',projectId,kind,chapterId]` (`:51`) |
| 4 | lazy detail / events / facts (on expand) | `getEntityDetail` / `listTimeline` / `getEntityFacts` | `['composition','cast',{'detail'\|'events'\|'facts'},…]` |
| 5 | arc roster (`limit:200`) + events (`limit:100`) + cutoff + relations + status | `listEntities` / `listTimeline` / `getEntityDetail` / `getEntityStatuses` | `['composition','arc',…]` (`useCharacterArc.ts:45-91`) |

**Scale.** Books target 10k+ chapters, cast 200+. Both list routes cap at `limit:200`; above that the
codex needs keyset paging + kind-scoped fetch, and the arc roster shares the cap (a Cast-launched
entity past it is surfaced by `focusName`, #4 above). **Paging past 200 is out of scope for this
port** (the cap is the existing behavior) — flagged §11 OQ-3, not silently "fixed."

---

## 5 · Backend prerequisites — **NONE.** (verified against source, unlike `arc-inspector`)

| Route | METHOD + path | Request | Response | Errors | Status |
|---|---|---|---|---|---|
| create entity | `POST /v1/knowledge/entities` | `{project_id, name, kind}` | `Entity` (201) | idempotent (returns existing on dup) | **EXISTS** `entities.py:1037` |
| update entity | `PATCH /v1/knowledge/entities/{id}` | `{name?,kind?,aliases?}` + `If-Match: W/"v"` | `Entity` + `ETag` | **428** no If-Match · **412** stale (+ current row) · **404** cross-user | **EXISTS** `entities.py:1072` |
| archive entity | `DELETE /v1/knowledge/me/entities/{id}` | — | 204 | 404 cross-user/typo (idempotent) | **EXISTS** `entities.py:176` |
| create relation | `POST /v1/knowledge/relations` | `{subject_id,object_id,predicate}` | `EntityRelation` (201) | **409** endpoint not caller's · **422** self-loop | **EXISTS** |
| list / status / detail / events / facts | (reads, §4) | — | — | — | **EXISTS** (`useCast`/`useCharacterArc` already call them) |

**No new route, no schema change, no migration, no gateway change.** This is exposure, not
construction. The **only** non-render code outside the panels is the Lane-B effect handler edit (§7),
which is FE.

**Two genuinely-absent routes, both correctly out of scope (named so nobody wires a fake):**
1. **`createEvent`** — no route at any layer (`api.ts` has `updateEvent`/`archiveEvent` only). The
   `active→gone` band is therefore read-only here (DP-4); event authoring is `kg-timeline`'s job.
2. **entity restore** — no route (re-extraction only, §3.5 box). The archive confirm says so.

---

## 6 · Registration checklist (GG-8) — exact files, keeping enum == openable == contract

Both panels are **openable by bare id** (palette + agent + User Guide), so **every** step applies —
none of the `hiddenFromPalette` shortcuts. This spec moves the three-way drift-lock by **+2, in
lockstep**.

⚠ **Assert the DELTA and the three-way equality (`py enum == contract enum == openable`), NEVER a
literal count.** Sibling S7 panels (`world`, `world-map`, `place-graph`) and earlier sessions move the
same counters; a DoD pinned to a literal `N` sends the next builder hunting a phantom regression.

| # | File | Change |
|---|---|---|
| 1 | `frontend/src/features/studio/panels/CastPanel.tsx` (new) | wrapper: `useStudioPanel('cast', props.api)`; reads `host.bookId` + `bus.activeChapterId`; renders `<CastCodexPanel …>` with `onViewArc` + edit props. Root `data-testid="studio-cast-panel"`. |
| 1b | `frontend/src/features/studio/panels/CharacterArcPanel.tsx` (new) | wrapper: `useStudioPanel('character-arc', props.api)`; resolves entityId via `props.params.entityId → bus.activeCastEntityId → picker` (DP-5); renders `<CharacterArcView …>`. Root `data-testid="studio-character-arc-panel"`. |
| 1c | `frontend/src/features/composition/hooks/useCastEdit.ts` (new) | the OCC write controller — rename/patch/archive/create/link, serialized write chain + 412 reseed (mirror `useSceneInspector.ts:44-102`). No JSX. Co-located with the leaves it drives. |
| 1d | `frontend/src/features/composition/components/CastEntityRow.tsx` | **additive** optional props `{ onRename?, onEdit?, onArchive? }` + the `[⋯]`/inline-rename UI, gated on their presence (legacy path passes none). Reuse `EntityEditDialog`. |
| 2 | `frontend/src/features/studio/panels/catalog.ts` | two rows in the **S7 block** (`:315`): `{id:'cast', component:CastPanel, category:'storyBible', titleKey/descKey/guideBodyKey:'panels.cast.*'}` and `{id:'character-arc', component:CharacterArcPanel, category:'storyBible', 'panels.character-arc.*'}`. `'storyBible'` is a member of `ALL_CATEGORIES` (`:100`) — verified. |
| 3 | `services/chat-service/app/services/frontend_tools.py` | **two edits:** (a) append `"cast"`, `"character-arc"` to the `panel_id` enum (`:402`); (b) append their clauses to the description prose (~`:479`, next to `quality-canon`) — the model's only hint they exist. Suggested: *"'cast' = the book's cast codex — every character/place/faction/concept, grouped and searchable, each with its spoiler-safe story-state; create/rename/retire entities and edit aliases/kind. 'character-arc' = ONE character's events on a timeline (spoiler-cut at the reading position), the active→gone band, and the 1-hop relations."* |
| 4 | `contracts/frontend-tools.contract.json` | **NEVER hand-edit — regenerate:** `cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py`. Commit the regen in the **same commit** as steps 2 + 3. |
| 5 | `frontend/src/i18n/locales/en/studio.json` | `panels.cast.{title,desc,guideBody}` + `panels.character-arc.{title,desc,guideBody}` |
| 5b | `frontend/src/i18n/locales/{ar,bn,de,es,fr,hi,id,ja,ko,ms,pt-BR,ru,th,tr,vi,zh-CN,zh-TW}/studio.json` | same 6 keys × 17 locales — **`python scripts/i18n_translate.py`**, never hand-written |
| 5c | `frontend/src/i18n/locales/*/composition.json` | any NEW edit strings (`codex.rename`, `codex.editEntity`, `codex.archive`, `codex.newEntity`, `chararc.linkEntity`, …) co-located with the leaves — gap-filled by `i18n_translate.py` (never overwrite existing translated keys — the `quality.canonIntro` lesson, `QualityCanonPanel.tsx:52-55`) |
| 6 | `frontend/src/features/studio/host/types.ts` | the `castEntity` bus event + `activeCastEntityId` snapshot key + the `applyBusEvent` case (DP-5) — one line per, same shape as `scene` (`:98`) |
| 7 | `frontend/src/features/studio/agent/handlers/knowledgeEffects.ts` | **§7 — extend the EXISTING handler** to also invalidate `['composition','cast']` + `['composition','arc']`. **Do NOT add a second `/^kg_/` handler** (double-fire — the arc-inspector "one home" rule). |
| — | `catalog.ts` `onboarding/tours.ts`, `studioLinks.ts` | **skip** — not tour steps; no external URL resolves to a cast entity today. |

**Verify (the drift-locks + the contract mirror):**
```
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
cd frontend && npx vitest run \
  src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
  src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
  src/features/studio/palette/__tests__/useStudioCommands.test.ts \
  src/features/chat/nav/__tests__/frontendToolContract.test.ts
```

**Do NOT touch:** `StudioDock.tsx`, `StudioFrame.tsx`, `useStudioCommands.ts`, `UserGuidePanel.tsx`
(all derive from `catalog.ts`).

---

## 7 · Agent surface / MCP parity + the Lane-B handler

**MCP-first is already satisfied for AGENTIC logic.** The agent authors the cast through the KG write
tools (`kg_create_node` at `knowledge mcp/server.py:1121`, `kg_view_upsert`, edge/entity writes) — all
matching `KNOWLEDGE_WRITE_PATTERN = /^kg_/` (`knowledgeEffects.ts:16`). **This panel adds no MCP tool:**
MCP-first governs the agent's decision logic, not a human's GUI Create; a GUI Create over the existing
REST route is correct (per the CLARIFY note + `kg_create_node`/`kg_view_upsert` parity).

**🔴 The real gap the draft undersells — the Lane-B handler does NOT reach these caches today.**
`knowledgeEffect` (`knowledgeEffects.ts:21`) invalidates `knowledge-*` and `kg-*` query keys — but the
cast/arc panels read `['composition','cast',…]` and `['composition','arc',…]` (`useCast.ts:39`,
`useCharacterArc.ts:60`). **Those keys are never invalidated.** So today an agent `kg_create_node`
refreshes the `kg-entities` panel but leaves an open **cast codex stale** — and the user's next rename
then 412s against a version they were never shown. **This handler edit is the difference between "the
agent and the human share one cast" and "they fight over it."**

**Fix (§6 step 7): extend `knowledgeEffect`** — add:
```ts
queryClient.invalidateQueries({ queryKey: ['composition', 'cast'] });
queryClient.invalidateQueries({ queryKey: ['composition', 'arc'] });
```
Extend the **existing** handler (KG writes are already its domain) rather than register a second
`/^kg_/` handler — `matchEffectHandlers` returns **every** match and `runEffectHandlers` awaits all, so
two overlapping registrations would double-invalidate and give the next agent two homes to forget (the
`arc-inspector` §6.8 "one home" rule). Update `effectCoverage.contract.test.ts` only if it pins the
key set.

**The human writes invalidate their own caches** in `useCastEdit`'s `onSuccess` (the same two keys),
so a rename/create/archive is visible without a manual reload regardless of who wrote.

**No new Lane-B handler file, no `resource_ref` variant required for v1.** (A future agent
`resource_ref {kind:'entity', id}` would land on `bus.activeCastEntityId` — the slice §6 step 7 adds —
but the panel core ships without it. Decompose, don't block.)

---

## 8 · Compliance — stated, not assumed

**Tenancy (scope key).** KG entities are **Per-user** within a book's knowledge project: the scope key
is **`user_id` (owner) + `project_id`** (the project is per-book, 0-or-1, `useCast.ts:12`). Every write
gates server-side on the JWT `user_id`: `createEntity` writes **under** the JWT user (`entities.py:1043`
— "a caller can only ever create entities in their own scope"); `patch`/`archive` collapse cross-user
to **404** (`:1083`, `:184-186`). **There is no System tier and no shared user-editable row** — this is
exactly the kinds-bug class the User-Boundaries law bans, and the KG avoids it by scoping every node to
its author. `project_id` is **a tag on the user's own node, never a cross-tenant handle**
(`entities.py:1045`). The panel filters by `project_id` (resolved from `book_id`) and never surfaces
another user's entities.

**Settings (SET-1..8).** Introduces **zero** settings, toggles, or env flags. The kind-chip filter and
the search box are **per-device view state** (local component state, `CastCodexPanel.tsx:47`) — legitimately
not server settings (they are transient UI, not a user preference two users would want to differ on and
persist). Nothing new to resolve/consume.

**OCC (If-Match).** Every content write is `PATCH /entities/{id}` with `If-Match: W/"<version>"`
(required — 428 without, `entities.py:1093`). A 412 returns the **current entity** (`:1112`), so
recovery is **seed-and-say**, never clobber. Two hard rules mirrored from repo scars:
- **Serialize the write chain** (`instant-commit-control-over-occ-entity-needs-write-serialization`):
  inline rename commits on Enter and the kebab dialog commits on Save; two rapid edits would both send
  `If-Match: v1` and the second would 412 + falsely blame a collaborator. `useCastEdit` chains writes
  and re-seeds the fresh version synchronously (`useSceneInspector.ts:44-47, 65-102`).
- `archive`, `create`, `link` carry **no** version and need none (create is idempotent; archive is
  idempotent; relations are guarded by ownership).

**Cost gate.** **None, by construction.** Every action is deterministic $0 CRUD, no LLM. There is no
propose→confirm here, and adding one would be a defect. (An LLM "suggest a relation / describe this
character" button is a separate, later spec — it would go through the generic composition actions
preview/confirm spine, never a bespoke per-action route.)

---

## 9 · Milestones / slices — each is one commit

| # | Slice | DoD evidence string |
|---|---|---|
| **S1** | **Port `cast` read-only** — `CastPanel.tsx` + catalog row + enum + contract regen + i18n×18 + `bus.activeChapterId` wiring + the kind-chips/search. No edits yet. | The 4 drift-lock suites green (enum==openable==contract, +1). Palette **and** `ui_open_studio_panel{panel_id:"cast"}` mount the tab; it renders a real book's grouped, spoiler-windowed cast. `live smoke: cast tab mounts in a rebuilt image, shows ≥1 group`. |
| **S2** | **Port `character-arc` read-only + the deep-link** — `CharacterArcPanel.tsx` + catalog row + enum + contract + i18n×18 + the `castEntity`/`activeCastEntityId` bus slice + the `onViewArc → openPanel('character-arc',{params:{entityId}})` handoff. | Second drift-lock delta green (+1, three-way equal). Clicking a cast row's arc glyph opens/focuses `character-arc` **on that entity** (verify by EFFECT — a dock tab with the picker on the right character, not a `shown:true`). `live smoke: cast row → arc panel focuses 李慕白`. |
| **S3** | **The ENHANCE — edit** — `useCastEdit` OCC hook + additive edit props on `CastEntityRow` + inline rename + `EntityEditDialog` reuse (aliases/kind) + archive-with-confirm. | Rename a cast member → the row shows the new name **and a bumped `version`**; edit again immediately → **no 412** (the serialization test). Archive → the row leaves the list; the confirm says *"returns if re-mentioned"*, not "restore". `live smoke: rename+re-rename no-412; archive removes row`. |
| **S4** | **The ENHANCE — create** — `+ New` entity (POST /entities, kind-enum) + `+ link entity` on the arc relations strip (POST /relations) + the arc-side `[✎ Edit]` pencil reusing the dialog. | `+ New` creates a character that appears in its group without reload; a duplicate (name,kind) returns the existing node (no dup, no error). `+ link` creates a relation; a self-loop shows the 422 inline. `live smoke: create entity + link relation round-trip`. |
| **S5** | **Agent-write freshness** — extend `knowledgeEffect` to invalidate `['composition','cast']`+`['composition','arc']`; the full live browser smoke (§10). | `effectCoverage` green. With the cast codex open, an agent `kg_create_node` makes the new entity appear **without a manual reload**, and a subsequent human rename does **not** 412 against a version it was never shown. `live smoke: agent kg_create_node → open codex refreshes`. |

---

## 10 · Definition of Done

1. **Unit/contract suites green** — the four in §6, plus `frontend` vitest for the new wrapper + hook
   (`useCastEdit` OCC serialization + 412 reseed; the additive-edit-props render test that the legacy
   no-props path shows **no** edit UI).
2. **The write API has a human consumer.** `grep -rn "onRename\|onArchive\|createEntity\|createRelation" frontend/src/features/composition` finds the new callers — the cast is authorable by a human, not only the map/agent.
3. 🔴 **LIVE BROWSER SMOKE — mandatory.** Against a **rebuilt** image
   (`live-smoke-rebuild-stale-images-first`), signed in as `claude-test@loreweave.dev`, driving dockview
   via `evaluate` + `data-testid` (refs go stale — `playwright-live-dockview-automation-recipe`):
   1. studio → `⌘P` → **Open Cast** → the `cast` tab mounts, shows grouped entities with status dots;
   2. click a character row's arc glyph → `character-arc` mounts/focuses **on that character** (EFFECT,
      not raw stream);
   3. **rename** the character inline → save → **rename again immediately** → **no 412** (serialization);
   4. open the kebab → **Edit aliases & kind** (`EntityEditDialog`) → change kind → save → the group
      re-buckets;
   5. **`+ New`** a faction → it appears in the Factions group without a manual reload;
   6. **`+ link entity`** on the arc strip → the relation appears in the strip; a self-loop → 422 inline;
   7. **archive** an entity → it leaves the list; the confirm copy says *"returns if re-mentioned"*
      (no restore button promised);
   8. **the agent leg + freshness:** in Compose, `kg_create_node` a new character → with the cast codex
      open, it **appears without a manual reload**; then rename it from the panel → **no phantom 412**;
   9. **spoiler-safety:** open a chapter (bus publishes `activeChapterId`) → a character with a
      later "gone" event reads **active** before that chapter and **gone** after — and the `character-arc`
      band + spoiler cut move with the reading position; with no active chapter the `cast-window-hint`
      banner shows.
4. **`/review-impl` on the diff** — load-bearing paths present: **tenant isolation** (every write scoped
   to the JWT user; a cross-user id 404s), **OCC** (no clobber; the serialization + 412 reseed), and
   the **derived-vs-stored** honesty (no status write path shipped). Proactively invoked — this touches
   a tenancy boundary + destructive (archive) op.
5. **SESSION_HANDOFF / S7-RUN-STATE updated** — the `Cast codex`/`Character-arc` rows of the
   S7-A1 matrix flip from ❌❌❌ to operable; DECISIONS + any DRIFT recorded.

---

## 11 · Open questions / Deferred

| # | Question | Disposition |
|---|---|---|
| **OQ-1** | Archived entities vanish from the codex with **no UI restore** (re-extraction only, `entities.py:158-160`). Should the codex offer *Show archived* + a restore route? | **DEFERRED — gate #2 (structural).** There is **no restore route** to call; building one is a real BE change (the anchor is preserved specifically so re-mention re-shows it). The v1 archive confirm is honest about this. **Row as `D-KG-ENTITY-UI-RESTORE`.** |
| **OQ-2** | `createRelation` `predicate` is a **free string** server-side (no enum). Should the `+ link` form hard-enum it? | **CODE-SETTLED (CLARIFY-SYNTHESIS 2026-07-16) — confirmed free-string, suggestions-not-enum is correct.** `relations.py:178` = `predicate: str = Field(min_length=1, max_length=100)`, no membership check. The `+ link` form **suggests** common predicates but must NOT hard-enum them — server enforcement would reject the agent's free-form `kg_propose_edge` edges + existing extraction edges. **Same question/resolution as s7-1 OQ-3** (`D-KG-PREDICATE-VOCAB`); one fact, resolved once. No PO. |
| **OQ-3** | Both list routes cap at `limit:200`; a 200+ cast needs keyset paging + kind-scoped fetch (the codex) and a roster past the cap (the arc). | **OUT OF SCOPE — gate #1.** The 200-cap is the **existing** behavior of `useCast`/`useCharacterArc`; the port does not regress it, and `focusName` already saves the arc picker from a past-cap launch. Paging is its own slice. **Row as `D-CAST-KEYSET-PAGING`.** |
| **OQ-4** | The `active→gone` band is authored by **creating an exit event**, but **`createEvent` has no route** at any layer (`api.ts` has update/archive only). | **NOT this panel's job — event authoring is `kg-timeline`'s.** DP-4 renders the band read-only and disables the "Set state" kebab row with the reason. Whether `kg-timeline` should gain a `createEvent` form is a separate S7/knowledge spec. **Row as `D-KG-EVENT-CREATE-ROUTE`.** |
| **OQ-5** | Does extending `knowledgeEffect` with `['composition','cast']`/`['composition','arc']` over-invalidate (a chatty KG read loop thrashing the cast cache)? | **NO — `KNOWLEDGE_WRITE_PATTERN` already excludes reads** (`knowledgeEffects.ts:16-17` negative-lookahead over `*_list`/`*_query`/…). Only writes fire the handler; the two added keys ride the same gate. Verified, not deferred. |
| **OQ-6** | The draft styles the panels as `category:'editor'`; the catalog category is `storyBible` (DP-1). Any consumer that assumes `editor`? | **Resolved — `storyBible` is in `ALL_CATEGORIES`** (`catalog.ts:100`) and `CATEGORY_ORDER`; the palette groups them with glossary/wiki. The draft's CSS class name is cosmetic. No open item. |
