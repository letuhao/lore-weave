# Writing Studio — Completeness Audit (convergence node)

> **Run:** 2026-07-17, after all 8 sessions closed. **Method:** verify every claim against CODE, never
> against prose. The sessions' own registers are self-report; this audit exists because
> `debt-batches-list-is-stale-verify-first` says a debt list overstates real debt by ~40-50% — and it did.
> **Audited against:** the §2 production-ready bar in
> [`2026-07-16-studio-completeness-8-session-orchestration.md`](2026-07-16-studio-completeness-8-session-orchestration.md)
> and its §6 convergence node.
>
> **Status:** ROUNDS 1–5. Rounds 1–4 walked every §2 axis, every plan-30 gap row, every legacy sub-tab and
> all 88 catalog panels. **Round 5 then re-derived the MAP itself — and found plan 30 has a hole** (an
> entire agent-only triage domain it never names, 18 tools it never counted, and 4 more composition
> holes). **ALL 142 tools are now re-derived — the audit is COMPLETE in breadth.** What remains: BUILD
> (A-3..A-13) + 7 PO decisions + the loop-③ smoke — which is the BEHAVIOURAL audit this static one
> cannot perform.
>
> **Depth of this audit — say it plainly:** STATIC. It proves "a button has no handler", "a panel does not
> mount the component", "an api function has no caller", "a route does not exist". It does NOT prove
> "clicking works", "the write persists", "the deep-link opens". Bar axes #1/#6/#7 are only reachable by
> running the app — the loop-③ smoke is that audit, and it is still owed.

---

## ⚠️ Framing correction (PO, 2026-07-17) — parity ≠ completeness

Rounds 1–5 audited the WRONG question. Plan 30 (and this audit through round 5) asks *"has each legacy
capability been ported to the Studio?"* But **the legacy code is itself incomplete**, so wiring it to the
new Studio moves an incomplete feature to a new address — it solves nothing. Proven on the backend, not
from docs:

- **references** — routes are `GET` · `POST` · `DELETE`. **No `UPDATE`.** Fixing a typo means delete +
  re-add, which **re-embeds**. Porting `ReferencesPanel` faithfully ports a corpus you cannot edit.
- **derivative (dị bản)** — `POST /derive` + `GET /derivative-context`. **No `UPDATE`, no `DELETE`, no
  LIST-of-a-book's-derivatives.** It is create-once/read-one, not CRUD.
- **structure_template** — the repo has `list_for_user` + `get` and **no create/insert/update/delete on
  ANY transport**. The "user-custom" tier the table advertises **cannot be inserted by any code**.

⇒ **Round 6 changes the question.** For every authorable domain, audit CRUD-completeness at the layer that
matters — **BE route + MCP tool + FE** — and record which verb is missing at which layer. That, not
"ported y/n", is the input to the detail-level build specs. A missing `UPDATE` route is a BUILD task, not a
port task; the old plan mislabelled several as ports.

## Verdict (rounds 1–5, parity lens)

The 8-session build is **substantially complete for what it was scoped to do** (port legacy → Studio): every
mechanical gate is green, and every "still open" debt row I could test turned out to be already built. The
parity gaps are in what the plan never assigned. **But parity was the wrong bar** — see round 6 for the
completeness gaps that porting cannot fix.

---

## Round 1 — mechanical gates (objective, no self-report)

| Bar axis | Gate | Result |
|---|---|---|
| #3 Reachable | `panelCatalogContract` (enum == openable == contract, CATEGORY_ORDER, guideBodyKey) | ✅ 9 tests green |
| #3 Reachable | `legacyParityContract` (25 legacy sub-tabs each homed or retired) | ✅ 3 green — **but see F-2: it was lying** |
| #5 Agent parity | Lane-B handlers registered + actually CALLED in `registerAllStudioEffectHandlers()` | ✅ 12 domains, incl. `motifEffects`/`conformanceEffects` that S4's note still called PENDING |
| #8 i18n | `scripts/i18n-completeness-gate.py` | ✅ 17 locales × 33 namespaces at full `en` parity (the bar's "18 locales" = 17 + `en`; no discrepancy) |
| — Full gate | every service suite in the repo | ✅ green (see the sweep in SESSION_HANDOFF) |
| — Full gate | `ai-provider-gate` | ✅ OK |

## Round 1 — session debt registers, verified against code

**Rows claiming "open" that are in fact BUILT** (stale — the accounting artifact lagged the work):

| Row | Reality |
|---|---|
| S4 `D-MOTIF-GRAPH-CANVAS` — "SPEC READY (XL)" | **BUILT**: `motif-graph` in catalog + `MotifGraphPanel` + `motif_graph_layout` table + 3 commits incl. a `/review-impl` fix (`b260d4e50`) |
| S4 `D-ARC-TEMPLATE-DRIFT-VIEW` — "SPEC READY (S)" | **BUILT**: `ArcTemplateDriftView.tsx` (its header: "replacing the raw `<pre>` JSON dump"), mounted in `ArcTemplatesPanel` |
| S2 `B2d` book-tier arc templates | **BUILT**: `book_id` + `book_shared` present in the repo/service |
| S3 `D-PLANFORGE-PROPOSE-BLIND` | gather lens present in `plan_forge_service.py` |

