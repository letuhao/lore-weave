# 31 · Quality Completion — canon rules, progress, corrections, self-heal

> **Status:** 📐 specced 2026-07-13 · branch `feat/context-budget-law` (studio track) · **not yet built** (PO-4: specs + drafts first, no implementation this phase).
> **Type:** FS. **Size: L** (logic ≈ 9 — 4 panels + a hoist chokepoint + a correction seam + a stats-denominator fix; side_effects = **5** — a DDL column, a new per-user table, 3 new routes, 2 new MCP tools, **and an API contract narrowing** (BE-9c′ closes `operation` to a `Literal` ⇒ a previously-accepted request body now 422s) ⇒ **risk floor L**, and this file supersedes the plan's **M** estimate: see [F-Q2](#f-q2)/[F-Q3](#f-q3)/[F-Q3a](#f-q3a)).
> **Wave:** [`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) **Wave 1 — Quality Completion**.
> **Gaps closed:** `G-CANON-RULE-CRUD` (P0, PARTIAL — a port) · `G-PROGRESS` (PARTIAL) · `G-CORRECTION-FLYWHEEL` (P1) · `G-POLISH-SELFHEAL` (P1, found by the completeness critic).
> **Deferred rows absorbed:** `D-QUALITY-CRITIC-HEAL-LINK` · 00C **Q-3(a)(b)**.
> **New panels:** `quality-canon-rules` · `quality-corrections` · `quality-heal` (category `quality`) · `progress` (category `editor` — see **QC-2**).
> **Design draft:** [`design-drafts/screens/studio/screen-quality-completion.html`](../../../design-drafts/screens/studio/screen-quality-completion.html) — **DRAWN** (1,429 lines; 4 panels + the DOCK-8 hub row + 8 states ①–⑧, per plan-30 §8.3 house style).
> **§9 collisions — checked, this wave is clear.** It touches **`QualityCanonPanel.tsx`** (🟡, last edited `d662bd97d`/D-04): its `focusRuleId` deep-link seam **already exists — extend it, do not rebuild it** (Panel A). It touches **`chat-service/app/services/frontend_tools.py`**, which is **NOT** one of Track C's four mid-edit files (`ToolApprovalCard.tsx`, `useChatMessages.ts`, `tool_permissions.py`, `stream_service.py` — verified clean in `git status`). It does **not** touch `PlanDrawer.tsx` or `plan-hub` (Book-Package track).
> **Depends on Wave 0:** **X-1** (AddModelCta DOCK-7 — `quality-heal` mounts a `ModelPicker`, whose empty state renders `AddModelCta`; without X-1 the Run-Polish empty state **destroys the dock**), **X-2** (`CATEGORY_ORDER` is missing `'quality'`), **X-3** (`guideBodyKey` assertion), **X-4** (Lane-B handlers).
> Follows [`docs/standards/dockable-gui.md`](../../standards/dockable-gui.md) (DOCK-1..11) · [`docs/standards/mcp-tool-io.md`](../../standards/mcp-tool-io.md) (IN-1..8 / OUT-1..6) · [`docs/standards/settings-and-config.md`](../../standards/settings-and-config.md) (SET-1..8).

---

## Why this exists

**Three of the four gaps are PORTS.** The components exist, are tested, and are mounted — on a page
[`16_chapter_editor_retirement.md`](16_chapter_editor_retirement.md) slates for deletion. The fourth
(`G-POLISH-SELFHEAL`) is worse than a gap: **the Studio already ships the consumer of a producer it
does not have.**

### The four, named concretely

1. **The Studio judges you against canon rules and gives you no way to write one.**
   `quality-canon` merges three read lenses ([`QualityCanonPanel.tsx:105-129`](../../../frontend/src/features/studio/panels/QualityCanonPanel.tsx#L105)) and has **zero writes**.
   A complete CRUD component — [`CanonRulesPanel.tsx`](../../../frontend/src/features/composition/components/CanonRulesPanel.tsx) + [`CanonRuleForm.tsx`](../../../frontend/src/features/composition/components/CanonRuleForm.tsx) + [`useCanonRules.ts`](../../../frontend/src/features/composition/hooks/useCanonRules.ts), 6 passing tests — is mounted **only** at [`CompositionPanel.tsx:836`](../../../frontend/src/features/composition/components/CompositionPanel.tsx#L836), inside the legacy page.
   The REST surface is **100% built** and 100% consumed *by that page*.

2. **Progress is a write-only loop waiting to happen.** The Studio's hoist reports a word-count
   snapshot on **every save** ([`ManuscriptUnitProvider.tsx:209,239`](../../../frontend/src/features/studio/manuscript/unit/ManuscriptUnitProvider.tsx#L209) → `useReportProgress` / `useEnsureBaseline`) and **no Studio panel reads it.**
   Today the loop is closed *on the legacy page* ([`ProgressPanel.tsx`](../../../frontend/src/features/composition/components/ProgressPanel.tsx) is mounted at [`CompositionPanel.tsx:847`](../../../frontend/src/features/composition/components/CompositionPanel.tsx#L847)); it becomes genuinely write-only the moment that page dies. **Retiring the page before this ports is data-generation with no reader** — GG-4, exactly.

3. **The correction flywheel is dark for every Studio user.** `generation_correction` — the human-gate
   learning signal that feeds `learning-service` through the outbox — is written **only** from the legacy
   ComposeView / ChapterAssembleView / CandidatesView (`useCorrection` → `POST /jobs/{job_id}/correction`).
   The Studio's Compose is chat/MCP-based and **no MCP tool records a correction**
   (`grep record_correction services/composition-service/app/mcp/server.py` → **0 hits**). The model's
   taste-learning signal structurally accrues **only for users still on the page we are deleting.**

4. **🔴 `QualityCriticPanel` mounts the consumer of a producer it does not have.**
   [`QualityCriticPanel.tsx:80`](../../../frontend/src/features/studio/panels/QualityCriticPanel.tsx#L80) renders
   `<QualityReportSection projectId chapterId token modelRef />` — **without the `proposals` prop.**
   [`QualityReportSection.tsx:39`](../../../frontend/src/features/composition/components/QualityReportSection.tsx#L39)
   defaults it to `[]`, so `_hasProposedFix()` ([`:30`](../../../frontend/src/features/composition/components/QualityReportSection.tsx#L30))
   **can never return true** and the `violation-has-fix` badge ([`:95`](../../../frontend/src/features/composition/components/QualityReportSection.tsx#L95))
   is unreachable dead code in the Studio. `D-QUALITY-CRITIC-HEAL-LINK` shipped its consumer and left its
   producer ([`PolishPanel.tsx`](../../../frontend/src/features/composition/components/PolishPanel.tsx), which
   *does* pass `proposals={p.proposals}` at [`:153`](../../../frontend/src/features/composition/components/PolishPanel.tsx#L153))
   on the legacy page.

### It is a PORT — say it loudly, and name every file

| File | Fate |
|---|---|
| `frontend/src/features/composition/components/CanonRulesPanel.tsx` | **STAYS** (legacy page still mounts it). Reused **as-is** by the new `quality-canon-rules` panel, with 2 additive props (`showArchived`, `onRestore`) — see M1. |
| `frontend/src/features/composition/components/CanonRuleForm.tsx` | **STAYS**, +`kind` field ([F-Q10](#f-q10)). |
| `frontend/src/features/composition/hooks/useCanonRules.ts` | **STAYS**, + `restore` mutation + an `includeArchived` list arg. |
| `frontend/src/features/composition/components/ProgressPanel.tsx` | **STAYS**, but its `settings`/`bookId` props change (QC-6 — the goal moves off `work.settings`). |
| `frontend/src/features/composition/hooks/useProgress.ts` | **STAYS**; `useSetDailyGoal` is **rewritten** (it currently drives `patchWork`'s full-blob settings REPLACE — [F-Q7](#f-q7)). |
| `frontend/src/features/composition/components/PolishPanel.tsx` | **STAYS** (legacy). Reused by `quality-heal` with an `onApply` that goes through a **new hoist chokepoint** ([F-Q6](#f-q6)). |
| `frontend/src/features/composition/hooks/usePolishProposals.ts` | **REWRITTEN in place** — `useState` → the react-query cache, so `quality-critic` (a *different dock panel*) can read the proposals (QC-8). Legacy `PolishPanel` keeps working because the hook's return shape is unchanged. |
| `frontend/src/features/composition/components/QualityPanel.tsx` | **NOT ported.** It is `CorrectionStatsTable` **+ `BookPromiseCoverageSection`**, and the Studio already ships the second half as `quality-coverage`. Mounting it whole would put a **paid LLM action on screen twice** ([F-Q11](#f-q11)). Extract `CorrectionStatsTable` into its own file. |
| `frontend/src/features/composition/components/FlywheelPanel.tsx` | **NOT in scope.** It is knowledge-graph growth (`knowledgeApi.getFlywheel`), not the correction flywheel. The name collides; the thing does not. |
| **NEW** `frontend/src/features/studio/panels/{QualityCanonRulesPanel,ProgressPanel,QualityCorrectionsPanel,QualityHealPanel}.tsx` | thin wrappers, `useQualityWork` gate + the shared `ModelPicker`, exactly the shape of `QualityCriticPanel`/`QualityCoveragePanel`. |

**Nothing here is a rewrite of a working component.** The work is registration, the Work gate, four
backend holes the audit under-called, and one genuinely new seam.

---

## Investigation findings

Everything below was read from source on **2026-07-13** at HEAD `9262ed53e`. Three of these findings
**correct plan-30**, which said this wave needed *"No schema change"* and was **M**. It needs two, and
it is **L**.

### F-Q1 — the dead `proposals` prop is real, and it is a two-panel problem, not a missing prop

Confirmed above. The non-obvious part: on the legacy page `PolishPanel` **owns** the proposals and
**passes them down** to `QualityReportSection` in the same subtree. In the Studio, `quality-critic` and
`quality-heal` are **two sibling dock panels with no common React ancestor other than the app root** —
there is no prop to drill. Passing `proposals` therefore requires a **shared store**, not a prop fix.
(→ **QC-8**.)

### F-Q2 — 🔴 the correction-capture seam has **no `job_id` to attach to**. Plan-30's BE-9 is wrong.

`generation_correction.job_id` is **`UUID NOT NULL REFERENCES generation_job(id)`**
([`migrate.py:368`](../../../services/composition-service/app/db/migrate.py#L368)), and
`GenerationCorrectionsRepo.create` *additionally* verifies the job is in the project before it will
write ([`generation_corrections.py`](../../../services/composition-service/app/db/repositories/generation_corrections.py) —
`SELECT 1 FROM generation_job WHERE id=$1 AND project_id=$2` → `ReferenceViolationError`).

The agent-mode path **has** a generation job — and **throws its id away**:

- `authoring_run_units` ([`migrate.py:1493`](../../../services/composition-service/app/db/migrate.py#L1493))
  has columns `run_id, unit_index, chapter_id, status, pre_revision_id, post_revision_id, cost_usd,
  error_message, critic_verdict, created_at, updated_at`. **There is no `job_id`.**
- `DraftOutcome` ([`authoring_run_service.py:197-202`](../../../services/composition-service/app/services/authoring_run_service.py#L197))
  is `{ok, cost_usd, error}`.
- `EngineDraftingSeam.draft_chapter` **reads** `payload["job_id"]`
  ([`:377`](../../../services/composition-service/app/services/authoring_run_service.py#L377)), uses it to fetch the
  cost, and returns `DraftOutcome(ok=True, cost_usd=cost)`
  ([`:391`](../../../services/composition-service/app/services/authoring_run_service.py#L391), and
  `_poll_job` at [`:408`](../../../services/composition-service/app/services/authoring_run_service.py#L408)) — **discarding the id.**

⇒ At `reject_unit` ([`:919`](../../../services/composition-service/app/services/authoring_run_service.py#L919))
there is **no way to name the generation the human just rejected.** BE-9 as written ("*No schema
change*") cannot be built. It needs `ALTER TABLE authoring_run_units ADD COLUMN job_id UUID` +
`DraftOutcome.job_id` + a driver write. That is a **side effect**, and it is why this spec is **L**.

### F-Q3 — 🔴 `correction_stats` counts jobs that can never be corrected. The panel would render a **wrong number.**

`GenerationCorrectionsRepo.correction_stats` groups by **`j.mode`** over every `generation_job` in the
project, with exactly one exclusion (`NOT input->>'selection_edit'`). But **`mode='auto'` is not "a
draft"** — it is the default for almost every LLM operation composition owns:

| `operation` | site | is it correctable? |
|---|---|---|
| `draft_chapter` / `body.operation` | [`engine.py:1049,1080`](../../../services/composition-service/app/routers/engine.py#L1049) | **yes** |
| `stitch_chapter` | [`engine.py:1278,1306`](../../../services/composition-service/app/routers/engine.py#L1278) | **yes** |
| `self_heal_propose` | [`plan.py:246`](../../../services/composition-service/app/routers/plan.py#L246) | no |
| `quality_report` | [`plan.py:312`](../../../services/composition-service/app/routers/plan.py#L312) | no |
| `promise_coverage` | [`plan.py:417`](../../../services/composition-service/app/routers/plan.py#L417) | no |
| `decompose_preview` | [`plan.py:612`](../../../services/composition-service/app/routers/plan.py#L612) | no |
| `plan_pipeline` | [`plan.py:548`](../../../services/composition-service/app/routers/plan.py#L548), [`plan_forge_service.py:1359`](../../../services/composition-service/app/services/plan_forge_service.py#L1359) | no |
| `plan_forge_propose` / `_refine` / `plan_pass` | [`plan_forge_service.py:236,525,1170`](../../../services/composition-service/app/services/plan_forge_service.py#L236) | no |

Every PlanForge pass, every quality report, every Polish run **inflates the `auto` `generations`
denominator**. `accept_rate = (generations − corrected_jobs) / generations`, so the panel reports an
author who is **delighted with everything** and an edit/regenerate/reject rate near zero — a
reassuring, false number, on the panel whose entire purpose is to be the quality signal.

The repo already contains the same bug, patched narrowly one row at a time — the `selection_edit`
exclusion carries a `/review-impl` comment saying exactly this:
> *"T3.2 selection edits run mode='cowrite' but are NOT part of the draft-correction flywheel … they'd inflate the cowrite `generations` denominator and drag its correction rate down — corrupting the cowrite-vs-auto eval signal."*

It was fixed with **a flag on one operation** instead of **an allowlist of the correctable ones**, and
nine more operations walked through the hole afterwards. **Fix it at the root (BE-9c).** Shipping
`quality-corrections` on top of the current query is shipping a lie with a chart on it.

### F-Q3a — 🔴 there is no such thing as "a cowrite op". The obvious allowlist **re-opens the hole it closes.**

The tempting phrasing — *"allowlist the draft ops **and the cowrite ops**"* — is a trap, and an earlier
draft of BE-9c contained it. `mode` and `operation` are **orthogonal**, and only one of them is closed:

| Site | `operation` | `mode` |
|---|---|---|
| `GenerateBody` — per-scene ([`engine.py:98-99`](../../../services/composition-service/app/routers/engine.py#L98)) | `str = "draft_scene"` (**open**) | `Literal["cowrite","auto"] = "cowrite"` — **client-chosen** |
| `GenerateChapterBody` ([`:141`](../../../services/composition-service/app/routers/engine.py#L141), job at [`:1049,1080`](../../../services/composition-service/app/routers/engine.py#L1049)) | `str = "draft_chapter"` (**open**) | `mode="auto"` — **hardcoded** |
| stitch ([`:1279,1307`](../../../services/composition-service/app/routers/engine.py#L1279)) | `"stitch_chapter"` (literal) | `mode="auto"` — **hardcoded** |
| `SelectionEditBody` ([`:122`](../../../services/composition-service/app/routers/engine.py#L122), job at [`:825,846`](../../../services/composition-service/app/routers/engine.py#L825)) | `Literal["rewrite","expand","describe"]` (**closed**) | `mode="cowrite"` — **hardcoded** |

Two consequences a builder **must** internalise before touching the query:

1. **Cowrite is a MODE over the same draft op, not an op family.** The panel's *Stream* column is
   `draft_scene` **with `mode='cowrite'`** — already in the allowlist. The **only** ops that are
   exclusively cowrite are `rewrite`/`expand`/`describe` — i.e. **`selection_edit`**, the exact jobs the
   existing `/review-impl` exclusion removes. An agent told to *"enumerate the cowrite ops from
   `engine.py`"* greps, finds that `Literal`, adds all three, and **silently reverts the documented fix**
   — corrupting the very Stream column the panel charts. ⇒ the allowlist is **exactly**
   `("draft_scene","draft_chapter","stitch_chapter")`, and `NOT selection_edit` **stays**.
2. **`operation` is an open `str` on both draft bodies.** So the allowlist filters what the *server*
   writes today, but does not *constrain* what a client may write tomorrow. → **BE-9c′** closes it to a
   `Literal`, applying to the draft bodies the same lesson `SelectionEditBody` already learned.

### F-Q4 — `propose_edit` has **no job**, so the plan's second capture leg is not buildable

`PROPOSE_EDIT_TOOL`'s parameters are `{operation, text, rationale}`
([`frontend_tools.py:78-98`](../../../services/chat-service/app/services/frontend_tools.py#L78)) — no
job id, no correlation id. The prose in a Studio Compose turn comes from a **chat-service LLM turn**,
which is **not** a composition `generation_job` row. There is nothing to `POST
/jobs/{job_id}/correction` against.

⇒ **`propose_edit` Apply/Dismiss cannot write a `generation_correction` without first minting a
`generation_job` for a chat turn** — a cross-service design decision, not a wiring task. It is **scoped
out of v1** and recorded as **OQ-1**. Plan-30's BE-9 named it as if it were free; it is not.
*(The agent's other prose path — the Tier-W `composition_generate` confirm — **does** mint a job and is
covered by BE-9's authoring-run leg.)*

### F-Q5 — you can see a broken archived rule and never reach it

`CanonRulesRepo.list_all` filters `NOT is_archived`
([`canon_rules.py`](../../../services/composition-service/app/db/repositories/canon_rules.py)), `archive`
is soft, and **there is no `restore` at any layer** — no repo method, no route, no MCP tool. Every
sibling soft-delete (`outline_node`, `motif`, `structure_node`, `arc_template`) has one.

Meanwhile [`QualityCanonPanel.tsx:174`](../../../frontend/src/features/studio/panels/QualityCanonPanel.tsx#L174)
renders violations of rules it cannot resolve as **“A rule that no longer exists”** — i.e. the Studio
*already* shows the user violations of archived rules. So the user can **see** that an archived rule is
being broken, and has **no surface that lists it and no way to bring it back.**

⇒ BE-11 is **two** things, not one: `restore` **and** an `include_archived` list filter. Shipping a
Delete button — on the row that steers the critic — with no undo is a one-way destructive action.

### F-Q6 — 🔴 `PolishPanel.onApply` is a whole-document replace, and the Studio has no chokepoint for one (and a live data-loss window)

`usePolishProposals` derives `healedText = applySelfHealEdits(sourceText, proposals, acceptedIds)`
([`usePolishProposals.ts:89`](../../../frontend/src/features/composition/hooks/usePolishProposals.ts#L89))
where `sourceText` was fetched **at propose time**. `PolishPanel` hands that whole string to
`onApply` ([`PolishPanel.tsx:137`](../../../frontend/src/features/composition/components/PolishPanel.tsx#L137)).

Two problems, both sharpened by the dock:

1. **No chokepoint.** `ManuscriptUnitApi` exposes exactly one AI write path —
   `applyProposedEdit({operation: 'insert_at_cursor' | 'replace_selection', text, provenance})`
   ([`ManuscriptUnitProvider.tsx:93-104`](../../../frontend/src/features/studio/manuscript/unit/ManuscriptUnitProvider.tsx#L93)).
   Neither operation replaces the document. The hoist's own doc-comment says it exists so *"future
   hoist-level bookkeeping has ONE chokepoint for 'an AI wrote into this chapter' instead of every
   consumer reaching into a raw ref"* — so `quality-heal` must **extend the chokepoint**, not bypass it.
2. **`draftVersion` is captured and never read.** `usePolishProposals` stores it
   ([`:24`](../../../frontend/src/features/composition/hooks/usePolishProposals.ts#L24)) and returns it
   ([`:97`](../../../frontend/src/features/composition/hooks/usePolishProposals.ts#L97)); **no caller
   uses it.** Applying `healedText` therefore overwrites the chapter with a splice of the text **as it
   was when Polish ran** — silently reverting anything typed since. On the legacy page this is masked:
   `PolishPanel` is `key={chapterId}`-remounted and sits inches from the editor
   ([`CompositionPanel.tsx:852-859`](../../../frontend/src/features/composition/components/CompositionPanel.tsx#L852), whose comment
   already warns *"stale Ch-A edits would Apply onto Ch-B (corruption)"*). In the dock it is a
   **persistent tab that survives chapter switches**, next to a live, dirty editor. The window is wide
   open by construction.

⇒ `quality-heal` needs (a) a new hoist verb, (b) a **stale-proposal guard** keyed on
`{chapterId, draftVersion}`, rendered — never a silent no-op, never a silent clobber.

### F-Q7 — the daily goal is a **shared** row and the words are **per-user**. That is the kinds-bug shape.

- `composition_daily_progress` PK is `(user_id, project_id, chapter_id, snapshot_date)`
  ([`migrate.py:475`](../../../services/composition-service/app/db/migrate.py#L475)) — **per-user**, and
  `progress.py`'s docstring says so explicitly (*"PM-16 … the stat is the caller's OWN authoring"*).
- The **daily goal** is read from `work.settings["daily_goal"]`
  ([`progress.py` `_coerce_goal`](../../../services/composition-service/app/routers/progress.py)) and written by
  `useSetDailyGoal` ([`useProgress.ts:71-87`](../../../frontend/src/features/composition/hooks/useProgress.ts#L71))
  through `patchWork`. `composition_work.settings` is a **shared per-book package row** every EDIT
  grantee can write.

⇒ **Alice sets a 2,000-word goal; Bob's progress panel now shows Alice's goal**, and Bob's counter is
measured against it. *"Would two users want different values? yes ⇒ user setting"* — CLAUDE.md's User
Boundaries. This is a **tenancy defect**, not a preference.

It also carries the plan's **BE-18** hazard live: `useSetDailyGoal` hand-merges
`{...currentSettings, daily_goal}` into a `PATCH /works/{pid}` that **REPLACES** the whole blob
(`repositories/works.py:311` — `settings = $n::jsonb`) with **no If-Match**. Two concurrent settings
writes lose one. Moving the goal to a per-user row **deletes this caller entirely** and closes the
window without waiting on BE-18.

### F-Q8 — the per-chapter breakdown does not exist on the wire

`GET /works/{pid}/progress` returns `{today, today_words, book_total, daily_goal, current_streak,
sparkline}`. The `chapter_id` dimension is in the PK and is **collapsed away** by
`DailyProgressRepo.read_aggregate` before the router sees it. The plan called the per-chapter
breakdown "SMALL"; it is a route + repo change (**BE-P1**), and it is **droppable from v1** — say which.

### F-Q9 — X-2 confirmed, and it bites this wave first

[`useStudioCommands.ts:20-22`](../../../frontend/src/features/studio/palette/useStudioCommands.ts#L20)
lists **9** categories; [`catalog.ts:81-91`](../../../frontend/src/features/studio/panels/catalog.ts#L81)
defines **10**. `'quality'` is missing, so `CATEGORY_ORDER.indexOf('quality')` → **−1** and the Quality
group sorts **above `editor`**. This wave adds **three more** rows to that category. **X-2 lands before M1.**

### F-Q10 — `kind` is a canon-rule field no GUI can set

`CanonRuleCreate.kind` / `CanonRulePatch.kind` exist
([`canon.py`](../../../services/composition-service/app/routers/canon.py)) and the column exists
([`migrate.py:254`](../../../services/composition-service/app/db/migrate.py#L254)). The TS type
[`types.ts:345`](../../../frontend/src/features/composition/types.ts#L345) **omits `kind`** (and
`is_archived`), and `CanonRulePayload`
([`CanonRuleForm.tsx:11`](../../../frontend/src/features/composition/components/CanonRuleForm.tsx#L11)) drops it.
The **agent** can set it (`composition_canon_rule_create`); the human cannot. A small **inverse gap**,
fixed in the same edit.

### F-Q11 — porting `QualityPanel` whole would double-mount a paid action

[`QualityPanel.tsx:29-34`](../../../frontend/src/features/composition/components/QualityPanel.tsx#L29)
renders `CorrectionStatsTable` **and** `BookPromiseCoverageSection`. The Studio already ships the second
as `quality-coverage` ([`QualityCoveragePanel.tsx:40`](../../../frontend/src/features/studio/panels/QualityCoveragePanel.tsx#L40)),
an on-demand **LLM** pass. Two panels, one paid button, two places to click it. **Extract, don't mount.**

### F-Q12 — the Lane-B reconciler's comment is now false in both halves

[`useStudioEffectReconciler.ts:8-9`](../../../frontend/src/features/studio/agent/useStudioEffectReconciler.ts#L8):
> *"…and the two tool families it confirmed DON'T need a handler (… authoring_run has no MCP tools at all, REST-only, no Studio consumer to go stale)."*

`composition_authoring_run_start` **is** an MCP tool, and `agent-mode` **is** a Studio consumer. X-4
deletes the comment; **this wave adds the first handler that proves it wrong** (a `composition_record_correction`
effect must invalidate `['composition','correction-stats',projectId]`).

### F-Q13 — `dismiss-violation` is a third legacy-only capability hiding in this domain

`POST /jobs/{job_id}/dismiss-violation` ([`engine.py:1684`](../../../services/composition-service/app/routers/engine.py#L1684))
+ `compositionApi.dismissViolation` exist; the only caller is legacy `CriticPanel`/`ComposeView`
(`useCritique`). `quality-canon`'s `RuleRow` — which renders exactly these violations, and already has
`r.job_id` and `r.rule_id` in hand ([`QualityCanonPanel.tsx:108`](../../../frontend/src/features/studio/panels/QualityCanonPanel.tsx#L108)) —
has **no dismiss button**. Zero backend. Folded into M1 as an additive affordance (**QC-9**).

---

## Locked decisions

| # | Decision | Why |
|---|---|---|
| **QC-1** | **This is a PORT.** No component is rewritten from scratch; `usePolishProposals` is the single exception, and only its *storage* changes (its return shape is preserved so the legacy panel keeps working until Wave 6 retires it). | GG-3: legacy-only ≠ unbuilt. |
| **QC-2** | **`progress` gets category `editor`, and is NOT a `quality` hub card.** Wave 1's shorthand called all four "DOCK-8 siblings under the quality hub"; plan-30 §5.2's own gap row does not, and it is right: a word-count streak is not a quality judgment. It sits with `editor` / `chapter-browser` / `scene-browser`, pairing with the existing `WordCountStatusItem` status-bar contribution ([`StudioStatusContributions.tsx:19`](../../../frontend/src/features/studio/statusbar/StudioStatusContributions.tsx#L19)). It **still uses `useQualityWork`** as its Work gate — one gate, one name. | The hub is a launcher for **one domain's** capability set. Three cards go on it (`quality-canon-rules`, `quality-corrections`, `quality-heal`) → the hub grows 4 → 7. |
| **QC-3** | **`quality-corrections` mounts an extracted `CorrectionStatsTable`, never `QualityPanel`.** | [F-Q11](#f-q11). |
| **QC-4** | **`quality-heal` applies through a NEW hoist verb `applyHealedDocument({text, chapterId, expectedDraftVersion})`** on `ManuscriptUnitApi` — not a raw `editorRef`, not `setBody`. It returns a discriminated result (`applied` / `no-editor` / `stale`), never a bare `false`. | [F-Q6](#f-q6); the hoist's own comment demands ONE chokepoint for "an AI wrote into this chapter". |
| **QC-5** | **Self-heal accept/reject is NOT recorded as a `generation_correction` in v1.** It *is* a human-gate signal, and it *does* have a `job_id` (self-heal 202s a `generation_job`) — but that job's `mode='auto'` and `operation='self_heal_propose'`, so a correction on it would land **outside** the draft flywheel's allowlist (BE-9c) and mean nothing, or **inside** it and corrupt the very denominator we are fixing. Correcting *a fix* is a different signal from correcting *a draft*. → **OQ-2**. | [F-Q3](#f-q3). |
| **QC-6** | **`daily_goal` moves to a per-user row** (`composition_progress_goal`), read-through-with-fallback to `work.settings.daily_goal` so no existing user loses a goal. The **writer** only ever writes the new table — the legacy window is closed in the writer, not by rewriting base schema. | [F-Q7](#f-q7) — a shared user-editable row is a tenancy defect; and it deletes the panel's `patchWork` full-blob caller. |
| **QC-7** | **No bespoke per-action estimate route.** `quality-heal` ports the **existing** `POST /works/{pid}/self-heal/propose` verbatim. It is a *paid* action with **no cost estimate today** — that is a pre-existing gap, and the fix is a `composition.self_heal_propose` descriptor on the **generic** `/actions/preview` + `/actions/confirm` spine, **not** a new `/self-heal/estimate`. → **OQ-3 / BE-Q4 (v2)**. | plan-30 §3.3: three invented per-action routes already 404 in production. Do not add a fourth. |
| **QC-8** | **`usePolishProposals` stores proposals in the react-query cache under `['composition','self-heal', projectId, chapterId]`** (`staleTime: Infinity`, no `queryFn` — the paid run is a `useMutation` that `setQueryData`s). `quality-critic` reads the same key with `useQuery({enabled:false})` and passes it as `proposals`. Cache **miss ⇒ `[]` ⇒ no badge** — a false badge is impossible. | [F-Q1](#f-q1): two sibling dock panels have no prop path. This is the smallest shared store that already exists in the app. |
| **QC-9** | **`quality-canon`'s `RuleRow` gains a Dismiss button** (zero backend — the row already carries `job_id` + `rule_id`). | [F-Q13](#f-q13). |
| **QC-10** | **The chapter a quality panel operates on is chosen by the panel's own picker, defaulting to the manuscript hoist's active chapter** — the shape `quality-critic` already uses ([`QualityCriticPanel.tsx:33-59`](../../../frontend/src/features/studio/panels/QualityCriticPanel.tsx#L33)). `quality-heal` copies it verbatim, including the `chaptersTruncated` no-silent-cap notice. | One convention, not two. AN-8: *"a reviewer finding a new confirmation convention here has found a defect."* |

---

## The design

### Panel A · `quality-canon-rules` (category `quality`, hub card 5)

The write half of `quality-canon`. **The pair is the point:** `quality-canon` says *what is broken*,
`quality-canon-rules` says *what the rules are*, and each deep-links into the other by rule id.

```
┌ CANON RULES ─────────────────────────────────────── ⟳  ⧉  ✕ ┐
│ [ + Add rule ]                        [ ] Show archived (3)  │  ← toolbar
├──────────────────────────────────────────────────────────────┤
│ ▸ WORLD    "Cultivation ranks never skip a tier."        ✎ ✕ │
│ ▸ ENTITY   @Lâm Phong  "…has one arm after ch. 41."      ✎ ✕ │
│   [41–…]                                        ⚠ 2 broken → │  ← violation count, click → quality-canon(focusRuleId)
│ ▸ REVEAL   "The Sect Master's identity is hidden."       ✎ ✕ │
│   [1–88]                              (inactive)             │
│ ─ archived ──────────────────────────────────────────────── │
│ ▸ WORLD    "Spirit stones are fungible."          ↺ restore  │  ← only when Show archived
└─ 4 rules · 3 active ────────────────────────── If-Match OCC ─┘
```

**Reads.** `GET /works/{pid}/canon-rules?include_archived=<bool>` (BE-11b) via
`useCanonRules(projectId, token, {includeArchived})`. The **⚠ N broken** badge joins against
`compositionApi.getRuleViolations(projectId)` — the same read `useQualityCanon` already makes — keyed by
`rule_id`. One extra query, no new route.

**Writes.**

| Action | Transport | OCC | 412 behavior |
|---|---|---|---|
| Create | `POST /works/{pid}/canon-rules` | — | — |
| Edit (in place) | `PATCH /canon-rules/{id}` + `If-Match: <version>` | **yes** | render the row's `current` (the 412 body carries `{code:"CANON_VERSION_CONFLICT", current}`), banner *"This rule changed elsewhere — showing the current version. Re-apply your edit?"*, keep the user's draft in the form. **Never** a silent overwrite, **never** a bare toast (today's `onError` → `toast.error` at [`CanonRulesPanel.tsx:20`](../../../frontend/src/features/composition/components/CanonRulesPanel.tsx#L20) is the thing being fixed). |
| Archive | `DELETE /canon-rules/{id}` | — | Confirm dialog + an **Undo** toast wired to the new restore route. A destructive action on the row that steers the critic gets an undo path or it is not shipped. |
| Restore | `POST /canon-rules/{id}/restore` **(BE-11a — MUST-BUILD)** | — | — |

⚠ **The `active` toggle and the `scope` select are chips over an OCC entity.** The memory
`instant-commit-control-over-occ-entity-needs-write-serialization` applies exactly: two rapid toggles
self-412 and the second is dropped. **Writes chain** (`mutateAsync` serialized per rule id), and the
control is disabled while its own write is in flight.

**States.** loading (`Skeleton`) · `useQualityWork` gate (`loading` / `unavailable` / `no-work` —
reuse `QualityWorkGate`, `testIdPrefix="quality-canon-rules"`) · empty (*"No canon rules yet. A canon
rule is an invariant the critic enforces on every generation."* + the Add form) · error · **412
conflict** (above) · **archived** (dimmed, `↺ restore`, only under the toggle) · roster loading (the
entity picker's `useGlossaryRoster`) · **no roster** (glossary empty ⇒ `scope=entity` is disabled with
a reason, not silently broken).

**Deep-links, both directions.**
- **IN** — `quality-canon`'s `RuleRow` gains **“Edit rule”** → `host.openPanel('quality-canon-rules', {params: {focusRuleId}})`. This *completes* the chain `plan-hub → quality-canon → quality-canon-rules` whose first hop already ships (`PlanHubPanel.tsx:74` passes `focusRuleId` — `d662bd97d`). **Do not rebuild that seam; extend it.**
- **OUT** — a rule's **⚠ N broken** badge → `host.openPanel('quality-canon', {params: {focusRuleId}})` — the panel and param that already exist ([`useQualityCanon.ts:27`](../../../frontend/src/features/studio/panels/useQualityCanon.ts#L27) `CanonFocusParams`).
- The **focus banner** copies `QualityCanonPanel`'s honesty rule: a focused rule that resolves to nothing says *"anchored here, nothing has broken it"*, and a focused id that resolves to **no rule at all** says *"that rule was archived — [show archived]"*. It never renders an empty list that reads as success.

**No cost gate** — canon-rule CRUD is free.

---

### Panel B · `progress` (category `editor`, **not** a hub card — QC-2)

A verbatim mount of the existing `ProgressPanel` with its goal-write rewired.

```
┌ PROGRESS ────────────────────────────────────────── ⟳  ⧉  ✕ ┐
│  TODAY        STREAK        BOOK TOTAL                        │
│  1,847        🔥 12         214,309                           │
│  of 2,000 (92%)  12 days                                      │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░  daily goal  1,847 / 2,000              │
│  ┌ last 7 days ─────────────────── [7d] [30d] ┐               │
│  │  ▁▄█▃▅█▂ ┄┄┄┄┄┄┄ goal line                 │               │
│  └───────────────────────────────────────────┘               │
│  ▸ by chapter (today)          Ch 88 · 1,204                  │  ← BE-P1; DROPPABLE (see M2)
│                                Ch 89 ·   643                  │
│  [ 2000 ] [Set goal]   your goal · not shared with collaborators │  ← SET-1: effective value + source tier
└──────────────────────────────────────────────────────────────┘
```

**Reads.** `GET /works/{pid}/progress?today=<local YYYY-MM-DD>` — unchanged, plus `by_chapter[]`
(BE-P1) and a `daily_goal_source: "user" | "work_legacy" | "none"` discriminator (**SET-1**: no silent
hidden default — the panel *shows* where the number came from).
**Writes.** `PUT /works/{pid}/progress/goal {goal}` (**BE-P2 — MUST-BUILD**), per-user. The
`patchWork` path is **deleted** from `useSetDailyGoal`.

**States.** loading · error · Work gate · **no goal set** (the bar and the `ReferenceLine` are simply
absent — already handled at [`ProgressPanel.tsx:65,104`](../../../frontend/src/features/composition/components/ProgressPanel.tsx#L65)) ·
**cold start** (0 words ever ⇒ *"Save a chapter and your first day lands here"* — not an error) ·
**legacy goal** (`source: "work_legacy"` ⇒ a one-line note: *"This goal came from the book's shared
settings. Setting it now makes it yours."*).

**The write-only loop closes here.** `ManuscriptUnitProvider` already reports on every save; this panel
is its first reader in the Studio. **GG-4: `ChapterEditorPage` may not be retired until this ships.**

---

### Panel C · `quality-corrections` (category `quality`, hub card 6)

The eval-gate dashboard: *are the K-option reranker and the co-writer earning their latency?*

```
┌ CORRECTIONS ─────────────────────────────────────── ⟳  ⧉  ✕ ┐
│ Your corrections are the quality signal. Lower edit/regenerate│
│ /reject (and higher accept-as-is) in Diverge means the K-option│
│ reranker is earning its time.                                 │
│                          Diverge (K)      Stream               │
│  Generations                    41            18               │
│  Accept as-is ↑                71%           56%               │
│  Edited       ↓                17%           28%               │
│  Picked other ↓                 7%            —                │
│  Regenerated  ↓                 5%           11%               │
│  Rejected     ↓                 0%            6%               │
│  Avg edit (blocks) ↓           1.4           2.1               │
│  ─────────────────────────────────────────────────────────────│
│  Counts DRAFT generations only — plan passes, quality reports  │  ← BE-9c, stated in the UI
│  and Polish runs are not corrections.                          │
└─ 59 draft generations · 21 corrected ─────────────────────────┘
```

**Reads.** `GET /works/{pid}/correction-stats` — **EXISTS**, but its numbers are wrong until **BE-9c**
lands ([F-Q3](#f-q3)). **Ship the fix and the panel in the same milestone.** Optionally
`GET /works/{pid}/jobs/{job_id}/corrections` (BE-9d) for a per-row drill-down —
`GenerationCorrectionsRepo.list_for_job()` exists and is used **only by tests**.

**Writes.** None on this panel. **The load-bearing half of `G-CORRECTION-FLYWHEEL` is not this panel —
it is the capture seam**, and it lives in `agent-mode`:

- `POST /v1/composition/authoring-runs/{run_id}/units/{i}/reject` already **restores the pre-run
  revision** — a textbook `kind='reject'` correction **being thrown away** every time.
- `…/accept` after the human edited the drafted chapter is a textbook `kind='edit'`.

**The seam (BE-9a/b).** `reject_unit` and `accept_unit` resolve the unit's `job_id` (new column) and
call `GenerationCorrectionsRepo.create(project_id, job_id, created_by=caller, kind=…)`. The write is
**best-effort telemetry and must never block the review** — the legacy FE's own rule
([`CandidatesView.tsx:9`](../../../frontend/src/features/composition/components/CandidatesView.tsx#L9): *"Correction
capture is fire-and-forget telemetry — it must never block"*). A unit with `job_id IS NULL`
(pre-migration rows) records **nothing** and says so in the run report — never a fabricated job id.

**H2 is inherited, not re-derived:** *accepting a draft as-is is **NOT** a correction.* Only
accept-**after-edit** is (`kind='edit'`, with `changed_blocks` computed by the existing
`count_changed_blocks`). The `accept` kind does not exist and must not be invented — the CHECK
constraint is closed on `('edit','pick_different','regenerate','reject')`.

**States.** loading · error · Work gate · **cold start** (`totalGens === 0` ⇒ the existing
`composition-quality-coldstart` copy) · **one-mode-only** (a Work that never used Diverge shows `—`, not
`0%`).

---

### Panel D · `quality-heal` (category `quality`, hub card 7)

The M6 Polish review gate: *apply the AI's fix to my prose — a subset I chose, never silently.*

```
┌ SELF-HEAL ───────────────────────────────────────── ⟳  ⧉  ✕ ┐
│ [Chapter 88 ▾] [Qwen3 35B ▾]  [ Run Polish ]  ☐ auto-tick (AI,│
│                                                  costs more)  │
│ 6 edits · 2 dropped by verify                                 │
│ [all] [all deterministic] [clear]                             │
│ ☑ auto  pronoun    ~~hắn~~ → y            he/him vs. y (VI)   │
│ ☑ auto  typo       ~~Lâm Phog~~ → Lâm Phong                   │
│ ☐ semantic canon   ~~raised his left arm~~ → reached out      │
│                    Lâm Phong lost his left arm in ch. 41      │
│              [ Apply 2 selected ]                             │
│ ── Quality report ─────────────────── [Re-analyze] ──────────│
│ coherence 4/5 · voice 5/5 · pacing 3/5 · canon 2/5            │
│ ⚠ Lâm Phong's left arm — "raised his left arm"  [fix proposed ↓]│  ← the badge that could never fire
└──────────────────────────────────────────────────────────────┘
```

**Reads / paid run.** `POST /works/{pid}/self-heal/propose {chapter_id, model_source, model_ref,
prefilter, rerank}` — **EXISTS**, 202+poll. `ModelPicker(capability="chat")`, exactly as
`quality-critic`/`quality-coverage`. **⚠ Depends on Wave-0 X-1**: the picker's empty state renders
`AddModelCta`, which today is a raw `<Link to="/settings/providers">` and **tears down the whole dock**
(DOCK-7).

**The write — and the guard that makes it safe.**

`onApply(healedText)` → `unit.applyHealedDocument({ text, chapterId, expectedDraftVersion })` (**QC-4**).

| Precondition | Result | UI |
|---|---|---|
| `unit.state.chapterId !== proposalChapterId` | `{kind:'stale', reason:'chapter'}` | *"These fixes were proposed for **Chapter 88**; the editor is on **Chapter 89**. Open Chapter 88, or re-run Polish."* Apply is **disabled**, not silently wrong. |
| `unit.state.version !== proposalDraftVersion` | `{kind:'stale', reason:'version'}` | *"The chapter changed since Polish ran — these fixes are against an older draft and would revert your edits. **[Re-run Polish]**"* |
| `unit.isDirty` | `{kind:'stale', reason:'dirty'}` | Same class: unsaved edits are, by definition, not in `sourceText`. |
| no live editor (Rich/Raw panel closed) | `{kind:'no-editor'}` | *"Open the editor to apply."* |
| ok | `{kind:'applied'}` | The document is replaced through the hoist with `provenance` = AI, the doc becomes dirty, the user saves (⌘S) — **the heal never persists behind the author's back.** |

This is the whole point of the panel. `usePolishProposals` has carried `draftVersion` since it was
written and **nothing has ever read it** ([F-Q6](#f-q6)); in the dock, not reading it is a data-loss bug.

**The critic link (`D-QUALITY-CRITIC-HEAL-LINK`).** The paid Polish run `setQueryData`s
`['composition','self-heal', projectId, chapterId]`; `quality-critic` reads that key (QC-8) and passes it
as `proposals` to `QualityReportSection`. `_hasProposedFix()` finally fires. **A test asserts the badge
renders in `quality-critic` after `quality-heal` runs** — a checklist item is done only when a test
asserts its *effect*.

**States.** Work gate · no model picked (`Run Polish` disabled + *"Pick a model first"*) · running ·
**clean** (*"No issues found — the prose is clean."*) · error · **stale** (×3, above) · no-editor ·
**re-run** (`Re-run Polish` label once `ran`).

---

## Backend prerequisites

**This section is a contract.** A later agent builds from it. Every row was verified against code.

| # | Route / change | METHOD + path | Request | Response | Errors | Size | Status |
|---|---|---|---|---|---|---|---|
| **BE-11a** | canon-rule **restore** | `POST /v1/composition/canon-rules/{rule_id}/restore` | — | the `CanonRule` row | `404` missing/not-in-scope/not-archived · `403` under-tier | **XS** | **MUST-BUILD** — `CanonRulesRepo.restore(project_id, rule_id)` mirroring `archive` (`SET is_archived=false … WHERE is_archived`); gate via `_rule_project_id` → `_require_work(EDIT)`, exactly as `delete_canon_rule`. |
| **BE-11b** | list archived rules | `GET /v1/composition/works/{pid}/canon-rules?include_archived=true` (also keep `active_only`) | — | `{rules: CanonRule[]}` (each now carrying `is_archived`) | `404`/`403` as today | **XS** | **MUST-BUILD** — `CanonRulesRepo.list_all(project_id, include_archived: bool = False)`; drop the `NOT is_archived` predicate when set. Without it, [F-Q5](#f-q5): a violated archived rule is visible and unreachable. |
| **BE-11c** | `composition_canon_rule_restore` MCP tool | MCP (Tier A) | `{project_id, rule_id}` | the row + `_meta.undo_hint = {tool:'composition_canon_rule_delete', args:{…}}` | uniform `not_accessible` | **XS** | **MUST-BUILD** — MCP-first parity: the human gains restore, so the agent must. Also **add the `undo_hint` to `composition_canon_rule_delete`**, which today honestly reports none *because no un-archive existed* ([`mcp/server.py`](../../../services/composition-service/app/mcp/server.py) — *"No undo hint (no un-archive repo method)"*). ⚠ **3-schema-source FastMCP caveat.** |
| **BE-9a** | 🔴 **thread the generation job to the unit** | DDL + service | — | — | — | **S** | **MUST-BUILD.** `ALTER TABLE authoring_run_units ADD COLUMN IF NOT EXISTS job_id UUID;` (nullable — historical units have none, and **never backfill a guess**). `DraftOutcome` gains `job_id: UUID \| None`; `EngineDraftingSeam.draft_chapter` + `_poll_job` **return** the id they already read (`authoring_run_service.py:377/391/408`); `AuthoringRunUnitsRepo.mark_drafted` persists it. **Plan-30 BE-9's "No schema change" is wrong** — [F-Q2](#f-q2). |
| **BE-9b** | correction capture at the review seam | MCP `composition_record_correction` (Tier A) **+ a write inside `accept_unit`/`reject_unit`** | tool: `{project_id, job_id, kind, guidance?, edited_text?, chosen_candidate_index?}` | `{correction_id}` | `404` job not in project · `422` `kind='edit'` with identical text (mirror `engine.py:1756`) | **M** | **MUST-BUILD.** The table, repo, outbox event (`GENERATION_CORRECTED`) and learning-service consumer are **all live**. `reject_unit` → `kind='reject'`; `accept_unit` **after an edit** → `kind='edit'` (H2: accept-as-is records **nothing**). Fire-and-forget: a capture failure logs and **never** fails the accept/reject. `job_id IS NULL` ⇒ skip + report, never fabricate. |
| **BE-9c** | 🔴 **correction-stats denominator: operation allowlist** | `GenerationCorrectionsRepo.correction_stats` | — | same shape | — | **S** | **MUST-BUILD.** **ADD** `AND j.operation = ANY($2)` and **KEEP** the existing `AND NOT coalesce((j.input->>'selection_edit')::boolean, false)` — do **not** replace it ([F-Q3a](#f-q3a): `operation` is an open `str`, so the allowlist is a filter, not a guarantee; the two predicates are defense in depth). The allowlist is **exactly three ops**, as ONE named constant `CORRECTABLE_OPERATIONS = ("draft_scene", "draft_chapter", "stitch_chapter")` — never a literal at the call site. ⚠ **`draft_scene` covers BOTH columns**: `mode` is a *per-request* `Literal["cowrite","auto"]` on the same op, so `draft_scene`+`cowrite` **is** the Stream column. Ship it **with** the panel: without it `quality-corrections` renders a false number. Add a repo test that a `plan_pass` job does **not** move `accept_rate`, **and** one that a `rewrite` selection-edit job still does not. |
| **BE-9c′** | close `operation` to a `Literal` | `GenerateBody.operation` / `GenerateChapterBody.operation` (`engine.py:98,141`) | — | — | `422` on an unregistered op | **XS** | **MUST-BUILD (with BE-9c).** Both are `operation: str = "draft_…"` — a **client-settable free string**, while every sibling field (`mode`, `reasoning`, `assembly_mode`, and `SelectionEditBody.operation`) is a `Literal`. The in-code comment at [`engine.py:118-121`](../../../services/composition-service/app/routers/engine.py#L118) already cites *"the LOOM-39 missing-enum lesson"* for exactly this — it was applied to the selection-edit body and **not** to the two draft bodies. Until it is closed, a client can post `operation:"anything"` on a draft route and silently drop its own generation out of the denominator BE-9c exists to make honest. |
| **BE-9d** | per-job corrections list *(optional)* | `GET /v1/composition/works/{pid}/jobs/{job_id}/corrections` | — | `{items: GenerationCorrection[]}` | `404`/`403` | **XS** | **OPTIONAL** — `list_for_job()` exists and is test-only. Only if the drill-down ships in M4. ⚠ **Before adding it, check the route that already exists:** plan-30's `G-CORRECTION-FLYWHEEL` row names a **learning-service `GET /v1/learning/corrections`** per-row LIST (*"a per-row LIST the original claim missed"*). If that route already serves the drill-down, **do not mint a second one** — two lists over the same rows is the "one name for one concept" violation. Verify at PLAN. |
| **BE-P1** | per-chapter progress breakdown | `GET /v1/composition/works/{pid}/progress` (widen) | — | `+ by_chapter: [{chapter_id, words}]` for the anchor date | as today | **S** | **MUST-BUILD *or* DROP** — `read_aggregate` collapses the chapter dimension before the router sees it ([F-Q8](#f-q8)). **Decide in PLAN.** The panel ships without it; the row is marked droppable. |
| **BE-P2** | 🔴 **per-user daily goal** | `PUT /v1/composition/works/{pid}/progress/goal` | `{goal: int}` (`0` clears) | `{goal, source}` | `422` `goal < 0` · `404`/`403` | **S** | **MUST-BUILD.** New table (per-user tier): `composition_progress_goal(user_id UUID, project_id UUID, daily_goal INT CHECK (daily_goal > 0), updated_at, PRIMARY KEY (user_id, project_id))` — mirrors `composition_progress_baseline`'s shape ([`migrate.py:496`](../../../services/composition-service/app/db/migrate.py#L496)) minus its `chapter_id` (a goal is per-day, not per-chapter). ⚠ **NO `book_id` column.** Both siblings (`composition_daily_progress` [`:475`](../../../services/composition-service/app/db/migrate.py#L475), `composition_progress_baseline` [`:496`](../../../services/composition-service/app/db/migrate.py#L496)) carry **none** — the book grant is enforced at the router by `_require_work(...)` **before** the repo, exactly as `progress.py` already does, and the row is never read by `book_id`. Adding one "for symmetry" would be a **column written and never read** — the write-only bug class this very spec exists to kill. `GET /progress` resolves `daily_goal` from this table, **falling back** to `work.settings.daily_goal` when absent, and returns `daily_goal_source: 'user' \| 'work_legacy' \| 'none'` (**SET-1**). The writer **only** writes the new table. [F-Q7](#f-q7). |
| **BE-Q4** | cost gate for the paid quality actions | `composition.self_heal_propose` (+ `.quality_report`) descriptors on the **generic** `GET /actions/preview` → `POST /actions/confirm` | — | — | — | **M** | **v2 / OQ-3.** *Not a v1 blocker.* **Do NOT invent `/self-heal/estimate`** — three such routes already 404 in production (plan-30 §3.3). |
| **BE-18** | `PATCH /works/{pid}` settings full-blob REPLACE | — | — | — | — | XS | **Inherited from plan-30.** BE-P2 removes *this wave's* exposure to it; the defect itself stays plan-30's. |

**EXISTS — verified, no work:** `GET|POST /works/{pid}/canon-rules` · `PATCH|DELETE /canon-rules/{id}`
(If-Match OCC, 412 `CANON_VERSION_CONFLICT`) · `GET /works/{pid}/canon-issues` · the rule-violations
lens · `POST /jobs/{job_id}/dismiss-violation` · `POST /jobs/{job_id}/correction` ·
`GET /works/{pid}/correction-stats` · `POST /works/{pid}/self-heal/propose` ·
`GET|POST /works/{pid}/progress{,/report,/baseline}` · the 4 `composition_canon_rule_*` MCP tools.

**Gateway: zero changes.** `gateway-setup.ts:350-354` proxies `/v1/composition/*` with a generic
`pathFilter` and **no rewrite** — every route above is auto-proxied the moment it exists.

---

## Registration checklist (GG-8)

Four new ids: **`quality-canon-rules`, `quality-corrections`, `quality-heal`, `progress`.**
The two machine guards are currently **green with zero drift** (py enum **57** == contract enum **57**
== openable **57**). After this wave: **61 == 61 == 61.** Here is exactly how it stays green.

**Gate check first — is each panel openable by a BARE id?** ✅ **All four are.** None needs a `node_id`
/ `rule_id` to open — `focusRuleId` is an *optional* deep-link param with a defined no-param behavior
(list everything), exactly like `quality-canon`. ⇒ **none** is `hiddenFromPalette`; all four go into the
enum, the palette, and the User Guide. **X-12 does not bite this wave.**

| # | File | Edit |
|---|---|---|
| 0 | `frontend/src/features/studio/palette/useStudioCommands.ts` | **Wave 0 / X-2 — do this first.** Add `'quality'` to `CATEGORY_ORDER` (9 → 10) **and** add the membership assertion to `panelCatalogContract.test.ts` (`every(p => CATEGORY_ORDER.includes(p.category))`). Without it, three new rows land in a category that sorts at index −1. |
| 1 | `frontend/src/features/studio/panels/QualityCanonRulesPanel.tsx`<br>`…/ProgressPanel.tsx`<br>`…/QualityCorrectionsPanel.tsx`<br>`…/QualityHealPanel.tsx` | The 4 components. Roots: `data-testid="studio-quality-canon-rules-panel"`, `studio-progress-panel`, `studio-quality-corrections-panel`, `studio-quality-heal-panel`. Each: `useStudioPanel(id, props.api)` + `useQualityWork(host.bookId, token)` + `if (work.kind !== 'ready') return <QualityWorkGate …/>`. |
| 2 | `frontend/src/features/studio/panels/catalog.ts` | 4 `STUDIO_PANELS` rows. `category: 'quality'` ×3; `category: 'editor'` ×1 (`progress` — QC-2). **`guideBodyKey` is mandatory on all four** (X-3). |
| 3 | `frontend/src/i18n/locales/en/studio.json` | `panels.<id>.{title,desc,guideBody}` ×4, plus the ~28 `quality.*` / `progress.*` strings the panels use. |
| 4 | `frontend/src/i18n/locales/{ar,bn,de,es,fr,hi,id,ja,ko,ms,pt-BR,ru,th,tr,vi,zh-CN,zh-TW}/studio.json` | Same keys × 17 locales — **`python scripts/i18n_translate.py`**, never hand-written. ⚠ The tool **gap-fills only**: it keeps an existing translation, so **never edit an `en` string that already has 17 translations** — add a new key instead (the note at [`QualityCanonPanel.tsx:52-55`](../../../frontend/src/features/studio/panels/QualityCanonPanel.tsx#L52) learned this the hard way). |
| 5 | `services/chat-service/app/services/frontend_tools.py` | **Two edits** in `UI_OPEN_STUDIO_PANEL_TOOL`: (a) append the 4 ids to the `panel_id` **enum** (~line 402); (b) append 4 clauses to the tool **description** (~403-481) — that gloss is the model's only hint the panel exists. Suggested: `'quality-canon-rules' = author the canon rules the critic enforces (create/edit/archive/restore invariants); 'quality-corrections' = your accept/edit/regenerate/reject rates on AI drafts — the quality signal; 'quality-heal' = run Polish on a chapter and accept/reject each proposed fix before it touches your prose; 'progress' = words written today, streak, daily goal, and the book total.` |
| 6 | `contracts/frontend-tools.contract.json` | **NEVER hand-edit — regenerate:** `cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py`, and **commit the regenerated JSON in the same commit** as steps 2 + 5. |
| 7 | `frontend/src/features/studio/panels/QualityHubPanel.tsx` | `CARDS` 4 → **7** (`quality-canon-rules` ⚖️, `quality-corrections` 📈, `quality-heal` ✨). **`progress` is NOT a card** (QC-2). |
| 8 **(mandatory — X-4)** | `frontend/src/features/studio/agent/handlers/compositionEffects.ts` **(new file)** | `registerEffectHandler(/^composition_canon_rule_/, …)` → invalidate `['composition','canon',projectId]` **and** the rule-violations key. `registerEffectHandler(/^composition_record_correction$/, …)` → invalidate `['composition','correction-stats',projectId]` — **the first handler that proves [F-Q12](#f-q12)'s comment false.** Register it in `useStudioEffectReconciler` and **delete the now-false comment at `:8-9`.** |
| 9 *(cond.)* | `frontend/src/features/studio/host/studioLinks.ts` | Not needed — these panels are reached via `host.openPanel`, not a URL scheme. Skip. |
| 10 *(cond.)* | `onboarding/tours.ts` | Not a role-tour step in v1. Skip (`quality` hub's `tourAnchor` already covers the area). |

**Verify — all four green (the first two are the drift-locks):**
```
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
cd frontend && npx vitest run \
  src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
  src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
  src/features/studio/palette/__tests__/useStudioCommands.test.ts \
  src/features/chat/nav/__tests__/frontendToolContract.test.ts
```
**Do NOT touch:** `StudioDock.tsx`, `StudioFrame.tsx`, `useStudioCommands.ts` (beyond X-2's
`CATEGORY_ORDER`), `UserGuidePanel.tsx` — all derive from `catalog.ts`.

---

## Agent surface

### MCP tools that drive this domain

| Domain | Tools | Status |
|---|---|---|
| canon rules | `composition_list_canon_rules` · `composition_canon_rule_create` · `_update` (OCC `expected_version`) · `_delete` | **exist** |
| canon rules | `composition_canon_rule_restore` | **BE-11c — MUST-BUILD** (parity: the human gains restore) |
| corrections | `composition_record_correction` | **BE-9b — MUST-BUILD** |
| progress | — | **none, and none is proposed.** Progress is a *personal stat*, not a capability the agent should write. Recording words on the user's behalf would corrupt their own signal. **This is a deliberate non-gap; do not "fix" it.** |
| self-heal | — | **none.** The REST route is the surface. An MCP `composition_self_heal_propose` is an *optional follow-up* (plan-30 G-POLISH-SELFHEAL: *"MCP tool = optional follow-up"*), **not** in this wave: it is a **paid** action and would need a Tier-W propose→confirm descriptor (BE-Q4) to be admissible at all. → **OQ-3**. |

### Lane-B effect handlers (X-4)

`handlers/compositionEffects.ts` (new) — see step 8. Two patterns, both **required for this wave**:
`^composition_canon_rule_` and `^composition_record_correction$`. Without them an agent write to a
canon rule leaves `quality-canon-rules` **stale**, which is the whole failure X-4 exists to stop.

### The INVERSE gaps this wave closes and opens

- **Closes:** the agent could create/update/delete a canon rule; the human could not (in the Studio). Now both can.
- **Closes:** `kind` was agent-writable and human-invisible ([F-Q10](#f-q10)).
- **Opens (deliberately):** the human can now **restore** a canon rule — so BE-11c gives the agent the same verb *in the same milestone*. **Do not ship the human half alone**; a one-sided restore is the GG-2 inverse defect, immediately.
- **Records:** `composition_dismiss_violation` has **no MCP tool** (only REST). The human gains dismiss in M1 (QC-9); the agent still cannot. → **OQ-4**, a one-row inverse gap, not this wave's job.

---

## Tenancy · settings · OCC · cost gates

**Tenancy.**

| Row / table | Tier | Scope key | Verdict |
|---|---|---|---|
| `canon_rule` | **Per-book** (shared package row) | `project_id` + `book_id`; access gated on the E0 book grant *before* the repo (`canon.py::_require_work` / `_rule_project_id`) | ✅ correct as built. The by-id routes derive the scope **from the row**, never from a body `book_id` — the H13 no-oracle shape. `quality-canon-rules` adds no new tier. |
| `generation_correction` | **Per-book** row, **per-user** actor stamp (`created_by`) | `project_id` + `book_id` (derived from the job **inside the INSERT**) | ✅ correct. The outbox payload carries `user_id = created_by` — the learning store is keyed per correcting user. Two collaborators' tastes do not merge. |
| `composition_daily_progress` / `_baseline` | **Per-user** | `(user_id, project_id, chapter_id, …)` | ✅ correct (PM-16). |
| `work.settings.daily_goal` | **Per-book, user-editable** | none | 🔴 **DEFECT** — [F-Q7](#f-q7). Fixed by **BE-P2** (`composition_progress_goal`, **per-user**, `PK (user_id, project_id)`). |
| `composition_progress_goal` **(new)** | **Per-user** | `(user_id, project_id)` | Declared here. **No `book_id` column** — neither sibling (`composition_daily_progress`, `composition_progress_baseline`) has one; the book grant is gated at the router (`_require_work`) *before* the repo, and every read/write filters on `user_id`. A `book_id` here would be written and never read (BE-P2). |

**Settings (SET-1..8).** One new user setting: **the daily word goal.**
- **SET-1 (effective value + source tier):** `GET /progress` returns `daily_goal_source: 'user' | 'work_legacy' | 'none'`, and the panel **renders it** (*"your goal · not shared with collaborators"* / *"from the book's shared settings"*). No silent hidden default.
- **SET-2 (server-side):** Postgres. No localStorage.
- **SET-3 (one home, one name):** the goal lives in `composition_progress_goal` and nowhere else. `work.settings.daily_goal` becomes **read-only legacy** — the writer never touches it again.
- **SET-4 (consumed, proven by effect):** a test asserts the goal bar + the `ReferenceLine` move when the goal changes.
- **SET-5 (enum-validated):** `goal` is an int, `>= 0`, `0` = clear (→ `NULL`). `422` otherwise.
- **No new env flag.** `daily_goal` is a per-user choice; an env var would be exactly the abuse CLAUDE.md names.

**OCC.**
- `canon_rule`: `If-Match: <version>` on `PATCH` → **412** `{code:'CANON_VERSION_CONFLICT', current}`. The panel re-renders `current`, keeps the user's draft, and asks. Chips/selects over the rule **serialize their writes** (`instant-commit-control-over-occ-entity-needs-write-serialization`).
- `chapter draft` (self-heal apply): `expectedDraftVersion` is checked **client-side at the hoist** before the document is replaced ([F-Q6](#f-q6)) *and* the subsequent save carries the draft's `If-Match` as it already does. Two gates, because the first one is about *the proposals being stale*, and the second is about *the save racing*.
- `authoring_run_units`: accept/reject are already guarded FSM transitions (`transition_unit(from_statuses=…)`). The correction write rides **inside** that guard's success path — never on a lost race.

**Cost gates.**
- `quality-heal`'s **Run Polish** is a **paid LLM action** and today has **no estimate** (an existing, pre-Studio gap). **v1 ports it verbatim** and adds **no bespoke estimate route** (QC-7). The user's cost controls are the existing ones: an explicit button, an explicit `ModelPicker`, and the opt-in `rerank` toggle whose label already says *"auto-tick (AI, costs more)"*.
- The correct fix is a `composition.self_heal_propose` descriptor on the **generic** `/actions/preview` → `/actions/confirm` spine (**BE-Q4**, v2, **OQ-3**). Three invented per-action estimate routes already 404 in production — this wave adds zero.
- Canon CRUD, progress, and correction-stats are **free**. `quality-corrections` triggers **no** LLM call.

---

## Milestones

Four shippable slices. Each ends at a POST-REVIEW and is independently revertable (GG-7).

### M1 — canon rules (closes `G-CANON-RULE-CRUD`, P0)
**Build:** X-2 (`CATEGORY_ORDER` + membership assertion) → BE-11a/b/c → `quality-canon-rules` panel +
GG-8 registration → the two-way deep-link → QC-9 (`dismiss` on `quality-canon`'s `RuleRow`) →
[F-Q10](#f-q10) (`kind` in the TS type + the form) → the Lane-B canon handler.
**DoD:** create/edit/archive/**restore** round-trip green · a 412 test that asserts the panel shows
`current` and **keeps the user's draft** · `include_archived` returns the archived rule a violation
points at · contract guards **58 == 58 == 58** · **live browser smoke** (below).

### M2 — progress (closes `G-PROGRESS`)
**Build:** BE-P2 (`composition_progress_goal` + `PUT …/progress/goal` + the read-through fallback +
`daily_goal_source`) → rewrite `useSetDailyGoal` (delete the `patchWork` caller) → BE-P1 *(or drop it —
decide in PLAN)* → `progress` panel + registration.
**DoD:** two users on one book have **independent goals** (a real-SQL test, not a mock — a mock would
encode the bug) · a user with a legacy `work.settings.daily_goal` still sees it, `source:'work_legacy'` ·
setting a goal writes **only** the new table · the panel renders the source tier · **59 == 59 == 59**.

### M3 — self-heal + the critic link (closes `G-POLISH-SELFHEAL`, `D-QUALITY-CRITIC-HEAL-LINK`)
**Build:** `applyHealedDocument` on `ManuscriptUnitApi` (QC-4) → `usePolishProposals` → react-query cache
(QC-8) → `quality-heal` panel → **pass `proposals` into `QualityCriticPanel`'s `QualityReportSection`**.
**DoD:** the three **stale** guards each render their own message and **disable Apply** (three tests —
chapter mismatch, version mismatch, dirty) · a test asserts the `violation-has-fix` badge **appears in
`quality-critic`** after `quality-heal` runs for the same chapter, and **does not** for a different
chapter · the legacy `PolishPanel` still passes its own tests (the hook's return shape is unchanged) ·
**60 == 60 == 60**.
⚠ **Blocked on Wave-0 X-1** — without it the `ModelPicker` empty state destroys the dock.

### M4 — the correction flywheel (closes `G-CORRECTION-FLYWHEEL`)
**Build:** BE-9c + BE-9c′ (**the denominator fix — first, alone, with its own tests**) → BE-9a (`job_id`
column + `DraftOutcome.job_id` + the driver write) → BE-9b (`composition_record_correction` + the
`accept_unit`/`reject_unit` write) → `quality-corrections` panel → the Lane-B correction handler.
**DoD:** a repo test proves a `plan_pass` / `quality_report` / `self_heal_propose` job **does not** move
`accept_rate` · a repo test proves a `rewrite` **selection-edit** job **still** does not (the
`NOT selection_edit` predicate survived the allowlist — [F-Q3a](#f-q3a)) · a `draft_scene` job with
`mode='cowrite'` **does** land in the *Stream* column (the allowlist did not amputate it) · posting an
unregistered `operation` to a draft route **422s** (BE-9c′) · rejecting an authoring-run unit writes
**exactly one** `generation_correction` with
`kind='reject'` and the right `job_id` · accept-**as-is** writes **none** (H2) · a unit with
`job_id IS NULL` records nothing and the run report **says so** · the outbox emits
`GENERATION_CORRECTED` in the **same transaction** · **cross-service live-smoke** (composition ↔
book-service restore ↔ the outbox relay) · **61 == 61 == 61**.

---

## Definition of Done

1. **Unit suites green** — `frontend` vitest (the 4 new panels + the 4 drift-lock suites) and
   `composition-service` pytest (`python -m pytest tests -q -n auto --dist loadgroup`; any new test
   touching real Postgres carries `pytestmark = pytest.mark.xdist_group("pg")`).
2. **The two machine guards green at 61 == 61 == 61**, with the regenerated
   `contracts/frontend-tools.contract.json` committed **in the same commit** as `catalog.ts` +
   `frontend_tools.py`.
3. **17 locales generated** by `scripts/i18n_translate.py`, no hand-written translations, **no edits to
   existing `en` strings that already have translations**.
4. 🔴 **LIVE BROWSER SMOKE — mandatory, not optional.** A green unit suite has repeatedly hidden *"the
   FE could not actually execute it"* (`agent-gui-loop-needs-live-browser-smoke-not-raw-stream`), and
   this repo's `24_plan_hub_v2.md` **named this exact DoD and then shipped without it (H8.2)**. New
   Playwright spec `frontend/e2e/studio-quality.spec.ts`, run against a **rebuilt** image (stale images
   = false green), signed in as `claude-test@loreweave.dev`:
   - **VERIFY BY EFFECT, not by raw stream** — for each of the 4 ids, drive
     `ui_open_studio_panel {panel_id: "<id>"}` **through a real agent turn** (local lm_studio model, $0)
     and assert the **dock tab mounts** (`[data-testid="studio-<id>-panel"]` visible). A `shown:true`
     in the stream proves nothing; the `panel_id`-enum bug shipped once already exactly this way.
   - **Canon round-trip:** palette → *Studio: Open Canon rules* → add a rule → it appears → edit it →
     archive it → **Show archived** → restore → it is back in the active list.
   - **The deep-link chain:** `quality-canon` → a violation row's **Edit rule** → `quality-canon-rules`
     opens **focused on that rule id**.
   - **The heal loop (the one that was dark):** `quality-heal` → pick a chapter + a **local** model →
     Run Polish → tick one edit → **Apply** → the editor's document changes → open `quality-critic` on
     the **same chapter** → assert **`[data-testid="violation-has-fix"]` is visible.** This single
     assertion is `D-QUALITY-CRITIC-HEAL-LINK` closed, proven by effect.
   - **The stale guard:** run Polish, then type in the editor, then click Apply → assert the **stale
     banner** renders and the document is **unchanged**.
   - **DOCK-7 regression:** with a model-less account, open `quality-heal` → click the picker's
     *Add a model* CTA → assert the **dock is still mounted** (X-1's guard, on the panel that
     introduces the new `ModelPicker` call site).
5. **Cross-service live-smoke evidence (M4)** — the VERIFY evidence string carries
   `live smoke: <one-liner>` (composition + book-service + the outbox relay ⇒ ≥2 services). A
   mock-only correction test proves the function was called, **not** that a row landed and an event
   relayed.
6. **`/review-impl`** on M4 (a new cross-service write path + a DDL column) and on BE-P2 (a tenancy
   boundary).
7. **SESSION** — `docs/sessions/SESSION_HANDOFF.md` updated; `D-QUALITY-CRITIC-HEAL-LINK` and 00C
   **Q-3(a)(b)** moved to *Recently cleared*; **OQ-1..4 filed as Deferred rows with their gate reason.**

---

## Open questions / Deferred

| # | Question | State |
|---|---|---|
| **OQ-1** | **Can a Studio-Compose `propose_edit` Apply/Dismiss ever record a correction?** It has no `job_id` and the prose came from a **chat-service** turn, not a composition `generation_job` ([F-Q4](#f-q4)). Options: (a) mint a `generation_job` for a chat prose turn (cross-service, and it would need a `mode`/`operation` that BE-9c's allowlist admits); (b) add a nullable `chat_run_id` to `generation_correction` and relax the FK; (c) accept that the flywheel only learns from **structured** generation (engine + authoring runs) and say so. **Plan-30's BE-9 assumed this was free. It is not.** → **Deferred, gate #2 (large/structural — needs a design).** Recommendation: **(c) for now**, and revisit when Compose's prose path is itself specced. |
| **OQ-2** | **Should accepting/rejecting a self-heal fix be a correction kind?** The CHECK constraint is closed on `('edit','pick_different','regenerate','reject')`; adding `heal_accept`/`heal_reject` is a migration **and** triggers the `migration-check-constraint-must-backfill-all-historical-blocks` law. The signal is real but it is a **different** signal (correcting a *fix*, not a *draft*). → **Deferred, gate #5 (conscious won't-fix for v1)** — QC-5. |
| **OQ-3** | **The paid quality actions have no cost estimate** (Run Polish, Analyze quality, Coverage). The fix is a descriptor on the **generic** action spine (BE-Q4), not a per-action route. → **Deferred, gate #2.** It is a genuine cost-visibility gap across *three already-shipped panels*, so it is **not** this wave's regression — but it should not be forgotten. |
| **OQ-4** | **`dismiss-violation` has no MCP tool** — after QC-9 the human can dismiss a false-positive violation and the agent cannot (a GG-2 inverse gap, one row). → **Deferred, gate #1 (out of scope).** |
| **OQ-5** | **Is `by_chapter` worth a route change (BE-P1)?** The dimension exists in the table and is collapsed in the repo. **PO/PLAN decides.** The panel ships either way. |
| **UNVERIFIED** | Whether `learning-service`'s corrections consumer copes with a **burst** of `GENERATION_CORRECTED` events from a Revert-All (which rejects every unit in one sweep — potentially dozens of corrections in one transaction storm). Not read. **Check before M4 ships**, or rate-limit the capture in `revert_all`. |
| **UNVERIFIED** | Whether any **other** consumer reads `work.settings.daily_goal` (BE-P2 makes it legacy-read-only). `grep daily_goal` found only `progress.py::_coerce_goal` and `useProgress.ts`, but a JSONB blob key is grep-hostile — **re-verify at BUILD.** |

---

## Risks

| Risk | Mitigation |
|---|---|
| 🔴 **`quality-corrections` ships on a corrupted denominator** and the author trusts a false "you accept 71% of drafts". | **BE-9c ships in the same milestone as the panel** (M4), with a test that a `plan_pass` job cannot move `accept_rate`. Non-negotiable. |
| 🔴 **`quality-heal` silently reverts the author's prose** by applying a splice of a stale `sourceText`. | The three **stale** guards (QC-4), each rendered and each tested. The bug exists on the legacy page today and is only masked by co-location. |
| **BE-9a's `job_id` backfill temptation.** A later agent "fixes" the NULLs by guessing the unit's job from the timestamp. | The column is **nullable by design** and the run report **states** when a unit has no job. Comment it in the DDL: *"NULL = drafted before D-31 M4. Never backfill a guess — a wrong job_id attributes the author's rejection to someone else's generation."* |
| **Two `PolishPanel` consumers diverge** once `usePolishProposals` moves to the query cache. | The hook's **return shape is unchanged**; the legacy panel's tests are the regression gate and must stay green (they are, until Wave 6 retires the page). |
| **`ChapterEditorPage` gets retired before M2.** | **GG-4 gate, restated:** `progress` and the canon/heal/corrections ports are **prerequisites** of spec 16's M1. Retiring first deletes the reader of a loop the Studio is already writing to. |
| The i18n tool leaves 17 stale locales because someone edited an existing `en` string. | Step 4 of the checklist, and the in-code warning at `QualityCanonPanel.tsx:52`. Add keys; do not edit them. |
