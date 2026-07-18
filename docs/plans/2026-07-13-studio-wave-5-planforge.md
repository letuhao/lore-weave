# Wave 5 — PlanForge made human · IMPLEMENTATION PLAN

> **Type:** FS · **Size:** **XL** (≈22 logic changes · side effects: **5 new REST routes + 1 new MCP tool**,
> 4 changed response contracts, 1 additive migration + partial index, **1 OpenAPI contract file**, 3
> JSON-schema contracts, 1 new panel id across 6 registration files, **4 repo reads gaining a new predicate**)
> **Wave:** 5 of [`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](../specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) §7
> **Spec:** [`35_planforge_studio.md`](../specs/2026-07-01-writing-studio/35_planforge_studio.md)
> 🔴 **ADJUDICATION REGISTER (THE AUTHORITY — read §0.1 first):** [`studio-adjudication/wave-5-decisions.md`](studio-adjudication/wave-5-decisions.md)
> **Drafts (NON-NORMATIVE — see below):** [`screen-planforge-pass-rail.html`](../../design-drafts/screens/studio/screen-planforge-pass-rail.html) (M4 layout) · [`2026-07-06-planner-panel-redesign-mockup.html`](../../design-drafts/planforge/2026-07-06-planner-panel-redesign-mockup.html) (M3 planner — **it has NO Pass Rail**)
> **Closes:** **G-PLANFORGE-PASS-RAIL** (P0, L) · **G-PLANNER-REPAIR** (M) · spec **27-B1/B1b/B2** (contract hygiene)
> **Absorbs deferred row:** `D-PLANFORGE-GUI-AUDIT` — ⚠ **its sub-gap 1 (the `arc_id` text box) is STALE, already fixed by `9c685c28a`. DO NOT re-do the arc picker.**
> **Written:** 2026-07-13 against HEAD `9262ed53e`. **Reconciled against the adjudication register 2026-07-13.**

### 🔴 How to read the mocks (`Q-35-MOCKUP-START-POINT` — three BINDING rules)

1. **The planner-redesign mockup is the layout start point for M3 (`planner` repair) ONLY — it has NO Pass
   Rail.** Take from it (a) the state model + layout of the planner flow, (b) the copy **voice**, and above all
   (c) its **ROOT DIAGNOSIS** (lines ~26-33): *"this isn't a missing-button problem, it's a **LEAKY
   ABSTRACTION** problem — the shipped panel renders raw backend vocabulary (literal `arc_2`, rule ids
   `pa_not_realm`, raw `var_delta`) at a novel **WRITER**."* **That diagnosis is why the repair buttons say
   *"Explain what's wrong"*, not *"interpret"*.** ⛔ Do not copy its raw CSS/HSL (the panel is Tailwind +
   shadcn tokens). ⛔ **Its sub-gap 1 (the `arc_id` text box) is STALE.**
2. 🔴 **Enable / disable / blocked state is NEVER drawn from EITHER mock, and NEVER re-derived in the
   frontend.** The backend already ships the answer per pass (`blockers[]`, `fresh`, `pass_cursor`,
   `blocked_at`). **A mock is a picture of one state, not a state machine.**
3. **The mechanical guard that makes rule 2 stick** is the **INVERTED-FIXTURE test** in W5-S12. *A frontend
   file under `features/plan-forge/**` must contain **NO literal dependency graph** — today `grep -rn
   "depends_on|PASS_ORDER|PASS_REGISTRY" frontend/src/` hits only an unrelated wiki constant.*

**Where a mock and §5 disagree on planner BEHAVIOUR, §5 wins** (the mocks predate the 2026-07-13 code
re-read); **where they disagree on PRESENTATION/COPY, the mock wins.** The mocks are **non-normative design
drafts, not contracts.**

---

## 0 · READ THIS FIRST — the policy this plan is written under (binding)

1. **This plan is written ONCE, in full, at BUILD DETAIL.** After the QC gate, implementation proceeds
   **autonomously with no further design checkpoints.** Every slice names WHICH FILE, WHAT CHANGE, WHICH
   TEST. If something here is vague, that is a bug in this plan — but do not stall on it: pick the reading
   that satisfies the DoD evidence string and record the choice in the decision register.
2. **`/review-impl` runs at the completion of the wave**, and **every bug it finds is fixed before the wave
   closes.** It is slice **W5-S15**, a literal step, not a nice-to-have.
3. **DEFERRAL POLICY — "blocked ≠ stopped".** Hit a blocker → write a tracked defer row and **KEEP GOING**.
   Do **not** stop, do **not** ask. **Stop and ask ONLY for a CRITICAL blocker**, defined narrowly as
   exactly one of:
   - a destructive / irreversible action (data loss; a migration that drops or rewrites user rows),
   - a **sealed decision proven wrong** by the code (plan 30 §0 PO-1..4),
   - a **tenancy / security breach** (cross-user data exposure),
   - a **paid-action defect that would charge the user for nothing** (this repo just shipped one — the
     motif-mine / 拆文 `POST /actions/confirm` **500s BEFORE the enqueue**: the confirm token is burnt, a
     billing **hold** is reserved, and **the job row is never created**. ⚠ **NOT a "404 at the poll", and
     NOBODY WAS EVER CHARGED** — no XADD, no worker, no LLM call. The fix is the **Work-less job lane**
     (`W0-BE1`), **not** a job-read route). ⚠ **Wave 5 is full of paid actions** (`run_pass`, `refine`,
     `interpret`, `autofix`). A Run button whose job can never be observed is exactly this class. Treat it
     as CRITICAL.

   Everything else — a missing route, an awkward refactor, an ugly seam — is a **defer row + continue**.
4. Every defer row carries: ID, slice of origin, what, the gate reason (CLAUDE.md's 5 gates), target
   wave/trigger. A defer row is never a silent drop.
5. **CLAUDE.md's anti-laziness rule is in force:** *"missing infrastructure is NOT blocked — it is unbuilt
   work to implement."* A route that does not exist is a route you **WRITE**.

### 0.1 🔴 THE ADJUDICATION REGISTER **EXISTS** — and it OVERRIDES this plan

> **Register:** [`docs/plans/studio-adjudication/wave-5-decisions.md`](studio-adjudication/wave-5-decisions.md)
> — **47 items · 44 DECIDED · 2 not-a-question · 1 deferred.** Every one was settled **by reading source**.

This plan's **first draft was written BLIND** — the register was recovered from the journal *after* the ten
wave plans were drafted. It has now been **folded in (2026-07-13, reconciliation pass)**. The rules:

1. **Where the register and this plan disagree, THE REGISTER WINS.** It was adjudicated against code; the
   plan was guessing. Every place that happened is listed in **§0.2** as a `C-*` correction row.
2. The register's decisions are **SEALED**. Do **not** re-open a decided question. §11 of this plan is now
   just an **index into the register**, not an independent authority.
3. Where the register itself contains two overlapping adjudications that disagree (it does, in three
   places — they were written by different adjudicators), the reconciliation is recorded in **§0.3** and is
   binding. **Do not re-litigate those from memory: re-read §0.3.**
4. **Read the register's entry for a slice BEFORE building that slice.** Each slice below names its
   register entries (`Q-35-*`). The register carries builder-ready code, exact line numbers, and the traps.
   This plan is the *board*; the register is the *spec*.

### 0.2 🔴 Spec corrections found by reading the code (the spec is wrong; this plan is right)

The wave brief warned the audit still carried wrong backend rows and to assume the same rate remains. Two
found:

| # | The spec says | The code says | What to build |
|---|---|---|---|
| **C-1** | Spec 35 §6 **BE-2**: the autofix route returns *"`202 {run_id, job_id, status}` — mirror `/refine`'s ack shape"* | **`handoff_autofix` NEVER returns an ack.** It loops synchronously and **always** returns `{"rounds": [...], "run": <detail>}` ([`plan_forge_service.py:849-850`](../../services/composition-service/app/services/plan_forge_service.py#L849)). When the worker is on, the first round's inner `refine` enqueues, the loop **breaks**, and the return is *still* `{rounds:[{round:1, targets:N, result:"pending"}], run:{…active_job_id set…}}`. The MCP tool ([`server.py:3499`](../../services/composition-service/app/mcp/server.py#L3499)) returns exactly that. | **`POST …/autofix` returns `200 {rounds, run}`.** NOT 202, NOT an ack. A builder who writes `status_code=202` ships an FE that reads `job_id` off a body that has none. See **W5-S4**. |
| **C-2** | Spec 35 §10 DoD item 1: *"py enum **58** == contract enum **58** == openable **58**"* | HEAD is **57** (measured: `frontend_tools.py:402` enum has 57 entries). **`65` IS ALSO A PHANTOM** (`Q-35-PANEL-COUNT-BASELINE`): it presumes waves 1–4 each land *exactly one* panel. If any slips or lands two, 65 is as wrong as 58. **No drift-lock test counts panels** — `panelCatalogContract.test.ts:26-35` asserts **SET equality**, which is strictly stronger. | **STRIKE EVERY LITERAL (57 / 58 / 65 / 66).** Measure `N_before` at wave start; assert `N_after == N_before + 1` **and** that the set difference is exactly `["plan-passes"]`. **ADD NO COUNT TEST** — a count assertion is weaker than the shipped set-equality guard and would manufacture the very drift it claims to catch. See **W5-S13**. |

#### 🔴 C-3 … C-13 — corrections the ADJUDICATION REGISTER makes to this plan (the register wins)

| # | Register entry | This plan (BLIND draft) said | The REGISTER says (adjudicated against source) | Where fixed |
|---|---|---|---|---|
| **C-3** | `Q-35-X1-ADDMODELCTA` | X-1 is an **external hard gate**; if it has not landed, **"STOP the panel slices"**. And it greps `frontend/src/components/model-picker/AddModelCta.tsx`. | **X-1 has NOT landed and it is THIS WAVE'S FIRST SLICE.** It is **~30 lines in ONE file** — `frontend/src/components/**shared**/AddModelCta.tsx` (the plan's path is **wrong**; grep proves 8 `useOptionalStudioHost` hits, **none** in `components/shared/`). "STOP and ask" for unbuilt work also **violates the run policy (§0 rule 3)** — a missing route/component is *work you WRITE*. | **W5-S0** (new) |
| **C-4** | `Q-35-BE21-LIST-NPLUS1` | BE-21 adds `await self._runs.latest_artifact(…, PACKAGE_KIND)` inside `_serialize_run` — **one extra query per run, in a LIST loop.** | **The N+1 does not exist and must not be created.** `list_artifact_refs` is already `SELECT DISTINCT ON (a.kind) … ORDER BY a.kind, a.created_at DESC` (`plan_runs.py:351`) = **the latest artifact id PER KIND — the package id is ALREADY in the list `_serialize_run` holds.** Read it from there. **Zero new queries.** | **W5-S1** |
| **C-5** | `Q-35-BE22-PHANTOM-TOOL` | Replaces the message with *"cast cannot be accepted: its glossary seed proposal is missing — re-run the `cast` pass…"* | **That REDs a shipped test.** `test_plan_pass_checkpoint.py:111` asserts the substring **`"before its glossary seed proposal exists"`**. **KEEP the leading clause**; replace only the phantom parenthetical. Exact wording in the register. | **W5-S1** |
| **C-6** | `Q-35-PS12-STUCK-BANNER-PREDICATE` | The stuck banner is **derived in the FE**: `blocked_at ?? (first BLOCKING pass not accepted/auto)`. | **OVERRIDDEN — FIX `blocked_at` AT THE SOURCE.** A predicate duplicated across BE+FE is this repo's known drift class, **and the panel-side fix leaves the AGENT surface lying** (`plan_pass_status` ships `blocked_at` to agents as *"the pass a human must accept next"*). Also the plan's rule is **under-inclusive**: `_review_pass` accepts ANY pass_id, so a **rejected ADVISORY** pass (`character_arcs`) hard-blocks `scenes` forever and a blocking-only predicate names nothing. **New `blocked_at` = the first COMPLETED pass that is `not is_accepted`, any checkpoint class.** FE renders `view.blocked_at` **directly and derives NOTHING.** ⚠ **This inverts DoD leg (f)** — see §10. | **W5-S1**, **W5-S12**, **§10** |
| **C-7** | `Q-35-BE2-AUTOFIX-ROUTE` | *"**NEVER** a 202."* Always `return out` (200). | Half right. **200 on the sync path** (correct — the spec's ack shape was a guess). **But 202 when `run.active_job_id` is set** — the worker path DID enqueue. **Same body either way** (`{rounds, run}`); the status code is the only difference. Returning 200 on a run with a live job **lies about being done**. | **W5-S4** |
| **C-8** | `Q-35-BE3B-SOURCE-MARKDOWN` | `_serialize_run` **unconditionally** adds `source_markdown`. | **OPT-IN ONLY** (`include_source: bool = False`). `_serialize_run` is shared by **LIST** (one call per item) and by the **MCP tool result** — `source_markdown` is capped at **262,144 chars** (`plan_forge.py:38`). Unconditional = echoing a 256 KiB body back into the LLM's own tool result: a **Context Budget Law** violation, on this very branch. Only `get_run_detail` opts in. FE type is **`source_markdown?: string`** (optional — the list truly omits the key). | **W5-S3** |
| **C-9** | `Q-35-PS9-PROVIDER-REGISTRATION` | `registerPlanArtifactDocumentProvider()` at **PlannerPanel/PassRailPanel mount**. | **REJECTED — register at MODULE IMPORT from `catalog.ts`.** The dock restores a `json-editor` tab from **localStorage** (`useStudioLayout.ts:26`) with **no guarantee any plan panel is mounted** ⇒ `openJsonDocument` throws *"no JSON document provider for type…"*. Mount-registration only **narrows** the browser-dead window. **Zero registration calls in the panels.** | **W5-S9** |
| **C-10** | `Q-35-PS9-COMPOSITE-ID` | `openPanel('json-editor', { params })`. | **WRONG — that panelId is the SINGLETON**; a second artifact **retargets/replaces** the first tab. Use the shipped multi-instance form: ``openPanel(`json-editor:loreweave.plan-artifact.v1:${runId}:${artifactId}`, { component: 'json-editor', title, params, focus: true })``. | **W5-S9** |
| **C-11** | `Q-35-OQ3-PLAN-GET-ARTIFACT-MCP` | **DEFER** `plan_get_artifact` (`D-PLAN-GET-ARTIFACT-TOOL`), because it is *"a 3-schema-source FastMCP change"*. | **THAT REASON IS FALSE — it is knowledge-service's shape, not composition's.** `grep TOOL_DEFINITIONS services/composition-service/app` → **0 hits**: the `@mcp_server.tool` decorator's function signature **IS** the advertised inputSchema. **ONE** schema source. **BUILD IT THIS WAVE as BE-3c**, ~35 lines in a file the wave already opens. **The defer row is DELETED.** | **W5-S2**, **§12** |
| **C-12** | `Q-35-OQ1-TIER-W-DESCRIPTOR` | Defer row `D-PLAN-TIERW-DESCRIPTOR`: *"PlanForge's paid actions spend with **no pre-run guardrail claim**."* | **THAT PREMISE IS FALSE.** Every plan pass's LLM call goes through `LLMClient.submit_and_wait` → provider-registry `POST /v1/jobs` → **`runGuardrailPreflight` (fail-CLOSED `guardrail.Reserve`, 402 `LLM_QUOTA_EXCEEDED`)** *before a token is spent* (`jobs_handler.go:203-218,415`). **OQ-1 is a CONSCIOUS WON'T-FIX (defer gate 5), not an open gap.** The one real value it was chasing — an **honest** quota refusal in the panel — is a build item. | **W5-S12**, **§12** |
| **C-13** | `Q-35-X4-PLAN-EFFECTS-HANDLER` + `Q-35-POLL-IDIOM` | `planEffects` reads `run_id` from the result and **`if (!runId) return;`** — plus **PS-14 migrates `usePlanRun` + `usePlanRunsList` to react-query.** | **`plan_run_pass`'s result carries NO `run_id`** (`{job_id, status, pass_id}` + the derived pass block — `plan_forge_service.py:1212-1217`), and `EffectContext` carries **no tool ARGS** (`effectRegistry.ts:9-24`). ⇒ **an exact-key handler could NEVER fire.** Invalidate by **BOOK PREFIX**, unconditionally. And **do NOT refactor the two shipped hand-rolled hooks** — reach them with the **`reload*` escape hatches `EffectContext` already has for exactly this** (`reloadChapter`/`reloadScenes`). **PS-14 is NARROWED — see §4.** | **W5-S8**, **W5-S14**, **§4** |

---

### 0.3 ⚖ Register-vs-register reconciliations (BINDING — do not re-litigate from memory)

The register was written by several adjudicators. Three entries overlap and disagree. **These three
readings are final for this wave:**

| Clash | Entries | **BINDING RESOLUTION** |
|---|---|---|
| **How `_serialize_run` gets the package id** | `Q-35-BE21-LIST-NPLUS1` (read it from the `artifacts` list already fetched — **zero queries**) **vs** `Q-35-BE21-TEST-PIN` / `Q-35-F-P3-TWO-TRUTHS` (call `latest_artifact(…)`) | **BOTH, correctly composed.** Build the **ONE producer** helper `_pass_view(run, package_artifact_id)` (F-P3's whole point: one derivation) **as a pure function taking the id** — and let each caller supply the id the cheapest way it already can: `_serialize_run` reads it **out of the `artifacts` refs it already holds** (zero new queries — LIST stays at its current cost); `pass_status`, which does **not** call `list_artifact_refs`, keeps its existing `latest_artifact` fetch. `list_artifact_refs` is `DISTINCT ON (kind) … ORDER BY created_at DESC` — it resolves the **same row** `latest_artifact` would. |
| **`plan-artifact` provider `save()`** | `Q-35-ARTIFACT-READONLY-WHY` (must surface `status:'error'`, because `types.ts:38` contracts *"save never throws"*) **vs** `Q-35-PS9-PROVIDER-REGISTRATION` (`save: () => { throw … }`) | **NO CONFLICT IN EFFECT — both, and here is why.** `FetchHandleIO.save`'s own contract (`fetchHandle.ts:8`) is literally *"Persist; **throw** … to surface conflict/error on the snapshot"* — the handle catches and sets `status:'error', detail:<message>`. So **`io.save` THROWS** `'plan artifacts are read-only — edit them at the pass checkpoint'`, and `DocumentHandle.save()` still never throws. **A save that silently resolved would be the bug.** |
| **The stuck-banner predicate** | `Q-35-NO-HOLD-COPY` §4 (derive `stuckAt` in the panel) **vs** `Q-35-PS12-STUCK-BANNER-PREDICATE` (fix `blocked_at` at the source; FE derives NOTHING) | **`Q-35-PS12-STUCK-BANNER-PREDICATE` WINS** — it explicitly overrides the panel-side derive, is strictly more inclusive (it catches the **rejected ADVISORY** pass the panel-side rule misses), and it is the only one that also fixes the **agent** surface. Everything else in `Q-35-NO-HOLD-COPY` (three buttons, no "Hold", the one-call approve-with-edits, the copy) **stands unchanged.** |

---

## 1 · Header — gaps, gates, what it unblocks

### What this wave fixes (the headline)

**A GUI-only user's plan run is permanently stuck at `pass_cursor: 1`, with 4 of its 7 passes unreachable.**

The PlanForge v2 compiler runs seven passes. Two — **`cast`** and **`beats`** — are **BLOCKING**: they
complete with `decision:"pending"` and the runner stops until a human accepts them. The only door that
clears a blocking pass is `POST …/checkpoint`, and **it has no GUI**. `frontend/src/features/plan-forge/api.ts`
has no `checkpoint`, no `passes`, no `link` method. Four shipped REST routes have **zero FE consumers**.

The code knows. This comment sits in the shipped MCP tool, [`server.py:3599`](../../services/composition-service/app/mcp/server.py#L3599):

```python
    # ⚠ THERE IS NO `force` HERE, AND THERE MUST NOT BE.
    #
    # The service and the HTTP route both take `force` — a human, at the GUI, may override the PF-5
    # gate on their own book. The AGENT may not, and the first version of this tool exposed it.
```

**The GUI it reserves that override for does not exist.** A capability deliberately reserved for a human,
exercisable only by an LLM, is GG-1 inverted.

### Hard gates

| Gate | What | Why | Blocking? |
|---|---|---|---|
| **X-1** | `AddModelCta.tsx` DOCK-7 teardown fixed **at the shared component** (`useOptionalStudioHost()` → `host.openPanel('settings', {params:{tab:'providers'}})`; `<Link>` fallback outside the studio) | **Every paid action in this wave needs a `ModelPicker`, whose empty state renders `AddModelCta` — today a raw `<Link to="/settings/providers">` that DESTROYS the dockview layout.** Shipping the Pass Rail before X-1 puts a workspace-destroying button on it. | 🔴 **NOT a gate you WAIT on — it is 🔴 W5-S0, THE FIRST SLICE OF THIS WAVE.** `Q-35-X1-ADDMODELCTA`: it has NOT landed, it is **~30 lines in ONE file**, and it is **fully unblocked**. CLAUDE.md's anti-laziness rule: *missing infrastructure is unbuilt work you WRITE.* **Do not defer it. Do not ship the Rail before it.** |
| **X-2** | `CATEGORY_ORDER` contains every `StudioPanelCategory` + the membership assertion exists | `plan-passes` is `category: 'editor'`, which IS already in `CATEGORY_ORDER` — **so X-2 does not gate this wave's panel.** Verify anyway (one grep); if red, it is Wave 1's problem, not yours. | 🟡 advisory |
| **X-3** | `panelCatalogContract.test.ts` asserts `guideBodyKey` on every openable panel | This wave adds a `guideBodyKey`. If X-3 landed, the test guards it. If not, add the key anyway. | 🟡 advisory |
| **X-3b** | The tool **description prose** is machine-checked against the `panel_id` enum | `Q-35-CATALOG-ROW-REQUIRED-FIELDS`: step 5(b) — the gloss that is *"the model's ONLY hint the panel exists"* — is **the one step in the whole 9-step checklist that NOTHING checks.** A builder can go 100% green while the model never learns the panel exists. **All 57 current ids already appear in the description**, so the assertion is **GREEN at HEAD** and reds on the next unglossed add. **Add it (XS, fix-now) in W5-S13** unless Wave 0 already did. | 🟢 **build it here** |

### What this wave unblocks downstream

- Nothing in plan 30 is gated on Wave 5. It is a **leaf** — the safest large lane available (plan 30 §9
  lists the Planner panel in its 🟢 *"genuinely un-colliding"* row).
- **FE-1** (`readOnly` on the JSON-document standard, W5-S7) is a **spec-12 contract widening** that every
  future read-only JSON viewer inherits. Wave 6+ benefits.

---

## 2 · Pre-flight — the exact commands (run ALL of them; paste the output)

```bash
# 0. Confirm the branch + HEAD
cd /d/Works/source/lore-weave-mvp && git status --short && git log --oneline -1

# 1. 🔴 X-1 — AddModelCta. ⚠ THE FILE IS `components/shared/`, NOT `components/model-picker/`
#    (the plan's first draft had the path wrong; `Q-35-X1-ADDMODELCTA` corrected it).
#    Expect: BOTH variants are still `<Link to={REGISTRATION_PATH…}>`, and ZERO useOptionalStudioHost.
#    That is NOT a stop — it is W5-S0, the first slice you build.
grep -n "useOptionalStudioHost\|openPanel\|Link to" frontend/src/components/shared/AddModelCta.tsx
grep -rln "useOptionalStudioHost" frontend/src/    # 8 hits; NONE in components/shared/ ⇒ X-1 unbuilt
grep -n "openPanel('settings'" frontend/src/pages/book-tabs/TranslateModal.tsx   # the shipped precedent to copy

# 2. Enum baseline — MEASURE it, never assume. Record the number; the DoD asserts baseline + 1.
python - <<'PY'
import re
src = open('services/chat-service/app/services/frontend_tools.py', encoding='utf-8').read()
m = re.search(r'"panel_id".*?"enum":\s*\[(.*?)\]', src, re.S)
ids = re.findall(r'"([a-z0-9\-]+)"', m.group(1))
print("py enum baseline:", len(ids))
assert 'plan-passes' not in ids, "plan-passes ALREADY in the enum — another wave took it?"
PY
grep -c '"id":' contracts/frontend-tools.contract.json   # sanity only

# 3. The 4 Pass-Rail routes exist (all four MUST print).
grep -n "passes\b\|/checkpoint\|/link\|/passes/{pass_id}/run" services/composition-service/app/routers/plan_forge.py

# 4. The three truth-bugs are STILL THERE (if any is already fixed, skip that sub-change; do NOT "re-fix").
grep -n "derive_view(run)" services/composition-service/app/services/plan_forge_service.py          # F-P3: expect a BARE call at ~:383
grep -n "bootstrap_proposal_id" services/composition-service/app/services/plan_pass_service.py      # F-P4: expect ONLY record_pass, NOT derive_view
grep -rn "plan_bootstrap_seed" services/                                                            # F-P5: expect EXACTLY ONE hit — the error string

# 5. There is NO artifact-read route and NO delete anywhere (both MUST print nothing).
grep -rn "artifacts/{artifact_id}\|@router.delete" services/composition-service/app/routers/plan_forge.py services/composition-service/app/routers/plan_bootstrap.py

# 6. readOnly does not exist in the JSON-document seam (MUST print nothing → FE-1 is real).
grep -rn "readOnly\|editable" frontend/src/features/studio/panels/JsonEditorPanel.tsx frontend/src/features/studio/documents/*.ts

# 7. interpret/refine have api.ts methods and ZERO callers (the free win).
grep -rn "interpret\|refine" frontend/src/features/plan-forge/hooks/ frontend/src/features/plan-forge/components/

# 8. Baselines — record BOTH numbers; the DoD compares against them.
cd services/composition-service && python -m pytest tests --collect-only -q 2>&1 | tail -1   # RECORD it; do not expect a number
cd ../../frontend && npx vitest run --reporter=dot 2>&1 | tail -3
```

**Recorded at plan time (2026-07-13, HEAD `9262ed53e`):** py enum = **57** · composition = **2355
collected** · `readOnly` in the JSON seam = **0 hits** · `plan_bootstrap_seed` = **1 hit (the error
string)** · artifact-read route = **absent** · `@router.delete` in plan routers = **absent** ·
`useOptionalStudioHost` in `components/shared/` = **0 hits (X-1 unbuilt)**.

🔴 **DO NOT EXPECT ANY PARTICULAR NUMBER — record what you MEASURE** (`Q-35-PANEL-COUNT-BASELINE`).
`57`, `58`, `65`, `66` are **all phantoms**: 65 presumes waves 1–4 each land exactly one panel; if any slips
or lands two, it is as wrong as 58. The DoD asserts **`measured + 1`, and that the set difference is exactly
`["plan-passes"]`** — never a literal.

```bash
# 9. THE DELTA GATE (Q-35-PANEL-COUNT-BASELINE) — record BOTH of these at wave start.
jq '.ui_open_studio_panel.args.panel_id.enum | length' contracts/frontend-tools.contract.json   # N_before
jq -r '.ui_open_studio_panel.args.panel_id.enum[]' contracts/frontend-tools.contract.json | sort \
  > /tmp/panels-before.txt        # the set, for the W5-S13 set-diff check
```

---

## 3 · The dependency graph — READ THIS BEFORE DRAWING ANYTHING

`PASS_ORDER` is the **serialization** order. `depends_on` is the **dependency** graph. **They are
different, and spec 35's own first draft got this backwards.** Read straight out of
[`PASS_REGISTRY`](../../services/composition-service/app/services/plan_pass_service.py#L55) —
**verified 2026-07-13**:

| # | pass | `depends_on` | class | `output_kind` | reads package |
|---|---|---|---|---|---|
| 1 | `motifs` | — | advisory | `motif_plan` | ✓ |
| 2 | `cast` | — | **BLOCKING** | `cast_plan` | ✓ |
| 3 | `world` | **`cast`** | advisory | `world_plan` | ✓ |
| 4 | `beats` | **`motifs`** | **BLOCKING** | `beat_plan` | ✓ |
| 5 | `character_arcs` | `cast`, `beats` | advisory | `char_arc_plan` | — |
| 6 | `scenes` | `cast`, `motifs`, `beats`, `character_arcs` | advisory | `scene_plan` | ✓ |
| 7 | `self_heal` | `scenes`, `cast` | advisory | **`scene_plan`** (re-emitted) | — |

**Three things a builder MUST NOT get wrong:**

- **`world` is gated on `cast`, NOT on order.** With `cast` pending, `world` is **BLOCKED** — its Run
  button 409s `UPSTREAM_STALE ["cast"]`. **Render it disabled.**
- **`beats` is gated ONLY on `motifs`.** With `motifs` accepted, **`beats` is RUNNABLE while `cast` is
  still pending.** It is the *only* pass that can run in the headline state. **Render its Run button
  ENABLED.** `blockers_for("beats")` can **only ever be `["motifs"]`** — an envelope naming `cast` as a
  blocker of `beats` is impossible.
- **`pass_cursor` is contiguous fresh AND *accepted***; `is_accepted` is `decision in ("accepted","auto")`.
  With `motifs` accepted and `cast` pending the cursor is **1**. **NEVER hard-code a cursor. Render
  whatever the ledger derives.**

**Seven passes, SIX artifact kinds** — `self_heal` re-emits `scene_plan`, deliberately. So the artifact
viewer's latest-per-kind list (`SELECT DISTINCT ON (a.kind)`,
[`plan_runs.py:355`](../../services/composition-service/app/db/repositories/plan_runs.py#L355)) shows
**`self_heal`'s healed output under the `scene_plan` row once pass 7 has run** — not pass 6's. **Say so in
the panel copy**, or the user thinks their scenes vanished.

---

## 4 · 🔴 THE ARCHITECTURAL DECISION THIS PLAN ADDS (PS-14) — read before writing any FE code

**`features/plan-forge` does NOT use react-query. It is hand-rolled `useState` + `useEffect` fetching**
(verified: `usePlanRun.ts`, `usePlanRunsList.ts` — plain `fetch`-on-mount, a `genRef` generation guard, a
manual `refresh()`).

This collides head-on with **Lane-B (X-4, registration step 8)**, which is **MANDATORY** for this panel:
`planEffects.ts` refreshes the GUI after an agent write by calling
`ctx.queryClient.invalidateQueries(...)`. **`invalidateQueries` cannot reach hand-rolled state** — it is
this repo's own recorded lesson (`invalidatequeries-cannot-reach-hand-rolled-state`: *"the manual loader
holds the rows the write mutated"*). A `planEffects.ts` that invalidates a key nobody reads is a **silent
no-op handler that passes its own unit test** (the test registers a fake and calls it) and **does nothing
live** — the exact `agent-gui-loop-needs-live-browser-smoke-not-raw-stream` class.

**🔴 PS-14 — NARROWED BY THE REGISTER (C-13). The plan's first draft over-reached; this is the sealed shape:**

`Q-35-X4-PLAN-EFFECTS-HANDLER`: *"Do NOT refactor the shipped hand-rolled `usePlanRun.ts` / `usePlanRunsList.ts`
(out of scope; leave them imperative — the Rail is the panel this handler serves)."*
`Q-35-POLL-IDIOM`: *"usePlanRun stays hand-rolled. If the PO wants one idiom repo-wide, that is a separate
S-size follow-up."* **Migrating the two SHIPPED hooks risks the shipped Planner panel for no gain — the
escape hatch that solves this already exists in the seam.**

| Hook | Verdict | How Lane-B reaches it |
|---|---|---|
| `usePassRail` (**NEW**) | 🟢 **react-query** — `useQuery` + `refetchInterval` (the repo's DOMINANT poll idiom: `useCampaignQueries`, `useEnrichmentJobs`, `authoringRuns/hooks.ts`, …). Key: **`['plan-passes', bookId, runId]`**. | `queryClient.invalidateQueries({ queryKey: ['plan-passes', bookId] })` — **BOOK PREFIX** (react-query prefix-matches). |
| `usePlanRun` (shipped) | ⛔ **NOT refactored.** Keeps `useState` + `setTimeout` + `genRef`. | **`ctx.reloadPlanRun?.(runId)`** — a new optional callback on `EffectContext`, **exactly mirroring the shipped `reloadChapter` / `reloadScenes` hatches**, which exist *because* `invalidateQueries` cannot reach hand-rolled state (`effectRegistry.ts:9-23`, `bookEffects.ts:36-40`). |
| `usePlanRunsList` (shipped) | ⛔ **NOT refactored.** Keeps its own `items` + `refresh()`. | **`ctx.reloadPlanRuns?.()`** — same hatch shape, supplied from `usePlanRunsList.refresh`. |

**The rule this replaces PS-14 with — and it is the SAME rule, applied honestly:**

> 🔴 **NEVER SHIP A DEAD-KEY INVALIDATION.** `planEffects.ts` must **not** call
> `invalidateQueries(['plan-run', …])` or `(['plan-runs', …])` — **those keys have no cache entry**, so the
> call is a **silent no-op handler that passes its own unit test** (`invalidatequeries-cannot-reach-hand-rolled-state`).
> It invalidates **`['plan-passes', bookId]`** (real) and calls **`reloadPlanRun` / `reloadPlanRuns`** (real).

`usePassRail`'s run-switch guard is satisfied **by construction**: `runId` is in the query key, so a tick for
run A can never write run B's ledger — that is precisely what `genRef` was hand-implementing, and why the NEW
hook needs no `genRef`. **The imperative actions** (`runSelfCheck`, `runValidate`, `runCompile`, and the three
new repair actions) **stay imperative on `usePlanRun`** — they are mutations, not reads, and they call the
hook's own `loadRun()` on success.

**Do NOT skip this and "just invalidate anyway".** A green unit suite over a dead handler is precisely
the bug this repo has shipped four times.

---

## 5 · The slices — X-1 first, then the backend, with their full route contracts

> Every route is on **composition-service**, under the existing `/v1/composition` prefix. The gateway is a
> **pure path-preserving proxy** with a generic `pathFilter` ([`gateway-setup.ts:354`](../../services/api-gateway-bff/src/gateway-setup.ts#L354)) ⇒ **ZERO gateway work.**
> Every route gates with `_gate_book(grant, book_id, user_id, VIEW|EDIT)` **before** touching the service —
> copy the existing helper at [`plan_forge.py:24`](../../services/composition-service/app/routers/plan_forge.py#L24).

---

### 🔴 W5-S0 · X-1 — `AddModelCta` must not tear the dock down (**~30 lines · THE FIRST SLICE**)

> **Register: `Q-35-X1-ADDMODELCTA`.** Answer (b): **X-1 has NOT landed. BUILD IT — do NOT defer, do NOT
> ship the Rail first.** Every paid action in this wave mounts a `ModelPicker`, whose zero-models empty
> state (`ModelPicker.tsx:388`) renders `AddModelCta` — **today a raw `<Link>` that navigates away and
> DESTROYS the dockview layout (DOCK-7).**

**Fix it AT THE SHARED COMPONENT — never at the ~8 call sites.**

| File | Change |
|---|---|
| `frontend/src/components/shared/AddModelCta.tsx` | the studio branch (⚠ **`shared/`**, not `model-picker/`) |
| `frontend/src/components/shared/__tests__/AddModelCta.test.tsx` | keep the 2 MemoryRouter tests; **add** a studio test |

1. `import { useOptionalStudioHost } from '@/features/studio/host/StudioHostProvider';`
2. Inside `AddModelCta()`, after `const location = useLocation()`: `const studioHost = useOptionalStudioHost();`
3. **`if (studioHost)`** → render a `<button type="button" onClick={() => studioHost.openPanel('settings', { params: { tab: 'providers' } })}>` carrying **the SAME className strings** as today's variants (`:46-49` for `variant==='link'`, `:60-63` for the default) and the same `<Plus/>` + `text` children. **No `<a>` is rendered in the studio — the anchor IS what tears the dock down.**
4. **`else`** → keep today's `<Link to={REGISTRATION_PATH…}>` **verbatim, including the `?return=` round-trip** (load-bearing outside the studio — `ProvidersTab` reads `?return=`).
5. Copy the **DOCK-7 rationale comment** from `frontend/src/pages/book-tabs/TranslateModal.tsx:69-78` — the **shipped precedent**: same `openPanel` call, same panel, same params.

**No new infrastructure is needed:** the `settings` panel is registered (`catalog.ts:120`), it honours
`params.tab` (`SettingsPanel.tsx:35-46`), and `'providers'` is a valid `SettingsTabId` (`settings/tabs.tsx:26,39`).

**Tests** — `frontend/src/components/shared/__tests__/AddModelCta.test.tsx`:
- The 2 existing MemoryRouter tests are **unchanged** — they now assert the **non-studio** branch.
- **NEW studio test:** render inside `StudioHostProvider` (mirror the harness at
  `frontend/src/features/studio/statusbar/__tests__/statusItems.test.tsx:55`, which does
  `vi.spyOn(hostRef!, 'openPanel')`). Assert **(i)** `screen.queryByRole('link')` is **null** — *an anchor
  in-studio IS the DOCK-7 bug, and this is the regression pin* — and **(ii)** clicking the button calls
  `openPanel` with exactly `('settings', { params: { tab: 'providers' } })`.

**DoD evidence:** `npx vitest run src/components/shared src/components/model-picker` **green**, **plus a
live-browser check**: open Studio → any panel whose `ModelPicker` empty state shows the CTA → click → **a
`settings` dock TAB opens on the Providers tab and the dock layout SURVIVES.** Only then may the Rail slices
(W5-S12/S13) start.

**dependsOn:** — (fully unblocked; start here)

---

### W5-S1 · BE-20 + BE-21 + BE-22 + **PS-12** — **the ledger tells the truth about itself** (BE, no UI)

> **Register: `Q-35-BE20-LEDGER-FIELDS` · `Q-35-BE21-LIST-NPLUS1` · `Q-35-BE21-TEST-PIN` ·
> `Q-35-F-P3-TWO-TRUTHS` · `Q-35-BE22-PHANTOM-TOOL` · `Q-35-PS12-STUCK-BANNER-PREDICATE`.**
> ⚠ **NAMING HAZARD:** `BE-21` names **two unrelated things**. `BE-21(35)` = this `_serialize_run` fix.
> `BE-21(36)` = the `resolve_model_role` engine reader (Wave 6). **Always write the suffix.**

🔴 **LOAD-BEARING. Without BE-20 the Pass Rail ships an Approve button that 409s forever.**

**Files**

| File | Change |
|---|---|
| `services/composition-service/app/services/plan_pass_service.py` | `derive_view()` — the per-pass dict at `:306-318` |
| `services/composition-service/app/services/plan_forge_service.py` | `_serialize_run()` at `:340-391`; `_assert_seed_applied()` at `:702-705` |
| `services/composition-service/tests/unit/test_genre_tags_plumbing.py` | **replace** the source-text assertion at `:88` |
| `services/composition-service/tests/unit/test_plan_pass_service.py` | new tests |

**Change 1 — BE-20 (the load-bearing one).** In `derive_view`, the per-pass row currently emits
`{pass_id, checkpoint, output_kind, depends_on, status, decision, artifact_id, job_id, fresh, blockers}`
and **stops**. Add **three fields, all of which already exist on the `PassEntry` model**
([`models.py:652-654`](../../services/composition-service/app/db/models.py#L652)) and are already written
by the worker — they are **returned to no client on any transport**:

```python
        passes.append({
            ...,
            "artifact_id": e.get("artifact_id"),
            "job_id": e.get("job_id"),
            # BE-20 (35 F-P4) — STORED BY THE WORKER, RETURNED TO NOBODY. The PF-7 gate
            # (`_assert_seed_applied`) refuses to accept `cast` until this proposal reads
            # `applied` — and the client could not see WHICH proposal to apply. A
            # stored-but-never-returned field is indistinguishable from a dropped one.
            "bootstrap_proposal_id": e.get("bootstrap_proposal_id"),
            "decided_by": e.get("decided_by"),
            "decided_at": e.get("decided_at"),
            # DERIVED — not stored:
            "fresh": is_fresh(run, pid, package_artifact_id=package_artifact_id),
            "blockers": blockers_for(run, pid, package_artifact_id=package_artifact_id),
        })
```

**Why it is load-bearing:** PF-7 ([`_assert_seed_applied`, `plan_forge_service.py:686`](../../services/composition-service/app/services/plan_forge_service.py#L686))
reads `pass_state["cast"]["bootstrap_proposal_id"]`, fetches the proposal, and refuses unless
`status == "applied"`. The proposal is auto-created by the worker
([`job_consumer.py:209`](../../services/composition-service/app/worker/job_consumer.py#L209)) and its id
recorded on the pass entry. Approving/applying it is a 3-route flow the FE **already has**
(`bootstrapGet`/`bootstrapApprove`/`bootstrapApply`, [`api.ts:99-116`](../../frontend/src/features/plan-forge/api.ts#L99)).
Without BE-20 the GUI sees `blocked_at: "cast"`, offers Approve, and gets
`409 CHECKPOINT_REFUSED` **with no way to discover which proposal to apply** (there is no
"list proposals for this run" route — only `GET /plan/bootstrap/{proposal_id}`, which needs the id you
don't have).

**Change 2 — BE-21 (the run detail LIES about freshness).** `_serialize_run` at `:383` calls
**`**derive_view(run)`** — with **no `package_artifact_id`**. The other two call sites pass the real id
(`pass_status` at `:1016`, `run_pass` at `:1216`). For the 5 passes with `reads_package=True`, the package
artifact id **is one of the fingerprint inputs**
([`plan_pass_service.py:180-181`](../../services/composition-service/app/services/plan_pass_service.py#L180)),
so with `None` the pointer resolves to `""`, the recomputed fingerprint can never match, and:

- every package-reading pass reports **`fresh: false`** — 5 of 7, including `motifs`, the first;
- `pass_cursor` breaks at the first non-fresh pass ⇒ it reports **0, always**;
- `blockers[]` on every downstream pass names upstreams that are actually fine.

`_serialize_run` backs **`GET /runs/{id}`, `GET /runs` (LIST), `POST /checkpoint`, and
`PATCH /novel-system-spec`.** So `GET /runs/{id}` says *"nothing is fresh"* about the very same run
`GET /runs/{id}/passes` correctly reports as five passes deep. **Two producers of one truth, disagreeing.**

🔴 **THE FIX — and it adds ZERO QUERIES (C-4 / §0.3).** The plan's first draft said *"add a
`latest_artifact()` call"* — **that would create an N+1 inside the LIST loop for no reason.** The package id
is **ALREADY IN HAND**: `list_artifact_refs` (`plan_runs.py:351`) is
`SELECT DISTINCT ON (a.kind) a.kind, a.id AS artifact_id … ORDER BY a.kind, a.created_at DESC` — **the latest
artifact id PER KIND**, which is *exactly* what `latest_artifact(kind=PACKAGE_KIND)` resolves. Read it from
the list `_serialize_run` already fetched at `:348`.

**Build ONE producer (F-P3) as a PURE function that TAKES the id, and let each caller supply it the cheapest
way it already can:**

```python
    # plan_forge_service.py — line 21: extend the EXISTING module-level import
    from app.services.plan_pass_service import PACKAGE_KIND, derive_view

    def _pass_view(self, run: PlanRun, package_artifact_id: UUID | str | None) -> dict[str, Any]:
        """THE ONE derived pass view (BE-21(35) / F-P3). `_serialize_run` used to call
        `derive_view(run)` with NO package id, so the five `reads_package` passes re-fingerprinted
        against "" and read STALE forever: cursor 0, blockers naming upstreams that were fine —
        while `GET …/passes` reported the same run correctly. TWO PRODUCERS OF ONE TRUTH.
        One derivation, one input. PURE + sync: it takes the id, it does not fetch it."""
        return {
            "compiled": package_artifact_id is not None,
            **derive_view(run, package_artifact_id=package_artifact_id),
        }

    async def _serialize_run(self, created_by: UUID, run: PlanRun, *, include_source: bool = False):
        artifacts = await self._runs.list_artifact_refs(run.book_id, run.id)   # :348 — ALREADY THERE
        ...
        # BE-21(35) — ZERO new queries. `list_artifact_refs` is DISTINCT ON (kind) ORDER BY created_at
        # DESC, i.e. the latest id PER KIND — the package pointer is already in the list we hold.
        # Do NOT add `latest_artifact(..., PACKAGE_KIND)` here: `list_runs` calls this in a LOOP.
        package_artifact_id = next(
            (a["artifact_id"] for a in artifacts if a["kind"] == PACKAGE_KIND), None,
        )
        return {
            ...,
            **self._pass_view(run, package_artifact_id),   # was: **derive_view(run),
            ...
        }
```

⚠ **Pass the raw asyncpg UUID — do NOT `str(...)` it.** `derive_view` accepts `UUID | str | None` and
normalises via `str(package_artifact_id or "")` (`plan_pass_service.py:181`) — **identical** to what
`pass_status` passes. An empty-string-vs-`None` divergence is how this bug class *starts*.

**And route the OTHER producer through the same helper.** In `pass_status` (`:1002-1016`), keep its existing
`latest_artifact` fetch (it does **not** call `list_artifact_refs`, so it has no cheaper source) but **delete
its inline `derive_view` call** and use `**self._pass_view(run, package.id if package else None)`.
`GET …/passes` keeps **the exact response shape it has today** (`compiled` now comes from the helper).
**Leave `run_pass` (`:1216`) alone** — it already holds `package_id` for the PF-5 gate and derives correctly.

This one edit fixes **`GET /runs/{id}`, `GET /runs` (LIST), `POST /checkpoint` and `PATCH /novel-system-spec`
at once** — all four route through `_serialize_run` (`:326, :337, :409, :611, :684`).

⚠ **Belt and braces:** the Pass Rail still reads `GET …/passes` — **one producer in the BE, one consumer read
in the FE.** After **ANY** mutation (`POST /checkpoint`, `POST /passes/{id}/run`, `PATCH /novel-system-spec`),
the Rail **IGNORES the response's pass block and refetches `/passes`.** Do not thread a mutation response into
Rail state, even after BE-21 lands.

**Change 3 — BE-22 (a live error message names a tool that does not exist).**
[`plan_forge_service.py:702-705`](../../services/composition-service/app/services/plan_forge_service.py#L702):

```python
            raise ValueError(
                "cast cannot be accepted before its glossary seed proposal exists "
                "(call plan_bootstrap_seed for this pass first)",   # ← plan_bootstrap_seed DOES NOT EXIST
            )
```

`grep -rn plan_bootstrap_seed services/` returns **exactly one hit: this string.** No MCP tool, no route,
no method. The real producer is the worker (`job_consumer.py:209-215` — `_propose_pass_seed` is the **only**
writer of `bootstrap_proposal_id`, and it fires only as a side effect of the plan-pass job). The real
recovery is **re-run the `cast` pass** via `plan_run_pass` (`mcp/server.py:3567` — the **sole** entry point).

🔴 **C-5 — KEEP THE LEADING CLAUSE.** `test_plan_pass_checkpoint.py:111` **asserts the substring
`"before its glossary seed proposal exists"`.** The plan's first-draft rewrite dropped it and would have
REDded a shipped test. Replace **only the phantom parenthetical** (`Q-35-BE22-PHANTOM-TOOL`, verbatim):

```python
            raise ValueError(
                "cast cannot be accepted before its glossary seed proposal exists — re-run the "
                "'cast' pass (plan_run_pass with pass_id='cast') to propose it. The proposal is "
                "opened by the pass job itself; there is no standalone seeding call.",
            )
```

⚠ **Keep it under 300 chars** — `plan_run_pass` truncates `detail` at `[:300]` (`mcp/server.py:3629`).
**Do NOT add a seeding tool/route.** BE-22 is explicitly *"no new route"*, and seed-on-pass is deliberate
(`job_consumer.py:199-208` documents PF-7: **one** approval mechanism, not two).
**Leave the other two branches alone** — `:708` (proposal vanished) and `:709-713` (*"apply it first (PF-7)"*)
already name real recoveries; the apply route exists at `routers/plan_bootstrap.py:113`.

---

**Change 4 — 🔴 PS-12: `blocked_at` LIES, and the AGENT reads it too (C-6).**

> `Q-35-PS12-STUCK-BANNER-PREDICATE` **overrides** the plan's first draft (which derived the fix in the
> panel). **Fix it AT THE SOURCE. The FE derives NOTHING.**

**THE INVARIANT:** `blocked_at` must be defined **in terms of `is_accepted`**, so *"am I stuck"* and *"may
this pass's dependents run"* **cannot disagree by construction.** Today they do: `blocked_at` matches
`decision == "pending"` (`plan_pass_service.py:288`) while `is_accepted` matches
`decision in ("accepted","auto")` (`:218`). **Those are not complements — the gap is `rejected`, which is
exactly what `approved:false` writes** (`plan_forge_service.py:673`). This is the same reasoning PF-7 already
applies: *"the blocking gate and the mutation gate are the same gate, so they cannot disagree"* (`:688`).

**`services/composition-service/app/services/plan_pass_service.py:277-291`** — replace the body of `blocked_at()`:

```python
    for pid in PASS_ORDER:
        e = _entry(run, pid)
        if e.get("status") == "completed" and not is_accepted(run, pid):
            return pid
    return None
```

**Drop the `checkpoint == "blocking"` clause.** Docstring: *"The first COMPLETED pass a human has not
settled — pending OR rejected, any checkpoint class. Defined via `is_accepted` so the stuck-signal and the
dependency gate cannot disagree. A never-run/running/failed pass is NOT `blocked_at` — it waits on a RUN, not
on a human. DERIVED; never stored."*

⚠ **WHY NOT BLOCKING-ONLY (the hole the panel-side fix misses):** `_review_pass` accepts **ANY** `pass_id`
with **no checkpoint-class check** (`:613-622`), so Save-edits on an **ADVISORY** pass also writes `rejected`.
`character_arcs` is advisory (`:72-75`) and **`scenes` depends_on it** (`:76-80`) ⇒ a rejected `character_arcs`
blocks `scenes` **forever**, while a blocking-only predicate names **nothing**. Same silent stall, one
pass-class over.

**MIGRATION RISK: NONE.** `blocked_at` is computed on read, has exactly one producer (`derive_view:322`), has
no persisted copy, and **no runner consumes it** (the runner gates on `assert_runnable`/`blockers_for`) — so
widening it cannot change execution, only make the report truthful. It **also** fixes the agent:
`plan_pass_status` ships `blocked_at` to agents as *"the pass a human must accept next"* (`server.py:3632-3639`),
so today an agent asked *"what is blocking the plan"* on a rejected run answers **"nothing"**. That is GG-1's
parity law failing on the agent side. Optionally tighten `server.py:3637`'s description to *"(pending or
rejected)"*.

**Tests — TDD order, failing test first.**

`services/composition-service/tests/unit/test_plan_pass_service.py` (add; it is a pure-function file, **no
DB** ⇒ **no `xdist_group` mark needed**):

1. `test_derive_view_emits_the_seed_proposal_id_the_PF7_gate_reads` — build a `PlanRun` whose
   `pass_state["cast"]` carries `bootstrap_proposal_id`, `decided_by="user"`, `decided_at="…"`; assert
   `derive_view(run)["passes"][1]` contains all three keys with those values, **and that a NEVER-RUN pass
   returns `None` for all three** (*absent ≠ dropped*). **RED before the change.**
2. `test_the_dependency_graph_is_not_the_pass_order` (**F-P12 — this test exists because spec 35's own
   first draft got all three wrong**): on a run with `motifs` accepted+fresh and `cast` completed+pending,
   assert `blockers_for(run, "world", package_artifact_id=pkg) == ["cast"]`,
   `blockers_for(run, "beats", package_artifact_id=pkg) == []`,
   `blockers_for(run, "scenes", …) == ["cast", "beats", "character_arcs"]` (motifs is accepted ⇒ filtered;
   `depends_on` order preserved), and `pass_cursor(run, package_artifact_id=pkg) == 1`.
   ⚠ **TRAP:** `motifs` has `reads_package=True`, so **record its fingerprint WITH the package id** —
   `fingerprint(input_artifact_ids=input_pointers(run, "motifs", package_artifact_id=pkg), params={})` — and
   assert with the **SAME** `pkg`. Otherwise motifs reads non-fresh, the cursor collapses to 0, and the test
   happily "proves" the wrong number.
3. 🔴 **PS-12 — the three tests that replace the phantom.** **DELETE**
   `test_an_ADVISORY_pass_pending_does_not_block` (`test_plan_pass_service.py:217`) — it pins an
   **unreachable** state: `job_consumer.py:220` is the only writer of a completed pass's decision and always
   writes `default_decision()`, which is `"auto"` for advisory. **Replace with:**
   - **(a)** `test_a_REJECTED_blocking_pass_is_STILL_blocked_at` — cast completed, `decision="rejected"` ⇒
     **`blocked_at(run) == "cast"`** *(this is F-P10 — and note it is the OPPOSITE of what the plan's blind
     draft asserted)*.
   - **(b)** `test_a_REJECTED_advisory_pass_is_blocked_at_too` — `character_arcs` completed,
     `decision="rejected"` ⇒ `blocked_at(run) == "character_arcs"` **AND**
     `"character_arcs" in blockers_for(run, "scenes", …)`.
   - **(c)** `test_blocked_at_AGREES_with_is_accepted` — for any run: if some completed pass is
     `not is_accepted` ⇒ `blocked_at is not None`. **Pins the INVARIANT, not the surprise.**
   Tests at `:206` (pending⇒cast), `:212` (accepted⇒None), `:234`/`:248` (derive_view) are unchanged and
   **must stay green**.

`services/composition-service/tests/unit/test_genre_tags_plumbing.py` — **the pinning test that asserts the
BUG.** `:88`'s `assert "**derive_view(run)" in src` goes RED the moment BE-21(35) lands. **DELETE it** (and
convert the `'"genre_tags": run.genre_tags' in src` line to a behavioural round-trip too) and replace the
whole `test_the_serialized_run_RETURNS_genre_tags_and_the_derived_pass_view` with ONE behavioural async test:

4. `test_the_run_detail_reports_the_SAME_pass_cursor_as_the_passes_endpoint` — build a run with a `motifs`
   entry whose fingerprint was recorded **WITH** a package id `PKG`; stub `list_artifact_refs` to return
   `[{"kind": "package", "artifact_id": PKG}]`; then:
   ```python
   detail = await svc.get_run_detail(USER, BOOK, run.id)
   passes = await svc.pass_status(USER, BOOK, run.id)
   assert passes["pass_cursor"] == 1                       # ⚠ MANDATORY — see below
   assert detail["pass_cursor"] == passes["pass_cursor"]   # …and the detail must AGREE
   assert {p["pass_id"]: p["fresh"] for p in detail["passes"]}["motifs"] is True
   assert detail["genre_tags"] == ["xianxia"]              # PF-15 round-trip, behaviourally
   ```
   🔴 **`assert passes["pass_cursor"] == 1` IS MANDATORY.** The equality assertion **ALONE IS VACUOUS** —
   `0 == 0` passes happily if the fixture is wrong and the package is never seen. **Pinning the non-zero
   value is what makes this test actually RED without BE-21(35).** *Verify it: comment out the fix, run it,
   watch it fail `0 != 1`.* Harness notes (verified): `sync_from_job` early-returns on `active_job_id=None`
   (no `jobs` setup needed); `list_artifact_refs` must return a **list**, not a bare `AsyncMock`;
   `pass_state` is `dict[str, PassEntry]` ⇒ **attribute** assignment, not subscript. Harness to copy:
   `tests/unit/test_plan_forge_default_model.py:41-64`.

`services/composition-service/tests/unit/test_plan_pass_checkpoint.py` (**it already seeds `pass_state`
directly at `:412`** — this is the TRANSPORT half, and it is required):

5. `test_the_passes_endpoint_RETURNS_the_bootstrap_proposal_id` — assert the **`GET …/passes` response
   body**'s `cast` row contains `bootstrap_proposal_id`. **A unit test on `derive_view` alone cannot prove
   the transport didn't strip it** — *"written by the worker, returned by nothing"* is precisely the bug
   class here (repo lesson: *"REST mirror drops fields the MCP tool accepts"*).
6. `test_seed_gate_message_names_a_real_recovery` — assert the refusal detail **still contains**
   `"before its glossary seed proposal exists"` (C-5), **contains `"plan_run_pass"`**, and does **NOT**
   contain `"plan_bootstrap_seed"`.

**DoD evidence:** `python -m pytest tests -q -n auto --dist loadgroup` — paste the actual tail. Plus:
`grep -rc plan_bootstrap_seed services/ == 0`. ⚠ **Do NOT assert a total test count** — the baseline drifts
under concurrent waves; assert the **named tests** are present and green.

**dependsOn:** —

---

### W5-S2 · BE-3 — the artifact **body** read route (**it exists in NO transport today**)

🔴 **There is no artifact-read path in ANY transport.** No REST route, and no `plan_get_artifact` MCP tool.
The run detail returns `[{kind, artifact_id}]` **metadata only**
([`plan_forge_service.py:385-388`](../../services/composition-service/app/services/plan_forge_service.py#L385)).
**The body of the plan the user just paid an LLM to write is unreachable — by the GUI, and by the agent.**

**Route contract**

```
GET /v1/composition/books/{book_id}/plan/runs/{run_id}/artifacts/{artifact_id}
  grant:    VIEW (via _gate_book)
  request:  —  (path params only; artifact_id typed UUID ⇒ FastAPI 422s a malformed id)
  200:      { "artifact_id": str, "run_id": str, "kind": str,
              "content": {...}, "created_at": ISO8601|null }
  404:      run not found · artifact not found · artifact belongs to ANOTHER BOOK
            ⚠ ALL THREE are the SAME 404 with the SAME body. No enumeration oracle (H13).
  403:      insufficient grant (handled by _gate_book)
```

**Files**

| File | Change |
|---|---|
| `services/composition-service/app/services/plan_forge_service.py` | **new method** `get_artifact()` |
| `services/composition-service/app/routers/plan_forge.py` | **new route** (place it right after `pass_status_route`, ~`:250`) |

```python
    # plan_forge_service.py — new method
    async def get_artifact(
        self, created_by: UUID, book_id: UUID, run_id: UUID, artifact_id: UUID,
    ) -> dict[str, Any] | None:
        """BE-3 (35 F-P2). The artifact BODY — unreachable by any client before this.

        Scoped through `artifacts_by_ids`, whose `JOIN plan_run r ON r.id = a.run_id
        WHERE r.book_id = $2` IS the tenancy boundary (`plan_artifact` carries no book_id of its
        own). A foreign artifact id simply does not come back ⇒ the same 404 as a missing one,
        with no enumeration oracle (H13).
        """
        loaded = await self._runs.artifacts_by_ids(book_id, run_id, [artifact_id])
        art = loaded.get(str(artifact_id))
        if art is None:
            return None
        return {
            "artifact_id": str(art.id),
            "run_id": str(art.run_id),
            "kind": art.kind,
            "content": art.content,
            "created_at": art.created_at.isoformat() if art.created_at else None,
        }
```

```python
    # plan_forge.py — new route
    @router.get("/books/{book_id}/plan/runs/{run_id}/artifacts/{artifact_id}")
    async def get_plan_artifact(
        book_id: UUID, run_id: UUID, artifact_id: UUID,
        user_id: UUID = Depends(get_current_user),
        grant: GrantClient = Depends(get_grant_client_dep),
        svc: PlanForgeService = Depends(get_plan_forge_service),
    ):
        await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
        out = await svc.get_artifact(user_id, book_id, run_id, artifact_id)
        if out is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return out
```

**Do NOT add a repo method.** [`PlanRunsRepo.artifacts_by_ids(book_id, run_id, ids)`](../../services/composition-service/app/db/repositories/plan_runs.py#L265)
already exists, is already book-scoped through the run join, and is already review-hardened. This route is
a **wrapper**.

🔴 **HARD RULES the builder must not "improve"** (`Q-35-BE3-ARTIFACT-READ`):
**(a)** Do **NOT** pre-check that the run exists and do **NOT** branch on cross-book. **ONE 404** covers
run-not-found + artifact-not-found + cross-book-artifact. **Emitting 403 for a foreign `artifact_id` is an
enumeration oracle and violates H13.**
**(b)** Path params stay typed `UUID` ⇒ a malformed id **422s at FastAPI** before touching the DB.
**(c)** **READ-ONLY.** No PATCH/PUT/DELETE on this path, ever.
**(d)** Body is `content` **as-is (a dict)** — do NOT re-serialise it to a string.
**(e)** `created_by` is an **actor stamp, never a filter** (PM-5).

---

#### 🔴 BE-3c — `plan_get_artifact`, the MCP tool (**BUILD IT — the deferral's reason was FALSE, C-11**)

> `Q-35-OQ3-PLAN-GET-ARTIFACT-MCP`: **BUILD IT IN WAVE 5, in the SAME slice as BE-3.** The plan's blind draft
> deferred it as *"a 3-schema-source FastMCP change"* — **that is knowledge-service's shape, not
> composition's.** `grep TOOL_DEFINITIONS services/composition-service/app` → **0 hits**: composition
> registers every tool through the `@mcp_server.tool` decorator only, so **the function signature IS the
> advertised inputSchema — ONE schema source.** The repo method exists and is already tenancy-hardened; the
> service wrapper is being written **in this very slice**. ~35 lines in a file the wave already opens.
> **CLAUDE.md:** *"if fixing is cheaper than writing + carrying its defer row, just fix it."* And GG-2 (the
> agent can't read what the human can) is **in-register law**, not a nicety.

**File:** `services/composition-service/app/mcp/server.py` — in the `plan_*` block, **after `plan_self_check`
(~`:3380`)**, Tier-**R**:

```python
@mcp_server.tool(
    name="plan_get_artifact",
    description=(
        "PlanForge: read the BODY of one plan artifact — the JSON a pass produced "
        "(spec, motif_plan, cast_plan, world_plan, beat_plan, char_arc_plan, scene_plan, "
        "link_report). Get artifact ids from `plan_pass_status` or the run detail's "
        "`artifacts` refs (latest per kind). Pass `path` (dot-path, e.g. 'cast.0.name') "
        "to fetch a subtree of a large body. VIEW on the book required."
    ),
    meta=require_meta("R", "book",
        synonyms=["read the plan", "show the cast plan", "artifact body",
                  "what did the pass output", "open the scene plan"],
        tool_name="plan_get_artifact"),
)
async def plan_get_artifact(
    ctx: MCPContext,
    book_id: Annotated[str, "The book (UUID)."],
    run_id: Annotated[str, "The plan run that owns the artifact (UUID) — required; the run join IS the artifact's scope."],
    artifact_id: Annotated[str, "The artifact (UUID)."],
    path: Annotated[str | None, "Optional dot-path into the body (e.g. 'cast.0.name') — returns that subtree only."] = None,
    max_tokens: Annotated[int, "Cap on the returned body (clamped 500..20000)."] = 6000,
) -> dict:
    tc = _ctx(ctx); bid = UUID(book_id)
    await _gate(tc, bid, GrantLevel.VIEW)
    art = await _plan_svc().get_artifact(tc.user_id, bid, UUID(run_id), UUID(artifact_id))
    if art is None:
        raise uniform_not_accessible()   # cross-book or unknown → SAME denial (H13, no oracle)
    ...
```

**It calls the SAME `get_artifact()` service method BE-3 adds — one repo method, two front doors.** Never
re-query the repo from the tool, and **never drop `run_id`**: `plan_artifact` has no `book_id`; the
`JOIN plan_run r ON r.id = a.run_id WHERE r.book_id = $2` **IS** its tenancy boundary.

**Return shape (OUT-1/2/5):** `{artifact_id, kind, created_at, content}`. When the serialised body exceeds
the clamped `max_tokens`: return `{..., "content": None, "oversized": True, "size_tokens": <n>,
"top_level_keys": [...], "guidance": "pass path=<key> to fetch a subtree"}` — 🔴 **REPORT THE CAP, NEVER A
SILENTLY TRUNCATED JSON BODY** (OUT-5; the 146K-token `composition_list_outline` incident is the precedent).
`path` resolves dot-path segments (an int segment = a list index); an unresolvable path returns
`{"error": "PATH_NOT_FOUND", …}`, **not a silent `None`**.

⚠ **There is deliberately NO `plan_put_artifact`.** The only sanctioned artifact write is the `edits`
deep-merge on `plan_review_checkpoint`, which **re-fingerprints**. A second write door would be an
un-fingerprinted mutation path — the same reason the human viewer is read-only (FE-1).
`contracts/tool-liveness.json` needs **no hand edit** — it is a sweep OUTPUT, regenerated.

**Tests** — `services/composition-service/tests/unit/test_plan_forge_router.py` (extend the existing fake-svc
harness; `test_get_plan_run` at `:93` is the template. **`pytestmark = pytest.mark.xdist_group("pg")` if it
touches the real DB**):

- **200** — returns **exactly** `{artifact_id, run_id, kind, content, created_at}`: **assert the KEY SET**,
  not just the status.
- **404 unknown `artifact_id`** (fake repo returns `{}`).
- 🔴 **404 cross-book** — fake `artifacts_by_ids` returns `{}` when `book_id` != the run's owner; assert
  `resp.status_code == 404` **AND `resp.status_code != 403`**, with a comment naming **H13**. *This is the
  test that pins the no-oracle property.*

`services/composition-service/tests/unit/test_mcp_server.py` — **BOTH edits or the drift guard doesn't fire:**
add `"plan_get_artifact"` to the **expected tool-name set** (the Tier-R plan line at `:97`) **and** to
**`TIER_R`** (`~:108-118`). It stands up an in-process FastMCP app, so it also proves the advertised
inputSchema carries `run_id`/`artifact_id`/`path`/`max_tokens`.

New MCP cases (`tests/unit/test_plan_forge_mcp.py` or the same file): **(a)** an `artifact_id` from another
book ⇒ **uniform not-accessible, the same shape as an unknown id**; **(b)** an oversized body ⇒
`oversized: true`, `content is None`, `size_tokens` present — **assert it is NOT a truncated body**;
**(c)** `path` selects a subtree.

**DoD evidence:** composition suite green (paste the tail) + a **curl** against the dev stack returning a real
`content` body + the **GG-2 live-smoke line**: *"an agent turn calls `plan_get_artifact` on the same run the
`json-editor` viewer reads and gets the same body."* **The loop is only closed when both halves read the same
bytes.**

**FRONTEND (in this slice):** `frontend/src/features/plan-forge/api.ts` gains
`getPlanArtifact(bookId, runId, artifactId, token)` (mirror the `getPlanRun` line at `api.ts:50`), and
`types.ts` gains `export interface PlanArtifact { artifact_id: string; run_id: string; kind: string; content: unknown; created_at: string | null }`.

**SCOPE FENCE:** BE-3b is a **separate** slice (W5-S3) — do not couple it to this route.

**dependsOn:** —

---

### W5-S3 · BE-3b — the run detail returns its own source

[`plan_runs.py:23-27`](../../services/composition-service/app/db/repositories/plan_runs.py#L23) **selects
`source_markdown` on every run read.** `_serialize_run` returns `source_checksum` and **not**
`source_markdown`. So *"the source markdown does not resume when you reopen a run"* is **NOT an FE bug** —
**the FE cannot resume what the API never sends.** It is a one-line contract widening.

🔴 **BUT IT IS OPT-IN, NOT UNCONDITIONAL (C-8 · `Q-35-BE3B-SOURCE-MARKDOWN`).** `_serialize_run` is
**shared** — by `list_runs` (**one call per list item**) and by the **MCP tool result**
(`mcp/server.py:3327` returns `"run": detail` from `plan_propose_spec`). `source_markdown` is capped at
**262,144 chars** (`plan_forge.py:38`). Unconditional ⇒ a 256 KiB body multiplied across a list page, **and
echoed straight back into the LLM's own tool result — the markdown it just SENT.** That is a **Context Budget
Law violation, on this very branch.**

**Files**

| File | Change |
|---|---|
| `services/composition-service/app/services/plan_forge_service.py` | `_serialize_run(self, created_by, run, *, include_source: bool = False)` — build the dict as today, then **`if include_source: payload["source_markdown"] = run.source_markdown`**. (`PlanRun.source_markdown` is a non-null `str` defaulting to `""` — `models.py:678` — so no `None` handling.) **Comment WHY it is opt-in.** |
| `services/composition-service/app/services/plan_forge_service.py:326` | **`get_run_detail` is the ONLY caller that opts in:** `return await self._serialize_run(created_by, run, include_source=True)` |
| — | **LEAVE on the default `False`:** `:337` (`list_runs`, per item), `:611` and `:684` (review/pass responses). This automatically keeps it out of MCP `plan_propose_spec`. |
| `frontend/src/features/plan-forge/types.ts` | `PlanRunDetail` → **`source_markdown?: string;`** — ⚠ **OPTIONAL, not `string`.** The list truly **omits the key**; a required field would make `PlanRunListPage.items: PlanRunDetail[]` **lie**. Comment: *present on `GET /runs/{id}` (and `POST /runs` → detail); omitted on list items.* |

**Tests** — `test_plan_forge_router.py`:
- **(a)** `test_run_detail_round_trips_source_markdown` — `GET /runs/{id}` carries `source_markdown`
  **byte-equal** to what `POST /runs` was given.
- 🔴 **(b)** `test_the_list_page_item_does_NOT_carry_source_markdown` — assert the key is **absent**.
  *This is the assertion that pins the flag and stops a later "helpful" widening from re-introducing the
  blowup.*

**DEFAULT ON RECORD (PO may veto):** the list page stays lean. If a future *"runs gallery with source
preview"* wants it, the answer is a **truncated `source_preview` field**, not the full column.

**DoD evidence:** composition suite green (paste the tail), **including test (b)**.

**dependsOn:** —

---

### W5-S4 · BE-2 — the autofix REST mirror (**200 `{rounds, run}`, NOT a 202 ack — see §0.2 C-1**)

`handoff_autofix` is fully implemented at
[`plan_forge_service.py:817`](../../services/composition-service/app/services/plan_forge_service.py#L817)
and exposed **only** as an MCP tool. GG-1: the agent can, the human cannot.

**Route contract** — 🔴 **the spec's ack shape is WRONG, and so was this plan's "NEVER a 202" (C-7).
`Q-35-BE2-AUTOFIX-ROUTE` is the right one — MIRROR THE SERVICE:**

```
POST /v1/composition/books/{book_id}/plan/runs/{run_id}/autofix
  grant:    EDIT
  request:  { "model_ref": UUID|null, "max_rounds": int = 3 }   # ge=1, le=5 → 422, NOT a silent clamp
  200:      { "rounds": [ {"round": int, "targets": int, "result": str|null}, ... ],
              "run":    <PlanRunDetail> }                        # the SYNC path (worker off) — loop finished
  202:      SAME BODY, when `run.active_job_id` is set                # the WORKER path — round 1 enqueued
  400:      ValueError ("no spec to refine" / no default planner model)
  403:      insufficient grant   ·   404: run not found (service returned None)

  ⚠ The spec's "202 {run_id, job_id, status} mirroring /refine" DOES NOT EXIST. `handoff_autofix`
    (plan_forge_service.py:817) ALWAYS returns {"rounds": [...], "run": <detail>} — it only breaks early
    (still returning that dict) when the worker is on and round 1 enqueues.
  ⚠ But "always 200" is ALSO wrong: 200 on a run with a live job LIES about being done.
    run_id / job_id / status are all INSIDE `run` (id, active_job_id, job_status) — plus `rounds`,
    which M3's R3 Repair strip needs to render WHAT was fixed. A bare ack would throw that away.
```

**Files**

| File | Change |
|---|---|
| `services/composition-service/app/routers/plan_forge.py` | new `PlanAutofixRequest` (after `PlanRefineRequest`, `:58`) + the route (after `refine_plan_run`, ends `:222`) |
| 🔴 `contracts/api/composition-service/plan-forge.v1.yaml` | **CONTRACT-FIRST — the route goes in the spec BEFORE the FE consumes it.** See **W5-S6c**. |

```python
class PlanAutofixRequest(BaseModel):
    """HTTP mirror of MCP `plan_handoff_autofix` (mcp/server.py:3490). `model_ref` is OPTIONAL —
    the service resolves the author's default planner model (plan_forge_service.py:123)."""
    model_ref: UUID | None = None
    max_rounds: int = Field(default=3, ge=1, le=5)   # closed range → 422, not a silent clamp


@router.post("/books/{book_id}/plan/runs/{run_id}/autofix")
async def autofix_plan_run(
    book_id: UUID, run_id: UUID, body: PlanAutofixRequest,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    svc: PlanForgeService = Depends(get_plan_forge_service),
):
    """BE-2 — the human's door to `plan_handoff_autofix` (MCP-only before this: GG-1)."""
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    try:
        out = await svc.handoff_autofix(
            user_id, book_id, run_id, model_ref=body.model_ref, max_rounds=body.max_rounds,
        )
    except ValueError as exc:            # "no spec to refine" / no default planner model
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if out is None:                      # the run isn't in this book
        raise HTTPException(status_code=404, detail="run not found")
    run = out.get("run") or {}
    # 202 ONLY when the worker path enqueued round 1 and the loop stopped (the run carries a live job).
    # The default worker-off path already finished the loop → 200. SAME BODY either way.
    if run.get("active_job_id"):
        return JSONResponse(status_code=202, content=out)
    return out                           # 200 {"rounds": [...], "run": {...}}
```

**Tests** — `test_plan_forge_router.py`. Add to `StubPlanForge` an
`async def handoff_autofix(self, owner_user_id, book_id, run_id, **kwargs)` returning `None` when
`run_id != RUN`, else `{"rounds": [{"round": 1, "targets": 2, "result": "applied"}], "run": await self.get_run_detail(...)}`. **Five cases, all required:**

1. `test_autofix_returns_rounds_and_run_not_an_ack` — **200**, `body["rounds"][0]["result"] == "applied"`,
   `"rounds" in body and "run" in body`, and **`"job_id" not in body`**. *(Pins C-1 so nobody "fixes" it back
   to a bare 202 ack.)*
2. 🔴 `test_autofix_is_202_when_the_worker_enqueued` — a stub whose run detail has `active_job_id` set ⇒
   **202**, **same body shape**. *(Pins C-7 so nobody "fixes" it back to an unconditional 200.)*
3. `test_autofix_unknown_run_is_404`.
4. `test_autofix_max_rounds_out_of_range_is_422` — `max_rounds: 0` **and** `9` ⇒ 422.
5. `test_autofix_view_only_grant_is_403` — `StubGrant` returning `GrantLevel.VIEW` ⇒ 403.

**OUT OF SCOPE for BE-2:** the FE client method — **W5-S10's R3 Repair strip adds it and consumes `rounds`.**

**DoD evidence:** composition suite green (paste the tail), **including cases 1 AND 2**.

**dependsOn:** W5-S6c (contract-first)

---

### W5-S5 · BE-4 + BE-4b — archive a plan run **AND restore it** (PS-13 — they ship TOGETHER)

Failed LLM runs accumulate forever: `grep "@router.delete"` across `plan_forge.py` + `plan_bootstrap.py`
returns **nothing**.

🔴 **BE-4 does NOT ship without BE-4b.** Every sibling soft-delete in this service (`outline_node`, `motif`,
`structure_node`, `arc_template`) has a **restore**. Plan 30 files "delete with no undo" as a defect in its
own right (**BE-11**, against `canon_rule`). Shipping the same shape here would be knowingly repeating it.

#### Migration

**File:** `services/composition-service/app/db/migrate.py` — append to the PlanForge v2 block, **after**
line 1316 (`ALTER TABLE plan_run ADD COLUMN IF NOT EXISTS genre_tags …`):

```sql
-- 35 BE-4/BE-4b — SOFT archive for plan runs (a failed LLM run is a per-book, per-user artifact
-- the user must be able to clear). Soft, to match every sibling in this service (outline_node,
-- motif, structure_node, arc_template) — and BE-4b's restore ships WITH it, because a Delete
-- button with no undo is a one-way destructive action (plan 30 BE-11).
--
-- ADDITIVE and default-correct: every EXISTING plan_run is active, so DEFAULT FALSE is right for
-- them and NO BACKFILL is needed. (⚠ `ADD COLUMN IF NOT EXISTS` never revisits a default on an
-- already-migrated DB — so the default must be right the FIRST time. It is.)
-- No CHECK constraint is touched ⇒ no historical-value backfill applies here.
ALTER TABLE plan_run ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_plan_run_book_created_active
    ON plan_run(book_id, created_at DESC) WHERE NOT is_archived;
```

🔴 **The partial index IS required** (`Q-35-BE4-ARCHIVE-MIGRATION` + `Q-35-BE4B-RESTORE-COUPLED` both
specify it — the plan's blind draft said *"no new index"*). It mirrors the shipped idiom on
`outline_node` / `canon_rule` / `structure_node` (`migrate.py:209/257/1122`, partial-index at `:216`) and it
is what makes the **new default predicate** (`WHERE NOT is_archived`, now on **four** reads, below) index-only.

#### Route contracts

```
DELETE /v1/composition/books/{book_id}/plan/runs/{run_id}          # ARCHIVE (soft)
  grant:  EDIT
  204:    (no body).  An ALREADY-archived run is still FOUND ⇒ 204. Idempotent.
  409:    { "code": "PLAN_RUN_JOB_IN_FLIGHT", "active_job_id": "<uuid>" }   ← mirrors engine.py:1056
          ⚠ DO NOT orphan a running worker job.
  404:    run not found        ·   403: insufficient grant

POST /v1/composition/books/{book_id}/plan/runs/{run_id}/restore
  grant:  EDIT
  200:    <PlanRunDetail>  (with is_archived: false)
  404:    run not found OR not archived
  403:    insufficient grant

GET /v1/composition/books/{book_id}/plan/runs?include_archived=true
  grant:  VIEW
  200:    { items: [...], next_cursor }   # DEFAULT (absent/false) ⇒ archived rows are FILTERED OUT
```

#### Files

| File | Change |
|---|---|
| `app/db/migrate.py` | the DDL above (**column + partial index**) |
| `app/db/models.py` | `PlanRun` (~`:679`) → `is_archived: bool = False` |
| 🔴 `app/db/repositories/plan_runs.py` | **SIX changes — and three of them are the ones a BE-4-only build gets WRONG.** See below. |
| `app/db/repositories/generation_jobs.py` | **new** `active_among(job_ids, book_id, statuses, since)` — the two-carrier in-flight probe |
| `app/services/plan_forge_service.py` | `_serialize_run` → `"is_archived": run.is_archived` · **new** `archive_run()` / `restore_run()` · `list_runs(..., include_archived)` |
| `app/routers/plan_forge.py` | the 2 new routes + `include_archived: bool = Query(default=False)` on `list_plan_runs` (`:131`) |
| 🔴 `contracts/api/composition-service/plan-forge.v1.yaml` | **CONTRACT-FIRST** — see **W5-S6c** |

#### 🔴 `plan_runs.py` — the four reads that need the filter (`Q-35-BE4B-RESTORE-COUPLED` 3a–3f)

| # | Method | Change | Why it is NOT optional |
|---|---|---|---|
| **a** | `_SELECT_RUN` (`:23-27`) | add `is_archived` | A column not in the SELECT **validates as the model default and LIES**. |
| **b** | `list_for_book` (`:128`) | kwarg `include_archived: bool = False`; when False append **`NOT is_archived`** to `where` (a *static* predicate — no param, so cursor numbering is unaffected) | the LIST half |
| **c** | 🔴 `find_by_checksum` (`:99-115`) | **`AND NOT is_archived`** | **MISSING FROM THE PLAN'S FIRST DRAFT.** Without it, re-Proposing **identical markdown** after archiving **dedupes onto the ARCHIVED run** — the user's new Propose silently returns an **invisible** run. A **silent un-archive the user never requested** (the tombstone bug class). |
| **d** | 🔴 `plan_state_for_book` (`:313-349`) | **`AND NOT is_archived` on ALL THREE subqueries** (incl. the `SELECT COUNT(*)` at `:334` and the latest-status subquery at `:336`) | **MISSING FROM THE PLAN'S FIRST DRAFT.** Archiving your only failed run leaves the **chat's per-turn plan probe** reporting `has_plan=true, latest_status='failed'` **forever**. |
| **e** | `get_for_book` (`:117`) | **MUST NOT filter archived** — restore *and* the archived-run detail read both need it to resolve. **Add that as a comment** so a later reviewer does not "fix" it. | |
| **f** | **new** `archive` / `restore` | `archive(book_id, run_id)`: `UPDATE plan_run SET is_archived=true, updated_at=now() WHERE id=$1 AND book_id=$2 AND NOT is_archived RETURNING id` (the `canon_rules.py:160` shape). `restore(...)` is the mirror (`is_archived=false … AND is_archived`, `RETURNING {_SELECT_RUN}`). | |

#### 🔴 The in-flight check — **JOB TRUTH, and BOTH job carriers**

**In-flight is decided by `generation_job.status`, NEVER by `plan_run.status` or `pass_state[*].status`** —
those are **known-lying** (`sync_from_job` exists *precisely* because the run row goes stale when the worker
hook misses).

**New `GenerationJobsRepo.active_among()`:**
```sql
SELECT id FROM generation_job
 WHERE id = ANY($1::uuid[]) AND book_id = $2
   AND status = ANY($3::text[])          -- $3 = list(_ACTIVE_STATUSES)   (generation_jobs.py:55)
   AND created_at > $4                   -- $4 = now() - 1800s  (the SAME stale bound as
 LIMIT 1                                 --      create_chapter_job_guarded, :266)
```
- **`book_id` in the WHERE is the tenancy assert** — a bare-id job read must be re-scoped to the run's book
  (same guard as `sync_from_job`'s `job.book_id != book_id`, `:109`).
- **The 1800s bound is load-bearing:** a **crash-orphaned** job must NOT make a failed run **un-archivable
  forever**.

🔴 **CANDIDATE IDS = `run.active_job_id` ∪ `{e["job_id"] for e in run.pass_state.values() if e.get("job_id")}`.**
**The PASS jobs are recorded ONLY in `pass_state`** (`plan_forge_service.py:1190`) — so the plan's first-draft
`active_job_id`-only probe would **happily archive a run with 7 live pass jobs.** **Both carriers or it is
wrong.**

```python
    # plan_forge_service.py
    async def archive_run(self, created_by: UUID, book_id: UUID, run_id: UUID) -> str | None:
        """BE-4. Soft-archive. Returns None (404), "in_flight" (409), or "ok" (204)."""
        run = await self._runs.get_for_book(book_id, run_id)
        if run is None:
            return None
        await self.sync_from_job(created_by, book_id, run)   # FIRST — a completed-but-unhooked job must not 409
        candidates = [run.active_job_id] if run.active_job_id else []
        candidates += [e["job_id"] for e in (run.pass_state or {}).values() if e.get("job_id")]
        if candidates and await self._jobs.active_among(candidates, book_id):
            return "in_flight"                               # → 409 PLAN_RUN_JOB_IN_FLIGHT {active_job_id}
        await self._runs.archive(book_id, run_id)            # already-archived ⇒ still 204 (idempotent)
        return "ok"

    async def restore_run(self, created_by: UUID, book_id: UUID, run_id: UUID) -> dict | None:
        """BE-4b (PS-13). The undo. Ships WITH BE-4, never after it.
        NO in-flight check — there is nothing to orphan by UN-archiving."""
        run = await self._runs.restore(book_id, run_id)
        return await self._serialize_run(created_by, run) if run else None
```

**DEFAULT (veto-able):** archive is plain CRUD, **not agent logic** ⇒ **REST-only, no new MCP tool.** The MCP
`.runs/` block (`server.py:3835`) needs **no change** — it calls `list_for_book` with the default, so archived
runs correctly drop out of the agent's package tree **for free**.

**Tests** — `test_plan_forge_router.py` (**real DB ⇒ `pytestmark = pytest.mark.xdist_group("pg")`**):

- `test_archived_run_disappears_from_the_list` · `test_archived_run_reappears_with_include_archived` ·
  `test_restore_unarchives` (200, `is_archived: false`, back in the default LIST) ·
  `test_restore_of_a_never_archived_run_is_404` · `test_archive_is_idempotent` (204 twice) ·
  `test_view_only_grantee_is_403_on_BOTH_archive_and_restore`.
- 🔴 `test_archive_409s_on_a_PASS_job_with_no_active_job_id` — `active_job_id=None` **but**
  `pass_state["cast"].job_id` is `running` ⇒ **409**. *An `active_job_id`-only impl passes **every other
  test** and fails this one. This is the test that proves the two-carrier union.*
- 🔴 `test_a_stale_running_job_does_not_lock_the_run_forever` — the only candidate job is `running` but
  **older than the 1800s window** ⇒ **204**. *(No permanent lockout.)*
- 🔴 `test_re_proposing_the_same_markdown_after_archiving_mints_a_NEW_run` — guards **(c)** `find_by_checksum`.
- 🔴 `test_archiving_the_only_run_makes_the_plan_probe_report_zero` — `/internal` plan-state ⇒
  `run_count=0`, `latest_status=null`. Guards **(d)** `plan_state_for_book`.

`tests/integration/db/test_repositories.py`: archived run **absent** from `list_for_book`, **present** with
`include_archived=True`; **`get_for_book` still returns it**; `find_by_checksum` **skips** it.

**DoD evidence:** composition suite green (paste the tail) + `docker compose exec … psql -c "\d plan_run"`
showing `is_archived | boolean | not null default false` **and** `idx_plan_run_book_created_active`.

**dependsOn:** W5-S6c (contract-first)

---

### W5-S5b · 🔴 OQ-6 — the pass ledger CAN lose a concurrent sibling write (FIX-NOW, BE)

> **Register: `Q-35-OQ6-CHECKPOINT-RACE`.** **The plan's first draft was silent on this.** PS-8 (no OCC) is
> upheld — **but the code has a REAL lost-update, and it contradicts its own comment.**

`plan_runs.py:209-215` merges with `pass_state = COALESCE(pass_state,'{}') || $n::jsonb` and claims
*"`||` cannot lose a sibling key"*. **It can — because `record_pass()` (`plan_pass_service.py:326-377`)
returns the WHOLE ledger rebuilt from a STALE READ SNAPSHOT, and every write site passes it whole.** The
merge then **re-asserts sibling keys from the stale read.**

**Concretely:** a human accepts pass A (a decision-only write) **while the worker finalizes pass B**. The
worker read the run *before* A's write ⇒ its whole-object write **re-asserts A's entry WITHOUT `decision`**
⇒ **the accept is silently dropped and the run stalls at a blocking checkpoint the user believes they
approved.** This needs **no collaboration grant** (it is human **vs. WORKER**), which is why OQ-6's
*"UNVERIFIED, needs two humans"* framing is wrong.

**THE CHANGE — write the DELTA, not the ledger.** No version column, no new convention, and the semantics
for the target pass are unchanged (still last-write-wins *per pass*):

```python
    # services/composition-service/app/services/plan_pass_service.py — next to record_pass
    def pass_delta(run: PlanRun, pass_id: str, **kw: Any) -> dict[str, Any]:
        """The ONE-KEY jsonb delta for `pass_id`. The repo merges with `||`, so writing ONLY the
        changed key is what actually makes `||`'s sibling-safety REAL — a whole-ledger write
        re-asserts siblings from a stale read and silently drops a concurrent pass's entry."""
        return {pass_id: record_pass(run, pass_id, **kw)[pass_id]}
```
Keep `record_pass` as-is (pure, whole-state) so existing unit tests keep passing.

**Switch ALL FIVE write sites to `pass_state=pass_delta(...)`:** `plan_forge_service.py:665-670`
(edits→completed) · `:674-678` (decision accepted/rejected) · `:1190-1191` (status=running on dispatch) ·
`worker/job_consumer.py:188-192` (failed) · `:211-222` (completed+decision).
**Update the now-stale comment** on `PlanRunsRepo.update_run`'s `pass_state` param (`plan_runs.py:176-178`,
*"Written as a WHOLE object"*) → *"callers pass a ONE-KEY delta; the `||` merge is what keeps siblings safe."*

**Tests** — `services/composition-service/tests/unit/test_plan_pass_checkpoint.py`:
- `test_review_pass_writes_only_its_own_key` — assert the dict handed to `update_run(pass_state=…)` has
  **exactly `{pass_id}`** as its keys when the run already has **2+** pass entries. **This REDs today.**
- 🔴 **real-DB** (`pytestmark = pytest.mark.xdist_group("pg")`)
  `test_concurrent_pass_writes_do_not_clobber_siblings` — seed `pass_state` with `cast`+`beats`; snapshot run
  `R0`; write `beats=completed` **from R0**; then write `cast decision=accepted` **from R0**; re-read ⇒
  **BOTH survive**. *Under the current whole-object write, the second UPDATE reverts `beats`.*

**PS-8 STANDS:** no OCC, no `If-Match` on the checkpoint, **no 412 to handle** on this route. The 412 →
*"changed elsewhere — reloaded"* recovery is owed **only** by the panels that write outline / canon / motif
(those routes **do** carry OCC: `routers/canon.py:168`, `routers/arc.py:219`/`:505`,
`db/repositories/outline.py:1022`/`:1096`/`:1506`). **Do not generalise it to PlanForge.** If a *same-pass*
race is ever actually reported after this, the fix is a `version` column + a repo-level compare-and-set —
not an ad-hoc guard, and not in this build.

**dependsOn:** —

---

### W5-S5c · 🔴 `self_heal` SHADOWS `scenes` — give the artifact list PROVENANCE (BE + contract + FE type)

> **Register: `Q-35-SELFHEAL-SHADOWS-SCENES` + `Q-35-OQ4-ARTIFACT-HISTORY`.** **The plan's first draft
> answered this with COPY ONLY. Copy is not enough — the row is not even THERE.**

Passes **6 (`scenes`)** and **7 (`self_heal`)** both emit `output_kind="scene_plan"`. `list_artifact_refs` is
`SELECT DISTINCT ON (a.kind)` ⇒ **pass 6's scene_plan simply VANISHES from the list** once pass 7 runs. The
provenance **already exists on the run** (`pass_state` pointers + `PASS_REGISTRY.output_kind`) — **zero
migration, zero new query.** The service already reads it this way everywhere else
(`_scenes_by_event`, `plan_forge_service.py:1086-1090`: *"Read through the PASS POINTER, not by
latest-kind"*).

**SLICE 1 (BE)** — `plan_forge_service.py`, `_serialize_run`'s `"artifacts"` block (`:385-388`). Replace it
with a **derived, provenance-bearing** list:
1. `pass_kinds = {s.output_kind for s in PASS_REGISTRY.values()}`
2. Walk `PASS_REGISTRY` **in registry order** (it IS pass order — asserted at `plan_pass_service.py:89`). For
   each pass whose `run.pass_state[pass_id]` has an `artifact_id`, append
   `{"kind": spec.output_kind, "artifact_id": str(aid), "pass_id": pass_id, "superseded_by": None}`.
3. Second loop: if a **LATER** ref has the **same `kind`**, set `superseded_by = <that later ref's pass_id>`.
   ⚠ Write it as this **GENERIC rule** (*any* pass whose `output_kind` is re-emitted by a later pass) —
   **not** a `scenes`/`self_heal` special case.
4. Keep the `list_artifact_refs` rows **ONLY for non-pass kinds** (`a["kind"] not in pass_kinds`) — `spec`,
   `graph`, `package`, `llm_io`, `validation_report`, `link_report — emitted with
   `"pass_id": None, "superseded_by": None`. **Dedupe by "is this kind produced by a pass", never by id.**
5. **Do NOT touch the `list_artifact_refs` SQL's `DISTINCT ON`** — it stays the latest-per-kind read for the
   non-pass kinds. **Do NOT add `?history=true`** (that is `D-PLAN-ARTIFACT-HISTORY`, out of v1).
6. **`Q-35-OQ4-ARTIFACT-HISTORY` — widen the ref row with its TIMESTAMP** (this is what makes *"latest"* a **verifiable claim**
   instead of a lie, and it is the signal the user needs to confirm their Save-edits landed):
   `plan_runs.py:355` → `SELECT DISTINCT ON (a.kind) a.kind, a.id AS artifact_id, a.created_at` (the
   `ORDER BY` is already `a.kind, a.created_at DESC`, so nothing else changes); `:363` → return
   `created_at` too.

**SLICE 2 (contract)** — `contracts/api/composition-service/plan-forge.v1.yaml`, schema **`PlanArtifactRef`**
(`:355`): add `pass_id: {type: string, nullable: true}`, `superseded_by: {type: string, nullable: true}`,
`created_at: {type: string, format: date-time, nullable: true}`. ⚠ Its `kind` **enum is also stale** — it
lists only `[analyze, spec, graph, package, llm_io, validation_report]` and **omits all six pass kinds**.
Fix it (see **W5-S6c**).

**SLICE 3 (FE)** — `frontend/src/features/plan-forge/types.ts` `PlanArtifact` (`:18-21`): add
`pass_id: string | null; superseded_by: string | null; created_at: string | null;`.
`components/PlanRunView.tsx` (`:48-60`) — header **`Artifacts` → `Latest per kind`** (i18n
`planForge.artifacts.latestPerKind`), render `created_at` (relative, *"2m ago"*) next to each id, and render
the rows with **this exact copy** (it is what the service actually does, so it is true by construction):

| Row | Title | Badge | Subtext |
|---|---|---|---|
| `pass_id="scenes"` **AND** `superseded_by="self_heal"` | `Scenes (pass 6)` | `superseded` | *"Kept for reference. Self-heal (pass 7) revised these — the healed version below is what linking and drafting use."* |
| `pass_id="self_heal"` | `Scenes — healed (pass 7)` | — | *"Self-heal's revision of pass 6's scenes. This is the version Link → scene_plan reads."* |
| any other superseded row | *(kind)* | `superseded` | *"Superseded by the {superseded_by} pass — kept for reference."* |
| `pass_id === null` | *(kind)* | — | unchanged (kind + short id) |

Plus the one-line honesty hint under the list: *"Each kind shows its newest body. Editing a pass saves a new
version — older versions are kept but not browsable yet."*

**Tests:**
- **BE** — `_serialize_run` with `scenes(completed, artifact A)` + `self_heal(completed, artifact B)`:
  assert `artifacts` contains **BOTH, in order**; `A.pass_id == "scenes"` and
  `A.superseded_by == "self_heal"`; `B.pass_id == "self_heal"` and `B.superseded_by is None`. Second test:
  **with `self_heal` absent, `A.superseded_by is None`.**
- **BE** — `tests/integration/db/test_repositories.py:2395` (extend): save **TWO** `spec` artifacts ⇒
  `len(refs) == 1`, `refs[0]["artifact_id"] == second.id`, **and `refs[0]["created_at"] == second.created_at`.**
  *That test IS the codification of "latest-per-kind, and we say WHICH one".*
- **FE** — `PlanRunView.test.tsx`: render a run with **both** `scene_plan` refs; assert **BOTH rows appear**,
  the pass-6 row shows the `superseded` badge + *"Kept for reference"*, the pass-7 row is titled
  *"Scenes — healed (pass 7)"*, `Latest per kind` + the timestamp render, and **no control implying versions
  is rendered** (no "history", no "previous", no version dropdown).

**OUT OF SCOPE (so no one gilds it):** **do NOT touch the Rail** — the confusion lives in the artifact list;
the Rail shows pass *status*, which already distinguishes `scenes` from `self_heal` by `pass_id`.
**Pass 6's scene_plan stays VISIBLE and is never deleted — we LABEL, we do not prune.**

**dependsOn:** W5-S6c (contract-first)

---

## 6 · Contract hygiene (spec 27-B1 / B1b / B2)

### W5-S6 · 27-B1 + B1b + B2 — the schema that contradicts its own emitter

**B1 — `contracts/plan-forge/planner_state.schema.json` is a POC fixture masquerading as a contract.**
Verified on disk 2026-07-13: it carries `"required": ["PA","HA","CD","THR"]` **and**
`"additionalProperties": false` — *Perfection_Addiction, Humanity_Anchor, Corruption_Debt,
Than_Hon_Resonance*: **four variables from one specific POC novel.** Meanwhile the shipped compiler emits
an **open map keyed by whatever variables the spec declares**
([`compile.py:65-69`](../../services/composition-service/app/engine/plan_forge/compile.py#L65)):

```python
    planner_state: dict[str, Any] = {
        v["code"]: _DEFAULT_VARIABLE_INITIAL
        for v in spec.get("layers", {}).get("variables", [])
    }
    planner_state["tier"] = "baseline"
```

⇒ **For every book that does not declare exactly PA/HA/CD/THR — i.e. every book but one — the artifact the
service actually writes VIOLATES its own published schema, on both clauses at once.** The service side of
the F5 severing landed; the contract side did not. Nothing validates against this schema at runtime, so it
is **safe to fix and pure debt to leave**.

**File:** `contracts/plan-forge/planner_state.schema.json` — **rewrite** (PS-10):

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://loreweave.dev/contracts/plan-forge/planner_state.schema.json",
  "title": "PlannerState",
  "description": "Runtime planner variables for a book or arc entry point. An OPEN map: one numeric slot per variable code the book's NovelSystemSpec declares (see VariableDef.code), plus the tier. The four codes this schema used to REQUIRE (PA/HA/CD/THR) were one POC novel's variables — the compiler has never emitted them for any other book, so every real artifact violated this schema on both `required` and `additionalProperties` (27-B1).",
  "type": "object",
  "required": [],
  "additionalProperties": { "type": "number" },
  "properties": {
    "tier": {
      "type": ["string", "null"],
      "enum": ["baseline", "tier_1", "tier_2", "tier_3", "tier_4", null]
    }
  }
}
```

⚠ **`additionalProperties: {type:"number"}` + a `tier` of type string is legal draft-07** — `properties`
wins over `additionalProperties` for a declared key. Verify with the test below; if the validator
disagrees, widen to `"additionalProperties": {"type": ["number","string","null"]}` and note it.
**DELETE PA/HA/CD/THR outright** — do *not* keep them as optional `properties`
(`test_plan_forge_no_fixture_constants.py:21-29` already **bans the string `"THR"`** as a fixture leak).
**Do NOT add `minimum: 0`** to the `additionalProperties` number — HA-style variables **decrease**, and future
`var_deltas` may go negative; bounding it re-creates the same over-fitting bug in a new form.

#### 🔴 B1-adjacent — the SAME bug next door, with a BIGGER blast radius (`Q-35-B1-PLANNER-STATE-SCHEMA` (2))

`contracts/plan-forge/planning_package.schema.json` is **also** `"additionalProperties": false` (`:8`) and its
property list (`:9-46`) **does not declare `arc_title`** — while `compile.py:128` **emits `arc_title` in EVERY
package.** ⇒ **The PlanningPackage schema is violated by EVERY book that compiles**, not just the
non-PA/HA/CD/THR ones. **Add `"arc_title": { "type": "string" }` to its `properties`** (leave it out of
`required` — it is derived and always present, but requiring it buys nothing). **One line. FIX-NOW.**

#### 🔴 B1-adjacent — close the hole that let it rot (`Q-35-B1-PLANNER-STATE-SCHEMA` (3))

**Nothing machine-checks producer-vs-contract** — which is *why* a POC fixture could masquerade as a contract
this long. **Add `jsonschema>=4.21` to `services/composition-service/requirements-test.txt`** (today it
carries only `pytest`, `pytest-asyncio`, `respx`; **jsonschema happens to import on this dev host (4.26.0), so
a test written without this line passes locally and FAILS IN A CLEAN CONTAINER — a false-green**). Then append
to `tests/unit/test_plan_forge_no_fixture_constants.py` a test that loads **both** contract files from
`contracts/plan-forge/` (repo-root-relative `Path`; register both in a `RefResolver`/registry so the
`$ref: planner_state.schema.json` at `planning_package.schema.json:13` resolves) and **validates
`compile_artifacts(_romance_spec(), arc_id="arc_1")["planning_package"]`** against
`planning_package.schema.json`.
🔴 **This test MUST FAIL on today's schemas** (TR/GR trip `additionalProperties:false`; the missing
PA/HA/CD/THR trip `required`; `arc_title` trips the package's closed set) **and pass after the edits.**
**Write it first and watch it red, or it proves nothing.** That red-then-green **IS** this slice's DoD.

**B1b — `VariableDef` has no `initial`.** [`novel_system_spec.schema.json:109-118`](../../contracts/plan-forge/novel_system_spec.schema.json#L109)
requires `code/name/range/transition_rules` with `additionalProperties:false` and **no `initial`** — which
is why [`compile.py:12-16`](../../services/composition-service/app/engine/plan_forge/compile.py#L12)
hardcodes `_DEFAULT_VARIABLE_INITIAL = 0` **with a comment saying so out loud**: *"a variable needing a
non-zero baseline … cannot be expressed."* Spec 27 **PF-14** (`27_planforge_v2_compiler.md:216`) already
sealed this exact change.

**Files (`Q-35-B1B-VARIABLE-INITIAL` — THREE, not two: without the WRITER it is a write-only contract):**

1. **SCHEMA** — `contracts/plan-forge/novel_system_spec.schema.json`, `VariableDef.properties` (after
   `range`, ~`:116`): `"initial": { "type": "number", "default": 0 },`. **Keep `additionalProperties: false`.
   Do NOT add `initial` to `required`** (optional; absent ⇒ 0). Safe: **nothing runtime-validates this
   schema** (no `jsonschema` import anywhere in `services/composition-service/app`).
2. **ENGINE (the READ)** — `app/engine/plan_forge/compile.py`. Keep `_DEFAULT_VARIABLE_INITIAL = 0` as the
   **fallback only** and **REWRITE its comment** (`:13-15` currently asserts the *opposite* of the new truth).
   Replace the dict-comp at `:65-69`:
   ```python
   def _initial(v: dict) -> float | int:
       raw = v.get("initial", _DEFAULT_VARIABLE_INITIAL)
       if isinstance(raw, bool) or not isinstance(raw, (int, float)):
           return _DEFAULT_VARIABLE_INITIAL          # ⚠ isinstance(True, int) is True — the bool guard is REQUIRED
       return raw
   planner_state = {v["code"]: _initial(v) for v in spec.get("layers", {}).get("variables", [])}
   ```
   `planner_state["tier"] = "baseline"` stays.
3. 🔴 **WRITER (so `initial` is not a field NOTHING ever sets)** — `app/engine/plan_forge/propose.py::_variable_defs`,
   at the declaration dict built at `:200-206`. **The regex at `:196-198` ALREADY captures the bracket as
   `group(3)`** (`HA = Humanity_Anchor [100 → 0]` ⇒ `"100 → 0"`). Derive the baseline from the **left
   endpoint** when numeric:
   ```python
   rng = (decl.group(3) or "").strip()
   m0 = re.match(r"^-?\d+(?:\.\d+)?", rng)
   current = {... "range": rng, ...}
   if m0:
       current["initial"] = float(m0.group(0)) if "." in m0.group(0) else int(m0.group(0))
   ```
   **Omit the key entirely** when the range has no numeric left endpoint (compile then defaults to 0). This
   makes the POC's `HA` **start at 100 from the document itself** — the exact case `compile.py`'s comment says
   is inexpressible.

⚠ **DO NOT touch `scripts/plan-forge-poc/**`** — the POC is frozen; its copy of `compile.py` stays as-is.

**B2 — `contracts/plan-forge/plan_pass_artifacts.schema.json` does not exist.** These are the exact bodies
**BE-3 is about to serve to a GUI** and **the `edits` deep-merge is about to patch**. Writing the schema now
is what stops the checkpoint cards being written against a shape nobody wrote down.

**File:** `contracts/plan-forge/plan_pass_artifacts.schema.json` (**new**). Keys on the **SIX** kinds
(`motif_plan`, `cast_plan`, `world_plan`, `beat_plan`, `char_arc_plan`, `scene_plan`) — **not seven.**
`self_heal.output_kind` **IS `scene_plan`**, deliberately (the registry says why: *"under a latest-by-kind
rule it would read its own output as its input"*), so **`scene_plan` must be valid for BOTH producers.**

🔴 **SOURCE OF TRUTH = `services/composition-service/app/services/plan_pass_adapters.py` — THE WRITER, not
the prompts, not the engine parsers, not memory** (`Q-35-B2-PASS-ARTIFACT-SCHEMA`; the adapter's own contract
is literally *"returns the artifact body to store under the pass's output_kind"*, `:10`). Name the definitions
**EXACTLY** as the `PlanArtifactKind` literals (`models.py:636`) so BE-3 can select by the stored `kind` with
**no mapping table**. Every subschema is `type: object`, `additionalProperties: false`. **No root
`oneOf`/discriminator** — the artifact row already carries `kind`; BE-3 refs `#/definitions/<kind>`.

🔴 **DO NOT ADD A `version` CONST**, even though every sibling plan-forge schema has one
(`plan_document.schema.json:10` *requires* it). **The adapters write NO version field; requiring one REDS
every real body.** *This is the single most likely builder mistake.*

**THE SIX BODIES (verbatim from the adapter):**

| kind | writer | required | traps |
|---|---|---|---|
| `motif_plan` | `run_motifs`, `:112-134` | `motifs`: array of `{code,name,summary,why,arc_role}` (all string, all required) | 🔴 **PLUS optional `degraded` (bool) + `warning` (string)** — the **no-retriever branch** (`:119-120`) emits them, and *absent ≠ zero* is deliberate. **Omit them and the degraded path fails validation.** |
| `cast_plan` | `run_cast`, `:138-150` | `cast`: array of `{name,role,archetype,summary: string; is_new: boolean; attributes: object}` | `attributes` is **`additionalProperties: {type: string}`**, **NOT a fixed key set** (`cast_attributes` maps to glossary codes and emits only non-empty). **NO `id`** — see the LOAD-BEARING rule below. |
| `world_plan` | `run_world`, `:154-168` | `entities`: array of `{name: string; kind: enum ["location","faction","concept"] (WORLD_KINDS, `world_plan.py:44`); summary: string; is_new: boolean; attributes: object of string→string}` | |
| `beat_plan` | `run_beats`, `:172-200` | **THREE parallel arrays, all required:** `chapters`: `[{ordinal:int, event_id:str, title:str, beat_role:str\|null, intent:str}]` · `tension_curve`: `[{chapter_index:int, beat_role:str\|null, tension_target:int 0..100}]` · `unmapped_beats`: `[string]` | 🔴 **There is NO `summary` and NO `tension` on a beat.** Tension lives in the **parallel `tension_curve`**, joined by `chapter_index` ⇄ `ordinal`. `unmapped_beats` is **surfaced-not-swallowed by design** — required. |
| `char_arc_plan` | `run_character_arcs`, `:204-219` | `character_arcs`: array of `{name,role,arc: string; introduce_at_chapter: integer\|null}` | |
| `scene_plan` | `_decompose_to_artifact`, `:308-345` — **VALID FOR BOTH PRODUCERS** | `arc_title` (string) · `chapters`: `[{chapter: {chapter_id,title: string; sort_order:int; beat_role: str\|null; intent: str}; scenes: [{title,synopsis: string; tension: int 0..100 (ALWAYS coerced, `plan.py:330-334` — never null); present_entity_ids: [string, format uuid]; present_entity_names_unresolved: [string]; suggested_k: int}]; warning: string\|null; exit_state: null OR {characters,world,plot: string; advances: [string]}}]` · `unmapped_beats`: `[string]` · `motif_coverage`: object (free-form) | 🔴 **PLUS `heal` — OPTIONAL.** `{findings: [{chapter,scene:int; type,issue,fix:str; applied:bool; skip_reason: str\|null}] (required); edits_applied: int (required); note: str (OPTIONAL — only the "no scenes to heal" branch, `:279`)}`. **THIS IS THE LOAD-BEARING RULE: pass 6 emits scene_plan WITHOUT `heal`; pass 7 emits it WITH.** Under `additionalProperties:false`, *present-but-optional* is **the only shape that validates both**. **Required ⇒ breaks pass 6. Banned ⇒ breaks pass 7.** `present_entity_ids` **must be `format: uuid`** — pass 7's `_artifact_to_decompose` does `UUID(e)` (`:370`), so a non-UUID **crashes the heal pass**. |

🔴 **HAND M4 ITS CONSTRAINT — and hand M2 the same one (`Q-35-OQ2-EDITS-EDITOR-SHAPE` §5).**
**NO cast/beat list item may EVER gain an `id` key.** `_deep_merge` (`validate.py:23-31`) merges a
list-of-dicts **by `id` (upsert, NO DELETE)** *iff* `val[0]` has an `"id"`, and **otherwise REPLACES THE LIST
WHOLESALE**. **No list item in ANY of the 7 pass artifacts carries an `id` today** — which is precisely what
makes *add / remove / rename* work in the checkpoint forms. **The instant an `id` appears, `_deep_merge` flips
to upsert-by-id, `by_id` resurrects every omitted element, and "remove a character" SILENTLY STOPS WORKING
while every unit test stays green.**

**Files** — 4:

1. `contracts/plan-forge/plan_pass_artifacts.schema.json` (**NEW**, draft-07,
   `$id: https://loreweave.dev/contracts/plan-forge/plan_pass_artifacts.schema.json`, title `PlanPassArtifacts`).
2. `services/composition-service/tests/unit/test_plan_pass_artifact_schema.py` (**NEW** — *without it the
   schema is decorative and drifts*).
3. `services/composition-service/requirements-test.txt` → **`jsonschema>=4.21`** (see B1-adjacent (3)).
4. `contracts/plan-forge/README.md` → add the row `| PlanPassArtifacts | plan_pass_artifacts.schema.json |`.

**Tests** — `test_plan_pass_artifact_schema.py` (**pure, no DB**). It must:
- **(a)** load the schema via `Path(__file__).parents[4] / "contracts" / "plan-forge" / "plan_pass_artifacts.schema.json"`;
- **(b)** 🔴 assert `set(schema["definitions"]) == {spec.output_kind for spec in PASS_REGISTRY.values()}` —
  **the guard that keeps the file honest when a pass is added, and it mechanically re-derives "6 kinds from 7
  passes"**;
- **(c)** validate **REAL ADAPTER OUTPUT, not hand-written dicts** — reuse the fixture at
  `test_plan_pass_adapters.py:84` and assert `_decompose_to_artifact(result)` validates against
  `#/definitions/scene_plan`;
- **(d)** 🔴 **THE CRITICAL TEST** — assert the `scene_plan` subschema validates **BOTH producers**: pass 6's
  body (**no `heal`**) **AND** pass 7's body (**`heal` present**), reusing the branch at
  `test_plan_pass_adapters.py:143`;
- **(e)** assert `run_motifs`'s **degraded** body (test at `:127`) validates against `#/definitions/motif_plan`;
- **(f)** an **`exit_state: None`** case **AND** a populated one — *the null branch already caused a live
  `AttributeError` that three redeliveries hid* (`plan_pass_adapters.py:334-338`), precisely because a fixture
  never exercised it.

**Plus (`test_planforge_v2_schema.py`, extend — pure, no DB):**
- `test_planner_state_validates_a_book_that_is_not_the_POC` — 🔴 **RED TODAY, on BOTH clauses.**
- `test_the_planning_package_validates_at_all` — 🔴 **RED TODAY on `arc_title`** (B1-adjacent (2)).
- `test_variable_initial_is_read_when_declared` — `"initial": 100` ⇒ `planner_state["HA"] == 100`; absent ⇒ `0`;
  🔴 **`"initial": true` and `"initial": "100"` ⇒ `0`** (the bool/str coercion guard).
- `test_propose_writes_initial_from_the_range_bracket` — a doc line `HA = Humanity_Anchor [100 → 0]` ⇒ the
  emitted `VariableDef` carries `initial == 100`; `PA = Perfection_Addiction [0 → 100+]` ⇒ `initial == 0`; a
  **non-numeric** range ⇒ **key absent**.
- `test_the_schema_declares_initial` — assert `VariableDef.properties` contains `initial` with
  `type == "number"` (**kills a silent revert**).

🔴 **M2 ⟂ M4 — THE DEPENDENCY IS SEVERED (`Q-35-MILESTONE-ORDERING`).** These schema files have **ZERO runtime
consumers** (`grep -rn "planner_state.schema|novel_system_spec.schema|plan_pass_artifacts|contracts/plan-forge"
services/ frontend/src/ scripts/` → **one hit**, `scripts/plan-forge-poc/README.md:79`). **A schema file
nothing reads cannot gate a panel.** W5-S12's cast/beats forms are built **from the adapter dicts**, which are
pinned in code **today**. Build these slices in **any order** — the anti-drift guard is test **(c)**: it
validates *real adapter output*, so **whichever lands second cannot silently disagree.**

**DEFAULT (PO may veto):** `motif_coverage` stays **free-form** (`type: object`) — its writer
(`DecomposeResult.motif_coverage: dict[str, Any]`) is explicitly `Any` telemetry; pinning it would
over-constrain a field the engine treats as open. **Everything else is closed** (`additionalProperties: false`),
which is what makes the M4 edit forms derivable from this file.

**DoD evidence:** composition suite green, **including the schema tests that are RED today** (write them
first; watch them red).

**dependsOn:** —

---

---

### 🔴 W5-S6c · CONTRACT-FIRST — freeze the API spec **BEFORE** any FE slice consumes it

> **CLAUDE.md, a repo LAW:** *"**Contract-first**: API contract frozen before frontend flow."*
> The plan's first draft added **5 new REST routes and touched ZERO contract files.** That is a
> `/review-impl` finding, not an oversight to wave through.

**🔴 FIND THE FILE — DO NOT GUESS.** There are **two** composition specs, and they are **not**
interchangeable:

| Path | What lives there | Wave 5? |
|---|---|---|
| `contracts/api/composition/v1/openapi.yaml` | the **general** composition surface (~17 paths; it already carries `/canon-rules/{rule_id}`) | ❌ **NO** |
| 🔴 **`contracts/api/composition-service/plan-forge.v1.yaml`** | **PlanForge — 455 lines, 8 paths, 14 schemas. THIS IS WHERE WAVE 5'S ROUTES GO.** | ✅ **YES** |
| ~~`contracts/api/book-service/`~~ | 🔴 **DOES NOT EXIST.** (Another wave's plan names it three times. The real path is `contracts/api/books/v1/openapi.yaml`.) Wave 5 touches neither. | — |

#### A · The **5 NEW** routes this wave adds — each needs path · method · request schema · response schema · error codes

| # | Route | Slice | Request | Responses |
|---|---|---|---|---|
| 1 | `GET /books/{book_id}/plan/runs/{run_id}/artifacts/{artifact_id}` | W5-S2 | path params only (all `format: uuid`) | **200** `PlanArtifactBody` `{artifact_id, run_id, kind, content(object), created_at(nullable)}` · **403** `$ref: Forbidden` · **404** `$ref: NotFound` *(run-not-found + artifact-not-found + **cross-book** are ALL this same 404 — document it: **no enumeration oracle, H13**)* · **422** malformed uuid |
| 2 | `POST /books/{book_id}/plan/runs/{run_id}/autofix` | W5-S4 | **`PlanAutofixRequest`** `{model_ref: uuid nullable, max_rounds: integer min 1 max 5 default 3}` | **200** `PlanAutofixResult` `{rounds: [{round:int, targets:int, result: string nullable}], run: PlanRun}` · **202** *same schema* (job in flight) · **400** · **403** · **404** · **422** (max_rounds out of range) |
| 3 | `DELETE /books/{book_id}/plan/runs/{run_id}` | W5-S5 | — | **204** (no body) · **409** `PlanRunJobInFlight` `{code: "PLAN_RUN_JOB_IN_FLIGHT", active_job_id: uuid}` · **403** · **404** |
| 4 | `POST /books/{book_id}/plan/runs/{run_id}/restore` | W5-S5 | — | **200** `PlanRun` (`is_archived: false`) · **403** · **404** (not found **or not archived**) |
| 5 | `GET /books/{book_id}/plan/runs` **`?include_archived`** | W5-S5 | **new query param** `include_archived: boolean, default false` on the **existing** path (`:32`) | **200** `PlanRunList` — document that the **default FILTERS archived rows OUT** |

#### B · The routes the FE consumes **for the first time in this wave** and the contract **never had**

**A contract that omits the routes the frontend calls is not a contract.** These four are **shipped in code**
and **uncontracted** — the Pass Rail is their first consumer, so contract-first binds them here:

| Route | Consumed by |
|---|---|
| `GET /books/{book_id}/plan/runs/{run_id}/passes` → **`PlanPassLedger`** `{run_id, book_id, genre_tags, compiled, passes[], pass_cursor, blocked_at}` | W5-S12 (**the Rail's ONLY read**) |
| `POST …/passes/{pass_id}/run` → **`PlanPassRunRequest`** `{model_ref: uuid, params: object, force: boolean}`; **202** + **409 `{code: "UPSTREAM_STALE", pass_id, blockers: [string]}`** | W5-S12 |
| `POST …/checkpoint` → `{approved: boolean, pass_id?: string, edits?: object}`; **409 `{code: "CHECKPOINT_REFUSED", message}`** | W5-S12 |
| `POST …/link` → `{target: enum [skeleton, scene_plan]}`; **409 `{code: "LINK_REFUSED", message}`** | W5-S12 |

**`PlanPass`** (the ledger row) must carry **all 13 fields** `derive_view` emits after BE-20:
`pass_id · checkpoint(enum blocking|advisory) · output_kind · depends_on[] · status · decision(enum
pending|accepted|rejected|auto) · artifact_id · job_id · **bootstrap_proposal_id** · **decided_by** ·
**decided_at** · fresh · blockers[]`.

#### C · Schemas the wave CHANGES (not adds)

- 🔴 **`PlanArtifactRef` (`:355`)** — **its `kind` enum is STALE**: it lists only
  `[analyze, spec, graph, package, llm_io, validation_report]` and **omits all six pass kinds** and
  `link_report`. **Add them**, plus **`pass_id` (nullable)**, **`superseded_by` (nullable)** and
  **`created_at` (nullable)** — W5-S5c.
- **`PlanRun` (`:315`)** — add **`is_archived: boolean`** (W5-S5), **`source_markdown: string`** ⚠ **document
  it as *present on the DETAIL response only, ABSENT on list items*** (C-8 / W5-S3), and the derived pass
  block (`passes[]`, `pass_cursor`, `blocked_at`).
- **`PlanRefineRequest` (`:385`)** — **`revision` is an OBJECT (`type: object`), not a string** (PS-5 / C-8's
  sibling drift). The TS type has been wrong since it was written; **the contract must not repeat it.**

**Test / DoD:** the spec is **YAML-valid** and **every route the FE calls appears in it**:
```bash
python -c "import yaml,sys; d=yaml.safe_load(open('contracts/api/composition-service/plan-forge.v1.yaml')); \
print(sorted(d['paths']))"
```
Assert the printed set contains all 5 new paths **and** the 4 previously-uncontracted ones. **This slice lands
BEFORE W5-S8** (the api.ts widening) — that ordering **is** the contract-first rule.

**dependsOn:** — (do it first; it costs nothing and it unblocks the honest review of every BE slice)

---

## 7 · The frontend slices

### W5-S7 · FE-1 — `readOnly` on the JSON-document standard (**BUILD IT; it does not exist**)

`grep -rn "readOnly\|editable" frontend/src/features/studio/panels/JsonEditorPanel.tsx
frontend/src/features/studio/documents/*.ts` → **ZERO hits** (verified). `DocumentHandle` is
`update()`/`save()`/`revert()`, and `JsonEditorPanel` wires **⌘S → `handle.save()`** plus a Save button.

**Registering a read-only provider whose `save()` quietly does nothing is `silent-success-is-a-bug`,
shipped** — the user edits the plan they paid an LLM to write, hits ⌘S, and **nothing happens and nothing
says so.** So `readOnly` must be **built**, not assumed. ~20 lines.

**Files**

| File | Change |
|---|---|
| `frontend/src/features/studio/documents/types.ts` | `JsonDocumentProvider` → add `readOnly?: boolean;` with a doc comment |
| `frontend/src/features/studio/panels/JsonEditorPanel.tsx` | honour it |

```ts
// documents/types.ts
export interface JsonDocumentProvider {
  type: string;
  schema?: object;
  titleKey?: string;
  /** #35 FE-1 — this document type has NO write path (the domain exposes no artifact-write route;
   *  the only sanctioned mutation goes through a different, re-fingerprinting channel). The view
   *  MUST render it non-editable with NO save affordance. A provider that instead swallowed save()
   *  would be `silent-success-is-a-bug`: the user edits, hits ⌘S, and nothing happens and nothing
   *  says so. Default false (writable) — every existing provider is unaffected. */
  readOnly?: boolean;
  open(ctx: DocContext, resourceId: string): Promise<DocumentHandle> | DocumentHandle;
}
```

> **Register: `Q-35-FE1-READONLY-PROVIDER` + `Q-35-ARTIFACT-READONLY-WHY`.** ⚠ `readOnly` lives on the
> **PROVIDER**, never on `DocumentHandle`/`DocumentSnapshot` and never in the panel's `params`. It is a
> property of the **TYPE**, not of an instance (a plan-artifact is read-only for **every** artifact) — and
> putting it in `params` would let a caller open the same artifact **writable** by passing a different flag.
> **NO CHANGES to the 2 existing call sites** (`entityDocument.ts:203`, `manuscriptUnitDocument.ts:228` are
> bare object literals — an optional field cannot break them; **do not touch those files**).

In `JsonEditorPanel.tsx` — **FIVE edits** (the plan's first draft had four, and **missed the one that
matters**):

1. `const readOnly = provider?.readOnly === true;` — next to `const provider = …` (`:42`).
2. **CM6 (`:164-171`):** `editable={!readOnly}` **and** `readOnly={readOnly}`.
   `@uiw/react-codemirror@4.25.10` exposes **BOTH as first-class props** (`esm/index.d.ts:39` + `:44`) —
   **do NOT hand-roll an `EditorState.readOnly` Compartment/extension**; the spec's *"+ readOnly extension"*
   is redundant. (Mouse selection + copy still work ⇒ the viewer stays **copyable**.)
3. **⌘S (`:93-99`): the listener is WINDOW-level, so it must NOT BE REGISTERED AT ALL** —
   `useEffect(() => { if (readOnly) return; … }, [onSave, readOnly])`. **Do not merely early-return inside
   `onSave`:** a live window listener that swallows the browser's ⌘S is a **side effect on the whole app.**
4. **Toolbar (`:152-161`): HIDE Save and Revert entirely** (`{!readOnly && (<>…</>)}`) — **do not merely
   `disabled` them.** *A disabled Save reads as "nothing to save yet" — a lie about an immutable doc.*
   **KEEP the Format button** — it is **buffer-local and harmless** (`Q-35-FE1-READONLY-PROVIDER` (c);
   the plan's first draft talked itself into hiding it mid-sentence — **it was wrong**). Render a
   `data-testid="json-editor-readonly"` chip (`t('jsonEditor.readOnly', { defaultValue: 'read-only' })`) in the
   status span, **plus the escape hatch**: *"To change this plan, approve the pass with edits, or re-run it."*
   (That **IS** the sanctioned channel — `POST /checkpoint`.)
5. 🔴 **`onChange` (`:71-81`): `if (readOnly) return;` BEFORE `handle?.update(parsed)` at `:76`.**
   **⚠ THIS IS THE HOLE FE-1's OWN ONE-LINER MISSES.** Hiding Save while `update()` still fires lets a
   read-only doc go **`dirty: true`**, which lights the **"● unsaved" chip** at `:145` — **an
   unsaved-changes warning the user can NEVER clear.** `editable={false}` alone does **not** close it (a
   programmatic/paste path still fires).
6. **Never conditionally unmount** the CodeMirror — flip its props, don't ternary it (repo FE rule).
7. Add the i18n key `jsonEditor.readOnly` to `en/studio.json` + the 17 locales (rides W5-S13's
   `i18n_translate.py` run).

**Test** — `frontend/src/features/studio/panels/__tests__/JsonEditorPanel.test.tsx` (**the mock at `:17`
already returns a provider object — add a `readOnly` variant**). Four assertions, all required:

- **(i)** provider `{readOnly:true}` ⇒ `queryByTestId('json-editor-save')` **and** `'json-editor-revert'` are
  **BOTH null**, and `getByTestId('json-editor-readonly')` is present.
- **(ii)** firing `keydown {key:'s', ctrlKey:true}` on `window` ⇒ the handle's `save` spy was **NEVER
  CALLED** — *not "called and returned undefined": **a no-op save IS the bug**.*
- **(iii)** 🔴 **type into the buffer ⇒ the snapshot NEVER goes dirty** (pins edit 5 — the hole).
- **(iv)** 🔴 **REGRESSION:** a provider **WITHOUT** `readOnly` still renders Save **and still saves on ⌘S**.
  *This is the test that protects the 2 shipped providers.*

⚠ **Vitest trap (recorded memory):** a `beforeEach` that **returns** a mock is treated by Vitest as a
teardown fn and gets **called after the test** — if it rejects, the test fails for no visible reason.
`beforeEach(() => { registerX(); })` — braces, not a concise arrow returning the mock.

**DoD evidence:** `frontend: <N> passed` (vitest), including all four assertions.

**dependsOn:** —

---

### W5-S8 · PS-14 (**NARROWED**) — the api/type widening + `usePassRail`'s react-query surface

> **Register: `Q-35-PS5-REFINE-TYPE-DRIFT` · `Q-35-POLL-IDIOM` · `Q-35-X4-PLAN-EFFECTS-HANDLER`.**
> 🔴 **This is NOT "migrate plan-forge to react-query".** That was the plan's blind draft (C-13). **Only the
> NEW `usePassRail` is react-query; the two SHIPPED hooks stay hand-rolled** and are reached by the
> `reload*` escape hatches. **Read §4 before starting.**

This slice makes Lane-B (W5-S14) actually work and fixes the **`RefinePlanBody` type drift** that would 422
the first Refine button — **plus the silent-no-op the type fix alone does not cover.**

🔴 **PS-14 IS NARROWED (C-13 / §4) — the two SHIPPED hooks are NOT refactored.**

**Files**

| File | Change |
|---|---|
| `frontend/src/features/plan-forge/types.ts` | **PS-5:** `RefinePlanBody.revision?: string` → **`PlanRevision`** (below) · `PlanRunDetail` gains **`source_markdown?: string`** (⚠ **optional** — C-8), `is_archived: boolean`, `genre_tags: string[]`, and the derived pass block · **new** `PlanPass`, `PlanPassLedger`, `PassId`, `PlanArtifact`, `AutofixResult`, `RunPassBody`, **`PASS_ORDER`**, **`PACKAGE_KIND`**, `PASS_POLL_MS`, `isLedgerPolling` |
| `frontend/src/features/plan-forge/api.ts` | **8 new methods** (below) + the **typed error** |
| ⛔ `hooks/usePlanRunsList.ts` | **NOT migrated.** Thread `includeArchived` into its fetch; expose `archive(runId)` / `restore(runId)` that call the api then its existing `refresh()`. It already owns `items` + `refresh` (`:17-46`) — **no new state container.** |
| ⛔ `hooks/usePlanRun.ts` | **NOT migrated.** Keeps `useState` + `setTimeout` + `genRef`. **Add** `runInterpret` / `runRefine` / `runAutofix` as imperative actions that call `loadRun()` on success. |
| 🟢 `hooks/usePassRail.ts` (**NEW**, W5-S12) | **react-query** — `['plan-passes', bookId, runId]` + `refetchInterval`. **This is the ONLY new react-query surface in the feature.** |

**The type drift (PS-5) — fix it HERE or the button 422s.** `types.ts:115` declares `revision?: string`; the
backend takes **`revision: dict[str, Any] | None`** ([`plan_forge.py:60`](../../services/composition-service/app/routers/plan_forge.py#L60)).
**Do NOT settle for a bare `Record<string, unknown>`** — document the keys the engine actually **acts on**,
and keep it **open**, because the backend **prompt-dumps the WHOLE dict** (`prompts.py:149`):

```ts
export interface PlanRevision {
  /** free-text user instruction (apply_policy.py:41) */
  instruction?: string;
  /** slices the artifact + merges the patch back (refine.py:24, merge_refine_output) */
  focus_paths?: string[];
  /** own line in the prompt (prompts.py:152) */
  intent?: string;
  /** own block in the prompt (prompts.py:150) */
  source_excerpt?: string;
  [k: string]: unknown;   // the whole dict is json.dumps'd into <plan_revision>
}
export interface RefinePlanBody { model_ref: string; revision?: PlanRevision; focus_paths?: string[] }
```

`InterpretPlanBody.user_message: string` is **already correct — do NOT touch it.** (`interpret` takes **prose**;
`refine` takes a **dict**. *That asymmetry is the trap.*)

🔴 **THE TYPE FIX ALONE DOES NOT CLOSE THE BUG (`Q-35-PS5-REFINE-TYPE-DRIFT` (2)).**
`plan_forge_service.py:494-500`: **if `revision` is empty AND `focus_paths` is empty, refine early-returns
HTTP 200 `{"status":"no_change","fidelity_delta":0.0,"diagnosis":null}` — no job, no model resolve, NO SPEND,
NOTHING CHANGED.** A button wired to send `{}` (or to omit `revision`) returns **200** and the user sees a
**success with zero effect** — the repo's own `silent-success-is-a-bug` class. Therefore:
- Wire the free-text box to **`revision: { instruction: userText }`**.
- **HARD-GUARD:** if the box is empty **and** no `focus_paths` are selected, **disable the button
  client-side — do not fire the request.**
- **Render `status === 'no_change'` as its OWN neutral state** (*"no change — nothing to refine"*),
  **NEVER as an applied/success toast.** Refine returns a **union** — `202 ack` | `{status:'applied'}` |
  `{status:'no_change'}` — and the `PlanRefineResult | PlanRunAck` union (`api.ts:70-72`) **must be
  discriminated on `status`**, never assumed applied.

**BONUS WIRING (free — and the reason the drift existed):** `interpret` **already RETURNS a ready-made
revision dict** — `interpret.py:141-199` builds `draft_revision` (keys: `instruction`, `focus_paths`, `intent`,
`source_excerpt`, `scope`, `expect`). **The interpret→refine chain is: take `interpretation.draft_revision` and
POST it verbatim as `revision`.** Type `PlanInterpretation` (today a bare `Record<string, unknown>` at
`types.ts:91`) with at least **`draft_revision?: PlanRevision`** — *its untyped-ness is precisely what let the
`revision?: string` drift go unnoticed.*

**New types** (mirror the wire exactly — the ledger's per-pass row after BE-20):

```ts
export type PassId = 'motifs' | 'cast' | 'world' | 'beats' | 'character_arcs' | 'scenes' | 'self_heal';
export type PassStatus = 'pending' | 'running' | 'completed' | 'failed';
export type PassDecision = 'pending' | 'accepted' | 'rejected' | 'auto';

