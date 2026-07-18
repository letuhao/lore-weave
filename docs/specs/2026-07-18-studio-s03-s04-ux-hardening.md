# Spec — Studio S-03/S-04 UX hardening: clear remaining dead-ends + lift GUI scores

> **STATUS: BUILT + QC'd (2026-07-18), 4 slices.** Commits: a785e9d5f (S1 CTA/confirms/aria),
> e2cba89d0 (S2 search/rename/BranchDiff), 3a4d36b13 (S3 mount reference-shelf + bible rail — registry,
> atomic), touch slice (S4 promote touchTarget + apply). Final QC: 239 FE tests green across 8 surfaces;
> BE frontend_tools+contract 43; tsc clean. Deferred: H-2c library-row pin (per-scene pin-state join);
> H-5b measured column-stacking (no @container plugin). See RUN-STATE_ux-hardening-build.md.

> **Status: CLARIFY (2026-07-18).** Follow-up to the cold-start UX audit of the reference-shelf (S-03) and
> divergence editor (S-04). The audit's quick wins already shipped (commit 5b380d249: archive→Undo/restore,
> POV snap-back, no-anchor hint, taxonomy labels, S-03 error toasts + URL-at-add + truncation). This spec
> covers the REMAINING dead-ends and the structural gaps that cap the GUI scores — each item names the metric
> it lifts, so the work is score-driven.
>
> **Current scores (post-quick-win):** S-03 ≈5.2/10 (capped by discoverability — stranded on the legacy page);
> S-04 ≈6.4/10 (capped by discoverability + touch). **Target: S-03 ≥7.5, S-04 ≥8.5.**
>
> **PO DECISION 2026-07-18 — discoverability is IN SCOPE (was: defer to S-10).** The PO pulled the S-10-owned
> discoverability items into this spec: **this spec now OWNS mounting `ReferencesPanel` as the `reference-shelf`
> studio panel (absorbs S-10 O2) and building the nav-rail discoverability for `reference-shelf` + `divergence`
> (absorbs the relevant slice of S-10 O4).** So the S-03 ceiling is no longer external — this spec clears it.
>
> **⚠ This means this spec DOES touch the shared studio registry** (`catalog.ts` + the `panel_id` enum in
> `chat-service/app/services/frontend_tools.py` + `contracts/frontend-tools.contract.json` + the
> `legacyParityContract` / `panelCatalogContract` tests) — the convergence node. **This spec SUPERSEDES S-10
> O2 (reference-shelf mount)**; the S-10 track must drop O2 (and the reference-shelf slice of O4) to avoid a
> double-build. Coordinate before building: confirm no parallel S-10 session is mid-mount, and land the
> registry edits as one atomic change (catalog + enum + contract + tests move together — the Frontend-Tool
> Contract discipline).

---

## The remaining gap list (from the audit) → what lifts which metric

| ID | Panel | Gap | Metric(s) lifted | Size |
|---|---|---|---|---|
| H-1a | S-03 | Reachable ONLY via the deprecated legacy `ChapterEditorPage` — a studio user can't find it | Usability, Discoverability | **M** (mount + registry + contract, absorbs S-10 O2) |
| H-1b | both | `divergence` (+ new `reference-shelf`) palette-only — no nav-rail entry | Ease-of-use, Discoverability | **M** (PANELS_BY_CATEGORY + category rail, absorbs O4 slice) |
| H-2a | S-04 | No **rename** for a derivative (name frozen at wizard creation) | Completeness | S |
| H-2b | S-03 | No **library search/filter** — a large shelf is an unfilterable scroll | Completeness, Usability | S |
| H-2c | S-03 | **Pin/exclude only on scene-retrieval hits** — can't pin a library row directly | Completeness | S |
| H-3a | S-03 | "Needs embedding model" is a **text dead-end** — no button to AI settings | Ease-of-use, Usability | XS |
| H-4a | S-03 | **Delete reference has no confirm** (hard delete, no restore) — data-loss | Consistency, Robustness | XS |
| H-4b | S-04 | **Remove override has no confirm** (low stakes — re-addable) | Consistency | XS |
| H-5a | both | Tap targets `py-0.5` + `text-[10px]` — under the touch minimum on a stated platform | A11y / multi-device | M |
| H-5b | S-04 | `BranchDiffView` fixed `grid-cols-[180px_1fr]` + nested `grid-cols-2` clips in a narrow dock | A11y, Beauty | S |
| H-5c | both | Icon-only `✎/✕`, `📌/🚫` with `title` only (no `aria-label`), low resting contrast, hover-reveal | A11y | S |

---

## EDGE CASES resolved + DECISIONS sealed (2026-07-18, at build eval)

