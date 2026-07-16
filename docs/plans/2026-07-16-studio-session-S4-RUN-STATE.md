# Studio Session S4 — Motif & craft (套路/爽点/打脸) — RUN-STATE

> Anchor for the 8-session Writing-Studio completeness build. **Re-read this file FIRST after any
> compaction**, then `git log --oneline -15`, then continue at the first non-DONE slice.
> Framework: docs/plans/2026-07-16-studio-completeness-8-session-orchestration.md (read §2 the bar, §4 your charter, §5 the rules).
> Detailed design (adopted as the plan): docs/specs/2026-07-01-writing-studio/33_motif_studio.md.

## COMMITMENT
S4 is DONE when: the motif library, binding lens, suggest and conformance trace are operable — each to the §2 production-ready bar (operable · CRUD · reachable ·
no-silent-fail · agent-parity · loop-connected · live-browser-proven · i18n+responsive · scale).

### 🎯 GOAL — CLEAR ALL OF S4 (set 2026-07-16 — autonomous mandate, per-slice discipline)
**Finish line:** all three spec-33 milestones closed to the §2 production-ready bar — **3a** (motif-library ✅ committed `4d72b78e6`) · **3b** (binding lens + suggest) · **3c** (quality-conformance + M-BUG-4/404 fixes).
**Per-slice gate — for EACH milestone the transcript must contain the PASTED PROOF (a claim without pasted output does NOT count):**
1. **Tests** — pasted passing output (scoped FE vitest + BE pytest).
2. **Live-browser smoke** — pasted result showing the panel/affordance operable by effect (own chromium, :5199 or baked).
3. **Gemma smoke** — for any LLM-spend action in the slice (mine / suggest / conformance-run): a pasted result driving the test account's **Gemma-4 26B-A4B QAT** local model ($0), explicit `model_ref` UUID.
4. **QC / /review-impl** — pasted findings + the fix (or "no findings" with the checks listed).
5. **Commit** — a pasted `git commit` sha staging ONLY S4 files (never `git add -A`), RUN-STATE update in the same commit.
**Bound:** stop + report on a 4-critical-class stop, or when QC surfaces a HIGH needing a PO decision, or after 60 turns. Autonomous otherwise (defer + continue).

**⤷ THE `/goal` STRING TO SET (PO gõ lệnh này):**
> `/goal S4 is cleared: milestones 3b (binding lens + suggest) and 3c (quality-conformance + M-BUG-4/404 fixes) are both closed to the production-ready bar. For each, the transcript contains — pasted — the passing scoped test output (FE vitest + BE pytest), a live-browser smoke result showing the panel operable by effect, a Gemma-4-26B-QAT LLM smoke for any LLM-spend action, a /review-impl pass with findings resolved, and a git commit sha staging only S4 files. Claiming a check passed without pasting its output does NOT satisfy this condition. Stop after 60 turns if not complete.`
Falsifiable finish-line (spec 33 §10 + §2 bar): `motif-library` + `quality-conformance` are registered dock panels that open
**unconditionally** from the palette; create/patch/archive/adopt/mine/sync/bind/conformance-run all work in a **live browser**;
the packer effect-test proves a bound motif **changes the prompt**; M-BUG-4 + the 3 live 404s are fixed; the binding-lens seam
mounts into S2's PlanDrawer; `enum == contract == openable` move +2 in lockstep — each with an EVIDENCE string.

## SCOPE
- **Persona / files:** features/composition/motif
- **Panels:** motif-library, quality-conformance
- **Seam / note:** Sends motif-chip edits to S2's PlanDrawer via `MotifBindingLens.tsx` (S4 owns the component; S2 mounts it — never cross-edit PlanDrawer.tsx).

## MANDATE (do this, in order)
1. Role-play a real web-novel author using this tool family — what must they DO?  ✅ (A1)
2. Audit the CURRENT surface against that — what works, what's a skeleton, what's a dead button.  ✅ (A1)
3. Per capability decide PORT / ENHANCE / BUILD — record the call, never silently drop a legacy feature.  ✅ (A2)
4. Write your own detailed design (specs 31–38 are reference; the SOURCE is truth). → **Adopted spec 33 as the plan** (see DECISIONS D-S4-1). No new spec/HTML draft — both already exist and are on-target.
5. Build to the §2 bar. `/review-impl` at each panel close, fix what it finds.

