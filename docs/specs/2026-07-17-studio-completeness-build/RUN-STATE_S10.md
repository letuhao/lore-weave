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
- [x] O5 — MotifBindingLens mounted in PlanDrawer (threaded projectId/token/roster; hidden w/o project).
      EVID: +2 mount tests; plan-hub 251 green. Commit a2761f769.
- [x] O7 — `[[`-create: GlossaryAutocomplete kind-picker (closed AuthorableKind) + useGlossaryQuickCreate
      wired in BOTH consumers. EVID: hook 4 + component 2 tests; consumers 20 green; i18n +6×18. Commit e7b633a13.
- [x] O6a — extract-template: "Save as template" on the arc inspector. EVID: 4 tests. (arcApi+hook+widget)
- [x] O6b — suggest: "Suggest" tab in Arc Templates panel (premise→ranked candidates). EVID: 3 tests.
- [x] O6c — decompile: REST twin POST /books/{id}/arcs/decompile + "Group chapters into arcs" in plan-hub
      Simple view. EVID: BE 3 + FE 4 tests; arc-routes 32 green. (O6a/b/c commits per git log)
- [x] O1 — style-voice GG-8 panel: StyleVoiceStudioPanel wrapper + catalog row + chat-service panel_id
      enum + contract regen + legacyParityContract flip (style HOMED) + i18n ×18. EVID: panelCatalog +
      legacyParity 14 green; frontend_tools_contract 20; tsc clean. (O1 commit per git log)
- [x] O3 — Issues tab + diagnostics REST twin: extracted the shared build_book_diagnostics(agent_native)
      called by BOTH the MCP tool + GET /books/{id}/diagnostics; FE Issues feed with kind→panel deep-links,
      jobs/generation launch jobs-list. EVID: BE arc+agent_native+mcp 129 green (refactor behaviour-
      preserving); FE Issues+bottom 8 + studio components 41 green; tsc clean. (O3 commit per git log)

## S-10 COMPLETE — all 7 O-items done (O2/O4/search were already shipped; O1/O3/O5/O6/O7 built this run).

## CONVERGENCE — i18n keys to batch-fill (deferred to avoid concurrent writes on the hot i18n files)
All rendered via `t(key, {defaultValue})` (UI works now; parity gate passes since keys are absent). Fill in a
convergence batch via `scripts/i18n_translate.py`:
- **studio.json**: `panels.arc-inspector.body.secTemplate`.
- **composition.json**: `motif.arc.extract.*` (blurb/open/namePlaceholder/save/saving/cancel/conflict/error/done),
  `motif.arc.suggest.*` (noProject/premisePlaceholder/genrePlaceholder/run/running/error/empty/mine/span),
  `motif.arc.templates.tabSuggest`, `motif.arc.decompile.*` (open/confirm/run/running/cancel/error/done/none).
- **studio.json (O3)**: `bottom.issues`, `bottom.launch.{jobs,generation}`, `bottom.openJobs`,
  `bottom.{issuesLoading,issuesError,issuesEmpty,issuesCapped}`, `bottom.sev.{error,warn,info}`. Also the old
  `bottomStub.*` keys are now ORPHANED (StudioBottomPanel no longer uses them) — a convergence cleanup can drop them.
- (O1's `panels.style-voice.*` studio.json keys ARE committed — the panelCatalogContract guideBody gate required them.)

## DECISIONS (S-10-local)
- O4-quality: keep the DOCK-8 hub (QualityHubPanel launcher) — reachability already met; do NOT add a rival
  sidebar list-rail (would duplicate the hub). O2 category stays storyBible/bible-rail (H-1a).

## CONVERGENCE NOTES
- (to append as slices land — esp. any catalog.ts / panel_id enum / studio.json touches for O1.)