export interface PlanPass {
  pass_id: PassId;
  checkpoint: 'blocking' | 'advisory';
  output_kind: string;
  depends_on: PassId[];
  status: PassStatus;
  decision: PassDecision;
  artifact_id: string | null;
  job_id: string | null;
  bootstrap_proposal_id: string | null;   // BE-20 — the PF-7 gate, surfaced
  decided_by: 'user' | 'auto' | null;     // BE-20
  decided_at: string | null;              // BE-20
  fresh: boolean;                          // DERIVED server-side, never stored
  blockers: PassId[];                      // == depends_on, filtered. Can NEVER name a non-upstream.
}

/** GET …/passes — the DERIVED ledger. `compiled:false` means the run has NO package and every
 *  package-reading pass is un-runnable: say so, do not render 7 tidy "pending" rows. */
export interface PlanPassLedger {
  run_id: string;
  book_id: string;
  genre_tags: string[];
  compiled: boolean;
  passes: PlanPass[];
  pass_cursor: number;
  blocked_at: PassId | null;
}
```

**New api.ts methods:**

```ts
  passes(bookId, runId, token): Promise<PlanPassLedger>
    → GET  `${BASE}/books/${bookId}/plan/runs/${runId}/passes`

  runPass(bookId, runId, passId, body: {model_ref?: string; params?: Record<string, unknown>; force?: boolean}, token)
    → POST `${BASE}/books/${bookId}/plan/runs/${runId}/passes/${passId}/run`
       // 409 UPSTREAM_STALE carries detail.blockers[] — see §7 W5-S12's error handling

  checkpoint(bookId, runId, body: {approved: boolean; pass_id?: PassId; edits?: Record<string, unknown>}, token)
    → POST `${BASE}/books/${bookId}/plan/runs/${runId}/checkpoint`   // 409 CHECKPOINT_REFUSED

  link(bookId, runId, body: {target: 'skeleton' | 'scene_plan'}, token)
    → POST `${BASE}/books/${bookId}/plan/runs/${runId}/link`         // 409 LINK_REFUSED

  autofix(bookId, runId, body: {model_ref?: string; max_rounds?: number}, token): Promise<AutofixResult>
    → POST `${BASE}/books/${bookId}/plan/runs/${runId}/autofix`      // 200 {rounds, run} — NOT an ack (C-1)

  artifact(bookId, runId, artifactId, token): Promise<PlanArtifactBody>
    → GET  `${BASE}/books/${bookId}/plan/runs/${runId}/artifacts/${artifactId}`

  archiveRun(bookId, runId, token): Promise<void>          → DELETE …/plan/runs/{runId}
  restoreRun(bookId, runId, token): Promise<PlanRunDetail> → POST   …/plan/runs/{runId}/restore