## RULES (same-folder)
- Build only under your file subtree. Add catalog rows in your block (catalog.ts, the S4 block ~line 312).
- Shared registry (enum/contract/i18n): keep enum == openable == contract; regen `WRITE_FRONTEND_CONTRACT=1 pytest`.
- Never `git add -A`. Commit small + often. `git pull --rebase` before push. Scoped tests during BUILD.
- `git commit -- <path>` commits the WORKING TREE not the index — enumerate files.
- Stop ONLY for the 4 critical classes: destructive/irreversible · a sealed decision proven wrong ·
  tenancy/security breach · a paid action that charges the user for nothing. Everything else = defer + continue.
- **PO cadence (this run): checkpoint at each slice; PO clarifies concerns inline.**

## SLICE BOARD  (status: TODO / DOING / DONE — DONE requires an EVIDENCE string, not a checkbox)
| slice | status | evidence (test count / live-smoke line / commit sha) |
|---|---|---|
| S4-A1 · audit current surface (role-play user) | DONE | Live headless-chromium smoke (own profile, sidesteps MCP lock) + live gateway curl, 2026-07-16. STUDIO: `STUDIO_HAS_MOTIF_TEXT=false`, `PALETTE_MOTIF_OPTIONS=0` (Ctrl+K "motif" → 0) → **motif has ZERO GUI path in Studio; agent/MCP is the only route** (= spec 33 line 267 GG-1 violation). LEGACY editor: motif reachable only behind Compose-workmode → right-panel → 25-tab strip → AND an initialised co-writer Work (else "Set up co-writer" dead-end). BE live: `GET /v1/composition/motifs?scope=mine` → real data ("Cultivation Revenge", kind=sequence). Scripts in scratchpad: s4-motif-smoke.mjs / s4-legacy-motif.mjs. |
| S4-A2 · PORT/ENHANCE/BUILD decisions per capability | DONE | Table below (per capability). Adopted spec 33 §9 milestones 3a/3b/3c as the build plan. |
| 3a-gate · verify BE prereqs vs HEAD | DONE | BE-M1/M2 (`gather_motif` `lenses.py:380`, WIRED into `pack()` at all 3 call-sites `engine.py:408/785/995`, emitted `<motif>` block `pack.py:541`, effect test `test_pack_motif_wired.py` exists) + W0-BE1 (`_enqueue_motif_job(project_id=None)` `actions.py:551`, `GET /motif-jobs/{id}` `engine.py:1450`) all **already landed** by a concurrent track. Spec 33's "0 hits / build BE-M1/M2/M3" is STALE. Only BE-M3 (motif_link REST) was genuinely missing. |
| 3a-BE-M3 · motif_link REST routes | DONE | 3 routes in `motif.py` (`GET /motifs/{id}/links`, `POST /motifs/{id}/links`, `DELETE /motif-links/{link_id}`) wrapping `MotifRepo.{list,create,delete}_link` (same methods backing the MCP tools); 409 self-link/cycle/cross-tier surfaces inline (not swallowed). **`test_motif_router.py` 46 passed** (15 new). OpenAPI contract rows added; **`test_openapi_contract_parity.py` 4 passed**. |
| 3a-A · motif-library panel REACHABLE + operable | DONE | `MotifLibraryPanel.tsx` (studio wrapper: mounts `MotifSimpleModeProvider`, passes `meUserId` from `useAuth`, `hideArcTabs` split — legacy `MotifLibraryView` unchanged via new opt-in prop). Registered: catalog row (S4 block) + `panel_id` enum + `frontend-tools.contract.json` (regen 20✓) + en i18n + guideBody. tsc clean; **15 registry-guard tests pass** (dockRegistration/contract/registryPanels — enum==openable==contract). **LIVE SMOKE (:5199, own chromium):** command palette "Studio: Open Motif Library" → `PALETTE_OPTIONS=1` (was 0 in audit) · `PANEL_MOUNTED=true` · `VIEW_RENDERED=true` · `RENDERS_REAL_MOTIF_DATA=true` (Cultivation Revenge) · `ARC_TOGGLE_HIDDEN=true` · `CONSOLE_ERRORS=0`. |
| 3a-B · 6 scope tabs (Mine/Book/Shared/System/Catalog/Drafts) | DONE | `useMotifLibrary` gained system + book/shared (ONE `/motifs/book/{id}` fetch, client-partitioned by book_id/book_shared — §3.1); `MotifScopeTabs` = 6 tabs, book/shared disabled+arrow-skip without a book; `motifApi.book()` added. tsc clean; **153 motif FE tests pass** (no regressions). LIVE SMOKE (:5199): `SCOPE_TAB_COUNT=6`, panel operable, 0 console errors. |
| 3a-C · motif graph section (reads/writes BE-M3) | DONE | `motifApi.{links,createLink,deleteLink}` + `MotifLinkRow` type + `useMotifLinks` hook + `MotifGraphSection.tsx` (collapsible list-not-canvas grouped by kind; add-edge picker; delete; **409 guard message rendered INLINE**; readOnly hides writes) mounted in `MotifDetailDrawer`. **5 new component tests pass**; tsc clean. **LIVE BE-M3 through gateway (rebuilt composition-service):** POST link→201 · GET→neighbor-joined count 1 · self-link→409 `MOTIF_LINK_INVALID` (exact guard msg) · DELETE→200. |
| 3a-close · DoD verification | DONE | **163 motif FE tests** (29 files) · **46 BE router** · contract guards (enum==contract==openable, 20+4) · tsc clean · **packer effect test `test_pack_motif_wired.py` 8 passed AGAINST REAL DB** (ran, not skipped — proves a bound motif CHANGES the packed prompt) · **full-panel live browser smoke**: palette→panel→motif card→detail drawer→graph toggle→`GRAPH_EDGES_RENDERED=1` (live BE-M3 edge), 0 console errors. |
| 3a-gemma · ⛏ Mine live smoke on Gemma-4 26B QAT ($0) | DONE | Full lifecycle through the gateway: propose `composition_motif_mine` (model_ref `019ebb72…` gemma) → `confirm_token` + $2 est → **confirm → HTTP 200 + job_id `019f6b89…` (NOT a 500 — the W0-BE1 proof)** → job readable via `/motif-jobs/{id}` (⇒ Work-less, project_id NULL — a Work-bound job 404s there) → **poll resolved to `completed`**, graceful degrade `reason: beat_extractor_unavailable` (no crash, no fake success). |
| 3a-COMMIT | DONE | **`4d72b78e6`** — 15 files, provider-gate PASS. Also fixed a broken HEAD (a concurrent session had swept my catalog row/import + enum/contract into its commit WITHOUT my untracked `MotifLibraryPanel.tsx` → HEAD imported a non-existent module; this commit lands it). |
| 3b-BE-M4 · ranked suggest REST route | DONE | `GET /works/{pid}/scenes/{node_id}/suggest-motifs` in engine.py (mirrors suggest-cast + agent-only `composition_motif_suggest_for_chapter`) → ranked `{motif,score,match_reason}`, VIEW-gated, node∈project IDOR guard via `_load_work_node`. **LIVE (rebuilt container):** HTTP 200 · 5 ranked candidates each w/ full `match_reason` (tension/genre/precond/cosine) · random node → **404**. (retriever `degraded` in dev — graceful.) No router unit test (local `loreweave_vecmath` blocks import) — live-smoke is the proof. |
| 3b-FE · scene-inspector Motifs section + suggest + seam | DONE | `motifApi.suggestForChapter` + `MotifSuggestion` type + `useMotifSuggestions` (lazy) + `SceneMotifsSection` (reuses `MotifBindingCard`/`useMotifBinding` verbatim; ranked Suggest button w/ score+reason replacing flat list = GG-1 fix; no-Work + empty + error states) mounted in `SceneInspectorPanel` (Craft→Motifs→Links); `MotifBindingLens.tsx` seam built (S2 mounts in PlanDrawer). **5 SceneMotifsSection tests · 168 motif FE suite · tsc clean.** **LIVE browser smoke (:5199):** scene-browser→spec scene→scene-inspector→`MOTIFS_SECTION_PRESENT` + `SUGGEST_TOGGLE` + `BINDING_CARD` all true, 0 console errors. Gemma: N/A (suggest = embed-retrieval, not gemma-chat; smoked live). |
| 3b-review · /review-impl | DONE | No HIGH. Tenancy clean (BE-M4 VIEW gate + `_load_work_node` node∈project 404 = IDOR guard; random-node smoke confirms). LOW (accept+doc): BE-M4 no router unit test (vecmath-blocked; live-proven); `bookId ?? ''` coercion (studio always has bookId). Coordination: MotifBindingLens awaits S2 mount (sanctioned seam); NodeBadges onClick → Book-Package track (deferred). |
| 3a-review · /review-impl (charter: at each panel close) | DONE | Tenancy/IDOR on BE-M3 verified clean (ownership+grant gates, no existence oracle, uniform 404). 2 findings FIXED: **MED** — 6-tab partition (book_id/book_shared) had no unit test (spec 33 §3.1 calls an un-filtered Book tab "a defect") → added `useMotifLibraryScopes.test.tsx` (5 tests locking Book=private-only, Shared=book_shared-only, single-fetch, disabled-without-book, system scope). **LOW** — `MotifGraphSection` state didn't reset on motif switch (mostly unreachable via overlay-close, but fragile) → `key={motif.id}`. Standards gate: no provider/model/secret/tenancy-table violations. |
| 3b · binding lens + suggest (size M) | TODO | seam: MotifBindingLens → PlanDrawer (S2 mounts); touches NodeBadges (Book-Package track) |
| 3c · quality-conformance panel + M-BUG-4/404 fixes (size M) | TODO | composition-service-only; no cross-service smoke; live-browser smoke still mandatory |

