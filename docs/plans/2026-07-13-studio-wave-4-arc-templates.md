# Wave 4 — Arc Templates + 拆文 · IMPLEMENTATION PLAN (BUILD DETAIL)

> **Written:** 2026-07-13 · branch `feat/context-budget-law` · HEAD at planning time `9262ed53e`
> **Spec (the design — do not re-design):** [`docs/specs/2026-07-01-writing-studio/34_arc_templates_and_deconstruct.md`](../specs/2026-07-01-writing-studio/34_arc_templates_and_deconstruct.md)
> **Master plan (the contract):** [`docs/specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](../specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) — §0 PO decisions (SEALED) · §8 GG-8 registration · §8.0 panel-id ledger · §8.0b Lane-B handler homes · §9 collisions · §10 REFUTED
> **HTML draft (the UI acceptance criterion):** [`design-drafts/screens/studio/screen-arc-templates.html`](../../design-drafts/screens/studio/screen-arc-templates.html) — every state it renders must exist in the built panel.
> **Size:** **L** — 🔴 **CORRECTED by adjudication `Q-34-SIZE-ESTIMATE-MOVED`.** This wave ships **TWO**
> new REST routes, not three: **BE-7a** (`POST /arcs/{node_id}/extract-template`) and **BE-7b**
> (`POST /arc-templates/suggest`). **BE-7c** (`GET /motif-jobs/{job_id}`) is **CONSUMED** here but
> **OWNED by Wave 3 / 3a** — verify, do not re-build (pre-flight cmd 4). The **3rd side effect** is the
> cross-service **frontend-tools `panel_id` contract** (`chat-service/.../frontend_tools.py` enum +
> the regenerated `contracts/frontend-tools.contract.json`) — a real API/contract side effect that is not
> a REST route.
>
> **Gate command (run it exactly):** `./scripts/workflow-gate.sh size L 19 9 3 <context_pct>`
> **IF W4-BE3 fires** (Wave 3a did not land BE-7c) the wave additionally carries a **relax-only
> migration + a repo path + two gate changes** (see the re-scope in W4-BE3) ⇒ re-run
> `./scripts/workflow-gate.sh size L 22 11 5 <context_pct>`. Still **L** either way (logic is the
> primary axis; side_effects only set a risk FLOOR of M, which L clears).
>
> **Type:** FS.
> **Closes:** `G-ARC-TEMPLATE-LIBRARY` (L) · `G-IMPORT-DECONSTRUCT` (M).
> **Decision prefix:** **AT-** (spec 34 §3). Slice prefix **W4-**.
> **Adjudications:** `docs/plans/studio-adjudication/wave-4-decisions.md` — 42 DECIDED items, settled
> against source. 🔴 **Where that file and this plan disagree, THAT FILE WINS.** Every disagreement found
> in the 2026-07-13 reconciliation has been folded in below and is marked **🔴 ADJUDICATED**.

---

## 0 · THE POLICY THIS PLAN IS WRITTEN UNDER (quoted verbatim from the PO — binding)

1. **This plan is written ONCE, in full, at BUILD DETAIL.** After the QC gate, implementation proceeds
   **autonomously with no further design checkpoints.** So anything left vague becomes a stall or a
   guess at 3am. A slice that says "wire the panel" is a FAILURE; a slice says WHICH FILE, WHAT CHANGE,
   WHICH TEST.
2. **`/review-impl` runs at the completion of EVERY wave**, and any bug it finds is fixed before the
   wave closes. It is a literal step in the Definition of Done (§9).
3. **DEFERRAL POLICY — "blocked ≠ stopped".** When the build hits a blocker: write a tracked defer row
   and **KEEP GOING**. Do **not** stop, do **not** ask. A blocker is a DEFER by default.
   **Stop and ask ONLY for a CRITICAL blocker**, defined narrowly as exactly one of:
   - a destructive / irreversible action (data loss, a migration that drops or rewrites user rows),
   - a **sealed decision proven wrong** by the code (plan 30 §0, PO-1..4),
   - a **tenancy / security breach** (cross-user data exposure),
   - a **paid-action defect that would charge the user for nothing** (this wave has exactly one such
     surface — 拆文. 🔴 **CORRECTED 2026-07-13: it is a HTTP 500 at `POST /actions/confirm`, BEFORE the
     enqueue — NOT "a poll that 404s".** The `generation_job` row is **never created**, the poll is never
     reached, and **nobody is charged** (no XADD, no worker, no LLM call) — though the confirm token is
     burnt and a billing hold is left dangling. **Its fix is the Work-less job LANE, built in Wave 0 as
     `W0-BE1`** — a job-READ route alone would read a row that never exists and would **ship green**;
     see `W4-BE3` = VERIFY-OR-BUILD.)
   Everything else — a missing route, an awkward refactor, a failing third-party thing, an ugly seam —
   is a **defer row + continue**.
4. Every defer row carries: ID, wave/slice of origin, what, the gate reason (CLAUDE.md's 5 gates),
   target wave/trigger. A defer row is never a silent drop.
5. **CLAUDE.md's anti-laziness rule is in force:** "missing infrastructure is NOT blocked — it is unbuilt
   work to implement." A route that does not exist is a route you WRITE.

### 0.1 · THE ADJUDICATION REGISTER — 🔴 IT EXISTS. READ IT FIRST.

**`docs/plans/studio-adjudication/wave-4-decisions.md`** — 46 items, **42 DECIDED against source code**.
When this plan was first written that file had not yet been recovered, so **this plan was written blind**
to it. It has since been folded in (2026-07-13 reconciliation). **The decisions file is the higher
authority.** Read it before the first slice; every 🔴 **ADJUDICATED** block below cites the item id
(`Q-34-*`) it came from, and the file carries the full evidence chain for each.

Spec 34's own §3 (locked decisions AT-1..AT-11) and §12 (open questions OQ-1..OQ-6) remain the design.
**§10 of this plan resolves every OQ into an instruction.** Do not re-open them.

The six adjudications that are LAW for this wave and are baked in below:

| # | Adjudication | Where it lands |
|---|---|---|
| **A** | **BE-8 drift: the ROUTE ALREADY SHIPS** (`?scope=arc_template_drift`). The **human drift view is BE-NONE and must NOT be parked.** BE-8 shrinks to **agent-parity only** (un-stub `composition_arc_apply` / `composition_arc_template_drift`). | Drift ships in **W4-FE5** (BE-NONE). Agent parity is **W4-BE8a / W4-BE8b**. |
| **B** | **DROP "mine motifs from an import source" — REFUTED** (plan 30 §10: `_MotifMineArgs.scope` is `Literal["book","corpus"]`; there is no `import_source_id` field). | Not built. Not specced. Not a defer row. **Do not add it.** A regression test fences it (§13). |
| **C** | **`arcEffects.ts` is EXTENDED, not created twice.** Spec 32 (Wave 2) creates it with one broad `/^composition_arc_/` registration. `matchEffectHandlers` returns **EVERY** match and `runEffectHandlers` **awaits ALL** of them — a second registration **double-fires**. | **W4-FE1** extends the existing handler **body**. It adds **no** second `registerEffectHandler`. |
| **D** 🔴 | **`materialize` ALREADY CREATES THE SPEC ARC AND ALREADY LINKS ITS CHAPTERS.** `commit_decomposed_tree` → `_insert_decomposed_tree` calls `StructureRepo.create_node(book_id, kind='arc', …)` (`outline.py:435-438`), sets `structure_node_id=arc.id` on **every** chapter node (`outline.py:444`), and returns it as `arc_id` (`outline.py:471` → `plan.py:1384`). **Spec 34:24's "no `structure_node` at all" is FALSE.** The ONLY gap is the `arc_template_id`/`template_version` **stamp** on that arc. ⇒ AT-6's `createArc` + `assignChapters` shape would mint a **SECOND** arc and **re-point the chapters off** materialize's arc — an orphan bystander (the `D-A3-REPLACE-ORPHAN-ARC-NODES` / FD-17 bug class). | **W4-BE4** (server-side stamp) + **W4-FE4** (one call, assert the effect). `createArc`/`assignChapters` are **NOT** added. (`Q-34-OQ1-STAMP-SITE`, `Q-34-OQ2-DOUBLE-MATERIALIZE`, `Q-34-AT6-SILENT-NOOP`) |
| **E** 🔴 | **BE-7c is NOT "just a read route" — the job ROW IS NEVER CREATED.** `_enqueue_motif_job` stamps a synthetic `pid=uuid4()` (`actions.py:552`); `GenerationJobsRepo.create` inserts via `… SELECT … FROM composition_work WHERE w.project_id=$2` (`generation_jobs.py:159-172`) ⇒ **0 rows** ⇒ `ReferenceViolationError` (`:198-206`), **uncaught ⇒ 500** — *after* `_claim_or_replay` burned the confirm token and `_precheck_or_402` placed a billing hold (there is **no release**). **Live DB proof: ZERO `mine_motifs` and ZERO `analyze_reference` rows have ever existed.** A poll route over a job that is never created polls nothing. | **W4-BE3 is RE-SCOPED to M** (relax-only migration + a Work-less insert path + spend-after-durability + a gate cascade + the read route). (`Q-34-JOB-NOT-POLLABLE`, `Q-34-BE7C-OWNERSHIP-CHECK`) |
| **F** 🔴 | **NO `studioLinks.ts` resolver.** §6 step 7 is conditional and the condition is **NOT met**: `resolveStudioLink` is a **path** resolver that discards the query string, there is no `?panel=` mechanism anywhere, and there is no `/arc-templates` app route. All three hand-offs (deconstruct-complete, suggest-candidate, extract-success) are **IN-PANEL view switches**, because AT-1 keeps all views MOUNTED inside one panel. | **W4-FE1** builds a `params.templateId` + `onDidParametersChange` seam (the `AgentModePanel.tsx:31-48` precedent) and ONE `openDetail(id)` callback. **studioLinks.ts is not touched.** (`Q-34-STUDIOLINKS-COND`) |

---

## 1 · Header — gates, scope, what it unblocks

### 1.1 Hard gates (must be green BEFORE the first slice starts)

| Gate | What | Why it is a gate | Verify command (§2) |
|---|---|---|---|
| **X-1** | **`frontend/src/components/shared/AddModelCta.tsx`** (🔧 **NOT** `components/model-picker/` — adjudicated path fix) DOCK-7 fixed at the **shared component** (`useOptionalStudioHost()` → `followStudioLink('/settings/providers', host, {bookId})` → `host.openPanel('settings', {params:{tab:'providers'}})`; `<Link>` fallback outside the studio, keeping its `?return=`). 🔴 **VERIFIED NOT LANDED** at HEAD `9262ed53e`: the file is a raw `<Link>` with **zero** `useOptionalStudioHost()` (`Q-34-X1-ADDMODELCTA`). | 🔴 **HARD BLOCKER.** The Deconstruct section renders a model picker whose **zero-model** state renders `AddModelCta` (`ModelPicker.tsx:388`). Un-fixed, that button route-navigates and **tears down the entire dockview**. **Fix it at the SHARED component — never at the ~8 call sites** (`CompositionPanel:514`, `BuildGraphDialog:647`, `EmbeddingModelPicker:97`, `RerankModelPicker:58`, …). Precedent to copy verbatim: `frontend/src/features/glossary-translate/StepConfig.tsx:44,153-166`. | §2 cmd 1 |
| **X-2** | `'quality'` present in `CATEGORY_ORDER` + the membership assertion in `panelCatalogContract.test.ts`. | Not strictly blocking (`storyBible` is already a `CATEGORY_ORDER` member) — but the membership **assertion** is what keeps this wave's `catalog.ts` row honest. | §2 cmd 2 |
| **X-3** | `panelCatalogContract.test.ts` asserts every openable panel has a non-empty `guideBodyKey`. | This wave's `catalog.ts` row **must** ship `guideBodyKey` or the test reds. | §2 cmd 2 |
| **X-4** | Lane-B handlers exist; the FALSE comment at `useStudioEffectReconciler.ts:10` is deleted. | Without a `composition_arc_*` handler, every agent write to an arc/template leaves this panel **stale**. | §2 cmd 3 |
| **Wave 2** | `arcEffects.ts` exists (spec 32 creates it). | W4-FE1 **extends** it. If it does not exist, W4-FE1 **creates** it exactly as spec 32 §6 step 8 specifies — **one file, one broad `/^composition_arc_/` pattern.** | §2 cmd 3 |
| **Wave 3 / 3a** | **BE-7c** (`GET /v1/composition/motif-jobs/{job_id}`, owner-scoped) is built. | The 拆文 poll. **At planning time it DOES NOT EXIST** (verified: `grep -rn "motif-jobs" services/composition-service/app/routers/` → empty). Wave 3 owns it because `MotifMinePanel` is its first consumer. **If Wave 3 has landed it, VERIFY and consume. If not, W4-BE3 BUILDS it here.** Do not build it twice. | §2 cmd 4 |
| **Wave 3 / 3c** | Spec 33's **M-BUG-4** (the `arc_template_id` → `arc_id` BA4 drift in `motifApi.arcConformance` + `arcConformanceRunPropose`) is fixed. | Informational — **W4-FE1 DROPS `ArcConformancePanel` from the new panel entirely (AT-7)**, so the bug cannot enter it. 🔴 **ADJUDICATED (`Q-34-OQ5-VS-DOD7-CONTRADICTION`): if 3c slipped, this is NOT a defer row and NOT "irrelevant" — it is a 3-line FIX-NOW, inline in M1** (`motif/api.ts:212-216,246,257`: `arcTemplateId`→`arcId`, `arc_template_id`→`arc_id`; `ArcConformancePanel.tsx:22,28,31,34` prop rename; `ArcTemplateLibraryView.tsx:39` stop passing `openArc.id` — pass the materialized arc's `structure_node.id`, which W4-BE4's stamp creates). Note it in VERIFY. **Never mint `D-ARC-CONFORMANCE-FE-ARGS-DRIFT`.** | §2 cmd 5 |
| **GG-4** | `ChapterEditorPage` **not yet retired**. 🔴 **ADJUDICATED (`Q-34-GG4-CHAPTEREDITORPAGE`): the "spec 16 slates it for deletion" premise is STALE.** Spec 16 **Phase 4b (COMPLETE 2026-07-05)** superseded M9: the page is *"kept indefinitely, not deleted"* (`ChapterEditorPage.tsx:1-18`). **Nothing will delete it out from under this wave.** | The **real** zero-door window is **Wave 3 → Wave 4**: spec 33 §2.3 tells slice 3a to drop the `kind` toggle from the LEGACY `motif/components/MotifLibraryView.tsx:66` — **that toggle is the arc library's ONLY door**. 🔴 **BINDING CROSS-WAVE INSTRUCTION: Wave 3 / 3a MUST NOT EDIT `MotifLibraryView.tsx`.** It creates a NEW motifs-only panel and leaves the legacy component byte-identical. Wave 4 then **LIFTS** (does not move) `ArcTemplateLibraryView` into the new panel — two hosts, zero deletes, zero window. **Wave 4 lands the mechanical guard** (`legacyRetirementGuard.test.ts`, W4-FE1) that makes GG-4 dischargeable by a test instead of a prose banner. | §2 cmd 6 |

### 1.2 What this wave builds — the milestone map

| M | Content | BE |
|---|---|---|
| **M1** | The `arc-templates` panel: registration (GG-8), 3-tier browse, the **fixed** empty state, CRUD + 412 reconcile, adopt, apply-preview → materialize, **AT-6's provenance stamp**. `ArcConformancePanel` **dropped**. | **NONE** |
| **M1** | (continued) 🔴 **AT-6's stamp moves SERVER-SIDE** (adjudication **D**) ⇒ M1 is **BE-XS**, not BE-NONE. | **W4-BE4** |
| **M2** | **Import & Deconstruct** (拆文): sources CRUD, configure, the AT-5 cost gate, the AT-11 owner-scoped poll, completion **in-panel** hand-off (adjudication **F** — no URL), the AT-9 copyright/strip disclosure. 🔴 **+ AT-8's two BE legs** (kill the platform-model fallback; reject-before-spend). | **BE-7c** (verify — Wave 3 owns it; else **build it FULLY**, adjudication **E**) · **W4-BE5** |
| **M3** | **Suggest + Extract** — two REST wrappers + their UIs + the `match_reason` render + **the OpenAPI contract, frozen FIRST** (W4-BE0). | **BE-7a**, **BE-7b** |
| **M4** | **Drift** — *Used by* list + the drift report over the **already-shipped** `?scope=arc_template_drift` route, with all **three** distinct server empty states **× the four Work-gate states** (`Q-34-DRIFT-PID-RESOLUTION`). | **NONE** ← the audit correction |
| **M5** | **BE-8 — agent parity. 🔴 IN-WAVE, NOT PARKED** (`Q-34-GG2-INVERSE-GAP`). Un-stub `composition_arc_template_drift` (delegate) + `composition_arc_apply` (**wrap the SHIPPED `arc_apply()` engine** — it is *not* unwritten) + **delete `_pending_engine` outright**. **DoD #9: zero `pending_dependency` responses remain in composition's MCP surface.** | **BE-8a / BE-8b** |

### 1.3 What it unblocks downstream

- **Wave 6 / GG-4** — `ChapterEditorPage` retirement may only proceed once Waves 4 + 3 + 6 have landed.
- **The agent's arc surface** — after M5 an agent can apply a template and read drift, closing GG-2 (the
  inverse law) for this domain.

---

## 2 · PRE-FLIGHT — run these EXACTLY, read the output, THEN start

Run every command. Do not skip one because "it obviously landed". Three rows of the audit were wrong
against code; assume the same rate remains.

```bash
cd d:/Works/source/lore-weave-mvp

# 1 · X-1 — AddModelCta must consult the studio host (NOT a raw <Link> that route-navigates).
#   🔧 THE PATH IS components/shared/, NOT components/model-picker/ (adjudicated).
grep -n "useOptionalStudioHost\|followStudioLink\|openPanel" frontend/src/components/shared/AddModelCta.tsx
#   EXPECT: a non-empty hit. EMPTY ⇒ X-1 is NOT done ⇒ the Deconstruct section's zero-model
#   state will tear down the dock. This is a HARD BLOCKER — fix X-1 first (plan 30 Wave 0),
#   at the SHARED COMPONENT, never at the ~8 call sites. At planning time: EMPTY.

# 2 · X-2 + X-3 — the two catalog-contract assertions.
grep -n "CATEGORY_ORDER" frontend/src/features/studio/palette/useStudioCommands.ts
grep -n "guideBodyKey\|CATEGORY_ORDER" frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts
#   EXPECT: CATEGORY_ORDER contains 'quality'; the contract test asserts BOTH
#   (a) category ∈ CATEGORY_ORDER and (b) every openable panel has a non-empty guideBodyKey.

# 3 · X-4 + Wave 2 — the Lane-B arc handler home.
ls frontend/src/features/studio/agent/handlers/
grep -rn "composition_arc" frontend/src/features/studio/agent/handlers/
grep -n "" frontend/src/features/studio/agent/useStudioEffectReconciler.ts | sed -n '8,14p'
#   EXPECT: arcEffects.ts EXISTS with ONE broad /^composition_arc_/ registration (spec 32).
#   EXPECT: the FALSE comment at useStudioEffectReconciler.ts:10 is GONE.
#   If arcEffects.ts is absent ⇒ W4-FE1 creates it (one file, one pattern). NEVER a second file.

# 4 · BE-7c — the 拆文 poll. THE decisive pre-flight. 🔴 TWO CHECKS, NOT ONE.
#   4a · the READ route
grep -rn "motif-jobs\|motif_jobs" services/composition-service/app/routers/ frontend/src/
grep -rn "created_by" services/composition-service/app/mcp/server.py | grep -i "mine_job"
#   4b · 🔴 the WRITE side — the job row is NEVER CREATED at HEAD (adjudication E).
grep -n "uuid4()" services/composition-service/app/routers/actions.py       # :552 = the synthetic pid
grep -n "FROM composition_work" services/composition-service/app/db/repositories/generation_jobs.py
psql "$COMPOSITION_DB_URL" -c \
  "SELECT operation, count(*) FROM generation_job GROUP BY 1 ORDER BY 1;"
#   EXPECT (at planning time): ZERO mine_motifs and ZERO analyze_reference rows have EVER existed.
#   BOTH 4a AND 4b GREEN ⇒ Wave 3/3a built BE-7c properly. VERIFY the shape, then CONSUME. Skip W4-BE3.
#   4a green but 4b still broken ⇒ Wave 3 shipped a READ ROUTE OVER A ROW THAT IS NEVER WRITTEN.
#         That is still the paid-action defect. W4-BE3's WRITE half is IN SCOPE. Raise it to spec 33's
#         owner as a regression; do not silently absorb it.
#   4a EMPTY ⇒ BUILD ALL OF W4-BE3 here. It is unbuilt work, not a blocker. (Planning-time state.)

# 5 · Spec 33's M-BUG-4 — the ArcConformancePanel arg drift.
grep -n "arc_template_id" frontend/src/features/composition/motif/api.ts
#   ZERO hits in arcConformance / arcConformanceRunPropose ⇒ 3c landed. Cite it closed in M1's
#   close-out. Done.
#   STILL PRESENT ⇒ 🔴 NOT a defer row and NOT "irrelevant". It is a 3-line FIX-NOW, inline in M1
#   (api.ts:212-216,246,257 + ArcConformancePanel.tsx:22,28,31,34 + ArcTemplateLibraryView.tsx:39).
#   NOTE: ArcMaterializeAction's `arc_template_id` (arcTypes.ts:23) is CORRECT — that route really
#   does take it. Do not "fix" that one.

# 6 · GG-4 — the legacy page must still exist (it is the only door to the arc library today).
grep -n "ChapterEditorPage" frontend/src/App.tsx
grep -n "ArcTemplateLibraryView\|const \[kind" frontend/src/features/composition/motif/components/MotifLibraryView.tsx
#   EXPECT: BOTH hit. Spec 16 Phase 4b keeps ChapterEditorPage indefinitely, so the ROUTE will be there.
#   🔴 THE REAL RISK IS THE SECOND GREP: if Wave 3/3a deleted MotifLibraryView's `kind` toggle, the arc
#   library has ZERO doors until this wave closes. That is a shipped feature with no door (GG-1's exact
#   failure). It is NOT a stop-and-ask — it is a DEFER+CONTINUE with a raised priority: build W4-FE1
#   FIRST (it restores the door), and file a cross-wave note against spec 33 §2.3.

# 7 · The shared components (DOCK-2 — the "do not fork" set).
#   🔴 ADJUDICATED (Q-34-SHARED-LIFT-LOCATION): THERE IS NO LIFT AND NO MOVE. The four shared
#   components already have exactly ONE home each, and that home IS the shared location. BOTH waves
#   import them IN PLACE. Spec 34 §2's "LIFT AS-IS" means MOUNT INTO THE PANEL, not RELOCATE THE FILE.
#   The canonical paths — import from these VERBATIM:
#     frontend/src/features/composition/motif/components/MotifStateBoundary.tsx
#     frontend/src/features/composition/motif/components/CostConfirmCard.tsx
#     frontend/src/features/composition/motif/components/AdoptTargetModal.tsx
#     frontend/src/features/campaigns/components/ModelRolePicker.tsx   (already cross-feature; mirror
#                                                                       MotifMinePanel.tsx:9's import)
grep -rln "MotifStateBoundary\|CostConfirmCard\|AdoptTargetModal\|ModelRolePicker" frontend/src/features/ | sort
#   EXPECT exactly ONE definition file per component. If a wave FORKED one, that is the DOCK-2 bug —
#   delete the fork and import the canonical path. The guard test is sharedComponentsSingleHome.test.ts
#   (W4-FE1). Do NOT create features/composition/shared/ and do NOT move anything into
#   components/shared/ (that dir is app-generic primitives; these are composition-domain — wrong altitude).

# 8 · Baseline the three enum counts (the drift-lock). Record the numbers — you assert the DELTA.
python - <<'PY'
import json, re, pathlib
ft = pathlib.Path('services/chat-service/app/services/frontend_tools.py').read_text(encoding='utf-8')
m = re.search(r'"panel_id":\s*\{\s*"type":\s*"string",\s*"enum":\s*(\[[^\]]*\])', ft, re.S)
py_enum = json.loads(m.group(1))
c = json.loads(pathlib.Path('contracts/frontend-tools.contract.json').read_text(encoding='utf-8'))
print("py enum   :", len(py_enum))
print("contract  :", json.dumps(c)[:0] or "(inspect ui_open_studio_panel.panel_id enum length)")
PY
grep -c "  { id: '" frontend/src/features/studio/panels/catalog.ts
#   🔴 ADJUDICATED (Q-34-PANEL-COUNT-DELTA): RECORD N_before. NEVER WRITE A TARGET NUMBER DOWN.
#   The three guards are ALREADY set-based and baseline-independent — panelCatalogContract.test.ts:33-36
#   is `expect([...enumIds].sort()).toEqual(openable)`, zero count literals. A written-down target
#   ("58", "65") is a HAZARD: it invites a hardcode, and it is wrong the moment a wave is re-ordered.
#   The ONLY assertions you may add are `expect(enumIds).toContain('arc-templates')` and the +1 DELTA
#   against the N you just recorded. Never arithmetic against a literal.

# 10 · 🔴 The four decisions-file greps that must be re-run at wave start (verify, don't trust the doc).
grep -rn "def apply_arc_to_spec\|def build_template_drift" services/composition-service/app/engine/
#   EXPECT: ZERO hits (both are still _pending_engine seams — W4-BE8a/b build them).
grep -rn "async def arc_apply" services/composition-service/app/engine/arc_apply.py
#   EXPECT: A HIT at ~:325. 🔴 The apply ENGINE IS SHIPPED. BE-8b is a SEAM WRAPPER (S), not a new
#   engine (M). Spec 34 §7/§10's "genuinely unwritten" is FALSE against code (Q-34-GG2-INVERSE-GAP).
grep -rn "arc_template_id\|template_version" services/composition-service/app/db/repositories/outline.py
#   EXPECT: ZERO — which is precisely the gap W4-BE4's stamp closes. The arc NODE is created there
#   (outline.py:435-438) and the chapters ARE linked (outline.py:444); only the stamp is missing.
grep -rn "pending_dependency" services/composition-service/app/mcp/server.py
#   Record the count. DoD #9: it must be ZERO when the wave closes.

# 9 · The suites you must be able to run green BEFORE you touch anything.
cd services/composition-service && python -m pytest tests -q -n auto --dist loadgroup ; cd ../..
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q ; cd ../..
cd frontend && npx vitest run src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
  src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
  src/features/studio/palette/__tests__/useStudioCommands.test.ts \
  src/features/chat/nav/__tests__/frontendToolContract.test.ts ; cd ..
#   Record the PASS COUNTS. They are the "before" half of every DoD evidence string.
```

---

## 3 · THE GROUND TRUTH — what exists at HEAD (verified by reading the files, 2026-07-13)

**Do not plan against a doc's claim. These were opened.** Where spec 34 is wrong, the correction is
marked 🔧.

### 3.1 Backend — composition-service

| Thing | Location | Verified shape |
|---|---|---|
| `GET /v1/composition/arc-templates` | `app/routers/arc.py:106` | `?scope=mine\|system\|all&genre&q&language&status&limit` — **NO `offset`**. Returns **`{arc_templates[], scope, limit}`**. |
| `GET /v1/composition/arc-templates/catalog` | `arc.py:132` | `?genre&q&language&sort=recent\|name&limit&offset` — **paged**. Returns **`{items[], total, limit, offset}`**, each item + `adopt_target:"user"`. ⚠ **Different shape from the list route. Reading `.items` off `/arc-templates` gets `undefined`.** **0 FE consumers.** |
| `GET /arc-templates/{id}` | `arc.py:157` | `repo.get_visible` → 404 `ARC_TEMPLATE_NOT_FOUND` (uniform H13). |
| `POST /arc-templates` | `arc.py:172` | `ArcTemplateCreateArgs`; owner server-stamped. **409 `ARC_TEMPLATE_CODE_EXISTS`** on duplicate `(owner, code, language)`. **409 `ARC_TEMPLATE_PUBLISH_LIMIT_REACHED`** if `visibility ∈ {public,unlisted}` and quota hit. 201. |
| `PATCH /arc-templates/{id}` | `arc.py:193` | `If-Match: <version>` → **412 `ARC_TEMPLATE_VERSION_CONFLICT`, body carries `current` (the server row)**. Owner-filtered in the repo ⇒ a **System/foreign row 404s** (that IS the "clone to edit" affordance). |
| `DELETE /arc-templates/{id}` | `arc.py:233` | Soft archive. Returns `{id, archived:true}` **uniformly** (no oracle). |
| `POST /arc-templates/{id}/adopt` | `arc.py:249` | Body `{retag_genres?}`. Clones into the caller's tier. **201.** 404 / 409 as above. |
| `POST /arc-templates/{id}/apply` | `arc.py:278` | **PURE preview.** `ArcApplyArgs` → `ArcApplyPlan` (rescaled placements + roster-bind + **drop/merge report**). Persists nothing. **$0, no LLM.** |
| `POST /works/{pid}/arc/materialize` | `app/routers/plan.py:1260` | Body `{arc_template_id, roster_bindings, replace, idempotency_key}`. Gate: `_require_work` = **EDIT** on the book (`plan.py:136-144`). Returns **`{arc_id, arc_template_id, chapter_ids[], scene_ids[], motif_applications, scenes_total, beats_distributed, unresolved_placements, drop_merge_report, replay}`**. 🔴 **CORRECTED (adjudication D — the earlier "`arc_id` is an OUTLINE node" note in this table was WRONG).** `commit_decomposed_tree` → `_insert_decomposed_tree` **creates a `structure_node` (kind='arc')** via `StructureRepo.create_node` (**`outline.py:435-438`**), **links every chapter node to it** with `structure_node_id=arc.id` (**`outline.py:444`**), and returns it (**`outline.py:471`**) — so **`arc_id` in the response IS a `structure_node.id`**, and **the chapters are ALREADY assigned**. The **only** missing piece is `arc_template_id`/`template_version` **on that arc**. `chapter_ids` are `outline_node` ids of `kind='chapter'`. Errors: **400 `NO_CHAPTERS`** · **400 `TOO_MANY_CHAPTERS`** (`{count,max}`) · **400 `NO_MATERIALIZABLE_PLACEMENTS`** (`{unresolved_placements}`, reasons ∈ `{motif_not_visible, motif_has_no_beats}` — `arc_materialize.py:116,121`) · **400 `BAD_REFERENCE`** · **409 `CHAPTER_ALREADY_PLANNED`** (`{chapter_ids[]}`) · 404 `ARC_TEMPLATE_NOT_FOUND`. **Replace path:** `outline.py:691-702` soft-archives the now-childless prior arc and mints a FRESH one ⇒ a re-materialize returns a **NEW** `arc_id` and the old stamped arc is already archived. **Replay path:** `_replay` (`outline.py:606-614`) returns the STORED result — the **same, still-active** `arc_id` — *before* the replace sweep. |
| `GenerationJobsRepo.create` | `app/db/repositories/generation_jobs.py:159-172` | 🔴 **THE PAID-ACTION DEFECT (adjudication E).** `INSERT INTO generation_job (…) SELECT $1,$2,w.book_id,… FROM composition_work w WHERE w.project_id=$2`. For a **synthetic** `project_id` (`actions.py:552`) there is **no `composition_work` row** ⇒ **0 rows inserted** ⇒ `raise ReferenceViolationError` (`:198-206`), **uncaught in `actions.py` ⇒ 500** — *after* `_claim_or_replay` burned the one-shot confirm token (`actions.py:639`) and `_precheck_or_402` placed a billing hold (`:642`; **`BillingClient` has NO release method**). **LIVE DB: zero `mine_motifs` / zero `analyze_reference` rows have ever existed.** `project_id` / `book_id` / `created_by` are all **`NOT NULL`**; there is **no FK** on `project_id`. |
| `POST /books/{bid}/arcs` | `arc.py:466` | Body `ArcCreate` = `{kind:'saga'\|'arc', parent_arc_id?, title, summary, goal, status, tracks?, roster?, roster_bindings?, **arc_template_id?**, **template_version?**}`. Gates **EDIT** on the book. Returns a `StructureNode`. **201.** **0 FE consumers — this is AT-6's provenance stamp.** |
| `PATCH /arcs/{node_id}` | `arc.py:489` | `ArcPatch` also accepts `arc_template_id` + `template_version`. `If-Match` → **412 `STRUCTURE_VERSION_CONFLICT`**. Gates on the **ROW's** book. |
| `POST /books/{bid}/arcs/assign-chapters` | `arc.py:560` | Body `{structure_node_id, chapter_node_ids[]}` → **`{assigned: <int>, structure_node_id}`**. The repo (`db/repositories/structure.py:540`) UPDATEs `outline_node` WHERE `book_id=$2 AND id = ANY($3) AND kind='chapter' AND NOT is_archived` + an `EXISTS` guard that the structure_node is in the same book. **A predicate mismatch returns `assigned: 0` — a SILENT SUCCESS.** |
| `GET /books/{bid}/arcs` | `arc.py:413` | Returns **`{nodes[], book_id}`** (each node = `StructureNode` + the derived `{span, is_contiguous, chapter_count, first_story_order}`). **`StructureNode` carries `arc_template_id` + `template_version`** (`db/models.py:206`). ⚠ The FE's `plan-hub/api.ts::getArcs` already normalises `nodes` → `arcs`. |
| `GET /works/{pid}/conformance?scope=arc_template_drift&arc_id=…` | `app/routers/conformance.py:334`, drift branch at **:390** | `arc_id` = a **`structure_node.id`**. Resolves `node.arc_template_id`; **422 `NO_TEMPLATE_PROVENANCE`** when null (`:396`); **404 `{code:"NOT_FOUND"}`** when the template is gone/foreign (`:401`); **422 `ARC_ID_REQUIRED`** when `arc_id` is omitted (`_resolve_book_arc`, `:327`); 403 on under-tier grant. On success → `compute_arc_report(..., by_structure=False)`. **SHIPPED. 0 FE consumers. THE AUDIT SAID THIS NEEDED BE-8. IT DOES NOT.** |
| `POST\|GET\|DELETE /import-sources[/{id}]` | `app/routers/import_source.py:54,66,77,89` | `content` is `StringConstraints(min_length=1, **max_length=20000**)`; `title` ≤ 500. Per-user, **no `visibility` column by construction**. `DELETE` is a **hard delete**. Uniform H13 404. **0 FE consumers.** |
| `POST /v1/composition/actions/confirm?token=…` | `app/routers/actions.py:213` | **Token rides the QUERY**; identity = the Bearer JWT. → `{outcome:'action_accepted', descriptor, job_id, poll:"composition_get_mine_job"}`. **402** from `_precheck_or_402`. 400 `action_error`. |
| 🔴 `GET /v1/composition/jobs/{id}` | `app/routers/engine.py:1415` | `_gate_work(works, grant, user, job.project_id, VIEW)`. **The 拆文 job's `project_id` is a synthetic `uuid4()`** (`actions.py:552`: *"stamp a synthetic project_id … so the row is valid"*) with **no `composition_work` row** ⇒ **404 `work not found`, ALWAYS.** |
| 🔴 `composition_get_mine_job` | `app/mcp/server.py:3207` | **Requires a `project_id` arg**, runs `_book_or_deny(pid)`, then asserts `job.project_id == pid`. The caller is never told the synthetic pid. **Uniform deny, always.** |
| `extract_template_from_arc` | `app/engine/arc_apply.py:652` | **EXISTS.** `(pool, *, arc_node, owner_user_id, code, name, language='en', visibility='private')` → `{success, outcome:'extracted', template_id, member_chapter_node_ids[], layout_placements, pacing_chapters}`. Raises `asyncpg.UniqueViolationError` on a duplicate — **it deliberately does not swallow it.** MCP handler: `server.py:4643`. |
| `MotifRetriever.retrieve_arcs` | reached from `server.py:2287` | `(user_id, book_id=, project_id=, premise=, genre=, limit=)` → candidates with `.arc_template`, `.score`, `.match_reason`. MCP handler applies `apply_response_contract(..., ref_fields=_ARC_REF_FIELDS, detail=detail)` + `_arc_public_projection` for non-owner rows. |
| `_ArcImportArgs` | `server.py:3038` | **`ForbidExtra`**: exactly `{import_source_id, use_web=False, arc_hint=None, language='en', model_ref=None, model_source=None}`. **The Configure step may send NO other field.** |
| `_execute_arc_import` | `actions.py:669` | Re-checks the `import_source` owner at confirm (a token is not a capability), claims the token, prechecks spend, enqueues `analyze_reference` with **`project_id=None`**. |
| 🔴 `arc_apply()` — **THE APPLY ENGINE, SHIPPED** | `app/engine/arc_apply.py:325` | **`async def arc_apply(template, structure_node, *, created_by, structure_repo, outline_repo, applications_repo, resolve_motifs, cast_index, cast_names, roster_bindings, k_ceiling, high_threshold, min_scenes, max_scenes, replace)`** — *"Apply an arc `template` onto an existing spec `structure_node` (BA3)"*. Rescale @365-385 · pacing→tension @447-457 · first-class ledger @475-487 · provenance stamp @490+. **Integration-tested** (`tests/integration/db/test_arc_apply_roundtrip.py:167,295-301`). **ZERO production callers.** 🔴 **Spec 34 §7/§10's "`apply_arc_to_spec` is GENUINELY UNWRITTEN ⇒ M" is FALSE.** The *symbol* `apply_arc_to_spec` does not exist — the **engine** does. BE-8b is a **seam wrapper (S)**, not a new engine. Raises `ArcApplyError` (`:233`) / `ArcApplyConflict` (`:243`). |
| `arc_template_publish_strip` (DB TRIGGER) | `app/db/migrate.py:1065-1088` | `BEFORE INSERT OR UPDATE OF visibility` — rewrites `source_ref` → `'lineage:'‖id` when `visibility ∈ (public,unlisted)` **AND** (`source='imported'` OR `imported_derived`). **It fires on INSERT too.** Adopt propagates the taint (`arc_template_repo.py:277-290`). 🔴 `extract_template_from_arc` calls `ArcTemplateRepo.create` with the **default `imported_derived=False`** ⇒ **a lineage-laundering hole** (W4-BE1 closes it). |
| `_publish_quota_guard` | `arc.py:88-100` | Raises **409 `ARC_TEMPLATE_PUBLISH_LIMIT_REACHED`** `{code,limit,message}`. 🔴 **Its ONLY callers are `create` (`:181-182`) and `PATCH` (`:205-213`), and ONLY when `visibility ∈ ("public","unlisted")`.** It **CANNOT** fire on **adopt** — adopt clones into the caller's own tier as a **private** row (`arc_template_repo.py:255`). **Spec 34 §8's "Adopt is quota-bearing" is WRONG** (`Q-34-NO-FAKE-COST-CARD`): adopt's only 409 is `ARC_TEMPLATE_CODE_EXISTS`. |
| **DOES NOT EXIST** | — | `app.engine.arc_apply.apply_arc_to_spec` (**the SYMBOL** — the engine it must wrap ships, see above) · `app.engine.arc_conformance.build_template_drift` (`grep` → hits only the `getattr` seam at `server.py:4698`) · any REST route for suggest or extract · **any readable poll for a Work-less job** · **any Work-less job ROW AT ALL** (adjudication E) · any `composition_arc_adopt` MCP tool · **no `?panel=` URL mechanism anywhere in the FE** (adjudication F — `WritingStudioPage.tsx:16-17` reads only `?chapter=`). |

### 3.2 Backend — api-gateway-bff

- `FE_BRIDGE_TOOL_ALLOWLIST` (`src/tools/tools.controller.ts:24-31`) already contains
  **`composition_arc_import_analyze`** (PROPOSE) and `composition_get_mine_job` (POLL).
  Its own contract comment: ***"NOTHING here writes or deletes."***
- **Gateway changes this wave: ZERO.** `gateway-setup.ts`'s composition `pathFilter` is
  `(p) => p.startsWith('/v1/composition')` — a new composition route is auto-proxied. **AT-3/AT-4 keep
  extract + suggest off the allowlist precisely so we never touch the BFF.**

### 3.3 Frontend — the port surface (`frontend/src/features/composition/motif/**`)

| File | Verdict |
|---|---|
| `arcApi.ts` (71 LOC) | **LIFT AS-IS** + **ADD** `catalog()`, `extractTemplate()`, `suggest()`. Every existing method maps to a live route. |
| `arcTypes.ts` | **LIFT AS-IS** + add the new response types. |
| `hooks/useArcLibrary.ts` | **LIFT** (`arcApi.list({scope:'all', limit:100})`, queryKey `['composition','arc-templates','all']`). Add a `scope` param + a `useArcCatalog` sibling. |
| `hooks/useArcTimeline.ts` · `components/ArcTimelineEditor.tsx` · `ArcTimelineGrid.tsx` · `ArcTimelineMobileList.tsx` · `applyArcEdit.ts` · `arcTimelineContract.ts` | **LIFT AS-IS** — 4 test files already cover them. |
| `hooks/useArcApplyPreview.ts` · `components/ArcApplyPreview.tsx` | **LIFT AS-IS.** |
| `hooks/useArcMaterialize.ts` · `components/ArcMaterializeAction.tsx` | **LIFT + EXTEND** with AT-6's provenance stamp. |
| `components/ArcTemplateLibraryView.tsx` | **LIFT + FIX.** Its empty state (`:50-52`) is the dangling CTA: *"…or import a story to deconstruct"* — **there is no import entry point anywhere in `frontend/src`** (`grep -rn "import-sources" frontend/src` → **empty**). |
| `components/MotifStateBoundary.tsx` · `CostConfirmCard.tsx` · `AdoptTargetModal.tsx` | **SHARED with spec 33 — do NOT fork.** Import from wherever pre-flight cmd 7 finds them. |
| 🔴 `components/ArcConformancePanel.tsx` · `hooks/useArcConformance.ts` · `useArcConformanceRun.ts` | **DROPPED from `arc-templates` (AT-7).** Dead at HEAD on **both** calls: `motifApi.arcConformance` sends `?arc_template_id=` (FastAPI **silently drops** the unknown param ⇒ `arc_id=None` ⇒ 422); `arcConformanceRunPropose` sends `arc_template_id` into `_ConformanceRunArgs`, which is `ForbidExtra` and has no such field ⇒ arg-validation refusal. **Owner: spec 33's M-BUG-4.** Dropping it costs nothing. |
| `components/MotifMinePanel.tsx` + `hooks/useMotifMine.ts` | **THE PRECEDENT to copy** for the Deconstruct section: `ModelRolePicker` (capability `chat`) → propose (`mcpExecute`) → `CostConfirmCard` → confirm. ⚠ **Copy only its PROPOSE + CONFIRM legs. Do NOT copy its POLL leg** — `mineConfirm` polls `compositionApi.getJob`, which **404s** on a Work-less job (§3.1). Copying it copies a live bug. |

### 3.4 Frontend — plan-hub (🔧 spec 34 has the names wrong)

`frontend/src/features/plan-hub/api.ts` exports **free functions**, not a `planHubApi` object:

| Actual export | Line | Shape |
|---|---|---|
| `getArcs(bookId, token)` | ~20 | → `{ arcs: ArcListNode[] }` (it normalises the route's `{nodes}` envelope — *"a live smoke caught the `nodes`-vs-`arcs` drift"*). |
| `moveArc(...)` | ~190 | — |
| **`assignChapters(bookId, structureNodeId, chapterNodeIds, token)`** | ~241 | → `{ assigned: number; structure_node_id: string }` |
| ~~`planHubApi.assignArcChapters`~~ | — | 🔧 **DOES NOT EXIST** — and neither does the `planHubApi` **object** (`grep -rn "planHubApi" frontend/src` → **0 hits**; this file is **bare named exports**). Spec 34 AT-6 names both wrongly. The real name is **`assignChapters`**. |
| **`createArc`** | — | 🔧 **DOES NOT EXIST — AND THIS WAVE DOES NOT ADD IT.** 🔴 **ADJUDICATED (adjudication **D**, `Q-34-OQ2-DOUBLE-MATERIALIZE` / `Q-34-AT6-SILENT-NOOP`):** the original plan told W4-FE4 to add `createArc` + call `assignChapters`. **That shape is a BUG:** `materialize` **already created** the spec arc and **already linked** its chapters (`outline.py:435-446`), so `createArc` mints a **SECOND** arc and `assignChapters` **re-points the chapters off** the first one — leaving materialize's arc **active-but-childless** (the `D-A3-REPLACE-ORPHAN-ARC-NODES` / FD-17 orphan class, and a rival writer of one column, which §9 forbids). **AT-6 needs NEITHER call.** The §9 "ONE writer of `structure_node` arcs, in plan-hub" **LOCK still stands** — it simply has no work to do in Wave 4. **Standing rule for whoever builds spec 32 (`arc-inspector`) later:** it imports `createArc`/`assignChapters` from `plan-hub/api` — plan-hub remains the single writer. (`Q-34-PLANHUB-CREATEARC`'s naming corrections are preserved above; its *build* instruction is superseded by D.) |

### 3.5 Frontend — studio registration surfaces

| File | Fact |
|---|---|
| `frontend/src/features/studio/panels/catalog.ts` | `StudioPanelDef = { id, component, titleKey, descKey, category, guideBodyKey?, hiddenFromPalette?, tourAnchor? }`. `StudioPanelCategory` **already includes `'storyBible'`**. |
| `services/chat-service/app/services/frontend_tools.py:400-402` | The `panel_id` **enum** (57 entries at HEAD) and the tool **description** prose (`:403-481`). |
| `contracts/frontend-tools.contract.json` | **NEVER hand-edit — regenerate.** |
| `frontend/src/features/studio/agent/effectRegistry.ts:31,45` | `registerEffectHandler(pattern: string \| RegExp, handler)`. **String branch is `tool === p \|\| tool.startsWith(p)` — NOT a pattern match. Use a `RegExp` for anything with alternation.** `matchEffectHandlers` returns **every** match; `runEffectHandlers` **awaits all**. |
| `frontend/src/features/studio/panels/useQualityWork.ts` | 🔑 **THE Work gate.** `useQualityWork(bookId, token) → {kind:'loading'\|'unavailable'\|'no-work'\|'ready', projectId?}`. **REUSE IT. Do not re-derive it a fourth time** — its own header says three independent re-derivations is exactly what this file exists to stop. |
| `frontend/src/features/studio/host/studioLinks.ts` | The deep-link resolver (`kind: 'studio' \| 'external' \| 'blocked'`). |
| `frontend/tests/e2e/specs/` | Playwright specs live here (`studio-compose.spec.ts`, `studio-palette.spec.ts` are the precedents). Config: `frontend/playwright.config.ts`. |

---

## 4 · BACKEND PREREQUISITE SLICES — these come FIRST

**A panel slice may not precede its route slice.** Order:
**W4-BE0 (CONTRACT) → W4-BE1 → W4-BE2 → W4-BE3 → W4-BE4 → W4-BE5 → the FE slices.**

---

### W4-BE0 — 🔴 CONTRACT-FIRST · freeze the OpenAPI for BE-7a + BE-7b **BEFORE** any FE flow

**Kind:** BE (contract) · **dependsOn:** — · **Size:** XS

**Why this is its own slice and why it is FIRST.** CLAUDE.md: ***"Contract-first: API contract frozen
before frontend flow."*** This wave adds **two** new REST routes. Specs 23 and 24 both shipped routes
with **no contract entry** — `arc.py` alone has **14 undocumented routes** today. *"Do not compound it"*
means **do not add a 15th** — it does **not** mean "clean up the backlog inside an XS slice"
(`Q-34-OPENAPI-CONTRACTS`'s scope fence). W4-BE1/W4-BE2 then implement **to** this frozen contract.

**The ONE file:** **`contracts/api/composition/v1/openapi.yaml`**
🔧 **NOT** `contracts/api/composition-service/plan-forge.v1.yaml` (that is the PlanForge-only surface).
Its `servers.url` is already `/v1/composition` (`:12-13`), so **path keys carry NO `/v1/composition`
prefix** — matching every existing entry (`/books/{book_id}/work`, `/jobs/{job_id}`, …). `arc.py` declares
`APIRouter(prefix="/v1/composition")` (`:63`), so contract path ⇄ route line up 1:1.

**Edits (all four, in one commit):**

1. **`tags:` (`:16-22`)** — append `- name: arc`.
2. **Insert TWO path items immediately BEFORE `components:` (`:309`):**
   - **`/arcs/{node_id}/extract-template:`** → `post`, tags `[arc]`, param `$ref: '#/components/parameters/NodeId'` (**reuse it — do not invent a new parameter component**), requestBody `ArcExtractTemplateRequest` = `{required:[code,name], code:string, name:string, language:string default 'en', visibility: enum [private, unlisted] default 'private'}`; responses `'201'` → `ArcExtractTemplateResult` = `{success:boolean, outcome: enum[extracted], template_id:uuid, member_chapter_node_ids:[uuid], layout_placements:integer, pacing_chapters:integer}`; `'404': {$ref:'#/components/responses/NotFound'}`; `'409': {$ref:'#/components/responses/DuplicateCode'}`.
   - **`/arc-templates/suggest:`** → `post`, tags `[arc]`, requestBody `ArcSuggestRequest` = `{required:[project_id], project_id:uuid, premise:string nullable, genre:string nullable, limit:integer default 5, detail: enum [summary, full] default 'full'}` — 🔴 **`detail` is an ENUM, not a free string** (Context Budget Law §6b + the closed-set rule); responses `'200'` → `ArcSuggestResult` = `{candidates:[{arc_template:object, score:number, match_reason:object}], detail:string, count:integer, truncated:integer}` (mirror the `apply_response_contract` meta); `'404': {$ref:'#/components/responses/NotFound'}`.
3. **`components.responses` (`:318-321`)** — add
   `DuplicateCode: { description: "409 — an arc template with this (owner, code, language) already exists in your library; surface it on the `code` field" }`.
4. **`components.schemas`** — add the four schemas named above.

**⚠ LINT NOTE — do not hunt for a gate that does not exist.** `scripts/lint-contract.sh` lints **only**
`contracts/api/identity/v1/openapi.yaml`. **Nothing machine-checks the composition contract.** So the DoD
for this slice is a **human / `/review-impl` check that the two path items match the two FastAPI handlers'
Pydantic request/response models exactly** (field names + the `detail` and `visibility` enums) — **not
"spectral passed."**

**SCOPE FENCE (adjudicated, veto-able by the PO):** document **only BE-7a and BE-7b**. The ~14 historical
undocumented `arc.py` routes get a **tracked defer row**, not a drive-by backfill:
**`D-COMPOSITION-OPENAPI-BACKLOG`** (§11).

**DoD evidence:** `"W4-BE0: contracts/api/composition/v1/openapi.yaml carries /arcs/{node_id}/extract-template + /arc-templates/suggest + the DuplicateCode response + 4 schemas; tags gains 'arc'; contract frozen BEFORE W4-BE1/BE2 implement it; D-COMPOSITION-OPENAPI-BACKLOG filed for the 14 pre-existing undocumented routes"`

---

### W4-BE1 — `POST /v1/composition/arcs/{node_id}/extract-template` (BE-7a)

**Why REST and not a bridge-allowlist entry (AT-3):** `composition_arc_extract_template` is a **Tier-A
WRITE**, and `FE_BRIDGE_TOOL_ALLOWLIST`'s own contract is *"NOTHING here writes or deletes."* Adding a
write to it would silently void the BFF's stated trust model.

**Kind:** BE · **dependsOn:** `W4-BE0` · **Size:** XS

**Route contract**

```
POST /v1/composition/arcs/{node_id}/extract-template
Auth:    Bearer JWT.  Gate: VIEW on the arc's book, DERIVED FROM THE ROW (_gate_arc).
Body:    { "code": str(1..), "name": str(1..), "language": str = "en",
           "visibility": "private" | "unlisted" = "private" }        ← ForbidExtra
         (NOTE: 'public' is deliberately excluded at create — publishing is the
          separate PATCH visibility flip, which also fires the strip trigger. Mirror
          the MCP _ArcExtractTemplateArgs Literal exactly.)
201:     { "success": true, "outcome": "extracted", "template_id": "<uuid>",
           "member_chapter_node_ids": ["<uuid>", …],
           "layout_placements": <int>, "pacing_chapters": <int> }
409:     { "code": "ARC_TEMPLATE_CODE_EXISTS",
           "message": "an arc template with this code + language already exists" }
404:     NOT_ACCESSIBLE_MESSAGE  (uniform H13 — missing node OR denied grant, same body)
403:     "insufficient access"   (grant present but under-tier)
```

🔴 **THREE ADJUDICATIONS THE BUILDER MUST NOT GET WRONG** (`Q-34-BE7A-EXTRACT-ROUTE`):

1. **`201`, not `200`** — it creates a resource, and it matches its siblings (`POST /arc-templates` → 201,
   `POST /{id}/adopt` → 201). Freeze `201` in W4-BE0's contract too.
2. **The 409 map — DO NOT "mirror the MCP handler verbatim".** Spec 34's phrase *"mirror the MCP handler
   verbatim including the `UniqueViolationError`→409 map"* is **self-contradictory**: the MCP handler does
   **NOT** map to 409 — it returns a 200-style envelope `{"success": False, "outcome": "applied_conflict"}`
   (`server.py:4663-4667`), because MCP has no HTTP status. Following it literally ships a **200 on
   duplicate**, violating this route's own error contract. **Mirror the handler's LOGIC, not its return
   envelope:** catch `asyncpg.UniqueViolationError` → `raise HTTPException(409)`. This is what the engine
   itself mandates (`arc_apply.py:660-663`: *"raises `asyncpg.UniqueViolationError`, which the caller maps
   to a 409 — this seam does not swallow it"*). **Do NOT add a try/except inside the engine.** Use the code
   **`ARC_TEMPLATE_CODE_EXISTS`** (one name for one concept — it is what `POST /arc-templates` already
   raises; the decisions file's snippet wrote `ARC_TEMPLATE_DUPLICATE`, which would be a second name for
   one thing).
3. **The gate is `VIEW`, not `EDIT`** — mirroring the MCP handler (`server.py:4648`). You only **read** the
   arc to extract from it; the new template is owner-stamped to the caller in their own always-writable
   library. ⚠ **The adjacent `delete_arc`/`restore_arc` use `GrantLevel.EDIT` — copy-pasting the wrong
   sibling silently OVER-gates this route.** The regression test that locks it is `(d)` below.
4. **Do NOT re-map the response** — the engine already returns the exact shape. Return it as-is. Unlike the
   MCP handler, **do NOT append the `_meta` / `undo_hint` key** (that is an MCP-envelope concern, not REST).

**Files**

1. **EDIT `services/composition-service/app/routers/arc.py`**
   - Add near the other `structure_node` models (after `ArcAssignChapters`, ~line 366):
     ```python
     class ArcExtractTemplateBody(_ForbidExtra):
         code: _Code
         name: _Title
         language: _Lang = "en"
         # 'public' excluded at create — publishing is the separate visibility flip
         # (which fires arc_template_publish_strip). Mirrors _ArcExtractTemplateArgs.
         visibility: Literal["private", "unlisted"] = "private"
     ```
     (`_Code`, `_Title`, `_Lang`, `_ForbidExtra` are already imported from `app.db.models`? — **check**:
     `arc.py:35-42` imports `_ForbidExtra` and `_Key`. **Add `_Code`, `_Lang`, `_Title` to that import
     list.** If a name is absent from `db/models.py`, fall back to `Annotated[str, StringConstraints(...)]`
     copied from `_ArcExtractTemplateArgs` in `mcp/server.py:4615-4625`.)
   - Add the handler **after `restore_arc`** (so it sits with the by-id `structure_node` routes):
     ```python
     @router.post("/arcs/{node_id}/extract-template", status_code=201)
     async def extract_arc_template(
         node_id: UUID,
         body: ArcExtractTemplateBody,
         user_id: UUID = Depends(get_current_user),
         grant: GrantClient = Depends(get_grant_client_dep),
     ) -> dict[str, Any]:
         """BE-7a — the REST twin of composition_arc_extract_template (AT-3: a Tier-A
         WRITE may not ride the FE bridge allowlist). Thin wrapper over the SHIPPED
         engine `extract_template_from_arc` (engine/arc_apply.py:652). Reading the spec
         to extract from it → VIEW on its book (derived from the ROW); the new template
         is owner-stamped to the caller. The engine deliberately does not swallow the
         UniqueViolationError — we map it to 409 on the `code` field."""
         structures = _structures()
         node = await _gate_arc(structures, grant, user_id, node_id, GrantLevel.VIEW)
         try:
             result = await extract_template_from_arc(
                 get_pool(), arc_node=node, owner_user_id=user_id,
                 code=body.code, name=body.name,
                 language=body.language, visibility=body.visibility,
             )
         except asyncpg.UniqueViolationError:
             raise HTTPException(status_code=409, detail={
                 "code": "ARC_TEMPLATE_CODE_EXISTS",
                 "message": "an arc template with this code + language already exists",
             })
         return result
     ```
   - **Import:** add `extract_template_from_arc` to the existing
     `from app.engine.arc_apply import build_apply_plan` line (→ `import build_apply_plan, extract_template_from_arc`).
     `import asyncpg` is **already present** at `arc.py:28`; `NOT_ACCESSIBLE_MESSAGE` at `:32`.
   - ⚠ **Do NOT re-implement the engine.** It ships. This route is 12 lines.

2b. 🔴 **CLOSE THE LINEAGE-LAUNDERING HOLE — FIX-NOW, ONE LINE** (`Q-34-AT9-PUBLISH-STRIP` item 7).
   `extract_template_from_arc` calls `ArcTemplateRepo.create` with the **default `imported_derived=False`**
   (`arc_apply.py:652-673`), so **extracting a template from an arc that was materialized FROM AN IMPORTED
   TEMPLATE mints an UNTAINTED template** — and `arc_template_publish_strip` then **never fires for it**.
   The raw source reference of a copyrighted import survives a publish. **Fix it in this wave, in this
   route** (the repo already accepts the flag — `arc_template_repo.py:97`):
   - resolve the source arc's `structure_node.arc_template_id` (W4-BE4's stamp is what puts it there);
   - if that template has `source='imported' OR imported_derived` ⇒ pass **`imported_derived=True`** into
     `extract_template_from_arc` (thread the kwarg through to `ArcTemplateRepo.create`).
   - **Backend test:** extract-from-a-materialized-imported-arc ⇒ the new template row has
     `imported_derived = TRUE`, and a subsequent `visibility='public'` PATCH **strips** its `source_ref`
     to `lineage:<id>` (assert the trigger fired).

2. **CREATE `services/composition-service/tests/unit/test_arc_extract_route.py`**
   House style = `tests/unit/test_arc_hub_routes.py` (TestClient + dependency overrides + a `_Grant` stub).
   **TDD: write these first, watch them red, then add the route.**
   | Test name | Asserts |
   |---|---|
   | `test_extract_happy_path_returns_template_id` | **201**; body has `template_id`, `outcome=="extracted"`, `member_chapter_node_ids`, `layout_placements`, `pacing_chapters`. The engine is monkeypatched to a stub returning the canonical dict. **Assert NO `_meta` / `undo_hint` key** (that is MCP-envelope, not REST). |
   | `test_extract_duplicate_code_is_409_on_the_code_field` | The engine stub raises `asyncpg.UniqueViolationError` ⇒ **409** with `detail["code"] == "ARC_TEMPLATE_CODE_EXISTS"`. 🔒 **Assert it is NOT a 200 envelope and NOT a 500** — the engine's exception must SURFACE as 409 (the MCP twin's `applied_conflict` shape must never be copied here). |
   | `test_extract_missing_node_is_uniform_404` | `StructureRepo.get` → `None` ⇒ **404** with the `NOT_ACCESSIBLE_MESSAGE` body. |
   | `test_extract_foreign_book_is_the_SAME_uniform_404` | Grant resolves to `None` on the row's book ⇒ **404**, **byte-identical body** to the missing-node case (no existence oracle). |
   | 🔒 `test_extract_VIEW_only_grantee_SUCCEEDS_with_201` | **THE GATE LOCK.** A **VIEW-only (non-EDIT)** grantee gets **201**. This test **REDS the moment someone raises the gate to `EDIT`** by copy-pasting `delete_arc`/`restore_arc`. |
   | `test_extract_gate_derives_from_the_ROW` | The grant stub was asked about **the NODE's** `book_id`, never a body-supplied one. |
   | `test_extract_visibility_public_is_rejected_by_the_schema` | `{"visibility":"public"}` ⇒ **422** (the `Literal` closes the set). |
   | 🔒 `test_extract_from_an_imported_derived_arc_taints_the_new_template` | **THE LAUNDERING LOCK (2b).** The source arc's template has `source='imported'` ⇒ the created template carries **`imported_derived=True`**. Without this, publishing it never fires the strip trigger. |

3. **CONTRACT: already frozen in `W4-BE0`.** Verify the implemented Pydantic models **match** the frozen
   path item field-for-field (incl. `201` and the `visibility` enum). If they differ, **the contract is
   right and the code is wrong** — that is what contract-first means.

**Tests to run:** `cd services/composition-service && python -m pytest tests -q -n auto --dist loadgroup`

**DoD evidence:** `"W4-BE1: composition suite <N> passed (was <N-8>); 8 new in tests/unit/test_arc_extract_route.py incl. the VIEW-only-201 gate lock and the imported_derived laundering lock; implementation matches W4-BE0's frozen contract (201 + visibility enum)"`

---

### W4-BE2 — `POST /v1/composition/arc-templates/suggest` (BE-7b)

**Why REST (AT-4):** it *is* a read, so the bridge allowlist would technically work — but the FE reaches
composition **over REST everywhere else**, and a GET-shaped read has no reason to take the agentic path.
REST keeps this wave **single-service** and skips a gateway change entirely.

🔴 **BE-7b is the SOLE OWNER of arc-suggest.** Plan 30 §7 Wave 3: *"spec 33's BE-M5 duplicate is deleted."*
If Wave 3 shipped an arc-suggest route anyway, **STOP building this one and consume theirs** — two routes
over one retriever is the duplicate-writer bug. Pre-flight check:
`grep -rn "arc-templates/suggest\|retrieve_arcs" services/composition-service/app/routers/`

**Kind:** BE · **dependsOn:** `W4-BE0` · **Size:** XS

**Route contract**

```
POST /v1/composition/arc-templates/suggest
Auth:   Bearer JWT.  Gate: VIEW on the WORK's book (via WorksRepo → authorize_book).
Body:   { "project_id": "<uuid>", "premise": str|null (max 20000), "genre": str|null (max 100),
          "limit": int = 5 (1..25), "detail": "summary" | "full" = "full" }   ← ForbidExtra
200:    { "candidates": [ { "arc_template": {...}, "score": <float>,
                            "match_reason": {...} }, … ],
          ...meta }                      ← the apply_response_contract meta (detail, count, truncated)
404:    "work not found"  (uniform — missing Work OR denied grant)
403:    "insufficient access"
```

⚠ **Keep `detail`** — Context Budget Law §6b. Do not "simplify" it away. Default `full` = byte-identical
to the MCP twin (`server.py:2296`); the FE ranked list calls it with `detail='summary'`.
⚠ **Keep `match_reason`** — it is the **only** explanation the user gets for a ranked list (§4.2 of the
spec). Throwing it away is the bug this route exists to avoid.

🔴 **ADJUDICATED — `premise` IS A PURE PASSTHROUGH** (`Q-34-OQ3-SUGGEST-PREMISE`). **Do NOT seed `premise`
from `book.summary` server-side**, even though `book_client.get_book()` could. A BE fallback is a **silent
hidden default** (settings-and-config SET-2) and it would make it **impossible to suggest against a premise
that DIFFERS from the book summary**. `premise=None` stays `None`. **No validation error on an empty
premise** — an empty premise is a *legal* call: `motif_retrieve.py:300` builds
`qtext = " ".join([premise or "", genre or ""])`; an empty `qtext` ⇒ no query vector ⇒ the ranker
**degrades to genre order** and *"never 500/[]"* (`:306`). The seed happens **on the FE** (W4-FE6).

🔴 **NO COST GATE / CONFIRM TOKEN** (`Q-34-BE7B-SUGGEST-ROUTE` item 3). `retrieve_arcs` does one
`embed_query` + a bounded owner-scoped lazy back-fill and degrades to genre order on `EmbeddingError`. It
is a **read** (the MCP twin is `require_meta("R","book")`). Adopt/apply set the precedent: **reads are
ungated.**

#### 🔴 STEP 0 — KILL THE FORK RISK FIRST (a 2-file prep; do this BEFORE the route)

`_ARC_REF_FIELDS` (`server.py:233-236`) and `_arc_public_projection` (`server.py:2333-2341`) are the
**tenant allow-list** that drops `embedding` / `embedding_model` / `embedding_dim` / `source_ref` /
`owner_user_id` / `source_version` from a non-owned arc. 🔴 **Do NOT copy them into the router — two
writers of one allow-list is the exact drift class this repo has already been bitten by**
(`css-var-duplicated-across-two-consumers-drifts`, applied to a **tenancy** projection: a drift here leaks
another user's `source_ref`).

- **CREATE `services/composition-service/app/projections.py`** exporting **`ARC_REF_FIELDS`** and
  **`arc_public_projection(arc) -> dict`** — move the bodies **verbatim**, with **no heavy imports**, so a
  router can import it.
- **EDIT `services/composition-service/app/mcp/server.py`** — replace the two defs with
  `from app.projections import ARC_REF_FIELDS as _ARC_REF_FIELDS, arc_public_projection as _arc_public_projection`.
- **Same for the gate:** promote `engine.py:219 _gate_work` into **`app/grant_deps.py`** as
  `async def gate_work(works, grant, user_id, project_id, need)` — **verbatim** (`works.get(project_id)` →
  `None` ⇒ 404 no-oracle; `authorize_book(...)` → `OwnershipError` ⇒ **the same** 404; `InsufficientGrant`
  ⇒ 403) — and make `engine._gate_work` a **one-line delegate** so its existing tests stay green.
- The route then calls `gate_work(...)`. **Do not hand-roll a third `works.get` + `_gate_book` pair.**

**Files**

1. **EDIT `services/composition-service/app/routers/arc.py`**
   Mirror `mcp/server.py:2287-2325` **verbatim**, swapping the MCP gate for the REST one.
   ```python
   class ArcSuggestBody(_ForbidExtra):
       project_id: UUID
       premise: str | None = Field(default=None, max_length=20000)   # matches import_source's cap
       genre: str | None = Field(default=None, max_length=100)
       limit: int = Field(default=5, ge=1, le=25)
       detail: Literal["summary", "full"] = "full"                   # mirrors server.py:2296


   @router.post("/arc-templates/suggest")
   async def suggest_arc_templates(
       body: ArcSuggestBody,
       user_id: UUID = Depends(get_current_user),
       works: WorksRepo = Depends(get_works_repo),          # deps.py:104
       grant: GrantClient = Depends(get_grant_client_dep),
       retriever: MotifRetriever = Depends(get_motif_retriever),   # deps.py:205 — ALREADY WIRED
   ) -> dict[str, Any]:
       """BE-7b — the REST twin of composition_arc_suggest (AT-4). Ranks the caller-
       visible arc_template set for this Work's premise/genre: SQL pre-filter → embed →
       cosine → match_reason → genre-degrade. Keeps `detail` (Context Budget Law §6b)
       and `match_reason` (the only explanation a ranked list gets). `premise` is a PURE
       PASSTHROUGH — never seeded server-side (SET-2: no silent hidden default)."""
       work = await gate_work(works, grant, user_id, body.project_id, GrantLevel.VIEW)
       candidates = await retriever.retrieve_arcs(
           user_id, book_id=work.book_id, project_id=body.project_id,
           premise=body.premise, genre=body.genre, limit=body.limit,
       )
       arc_dicts, meta = apply_response_contract(
           [
               c.arc_template.model_dump(mode="json")
               if getattr(c.arc_template, "owner_user_id", None) == user_id
               else _arc_public_projection(c.arc_template)
               for c in candidates
           ],
           ref_fields=_ARC_REF_FIELDS, detail=body.detail,
       )
       return {
           "candidates": [
               {"arc_template": arc_dicts[i], "score": c.score, "match_reason": c.match_reason}
               for i, c in enumerate(candidates)
           ],
           **meta,
       }
   ```
   **Imports needed in `arc.py`** (all resolved by STEP 0 — **no copy-paste**):
   - `ARC_REF_FIELDS`, `arc_public_projection` — **from `app.projections`** (the new shared module).
   - `gate_work` — **from `app.grant_deps`** (the promoted `_gate_work`).
   - `apply_response_contract` — `sdks/python/loreweave_mcp/response.py:33`.
   - `MotifRetriever` / `get_motif_retriever`, `WorksRepo` / `get_works_repo` — from `app.deps`
     (`:104`, `:205` — **already wired**; do not construct them by hand).
   - ⚠ **Route-order trap:** FastAPI matches in declaration order and
     `GET /arc-templates/{arc_id}` already exists. This is a **POST**, so there is no collision with the
     GET — but if you ever add `GET /arc-templates/suggest`, it **must** be declared **before**
     `/{arc_id}` or `suggest` will be parsed as a UUID and 422. `/catalog` (`arc.py:132`) is declared
     before `/{arc_id}` (`:157`) for exactly this reason. **Follow that precedent.**

2. **CREATE `services/composition-service/tests/unit/test_arc_suggest_route.py`**
   | Test name | Asserts |
   |---|---|
   | `test_suggest_returns_candidates_with_score_and_match_reason` | 200; every candidate has **all three** of `arc_template`, `score`, `match_reason`. **This is the anti-regression for "the FE throws the explanation away".** |
   | `test_suggest_detail_summary_projects_refs_only` | `detail="summary"` ⇒ each `arc_template` lacks `threads`/`layout`/`pacing`, **but keeps `score` + `match_reason`**. |
   | `test_suggest_detail_full_keeps_every_field` | `detail="full"` ⇒ `threads`/`layout`/`pacing` present. |
   | `test_suggest_missing_work_is_404` | `WorksRepo.get` → `None` ⇒ 404. |
   | `test_suggest_denied_grant_is_the_same_404` | Grant `None` ⇒ 404, **same body** (no oracle). |
   | `test_suggest_non_owner_candidate_is_public_projection` | A candidate whose `owner_user_id != caller` comes back through `_arc_public_projection` (no `source_ref`, no `embedding`). |
   | `test_suggest_rejects_unknown_field` | `{"nonsense": 1}` ⇒ 422 (`ForbidExtra`). |
   | `test_suggest_empty_prefilter_returns_empty_candidates_not_500` | No visible arcs ⇒ `{"candidates": []}`, **not a 500**. |
   | `test_suggest_null_premise_is_legal` | `premise=None` ⇒ **200** (the ranker degrades to genre order). **No 422.** This locks the pure-passthrough decision. |
   | 🔒 `test_the_projection_has_ONE_home` | `app.mcp.server._ARC_REF_FIELDS is app.projections.ARC_REF_FIELDS` (identity, not equality) — the anti-fork assertion for STEP 0. |

3. **CONTRACT: already frozen in `W4-BE0`.** Verify the Pydantic model matches it (esp. the `detail` enum
   and `limit`'s bounds).

**DoD evidence:** `"W4-BE2: composition suite <N> passed; 10 new in tests/unit/test_arc_suggest_route.py; match_reason asserted present on every candidate; app/projections.py + app/grant_deps.py extracted (ONE home each, identity-asserted); premise is a pure passthrough (null ⇒ 200)"`

---

### W4-BE3 — `GET /v1/composition/motif-jobs/{job_id}` (BE-7c) — **CONDITIONAL**

🔴🔴 **RE-SCOPED BY ADJUDICATION E (`Q-34-JOB-NOT-POLLABLE`, `Q-34-BE7C-OWNERSHIP-CHECK`). THE ORIGINAL
PLAN SCOPED THIS AS "ADD A READ ROUTE, XS". THAT IS NECESSARY BUT NOT SUFFICIENT — AND THE WAVE WOULD
HAVE SHIPPED THE PAID-ACTION DEFECT INTACT.**

> **A poll route over a job that is never created polls nothing.**
>
> `_enqueue_motif_job` stamps a **synthetic** `pid=uuid4()` (`actions.py:552`). `GenerationJobsRepo.create`
> inserts via `INSERT INTO generation_job (…) SELECT $1,$2,w.book_id,… FROM composition_work w WHERE
> w.project_id=$2` (`generation_jobs.py:159-172`). For a synthetic pid there is **no `composition_work`
> row** ⇒ **0 rows inserted** ⇒ `row is None` ⇒ **`raise ReferenceViolationError`** (`:198-206`) — and
> **nothing in `actions.py` catches it** ⇒ an **uncaught 500**. No job row. No XADD. No worker run.
> **Meanwhile `_claim_or_replay` has already burned the one-shot confirm token (`actions.py:639`) and
> `_precheck_or_402` has already placed a billing hold (`:642`) — and `BillingClient` has NO release.**
>
> **LIVE DB, verified: `SELECT operation, count(*) FROM generation_job GROUP BY 1` →
> `plan_forge_propose 11`, `plan_pass 4`. ZERO `mine_motifs`. ZERO `analyze_reference`. They have NEVER
> been created, not once.**
>
> This is the PO's ***"paid-action defect that would charge the user for nothing"***, in full. It is
> **not deferrable.**

🔴 **RUN PRE-FLIGHT CMD 4 — BOTH HALVES (4a the read route, 4b the write side).**
- **4a AND 4b green** ⇒ Wave 3 / 3a built BE-7c properly. **VERIFY the shape below**, then **SKIP this
  slice** and consume it. Record: *"BE-7c verified as built in Wave 3/3a, write side included."*
- **4a green, 4b still broken** ⇒ Wave 3 shipped a **read route over a row that is never written**.
  The defect stands. **The WRITE half (S1–S5) is IN SCOPE here**, and raise it to spec 33's owner.
- **4a EMPTY** (the state at planning time) ⇒ **BUILD ALL OF IT HERE.** It is not "blocked" — it is
  **unbuilt work** (CLAUDE.md's anti-laziness rule). Every signal exists: `created_by` is a real column
  (`generation_jobs.py:48,92`), and the worker never reads `project_id` for these ops
  (`job_consumer.py:373-381` dispatches on `input['worker_op']`).

🔴 **SCOPE CORRECTION — TWO ops, not three** (`Q-34-MINECONFIRM-DEAD` item 3). BE-7c covers exactly the
**two synthetic-pid operations**: `mine_motifs` (`actions.py:643`) and `analyze_reference` (`:693`).
**The deep-conformance job is NOT affected** — `_execute_conformance_run` (`actions.py:723-725`) passes a
**REAL** `project_id`, so its `/jobs/{id}` poll resolves a real Work. 🔴 **`motifApi.arcConformanceRunConfirm`
(`motif/api.ts:286-289`) WORKS and MUST STAY on `compositionApi.getJob`. Do NOT re-point it. Do NOT
regress it.**

**Kind:** BE · **dependsOn:** — · **Size:** 🔴 **M** (migration + repo + enqueue rewire + spend reorder +
2 gates + an MCP tool-signature change), **not XS**.

**Route contract**

```
GET /v1/composition/motif-jobs/{job_id}
Auth:  Bearer JWT.
Gate:  the ROW'S OWNER — generation_job.created_by == caller.
       ⚠ NOT a book grant. A mine/import job is genuinely NOT Work-bound; its
       scope key is its OWNER, not a book. This is the repo's
       `gate-must-derive-scope-from-the-loaded-row` memory applied to a row whose
       parent is a USER.
       ⚠ Do NOT "fix" this by back-filling a real project_id. The row is Work-less
       by design.
200:   the generation_job row (model_dump) — { id, status, operation, result, cost_usd,
       created_at, updated_at, … }
404:   uniform H13 — the SAME body for "no such job" and "not your job". No existence
       oracle.
```

Covers the **two Work-less** job kinds: `analyze_reference` (拆文) and `mine_motifs` (Wave 3's ⛏ Mine —
its poll is the 4th live 404). 🔴 **NOT** the deep-conformance job (it has a real `project_id`; leave it
on `/jobs/{id}`).

**Files — S1..S7. S1–S5 are the WRITE half (the part the original plan missed). S6–S7 are the READ half.**

---

**S1 · MIGRATION (relax-only, non-destructive, idempotent).**
🔴 **DO NOT WRITE A NEW DDL BLOCK HERE. COPY `W0-BE1`'s, VERBATIM** (canonical detail: Wave 3 `3a-1` §(a);
Wave 0 `W0-BE1` step (a)). It is: `ALTER TABLE generation_job ALTER COLUMN project_id DROP NOT NULL;` +
the same for `book_id`, + the **`generation_job_scope_shape` both-or-neither CHECK**, + the partial index
**`idx_generation_job_owner_unbound`**.

⚠ **An earlier cut of this slice wrote a DIFFERENT constraint** — `generation_job_project_scope_chk
CHECK (project_id IS NOT NULL OR operation IN ('mine_motifs','analyze_reference'))` — plus a differently-named
index. **Both are superseded and must NOT be written.** Two reasons, and they are the reasons Wave 0 chose
its shape:
1. **An operation-enumerating CHECK forces a DDL change on every new Work-less op**, and a new enum value in
   a CHECK must be **back-filled into every historical CHECK block**
   (`migration-check-constraint-must-backfill-all-historical-blocks`). Wave 0's CHECK constrains the **SHAPE**
   (both scope keys NULL, or both set) so a third Work-less op needs **zero DDL**. The op allowlist lives in
   the **writer** (`create_unbound()`), where a new op is one line.
2. **Two names for one invariant** — the schema would carry two constraints and two indexes for the same
   rule. *One name for one concept* is a repo law; it applies to schema objects too.

🔴 **`created_by` STAYS `NOT NULL`** — it becomes the owner axis, and it is the gate.
🔴 **This is NOT a back-fill.** Do **not** invent a real `project_id` for a Work-less row (§5's ban stands).
`DROP NOT NULL` **always re-applies** (unlike `ADD COLUMN IF NOT EXISTS`, which never revisits a bad
default) — so it is safe to re-run. Verified live: all three columns are currently `NOT NULL`; there is
**no FK** on `project_id` (only on `outline_node_id`).

**S2 · MODEL.** `app/db/models.py:364-365` → `project_id: UUID | None = None`, `book_id: UUID | None = None`.

**S3 · REPO — a Work-less insert path.** `app/db/repositories/generation_jobs.py`: add
`create_unbound(*, created_by, operation, input, book_id=None, status='pending')` — a **PLAIN `INSERT …
VALUES`** (no `SELECT … FROM composition_work`), same `emit_job_event` **in the same transaction**
(`owner_user_id=created_by` already). 🔴 **Keep the existing Work-bound branch byte-for-byte** so
`conformance_run` / `generate` / `plan_pass` are untouched.

**S4 · ENQUEUE.** `app/routers/actions.py:534-561` (`_enqueue_motif_job`): **DELETE the
`pid = project_id if project_id is not None else uuid4()` line** and the false comment above it. Take
`book_id: UUID | None`. When `project_id is None` ⇒ `create_unbound(...)` (pass `book_id` when the mine is
`scope='book'`, else `NULL`) and call `enqueue_job(..., project_id="")` — **safe**: `job_consumer.py:373-381`
dispatches `mine_motifs` / `analyze_reference` on `input['worker_op']` and their handlers take only
`user_id` + `input`. At `:643` (mine) pass the payload's `book_id`; at `:693` (arc_import) pass
`book_id=None` (`import_source` is user-scoped and un-shareable — §12.6).

**S5 · 🔴 ORDER SPEND AFTER DURABILITY — THIS IS THE CHARGED-FOR-NOTHING FIX.** In `_execute_motif_mine`
and `_execute_arc_import`, **reorder** to:
```
_claim_or_replay  →  CREATE the job row (pending; no spend yet)  →  _precheck_or_402  →  XADD
```
On a **402**, mark the now-existing job **`failed`** with `result={"error":{"code":"quota_exhausted"}}` and
**still return its `job_id`** — so the failure is **POLLABLE** instead of a naked 402 + a dangling hold.
Wrap the create in `except ReferenceViolationError` → **400/409 `action_error`**, **never a bare 500**.

---

**S6 · READ ROUTE.** **EDIT `services/composition-service/app/routers/engine.py`** — add **directly after** `get_job`
   (`:1415`), so the two readers sit side by side and the contrast is legible:
   ```python
   @router.get("/motif-jobs/{job_id}")
   async def get_motif_job(
       job_id: UUID,
       user_id: UUID = Depends(get_current_user),
       jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
   ) -> dict[str, Any]:
       """BE-7c (AT-11) — the OWNER-scoped job read. A mine/import/deconstruct job is
       NOT Work-bound: `_enqueue_motif_job` stamps a SYNTHETIC uuid4() project_id
       (actions.py:552) with no composition_work behind it, so `GET /jobs/{id}`'s book
       gate 404s on it forever — the spend happens and the caller can never learn the
       outcome (`silent-success-is-a-bug`).

       A Work-less row has no book to gate on. Its scope key is its OWNER
       (`created_by`), so that is the gate. Missing row and foreign row return the SAME
       uniform 404 (H13 — no existence oracle)."""
       job = await jobs.get(job_id)
       if job is None or job.created_by != user_id:
           raise HTTPException(status_code=404, detail=NOT_ACCESSIBLE_MESSAGE)
       return job.model_dump(mode="json")
   ```
   (`NOT_ACCESSIBLE_MESSAGE` — import from `loreweave_mcp.errors`, same as `arc.py:32`. If `engine.py`
   already has a uniform-404 constant, reuse **that** one; one name for one concept.)

🔴 **THE GATE IS A CASCADE, NOT A FLAT OWNER CHECK** (`Q-34-JOB-NOT-POLLABLE` S6). Once `project_id` and
`book_id` are nullable, **gate on the LOADED ROW'S OWN SCOPE** (`gate-must-derive-scope-from-the-loaded-row`),
in this order — in **both** `get_job` (`engine.py:1415-1428`) and the MCP tool:
```
1. job.project_id is not None  → the EXISTING _gate_work(…, VIEW)      [conformance_run — UNCHANGED]
2. elif job.book_id is not None → authorize_book(grant, job.book_id, user_id, VIEW)   [book-scoped mine]
3. else                         → require job.created_by == user_id, else the uniform 404
                                                                        [corpus mine + arc_import]
```
The dedicated `GET /motif-jobs/{job_id}` route above stays a **pure owner read** (it exists so the FE has
one honest, Work-free reader); the cascade is what un-breaks the **generic** `/jobs/{id}` for the book-scoped
mine without weakening it for Work-bound jobs.

**S7 · EDIT `services/composition-service/app/mcp/server.py`** — un-break `composition_get_mine_job`
   (`:3207`) **the same way**, so the agent gets the identical fix (AT-11: *"the `composition_get_mine_job`
   arg change rides with BE-7c"*):
   ```python
   async def composition_get_mine_job(
       ctx: MCPContext,
       job_id: Annotated[str, "The motif job id returned by a confirmed Tier-W motif action."],
       project_id: Annotated[str | None, "DEPRECATED — ignored. A mine/import job is not "
                                         "Work-bound; the gate is the job's owner."] = None,
   ) -> dict:
       tc = _ctx(ctx)
       jobs = GenerationJobsRepo(get_pool())
       job = await jobs.get(UUID(job_id))
       # BE-7c / AT-11 — a Work-less job has NO book to gate on. The row's scope key is
       # its OWNER. Missing row and foreign row are the SAME uniform deny (no oracle).
       if job is None or job.created_by != tc.user_id:
           raise uniform_not_accessible()
       return job.model_dump(mode="json")
   ```
   ⚠ **`project_id` becomes OPTIONAL, not removed** — the BFF allowlist already advertises this tool and
   an in-flight agent may still pass it. Accept and ignore it. Update the tool's **description** to say
   the gate is ownership.
   ⚠ **THE 3-SCHEMA-SOURCE FASTMCP CAVEAT** (repo memory `knowledge-mcp-three-schema-sources-fastmcp-strips`):
   after changing an MCP tool's signature, **grep for every place its schema is declared** —
   `grep -rn "composition_get_mine_job" services/ contracts/` — and update **all** of them. FastMCP
   strips what it does not know about; a stale second schema source silently wins.

⚠ **`project_id` becomes OPTIONAL, not removed** (an in-flight agent may still pass it). **Keep the IDOR
guard: when `project_id` IS supplied, still assert `job.project_id == pid`.** Update the tool's
**description** and its `require_meta` scope to say the gate is **ownership**.
⚠ **THE 3-SCHEMA-SOURCE FASTMCP CAVEAT** (`knowledge-mcp-three-schema-sources-fastmcp-strips`): after
changing an MCP tool's signature, **grep every place its schema is declared** —
`grep -rn "composition_get_mine_job" services/ contracts/` — and update **all** of them, including the
**three `tool-liveness.json` copies** (`contracts/`, `chat-service/`, `agent-registry-service/`), which may
pin an arg set. FastMCP **strips** what it does not know about; a stale second schema source silently wins.

---

**S8 · FE — repoint the two dead pollers** (`Q-34-MINECONFIRM-DEAD`, `Q-34-AT11-NO-SPINNER-PAPER`).
In `frontend/src/features/composition/motif/api.ts`: add
`getMotifJob(jobId, token) => apiJson(`${BASE}/motif-jobs/${jobId}`, { token })`, extract a shared
**`_pollMotifJob(jobId, token)`** helper, and **RE-POINT `motifApi.mineConfirm` (`:172-176`) at it**
(it polls `compositionApi.getJob` today = the live 404). **W4-FE7's 拆文 confirm reuses `_pollMotifJob`** —
that is the leg AT-5 mirrors, **instead of the dead one**. 🔴 **Leave `arcConformanceRunConfirm`
(`:286-289`) on `compositionApi.getJob` — it works.**

---

**Tests · `services/composition-service/tests/unit/test_motif_job_read.py` (NEW)
+ `tests/integration/db/test_motif_job_lifecycle.py` (NEW — 🔴 real PG)**

🔴 **THE INTEGRATION TEST IS THE POINT. A MOCK IS WHAT HID THIS BUG** (`test_motif_mcp.py:1320` does
`jobs.create = AsyncMock(return_value=(job, True))` — it fakes the very insert that fails). The new
real-SQL file **MUST** carry `pytestmark = pytest.mark.xdist_group("pg")`.

| Test | File | Asserts |
|---|---|---|
| 🔒 `test_confirmed_mine_ACTUALLY_CREATES_A_JOB_ROW` | integration | **THE LOCK.** Confirm a `mine_motifs` ⇒ a `generation_job` row **EXISTS** with **`project_id IS NULL`** and `created_by = caller`. *At HEAD this reds — the row is never written.* |
| 🔒 `test_a_402_leaves_a_POLLABLE_failed_job_not_a_dangling_hold` | integration | S5's lock. A quota-exhausted confirm ⇒ a **`failed`** job row + a returned `job_id`, **not** a naked 402. |
| `test_owner_can_read_a_work_less_job` | unit | Synthetic `project_id`, `created_by == caller` ⇒ **200** via `/motif-jobs/{id}`, body carries `status` + `result`. **The exact case both existing readers fail.** |
| `test_foreign_job_is_uniform_404` | unit | `created_by != caller` ⇒ **404**, body **byte-identical** to… |
| `test_missing_job_is_the_same_uniform_404` | unit | …`jobs.get` → `None` ⇒ **404**, same body. **Assert the two bodies are EQUAL** — that equality *is* the no-oracle guarantee. |
| `test_analyze_reference_job_is_readable` / `test_mine_motifs_job_is_readable` | unit | Both ops ⇒ 200 (this un-breaks Wave 3's `MotifMinePanel` too). |
| 🔒 `test_conformance_run_still_polls_via_jobs_id` | unit | **THE NO-REGRESSION LOCK.** A `conformance_run` job with a **real** `project_id` still resolves through `GET /jobs/{id}`'s Work gate. We did not weaken it. |
| `test_get_mine_job_owner_gate` | unit | Replaces `test_get_mine_job_foreign_project_uniform` (`test_motif_mcp.py:1085`) with a **foreign-`created_by`** uniform-deny test. |
| FE (vitest) | `motif/__tests__/` | `mineConfirm` calls `/v1/composition/motif-jobs/{id}` and **NEVER** `/v1/composition/jobs/{id}`. |

**DoD evidence:** `"W4-BE3 (RE-SCOPED, size M): composition suite <N> passed; migrate.py relaxes generation_job.project_id/book_id (relax-only, NOT a back-fill) + the two-op CHECK + the owner index; create_unbound added; spend now runs AFTER durability (a 402 leaves a POLLABLE failed job); GET /motif-jobs/{id} owner-gated; integration test on real PG proves a confirmed mine_motifs ACTUALLY WRITES A ROW with project_id IS NULL (it never did before — live DB had ZERO such rows); GET /jobs/{id} still gates conformance_run on its real Work (regression lock); mineConfirm repointed"`

---

## 5 · MIGRATIONS

🔴 **AMENDED BY ADJUDICATION E.** The original plan said **"NONE"** and **banned** a migration outright.
That ban would have shipped the paid-action defect: the 拆文 job row **cannot be written at all** while
`generation_job.project_id` is `NOT NULL` and the insert derives it from `composition_work`.

**EXACTLY ONE migration is in scope, and ONLY when W4-BE3 fires** (i.e. **Wave 0 / `W0-BE1`** — and its
re-verify at Wave 3 / `3a-1` — somehow did **not** already land it). **In the planned sequence this is a
SKIP: W0-BE1 builds it. Pre-flight cmd 4 tells you which.**

🔴 **THE CANONICAL DDL IS `W0-BE1`'s (verbatim from Wave 3's `3a-1` §(a)). DO NOT FORK IT — copy it.**
An earlier cut of this section wrote a **second, DIFFERENT** version of the same migration
(`generation_job_project_scope_chk` + `idx_generation_job_owner`) against Wave 0's
(`generation_job_scope_shape` + `idx_generation_job_owner_unbound`). Applying **both** would leave the table
carrying **two constraints and two indexes for one invariant**, under two names — *one name for one concept*,
violated in the schema. **If W4-BE3 ever fires, open `…-wave-0-foundations.md` → `W0-BE1` step (a) and apply
THAT block, unmodified.** Its shape, restated here only so you can recognize it:

| Change | Why it is not the banned thing |
|---|---|
| `ALTER TABLE generation_job ALTER COLUMN project_id DROP NOT NULL;` + the same for `book_id` | **RELAX-ONLY. Non-destructive. Rewrites no user rows. Drops nothing.** It is **NOT a back-fill** — the ban that stands is *"do not invent a synthetic-but-real `project_id`"*, and this is its opposite: it lets the row be honestly Work-less. |
| the **`generation_job_scope_shape` both-or-neither CHECK** (W0-BE1's name and shape) | Constrains the **SHAPE** (`project_id` and `book_id` are both NULL or both set), **not an operation set** — so a new Work-less op **never needs another DDL block**. The op allowlist lives in the **writer** (`create_unbound()`), where it belongs. ⚠ A CHECK enumerating operations (`… OR operation IN ('mine_motifs','analyze_reference')`) would force a **CHECK-backfill on every future op** — the `migration-check-constraint-must-backfill-all-historical-blocks` trap. **Do not write that version.** |
| the partial index **`idx_generation_job_owner_unbound`** (W0-BE1's name) | The owner axis the new owner-gated read uses for Work-less rows. |

**Everything else: still ZERO.** No new tables, no new enum values, no columns on `arc_template` /
`import_source` / `structure_node` / `outline_node`.

If a slice discovers it wants **any other** schema change: **write a defer row and CONTINUE** (gate #2 —
large/structural). Do not stop, do not ask. In particular:
- **Do NOT** add a `book_id` / `book_shared` column to `arc_template` (OQ-6 — §10).
- **Do NOT** back-fill `generation_job.project_id` with a fabricated value. The row is Work-less **by
  design**; the fix is the **nullability + the gate**, not the data.

*The migration hazards that apply to the block above:* `ADD COLUMN IF NOT EXISTS` **never revisits a bad
default** on an already-migrated DB (irrelevant here — `DROP NOT NULL` **does** always re-apply, which is
why this block is safely idempotent); a new **enum value** must back-fill **every** historical CHECK block;
a **partial UNIQUE** index must exempt soft-delete tombstones and its `ON CONFLICT` must **repeat the
partial index's predicate**.

---

## 5b · W4-BE4 — 🔴 AT-6's PROVENANCE STAMP, **SERVER-SIDE** (adjudication D)

**Kind:** BE · **dependsOn:** — · **Size:** **XS** (~25 lines of Python + 4 tests, in a route we own)

> **This replaces AT-6's "Zero backend" and the original W4-FE4's `createArc` + `assignChapters` shape.**
> `Q-34-OQ1-STAMP-SITE` adjudicated **answer (b) — stamp server-side — overturning the spec's (a)**, and
> `Q-34-OQ2-DOUBLE-MATERIALIZE` + `Q-34-AT6-SILENT-NOOP` proved the FE create+assign shape is an **orphan
> bug**, not merely a costlier option.

**THE DECISIVE CODE FACT.** `materialize` **already writes the OTHER half of the drift subject** — the
`motif_application` ledger keyed by `annotations->>'arc_template_id'`, which is exactly what
`?scope=arc_template_drift` reads (`conformance.py:389-403` → `compute_arc_report(by_structure=False)` →
the annotation-keyed bindings, `conformance.py:122-143`). Putting the **provenance** half in the FE splits
**ONE subject across two writers and two transports**: every non-Studio caller — the legacy
`motif/arcApi.ts:65`, the MCP/agent path, a retry after the 2nd call drops — writes the ledger with **no**
`structure_node.arc_template_id` ⇒ **drift 422 `NO_TEMPLATE_PROVENANCE` forever**. That is precisely the
`silent-success-is-a-bug` class AT-6 exists to kill.

**No new authz surface:** `materialize` already gates **EDIT** on the book (`plan.py:136-144`).

**Files**

1. **CREATE the ONE writer** — `services/composition-service/app/engine/arc_apply.py`:
   ```python
   async def stamp_arc_provenance(
       pool, *, arc_node_id: UUID, arc_template: ArcTemplate, structure_repo: StructureRepo,
   ) -> dict[str, Any]:
       """AT-6 — the ONLY writer of structure_node.arc_template_id. Idempotent.

       `commit_decomposed_tree` ALREADY created this arc (outline.py:435-438) and ALREADY
       linked every chapter to it (outline.py:444). The ONLY thing missing is the stamp.
       Creating a node here, or re-assigning chapters here, would mint a SECOND arc and
       orphan the first (FD-17). Do neither."""
       updated = await structure_repo.update(
           arc_node_id,
           {"arc_template_id": arc_template.id, "template_version": arc_template.version},
           expected_version=None,          # no OCC: the arc was minted by this same flow
       )
       return {"structure_node_id": str(updated.id),
               "arc_template_id": str(updated.arc_template_id),
               "template_version": updated.template_version}
   ```
   Both columns are already in `_UPDATE_COLUMNS` / `_NULLABLE_UPDATE_COLUMNS` (`structure.py:54,59`) and in
   `_SELECT_COLS` (`:42`). `ArcTemplate.version` is `models.py:587`.
   🔴 **It lives in `arc_apply.py` on purpose: `apply_arc_to_spec` (W4-BE8b) calls the SAME function.**
   **Exactly one writer of `structure_node.arc_template_id`, forever.**

2. **EDIT `services/composition-service/app/routers/plan.py`** (`materialize_arc`, `:1260-1400`) — **AFTER**
   `created = await outline.commit_decomposed_tree(...)` and **before** the `return`, call
   `stamp_arc_provenance(pool, arc_node_id=created["arc_id"], arc_template=arc, structure_repo=structures)`.
   The stamp is a **purely ADDITIVE ~5-line block appended in the handler** — it touches **zero** decompose
   code (that is why OQ-1's "blast radius" objection does not hold: the 130-line shared commit path is
   `commit_decomposed_tree`, and we run *after* it returns).
   🔴 **RUN THE STAMP ON THE IDEMPOTENCY-REPLAY PATH TOO** (`created["replay"] is True`). It is an
   idempotent update, and it is **the only way a replay heals a materialize whose stamp previously failed**.
   Suppressing on replay would leave such an arc **permanently unstamped** and drift with **no subject
   forever**. (That closes OQ-2's "UNVERIFIED" half: **replay suppresses the LEDGER, not the STAMP.**)
   `_replay` returns the stored result *before* the replace sweep (`outline.py:606-614, 629-631`), so
   `arc_id` is the **original, still-active** arc. The stamp target is valid and stable.
   🔴 **Do NOT "match on `(book_id, arc_template_id)` and PATCH the existing node"** (the spec's OQ-2
   proposal). It is **a bug**: the `replace` path **soft-archives** the prior arc (`outline.py:691-702`)
   and mints a fresh one, so that rule would PATCH the **ARCHIVED** arc and leave the **live** one
   unstamped ⇒ `NO_TEMPLATE_PROVENANCE` forever after any re-materialize. **Always stamp the `arc_id` that
   came back.**

3. **EXTEND the materialize response** (`plan.py`'s final `return {...}`) with
   **`"structure_node_id": str(...)`** and **`"chapters_assigned": len(created["chapter_ids"])`**
   (additive — existing consumers are unaffected). These two fields are what the FE **asserts the effect**
   against.

**Tests — `services/composition-service/tests/unit/test_arc_materialize_route.py` (EXTEND) +
`tests/integration/db/test_arc_materialize_stamp.py` (NEW — 🔴 `pytestmark = pytest.mark.xdist_group("pg")`)**

⚠ The existing unit file **STUBS `commit_decomposed_tree`** (`:71-73`), so it **cannot see** the
archive/replay semantics. The replay + replace cases **need the real-DB integration test** to be honest.

| Test | Asserts |
|---|---|
| `materialize stamps the arc it just created` | A `structure_node` exists with `arc_template_id` **and** `template_version == arc.version`; the response carries `structure_node_id` + `chapters_assigned == len(chapter_ids)`. |
| 🔒 `materialize TWICE with the same template yields ONE live stamped arc` | Not two. |
| 🔒 `replay (same idempotency_key) STILL STAMPS` | Re-POST with the same `K` ⇒ `replay: true`, the **same** `arc_id`, and the arc **is still stamped**. **A suppress-on-replay implementation FAILS this.** |
| 🔒 `replace=true: the NEW arc carries the stamp and the OLD one is archived` | `is_archived=true` on the old; the stamp is on the **live** one. **A "match on (book_id, arc_template_id)" implementation FAILS this.** |
| 🔒 `end-to-end: drift has a subject` | `GET /works/{pid}/conformance?scope=arc_template_drift&arc_id=<that structure_node_id>` returns **a report, not a 422**. |
| `a hand-authored arc (no template) still 422s NO_TEMPLATE_PROVENANCE` | The negative control — we did not stamp everything. |

**DoD evidence:** `"W4-BE4: composition suite <N> passed; stamp_arc_provenance is the SINGLE writer of structure_node.arc_template_id (arc_apply.py); materialize returns structure_node_id + chapters_assigned; the replay-still-stamps and replace-stamps-the-LIVE-arc integration tests are green on real PG; drift now resolves a report instead of 422 NO_TEMPLATE_PROVENANCE; NO createArc and NO assignChapters were added to the FE"`

**PO veto point (stated so it can be overruled in one word):** the only thing this costs that a FE stamp
doesn't is ~25 lines of Python + 4 tests in a route we already own. **If the PO insists on BE-NONE for M1**,
the fallback is the FE **single-PATCH** shape (`PATCH /v1/composition/arcs/{res.arc_id}` with
`{arc_template_id, template_version}`, **no `If-Match`**, assert the echoed row, error-never-checkmark) —
**still NOT `createArc` + `assignChapters`**, which is a bug on every path. On that fallback the debt row
**`D-AT6-FE-PROVENANCE-STAMP-DUPLICATE-WRITER`** becomes **mandatory**, and the legacy/agent materialize
callers stay unstamped in the meantime.

---

## 5c · W4-BE5 — 🔴 AT-8: THE PLATFORM MODEL MAY NEVER SILENTLY PAY

**Kind:** BE · **dependsOn:** — · **Size:** XS · **Source:** `Q-34-AT8-NO-SILENT-PAYER`

The FE gate (`disabled={!model}`, W4-FE7) is **one of three legs**. Without the other two, an agent — or
any non-GUI caller — can submit a deconstruct with **no `model_ref`**, and the worker will happily bill the
**platform default** (`settings.motif_deconstruct_model_ref`). That is the *silent hidden default* SET-2
bans, on a **paid** path.

1. **KILL THE FALLBACK.** `services/composition-service/app/engine/motif_deconstruct.py:662-663` become
   `model_source = str(input.get("model_source") or "")` and `model_ref = str(input.get("model_ref") or "")`
   — **drop both `settings.motif_deconstruct_*` reads**. The existing fail-closed `ValueError` (`:523-527`)
   then fires unconditionally; update its message to
   *"no deconstruct model_ref on the job (AT-8: the platform default may never pay for a Deconstruct)"*.
   Leave `config.py:200-201` in place (`motif_mine.py:521-522` still reads them — out of scope) but **add a
   comment marking them NOT-a-fallback-for-deconstruct**.
2. **REJECT BEFORE SPEND.** In `app/routers/actions.py` `_execute_arc_import` (~`:669-712`), **after** the
   ownership re-check and **BEFORE** claiming the token / the spend precheck / the enqueue:
   `if not payload.get("model_ref"): raise HTTPException(400, detail={"code": "model_ref_required"})`.
   This makes "no model_ref" **impossible to submit** for **both** the GUI and any agent caller, and it
   fails **before any token is claimed or any job enqueued** — no charge-for-nothing.
3. **Do NOT tighten `_ArcImportArgs.model_ref` (`server.py:3049`) to a required `str`.** **No MCP tool
   anywhere exposes the user's `user_models` list** (grepped every `services/*/app/mcp/*.py`), so a required
   arg would make the tool **uncallable by an agent that cannot discover a ref**. The confirm-effect gate
   (2) achieves the same "impossible to submit" with a **legible 400** instead of a schema error. *(PO may
   veto and make the arg required once agent model-discovery lands.)*

**Tests**

| Test | Asserts |
|---|---|
| 🔒 `test_deconstruct_never_picks_up_the_platform_ref` (`tests/unit/test_motif_deconstruct.py`) | **THE HOLE'S REGRESSION TEST.** `monkeypatch settings.motif_deconstruct_model_ref = "SOME-PLATFORM-REF"`, call `run_analyze_reference` with input **lacking** `model_ref` ⇒ `pytest.raises(ValueError)` **AND the LLM client was NEVER called**. |
| 🔒 `test_arc_import_confirm_without_model_ref_is_400_and_enqueues_NOTHING` (router test) | 400 `model_ref_required`; assert **no job row** was enqueued **and no token was claimed**. |

**DoD evidence:** `"W4-BE5: composition suite <N> passed; the platform deconstruct model is unreachable from the job path (monkeypatched platform ref + no model_ref ⇒ ValueError, LLM client never called); a confirm without model_ref is a 400 BEFORE the token is claimed (no charge-for-nothing)"`

*For the record, so a future agent does not have to re-derive it — the migration hazards that would apply
IF one were ever added here:* `ADD COLUMN IF NOT EXISTS` **never revisits a bad default** on an
already-migrated DB; a new enum value must back-fill **every** historical CHECK block; a partial UNIQUE
index must exempt soft-delete tombstones and its `ON CONFLICT` must **repeat the partial index's
predicate**.

---

## 6 · THE FRONTEND SLICES

### W4-FE1 — the `arc-templates` panel + GG-8 registration + the 3-tier browse

**Kind:** FS (it touches chat-service's tool schema) · **dependsOn:** — · **Size:** M

This is the GG-8 slice. **A new panel is not done until all of §6.1 is done.**

#### 6.1 The registration checklist (plan 30 §8, in order)

| # | File | Exact change |
|---|---|---|
| **1** | **CREATE** `frontend/src/features/studio/panels/ArcTemplatesPanel.tsx` | The panel. Root **`data-testid="studio-arc-templates-panel"`**. `useStudioPanel('arc-templates', props.api)`. Work resolution via **`useQualityWork(host.bookId, accessToken)`** — **reuse it, do not re-derive** (§3.5). **The library must still BROWSE with no Work** (an arc template is a *user*-tier resource); only **Apply / Extract / Drift** need `work.kind === 'ready'`. Render `work.kind === 'unavailable'` as *"could not reach the co-writer service"* — **never** as "no work yet" (`unconsulted is not empty`). ≤ ~100 lines: it composes, it does not implement. |
| **2** | **EDIT** `frontend/src/features/studio/panels/catalog.ts` | Import `ArcTemplatesPanel`. Add **one** `STUDIO_PANELS` row, in the `storyBible` cluster: `{ id: 'arc-templates', component: ArcTemplatesPanel, titleKey: 'panels.arc-templates.title', descKey: 'panels.arc-templates.desc', category: 'storyBible', guideBodyKey: 'panels.arc-templates.guideBody' }`. **`category` is MANDATORY** (`panelCatalogContract.test.ts` reds without it). **`storyBible` IS already a `CATEGORY_ORDER` member** — X-2 does not block this panel. **`guideBodyKey` is MANDATORY** (X-3). |
| **3** | **EDIT** `frontend/src/i18n/locales/en/studio.json` | `panels.arc-templates.title` = `"Arc Templates"` · `.desc` = `"Browse, adopt and apply multi-chapter arc structures — and deconstruct a reference story into one (拆文)."` · `.guideBody` = a paragraph covering: the three tiers (Mine / System / Catalog), that a **System row is read-only — adopt it to edit**, apply-preview → materialize, save-an-arc-as-a-template, Import & Deconstruct, and — per **OQ-6** — an explicit sentence that **there is no book-shared tier: collaborators share arc structure by publishing + adopting** (so its absence does not read as an omission). |
| **4** | **EDIT** `frontend/src/i18n/locales/{ar,bn,de,es,fr,hi,id,ja,ko,ms,pt-BR,ru,th,tr,vi,zh-CN,zh-TW}/studio.json` | The same 3 keys × 17 locales — **`python scripts/i18n_translate.py`**. **Never hand-write.** |
| **5** | **EDIT** `services/chat-service/app/services/frontend_tools.py` | **Two edits** in `UI_OPEN_STUDIO_PANEL_TOOL`: **(a)** append `"arc-templates"` to the `panel_id` **enum** (line ~402). **(b)** append a clause to the tool **description** prose (lines ~403-481) — *that gloss is the model's only hint the panel exists*. Use exactly: `"'arc-templates' = the arc-template library — browse/adopt multi-chapter arc structures, apply one onto this book, save one of your arcs as a template, or import a reference story and deconstruct it (拆文) into a reusable arc; "` |
| **6** | **REGENERATE** `contracts/frontend-tools.contract.json` | **NEVER hand-edit.** `cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py`. **Commit the regenerated JSON in the SAME commit as steps 2 + 5.** |
| **7** | ~~**EDIT** `frontend/src/features/studio/host/studioLinks.ts`~~ | 🔴 **DELETED — ADJUDICATED NOT NEEDED (adjudication F, `Q-34-STUDIOLINKS-COND`). DO NOT BUILD A `studioLinks` RESOLVER.** The premise was false: `resolveStudioLink` matches on `path = link.split(/[?#]/,1)[0]` (`studioLinks.ts:76`) — it is a **PATH** resolver and **DISCARDS the query string**; there is **no `?panel=` mechanism anywhere** (`WritingStudioPage.tsx:16-17` reads only `?chapter=`); and there is **no `/arc-templates` app route** to resolve. Building one means **inventing a new cross-cutting `?panel=` URL contract for all 57 panels** — out of scope, and **nothing needs it**: AT-1 makes Import & Deconstruct a **SECTION INSIDE** this panel and §4 keeps **all three views MOUNTED**, so at job-completion **the panel is already open and the user is already in it**. **BUILD THIS INSTEAD (step 7′).** |
| **7′** | **`ArcTemplatesPanel.tsx`** — the **params seam** (replaces step 7) | Accept an **OPTIONAL** `params.templateId`, mirroring **`AgentModePanel.tsx:31-48` line-for-line** (the repo's params-retargeting precedent): <br>`const str = (v: unknown) => (typeof v === 'string' && v ? v : null);`<br>`const initialId = str((props.params as {templateId?: unknown})?.templateId);`<br>`const [selectedTemplateId, setSelectedTemplateId] = useState<string|null>(initialId);`<br>`const openDetail = (id: string) => { setSelectedTemplateId(id); setView('detail'); };`<br>`useEffect(() => { const d = props.api.onDidParametersChange?.((next) => { const id = str(next?.templateId); if (id) openDetail(id); }); return () => d?.dispose?.(); }, [props.api]);`<br>🔴 **Params stay OPTIONAL** — a bare `openPanel('arc-templates')` lands on the Library list. That **preserves AT-1's bare-id openability** and keeps the panel **out of the X-12 trap** (a params-REQUIRING panel is structurally outside `ui_open_studio_panel`'s enum). The host seam already carries it: `StudioHostProvider.tsx:52,77-92` passes `params` to `addPanel` on open and `updateParameters` when already open — **no host change needed**. <br>🔴 **`openDetail` is the ONE hand-off callback.** All three consumers use it: the deconstruct's terminal handler, each Suggest candidate's click, and the Extract success. **One concept, one home. No URL.** |
| **8** | **EDIT** `frontend/src/features/studio/agent/handlers/arcEffects.ts` | 🔴 **NOT NEW.** The conditional is **decided by a command, not a vibe**: `test -f frontend/src/features/studio/agent/handlers/arcEffects.ts`. <br>**EXISTS (expected — Wave 2 landed it)** ⇒ **EXTEND ITS HANDLER BODY**: add `qc.invalidateQueries({ queryKey: ['composition','arc-templates'] })` alongside its existing `['plan-hub']` + `['composition','arcs', bookId]`. The **2-segment prefix is correct and sufficient** — TanStack invalidation is prefix-matched and the live consumer key is `['composition','arc-templates','all']` (`useArcLibrary.ts:10`). <br>🔴 **Do NOT add a second `registerEffectHandler`** for an overlapping `composition_arc_*` pattern — `matchEffectHandlers` (`effectRegistry.ts:45`) **`filter`s and returns EVERY match** and `runEffectHandlers` (`:49-53`) **awaits ALL** of them, so a second registration **double-fires** on every arc write (plan 30 §8.0b **SEALS** this: *"Wave 2 creates the file; Wave 4 extends its handler body — it does not register a second pattern."*). The broad `/^composition_arc_/` **already covers** the two tool names this wave newly reaches (`composition_arc_apply`, `composition_arc_extract_template` — both confirmed present in `mcp/server.py`). <br>**MISSING (only if Wave 2 / the X-4 sweep was skipped)** ⇒ CREATE it exactly per spec 32 §6 step 8 — **ONE file, ONE `registerEffectHandler(/^composition_arc_/, arcEffect)`**, `unwrapToolResult` from `./resultEnvelope`, the idempotent `let registered = false` guard + a `_resetArcEffectHandlers()` test hook, mirroring `knowledgeEffects.ts:46-58` **verbatim**. Wire it in `useStudioEffectReconciler.ts` (import next to `:18-21`; call inside the once-only `useEffect` at `:33-38` — **there is no barrel file; that `useEffect` IS the registration site**). **Use a RegExp, never a string** — `registerEffectHandler`'s string branch is `===`-or-`startsWith`, so an alternation written as a string matches **nothing** and ships a **silent no-op handler no unit test can catch**. |
| **8b** | 🔴 **X-4 — DELETE THE FALSE COMMENT** | `grep -n "authoring_run has no MCP tools" frontend/src/features/studio/agent/useStudioEffectReconciler.ts` → **if it hits, delete that clause** (`:7-10`'s *"and the two tool families it confirmed DON'T need a handler … authoring_run has no MCP tools at all, REST-only, no Studio consumer to go stale"*). **It is REFUTED by the code:** `composition_authoring_run_list/get/create/gate/start/resume/pause/accept_unit/reject_unit/close/revert_all` are **all registered MCP tools** (`mcp/server.py:1526,1560,1616,1677,1723,1771,1817,…`). If the grep does not hit, Wave 0/1 already removed it — **no-op, do not re-add it.** |
| **8c** | 📌 **NOTE FOR THE WAVE-2 BUILDER** (not a Wave-4 change — flagged so it is not forgotten) | `/^composition_arc_/` also matches the pure **reads** `composition_arc_list/_get/_suggest/_import_analyze/_template_drift`, so a chatty agent read-loop will **thrash the cache**. Mirror `KNOWLEDGE_WRITE_PATTERN`'s negative lookahead (`knowledgeEffects.ts:16-17`): `/^composition_arc_(?!list|get|suggest|import_analyze|template_drift)/`. **Still ONE registration in ONE file** — it does not violate the §8.0b seal. |
| **9** | `frontend/src/features/studio/onboarding/tours.ts` | **SKIP** — not a role-tour step in v1. |
| **10** | 🔴 **CREATE** `frontend/src/features/studio/panels/__tests__/legacyRetirementGuard.test.ts` | **THE GG-4 MECHANICAL GUARD** (`Q-34-GG4-CHAPTEREDITORPAGE` item 3; plan 30 §437-438 demands *"a route assertion / hygiene test, not the current 18-line prose banner"*). ~10 lines: <br>`const studioDoor = STUDIO_PANELS.some(p => p.id === 'arc-templates');`<br>`const app = readFileSync('src/App.tsx','utf8');`<br>`const mlv = readFileSync('src/features/composition/motif/components/MotifLibraryView.tsx','utf8');`<br>`const legacyDoor = app.includes('chapters/:chapterId/edit') && app.includes('ChapterEditorPage') && mlv.includes('ArcTemplateLibraryView');`<br>`expect(studioDoor \|\| legacyDoor).toBe(true);`<br>(Import `STUDIO_PANELS` from `../catalog`.) **Removing the LAST door reds this test.** Once it is green, the legacy door is no longer load-bearing and **Wave 6 / 00C Q-6 may remove it — the guard, not a prose note, is what PERMITS that.** Add the same shape for `motif-library`. |
| **11** | 🔴 **CREATE** `frontend/src/features/composition/motif/__tests__/sharedComponentsSingleHome.test.ts` | **THE DOCK-2 ANTI-FORK GUARD** (`Q-34-SHARED-LIFT-LOCATION`). Walk `frontend/src` and assert that for **each** of `MotifStateBoundary.tsx`, `CostConfirmCard.tsx`, `AdoptTargetModal.tsx`, `ModelRolePicker.tsx` there is **EXACTLY ONE** matching file path, and that it **equals the canonical path** (pre-flight cmd 7). A Wave-4 builder who copy-pastes a component to *"un-couple arc from motif"* **reds this immediately**. ~15 lines. *(If Wave 3 already created it — extend, do not fork the guard either.)* |

#### 6.2 The panel's own content, this slice

Root layout per the HTML draft's state ①:

```
┌ ARC TEMPLATES ─────────────────────────────────────── ⟳  ⧉  ✕ ┐
│ [ Library │ Catalog │ Import & Deconstruct ]      ⌕ search…    │  toolbar row1
│ tier chips: ⦿ Mine  ○ System  ○ All   genre: [ xianxia ▾ ]     │  row2 (Library only)
├───────────────────────────────────────────────────────────────┤
│ ▸ 逆天改命 · 18 chapters · xianxia, 爽文        [Mine]    ⋯    │
│ ▸ Hero's Journey · 12 chapters · —             [System]  ⋯    │
│ ▸ 山海遺聞 (deconstructed)  · 24 ch · ⚠ imported [Mine] ⋯    │
├───────────────────────────────────────────────────────────────┤
│ 14 templates · 3 mine · 6 system            + New   ⤓ Extract │  panel-foot
└───────────────────────────────────────────────────────────────┘
```

🔴 **ALL THREE top-level views (Library / Catalog / Import) STAY MOUNTED** — CSS `hidden`, **never** a
ternary unmount. Copy **`AgentModePanel.tsx:76-84`** verbatim in shape:
```tsx
<div data-testid="arc-templates-view-library" className={cn('min-h-0 flex-1 overflow-auto', view !== 'library' && 'hidden')}>…</div>
<div data-testid="arc-templates-view-catalog" className={cn('min-h-0 flex-1 overflow-auto', view !== 'catalog' && 'hidden')}>…</div>
<div data-testid="arc-templates-view-import"  className={cn('min-h-0 flex-1 overflow-auto', view !== 'import'  && 'hidden')}>…</div>
```
No `{cond ? <A/> : <B/>}` and no `if (x) return …` at **any** of the view boundaries.

🔴 **KILL THE EXISTING TERNARY** (`Q-34-MOUNTED-NOT-TERNARY` item 2). `ArcTemplateLibraryView.tsx:21` is
`if (openArc) { return (…) }` — **an early-return UNMOUNT of the list**, and `:18` holds the local
`openArc` state. **DELETE both.** Lift selection to the panel root: a row's `onClick` calls `onOpen(arc)`
⇒ the root sets `selectedTemplateId` + `setView('detail')`. The detail body renders inside an
always-mounted div, returning null-content when nothing is selected.

🔴 **CSS `hidden` ALONE IS NOT ENOUGH — HOIST THE POLL** (`Q-34-MOUNTED-NOT-TERNARY` item 3). The
mine/deconstruct poll as it exists today is an **`await` loop inside a react-query `mutationFn`**
(`useMotifMine.ts:32-39` → `motif/api.ts:163-180`) — it **dies with its owner**. `hidden` only saves it
while nothing remounts the subtree. **The deconstruct poll MUST live at the PANEL ROOT as a `useQuery`**,
not an await loop:
```ts
// frontend/src/features/composition/arc-templates/hooks/useDeconstructJob.ts — called from the PANEL ROOT
queryKey: ['composition','motif-job', jobId], enabled: !!jobId,
refetchInterval: (q) => (['pending','running'].includes(q.state.data?.status) ? 3000 : false)
```
Mirror **`frontend/src/features/composition/authoringRuns/hooks.ts:41`** exactly. `jobId` lives in
panel-root state; the Import view receives `{status, result, error}` as **props**.
*(Default, PO-vetoable: `jobId` does not survive a full page reload — spec 34's DoD asserts survival across
a **TAB SWITCH**, which this delivers. Reload-survival would need the job id persisted in the panel's dock
params; that is a separate slice.)*

---

#### 🔴 WHERE THE FILES LIVE — ADJUDICATED (`Q-34-SHARED-LIFT-LOCATION`)

**NO LIFT. NO MOVE. NO NEW SHARED DIRECTORY.** *"LIFT AS-IS"* in spec 34 §2 means **mount into the panel**,
**not relocate the file**. The port surface is *"all under `frontend/src/features/composition/motif/`"* —
that is where it stays.

| Kind | Rule |
|---|---|
| **The 4 shared components** (`MotifStateBoundary`, `CostConfirmCard`, `AdoptTargetModal`, `ModelRolePicker`) | **Import IN PLACE from the canonical paths** (pre-flight cmd 7). **Never copy. Never move. Never re-export.** DOCK-2 forbids **forking**, not co-location. Guard: `sharedComponentsSingleHome.test.ts` (step 11). |
| **The existing arc components** (`ArcTemplateLibraryView`, `ArcTimelineEditor`/`Grid`/`MobileList`, `useArcTimeline`, `useArcApplyPreview`, `ArcApplyPreview`, `useArcMaterialize`, `ArcMaterializeAction`, `arcApi`, `arcTypes`, `useArcLibrary`, `applyArcEdit`, `arcTimelineContract`) | **EDITED IN PLACE under `composition/motif/` and MOUNTED by the new panel.** 🔴 **Do NOT rewrite them into a new tree** — they carry **4 existing test files**, and a rewrite is a fork by another name. |
| **Genuinely NEW files** (the panel shell, the catalog hooks, the drift hooks/components, the deconstruct section, the provenance-assert hook) | May live under **`frontend/src/features/composition/arc-templates/`**. Do **not** create `features/composition/shared/` and do **not** put composition-domain components in `frontend/src/components/shared/` (that dir is app-generic primitives — wrong altitude). |
| The `motif/` directory name | If an arc panel importing from a dir named `motif/` bothers you: **it is a naming smell, not a defect.** Renaming an 86-file tree mid-wave is exactly the churn DOCK-2 exists to prevent. |

**Files this slice creates**

| File | Contents |
|---|---|
| `arc-templates/hooks/useArcTemplatesPanel.ts` | View state: `view: 'library'\|'catalog'\|'detail'\|'import'`, `selectedTemplateId`, `openDetail(id)`, `scope: 'mine'\|'system'\|'catalog'`, `genre`, `q`. ≤ ~200 lines. **No JSX.** |
| `arc-templates/hooks/useDeconstructJob.ts` | The **hoisted** BE-7c poll (above). |
| `arc-templates/components/ArcTemplatesToolbar.tsx` | The two toolbar rows. Render-only. **Includes the persistent Import CTA (below).** |
| `arc-templates/components/ArcTemplateRow.tsx` | One row: name · `chapter_span` · `genre_tags` · **tier chip** (`owner_user_id === null` ⇒ *System*; `=== me` ⇒ *Mine*; else *Public*) · **an ⚠ imported chip when `source === 'imported' \|\| imported_derived`** — the SAME predicate the AT-9 publish gate uses (so an adopted-from-imported clone is chipped too), tooltip *"Derived from an imported story — publishing strips its source reference."* `data-testid={`arc-tpl-row-${id}`}`. |
| `arc-templates/components/ArcTemplateEmptyState.tsx` | 🔴 **THE FIXED CTA** — see the correction below. |

#### 🔴 THE DEAD-CTA FIX — AT-1's SCOPE CORRECTION (`Q-34-DEAD-CTA-ROOT-BUG`)

`ArcTemplateLibraryView.tsx:49` is a **TERNARY**, and the empty-state branch is the **only** place AT-1
puts the CTA. **After the user's first adopt the library is non-empty, the empty branch never renders, and
import becomes UNREACHABLE AGAIN.** 🔴 **Fixing only the empty state RE-FORKS the exact defect this wave
exists to kill.**

**Put the entry point in BOTH branches:**
- a **persistent header button** in the toolbar, rendered **regardless of list length**:
  `<button data-testid="arc-import-cta" onClick={() => setView('import')}>` labelled
  `t('motif.arc.importCta', { defaultValue: 'Import a story to deconstruct' })`;
- **AND** the empty state (`data-testid="arc-library-empty"`), reworded to end at *"Adopt one from the
  catalog, or —"* followed by **two real buttons**: *Browse the catalog* (→ `setView('catalog')`) and
  *Import a story to deconstruct* (→ `setView('import')`). **The string must never again promise an action
  no control performs.** Retire/split the `motif.arc.libraryEmpty` key — its current `defaultValue` **is**
  the bug. (Draft state ⑦'s "After" panel, lines 1322-1336, is the exact target.)

**EDIT `frontend/src/features/composition/motif/hooks/useArcLibrary.ts`** — 🔴 **the three tiers are
`mine` | `system` | `catalog`, NOT `all`** (`Q-34-OQ6-BOOK-SHARED-TIER` item 2; `Q-34-TWO-LIST-SHAPES`).
Restructure it to mirror `useMotifLibrary.ts:63-101`:
- `'mine'` → `arcApi.list({scope:'mine', limit:100})`, `select: d => d.arc_templates`
- `'system'` → `arcApi.list({scope:'system', limit:100})`, `select: d => d.arc_templates`
- `'catalog'` → `arcApi.catalog({q, limit:100})`, `select: d => d.items.map(catalogToArc)` ← **W4-FE2**
Distinct query keys per tab: `['composition','arc-templates', scope, q]`.
⚠ **Keep the `['composition','arc-templates']` PREFIX** — that is exactly what step 8's effect handler
invalidates.
⚠ **`scope=public` does NOT exist** — the route's pattern is `^(mine|system|all)$` (it 422s), **and** it
would bypass the B-3 allow-list. The catalog is its **own route**. (`motif/api.ts:80-81` already carries
this exact warning for motifs.)

**AT-7 — DROP `ArcConformancePanel` — 🔴 A RENDER-SITE REMOVAL, NOT A FILE DELETE** (`Q-34-AT7-DROP-CONFORMANCE`).

1. **EDIT `motif/components/ArcTemplateLibraryView.tsx`:** delete the import (`:10`) and the render block
   (`:36-40`). At HEAD **no other child of this view uses `modelRef`**, so **also drop `modelRef` from its
   Props and from its call site** (`grep '<ArcTemplateLibraryView'` first to confirm).
2. 🔴 **DO NOT DELETE THESE FILES** — they are spec 33's `quality-conformance` assets:
   `ArcConformancePanel.tsx`, `hooks/useArcConformance.ts`, `hooks/useArcConformanceRun.ts`,
   `motifApi.arcConformance` (`api.ts:212-221`), `motifApi.arcConformanceRunPropose` (`:245-260`),
   `__tests__/ArcConformancePanel.test.tsx`. **Spec 33's M-BUG-4 owns the fix, and its DoD carries a
   regression test that REDS ON THE OLD CODE. Deleting these files deletes that test.**
   **This wave must NOT touch those two `api.ts` functions — leaving them broken is CORRECT.**
3. The arc-templates **drift** view (W4-FE5) is a **NEW component**, not a rename of `ArcConformancePanel`.
   🔴 **CRITICAL TRAP:** its `arc_id` is a **`structure_node.id`**, **NOT `openArc.id`** (an
   `arc_template.id`) — **passing `openArc.id` recreates the exact bug being dropped.**

*"Did the prose realize my plan"* is a `structure_node` question and belongs to `quality-conformance`.
*"How far has my arc drifted from its template"* is this panel's, and it is **W4-FE5**.

📌 **BONUS FIX-NOW (same bug class, already 404ing in production) — `Q-34-AT5-NO-BESPOKE-ROUTES`.**
`motif/api.ts:223-235`'s `conformanceRunEstimate` POSTs `${BASE}/actions/conformance_run/estimate` and
`conformanceRunConfirm` POSTs `${BASE}/actions/conformance_run/confirm` — **neither route exists** in
`routers/actions.py` (only the generic `/preview` + `/confirm`). They are **LIVE-CALLED** from
`motif/hooks/useConformanceTrace.ts:32,36` ⇒ **the user pays nothing but gets a 404 spinner.** These belong
to **spec 33 / G-CONFORMANCE-TRACE**. **If Wave 3 has already fixed them at Wave-4 start, do nothing.
If it has NOT, this is a FIX-NOW, not a defer row** (rewrite both onto the generic spine:
`mcpExecute('composition_conformance_run', {args:{…}})` → `POST /actions/confirm?token=`; and fix the
arc-scope drift at `:255`, which sends `arc_template_id` where `_ConformanceRunArgs` (ForbidExtra) declares
`arc_id`). **Note it in VERIFY and flag it to spec 33's owner. Never mint a Wave-4 row for it.**

#### 6.3 Tests

| File | Test name | Asserts |
|---|---|---|
| `frontend/src/features/studio/panels/__tests__/ArcTemplatesPanel.test.tsx` (**NEW**) | `renders the panel root testid` | `studio-arc-templates-panel` is in the DOM. |
| | `browses with NO work (a template is user-tier)` | `useQualityWork` → `{kind:'no-work'}` ⇒ the **library still lists templates**; only Apply/Extract/Drift are gated. |
| | `an unavailable work service is NOT rendered as "no work yet"` | `{kind:'unavailable'}` ⇒ the *"could not reach the co-writer service"* copy, **not** the "start composing" nudge. |
| | `the empty state renders TWO WIRED buttons, not a sentence` | Zero templates ⇒ a *Browse the catalog* button **and** an *Import a story to deconstruct* button; clicking each switches the view. 🔒 **The dangling-CTA regression lock.** |
| | 🔒 `the import CTA is ALSO present when the library is NON-EMPTY` | **THE TEST THAT WOULD HAVE CAUGHT THE ORIGINAL BUG.** Render with 3 templates ⇒ `getByTestId('arc-import-cta')` still exists. A fix that only touches the empty branch **reds here**. |
| | `clicking the CTA renders the import section IN THE SAME PANEL` | It switches `view`; it calls **NO** `openPanel` and **NO** `ui_open_studio_panel`. (X-12: an import panel would need `import_source_id`, which is structurally inexpressible in the param-less `panel_id` enum — that is why it is a SECTION.) |
| | `a System row renders "Adopt to edit", never an edit affordance` | `owner_user_id === null` ⇒ no edit button, **no `<input disabled>`**; an **Adopt** primary. |
| | `an imported row renders the ⚠ imported chip` | `source==='imported'` **or** `imported_derived===true` ⇒ the chip. |
| | `all three views stay MOUNTED across a tab switch` | Switch Library→Import→Library; assert the Import subtree is still in the DOM (hidden), **not unmounted**. |
| | 🔒 `the panel renders the DETAIL view from params.templateId, and the LIST with no params` | Adjudication **F**'s seam. Mount with `params={{templateId:'t1'}}` ⇒ detail; mount bare ⇒ list (**the bare-id / X-12 guard**); fire `onDidParametersChange` with a templateId ⇒ it switches to detail. |
| 🔴 `frontend/src/features/studio/panels/__tests__/ArcTemplatesPanelPollSurvivesTabSwitch.test.tsx` (**NEW**) | 🔒 `the paid job's poll KEEPS POLLING while its view is hidden` | **THE ONE THAT MAKES `hidden` REAL.** Mock BE-7c to return `running` for N polls then `completed`. Start a deconstruct in the Import view → `fireEvent.click` the Library tab → advance fake timers → assert **(a)** the poll's **fetch count KEPT INCREASING** while Import was hidden, **(b)** `arc-templates-view-import` is still in the document, **(c)** switching back shows the terminal `completed` state and the new template row. 🔴 **A test that only asserts the `hidden` className is a RUBBER-STAMP** — the red must come from **the poll dying**, not from a classname. |
| `frontend/src/features/studio/panels/__tests__/legacyRetirementGuard.test.ts` (**NEW** — step 10) | `the arc-template library has at least one reachable door` | 🔒 **GG-4, made mechanical.** |
| `frontend/src/features/composition/motif/__tests__/sharedComponentsSingleHome.test.ts` (**NEW** — step 11) | `each shared component has EXACTLY ONE home` | 🔒 **DOCK-2's anti-fork lock.** |
| `frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts` (**existing — it just goes green**) | — | `arc-templates` has a `category` **∈ `CATEGORY_ORDER`** and a non-empty `guideBodyKey`; **py enum == contract enum == `OPENABLE_STUDIO_PANELS`**. |
| `frontend/src/features/studio/agent/handlers/__tests__/arcEffects.test.ts` (**EXTEND — spec 32 owns the file**) | `a composition_arc_* effect invalidates the arc-templates queries` | Fire `composition_arc_extract_template` through `runEffectHandlers`; assert `invalidateQueries` was called with `['composition','arc-templates']`. |
| | `there is exactly ONE handler registered for composition_arc_*` | 🔒 **THE DOUBLE-FIRE LOCK.** After `clearEffectHandlers()` + `_resetArcEffectHandlers()` + `registerArcEffectHandlers()`, assert `matchEffectHandlers('composition_arc_update').length === 1` — **and likewise for `composition_arc_apply` and `composition_arc_extract_template`**. It **reds the moment anyone adds a second overlapping pattern anywhere, including in `bookEffects.ts`.** |
| | 🔒 `the handler unwraps a NESTED envelope` | Run the handler over `{ok:true, result: JSON.stringify({arc_id:'A1'})}` (**not** an already-unwrapped payload) and assert `invalidateQueries` was called with `['composition','arc-templates']`. **Feeding a pre-unwrapped payload is the exact test hole that let the `unwrapToolResult` bug ship TWICE** (`resultEnvelope.ts:1-7`). |

#### 6.4 The enum-count assertion — READ THIS TWICE

The three guards must move **in lockstep, by +1**:

```
py enum (frontend_tools.py)  N → N+1
contract enum (contracts/frontend-tools.contract.json)  N → N+1
OPENABLE_STUDIO_PANELS (catalog.ts)  N → N+1
```

🔴 **ASSERT THE DELTA AND THE SET EQUALITY. NEVER A LITERAL — AND DO NOT WRITE A TARGET NUMBER DOWN AT
ALL** (`Q-34-PANEL-COUNT-DELTA`). Plan 30 §8.0 check 6: *six of eight specs computed their target from the
same 57 baseline, as if each were the only wave.* The waves are **sequential**; the counts are
**cumulative**. **A written-down target is a HAZARD, not a help — it invites someone to hardcode it, and it
is wrong the moment a wave is re-ordered or dropped**, which *"sends a builder hunting a phantom
regression."*

**The three guards are ALREADY set-based and baseline-independent, so this is structurally handled by
existing code:** `panelCatalogContract.test.ts:33-36` is `expect([...(enumIds ?? [])].sort()).toEqual(openable)`
— **SET equality, zero count literals** — and step 6's generator makes the contract JSON a **derivative** of
the py enum rather than a third hand-maintained list. **The only assertions you may add are
`expect(enumIds).toContain('arc-templates')` and the +1 delta against the `N_before` you recorded in
pre-flight cmd 8. Never arithmetic against a literal.**

**The four steps, in order** (`Q-34-CONTRACT-REGEN` — and **step D is not optional**):
- **A.** `frontend_tools.py:402` — append `"arc-templates"` to the `panel_id` enum.
- **B.** `frontend_tools.py:403-481` — append **one clause to the description prose**, right after the
  `'quality-canon' = …` clause that currently ends it. 🔴 **That gloss is the model's ONLY hint the panel
  exists — an enum entry with no gloss is a panel the agent can NEVER choose. Do not skip it.**
- **C.** **REGENERATE** the contract — **never hand-edit** `contracts/frontend-tools.contract.json`.
  ⚠ The spec's command line is bash and **will NOT run in this repo's PowerShell dev shell**. Use:
  ```powershell
  cd services/chat-service
  $env:WRITE_FRONTEND_CONTRACT='1'; python -m pytest tests/test_frontend_tools_contract.py; $env:WRITE_FRONTEND_CONTRACT=$null
  ```
- **D.** 🔴 **RE-RUN WITHOUT THE ENV VAR — THIS IS THE ACTUAL EVIDENCE STEP.** The regen run calls
  `pytest.skip(...)` (`test_frontend_tools_contract.py:138`), so **it asserts NOTHING**. A builder who runs
  only step C and sees green **has proven nothing.** Run `python -m pytest tests/test_frontend_tools_contract.py`
  clean and **paste the green output**. Then run the FE half (`panelCatalogContract.test.ts` +
  `frontendToolContract.test.ts`), which read the same JSON — they are the guard that catches a count moving
  in only two of three.
- **COMMIT `catalog.ts` + `frontend_tools.py` + the regenerated JSON TOGETHER.** A commit that lands the
  enum without the regenerated JSON reds the contract test; one that lands the JSON without `catalog.ts`
  reds `panelCatalogContract`. **Stage the files by name — never `git add -A`.**
- **No `CLOSED_SET_ARGS` change is needed** — `ui_open_studio_panel: ["panel_id"]` is already registered
  (`test_frontend_tools_contract.py:64`), so the enum rule is already enforced for this arg.

**DoD evidence:** `"W4-FE1: panelCatalogContract + UserGuidePanel + useStudioCommands + frontendToolContract green; chat-service test_frontend_tools_contract RE-RUN WITHOUT the env var (green, not skipped) + test_frontend_tools green; ArcTemplatesPanel.test.tsx <N> passed incl. the non-empty-library CTA lock and the params seam; ArcTemplatesPanelPollSurvivesTabSwitch green (fetch count kept increasing while hidden); legacyRetirementGuard + sharedComponentsSingleHome green; arcEffects.test.ts incl. the single-handler lock and the nested-envelope unwrap; py enum == contract enum == openable, all N_before+1"`

---

### W4-FE2 — the Catalog tab (the paged public browse)

**Kind:** FE · **dependsOn:** `W4-FE1` · **Size:** S

`GET /arc-templates/catalog` has **ZERO FE consumers** at HEAD. This slice gives it one.

**Files**

1. **EDIT `frontend/src/features/composition/motif/arcApi.ts`** — add:
   ```ts
   /** BE-NONE — the SHIPPED public-discovery route (0 FE consumers at HEAD).
    *  ⚠ Its response shape is DIFFERENT from `list()`: `{items, total, limit, offset}`
    *  and it IS paged. `list()` returns `{arc_templates, scope, limit}` and is NOT.
    *  Reading `.items` off `list()` gets `undefined`. */
   catalog(
     params: { genre?: string; q?: string; language?: string;
               sort?: 'recent' | 'name'; limit?: number; offset?: number },
     token: string,
   ): Promise<ArcTemplateCatalogPage> {
     return apiJson<ArcTemplateCatalogPage>(`${BASE}/arc-templates/catalog${_qs(params)}`, { token });
   },
   ```
2. **EDIT `frontend/src/features/composition/motif/arcTypes.ts`** — 🔴 **ADJUDICATED
   (`Q-34-TWO-LIST-SHAPES`): the catalog item is a NARROW `Pick`, NOT `ArcTemplate & {adopt_target}`.**
   The server's `_CATALOG_COLS` allow-list (`arc_template_repo.py:304-307`) sends **only** these fields
   (note `tracks AS threads`); it **never** sends `owner_user_id` / `visibility` / `layout` / `arc_roster` /
   `pacing` / `status`. Typing the item as a full `ArcTemplate` is a **lie the compiler will help you tell**.
   ```ts
   export type ArcCatalogParams = { genre?: string; q?: string; language?: string;
                                    sort?: 'recent' | 'name'; limit?: number; offset?: number };
   export type CatalogArcTemplate = Pick<ArcTemplate,
     'id'|'code'|'language'|'name'|'summary'|'genre_tags'|'chapter_span'|'threads'|'source'|'version'
   > & { updated_at: string; adopt_target: 'user' };
   export type ArcCatalogList = { items: CatalogArcTemplate[]; total: number; limit: number; offset: number };
   ```
3. **CREATE `frontend/src/features/composition/arc-templates/hooks/useArcCatalog.ts`** —
   `useQuery(['composition','arc-templates','catalog', {genre,q,limit,offset}], …)`. Exposes
   `items`, `total`, `page`, `nextPage`, `prevPage`. ≤ ~200 lines, **no JSX**.
   🔴 **Add the `catalogToArc(c: CatalogArcTemplate): ArcTemplate` normalizer**, copied from
   `catalogToMotif` (`useMotifLibrary.ts:31-61`): set `owner_user_id` to a **`CATALOG_OWNER_SENTINEL`**
   (`'__catalog__'`) so the tier helper resolves **`public`** (non-null and never `=== viewer`),
   `visibility:'public'`, `status:'active'` (`list_public` is active-only), and fill the omitted heavy
   fields with `layout: []`, `arc_roster: []`, `pacing: []`.
   ⚠ **An empty `layout` on a catalog card is CORRECT, not a bug** — the card renders
   name/summary/chapter_span/threads only, and the **full** arc is one `arcApi.get` away on **Open**
   (`get_visible` **does** admit others' public rows; only a foreign **PRIVATE** row is the uniform 404 —
   `arc.py:66`).
   **Paging default (veto-able):** mirror motif — pass `limit:100` and **IGNORE `offset` for M1**; the
   catalog tab is a single page. `total` is on the envelope if you later want a *"showing N of M"* chip.
   **Do not build an offset pager AT-2 did not ask for.**
4. **CREATE `frontend/src/features/composition/arc-templates/components/ArcCatalogList.tsx`** — rows +
   an **Adopt** action per row (the **only** write available on a catalog row).
   `MotifStateBoundary skeleton="cards"` for loading; boundary + Retry for error.

**Tests — `frontend/src/features/composition/arc-templates/__tests__/useArcCatalog.test.tsx` (NEW)**

| Test | Asserts |
|---|---|
| 🔒 `reads .items (not .arc_templates) from the catalog route` | **The shape-drift lock.** Mock the fetch with `{items:[…], total:9, limit:50, offset:0}` ⇒ the hook returns 1 item. Then mock it with the **list** route's shape `{arc_templates:[…]}` ⇒ the hook yields **zero** items — proving we read the right key and would notice a re-point. *(This is the exact `undefined`-crash the two envelopes invite.)* |
| 🔒 `ArcCatalogList is NOT assignable to ArcTemplateList` | A **tsc-level** guard (`@ts-expect-error` on the assignment). The two envelopes are **not interchangeable**. |
| `catalogToArc fills the omitted heavy fields and marks the row public` | `owner_user_id === CATALOG_OWNER_SENTINEL`, `visibility === 'public'`, `layout/arc_roster/pacing === []`. |
| `the catalog tab renders a catalog row` | Required by `ArcTemplateLibraryView.test.tsx` too — it would **RED** if the hook read `.arc_templates` off the catalog response. |
| `total drives the pager, not items.length` | `{items: 50 rows, total: 214}` ⇒ the pager reports more pages (if a pager ships at all). |

**DoD evidence:** `"W4-FE2: useArcCatalog.test.tsx passed; the catalog route has its first FE consumer; the {items,total} vs {arc_templates} shape lock + the tsc non-assignability guard are green; CatalogArcTemplate is a narrow Pick (no owner_user_id/visibility/layout — the server never sends them)"`

---

### W4-FE3 — CRUD + adopt + the 412 reconcile + the System-row read-only rule

**Kind:** FE · **dependsOn:** `W4-FE1` · **Size:** M

**Files**

1. 🔴 **REWRITE THE PERSIST PATH OF `frontend/src/features/composition/motif/hooks/useArcTimeline.ts`**
   (`Q-34-OCC-412-AND-WRITE-CHAIN`) — **THE LIFTED HOOK ACTIVELY DOES THE WRONG THING TODAY.** This is not
   "already handled"; it is three live bugs in a file this wave mounts. Then apply the **same five rules**
   to the new `arc-templates/hooks/useArcTemplateEditor.ts` (the CRUD form).

   **(1) READ `current` OUT OF THE 412 BODY — DO NOT REFETCH.** `apiJson` already attaches it
   (`frontend/src/api.ts:159-163`, whose comment says so verbatim); the server sends it (`arc.py:218-222`).
   In the catch:
   `const current = (err as {body?:{detail?:{code?:string;current?:ArcTemplate}}}).body?.detail?.current`
   when `status===412 && detail.code==='ARC_TEMPLATE_VERSION_CONFLICT'`.

   **(2) RECONCILE, NEVER CLOBBER — the anti-clobber mechanism is the SEED GUARD.**
   🔴 **`useArcTimeline.ts:91-94`'s `qc.invalidateQueries` IS THE BUG:** the refetch bumps `arc.version`,
   the seed effect at `:67-76` sees `arc.version !== seededVersionRef.current` and calls
   `setPlacements(layoutToPlacements(arc.layout))` — **destroying the user's unsaved edits.**
   **DELETE the `invalidateQueries` call.** Replace it with, **in this order**:
   ```ts
   versionRef.current = current.version;
   seededVersionRef.current = current.version;               // ← the whole trick: the seed effect now
   qc.setQueryData(['composition','arc-template', targetArcId], current);   //   short-circuits
   setSaveError('conflict');
   // and DO NOT touch `placements`.
   ```
   Because `seededVersionRef` now equals the new `arc.version`, the seed effect's guard short-circuits and
   **the user's local placements survive**. **State this in a code comment** — it is not obvious.

   **(3) NO AUTO-RETRY after a 412** *(chosen default — PO may veto)*. The layout PATCH is a **whole-layout
   replace**, so an automatic re-PATCH at the new version **IS a silent clobber of the other writer.** The
   conflict banner (*"changed elsewhere — reloaded"*) carries **two explicit buttons**: **Keep my layout** →
   re-chains **one** persist at the NEW version; **Take theirs** → `setPlacements(layoutToPlacements(current.layout))`
   + clear the error. For the CRUD form (which has a real Save button), same reconcile — Save simply
   re-enables at the new version.

   **(4) CHAIN THE WRITES** (`instant-commit-control-over-occ-entity-needs-write-serialization`).
   `useArcTimeline.ts:103-108`'s debounce **dedups pending timers only, never in-flight PATCHes** ⇒ a rapid
   second edit carries a **stale `If-Match`** and **self-412s**. Add `const chainRef = useRef<Promise<void>>(Promise.resolve())`;
   the debounce timer **never calls `persist()` directly** — it does
   `chainRef.current = chainRef.current.then(() => persistOnce(arcId)).catch(() => {})`. `persistOnce` reads
   `versionRef.current` **only after the prior link resolves**. **The unmount flush (`:123-128`) must also go
   through `chainRef`, not call `persist()` raw.**

   **(5) BIND EACH WRITE TO ITS TEMPLATE ID** (`debounced-write-must-bind-its-target-entity`).
   `persistOnce(targetArcId: string)` takes the id as a **PARAMETER** (captured at schedule time) and guards
   **TWICE**: at entry `if (targetArcId !== arcIdRef.current) return;` and **again on resolution**, BEFORE
   touching `versionRef` / `seededVersionRef` / `setQueryData`. 🔴 **`:86-88` is the live bug:** a late
   resolution for template **A** stamps A's version into the **shared refs template B is now using.** Keep
   `arcIdRef` in sync inside the seed effect, and add an effect keyed on `arcId` whose **cleanup flushes the
   pending timer for the OUTGOING id**.

   📌 `useMotifEditor.ts` / `MotifEditorForm.tsx` have the **same** If-Match shape — if the CRUD form is
   built by copying them, **port these five rules there too** rather than inheriting the same three bugs.

2. **CREATE `frontend/src/features/composition/arc-templates/components/ArcTemplateDetail.tsx`**
   The detail view (draft state ②). Composes the **lifted** `ArcTimelineEditor` (+ the mobile list under
   `sm`) and `ArcApplyPreview`. **Does NOT render `ArcConformancePanel`** (AT-7).
   🔴 **The System-row rule (AT-2 / draft state ①b):** when `owner_user_id === null`, render the editor
   **read-only with an `Adopt to edit` PRIMARY button** — **never a disabled input.**
   *A disabled field says "you may not". The correct message is "clone it first."*
   Backing fact: `PATCH /arc-templates/{id}` is **owner-filtered in the repo**, so a System row simply
   **404s** for a regular user (`arc.py:201-204`). The GUI must never offer an affordance the server will
   uniformly 404.

3. **CREATE `frontend/src/features/composition/arc-templates/components/ArcTemplateCreateForm.tsx`**
   `+ New` → `POST /arc-templates`. **409 `ARC_TEMPLATE_CODE_EXISTS` renders ON THE `code` FIELD** —
   not as a toast. (A toast for a field-scoped validation error is a UX defect the spec names explicitly.)
   Also surface **409 `ARC_TEMPLATE_PUBLISH_LIMIT_REACHED`** as an **informative refusal** (*"published
   arc-template limit reached (N) — unpublish one first"*), never a generic error.

4. 🔴 **AT-9 — THE PUBLISH-STRIP DISCLOSURE, AS A PRE-FLIP CONFIRM DIALOG** (`Q-34-AT9-PUBLISH-STRIP`).
   The DB trigger `arc_template_publish_strip` (`db/migrate.py:1065-1088`) rewrites `source_ref` → an
   opaque `lineage:<own id>` on **any** `visibility → public|unlisted` transition (**and on INSERT**) of a
   row with `source='imported' OR imported_derived`. **It is a DB trigger, not a prompt — it cannot be
   bypassed, and it cannot be undone by setting the row back to private.**

   **(a) ONE flip control, and only one.** The **detail editor's** `visibility` `<select>`
   (private|unlisted|public) is the **ONLY** place visibility can change in this GUI. 🔴 **The `+ New`
   create form (M1) and the Extract form (M3) ship WITHOUT a visibility control** — they create **private**
   (server default; BE-7a sends `visibility:'private'`). *Rationale: the trigger fires on INSERT too, so a
   second shared-on-create path would be a **second un-gated flip**. One name, one concept.* *(Sane default
   — PO may veto and ask for `unlisted` on extract; then it must reuse the same dialog.)*

   **(b) FE TYPE FIX — do this first, it is the enabler.** `motif/arcTypes.ts` (~`:37-59`): **add
   `source_ref: string | null;`** to `ArcTemplate` and **DELETE the stale doc-comment claiming `source_ref`
   is never projected** — `arc_template_repo.py:45-50` **does** project it to the owner. The panel needs it
   to show the **actual value that is about to be rewritten.**

   **(c) CREATE the shared `motif/components/PublishStripDialog.tsx`**, prop `kind: 'arc' | 'motif'`
   (spec 33's `motif_publish_strip`, `migrate.py:989-1013`, **also wipes `examples[]`** — the motif variant
   adds that line). **Whichever of wave 3 / wave 4 lands first creates it; the other IMPORTS it. Do not fork.**

   **(d) THE GATE — in the select's `onChange` CALLBACK, never a `useEffect`** (CLAUDE.md's
   no-useEffect-for-event rule):
   ```ts
   const tainted   = tpl.source === 'imported' || tpl.imported_derived;  // == the trigger's predicate,
                                                                          //    incl. adopted clones
   const sharedNow = tpl.visibility === 'public' || tpl.visibility === 'unlisted';
   const toShared  = next === 'public' || next === 'unlisted';
   const needsGate = tainted && toShared && !sharedNow;
   ```
   `needsGate` ⇒ `setPendingVisibility(next)` + open the dialog; **DO NOT call `arcApi.patch`.** Otherwise
   patch immediately (**no false ceremony on an authored template — the trigger is inert there**).
   `arcApi.patch(id, {visibility: pending}, tpl.version, token)` fires **ONLY** from the dialog's
   `onConfirm` (**with `If-Match`** — this is a user-edited row; a 409
   `ARC_TEMPLATE_PUBLISH_LIMIT_REACHED` renders as an informative refusal, not a toast). **Cancel = close**;
   the select is controlled by `tpl.visibility`, so it snaps back with **no local state**.

   **(e) DIALOG COPY** (i18n, `composition` ns, keys `motif.arc.publish.*`; en first, then all 17 locales
   via `python scripts/i18n_translate.py` — **never hand-written**):
   - title: *"Publishing strips the source reference"*
   - body (**the §4.3 sentence, VERBATIM** — M2 must render this **same string** statically in the Import &
     Deconstruct section header, so **define it once and import it in both places**):
     > *"The raw text stays private to you and is never shared. Only the derived abstract structure can be
     > published — and publishing strips the source reference."*
   - the concrete rewrite line, rendered when `tpl.source_ref && !tpl.source_ref.startsWith('lineage:')`:
     *"Its source reference (`<tpl.source_ref>`) will be replaced with an opaque lineage token
     (`lineage:<id>`). This is done by the database and cannot be undone by setting the template back to
     private."*
   - buttons: *"Publish anyway"* / *"Keep private"*.

5. **Adopt** — reuse the shared `AdoptTargetModal` (**import it; do not fork it**). `POST /{id}/adopt`
   → **201** with the clone. It is the **only** write available on a System or Catalog row.
   ⚠ **NO cost card** — adopt is a **row clone**, $0, no LLM (`arc_template_repo.py:249-261`). Wrapping a
   $0 action in a cost confirmation is a **fake confirmation** — its own defect.
   🔴 **THE 409 CORRECTION — spec 34 §8 MIS-SITES IT** (`Q-34-NO-FAKE-COST-CARD` item 2).
   **`ARC_TEMPLATE_PUBLISH_LIMIT_REACHED` CANNOT fire on adopt.** `_publish_quota_guard` (`arc.py:88-100`)
   is called **ONLY** from `create` (`:181-182`) and `PATCH` (`:205-213`), and **only** when
   `body.visibility ∈ ("public","unlisted")`; **adopt clones into the caller's own tier as a PRIVATE row**,
   so it **never** trips the ceiling. Wiring a PUBLISH_LIMIT branch on the Adopt button would be a **dead
   branch** *and* would leave the real refusal generic. Branch on `err.body.detail.code` (**not
   `err.code`** — `api.ts:161` reads the TOP-LEVEL body, which is `undefined` for FastAPI's
   `{detail:{code}}` envelope) at exactly **three** sites:
   | Site | Code | Render |
   |---|---|---|
   | **CREATE form + the visibility flip (PATCH)** | 409 `ARC_TEMPLATE_PUBLISH_LIMIT_REACHED` | An **informative inline refusal** using the server's own `limit` + `message` (*"published arc-template limit reached (N) — unpublish one first"*); the row **stays private** (the server wrote nothing); offer a one-click jump to the user's published templates (`scope=mine` filtered on visibility) so they can unpublish. **NEVER a toast of `res.statusText`.** |
   | **ADOPT** | 409 `ARC_TEMPLATE_CODE_EXISTS` | The server's message **on the `code` field**, with a rename/retag affordance (the caller owns the rename policy — `arc.py:259-260`). No cost card, no spinner. |
   | **MATERIALIZE** | 409 `CHAPTER_ALREADY_PLANNED` | Keep the existing honest affordance (`useArcMaterialize.ts:25-26` → *"Replace existing"* re-POST with `replace:true`). Add no cost card. |
   📌 Also correct **spec 34 §8's wording** in this slice: *"Adopt is quota-bearing … surface 409
   `ARC_TEMPLATE_PUBLISH_LIMIT_REACHED`"* → *"**PUBLISH** (create/PATCH with visibility public|unlisted) is
   quota-bearing → 409 `ARC_TEMPLATE_PUBLISH_LIMIT_REACHED` as an informative refusal; **ADOPT is free and
   private**, its only refusal is 409 `ARC_TEMPLATE_CODE_EXISTS`."*

6. **Archive** — `DELETE` (soft; owner-only). The route returns `{archived:true}` **uniformly** even for
   a row you don't own (no oracle), so **the UI must only offer Archive on `owner_user_id === me`**.

7. 🔴 **THE NO-FAKE-COST-CARD GUARD, MADE MECHANICAL.** Exactly **one** paid action exists in this panel:
   the **deconstruct** (M2). `/arc-templates/{id}/apply` is **PURE** (`arc.py:278-296` — *"no LLM, nothing
   persisted"*), `/works/{pid}/arc/materialize` is **deterministic DB-write only** (`plan.py:1260`; MCP
   mirror `server.py:4584` — *"Deterministic (no LLM)"*), adopt is a row clone. **Builder rule: within
   `features/composition/**`, `CostConfirmCard` and `mcpExecute` may be imported ONLY by the Deconstruct
   section component.** Enforce with `__tests__/ArcTemplatesNoCostCard.test.tsx`: render the Apply-preview,
   Materialize and Adopt flows and assert `queryByTestId('cost-confirm-card') === null` (add the testid to
   `CostConfirmCard` if absent), **plus** a source assertion that `arcApi.ts` / `useArcMaterialize.ts` /
   `useAdoptFlow` do **not** reference `mcpExecute`.

**Tests — `frontend/src/features/composition/motif/__tests__/useArcTimeline.test.tsx` (EXTEND — §11.3's
forced-412 test) + `arc-templates/__tests__/useArcTemplateEditor.test.tsx` (NEW)**

| Test | Asserts |
|---|---|
| 🔒 `a forced 412 reconciles: baseline replaced, USER EDITS SURVIVE` | Mock `arcApi.patch` → reject with `{status:412, body:{detail:{code:'ARC_TEMPLATE_VERSION_CONFLICT', current:{…version:9, layout: SERVER_LAYOUT}}}}`. Assert `saveError==='conflict'` **AND — this is the assertion that catches the clobber — `result.current.placements` still equals the USER's edited placements, NOT `SERVER_LAYOUT`.** Then assert the next persist sends `If-Match: 9`. 🔴 **A test that only asserts `saveError==='conflict'` PASSES ON THE BROKEN CODE and proves nothing.** |
| 🔒 `the write chain prevents a self-412` | Make `patch` return a manually-deferred promise. `onEdit A` → advance 600ms (PATCH #1 in flight) → `onEdit B` → advance 600ms ⇒ assert `patch` was called **exactly ONCE**. Resolve #1 with `version:6` ⇒ assert PATCH #2 goes out with **`If-Match: 6`, not 5**. |
| 🔒 `a late resolution for template A does not poison template B` | `onEdit` on A, let PATCH A go in flight, rerender with `arcId=B`, resolve A's PATCH with `version:99` ⇒ assert **B's first PATCH carries B's OWN version, not 99**, and that **no `setQueryData` landed on B's key**. |
| `a 412 never auto-retries` | The hook does **not** re-issue the PATCH by itself; the two explicit buttons do. |
| `ArcTemplateDetail.test.tsx :: a System row shows "Adopt to edit", not a disabled input` | 🔒 The tenancy-affordance lock. `owner_user_id: null` ⇒ `queryByTestId('arc-tpl-save')` is **null**, `getByTestId('arc-tpl-adopt')` exists, and **no `<input disabled>`** is rendered. |
| `ArcTemplateCreateForm.test.tsx :: a 409 code-exists renders on the code field` | The error text is inside the `code` field's error slot, not a toast. |
| `PublishStripDialog.test.tsx` — **five cases** | (a) selecting `public` on a **tainted** template does **NOT** call `arcApi.patch` **and DOES render the §4.3 body string**; (b) Confirm calls `patch` **once** with `{visibility:'public'}` + the `If-Match` version; (c) Cancel ⇒ **zero** patch calls, select still `private`; (d) an **untainted** template patches **immediately, with NO dialog** (no false ceremony); (e) an **already-`unlisted` tainted** template flipping to `public` shows **no dialog** (its ref is already `lineage:` — mirror the producer's own guard). |
| `ArcTemplatesNoCostCard.test.tsx` | 🔒 Apply-preview / Materialize / Adopt render **no** `cost-confirm-card`, and `arcApi.ts` / `useArcMaterialize.ts` / `useAdoptFlow` never reference `mcpExecute`. |
| `a 409 PUBLISH_LIMIT renders on the PUBLISH flip, and a 409 CODE_EXISTS on ADOPT` | Two tests, two codes, two specific copies — **neither is a generic error**. |

**DoD evidence:** `"W4-FE3: useArcTimeline.test.tsx forced-412 reconcile PROVES the user's placements survive (not just that saveError==='conflict'); the write chain + entity-binding locks green; useArcTemplateEditor + ArcTemplateDetail + ArcTemplateCreateForm + PublishStripDialog (5 cases) + ArcTemplatesNoCostCard — <N> passed; System row has no edit affordance; adopt's 409 is CODE_EXISTS (PUBLISH_LIMIT is on create/PATCH only — the spec's §8 wording was wrong and is corrected)"`

---

### W4-FE4 — Apply-preview → Materialize → **assert AT-6's stamp landed**

**Kind:** FE · **dependsOn:** `W4-BE4`, `W4-FE3` · **Size:** S *(was M — the stamp moved server-side)*

🔴🔴 **THIS SLICE WAS REWRITTEN BY ADJUDICATION D. The original W4-FE4 (`getArcs` → find-or-create →
`createArc` / `PATCH` → `assign-chapters` → assert `assigned`) IS A BUG ON EVERY PATH. DO NOT BUILD IT.**

> **Why.** `materialize` → `commit_decomposed_tree` → `_insert_decomposed_tree` **already created** the
> spec arc (`StructureRepo.create_node(book_id, kind='arc', …)` — `outline.py:435-438`) and **already set
> `structure_node_id=arc.id` on every chapter node** (`outline.py:444`), returning it as `arc_id`
> (`outline.py:471` → `plan.py:1384`).
> - `createArc` would mint a **SECOND** spec arc — **the exact duplicate AT-6 exists to prevent.**
> - `assignChapters` would then **re-point the chapter nodes' `structure_node_id` OFF materialize's arc
>   onto the new one**, leaving materialize's arc **active-but-childless**: an orphan bystander, the very
>   class `D-A3-REPLACE-ORPHAN-ARC-NODES` / FD-17 was written to kill.
> - *"Match on `(book_id, arc_template_id)` and PATCH the existing node"* is **also** a bug: the `replace`
>   path **archives** the prior arc (`outline.py:691-702`) and mints a fresh one, so that rule PATCHes the
>   **ARCHIVED** arc and leaves the **live** one unstamped ⇒ `NO_TEMPLATE_PROVENANCE` **forever** after any
>   re-materialize.
>
> **The stamp is now W4-BE4 (server-side, ~25 lines, one writer, transactional).** This slice's job is to
> **ASSERT THE EFFECT** and to render every refusal honestly.

#### The flow (draft states ② + ②b)

```
1. Apply-preview   POST /arc-templates/{id}/apply     → ArcApplyPlan   (PURE, $0, persists NOTHING)
                   render: rescaled placements · roster binding · the §12.6 DROP/MERGE report
2. Materialize     POST /works/{pid}/arc/materialize  → { arc_id (a STRUCTURE_NODE), chapter_ids[],
                                                          scene_ids[], drop_merge_report, replay,
                                                          structure_node_id, chapters_assigned, … }
                                                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                                          ← the two fields W4-BE4 added
3. ASSERT          🔴 res.structure_node_id && res.chapters_assigned === res.chapter_ids.length
                   else ⇒ ERROR STATE. Never a checkmark.
```

#### Files

1. **EDIT `frontend/src/features/composition/motif/arcTypes.ts`** — add `structure_node_id: string` and
   `chapters_assigned: number` to `ArcMaterializeResult` (`:141`).

2. **EDIT `frontend/src/features/composition/motif/hooks/useArcMaterialize.ts`**
   - **ONE call.** After `POST /works/{pid}/arc/materialize` resolves, **assert the effect**:
     ```ts
     if (!res.structure_node_id || res.chapters_assigned !== res.chapter_ids.length) {
       // The plan was written, but its template provenance was NOT stamped ⇒ Drift will show no
       // template for this arc. A checkmark here is a lie (silent-success-is-a-bug).
       setState('STAMP_FAILED');   // data-testid="arc-materialize-error", i18n arcTemplates.stampFailed
     }
     ```
     Copy: *"The plan was written, but its template provenance was NOT stamped — Drift will show no
     template for this arc."* + a **Retry** that re-issues **only** the materialize (idempotent by key).
   - 🔴 **Do NOT add `createArc` to `plan-hub/api.ts`. Do NOT call `assignChapters` from this flow. Do NOT
     add `POST /books/{bid}/arcs` or `assign-chapters` anywhere under `features/composition/`.** Spec 34
     §9's *"two callers of one table"* hazard is thereby **never created** — and no debt row is filed,
     because **there is no second writer**.
   - 🔴 **The FE ignores `replay`** when deciding anything about provenance (W4-BE4 stamps on replay too).
     It may use `replay` for UI copy (*"already materialized"*) — **never as a gate**.
   - Invalidate: `['composition','decompose', projectId]` (existing),
     `['composition','motif-bindings', projectId]` (existing), **`['composition','arcs', bookId]`** (new —
     the *Used by* list) and **`['composition','arc-templates']`** (new).
   - ⚠ **No `useEffect` for any of this.** It is a *consequence of an action*, not a synchronization — it
     lives in the mutation's `onSuccess` / `mutationFn` chain.

3. **EXTEND `frontend/src/features/composition/motif/hooks/useArcMaterialize.ts`'s error surface**
   (`Q-34-MATERIALIZE-ERRORS`). Today `:26` exposes only
   `conflict: (error as {status?}).status === 409` — **everything else degrades to a boolean `isError`**,
   and `ArcMaterializeAction.tsx:64-68` collapses **three distinct 400s into one string**, discarding
   `unresolved_placements`. **The backend already ships all four codes with their payloads. The FE swallow
   is the whole gap. NO backend change, NO `api.ts` change.**
   ```ts
   export type MaterializeFailure = {
     status: number;
     code: 'NO_CHAPTERS' | 'TOO_MANY_CHAPTERS' | 'NO_MATERIALIZABLE_PLACEMENTS'
         | 'CHAPTER_ALREADY_PLANNED' | 'BAD_REFERENCE' | 'UNKNOWN';
     detail?: string;
     chapter_ids?: string[];                                                    // 409
     unresolved_placements?: { motif_code: string; thread: string; reason: string }[];  // 400
     count?: number; max?: number;                                              // 400 TOO_MANY_CHAPTERS
   };
   ```
   🔴 **THE PARSE TRAP:** read it from `(mut.error as {body?:{detail?:unknown}}).body?.detail` — **NOT**
   from `error.code`. `api.ts:161` sets `code` off the **TOP-LEVEL** body, which is **always `undefined`**
   for FastAPI's `{detail:{code,…}}` envelope. Unknown/absent ⇒ `'UNKNOWN'`. **Keep `conflict` as a derived
   `failure?.code === 'CHAPTER_ALREADY_PLANNED'`** so existing consumers/tests don't break.

4. **EDIT `frontend/src/features/composition/motif/components/ArcMaterializeAction.tsx`** — replace the
   single generic `<p>` (`:64-68`) with a **switch on `failure.code`** — **swallow none**:
   | Server | Render |
   |---|---|
   | **400 `NO_CHAPTERS`** | `data-testid="arc-materialize-err-no-chapters"` — the server's own detail + *"materialize maps onto existing chapters — create chapters first."* *(Default, veto-able: a hint, **not** a deep-link CTA into the chapter creator — that is a nav dependency this wave doesn't own, and a wrong deep-link is worse than a hint.)* |
   | **400 `TOO_MANY_CHAPTERS`** | `data-testid="arc-materialize-err-too-many"` — render `count` and `max` **numerically**, from the body. |
   | **400 `NO_MATERIALIZABLE_PLACEMENTS`** | `data-testid="arc-materialize-err-unresolved"` — 🔴 **render `unresolved_placements` as a LIST**, one row per entry showing `motif_code · thread · reason`, **NOT a count**. Map the **only two** server reasons (`arc_materialize.py:116,121`): `motif_not_visible` → *"motif not found or not shared with you"*; `motif_has_no_beats` → *"motif has no beats to distribute"*. |
   | **400 `BAD_REFERENCE`** | The server's `detail`, verbatim. |
   | **409 `CHAPTER_ALREADY_PLANNED`** | Keep the existing conflict block + **Replace** button (`:47-62`), and **ADD a list of the returned `chapter_ids`** under `data-testid="arc-materialize-conflict-chapters"` — the spec requires the re-confirm dialog to **list them**; today it does not. |
   | **fallback `UNKNOWN`** | Keep the existing generic string. **Do not delete the safety net.** |
   | **200 + a non-empty `drop_merge_report`** | 🔴 Always render it. *"A motif lost to a scale mismatch is NEVER silent"* (`arc.py:288`). |
   | **200 + the stamp assertion failing** | 🔴 **AN ERROR** (item 2), never a checkmark. |
   📌 The existing **success-path** `unresolved_placements` render (`:78-85`) is a **COUNT** and **stays
   as-is** — that is the **partial** case. The new 400 branch is the **total-failure** case and **must be
   itemized**.

**Tests**

| File | Test | Asserts |
|---|---|---|
| `motif/__tests__/useArcMaterialize.test.tsx` | 🔒 `chapters_assigned:0 renders an ERROR, not a checkmark` | Mock materialize → `{arc_id:'A', chapter_ids:['c1','c2'], structure_node_id:'A', chapters_assigned:0}` ⇒ `arc-materialize-error` is present and `arc-materialize-success` is **absent**. **THE SILENT-NO-OP LOCK.** |
| | 🔒 `a missing structure_node_id ALSO errors` | `structure_node_id: null` ⇒ error. |
| | 🔒 `a partial link (n-1) ALSO errors` | `chapters_assigned: 4` for 5 ids ⇒ error. **Partial ≠ success.** |
| | `the happy path renders the checkmark` | `chapters_assigned === chapter_ids.length` ⇒ success. |
| | 🔒 `replay: true is NOT a gate` | `{replay:true, …}` ⇒ the same assertion runs; no branch skips it. |
| | 🔒 `NO second structure_node writer exists` | **Static:** `grep` `features/composition/**` for `assign-chapters` and `POST .../arcs` string literals ⇒ **ZERO**. And `plan-hub/api.ts` gained **no** `createArc`. |
| `motif/__tests__/ArcMaterializeAction.test.tsx` | `each of the 5 error codes renders its OWN copy, WITH ITS PAYLOAD` | Each mocks `apiJson` to reject with `Object.assign(new Error('x'), {status, body:{detail:{…}}})` and asserts the **testid PLUS the payload text**: the 409 asserts a returned **chapter_id string is on screen**; `NO_MATERIALIZABLE` asserts the **motif_code** (e.g. `"duel"`) is on screen; `TOO_MANY` asserts **count + max** render. 🔴 **Asserting only the testid would pass a component that renders an empty list. Assert the payload.** |

**i18n:** new keys under the `composition` namespace `motif.arc.materialize.*`, alongside the existing ones
(the component already uses `t()` with `defaultValue` — follow that pattern).

**DoD evidence:** `"W4-FE4: useArcMaterialize.test.tsx <N> passed incl. the chapters_assigned:0 → ERROR lock, the missing-structure_node_id lock and the replay-is-not-a-gate lock; ArcMaterializeAction.test.tsx 5 passed, each asserting the PAYLOAD not just the testid; grep proves ZERO second writers of structure_node in features/composition/** and NO createArc in plan-hub"`

---

### W4-FE5 — *Used by* + **Drift** (BE-NONE — the audit correction)

**Kind:** FE · **dependsOn:** `W4-FE4` · **Size:** M

🔴 **The audit said the drift view needed BE-8 and told this wave to PARK it. That is FALSE.**
`GET /v1/composition/works/{pid}/conformance?scope=arc_template_drift&arc_id=<structure_node_id>` is
**SHIPPED, wired, and has zero FE consumers** (`routers/conformance.py:390-404`). **BE-NONE. It ships in
the core of this wave.**

#### § Used by (BE-NONE)

`getArcs(bookId, token)` (plan-hub — **reuse**) → **client-side filter** on
`node.arc_template_id === template.id`. Each row = one spec arc materialized from this template, with a
**Drift** button carrying that node's id.
*(This is why AT-6 matters: with no stamp, this list is empty forever.)*

#### § Drift (BE-NONE)

`GET /works/{pid}/conformance?scope=arc_template_drift&arc_id=<structure_node.id>` →
`compute_arc_report(..., by_structure=False)`.

Render (draft state ③): **thread-progress coverage** · the **realized-vs-template pacing curve** ·
**structural succession flags** · the §12.6 **unmaterialized (folded-away) placements** — the drop/merge
report, *which is the whole point*.

🔴 **SEVEN RENDERED OUTCOMES, NOT THREE.** The **four Work-gate states** are **ORTHOGONAL** to the **three
server empty states** and **must not be merged** (`Q-34-DRIFT-PID-RESOLUTION` item 5).

**§A · The Work gate — gate the AFFORDANCE, never the panel** (`Q-34-DRIFT-PID-RESOLUTION`)

🔴 Resolve `pid` **once, at panel root**, via **`useQualityWork(host.bookId, accessToken)`**.
**Do NOT call `useWorkResolution` and do NOT hand-roll `data?.status === 'found' ? work.project_id : null`
— that exact line is the bug commit `9262ed53e` removed** (*"unconsulted is not empty, ambiguous is not
absent"*). 📌 **Spec 34 §6 says "the existing `useWork()` gate" — NO SUCH FUNCTION EXISTS**
(`features/composition/hooks/useWork.ts:7` exports only the raw `useWorkResolution`). The gate is
**`useQualityWork`** — it already resolves `candidates[0].project_id` exactly like every other consumer.
**Reuse it as-is; do not rename or fork it** (6 files consume it).

🔴 **NEVER early-return a gate screen from the panel.** `arc-templates` is **user-tier** and MUST browse
with **no Work**. Mirror `QualityHubPanel.tsx:28-60` literally: the gate drives an **inline banner**, and
Library / Catalog / detail / timeline / CRUD / Adopt / Suggest / **§ Used by** (book-scoped) all render and
work in **all four** states. Only the **pid-bearing** actions are gated: **Drift** and **Materialize**.
📌 **Extract needs NO pid** — it is node-scoped and stays enabled Work-less. (Correct §6 step 1's
*"Apply/Extract/Drift need one"* to *"Apply/Materialize + Drift"*.)

| Gate state | Drift button | `data-testid` / copy |
|---|---|---|
| `loading` | disabled, `aria-busy` | `arc-templates-drift-loading`. **No text claim either way.** |
| `unavailable` | disabled + an **AMBER** note | `arc-templates-drift-unavailable`, key `composition:arc.drift.workUnavailable`: *"Could not reach the co-writer service, so drift could not be computed. This arc may have drifted in ways not shown here. Try again shortly."* 🔴 **NEVER render the no-work sentence here** — this is a fact about **US**, not about the book, and saying "no session yet" invites the user to create a **duplicate Work**. |
| `no-work` | disabled + a **neutral** note | `arc-templates-drift-no-work`, key `composition:arc.drift.noWork`: *"Drift is measured against a co-writer session, and this book has no session yet — start composing a chapter first. Browsing, adopting and extracting templates still work."* **No "Set up co-writer" create CTA in v1** — Work creation stays owned by `CompositionPanel` (one home). |
| `ready` | **ENABLED** | Fire the read with `pid = work.projectId`, `arc_id = row.structure_node_id` (**the § Used by row's own id — NOT `template.id`**, the M-BUG-4 class). |

**§B · The three SERVER empty states — DISTINCT, and evaluated BEFORE the query result reaches
`MotifStateBoundary`** (`Q-34-DRIFT-3-EMPTY-STATES`; draft state ③b):

| Condition | Server | `data-testid` / Render |
|---|---|---|
| No spec arc uses this template | *(**no call is made** — `arcNodeId = null` ⇒ the hook stays `enabled: false`)* | `arc-drift-not-applied` — *"Not applied to this book yet."* + the **Apply** CTA. **ZERO network calls.** |
| The arc has no template provenance | **422 `NO_TEMPLATE_PROVENANCE`** (`conformance.py:394`) | `arc-drift-no-provenance` — *"This arc was authored directly — there is no template to drift from."* (BA13). **No Retry button — retrying is not a remedy.** |
| The template was deleted / is foreign | **404 `{code:"NOT_FOUND"}`** (`:399-400`, H13 uniform) | `arc-drift-template-gone` — *"The source template is no longer available."* Covers **both** the deleted/foreign template (`:400`) **and** the foreign `structure_node` (`:330`) — **that is the H13 uniformity, and it is CORRECT that they read the same. Never phrase it as "not found."** |

*(A fourth exists and must also not be swallowed: **422 `ARC_ID_REQUIRED`** (`_resolve_book_arc`, `:327`).
The FE always passes one ⇒ it is a **programmer error** — surface it as an error, not a spinner.)*

🔴 **ONLY THEN** `<MotifStateBoundary isLoading isError onRetry skeleton="rows">` — for the **genuine
transport / 5xx** case. `MotifStateBoundary.tsx:49` renders **ONE generic "Couldn't load — please retry."
for every `isError`. Routing a 422/404 through it IS the collapse this item forbids.**

**§C · TWO CODE-LEVEL TRAPS**

1. 🔴 **`retry: false` IS REQUIRED** on the drift query. `App.tsx:12` sets a **global `retry: 1`**, so a
   422/404 would otherwise be **re-fired** and the user watches a **double-length spinner** before the
   honest message.
2. 🔴 **The error code is NOT on `err.code`.** `apiJson` (`frontend/src/api.ts:159-163`) sets `.code` from
   the **TOP-LEVEL** `body.code`, but composition-service raises `HTTPException(detail={"code": …})` — so
   it lands at **`err.body.detail.code`**. Add a local helper:
   ```ts
   function driftErr(e: unknown) {
     const x = e as { status?: number; body?: { detail?: { code?: string } } };
     return { status: x?.status, code: x?.body?.detail?.code };
   }
   ```
   **Never match on `e.message`** (it *incidentally* equals the code string via `api.ts:145-155`'s
   `detailMessage` fallback — **that is a coincidence, not a contract**), and **never RENDER `e.message`**
   (it would literally print `"NO_TEMPLATE_PROVENANCE"` at the user).

#### Files

- **EDIT `frontend/src/features/composition/motif/api.ts`** — add, next to `arcConformance`:
  `arcTemplateDrift(projectId, arcNodeId, token)` →
  `apiJson(`${BASE}/works/${projectId}/conformance${_qs({ scope:'arc_template_drift', arc_id: arcNodeId })}`, { token })`.
  ⚠ **The param is `arc_id` = a `structure_node.id`** (`conformance.py:339`). The existing `arcConformance`
  (`:212-222`) still sends **`arc_template_id`** — **that param no longer exists on the router** (it would
  422 `ARC_ID_REQUIRED`). **Do NOT copy it. Send `arc_id`.**
- **CREATE** `arc-templates/hooks/useArcTemplateDrift.ts` —
  `useQuery({ queryKey: ['composition','arc-template-drift',projectId,arcNodeId], enabled: !!projectId && !!arcNodeId && !!token, staleTime: 30_000, retry: false })`;
  maps 422/404 to **discriminated** result kinds (`'no-provenance' | 'template-gone' | 'report'`), **never**
  a generic `isError`.
- **CREATE** `arc-templates/hooks/useArcTemplateUsage.ts` — the *Used by* filter: `getArcs(bookId, token)`
  (plan-hub — **reuse**) → client-side `nodes.filter(n => n.arc_template_id === template.id)`. Picker if >1.
- **CREATE** `arc-templates/components/ArcDriftPanel.tsx` (render order **fixed**: §A gate → §B's three →
  boundary) and `ArcDriftReport.tsx` (the four report sections).
- **CREATE** `arc-templates/components/ArcUsedByList.tsx`.
- **i18n** (ns `composition`): `motif.arcDrift.notApplied` / `.noProvenance` / `.templateGone` +
  `arc.drift.workUnavailable` / `.noWork`, each with the copy above as `defaultValue`.

**Tests — `arc-templates/__tests__/ArcDriftPanel.test.tsx` + `useArcTemplateDrift.test.tsx` (NEW)**

| Test | Asserts |
|---|---|
| 🔒 `zero usages makes NO call at all` | Empty *Used by* ⇒ `arc-drift-not-applied` present **AND `fetch` is NOT called**. |
| 🔒 `a 422 NO_TEMPLATE_PROVENANCE is its OWN state — not an error, not a zero, not a spinner` | `arc-drift-no-provenance` present **AND `motif-state-error` absent AND `motif-state-loading` absent.** (§11.4's *"not a spinner, not a zero"*.) The server side is already locked by `tests/unit/test_arc_conformance.py:311`. |
| 🔒 `a 404 is "the source template is no longer available", never "not found"` | `arc-drift-template-gone`; the copy contains **no existence-oracle wording**. |
| `a 200 renders all four report sections` | thread coverage · pacing curve · succession flags · **§12.6 unmaterialized (folded-away) placements**. |
| 🔒 `the four Work-gate states each render a DISTINCT testid, and the library still lists in ALL of them` | Mock `useWorkResolution` to yield `isLoading` / `isError` / `{status:'unavailable'}` / `{status:'none'}` / `{status:'candidates', candidates:[{project_id:'p1'}]}` / `{status:'found', …}` and assert **(a)** the template list renders in **every** one (Work-less browse), **(b)** Drift is disabled with the correct distinct testid in the first four, **(c)** 🔴 **in the `candidates` case Drift is ENABLED** and the fetch URL contains `/works/p1/conformance?scope=arc_template_drift` — **`candidates` is NOT `no-work`.** |
| `ArcUsedByList.test.tsx :: filters on arc_template_id` | Given 3 arcs, only the one whose `arc_template_id` matches is listed, and the Drift button carries **that node's `structure_node.id`**, not the template id. |

**DoD evidence:** `"W4-FE5: ArcDriftPanel.test.tsx + useArcTemplateDrift.test.tsx <N> passed — the three server empty states are three DIFFERENT renders (none reaches MotifStateBoundary) and the four Work-gate states are four DIFFERENT testids with the library browsing in all of them; candidates ⇒ Drift ENABLED; retry:false set (global retry:1 would have double-spun); the code is read from err.body.detail.code, never err.code; drift consumes the SHIPPED ?scope=arc_template_drift route (BE-NONE, zero backend written)"`

---

### W4-FE6 — Extract + Suggest (the UIs for BE-7a / BE-7b)

**Kind:** FE · **dependsOn:** `W4-BE1`, `W4-BE2`, `W4-FE3` · **Size:** S

#### § Extract — *"save this arc as a template"* (draft state ④)

The half that makes the library **grow from the user's own work**. *A library you can only consume from is
a catalog, not a library.*

- **EDIT** `frontend/src/features/composition/motif/arcApi.ts` — add:
  ```ts
  /** BE-7a — the REST twin of composition_arc_extract_template (AT-3: a Tier-A WRITE
   *  may not ride the FE bridge allowlist). */
  extractTemplate(
    nodeId: string,
    body: { code: string; name: string; language?: string; visibility?: 'private' | 'unlisted' },
    token: string,
  ): Promise<ArcExtractResult> {
    return apiJson<ArcExtractResult>(`${BASE}/arcs/${nodeId}/extract-template`, {
      method: 'POST', body: JSON.stringify(body), token,
    });
  },
  ```
- **CREATE** `hooks/useArcExtract.ts` + `components/ArcExtractForm.tsx`:
  pick a spec arc (from `getArcs`) → `code` / `name` / `language` → POST.
  🔴 **NO VISIBILITY CONTROL** (`Q-34-AT9-PUBLISH-STRIP` item 1) — the form **always sends
  `visibility:'private'`**. The strip trigger **fires on INSERT too**, so a shared-on-create path here
  would be a **second, un-gated visibility flip**. Publishing happens in **exactly one place**: the detail
  editor's select, behind `PublishStripDialog` (W4-FE3). *(PO may veto and ask for `unlisted` on extract —
  then it must reuse the same dialog.)*
  🔴 **409 renders ON THE `code` FIELD** (the engine deliberately does not swallow the
  `UniqueViolationError`, `arc_apply.py:660-666`). Not a toast.
  On success ⇒ invalidate `['composition','arc-templates']` and call **`openDetail(res.template_id)`**
  (the panel-root callback from W4-FE1 step 7′). 🔴 **NOT `studioLinks`** — adjudication **F**.

#### § Suggest — *"suggest an arc for this premise"* (draft state ④)

- **EDIT** `arcApi.ts` — add `suggest(body, token)` → `POST /arc-templates/suggest`.
- **CREATE** `hooks/useArcSuggest.ts` + `components/ArcSuggestPanel.tsx`.
- 🔴 **RENDER `match_reason`.** It is the **only** explanation the user gets for a ranked list. There is a
  shipped component for exactly this: **`motif/components/MatchReasonChip.tsx` — import it, do not fork
  it.** Each candidate's click = **`openDetail(candidate.arc_template.id)`** — the **same** callback the
  Library row click uses. **One concept, one home. No URL.**
- Call it with **`detail: 'summary'`** (each card deep-links to the detail view, which fetches the full row).

**🔴 OQ-3 — `premise`: THE SEED IS ON THE FE, AND IT IS AN OVERRIDE-OR-DERIVE, NOT A `useEffect`**
(`Q-34-OQ3-SUGGEST-PREMISE`). The Work's premise is **not** a first-class field on `composition_work`;
`premise` is **not a domain field at all** — it is an **optional embedding-query seed**
(`motif_retrieve.py:300`: empty ⇒ no query vector ⇒ the ranker degrades to genre order and *"never
500/[]"*). So an empty premise is a **legal call** and nothing breaks when a book has no summary.

1. **Seed from the EXISTING react-query cache — zero new backend work.** Call
   `useQuery({ queryKey: ['book', bookId], queryFn: () => booksApi.getBook(accessToken!, bookId) })` —
   **the SAME key `BookSettingsPanel.tsx:31-35` already uses**, so it is a **cache hit, not a second
   fetch**. `GET /v1/books/{id}` already returns **both** `summary` and `genre_tags`
   (`book-service/internal/api/server.go:991,996`).
2. 🔴 **THE SEED SHAPE — override-or-derive.** The book query resolves **AFTER mount**, so
   `useEffect(() => setPremise(book.summary), [book])` is **the exact anti-pattern CLAUDE.md bans**. Use:
   ```ts
   const [premiseOverride, setPremiseOverride] = useState<string | null>(null);
   const premise = premiseOverride ?? seedPremise(book);   // async-safe, NO effect
   // seedPremise(book) = (book?.summary?.trim() || book?.description?.trim() || '')
   ```
   Put **`seedPremise` in ONE exported helper** so Wave 6 changes **one line**. The textarea is controlled
   by `premise`; `onChange` → `setPremiseOverride`.
3. Also **seed the genre control from `book.genre_tags?.[0]`** — it is free (same wire) and it **materially
   improves the rank**.
4. **On submit, OMIT `premise` from the body when it is empty/whitespace-only** (do not send `""`). Both
   behave identically at `motif_retrieve.py:300`; **omitting is the honest wire.**
5. If `summary` **and** `description` are both blank, render the empty box with the placeholder
   *"Describe your premise — or add a summary in Book Settings to pre-fill this"* and a link that calls
   `host.openPanel('book-settings')`.
6. **Do NOT persist the box** (no localStorage for user data) — it is **ephemeral panel state**.
7. **Do NOT add a `composition_work.settings` key here** (SET-1..8: a stored-but-unread setting is a bug).
   📌 **Forward-compat, recorded so Wave 6 doesn't re-derive it:** `composition_work.settings JSONB NOT
   NULL DEFAULT '{}'` **ALREADY EXISTS** (`migrate.py:41`), so the dedicated field needs **NO migration** —
   it is purely a **settings-surface** question (effective value + source tier + one home/one name). When
   it lands, `seedPremise` becomes `work.settings.premise ?? book.summary ?? book.description` — **one
   line, one file.**
   *(Default noted for PO veto: `description` is the second-tier fallback because it is on the same wire and
   a blank suggest is a worse first run than a slightly-off seed. Trivially removable — delete one clause.)*

**Tests**

| File | Test | Asserts |
|---|---|---|
| `__tests__/useArcExtract.test.tsx` (NEW) | `a 409 renders on the code field, not as a toast` | The error lands in the `code` field's error slot. |
| | `the extract form sends visibility:'private' and renders NO visibility control` | 🔒 AT-9's one-flip-control lock. |
| | `success calls openDetail(template_id) — NOT studioLinks` | Adjudication **F**: assert `openDetail` fired and **no** `resolveStudioLink` / URL navigation happened. |
| `__tests__/ArcSuggestPanel.test.tsx` (NEW) | 🔒 `every candidate renders its match_reason` | 3 candidates ⇒ 3 `MatchReasonChip`s. **The "don't throw the explanation away" lock.** |
| | `imports MatchReasonChip, does not re-implement it` | Static assertion / snapshot of the import. |
| | 🔒 `the premise box is SEEDED from the cached book, with NO useEffect` | Book query resolves **after** mount ⇒ the box shows `book.summary` **without** an effect. Then type ⇒ the override wins. Then clear the book ⇒ the override **still** wins (proving it is not re-seeded). |
| | 🔒 `an empty premise is OMITTED from the request body, not sent as ""` | The POST body has **no `premise` key**. |
| | `a candidate click opens its detail view in-panel` | `selectedTemplateId` is set; **no URL change**. |

**DoD evidence:** `"W4-FE6: useArcExtract.test.tsx 3 + ArcSuggestPanel.test.tsx 5 passed; extract's 409 is on the code field and it ships NO visibility control (always private); every suggest candidate renders its match_reason via the SHARED MatchReasonChip; the premise box is override-or-derive from the CACHED ['book', bookId] query (no useEffect, no second fetch) and an empty premise is OMITTED from the wire; all three hand-offs go through openDetail() — studioLinks.ts is untouched"`

---

### W4-FE7 — Import & Deconstruct (拆文) — the section

**Kind:** FS (frontend → BFF → ai-gateway → composition → worker) · **dependsOn:** `W4-BE3`, `W4-FE1` · **Size:** L

Four steps, one column, **every state rendered** (draft states ⑤ + ⑥).

#### Step 1 — Sources

| Call | Detail |
|---|---|
| `GET /v1/composition/import-sources` | → `{import_sources[]}`. List: title · `created_at` · content length. |
| `POST /v1/composition/import-sources` | `{content, title, project_id?}`. 🔴 **`content` max is 20 000 chars.** **The FE COUNTS AND BLOCKS AT 20 000 BEFORE SUBMITTING** — it does **not** let the server 422 an essay the user just pasted. See the cap rules below. |
| `DELETE /v1/composition/import-sources/{id}` | 🔴 **HARD delete — there is no restore. SAY SO** (below). |

🔴 **THE 20 000-CHAR CAP — ACCEPTED, AND THE REAL DEFECT IS THE FRAMING** (`Q-34-OQ4-20K-CAP-USEFUL`).
**OQ-4 is CLOSED.** Do **not** raise the cap. Do **not** build chunked multi-part import sources. **Do NOT
flag it at M2's POST-REVIEW** — remove it from the M2 gate and from the wave DoD.

> The spec's premise was **factually wrong**, and that dissolves the question: it assumed lifting the cap
> requires *"a chunked multi-part import source (a schema change)"*. **It does not.** `content TEXT NOT
> NULL` (`migrate.py:966`) is **already unbounded**, and the engine **already chunks + map-reduces**
> (`chunk_content`, `motif_deconstruct.py:97`; `motif_deconstruct_chunk_chars=12000`, scaled by the model
> window). There is **no storage ceiling and no window ceiling.** The cap is a **pure policy integer at ONE
> line** (`import_source.py:47`).
>
> **What the cap actually guards is COST, and it is guarding correctly.** `motif_deconstruct.py:561-567`
> issues **one paid `llm.submit_and_wait` PER CHUNK, sequentially, inside a job the spec itself states has
> no cancel.** 20k = **2 paid calls**. A real 3M-char novel = **~250 sequential paid calls the user cannot
> abort** — the exact *"paid-action defect that charges the user for nothing"* class the PO named CRITICAL.
>
> **And 20k is sufficient for the artifact being produced:** the output is an **ABSTRACT** arc template
> (threads/roster/beats/motifs), with `scrub_verbatim` actively stripping near-verbatim prose
> (`config.py:211`, max_overlap 0.50). **Volume does not improve an abstraction.** The whole-manuscript path
> **already exists elsewhere** — **BE-7a** derives a template from the user's OWN book, deterministically,
> **$0**. Import is for **EXTERNAL reference works**, where storing a full copyrighted manuscript is
> precisely what §12.6 designs against (`import_source` has **no `visibility` column by construction**).

**BUILDER INSTRUCTION — the cap is a FRAMING fix, not a limit fix:**
1. **KEEP `max_length=20000`** at `import_source.py:47`. **No BE change at all in this wave.**
2. **Frame the input as an ABSTRACT source, not a manuscript.** Field label: **"Synopsis, outline, or beat
   sheet"**. Helper text under the box, **verbatim**:
   > *"Paste a synopsis, outline, beat sheet, or a representative excerpt — not the full manuscript. The
   > deconstruct derives an abstract arc skeleton (threads, roster, beats), so a summary of the work's
   > structure gives a BETTER template than raw chapters. Max 20,000 characters."*
   Keep the live counter that blocks submit at 20 000, and **label the blocked state with the same
   guidance, not a bare limit error.**
3. Set the `arc_hint` placeholder to reinforce it: *"e.g. three-act hero's journey; the reference work's
   overall shape"*.
4. **No new defer row.** The chunked multi-part import source is a **CONSCIOUS WON'T-FIX (gate #5)** — it is
   **unneeded** (own-book manuscripts go through extract-template) and **undesirable** (copyright + an
   uncancellable ~250-call paid job). *(If real usage later shows thin templates from correctly-framed 20k
   inputs, the lever is the single integer — **but any raise MUST ship together with job cancellation.**
   That sequencing, not the schema, is the real constraint.)*

🔴 **THE COUNTER MUST COUNT CODE POINTS** (`Q-34-IMPORT-SOURCE-UX` item 1). Export **ONE** constant
`export const IMPORT_SOURCE_MAX_CHARS = 20000;` from `motif/types.ts` (**one home, one name — do NOT
re-literal it in the component**). `len` MUST be **`[...content].length`** (code points), **NOT
`content.length`** (UTF-16 units) — Python's `StringConstraints(max_length=20000)` counts **code points**,
so `.length` **over-counts every surrogate-pair char** (emoji, rare CJK) and would **block a legal
19,500-cp paste**. Counter goes `text-destructive` when `len > MAX`; the button is
`disabled={len === 0 || len > MAX}`. **The POST is NEVER fired over the cap** — no 422 round-trip.

🔴 **HARD DELETE, SAID OUT LOUD** (item 2). Use the shared `ConfirmDialog`
(`frontend/src/components/shared/ConfirmDialog.tsx:36`) with `variant="destructive"`,
`confirmLabel="Delete permanently"`, description: *"This deletes the raw source text permanently. It does
not go to Trash and cannot be restored."* (key `motif.import.delete_confirm`). **Do NOT use
`window.confirm`. Do NOT show a "Trash"/"Archive" verb anywhere in this section. Do NOT wire it to
TrashPage** — there is **no soft-delete column and no restore route** (`import_source_repo.py:96`).
`confirmationPhrase` is **not** needed (single row, low blast radius).

#### Step 2 — Configure

The MCP tool's `args` model `_ArcImportArgs` is **`ForbidExtra`** and takes **exactly**:
`{import_source_id, use_web, arc_hint, language, model_ref, model_source}`.
🔴 **THE CONFIGURE STEP MAY SEND NO OTHER FIELD.** An extra key = an arg-validation refusal.

| Control | Rule |
|---|---|
| `arc_hint` | free text |
| `language` | 🔴 **Prominent, not a footnote.** It is a **first-class dedup/embed key** — an imported `zh` work tagged `en` is a later **re-key migration**. |
| `use_web` | toggle |
| **`model_ref`** | 🔴 **REQUIRED (AT-8).** Copy **`MotifMinePanel.tsx:96-109` verbatim**: `const [model, setModel] = useState<string|null>(null)` (**NO default, NO prefill**), `<ModelRolePicker capability="chat" value={model} onChange={setModel} disabled={busy} />`, and the run button gated `disabled={!model || !token || busy}`. **There is NO warn-and-proceed path and NO "use default" affordance.** |
| **effective model + source tier** | 🔴 Directly under the picker, a line `data-testid="deconstruct-model-effective"`: *"Runs on `<alias>` — your BYOK model (source: `user_model`)"*, derived from the selected model in the shared `useUserModels` cache. Because `ModelPicker` only ever lists the caller's own BYOK models, the tier string is the **literal `user_model`** — **never render a "platform" tier**, and **never render an effective model when `model === null`** (render nothing; the button is disabled). *(SET-1..8: expose the effective value + its source tier — no silent hidden default.)* |
| **`model_source`** | 🔴 **NEVER OMIT IT.** The api layer sends `model_source: args.modelSource ?? 'user_model'` (mirroring `motif/api.ts:148-149`). **Omitting it lets the worker fall back to `settings.motif_deconstruct_model_source` (`"platform_model"`) while carrying a `user_model` UUID** — a mismatched pair that resolves to the wrong payer. |

🔴 **THE FE GATE IS ONE OF THREE LEGS. THE OTHER TWO ARE `W4-BE5`** (kill the worker's platform fallback;
reject-before-spend with a 400). **A disabled button stops the GUI; it does not stop an agent.** Ship all
three or ship none.

⚠ **X-1 is a HARD prerequisite here.** The picker's zero-models state renders `AddModelCta`
(`ModelPicker.tsx:388`), which at HEAD is a raw `<Link>` that **tears down the whole dock.**

#### Step 3 — the cost gate (AT-5)

🔴 **THE GENERIC SPINE ONLY. NO BESPOKE PER-ACTION ROUTE.**

```ts
// PROPOSE — mints a confirm token + a $ estimate. NO SPEND YET.
const res = await mcpExecute<_McpProposeResult>(
  'composition_arc_import_analyze',
  // 🔴 The MCP tool takes a SINGLE pydantic `args` model, so the bridge body must NEST
  //    the fields under `args`. A FLAT body fails arg-validation. This is verified live
  //    and commented at motif/api.ts:251-253. COPY THE NESTING. DO NOT "clean it up".
  { args: {
      import_source_id: sourceId,
      use_web: useWeb,
      arc_hint: arcHint,
      language,
      model_ref: modelRef,          // REQUIRED — AT-8
      model_source: 'user_model',
  } },
  token,
);
// → CostConfirmCard renders res.estimate.estimated_usd   (import the SHARED card; do not fork)

// CONFIRM — the token rides the QUERY; identity is the Bearer JWT.
const { job_id } = await apiJson(`/v1/composition/actions/confirm?token=${res.confirm_token}`,
                                 { method: 'POST', token });
```

🔴 **DO NOT INVENT `/actions/arc_import/estimate` OR `/actions/arc_import/confirm`.**
That exact mistake is **already shipped three times** — plan 30 §3.3:
`motifApi.conformanceRunEstimate` / `conformanceRunConfirm` **404 in production today** because someone
invented per-action paths. The generic pair is `GET /actions/preview` + `POST /actions/confirm`.

**Mirror `motifApi.minePropose` + `mineConfirm`'s PROPOSE and CONFIRM legs** (`motif/api.ts:131-176`) —
those are proven.
🔴 **DO NOT MIRROR `mineConfirm`'s POLL LEG.** It polls `compositionApi.getJob`, which **404s** on a
Work-less job. Copying it copies a live bug.

**`composition_arc_import_analyze` is ALREADY on the BFF FE-bridge allowlist** (`tools.controller.ts:24-31`).
**No BFF change. No gateway change.**

#### Step 4 — Run (the poll — **AT-11**)

```ts
// 🔴 GET /v1/composition/motif-jobs/{job_id}   ← BE-7c, the OWNER-scoped read.
//    NOT GET /v1/composition/jobs/{id}          — that route 404s on this job, ALWAYS.
//    NOT composition_get_mine_job with a project_id — the caller can never know the
//        synthetic pid.
//    🔴 The FE MUST NOT paper over a 404 with a spinner-until-timeout. An unreadable job
//       is an ERROR, and the panel says so. A spinner is exactly how that 404 would hide,
//       and the user has ALREADY PAID.
```
🔴 **THE POLL HAS EXACTLY FOUR TERMINAL OUTCOMES, AND A SPINNER RENDERS FOR ONLY ONE NON-TERMINAL CASE**
(`Q-34-AT11-NO-SPINNER-PAPER`). This is the anti-spinner contract, made mechanical:

| Outcome | Render |
|---|---|
| **HTTP non-2xx** (404/401/403/5xx) on **ANY** poll tick | 🔴 **BREAK OUT OF THE LOOP ON THE FIRST FAILURE** — **no catch-and-continue, no retry-until-budget.** ⇒ ERROR state: *"Job `<id>` could not be read (HTTP `<status>`)"* + a **Retry** button. **A poll that throws must NOT be swallowed back into the loop condition.** |
| `status === 'failed'` | ERROR state; render **`job.result.error` VERBATIM** (the worker's own message, not a generic string). |
| `status === 'completed'` | Invalidate `['composition','arc-templates']` **and** call **`openDetail(job.result.arc_template_id)`** (the field is confirmed at `motif_deconstruct.py:622-623`). 🔴 **In the TERMINAL handler — NOT a `useEffect` reacting to `status`** (CLAUDE.md: *"No useEffect for event handling"*). 🔴 **A `completed` job with NO `arc_template_id` ⇒ render an ERROR, not a checkmark** — that is a silent no-op. |
| **loop budget exhausted** while still `pending\|running` | A **DISTINCT "still running"** state (job id shown + a **"Check again"** re-poll). **Never a silent success. Never a persistent spinner.** |
| *(non-terminal)* a **200** whose status is `pending\|running` | ✅ **The ONLY case a spinner is allowed.** |

🔴 **NOT `studioLinks`** (adjudication **F**) — the panel is **already open**; the hand-off is
`openDetail(id)`, the **same** callback the Library row click and the Suggest candidate use.
The poll lives in `useDeconstructJob.ts` at the **PANEL ROOT** as a `useQuery` with `refetchInterval` —
**not an `await` loop in a `mutationFn`** (W4-FE1's hoist rule; `hidden` alone does not save an await loop).

#### Step 5 — the 402 (insufficient balance)

🔴 **BUG YOU MUST FIX WHILE HERE — ONE LINE, FIX-NOW** (`Q-34-IMPORT-SOURCE-UX` item 4).
**`isQuotaError` (`motif/api.ts:353-361`) returns FALSE on every real 402 today.** It reads `e.body?.code` /
`e.body?.reason` — **the FLAT shape**. The real 402 from `_precheck_or_402` (`actions.py:527-531`) arrives
as **`{detail:{code:'action_error', reason:'quota_exhausted'}}`**, and `api.ts:156-163` attaches that body
**verbatim**. **The existing test (`useAdoptFlow.test.tsx:85`) mocks the FLAT body and hides it.**
- **Extend the predicate** to also read **`body.detail.code` / `body.detail.reason`** **AND** to accept
  **`status === 402`** (transport-level, always true).
- Add a `contract.test.ts` case with the **REAL nested shape**.
- Then use the fixed predicate for the deep-link branch. **`MotifMinePanel`'s quota copy inherits the fix
  for free.**

**Render (INLINE in the section — not a toast, not a modal):** *"Not enough balance to run this
deconstruct."* + an **"Open Usage"** button whose `onClick` **mirrors `UsageCostStatusItem.tsx:40-43`
exactly**: `const def = getStudioPanelDef('usage'); host.openPanel('usage', { title: def ? t(def.titleKey, {defaultValue:'Usage'}) : undefined });`
*(Inline, so the user keeps their pasted source and their configure state — **a modal that unmounts the
form would lose a 20k-char paste.**)*

#### Step 6 — Running: NO CANCEL BUTTON, AND SAY WHY

🔴 While the poll is in flight render **elapsed time** + the literal line
> *"This run can't be stopped once it starts — it will finish on its own."* (key `motif.import.no_cancel`)

**Render NO cancel/stop control.** This is **not** a UX shortcut: `job_consumer.py:378-381` dispatches
`analyze_reference` **WITHOUT** the `cancel_check` callable every other op receives, so a CAS-cancel is
**silently ignored by the worker** — the job still completes **and still bills**. **A Cancel button here
would be a lying control** (`silent-success-is-a-bug`).

📌 **RAISE, DO NOT FIX HERE:** defer row **`D-COMPOSITION-MOTIF-JOB-CANCEL-NOOP`** (§11) — jobs-service
`app/contract.py` advertises **cancel-capable** caps for composition kinds, so **the generic Jobs panel WILL
render a Cancel button** for a running `analyze_reference` / `mine_motifs` job **and that cancel no-ops**.
Fix = thread `cancel_check` into `run_analyze_reference` / `run_mine_motifs` / `run_conformance_run` like
the other ops. **Gate #1 (out of scope — a different panel + 3 engine signatures).**

#### Copyright — rendered, not buried (AT-9 / §12.6 / B-3)

The section states, **in the UI** — 🔴 **the SAME string `PublishStripDialog` renders (W4-FE3 item 4e).
Define it ONCE and import it in both places:**
> *"The raw text stays private to you and is never shared. Only the derived abstract structure can be
> published — and publishing strips the source reference."*

This is not decoration: `import_source` has **no `visibility` column, by construction**
(`db/migrate.py:961-969`), and AT-9's trigger enforces the strip.

#### Files

| File | Contents |
|---|---|
| **CREATE** `frontend/src/features/composition/arc-templates/importApi.ts` | `listSources` / `createSource` / `deleteSource` (the 3 import-source calls) + `proposeDeconstruct` (mcpExecute, nested `args`) + `confirmDeconstruct` (POST `/actions/confirm?token=`) + `getMotifJob` (**BE-7c**). |
| **CREATE** `hooks/useImportSources.ts` | The sources query + create/delete mutations. **Blocks at 20 000 chars client-side.** |
| **CREATE** `hooks/useDeconstruct.ts` | propose → confirm → **poll BE-7c to terminal**. Mirrors `useMotifMine`'s shape, **minus its broken poll**. Exposes: `estimate`, `jobId`, `status`, `result`, `error`, `elapsed`. |
| **CREATE** `components/ImportDeconstructSection.tsx` | The 4 steps. ≤ ~100 lines — it composes. |
| **CREATE** `components/ImportSourceList.tsx`, `ImportSourcePasteBox.tsx`, `DeconstructConfigForm.tsx`, `DeconstructRunView.tsx` | The four sub-views. |

#### Every state (draft ⑤ + ⑥) — all must exist

no sources (empty + paste box) · **over-length paste (blocked, with the live count)** · **no model (the
`AddModelCta` empty state — X-1)** · estimate pending · **awaiting confirm (the spend has NOT happened —
say so)** · running (elapsed + *"this cannot be cancelled"*, said honestly) · completed (→ the new
template) · failed (the worker's own message) · **402 from `_precheck_or_402`** (insufficient balance →
deep-link `usage`).

#### Tests — `frontend/src/features/composition/arc-templates/__tests__/useDeconstruct.test.tsx` (NEW)

| Test | Asserts |
|---|---|
| `🔒 the propose body NESTS the fields under \`args\`` | The `mcpExecute` payload is `{args: {...}}`, **not flat**. |
| `🔒 the propose body sends NO field outside _ArcImportArgs` | The `args` keys ⊆ `{import_source_id, use_web, arc_hint, language, model_ref, model_source}`. **The ForbidExtra lock.** |
| `🔒 submit is IMPOSSIBLE with no model_ref` | `DeconstructConfigForm` with `model === null` ⇒ the run button is `disabled`. **Not** merely a warning. (AT-8 / SET-1..8.) |
| `🔒 confirm posts to the GENERIC /actions/confirm?token=, never a per-action path` | The URL matches `/v1/composition/actions/confirm?token=`. **Assert it does NOT match `/actions/arc_import/`.** This is the 3-times-shipped bug. |
| `🔒 the poll hits /motif-jobs/{id}, NOT /jobs/{id}` | The polled URL contains `motif-jobs`. **The paid-action lock.** |
| `🔒 a 404 from the poll is an ERROR, not an eternal spinner` | Poll → 404 ⇒ the hook enters `error`, the view renders an error, and polling **stops**. |
| `a failed job renders result.error verbatim` | The worker's message, not a generic string. |
| `a completed job invalidates arc-templates and opens the new template IN-PANEL` | `invalidateQueries(['composition','arc-templates'])` + **`openDetail(templateId)`**. 🔴 **Assert NO URL change and NO `resolveStudioLink` call** (adjudication **F**). |
| 🔒 `a COMPLETED job with NO arc_template_id renders an ERROR, not a checkmark` | The silent-no-op lock on the terminal handler. |
| 🔒 `an exhausted poll budget renders "still running", not a spinner and not a success` | The 4th outcome — a distinct state with a **Check again** button. |
| 🔒 `the poll STOPS on the first failure — it does not catch-and-continue` | Mock fetch → 404 ⇒ the hook lands in `error` **AND `fetch` is called exactly ONCE more than before the failure**. 🔴 **This is the anti-spinner assertion — a snapshot of the error text is not.** |
| 🔒 `a 402 uses the FIXED isQuotaError and deep-links to usage` | Reject with the **REAL nested shape** `{status:402, body:{detail:{code:'action_error', reason:'quota_exhausted'}}}` ⇒ the **"Open Usage"** button renders **AND** clicking it calls `host.openPanel('usage', …)`. **The current `isQuotaError` FAILS this — that is the point.** |
| `the running state renders "this can't be stopped" and NO cancel control` | `queryByRole('button', {name: /cancel|stop/i})` is **null**. |
| `useImportSources.test.tsx :: a 20 001-char paste is BLOCKED CLIENT-SIDE` | The submit button is disabled, the over-limit counter renders, **and the `apiJson` spy is NOT called**. 🔴 **Assert the spy-not-called leg** — a test that only checks the `disabled` attribute **cannot catch a form that still submits on Enter.** |
| `useImportSources.test.tsx :: exactly 20 000 chars is ALLOWED` | Enabled, and the spy **IS** called. |
| 🔒 `useImportSources.test.tsx :: the counter counts CODE POINTS, not UTF-16 units` | 19,500 code points of emoji/rare-CJK ⇒ **enabled** (`.length` would over-count and wrongly block it). |
| `useImportSources.test.tsx :: delete says it is permanent` | The `ConfirmDialog` copy names it as a **hard delete with no restore**; there is no "Trash"/"Archive" verb anywhere in the section. |

**DoD evidence:** `"W4-FE7: useDeconstruct.test.tsx <N> + useImportSources.test.tsx <N> passed; the args-nesting, ForbidExtra-closed-set, generic-confirm-path, motif-jobs-poll, poll-stops-on-first-failure, completed-without-template-id-is-an-error and still-running locks are green; isQuotaError FIXED to read body.detail.* (it returned FALSE on every real 402); the paste box counts CODE POINTS and blocks client-side; no cancel control is rendered and the no-cancel line is shown; the framing copy names it a synopsis/outline, not a manuscript"`

---

## 7 · W4-BE8 — agent parity (the LAST slices; the panel does not depend on them)

> **GG-2, stated plainly and in writing:** *After M1–M4 ship, a human can apply an arc template and read
> its drift from a panel; an agent asked to do the same gets a refusal.* Both tools return
> `{success:false, error:"arc engine not yet integrated…", pending_dependency}` (`server.py:4556-4564`) —
> which is **correct honest-failure behavior, not a silent no-op** — but the asymmetry is a **defect,
> tracked, not hidden.** BE-8 closes it.

🔴 **ADJUDICATED IN-WAVE, NOT PARKED** (`Q-34-GG2-INVERSE-GAP`). **The wave MAY NOT CLOSE with either tool
returning `pending_dependency`** — that is **DoD #9**. Sequenced **after** the panel because the panel has
**zero** dependency on it (spec 34 §0), **not** because it is optional.

🔴 **AND THE COST BASIS WAS FALSE.** Spec 34 §7/§10 assert *"`apply_arc_to_spec` is genuinely unwritten ⇒
**M** (a genuine engine: rescale placements onto chapters, bind the roster once, write pacing into scene
tension, emit the `motif_application` ledger — onto `structure_node`)"*. **That engine EXISTS:**
`services/composition-service/app/engine/arc_apply.py:325` — `async def arc_apply(template, structure_node,
*, created_by, structure_repo, outline_repo, applications_repo, resolve_motifs, cast_index, cast_names,
roster_bindings, k_ceiling, high_threshold, min_scenes, max_scenes, replace)`, docstring *"Apply an arc
`template` onto an existing spec `structure_node` — the template → spec snapshot (BA3)"*. It is
**integration-tested** (`test_arc_apply_roundtrip.py:167,295-301`) and has **ZERO production callers**.
The MCP tool does `getattr(_engine, "apply_arc_to_spec", None)` — **a name that is never defined anywhere in
the repo** — so `_pending_engine` is **not a parallel-build interim state, it is a PERMANENT dead seam
caused by a name mismatch.** **Proof the seam has already rotted:** `server.py:4651-4654` keeps the same
`_pending_engine` fallback for `extract_template_from_arc`, **which shipped** at `arc_apply.py:652` — a dead
branch nobody removed.

⇒ **BE-8 is TWO SEAM WRAPPERS + a deletion. S + S, not S + M.** Zero new engine.

**Also amend, in this slice's SESSION step:** spec 34 §7 (delete the *"still stubbed → BE-8"* cells and the
GG-2 admission at `:264-266`), §10 M5 (drop the word **PARKED**), §11 (add DoD #9), and plan 30 §5.2's BE-8
row. **`D-ARC-APPLY-MCP-WRAPPER` is CLEARED by M5, not re-scoped again.**

### W4-BE8a — `composition_arc_template_drift` (S — DELEGATE, do not write a second engine)

**Kind:** BE · **dependsOn:** `W4-FE5` · **Size:** S

The tool is a `_pending_engine` stub because `getattr(app.engine.arc_conformance, "build_template_drift")`
returns `None` (`server.py:4698-4700`). The **orchestrator the REST route already uses** is
`compute_arc_report(..., by_structure=False)` (`engine/arc_conformance_orchestrate.py:38`).

**Files**

1. **EDIT `services/composition-service/app/engine/arc_conformance.py`** — add:
   ```python
   async def build_template_drift(*, reader, mrepo, knowledge, user_id, project_id,
                                  book_id, arc_node, arc_template, deep=False,
                                  model_ref=None, model_source=None) -> dict:
       """BE-8a — the agent's drift, DELEGATED to the SAME orchestrator the REST route
       already uses (`compute_arc_report(..., by_structure=False)`). Deliberately NOT a
       second engine: two engines answering one question is the bug this slice exists to
       prevent — the M5 parity assertion below would catch it, and we would rather it
       never happen."""
       from app.engine.arc_conformance_orchestrate import compute_arc_report
       return await compute_arc_report(
           reader=reader, mrepo=mrepo, knowledge=knowledge,
           user_id=user_id, project_id=project_id, book_id=book_id,
           arc=arc_template, by_structure=False,
           deep=deep, model_ref=model_ref, model_source=model_source,
       )
   ```
   ⚠ Match `compute_arc_report`'s **actual** signature — open
   `engine/arc_conformance_orchestrate.py:38` and copy it. Do not guess.
2. **EDIT `services/composition-service/app/mcp/server.py:4698`** — the `getattr` seam now resolves; wire
   the handler to pass the arc's resolved template (mirroring the REST branch at `conformance.py:390-404`:
   resolve `node.arc_template_id` → 422-equivalent `{success:false, outcome:'no_provenance'}` when null →
   `arc_repo.get_visible` → uniform deny when gone).

