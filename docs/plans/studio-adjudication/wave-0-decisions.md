# Wave 0 — foundations / cross-cutting (X-1..X-10) — adjudicated decisions

> 90 items · 81 DECIDED · 5 not-a-question · 4 deferred · 0 escalated.

> **These are INSTRUCTIONS, not suggestions.** Each was settled by reading source. Do not re-open a
> decided question. Where this contradicts the wave plan, **this file wins.**

---

## Deferred (tracked, non-blocking)

### Q-30-OOS-AGENT-HOOKS
DEFER — confirmed 0% built and confirmed genuinely out of plan 30's scope. Builder instruction: (1) Do NOT build any part of spec 10 in waves 1–8. (2) Do NOT delete or retire `docs/specs/2026-07-01-writing-studio/10_agent_lifecycle_hooks.md` or `design-drafts/screens/studio/screen-studio-agent-hooks.html` — they are the seed for its own future spec+plan. (3) Add the defer row below to `docs/deferred/DEFERRED.md` AND keep the §7 "Consciously OUT OF SCOPE" row in plan 30 (line 486) so it stops re-surfacing. (4) Two leak points must be treated as NO-OPS during this build: `08_studio_state_architecture.md:278` lists `hook_audit`/`hook_progress` SSE as Optional-from-#10 — do not emit, consume, or stub them (zero grep hits today; adding a dead enum value would breach the closed-set/no-silent-no-op discipline); `09_agent_gui_reconciliation.md:44` describes future hook ordering — `StudioEffectReconciler` stays the SOLE GUI refresh path per spec 10's own PO rule D27–D30, so no wave needs a hook seam. (5) When it is eventually built, it MUST follow `docs/standards/agent-extensibility.md` (storage→resolver→degrade-safe-consumer→live-E2E; quarantine+scan+SSRF for every external source; enum-closed-set capability args) — it is a multi-tenant arbitrary-code-execution boundary, not a settings toggle. Note for PO (veto-able default): I am NOT escalating this because the spec set already answers it three times over (spec 10 §'Not in scope' + plan 30 §7 + spec 30's own GG-1 law, which only governs capabilities that EXIST); nothing here is a product/taste call.

**Defer row:** | **D-STUDIO-10-AGENT-HOOKS** | Origin: plan 30 QC gate (Q-30-OOS-AGENT-HOOKS), pre-Wave-1 | **Spec 10 (agent lifecycle hooks) is 0% BUILT** — no `agent-hook-runner` sandbox service, no `agent_hook_bundles` table, no HookOrchestrator, no `.loreweave/hooks.json` manifest format, no settings UI, no `preToolUse`/`postToolUse` events. Verified 0 grep hits across services/, frontend/src, infra/, contracts/ at HEAD 9262ed53e. The single biggest unbuilt block in specs 00–11. **Not a tool↔GUI gap** (plan 30's GG-1 law governs capabilities that exist and lack a surface; here the capability itself does not exist), so it is outside plan 30's scope entirely — it is not deferred *within* the plan, it is *not in* the plan. | **Gate #2 — large/structural**: needs its own spec + plan. It is an XL multi-tenant **arbitrary-code-execution security boundary** (server-side sandbox running user-authored scripts), touching a new service, a new table, a new manifest contract, and a settings surface. Must be built to `docs/standards/agent-extensibility.md` (quarantine+scan+SSRF on external sources; enum-closed-set capability args; no-silent-no-op). Not gate #4 — it is buildable in this repo, just not here. | Target: **its own spec+plan track, after plan 30's waves 1–8 close.** Seed artifacts already on disk: `docs/specs/2026-07-01-writing-studio/10_agent_lifecycle_hooks.md` (488 lines, design-only) + `design-drafts/screens/studio/screen-studio-agent-hooks.html`. Prereqs per spec 10:24 — #09 reconciler + story 04 BE. **Constraint on waves 1–8:** `hook_audit`/`hook_progress` SSE (08:278) and hook ordering (09:44) stay NO-OPS — do not stub, do not add dead enum values; `StudioEffectReconciler` remains the sole GUI refresh path (D27–D30). |

### Q-30-OOS-ARC-DECOMPILER
CONFIRM the plan's out-of-scope call: do NOT build the arc decompiler in Waves 1-8. It gets its own spec (26-D3), written after Wave 2 (G-ARC-SPEC-CRUD) lands the arc CRUD/inspector surface it must mint into. Builder instruction for THIS plan: touch nothing. Specifically do not "improve" the PH21 empty state to hide the missing arc step — it is already correct and honest.

THREE CORRECTIONS the row must carry, because the question as filed is partly wrong:

(1) The stated "where it bites" is FALSE and must not be propagated. "Every arc/plan panel is empty for an imported book" is not true: the SCENE decompiler is shipped AND GUI-reachable (PlanEmptyState.tsx -> useExtractPlan.ts -> materializeScenes(), the EDIT-gated /v1 mirror of materialize-scenes). It mints chapter + scene outline_nodes which render in the shipped UNASSIGNED strip (RUN-STATE A2, 774f51692). Only the ARC RAIL is empty, and it is empty *truthfully* — the book has no arcs. The UI says so in plain words and names the next action (studio.json:1136: "Grouping them into arcs is a separate AI step — ask the agent for it. Until then the extracted chapters sit in the Unassigned strip."). So there is NO dead button, NO silent-success, and NO GG-1 breach. That honesty is precisely what makes this defer legitimate instead of lazy — an existing capability has its human surface; an absent one declares its absence.

(2) The gap is REAL but it is an UNBUILT FEATURE, not a tool<->GUI gap — so it is correctly outside plan 30's scope (plan 30 audits tools vs GUI surfaces; here the tool itself does not exist). composition_arc_import_analyze mints a reusable arc_template (source='imported'), NOT a structure_node — a different feature (template import), not the decompiler. Nothing in the repo produces structure_node(source='decompiled').

(3) The "real design decision (Tier-W mint semantics)" cited as a blocker is ALREADY HALF-SEALED — the future spec must not re-litigate it. BPS-9 (PO-decided 2026-07-10) + 23-BA14 + 26-IX-17 already fix the semantics: the decompiler PROPOSES volume-aligned arc boundaries (boundary_hint: volume|content) through the existing Tier-W propose->confirm gate; a human approves or redraws; silent inference stays forbidden (DA-12). What remains is engineering, not a product call.

SCOPE THE FUTURE SPEC (26-D3) SHOULD COVER — pre-scoped here so it is cheap to write: (a) a new LLM arc-mining engine over the book's own scene nodes/prose, a sibling of engine/motif_deconstruct.py, that emits a PROPOSAL (not a write); (b) confirm-effect mints structure_node rows with source='decompiled' and arc_template_id NULL — schema is ALREADY READY, no migration needed (migrate.py:1212 + CHECK at 1219-1221 already admit 'decompiled'); (c) re-parents the UNASSIGNED outline_nodes onto the minted arcs; (d) a cost-gated /v1 propose->confirm trigger (CostConfirmCard pattern), because a human GUI can call neither an internal-token route nor an MCP tool (24 OQ-9); (e) reuse the D1 never-overwrite-authored predicate so a re-run cannot clobber human-authored arcs.

Default I am picking (veto if wrong): the arc decompiler stays AGENT-INITIATED (MCP Tier-W) in v1, with the GUI CTA being the propose->confirm card — not a one-click deterministic button — because unlike materialize-scenes it is a priced LLM step.

**Defer row:** | `D-ARC-DECOMPILER-STRUCTURE-NODE` | Origin: plan 30 §7 (Consciously OUT OF SCOPE) / spec 26-D3 | **What:** nothing mints `structure_node(source='decompiled')`. `composition_arc_import_analyze` mints a reusable `arc_template(source='imported')` (motif_deconstruct.py:25,610-618) — template-import, a DIFFERENT feature. The arc decompiler (mine a book's own prose -> template-less `structure_node`s, `arc_template_id` NULL, Tier-W propose->confirm, IX-17 volume-aligned hints) does not exist. **Gate reason: #2 large/structural** — needs a new LLM mining engine + confirm-mint path + a cost-gated /v1 trigger; size L; its own spec. NOT gate #4 — it is unbuilt work, not blocked. **Blast radius (corrected — the filed claim was wrong):** does NOT empty the Plan Hub. The scene decompiler is shipped + GUI-reachable (`useExtractPlan.ts` -> `/v1` materialize-scenes) and extracted chapters/scenes render in the UNASSIGNED strip; only the arc rail is empty, truthfully, and the empty state says so and names the next action (`studio.json:1136`). No dead button, no silent-success, no GG-1 breach. **Design is half-sealed already** — BPS-9 / 23-BA14 / 26-IX-17 fix propose->confirm + volume-aligned hints; do not re-litigate. **Schema ready, no migration** (`migrate.py:1212`, CHECK `:1219-1221` already admit `'decompiled'`). **Target/trigger:** its own spec (26-D3), authored after Wave 2 (G-ARC-SPEC-CRUD) lands the arc CRUD/inspector surface the decompiler mints into. |

### Q-30-OOS-WIKI-INVERSE-GAP
CONFIRMED REAL, and DEFER out of plan 30 — exactly as plan 30 §7 already recorded ("One row, its own small spec"). Do NOT add wiki tools to any of waves 1-8: they touch composition-service (Python) + the Studio dock; this gap is in glossary-service (Go) MCP, which no wave opens. It blocks nothing.

The row is written as BUILDABLE, not blocked — every REST handler a wiki tool would wrap is already shipped and grant-gated (server.go:415-453). The future spec is a WRAPPER spec, not a design exercise. Scope it as follows so the builder needs no further thought:

TARGET: new spec `docs/specs/2026-07-01-writing-studio/39_wiki_agent_tools.md` (31-38 are taken). Trigger: after Wave 8 closes (i.e. the plan-30 batch is done). Size: S-M.

BUILD SHAPE (all of it is already determined by code):
1. New file `services/glossary-service/internal/api/mcp_wiki_tools.go` exposing `func (s *Server) RegisterWikiTools(srv *mcp.Server)`, called from `mcp_server.go` right beside the existing `s.RegisterBookTools(srv)` (mcp_server.go:59). Do not inline into mcp_server.go — mirror the existing tier-stream split.
2. Each tool delegates to the SAME core the shipped HTTP handler calls (`wiki_handler.go`, `wiki_jobs.go`, `wiki_staleness.go`) — do NOT write a second engine, and do NOT bypass the grant gate the HTTP route applies (that would be the css-var-duplicated-across-two-consumers class + a tenancy defect).
3. Tool set v1 (7 tools, each mapping 1:1 onto a shipped route):
   - wiki_list_articles (TierR/ScopeBook) -> listWikiArticles
   - wiki_get_article (TierR/ScopeBook) -> getWikiArticle
   - wiki_create_article (TierW) -> createWikiArticle
   - wiki_patch_article (TierW) -> patchWikiArticle
   - wiki_generate_stubs (TierW, ASYNC) -> generateWikiStubs
   - wiki_list_staleness (TierR) -> listWikiStaleness
   - wiki_submit_suggestion (TierW) -> submitWikiSuggestion
4. FREE WIN — name the generator with the `wiki_generate` substring: `services/chat-service/app/services/workflow_runner.py:49` ALREADY lists "wiki_generate" in `_ASYNC_JOB_VERBS`, so the async-honesty annotation fires with zero extra work. Still declare `_meta.async` explicitly via `lwmcp.NewToolMeta` (the catalog flag outranks the name heuristic — see workflow_runner.py:13-21).
5. Any closed-set arg (article status/visibility/kind) MUST ship a real JSON-schema `enum` built with `closedSetSchemaFor` AND be registered in `closedSetArgs` in `services/glossary-service/internal/api/mcp_tool_schema_contract_test.go` — a bare string schema turns that test red by design.

DEFAULT THE PO MAY VETO: v1 deliberately does NOT expose `deleteWikiArticle` or `reviewWikiSuggestion` as agent tools. Delete is destructive, and review-suggestion IS the human approval step — handing the agent both sides of the approval loop would invert GG-1 ("the agent is an accelerant on the user's capabilities, never the only door"). The agent proposes; the human approves in the shipped wiki-editor panel.

DoD for that future spec's wave (per the run policy): `go test ./internal/api/...` green including the schema contract test, ai-gateway federation live-smoke showing the new tools in tools/list under the `glossary` namespace, and `/review-impl` at wave completion.

**Defer row:** **D-WIKI-MCP-TOOLS** | origin: plan 30 §7 (GG-2 inverse gap), line 490 | WHAT: glossary-service registers ZERO `wiki_*` MCP tools while the `wiki` + `wiki-editor` Studio panels and ~20 grant-gated wiki REST routes are shipped — the agent cannot read, draft, or improve a wiki article the user owns. | GATE: **#1 out-of-scope** — glossary-service (Go) MCP surface; plan 30's waves 1-8 touch composition-service (Python) + the Studio dock and never open `mcp_server.go`. NOT gate #4: this is fully buildable in-repo (every handler it wraps already exists at server.go:415-453) — it is unbuilt work, not a blocker. Non-blocking: no wave depends on it. | SIZE: S-M | TARGET: new spec `docs/specs/2026-07-01-writing-studio/39_wiki_agent_tools.md`, triggered when the plan-30 batch closes (after Wave 8). | SCOPE: `RegisterWikiTools` in a new `services/glossary-service/internal/api/mcp_wiki_tools.go`, called beside `RegisterBookTools` (mcp_server.go:59); 7 tools (list/get/create/patch articles, generate_stubs [async], list_staleness, submit_suggestion) each delegating to the shipped handler core behind its existing grant gate; closed-set args get `enum`s + a row in `mcp_tool_schema_contract_test.go`; delete + review-suggestion stay human-only.

### Q-30-OOS-PLANFORGE-BLIND-PROPOSE
UPHOLD plan 30 §7: Wave 5 (spec 35, PlanForge Studio) does NOT touch this. Builder instruction: (1) do not add any existing_state work to Wave 5 slices — spec 35 OQ-5 already records it as honoured, leave it; (2) write the defer row below into docs/sessions/SESSION_HANDOFF.md Deferred Items and docs/deferred/DEFERRED.md, then continue. The row is pre-scoped so the future builder needs no fresh design pass except the ONE genuine fork named in it. Scope of the eventual fix (record it in the row so it is not re-derived): (a) new `app/engine/plan_forge/book_state.py::gather_book_state(book_id) -> dict` returning a bounded digest — chapter count + last chapter index (chapters repo), existing structure/outline nodes (db/repositories/structure.py, outline.py), cast names (glossary), and any prior compiled spec's arc ids; (b) thread it: plan_forge_service._enqueue_propose (plan_forge_service.py:227 already puts book_id in pipe_input) → worker/operations.py:607 run_plan_forge_propose (which today reads only `source_markdown` and drops the book_id it is handed) → propose_spec_llm_async(source_markdown, client, book_state=...) (propose_llm_async.py:86) → a new BOOK STATE block in the ANALYZE prompt (app/engine/plan_forge/prompts.py); rules-mode propose_spec (propose.py:412) gets the digest too but only to emit honest `meta.existing_state` + open_questions — it must NOT invent from it (the file's own "absent != invented" law); (c) the dedupe checksum at plan_forge_service.py:167 MUST become sha256(source_markdown + state_digest_hash), or a re-propose after the book grows silently returns the old blind spec; (d) VERIFY is an eval, not a unit test — run app/engine/plan_forge/eval_fidelity.py on a >100-chapter book before/after. THE ONE DESIGN FORK the future spec must settle (do not guess it at 3am): does a propose against a book with existing chapters EXTEND (mint arcs/chapters numbered after the existing tail) or RE-PLAN (and what becomes of the already-linked nodes)? This changes link_outline_skeleton's numbering semantics (plan_link_service.py:295), which is exactly why it is not a Wave-5-sized edit. Sane default to propose in that spec (PO may veto): EXTEND — blind RE-PLAN over 200 linked chapters is the destructive branch. NOT a CRITICAL blocker today: link_outline_skeleton preserves human-edited nodes via prior_versions (plan_forge_service.py:1276-1285), so the failure mode is a wrong plan, not data loss.

**Defer row:** D-PLANFORGE-BLIND-PROPOSE — origin: plan 30 §7 OOS / spec 21-G2 / spec 35 OQ-5. WHAT: PlanForge propose is blind to book state — `propose_spec(doc)` (propose.py:412) and `propose_spec_llm_async(source_markdown, client)` (propose_llm_async.py:86) take only the braindump; the worker op is handed `book_id` (plan_forge_service.py:227) and never reads it (operations.py:607-622), so proposing a plan for a book with 200 written chapters ignores all of them and produces a plan for chapter 1. GATE: #2 large/structural (+#1 out-of-scope of the GUI-gap plan) — the fix needs a new book_state gatherer, a 4-layer thread-through, a change to the propose dedupe checksum (plan_forge_service.py:167, today sha256(source_markdown) only), a prompt change, an eval_fidelity run on a long book, AND it forces a design fork (EXTEND vs RE-PLAN, which changes link_outline_skeleton numbering semantics, plan_link_service.py:295). Not a GUI gap; not a Wave 5 item. Size M-L. TARGET: its own spec — "PlanForge propose against an existing manuscript" — scheduled after the 8 waves of plan 30 close, alongside spec 26-D3 (arc decompiler), which shares the same "book already exists, plan does not" surface. TRIGGER: whichever comes first — plan 30 Wave 8 close-out, or the first user report of a PlanForge propose on a book with >0 linked chapters. NOT CRITICAL: linker preserves human-edited nodes (prior_versions), so today's failure mode is a wrong plan, not data loss.

## Decisions

### Q-30-X1-ADDMODELCTA-DOCK7
Take the shared-component fix exactly as the spec's candidate states it. The whole resolver chain the fix needs ALREADY EXISTS and is proven by the StepConfig.tsx precedent — nothing to build but the branch itself. Builder instruction (single file + single test file, ~8 call sites untouched):

1) `frontend/src/components/shared/AddModelCta.tsx` — add two imports:
   `import { useOptionalStudioHost } from '@/features/studio/host/StudioHostProvider';`
   `import { followStudioLink } from '@/features/studio/host/studioLinks';`
   Inside the component (currently line 33-37, which computes `to = '/settings/providers?return=' + encodeURIComponent(back)`), call `const studioHost = useOptionalStudioHost();` and branch BEFORE the two `<Link>` returns:
   - **studio branch** (`studioHost !== null`): render a `<button type="button">` carrying the SAME `cn(...)` classes as the corresponding variant (so `variant: 'button' | 'link'` styling is preserved), with
     `onClick={() => followStudioLink(REGISTRATION_PATH, studioHost, { bookId: studioHost.bookId })}`.
     Pass the BARE `REGISTRATION_PATH` (`/settings/providers`), **not** `to` — do NOT append `?return=`. Rationale from code: `resolveStudioLink` (studioLinks.ts:76) strips the query before matching, and `SETTINGS_RE` (studioLinks.ts:110-111) resolves `/settings/providers` → `openPanel('settings', { tab: 'providers' })`; `SettingsPanel.tsx:35-38` reads `params.tab` and `'providers'` is a valid `SettingsTabId` (features/settings/tabs.ts:26). The return-path round-trip is MEANINGLESS in the studio — the dock never navigates away, the caller's panel stays mounted, so there is nothing to come back from. (`ProvidersTab.tsx:46` only honors `?return=` on the classic route, which the non-studio branch keeps.)
   - **fallback branch** (host null): keep the EXISTING `<Link to={to}>` for both variants verbatim, `useLocation()`-derived `?return=` intact. `useLocation()` stays safe in the studio (panels mount under the `/books/:id/studio` route), so no need to guard it.
   Mirror the DOCK-7 comment style of StepConfig.tsx:41-44.

2) Do NOT touch the ~8 call sites (`ModelPicker.tsx:388`, `CompositionPanel.tsx:514`, `BuildGraphDialog.tsx:647`, `EmbeddingModelPicker.tsx:97`, `RerankModelPicker.tsx:58`, `DefaultModelsCard.tsx:50`, + the two picker re-exports). They inherit the fix. This is the point of the shared-component fix: every future BYOK/model-picker panel (Motif Mine, Conformance Run, Arc Import, every `plan_*` pass) gets DOCK-7 safety for free.

3) Test: extend `frontend/src/components/shared/__tests__/AddModelCta.test.tsx` (it currently asserts only the `<Link>` href, via `screen.getByRole('link')`). Add a studio case: wrap in `<MemoryRouter><StudioHostProvider bookId="b1">…`, assert `screen.queryByRole('link')` is NULL and `getByRole('button')` exists, then click it and assert the host's `openPanel` was called with `('settings', expect.objectContaining({ params: { tab: 'providers' } }))` — spy by mocking `useOptionalStudioHost` OR by asserting on a `_dockApiRef`-injected fake `addPanel`. This is the "no-silent-no-op / verify by EFFECT" discipline: assert the PANEL OPENS, not merely that a button rendered.

Ordering note for the builder: this is a Wave-0 hard gate — land it BEFORE any new panel that renders a model picker's empty state, or every such panel ships a layout-nuking link.

*Evidence:* frontend/src/components/shared/AddModelCta.tsx:33-68 — raw `<Link to={to}>` in BOTH variants, zero `useOptionalStudioHost()` (confirms the DOCK-7 defect). The precedent + every dependency already exist: frontend/src/features/glossary-translate/StepConfig.tsx:44 + :154-163 (`studioHost ? <button onClick={() => followStudioLink(SETTINGS_PROVIDERS_LINK, studioHost, { bookId: studioHost.bookId })}> : <Link to={SETTINGS_PROVIDERS_LINK}>`); frontend/src/features/studio/host/studioLinks.ts:110-111 (`SETTINGS_RE` → `openPanel('settings', { tab: settings[1] })`) and :76 (query stripped before match, so `?return=` is inert in studio); frontend/src/features/studio/host/StudioHostProvider.tsx:143-145 (`useOptionalStudioHost` returns null outside the provider, documented for exactly this DOCK-7 case); frontend/src/features/studio/panels/SettingsPanel.tsx:35-38 (consumes `params.tab`); frontend/src/features/settings/tabs.ts:26 (`'providers'` is a valid SettingsTabId). Call sites that inherit the fix: ModelPicker.tsx:388, CompositionPanel.tsx:514, BuildGraphDialog.tsx:647, EmbeddingModelPicker.tsx:97, RerankModelPicker.tsx:58, DefaultModelsCard.tsx:50.

### Q-30-X3-GUIDEBODYKEY-UNGUARDED
Add the guard — but as TWO assertions, not one. The spec's proposed `OPENABLE_STUDIO_PANELS.every(p => !!p.guideBodyKey)` is necessary but NOT sufficient: `UserGuidePanel.tsx:120` renders `t(p.guideBodyKey ?? p.descKey, { defaultValue: '' })`, so a key declared with no copy behind it still renders a silently blank guide row — which is exactly the "silently missing User-Guide copy" the item is trying to prevent. Code proves this is already live: 4 panels (quality-promises, quality-critic, quality-coverage, quality-canon, catalog.ts:267-270) DO declare a guideBodyKey but have NO `guideBody` string in `en/studio.json` (vi/ja DO have it — English is the drifted locale), so English users see 4 blank rows today. A key-only assertion would go green while those stay broken and let the 14 new Wave-0 panels ship the same way.

BUILDER INSTRUCTIONS (Wave 0, 3 files):

(1) `frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts` — after the existing `'every palette-openable panel has a category (#18 domain grouping)'` test (line 38-42), which is the exact pattern to mirror, add:

```ts
// X-3 — every palette-openable panel must (a) declare a guideBodyKey and (b) have real English
// copy behind it. UserGuidePanel renders t(p.guideBodyKey ?? p.descKey, { defaultValue: '' })
// (UserGuidePanel.tsx:120), so a missing key OR missing copy renders a SILENTLY EMPTY guide row.
const enStudio = JSON.parse(
  readFileSync(resolve(process.cwd(), 'src/i18n/locales/en/studio.json'), 'utf-8'),
);
const lookupEn = (key: string): unknown =>
  key.split('.').reduce<any>((o, k) => (o == null ? undefined : o[k]), enStudio);

it('every palette-openable panel declares a guideBodyKey (#19 User Guide)', () => {
  const missing = OPENABLE_STUDIO_PANELS.filter((p) => !p.guideBodyKey).map((p) => p.id);
  expect(missing).toEqual([]);
});

it('every guideBodyKey resolves to non-empty English copy (no blank guide row)', () => {
  const empty = OPENABLE_STUDIO_PANELS.filter((p) => {
    const v = p.guideBodyKey ? lookupEn(p.guideBodyKey) : undefined;
    return typeof v !== 'string' || v.trim() === '';
  }).map((p) => p.id);
  expect(empty).toEqual([]);
});
```
(`readFileSync`/`resolve` are already imported at the top of the file; vitest cwd is `frontend/`, same base the existing `'../contracts/frontend-tools.contract.json'` read relies on.)

(2) `frontend/src/features/studio/panels/catalog.ts:258` — backfill agent-mode's key: add `guideBodyKey: 'panels.agent-mode.guideBody'` to the `{ id: 'agent-mode', ... category: 'editor' }` row.

(3) `frontend/src/i18n/locales/en/studio.json` — add FIVE `guideBody` strings under `panels.*`: `agent-mode` (new) plus the four already-declared-but-uncopied `quality-promises`, `quality-critic`, `quality-coverage`, `quality-canon`. Write 1-2 sentences each in the voice of the existing `panels.quality.guideBody`. Do NOT touch the other 17 locales — `fallbackLng: 'en'` (i18n/index.ts:48) covers them; optionally propagate later via `scripts/i18n_translate.py`.

WAVE-0 DEFINITION OF DONE (add as a literal line): each of the 14 new panels lands its `guideBodyKey` in catalog.ts AND its `panels.<id>.guideBody` string in `en/studio.json` in the same slice — the two new tests above red otherwise. Do not create a separate studio.json parity test (none exists; out of scope).

*Evidence:* frontend/src/features/studio/panels/catalog.ts:258 — `{ id: 'agent-mode', component: AgentModePanel, titleKey: 'panels.agent-mode.title', descKey: 'panels.agent-mode.desc', category: 'editor' }` — no guideBodyKey; a scan of all catalog rows confirms it is the ONLY non-hiddenFromPalette panel missing one. frontend/src/features/studio/panels/UserGuidePanel.tsx:120 — `{t(p.guideBodyKey ?? p.descKey, { defaultValue: '' })}` — a missing key/copy renders empty, not a warning. frontend/src/i18n/locales/en/studio.json — `panels.quality-promises|quality-critic|quality-coverage|quality-canon` have `title`+`desc` but NO `guideBody`, while catalog.ts:267-270 declare `guideBodyKey` for all four (vi/ja studio.json DO carry the copy → English is the drifted SSOT). frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts:38-42 — the `!p.category` guard is the exact assertion shape to mirror. frontend/src/i18n/index.ts:48 — `fallbackLng: 'en'`.

### Q-30-SEC11-VS-SEC0-CONTRADICTION
§0 SEALED wins. §11 is stale prose and ALL THREE of its "blocking" decisions are already made — including the X-12 sub-question, which the CODE settles (contrary to the spec's own candidate answer). Builder action, mechanical:

**EDIT `docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md` §11 (lines 768-789).** Delete item 1 ("PO decisions (3, all blocking)", lines 772-782) in its entirety and replace with:

> **1. PO decisions — ALL SEALED (§0). Nothing below blocks. Do NOT re-litigate; re-read §0.**
> - **(a) X-5** → **PO-3**: RETIRE `ui_show_panel`, fold into `ui_open_studio_panel`. It is a cross-surface migration, not a delete — the non-studio resolver at `frontend/src/features/chat/nav/uiNav.ts:115` must keep working (migrate it to `ui_open_studio_panel` + the studio interceptor, or give it an explicit non-studio path); land with `test_frontend_tools_contract.py` + `panelCatalogContract.test.ts` green. Separately: `ui_watch_job` → add to `STUDIO_UI_TOOLS` + the interceptor → open `job-detail`.
> - **(a′) X-12** → **NOT a PO decision — ANSWERED, and its premise is REFUTED by the code: do NOT add a `params` arg to `ui_open_studio_panel`; it keeps `panel_id` (bare id) only.** Grounds: (i) `quality-canon` sits INSIDE the `panel_id` enum (`services/chat-service/app/services/frontend_tools.py:402`) while `QualityCanonPanel.tsx:33` already reads `props.params as CanonFocusParams` — a panel can take params from an FE deep-link AND be agent-openable; (ii) §8.0 check 5 (lines 576-579): all 14 new panels are bare-id openable, ZERO need `hiddenFromPalette`; (iii) spec `32_arc_inspector.md:524` (AI-1/OQ-6) says it explicitly. **Also amend §8.2's X-12 row (lines 649-656)** from "Decide this in Wave 0, alongside X-5" to: *"REFUTED — precedents: `scene-inspector` (bus) and `quality-canon` (`props.params`, QualityCanonPanel.tsx:33) are both in the enum. `ui_open_studio_panel` keeps `panel_id` only; every panel in this batch is bare-id openable. No contract change."*
> - **(b) AN-12** → **PO-1**: AMENDED, Wave 7 proceeds (bottom-panel Issues tab + right-click lens, no new dock panel). Write the amendment INTO `28_agent_native_studio.md`.
> - **(c) Track C P-5** → **PO-2**: workflows + mode-binding UI (**8c**) = **Track C's**. **Wave 8 = 8a (KG write holes) + 8b (world container + world-map) and 8b STAYS IN THIS PLAN** — PO-2's consequence sentence, line 20, and spec `38_kg_and_world.md` is on disk per PO-4. ⚠ **Hand Track C this note** (mirror of the paragraph PO-2 hands them for G-WORKFLOWS): *"the `world` container + `world-map` FE surfaces (your P-5 'W10 world container') are OWNED BY plan 30 Wave 8b, specced in 38_kg_and_world.md. Drop W10 from P-5."*

Also update the §11 preamble: "Immediately, before any code:" → since PO-4's specs 31-38 are all written and on disk, the first real action is now item 2 (write the AN-12 `resource_ref` section, X-6) then item 3 (land Wave 0). Renumber accordingly.

**Default I am picking (PO may veto):** on (c), plan 30 owns the world container because its spec is written and PO-approved while Track C's W10 is explicitly parked-and-undesigned at gate #2 (`docs/plans/2026-07-12-track-c-completion-RUN-STATE.md:212`: "each is a real product surface with its own design"). Specced beats parked.

**Do NOT fold X-13 into this.** X-13 (`consumer_capabilities` / `contributeContext()`, §8.2 lines 657-663) is genuinely still open and is raised as an escalation by `37_issues_feed.md:697` (OQ-5). It is a different question — it must not be swept away with §11's stale rows.

*Evidence:* SEALED: 30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:19 (PO-1/AN-12), :20 (PO-2 — "Wave 8 loses 8c. Wave 8 = KG write holes + world maps only"), :21 (PO-3 — retire ui_show_panel), :22 (PO-4). STALE: same file :772-782 (§11 item 1). X-12 REFUTED IN CODE: services/chat-service/app/services/frontend_tools.py:399-402 (ui_open_studio_panel schema = `panel_id` enum ONLY, and `quality-canon` is in it) vs frontend/src/features/studio/panels/QualityCanonPanel.tsx:33 (`props.params as CanonFocusParams` on that same in-enum panel) — a params-taking panel IS agent-openable; corroborated by 30_…PLAN.md:576-579 (§8.0 check 5, "X-12 does not bite this batch") and 32_arc_inspector.md:524 (AI-1/OQ-6, "REFUTED by this spec"). Track C W10 collision: docs/plans/2026-07-12-track-c-completion-RUN-STATE.md:212 ("P-5 … W10 world container" — Gate #2, parked, undesigned) vs docs/specs/2026-07-01-writing-studio/38_kg_and_world.md (written, PO-4-approved). ui_show_panel non-studio call site to migrate: frontend/src/features/chat/nav/uiNav.ts:115.

### Q-30-BE12-STRUCTURE-TEMPLATE-AUTHORING
**v1 = READ-ONLY. SKIP BE-12.** (This is the default I am picking — spec 36 already recommends it in writing at 36_editor_craft_ports.md:276/690; PO may veto, but nothing in §0's sealed PO-1..4 conflicts, and nobody has asked for custom structures.) Wave 6 stays **M**, not L.

WHY THE CODE SETTLES THE COST (not just taste): the pipeline consumes ONLY `tmpl.beats` + `tmpl.name` (plan.py:536,563,593,627); `structure_template.kind` is read by no branch (plan_forge_service.py:1327 says so explicitly). So BE-12's 3 routes are the CHEAP part — the expensive part is the thing nobody costed: a **beats-array authoring GUI** (an ordered list of {key,label,purpose,order} objects, 15 of them for Save the Cat — migrate.py:1631-1646) plus a clone-to-user tenancy design + review. That is a panel, not a slice. It is CLAUDE.md defer-gate #2 (large/structural), not gate #4 — it is buildable, we are consciously not building it in v1.

BUILDER INSTRUCTION for Wave 6 / G-STORY-STRUCTURE (spec 36):
1. **Do NOT touch `structure_templates.py`.** No POST/PATCH/DELETE on `/templates`. No new repo methods. The only backend work for G-STORY-STRUCTURE is BE-20 (cost-gated `composition_decompose`, spec 36:438) — which is unrelated to authoring and stays in scope.
2. **The picker is a read-only list of the 6 System-tier built-ins**, sourced from the ALREADY-SHIPPED `GET /templates` (canon.py:192) via the ALREADY-SHIPPED FE call `frontend/src/features/composition/api.ts:270` (`listTemplates`). Reuse that function — do not write a second fetcher.
3. **NO dangling CTA.** The picker must NOT render a "＋ New template" / "Save as my template" button — not even disabled. This plan's own §3.2 G-IMPORT-DECONSTRUCT row (30:264) flags exactly this bug class shipped (`ArcTemplateLibraryView.tsx:51` advertises a flow with no entry point). Per EC-5a, render an honest empty affordance: a one-line note under the list — "Custom story structures are not available yet" — and nothing clickable. i18n key it; no `disabled` button with no explanation.
4. **`active_template_id` is the one home of the book's structure** (EC-5, spec 36:275): the Composition section of `book-settings` sets it; the decompose action defaults to it and writes it back on commit; the Beats facet reads it. `structure_template_id` stays on the decompose request body as a per-run override. This closes the stored-but-unread column WITHOUT needing authoring.
5. **Fix the lie in the schema comment** (cheap, do it in the same slice): `migrate.py:178` currently says "global built-ins + user-custom" — a table comment advertising a tier no code can write is the repo's own `silent-success-is-a-bug` class. Change to: `-- structure_template: story-structure library. System-tier built-ins ONLY (owner_user_id IS NULL). The owner_user_id column is reserved for D-STRUCTURE-TEMPLATE-AUTHORING (BE-12, deferred v2) — NO write path exists; do not assume one.` Leave the column and the `owner_user_id = $1` clause in `list_for_user` in place — they are the forward seam, and removing them costs a migration later for zero gain today.
6. Wave-6 DoD unchanged: `/review-impl` runs at wave close.

WHEN BE-12 IS EVENTUALLY BUILT (v2 — bind the future builder now so the tenancy is not re-litigated): the 6 built-ins are System tier (`owner_user_id IS NULL`, migrate.py:180). A regular user **CLONES** (`POST /templates/{id}/clone` → INSERT with `owner_user_id = caller`), and may PATCH/DELETE **only** rows where `owner_user_id = caller`. A user must NEVER mutate an `owner_user_id IS NULL` row — that is verbatim the `entity_kinds` global-row bug CLAUDE.md's User Boundaries section was written to kill. `get()` already refuses cross-user reads correctly (structure_templates.py:43-51) — mirror that gate on every write.

*Evidence:* services/composition-service/app/db/repositories/structure_templates.py:31,43 — ONLY `list_for_user` + `get` exist; docstring: "Read-only in V0 (custom-template authoring is a later surface)". services/composition-service/app/routers/canon.py:192 — `GET /templates` is the sole route (no POST/PATCH/DELETE anywhere in the service). services/composition-service/app/db/migrate.py:179-187 (schema: owner_user_id nullable = System tier; beats JSONB) + :1628-1646 (6 built-ins seeded, 15-beat objects). services/composition-service/app/routers/plan.py:536,563,593-594,627 — the decompose/plan pipeline consumes ONLY `tmpl.beats` and `tmpl.name`; services/composition-service/app/services/plan_forge_service.py:1327 confirms `structure_template.kind` steers nothing. frontend/src/features/composition/api.ts:270 — `GET /templates` FE client already shipped. Prior written recommendation: docs/specs/2026-07-01-writing-studio/36_editor_craft_ports.md:276 (EC-5a), :441 (BE-12), :690 (OQ-1 "Defer"), :705 (defer row).

### Q-30-BE15-WORLDMAP-UPDATE-SEMANTICS
**Take candidate 1 — real PATCH routes with stable ids. Delete+recreate is REJECTED.** The design is already written at build detail in `38_kg_and_world.md` §3.3.1 + §4.2 (BE-15a…m); this adjudication RATIFIES it — do not re-design, and do not treat "UPDATE exists at no layer" as a blocker (it is unbuilt work, CLAUDE.md anti-laziness rule). Concrete instruction for the builder, grounded in the code:

1. **Migration** (`services/book-service/internal/migrate/migrate.go`, forward-only + idempotent, next to the world_maps block at :401-434):
   `ALTER TABLE world_maps ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1;`
   `ALTER TABLE map_markers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();`
   `ALTER TABLE map_regions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();`
   (`world_maps.updated_at` already exists — `migrate.go:410`. Defaults must be right first time: ADD COLUMN IF NOT EXISTS never revisits a bad default.)

2. **Three PATCH routes**, new file `services/book-service/internal/api/maps.go`, mounted inside the existing `r.Route("/v1/worlds", …)` at `server.go:381` (add a **static** `r.Route("/maps", …)` sibling of `r.Route("/{world_id}", …)` — chi gives static segments precedence over params, so `/v1/worlds/maps/{map_id}` and `/v1/worlds/{world_id}` coexist). Gateway needs ZERO changes: `worldsProxy` already forwards anything under `/v1/worlds` (`gateway-setup.ts:90,592`).
   - `PATCH /v1/worlds/maps/{map_id}` `{name?}` — **If-Match OCC**: 428 without the header, 412 + the current map body on mismatch, bump `version` and `updated_at=now()` on success.
   - `PATCH /v1/worlds/maps/{map_id}/markers/{marker_id}` `{label?,x?,y?,marker_type?,entity_id?}` — **no OCC, last-write-wins** (a drag is a continuous gesture; OCC produces a 412 storm and self-conflicts on the 2nd rapid edit — `instant-commit-control-over-occ-entity-needs-write-serialization`). FE serializes+debounces per marker id and must bind the debounced save to WHICH marker (`debounced-write-must-bind-its-target-entity`).
   - `PATCH /v1/worlds/maps/{map_id}/regions/{region_id}` `{name?,polygon?,entity_id?}` — same, `polygon` replace-whole (≥3 pts, each in [0,1]).

3. **Partial semantics — reuse the shipped pattern, don't invent one:** decode into `map[string]any` and build SET clauses by key presence, exactly as `patchWorld` does at `worlds.go:270-293` (absent key = unchanged; an explicit `null` on `entity_id`/`marker_type` = CLEAR, which the `map[string]any` decode expresses and a typed struct with `omitempty` cannot). Re-validate coords `[0,1]` and polygon ≥3 points server-side (mirror `mcp_maps.go:155,199-206`).

4. **Scope gate on every child route — this is the tenancy-critical bit.** Verify BOTH `world_maps.owner_user_id == caller` AND `marker.map_id == {map_id}` in ONE statement, mirroring the existing delete: `UPDATE map_markers m SET … FROM world_maps wm WHERE m.id=$1 AND m.map_id=$2 AND m.map_id=wm.id AND wm.owner_user_id=$3` — `RowsAffected()==0` ⇒ uniform 404 "marker not found" (no cross-owner existence oracle). A marker from another map addressed under YOUR map id must 404, not patch (`gate-must-derive-scope-from-the-loaded-row`). Go test required for both: foreign map ⇒ 404, and foreign marker under an owned map id ⇒ 404, identical body.

5. **⚠ Cost the builder must know: book-service has NO If-Match implementation anywhere today** — the only mention in the service is `chapter_reorder.go:16`, a comment explaining why it deliberately does NOT need one. So BE-15d writes book-service's FIRST OCC handler (~30 LOC). Mirror knowledge-service's contract exactly (428 no-header / 412 + current body — `entities.py:1035`); the 412 body IS the FE's new baseline (never re-GET, never blind-retry). **PO default I am setting so this does not stall: keep the If-Match on rename only.** If the PO would rather ship rename as last-write-wins too and drop `version` entirely, that is a 1-line veto — but rename is rare, human-paced and genuinely conflict-worthy across devices, so OCC there is the right call and it is the only place it costs anything.

6. **`updated_at` must be READ or it is a write-only column (banned):** every PATCH sets `updated_at=now()`; BE-15c returns it per marker/region; the `world-map` inspector renders "edited 4m ago". A Go test asserts the timestamp ADVANCES across a PATCH — that is also the only thing that proves the drag-PATCH landed rather than merely repainting optimistic state.

7. **BE-15m, same slice, non-negotiable:** add 3 MCP tools in `mcp_maps.go` — `world_map_update` / `world_map_update_marker` / `world_map_update_region`, Tier-A, reversible (inverse patch with prior values, stated in the description as the existing 8 do), reusing the same SQL. Without them Wave 8b CREATES a fresh GG-2 inverse gap: the human could move a pin and the agent could not. Register the `world_map_*` effect handler in `frontend/src/features/studio/agent/handlers/worldEffects.ts` (one file, per plan 30 §8.0b) with a **RegExp** (the string branch is `tool === p || startsWith(p)` and would silently no-op on alternation).

Rejection rationale for candidate 2 (delete+recreate), for the record: it churns ids (breaking inspector selection, deep links and the agent's undo hint), it is non-atomic across two HTTP calls (DELETE succeeds → POST fails ⇒ the user's pin is GONE), it is an unbounded write storm under a drag, and it reorders the render set (both children sort by `created_at` — `mcp_maps.go:280,303`). It also does NOT actually break glossary entity links (`entity_id` is a soft nullable UUID, not an FK — `migrate.go:417,431`), so the plan's stated reason is slightly wrong; it is rejected on the four reasons above, which are stronger.

*Evidence:* services/book-service/internal/api/mcp_maps.go:431-433 (the owner-scoped `DELETE … USING world_maps wm WHERE m.id=$1 AND m.map_id=wm.id AND wm.owner_user_id=$2` — the exact join the UPDATE mirrors) · migrate.go:401-434 (world_maps/map_markers/map_regions: CASCADE, relative [0,1] coords, `entity_id` is a SOFT nullable UUID with no FK, `world_maps.updated_at` already present, no `version` anywhere) · worlds.go:260-300 (`patchWorld` — the shipped `map[string]any` partial-decode + dynamic SET pattern to copy) · server.go:381-392 (the `/v1/worlds` chi mount to extend) · server.go:200 (the internal-only `?user_id` image route to lift into a public JWT sibling) · chapter_reorder.go:16 (proof book-service has NO If-Match/version precedent — BE-15d is its first) · api-gateway-bff/src/gateway-setup.ts:90,592 (worldsProxy already forwards `/v1/worlds*` ⇒ zero gateway change) · docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:240-254, 295-318 (the PATCH design + migration + BE-15m, already written at build detail)

### Q-30-WAVE8B-WORLD-OWNERSHIP
**THIS PLAN TAKES OVER THE `world` CONTAINER. Wave 8b (spec 38) owns it. This adjudication IS the "explicit ownership handoff in writing" that §9 demands — Wave 8b is UNBLOCKED; Wave 8c stays dropped (PO-2).**

Grounding: PO-2 is SEALED and its consequence clause already retained 8b in writing — "Wave 8 loses 8c. Wave 8 = KG write holes **+ world maps only**". The candidate answer "Track C keeps it" contradicts a §0 sealed row and is wrong by construction. The collision is nominal: Track C's "W10 world container" is a **workflow RAIL/journey** ("Worldbuilding-first world container" — prose-less lore/graph/map authoring), not a dock panel; it has zero code, zero design, is PARKED at Gate #2, and its own audit says "no files". Spec 38 §3.2 designs the panel at BUILD DETAIL. Track C is the **consumer** of this panel, not its producer.

**Concrete builder instructions (do these in Wave 8b, slice 8b-part-1, before any panel code):**

1. **Build the `world` panel per spec 38 §3.2 exactly as written** — id `world`, category `storyBible` (do NOT add a new `world` category; `CATEGORY_ORDER` is missing `'quality'` per X-2 and a new group sorts to the top via `indexOf → -1`), palette-visible, `guideBodyKey` required, **self-resolving** from the book row's `world_id` (mirroring how `kg-overview` resolves via `useBookKnowledgeProject`). Because it is self-resolving it is openable by a BARE ID ⇒ register it in the `ui_open_studio_panel` enum, the Command Palette, and the User Guide. This is also the answer to X-12: self-resolve, do NOT mark it `hiddenFromPalette`.
   - Files: `frontend/src/features/studio/panels/catalog.ts` (new row), the new panel component, `services/chat-service/app/services/frontend_tools.py` (`panel_id` enum — closed-set arg, per the Frontend-Tool Contract), `contracts/frontend-tools.contract.json` (regen: `WRITE_FRONTEND_CONTRACT=1 pytest`).
   - Render the 3 empty states of §3.2 (book-in-no-world ⇒ "Link this book to a world" control, NOT a route hop; foreign world ⇒ the uniform no-oracle card; world-with-no-maps ⇒ Maps empty state + `+ New map`). A blank panel after `shown:true` is the silent-success bug class.
   - `studioLinks.ts` is a **3-file** change, not one line (§3.2): add `worldId?: string` to `StudioLinkContext` + `WORLD_RE`, resolve to `openPanel('world')` ONLY when `ctx.worldId && id === ctx.worldId` (absent ⇒ fall through to `external` = today's behaviour, degrade-safe); pass `{ bookId: host.bookId, worldId }` at `KgOverviewPanel.tsx:44` (the call site that already HAS the world id and throws it away — without this the rule is dead code); add `host/__tests__/studioLinks.test.ts` cases for matching-world ⇒ studio, different-world ⇒ external, **worldId-absent ⇒ external** (the branch a builder will forget).

2. **Record the handoff in the 3 docs that currently claim the opposite** (a defer/ownership row is never a silent drop):
   - `docs/plans/2026-07-12-track-c-completion-RUN-STATE.md` — row 5.3–5.4 (`:177`) and the P-5 register row (`:212`): strike **"W10 world container"** from Track C's FE-surface claim. Replace with: *"W10's `world` container panel is OWNED BY writing-studio Wave 8b (spec 38 §3.2), per Q-30-WAVE8B-WORLD-OWNERSHIP. Track C's residual W10 scope = the workflow RAIL only (the curated catalog row + its `done_when`), which CONSUMES the `world` panel Wave 8b ships. Do not build a world FE surface here."*
   - `docs/specs/2026-07-09-agent-discoverability-and-workflow/tracks/TRACK-C.md:10,18,23` — same amendment to the scope line.
   - `docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md` §9 Track-C row (`:714`) — flip 🔴→🟢 for 8b: *"RESOLVED — Wave 8b takes the `world` container in writing (Q-30-WAVE8B-WORLD-OWNERSHIP). 8c (G-WORKFLOWS) remains Track C's per PO-2."* Leave the 8c half of that row 🔴/OWNED-BY-TRACK-C untouched.

3. **Track C's P-5 residual scope is unchanged and untouched by this plan:** workflow rack, binding UI (`D-WS3-BINDING-GUI`), W8 onboarding fork, W11 reader. File sets are disjoint — Wave 8b touches `services/book-service/**` (BE-15a–l), `frontend/src/features/studio/panels/**`, `frontend/src/features/world/**`; Track C P-5 touches `agent-registry` + chat/agent settings surfaces. No shared file. **Do NOT touch `chat-service/app/services/stream_service.py`** (§9: Track C mid-edit; that constraint still binds X-10, unrelated to 8b).

4. Wave 8b's Definition of Done keeps the literal `/review-impl` step (PO run policy #2).

**Default flagged for PO veto:** I am reading PO-2's "+ world maps only" clause as dispositive. If the PO actually intended to hand the world container to Track C as well, they should say so — but nothing in Track C's code or design supports it (no files exist), and Track C's W10 is a workflow rail that needs this panel to exist anyway, so building it here unblocks both tracks.

*Evidence:* docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:20 — SEALED PO-2: "Wave 8 loses 8c. Wave 8 = KG write holes + world maps only" (8b retained in this plan by the sealed row itself). · docs/specs/2026-07-01-writing-studio/38_kg_and_world.md:167-195 — §3.2 designs the `world` panel at BUILD DETAIL (self-resolving via the book's world_id, category storyBible, the 3-file studioLinks change, the 3 empty states). · docs/specs/2026-07-09-agent-discoverability-and-workflow/tracks/TRACK-C-AUDIT.md:87 — "W10 world-container surface | ❌ | no files". · docs/specs/2026-07-09-agent-discoverability-and-workflow/tracks/TRACK-C-AUDIT.md:63 — W10 = "Worldbuilding-first world container ... needs FE + workflow" (a workflow RAIL, not a dock panel). · docs/plans/2026-07-12-track-c-completion-RUN-STATE.md:177,212 — W10 is 🅿️ PARKED under P-5, Gate #2, nothing built. · frontend/src/features/studio/panels/catalog.ts — no `world` panel row exists today (only an unrelated comment at :222), so there is nothing of Track C's to collide with. · docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:714 — §9's rule: "Either drop them from this plan or take them over in writing" — this decision is the taking-over-in-writing.

### Q-30-X7-GATHER-MOTIFS-LENS
CONFIRMED — build the motif packer lens in Wave 0; it IS a HARD GATE on Wave 3 (G-MOTIF-LIBRARY / G-MOTIF-BINDING / G-MOTIF-SUGGEST must not ship before it). Deferral is not available: the read path already exists, so this is unbuilt wiring, not missing infrastructure.

BUILD DETAIL (mirror the shipped gather_arc exactly):

1. LENS — new `async def gather_motif(...)` in `services/composition-service/app/packer/lenses.py`, placed immediately after `gather_arc` (which ends at line 363). Signature mirrors gather_arc's repo-injection shape:
   `async def gather_motif(applications_repo, motif_repo, project_id: UUID, node_id: UUID, *, user_id: UUID) -> str`
   Body:
   a. `apps = await applications_repo.by_nodes(project_id, [node_id])` — take the LAST row (by_nodes is `ORDER BY created_at` ASC, so last-wins on a re-bind; this is the same rule plan.py:1196 already applies). Empty → return "".
   b. `m = await motif_repo.get_visible(user_id, app.motif_id)` — None (archived/foreign motif → `motif_id` is SET NULL per models.py:545) → return "". No oracle, exactly as plan.py:1188 degrades.
   c. Render these lines from the Motif (models.py:493) + MotifApplication (models.py:539):
      · `Motif: "<name>" (<kind>)` + `Motif intent: <summary>`
      · the BOUND BEAT — resolve `app.annotations["beat_key"]` against `m.beats[]` (MotifBeat, models.py:476) → `Beat: <label> — <intent>` plus `Tension target: <n>/5` when `tension_target` is set. Absent beat_key → fall back to listing the motif's beats in `order` as the scene's shape.
      · `Reversal:` / `Alliance shift:` from `app.annotations` (or the beat's `reversal`/`alliance_shift`) when present.
      · `Motif roles:` — `role_bindings` (role_key → entity_id), rendered `role_key → entity` EXACTLY like gather_arc's "Cast bindings" (lenses.py:337-343). A `null` entity_id (set_role_binding writes JSON null for an unresolved role) renders `role_key → (unresolved)`, never dropped silently.
   d. `sanitize_lore(...)` EVERY author-authored string (name, summary, beat label/intent, role keys). This is stricter than gather_arc's need, not looser: motifs can be MINED from imported third-party text (`source`/`imported_derived`, models.py:519-521), so the SEC3 delimiter-forging surface is larger.
   e. Best-effort posture: wrap in `try/except Exception` → `logger.warning(...); return ""`. The motif frame THINS, never fails a pack.

2. WIRE THE CHOKEPOINT (this is the half the arc lens got wrong — do not skip):
   · `pack.py:194` — add `motif_application_repo=None, motif_repo=None` params next to `structure_repo=None`.
   · `pack.py:332-337` — add a `motif_gated` coroutine beside `arc_gated`, gated on `(motif_application_repo is not None and motif_repo is not None and node_id is not None)`, else the `_empty_str()` placeholder.
   · `pack.py:338` — add it to the existing `asyncio.gather(...)` tuple.
   · `pack.py:522` — the arc frame is composed HERE (prepended manually, NOT via assemble.py's `_BLOCK_ORDER` — note "arc" is deliberately absent from assemble.py:25). Follow that same pattern: set `blocks["motif"] = motif_text` and inject `<motif>…</motif>` IMMEDIATELY AFTER the `<arc>` frame — arc = the durable chapter-level spec frame, motif = the scene-level beat structure inside it.
   · `routers/engine.py:391` — the real `pack(...)` call site. Pass `motif_application_repo=` and `motif_repo=` alongside the existing `structure_repo=structures,  # 23 BA12 — the arc lens`. **A lens not passed here is a lens that does not exist in production** — that is verbatim the arc bug.

3. TESTS — BOTH are required. The spec asked for "a BA12-style EFFECT test"; a unit effect test is precisely what FAILED to catch this bug for the arc lens, so it is necessary but NOT sufficient:
   · `tests/unit/test_pack_motif.py` — the effect test (mirror `test_pack_arc.py`): the prompt CHANGES when a binding changes. Assert the rendered prompt differs when `role_bindings` / `beat_key` differ, and that an unbound scene is byte-unchanged.
   · `tests/integration/db/test_pack_motif_wired.py` — the WIRED proof (mirror `test_pack_arc_wired.py`): drive `pack()` with a REAL MotifApplicationRepo + MotifRepo against a real DB, from a scene node carrying only its ids, and assert `<motif>` reaches the prompt. Gate on `TEST_COMPOSITION_DB_URL`; add `pytestmark = pytest.mark.xdist_group("pg")`. If a future edit drops `motif_application_repo=` at the engine.py call site, this must red.

DoD: both tests green + `/review-impl` at wave close (per PO policy #2).

*Evidence:* GAP CONFIRMED: `grep -rn "motif" services/composition-service/app/packer/*.py` → 0 hits. pack() accepts `structure_repo=None,  # 23 BA12 — the arc lens (durable spec layer; gated)` at services/composition-service/app/packer/pack.py:194 but has NO motif repo param; the arc frame is composed at pack.py:516-523 and the sole prod call site is services/composition-service/app/routers/engine.py:391-403 (`structure_repo=structures`).
WRITE-ONLY CONFIRMED: motif_application is written at app/routers/plan.py:774 + :1377 and app/engine/arc_apply.py, and read ONLY by conformance (app/engine/arc_apply.py:590), the FE planner view (app/routers/plan.py:1193), and anti-repetition (app/routers/plan.py:577) — never by the packer.
READ PATH ALREADY EXISTS (⇒ unbuilt work, not blocked): `MotifApplicationRepo.by_nodes` at app/db/repositories/motif_application.py:94 and `MotifRepo.get_visible` used at app/routers/plan.py:1211.
MIRROR TARGET: `gather_arc` at app/packer/lenses.py:257-363 (cast-binding render at :337-343).
THE CLINCHER — SAME BUG ALREADY SHIPPED ONCE: services/composition-service/tests/integration/db/test_pack_arc_wired.py:1-8 — "the pack() call sites omitted `structure_repo=` … so in production `arc_gated` always took the dormant branch and the arc never reached the prompt. The write-only-arc bug the whole spec exists to kill was alive in prod, and D2 could not see it because it bypassed the real chokepoint. (Found by /review-impl, 2026-07-11.)" This is why the unit effect test alone is insufficient and the wired integration test is mandatory.

### Q-30-X12-PARAMS-ARG
EXTEND `ui_open_studio_panel` with an OPTIONAL free-form `params` object arg. This does NOT contradict §8.0 check 5 — that check answers only the `hiddenFromPalette` half of X-12 (no panel is forced out of the enum); it is silent on the deep-link half. Because `params` is OPTIONAL, all 14 panels stay bare-id openable, stay in the enum/palette/User Guide, and §8.0's 57→71 ledger is untouched. The work is ~1 schema field + 1 line of resolver: the whole params pipe ALREADY EXISTS below the agent.

WAVE 0, slice X-12 (size S; paired with X-5 exactly as §8.2 asked). Builder steps:

(1) services/chat-service/app/services/frontend_tools.py — in UI_OPEN_STUDIO_PANEL_TOOL["function"]["parameters"]["properties"], after `panel_id` (~line 402), add:
    "params": {
        "type": "object",
        "additionalProperties": True,
        "description": (
            "OPTIONAL deep-link target — the ID of the row you want the panel focused on. IDs only, never prose. "
            "Recognized keys: arc-inspector {arcId}; world-map {mapId}; quality-canon-rules {focusRuleId}; "
            "job-detail {jobId}; chapter-revision-compare {chapterId, fromRevisionId, toRevisionId}; "
            "book-reader {bookId, chapterId}; settings {tab}. Omit it and the panel self-resolves a sane default."
        ),
    },
    LEAVE `required` as ["panel_id"] — params must NOT be required.

(2) services/chat-service/tests/test_frontend_tools_contract.py — do NOT add `params` to CLOSED_SET_ARGS (line 57). Its values are dynamic UUIDs; that dict's own comment (l.54-56) reserves it for "a FINITE, code-known set" and explicitly excludes free-form/UUID args. `panel_id` remains the tool's only closed-set entry. (This answers the "+ CLOSED_SET_ARGS" clause of the question: the answer is NO ENTRY.)

(3) Regenerate the contract, never hand-edit: `cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py`; commit contracts/frontend-tools.contract.json in the SAME commit as (1).

(4) frontend/src/features/studio/agent/studioUiNav.ts:35 — replace `return { result: { opened: true }, effect: (host) => host.openPanel(panelId) };` with:
    const p = args.params;
    const params = p && typeof p === 'object' && !Array.isArray(p) ? (p as Record<string, unknown>) : undefined;
    return {
      result: { opened: true, ...(params ? { params } : {}) },
      effect: (host) => host.openPanel(panelId, params ? { params } : undefined),
    };
    A non-object `params` (the weak-model drift, e.g. the string "arcId=A") is DROPPED, not crashed on — the panel still opens bare-id. NO host change: StudioHostProvider.tsx:52/83/92 already accepts opts.params, and calls updateParameters() on an already-open panel, so retargeting an open arc-inspector works for free.

(5) "BOTH resolvers": there is in fact only ONE executor of this tool (useStudioUiToolExecutor -> resolveStudioUiTool). The chat-side mirror frontend/src/features/chat/utils/serverKey.ts:41 is a NAME list only (no arg shape) and needs NO change. Do not go hunting for a second resolver.

(6) Tests (all must be written, not just run):
    - frontend/src/features/studio/agent/__tests__/studioUiNav.test.ts: (a) {panel_id:'arc-inspector', params:{arcId:'A'}} -> spy host.openPanel called with ('arc-inspector', {params:{arcId:'A'}}); (b) no params -> openPanel('arc-inspector', undefined) (bare-id open unbroken); (c) params:'arcId=A' (string) -> opened:true, params dropped, no throw.
    - services/chat-service/tests/test_frontend_tools.py: assert 'params' in properties, type == 'object', and 'params' NOT in required.
    - Both drift-locks stay green: test_frontend_tools_contract.py + panelCatalogContract.test.ts (py enum == contract enum == openable; still 57 at Wave 0 close).

(7) VERIFY BY EFFECT (GG-8 — a green unit suite does not prove the loop closed): live browser smoke that `ui_open_studio_panel {panel_id:"job-detail", params:{jobId:"<real id>"}}` mounts the dock tab ON THAT JOB. Precedent: studio-palette.spec.ts.

(8) Amend §8 step 5 of the per-panel checklist: a new panel that accepts a params deep-link must ALSO append its key to the `params` description gloss — that prose is the model's only hint about the key's name.

WHY (the decisive fact): sealed PO-3 already REQUIRES this. It mandates `ui_watch_job` -> open `job-detail`, and JobDetailPanel.tsx:1 says verbatim "singleton, retargets via params". Without a params arg, a sealed decision cannot be implemented faithfully. On top of that, three specs in this very batch design a params deep-link the agent structurally cannot use today (32:142 props.params.arcId; 38:203 params.mapId; 31:136 params.focusRuleId). Refusing the extension would ship the agent a set of panels it can open but never point at — the exact "agent cannot open the panel it just wrote to" failure §8.2 named.

DEFAULT NOTED FOR PO VETO: params is free-form (no enum), so a weak model could invent a key. That is accepted — the resolver ignores unknown keys (dockview params are read defensively by every panel: see ChapterRevisionComparePanel.tsx:34 `str()` guard), the panel self-resolves a default, and the bare-id path is unchanged. The alternative (a closed enum of key names) would have to be re-opened on every new panel and buys nothing the panel-side guard doesn't already give.

*Evidence:* frontend/src/features/studio/host/StudioHostProvider.tsx:52 — `openPanel: (panelId: string, opts?: { focus?: boolean; title?: string; params?: Record<string, unknown>; component?: string }) => void` (params ALREADY in the host); :83 `if (opts?.params) existing.api.updateParameters(opts.params);` (retarget an open panel); :92 `api.addPanel({ id: panelId, component: ..., title, params: opts?.params })`. ||| frontend/src/features/studio/agent/studioUiNav.ts:35 — `return { result: { opened: true }, effect: (host) => host.openPanel(panelId) };` — the ONE line that drops params; the agent is the only caller in the repo that cannot pass them. ||| services/chat-service/app/services/frontend_tools.py:397-402 — `parameters.properties` contains `panel_id` only. ||| services/chat-service/tests/test_frontend_tools_contract.py:54-57 — "Free-form args (UUIDs, prose, allowlisted paths, dynamic panel names) are deliberately NOT listed" in CLOSED_SET_ARGS ⇒ `params` gets no entry. ||| frontend/src/features/studio/panels/JobDetailPanel.tsx:1 — "the `job-detail` dock panel: singleton, retargets via params" = the target sealed PO-3 assigns to `ui_watch_job`, so params-passing is already a sealed requirement. ||| Existing params callers prove the pipe works end-to-end: useMissionControl.ts:149 (`chapter-revision-compare`), BooksBrowserPanel.tsx:51 (`book-reader`), studioLinks.ts:80/111 (`settings` {tab}). ||| Batch specs that design a params deep-link: 32_arc_inspector.md:142 (`props.params.arcId`), 38_kg_and_world.md:203 (`params.mapId`), 31_quality_completion.md:136 (`props.params.focusRuleId`).

### Q-30-X8-DOC-HYGIENE
DO X-8, but only the 3 items that are still open — items (3) and (4) were fixed on 2026-07-12 and re-doing them would churn correct docs. Wave 0, XS, pure-docs slice, no code touched.

SKIP (verify, do not redo):
- (3) 00_OVERVIEW component index + Debt stack: ALREADY REFRESHED. 00_OVERVIEW.md:74-79 carries the "STATUS SOURCE OF TRUTH (2026-07-12) … copied from 30 §4 … When these disagree, §4 wins" banner; rows 02/03/04/07/08/09 now read 🟡/✅ with code citations; the Debt stack (00_OVERVIEW.md:149-158) was rebuilt to 3 live rows (AddModelCta DOCK-7 / top-bar Generate-Save-model / no compaction_failed breaker) with a "5 of the original 6 were stale" note.
- (4) 00C Q-2: ALREADY CLEARED. 00C_POST_ARCHITECTURE_QUEUE.md:34 = "~~Agent Mode / Mission Control build~~ — CLEARED 2026-07-12 (this row was FALSE)", with the §3 write-up at :54-59.

DO (3 open items + 1 found gap):

1) RENUMBER — a = the spec that already owns that number's 00_OVERVIEW row; b = the later add-on that collided. This is NOT arbitrary: every bare-number prose ref on disk already means it (#14 = KG at 00_OVERVIEW.md:104, 21_plan_hub.md:36/196/218, 20_agent_mode.md:43; #15 = Wiki at 00_OVERVIEW.md:105 and 20_agent_mode.md:65 "same params-retargeting pattern as wiki-editor, #15"). Choosing this mapping means ZERO prose rewrites; the inverse mapping would silently invert 6 existing references.
   git mv (in docs/specs/2026-07-01-writing-studio/):
     14_kg_panels.md        -> 14a_kg_panels.md
     14_utility_panels.md   -> 14b_utility_panels.md
     15_wiki_panels.md      -> 15a_wiki_panels.md
     15_chapter_browser.md  -> 15b_chapter_browser.md
   Then update ALL 21 link occurrences (every cross-ref is a markdown link by FILENAME, so a mechanical path rewrite is complete and safe):
     docs/plans/2026-07-04-chapter-browser-plan.md:3,57
     docs/plans/2026-07-04-utility-panels-fanout.md:3,9,45,70
     docs/sessions/SESSION_HANDOFF.md:1971,2215,2218,2246
     docs/specs/2026-07-01-writing-studio/00_OVERVIEW.md:104,105
     docs/specs/2026-07-01-writing-studio/12_json_document_standard.md:117
     docs/specs/2026-07-01-writing-studio/15b_chapter_browser.md:4  (its own "same shape as 14_utility_panels.md" prose workaround — the one 30 §X-8 calls out)
     docs/specs/2026-07-01-writing-studio/15a_wiki_panels.md:11
     docs/specs/2026-07-01-writing-studio/16_chapter_editor_parity_and_retirement.md:143
     docs/specs/2026-07-01-writing-studio/22_scene_model_and_crud.md:238,272
     docs/specs/2026-07-01-writing-studio/23_book_architecture.md:302,493
     docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:219  (rewrite the X-8 bullet to record the mapping as DONE + the a/b rationale, so no later agent re-litigates it)
   Also bump each renamed file's H1 number: "# 14 · Knowledge/KG…" -> "# 14a · …"; "# 14 · Utility Panels…" -> "# 14b · …"; "# 15 — Wiki dockable migration" -> "# 15a — …"; "# 15 · Chapter Browser…" -> "# 15b · …".
   VERIFY: `grep -rn "14_kg_panels\|14_utility_panels\|15_chapter_browser\|15_wiki_panels" --include=*.md docs/` returns 0 hits.

2) FIX 29's H1 — docs/specs/2026-07-01-writing-studio/29_translation_repair.md:1: replace "# 24 — Translation surfaces: defect audit + repair spec" with "# 29 — Translation surfaces: defect audit + repair spec" (29 is the file's real number; 24 is now Plan Hub v2, so the current H1 actively collides).

3) UN-STALE spec 20's header — docs/specs/2026-07-01-writing-studio/20_agent_mode.md:3: replace "> **Status:** 📐 CLARIFY complete, ready for DESIGN/PLAN · not yet built" with a line stating the verified truth: "✅ SHIPPED — the `agent-mode` panel is in `frontend/src/features/studio/panels/catalog.ts` AND in the `ui_open_studio_panel` enum (verified by 30 §4, 2026-07-12). Unshipped tail: no Lane-B effect handler for `composition_authoring_run_*` (30 X-4), a now-false comment at `useStudioEffectReconciler.ts:10`, a missing `guideBodyKey` (30 X-3), and NO `compaction_failed` breaker for its L3/L4 autonomous runs (07S §3/§10 makes it MANDATORY — P1 Deferred row in SESSION_HANDOFF)." This matches what 00_OVERVIEW.md:109 and 00C:34 already say, so the three files stop contradicting each other.

4) FOUND GAP — close it in the same slice: 14b (utility panels) and 15b (chapter browser) have NO ROW AT ALL in the 00_OVERVIEW component index (it goes 13 -> 14 KG -> 15 Wiki -> 16). Two shipped specs are invisible to the index that plan 30 just declared the status SSOT. Add a row for each after their 'a' sibling, status per their own headers ("📐 specced + sealed 2026-07-04" / "📐 specced 2026-07-04") re-checked against catalog.ts before writing the status — do not copy a status from memory (the exact rule 00_OVERVIEW.md:79 lays down).

DoD for this slice: the grep in (1) returns 0; `grep -rn "not yet built" 20_agent_mode.md` returns 0; 29's H1 says 29; the overview index contains 14a/14b/15a/15b rows; `/review-impl` runs at wave close (PO policy #2). No code files change, so no test gate beyond the greps.

*Evidence:* OPEN: `ls docs/specs/2026-07-01-writing-studio/` → 14_kg_panels.md + 14_utility_panels.md + 15_chapter_browser.md + 15_wiki_panels.md all present · 29_translation_repair.md:1 = "# 24 — Translation surfaces: defect audit + repair spec" · 20_agent_mode.md:3 = "> **Status:** 📐 CLARIFY complete, ready for DESIGN/PLAN · not yet built". ALREADY FIXED: 00_OVERVIEW.md:74-79 (status-SSOT banner + rows 02/03/04/07/08/09 now ✅/🟡) and 00_OVERVIEW.md:151-154 (Debt stack refreshed, 3 rows); 00C_POST_ARCHITECTURE_QUEUE.md:34 + :54-59 (Q-2 CLEARED as FALSE). a/b mapping grounded by: 00_OVERVIEW.md:104 (row 14 = KG), 00_OVERVIEW.md:105 (row 15 = Wiki), 20_agent_mode.md:65 ("wiki-editor, #15"), 21_plan_hub.md:36 ("#13/#14 shared-foundation-then-fanout"). Cross-refs to rewrite: 21 hits from `grep -rn "14_kg_panels\|14_utility_panels\|15_chapter_browser\|15_wiki_panels" --include=*.md docs/`, all markdown links by filename. Plan-30 source row: 30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:341 (X-8, XS) and :219.

### Q-30-X4-LANE-B-HANDLERS
X-4 is REAL but its scope is wrong on 3 counts. Wave 0 ships 4 things, NOT 15 handlers.

**(1) DELETE the false comment.** `frontend/src/features/studio/agent/useStudioEffectReconciler.ts` lines 5-10 (the block ending "...authoring_run has no MCP tools at all, REST-only, no Studio consumer to go stale"). Both halves are FALSE (see 2). Replace with: "Handlers are registered per-domain in handlers/*.ts; §8.0b of spec 30 is the one-file-per-domain owner map. Coverage is machine-checked by effectCoverage.contract.test.ts — do not add a domain without a row there." Also fix `effectRegistry.ts:4` ("book/glossary/knowledge/translation as of 2026-07-05").

**(2) DROP `kg_create_node` from X-4 — already covered.** `handlers/knowledgeEffects.ts:16` `KNOWLEDGE_WRITE_PATTERN` is a NEGATIVE-lookahead (`/^kg_(?!project_list|graph_query|world_query|multi_query|entity_edge_timeline|schema_read|list_templates|sync_available|view_read|triage_list)/`) — allow-by-default over kg_*, minus reads. `kg_create_node` is not excluded ⇒ it matches ⇒ knowledgeEffect fires today. No new handler. Add `kg_create_node` to `knowledgeEffects.test.ts` as an explicit positive case so this stays true.

**(3) NEW: `handlers/authoringRunEffects.ts` — Wave 0, ship it now.** §8.0b's owner map has NO row for `composition_authoring_run_*`; this is the map's orphan and it is a LIVE staleness bug, not a future prereq: the 11 tools exist (`composition-service/app/mcp/server.py:1616`+) and the `agent-mode` panel SHIPPED and reads these keys (`panels/agentMode/useNewRunForm.ts:124`). Mirror knowledgeEffects.ts exactly (module-level `let registered`, `_reset*` test hook, RegExp not string):
  `registerEffectHandler(/^composition_authoring_run_/, authoringRunEffect)` → invalidate `['authoring-runs']`, `['authoring-run']`, `['authoring-run-report']`, `['authoring-unit-diff']`, `['plan-runs-for-authoring']`, `['plan-run-for-authoring-gate']`, `['book-toc-for-authoring']`. Call `registerAuthoringRunEffectHandlers()` in the reconciler's registration useEffect (~line 35). Test: `__tests__/authoringRunEffects.test.ts`, asserting each of the 11 real tool names matches and each key is invalidated. ADD THE §8.0b ROW: `composition_authoring_run_* → authoringRunEffects.ts → owner: Wave 0 (spec 30 itself)`.

**(4) THE ACTUAL WAVE-0 GATE ARTIFACT — `agent/__tests__/effectCoverage.contract.test.ts`.** The remaining ~13 handlers CANNOT be written in Wave 0: per §8.0b each file is created by the wave that ships its panel (compositionEffects→W1/spec31, arcEffects→W2/spec32, motifEffects→W3/spec33, planEffects→W5/spec35, diagnosticsEffects→W7/spec37, worldEffects→W8/spec38). A Wave-0 handler invalidating query keys of panels that do not exist yet IS a silent-no-op handler — precisely the class §8.0b's RegExp-vs-string warning exists to kill. So Wave 0 ships the ENFORCEMENT instead of the stubs (CLAUDE.md "checklist ⇒ test the effect"):
  - A literal `WRITE_TOOLS: Record<string, string>` mapping every write-tool NAME (not pattern) to its owning file. Seed from the live inventory: `composition_canon_rule_{create,update,delete,restore}`, `composition_publish`, `composition_conformance_run` → compositionEffects; `composition_arc_{create,update,delete,move,restore,apply,assign_chapters,import_analyze,extract_template,suggest}` + `composition_arc_template_drift` → arcEffects; `composition_motif_{create,patch,archive,adopt,bind,unbind,link_create,link_delete,mine,suggest_for_chapter}` → motifEffects; `plan_{compile,run_pass,apply_revision,propose_spec,self_check,validate,link,handoff_autofix,interpret_feedback,review_checkpoint}` → planEffects; `world_map_{create,delete,add_marker,remove_marker,add_region,remove_region}` → worldEffects; `registry_{propose_skill,propose_workflow,update_skill,update_workflow,set_skill_enabled,ingest}` → registryEffects; `composition_authoring_run_*` → authoringRunEffects; `kg_create_node` → knowledgeEffects.
  - After calling every `register*EffectHandlers()`, assert for each name `matchEffectHandlers(name).length >= 1` UNLESS it is in an explicit `PENDING: Record<string, 'wave-N'>` allowlist. Because it tests REAL TOOL NAMES, it also catches the string-vs-RegExp silent-no-op trap (§8.0b) that no per-handler unit test can catch.
  - **Each wave's Definition of Done gains a literal step: "delete this wave's rows from `PENDING` in effectCoverage.contract.test.ts by creating/extending its §8.0b handler file — the test reds until you do."** That converts X-4 from a checklist item into a mechanical ledger.
  - Wave 0 leaves `PENDING` holding exactly: compositionEffects(W1), arcEffects(W2), motifEffects(W3), planEffects(W5), diagnosticsEffects(W7), worldEffects(W8), registryEffects(→see below). Wave 0 itself clears authoringRunEffects + kg_create_node.

**Default I am picking (PO may veto): `registry_*workflow*` has no owning spec in §8.0b.** I assign `registryEffects.ts` to the wave that ships the agent-registry/workflow panel; if no wave does, it stays in `PENDING` with target `wave-7` (spec 37) rather than being silently dropped. It is NOT a Wave-0 handler — no Studio panel reads registry workflows today, so a Wave-0 handler there would be the no-op class again.

Wave-0 gate for X-4 is green when: comment deleted, authoringRunEffects.ts + its test green, kg_create_node positive case green, effectCoverage.contract.test.ts green with a non-empty documented PENDING, and `/review-impl` run at wave close.

*Evidence:* frontend/src/features/studio/agent/useStudioEffectReconciler.ts:5-10 (the FALSE comment: "authoring_run has no MCP tools at all, REST-only, no Studio consumer to go stale") and :35-40 (the 4 registration call sites) · frontend/src/features/studio/agent/handlers/bookEffects.ts:59-62 (the only 3 composition/book patterns registered) · frontend/src/features/studio/agent/handlers/knowledgeEffects.ts:16 (KNOWLEDGE_WRITE_PATTERN negative-lookahead ⇒ kg_create_node ALREADY matches — X-4's claim is false) · services/composition-service/app/mcp/server.py:1616 (`name="composition_authoring_run_create"` — the tools X-4's comment says don't exist) · frontend/src/features/studio/panels/agentMode/useNewRunForm.ts:124 (`invalidateQueries({queryKey:['authoring-runs', bookId]})` — the shipped consumer the comment says doesn't exist) · frontend/src/features/studio/agent/effectRegistry.ts:45 (matchEffectHandlers returns ALL matches ⇒ §8.0b's double-fire rule) · docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:605-620 (§8.0b one-file-per-domain owner map, which assigns each file to its panel's wave — hence Wave 0 cannot write them)

### Q-30-X9-UNAUDITED-MCP-SWEEPS
The two sweeps are DONE — here, from the code. Wave 0 does not "run a sweep", it applies this result (3 doc edits + 2 code fixes, all small).

(1) CORRECT THE SCOREBOARD in 30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md §3.1 + delete §3.4 entirely (replace it with a one-line "closed by X-9" note). Real numbers: provider-registry hosts **13** tools, not 14 (12 `settings_*` + 1 `web_search`); catalog hosts 2. So the "MCP tools, other services" row becomes **188 total / 164 covered / 24 no-GUI** (was 173/150/23). The "real total >= 189" claim is itself wrong — it is 188. The 24th no-GUI tool is `web_search`, which is **agent-native by design (NOT a gap to close)** — a human already has a browser; classify it in the same bucket as the audit's existing "3 agent-native reads".

(2) `web_search`'s "unprefixed = namespacing violation" is **REFUTED — no action.** ai-gateway `src/config/config.ts:110-128` declares `settings: ['web_']` in EXTRA_PREFIX_MAP and `test/catalog.spec.ts:161` asserts it against the REAL config (not a fixture), so the C-GW prefix gate does not drop it. It shadows nothing: glossary's tool is named `glossary_web_search` (`glossary-service/internal/api/web_search_tool.go:40`, retained as legacy in `mcp-public-gateway/src/scope/tool-policy.ts:174-179`). Strike the bullet from the spec.

(3) catalog-service: **2/2 GUI-covered, zero gaps.** `catalog_list_public_books` -> `frontend/src/pages/BrowsePage.tsx:53` (GET /v1/catalog/books); `catalog_get_book` -> `frontend/src/features/books/api.ts:535`. Record as verified-covered; add nothing to the gap register.

(4) NEW GAP — register it as **G-PROFILE-FIELDS** (agent-only write surface; the "spot-check was luck" was right): `settings_update_profile` accepts `locale/avatar_url/bio/languages` (`provider-registry-service/internal/api/mcp_server.go:441-445`) and auth-service validates + persists all of them (`auth-service/internal/api/handlers.go:366-384`), but the FE payload type is literally `{ display_name?: string }` (`frontend/src/features/settings/api.ts:24`) and `AccountTab.tsx:65` only ever sends display_name — while `frontend/src/features/profile/ProfileHeader.tsx:32-62` RENDERS avatar/bio/languages no human can set. FIX IN WAVE 0 (it is ~40 lines, it does not clear any defer gate): widen `accountApi.patchProfile`'s payload type in `settings/api.ts:24` to `{ display_name?: string; locale?: string; avatar_url?: string; bio?: string; languages?: string[] }`; in `AccountTab.tsx` add, under the existing display_name field (~:141), an avatar_url text input, a bio <textarea maxLength={1000}>, a languages editor reusing `frontend/src/features/settings/TagEditor.tsx`, and a locale <select>; send all five in the `patchProfile` call at :65 and keep the dirty-check at :216 covering every field. TEST: new `frontend/src/features/settings/__tests__/AccountTab.profile.test.tsx` — edit bio + add a language + set avatar_url, click Save, assert the fetch body contains all four keys (guards the exact bug: a save that silently drops the fields).

(5) NEW BUG — fix in Wave 0, one-liner class: `settings_model_set_default` under-advertises its capability set to the LLM. Its Description and jsonschema say "(rerank or embedding)" (`mcp_server.go:82`, `:135`, `:650`) while the runtime whitelist `defaultModelCapabilities` accepts **rerank | embedding | chat | planner** (`default_models_handler.go:20-30`) and the GUI already exposes all four (`settings/api.ts:91-96`). The agent only ever sees the description, so it will never set a chat or planner default. Change all three strings to "rerank, embedding, chat, or planner" (and mirror the same wording in `settings_get_defaults`'s Description at :82). TEST in `mcp_server_test.go`: assert `settings_model_set_default` with `capability:"planner"` succeeds AND that the registered tool's schema/description mentions all four capabilities (a string-drift guard, since the whitelist and the description live in different files).

DEFAULT I AM PICKING (veto-able): `web_search` stays unprefixed and gets no GUI. It is correctly allowlisted at the gateway and a "web search panel" is not a Studio feature.

*Evidence:* Counts: services/provider-registry-service/internal/api/mcp_server.go:59-141 (12 settings_* tools; header comment at :22 says "10 of the 12 tools") + services/provider-registry-service/internal/api/mcp_web_search_tool.go:70 (web_search) = 13, NOT 14. services/catalog-service/internal/api/mcp_server.go:41-56 = 2 tools. | Namespacing REFUTED: services/ai-gateway/src/config/config.ts:110-128 (`settings: ['web_']`) + services/ai-gateway/test/catalog.spec.ts:161-162; glossary's tool is separately named at services/glossary-service/internal/api/web_search_tool.go:40. | Catalog covered: frontend/src/pages/BrowsePage.tsx:53 + frontend/src/features/books/api.ts:530-549 vs services/catalog-service/internal/api/server.go:89-93. | G-PROFILE-FIELDS: services/provider-registry-service/internal/api/mcp_server.go:441-445 (tool takes locale/avatar_url/bio/languages) + services/auth-service/internal/api/handlers.go:366-384 (BE validates them) vs frontend/src/features/settings/api.ts:24 (`patchProfile(token, payload: { display_name?: string })`) and frontend/src/features/settings/AccountTab.tsx:65 (`patchProfile(accessToken, { display_name: displayName })`) — and frontend/src/features/profile/ProfileHeader.tsx:32-62 displays the unsettable fields. | set_default drift: mcp_server.go:82 + :135 + :650 say "rerank or embedding"; services/provider-registry-service/internal/api/default_models_handler.go:20-30 accepts rerank/embedding/chat/planner; frontend/src/features/settings/api.ts:91-96 exposes all four.

### Q-30-X2-CATEGORY-ORDER
CONFIRMED BUG — and it is LIVE IN PROD TODAY, not a Wave-1 hazard: 5 `category:'quality'` panels already ship (catalog.ts:266-270) and all 5 currently sort to the TOP of the Command Palette, above `editor`. Adopt the spec's candidate answer, plus 2 additions the spec missed. Build it as 4 slices:

SLICE 1 — fix the order + make the drift UNBUILDABLE.
File: frontend/src/features/studio/palette/useStudioCommands.ts, replace lines 20-22 with:

    export const CATEGORY_ORDER = [
      'editor', 'storyBible', 'knowledge', 'quality', 'translation',
      'enrichment', 'sharing', 'platform', 'discovery', 'jobs',
    ] as const satisfies readonly StudioPanelCategory[];

    // X-2 — compile-time exhaustiveness. A new StudioPanelCategory not listed above is now a TYPE
    // ERROR. The failure modes are INVERTED: an un-categorized panel sorts LAST (harmless fallback),
    // but an UNLISTED category indexOf()s to -1 and sorts FIRST. "Forgot to add it" must be
    // unbuildable, not merely ugly.
    type _UnorderedCategory = Exclude<StudioPanelCategory, (typeof CATEGORY_ORDER)[number]>;
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const _CATEGORY_ORDER_IS_EXHAUSTIVE: [_UnorderedCategory] extends [never] ? true : never = true;

⚠ THE `as const satisfies` IS LOAD-BEARING, NOT STYLE. Keeping the existing `: StudioPanelCategory[]` annotation makes `(typeof CATEGORY_ORDER)[number]` widen back to the full union, so `Exclude<>` is always `never` and the guard PASSES WHILE STILL MISSING 'quality'. Dropping the annotation is what gives the tuple its literal element type.
Placement default (PO may veto by reordering one array): 'quality' sits after 'knowledge', before 'translation' — it reads the manuscript, so it groups with the other analysis surfaces.
Consumers keep typechecking on a readonly tuple: useStudioCommands.ts:55-56 (`.indexOf`, `.length`) and UserGuidePanel.tsx:24-25 (`.filter`, `.includes(c as (typeof CATEGORY_ORDER)[number])`). Verify with `npx tsc --noEmit`.

SLICE 2 — the SECOND LIVE HALF the spec did not catch (same root cause, same defect surface).
`palette.group.quality` does not exist in ANY locale — `en/studio.json` `palette.group` has 13 keys (recent, panels, navigate, layout, editor, storyBible, knowledge, translation, enrichment, sharing, platform, discovery, jobs, help) and no `quality`. Because useStudioCommands.ts:60 calls `group(p.category, p.category)`, the palette today renders a group header of the RAW LOWERCASE STRING "quality" next to "Editor & Chapters" and "Story Bible". Sorting it correctly but leaving it mislabeled is a half-fix.
Add `"quality": "Quality"` to `palette.group` in frontend/src/i18n/locales/en/studio.json (beside `"knowledge": "Knowledge Graph"`), then propagate to the other 17 locales (ar bn de es fr hi id ja ko ms pt-BR ru th tr vi zh-CN zh-TW) with scripts/i18n_translate.py. There is NO studio-namespace parity test, so an en-only add silently English-fallbacks in 17 locales — do all 18.

SLICE 3 — the membership assertion (the guard spec 18's B6 got backwards).
File: frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts, after B6 (lines 40-43). Add `import { CATEGORY_ORDER } from '../../palette/useStudioCommands';` — NO runtime cycle: useStudioCommands.ts:4 imports only *types* from catalog, so the edge is erased.

    // X-2 / B7 — B6 above asserts a category is PRESENT; nothing asserted it was a MEMBER of
    // CATEGORY_ORDER. That guards the harmless half. A panel with no category sorts LAST; a panel
    // whose category is unlisted sorts FIRST — which is how 5 shipped `quality` panels ended up
    // above `editor` at the top of the palette.
    it('every palette-openable panel category is a MEMBER of CATEGORY_ORDER (X-2)', () => {
      const unordered = OPENABLE_STUDIO_PANELS
        .filter((p) => p.category && !CATEGORY_ORDER.includes(p.category))
        .map((p) => `${p.id}:${p.category}`);
      expect(unordered).toEqual([]);
    });

    // X-2 — SLICE 2's effect: an ordered category with no `palette.group.<cat>` label renders its
    // raw lowercase id as the group header. Guard the label set, not just the order.
    it('every CATEGORY_ORDER entry has a palette.group i18n label', () => {
      const groups = (JSON.parse(readFileSync(resolve(process.cwd(),
        'src/i18n/locales/en/studio.json'), 'utf-8')) as any).palette.group;
      expect(CATEGORY_ORDER.filter((c) => !groups[c])).toEqual([]);
    });

SLICE 4 — assert the EFFECT (a green type-guard is not a sorted palette).
File: frontend/src/features/studio/palette/__tests__/useStudioCommands.test.ts, extend the B4 sort test (line 74). Feed it a `category:'quality'` panel alongside an `editor` panel IN THAT ORDER and assert the emitted `studio.openPanel.*` id list puts editor FIRST — the exact assertion that would have red-flagged this bug the day the quality tab shipped.

DoD (per PO policy: `/review-impl` runs at wave close and any bug it finds is fixed before the wave closes):
`cd frontend && npx tsc --noEmit && npx vitest run src/features/studio/panels/__tests__/panelCatalogContract.test.ts src/features/studio/palette/__tests__/useStudioCommands.test.ts` — all green, and tsc is what proves the compile guard.

REJECTED ALTERNATIVE (do not "improve" the fix into this — it is a regression): moving CATEGORY_ORDER into catalog.ts to sit beside the union. catalog.ts imports UserGuidePanel.tsx, which imports CATEGORY_ORDER from useStudioCommands; a VALUE import back into useStudioCommands from catalog closes a real runtime cycle — precisely the hazard UserGuidePanel.tsx:12-14's own header comment warns about for tours.ts. StudioPanelCategory is already imported at useStudioCommands.ts:4, so the exhaustiveness guard works in place at zero import churn.

This unblocks Wave 1: spec 31's three new `quality` panels and spec 33's fourth inherit a correct sort and a real group label, and any future category is a compile error until it is ordered AND labeled.

*Evidence:* frontend/src/features/studio/palette/useStudioCommands.ts:20-22 — CATEGORY_ORDER lists 9: ['editor','storyBible','knowledge','translation','enrichment','sharing','platform','discovery','jobs'] — 'quality' absent. | frontend/src/features/studio/panels/catalog.ts:81-91 — StudioPanelCategory union defines 10, with 'quality' at line 85. | useStudioCommands.ts:55-56 — `const ai = a.category ? CATEGORY_ORDER.indexOf(a.category) : CATEGORY_ORDER.length; return ai - bi;` → indexOf('quality') === -1 → (-1 - 0) < 0 → quality sorts ABOVE editor(0); an uncategorized panel gets length(9) → sorts last. Failure modes INVERTED, exactly as the spec states. | catalog.ts:266-270 — FIVE quality panels already shipped and openable (quality, quality-promises, quality-critic, quality-coverage, quality-canon; catalog.ts:279 OPENABLE_STUDIO_PANELS = filter(!hiddenFromPalette) — none are hidden) ⇒ the bug is live in prod NOW. | panelCatalogContract.test.ts:40-43 — B6 asserts `!p.category` is empty (PRESENCE), never membership in CATEGORY_ORDER — guards the harmless half. | useStudioCommands.ts:60 `group(p.category, p.category)` + frontend/src/i18n/locales/en/studio.json palette.group (13 keys: recent/panels/navigate/layout/editor/storyBible/knowledge/translation/enrichment/sharing/platform/discovery/jobs/help — no 'quality') ⇒ the group header currently renders the raw lowercase string "quality". | UserGuidePanel.tsx:11,24-25 — the only other CATEGORY_ORDER consumer; its `rest` bucket appends unlisted categories LAST, so the guide and the palette disagree on where quality goes today. | useStudioCommands.ts:4 — `import type { StudioPanelDef, StudioPanelCategory } from '../panels/catalog'` is TYPE-ONLY ⇒ the new test import creates no runtime cycle, and the exhaustiveness guard needs no new import.

### Q-30-X11-DANGLING-REF
X-11 == BE-11. It is a stale cross-reference, not missing work. Two things for the builder:

(1) DOC FIX (do this first, 1 line): in docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md line 237, the G-CANON-RULE-CRUD row's "(+ one SMALL: no `restore` — see X-11)" becomes "(+ one SMALL: no `restore` — see BE-11)". No X-11 exists (§8 runs X-1..X-10, X-12, X-13) and §7 line 355 already names the real item: "BE prereqs: BE-11 (canon restore, XS)". Nothing else in the repo cites X-11 (grep: only line 237).

(2) BUILD BE-11 exactly as §7 line 305 scopes it (composition, XS), mirroring the outline sibling verbatim:
  - REPO — services/composition-service/app/db/repositories/canon_rules.py, add `async def restore(self, project_id: UUID, rule_id: UUID) -> CanonRule | None` immediately after `archive()` (which ends at line 166). It is archive()'s exact inverse: `UPDATE canon_rule SET is_archived = false, updated_at = now() WHERE project_id = $1 AND id = $2 AND is_archived RETURNING {_SELECT_COLS}`; return `_row_to_rule(row) if row else None`. NOTE: it must NOT bump `version` and must NOT touch `active` — restore un-archives only; a rule that was `active=false` when deleted comes back inactive. canon_rule has no parent/child tree, so there is no cascade (unlike outline.restore_node's two recursive walks).
  - ROUTE — services/composition-service/app/routers/canon.py, add `@router.post("/canon-rules/{rule_id}/restore", status_code=200)` right after the DELETE handler (line 175). Copy the DELETE handler's body shape 1:1: resolve scope from the ROW via the existing `_rule_project_id(rule_id)` helper (canon.py:95-105 — the by-id routes have no project in the path), then `await _require_work(works, grant, user_id, project_id, GrantLevel.EDIT)`, then `rule = await canon.restore(project_id, rule_id)`; `if rule is None: raise HTTPException(404, detail="canon rule not found or not archived")` (same wording shape as outline.py:663); return `rule.model_dump(mode="json")`. No If-Match / OCC on restore — the sibling restores (outline.py:648, arc.py:528) take none, and the row is archived so no concurrent editor is racing it.
  - TESTS — services/composition-service/tests/unit/test_outline_canon_routers.py (the existing home for both routers): (a) delete → restore → the rule reappears in `GET /works/{pid}/canon-rules`; (b) restore of a never-archived rule → 404; (c) restore by a VIEW-only grantee → 403 (the gate is EDIT); (d) repo-level: restore does not bump `version` and does not flip `active`. Add the repo round-trip to tests/integration/db/test_repositories.py alongside the existing restore_node coverage.

DEFAULT I AM PICKING (PO may veto): reachability of the undo is an undo-TOAST, not an archive browser. `CanonRulesRepo.list_all` (canon_rules.py:88) filters `NOT is_archived`, so an archived rule cannot be listed — but `DELETE /canon-rules/{rule_id}` already returns the archived row (id included), so the FE holds the id and shows "Rule deleted · Undo" → POST .../restore. Do NOT add an `include_archived` list param or an archived-rules UI in this wave; that is scope the row does not buy, and it would push BE-11 off XS.

Do NOT add a `composition_canon_rule_restore` MCP tool in this slice — §5.1's tool column for G-CANON-RULE-CRUD lists create/update/delete + list only, and §7 scopes BE-11 as "repo + route". The restore is a human undo affordance on the GUI, not an agent action.

*Evidence:* docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:237 (the dangling "see X-11") vs :305 (BE-11 = "canon_rule restore (repo + route) · composition · G-CANON-RULE-CRUD · XS") and :355 ("BE prereqs: BE-11 (canon restore, XS)"). Code proving BE-11 is real+unbuilt: services/composition-service/app/db/repositories/canon_rules.py:155 `archive()` (soft-delete) with NO restore anywhere in the 166-line file; services/composition-service/app/routers/canon.py:175 `DELETE /canon-rules/{rule_id}` with no restore route. Sibling pattern to copy: services/composition-service/app/routers/outline.py:648 (`POST /outline/nodes/{node_id}/restore`) + services/composition-service/app/db/repositories/outline.py:1409 (`restore_node`), and services/composition-service/app/routers/arc.py:528. Reachability constraint: services/composition-service/app/db/repositories/canon_rules.py:88 (`list_all` filters `NOT is_archived` ⇒ archived rules are unlistable ⇒ undo must carry the id from the DELETE response). Test home: services/composition-service/tests/unit/test_outline_canon_routers.py.

### Q-30-X6-RESOURCE-REF
WRITE §"AN-12.1 — the `resource_ref` convention" INTO `docs/specs/2026-07-01-writing-studio/28_agent_native_studio.md` (do not fork; place it directly after the existing "## AN-12 AMENDED (PO-1)" section at :217). It is a RATIFICATION + DISAMBIGUATION of a shape that ALREADY SHIPS — not a greenfield design. OQ-8's shape sketch is WRONG in two ways and the section must override it on the record. Five normative parts:

(1) NAME — one name for one concept (DA-10). The concept is `resource_ref`. The shipped object key is `node_ref` and there is no FE consumer of it (zero hits for `node_ref` under `frontend/`), so RENAME it at its 3 producers: `entity_references.py` (5 sites: :138 :161 :186 :212 :222), `agent_native.py` (the `Diagnostic.node_ref` field :113 + its serializer :143), `mcp/server.py` (5 sites: :3998 :4025 :4047 :4099 :4125). ~11 non-test sites. The rename is MANDATORY, not cosmetic: `node_ref` is ALREADY a third, unrelated thing in this same service — `plan_overlay.py:110` aliases it to a bare uuid STRING and `routers/plan_overlay.py:195` returns it as one. Leaving the object named `node_ref` ships one name over three meanings.

(2) KIND = ONE TABLE = ONE ID-SPACE — this is the bug the section exists to kill, and it is live today. `{kind:'arc'}` is emitted BOTH for a `structure_node.id` (server.py:3998) and for an `outline_node` row (whose CHECK allows 'arc' — migrate.py:196), and `{kind:'chapter'}` BOTH for a book-service chapter id (server.py:4125) and an outline_node id (server.py:4099). A resolver receiving `{kind:'arc'|'chapter', id}` cannot tell which TABLE the uuid lives in ⇒ it deep-links to the wrong object or 404s. So the closed set is keyed to the TABLE, never to the row's `kind` column:
  composition: `structure_node` | `outline_node` | `motif_application` | `canon_rule` | `narrative_thread`
  book-service: `chapter` | `scene`
  glossary: `glossary_entity`
Shape: `{kind: <enum above>, id: uuid-string, subkind?: string, title?: string|null, version?: number|null}`. `subkind` carries the row's own kind column ('saga'|'arc' for structure_node; 'arc'|'chapter'|'scene'|'beat' for outline_node) so emitters keep the semantics they'd otherwise lose. `version` is an optimistic-concurrency HINT only; absent means unknown, never 0 (fe-status-default-fallback lesson).
Emitter fixes (exact): server.py:3998 → kind `structure_node` + subkind 'arc'; :4025/:4047 → `scene`; :4099 → `outline_node` + subkind `n['kind']`; :4125 → `chapter`. entity_references.py:138 → `structure_node` + subkind `r['kind']`; :222 `_ref()` → `outline_node` + subkind; :161 `motif_application`; :186 `canon_rule`; :212 `narrative_thread`.
⚠ RECORD THE OVERRIDE OF OQ-8's SKETCH: 'structure'→`structure_node`, 'outline'→`outline_node`, 'thread'→`narrative_thread` (the table and the shipped emitter both say narrative_thread), and the sketch's 5 kinds are INCOMPLETE — it omits `chapter`/`scene`/`glossary_entity`, which the shipped diagnostics already emits and which G-MOTIF-BINDING (chips→editor) and the shipped PH18 canon deep-link both require. A builder following the sketch literally would drop kinds the code already produces.

(3) THE FE RESOLVER — the genuinely missing half (no such function exists). NEW FILE `frontend/src/features/studio/host/resourceRef.ts`, mirroring `studioLinks.ts:69` exactly (pure, host injected, no React, unit-testable): `resolveResourceRef(ref, ctx:{bookId}) → {kind:'studio'; effect:(host:StudioHost)=>void} | {kind:'unresolved'; reason:string}`. It NEVER silently no-ops (Frontend-Tool-Contract: return the error). Each arm reuses a SHIPPED seam:
  `canon_rule` → `host.openPanel('quality-canon', {params:{bookId, focusRuleId:id}})` — the exact contract PlanHubPanel.tsx:74 already emits and useQualityCanon.ts:74 already consumes
  `chapter` → `host.focusManuscriptUnit(id)` (StudioHostProvider.tsx:53)
  `outline_node` / `structure_node` → `host.publish({type:'planFocusNode', nodeId:id})` + `openPanel('plan-hub')` (types.ts:66/109 → PlanHubPanel.tsx:121-127)
  `scene` → `openPanel('scene-inspector', {params:{sceneId:id}})`
  `narrative_thread` → `openPanel('quality-promises', {params:{bookId, focusPromiseId:id}})`
  `glossary_entity` → `openPanel('glossary', {params:{focusEntityId:id}})`
  `motif_application` → `{kind:'unresolved', reason:'motif studio not built yet (spec 33 / Wave 3)'}` — Wave 3's DoD flips this arm and its test.
TEST: `frontend/src/features/studio/host/__tests__/resourceRef.test.ts` — one case per kind asserting the exact host call, plus 'unresolved' for motif_application AND for an unknown kind (never throws, never no-ops).

(4) THE AGENT'S POINTING VERB — today the agent literally CANNOT point at a rule or a plan node: `ui_open_studio_panel` takes `panel_id` and NOTHING else (frontend_tools.py:391), `ui_focus_manuscript_unit` takes only chapter_id/scene_id (:493). The section specs ONE new frontend tool `ui_focus_resource(kind, id)`: `kind` is a closed set ⇒ `enum` in the schema + registered in `CLOSED_SET_ARGS` + `WRITE_FRONTEND_CONTRACT=1 pytest` regen of `contracts/frontend-tools.contract.json`; the FE resolver is `resolveResourceRef`. NO new dock panel, NO catalog row, NO `ui_open_studio_panel` enum change — AN-12's architecture (the DOCK-2/DOCK-8 anti-fork clause, which PO-1 left standing) is honoured verbatim. SEQUENCING: its contract regen must not run concurrently with X-5's `ui_show_panel` retirement regen — land X-5 first (00B_EXECUTION_ROADMAP.md:203, "never two concurrent regens").
DEFAULT I AM PICKING (veto-able): a typed 2-arg verb, NOT a free-form `params` bag bolted onto `ui_open_studio_panel` — a free-string params object is precisely the drift the Frontend-Tool-Contract standard forbids, while `{kind enum, id}` stays machine-checked on both sides.

(5) SCOPE FENCE — `resource_ref` is an ADDRESS, not a lock and not a mutation contract. Writes keep going through the owning tool's own OCC/base_version. State this explicitly so a later agent does not grow it into a write channel.

BUILD PLACEMENT: the spec section itself is Wave 0 and this adjudication IS the sign-off plan 30:345 asks for (the PO has sealed: no further design checkpoints after the QC gate). Parts (1)+(2) — BE rename + kind disambiguation + emitter fixes + updated MCP output-schema tests — build in Wave 2 alongside G-ARC-SPEC-CRUD. Parts (3)+(4) build in Wave 2 and are CONSUMED by Wave 3 (G-MOTIF-BINDING) and Wave 7. `/review-impl` at the close of each wave, per the run policy.

*Evidence:* SHIPPED PRODUCER (the shape already exists, under the wrong name): services/composition-service/app/db/repositories/entity_references.py:138,161,186,212,222 — `"node_ref": {"kind":…, "id":…, "title":…}`; services/composition-service/app/services/agent_native.py:113,143 — `Diagnostic.node_ref`; services/composition-service/app/mcp/server.py:3998,4025,4047,4099,4125. THE AMBIGUITY: app/db/migrate.py:1102 `structure_node.kind CHECK IN ('saga','arc')` vs migrate.py:196 `outline_node.kind CHECK IN ('arc','chapter','scene','beat')` — so server.py:3998 emits `{kind:'arc'}` for a structure_node.id while server.py:4099 emits `{kind: n['kind']}` (also 'arc') for an outline_node.id; server.py:4125 emits `{kind:'chapter'}` for a BOOK-SERVICE chapter id while server.py:4099 emits it for an outline_node id. NAME COLLISION IN-SERVICE: app/db/repositories/plan_overlay.py:110 + app/routers/plan_overlay.py:195 — `node_ref` is a bare uuid STRING there. SHIPPED FE SEAMS the resolver must reuse: frontend/src/features/studio/panels/PlanHubPanel.tsx:74 (`params:{bookId, focusRuleId, focusChapterId}`) → panels/useQualityCanon.ts:74-75; host/StudioHostProvider.tsx:52-53 (`openPanel(panelId,{params})`, `focusManuscriptUnit(chapterId)`); host/types.ts:66,109 (`planFocusNode` bus event) → PlanHubPanel.tsx:121-127; host/studioLinks.ts:69 (the pure host-injected resolver pattern to mirror). THE AGENT-SIDE HOLE: services/chat-service/app/services/frontend_tools.py:391 (`ui_open_studio_panel` — `panel_id` is its ONLY property) and :493 (`ui_focus_manuscript_unit` — chapter_id/scene_id only) — no tool can carry a ref today. GATING SPECS: 28_agent_native_studio.md:615 (OQ-8, the sketch being overridden), 30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:339,345 (X-6 + Wave-0 gate), 32_arc_inspector.md:8,405 and 33_motif_studio.md:363,542 (the consumers).

### Q-30-X10-DISCOVERY-SCENT
BUILD IT — the "wait for Track C" hold is DISCHARGED (verified, not assumed): `git status --short` on `feat/context-budget-law` shows only `M .gitignore` + untracked `docs/eval/discoverability/runs/` — `stream_service.py` is COMMITTED and clean, and HEAD `9262ed53e` IS Track C's D8 ("fix(studio): unconsulted is not empty…"). §9's "DO NOT TOUCH" row is stale. X-10 is buildable now, in its wave, with no cross-track collision.

EXACT CHANGE (XS, one file + one test file):

1) `services/chat-service/app/services/stream_service.py` — hoist the tools-live predicate that is currently computed inline at line 3723 for `group_directory_block` into a named local so the scent can reuse it verbatim:
   `_tools_live = stream_format == "agui" and not disable_tools and kctx.tool_calling_enabled`
   (then `if _tools_live: group_directory_block = group_directory_text()`).

2) Extract the note into a module-level pure helper next to the other prompt-text helpers, so it is unit-testable (the enclosing assembly fn is ~500 lines and cannot be called from a unit test):
   `def build_book_context_note(book_id, chapter_id, project_id, tools_live: bool) -> str | None:` — body = exactly the existing lines 3750-3765 (verbatim: "You are working inside book_id=…", the chapter clause, the CTX-1 project_id clause, "Use these exact ids… never pass a placeholder."), PLUS, appended only when `tools_live`, the AN-9 scent sentence:
   `" To orient yourself in this book, call composition_package_tree (the book at a glance) or composition_diagnostics (what is currently wrong with it) instead of stitching several reads together; composition_find_references answers where one entity is used."`
   Call site becomes: `book_context_note = build_book_context_note(_ctx_book_id, _ctx_chapter_id, _ctx_project_id, _tools_live)`.

   The three names are verified to exist as registered MCP tools: `services/composition-service/app/mcp/server.py:3712` (`composition_package_tree`), `:3867` (`composition_find_references`), `:3935` (`composition_diagnostics`).

DECISIONS I MADE (veto-able):
- **Gated on `_tools_live`, not on `_studio`.** Spec 28 AN-9/C2 says "the *studio* book_context_note", but the three tools are book-scoped and are reached through `find_tools(group=…)` discovery, which is live on any agui tool-calling turn — a book-scoped non-studio turn has exactly the same access. Cost is ~25 tokens and only when tools are on. Naming tools on a tools-OFF turn (the case a `_studio`-only gate would still allow) is the real hazard, and `_tools_live` closes it.
- **All three tools named, not two.** Spec X-10 names only package_tree/diagnostics; find_references is +8 tokens and is the third of the same shipped trio (AN-2/3/4) with the identical "shipped but never called" risk.
- **No per-turn fetch.** Static text only — AN-9's measured-budget rule and OQ-2 (ratified NO on an auto `package_tree` call) both hold.

TEST (new file `services/chat-service/tests/test_book_context_note.py`, 4 asserts):
- `tools_live=True` + book_id ⇒ note contains all of `composition_package_tree`, `composition_diagnostics`, `composition_find_references`;
- `tools_live=False` ⇒ note contains NONE of them but still contains `book_id=`;
- `book_id=None` ⇒ returns `None` (no scent leaks onto a bookless turn);
- project_id present ⇒ the CTX-1 "a book_id is NOT a project_id" clause still lands (regression guard on the extraction).

BUDGET: no test breaks — `book_note` is already a first-class `BREAKDOWN_CATEGORIES` key (`token_budget.py:100`) counted at `stream_service.py:4091`, and `test_token_budget.py:165`'s `"book_note": 20` is a synthetic fixture, not an assertion about the real string. The ~25 added tokens are automatically measured and surfaced in the Inspector — no Context-Budget-Law violation (an always-on block that is counted).

DoD per the PO policy: `/review-impl` at wave close; AN-11's S06 replay is the effect-proof that the scent is actually consumed (`composition_package_tree` used as the verification read).

*Evidence:* services/chat-service/app/services/stream_service.py:3750-3765 (book_context_note — ids only, no tool names) · :3723 (the `stream_format=="agui" and not disable_tools and kctx.tool_calling_enabled` predicate to reuse) · :4091 (`"book_note": estimate_tokens(book_context_note)`) · services/composition-service/app/mcp/server.py:3712 / :3867 / :3935 (the three shipped tools) · docs/specs/2026-07-01-writing-studio/28_agent_native_studio.md:517-520 (AN-9: "one static addition… ~15 tokens") · `git status --short` = clean stream_service.py at HEAD 9262ed53e (Track C's D8 landed → spec 30 §9's DO-NOT-TOUCH row is stale)

### Q-30-404-CONFORMANCE-CONFIRM
RE-POINT AT THE GENERIC `POST /v1/composition/actions/confirm` — but the fix is NOT a path swap. The spec's "same fix as #1" hides three details that make a naive re-point still fail. Pure FE bug; zero backend work.

FILE: frontend/src/features/composition/motif/api.ts — replace `conformanceRunConfirm` (lines 229-236) with a body that MIRRORS the already-working `arcConformanceRunConfirm` (api.ts:277-297) in the same file:

```ts
async conformanceRunConfirm(confirmToken: string, token: string): Promise<void> {
  const resp = await apiJson<{ job_id?: string; status?: string } & Record<string, unknown>>(
    `${BASE}/actions/confirm${_qs({ token: confirmToken })}`,
    { method: 'POST', token },   // token rides the QUERY; identity is the Bearer JWT
  );
  await _resolveActionJob(resp, token);  // 202+poll to terminal; throws on failed/timeout
}
```

The four changes, each grounded:
1. PATH: `/actions/conformance_run/confirm` -> `/actions/confirm`. That is the ONLY confirm route (actions.py:58 prefix + actions.py:213 `@router.post("/confirm")`).
2. TOKEN MOVES BODY -> QUERY. actions.py:215 declares `token: str = Query(..., min_length=1)`. Keeping the JSON body `{confirm_token}` turns today's 404 into a 422 — the bug survives the "fix". Use the existing `_qs()` helper (api.ts:45).
3. DROP the JSON body entirely (no `body:`). Identity is the Bearer JWT via `get_optional_current_user` (actions.py:218); the confirm token is the capability.
4. DROP the return cast + type. `_execute_conformance_run` (actions.py:714, return at :737-742) answers `{outcome:"action_accepted", job_id, poll:"composition_get_mine_job"}` — a 202+poll JOB, never an inline conformance. So today's `(job.result as {conformance: ChapterConformance}).conformance` is a latent second bug. The caller does not need the value: `useConformanceTrace.ts:37-38`'s `confirmRun.onSuccess` only runs `setEstimate(null); invalidate()`, and that invalidate re-fetches the REAL, existing `GET /works/{pid}/conformance` (api.ts:204). Return `Promise<void>`.

PAIRED — do #1 (Q-30-404-ESTIMATE) IN THE SAME SLICE; they are one propose->confirm flow and splitting them ships a half-dead button. `conformanceRunEstimate` (api.ts:224) must MINT the token through the MCP bridge, NOT through `/actions/preview` — `/actions/preview` is a GET describe-only route (actions.py:183) that DECODES an existing token and mints nothing. Mirror `arcConformanceRunPropose` (api.ts:249): `mcpExecute<_McpProposeResult>('composition_conformance_run', { args: { project_id: projectId, scope: 'chapter', chapter_id: chapterId } }, token)` -> `{confirm_token, estimate:{estimated_usd}}`. `model_ref` is NOT required for chapter scope (server.py:3141-3143 requires only chapter_id; model_ref is arc-only, server.py:3148-3151).

TESTS (frontend/src/features/composition/motif/__tests__/): (a) assert `conformanceRunConfirm` issues POST to a URL matching /\/actions\/confirm\?token=/ AND sends NO request body; (b) assert `conformanceRunEstimate` calls `mcpExecute('composition_conformance_run', {args:{scope:'chapter',...}})` and never fetches a URL containing 'conformance_run/estimate'; (c) BUG-CLASS GUARD — assert no string literal in motif/api.ts matches /actions\/[a-z_]+\/(estimate|confirm)/, which kills the whole per-action-route class that §8.1 forbids ("never a per-action route") rather than just these two instances.

Blast radius is contained: the ONLY callers are useConformanceTrace.ts:32 and :36. Aligns with sealed §8.1; contradicts no §0 PO decision. NOT deferrable — it is a shipped live 404 on a paid Tier-W action, fixed in one file.

*Evidence:* services/composition-service/app/routers/actions.py:58 (prefix `/v1/composition/actions`), :183 (`@router.get("/preview")`), :213-215 (`@router.post("/confirm")` + `token: str = Query(..., min_length=1)` — token is a QUERY param, not a body field), :218 (`jwt_user = Depends(get_optional_current_user)`), :714+:737-742 (`_execute_conformance_run` returns `{outcome:"action_accepted", job_id, poll}` = 202+poll, not inline conformance). BROKEN CALLER: frontend/src/features/composition/motif/api.ts:229-236 (`POST ${BASE}/actions/conformance_run/confirm` with `body: JSON.stringify({confirm_token})` — route does not exist). WORKING SIBLING TO COPY: api.ts:277-297 `arcConformanceRunConfirm` -> `${BASE}/actions/confirm${_qs({ token: confirmToken })}`, `{method:'POST', token}`, then poll (same pattern at api.ts:118-121 adoptConfirm, :163 mineConfirm). MINT PATH: services/composition-service/app/mcp/server.py:3121-3180 (`composition_conformance_run`, `scope: Literal["chapter","arc"]`, returns `confirm_token` + `estimate`); FE mirror at api.ts:249 `arcConformanceRunPropose`. CALLERS: frontend/src/features/composition/motif/hooks/useConformanceTrace.ts:32,36 (only two).

### Q-30-BE1-DIAGNOSTICS-REST
BUILD IT. The only gate was PO-1 (AN-12 amendment), and §0 seals it YES — so BE-1 is a work item, not an open question. But the spec's framing ("a near-mechanical lift of the ~120-line MCP handler") invites the exact bug this repo has shipped before (a duplicated computation that drifts — see the CSS-var lesson the tool's OWN test docstring cites). So the binding instruction is EXTRACT, DO NOT COPY:

1) EXTRACT the engine into a shared service function. In `services/composition-service/app/services/agent_native.py` (which already owns `SEVERITY`, `Diagnostic`, `Diagnostics.ranked`, and today has ZERO async/DB code) add:
   `async def compute_diagnostics(*, pool, user_id: UUID, book_id: UUID, limit: int = 25) -> dict:`
   Its body is verbatim `app/mcp/server.py` lines 3961→4137: `resolve_scope(WorksRepo(pool), bid)`, the `cap = max(1, min(int(limit or 25), 100))` clamp (KEEP the clamp inside the shared fn — both callers inherit it), the `pid is None` "absent, not zero" warning, and all 6 sources (conformance+index staleness, canon_issues, rule_violations, open thread debt, prose_deleted, unplanned chapters), ending in `return {"book_id": str(bid), **diag.ranked(cap=cap)}`. Two substitutions: `tc.user_id` → the `user_id` param (used by `mint_service_bearer(user_id, settings.jwt_secret)` in the prose-deleted + coverage sources), and `get_pool()` → the `pool` param. The grant gate does NOT move into the shared fn — each caller gates in its own idiom.

2) MCP tool shrinks to a 3-liner. `composition_diagnostics` (server.py:3950) keeps its `@mcp_server.tool` decorator + `require_meta("R","book", …)` unchanged and becomes:
   `tc = _ctx(ctx); bid = UUID(book_id); await _gate(tc, bid, GrantLevel.VIEW); return await compute_diagnostics(pool=get_pool(), user_id=tc.user_id, book_id=bid, limit=limit)`

3) NEW REST route. New file `services/composition-service/app/routers/diagnostics.py`, `router = APIRouter(prefix="/v1/composition")`, copying the gate shape of `routers/conformance.py:424-450` EXACTLY:
   `@router.get("/books/{book_id}/diagnostics")` · `book_id: UUID` · `limit: int = Query(25, ge=1, le=100)` · `user_id: UUID = Depends(get_current_user)` · `grant: GrantClient = Depends(get_grant_client_dep)` · `try: await authorize_book(grant, book_id, user_id, GrantLevel.VIEW) except OwnershipError: 404 "book not found" / except InsufficientGrant: 403 "insufficient access"` (H13 uniform) · then `return await compute_diagnostics(pool=get_pool(), user_id=user_id, book_id=book_id, limit=limit)`.
   Register it in `app/main.py` next to conformance (line 244): `app.include_router(diagnostics.router)`.

4) Response contract for Wave 7's FE (`diagnosticsEffects.ts`) is BIT-IDENTICAL to the MCP payload — freeze it now: `{book_id, items:[{kind, severity, title, detail?, node_ref?:{kind,id,title}, at?}], counts:{<kind>:n} (EXACT, never capped), total, refs_capped, warnings?:[str]}` (agent_native.py:128-152). The Issues tab MUST render `warnings` and `refs_capped` — a truncated/degraded read that displays as a clean count is the "absent-vs-zero" bug the engine's comments were written to prevent.

5) TESTS — the extraction WILL red three existing tests; fixing them is part of the slice, not a surprise. `tests/unit/test_agent_native.py:165` and `:178` call `inspect.getsource(server.composition_diagnostics)` and assert `compute_conformance_status(` / `canon_issues(` / `list_open(` / `compute_coverage(` are in it and `conformance_run(` is not. Repoint BOTH at `inspect.getsource(agent_native.compute_diagnostics)`, keeping the `require_meta("R","book")` assertion pointed at `server`. Then ADD, in a new `tests/unit/test_diagnostics_route.py`: (a) 200 → items ranked error→warn→info with exact `counts`; (b) 403 without VIEW; (c) 404 on a foreign/missing book; (d) a book with no composition work (`pid is None`) → the "absent, not zero" warning is present in the JSON; (e) `limit=500` → 422 (Query le=100) and `limit=25` default.

6) GATEWAY: ZERO work — confirmed, do not touch it. `services/api-gateway-bff/src/gateway-setup.ts:354` is `pathFilter: (pathname) => pathname.startsWith('/v1/composition')`, i.e. generic prefix forwarding; the new GET is proxied on day one.

DEFAULT I AM PICKING (veto-able): `limit` is a hard 422 above 100 on the REST side (Query ge=1,le=100) rather than the MCP's silent clamp — a human GUI caller should learn its bound, an LLM should not be refused. The shared clamp still protects both.

*Evidence:* Gate cleared: docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:19 (PO-1 sealed — AN-12's "no new GUI surface" clause lifted for composition_diagnostics). Engine to extract: services/composition-service/app/mcp/server.py:3950-4137 (handler body; clamp at :3966, six sources, `return {"book_id": …, **diag.ranked(cap=cap)}` at :4137). Shared types already homed: services/composition-service/app/services/agent_native.py:58-152 (SEVERITY map + Diagnostics.ranked payload shape). Route pattern to mirror verbatim: services/composition-service/app/routers/conformance.py:424-450 (`@router.get("/books/{book_id}/conformance/status")` + authorize_book/OwnershipError→404/InsufficientGrant→403), router prefix at conformance.py:63, registration at services/composition-service/app/main.py:244. Zero gateway work confirmed: services/api-gateway-bff/src/gateway-setup.ts:354 `pathFilter: (pathname: string) => pathname.startsWith('/v1/composition')`. Tests that WILL red on extraction: services/composition-service/tests/unit/test_agent_native.py:165,171,178,184 (`inspect.getsource(server.composition_diagnostics)`).

### Q-30-PO3-SHOWPANEL-NONSTUDIO-PATH
**Answer: neither (a) nor (b) as written — RETIRE `ui_show_panel` OUTRIGHT. Build no non-studio path and no migration shim, because the code proves there are ZERO working non-studio call sites to preserve.** This is consistent with §0 PO-3 ("RETIRE ui_show_panel", one name for one concept); it only voids PO-3's *caveat*, which rests on a false premise. The non-studio panel intent is already covered by `ui_open_book(tab)` + `ui_navigate`; the studio intent is covered by `ui_open_studio_panel` + the existing interceptor. If the PO disagrees, the veto-able default they'd be overriding is: "a non-studio chat can no longer say 'open a panel' by that name — it says `ui_open_book(tab=…)` or `ui_navigate(path)` instead."

WHY (grounding): `ui_show_panel` resolves to `<current pathname>?panel=X` (uiNav.ts:115-131) and NO page in the app reads `?panel=` — the sole reader is PopoutHost.tsx:27 on the `/composition/popout` route (App.tsx:112), a popout window fed by PopoutBridge.tsx:39, never a chat surface. The tool is therefore a silent `shown:true` no-op on EVERY surface, non-studio included. Nothing works today, so nothing can break.

BUILDER INSTRUCTION — Wave 0 / X-5, exact edits:

BACKEND (services/chat-service):
1. `app/services/frontend_tools.py:52` — delete `"ui_show_panel",` from `FRONTEND_TOOL_NAMES`.
2. `app/services/frontend_tools.py:336-359` — delete the whole `UI_SHOW_PANEL_TOOL` dict.
3. `app/services/frontend_tools.py:655` — delete the `"ui_show_panel": UI_SHOW_PANEL_TOOL,` entry from `_GENERIC_FRONTEND_TOOLS_BY_NAME`.
4. `app/services/frontend_tools.py:36` — drop `ui_show_panel` from the C-NAV comment list.
5. `app/services/tool_discovery.py:258` — delete `"ui_show_panel",` from `ALWAYS_ON_CORE_NAMES` (core drops 10→9; the ≤10 ceiling still holds).
6. `app/services/stream_service.py:2362-2371` — COMMENT ONLY. The `_unwrap_wrapped_args(..., _fe_def)` logic is schema-generic; reword the sentence "Protect ui_show_panel's real `args` param via its schema" to name a surviving open-bag tool (or state it generically). **Do not touch the logic.**

FRONTEND:
7. `frontend/src/features/chat/nav/uiNav.ts:19` — remove `'ui_show_panel'` from `UI_TOOL_NAMES`; `:115-131` — delete the entire `case 'ui_show_panel'` block. Leave `ui_navigate`/`ui_open_book`/`ui_open_chapter`/`ui_watch_job` untouched.
8. `frontend/src/features/chat/utils/serverKey.ts:37` — remove `'ui_show_panel'` from `FRONTEND_TOOL_NAMES`.
9. Do NOT add `ui_show_panel` to `STUDIO_UI_TOOLS` or to `makeStudioNavInterceptor` (studioUiNav.ts:11, :53-83). Do NOT alias it inside `resolveStudioUiTool`. (The `panel`/`page` alias tolerance at studioUiNav.ts:32 already catches a model that reaches for the old name while calling `ui_open_studio_panel` — that stays.)

CONTRACT + TESTS (the green gate PO-3 requires):
10. Regenerate the cross-language contract: `WRITE_FRONTEND_CONTRACT=1 python -m pytest services/chat-service/tests/test_frontend_tools_contract.py` → `contracts/frontend-tools.contract.json` must drop the `ui_show_panel` key (12→11 tools). `test_every_advertised_name_has_exactly_one_schema` (test_frontend_tools_contract.py:103) is the machine check that both sides agree.
11. Update/remove the `ui_show_panel` cases in: `services/chat-service/tests/test_frontend_tools.py`, `test_tool_discovery.py`, `test_agent_surface.py`, `frontend/src/features/chat/nav/__tests__/uiNav.test.ts`, `frontend/tests/e2e/specs/frontend-tools-liveness.spec.ts`.
12. ADD two regression tests (no-silent-no-op, the rule X-5 exists to enforce):
    - py: assert `"ui_show_panel" not in FRONTEND_TOOL_NAMES` and `is_frontend_tool("ui_show_panel") is False` — so a model that still emits the retired name is dispatched to the backend, gets a real tool-not-found error envelope back, and self-corrects, rather than being suspended and resolved with a fabricated `shown:true`.
    - ts: assert `isUiTool('ui_show_panel') === false` and `resolveUiTool('ui_show_panel', {panel:'glossary'})` returns `{path: null, result: {}}` (the `default` branch) — never a `shown:true`.
13. Coverage assertion to put in the wave's DoD: every panel `ui_show_panel` could plausibly have targeted outside the studio is reachable via `ui_open_book.tab` ∈ {overview, translation, glossary, enrichment, wiki, settings} or an `ALLOWED_NAV_PREFIXES` route. No new tool, no new route.
14. Wave 0 DoD (per the PO's binding policy): `/review-impl` runs at wave close; any bug it finds is fixed before the wave closes. Live-smoke evidence for X-5 = a studio browser smoke where the agent is asked to "open the glossary" and a dock tab actually appears (verify by EFFECT, not raw stream).

NOTE for X-5's sibling (`ui_watch_job`), which the same row covers and which this decision does NOT retire: it stays a live tool, and it DOES need the interceptor treatment — add `ui_watch_job` to the studio interceptor in `studioUiNav.ts` `makeStudioNavInterceptor` (a new `case 'ui_watch_job'` returning `{path: null, result: {watching: true}, effect: (host) => host.openPanel('job-detail', {params: {jobId}})}`) so it stops route-navigating to `/jobs?focus=` and tearing down the dock (uiNav.ts:132-136).

*Evidence:* frontend/src/features/chat/nav/uiNav.ts:115-131 (`ui_show_panel` → `` `${window.location.pathname}?panel=${panel}` ``, returns `{shown:true}`) + the ONLY `?panel=` reader in the whole FE: frontend/src/features/composition/components/workspace/PopoutHost.tsx:27 (`params.get('panel')`), mounted at `/composition/popout` (frontend/src/App.tsx:112) and fed by PopoutBridge.tsx:39 — never a chat surface ⇒ ui_show_panel is a silent no-op everywhere, so there are no working non-studio call sites to migrate or replace. Replacement coverage already exists: services/chat-service/app/services/frontend_tools.py:296-300 (`ui_open_book.tab` enum = overview|translation|glossary|enrichment|wiki|settings) and uiNav.ts:30-46 (`ALLOWED_NAV_PREFIXES`). Advertising site to strip: services/chat-service/app/services/tool_discovery.py:258 (`ALWAYS_ON_CORE_NAMES`). Studio side already sound: frontend/src/features/studio/agent/studioUiNav.ts:11,53-83 (`STUDIO_UI_TOOLS` + interceptor, which never handled ui_show_panel).

### Q-30-BE3-ARTIFACT-READ
BUILD THE ROUTE — it is unbuilt work, not a blocker, and the repo layer is already done. Four slices, plus one correction to the question's premise.

SLICE 1 (BE, repo) — NOTHING TO DO. Do NOT use `latest_artifact` (plan_runs.py:246) as the question suggests: it reads by KIND. Use the EXISTING `artifacts_by_ids(book_id, run_id, ids)` (plan_runs.py:265-286) — a by-ID read already gated by `JOIN plan_run r ON r.id = a.run_id WHERE a.run_id=$1 AND r.book_id=$2`. Tenancy is already correct: a foreign/other-book artifact_id is simply not returned, so it 404s rather than reading across a book boundary. Do not add a new query.

SLICE 2 (BE, service) — in `services/composition-service/app/services/plan_forge_service.py`, add next to `get_run_detail` (line 319):
  async def get_artifact(self, created_by, book_id, run_id, artifact_id) -> dict|None:
      run = await self._runs.get_for_book(book_id, run_id)
      if run is None: return None
      found = await self._runs.artifacts_by_ids(book_id, run_id, [artifact_id])
      art = found.get(str(artifact_id))
      if art is None: return None
      return {"id": str(art.id), "run_id": str(run_id), "kind": art.kind, "content": art.content,
              "created_at": art.created_at.isoformat() if art.created_at else None}

SLICE 3 (BE, route) — in `services/composition-service/app/routers/plan_forge.py`, immediately after `get_plan_run` (ends line 156):
  @router.get("/books/{book_id}/plan/runs/{run_id}/artifacts/{artifact_id}")
  async def get_plan_artifact(book_id: UUID, run_id: UUID, artifact_id: UUID,
      user_id=Depends(get_current_user), grant=Depends(get_grant_client_dep), svc=Depends(get_plan_forge_service)):
      await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)     # VIEW — same read tier as get_plan_run
      art = await svc.get_artifact(user_id, book_id, run_id, artifact_id)
      if art is None: raise HTTPException(status_code=404, detail="artifact not found")
      return art
TESTS in `services/composition-service/tests/unit/test_plan_forge_router.py`: (a) 200 returns `content`; (b) 404 on unknown artifact_id; (c) TENANCY — artifact_id belonging to book B requested under book A returns 404, never the body; (d) 403 with no VIEW grant.

SLICE 4 (MCP, GG-2's inverse law) — add tool `plan_get_artifact` in `services/composition-service/app/mcp/server.py` beside `plan_pass_status` (line 3633): args {book_id, run_id, artifact_id}, `require_meta("R", "book", synonyms=["read artifact","open plan artifact","show spec body"], tool_name="plan_get_artifact")`, wrapping the SAME `svc.get_artifact`. The audit's own finding is that no such tool exists; a read wrapper is cheap and closes the agent half of the loop.

SLICE 5 (FE) — the `json-editor` panel ALREADY EXISTS (`frontend/src/features/studio/panels/catalog.ts:208`, JsonEditorPanel, hiddenFromPalette) driven by the `JsonDocumentProvider` registry (`frontend/src/features/studio/documents/types.ts:44-55`) and opened as `json-editor:{docType}:{resourceId}` (StudioHostProvider.tsx:50). Register provider `loreweave.plan-artifact.v1` whose `open()` GETs the Slice-3 route. Make PlanRunView's existing `{kind, artifact_id}` refs CLICKABLE → open that doc. This closes spec-12 cycle-gate item 5 as the question predicts.

DEFAULT I AM SETTING (PO may veto): artifacts open READ-ONLY in v1 — the provider's `save()` is absent and JsonEditorPanel hides Save for this docType. Reason: artifacts are pass OUTPUTS, and a hand-edit to e.g. `scene_plan` would desync PF-3's input fingerprints; the one artifact that SHOULD be writable (`spec`) already has its own write path (`PATCH .../novel-system-spec`, plan_forge.py:159). Do not add a generic artifact-write route — that would bypass the compiler's provenance.

CORRECTION — THE QUESTION IS WRONG THAT THIS ROUTE "ALSO SOLVES THE SOURCE-MARKDOWN RESUME." IT DOES NOT. `source_markdown` is a COLUMN on `plan_run` (migrate.py:1265 `source_markdown TEXT NOT NULL DEFAULT ''`), not an artifact. plan_forge_service.py:968-979 states this explicitly: the `document` artifact stores only PARSED sections + a checksum, "the raw text is not there. I reached for the artifact first and it silently returned ''". And `_serialize_run` never emits it. So the artifact route alone leaves the resume field EMPTY — a silent-success bug. SLICE 6 (one line, do it in the same wave): give `_serialize_run` an `include_source: bool = False` kwarg that adds `"source_markdown": run.source_markdown`, and have `get_run_detail` (line 326) pass `include_source=True`. Detail path ONLY — `_serialize_run` is shared with `list_runs` (line 337), and a 256KB field (the router's `_SOURCE_MARKDOWN_MAX`, plan_forge.py:38) times a 50-item page is a 13MB list response. Test: run DETAIL returns source_markdown; run LIST does not.

DoD per the PO policy: `/review-impl` runs at wave close; any bug it finds is fixed before the wave closes.

*Evidence:* GAP CONFIRMED: services/composition-service/app/routers/plan_forge.py:94-375 registers 14 plan routes (create/list/get/patch-spec/validate/refine/passes/link/checkpoint/run-pass/interpret/self-check/compile) — NO /artifacts/{artifact_id}; the only add_api_route calls in the service (authoring_runs.py:275-281) are start/resume transitions, so no route hides from the grep. services/composition-service/app/mcp/server.py — no plan_get_artifact tool; every "artifact" hit (lines 3448, 3466-3467, 3636, 3682) is prose inside a tool DESCRIPTION. services/composition-service/app/services/plan_forge_service.py:384-388 returns `"artifacts": [{"kind": a["kind"], "artifact_id": str(a["artifact_id"])}]` — refs only, body unreachable.
ALREADY-BUILT REPO METHOD (reuse, do not rewrite): services/composition-service/app/db/repositories/plan_runs.py:265-286 `artifacts_by_ids(book_id, run_id, ids)` — by-ID + book-scoped via `JOIN plan_run r ON r.id = a.run_id WHERE a.run_id=$1 AND r.book_id=$2` (the by-KIND `latest_artifact` at :246 is the WRONG method for this route).
SOURCE-MARKDOWN CLAIM REFUTED: services/composition-service/app/db/migrate.py:1265 `source_markdown TEXT NOT NULL DEFAULT ''` on plan_run (a column, not an artifact) + services/composition-service/app/services/plan_forge_service.py:968-979 docstring: "NOT on the `document` artifact: `ingest_markdown` stores only the PARSED sections plus a checksum, so the raw text is not there. I reached for the artifact first and it silently returned ''."
FE TARGET EXISTS: frontend/src/features/studio/panels/catalog.ts:208 (`json-editor` → JsonEditorPanel, hiddenFromPalette) + frontend/src/features/studio/documents/types.ts:44-55 (JsonDocumentProvider) + frontend/src/features/studio/host/StudioHostProvider.tsx:50 (`json-editor:{docType}:{resourceId}` per-resource instances).

### Q-30-404-CONFORMANCE-ESTIMATE
DELETE the invented chapter Tier-W re-run flow — do NOT re-point it at any spine. The spec's candidate answer (§8.1) is WRONG on mechanism and, if built, ships a CRITICAL paid-action defect. Two facts settle it: (a) /actions/preview is a GET that DECODES an existing confirm token (actions.py:189, "NO side effects") — it cannot MINT one; there is no REST mint route, minting is the MCP tool. (b) The conformance_run WORKER terminally rejects scope='chapter' (motif_conformance_run.py:74-78) — while composition_conformance_run (server.py:3141) happily MINTS for scope='chapter' and /actions/confirm → _execute_conformance_run (actions.py:714) ledger-claims + billing-prechecks (_precheck_or_402) + enqueues. So wiring the chapter FE to the "real" spine turns a harmless 404 into a PAID job guaranteed to fail — the motif-mine twin the PO named CRITICAL. Chapter conformance is already FREE + SYNCHRONOUS via GET /works/{project_id}/conformance?scope=chapter&chapter_id= (conformance.py:334; _assemble_conformance reads stored per-scene verdicts, no LLM) and the hook ALREADY calls it (motifApi.conformance). "Re-run" for chapter = refetch.

BUILDER STEPS (Wave 3c, G-CONFORMANCE-TRACE):
1. frontend/src/features/composition/motif/api.ts — DELETE conformanceRunEstimate (line 223) and conformanceRunConfirm (line 228) outright. Do NOT re-point them. KEEP arcConformanceRunPropose/arcConformanceRunConfirm (lines ~103/140) — those are correct and are the model for any future paid flow.
2. frontend/src/features/composition/motif/hooks/useConformanceTrace.ts — delete the `estimate` useState, `mintRun`, `confirmRun`, `cancelRun`, and the now-unused CostEstimate import. Keep query/regenerateToBeat/refetch. Export `rerun: () => query.refetch()` and `isFetching: query.isFetching`.
3. frontend/src/features/composition/motif/components/ConformanceTraceView.tsx — the [data-testid=conformance-rerun] button (lines 41-46) calls trace.rerun(), disabled={!projectId || !chapterId || trace.isFetching}. DELETE the CostConfirmCard block (lines 50-58) and its import (line 7). No cost card, no confirm — the read is free.
4. TEST (guards the regression): assert clicking [data-testid=conformance-rerun] fires exactly ONE request — a GET to /v1/composition/works/:pid/conformance?scope=chapter&chapter_id=… — and that NO request to any /actions/* path is made.
5. HARDEN AT SOURCE (same slice, ~4 lines — the FE fix alone does NOT close this, because an LLM can still call the tool directly): in services/composition-service/app/mcp/server.py:3141, make composition_conformance_run REFUSE to mint what the worker cannot run — for scope=='chapter' return {"success": False, "error": "chapter conformance is a free synchronous read (GET …/conformance?scope=chapter) — no run needed"} instead of minting a confirm token. No live caller can regress: the worker rejects chapter today, so no chapter mint has ever succeeded. Add a unit test asserting scope='chapter' returns success:False and mints NO confirm_token.

DEFER ROW to file alongside (the genuine gap, so it is not silently dropped) — ID: D-MOTIF-CONFORMANCE-ENGINE-WIRING (the worker already names it); origin: Wave 3c / Q-30-404-CONFORMANCE-ESTIMATE; what: the PAID per-scene extract-diff chapter re-run does not exist (worker is arc-only); gate reason: 3 (naturally-next-phase — the chapter extract-diff engine is unbuilt; this is not "blocked", it is a real unbuilt slice, but it is out of Wave 3c's scope, which is GUI wiring); target: whenever the chapter extract-diff engine is scoped. Until then chapter conformance is a read-only refresh and the button must not pretend to spend.

PO VETO POINT (default I picked, flag if you disagree): the "Re-run" button stays visible but becomes a free refresh rather than a cost-gated action. If you want the chapter re-run to genuinely re-compute per-scene verdicts with an LLM, that is the D-MOTIF-CONFORMANCE-ENGINE-WIRING build, not a wiring fix.

*Evidence:* services/composition-service/app/engine/motif_conformance_run.py:74-78 — `scope = input.get("scope"); if scope != "arc": raise ValueError("conformance_run worker supports scope='arc' only (got {scope!r}); chapter conformance is the synchronous GET trace (tracked D-MOTIF-CONFORMANCE-ENGINE-WIRING)")` — the worker terminally rejects chapter. Corroborating: services/composition-service/app/mcp/server.py:3136-3151 (composition_conformance_run accepts Literal["chapter","arc"] and MINTS a confirm token for chapter); services/composition-service/app/routers/actions.py:714-742 (_execute_conformance_run: _claim_or_replay → _precheck_or_402 → _enqueue_motif_job — the billing precheck fires BEFORE the worker's ValueError); services/composition-service/app/routers/actions.py:183-189 (GET /preview only DECODES a token, "NO side effects" — it cannot mint); services/composition-service/app/routers/conformance.py:334,405,417 (GET /works/{project_id}/conformance?scope=chapter — free synchronous read, _assemble_conformance, no LLM); frontend/src/features/composition/motif/api.ts:223,228 (the two invented URLs); frontend/src/features/composition/motif/api.ts:103,140 (arcConformanceRunPropose/Confirm — the CORRECT spine, mcpExecute + /actions/confirm?token=); frontend/src/features/composition/motif/components/ConformanceTraceView.tsx:41-58 (the button + CostConfirmCard to delete).

### Q-30-BE6-VS-BE7-ARC-SUGGEST-DUPE
BE-7b / spec 34 is the SOLE OWNER of arc-suggest. Spec 33's BE-M5 (`GET /books/{bid}/arcs/suggest?limit=10`) is DELETED — it was not merely redundant, it was the WRONG contract. Build exactly ONE route, in Wave 4 (spec 34 M3); Wave 3 ships nothing arc-suggest-shaped.

BUILDER INSTRUCTION (no further thought required):
1. FILE: `services/composition-service/app/routers/arc.py` (router already `APIRouter(prefix="/v1/composition")` at arc.py:63; mounted at `main.py:228`). Add `@router.post("/arc-templates/suggest")` near the other `/arc-templates` routes. It does NOT collide with `POST /arc-templates` (arc.py:172) or `POST /arc-templates/{arc_id}/adopt` (arc.py:249).
2. BODY (Pydantic, mirror the tool EXACTLY): `{project_id: str, premise: str|None = None, genre: str|None = None, limit: int = 5, detail: Literal['summary','full'] = 'full'}`. NO `book_id` path segment. Default `limit=5`, NOT 10. Keep `detail` (Context Budget Law §6b).
3. HANDLER: mirror `composition_arc_suggest` (services/composition-service/app/mcp/server.py:2287-2325) line-for-line — `WorksRepo(get_pool())` → `_book_or_deny(works, tc, UUID(project_id), GrantLevel.VIEW)` (uniform H13 404 on deny) → `MotifRetriever(get_pool()).retrieve_arcs(tc.user_id, book_id=meta.book_id, project_id=pid, premise=premise, genre=genre, limit=limit)` → owner-vs-public projection → `apply_response_contract(..., ref_fields=_ARC_REF_FIELDS, detail=detail)` → return `{candidates: [{arc_template, score, match_reason}], **meta}`. Do NOT drop `match_reason` — it is the only explanation the user gets for a ranked list.
4. TESTS: (a) VIEW-grant gate → uniform 404 for a non-grantee (no existence oracle); (b) `candidates[i].match_reason` present in the response; (c) `detail='summary'` returns arc_template refs only while keeping score + match_reason; (d) a guard test asserting NO route matching `/books/{book_id}/arcs/suggest` exists (kills the deleted duplicate for good).
5. OPENAPI: add BE-7b to `contracts/api/` (spec 34 §5: specs 23 and 24 both left this undone — do not compound it).
6. FE: the "Suggest an arc ✨" button lives on `arc-inspector` / `arc-templates` (Wave 4), NOT on `motif-library`. Wave 3 ships MOTIF-suggest only (BE-M4, `GET /v1/composition/works/{project_id}/motifs/suggest`).

NOTE: the specs on disk ALREADY encode this — 30 §BE-6/BE-7 (lines 299-300), 33 §3.3 (lines 372-375 + the struck BE-M5 row at 445), 34 §5 BE-7b (line 206) all agree. No spec edit is required; the builder must simply not follow spec 33's pre-strike prose. Consistent with §0 PO-1..4 (nothing here touches them).

*Evidence:* services/composition-service/app/mcp/server.py:2287-2295 — `async def composition_arc_suggest(ctx, project_id: str, premise=None, genre=None, limit: int = 5, detail: Literal["summary","full"]="full")`; VIEW gate at server.py:2308 (`_book_or_deny(works, tc, pid, GrantLevel.VIEW)`); engine call at server.py:2310 (`retriever.retrieve_arcs(...)`, repo at services/composition-service/app/db/repositories/motif_retrieve.py:279). No REST arc-suggest route exists at HEAD: grep of services/composition-service/app/routers/*.py for "suggest" yields only engine.py:1397 `POST /works/{project_id}/scenes/{node_id}/suggest-cast`. Target router: services/composition-service/app/routers/arc.py:63 (prefix `/v1/composition`), included at services/composition-service/app/main.py:228. Spec agreement: docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:299-300; 33_motif_studio.md:445 (BE-M5 struck as duplicate + wrong contract); 34_arc_templates_and_deconstruct.md:206 (BE-7b contract).

### Q-30-404-MOTIF-MINE-POLL
BUILD BE-7c EXACTLY AS THE SPEC STATES, IN WAVE 3 (3a), BEFORE MotifMinePanel ships. The code confirms the defect end-to-end; nothing here is a product call. Zero migration needed (`created_by` already exists on `generation_job`).

**1 · NEW ROUTE — `services/composition-service/app/routers/engine.py`, immediately after `get_job` (:1428).** Router prefix is already `/v1/composition` (engine.py:82), so the literal segment `motif-jobs` cannot collide with `/jobs/{job_id}`:
```python
@router.get("/motif-jobs/{job_id}")
async def get_motif_job(
    job_id: UUID,
    user_id: UUID = Depends(get_current_user),
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
) -> dict[str, Any]:
    """Owner-scoped read of a Work-LESS async job (mine_motifs / analyze_reference /
    conformance_run). Those rows carry a SYNTHETIC project_id (actions.py:552) with no
    composition_work row, so GET /jobs/{id}'s Work/book gate 404s forever. A Work-less
    job has no book to gate on — its scope key is its OWNER. Uniform 404 (no oracle)."""
    job = await jobs.get(job_id)
    if job is None or job.created_by != user_id:
        raise HTTPException(status_code=404, detail="job not found")
    return job.model_dump(mode="json")
```
No `works`/`grant` deps at all. **NEVER back-fill a real project_id at actions.py:552, and do NOT touch `GET /jobs/{id}` (:1415)** — the Work gate is correct for Work-bound jobs (collaborator polling of an engine job still works).

**2 · MCP TOOL — `services/composition-service/app/mcp/server.py:3205-3221`.** Drop the `project_id` parameter entirely (the caller can never know the synthetic pid). Remove `_book_or_deny` + the `job.project_id != pid` assertion; replace with `if job is None or job.created_by != tc.user_id: raise uniform_not_accessible()`. Change `require_meta("R", "book", …)` → `require_meta("R", "user", …)` (the pattern already used by `composition_motif_search`, server.py:2083). Keep the name, tier R, and synonyms. Update the tool description ("VIEW on the book required" → "Your own job only"). Update the composition row in `docs/specs/2026-06-26-public-mcp/05-tool-scope-map.md:35` if it records a scope.

**3 · FRONTEND.** Add to `frontend/src/features/composition/api.ts` next to `getJob` (:420): `getMotifJob(jobId, token) => apiJson(\`${BASE}/motif-jobs/${jobId}\`, { token })`. Repoint the THREE Tier-W action polls in `frontend/src/features/composition/motif/api.ts` off `compositionApi.getJob` onto `getMotifJob`: `mineConfirm` (:172,:175), `arcConformanceRunConfirm` (:286,:289), `_resolveActionJob` (:335,:338). All three poll a job the caller itself just confirmed, so `created_by == caller` always holds — including conformance, which is safe under the owner gate even though it has a real project_id. Leave `compositionApi.getJob` in place for the engine/critic jobs (`CriticPanel.tsx:35`, `api.ts:59`). On 404 the panel must render an ERROR, never spin (spec 34 AT-11) — no spinner-until-timeout papering over it.

**4 · TESTS (the shipped test MOCKED the poll — that mock is why this shipped).**
- BE router test (new, `services/composition-service/tests/unit/`): (a) owner GETs `/v1/composition/motif-jobs/{id}` for a job whose `project_id` has NO `composition_work` row → **200** with status/result; (b) a different `created_by` → **404** with the identical body as (c) a missing id → **404**; (d) regression: the SAME job id through `GET /v1/composition/jobs/{id}` still 404s — this documents why the route exists.
- MCP test (`tests/unit/test_motif_mcp.py`): replace `test_get_mine_job_foreign_project_uniform` with `test_get_mine_job_foreign_owner_uniform`; add a happy-path call passing ONLY `job_id`.
- FE test (`frontend/src/features/composition/motif/__tests__/MotifMine.test.tsx:56`): **delete the `vi.spyOn(motifApi, 'mineConfirm')` mock for at least one case** and instead stub the HTTP layer, asserting the poll URL is `/v1/composition/motif-jobs/{id}` and NEVER `/v1/composition/jobs/{id}`.
- Live smoke (this is a paid path — mandatory at wave close): real `composition_motif_mine` propose → confirm → poll the new route to terminal; paste the terminal JSON.

**Default I picked (veto-able):** all three motif action polls move to the owner-gated route, not just mine/import. Rationale: one route covers all three async ops (spec 33 §4), and the confirming user is always the poller. The only behavior lost is a *collaborator* polling someone else's conformance job — which no shipped GUI does.

*Evidence:* actions.py:552 (`pid = project_id if project_id is not None else uuid4()`) + actions.py:644/:694 (`project_id=None`) → engine.py:1415-1428 `get_job` → `_gate_work(..., job.project_id)` → engine.py:225-227 `works.get()` → None → `HTTPException(404, "work not found")`, always. MCP twin: server.py:3205-3221 (`project_id` arg → `_book_or_deny` → `job.project_id != pid` → uniform deny). FE dead poll: frontend/src/features/composition/motif/api.ts:172 → frontend/src/features/composition/api.ts:420 (`GET ${BASE}/jobs/${jobId}`). Owner key already present: services/composition-service/app/db/repositories/generation_jobs.py:48 `_SELECT_COLS` includes `created_by` (no migration). Gateway needs no change: services/api-gateway-bff/src/gateway-setup.ts:354 proxies all `/v1/composition`.

### Q-30-BE2-PLAN-AUTOFIX-ROUTE
BUILD THE ROUTE (thin wrapper) — but NOT as a copy of /refine. The spec line "Mirror /refine's 202-ack shape" is FACTUALLY WRONG and will break the build: `handoff_autofix` returns a single `dict | None`, not the `(mode, payload)` tuple `refine`/`compile` return. Copy the `/self-check` route instead. Exact instructions:

1) `services/composition-service/app/routers/plan_forge.py` — add a request model beside the others (near `PlanCompileRequest`, ~line 63):
```python
class PlanAutofixRequest(BaseModel):
    """HTTP mirror of `plan_handoff_autofix` (mcp/server.py:3499) — same service call, same gate.
    model_ref is OPTIONAL (omit → the author's default planner model), unlike PlanRefineRequest."""
    model_ref: UUID | None = None
    max_rounds: int = Field(default=3, ge=1, le=5)
```
(`ge=1, le=5` gives a 422 on garbage; the service already clamps identically at plan_forge_service.py:836 `max(1, min(int(max_rounds), 5))` — keep both.)

2) Same file — add the route immediately AFTER `self_check_plan_run` (ends line 373), before `compile_plan_run`:
```python
@router.post("/books/{book_id}/plan/runs/{run_id}/autofix")
async def handoff_autofix_route(
    book_id: UUID,
    run_id: UUID,
    body: PlanAutofixRequest,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: PlanForgeService = Depends(get_plan_forge_service),
):
    """Bounded self-check→refine loop. Returns 200 {rounds, run} — NOT a 202: the service
    returns one dict, and its embedded `run` already carries active_job_id + job_status
    (plan_forge_service.py:369-370), which is what the caller polls when a round enqueued."""
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)   # EDIT — matches mcp/server.py:3510
    try:
        out = await svc.handoff_autofix(
            user_id, book_id, run_id,
            model_ref=body.model_ref, max_rounds=body.max_rounds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if out is None:
        raise HTTPException(status_code=404, detail="run not found")
    return out
```
No `JSONResponse`/202 branch, no `mode, payload = ...` unpack. No gateway change (`/v1/composition/*` is a generic passthrough, gateway-setup.ts:354). No contract/schema change beyond this router.

3) TEST — `services/composition-service/tests/unit/test_plan_forge_router.py`: add to `StubPlanForge` (beside `self_check`, line 67):
```python
    async def handoff_autofix(self, owner_user_id, book_id, run_id, **kwargs):
        if run_id != RUN:
            return None
        return {"rounds": [{"round": 1, "targets": 2, "result": "applied"}],
                "run": await self.get_run_detail(owner_user_id, book_id, run_id)}
```
plus three tests: (a) POST `/v1/composition/books/{BOOK}/plan/runs/{RUN}/autofix` with `{}` → 200, body has `rounds` and `run`; (b) unknown run_id → 404; (c) `{"max_rounds": 9}` → 422 (proves the Field bound, not a silent clamp at the edge).

4) FE consumer (Wave 5, G-PLANFORGE-PASS-RAIL) — `frontend/src/features/plan-forge/api.ts`, beside `selfCheck` (line 65): `autofix(bookId, runId, body?: {model_ref?: string; max_rounds?: number})` → POST `${BASE}/books/${bookId}/plan/runs/${runId}/autofix`. RAIL BEHAVIOR THE BUILDER MUST HONOR: with the worker on (`COMPOSITION_WORKER_ENABLED` defaults **true** in infra/docker-compose.yml:217), the loop does at most ONE round — refine enqueues, `handoff_autofix` breaks (plan_forge_service.py:843-845) and returns `rounds:[{result:"pending"}]`. So the rail must NOT render "autofix complete" on a 200; branch on `run.active_job_id`/`run.job_status` and poll `GET …/plan/runs/{run_id}` until the job settles, else the user pays for a refine and sees a false "done". (This is a service-behavior note, not a route change — do not touch handoff_autofix.)

DEFAULT I PICKED (veto-able): 200-always rather than a synthesized 202. A 202 would require the router to sniff `out["run"]["job_status"]`, and the ack payload would have no `job_id` of its own (handoff_autofix drops it at line 842 — only `payload["status"]` is kept). 200 + the run's `active_job_id` is the honest, already-working poll handle.

*Evidence:* services/composition-service/app/services/plan_forge_service.py:817 (`async def handoff_autofix(...) -> dict[str, Any] | None`) and :846-847 (`detail = await self.get_run_detail(...)` / `return {"rounds": applied, "run": detail}`) — a plain dict, NOT the `(mode, payload)` tuple of `refine` (:468) / `compile`, so /refine's 202 shape is not mirrorable. Template to copy = `self_check_plan_run`, services/composition-service/app/routers/plan_forge.py:357-373. Gate + arg contract to mirror = services/composition-service/app/mcp/server.py:3499-3516 (`_gate(tc, bid, GrantLevel.EDIT)`, `model_ref` optional, `max_rounds` 1-5). Poll handle already present: plan_forge_service.py:369-370 (`"active_job_id"`, `"job_status"` in `_serialize_run`). Worker-on = one round only: plan_forge_service.py:843-845 + infra/docker-compose.yml:217 (`COMPOSITION_WORKER_ENABLED:-true`). Gateway passthrough, no change: services/api-gateway-bff/src/gateway-setup.ts:354. Test seam: services/composition-service/tests/unit/test_plan_forge_router.py:61-70 (StubPlanForge).

### Q-30-X13-CONSUMER-CAPABILITIES-DEAD
**WAVE 0 — but NOT as "implement the two fields". DELETE both dead fields and fix the REAL bug they were nominally defending against.** X-13 rides the X-5/X-12 slice (same files, same contract regen), because Wave 7 (spec 37) adds zero frontend tools/panel ids and folding it there is scope-creep onto `chat-service` mid-edit by Track C — and because X-13b below is a *shipped* hallucinated-success bug that every panel Waves 1–8 add multiplies.

**Rationale from the code (all three premises of X-13 are false):**
(a) `consumer_capabilities` is not "stored-but-unread" — it is an **empty model**: `class ConsumerCapabilities(BaseModel): pass` (`services/chat-service/app/models.py:474-476`). There is nothing in it to read, and zero producers exist (the FE body builder sends only `studio_context` — `frontend/src/features/chat/hooks/runChatStream.ts:137`).
(b) The G6 advertise-filter **already exists and is CI-enforced, statically**: surface gating via `frontend_tool_defs(editor=|book_scoped=|studio=)` (`services/chat-service/app/services/frontend_tools.py:670-691`, keyed on which context object the request carries), plus the triple lock in `frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts` (BE `panel_id` enum == FE `OPENABLE_STUDIO_PANELS` == buildable `STUDIO_PANEL_COMPONENTS`). `OPENABLE_STUDIO_PANELS` is a **static compile-time filter** (`catalog.ts:279`) — there is NO runtime-variable panel set (no role/flag gate) — so a runtime capability handshake would be a second source of truth for a fact already machine-checked. That is the "one home / one name" violation, not a defense.
(c) `contributeContext()` is dead *by construction*: `useStudioPanel.ts:14` forwards only `mcpToolPrefixes|mcpTools|frontendTools|skills`, so no panel using the shared registration helper can supply it. Its function is already served by the push bus (`StudioBusEvent` chapter/scene/selection/panels → `StudioBusSnapshot`) and what actually reaches the agent is `ComposePanel.tsx:35-39`'s `studioContext` memo → `useChatMessages.ts:271` → `runChatStream.ts:137`.

**BUILD INSTRUCTION — three slices, in Wave 0 alongside X-5/X-12.**

**X-13a (BE, chat-service).** Delete `class ConsumerCapabilities` (`app/models.py:474-476`) and the field `consumer_capabilities: ConsumerCapabilities | None = None` (`app/models.py:502`). Safe: zero senders repo-wide (grep: only `models.py` + docs), and Pydantic's default `extra='ignore'` means a hypothetical caller sending the key still 200s. Then AMEND — do not fork — the specs that promised it, stating the filter is STATIC + CI-enforced, not a runtime handshake: `docs/specs/2026-07-01-writing-studio/09_agent_gui_reconciliation.md` (G6 at :42, the JSON at :269, the prose at :283), `07_studio_agent_chat.md:85`, `00_OVERVIEW.md:93/:99`, and the `docs/standards/README.md:76` enforcement cell (replace "`consumer_capabilities.frontend_tools` advertise filter" with "`frontend_tool_defs()` surface gating + `panelCatalogContract.test.ts` enum⇄catalog lock"). Test: no new test; `pytest tests -q -n auto --dist loadgroup` in chat-service must stay green (proves nothing read it).

**X-13b (FE — THE REAL BUG, and it is live today).** `frontend/src/features/studio/agent/studioUiNav.ts:32-38` returns `{ result: { opened: true }, effect: host.openPanel(panelId) }` for **any** non-empty string, and `StudioHostProvider.tsx:92` swallows the unknown-component throw (`catch { /* panel not in the catalog */ }`). Net: the agent is told `opened: true` while nothing opened — the repo's own `silent-success-is-a-bug` class, shipped. FIX: in `studioUiNav.ts`, import `STUDIO_PANEL_COMPONENTS` from `../panels/catalog` and validate BEFORE returning success — if `!(panelId in STUDIO_PANEL_COMPONENTS)` return `{ result: { opened: false, error: `unknown panel_id "${panelId}" — valid ids: ${Object.keys(STUDIO_PANEL_COMPONENTS).join(', ')}` } }` (no `effect`). Validate against `STUDIO_PANEL_COMPONENTS` (the *buildable* set), NOT `OPENABLE_STUDIO_PANELS`, so X-12's future params-carrying `hiddenFromPalette` ids (`arc-inspector`, `motif-editor`) do not false-reject. Keep the existing `panel`/`page` alias tolerance (it exists because a live gemma-26b smoke sent `panel:"editor"`). Also make `StudioHostProvider.openPanel` return `boolean` (`false` on `!api` or on the caught `addPanel` throw) so no future caller can re-introduce a silent swallow. TEST (new, in `frontend/src/features/studio/agent/__tests__/studioUiNav.test.ts`): "unknown panel_id ⇒ `opened:false` + `result.error`, and NO effect returned"; plus a regression that every id in the contract's `ui_open_studio_panel.panel_id.enum` resolves with `opened:true` (guards the enum⇄resolver seam the same way `panelCatalogContract.test.ts` guards the enum⇄catalog seam).

**X-13c (FE, contributeContext).** Delete `contributeContext?: () => StudioContextSlice | null;` (`frontend/src/features/studio/host/types.ts:31`) and `interface StudioContextSlice` (`types.ts:34-39`, unreferenced elsewhere — grep confirms `types.ts` is the only file). Replace the line in the two specs that promise it (`07c_studio_tool_registry.md:54`, `08_studio_state_architecture.md:300` item 4, `04b_raw_editor.md:152`) with the LAW every new panel in Waves 1–8 follows: **"a panel feeds the agent by PUBLISHING a bus event (`host.publish({type: ...})`), never by implementing a second context mechanism. If a panel's slice key has no `StudioBusEvent` variant, ADD one — the union is additive (see `types.ts:41-66`)."**

**DoD for the wave (per PO policy #2):** `/review-impl` runs at wave close; the wave is not done until the two new studioUiNav tests + `panelCatalogContract.test.ts` are green and a live browser smoke shows the agent calling `ui_open_studio_panel` with a bogus id and getting a visible `error` back (not a hallucinated "Opened!").

**Default noted for PO veto:** I am choosing DELETE over IMPLEMENT for both fields. The only thing a runtime capability handshake could buy that the static contract cannot is BE/FE version skew (a deployed backend advertising a panel an older cached bundle lacks). This is a single monorepo deployed as one compose stack, and X-13b's resolver guard degrades that case correctly anyway (the agent gets an honest error instead of a lie). If the PO wants the handshake anyway, veto X-13a — but X-13b ships regardless; it is the actual bug.

*Evidence:* services/chat-service/app/models.py:474-476 (`class ConsumerCapabilities(BaseModel): pass` — an EMPTY model, nothing to read) + :502 (the field). services/chat-service/app/services/frontend_tools.py:670-691 (`frontend_tool_defs(editor|book_scoped|studio)` — the advertise filter that ALREADY exists). frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts (CI lock: BE enum == OPENABLE_STUDIO_PANELS == STUDIO_PANEL_COMPONENTS) + frontend/src/features/studio/panels/catalog.ts:279 (OPENABLE is a STATIC compile-time filter — no runtime-variable panel set exists). THE REAL BUG: frontend/src/features/studio/agent/studioUiNav.ts:36-38 (`return { result: { opened: true }, effect: (host) => host.openPanel(panelId) }` for ANY non-empty string) + frontend/src/features/studio/host/StudioHostProvider.tsx:91-92 (`try { api.addPanel(...) } catch { /* panel not in the catalog */ }` — swallows the unknown-component throw after success was already reported). contributeContext DEAD BY CONSTRUCTION: frontend/src/features/studio/host/types.ts:31 (declared) vs frontend/src/features/studio/panels/useStudioPanel.ts:14 (`extras?: Pick<StudioToolRegistration, 'mcpToolPrefixes' | 'mcpTools' | 'frontendTools' | 'skills'>` — contributeContext is not forwardable); the live path is frontend/src/features/studio/panels/ComposePanel.tsx:35-39 → frontend/src/features/chat/hooks/useChatMessages.ts:271 → runChatStream.ts:137 (`body.studio_context`).

### Q-30-BE4-PLAN-RUN-DELETE
BUILD IT — it is unbuilt work, not a blocker. Ship `DELETE /v1/composition/books/{book_id}/plan/runs/{run_id}` whose SEMANTICS ARE ARCHIVE (soft delete), never a hard row delete. WHY archive is forced by the schema, not taste: `authoring_runs.plan_run_id UUID NOT NULL REFERENCES plan_run(id)` (migrate.py:1421) has NO `ON DELETE` clause -> NO ACTION -> a hard DELETE of any plan run that fed an authoring run throws ForeignKeyViolation (500); and `structure_node.plan_run_id` / `outline_node.plan_run_id` (migrate.py:1352,1358) are FK-LESS provenance columns feeding the linker's partial-unique idempotency index, so a hard delete silently orphans them. (plan_artifact:1293 and plan_bootstrap_proposal:1535 already CASCADE, so they need nothing.)

SLICE BE-4 — 6 files, exact changes:

1. `services/composition-service/app/db/migrate.py` — in the PlanForge v2 ALTER block right after line 1316 (`ALTER TABLE plan_run ADD COLUMN IF NOT EXISTS genre_tags ...`), add:
   ALTER TABLE plan_run ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE;
   ALTER TABLE plan_run ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;
   CREATE INDEX IF NOT EXISTS idx_plan_run_book_active ON plan_run(book_id, created_at DESC) WHERE NOT is_archived;

2. `services/composition-service/app/db/models.py` — `PlanRun`: add `is_archived: bool = False` and `archived_at: datetime | None = None`.

3. `services/composition-service/app/db/repositories/plan_runs.py` —
   a. add `is_archived, archived_at` to `_SELECT_RUN`;
   b. NEW method:
      async def archive(self, book_id: UUID, run_id: UUID) -> bool:
          UPDATE plan_run SET is_archived = TRUE, archived_at = now(), updated_at = now()
          WHERE id = $1 AND book_id = $2 AND NOT is_archived RETURNING id
      (returns True iff a row flipped);
   c. add `AND NOT is_archived` to THREE existing readers or the archive is cosmetic:
      - `list_for_book` (line ~128) WHERE clause — archived runs must leave the list;
      - `find_by_checksum` (line ~99) — otherwise re-Proposing the same markdown RESURRECTS the archived run instead of making a fresh one (silent-success bug class);
      - `plan_state_for_book` (line ~313) — all three subqueries (run_count, latest_status, has_spec EXISTS): an archived failed run must not remain the book's "latest_status" on every chat turn.
   d. LEAVE `get_for_book` returning archived rows (so a deep-link still resolves and DELETE is idempotent); surface `is_archived` in `_serialize_run` so the GUI can badge it.

4. `services/composition-service/app/services/plan_forge_service.py` — next to `get_run_detail` (line 319):
      async def archive_run(self, user_id: UUID, book_id: UUID, run_id: UUID) -> bool:
          run = await self._runs.get_for_book(book_id, run_id)
          if run is None: return False
          await self._runs.archive(book_id, run_id)   # already-archived -> still True (idempotent 204)
          return True
   NO status guard — clearing a stuck `pending`/`failed` run is the entire use case. Do NOT try to cancel `active_job_id` (out of scope; the worker's `update_run` on an archived row is harmless).

5. `services/composition-service/app/routers/plan_forge.py` — after `get_plan_run` (line 144):
      @router.delete("/books/{book_id}/plan/runs/{run_id}", status_code=204)
      async def delete_plan_run(book_id, run_id, user_id=Depends(get_current_user), grant=Depends(get_grant_client_dep), svc=Depends(get_plan_forge_service)):
          await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)   # EDIT, matching create/patch/compile
          if not await svc.archive_run(user_id, book_id, run_id):
              raise HTTPException(status_code=404, detail="run not found")
          return Response(status_code=204)
   404 unknown run · 403 VIEW-only grantee · 204 on both first archive and a repeat.

6. `frontend/src/features/plan-forge/api.ts` (line ~50, beside `getPlanRun`) — `deletePlanRun(bookId, runId, token)` issuing DELETE. NO gateway change needed: `services/api-gateway-bff/src/gateway-setup.ts:350-354` proxies the whole `/v1/composition` prefix by pathFilter for all verbs. (The Wave-5 trash button in the planner panel belongs to G-PLANNER-REPAIR, not to BE-4.)

7. MCP (MCP-first invariant — the studio agent must be able to clear the failed run it just created): add `plan_archive_run` in `services/composition-service/app/mcp/server.py` beside the other `plan_*` tools (~line 3442 `plan_review_checkpoint` is the shape to mirror; meta `require_meta("W", "book", synonyms=["delete plan run","archive plan run","clear failed run"], tool_name="plan_archive_run")`), delegating to the SAME `svc.archive_run` — no second code path.

TESTS (both required for wave DoD):
- `services/composition-service/tests/unit/test_plan_forge_router.py`: DELETE -> 204 and `archive` called; unknown run -> 404; VIEW-only grant -> 403.
- `services/composition-service/tests/integration/db/test_repositories.py`: after `archive()` — `list_for_book` excludes it, `find_by_checksum` returns None (so re-Propose yields a FRESH run), `plan_state_for_book.run_count` drops and `latest_status` moves to the newest non-archived run.

Default I picked that the PO may veto: soft archive + `DELETE` verb (rather than a `POST .../archive` route or a real row delete). Rationale above — a real delete 500s on compiled runs, and the spec itself offers "DELETE (or archive)".

*Evidence:* services/composition-service/app/routers/plan_forge.py:94-375 (13 routes, zero @router.delete) + plan_bootstrap.py:41-113 (zero) — gap confirmed. services/composition-service/app/db/repositories/plan_runs.py:58-365 — PlanRunsRepo has no delete/archive. services/composition-service/app/db/migrate.py:1256 — plan_run DDL has no is_archived. **migrate.py:1421 — `plan_run_id UUID NOT NULL REFERENCES plan_run(id)` on authoring_runs with NO ON DELETE clause = hard DELETE is a FK violation**; migrate.py:1352,1358 — structure_node/outline_node.plan_run_id are FK-less provenance; migrate.py:1293,1535 — plan_artifact + plan_bootstrap_proposal already ON DELETE CASCADE. services/api-gateway-bff/src/gateway-setup.ts:350-354 — prefix proxy, all verbs, no gateway work needed.

### Q-30-OQ1-PROPOSE-EDIT-NO-JOBID
ACCEPT the scope-out. Wave 1 captures corrections ONLY on the accept_unit/reject_unit path (spec 31 BE-9a/b/c/c'). chat-service does NOT mint or propagate a composition generation_job.

WHY (from code, not convenience): correction_stats (services/composition-service/app/db/repositories/generation_corrections.py:183-195) computes `generations = count(DISTINCT j.id) FILTER (WHERE j.status='completed')` GROUPED BY j.mode, and Wave 1's own BE-9c narrows that denominator to the operation allowlist ('draft_scene','draft_chapter','stitch_chapter') precisely because non-draft jobs can never be corrected and corrupt the auto-vs-cowrite rate (spec 31 F-Q3). A synthetic chat-turn job therefore forks into two bad branches: (a) allowlisted operation => it inflates the cowrite denominator with jobs that were never engine drafts, re-introducing the exact lie BE-9c is fixing IN THE SAME WAVE; or (b) new operation outside the allowlist => correction_stats filters it out, so the captured row is invisible to the very panel it was captured for. Both are worse than not capturing. Semantics agree: H2 says accept-as-is is NOT a correction — propose_edit Apply IS an accept, and Dismiss is a one-bit reject with no changed_blocks magnitude, whereas accept_unit/reject_unit carry a real diff against a real job.

What is actually lost is only the PERSISTED flywheel row — not in-turn honesty: the Apply/Dismiss outcome already returns to the model via the frontend-tool resolve (frontend_tools.py:70-77 description), so the agent still reports the real result. The flywheel is not "dark" for the agent, only for the learning store.

BUILDER INSTRUCTIONS (concrete, 3 items):
1. DO NOT add `job_id`/`correlation_id` to PROPOSE_EDIT_TOOL (services/chat-service/app/services/frontend_tools.py:66-103). Its params stay exactly {operation, text, rationale}. No contracts/frontend-tools.contract.json change, no chat-service->composition job-minting route.
2. Add an ANTI-REVERT comment (mirroring spec 31 F-Q3's own "a future agent silently reverts the fix" guard) in TWO places, each citing this decision: (a) above PROPOSE_EDIT_TOOL in services/chat-service/app/services/frontend_tools.py:66 — "propose_edit intentionally carries NO job_id: its prose is a chat-service turn, not a composition generation_job. Minting one would either inflate correction_stats' cowrite denominator (the lie BE-9c fixes) or be filtered out by the BE-9c operation allowlist. See spec 31 OQ-1."; (b) at the BE-9c operation allowlist in composition-service (the ('draft_scene','draft_chapter','stitch_chapter') tuple) — "do NOT widen for chat-authored prose; see spec 31 OQ-1."
3. Write the defer row below into docs/sessions/SESSION_HANDOFF.md Deferred Items so this is a tracked conscious scope-out, never a silent drop.

PO VETO POINT: if the PO wants propose_edit's signal persisted, the correct shape is NOT job-minting — it is a separate chat-side suggestion-outcome table with its OWN denominator, kept out of correction_stats' auto-vs-cowrite A/B. That is a new track, not a Wave-1 wiring task.

*Evidence:* services/composition-service/app/db/migrate.py:368 — `job_id UUID NOT NULL REFERENCES generation_job(id) ON DELETE CASCADE` (a correction REQUIRES a real engine job); migrate.py:272 — `mode TEXT NOT NULL DEFAULT 'cowrite' CHECK (mode IN ('cowrite','auto'))`; services/composition-service/app/db/repositories/generation_corrections.py:183-195 — denominator `count(DISTINCT j.id) FILTER (WHERE j.status='completed')` grouped by `j.mode` (what a synthetic job would corrupt); services/chat-service/app/services/frontend_tools.py:78-101 — PROPOSE_EDIT_TOOL params are exactly {operation, text, rationale}, no job/correlation id; frontend/src/features/studio/panels/ComposePanel.tsx:101 — ComposePanel passes `editorContext`, so propose_edit IS live in the Studio (the path is real, the loss is real but bounded to the persisted row).

### Q-30-404-REGENERATE-TO-BEAT
DO NOT BUILD a `regenerate-to-beat` route. Re-point the button at the EXISTING per-scene generate. The spec's candidate answer is CORRECT on the code — adopt it, with one addition it under-specifies (the accept path), because `/generate` does not persist prose and a fire-and-forget re-point would ship an invisible button (the repo's own `silent-success-is-a-bug` class).

BUILDER STEPS (Wave 3, slice 3c — frontend-only, ZERO backend work, no allowlist/gateway change):

1. DELETE `motifApi.regenerateToBeat` — `frontend/src/features/composition/motif/api.ts:299-304` (the whole method + its doc comment).
2. DELETE `useMotifBinding.regenerateScene` — `frontend/src/features/composition/motif/hooks/useMotifBinding.ts:64-68` — and remove it from the returned object at `:75`. Keep `commitAndGenerate` (`:70`) — it is a different, working seam.
3. REWRITE the mutation in `frontend/src/features/composition/motif/hooks/useConformanceTrace.ts:25-28`. Rename `regenerateToBeat` -> `regenerateScene`. Widen the hook signature to `useConformanceTrace(projectId, chapterId, token, model: { modelRef?: string; modelKind?: string; modelName?: string })`. The mutation calls the EXISTING client `compositionApi.generateAuto(projectId, { outlineNodeId: nodeId, modelSource: 'user_model', modelRef, operation: 'draft_scene', modelKind, modelName }, token)` (`frontend/src/features/composition/api.ts:398`), which POSTs `/v1/composition/works/{pid}/generate` with `{mode:'auto', outline_node_id, model_source, model_ref, operation}` — byte-matching `GenerateBody` at `services/composition-service/app/routers/engine.py:89-112`. Do NOT hand-roll an `apiJson` call; reuse `generateAuto` (it already handles the worker-flag 202 submit+poll via `_resolveJob`).
4. SHOW THE RESULT — do not `mutate()` and `invalidate()`. `POST /generate` returns the winner text; it does NOT write the chapter draft (the only per-scene write is `persist_scene_prose`, `engine.py:1521`, and it is derivative-promote-only). So: hold the returned `AutoGeneration` in hook state keyed by `outline_node_id`, and have `ConformanceSceneRow.tsx` render the winner text inline as a review ghost with an Accept button that calls a new `onAccept(nodeId, text)` prop — the `quality-conformance` panel wires `onAccept` to the SAME editor write-back target `EditorPanel` already registers (`registerEditorTarget` / the propose-edit ghost), exactly mirroring `ComposeView.accept` (`ComposeView.tsx:77`, buttons at `:223-240`). Invalidate the conformance query ONLY after the accept lands — that is the point at which the trace can actually change.
5. GATE ON MODEL, NOT ON COST. Disable Regenerate when `!modelRef` and show the "Pick a model" affordance + the X-1 `AddModelCta`, mirroring `ComposeView.tsx:63` (`canGenerate = !!sceneId && !!modelRef && !busy`) and `:204` (`data-testid="compose-need-model"`). Do NOT bolt a bespoke estimate/confirm gate onto this one button — `POST /generate` is ungated today for ComposePanel too (spec 28 AN-8: a new confirmation convention here is a defect); the ungated spend is tracked as D-COMPOSE-GENERATE-UNGATED and is fixed once, on the compose path, for both.
6. TESTS: (a) vitest on `useConformanceTrace` asserting the request URL is `/v1/composition/works/{pid}/generate` with body `{mode:'auto', outline_node_id, operation:'draft_scene'}` and that ZERO requests hit `regenerate-to-beat`; (b) a grep-guard is NOT sufficient — 3c's DoD network-tab assertion (live browser smoke) is the real proof; (c) the "new prose reflects the bound beat" end-to-end check belongs to X-7/BE-M2's packer test (`test_pack_motifs_wired.py`), not here.

WHY NO ROUTE: "to-beat" is the PACKER LENS, not a route. Once X-7 (`gather_motifs`) injects the scene's bound motif + target beat into `pack()`, the existing scene-generate IS "regenerate to beat" — and `engine.py:326` is already the production caller that will ride it (it already takes `structures: StructureRepo` at `:334`). Building a bespoke route would be a per-action route for a Tier-W op — the exact plan-30 §8.1 violation the two other live 404s already committed. Consistent with sealed §0 (PO-1..4 say nothing about this; no conflict).

DEFAULT THE PO MAY VETO: step 4 (inline ghost + Accept in the conformance row) is my call, not the spec's. If the PO would rather the button just hand off to the compose surface, the one-line alternative is: Regenerate = `commitAndGenerate(sceneId)` -> open/focus the compose surface with the scene preselected. Either is fine; what is NOT fine is mutate-and-invalidate with nothing rendered.

*Evidence:* services/composition-service/app/routers/engine.py:326 (`@router.post("/works/{project_id}/generate")`) + engine.py:89-112 (`GenerateBody.outline_node_id: UUID`, `model_source`, `model_ref`, `operation='draft_scene'`, `mode='cowrite'|'auto'`) + engine.py:352 ("B2 — this is the PER-SCENE endpoint") | REFUTATION of BE-5's premise: services/composition-service/app/routers/engine.py:1521 `persist_scene_prose` — "WS-B3 prose-persist-on-promote… writes a synthetic completed generation_job" (persists, generates nothing) | dead FE callers: frontend/src/features/composition/motif/api.ts:300 and frontend/src/features/composition/motif/hooks/useMotifBinding.ts:66; button at frontend/src/features/composition/motif/components/ConformanceTraceView.tsx:69 -> ConformanceSceneRow.tsx:70 | existing client to reuse: frontend/src/features/composition/api.ts:398 `generateAuto` + hooks/useAutoGenerate.ts:11 | accept-path precedent: frontend/src/features/composition/components/ComposeView.tsx:63, :77, :204, :239 | `grep -rn "regenerate-to-beat" services/**/*.py` -> 0 hits

### Q-30-BE7-ARC-ROUTES
BUILD BOTH ROUTES IN WAVE 4, both in the EXISTING `services/composition-service/app/routers/arc.py` (already `prefix="/v1/composition"`, already mounted at `app/main.py:228`, already carries every gate/error helper). No new router file, no gateway change (`gateway-setup.ts:354` proxies `/v1/composition/*` generically), no bridge-allowlist entry. Contract = spec 34 §5 BE-7a/BE-7b verbatim.

STEP 0 — ONE HOME FOR THE PROJECTION (do this first; it is the only non-mechanical part). `_ARC_REF_FIELDS` (server.py:233) and `_arc_public_projection` (server.py:2336) currently live INSIDE the MCP tool registry; a router must not import `app.mcp.server` (it would import 4,777 lines of FastMCP tool registration at HTTP boot). Create `services/composition-service/app/engine/arc_projection.py` exporting `ARC_REF_FIELDS: tuple[str, ...]` and `arc_public_projection(arc) -> dict` (bodies moved verbatim), then in `mcp/server.py` DELETE both local definitions and import them from there. Do NOT copy-paste the drop-set into the router — a duplicated allow-list drifts (memory: `css-var-duplicated-across-two-consumers-drifts`). `apply_response_contract` is already SDK-level (`from loreweave_mcp import apply_response_contract`, server.py:55) so the router imports it directly. Precedent for a router importing `app.engine.*`: arc.py:56 already does (`from app.engine.arc_apply import build_apply_plan`).

STEP 1 — BE-7a `POST /v1/composition/arcs/{node_id}/extract-template` (Tier-A WRITE, REST only). In arc.py, next to the other `/arcs/{node_id}` writes (after `@router.patch("/arcs/{node_id}")`, ~line 489):
  class ArcExtractBody(_ForbidExtra):  # `_ForbidExtra` is already imported at arc.py:42
      code: str; name: str; language: str = "en"
      visibility: Literal["private", "unlisted"] = "private"   # 'public' excluded at create — publishing is the separate PATCH flip
  @router.post("/arcs/{node_id}/extract-template")
  async def extract_arc_template(node_id: UUID, body: ArcExtractBody, user_id=Depends(get_current_user), grant: GrantClient = Depends(get_grant_client_dep)) -> dict:
      node = await _gate_arc(_structures(), grant, user_id, node_id, GrantLevel.VIEW)   # arc.py:383 — scope derived from the ROW's book (VIEW, exactly like the MCP handler at server.py:4649); missing node → same uniform 404 as denied grant
      try:
          return await extract_template_from_arc(get_pool(), arc_node=node, owner_user_id=user_id, code=body.code, name=body.name, language=body.language, visibility=body.visibility)
      except asyncpg.UniqueViolationError:
          raise HTTPException(status_code=409, detail={"code": "ARC_TEMPLATE_CODE_EXISTS", "message": "an arc template with this code + language already exists — rename before extracting"})
  Return the engine dict UNMODIFIED (`{success, outcome:'extracted', template_id, member_chapter_node_ids[], layout_placements, pacing_chapters}`), status 200, and do NOT add the MCP-only `_meta.undo_hint`. VIEW (not EDIT) is correct and deliberate: the read is on someone else's arc, the WRITE lands in the caller's own library tier (owner server-stamped by `ArcTemplateRepo.create(owner_user_id, …)`).

STEP 2 — BE-7b `POST /v1/composition/arc-templates/suggest` (free read; the ONE owner of arc-suggest — spec 33's BE-M5 is DELETED, and the `GET /books/{bid}/arcs/suggest` shape in plan 30's old BE-6 row was wrong). Register it ABOVE `@router.get("/arc-templates/{arc_id}")` (arc.py:157) so no path-param route can ever shadow the literal segment:
  class ArcSuggestBody(_ForbidExtra):
      project_id: UUID; premise: str | None = None; genre: str | None = None
      limit: int = Field(default=5, ge=1, le=50)
      detail: Literal["summary", "full"] = "full"   # mirror the tool exactly (server.py:2293 defaults 'full'); the FE panel PASSES detail='summary' for the ranked list (Context Budget Law §6b)
  Handler: `book_id = await book_id_for_project(WorksRepo(get_pool()), grant, body.project_id, user_id, GrantLevel.VIEW)` — grant_deps.py:58, the sanctioned HTTP mirror of MCP's `_book_or_deny` (OwnershipError→404 H13, InsufficientGrant→403; wrap with arc.py's `_gate_book`-style try/except to get those exact codes). Then `candidates = await MotifRetriever(get_pool()).retrieve_arcs(user_id, book_id=book_id, project_id=body.project_id, premise=body.premise, genre=body.genre, limit=body.limit)` (motif_retrieve.py:279 — or inject via `Depends(get_motif_retriever)`, deps.py:205). Then reproduce server.py:2317-2332 EXACTLY: per-candidate owner check (`c.arc_template.owner_user_id == user_id` → full `model_dump(mode="json")`, else `arc_public_projection(c.arc_template)`), feed through `apply_response_contract(..., ref_fields=ARC_REF_FIELDS, detail=body.detail)`, return `{"candidates": [{"arc_template": arc_dicts[i], "score": c.score, "match_reason": c.match_reason} …], **meta}`. Keep `match_reason` — it is the only explanation the ranked list gives the user.

STEP 3 — TESTS (`services/composition-service/tests/unit/test_arc_hub_routes.py`, same TestClient + `dependency_overrides[get_grant_client_dep] = _Grant(level)` harness already in that file): (a) extract as non-grantee → 404 and the engine is NEVER called; (b) extract as VIEW grantee → 200 + engine called with `owner_user_id == caller`; (c) extract when the engine raises `asyncpg.UniqueViolationError` → 409 `ARC_TEMPLATE_CODE_EXISTS`; (d) suggest as non-grantee → 404, retriever never called; (e) suggest `detail='summary'` → each candidate's `arc_template` carries only `ARC_REF_FIELDS` while `score` + `match_reason` survive; (f) a NON-owned candidate never leaks `embedding`/`owner_user_id`/`source_ref`. Also add one test in `tests/unit/test_mcp_arc_structure.py` (or wherever server.py's projection is covered) asserting `mcp.server._ARC_REF_FIELDS is arc_projection.ARC_REF_FIELDS` — i.e. the move left ONE home.

STEP 4 — OpenAPI: add both routes to `contracts/api/` (spec 34 §5: "specs 23 and 24 both left this undone — do not compound it").

STEP 5 — `/review-impl` at wave close (PO policy #2).

DEFAULT THE PO MAY VETO: `detail` defaults to `'full'` (mirrors the tool) rather than `'summary'`; the FE is instructed to pass `'summary'` explicitly for the list view. If the PO prefers the budget-safe default at the route, flip the one literal.

*Evidence:* Engine (BE-7a): services/composition-service/app/engine/arc_apply.py:652 `extract_template_from_arc(pool, *, arc_node, owner_user_id, code, name, language='en', visibility='private')` — docstring says "MCP/REST seam" and "does not swallow" the UniqueViolationError (arc_apply.py:660-666). MCP handler to mirror: services/composition-service/app/mcp/server.py:4618-4669 (`_ArcExtractTemplateArgs` ForbidExtra + `_arc_or_deny(..., GrantLevel.VIEW)`). Engine (BE-7b): services/composition-service/app/db/repositories/motif_retrieve.py:279 `retrieve_arcs(caller_id, *, book_id, project_id, premise, genre, limit=5)`; MCP handler services/composition-service/app/mcp/server.py:2287-2332 (takes `project_id`, `limit=5`, `detail='full'` — NOT a book_id path segment). Host router: services/composition-service/app/routers/arc.py:63 (`APIRouter(prefix="/v1/composition")`), mounted app/main.py:228; gates already present: `_gate_arc` arc.py:383, `_gate_book` arc.py:372, `book_id_for_project` app/grant_deps.py:58; retriever dep app/deps.py:205. Projection helpers currently trapped in the MCP registry: `_ARC_REF_FIELDS` server.py:233, `_arc_public_projection` server.py:2336; `apply_response_contract` is SDK-level (server.py:55). Contract rows: docs/specs/2026-07-01-writing-studio/34_arc_templates_and_deconstruct.md §5 (BE-7a/BE-7b) + AT-3/AT-4 (write ⇒ REST, never the bridge allowlist — `tools.controller.ts:19-31` says "NOTHING here writes or deletes"). Test harness precedent: services/composition-service/tests/unit/test_arc_hub_routes.py:67-73.

### Q-30-BE8-ARC-DRIFT-AND-APPLY
CONFIRMED + FURTHER CORRECTED (the spec's own correction is still half-wrong in the OTHER direction — it over-sizes apply).

**(1) Human drift view = BE-NONE. Build it in Wave 4 (M4). Do NOT park it.** VERIFIED IN CODE: `services/composition-service/app/routers/conformance.py:334-404` — `GET /v1/composition/works/{project_id}/conformance?scope=arc_template_drift&arc_id=<structure_node.id>` ships: it resolves the node (`_resolve_book_arc`), 422 `NO_TEMPLATE_PROVENANCE` when `node.arc_template_id is None` (:394-396), H13-uniform 404 on a foreign/missing template (`arc_repo.get_visible` :397-400), then returns `compute_arc_report(..., arc=<the arc_template>, by_structure=False, deep=deep)` (:401-404). Tested at `tests/unit/test_arc_conformance.py:301-345` (arc_id required / 422 / 404 / coarse report / deep overlay). Zero FE consumers. So M4 is pure FE: build the `arc-templates` panel's drift view + the three empty states (no-provenance-422 · not-found-404 · zero-drift) against this route; render coverage, realized-vs-template pacing, succession flags, and the `unmaterialized` drop/merge list the report already returns (`app/engine/arc_conformance.py:354-378`).

**(2) `composition_arc_template_drift` (agent parity) = S — delegate, do not write a second engine.** Current stub: `app/mcp/server.py:4688-4701` does `getattr(app.engine.arc_conformance, "build_template_drift")` → None → `_pending_engine("A4", ...)`. IMPLEMENT `build_template_drift` IN `app/engine/arc_conformance.py` (that exact module/name — the getattr seam at :4698 then resolves it; after it lands, replace the getattr with a direct import so the `_pending_engine` path for A4 is deleted, not left dormant). Body — a pure delegator, ~25 lines, ZERO new compute:
  - function-LOCAL imports (avoid the cycle: `arc_conformance_orchestrate` already imports `arc_conformance`): `from app.engine.arc_conformance_orchestrate import compute_arc_report`, `from app.routers.conformance import ConformanceTraceReader` (defined at `conformance.py:88`), `MotifRepo`, `ArcTemplateRepo`, `WorksRepo`, `get_knowledge_client`.
  - resolve the Work: `WorksRepo(pool).resolve_by_book(arc_node.book_id)` (`app/db/repositories/works.py:250`); empty ⇒ return the honest `{"available": False, "reason": "no composition work for this book"}` (never a silent success). ALSO add an optional `project_id` arg to the MCP tool (`server.py:4688`) so a caller with >1 Work per book can disambiguate; when absent take `resolve_by_book(...)[0]`.
  - `tmpl = await ArcTemplateRepo(pool).get_visible(user_id, arc_node.arc_template_id)`; None ⇒ `raise uniform_not_accessible()` (same H13 as the REST route).
  - `return await compute_arc_report(reader=ConformanceTraceReader(pool), mrepo=MotifRepo(pool), knowledge=get_knowledge_client(), user_id=user_id, project_id=<resolved>, book_id=arc_node.book_id, arc=tmpl, by_structure=False, deep=False)`.
  TEST (`tests/unit/test_mcp_server.py`): monkeypatch `compute_arc_report`, assert the tool (a) no longer returns `pending_dependency`, and (b) called it with `by_structure=False` — the one-engine guard (`css-var-duplicated-across-two-consumers-drifts`).

**(3) `composition_arc_apply` is NOT "M — genuinely unwritten". The ENGINE IS WRITTEN AND TESTED; only the seam wrapper + one tool arg are missing ⇒ S/low-M.** `app/engine/arc_apply.py:325` `async def arc_apply(template, structure_node, *, created_by, structure_repo, outline_repo, applications_repo, resolve_motifs, cast_index, cast_names, roster_bindings, k_ceiling, high_threshold, min_scenes, max_scenes, replace)` is the full BA3 template→spec apply: rescales onto the arc's member chapters, materializes scenes, writes pacing from the template curve, emits the `motif_application` ledger, stamps `tracks`/`roster`/`roster_bindings`/provenance, raises `ArcApplyError`(→400)/`ArcApplyConflict`(→409). It is covered by `tests/integration/db/test_arc_apply_roundtrip.py:167,234,265,295-301` (roundtrip + conflict + replace). It has NO production caller — it is awaiting exactly one wrapper. Also note the spec is STALE on the other half: the sibling seam `extract_template_from_arc` ALREADY LANDED (`arc_apply.py:652-681`), so `composition_arc_extract_template` is LIVE today, not a `_pending_engine` stub.
  So BE-8's apply slice = **write `apply_arc_to_spec(pool, *, book_id, project_id, structure_node, arc_template, roster_bindings, replace, idempotency_key, created_by)` in `app/engine/arc_apply.py`, mirroring `extract_template_from_arc` at :652 line-for-line**: build `StructureRepo/OutlineRepo/MotifApplicationRepo/MotifRepo` from `pool`; `resolve_motifs = partial(_resolve_plan_motifs, MotifRepo(pool), created_by)` (lift `_resolve_plan_motifs` from `app/routers/plan.py:1239-1257` into the engine module and have plan.py import it — one resolver, not two); `cast_index/cast_names` from `_cast_roster(kal, book_id, user_id)` (`plan.py:167-182`, KAL client via the same `mint_service_bearer` seam `server.py:583-584` uses); knobs from `app.config.settings` (`compose_diverge_k`, `plan_high_tension_threshold`, `plan_min_scenes_per_chapter`, `plan_max_scenes_per_chapter` — exactly `plan.py:1315-1316`); map `ArcApplyConflict` → `{"success": false, "outcome": "applied_conflict", "chapter_ids": […]}` and `ArcApplyError` → `{"success": false, "error": …, **detail}`; return `asdict(ArcApplyResult)` + `_meta`.
  **BUG IN THE CURRENT STUB'S SURFACE — fix it in the same slice:** `_ArcApplyArgs` (`server.py:4567-4574`) carries `project_id` + `arc_template_id` but **no target arc**, while the engine requires a `structure_node`. Add `structure_node_id: str` to `_ArcApplyArgs` and gate it with `_arc_or_deny(structures, tc, UUID(args.structure_node_id), GrantLevel.EDIT)` before the apply. Without this the tool literally cannot call the engine.
  **Liveness contract:** flip the `composition_arc_apply` and `composition_arc_template_drift` rows in BOTH copies of the liveness map — `contracts/tool-liveness.json:157,212` AND `services/agent-registry-service/internal/api/tool-liveness.json:157,212` (two files, keep in sync) — and add a guard test asserting `getattr(app.engine.arc_apply, "apply_arc_to_spec")` and `getattr(app.engine.arc_conformance, "build_template_drift")` are both non-None, so the `_pending_engine` refusal can never silently come back.

**Wave placement (matches the spec's candidate, re-sized):** M4 drift view = Wave 4, BE-NONE, unblocked, not parked. Agent parity = its own slice **M5, after the panel, still inside Wave 4** (it is small now: drift S + apply S/low-M — both are wrappers over shipped, tested engines, so it does NOT clear any of CLAUDE.md's 5 defer gates and must not become a defer row). If Wave 4 runs out of room, the parity slice moves to the FRONT of Wave 5 — it never becomes "parked indefinitely". `/review-impl` at wave close, per PO policy.

*Evidence:* services/composition-service/app/routers/conformance.py:390-404 (scope=arc_template_drift SHIPS → compute_arc_report(by_structure=False)); tests/unit/test_arc_conformance.py:301-345 (route tested); services/composition-service/app/engine/arc_apply.py:325 (async def arc_apply — the apply engine EXISTS, fully written) + arc_apply.py:652-681 (extract_template_from_arc seam ALREADY LANDED — the pattern to copy); tests/integration/db/test_arc_apply_roundtrip.py:167,295-301 (engine covered incl. conflict/replace); services/composition-service/app/mcp/server.py:4593-4615 (composition_arc_apply stub; _ArcApplyArgs at :4567-4574 has NO structure_node_id) and server.py:4688-4701 (composition_arc_template_drift getattr → _pending_engine); app/routers/plan.py:1239-1257,1315-1316 (_resolve_plan_motifs + the settings knobs the wrapper must pass); app/db/repositories/works.py:250 (resolve_by_book, for the drift wrapper's project_id).

### Q-30-BE13-DIVERGENCE-CRUD
DO NOT build the 5 routes. The audit's premise is 1/3 correct: only UPDATE is missing; LIST and DELETE already exist. Builder instruction for Wave 6 / M3 (`divergence` panel):

(1) LIST — **write no route.** Use the existing `GET /v1/composition/books/{bid}/work`. `resolve_by_book` (repositories/works.py:250-268) returns EVERY active Work of the book — canonical + derivatives — and `_serialize_resolution` (routers/works.py:75-79) emits them as `candidates[]`, each row carrying `source_work_id`, `branch_point`, `settings` (in `_SELECT_COLS`, works.py:32-38). Canonical = `!w.source_work_id`; derivatives = the rest. ⚠ TRAP the builder must handle: `candidates` is EMPTY when the book has exactly one Work (`resolve_work` returns `status:"found"` + `work`, `works=[]` — work_resolution.py:88-95). So the panel's list is `const works = candidates.length ? candidates : (work ? [work] : [])` — never `candidates` alone, or a book with only a canonical Work renders an empty panel. Put that in the panel's unit test (fixture A: status=found, 1 work → 1 row, 0 derivatives; fixture B: status=candidates, canonical+2 derivatives → 3 rows).

(2) DELETE — **write no route.** `PATCH /works/{pid}` with `{status:'archived'}` + `If-Match` IS the soft-delete: `status` is in `_UPDATABLE_COLUMNS` (repositories/works.py:42) and in `WorkPatch` (routers/works.py:61), the CHECK allows `'archived'` (migrate.py:40), and `resolve_by_book` filters `status='active'` (works.py:268) so an archived derivative drops out of `candidates[]` on the next read. Use the per-call-site `ifMatch` option from EC-4b's `patchWork(pid, patch, token, {ifMatch})` — this is a human-paced, conflict-meaningful write, so If-Match is REQUIRED here (unlike `useWorldMap`).

(3) BUILD **BE-13a only** (XS, no DDL): add `name: str = Field(min_length=1, max_length=200)` to `DeriveBody` (routers/works.py:304-307); in the derive txn persist it into the Work's `settings` JSONB as `derivative_name` (pass through `works.create_derivative(..., settings={"derivative_name": name})`); add `name` to `DerivativeContextResponse` (works.py:426-441) sourced from `work.settings.get("derivative_name")`. `candidates[]` already ships `settings`, so the LIST gets the name for free — no serializer change. Wire `useDivergenceWizard.buildBody()` (frontend/src/features/composition/hooks/useDivergenceWizard.ts:106-121) + `DeriveBody` in types.ts:41 to actually SEND the name it already forces the user to type (today it is collected at :169 and thrown away — shipped `silent-success-is-a-bug`). Tests: 422 on empty name; round-trip name → `/derivative-context` → `candidates[i].settings.derivative_name`.

(4) BE-13 proper — `PATCH /works/{pid}/divergence-spec` and `POST|PATCH|DELETE /works/{pid}/overrides` — is **DEFERRED to v2** as `D-DIVERGENCE-SPEC-EDIT` (gate #2, large/structural). It is genuinely absent (derivatives.py has ONLY create_spec:44 / create_override:71 / get_spec_for_work:99 / list_overrides_for_work:112 — no UPDATE, no DELETE; the rows are written once inside the derive txn at routers/works.py:378-405). It is NOT deferred as "missing infra": it is deferred because the *write semantics* don't exist. These rows are consumed by `build_derivative_context` → the packer, and the derivative's prose was already grounded on the spec as-written; mutating it post-derive needs an invalidation/regeneration story (which chapters go stale, does the derivative's knowledge project get re-anchored) that is a design slice of its own. The panel renders spec + overrides READ-ONLY with EC-3a's inline note naming `works.py:378` — no disabled mystery button. This matches spec 36's already-locked EC-3a and its BE table (36_editor_craft_ports.md:435, :439), so it contradicts no sealed §0 decision (PO-1..4 are silent on divergence).

(5) Divergence MCP tools (the inverse GG-2 gap): NOT in Wave 6. Spec 36's BE-prereq table is the wave contract and lists none. Sane default the PO may veto: the divergence verbs are cheap, human-paced, and irreversible-ish (derive provisions a knowledge project) — a GUI-first v1 is right; revisit agent tools once the panel's shape is proven.

D-DECOMP-KEY-COLLIDES-ON-SPEC-BRANCH stays DORMANT under this scoping: nothing above copies `outline_node` rows into the derivative partition. `POST /derive` still doesn't. Add a one-line comment at the derive txn saying so, so a later builder doesn't "helpfully" copy the outline.

*Evidence:* services/composition-service/app/db/repositories/derivatives.py:44,71,99,112 (create_spec / create_override / get_spec_for_work / list_overrides_for_work — NO update, NO delete ⇒ UPDATE leg confirmed missing) · services/composition-service/app/routers/works.py:378-405 (spec + overrides written once, inside the derive txn) · services/composition-service/app/db/repositories/works.py:42 (`_UPDATABLE_COLUMNS = {active_template_id, status, settings}`) + :250-268 (`resolve_by_book`: `WHERE book_id=$1 AND status='active'` returns canonical + derivatives) ⇒ DELETE = `PATCH {status:'archived'}` EXISTS · services/composition-service/app/db/migrate.py:40 (`CHECK (status IN ('active','archived'))`) + :35-45 (no name column, but `settings JSONB NOT NULL DEFAULT '{}'`) · services/composition-service/app/routers/works.py:32-38 `_SELECT_COLS` (source_work_id, branch_point, settings) + :75-79 `_serialize_resolution` (candidates[]) + app/work_resolution.py:88-95 (status="found" ⇒ `works=[]`, the empty-candidates trap) ⇒ LIST EXISTS · services/composition-service/app/routers/works.py:304-307 `DeriveBody` (branch_point/divergence/entity_overrides — no `name`) + frontend/src/features/composition/hooks/useDivergenceWizard.ts:106-121,169 (name demanded, never sent) ⇒ BE-13a is the one real build

### Q-30-BE9-CORRECTION-SEAM-SCHEMA
BUILD THE SCHEMA CHANGE — the corrected BE-9 is right, and Wave 1 stays L. The candidate answer is adopted with three additions the spec missed. No PO call needed: no sealed decision (PO-1..4) touches this, and the CHECK constraint + stats query settle the only ambiguity (the accept half).

=== SLICE BE-9a — carry the job_id (schema + seam + driver) ===
1. services/composition-service/app/db/migrate.py:1494 — inside `CREATE TABLE IF NOT EXISTS authoring_run_units (...)` add `job_id UUID REFERENCES generation_job(id) ON DELETE SET NULL,` (NOT cascade — deleting a job must never delete the unit ledger row). Then, mirroring the D5 `critic_verdict` pattern at migrate.py:1516, add for already-migrated DBs: `ALTER TABLE authoring_run_units ADD COLUMN IF NOT EXISTS job_id UUID REFERENCES generation_job(id) ON DELETE SET NULL;`. NULLABLE, and NEVER backfill — a pre-existing unit row genuinely has no recoverable job id; a guessed FK is a fabricated learning signal.
2. app/db/models.py:761 (`class AuthoringRunUnit`) — add `job_id: UUID | None = None`.
3. app/db/repositories/authoring_runs.py:39-43 (`_UNIT_SELECT`) — add `u.job_id`.
4. authoring_runs.py `upsert_pending` (~:300-326) — add `job_id = NULL` to the `ON CONFLICT ... DO UPDATE SET` list, next to `post_revision_id = NULL, cost_usd = 0, critic_verdict = NULL`. A resume/re-run of the cursor unit must not leave the PREVIOUS attempt's job id on the row (that would let a reject name the wrong generation).
5. authoring_runs.py `transition_unit` + `mark_drafted` (:329) — add `job_id: UUID | None = None` and SET it on the drafted transition (same shape as `post_revision_id`/`cost_usd`).
6. app/services/authoring_run_service.py:197 (`DraftOutcome`) — add `job_id: UUID | None = None`. Populate it at BOTH success returns: :391 `return DraftOutcome(ok=True, cost_usd=cost, job_id=UUID(str(job_id_raw)) if job_id_raw else None)` and in `_poll_job` :408 `return DraftOutcome(ok=True, cost_usd=..., job_id=job_id)` (the id is already in scope there).
7. Driver at authoring_run_service.py:1186 — pass `job_id=outcome.job_id` into `self._units.mark_drafted(...)`.
8. Expose `job_id` in `_serialize_unit` (routers/authoring_runs.py) and the MCP unit serializer (mcp/server.py) — the Run Report/panel needs it to deep-link the generation.

=== SLICE BE-9b — the capture write (the load-bearing half) ===
9. app/deps.py:79 `get_authoring_run_service` — inject `GenerationCorrectionsRepo(get_pool())` and `GenerationJobsRepo(get_pool())`; `AuthoringRunService.__init__` (:625) takes `corrections=None, jobs=None` (tests inject fakes, same convention as `critic`/`late_restore`).
10. `reject_unit` (:919) — add a required `created_by: UUID` param (the HUMAN WHO CLICKED REJECT, not run.created_by — the correction repo stamps the *corrector*). Router passes `user_id` (routers/authoring_runs.py:363); MCP tool passes its caller id (mcp/server.py:1970). AFTER the restore succeeded AND `transition_unit(...→rejected)` returned non-None, write the correction:
    if rejected.job_id is not None and self._corrections is not None:
        job = await self._jobs.get(rejected.job_id)
        if job is not None and job.book_id == run.book_id:      # scope fence
            try:
                await self._corrections.create(job.project_id, rejected.job_id, created_by=created_by, kind="reject")
            except Exception: logger.warning(..., exc_info=True)   # never raise
    IMPORTANT (hole the spec missed): `authoring_runs` has NO project_id column (migrate.py:1417-1435) but `GenerationCorrectionsRepo.create` REQUIRES it — derive it from the loaded `generation_job.project_id` (models.py:364), fenced by `job.book_id == run.book_id`. Do not add project_id to authoring_runs.
    The correction write is BEST-EFFORT and must NEVER fail the reject: the chapter is already reverted and the row already flipped; a 502 here would strand the caller. Log and swallow. job_id IS NULL (legacy row) → skip the write silently, reject still succeeds.
11. `accept_unit` (:896) — WRITES NOTHING. BE-9's "accept_unit/reject_unit" phrasing is misleading and a builder must not act on it literally: `generation_correction.kind` is `CHECK (kind IN ('edit','pick_different','regenerate','reject'))` (migrate.py:365) — there is no `accept` kind — and `correction_stats` DERIVES `accept_rate = (generations - corrected_jobs)/generations`. Accept-as-is is captured BY ABSENCE (the §2 H2 self-reinforcement guard). Adding an `accept` kind would need a CHECK migration AND would double-count itself into `corrected_jobs`, inverting the eval signal. Leave accept_unit untouched.
12. MCP tool `composition_record_correction` — thin wrapper over the existing correction path (routers/engine.py:1718). Args: `job_id` (UUID), `kind` (ENUM closed set: edit|pick_different|regenerate|reject — register in CLOSED_SET_ARGS per the Frontend-Tool-Contract), optional `chosen_candidate_index`, `guidance`, `changed_blocks`. It is the Studio's *editor-side* capture door; it is NOT the reject seam (an LLM must never be the only writer of the flywheel signal — that is exactly the G-CORRECTION-FLYWHEEL defect).

=== TESTS (each slice is done only when its test asserts the EFFECT) ===
- migration: fresh boot AND legacy-shape boot both end with `authoring_run_units.job_id`; pre-existing rows are NULL (never backfilled).
- repo: mark_drafted persists job_id; upsert_pending RESETS it to NULL on a resume.
- seam: DraftOutcome.job_id is set on BOTH the status=completed path and the status=pending→_poll_job path.
- service: reject_unit on a unit WITH job_id → exactly ONE generation_correction row, kind='reject', created_by = the rejecting caller, project_id = the job's project. reject_unit on a legacy unit (job_id NULL) → ZERO rows, reject still 200. corrections.create raising → reject STILL succeeds (no rollback of the revert). accept_unit → ZERO correction rows.
- live-smoke (Wave 1 DoD): run an agent-mode unit end-to-end, reject it, then GET /works/{pid}/correction-stats and see reject_n move.

DoD per PO policy: /review-impl runs at wave close; any bug it finds is fixed before the wave closes. BE-9c (the CORRECTABLE_OPERATIONS allowlist for the stats denominator) is a SEPARATE slice, not this question.

*Evidence:* services/composition-service/app/db/migrate.py:368 (`job_id UUID NOT NULL REFERENCES generation_job(id)`) + migrate.py:365 (`kind IN ('edit','pick_different','regenerate','reject')` — no 'accept') · migrate.py:1494-1516 (authoring_run_units — no job_id column) · migrate.py:1417-1435 (authoring_runs — book_id but NO project_id, the hole the spec missed) · services/composition-service/app/services/authoring_run_service.py:197-202 (DraftOutcome = ok/cost_usd/error), :377-391 (payload['job_id'] read for cost, then DISCARDED), :408 (_poll_job has job_id in scope), :919 (reject_unit), :1186 (driver mark_drafted call) · services/composition-service/app/db/repositories/authoring_runs.py:39-43 (_UNIT_SELECT), :300-326 (upsert_pending DO UPDATE reset list), :329 (mark_drafted) · services/composition-service/app/db/repositories/generation_corrections.py (create(project_id, job_id, created_by=…) + the `SELECT 1 FROM generation_job WHERE id=$1 AND project_id=$2` ownership guard; correction_stats derives accept_rate = gens - corrected_jobs) · services/composition-service/app/db/models.py:364 (GenerationJob.project_id), :761 (AuthoringRunUnit) · services/composition-service/app/deps.py:79 (get_authoring_run_service), :175 (get_generation_corrections_repo)

### Q-30-BE6-MOTIF-SUGGEST-ROUTE
BUILD IT AS A REST GET IN composition-service (confirms the spec's own candidate; no bridge entry, wave stays single-service). Concrete slice:

**1. Add the route** at the end of `services/composition-service/app/routers/motif.py` (that router already carries prefix `/v1/composition`; no path collision — `works.py` owns `/works/{project_id}` exactly, this is a deeper segment):

`@router.get("/works/{project_id}/motifs/suggest")`
Signature: `project_id: UUID` (path) · `chapter_id: UUID = Query(...)` (REQUIRED → FastAPI gives the spec'd 422) · `limit: int = Query(10, ge=1, le=25)` · `detail: str = Query("summary", pattern="^(summary|full)$")` · `language: str | None = Query(None, max_length=20)` (override) · deps: `get_current_user`, `get_bearer_token`, `get_works_repo`, `get_outline_repo`, `get_motif_retriever` (already wired, `app/deps.py:205`), `get_book_client_dep`, `get_grant_client_dep`.

Body — mirror the MCP handler `composition_motif_suggest_for_chapter` (`app/mcp/server.py:2224-2266`) exactly:
  a. `work = await works.get(project_id)`; `None` → `HTTPException(404, _NOT_FOUND)` (uniform, no oracle).
  b. `await _gate_book(grant, work.book_id, user_id, GrantLevel.VIEW)` — the existing helper at `motif.py:57`.
  c. `node = await outline.get_node(chapter_id)`; `if node is None or node.project_id != project_id: 404 _NOT_FOUND` — this is the per-route IDOR check, do NOT drop it (it mirrors `server.py:2242-2244`).
  d. **Scope resolution (do NOT copy the MCP bug — see below):** `genre_tags = await fetch_genre_tags(book, work.book_id, bearer)`; `lang = language or from_settings(work.settings).source_language`; `if lang in ("", "auto"): lang = "en"` (the retriever's `language` filter is hard equality, `motif_retrieve.py:410`).
  e. `candidates = await retriever.retrieve(user_id, book_id=work.book_id, project_id=project_id, genre_tags=genre_tags, language=lang, beat_role=None, tension=getattr(node, "tension_target", None), limit=limit)`.
  f. Response: `{"candidates": [{"motif": <projection>, "score": c.score, "match_reason": c.match_reason}], "count": n, "detail": detail, "project_id": str(project_id), "chapter_id": str(chapter_id)}`. `full` = `_redact_for_viewer(c.motif, is_owner=(c.motif.owner_user_id == user_id))`; `summary` = that dict narrowed to the SAME ref key-set the MCP tool uses (`server.py:222-225`: id, code, name, kind, summary, genre_tags, language, visibility, status, version) — i.e. no roles/beats/examples. `embedding` is never projected (the retriever already strips it, `motif_retrieve.py:_row_to_motif`).

**2. One home for the genre lookup:** move `_book_genre_tags` out of `app/routers/plan.py:473-486` into `app/clients/book_client.py` as `async def fetch_genre_tags(book, book_id, bearer) -> list[str]` (same best-effort body: `BookClientError` / empty → `[]`), and re-point `plan.py`'s two call sites (`plan.py:231`, `plan.py:298`) at it. No duplication.

**3. FIX-NOW (same slice, one-line class of bug, clears no defer gate): the MCP twin is broken.** `_book_or_deny` returns `WorkScopeMeta`, which has ONLY `book_id/work_id/project_id` (`app/db/repositories/works.py:49-57`), so `server.py:2251-2252`'s `getattr(meta, "genre_tags", [])` is ALWAYS `[]` and `getattr(meta, "language", None) or "en"` is ALWAYS `"en"` — and because the candidate SQL hard-filters `AND language = $2` (`motif_retrieve.py:410`), motif-suggest returns **zero candidates for every non-English Work**. In the MCP handler, after `_book_or_deny`, load the Work (`work = await WorksRepo(get_pool()).get(pid)`) and use the identical step (d) resolution (`from_settings(work.settings)` + `fetch_genre_tags` with `mint_service_bearer(tc.user_id, settings.jwt_secret)` — the pattern already used at `server.py:484-487`). REST and MCP must agree; do not ship a REST mirror that is silently better than its twin.

**4. Tests** — `services/composition-service/tests/unit/test_motif_suggest_route.py` (new), 5 cases: (1) 200 shape — `candidates[].{motif,score,match_reason}` with `match_reason` carrying tension/genre/precond/cosine; (2) **IDOR** — a `chapter_id` whose node belongs to another Work → 404 `_NOT_FOUND`; (3) no-grant caller → 404 at `_gate_book`; (4) missing `chapter_id` → 422; (5) `detail=summary` drops roles/beats but keeps `score`+`match_reason`. Plus one regression test pinning the fix in (3): a Work with `settings={"source_language":"vi"}` retrieves with `language="vi"` (assert the retriever call args), NOT `"en"`.

Sane default I am picking (veto-able): `limit` default 10 and `detail` default `summary` per spec 33 BE-M4; the `language` query param is an optional override, not required by the FE.

*Evidence:* No route today: services/composition-service/app/routers/motif.py:151-386 (list/catalog/book/get/create/patch/delete/adopt only). Mirror source: services/composition-service/app/mcp/server.py:2208-2266 (composition_motif_suggest_for_chapter). Engine wired: services/composition-service/app/deps.py:205 (get_motif_retriever). Gate helper to reuse: app/routers/motif.py:57 (_gate_book) + app/routers/works.py:409-421 (GET /works/{project_id} pattern). THE BUG: app/db/repositories/works.py:49-57 (WorkScopeMeta has no genre_tags/language) vs app/mcp/server.py:2251-2252 (getattr on it) vs app/db/repositories/motif_retrieve.py:410 (`AND language = $2` hard filter) ⇒ zero candidates for any non-English Work. Correct resolution already in app/routers/plan.py:228 + app/routers/plan.py:473-486.

### Q-30-BE18-SETTINGS-BLOB-REPLACE
Take the MERGE branch (server-side `||`), not the "require If-Match" branch — and add the delete-key escape hatch the naive `||` answer forgets. Also fix the version bump, because If-Match is currently a fake guarantee.

BUILD (composition-service, ~XS, 3 files):

1. `services/composition-service/app/db/repositories/works.py:311-313` — replace the full-blob REPLACE with a shallow merge + explicit unset. In the `for field, value in updates.items()` loop, for `field == "settings"`:
   - split the patch dict: `_set = {k: v for k, v in value.items() if v is not None}`, `_del = [k for k, v in value.items() if v is None]`
   - append TWO params and emit:
     `settings = (COALESCE(settings, '{}'::jsonb) || $N::jsonb) - $M::text[]`
     where `$N = json.dumps(_set)` and `$M = _del` (asyncpg binds a Python list to `text[]` directly).
   - Semantics to document in the docstring: PATCH settings now MERGES top-level keys; an explicit `null` value for a key DELETES that key. This is the right merge depth — settings is read as flat top-level keys (`packer/profile.py:73-77`, `engine.py:1766`, `progress.py:68`).

2. `services/composition-service/app/db/repositories/works.py:322-323` — move `set_clauses.append("version = version + 1")` OUT of the `if expected_version is not None:` block so EVERY non-empty update bumps `version`. Rationale (this is the load-bearing find): today a plain PATCH mutates `settings` and leaves `version` untouched, so a concurrent client's stale If-Match still validates — the OCC that the router already implements (`_parse_if_match`, 412, `VersionMismatchError`) is unsound without this. The existing "empty effective patch → no version bump" early-return at :305-306 already protects the GET-like no-op path, so this is safe. Run the composition suite and update any test that pinned the old "no bump without If-Match" behavior (expected: `integration/db/test_repositories.py`).

3. `services/composition-service/app/routers/works.py:64-72` — the `_validate_known_setting_enums` validator must not reject a deliberate unset: change the guard to `if v is not None and v.get("assembly_mode") is not None and v["assembly_mode"] not in ASSEMBLY_MODES`. Otherwise `{"assembly_mode": null}` (the new delete form) 422s.

4. `frontend/src/features/composition/api.ts:439-445` — rewrite the warning comment: the server now merges; callers MAY send only the changed keys, and send `null` to clear one. Do NOT rip out the existing hand-merges in `useWork.ts:135`, `useChapterAssembly.ts:33`, or BE `routers/references.py:137` — merging a superset is idempotent, so they stay correct. Simplifying them is optional cleanup, not required for BE-18.

TESTS (name them explicitly):
- repo test: seed `settings={"a":1,"b":2}` → `update(pid, {"settings": {"b": 3}})` → row is `{"a":1,"b":3}` (proves no key loss — this is the lost-update regression test).
- repo test: `update(pid, {"settings": {"a": None}})` → row is `{"b":2}` (proves delete works).
- repo test: two sequential plain PATCHes → `version` is 3 from 1 (proves the bump; without it If-Match is defeatable).
- router test: `PATCH` with `{"settings": {"assembly_mode": null}}` → 200, not 422.

Do NOT require If-Match on `patchWork` — it would force a 412 retry loop into every FE settings caller for a benign toggle write, and same-key last-write-wins on a settings toggle is acceptable. If-Match stays OPTIONAL and now actually works (fix 2) for any caller that wants strict OCC.

Default I am picking (veto-able): merge is the contract; If-Match is opt-in.

*Evidence:* services/composition-service/app/db/repositories/works.py:312-313 (`params.append(json.dumps(value))` / `settings = ${len(params)}::jsonb` — the full-blob REPLACE) · works.py:323 (`version = version + 1` sits INSIDE `if expected_version is not None`, so plain PATCHes never bump the version — If-Match is currently unsound) · works.py:41-46 (`_UPDATABLE_COLUMNS` includes `settings`; not in `_NULLABLE_UPDATE_COLUMNS`) · routers/works.py:122-128, :588, :597-601 (If-Match parse + 412 already wired end-to-end — NOT unbuilt infra) · routers/works.py:64-72 (`_validate_known_setting_enums` would 422 on a null assembly_mode) · frontend/src/features/composition/api.ts:439-445 (the hand-merge warning) · useWork.ts:135 + useChapterAssembly.ts:33 + services/composition-service/app/routers/references.py:137 (three hand-merge sites, incl. a BE one) · packer/profile.py:73-77, engine.py:1766, progress.py:68 (settings read as flat top-level keys ⇒ shallow `||` is the correct merge depth)

### Q-30-BE-A1-ARC-SPAN-STRIDED
CONFIRMED — the 🔴 CORRECTION is real, and the fix is the spec's candidate answer, SHARPENED in two ways: (a) do NOT hand-write dense-rank SQL at the route — reuse the ONE existing dense-ranked implementation, StructureRepo.derived_blocks() (structure.py:244-315), which the LIST route already serves; (b) the defect is BIGGER than the spec says — is_contiguous is strided too, so replace the WHOLE derived block, not just min/max.

BUILDER INSTRUCTION (2 files, ~6 lines, + 2 tests):

1. services/composition-service/app/routers/arc.py:455 — REPLACE `out["span"] = await structures.span(node.id)` with:

    # BE-A1 — the inspector renders the DENSE-RANKED ordinals a reader means
    # ("Chapters 41–58"), never StructureRepo.span()'s RAW STRIDED story_orders
    # ("41000–58000"). Reuse derived_blocks() — the ONE dense-rank implementation
    # (structure.py:244) the LIST route already serves — so GET and LIST cannot drift.
    # span() itself is UNTOUCHED: the packer (lenses.py:322 → _arc_position) divides a
    # scene's RAW strided story_order by these bounds; dense-ranking the repo would clamp
    # every scene to "~100% through arc" and silently corrupt every generation prompt.
    _empty = {"span": None, "is_contiguous": True, "chapter_count": 0, "first_story_order": None}
    out.update((await structures.derived_blocks(node.book_id)).get(node.id, _empty))

   Payload shape becomes IDENTICAL to a LIST node (arc.py:427-434): top-level `span: {from_order, to_order} | None`, `is_contiguous`, `chapter_count`, `first_story_order`. This is a deliberate shape change from the old nested `{min_story_order, max_story_order, ...}` — verified un-consumed (no FE reference to min_story_order/max_story_order; no test asserts get_arc's span), and it means the arc-inspector reuses the Hub's renderer instead of a second one. Archived node ⇒ empty block, exactly as LIST?include_archived=true already behaves.

2. services/composition-service/app/mcp/server.py:4255 — SAME replacement, same comment, in composition_arc_get. (node.book_id is on the model; derived_blocks is one aggregate query.)

3. LEAVE StructureRepo.span() EXACTLY AS IS. Do not "fix" it, do not add a flag, do not deprecate it. Its third caller is the packer and it is CORRECT for that caller. Add a one-line docstring guard at structure.py:641: "RAW STRIDED units — the packer's axis (lenses.py:322). Display callers MUST use derived_blocks() instead (BE-A1)."

4. TESTS (both must red before the fix):
   - services/composition-service/tests/unit/test_arc_hub_routes.py — new test: stub derived_blocks to return {NODE: {"span": {"from_order": 41, "to_order": 58}, "is_contiguous": True, "chapter_count": 18}}, stub span() to return the strided {"min_story_order": 41000, "max_story_order": 58000, ...}; GET /arcs/{id} must return span == {"from_order": 41, "to_order": 58} and MUST NOT contain 41000 anywhere in the payload. Mirror it for the MCP tool composition_arc_get.
   - services/composition-service/tests/integration/db/test_structure_repo.py — ADD a test that seeds STRIDED chapters (e.g. story_orders 1000, 2000, 3000 — the production writer's axis, which the existing span tests never model: they seed 0,1,2 and so mask the bug) and asserts BOTH: repo.span() still returns raw {min:1000, max:3000} (the packer's contract, pinned so nobody "fixes" it), AND derived_blocks()[arc]["span"] == {"from_order": 1, "to_order": 3} with is_contiguous True.

Note for the PO (veto if you disagree): I changed the GET/MCP span payload shape to match LIST rather than dense-ranking in place inside the old {min_story_order, max_story_order} keys. Rationale = one name for one concept + zero duplicated dense-rank formula; cost = nothing, since nothing consumes the old shape yet and the panel isn't built.

*Evidence:* services/composition-service/app/db/repositories/structure.py:641-686 (span() = raw min/max(story_order); is_contiguous at :680 does (max-min+1)==count on STRIDED values ⇒ always False for ≥2 chapters in prod) · services/composition-service/app/packer/lenses.py:241-254 + :322 (_arc_position divides a scene's RAW strided story_order by span's bounds ⇒ dense-ranking the repo clamps every scene to 100% — the corruption the spec warns of, confirmed) · services/composition-service/app/db/repositories/structure.py:244-315 (derived_blocks() — the EXISTING dense_rank() implementation, its SQL comment at :270-277 documents this exact trap) · services/composition-service/app/routers/arc.py:455 and services/composition-service/app/mcp/server.py:4255 (the two display doors, both calling span()) · services/composition-service/app/routers/arc.py:427-434 (LIST already serves derived_blocks — the shape to match) · services/composition-service/tests/integration/db/test_repositories.py:916 (derived_blocks proven correct UNDER STRIDE: first_story_order == 1*S while span == {from_order:1,to_order:2}) · services/composition-service/tests/integration/db/test_structure_repo.py:317 (the span() test seeds UNSTRIDED [0,1,2] — the fixture that masked is_contiguous) · services/composition-service/app/db/repositories/outline.py:533 (new_order = sort * stride — the strided writer)

### Q-30-BE10-STYLE-VOICE-MCP
BUILD 7 net-new MCP tools on composition-service, appended to services/composition-service/app/mcp/server.py before the `# ── ASGI factory ──` block (~line 4774), copying the composition_canon_rule_* pattern verbatim (server.py:1069-1200): a `ForbidExtra` pydantic args model + `@mcp_server.tool(name=…, description=…, meta=require_meta(tier, "book", synonyms=[…], tool_name=…))`, then `tc=_ctx(ctx)` → `await _book_or_deny(WorksRepo(get_pool()), tc, pid, GrantLevel.VIEW|EDIT)` → repo call → `out["_meta"]={"undo_hint": _undo(...)}`.

THE 7 TOOLS (mirror the 6 shipped REST routes + expose the already-written resolver):
1. composition_style_list (R): project_id → VIEW → StyleProfileRepo.list_all(pid) → {"items":[…]}
2. composition_style_resolve (R): project_id, scene_id?, chapter_id? → VIEW → StyleProfileRepo.resolve(pid, scene_id, chapter_id) → {"density","pace","source_scope_type","source_scope_id"} or {"effective": null, "note":"no override — packer stays neutral"}. This is the SET-1 "effective value + source tier" read the Wave-6 panel also needs; the repo method EXISTS (style_voice.py resolve) — do NOT write a second resolver (css-var-duplicated class).
3. composition_style_set (A): project_id, scope_type: Literal["work","chapter","scene"] (CLOSED SET ⇒ Literal, mirroring StyleScope at app/db/models.py:332), scope_id, density: Annotated[int, Field(ge=0,le=100)], pace: same → EDIT → read prior via list_all filtered on (scope_type,scope_id) → upsert(..., created_by=tc.user_id) → undo_hint = composition_style_set with the PRIOR density/pace, or composition_style_clear when there was no prior row.
4. composition_style_clear (A): project_id, scope_type, scope_id → EDIT → read prior → delete() → undo_hint = composition_style_set with prior values (None if nothing removed).
5. composition_voice_list (R): project_id → VIEW → VoiceProfileRepo.list_all(pid).
6. composition_voice_set (A): project_id, entity_id, entity_name (1-200), tags: list[str] with ≤20 tags / ≤40 chars each (mirror _Tag + max_length=20 at routers/style_voice.py:33,111) → EDIT → prior via list_for_entities(pid,[entity_id]) → upsert() → undo = set-with-prior or composition_voice_clear.
7. composition_voice_clear (A): project_id, entity_id → EDIT → prior → delete() → undo = composition_voice_set with prior name+tags.
ReferenceViolationError from either upsert (project has no composition work) → return {"success": False, "error": …}, never a 5xx.

THE 3 REGISTRATION SURFACES — this is what BE-10's "3-schema-source" warning actually means HERE. (The knowledge-service 3-schema memory does NOT apply: composition uses make_stateless_fastmcp("composition") (server.py:104) with ONE pydantic args model per tool. But FastMCP still STRIPS any arg absent from that model, and there are 3 places a tool must be REGISTERED or it is invisible / fails closed):
  (1) app/mcp/server.py — the @mcp_server.tool + args model (the advertised inputSchema).
  (2) app/services/authoring_run_service.py:127 ALLOWLISTABLE_TOOLS — add all 7 names, else an authoring run can never call them.
  (3) services/mcp-public-gateway/src/scope/tool-policy.ts — TOOL_POLICY is DEFAULT-DENY / fail-closed (tool-policy.ts:9). Add the 3 reads as { tier: 'read', domains: ['composition'] } (~line 133) and the 4 writes as { tier: 'write_auto', domains: ['composition'] } (~line 236, beside composition_canon_rule_*). NO confirm token — these are cheap, reversible, zero-spend config writes, same class as composition_canon_rule_create.
  contracts/tool-liveness.json is GENERATED (scripts/eval/tool_liveness/manifest.py — "do not hand-edit"; an absent tool = unproven, not broken) ⇒ NO edit required.

TESTS (services/composition-service/tests/unit/test_mcp_server.py): the existing test_every_tool_carries_valid_meta (line 191) auto-covers tier/scope/synonyms once registered (a missing `synonyms` reds). Add per-tool: (a) set→list round-trip; (b) scope_type outside the Literal is rejected; (c) resolve returns the SCENE row when scene+work rows both exist (most-specific-wins — the packer's contract at pack.py:270); (d) a no-grant caller gets the uniform_not_accessible error on BOTH read and write; (e) _meta.undo_hint round-trips (set → undo → prior restored).

SIZE holds at S: no migration, no new repo, no new engine — the tables, repos, E0 gate and packer consumption all ship today. Sequence BEFORE the Wave-6 `style-voice` panel slice so panel + tools land against ONE resolution semantics. DEFAULT I PICKED (veto-able): including tool #7 composition_style_resolve, which the spec's "composition_style_* + composition_voice_*" did not enumerate — it is free (the repo method exists) and it is the agent's half of the panel's most-specific-wins display.

*Evidence:* ZERO tools today: `grep -rn "style|voice" services/composition-service/app/mcp/` → no matches (server.py is 4,783 lines). Everything below the MCP layer is SHIPPED: services/composition-service/app/db/repositories/style_voice.py (StyleProfileRepo.upsert/list_all/resolve/delete + VoiceProfileRepo.upsert/list_all/list_for_entities/delete); services/composition-service/app/packer/pack.py:263-283 folds them into every draft prompt (`style_profile_repo.resolve(...)` → `_replace(profile, density_level=sp.density, pace_level=sp.pace)`; `voice_profile_repo.list_for_entities(...)` → `character_voices`); services/composition-service/app/routers/style_voice.py:60-150 = the 6 human REST routes with the E0 gate (`_gate_work`, VIEW/EDIT, 404-no-oracle). Pattern to copy: services/composition-service/app/mcp/server.py:1069-1200 (composition_canon_rule_create/update/delete). Gate helper: server.py:155 `_book_or_deny`. Registration surfaces: services/composition-service/app/services/authoring_run_service.py:127 (ALLOWLISTABLE_TOOLS) and services/mcp-public-gateway/src/scope/tool-policy.ts:9 (default-deny), :133 reads / :236 composition writes. Closed-set enum source: services/composition-service/app/db/models.py:332 `StyleScope = Literal["work","chapter","scene"]`.

### Q-30-BE14-KG-WRITE-ROUTES
BUILD BOTH ROUTES — the spec's "2 thin route mirrors" is correct and confirmed by code. Neither engine has any REST surface today (both are MCP-tool-only), and both are buildable in this repo, so this is unbuilt work, not a blocker.

ROUTE 1 — projection.
File: services/knowledge-service/app/routers/public/projects.py (existing router, prefix "/v1/knowledge/projects", line 105). Add:
  @router.post("/{project_id}/project-entities", response_model=ProjectEntitiesResult, status_code=200)
  async def project_entities(project_id: UUID = Path(...), body: ProjectEntitiesRequest = Body(default=ProjectEntitiesRequest()), owner: UUID = Depends(require_project_grant(GrantLevel.EDIT)), meta: ProjectMeta | None = Depends(project_meta_dep)) -> ProjectEntitiesResult
Final path: POST /v1/knowledge/projects/{project_id}/project-entities.
Body: {"entity_ids": string[] | null} (null/omitted = whole active glossary; strip+drop empties exactly as app/tools/graph_schema_tools.py:1647 does).
Handler body = a LITERAL port of _handle_kg_project_entities_to_nodes (graph_schema_tools.py:1626-1700), keeping ALL FOUR of its behaviours — do not thin these away:
  1. owner comes from require_project_grant(GrantLevel.EDIT) (grant_deps.py:108 — returns the project OWNER, the REST twin of _resolve_project_owner(ctx, EDIT)); pass user_id=str(owner), NOT the caller.
  2. book_id from project_meta_dep (grant_deps.py:60, returns (owner, book_id)). book_id is None -> HTTP 409 with the tool's exact message ("this project isn't linked to a book, so it has no glossary entities to project — link a book to the project first"). meta is None is already 404'd by the grant dep.
  3. async with neo4j_session(): await project_glossary_entities_to_nodes(session, get_glossary_client(), user_id=str(owner), project_id=str(project_id), book_id=book_id, entity_ids=entity_ids or None)  [anchor_loader.py:194]
  4. STILL INSIDE the same session: best-effort reconcile_project_stats(projects_repo._pool, session, owner, project_id) in try/except-log. This is NON-NEGOTIABLE — graph_schema_tools.py:1665-1685 records that this call is the ONLY production writer of stat_updated_at; a REST mirror that omits it re-opens D-KG-STAT-CACHE-DEAD (entity_count stays UNKNOWN, the vision-to-book rail stalls at STOP_UNKNOWN).
Response model mirrors the tool dict 1:1: {nodes_created, nodes_existing, entities_seen, skipped, truncated?, nodes_conflicted?, notes?: string[]} from ProjectionResult (anchor_loader.py:165-192). Surface truncated + conflicted — never report a partial projection as complete.

ROUTE 2 — forget.
New file: services/knowledge-service/app/routers/public/facts.py, written as a copy of app/routers/public/relations.py:42-92 with relation→fact:
  facts_router = APIRouter(prefix="/v1/knowledge", tags=["facts"], dependencies=[Depends(get_current_user)])
  @facts_router.post("/facts/{fact_id}/invalidate", response_model=Fact)
  async def invalidate_fact_endpoint(fact_id: str = Path(min_length=1, max_length=200), user_id: UUID = Depends(get_current_user)) -> Fact:
      async with neo4j_session() as session:
          fact = await invalidate_fact(session, user_id=str(user_id), fact_id=fact_id)
      if fact is None: raise HTTPException(404, "fact not found")
      return fact
Final path: POST /v1/knowledge/facts/{fact_id}/invalidate. CALLER-scoped, NOT owner-resolved — invalidate_fact is user_id-keyed (facts.py:675) and app/tools/executor.py:713-716 states the boundary is the user, not the project; another user's fact simply doesn't match -> 404. Idempotent (re-invalidate returns the fact).
DEFAULT I AM SETTING (PO may veto): the fact route emits NO outbox correction event. There is no FACT_CORRECTED type (app/events/outbox_emit.py:63-66) and memory_forget emits nothing — inventing an event type + a learning-service consumer is not a "thin mirror". Parity with the tool wins.

MOUNT: services/knowledge-service/app/main.py — add `from app.routers.public import facts as public_facts` and `app.include_router(public_facts.facts_router)` beside public_relations.relations_router (main.py:771). projects.py is already mounted (main.py:777) — no mount change needed for route 1.

DO NOT TOUCH (the spec's own warning, verified): POST /pending-facts/{id}/reject (app/routers/public/pending_facts.py — the pre-commit queue) and /internal/admin/.../reject-fact (internal_admin.py). Different objects, different lifecycle stage.

TESTS (required for wave close):
- services/knowledge-service/tests/unit/test_fact_invalidate_route.py — mirror tests/unit/test_relation_correction.py: 200 + valid_until set; second call idempotent; other user's fact -> 404; unknown id -> 404.
- Extend services/knowledge-service/tests/unit/test_project_tools.py (or new test_project_entities_route.py): 200 with counts; entity_ids subset honoured; book-less project -> 409; non-grantee caller -> 404; VIEW-only grantee -> 403; and a SPY assert that reconcile_project_stats was CALLED (the mirror's own regression guard — a green route test that doesn't assert the recount is exactly the false-green D-KG-STAT-CACHE-DEAD hid behind).
- Contract: add both to contracts/api/knowledge-service/ (the openapi file that already carries /relations/{id}/invalidate).
FE (Wave 8a consumes these): add knowledgeApi.projectEntities(projectId, entityIds?) and knowledgeApi.invalidateFact(factId) in frontend/src/features/knowledge/api.ts next to invalidateRelation (api.ts:1722).

*Evidence:* Engines exist, REST does not: services/knowledge-service/app/db/neo4j_repos/facts.py:675 (invalidate_fact, user_id-keyed, idempotent) + services/knowledge-service/app/extraction/anchor_loader.py:194 (project_glossary_entities_to_nodes). Only callers are MCP tools: app/tools/executor.py:718 (memory_forget) and app/tools/graph_schema_tools.py:1651 (kg_project_entities_to_nodes). Mirror template: app/routers/public/relations.py:63 (POST /v1/knowledge/relations/{relation_id}/invalidate). Grant gate to reuse: app/auth/grant_deps.py:108 require_project_grant -> returns project OWNER; app/auth/grant_deps.py:60 project_meta_dep -> (owner, book_id). Mandatory stat recount the mirror must keep: app/tools/graph_schema_tools.py:1665-1685 ("the ONLY production writer of stat_updated_at"). No FACT_CORRECTED event exists: app/events/outbox_emit.py:63-66. Host router for route 1: app/routers/public/projects.py:105 (prefix /v1/knowledge/projects); mount point for route 2: app/main.py:771.

### Q-30-BE11-CANON-RESTORE
BUILD IT IN WAVE 1, alongside G-CANON-RULE-CRUD's Delete button. Mirror the outline_node restore shape exactly. Six concrete edits + tests:

1. REPO — services/composition-service/app/db/repositories/canon_rules.py
   a. Add `async def restore(self, project_id: UUID, rule_id: UUID) -> CanonRule | None` immediately after `archive()` (currently ends at line 166). Body = archive() inverted: `UPDATE canon_rule SET is_archived = false, updated_at = now() WHERE project_id = $1 AND id = $2 AND is_archived RETURNING {_SELECT_COLS}` → `_row_to_rule(row) if row else None`. The `AND is_archived` predicate makes it return None for a not-archived row (same "only flips the wrong-state row" discipline as archive), so the route can 404 honestly. Do NOT touch `version` (restore is not an OCC edit — archive doesn't bump it either).
   b. Change `list_all(self, project_id)` (line 88) to `list_all(self, project_id, *, include_archived: bool = False)` and build the predicate the way outline.py:743 does: `archived_pred = "" if include_archived else " AND NOT is_archived"`. Default False keeps every existing caller's behavior byte-identical. Leave `list_active` alone — the critic must never see an archived rule (§13 CC2).

2. ROUTER — services/composition-service/app/routers/canon.py
   a. Add `POST /canon-rules/{rule_id}/restore` (status_code=200) directly under `delete_canon_rule` (line 175-189), copying its body verbatim except the repo call: `project_id = await _rule_project_id(rule_id)` → `await _require_work(works, grant, user_id, project_id, GrantLevel.EDIT)` → `rule = await canon.restore(project_id, rule_id)` → `if rule is None: raise HTTPException(404, "canon rule not found or not archived")` → return `rule.model_dump(mode="json")`. This is safe as-is: `_rule_project_id` (line 94-105) reads the row by id with no archived predicate, so an archived rule still resolves its book for the grant gate.
   b. Add `include_archived: bool = False` to `list_canon_rules` (line 108) and pass it through: `canon.list_active(project_id) if active_only else canon.list_all(project_id, include_archived=include_archived)`. (`active_only` + `include_archived` together = active_only wins; that's fine, no new semantics.)

3. MCP — services/composition-service/app/mcp/server.py
   a. Add `composition_canon_rule_restore(ctx, project_id, rule_id)` next to `composition_canon_rule_delete` (line 1168-1202), same `_book_or_deny(..., GrantLevel.EDIT)` + the same "project-scope BEFORE mutating" prior-read guard at lines 1189-1194 (prior is None or prior.project_id != pid → uniform_not_accessible()), then `canon.restore(...)`. meta: tier "A", scope "book", synonyms ["restore canon rule","un-archive rule","undo delete canon rule"].
   b. DELETE the lie at server.py:1199-1201: replace `out["_meta"] = {"undo_hint": None}` with `out["_meta"] = {"undo_hint": _undo("composition_canon_rule_restore", project_id=project_id, rule_id=rule_id)}` and drop the "there is no un-archive repo method / undo unavailable" comment. The description at line 1170 already promises "reversible" — this is what makes that true.
   c. Add `include_archived: Annotated[bool, "Include soft-archived rules."] = False` to `composition_list_canon_rules` (line 497-508), mirroring outline's line 379.

4. FE API — frontend/src/features/composition/api.ts: add `restoreCanonRule(ruleId, token)` → `apiJson(`${BASE}/canon-rules/${ruleId}/restore`, { method: 'POST', token })` (copy `restoreNode`, api.ts:247). Add an optional `includeArchived` query param to `listCanonRules` (api.ts:567).

5. FE HOOK — frontend/src/features/composition/hooks/useCanonRules.ts: add `const restore = useMutation({ mutationFn: (id: string) => compositionApi.restoreCanonRule(id, token!), onSuccess: invalidate })` and return it. Note the query key `['composition','canon',projectId]` must include the archived flag, else the archived view serves the cached unarchived list.

6. FE PANEL — the new `quality-canon-rules` Studio panel (ported from CanonRulesPanel.tsx): the Delete button ships WITH an "Archived" toggle (list?include_archived=true) whose rows render a Restore button — mirroring OutlineTree.tsx:217 + OutlineNodeRow.tsx:149 (`data-testid="outline-action-restore"`); use `data-testid="composition-canon-restore"` to match the existing `composition-canon-archive` at CanonRulesPanel.tsx:86. DEFAULT I AM PICKING (veto-able): archived-view + Restore button, NOT a transient undo-toast — it matches the sibling pattern already shipped, survives a page reload, and needs no client-side id stash.

TESTS (all three homes already exist — extend, don't create):
- services/composition-service/tests/integration/db/test_repositories.py (its header already says "canon_rule active-listing + archive"): archive→restore round-trip; restore of a never-archived rule returns None; restore of another project's rule returns None; `list_all(include_archived=True)` includes the archived row and the default still excludes it; `list_active` NEVER returns a restored-then-re-archived rule.
- services/composition-service/tests/unit/test_outline_canon_routers.py: POST /canon-rules/{id}/restore → 200 with EDIT; 403 with VIEW-only; 404 when not archived; 404 for an unknown id.
- services/composition-service/tests/unit/test_mcp_server.py: delete's `_meta.undo_hint` is now non-null and names `composition_canon_rule_restore`; the restore tool denies a cross-project rule id (uniform_not_accessible).
- FE: a CanonRulesPanel test asserting Archived toggle → Restore click → POST hits /canon-rules/{id}/restore and the row returns to the active list.

Cost check per CLAUDE.md: writing the defer row costs more than the fix. Ship it. `/review-impl` at Wave 1 close covers it.

*Evidence:* services/composition-service/app/db/repositories/canon_rules.py:155-166 (archive() exists, no restore) · services/composition-service/app/mcp/server.py:1199-1201 ("archive() only flips a NOT-archived row; there is no un-archive repo method, so there is no verified reverse op to surface. Honest: undo unavailable." → undo_hint: None — while server.py:1170 advertises the delete as "reversible") · sibling shape to copy: services/composition-service/app/db/repositories/outline.py:1409 restore_node() + app/routers/outline.py:648 POST /outline/nodes/{node_id}/restore; app/db/repositories/structure.py:426 restore() + app/routers/arc.py:528 POST /arcs/{node_id}/restore · reachability: canon_rules.py:88-97 list_all hard-codes "NOT is_archived" (an archived rule is invisible → restore would be unreachable) vs outline.py:739-743 include_archived + routers/outline.py:179 + OutlineTree.tsx:217 / OutlineNodeRow.tsx:149 · gate already works for an archived row: routers/canon.py:94-105 _rule_project_id selects by id with no archived predicate.

### Q-30-BE17-REFERENCE-UPDATE
BUILD BE-17 IN WAVE 6 — do NOT defer it to v2. Overturn the spec's candidate (line 311 "Not a v1 blocker… v2" / line 434 "BE-17 deferred to v2"): this is ~40 LOC of unbuilt work, not a blocker, so CLAUDE.md's anti-laziness rule + "cheaper to fix than to write and carry the defer row" both apply. Nothing in §0 (PO-1..4) touches it. It needs NO gateway change: api-gateway-bff proxies the whole `/v1/composition` prefix by path filter (gateway-setup.ts:354), so a new verb on an existing prefix is transparent. Amend plan 30 lines 311 + 434 to BUILD-IN-WAVE-6.

SCOPE LIMIT (the conscious v1 line — write it into spec 36): PATCH is METADATA-ONLY (title/author/source_url). `content` is NOT editable, because a content edit re-embeds → a provider call → real money. Content edit = delete + re-add, and the panel must SAY so.

BUILD DETAIL — 4 files, in order:

(1) services/composition-service/app/db/repositories/references.py — add `update_meta` right after `get()` (ends line 114):
```python
async def update_meta(self, project_id: UUID, reference_id: UUID, fields: dict[str, str]) -> ReferenceSource | None:
    """Metadata-only update. NEVER touches `content`/`embedding` — a metadata edit
    must not re-embed (no provider call, no cost, no 502 path). Project-bound;
    None when missing/other-project (router → 404, no existence oracle)."""
    allowed = [k for k in ("title", "author", "source_url") if k in fields]
    if not allowed:
        return await self.get(project_id, reference_id)
    sets = ", ".join(f"{k} = ${i + 3}" for i, k in enumerate(allowed))
    sql = f"UPDATE reference_source SET {sets} WHERE project_id = $1 AND id = $2 RETURNING {_SELECT_COLS}"
    async with self._pool.acquire() as c:
        row = await c.fetchrow(sql, project_id, reference_id, *[fields[k] for k in allowed])
    return _row_to_ref(row) if row else None
```
Column names come ONLY from that closed literal tuple, never from the request body — no injection surface. There is no `updated_at` column (migrate.py:554-567) and none is needed (list orders by created_at DESC) — do not add one.

(2) services/composition-service/app/routers/references.py — add:
```python
class ReferenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")   # content/model_ref sent → 422, never a SILENT DROP
    title: Annotated[str, StringConstraints(max_length=500)] | None = None
    author: Annotated[str, StringConstraints(max_length=500)] | None = None
    source_url: Annotated[str, StringConstraints(max_length=500)] | None = None
```
`extra="forbid"` is load-bearing — this repo's `rest-write-mirror-drops-fields` bug class is Pydantic silently ignoring an undeclared write field; here the field is *deliberately unsupported*, so it must 422, not no-op.
Then `@router.patch("/references/{reference_id}")`, copying delete_reference's scope-bootstrap VERBATIM (references.py:156-167): fetchrow `project_id` from reference_source → None → 404 → `await _require_work(works, grant, user_id, row["project_id"], GrantLevel.EDIT)` → `ref = await refs.update_meta(row["project_id"], reference_id, body.model_dump(exclude_none=True))` → None → 404 → `return ref.model_dump(mode="json")`. It takes NO embedder dep — that absence IS the invariant.

(3) Same file, widen list_references (references.py:89-93) — the second leg, one line:
```python
model = reference_embed_model(work.settings)
return {"references": [r.model_dump(mode="json") for r in rows],
        "embed_model_set": model is not None,
        "reference_embed_model_source": model[0] if model else None,
        "reference_embed_model_ref": model[1] if model else None}
```
Additive — KEEP `embed_model_set` (test_references_router.py and useReferences.ts already consume it).

(4) Tests — services/composition-service/tests/unit/test_references_router.py: (a) `test_patch_updates_metadata_without_reembed` — assert the embedding-client mock's `.embed` was NOT called AND the title changed (that is the whole point of the slice); (b) `test_patch_rejects_content_field` → 422; (c) tenancy: PATCH on another book's reference → 403/404, mirroring the existing delete tenancy test; (d) `test_list_exposes_reference_embed_model_ref`.

FE (same wave, in the reference-shelf panel slice): frontend/src/features/composition/hooks/useReferences.ts — add `updateReference(id, {title, author, source_url})` hitting PATCH + list refresh; types.ts — extend the LIST response type with `reference_embed_model_ref`/`reference_embed_model_source`; the panel renders inline-editable title/author/url and a READ-ONLY content body with the note "content is fixed — delete and re-add to change it (re-embeds)". Wave-6 DoD still ends with /review-impl.

*Evidence:* services/composition-service/app/routers/references.py:79-93 (LIST returns only `embed_model_set: bool` — the "surface reference_embed_model_ref" leg is indeed unbacked, confirmed) · references.py:148-168 (delete_reference — the exact scope-bootstrap pattern PATCH copies; also confirms no PATCH/PUT exists anywhere on the router) · services/composition-service/app/db/repositories/references.py:99-125 (list/get/delete — no update method) · services/composition-service/app/db/migrate.py:554-567 (reference_source DDL: title/author/source_url are plain `TEXT NOT NULL DEFAULT ''` — updatable with zero migration) · services/api-gateway-bff/src/gateway-setup.ts:354 (`pathFilter: pathname.startsWith('/v1/composition')` — a new verb needs no gateway work) · docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:311,434 (the two rows this decision amends)

### Q-30-BE-A2-ARC-PATCH-OCC
ADOPT the spec's candidate answer — strict If-Match (428) + unconditional version bump. Two edits, BOTH required; the repo edit is the load-bearing one.

**(1) REPO — `services/composition-service/app/db/repositories/structure.py:376-382` (do this first).** Move the version bump OUT of the OCC branch so EVERY successful update bumps `version`. Keep the WHERE-guard conditional:

```python
set_clauses.append("updated_at = now()")
set_clauses.append("version = version + 1")   # ALWAYS — a write must be visible to OCC holders

version_clause = ""
if expected_version is not None:
    params.append(expected_version)
    version_clause = f" AND version = ${len(params)}"   # the GUARD stays optional
```
(i.e. delete the `set_clauses.append("version = version + 1")` line from inside the `if`, and hoist it.)

WHY this and not just the route: today the bump is coupled to the guard, so a blind write leaves `version` UNCHANGED. That does not merely make REST "weaker" — it DEFEATS the MCP door. Sequence: agent reads version=3 → a blind write lands (content changes, version stays 3) → agent calls `composition_arc_update(expected_version=3)` → its OCC check PASSES → silent clobber of the object that steers generation. `StructureRepo` is arc-only (3 callers: routers/arc.py:501, mcp/server.py:4379, engine/arc_apply.py:497), so this change is confined to arcs — no blast radius.

Note `arc_apply.py:497` intentionally passes `expected_version=None` (comment: "apply is a deliberate snapshot, not an OCC-guarded field edit"). LEAVE that call site alone — it keeps its unguarded write, but now that write correctly bumps `version`, so a concurrent holder's stale token is properly rejected instead of silently sailing through. Fixing only the route would leave this hole open.

**(2) ROUTE — `services/composition-service/app/routers/arc.py:489-505` (`patch_arc`).** Make If-Match required, mirroring the in-repo precedent at `services/knowledge-service/app/routers/public/entities.py:1054-1063` verbatim in shape. Insert immediately after `_gate_arc(...)`:

```python
expected = _parse_if_match(if_match)
if expected is None:
    raise HTTPException(
        status_code=428,   # status.HTTP_428_PRECONDITION_REQUIRED
        detail="If-Match header required — GET the arc first to obtain its version",
    )
updated = await structures.update(node.id, patch, expected_version=expected)
```
Keep the existing 412 `STRUCTURE_VERSION_CONFLICT` handler (which already returns `current` as the body) unchanged — the FE resets its baseline from it without a second GET. `_parse_if_match` (arc.py:79-85) already accepts composition's bare-integer header format (`String(version)`, per frontend/src/features/composition/api.ts:237), so no header-format work is needed.

**SCOPE FENCE — do NOT generalize.** Fix ONLY `/arcs/{node_id}`. Leave `works.py:282`, `outline.py:1017`, `canon_rules.py:111`, `arc_template_repo.py:142` on optional-If-Match: they have LIVE FE consumers that send the header conditionally (`api.ts:237`, `api.ts:262` — `version !== undefined ? headers : {}`), and 428-ing them would break shipped OutlineTree flows. That is a different gap, not this one. Also out of scope: `move()`/`archive()`/`restore()` don't bump version either, but they mutate rank/parent/is_archived, which are NOT patchable fields and are not what this OCC token guards.

**TESTS (`services/composition-service/tests/unit/test_arc_hub_routes.py` — it currently has ZERO PATCH /arcs coverage, so nothing goes red; these are all NEW):**
1. `PATCH /v1/composition/arcs/{id}` with NO If-Match → **428**, and assert the row is UNCHANGED (the write must not land).
2. PATCH with a stale If-Match → **412**, body carries `code=STRUCTURE_VERSION_CONFLICT` + `current`.
3. PATCH with the correct If-Match → **200**, and `updated["version"] == prior + 1`.
4. **The regression test that proves the repo half** (this is the one that would have caught it): call `StructureRepo.update(nid, {...}, expected_version=None)` directly (the `arc_apply` path), then assert `version` **incremented**; then assert a follow-up `update(..., expected_version=<pre-apply version>)` raises `VersionMismatchError`. Without the repo hoist, this test reds.

**FE contract note for Wave 2 (G-ARC-SPEC-CRUD / arc-inspector, DBT-06):** the inspector's save path MUST send `If-Match: String(version)` from the `version` returned by `GET /arcs/{node_id}` (already in the payload), and MUST handle 412 by resetting its baseline from the response's `current` — same discipline as OutlineTree (arc.py:315 names it as the precedent). A 428 in the browser means the FE forgot the header — treat it as a bug, not a user-facing state.

DEFAULT FLAGGED FOR PO VETO: this makes the REST door strictly stricter, so any *future* unguarded arc PATCH caller must now read-then-write. That is the intent (it is the object that steers generation), and there are no current unguarded callers, so the cost is zero today.

*Evidence:* services/composition-service/app/db/repositories/structure.py:379-382 — `if expected_version is not None:` wraps BOTH the `AND version = $N` guard AND `set_clauses.append("version = version + 1")` ⇒ a blind write leaves `version` unchanged (invisible to OCC holders). · services/composition-service/app/routers/arc.py:489-505 — `patch_arc`, `if_match: str | None = Header(default=None, alias="If-Match")` passed straight to `expected_version=_parse_if_match(if_match)`; no 428. · services/composition-service/app/mcp/server.py:4331-4333 — `_ArcUpdateArgs.expected_version: int` is MANDATORY ⇒ confirms the REST-weaker-than-MCP asymmetry. · services/composition-service/app/engine/arc_apply.py:497 — third caller, `expected_version=None` by design ⇒ template-apply also strands `version`, proving the fix must be in the REPO not just the route. · FIX PATTERN (copy it): services/knowledge-service/app/routers/public/entities.py:1054-1063 — strict If-Match → `HTTP_428_PRECONDITION_REQUIRED`, 412 returns current+ETag. · services/composition-service/app/routers/arc.py:79-85 — `_parse_if_match` already handles composition's bare-int header. · frontend/src/features/composition/api.ts:237 — existing FE sends If-Match only when `version !== undefined` ⇒ the reason the scope fence excludes outline/works/canon. · services/composition-service/tests/unit/test_arc_hub_routes.py — no `/arcs/` PATCH test exists ⇒ zero red-test cost.

### Q-30-BE-M1-MOTIF-UNIQUE-INDEX
BUILD THE MIGRATION, DO NOT BUILD AN ON CONFLICT. The candidate answer's second half ("matching ON CONFLICT predicate") is a phantom — there is no ON CONFLICT on motif_application anywhere in the repo, and none is to be added.

(a) DDL — append to `_MOTIF_SCHEMA_SQL` in `services/composition-service/app/db/migrate.py`, immediately before the closing `"""` at :1622 (i.e. after the `idx_outline_node_written` block at :1620-1621), EXACTLY:
    CREATE UNIQUE INDEX IF NOT EXISTS uq_motif_application_node
      ON motif_application(outline_node_id) WHERE outline_node_id IS NOT NULL;
Nothing else. No `CONCURRENTLY` (this runs inside run_migrations at boot, :1729; the table is 28 rows). No dedupe/backfill DML — the probe is clean (below), so the index build is non-destructive and the "STOP and re-plan" branch of spec 33 BE-M1(a) is CLOSED, not taken.

(b) ⚠ TRAP — DO NOT write `AND NOT is_archived` into the predicate. `motif_application` HAS NO `is_archived` COLUMN (DDL migrate.py:869-880; the only later ALTER, :1248, adds `structure_node_id` only). The repo memory "partial UNIQUE must exempt soft-delete tombstones" DOES NOT APPLY to this table: soft-delete lives on `outline_node`, and superseded bindings here are HARD-deleted (`delete_for_nodes`, motif_application.py:165-178) — there are no tombstones to exempt. Adding that clause raises `column "is_archived" does not exist`, and since run_migrations gates the entire boot (:1729), it BRICKS composition-service startup.

(c) ⚠ TRAP — DO NOT convert `insert_many` to an upsert. All 5 writers are already DELETE-then-INSERT and are correct: arc_apply.py:438→485, motif_select.py:470→491 and :526, plan.py:843→844, plan.py:971 (plan.py:774 and :1377 insert onto freshly-created scene ids under a `not created["replay"]` guard). Keep them. Record this note in the migration comment: IF a future writer ever needs an upsert, the partial index forces the arbiter to repeat the predicate — `ON CONFLICT (outline_node_id) WHERE outline_node_id IS NOT NULL DO UPDATE …` — a bare `ON CONFLICT (outline_node_id)` will NOT infer a partial index and will raise "no unique or exclusion constraint matching the ON CONFLICT specification". That is the only sense in which the ON CONFLICT rule bites here, and it bites nothing in this wave.

(d) The rest of BE-M1 is unchanged from its spec-33:440 contract and is NOT re-opened: add `MotifApplicationRepo.current_for_nodes(project_id, node_ids) -> dict[UUID, MotifApplication]` (`DISTINCT ON (outline_node_id) … ORDER BY outline_node_id, created_at DESC`); delete the router-private `ConformanceTraceReader.apps_by_nodes` (conformance.py:95-113) and repoint conformance.py:412; repoint plan.py:1034 (`bound[0]`) and plan.py:1193 (the dict-collapse) to it; add `DISTINCT ON (COALESCE(outline_node_id, structure_node_id))` to `_MOTIF_CHIPS_SQL` (plan_overlay.py:112-123) as hardening; rename `by_nodes` → `history_by_nodes` (sole surviving caller arc_apply.py:590); scope `set_role_binding`'s UPDATE to the current application id.

(e) TESTS — in `services/composition-service/tests/integration/db/test_motif_migrate.py`: (1) bind a scene, re-bind it, assert EXACTLY one `motif_application` row survives; (2) a raw double-INSERT for the same `outline_node_id` raises `asyncpg.UniqueViolationError`; (3) two rows with `outline_node_id IS NULL` (structure_node-only) both insert fine — proves the partial predicate. Wave DoD includes `/review-impl` per PO policy #2.

VERIFY evidence to paste (already run, spec 33 BE-M1(a)'s mandatory probe, dev `loreweave_composition`):
  SELECT outline_node_id, count(*) FROM motif_application WHERE outline_node_id IS NOT NULL GROUP BY 1 HAVING count(*) > 1;
  → (0 rows)
  SELECT count(*), count(outline_node_id), count(DISTINCT outline_node_id) FROM motif_application;
  → total_rows=28 | with_node=28 | distinct_nodes=28
Zero duplicates ⇒ §1.1's invariant CONFIRMED on live data ⇒ index builds clean; M-BUG-2/M-BUG-3 stay REFUTED (do not budget regression tests for them).

*Evidence:* migrate.py:869-880 (motif_application DDL — NO is_archived column) · migrate.py:1248 (only later ALTER adds structure_node_id) · migrate.py:1622 (end of _MOTIF_SCHEMA_SQL = insertion point) · migrate.py:1729 (run_migrations executes it, gates boot ⇒ a bad predicate bricks startup) · repositories/motif_application.py:63-71 (plain INSERT, no ON CONFLICT) + :165-178 (delete_for_nodes = HARD DELETE, no tombstone) · writers all DELETE-then-INSERT: engine/arc_apply.py:438→485, engine/motif_select.py:470→491 & :526, routers/plan.py:843-844 & :971 · `grep -rn "ON CONFLICT" services/composition-service/app | grep motif_application` → no hits · live probe on loreweave_composition: 0 duplicate outline_node_id, 28 rows / 28 distinct nodes.

### Q-30-REGISTEREFFECT-STRING-BRANCH
MAKE THE BUG UNCOMPILABLE — delete the string branch instead of documenting it. The string branch has ZERO production callers (all 4 live registrations already pass a RegExp), so this is a 3-line change with no migration. Do it as slice X-4.0, BEFORE any of the 6 domain handler files are written.

1) `frontend/src/features/studio/agent/effectRegistry.ts`:
   - line 28: `interface Entry { pattern: RegExp; handler: EffectHandler; }`  (drop `string |`)
   - line 32: narrow the signature to `export function registerEffectHandler(pattern: RegExp, handler: EffectHandler): void` and add a runtime guard as the first statement (TS types are erased; a `as any` or a JS caller must still fail loudly):
       if (!(pattern instanceof RegExp)) throw new Error(`registerEffectHandler: pattern must be a RegExp, got ${typeof pattern}. A string was exact-or-prefix, NOT a pattern — 'composition_(style|voice)_' would have matched NOTHING and shipped a silent no-op handler.`);
       if (pattern.global) throw new Error('registerEffectHandler: pattern must not use the /g flag — RegExp.test() with /g advances lastIndex and alternates true/false across calls.');
   - lines 41-43: collapse `matches()` to `pattern.test(tool)` (or inline it into `matchEffectHandlers`) and delete the `typeof pattern === 'string'` ternary.
   - Update the doc comment on line 31 to: `/** Register a handler for a tool-name RegExp (anchored, e.g. /^composition_arc_/). Strings are REJECTED — see plan 30 §8.0b. */`

2) `frontend/src/features/studio/agent/__tests__/effectRegistry.test.ts` — the only two string callers:
   - line 23 `registerEffectHandler('book_save', s)` → `/^book_save/`; line 33 `registerEffectHandler('book_', a)` → `/^book_/`. Rename the test on line 21 from 'string pattern matches exact + prefix; RegExp matches by test' to 'RegExp patterns match by test'.
   - ADD the regression test that makes this finding permanent:
       it('REJECTS a string pattern — an alternation string would silently match nothing (plan 30 §8.0b)', () => {
         expect(() => registerEffectHandler('composition_(style|voice)_' as unknown as RegExp, vi.fn())).toThrow(/must be a RegExp/);
         expect(matchEffectHandlers('composition_style_set')).toHaveLength(0);
       });
       it('the RegExp form of the same pattern DOES match', () => {
         const h = vi.fn(); registerEffectHandler(/^composition_(style|voice)_/, h);
         expect(matchEffectHandlers('composition_style_set')).toContain(h);
         expect(matchEffectHandlers('composition_voice_apply')).toContain(h);
       });
   - ADD a /g guard test: `expect(() => registerEffectHandler(/^book_/g, vi.fn())).toThrow(/\/g flag/)`.

3) BINDING ON ALL 6 DOMAIN HANDLER FILES (arcEffects, compositionEffects, motifEffects, planEffects, diagnosticsEffects, worldEffects) + the 8b `memory_(remember|forget)` registration in knowledgeEffects: every `registerEffectHandler` call takes an ANCHORED RegExp (`/^…/`). A string literal will now fail `tsc` and throw at registration, so the class is dead — not merely discouraged.

Rationale (note the default so the PO can veto): I chose DELETE over "keep the string branch + a lint note" because a note is self-report, and this repo's own lesson `checklist-is-self-report-enforce-by-tests` says an item is done only when a test asserts its effect. The branch is unused in production, so keeping it buys nothing and costs a silent-no-op bug class across 15 upcoming registrations — exactly the `silent-success-is-a-bug-not-environment` shape. Plan 30 §8.0b's prose note stays, but it is now backed by a throw + a test.

*Evidence:* frontend/src/features/studio/agent/effectRegistry.ts:41-43 — `function matches(pattern: string | RegExp, tool: string) { return typeof pattern === 'string' ? tool === pattern || tool.startsWith(pattern) : pattern.test(tool); }` (string = exact-or-prefix, NOT a pattern; a non-matching registration produces no error — `runEffectHandlers`:49-52 only iterates MATCHING handlers, so a no-op handler is invisible). Signature at effectRegistry.ts:32; Entry type at :28. Zero production string callers: bookEffects.ts:59-62 (`/^book_.*(draft|chapter)/`, `/^composition_.*(prose|draft)/`, `/^composition_(outline_node|scene_link)_/`), glossaryEffects.ts:18+:59 (`GLOSSARY_WRITE_PATTERN = /^glossary_(?!get_|list_|search|deep_research|web_search)/`), knowledgeEffects.ts:16+:51, translationEffects.ts:28 (`/^translation_job_control/`) — all RegExp. The ONLY string callers in the repo are the two test lines __tests__/effectRegistry.test.ts:23 (`'book_save'`) and :33 (`'book_'`). Spec: docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:621-625.

### Q-30-DROP-MINE-FROM-IMPORT
SPLIT THE DECISION — the refutation stands, the "drop" does not.

(A) CONFIRM THE DROP OF THE TOOL, and reject candidate answer #2 ("spec the backend arg first"). Do NOT add `import_source_id` to `_MotifMineArgs`; do NOT call `composition_motif_mine` from the Import & Deconstruct section; do NOT put a "Mine motifs" button there. Spec 34's AT-10 stands as written. There is NO backend arg to spec — not because the capability is missing, but because it already exists elsewhere (B). Adding an import scope to motif_mine would be a duplicate, second writer of imported motifs.

(B) DO NOT DROP THE USER-FACING OUTCOME — it is already SHIPPED under `composition_arc_import_analyze`. `deconstruct_reference` (engine/motif_deconstruct.py:602-630) persists member motifs from the import source via `motif_repo.create(UUID(user_id), args, source="imported", imported_derived=True)` and returns `{"arc_template_id", "motif_ids": [...], "abstraction_check": {"motifs_emitted": N, "scrubbed_fields": ...}, "chunks", "chunks_parsed", "chunks_failed", "websearch_status"}`. So a confirmed deconstruct ALREADY writes N motifs into the user's library — and today no GUI ever tells them. Dropping the leg outright would ship a fresh GG-1 violation (backend capability with no human surface) inside the very plan that enforces GG-1.

BUILDER INSTRUCTION (Wave 4, spec 34's "Import & Deconstruct" section inside `arc-templates`):
1. frontend/src/features/composition/motif/types.ts — add a NEW type next to `MineResult` (types.ts:351-361). Do NOT reuse `MineResult`; its `motif_ids` (types.ts:354) is the MINE worker's result and conflating them is the drift this question is about:
   export type DeconstructResult = { arc_template_id: string; motif_ids?: string[]; abstraction_check?: { motifs_emitted?: number; scrubbed_fields?: number }; chunks?: number; chunks_parsed?: number; chunks_failed?: number; websearch_status?: string; language?: string; use_web?: boolean };
2. The deconstruct RESULT card reads the job result from BE-7c's owner-scoped poll (`GET /v1/composition/motif-jobs/{job_id}`, built in Wave 3 — same route the confirm response names) and renders THREE things: (a) the derived arc template (link to it in `arc-templates`), (b) "Derived N motifs" from `motif_ids.length` / `abstraction_check.motifs_emitted`, each linking into the motif library filtered to `source='imported'`, (c) a partial-deconstruct warning when `chunks_failed > 0` (MED-4: a partial deconstruct is visible, not silent) plus `websearch_status` when `use_web` was set.
3. Test (vitest, features/composition/motif/__tests__/): given a DeconstructResult with 3 motif_ids and chunks_failed=1, the result card shows the motif count, renders a link per motif id, and shows the partial warning.

Net: one row DROPPED (the motif_mine arg), one row ADDED (render the deconstruct's motifs). Wave 4 sizing is unchanged (M) — this is a render addition to a card the section already needs, no new route and no new backend arg.

DEFAULT NOTED FOR PO VETO: I render the derived motifs read-only (count + deep links into the existing motif library) rather than building a review/approve queue for them. The motifs land as ordinary library rows the user can already edit/delete through the ported motif GUI (Wave 3), so a bespoke approval step would be redundant surface. Veto if you want imported motifs quarantined behind an explicit accept step.

*Evidence:* services/composition-service/app/mcp/server.py:2958-2966 — `class _MotifMineArgs(ForbidExtra): scope: Literal["book","corpus"]` … no `import_source_id` field (refutation CONFIRMED). services/composition-service/app/engine/motif_deconstruct.py:602-630 — `# PERSIST — member motifs (source='imported', imported_derived=True) then the arc.` → `motif: Motif = await motif_repo.create(UUID(user_id), args, source="imported", imported_derived=True)`; `motif_ids.append(str(motif.id))`; `return {"arc_template_id": str(arc.id), "motif_ids": motif_ids, "abstraction_check": {..., "motifs_emitted": len(motif_ids)}, "chunks_failed": chunks_failed, ...}` (the capability EXISTS, under composition_arc_import_analyze). services/composition-service/app/engine/motif_deconstruct.py:23-26 (module docstring) — the deconstruct yields "a proposed arc_template (source='imported', status='draft') + member motifs (source='imported', imported_derived=true)". frontend/src/features/composition/motif/types.ts:351-361 — `MineResult.motif_ids` is the MINE worker's result; there is NO FE type for the deconstruct result. docs/specs/2026-07-01-writing-studio/34_arc_templates_and_deconstruct.md:121 (AT-10) — already records the refutation and even states "The member motifs of a deconstructed work are written by the analyze_reference worker, not by mining" — but spec 34 never specs RENDERING them (grep for motif_ids in spec 34 returns only that one line).

### Q-30-BE-A3-ARC-UNASSIGN
CONFIRMED as a real hole, and it is BUILDABLE (unbuilt work, not a blocker): `?unassigned=true` is a reader with NO writer. Build a **distinct UNASSIGN verb at all 3 layers**, mirroring assign-chapters — do NOT take spec 32 §5's "make `structure_node_id` nullable on assign" variant (see rationale). Nothing in plan-30 §0 (PO-1..4) touches this, so this is a free implementation call. Ship in Wave 2, slice M4 (spec 32 §M4).

WHY the separate verb beats the nullable-arg variant (the default I'm picking; PO may veto):
- `composition_arc_assign_chapters`'s name, description ("Attach CHAPTER-kind outline nodes…"), synonyms ("attach chapters to arc", "add chapters to arc") and response key `{"assigned": n}` ALL say *attach* (server.py:4514-4543). A null `structure_node_id` meaning "detach" is a semantic overload no LLM will discover, and the response field would lie. That violates mcp-tool-io "one name for one concept" + no-silent-no-op.
- It is the same cost (one repo method, one route, one tool) with zero ambiguity, and it keeps the EXISTS-in-book guard on the assign branch intact instead of forking it on a nullable arg.

EXACT CHANGES (builder follows without further thought):

1) REPO — `services/composition-service/app/db/repositories/structure.py`, new method directly below `assign_chapters` (which ends at :564):
```python
async def unassign_chapters(
    self, book_id: UUID, chapter_node_ids: list[UUID],
    *, from_structure_node_id: UUID | None = None,
) -> list[tuple[UUID, UUID]]:
    """Detach CHAPTER-kind outline nodes from their arc (structure_node_id -> NULL):
    the ONLY writer for the pool `list_unassigned_chapters` already reads
    (outline.py:853). Book-scoped. `from_structure_node_id` (optional) restricts the
    detach to chapters CURRENTLY bound to that arc — a stale client cannot clobber a
    chapter that was re-bound elsewhere. Returns (chapter_node_id, previous_arc_id)
    pairs so callers can offer a TRUE undo (re-assign)."""
    if not chapter_node_ids:
        return []
    async with self._pool.acquire() as c:
        rows = await c.fetch(
            """
            WITH prev AS (
              SELECT id, structure_node_id FROM outline_node
              WHERE book_id = $1 AND id = ANY($2)
                AND kind = 'chapter' AND NOT is_archived
                AND structure_node_id IS NOT NULL
                AND ($3::uuid IS NULL OR structure_node_id = $3)
              FOR UPDATE
            ), upd AS (
              UPDATE outline_node o SET structure_node_id = NULL, updated_at = now()
              FROM prev p WHERE o.id = p.id
              RETURNING o.id
            )
            SELECT p.id, p.structure_node_id FROM prev p
            """,
            book_id, chapter_node_ids, from_structure_node_id,
        )
    return [(r["id"], r["structure_node_id"]) for r in rows]
```
Note deliberately does NOT check the ARC's `is_archived` — spec 32 §4 says an archived arc's chapters are stranded (archive() flips structure_node.is_archived only) and BE-A3 is their ONLY escape hatch. This query frees them.

2) REST — `services/composition-service/app/routers/arc.py`: add model beside `ArcAssignChapters` (:363):
```python
class ArcUnassignChapters(BaseModel):
    chapter_node_ids: list[UUID]
    from_structure_node_id: UUID | None = None
```
and route directly after `assign_arc_chapters` (:560-572), copying its gate VERBATIM:
```python
@router.post("/books/{book_id}/arcs/unassign-chapters", status_code=200)
async def unassign_arc_chapters(
    book_id: UUID, body: ArcUnassignChapters,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Detach chapter-kind outline nodes from their arc (back to the unassigned pool). EDIT."""
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    pairs = await _structures().unassign_chapters(
        book_id, body.chapter_node_ids, from_structure_node_id=body.from_structure_node_id,
    )
    return {"unassigned": len(pairs),
            "previous": [{"chapter_node_id": str(cid), "structure_node_id": str(aid)}
                         for cid, aid in pairs]}
```

3) MCP — `services/composition-service/app/mcp/server.py`, directly after `composition_arc_assign_chapters` (ends :4543). Tier **A**, `require_meta("A", "book", synonyms=["unassign chapters", "remove chapter from arc", "detach chapters", "return chapters to unassigned", "unfile chapters"], tool_name="composition_arc_unassign_chapters")`. Args `class _ArcUnassignChaptersArgs(ForbidExtra): book_id: str; chapter_node_ids: list[str]; from_structure_node_id: str | None = None`. Body: `_gate(tc, bid, GrantLevel.EDIT)` → repo call → return `{"unassigned": len(pairs), "previous": [...], "_meta": {"undo_hint": {...}}}` where `undo_hint` is `{"tool": "composition_arc_assign_chapters", "args": {"book_id":…, "structure_node_id": <the one prev arc>, "chapter_node_ids": [...]}}` ONLY when every pair shares one previous arc, else `None` (honest — no fake inverse, same discipline as move at :4502-4504).

4) FE API — `frontend/src/features/plan-hub/api.ts`, next to `assignChapters` (:241): `export function unassignChapters(bookId, chapterNodeIds, token, fromStructureNodeId?)` → POST `${COMP}/books/${bookId}/arcs/unassign-chapters`, body `{chapter_node_ids, from_structure_node_id}`, returns `{unassigned: number; previous: {...}[]}`. Consumers (arc-inspector "remove" row-action per 32 §3.3, Hub drag-to-unassigned) land in the same M4 slice; the mutation must invalidate BOTH `['plan-hub','arcs',bookId]` and the `?unassigned=true` children query.

TESTS (each is the DoD, no slice is done without them):
- `tests/integration/db/test_structure_repo.py` (mirror `test_assign_chapters_book_scoped_both_sides_by_effect`, :381): assign 2 chapters to arc A → unassign one → it appears in `OutlineRepo.list_unassigned_chapters(book)` and the other does not; a chapter of book B is untouched when called with book A; `from_structure_node_id=arcB` on a chapter bound to arcA returns `[]` and does NOT clear it; returned pair carries arcA's id.
- `tests/unit/test_arc_hub_routes.py` (mirror :79-96): view-grantee → 403 and `repo.unassign_chapters.assert_not_called()`; non-grantee → 404 + never writes.
- `tests/unit/test_mcp_arc_structure.py`: tool returns `{"unassigned": 2}` and an undo_hint naming `composition_arc_assign_chapters` with the previous arc; mixed-arc batch ⇒ `undo_hint is None`.
- **Registration (will red otherwise):** add `"composition_arc_unassign_chapters"` to the expected tool-name set in `services/composition-service/tests/unit/test_mcp_server.py:92` AND to its `TIER_A` set. Add the entry to `contracts/tool-liveness.json` if the suite asserts coverage.
- FE: `frontend/src/features/plan-hub/__tests__/api.test.ts` — asserts URL + snake_case body.
Verify: `python -m pytest tests -q -n auto --dist loadgroup` in `services/composition-service` + the FE vitest file. `/review-impl` at wave close per the run policy.

*Evidence:* services/composition-service/app/db/repositories/structure.py:540-564 (`assign_chapters` = `SET structure_node_id = $1` + EXISTS guard — no NULL path anywhere) · app/routers/arc.py:363-365 (`ArcAssignChapters.structure_node_id: UUID`, non-null) + :560-572 (the only assign route, `_gate_book(..., EDIT)`) · app/mcp/server.py:4508-4543 (`_ArcAssignChaptersArgs` non-null; description/synonyms are all "attach"; returns `{"assigned": n}`) · app/db/repositories/outline.py:853 `list_unassigned_chapters` = `structure_node_id IS NULL` — a READER with no writer · app/routers/outline.py:363-364 (`?unassigned=true` axis) · frontend/src/features/plan-hub/api.ts:35 + :241 (Hub already reads the pool and calls assign) · spec 32 §5 BE-A3 (docs/specs/2026-07-01-writing-studio/32_arc_inspector.md:349) and §4 archived-arc row (:256, "BE-A3 is their only escape hatch") · tests/unit/test_mcp_server.py:92 (exact tool-name set — must be extended) · tests/unit/test_arc_hub_routes.py:79-96 (the grant-gate test pattern to mirror)

### Q-30-EFFECT-HANDLER-DOUBLE-FIRE
RATIFY the §8.0b table verbatim — ONE FILE PER DOMAIN — and make it MACHINE-CHECKED so the rule cannot be violated silently by a later wave.

(1) OWNERSHIP (unchanged from §8.0b:614-619; builders follow it as written):
- `handlers/arcEffects.ts` — Wave 2 (spec 32) CREATES it with ONE broad `registerEffectHandler(/^composition_arc_/, arcEffect)`. Wave 4 (spec 34) EXTENDS the handler BODY only (adds `['composition','arc-templates']` to the invalidation set). Wave 4 MUST NOT call `registerEffectHandler` again — `/^composition_arc_/` already covers `composition_arc_apply` and `composition_arc_extract_template`.
- `handlers/compositionEffects.ts` — Wave 1 (spec 31) CREATES it (`/^composition_canon_rule_/`, `/^composition_record_correction$/`). Wave 6 (spec 36) EXTENDS THE SAME FILE (`/^composition_(style|voice)_/` as a RegExp, never a string — effectRegistry.ts:41's string branch is `===`-or-`startsWith`, not a pattern).
- `motifEffects.ts` (33) · `planEffects.ts` (35) · `diagnosticsEffects.ts` (37) · `worldEffects.ts` (38) — one file each, patterns disjoint from every other file's.
- `bookEffects.ts` KEEPS its 3 existing registrations and gains NOTHING new. Verified by grep: no `composition_arc_*` / `composition_canon_*` / `composition_style|voice_*` / `plan_*` / `world_map_*` handler exists anywhere today, so every new domain file is a clean CREATE — there is no code to move, and none of the new families collide with `bookEffects.ts:59-62`'s regexes (none contains `prose`, `draft`, `outline_node`, or `scene_link`).

(2) THE MACHINE CHECK (new — this is the part the spec text was missing; the rule currently lives only as prose in 4 files, so nothing reds if wave 4 or 6 registers a second pattern at 3am).
Wave 1 CREATES `frontend/src/features/studio/agent/handlers/__tests__/handlerOwnership.test.ts`:
- `beforeEach`: `clearEffectHandlers()`, then reset each handler module's module-level `registered` guard via `vi.resetModules()` + dynamic import, then call EVERY `register*EffectHandlers()` that exists at that wave (start: book/glossary/knowledge/translation/composition).
- Body: a `TOOL_OWNERSHIP` fixture table mapping each registered write-tool name -> its owning handler file, and assert for every row `expect(matchEffectHandlers(name)).toHaveLength(1)` — EXACTLY ONE. A double-registration across two files makes this go to 2 and REDS.
- Also assert `toHaveLength(0)` for the representative READ tools each domain excludes (`glossary_get_*`, `kg_graph_query`, `world_map_get`, `world_map_list`, `translation_job_status`) so an over-broad new pattern that starts thrashing the cache also reds.
- EVERY subsequent wave (2,3,4,5,6,7,8) adds its new tool names to `TOOL_OWNERSHIP` as a literal Definition-of-Done step. Waves 4 and 6 add ONLY rows (`composition_arc_apply`, `composition_arc_extract_template`, `composition_style_*`, `composition_voice_*`) — if a builder also adds a `registerEffectHandler` call, the length-1 assertion fails on the arc/composition rows and the wave cannot close.

Do NOT change `matchEffectHandlers`/`runEffectHandlers` to first-match-wins: `__tests__/effectRegistry.test.ts:31` asserts awaits-all as intended behavior, and `bookEffects.ts` legitimately registers 3 patterns against 2 handlers. The fix is ownership + a test, not a registry rewrite.

DEFAULT NOTED FOR PO VETO: I chose "exactly 1 handler per tool name" rather than "<=1" so the test doubles as a Lane-B COVERAGE gate (a wave that ships a panel but forgets its handler — the X-4 bug class — also reds).

*Evidence:* frontend/src/features/studio/agent/effectRegistry.ts:45-53 — `matchEffectHandlers` = `registry.filter((e) => matches(e.pattern, tool)).map(...)` (returns EVERY match) and `runEffectHandlers` = `for (const handler of matchEffectHandlers(ctx.tool)) { await handler(ctx); }` (awaits ALL) => overlapping patterns DOUBLE-FIRE, confirmed; also effectRegistry.ts:41 `typeof pattern === 'string' ? tool === pattern || tool.startsWith(pattern) : pattern.test(tool)` (string branch is not a pattern match). frontend/src/features/studio/agent/handlers/bookEffects.ts:59-62 — the only 3 registrations today. `grep -rn "composition_arc\|composition_canon\|composition_style\|composition_voice\|plan_run_pass\|world_map_" frontend/src/features/studio/agent/` => NO MATCHES (every new domain file is a clean create; nothing to move out of bookEffects.ts). Spec: docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:607-624 (§8.0b table) + 32_arc_inspector.md:378, 34_arc_templates_and_deconstruct.md:228, 31_quality_completion.md:564, 36_editor_craft_ports.md:470 (the 🔴 one-home annotations already in the per-wave specs). Consistent with §0 PO-1..4 (no sealed decision touches Lane-B handler layout).

### Q-30-BE-M3-MOTIF-LINK-REST
BUILD THE 3 REST ROUTES (candidate answer confirmed). Not the bridge: `services/api-gateway-bff/src/tools/tools.controller.ts:18-30` states its own contract — "NOTHING here writes or deletes" — and `motif_link_create`/`_delete` are writes; adding them to `FE_BRIDGE_TOOL_ALLOWLIST` would also make Wave 3 cross-service (mandatory live-smoke) for zero benefit. Wave 3 stays single-service (composition only).

WHERE: append to the EXISTING `services/composition-service/app/routers/motif.py` (router already `APIRouter(prefix="/v1/composition")` at :53, already mounted at `main.py:226`). No new router, no new repo — there is NO `MotifLinkRepo`; the methods live on `MotifRepo`. All three routes are thin wrappers (~40 LOC total) over already-built, already-tested repo methods.

ROUTE 1 — `GET /v1/composition/motifs/{motif_id}/links`
  Query: `direction: str = "both"` (validate in {out,in,both} else 400), `kinds: list[str] | None = Query(None)` (subset of composed_of|precedes|variant_of), `book_id: UUID | None`, `limit: int = 200`.
  If `book_id` → `await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)` (the helper at motif.py:56).
  Call `repo.list_links(user_id, motif_id, direction=..., kinds=..., limit=..., book_id=...)`.
  Return `200 {"motif_id": str(motif_id), "links": [...], "count": n}` where each link = `{id, kind, ord, direction, neighbor:{id, code, name}}`.
  ⚠ SETTLES A SPEC CONTRADICTION: spec 33's error column says GET → 404 for a foreign motif, but `list_links` returns `[]` for an invisible anchor BY DESIGN (motif_repo.py:227-235: "IDOR-safe — empty is indistinguishable from 'no edges', no existence oracle"). A 404 would require an extra visibility probe and buys nothing. DECISION: GET returns `200 {"links": [], "count": 0}` for a missing/invisible anchor — identical to the MCP tool `composition_motif_link_list` (server.py:2613). The 404 in spec 33's error column applies to the two WRITE routes only. (PO may veto; both options are equally non-oracular.)

ROUTE 2 — `POST /v1/composition/motifs/{motif_id}/links` → 201
  Body model `MotifLinkCreate(_ForbidExtra)`: `to_motif_id: UUID`, `kind: Literal["composed_of","precedes","variant_of"]` (CLOSED SET — enum/Literal, never a free string), `ord: int | None = None`, `book_id: UUID | None = None`.
  If `book_id` → `_gate_book(..., GrantLevel.EDIT)` (mirrors the MCP gate at server.py:2665-2668 — the HTTP route must be NO softer than the MCP path).
  Call `repo.create_link(user_id, motif_id, body.to_motif_id, body.kind, ord=body.ord, book_id=body.book_id)`.
  Error map (mirror `composition_motif_link_create`, server.py:2670-2683):
    • `LookupError` → 404 `_NOT_FOUND` (motif.py:70 — the uniform H13 dict; endpoint not owned / not book-shared)
    • `asyncpg.UniqueViolationError` → 409 `{"code":"MOTIF_LINK_EXISTS","message":"that edge already exists"}`
    • `asyncpg.CheckViolationError` → 409 `{"code":"MOTIF_LINK_INVALID","message": str(e)}` — RELAY the trigger's reason, do NOT flatten to 500.
  VERIFIED (do not "fix" this): the `motif_link_guard` trigger raises `USING ERRCODE = 'check_violation'` (migrate.py:836-838 cross-tier, :850-851 cycle), so asyncpg surfaces `CheckViolationError` — the SAME class as the `motif_link_distinct` self-link CHECK. ONE except arm catches self-link + cycle + cross-tier. (It is NOT `RaiseError`/P0001, because of the explicit ERRCODE.)
  Return `link.model_dump(mode="json")`.

ROUTE 3 — `DELETE /v1/composition/motif-links/{link_id}` → 204
  Path is NOT nested under the motif (matches the MCP arg shape: link_id only). Query `book_id: UUID | None`; if set → `_gate_book(..., GrantLevel.EDIT)`.
  `deleted = await repo.delete_link(user_id, link_id, book_id=book_id)`; `if not deleted: raise HTTPException(404, detail=_NOT_FOUND)`. Else 204, no body.

TESTS: extend `services/composition-service/tests/unit/test_motif_router.py` (the existing motif REST-route test home). Minimum 6: (1) GET both/out/in returns neighbor stubs; (2) GET on a foreign motif → 200 with `links: []` (no existence oracle); (3) POST between two owned motifs → 201; (4) POST that closes a cycle → 409 with the trigger's reason IN the body (assert the message is not flattened); (5) POST with `book_id` and no EDIT grant → 403, with VIEW-only → 403, unknown book → 404; (6) DELETE of a foreign edge → 404, of an owned edge → 204.

FE (Wave 3a consumer, spec 33 §294-305): add `listLinks/createLink/deleteLink` to `frontend/src/features/composition/motif/api.ts` via `apiJson` (NOT `mcpExecute`), and render the graph as a COLLAPSED LIST SECTION inside the motif detail drawer — grouped by kind (composed_of / precedes / variant_of), each row a neighbor chip that re-anchors the section on click. NOT a canvas (OQ-2 is deliberate; D-MOTIF-GRAPH-CANVAS stays deferred). The 409 renders inline on the add-link form, not as a toast.

*Evidence:* services/composition-service/app/db/repositories/motif_repo.py:215 (`list_links`), :275 (`create_link`), :320 (`delete_link`) — all built + tenant-gated + tested; no MotifLinkRepo exists. services/composition-service/app/routers/motif.py:53 (`APIRouter(prefix="/v1/composition")`) + :151-445 — motifs CRUD/catalog/adopt only, ZERO link routes (`grep -n "router\.\(get\|post\|delete\)" routers/motif.py`). services/composition-service/app/mcp/server.py:2613/:2659/:2703 — the 3 agent-only tools whose gates the routes must mirror. services/api-gateway-bff/src/tools/tools.controller.ts:18-30 — allowlist contract "NOTHING here writes or deletes" (rules the bridge out). services/composition-service/app/db/migrate.py:836-838 + :850-851 — trigger raises `USING ERRCODE = 'check_violation'` ⇒ asyncpg.CheckViolationError for cross-tier AND cycle. Spec: docs/specs/2026-07-01-writing-studio/33_motif_studio.md:442 (BE-M3 MUST-BUILD) + :294-305 (graph = list, not canvas); plan 30 line 246 (G-MOTIF-LIBRARY) — and §0 PO-1..4 say nothing about motif links, so nothing here contradicts a sealed decision.

### Q-30-PANEL-REGISTRATION-9-STEPS
ADOPT §8's 9-step checklist VERBATIM as the per-panel Definition of Done — it is correct against HEAD and is not re-litigable. But two of its steps are currently PROSE, NOT TESTS, so a builder can follow the checklist, get a green suite, and still ship a broken panel. Therefore: **X-2 and X-3 land as machine guards in `panelCatalogContract.test.ts` BEFORE Wave 1's first panel row is added — they are a hard gate on Wave 1, not a wave-1 deliverable.**

WHAT IS ALREADY ENFORCED (do not re-add):
- `category` present ⇒ reds (panelCatalogContract.test.ts:38-42, "#18 B6").
- enum == contract enum == openable, sorted equality (same file, 3 tests).
- `CLOSED_SET_ARGS` ⇒ must carry an `enum` (chat-service tests/test_frontend_tools_contract.py).

WHAT IS NOT ENFORCED — BUILD IT (3 edits, ~20 LOC, all in the FE):

(1) X-2 — put `quality` in CATEGORY_ORDER. Edit `frontend/src/features/studio/palette/useStudioCommands.ts:20-22`: the array lists 9 of the 10 members of `StudioPanelCategory` (catalog.ts:81-91). Insert `'quality'` AFTER `'knowledge'` and BEFORE `'translation'`. This is a live shipped bug, not just batch prep: `CATEGORY_ORDER.indexOf('quality')` returns `-1`, and `useStudioCommands.ts:55-56` sorts by that index, so today's shipped `quality` hub already sorts ABOVE `editor` in the Command Palette. Wave 1 adds 3 more `quality` panels and Wave 3c adds a 4th, which multiplies the misorder.

(2) X-2 guard — add to `panelCatalogContract.test.ts` (import CATEGORY_ORDER from '../../palette/useStudioCommands'):
  it('every panel category is a member of CATEGORY_ORDER (unlisted sorts FIRST via indexOf -1)', () => {
    const unlisted = OPENABLE_STUDIO_PANELS.filter(p => p.category && !CATEGORY_ORDER.includes(p.category)).map(p => p.id);
    expect(unlisted).toEqual([]);
  });
  Also assert the two sets are the SAME SIZE, so a future 11th category added to the union type but not to CATEGORY_ORDER reds:
    expect([...CATEGORY_ORDER].sort()).toEqual([...new Set(OPENABLE_STUDIO_PANELS.map(p => p.category))].sort()) — NO: use a superset assertion only (some categories may legitimately have zero panels). Assert: every `StudioPanelCategory` literal is in CATEGORY_ORDER, by exporting a `const ALL_CATEGORIES: StudioPanelCategory[]` from catalog.ts next to the type and asserting `expect([...ALL_CATEGORIES].sort()).toEqual([...CATEGORY_ORDER].sort())`. This is the assertion that catches the drift AT THE TYPE, which is where it was actually introduced.

(3) X-3 — make `guideBodyKey` mandatory. Two parts, both required (the type alone is not a guard — the catalog rows are object literals and TS will red at build, but the batch's builders run vitest, not tsc, in the inner loop):
  (a) `catalog.ts:105` — change `guideBodyKey?: string;` to `guideBodyKey: string;` and delete the "falls back to descKey when absent" comment. Backfill: every one of the 57 openable rows ALREADY has one (verified — catalog.ts:114+), so this is a type tightening with zero row edits. Keep it optional for `hiddenFromPalette` rows if any lack it (json-editor precedent) by making the field required only on the openable path, or just fill the hidden rows too.
  (b) add to `panelCatalogContract.test.ts`:
    it('every palette-openable panel has a guideBodyKey (#19 User Guide body)', () => {
      const missing = OPENABLE_STUDIO_PANELS.filter(p => !p.guideBodyKey).map(p => p.id);
      expect(missing).toEqual([]);
    });

THE DoD SENTENCE EVERY WAVE COPIES (this is the answer a builder acts on):
A panel is DONE when: steps 1-9 of §8 are done; the 4 named suites are green (chat-service test_frontend_tools_contract.py + test_frontend_tools.py; vitest panelCatalogContract.test.ts + UserGuidePanel.test.tsx + useStudioCommands.test.ts + frontendToolContract.test.ts); the DoD asserts the **delta + the three-way equality** (`N_before + k == N_after` across openable == py enum == contract enum) and **NEVER a literal count** — a literal sends the next builder hunting a phantom regression when a wave is reordered; `contracts/frontend-tools.contract.json` is REGENERATED (`cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py`) and committed in the SAME commit as the catalog + frontend_tools.py edits; and a **live browser smoke** shows `ui_open_studio_panel {panel_id:"<id>"}` actually mounting the dock tab (precedent: `studio-compose.spec.ts`, `studio-palette.spec.ts`). **A green unit suite does NOT prove the loop closed** — this repo already shipped that bug (`panel_id` with no enum → gemma sent `panel:"editor"` → silent no-op → hallucinated success; memory `agent-gui-loop-needs-live-browser-smoke-not-raw-stream`).

DEFAULT I AM PICKING (veto-able): X-2 + X-3 land as ONE small pre-Wave-1 commit ("X-2/X-3: make the panel-registration checklist machine-enforced") rather than being folded into Wave 1's first panel. Rationale: they are the guards that make every subsequent wave's "green suite" mean something, and X-2 fixes a bug that is ALREADY MISORDERING the shipped palette — folding them into a panel commit hides a live fix inside a feature diff.

*Evidence:* frontend/src/features/studio/panels/catalog.ts:102 (`category?`) + :105 (`guideBodyKey?`) — both OPTIONAL in `StudioPanelDef`, contradicting §8's "MANDATORY". · frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts:38-42 — the ONLY category assertion is presence, not CATEGORY_ORDER membership; there is NO guideBodyKey assertion. · frontend/src/features/studio/palette/useStudioCommands.ts:20-22 — CATEGORY_ORDER lists 9 categories; catalog.ts:81-91 defines 10 (`quality` missing) and useStudioCommands.ts:55-56 sorts by `indexOf`, so `-1` sorts `quality` FIRST — the shipped quality hub already outranks `editor`. · services/chat-service/app/services/frontend_tools.py:402 — the `panel_id` enum (57 ids); gloss prose at :403-481.

### Q-30-ENUM-COUNT-BASELINE
CONFIRM the spec's candidate answer — it is already the codebase's own convention, learned the hard way. RULE (binding for all 8 waves): **no DoD, test, or spec may assert a literal panel count.** Concretely:

1. **Never add a count assertion.** The three-way guard is already count-free and self-updating: `panelCatalogContract.test.ts:32-35` asserts SORTED SET EQUALITY (`enumIds.sort() === OPENABLE_STUDIO_PANELS.map(p=>p.id).sort()`) plus every advertised id is buildable in `STUDIO_PANEL_COMPONENTS`; `test_frontend_tools.py:168-171` asserts only non-empty + no-duplicates. Nothing anywhere hardcodes 57. A builder who "fixes" a wave by writing `expect(enum).toHaveLength(61)` is RE-INTRODUCING the exact anti-pattern the repo deliberately deleted (see evidence).

2. **Each wave's DoD asserts the DELTA, measured — not a literal.** The DoD step is literally:
   - Before the wave, MEASURE the baseline (do not copy it from the spec):
     `N_before=$(python -c "import json;print(len(json.load(open('contracts/frontend-tools.contract.json'))['ui_open_studio_panel']['args']['panel_id']['enum']))")`
   - Add the wave's k panels to ALL THREE places: the `enum` list in `services/chat-service/app/services/frontend_tools.py` (UI_OPEN_STUDIO_PANEL_TOOL, ~line 400) + its description string; a row in `frontend/src/features/studio/panels/catalog.ts` STUDIO_PANELS (with a `category`, or the 4th test reds) + its component in `STUDIO_PANEL_COMPONENTS`; then REGENERATE the contract with `WRITE_FRONTEND_CONTRACT=1 pytest services/chat-service/tests/test_frontend_tools_contract.py` (never hand-edit the JSON).
   - Assert `N_after == N_before + k` AND the three-way set-equality suite green (`npx vitest run panelCatalogContract` + the chat-service contract test). That is the whole DoD; the k for each wave is the only number a spec may state.

3. **The §8 ladder table (57→61→62→64→65→66→69→69→71) stays as a PLANNING aid ONLY**, already correctly annotated "not a test assertion." Fix the six specs (31, 32, 33, 34, 35, 38) by replacing their literal target counts with the delta form + their k; spec 36 already has it right and is the template to copy.

4. **Set `hiddenFromPalette` on none of the 14** — plan 30 §8.0 check 5 already establishes all 14 are bare-id openable, so all 14 enter the enum, the palette, and the User Guide, keeping the three sets identical by construction.

End state is 57 + 14 = 71, but NO wave may encode 71 (or any intermediate) as an assertion — if a wave is re-ordered, dropped, or split, every literal below it becomes a false red. The delta form survives re-ordering; a literal does not.

*Evidence:* services/chat-service/tests/test_frontend_tools.py:153-162 — the tombstone comment that settles this: "NOTE: this used to also assert `panel_id`'s enum against a hand-copied literal list — that list drifted stale at least twice (missing context-inspector, sharing, book-settings, translation, enrichment-*, user-guide, agent-mode) because nothing forced it to stay in sync with the real enum. The actual anti-drift mechanism for that is test_frontend_tools_contract.py's committed contracts/frontend-tools.contract.json (regenerated via WRITE_FRONTEND_CONTRACT=1), which the FE guard also reads — duplicating the list here only added a second, unmaintained copy that could fail for reasons unrelated to whatever change actually broke the contract."
Corroborating: frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts:32-35 asserts sorted SET equality, not a count; frontend/src/features/studio/panels/catalog.ts:279 `OPENABLE_STUDIO_PANELS = STUDIO_PANELS.filter((p) => !p.hiddenFromPalette)`; services/chat-service/app/services/frontend_tools.py:400 (panel_id enum). Measured at HEAD 9262ed53e: py enum 57 == contract enum 57 == openable 57 (68 catalog rows − 11 hidden), zero drift.

### Q-30-G-MOTIF-BINDING-UNDO-SCOPE
CONFIRMED BY CODE — take the candidate answer (render the undo affordance conditionally on node kind), and wire each kind to its own real inverse. The concern is correct and the trap is real: a scene bind's return dict LITERALLY HAS NO `undo_token` KEY (plan.py:845-852), so a token-undo button on a scene would post `undo_token: undefined` and silently no-op.

BUILDER INSTRUCTION (Wave 3b, binding lens):

1. FE TYPE — in the motif types, declare the bind response as a discriminated shape: chapter → `{chapter_node_id, archived_scene_ids, new_scene_ids, orphaned_thread_ids, new_motif_id, undo_token: {chapter_node_id, archived_scene_ids, new_scene_ids}}`; scene → `{node_id, motif_id, motif_name, bound, unresolved_roles, warning}` (no `undo_token`). Type it `undo_token?: UndoToken | null` — never non-optional.

2. FE HOOK — `frontend/src/features/composition/motif/hooks/useMotifBinding.ts`. Its `swap` mutation (line 31-37) TODAY DISCARDS THE RESPONSE, so the token is thrown away. Change `swap`'s `onSuccess` to capture `res.undo_token` into hook state keyed by nodeId (`const [undoToken, setUndoToken] = useState<UndoToken|null>(null)`), and add an `undoBind` mutation: `apiJson(`${BASE}/works/${projectId}/outline/${nodeId}/motif`, {method:'PATCH', body: JSON.stringify({undo_token: undoToken}), token})`, `onSuccess: () => { invalidatePreview(); setUndoToken(null); }`. Do NOT call the MCP tool from the FE — the HTTP route IS the FE seam and it accepts `undo_token` in the PATCH body (plan.py:881-886 → `undo_motif_swap`, the exact idempotent inverse, motif_select.py:509-532).

3. FE RENDER GATE — render the "Undo bind" control ONLY when `node.kind === 'chapter' && undoToken != null`. Both conjuncts required; a truthiness check on the token alone is the trap, because the scene response's missing key is `undefined`, not `null`.

4. SCENE AFFORDANCE — on a scene node render "Unbind" (NOT "Undo"), wired to the EXISTING `clearMotif` mutation (useMotifBinding.ts:49-53) → `DELETE …/outline/{nodeId}/motif` → the scene branch at plan.py:968-972 deletes the ledger row. To CHANGE a scene's motif just call `swap` again — `_bind_scene_motif` atomically deletes+inserts one row (plan.py:841-844), so a re-bind IS the swap. No token is needed or produced. Caveat to encode in the copy: a re-bind recomputes `role_bindings` from cast auto-resolution (plan.py:827-832) and stamps `bound_via:'manual_scene'` (plan.py:839), so it is NOT byte-exact if a role was hand-rebound — which is exactly why we do not call it "Undo".

5. TEST (spec 33 DoD, line 718-722) — a unit test on the binding lens asserting: given a chapter bind response, the Undo control renders and PATCHes with the token; given a scene bind response, the Undo control is ABSENT and only "Unbind" renders.

SECONDARY (agent/GUI parity — the spec understates this): the MCP tool does NOT "return undo_token: none" on a scene, it HARD-404s. `composition_motif_bind` calls `apply_motif_swap` unconditionally (server.py:2785); `apply_motif_swap` raises `MotifSwapError` unless `kind == "chapter"` (motif_select.py:463-464); server.py:2794-2796 maps that to `uniform_not_accessible()`. So there is NO agent path to bind a motif to a scene while the GUI has one. Do BOTH: (a) fix-now, one line — amend the `composition_motif_bind` description (server.py:2734-2740) to state "CHAPTER nodes only; a scene node is not accessible" so the agent stops burning a call on a 404; and (b) file defer row D-MOTIF-MCP-SCENE-BIND-404 for the real fix (teach the MCP tool the same `node.kind` dispatch the HTTP route has at plan.py:894, calling `_bind_scene_motif`) — gate 2 (large/structural: it changes an MCP tool's return contract by node kind, which ripples into contracts/tool-liveness.json), target: the Wave-3b BE slice or the next composition-tools wave.

DEFAULT THE PO CAN VETO: I am giving scene nodes an "Unbind" (clear) button rather than no control at all. Spec 33's DoD says only "no Undo button is offered on a scene node" — Unbind is a different, honest control backed by a route that already exists, and it does not advertise token-undo. If the PO wants scene nodes to have zero binding-removal affordance in this wave, drop step 4 and keep steps 1-3.

*Evidence:* services/composition-service/app/routers/plan.py:845-852 — `_bind_scene_motif` returns {node_id, motif_id, motif_name, bound, unresolved_roles, warning} with NO `undo_token` key; contrast plan.py:942 (chapter swap returns `undo_token`). Dispatch on kind: plan.py:894. Undo branch: plan.py:881-886. Scene clear: plan.py:968-972. Root cause: services/composition-service/app/engine/motif_select.py:463-464 (`apply_motif_swap` requires kind=="chapter") + motif_select.py:494-498 (token = {chapter_node_id, archived_scene_ids, new_scene_ids} — exists to reverse scene archival, which a scene bind never does) + motif_select.py:509-532 (`undo_motif_swap` = exact idempotent inverse). MCP hard-404 on scene: services/composition-service/app/mcp/server.py:2785 + 2794-2796. Zero FE consumers: `grep -rn "undo_token\|undoToken" frontend/src` → no matches; frontend/src/features/composition/motif/hooks/useMotifBinding.ts:31-37 discards the swap response entirely (no undo mutation exists).

### Q-30-PO4-SPECS-DRAFTS-GATE
PO-4's whole-plan gate is MET — proceed to PLAN/BUILD for all waves; do NOT author any further specs or drafts as a precondition. The two "folded" surfaces are both already drafted, exactly where plan 30 §11 assigned them, so NO new draft file is to be created for either:

1. `progress` — build it from `design-drafts/screens/studio/screen-quality-completion.html` section ⑤ (starts :870). It ships in Wave 1 with the other three quality panels, but as category `editor`, NOT as a quality-hub card (QC-2, restated at :449 and in plan 30 :548). The draft already specifies the backend deltas the builder needs: BE-P1 = widen `GET …/progress` with `by_chapter[]` (:100, marked DROPPABLE); BE-P2 = `PUT …/progress/goal` + a NEW per-user table `composition_progress_goal(user_id, project_id, daily_goal, …)` (:101-104) — note this is a schema side effect, so Wave 1's size floor already accounts for it alongside BE-9's `authoring_run_units.job_id`. Panel renders today's words / streak / goal / sparkline / by-chapter, with the goal's effective value + source tier per SET-1 (:1002-1004). No MCP tool for `progress` — deliberate (:1420): a personal word-count stat is not an agent capability. Do NOT create `screen-progress.html`.

2. `book-settings` Composition section — build it from `design-drafts/screens/studio/screen-divergence.html` section ⑦ (starts :906) in Wave 6. It is explicitly NOT a new panel: add a self-contained `<CompositionSettingsSection bookId>` inside `pages/book-tabs/SettingsTab.tsx` (which the `book-settings` panel already wraps), with its own save path (:908-911). Reuse the shipped TierChip on its already-existing `book`/`account` tiers (:394-396) — no new tier rows. Every row shows effective value + source tier (SET-1), and no row may show a value the engine will not use — the draft flags that `work.settings.model_roles` HAS NO READER in composition-service (:147-150) while the engine actually reads `settings_dict.get("critic_model_ref")`, so the section writes `model_roles.{critic,planner}` and must either wire the reader or render the honest "critique skipped" warning rather than a fourth bespoke `critic_model_ref` picker (SET-8: one home, one name). Also carry the `works.py:311` lost-update fix from plan 30 :267 (`settings = $n::jsonb` full-blob REPLACE → `settings || $n::jsonb`, or send If-Match). Do NOT create `screen-book-settings.html`.

Bonus coverage confirmed while verifying: the same divergence draft also carries section ⑧, the plan-hub Beats facet — Wave 6's second non-panel surface — so Wave 6 has zero undrafted surfaces.

Default I am picking so the PO is not stopped (veto if wrong): the fold stands. A separate mock for either surface would be strictly less informative than the drafted sections, which already name the target file, the tier semantics, and the backend deltas. Nothing blocks Wave 6.

*Evidence:* design-drafts/screens/studio/screen-quality-completion.html:870 (`<h2>⑤ Progress <span class="tag">progress</span> <span class="tag">category: editor</span> — the write-only loop closes here`; panel mock :878, SET-1 tier treatment :1002, BE-P1/BE-P2 backend deltas :100-104, no-MCP-tool rationale :1420) · design-drafts/screens/studio/screen-divergence.html:906 (`<h2>⑦ The Composition section <span class="tag">inside book-settings</span> — the Book tier of the model cascade, which has never had a writer`; "Not a new panel" + target file `pages/book-tabs/SettingsTab.tsx` :908, TierChip reuse :394-404, `model_roles` has no reader :147-150) · both folds are the plan's OWN assignment: docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:795 (Wave 1 draft = quality-canon-rules + progress + quality-corrections + quality-heal) and :800 (Wave 6 drafts = style-voice + reference-shelf; divergence + the book-settings Composition section) · specs 31-38 all present in docs/specs/2026-07-01-writing-studio/ · 24 drafts present in design-drafts/screens/studio/ (13 pre-existing + 11 new), token-normalized per plan 30 :686-691.

### Q-30-KG-CREATE-GRANT-PATH
ALIGN THE REST ROUTE ON THE GRANT CHECK — as a mandatory backend slice of Wave 8a (G-KG-WRITE-HOLES), landing BEFORE the FE create/archive buttons are wired, because the FE buttons are what make the divergence user-visible.

Verdict first: this is a real defect but NOT the CRITICAL "tenancy breach" stop (no cross-user read/mutation is possible — merge_entity hashes user_id into canonical_id and every read binds the JWT user_id, so an ungranted POST lands in the CALLER'S OWN partition). It is a two-partitions divergence + an unauthorized project-tag write. Fix it in-wave; do not stop the run.

SLICE X-KG-REST-GRANT (service: knowledge-service; size M; one file + one repo helper + tests)

1) POST /v1/knowledge/entities — `app/routers/public/entities.py:999-1026`. project_id arrives in the BODY, so use the body/token-driven gate, NOT the path-bound `require_project_grant` factory (it binds `project_id` as a path/query param and will not see the body). Copy the pattern already used at `app/routers/public/kg_actions.py:318`:
   - inject `projects: ProjectsRepo = Depends(get_projects_repo)`, `gc: GrantClient = Depends(get_grant_client)`, keep `caller: UUID = Depends(get_current_user)`;
   - `meta = await projects.project_meta(body.project_id)`; `if meta is None: raise HTTPException(404, "not found")`;
   - `owner = await _resolve_owner(caller, owner, book_id, GrantLevel.EDIT, gc)` (import from `app.auth.grant_deps` — same import kg_actions.py:38 uses; it already gives anti-oracle 404 for non-grantee / book-less-non-owner and 403 for under-tier);
   - call `merge_entity(session, user_id=str(owner), project_id=str(body.project_id), name=..., kind=body.kind, source_type="manual", confidence=1.0, provenance="human_authored")` — i.e. byte-identical authorization + write to `_handle_kg_create_node` (graph_schema_tools.py:1719-1731). Keep the existing `_AUTHORABLE_KINDS` validator (entities.py:975); the MCP tool has no such gate, so REST stays the stricter of the two — that is intentional, do not loosen it.

2) Pair it with the READ routes the same panels call, or the collaborator writes a node they cannot see (the repo's write-you-can't-read trap). Same file, swap `user_id: UUID = Depends(get_current_user)` for a resolve-to-owner gate on: `GET /projects/{project_id}/subgraph` (:750), `GET /projects/{project_id}/world-subgraph` (:818), `GET /projects/{project_id}/gaps` (:691) → `Depends(require_project_grant(GrantLevel.VIEW))` (mechanical; precedent drawers.py:152, graph_views.py:520). `GET /entities` (:278) has an OPTIONAL project_id query — when it is set, resolve-to-owner (manual `_resolve_owner`, same as #1, at VIEW); when it is None keep raw-JWT ("browse what I own").

3) Entity-id-keyed writes that Wave 8a is also wiring buttons for — DELETE /entities/{id} (archive, :172), POST /entities/{id}/unlock (:1134), PATCH /entities/{id} (:1039) — gate on the LOADED ROW'S parent (the repo's `gate-must-derive-scope-from-the-loaded-row` rule): add `project_for_entity(session, entity_id) -> (user_id, project_id) | None` to `app/db/neo4j_repos/entities.py` (a one-line `MATCH (e:Entity {id:$id}) RETURN e.user_id, e.project_id`), then `projects.project_meta(project_id)` → `_resolve_owner(caller, owner, book_id, GrantLevel.EDIT, gc)` → pass `user_id=str(owner)` to the repo call. Missing entity / non-grantee → 404 (preserves the KSA §6.4 cross-user-404 contract the existing tests assert). `promote_entity` (:1206) and `merge_entity_into` (:1403) get the same treatment at MANAGE.

4) TESTS (all in knowledge-service tests; the 4th is the one that proves the two doors converged):
   a. non-grantee POSTs /v1/knowledge/entities with another user's project_id → 404 (today: 201 + a junk node tagged with a project they cannot touch);
   b. VIEW-only grantee POSTs → 403;
   c. EDIT grantee POSTs → 201 AND the node is returned by the OWNER's GET /projects/{id}/subgraph (proves it landed in the owner partition, not the collaborator's);
   d. ONE-CANONICAL-ID test: an EDIT collaborator calling MCP `kg_create_node` and REST POST /entities with the same (project, name, kind) gets the SAME `entity_id` back. Today these return two different ids — that assertion is the refutation residual, and it going green is the definition of done for this slice.

5) Wave 8a Definition of Done gains the literal step: `/review-impl` runs at wave close and any bug it finds is fixed before the wave closes (PO run policy).

Default I am choosing (veto-able): grant tier for entity create/edit = EDIT, delete/promote/merge = MANAGE, reads = VIEW — mirroring what the MCP tools already chose (graph_schema_tools.py:1719 uses EDIT for create). If the PO wants KG writes to be owner-only, the change is one enum per route, but that would contradict the shipped MCP behaviour and should be decided explicitly rather than by drift.

*Evidence:* services/knowledge-service/app/routers/public/entities.py:1004-1026 (`create_entity_endpoint`: `user_id: UUID = Depends(get_current_user)` → `merge_entity(user_id=str(user_id), project_id=str(body.project_id))` at :1020 — `body.project_id` is never looked up and no grant call is made) vs services/knowledge-service/app/tools/graph_schema_tools.py:1711-1737 (`_handle_kg_create_node`: `owner = await _resolve_project_owner(ctx, GrantLevel.EDIT)` at :1719 → `merge_entity(user_id=str(owner), ...)`). The canonical gate to reuse when project_id is NOT a path param: services/knowledge-service/app/auth/grant_deps.py:92 `_resolve_owner`, invoked exactly this way at services/knowledge-service/app/routers/public/kg_actions.py:318 (`_resolve_owner(caller, owner, book_id, GrantLevel.MANAGE, gc)`, imported at kg_actions.py:38). Path-bound precedent: drawers.py:152, graph_views.py:520, extraction.py:335. Non-breach proof: services/knowledge-service/app/db/neo4j_repos/entities.py:319-331 (`merge_entity` docstring + `entity_canonical_id(user_id=...)`) — the id hash includes user_id and reads bind user_id, so an ungranted REST write lands in the caller's own partition, never the owner's.

### Q-30-MOTIF-PROMOTE-TARGET
BUILD BOTH LEGS IN WAVE 3a (G-MOTIF-LIBRARY). No new backend routes — the BE is complete and enum-closed; this is pure FE wiring. It does not contradict §0 PO-1..4, and plan 30's own G-MOTIF-LIBRARY target GUI already commits to "3-tier browse (incl. the NO-FE-CONSUMER book_shared tier)" — this decision just makes it executable. (X-7 gather_motifs packer lens remains the cluster's prerequisite; unchanged.)

=== LEG A — MotifMinePanel SENDS promote_target ===
A1. frontend/src/features/composition/motif/api.ts:133-161 (minePropose). Add `promoteTarget?: 'user' | 'book_shared'` to the args type. In the MCP args object add:
    ...(args.scope === 'book' && args.bookId && args.promoteTarget === 'book_shared' ? { promote_target: 'book_shared' } : {})
    NEVER send book_shared on corpus scope: server.py:3004 returns {success:false,error:"promote_target='book_shared' requires scope='book' with a book_id"} and motif_mine.py:507-509 silently downgrades to 'user'. Do not rely on either — guard client-side (the closed-set arg is already `Literal["user","book_shared"]` at server.py:2966, so no contract change is needed).
A2. hooks/useMotifMine.ts — add `const [promoteTarget, setPromoteTarget] = useState<'user'|'book_shared'>('user')`; pass it into motifApi.minePropose (line 24-27). Reset it to 'user' inside a `setScope` WRAPPER when scope flips to 'corpus' (explicit callback — NOT a useEffect; CLAUDE.md bans useEffect-for-event-handling). Return `promoteTarget, setPromoteTarget`.
A3. components/MotifMinePanel.tsx — directly under the scope radiogroup (after line 78), render, ONLY when `mine.scope === 'book' && bookId`, a checkbox `data-testid="motif-mine-shared"` labelled i18n key `motif.mine.shareWithBook` (defaultValue: "Share the mined drafts with this book's collaborators") bound to `mine.promoteTarget === 'book_shared'`, onChange → setPromoteTarget. Disabled while `busy`. It must NOT render on corpus scope.
A4. Tests — __tests__/MotifMine.test.tsx: (a) book scope + checkbox ON ⇒ mcpExecute called with args containing promote_target:'book_shared'; (b) corpus scope ⇒ the checkbox is NOT in the DOM AND promote_target is absent from the args; (c) toggle ON then switch book→corpus ⇒ promote_target absent (the reset fired).

=== LEG B — surface the book_shared tier in the browse (route EXISTS) ===
B1. api.ts — add `listInBook(bookId, params: { status?: 'active'|'draft'|'archived'; q?; kind?; genre?; language?; limit? }, token): Promise<{ motifs: Motif[]; book_id: string; count: number }>` → apiJson(`${BASE}/motifs/book/${bookId}${_qs(params)}`). This is motif.py:219 (VIEW-gated; returns caller's own rows + ANY collaborator's book_shared rows; each row badged book_shared at motif.py:215; limit cap le=100).
B2. hooks/useMotifLibrary.ts:17 — widen `LibraryScope` to `'my' | 'book' | 'catalog' | 'drafts'`; accept `bookId` in opts. Add `bookStatus` state ('active' | 'draft') + a `bookQuery`: queryKey ['composition','motifs','book',bookId,bookStatus,q], queryFn motifApi.listInBook(bookId!, { status: bookStatus, q, limit: 100 }, token!), enabled: !!token && !!bookId && scope==='book'. Wire it into the `query` selector at line 101. The draft status is what makes the Leg-A shared mined drafts reviewable BY COLLABORATORS (the existing 'drafts' tab is scope='mine' = owner-only, so it shows them only to the miner).
B3. components/MotifScopeTabs.tsx — add a "This book" tab, rendered ONLY when bookId != null; MotifLibraryView.tsx (line 72) passes bookId through. On the book tab show a small active|draft status toggle. MotifCard already badges book_shared (MotifCard.tsx:68) — no card change.
B4. COLLABORATOR WRITE PATH (the real bug this leg exposes — fix it in the same slice): api.ts:67-77 `patch`/`archive` never send `?book_id=`, but the shared-tier branches are keyed on exactly that query param (motif.py:293/303, motif.py:367/375); the default branch filters owner_user_id=caller, so a NON-OWNER collaborator promoting/archiving a shared draft gets a 404 today. Add an optional `bookId` arg to `patch`, `archive` and `promote` (api.ts:185) that appends `?book_id=<id>`, and have useMotifDraftActions / useMotifEditor pass it whenever `motif.book_shared === true`. Also disable the visibility control in MotifEditor for a book_shared row — the shared PATCH path 400s MOTIF_SHARED_STAYS_PRIVATE on any visibility != 'private' (motif.py:307).
B5. Tests — MotifLibraryView test: the "This book" tab renders only with a bookId and fetches /motifs/book/{id}; useMotifDraftActions test: promoting a row with book_shared=true issues PATCH /motifs/{id}?book_id=<id> with If-Match, and a non-shared row issues it WITHOUT book_id.

Definition of Done for the slice: A4+B5 green, plus `/review-impl` at wave close (PO policy #2). Sane default recorded for PO veto: the mine "share with collaborators" toggle defaults OFF (promote_target='user'), i.e. mining stays private unless the user opts in.

*Evidence:* FE gap (mine): frontend/src/features/composition/motif/api.ts:143-150 — minePropose's MCP args are scope/book_id/min_support/language/model_ref/model_source; promote_target is never sent. BE already accepts it: services/composition-service/app/mcp/server.py:2966 (`promote_target: Literal["user","book_shared"] = "user"`), guarded at server.py:3004, forwarded at app/routers/actions.py:653, applied at app/engine/motif_mine.py:376. | FE gap (browse): frontend/src/features/composition/motif/hooks/useMotifLibrary.ts:17 (`LibraryScope = 'my'|'catalog'|'drafts'`) + api.ts has no caller for the EXISTING route services/composition-service/app/routers/motif.py:219 (`GET /motifs/book/{book_id}`, VIEW-gated, badges book_shared at motif.py:215); the 'my' tab cannot see a collaborator's shared row because app/db/repositories/motif_repo.py:45 `_VISIBLE_PREDICATE = (owner_user_id IS NULL OR visibility='public' OR owner_user_id=$1)`. | Collaborator-write trap: api.ts:67-77 patch/archive send no `?book_id=`, but the shared branches key on it at motif.py:293/303 and motif.py:367/375. | Adopt half is already wired (AdoptTargetModal.tsx:109, useAdoptFlow.ts:36, MotifCard.tsx:68), so "no FE consumer" holds only for mine + browse.

### Q-30-DRAFT-DESTRUCTIVE-TOKEN
CLAIM IS PARTIALLY FALSE — the rename landed, but the drift was FIVE ways, not four. Verified on disk at HEAD (drafts committed in d0f17555e).

WHAT HOLDS: `--danger`/`--danger-muted` = ZERO occurrences in all 24 drafts (every "danger" hit is a CSS class like `.btn.danger`, never a custom property). `#d95d5d` and `#dc4e4e` = ZERO occurrences. All 18 files that define `--destructive` define it `#d9584f`; all 17 defining `--destructive-muted` use `#3a1f1c`. The latent undefined-var no-op IS fixed — I cross-checked all 24 files: every file that USES `var(--destructive-muted)` also DEFINES it, including studio-agent-mode (def=1, uses=5).

WHAT IS FALSE: `#e85a5a` SURVIVES in 2 files. The audit grepped token NAMES (`--danger`/`--destructive`) so it missed a fifth drift wearing a THIRD name. Also "all 24 normalized" is overstated: only 18/24 define the token; the other 6 (command-palette, manuscript-navigator, studio-agent-chat, studio-agent-gui-bridge, studio-raw-editor, studio-state-host) define AND use zero destructive tokens — benign, leave them.

BUILDER INSTRUCTIONS (FIX-NOW — 2 files, root cause clear; a defer row would cost more than the fix):

1. TEMPLATE — copy `design-drafts/screens/studio/screen-issues-feed.html` (canon core block at :148, one-line, `--destructive: #d9584f; --destructive-muted: #3a1f1c;`, uses muted 4x, appends domain tokens below the block under a comment). DO NOT copy `screen-studio-raw-editor.html` or `screen-studio-agent-gui-bridge.html` — both carry the surviving drift.

2. FIX `screen-studio-raw-editor.html`: at :28 replace `--error: #e85a5a; --error-muted: #3d1a1a;` with `--destructive: #d9584f; --destructive-muted: #3a1f1c;`. Rewrite the 7 usages `var(--error)`→`var(--destructive)` and `var(--error-muted)`→`var(--destructive-muted)` at lines 65, 97, 98, 108, 109, 120, 128. At :120 also replace the raw `rgba(232,90,90,.18)` (== #e85a5a) with `rgba(217,88,79,.18)` (== #d9584f).

3. FIX `screen-studio-agent-gui-bridge.html`: add `--destructive: #d9584f; --destructive-muted: #3a1f1c;` to its `:root`, and at :74 change `.forbidden strong { color: #e85a5a; }` → `color: var(--destructive);`.

4. AMEND spec 30 §8.3 (lines 673-689): the table says the red "drifted FOUR ways" and "All 24 files are now normalized" — both wrong. Add the fifth row (`--error: #e85a5a` + `--error-muted: #3d1a1a` in studio-raw-editor; raw `#e85a5a` hex in studio-agent-gui-bridge) and restate as: "18 of 24 define the canon destructive token; the other 6 have no destructive affordance and need none. There is no `--danger` and no `--error` alias."

5. GUARD (per the repo's own `checklist-is-self-report-enforce-by-tests` lesson — a prose checklist did not stop this drift, and grepping only the known names is exactly why it was missed): add `scripts/design-draft-token-lint.py` — fail if any file under `design-drafts/screens/studio/*.html` contains (a) a destructive-alias custom property other than `--destructive`/`--destructive-muted` (i.e. `--danger*`, `--error*`), or (b) any red hex/rgba outside {#d9584f, #3a1f1c} in a color-ish position. Wire it into the same pre-commit hook path as `scripts/ai-provider-gate.py`. Grep by CONCEPT (the hex), not by the token name — that is the miss this bug is made of.

SECONDARY (same bug class, WARNING token, fix while you are in the file): `screen-studio-agent-hooks.html:23` defines `--warn: #e8b87e` where canon is `--warning: #e8a832` — a name+value drift on the warning token. Normalize it and have the lint in step 5 cover `--warn*` too. (Same file defines `--destructive` but not `--destructive-muted`; harmless since it uses muted 0x, but add it for template parity.)

DEFAULT THE PO CAN VETO: I chose to normalize `--error` → `--destructive` rather than bless `--error` as a second sanctioned token. Rationale: §8.3 and the repo's `css-var-duplicated-across-two-consumers-drifts` memory both say one concept = one name; a syntax-error underline and a destructive button are the same "this is wrong" red in a dark-only mock.

*Evidence:* design-drafts/screens/studio/screen-studio-raw-editor.html:28 — `--error: #e85a5a; --error-muted: #3d1a1a;` (the FIFTH drift, missed by the audit's name-based grep; used 7x at :65,:97,:98,:108,:109,:120,:128, plus rgba(232,90,90,.18) at :120). design-drafts/screens/studio/screen-studio-agent-gui-bridge.html:74 — `.forbidden strong { color: #e85a5a; }` (raw hex; file defines zero destructive tokens). CANON TEMPLATE: design-drafts/screens/studio/screen-issues-feed.html:148. FIX CONFIRMED LANDED: screen-studio-agent-mode.html:76 defines `--destructive-muted: #3a1f1c` and uses it 5x (the undefined-var no-op is gone). SECONDARY: screen-studio-agent-hooks.html:23 — `--warn: #e8b87e` vs canon `--warning: #e8a832`. Greps: `grep -rn -- "--danger" design-drafts/screens/studio/` → 0 hits; `d95d5d`/`dc4e4e` → 0 hits; `e85a5a` → 2 hits; 18/24 files define `--destructive`, all `#d9584f`; every file using `var(--destructive-muted)` also defines it. Spec claim under test: docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:673-689.

### Q-30-KG-THREE-DEAD-BUTTONS
RECLASSIFY: this is NOT a BE_PREREQ — it is pure FE wiring (zero backend). And the fix is 3 ADDS + 1 REMOVE, not 4 adds. The 3 "dead buttons" must be DELETED, not wired.

WHY REMOVE (the default the PO may veto): project archive/restore/delete ALREADY has a working studio home — KnowledgeHubPanel.tsx:20,45 mounts ProjectsBrowser as-is, with real handlers (ProjectsBrowser.tsx:129-168) and confirm dialogs (:313-330). So GG-1 ("every backend capability has a human surface") is SATISFIED for project CRUD. The kg-overview buttons are a duplicate broken copy, and OverviewSection.tsx:60-63 already records the intent: "Archive/restore/delete stay on the projects browser (destructive CRUD lives with the list)." Wiring a second destructive-CRUD path into kg-overview would fork it (DOCK-2 anti-fork) and let a user delete the very project the panel is scoped to. Removing kills the silent-no-op (the actual defect, repo's own silent-success-is-a-bug class) in ~10 lines and cannot regress ProjectsBrowser.

WAVE 8a SLICES (builder follows without further thought):

S1 — REMOVE the 3 dead buttons.
- frontend/src/features/knowledge/components/ProjectRow.tsx: make props optional — `onArchive?:`, `onRestore?:`, `onDelete?:` (lines 29-31); guard each render site so the button only renders when its prop is passed (`:294` archive, `:302` restore, `:310` delete).
- frontend/src/features/knowledge/components/shell/OverviewSection.tsx: delete `const noop = () => {}` (:56) and the three `onArchive/onRestore/onDelete={noop}` props (:67-69). Keep `onEdit` (real — opens ProjectFormModal at :73-82) and `onExploreGraph`.
- TESTS: studio/panels/__tests__/KgOverviewPanel.test.tsx asserts the archive/restore/delete buttons are ABSENT; add/extend a ProjectsBrowser test asserting they are still PRESENT (regression guard for the optional-prop change).

S2 — ADD useCreateEntity.
- frontend/src/features/knowledge/hooks/useEntityMutations.ts: new `useCreateEntity()` mirroring `useUpdateEntity` (:33-91). Calls `knowledgeApi.createEntity` (api.ts:1600 → POST /entities), payload `CreateEntityPayload {project_id, name, kind}` (api.ts:581-585). Invalidate the same entity-list queryKey useUpdateEntity invalidates. Copy the live working caller's shape: composition/hooks/useWorldMap.ts:129.

S3 — ADD EntityCreateDialog + "New entity" toolbar button.
- New frontend/src/features/knowledge/components/EntityCreateDialog.tsx beside EntityEditDialog.tsx (which is edit-only — it requires an `entity` prop, EntityEditDialog.tsx:13-17, so it cannot be reused for create). Same FormDialog shell, same splitAliases helper; fields name + kind + aliases.
- EntitiesTab.tsx renders the button, ENABLED ONLY when `scopedProjectId` is set (EntitiesTab takes optional scope — KgEntitiesPanel.tsx:18-19); in global cross-project browse there is no project to create into, so hide it (do NOT render a disabled mystery button).

S4 — ADD the empty-state CTA (the real buttonless state).
- EntitiesTab.tsx:249-258: the `entities-empty` <p> is a dead end. Render the same "New entity" button inside it when `total === 0 && scopedProjectId` — the truly-empty branch ONLY, never the `emptyForFilters` branch (a filter miss is not an empty graph).
- STALE-CLAIM CORRECTION (do not re-do this work): the audit's "the empty-graph state has no button" is HALF STALE. The NO-PROJECT empty state already HAS a create button — KgNoProjectState.tsx:39-47 (`kg-no-project-create-btn`, shipped D-KG-NO-CREATE-CTA 2026-07-05), rendered by KgOverviewPanel.tsx:29-35. Only `entities-empty` lacks one.

OPTIONAL RIDE-ALONG (same register row, zero backend): relation create — `knowledgeApi.createRelation` + `CreateRelationPayload` already exist (api.ts:589). One more dialog on the same pattern if the builder wants it in 8a.

DoD: `/review-impl` at wave close (PO policy 2), and the vitest suites for KgOverviewPanel + EntitiesTab + ProjectsBrowser green.

*Evidence:* frontend/src/features/studio/panels/KnowledgeHubPanel.tsx:20,45 (mounts ProjectsBrowser as-is ⇒ project archive/restore/delete ALREADY has a working studio home) · frontend/src/features/knowledge/components/shell/OverviewSection.tsx:56,60-63,67-69 (`const noop = () => {}` passed as onArchive/onRestore/onDelete, with a comment stating destructive CRUD is meant to live on the browser) · frontend/src/features/knowledge/components/ProjectRow.tsx:29-31,294,302,310 (props required + all 3 buttons rendered unconditionally ⇒ the silent no-op) · frontend/src/features/knowledge/components/ProjectsBrowser.tsx:129-168,279-281,313-330 (the real, working handlers + confirm dialogs) · frontend/src/features/knowledge/api.ts:1067 archiveProject, :1074 deleteProject, :1600 createEntity, :581-585 CreateEntityPayload; useProjects.ts:144-147 exports all four mutations ⇒ ZERO backend needed · frontend/src/features/composition/hooks/useWorldMap.ts:129 (live createEntity caller to copy — the audit's "grep → EMPTY" holds only within features/knowledge/**) · frontend/src/features/knowledge/components/EntitiesTab.tsx:249-258 (`entities-empty` is a bare <p> — the actual buttonless state) · frontend/src/features/knowledge/components/shell/KgNoProjectState.tsx:39-47 (`kg-no-project-create-btn` ALREADY EXISTS ⇒ the audit's empty-state sub-claim is half stale) · frontend/src/features/knowledge/components/EntityEditDialog.tsx:13-17 (edit-only: requires `entity` ⇒ a separate create dialog is needed) · docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:263 (register agrees: "entity/relation create: NONE (pure FE wiring)"), :308 (BE-14 — the routes belong to the OTHER sub-gap, not this one)

### Q-30-STALE-WORKTREES
DECIDED — no collision is possible, because `/warp` does not use `lane/*` at all. The 7 stale worktrees are inert; leave them alone. Concrete build instructions:

1) **Never hand-name a lane branch.** `/warp` mints slice branches from `slice_branch()` = `warp/<task-slug>/slice-<id>` (scripts/warp/worktrees.py:43-46). Use the built-in namespace as-is. For any fan-out in plan 30, pass a task slug (e.g. `--task studio-gui-gap`), producing `warp/studio-gui-gap/slice-1..N`. The `lane/*` names from the KG-ontology fan-out are in a **different namespace** and cannot be reused by accident — `/warp` has no code path that emits `lane/`.

2) **Pre-fan-out gate (literal step in each wave that fans out):** `python scripts/warp/worktrees.py check --task <slug>` must print `OK: no stale warp worktrees/branches`. It scopes strictly to the `warp/` prefix (`is_warp_branch`, scripts/warp/worktrees.py:84-88; `warp_worktrees`, :102-106), so the 7 `lane/*` worktrees are **invisible** to it and will NOT false-refuse the fan-out. Do not "clean up the lanes to make check pass" — check never looks at them.

3) **DO NOT remove the lane worktrees.** `cmd_cleanup` (scripts/warp/worktrees.py:236-250) calls `git worktree remove --force` but only over `warp_worktrees(task)` — i.e. `warp/`-prefixed only — so it can never touch `.claude/worktrees/agent-*` carrying `lane/*`. **Never run a manual `git worktree remove --force` against those 7 paths** (repo memory: Windows `--force` follows the `node_modules` junction and deletes the SHARED target). Reclaiming them is out of scope for plan 30 and buys nothing: all 7 lane branches are **0 commits ahead of main** (fully merged), so nothing is at risk in leaving them checked out. (Checked: none of the 7 currently has a `node_modules` junction, but the do-not-force rule stands regardless.)

4) **Post-COMMIT cleanup of THIS plan's lanes only:** `python scripts/warp/worktrees.py cleanup --task <slug> --delete-branches` — it skips dirty worktrees (`_is_dirty`, :116-123) and refuses to delete unmerged branches (:245-250).

Default if the PO disagrees: the only alternative is a manual lane-worktree purge, which is exactly the destructive Windows-junction op CLAUDE.md's critical-blocker rule tells the builder to stop on — so it stays out of the plan.

*Evidence:* scripts/warp/worktrees.py:43-46 (`slice_branch` → `warp/<task>/slice-<id>` — no `lane/` anywhere); :84-88 (`is_warp_branch` matches only the `warp/` prefix); :102-106 (`warp_worktrees` filters by that predicate); :203-216 (`cmd_check` refuses a fan-out only on `warp/` staleness); :236-250 (`cmd_cleanup`'s `git worktree remove --force` iterates `warp_worktrees(task)` only). `git worktree list` → 7 worktrees on `lane/{LA-resolver,LB-extraction,LC-adopt,LD-views,LE-frontend,LF-mcp,LH-triage}`; `git rev-list --count main..lane/*` = 0 for all 7 (already merged into main). Plan 30 line 720 is the row this resolves.

### Q-30-BOOKPACKAGE-PLANDRAWER
NO COORDINATION STEP. Build straight through. The concern rests on a stale premise and a no-op instruction; the code settles both.

(1) DELETE the "read the Book-Package RUN-STATE for SC11/PH12 before Wave 2" gate — the PO-DECIDE is RESOLVED AND SHIPPED (2026-07-13, 5 phases). Verdict: the written-verdict is MAINTAINED on write, not derived. `outline_node.written_scene_id` is a real column; `written` (bool) rides PH10's summary payload; `useActualState.ts` is DELETED. Wave 2/3/6 consume `node.written` from `planHubMappers.ts:32` and must NOT re-derive it client-side or add a cross-service join. Also correct plan 30's §9 row (line 716), which still says "unresolved".

(2) DELETE "coordinate before editing PlanDrawer.tsx" — Book-Package is DECLARED COMPLETE; there is no concurrent writer. The waves are sequential and touch DISJOINT functions in the file, so there is nothing to serialize:

  WAVE 2 (G-ARC-SPEC-CRUD) owns `ArcFacets`, PlanDrawer.tsx:305-357 ONLY.
    - Replace the body of `ArcFacets` with `<ArcInspectorEmbed nodeId={arc.id} />` (new panel, spec 32 / DBT-06). Do not grow PlanDrawer — the embed makes the file SHRINK.
    - DELETE the `plan-drawer-arc-gap` note at PlanDrawer.tsx:351-354.
    - REQUIRED TEST FIX: `PlanDrawer.test.tsx:110` currently asserts `getByTestId('plan-drawer-arc-gap')).toBeInTheDocument()` — it asserts the ABSENCE of the feature Wave 2 builds. Flip it to `queryByTestId('plan-drawer-arc-gap')).toBeNull()` + assert the embed renders. Leave :88 (the chapter-variant negative assertion) as-is.
    - Do NOT touch `ChapterSceneFacets`.

  WAVE 3 (G-MOTIF-BINDING) owns `ChapterSceneFacets`, PlanDrawer.tsx:187-296 ONLY.
    - Insert ONE new `<Section title="Motifs" testid="plan-drawer-section-motifs">` between the "Craft" Section (closes :253) and the "Canon here" Section (opens :259), carrying bind/unbind/re-role.
    - Gate it on the CHAPTER variant only: `undo_token` is CHAPTER-scope, so do not advertise token-undo on scene nodes (plan 30:247).
    - Do NOT touch `ArcFacets`.

(3) Keep plan 30's existing warning that 00B_EXECUTION_ROADMAP.md §2 ("everything else in 22-28 is unbuilt") is STALE — that half of the concern is correct and still load-bearing. Do not re-plan 22-28 from it.

DEFAULT THE PO MAY VETO: I am treating the SC11 amendment as binding law for Waves 2/3/6 (read `written`, never re-derive). If the PO wants the client-side join back, that reverses a shipped 5-phase change and must be said now.

*Evidence:* docs/specs/2026-07-13-sc11-amendment-written-verdict.md:1-6 ("✅ SHIPPED 2026-07-13 — all 5 phases built, live-proven, committed", commits 3e0dbca3b..4bffd2cbe — verified present via `git log --oneline -1 3e0dbca3b` = "SC11 Phase 0" and `4bffd2cbe` = "SC11 Phase 4 — delete the client-side derivation"). docs/plans/2026-07-12-book-package-RUN-STATE.md:356 ("No ⚠ PO-DECIDE outstanding"). frontend/src/features/plan-hub/hooks/useActualState.ts — DOES NOT EXIST (deleted by Phase 4); replaced by frontend/src/features/plan-hub/hooks/planHubMappers.ts:32 (`written: n.written`) and :69 ("`written` is MAINTAINED on write (`outline_node.written_scene_id`)"). docs/specs/2026-07-01-writing-studio/24_plan_hub_v2.md:93 (PH10 AMENDED 2026-07-13 to carry `written`). DISJOINTNESS: frontend/src/features/plan-hub/components/PlanDrawer.tsx:187-296 (`ChapterSceneFacets` = Wave 3) vs :305-357 (`ArcFacets` = Wave 2) — zero shared lines; the stale gap note is :351-354. TEST TRAP: frontend/src/features/plan-hub/components/__tests__/PlanDrawer.test.tsx:110 asserts `plan-drawer-arc-gap` is in the document — Wave 2 must flip it. STALE ROW TO FIX: docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:716.

### Q-30-QUALITYCANONPANEL-HISTORY
REUSE the existing `focusRuleId` params seam in BOTH directions; write zero new deep-link plumbing. It is not a channel — it is one key on the generic `host.openPanel(panelId, {focus, params})` transport (StudioHostProvider.tsx:52). Builder instructions, exactly:

1. NEW WRAPPER — `frontend/src/features/studio/panels/QualityCanonRulesPanel.tsx` (studio panel, thin). It MUST: (a) `useStudioPanel('quality-canon-rules', props.api)`; (b) resolve the project through the ONE gate `useQualityWork(host.bookId, accessToken)` (useQualityWork.ts:34) and render `QualityNoWorkState` when kind !== 'ready' — do NOT render a CRUD list over an unqueried project (this is verbatim the HIGH that /review-impl caught in d662bd97d: `enabled: !!projectId` queries resolve to [] and the panel lied "no canon issues found"; all 8 dev-DB Works are pending_project_backfill); (c) on ready, render the ALREADY-BUILT `<CanonRulesPanel projectId={work.projectId} bookId={host.bookId} token={accessToken} />` from features/composition/components/CanonRulesPanel.tsx:11 — a PORT, not a rebuild. Do not re-implement useCanonRules (hooks/useCanonRules.ts:6 already has list/create/patch/remove with If-Match OCC via `version`).

2. FOCUS PROP — add ONE optional prop `focusRuleId?: string | null` to CanonRulesPanel (same name, one name for one concept). Behavior: hoist that rule to the top of the list (copy the stable `hoist()` helper at useQualityCanon.ts:63 — same semantics, non-matching rows keep order) and open it in the in-place editor (`setEditingId(focusRuleId)` at CanonRulesPanel.tsx:18). If the id matches no rule (archived, or a judge-paraphrased id — d662bd97d deliberately keeps `rule_id` as raw TEXT, never uuid-cast), show a "that rule no longer exists" banner — MUST NOT silently no-op, mirroring the FocusBanner honesty pattern at QualityCanonPanel.tsx:135-146. Its existing prop signature stays intact so the legacy composition page keeps working.

3. DEEP-LINK OUT (read → write) — in `QualityCanonPanel.tsx` `RuleRow` (~line 163), add an "Edit rule" action next to the existing jump action: `host.openPanel('quality-canon-rules', { focus: true, params: { bookId: host.bookId, focusRuleId: r.rule_id } })`. Render it ONLY when `r.rule_id && r.rule_text` (a violation whose rule did not resolve has nothing to edit — d662bd97d keeps those rows visible with rule_text=null; the button must be absent, not dead).

4. DEEP-LINK IN (write → read) — in the new wrapper's row actions, "See violations" → `host.openPanel('quality-canon', { focus: true, params: { bookId, focusRuleId: rule.id } })`. This is the seam PlanHubPanel.tsx:72 already uses; consumer side already implemented (useQualityCanon.ts:74). Zero new code beyond the call.

5. REGISTRATION — catalog.ts: add `{ id: 'quality-canon-rules', component: QualityCanonRulesPanel, titleKey/descKey/guideBodyKey, category: 'quality' }` next to line 270. QualityHubPanel.tsx:17: add the 5th hub card `{ panelId: 'quality-canon-rules', icon: '📜', ... }`. Frontend-Tool-Contract (closed-set enum, LOCKED): append `"quality-canon-rules"` to the panel_id enum in services/chat-service/app/services/frontend_tools.py:402 AND its description block (~:479), then regenerate contracts/frontend-tools.contract.json (:256) via `WRITE_FRONTEND_CONTRACT=1 pytest` — a panel not in the enum is unreachable by the agent (this is the `panel:"editor"` silent-no-op bug class).

6. TESTS — extend `panels/__tests__/QualityCanonPanel.test.tsx`: (a) rule row with resolved rule_text renders the Edit-rule button and openPanel is called with exactly `('quality-canon-rules', {focus:true, params:{bookId, focusRuleId}})`; (b) rule row with rule_text=null renders NO Edit button. New `QualityCanonRulesPanel.test.tsx`: (c) work.kind='no-work'/'unavailable' → QualityNoWorkState, and NO canon-rule list is rendered; (d) params.focusRuleId matching a rule → that rule is first AND in edit mode; (e) params.focusRuleId matching nothing → "rule no longer exists" banner (assert testid), not a silent empty focus.

Default I am picking (PO may veto): the OUT link is a per-row button, not an auto-open — clicking a violation must not yank the reader out of the findings list.

*Evidence:* frontend/src/features/studio/panels/useQualityCanon.ts:29 (`focusRuleId?: string | null` in CanonFocusParams), :74 (consumed), :107/:115/:121 (hoist + focus banner data) · frontend/src/features/studio/panels/PlanHubPanel.tsx:72-75 (producer: openPanel('quality-canon', {params:{bookId, focusRuleId: ref.id, focusChapterId}})) · frontend/src/features/studio/host/StudioHostProvider.tsx:52 (generic openPanel(panelId,{focus,title,params}) — the transport, already generic) · frontend/src/features/composition/components/CanonRulesPanel.tsx:11 + hooks/useCanonRules.ts:6 (the write half, fully built, legacy-page-only) · frontend/src/features/studio/panels/useQualityWork.ts:34 (the ONE work gate that prevents the false-clean HIGH from d662bd97d) · frontend/src/features/studio/panels/catalog.ts:270 + QualityHubPanel.tsx:17 (registration sites) · services/chat-service/app/services/frontend_tools.py:402 + contracts/frontend-tools.contract.json:256 (panel_id closed-set enum — 'quality-canon-rules' absent, must be added) · spec 30 line 237 (G-CANON-RULE-CRUD: "This is a port, not a build") · git log QualityCanonPanel.tsx → 557d848cf, d662bd97d, 09f2d29b1, 75360bbd7

### Q-30-TRACKC-UNCOMMITTED-FILES
STALE CONCERN — its premise is false as of HEAD. Track C's D8 has LANDED: `git status --porcelain` and `git diff --stat HEAD` are both EMPTY for all four named files (ToolApprovalCard.tsx, useChatMessages.ts, tool_permissions.py, stream_service.py). D8 committed as 72b5fc895 ("feat(chat,fe): D3 Never allow on the card + D7 route catalog 422 (PO sign-off)"), with 7d2e945ef/bac8802c2 on top. Track C's NEXT run (docs/specs/2026-07-13-track-c-clear.md) does not touch stream_service.py (grep: 0 hits; it cites only tool_permissions.py, as an existing surface) — its remainder is workflow-rack FE, binding UI, the W11 reader, and book/glossary MCP debt. Therefore the §9 rule "DO NOT TOUCH these files / sequence X-10 after Track C lands" is SATISFIED. X-10 is UNBLOCKED and runs in Wave 0's ordinary XS batch (alongside X-1/X-2/X-8/X-9); do NOT hold it.

BUILDER INSTRUCTION (X-10, AN-C2, XS — one file + one test):
1. CODE — services/chat-service/app/services/stream_service.py, inside the `if _ctx_project_id:` branch (currently :3755-3760, right before the unconditional tail at :3761), append:
       book_context_note += (
           " To orient in this project before answering, you may call"
           " composition_package_tree (the project's package/structure tree) and"
           " composition_diagnostics (its ranked open issues)."
       )
   Scope it to the project_id branch ON PURPOSE: both tools are project-scoped, so naming them when there is no project_id invites a call with no valid arg. (Veto-able default: to advertise them on every book turn, move the sentences to the unconditional tail at :3761.)
2. TEST — services/chat-service/tests/test_stream_service_story04.py::TestStudioSurface::test_studio_context_position_pointer_in_system_message (:175; it already flattens the system message into `content` at :212-213 and asserts "a book_id is NOT a project_id" at :217). Add: assert "composition_package_tree" in content; assert "composition_diagnostics" in content. Add the negative to test_no_studio_context_does_not_advertise_studio_tools (:263): the scent is ABSENT when there is no project_id.
3. BUDGET — book_context_note is metered into the `book_note` bucket at stream_service.py:4091. NO test asserts a ceiling on it (test_token_budget.py:165 and test_context_history_router.py:56 use book_note only as a fixture int). ~30 tokens added; nothing to re-tune.
4. SHARED-CHECKOUT HYGIENE (still binding — 3 tracks, 1 branch, 1 checkout): immediately before editing, re-run `git status --porcelain -- services/chat-service/app/services/stream_service.py`; if Track C's CLEAR run has re-dirtied it, stop and coordinate. Stage by enumeration (`git add <the 2 paths>`), NEVER `git add -A`, and remember `git commit -- <path>` commits the WORKING TREE, not the index.

*Evidence:* git status --porcelain / git diff --stat HEAD over the 4 paths = EMPTY (Track C D8 committed at 72b5fc895). Edit site: services/chat-service/app/services/stream_service.py:3750-3764 (book_context_note assembly; project_id branch :3755-3760, unconditional tail :3761-3764); token meter at stream_service.py:4091. Test site: services/chat-service/tests/test_stream_service_story04.py:175-217 (existing system-message substring assertions) and :263. Track C's open run: docs/specs/2026-07-13-track-c-clear.md — grep "stream_service" => 0 hits. Now-stale plan-30 rows: 30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:343 (X-10) and :715 (§9 collision row).

### Q-30-GG4-RETIREMENT-GATE
CONFIRM the constraint AND make it mechanical NOW — it is a buildable Wave-0 slice, not a note. Three concrete instructions:

**(1) Wave 0, new slice `X-GG4-GATE` (XS, FE-only, no backend).** Create `frontend/src/features/studio/panels/__tests__/legacyEditorRetirementGate.test.ts`, copying the fs-read pattern of its sibling `dockablePanelHygiene.test.ts` (`readFileSync` + `resolve(__dirname, ...)`, vitest `describe/it/expect`). Body:
```ts
const APP = readFileSync(resolve(__dirname,'../../../../App.tsx'),'utf-8');
const CATALOG = readFileSync(resolve(__dirname,'../catalog.ts'),'utf-8');
const LEGACY_ROUTE = '/books/:bookId/chapters/:chapterId/edit';
// GG-4: every panel that PORTS a feature living ONLY on ChapterEditorPage.
const PORTED_PANELS = [
  'quality-canon-rules','quality-corrections','quality-heal','progress', // Wave 1
  'motif-library',                                                        // Wave 3
  'arc-templates',                                                        // Wave 4
  'style-voice','reference-shelf','divergence',                           // Wave 6
];
const missing = PORTED_PANELS.filter(id => !CATALOG.includes(`id: '${id}'`));
it('GG-4: the legacy chapter editor stays mounted until every port lands', () => {
  if (missing.length === 0) return;            // gate OPEN — retirement is now *permitted*
  expect(APP, `GG-4 VIOLATION: you removed the legacy route while these ports are still missing from catalog.ts: ${missing.join(', ')}. Deleting ChapterEditorPage now DELETES shipped features (style/voice, references, motif library, arc templates, divergence, progress, correction capture, polish/self-heal). See spec 30 §GG-4 + Wave 6.`).toContain(LEGACY_ROUTE);
  expect(existsSync(resolve(__dirname,'../../../../pages/ChapterEditorPage.tsx'))).toBe(true);
});
```
Add a second `it` asserting `PORTED_PANELS.length === 9` (guards a silent list-trim — the way a lazy agent would "pass" this gate). Put a file header saying: *deleting THIS TEST is itself the retirement act and requires the spec-16 M1 close-out row.* Verify by effect: `npx vitest run legacyEditorRetirementGate` must go RED when you locally comment out `App.tsx:134`, and green when restored — paste both outputs.

**(2) The gate is self-expiring and PERMISSIVE, not forcing.** When all 9 ids are in `catalog.ts` (i.e. Wave 6 closes), the test early-returns and retirement is *unlocked* — it does NOT then demand the deletion. **DEFAULT CHOSEN (PO may veto):** retirement stays a deliberate, separately-scoped slice, because the code already reversed the premise — `ChapterEditorPage.tsx:9-10` records *"spec 16 Phase 4b, 2026-07-05: kept indefinitely, not deleted"*, and spec 16's M6 (mobile shell — the page owns `MobileEditorShell`, dockview has no narrow-viewport pattern) is an unresolved product call. So Wave 6 close ⇒ 00C Q-4/Q-5/Q-6 become *eligible*, not *automatic*.

**(3) Wave 6 Definition of Done gains two literal steps:** (a) `legacyEditorRetirementGate.test.ts` reports gate OPEN (all 9 ids present); (b) fix the stale premise the audit found: spec 16 P1 left the `editorBridge` singleton in place *because* the page was being retired — that premise is dead, so either finish the `applyProposedEdit`/Tier-4 migration (spec 08 steps 1-3) or write a defer row naming the reversal. Also amend `16_chapter_editor_parity_and_retirement.md`'s M1 in place ("Studio is the SOLE surface") to point at spec 30 GG-4 — do not leave two docs disagreeing.

*Evidence:* frontend/src/App.tsx:134 (legacy route still mounted) · frontend/src/pages/ChapterEditorPage.tsx:1-19 (the entire enforcement is the prose banner; line 9-10 already records the Phase-4b "kept indefinitely, not deleted" reversal that spec 16's M1 headline contradicts) · frontend/src/features/studio/panels/__tests__/dockablePanelHygiene.test.ts:1-31 (the exact readFileSync-over-source hygiene-test precedent to clone; proves this guard is a ~40-line file, not new infrastructure) · frontend/src/features/studio/panels/catalog.ts:114-271 (grep confirms none of the 9 port-target ids exist yet ⇒ the gate computes CLOSED today from source)

### Q-30-BE9C-CORRECTION-STATS-DENOMINATOR
BUILD the root allowlist — but the membership in spec 31 F-Q3a ("exactly draft_scene, draft_chapter, stitch_chapter") is WRONG by two live call sites. Ship this instead:

**1 · The constant (root).** `services/composition-service/app/db/repositories/generation_corrections.py`, next to `_DASHBOARD_MODES` (line 34):
```python
# BE-9c — the ONLY ops a human-gate correction can be captured on (the draft flywheel).
# Every other generation_job op (quality_report, self_heal_propose, promise_coverage,
# decompose_preview, plan_pipeline, plan_forge_*, conformance_run, mine_motifs,
# analyze_reference) is a MACHINE pass with no human gate: counting it in `generations`
# inflates the denominator ⇒ a false ~100% accept_rate on the panel that exists to be
# the quality signal. `continue` (inline ghost) is a generation with NO capture surface
# → also out. Selection edits stay excluded by the input predicate below (belt+braces).
CORRECTABLE_OPERATIONS = ("draft_scene", "adapt_scene", "draft_chapter", "stitch_chapter")
```
**2 · The query.** In `correction_stats` (same file, lines 180-210), add ONE line to the WHERE, immediately after `WHERE j.project_id = $1`:
```sql
              AND j.operation = ANY($2::text[])
```
and pass `list(CORRECTABLE_OPERATIONS)` as `$2`. **KEEP** the existing `AND NOT coalesce((j.input->>'selection_edit')::boolean, false)` line and its comment verbatim (line 206) — do not "simplify" it away now that rewrite/expand/describe are also out by allowlist; it is the documented /review-impl fix and the defense-in-depth layer.

**3 · Why `adapt_scene` is IN (the spec's 3-tuple is a silent-undercount bug).** `frontend/src/features/composition/components/ComposeView.tsx:73` sends `operation: 'adapt_scene'` through the SAME `auto.mutate` / `stream.start` paths whose accept/regenerate/reject handlers call `correction.mutate` (`ComposeView.tsx:106-113` and `:136-140`). adapt_scene jobs therefore already carry REAL correction rows. The 3-tuple drops those corrections from the numerator AND their jobs from the denominator — it under-reports the dị-bản (M1 divergence) path, which is the exact class of lie BE-9c exists to kill.

**4 · Why `continue` is OUT.** `useInlineGhost.ts:60` streams `operation:'continue'` (mode=cowrite), and the hook owns its own stream with NO `useCorrection` import (header: "No new BE") — Accept/Discard capture nothing. Allowlisting it would inflate the *cowrite* denominator exactly as quality_report inflates auto. **Coupling note for a future builder:** if ghost Discard is ever wired to `POST /jobs/{id}/correction`, add `"continue"` to `CORRECTABLE_OPERATIONS` in that same commit.

**5 · BE-9c′ MUST be a SUPERSET of the allowlist — a narrower Literal 422s two shipped flows.** When closing `operation` to a Literal:
- `GenerateBody` (`engine.py:98`) → `Literal["draft_scene","adapt_scene","continue"] = "draft_scene"`
- `GenerateChapterBody` (`engine.py:141`) → `Literal["draft_chapter"] = "draft_chapter"`
- MCP `composition_generate` args (`app/mcp/server.py:1356`, today `operation: str | None = None`) → the same union as an enum'd Literal (mcp-tool-io IN-1).
A Literal of just `draft_scene`/`draft_chapter` breaks ComposeView's **Adapt** button and the **✦ Continue** ghost — both live. Invariant to write into the code comment: **allowlist ⊆ Literal set**, and `continue` is in the Literal but NOT the allowlist.

**6 · Close the what-if hole in the SAME commit (do NOT defer it — it is 4 lines).** `useWhatIfTakes.ts:36` fires `operation:'draft_scene'` via `generateAuto` (mode='auto') and *deliberately* captures no correction ("ephemeral take", `useWhatIfTakes.ts:20-22`). Those jobs are op-indistinguishable from real drafts, so they survive the allowlist and still inflate `auto`. Mirror the `selection_edit` shape: add `ephemeral: bool = False` to `GenerateBody` (`engine.py:~114`); stamp `"ephemeral": body.ephemeral` into `job_input` (`engine.py:455-459`); send `ephemeral: true` from `useWhatIfTakes.ts:36` (thread through `generateAuto`, `frontend/src/features/composition/api.ts:398-411`); add `AND NOT coalesce((j.input->>'ephemeral')::boolean, false)` next to the selection_edit predicate.

**7 · Tests** — `services/composition-service/tests/integration/db/test_repositories.py`, beside `test_correction_stats_excludes_selection_edits` (line 2052); file already carries the pg xdist group. Run: `python -m pytest tests/integration/db/test_repositories.py -q -k correction_stats`.
- `test_correction_stats_excludes_noncorrectable_operations` — seed 6 completed mode="auto" jobs (`quality_report`, `self_heal_propose`, `promise_coverage`, `plan_pipeline`, `decompose_preview`, `conformance_run`) + ONE completed `draft_scene` auto job with one `edit` correction → assert `auto.generations == 1`, `edit_rate == 1.0`, `accept_rate == 0.0`. **This test must RED on HEAD** (today: generations==7, edit_rate≈0.14) — that red is the proof the bug was real.
- `test_correction_stats_counts_adapt_scene` — completed `adapt_scene` cowrite + a `reject` correction → `cowrite.generations == 1`, `reject_rate == 1.0`.
- `test_correction_stats_excludes_inline_continue_and_ephemeral` — a completed `continue` cowrite job + a completed `draft_scene` auto job with `input={"ephemeral": True}` + one real completed `draft_scene` cowrite → `cowrite.generations == 1`, `auto.generations == 0`.
- The 4 existing correction_stats tests (2012/2052/2072/2096) use `draft_scene`/`rewrite`/`expand` only → stay green unchanged.
Also add a 422 test for BE-9c′ asserting `operation:"adapt_scene"` and `"continue"` are ACCEPTED (guards the regression where a builder narrows the Literal to the allowlist).

Default I am picking (veto-able): `stitch_chapter` stays IN, per spec 31's table — it produces the assembled chapter prose the author gates. QC-5 (self-heal corrections) stays OUT of the allowlist, unchanged, as OQ-2 already records.

*Evidence:* ROOT: services/composition-service/app/db/repositories/generation_corrections.py:180-210 — `FROM generation_job j ... WHERE j.project_id = $1 AND NOT coalesce((j.input->>'selection_edit')::boolean,false) GROUP BY j.mode` (no operation filter). INFLATORS (all mode="auto", same project): routers/plan.py:246 self_heal_propose, :312 quality_report, :417 promise_coverage, :548 plan_pipeline, :612 decompose_preview; routers/actions.py:724 conformance_run (real project_id). MISSED-BY-SPEC CORRECTABLE OP: frontend/src/features/composition/components/ComposeView.tsx:73 (`operation: 'adapt_scene'`) feeding the correction capture at ComposeView.tsx:107 and :137. NON-CORRECTABLE GENERATION: frontend/src/features/composition/hooks/useInlineGhost.ts:60 (`operation:'continue'`, no useCorrection) and useWhatIfTakes.ts:20-22,36 (draft_scene, "no correction is captured for an ephemeral take"). OPEN CONTRACT (BE-9c′): engine.py:98 / :141 `operation: str`, app/mcp/server.py:1356 `operation: str | None`. Existing tests: tests/integration/db/test_repositories.py:2012-2100.

### Q-30-SPEC29-PARALLEL-LANE
START IT NOW, as its own lane, concurrently with plan-30's spec-writing phase. This is a work item, not an open question — the code confirms all 4 defects still live at HEAD, and nothing gates it.

WHY IT IS NOT BLOCKED BY PO-4 (read this before objecting): PO-4 seals "write ALL detail specs (31-38) + ALL HTML drafts FIRST; no implementation this phase" — its consequence sentence scopes it to the wave build ("planned as one piece … once every spec and draft is on disk"). The SAME PO-approved doc says twice that spec 29 runs in parallel: §7 line 474 "Independent of all 8 waves. Start it whenever a lane is free" and §9 line 804 "In parallel, any time: kick off spec 29". 00C Q-1: entry condition "None — unblocked now", spec state "build-ready". GG-6's spec+draft gate is a per-WAVE gate for NEW panels; spec 29 adds no panel (it repairs the existing `translation` catalog row, frontend/src/features/studio/panels/catalog.ts:229), so the absent HTML draft is not a gate. No contradiction with §0.

LANE SETUP: branch `feat/translation-repair` (do NOT reuse any `lane/*` name — 7 stale worktrees exist). Owns exactly: frontend/src/pages/book-tabs/{TranslationTab,TranslateModal}.tsx, frontend/src/features/translation/**, frontend/src/lib/languages.ts, services/translation-service/**, and (Phase C only) book-service's book read + frontend/src/features/books/api.ts. It must NOT touch chat-service/stream_service.py, ToolApprovalCard.tsx, useChatMessages.ts (Track C is mid-edit there), nor PlanDrawer.tsx / plan-hub (book-package track). Ship as 3 commits = spec 29's Phase A / B / C; each wave-equivalent ends with a literal `/review-impl` step + POST-REVIEW before it closes (binding PO policy #2).

PHASE A — frontend-only, no contract change, ship first (this is what the user reported):
1. T8/D6 — TranslationTab.tsx:300-305: pass `preselectedChapterIds={[...selectedChapters]}`; ADD an optional `preselectedLang?: string` prop to TranslateModal (the ids prop already exists at TranslateModal.tsx:31) and pass the clicked column's language. Keep TranslateModal.tsx:205-209's guard so a language change does not re-derive the default selection when a preselection was given.
2. T1/D1 — header CTA `Translate…` (unscoped; the modal owns scope). Restructure TranslationTab.tsx:251-260 so the header renders ABOVE the `if (loading)` / `if (error)` early returns; the table region owns loading/error/empty. Enabled whenever chapters.length > 0; independent of coverage. Keep the empty-state CTA (D2). The vestigial `Plus`/`AlertCircle` imports (line 6) become live.
3. T2/D3/D4/D5 — matrix renders one row per CHAPTER left-joined onto coverage (move toggleAllChapters:216-220, allSelected:271, summaryCounts:224-237, staleChapterIds:97-112, showing_chapters:472 off `coverage.coverage` onto the chapter list); paginate with the existing usePagedList+Pager at 100/page; selection is a Set<chapter_id> surviving page changes; orphan coverage rows get the "N translations belong to trashed chapters" footnote, never a silent drop.
4. T5/D7/D8 — wrap TranslateModal.tsx:113-155's loads in an AbortController + timeout, propagating abort into fetchAllChapters' paging loop (TranslateModal.tsx:37-53); render the language <select> + ModelPicker IMMEDIATELY (they need no network); seed book settings behind a `seeded` ref that never clobbers a user-touched field; scope the spinner to the chapter checklist with an inline error + Retry; submit stays ENABLED when preselectedChapterIds is present even if the chapter list fails.
5. T4/T10/D9 — typed errors: retryable (5xx/network) vs terminal (403/404). Never render `(error as Error).message` (that is what leaked the proxy string). A chapter-fetch failure must NOT render as "No chapters to translate" (TranslationTab.tsx:262-266).
6. D10 first half — a readable toast on the EDIT-grant 403 at job create.
Tests (assert the EFFECT, per checklist-is-self-report-enforce-by-tests): preselect reaches the modal and the footer reads "Translate 2 selected" ENABLED; a fully-translated book still yields an enabled force-retranslate for the selection; a coverage fixture with fewer rows than chapters renders one row per chapter; 250 chapters paginate and selection survives a page change; a HANGING (not just rejecting) API produces a timeout + Retry; a 403 renders no Retry; a language picked before getBookSettings resolves survives.

PHASE B — degraded mode + parity: T6 (ChapterTranslationsPanel loadAll:66-96 — listChapterVersions has no .catch), T7, D11 (EditorPanel.tsx:351 adopts the bare `translation-versions` id, killing the double dock tab), S1-S5.

PHASE C — contract + hygiene (first cross-service phase ⇒ carries the live-smoke gate):
- D13: WRITE `services/translation-service/app/lib/languages.py` mirroring frontend/src/lib/languages.ts + the parity test the source comment (languages.ts:9-10) already promises but never built. This is UNBUILT WORK, not a blocker (CLAUDE.md anti-laziness rule).
- Normalize-then-validate on write ("VI"→"vi" accept; "Vietnamese"→400 invalid_target_language). Turn services/translation-service/app/mcp/server.py:220's free-string `target_language` into a registry-generated enum/Literal (closed-set ⇒ enum, mcp-tool-io IN-*). Reads must keep tolerating unknown legacy codes.
- Consolidate all 3 FE language inputs (LanguagePicker, TranslateModal's hand-rolled <select> :320-329, BatchTranslateDialog's free-text input) onto LanguagePicker fed by TRANSLATION_TARGETS (languages.ts:73 — currently imported by nobody). Fixes S7 for free.
- T9/D10 second half: add `my_grant_level: 'view'|'edit'|'owner'` to the book read (zero occurrences repo-wide today — build it in book-service and surface it on the Book type in frontend/src/features/books/api.ts) and DISABLE the affordance WITH A REASON (never hide it — a hidden button is indistinguishable from the T1 bug).
- Live smoke, both states: healthy stack AND `docker stop infra-translation-service-1`. A mock-only pass cannot see T4/T5/T6.

DEFER ROW (already earned, carry it forward): D-TRANSL-LANG-BACKFILL — merge legacy free-text target_language into canonical codes across chapter_translations / active_chapter_translation_versions / translation_chapter_memos. Gate #2 (large/structural: needs a which-version-wins rule + version_num renumbering). Target: after Phase C lands write-side validation.

FREE RIDE while in these files: fix spec 29's stale H1 (`# 24 — Translation surfaces…` → `# 29 — …`), the plan-30 X-8 doc-hygiene item, so it stops colliding visually with 24_plan_hub_v2.md.

DEFAULT THE PO CAN VETO: Phase A ships and is smoked BEFORE Phase B/C start, because it alone closes the user's original report ("no translate button / pressing it does nothing / no language modal") and is frontend-only.

*Evidence:* TranslationTab.tsx:300-305 (<TranslateModal> with no preselectedChapterIds) vs TranslateModal.tsx:31 (`preselectedChapterIds?: string[]` — the prop exists); TranslateModal.tsx:37-53 (fetchAllChapters paging loop, no AbortController/timeout) + :113-155 (.catch(()=>null)); services/translation-service/app/mcp/server.py:220 (`target_language: Annotated[str, "The target language code (e.g. 'en')."]` — free string, closed-set⇒enum breach); grep `my_grant_level` across *.ts/*.tsx/*.py/*.go = ZERO hits; frontend/src/lib/languages.ts:73 (TRANSLATION_TARGETS exported, imported by nobody) + :9-10 (the "Backend mirrors this in Python … parity test" comment that was never built — no languages.py exists); catalog.ts:229 (the `translation` panel row spec 29 repairs — no NEW panel, so GG-6's spec+draft wave gate does not apply); 30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:474 ("Start it whenever a lane is free") and :804 ("In parallel, any time: kick off spec 29") vs :22 (PO-4, scoped to specs 31-38); 00C_POST_ARCHITECTURE_QUEUE.md:33 (Q-1 entry condition "None — unblocked now", spec state "build-ready"); `git worktree list` = 7 stale lane/* trees, none in book-tabs or translation-service.

### Q-30-OOS-MISSING-E2E
DECIDE — do BOTH: (A) close the 10-panel gap once with ONE generic spec (it is cheaper than the defer row and it auto-covers every future wave), and (B) keep a per-wave behavior smoke in each wave's DoD. Concretely:

(A) WAVE 1, SLICE "E2E-LIVENESS" (new file, ~70 LOC, no other file changes):
Create `frontend/tests/e2e/specs/studio-panel-catalog-liveness.spec.ts`:
- `import { STUDIO_PANELS } from '../../../src/features/studio/panels/catalog';` (precedent for importing src from a spec: `frontend/tests/e2e/pages/StudioPage.ts:2` imports `../../../src/features/studio/types`) and `import en from '../../../src/i18n/locales/en/studio.json';`
- `beforeAll`: `getAccessToken` + `createBook` from `../helpers/api` (afterAll `trashBook`); `beforeEach`: `loginViaUI` from `../helpers/auth` — same preamble as `kg-panels.spec.ts:1-37`.
- Body: `for (const p of STUDIO_PANELS.filter(p => !p.hiddenFromPalette))` → `test(\`${p.id} opens via the Command Palette and mounts\`)`: `const studio = new StudioPage(page); await studio.goto(bookId); await studio.openPanel(p.id, <title from en.panels[p.id].title>); await expect(page.getByTestId(TESTID[p.id] ?? \`studio-${p.id}-panel\`)).toBeVisible();`
- `const TESTID: Record<string,string>` override map for the ONLY 4 palette-openable panels whose root testid deviates from the convention: `knowledge → 'studio-knowledge-hub-panel'` (KnowledgeHubPanel.tsx:41), `quality → 'studio-quality-hub-panel'` (QualityHubPanel.tsx:31), plus `planner` and `glossary-unknown` (resolve their actual root testid by grep — they are re-exported from outside `panels/`; do NOT rename existing testids, they are tour anchors).
- This yields 57 live tests today and covers all 10 orphans in one shot: `jobs-list` (JobsListPanel.tsx:25), `books` (BooksBrowserPanel.tsx:55), `leaderboard-books/-authors/-translators/-trending`, `chapter-browser` (ChapterBrowserPanel.tsx:29), `plan-hub` (PlanHubPanel.tsx:161) — the exact spec-24-H8.2 "no Playwright targets plan-hub anywhere" hole — plus `scene-browser`/`scene-inspector`.
- Crucially it is DATA-DRIVEN off `catalog.ts`, so every panel a later wave registers (the §8.0 ledger) is smoked automatically with zero per-wave work — this is the E2E twin of `panelCatalogContract.test.ts`.
- Hidden-from-palette panels (`job-detail`, `book-reader`, `json-editor`, …) are intentionally excluded: they are not bare-id openable (DOCK-6 exception).

(B) PER-WAVE DoD (add as step 10 of the GG-8 registration checklist in spec 30 §8, right under the existing "Then VERIFY BY EFFECT" paragraph at line 529):
1. `studio-panel-catalog-liveness.spec.ts` green — it will already contain the wave's new panels (mount proof, free).
2. ONE behavior spec per wave: `frontend/tests/e2e/specs/studio-wave<N>-<name>.spec.ts`, modeled on `kg-panels.spec.ts` (seed real data via `helpers/api`, drive the panel's primary read + its primary write through the real backend, assert the effect). A mount-only test is NOT the wave's smoke.
3. ≥1 agent-loop assertion in that spec: the model/tool path `ui_open_studio_panel {panel_id:"<new-id>"}` actually mounts the dock tab (precedent: `frontend/tests/e2e/specs/frontend-tools-liveness.spec.ts`) — this is the `agent-gui-loop-needs-live-browser-smoke-not-raw-stream` lesson.
4. VERIFY evidence string MUST literally contain: `live smoke: npx playwright test tests/e2e/specs/<file> — N passed`. Run against the BAKED build (`:5174`, rebuild the FE image first — stale image = false green) or `PLAYWRIGHT_BASE_URL=http://localhost:5199 npx playwright test` with `vite dev`. A curl/API-only smoke does NOT satisfy this DoD (that was pillar-24's exact miss).
5. `/review-impl` at wave close, per the run policy.

DEFAULT NOTE for the PO (veto-able): this overrides plan 30 §7's out-of-scope line "do not retro-fit the old ones here" — not by adding 10 bespoke specs, but because the generic catalog-driven spec makes the retro-fit a free byproduct of the mechanism the waves need anyway. It touches no §0 SEALED decision (PO-1..4). If the PO prefers the debt to stand, drop slice (A) and keep (B) — but then jobs/books/leaderboard/chapter-browser/plan-hub will never be smoked, because no wave in 31–38 touches them.

*Evidence:* docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:491 ("The 10 shipped panels with no live E2E (14b + 15a) | Real debt…") and :529 ("Then VERIFY BY EFFECT — a live browser smoke that ui_open_studio_panel {panel_id:"<id>"} actually mounts the dock tab"); harness that makes it cheap: frontend/tests/e2e/pages/StudioPage.ts:43-53 (openPanel via real Command Palette) + frontend/tests/e2e/specs/kg-panels.spec.ts:40-66 (13-panel parametrized live loop) + frontend/playwright.config.ts:3 (PLAYWRIGHT_BASE_URL ?? http://localhost:5174); the orphans already carry the required selectors: frontend/src/features/studio/panels/JobsListPanel.tsx:25, BooksBrowserPanel.tsx:55, ChapterBrowserPanel.tsx:29, PlanHubPanel.tsx:161, and catalog rows catalog.ts:167-190; audit of all 57 palette-openable rows shows only planner/glossary-unknown/knowledge/quality deviate from data-testid="studio-<id>-panel".

### Q-30-SPEC27-B1-B2-SCHEMA-TAINT
CONFIRM THE FOLD, and sequence it FIRST in Wave 5 — not last. Plan 30 §Wave 5 already says "Also fold in: spec 27-B1/B2 … contract-hygiene debt in the same files" (30:420-421), and spec 27 already specifies the exact diff (27:433-436, slices B1/B2 at 27:513-514). Nothing here needs a new decision; it needs a builder instruction. Here it is.

SEQUENCING (the one change to the plan's framing): do B2 FIRST, before the Pass Rail panel. `plan_pass_artifacts.schema.json` is the type contract between Wave 5's BE-3 (artifact read — "exists in NO transport") and the `plan-passes` panel that renders it. Writing it first de-risks the wave; writing it last means the panel and the route agree by luck. Call it slice W5-B0.

SLICE W5-B0a (= 27-B1) — unfixture the contracts. NOT runtime-validated (no jsonschema loader anywhere in services/composition-service/app/), so this cannot break runtime. Zero risk.
1. `contracts/plan-forge/planner_state.schema.json` — DELETE line 7 (`"required": ["PA","HA","CD","THR"]`). DELETE the four `PA`/`HA`/`CD`/`THR` property blocks (lines 10-30). ADD `"patternProperties": {"^[A-Z]{2,4}$": {"type":"number","minimum":0}}`. KEEP `additionalProperties: false`.
   ⚠ TRAP: `tier` MUST STAY inside `properties` — it is lowercase, does not match `^[A-Z]{2,4}$`, and with `additionalProperties:false` a naive wholesale swap of `properties`→`patternProperties` REJECTS every doc carrying a tier. Change `tier` only in kind: `{"type":["string","null"]}` — drop the `["baseline","tier_1".."tier_4"]` enum (line 33); that ladder is the POC novel's cultivation system, not a platform concept.
2. `contracts/plan-forge/novel_system_spec.schema.json`:
   - `VariableDef` (lines 109-123): ADD optional `"initial": {"type":"number","default":0}`. Do NOT add it to `required`.
   - Line 197: DELETE `"planner_state_init": { "$ref": "planner_state.schema.json" }` from `CompileTargets`. This is the load-bearing one — see EVIDENCE: the code already stopped emitting it, so the contract is currently LYING about compile's output.
   - Line 168: `"coupled_to_realm": {"type":"boolean","const":false}` → drop `const:false`, leave `{"type":"boolean"}`. (`realm` is the fixture's world-model.)
   - `version` stays `const: 1` — additive-optional fields do not fork the IR.
3. `services/composition-service/app/engine/plan_forge/compile.py`:
   - Line 66: `v["code"]: _DEFAULT_VARIABLE_INITIAL` → `v["code"]: v.get("initial", 0)`. Delete the now-dead `_DEFAULT_VARIABLE_INITIAL` (line 16) and the stale BPS-21 comment block (lines 13-16) that says the change is untracked.
   - Line 69: DELETE `planner_state["tier"] = "baseline"`. THIS IS A SECOND FIXTURE CONSTANT THE SERVICE-SIDE SEVERING MISSED — it stamps every user's book with the POC novel's ladder baseline. Emit `tier` only if the spec declares one; otherwise omit the key.
4. TEST (extend `services/composition-service/tests/unit/test_plan_forge_no_fixture_constants.py`, which already owns this bug class): a spec declaring variables `["MP","XYZ"]` with `initial: 50` on one compiles to `planning_package.planner_state == {"MP":50,"XYZ":0}` — no `PA`/`HA`/`CD`/`THR` key, no `tier` key. Assert the two schema files contain none of the strings `"PA"`,`"HA"`,`"CD"`,`"THR"`,`planner_state_init`. That last assert is what stops a future agent re-adding the $ref "for completeness".

SLICE W5-B0b (= 27-B2) — CREATE `contracts/plan-forge/plan_pass_artifacts.schema.json`. One `definitions` entry per pass-artifact kind: `MotifPlan`, `CastPlan`, `WorldPlan`, `BeatPlan`, `CharArcPlan`, `ScenePlan`, `HealReport`, `LinkReport`, each mirroring the engine dataclass (`ProposedChar`, `CharacterArc`, `ChapterTension`, `DecomposeResult`, `PlanHealReport`). Same posture as its siblings: referenced by tests, NOT runtime-enforced. Add the row to `contracts/plan-forge/README.md` (its table, lines 5-13, is the index and will otherwise go stale). Test: a mirror test asserting every `PlanArtifactKind` enum member has a matching `definitions` entry — so adding a 9th pass kind without a schema reds the suite.

SCOPE FENCE (prevents a 3am stall): PF-14 also says "`planner_state` gains its first reader" — pass 6's prompt including the variable ledger. That is the ENGINE half and it lands with the scenes pass (27 V2-C), NOT with this contract slice. W5-B0 is schema + compile + tests only. Do not block it on the pass runner existing.

WHY NOT DEFER: fails all 5 CLAUDE.md gates. In-scope (Wave 5 owns these files), not structural (4 files, no migration, no cross-service contract), prerequisites exist today, nothing external blocks it, and it is not a won't-fix — the contract actively misdescribes shipped code. Writing a defer row costs more than the fix.

*Evidence:* TAINT STILL PRESENT (contract side):
• contracts/plan-forge/planner_state.schema.json:7 — `"required": ["PA","HA","CD","THR"]`; :8 `additionalProperties:false`; :10-30 the four fixture var blocks; :33 `enum ["baseline","tier_1".."tier_4"]` (the POC novel's cultivation ladder).
• contracts/plan-forge/novel_system_spec.schema.json:109-123 — `VariableDef` has NO `initial` (required: code/name/range/transition_rules only).
• contracts/plan-forge/novel_system_spec.schema.json:168 — `"coupled_to_realm": {"type":"boolean","const":false}`.
• `ls contracts/plan-forge/` returns 7 schemas + README — `plan_pass_artifacts.schema.json` is ABSENT. Confirmed.

THE CONTRACT NOW CONTRADICTS THE CODE (the finding the question understates):
• contracts/plan-forge/novel_system_spec.schema.json:197 — `CompileTargets` still `$ref`s `"planner_state_init"` …
• …but services/composition-service/app/engine/plan_forge/compile.py:146-153 — "`planner_state_init` and `working_memory_charter` were emitted here and read by NOTHING … Dropped per DA-13"; `return` at :149-153 yields only `glossary_seeds` / `outline_skeleton` / `planning_package`.
• services/composition-service/tests/unit/test_plan_forge_no_fixture_constants.py:124-125 — `assert "planner_state_init" not in compiled`. So the service side is severed AND test-locked; the contract is stale in the strong sense (describes an output that does not exist).

PLANNER_STATE IS STILL LIVE (so B1 is not editing a dead payload):
• compile.py:65-69 builds `planner_state`, :131 embeds it in `planning_package`. Only the standalone `planner_state_init` target died.
• compile.py:16 `_DEFAULT_VARIABLE_INITIAL = 0` + :66 forces every variable to 0 (the exact gap `VariableDef.initial` closes).
• compile.py:69 `planner_state["tier"] = "baseline"` — a SECOND fixture constant the severing missed, unmentioned in the question.

ZERO RISK TO FIX: grep for `jsonschema|schema.json` across services/composition-service/app/ → EMPTY. These contracts are not runtime-validated (matches spec 27:433 "Not runtime-validated (verified BPS-21)").

ALREADY-DECIDED SOURCES: docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:420-421 ("Also fold in: spec 27-B1/B2 … contract-hygiene debt in the same files"); 27_planforge_v2_compiler.md:433-436 (exact contract-change table), :513-514 (slices B1/B2), :216 (PF-14). No §0 PO-1..4 decision touches plan-forge contracts — no sealed-decision conflict.

### Q-30-SPEC12-JSON-PROVIDER-GATE
BOTH halves, in Wave 5. No new design work — half A is already written; half B is a small, fully-specified new slice.

**A · Item 5 closes in Wave 5 — it is already specced, do not re-design it.** Build `35_planforge_studio.md:361-395` (R1 + PS-9) verbatim: BE-3 route `GET /books/{book_id}/plan/runs/{run_id}/artifacts/{artifact_id}` wrapping the existing `PlanRunsRepo.artifacts_by_ids(book_id, run_id, ids)` (plan_runs.py:265 — the run JOIN *is* the tenancy check); FE provider `loreweave.plan-artifact.v1` with composite `resourceId = "{runId}:{artifactId}"` split inside the provider; add `readOnly?: boolean` to `JsonDocumentProvider`/`DocumentHandle`/`JsonEditorPanel` (it exists at NO layer today — a provider whose `save()` no-ops is this repo's `silent-success-is-a-bug` class); `PlanRunView.tsx:52-57` artifact rows become buttons → `host.openPanel('json-editor', { params: { docType, resourceId } })`.

**B · Add the mechanical guard (new Wave 5 slice, size S, ~3 files) — the gate stops being self-report.** The reason KG and Translation could silently skip item 5 is that registration is imperative and view-lazy (`ManuscriptUnitProvider.tsx:28`, `EntityEditorModal.tsx:7`) and NOTHING asserts the set of registered types. Fix, mirroring the existing `useStudioEffectReconciler.ts:18-21` barrel pattern:

1. NEW `frontend/src/features/studio/documents/ledger.ts` — `export const JSON_DOCUMENT_LEDGER: { cycle: string; status: 'REGISTERED'|'DECLINED'|'OPEN'; type?: string; reason: string }[]` with one row per spec-12 cycle: chapter-editor → REGISTERED `loreweave.manuscript-unit.v1`; glossary → REGISTERED `loreweave.glossary-entity.v1`; wiki → DECLINED (markdown body, not a JSON document — the conscious call already on record); kg-ontology → OPEN (reason + target: Wave 8); translation → OPEN (reason + target: the spec-29 parallel lane); planforge → REGISTERED `loreweave.plan-artifact.v1` (this wave).
2. NEW `frontend/src/features/studio/documents/providers.ts` — `registerAllJsonDocumentProviders()` calling every registrar (the 2 existing + plan-artifact); call it once from the studio host mount. Existing lazy call sites stay (idempotent `registered` guards already present); registration ≠ binding, `open()` still throws its clear unbound error.
3. NEW `frontend/src/features/studio/documents/__tests__/providerLedger.test.ts` — 4 assertions, all mechanical: (a) after `registerAllJsonDocumentProviders()`, every REGISTERED row's `type` is returned by `getJsonDocumentProvider(type)` (proves REGISTERED, not merely defined — the exact failure spec 35 PS-9 §3 warns about); (b) every type in `listJsonDocumentProviders()` maps to exactly one REGISTERED row (no unlisted drift); (c) `import.meta.glob('/src/**/documents/*Document.ts', { eager: true })` — every module exporting `/^register\\w*DocumentProvider$/` must have its type present after the barrel runs (an orphan provider file that nobody imports REDs); (d) every DECLINED/OPEN row has a non-empty `reason` (silence is no longer a legal state).
4. EDIT `docs/specs/2026-07-01-writing-studio/12_json_document_standard.md:65` — restate gate item 5 as: *"JSON provider registered for the tool's resource, OR a DECLINED/OPEN row with a reason in `documents/ledger.ts` — enforced by `providerLedger.test.ts`."*

Residual, stated honestly (PO may veto): code cannot detect "a new cycle shipped", so the guard cannot force a cycle to *create* a provider — it forces a cycle to make the call **explicitly and provably**, and reds on every silent drift thereafter. Do NOT retro-build KG/Translation providers in Wave 5 (out of scope, CLAUDE.md gate 1) — they land as OPEN ledger rows carrying their target wave. Per the run policy, `/review-impl` runs at Wave 5 close and this slice is in its Definition of Done.

*Evidence:* frontend/src/features/studio/documents/registry.ts:10 (`registerJsonDocumentProvider` — the only mechanism) · only 2 call sites repo-wide: frontend/src/features/studio/manuscript/unit/manuscriptUnitDocument.ts:228 and frontend/src/features/glossary/documents/entityDocument.ts:203, each invoked lazily from a view (ManuscriptUnitProvider.tsx:28, EntityEditorModal.tsx:7) · frontend/src/features/studio/documents/__tests__/registry.test.ts:19 registers a FAKE type only — no test asserts the real type set, which is why items 5 could be skipped silently · docs/specs/2026-07-01-writing-studio/12_json_document_standard.md:53-68 (the MANDATORY 6-point gate; item 5 at :65) · docs/specs/2026-07-01-writing-studio/35_planforge_studio.md:361-395 (R1 + PS-9 — item 5's close already specced in build detail, incl. the missing `readOnly` at every layer and the "a provider must be REGISTERED FROM SOMEWHERE" hazard) · services/composition-service/app/db/repositories/plan_runs.py:265 (`artifacts_by_ids` — BE-3's already-scoped repo method) · frontend/src/features/studio/agent/useStudioEffectReconciler.ts:18-21 (the existing registrar-barrel precedent to mirror)

### Q-30-COMPACTION-BREAKER
DO NOT file the P1 defect row — its premise is factually false. (1) CORRECT spec 30's claim: microcompact, hard-truncate, and the compaction failure signals ALL exist. The audit's "0 grep hits" ran against services/ and missed the T3.3b kernel move — services/chat-service/app/services/compaction.py is a re-export SHIM whose docstring says "MOVED to the shared Context Budget kernel". Real impl: sdks/python/loreweave_context/compaction.py — _microcompact() :319 (wired tier 1 at :488), _hard_truncate() :409 (wired tier 3 at :531), CompactionReport.summarize_failed/.overflowed :285-287 (tested: test_compaction.py:381, :397-404). Edit 30_TOOL_GUI_GAP_AUDIT_AND_PLAN's concern row to cite these lines and strike the 🔴. (2) The `compaction_failed` breaker for Agent Mode L3/L4 is ARCHITECTURALLY N/A, not missing: the autonomous authoring-run driver (composition-service/app/services/authoring_run_service.py:1092 run_driver) is a per-unit loop whose DraftingSeam is stateless — draft_chapter(created_by, book_id, chapter_id, plan_run_id, params) (:204-217). No conversation accumulates across chapter units, so compaction never runs on that path and a compaction_failed cannot occur there. Its existing breaker reasons (budget / unit_failed / critic_severe / driver_crashed) are complete for the failures that path can actually produce. Do NOT add a compaction_failed breaker reason to it. (3) 07S §3's interactive half is already shipped: overflow is logged + traced is_error=True (stream_service.py:4491-4502) + surfaced as a status flag to the FE (:4938 → frontend/src/features/chat/types.ts:289). (4) FIX NOW (the one real residual, ~10 lines, one file, CLAUDE.md fix-now default — a defer row would cost more than the fix): the headless SUBAGENT loop shares the same compact_messages call (stream_service.py:4472) but has no FE to see that status flag, so on overflow it drafts blind and returns a plausible poisoned result to its parent — exactly edge #2's hazard in the only place it can still bite. In stream_service.py's compaction block (after :4486 where _compaction.triggered is handled), add: if _compaction.overflowed and subagent_depth > 0, abort the sub-run turn and return an explicit error result ("sub-run aborted: context overflowed compaction; the prompt could not be brought under the model window") INSTEAD of calling the provider — the same no-silent-no-op discipline the file already applies to require_approval at :2574 (which uses the identical `subagent_depth > 0` headless condition). Test: services/chat-service/tests/test_subagent_runtime.py — assert a sub-run whose compaction reports overflowed=True yields result.error and never reaches the provider. This is a chat-service fix, NOT a wave of plan 30 — it does not touch the GUI-gap plan, so keep it out of every wave exactly as the spec instructed.

*Evidence:* sdks/python/loreweave_context/compaction.py:319 (_microcompact — tier 1 EXISTS), :409 (_hard_truncate — tier 3 EXISTS), :285-287 (summarize_failed/overflowed); services/chat-service/app/services/compaction.py:1 ("MOVED to the shared Context Budget kernel (T3.3b)" — the shim that made the audit's grep return 0 hits); services/composition-service/app/services/authoring_run_service.py:204-217 (stateless DraftingSeam ⇒ no conversation in the L3/L4 autonomous path ⇒ compaction_failed cannot occur) + :1092 (run_driver breaker: budget/unit_failed/critic_severe/driver_crashed); services/chat-service/app/services/stream_service.py:4491-4502 + :4938 (overflow traced is_error + surfaced to FE — 07S §3 interactive half shipped), :4472 (subagent shares compact_messages), :2574 (`subagent_depth > 0` = the headless condition to guard on); services/chat-service/tests/test_compaction.py:397-404 (overflow already tested)

### Q-30-PLANNER-CHEAPEST-WIN
YES — wire it in Wave 5, ZERO backend (both routes + service methods are fully implemented). But the spec's "buttons only, zero risk" framing is REFUTED BY CODE and a builder who follows it literally ships a silent no-op on a paid action. Build it as ONE feedback loop, not two orphan buttons.

WHY NOT TWO BARE BUTTONS: plan_forge_service.py:494-500 — refine() with empty `revision` AND empty `focus_paths` returns {"status":"no_change","fidelity_delta":0.0,"diagnosis":None} without resolving a model or doing any work. A bare "Refine" button = user clicks, nothing happens, UI says no_change. That is this repo's own `silent-success-is-a-bug` class. refine REQUIRES an input. And interpret.py:227 returns `draft_revision` as a DICT whose keys (focus_paths/instruction/scope/frozen_paths/expect_contains) are EXACTLY what refine.py:24,285,315,320 reads back — interpret → draft_revision → refine(revision=draft_revision) is the designed pipeline. They are one loop.

BUILD THIS (all files under frontend/src/features/plan-forge/):

1. types.ts — fix 3 drifts (each 422s or crashes a literal wiring):
   - :115 `revision?: string` → `revision?: Record<string, unknown>` (BE PlanRefineRequest.revision is `dict[str,Any]|None`, plan_forge.py:60 — a string 422s).
   - :87 `diagnosis: string` → `diagnosis: string | null` (BE returns None on accepted, plan_forge_service.py:499,569).
   - :120 `apply_mode_hint?: string` → `apply_mode_hint?: 'auto'|'confirm'|'diagnose_only'` (BE Literal, plan_forge.py:67 — closed-set arg must be an enum per SET-1..8).
   - Replace `PlanInterpretation = Record<string, unknown>` with the real shape from interpret.py:220-230: `{version:number; intent:string; confidence:number; focus_paths:string[]; diagnosis:unknown[]; draft_revision:Record<string,unknown>|null; apply_mode:string; clarifying_questions:string[]}`.

2. hooks/usePlanRun.ts — add `interpretation: PlanInterpretation|null`, `refineResult: PlanRefineResult|null`, plus two handlers taking modelRef:
   - `runInterpret(userMessage, modelRef)` → planForgeApi.interpret(...) → setInterpretation.
   - `runRefine(revision, modelRef)` → planForgeApi.refine(...). MUST copy runCompile's ack branch (usePlanRun.ts:169-173): `if (isAck(r)) { setRun(await planForgeApi.getRun(bookId, run.id, token)) } else setRefineResult(r)` — refine returns a 202 ack + sets active_job_id/status=checkpoint when the worker is on (plan_forge_service.py:521-535), so without this the user watches a stale run while a job runs.
   - Guard: never call runRefine with an empty revision (that is the no_change no-op above).

3. components/PlanRunView.tsx — add a "Feedback" block under Validate:
   - Textarea + Send → onInterpret(text). BE requires user_message min_length=1 (plan_forge.py:65) → disable Send on empty.
   - Render the interpretation card: intent, confidence, clarifying_questions, focus_paths.
   - If `interpretation.draft_revision` is non-null, show an "Apply this revision" button → onRefine(interpretation.draft_revision). THIS is refine's real caller; it can never be empty, so it can never no-op.
   - Second refine path (free, and it makes self-check useful): the selfCheck gaps list already renders `g.path` (PlanRunView.tsx:82-88) — add checkboxes and a "Refine selected gaps" button → onRefine({ focus_paths: checked }). focus_paths alone is sufficient for a non-no_change refine (plan_forge_service.py:487-488).
   - Render refineResult: status (applied|no_change|rejected) + diagnosis (nullable).

4. components/PlannerPanel.tsx — `effectiveModelRef` is ALREADY computed at :79 but never passed down. Pass it into PlanRunView and thread it into both handlers. Both interpret and refine are PAID (they resolve a model + call chat: plan_forge_service.py:868,910 and 505,540) → disable both buttons when `!effectiveModelRef`, same as canPropose does at :82. This is what keeps it off the PO's "paid-action that charges for nothing" critical list.

TESTS (extend the existing files): usePlanRun.test.tsx — (a) runRefine on a 202 ack re-fetches the run detail (assert getRun called, run replaced); (b) runInterpret stores the interpretation. PlanRunView.test.tsx — (c) Send is disabled on an empty message; (d) "Apply this revision" appears only when draft_revision is non-null and calls onRefine WITH that dict; (e) "Refine selected gaps" sends {focus_paths:[...]} from the checked gap paths; (f) both buttons disabled when modelRef is empty.

DEFAULT I AM PICKING (PO may veto): do NOT expose a raw revision-dict editor to the user in v1. The user's two doors to refine are the interpret chat box and the self-check gap checkboxes — both produce a well-formed revision dict for free. A hand-typed revision box is the only part that would need design, and it buys nothing the loop above doesn't already give.

Net: still the cheapest win in the plan, still zero backend — but it is ~4 files + 6 tests, not "two buttons", and the plan's Wave 5 line ("buttons only, zero backend, zero risk") should be amended to say so.

*Evidence:* services/composition-service/app/services/plan_forge_service.py:494-500 (empty revision+focus_paths ⇒ no_change, zero work, no model resolve — the silent no-op a bare button would ship); :521-535 (worker on ⇒ 202 ack {run_id,job_id,status} + active_job_id/status=checkpoint ⇒ hook must re-fetch); :499,569 (diagnosis=None). services/composition-service/app/routers/plan_forge.py:58-67 (PlanRefineRequest.revision: dict[str,Any]|None; PlanInterpretRequest.user_message min_length=1; apply_mode_hint: Literal["auto","confirm","diagnose_only"]). services/composition-service/app/engine/plan_forge/interpret.py:220-230 (interpret returns version/intent/confidence/focus_paths/diagnosis/draft_revision/apply_mode/clarifying_questions) + refine.py:24,285,315,320 (refine reads revision.focus_paths/frozen_paths/expect_contains/scope ⇒ draft_revision IS a refine revision). frontend/src/features/plan-forge/types.ts:87,113-122 (3 drifts: revision?: string, diagnosis: string, apply_mode_hint?: string). frontend/src/features/plan-forge/api.ts:70-83 + :29 isAck (methods + ack helper already exist). frontend/src/features/plan-forge/hooks/usePlanRun.ts:158-180 (runCompile's isAck→getRun branch = the pattern runRefine must copy). frontend/src/features/plan-forge/components/PlanRunView.tsx:82-88 (selfCheck gaps already render g.path ⇒ checkboxes are free). frontend/src/features/plan-forge/components/PlannerPanel.tsx:79,82 (effectiveModelRef already computed + the canPropose disable pattern; never passed to PlanRunView). Grep for `interpret|refine` across frontend/src/features/plan-forge/hooks/ + components/ returns ZERO — the spec's "zero callers" claim CONFIRMED.

### Q-30-AN9-AN10-NO-NEW-REGISTRY
CONFIRMED AND SHARPENED — but the guardrail is stronger than the spec states: not only is there no need for a new registry, there is no need for a new SURFACE either, and no wave in plan 30 may build one.

Write this into §8.1 verbatim as a binding rule on Waves 1-8:

**RULE X-REG (binding, Waves 1-8): NO wave in this plan builds a tool/skill listing surface, a tool categorization, or a tool-domain registry. Both halves already ship.**

1. **The registry exists.** `services/chat-service/app/services/tool_discovery.py:64` `GROUP_DIRECTORY` (13 domains) + `_DOMAIN_ALIASES` (:656) + `_domain_of()` (:664) + `CATEGORY_ENUM` (:98), and the deterministic `tool_list`/`tool_load` pair (:50, :166) IS AN-9's pull-not-push law in code. TS mirror: `services/ai-gateway/src/federation/find-tools.ts`, lockstep-asserted by `services/ai-gateway/test/find-tools.spec.ts:202`.
2. **The surface OVER it already exists too** — the spec's prescription is already satisfied at HEAD, so "reuse it" means "call it", not "build it": `GET /v1/chat/tools/catalog?visibility=discoverable|legacy` (`services/chat-service/app/routers/catalog.py:14`) returns `{name, domain, tier, description, visibility}` with `domain` already resolved through `_domain_of()` (:40-44); `GET /v1/chat/skills/catalog` (:50) is the skill twin.
3. **FE clients already exist — do NOT hand-roll a fetch.** Use `listToolsCatalog()` (`frontend/src/features/chat/api.ts:230`, backs the context-rack browser) or `listToolCatalog()` (`frontend/src/features/extensions/api.ts:269`, backs the tool-permissions surface).

**Concrete builder instructions:**
- Need to display "what tools exist in domain X" in any panel? Call the existing route/client above. Add NO route, NO table, NO new domain list.
- Wave 8 (world/KG): **`world` is ALREADY a GROUP_DIRECTORY domain** (`tool_discovery.py:74`, covering `world_*` + `world_map_*`) ⇒ Wave 8 requires ZERO directory change. Any PR that adds one is wrong.
- If a genuinely new tool domain is ever needed: edit `GROUP_DIRECTORY` (`tool_discovery.py:64`) AND the `find-tools.ts` mirror in the SAME commit; verify with `pytest services/chat-service/tests/test_tool_discovery.py -k group_directory` (asserts `find_tools.group.enum == sorted(GROUP_DIRECTORY)`, :983) + `npx vitest run services/ai-gateway/test/find-tools.spec.ts`.
- **`/review-impl` finding (bake into every wave's DoD):** any NEW dict / array / TS union / enum in this batch that maps a tool-name prefix → a category label is a **second registry** — reject it and re-point at `_domain_of()`.

**Why the temptation is already gone:** PO-2 (§0, SEALED) dropped G-WORKFLOWS to Track C — that was the ONLY gap in the register that wanted a tool-listing surface (the workflow rack / binding UI). PO-1 makes Wave 7 add no panel at all. So Waves 1-8 have no legitimate reason to enumerate tools. This concern is therefore CLOSED as a prohibition, not carried as a work item. Default I am picking (veto-able): the rule is enforcement-by-review, not a new lint script — writing a "no second registry" AST lint is more machinery than the risk warrants now that no wave needs the surface.

*Evidence:* services/chat-service/app/services/tool_discovery.py:64 (GROUP_DIRECTORY), :74 (`world` domain already present), :98 (CATEGORY_ENUM), :664 (_domain_of) · services/chat-service/app/routers/catalog.py:14 + :50 (GET /v1/chat/tools/catalog + /skills/catalog — the surface already exists, domain resolved via _domain_of at :40-44) · frontend/src/features/chat/api.ts:230 (listToolsCatalog) · frontend/src/features/extensions/api.ts:269 (listToolCatalog) · services/ai-gateway/test/find-tools.spec.ts:202 (TS-mirror lockstep guard) · services/chat-service/tests/test_tool_discovery.py:983 (find_tools group enum == sorted(GROUP_DIRECTORY)) · docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md §0 PO-2 (G-WORKFLOWS dropped → the only gap wanting this surface)

### Q-30-WORK-ASSISTANT-KNOWLEDGE
VERIFIED — the disjointness grep the spec asked for is DONE; do not re-do it. Wave 8a is CLEARED to build all of G-KG-WRITE-HOLES, with 2 file-placement rules and 1 semantics rule.

CLEARED AS DISJOINT (no WA overlap — build freely):
(a) FE affordances. Wave 8a touches `frontend/src/features/knowledge/**` + `frontend/src/features/studio/panels/KgOverviewPanel.tsx`. The Work Assistant's FE is `frontend/src/features/assistant/**` (incl. `hooks/useDiaryFactInbox.ts` = the WS-2.5 fact inbox) + `frontend/src/features/chat/**` (`PendingFactsCard.tsx`, `usePendingFacts.ts`). ZERO shared files.
(b) The projection engine `project_glossary_entities_to_nodes` (`app/extraction/anchor_loader.py:194`) and `app/db/neo4j_repos/entities.py` — WA never edits them; Wave 8a only CALLS them (import, no edit).

RULE 1 — BE-14a goes in a NEW FILE, not `projects.py`. `app/routers/public/projects.py` is WA's live file (`PUT /{project_id}/capture-consent` :635 and `PUT /{project_id}/extraction-config` :653 are WA's A2 consent lane). Create `services/knowledge-service/app/routers/public/kg_projection.py` with its own `APIRouter(prefix="/v1/knowledge/projects", tags=["knowledge-kg"])` exposing `POST /{project_id}/project-entities`; register it with ONE line in `app/main.py` after line 786 (`app.include_router(public_kg_projection.router)`). Two routers on one prefix is already the house pattern — `app/routers/public/extraction.py:83` mounts a second router on this exact prefix. Handler: resolve project → assert `owner_user_id == JWT user` (404 on mismatch, KSA §6.4) → `async with neo4j_session()` → `project_glossary_entities_to_nodes(session, glossary_client, user_id=…, project_id=…, book_id=project.book_id, entity_ids=body.entity_ids or None)` → return the full `ProjectionResult` (`{nodes_created, nodes_existing, seen, skipped, conflicted, truncated}` — do NOT drop `conflicted`/`truncated`; anchor_loader.py:180-190 exists precisely so a partial projection isn't reported as a complete one). Test: `services/knowledge-service/tests/unit/test_kg_projection_api.py` — 200 happy path (counts mirror ProjectionResult), 404 on another user's project, second call idempotent (created=0, existing=N).

RULE 2 — BE-14b (`POST /facts/{fact_id}/invalidate`) goes in a NEW FILE `app/routers/public/facts.py`, NOT in `pending_facts.py` (WA's file: `pending_facts.py:56`, WS-2.2 tombstone landed there at HEAD~1). There is no public facts router today, so the file is free. MIRROR `app/routers/public/relations.py:63` (`POST /relations/{relation_id}/invalidate`) exactly — it is the already-shipped, already-reviewed sibling: JWT user_id threaded into the Cypher, cross-user/missing collapses to 404, `Fact` response model.

RULE 3 (the semantics rule — this is the actual bite, and it is NOT a grep issue). `invalidate_fact` (`facts.py:675`) is the exact primitive WA's SEALED D17 governs. Code confirms its limits: `_INVALIDATE_FACT_CYPHER` (facts.py:667-673) only SETs `valid_until` on the Neo4j node — it never touches the PG SSOT — and it is USER-wide, not project-scoped (executor.py:710-713 says so in a comment). It is therefore NOT erasure and NOT a correction. So: (i) name the FE affordance "Mark wrong / hide from context", NEVER "Forget" or "Delete"; (ii) the route docstring must carry the one-liner `not an erasure primitive — soft-invalidates one Neo4j fact's valid_until; the SSOT text is unchanged (see D17, docs/specs/2026-07-11-work-assistant-mode/00-overview.md:64)`. This route is a LEG-3 primitive that WA's WS-2.6 amendment will call on top of — it does not compete with D17 and does not need to wait for it. Rebuild-resurrection is NOT a blocker for Wave 8a: fact ids are content-hashed and `_MERGE_FACT_CYPHER`'s ON MATCH branch never resets `valid_until` (facts.py:180 sets NULL on ON CREATE only), and relations.py:12-14 states the same invariant for the shipped sibling ("recreate_relation resurrects valid_until without the extraction path ever being able to, F5").

BONUS CORRECTION for the Wave 8a builder (found while grepping; free, same disjoint file): the plan's "THREE dead buttons" claim is half wrong. `OverviewSection.tsx:56-69` no-ops `onArchive/onRestore/onDelete` on `ProjectRow` — those are KG-PROJECT destructive ops, and the code comment right above them (`OverviewSection.tsx:61-63`) says this is DELIBERATE: "Archive/restore/delete stay on the projects browser (destructive CRUD lives with the list)." Do NOT wire three destructive project ops into a dock panel. HIDE them instead (add a `hideDestructive`/`showDestructive={false}` prop to `ProjectRow` and pass it from `OverviewSection`) — a rendered button that does nothing is the bug; a panel that duplicates destructive project CRUD is a worse one. The genuinely dead ENTITY writes (create entity, and the 2 agent-only writes) are what Wave 8a wires.

*Evidence:* DISJOINT: frontend/src/features/knowledge/components/shell/OverviewSection.tsx:56,67-69 (Wave 8a) vs frontend/src/features/assistant/hooks/useDiaryFactInbox.ts + frontend/src/features/chat/components/PendingFactsCard.tsx (WA). COLLISION 1 (file): services/knowledge-service/app/routers/public/projects.py:635,653 = WA's capture-consent/extraction-config → avoid via new module; precedent for a 2nd router on the same prefix at services/knowledge-service/app/routers/public/extraction.py:83. COLLISION 2 (file): services/knowledge-service/app/routers/public/pending_facts.py:56 = WA's WS-2.2 file → new app/routers/public/facts.py instead. SEMANTICS: services/knowledge-service/app/db/neo4j_repos/facts.py:667-673 (invalidate = Neo4j-only SET valid_until, user-keyed) + :180 (ON CREATE SET f.valid_until = NULL — only a drop+rebuild resurrects; ON MATCH never resets it) + services/knowledge-service/app/tools/executor.py:710-713 ("no project gate needed... user_id, not a project"). PRECEDENT TO MIRROR: services/knowledge-service/app/routers/public/relations.py:63 (shipped public POST /relations/{id}/invalidate) and its file docstring at relations.py:12-14. ENGINES (call-only, no edit): app/extraction/anchor_loader.py:194, app/db/neo4j_repos/facts.py:675. WA's sealed D17: docs/specs/2026-07-11-work-assistant-mode/00-overview.md:64.

### Q-30-SPEC08-SESSION-ORCHESTRATOR
SPLIT the item. (a) The dirty-close guard (S7) is a **Wave-0 cross-cutting fix — build it, ID `X-DIRTY-CLOSE`**. (b) `StudioSessionOrchestrator` (the Tier-3 FSM) is **conscious won't-fix for this plan** — it has no consumer; the Tier-3 host primitives that S7 actually needs (registry + bus + `_dockApiRef`) already shipped in `StudioHostProvider.tsx`. Do NOT build an FSM to get a close guard.

FIRST, correct the spec's premise: **dockview 7.0.2 has no cancelable panel-close event.** `onWillClose` exists ONLY on `DockviewPopoutGroupOptions` (popout-window lifecycle) at `frontend/node_modules/dockview-core/dist/cjs/dockview/dockviewComponent.d.ts:48`. The real seam is `defaultTabComponent` (`dockview-react/dist/cjs/dockview/dockview.d.ts:12`), which `StudioDock.tsx` does not pass today. Build it as a **guarded tab**, not an "onWillClose handler".

BUILD (Wave 0, before any new EDITING panel lands):
1. NEW `frontend/src/features/studio/host/dirtyRegistry.ts` — module-level `Map<panelId, () => boolean>`; export `registerDirtyGuard(panelId, isDirty)` / `unregisterDirtyGuard(panelId)` / `isPanelDirty(panelId)` / `anyPanelDirty()` / `_clearDirtyGuards()`. Mirror the existing module-registry pattern in `documents/registry.ts` + `agent/effectRegistry.ts` (register at mount, test hook to clear).
2. NEW `frontend/src/features/studio/hooks/useDirtyGuard.ts` — `useDirtyGuard(panelId: string, dirty: boolean, onSave?: () => Promise<void>)`. Store `dirty`/`onSave` in a ref so a keystroke does NOT re-register; register on mount, unregister on unmount.
3. NEW `frontend/src/features/studio/components/StudioTab.tsx` — a `FunctionComponent<IDockviewPanelHeaderProps>`: title + a dirty dot (`isPanelDirty(props.api.id)`), and a close button + middle-click (`auxclick`, button 1) handler that, when dirty, opens `ConfirmDialog` (`components/shared/ConfirmDialog.tsx`) instead of closing: use its 3-way shape — `extraAction={{label:'Save & close', onClick: save→api.close()}}`, `confirmLabel='Discard changes'` → `api.close()`, cancel → no-op. When not dirty, close immediately (identical to today).
4. EDIT `frontend/src/features/studio/components/StudioDock.tsx:31-37` — pass `defaultTabComponent={StudioTab}`. Also check whether the current dock chrome exposes a group-level close-all control that bypasses the tab; if it does, route it through the same guard via `rightHeaderActionsComponent`; if it does not, assert that in the test.
5. EDIT `frontend/src/features/studio/panels/JsonEditorPanel.tsx:41` — `useDirtyGuard(props.api.id, !!snapshot?.dirty, () => handle.save())`. This is the live bug: `documents/types.ts:23` puts `dirty` on the shared handle and `registry.ts` `wrapRelease()` disposes it at refcount 0, so `useJsonDocument`'s unmount `release()` silently discards unsaved JSON today. Do the same for `WikiEditorPanel` (keep its localStorage draft cache as the safety net for bypass paths).
6. EDIT `frontend/src/features/studio/components/StudioFrame.tsx` — one `beforeunload` listener gated on `anyPanelDirty()` (same shape as `WikiEditorWorkspace.tsx:326-333`), covering browser refresh/close.
7. i18n: add `studio` ns keys `dirtyClose.title|body|save|discard|cancel` in every locale (no literals).

TESTS (the DoD, per "checklist ⇒ test the effect"):
- `components/__tests__/StudioTab.test.tsx` — dirty tab: close click ⇒ `api.close()` NOT called + dialog shown; Discard ⇒ `api.close()` called; Save & close ⇒ save awaited THEN `api.close()`; clean tab ⇒ closes with no dialog.
- `panels/__tests__/JsonEditorPanel.dirtyGuard.test.tsx` — an edited buffer registers a guard whose getter returns true.
- A guard-coverage test over an `EDITING_PANEL_IDS` constant: every id in it must have called `useDirtyGuard` (reds when a new editing panel forgets) — this is what makes the fix cross-cutting for canon-rules / arc-inspector / style-voice / divergence.

CATALOG/CHECKLIST: add "editing panel ⇒ `useDirtyGuard(props.api.id, dirty, save)`" as a mandatory line in spec 08's D22 panel-author checklist, and mark S7 ✅ in `08_studio_state_architecture.md:48/64`, replacing the "no onWillClose guard" wording with the defaultTabComponent mechanism (the API it named does not exist).

DEFER ROW (part b, filed not dropped): `D-STUDIO-ORCHESTRATOR-FSM` — `StudioSessionOrchestrator` FSM (spec 08 §"StudioSessionOrchestrator FSM", `08:228`). Gate 5 (conscious won't-fix for this plan) + gate 2 (large/structural if ever revived). Trigger: only if a concrete orchestration domain (boot / save-conflict / agent-surface) produces a bug that panel-local state + the bus cannot express. Note in the row that S7 — the ONLY consequence of its absence anyone could name — is closed by X-DIRTY-CLOSE without it.

PO DEFAULT NOTED FOR VETO: three-way prompt (Save & close / Discard / Cancel). If the PO prefers the wiki's silent draft-cache-and-restore instead of a prompt, that swaps step 3's dialog for a per-handle draft cache — same registry, ~same cost.

*Evidence:* frontend/node_modules/dockview-core/dist/cjs/dockview/dockviewComponent.d.ts:48 (`onWillClose` is POPOUT-window only — there is no cancelable panel close event, so the spec's premise is wrong); frontend/node_modules/dockview-react/dist/cjs/dockview/dockview.d.ts:12 (`defaultTabComponent` = the real seam); frontend/src/features/studio/components/StudioDock.tsx:31-37 (DockviewReact gets only onReady/components/theme — no tab component); frontend/src/features/studio/documents/types.ts:23 (`dirty: boolean` on the shared DocumentHandle) + frontend/src/features/studio/documents/registry.ts (`wrapRelease` disposes the handle at refs<=0) + frontend/src/features/studio/documents/useJsonDocument.ts:41-47 (unmount cleanup calls `release()` ⇒ dirty JSON silently discarded on tab close); frontend/src/components/shared/ConfirmDialog.tsx:6-33 (`extraAction` gives the 3-way Save/Discard/Cancel for free); frontend/src/features/wiki/components/WikiEditorWorkspace.tsx:326-333 (existing in-repo dirty-guard precedent); frontend/src/features/studio/host/StudioHostProvider.tsx:47-126 (Tier-3 host primitives already shipped — no FSM needed for S7)

### Q-30-PLANFORGE-GUI-AUDIT-STALE
CONFIRMED STALE on sub-gap 1 — the concern is right, and the candidate answer is adopted: amend, keep the other three sub-gaps. Concrete instructions for the Wave 5 builder:

(1) DO NOT touch the arc picker. It is fully shipped, FE *and* BE. `PlanRunView.tsx:117-124` renders `<select data-testid="plan-arc-picker">` from `run.arcs[]`; `:111-114` renders an explicit `data-testid="plan-arc-none"` reason (no silent disable); `:31` derives the default as `pickedArcId || run.arcs[0]?.id || ''` (derived default, not a useEffect). It is fed for real by `plan_forge_service.py:355-362`, which reads the latest `spec` artifact and emits `{id,title}` — the code comment there literally names `D-PLANFORGE-ARC-PICKER`. `types.ts:43` carries `arcs: PlanArc[]`. Any Wave 5 slice proposing an arc-picker build is re-work; delete it.

(2) The remaining three sub-gaps are REAL and stay in G-PLANNER-REPAIR exactly as spec 35 §7 scopes them — I re-verified each against code:
  - artifact viewer → BE-3. `PlanRunView.tsx:52-57` still renders artifacts as unclickable `<li>` (kind + truncated UUID). `plan_forge.py` has 13 routes, NONE reads an artifact body. Repo method `PlanRunsRepo.artifacts_by_ids(book_id, run_id, ids)` already exists and is book-scoped via the run join — the route is a wrapper.
  - source-markdown resume → BE-3b. `_serialize_run`'s returned dict (`plan_forge_service.py:363-378`) omits `source_markdown`. The FE cannot resume what the API never sends. One-line contract widening + widen `types.ts:PlanRunDetail`.
  - autofix → BE-2. `handoff_autofix` is implemented at `plan_forge_service.py:817`, exposed MCP-only; no `/autofix` route exists.
  - (Also still real: BE-4. `grep -c "@router.delete" plan_forge.py` → 0.)

(3) CORRECTION the builder must apply — there is NO live deferred row to amend. `D-PLANFORGE-GUI-AUDIT` is not in `docs/deferred/DEFERRED.md`, and the Writing Studio Deferred table (`SESSION_HANDOFF.md:95-104`) holds 5 rows, none of them this one. The ID survives only as narrative in archived `<details>` blocks (`SESSION_HANDOFF.md:1248, 1403, 1572`). The amendment is ALREADY recorded in the specs (`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:268` + `:817`; `35_planforge_studio.md:9` + `:359`). Therefore: EDIT `35_planforge_studio.md:583` (DoD item 7) from "`D-PLANFORGE-GUI-AUDIT` amended (sub-gap 1 stale) then cleared" to: "`D-PLANFORGE-GUI-AUDIT` has no live row (it lives only in SESSION_HANDOFF's archived <details>; the amendment is recorded in 30 §5 + 35 §0/§7) — nothing to clear. Confirm no arc-picker work was done." Without this edit the Wave 5 builder burns a cycle hunting a nonexistent row — the exact stall the PO's no-checkpoint policy makes expensive.

(4) Minor, non-blocking: spec 30 §5 cites `PlanRunView.tsx:120-128` / `:114-116`; the true lines are `:117-124` (select) and `:111-114` (no-arcs). Line drift only, same component — fix the cite if touching the line, but do not chase it as a different file. (Spec 35's `:52-57` artifact cite IS exact.)

Default I am picking so the PO need not stop: keep G-PLANNER-REPAIR sized M as-is. Removing sub-gap 1 does not shrink the wave — it was already excluded from the BE prereq list (BE-2/3/3b/4), so the size is unchanged. Veto only if you want the wave re-sized.

*Evidence:* FIXED (do not re-do): frontend/src/features/plan-forge/components/PlanRunView.tsx:117-124 (<select data-testid="plan-arc-picker"> over run.arcs), :111-114 (data-testid="plan-arc-none" explicit reason), :31 (derived default); fed by services/composition-service/app/services/plan_forge_service.py:355-362 (builds arcs from latest "spec" artifact; comment names D-PLANFORGE-ARC-PICKER); frontend/src/features/plan-forge/types.ts:43 (arcs: PlanArc[]). Commit 9c685c28a "feat(planforge): M4 real plain-language bootstrap UI + arc picker fix".
STILL REAL: PlanRunView.tsx:52-57 (artifacts as unclickable <li>); services/composition-service/app/routers/plan_forge.py (13 @router.* routes, none reads an artifact body; grep -c "@router.delete" → 0); plan_forge_service.py:363-378 (_serialize_run omits source_markdown); plan_forge_service.py:817 (handoff_autofix implemented, MCP-only).
NO LIVE ROW: "D-PLANFORGE-GUI-AUDIT" absent from docs/deferred/DEFERRED.md; SESSION_HANDOFF.md:95-104 Deferred table has 5 rows, none this one; ID appears only at SESSION_HANDOFF.md:1248, 1403, 1405, 1572 (archived <details>). Amendment already written at docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:268 and :817, and 35_planforge_studio.md:9 and :359. Stale DoD to fix: 35_planforge_studio.md:583.

### Q-30-SPEC05-BIBLE-SEARCH-STUBS
ADD ONE ROW — a 2-slice item **G-RAIL-STUBS (S)**, landed in **Wave 8** (which PO-2 emptied of 8c, and which completes the `storyBible` category with `world`/`world-map` — so the bible launcher renders the full set on day one). NOT a new wave. Neither half is a build; one is a PORT, the other is a 10-line-away precedent.

The spec framed this as "two views lead nowhere, decide whether to add a row." The code says both are near-free, and one of them is actively LYING to the user.

── SLICE A · `search` rail = mount the SHIPPED panel (a PORT per GG-3, ~30 LOC) ──
The search UI ALREADY EXISTS and is tested: `frontend/src/features/raw-search/` (13 files: hybrid lexical+semantic, `renderHighlight`, debounce, owner-only draft indexing), backed by a live route `GET /v1/books/{id}/search` (`services/book-service/internal/api/server.go:263` → `searchChapterText`) + the knowledge semantic leg. It is mounted ONLY at the standalone page `/books/:bookId/search` (`frontend/src/App.tsx:173`). Meanwhile the Studio rail stub renders i18n `navStub.search.body` = "Full-text & semantic search across the book. **Coming soon.**" — the `built-but-unreachable-nav` bug class, shipped, telling the user a live feature is unbuilt.

1. `frontend/src/features/raw-search/components/RawSearchPanel.tsx` — add an optional prop to `RawSearchPanelProps` (line 18-20): `onOpenHit?: (chapterId: string, blockId?: string) => void`. At **line 54**, replace the unconditional `navigate(`/books/${bookId}/chapters/${chapterId}/read${target}`)` with: call `onOpenHit(chapterId, blockId)` when provided, ELSE fall through to the existing `navigate(...)`. ⚠ This prop is REQUIRED, not cosmetic: inside the Studio a bare `navigate()` **tears down the dock** — the exact defect §0 PO-3 records for `ui_watch_job`. A naive port would ship that bug. Do NOT delete `RawSearchPage`; the default branch keeps it working.
2. `frontend/src/features/studio/components/StudioSideBar.tsx` — add a branch before the stub `else` (line 57): `activeView === 'search'` → the existing 34px header chrome (title + collapse, copy lines 59-71) wrapping `<RawSearchPanel bookId={bookId} onOpenHit={(chapterId) => host.focusManuscriptUnit(chapterId)} />`. `bookId` is already in props (line 14); `host.focusManuscriptUnit` is the existing seam — `StudioFrame.tsx:114` uses exactly it for a chapter hit.
3. i18n — DELETE `navStub.search` from all 12 `frontend/src/i18n/locales/*/studio.json`. The `rawSearch` namespace already exists.
4. Tests — `StudioSideBar.test.tsx`: `activeView='search'` renders the search input (not the stub body); clicking a hit calls `focusManuscriptUnit` and does **NOT** call `navigate` (the dock-teardown guard). `RawSearchPanel.test.tsx`: with no `onOpenHit`, it STILL navigates (the RawSearchPage regression guard).

── SLICE B · `bible` rail = catalog-derived launcher (~40 LOC) ──
Follow the **Quality precedent verbatim** — `StudioSideBar.tsx:83-92`, whose own comment states the rule: "Quality has no rail navigator of its own (its 4 capabilities are dock panels, DOCK-8 hub pattern) — this button is its only rail affordance." Bible is the identical shape: its capabilities ARE dock panels (6 ship today: `glossary`, `glossary-ontology`, `glossary-unknown`, `glossary-ai-suggestions`, `glossary-merge-candidates`, `wiki` — `catalog.ts:128-139`).

1. `StudioSideBar.tsx` — `activeView === 'bible'` → a launcher list DERIVED from `STUDIO_PANELS.filter(p => p.category === 'storyBible' && !p.hiddenFromPalette)`; each row a button → `host.openPanel(p.id)`, labelled `t(p.titleKey)` with `t(p.descKey)` as sub-text.
2. 🔴 **DERIVE from the catalog — do NOT hardcode the ids.** `catalog.ts:81-83` already types `StudioPanelCategory`, and plan 30's own panel table (§ rows 550-559) registers `motif-library` (W3a), `arc-templates` (W4), `world` + `world-map` (W8b) as `category: 'storyBible'`. A derived rail picks all four up **for free, with zero further edits**. The filter also correctly excludes `wiki-editor` (`catalog.ts:144`, `hiddenFromPalette: true`).
3. i18n — drop `navStub.bible` (labels now come from each panel's existing `titleKey`/`descKey`).
4. Tests — `StudioSideBar.test.tsx`: renders one button per `storyBible` catalog panel; clicking `glossary` calls `host.openPanel('glossary')`; **inject a fake `storyBible` panel into the catalog and assert a row appears** — that is the guard that keeps it auto-growing as the waves land.

── DoD (per PO policy #2) ──
`/review-impl` at wave close + a **live browser smoke** proving the dock stays mounted after a search-hit click (that is the entire reason `onOpenHit` exists — a unit test on a mocked router will not catch a real dock teardown).

── Why not DEFER ──
Clears NONE of CLAUDE.md's 5 gates. Not out-of-scope (it is the Studio chrome the plan owns), not structural (no schema, no contract, no new route — the route ships), not next-phase, not externally blocked, not a won't-fix. The search half is a port of tested code whose panel takes one prop the caller already has; the bible half has a working precedent in the same file. **Writing the two defer rows would cost more than the fix** — the exact anti-pattern CLAUDE.md names.

── The one default I am setting (PO may veto) ──
The bible rail is a **launcher, not a tree**. A true story-bible entity *tree navigator* (cast/world/canon hierarchy in the rail) is a materially bigger build with its own data-shape questions. I default to the launcher because it is what the Quality view already does, it makes both dead icons live now, and it auto-grows. If the PO wants a real entity tree in the rail, that is a separate spec — this decision does not preclude it (the launcher is the honest floor, not a ceiling).

*Evidence:* frontend/src/features/studio/components/StudioSideBar.tsx:73-93 — the `else` stub covering bible+search, AND the Quality precedent at :83-92 ("Quality has no rail navigator of its own … this button is its only rail affordance") which is the exact pattern bible should copy. · frontend/src/features/raw-search/components/RawSearchPanel.tsx:18-20 (`RawSearchPanelProps` = `{ bookId }` ONLY — the one prop StudioSideBar.tsx:14 already holds) and :54 (`navigate(`/books/${bookId}/chapters/${chapterId}/read${target}`)` — the dock-teardown hazard the `onOpenHit` prop fixes). · frontend/src/App.tsx:173 — `<Route path="/books/:bookId/search" element={<RawSearchPage />} />`: the search UI is SHIPPED, just mounted outside the Studio. · services/book-service/internal/api/server.go:263 — `r.Get("/search", s.searchChapterText)` (+ semantic leg via frontend/src/features/raw-search/api.ts:48): the backend is live. · frontend/src/i18n/locales/en/studio.json — `navStub.search.body` = "Full-text & semantic search across the book. Coming soon." (a shipped feature advertised as unbuilt). · frontend/src/features/studio/panels/catalog.ts:81-83 (`StudioPanelCategory` incl. `storyBible`) + :128-139 (6 shipped storyBible panels) + plan 30 §rows 550-559 (motif-library/arc-templates/world/world-map register as `storyBible` in W3a/W4/W8b → a catalog-derived rail absorbs them free). · StudioFrame.tsx:114 — `host.focusManuscriptUnit(r.chapterId)`, the existing open-a-chapter seam the search rail reuses.

### Q-30-G-WORK-SETTINGS-ORPHANS
All 3 orphan routes are now OWNED, and the 3 hidden keys get a specified surface. Wave 6, spec 36 (`36_editor_craft_ports.md`), G-WORK-SETTINGS + G-DIVERGENCE (same wave — that is why `approve` lands here and not in a new one).

=== (1) `approve` → ASSIGN. It is a CAPABILITY orphan, and it is the most serious thing in this row. ===
`services/composition-service/app/routers/approve.py:182` is the ONLY `knowledge.extract_item` call site in composition-service, and the route has zero FE callers ⇒ the C27 dị bản DELTA FLYWHEEL HAS NEVER RUN. A derivative Work's delta partition is never enriched by its own approved chapters, so C25's packer keeps serving the base's knowledge forever. Shipped-and-unreachable (this repo's `built-mounted-unreachable` class).
BUILD (Wave 6, alongside the `divergence` panel port):
- Host: the `DerivativeBanner` component ported by G-DIVERGENCE (it already renders only when `derivative-context` says `is_derivative`, and it already knows `source_work_id` + `branch_point` — `frontend/src/features/composition/api.ts:128-134`). Add a primary action **"Commit chapter to this dị bản"**, enabled only when an editor chapter is open.
- API: add `compositionApi.approveChapter(token, projectId, chapterId, {model_source, model_ref})` in `frontend/src/features/composition/api.ts` (next to `persistScenePros`/derive, ~line 215) → `POST ${BASE}/works/${projectId}/chapters/${chapterId}/approve`. Body is REQUIRED (`ApproveChapterBody`, approve.py:59-65): pass `model_source:'user_model'` and `model_ref` = the Work's `settings.default_model_ref` (`CompositionSettingsView.tsx` already persists it); if unset, disable the button with the hint "Set a default drafter model in Book settings → Composition" — do NOT hardcode a model (provider-registry invariant).
- Render the response honestly. The route returns `{dispatched, reason, ...}` and a `dispatched:false` is a CLEAN 200 — a silent success here is exactly the bug class the plan exists to kill. Map every `reason` from approve.py to a distinct toast: `not_a_derivative` / pre-branch (`decision.reason`) → "Inherited from the base — nothing to add to the delta"; `empty_chapter` → "Chapter is empty"; `source_unresolved` → "Source Work missing — delta cannot be scoped"; `knowledge_unavailable` → "Approved, but knowledge is offline — re-approve to enrich"; `dispatched:true` → "Approved — extracting into this dị bản's delta (N entities/events/facts)" from `extraction`. A 409 `DELTA_PROJECT_UNSCOPED` → error toast, never a success.
- TEST: `frontend/src/features/studio/panels/__tests__/` — one test asserting the button POSTs with the resolved model_ref, and one asserting `dispatched:false` renders the reason (NOT a success toast).

=== (2) `suggest-cast` → ASSIGN (as the plan proposed; confirmed buildable, zero BE work). ===
`engine.py:1397` `POST /works/{pid}/scenes/{nid}/suggest-cast`, body `{guide: str}` (engine.py:198), returns `{suggested_entity_ids: [...]}`. Its target field exists: `OutlineNode.present_entity_ids` (`db/models.py:152`), already editable via the outline PATCH the scene-inspector uses.
BUILD: in `SceneInspectorPanel` (registered `frontend/src/features/studio/panels/catalog.ts:185`), add a **"Suggest cast"** button next to the present-entities field → call the route with `guide` = the free-text box (default '') → render the returned entity ids as *proposed chips* (reuse `EntityRefField.tsx`), each with an accept ✓ that appends to `present_entity_ids` via the existing outline update mutation. NEVER auto-write the cast (AN-8 edit discipline: human-gated). Add the api method to `features/composition/api.ts`. TEST: mock the route, assert chips render and that accepting one issues the outline PATCH with the union of prior + accepted ids.

=== (3) chapter-level GET|PUT /prose → CONSCIOUSLY DROP as a GUI gap (gate 5). NOT a gap under GG-1. ===
The capability is ALREADY GUI-covered: the Studio editor reads/writes the identical `loreweave_book.chapter_drafts` row directly through book-service (`frontend/src/features/books/api.ts:427` GET draft / `:435` PATCH draft, consumed at `frontend/src/features/studio/manuscript/unit/ManuscriptUnitProvider.tsx:222` — and it already sends `expected_draft_version`, so the proxy's one differentiator buys nothing). `prose.py` is a duplicate door. The repo has ALREADY made this exact call on the agent side: the MCP twins `composition_get_prose` (`mcp/server.py:465-469`) and `composition_write_prose` (`mcp/server.py:1227-1231`) are both marked `visibility="legacy", superseded_by="book_get_chapter" / "book_chapter_save_draft"` with the comment "the catalog has ONE chapter-read tool, not two identical ones". The REST pair inherits that decision by construction.
BUILD (XS, in Wave 6 so the register closes clean): mark BOTH routes `deprecated=True` in the decorator (`prose.py:92`, `prose.py:115`) and add a one-line comment citing `mcp/server.py:465-469`'s `superseded_by`. Wire NO GUI to them. Note: the SCENE-level `POST /works/{pid}/scenes/{nid}/prose` (`engine.py:1522`) is a DIFFERENT route, IS consumed (`features/composition/api.ts:223`), and is untouched by this.
DEFER ROW (deletion, not wiring): D-COMP-PROSE-PROXY-RETIRE — see deferRow.

=== (4) The 3 SET-1..8 hidden defaults → the Composition section in `book-settings`. ===
Extend `frontend/src/features/composition/components/CompositionSettingsView.tsx` (already surfaces `default_model_ref`, `assembly_mode`, `narrative_thread_enabled`; it is reused inside the `book-settings` dock panel — `BookSettingsPanel.tsx` reuses `SettingsTab`, same DOCK-2 reuse pattern) with a `<SettingRow>` helper that renders for EVERY key: label · control · **"Effective: X · Source: <tier>"**. The tiers here are exactly two: **Default (code)** and **This Work** (the per-book `composition_work.settings` blob) — say which one is live, never render a control whose value silently comes from elsewhere.
- `capture_correction_prose` — checkbox. Consumer: `routers/engine.py:1766` `bool(work.settings.get("capture_correction_prose", False))`. Effective when absent = **OFF · Source: Default**. Hint: "Stores the verbatim before/after prose of your corrections (raw_before/raw_after are NULL unless opted in — migrate.py:360). Off = structural signal only."
- `critic_model_ref` (+ `critic_model_source`) — model select. Consumers: `engine.py:465/529/1029/1099/1261/1345`, `routers/internal_model_settings.py:62-64`. THE HIDDEN DEFAULT: when unset, `services/authoring_run_service.py:574` does `params.get("critic_model_ref") or params.get("model_ref")` — the critic silently becomes the DRAFTER model (self-critique / anti-self-reinforcement is lost). So when unset the row MUST read: **"Effective: <drafter model alias> (falling back to the drafter — the critic is grading its own prose) · Source: Default"**. That sentence is the whole point of this key.
- `reference_embed_model_ref` (+ `_source`) — model select, EMBEDDING-capable models only. Consumer: `db/repositories/references.py:35-48` (`reference_embed_model()`), write-through on the first reference add — one vector space per Work. Row must show: unset → "Effective: none — set on your first reference · Source: Default"; set → value + **read-only + a lock hint** "Locked: all this Work's reference vectors share this model. Changing it would invalidate them." (Do NOT ship an unguarded edit control on a set value — that is a silent corruption.) This pairs with G-REFERENCES-SHELF in the same wave.
All writes go through `useSetWorkSettings` (merge-patch), which stays correct only until BE-18 lands the server-side `settings || $n::jsonb` fix — confirmed at `services/composition-service/app/db/repositories/works.py:313` (`set_clauses.append(f"settings = ${len(params)}::jsonb")`, a full-blob REPLACE). BE-18 is a hard prerequisite of this slice, not a nice-to-have: two settings sections (Composition + any concurrent writer) racing on one blob is a live lost-update.
TESTS: extend `frontend/src/features/studio/panels/__tests__/BookSettingsPanel.test.tsx` — assert each of the 3 rows renders BOTH the effective value AND the source tier, and specifically that with `critic_model_ref` absent the row names the drafter model as the effective critic. (Per this repo's `checklist⇒test-the-effect` rule, a SET-1..8 claim is DONE only when a test asserts the source-tier string.)

DoD for the slice (PO policy, quoted): "/review-impl runs at the completion of EVERY wave, and any bug it finds is fixed before the wave closes."

*Evidence:* approve is a capability orphan: services/composition-service/app/routers/approve.py:77 (route) + :182 (the ONLY knowledge.extract_item call site in the service — `grep -rn "extract_item" services/composition-service/app` → clients/knowledge_client.py:158 def + approve.py:182 only), zero FE callers (`grep -rn "/approve" frontend/src` → enrichment/extensions/plan-forge/settings only). | chapter /prose is a duplicate door: services/composition-service/app/routers/prose.py:92,115 vs the live editor path frontend/src/features/books/api.ts:427,435 → frontend/src/features/studio/manuscript/unit/ManuscriptUnitProvider.tsx:222; its MCP twins are already retired — services/composition-service/app/mcp/server.py:465-469 and :1227-1231 (`visibility="legacy", superseded_by="book_get_chapter"/"book_chapter_save_draft"`). | suggest-cast: services/composition-service/app/routers/engine.py:1397 (+ body at :198) → OutlineNode.present_entity_ids at services/composition-service/app/db/models.py:152; host panel registered at frontend/src/features/studio/panels/catalog.ts:185. | hidden defaults: engine.py:1766 (capture_correction_prose default False), services/composition-service/app/services/authoring_run_service.py:574 (critic silently falls back to the drafter model), services/composition-service/app/db/repositories/references.py:35-48 (reference_embed_model write-through-on-first-add). | blob REPLACE (BE-18): services/composition-service/app/db/repositories/works.py:313.

### Q-30-MCPBRIDGE-PRECEDENT
TRANSPORT RULE (binding for Waves 3+4; the spec's own phrasing is CORRECTED by the code): the bridge is NOT "the motif transport". It is the transport for exactly ONE leg — the cost-gated PROPOSE that mints a confirm_token + $ estimate. Ask one question per FE action: "does this action SPEND LLM tokens / need a cost gate?" YES -> bridge-propose, then REST-confirm, then REST-poll. NO -> plain REST `/v1/composition/*` via `apiJson`. This is enforced by construction: FE_BRIDGE_TOOL_ALLOWLIST (tools.controller.ts:25) admits ONLY propose+poll tools and its own comment says "NOTHING here writes or deletes".

CONCRETELY:

(1) G-MOTIF-LIBRARY is a PORT, not a build. Reuse `frontend/src/features/composition/motif/api.ts` VERBATIM as the panel's api layer. Do NOT write a new api.ts, do NOT add a REST mirror of adopt/mine, do NOT touch the BFF allowlist. Note the file already splits the transports correctly and the builder must preserve that split: bridge for `adoptEstimate` (:103) / `minePropose` (:140) / `arcConformanceRunPropose` (:249); REST for `list`/`get`/`patch`/catalog, `upstreamDiff` (:192), `sync` (:197), `/actions/confirm`, and `compositionApi.getJob`. The Wave-3 work is catalog.ts row + panel enum + frontend-tools contract + i18n + mounting the existing components — zero new API surface.

(2) G-IMPORT-DECONSTRUCT needs ZERO new backend/BFF work for its LLM leg: `composition_arc_import_analyze` is ALREADY on the FE allowlist (tools.controller.ts:28) and has ZERO FE callers today (grep: only two comments in features/plan-hub/). Build the panel as: propose = `mcpExecute('composition_arc_import_analyze', { args: {...} }, token)` -> `{confirm_token, estimate}`; confirm = `POST /v1/composition/actions/confirm?token=<ct>` (JWT-authed; token in the QUERY, identity from the Bearer); poll = reuse `_resolveActionJob` (motif/api.ts:324) -> `compositionApi.getJob` -> `GET /jobs/{job_id}` (engine.py:1415). Any non-LLM CRUD around it (list imports, persist the resulting arc) is REST — write the route if it does not exist (unbuilt work, not a blocker).

(3) THE ONE CASE THE BRIDGE IS NOT FREE — bake this into both waves' DoD or a builder eats a 403 at 3am: a NEW Tier-W propose tool (e.g. a "suggest" that spends tokens) that is not one of the 5 allowlisted names MUST be added to FE_BRIDGE_TOOL_ALLOWLIST (tools.controller.ts:25) AND to its spec test (tools.controller.spec.ts:118 pattern) in the same slice. A missing allowlist entry returns a uniform 403 "tool not permitted" that reveals nothing — it will read as a mystery auth bug.

(4) FASTMCP ARG-NESTING GOTCHA (verified live, per the comment at motif/api.ts:250): the MCP tool takes a single pydantic `args` param, so the bridge call must nest — `mcpExecute(tool, { args: { ... } }, token)`. A flat body fails arg validation. Every new bridge call site copies this shape.

(5) Do NOT build a REST mirror of any allowlisted propose tool (that would violate MCP-first and duplicate the cost gate), and do NOT try to route a WRITE through the bridge (the allowlist rejects it by design — confirm stays a signed-token write on the domain service).

*Evidence:* services/api-gateway-bff/src/tools/tools.controller.ts:19-31 (FE_BRIDGE_TOOL_ALLOWLIST = 5 tools, propose+poll ONLY, "NOTHING here writes or deletes"; line 28 = `composition_arc_import_analyze` already allowlisted) · frontend/src/mcpBridge.ts:15-24 (mcpExecute -> POST /v1/ai/tools/execute) · frontend/src/features/composition/motif/api.ts:103,140,249 (bridge = propose only) vs :192,:197,:118,:164 (REST for sync/upstream-diff/confirm) and :324 `_resolveActionJob` (REST poll) · services/composition-service/app/routers/engine.py:1415 (GET /jobs/{job_id}, the real poll route) · grep for `arc_import_analyze` in frontend/src returns only 2 comments — zero callers.

### Q-30-00C-Q3C-THREADS-DUPLICATE
Wave 1 does ZERO porting work for Q-3(c) — the port is ALREADY DONE by reuse — plus ONE guardrail the spec's wording actively endangers.

(1) DO NOT DELETE `frontend/src/features/composition/components/ThreadsPanel.tsx`. It is NOT the duplicate — it is the SHARED view component that Studio's `quality-promises` renders. `QualityPromisesPanel.tsx:9` imports it and `:33` renders it ("thin wrapper ... reuses ThreadsPanel AS-IS ... (no fork)"). Deleting the file breaks the Studio Quality hub tile, the panel catalog entry, and the Plan Hub thread deep-link. The word "duplicate" in 00C Q-3(c) refers to the legacy TAB REGISTRATION, not the component file.

(2) Build NOTHING new for threads in Wave 1. `quality-promises` is registered (`studio/panels/catalog.ts:267`, category 'quality'), is a tile in the Quality hub (`QualityHubPanel.tsx:14`), and is the deep-link target of the Plan Hub thread badge (`PlanHubPanel.tsx:68`, params `{ focusThreadId }`). Wave 1 ports only Q-3(a) `progress` word-count goals and Q-3(b) `quality` correction-stats. Threads gets no new panel, no fork, no re-implementation.

(3) The legacy duplicate SURFACE = the CompositionPanel `threads` tab registration: `CompositionPanel.tsx:87` (SubTab union), `:450` (stripIds), `:841-843` (DockSlot), `:329` (threadsEnabled), and `workspace/dock.ts:7-8` (`included()`). DEFAULT DECISION (PO may veto): delete these with Q-6's wholesale legacy-CompositionPanel retirement, NOT piecemeal in Wave 1. Rationale: Q-6 deletes all 25 tabs anyway, so "delete, don't port" still lands; removing one tab early buys nothing and touches the persisted-layout path — `CompositionPanel.test.tsx:221-239` covers a saved layout with `active:'threads'` falling back gracefully, and that fallback is driven by the exact `threadsEnabled` gate a piecemeal delete would remove. Add `threads` to Q-6's retirement checklist as "KILLED — superseded by studio `quality-promises`".

(4) `quality-promises` STAYS READ-ONLY. Confirmed at `services/composition-service/app/routers/narrative_threads.py:50`: the only route is `@router.get("/works/{project_id}/narrative-threads")` — zero POST/PATCH/PUT/DELETE on threads in the service. `narrative_thread` is generation-time-detected, not user-authored. Do not add write affordances; do not re-raise "half-built read-only panel" as a gap.

Note: the Studio wrapper is a strict SUPERSET of the legacy tab — legacy gates on `work.settings.narrative_thread_enabled` (`CompositionPanel.tsx:329`), Studio passes `enabled` unconditionally because opt-in navigation makes the declutter gate moot. So retiring the legacy tab loses no capability.

*Evidence:* frontend/src/features/studio/panels/QualityPromisesPanel.tsx:9,33 (imports+renders composition's ThreadsPanel AS-IS — no fork ⇒ the file is load-bearing, not deletable); frontend/src/features/studio/panels/catalog.ts:267 + QualityHubPanel.tsx:14 + PlanHubPanel.tsx:68 (quality-promises registered, hub-tiled, deep-linkable ⇒ port already done); frontend/src/features/composition/components/CompositionPanel.tsx:87,329,450,841-843 + workspace/dock.ts:7-8 (the actual duplicate = legacy tab registration); services/composition-service/app/routers/narrative_threads.py:50 (ONLY @router.get — no write verb on threads anywhere ⇒ read-only refutation CONFIRMED); frontend/src/features/composition/components/__tests__/CompositionPanel.test.tsx:221-239 (stale active:'threads' layout fallback rides the threadsEnabled gate ⇒ piecemeal delete has a regression surface Q-6 already owns)

### Q-30-SPEC01-TOPBAR-DEBT2
FOLD INTO WAVE 7 as slice **7d — "chrome truth"** (add it to `37_issues_feed.md`; Wave 7 is already "wire the chrome that renders a placeholder string with no producer" — the top/status bar is the same file family, same shape of fix, same reviewer, same live-smoke). Do NOT file a defer row: the whole slice is ~3 files and cheaper than carrying the row (CLAUDE.md fix-now default). Debt #2 as written is 2/3 phantom — spec 01:16 sealed "Generate/Save/model come with the panels that need them", and they DID: Save = EditorPanel.tsx:363-370 over the Tier-4 hoist; Generate = the Compose panel; model = the shared ModelPicker. What is actually broken is (a) a provider-nesting bug and (b) one lying placeholder.

**Slice 7d — exact work:**

1. **`frontend/src/features/studio/components/StudioFrame.tsx`** — move `<ManuscriptUnitProvider bookId={bookId}>` from line 137 UP so it wraps the frame's entire subtree: open it immediately inside the root `<div className="flex h-screen …">` (i.e. BEFORE `<StudioTopBar>` at :131) and close it AFTER `<CommandPalette …/>` (currently the tag closes at :171, before the palettes at :174+). Nothing inside the provider depends on the top bar or the palettes — it was already hoisted once for exactly this reason (see the `#12 M-H` comment at :133-136). This single move is what unblocks BOTH the top bar and the palette; there is no missing route and no missing pipeline.

2. **`frontend/src/features/studio/manuscript/unit/ManuscriptUnitProvider.tsx`** — add a THIRD narrow context beside the existing `ManuscriptUnitMetaContext` (:112) and `ManuscriptUnitContext` (:100): `ManuscriptUnitSaveContext` + `useManuscriptUnitSave()` returning `{ isDirty, saveState, save }`, memoized on `[isDirtyState(state), state.saveState, save]` ONLY. Required by CLAUDE.md "split context by update frequency": `useManuscriptUnit()` re-memos on every keystroke (api memo at :332 depends on `state`), and the chrome must not sit on the keystroke path. ~8 lines.

3. **`frontend/src/features/studio/components/StudioTopBar.tsx`** — add a Save control consuming `useManuscriptUnitSave()`: `data-testid="studio-topbar-save"`, label `t('editor.save')` + `⌘S`, `disabled={!isDirty || saveState === 'saving'}`, dirty dot when `isDirty`. It CALLS `save()` — do not fork save logic, and do NOT remove the EditorPanel button (that one is the in-context save). Renders nothing when the hook returns no dirty-capable unit.

4. **`frontend/src/features/studio/components/StudioStatusBar.tsx:38`** — DELETE the hardcoded `'no model'` lie. Replace with the user's effective default chat model, read via the EXISTING `useUserModels({ capability: 'chat' })` (`@/components/model-picker`): render the favourite/first model's `alias`; when `models` is `[]` render a button "Set a model" that opens the `settings` panel (`catalog.ts:120`) via `host.openPanel('settings')`. **Do NOT invent a "studio model" setting** — that would be a second home for a concept the chat session + user defaults already own (SET-8 / the model-picked-in-8-places bug). The status bar DISPLAYS the effective value; it does not become a new tier.

5. **`frontend/src/features/studio/palette/useStudioCommands.ts`** — resolve 06b's 3 deferred commands (06b_command_palette.md:87-93) as **1 wired, 2 retired**:
   - ADD `studio.saveChapter` → `Studio: Save Chapter` (group `layout`/new `file` group), `run: () => void save()` from `useManuscriptUnitSave()` threaded through `buildStudioCommands` opts. Name it Save **Chapter**, not "Save All" — the hoist owns exactly ONE unit at a time (`ManuscriptUnitProvider` state carries a single `chapterId`), so "Save All" would be a lie about scope.
   - **RETIRE `Studio: Generate`** (conscious won't-fix): it would duplicate the already-shipped `Studio: Open Compose`; there is no global generate verb in this product.
   - **RETIRE `Studio: Select Model…`** (conscious won't-fix): model selection lives in the chat session settings (`features/chat/components/session-settings/ModelsSection.tsx`) and the status-bar chip from (4); a palette command would be a third door to one concept.

6. **Doc edits (same slice, they are actively misleading — plan 30 §4.1 class):** in `01_skeleton.md` mark Debt #2 CLEARED-BY-DESIGN with the three shipped homes; in `06b_command_palette.md:87-93` replace the "Deferred commands (Debt #2)" table with the 1-wired/2-retired outcome; in `30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:184` and `00_OVERVIEW.md:84,92` strike "never built / blocked on Debt #2" and point at Wave 7 slice 7d.

**Tests (Definition of Done, per the PO's policy — `/review-impl` runs at wave close):**
- `components/__tests__/StudioTopBar.test.tsx` — save button disabled when clean, enabled when dirty, calls `save()` once on click; asserts it renders inside the provider.
- `components/__tests__/StudioStatusBar.test.tsx` — asserts the string `no model` NEVER renders when `useUserModels` returns a model (regression on the lying placeholder), and that the zero-model case renders the settings CTA.
- `palette/__tests__` — `Studio: Save Chapter` present and invokes `save()`; asserts `Studio: Generate` / `Studio: Select Model…` are ABSENT (retirement is machine-enforced, so a future agent can't re-add them from the stale spec).
- Live smoke (Wave 7's existing browser smoke): open studio → type in editor → top-bar dirty dot appears → ⌘⇧P → "Save Chapter" → dot clears; status bar shows a real model alias.

**Default I am picking (veto-able):** the status-bar chip shows the user's **default chat model**, not a per-panel model. If the PO wants it to mirror the active generating panel's model instead, that is a one-line source swap in step 4 and nothing else in the slice changes.

*Evidence:* frontend/src/features/studio/components/StudioFrame.tsx:131 (`<StudioTopBar>`) vs :137 (`<ManuscriptUnitProvider>` opens) and :171 (closes, before the palettes at :174+) — the top bar and command palette are BOTH outside the hoist; that nesting, not missing infra, is what blocked Debt #2. Save already exists: ManuscriptUnitProvider.tsx:72 (`save`), :216-241 (impl), :247 (5-min autosave), surfaced at EditorPanel.tsx:363-370 (`data-testid="studio-editor-save"`). The one real live defect: StudioStatusBar.tsx:38 hardcodes `t('status.modelPlaceholder', {defaultValue: 'no model'})`. Reusable model surface already on disk: frontend/src/components/model-picker/{ModelPicker.tsx,useUserModels.ts}. Spec basis: docs/specs/2026-07-01-writing-studio/01_skeleton.md:16 ("Generate/Save/model come with the panels that need them"); the 3 deferred commands: 06b_command_palette.md:87-93; the palette command set: frontend/src/features/studio/palette/useStudioCommands.ts:70-91.

### Q-30-G-PROGRESS-CHAPTER-DIM
BUILD BE-P1 (do NOT drop it). It is ~25 lines of SQL + 1 response key + ~20 lines of FE — cheaper than the defer row it would need. It contradicts no §0 sealed decision (PO-1..4 concern AN-12, G-WORKFLOWS, ui_show_panel, spec-first ordering — none touch progress).

WHY IT IS SMALL: the chapter dimension is fully present — `composition_daily_progress` PK is `(user_id, project_id, chapter_id, snapshot_date)` (migrate.py:475-483) and the differencing CTE in `DailyProgressRepo.read_aggregate` already computes per-chapter `prev_words` via `LAG(...) OVER (PARTITION BY d.chapter_id ...)` with the baseline COALESCE (daily_progress.py:94-113). It is thrown away only by the final `GROUP BY snapshot_date` (line 111). No new table, no cross-service call, no migration.

BUILDER INSTRUCTION (exact):

1. `services/composition-service/app/db/repositories/daily_progress.py`
   - `ProgressAggregate` (line 38): add `by_chapter: list[tuple[UUID, int]] = field(default_factory=list)` — chapter_id → words authored ON the anchor date.
   - In `read_aggregate` (line 82) add a THIRD query — do NOT edit `day_words_q`, copy its CTE verbatim and add `d.chapter_id` to the CTE's SELECT list (zero regression risk on the shipped differencing query):
     ```sql
     WITH s AS (
       SELECT d.chapter_id, d.snapshot_date, d.words,
              COALESCE(LAG(d.words) OVER (PARTITION BY d.chapter_id ORDER BY d.snapshot_date), b.words) AS prev_words
       FROM composition_daily_progress d
       LEFT JOIN composition_progress_baseline b
         ON b.user_id = d.user_id AND b.project_id = d.project_id AND b.chapter_id = d.chapter_id
       WHERE d.user_id = $1 AND d.project_id = $2 AND d.snapshot_date <= $3
     )
     SELECT chapter_id, words FROM (
       SELECT chapter_id,
              (CASE WHEN prev_words IS NULL THEN 0 ELSE GREATEST(words - prev_words, 0) END)::int AS words
       FROM s WHERE snapshot_date = $3
     ) x WHERE x.words > 0 ORDER BY x.words DESC, x.chapter_id LIMIT 50
     ```
     (`snapshot_date = $3` = the anchor day only; `words > 0` drops baseline-only/untouched chapters; the same `user_id` predicate keeps M5 isolation.)

2. `services/composition-service/app/routers/progress.py` — in `get_progress`'s return dict (lines 120-127) add:
   `"by_chapter": [{"chapter_id": str(cid), "words": w} for cid, w in agg.by_chapter],`
   Nothing else changes: the `_gate_book` VIEW gate (line 116) already runs before the read, so no new tenancy surface.

3. FE type: `frontend/src/features/composition/types.ts` — add `by_chapter: { chapter_id: string; words: number }[]` to the progress response type (it is additive; the legacy `ProgressPanel` ignores it).

4. FE panel (the Studio `progress` panel ported per M2): render a "by chapter (today)" section under the sparkline, `data-testid="progress-by-chapter"`, one row per entry, `words.toLocaleString()`. LABELS ARE FE-SIDE — the BE returns NO title (composition-service does not own chapter titles; `BookClient.get_chapter_sort_orders` (book_client.py:142) returns sort_order only, and adding a title round-trip to a free read is not worth it). Resolve titles exactly like `BookReaderPanel.tsx:98`: `booksApi.listChapters(token, bookId, { lifecycle_state: 'active', limit: 100 })` (keep limit ≤100 — a larger limit silently falls back to 20) and build an id→title map. If an id is NOT in the loaded page, render the fallback `Chapter ${chapter_id.slice(0, 8)}` — NEVER omit the row and never label it "unknown chapter" (the paged-join-mislabels-absent bug class). Empty `by_chapter` ⇒ hide the section entirely.

5. Tests (both required):
   - composition pytest, real SQL, `pytestmark = pytest.mark.xdist_group("pg")`: seed a baseline of 500 for ch A; report A=800 and B=200 on the anchor date (B has baseline 0) → `by_chapter == [(A, 300), (B, 200)]` sorted desc; a chapter whose anchor-day snapshot equals its previous snapshot is ABSENT (words=0); a second user's rows are invisible.
   - vitest on the studio progress panel: 2 rows render with titles from the mocked chapter list, and an id absent from the list renders the `Chapter <8-char>` fallback.

Also note for the builder (the CONCERN half of the question, already settled by the plan, not re-opened here): the panel PORT itself is BE-NONE — `ProgressPanel.tsx` exists and works; the only MUST-BUILD BE for M2 is BE-P2 (the per-user goal table, a tenancy fix). And the "becomes write-only" risk is already governed by GG-4 (§1 of plan 30): `ChapterEditorPage` must NOT be retired before the ports land, so the write/read loop is never open.

*Evidence:* services/composition-service/app/db/repositories/daily_progress.py:94-113 — the CTE already partitions by `d.chapter_id` (`LAG(d.words) OVER (PARTITION BY d.chapter_id ORDER BY d.snapshot_date)`) with the baseline COALESCE; line 111's `GROUP BY snapshot_date` is the single statement that collapses the chapter dimension. Table: services/composition-service/app/db/migrate.py:475-483 (`PRIMARY KEY (user_id, project_id, chapter_id, snapshot_date)`). Router that must widen: services/composition-service/app/routers/progress.py:120-127 (response dict, VIEW gate already applied at :116). FE title source pattern: frontend/src/features/studio/panels/BookReaderPanel.tsx:98 (`booksApi.listChapters(..., { lifecycle_state: 'active', limit: 100 })`). No title on the BE side: services/composition-service/app/clients/book_client.py:142-168 returns sort_order only.

### Q-30-SPEC02-NEW-CHAPTER-DEAD
FIX NOW — add as **Wave 0 row X-11** (size S; Wave 0 already carries live-drift XS/S fixes like X-2). It is NOT a one-line prop pass: the break is at StudioSideBar (which has no `onNewChapter` prop at all), and a naive book-service-only create is INVISIBLE in a Work-backed book. Build exactly this:

1) NEW hook `frontend/src/features/studio/manuscript/useNewChapter.ts` (logic lives in a hook, not the view — CLAUDE.md React-MVC):
   `export function useNewChapter(bookId: string, token: string | null, bookLanguage?: string)` → `{ createChapter: () => Promise<string | null>, creating: boolean }`.
   - Internally call `useWorkResolution(bookId, token)` (the SAME hook `useManuscriptTree.ts:51` uses → shared react-query cache, no extra fetch) and derive `projectId` with the identical shape as `useManuscriptTree.ts:52-57` (`status==='found' ? work.project_id : candidates[0]?.project_id ?? null`).
   - `createChapter()`:
     a. `const title = t('manuscript.untitledChapter', { defaultValue: 'Untitled chapter' })`
     b. `const ch = await booksApi.createChapterEditor(token, bookId, { original_language: bookLanguage ?? 'auto', title })` — OMIT `sort_order` (server.go:1699-1701 auto-appends `MAX(sort_order)+1`); OMIT `body` (empty draft is valid).
     c. **If `projectId` is non-null** (Work-backed book): `await compositionApi.createNode(projectId, { kind: 'chapter', title, chapter_id: ch.chapter_id, status: 'empty' }, token)` — parent_id/rank omitted (root-level, server-assigned rank). WITHOUT this the row never shows: `useManuscriptTree.ts:85-90` renders ONLY outline nodes for a Work, so the create would 201 and vanish (repo's `silent-success-is-a-bug` class).
     d. On any throw: `toast.error(...)` (mirror `ChaptersTab.tsx:71`) and return null. Guard re-entry with `creating`.
     e. Return `ch.chapter_id`.

2) `StudioFrame.tsx` — it already holds `bookLanguage` (l.46), `accessToken`, `host`, `setSelectedNodeId`. Add:
   `const { createChapter } = useNewChapter(bookId, accessToken, bookLanguage);`
   `const onNewChapter = useCallback(async () => { const id = await createChapter(); if (!id) return; setSelectedNodeId(id); host.focusManuscriptUnit(id); }, [createChapter, host]);`
   and pass `onNewChapter={onNewChapter}` into `<StudioSideBar>` (l.146-153).

3) `StudioSideBar.tsx` — ADD `onNewChapter?: () => void | Promise<void>` to `Props` (l.11-20) and forward it to `<ManuscriptNavigator>` (l.34-40). This is the actual missing link.

4) `ManuscriptNavigator.tsx:112-121` — keep the prop optional/`disabled={!onNewChapter}` (other hosts/tests rely on it), but the click must refresh the tree it owns:
   `const handleNew = useCallback(async () => { if (!onNewChapter) return; await onNewChapter(); reload(); }, [onNewChapter, reload]);` → `onClick={handleNew}`. (`reload` already comes from `useManuscriptTree`, l.55.)

5) i18n: add `manuscript.untitledChapter` + `manuscript.newChapterFailed` to `frontend/src/i18n/locales/en/studio.json` (next to the existing `manuscript.newChapter`), then regenerate the other locales with `scripts/i18n_translate.py`.

TESTS (all three required — the shipped bug proves the component test alone is worthless):
- `frontend/src/features/studio/components/__tests__/StudioFrame*.test.tsx` (or a new one): render the frame and assert `screen.getByTestId('manuscript-new')` is **NOT disabled** — this is the exact regression that shipped (green component test + dead app).
- `useNewChapter.test.tsx`: (a) NO Work → only `booksApi.createChapterEditor` called, with `original_language` = the book's language (falls back to `'auto'`); (b) WITH Work → `compositionApi.createNode` called with `{ kind:'chapter', chapter_id: <the id returned by createChapterEditor> }` (the anti-invisible-create assertion); (c) failure → toast, no `focusManuscriptUnit`.
- `ManuscriptNavigator.test.tsx`: extend l.168-172 — after clicking `manuscript-new`, the tree fetch is re-issued (`reload` ran).
DoD: `/review-impl` at wave close (PO policy), plus a live browser smoke on :5199 (agent→GUI/`+`→new chapter opens in the editor and appears in the tree) — a raw unit-green does not prove this affordance.

Default I picked (veto-able): the `+` creates an **Untitled chapter immediately** (VS Code "new file" semantics) rather than opening a title/language dialog like `ChaptersTab`; the user renames in the editor. Language defaults to the book's `original_language`, or `'auto'` if unset.

*Evidence:* frontend/src/features/studio/components/StudioSideBar.tsx:11-20 (Props has NO onNewChapter) + :34-40 (ManuscriptNavigator rendered without it) — the true break; StudioFrame.tsx:145-154 (only SideBar call site, no handler); ManuscriptNavigator.tsx:115-116 (`onClick={onNewChapter} disabled={!onNewChapter}`); ManuscriptNavigator.test.tsx:168 asserts disabled-when-absent (green test, dead button). Backend already complete: services/book-service/internal/api/server.go:297 → :1619 createChapter (JSON branch needs only original_language, :1645; sort_order 0 auto-appends, :1699); FE client exists at frontend/src/features/books/api.ts:319 (createChapterEditor), used by pages/book-tabs/ChaptersTab.tsx:63. Outline trap: frontend/src/features/studio/manuscript/useManuscriptTree.ts:59,85-90 (Work ⇒ outline nodes only) — fixed via frontend/src/features/composition/api.ts:201 createNode → services/composition-service/app/routers/outline.py:549 (NodeCreate accepts kind/parent_id/title/chapter_id).

### Q-30-BE-M2-MISSING
**BE-M2 was NOT dropped — it is in spec 30 twice, under two OTHER IDs. This is an ID-aliasing defect, not a missing work item.** One work item = `gather_motifs` packer lens, three names:
- spec 30 **X-7** (`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:340`) — the cross-cutting-blocker row
- spec 30 **BE-19** (`:313`) — a duplicate row that literally says *"See §8 X-7"*
- spec 33 **BE-M2** (`33_motif_studio.md:441`) — the build-detail row (the only place with the full contract)

It is missing from Wave 3's *prereq line* (`30:384`) **on purpose and correctly**: X-7 is a **Wave 0 gate item** (`30:345` — *"Wave 0 gate: X-1, X-2, X-4, X-5, X-7 green"*), so by the time Wave 3 opens it is already built. Wave 3 restates it as its **HARD GATE** at `30:377` (*"X-7 (gather_motifs) must be green"*), which is the same sentence spec 33 §6 writes as *"BE-M2 green"* (`33:696`). The two specs agree; only the label differs. Nothing contradicts §0 PO-1..4.

**Builder instruction (do exactly this — 2 doc edits + no code change to the plan's substance):**

1. **Canonical ID = `X-7`** (master plan owns the ID space). Treat `BE-19` and `BE-M2` as *aliases of X-7*, never as separate slices. **Do not build it three times, and do not build it in Wave 3** — build it ONCE in **Wave 0**, to spec 33's BE-M2 contract (`33_motif_studio.md:441` is the only row that carries the signature, the scene→chapter→arc resolution chain, `sanitize_lore`/SEC3, the best-effort-`""` rule, and the ≤3-binding cap — the Wave-0 builder MUST read it, not just X-7's one-liner).

2. **Edit `30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:384`** (Wave 3's `**BE prereqs**` line) — append to the end of the prereq enumeration, verbatim:
   > · **X-7 = spec 33's BE-M2 = BE-19** (`gather_motifs`) — **one item, three IDs; BUILT IN WAVE 0, not here.** Wave 3 only *verifies* it is green (that is this wave's HARD GATE above). Its build contract lives in [`33_motif_studio.md`](33_motif_studio.md) **§5 BE-M2** — read that row, not X-7's summary. **Spec 33's BE-M* list is BE-M1 · BE-M2 · BE-M3 · BE-M4 (~~BE-M5~~ deleted); BE-M2 is absent from this line because it is Wave 0's, not because it does not exist.**

3. **Edit `30:340` (X-7)** — append: `**Aliases: BE-19 (this doc, :313) · BE-M2 (spec 33 §5, :441 — the authoritative build contract).**`
   **Edit `30:313` (BE-19)** — append: `**= X-7 = spec 33 BE-M2. Alias row only — do NOT budget it as a second slice.**`

4. **Wave 0's Definition of Done gains a literal step:** the BA12-style effect test named in both X-7 and BE-M2 (*the packed prompt CHANGES when a motif binding changes*; pattern = `test_pack_arc_wired.py`), plus `/review-impl` per PO policy #2.

**Why this is not "just a doc nit":** X-7's own row states building the motif GUIs without it ships *"a beautiful editor for a field with no consumer"* — the stored-but-unread bug CLAUDE.md bans. Verified against code: `grep -rn "motif" services/composition-service/app/packer/` returns **zero hits** today, while `gather_arc` (the lens to mirror) is at `app/packer/lenses.py:257`. The item is genuinely unbuilt, so a builder who reads only spec 30's Wave-3 prereq line and skips it would ship exactly that bug. The alias note above is what prevents both failure modes (skipping it, and building it twice).

*Evidence:* Spec 30 `docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:340` (X-7 = `gather_motifs`), `:313` (BE-19, "See §8 X-7"), `:345` ("Wave 0 gate: X-1, X-2, X-4, X-5, X-7 green"), `:377` (Wave 3 "HARD GATE: X-7 must be green"), `:384` (the Wave 3 prereq line that omits it). Spec 33 `33_motif_studio.md:441` (BE-M2 full build contract), `:696` (Wave 3a gate "BE-M2 green"), `:445` (BE-M5 deleted). Code: `grep -rn "motif" services/composition-service/app/packer/` → **0 hits** (lens genuinely unbuilt); mirror target `services/composition-service/app/packer/lenses.py:257` = `async def gather_arc(`.

### Q-30-OCC-CHIP-SERIALIZATION
SERIALIZE — but the spec's stated REASON is only half right, and a builder following it verbatim would write dead code for Wave 3 and miss the real bug. Corrected instruction:

**(1) Extract the proven chain — do not re-derive or copy-paste it.** `useSceneInspector.ts:39-101` already implements the memory's fix and has passing tests. Extract it to a new shared hook `frontend/src/features/studio/hooks/useWriteChain.ts`:
- `entityRef = useRef<T|null>` — a live mirror of the entity (incl. `version`), kept fresh by `useEffect(() => { entityRef.current = entity }, [entity])`.
- `chainRef = useRef<Promise<void>>(Promise.resolve())`; `enqueue(run)` does `chainRef.current = chainRef.current.then(run, run)` (BOTH arms — a rejected link must not break the chain).
- `run` reads the version from `entityRef.current`, NOT from its closure (the prior link just bumped it).
- Capture `targetId` at CALL time; if `entityRef.current.id !== targetId` when the link finally runs, DROP the queued write (applying a stale field to a newly-selected entity is the worse bug).
Refactor `useSceneInspector` to consume it — its existing tests are the regression net and MUST stay green.

**(2) Wave 1 — canon-rule severity/scope/active selects: the OCC premise is TRUE. Chain them.** `canon.py:141-172` accepts `If-Match` and raises 412 `CANON_VERSION_CONFLICT`, backed by `canon_rules.py:105-136` (`AND version = $n` … `version = version + 1`). Route every instant-commit select in the new studio canon panel through `useWriteChain`. Keep the 412 handler: after serialization, a genuine 412 IS an external edit — only then show "changed elsewhere — reloaded". The legacy `CanonRulesPanel.tsx:25-27` is form-submit-gated so it never had the bug; the port to instant-commit selects is what INTRODUCES it.
⚠ TRAP: `if_match: str | None = Header(default=None)` (`canon.py:149`) — If-Match is OPTIONAL. The lazy way to make the 412 disappear is to simply not send it. DO NOT. Canon rules are EDIT-grant shared; omitting If-Match silently clobbers a collaborator's concurrent edit. Always send If-Match AND serialize.

**(3) Wave 3 — motif-binding chips: the OCC premise is FALSE. Chain them anyway, for ORDERING.** The bind/unbind/role/chain routes (`plan.py:855, 946, 1009, 1061`) take NO `If-Match` and NO `expected_version`; `_bind_scene_motif` (`plan.py:801-850`) is a delete+insert on the `motif_application` CHILD ledger and never touches `outline_node.version`. It CANNOT 412 — so write NO 412 handler and NO "changed elsewhere" toast here (dead code + a false accusation). The real defect is that the bind is a full REPLACE (`delete_for_nodes` → `insert_many`, `plan.py:843-844`): two rapid chip clicks arriving out-of-order leave the WRONG motif bound with NO error surfaced anywhere — the repo's `silent-success-is-a-bug` class. Serialization fixes exactly that.
Because the binding lens lives IN `scene-inspector`, scene-level motif binds MUST share the SAME `useWriteChain` instance as the pov/present/location field patches (same target entity = the node). Do not stand up a second parallel chain over one node — a bind's response `setNode` can otherwise clobber a concurrent field patch's fresher node.

**(4) Guard rail — the chapter-level motif swap is NOT a chip.** `apply_motif_swap` (`plan.py:920-940`) archives scenes, regenerates them, and returns an `undo_token` — a destructive, expensive op. It stays behind an explicit confirm + `disabled while pending`. Do not let "make bindings instant-commit chips" sweep it in.

**(5) Definition of Done — the test that would have caught it.** A vitest per surface that fires two writes WITHOUT awaiting between them (mock resolves the 1st only after the 2nd is dispatched), asserting: (a) BOTH writes land, (b) the 2nd carried the version the 1st returned, (c) no "changed elsewhere" toast fires, (d) a write queued against a de-selected entity is dropped. The memory records that every existing unit test awaited patches sequentially — which is precisely why the green suite hid this bug. A test that awaits between the two calls does NOT satisfy this DoD.

DEFAULT I picked (PO may veto): serialization over the cheaper `disabled={saving}`, because disabling instant controls mid-write makes "pick two quickly" feel broken, and serialization is the only fix where both of the user's own rapid edits actually land.

*Evidence:* REFERENCE IMPL (already shipped): frontend/src/features/studio/panels/useSceneInspector.ts:39-101 — nodeRef mirror (44-45), chainRef (46), targetId captured at call time (68), fresh version read from mirror (74-75), chain `.then(run, run)` (99-100).
WAVE 1 OCC CONFIRMED: services/composition-service/app/routers/canon.py:141-172 (If-Match header → 412 CANON_VERSION_CONFLICT); services/composition-service/app/db/repositories/canon_rules.py:105-136 (`AND version = $n`, `version = version + 1`). Optional-If-Match trap: canon.py:149 `if_match: str | None = Header(default=None, alias="If-Match")`.
WAVE 3 OCC REFUTED: services/composition-service/app/routers/plan.py:855-867 (swap_node_motif — no If-Match param), :946-956 (clear_node_motif — no If-Match), :1009, :1061; services/composition-service/app/routers/plan.py:801-850 (_bind_scene_motif — delete_for_nodes + insert_many on motif_application at :843-844, outline_node.version untouched). outline_node's only version bump is services/composition-service/app/db/repositories/outline.py:1052, not reachable from the bind path.
LEGACY (no bug — form-gated, hence the port introduces it): frontend/src/features/composition/components/CanonRulesPanel.tsx:25-27,60.

### Q-30-WAVE3-SINGLE-SERVICE
CONFIRMED — Wave 3 stays SINGLE-SERVICE. Build BE-6/BE-M4 as a composition-service REST route; do NOT add any name to FE_BRIDGE_TOOL_ALLOWLIST. (The concern is correct on the code; this is the ratified instruction, not a re-litigation.)

BUILDER INSTRUCTION (Wave 3b):

1) DO NOT TOUCH `services/api-gateway-bff/src/tools/tools.controller.ts`. The allowlist (lines 24-30) is a 5-member set of PROPOSE (mint-a-confirm-token) + one POLL tool; its stated contract is "NOTHING here writes or deletes" and every member is spend-adjacent. A free, ranked, synchronous read does not belong there. Adding a 6th name would (a) edit a 2nd service ⇒ workflow-gate.py's cross-service live-smoke trigger fires, (b) route an FE read through ai-gateway MCP federation for zero benefit, and (c) require the tools.controller.spec.ts allowlist assertion to be updated. Wave 3's diff must stay under `services/composition-service/**` + `frontend/**` only.

2) ADD THE ROUTE in `services/composition-service/app/routers/motif.py` (router prefix is already `/v1/composition`, line 53):
   `@router.get("/works/{project_id}/motifs/suggest")`
   Signature: `project_id: UUID` (path) · `chapter_id: UUID` (REQUIRED query — FastAPI gives the 422 spec 33 wants) · `limit: int = Query(default=10, ge=1, le=50)` · `detail: str = Query(default="full", pattern="^(summary|full)$")` · `user_id: UUID = Depends(get_current_user)` · `works: WorksRepo = Depends(get_works_repo)` · `outline: OutlineRepo = Depends(get_outline_repo)` · `retriever: MotifRetriever = Depends(get_motif_retriever)` · `grant: GrantClient = Depends(get_grant_client_dep)`.
   Body = a lift of the MCP handler (`app/mcp/server.py:2224-2268`), using the REST gate pattern already shipped in `app/routers/conformance.py:363-372`:
   - `work = await works.get(project_id)`; None ⇒ 404 "work not found".
   - `await authorize_book(grant, work.book_id, user_id, GrantLevel.VIEW)`; OwnershipError ⇒ 404, InsufficientGrant ⇒ 403 (identical to the MCP `_book_or_deny(..., VIEW)`).
   - `node = await outline.get_node(chapter_id)`; **keep the per-tool IDOR check verbatim** — `if node is None or node.project_id != project_id: raise HTTPException(404, detail=_NOT_FOUND)` (uniform H13 no-oracle 404, `motif.py:69`). Dropping this is a cross-tenant read of another Work's node under this book's gate.
   - `candidates = await retriever.retrieve(user_id, book_id=work.book_id, project_id=project_id, genre_tags=list(getattr(work, "genre_tags", []) or []), language=getattr(work, "language", None) or "en", beat_role=None, tension=getattr(node, "tension_target", None), limit=limit)`.
   - Project through `apply_response_contract([... _motif_view(c.motif, user_id) ...], ref_fields=_MOTIF_REF_FIELDS, detail=detail)` (import the same helpers the MCP layer uses) and return `{"candidates": [{"motif": motif_dicts[i], "score": c.score, "match_reason": c.match_reason} for i, c in enumerate(candidates)], **meta}`.

3) CONTRACT NIT — RETURN THE ENGINE'S KEYS VERBATIM. `MotifRetriever` emits `match_reason = {tension, genre, precond, cosine[, degraded]}` (`motif_retrieve.py:249-256`). Spec 33 §BE-M4 prose writes `{tension, genre, precondition, semantic}`. Do NOT rename in the REST transport only — that is the `cross-service-normalization-bug-class` (one concept, two names, MCP vs REST). Ship `precond`/`cosine` (+ `degraded`) on both transports and let the FE render the human labels ("precondition", "semantic match"). Fix the spec-33 prose to match.

4) FE (3b): add `motifApi.suggest(projectId, chapterId, {limit, detail}, token)` in `frontend/src/features/composition/motif/api.ts` (relative `/v1/composition/...`, Bearer JWT — the same shape as the other motifApi reads) + a `useMotifSuggest` hook next to `useMotifCandidates.ts`. The ✨ Suggest button in the scene-inspector Motifs section / PlanDrawer calls THAT, not the FE bridge. Today no FE suggest call exists — `useMotifCandidates.ts:13` falls back to an unranked `motifApi.list({scope:'all'})`.

5) TESTS (Wave-3b DoD): (a) composition unit/route test — 200 ranked shape, 404 on a foreign `chapter_id` (IDOR), 403 under-grant, 422 on missing `chapter_id`; (b) an assertion that `FE_BRIDGE_TOOL_ALLOWLIST` still has exactly its 5 existing members (`tools.controller.spec.ts` already guards it — leave it green, do not edit it); (c) VERIFY evidence may legitimately state `live infra unavailable`/no-live-smoke-needed BECAUSE the wave is single-service — that is the whole point of this decision.

DEFAULT NOTED FOR PO VETO: the embed of the query text inside `retrieve()` (`motif_retrieve.py:220` → `embed_query`) is a platform embed call that degrades to genre+tension ranking on failure — it is NOT a BYOK spend and needs NO model_ref/ModelPicker and NO confirm token. If the PO wants motif-suggest to be a user-model-priced call, that changes it into a propose/confirm op and this decision would flip — they can veto here; otherwise build it as the free read.

*Evidence:* services/api-gateway-bff/src/tools/tools.controller.ts:18-30 (allowlist = 5 propose/poll spend-gated tools; "NOTHING here writes or deletes") · services/api-gateway-bff/src/gateway-setup.ts:354 (`pathFilter: pathname.startsWith('/v1/composition')` — a new composition REST route needs ZERO gateway diff, so the wave's git diff touches exactly one `services/` prefix and the cross-service live-smoke trigger never fires) · services/composition-service/app/mcp/server.py:2224-2268 (the engine handler to lift, incl. the `node.project_id != pid` IDOR check) · services/composition-service/app/db/repositories/motif_retrieve.py:200-256 (pure SQL+cosine read; match_reason keys = tension/genre/precond/cosine) · services/composition-service/app/deps.py:205 (`get_motif_retriever`) · services/composition-service/app/routers/motif.py:53 (prefix `/v1/composition`) + :69 (`_NOT_FOUND` uniform 404) · services/composition-service/app/routers/conformance.py:363-372 (the exact project_id→book VIEW-gate pattern to copy) · frontend/src/features/composition/motif/hooks/useMotifCandidates.ts:13 (no suggest call exists today — unranked list fallback)

### Q-30-G-POLISH-HALF-DARK
BUILD the producer; do NOT pass `proposals` into QualityCriticPanel. Four slices, Wave 1.

SLICE 1 — new panel `frontend/src/features/studio/panels/QualityHealPanel.tsx`:
- `useStudioPanel('quality-heal', props.api)`; `const host = useStudioHost(); const { accessToken } = useAuth();`
- Work gate, copied from QualityCriticPanel.tsx:29/39: `const work = useQualityWork(host.bookId, accessToken); if (work.kind !== 'ready') return <QualityWorkGate state={work} testIdPrefix="quality-heal" />;` (unconsulted != empty).
- Chapter = the OPEN editor chapter via `useManuscriptUnit()?.state.chapterId`. Do NOT copy QualityCriticPanel's chapter picker: the critic is read-only, but Apply WRITES into the live editor, so a picker lets a user heal chapter A and write it into chapter B. No open chapter => render a hint ("Open a chapter to polish it"), never a disabled silent no-op.
- `<ModelPicker capability="chat" .../>` (same as QualityCriticPanel.tsx:71-77).
- Render `<PolishPanel projectId={work.projectId} chapterId={chapterId} token={accessToken} modelRef={modelRef} onApply={handleApply} />`. PolishPanel.tsx:148-154 ALREADY passes `proposals={p.proposals}` into QualityReportSection, so `_hasProposedFix` (QualityReportSection.tsx:30, called :90) FIRES and the `violation-has-fix` badge (:95) renders for a Studio user. That alone cures the half-dark.

SLICE 2 — the Apply seam (the non-free part). `onApply(healedText)` is a WHOLE-DOC replace. A raw `editorRef.current.setContent()` would silently fail to save: TiptapEditor.tsx:172 early-returns from `onUpdate` while `isExternalUpdate` is true and `setContentHandler` (:252-257) sets that flag, so setContent never reaches the hoist's `setBody`, AND it bypasses Studio's single AI-write chokepoint (useManuscriptCheckpoints.ts:5-11), losing the restore point. So widen the chokepoint:
(a) `frontend/src/features/chat/context/editorBridge.ts:22-26` — `ApplyProposedEdit` operation union += `'replace_document'`.
(b) `frontend/src/features/studio/manuscript/unit/ManuscriptUnitProvider.tsx:93-97` (type) + `:307-318` (impl) — same widening; for `'replace_document'`: build the doc by paragraph-splitting `params.text` (mirror ChapterEditorPage.tsx:593-598), call `handle.setContent(doc)` AND then `setBody(doc, params.text)` explicitly (setContent suppresses onUpdate, so without setBody the hoist never dirties and the heal is never saved). Return false when `editorRef.current` is null.
(c) `useManuscriptCheckpoints.ts:134` — map `'replace_document'` to kind `'replace'` (leave the 'insert'|'replace' union alone).
(d) QualityHealPanel's `handleApply` calls `getEditorTarget()?.applyProposedEdit?.({ operation: 'replace_document', text: healedText })`. EditorPanel.tsx:97-102 registers the CHECKPOINT-WRAPPED fn, so a heal Apply captures a pre-edit restore point exactly like propose_edit Apply. Falsy/false return => surface an error (no silent no-op).

SLICE 3 — register it: `catalog.ts` add `{ id: 'quality-heal', component: QualityHealPanel, titleKey/descKey/guideBodyKey: 'panels.quality-heal.*', category: 'quality' }` beside quality-critic (catalog.ts:268); add the tile to QualityHubPanel; add the `en` i18n keys.

SLICE 4 — QualityCriticPanel.tsx:80 KEEPS its no-`proposals` mount, and that is CORRECT, not a bug: `POST /works/{project_id}/self-heal/propose` (services/composition-service/app/routers/plan.py:199) is the ONLY self-heal route — proposals are computed by a PAID LLM pass and never persisted, so there is nothing cached to pass in; making the critic fetch them would silently spend the user's money on an advisory panel. Instead: when `critic.violations.length > 0`, render a "Propose fixes" button calling `host.openPanel('quality-heal', { focus: true })`. The badge then fires where the proposals actually live. (DEFAULT I am choosing — PO may veto if they want the critic to auto-run the paid propose pass.)

TESTS (a slice is not done without them):
- `__tests__/QualityHealPanel.test.tsx`: (1) renders QualityWorkGate on unavailable/no-work; (2) with a ready Work + open chapter, mock `compositionApi.proposeSelfHeal` to return a proposal whose `before` matches a critic violation's `span`, then ASSERT `getByTestId('violation-has-fix')` is present — this is the test that proves the half-dark is cured; asserting the panel merely mounts does NOT count; (3) Apply calls the bridge with `operation:'replace_document'` + the healed text, and a `false` return renders an error rather than a success.
- ManuscriptUnitProvider test: `applyProposedEdit({operation:'replace_document'})` calls `handle.setContent` AND `setBody` (hoist dirties).
- useManuscriptCheckpoints test: a replace_document apply captures a checkpoint with kind 'replace'.

MCP tool: NOT this wave and NOT a violation. Self-heal propose is a fixed propose→verify LLM pipeline, not an LLM deciding actions, so the MCP-first invariant exempts it and the REST route is legitimate. Track the optional `compose_self_heal` MCP tool as its own row; it does not gate this fix.

`/review-impl` runs at wave close per the PO policy; any bug it finds is fixed before the wave closes.

*Evidence:* frontend/src/features/studio/panels/QualityCriticPanel.tsx:80 mounts <QualityReportSection> with no `proposals`; QualityReportSection.tsx:39 defaults `proposals = []` so `_hasProposedFix()` (:30, called :90) always returns false and the `violation-has-fix` badge (:95) is unreachable in Studio — PolishPanel.tsx:148-154 is the only mount that passes it, and PolishPanel has no Studio panel (catalog.ts:266-270 lists quality/-promises/-critic/-coverage/-canon, no heal). Producer-only route: services/composition-service/app/routers/plan.py:199 `POST /works/{project_id}/self-heal/propose` (compute-on-demand, paid, not persisted — nothing cached to pass into the critic). Apply-seam trap: TiptapEditor.tsx:172 (`onUpdate` early-returns when `isExternalUpdate`) + :252-257 (`setContentHandler` sets that flag) => `setContent` never reaches the hoist's `setBody`; ManuscriptUnitProvider.tsx:93-97/:307-318 only supports insert_at_cursor|replace_selection; useManuscriptCheckpoints.ts:5-11 declares `applyProposedEdit` the single AI-write chokepoint and EditorPanel.tsx:97-102 registers the checkpoint-wrapped fn via editorBridge.ts:22-26/48.

### Q-30-22-NOFE-ROUTES-NOT-ENUMERATED
DECIDE: the claim is CORROBORATED and the list is now enumerated — I re-ran the FastAPI introspection sweep at HEAD. Do NOT wait for Wave 6: publish it as a MACHINE-GENERATED, TEST-ENFORCED register as the first slice of Wave 1 (a hand-typed table in a doc goes stale the moment Wave 2 lands a route; this repo's own lesson is "checklist ⇒ test the effect").

MEASURED AT HEAD (composition-service `app.main:app.routes`, dummy env, PYTHONPATH=sdks/python): **159 routes total = 143 public `/v1/composition/*` + 10 `/internal/*` + 6 infra** (docs, redoc, openapi.json, health, metrics, /v1/composition/ping). The plan's §3.1 "155 (147 public · 9 internal · 3 infra)" is STALE — update it to these numbers.

**The 21 public NO-FE-CONSUMER routes** (method+path never constructed in non-test `frontend/src`; file-local `const BASE = '/v1/composition…'` resolved, so `authoring-runs` is NOT a false positive):
1. GET /v1/composition/arc-templates/catalog
2. GET /v1/composition/arcs/{node_id}
3. PATCH /v1/composition/arcs/{node_id}
4. DELETE /v1/composition/arcs/{node_id}
5. POST /v1/composition/arcs/{node_id}/restore
6. POST /v1/composition/books/{book_id}/arcs
   (2–6 exactly reproduce G-ARC-SPEC-CRUD's "all 5 NO-FE-CONSUMER" — independent confirmation)
7. POST /v1/composition/authoring-runs  (FE has list/get/gate/start/pause/resume/close/report/accept/reject/revert-all — but NO create)
8. POST /v1/composition/books/{book_id}/plan/runs/{run_id}/checkpoint
9. POST /v1/composition/books/{book_id}/plan/runs/{run_id}/link
10. GET /v1/composition/books/{book_id}/plan/runs/{run_id}/passes
11. POST /v1/composition/books/{book_id}/plan/runs/{run_id}/passes/{pass_id}/run
    (8–11 = G-PLANFORGE-PASS-RAIL's "4 REST routes, all NO-FE-CONSUMER" — confirmed)
12. GET /v1/composition/import-sources
13. POST /v1/composition/import-sources
14. GET /v1/composition/import-sources/{import_source_id}
15. DELETE /v1/composition/import-sources/{import_source_id}
16. GET /v1/composition/motifs/book/{book_id}
17. POST /v1/composition/motifs/{motif_id}/adopt
18. POST /v1/composition/works/{project_id}/chapters/{chapter_id}/approve
19. GET /v1/composition/works/{project_id}/chapters/{chapter_id}/prose
20. PUT /v1/composition/works/{project_id}/chapters/{chapter_id}/prose
21. POST /v1/composition/works/{project_id}/scenes/{node_id}/suggest-cast

TWO WAIVERS the naive grep gets wrong — the builder MUST encode them, not "fix" them:
- POST /v1/composition/works/{project_id}/selection-edit — IS consumed, as an SSE stream URL (`compositionApi.selectionEditUrl()`, frontend/src/features/composition/api.ts:393 → hooks/runCompositionGeneration.ts:44). It has no `method:'POST'` literal, so a verb-aware grep reports it as orphaned. NOT a gap.
- POST /v1/composition/motifs/{motif_id}/adopt — the capability is reached through the FE→MCP bridge, not REST (see the comment at frontend/src/features/composition/motif/api.ts:351, "adopt mints via the bridge"). Keep the row, flagged `waived: bridge`.
(21 genuine + selection-edit counted naively = the plan's "~22". The claim held; it was just never written down.)

BUILD SLICE — "W1-S0 · route-coverage register" (do it before any other Wave 1 work; ~1h):
a) NEW `scripts/fe-route-coverage.py` (cross-platform, mirrors `scripts/ai-provider-gate.py` conventions). It MUST: (i) import `app.main:app` with dummy env (COMPOSITION_DB_URL / INTERNAL_SERVICE_TOKEN / JWT_SECRET / CONFIRM_TOKEN_SIGNING_SECRET) and `sys.path` += `sdks/python` — FastAPI introspection, NOT a `@router.` grep (authoring_runs.py:275-281 registers 4 routes via `router.add_api_route(...)` which a decorator grep MISSES); (ii) walk `frontend/src/**/*.{ts,tsx}`, resolving FILE-LOCAL `const NAME = '/...'` before substituting the remaining `${…}` holes with a wildcard — a repo-wide const map is WRONG, `BASE` is defined with 3 different values in composition/api.ts:42, motif/api.ts:19, authoringRuns/api.ts:14 and plan-forge/api.ts:20; (iii) infer the verb from the `method:'X'` key of the call's own option object (default GET), so `GET /arcs/{id}` is not masked by the `POST /arcs/{id}/move` on the same path stem; (iv) skip `__tests__/` + `*.test.*`; (v) emit `{method, path}` JSON.
b) NEW `contracts/composition-no-fe-consumer.json` — the 21 rows above + the 2 waivers with their reason strings.
c) NEW `services/composition-service/tests/test_no_fe_consumer_register.py` — recompute the live set, assert set-equality with the JSON minus waivers, print a symmetric diff on failure. No DB ⇒ no `xdist_group` mark needed.
d) EDIT `30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md` §3.1: replace "155 (147 public · 9 internal · 3 infra) / ~22 public NO-FE-CONSUMER" with "159 (143 public · 10 internal · 6 infra) / 21 public NO-FE-CONSUMER (+2 waived)" and link `contracts/composition-no-fe-consumer.json` as the authoritative register. Add the list as Appendix C.
e) ADD TO EVERY WAVE'S DEFINITION OF DONE (alongside the mandatory `/review-impl`): "any route this wave gives a FE consumer has its row DELETED from `contracts/composition-no-fe-consumer.json` in the same commit; any route this wave ADDS without a FE consumer gets a row ADDED. The register test must be green." That converts the coverage risk into a mechanical gate the build cannot talk past.

Sane default I am picking (veto-able): the register covers composition-service ONLY (the audit's scope). Do not widen it to the other 45 services in this batch.

*Evidence:* Live sweep at HEAD 9262ed53e: `python -c "from app.main import app; ..."` with PYTHONPATH=D:/Works/source/lore-weave-mvp/sdks/python → TOTAL 159 | public 143 | internal 10 | infra 6; verb-aware FE join over frontend/src → 21 NO-FE-CONSUMER + 2 waivers. Grounding file:line — services/composition-service/app/routers/authoring_runs.py:275-281 (`router.add_api_route(...)`, invisible to a `@router.` grep, which is why introspection is mandatory); frontend/src/features/composition/authoringRuns/api.ts:14 vs api.ts:42 vs motif/api.ts:19 vs plan-forge/api.ts:20 (four different `const BASE` values ⇒ per-file const resolution required); frontend/src/features/composition/api.ts:393 + hooks/runCompositionGeneration.ts:44 (selection-edit SSE waiver); frontend/src/features/composition/motif/api.ts:351 (motif-adopt bridge waiver); docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:114 (the unenumerated "~22" claim) and :78 (the audit's own introspection note).

## Not a question (already answered by code / a sealed decision)
- **Q-30-AN12-AMENDMENT-TEXT** — ALREADY DONE — the AN-12 amendment text has landed and is committed. `docs/specs/2026-07-01-writing-studio/28_agent_native_studio.md:217-283` carries a `## AN-12 AMENDED (PO-1, 2026-07-12)` section, written IN PLACE (not forked), committed at `d0f17555e`. It cites PO-1 by name and location (:223 "Authority: 30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md §0 PO-1 (sealed 2026-07-12) · Consumed by: 37_issues_feed.md (Wave 7)"), carries the exact rationale the candidate answer names (:243 "≈2.5 of 5 sources have a human surface, not one of them is ranked", with prose_deleted_spec_node — an `error` — having no screen at all), preserves AN-12's architecture verbatim (:249-270 — no new dock panel, zero catalog.ts rows, zero panel_id enum change, byte-identical drift-lock, feed ROUTES never EDITS), restates the lifted clause struck-and-amended (:272-281), and adds an anti-reconciliation guard (:225 "read them together; do not 'reconcile' one against the other by deleting either").

CONSEQUENCE FOR THE BUILDER: Wave 7 (issues feed / spec 37) is UNBLOCKED. The "spec violation, not a shortcut" condition no longer holds. Do NOT re-write, re-open, or re-litigate this amendment — re-read 28:217-283 instead. Start Wave 7 BUILD.

ONE SMALL FIX-NOW TIDY (do it in Wave 7's first commit, ~2 lines, no behavior change): PO-1's row at 30:19 literally lifts the clause for all THREE tools (diagnostics / package_tree / find_references), but 28:266 and its mirror 37:582 say "composition_package_tree gets NO human surface. AN-12 stands for it, unamended" — wording that re-imposes a clause a SEALED §0 row lifted. They agree in substance (PO-1's Consequence column mandates only two surfaces — the StudioBottomPanel Issues tab and the find_references right-click lens — and lifting a prohibition is permissive, not compulsory), but the wording is a trip-hazard a later agent will try to "reconcile". Reword both to record it as a conscious won't-fix UNDER the lifted permission rather than as the clause surviving:
  - `28_agent_native_studio.md:266-270` — replace "composition_package_tree gets NO human surface. AN-12 stands for it, unamended." with: "composition_package_tree gets NO human surface. PO-1 lifts the clause for all three tools; we consciously decline the permission for this one (CLAUDE.md defer gate #5, won't-fix). AN-12's premise HELD for the tree: plan-hub = the tree, chapter-browser = the spine, the PH21 tray = the coverage gap. A 'book at a glance' panel would be exactly the DOCK-2 duplication AN-12 exists to prevent. Recorded so it stops re-surfacing as a gap (spec 37 IF-5 / D-1)."
  - `37_issues_feed.md:582-583` — same edit to IF-5: "PO-1 lifts the clause for all three; the amendment DECLINES it for package_tree (conscious won't-fix), and builds a surface for diagnostics and find_references only. Written into spec 28 §AN-12 AMENDED."
Test/verification for the tidy: none needed (docs-only); the assertion that must stay true is spec 37 §6's drift-lock (`py enum == contract enum == openable`, byte-identical after Wave 7).
- **Q-30-X9-WEBSEARCH-NAMESPACE** — KEEP `web_search` UNPREFIXED. Do not rename it; do not write a migration. This was already decided, implemented, and test-pinned by Track D · WS-D0 Wave 2 / CD5 — the spec's premise (an un-adjudicated namespacing violation) is factually wrong.

The answer the code gives:
- `web_search` is unprefixed BY DESIGN — it is the UNIVERSAL web-research tool (no book, no entity, writes nothing). It is hosted on provider-registry only because that is the one service allowed to make the outward provider call (Provider-gateway invariant), so it reaches `runWebSearch` in-process with no HTTP hop.
- The C-GW prefix gate does NOT drop it: `EXTRA_PREFIX_MAP.settings = ['web_']` (ai-gateway/src/config/config.ts:118-123) explicitly allows it, and catalog.spec.ts:161-162 pins that against the REAL config.
- `glossary_web_search` is already demoted in place (visibility: legacy + superseded_by: web_search) and CANNOT be renamed: (a) the C-GW gate binds a tool name to its provider, so the glossary server physically cannot answer to `web_search`; (b) existing public MCP keys scoped to `domain:glossary` still call it (mcp-public-gateway/src/scope/tool-policy.ts:173-179).
- The `external-system-mcp-must-be-namespaced` law governs EXTERNALLY FEDERATED servers, where an unprefixed tool shadows a first-party one. `web_search` is first-party, registered by exactly ONE provider, resolved through a single `toolToProvider` map. That law is precisely what guarantees no external tool can collide with it (every external tool arrives prefixed). There is no shadowing.

BUILDER INSTRUCTION (the only residual work — XS, doc-only, no code change):
1. In `docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md` §3.4 (lines ~166-168): DELETE the claim that `web_search` is a namespacing-law violation. Replace with: "`web_search` is unprefixed BY DESIGN (Track D CD5) — a universal, service-agnostic tool hosted on provider-registry per the Provider-gateway invariant. The C-GW gate keeps it via `EXTRA_PREFIX_MAP.settings = ['web_']`. The namespacing law governs EXTERNAL federation; a first-party tool on a single provider cannot shadow. CONSCIOUS EXCEPTION — closed, no action."
2. In the X-9 row (line 342): strike "Also decide the unprefixed `web_search` namespacing violation." X-9 reduces to the two real MCP sweeps (provider-registry 14 tools, catalog-service 2 tools).
3. Record the exception where an auditor will actually look, so this does not get re-opened a third time: add one row to `docs/standards/README.md`'s standards index (or the namespacing law's home section) — "Exception: first-party universal `web_search` is intentionally unprefixed; allowed via EXTRA_PREFIX_MAP.settings=['web_']; pinned by ai-gateway/test/catalog.spec.ts. See services/provider-registry-service/internal/api/mcp_web_search_tool.go:3-18."

NO code, test, or migration changes. Anyone touching the four sites listed in Evidence should read the header comments first — they already carry the full rationale.
- **Q-30-BE16-WORKFLOW-ROUTES** — Already answered by SEALED PO-2 — do not re-litigate. BE-16 and Wave 8c are OUT of plan 30's scope; Track C owns them. The residual is doc drift plus one FALSE claim in Track C's RUN-STATE. Builder does exactly this, no code in this plan:

(1) EDIT docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md — four surgical edits:
  - :310 — the BE-16 row in the BE-prereq table: strike it from active scope. Replace its Notes cell with "❌ NOT THIS PLAN — OWNED-BY-TRACK-C per PO-2 (§0). Route list retained here only as the handoff payload for Track C P-5." Do NOT delete the row (the route list is the handoff content).
  - :464-466 — the Wave 8 block: retitle to "Wave 8 — KG WRITE HOLES + WORLD MAPS"; remove "`workflows` + `workflow-proposals` + a mode-binding control" from Panels; remove "G-WORKFLOWS (M)" from Gaps; remove "BE-16" from BE prereqs; delete "· (8c) workflows" from the Split line and delete the "🔴 8c collides head-on with Track C's P-5" line (with 8c gone there is no collision left on 8c). Wave 8 = 8a + 8b only.
  - :256 — the G-WORKFLOWS register row: prefix the Status cell with "**OWNED-BY-TRACK-C (PO-2)** —" so it is never re-raised as an open hole in this plan.
  - :714 — the Track C coordination row: narrow it to 8b only (world container) — 8c is no longer this plan's.
  - :818 — defer row D-WS3-BINDING-GUI: retarget "G-WORKFLOWS (Wave 8c)" → "Track C P-5".
  No change to 38_kg_and_world.md — it ALREADY implements PO-2 correctly (:6, :17-19), including the handoff paragraph. It is plan 30 that is stale, not the spec.

(2) EDIT docs/plans/2026-07-12-track-c-completion-RUN-STATE.md:212 (and the same claim at :344) — this is a REAL correctness fix, not cosmetics. The P-5 row says the workflow rack is "cheapest" because "Their backends are all live (workflow_list, mode-bindings…)". FALSE: `workflow_list` is an MCP tool only (workflows.go:258 / mcp_server.go:68), reachable by an agent, NOT by a browser; the public REST workflows surface is empty (server.go:313 — only token-gated /internal/workflows), and mode-bindings has GET/PUT but no DELETE (server.go:291-292). Rewrite the cell to: "⚠ NOT pure-FE: the workflow rack needs BE first — public GET /workflows, GET /workflows/{slug}, DELETE /workflows/{slug}, an enablement toggle, and DELETE /mode-bindings/{mode} (reset-to-inherited). ~4 new Go routes on agent-registry (plan 30's BE-16, handed over per PO-2). mode-bindings GET/PUT are the only live public halves."

Default I am picking (PO may veto): the BE-16 row STAYS in plan 30 as a struck/OWNED-BY row rather than being deleted, because it is the only place the exact route list is written down and deleting it would silently drop the handoff — PO-2 says "the gap stays in the register… so it is not re-raised as a hole".
- **Q-30-FIND-REFERENCES-NAME-COLLISION** — Already answered — by the code AND by two sealed spec amendments. Both candidate answers are correct and are the standing instruction; no new decision is needed. The builder does exactly this:

(1) PANEL ID = `reference-shelf` (NOT `references`). Wave 6 / spec 36 EC-2. Concretely: append `"reference-shelf"` to the `panel_id` enum at `services/chat-service/app/services/frontend_tools.py:402`; add the matching row to `frontend/src/features/studio/panels/catalog.ts` (category `editor`); add `panels.reference-shelf.{title,desc,guideBody}` via `python scripts/i18n_translate.py` (18 locales, never hand-written); regen `contracts/frontend-tools.contract.json` with `WRITE_FRONTEND_CONTRACT=1 pytest`. The three-way drift-lock (`py enum == contract enum == OPENABLE_STUDIO_PANELS`, currently 57==57==57) must stay green.

(2) THE GLOSS MUST DISAMBIGUATE EXPLICITLY. In the same file, the `ui_open_studio_panel` description block (`frontend_tools.py:403-481`) gets a per-panel clause reading, verbatim in substance: "`reference-shelf` = the author's research corpus of source documents (NOT entity backlinks — that is the `composition_find_references` lens)." That gloss is the model's ONLY hint at tool-search time; without it a model choosing between "references" concepts silently no-ops (the exact bug class the `panel_id` enum was added to kill).

(3) BACKLINKS ROUTE = a NEW, BOOK-SCOPED PATH. `GET /v1/composition/books/{bid}/entity-references?entity_id=…&sources=…&limit=…`, in a NEW file `services/composition-service/app/routers/entity_references.py` (thin route over the already-built `EntityReferencesRepo`), registered in `main.py`. Do NOT touch `routers/references.py` and do NOT hang it off `/works/{pid}/references` — that path is TAKEN (see evidence). Note the scopes differ (`books/{bid}` vs `works/{pid}`), so collision is structurally impossible, not merely avoided by convention. Spec 37 §5.2 (BE-1d) also already rejected the `mcpBridge`/`mcpExecute` alternative: the FE_BRIDGE_TOOL_ALLOWLIST (`tools.controller.ts:24-30`) is exactly 5 spend-adjacent names and a free read must not widen it.

(4) THE ROUTE IS UNBUILT, NOT BLOCKED. grep confirms no `entity-references` route exists among the 31 routers. Per CLAUDE.md's anti-laziness rule this is work to WRITE in Wave 7, not a defer row. The engine is done: `EntityReferencesRepo` (8 sources) already backs `composition_find_references` at `mcp/server.py:3867`.

(5) ONE NON-OBVIOUS TRAP the specs imply but do not spell out — enum-validate `sources` (the closed set of 8 `REFERENCE_SOURCES`) ON THE ROUTE. `EntityReferencesRepo.find` deliberately RAISES on an unknown source so a typo cannot return `(0, [])`. The route must surface that as a 422; catching it into a zero would render to the author as "this entity is used nowhere" — a false, confident answer.
- **Q-30-TIER-W-GENERIC-SPINE** — SEALED + ALREADY TRUE IN CODE — inherit, do not re-litigate. Every panel in every wave drives a Tier-W (paid/canon) action with EXACTLY two calls and no others:

(1) PROPOSE — mint via the FE→MCP bridge: `mcpExecute('<composition_*>', { args: {…} }, token)` → `{ confirm_token, estimate:{estimated_usd,currency,basis} }`. NEVER a bespoke `/estimate` route.
(2) CONFIRM — `POST ${BASE}/actions/confirm?token=<confirm_token>` (Bearer JWT, token in the QUERY, NO body) → either `{outcome:'action_done', …}` (sync effects: publish, motif_adopt) or `{job_id}` → poll to terminal (LLM-spend effects: motif_mine, arc_import, conformance_run, generate, authoring_run_*). Optional pre-confirm describe: `GET ${BASE}/actions/preview?token=`.

COPY THIS EXACT PAIR: `frontend/src/features/composition/motif/api.ts:245` (`arcConformanceRunPropose`) + `:277` (`arcConformanceRunConfirm`). That is the reference implementation; a new panel that needs a Tier-W action clones it and swaps the tool name + args. The BE side needs NOTHING new: the descriptor allowlist at `services/composition-service/app/routers/actions.py:96-102` already contains all 12 descriptors, and `actions.py:183`/`:213` are the only two routes.

BUILDER RULES (add to each wave's Definition of Done):
- ADDING a new Tier-W action ⇒ add its descriptor to `_ALL_DESCRIPTORS` + an `_execute_*` branch in `actions.py`. It is a DEFECT to add any route matching `/v1/composition/actions/<name>/…` or any per-action POST. "A reviewer finding a new confirmation convention here has found a defect."
- FIX THE 3 SHIPPED 404s IN THE WAVE THAT TOUCHES CONFORMANCE (Wave 4 / G-CONFORMANCE-TRACE) — all three are FE-only deletions, no BE route is missing:
  • `motif/api.ts:223 conformanceRunEstimate` — DELETE the `POST ${BASE}/actions/conformance_run/estimate` body; replace with `mcpExecute('composition_conformance_run', { args: { project_id, scope:'chapter', chapter_id, model_ref, model_source:'user_model' } }, token)` mapped to `CostEstimate` exactly as `api.ts:245-275` does.
  • `motif/api.ts:228 conformanceRunConfirm` — DELETE the `POST ${BASE}/actions/conformance_run/confirm` + JSON body; replace with `POST ${BASE}/actions/confirm${_qs({token: confirmToken})}` + the `job_id` poll, exactly as `api.ts:277-296`.
  • `motif/api.ts:300 regenerateToBeat` AND its duplicate `motif/hooks/useMotifBinding.ts:66` — DELETE BOTH (`regenerate-to-beat` exists in no Python file; building it would itself be the §8.1 violation). Re-point `ConformanceTraceView.tsx:69`'s per-scene Regenerate at the EXISTING scene-generate: `POST /v1/composition/works/{project_id}/generate` with `{ outline_node_id: <scene id>, … }` (`services/composition-service/app/routers/engine.py:326`, body field `engine.py:92`), driven propose→confirm through the `composition.generate` descriptor (`actions.py:66`) — i.e. `mcpExecute('composition_generate', {args:{project_id, outline_node_id, …}})` → `/actions/confirm`. "To-beat" is the packer lens (X-7 `gather_motifs`), not a route.
- TESTS: (a) a vitest per new Tier-W panel asserting the confirm call URL matches `/actions/confirm?token=` (mirror `motif/__tests__/ArcConformancePanel.test.tsx:55`); (b) a repo-guard test/grep in each wave DoD: `grep -rnE "actions/[a-z_]+/(estimate|confirm)" frontend/src` MUST return empty, and no new `@router.post` under `/v1/composition/actions/` beyond `/confirm`.
- The rest of §8.1 is likewise inherited verbatim and un-negotiable per panel: AN-8 one-channel/one-tier/one-undo per object class; OCC (`expected_version` on outline_node/canon_rule/motif/structure_node, `expected_draft_version` on prose) with serialized writes behind any chip/select; grant gating derives the book from the ROW (`_arc_or_deny`) never a body `book_id`, and denial == missing row == `uniform_not_accessible()` (H13).

DEFAULT THE PO MAY VETO: none needed — this is a restatement of a sealed §0/§8.1 constraint that the code already satisfies; no product call is involved.
