# 17 — Translation / Lore Enrichment / Book Sharing / Book Settings docks

Status: CLARIFY+PLAN complete, ready for BUILD fanout.
Size: XL (4 independent porting efforts; Enrichment alone is a DOCK-8 6-way split).

## Why

Four classic book-route pages (`TranslationTab`, `EnrichmentTab`→`EnrichmentView`,
`SharingTab`, `SettingsTab`) still live outside the Writing Studio, forcing a route
hop away from the dockable workspace every time an author wants to translate,
enrich, share, or configure their book — the same gap Chapter Browser, Books,
Leaderboard, and the 13 `kg-*` panels already closed for their own capabilities.
This spec ports all four, following the identical shape: thin `DOCK-2` wrappers
over the EXISTING feature components, `DOCK-7` route-decoupling, `DOCK-9`
overlay-hygiene, and (for Enrichment specifically) a `DOCK-8` capability split.

Investigation source: a dedicated research pass over all four classic pages
(capabilities, `navigate`/`Link` call sites, API deps, dead-end empty states,
hand-rolled overlays) — findings folded into the per-dock sections below.

---

## Cross-cutting decisions (apply to all 4)

- **D1 — one catalog panel per real capability**, never an internal tab switch
  hiding sibling capabilities (`DOCK-8`). Translation/Sharing/Settings are each
  genuinely ONE capability → ONE panel. Enrichment's `EnrichmentView` 6-way
  switch is the textbook violation and gets split into 6 sibling panels (§Enrichment).
- **D2 — reuse AS-IS, no forks.** Every new panel is a thin wrapper: register
  (`useStudioPanel`), resolve book/project context from `host.bookId` instead of
  a route param, render the EXISTING component/hook tree unmodified except for
  the specific `DOCK-7`/`DOCK-9` call sites listed per dock.
  Empty state / not-linked messages get a real button (following the
  `KgNoProjectState` precedent from the just-shipped `D-KG-NO-CREATE-CTA` fix) — a
  dead-end message with no button is a defect, not an acceptable empty state.