**Tests — `services/composition-service/tests/unit/test_arc_template_drift_tool.py` (NEW)**

| Test | Asserts |
|---|---|
| `the tool no longer returns pending_dependency` | 🔒 The un-stub lock. |
| `an arc with no provenance returns the no-provenance outcome (not an error)` | Mirrors the REST 422. |
| `🔒 the tool's report EQUALS the REST route's report for the same arc` | **THE PARITY ASSERTION.** Same fixtures through both paths ⇒ **identical dicts**. *A differing answer means two engines, which is the bug BE-8 exists to prevent.* |

### W4-BE8b — `composition_arc_apply` → `apply_arc_to_spec` (**S** — a SEAM WRAPPER over the SHIPPED engine)

**Kind:** BE · **dependsOn:** `W4-BE8a`, `W4-BE4` · **Size:** **S** *(was M — the engine already exists)*

🔴 **DO NOT WRITE A FOURTH ARC ENGINE.** `arc_apply()` (`arc_apply.py:325`) **is** the engine. Write the
**wrapper**, mirroring `extract_template_from_arc` (`:652`) **verbatim in shape**:

```python
async def apply_arc_to_spec(pool, *, book_id, project_id, arc_template, structure_node_id,
                            roster_bindings, replace=False, created_by) -> dict:
```
1. `node = await StructureRepo(pool).get(structure_node_id)`; **`if node is None or node.book_id != book_id`
   ⇒ the H13 uniform deny** (tenancy: **gate on the ROW's book, not the arg**).
2. `cast = await _cast_roster(get_kal_client(), book_id, created_by)`; build
   `cast_index = {name.casefold(): entity_id}` and `cast_names = {entity_id: name}`. 🔴 **REUSE
   `app.routers.plan._cast_roster` (`plan.py:167`) + `_resolve_plan_motifs` (`:1239`) via a
   FUNCTION-LOCAL import** (precedent: `motif_conformance_run.py` imports `ConformanceTraceReader` from
   `app.routers.conformance`). **Reusing them is what keeps the agent's cast/motif resolution IDENTICAL to
   the panel's** — a forked resolver is the "two engines" bug BE-8 exists to prevent.
3. `result = await arc_apply(arc_template, node, created_by=created_by, structure_repo=…, outline_repo=…,
   applications_repo=…, resolve_motifs=lambda pl: _resolve_plan_motifs(MotifRepo(pool), created_by, pl),
   cast_index=…, cast_names=…, roster_bindings=roster_bindings, k_ceiling=settings.compose_diverge_k,
   high_threshold=settings.plan_high_tension_threshold, min_scenes=settings.plan_min_scenes_per_chapter,
   max_scenes=settings.plan_max_scenes_per_chapter, replace=replace)`
   — **the assembly is copied verbatim from the human's route `plan.py:1260-1400` (`materialize_arc`)**,
   the acknowledged assembly template. **This is not new work.**
4. 🔴 **The provenance stamp REUSES `stamp_arc_provenance` (W4-BE4).** **Exactly one writer of
   `structure_node.arc_template_id`, forever.** Do **not** write a second stamp here.
5. **Map the engine's two exceptions to tool-shaped dicts — never a 500, never a silent success:**
   - `ArcApplyError` (`:233`) → `{"success": False, "error": exc.message, **exc.detail}` (carries
     `NO_MEMBER_CHAPTERS` / `NO_MATERIALIZABLE_PLACEMENTS` + `unresolved_placements`);
   - `ArcApplyConflict` (`:243`) → `{"success": False, "outcome": "applied_conflict",
     "chapter_ids": exc.chapter_ids, "error": "member chapters already have scenes — resend with replace=true"}`.
6. Success → `{"success": True, "outcome": "applied", **dataclasses.asdict(result)}` — **surface
   `unbound_roster_keys`, `unresolved_placements` and `drop_merge_report`** (§12.6: **a folded-away motif is
   NEVER silent**).

**SERVER EDIT (required — the current stub's arg list CANNOT call the engine):** in `mcp/server.py`,
`_ArcApplyArgs` (`:4570`) must **ADD `structure_node_id: str`** — `arc_apply` applies onto an **existing**
arc's member chapters (`arc_apply.py:365` raises `NO_MEMBER_CHAPTERS` otherwise), and
`project_id + arc_template_id` **cannot name one**. The agent's flow is
`composition_arc_create` (with `arc_template_id`) → `composition_arc_assign_chapters` (`server.py:4514`) →
`composition_arc_apply`. 🔴 **DROP `idempotency_key` from `_ArcApplyArgs`** — the engine has **no**
idempotency path; **`replace=True` IS the re-apply path**, and an accepted-but-ignored arg **is a silent
no-op**.
*(Default, veto-able: the tool takes an EXISTING `structure_node_id` rather than minting the arc itself —
minting would fork a second "create arc from template" writer against W4-BE4's stamp, the exact duplication
BE-8 forbids.)*

### W4-BE8c — 🔴 KILL THE SEAM (XS)

**Delete `_pending_engine` (`server.py:4556-4564`) and ALL THREE `getattr` guards** (`:4602-4605`,
`:4651-4654`, `:4698-4700`). Call the engine symbols **directly**. **Rationale:** with all three symbols
present, the guard no longer buys honesty — it converts a future **rename** from a loud `AttributeError`
into a `{"success": false, "pending_dependency": …}` **that reads as "not built yet."** **A refusal that
outlives its dependency is `silent-success-is-a-bug` wearing a different hat.**

**Tests — `services/composition-service/tests/integration/db/test_arc_apply_parity.py` (NEW)**
🔴 **This file touches a real DB ⇒ it MUST carry `pytestmark = pytest.mark.xdist_group("pg")`** or
parallel `-n auto` workers interleave and the counts lie.

| Test | Asserts |
|---|---|
| 🔒 `THE PARITY ASSERTION — the tool's drift report EQUALS the REST route's` | `await build_template_drift(pool, arc_node=arc, user_id=u)` **== dict-equal to** `await compute_arc_report(..., arc=template, by_structure=False)` called with the REST route's **exact arg set**. **Field-by-field, not "both returned 200."** 🔴 **A differing answer means two engines — the bug BE-8 exists to prevent.** |
| 🔒 `drift sees an AGENT-applied arc` | `ConformanceTraceReader.arc_bindings(project_id, template.id)` (the **ANNOTATION-keyed** reader drift uses) returns the **same row count** as `arc_bindings_by_structure(project_id, arc.id)`. This is the load-bearing fact (guaranteed by `arc_apply.py:389` → `arc_materialize.py:159-162`). |
| `apply_arc_to_spec stamps provenance VIA stamp_arc_provenance` | `arc_template_id` + `template_version` set — **by the same function W4-BE4 uses** (assert the call, not a re-implementation). |
| `it writes the motif_application ledger` | Row count > 0. |
| `a structure_node from ANOTHER book ⇒ uniform deny` | Tenancy, gated on the **ROW's** book. |
| `no member chapters ⇒ NO_MEMBER_CHAPTERS, not a 500` | The `ArcApplyError` map. |
| `a re-apply WITHOUT replace ⇒ applied_conflict carrying chapter_ids` | The `ArcApplyConflict` map. |
| `drift on an arc with arc_template_id IS NULL ⇒ available:false` | **Never `pending_dependency`.** |
| 🔒 `NO tool returns pending_dependency` | **A repo-wide grep assertion: `pending_dependency` no longer appears in `services/composition-service/app/mcp/server.py`.** The mechanical guard that DoD #9 cannot regress. |

⚠ **DEFER ESCAPE HATCH (declared up front, per the deferral policy):** if the wrapper turns out to need a
**schema change** (it should not — `structure_node` already carries `arc_template_id` / `template_version`),
**write `D-ARC-APPLY-TXN-STAMP` (gate #2) and CONTINUE to the wave close**, keeping the tool working against
an explicit `structure_node_id`. **Do NOT stop and ask.** 🔴 **W4-BE8a is NOT deferrable under ANY gate** —
a ~15-line delegate to a shipped orchestrator **costs less than the defer row that would track it.**

**DoD evidence (BE-8):** `"W4-BE8: composition suite <N> passed; apply_arc_to_spec is a WRAPPER over the SHIPPED arc_apply() engine (S, not M — spec 34's 'genuinely unwritten' was false); _ArcApplyArgs gains structure_node_id and DROPS the no-op idempotency_key; _pending_engine and all 3 getattr guards DELETED; grep 'pending_dependency' in mcp/server.py → ZERO (DoD #9); the PARITY test asserts the tool's drift report == the REST route's FIELD BY FIELD; the annotation-keyed reader sees an agent-applied arc"`

---

## 8 · SLICE ORDER + DEPENDENCY GRAPH

```
W4-BE0 (🔴 CONTRACT-FIRST: freeze the OpenAPI) ──┬──▶ W4-BE1 (extract route)
                                                 └──▶ W4-BE2 (suggest route + projections.py/grant_deps.py)

W4-BE3 (🔴 motif-jobs, RE-SCOPED to M: migration + create_unbound + spend-after-durability
         + the gate cascade + the read route)   ← CONDITIONAL: skip ONLY if pre-flight cmd 4a AND 4b
                                                  are BOTH green (Wave 3 built it properly)
W4-BE4 (🔴 the SERVER-SIDE provenance stamp — stamp_arc_provenance, the ONE writer)
W4-BE5 (🔴 AT-8: kill the worker's platform-model fallback + reject-before-spend)

W4-FE1 (panel + GG-8 + the params seam + the GG-4 & DOCK-2 guards)
   ├──▶ W4-FE2 (catalog)
   └──▶ W4-FE3 (CRUD/adopt/412-reconcile/publish-strip) ──▶ W4-FE4 (materialize + ASSERT the stamp)
                                                                │
                                                                └──▶ W4-FE5 (Used by + DRIFT)

W4-BE1 + W4-BE2 + W4-FE3 ──────────────────────────────────────────▶ W4-FE6 (extract + suggest UI)
W4-BE3 + W4-BE5 + W4-FE1 ──────────────────────────────────────────▶ W4-FE7 (拆文)
                                                                │
                                                                ▼
                                          W4-BE8a ──▶ W4-BE8b ──▶ W4-BE8c   (agent parity, LAST)
                                                                │
                                                                ▼
                                            W4-CLOSE (review-impl + SESSION + commit)
```

**One slice = one commit.** Never `git add -A` — enumerate the files
(⚠ `git commit -- <path>` commits the **WORKING TREE**, not the index; and the index may already carry a
concurrent session's pre-staged changes — check `git diff --cached --name-only` before every commit).

---

## 9 · WAVE DEFINITION OF DONE

A literal checklist. **Every box, in order. No box is optional.**

- [ ] **1 · All four registration guards GREEN**, and the three counts moved **N → N+1 in lockstep**:
  ```bash
  cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
  cd frontend && npx vitest run \
    src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
    src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
    src/features/studio/palette/__tests__/useStudioCommands.test.ts \
    src/features/chat/nav/__tests__/frontendToolContract.test.ts
  ```
  ⚠ **Assert the DELTA + the SET equality (py enum == contract enum == `OPENABLE_STUDIO_PANELS`).
  NEVER a literal, and do not write a target number down at all.** A count that moves in only two of three
  is exactly the drift the guards exist to catch.
  🔴 **AND RE-RUN `test_frontend_tools_contract.py` WITHOUT `WRITE_FRONTEND_CONTRACT` and paste the green
  output** — the regen run **`pytest.skip`s** (`:138`) and therefore **asserts nothing**. A builder who runs
  only the regen and sees green has proven nothing.

- [ ] **2 · `panelCatalogContract.test.ts`** asserts `arc-templates` has a `category` **that is a member of
  `CATEGORY_ORDER`** (X-2's assertion) **and** a non-empty `guideBodyKey` (X-3's).

- [ ] **3 · The full composition-service suite green** (parallel, per CLAUDE.md):
  ```bash
  cd services/composition-service && python -m pytest tests -q -n auto --dist loadgroup
  ```
  🔴 **Every NEW test touching a real DB/port carries `pytestmark = pytest.mark.xdist_group("pg")`.** Four
  new real-DB files this wave: `test_arc_materialize_stamp.py` (W4-BE4), `test_motif_job_lifecycle.py`
  (W4-BE3), `test_arc_apply_parity.py` (W4-BE8), and any BE-7a laundering test that seeds a real row.

- [ ] **4 · The full frontend suite green:** `cd frontend && npx vitest run`.

- [ ] **5 · The unit/component tests for the wave's named hazards all exist and are green:**
  - the **412 reconcile** path — 🔴 asserting **the user's placements SURVIVE**, not merely that
    `saveError === 'conflict'` (that passes on the broken code)
  - the **write chain** (no self-412) and the **entity binding** (A's late resolution does not poison B)
  - the **three drift server empty states** (three *different* renders, none reaching `MotifStateBoundary`)
    **and** the **four Work-gate states** (four different testids; `candidates` ⇒ **ENABLED**)
  - the **20 000-char** client-side block (**the `apiJson` spy is NOT called**) + the **code-point** counter
  - the **required-model gate** (a Deconstruct with no `model_ref` is **impossible to submit**, not merely
    warned) — **plus W4-BE5's two BE legs** (the platform ref is unreachable; the confirm 400s before spend)
  - the **five materialize error codes** (each asserting **its PAYLOAD**, not just its testid)
  - 🔴 **the stamp assertion** — `chapters_assigned: 0` or a missing `structure_node_id` renders an
    **ERROR**, not a checkmark. *(A test that only asserts "the call was made" cannot catch a silent no-op:
    `inject-at-chokepoint-proves-nothing`.)*
  - 🔴 **the single-handler lock** — `matchEffectHandlers('composition_arc_update').length === 1` (and for
    `_apply` / `_extract_template`) **+ the nested-envelope unwrap test**
  - 🔴 **the poll-survives-a-tab-switch lock** — the **fetch count kept increasing** while the view was
    hidden (a `hidden`-className assertion is a rubber-stamp)
  - 🔴 **the no-second-writer grep** — zero `assign-chapters` / `POST …/arcs` literals under
    `features/composition/**`, and **no `createArc` in `plan-hub/api.ts`**
  - 🔴 **`legacyRetirementGuard.test.ts`** (GG-4) and **`sharedComponentsSingleHome.test.ts`** (DOCK-2)

- [ ] **5b · 🔴 THE 17 LOCALES — RUN IT ONCE, AT END OF WAVE, AND PROVE IT** (`Q-34-I18N-17-LOCALES`).
  **NOTHING tests studio-locale parity** — the only i18n parity tests are
  `campaignsParity`/`chatParity`/`compositionWorldParity`/`onboardingParity`; **there is no `studioParity`
  test**, and `panelCatalogContract.test.ts` **never asserts i18n keys at all**. **Missing locale keys
  therefore RED ZERO TESTS and silently fall back to English at runtime. This step has no mechanical guard
  and WILL be forgotten unless it is a literal checked box.**
  ```bash
  python scripts/i18n_translate.py --ns studio        # 🔴 WITHOUT --force
  python scripts/i18n_translate.py --check vi/studio.json
  python scripts/i18n_translate.py --check ar/studio.json     # one non-Latin script
  ```
  🔴 **NEVER `--force`.** `plan_namespace()` (`i18n_translate.py:339-357`) is **GAP-FILL** — it carries
  forward every existing key that is present/non-empty/placeholder-faithful and translates **only the
  missing ones**, so a bare run adds **just the new keys × 17 locales** and touches nothing else.
  `--force` (`:396`) **re-translates the ENTIRE studio namespace across all 17 languages**: a massive
  churned diff **plus real risk of regressing good existing translations.**
  **Requires LM Studio on :1234 with `google/gemma-4-26b-a4b-qat`** (`i18n_translate.py:44-45`).
  **PROOF (paste it):** both `--check`s pass **AND** `grep` the new keys in **all 18** locale files.
  📌 **REUSE `motif.arc.*` from the `composition` namespace** — 8 keys already exist
  (`motif.arc.mobileNotice/.place/.chapters/.moveLeft/.moveRight/.grow/.shrink/.remove`). Read them with
  `useTranslation('composition')`. **Do NOT copy/re-key them into `studio.json`** — that forks a live
  string set.

- [ ] **6 · Backend tests for BE-7a / BE-7b / BE-7c:** grant gating (VIEW derived from the **ROW**), the
  H13 uniform 404 (**assert the two bodies are EQUAL** — that equality *is* the no-oracle guarantee), the
  409 duplicate-code map. **BE-7c specifically:** a job owned by user A is a **uniform 404** for user B,
  **and** a `mine_motifs` / `analyze_reference` job with a **synthetic `project_id`** is readable **by its
  owner** — the exact case both existing readers fail.

- [ ] **7 · 🔴 LIVE BROWSER SMOKE — MANDATORY. Not a curl script. Not a unit suite.**
  `agent-gui-loop-needs-live-browser-smoke-not-raw-stream`. **Specs 24 (H8.2) and 15a both NAMED this DoD
  and SKIPPED it. This one does not.**

  **CREATE `frontend/tests/e2e/specs/studio-arc-templates.spec.ts`.** Precedents:
  `studio-compose.spec.ts` / `studio-palette.spec.ts`.
  **Target:** the **baked `:5174` nginx build** *(rebuild the image first — stale images are false-green:
  `live-smoke-rebuild-stale-images-first`)*, **or** `vite dev :5199`. **A host `vite dev` SHADOWS :5174 —
  know which one you are driving.**
  **Account:** `claude-test@loreweave.dev` / `Claude@Test2026`.
  **Model:** a **local lm_studio chat model** (e.g. Qwen2.5 7B Instruct) so the priced run is **$0**.
  Resolve the `model_ref` live — it is the **`user_model_id` UUID**:
  ```sql
  SELECT user_model_id, alias, capability_flags FROM user_models
   WHERE owner_user_id='019d5e3c-7cc5-7e6a-8b27-1344e148bf7c' AND is_active;
  ```
  ⚠ `user_default_models` is **empty** for this account — anything resolving "the default model for
  capability X" gets **nothing**. **Pass an explicit `model_ref`.**
  **Driving technique (repo memories):** Playwright refs go stale in dockview ⇒ drive via
  **`page.evaluate` + `data-testid`**; use **`page.mouse`** (trusted events) for any drag — synthetic
  drag events do not work on d3/dockview.

  🔴 **THE HARNESS ALREADY EXISTS — there is nothing to escalate and nothing to defer**
  (`Q-34-LIVE-BROWSER-SMOKE`): `frontend/playwright.config.ts:3`,
  `tests/e2e/helpers/frontendToolInject.ts:113` (`installFrontendToolSuspend`),
  `tests/e2e/specs/frontend-tools-liveness.spec.ts:1-20` (the exact precedent, incl. the BYOK `MODEL_REF`
  default), `tests/e2e/pages/StudioPage.ts:24` (`studio-dock`).

  **FOUR tests, in this exact shape:**

  1. **AT-SMOKE-1 (M1 · the dock tab appears). LLM-free.**
     `loginViaUI(page)` → `new StudioPage(page).goto(bookId)` →
     **`installFrontendToolSuspend(page, { tool: 'ui_open_studio_panel', args: { panel_id: 'arc-templates' } })`**
     and send a chat turn. 🔴 **DECISION (take the default — it is the sanctioned precedent): do NOT wait
     for a local model to CHOOSE to emit the tool.** That choice is **non-deterministic**
     (`frontendToolInject.ts:11-20`). **The trigger is canned; the FE executor / resolver / dock mount
     under test is 100% real**, exactly as `frontend-tools-liveness.spec.ts` proves G4 today.
     **Assert:** the `arc-templates` panel body is visible inside `getByTestId('studio-dock')`, **AND** the
     resume POST to `/tool-results` carries a **success** payload — **not `result.error`**. *(A silent
     no-op returns `ok` shaped as an error — assert the BODY, per the Frontend-Tool Contract's "resolver
     never silently no-ops".)*
  2. **AT-SMOKE-2 (M2 · the priced 拆文 run). Tag `@live-llm`.**
     Paste reference text → pick a **local lm_studio BYOK** model in the `ModelPicker` (`model_ref` from
     `PLAYWRIGHT_MODEL_REF`; the test account's gemma-4-26b `user_model` is the default, as in
     `frontend-tools-liveness.spec.ts:20`) → **Propose** ⇒ assert the cost card renders a **numeric,
     non-zero** estimate (**not `—`, not `0`**) → **Confirm** →
     `await expect.poll(pollJob, { timeout: 300_000, intervals: [2000] }).toBe('completed')` against the
     **owner-scoped job read (BE-7c)**. 🔴 **The assertion is a TERMINAL status — NEVER "it started."**
     🔴 **Before `W0-BE1` this run 500s AT THE CONFIRM and enqueues nothing** — there is no `job_id`, so
     **the poll is never even reached** (it does not "404 forever"; that describes a code path that never
     executes). **Nobody is charged** — but the confirm token is burnt and a spinner would hide the whole
     thing. ⇒ **Assert TWO things, in this order: (1) the confirm returns 200 + a real `job_id`; (2) the
     poll reaches a TERMINAL status.** Then assert the new template row is visible in the Library tab.
  3. **AT-SMOKE-3 (M4 · drift proves the stamp landed). LLM-free.**
     🔴 **Seed the template through M1's CRUD REST route — do NOT chain it off the LLM job** (that would
     make the M4 assertion hostage to lm_studio). Open it → Apply-preview → **Materialize** → open **Drift**
     ⇒ assert a report renders **AND the DOM does NOT contain `NO_TEMPLATE_PROVENANCE`** (that string is
     **the tell that the provenance stamp silently no-op'd**) and is **not a spinner and not a zero-state**.
  4. **AT-SMOKE-4 (X-1 regression guard — no dock teardown). LLM-free.**
     `page.route()` the user-models list to return `[]` so `ModelPicker` renders its zero-model empty state
     (`ModelPicker.tsx:388` → `AddModelCta`), click the CTA, then assert `getByTestId('studio-dock')` is
     **still attached**, the `arc-templates` tab still exists, the **Providers** tab is active, and
     **`page.url()` is UNCHANGED** (no route hop).
     **Re-assert `studio-dock` is attached at the END of every one of the four tests.**

  🔴 **INFRA POLICY — THE PART THAT STOPS THIS BEING SKIPPED LIKE SPECS 24 AND 15a.** SMOKE-1, -3 and -4
  need **no LLM** and **MUST run green at every wave close and in CI**. SMOKE-2 is `@live-llm`; it may
  `test.skip()` **only** when `PLAYWRIGHT_LIVE_LLM=0` is **explicitly** set — **and in that case THE WAVE
  DOES NOT CLOSE.** M2's DoD is satisfied **only** by pasting the real run's output into the VERIFY
  evidence, which also discharges DoD #8's cross-service token:
  ```
  live smoke: 拆文 arc-import job <job_id> → completed on lm_studio gemma-4-26b ($0),
  arc_template <id> rendered in the Library tab (FE→BFF→ai-gateway→composition→worker)
  ```
  **A green unit suite, a curl script, or "should work" satisfies none of this.**

- [ ] **8 · A cross-service live-smoke token in the VERIFY evidence.** BE-7a/BE-7b are composition-only,
  but the deconstruct crosses **frontend → BFF → ai-gateway → composition → worker**. The evidence string
  carries `live smoke: <one-liner>` — or an explicit `LIVE-SMOKE deferred to D-<NAME>-LIVE-SMOKE` row, or
  `live infra unavailable: <reason>`.

- [ ] **8b · 🔴 GG-4 DISCHARGED** (`Q-34-GG4-CHAPTEREDITORPAGE` item 4): `arc-templates` is present in
  `catalog.ts`'s `STUDIO_PANELS` + the `ui_open_studio_panel` enum + the palette (bare-id openable per
  AT-1); **`legacyRetirementGuard.test.ts` is GREEN**. **Once that passes, the legacy door is no longer
  load-bearing and Wave 6 / 00C Q-6 may remove it — the GUARD, not a prose note, is what PERMITS that.**

- [ ] **8c · 🔴 DoD #9 (GG-2 CLOSED): ZERO `pending_dependency` responses remain in composition's MCP
  surface.** `grep -rn "pending_dependency" services/composition-service/app/mcp/server.py` → **empty**.
  An agent-driven `composition_arc_apply` + `composition_arc_template_drift` on the same arc produce output
  **equal, field-by-field, to what the panel renders from the REST routes** (the parity test).
  **The wave MAY NOT CLOSE with either tool returning `pending_dependency`.**

- [ ] **9 · 🔴 `/review-impl` RUN ON THE WAVE'S DIFF, AND EVERY BUG IT FINDS FIXED BEFORE THE WAVE CLOSES.**
  This is a literal step, not a suggestion (the PO's policy §0.2). Load-bearing surfaces it **must** be
  pointed at: **W4-BE3's owner gate + the nullability migration** (a tenancy boundary + a schema relax),
  **W4-BE4's stamp** (a silent-no-op class **and** the single-writer invariant), the **cost gate**
  (a paid action), and **W4-BE5** (a spend-causing default).

- [ ] **10 · `docs/sessions/SESSION_HANDOFF.md` updated** — the ▶ NEXT SESSION block; deferred rows moved
  **exactly as adjudicated** (`Q-34-DEFERRED-ROW-MOVES` — every claim in §11.7 verified, with ONE trap):
  - 🔴 **`SESSION_HANDOFF.md:3378` is a COMBINED row** — *"**D-ARC-TEMPLATE-CRUD-GUI / D-MOTIF-LIBRARY-CRUD-GUI**"*.
    **DO NOT DELETE THE LINE — SPLIT IT.**
    - Move the **ARC** half to "Recently cleared": *"~~D-ARC-TEMPLATE-CRUD-GUI~~ — CLEARED 2026-07-xx by
      spec 34 M1–M4 (arc-templates panel: browse/CRUD/adopt/suggest/extract/apply→materialize/drift; the
      work→arc_template link is stamped server-side by W4-BE4)."*
    - The **MOTIF** half is **owned by spec 33** (`33_motif_studio.md:806`). If Wave 3 landed, 33's own
      SESSION clears it; **if it has NOT, re-write it as a STANDALONE surviving row.** 🔴 **Clearing the arc
      half must never silently drop the motif half.**
  - 🔴 **`SESSION_HANDOFF.md:428` — `D-ARC-APPLY-MCP-WRAPPER`: CLEARED by W4-BE8** (not re-scoped again).
    Its text carries a **FALSE** clause — *"and a `build_template_drift` engine fn"* is **not** missing
    work; the orchestrator ships and BE-8a is a **delegate**. And *"`apply_arc_to_spec` is genuinely
    unwritten"* is **false** — the engine is `arc_apply()`. Say so when you clear it.
  - 🔴 **NEW ROWS: verify, don't assume, before minting anything.**
    - `D-ARC-CONFORMANCE-FE-ARGS-DRIFT` ≡ spec 33's **M-BUG-4**. Verify:
      `grep -n "arc_template_id" frontend/src/features/composition/motif/api.ts` → must return **nothing**
      for the two conformance calls. *(`ArcMaterializeAction`'s `arc_template_id` at `arcTypes.ts:23` is
      **CORRECT** and must remain — that route really does take it.)* If 3c did not fix it, **it is a 33
      regression: reopen it against 33 — do not mint a 34 row.**
    - `D-MOTIF-JOB-POLL-404` ≡ spec 33's **BE-7c**. Verify: `grep -rn "motif-jobs" services/ frontend/src`
      → must hit a route **and** an FE consumer. If 3a did not build it, **reopen against 33 — do not
      re-file.**
  - The new rows in §11 added **as they are raised**, not at the end.

- [ ] **10b · 🔴 THE SPEC EDITS (doc-only, in the SESSION commit)** — a spec that contradicts itself
  re-seeds the stale row it withdrew:
  - `34_arc_templates_and_deconstruct.md:349` — OQ-5's disposition still says *"New deferred row:
    `D-ARC-CONFORMANCE-FE-ARGS-DRIFT`"* while `:335` (§11 DoD-7) **withdraws** it. **§11 wins.** Rewrite
    OQ-5's disposition to: *"Owned by spec 33 as **M-BUG-4**, fixed in 3c. **No deferred row** — see §11.7."*
  - `design-drafts/screens/studio/screen-arc-templates.html:1309` — **the third copy of the stale name.**
    Replace `<code>D-ARC-CONFORMANCE-FE-ARGS-DRIFT</code>` with *"spec 33's M-BUG-4 (fixed in 3c)"*.
    **Left there, it re-seeds the duplicate row.**
  - `34_…:3` — the header still says *"side_effects = 3 — **3** new REST routes"*. Replace with
    *"side_effects = 3 — **2** new REST routes (BE-7a, BE-7b) + the frontend-tools `panel_id` contract
    (BE-7c ships in Wave 3a), no schema change"*. §5 of the same file **already** says *"BUILT IN WAVE 3,
    NOT HERE"* — this makes the header agree with its own body.
  - `34_…:348` — **OQ-4 is CLOSED** (the 20k cap is accepted). **Remove it from the M2 gate and the M2 DoD.**
  - §7 / §10 M5 / §11 — drop **PARKED**, delete the *"still stubbed → BE-8"* cells and the GG-2 admission
    (`:264-266`), and **add DoD #9**.
  - §8 — *"Adopt is quota-bearing"* → **the publish flip is; adopt is free and private.**
  - §OQ-3 — record that `composition_work.settings JSONB` **already exists**, so Wave 6's dedicated
    `premise` field needs **no migration**.
  - `34_…:24` — *"materialize writes … **no `structure_node` at all**"* is **FALSE** (`outline.py:435-446`).
    Fix it, or the next reader re-derives the orphan bug.

- [ ] **11 · Plan 30 is AMENDED, not silently contradicted.** 🔴 **~95% of this is ALREADY DONE at HEAD**
  (`Q-34-AMEND-PLAN-30` — §5.2 `G-IMPORT-DECONSTRUCT` `:264`, §3.3 `:131`, BE-7c `:301`, BE-8 `:302`, and
  the Wave-4 BE prereqs `:403-406` all carry their 2026-07-13 corrections in place). **DO NOT RE-WRITE
  THEM.** **Exactly TWO edits remain:**
  - **`:114`** (the §3 inventory cell) still reads *"**3 FE calls with NO backend route (404 at runtime)**"*.
    Replace with: *"**4 FE calls that 404 at runtime** (3 with no backend route + 1 whose route exists but
    always 404s on a synthetic `project_id` — §3.3)"*. **It is the last cell still counting three.**
  - **`:635`** (§8.1 Tier-W prose) reads *"(The 3 live 404s in §3.3 are exactly this mistake, already
    shipped.)"* 🔴 **This must NOT simply become "4"** — the 4th 404 is a **gate/enqueue** bug, not the
    per-action-route mistake §8.1 describes. Rewrite as: *"(3 of the 4 live 404s in §3.3 are exactly this
    mistake, already shipped; the 4th is the synthetic-`project_id` job-gate bug, not a routing one.)"*
  - 📌 **Leave §5.2's `G-CONFORMANCE-TRACE` row at "3 live FE calls 404"** — its three **are** the
    conformance-trace three. The 4th belongs to motif-mine / 拆文 and is correctly owned by
    `G-IMPORT-DECONSTRUCT` + BE-7c. **Leaving it at three is correct, not stale.**
  - Also amend plan 30 §5.2's **BE-8** row + `:813-815`'s defer-row map to say BE-8 is **in-wave** and
    `D-ARC-APPLY-MCP-WRAPPER` is **CLEARED**, not re-scoped.

- [ ] **12 · The wave committed.** Files enumerated, never `git add -A` (shared checkout, three live
  tracks on this branch). The SESSION update lands **in the same commit** as the code.

- [ ] **13 · RETRO** — `add_lesson` to ContextHub (`project_id = mmo-rpg-zone-map-design-non-human-in-loop`)
  for anything non-obvious. Candidates already visible: *"a shipped route with zero FE consumers is
  invisible to an audit that greps the FE"*; *"an `assigned: N` count over a predicate-matched UPDATE is a
  silent-success surface."*

---

## 10 · THE OPEN QUESTIONS — RESOLVED. Bake these in; do not re-open them.

| OQ | Question | **THE INSTRUCTION** |
|---|---|---|
| **OQ-1** 🔴 | Should AT-6 stamp provenance FE-side (2 calls) or server-side inside `materialize` (1 transaction)? | 🔴 **ADJUDICATED: SERVER-SIDE — answer (b), OVERTURNING the spec's (a)** (`Q-34-OQ1-STAMP-SITE`). **The code falsifies (a)'s premise:** the stamp does **NOT** touch the shared 130-line commit path — `materialize_arc` is its own handler, the decompose-shared primitive is `outline.commit_decomposed_tree(...)`, and the stamp is a **~5-line ADDITIVE block AFTER it returns**. It is **cheaper than the FE version** (which needs 2 calls + a new `plan-hub` export + a debt row + a mandated later delete) and it **removes the duplicate-writer problem instead of scheduling it**. **⇒ W4-BE4.** **No debt row is filed, because there is no second writer.** *(CLAUDE.md: "if fixing the bug is cheaper than writing + carrying its defer row, just fix it.")* |
| **OQ-2** 🔴 | What if the user materializes the same template twice? | 🔴 **ADJUDICATED — AND THE QUESTION DISSOLVES** (`Q-34-OQ2-DOUBLE-MATERIALIZE`). **The spec's proposal — "match on `(book_id, arc_template_id)` and PATCH the existing node" — is A BUG.** The `replace` path **soft-archives** the now-childless prior arc (`outline.py:691-702`) and mints a **FRESH** one, so a second materialize returns a **NEW** `arc_id` and the old stamped arc is **already archived**. That rule would PATCH the **ARCHIVED** arc and leave the **live** one unstamped ⇒ `NO_TEMPLATE_PROVENANCE` **forever** after any re-materialize. 🔴 **ALWAYS STAMP THE `arc_id` THAT CAME BACK.** One live stamped arc, always. **And: STAMP ON `replay: true` TOO — never suppress.** `_replay` returns the **original, still-active** `arc_id` *before* the replace sweep; re-stamping is a no-op in effect; and **suppressing on replay is what would leave an arc permanently unstamped if the first stamp failed. Stamp-on-replay IS the self-heal.** |
| **OQ-3** 🔴 | Where does the suggest route's `premise` come from? | **CONFIRMED: a free-text box, seeded from the book's `summary`.** 🔴 **AND THE SEED IS ON THE FE, NOT THE SERVER** (`Q-34-OQ3-SUGGEST-PREMISE`): BE-7b is a **PURE PASSTHROUGH** — seeding `premise` from `book.summary` server-side is a **silent hidden default** (SET-2) **and** it would make it impossible to suggest against a premise that *differs* from the summary. `premise` is **not a domain field** — it is an **optional embedding-query seed** (empty ⇒ the ranker degrades to genre order; *"never 500/[]"*). FE seeds from the **already-cached** `['book', bookId]` query via **override-or-derive, never a `useEffect`** (W4-FE6). **Do not add a `composition_work.settings` key here** — though note `settings JSONB` **already exists** (`migrate.py:41`), so Wave 6's dedicated field needs **no migration**. |
| **OQ-4** 🔴 | `import_source.content` is capped at 20 000 chars — a real novel is 100×–1000× that. Is a 20k excerpt actually useful? | 🔴 **CLOSED — ACCEPT THE CAP, AND FIX THE FRAMING, WHICH IS THE ACTUAL DEFECT** (`Q-34-OQ4-20K-CAP-USEFUL`). **Do NOT raise the cap. Do NOT build chunked multi-part import sources. Do NOT flag it at POST-REVIEW — remove it from the M2 gate and the M2 DoD.** **The spec's premise is factually wrong and that dissolves the question:** raising the cap needs **no schema change** (`content TEXT` is already unbounded; the engine already chunks + map-reduces). **What the cap guards is COST** — one paid LLM call per 12k chars, **sequential, in a job with no cancel**: a 3M-char novel = **~250 paid calls the user cannot abort.** And **20k is sufficient for an ABSTRACT template** (`scrub_verbatim` strips near-verbatim prose — **volume does not improve an abstraction**); the whole-manuscript path **already exists** as BE-7a, deterministic and **$0**. **No defer row: this is a CONSCIOUS WON'T-FIX (gate #5).** *(Any future raise MUST ship together with job cancellation — that sequencing, not the schema, is the real constraint.)* |
| **OQ-5** | `ArcConformancePanel`'s two dead calls — who fixes them? | **SPEC 33 (Wave 3 / `quality-conformance`) — it owns them as M-BUG-4 and fixes them in 3c, which lands BEFORE this wave.** 🔴 **DO NOT MINT A DEFER ROW.** Spec 34 §11 explicitly **withdrew** `D-ARC-CONFORMANCE-FE-ARGS-DRIFT` as a duplicate: *"filing a deferred row for a bug an earlier wave closes is tracking debt that does not exist"* (`debt-batches-list-is-stale-verify-first`). **Verify it (pre-flight cmd 5); do not re-file it.** This wave simply **drops the panel** (AT-7). |
| **OQ-6** | Does an arc template need a **book-shared** tier (like `motif`'s `book_shared`)? | **NO for v1, and it is NOT a gap.** `arc_template` has **no `book_id` column** — a book tier would be a **schema change PLUS a tenancy design** (who may edit a shared arc? the E0 grant model says EDIT-grantees — that is motif's answer and it needed a trigger). **Defer gate #2.** Collaborators share arc structure **by publishing + adopting**. 🔴 **SAY SO IN THE USER GUIDE** (`panels.arc-templates.guideBody`, W4-FE1 step 3) **so its absence does not read as an omission.** |

---

## 11 · DEFER REGISTER — starting rows

Add these to `docs/sessions/SESSION_HANDOFF.md` § Deferred Items **as they are raised**, not at the end.

| ID | Origin | What | Gate | Target |
|---|---|---|---|---|
| **`D-ARC-TEMPLATE-BOOK-SHARED-TIER`** | W4-FE1 (OQ-6) | No book-shared tier for `arc_template` (unlike `motif`'s `book_shared`). Collaborators share by **publish + adopt**. *(Cost, for the record: motif's `book_shared` needed a column + a shape CHECK + a **RECREATED** partial unique index + a second partial unique + a PL/pgSQL scope-guard trigger. And publish+adopt is **already fully wired** — `POST /arc-templates/{id}/adopt` — so a book tier buys collaborators **nothing they cannot do today**.)* | **#5 conscious won't-fix for v1** (a schema change **+** a tenancy design). | Recorded so it stops re-surfacing. **Documented in the User Guide** (W4-FE1 step 3) so its absence does not read as an omission. |
| **`D-COMPOSITION-OPENAPI-BACKLOG`** | W4-BE0 | `arc.py` has **14 routes with no OpenAPI entry** (`/arc-templates` CRUD/catalog/adopt/apply, `/books/{bid}/arcs`, `/arcs/{node_id}` PATCH/DELETE/restore/move, assign-chapters), inherited from specs 23/24. W4-BE0 documents **only** the two NEW routes — *"do not compound it"* ≠ *"backfill the backlog inside an XS slice."* | **#2 large/structural** (a contract sweep, not a wave item). | A contract-hygiene slice. **Nothing machine-checks the composition contract today** (`lint-contract.sh` lints identity only) — that gap belongs in the same row. |
| **`D-COMPOSITION-MOTIF-JOB-CANCEL-NOOP`** | W4-FE7 | `job_consumer.py:378-381` dispatches `analyze_reference` (and `mine_motifs`, `conformance_run`) **WITHOUT** the `cancel_check` callable every other op receives ⇒ a CAS-cancel is **silently ignored** and the job **still completes and still bills**. jobs-service `app/contract.py` advertises **cancel-capable** caps for composition kinds, so **the generic Jobs panel WILL render a Cancel button that no-ops.** *(This panel renders no cancel control and says why — that is the honest local fix.)* | **#1 out of scope** — a different panel + 3 engine signatures. | The next composition **worker** slice. |
| **`D-BE8-APPLY-ARC-TO-SPEC`** *(alias `D-ARC-APPLY-TXN-STAMP`)* | W4-BE8b — **ONLY IF the escape hatch fires** | The `apply_arc_to_spec` **wrapper** needs a schema change (it should not — `structure_node` already carries both columns). | **#2 large/structural** | Its own slice. 🔴 **W4-BE8a (drift) is NOT deferrable under ANY gate** — it is a 15-line delegate to a shipped orchestrator; the defer row would cost more than the fix. |

🔴 **ROWS THE ORIGINAL PLAN WOULD HAVE MINTED — AND MUST NOT:**
- ~~`D-AT6-FE-PROVENANCE-STAMP-DUPLICATE-WRITER`~~ — **DELETED.** OQ-1 is adjudicated **server-side**
  (W4-BE4) ⇒ **there is no second writer, so there is nothing to track.** *(This row is **mandatory** only
  if the PO overrules OQ-1 back to an FE stamp.)*
- ~~`D-IMPORT-SOURCE-20K-CAP`~~ — **DELETED.** OQ-4 is **CLOSED** as a **conscious won't-fix (gate #5)**,
  not a parked item. It is **unneeded** (own-book manuscripts go through extract-template) **and
  undesirable** (copyright + an uncancellable ~250-call paid job). **Do not flag it at POST-REVIEW.**

**Rows this wave CLEARS (move to "Recently cleared"):**
- 🔴 **`D-ARC-TEMPLATE-CRUD-GUI`** → closed by M1–M4. ⚠ **It is a COMBINED row on `SESSION_HANDOFF.md:3378`
  (`D-ARC-TEMPLATE-CRUD-GUI / D-MOTIF-LIBRARY-CRUD-GUI`) — SPLIT it, do not delete the line.** The motif
  half belongs to spec 33.
- 🔴 **`D-ARC-APPLY-MCP-WRAPPER`** → **CLEARED by W4-BE8** (not re-scoped again). Its text carries **two
  false claims** — that `build_template_drift` is missing engine work (it is a **delegate**; the
  orchestrator ships) and that `apply_arc_to_spec` is *"genuinely unwritten"* (the engine is
  **`arc_apply()`**, `arc_apply.py:325`, integration-tested). **Say so when you clear it.**

**Rows this wave DOES NOT MINT (and why — do not re-file them):**
- ~~`D-ARC-CONFORMANCE-FE-ARGS-DRIFT`~~ — **spec 33 M-BUG-4 owns it and closes it in 3c, before this wave.**
  🔴 **If 3c slipped, it is still NOT a row — it is a 3-line FIX-NOW inline in M1** (pre-flight cmd 5).
  *"Writing a defer row for a one-line fix is the anti-pattern that rule kills."*
- ~~`D-MOTIF-JOB-POLL-404`~~ — **it is BE-7c, owned by Wave 3 / 3a.** Verify (pre-flight cmd 4); if absent,
  **BUILD it (W4-BE3, re-scoped to M)** — it is **not deferrable**, it **is** the paid-action defect.

---

## 12 · RISKS — and the tell that each has fired

| # | Risk | The TELL | The response |
|---|---|---|---|
| **R1** | 🔴 **The provenance stamp silently no-ops.** | **Drift renders `NO_TEMPLATE_PROVENANCE` right after a successful materialize.** (Live-smoke AT-SMOKE-3 is designed to catch exactly this.) | W4-BE4's server-side stamp + W4-FE4's **`structure_node_id` + `chapters_assigned` assertion**, which renders an **ERROR, never a checkmark**. 🔴 **And do NOT "fix" a firing assertion by re-introducing `createArc`/`assignChapters` — that is the orphan bug (adjudication D).** If it fires, inspect `commit_decomposed_tree`'s return. |
| **R1b** | 🔴🔴 **A builder follows the ORIGINAL AT-6 shape** (`createArc` + `assignChapters`) because it is still written in spec 34. | Two spec arcs per materialize; the chapters re-pointed onto the new one; **materialize's arc left active-but-childless**; drift silently reads the wrong subject. | **Adjudication D, §3.4, and W4-FE4's opening banner all say it in writing.** The mechanical guard is W4-FE4's **grep test**: zero `assign-chapters` / `POST …/arcs` literals under `features/composition/**`, and **no `createArc` in `plan-hub/api.ts`**. |
| **R2** | 🔴 **`W0-BE1` (ex-BE-7c) is missing — or is present as a READ ROUTE OVER A ROW THAT IS NEVER WRITTEN.** | 🔴 **`POST /actions/confirm` returns HTTP 500 BEFORE the enqueue** (`_enqueue_motif_job`'s synthetic `uuid4()` → `GenerationJobsRepo.create()`'s `INSERT … SELECT … FROM composition_work` matches **zero rows** → `ReferenceViolationError`). The confirm token is **burnt** and a billing **hold** is left dangling — but ⚠ **NOBODY IS CHARGED** (no XADD, no worker, no LLM). **There is no `job_id`, so the poll is never reached** — *"the poll 404s forever"* describes a path that never executes. **A spinner hides all of it.** ⚠⚠ **And a read-route-only "fix" SHIPS GREEN** over a still-500ing confirm, because its test seeds the row with a raw `INSERT` the producer can never produce (`fixtures-can-seed-a-field-the-writer-never-sets`). | **Pre-flight cmd 4 has TWO halves for exactly this reason (adjudication E).** `4a` (the route) green is **not sufficient** — run `4b` (the live `generation_job` count). If either is broken ⇒ **W4-BE3 (re-scoped to M) is IN SCOPE**. **It is unbuilt work, not a blocker. You can build it. Build it.** *(This is the one class where you would stop and ask **only if you genuinely could not build it** — you can.)* |
| **R3** | **`arcEffects.ts` gets a SECOND registration** and every `composition_arc_*` write double-fires. | Duplicate invalidations; a query refetches twice per agent write. Silent — no test reds without the lock. | The **single-handler lock** in W4-FE1's test (`matchEffectHandlers(...).length === 1`). |
| **R4** | **The catalog's `{items,total}` shape is read as `{arc_templates}`** (or vice-versa). | The Catalog tab renders empty; `.items` is `undefined`. | The shape-drift lock in W4-FE2. **The two routes are NOT interchangeable.** |
| **R5** | **A bespoke `/actions/arc_import/confirm` gets invented** (the 3-times-shipped bug). | A production 404 on the confirm, after the propose already minted a token. | The generic-confirm-path lock in W4-FE7's tests. |
| **R6** | **The deconstruct's propose body is sent FLAT** instead of nested under `args`. | Arg-validation refusal from FastMCP; the propose 400s. | The args-nesting lock in W4-FE7's tests. **Copy `motif/api.ts:251-253`'s nesting; do not "clean it up".** |
| **R7** | **X-1 is not actually done** and the Deconstruct section's zero-model state destroys the dock. | The dock disappears when a user with no models opens the Import tab. **A unit suite cannot see this.** | Pre-flight cmd 1 + the **live smoke's step 4** (assert no dock teardown after touching the picker). |
| **R8** | **A second `structure_node` writer** appears (a rival `arcSpecApi` in the motif tree). | Two callers of `POST /books/{bid}/arcs`. | W4-FE4's "reuses plan-hub's `assignChapters`" test + a `grep` for `assign-chapters` literals outside `plan-hub/api.ts`. |
| **R9** | **The three drift empty states collapse into one** generic "no data". | The user sees "no drift" for an arc that was never applied, an arc with no provenance, **and** a deleted template — three different facts, one lie. | W4-FE5's three separate render tests. |
| **R10** | **Wave 3 has NOT landed** and the shared components (`MotifStateBoundary`, `CostConfirmCard`, `AdoptTargetModal`) get **forked** instead of imported. | Two copies drift; a fix lands in one. | Pre-flight cmd 7 finds where they live. **Import from there. Whichever wave lands first does the lift; the second imports.** |
| **R11** | **The enum count is asserted as a LITERAL** (`58` or `65`). | A builder in a re-ordered wave hunts a phantom regression. | **Assert the DELTA + the three-way equality. Never a literal.** Plan 30 §8.0 check 6. |
| **R12** | **BE-8b (`apply_arc_to_spec`) balloons** into a schema change / a `plan.py` refactor. | The slice runs long; the diff spreads into `plan.py`. | **The declared escape hatch:** write `D-BE8-APPLY-ARC-TO-SPEC` (gate #2), ship **BE-8a**, close the wave. **Do not stop. Do not ask.** |
| **R13** | **A shared-checkout collision** — three live tracks on `feat/context-budget-law`. | Someone else's edit lands in your commit. | **Never `git add -A`.** Enumerate files. `git commit -- <path>` reads the **WORKING TREE**, not the index — and the index may already carry a concurrent session's pre-staged changes. **Check `git diff --cached --name-only` before every commit.** Do **not** touch: `stream_service.py`, `ToolApprovalCard.tsx`, `useChatMessages.ts`, `tool_permissions.py` (Track C, mid-edit), or `PlanDrawer.tsx` (Book-Package track). |

---

## 12b · 🔴 WHAT `arc-templates` IS **NOT** — two panels are FALSE-HOMED to this wave

**Two rows in Wave 6's `LEGACY_SUBTAB_HOME` map point at panels this wave owns. Both are WRONG, and a
machine-checked retirement gate would go GREEN on a feature being DELETED.** Wave 4 does **not** build
either of them — but a Wave-4 builder must not be tempted to cram them in, and the map rows must be fixed
by their owners.

| Legacy sub-tab | Falsely homed to | The truth | Where it actually belongs |
|---|---|---|---|
| **`arc`** (`CharacterArcView`) | 🔴 `arc: 'arc-templates'` (wave-6 plan `:1457`) | **WRONG.** `arc-templates` (this wave) is the structure-**TEMPLATE** library + 拆文 deconstruct. `arc-inspector` (Wave 2) is the narrative-arc **SPEC tree** over book-service/composition arc rows. **Neither is a CHARACTER's event arc over the knowledge graph** (one character's events in `event_order`, spoiler-cut at the current chapter, with the active→gone state band + `ArcRelationsStrip`). | A **`character-arc`** panel in **Wave 8**, next to `cast` (same knowledge-service data, same deep-link pair). **Do NOT build it here.** |
| **`flywheel`** (`FlywheelPanel`) | 🔴 `flywheel: 'quality-corrections'` (wave-6 plan `:1454`) | **WRONG — and this is the single most dangerous line in the whole gate.** `quality-corrections` is `CorrectionStatsTable` (composition **correction rates**). `FlywheelPanel` is **canon-graph growth** (`knowledgeApi.getFlywheel`). **Two services, two datasets. The name collides; the thing does not.** *(Wave 1's own plan says so in writing, and spec 31 `:64` repeats it.)* | A **`canon-growth`** / `kg-flywheel` panel in **Wave 8**. **Do NOT build it here.** |

**Wave 4's obligation:** none — except **do not absorb either of them**, and **do not let anyone "close" a
homeless-tab row by pointing it at `arc-templates`.** *(Flagged so the Wave-6 map gets fixed by its owner
rather than silently going green.)*

---

## 13 · WHAT THIS WAVE MUST NOT DO

- ❌ **Do not build "mine motifs from this import source."** **REFUTED** (plan 30 §10): `_MotifMineArgs`
  is `scope: Literal["book","corpus"]` — there is **no `import_source_id` field**. `motif_mine` mines your
  **own** corpus. The member motifs of a deconstructed work are written by the `analyze_reference` worker,
  **not by mining.**
  🔴 **MAKE THE GUARDRAIL MECHANICAL, not prose** (`checklist ⇒ test the effect`): add **ONE** regression
  test to `services/composition-service/tests/unit/test_motif_mcp.py`:
  ```python
  def test_mine_args_reject_import_source_id():
      """AT-10, REFUTED: composition_motif_mine mines the CALLER'S OWN material only. The
      'deconstruct an imported work' capability is composition_arc_import_analyze. This test
      REDS the moment someone 'helpfully' adds the field."""
      with pytest.raises(ValidationError):
          srv._MotifMineArgs(scope="corpus", import_source_id=str(uuid4()))
  ```
  (`_MotifMineArgs` already extends `ForbidExtra`, so it **passes today** and reds on the regression.)
  Any M2 affordance phrased as *"mine motifs from this import"* MUST call `composition_arc_import_analyze`
  — **label the button "Deconstruct" / "Analyze reference"** so no builder reaches for mine.
- ❌ 🔴 **Do not add `createArc` to `plan-hub/api.ts`, and do not call `assignChapters` from the materialize
  flow.** Adjudication **D**: `materialize` already creates the arc and already links the chapters. Both
  calls mint a duplicate and orphan the original.
- ❌ 🔴 **Do not build a `studioLinks.ts` resolver or a `?panel=` URL contract.** Adjudication **F**: all
  three hand-offs are in-panel `openDetail(id)` calls.
- ❌ 🔴 **Do not author `design-drafts/screens/studio/screen-arc-templates.html`.** **It already exists**
  (1379 lines, committed in `d0f17555e` — the SAME commit that authored spec 34). Spec 34's *"Design draft:
  <path>"* header is a **POINTER to an existing file, not a to-do.** It already renders all ten states,
  including §4.1's Before/After empty-state fix (state ⑦, `:1270`). **READ it and treat it as the
  spec-of-record. Create NO new file and touch NO existing draft** — except the one-line stale-defer-row
  fix at `:1309` (DoD 10b).
- ❌ **Do not park the human drift view behind BE-8.** The route ships. Drift is **BE-NONE**.
- ❌ 🔴 **Do not park BE-8 itself.** It is **in-wave** (DoD #9: **zero `pending_dependency` may remain**).
  And **do not write a new apply engine** — `arc_apply()` ships; BE-8b is a **wrapper**.
- ❌ 🔴 **Do not re-point `arcConformanceRunConfirm` off `compositionApi.getJob`.** It **works** — that job
  carries a **real** `project_id`. BE-7c covers only the **two** synthetic-pid ops.
- ❌ 🔴 **Do not seed `premise` server-side.** BE-7b is a pure passthrough (SET-2).
- ❌ 🔴 **Do not raise the 20 000-char cap** — and do not flag it at POST-REVIEW. **OQ-4 is closed.**
- ❌ **Do not create a second `arcEffects.ts`, and do not add a second `registerEffectHandler` for an
  overlapping `composition_arc_*` pattern.** Extend the handler **body**.
- ❌ **Do not invent `/actions/arc_import/estimate` or `/actions/arc_import/confirm`.** Use the generic
  `POST /actions/confirm?token=`.
- ❌ **Do not mirror `mineConfirm`'s poll leg.** It 404s.
- ❌ **Do not add `composition_arc_extract_template` (a WRITE) to `FE_BRIDGE_TOOL_ALLOWLIST`.** It gets a
  REST route (AT-3).
- ❌ **Do not touch the BFF or the gateway.** Zero changes. The composition `pathFilter` is generic.
- ❌ **Do not fork `MotifStateBoundary` / `CostConfirmCard` / `AdoptTargetModal` / `MatchReasonChip`.**
- ❌ **Do not write a rival `arcSpecApi`.** Add `createArc` to `plan-hub/api.ts`.
- ❌ **Do not render `ArcConformancePanel` in the new panel** (AT-7 — it is dead on both calls, and it is
  spec 33's surface).
- ❌ **Do not add a new global env flag** for anything user-facing (SET-1..8). This panel introduces
  **zero** new settings. The one configurable thing is the deconstruct's `model_ref` — a **per-user BYOK
  choice** through `provider-registry`.
- ❌ **Do not hardcode a model name anywhere.** The provider-gateway invariant is ENFORCED by
  `scripts/ai-provider-gate.py` (a pre-commit hook).
- ❌ **Do not retire `ChapterEditorPage`.** GG-4 — Wave 6 holds that gate.
