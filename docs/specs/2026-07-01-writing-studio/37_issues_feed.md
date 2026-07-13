# 37 · The Issues feed — "what is wrong with my book", finally answerable without an LLM

> **Status:** 📐 specced 2026-07-12 · 🔎 **adversarially reviewed + corrected 2026-07-13** (FE-1, the `ref_kind` set, and the 8-source lens were all wrong on the first cut — §4.1.1 / §3 IF-1 / §4.2) · branch `feat/context-budget-law` (studio track) · **M** (files≈14, logic≈7, side_effects=2 — one new read-only route, one producer field)
> **Closes:** **G-DIAGNOSTICS-ISSUES** (M) — [`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) §5.2. **Wave 7.**
> **Unblocked by:** **PO-1** (§0 of plan 30) — spec 28's **AN-12 "no new GUI surface" clause is AMENDED**. Its *architecture* is not: **no new dock panel.** The amendment is written into [`28_agent_native_studio.md`](28_agent_native_studio.md) (§AN-12 AMENDED), not forked here.
> **Surfaces:** the **existing** [`StudioBottomPanel.tsx`](../../../frontend/src/features/studio/components/StudioBottomPanel.tsx) (Issues · Jobs · Generation) + a **right-click lens** on entity badges. **Zero new panel ids.**
> **Backend:** 2 new read-only routes (**BE-1** diagnostics + **BE-1d** entity-references) + the **BE-1a** payload widening + 2 XS producer/filter fixes (**BE-1b/1c**, M3 only). **Zero gateway work** — `gateway-setup.ts:354`'s composition `pathFilter` is generic.
> **Frontend prereq:** **FE-1** — `plan-hub` and `chapter-browser` are **param-blind today** (verified: `focusNodeId`/`focusArcId` = zero hits repo-wide). 3 of 7 rows ship **INERT** until it lands. See §4.1.1.
> Design draft: [`design-drafts/screens/studio/screen-issues-feed.html`](../../../design-drafts/screens/studio/screen-issues-feed.html) ✅ **drawn** (house style §8.3 of plan 30).
> Follows [`docs/standards/dockable-gui.md`](../../standards/dockable-gui.md) · [`docs/standards/mcp-tool-io.md`](../../standards/mcp-tool-io.md) (OUT-1..6).

---

## 1 · Why this exists

**The highest-value read in the product answers only to an LLM.**

`composition_diagnostics` ([`mcp/server.py:3934-4132`](../../../services/composition-service/app/mcp/server.py#L3934-L4132)) ranks
everything wrong with a book across **seven sources**, error → warn → info, in one cheap
call that never touches a model. It is **MCP-only**. There is **no REST route**. The only way a
human reaches it is to ask a chat agent to call it by name, pay for the turn, and trust that the
model neither mis-typed the `book_id` nor hallucinated the answer.

Meanwhile, the human surface that was *designed* to hold exactly this has been a placeholder since
day one:

```tsx
// frontend/src/features/studio/components/StudioBottomPanel.tsx:43-45
<div className="flex flex-1 items-center justify-center …">
  {t(`bottomStub.${tab}`, { defaultValue: 'Feed appears here once wired.' })}
</div>
```

Three tabs — **Jobs · Generation · Issues** — one shared stub string. `en/studio.json:721-725`:
*"Quality issues appear here once wired."* Nothing wires them.

**This is not a broken promise** — spec 01 says *"frame real, content stub"*, and plan 30 §10 REFUTES
the claim that 01 promised a working feed. It is a **new ask**, and it is the right one.

### 1.1 Why AN-12's premise was false (and why the amendment is narrow)

Spec 28 **AN-12** sealed *"No new GUI surface"* on the three agent-native reads, reasoning:
*"the human equivalents already exist… problems → 24's overlay + quality panels."* The audit
checked. **They mostly do not:**

| Diagnostic kind | Human surface today | Ranked? |
|---|---|---|
| `broken_canon_rule` | ✅ `quality-canon` (the PH18 rule lane, `d662bd97d`) | no |
| `canon_contradiction` | ✅ `quality-canon` (the entity lane) | no |
| `conformance_dirty` / `_never_run` | 🟡 a **dot** on the Plan Hub — arc-scoped, not listed | no |
| `open_thread_debt` | ✅ `quality-promises` (read-only, correctly so) | no |
| `unplanned_chapter` | 🟡 the PH21 coverage tray — a count, not a work list | no |
| `index_stale` | ❌ **nothing** | — |
| `prose_deleted_spec_node` | ❌ **nothing** — and it is `error` severity, the **highest** the map has | — |

**~2.5 of 5 sources have a human surface, none is ranked, and the two with no surface at all include
the only ERROR-severity class an author can actually act on.** A `prose_deleted_spec_node` means the
author's *plan* now points at a chapter that no longer exists (26 IX-13: the spec SURVIVES a prose
delete, deliberately). The remedy is re-link or archive. **Today there is no screen anywhere in
LoreWeave that will ever tell them.**

AN-12's *architecture* survives intact and this spec honours it exactly:

- **No new dock panel.** The DOCK-2/DOCK-8 fork AN-12 was actually protecting against — a parallel
  "agent panels" rack duplicating the quality organs — **still cannot happen**, because we ship
  **zero catalog rows**.
- **Issues is a FEED, not an organ.** Every row **deep-links into the panel that owns the fix**. It
  ranks and routes; it never edits. A row that could not name its owning panel would be a design
  failure, not a feature.
- **`composition_find_references` becomes a LENS** — a right-click popover on an entity badge — not
  a panel.

### 1.2 What this closes, in one line

> A GUI user can see, ranked, everything wrong with their book, click any row, and land on the
> control that fixes it — for **$0** and **deterministically**.

---

## 2 · What is already built (be specific — this is what makes the estimate trustworthy)

**The engine is done, and it is review-hardened.** `app/services/agent_native.py` (216 lines) is not
a sketch:

- `Diagnostics.ranked(cap)` — error→warn→info, then most-recent-first via `_neg_ts` (lexicographic
  ISO inversion, no parsing). **Counts are EXACT; only rows are capped**, and it *says* it capped
  (`refs_capped`) — OUT-5 verbatim.
- `SEVERITY` — a **fixed** map (`agent_native.py:60-73`), never computed. A diagnostics tool that
  ranked by its own judgement would be a second opinion competing with the engines that produced
  the findings.
- `Block.failed(warning)` / `Block.into()` — **absent ≠ zero.** A source that could not be read is
  **OMITTED** from the payload and named in `warnings[]`. The module's own docstring: *"'0 unplanned
  chapters' and 'I could not reach book-service' lead to opposite actions, and only one of them is
  honest."* Every consumer is forced to branch.
- Each of the 7 sources **composes** an engine that already owns its number:
  `compute_conformance_status` · `OutlineRepo.canon_issues` · `OutlineRepo.rule_violations` ·
  `NarrativeThreadRepo.list_open` · `compute_prose_deleted` · `compute_coverage`. **It never
  recomputes.**

**The entity-backlinks engine is done too.** `EntityReferencesRepo`
([`db/repositories/entity_references.py`](../../../services/composition-service/app/db/repositories/entity_references.py))
— 8 real joins, exact counts, capped refs, uniform `{source, node_ref:{kind,id,title}, detail}` rows.

**The deep-link seam is done — but only on ONE of its two ends.** `PlanHubPanel.tsx:72-76` already
does the exact move every Issues row needs:

```ts
openPanel('quality-canon', {
  focus: true,
  params: { bookId, focusRuleId: ref.id, focusChapterId: chapterId },
});
```

and `useQualityCanon.ts:74-75,107,111` **reads** those params and hoists the focused rule/chapter to the
top of the list. **Do not rebuild this seam. Reuse it.**

> 🔴 **But the seam is one-directional, and that asymmetry is FE-1 (§4.1.1).** `plan-hub` **emits** a
> params deep-link; it **consumes** none. Neither does `chapter-browser`. Emitting ≠ accepting — and
> three of this feed's seven rows point at exactly those two panels. **Verified: `focusNodeId` /
> `focusArcId` have ZERO hits repo-wide.** `quality-canon` is the *only* target that works today.

**What is NOT built:** any REST route for `composition_diagnostics`, `composition_package_tree`, or
`composition_find_references`. Zero. `grep -rn "diagnostics" services/composition-service/app/routers/`
→ empty.

---

## 3 · The three bugs that make this a REAL spec and not a wiring ticket

The audit's estimate ("a mechanical lift of the MCP handler") is **right about the engine and wrong
about the payload.** The MCP handler builds `node_ref` for an *agent*, which reads titles and
reasons in prose. A *GUI* has to **navigate** on it — and three fields it needs are dropped on the
floor.

### IF-1 🔴 `node_ref.kind:"chapter"` names **two different id spaces**

| Diagnostic | `node_ref` emitted | `id` actually is |
|---|---|---|
| `unplanned_chapter` (`server.py:4125`) | `{kind:"chapter", id: ch["chapter_id"]}` | a **book-service `chapter_id`** |
| `prose_deleted_spec_node` (`server.py:4099`) | `{kind: n["kind"] or "chapter", id: n["id"]}` | a **composition `outline_node.id`** — and a chapter-kind outline node's `kind` is *literally the string* `"chapter"` |

Two rows, identical shape, **disjoint id spaces**. A frontend that trusts `kind` and opens the
`editor` on a `prose_deleted_spec_node` sends an `outline_node` UUID where a `chapter_id` belongs
and gets a 404 — or, far worse, a collision. This is the repo's own
`cross-service-normalization-bug-class`, pre-loaded into a payload nobody has consumed yet.

**Fix (in the REST mirror, and back-ported to the MCP tool):** `node_ref` gains an explicit
`ref_kind` naming the **ID SPACE** — from a closed set of exactly the **three id spaces that exist**:

| `ref_kind` | The id is | Emitted by |
|---|---|---|
| `chapter` | a **book-service** `chapter_id` | `unplanned_chapter` |
| `outline_node` | a composition `outline_node.id` (its `kind` column may be `chapter` **or** `scene`) | `canon_contradiction`, `broken_canon_rule`, `prose_deleted_spec_node` |
| `structure_node` | a composition `structure_node.id` (saga/arc) | `conformance_dirty`, `conformance_never_run` |

`kind` stays as the **display** label (`"scene"`, `"chapter"`, `"arc"`). `ref_kind` is the **routing**
key. One name, one concept.

> ⚠ **`scene` and `canon_rule` are NOT members of this set, and that is deliberate.** An earlier cut of
> this spec proposed `chapter|outline_node|structure_node|canon_rule|scene` — which is **wrong twice**:
> - **`scene` IS an `outline_node`.** Verified: both canon lanes `SELECT n.id AS scene_id … FROM
>   outline_node n` (`outline.py:1214`, `:1338`). A set carrying both `scene` and `outline_node` names
>   **one id space with two names** — precisely the ambiguity IF-1 exists to kill, re-introduced inside
>   its own fix, and a straight breach of the one-name-one-concept rule the same paragraph invokes.
> - **No diagnostic emits a `canon_rule` node_ref.** `broken_canon_rule` gains `rule_id` as a
>   **sibling field** (IF-2), not as a `node_ref`. A closed-set member nothing emits is dead enum
>   surface — and a `CLOSED_SET_ARGS` enum that over-advertises is its own defect class.
>
> Three id spaces exist. The set has three members. **Do not re-add the other two.**

### IF-2 🔴 `broken_canon_rule` drops the `rule_id` — the deep-link's only key

`OutlineRepo.rule_violations` returns `rule_id`, `chapter_id`, `scene_id`, `rule_text`, `why`,
`span` ([`outline.py:1338-1345`](../../../services/composition-service/app/db/repositories/outline.py#L1338-L1345)),
and its docstring is explicit: *"the rule→violation link the Plan Hub's canon badge needs already
exists; it lives here."*

The diagnostics handler (`server.py:4043-4050`) keeps `rule_text` (inside a *string title*) and
throws `rule_id` and `chapter_id` away.

**Consequence:** the one row in the whole feed whose owning panel is already built and already
accepts a focus param **cannot be deep-linked**, because the payload no longer carries the key.
`quality-canon` takes `focusRuleId` — and the feed has nothing to put in it.

### IF-3 🔴 `scene-inspector` selects from the **BUS**, not from `params`

`useSceneInspector.ts:24` — `const activeSceneId = useStudioBusSelector((s) => s.activeSceneId)`.
It ignores panel params entirely.

So a row that does `openPanel('scene-inspector', { params: { nodeId } })` opens an inspector
showing **whatever scene was last selected** — a silent wrong-target, the exact
`silent-success-is-a-bug` class. The correct move is `host.publish({ type:'scene', sceneId, chapterId })`
**then** `openPanel('scene-inspector')`.

And the bus event **requires `chapterId`** (`host/types.ts` — `{type:'scene'; sceneId: string; chapterId: string}`).
`canon_issues` returns `chapter_id` ([`outline.py:1214`](../../../services/composition-service/app/db/repositories/outline.py#L1214)).
The diagnostics handler **drops it.** Same bug as IF-2, different row.

> **These three are the spec.** The route is a lift; the *payload contract* is the work.

---

## 4 · The design

### 4.0 The surface — where it lives

`StudioBottomPanel` is mounted at `StudioFrame.tsx:160` (`{chrome.bottomOpen && <StudioBottomPanel …/>}`),
height-fixed at `168px`, tab state local. It is **outside dockview** — which is precisely why AN-12's
fork risk does not apply, and also why it is **not** in `catalog.ts` and **must not** be added to the
`panel_id` enum (§6).

**Structural rule (CLAUDE.md — never conditionally unmount stateful components):** the three tab
bodies keep the CSS-`hidden` pattern, **not** a ternary. Each tab owns a live subscription (the Jobs
tab an SSE stream); a ternary would tear it down on every tab switch. The current file renders one
`<div>` for whichever tab is active — **that must change to three always-mounted bodies** the moment
the first tab has state. This is a *behavioral* change to an existing file, and it is the first thing
to write.

**Height.** 168px is ~4 rows. The panel gains a **drag-resize grip** (persisted per-device in
localStorage — a legitimate per-device UI preference under the Data Persistence rules; **not** a
server setting).

---

### 4.1 The **Issues** tab

**Layout** (one row per finding, densest-possible; the house-style `.trow` grid):

```
[sev] │ kind chip      │ title                                             │ where     │ at
  ●   │ ERROR  canon   │ 3 canon violation(s) in "Nàng bước vào sương mù"  │ Ch.41 ▸   │ 2h ago
  ●   │ ERROR  spec    │ "Arc II — the debt" points at a deleted chapter   │ plan ▸    │ —
  ▲   │ WARN   conform │ arc "Trấn Nam" — never_run                        │ plan ▸    │ —
  ▲   │ WARN   plan    │ chapter "第四十二章" is written but not planned    │ Ch.42 ▸   │ —
  ○   │ INFO   threads │ 7 open promise(s) still unpaid                    │ quality ▸ │ —
```

**Toolbar (row 1):** severity filter chips (`All · Error 2 · Warn 5 · Info 1` — counts from the
**exact** `counts` map, never from the capped rows) · a `kind` select · a **Refresh** button.
**Toolbar (row 2, conditional):** the **warnings strip** — see 4.1.3, it is load-bearing.

**Footer:** `mono` — `Showing 25 of 38 findings · computed just now`. When `refs_capped` is true the
"of 38" is the honest total and the strip says so.

#### 4.1.1 The row → panel routing table (the whole point of the feed)

| kind | severity | Deep-link effect | Target | Target reads its param **today**? |
|---|---|---|---|---|
| `canon_contradiction` | error | `publish({type:'scene', sceneId, chapterId})` → `openPanel('quality-canon', {focus:true, params:{bookId, focusChapterId}})` | `quality-canon` (entity lane) | ✅ **YES** — `useQualityCanon.ts:75,111` hoists `allIssues` on `i.chapter_id === focusChapterId` |
| `broken_canon_rule` | error | `openPanel('quality-canon', {focus:true, params:{bookId, focusRuleId, focusChapterId}})` — **the PH18 seam** | `quality-canon` (rule lane) | ✅ **YES** — `useQualityCanon.ts:74,107` hoists `allRules` on `r.rule_id === focusRuleId` |
| `prose_deleted_spec_node` | error | `publish({type:'scene'…})` is **wrong** (it is an outline node, maybe a chapter node) → `openPanel('plan-hub', {params:{bookId, focusNodeId}})` | `plan-hub` | 🔴 **NO — FE-1** |
| `conformance_never_run` · `conformance_dirty` | warn | `openPanel('plan-hub', {params:{bookId, focusArcId}})` — and the row offers **Run conformance** (cost-gated, §8.4) | `plan-hub` | 🔴 **NO — FE-1** |
| `unplanned_chapter` | warn | `openPanel('chapter-browser', {params:{bookId, focusChapterId}})` | `chapter-browser` | 🔴 **NO — FE-1** |
| `index_stale` | warn | **no panel** — the sweeper heals it. Row is informational, click is a no-op, and the row **says so** (`detail`: *"the sweeper heals these"*). | — | n/a (inert by design) |
| `open_thread_debt` | info | `openPanel('quality-promises', {focus:true, params:{bookId}})` | `quality-promises` | ✅ **YES** — `QualityPromisesPanel.tsx:23` reads `props.params`; the debt row passes no focus id (it is a rollup) |

#### 🔴 FE-1 — **three of these seven targets are PARAM-BLIND today. VERIFIED, not assumed.**

This was the spec's own worst bug, and it is the exact class it was written to kill. **Verified at
HEAD `9262ed53e`:**

- `grep -rn "focusNodeId\|focusArcId" frontend/src` → **ZERO hits repo-wide.** Neither param exists.
- `PlanHubPanel.tsx:39` → `useStudioPanel('plan-hub', props.api);` — the return value is **discarded**
  and `props.params` is **never read**. Plan Hub **EMITS** a params deep-link (`:74`); it **CONSUMES**
  none.
- `ChapterBrowserPanel.tsx:23` → `useStudioPanel('chapter-browser', props.api);` — **same**. It reads
  no `props.params` at all.
- ⚠ **`useStudioPanel` does NOT "expose params."** Its signature is
  `useStudioPanel(panelId, api, extras?) -> string` — it returns the **localized label** and nothing
  else. Params arrive **only** as the dockview prop `props.params` (the shipped pattern:
  `JobDetailPanel.tsx:24`, `QualityPromisesPanel.tsx:23`, `KgEntitiesPanel.tsx:18`). An earlier draft
  of this spec asserted the opposite. **It was wrong. Do not re-introduce that claim.**

**So `openPanel('plan-hub', {params:{focusNodeId}})` mounts the Plan Hub and focuses NOTHING.** The
dock tab appears, the user sees an unfocused tree, and the click "worked". That is
`silent-success-is-a-bug`, and shipping it inside the feed whose §3 IF-3 *names that very class* would
be indefensible.

**FE-1 (MUST-BUILD, S, M1b):** `PlanHubPanel` reads `props.params.focusNodeId` / `.focusArcId` and
selects+reveals that node; `ChapterBrowserPanel` reads `props.params.focusChapterId` and
hoists+highlights that row. **Mirror `useQualityCanon`'s `hoist()` — a focus HOISTS and HIGHLIGHTS, it
never filters/hides** (`useQualityCanon.ts:15-16` states that contract; do not invent a second one).
⚠ Both files are owned by the **Book-Package track** (plan 30 §9) — **coordinate before editing.**

**IF-4 (a decision, recorded so it is not "fixed" back) — REVISED to close the hole above:**
a row renders **without a chevron, is not clickable, and carries the reason in its `title`** when
**either**

1. **no panel owns the fix** (`index_stale` — the sweeper heals it), **or**
2. 🔴 **its target panel is PARAM-BLIND** — i.e. the panel exists but does not yet read the focus
   param this row needs (the three FE-1 rows, until FE-1 lands).

Case (2) is the one the first cut of this spec missed. **"The panel exists" is NOT the test — "the
panel will actually focus what I clicked" is.** A row that opens a panel onto nothing is *worse* than
an inert row: an inert row is honest, and a false-focus row teaches the user the feed lies. Ship **M1
with the three FE-1 rows inert** (chevron-less, reason in `title`), and light them up in **M1b** when
FE-1 lands. **Do not block the feed on FE-1** — 4 of 7 kinds route correctly on day one.

#### 4.1.2 Every state, rendered (none hand-waved)

| State | Render |
|---|---|
| **Loading** | 4 skeleton rows. Never a spinner-in-a-void — the tab is 168px tall. |
| **Empty (genuinely clean)** | *"No issues found across 7 sources."* — **and the source list**, so the user can see what was checked. |
| **Empty (degraded)** | 🔴 **NEVER the clean state.** If `warnings[]` is non-empty the empty body says *"No issues found in the sources that answered — **N sources could not be read.**"* + the strip. (§4.1.3.) |
| **Error (route 4xx/5xx)** | One inline row with the status + a Retry. The tab never blanks. |
| **No Work** (`resolve_scope` → `(None, None)`) | The route still answers (the spec tree is book-keyed). Renders whatever answered + the warning *"this book has no composition work — canon issues, thread debt and motif applications were NOT checked."* |
| **Capped** | Footer + strip: `Showing 25 of 38` (exact total). |
| **Stale** | A `computed_at` relative time in the footer; **Refresh** re-fetches. No polling (§4.1.4). |

#### 4.1.3 🔴 The warnings strip is NOT optional chrome

`agent_native.py`'s whole design is **absent ≠ zero**. If the FE renders a degraded diagnostics
response as *"No issues found"*, it converts the engine's careful honesty into the exact lie the
engine was written to prevent — and it does it on the one screen the user trusts to tell them their
book is fine.

**Contract:** `warnings.length > 0` ⇒ an amber strip renders **above** the rows, listing each
warning verbatim, and the empty-state copy switches. **This is a unit test (§10 DoD-3), not a
convention.**

#### 4.1.4 Freshness — pull, not push

The route is a **cheap read** but not free (it fans out to book-service twice — `compute_coverage`
and `compute_prose_deleted` each pull the chapter spine). **No polling. No SSE.** It refetches on:
(a) tab open, (b) the Refresh button, (c) a **Lane-B effect** after an agent write to any of its
sources (§7). React-Query `staleTime: 60_000`.

---

### 4.2 The **find-references** lens (not a panel — PO-1, verbatim)

**Trigger:** right-click (and a keyboard-accessible `⋯` affordance — a right-click-only feature is an
a11y defect) on an **entity badge**:

- [`frontend/src/features/plan-hub/components/NodeBadges.tsx`](../../../frontend/src/features/plan-hub/components/NodeBadges.tsx)`:100-124` — the Plan Hub's `case 'cast'` chip (`data-testid="plan-badge-cast-…"`). ⚠ It lives under **`features/plan-hub/`**, *not* `features/studio/` — and is therefore **Book-Package-track-owned** (§9), same as `PlanHubPanel.tsx`. **Coordinate.**
- [`frontend/src/features/studio/panels/EntityRefField.tsx`](../../../frontend/src/features/studio/panels/EntityRefField.tsx) — the scene-inspector's POV / present-cast fields (studio-owned; no coordination needed)

**Renders:** a popover, ~320px, over the badge — **one row per source, and there are EIGHT:**

```
  Lâm Thanh Vân                                    ✕
  ─────────────────────────────────────────────────
  POV · chapters        4               ▸    outline_pov
  POV · scenes          11              ▸    scene_pov
  Present · chapters    7               ▸    outline_present
  Present · scenes      23              ▸    scene_present
  Cast in arc roster    2 arcs · "the mentor" ▸  structure_roster
  Motif applications    6               ▸    motif_application
  Canon rules           1               ▸    canon_rule
  Promises opened       3               ▸    narrative_thread
  ─────────────────────────────────────────────────
  Composition scope only — prose mentions live in
  the glossary; graph edges in the KG.
```

#### 🔴 EIGHT rows, not six — one per `REFERENCE_SOURCES` member. This is not cosmetic.

`REFERENCE_SOURCES` (`agent_native.py:53-56`) is **exactly eight**:

```python
"outline_pov", "outline_present", "scene_pov", "scene_present",
"structure_roster", "motif_application", "canon_rule", "narrative_thread",
```

An earlier cut of this spec drew **six** — collapsing the pov/present pairs and thereby **silently
dropping `outline_present` and `scene_pov` entirely.** That is a bug for two independent reasons:

1. **It under-reports.** A character who is present-cast on 7 **chapter** nodes but zero scene nodes
   reads as "Present in — 0". The author concludes she is unused. She is not.
2. 🔴 **A source with no row cannot render its own degrade.** The repo degrades **per source**
   (`server.py:3909-3913` → `{"error": "this source could not be read"}`). A source the lens never
   draws is a source whose failure is **invisible** — the popover silently answers a question it
   never asked. That is the *same* absent≠zero violation §4.1.3 exists to prevent, committed in the
   sibling surface.

**The split by node kind is the repo's own design, stated in its docstring:** *"there is no `scenes`
table in this database … `outline_node` holds BOTH chapters and scenes (`kind`), so the pov/present
pair splits by kind"* (`entity_references.py:17-21`). **Render the split. Do not re-collapse it.**
If a future PO decides two merged rows read better, the merged row **must** sum the exact counts of
both sub-sources **and** degrade if *either* sub-source errored — which is strictly more code than
just drawing eight rows.

**Exact counts, capped sample rows on expand** (the repo already returns both — `has_more` per
source). Each expanded row deep-links exactly like an Issues row (§4.1.1 routing) — **including the
FE-1 inert rule**: an expanded `structure_roster` row targets `plan-hub`, which is param-blind until
FE-1 lands, so it is **inert in M2** exactly as the Issues rows are in M1.

**The footnote is not decoration** — it is the tool's own `_meta.note` (`server.py:3926-3930`)
rendered. Omitting it invites the user to read "23 scenes" as "23 mentions in the prose", which is a
different, wrong number.

**States:** loading (**8** skeleton rows — one per source) · a per-source
`{error: "this source could not be read"}` → that row renders **"could not be read"**, not `0` (the
repo degrades per-source, `server.py:3909-3913` — do not collapse it to a zero) · all-zero →
*"Not referenced anywhere in the spec layer — all 8 sources answered, all 8 returned 0."* (**that copy
is only honest if all 8 actually rendered** — see above).

---

### 4.3 The **Jobs** and **Generation** tabs (the rest of the bottom panel)

Plan 30 §7: *"+ Jobs + Generation, which are equally dark, in the same file, and the same shape of
fix."* They are — with **one honest blocker the audit did not name.**

**Jobs** = the book's background work: translation, extraction, import, composition generation.
The data exists: `jobsApi.list/summary/stream` + `JobsStreamProvider` (the `jobs-list` panel is
built and shipped). The bottom tab is a **compact, book-scoped mirror** — 4 rows, `title · kind ·
status · progress`, click → `openPanel('job-detail', {params:{service, jobId}})`.

**Generation** = the composition slice, live: the in-flight `generation_job` for the chapter/scene
you are editing, streaming its critic verdict on completion. Same store, filtered to
`service === 'composition'`, plus a deep-link to the `editor`.

> 🔴 **The blocker: jobs-service cannot filter by book, and the composition producer never stamps
> one.** `GET /v1/jobs` accepts `status · kind · parent · q · bucket · cursor · offset · limit`
> ([`jobs-service/app/routers/jobs.py:42-51`](../../../services/jobs-service/app/routers/jobs.py#L42-L51))
> — **no `book_id`**. And the `Job` projection has no book column: composition's
> `_job_params` (`generation_jobs.py:127-140`) emits `model · model_ref · operation · mode ·
> reasoning · …` and **not `book_id`**.
>
> So a *book-scoped* Jobs feed is **unbuildable today** — and a bottom panel inside a per-book Studio
> that shows the user's jobs **from every book they own** is not a feature, it is noise.
>
> This is **buildable, not blocked** (CLAUDE.md's anti-laziness rule): **BE-1b** stamps `book_id`
> into `params` at the producer (one line, additive — and the projection's COALESCE merge means a
> later event without it never wipes it: `jobs-projection-usage-fields-coalesce-merge`), **BE-1c**
> adds the `book_id` filter to `GET /v1/jobs`. Both XS. **Both are cross-service ⇒ a live-smoke is
> mandatory**, not optional.

**Until BE-1b/1c land, the Jobs and Generation tabs stay stubbed** — and the stub string changes
from the lie *"once wired"* to the truth: *"Book-scoped job feed — pending `book_id` on the jobs
projection (BE-1b)."* **A stub that names its blocker is honest; one that says "soon" for eight
months is not.** They are **M3**, and M1/M2 do not depend on them.

---

## 5 · Backend prerequisites — this section is a contract

| # | Route | METHOD + path | Request | Response | Errors | Size | Status |
|---|---|---|---|---|---|---|---|
| **BE-1** | **book diagnostics** | `GET /v1/composition/books/{book_id}/diagnostics` | query: `limit` (1..100, **default 25**, clamped ONCE — mirror `server.py:3966`) · `severity` (optional, enum `error\|warn\|info`) · `kind` (optional, enum = the 8 `SEVERITY` keys) | `{book_id, items[], counts{}, total, refs_capped, warnings[]?}` — **byte-identical to `Diagnostics.ranked()`** plus the IF-1/IF-2/IF-3 payload widening below | `403` no VIEW grant · `404` no such book (**uniform** — `authorize_book` → `OwnershipError` ⇒ 404, `InsufficientGrant` ⇒ 403; H13, no enumeration oracle) · **never 500 on a degraded source** (that is a `warnings[]` entry) | **S** | **MUST-BUILD** |
| **BE-1a** | **payload widening** (the real work — §3) | — (same route + back-port to the MCP tool) | — | every `node_ref` gains `ref_kind` — closed set **`chapter\|outline_node\|structure_node`**, the 3 id spaces that exist (**NOT** `scene`/`canon_rule` — §3 IF-1) — plus `chapter_id` where the source has it; `broken_canon_rule` gains `rule_id` | — | **S** | **MUST-BUILD** |
| **FE-1** | **param-blind deep-link targets** (§4.1.1) | — (frontend) `PlanHubPanel.tsx` · `ChapterBrowserPanel.tsx` | — | read `props.params.{focusNodeId,focusArcId}` / `.focusChapterId` and hoist+reveal (mirror `useQualityCanon`'s `hoist()`) | — | **S** | **MUST-BUILD** *(M1b — 3 rows ship INERT until then; ⚠ Book-Package track owns both files)* |
| **BE-1b** | `book_id` on the jobs projection | — (producer) `generation_jobs.py:127` `_job_params` | — | `params.book_id` | — | **XS** | **MUST-BUILD** *(M3 only)* |
| **BE-1c** | jobs LIST book filter | `GET /v1/jobs?book_id=…` | +1 query param | unchanged | — | **XS** | **MUST-BUILD** *(M3 only)* |
| **BE-1d** | entity references | **DECISION — §5.2** | — | — | — | **S** | **DECIDE** |
| — | gateway | — | — | — | — | **0** | ✅ **EXISTS** — `gateway-setup.ts:354` `pathFilter: (p) => p.startsWith('/v1/composition')`, no rewrite. A new composition route is auto-proxied. |

### 5.1 BE-1 — the shape, precisely

Mirror `routers/conformance.py:424-454` (`read_conformance_status`) — it is the **same class of
route** (book-scoped, VIEW-gated, cheap, composes an engine):

```python
@router.get("/books/{book_id}/diagnostics")
async def read_diagnostics(
    book_id: UUID,
    limit: int = Query(25, ge=1, le=100),
    severity: Literal["error", "warn", "info"] | None = Query(None),
    kind: str | None = Query(None),                      # validated against SEVERITY.keys()
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
```

**Three things the lift must not get wrong:**

1. **The bearer.** The MCP handler mints a service bearer (`mint_service_bearer(tc.user_id, …)`)
   for its two book-service calls. A REST route has the **user's own JWT** — use it
   (`plan_overlay.py:255` is the precedent for `compute_coverage(book_id, bearer, …)` from a router).
   Minting a service bearer inside a user-facing route re-opens the
   `internal-route-driven-by-a-session-must-grant-check` hole. The E0 VIEW gate runs **first**, so
   the user's own token is both sufficient and correct.
2. **Extract the body, do not fork it.** The ~180-line source-fanout in `composition_diagnostics`
   moves to `agent_native.build_diagnostics(pool, book_client, book_id, bearer, cap) -> Diagnostics`,
   and **both** the MCP tool and the route call it. Two implementations of the problems panel is the
   `css-var-duplicated-across-two-consumers-drifts` bug, and this module's own docstring
   (*"It composes. It never recomputes."*) already forbids it.
3. **`severity`/`kind` filter AFTER ranking, and keep `counts` UNFILTERED.** The chip counts must show
   what exists, not what is shown. A filtered `counts` map turns "Error 2" into "Error 0" the moment
   you click the Info chip — and the user reads that as "my errors went away".

### 5.2 BE-1d — find-references: REST route **or** MCP bridge?

Two viable paths. **The spec picks REST. Recorded so it is not re-litigated:**

| | REST (**chosen**) | `mcpBridge` (`mcpExecute`) |
|---|---|---|
| Route | `GET /v1/composition/books/{bid}/entity-references?entity_id=…&sources=…&limit=…` | none |
| Cost | 1 thin route over `EntityReferencesRepo` | 1 name added to `FE_BRIDGE_TOOL_ALLOWLIST` (`tools.controller.ts:24`) |
| Verdict | ✅ every sibling panel reaches composition over **REST**; a *read* has no propose→confirm to justify the bridge | ❌ the bridge's allowlist is **exactly 5 names** (`tools.controller.ts:24-30`): **4 cost-gated PROPOSE flows** (`composition_conformance_run`, `composition_motif_mine`, `composition_motif_adopt`, `composition_arc_import_analyze`) **+ 1 POLL** (`composition_get_mine_job`). Every member is **spend-adjacent**. Adding a free read widens that allowlist for no benefit. |

> ⚠ **The path `/works/{pid}/references` is TAKEN.** `routers/references.py` is the author's
> **research reference shelf** (`reference_source` + embeddings, LOOM T3.6) — an entirely different
> concept the repo already flags as a name collision (`entity_references.py:8-15`). The new route is
> **book-scoped** and named `entity-references`. **One name, one concept.**

`sources` is a **closed set** (the 8 `REFERENCE_SOURCES`) and must be validated as an enum on the
route — `EntityReferencesRepo.find` **raises** on an unknown source *precisely so a typo cannot
return `(0, [])`*, which would read as *"this entity is used nowhere"*. Do not catch that into a zero.

---

## 6 · Registration checklist (GG-8) — **how the guards stay green with ZERO new panel ids**

**This spec adds NO panel. That is the design, and it is also what keeps the two drift-locks green.**

Current state, verified: **py enum 57 == contract enum 57 == openable 57, zero drift.**
`panelCatalogContract.test.ts` asserts *sorted equality* between `OPENABLE_STUDIO_PANELS` and the
backend `panel_id` enum. **Therefore:**

| GG-8 step | This spec |
|---|---|
| 1. `panels/<New>.tsx` | ❌ **none.** New files are `components/bottom/IssuesTab.tsx`, `JobsTab.tsx`, `GenerationTab.tsx`, `hooks/useDiagnostics.ts`, `panels/EntityReferencesLens.tsx` — **none is a dock panel.** |
| 2. `catalog.ts` | ❌ **no row.** |
| 3–4. i18n `panels.<id>.*` × 18 locales | ❌ none. **But:** the `bottomStub.*` keys **change meaning** (§4.3) and new keys land under `bottom.*` / `issues.*` / `refs.*` → **`python scripts/i18n_translate.py`, never hand-written.** |
| 5. `frontend_tools.py` `panel_id` enum | 🔴 **DO NOT ADD `"issues"`.** The enum is machine-locked to `OPENABLE_STUDIO_PANELS`; a pseudo-id with no catalog row **REDS `panelCatalogContract.test.ts` immediately** (and rightly — `ui_open_studio_panel` resolves through dockview, which cannot mount the bottom panel). See **OQ-1**. |
| 6. `contracts/frontend-tools.contract.json` | ❌ no regen needed. **Assert it: the contract file must be BYTE-IDENTICAL before and after this wave.** That is DoD-5. |
| 7. `studioLinks.ts` | ❌ none (no new URL shape). |
| 8. **Lane-B effect handlers** | ✅ **YES — mandatory (X-4).** §7. |
| 9. tours | ❌ none. |

**The guard we DO add** (this spec's one contribution to the drift-locks):

> `frontend/src/features/studio/components/__tests__/StudioBottomPanel.test.tsx` (**it exists — `.tsx`,
> not `.ts`**) gains: **every `BottomTab` id has a `bottom.<id>` label key AND a rendered body
> component** — the mechanical version of "the tab is wired". Today's test asserts the **stub string is
> present** (`:9` — `expect(panel.textContent).toContain('bottomStub.jobs')`) — i.e. it currently
> **guards the bug**. That assertion inverts.
>
> ⚠ **The always-mounted refactor (§4.0) also REDS `:12`** — `expect(panel.textContent).not.toContain('bottomStub.jobs')`
> after a tab switch. With three CSS-`hidden` bodies, **all three bodies' text stays in
> `textContent`** (hidden elements still contribute to it). The rewritten test must assert on
> **visibility**, not on `textContent` — e.g. `expect(screen.getByTestId('bottom-body-jobs')).not.toBeVisible()`.
> Asserting `textContent` after this refactor is how a green test would certify the wrong thing.

---

## 7 · Agent surface

### 7.1 Lane-B effect handlers (X-4 — mandatory for this batch)

`useStudioEffectReconciler.ts` registers patterns for `book_.*(draft|chapter)`,
`composition_.*(prose|draft)`, `composition_(outline_node|scene_link)_`, glossary, knowledge,
`translation_job_control`. **Nothing invalidates the Issues feed.** So today: the agent fixes a canon
rule, and the human's problems panel keeps showing the problem — the exact staleness X-4 exists to
kill.

**New handler — `frontend/src/features/studio/agent/handlers/diagnosticsEffects.ts`:**

```ts
const DIAGNOSTICS_STALING = /^composition_(canon_rule_|conformance_run|outline_node_|arc_|motif_(bind|unbind))/;
registerEffectHandler(DIAGNOSTICS_STALING, (ctx) => {
  ctx.queryClient.invalidateQueries({ queryKey: ['composition', 'diagnostics', ctx.bookId] });
  ctx.queryClient.invalidateQueries({ queryKey: ['composition', 'entity-references', ctx.bookId] });
});
```

⚠ **Do not use `invalidateQueries` for anything the bottom panel holds in hand-rolled state**
(`invalidatequeries-cannot-reach-hand-rolled-state`). The Issues tab **must** own its data through
React-Query for this handler to reach it. That is a design constraint, not a preference.

⚠ Also delete the now-FALSE comment at `useStudioEffectReconciler.ts:7-9` (X-4 names it).

### 7.2 The INVERSE gap — can the agent do anything the human still cannot?

**Yes, and after this spec it still can — deliberately.**

| Capability | Human (after this spec) | Agent |
|---|---|---|
| Read ranked diagnostics | ✅ Issues tab | ✅ `composition_diagnostics` |
| Read entity backlinks | ✅ the lens | ✅ `composition_find_references` |
| **Read the package tree** (`composition_package_tree`) | ❌ **still none** | ✅ |

`composition_package_tree` is the agent's `ls -R` — arc count, chapter count, index freshness,
coverage gap, recent runs. **The human's equivalent genuinely does already exist**, spread across
`plan-hub` (the tree), `chapter-browser` (the spine), and the PH21 coverage tray. Unlike diagnostics,
**AN-12's premise holds for this one.** Building a "book at a glance" panel would be exactly the
DOCK-2 fork AN-12 forbids.

**Decision (IF-5): `composition_package_tree` gets NO human surface. AN-12 stands for it.** The
amendment lifts the clause for `diagnostics` and `find_references` **only**. Written into spec 28.

### 7.3 Discovery scent (X-10) — **out of scope here**

AN-C2 (the `book_context_note` sentence naming these tools) touches
`chat-service/app/services/stream_service.py`, which is **uncommitted and mid-edit by Track C**
(plan 30 §9). **Do not touch it.** X-10 sequences after Track C lands.

---

## 8 · Compliance — tenancy · settings · OCC · cost-gates

**8.1 Tenancy.** **No new table. No new row. No new scope key.** Every read is
**Per-book**, gated at the E0 grant on `book_id` (`authorize_book(grant, book_id, user_id, VIEW)`)
**before** any repo call. Denial and missing-row return the **same** response (H13 — 404 for
`OwnershipError`, 403 for `InsufficientGrant`, no enumeration oracle). The diagnostics fanout's
project-keyed sources resolve the **canonical Work** via `resolve_scope` (PM-3/PM-4) — a derivative's
rows never merge into the source's feed. **A collaborator with VIEW sees the book's issues; that is
correct — they are the book's, not the owner's.**

**8.2 Settings.** **This spec adds ZERO settings.** The severity filter is ephemeral UI state
(component state, not persisted — it is a lens on a list, not a preference). The panel **height** is
`localStorage` — explicitly sanctioned by CLAUDE.md ("UI state that is per-device — OK in
localStorage (e.g. sidebar collapsed, editor panel widths)"). **No new `*_ENABLED` env flag.**
Nothing here is a user setting, so SET-1..8 is satisfied by having nothing to satisfy.

**8.3 OCC.** **This spec performs zero writes.** Every surface is Tier-R. There is no `If-Match`, no
`expected_version`, and **no 412 state to design** — the Issues feed *routes to* the panels that own
the OCC writes (`quality-canon`, `scene-inspector`, `plan-hub`), and each already handles its own
412. **A feed that could edit would be the DOCK-2 fork.** It cannot.

**8.4 Cost gates.** One row type offers a **paid** action: `conformance_never_run` / `_dirty` →
**Run conformance**.

- It goes through the **generic** spine — `GET /v1/composition/actions/preview` →
  `POST /v1/composition/actions/confirm`, descriptor `composition.conformance_run` (already
  dispatched at `actions.py:75, 343 → _execute_conformance_run:714`).
- 🔴 **NEVER** the two invented per-action paths `/actions/conformance_run/estimate` +
  `/confirm` — they **404 in production today** (plan 30 §3.3; `motif/api.ts:224,230`). This spec
  does **not** fix that live bug (Wave 3 owns it) and **must not copy it.**
- The button needs a **BYOK `model_ref`** (arc-scope conformance is `deep`) ⇒ it renders a
  `ModelPicker` ⇒ its empty state renders **`AddModelCta`** ⇒ 🔴 **X-1 (the DOCK-7 teardown) is a
  HARD PREREQUISITE.** Without X-1, clicking "add a model" from the bottom panel **destroys the
  user's entire dock layout.** If X-1 has not landed, **ship M1 without the Run button** (the row
  still deep-links to `plan-hub`) rather than shipping the landmine.
- **Paid-action-in-flight state:** the row shows a spinner + the job id, disables the button, and the
  finished job lands via the Lane-B handler (§7.1) → the row **disappears** because the source
  re-ranks. No optimistic mutation of a diagnostics row, ever — it is a *derived* read.

---

## 9 · Milestones

| # | Slice | Contents | DoD |
|---|---|---|---|
| **M1** | **The Issues feed** | BE-1 + BE-1a (route + payload widening + `build_diagnostics` extraction) · `IssuesTab.tsx` + `useDiagnostics.ts` · the 3-body always-mounted refactor of `StudioBottomPanel` · the routing table (4.1.1) — **4 live rows (`quality-canon` ×2, `quality-promises`, `index_stale`-inert) + the 3 FE-1 rows rendered INERT** · the warnings strip · Lane-B handler | pytest green on the route (incl. **a degraded-source test asserting the key is OMITTED, not `0`**) · vitest green incl. the warnings-strip test · 🔴 **a test asserting the 3 FE-1 rows render with NO chevron and are NOT clickable** (this is the guard against the silent-wrong-target regression) · **live browser smoke (§10)** |
| **M1b** | **FE-1 — the param-blind targets** | `PlanHubPanel` reads `props.params.{focusNodeId,focusArcId}`; `ChapterBrowserPanel` reads `props.params.focusChapterId`; both hoist+reveal (mirror `useQualityCanon`'s `hoist()`) — **only after Book-Package-track handoff (§9)** | the 3 previously-inert rows become clickable; **a Playwright click lands on the focused node/chapter** — not merely on the mounted panel. *Asserting the tab mounted is NOT the assertion; asserting the right row is focused IS.* |
| **M2** | **The find-references lens** | BE-1d route · `EntityReferencesLens.tsx` — **8 rows, one per `REFERENCE_SOURCES` member (§4.2)** · right-click + keyboard affordance on `NodeBadges` cast chips **and** `EntityRefField` · per-source degrade rendering | a per-source error renders **"could not be read"**, asserted — **not `0`** · 🔴 **a test asserting all 8 sources render a row** (the guard against re-collapsing pov/present) · **live browser smoke** |
| **M3** | **Jobs + Generation** | BE-1b (producer `book_id`) · BE-1c (jobs LIST filter) · `JobsTab` + `GenerationTab` over `JobsStreamProvider` · honest stub copy until then | **cross-service ⇒ live-smoke MANDATORY** — a real composition job appears in the tab, book-scoped, on a stack-up |

**M1 and M2 are independently shippable and touch disjoint files.** M3 is independently deferrable —
and if it is deferred, **the stub copy still changes** (M1 ships the honest string).

---

## 10 · Definition of Done

0. 🔴 **NO ROW OPENS A PANEL ONTO NOTHING (FE-1).** Every clickable row's target panel **provably reads
   the focus param that row sends** — asserted by a test, not by inspection. The three param-blind
   targets (`plan-hub` ×2, `chapter-browser`) render **inert** until FE-1 lands. *This is DoD item
   zero because a feed that false-focuses is worse than the stub it replaces: the stub is honest.*
1. **BE-1 route** returns `Diagnostics.ranked()`'s shape + the IF-1/IF-2/IF-3 fields, and the MCP
   tool and the route call **one** `build_diagnostics()`. `grep` proves there is no second fanout.
   `ref_kind` is the **3-member** closed set (`chapter|outline_node|structure_node`) — a test asserts
   no other value is ever emitted.
2. **The degraded path is tested, not assumed:** a test that makes `book_client.list_chapters` raise
   asserts the response has **no `coverage` key** and a `warnings[]` entry — *not* `unplanned: 0`.
3. **The warnings strip is tested:** a diagnostics response with `warnings[]` and `items: []` renders
   the *"N sources could not be read"* copy, **never** *"No issues found"*.
4. **Guard inversion:** `StudioBottomPanel.test.tsx` no longer asserts `bottomStub.jobs` is present
   for a wired tab; it asserts every `BottomTab` has a label key + a body component.
5. **Drift-lock proof:** `contracts/frontend-tools.contract.json` is **byte-identical** to its
   pre-wave state (`git diff --exit-code contracts/frontend-tools.contract.json`), and
   `panelCatalogContract.test.ts` still reports **57 == 57 == 57**.
6. 🔴 **LIVE BROWSER SMOKE (mandatory — this repo's `agent-gui-loop-needs-live-browser-smoke` law).**
   A green unit suite has repeatedly hidden *"the FE could not actually execute it"* — spec 24's own
   named pillar-DoD (H8.2) was skipped this way, with a curl smoke standing in for a browser. **Not
   again.** Playwright, against the **baked nginx build on :5174 or `vite dev` :5199** (a host vite
   SHADOWS the baked image — `frontend-5174-is-baked-prod-nginx-not-vite`), with the
   `claude-test@loreweave.dev` account:
   - open the Studio on a book with a **known-seeded** canon-rule violation
   - toggle the bottom panel → **Issues** → assert ≥1 row with severity `error`
   - **click the `broken_canon_rule` row** → assert the `quality-canon` dock tab mounts **and the
     focused rule is hoisted to the top** (`useQualityCanon.ts:107`). *This is the assertion that
     proves IF-2 is actually fixed — the unit test cannot see it, because the unit test does not
     know the payload dropped `rule_id`.*
   - 🔴 **assert the 3 FE-1 rows are INERT** — no chevron, `click()` mounts **no** dock tab. *Asserting
     the good row works does NOT prove the bad rows are safe. The failure this smoke exists to catch
     is a `plan-hub` tab that opens onto an unfocused tree and reads as success.*
   - right-click a cast badge on `plan-hub` → assert the lens opens with **all 8 source rows present**
     and a **non-zero exact count** (a 6-row lens is the §4.2 regression).
   - screenshot both.
   Drive dockview via `evaluate` + `data-testid` (refs go stale — `playwright-live-dockview-automation-recipe`).
7. **SESSION_HANDOFF** updated; `D-QUALITY-*` rows this spec touches are reconciled; the AN-12
   amendment is committed **in spec 28**, not here.

---

## 11 · Open questions / Deferred

| # | Question | Status |
|---|---|---|
| **OQ-1** | **How does the AGENT show a human the Issues feed?** `ui_open_studio_panel` takes a bare dockview id; the bottom panel is not a dockview panel, and adding `"issues"` to the enum **reds the catalog contract by construction** (§6). **Recommendation: do NOT.** The agent already has `composition_diagnostics` and can *state* the findings. If a "show me" affordance is ever wanted, it is a **distinct frontend tool** (`ui_toggle_bottom_panel {tab: enum}`), which is a Frontend-Tool-Contract change (schema + `CLOSED_SET_ARGS` + regen + both resolvers) and belongs with **X-5/X-12's decision surface in Wave 0**, not here. | **DEFERRED — gate #1 (out of scope: it is X-5's decision surface).** |
| **OQ-2** | ~~Does `plan-hub` accept `focusNodeId` / `focusArcId` today?~~ **RESOLVED — VERIFIED, and the answer is NO.** `grep -rn "focusNodeId\|focusArcId" frontend/src` → **zero hits repo-wide.** `PlanHubPanel.tsx:39` and `ChapterBrowserPanel.tsx:23` both call `useStudioPanel(id, props.api)` and **never read `props.params`**. The old claim that *"`useStudioPanel` exposes `params`"* was **FALSE** — it returns the localized **label** (`useStudioPanel(panelId, api, extras?) -> string`); params arrive only as the dockview prop `props.params`. ⇒ **3 of the 7 routing rows were specced to silently open a panel onto nothing.** | ✅ **CLOSED → became FE-1** (§4.1.1 + §5). The 3 rows ship **INERT** in M1 (IF-4 case 2) and light up in M1b. |
| **OQ-5** | 🔴 **X-13 (`consumer_capabilities` + `contributeContext()`) — plan 30 §8.2 deadlines it "Wave 0 stretch, **or Wave 7 at the latest**." Wave 7 is THIS spec, and it was not carried.** Both fields are declared and read by **nothing** (`chat-service/app/models.py:502`; `studio/host/types.ts:31`) — the *stored-but-unread ⇒ write-only-behavior* class CLAUDE.md bans, and §8.2 calls them "load-bearing for this batch". **They are NOT load-bearing for THIS wave specifically** (this spec adds zero frontend tools, zero panel ids, and zero `contributeContext` consumers — see §6), so folding them in here would be scope-creep onto an unrelated file (`chat-service`, mid-edit by Track C — §9). **Recommendation: re-home X-13 to the X-5/X-12 decision surface** (the same `frontend_tools.py` + contract-regen blast radius) and say so in plan 30, rather than letting a Wave-7 deadline lapse silently. | 🔴 **ESCALATE AT CLARIFY — PO must re-home it or explicitly accept it into this wave.** Do **not** let it fall off the plan by omission; that is how a "load-bearing" item becomes an orphan. |
| **OQ-3** | Should the Issues feed be **book-wide or scoped to the open chapter**? Book-wide (as specced) matches `composition_diagnostics`. A chapter filter is cheap (`chapter_id` is on most rows after BE-1a) but risks the user believing a clean chapter means a clean book. **Recommendation: book-wide only in v1**, with the chapter shown per row. | **OPEN — PO to confirm at CLARIFY.** |
| **OQ-4** | `index_stale` has **no owning panel** and self-heals via the sweeper. Should it be in the feed at all, or is it noise that trains users to ignore warns? **Recommendation: keep it, `warn`, inert (IF-4)** — it explains why a conformance number may lag, which is otherwise mysterious. | **OPEN.** |
| **D-1** | `composition_package_tree` gets no human surface (**IF-5**, §7.2). Recorded as a **conscious won't-fix** (defer gate #5) so it stops re-surfacing as a "gap". | **WON'T-FIX — recorded.** |
| **D-2** | The `severity`/`kind` query filters (BE-1) could equally be client-side over the capped rows. They are **server-side** because `counts` must stay exact and the cap must apply *after* the filter, or a filtered view silently truncates differently from the unfiltered one. Recorded so a later agent does not "simplify" it into a bug. | **DECIDED — do not simplify.** |
| **D-3** | The **3 live 404s** (`/actions/conformance_run/estimate`, `/confirm`, `regenerate-to-beat` — plan 30 §3.3) are **Wave 3's** (G-CONFORMANCE-TRACE). This spec's Run-conformance button uses the **generic** spine and is therefore correct **today**, but it will sit next to a broken button in `motif/api.ts` until Wave 3 lands. Do not "align" with the broken one. | **OUT OF SCOPE — Wave 3.** |