```

**⚠ The 409 bodies must survive `apiJson` — and the register says they DO.** `frontend/src/api.ts:158-163`
**already attaches `.status` and `.body` to the thrown Error**, so the 409's `detail` is reachable:
`(err as {body?: {detail?: {code: string; pass_id: string; blockers: string[]}}}).body?.detail`.
**Read `frontend/src/api.ts` and CONFIRM before writing the api methods.** If it turns out the structured
`detail` is *not* reachable, add a narrow typed error
(`PlanApiError extends Error { code?: string; blockers?: PassId[]; passId?: string }`) that the plan-forge api
layer throws by **parsing the response body** — 🔴 **NEVER regex the message string.** A 409 whose `blockers[]`
never reaches the UI degrades the whole "blocked" state to a useless toast **and makes the force escape
unreachable**.

**Also add (`Q-35-NO-HOLD-COPY` (1) · `Q-35-LINK-GATE-ASYMMETRY` · `Q-35-ARCHIVE-TOAST-COPY` (2)):**
`checkpoint(...)`, `linkPlanRun(token, bookId, runId, target)` (on 409 read `detail.code === 'LINK_REFUSED'`
and throw an error carrying `detail.message` **verbatim**), `archiveRun` (DELETE), `restoreRun` (POST
`…/restore`), and `listRuns(bookId, token, opts)` widened with **`opts.includeArchived?: boolean` →
`?include_archived=true`** (*an unread query param is dead contract*).

**`usePassRail` — the ONE new react-query hook** (`Q-35-POLL-IDIOM`: build it on the repo's **DOMINANT** poll
idiom — `refetchInterval` — used by `useCampaignQueries:39`, `useEnrichmentJobs:21`, `useResearchJobs:29`,
`authoringRuns/hooks.ts:41`, `useWikiGenJob:54`, … **`usePlanRun`'s hand-rolled `setTimeout`+`genRef` is the
plan-forge ONE-OFF, not the house idiom — do NOT copy it into the new hook**):

```ts
// types.ts — one predicate, one home (mirrors isRunPolling at types.ts:130)
export const PASS_POLL_MS = 2000;
export function isLedgerPolling(l?: PlanPassLedger | null): boolean {
  return !!l && l.passes.some((p) => p.status === 'running' || p.status === 'pending');
}

