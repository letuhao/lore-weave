# Writing Studio — Completeness Audit (convergence node)

> **Run:** 2026-07-17, after all 8 sessions closed. **Method:** verify every claim against CODE, never
> against prose. The sessions' own registers are self-report; this audit exists because
> `debt-batches-list-is-stale-verify-first` says a debt list overstates real debt by ~40-50% — and it did.
> **Audited against:** the §2 production-ready bar in
> [`2026-07-16-studio-completeness-8-session-orchestration.md`](2026-07-16-studio-completeness-8-session-orchestration.md)
> and its §6 convergence node.
>
> **Status:** ROUNDS 1–4 COMPLETE — every §2 axis, every plan-30 gap row, every legacy sub-tab and all
> 88 catalog panels have been walked. What remains is BUILD (A-3..A-8) + 5 PO decisions + the loop-③
> smoke. Update in place as those land.

---

## Verdict so far

The 8-session build is **substantially complete and honest**: every mechanical gate is green, and every
"still open" debt row I could test turned out to be **already built**. The real gaps are NOT in what the
sessions did — they are in what the **plan never assigned** and in what **no session owned**.

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

## What is left, and who must decide

**Buildable now (no decision needed) — the orphans no charter owns:**
- **A-3** port `style-voice` + `reference-shelf` (F-1)
- **A-4** home `CompositionSettingsView` (F-6 / G-WORK-SETTINGS)
- **A-5** home the `beats` capability (F-6)
- **A-6** wire the Issues tab + `GET /books/{bid}/diagnostics` (F-5) — **already PO-approved via PO-1**
- **A-8** give `bible` (and `quality`) a real rail (F-7) — pure FE over 13 + 9 existing panels

**Needs a PO decision:**
| Q | Decision |
|---|---|
| **D-a** | **`search`** (F-7): a whole unbuilt feature, in NO plan-30 row and no charter. Build it, or retire the activity-bar icon? A nav icon that says "Coming soon" is not an option. |
| **D-b** | **`timeline`** (F-6): extend knowledge's `TimelineTab` with the spoiler cutoff, or port composition's `TimelineView` as its own panel? |
| **D-c** | **G-WORKFLOWS**: plan 30 flags a head-on collision with Track C's P-5. Ownership call, not a build call. |
| **D-d** | **`[[`-create** (F-9): build "type `[[NewCharacter` → create it", or leave the affordance hidden? |
| **D-e** | **D-5 mobile-shell** — GG-4 retirement depends on it (per the orchestration plan's §6.3) |

**Convergence node, still to run:**
- **#2 the loop-③ Studio-only live smoke** (import → plan → draft → revise → translate → publish on ONE book). Cannot run before A-3..A-6 land.
- **#3 GG-4 retirement** — gated on the **5 unhomed** capabilities (settings · beats · timeline · style · references), NOT on a green test. The inventory now says so mechanically.
- **#4 full gate** — ✅ already green (every service suite + `ai-provider-gate`; see SESSION_HANDOFF).
