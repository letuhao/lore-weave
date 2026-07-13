# 34 · Arc Templates + 拆文 (Import & Deconstruct)

> **Status:** 📐 specced 2026-07-13 · **adversarially reviewed 2026-07-13 (§0.1 added — the audit's "BE: NONE" for 拆文 is FALSE)** · branch `feat/context-budget-law` (studio track) · **L** (files ≈ 19, logic ≈ 9, side_effects = 3 — **3** new REST routes, no schema change)
> **Type:** FS. Mostly a **PORT** + 2 thin route wrappers. Decision prefix **AT-**.
> **Closes:** **G-ARC-TEMPLATE-LIBRARY** (L) · **G-IMPORT-DECONSTRUCT** (M) — [`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) §5.2.
> **Wave:** **4** of plan 30 (§7). Gated behind Wave 0 (X-1 `AddModelCta` DOCK-7, X-2 `CATEGORY_ORDER`, X-3 `guideBodyKey`, X-4 Lane-B handlers).
> **Design draft:** `design-drafts/screens/studio/screen-arc-templates.html` (house style per plan 30 §8.3 — dark-only, banner comment, every state rendered).
> **Inherits, does not re-litigate:** plan 30 §0 (PO-1..4) · §8.1 (spec 28's AN-8 edit-discipline table; Tier-W executes nothing; OCC everywhere; grant-from-the-ROW) · §10 (REFUTED claims).
> **Panel:** `arc-templates` (category `storyBible`), **with an "Import & Deconstruct" SECTION inside it.** Not a standalone panel — the import's only purpose is to feed the template library.

---

## 0 · TL;DR for the next agent — the three places the audit is wrong

> **The estimate moves in BOTH directions.** The audit **over**-sized drift (it needs no backend at all) and **under**-sized the deconstruct (its poll leg does not exist — §0.1). Read both before you trust the wave size.

The audit told this wave to **park the drift view behind BE-8** and called `build_template_drift` "REAL work — the function does not exist." Both halves were checked against code. **The audit is half right and the consequence inverts.**

| Audit claim | Verdict against code | Consequence |
|---|---|---|
| *"`build_template_drift` DOES NOT EXIST"* | ✅ **TRUE** — `grep build_template_drift services/composition-service/app/` hits only [`mcp/server.py:4698-4700`](../../../services/composition-service/app/mcp/server.py#L4698) (the `getattr` seam). `app/engine/arc_conformance.py` has `build_arc_conformance` + `build_deep_report` and **no** `build_template_drift`. | The **agent's** `composition_arc_template_drift` really is a `_pending_engine` stub. |
| *"⇒ the drift VIEW is REAL backend work ⇒ PARK it"* | 🔴 **FALSE.** **`GET /v1/composition/works/{pid}/conformance?scope=arc_template_drift&arc_id=<structure_node_id>` is SHIPPED, wired, and has ZERO FE consumers** — [`routers/conformance.py:390-404`](../../../services/composition-service/app/routers/conformance.py#L390). It resolves the arc's `arc_template_id` provenance and runs `compute_arc_report(…, by_structure=False)` ([`engine/arc_conformance_orchestrate.py:38`](../../../services/composition-service/app/engine/arc_conformance_orchestrate.py#L38)). | **The human drift view is BE-NONE and ships in the core.** BE-8 shrinks to *"point the stubbed MCP tool at the orchestrator the REST route already uses"* — an **agent-parity** slice, still parked, but **S, not M.** |

**The real blocker for drift is not the read — it is the WRITER of the thing the read keys on.** Drift is `diff(structure_node, its arc_template)`, resolved through `structure_node.arc_template_id`. The only tool that was ever meant to stamp that provenance is `composition_arc_apply` → `app.engine.arc_apply.apply_arc_to_spec` — **which also does not exist** ([`server.py:4603-4605`](../../../services/composition-service/app/mcp/server.py#L4603); `grep apply_arc_to_spec app/engine/` → 0 hits). Meanwhile the **human's** apply (`POST /works/{pid}/arc/materialize`, [`routers/plan.py:1260`](../../../services/composition-service/app/routers/plan.py#L1260)) writes **`outline_node` + a `motif_application` ledger** and **no `structure_node` at all** — so it stamps no provenance either.

⇒ **AT-6 (below) closes this with zero backend:** `POST /v1/composition/books/{bid}/arcs` **already accepts `arc_template_id` + `template_version`** ([`routers/arc.py:342,354,482`](../../../services/composition-service/app/routers/arc.py#L482)) and has **no FE consumer**. The panel stamps provenance on the spec arc through that existing route. Drift then has a subject, and the shipped read answers it.

**Third find, not in the audit — a 4th live bug (beyond §3.3's three 404s).** `ArcConformancePanel` — which is rendered **inside** `ArcTemplateLibraryView`'s detail view, i.e. inside this wave's port surface — is **dead at HEAD, on both of its calls:**

- `motifApi.arcConformance()` ([`motif/api.ts:214-226`](../../../frontend/src/features/composition/motif/api.ts#L214)) sends `?scope=arc&arc_template_id=…`. The route was **retargeted by BA4** to `arc_id` = a `structure_node` id ([`conformance.py:339`](../../../services/composition-service/app/routers/conformance.py#L339) — *"BA4: structure_node.id (replaces arc_template_id)"*). FastAPI **silently drops** the unknown query param ⇒ `arc_id=None` ⇒ `_resolve_book_arc(None, …)`.
- `motifApi.arcConformanceRunPropose()` ([`motif/api.ts:245-260`](../../../frontend/src/features/composition/motif/api.ts#L245)) sends `arc_template_id` into `_ConformanceRunArgs`, which is **`ForbidExtra` and has no such field** ([`server.py:3105-3117`](../../../services/composition-service/app/mcp/server.py#L3105)) ⇒ arg-validation refusal.

This is the repo's own `cross-service-normalization-bug-class`: the BA4 retarget swept the service and never swept the FE. **AT-7: the port DROPS `ArcConformancePanel` from `arc-templates`.** "Did the prose realize my plan" is a `structure_node` question and belongs to Wave 3's `quality-conformance` (spec 33), which owns the fix. Dropping it removes nothing that works.

### 0.1 · Fourth find — 🔴 **the 拆文 CONFIRM RETURNS HTTP 500. The job is never created. M2 is NOT "BE-NONE".**

> 🔴 **MECHANISM CORRECTED 2026-07-13** (Wave-0 adversarial QC + an independent in-container live repro).
> **The first version of this section was WRONG**, and its wrongness propagated into `33` §1.2 and plan
> `30` §3.3. It said: *"the job is enqueued and runs, but nobody can poll it — the spend happens and the
> caller never learns the outcome (`silent-success-is-a-bug`)."* **Every clause of that is false.** The
> job is **never enqueued**. Nothing runs. Nobody is charged. **It dies at the confirm, with a 500.**
> The corrected trace, every line verified against source:

The audit (§5.2 `G-IMPORT-DECONSTRUCT`) sized the deconstruct as **"BE: NONE — the 4 REST routes + the proven `mcpBridge` propose→confirm→**poll** pattern are sufficient."** The propose is real. **The confirm 500s.**

1. `_execute_arc_import` enqueues with **`project_id=None`** ([`actions.py:643-645`](../../../services/composition-service/app/routers/actions.py#L643)) — a deconstruct is genuinely not Work-bound.
2. `_enqueue_motif_job` then stamps **`pid = uuid4()`** — *"a synthetic project_id … so the row is valid"* ([`actions.py:552`](../../../services/composition-service/app/routers/actions.py#L552)). It is a **random UUID with no `composition_work` row behind it.** (The comment says *"from the user"*; the code does not derive it from the user at all.)
3. 🔴 **`GenerationJobsRepo.create()` is NOT a plain INSERT.** ([`generation_jobs.py:159-173`](../../../services/composition-service/app/db/repositories/generation_jobs.py#L159)) `generation_job.book_id` is **`UUID NOT NULL`** ([`migrate.py:269`](../../../services/composition-service/app/db/migrate.py#L269)) and the statement **derives it from the Work**: `INSERT INTO generation_job … SELECT $1, $2, w.book_id, … FROM composition_work w WHERE w.project_id = $2`. The synthetic id matches **ZERO rows** ⇒ **zero rows inserted** ⇒ [`:198-206`](../../../services/composition-service/app/db/repositories/generation_jobs.py#L198) raises **`ReferenceViolationError("project … has no composition_work row")`**.
4. `actions.py` has **no `except ReferenceViolationError`** (grep: **0 hits**) ⇒ it escapes to the global `@app.exception_handler(Exception)` ([`main.py:200`](../../../services/composition-service/app/main.py#L200)) ⇒ 🔴 **`POST /actions/confirm` returns HTTP 500** — *after* `_claim_or_replay` ([`:504`](../../../services/composition-service/app/routers/actions.py#L504)) **burnt the confirm token** (a retry gets **409 `already_consumed`**).

**⇒ There is no `job_id`, no `generation_job` row, and nothing to poll — the poll is never reached.**

- 🔴 **NOT a 404 at the poll.** The `GET /jobs/{id}` analysis in the old text described a code path **that never executes**. (It *would* also 404 — but only if a row existed, and one cannot.)
- 🔴 **NOBODY WAS EVER CHARGED.** The `POST` dies at step 3: **no Redis XADD, no worker pickup, no LLM call, no recorded spend.** `_precheck_or_402` ([`:517`](../../../services/composition-service/app/routers/actions.py#L517)) does reserve a billing **hold** one line earlier — a pre-authorization, *not* a charge. A burnt token + a dangling hold is a real defect; *"the spend happens"* / *"the user pays and watches a spinner forever"* is **not**, and is retracted. It is **not** `silent-success-is-a-bug` — a 500 is the opposite of a silent success.
- ✅ `_execute_conformance_run` ([`:723`](../../../services/composition-service/app/routers/actions.py#L723)) passes a **real** `project_id` ⇒ **conformance is unaffected.** This is a **mine / arc-import-only** defect.

**Fifth find, free with the fourth: `motifApi.mineConfirm` is dead at HEAD for exactly the same reason** — `_execute_motif_mine` ([`actions.py:644`](../../../services/composition-service/app/routers/actions.py#L644)) also passes `project_id=None`, so **the ⛏ Mine confirm 500s too**, before its poll leg is ever reached ([`motif/api.ts:170-176`](../../../frontend/src/features/composition/motif/api.ts#L170)). **Plan 30 §3.3 lists neither.** Do **not** mirror `mineConfirm`'s poll leg (AT-5 is amended accordingly) — mirror only its **propose + confirm** legs.

#### ⚠ WHY THE OBVIOUS FIX IS WRONG — and why this row's old size was fiction

This section used to close with: *"it needs **BE-7c**, an owner-scoped job read … size **XS**"*, and the BE-7c row promised it would *"unbreak mine, arc-import and the deep-conformance job in one route."*

🔴 **An owner-scoped read route CANNOT FIX THIS. It would be a route that reads a row that does not exist.** The producer can never insert it — that is the whole bug.

And it would **SHIP GREEN.** Its integration test would seed the `generation_job` row with a raw `INSERT`, the route would read it back correctly, every assertion would pass — and 拆文 would **still 500 at confirm**, because nothing on the test's path ever went through the **producer**. That is this repo's own **`fixtures-can-seed-a-field-the-writer-never-sets`** bug class, about to be committed *on purpose*. **Name it so the next agent cannot re-make it.**

**The real fix is the whole Work-less job LANE** (7 legs, not 1): the **DDL** (`project_id`/`book_id` `DROP NOT NULL` + a **both-or-neither shape CHECK** + a partial owner index) · **`create_unbound()`** (a plain INSERT — *do not touch `create()`*, the hot path for every draft) · the **model** change (`UUID | None`) · 🔴 **the `_enqueue_motif_job` writer fix — delete the `uuid4()` synthetic pid** *(this is the leg that actually stops the 500)* · the owner-scoped **read route** · the **MCP** arg drop · and **tests forced through the producer.**

⇒ 🔴 **THE CANONICAL FIX IS `W0-BE1`, AND IT IS ALREADY WRITTEN.** [`docs/plans/2026-07-13-studio-wave-0-foundations.md`](../../plans/2026-07-13-studio-wave-0-foundations.md) slice **`W0-BE1`** carries all seven legs (Files (a)–(g)), with the build detail written once, verbatim, in [`docs/plans/2026-07-13-studio-wave-3-motif.md`](../../plans/2026-07-13-studio-wave-3-motif.md) `3a-1` (a)–(d). **The Wave-0 plan is correct and is the source of truth — build from it. Do not re-derive it and do not fork a second DDL.** ⚠ **Size is NOT "XS"** — a DDL change + a new repo method + a model change + a writer change + a route + an MCP arg is an **S/M with a schema side effect.**

**Consequence for this wave — the estimate still moves, but the BE lands EARLIER than either spec said.** M2 is **not** BE-NONE; it **consumes** `W0-BE1`, which **Wave 0 builds** (it was pulled forward out of Wave 3a because the defect fires **today**, on the live legacy page). Wave 4 **verifies** the lane and consumes the finished route for 拆文.

---

## 1 · Why this exists

**拆文** — deconstructing a reference novel into reusable structure — is a headline differentiator for this product's target audience (web-novel authors who study 套路 by taking other books apart). At HEAD it is **100% agent-only**, and its input CRUD has **zero FE consumers**:

| Capability | Backend | Human surface |
|---|---|---|
| Create / list / read / delete an import source | 4 REST routes, [`routers/import_source.py`](../../../services/composition-service/app/routers/import_source.py) | **NONE** — `grep -rn "import-sources" frontend/src` → **empty** |
| Deconstruct it into an arc template (拆文) | `composition_arc_import_analyze` (Tier-W, paid, async) — **already on the BFF FE-bridge allowlist**, [`tools.controller.ts:24-31`](../../../services/api-gateway-bff/src/tools/tools.controller.ts#L24) | **NONE** |
| Suggest an arc for this premise | `composition_arc_suggest` ([`server.py:2272`](../../../services/composition-service/app/mcp/server.py#L2272)) | **NONE** — no REST route |
| Save this arc as a template | `composition_arc_extract_template` ([`server.py:4627`](../../../services/composition-service/app/mcp/server.py#L4627); engine **exists**, [`arc_apply.py:652`](../../../services/composition-service/app/engine/arc_apply.py#L652)) | **NONE** — no REST route |
| Browse / CRUD / adopt / apply-preview / materialize | 9 REST routes, all consumed | **LEGACY-ONLY** |

And the shipped UI **advertises the feature it cannot reach.** [`ArcTemplateLibraryView.tsx:50-52`](../../../frontend/src/features/composition/motif/components/ArcTemplateLibraryView.tsx#L50) renders, as its empty state:

> *"No arc templates yet. Adopt one from the catalog, **or import a story to deconstruct.**"*

There is no import entry point anywhere in `frontend/src`. That is a **dangling CTA pointing at a feature with no door** — this repo's `built-mounted-unreachable` class, shipped in the empty state of the very panel that needs it.

**The library is also stranded.** `ArcTemplateLibraryView` is reachable only through
[`MotifLibraryView.tsx:66`](../../../frontend/src/features/composition/motif/components/MotifLibraryView.tsx#L66) (a Motifs|Arcs kind-toggle) → [`CompositionPanel.tsx:879`](../../../frontend/src/features/composition/components/CompositionPanel.tsx#L879) → the legacy `ChapterEditorPage`, which spec 16 slates for deletion. **GG-4: retiring that page before this wave lands DELETES the arc-template library.**

**The asymmetry, stated plainly.** Apply exists for the human. **Extract, suggest, and drift do not exist for anyone with a mouse** — and extract is the half that makes the library *grow from the user's own work*. A library you can only consume from is a catalog, not a library.

---

## 2 · What is already built (so the estimate is trustworthy)

**Frontend — the port surface (all under `frontend/src/features/composition/motif/`):**

| File | What it does | Port verdict |
|---|---|---|
| `arcApi.ts` (71 LOC) | list / get / create / patch(If-Match) / archive / adopt / apply-preview / materialize | **LIFT AS-IS** — every method maps to a live route |
| `arcTypes.ts` | `ArcTemplate`, `ArcApplyArgs`, `ArcApplyPlan`, `ArcMaterializeArgs/Result` | **LIFT AS-IS** |
| `hooks/useArcLibrary.ts` | `arcApi.list({scope:'all'})` | **LIFT**, + add a `scope='catalog'` sibling (AT-2) |
| `hooks/useArcTimeline.ts` · `components/ArcTimelineEditor.tsx` · `ArcTimelineGrid.tsx` · `ArcTimelineMobileList.tsx` · `applyArcEdit.ts` | the thread × chapter layout editor (+ mobile list) | **LIFT AS-IS** — 4 test files already cover it |
| `hooks/useArcApplyPreview.ts` · `components/ArcApplyPreview.tsx` | the PURE rescale/roster-bind/drop-merge preview | **LIFT AS-IS** |
| `hooks/useArcMaterialize.ts` · `components/ArcMaterializeAction.tsx` | commit the preview onto the book | **LIFT**, + AT-6 (stamp provenance) |
| `components/ArcTemplateLibraryView.tsx` | the list + tier chips + the dangling empty state | **LIFT**, fix the empty state (AT-1) |
| `components/MotifStateBoundary.tsx` · `CostConfirmCard.tsx` · `AdoptTargetModal.tsx` | loading/error boundary · the propose→confirm cost card · adopt target | **SHARED with spec 33** — do NOT fork (§9) |
| `components/ArcConformancePanel.tsx` · `hooks/useArcConformance.ts` · `useArcConformanceRun.ts` | arc-vs-prose conformance | **DROP from this panel (AT-7)** — dead at HEAD, and it is spec 33's surface |

**Backend — what exists (verified by reading the routers, not the docs):**

- **9 arc-template REST routes**, [`routers/arc.py`](../../../services/composition-service/app/routers/arc.py): `GET /arc-templates` · `GET /arc-templates/catalog` (**NO-FE-CONSUMER**) · `GET|POST|PATCH|DELETE /arc-templates[/{id}]` · `POST /{id}/adopt` · `POST /{id}/apply` (PURE preview, [`arc.py:278-296`](../../../services/composition-service/app/routers/arc.py#L278)) · `POST /works/{pid}/arc/materialize` ([`plan.py:1260`](../../../services/composition-service/app/routers/plan.py#L1260)).
- **4 import-source REST routes** ([`import_source.py`](../../../services/composition-service/app/routers/import_source.py)) — per-user, H13-uniform 404, **zero FE consumers**.
- **The 拆文 spine, complete THROUGH ENQUEUE — and NO FURTHER:** `composition_arc_import_analyze` mints a `composition.arc_import` confirm token ([`server.py:3055-3105`](../../../services/composition-service/app/mcp/server.py#L3055)) → `POST /v1/composition/actions/confirm` executes `_execute_arc_import` ([`actions.py:669-712`](../../../services/composition-service/app/routers/actions.py#L669)): re-checks the import_source owner, claims the token, prechecks spend, enqueues `analyze_reference`. **The tool is already allowlisted on the BFF bridge.** 🔴 **…AND THE ENQUEUE ITSELF FAILS: `POST /actions/confirm` returns HTTP 500** — `_enqueue_motif_job` stamps a synthetic `project_id`, `GenerationJobsRepo.create()` derives the `NOT NULL book_id` via `INSERT … SELECT … FROM composition_work`, matches **zero rows**, and raises `ReferenceViolationError` into an uncaught 500. **The `generation_job` row is never written**, so there is nothing to poll and the poll leg is never reached (§0.1). *(Both readers — `GET /jobs/{id}` and `composition_get_mine_job` — would also be the wrong gate, but that is downstream of a row that does not exist.)* ⇒ **the Work-less job lane, `W0-BE1`** (§0.1, §5). The `args` model `_ArcImportArgs` ([`server.py:3038-3050`](../../../services/composition-service/app/mcp/server.py#L3038)) is `ForbidExtra` and takes exactly `{import_source_id, use_web, arc_hint, language, model_ref, model_source}` — the Configure step may send **no other field**.
- **The drift read**, `?scope=arc_template_drift` ([`conformance.py:390-404`](../../../services/composition-service/app/routers/conformance.py#L390)) — shipped, unconsumed.
- **The provenance write**, `POST /books/{bid}/arcs` with `arc_template_id`/`template_version` ([`arc.py:482`](../../../services/composition-service/app/routers/arc.py#L482)) — shipped, unconsumed.
- **The extract engine**, `extract_template_from_arc` ([`arc_apply.py:652`](../../../services/composition-service/app/engine/arc_apply.py#L652)) — shipped, reachable **only** by MCP.
- **The suggest engine**, `MotifRetriever.retrieve_arcs` (SQL prefilter → embed → cosine → `match_reason`) — shipped, reachable **only** by MCP.

**Does NOT exist (say it out loud):** `app.engine.arc_apply.apply_arc_to_spec` · `app.engine.arc_conformance.build_template_drift` · any REST route for suggest or extract · 🔴 **any WAY TO CREATE a Work-less `generation_job` at all** — `GenerationJobsRepo.create()` derives its `NOT NULL book_id` from `composition_work`, so a mine/import confirm **500s** and the row is never written; there is therefore also no readable poll, but *the missing piece is the WRITER, not the reader* (§0.1 — `W0-BE1`) · any `composition_arc_adopt` MCP tool (adopt is REST-only — no cost gate; it is quota-bearing, not token-bearing).

---

## 3 · Locked decisions

| # | Decision | Why |
|---|---|---|
| **AT-1** | **ONE new panel: `arc-templates`** (category `storyBible`, openable by **bare id** ⇒ **in** the agent enum + palette + User Guide). The **Import & Deconstruct** flow is a **SECTION inside it**, not a panel. Its empty state stops lying: the "import a story to deconstruct" CTA becomes a **button that opens the section**. | 拆文's only product purpose is to *produce an arc template*. A separate panel would put the producer and the consumer in two docks and re-fork the library. Bare-id openability keeps us out of the **X-12** trap (a `params`-needing panel is structurally outside `ui_open_studio_panel`'s enum). |
| **AT-2** | **Three tiers, one browse, explicitly labelled:** **Mine** (`owner_user_id = me`) · **System** (`owner_user_id IS NULL` — **read-only; clone-to-edit**) · **Catalog** (others' `public` — via the **NO-FE-CONSUMER** `GET /arc-templates/catalog`). `arc_template` has **no `book_id` / `book_shared`** (unlike `motif`) — there is **no book-shared tier**. Do not invent one. | CLAUDE.md User Boundaries: a System row is admin-seeded and **must not be user-mutable**. `PATCH /arc-templates/{id}` already enforces this (owner-filtered ⇒ a System row 404s — [`arc.py:201-204`](../../../services/composition-service/app/routers/arc.py#L201)); the GUI must render *Adopt to edit*, never a disabled-looking edit field. |
| **AT-3** | **Extract ("save this arc as a template") gets a REST route, NOT a bridge allowlist entry.** `composition_arc_extract_template` is a **Tier-A WRITE**, and `FE_BRIDGE_TOOL_ALLOWLIST`'s own contract is *"NOTHING here writes or deletes"* ([`tools.controller.ts:19-31`](../../../services/api-gateway-bff/src/tools/tools.controller.ts#L19)). | Adding a write to the bridge allowlist would silently void the BFF's stated trust model. **BE-7a.** |
| **AT-4** | **Suggest also gets a REST route** (`POST /arc-templates/suggest`), not an allowlist entry. | It is a read, so the allowlist *would* work — but the FE reaches composition **over REST** everywhere else (plan 30 §6.1), and a suggest that is a GET-shaped read has no reason to take the agentic path. **BE-7b.** ⚠ Either way this is **cross-service** if done via the allowlist; REST keeps it single-service and skips a gateway change entirely (the composition proxy's `pathFilter` is generic). |
| **AT-5** | **The deconstruct is cost-gated through the GENERIC spine only:** `mcpExecute('composition_arc_import_analyze')` → `{confirm_token, estimate}` → **`POST /v1/composition/actions/confirm?token=…`** (token in the **query**; identity = the Bearer JWT) → `job_id` → poll **BE-7c's owner-scoped job read**. **No bespoke `/actions/arc_import/estimate` or `/actions/arc_import/confirm` route may be invented.** | This is the exact mistake already shipped 3× (plan 30 §3.3 — `motifApi.conformanceRunEstimate/Confirm` 404 in production **today** because someone invented per-action paths). The generic pair is `GET /actions/preview` + `POST /actions/confirm`. Mirror `motifApi.minePropose/mineConfirm`'s **propose + confirm** legs ([`motif/api.ts:131-176`](../../../frontend/src/features/composition/motif/api.ts#L131)) — those are the right *shape*. ⚠ **Do NOT mirror its POLL leg:** `mineConfirm` polls `compositionApi.getJob`, which is **the wrong route for a Work-less job** — poll **`GET /motif-jobs/{job_id}`** (`W0-BE1`) instead. ⚠⚠ **And do not read `mineConfirm` as "proven end-to-end": at HEAD its own confirm returns HTTP 500** (§0.1) — the Work-less job lane (`W0-BE1`) is what makes *both* callers work. **Verify a green `POST /actions/confirm` → real `job_id` → resolving poll before you trust either.** |
| **AT-6** | **Materialize STAMPS PROVENANCE.** After `POST /works/{pid}/arc/materialize` succeeds, the panel creates (or updates) the book's spec arc via the existing, unconsumed `POST /v1/composition/books/{bid}/arcs` with `{kind:'arc', title, arc_template_id, template_version}`, and links its chapters by **reusing `planHubApi.assignArcChapters`** ([`plan-hub/api.ts:248`](../../../frontend/src/features/plan-hub/api.ts#L248) — **already an FE consumer; do NOT write a second caller**, DOCK-2), passing the `chapter_ids` **materialize itself returns** (they are `outline_node` ids of `kind='chapter'`, which is exactly what `assign_chapters` matches on — [`structure.py:540-562`](../../../services/composition-service/app/db/repositories/structure.py#L540)). 🔴 **The stamp MUST be verified by effect:** `assign-chapters` returns `{assigned: <count>}` and matches rows by predicate — **a 0-count is a silent success.** The panel asserts `assigned == len(chapter_ids)` and surfaces a mismatch as an error, never as a checkmark. **Zero backend.** | Without this, **nothing in the product ever writes `structure_node.arc_template_id`** (the human path writes only `outline_node`; the agent path is a stub) — so the shipped drift read has **no subject**, forever. This is the minimum honest close: it does **not** re-implement `apply_arc_to_spec` (a rescale/pacing/ledger engine); it records *"this arc came from that template"*, which is exactly what drift needs. The `assigned`-count assertion is the repo's `silent-success-is-a-bug` law: a stamp that no-ops leaves drift permanently empty and the panel would render a green tick over it. |
| **AT-11** | 🔴 **THE JOB MUST FIRST BE CREATABLE, THEN READABLE — in that order.** ⚠ **AMENDED 2026-07-13:** this rule used to say only *"the poll is BE-7c's owner-scoped read"*. **That is half the rule, and it is the half that does not fix anything.** At HEAD a Work-less job **cannot be written at all** — the confirm **500s** (§0.1) — so a read route would read a row that never exists (and would **ship green** on a raw-`INSERT` fixture: `fixtures-can-seed-a-field-the-writer-never-sets`). **(1) WRITE:** `_enqueue_motif_job` must drop the synthetic `uuid4()` and call **`create_unbound()`** (scope columns **NULL**, guarded by a both-or-neither CHECK). **(2) READ:** poll the owner-scoped **`GET /motif-jobs/{job_id}`** — **NOT `GET /jobs/{id}`, NOT `composition_get_mine_job`**; both gate on a `composition_work` this job does not have. Both legs ship together in **[`W0-BE1`](../../plans/2026-07-13-studio-wave-0-foundations.md)**. **The FE must not paper over either failure with a spinner-until-timeout** — a 500 at confirm and an unreadable job are both **errors**, and the panel says so. | A Work-less job has **no book to gate on**, so a *book*-grant gate is the wrong gate for it; the row's own `created_by` is the correct scope key (`gate-must-derive-scope-from-the-loaded-row`, applied to a row whose parent is a **user**, not a book). And a row the **producer** can never emit is not fixable at the **reader** — fixing the reader alone is the `fixtures-can-seed-a-field-the-writer-never-sets` trap, committed on purpose. |
| **AT-7** | **`ArcConformancePanel` is DROPPED from `arc-templates`** and its two dead calls are handed to spec 33 (`quality-conformance`) with the finding in §11. `arc-templates` answers **"how far has my arc drifted from its template"** (`?scope=arc_template_drift`); `quality-conformance` answers **"did the prose realize my plan"** (`?scope=arc`). Two questions, two panels, one route family. | The panel is **dead on both calls at HEAD** (§0), so dropping it costs nothing. Keeping it would import a known-broken surface into a brand-new panel and blur the seam BA4 drew deliberately. |
| **AT-8** | **No hidden model default on a spending action.** The Deconstruct section **requires** an explicit BYOK `model_ref` (the `ModelPicker`, capability `chat`), and renders the effective model + its source tier. The worker's platform fallback (`settings.motif_deconstruct_model_ref`) is **never allowed to be the silent payer.** | SET-1..8 (*"no silent hidden default"*) + the repo's own `spend-causing-setting-fails-closed-not-open`. `MotifMinePanel` already sets this precedent — copy it. **Consequence: X-1 (`AddModelCta` DOCK-7) is a HARD prerequisite** — the picker's zero-models state renders `AddModelCta` ([`ModelPicker.tsx:388`](../../../frontend/src/components/model-picker/ModelPicker.tsx#L388)), which today is a raw `<Link>` that **tears down the whole dock**. |
| **AT-9** | **Publishing an import-derived template is ALLOWED, and the panel says what it strips.** The DB trigger `arc_template_publish_strip` ([`migrate.py:1065-1078`](../../../services/composition-service/app/db/migrate.py#L1065)) rewrites `source_ref` → an opaque `lineage:<own id>` on any `visibility → public|unlisted` transition of a row with `source='imported' OR imported_derived`. The visibility control must render this **before** the flip, not after. | It is a **DB trigger, not a prompt** — it cannot be bypassed, and a user who publishes and then finds their source reference silently rewritten has been surprised by their own database. Surfacing it is the honest read of B-3. |
| **AT-10** | **Do not spec, do not build: "mine motifs from this import source."** | **REFUTED** — plan 30 §10: `_MotifMineArgs` ([`server.py:2958-2973`](../../../services/composition-service/app/mcp/server.py#L2958)) is `scope: Literal["book","corpus"]`; there is **no `import_source_id` field**. `motif_mine` mines *your own* corpus. The member motifs of a deconstructed work are written by the `analyze_reference` worker, not by mining. |

---

## 4 · The design — `arc-templates`

**Root:** `data-testid="studio-arc-templates-panel"`. Two-level: **list ⇄ detail** (the existing `ArcTemplateLibraryView` shape), plus a third top-level view for **Import & Deconstruct**. All three stay **MOUNTED** (CSS `hidden`, never a ternary unmount — the React-MVC rule; the deconstruct job poll must survive a tab switch).

```
┌ ARC TEMPLATES ─────────────────────────────────────── ⟳  ⧉  ✕ ┐
│ [ Library │ Catalog │ Import & Deconstruct ]      ⌕ search…    │  ← toolbar row1
│ tier chips: ⦿ Mine  ○ System  ○ All   genre: [ xianxia ▾ ]     │  ← row2 (Library only)
├───────────────────────────────────────────────────────────────┤
│ ▸ 逆天改命 · 18 chapters · xianxia, 爽文        [Mine]    ⋯    │
│ ▸ Hero's Journey · 12 chapters · —             [System]  ⋯    │
│ ▸ 山海遺聞 (deconstructed)  · 24 ch · ⚠ imported [Mine] ⋯    │
├───────────────────────────────────────────────────────────────┤
│ 14 templates · 3 mine · 6 system            + New   ⤓ Extract │  ← panel-foot
└───────────────────────────────────────────────────────────────┘
```

### 4.1 Library / Catalog (browse)

**Reads.** `GET /arc-templates?scope=mine|system|all` (`useArcLibrary`) · `GET /arc-templates/catalog?genre=&q=&limit=&offset=` (**new consumer** of a shipped route). ⚠ **The two routes have DIFFERENT response shapes and are NOT interchangeable** — `/arc-templates` returns `{arc_templates[], scope, limit}` and is **NOT paged** (`limit` only, no `offset`); `/arc-templates/catalog` returns `{items[], total, limit, offset}` and **is** paged ([`arc.py:106-155`](../../../services/composition-service/app/routers/arc.py#L106)). An FE that reads `.items` off the first gets `undefined`. Rows: name · `chapter_span` · `genre_tags` · **tier chip** (Mine / System / Public) · an **⚠ imported** chip when `source='imported' || imported_derived` (AT-9's honesty, at the row).

**Writes.** `+ New` → `POST /arc-templates` (owner server-stamped; 409 `ARC_TEMPLATE_CODE_EXISTS` on a duplicate `(owner, code, language)` — surface it on the `code` field, not as a toast). `⋯ → Adopt` → `POST /arc-templates/{id}/adopt` (clone-to-customize; the **only** write available on a System/Catalog row). `⋯ → Archive` → `DELETE` (soft; owner-only).

**States.** *Empty (no templates)* → the **fixed** CTA: two buttons, *Browse the catalog* + *Import a story to deconstruct* — both wired (this is the bug being replaced; render it in the draft as `Before`/`After`). *Loading* → `MotifStateBoundary skeleton="cards"`. *Error* → boundary + Retry. *System row selected* → the editor is **read-only with an `Adopt to edit` primary**, never a disabled input (a disabled field says *"you may not"*; the correct message is *"clone it first"*).

### 4.2 Detail — identity · timeline · apply · **drift**

Lifted from `ArcTemplateLibraryView`'s detail branch: `ArcTimelineEditor` (thread × chapter grid; mobile list under `sm`) + `ArcApplyPreview`. **`ArcConformancePanel` is removed (AT-7)** and replaced by:

**§ Used by (new, BE-NONE).** `GET /v1/composition/books/{bid}/arcs` (already consumed by plan-hub) → **client-side filter** on `arc_template_id === template.id`. Each row = one spec arc materialized from this template, with a **Drift** button.

**§ Drift (new, BE-NONE — the audit said this needed BE-8; it does not).**
`GET /works/{pid}/conformance?scope=arc_template_drift&arc_id=<structure_node_id>` →
`compute_arc_report(by_structure=False)`. Renders: thread-progress coverage · realized-vs-template pacing curve · structural succession flags · the §12.6 **unmaterialized (folded-away) placements** — the drop/merge report, which is the whole point (*"a motif lost to a scale mismatch is NEVER silent"*, [`arc.py:288`](../../../services/composition-service/app/routers/arc.py#L288)).

**Drift's honest empty states — all three are distinct and must not collapse into one:**

| Condition | Server | Render |
|---|---|---|
| No spec arc uses this template | *(no call made)* | *"Not applied to this book yet."* + the Apply CTA |
| The arc has no template provenance | **422 `NO_TEMPLATE_PROVENANCE`** ([`conformance.py:394`](../../../services/composition-service/app/routers/conformance.py#L394)) | *"This arc was authored directly — there is no template to drift from."* (BA13) |
| The template was deleted / is foreign | **404** (H13 uniform) | *"The source template is no longer available."* — never *"not found"* as an existence oracle |

**§ Apply.** `POST /arc-templates/{id}/apply` (PURE preview — persists nothing) → the plan (rescaled placements, roster binding, drop/merge report) → **Materialize** → `POST /works/{pid}/arc/materialize` → **then AT-6's provenance stamp.** Errors to render, not swallow: **400 `NO_CHAPTERS`** (*"materialize maps onto existing chapters — create chapters first"*), **400 `TOO_MANY_CHAPTERS`**, **400 `NO_MATERIALIZABLE_PLACEMENTS`** (render `unresolved_placements` — the user needs to see *which* motif failed to resolve), **409 `CHAPTER_ALREADY_PLANNED`** → the `replace=true` re-confirm dialog, listing the `chapter_ids` the server returned.

**§ Extract (new — BE-7a).** *Save an arc as a template*: pick a spec arc (`GET /books/{bid}/arcs`) → `code` / `name` / `language` / `visibility` → `POST /v1/composition/arcs/{node_id}/extract-template`. **409** on a duplicate `(owner, code, language)` — the engine deliberately does not swallow the `UniqueViolationError` ([`arc_apply.py:660-666`](../../../services/composition-service/app/engine/arc_apply.py#L660)); surface it on the `code` field.

**§ Suggest (new — BE-7b).** *Suggest an arc for this premise* → `POST /arc-templates/suggest` → ranked candidates + the **`match_reason` breakdown the engine already returns** (do not throw it away — it is the only explanation the user gets for a ranked list). Each candidate deep-links to its detail view.

### 4.3 Import & Deconstruct (the section — 拆文)

Four steps, one column, every state rendered.

1. **Sources.** `GET /import-sources` → list (title · created_at · content length). `POST /import-sources` (paste or file → text; `content` **max 20 000 chars** — [`import_source.py`](../../../services/composition-service/app/routers/import_source.py) `StringConstraints(max_length=20000)`; the FE must **count and block at 20 000 before submitting**, not let the server 422 an essay). `DELETE /import-sources/{id}` (hard delete — say so; there is no restore).
2. **Configure.** `arc_hint` (free text) · `language` (the source's language — a **first-class dedup/embed key**; an imported `zh` work tagged `en` is a later re-key migration, so make the control prominent, not a footnote) · `use_web` toggle · **`model_ref` — REQUIRED (AT-8)**, via `ModelPicker`.
3. **Cost gate (AT-5).** `mcpExecute('composition_arc_import_analyze', { args: {…} })` → `CostConfirmCard` renders `{estimate.estimated_usd}` → **Confirm** → `POST /actions/confirm?token=…` → `{job_id}`.
   ⚠ **The MCP tool takes a single Pydantic `args` model, so the bridge body must NEST the fields under `args`** — a flat body fails arg-validation. This is verified live and commented at [`motif/api.ts:251-253`](../../../frontend/src/features/composition/motif/api.ts#L251). Copy the nesting; do not "clean it up".
4. **Run.** Poll **`GET /v1/composition/motif-jobs/{job_id}`** (the owner-scoped read — **AT-11**, one leg of `W0-BE1`) to terminal → on `completed`, invalidate `['composition','arc-templates']` and **deep-link the new template into the detail view**. On `failed`, render `job.result.error` verbatim. ⚠ **Not `GET /v1/composition/jobs/{id}`** — it gates on a Work this job does not have (§0.1). ⚠⚠ **And handle the confirm's own failure loudly**: before `W0-BE1` the `POST /actions/confirm` itself **500s** and there is no `job_id` to poll at all. A `catch`-into-spinner is how that 500 hides — surface it.

**States:** no sources (empty + paste box) · over-length paste (blocked, with the count) · no model (the `AddModelCta` empty state — **X-1 must be fixed or this button destroys the workspace**) · estimate pending · **awaiting confirm** (the spend has NOT happened) · running (elapsed + cancel-is-not-available, said honestly) · completed (→ the new template) · failed (the worker's own message) · **402** from `_precheck_or_402` (insufficient balance → deep-link `usage`).

**Copyright, rendered not buried (§12.6 / B-3).** The section states, in the UI: *"The raw text stays private to you and is never shared. Only the derived abstract structure can be published — and publishing strips the source reference."* This is not decoration: `import_source` has **no `visibility` column by construction** ([`migrate.py:961-969`](../../../services/composition-service/app/db/migrate.py#L961)), and AT-9's trigger enforces the strip.

---

## 5 · Backend prerequisites — the contract

| # | Route | Status | Request | Response | Errors | Size |
|---|---|---|---|---|---|---|
| — | `GET /v1/composition/arc-templates` | ✅ **EXISTS** | `?scope=mine\|system\|all&genre&q&language&status&limit` — **NO `offset`** | **`{arc_templates[], scope, limit}`** — ⚠ *not* `{items,total}` | — | — |
| — | `GET /v1/composition/arc-templates/catalog` | ✅ **EXISTS** (0 FE consumers) | `?genre&q&language&sort&limit&offset` (paged) | **`{items[], total, limit, offset}`** — allow-listed public projection (B-3) | — | — |
| — | `GET\|POST\|PATCH\|DELETE /v1/composition/arc-templates[/{id}]` | ✅ **EXISTS** | PATCH takes **`If-Match: <version>`** | `ArcTemplate` | 409 `ARC_TEMPLATE_CODE_EXISTS` · 409 `…PUBLISH_LIMIT_REACHED` · **412 `ARC_TEMPLATE_VERSION_CONFLICT`** (body carries `current`) · 404 H13 | — |
| — | `POST /v1/composition/arc-templates/{id}/adopt` · `/apply` | ✅ **EXISTS** | `apply` = PURE preview | `ArcTemplate` · `ArcApplyPlan` | 404 H13 | — |
| — | `POST /v1/composition/works/{pid}/arc/materialize` | ✅ **EXISTS** | `{arc_template_id, roster_bindings, replace, idempotency_key}` | `{…, scene_ids[], applied}` | 400 `NO_CHAPTERS` / `TOO_MANY_CHAPTERS` / `NO_MATERIALIZABLE_PLACEMENTS` · 409 `CHAPTER_ALREADY_PLANNED` | — |
| — | `POST\|GET\|DELETE /v1/composition/import-sources[/{id}]` | ✅ **EXISTS** (0 FE consumers) | `{content ≤20000, title, project_id?}` | row / `{import_sources[]}` | 404 `IMPORT_SOURCE_NOT_FOUND` (uniform H13) | — |
| — | `GET /v1/composition/works/{pid}/conformance?scope=arc_template_drift&arc_id=…` | ✅ **EXISTS** (0 FE consumers) — **the audit said this needed BE-8; it does not** | `arc_id` = **`structure_node.id`** | the coarse arc report | **422 `NO_TEMPLATE_PROVENANCE`** · 404 H13 · 403 | — |
| — | `POST /v1/composition/books/{bid}/arcs` | ✅ **EXISTS** (0 FE consumers) — **AT-6's provenance stamp** | accepts `arc_template_id` + `template_version` | `StructureNode` | 404 H13 · depth-guard 400 | — |
| — | `POST /v1/composition/actions/confirm?token=…` | 🔴 **EXISTS, and for `arc_import` / `motif_mine` it returns HTTP 500 AT HEAD** (§0.1) — the enqueue raises `ReferenceViolationError` and nothing catches it; the confirm token is burnt (retry → 409). **The audit's *"BE: NONE"* for `G-IMPORT-DECONSTRUCT` rests on this confirm working. It does not.** Fixed by **`W0-BE1`**. | token in the **query**; identity = the Bearer JWT | `{outcome:'action_accepted', job_id, poll}` ⚠ the `poll` value (`composition_get_mine_job`) is a **dangling pointer** until `W0-BE1` lands | 400 `action_error` · **402** (precheck) · 🔴 **500 (today)** | — |
| — | ~~`GET /v1/composition/jobs/{id}`~~ **as the deconstruct poll** | 🔴 **WRONG ROUTE — but it is NOT where the bug bites.** It gates on `job.project_id`, so it could never serve a Work-less job. ⚠ **Correction:** an earlier draft called this *"the"* defect (*"404s on this job, always"*). **It is never reached** — the confirm 500s first and the job row is never written (§0.1). Poll **`GET /motif-jobs/{id}`** instead. | — | — | (unreachable at HEAD) | — |
| **BE-7c** *(→ **`W0-BE1`**)* | `GET /v1/composition/motif-jobs/{job_id}` — **one leg of the WORK-LESS JOB LANE** | 🔴 **RE-SCOPED + RE-SIZED + RE-WAVED 2026-07-13. BUILT IN WAVE 0 as [`W0-BE1`](../../plans/2026-07-13-studio-wave-0-foundations.md) — not here, and no longer Wave 3.** (**AT-11**) | path `job_id` | the `generation_job` row (`{status, result, cost, …}`) — `project_id`/`book_id` may be **`null`** | 404 **H13 uniform** when the row is missing **or not the caller's** (`created_by != user` — no existence oracle) | ~~XS~~ → **S/M** *(schema side effect)* — 🔴 **THIS ROW USED TO SAY: *"XS — a `GenerationJobsRepo.get` + an owner gate … unbreaks mine, arc-import and the deep-conformance job in one route."* IT DOES NOT.** An owner-scoped **read** cannot resurrect a row that was **never inserted** — and it would **ship green** over a still-broken path, because its test would seed the row with a raw `INSERT` the **producer can never produce** (`fixtures-can-seed-a-field-the-writer-never-sets`). **The read route is one leg of seven**, and the leg that actually stops the 500 is **the writer**.<br><br>**The lane, in full:** **(a)** DDL — `generation_job.project_id`/`.book_id` `DROP NOT NULL` + a **both-or-neither shape CHECK** + a partial owner index · **(b)** **`create_unbound()`** — a plain INSERT, no `FROM composition_work` (**do NOT touch `create()`**: the hot path for every draft) · **(c)** `GenerationJob.project_id`/`.book_id` → `UUID \| None` · **(d)** 🔴 **`_enqueue_motif_job` — DELETE the `uuid4()` synthetic pid**, branch to `create_unbound()` when `project_id is None` · **(e)** this read route (owner gate on `created_by`, **not** a book gate — a Work-less job has no book) · **(f)** `composition_get_mine_job` — drop the un-knowable `project_id` arg · **(g)** tests **forced through the producer** (`POST /actions/confirm` → assert the row exists → read it back). ⚠ **Do NOT "fix" this by back-filling a real or phantom `project_id`** — a mine/import is genuinely not Work-bound; the row's scope key is its **owner**.<br><br>🔴 **WHY IT MOVED TO WAVE 0:** the defect fires **today**, on the live legacy page, and it is the PO's CRITICAL class. `W0-BE1` carries all seven legs; the build detail is written once, verbatim, in [`wave-3-motif`](../../plans/2026-07-13-studio-wave-3-motif.md) `3a-1` (a)–(d). **Build from the Wave-0 plan; do not re-derive it or fork a second DDL.** Wave 3 (3a) **verifies** it and ships the first GUI consumer (⛏ Mine); **this wave (4) verifies and consumes it** for 拆文. |
| **BE-7a** | `POST /v1/composition/arcs/{node_id}/extract-template` | 🔨 **MUST BUILD** | `{code, name, language='en', visibility='private'\|'unlisted'}` | `{success, outcome:'extracted', template_id, member_chapter_node_ids[], layout_placements, pacing_chapters}` | **409** duplicate `(owner, code, language)` · 404 H13 (VIEW on the arc's book, derived from the **ROW**) | **XS** — a thin wrapper over `extract_template_from_arc` ([`arc_apply.py:652`](../../../services/composition-service/app/engine/arc_apply.py#L652)); mirror the MCP handler at [`server.py:4643-4669`](../../../services/composition-service/app/mcp/server.py#L4643) verbatim, including the `UniqueViolationError` → 409 map |
| **BE-7b** | `POST /v1/composition/arc-templates/suggest` | 🔨 **MUST BUILD** | `{project_id, premise?, genre?, limit=5, detail='summary'\|'full'}` | `{candidates:[{arc_template, score, match_reason}], …meta}` | 404 H13 (VIEW on the Work's book) | **XS** — thin wrapper over `MotifRetriever.retrieve_arcs`; mirror [`server.py:2287-2320`](../../../services/composition-service/app/mcp/server.py#L2287). Keep `detail` (Context Budget Law §6b) |
| **BE-8** | **PARKED — its own slice, AFTER the panel ships.** Un-stub the **agent's** two tools. | 🔨 **AGENT PARITY ONLY** | — | — | — | **S (was M).** `composition_arc_template_drift` → point it at the **already-shipped** `compute_arc_report(…, by_structure=False)` the REST route uses (i.e. *implement `build_template_drift` as a call into the orchestrator*, do not write a second engine). `composition_arc_apply` → `apply_arc_to_spec` is genuinely unwritten (rescale + roster-bind + pacing→tension + ledger, onto `structure_node`) — that half stays **M** |

**Gateway:** **zero changes.** `gateway-setup.ts:354`'s composition `pathFilter` is `(p) => p.startsWith('/v1/composition')` — a new composition route is auto-proxied. **Do not touch the BFF** (AT-3/AT-4 avoid the allowlist entirely).

**OpenAPI:** add BE-7a/BE-7b to `contracts/api/` (specs 23 and 24 both left this undone — do not compound it).

---

## 6 · Registration checklist (GG-8) — exact files, in order

The two machine guards are **GREEN with zero drift at HEAD `9262ed53e` (py enum 57 == contract enum 57 == openable 57)**. This panel moves all three by **+1, in lockstep**. ⚠ **Assert the DELTA and the three-way equality — never the literal `58`.** Waves 1–3 land **7** panels before this wave starts (`quality-canon-rules`, `quality-corrections`, `quality-heal`, `progress`, `arc-inspector`, `motif-library`, `quality-conformance`), so the baseline here is **64**, not 57. Here is exactly how each guard stays green.

| # | File | Change |
|---|---|---|
| 1 | `frontend/src/features/studio/panels/ArcTemplatesPanel.tsx` | **NEW.** Root `data-testid="studio-arc-templates-panel"`. Composes the lifted `motif/components/Arc*` + the new `ImportDeconstructSection`. Book/Work resolution via the existing `useWork()` gate (mirror `QualityHubPanel`'s Work-less state — an arc template library is user-tier and **must still browse with no Work**; only Apply/Extract/Drift need one). |
| 2 | `frontend/src/features/studio/panels/catalog.ts` | One `STUDIO_PANELS` row: `{ id: 'arc-templates', component: ArcTemplatesPanel, titleKey: 'panels.arc-templates.title', descKey: 'panels.arc-templates.desc', category: 'storyBible', guideBodyKey: 'panels.arc-templates.guideBody' }`. **`category` is MANDATORY** (`panelCatalogContract.test.ts` reds without it) and **`storyBible` is already a member of `CATEGORY_ORDER`** ([`useStudioCommands.ts:20-22`](../../../frontend/src/features/studio/palette/useStudioCommands.ts#L20)) — so **X-2 does not block this panel**, but X-3's `guideBodyKey` assertion does: ship the key. |
| 3 | `frontend/src/i18n/locales/en/studio.json` | `panels.arc-templates.title` / `.desc` / `.guideBody`. |
| 4 | `frontend/src/i18n/locales/{ar,bn,de,es,fr,hi,id,ja,ko,ms,pt-BR,ru,th,tr,vi,zh-CN,zh-TW}/studio.json` | Same 3 keys × 17 locales — **`python scripts/i18n_translate.py`**, never hand-written. Plus the panel's own `composition` namespace strings (the lifted `motif.arc.*` keys already exist — **reuse, do not re-key**). |
| 5 | `services/chat-service/app/services/frontend_tools.py` | **Two edits** in `UI_OPEN_STUDIO_PANEL_TOOL`: (a) append `"arc-templates"` to the `panel_id` **enum** (~line 402); (b) append a clause to the tool **description** prose (~403-481) — that gloss is the model's only hint. Proposed: *"'arc-templates' = the arc-template library — browse/adopt multi-chapter arc structures, apply one onto this book, save one of your arcs as a template, or import a reference story and deconstruct it (拆文) into a reusable arc."* |
| 6 | `contracts/frontend-tools.contract.json` | **NEVER hand-edit — regenerate:** `cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py`; **commit the regenerated JSON in the SAME commit** as steps 2 + 5. |
| 7 | `frontend/src/features/studio/host/studioLinks.ts` | *(cond.)* Add a deep-link resolver so `?panel=arc-templates&template=<id>` opens the detail view in-dock. Needed by the deconstruct job's completion hand-off (§4.3 step 4). |
| 8 **(MANDATORY — X-4)** | `frontend/src/features/studio/agent/handlers/arcEffects.ts` | 🔴 **NOT NEW — [`32`](32_arc_inspector.md) (Wave 2) CREATES this file** with a single broad `/^composition_arc_/` registration. **EXTEND its handler body** (add `['composition','arc-templates']` to the invalidation set alongside its `['plan-hub']` + `['composition','arcs', bookId]`). **Do NOT add a second `registerEffectHandler` for an overlapping `composition_arc_*` pattern:** `matchEffectHandlers` ([`effectRegistry.ts:45`](../../../frontend/src/features/studio/agent/effectRegistry.ts#L45)) returns **every** match and `runEffectHandlers` awaits **all** of them — a second registration double-fires on every arc write and gives one concept two homes. The only *new* tool names this wave introduces to the pattern are `composition_arc_apply` / `_extract_template`, and the broad `/^composition_arc_/` already covers them. *(If Wave 2 has somehow not landed, create the file exactly as 32 §6 step 8 specifies — one file, one pattern.)* ⚠ Also **delete the now-FALSE comment** at `useStudioEffectReconciler.ts:10` (X-4), **if Wave 1 has not already.** |
| 9 | `frontend/src/features/studio/onboarding/tours.ts` | *(skip)* — not a role-tour step in v1. |

**Verify (all four green — the first two are the drift-locks):**
```
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
cd frontend && npx vitest run \
  src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
  src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
  src/features/studio/palette/__tests__/useStudioCommands.test.ts \
  src/features/chat/nav/__tests__/frontendToolContract.test.ts
```
**Do NOT touch:** `StudioDock.tsx`, `StudioFrame.tsx`, `useStudioCommands.ts`, `UserGuidePanel.tsx` (all derive from `catalog.ts`); `studioUiNav.ts` / `useStudioUiToolExecutor.ts` (panel-id-agnostic).

---

## 7 · Agent surface

**MCP tools that drive this domain (all exist; none is new):**

| Tool | Tier | State at HEAD | After this wave |
|---|---|---|---|
| `composition_arc_suggest` | R | live, **no REST** | live + a REST twin (BE-7b) |
| `composition_arc_extract_template` | A | **live** (engine at `arc_apply.py:652`), no REST | live + a REST twin (BE-7a) |
| `composition_arc_import_analyze` | W (paid, async) | live + **already BFF-allowlisted** | unchanged — the GUI rides the same tool |
| `composition_get_mine_job` | R | 🔴 live + allowlisted, but **it has never had a row to read** — the mine/import confirm 500s before any job is written (§0.1), and even given a row it demands a `project_id` the caller cannot know | the GUI polls the owner-scoped **`GET /motif-jobs/{job_id}`** (AT-11). Making the tool itself usable (drop the `project_id` arg → gate on `created_by`) is **leg (f) of [`W0-BE1`](../../plans/2026-07-13-studio-wave-0-foundations.md)**, so the agent gets the same fix — but the leg that actually unbreaks it is **(d), the writer** |
| `composition_arc_apply` | A | 🔴 **`_pending_engine` STUB** | still stubbed → **BE-8** |
| `composition_arc_template_drift` | R | 🔴 **`_pending_engine` STUB** | still stubbed → **BE-8** |
| `composition_arc_{list,get,create,update,delete,restore}` | R/A | live. ⚠ **Their REST twins are NOT all unconsumed** — `plan-hub/api.ts` already calls `GET /books/{bid}/arcs` (:22), `POST /arcs/{id}/move` (:196) and `POST /books/{bid}/arcs/assign-chapters` (:248). **`POST /books/{bid}/arcs` (create) is the only one with 0 FE consumers.** | `create` gains its **first** FE consumer (AT-6). The *Used by* list and AT-6's chapter link **reuse `planHubApi`** — they do not fork a second caller (§9) |

**Lane-B effect handlers (X-4):** `arcEffects.ts` per §6 step 8. Without it, **every agent write to an arc or a template leaves this panel stale** — the exact class X-4 exists to close.

### The INVERSE gap — the agent cannot do what the human can, and this wave WIDENS it before it closes it

`composition_arc_apply` and `composition_arc_template_drift` are honest-failure stubs ([`server.py:4556-4564`](../../../services/composition-service/app/mcp/server.py#L4556) — they return `{success:false, error:"arc engine not yet integrated…", pending_dependency}`, which is correct behavior and **not** a silent no-op). But the consequence is real and must be stated:

> **After this wave ships, a human can apply an arc template and read its drift from a panel; an agent asked to do the same gets a refusal.** That is GG-2 (the inverse law) — a defect, tracked, not hidden.

**BE-8 closes it, and is deliberately sequenced AFTER the panel** because (a) the panel has **zero** dependency on it (§0), and (b) BE-8's two halves have very different costs: `build_template_drift` is now **S** (delegate to the shipped `compute_arc_report`), while `apply_arc_to_spec` is **M** (a genuine engine: rescale placements onto chapters, bind the roster once, write pacing into scene tension, emit the `motif_application` ledger — onto `structure_node`, which the human's `materialize` never touches).

---

## 8 · Compliance — tenancy · settings · OCC · cost gates

**Tenancy (CLAUDE.md User Boundaries).**

| Table | Tier | Scope key | Enforcement |
|---|---|---|---|
| `arc_template` | **System** (`owner_user_id IS NULL`) **+ Per-user** | `owner_user_id`; `UNIQUE(owner_user_id, code, language) WHERE owner_user_id IS NOT NULL` + `UNIQUE(code, language) WHERE owner_user_id IS NULL` ([`migrate.py:949-953`](../../../services/composition-service/app/db/migrate.py#L949)) | `PATCH`/`DELETE` are **owner-filtered in the repo** ⇒ a System row 404s for a regular user. **The GUI must never render an edit affordance on a System row** — it renders *Adopt to edit*. **No `book_id`, no `book_shared` — there is no book tier (AT-2).** |
| `import_source` | **Per-user, structurally un-shareable** | `owner_user_id NOT NULL`; **no `visibility` column, by construction** ([`migrate.py:961-969`](../../../services/composition-service/app/db/migrate.py#L961)) | Every route is owner-scoped; a foreign/missing id is the **same** uniform H13 404 (no existence oracle). The confirm effect **re-checks the owner** ([`actions.py:683-688`](../../../services/composition-service/app/routers/actions.py#L683)) — a token is not a capability. |
| `structure_node` (AT-6's write) | **Per-book** | `book_id` (BA8) | `POST /books/{bid}/arcs` gates EDIT on the book; every by-id arc tool derives the book from the **ROW** (`_arc_or_deny`), never a body-supplied `book_id`. |

**Settings (SET-1..8).** **This panel introduces ZERO new settings and no env flag.** The one configurable thing is the deconstruct `model_ref` — a **per-user BYOK choice**, resolved through `provider-registry` via the existing `ModelPicker` (provider-gateway invariant: no platform model literal ever reaches the panel). Per **AT-8** the picker is **required**, and the panel renders the **effective model + source tier**; the worker's platform fallback is never allowed to be a silent hidden payer. A `capture_*`-style toggle is **out of scope** — do not invent one.

**OCC.** `PATCH /arc-templates/{id}` takes `If-Match: <version>` and returns **412 `ARC_TEMPLATE_VERSION_CONFLICT` with the server's `current` row in the body** ([`arc.py:215-229`](../../../services/composition-service/app/routers/arc.py#L215)). The panel's 412 path: **reconcile, never clobber** — show *"changed elsewhere — reloaded"*, replace the editor's baseline with `current`, keep the user's unsaved edits in the form, and re-enable Save at the new version. ⚠ The timeline grid is a **chip/select over an OCC entity** — the repo's `instant-commit-control-over-occ-entity-needs-write-serialization` memory applies: **chain the writes** (a rapid second cell edit must not race the first into a self-412) and **bind each debounced write to the template id it was started for** (`debounced-write-must-bind-its-target-entity`).

**Cost gates.** Exactly one paid action: the **deconstruct**. It goes through **`mcpExecute(propose)` → `POST /actions/confirm`** (AT-5). `POST /arc-templates/{id}/apply` and `/materialize` are **deterministic, no LLM, $0** — they must **not** be wrapped in a cost card (a fake confirmation is its own defect). Adopt is quota-bearing, not token-bearing: no cost card, but surface **409 `ARC_TEMPLATE_PUBLISH_LIMIT_REACHED`** as an informative refusal, never as a generic error.

---

## 9 · Collisions (read before editing a file)

| Risk | Rule |
|---|---|
| **Spec 33 (Wave 3) owns `motif-library`** and ports the **same** `features/composition/motif/**` tree. `ArcTemplateLibraryView` is a **child of `MotifLibraryView`'s kind-toggle** ([`MotifLibraryView.tsx:66`](../../../frontend/src/features/composition/motif/components/MotifLibraryView.tsx#L66)). | **This spec owns the ARC half; 33 owns the MOTIF half.** The kind-toggle is the DOCK-8 violation being split — after both waves, `MotifLibraryView` no longer renders `ArcTemplateLibraryView`. **Shared components (`MotifStateBoundary`, `CostConfirmCard`, `AdoptTargetModal`, `ModelRolePicker`) are LIFTED ONCE into a shared location and imported by both — never forked** (DOCK-2; `parallel fanout forks page` memory). Whichever wave lands first does the lift; the second imports. |
| **GG-4 sequencing** | `ChapterEditorPage` **must not be retired** until this wave (and 33, 36) land. Retiring it today deletes the arc-template library. |
| **Wave 0 (X-1)** | **HARD BLOCKER.** The Deconstruct section renders `ModelPicker` → `AddModelCta` on zero models. Un-fixed, that button route-navigates and **tears down the entire dockview**. Do not ship this panel before X-1. |
| **Wave 2 (`arc-inspector`, spec 32)** | Both surface `structure_node`. **32 owns arc-node CRUD**; this spec calls `POST /books/{bid}/arcs` only for **AT-6's provenance stamp**. If 32 lands first, **reuse its hook** rather than adding a second writer of the same table. |
| 🟡 **`plan-hub` / the Book-Package track (specs 22–28)** — plan 30 §9: *"Coordinate before editing `PlanDrawer.tsx` / `plan-hub`."* | **AT-6 walks straight into plan-hub's file.** `frontend/src/features/plan-hub/api.ts` ALREADY owns `listArcs` (:22), `moveArc` (:196) and `assignArcChapters` (:248). **This wave ADDS `createArc` to `planHubApi` and IMPORTS the rest — it does NOT create a rival `arcSpecApi` in `features/composition/motif/`.** Two callers of one table is the `KG↔glossary anchor` bug in miniature. We do **not** touch `PlanDrawer.tsx`. |
| **`design-drafts/`** | New file only: `screen-arc-templates.html`. Touch no existing draft. |

---

## 10 · Milestones

**M1 — the library port (BE-NONE).** `arc-templates` panel + catalog/enum/contract/i18n registration + the 3-tier browse (incl. the unconsumed `/catalog` route) + CRUD + adopt + apply-preview → materialize + **AT-6's provenance stamp** + the fixed empty state. `ArcConformancePanel` dropped (AT-7).
**DoD:** the 4 guard suites green (§6) · a Studio user creates, edits (with a forced 412 reconcile), adopts, and materializes a template **without touching `/books/:id/chapters/:id/edit`** · a **live browser smoke** proves `ui_open_studio_panel {panel_id:"arc-templates"}` mounts the dock tab.

**M2 — Import & Deconstruct (⚠ NOT BE-NONE; §0.1 corrects the audit — but the BE lands EARLIER, in Wave 0).** The section: sources CRUD + configure + the AT-5 cost gate + **the Work-less job lane (AT-11) — CONSUMED here, BUILT in Wave 0 as [`W0-BE1`](../../plans/2026-07-13-studio-wave-0-foundations.md)** (ex-BE-7c; pulled forward out of Wave 3a because the confirm **500s today** on the live page) + the completion deep-link + the AT-9 copyright/strip disclosure.

🔴 **VERIFY `W0-BE1` LANDED — do not assume, and do not "verify" it with a read-route test.** The proof is **through the producer**: a live `POST /v1/composition/actions/confirm` for `composition.arc_import_analyze` returns **200 + a real `job_id`** (not a 500), a `generation_job` row exists with `project_id IS NULL`, and `GET /motif-jobs/{job_id}` resolves it. **If Wave 0 and Wave 3 both somehow skipped it, this wave builds all SEVEN legs** (§5 BE-7c) — **not just the read route**; a read route alone ships green over a still-broken confirm (`fixtures-can-seed-a-field-the-writer-never-sets`). Check `git log` first; do not build it twice.
**DoD:** a **priced, real** 拆文 run end-to-end on a local BYOK model (`$0` spend, per the test account's lm_studio models) — paste → propose → confirm → job → **poll to `completed`** → **a new `arc_template` row visible in the Library tab.** A green unit suite does **not** satisfy this (`public-mcp-worker-carrier-live-smoke-recipe`). 🔴 **Two assertions matter, in this order:** (1) **the confirm returns 200 + a real `job_id`** — before `W0-BE1` it returns **HTTP 500** and no job is ever created (§0.1); (2) **the poll reaches a TERMINAL status**, not "it started". A spinner would hide both.

**M3 — Suggest + Extract (BE-7a + BE-7b, XS each).** The two REST wrappers + their buttons + the `match_reason` render.
**DoD:** extract an authored arc → it appears in the Library; a duplicate `code` renders the **409 on the field**. Suggest returns ranked candidates **with** their match breakdown.

**M4 — Drift (BE-NONE — this is the audit correction).** The *Used by* list + the drift view over the shipped `?scope=arc_template_drift` route, with all **three** distinct empty states.
**DoD:** materialize a template (M1) → open Drift → the report renders. An arc authored directly renders the **422 `NO_TEMPLATE_PROVENANCE`** message, **not** a spinner and not a zero.

**M5 — BE-8 (PARKED — agent parity, its own slice, after M1–M4).** `build_template_drift` → delegate to `compute_arc_report(by_structure=False)` (**S**). `apply_arc_to_spec` → the real spec-layer apply engine (**M**).
**DoD:** both MCP tools stop returning `pending_dependency`; an agent-driven apply + drift **matches the panel's output on the same arc** (the parity assertion — a differing answer means two engines, which is the bug BE-8 exists to prevent).

---

## 11 · Definition of Done

1. **All 4 registration guards green** (§6) — and the counts move **`N_before` → `N_before + 1` in lockstep** across the py enum, the contract JSON, and `OPENABLE_STUDIO_PANELS`. A count that moves in only two of three is the drift the guards exist to catch. ⚠ **Assert the delta, not a literal** (§6): 57 is HEAD's count, not this wave's baseline.
2. **`panelCatalogContract.test.ts`** asserts `arc-templates` has a `category` **that is a member of `CATEGORY_ORDER`** (X-2's new assertion) **and** a non-empty `guideBodyKey` (X-3's).
3. **Unit/component tests** for: the 412 reconcile path · the three drift empty states · the 20 000-char block · the required-model gate (a Deconstruct with no `model_ref` must be **impossible to submit**, not merely warned) · the four materialize error codes · **AT-6's `assigned`-count assertion** (an `assigned: 0` response must render an ERROR, not a checkmark — a test that only asserts "the call was made" cannot catch a silent no-op: `inject-at-chokepoint proves nothing`).
4. **Backend tests** for BE-7a/BE-7b/**BE-7c (`W0-BE1`)**: grant gating (VIEW derived from the **ROW**), the H13 uniform 404, the 409 duplicate-code map. 🔴 **BE-7c specifically — THE TEST MUST GO THROUGH THE PRODUCER:** drive a real **`POST /actions/confirm`**, assert it returns **200 + a `job_id`** (it returns **500** at HEAD), assert the `generation_job` row exists with **`project_id IS NULL`** *(NOT a synthetic uuid — the fix **removes** the synthetic pid)*, then read it back. A test that raw-`INSERT`s the job row and exercises only the read route **proves nothing** — it green-lights a still-500ing confirm (`fixtures-can-seed-a-field-the-writer-never-sets`). Plus: a job owned by user A is a **uniform 404** for user B (owner gate, no existence oracle); and the **both-or-neither shape CHECK** rejects a half-bound row.
5. 🔴 **LIVE BROWSER SMOKE (mandatory — `agent-gui-loop-needs-live-browser-smoke-not-raw-stream`).** Playwright, against the **baked `:5174` nginx build or `vite dev :5199`** — *not* a curl script, and *not* a unit suite:
   - `ui_open_studio_panel {panel_id:"arc-templates"}` from the agent chat → **a dock tab appears** (this is the assertion that a green contract test cannot make);
   - paste a reference text → configure a **local BYOK** model → Propose → **the cost card renders a real estimate** → Confirm → poll → **a new arc template appears in the Library tab**;
   - open it → Apply-preview → Materialize → **Drift renders a report** (this transitively proves AT-6's provenance stamp actually landed — a drift view that renders `NO_TEMPLATE_PROVENANCE` here means AT-6 silently no-op'd);
   - assert **no dock teardown** at any point — in particular after touching the model picker's zero-model state (the X-1 regression guard).
   Precedent: `studio-compose.spec.ts` / `studio-palette.spec.ts`. Specs 24 (H8.2) and 15a both **named** this DoD and **skipped** it. This one does not.
6. **A cross-service live-smoke token** in the VERIFY evidence — BE-7a/BE-7b are composition-only, but the deconstruct path crosses **frontend → BFF → ai-gateway → composition → worker**. `live smoke: <one-liner>` or an explicit deferral row.
7. **SESSION_HANDOFF updated**, and the deferred rows this wave absorbs are moved: `D-ARC-TEMPLATE-CRUD-GUI` → **cleared by M1–M4**; `D-ARC-APPLY-MCP-WRAPPER` → **re-scoped to M5 (BE-8) and amended** — its "the drift view needs a new engine" premise is **false** (§0).
   **New rows raised by this spec: NONE.** *(Cross-spec sweep, 2026-07-13 — both candidates were withdrawn as duplicates:)*
   - ~~`D-ARC-CONFORMANCE-FE-ARGS-DRIFT`~~ — **withdrawn.** [`33`](33_motif_studio.md) §1.1 already owns this as **M-BUG-4** (the `arc_template_id` → `arc_id` BA4 drift, dead on **both** transports) and **fixes it in 3c**, which lands **before** this wave. Filing a deferred row for a bug an earlier wave closes is tracking debt that does not exist (`debt-batches-list-is-stale-verify-first`). Cite 33's M-BUG-4; do not mint a row.
   - ~~`D-MOTIF-JOB-POLL-404`~~ — **withdrawn, and its NAME was wrong.** §0.1's fifth find is real, but it is **not a poll 404** (it is a **500 at confirm**) and it is **not deferred work**: it is the Work-less job lane, **built in Wave 0 as [`W0-BE1`](../../plans/2026-07-13-studio-wave-0-foundations.md)** (ex-BE-7c; pulled forward out of Wave 3a because it fires today). By the time this wave starts it is **already closed**. **Verify it through the producer** (green confirm → real `job_id` → resolving poll); do not re-file it, and do not "re-fix" it with a read route.
8. **Plan 30 is AMENDED, not silently contradicted.** §5.2's `G-IMPORT-DECONSTRUCT` row says **"BE: NONE"**; §0.1 proves that false. Write the correction **into plan 30's row** (one line, citing §0.1) rather than leaving two documents that disagree — a stale audit row is what produced this wave's other three misestimates.

---

## 12 · Open questions / Deferred

| # | Question | Disposition |
|---|---|---|
| **OQ-1** | Should AT-6 stamp provenance by **creating** a `structure_node`, or should `materialize` do it **server-side** (one transaction)? | **FE for v1, and say why:** a server-side stamp means editing `materialize`, which is `plan.py`'s 130-line commit path shared with decompose — a change with a blast radius far beyond this wave. The FE stamp is 2 calls against 2 shipped routes. **Revisit in BE-8/M5**, where `apply_arc_to_spec` will own the transactional version and the FE stamp should then be **deleted, not left as a second writer.** ⚠ Record it as debt the moment M1 lands, or it becomes a permanent duplicate writer. |
| **OQ-2** | AT-6 creates a spec arc per materialize. What if the user materializes the **same** template twice (`replace=true`)? | **v1: match on `(book_id, arc_template_id)` and PATCH the existing node** rather than creating a second one — `PATCH /arcs/{node_id}` accepts `arc_template_id`/`template_version` ([`structure.py:54,59`](../../../services/composition-service/app/db/repositories/structure.py#L54)). **UNVERIFIED:** whether `materialize`'s `idempotency_key` replay path should suppress the stamp entirely. **Decide with a test before M1 ships**, not after. |
| **OQ-3** | The suggest route's `premise` — where does it come from? | The Work's premise is not a first-class field on `composition_work`. **v1: a free-text box, seeded from the book's `summary`** (`book-settings` owns it). A dedicated `premise` field is a `composition_work.settings` question and belongs to **Wave 6 / G-WORK-SETTINGS**, not here. |
| **OQ-4** | `import_source.content` is capped at **20 000 chars** — a real novel is 100×–1000× that. Is deconstructing a 20k excerpt actually useful? | **UNVERIFIED — a product question, not a code one.** The cap is in the router's `StringConstraints`, and the worker chunks across "the map rails". **Flag it to the PO at M2's POST-REVIEW with a real run's output**: if a 20k excerpt yields a thin template, the fix is a **chunked multi-part import source** (a schema change) — **defer gate #2 (large/structural)**, not something to smuggle into this wave. |
| **OQ-5** | `ArcConformancePanel`'s two dead calls (§0) — who fixes them? | **Spec 33 (Wave 3 / `quality-conformance`).** Handed over in writing here. **New deferred row: `D-ARC-CONFORMANCE-FE-ARGS-DRIFT`** — *"`motifApi.arcConformance` + `arcConformanceRunPropose` still send `arc_template_id`; BA4 retargeted the route + the tool to `arc_id` (a `structure_node`). Both calls are dead at HEAD. Owner: spec 33."* This is a **new finding**, not in plan 30's §3.3 list of three. |
| **OQ-6** | Does an arc template need a **book-shared** tier (like `motif`'s `book_shared`)? | **NO for v1, and it is not a gap:** `arc_template` has **no `book_id` column** — a book tier would be a **schema change plus a tenancy design** (who may edit a shared arc? the E0 grant model says EDIT-grantees — that is motif's answer and it needed a trigger). **Defer gate #2.** Collaborators share arc structure today by **publishing + adopting**. Say so in the User Guide so it does not read as an omission. |