// hooks/usePassRail.ts (NEW — no JSX; MVC rule)
const passes = useQuery({
  queryKey: ['plan-passes', bookId, runId],
  queryFn: () => planForgeApi.passes(bookId, runId!, token!),
  enabled: !!token && !!bookId && !!runId,
  refetchInterval: (q) => (isLedgerPolling(q.state.data) ? PASS_POLL_MS : false),
});
```
**The run-switch guard the `genRef` was hand-implementing is satisfied BY CONSTRUCTION:** `runId` is in the
query key, so **a tick for run A can never write run B's ledger** and react-query drops the in-flight result on
key change. **No `genRef` in the new hook.** `plan_run_pass` is `async_job=True` (`mcp/server.py:3583`) — it
only **ENQUEUES**, so **without the poll the Rail freezes showing "running" forever.**
Mutations (`…/passes/{id}/run`, `…/checkpoint`, `…/link`) are `useMutation` →
`onSuccess: qc.invalidateQueries({ queryKey: ['plan-passes', bookId, runId] })` (mirror
`authoringRuns/hooks.ts:56-60`).

**Tests** — `frontend/src/features/plan-forge/__tests__/usePassRail.test.tsx` (**real timers +
`QueryClientProvider`** — copy the harness at `features/enrichment/hooks/__tests__/useEnrichmentJobs.test.tsx:131,155`):

- **(a)** a ledger with an in-flight pass ⇒ a **second fetch fires after 2s**.
- **(b)** an all-terminal ledger ⇒ `refetchInterval` **false**, **NO further fetch**.
- **(c)** 🔴 **run-switch:** rerender with `runId` **B** while **A**'s fetch is in flight ⇒ **A's resolved
  ledger never renders** (the stale-resurrect regression `genRef` existed to stop).
- **(d)** `test_an_agent_pass_run_invalidation_refetches_the_ledger` —
  `qc.invalidateQueries({queryKey: ['plan-passes', bookId]})` (**the BOOK PREFIX — the key `planEffects`
  actually fires**) ⇒ `planForgeApi.passes` called again. **This is the test that proves Lane-B can reach this
  hook.**

`__tests__/usePlanRun.test.tsx` (**it stays hand-rolled — do NOT wrap it in `renderWithClient`**):
- **New:** `test_refine_body_sends_revision_as_an_OBJECT_with_a_nonempty_instruction` — assert the POST body's
  `revision` is an **object** carrying a **non-empty `instruction`** — **never a bare string, never `{}`**
  (pins PS-5 **and** the silent-no-op guard).
- **New:** `test_an_empty_refine_input_does_not_fire_the_request`.

**DoD evidence:** `frontend: <N> passed`, including **(c)** and **(d)**.

**dependsOn:** W5-S6c (contract), W5-S3 (`source_markdown?` on the type), W5-S5 (`is_archived` on the type)

---

### W5-S9 · R1 + PS-9 — the artifact viewer (and the `plan-artifact` JSON document provider)

[`PlanRunView.tsx:52-57`](../../frontend/src/features/plan-forge/components/PlanRunView.tsx#L52) renders
each artifact as an **unclickable `<li>`**: `kind` + a truncated UUID. Make the row a button that opens the
body in the generic `json-editor`. **This is also the cheapest available close of
[`12_json_document_standard.md`](../specs/2026-07-01-writing-studio/12_json_document_standard.md)'s
cycle-gate item 5**, which the KG and Translation cycles **silently skipped** (only 2
`registerJsonDocumentProvider` call sites exist repo-wide).

**🔴 The shipped provider seam does NOT fit as-is — on two axes. Both are handled here.**

```ts
// documents/types.ts — what actually exists (verified)
export interface DocContext { token: string; bookId: string; }        // ← NO runId
open(ctx: DocContext, resourceId: string): Promise<DocumentHandle>;   // ← ONE id
```

1. **Composite resource id.** BE-3's route needs `run_id` — `plan_artifact` has **no `book_id`**, and the
   `JOIN plan_run r ON r.id = a.run_id WHERE r.book_id = $2` **IS** its tenancy check. You cannot drop
   `run_id` without dropping the scope check. The provider gets **one** string ⇒
   **`resourceId = "{runId}:{artifactId}"`, split inside the provider.** The dock id becomes
   `json-editor:plan-artifact:{runId}:{artifactId}` — `JsonEditorPanel` already keys tabs on that string,
   so **N artifacts open as N tabs for free**.
2. **Read-only.** Built in **W5-S7**. `readOnly: true` on the provider.

**⚠ Why read-only at all (do NOT "improve" this to editable):** there is **no artifact-write route**, and
`edits` — the only sanctioned artifact mutation — goes through `POST /checkpoint`'s deep-merge, which
**re-fingerprints** (`_review_pass` saves a NEW artifact and re-records the fingerprint,
[`plan_forge_service.py:656-670`](../../services/composition-service/app/services/plan_forge_service.py#L656)).
A writable artifact viewer would be a **second, un-fingerprinted write channel into the pass ledger**,
breaking PF-3's derivation. **Do not make it editable — and do not fake it by swallowing the save.**

**Files**

| File | Change |
|---|---|
| `frontend/src/features/plan-forge/documents/planArtifactDocument.ts` | **NEW** — the provider |
| 🔴 `frontend/src/features/studio/panels/catalog.ts` | **the registration lives HERE, at MODULE SCOPE** (C-9) |
| `frontend/src/features/plan-forge/components/PlanRunView.tsx` | artifact `<li>` → `<button>` |
| ⛔ `frontend/src/features/plan-forge/components/PlannerPanel.tsx` | **ZERO registration calls** (C-9) |
| `frontend/src/features/plan-forge/documents/__tests__/planArtifactDocument.test.ts` | **NEW** |

#### 🔴 C-9 — REGISTER AT MODULE IMPORT FROM `catalog.ts`, **NOT** at panel mount

> `Q-35-PS9-PROVIDER-REGISTRATION`: *"the candidate answer is **REJECTED** — it does not fix the failure mode
> it names."* **The dock layout is restored from localStorage** (`useStudioLayout.ts:26-27`,
> `api.fromJSON(...)`). A `json-editor:…:{runId}:{artifactId}` tab therefore **returns on a fresh page load
> with NO guarantee `PlannerPanel` or `PassRailPanel` is mounted** — the user can close those tabs and keep the
> JSON tab. `JsonEditorPanel` mounts → `useJsonDocument` → `openJsonDocument` → **throws
> `no JSON document provider for type …`** (`registry.ts:31`). **Mount-scoped registration only NARROWS the
> browser-dead window; it does not close it.**
>
> **Why the 2 existing providers register on mount — do NOT cargo-cult them:** they are **BINDING-BRIDGE**
> providers whose `open()` needs a live mount-scoped hook instance (`entityDocument.ts:200-208` throws
> *"glossary entity unavailable — open the entity editor for it first"*). **`plan-artifact` has NO binding** —
> it is read-only and REST-fetched; everything it needs is in `DocContext {token, bookId}` + the composite
> `resourceId`. And `registry.ts:1-3` states the intended pattern **verbatim**: *"module-level, register at
> feature import."*

```ts
// features/plan-forge/documents/planArtifactDocument.ts
import { registerJsonDocumentProvider } from '@/features/studio/documents/registry';
import { createFetchDocumentHandle } from '@/features/studio/documents/fetchHandle';
import { planForgeApi } from '../api';

