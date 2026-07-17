# Writing Studio — Completeness Audit (convergence node)

> **Run:** 2026-07-17, after all 8 sessions closed. **Method:** verify every claim against CODE, never
> against prose. The sessions' own registers are self-report; this audit exists because
> `debt-batches-list-is-stale-verify-first` says a debt list overstates real debt by ~40-50% — and it did.
> **Audited against:** the §2 production-ready bar in
> [`2026-07-16-studio-completeness-8-session-orchestration.md`](2026-07-16-studio-completeness-8-session-orchestration.md)
> and its §6 convergence node.
>
> **Status:** IN PROGRESS — rounds 1–2 below. Update in place as rounds land.

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

## Still to audit (rounds 3+)

- [ ] Per-family §2 bar: operable · CRUD · no-silent-failure · loop-connected · proven · scale
- [ ] plan 30's §5 gap register — every row's real state
- [ ] BE/MCP tools with no GUI (the original question this whole track started from)
- [ ] Convergence #2: the loop-③ Studio-only live smoke (import → plan → draft → revise → translate → publish)
- [ ] Convergence #3: GG-4 retirement readiness (blocked on F-1 + the D-5 mobile-shell decision)
