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
- [ ] S1 XS (no registry): H-3a AddModelCta · H-4a delete-confirm · H-4b override-confirm · H-5c aria — EVID:
- [ ] S2 S: H-2b library search · H-2c library-row pin (scene-gated) · H-2a rename FormDialog · H-5b BranchDiff — EVID:
- [ ] S3 M discoverability (REGISTRY, atomic): H-1a mount reference-shelf · H-1b bible nav rail — EVID:
- [ ] S4 M touch: H-5a promote touchTarget + apply to both panels — EVID:

## PARKED / DEBT / DRIFT
- (none yet)