export const PLAN_ARTIFACT_DOC_TYPE = 'loreweave.plan-artifact.v1';

/** `{runId}:{artifactId}` — BE-3's route needs BOTH, and DocContext carries only bookId.
 *  resourceId is OPAQUE end-to-end (registry.ts:22 keys on `${type} ${resourceId}`), so a composite
 *  costs ZERO contract changes — while widening DocContext with runId would touch types.ts +
 *  useJsonDocument + EVERY existing provider for one caller's benefit. */
export const planArtifactResourceId = (runId: string, artifactId: string) => `${runId}:${artifactId}`;

let registered = false;

export function registerPlanArtifactDocumentProvider(): void {
  if (registered) return;                 // idempotent (entityDocument.ts:199-215's guard pattern)
  registered = true;
  registerJsonDocumentProvider({
    type: PLAN_ARTIFACT_DOC_TYPE,
    titleKey: 'documents.planArtifact',
    // FE-1 (35 F-P11). There is NO artifact-write route; `edits` go through POST /checkpoint's
    // re-fingerprinting deep-merge. A writable viewer would be a SECOND, un-fingerprinted write
    // channel into the pass ledger and would break PF-3's derivation.
    readOnly: true,
    open: (ctx, resourceId) => {
      const sep = resourceId.indexOf(':');          // split ONCE, on the FIRST ':'
      const runId = resourceId.slice(0, sep);
      const artifactId = resourceId.slice(sep + 1);
      // NEVER return a dead handle. useJsonDocument.ts:36 surfaces this as `openError`.
      if (sep <= 0 || !runId || !artifactId) {
        throw new Error(`plan-artifact resourceId must be "{runId}:{artifactId}" (got "${resourceId}")`);
      }
      return createFetchDocumentHandle(PLAN_ARTIFACT_DOC_TYPE, resourceId, {
        load: async () => {
          const a = await planForgeApi.getPlanArtifact(ctx.bookId, runId, artifactId, ctx.token);
          return { doc: a.content, etag: a.created_at ?? '' };
        },
        // §0.3: FetchHandleIO.save's OWN contract (fetchHandle.ts:8) is "throw ... to surface
        // conflict/error on the snapshot" — the handle catches and sets status:'error', so
        // DocumentHandle.save() still never throws (types.ts:38). Unreachable under readOnly;
        // defense-in-depth if a FUTURE view calls it. A save() that silently RESOLVED would be the
        // exact `silent-success-is-a-bug` class this whole slice exists to avoid.
        save: async () => { throw new Error('plan artifacts are read-only — edit them at the pass checkpoint'); },
      });
    },
  });
}

/** Test-only: undo the idempotency guard (mirrors entityDocument.ts:218). */
export function _resetPlanArtifactDocumentProvider(): void { registered = false; }
```

```ts
// frontend/src/features/studio/panels/catalog.ts — AT MODULE SCOPE, right after the import block
import { registerPlanArtifactDocumentProvider } from '@/features/plan-forge/documents/planArtifactDocument';
// Q-35-PS9: registered at MODULE IMPORT, not panel mount — the dock restores a json-editor tab from
// localStorage (useStudioLayout.ts:26) with NO guarantee PlannerPanel is mounted. catalog.ts is the
// correct anchor: it is the static "every panel the studio CAN open, mounted or not" module and is
// imported by StudioDock.tsx:9 as the dockview component map, so it ALWAYS loads before any panel renders.
registerPlanArtifactDocumentProvider();
```

⛔ **Do NOT use a `useEffect` in `StudioHostProvider` instead** — React runs **CHILD effects before PARENT
effects**, so a parent-mount registration is an **ordering race** against a restored panel's own mount.
**Module scope has no such ambiguity.** ⛔ **Add ZERO `registerPlanArtifactDocumentProvider()` calls to
`PlannerPanel` or `PassRailPanel`** — that is the whole point of this decision, and it means **W5-S12 needs no
registration change at all.**

**`PlanRunView.tsx`** — the row becomes:

```tsx
<button
  type="button"
  data-testid="plan-artifact-row"
  data-artifact-kind={a.kind}
  onClick={() => onOpenArtifact(a.artifact_id)}
  className="flex w-full justify-between gap-2 rounded bg-muted/40 px-2 py-0.5 text-left hover:bg-secondary"
>
  <span>{a.kind}</span>
  <span className="font-mono text-[10px] text-muted-foreground/60">{a.artifact_id.slice(0, 8)}</span>
</button>
```

with a new prop `onOpenArtifact: (artifactId: string) => void`, wired in `PlannerPanel`.

🔴 **C-10 — `openPanel('json-editor', { params })` IS WRONG AND MUST NOT BE COPIED** (`Q-35-PS9-COMPOSITE-ID` (3);
the spec's §4.1 line says it, and it is a bug). **That panelId is the SINGLETON** — opening a **second**
artifact would **retarget/replace the first tab**. Use the **shipped multi-instance form**
(`EditorPanel.tsx:310-314`) with the dock-id convention documented at `StudioHostProvider.tsx:50` —
**`json-editor:{FULL docType}:{resourceId}`**, *not* the spec's abbreviated `json-editor:plan-artifact:…`:

```tsx
const openArtifact = (artifactId: string, kind: string) => {
  if (!plan.run) return;
  const runId = plan.run.id;
  openPanel(`json-editor:${PLAN_ARTIFACT_DOC_TYPE}:${runId}:${artifactId}`, {
    component: 'json-editor',                                   // ← the multi-instance opt
    title: `${kind} · ${artifactId.slice(0, 8)}`,
    params: { docType: PLAN_ARTIFACT_DOC_TYPE, resourceId: planArtifactResourceId(runId, artifactId) },
    focus: true,
  });
};
```

(`{docType, resourceId}` **is** `JsonEditorPanel`'s params contract — [`JsonEditorPanel.tsx:20`](../../frontend/src/features/studio/panels/JsonEditorPanel.tsx#L20).
**N artifacts ⇒ N tabs**, for free.)

**⚠ The `DISTINCT ON (kind)` copy is NOT the whole fix — W5-S5c gives the list real PROVENANCE**
(`pass_id` + `superseded_by` + `created_at`), so **pass 6's `scene_plan` row is actually THERE**, labelled
`superseded`. Render the header as **`Latest per kind`** (not `Artifacts`) and the per-row copy from W5-S5c's
table. Without that, the user thinks their scenes vanished — **and the row they need is genuinely missing.**

**Tests** — `frontend/src/features/plan-forge/documents/__tests__/planArtifactDocument.test.ts` (**NEW**):
- 🔴 `test_the_provider_is_registered_by_IMPORTING_THE_CATALOG_ALONE` — a case that imports **ONLY**
  `@/features/studio/panels/catalog`, **renders NO panel, mounts NO PlannerPanel**, and asserts
  `getJsonDocumentProvider('loreweave.plan-artifact.v1')` is **defined**. ***This is the test that closes the
  unit-green/browser-dead gap*** (`checklist ⇒ test the effect`).
- `test_open_fetches_the_composite_route` — `open({token,bookId}, 'RUN:ART')` fetches a URL containing
  `/books/{bookId}/plan/runs/RUN/artifacts/ART`.
- `test_a_malformed_resourceId_REJECTS` — `'ART'`, `''`, `':x'` ⇒ **rejects with a message** (asserts **no
  silent no-op**).
- `test_two_composite_ids_yield_two_distinct_handles` — `_liveHandleCount() === 2` (**proves the composite key
  does not collide**).

`PlanRunView.test.tsx`:
- `test_clicking_an_artifact_row_opens_a_MULTI_INSTANCE_json_editor_tab` — assert `openPanel` is called with
  the **dock id** `` `json-editor:loreweave.plan-artifact.v1:${runId}:${artifactId}` `` **and**
  `{ component: 'json-editor', params: { docType, resourceId } }`. 🔴 **Assert it is NOT called with the bare
  `'json-editor'` singleton id** — that is the C-10 regression pin.

**DoD evidence:** `frontend: <N> passed` + the **live browser smoke leg (e)** (§10) + **two artifact rows open
as TWO tabs** (not one retargeted tab).

**dependsOn:** W5-S2, W5-S5c, W5-S6c, W5-S7, W5-S8

---

### W5-S10 · R2 + R3 — source resume + the Repair strip (interpret / refine / autofix)

**R2 — source-markdown resume.** Fed by **BE-3b** (W5-S3). `PlannerPanel`'s `markdown` state must seed
from `plan.run?.source_markdown` on run-load — as a **DERIVED DEFAULT, not a `useEffect` chasing a prop**
(the repo's FE rule; the panel **already does exactly this** for `effectiveModelRef` at
[`PlannerPanel.tsx:71-79`](../../frontend/src/features/plan-forge/components/PlannerPanel.tsx#L71) —
**mirror it**):

```tsx
// PlannerPanel.tsx — a derived default, NOT an effect.
const [markdownEdit, setMarkdownEdit] = useState<string | null>(null);
const markdown = markdownEdit ?? plan.run?.source_markdown ?? '';
// startNewRun() sets setMarkdownEdit(''); openRun() sets setMarkdownEdit(null) so the loaded
// run's own source shows through. The textarea's onChange sets markdownEdit.
```

**R3 — the free win.** `interpret` and `refine` have **routes AND `api.ts` methods AND zero callers**
(verified). `usePlanRun` exposes only `createRun / loadRun / resetRun / runSelfCheck / runValidate /
runCompile`. They need **buttons only** (`autofix` needs W5-S4's route).

Add to `usePlanRun`: `runInterpret(message: string)`, `runRefine(body: RefinePlanBody)`,
`runAutofix(maxRounds: number)`. Each: set busy → call → on success **`loadRun(runId)`** (the hook stays
hand-rolled — **do NOT `invalidateQueries(['plan-run'])`; that key has no cache entry**, C-13/§4) → clear
busy; on error set `error`.

#### 🔴 THE GATE IS WIDER THAN THE PLAN'S FIRST DRAFT (`Q-35-R3-REPAIR-STRIP-GATING`)

Gating on `selfCheck.gaps.length > 0` **alone leaves open the exact strand R3 exists to close.**
`usePlanRun` holds **`validation` as state SEPARATE from `selfCheck`**, set by a **SEPARATE button** —
`runValidate` **never populates `selfCheck`**. Spec 35 §39 says the panel *"strands a user at the first failed
**VALIDATION**"* — and gating on gaps alone means **that** user (and anyone reopening a past broken run:
`loadRun`/`resetRun` both `setSelfCheck(null)`) **still sees no repair tools. A failed validate IS a
diagnosis.**

Insert `<RepairStrip>` **immediately AFTER** the `{selfCheck && …}` block (ends ~`:91`) and **BEFORE** the
`{validation && …}` block (`:93`):

```ts
const gaps = selfCheck?.gaps ?? [];
const failedRules = validation && !validation.passed ? validation.rules.filter(r => !r.passed) : [];
const diagnosed = gaps.length > 0 || failedRules.length > 0;   // {diagnosed && <RepairStrip … />}
```
**Hidden** when nothing has been run (`selfCheck === null && validation === null`) **and** when the diagnosis
is **clean**. *(The Self-check / Validate buttons at `PlanRunView.tsx:63-70` are the one-click path to a
diagnosis.)*

#### 🔴 THE THREE CONTROLS — the plan's first-draft copy and wiring were BOTH wrong

| # | Control | `data-testid` | 🔴 What the register corrects |
|---|---|---|---|
| **1** | **interpret — a one-line INPUT + Send, NOT a bare button** | `plan-interpret-input` / `plan-interpret-btn` | `PlanInterpretRequest.user_message: str = Field(min_length=1)` (`plan_forge.py:65`) ⇒ **a zero-arg fire is a 422.** And `interpret_rules` runs `detect_intent(user_message)` + `search_index(user_message, …)` (`interpret.py:112-117`) — **the message is what SELECTS the spec paths.** Label: *"Tell the planner what's wrong, in your words"*. ⛔ **Do NOT auto-fill it with the gaps** — they are **already injected server-side** (`interpret.py:125-126, 259`); the user must not restate them. |
| **2** | **refine — the copy is "Fix these gaps", NOT "Apply the suggested fix"** | `plan-refine-btn` | 🔴 **THERE IS NO SUGGESTION TO APPLY.** `self_check` returns **only** `{"gaps","fidelity_score"}` (`plan_forge_service.py:963`) — it **drops** `ranked_gaps`/`suggestions`. ⛔ **Do NOT plumb `suggestions` through:** `suggest_fixes` emits **hardcoded Vietnamese POC strings** (`eval_fidelity.py:468-490`). Mirror what shipped autofix already does: **`revision = { focus_paths: [g.path for the ticked/top gaps] }`** (`plan_forge_service.py:840`). |
| **3** | **autofix — keep the spec's copy verbatim** | `plan-autofix-btn` | *"Fix the top gaps automatically (up to 3 rounds)"*. Needs **W5-S4**'s route; `max_rounds` clamps **1..5** server-side. |

**Severity:** filter/style on **`('error','warn')`** exactly as autofix does (`plan_forge_service.py:838`) —
🔴 **the BE emits `warn`, NOT `warning`** (the `types.ts` `PlanGapSeverity` comment is **drifted**).

**All three are PAID** ⇒ **all three take the PS-6 gate** — and they reuse the **SAME shared
`PaidPassConfirm` component** W5-S12 builds (**one component, four call sites — do not fork it per button**).
`model_ref` is a **REQUIRED `UUID` for interpret AND refine** (`plan_forge.py:59, 66`) ⇒ **the confirm cannot
submit with an empty `ModelPicker`** (a silent default violates SET-1..8 **and 422s anyway**). Autofix's
`model_ref` is optional (the service resolves it) — **pass the same explicitly-picked value.** Disabled while
`plan.polling || plan.busy`.

⚠ **`runAutofix` reads `{rounds, run}` (C-1), not an ack** — and it may answer **202** (C-7). When the worker
is on, `rounds[0].result` is `"pending"` and `run.active_job_id` is set → route it through the existing
`isAck` + poll path. **Do not look for a top-level `job_id`.**
⚠ **`runRefine` may answer 202 as well, or `{status:'no_change'}`** — discriminate on `status`
(W5-S8 / PS-5).

#### 🔴 OQ-5 — ONE honesty string in the new-run form (`Q-35-OQ5-EXISTING-STATE`, item 3)

`propose_spec` **reads the braindump and NOTHING ELSE** — proposing a plan for a book with 200 written
chapters **ignores every one of them** (`D-PLANFORGE-PROPOSE-BLIND`, an **existing** tracked row, gate #2).
⛔ **Do NOT wire `existing_state` into `propose.py` / `propose_llm.py` / `PlanRunCreate`** — *"helpfully"
doing so is **scope creep against a PO-approved plan row and must be rejected at `/review-impl`**.*
✅ **DO ship the copy string** in `PlannerPanel`'s new-run form, next to the source textarea:

> **"Proposed from this braindump only. Existing chapters are not read."**

*It is the repo's `silent-success-is-a-bug` law applied to a **KNOWN blindness**. It costs one i18n key, it
changes no engine code, and it does not inflate the wave.* **Test:** the string renders in the new-run form.

**Files:** `hooks/usePlanRun.ts`, `components/PlanRunView.tsx` (the strip), `components/PlannerPanel.tsx`
(seed + wiring + the OQ-5 string), `frontend/src/i18n/locales/en/studio.json` (the copy keys).

**Tests** — `PlanRunView.test.tsx` + `PlannerPanel.test.tsx` + `usePlanRun.test.ts`:
- **(a)** no strip when `selfCheck === null && validation === null`.
- **(b)** no strip when `gaps === [] && validation.passed`.
- 🔴 **(c)** **strip PRESENT when `validation.passed === false` AND `selfCheck === null`** — ***this is the
  regression the naive gate fails.***
- **(d)** strip present when `gaps.length > 0`.
- **(e)** buttons disabled while `busy || polling`.
- **(f)** a repair click does **NOT** hit the api **until the confirm is accepted**.
- **(g)** `test_reopening_a_run_seeds_the_source_textarea` — `loadRun` a run whose `source_markdown` is `"# X"`
  ⇒ `getByTestId('plan-source-input')` has value `"# X"`. **This is BE-3b's effect, observed.**
- **(h)** `runInterpret`/`runRefine`/`runAutofix` send **the picked `model_ref`**, and **refine sends
  `revision` as an OBJECT carrying `focus_paths`.**

**DoD evidence:** `frontend: <N> passed`, **including (c)**.

**dependsOn:** W5-S3, W5-S4, W5-S8, W5-S12 (`PaidPassConfirm`)

---

### W5-S11 · R4 — archive a failed run **and restore it** (PS-13)

> **Register: `Q-35-ARCHIVE-TOAST-COPY`.** Fed by **BE-4 + BE-4b** (W5-S5).

**Files:** `components/PlanRunsListView.tsx`, `components/PlannerPanel.tsx`, `hooks/usePlanRunsList.ts`
(**hand-rolled — it already owns `items` + `refresh()` at `:17-46`; call the api then `refresh()`. NOT
react-query**, C-13), `frontend/src/i18n/locales/en/studio.json`.

**1 · The toast mechanism ALREADY EXISTS — do not invent one.** **Sonner** is the app toaster
(`frontend/src/App.tsx:2,81` — `<Toaster position="bottom-right" richColors closeButton />`), and the exact
archive/undo shape **already ships** at `frontend/src/features/glossary/components/MergeCandidatePanel.tsx:106-114`:
`toast.success(msg, { action: { label: t('…undo'), onClick: () => void undo(...) } })`. **Copy it verbatim.**

**2 · The row action.** `PlanRunsListView.tsx`'s table (`:65-97`) has **no row action today**. Add a trailing
`<td>` with an **Archive** button (`data-testid="plan-run-archive"`, `stopPropagation` — the row itself opens
the run) using a 🔴 **two-click INLINE confirm in the row** (`Archive` → `Confirm?`) — **NOT `window.confirm`**
(unmockable in jsdom, and the panel is dockable). Archived rows (visible only under the toggle) render
**Restore** instead.

**3 · 🔴 THE LOCKED COPY** — `frontend/src/i18n/locales/en/studio.json` under `planner.list.*`. **NONE of these
may contain "delete" / "remove permanently":**

| key | string |
|---|---|
| `archiveButton` | *"Archive"* |
| `archiveConfirm` | *"Archive this run?"* |
| `archivedToast` | *"That run was archived."* |
| `archivedToastDesc` (sonner `description`) | *"It's hidden from the list, not deleted. You can restore it any time."* |
| `undo` | *"Undo"* |
| `restoredToast` | *"Run restored."* |
| `archiveBlockedToast` (the **409**) | *"That run has a pass running. Wait for it to finish, then archive it."* — `toast.error`, **no Undo action** |
| `showArchived` | *"Show archived"* |
| `restoreButton` | *"Restore"* |

**4 · Behaviour on archive:**
```
onArchive(runId):
  await archive(runId)                       // 409 → toast.error(archiveBlockedToast); return (row STAYS)
  const remaining = items.filter(r => r.id !== runId)   // items are newest-first from LIST
  if (selectedRunId === runId) {
    if (remaining.length) openRun(remaining[0].id)      // newest remaining
    else setView('list')                                // the empty state — NOT a blank run view
  }
  toast.success(t('planner.list.archivedToast'), {
    description: t('planner.list.archivedToastDesc'),
    duration: 10000,                          // ⚠ sonner's 4s default is TOO SHORT to hit Undo
    action: { label: t('planner.list.undo'), onClick: () => {
      void restore(runId).then(() => { openRun(runId); toast.success(t('planner.list.restoredToast')); });
    }},
  })
