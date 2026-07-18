# Spec — Studio S-03/S-04 UX hardening: clear remaining dead-ends + lift GUI scores

> **Status: CLARIFY (2026-07-18).** Follow-up to the cold-start UX audit of the reference-shelf (S-03) and
> divergence editor (S-04). The audit's quick wins already shipped (commit 5b380d249: archive→Undo/restore,
> POV snap-back, no-anchor hint, taxonomy labels, S-03 error toasts + URL-at-add + truncation). This spec
> covers the REMAINING dead-ends and the structural gaps that cap the GUI scores — each item names the metric
> it lifts, so the work is score-driven.
>
> **Current scores (post-quick-win):** S-03 ≈5.2/10 (capped by discoverability — stranded on the legacy page);
> S-04 ≈6.4/10 (capped by discoverability + touch). **Target: S-04 ≥8 (reachable here); S-03 ≥6.8 here, with
> its ~7 ceiling gated on the S-10 O2 studio mount (cross-track).**
>
> **Sealed reality (verified 2026-07-18):** the biggest S-03 cap (studio mount) and the *proper* nav-rail
> mechanism are **owned by S-10** (O2 mount + O4 category rails) and are unbuilt — so this spec DEFERS those,
> coordinates with S-10, and delivers everything else (rename, search, pin-row, CTA, confirms, touch/a11y,
> BranchDiff, a nav-launcher stopgap). It does NOT touch the shared registry (catalog.ts / panel_id enum /
> frontend-tools.contract.json) — that's S-10's.

---

## The remaining gap list (from the audit) → what lifts which metric

| ID | Panel | Gap | Metric(s) lifted | Size |
|---|---|---|---|---|
| H-1a | S-03 | Reachable ONLY via the deprecated legacy `ChapterEditorPage` — a studio user can't find it | Usability, Discoverability | **DEFER → S-10 O2** |
| H-1b | S-04 | `divergence` panel is palette-only — no nav-rail entry | Ease-of-use, Discoverability | S (stopgap launcher; proper rail = S-10 O4) |
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

## Part 1 — Discoverability (the biggest score cap) — MOSTLY owned by S-10; this spec coordinates + stopgaps

**Load-bearing finding (verified):** the "left nav lists a view's panels" mechanism **does not exist** —
`StudioSideBar.tsx:31-109` is a hardcoded if/else: `manuscript`→`ManuscriptNavigator`, `plan`→`PlanNavigatorRail`
are real; `bible`/`search`/`quality` are literal "Built next." stubs (`quality` has ONE fallback button →
`host.openPanel('quality')`, `:97-106`). The general "rail that lists a category's panels from a
`PANELS_BY_CATEGORY` export" is **S-10 O4** (that export doesn't exist yet). So both discoverability items are
substantially S-10's charter.

### H-1a · S-03 reference-shelf into the studio — **DEFER to S-10 O2 (owned, pending)**
Verified: `ReferencesPanel` is NOT in `catalog.ts` / the `panel_id` enum; the parity contract records it as
`unported` "pending the F-1 port … belongs to NO session charter" (`legacyParityContract.test.ts:105`), and
**S-10 O2** (`S-10_fe-orphans.md:15-18`) owns wrapping it as the `reference-shelf` catalog panel that CARRIES
the S-03 edit affordance I already built. Git log confirms no mount commit. **This spec does NOT duplicate the
port** — it is a cross-track dependency. Action: (1) leave the S-03 edit affordance on the component (it rides
S-10's mount for free); (2) add a coordination note so S-10 O2 knows the affordance + error toasts are ready.
Until S-10 O2 lands, S-03's studio-discoverability score stays capped — that is the honest ceiling and it is
not in this spec's power to lift.

### H-1b · S-04 divergence on a nav rail — **stopgap launcher now; proper rail = S-10 O4**
The proper fix (a rail listing `editor`-category panels) is S-10 O4. **Stopgap (in scope here):** mirror the
`quality` precedent (`StudioSideBar.tsx:97-106`) — add an explicit "What-if / dị bản" launcher button that
calls `host.openPanel('divergence')`, so a user browsing the nav finds it before O4 lands. **PO-rail:** which
view hosts the launcher — recommend the **`plan`** rail (a dị bản is a plan-level what-if; `PlanNavigatorRail`
is real and already opens plan-hub, so adding a divergence launcher there is natural). Keep it a small addition
that O4 can later absorb into the generic category rail.

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
| **PO-rail** | Which nav view hosts the `divergence` launcher stopgap? | **NEEDS PO** — recommend `plan` rail |
| **PO-tap** | Promote touchTarget util to shared + apply mobile-only variant? | **NEEDS PO** — recommend yes (promote + mobile-only) |
| **PO-ovr-confirm** | Confirm on override remove — inline / modal / none? | **NEEDS PO** — recommend lightweight inline (low stakes, re-addable) |
| **PO-scope** | Is H-1a in scope or strictly S-10's? | **NEEDS PO** — recommend DEFER to S-10 (don't fork the registry) |

## Projected score lift (why this is worth building)
| Panel | Now | After this spec (excl. H-1a, S-10-gated) | The remaining cap |
|---|---|---|---|
| **S-03** | ≈5.2 | **≈6.8** (search + pin-row + CTA + confirm + touch + aria) | still capped at ~7 until **S-10 O2** mounts it in the studio (discoverability) |
| **S-04** | ≈6.4 | **≈8.0** (rename + nav launcher + confirms + touch + BranchDiff + aria) | reaches target; proper category rail (S-10 O4) polishes discoverability further |

S-03 can't clear ~7 from THIS spec alone — its ceiling is the S-10 O2 mount. S-04 reaches the ≥8 target.

## Sizing + build order (score-per-effort)
1. **XS quick wins (do first):** H-3a (AddModelCta), H-4a + H-4b (confirms), H-5c (aria-labels + contrast).
2. **S:** H-2b (library search), H-2c (library-row pin), H-2a (rename via FormDialog), H-1b (divergence nav
   launcher stopgap), H-5b (BranchDiff responsive).
3. **M (one focused pass):** H-5a (promote touchTarget util + apply to both panels).
4. **DEFERRED to S-10 (not this spec):** H-1a (reference-shelf mount, O2) + the generic category rail (O4).
   Add a coordination note to S-10 that S-03's edit affordance + error toasts are built and ready to ride O2.

**Total in-scope: M** (single-service composition FE + one shared-util promotion). Full CLARIFY→…→RETRO when
built. Registry files (catalog.ts / panel_id enum / frontend-tools.contract.json) are NOT touched here — the
only nav change is a launcher button in a real navigator, not a catalog/enum edit (those belong to S-10).
