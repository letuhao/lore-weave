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
- [ ] S3 M discoverability (REGISTRY, atomic): H-1a mount reference-shelf · H-1b bible nav rail — EVID:
- [ ] S4 M touch: H-5a promote touchTarget + apply to both panels — EVID:

## PARKED / DEBT / DRIFT
- DEBT H-2c: library-row pin/exclude deferred — needs a per-scene pin-state join on library rows (pins are
  per-scene); studio mount is library-first (no scene); retrieval hits already offer pin. Low value; revisit
  if per-scene reference-shelf-in-studio lands.
- DEBT H-5b: full narrow-dock STACKING (Canon/dị bản columns) needs a measured breakpoint — no @container
  plugin in the app. Shipped the no-clip CSS fix (minmax + min-w-0 + break-words); measured-stack is a follow-up.
- DRIFT: spec H-1b said PANELS_BY_CATEGORY; editor category = 19 panels (too broad) → using curated navGroup.