```
`runId` is captured in the closure, so **Undo still targets the right run after the fallback re-selects
another one.**

**5 · 🔴 A `Show archived` checkbox in the list header** (`data-testid="plan-runs-show-archived"`) →
`listRuns(..., { includeArchived: true })`, archived rows greyed with a **Restore** action. **Rationale (this
is not a nicety):** BE-4b's `?include_archived=true` otherwise has **zero consumers** (*an unread query param
is dead contract*), **and an Undo that exists only inside a dismissible toast means a mis-click at 3am is
EFFECTIVELY PERMANENT** — exactly the fear §4.4 says the copy must not create. ~25 lines; same slice.

**Tests** — `frontend/src/features/plan-forge/components/__tests__/PlanRunsListView.archive.test.tsx` (**new**):
- archive ⇒ `toast.success` called; 🔴 **assert the message + description do NOT match `/delet|remov/i`.**
  ***This is the literal guard for the concern — enforce it with an assertion, not a review note.***
- the toast options carry `action.label === 'Undo'`; invoking `action.onClick()` calls
  `planForgeApi.restoreRun` with **that** `runId` and **re-opens it**.
- archiving the **selected** run re-selects `items[0]` of the remainder; archiving the **last** run lands on
  the **empty state**.
- a **409** from `archiveRun` ⇒ `toast.error(archiveBlockedToast)` with **no action**, and the row **stays**.
- `Show archived` re-fetches with `include_archived=true` and its rows offer **Restore**.

**DoD evidence:** `frontend: <N> passed` + the live smoke (archive → the row goes → Undo → it is back).

**dependsOn:** W5-S5, W5-S8

---

### W5-S12 · THE PASS RAIL — `plan-passes` (the panel)

**Category:** `editor` (same as `planner`/`plan-hub` — the Rail is a planning surface, not a quality
diagnostic). **Root:** `data-testid="studio-plan-passes-panel"`.
**The HTML draft is the acceptance criterion:** `design-drafts/screens/studio/screen-planforge-pass-rail.html`.
**Every state it renders must exist in the built panel.**

> **Register: `Q-35-PS7-BARE-ID-PANEL` · `Q-35-EMPTY-NOT-COMPILED` · `Q-35-FORCE-OVERRIDE-AFFORDANCE` ·
> `Q-35-NO-HOLD-COPY` · `Q-35-PS6-COST-CONFIRM-SHAPE` · `Q-35-PARAMS-UNSPECIFIED` ·
> `Q-35-LINK-GATE-ASYMMETRY` · `Q-35-OQ2-EDITS-EDITOR-SHAPE` · `Q-35-DEPENDENCY-GRAPH-INVERSION` ·
> `Q-35-MOCKUP-START-POINT` · `Q-35-PS1-NO-DELETE`.**

**PS-7 — `plan-passes` opens on a BARE ID.** It is **book-scoped**, and `useStudioHost()` already supplies
`bookId` (`PlannerPanel.tsx:26`). The panel **resolves the run ITSELF** in `usePassRail.ts` (controller, no
JSX). A `run_id` is a **selection inside the panel**, never an opening argument. ⇒ no `hiddenFromPalette`, no
`params`, **and X-12 does not bite this panel** (X-12 governs panels that *need* `params`).

🔴 **THE DEFAULT-RUN RULE — a pure function over the FIRST page of `GET /books/{bookId}/plan/runs`. No new
backend route: the list response ALREADY carries the signal.**

```ts
const defaultRun = items.find(r => r.artifacts.some(a => a.kind === PACKAGE_KIND));   // PACKAGE_KIND = 'package'
```
- **`items` is ALREADY newest-first** (`plan_runs.py:153` `ORDER BY created_at DESC, id DESC`) ⇒ `.find` **IS**
  "newest". **Do not re-sort.**
- **`artifacts` is ALREADY on every list item** (`list_runs` → `_serialize_run` → `list_artifact_refs`).
  ⛔ **Do NOT fetch each run's detail to test for a package (N+1).**
- **Pin `'package'` to a shared const** mirroring `plan_pass_service.py:100`. **Do not free-string it.**
- **PAGINATION IS REAL:** the route is `limit` default 20 / **max 50** (`plan_forge.py:134`). **Request
  `limit=50` and scan ONLY that first page. Do NOT walk `next_cursor`** — a book whose 50 newest runs are all
  uncompiled falls to state (b) below; the picker already exposes every run, so **the cost of a miss is one
  click**, whereas cursor-walking makes panel-open latency **unbounded**.
- 🔴 **The test that proves it:** *the selector picks the newest **PACKAGE-BEARING** run **when a NEWER
  package-less run sits above it in `items`**.* **A naive `items[0]` implementation passes a naive test and
  fails this one.**

**Files**

| File | Change |
|---|---|
| `frontend/src/features/plan-forge/hooks/usePassRail.ts` | **NEW** — the controller (≤~200 lines, **no JSX**) |
| `frontend/src/features/studio/panels/PassRailPanel.tsx` | **NEW** — the view (≤~100 lines) |
| `frontend/src/features/plan-forge/components/` | **NEW:** `PassRow.tsx` · `PassBlockedState.tsx` · `CastCheckpointCard.tsx` · `BeatsCheckpointCard.tsx` · `LinkMenu.tsx` |
| `frontend/src/features/studio/panels/planforge/PaidPassConfirm.tsx` | **NEW — ONE component, FOUR call sites** (run-pass · interpret · refine · autofix). **Do not fork it per button.** |
| `frontend/src/features/plan-forge/__tests__/usePassRail.test.tsx` | **NEW** |
| `frontend/src/features/studio/panels/__tests__/PassRailPanel.test.tsx` + `PassRailPanel.blocked.test.tsx` | **NEW** |

#### The data it reads

**ONE** read: `GET /v1/composition/books/{bookId}/plan/runs/{runId}/passes` — **NOT the run detail**, and
**NOT a mutation's response body.** After **ANY** mutation (`POST /checkpoint`, `POST /passes/{id}/run`,
`PATCH /novel-system-spec`), **IGNORE the response's pass block and REFETCH `/passes`.** *One producer in the
BE, one consumer read in the FE.* (`GET …/passes` is also the **only** response carrying **`compiled`** —
*absent ≠ zero*.) Plus `GET …/plan/runs?limit=50` for the picker, and
`GET /plan/bootstrap/{proposal_id}` for the cast card's seed diff (**needs BE-20's `bootstrap_proposal_id`**).

#### 🔴 THE FE CARRIES **ZERO** DEPENDENCY KNOWLEDGE (`Q-35-DEPENDENCY-GRAPH-INVERSION`)

Every gating answer is **already on the wire**. Each of these is a **`/review-impl` finding if violated**:
- **Run button:** `disabled = row.blockers.length > 0 || anyJobInFlight` — **from `row.blockers`**, ⛔ **never
  from the row's index, its position in `PASS_ORDER`, or any FE-side dependency map.**
- **Progress header:** render **`pass_cursor` / `passes.length` straight from the envelope.** ⛔ Do not count
  fresh rows client-side. ⛔ **Do not hard-code `"1/7"`** (§4.1b's mock shows it as an *illustration of a
  derived value*, not a constant).
- **Row order:** iterate `envelope.passes[]` **as returned** (it is already `PASS_ORDER`).
- 🔴 **A `PASS_DEPS` / `DEPENDS_ON` const in FE code IS THE DEFECT this rule exists to prevent — reject it in
  review.** `types.ts` may declare `PassId` and a flat **`PASS_ORDER`** (for the 7 skeleton rows + the drift
  pin) — **that is all.**
- **THE MECHANICAL GUARD (`Q-35-MOCKUP-START-POINT` rule 3):** a vitest that feeds fixture A
  (`world.blockers=["cast"]`, `beats.blockers=[]`) ⇒ world's Run **disabled**, beats' **enabled**; **and**
  fixture B, **INVERTED** (`world.blockers=[]`, `beats.blockers=["motifs"]`) ⇒ **the enable/disable INVERTS
  with it.** ***Test B is the one that fails if anyone hard-codes the graph from a mock — which is exactly the
  bug spec 35's own first draft shipped in its ASCII.***

#### 🔴 EVERY STATE IS A STRICT 4-WAY SWITCH, EVALUATED **BEFORE ANY PASS ROW RENDERS** (`Q-35-EMPTY-NOT-COMPILED`)

1. **LOADING** (runs list **or** ledger in flight) → **exactly 7 skeleton rows**, mapped from the FE-local
   `PASS_ORDER`. ⛔ **Never a spinner, never `<Spinner/>`, never `role="status"`.**
2. **NO RUNS** (`runs.length === 0`, **derived from `GET …/plan/runs` — NOT from a 404 on `/passes`**) →
   *"No plan run for this book yet."* + **"Open the Planner"** → `host.openPanel('planner', { focus: true })`.
   ⛔ **No `<Link>`, no `useNavigate()` — DOCK-7.**
3. 🔴 **NOT COMPILED** (`ledger.compiled === false`) → *"This run has no compiled package — the passes read
   it. Compile it in the Planner first."* + the same button. **RENDER NO PASS ROWS AND NO RUN BUTTONS AT ALL
   — ZERO, not seven greyed ones.** **Grounding:** `PASS_REGISTRY` gives **BOTH** dependency-graph roots —
   `motifs` and `cast`, the only two with `depends_on=()` — **and BOTH have `reads_package=True`.** With no
   package **there is not ONE runnable pass in the graph**, so a rail of seven "pending" rows with live Run
   buttons is **both false and a PAID-ACTION TRAP** (a user clicks Run on `motifs`, **pays**, and it cannot
   run). *Disabled rows still imply "the compiler is merely waiting to be told to go" — exactly the
   impression the service's `"Absent ≠ zero"` comment was written to prevent.*
4. **ELSE** → the rail.

🔴 **A 404 from `GET …/passes` is a DIFFERENT state from (2)** — it means **"unknown/archived run"**: show
*"That run no longer exists."* and **fall back to the newest remaining run.** ⛔ **Do not collapse it into "no
runs".**

**BACKEND (same slice):** add/confirm `test_pass_status_compiled_false_when_no_package` asserting
`pass_status()` returns **`compiled: false` and STILL emits all 7 rows** (*the FE, not the service, is what
suppresses them*).

#### The writes it offers

**The checkpoint route has TWO decisions, not three:** `decision = "accepted" if approved else "rejected"`
([`plan_forge_service.py:673`](../../services/composition-service/app/services/plan_forge_service.py#L673)).
**There is no "hold".** Every row below maps onto one of those two, or onto `/run`.

| Action | Call | Gate / copy |
|---|---|---|
| **Run a pass** | `POST …/passes/{pass_id}/run {model_ref, force:false}` 🔴 **and NO `params` key** | **PAID.** PS-6 confirm naming the pass + the model + that this spends. Disabled while any job is in flight. Disabled when `blockers[]` is non-empty (the 409 is the fallback, not the plan). |
| **Force-run** | same, `force: true` | **The reserved human override.** Only inside the **BLOCKED** state (**not** literally an HTTP 409 — see below), never the primary button. Copy names what it does. |
| **Approve** | `POST …/checkpoint {approved:true, pass_id}` | Free. → `decision:"accepted"`. **For `cast`: DISABLED until the seed proposal reads `applied`.** |
| **Approve WITH edits** ⭐ **the primary path** | `POST …/checkpoint {approved:true, pass_id, edits}` | Free. **ONE call.** The seed gate runs **BEFORE the write** ([`:634`](../../services/composition-service/app/services/plan_forge_service.py#L634) — *"THE GATE RUNS BEFORE ANY WRITE"*), so a refused approve-with-edits mutates **nothing** — no half-applied edit to retry on top of itself. The panel must **say**: *"Approving these cast edits will stale the 4 passes below it."* |
| **Save edits (no approval)** | `POST …/checkpoint {approved:false, pass_id, edits}` | Free — **and it writes `decision:"rejected"`.** ⚠ Copy must say what it does: *"Saves your edits. `cast` stays **rejected** until you approve it — nothing below it can run."* **The button is labelled "Save edits", NEVER "Hold".** |
| **Reject** | `POST …/checkpoint {approved:false, pass_id}` | Free. Same write, no edits. |
| **Re-run** | `POST …/passes/{pass_id}/run` on a completed pass | Paid, same gate. The way a pass is **un-done** (PS-1). |
| **Link to spec tree** | `POST …/link {target}` | Free. `skeleton` \| `scene_plan`. 🔴 **The strict predicate GATES A CONFIRM, NOT A DISABLE** — see below. |

**PS-1 — the Rail offers Re-run and Reject. It offers NO Delete.** The ledger is derived from `pass_state`;
a pass is un-done by **re-running** it (which re-fingerprints and stales downstream) or by **rejecting** it.
A "delete this pass" button would be a second, incoherent invalidation mechanism — the exact thing PF-3
exists to avoid. **Do not add one** — not in the row, not in an overflow menu, not behind a confirm.
🔴 **Guard test:** assert the rendered action set for a completed pass contains **no button matching
`/delete|remove|discard/i`**, so a later wave cannot reintroduce it silently.
**Where a user would reach for "delete", the Rail SAYS WHAT TO DO INSTEAD:** Re-run's tooltip/confirm reads
*"Re-runs this pass and stales every pass below it"*, and Reject reads *"`<pass>` stays rejected until you
approve it — nothing below it can run."*

#### 🔴 THREE checkpoint buttons — and the literal string **"Hold" is FORBIDDEN** (`Q-35-NO-HOLD-COPY`)

`decision = "accepted" if approved else "rejected"` (`plan_forge_service.py:673`). **There is no third
decision. A "Hold" label would LIE about the write.**

| | Button | Body | Copy (i18n `studio` ns, `useTranslation('studio')` + `defaultValue` — the `BootstrapPanel.tsx:33` convention) |
|---|---|---|---|
| **PRIMARY** (rightmost, filled) | **Approve** ⇄ **Approve with edits** (**ONE button whose label swaps on dirty state**) | `{approved:true, pass_id, edits?}` — 🔴 **send `edits` in the SAME call when dirty. NEVER save-then-approve.** The seed gate runs **BEFORE ANY WRITE** (`:634`, `:643`), so a refused approve mutates **nothing** — there is no half-applied edit to retry on top of itself. | `planner.pass.approve` · `planner.pass.approveWithEdits` · `approveWithEditsHint` = *"Approving these {{pass}} edits will stale the {{count}} passes below it."* |
| **SECONDARY** | **Save edits** (only enabled when dirty) | `{approved:false, pass_id, edits}` | `saveEditsHint` = *"Saves your edits and marks {{pass}} rejected until you approve it — nothing below it can run."* |
| **TERTIARY** (ghost/destructive) | **Reject** | `{approved:false, pass_id}` | `planner.pass.reject` |

**Approve is DISABLED for `cast`** until its bootstrap proposal reads `applied` (F-P4/PS-3) — **with the
reason ON SCREEN**, not hidden in a 409.

#### 🔴 THE STUCK BANNER — render `view.blocked_at` **DIRECTLY. Derive NOTHING.** (C-6 / PS-12)

W5-S1 Change 4 **fixed `blocked_at` at the source**. So:
- The banner **is** `view.blocked_at`. ⛔ **No FE-side copy of the predicate** — *a derived rule duplicated
  across BE+FE is this repo's known drift class.*
- The amber **`rejected`** chip still comes from the per-pass **`decision`** field on the row.
- A **rejected** `cast` now reports **`blocked_at: "cast"` ON THE WIRE** — *the opposite of what the plan's
  blind draft assumed.* **Test:** a fixture view with `cast.decision === "rejected"` and
  `blocked_at === "cast"` ⇒ the Rail shows *"stuck at cast"* and **Approve is live**.

#### 🔴 `params`: **THE FE SENDS NONE. EVER.** (`Q-35-PARAMS-UNSPECIFIED`)

The POST body is **`{ model_ref?, force }`** — **omit `params` entirely.** The route's Pydantic model already
supplies `params = {}` (`plan_forge.py:84`), so an omitted key and `{}` are identical.
🔴 **NEVER send a key the user did not explicitly change — in particular NEVER pre-fill and send the engine
defaults.** `params` is an input to the **PF-3 fingerprint**
(`sha256(canonical({"inputs": [...], "params": params or {}}))`, `plan_pass_service.py:136-150`), and
**`{"k_ceiling":3}` hashes DIFFERENTLY from `{}`** even though the behaviour is identical. A GUI that
"helpfully" echoes defaults **forks the fingerprint against every pass the MCP tool ran with `{}`** → those
passes read **STALE** → **the paid Run button charges the user to recompute an identical artifact.**
***That is the paid-for-nothing defect class — the CRITICAL class in §0 rule 3.***
**v1 ships NO "Advanced" params form.** (Only `motifs` and `scenes` read `params` at all; the other five never
do — an accepted-but-ignored input is the silent-no-op class. If the PO ever wants the knobs, the exact
six-key closed-set build is pre-specified in `Q-35-PARAMS-UNSPECIFIED` (3) — no further design needed.)
🔴 **TEST THAT PINS IT:** the Run-pass request body for a `cast` pass **has no `params` key**.

#### 🔴 THE FORCE OVERRIDE — "the 409 state" **MEANS THE BLOCKED STATE** (`Q-35-FORCE-OVERRIDE-AFFORDANCE`)

**BINDING DISAMBIGUATION:** `derive_view` already ships **`blockers: []` on every row**, so **the panel knows a
pass is blocked BEFORE it ever fires a request** — and §4.3 says the primary Run button is **disabled** when
`blockers[]` is non-empty. ⇒ **a well-behaved panel NEVER RECEIVES a 409**, and *a builder reading "inside the
409 state" literally would ship a force door NO USER CAN REACH* (making DoD leg (d) undeliverable).

**Therefore:** render ONE **`<PassBlockedState>`** whenever `row.blockers.length > 0`. The 409
`UPSTREAM_STALE` catch renders **the SAME component** (it is only the race/stale-ledger fallback). **The force
button lives in that component and NOWHERE else.**

- `usePassRail` exposes **TWO DISTINCT FUNCTIONS**, never one boolean-parameterised one:
  **`runPass(passId, {model_ref})` sends `force: false`** and **`forceRunPass(passId, {model_ref})` sends
  `force: true`.** *Two call sites = the override cannot be reached by flipping a prop.*
- `<PassBlockedState>` renders the blockers **as copy** (*"`world` needs `cast` (not accepted)."*), each
  blocker **click-to-scroll** to that pass's row, and **THEN**, visually **subordinate** to it, the escape:
  `<Button variant="ghost" size="sm" data-testid={\`pass-force-run-${passId}\`}>Run anyway</Button>`.
  ⛔ It must **NOT** be `variant="default"`/primary and must **not** sit in the row's primary action slot.
- **"Run anyway" opens the SAME `PaidPassConfirm` the normal Run uses — force does NOT skip the cost gate** —
  whose body copy is exactly: **"Run `{pass_id}` against a `{blockers.join('`, `')}` you have not accepted.
  The result may contradict the plan above it."** **Only on confirm** does it call `forceRunPass`.
- a11y: a real `<button>`, `aria-describedby` → the warning copy's id.
- ⛔ **Do NOT touch `mcp/server.py:3599-3611`** — **`force` stays ABSENT from `plan_run_pass`.** *Adding it
  back is the design's central inversion.*

#### 🔴 PS-6 — `PaidPassConfirm.tsx`: FOUR facts, ZERO new routes, and **NO FABRICATED TOTAL** (`Q-35-PS6-COST-CONFIRM-SHAPE`)

**One shared component; four call sites (run-pass · interpret · refine · autofix).** It renders an **in-panel
confirm step** (NOT a route, NOT a Tier-W token flow):

- **(a) THE PASS** — the human pass name + `pass_id`.
- **(b) THE MODEL** — the value the user **explicitly picked** in `ModelPicker`. 🔴 **NEVER a silent default:**
  if `model_ref` is unset the confirm button is **DISABLED** with *"pick a model"* (the route requires
  `model_ref: UUID`).
- **(c) THE SPEND CLASS + RATE — DO NOT INVENT A TOTAL.** Reuse the pricing the FE **already holds**
  (`features/ai-models/api.ts` → `ModelPricing` + the derived `isFree` / `isPriced`; `ModelPicker.tsx:466-470`
  already renders it). Exactly one of:
  - free/local → *"Runs locally — no per-token cost."* (reuse `modelPicker.freeHint`)
  - priced → *"This SPENDS. `<alias>` bills $`<in>`/$`<out>` per 1M tokens; the final cost depends on how much
    of your plan this pass reads."* (**rate only — never a fabricated total**)
  - unpriced → *"This spends. This model has no pricing on file, so the cost cannot be shown."* (fails-closed
    honesty)
- **(d)** a single primary *"Run pass — this spends"* + **Cancel**.

🔴 **HARD PROHIBITION (write it as a comment in the component):** do **NOT** clone `_mine_estimate`
(`mcp/server.py:271-277`) — it returns a **HARDCODED `0.50 if scope=="book" else 2.00`.** That constant is
legitimate only because it feeds a Tier-W billing precheck. **A confirm that shows a FAKE number is WORSE than
one that shows none.** And do **NOT** add `POST /actions/plan_run_pass/estimate` or any
`/actions/<name>/estimate|confirm` path — **three such invented FE calls 404 in production today** (plan 30 §3.3).

🔴 **THE DOUBLE-FIRE GUARD (this is the part that actually protects the wallet — it is NOT optional).**
Derive it purely from data the route already returns: **`const inFlight = passes.some(p => p.status === 'pending' || p.status === 'running')`.**
While `inFlight`, **EVERY paid button in the panel** (run-pass, interpret, refine, autofix, compile) is
`disabled` and the in-flight pass spins. ⚠ **THERE IS NO SERVER-SIDE IN-FLIGHT GUARD in `plan_pass_service.py`
today — the FE guard IS the whole guard.** The confirm dialog must also be **single-flight**: close it on
submit; the button cannot be re-clicked into a second POST.

#### 🔴 QUOTA HONESTY — the one real value OQ-1 was chasing (C-12 / `Q-35-OQ1-TIER-W-DESCRIPTOR` (3))

Plan passes **ARE** ledger-claimed: the worker's LLM call goes through provider-registry's
**fail-CLOSED `runGuardrailPreflight`** (`jobs_handler.go:203-218, :415`) → **402 `LLM_QUOTA_EXCEEDED` before a
single token is spent**. **So make the refusal HONEST in the panel:** when a `plan_pass` job terminates
`failed` **because the reserve was denied**, the job's error **must carry the SDK's `LLM_QUOTA_EXCEEDED` code
through to the panel**, which renders 🔴 **"Spend limit reached — the pass did not run and you were not
charged"**, **NOT a generic *"pass failed"*.**
**Tests:** BE — make the worker's LLM stub raise `LLMQuotaExceeded`; assert the persisted job error /
`pass_state` entry carries the quota code **and that the pass returns to a non-`running` state (the rail must
not wedge)**. FE — the quota code renders the budget message.

#### 🔴 LINK — the strict predicate GATES A CONFIRM, **NOT A DISABLE** (`Q-35-LINK-GATE-ASYMMETRY`)

`scenes` and `self_heal` are **both `checkpoint="advisory"`**, and `default_decision()` stamps
`decision="auto"` the moment an advisory pass completes — which `is_accepted()` **counts as accepted**. ⇒
*"fresh + accepted"* collapses to **just "fresh"** in every normal run. **Hard-disabling on staleness would
delete the user's only GUI door to an action the service PERMITS (GG-1) and buy nothing** — and §4.4 already
rules that stale means *"do this again"*, **not** *"error"*.

**BE: no change.** The linker is **idempotent and never reclaims a user edit** (`:1030-1032`), so linking a
stale plan is **recoverable, not destructive.**

**FE — derive from the ledger the panel already polls (NO new route, NO second fetch):**
```ts
// MIRROR the service's pointer order (_scenes_by_event, plan_forge_service.py:1089) — NOT latest-by-kind
const sceneSource = passes.self_heal.status === 'completed' ? passes.self_heal
                  : passes.scenes.status === 'completed'    ? passes.scenes : null;
const serviceWouldAccept = sceneSource !== null;
const strict = serviceWouldAccept && sceneSource.fresh && ['accepted','auto'].includes(sceneSource.decision);
```
| state | `scene_plan` menu item |
|---|---|
| `strict` | **enabled, plain.** Click links immediately. |
| `serviceWouldAccept && !strict` | **enabled, amber `stale` chip.** Click opens a **confirm**: *"This scene plan is stale — its inputs changed since `{pass_id}` ran. Linking it now puts the OLDER scenes in the spec tree. Re-run `scenes` first, or link it anyway."* Buttons: **Re-run scenes** (scrolls to that row) · **Link anyway**. **Free action — no cost confirm.** |
| `!serviceWouldAccept` | **disabled**, tooltip = the service's own words: *"No scene plan to link — run the `scenes` pass first."* |

`skeleton` item: **enabled iff `ledger.compiled === true`**; else disabled with *"This run has no compiled
package — compile it in the Planner first."*

🔴 **ALWAYS render a 409 `LINK_REFUSED` `detail.message` VERBATIM in a toast, in BOTH targets — even when the
client predicate said go.** The FE cannot see the artifact's `chapters` emptiness that `:1055` refuses on, so
**the client predicate is an optimization, never the truth** (repo law: *mocked-client-hides-server-side-filters*).

🔴 **COPY RULE (the actual answer to the concern) — add it as an inline comment so a later agent does not
"tighten" it into a lie.** **BANNED:** *"the server requires an accepted/fresh scene plan"*, *"you must re-run
before linking"*. **REQUIRED framing:** what the link **WILL DO** (*"the spec tree will show the older
scenes"*) and what the user **SHOULD** do (*"re-run first"*). **A copy-assertion test greps the rendered
confirm for the banned phrasing and FAILS on a hit.**

#### 🔴 THE EDIT FORMS — `cast` + `beats` ONLY, and **NO generic JSON-patch editor. Not in v1, not EVER, against this backend.** (`Q-35-OQ2-EDITS-EDITOR-SHAPE`)

**This is not a taste call — the code FORBIDS the generic editor.** `_deep_merge` (`validate.py:20-36`) is a
**merge, not RFC-6902**: its loop only ever **SETS** keys (`out[key] = …`); **nothing is ever popped.**
🔴 **`edits` CANNOT REMOVE ANY KEY, EVER.** A generic JSON editor's core gesture is *"delete this field, hit
save"* — the user does it, the PUT **succeeds**, and the artifact comes back **unchanged**. That is
`silent-success-is-a-bug`, shipped, on a surface the user **paid an LLM** to produce.

🔴 **THE FORMS SEND THE FULL LIST, NEVER A PARTIAL ONE — THIS IS THE TRAP.** `_deep_merge` (`:23-31`) merges a
list-of-dicts **by `id` (upsert, no delete)** *iff* `val[0]` has an `"id"`, and **otherwise REPLACES THE LIST
WHOLESALE**. **No list item in any pass artifact carries an `id`** ⇒ cast/beats edits take the
**replace-wholesale** branch — *which is what makes add / remove / rename / role-change all work.* **But a
form that PATCHes only the changed rows SILENTLY DELETES every character it omitted.** ⇒ **serialise the
ENTIRE edited array.**

- **CAST form** — body is `{"cast": [...]}`; per-item fields **exactly** `{name, role, archetype, summary,
  is_new, attributes}`. An editable table (add row / remove row / rename / change `role`) emitting
  `edits = {"cast": [<FULL list>]}`.
- **BEATS form** — 🔴 **spec 35's OQ-2 wording is WRONG and must be corrected in the spec: there is NO
  `summary` and NO `tension` on a beat.** The real body is **THREE parallel arrays**:
  `chapters:[{ordinal, event_id, title, beat_role, intent}]` ·
  `tension_curve:[{chapter_index, beat_role, tension_target}]` · `unmapped_beats:[…]`. **Tension is NOT on the
  chapter row — it lives in `tension_curve`, joined `chapter_index` ⇄ `ordinal`.** So the form edits
  `title`/`beat_role`/`intent` on `chapters[]` **and** `tension_target` on `tension_curve[]`, and **emits BOTH
  FULL arrays in one `edits` object.** Render `unmapped_beats` **read-only, as a warning strip** — pass 6
  honours the curve **verbatim** (`plan_pass_adapters.py:238-247`), so an edited curve is **load-bearing**, and
  an unmapped beat is **a beat the story never hits**.
- **The other four kinds** (`motif_plan`, `world_plan`, `char_arc_plan`, `scene_plan`) → **read-only viewer +
  "Re-run this pass"** (the W5-S9 `plan-artifact` provider, `readOnly: true`).
- 🔴 **Regression test in `tests/unit/test_plan_pass_checkpoint.py`** (which today source-greps `_review_pass`
  and asserts **NOTHING** about merge semantics): assert **(i)**
  `_deep_merge({"cast":[{"name":"A"},{"name":"B"}]}, {"cast":[{"name":"A"}]}) == {"cast":[{"name":"A"}]}`
  (**removal works**), and **(ii)** a deep_merge of a body carrying `id`s does **NOT** delete — *the executable
  statement of why no artifact schema may introduce `id`* (the constraint W5-S6/B2 must honour).

#### Every state, rendered (this table IS the panel's test matrix)

| State | What it shows | `data-testid` |
|---|---|---|
| **Empty — no runs** | *"No plan run for this book yet."* + a button → `host.openPanel('planner')`. **NEVER a route hop** (DOCK-7). | `pass-rail-empty-no-runs` |
| **Empty — run not compiled** | `compiled: false` from the ledger. **Say it; do not render seven tidy "pending" rows** — the service went out of its way to distinguish this ([`:1012-1015`](../../services/composition-service/app/services/plan_forge_service.py#L1012): *"Absent ≠ zero"*): *"This run has no compiled package — the passes read it. Compile it in the Planner first."* + the openPanel button. | `pass-rail-not-compiled` |
| **Loading** | Skeleton rows for the **7 known passes** — the pass list is a **closed set**, render it from a local `PASS_ORDER` const, never from a spinner. | `pass-rail-skeleton` |
| **Pass running** | Row shows a spinner + `job_id`; **every** Run button disabled; the poll is live. | `pass-row-{id}` + `pass-running` |
| **🔴 BLOCKED** (`row.blockers.length > 0` — **derived from the ledger, NOT from an HTTP 409**) | `blockers[]` **is** the copy: *"`world` needs `cast` (not accepted)."* Each blocker is **click-to-scroll** to that pass's row. Then, and only then, the **"Run anyway"** (force) escape, behind the SAME paid confirm. The 409 `UPSTREAM_STALE` catch renders **this same component** (the race fallback). ⚠ `blockers[]` is **exactly `depends_on`, filtered** — it can never name a non-upstream. ⚠ **A runnable pass renders NO force button AT ALL** (absent from the DOM, not merely disabled). | `pass-blockers-{id}`, `pass-force-run-{id}` |
| **🔴 Rejected (ANY pass with `decision:"rejected"`)** | Reached by Save-edits or Reject. `is_accepted` is false ⇒ everything downstream stays blocked — **and, after W5-S1 Change 4 (PS-12), `blocked_at` CORRECTLY REPORTS IT** (`blocked_at === "cast"`). ⇒ 🔴 **Render `view.blocked_at` DIRECTLY. DERIVE NOTHING IN THE PANEL.** *(The plan's blind draft said `blocked_at` goes `null` here and had the FE re-derive it — C-6 fixed the SOURCE instead, so the FE predicate is now forbidden.)* Row renders an amber **rejected** chip + **Approve** and **Re-run** both live. **NB: a rejected ADVISORY pass (`character_arcs`) is `blocked_at` too** — it hard-blocks `scenes`. | `pass-rail-stuck-banner`, `pass-rejected-{id}` |
| **Checkpoint refused (409 `CHECKPOINT_REFUSED`)** | Render `detail.message` **verbatim** (the service's messages are good, and BE-22 fixes the one that wasn't). For the cast-seed case, **deep-link to the seed card** instead of repeating the text. | `pass-checkpoint-error` |
| **Stale** | A pass that is `completed` but `fresh:false` renders **struck-through freshness + an amber "stale" chip**, and its Run button re-labels to **Re-run**. Stale is the compiler's **normal state after an edit** — it must read as *"do this again"*, **never as an error**. | `pass-stale-{id}` |
| **Cost-gate / paid-action in flight** | PS-6 confirm → then a disabled rail with the in-flight pass spinning. **A second click cannot double-charge.** | `pass-run-confirm` |
| **No model / BYOK empty** | `ModelPicker`'s empty state → `AddModelCta`. ⚠ **This is X-1.** Until X-1 lands, that component **tears the dock down**. | — |
| **Archived run** | Disappears from the picker; if it was selected, fall back to the newest remaining + toast *"That run was archived."* + **Undo**. | — |

#### The cast checkpoint card (the headline flow — BE-20's whole reason for existing)

```
│    ┌──────────────────────────────────────────────────────┐    │
│    │  CAST — 7 characters, 3 roles bound                  │    │
│    │  Lâm Vân · protagonist · 冷面 stoic, driven          │    │
│    │  …                                                   │    │
│    │  ⚠ Glossary seed: 7 new entities  [review] pending   │    │  ← BE-20's bootstrap_proposal_id
│    │  [Save edits] [Reject]   [ Approve ] ← disabled      │    │  ← NO "Hold". Save edits ⇒ REJECTED
│    └──────────────────────────────────────────────────────┘    │
```

- Read `pass.bootstrap_proposal_id` (BE-20) → `planForgeApi.bootstrapGet(bookId, proposalId, token)` → render
  the seed diff inline (reuse `BootstrapPanel`'s diff rendering if it factors cleanly; otherwise a compact
  inline list).
- **Approve is `disabled` until `proposal.status === 'applied'`**, with the reason **on screen**
  (*"Apply the glossary seed first — the cast can't be accepted until its characters exist."*), not hidden
  in a 409.
- Approve → apply flow uses the **already-shipped** `bootstrapApprove` / `bootstrapApply` api methods.

#### OCC — **NONE, deliberately (PS-8)**

`plan_run.pass_state` has no version column and `review_checkpoint` is **idempotent and last-write-wins by
design** ([`:594`](../../services/composition-service/app/services/plan_forge_service.py#L594): *"Idempotent,
no LLM"*). There is nothing to 412 on, and inventing an `If-Match` here would be *"a new confirmation
convention"* — AN-8 says finding one is finding a **defect**. **Add no OCC to PlanForge.** What protects the
user is **derived freshness**: whatever the last decision was, `fresh`/`blocked_at` recompute from the
fingerprints on the next read.

#### Tests

`frontend/src/features/plan-forge/__tests__/usePassRail.test.tsx`:
- 🔴 `test_the_default_run_is_the_newest_PACKAGE_BEARING_run` — a **newer package-less** run sits **above** the
  compiled one in `items` ⇒ the selector picks the **compiled** one. ***A naive `items[0]` passes every other
  test and fails this one.***
- `test_the_stuck_banner_renders_blocked_at_VERBATIM` — ledger with `cast.decision === 'rejected'` **and
  `blocked_at: 'cast'`** ⇒ the banner says *"stuck at cast"* and **Approve is live**. 🔴 **Assert the panel
  computes NO predicate of its own** (grep the hook for `accepted`/`auto` literals — there must be none).
- `test_world_is_disabled_and_beats_is_enabled_on_a_cast_pending_run` — the F-P12 inversion, in the controller.
- 🔴 `test_the_enable_disable_INVERTS_with_an_inverted_fixture` — `world.blockers=[]`,
  `beats.blockers=["motifs"]` ⇒ the states swap. ***This is the test that fails if anyone hard-codes the graph
  from a mock.***
- `test_the_run_body_has_NO_params_key` (the fingerprint-fork / paid-for-nothing pin).
- `test_an_agent_pass_run_invalidation_refetches_the_ledger` — `qc.invalidateQueries(['plan-passes', bookId])`
  (**the BOOK PREFIX**) ⇒ `planForgeApi.passes` called again. **Proves Lane-B can reach this hook.**
- run-switch: rerender with `runId` B while A is in flight ⇒ **A never lands** (W5-S8 test (c)).

`frontend/src/features/studio/panels/__tests__/PassRailPanel.test.tsx` — **one case per row of the state
table**, each asserting its `data-testid` **and its copy**, plus:
- **loading** ⇒ `getAllByTestId('pass-skeleton-row')` has length **7**; `queryByRole('status')` is **null**.
- **no runs** ⇒ clicking the CTA calls a mocked `host.openPanel('planner')`; 🔴 **a mocked `useNavigate` is
  asserted NOT called** (the DOCK-7 regression pin).
- 🔴 **`compiled:false`** ⇒ the copy is present; `queryAllByTestId('pass-row')` length **0**;
  `queryAllByRole('button', { name: /run/i })` length **0**.
- **`compiled:true`** ⇒ **7** real `pass-row`s, no skeletons, no empty-state copy.
- 🔴 **drift pin:** the FE `PASS_ORDER` array **deep-equals** `ledgerFixture.passes.map(p => p.pass_id)` — *a
  backend pass added/renamed REDS the FE.*
- `test_run_is_disabled_while_any_pass_is_running` (no double-charge) + `test_two_rapid_confirm_clicks_fire_exactly_ONE_post`.
- `test_no_button_matches_delete_remove_discard` (PS-1) + `test_no_button_named_hold_exists`
  (`queryByRole('button', {name: /hold/i})` is **null**).

`PassRailPanel.blocked.test.tsx`:
- `cast` pending ⇒ `pass-run-world` is **disabled** and `pass-force-run-world` **IS** in the DOM inside the
  blocked block.
- 🔴 a **runnable** pass (`beats`, blockers `[]`) ⇒ `pass-force-run-beats` is **ABSENT FROM THE DOM ENTIRELY**
  — not merely disabled. *The force door exists only in the blocked state.*
- clicking `pass-force-run-world` **does NOT post** until the confirm is accepted; **after** confirm the body
  is exactly `{force: true, …}`. Clicking `pass-run-*` posts `force: false`.
- the confirm body **renders the pass name AND the blocker name** (guards the copy from decaying into *"Are
  you sure?"*).

`PaidPassConfirm.test.tsx`: names the pass + the model alias · a **free/local** model renders the no-cost line
and a **priced** one renders the **$/1M rate** — 🔴 **assert NO total-$ string is rendered for either** ·
`model_ref` unset ⇒ confirm **disabled** · any pass `status:'running'` ⇒ **every** paid button disabled and a
click fires **no POST**.

`CastCheckpointCard.test.tsx` / `BeatsCheckpointCard.test.tsx`:
- 🔴 dirty editor + click **Approve** ⇒ **EXACTLY ONE** `planForgeApi.checkpoint` call, body
  `{approved:true, pass_id:'cast', edits:{…}}` — **assert the call count is 1** (*pins "no
  save-then-approve"*).
- a **409 `CHECKPOINT_REFUSED`** on that call ⇒ the card **still shows the edits as dirty** and surfaces the
  refusal (**nothing was written**).
- **Save edits** ⇒ `{approved:false, pass_id, edits}` and the card flips to the amber **`rejected`** chip.
- 🔴 the cast form **serialises the FULL list** — remove a character, submit, assert the body's `cast` array
  is the **whole remaining list** (*a partial patch would silently delete the omitted characters*).

**DoD evidence:** `frontend: <N> passed` + **live browser smoke legs (a)(b)(c)(d)(f)** (§10).

**dependsOn:** W5-S0 (X-1 — **the ModelPicker CTA must not tear the dock down**), W5-S1, W5-S6c, W5-S8

---

### W5-S13 · GG-8 — the registration checklist for `plan-passes`, in order

🔴 **A NEW PANEL IS NOT DONE UNTIL ALL OF THIS IS DONE.** Two machine guards red on drift in *either*
direction. **Assert the DELTA + the three-way equality — NEVER a literal (§0.2 C-2).**

| # | File | Edit |
|---|---|---|
| 1 | `frontend/src/features/studio/panels/PassRailPanel.tsx` | *(W5-S12)* Root `data-testid="studio-plan-passes-panel"`. Logic in `features/plan-forge/hooks/usePassRail.ts`. |
| 2 | `frontend/src/features/studio/panels/catalog.ts` | **One row, appended after `plan-hub` (`:190`):** `{ id: 'plan-passes', component: PassRailPanel, titleKey: 'panels.plan-passes.title', descKey: 'panels.plan-passes.desc', category: 'editor', guideBodyKey: 'panels.plan-passes.guideBody' }`. **`category` MANDATORY** (test reds without it) and **must be a member of `CATEGORY_ORDER`** — `'editor'` already is. **`guideBodyKey` MANDATORY** (X-3). **NO `hiddenFromPalette`** (PS-7). |
| 3 | `frontend/src/i18n/locales/en/studio.json` | `panels.plan-passes.{title,desc,guideBody}` + `documents.planArtifact` + `jsonEditor.readOnly` + the Repair-strip + Pass-Rail copy keys. **Title: "Pass Rail".** |
| 4 | `frontend/src/i18n/locales/{ar,bn,de,es,fr,hi,id,ja,ko,ms,pt-BR,ru,th,tr,vi,zh-CN,zh-TW}/studio.json` | Same keys × **17 locales** — **`python scripts/i18n_translate.py`**, **never hand-written.** |
| 5 | `services/chat-service/app/services/frontend_tools.py` | **TWO edits** in `UI_OPEN_STUDIO_PANEL_TOOL`: **(a)** append `"plan-passes"` to the `panel_id` **enum** (`:402`); **(b)** append a clause to the tool **description** prose (`:403-481`) — **that gloss is the model's ONLY hint the panel exists.** Suggested: *"'plan-passes' = the PlanForge Pass Rail — the 7-pass compiler ledger: what is stale, what is blocked, and the cast/beats checkpoints a human must accept."* |
| 6 | `contracts/frontend-tools.contract.json` | **NEVER HAND-EDIT — REGENERATE:** `cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py`, then **commit the regenerated JSON in the SAME COMMIT as steps 2 + 5.** |
| 7 *(cond.)* | `studioLinks.ts` | **SKIP.** Not needed for v1 — the Rail is reached from the palette, the agent, or `planner`'s "Open the Pass Rail →" button (`host.openPanel`, **never a route hop** — DOCK-7). |
| 8 **(MANDATORY — X-4)** | `frontend/src/features/studio/agent/handlers/planEffects.ts` | *(W5-S14)* |
| 9 *(cond.)* | `tours.ts` / `tourCatalog.ts` | **SKIP.** Not a role-tour step in v1. |

**Also add to `PlannerPanel`:** an *"Open the Pass Rail →"* button (`data-testid="planner-open-pass-rail"`,
`openPanel('plan-passes')`) — mirror the existing `planner-open-agent-mode` button at `:102-109`.

⚠ **Step 2 ALSO carries the module-scope `registerPlanArtifactDocumentProvider()` call** (W5-S9 / C-9).

#### 🔴 X-3b — make step 5(b) a TESTED EFFECT, not a discipline (`Q-35-CATALOG-ROW-REQUIRED-FIELDS` (2))

**Step 5(b) — the tool DESCRIPTION prose — is the ONLY step in the entire 9-step checklist that NOTHING
machine-checks.** A builder can add the enum entry, regenerate the contract, and go **100% green while the
model never learns the panel exists** — the silent-discoverability failure the enum was added to kill.
**It is cheaply closable, and it is GREEN AT HEAD** (all 57 current ids already appear in the description).

Add to `services/chat-service/tests/test_frontend_tools.py`:
```python
def test_every_panel_id_is_GLOSSED_in_the_tool_description():
    prop = UI_OPEN_STUDIO_PANEL_TOOL["parameters"]["properties"]["panel_id"]
    for pid in prop["enum"]:
        assert f"'{pid}'" in prop["description"], f"{pid} is in the enum but the model is never told it exists"
```
*(CLAUDE.md: **checklist ⇒ test the effect**. All ~9 panels in this batch then inherit it. **Skip only if
Wave 0 already landed X-3b** — grep first.)*

#### 🔴 THE COUNT GATE — assert the DELTA and the SET DIFF. **NEVER a literal.** (C-2)

⛔ **ADD NO NEW COUNT TEST.** The shipped `panelCatalogContract.test.ts:32-35` asserts **SET EQUALITY**
(`expect([...enumIds].sort()).toEqual(openable)`), which is **strictly STRONGER** than `N == N == N` (it
catches a swap that keeps the count constant). *A count assertion would be a weaker check that must be
hand-bumped every wave — i.e. it would **MANUFACTURE** the drift this question is about.*

The gate is a **2-command shell check the builder RUNS** (it is not a test file):
```bash
# after regenerating the contract (step 6):
N_after=$(jq '.ui_open_studio_panel.args.panel_id.enum | length' contracts/frontend-tools.contract.json)
[ "$N_after" -eq "$((N_before + 1))" ] || { echo "DELTA WRONG: $N_before -> $N_after"; exit 1; }
jq -r '.ui_open_studio_panel.args.panel_id.enum[]' contracts/frontend-tools.contract.json | sort > /tmp/panels-after.txt
diff /tmp/panels-before.txt /tmp/panels-after.txt     # the ONLY added line must be `plan-passes`; ZERO removals
```
🔴 **A REMOVAL here means another wave's panel was CLOBBERED by a hand-edit of the JSON** — step 6's exact
failure mode.

#### 🔴 REBASE RECIPE (`Q-35-CONTRACT-JSON-COLLISION`) — the JSON is **order-sensitive**

`test_frontend_tools_contract.py:130-147` asserts `on_disk == built`, and `_normalize` (`:81`) carries `enum`
through **as a LIST** ⇒ **equality is ORDER-SENSITIVE. A hand-merged enum whose element order differs from the
Python literal's order REDS the test even though the sets are identical.** Regeneration is the **only**
byte-exact path. So, if a rebase/pull brings another wave's panel:
1. Resolve the conflict **ONLY** in `frontend_tools.py:402` (**take the UNION** of both panel ids on that one
   line; order is irrelevant) and in `catalog.ts` (union of the appended rows).
2. For `contracts/frontend-tools.contract.json`: ⛔ **do NOT merge by hand and do NOT reason about the
   hunks.** End the conflict with **either** side (`git checkout --ours -- contracts/frontend-tools.contract.json`),
   then **RE-RUN step 6 and the verify below.** *The generator overwrites the file wholesale, so whichever side
   you took is irrelevant.*

**Verify (all four green — the first two are the drift-locks; `.githooks/pre-commit` runs NEITHER, so a stale
JSON WILL reach HEAD if you skip this):**

```bash
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
cd frontend && npx vitest run \
  src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
  src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
  src/features/studio/palette/__tests__/useStudioCommands.test.ts \
  src/features/chat/nav/__tests__/frontendToolContract.test.ts
```

**Do NOT touch:** `StudioDock.tsx`, `StudioFrame.tsx`, `useStudioCommands.ts`, `UserGuidePanel.tsx` (all
derive from `catalog.ts`); `studioUiNav.ts` / `useStudioUiToolExecutor.ts` (panel-id-agnostic — verified:
`studioUiNav.ts:32-35` passes `panelId` straight through with **zero hardcoded ids**).

**DoD evidence:** the 4 suites green + `py enum == contract enum == openable` + **the delta gate above
(measured `N_before + 1`, set-diff == `["plan-passes"]`)** — ⛔ **never the literal 66.**

**dependsOn:** W5-S12

---

### W5-S14 · X-4 — the Lane-B effect handler (`planEffects.ts`)

🔴 **There is NO `plan_*` effect handler today.** The registered patterns are only book/composition-draft,
outline/scene-link, glossary, knowledge, translation (verified: `handlers/` holds exactly `bookEffects`,
`glossaryEffects`, `knowledgeEffects`, `translationEffects`). **Without this, the agent runs a pass and the
Rail sits stale.**

**Plan 30 §8.0b — ONE FILE PER DOMAIN.** `matchEffectHandlers` returns **EVERY** match and
`runEffectHandlers` **awaits ALL** of them, so two files registering overlapping patterns **double-fire**.
`plan_*` is owned by **spec 35 / this wave**, in **`planEffects.ts`**. **Do not put plan handlers anywhere
else.**

**Files**

| File | Change |
|---|---|
| `frontend/src/features/studio/agent/handlers/planEffects.ts` | **NEW** |
| 🔴 `frontend/src/features/studio/agent/effectRegistry.ts` | **`EffectContext` gains `reloadPlanRun?: (runId?: string) => void` and `reloadPlanRuns?: () => void`** — the **same escape-hatch shape** the shipped `reloadChapter` / `reloadScenes` already have (`:9-23`), which exist **precisely because `invalidateQueries` cannot reach hand-rolled state** |
| `frontend/src/features/studio/agent/useStudioEffectReconciler.ts` | import + call `registerPlanEffectHandlers()` in the existing registration `useEffect` (`:34-39`); **supply `reloadPlanRun` from `usePlanRun.loadRun` and `reloadPlanRuns` from `usePlanRunsList.refresh`** · **DELETE the now-FALSE comment at `:7-10`** claiming certain families "DON'T need a handler" |
| `frontend/src/features/studio/agent/handlers/__tests__/planEffects.test.ts` | **NEW** |

🔴 **TWO BUGS IN THE PLAN'S FIRST DRAFT (C-13) — both would ship a handler that NEVER FIRES:**

1. **`if (!runId) return;` KILLS IT.** `plan_run_pass`'s result is `{job_id, status, pass_id}` + the derived
   pass block (`plan_forge_service.py:1212-1217`) — **it carries NO `run_id`.** And `EffectContext` carries
   **no tool ARGS** (`effectRegistry.ts:9-24`), where `run_id` actually lives. ⇒ **an exact-key handler could
   NEVER fire for the single most important tool in the wave.** **Invalidate by BOOK PREFIX,
   UNCONDITIONALLY** — react-query prefix-matches, and *a wasted refetch is strictly safer than a missed one*
   (a `plan_run_pass` refusal returns `ok:true` + `{success:false, blockers:[…]}`, so even "did it work?" is
   not a usable gate).
2. **`invalidateQueries(['plan-run'…])` / `(['plan-runs'…])` ARE DEAD KEYS** — those hooks are hand-rolled
   (C-13/§4). ⛔ **Do not ship a no-op invalidation.** Use the **reload hatches**.

```ts
// handlers/planEffects.ts
import { registerEffectHandler, type EffectContext } from '../effectRegistry';
import { unwrapToolResult } from './resultEnvelope';

let registered = false;

/** plan_* WRITES only. The three READS (plan_pass_status, plan_validate, plan_self_check) are excluded
 *  so a chatty agent read-loop doesn't thrash the cache — same discipline as KNOWLEDGE_WRITE_PATTERN.
 *  ⚠ A RegExp, not a string: registerEffectHandler's string branch is `tool === p || tool.startsWith(p)`,
 *  so a STRING with alternation matches NOTHING and ships a silent no-op no unit test can catch. */
export const PLAN_WRITE_PATTERN =
  /^plan_(propose_spec|run_pass|review_checkpoint|link|handoff_autofix|apply_revision|interpret_feedback|compile)/;

function runIdFromResult(result: unknown): string | null {
  // ⚠ The live stream nests the domain payload inside the chat-service {ok, result} envelope (and the
  // inner may be a JSON *string*). A bare top-level read returns null, stays GREEN in unit tests that
  // feed the payload unwrapped, and NEVER FIRES LIVE. That is the M-E live gate's bug, exactly.
  const p = unwrapToolResult(result);
  if (!p || typeof p !== 'object') return null;
  const r = p as Record<string, unknown>;
  for (const k of ['run_id', 'plan_run_id', 'id']) if (typeof r[k] === 'string') return r[k] as string;
  return null;
}

export function planEffect(ctx: EffectContext): void {
  const { queryClient, bookId } = ctx;
  // BOOK-PREFIX, UNCONDITIONAL — see bug 1 above. This is the ONLY react-query surface in plan-forge
  // (usePassRail). react-query prefix-matches, so this covers every run under the book.
  queryClient.invalidateQueries({ queryKey: ['plan-passes', bookId] });

  const runId = runIdFromResult(ctx.result);              // opportunistic narrow when the payload has it
  if (runId) queryClient.invalidateQueries({ queryKey: ['plan-passes', bookId, runId] });

  // The two SHIPPED hooks are hand-rolled ⇒ invalidateQueries CANNOT reach them. Use the same escape
  // hatches the seam already has for exactly this (reloadChapter/reloadScenes, effectRegistry.ts:9-23).
  ctx.reloadPlanRun?.(runId ?? undefined);
  ctx.reloadPlanRuns?.();                                  // plan_propose_spec MINTS a run → the picker is stale
}

/** Idempotent. */
export function registerPlanEffectHandlers(): void {
  if (registered) return;
  registered = true;
  registerEffectHandler(PLAN_WRITE_PATTERN, planEffect);
}

/** Test-only: undo the idempotency guard after clearEffectHandlers(). */
export function _resetPlanEffectHandlers(): void { registered = false; }
```

*(The 11 shipped tool names, verified in `server.py`: `plan_propose_spec`, `plan_validate`,
`plan_self_check`, `plan_interpret_feedback`, `plan_apply_revision`, `plan_review_checkpoint`,
`plan_handoff_autofix`, `plan_compile`, `plan_run_pass`, `plan_pass_status`, `plan_link`. The regex
deliberately excludes the three READS — `plan_validate`, `plan_self_check`, `plan_pass_status` — which
mutate nothing.)*

**Tests** — `planEffects.test.ts`. 🔴 **Feed `runEffectHandlers` the LIVE ENVELOPE shape**
`{ok:true, result: JSON.stringify({job_id, status:'running', pass_id:'cast', passes:[…]})}` — **NOT the
unwrapped payload.** *(Feeding it unwrapped is exactly what kept the M-E bug green — `resultEnvelope.ts:1-7`.)*

- 🔴 `test_plan_run_pass_invalidates_the_rail_EVEN_THOUGH_its_result_has_no_run_id` — the **real**
  `plan_run_pass` payload (no `run_id` anywhere) ⇒ `invalidateQueries` **called with `['plan-passes', bookId]`**.
  ***This is the test the plan's first-draft handler FAILS.***
- `test_a_payload_carrying_run_id_also_invalidates_the_exact_key`.
- 🔴 `test_the_hand_rolled_hooks_are_reached_via_the_reload_hatches` — spy `reloadPlanRun` + `reloadPlanRuns`;
  assert **both are called**. *(And assert **no** `invalidateQueries(['plan-run', …])` / `(['plan-runs', …])`
  is issued — **a dead-key invalidation is a shipped no-op**.)*
- `test_the_pattern_matches_the_real_tool_names_and_not_the_reads` — `matchEffectHandlers('plan_run_pass').length === 1`
  **and** `matchEffectHandlers('plan_pass_status').length === 0` (and `plan_validate` / `plan_self_check` = 0).

**DoD evidence:** `frontend: <N> passed` + 🔴 **live browser smoke leg (b)** — *with the Rail open, the agent
calls `plan_run_pass` in chat → the Rail's `cast` row flips to `running` and then to `completed` **WITHOUT a
manual reload**.* **A vitest-green handler proves NOTHING here** (agent→GUI loops need a live browser smoke).

**dependsOn:** W5-S8, W5-S12

---

### W5-S15 · WAVE CLOSE — seed script, live smoke, spec edits, `/review-impl`, SESSION_HANDOFF, commit

Not optional, not a formality. See §10.

#### 🔴 The SPEC EDITS this wave owes (the register requires them — a decision no one can find is a decision lost)

| File · line | Edit | Register entry |
|---|---|---|
| `35_planforge_studio.md:591` (**OQ-1**) | → **`RESOLVED 2026-07-13 — (a) NO Tier-W descriptor, WON'T-FIX (defer gate 5)`**, quoting the `jobs_handler.go:203-218` grounding **so no later agent re-opens it on the false "unguarded spend" premise.** Fix the same false claim in §4.3 / §523 prose. | `Q-35-OQ1-TIER-W-DESCRIPTOR` (4) |
| `35_planforge_studio.md:593` (**OQ-3**) | → **`RESOLVED — built as BE-3c`** (amend PS-11 in place; **do not fork the spec**). | `Q-35-OQ3-PLAN-GET-ARTIFACT-MCP` |
| `35_planforge_studio.md:595` (**OQ-5**) | → name the row: *"Tracked as **`D-PLANFORGE-PROPOSE-BLIND`** (SESSION_HANDOFF.md Deferred, gate #2)."* *A "tracked elsewhere" with **no ID** is how a row becomes an orphan.* | `Q-35-OQ5-EXISTING-STATE` (2) |
| `35_planforge_studio.md` **OQ-2** | 🔴 **Correct the beats shape** — *"edit a beat's **summary**/tension"* is **WRONG**: neither field exists. The form edits `title`/`beat_role`/`intent` on `chapters[]` and `tension_target` on the **parallel** `tension_curve[]`. | `Q-35-OQ2-EDITS-EDITOR-SHAPE` (3) |
| `35_planforge_studio.md` **PS-12** (§2 `:198-200`), §4.4's *Rejected* row (`:347`), M1 DoD #4 (`:551`) and #6(f) (`:581`) | 🔴 **Rewrite: `blocked_at` is fixed AT THE SOURCE.** DoD #4 flips **from pinning the surprise to pinning the fix**: `POST /checkpoint {approved:false, pass_id:"cast", edits}` ⇒ `decision:"rejected"`, **`blocked_at` STILL `"cast"`**, downstream still lists `cast` in `blockers[]`. | `Q-35-PS12-STUCK-BANNER-PREDICATE` (4) |
| `35_planforge_studio.md` §10 DoD item 1 · §7 | 🔴 **Strike every count literal** (58/65). → *"The three-way lockstep holds by **SET** equality (`panelCatalogContract.test.ts` — it asserts sets, not counts), and the enum grew by exactly **+1** whose sole new member is `plan-passes`. **No count literal appears in any test or DoD check.**"* Mark `(:402, currently 57 entries)` as *"at HEAD 9262ed53e — **stale after Wave 1**; APPEND to the enum, never count it."* | `Q-35-PANEL-COUNT-BASELINE` (2) |
| 🔴 `35_planforge_studio.md` §5 **and** `30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:749` | **TWO WRONG CITATIONS** — both cite `features/**planforge**/PlanRunView.tsx:120-128`. The real path is `features/**plan-forge**/` (**hyphen**) and the picker is at **`:111-124`**. *They will send a builder to the wrong file at 3am.* **Fix both.** | `Q-35-D-PLANFORGE-GUI-AUDIT-STALE` (2) |

#### SESSION (DoD item 10) — amend-then-clear, ONE edit, same commit as the code

Edit the **`D-PLANFORGE-GUI-AUDIT`** block at `SESSION_HANDOFF.md:1572`: strike **sub-gap 1** (`:1244-1249`)
**in place** with the amendment *"Sub-gap 1 (`arc_id` text box + silent disable): **STALE** — fixed by
`9c685c28a`, `PlanRunView.tsx:111-124`. Not re-done."* — **then CLEAR the whole row to "Recently cleared"**,
citing §5 R1/R2/R3 as the close for sub-gaps 2/3/4. **Do not carry the row forward.**
**File the §12 rows.** ⛔ **Do NOT duplicate `D-PLANFORGE-PROPOSE-BLIND`** — it already exists at `:102`.

**dependsOn:** all of the above

---

## 8 · Cost gates, settings, tenancy, agent surface

### Cost gates — PS-6. **No new estimate route. No new `/actions/*` descriptor.**

`grep "composition\." services/composition-service/app/routers/actions.py` → the descriptor set is
`publish`, `generate`, `motif_adopt`, `motif_mine`, `conformance_run`, `authoring_run_{create,gate,start,resume,revert_all}`.
**There is no `composition.plan_run_pass`, and no `composition.plan_*` of any kind.**

PlanForge's paid actions (`run_pass`, `refine`, `interpret`, `autofix`, `compile(run_pipeline=true)`,
`create_run` in llm mode) are **Tier-A with `paid=true`** — they execute directly, over their own REST
routes, with an explicit `model_ref`. They are **not** Tier-W propose→confirm actions, and the shipped
`planner` panel already drives four of them that way.

**Plan 30's cost-gate rule's operative clause is the SECOND one:** *"…**never a bespoke per-action estimate
route**"*. Three invented `/actions/<name>/estimate|confirm` paths **404 in production today** (plan 30
§3.3). **This wave invents none.**

**PS-6 — the sanctioned gate for a Tier-A `paid` action is the CALLER'S OWN gate.** For the agent that is
the chat approval card (driven by `paid=true` in `require_meta`). **For the GUI it is an explicit in-panel
confirmation:** a Run button that opens a confirm step naming **the pass**, **the model** (`ModelPicker`,
explicit — **never a silent default**), and **that this spends** — and which **cannot be double-fired while
a job is in flight**.

🔴 **OQ-1 IS A CONSCIOUS WON'T-FIX, NOT AN OPEN GAP — ITS PREMISE IS FALSE (C-12 / `Q-35-OQ1-TIER-W-DESCRIPTOR`).**
The claim *"PlanForge's paid actions spend with NO pre-run guardrail claim"* **is refuted by the code.**
`plan_run_pass` → `PlanForgeService.run_pass` → a `plan_pass` job → the worker's LLM call →
`LLMClient.submit_and_wait` (`llm_client.py:54`) → provider-registry **`POST /v1/jobs`**, whose
**`runGuardrailPreflight` does a fail-CLOSED usage-billing `guardrail.Reserve`** and returns **402
`LLM_QUOTA_EXCEEDED`** (or 503) **BEFORE A SINGLE TOKEN IS SPENT** (`jobs_handler.go:203-218`, `:415`;
surfaced to Python as `LLMQuotaExceeded`, `sdks/python/loreweave_llm/errors.py:32`).
**Every plan pass IS ledger-claimed against the user's spend guardrail.** The only delta vs `motif_mine` is
**WHEN** the refusal lands — in-worker at LLM submit, instead of pre-enqueue at confirm. **That is a
fail-fast/UX difference, not a spend hole**, and it does not justify minting a second confirmation convention
for the same object class (AN-8 seals it; spec 35 §523 already forbids it).

**BUILDER INSTRUCTIONS:**
1. ⛔ **Do NOT touch `services/composition-service/app/routers/actions.py`.** No `_PLAN_RUN_PASS_DESCRIPTOR`,
   no extension of `_ALL_DESCRIPTORS`, no plan-pass confirm effect. `plan_run_pass` stays **Tier-A
   `paid=True`** on its shipped direct channel.
2. **GUI channel = PS-6 exactly** (the `PaidPassConfirm` component, W5-S12). **No `/actions/plan_run_pass/estimate`
   route** — inventing one reproduces the three FE 404s of plan 30 §3.3.
3. 🔴 **Capture the ONE real value OQ-1 was chasing:** **make the guardrail refusal HONEST in the panel**
   (W5-S12 "QUOTA HONESTY").
4. **Edit `docs/specs/2026-07-01-writing-studio/35_planforge_studio.md:591`:** rewrite OQ-1 from an open
   question to **`RESOLVED 2026-07-13 — (a) NO Tier-W descriptor, WON'T-FIX (CLAUDE.md defer gate 5)`**,
   quoting the `jobs_handler.go` grounding **so no later agent re-opens it on the false premise.** Fix the
   same false claim wherever it appears in §4.3 / §523 prose.

**⇒ `D-PLAN-TIERW-DESCRIPTOR` IS DELETED FROM §12** (a defer row whose premise is false is worse than no row).

### Settings (SET-1..8) — **this wave introduces NO new toggle and NO new env flag.**

The two knobs it exposes are **per-call run inputs, not settings**:
- `model_ref` — an explicit `ModelPicker` value; the panel shows **which** model it will spend on.
- `force` — an explicit per-call argument **the code itself insists must never be an env flag**
  ([`plan_pass_service.py:248-250`](../../services/composition-service/app/services/plan_pass_service.py#L248)).
- `max_rounds` on autofix — a per-call bounded input (1–5), not config.

**Adding a `PLAN_FORCE_ENABLED` / `PLAN_AUTOFIX_MODE` env flag would be a `/review-impl` finding.**

### Tenancy — no new tables, no new scope keys.

`plan_run` is **per-book** (`book_id` scope key; `created_by` is a plain actor stamp — stored, never
filtered on). `plan_artifact` carries **no `book_id`** and is scoped **transitively through
`JOIN plan_run r ON r.id = a.run_id`** — **every new read (BE-3) MUST go through that join**, and
`artifacts_by_ids` already does. BE-4's `is_archived` is a column on the existing book-scoped table.

Every route gates with `_gate_book(grant, book_id, user_id, VIEW|EDIT)` **before** the service. **A
cross-book artifact id simply does not come back — the SAME 404 as a missing one (no enumeration
oracle, H13).**

### Agent surface — 🔴 **this wave ADDS ONE MCP TOOL** (C-11).

`plan_run_pass` (A, `paid`, async — **no `force`, by design**), `plan_pass_status` (R),
`plan_review_checkpoint` (A), `plan_link` (A), `plan_handoff_autofix` (A), plus the v1 cluster —
**all unchanged.**

**NEW: `plan_get_artifact` (Tier-R, VIEW) — W5-S2 / BE-3c.** The plan's first draft deferred it
(`D-PLAN-GET-ARTIFACT-TOOL`); **the deferral's stated cost driver was FALSE** (the 3-schema-source FastMCP
shape is **knowledge-service's**, not composition's — composition has **ONE** schema source, the decorator's
signature). Without it, **BE-3 would leave a GG-2 inversion shipped by this very wave**: the human can read an
artifact body and **the agent cannot.** The MCP-first invariant says the domain owns its tools. **It is ~35
lines in a file this wave already opens. `D-PLAN-GET-ARTIFACT-TOOL` is DELETED from §12.**
⛔ **There is still NO `plan_put_artifact`** — the only sanctioned artifact write is the `edits` deep-merge on
`plan_review_checkpoint`, which re-fingerprints.

---

## 9 · Collisions — whose files this wave walks into

**All live tracks share THIS checkout on `feat/context-budget-law`.** This is a shared-checkout multi-agent
situation.

| File this wave edits | Owner / risk | Verdict |
|---|---|---|
| `services/chat-service/app/services/frontend_tools.py` | Track C's D8 had uncommitted, mid-edit chat-service files. | ✅ **CLEAR** — re-verify with `git status --short services/chat-service` (empty at plan time). `frontend_tools.py` was never in that set. |
| `contracts/frontend-tools.contract.json` | **Every wave in plan 30 regenerates this file.** | ⚠ **REGENERATE, NEVER HAND-EDIT** (W5-S13 step 6), and land it in the **same commit** as `catalog.ts` + `frontend_tools.py`. If another wave landed a panel first, **re-run the generator after rebasing** — do not merge the JSON by hand. |
| `frontend/src/features/studio/panels/catalog.ts` | Shared by every wave. | ✅ Append-only; no reordering. Low conflict. |
| `frontend/src/features/studio/documents/types.ts` + `JsonEditorPanel.tsx` | The spec-12 seam. **FE-1 widens it.** | 🟡 **Additive + optional (`readOnly?`)** ⇒ every existing provider is unaffected. But **another wave adding a provider concurrently will conflict in `types.ts`.** Land FE-1 EARLY (W5-S7) and keep the diff to 2 files. |
| `frontend/src/features/studio/agent/useStudioEffectReconciler.ts` | **Every wave adds a handler registration here** (§8.0b lists 6 owners). | ⚠ **Two added import lines + two added call lines.** Rebase-conflict-prone but trivially resolvable — take BOTH sides. |
| `frontend/src/features/plan-forge/**` | Plan 30 §9 lists **the Planner panel** in its 🟢 *"genuinely un-colliding"* row — *"Track C only READS PlanForge tool descriptions."* | ✅ **THE SAFEST LANE IN THE PLAN.** |
| `PlanDrawer.tsx` / `QualityCanonPanel.tsx` | Book-Package track + `d662bd97d`. | ✅ **This wave touches NEITHER.** Recorded so a builder does not wander into them for the artifact viewer — **the viewer is `json-editor`, not PlanDrawer.** |

**Staging rule (memories `never-git-add-A` + `git-commit-pathspec-reads-working-tree-not-index` +
`git-index-may-carry-prestaged`):** enumerate every file. **`git add -A` is FORBIDDEN in a shared
checkout.** `git commit -- <path>` commits the **WORKING TREE**, not the index. **Check `git diff --cached`
before every commit** — the index may already carry another session's pre-staged changes.

---

## 10 · Wave Definition of Done — the literal checklist

- [ ] **1 · composition-service suite green** under `python -m pytest tests -q -n auto --dist loadgroup`.
      **Paste the tail.** ⛔ **Do NOT assert a total count** — the baseline drifts under concurrent waves.
      Assert the **named tests** are present and green.
      ⚠ Any NEW test touching the real DB/port carries `pytestmark = pytest.mark.xdist_group("pg")` **or
      parallel workers interleave and the counts lie.**
- [ ] **2 · chat-service drift-locks green:** `python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q`
- [ ] **3 · frontend suite green:** `npx vitest run`, **plus** the four drift-lock suites named in W5-S13.
- [ ] **4 · The three-way enum equality holds, asserted as a DELTA + a SET DIFF:**
      `py enum == contract enum == openable`, **each == the measured `N_before + 1`**, and the set difference
      is **exactly `["plan-passes"]` with ZERO removals**. ⛔ **NEVER assert a literal (58/65/66)** — §0.2 C-2.
      ⛔ **Add no count test** — the shipped set-equality guard is strictly stronger.
- [ ] **5 · `contracts/frontend-tools.contract.json` REGENERATED, not hand-edited**, and committed in the
      same commit as `catalog.ts` + `frontend_tools.py`.
- [ ] **5b · 🔴 `contracts/api/composition-service/plan-forge.v1.yaml` carries EVERY route this wave's FE
      calls** (W5-S6c) — the 5 new ones **and** the 4 shipped-but-uncontracted ones. **Contract-first is a
      CLAUDE.md law, not a preference.**
- [ ] **6 · 17 locales generated with `python scripts/i18n_translate.py`** — not hand-written.
- [ ] **6b · 🔴 The seed script is COMMITTED and RUNS:**
      `services/composition-service/scripts/seed_planforge_smoke_fixture.py` (`Q-35-LIVE-SMOKE-PREREQS`).
      **It is 2 free routes + 1 local ($0) LLM call — NOT a blocker.** Run from the **host against the
      GATEWAY `http://localhost:3123`** (never the service port — it must traverse the same auth+grant path
      the browser does):
      1. `POST /v1/auth/login` (`claude-test@loreweave.dev` / `Claude@Test2026`) → JWT.
      2. `POST /v1/books {title: f"PF-SMOKE-{label} {ts}"}` → a **NEW book per invocation** (`create_run`
         dedupes on `(book, checksum, mode)` — a fresh book guarantees a fresh run).
      3. `POST /v1/composition/books/{book}/plan/runs {source_markdown: <read of
         tests/fixtures/plan-forge/story-plan-v1.md>, mode: "rules", genre_tags: ["xianxia","cultivation"]}`
         → 201 `proposed`. **NO LLM. $0.**
      4. `POST …/compile {arc_id: <arcs[0].id straight from that 201 body>, run_pipeline: false}` → 200
         `compiled`. **Still NO LLM. $0.** The ledger now reports `compiled: true`.
      5. `POST …/passes/cast/run {model_ref}` — `--model-ref` defaults to
         **`019ebb72-27a2-72f3-a42d-d2d0e0ded179`** (*Gemma-4 26B-A4B QAT* — the verified-active **$0 local
         lm_studio** chat+tool model for this account). Poll `GET …/passes` every 3s (cap 180s) until
         `passes[cast].status == "completed"`, then **ASSERT `blocked_at == "cast"` AND `pass_cursor == 0` AND
         `cast.bootstrap_proposal_id is not null`** — exit non-zero with the raw JSON if not.
      6. **Seed TWO fixtures** (`--count 2`): **`A-headline`** and **`B-reject`** — DoD (c) advances `cast`
         off blocked while DoD (f) needs a **still-blocked** run. Print `{label, book_id, run_id}` as JSON on
         stdout; the Playwright smoke consumes that.
      ⛔ **Do NOT reuse the ad-hoc rows already in the dev DB** — they are residue from a prior manual smoke
      (its proposal row is `status=failed`), and **composition integration tests TRUNCATE the shared dev DB.**
      **DEGRADE RULE:** if lm_studio is genuinely unbootable at VERIFY, proofs **(a)(b)(e)** still run on the
      compiled-but-zero-passes fixture (steps 1–4, **no LLM at all**); **(c)(d)(f) require step 5 — bring
      lm_studio up.** 🔴 **NEVER substitute gpt-4o (paid).** If the local backend truly cannot boot, the VERIFY
      evidence string says `live infra unavailable: lm_studio down` **and the wave does not close.**
- [ ] **7 · 🔴 LIVE BROWSER SMOKE — mandatory. It IS the DoD, not a nice-to-have.**

      This repo's law (`agent-gui-loop-needs-live-browser-smoke-not-raw-stream`): a green unit suite has
      repeatedly hidden *"the FE could not actually execute it."* **Spec 24's own named DoD pillar (H8.2)
      was a live browser smoke, and it was never written — the run-state's "smoke" was curl. DO NOT REPEAT
      THAT HERE.**

      **Setup:** Playwright · real dev stack (**rebuild the images first** — `live-smoke-rebuild-stale-images-first`;
      **:5174 is the BAKED nginx prod build and a host `vite dev` SHADOWS it** — smoke the built image on a
      free port, or `vite dev` on :5199) · the `claude-test@loreweave.dev` account · a **local lm_studio**
      chat model (**$0**) · **the fixtures from 6b**. **Drive the dock via `evaluate` + `data-testid`**
      (refs go stale — `playwright-live-dockview-automation-recipe`).

      **SMOKE ORDER on fixture A:** (a) mount → (b) 7 passes + world disabled / beats enabled → (e) artifact
      read-only + source resume → (d) world's Run → the real 409 + force → **(c) the headline.**
      **On fixture B:** (f).

      **Prove, by EFFECT:**
      - [ ] **(a)** `ui_open_studio_panel {panel_id: "plan-passes"}` from the agent **MOUNTS THE DOCK TAB**
            — not `shown:true` with no tab (the `ui_show_panel` silent-no-op class).
      - [ ] **(b)** The Rail renders the **7 passes with the same `pass_cursor` the API reports** (the F-P3
            regression, observed in the browser), **and the enable/disable state matches the dependency
            table (§3):** on a `cast`-pending run, **`world`'s Run button is DISABLED and `beats`' is
            ENABLED.** *(The inversion spec 35's own first draft shipped in its own mock.)* Then the agent
            runs a pass and **the Rail updates with no manual refresh** (Lane-B, W5-S14).
      - [ ] **(c) 🔴 THE HEADLINE.** On a run `blocked_at: "cast"`, a **human clicks through the seed
            proposal (review → approve → apply) and then Approve**, and **the ledger ADVANCES** —
            `blocked_at` moves off `cast`, `pass_cursor` increments. **This is the capability that does not
            exist today. If this step cannot be driven in a browser, THE WAVE IS NOT DONE**, whatever the
            unit suite says.
      - [ ] **(d)** A 409 `UPSTREAM_STALE` renders its `blockers[]` as **readable copy**, and the **force**
            escape is reachable behind it.
      - [ ] **(e)** `planner`: an artifact row opens `json-editor` **with a real body** (BE-3),
            **read-only** (FE-1 — **no Save button; ⌘S does nothing, visibly and deliberately; the buffer
            never goes dirty**), **two artifact rows open as TWO tabs** (C-10), and a reopened run's
            **source markdown is in the textarea** (BE-3b).
      - [ ] **(f)** 🔴 **Save edits on a blocking checkpoint (F-P10) — THE EXPECTATION IS INVERTED BY C-6.**
            The pass flips to **`rejected`**, and — **because W5-S1 Change 4 fixed `blocked_at` at the
            source** — **`blocked_at` STILL READS `"cast"` ON THE WIRE** (it no longer goes `null`), the Rail
            still says *"stuck at cast"*, and Approve is still offered. ⚠ **The plan's blind draft expected
            `blocked_at: null` here. If you observe `null`, PS-12 did not land — that is the bug, not the
            panel.** **Also assert the AGENT sees it:** `plan_pass_status` on the same run reports
            `blocked_at: "cast"` (GG-1 parity — the whole reason PS-12 fixes the source, not the panel).
      - [ ] **(g)** 🔴 **X-1 (W5-S0), observed:** from the Rail's **empty `ModelPicker`**, click *"Add a
            model"* → **a `settings` dock TAB opens on Providers and THE DOCK LAYOUT SURVIVES.** *(Before
            X-1, this navigates away and destroys the workspace. This leg is the proof the wave did not ship
            a workspace-destroying button on a paid surface.)*
      - [ ] **(h)** 🔴 **GG-2 parity (BE-3c):** an agent turn calls **`plan_get_artifact`** on the same run
            the `json-editor` viewer is showing **and gets the same body.** *The loop is only closed when both
            halves read the same bytes.*
- [ ] **8 · Cross-service evidence.** The cycle touches composition-service **and** chat-service (the
      `panel_id` enum) ⇒ the VERIFY evidence string carries a **`live smoke: <one-liner>`** token
      (CLAUDE.md).
- [ ] **9 · 🔴 `/review-impl` run on the wave's diff, and EVERY bug it finds FIXED before the wave closes.**
      Not deferred. Not "noted". Fixed.
- [ ] **10 · `docs/sessions/SESSION_HANDOFF.md` updated:** `D-PLANFORGE-GUI-AUDIT` **amended** (sub-gap 1
      stale) then **cleared**; every §12 defer row filed.
- [ ] **11 · Committed** — files enumerated, never `git add -A`, `git diff --cached` checked first.

---

## 11 · SEALED adjudications — **an INDEX into the register, not an authority**

> 🔴 **The authority is [`docs/plans/studio-adjudication/wave-5-decisions.md`](studio-adjudication/wave-5-decisions.md).**
> Read the register entry before building the slice. This table is a map, and it records **where the plan's
> blind draft was overruled.**

| # | Question | **SEALED ANSWER (register)** | Plan's blind draft |
|---|---|---|---|
| **OQ-1** | A Tier-W `composition.plan_run_pass` descriptor? | 🔴 **`Q-35-OQ1-TIER-W-DESCRIPTOR` — (a) NO. CONSCIOUS WON'T-FIX (defer gate 5).** Its premise is **FALSE**: plan passes **ARE** ledger-claimed (fail-closed `guardrail.Reserve` → 402, `jobs_handler.go:203-218`). **What IS built: the honest quota refusal in the panel** (W5-S12). | ❌ **OVERRULED (C-12)** — it filed a defer row on a false premise. **Row deleted.** |
| **OQ-2** | A generic JSON-patch editor over an arbitrary artifact? | 🔴 **`Q-35-OQ2-EDITS-EDITOR-SHAPE` — (a) NO. Not in v1, NOT EVER, against this backend.** `_deep_merge` **can never remove a key** ⇒ a generic editor advertises semantics the backend does not implement (`silent-success-is-a-bug`). **Structured forms for `cast` + `beats` only.** **And M4 does NOT wait for M2** — the shapes are in the adapters today. | ⚠ Right answer, **WRONG BEATS SHAPE** ("edit a beat's summary/tension" — **neither field exists**). Fixed in W5-S12. |
| **OQ-3** | No `plan_get_artifact` MCP tool (the GG-2 inversion). | 🔴 **`Q-35-OQ3-PLAN-GET-ARTIFACT-MCP` — BUILD IT THIS WAVE as BE-3c.** | ❌ **OVERRULED (C-11)** — deferred it on a **false** cost driver. **Row deleted.** |
| **OQ-4** | Artifact history/diff view? | **`Q-35-OQ4-ARTIFACT-HISTORY` — NOT in v1** (`D-PLAN-ARTIFACT-HISTORY`) — **but the honesty fix is MANDATORY and is a BUILD item**, not a copy suggestion: `created_at` on every ref + the `Latest per kind` header (W5-S5c). | ⚠ Had the copy, **missed the build.** |
| **OQ-5** | `propose.py` has no `existing_state` input. | **`Q-35-OQ5-EXISTING-STATE` — CONFIRMED PARKED** (`D-PLANFORGE-PROPOSE-BLIND`, **already exists** at SESSION_HANDOFF:102 — **do not duplicate it**). **Three builder items, none an engine change:** (1) ⛔ do **NOT** wire `existing_state` — an attempt to "helpfully" do so is **scope creep against a PO-approved row and must be rejected at `/review-impl`**; (2) amend `35_planforge_studio.md:595` to **name the row's ID** (*"tracked elsewhere" with no ID is how a row becomes an orphan*); (3) 🔴 **ship ONE honesty string in the new-run form: *"Proposed from this braindump only. Existing chapters are not read."*** *(the repo's silent-success law applied to a KNOWN blindness — it costs nothing and does not inflate the wave).* | ⚠ Had (1); **missed (2) and (3).** |
| **OQ-6** | Two humans racing the same checkpoint. | **`Q-35-OQ6-CHECKPOINT-RACE` — PS-8 upheld: NO OCC.** 🔴 **BUT the code has a REAL lost-update (human vs. WORKER, no grant needed), and it is FIX-NOW: `pass_delta()` — write the ONE-KEY jsonb delta, not the whole ledger.** | ❌ **SILENT** — the bug was missed entirely. **New slice W5-S5b.** |
| **PS-12** | The stuck banner. | 🔴 **`Q-35-PS12-STUCK-BANNER-PREDICATE` — fix `blocked_at` AT THE SOURCE. The FE derives NOTHING.** | ❌ **OVERRULED (C-6).** |
| **PS-14** | plan-forge is hand-rolled state. | 🔴 **NARROWED (C-13):** only the **NEW** `usePassRail` is react-query. **The two shipped hooks are NOT refactored** — Lane-B reaches them via the **`reload*` escape hatches the seam already has.** | ❌ **OVERRULED (C-13)** — it proposed refactoring the shipped Planner panel for no gain. |
| **C-1 / C-7** | The autofix route's shape. | **200 `{rounds, run}` on the sync path; 202 (same body) when the worker enqueued.** | ⚠ Half right — *"NEVER a 202"* was wrong. |
| **C-2** | The panel count. | **Strike EVERY literal. Assert the delta + the set diff.** | ⚠ Half right — it replaced one phantom (58) with another (65). |

---

## 12 · Defer register — the starting rows

| ID | Origin | What | **Gate (CLAUDE.md 1–5)** | Target |
|---|---|---|---|---|
| ~~`D-PLAN-GET-ARTIFACT-TOOL`~~ | — | 🔴 **DELETED (C-11).** The deferral's cost driver was **FALSE** (3-schema-source FastMCP is *knowledge-service's* shape). **`plan_get_artifact` is BUILT this wave as BE-3c (W5-S2).** | — | **BUILT** |
| ~~`D-PLAN-TIERW-DESCRIPTOR`~~ | — | 🔴 **DELETED (C-12).** Its premise (*"paid actions spend with no pre-run guardrail claim"*) is **refuted by `jobs_handler.go:203-218`**. **OQ-1 is a CONSCIOUS WON'T-FIX (gate 5)**, recorded in spec 35:591 — **not an open gap.** *A defer row on a false premise is worse than no row.* | **5 (conscious won't-fix)** | **CLOSED** |
| `D-PLAN-ARTIFACT-HISTORY` | W5-S5c / OQ-4 | No **version browser** in v1. Every version **is** durable (`edits` is save-new-never-mutate), so nothing is lost, and adding it later is **purely additive with ZERO rework** (a new `GET …/artifacts?kind=…&history=true` beside BE-3 — no contract break, no migration). ⚠ **The HONESTY half is NOT deferred** — `created_at` + `Latest per kind` + the provenance rows **ship in W5-S5c.** | **1 (out of scope)** | v2 |
| `D-PLAN-EDITS-GENERIC-PATCH` | OQ-2 | v1 exposes structured edit forms for **`cast`** and **`beats`** only; every other pass artifact is **read-only viewer + "re-run this pass"**. | 🔴 **5 (CONSCIOUS WON'T-FIX — refused on CORRECTNESS grounds, not scope):** `_deep_merge` can never remove a key. *If the PO ever wants raw artifact authoring, the correct build is an artifact **REPLACE** route (PUT whole body → save-new-artifact), **not** a patch editor over `_deep_merge`.* | **won't-fix** |
| `D-PLANFORGE-PROPOSE-BLIND` | *(inherited — SESSION_HANDOFF:102)* | `propose_spec` has no `existing_state` input. **The row ALREADY EXISTS — do NOT duplicate it.** Wave 5 changes **ZERO** engine code for it; it only (a) names the ID in spec 35:595 and (b) ships the honesty string. | **2 (large/structural)** | Spec 27's PlanForge-v2 compiler work — **NOT Wave 5** |
| `D-PLANFORGE-GUI-AUDIT` | *(inherited)* | ⚠ **AMEND then CLEAR** (`Q-35-D-PLANFORGE-GUI-AUDIT-STALE`). Sub-gap 1 (the `arc_id` text box) is **STALE — already fixed by `9c685c28a`** (`PlanRunView.tsx:111-124`, `data-testid="plan-arc-picker"`). **Any diff that re-adds an `arc_id` text input is a REGRESSION.** Sub-gaps 2/3/4 **are** this wave's R1/R2/R3. | — | **CLEARED by this wave** |

**Anything the build hits that is not on this list:** write the row, name the gate, **KEEP GOING** (policy
3). Do **not** stop unless it is one of the four CRITICAL classes.

---

## 13 · Risks — and the TELL that each has fired

| # | Risk | **The tell** | Mitigation |
|---|---|---|---|
| **R-1** | 🔴 **X-1 has not landed** and the Pass Rail ships a button that destroys the dock. | The pre-flight grep (§2 step 1) prints a bare `<Link to={REGISTRATION_PATH…}>` with **no** `useOptionalStudioHost` branch. In the browser: **click "Add a model" from the Rail's empty ModelPicker → the entire dockview layout vanishes.** | 🔴 **BUILD IT — it is W5-S0, the FIRST SLICE, ~30 lines, one file.** ⚠ **The plan's first draft said *"STOP the panel slices"* — that was a POLICY BUG.** §0 rule 3 stops the run for exactly four things and *"a component I would have to write"* is **not** one of them; CLAUDE.md's anti-laziness rule says **missing infrastructure is unbuilt work you WRITE.** Just build it, then build the Rail. **Live-smoke leg (g) is the proof.** |
| **R-2** | 🔴 **`planEffects.ts` is a silent no-op.** Registered, unit-tested, and dead. | Unit suite **green**. Live: the agent runs a pass, the Rail **does not move** until you close and reopen the panel. | **THREE causes, all closed (C-13):** (i) `if (!runId) return;` — **`plan_run_pass`'s result has no `run_id`** ⇒ **invalidate by BOOK PREFIX, unconditionally**; (ii) `invalidateQueries(['plan-run'…])` is a **DEAD KEY** (hand-rolled hook) ⇒ use the **`reload*` hatches**; (iii) a **string** pattern instead of a RegExp matches nothing. **Live-smoke leg (b) is the only real proof — a green `planEffects.test.ts` proves NOTHING on its own** (the test registers a fake and calls it). |
| **R-3** | 🔴 **The 409 `blockers[]` never reaches the UI** because `apiJson` throws a bare `Error(message)` and the structured `detail` is lost. | The Rail shows *"Request failed with status 409"* instead of *"`world` needs `cast`"*. The force escape is unreachable because the panel does not know it is in the blocked state. | **`frontend/src/api.ts:158-163` already attaches `.status` + `.body`** — **CONFIRM it, then read `err.body.detail`.** If it turns out unreachable, add a typed `PlanApiError` that **parses the body**. 🔴 **Never regex the message string.** |
| **R-4** | **The Rail's "stuck" banner goes QUIET at the exact moment the user needs it.** | Click "Save edits" on `cast` ⇒ the banner flips to *"nothing blocking"* on a run that cannot advance a single pass. **AND the agent, asked "what is blocking the plan", answers "nothing".** | 🔴 **FIXED AT THE SOURCE (C-6 / PS-12), not in the panel.** `blocked_at` is redefined via `is_accepted` ⇒ a **rejected** pass (blocking **OR advisory**) is correctly reported. **The FE renders `view.blocked_at` verbatim and derives NOTHING** — *a predicate duplicated across BE+FE is this repo's known drift class, and the panel-side fix leaves the AGENT surface lying.* Unit-tested (W5-S1 test 3a/3b/3c) **AND** live-smoked (leg f). |
| **R-13** | 🔴 **BE-21 is "fixed" by adding a `latest_artifact()` call inside `_serialize_run` — creating an N+1 in the LIST loop.** | `GET /runs` fires **one extra query per run** for a value **it already has in hand**. | **C-4:** `list_artifact_refs` is **`DISTINCT ON (kind) … ORDER BY created_at DESC`** = the latest id **per kind** — **the package pointer is already in the list.** Read it from there. **ZERO new queries.** |
| **R-14** | 🔴 **The paid Run button charges the user to recompute an identical artifact.** | The GUI "helpfully" pre-fills the engine defaults into `params`; `{"k_ceiling":3}` hashes **differently** from `{}`; every pass the agent ran reads **STALE**; the user pays to redo them. | **`Q-35-PARAMS-UNSPECIFIED`: the FE sends NO `params` key. Ever.** Test-pinned (W5-S12). ***This is the CRITICAL "paid-action defect" class of §0 rule 3 — it would stop the run.*** |
| **R-15** | 🔴 **The cast/beats edit form silently deletes the rows it did not send.** | Remove one character, submit, and the artifact comes back with **only that character** — or a form that PATCHes just the changed row **wipes the rest**. | `_deep_merge` **replaces a list wholesale** when its items have no `id` (they don't). ⇒ **the forms serialise the ENTIRE edited array.** And **B2's schema must never introduce an `id`** on a cast/beat item — the instant it does, the merge flips to upsert-by-id and **"remove a character" stops working while every unit test stays green.** Pinned by the `_deep_merge` regression tests (W5-S12). |
| **R-5** | **The dependency graph is drawn from `PASS_ORDER` instead of `depends_on`** — the exact error spec 35's own first draft made. | `world`'s Run button is **enabled** on a `cast`-pending run (it 409s), and `beats`' is **disabled** (it would have worked). | §3's table + the unit test `test_the_dependency_graph_is_not_the_pass_order` + **live-smoke leg (b)**, which asserts the button states directly. |
| **R-6** | **BE-21 reds `test_genre_tags_plumbing.py:88`** and the builder "fixes" it by reverting BE-21. | `assert "**derive_view(run)" in src` fails. | **That assertion asserts the PRESENCE of the bug.** Delete it; replace with the behavioural test (W5-S1 test 4). Flagged here so nobody mistakes it for a regression. |
| **R-7** | **The autofix route is written as a 202 ack** (following the spec, not the code) and the FE reads a `job_id` that is not there. | `runAutofix` resolves with `undefined` job id; the Repair strip spins forever. **This is the CRITICAL class — the user PAID for the LLM rounds.** | §0.2 **C-1**. The route returns **200 `{rounds, run}`**. The test `test_autofix_returns_rounds_and_run_not_an_ack` pins it. |
| **R-8** | **The `plan-artifact` provider is defined and never REGISTERED — or registered too LATE.** | `openJsonDocument` rejects with *"no JSON document provider for type loreweave.plan-artifact.v1"*. **Green in unit tests, dead in the browser.** ⚠ **Mount-scoped registration does NOT close this** — the dock **restores a `json-editor` tab from localStorage** with no plan panel mounted. | 🔴 **C-9: register at MODULE SCOPE from `catalog.ts`** (the always-loaded "what CAN be opened" module, imported by `StudioDock.tsx:9`). **ZERO registration calls in the panels.** Test: *the provider is registered by IMPORTING THE CATALOG ALONE* — **render no panel at all.** |
| **R-16** | 🔴 **Opening a second artifact REPLACES the first tab.** | Click `cast_plan`, then `beat_plan` — one tab, retargeted. The user cannot compare two artifacts. | **C-10:** `openPanel('json-editor', …)` is the **SINGLETON** id. Use the shipped **multi-instance** form: ``openPanel(`json-editor:${docType}:${runId}:${artifactId}`, { component: 'json-editor', … })``. Pinned by a test asserting the **bare** `'json-editor'` id is **not** used. |
| **R-9** | **`contracts/frontend-tools.contract.json` is hand-edited** (or merged by hand after a rebase). | The contract test passes locally and reds in CI, or the enum and the contract silently disagree. | **REGENERATE, always:** `WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py`. After any rebase that touched another wave's panel: **re-run the generator.** |
| **R-10** | **The i18n keys are hand-written into 17 locales.** | Drift, mojibake, or a missing key that only shows in production for a Thai user. | `python scripts/i18n_translate.py`. **Never by hand.** |
| **R-11** | **Two waves write two effect-handler files for one domain ⇒ DOUBLE-FIRE.** `matchEffectHandlers` returns EVERY match and `runEffectHandlers` awaits ALL of them. | The Rail refetches twice per agent write; a mutation handler would run twice. | **ONE FILE PER DOMAIN** (plan 30 §8.0b). `plan_*` ⇒ **`planEffects.ts`, owned by this wave.** Do not register a `plan_*` pattern anywhere else. |
| **R-12** | **The migration's `is_archived` default is wrong and `ADD COLUMN IF NOT EXISTS` never revisits it** on an already-migrated dev DB. | Every existing plan run comes back archived (or the column silently keeps an old default). | `DEFAULT FALSE` is correct for every existing row (they are all active) ⇒ **no backfill needed, and the default is right the first time.** Verify with `\d plan_run` on the dev DB after migrating. |

---

## 14 · Slice dependency graph (build order)

```
  🔴 W5-S0  (X-1 AddModelCta — ~30 lines, FULLY UNBLOCKED, START HERE) ───────────────┐
  🔴 W5-S6c (CONTRACT-FIRST — freeze plan-forge.v1.yaml) ──────────────┐             │
                                                                        │             │
  W5-S1  (ledger truth: BE-20/21(35)/22 + PS-12 blocked_at) ─┬──────────┤             │
  W5-S2  (BE-3 artifact read + BE-3c MCP tool) ──────────────┤          │             │
  W5-S3  (BE-3b source_markdown — OPT-IN) ───────────────────┤          │             │
  W5-S4  (BE-2 autofix — 200 sync / 202 worker) ─────────────┤          │             │
  W5-S5  (BE-4/4b archive+restore — 4 repo filters, 2 job carriers) ────┤             │
  W5-S5b (OQ-6 pass_delta — the lost-update) ────────────────┤          │             │
  W5-S5c (self_heal provenance + created_at) ────────────────┤          │             │
  W5-S6  (27-B1/B1b/B2 contracts + jsonschema dep) ──────────┘  (independent)         │
                                                                                       │
  W5-S7 (FE-1 readOnly + the onChange dirty hole) ─────┐                               │
                                                        ├─► W5-S9  (artifact viewer; provider @ catalog.ts)
  W5-S8 (api/types + PlanRevision; usePassRail=RQ ONLY)─┼─► W5-S10 (source resume + Repair strip)
                                                        ├─► W5-S11 (archive/restore UI + locked copy)
                                                        └─► W5-S12 (THE PASS RAIL) ◄───┘  (needs S0)
                                                                        │
                                                        ┌───────────────┴───────────────┐
                                                        ▼                               ▼
                                              W5-S13 (GG-8 registration + X-3b)   W5-S14 (Lane-B planEffects)
                                                        └───────────────┬───────────────┘
                                                                        ▼
                                       W5-S15 (seed script · live smoke · /review-impl · handoff · commit)
```

**Ordering rules that are NOT negotiable:**
- 🔴 **W5-S0 (X-1) FIRST.** The Rail mounts a `ModelPicker` on a **paid** surface; its empty-state CTA
  currently **tears the dock down**. *(`Q-35-MILESTONE-ORDERING`: X-1 → M4 is a **HARD** edge.)*
- 🔴 **W5-S6c (the contract) BEFORE any FE slice consumes those routes.** *Contract-first is a CLAUDE.md law.*
- **W5-S7 (FE-1) before W5-S9 (PS-9)** — the read-only provider cannot exist without `readOnly`. *(FE-1 is
  the ONE slice with **zero** backend dependency: it may start on day 1, in parallel with the BE lane.)*
- **W5-S9 (the read-only viewer) before W5-S12** — it **IS** M4's fallback for every artifact that is not
  `cast`/`beats`.
- 🔴 **W5-S6 does NOT gate W5-S12.** *(`Q-35-MILESTONE-ORDERING`: **M2 ⟂ M4, explicitly severed** — the
  plan-forge JSON schemas have **ZERO runtime consumers**, and the cast/beats shapes are **pinned in
  `plan_pass_adapters.py` today**. The anti-drift guard is B2's test validating **real adapter output**, so
  whichever lands second cannot silently disagree.)*

**S1–S6 are otherwise independent** — build them in any order, or in parallel on disjoint files.
⚠ **S1, S3, S5 and S5c ALL touch `_serialize_run`** — do them **serially**, or expect a merge. *(S1 adds
`_pass_view` + the package id; S3 adds the `include_source` kwarg; S5 adds `is_archived`; S5c rewrites the
`artifacts` block.)*