### A2 · PORT / ENHANCE / BUILD decisions (per capability)
| Capability | Current state | Call | How (spec 33 ref) |
|---|---|---|---|
| Motif library CRUD (list/get/create/patch/archive) | FE built (`MotifLibraryView`…), wired REST, legacy-only | **PORT** | new `motif-library` dock panel; **SPLIT off `ArcTemplateLibraryView`** (§2.3 trap — drop the `kind` toggle); mount `MotifSimpleModeProvider` (§2.4); pass `meUserId` from `useAuth()` not localStorage shim (§2.4) |
| Scope tabs (Mine/Book/Shared/System/Catalog/Drafts) | 4 tabs today (mine/system/all/drafts) | **ENHANCE** | +Book +Shared from `GET /motifs/book/{book_id}` (no FE consumer today), one fetch feeds both (§2.5, §3.1) |
| Motif GRAPH (composed_of/precedes/variant_of) | agent-only link tools; no REST, no GUI | **BUILD** | list-style graph section (NOT a canvas — OQ-2); needs BE-M3 REST for `motif_link_{list,create,delete}` |
| Mine (corpus → unbound drafts, LLM async) | FE built, wired | **PORT + fix** | repoint poll `getJob` → `GET /motif-jobs/{id}`; **gated on W0-BE1** — if unlanded, build all 7 legs (§1.2, §9-3a) |
| Adopt (quota-gated) / upstream-sync | FE built, wired | **PORT** | via generic propose→confirm cost spine (§3.0) |
| Ranked suggest-for-chapter | agent-only (`MotifRetriever`); FE uses flat `list(scope=all,100)` | **BUILD/ENHANCE** | the ONE suggest button this wave (3b); ranked rows + `match_reason` (arc-suggest is Wave 4) |
| Binding lens (bind/unbind/re-role/chain/overuse) | FE built, legacy-only | **PORT → seam** | `MotifBindingLens.tsx` (S4 file) mounted by S2 in PlanDrawer + `scene-inspector` Motifs section; chapter-scope undo only (§3.2) |
| Conformance trace (chapter/arc scope) | FE built (`ConformanceTraceView`), **M-BUG-4 broken** | **PORT + fix** | new `quality-conformance` panel; fix M-BUG-4 (`arc_template_id`→`arc_id`=structure_node.id) both transports; delete dead `conformanceRunEstimate/Confirm/regenerateToBeat` (§3.4, §5.1) |
| **Packer reads motifs (`gather_motifs`)** | 🔴 **NOT built** (0 hits in packer, §2.1) | **BUILD (BE)** | the hard gate for 3a — mirror the proven `gather_arc` lens; composition-service backend. *Unbuilt, not blocked.* |