**Sealed decisions** (PO delegated "resolve"): **PO-rail = `bible`** (empty stub today; "story bible" grouping);
**PO-tap = promote `touchTarget` util to shared + mobile-only variant**; **PO-ovr-confirm = lightweight inline
two-step** (not a modal — low stakes, re-addable).

**Edge fixes (found evaluating the spec against the catalog):**
1. **The `editor` category is too broad for a nav rail** (19 panels: settings/trash/planner/compose…). H-1b
   does NOT list a category — it introduces a curated **`navGroup?: 'bible'`** field on catalog panels, tags
   `reference-shelf` + `divergence` (extensible), and the `bible` rail lists `navGroup === 'bible'` panels as
   `host.openPanel(id)` launcher rows (the `quality`-button pattern, `StudioSideBar.tsx:97-106`). No
   `PANELS_BY_CATEGORY` (that was the wrong seam).
2. **No ambient scene in the studio mount.** Reference retrieval + pins are per-SCENE (`outline_node`). The
   studio dock has no reliable active-scene for a free-floating shelf, so **mount LIBRARY-FIRST**: pass
   `sceneId=''` → the panel's existing `{sceneId && embedModelSet && …}` gate hides retrieval/pin and shows the
   library CRUD (add/edit/delete/search — the S-03 core, fully operable). Per-scene retrieval-in-studio is a
   NOTED follow-up (needs the studio's active-scene plumbing; not a blocker — library management is the job).
3. **H-2c (library-row pin) is scene-gated too** — the pin control renders only when a `sceneId` is present
   (consistent with #2); library-first, it's simply absent, no dead control.

---

## Part 1 — Discoverability (the biggest score cap) — NOW IN SCOPE (PO pulled it in; absorbs S-10 O2 + O4-slice)

**Load-bearing finding (verified):** the "left nav lists a view's panels" mechanism **does not exist** —
`StudioSideBar.tsx:31-109` is a hardcoded if/else: `manuscript`→`ManuscriptNavigator`, `plan`→`PlanNavigatorRail`
are real; `bible`/`search`/`quality` are literal "Built next." stubs (`quality` has ONE fallback button →
`host.openPanel('quality')`, `:97-106`). The general "rail that lists a category's panels from a
`PANELS_BY_CATEGORY` export" (S-10 O4) does not exist yet. This spec builds the minimal version of it needed to
surface the two panels.

### H-1a · Mount `ReferencesPanel` as the `reference-shelf` studio panel (absorbs S-10 O2)
The S-03 edit affordance + error toasts already live ON `ReferencesPanel`, so mounting it makes the whole S-03
feature reachable in the studio. Build (mirrors the GG-8 panel shape of existing catalog panels, e.g.
`DivergencePanel.tsx`):
1. **Panel wrapper** `frontend/src/features/studio/panels/ReferenceShelfPanel.tsx` — `useStudioPanel('reference-shelf', props.api)`, reads `host.bookId` → resolves the Work's `project_id` (via `useWorkResolution`, same as DivergencePanel) + the active `sceneId` if the host exposes one (library add/edit/delete works without a scene; retrieval/pin needs one — degrade gracefully), renders `<ReferencesPanel projectId sceneId token models/>`.
2. **Catalog** — add `{ id: 'reference-shelf', component: ReferenceShelfPanel, category: 'editor', … }` to `STUDIO_PANELS` (`catalog.ts`). **Id is `reference-shelf`, NOT `references`** (collides with the `composition_find_references` tool — the S-10 O2 rule).
3. **panel_id enum** — add `"reference-shelf"` to the `ui_open_studio_panel` enum (`frontend_tools.py:402`) so the agent can open it.
4. **Contract + tests** — regenerate `contracts/frontend-tools.contract.json` (`WRITE_FRONTEND_CONTRACT=1 pytest`), and update `legacyParityContract.test.ts:105` (flip `references` from `unported` → ported) + `panelCatalogContract` (palette-openable set == enum == contract). These move together atomically (Frontend-Tool Contract discipline).
5. **Live-smoke** — open `reference-shelf` from the palette on a built FE, add + edit + delete a reference, confirm it round-trips (the anti-shell proof: the panel is reachable AND operable, not just registered).

### H-1b · Nav-rail discoverability for `reference-shelf` + `divergence` (absorbs the O4 slice)
Build the minimal category-rail so `editor`-category panels are discoverable from the nav (not palette-only):
1. **`PANELS_BY_CATEGORY`** export in `catalog.ts` — derive `{category: STUDIO_PANELS[]}` from the catalog
   (the map S-10 O4 references but that doesn't exist yet). One source of truth; no hand-rolled list.
2. **A rail that lists a category's panels** — extend `StudioSideBar.tsx`'s view→rail resolution so a view
   renders the list of its category's panels (each row → `host.openPanel(id)`), replacing the "Built next"
   stub for the view that owns the `editor` category. **PO-rail:** which activity view surfaces `editor`
   panels (divergence + reference-shelf)? Options: (a) reuse **`bible`** (currently a stub) as the
   story-authoring rail; (b) reuse **`plan`** (a dị bản is a plan-level what-if — but `plan` already has a
   real `PlanNavigatorRail`, so this would append a panel list below it); (c) add a new `editor`/`compose`
   activity view (`types.ts` union + icon + branch). Recommend **(a) `bible`** — it's an empty stub today, and
   "story bible / references / what-ifs" is a coherent grouping; least disruption.
3. This also lights up the other `editor`-category panels for free (whatever else is category `editor`), which
   is the O4 intent — coordinate with S-10 so O4 doesn't rebuild the rail.

**Coordination:** H-1a + H-1b are the S-10 O2 + O4-editor-slice work. This spec SUPERSEDES them; the S-10 track
retires O2 and the reference-shelf/divergence part of O4. The registry edits (catalog + enum + contract +
tests) land as ONE atomic change.

---

## Part 2 — Missing verbs

### H-2a · Rename a derivative — RESOLVED (code)
The name lives in `composition_work.settings.derivative_name`. **`patchWork` accepts a partial `settings`
patch and the server SHALLOW-MERGES it** (BE-18, `api.ts:586-604`: `COALESCE(settings,'{}') || $n`) — so a
rename = `patchWork(project_id, {settings: {derivative_name}}, token, {version})`, sending only the changed
key. Add a rename affordance (a ✎ on the detail header via the app's **`FormDialog`**
(`components/shared/FormDialog.tsx`, dock-safe, `max-h-[85vh]` body-scroll) with a name input) → patchWork with
`{version: w.version}` for If-Match parity with archive/restore (412 → reload). Keep the wizard's 1..200
validation. **FE-only — no MCP verb** (agents manage divergences via list/switch/archive/spawn; rename is a
human nicety; `frontend_tools.py:467-469` has no rename and doesn't need one).

### H-2b · Library search/filter (S-03)
A client-side filter over `refs.references` (title/author/content substring) — the library is small
(dozens–low-hundreds), so no backend. Add a search input above the Library list; filter the rendered rows.

### H-2c · Pin/exclude a library row directly (S-03)
Today pin/exclude only render on scene-retrieval hits. Add a pin/exclude control on each library row too
(reuse `setPin` — it already takes a reference id). Gated on a scene being selected (pins are per-scene);
when no scene, hide the control or show a hint.

---

## Part 3 — Dead-end CTAs + safety

### H-3a · Embed-model CTA (S-03) — RESOLVED (code)
Replace the text-only amber box (`ReferencesPanel.tsx:76-78`) with **`AddModelCta`**
(`components/shared/AddModelCta.tsx`, props `{capability:'embedding', variant:'link', label}`). Crucially it
detects `useOptionalStudioHost()` and, inside the dock, opens the `settings` panel **in-dock via
`followStudioLink`** (never navigates/unmounts) — so the user fixes the missing model without leaving the
shelf. Exactly the pattern `CompositionPanel.tsx:518-524` already uses for its `noChatModel` dead-end.

### H-4a · Confirm delete reference (S-03) — RESOLVED (code)
Reference delete is a HARD delete with no restore (by design). Guard it with **`ConfirmDialog`**
(`components/shared/ConfirmDialog.tsx`, `variant:'destructive'`, `title/description/onConfirm`) — "Delete this
reference? This can't be undone." (It even supports `confirmationPhrase` typed-confirm for extra-irreversible
deletes; not needed here — a single confirm suffices.)

### H-4b · Confirm remove override (S-04)
Lower stakes (re-addable via the picker). Either a lightweight inline "Remove? ✓/✕" two-step or the same
`ConfirmDialog`. PO: is a confirm wanted here, or is the low-stakes re-addability enough? (recommend a
lightweight inline confirm for consistency, not a modal.)

---

## Part 4 — Touch / a11y (the multi-device metric)

### H-5a · Tap-target sizing — convention EXISTS (code)
A shared convention exists: `features/knowledge/lib/touchTarget.ts` — `TOUCH_TARGET_MOBILE_ONLY_CLASS =
'min-h-[44px] md:min-h-0'` (44px on touch, normal on desktop) + a `_SQUARE_` variant for icon buttons. The
studio dock panels have NOT adopted it. **PO-tap:** promote the util to a shared location (`components/shared/`
or a `lib/`) and compose it via `cn()` on the interactive controls in both panels, OR import cross-feature.
Recommend **promote to shared** (a studio spec importing from `features/knowledge` is a smell) + apply the
mobile-only variant (keeps the dense desktop look, only grows tap targets on touch). Scope to these two panels
to stay bounded (not an app-wide sweep).

### H-5b · BranchDiffView responsive (S-04)
`BranchDiffView.tsx:42` is `grid-cols-[180px_1fr]` (fixed 180px scene list) and the changed-scene view nests
`grid-cols-2` (`:92`, Canon | dị bản) — both hardcoded, container-agnostic, and it renders inside the
`divergence` dock panel (can be ~300px). Fix: make the scene list `minmax(140px, 180px)` or collapsible, and
stack the two prose columns vertically under a container/width breakpoint (`@container` or a `md:` split) so
each gets full width when narrow. The `h-72` fixed height on the Diff tab (`DivergenceManagerView.tsx:183`) can
also flex to available height.

### H-5c · aria-labels + contrast on icon controls
Add `aria-label` to every icon-only button (`✎/✕/📌/🚫`), raise resting contrast (drop the `text-neutral-400`
rest state or make it visible), and make the row actions non-hover-dependent (already visible, not hover-gated)
for touch.

---

## CLARIFY summary — resolved (code) vs PO
| # | Question | Status |
|---|---|---|
| CV-nav | The view→panel discoverability mechanism | **RESOLVED: none exists; nav is hardcoded (StudioSideBar.tsx); the generic category rail = S-10 O4 (unbuilt)** |
| CV-s10 | Does S-10 own the reference-shelf mount; shipped or pending? | **RESOLVED: S-10 O2 owns it, PENDING/unbuilt — cross-track dep; this spec DEFERS** |
| CV-confirm | ConfirmDialog / AddModelCta / FormDialog | **RESOLVED: all exist in `components/shared/` (props in H-3a/H-4a/H-2a)** |
| CV-rename | patchWork settings patch for rename | **RESOLVED: shallow-merge settings patch (BE-18); FE-only, no MCP** |
| CV-tap | Shared tap-target convention? | **RESOLVED: `features/knowledge/lib/touchTarget.ts` (min-h-[44px] md:min-h-0); studio hasn't adopted** |
| **PO-scope** | Is H-1a (studio mount) + the nav rail in scope, or S-10's? | **SEALED 2026-07-18: IN SCOPE** — this spec absorbs S-10 O2 + the editor-slice of O4; SUPERSEDES them |
| **PO-rail** | Which activity view surfaces the `editor` category panels (divergence + reference-shelf)? | **NEEDS PO** — recommend **`bible`** (empty stub today; coherent "story bible" grouping) |
| **PO-tap** | Promote touchTarget util to shared + apply mobile-only variant? | **NEEDS PO** — recommend yes (promote + mobile-only) |
| **PO-ovr-confirm** | Confirm on override remove — inline / modal / none? | **NEEDS PO** — recommend lightweight inline (low stakes, re-addable) |

## Projected score lift (why this is worth building)
| Panel | Now | After this spec (H-1a now IN scope) | Note |
|---|---|---|---|
| **S-03** | ≈5.2 | **≈7.5** (studio MOUNT + nav rail lift the discoverability cap; + search + pin-row + CTA + confirm + touch + aria) | ceiling removed — the whole feature is now reachable + operable in the studio |
| **S-04** | ≈6.4 | **≈8.5** (nav rail + rename + confirms + touch + BranchDiff + aria; archive-Undo already shipped) | target exceeded |

Pulling the mount in-scope is what unlocks S-03 past ~7 — the discoverability cap was the dominant term.

## Sizing + build order (score-per-effort)
1. **XS quick wins (do first, no registry risk):** H-3a (AddModelCta), H-4a + H-4b (confirms), H-5c (aria +
   contrast). Pure composition-FE.
2. **S:** H-2b (library search), H-2c (library-row pin), H-2a (rename via FormDialog), H-5b (BranchDiff
   responsive).
3. **M — the discoverability block (touches the shared registry — land atomically, coordinate with S-10):**
   H-1a (mount `ReferencesPanel` → `reference-shelf`: catalog + panel_id enum + contract + parity/catalog tests
   + live-smoke) then H-1b (`PANELS_BY_CATEGORY` + the category rail in `StudioSideBar`). Do H-1a before H-1b
   (the rail lists what the catalog holds).
4. **M:** H-5a (promote `touchTarget` util to shared + apply mobile-only variant to both panels).

**Total in-scope: L** (composition FE + studio panels + the shared studio registry + contract/test regen +
cross-service live-smoke through the gateway). Full CLARIFY→…→RETRO when built; **`/review-impl` recommended**
for the registry/contract change (Frontend-Tool Contract is load-bearing — a drift silently breaks the agent
open path). **This spec now edits the convergence registry** — build only after confirming no parallel S-10
mount is in flight, and retire S-10 O2 + the O4 editor-slice so they aren't double-built.
