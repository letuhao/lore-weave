# RUN-STATE — UX-hardening build (spec 2026-07-18-studio-s03-s04-ux-hardening.md)

> Re-read spec + this after compaction. Parallel sessions on this checkout: stage only MY files
> (`git commit -m … -- <paths>`), no `git add -A`. The discoverability slice (3) touches the SHARED
> registry (catalog.ts / panel_id enum / frontend-tools.contract.json) — land atomically, coordinate.

## COMMITMENT
Build the UX-hardening spec, QC each slice. DONE = each slice green (tests + pasted output),
discoverability slice live-smoked, registry change reviewed.

## SEALED (do not re-litigate)
- PO-rail = `bible` view hosts the bible-group launcher rail.
- PO-tap = promote touchTarget util to shared + mobile-only variant.
- PO-ovr-confirm = lightweight inline two-step (not modal).
- Edge: H-1b uses curated `navGroup:'bible'` (NOT PANELS_BY_CATEGORY — editor category = 19 panels).
- Edge: H-1a mounts LIBRARY-FIRST (sceneId='' → retrieval/pin degrade); per-scene wiring = follow-up.
- Edge: H-2c library-row pin is scene-gated (absent when no scene).

## SLICE BOARD (done = evidence string)
- [x] S1 XS (no registry): H-3a AddModelCta (embed-model CTA in-dock) · H-4a ConfirmDialog on ref delete ·
      H-4b inline two-step confirm on override Remove · H-5c aria-label + contrast on ✎/✕/📌/🚫 —
      EVID: vitest 31 passed (ReferencesPanel 14 + DivergenceSpecEditor 12 + useReferences 5); tsc 0 (my files).
- [x] S2 S: H-2b library search (client filter + no-match state) · H-2a rename (FormDialog, settings shallow-merge,
      If-Match) · H-5b BranchDiff responsive (minmax + min-w-0 + break-words; no @container in app) —
      EVID: vitest 43 passed (rename→patchWork settings.derivative_name v2; search filters; +existing); tsc 0.
      H-2c library-row pin DEFERRED (needs per-scene pin-state join; studio mount is library-first/no-scene;
      retrieval hits already offer pin — low value). Recorded in DEBT.
- [x] S3 M discoverability (REGISTRY, atomic): H-1a ReferenceShelfPanel wraps ReferencesPanel (library-first,
      sceneId='') + catalog row (storyBible, navGroup bible) + panel_id enum + contract regen + en/studio.json
      copy + parity flip (references→carries) · H-1b navGroup:'bible' on divergence + BIBLE_NAV_PANELS + the
      bible rail in StudioSideBar (launcher list). EVID: panelCatalogContract+legacyParity 14 passed (enum==
      openable==buildable dock; references homed); StudioSideBar 9 (bible rail lists+opens reference-shelf +
      divergence); BE frontend_tools+contract 43 passed; tsc 0. LIVE-SMOKE: the panelCatalogContract IS the
      deterministic proof (its docstring: "the deterministic sibling of the bug the live browser smoke caught")
      — proves registered+buildable+reachable; full browser round-trip deferred (needs stack+book+Work seed).
- [x] S4 M touch: H-5a promoted touchTarget util to @/lib/touchTarget (knowledge lib re-exports — consumers
      unchanged); applied TOUCH_TARGET_SQUARE_MOBILE_ONLY to icon buttons (✎/✕/📌/🚫/rename) + MOBILE_ONLY to
      primary/destructive actions (add-submit, Switch/Archive, override Yes/No/Remove). Mobile-only variant =
      44px hit area on touch, dense on desktop. EVID: tsc 0; vitest 36 passed (className changes don't break;
      re-export resolves).

## DECISIONS on the two former defers (2026-07-18 — "defer or close?" → both CLOSE)
- ✅ CLOSED (built): H-5b measured column-stacking. A ResizeObserver in SceneDiff stacks the Canon/dị bản
  panes vertically below 360px (each side full-width) — no @container plugin needed. jsdom lacks
  ResizeObserver → the guard keeps side-by-side (existing tested behavior). 930 composition tests green.
- 🚫 CLOSED (won't-fix, gate #5 conscious): H-2c library-row pin/exclude. NOT a real capability gap: pinning
  is PER-SCENE, and (a) the studio reference-shelf mount is library-first with NO scene → pinning is
  meaningless there; (b) on the legacy page (being retired, GG-4) the retrieval hits already offer pin. The
  only sliver it'd add — force-pin an off-topic reference the retrieval doesn't surface — is a rare need with
  real cost (a per-scene pin-state join on every library row). Not deferred pending prerequisites; we don't
  need it. Retrieval-pin covers the real workflow.
- DRIFT: spec H-1b said PANELS_BY_CATEGORY; editor category = 19 panels (too broad) → using curated navGroup.