**Rows genuinely closed:** S1 (zero open), S6 (all cleared but `kind` — verified write-only, won't-fix),
S7 (all cleared/dispositioned), S8 (empty).

**Rows genuinely still open:** see the findings below.

---

## FINDINGS

### F-1 · `style-voice` + `reference-shelf` have NO studio home and NO owner — 🔴 the biggest gap

`StyleVoicePanel` and `ReferencesPanel` are **real, live capabilities** (mounted at
`CompositionPanel.tsx` slots `style` / `references`). They are reachable **only** from the legacy
`ChapterEditorPage`. And they appear:

- in `legacyParityContract` as `unported` ("pending Wave 6 M1/M2"),
- **nowhere** in the 8-session orchestration plan,
- in **no** session's RUN-STATE.

⇒ The completeness plan never assigned them. Consequences: a Studio-only author cannot reach them
(fails bar #3), and **GG-4 retirement would DELETE two working capabilities**.

**Disposition:** PORT (the S6 shape — catalog row + panel_id enum + contract + i18n `guideBodyKey` +
CATEGORY_ORDER + Lane-B if it writes). Status: in progress.

### F-2 · The legacy-parity inventory understated readiness, invisibly — ✅ FIXED (`e06b4b70e`)

`motifs` and `conformance` still read *"pending Wave 3 — panel not yet in this branch catalog"* while
S4 had shipped **both**. The file's own instruction ("when the wave lands, flip each back to its
bare-string home") was never followed. The contract stayed **green either way**, because an `unported`
row only needs a >20-char reason — so the artifact that **GG-4 retirement reads** was wrong and nothing
could catch it.

Flipped to real homes, which also gives the rows teeth (they now assert the panel EXISTS). Verified
faithful, not merely id-exists: the legacy `motifs` sub-tab mounts `MotifSimpleModeProvider` +
`MotifLibraryView` and `MotifLibraryPanel` mounts the **same two**; legacy `conformance` mounts
`ConformanceTraceView` and `QualityConformancePanel` wraps the **same view**.

*(This is the `completeness-audit-gap-hides-in-the-accounting-artifact` lesson, again.)*

### F-3 · A 502 rendered nginx's HTML page at the author — ✅ FIXED (`e06b4b70e`)

S2 hit this live and routed it to "not S2's"; **nobody owned it**. Root cause was in `apiJson`, not the
reader: a non-JSON body became `{code:'PARSE_ERROR', message: text}`, so the raw page landed on **both**
`Error.message` and `body.message` — and `readBackendError` feeds those to the **global**
`MutationCache.onError` toast, i.e. **every panel in the studio**.

The naive fix (never trust a non-JSON body) would have **regressed 24 real messages**: Go's
`http.Error(w, "database unavailable", 503)` writes text/plain. So `isPlainTextMessage` discriminates —
short + no markup ⇒ a sentence, still surfaced; markup or too long ⇒ an infra page, suppressed to the
status line, raw kept on `rawBody` for debugging.

**Bonus silent-failure hole closed while fixing it:** `res.statusText` is **empty over HTTP/2**, so it
could not be the last resort — behind an HTTP/2 LB the throw was `Error('')` ⇒ a **blank toast**. Now
falls back to `HTTP <status>`. All four paths test-locked.

### F-4 · The FE↔BE entity-kind cross-language lock caught a real move — ✅ (working as designed)

`entityKinds.test.ts` parses `entities.py` to lock the FE picker vocabulary to the server gate. It
**failed** when `AUTHORABLE_KINDS` moved to derive from the new `AuthorableKind` Literal (done so the
FastMCP signature could reuse the type and finally advertise `kind` as a real **enum** instead of prose —
see the sweep commit `bf29e70b5`). Updated to read the Literal, and it now also asserts the tuple still
derives from it. **Not a defect — the guard doing its job.**

---

## Round 2 — plan 30's §5 gap register, verified panel-by-panel

**18 of the 20 proposed panel ids ARE in the catalog.** The two that are not are exactly F-1's:
`style-voice`, `reference-shelf`. The non-panel gaps:

| Gap | Proposed surface | State |
|---|---|---|
| G-MOTIF-SUGGEST | 2 suggest buttons | ✅ built |
| G-STORY-STRUCTURE | decompose action in `plan-hub` | ✅ built |
| G-KG-WRITE-HOLES | 4 affordances, no new panel | ✅ built (`createEntity` has FE consumers) |
| G-IMPORT-DECONSTRUCT | 拆文 section inside `arc-templates` | ✅ built + MOUNTED (`ImportDeconstructSection` in `ArcTemplatesPanel`) |
| **G-DIAGNOSTICS-ISSUES** | wire the existing Issues tab + `GET /books/{bid}/diagnostics` | 🔴 **NOT built — see F-5** |
| **G-WORK-SETTINGS** | a Composition section in `book-settings` | 🔴 **NOT built — see F-6** |
| **G-WORKFLOWS** | `workflows` + `workflow-proposals` panels | 🔴 not built (plan 30 flags it as colliding with Track C's P-5 — needs a PO call on ownership, not a build decision) |

### F-5 · The whole `StudioBottomPanel` is a stub, and G-DIAGNOSTICS-ISSUES is PO-approved + orphaned — 🔴 OPEN

`StudioBottomPanel` renders **all three** tabs (`jobs` · `generation` · `issues`) as one string:
`'Feed appears here once wired.'` It is **reachable** — the status bar has a toggle and the Command
Palette has a `toggleBottom` command — so an author opens it and finds **three dead tabs**. That is
precisely the *"cho có"* failure the §2 bar names (fails #1 Operable and #2 no-dead-buttons).

`GET /v1/composition/books/{bid}/diagnostics` does not exist (grep of the composition routers → 0).
So *"what is wrong with my book"* — which plan 30 calls **the highest-value read in the product** —
still answers only to an LLM.

**The PO already approved this**: decision **PO-1** amends spec 28's AN-12 explicitly for
`composition_diagnostics` / `package_tree` / `find_references`, concluding *"Wave 7 proceeds"*. Yet
the gap appears in **no session's charter and no RUN-STATE**. Orphaned, exactly like F-1.

### F-6 · The retirement inventory contains FALSE homes — 🔴 the most dangerous finding

`legacyParityContract` is, by its own docstring, *"the only mechanical guard that Wave 6 does not
delete a live capability by mapping it to a panel that was never built."* But its test only asserts
**the panel id exists in the catalog** — never that the panel *carries the capability*. So a row can
name a real panel that does something else entirely, and the guard goes green while GG-4 deletes the
feature.

Verified by mapping each legacy `DockSlot` to the component it renders, then checking the homed
panel's subtree for that capability:

| legacy tab | renders | contract says home is | reality |
|---|---|---|---|
| `settings` | `CompositionSettingsView` | `book-settings` | 🔴 **FALSE.** `BookSettingsPanel` wraps `SettingsTab` (book info/cover/genre/world). `CompositionSettingsView` (model refs, `capture_correction_prose`, `critic_model_ref`, `reference_embed_model_ref`) is mounted **only** in the legacy `CompositionPanel`. Retirement DELETES it. This is also G-WORK-SETTINGS. |
| `beats` | `BeatSheetView` | `plan-hub` | 🔴 **FALSE.** `BeatSheetView` = drag a node onto a beat card to assign `beat_role`. `PlanHubPanel` contains **zero** `beat` references. The "Wave 6 M4a (drawer facet)" the comment claims was never built. |
| `cast` | `CastCodexPanel` | `kg-entities` | 🟠 **WRONG (not lost).** S7 shipped a dedicated **`cast`** panel that mounts `CastCodexPanel`. The capability IS homed — the inventory just names the wrong panel. |
| `arc` | `CharacterArcView` | `kg-timeline` | 🟠 **WRONG (not lost).** S7 shipped **`character-arc`** (`CharacterArcPanel` mounts `CharacterArcView`). |
| `timeline` | `TimelineView` | `kg-timeline` | 🟠 **PARTIAL.** `KgTimelinePanel` mounts knowledge's `TimelineTab`, which has **no spoiler support**. Composition's `TimelineView` is the *spoiler-safe* chronology with the "AI sees ≤ here" cutoff marker — a load-bearing authoring feature that the home does not carry. |

Legitimate supersedes (checked, NOT defects): `graph → plan-hub` (plan-hub *is* the graph canvas),
`quality → quality` (`QualityHubPanel` deliberately never mounts `QualityPanel` whole — F-Q11),
`relmap → kg-graph` (`ProjectGraphView` *generalizes* `RelationshipMap` and reuses
`useRelationshipMap`).

**Root cause is structural, not clerical:** id-existence ≠ capability-homed. The fix is to give the
contract teeth — encode the capability per row and assert the home panel actually carries it (or
declares a reasoned supersede). See "Actions".

---

## Round 3 — sweeping ALL 88 panels + the studio chrome for "cho có" surfaces

Method: grep the whole `features/studio` tree for stub markers (`once wired`, `Coming soon`,
`Built next.`, TODO, noop handlers), then verify each hit against what actually exists.

### F-7 · Two of the studio's FIVE top-level views are dead — and one of them is fully built 🔴

`ACTIVITY_VIEWS = ['manuscript', 'plan', 'bible', 'search', 'quality']` — the VS-Code-style activity
bar, the studio's primary navigation. `StudioActivityBar` renders **all five** as clickable buttons.
`StudioSideBar` only implements two navigators (`manuscript`, `plan`); the rest fall to a stub that
renders `navStub.<view>.body`. That copy is shipped **and translated into all 17 locales**:

| View | What the author is told | What actually exists |
|---|---|---|
| `bible` | *"Cast, world & canon entries. **Coming soon.**"* | 🔴 **13 storyBible panels ship**: glossary, glossary-ontology, glossary-unknown, glossary-ai-suggestions, glossary-merge-candidates, wiki, arc-templates, motif-library, motif-graph, world-map, place-graph, cast, character-arc |
| `quality` | *"Critic scores, promise threads & canon issues. **Coming soon.**"* | 🟠 **9 quality panels ship.** The rail does offer ONE honest affordance (a button that opens the `quality` hub), but still leads with "Coming soon" |
| `search` | *"Full-text & semantic search across the book. **Coming soon.**"* | ⚪ **True** — no search panel exists anywhere in the catalog. A genuinely unbuilt feature |

**Severity.** The author clicks the Story Bible icon — the entry point to their whole cast, world,
glossary, wiki and motif library — and is told the feature is *coming soon*, while 13 panels sit
built, tested, i18n'd and palette-reachable. This is `built-mounted-unreachable-duplicated-nav-list`
at the **top level of the product**. Bar #3 (reachable) is technically satisfied via the Command
Palette, which is exactly why no gate caught it: *reachable-by-palette* is not *discoverable*, and
the primary nav actively tells the author the opposite of the truth.

**Disposition:** `bible` + `quality` are pure FE wiring over panels that already exist (a rail that
lists its category's panels — the data is in `catalog.ts`, `PANELS_BY_CATEGORY` already groups it).
`search` is a real unbuilt feature and a scope decision for the PO — it is NOT in plan 30's gap
register either.

### F-8 · The "kg-overview 3-noop-buttons" bug the §2 bar CITES was still live — ✅ FIXED (`e51593f8f`)

The bar names this bug as its canonical dead-button example. It survived all 8 sessions.
`ProjectRow` REQUIRED `onArchive`/`onRestore`/`onDelete` and rendered their buttons
unconditionally, so `OverviewSection` — where the recorded decision is that destructive CRUD belongs
with the projects LIST — satisfied the types with `noop`. In the `kg-overview` panel the author saw
a live Archive icon and a live Delete icon that did **nothing** on click: no dialog, no toast, no
error. Bar #2 and #4, both violated.

Fixed by expressing the intent in the types (the trio is optional; a button renders only when
handled — the same `onOpen?`/`onExploreGraph?` idiom this file already documents). **Why no test
caught it:** `OverviewSection`'s suite stubs `ProjectRow` out entirely, so nothing ever rendered the
real buttons. Added a guard on the real component, proven both ways (re-injecting the old render
REDs it; the handled case still shows the buttons, so it cannot pass by rendering nothing).

### F-9 · A 4th dead button — `[[` autocomplete's "+ Create new", in the studio's main editor — ✅ FIXED

`GlossaryAutocomplete` renders a primary-coloured, `cursor-pointer hover:underline` **"+ Create
new"** action at the foot of every `[[` popup. **Both** consumers — `EditorPanel` (the studio's
manuscript editor) and the legacy `ChapterEditorPage` — passed `onCreateNew={() => {}}`. Clicking it
closed the popup and did nothing. It has **never worked anywhere**: the component advertises a
capability no consumer ever implemented.

Made optional + hidden when unhandled (same pattern as F-8). **The capability itself is a real,
unbuilt gap** — "type `[[NewCharacter` → create it" is a natural authoring flow, is in no session
charter and in no plan-30 row. Recorded here for the PO; hiding the lie is the honest interim state.

---

## Actions

| # | Action | State |
|---|---|---|
| A-1 | Strengthen `legacyParityContract`: assert the CAPABILITY, not the id (`carries` / `supersedes+why` / `retired` / `unported`) | TODO |
| A-2 | Correct the 3 wrong/partial homes it exposes (`cast`→`cast`, `arc`→`character-arc`, `timeline`) | TODO |
| A-3 | F-1: port `style-voice` + `reference-shelf` (GG-8 shape) | TODO |
| A-4 | F-6: home `CompositionSettingsView` (G-WORK-SETTINGS) — else GG-4 deletes it | TODO |
| A-5 | F-6: home the `beats` capability (`BeatSheetView`) — else GG-4 deletes it | TODO |
| A-6 | F-5: wire the Issues tab + `GET /books/{bid}/diagnostics` (PO-1 already approved) | TODO |
| A-7 | G-WORKFLOWS: PO call on Track C ownership — not a build decision | ASK PO |

---

## Round 4 — the §2 bar, all nine axes swept

| # | Axis | Method | Result |
|---|---|---|---|
| 1 | Operable | grep every stub marker across `features/studio` | 🔴 **F-5** (bottom panel), **F-7** (2 dead views) |
| 2 | CRUD / no dead buttons | grep every `on*={noop / () => {}}` across studio + composition + knowledge | 🔴 **F-8**, **F-9** — both FIXED |
| 3 | Reachable | `panelCatalogContract` + the plan-30 panel list vs `catalog.ts` | 🔴 **F-1** (2 panels absent), **F-7** (nav says "Coming soon" over 13 built panels) |
| 4 | No silent failure | the shared error path + the dead handlers above | 🔴 **F-3** — FIXED |
| 5 | Agent parity | Lane-B handlers registered AND called | ✅ 12 domains wired in `registerAllStudioEffectHandlers()` |
| 6 | Loop-connected | deep-links between adjacent tools | ⚪ not mechanically sweepable — covered by the loop-③ smoke, still to run |
| 7 | **Proven** | every catalog component vs the test corpus | ✅ 6 panels have no test naming the WRAPPER, but all 6 have unit tests on their inner view **and** e2e specs — the legitimate DOCK-2 pattern, not a gap |
| 8 | i18n | `i18n-completeness-gate.py` | ✅ 17 locales × 33 namespaces at full `en` parity |
| 9 | Scale | caps / paging / virtualization | ✅ 38 files carry a cap or paging (cast offset-paging, arc-template 200 cap, scene-graph virtualize, relmap 60-node cap, subgraph 250) |

**Coverage of this audit:** 9/9 bar axes · 22/22 plan-30 gap rows · 25/25 legacy sub-tabs · 88/88
catalog panels · 8/8 session registers.

---

## Round 5 — the map itself: re-deriving tool→GUI parity from scratch 🔴 **the map had a hole**

Rounds 1–4 verified plan 30's rows. But **nobody had verified that plan 30's map is COMPLETE** — and plan
30 itself warns you not to assume so: it calls its own scoreboard *"a floor, not a total. Real total ≥
189"*, and one of its rows is labelled *"G-POLISH-SELFHEAL (NEW — found by the completeness critic; **in
no original gap**)"*. A map that already lost one feature can lose more.

So the inventory was re-derived from the service registries (142 tools: composition 87 · knowledge 37 ·
translation 12 · jobs 5 · lore-enrichment 1) and each tool traced **tool → REST route → FE caller → is
that component mounted in a registered panel**. Three agents, one per disjoint service corpus.

⚠️ **Method note — a name-match sweep does NOT work here and was thrown away.** Matching camelCased tool
names against the FE reported 78 "no GUI" tools; spot-checking killed it (`composition_canon_rule_create`
was flagged, but the FE has `compositionApi.createCanonRule` — the FE names verbs **verb-first**, tools are
**noun-first**). Only capability-level tracing is sound. Every claim below was re-verified by hand.

### F-10 · The whole KG **triage** queue has no GUI — and plan 30 never mentions it 🔴 (correction below)

> **⚠️ Correction (round 6): this is an FE gap, NOT a backend gap.** The round-6 knowledge sweep verified
> that `app/routers/public/triage.py` is a **full public JWT router** (list/resolve/dismiss), mounted at
> `main.py:784` — the backend is complete. My "agent can fill an inbox the human can never open" framing
> was imprecise: the human *route* exists; only the FE *caller* is missing. This makes it an **XS wire-up**
> (call an existing route), not a build. The finding stands — the triage queue is unreachable in the GUI —
> but its size and layer were wrong.

Extraction parks every off-schema element in a triage queue, and `kg_propose_edge` writes *into* it. Four
tools operate it — `kg_triage_list` · `kg_triage_resolve` · `kg_triage_place_edge` · `kg_triage_schema_write`.
The routes are **public and complete**; the FE functions exist with **zero callers** — the exact
`createEntity`-with-no-callers shape this repo has shipped before.

| Verified | |
|---|---|
| `listTriage` / `resolveTriage` / `dismissTriageItem` defined in `features/knowledge/api/ontology.ts` | **3 present** |
| their callers (excluding tests) | **0 / 0** |
| occurrences of "triage" in plan 30 | **0** |

`kg-proposals` is **not** the missing panel: `KgProposalsPanel` mounts `ProposalsInboxTab`, whose sources
(`lib/proposalsInbox.ts`) are `glossaryApi`/`wikiApi`/`enrichmentApi` only.

### F-11 · A human cannot author, or forget, a fact 🔴

- `memory_remember` / `kg_propose_fact` — **no POST route for a fact at all**; `_handle_memory_remember`
  calls `merge_fact` directly. `pending_facts.py` exposes only `GET ""` + `confirm` + `reject`, so the human
  is confined to judging what the agent proposed.
- `memory_forget` — no public route; `invalidate_fact`'s only caller in the entire service is the MCP
  executor (`app/tools/executor.py`).

Plan 30 caught `memory_forget` (under G-KG-WRITE-HOLES) but **not** the authoring half.

### F-12 · Views are authorable but not applicable — a lens you cannot look through 🔴 (FE gap, corrected)

> **⚠️ Correction (round 6): FE gap, not backend.** `GET /v1/kg/projects/{id}/graph?view=&as_of_chapter=`
> (`graph_views.py:597`) is a **public, browser-reachable reader** that applies the lens — the backend is
> complete. The gap is only that `KgGraphPanel`'s `ProjectGraphView` calls a *different* endpoint
> (`/subgraph`, params `center`/`hops`/`limit`) instead of this one. So it is an **S FE swap** (point the
> panel at the view-aware reader), not a backend build. The finding stands; the layer/size were wrong.

`kg_view_upsert`/`delete`/`read` are fully GUI (`ViewBuilder` ← `KgSchemaPanel`). The reader that applies a
view + `as_of_chapter` exists and is public — but has **zero FE callers**. **A human can build a saved lens
and then never apply it, and cannot view the graph as-of a chapter.** In no plan-30 row.

### F-13 · `kg_project_entities_to_nodes` is MCP-only (plan 30 caught this one)

The glossary→graph projection that seeds an empty graph — the prose-less path that unblocks
`kg_propose_edge` — has no route and no button. Engine at `app/extraction/anchor_loader.py`, exposed only
at `app/mcp/server.py`.

### F-14 · translation: job **control** is missing from the translation surface 🟠

All 12 translation tools + all 5 jobs tools + the 1 lore tool have a mounted human path — **no agent-only
writes**. One asymmetry: `translation_job_control` (cancel/pause/resume/retry) is `/internal`-token-gated,
so the only human path is the generic `jobs-list` panel — the author must leave translation and guess which
row is theirs. `translationApi.cancelJob` / `getJob` / `listJobs` are **dead code, zero callers** (verified).
The code already admits it: `studio/agent/handlers/translationEffects.ts` calls translation's cancel/pause
*"the one real gap"*.

**Inverse gap (agent-side, not GUI-side):** the GUI exposes job `resume` + `retry`, and **no MCP tool
covers them**.

### F-16 · The plan's OWN worked example of a cross-session handoff silently never happened 🔴

The orchestration plan's §5 coordination rules use this as their model case, verbatim:

> *"`PlanDrawer.tsx` → **S2 owns the file.** S4 builds `MotifBindingLens.tsx` (S4's file); **S2 mounts
> `<MotifBindingLens nodeId={…}/>` with a one-line import.** S4 never edits `PlanDrawer.tsx`."*

**S4 built it. S2 never mounted it.** `MotifBindingLens.tsx` exists with **zero importers** (verified),
so `composition_motif_bind`/`unbind` — per-scene motif binding — remains reachable **only from the legacy
page** (`useMotifBinding` → `ChapterMotifBindings` → `PlannerView` → `CompositionPanel` →
`ChapterEditorPage`). GG-4 would delete it.

**Nobody was wrong by their own charter, and no gate could catch it.** S4's component has its own tests
and passes; S2's `PlanDrawer.tsx` is untouched and passes. A handoff that spans two owners is invisible to
per-owner tests — which is exactly the risk §5 was written to manage, and it still landed.

*(Cost note, since the plan called it "a one-line import": it isn't quite. `PlanDrawerProps` carries
`bookId` but not `projectId`/`chapterId`, which `MotifBindingLens` needs — so the mount also threads two
props. Small, but not one line.)*

### F-17 · composition: 4 more agent-only capabilities plan 30 never names

Re-derived: **87 tools** (plan 30 says 75) — **76 GUI · 4 agent-only · 3 agent-native reads · 2 legacy
proxies**. The composition surface is in far better shape than its scoreboard suggests, but four holes are
real and none appear in any plan-30 row:

| Capability | State |
|---|---|
| `composition_decompile_arcs` | 🔴 **Agent-only write.** "Group my flat/imported book's chapters into arcs" — deterministic, $0, confirm-gated. No FE at all. (`materializeScenes` in plan-hub is a DIFFERENT capability: scenes-from-chapters.) |
| `composition_arc_extract_template` | 🔴 **Agent-only write.** "Save my authored arc as a reusable template" — the **extract** half of the apply↔extract round trip. `composition_arc_apply` IS GUI-reachable, so the pair is asymmetric. `grep extract-template frontend/src` → **0**. |
| `composition_arc_suggest` | 🟡 **Agent-only read.** `grep arc-templates/suggest frontend/src` → **0**. The route's own header says it is *"the REST twin of `composition_arc_suggest` … so it is a route, not a bridge entry"* — built for an FE that was never written. |
| `composition_motif_bind`/`unbind` | 🟠 **Legacy-only** — see F-16. |

**Also closed by the sessions (plan 30 is stale here):** `G-ARC-SPEC-CRUD` claimed all 5 arc CRUD tools had
NO FE consumer — `useArcInspector.ts` now calls all five and `arc-inspector` is registered.
**Confirmed still true:** `G-STYLE-VOICE`'s inverse gap — `grep "composition_style_|composition_voice_"` in
server.py → **0 tools**, while 6 style/voice REST routes exist and only the legacy page consumes them. So
style/voice is invisible to the agent AND (per F-1) to the Studio user. Both halves missing.

### F-15 · plan 30's own scoreboard is provably incomplete — and one of its rows is stale

- It contains **zero** occurrences of `translation-service`, `jobs-service`, `lore-enrichment` — those **18
  tools were never on its scoreboard at all**. Its §3.4 names only provider-registry (14) + catalog (2) as
  uncounted, concluding *"Real total ≥ 189"*; the floor is really **≥ 207**.
- It contains **zero** occurrences of `triage`, `memory_remember`, `kg_multi_query`, `lore_` — F-10/F-11/F-12
  are outside its map.
- **Stale row:** G-KG-WRITE-HOLES asserts *"No Create anywhere (`grep createEntity` across
  `features/knowledge/**` → EMPTY)"*. **False at HEAD** — `useEntityMutations.ts` calls
  `knowledgeApi.createEntity`, surfaced by `CreateEntityDialog`, mounted in `EntitiesTab` (`kg-entities`)
  **and** `CastPanel` (`cast`). S7 built it.
- Its `target_language` free-string Frontend-Tool-Contract flag is **also stale** — both
  `translation_update_settings` and `translation_start_job` now type it as a closed-set `TargetLangCode`
  Literal with a server-side re-check.

**Dead code surfaced along the way:** `useResolvedSchema.ts` (zero importers), `ontologyApi.updateView`
(zero callers, `upsertView` won).

---

## Round 6 — CRUD-completeness at the BACKEND (the real build-spec input) 🔴

The question rounds 1–5 should have asked. For each authorable domain: which CRUD verb is missing, **at
which layer** (repo / route / MCP)? A missing repo method is a data-model gap (M); a missing route over an
existing method is a wire-up (XS–S). Every row below was re-verified against the repos by hand after the
agents returned — the two corrections to F-10/F-12 above came out of exactly this cross-check (both were FE
gaps I'd mislabelled as backend).

**The pattern that emerged: this is NOT "port the legacy code". Several domains are missing a verb at the
DATA layer, so no port could ever add it.** Grouped by fix shape:

### 6.1 · Missing at the REPO/DATA layer — a real BUILD, not a port

| Domain | Missing | Evidence | Consequence | Size |
|---|---|---|---|---|
| **structure_template** | Create · Update · Delete — **the entire write side** | `structure_templates.py` has ONLY `list_for_user`+`get`; the sole `INSERT` is the built-in seed at `migrate.py:1985` (`owner_user_id NULL`) | The schema fully provisions a per-user tier (`owner_user_id` col + index + the SELECT filters on it) but **no code can insert one** — the advertised "user-custom story structure" tier is dead. Only the 6 seeds are ever usable. | **M** (repo methods + `UNIQUE(owner_user_id,name)` tenancy + route + MCP) |
| **references** | Update | `ReferencesRepo` = create/list/get/delete/search — no `update` (verified); router GET/POST/DELETE only | Cannot fix a typo in a reference's title/author/url — delete+re-add **re-embeds** the whole content and loses ordering | **S** metadata-only PATCH · **M** if content edits re-embed |
| **derivative deltas** | Update/Delete of `divergence_spec`; add-after/Update/Delete of `entity_override` | `derivatives.py` = create_spec/create_override/get/list only; sole writer is `perform_derive` at derive-time | After creating a dị bản the author can't change its taxonomy/pov/added-rules or edit a per-entity override — the only "edit" is archive-and-re-derive. `DivergenceManagerView` shows deltas it cannot mutate. | **M** |

### 6.2 · Missing at the ROUTE/MCP layer — the repo method EXISTS (wire-up)

| Domain | Missing | Evidence | Fix |
|---|---|---|---|
| **facts (author)** | no public POST-create | `pending_facts.py` = GET/confirm/reject only; `merge_fact`+`PendingFactsRepo.queue` called only from MCP | `POST /v1/knowledge/pending-facts` (or direct `…/facts`) — **S** |
| **facts (invalidate)** | no `/facts/{id}/invalidate` | `invalidate_fact` exists (`facts.py:764`) and IS exposed for relations (`/relations/{id}/invalidate`), just not facts | route over the existing method — **XS** |
| **corrections (list)** | no `GET …/corrections` | `generation_corrections.py:280 list_for_job` defined, **zero callers** | route mirror — **XS** |
| **glossary→graph seed** | `kg_project_entities_to_nodes` MCP-only | no REST twin; `POST /entities` is single-node | `POST …/projects/{id}/entities/from-glossary` — **S** |
| **world rollup `unify`** | REST subgraph takes only `limit` | `unify` (off/by_name/semantic) lives in `kg_world_query`/`kg_multi_query` MCP + `kg_unify.py` | add `unify` param to the REST route — **M** |
| **triage / views (F-10/F-12)** | FE caller only | routes public + complete | wire the panel — **XS–S** |
| **motif RESTORE, arc-template RESTORE** | soft-archive with **no restore** | `motif_repo`/`arc_template_repo`: `archive` present, `restore` absent (verified vs canon/plan/structure/outline which all have it) | `restore` method + route — **S each** |

### 6.3 · Confirmed COMPLETE (no gap — do not spec) & by-design absences

- **Full CRUD:** outline nodes · canon rules · style/voice · arcs · plan runs · motif bindings (fully
  reversible, undo_token round-trips) · projects · schema/ontology · views(backend) · triage(backend).
- **By-design, NOT a gap:** entity hard-delete (soft-archive preserves the glossary anchor) · relation &
  fact in-place UPDATE (bitemporal — correction = invalidate + re-assert) · references restore (hard-delete,
  no calibration history to keep) · import-source update (immutable raw input) · self-heal proposals
  (ephemeral compute; accepted edits persist via prose write) · corrections update/delete (append-only
  preference log).

### 6.4 · Stale flags in plan 30, now disproven by code

- `composition_arc_apply` / `composition_arc_template_drift` were flagged as `_pending_engine` stubs —
  **both are fully wired** now (`apply_arc_to_spec`, `compute_arc_report`). The only live `_pending_engine`
  is dead code (`server.py:5077`, unreachable because `extract_template_from_arc` now exists).
- `G-ARC-SPEC-CRUD` ("all 5 arc CRUD tools NO-FE") — **closed** (`useArcInspector` calls all 5).
- `G-KG-WRITE-HOLES` "grep createEntity → EMPTY" — **false at HEAD**.

*(world / book / glossary domains — the 4th agent — appended below when it lands.)*

---

## What is left, and who must decide

**Buildable now (no decision needed) — the orphans no charter owns:**
- **A-3** port `style-voice` + `reference-shelf` (F-1)
- **A-4** home `CompositionSettingsView` (F-6 / G-WORK-SETTINGS)
- **A-5** home the `beats` capability (F-6)
- **A-6** wire the Issues tab + `GET /books/{bid}/diagnostics` (F-5) — **already PO-approved via PO-1**
- **A-8** give `bible` (and `quality`) a real rail (F-7) — pure FE over 13 + 9 existing panels
- **A-9** (F-10) a **triage panel** — the routes are already public and the FE api functions already exist
  with zero callers, so this is FE wiring. It is the largest single hole the audit found.
- **A-10** (F-12) let `KgGraphPanel` apply a saved `view` + `as_of_chapter` (consume `kg_graph_query`)
- **A-11** (F-14) put job control on the translation surface — or delete the 3 dead `translationApi` fns
- **A-12** (F-16) mount `MotifBindingLens` in `PlanDrawer` — S4 built it, S2 never mounted it; it also
  needs `projectId`/`chapterId` threaded into `PlanDrawerProps`
- **A-13** (F-17) surface `decompile_arcs` + `arc_extract_template` (+ `arc_suggest`) — the extract half of
  apply↔extract is the sharpest asymmetry

**Needs a PO decision:**
| Q | Decision |
|---|---|
| **D-a** | **`search`** (F-7): a whole unbuilt feature, in NO plan-30 row and no charter. Build it, or retire the activity-bar icon? A nav icon that says "Coming soon" is not an option. |
| **D-b** | **`timeline`** (F-6): extend knowledge's `TimelineTab` with the spoiler cutoff, or port composition's `TimelineView` as its own panel? |
| **D-c** | **G-WORKFLOWS**: plan 30 flags a head-on collision with Track C's P-5. Ownership call, not a build call. |
| **D-d** | **`[[`-create** (F-9): build "type `[[NewCharacter` → create it", or leave the affordance hidden? |
| **D-e** | **D-5 mobile-shell** — GG-4 retirement depends on it (per the orchestration plan's §6.3) |
| **D-f** | **F-11 — human fact authoring/forgetting.** Should a human be able to write and retract a KG fact directly, or is "the agent proposes, the human confirms/rejects" the intended product boundary? If the latter, it is a conscious won't-fix and should be recorded as one — not left looking like a hole. |
| **D-g** | **plan 30's scoreboard is a floor, not a total** (F-15). Its 173/23 excludes translation+jobs+lore (18), provider-registry (14) and catalog (2) → the real floor is **≥207**. Do we re-derive the remaining uncounted services (provider-registry, catalog, glossary, book, agent-registry), or declare them out of the Studio's scope? |

**Convergence node, still to run:**
- **#2 the loop-③ Studio-only live smoke** (import → plan → draft → revise → translate → publish on ONE book). Cannot run before A-3..A-6 land.
- **#3 GG-4 retirement** — gated on the **5 unhomed** capabilities (settings · beats · timeline · style · references), NOT on a green test. The inventory now says so mechanically.
- **#4 full gate** — ✅ already green (every service suite + `ai-provider-gate`; see SESSION_HANDOFF).
