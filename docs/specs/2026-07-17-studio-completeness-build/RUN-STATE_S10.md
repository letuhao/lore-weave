# RUN-STATE — S-10 build (Tier-C FE orphans: reachability + mounts)

> Spec: S-10_fe-orphans.md (CLARIFY-sealed; PO D-a/D-d resolved). NO new spec needed.
> Mostly FE; ONE backend piece (O3 diagnostics REST route mirroring the shipped agent_native.py).
> Shared checkout: NO `git add -A`; atomic pathspec commits; GG-8 items touch the hot registry
> (catalog.ts / panel_id enum / frontend-tools.contract.json / studio.json) — go carefully.

## THE COMMITMENT
Build the S-10 orphans that are genuinely unbuilt. DONE = each buildable slice built + tested + committed.

## INVESTIGATE (verified vs code 2026-07-18 — NOT trusting the doc)
Already shipped by the UX-hardening + parallel sessions (verified in catalog.ts / StudioSideBar):
- **O2 reference-shelf** — BUILT (catalog `reference-shelf`, `ReferenceShelfPanel`, H-1a). Placed `storyBible`
  + `navGroup:'bible'` (the bible rail), NOT the spec's `editor` category — reachable via the bible rail
  either way, so O2's reachability goal is met. (Category placement = a conscious H-1a call, not a gap.)
- **O4 bible rail** — BUILT (`BIBLE_NAV_PANELS` + StudioSideBar renders the launcher list).
- **O4 quality rail** — RESOLVED DIFFERENTLY: `QualityHubPanel` is a launcher listing all 9 quality panels
  (the DOCK-8 hub pattern). Reachability is satisfied by the hub button → hub launcher, not a sidebar list.
  Conscious won't-fix vs the spec's "list-rail" wording (same reachability outcome).
- **search rail** — BUILT in S-11 (D-a).

Genuinely UNBUILT (the S-10 build set):
- **O1 style-voice** — no `style-voice` panel in catalog. StyleVoicePanel is editor-page-only. BUILD (GG-8).
- **O3 Issues tab + diagnostics** — StudioBottomPanel's 3 tabs are stubs ("Feed appears here once wired").
  The engine `services/composition-service/app/services/agent_native.py` (Diagnostics/severity map/rank)
  EXISTS + is MCP-exposed. BUILD the REST mirror + wire the tabs.
- **O5 MotifBindingLens** — component exists, 0 importers. BUILD the PlanDrawer mount.
- **O6 3 arc surfaces** — no FE callers of arc_extract_template / arc-templates/suggest / decompile_arcs.
  BUILD 3 buttons over the shipped engines.
- **O7 [[-create** — `GlossaryAutocomplete.tsx` has onCreateNew wired to `() => {}` (EditorPanel comment
  says "omitted on purpose"). PO D-d decided BUILD. BUILD the `[[NewName`→kind-picker→createEntity flow.

## SLICE BOARD (done = evidence)
- [ ] O5 — mount MotifBindingLens in PlanDrawer's ChapterSceneFacets + thread projectId/chapterId; mount test.
- [ ] O7 — `[[`-create in GlossaryAutocomplete (enum-gated AuthorableKind) + wire EditorPanel + ChapterEditorPage.
- [ ] O6 — 3 arc buttons (extract-template / suggest-arc / decompile-arcs) over shipped engines.
- [ ] O1 — style-voice GG-8 panel (catalog + enum + contract + i18n + CATEGORY_ORDER + Lane-B handler).
- [ ] O3 — GET /v1/composition/books/{bid}/diagnostics (read-only agent_native mirror) + wire the 3 bottom tabs.

## DECISIONS (S-10-local)
- O4-quality: keep the DOCK-8 hub (QualityHubPanel launcher) — reachability already met; do NOT add a rival
  sidebar list-rail (would duplicate the hub). O2 category stays storyBible/bible-rail (H-1a).

## CONVERGENCE NOTES
- (to append as slices land — esp. any catalog.ts / panel_id enum / studio.json touches for O1.)