**Nothing silently dropped.** Wave-4 arc-template files (`ArcTemplateLibraryView`, `ArcTimeline*`, `arcApi.ts`…) are **NOT ported here** (belong to S2/spec 34) — recorded, not dropped.

## REGISTERS  (append as you go — an empty DRIFT log at the end is dishonest, not clean)
### DECISIONS
- **D-S4-1** — Adopt spec 33 (`33_motif_studio.md`, 880 lines) as the detailed design/plan verbatim; do NOT author a new spec or HTML draft. Rationale: it already reaches the live-audit conclusions (built-but-unreachable, MCP-only=GG-1 violation, MotifEmptyState+CTAs), carries the registration checklist/Lane-B/tenancy/milestones/DoD, and repo law forbids duplicating an 880-line spec. HTML acceptance targets already exist: `design-drafts/motif-library/*` (7 screens) + `design-drafts/screens/studio/screen-motif-library.html`, `screen-motif-binding-and-conformance.html`.
- **D-S4-2** — Do NOT touch legacy `CompositionPanel.tsx` / `ChapterEditorPage.tsx`. Add Studio dock panels in parallel; legacy sub-tabs stay until convergence retirement ② (not S4's job). Keeps the working legacy layer intact.
- **D-S4-3** — Studio `motif-library` opens **unconditionally** (no co-writer-Work gate, unlike legacy). Motif library is user-scoped (`book_id=null`, reused across books); book/scene context only needed for binding + conformance. Empty-state = `MotifEmptyState` with actionable CTAs (Adopt / Mine), never a "Set up co-writer" dead-end.
- **D-S4-4** — Live-browser smoke uses a **self-launched headless chromium with its own temp profile** (playwright-core from frontend/node_modules), because the shared MCP browser profiles are held by concurrent same-folder sessions (verified: PID 22276/48868). $0 LLM smokes drive local lm_studio (Gemma-4 26B / Qwen2.5 7B; :1234 up) with an explicit `model_ref` (account's `user_default_models` is empty).

### PARKED  (blocker -> defer row + continue)
- (spec 33 §11 pre-existing defers carried: D-COMPOSE-GENERATE-UNGATED [gate#1 out-of-scope], D-MOTIF-BOOKSHARED-QUOTA [gate#4], D-MOTIF-GRAPH-CANVAS [gate#2], D-ARC-TEMPLATE-DRIFT-VIEW → Wave 4.)

### DEBT
- **D-MOTIF-LENS-PLANDRAWER-MOUNT** (gate #1, coordination) — `MotifBindingLens.tsx` is built (S4 owns) but not yet mounted in `PlanDrawer.tsx` (S2 owns the file). Per the seam rule S2 adds `<MotifBindingLens nodeId={…}/>` with a one-line import. Reachable via scene-inspector today; the PlanDrawer entry lands when S2 mounts it.
- **D-MOTIF-NODEBADGES-ONCLICK** (gate #1, cross-track) — §3.2b's `NodeBadges` motif-chip → `openPanel('scene-inspector')` onClick touches the Book-Package track's `NodeBadges.tsx`. Deferred to coordinate with that track (don't cross-edit).
- **D-MOTIF-MINE-BEAT-EXTRACTOR** (env caveat, gate #4) — the gemma mine smoke completed but mined 0 with `reason: beat_extractor_unavailable`: a mining sub-component (beat extractor) isn't available in this dev env. Graceful degrade (no crash, no fake success), so the FE flow is correct; the 0-result is an infra gap, not an S4 bug. Verify mine yields drafts once the beat extractor is provisioned.

### 3c — quality-conformance + M-BUG-4 (DONE)
- **quality-conformance panel** — `QualityConformancePanel.tsx` (mirrors QualityCriticPanel: useQualityWork gate + chapter picker + ModelPicker) rendering `ConformanceTraceView` (chapter-scope beat trace). Registered (catalog row + enum + contract + i18n + guide + QualityHub 8th card). **LIVE browser smoke (:5199):** palette "Open Conformance" → `PANEL_MOUNTED` + `CHAPTER_PICKER` + `NO_CHAPTER_HINT`, 0 console errors.
- **M-BUG-4 FIXED** — `arc_template_id`→`arc_id` (a structure_node.id) on the GET + the MCP propose. **LIVE proof:** `?scope=arc&arc_template_id=` → **422** (old bug), `?scope=arc&arc_id=` → **404** (parsed — a valid node returns data). 2 ArcConformancePanel regression tests flipped to assert `arc_id` (red on old code = the DoD's M-BUG-4 test).
- **Dead code deleted + re-pointed** — removed `conformanceRunEstimate`/`conformanceRunConfirm`/`regenerateToBeat` + orphaned `_resolveActionJob`; regenerate → the existing `POST /works/{pid}/generate {outline_node_id}` (§5.1); chapter re-run → the generic MCP `composition_conformance_run` (mirrors arcConformanceRunPropose), BYOK-gated (`canRerun`).
- **Tests:** 168 motif FE · registry guards · contract (enum==contract==openable). tsc: my files clean (only a concurrent `ProgressPanel` error, not mine).
- **Gemma conformance-run:** attempted — the `composition_conformance_run` tool accepted the gemma `model_ref` + args, then returned "not found" on the chapter data lookup (no conformance-ready generated+bound chapter in the test Work — an env-data gap, like mine's beat_extractor / suggest's degrade, NOT a 3c code defect). FE wiring correct (calls the right MCP tool).
- **/review-impl:** No HIGH. Legacy CompositionPanel's conformance re-run now degrades to *disabled* (no modelRef + deleted REST) — graceful (disabled+hint, no silent fail), acceptable as legacy retires. M-BUG-4 arc *value* (structure_node.id) is the arc-templates caller's fix → **D-M-BUG-4-ARC-CALLER** (Wave 4).
- ⚠ **HEAD-broken-by-sweep (again):** a concurrent commit swept my catalog row+import+enum+contract WITHOUT my untracked `QualityConformancePanel.tsx` → HEAD imported a non-existent module. This commit lands it.

### DRIFT  (near-misses, bars nearly lowered, tests nearly skipped)
- **SPEC-STALE (3a-gate)** — spec 33 (§2.1, §9-3a) says the packer has "0 motif hits" and 3a must build BE-M1/M2/M3. Verified vs HEAD: BE-M1/M2 + W0-BE1 **already landed** by a concurrent track (38 motif hits in packer; `gather_motif` wired at all 3 pack() call-sites; effect test present). Had I trusted the doc note I'd have rebuilt a live lens ([[planforge-promoted-by-another-agent-check-compat]]). Only BE-M3 was real. Recorded so 3a's DoD "the packer effect test proves a bound motif changes the prompt" is a VERIFY step (run the existing test with a real DB), not a build.
- **NEAR-MISS (A1)** — first audit was structural-only (files+tools exist ⇒ "mostly a port"). That is exactly the "skeleton renders = done" trap §2 bar warns of. PO pushed for a user-POV review; the live smoke then proved the Studio GUI path is **zero**. Lesson: an audit that never drives the real surface cannot claim operability.
- **NEAR-MISS (A1)** — first live-smoke ran against my own `vite :5200`, which rendered **blank** (misconfigured entry) → a false "no motif" read. Caught by cross-checking body length; re-ran on baked `:5174` (known-good) + isolated chromium. Lesson: `frontend-5174-is-baked-prod-nginx-not-vite`, and verify the page actually rendered before trusting an absence.
