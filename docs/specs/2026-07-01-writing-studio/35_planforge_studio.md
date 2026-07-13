# 35 · PlanForge made human — the Pass Rail + planner repair

> **Status:** 📐 DRAFT — buildable. Written 2026-07-13 against HEAD `9262ed53e`. **ADVERSARIALLY REVIEWED 2026-07-13** — the review found **five defects in this spec's own first draft** (a re-read of `PASS_REGISTRY`, `_review_pass`, and `documents/types.ts` refuted them); all five are fixed in place and recorded as **F-P10 · F-P11 · F-P12** in §2 + the corrected §4.1. Every claim below was verified by opening the file; nothing is inherited from a doc, a handoff note, or the audit's own summary. **Three defects the audit did not find are recorded in §2 (F-P3, F-P4, F-P5) — two of them are load-bearing.**
> **⚠ The first draft of this spec got the dependency graph backwards** (it drew `world` as runnable and `beats` as blocked; the registry says the exact opposite). That is why §4.1 now carries the **dependency table read from the registry**, and why no number in the mock or the spec is hand-computed. *Nothing in this file may be trusted against `PASS_REGISTRY` — read the registry.*
> **Type:** FS. One new panel (`plan-passes`) + a repair of the existing `planner` panel (no new id) + 4 backend routes + 2 backend truth-fixes + contract hygiene.
> **Size:** **L** (13+ logic changes · side effects: 4 new REST routes, 2 changed response contracts, 2 JSON-schema contracts, 1 new panel id across 6 registration files).
> **Closes:** **G-PLANFORGE-PASS-RAIL** (P0, L) · **G-PLANNER-REPAIR** (M, PARTIAL) — [`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md) §5.1, §5.3.
> **Wave:** **5** of plan 30 (§7). **Also folds in:** spec [`27`](27_planforge_v2_compiler.md)'s **B1** (the `planner_state.schema.json` POC-fixture taint) and **B2** (the missing `plan_pass_artifacts.schema.json`) — contract-hygiene debt in the same files.
> **Absorbs deferred row:** `D-PLANFORGE-GUI-AUDIT` — **amended: its sub-gap 1 (the `arc_id` text box) is STALE, already fixed by `9c685c28a`. Do not re-do that work.**
> **LAW upstream:** [`27_planforge_v2_compiler.md`](27_planforge_v2_compiler.md) (PF-1..PF-15) — this spec is 27's **F3 ("Pass Rail")**, and it re-litigates none of PF-1..PF-15. [`28_agent_native_studio.md`](28_agent_native_studio.md) AN-8 (edit discipline: one channel, one tier, one undo path per object class). [`docs/standards/dockable-gui.md`](../../standards/dockable-gui.md) DOCK-1..11 · [`docs/standards/mcp-tool-io.md`](../../standards/mcp-tool-io.md) · [`docs/standards/settings-and-config.md`](../../standards/settings-and-config.md) SET-1..8.
> **Decision prefix:** **PS-** (Pass Studio). 27 owns **PF-**; this file never re-numbers into that space.
> **Hard prerequisite:** plan 30's **X-1** (the `AddModelCta` DOCK-7 teardown). Every paid action in this spec needs a `ModelPicker`, whose empty state renders `AddModelCta` — which today is a raw `<Link to="/settings/providers">` that **destroys the dockview layout**. Shipping this panel before X-1 puts a workspace-destroying button on the Pass Rail. **Not negotiable, not deferrable.**

---

## 1 · Why this exists

**A GUI-only user's plan run is permanently stuck at `pass_cursor: 1`, with 4 of its 7 passes unreachable. Not "with difficulty" — at all.**

The PlanForge v2 compiler runs seven passes (`motifs → cast → world → beats → character_arcs → scenes → self_heal`). Two of them — **`cast`** ("who the characters ARE") and **`beats`** ("what SHAPE the story takes") — are **BLOCKING checkpoints**: the pass completes with `decision:"pending"` and the runner stops until a human accepts it ([`plan_pass_service.py:60-71`](../../../services/composition-service/app/services/plan_pass_service.py#L60)). That is PF-6, and it is the design's central safety claim.

⚠ **Precisely** (and the first draft of this spec was sloppy here — see §4.1): the user *can* still fire `beats`, because it depends only on `motifs`. But `beats` is itself BLOCKING, so it stops at its own un-clearable checkpoint. **`world`, `character_arcs`, `scenes` and `self_heal` all depend on an *accepted* `cast` — so they are unreachable, forever, without a GUI.** And `pass_cursor` (contiguous fresh **and accepted**) never leaves **1**. The dead end is real; it is just one pass wider than the headline suggests.

The only door that clears a blocking pass is `plan_review_checkpoint` / `POST …/checkpoint`. **It has no GUI.** `frontend/src/features/plan-forge/api.ts` has no `checkpoint` method, no `passes` method, no `link` method. Four REST routes — `GET …/passes`, `POST …/passes/{pass_id}/run`, `POST …/checkpoint`, `POST …/link` — are **NO-FE-CONSUMER**, all four.

So the human, who is the *only oracle* the design says can answer those two questions, is the one party who cannot answer them. The agent can. The code knows this and says so out loud — this comment sits in the shipped tool, at [`mcp/server.py:3599`](../../../services/composition-service/app/mcp/server.py#L3599):

```python
    # ⚠ THERE IS NO `force` HERE, AND THERE MUST NOT BE.
    #
    # The service and the HTTP route both take `force` — a human, at the GUI, may override the PF-5
    # gate on their own book. The AGENT may not, and the first version of this tool exposed it.
```

**The GUI it reserves that override for does not exist.** [`plan_forge.py:87`](../../../services/composition-service/app/routers/plan_forge.py#L87) really does carry `force: bool = False` on `PlanPassRequest`, and [`server.py:3619`](../../../services/composition-service/app/mcp/server.py#L3619) really does hard-wire `force=False` on the agent's call. The asymmetry the architecture was built around is implemented on the backend and unbuilt on the front. A capability deliberately reserved for a human, exercisable only by an LLM, is this repo's `silent-success-is-a-bug` law inverted: not a fake success, but a **real capability with no door**.

That is GG-1, exactly: *"the agent is an accelerant on the user's own capabilities — never the only door to them."*

**The second half — `planner` repair.** The shipped `planner` panel strands a user at the first failed validation. It renders 3–5 artifact rows as **`kind` + a truncated UUID, unclickable** ([`PlanRunView.tsx:52-57`](../../../frontend/src/features/plan-forge/components/PlanRunView.tsx#L52)); reopening a past run shows an **empty source textarea**; and the three recovery tools (`interpret`, `refine`, `handoff_autofix`) are not reachable. Two of those three have **routes AND `api.ts` methods AND zero callers** — they need *buttons only*.

---

## 2 · Investigation findings — verified against code, 2026-07-13

### F-P1 — the Pass Rail's backend is DONE. All four routes exist.

| Route | File | Shape |
|---|---|---|
| `GET …/plan/runs/{run_id}/passes` | [`plan_forge.py:236`](../../../services/composition-service/app/routers/plan_forge.py#L236) | the **DERIVED** ledger — `{run_id, book_id, genre_tags, compiled, passes[], pass_cursor, blocked_at}` |
| `POST …/passes/{pass_id}/run` | [`plan_forge.py:303`](../../../services/composition-service/app/routers/plan_forge.py#L303) | `{model_ref?, params, force}` → job envelope + the derived view. **409 `UPSTREAM_STALE` carries `blockers[]`** |
| `POST …/checkpoint` | [`plan_forge.py:275`](../../../services/composition-service/app/routers/plan_forge.py#L275) | `{approved, pass_id?, edits?}`. **409 `CHECKPOINT_REFUSED`** |
| `POST …/link` | [`plan_forge.py:256`](../../../services/composition-service/app/routers/plan_forge.py#L256) | `{target: "skeleton"\|"scene_plan"}`. **409 `LINK_REFUSED`** |

The per-pass row ([`plan_pass_service.py:306-318`](../../../services/composition-service/app/services/plan_pass_service.py#L306)) is `{pass_id, checkpoint, output_kind, depends_on[], status, decision, artifact_id, job_id, fresh, blockers[]}`. `fresh`, `pass_cursor` and `blocked_at` are **derived at serialization, never stored** (PF-3) — so the Rail never has to invalidate anything, and a re-run of a pass stales everything below it for free.

**There is deliberately NO DELETE for a pass, and this spec does not add one.** The ledger is derived from `pass_state`; a pass is un-done by **re-running it** (which re-fingerprints and stales downstream) or by **rejecting it** at its checkpoint. A "delete this pass" button would be a second, incoherent invalidation mechanism — the exact thing PF-3 exists to avoid. **PS-1: the Rail offers Re-run and Reject. It offers no Delete.**

### F-P2 — 🔴 `plan_handoff_autofix` has no REST route; artifact bodies are unreachable by ANY client

Confirmed. `handoff_autofix` is fully implemented at [`plan_forge_service.py:817`](../../../services/composition-service/app/services/plan_forge_service.py#L817) and exposed **only** as an MCP tool ([`server.py:3511`](../../../services/composition-service/app/mcp/server.py#L3511)).

Worse, and the audit stated this correctly: **there is no artifact-read path in any transport.** No REST route, and no `plan_get_artifact` MCP tool. The run detail returns `[{kind, artifact_id}]` metadata only ([`plan_forge_service.py:385-388`](../../../services/composition-service/app/services/plan_forge_service.py#L385)). **The body of the plan the user just paid an LLM to write is unreachable — by the GUI, and by the agent.**

The fix is cheap, because the repo method is already there and already correctly scoped: [`PlanRunsRepo.artifacts_by_ids(book_id, run_id, ids)`](../../../services/composition-service/app/db/repositories/plan_runs.py#L265) gates through `JOIN plan_run r ON r.id = a.run_id WHERE r.book_id = $2` — `plan_artifact` carries no `book_id` of its own, and this join **is** its tenancy boundary. A read route is a wrapper over an existing, already-review-hardened method (BE-3).

⚠ **`list_artifact_refs` is `SELECT DISTINCT ON (a.kind)`** ([`plan_runs.py:355`](../../../services/composition-service/app/db/repositories/plan_runs.py#L355)) — the run detail shows the **latest artifact per kind**, not a history. The viewer therefore shows *the current body of each kind*. It is **not** a version browser, and this spec does not pretend it is (see Open Questions OQ-4).

### F-P3 — 🔴 **NEW.** The run detail's pass ledger LIES. It disagrees with `/passes` about the same run.

**Not in the audit. Found by reading the two call sites.**

`derive_view(run, *, package_artifact_id=None)` computes each pass's freshness by re-deriving its input fingerprint. For the 5 passes with `reads_package=True` (`motifs`, `cast`, `world`, `beats`, `scenes`), the package artifact id **is one of the inputs** ([`plan_pass_service.py:180-181`](../../../services/composition-service/app/services/plan_pass_service.py#L180)):

```python
    if spec.reads_package:
        out.append(str(package_artifact_id or ""))
```

There are three call sites. Two pass the real package id:
- `pass_status` → [`plan_forge_service.py:1016`](../../../services/composition-service/app/services/plan_forge_service.py#L1016) — `derive_view(run, package_artifact_id=package.id if package else None)` ✅
- `run_pass` → [`plan_forge_service.py:1216`](../../../services/composition-service/app/services/plan_forge_service.py#L1216) — `derive_view(run_after, package_artifact_id=package_id)` ✅

And one does not:
- `_serialize_run` → [`plan_forge_service.py:383`](../../../services/composition-service/app/services/plan_forge_service.py#L383) — **`**derive_view(run)`** ❌

`_serialize_run` is what backs **`GET /runs/{run_id}`, `GET /runs` (the LIST), `POST /checkpoint`, and `PATCH /novel-system-spec`.** With `package_artifact_id=None`, the package pointer resolves to `""`, the recomputed fingerprint cannot match the one the pass recorded (which included the real package id), and so:

- every package-reading pass reports **`fresh: false`** — 5 of 7, including `motifs`, the first;
- `pass_cursor` walks `PASS_ORDER` and stops at the first non-fresh pass ([`:268-274`](../../../services/composition-service/app/services/plan_pass_service.py#L268)) ⇒ it reports **0**, always;
- `blockers[]` on every downstream pass names upstreams that are actually fine.

So `GET /runs/{id}` says *"nothing is fresh, the compiler has made zero progress"* about the very same run that `GET /runs/{id}/passes` correctly reports as five passes deep. **Two producers of the same truth, disagreeing** — the repo's `cross-service-normalization-bug-class`, inside one service.

It has not bitten anyone **only because no FE consumer reads the pass block from the run detail** — which is precisely the gap this spec closes. A Pass Rail built on `GET /runs/{id}` (the endpoint the existing `usePlanRun` hook already polls) would render every pass grey and the cursor at zero.

**And a test pins the bug in place.** [`test_genre_tags_plumbing.py:88`](../../../services/composition-service/tests/unit/test_genre_tags_plumbing.py#L88) asserts on the **source text**:

```python
    assert "**derive_view(run)" in src
```

Adding the `package_artifact_id` argument REDs that assertion. The builder must update it — and it is a lovely illustration of why source-text assertions are a bad proxy for behaviour: this one asserts the presence of the bug.

**PS-2: fix `_serialize_run` to pass the package id (BE-21), update the pinning test to assert behaviour instead of source text, and — belt and braces — the Pass Rail reads `GET …/passes`, the endpoint whose freshness is correct by construction.**

### F-P4 — 🔴 **NEW.** The `cast` checkpoint cannot be approved from a GUI, because the ledger hides the field that unblocks it.

**Not in the audit. This is the load-bearing finding — without it the Pass Rail ships an Approve button that fails 409 forever on the very first blocking pass.**

PF-7: `cast` cannot be **accepted** until its glossary seed proposal has been **applied** ([`_assert_seed_applied`, `plan_forge_service.py:686-713`](../../../services/composition-service/app/services/plan_forge_service.py#L686)). The gate reads `pass_state["cast"]["bootstrap_proposal_id"]`, fetches the proposal, and refuses unless `proposal.status == "applied"`.

The seed proposal is created **automatically by the worker** when the cast pass completes ([`job_consumer.py:209`](../../../services/composition-service/app/worker/job_consumer.py#L209) → `_propose_pass_seed`), and its id is recorded onto the pass entry ([`:215`](../../../services/composition-service/app/worker/job_consumer.py#L215)). Approving/applying it is a 3-route flow the FE **already has**: `bootstrapGet` / `bootstrapApprove` / `bootstrapApply` ([`api.ts:99-116`](../../../frontend/src/features/plan-forge/api.ts#L99)).

**But `derive_view` does not emit `bootstrap_proposal_id`.** Its per-pass row ([`plan_pass_service.py:306-318`](../../../services/composition-service/app/services/plan_pass_service.py#L306)) carries `artifact_id` and `job_id` and stops. The field is declared on the model ([`models.py:652`](../../../services/composition-service/app/db/models.py#L652)) and stored by the worker — and **returned to no client, on any transport.**

So a GUI that lists the passes, sees `blocked_at: "cast"`, and offers Approve gets:

```
409 CHECKPOINT_REFUSED — "cast cannot be accepted before its glossary seed proposal exists"
```

…with **no way to discover which proposal to apply.** The seed proposal id is a `bootstrap_proposal_id` the client cannot see, addressing a proposal the client cannot list (there is no "list proposals for this run" route — only `GET /plan/bootstrap/{proposal_id}`, which needs the id you don't have).

**This is a stored-but-never-returned field, and CLAUDE.md's own words for it are in this very file, 275 lines away:** *"a stored-but-never-returned field is indistinguishable from a dropped one"* ([`plan_forge_service.py:375`](../../../services/composition-service/app/services/plan_forge_service.py#L375), the comment justifying `genre_tags`' round-trip).

**PS-3: `derive_view` must emit `bootstrap_proposal_id`, `decided_by` and `decided_at` per pass (BE-20, XS).** All three are already on the `PassEntry` model; none is a new column. The cast card then renders the seed diff inline (`bootstrapGet` → approve → apply) and **enables Approve only once the proposal reads `applied`** — turning a permanent 409 into a two-click flow.

### F-P5 — 🔴 **NEW.** A live error message names a tool that does not exist.

`_assert_seed_applied` refuses with ([`plan_forge_service.py:702-705`](../../../services/composition-service/app/services/plan_forge_service.py#L702)):

```python
            raise ValueError(
                "cast cannot be accepted before its glossary seed proposal exists "
                "(call plan_bootstrap_seed for this pass first)",
            )
```

**`plan_bootstrap_seed` does not exist.** `grep -rn plan_bootstrap_seed services/` returns exactly one hit: this string. There is no such MCP tool, no such route, no such service method. An agent that hits this 409 will search for the tool, fail to find it, and either hallucinate a call or give up — and a human reading the 409 in a toast is sent hunting for a button that was never built.

The real producer is the worker, and the real recovery is **re-run the `cast` pass** (which re-proposes the seed; the `None`-return path at [`job_consumer.py:136-142`](../../../services/composition-service/app/worker/job_consumer.py#L136) deliberately keeps an already-applied proposal pointed at, so a re-run is a safe no-op).

**PS-4: fix the message (BE-22, XS) to name the real recovery** — *"…its glossary seed proposal is missing; re-run the `cast` pass to propose it."* A wrong error message is a bug, not a cosmetic. This one is cheaper to fix than to write a defer row for.

### F-P6 — the free win is real, and it has a trap in it

`interpret` and `refine` have routes ([`plan_forge.py:333`, `:199`](../../../services/composition-service/app/routers/plan_forge.py#L199)) **and** `api.ts` methods ([`api.ts:70-83`](../../../frontend/src/features/plan-forge/api.ts#L70)) **and zero callers**: `usePlanRun` ([`hooks/usePlanRun.ts`](../../../frontend/src/features/plan-forge/hooks/usePlanRun.ts)) exposes only `createRun / loadRun / resetRun / runSelfCheck / runValidate / runCompile`. Confirmed — no button, anywhere.

**The trap:** the FE type is wrong. [`types.ts:113-117`](../../../frontend/src/features/plan-forge/types.ts#L113):

```ts
export interface RefinePlanBody {
  model_ref: string;
  revision?: string;          // ← string
  focus_paths?: string[];
}
```

The backend expects a **dict** ([`plan_forge.py:60`](../../../services/composition-service/app/routers/plan_forge.py#L60), `revision: dict[str, Any] | None`). The dead api.ts method has been type-drifted since it was written; the first person to wire the button and pass a revision string gets a **422**, and will debug the button rather than the type. **PS-5: fix `RefinePlanBody.revision` to `Record<string, unknown>` in the same slice that adds the button.** (`interpret`'s body is correct — `user_message: string` matches.)

### F-P7 — `source_markdown` is a column the API never returns

[`plan_runs.py:23-27`](../../../services/composition-service/app/db/repositories/plan_runs.py#L23) selects `source_markdown` on every run read. `_serialize_run` ([`plan_forge_service.py:363-391`](../../../services/composition-service/app/services/plan_forge_service.py#L363)) returns `source_checksum` and **not** `source_markdown`. `PlanRunDetail` ([`types.ts:32-47`](../../../frontend/src/features/plan-forge/types.ts#L32)) mirrors that faithfully.

So "the source markdown does not resume when you reopen a run" is **not an FE bug** — the FE cannot resume what the API never sends. It is a one-line contract widening (BE-3b). The audit filed this under BE-3 (the artifact route); it is a *separate, simpler* fix and should not wait on it.

### F-P8 — there is NO cost-gate descriptor for plan passes, and inventing one is the trap

`grep "composition\." services/composition-service/app/routers/actions.py` → the descriptor set is `publish`, `generate`, `motif_adopt`, `motif_mine`, `conformance_run`, `authoring_run_{create,gate,start,resume,revert_all}`. **There is no `composition.plan_run_pass`, and no `composition.plan_*` of any kind.**

PlanForge's paid actions (`create_run` in `llm` mode, `refine`, `interpret`, `compile(run_pipeline=true)`, `run_pass`) are **Tier A with `paid=true`** — they execute directly, over their own REST routes, with an explicit `model_ref`. They are *not* Tier-W propose→confirm actions, and the shipped `planner` panel already drives four of them that way.

Plan 30's cost-gate rule says: *"any paid (LLM) action goes through propose→confirm … **never a bespoke per-action estimate route**"*. The operative clause is the second one — three invented `/actions/<name>/estimate|confirm` paths **404 in production today** (§3.3 of plan 30). **This spec invents none.**

**PS-6 — the sanctioned gate for a Tier-A `paid` action is the CALLER's own gate.** For the agent that is the chat approval card (driven by `paid=true` in `require_meta`). For the GUI it is an **explicit in-panel confirmation**: a Run-pass button that opens a confirm step naming *the pass, the model (`ModelPicker`, explicit — never a silent default), and that this spends*, and which cannot be double-fired while a job is in flight. Adding a Tier-W `composition.plan_run_pass` descriptor would give both callers a ledger-claim + precheck — but it **changes the agent's channel too**, and AN-8 is explicit: *"a reviewer finding a new confirmation convention here has found a defect."* → **OQ-1, PO decides. Not built in this spec.**

### F-P9 — `plan-passes` can be a BARE-ID panel, and therefore stays in the enum

X-12 (plan 30 §8.2) warns that a panel needing `params` (a `node_id`, a `motif_id`) is structurally **outside** the `ui_open_studio_panel` enum, the palette, and the User Guide.

**`plan-passes` escapes this.** It is **book-scoped**, and `useStudioHost()` already supplies `bookId` (the shipped `PlannerPanel` uses exactly that — [`PlannerPanel.tsx:26`](../../../frontend/src/features/plan-forge/components/PlannerPanel.tsx#L26)). The panel resolves the run itself: `GET /books/{bookId}/plan/runs` → default to the newest run that has a package, with an in-panel run picker for the rest. A `run_id` is a *selection inside the panel*, not an opening argument.

**PS-7: `plan-passes` opens on a bare id. It is palette-openable, agent-openable, and carries a `guideBodyKey`.** No `hiddenFromPalette`, no dependency on the X-12 decision.

### F-P10 — 🔴 **THERE IS NO "HOLD".** `approved:false` writes `decision="rejected"` — and that makes `blocked_at` go **NULL**.

**Found by the adversarial review, in this spec's own §4.3.** The first draft specced a *"Hold + edit"* action. **The backend has no such state.** [`_review_pass`, `plan_forge_service.py:673`](../../../services/composition-service/app/services/plan_forge_service.py#L673):

```python
        decision = "accepted" if approved else "rejected"
```

Two values. No third. So `POST /checkpoint {approved:false, pass_id, edits}` — the call the "Hold" button would make — writes **`decision="rejected"`**, with `decided_by="user"`. The consequences, none of which the first draft stated:

- `is_accepted` ([`plan_pass_service.py:213`](../../../services/composition-service/app/services/plan_pass_service.py#L213)) is `decision in ("accepted","auto")` ⇒ a rejected pass is **not accepted** ⇒ every downstream pass keeps it in `blockers[]` **forever**. The edit did not un-stick the run; it re-stuck it.
- `blocked_at` ([`:277`](../../../services/composition-service/app/services/plan_pass_service.py#L277)) matches `checkpoint=="blocking" AND status=="completed" AND decision=="pending"`. **A rejected pass does not match.** So the instant the user clicks "Hold + edit", `blocked_at` flips to **`null`** — and a Rail that renders "blocked at CAST" from `blocked_at` would announce **"nothing blocking"** about a run that cannot advance a single pass. *A panel that goes quiet at the exact moment the user needs it most.*

**PS-12 — the Rail speaks the backend's two words, and renders the third state itself.**
1. There is **no Hold**. The button is **"Save edits"** and its copy says what it does: *"Saves your edits and marks `cast` **rejected** until you approve it."*
2. **A `rejected` BLOCKING pass is a first-class rendered state** (§4.4), and it must stay visibly actionable — **the Rail must NOT derive its "you are stuck here" banner from `blocked_at` alone.** The correct predicate is `blocked_at ?? (the first BLOCKING pass whose decision is not accepted/auto)`. Derive it in the panel; do not add a column.
3. **The clean path the first draft missed entirely: `{approved:true, pass_id, edits}` in ONE call.** The gate runs **before** the write ([`:634`](../../../services/composition-service/app/services/plan_forge_service.py#L634) — *"THE GATE RUNS BEFORE ANY WRITE"*), so an approve-with-edits that the seed gate refuses mutates **nothing**. That is the primary button. Save-edits-without-approving is the secondary.

### F-P11 — 🔴 the `json-editor` seam PS-9 names **cannot carry a `runId`, and has no read-only mode**

**Found by the adversarial review. The first draft's PS-9 (*"register a `plan-artifact` JSON document provider (`{runId, artifactId} → {content, readOnly: true}`)"*) is a claim with no code behind it, on two axes.**

The shipped provider contract ([`documents/types.ts`](../../../frontend/src/features/studio/documents/types.ts)) is:

```ts
export interface DocContext { token: string; bookId: string; }   // ← no runId
open(ctx: DocContext, resourceId: string): Promise<DocumentHandle> | DocumentHandle;   // ← ONE id
```

and the call site is `openJsonDocument(type, resourceId, { token, bookId })` ([`useJsonDocument.ts:31`](../../../frontend/src/features/studio/documents/useJsonDocument.ts#L31)).

1. **One `resourceId` string, and the context carries only `bookId`.** But BE-3's route is `…/plan/runs/{run_id}/artifacts/{artifact_id}`, and [`artifacts_by_ids(book_id, run_id, ids)`](../../../services/composition-service/app/db/repositories/plan_runs.py#L265) **requires** `run_id` (`plan_artifact` has no `book_id`; the run join *is* its tenancy boundary — you cannot drop `run_id` without dropping the scope check).
2. **`readOnly` does not exist at any layer.** `grep -rn "readOnly\|editable" frontend/src/features/studio/panels/JsonEditorPanel.tsx frontend/src/features/studio/documents/*.ts` → **zero hits.** `DocumentHandle` is `update()` / `save()` / `revert()`; `JsonEditorPanel` mounts CodeMirror with ⌘S wired to `handle.save()`. **A provider whose `save()` quietly does nothing is this repo's `silent-success-is-a-bug` class, shipped** — the user edits the plan they paid for, hits ⌘S, and the panel says nothing.

**PS-9 (REWRITTEN):**
- **Composite resource id:** `resourceId = "{runId}:{artifactId}"`, split in the provider. The dock id becomes `json-editor:plan-artifact:{runId}:{artifactId}` — the panel already keys tabs by that string, so multiple artifacts open as multiple tabs for free.
- **`readOnly` must be BUILT, not assumed → FE-1 (§6).** Widen `JsonDocumentProvider` with `readOnly?: boolean`, and honour it in `JsonEditorPanel` (CM6 `editable={false}` + `readOnly` extension, hide/disable Save, no ⌘S binding). This is a **spec-12 contract widening in the same slice** — small, and the alternative is a no-op save button.

### F-P12 — the pass dependency graph is **not** the pass order, and the first draft got it backwards

`PASS_ORDER` is the *serialization* order. `depends_on` is the *dependency* graph, and they are **different**. See the table in **§4.1** — it is read straight out of [`PASS_REGISTRY`](../../../services/composition-service/app/services/plan_pass_service.py#L55) and it is the only trustworthy source. The two traps it kills:

- **`world` depends on `cast`** (`depends_on=("cast",)`) ⇒ while `cast` sits `pending`, **`world` is BLOCKED.** The first draft drew it as the runnable next pass, with the paid Run button on it. That button 409s.
- **`beats` depends only on `motifs`** (`depends_on=("motifs",)`) ⇒ with `motifs` accepted, **`beats` is RUNNABLE while `cast` is still pending.** The first draft drew it as blocked. It is the one pass that *can* run — and it is itself BLOCKING, so it stops at its own checkpoint. `blockers_for("beats")` can **only ever contain `"motifs"`** ([`blockers_for` walks `depends_on` and nothing else](../../../services/composition-service/app/services/plan_pass_service.py#L221)); an envelope naming `cast` as a blocker of `beats` is impossible.

---

## 3 · What is already built (so the estimate is trustworthy)

| Layer | State |
|---|---|
| The 7-pass compiler engine, the pass registry, dependency order, blocking classes | ✅ **Shipped** — [`plan_pass_service.py:55-87`](../../../services/composition-service/app/services/plan_pass_service.py#L55) |
| Fingerprint-derived freshness / `pass_cursor` / `blocked_at` (no dirty flags) | ✅ **Shipped**, and correct — [`:187-323`](../../../services/composition-service/app/services/plan_pass_service.py#L187) |
| The 4 Pass-Rail REST routes + their 409 envelopes with `blockers[]` | ✅ **Shipped** — [`plan_forge.py:236-330`](../../../services/composition-service/app/routers/plan_forge.py#L236) |
| `force` on the REST run route (the human override) | ✅ **Shipped** — [`plan_forge.py:87`](../../../services/composition-service/app/routers/plan_forge.py#L87) |
| `edits` deep-merge into a pass artifact → new artifact → downstream stales by derivation | ✅ **Shipped** — [`_review_pass`, `plan_forge_service.py:613-684`](../../../services/composition-service/app/services/plan_forge_service.py#L613) |
| Gate-before-write on checkpoint (a refused approve mutates nothing) | ✅ **Shipped + live-smoke-hardened** — [`:634-644`](../../../services/composition-service/app/services/plan_forge_service.py#L634) |
| `_bind_roster` — accepted cast writes `roster_bindings` onto the arc (PF-13) | ✅ **Shipped** — [`:715`](../../../services/composition-service/app/services/plan_forge_service.py#L715) |
| Glossary seed proposal auto-created by the worker; approve/apply routes + FE api methods | ✅ **Shipped** — [`job_consumer.py:209`](../../../services/composition-service/app/worker/job_consumer.py#L209), [`api.ts:94-116`](../../../frontend/src/features/plan-forge/api.ts#L94) |
| `handoff_autofix` service method (bounded refine loop, `max_rounds` 1–5) | ✅ **Shipped** — [`plan_forge_service.py:817`](../../../services/composition-service/app/services/plan_forge_service.py#L817) — **MCP-only** |
| `artifacts_by_ids` (book-scoped through the run join) | ✅ **Shipped** — [`plan_runs.py:265`](../../../services/composition-service/app/db/repositories/plan_runs.py#L265) — **no route** |
| `planner` panel: Runs list, run load, propose, self-check, validate, compile, arc **picker** | ✅ **Shipped** — the arc picker landed in `9c685c28a` ([`PlanRunView.tsx:117-124`](../../../frontend/src/features/plan-forge/components/PlanRunView.tsx#L117)) |
| Bootstrap panel (propose→approve→apply) under a compiled run | ✅ **Shipped** — [`BootstrapPanel.tsx`](../../../frontend/src/features/plan-forge/components/BootstrapPanel.tsx) |
| `interpret` / `refine` routes + api.ts methods | ✅ **Shipped** — **zero callers, no button** |
| A Planner-redesign HTML mockup (2026-07-06, 621 lines) | ✅ On disk — [`design-drafts/planforge/2026-07-06-planner-panel-redesign-mockup.html`](../../../design-drafts/planforge/2026-07-06-planner-panel-redesign-mockup.html). **Start the draft from it.** Its sub-gap 1 is now stale; sub-gaps 2/3/4 are exactly §5 of this spec. |

**The honest summary: the Pass Rail is ~85% backend-complete.** What is missing is 4 thin routes, 3 truth-fixes, and a panel.

---

## 4 · The design — `plan-passes` (the Pass Rail)

**Category:** `editor` (the same category as `planner` and `plan-hub` — the Rail is a planning surface, not a quality diagnostic). **Root:** `data-testid="studio-plan-passes-panel"`.

### 4.1 The dependency graph — **read this before drawing anything** (F-P12)

`PASS_ORDER` is the order the ledger *serializes* in. `depends_on` is what actually gates a pass. They
are **not the same**, and the first draft of this spec conflated them. Straight out of
[`PASS_REGISTRY`](../../../services/composition-service/app/services/plan_pass_service.py#L55):

| # | pass | `depends_on` | class | `output_kind` | reads package |
|---|---|---|---|---|---|
| 1 | `motifs` | — | advisory | `motif_plan` | ✓ |
| 2 | `cast` | — | **BLOCKING** | `cast_plan` | ✓ |
| 3 | `world` | **`cast`** | advisory | `world_plan` | ✓ |
| 4 | `beats` | **`motifs`** | **BLOCKING** | `beat_plan` | ✓ |
| 5 | `character_arcs` | `cast`, `beats` | advisory | `char_arc_plan` | — |
| 6 | `scenes` | `cast`, `motifs`, `beats`, `character_arcs` | advisory | `scene_plan` | ✓ |
| 7 | `self_heal` | `scenes`, `cast` | advisory | **`scene_plan`** (re-emitted — see §6.1 B2) | — |

Three consequences a builder MUST NOT get wrong:

- **`world` is gated on `cast`, not on order.** With `cast` `pending`, `world` is **BLOCKED** — its Run
  button 409s `UPSTREAM_STALE ["cast"]`.
- **`beats` is gated only on `motifs`.** With `motifs` accepted, **`beats` is RUNNABLE while `cast` is
  still pending.** It is the *only* pass that can run in the headline state — and being BLOCKING itself,
  it stops at its own checkpoint. `blockers_for("beats")` can **only ever be `["motifs"]`.**
- **`pass_cursor` is contiguous fresh AND *accepted*** ([`:259`](../../../services/composition-service/app/services/plan_pass_service.py#L259)), and
  `is_accepted` is `decision in ("accepted","auto")`. With `motifs` accepted and `cast` pending, the
  cursor is **1** — it breaks at `cast`. **Never hard-code a cursor. Render whatever the ledger derives.**

### 4.1b Layout — the headline state (`motifs` accepted, `cast` pending)

```
┌─ PASS RAIL ────────────────────────────── [run ▾] [↻] [⤢] [×] ┐
│ Run  a3f7c1e2 · llm · xianxia, cultivation      compiled ✓     │  ← run header
│ ▓▓▓░░░░░░░░░░░░░░░░░  cursor 1/7 · blocked at CAST             │  ← DERIVED. cursor breaks at
├────────────────────────────────────────────────────────────────┤    the first un-accepted pass
│ ① motifs        advisory   ✓ auto       fresh    [view] [↻]    │
│ ② cast          BLOCKING   ⏸ pending    fresh    [view] [↻]    │  ← blocked_at, highlighted
│    ┌──────────────────────────────────────────────────────┐    │
│    │  CAST — 7 characters, 3 roles bound                  │    │  ← the checkpoint CARD,
│    │  Lâm Vân · protagonist · 冷面 stoic, driven          │    │    expanded inline
│    │  …                                                   │    │
│    │  ⚠ Glossary seed: 7 new entities  [review] pending   │    │  ← PF-7 gate, surfaced (BE-20)
│    │  [Save edits] [Reject]   [ Approve ] ← disabled      │    │  ← NO "Hold" — F-P10.
│    └──────────────────────────────────────────────────────┘    │    Save edits ⇒ decision=REJECTED
│ ③ world         advisory   — not run    —        blocked ⓘ     │  ← blockers: [cast] — NOT runnable
│ ④ beats         BLOCKING   — not run    —        [run…]        │  ← depends only on motifs ⇒ RUNNABLE
│ ⑤ character_arcs advisory  — not run    —        blocked ⓘ     │  ← blockers: [cast, beats]
│ ⑥ scenes        advisory   — not run    —        blocked ⓘ     │  ← blockers: [cast, beats, char_arcs]
│ ⑦ self_heal     advisory   — not run    —        blocked ⓘ     │  ← blockers: [scenes, cast]
├────────────────────────────────────────────────────────────────┤
│ 1 of 7 · blocked at cast          [Link to spec tree ▾]        │  ← foot
└────────────────────────────────────────────────────────────────┘
```

**The story is stronger, not weaker, once the graph is right:** the GUI-only user can run exactly one
more pass (`beats`) — into a *second* blocking checkpoint they also cannot clear. Four of seven passes
(`world`, `character_arcs`, `scenes`, `self_heal`) are gated on an accepted `cast` and are therefore
**permanently unreachable without a GUI.** The cursor never leaves 1.

### 4.2 The data it reads

**One** read: `GET /v1/composition/books/{bookId}/plan/runs/{runId}/passes` (F-P3: *not* the run detail — its freshness is wrong until BE-21 lands, and even after, one producer is better than two). Plus `GET …/plan/runs` for the run picker, and `GET /plan/bootstrap/{proposal_id}` for the cast card's seed diff (needs BE-20).

Polled at 2s while any pass has an in-flight `job_id`, using the **same generation-guard pattern** as [`usePlanRun.ts:47-72`](../../../frontend/src/features/plan-forge/hooks/usePlanRun.ts#L47) — a `genRef` bump on run-switch so a stale tick cannot resurrect the previous run's ledger. Do not invent a second poll idiom.

### 4.3 The writes it offers

**The checkpoint route has TWO decisions, not three (F-P10):** `decision = "accepted" if approved else "rejected"`. Every row below maps onto one of those two, or onto `/run`.

| Action | Route | Gate |
|---|---|---|
| **Run a pass** | `POST …/passes/{pass_id}/run` `{model_ref, params, force}` | **Paid.** Explicit confirm step (PS-6) naming pass + model + spend. Disabled while any job is in flight. Disabled when `blockers[]` is non-empty (the 409 is the fallback, not the plan). |
| **Force-run a pass** | same, `force: true` | **The reserved human override.** Behind a secondary "Run anyway" affordance inside the 409 state, never the primary button. Copy names what it does: *"Run `world` against a `cast` you have not accepted. The result may contradict the plan above it."* |
| **Approve** | `POST …/checkpoint` `{approved: true, pass_id}` | Free. `decision → "accepted"`. For `cast`: **disabled until the seed proposal reads `applied`** (F-P4/BE-20). |
| **Approve WITH edits** ⭐ **the primary path** | `POST …/checkpoint` `{approved: true, pass_id, edits}` | Free. **One call.** The seed gate runs **before** the write ([`:634`](../../../services/composition-service/app/services/plan_forge_service.py#L634)), so a refusal mutates **nothing** — no half-applied edit to retry on top of itself. `edits` deep-merge → new artifact → downstream stales by derivation. The panel must **say so**: *"Approving these cast edits will stale the 4 passes below it."* |
| **Save edits (no approval)** | `POST …/checkpoint` `{approved: false, pass_id, edits}` | Free — **and it writes `decision="rejected"`.** ⚠ There is **no "hold"** (F-P10). Copy must say what it does: *"Saves your edits. `cast` stays **rejected** until you approve it — nothing below it can run."* |
| **Reject** | `POST …/checkpoint` `{approved: false, pass_id}` | Free. Same write, no edits. `decision → "rejected"`. |
| **Re-run** | `POST …/passes/{pass_id}/run` on a completed pass | Paid. Same gate. The way a pass is un-done (PS-1). |
| **Link to spec tree** | `POST …/link` `{target}` | Free. `skeleton` \| `scene_plan`. ⚠ The **service** gate for `scene_plan` is *"a `scene_plan` artifact exists"* ([`relink`, `:1053-1060`](../../../services/composition-service/app/services/plan_forge_service.py#L1053)), not "fresh + accepted". The panel may disable on the stricter client-side predicate (fresh+accepted) — but the copy must not claim the service enforces it. `skeleton` refuses with `LINK_REFUSED` if the run has no compiled package. |

### 4.4 Every state, rendered

| State | What the panel shows |
|---|---|
| **Empty — no runs** | *"No plan run for this book yet."* + a button that opens `planner` (`host.openPanel('planner')` — **never** a route hop; DOCK-7). |
| **Empty — run not compiled** | `compiled: false` from the ledger. **Say it, don't render seven tidy "pending" rows** — the service went out of its way to distinguish this ([`plan_forge_service.py:1012-1015`](../../../services/composition-service/app/services/plan_forge_service.py#L1012)): *"Absent ≠ zero."* Show *"This run has no compiled package — the passes read it. Compile it in the Planner first."* + the openPanel button. |
| **Loading** | Skeleton rows for the 7 known passes (the pass list is a **closed set** — render it from `PASS_ORDER`, never from a spinner). |
| **Pass running** | Row shows a job spinner + `job_id`; every Run button disabled; the poll is live. |
| **Blocked (409 `UPSTREAM_STALE`)** | The response's `blockers[]` is the copy: *"`world` needs `cast` (not accepted)."* ⚠ `blockers[]` is **exactly `depends_on`, filtered** — it can never name a pass that is not an upstream (F-P12). Each blocker is a **click-to-scroll** to that pass's row. Then, and only then, the "Run anyway" (force) escape. |
| **🔴 Rejected (a BLOCKING pass with `decision:"rejected"`)** | **The state the first draft had no name for (F-P10).** Reached by Save-edits or Reject. The pass reads `rejected`, `is_accepted` is false ⇒ everything downstream stays blocked — **but `blocked_at` is now `null`.** So the panel's "you are stuck here" banner MUST be derived as `blocked_at ?? (first BLOCKING pass not in accepted/auto)`, never from `blocked_at` alone, or the Rail announces *"nothing blocking"* about a run that cannot advance one pass. Row renders an amber **rejected** chip + **Approve** and **Re-run** both live. |
| **Checkpoint refused (409 `CHECKPOINT_REFUSED`)** | Render `detail.message` verbatim — the service's messages are good (and BE-22 fixes the one that isn't). For the cast-seed case, deep-link to the seed card rather than repeating the text. |
| **Stale** | A pass that is `completed` but `fresh:false` renders **struck-through freshness + an amber "stale" chip** and its Run button re-labels to **Re-run**. Stale is the compiler's normal state after an edit — it must read as *"do this again"*, never as an error. |
| **Cost-gate / paid-action-in-flight** | Confirm step (PS-6) → then a disabled rail with the in-flight pass spinning. A second click cannot double-charge. |
| **No model / BYOK empty** | `ModelPicker`'s empty state → `AddModelCta`. **⚠ This is X-1.** Until X-1 lands, that component tears the dock down. |
| **Archived run** | A run archived via BE-4 disappears from the picker; if it was the selected run, fall back to the newest remaining and toast *"That run was archived."* + an **Undo** that calls BE-4b's restore. **The copy must not say "deleted" — BE-4 is a soft-archive, and a toast that lies about permanence is what makes users afraid to use the button.** |
| **OCC** | **None.** `pass_state` has no version column and `review_checkpoint` is idempotent and last-write-wins by design ([`plan_forge_service.py:594`](../../../services/composition-service/app/services/plan_forge_service.py#L594): *"Idempotent, no LLM"*). **PS-8: this spec adds no OCC to PlanForge.** Two humans racing on the same checkpoint is not a corruption — the second decision wins, and the ledger's derived freshness makes the consequence visible. See §8. |

---

## 5 · The design — repairing `planner` (no new panel id)

Four changes to the **existing** panel. Sub-gap 1 of `D-PLANFORGE-GUI-AUDIT` (the `arc_id` text box) is **STALE — already fixed by `9c685c28a`. Do not touch the arc picker.**

### R1 — the artifact viewer (closes spec-12 cycle-gate item 5)

`PlanRunView.tsx:52-57` renders each artifact as an unclickable `<li>`. Make the row a button → `host.openPanel('json-editor', { params: { … } })`, fed by **BE-3**.

This is also the cheapest available close of [`12_json_document_standard.md`](12_json_document_standard.md)'s cycle-gate item 5 (a JSON document provider), which the KG and Translation cycles **silently skipped** — only 2 `registerJsonDocumentProvider` call sites exist repo-wide.

**PS-9 (REWRITTEN after the adversarial review — F-P11). Register a `plan-artifact` JSON document provider, but the shipped seam does NOT fit as-is:**

```ts
// documents/types.ts — what actually exists
export interface DocContext { token: string; bookId: string; }        // ← no runId
open(ctx: DocContext, resourceId: string): Promise<DocumentHandle>;   // ← ONE id
```

1. **Composite resource id.** BE-3's route needs `run_id` (`plan_artifact` has no `book_id`; the run
   join *is* its tenancy check), and the provider gets one string. ⇒ **`resourceId = "{runId}:{artifactId}"`**,
   split inside the provider. The dock id becomes `json-editor:plan-artifact:{runId}:{artifactId}` — the
   panel already keys tabs on that string, so N artifacts open as N tabs for free. Opened with
   `host.openPanel('json-editor', { params: { docType: 'loreweave.plan-artifact.v1', resourceId } })`
   ([`JsonEditorPanel.tsx:21`](../../../frontend/src/features/studio/panels/JsonEditorPanel.tsx#L21) — `{docType, resourceId}` is the params contract).
2. **Read-only must be BUILT — it does not exist → FE-1 (§6).** `grep -rn "readOnly\|editable"` across
   `JsonEditorPanel.tsx` + `documents/*.ts` → **zero hits**. `DocumentHandle` is `update()`/`save()`/`revert()`
   and the panel wires ⌘S to `save()`. **Registering a provider whose `save()` no-ops is
   `silent-success-is-a-bug`, shipped** — the user edits the plan they paid an LLM to write, hits ⌘S,
   and nothing happens and nothing says so.
3. **A provider must be REGISTERED FROM SOMEWHERE.** The registry is a module-level idempotent
   `register…()` (see [`entityDocument.ts:200`](../../../frontend/src/features/glossary/documents/entityDocument.ts#L200) — *"Idempotent — called by EntityEditorModal on mount"*).
   ⇒ **`registerPlanArtifactDocumentProvider()` is called from `PlannerPanel`'s mount** (and from
   `PassRailPanel`'s, once M4 lands). A provider defined and never registered means `openJsonDocument`
   rejects with *"unknown type"* — green in unit tests, dead in the browser.

⚠ **Why read-only at all.** There is no artifact-write route, and `edits` (the only sanctioned artifact
mutation) goes through `POST /checkpoint`'s deep-merge — the Pass Rail's Save-edits / Approve-with-edits
path, which **re-fingerprints**. A writable artifact viewer would be a **second, un-fingerprinted write
channel into the pass ledger**, which breaks PF-3's derivation. **Do not make it editable — and do not
fake it by swallowing the save.**

### R2 — source-markdown resume

Fed by **BE-3b** (`_serialize_run` returns `source_markdown`). `PlannerPanel`'s `markdown` state seeds from `plan.run?.source_markdown` on run-load — as a **derived default**, not a `useEffect` chasing a prop (the panel already does exactly this for `effectiveModelRef`, [`PlannerPanel.tsx:71-79`](../../../frontend/src/features/plan-forge/components/PlannerPanel.tsx#L71) — mirror it).

### R3 — the free win: `interpret` / `refine` / `autofix` buttons

Add to `usePlanRun`: `runInterpret(message)`, `runRefine(body)`, `runAutofix(maxRounds)`. Routes and api.ts methods exist for the first two (**zero backend**); autofix needs **BE-2**.

Placement: a **Repair** strip that appears under the self-check gaps block **only when `selfCheck.gaps.length > 0`** — the recovery tools are meaningless without a diagnosis, and an always-on row of three buttons is how a leaky abstraction gets built. Each button's copy is written for a novelist, not for the API: *"Explain what's wrong"* (interpret), *"Apply the suggested fix"* (refine), *"Fix the top gaps automatically (up to 3 rounds)"* (autofix).

**PS-5 rider:** fix `RefinePlanBody.revision: string → Record<string, unknown>` in this slice (F-P6), or the button 422s.

`interpret` and `refine` and `autofix` are all **paid** — same PS-6 gate as §4.3.

### R4 — archive a failed run (**and restore it**)

Fed by **BE-4 + BE-4b**. A row action in `PlanRunsListView` with a confirm. Failed LLM runs accumulate forever today; a plan run is a per-book, per-user artifact and the user must be able to clear their own. Archive-vs-hard-delete: **soft-archive** (`is_archived`, filtered from LIST) to match every sibling in this service (`outline_node`, `motif`, `structure_node`, `arc_template`).

🔴 **Those siblings all soft-delete AND restore — and the first draft of this spec specced the archive without the restore.** That is precisely the defect plan 30 files as **BE-11** against `canon_rule`: *"Every sibling soft-delete has a restore. `canon_rule` does not. Shipping a Delete button with no undo … is a one-way destructive action."* Shipping the same shape here would be knowingly repeating it. **PS-13: BE-4 does not ship without BE-4b (`POST …/plan/runs/{run_id}/restore` + `GET /runs?include_archived=true`), and the archive toast carries an Undo.**

---

## 6 · Backend prerequisites

**This section is a contract. A later agent builds from it.** Every route is on composition-service, under the existing `/v1/composition` prefix — the gateway is a **pure path-preserving proxy** with a generic `pathFilter` ([`gateway-setup.ts:354`](../../../services/api-gateway-bff/src/gateway-setup.ts#L354)), so **zero gateway work**.

| # | Route / change | METHOD + path | Request | Response | Errors | Size | Status |
|---|---|---|---|---|---|---|---|
| **BE-2** | autofix REST mirror | `POST /v1/composition/books/{book_id}/plan/runs/{run_id}/autofix` | `{model_ref?: UUID, max_rounds: int = 3}` (1–5) | `202 {run_id, job_id, status}` — mirror `/refine`'s ack shape | 404 run · 400 bad state · 403 grant | **XS** | 🔴 **MUST-BUILD**. Service method exists ([`plan_forge_service.py:817`](../../../services/composition-service/app/services/plan_forge_service.py#L817)). EDIT grant. |
| **BE-3** | artifact **body** read | `GET …/plan/runs/{run_id}/artifacts/{artifact_id}` | — | `{artifact_id, kind, content, created_at}` | 404 (unknown **or** cross-book — [`artifacts_by_ids`](../../../services/composition-service/app/db/repositories/plan_runs.py#L265) simply doesn't return a foreign id ⇒ same 404, **no enumeration oracle**, H13) | **S** | 🔴 **MUST-BUILD**. Repo method exists + is book-scoped through the run join. VIEW grant. |
| **BE-3b** | run detail returns its source | *(no new route)* widen `_serialize_run` with `"source_markdown": run.source_markdown` | — | `PlanRunDetail` + `source_markdown` | — | **XS** | 🔴 **MUST-BUILD**. Column already selected ([`plan_runs.py:25`](../../../services/composition-service/app/db/repositories/plan_runs.py#L25)). ⚠ Also widen `types.ts:PlanRunDetail`. |
| **BE-4** | archive a plan run | `DELETE …/plan/runs/{run_id}` | — | `204` | 404 · 403 · **409 if a job is in flight** (do not orphan a running worker job) | **S** | 🔴 **MUST-BUILD**. Needs an `is_archived` column on `plan_run` + a filter in `list_for_book`. `grep "@router.delete" plan_forge.py plan_bootstrap.py` → **nothing**. EDIT grant. |
| **BE-4b** | **restore an archived run** | `POST …/plan/runs/{run_id}/restore` + `GET …/plan/runs?include_archived=true` | — | run detail / list | 404 · 403 | **XS** | 🔴 **MUST-BUILD — ships WITH BE-4, never after it (PS-13).** Every sibling soft-delete in this service has a restore; plan 30's **BE-11** files "delete with no undo" as a defect in its own right. EDIT grant. |
| **FE-1** | **`readOnly` on the JSON-document standard** | *(frontend, no route)* `JsonDocumentProvider.readOnly?: boolean` + `JsonEditorPanel` honours it (CM6 `editable={false}`, no ⌘S, Save hidden) | — | — | — | **XS** | 🔴 **MUST-BUILD (F-P11).** `grep -rn "readOnly\|editable" JsonEditorPanel.tsx documents/*.ts` → **0 hits.** Without it, PS-9's read-only artifact viewer either **cannot exist** or ships a **save button that silently does nothing** — `silent-success-is-a-bug`. A spec-12 contract widening; ~20 lines. |
| **BE-20** | **the ledger tells the truth about its own gate** | *(no new route)* `derive_view`'s per-pass row gains `bootstrap_proposal_id`, `decided_by`, `decided_at` | — | per-pass row +3 fields | — | **XS** | 🔴 **MUST-BUILD — LOAD-BEARING (F-P4).** All three are already on `PassEntry` ([`models.py:652-654`](../../../services/composition-service/app/db/models.py#L652)). **Without this the Approve button on `cast` 409s forever and the panel is a lie.** |
| **BE-21** | **stop the run detail lying about freshness** | *(no new route)* `_serialize_run` → `derive_view(run, package_artifact_id=<latest PACKAGE_KIND artifact id>)` | — | correct `fresh`/`pass_cursor`/`blockers` on `GET /runs/{id}` + LIST | — | **XS** | 🔴 **MUST-BUILD (F-P3).** ⚠ **Updates [`test_genre_tags_plumbing.py:88`](../../../services/composition-service/tests/unit/test_genre_tags_plumbing.py#L88)**, which asserts the buggy source text `"**derive_view(run)"`. Replace it with a behavioural assertion (a compiled run's detail reports the same `pass_cursor` as its `/passes`). |
| **BE-22** | the phantom-tool error message | *(no new route)* [`plan_forge_service.py:704`](../../../services/composition-service/app/services/plan_forge_service.py#L704) | — | — | — | **XS** | 🔴 **MUST-BUILD (F-P5).** `plan_bootstrap_seed` **does not exist.** Name the real recovery: re-run the `cast` pass. |
| — | `GET …/passes` | `GET …/plan/runs/{run_id}/passes` | — | derived ledger | 404 | — | ✅ **EXISTS** ([`plan_forge.py:236`](../../../services/composition-service/app/routers/plan_forge.py#L236)) |
| — | run one pass (**with `force`**) | `POST …/passes/{pass_id}/run` | `{model_ref?, params, force}` | job envelope + derived view | **409 `UPSTREAM_STALE` + `blockers[]`** · 400 | — | ✅ **EXISTS** ([`:303`](../../../services/composition-service/app/routers/plan_forge.py#L303)) |
| — | checkpoint (approve/**reject** + `edits`) | `POST …/checkpoint` | `{approved, pass_id?, edits?}` | run detail | **409 `CHECKPOINT_REFUSED`** · 404 | — | ✅ **EXISTS** ([`:275`](../../../services/composition-service/app/routers/plan_forge.py#L275)) |
| — | link to spec tree | `POST …/link` | `{target}` | link report | **409 `LINK_REFUSED`** · 404 | — | ✅ **EXISTS** ([`:256`](../../../services/composition-service/app/routers/plan_forge.py#L256)) |
| — | seed proposal get/approve/apply | `GET\|POST /plan/bootstrap/{proposal_id}[/approve\|/apply]` | — | proposal | — | — | ✅ **EXISTS + already in `api.ts`** ([`api.ts:99-116`](../../../frontend/src/features/plan-forge/api.ts#L99)) |

### 6.1 Contract hygiene — spec 27's B1 + B2, folded in here

**B1 — `contracts/plan-forge/planner_state.schema.json` is a POC fixture masquerading as a contract, and it contradicts the shipped emitter.**

It still carries `"required": ["PA","HA","CD","THR"]` + `"additionalProperties": false` — `Perfection_Addiction`, `Humanity_Anchor`, `Corruption_Debt`, `Than_Hon_Resonance`: **four variables from one specific POC novel.** Meanwhile the shipped compiler emits an **open map keyed by whatever variables the spec declares** ([`compile.py:65-69`](../../../services/composition-service/app/engine/plan_forge/compile.py#L65)):

```python
    planner_state: dict[str, Any] = {
        v["code"]: _DEFAULT_VARIABLE_INITIAL
        for v in spec.get("layers", {}).get("variables", [])
    }
    planner_state["tier"] = "baseline"
```

⇒ For **every book that does not declare exactly PA/HA/CD/THR** — i.e. every book but one — the artifact the service actually writes **violates its own published schema**, on both clauses at once. The service side of the F5 severing landed; the contract side did not. Nothing validates against this schema at runtime (`grep planner_state` → `compile.py`, one test, and the POC script), so it is **safe to fix and pure debt to leave**.

→ **PS-10:** rewrite as `{ "type":"object", "additionalProperties": {"type":"number"}, "properties": { "tier": {…} }, "required": [] }` — an open map of declared variable codes → number, plus the `tier` string. **Delete the four fixture codes.**

**B1b — `VariableDef` has no `initial`.** [`novel_system_spec.schema.json:109-118`](../../../contracts/plan-forge/novel_system_spec.schema.json#L109) requires `code/name/range/transition_rules` with `additionalProperties: false` and no `initial`, which is why [`compile.py:16`](../../../services/composition-service/app/engine/plan_forge/compile.py#L16) hardcodes `_DEFAULT_VARIABLE_INITIAL = 0` with a comment saying so out loud (*"a variable needing a non-zero baseline … cannot be expressed"*). Add `"initial": {"type":"number"}` (optional, default 0) and read it in `compile_artifacts`.

**B2 — `contracts/plan-forge/plan_pass_artifacts.schema.json` does not exist.** The pass outputs are the **exact bodies BE-3 is about to serve to a GUI and the `edits` deep-merge is about to patch**. Writing the schema now is what stops the Pass Rail's checkpoint cards from being written against a shape nobody wrote down. Source of truth for each: `PASS_REGISTRY[*].output_kind` + the pass prompt/parser in `app/engine/plan_forge/`.

⚠ **SEVEN passes, SIX kinds — and that is not an omission, it is load-bearing.** `self_heal`'s `output_kind` is **`scene_plan`**, the same kind `scenes` emits, and the registry says out loud why:

```python
    "self_heal": PassSpec(
        pass_id="self_heal", depends_on=("scenes", "cast"), reads_package=False,
        # Pass 7 emits a NEW `scene_plan` (the healed one) — which is exactly why inputs must
        # resolve by POINTER: under a latest-by-kind rule it would read its own output as its input.
        output_kind="scene_plan", checkpoint="advisory",
    ),
```

So the schema keys on the **six kinds** (`motif_plan`, `cast_plan`, `world_plan`, `beat_plan`, `char_arc_plan`, `scene_plan`), and **`scene_plan` must be valid for both producers**. It also means the artifact viewer's *latest-per-kind* list (`DISTINCT ON (a.kind)`, F-P2) shows **`self_heal`'s healed output under the `scene_plan` row once pass 7 has run** — not pass 6's. Say so in the panel, or the user thinks their scenes vanished. *(An earlier draft of this spec claimed `self_heal`'s output kind was "unnamed". It is not. Read the registry.)*

---

## 7 · Registration checklist (GG-8) — `plan-passes`, in order

Two machine guards are **GREEN with zero drift at HEAD `9262ed53e`: py enum 57 == contract enum 57 == openable 57.** This panel moves all three by **+1, in lockstep**. ⚠ **Assert the DELTA and the three-way equality — never the literal `58`.** Waves 1–4 land **8** panels before this wave starts (`quality-canon-rules`, `quality-corrections`, `quality-heal`, `progress`, `arc-inspector`, `motif-library`, `quality-conformance`, `arc-templates`), so the baseline here is **65**, not 57 — a DoD pinned to `58 == 58 == 58` sends the next builder hunting a phantom regression. Here is exactly how it stays green.

| # | File | Edit |
|---|---|---|
| 1 | `frontend/src/features/studio/panels/PassRailPanel.tsx` *(new)* | The component. Root `data-testid="studio-plan-passes-panel"`. Logic lives in `features/plan-forge/hooks/usePassRail.ts` (controller, no JSX — the repo's MVC rule). |
| 2 | `frontend/src/features/studio/panels/catalog.ts` | One row, after `plan-hub` (`:190`): `{ id: 'plan-passes', component: PassRailPanel, titleKey: 'panels.plan-passes.title', descKey: 'panels.plan-passes.desc', category: 'editor', guideBodyKey: 'panels.plan-passes.guideBody' }`. **`category` MANDATORY** (test reds without it) and **must be a member of `CATEGORY_ORDER`** — `'editor'` already is. **`guideBodyKey` MANDATORY** (X-3). **No `hiddenFromPalette`** (PS-7). |
| 3 | `frontend/src/i18n/locales/en/studio.json` | `panels.plan-passes.{title,desc,guideBody}`. Title: **"Pass Rail"**. |
| 4 | `frontend/src/i18n/locales/{ar,bn,de,es,fr,hi,id,ja,ko,ms,pt-BR,ru,th,tr,vi,zh-CN,zh-TW}/studio.json` | Same 3 keys × 17 locales — **`python scripts/i18n_translate.py`**, never hand-written. |
| 5 | `services/chat-service/app/services/frontend_tools.py` | **Two edits** in `UI_OPEN_STUDIO_PANEL_TOOL`: (a) append `"plan-passes"` to the `panel_id` **enum** (`:402`, currently 57 entries); (b) append a clause to the tool **description** prose (`:403-481`) — that gloss is the model's *only* hint the panel exists. Suggested: *"'plan-passes' = the PlanForge Pass Rail — the 7-pass compiler ledger, what is stale, what is blocked, and the cast/beats checkpoints a human must accept."* |
| 6 | `contracts/frontend-tools.contract.json` | **NEVER hand-edit — regenerate:** `cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py`, then **commit the regenerated JSON in the same commit as steps 2 + 5.** |
| 7 *(cond.)* | `frontend/src/features/studio/host/studioLinks.ts` | Only if a deep-link URL should resolve here. **Not needed for v1** — the Rail is reached from the palette, the agent, or `planner`'s "Open the Pass Rail →" button (`host.openPanel`, never a route hop — DOCK-7). |
| 8 **(MANDATORY — X-4)** | `frontend/src/features/studio/agent/handlers/planEffects.ts` *(new)* | `registerEffectHandler(/^plan_(run_pass\|review_checkpoint\|link\|handoff_autofix\|apply_revision\|interpret_feedback\|compile)/, planEffect)` → invalidate `['plan-passes', bookId, runId]` + `['plan-run', bookId, runId]`. **There is no `plan_*` handler today** — the registered patterns are only book/composition-draft, outline/scene-link, glossary, knowledge, translation. Without this, **the agent runs a pass and the Rail sits stale.** Mirror [`bookEffects.ts`](../../../frontend/src/features/studio/agent/handlers/bookEffects.ts) exactly, including `unwrapToolResult` (the live stream nests the domain payload inside the `{ok, result}` envelope — a bare top-level read returns `null`, stays green in unit tests, and never fires live). |
| 9 *(cond.)* | `tours.ts` / `tourCatalog.ts` | Not a role-tour step in v1. Skip. |

**Verify (all four green — the first two are the drift-locks):**

```bash
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
cd frontend && npx vitest run \
  src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
  src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
  src/features/studio/palette/__tests__/useStudioCommands.test.ts \
  src/features/chat/nav/__tests__/frontendToolContract.test.ts
```

**Do NOT touch:** `StudioDock.tsx`, `StudioFrame.tsx`, `useStudioCommands.ts`, `UserGuidePanel.tsx` (all derive from `catalog.ts`); `studioUiNav.ts` / `useStudioUiToolExecutor.ts` (panel-id-agnostic).

---

## 8 · Agent surface, tenancy, settings, OCC, cost gates

**Agent surface.** The domain's tools are already registered and are **not changed by this spec**: `plan_run_pass` (A, `paid`, async — **no `force`, by design**), `plan_pass_status` (R), `plan_review_checkpoint` (A), `plan_link` (A), `plan_handoff_autofix` (A), plus the v1 cluster (`plan_propose_spec`, `plan_validate`, `plan_self_check`, `plan_interpret_feedback`, `plan_apply_revision`, `plan_compile`).

**PS-11 — the INVERSE gap this spec deliberately does NOT close.** After BE-3 the human can read an artifact body and the **agent still cannot** (there is no `plan_get_artifact` MCP tool). That is a real GG-2 inversion, and the MCP-first invariant says the domain owns its tools. It is *not* in this spec's scope — this wave is about the human half, and adding a tool is a 3-schema-source FastMCP change with its own contract test. **→ OQ-3, one row, own slice.** Recorded rather than silently grandfathered.

**Lane-B (X-4):** step 8 above. Mandatory, not conditional.

**Tenancy.** No new tables. `plan_run` is **per-book** (`book_id` scope key, `created_by` is a plain actor stamp — [`plan_runs.py:1-10`](../../../services/composition-service/app/db/repositories/plan_runs.py#L1)); `plan_artifact` carries **no `book_id`** and is scoped **transitively through `JOIN plan_run r ON r.id = a.run_id`** — every new read (BE-3) MUST go through that join, and `artifacts_by_ids` already does. BE-4's `is_archived` is a column on the existing book-scoped table. Every route gates with `_gate_book(grant, book_id, user_id, VIEW|EDIT)` before touching the service. **A cross-book artifact id simply does not come back — same 404 as a missing one (no enumeration oracle).**

**Settings (SET-1..8).** This spec introduces **no new toggle, no new env flag.** The two knobs it exposes are both **per-call run inputs, not settings**: `model_ref` (an explicit `ModelPicker` value — never a silent default; the panel shows *which* model it will spend on) and `force` (an explicit per-call argument the code itself insists must never be an env flag — [`plan_pass_service.py:248-250`](../../../services/composition-service/app/services/plan_pass_service.py#L248)). `max_rounds` on autofix is a per-call bounded input (1–5), not config.

**OCC.** **None, deliberately (PS-8).** `plan_run.pass_state` has no version column; `review_checkpoint` is idempotent and last-write-wins by construction. There is nothing to 412 on, and inventing an `If-Match` here would be *"a new confirmation convention"* — AN-8 says finding one is finding a defect. What protects the user is not a version check but **derived freshness**: whatever the last decision was, `fresh`/`blocked_at` recompute from the fingerprints on the next read, so the ledger cannot disagree with itself. (Contrast: outline/canon/motif writes — those **do** carry OCC, and any panel touching them still owes the 412 → *"changed elsewhere — reloaded"* recovery.)

**Cost gates.** PS-6, §F-P8. **No new estimate route. No new `/actions/*` descriptor.** Paid actions (`run_pass`, `refine`, `interpret`, `autofix`, `compile(run_pipeline)`) are Tier-A `paid=true` and go through their existing REST routes with an explicit `model_ref` + an explicit in-panel confirm. Inventing `POST /actions/plan_run_pass/estimate` would reproduce, exactly, the three FE calls that **404 in production today** (plan 30 §3.3).

### 8.1 Collisions — whose files this wave walks into (plan 30 §9)

**All live tracks share THIS checkout on `feat/context-budget-law`.** Verified 2026-07-13, not inherited:

| File this wave edits | Owner / risk | Verdict |
|---|---|---|
| `services/chat-service/app/services/frontend_tools.py` | Track C's D8 had **uncommitted, mid-edit** chat-service files (`ToolApprovalCard.tsx`, `useChatMessages.ts`, `tool_permissions.py`, `stream_service.py`). | ✅ **CLEAR — re-verified: `git status --short services/chat-service` is empty.** Those edits have landed. `frontend_tools.py` was never in that set. |
| `contracts/frontend-tools.contract.json` | **Every wave in plan 30 regenerates this file.** A concurrent wave that also adds a panel will conflict here. | ⚠ **Regenerate, never hand-edit** (§7 step 6), and land it in the **same commit** as `catalog.ts` + `frontend_tools.py`. If another wave landed a panel first, **re-run the generator after rebasing** — do not merge the JSON by hand. |
| `frontend/src/features/studio/panels/catalog.ts` | Shared by every wave. One appended row; no reordering. | ✅ Append-only; low conflict. |
| `frontend/src/features/plan-forge/**` | Plan 30 §9 lists **the Planner panel** in its 🟢 *"genuinely un-colliding"* row — *"Track C only **reads** PlanForge tool descriptions."* | ✅ **The safest lane in the plan.** |
| `PlanDrawer.tsx` / `QualityCanonPanel.tsx` | Book-Package track + `d662bd97d` (D-04). | ✅ **This wave does not touch either.** Recorded so a builder does not wander into them for the artifact viewer — the viewer is `json-editor`, not PlanDrawer. |

**Staging rule (memory `never-git-add-A` + `git-commit-pathspec-reads-working-tree-not-index`):** enumerate every file; `git add -A` is forbidden in a shared checkout; `git commit -- <path>` commits the **WORKING TREE**, not the index — check `git diff --cached` before committing.

---

## 9 · Milestones

Each ends at a POST-REVIEW and is independently revertable.

### M1 — backend truth + routes (BE only, no UI)
BE-20 (ledger emits `bootstrap_proposal_id`/`decided_by`/`decided_at`) · BE-21 (`_serialize_run` freshness + **fix the pinning test**) · BE-22 (the phantom-tool message) · BE-2 (autofix route) · BE-3 (artifact read) · BE-3b (`source_markdown`) · BE-4 (archive a run) · **BE-4b (restore, PS-13)**.
**DoD:** composition suite green (`python -m pytest tests -q -n auto --dist loadgroup`). Four new tests, all **behavioural**:
1. **`GET /runs/{id}`'s `pass_cursor` == `GET /runs/{id}/passes`'s `pass_cursor`** for a compiled run with ≥1 completed package-reading pass — the F-P3 regression. *(This replaces `test_genre_tags_plumbing.py:88`'s source-text assertion, which asserts the presence of the bug.)*
2. A cross-book `artifact_id` returns **404, not 403** (no enumeration oracle).
3. **The dependency-graph regression (F-P12):** on a run with `motifs` accepted + `cast` pending, assert `blockers_for("world") == ["cast"]`, `blockers_for("beats") == []`, and `pass_cursor == 1`. *This test exists because this spec's own first draft got all three wrong.*
4. **The rejected-checkpoint regression (F-P10):** `POST /checkpoint {approved:false, pass_id:"cast", edits:{…}}` ⇒ the pass reads `decision:"rejected"`, `blocked_at` is **`null`**, and every downstream pass still lists `cast` in `blockers[]`. Pin the surprise so the panel is built against it.

### M2 — contract hygiene (27-B1/B2)
`planner_state.schema.json` rewritten open-map (PS-10) · `VariableDef.initial` added + read in `compile_artifacts` · `plan_pass_artifacts.schema.json` written for all 7 pass outputs.
**DoD:** a test round-trips a **compiled package for a book declaring variable codes that are NOT PA/HA/CD/THR** and validates its `planner_state` against the schema. That test is **red today**, on both clauses.

### M3 — `planner` repair (the cheap half; **no dependency on M4**)
**FE-1** (`readOnly` on the JSON-document standard — **do this FIRST; PS-9 cannot exist without it**) · R1 artifact viewer (+ the `plan-artifact` provider on a **composite `{runId}:{artifactId}` resourceId**, PS-9) · R2 source resume · R3 interpret/refine/autofix buttons (+ **PS-5**, the `revision` type fix) · R4 archive **+ restore** a run.
**DoD:** `PlanRunView.test.tsx` + `PlannerPanel.test.tsx` green with new cases, plus a `registry.test.ts` case asserting **a `readOnly` provider's document renders with no Save affordance and ⌘S does not call `save()`** (not "save() is a no-op" — a no-op save is the bug). **A live browser smoke** (below) covering: open a past run → its source markdown is in the textarea → click an artifact row → the `json-editor` tab mounts with the body, **read-only**.

### M4 — the Pass Rail (`plan-passes`)
The panel + the 9-step registration + the Lane-B handler.
**DoD:** the four drift-lock suites green (§7), all three counts **+1 in lockstep** (delta, not a literal — §7). **The live browser smoke (below).**

**Gate on M4:** plan 30's **X-1** (AddModelCta DOCK-7) must be green first. The Rail's `ModelPicker` empty state renders `AddModelCta`, and today that button destroys the dockview layout.

---

## 10 · Definition of Done

1. All four drift-locks green: chat-service `test_frontend_tools_contract.py` + `test_frontend_tools.py`; frontend `panelCatalogContract` + `UserGuidePanel` + `useStudioCommands` + `frontendToolContract`. **py enum 58 == contract enum 58 == openable 58.**
2. composition-service suite green under `-n auto --dist loadgroup`, including the **three new regression tests** (M1/M2 DoD).
3. `contracts/frontend-tools.contract.json` **regenerated, not hand-edited**, and committed in the same commit as `catalog.ts` + `frontend_tools.py`.
4. 17 locales generated with `scripts/i18n_translate.py`.
5. **🔴 LIVE BROWSER SMOKE — mandatory, and it is the DoD, not a nice-to-have.** This repo's law (`agent-gui-loop-needs-live-browser-smoke-not-raw-stream`): a green unit suite has repeatedly hidden *"the FE could not actually execute it."* Spec **24's own named DoD pillar (H8.2) was a live browser smoke, and it was never written** — the run-state's "smoke" was curl. **Do not repeat that here.** Playwright, real dev stack, the `claude-test@loreweave.dev` account, a **local** lm_studio chat model (**$0**), a real book with a compiled plan run. Drive the dock via `evaluate` + `data-testid` (refs go stale — `playwright-live-dockview-automation-recipe`). Prove, by **effect**:
   - **(a)** `ui_open_studio_panel {panel_id: "plan-passes"}` from the agent **mounts the dock tab** (not `shown:true` with no tab — the `ui_show_panel` silent-no-op class).
   - **(b)** The Rail renders the **7 passes with the same `pass_cursor` the API reports** — the F-P3 regression, observed in the browser. **And the enable/disable state matches the dependency table (§4.1):** on a `cast`-pending run, `world`'s Run button is **disabled** and `beats`' is **enabled** (F-P12 — the inversion this spec's first draft shipped in its own mock).
   - **(c)** **The headline:** on a run `blocked_at: "cast"`, a **human clicks through the seed proposal (review → approve → apply) and then Approve**, and the ledger advances — `blocked_at` moves off `cast`, `pass_cursor` increments. *This is the capability that does not exist today.* If this step cannot be driven in a browser, **the wave is not done**, whatever the unit suite says.
   - **(d)** A 409 `UPSTREAM_STALE` renders its `blockers[]` as readable copy, and the **force** escape is reachable behind it.
   - **(e)** `planner`: an artifact row opens `json-editor` with a real body (BE-3), **read-only** (FE-1 — no Save button, ⌘S does nothing *visibly and deliberately*), and a reopened run's source markdown is in the textarea (BE-3b).
   - **(f)** **Save edits on a blocking checkpoint (F-P10):** the pass flips to **`rejected`**, `blocked_at` goes `null` on the wire — and **the Rail still says "stuck at cast"** and still offers Approve. If the panel goes quiet here, it is wrong, and the unit suite will not catch it.
6. **Cross-service evidence.** The cycle touches composition-service **and** chat-service (the `panel_id` enum) ⇒ VERIFY's evidence string carries a `live smoke: <one-liner>` token, per CLAUDE.md.
7. `SESSION_HANDOFF.md` updated: `D-PLANFORGE-GUI-AUDIT` **amended** (sub-gap 1 stale) then cleared; the OQs below filed as rows.

---

## 11 · Open questions / Deferred

| # | Question | Status |
|---|---|---|
| **OQ-1** | **Should `plan_run_pass` get a Tier-W `composition.plan_run_pass` descriptor** on the generic `/actions/preview` + `/actions/confirm` spine, giving both the agent and the GUI a ledger-claim + usage-billing precheck? Today PlanForge's paid actions spend with **no pre-run guardrail claim** (unlike `motif_mine` / `conformance_run`, which are Tier-W and do claim). **Recommendation: yes, eventually — but not in this spec.** It changes the *agent's* channel, and AN-8 seals one-channel-per-object-class. **PO decides.** v1 uses the shipped direct channel + an explicit in-panel confirm (PS-6). |
| **OQ-2** | The `edits` deep-merge on a checkpoint is a **raw JSON patch** into a pass artifact. v1 exposes it as a **structured form** for `cast` (add/remove/rename a character, change a role) and `beats` (edit a beat's summary/tension), because those are the two shapes we know. **Anything else falls back to the read-only viewer + "re-run this pass".** Is a generic JSON-patch editor over an arbitrary artifact wanted? **UNVERIFIED — depends on B2's schemas (M2). Decide after M2, not before.** |
| **OQ-3** | **The inverse gap (PS-11):** after BE-3 the human can read an artifact body and the **agent cannot** (no `plan_get_artifact` MCP tool). Real, and out of this wave's scope. **One row, own slice.** ⚠ 3-schema-source FastMCP caveat applies. |
| **OQ-4** | `list_artifact_refs` is `DISTINCT ON (kind)` — the viewer shows the **latest body per kind**, not a history, even though `plan_artifact` stores every version (that is how `edits` works: save-new, never mutate). Is an artifact **history/diff** view wanted (*"what did the cast look like before I edited it?"*)? Cheap to add (drop the `DISTINCT ON`, add a `?history=true`), and it would make the Save-edits flow reversible. **Not in v1. Recorded because the data is already there.** |
| **OQ-5** | Spec **21-G2** — *PlanForge `propose.py` has no `existing_state` input: proposing a plan for a book with 200 chapters ignores all of them.* Plan 30 §7 explicitly parks this **out of Wave 5** ("a generation-quality defect, not a GUI gap — track it; don't inflate Wave 5"). **Honoured. Not touched here.** Flagged so the next reader does not think it was missed. |
| **OQ-6** | Two humans racing the same checkpoint: last-write-wins, no OCC (PS-8). Deliberate, and the derived ledger makes the outcome visible on the next read. **UNVERIFIED** whether any user has ever hit this (collaboration grants make it *possible*). If it ever bites, the fix is a version column on `plan_run`, not an ad-hoc guard. |