- **D3 — DOCK-7 fix shape.** A `navigate()`/`<Link>` call site inside a ported
  component becomes `host.openPanel(...)` (in-studio target exists) or
  `followStudioLink(...)` (target is out-of-studio scope, e.g. another top-level
  resource — external new tab is the CORRECT behavior there, same as the
  Knowledge hub's cross-book case, not a bug to "fix away").
- **D4 — DOCK-9 fix shape.** A hand-rolled `fixed inset-0` overlay pair becomes
  `FormDialog` (form-shaped content) or raw `Dialog.*` (custom multi-part chrome
  that doesn't fit FormDialog's single-body shape) per `docs/standards/dockable-gui.md`.
  A pure click-outside popover (no backdrop dim, no portal) is NOT a DOCK-9
  violation — same accepted-exception shape already used elsewhere in this repo.
- **D5 — spine files are orchestrator-only.** All 4 build efforts run in
  parallel on genuinely disjoint feature files. `catalog.ts`, the 4 locale
  `studio.json` files, `frontend_tools.py`'s `panel_id` enum, and
  `contracts/frontend-tools.contract.json` are shared across all 4 — no BUILD
  agent touches them. Each agent's final report lists its exact catalog
  row(s)/i18n keys/enum entries; the orchestrator integrates all 4 into the
  spine files serially, once, after every agent finishes. This is the same
  discipline the Chapter Browser BE/FE split and the Books+Leaderboard+Jobs
  3-way fanout already used successfully in this session.

---

## Translation dock

**Panels:** `translation` (the coverage matrix — chapters × languages, filters,
bulk-select, legend) and a new sibling `translation-versions` (per-(chapter,lang)
version management — thin wrapper over the EXISTING `ChapterTranslationsPanel`,
already used by the editor's Translate workmode; opened via
`host.openPanel('translation-versions', {params:{chapterId, lang}})` instead of
`TranslationTab`'s current `navigate(/books/:id/chapters/:id/translations?lang=)`).

**Source:** `TranslationTab.tsx` (540 lines, monolith) + `TranslateModal.tsx` (593
lines, monolith, ALREADY reused in-studio by Chapter Browser's bulk "Translate…"
action) + `SegmentDrilldownModal.tsx` (116 lines) + `ExtractionWizard.tsx` (282
lines, shared with other tabs — already Radix-compliant, do not touch its dialog
chrome).

**DOCK-7 fixes:**
- `TranslationTab.tsx:422` matrix-cell `navigate(...)` → `host.openPanel('translation-versions', {params:{chapterId, lang}})`.
- `TranslateModal.tsx:313` `<Link to="/settings">` (ModelPicker's no-models empty state) → `host.openPanel('settings', {params:{tab:'providers'}})` (mirrors `studioLinks.ts`'s existing `SETTINGS_RE` → `{tab}` param shape).
- `ExtractionWizard.tsx:43,87` — already has a `studioHost ? openPanel : navigate` guard; verify in BUILD whether `dockablePanelHygiene.test.ts`'s grep scope includes files outside `features/studio/panels/` (it currently doesn't appear to, per precedent — `ExtractionWizard` lives in its own feature folder) — if the grep does NOT reach it, no further change needed there; if it does, thread `host` down explicitly and drop the `navigate` branch when called from a studio panel context.

**DOCK-9 fixes (both are hand-rolled `fixed inset-0` pairs, already live in
production via Chapter Browser's existing TranslateModal reuse — fix now, not a
new defect):**
- `TranslateModal.tsx` (lines 265-266) → `FormDialog` (size `2xl`/`3xl` — it has language+model pickers, an advanced QA-config panel, and a paginated chapter checklist; pick the size that avoids a cramped layout).
- `SegmentDrilldownModal.tsx` (lines 26-27) → `FormDialog` or raw `Dialog.*`, whichever fits its per-segment dirty/stale list + re-translate action better.

**Empty-state note:** `TranslationTab`'s own "no chapters"/"no translations yet"
states and `TranslateModal`'s "everything already translated" state all already
have real CTAs — no dead-end fix needed here (unlike Enrichment/Settings below).

---

## Lore enrichment dock

**Panels (6 siblings, no hub — each is independently palette+agent-openable,
mirroring the `kg-*` panels' shape rather than Glossary's hub+siblings shape,
since there's no natural "browse first" list UI need here):**
`enrichment-compose`, `enrichment-proposals`, `enrichment-gaps`,
`enrichment-sources`, `enrichment-jobs`, `enrichment-settings`.

**Source:** `EnrichmentView.tsx`'s `PANELS` switch → `ComposePanel.tsx`,
`ProposalsPanel.tsx`, `GapsPanel.tsx`, `SourcesPanel.tsx`, `JobsPanel.tsx`,
`SettingsPanel.tsx` (each already an isolated, sub-280-line component — the
violation is purely at the shell layer, not a monolith problem; this is the
easy case of the 4).

**DOCK-7 fixes:** none — the whole `features/enrichment/` tree is already clean
(zero `navigate`/`useParams`/`Link` found).

**DOCK-9 fixes:** none needed for the 6 target panels — `PromoteDialog.tsx`
(used inside Proposals) is already correctly-patterned raw Radix `Dialog.*`.

**Empty-state fix (D-ENRICH-GAPS-NO-EXTRACT-CTA, same bug class as
`D-KG-NO-CREATE-CTA`):** `GapsPanel.tsx`'s `gaps.length === 0 && needsExtraction`
branch renders `t('gaps.extract_first')` with no button. Fix: add a CTA that
opens the existing `ExtractionWizard` (already used elsewhere in this repo,
already Radix-compliant) scoped to this book, so the user has an actual path
forward instead of a static message.

---

## Book sharing dock

**Panel:** `sharing` (visibility radio-cards, unlisted-link + rotate, collaborator
invite/role-change/remove).

**Source:** `SharingTab.tsx` (158 lines) + `CollaboratorsPanel.tsx` (114 lines).

**DOCK-7 / DOCK-9 fixes:** none — already clean on both (no `navigate`/`Link`,
no dialogs/overlays at all). This is the simplest, lowest-risk port of the 4;
build it first if the BUILD agent needs a template for the other three.

---

## Book settings dock

**Panel:** `book-settings` (deliberately NOT `settings` — that id is already the
user-level account/providers/translation panel in the catalog; reusing it here
would collide two different capabilities under one id).

**Source:** `SettingsTab.tsx` (404 lines, monolith — basic info / cover / genre
tags / world link, no sub-component split yet) + `BookWorldSection.tsx`.

**DOCK-7 fix:** `BookWorldSection.tsx:51` `<Link to={/worlds/:id}>` ("Open in
world") → route through `followStudioLink`/`host` instead of a raw react-router
`Link`. World is a top-level resource with no studio panel today, so the
PRACTICAL behavior is unchanged (external new tab) — this fix is about hygiene
(no raw `Link` inside a studio panel's component tree) and forward-compat (it
upgrades automatically if a `world` panel is ever built, same as the Knowledge
hub's own precedent comment).

**DOCK-9 — accepted exception, not a fix:** the genre-dropdown
(`SettingsTab.tsx:285-321`) is a click-outside-to-close popover (z-30 catcher +
z-40 body, no backdrop dim, no portal) — same accepted shape as other
anchored-popovers already living in this repo. Port it as-is; do not force it
into `FormDialog`.

**Small fix-now (cheap, root-cause-clear per CLAUDE.md's fix-now bias — touching
this exact function anyway):** the cover-image DELETE call uses raw `apiJson`,
bypassing `booksApi` (every other call in the file goes through `booksApi.*`).
Add `booksApi.deleteCover` and use it instead.

**Deferred (gate #2 — large/structural, earns its row, do NOT fix in this
task):** `D-SETTINGS-NO-GENRE-CTA` — the "no genres" empty state has no button
either, but genres are authored elsewhere (Glossary/Ontology admin, not yet
clear which surface), and building that click-through needs a PLAN-time
decision about where genres actually get created — out of scope for a
straightforward page-port. Track in `docs/sessions/SESSION_HANDOFF.md`.

---

## BUILD fanout plan

4 parallel agents, genuinely disjoint files (D5 above — none touch the shared
spine). Suggested order if run with limited concurrency: Sharing (simplest,
validates the pattern) → Settings → Translation → Enrichment (largest).

| Agent | Scope | New/changed files (indicative) |
|---|---|---|
| **A — Sharing** | `sharing` panel | `features/studio/panels/SharingPanel.tsx` (+test) |
| **B — Book Settings** | `book-settings` panel + `booksApi.deleteCover` + `BookWorldSection` DOCK-7 fix | `features/studio/panels/BookSettingsPanel.tsx` (+test), `features/books/api.ts`, `features/world/components/BookWorldSection.tsx` |
| **C — Translation** | `translation` + `translation-versions` panels + DOCK-9 migration | `features/studio/panels/TranslationPanel.tsx`, `TranslationVersionsPanel.tsx` (+tests), `pages/book-tabs/TranslateModal.tsx`, `SegmentDrilldownModal.tsx` |
| **D — Enrichment** | 6 sibling panels + Gaps CTA fix | `features/studio/panels/Enrichment{Compose,Proposals,Gaps,Sources,Jobs,Settings}Panel.tsx` (+tests), `features/enrichment/components/GapsPanel.tsx` |

Each agent's final report must include, verbatim, for orchestrator integration:
1. Exact `catalog.ts` row(s) (id, component import, titleKey/descKey).
2. Exact new i18n keys needed (English text; other 3 locales translated by the
   orchestrator during integration, matching this session's established pattern).
3. Exact `panel_id` enum additions for `frontend_tools.py` + the matching
   `contracts/frontend-tools.contract.json` regen.
4. Any new/changed shared component (e.g. `booksApi.deleteCover`) — call out
   explicitly since it's the one cross-agent-visible change (B only).

## Verify gate (applies per-panel, before integration)

- Unit tests green (mirror the `KnowledgeHubPanel`/`ChapterBrowserPanel`
  stubbing pattern — stub heavy child components, test the panel's own wiring).
- `dockablePanelHygiene.test.ts` passes with the new files included (no raw
  `navigate`/`useParams`/`Link`, no hand-rolled `fixed inset-0` outside the one
  accepted genre-popover exception).
- Live browser smoke of at least the golden path per dock (this task's own
  retro should NOT repeat the DOCK-11 E2E gap the Chapter Browser task's retro
  flagged and then closed) — minimum bar: open each of the 4(+2) new panels
  from the command palette on a real book, confirm no console errors, exercise
  one real action per dock (e.g. trigger a translation, approve/reject one
  proposal, change visibility, save a settings edit).

## Out of scope

- Building the "create genre" flow (`D-SETTINGS-NO-GENRE-CTA`, deferred above).
- Any World workspace studio panel (out of scope entirely — Worlds stays a
  top-level classic route for now).
- Deeper Enrichment feature work (new compose modes, new proposal actions) —
  this is a port, not a redesign.
