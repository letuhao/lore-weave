# Wave 1 — Quality Completion · IMPLEMENTATION PLAN (BUILD DETAIL)

> **Written:** 2026-07-13 · branch `feat/context-budget-law` · audited at HEAD `9262ed53e`
> **Spec (the design — read it, do not re-design):** [`docs/specs/2026-07-01-writing-studio/31_quality_completion.md`](../specs/2026-07-01-writing-studio/31_quality_completion.md)
> **Master plan (SEALED decisions §0, ledger §8.0, handler homes §8.0b):** [`30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md`](../specs/2026-07-01-writing-studio/30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md)
> **Design draft (the UI acceptance criterion):** [`design-drafts/screens/studio/screen-quality-completion.html`](../../design-drafts/screens/studio/screen-quality-completion.html) — 1,459 lines, 8 states ①–⑧
> **Type:** FS · **Size: L** — **L comes from the LOGIC axis (logic ≈ 9 → `logic <= 12` → base L,
> `workflow-gate.py:349`), NOT from the side-effect floor.**
> 🔴 **Do not repeat spec 31 line 4's claim that "side_effects = 5 ⇒ risk floor L". It is FALSE:**
> `_expected_size` caps the risk floor at **M** (`side_effects >= 2 → floor = 2`, `workflow-gate.py:357-363`),
> and undersizing *above* the floor is advisory only (`fail()` fires only `if chosen_idx < floor`, `:384`).
> **`size M …` would be silently ACCEPTED.** Type **L deliberately** — the gate will not catch you if you don't.
> **Keep `<files>` ≥ 10** (the breadth bump `if files >= 6 and logic >= files: base += 1`, `:355`, would
> escalate to XL if you pass files in 6..9 with logic = 9). With the real count (~40) expected == L exactly.
> **FIX-NOW while you are here** (one-line doc edit, cheaper than a defer row): correct
> `31_quality_completion.md` line 4 to *"side_effects = 5 ⇒ risk floor **M**; **L is set by the logic axis**
> (logic ≈ 9). NOTE: the gate will accept M — pass L deliberately."* Leaving the false claim is how a later
> agent 'corrects' the size back to M and passes the gate.
> **Gate command:** `./scripts/workflow-gate.sh size L 40 9 5 <ctx%>`

---

## 0 · THE POLICY THIS PLAN IS WRITTEN UNDER (binding — quoted verbatim from the PO)

1. **This plan is written ONCE, in full, at BUILD DETAIL.** After the QC gate, implementation proceeds
   **autonomously with no further design checkpoints.** Anything left vague becomes a stall or a guess at
   3am. A slice that says "wire the panel" is a FAILURE; a slice says WHICH FILE, WHAT CHANGE, WHICH TEST.
2. **`/review-impl` runs at the completion of the wave**, and any bug it finds is fixed before the wave
   closes. It is a literal step in the Definition of Done (§9).
3. **DEFERRAL POLICY — "blocked ≠ stopped".** On a blocker: write a tracked defer row and **KEEP GOING**.
   Do **not** stop, do **not** ask. **Stop and ask ONLY for a CRITICAL blocker**, defined narrowly as
   exactly one of:
   - a destructive / irreversible action (data loss; a migration that drops or rewrites user rows),
   - a **sealed decision proven wrong** by the code (§0 PO-1..4 of plan 30),
   - a **tenancy / security breach** (cross-user data exposure),
   - a **paid-action defect that would charge the user for nothing.**
   Everything else — a missing route, an awkward refactor, a failing third-party thing, an ugly seam — is
   a **defer row + continue**.
4. Every defer row carries: ID, wave/slice of origin, what, the gate reason (CLAUDE.md's 5 gates), target
   wave/trigger. A defer row is never a silent drop.
5. **CLAUDE.md's anti-laziness rule is in force:** *"missing infrastructure is NOT blocked — it is unbuilt
   work to implement."* A route that does not exist is a route you **WRITE**.

**🔴 THE ADJUDICATION REGISTER EXISTS. IT WINS OVER THIS PLAN.**
[`docs/plans/studio-adjudication/wave-1-decisions.md`](studio-adjudication/wave-1-decisions.md) — **53 items,
49 DECIDED against source code**, recovered from the adjudication journal *after* this plan was first written
**blind**. Its header is binding: *"These are INSTRUCTIONS, not suggestions. Where this contradicts the wave
plan, this file wins."*

This plan has been **RECONCILED** against it (2026-07-13). Every decision is now folded into §2/§3/§5/§7
below. **Where a slice cites a decision id (`Q-31-…`, `BE-31-…`, `X-31-…`, `QC-31-…`), that decision is the
authority — go read it if a detail here is ambiguous.** Do not re-open a decided question. §2 lists the
places the pre-reconcile plan was **WRONG** and has been corrected — 🔴 marks each one, so a builder who read
an older copy is not misled.

---

## 1 · Header — what this wave is, what gates it, what it unblocks

| | |
|---|---|
| **Panels shipped** | `quality-canon-rules` · `progress` · `quality-corrections` · `quality-heal` |
| **Gaps closed** | `G-CANON-RULE-CRUD` (P0) · `G-PROGRESS` · `G-CORRECTION-FLYWHEEL` (P1) · `G-POLISH-SELFHEAL` (P1) |
| **Deferred rows cleared** | `D-QUALITY-CRITIC-HEAL-LINK` · 00C **Q-3(a)(b)** |
| **Panel-id ledger (plan 30 §8.0)** | rows 1–4. Baseline **57** → **61** after this wave. **The count is CUMULATIVE across waves — six of eight specs got this wrong by each computing from 57.** A DoD asserts the **delta + the three-way equality**, **never a literal**. |
| **Lane-B handler home (plan 30 §8.0b)** | **Wave 1 CREATES `frontend/src/features/studio/agent/handlers/compositionEffects.ts`.** Wave 6 (spec 36) **extends** it. Do not create a second `composition*Effects.ts` — `matchEffectHandlers` returns **every** match and `runEffectHandlers` **awaits all** ⇒ two files DOUBLE-FIRE. |
| **HARD GATES (must be green before M1 starts)** | **X-2** (`CATEGORY_ORDER` missing `'quality'`) · **X-3** (`guideBodyKey` unguarded) · **X-1** (`AddModelCta` DOCK-7 — gates **M3** specifically) |
| **Unblocks downstream** | 🔴 **GG-4 — but read §2 GG-4 before you act on it.** This wave gives the Studio its **own reader** for the save-time word-count loop (`progress`), which is what GG-4 actually asks for. **It does NOT gate a retirement, because no retirement is scheduled:** spec 16 is CLOSED and Phase 4b (2026-07-05, the user's call) **keeps `ChapterEditorPage.tsx` indefinitely.** The deliverable is a **mechanical guard** (`ProgressPanel.test.tsx` renders `today_words`/`daily_goal` from the real route), **not a scheduling hand-off.** · Wave 3's `quality-conformance` becomes hub card **8** (not 5 — this wave takes the hub to 7). |

### §9 collision check — run again at BUILD start, do not trust this snapshot

- 🟡 **`QualityCanonPanel.tsx`** was last edited `d662bd97d` (D-04). Its `focusRuleId` deep-link seam
  **already exists** (`useQualityCanon.ts:27` `CanonFocusParams`; `PlanHubPanel.tsx:74` passes it).
  **EXTEND it — do not rebuild it.**
- 🔴 **Track C's four mid-edit files — DO NOT TOUCH:** `frontend/src/features/chat/components/ToolApprovalCard.tsx`,
  `frontend/src/features/chat/hooks/useChatMessages.ts`, `services/chat-service/app/routers/tool_permissions.py`,
  `services/chat-service/app/services/stream_service.py`. This wave touches
  `services/chat-service/app/services/frontend_tools.py` — **a different file**, verified clean.
- 🟡 This wave does **not** touch `PlanDrawer.tsx` or `plan-hub` (Book-Package track).
- **NEVER `git add -A`.** Enumerate files. `git commit -- <path>` commits the **WORKING TREE**, not the
  index — check `git diff --cached` before every commit (a concurrent session may have pre-staged rows).

---

## 2 · THE REGISTER — every open question, ADJUDICATED. Do not re-open.

| # | Question (spec 31) | **DECISION (binding)** | Consequence |
|---|---|---|---|
| **OQ-1** | Can a Studio-Compose `propose_edit` Apply/Dismiss record a correction? | **NO — option (c).** The flywheel learns from **structured** generation only (engine jobs + authoring runs). `PROPOSE_EDIT_TOOL` has `{operation,text,rationale}` and no job id (`frontend_tools.py:78-98`); the prose came from a **chat-service** turn, not a composition `generation_job`. **Do not mint a job for a chat turn in this wave.** | Defer row **D-31-PROPOSE-EDIT-CORRECTION**, gate **#2**. |
| **OQ-2** | Is a self-heal accept/reject a correction kind? | **NO (conscious won't-fix, v1).** The CHECK is closed on `('edit','pick_different','regenerate','reject')`; adding `heal_*` is a migration **and** trips `migration-check-constraint-must-backfill-all-historical-blocks`. Correcting a *fix* ≠ correcting a *draft*. **`quality-heal` writes ZERO corrections.** | Defer row **D-31-HEAL-CORRECTION-KIND**, gate **#5**. |
| **OQ-3** | The paid quality actions have no cost estimate. | **Ship v1 without one. Add NO estimate route.** QC-7: the fix is a `composition.self_heal_propose` descriptor on the **generic** `GET /actions/preview` → `POST /actions/confirm` spine (**BE-Q4**). **Three invented per-action estimate routes already 404 in production (plan 30 §3.3). Do not add a fourth.** | Defer row **D-31-SELFHEAL-COST-GATE**, gate **#2**. |
| **OQ-4** | `dismiss-violation` has no MCP tool. | 🔴 **REVERSED BY ADJUDICATION — BUILD IT IN M1** (`Q-31-OQ4-DISMISS-VIOLATION-NO-MCP`). The pre-reconcile plan said "human-only in v1, defer". **Wrong.** Spec 31 already MUST-BUILDs two GG-2 parity tools in this wave, **in this exact file**, under its own rule *"Do not ship the human half alone; a one-sided restore is the GG-2 inverse defect, immediately"* (31:521, 31:601). Dismiss is the same shape and is **~25 lines of logic that ALREADY EXISTS in the REST handler** — it clears **none** of CLAUDE.md's 5 defer gates ("a route you could write is unbuilt work, not a blocker"). **Writing + carrying the defer row costs more than the tool.** → **NEW row BE-11d · `composition_dismiss_violation` (Tier A, XS) — built in `W1-03`, same slice as BE-11c.** | **No defer row.** `D-31-DISMISS-MCP` is **DELETED** from §9.4. |
| **OQ-5 / BE-P1** | Is `by_chapter` worth a route change? | **🔴 BUILD IT** (`BE-31-P1-BY-CHAPTER`, which explicitly overrides the spec's "default = drop"). The dimension is in the PK and is collapsed by `DailyProgressRepo.read_aggregate` before the router sees it (`daily_progress.py:98` partitions `BY d.chapter_id`, `:111` throws it away) — written forever, read at that grain by nobody = the write-only class this spec exists to close. Adding it = **one extra query + one additive field** (~40 lines). **No chapter titles on the wire** (composition does not own chapters) — the FE maps ids→titles by mirroring `QualityCriticPanel.tsx:33-41`. → **BE-P1 is IN, in slice W1-07.** *(A second adjudication row, `Q-31-OQ5-BY-CHAPTER-BUILD-OR-DROP`, argued DROP on the premise that the wire shape needs a cross-service call. **That premise is refuted by the build recipe above** — the router adds no `book_client` call. BUILD stands. **PO may veto**; if vetoed, strike BE-P1 from W1-07 and file `D-PROGRESS-BY-CHAPTER`, gate #5.)* | No defer row. |
| **BE-9d** | Per-job corrections drill-down route. | **DROP from v1** (`BE-31-9d-PER-JOB-CORRECTIONS-LIST`) — but 🔴 **for a different reason than this plan first gave.** The plan's rationale ("learning-service may already serve it") is **FALSE and was grepped**: `GET /v1/learning/corrections` (`learning-service/app/routers/corrections.py:64-73`) accepts only `project_id/target_type/diff_class/limit/cursor` — **there is no `target_id`/`job_id` filter**, so it *cannot* answer "the corrections on THIS job". The real reasons are: (1) **NO CALLER** — Panel C's wireframe is an aggregate-per-mode table with no per-job row to click ⇒ a route with zero consumers = the built-but-unreachable class; (2) learning's copy is **redact-by-default** (the outbox payload carries `has_guidance`/`has_raw_prose` **booleans**, never prose) so it must **not** be widened for this — a drill-down wants exactly what learning does not have. **Builder action:** strike the BE-9d row from the M4 build set and delete 31:430-432's *"Optionally … BE-9d"* sentence so it cannot be re-picked at 3am. **Leave `GenerationCorrectionsRepo.list_for_job()` in place, test-only** — do not delete it, do not "wire it up for completeness". If ever asked for, build it in **composition** (never by adding a `target_id` filter to learning). | Defer row **D-31-CORRECTION-DRILLDOWN**, gate **#1** (rationale corrected). |
| **UNVERIFIED-1** | Does learning-service cope with a **burst** of `GENERATION_CORRECTED` from a Revert-All? | 🔴 **REVERSED BY ADJUDICATION — VERIFIED, AND `revert_all` MUST CAPTURE** (`Q-31-UNVERIFIED-LEARNING-BURST`). The pre-reconcile plan's "no capture, it's an unmeasured transaction storm" is **wrong on the code**: the transport is a **Redis Streams consumer group** (`learning-collector` on `loreweave:events:composition`, `BaseProjectionConsumer`: durable log, `start_id="0"` backlog replay, batched `XREADGROUP(count=10, block=5000)`, per-msg XACK, bounded retry→DLQ, XAUTOCLAIM). A burst is not pressure — events **sit in the stream and drain at the consumer's pace**; `STREAM_MAXLEN = 10000` (`worker/events.py:30`) is 3 orders of magnitude above "dozens". Per-event work is **one `INSERT … ON CONFLICT DO NOTHING`** (`handlers.py:500-546, 102-124`) — no LLM, no HTTP, **zero token spend** (the LLM-judge is a *different* consumer on a *different* stream). **And the read exposed the REAL gap: `revert_all` (`authoring_run_service.py:960-1019`) calls `transition_unit` DIRECTLY at `:1001` — it BYPASSES `reject_unit`** ⇒ a capture written only in accept/reject records **NOTHING** on a Revert-All, silently losing the richest bulk-rejection signal. → **W1-15 ADDS the capture inside `revert_all`'s per-unit loop** (sequential, fire-and-forget, skip on `job_id IS NULL`). **No throttle, no batch, no debounce anywhere.** | **No defer row.** `D-31-REVERTALL-CAPTURE` is **DELETED** from §9.4. |
| **UNVERIFIED-2** | Does any OTHER consumer read `work.settings.daily_goal`? (BE-P2 makes it legacy-read-only.) | **CLOSED — VERIFIED AT CODE** (`Q-31-UNVERIFIED-DAILYGOAL-CONSUMERS`). Semantic readers: **exactly ONE**, `progress.py:68 _coerce_goal` (used at `:124`) — the reader BE-P2 rewrites anyway. Proven against all three grep-hostile paths: every other `work.settings` consumer reads through `packer/profile.py:71-78 from_settings`, a **5-key allowlist** (`source_language, voice, structure_pref, tone, density`) ⇒ `daily_goal` never reaches a prompt; **ZERO** `settings->>`/`settings->` JSONB accessors against `composition_work.settings` repo-wide; **ZERO** cross-service readers; `daily_goal` is in **no** OpenAPI contract. 🔴 **BUT THE GREP COULD NOT SEE THE SECOND CONSUMER: `composition_get_work` (`mcp/server.py:333`) returns `work.model_dump()` — the WHOLE settings blob — to the LLM.** After BE-P2 an agent asked *"what's my daily goal?"* reads the **frozen legacy** `settings.daily_goal` and reports it, while the real per-user goal lives in `composition_progress_goal`. A stale SECOND HOME surfaced to the model = the SET-3 violation QC-6 exists to close. → **W1-07 REDACTS `daily_goal` at the MCP boundary** (3 lines + 1 test). **Still run the greps at W1-07 step 0** — but the answer is known. | **No defer row.** New work item **BE-P4** (§5). |
| 🔴 **P2-CLEAR** *(new — adjudicated)* | What does "clear my goal" (`PUT {goal: 0}`) do to the per-user row? | 🔴 **UPSERT the row with `daily_goal = NULL`. NEVER DELETE the row; never store a literal `0`** (`Q-31-P2-CLEAR-SEMANTICS`). The pre-reconcile plan said **DELETE** — and that **re-enters the exact tenancy defect BE-P2 exists to kill**: deleting the row re-exposes `work.settings.daily_goal`, so **Bob clearing his goal resurrects Alice's shared book goal** and measures Bob's counter against it. **The row's EXISTENCE is the per-user tier claim; its VALUE is the goal.** A NULL row is an explicit *"I have no goal"* that **SHADOWS** the legacy per-book value. ⇒ DDL drops `NOT NULL` (a Postgres CHECK passes on NULL: `NULL > 0` → UNKNOWN → passes); resolution gates on **ROW PRESENCE**, tri-state, **never `row.daily_goal or legacy`**. | No defer row. **Rewrites M-B + W1-07.** |
| 🔴 **9c-OPS** *(new — adjudicated)* | Is `CORRECTABLE_OPERATIONS` three ops or four? | 🔴 **FOUR — add `adapt_scene`** (`BE-31-9c-DENOMINATOR-ALLOWLIST`). `ComposeView.tsx:73` posts `operation:'adapt_scene'` on the **same `/generate` route**, and the **same capture handlers fire on it** (`ComposeView.tsx:107` `correct()`, `:137` `cowriteCorrect()`). With a 3-op allowlist the correction ROWS still get written but their JOB rows are filtered out of the FROM side of the join ⇒ **a derivative Work drafted via Adapt-from-source renders the cold-start "no generations" panel for an author who drafted an entire branch** — the same bug class, inverted. `CORRECTABLE_OPERATIONS = ("draft_scene", "draft_chapter", "stitch_chapter", "adapt_scene")`. *(PO veto = delete the 4th entry; nothing else changes.)* | No defer row. **Rewrites W1-13.** |
| 🔴 **9c′-LITERAL** *(new — adjudicated)* | What closed set does `GenerateBody.operation` narrow to? | 🔴 **NOT `Literal["draft_scene"]` — that would 422 TWO SHIPPED FE FEATURES** (`BE-31-9c-prime-LITERAL-NARROWING`). The spec's own pre-flight ("check for a caller posting a non-standard operation") is a **POSITIVE HIT**: `useInlineGhost.ts:60` posts `operation:'continue'` and `ComposeView.tsx:73` posts `operation:'adapt_scene'` — both to `/works/{pid}/generate` = `GenerateBody`. The correct closed set is the drafter's **own registry** (`cowrite._OPERATION_INSTRUCTIONS`), **partitioned by route**: `GenerateBody → Literal["draft_scene","continue","adapt_scene"]`; `GenerateChapterBody → Literal["draft_chapter"]`; selection stays as-is. **Plus a THIRD open surface the spec missed: `mcp/server.py:1356 _GenerateArgs.operation: str \| None`** — it feeds these exact bodies at the confirm-execute seam, so a bad op survives propose AND the user's **paid confirm**, then dies as a 400 at execute (the paid-action-defect shape). Close it to the union. | No defer row. **Rewrites W1-13.** |
| 🔴 **ACCEPT-EDIT** *(new — adjudicated)* | How is "accepted after editing" detected? | 🔴 **REVISION-TEXT vs REVISION-TEXT — never `job.result["text"]` vs the live chapter** (`Q-31-ACCEPT-AFTER-EDIT-DETECTION`). The pre-reconcile plan compared the job's LLM plain text against the chapter's TipTap `_text`. **The round-trip is NOT identity**: generated prose carries ATX `### <scene title>` lines; `text_to_tiptap_doc` lifts them to heading nodes whose `_text` **drops the `### ` prefix** (`prose_doc.py:48,107,127`) ⇒ **a phantom diff on every heading line of an UNTOUCHED chapter** ⇒ a false `kind='edit'` on every accept-as-is, **bypassing the `EDIT_NO_CHANGE` guard** because `changed_blocks > 0`. That is the self-reinforcement H2 forbids. **Both texts must come from the SAME producer**: `before = text(unit.post_revision_id)`, `after = text(latest_revision_id)`, via a **new** `BookClient.get_chapter_revision_text()` (mirror `knowledge-service/app/clients/book_client.py:602`; the route **exists** at `book-service/server.go:3372`). Revision-id divergence is the **TRIGGER**; `changed_blocks > 0` is the **CONFIRMATION** — **both** required. | No defer row. **Rewrites W1-15.** |
| 🔴 **GG-4** *(new — adjudicated)* | Does this wave gate `ChapterEditorPage`'s retirement? | **GG-4 is SATISFIED BY CONSTRUCTION — and nothing is scheduled to delete the page** (`Q-31-GG4-RETIREMENT-ORDER`). Spec 16 is **CLOSED**: Phase 4b (2026-07-05, the user's call, superseding M9) keeps `ChapterEditorPage.tsx` **indefinitely** as an unlinked, banner-marked, direct-URL fallback. **Do NOT add a scheduling gate, a defer row, or a hand-off.** What this wave owes GG-4 is a **mechanical guard, not a prose banner**: `ProgressPanel.test.tsx` must assert the Studio panel **RENDERS `today_words`/`daily_goal` fetched from `GET /works/{pid}/progress`** — from the moment that is green, deleting the legacy page can no longer orphan the save-time word-count loop. **FIX-NOW at wave close** (~3 lines): strike the stale "🔴 GG-4 GATE … retirement may proceed" text in plan 30 §7's Wave-6 block, soften GG-3's "user-approved decision to RETIRE" row, and strike 31:402 + 31:753 — all four contradict spec 16's actual sealed outcome. | No defer row. |

### Locked decisions inherited from spec 31 (QC-1..10) — restated so this file is self-contained

- **QC-1** — **This is a PORT.** No component is rewritten from scratch. `usePolishProposals` is the single
  exception, and **only its storage changes**; its **return shape is preserved** so the legacy `PolishPanel`
  keeps working (its tests are the regression gate).
- **QC-2** — **`progress` gets `category: 'editor'` and is NOT a quality-hub card.** A word-count streak is
  not a quality judgment. It **still uses `useQualityWork`** as its Work gate (one gate, one name).
- **QC-3** — `quality-corrections` mounts an **extracted `CorrectionStatsTable`**, never `QualityPanel`
  (which also renders `BookPromiseCoverageSection` — the Studio already ships that as `quality-coverage`;
  mounting it whole puts a **paid LLM action on screen twice**).
- **QC-4** — `quality-heal` applies through a **NEW hoist verb** `applyHealedDocument(...)` on
  `ManuscriptUnitApi`. **Not** a raw `editorRef`. **Not** `setBody` from the panel. It returns a
  **discriminated result**, never a bare `false`.
- **QC-5** — self-heal accept/reject records **no** `generation_correction` (= OQ-2).
- **QC-6** — `daily_goal` moves to a **per-user** row `composition_progress_goal`, read-through-with-fallback
  to `work.settings.daily_goal`. **The writer only ever writes the new table** — the legacy window is closed
  **in the writer**, not by rewriting base schema. 🔴 **And "clear" is an UPSERT-to-NULL, never a DELETE**
  (§2 P2-CLEAR). 🔴 **And the legacy key is REDACTED at the MCP boundary** (§2 UNVERIFIED-2 / BE-P4).
- **QC-7** — no bespoke per-action estimate route (= OQ-3). 🔴 **Make it MECHANICAL, not a promise**
  (`Q-31-OQ3-PAID-ACTION-COST-GATE` item 4): add ONE test to the composition suite that introspects
  `app.main:app.routes` and asserts **no** route path under `/v1/composition/` contains `estimate` — the same
  FastAPI-introspection technique plan-30 §2 used to find the `add_api_route` blind spot a `@router.` grep
  misses. *"That single test is what actually stops the fourth 404 route from being born at 3am, and it costs
  ~10 lines."* Build it in **W1-07** (any BE slice will do; it is route-table-wide).
- **QC-8** — `usePolishProposals` stores proposals in the **react-query cache** under
  `['composition','self-heal', projectId, chapterId]` (`staleTime: Infinity`, **no `queryFn`** — the paid run
  is a `useMutation` that `setQueryData`s). `quality-critic` reads the same key with `useQuery({enabled:false})`.
  **Cache miss ⇒ `[]` ⇒ no badge** — a false badge is impossible.
  🔴 **TWO corrections the code forces** (`Q-31-QC8-GCTIME-EVICTION` + `QC-31-8-POLISHPROPOSALS-QUERYCACHE`):
  **(a) `gcTime: Infinity` is NOT optional, on BOTH observers.** `App.tsx:10` sets a global
  `gcTime: 5 * 60 * 1000`; `staleTime: Infinity` does **not** prevent GC. Run Polish in `quality-heal`, open
  `quality-critic` >5 min later with no observer in between ⇒ **the entry is evicted and the badge silently
  never appears.** **(b) `acceptedIds` lives IN the cache value, not in `useState`** — otherwise a dock-panel
  remount restores `proposals` + `ran:true` but resets acceptance to empty ⇒ `healedText === sourceText` ⇒
  **Apply burns an OCC draft bump writing back unchanged prose.** Half-cached state is a bug, not a smaller diff.
- **QC-9** — `quality-canon`'s `RuleRow` gains a **Dismiss** button (zero backend — the row already carries
  `job_id` + `rule_id`; `POST /jobs/{job_id}/dismiss-violation` exists at `engine.py:1684`).
  🔴 **And the agent gets `composition_dismiss_violation` in the SAME milestone** (§2 OQ-4 → **BE-11d**).
- **QC-10** — the chapter a quality panel operates on is chosen by **the panel's own picker**, defaulting to
  the manuscript hoist's active chapter, including the `chaptersTruncated` no-silent-cap notice.
  🔴 **EXTRACT, do not copy-paste** (`Q-31-QC10-CHAPTER-PICKER-CONVENTION`): lift
  `QualityCriticPanel.tsx:20,33-70` into ONE shared `panels/ChapterPicker.tsx` that **both** panels consume.
  *"One implementation, for every consumer… three independent re-derivations of one gate is exactly what
  SDK-First exists to stop"* (`useQualityWork.ts:1-2`). 🔴 **And fix the spec's factual slip:** QC-10 claims
  the shape "defaults to the manuscript hoist's active chapter" — **the code does not**
  (`QualityCriticPanel.tsx:31` inits `useState('')`). **Build the default INTO the shared picker**
  (seed-once from the studio bus, then stop following it — see W1-11).

---

## 3 · CODE FACTS — verified at HEAD `9262ed53e` on 2026-07-13. Build against THESE, not against a doc.

Everything below was opened and read. Where the audit or plan-30 was wrong, the correction is marked 🔴.

| # | Fact | Where |
|---|---|---|
| F1 | `canon_rule` HAS `book_id`, `kind`, `active`, `version`, `is_archived`. `CanonRulesRepo` has `create/list_active/list_all/get/update/archive` — **NO `restore`, and `list_all` hardcodes `NOT is_archived`**. | `app/db/migrate.py:245-262`, `app/db/repositories/canon_rules.py:88-97,155-166` |
| F2 | `GET /works/{pid}/canon-rules` takes only `active_only: bool`. By-id routes derive scope from the ROW via `_rule_project_id()` then `_require_work(EDIT)`. `PATCH` → 412 `{code:"CANON_VERSION_CONFLICT", current}`. | `app/routers/canon.py:108-189` |
| F3 | `composition_canon_rule_update` MCP only accepts `text` + `active` (**not** scope/entity/kind/window). `composition_canon_rule_delete` returns `undo_hint: None` with the comment *"there is no un-archive repo method"*. | `app/mcp/server.py:1111-1200` |
| F4 | 🔴 `generation_correction.job_id` is **`UUID NOT NULL REFERENCES generation_job(id)`**, and `GenerationCorrectionsRepo.create` **additionally** verifies `job.project_id == project_id` before writing. | `migrate.py:363-368`, `generation_corrections.py:88-98` |
| F5 | 🔴 **`authoring_run_units` has NO `job_id` column.** Columns: `run_id, unit_index, chapter_id, status, pre_revision_id, post_revision_id, cost_usd, error_message, critic_verdict, created_at, updated_at`. **Plan-30's BE-9 ("No schema change") CANNOT be built.** | `migrate.py:1493-1520` |
| F6 | 🔴 **`AuthoringRun` has NO `project_id`** — only `book_id`. The project is resolved *inside* `EngineDraftingSeam.draft_chapter` (`works.list_marked(book_id)`, `:316-325`). ⇒ the correction capture **must resolve `project_id` from the JOB row** (`GenerationJobsRepo.get(job_id).project_id`), never re-derive the Work. | `app/db/models.py:723-745`, `authoring_run_service.py:316-325` |
| F7 | `DraftOutcome` = `{ok, cost_usd, error}`. `draft_chapter` **reads `payload["job_id"]`** (`:377`), uses it for cost, and **throws the id away** (`:391`); `_poll_job` (`:395-411`) likewise. | `authoring_run_service.py:197-202, 360-411` |
| F8 | `RevisionCapture.latest_revision_id(created_by, book_id, chapter_id)` exists (real impl `BookRevisionCapture` → `BookClient.list_revisions(limit=1)`). This is the **edit-detection anchor**. | `authoring_run_service.py:222-260` |
| F9 | `BookClient.get_draft(book_id, chapter_id, bearer)` returns `{body, text_content, draft_version}` — **the current prose text** for `count_changed_blocks`. | `app/clients/book_client.py:111-118` |
| F10 | 🔴 `correction_stats` groups by `j.mode` over **every** `generation_job` in the project, with ONE exclusion (`NOT input->>'selection_edit'`). `mode='auto'` is the default for `self_heal_propose`, `quality_report`, `promise_coverage`, `decompose_preview`, `plan_pipeline`, `plan_forge_propose/_refine/plan_pass` — **none correctable.** Every PlanForge pass inflates the denominator. | `generation_corrections.py:170-236`; `plan.py:246,312,417,548,612`; `plan_forge_service.py:236,525,1170,1359` |
| F11 | 🔴 `GenerateBody.operation: str = "draft_scene"` and `GenerateChapterBody.operation: str = "draft_chapter"` are **client-settable free strings**, while `SelectionEditBody.operation` is `Literal["rewrite","expand","describe"]` and `mode` is `Literal["cowrite","auto"]`. The in-code comment at `engine.py:118-121` **already cites the LOOM-39 missing-enum lesson** — applied to the selection body, **not** to the two draft bodies. | `engine.py:90-150` |
| F12 | 🔴 **`mode` and `operation` are ORTHOGONAL. There is no such thing as "a cowrite op."** `draft_scene` + `mode='cowrite'` **IS** the panel's *Stream* column. The only exclusively-cowrite ops are `rewrite/expand/describe` = **selection edits**, the exact jobs the existing `/review-impl` exclusion removes. **An agent told to "enumerate the cowrite ops from engine.py" will grep, find that Literal, add all three, and silently revert the documented fix.** | `engine.py:98-99,122,141,1049,1080,1278-1307,825-846` |
| F13 | The existing `correction_stats` repo tests seed `operation="draft_scene"` (and `"rewrite"/"expand"` for the selection-edit test) — **all allowlist-compatible.** BE-9c will **not** red them. Verify anyway. | `tests/integration/db/test_repositories.py:2012-2100` |
| F14 | `POST /jobs/{job_id}/correction` (`engine.py:1712+`) computes `changed_blocks = count_changed_blocks(job.result["text"], body.edited_text)` and **422s `EDIT_NO_CHANGE` when it is 0** (*"a zero-change edit is an accept-as-is wearing an edit costume"*). **The new capture MUST mirror this.** | `engine.py:1712-1795` |
| F15 | `composition_daily_progress` PK `(user_id, project_id, chapter_id, snapshot_date)`; `composition_progress_baseline` PK `(user_id, project_id, chapter_id)`. **Neither has a `book_id` column.** The book grant is gated at the router by `_gate_book` **before** the repo. | `migrate.py:465-500`, `routers/progress.py:43-53,102-127` |
| F16 | 🔴 `daily_goal` is read from `work.settings` (`progress.py::_coerce_goal`) and written by `useSetDailyGoal` through `patchWork`, which **REPLACES the whole settings blob** with no If-Match. `composition_work.settings` is a **shared per-book row every EDIT grantee can write.** ⇒ **Alice's goal becomes Bob's.** Tenancy defect. | `progress.py:65-73,124`, `useProgress.ts:71-87`, `repositories/works.py:311` |
| F17 | `DailyProgressRepo.read_aggregate` **collapses the chapter dimension** before the router sees it (`GROUP BY snapshot_date`). | `daily_progress.py:82-144` |
| F18 | 🔴🔴 **`TiptapEditorHandle.setContent` SUPPRESSES `onUpdate`.** `setContentHandler` sets `isExternalUpdate.current = true` around `editor.commands.setContent(...)`, and `onUpdate` early-returns on that flag. **⇒ a heal applied via `setContent` alone does NOT dirty the hoist, so the user's ⌘S saves NOTHING and the heal silently vanishes on reload.** The legacy `ChapterEditorPage.handleApplyPolish` (`:591-602`) does exactly this. **`applyHealedDocument` MUST call the hoist's `setBody(doc, text)` itself.** This is the single most dangerous trap in the wave. | `TiptapEditor.tsx:171-174, 252-257`; `ChapterEditorPage.tsx:591-602` |
| F19 | `ManuscriptUnitApi` exposes exactly one AI write path: `applyProposedEdit({operation:'insert_at_cursor'\|'replace_selection', text, provenance})`. **Neither operation replaces the document.** Its doc-comment says it exists so *"future hoist-level bookkeeping has ONE chokepoint for 'an AI wrote into this chapter'"*. | `ManuscriptUnitProvider.tsx:86-97, 303-317` |
| F20 | `usePolishProposals` captures `draftVersion` (`:24`) and returns it (`:97`) — **and NO caller reads it.** `healedText = applySelfHealEdits(sourceText, ...)` where `sourceText` was fetched **at propose time**. In the dock, `quality-heal` is a **persistent tab that survives chapter switches**, next to a live dirty editor. | `usePolishProposals.ts:22-24, 89-109` |
| F21 | `QualityCriticPanel.tsx:80` renders `<QualityReportSection … />` **without `proposals`** → defaults `[]` (`QualityReportSection.tsx:39`) → `_hasProposedFix()` (`:30`) can never return true → the `violation-has-fix` badge (`:95`) is **unreachable dead code in the Studio.** | as cited |
| F22 | 🔴 **X-2 IS STILL OPEN.** `CATEGORY_ORDER` (`useStudioCommands.ts:20-22`) lists **9**; `StudioPanelCategory` (`catalog.ts:81-91`) defines **10**. `'quality'` is missing ⇒ `indexOf → -1` ⇒ the Quality group sorts **above `editor`**. `panelCatalogContract.test.ts` asserts a category is **present**, never that it is a **member of `CATEGORY_ORDER`**, and **nothing** asserts `guideBodyKey` (X-3). | as cited |
| F23 | 🔴 **X-1 IS STILL OPEN.** `AddModelCta.tsx` is a raw `<Link to="/settings/providers?return=…">` with **no `useOptionalStudioHost()` branch** ⇒ clicking it inside the dock **route-navigates the SPA and tears down the whole workspace.** `quality-heal` mounts a `ModelPicker`, whose empty state renders it. | `frontend/src/components/shared/AddModelCta.tsx` |
| F24 | **X-4: `compositionEffects.ts` does not exist.** `handlers/` contains only `bookEffects.ts`, `glossaryEffects.ts`, `knowledgeEffects.ts`, `translationEffects.ts`, `resultEnvelope.ts`. `registerEffectHandler`'s **string** branch is `tool === p \|\| tool.startsWith(p)` — **NOT a pattern match. Use a `RegExp` for anything with alternation.** Handler modules use a `let registered = false;` module guard. | `agent/effectRegistry.ts:32-47`, `handlers/glossaryEffects.ts:18-20` |
| F25 | `useStudioEffectReconciler.ts:8-9` carries a comment claiming *"authoring_run has no MCP tools at all, REST-only, no Studio consumer to go stale."* **`composition_authoring_run_start` IS an MCP tool and `agent-mode` IS a Studio consumer. Delete the comment.** | as cited |
| F26 | `ui_open_studio_panel`'s `panel_id` enum has **exactly 57** entries today (counted programmatically). `contracts/frontend-tools.contract.json` is **generated**, never hand-edited. | `chat-service/app/services/frontend_tools.py:400-402` |
| F27 | **Gateway: ZERO changes.** `gateway-setup.ts:350-354` proxies `/v1/composition/*` with a generic `pathFilter` and **no rewrite** — every new route is auto-proxied the moment it exists. | plan 31, verified |
| F28 | Playwright e2e specs live in **`frontend/tests/e2e/specs/`** (not `frontend/e2e/`). Existing studio specs: `studio-compose`, `studio-editor`, `studio-palette`, `studio-onboarding`, `writing-studio`. | `frontend/tests/e2e/specs/` |
| F29 | composition-service tests: `tests/unit/**` (no DB), `tests/integration/db/**` (real PG, gated on `TEST_COMPOSITION_DB_URL`, `pytestmark = pytest.mark.skipif(...)`). **A NEW test touching a real DB/port MUST add `pytest.mark.xdist_group("pg")`** or parallel workers interleave and the counts lie. | `tests/`, CLAUDE.md |
| F30 | `RuleViolationItem` already carries `{scene_id, scene_title, chapter_id, job_id, created_at, rule_id, rule_text, span, why}` — **`job_id` + `rule_id` are in hand**, so QC-9's Dismiss is zero-backend. | `features/composition/types.ts:92-102` |
| F31 | `CanonRule` TS type **omits `kind` AND `is_archived`** (`types.ts:345-354`). `CanonRulePayload` (`CanonRuleForm.tsx:11-18`) drops `kind`. **The agent can set `kind`; the human cannot.** | as cited |

### §3b — the facts the ADJUDICATION added (each one killed a wrong line in the pre-reconcile plan)

| # | Fact | Where |
|---|---|---|
| F32 | 🔴 **TWO SHIPPED FE FEATURES POST A NON-DEFAULT `operation` ON THE DRAFT ROUTE.** `useInlineGhost.ts:60` posts `operation:'continue'`; `ComposeView.tsx:73` posts `operation:'adapt_scene' as const` — both to `generateUrl` = `/works/{pid}/generate` = `GenerateBody`. **`Literal["draft_scene"]` would 422 them both.** The drafter's own registry `_OPERATION_INSTRUCTIONS` (cowrite.py:28-48) has SEVEN ops; the silent fallback at `cowrite.py:101` (`.get(operation, "Write the next passage of the scene.")`) is what makes an open `str` a bug. | `cowrite.py:28-48,101`; `useInlineGhost.ts:60`; `ComposeView.tsx:73`; `api.ts:389-399` |
| F33 | 🔴 **A THIRD OPEN `operation` SURFACE the spec never named:** `mcp/server.py:1356` `_GenerateArgs.operation: str \| None = None`, whose comment at `:1351-1355` **falsely claims** *"Literals mirror the engine's GenerateBody"*. It feeds `GenerateBody`/`GenerateChapterBody` at the **confirm-execute** seam (`actions.py:425,453,462`) ⇒ a bad op survives propose **and the user's PAID confirm**, then dies as a 400 at execute. | as cited |
| F34 | 🔴 **`services/mcp-public-gateway/src/scope/tool-policy.ts` IS DEFAULT-DENY / FAIL-CLOSED** (`:9`, `:340 isClassified`, `:368 filterTools` drops unclassified tools). **A new MCP tool with no row there is registered, unit-green, and SILENTLY UNREACHABLE at the public edge** — the built-but-unreachable class. `composition_outline_node_restore` carries its row at `:231`; `composition_canon_rule_delete` at `:236`. **There is NO parity test guarding this** (grepped — none exists), so nothing will catch the omission. **Every new tool in this wave needs a row.** | as cited |
| F35 | 🔴 **THE "3-SCHEMA-SOURCE FastMCP CAVEAT" DOES NOT APPLY TO composition-service.** That caveat is knowledge-service-specific (it has a bespoke `tools/definitions.py` hand-schema **plus** a pydantic arg model **plus** the FastMCP signature). `find services/composition-service -name definitions.py` → **nothing**. The `@mcp_server.tool` decorator is the **single** schema source. **A builder chasing three schema sources here will hunt two files that do not exist.** The real second surface is **F34**. | verified |
| F36 | 🔴 **`revert_all` BYPASSES `reject_unit`** — it calls `self._units.transition_unit(...)` **directly** at `authoring_run_service.py:1001`. A capture written only inside `accept_unit`/`reject_unit` records **NOTHING** on a Revert-All. | `authoring_run_service.py:960-1019` |
| F37 | 🔴 **THE TIPTAP ROUND-TRIP IS NOT IDENTITY.** `_heading_node` **strips** the `### ` prefix (`prose_doc.py:48,107`) and `tiptap_doc_to_text` reads `_text` back (`:127`) ⇒ comparing `job.result["text"]` (raw LLM prose, with ATX scene markers) against the chapter's TipTap `_text` reports **a diff on every heading line of an untouched chapter**. `book-service` **already exposes the right primitive**: `GET /internal/books/{b}/chapters/{c}/revisions/{r}/text` → `text_content` (`server.go:3364-3405`); composition's `BookClient` has `_internal_token` (`book_client.py:142`) but **no wrapper** — that wrapper is **unbuilt work to write**, not a blocker. Mirror `knowledge-service/app/clients/book_client.py:602`. | as cited |
| F38 | 🔴 **`_parse_local_date` (`progress.py:56-62`) validates FORMAT ONLY — no bound.** The client supplies its own local date (correctly — streaks must honour the writer's midnight, not UTC), but an **unbounded** client date lets a hand-crafted `today`/`date` **fabricate or inflate a streak** (`:117` → `_current_streak`; `:157` → `progress.report(...)` writes the row on that arbitrary date). Blast radius is the caller's own streak only (rows are per-user) ⇒ **not a tenancy defect and not a build gate** — but it is a 30-minute fix. | as cited |
| F39 | 🔴 **`composition_get_work` (`mcp/server.py:333`) returns `work.model_dump(mode="json")` — the WHOLE settings blob — to the LLM.** After BE-P2 that includes the **frozen legacy** `settings.daily_goal`, a stale SECOND HOME the model will happily report. And it is **sticky**: the two surviving full-blob writers (`useWork.ts:134-135`, `useChapterAssembly.ts:32-33` → `patchWork` → `works.py:311-313`, a full REPLACE) spread `...currentSettings`, so they **re-write the legacy key forever**. | as cited |
| F40 | 🔴 **SERVER-SIDE OCC ON `PATCH /works/{pid}` IS ALREADY SHIPPED** — `works.py:588` accepts `If-Match`, `:597` parses it, `:603-607` maps `VersionMismatchError` → `412 {"code":"WORK_VERSION_CONFLICT","current":…}`; `works.py:319-324` gates `WHERE version = $n` and bumps. **Plan 30:312 / spec 31:530's "NO If-Match" is FALSE.** BE-18 is therefore **FE-ONLY** and needs **no** jsonb `\|\|` merge — full-blob replace *under OCC* is the correct semantics (a `settings \|\| $n` merge would make key-**deletion** impossible). **Correct the row; touch nothing in `PATCH /works` this wave.** | as cited |
| F41 | 🔴 **`PolishPanel.test.tsx` renders BARE** (`render(<PolishPanel …/>)` at `:32`, `:45` — **no `QueryClientProvider`**) **and it MOCKS THE HOOK MODULE OUT ENTIRELY** (`vi.mock('../../hooks/usePolishProposals')`, `:8-11`). ⇒ **(a)** the instant the hook touches `useQuery`/`useMutation` those tests throw *"No QueryClient set"* — wrapping them is **part of the slice**, not a surprise; **(b)** that suite is **structurally blind to ANY hook rewrite** and **cannot be the regression gate.** There is **NO** `usePolishProposals` hook test today (27 hook tests in that dir, none for it). | as cited |
| F42 | 🔴 **`CATEGORY_ORDER` and `StudioPanelCategory` are TWO hand-maintained lists of ONE closed set — that is WHY they drifted.** And the i18n half is missing too: `en/studio.json` `palette.group` holds **13** keys with **no `quality`**, so the `group(p.category, p.category)` fallback (`useStudioCommands.ts:61-63`) renders the quality panels under a **raw lowercase `quality`** header while every sibling gets a real label. | `catalog.ts:81-91`; `useStudioCommands.ts:20-22,61-63`; `en/studio.json` |
| F43 | `CanonRule.kind` is `TEXT` with **NO CHECK constraint** (`migrate.py:254` — contrast `outline_node.kind:196` / `motif.kind:704`, which DO carry CHECKs); nothing downstream reads it (`packer/lenses.py:92-100 gather_canon` packs rule **text**, never `kind`). ⇒ **`kind` is a FREE-TEXT label. Render a text input; do NOT invent a closed set / `<select>`** — that would fabricate a taxonomy the backend does not have. The Frontend-Tool-Contract "closed-set ⇒ enum" rule applies to **tool args**, and there is no closed set here. | as cited |
| F44 | `getRuleViolations` is **CAPPED at `RULE_VIOLATIONS_CAP = 200`** (`repositories/outline.py:35`, `routers/outline.py:543`) and its exact `count` is the **BOOK-WIDE** total, not per-rule. ⇒ a per-rule count derived from a `capped: true` page is a **LOWER BOUND** — the paged-join-mislabels-absent class. **Never render "0 broken" from a truncated page.** | as cited |

---

## 4 · PRE-FLIGHT — run these EXACT commands before writing a line of code

```bash
# 0. Where am I?
git -C d:/Works/source/lore-weave-mvp status --short && git log --oneline -3
git diff --cached --name-only          # MUST be empty-or-known (a concurrent session may have pre-staged)

# 1. GATE X-2 — 'quality' in CATEGORY_ORDER?  (MUST print a line containing 'quality')
grep -n "CATEGORY_ORDER" -A 3 frontend/src/features/studio/palette/useStudioCommands.ts

# 2. GATE X-3 — is guideBodyKey asserted?  (MUST be NON-empty)
grep -n "guideBodyKey" frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts

# 3. GATE X-1 — is AddModelCta dock-safe?  (MUST print a useOptionalStudioHost line)
grep -n "useOptionalStudioHost\|openPanel" frontend/src/components/shared/AddModelCta.tsx

# 4. X-4 home — does compositionEffects.ts already exist? (MUST be absent; Wave 1 creates it)
ls frontend/src/features/studio/agent/handlers/

# 5. The enum baseline (record the number; the DoD asserts a DELTA from it, never a literal)
python scripts/../- ; # or inline:
python -c "import re; s=open('services/chat-service/app/services/frontend_tools.py',encoding='utf8').read(); i=s.index('\"panel_id\"'); j=s.index('\"enum\":',i); k=s.index(']',j); print('panel_id enum baseline =', len(eval(s[j+7:k+1])))"

# 6. UNVERIFIED-2 — who else reads work.settings.daily_goal? (JSONB keys are grep-hostile)
grep -rn "daily_goal" --include=*.py --include=*.ts --include=*.tsx services/ frontend/src/ | grep -v test

# 7. Baseline suites GREEN before you start (you cannot claim a regression you didn't measure)
cd services/composition-service && python -m pytest tests -q -n auto --dist loadgroup ; cd ../..
cd services/chat-service      && python -m pytest tests -q ; cd ../..
cd frontend && npx vitest run src/features/studio src/features/composition ; cd ..
```

### Gate outcomes — what to do with each (this is the "blocked ≠ stopped" instruction)

- **X-2 / X-3 RED and Wave 0 has NOT landed** ⇒ **do NOT stall and do NOT defer.** They are XS, they are a
  hard prerequisite of this wave's three `quality` panels, and CLAUDE.md's anti-laziness rule says missing
  infrastructure is *unbuilt work to implement*. → **build them as slice `W1-00`** (below).
  **If Wave 0 HAS landed** (the greps are green): **skip W1-00 entirely.** Do not double-implement.
- **X-1 RED** ⇒ same: **build it as slice `W1-01`.** It is a **hard gate on M3 only**, so M1/M2/M4 may
  proceed while it is pending — but **M3 must not start until it is green.** Shipping a `ModelPicker` whose
  empty-state CTA **destroys the user's whole workspace** is not acceptable.
- **X-4** ⇒ this wave **owns** `compositionEffects.ts` (plan 30 §8.0b). Create it in `W1-06`.
- **Enum baseline ≠ 57** ⇒ another wave landed first. **That is fine and expected.** Record the new number
  `N`. Every registration slice asserts `N_before + 1 == N_after` **and** the three-way equality. **Never
  write a literal count into a test** — a literal "sends a builder hunting a phantom regression."

---

## 5 · BACKEND PREREQUISITES — the route contracts (a panel slice may not precede its route slice)

**This section is a contract.** Every row was verified against code in §3.

| # | METHOD + path / change | Request | Response | Errors | Slice |
|---|---|---|---|---|---|
| **BE-11a** | `POST /v1/composition/canon-rules/{rule_id}/restore` | — | the `CanonRule` row (`is_archived:false`) | `404` missing / not-in-scope / **not archived** · `403` under-tier | W1-02 |
| **BE-11b** | `GET /v1/composition/works/{pid}/canon-rules?include_archived=<bool>` (keep `active_only`) | — | `{rules: CanonRule[]}`, each carrying `is_archived` + `kind` | `404`/`403` as today | W1-02 |
| **BE-11c** | MCP `composition_canon_rule_restore` (Tier A) | `{project_id, rule_id}` | the row + `_meta.undo_hint = {tool:'composition_canon_rule_delete', args:{project_id, rule_id}}` | uniform `not_accessible` | W1-03 |
| **BE-11c′** | MCP `composition_canon_rule_delete` — **add** `_meta.undo_hint = {tool:'composition_canon_rule_restore', args:{…}}` (today honestly `None` *because no un-archive existed*) | — | — | — | W1-03 |
| 🔴 **BE-11d** *(NEW — §2 OQ-4)* | MCP `composition_dismiss_violation` (Tier A) — the agent-side twin of QC-9's human button | `{project_id, job_id, rule_id}` | `{critic, _meta.undo_hint: null}` | uniform `not_accessible` (foreign job · unknown rule_id) | W1-03 |
| 🔴 **BE-11e** *(NEW — F34)* | `services/mcp-public-gateway/src/scope/tool-policy.ts` — a `{ tier: 'write_auto', domains: ['composition'] }` row for **each** of `composition_canon_rule_restore`, `composition_dismiss_violation`, `composition_record_correction` | — | — | — | W1-03 / W1-15 |
| **BE-P2** | `PUT /v1/composition/works/{pid}/progress/goal` | `{goal: int}` (`0` clears → **the row is UPSERTed with `daily_goal = NULL`, never deleted**) | `{goal: int\|null, source: 'user'\|'work_legacy'\|'none'}` — the **RESOLVER's** output, not an echo | `422` `goal < 0` · `404`/`403` | W1-07 |
| **BE-P2′** | `GET /v1/composition/works/{pid}/progress` — **widen** | — | `+ daily_goal_source: 'user'\|'work_legacy'\|'none'` (closed set — **no 4th value for "cleared"**: under SET-1 the effective value IS none) | — | W1-07 |
| **BE-P1** | `GET /v1/composition/works/{pid}/progress` — **widen** | — | `+ by_chapter: [{chapter_id, words}]` — words authored **on the anchor date**, `words > 0` only, desc. **No chapter titles on the wire** — composition does not own chapters; the router adds **no** `book_client` call. | — | W1-07 |
| 🔴 **BE-P3** *(NEW — F38)* | `GET /works/{pid}/progress?today=` + `POST /works/{pid}/progress/report` — **CLAMP the client-supplied local date to ±1 day of the server's UTC date** (real offsets span UTC-12..UTC+14) | — | — | **`422`** outside the window (never a silent clamp-to-nearest — that would write the snapshot to a day the user did not write on) | W1-07 |
| 🔴 **BE-P4** *(NEW — F39)* | MCP `composition_get_work` — **REDACT `settings.daily_goal`** from the dumped blob (SET-3: one home, one name) | — | — | — | W1-07 |
| **BE-9c** | `GenerationCorrectionsRepo.correction_stats` — **operation allowlist** on the denominator. 🔴 **FOUR ops** (`+ adapt_scene`, §2 9c-OPS). **KEEP `NOT selection_edit` — ADD to it, never replace it.** | — | same shape | — | W1-13 |
| **BE-9c′** | `GenerateBody.operation` → 🔴 `Literal["draft_scene","continue","adapt_scene"]` · `GenerateChapterBody.operation` → `Literal["draft_chapter"]` · 🔴 `mcp/server.py:1356 _GenerateArgs.operation` → the union (F33) | — | — | `422` on an unregistered op | W1-13 |
| **BE-9a** | DDL `authoring_run_units.job_id` + `DraftOutcome.job_id` + the driver persist. 🔴 `upsert_pending`'s `ON CONFLICT DO UPDATE` must **reset `job_id = NULL`** (a resumed/re-run unit must NOT inherit the previous attempt's job — that names the wrong generation in a correction). | — | — | — | W1-14 |
| **BE-9b** | correction capture inside `accept_unit`/`reject_unit` 🔴 **AND `revert_all`** (F36) + MCP `composition_record_correction` (Tier A) | tool: `{project_id, job_id, kind, guidance?, edited_text?, chosen_candidate_index?}` — `kind` is a **closed `Literal`** of the 4 DB values (`accept` **does not exist**) | `{correction_id}`; and the accept/reject **response** carries `correction: {status, correction_id}` (no silent success) | `404` job not in project · `422` `kind='edit'` with identical text | W1-15 |
| 🔴 **BE-9e** *(NEW — anti-drift)* | **EXTRACT** `engine.py:1712-1790`'s correction body into `app/services/correction_capture.py::capture_correction(...)` and call it from **all three** consumers (the REST route, the new MCP tool, the accept/reject seam) — so the 422 rule, the opt-in-prose rule, and `winner_index`/`candidate_count` have **ONE home**. **Do NOT "mirror" it — a mirrored copy is a guaranteed drift** (the `css-var-duplicated-across-two-consumers` class). | — | — | — | W1-15 |
| 🔴 **BE-CONTRACT** *(NEW — CLAUDE.md "contract-first")* | `contracts/api/composition/v1/openapi.yaml` — every new/widened route above, **frozen BEFORE the FE slices that consume them** | — | — | — | **W1-CONTRACT** |

**EXISTS — verified, ZERO work:** `GET|POST /works/{pid}/canon-rules` · `PATCH|DELETE /canon-rules/{id}`
(If-Match OCC → 412 `CANON_VERSION_CONFLICT`) · `GET /works/{pid}/canon-issues` ·
`GET /works/{pid}/rule-violations` · `POST /jobs/{job_id}/dismiss-violation` ·
`POST /jobs/{job_id}/correction` · `GET /works/{pid}/correction-stats` ·
`POST /works/{pid}/self-heal/propose` · `GET|POST /works/{pid}/progress{,/report,/baseline}` ·
the 4 `composition_canon_rule_*` MCP tools · the generic `/actions/preview` + `/actions/confirm` spine.

**Gateway: ZERO changes** (F27) — `gateway-setup.ts:350-354` proxies `/v1/composition/*` with a generic
`pathFilter` and no rewrite. Every new route above is auto-proxied the moment it exists.

🔴 **BUT THAT CLAIM SILENTLY DEPENDS ON FOUR CONDITIONS** (`Q-31-GATEWAY-ZERO-CHANGES`). They are **binding
rules for every builder in this wave**:

1. **MOUNT UNDER THE PREFIX.** Every new FE-reachable route MUST live on a router declared
   `APIRouter(prefix="/v1/composition")` (or a sub-prefix) and be registered via `app.include_router(...)` in
   `app/main.py` (the block at `:215-245`). **Do NOT invent `/v1/studio/*` or `/v1/quality/*`** — the gateway
   matches the **LITERAL** prefix, so such a route falls through to `next()` (`gateway-setup.ts:666`) and
   **404s at the edge while every composition-service unit test stays green.** *This is the only way to get
   the "no gateway work" claim wrong.*
2. **AUTH IS PER-ROUTE, IN THE SERVICE — NOT AT THE GATEWAY.** The proxy forwards `Authorization` **raw** and
   verifies **nothing**. Every new `/v1/composition/*` route MUST declare `Depends(get_current_user)` and,
   where a book/project is addressed, the grant gate. **Omitting them ships a PUBLIC UNAUTHENTICATED route (a
   tenancy defect) and no gateway layer will catch it.**
3. **SSE needs no work** (`selfHandleResponse: false`); edge rate-limiting is global and automatic.
4. **`/internal/*` IS DELIBERATELY NOT PROXIED** — the dispatcher has no `/internal` branch. An FE-reachable
   route must be `/v1/composition/*`.

**PIN IT WITH A TEST (W1-07, ~10 lines, cheap):** a route-table test in composition-service asserting **every**
router in `main.py`'s public `include_router` list carries a path starting `/v1/composition`. That converts a
verified-once claim into a standing guard against rule #1. *(Pair it with QC-7's `no route contains "estimate"`
assertion — same introspection, same file.)*

---

## 6 · MIGRATIONS

Both live in `services/composition-service/app/db/migrate.py` — this service migrates by running one
idempotent DDL script at boot. **There is no per-file migration directory.** Append to the script and add an
assertion to `tests/integration/db/test_migrate.py`.

### M-A · `authoring_run_units.job_id` (BE-9a — slice W1-14)

Place it **immediately after** the existing D5 additive column
(`ALTER TABLE authoring_run_units ADD COLUMN IF NOT EXISTS critic_verdict JSONB;`, `migrate.py:~1521`):

```sql
-- D-31 M4 (BE-9a): the generation_job the unit's draft came from — the correction
-- flywheel's attachment point (generation_correction.job_id is NOT NULL, so without
-- this there is literally nothing to attach the human's rejection to).
-- NULLABLE BY DESIGN: units drafted before this column existed have no job, and there
-- is no honest way to recover it.
--   ⚠ NEVER BACKFILL A GUESS. A wrong job_id attributes THIS author's rejection to
--   SOMEONE ELSE'S generation and poisons the learning store. NULL = "not recorded":
--   accept/reject SKIP the capture and the Run Report SAYS SO.
-- No FK to generation_job: the capture is best-effort telemetry — a dangling id must
-- degrade to "skip", never to a 500 on the review the author is trying to do.
ALTER TABLE authoring_run_units ADD COLUMN IF NOT EXISTS job_id UUID;
```

- **Additive.** No backfill, **no default**, no CHECK change, nothing dropped or rewritten.
- ⚠ CLAUDE.md memory: **`ADD COLUMN IF NOT EXISTS` never revisits a bad default on an already-migrated DB.**
  That is precisely why this column has **no** default — the only correct value for a historical row is NULL.
- **Test** (`test_migrate.py`): the column exists and `information_schema.columns.is_nullable = 'YES'`.

### M-B · `composition_progress_goal` (BE-P2 — slice W1-07)

Place it **immediately after `composition_progress_baseline`** (`migrate.py:~496`):

```sql
-- ── composition_progress_goal: D-31 M2 (BE-P2) — the author's PER-USER daily word goal.
-- It used to live in composition_work.settings.daily_goal — a SHARED per-book row every
-- EDIT grantee can write — while the word COUNTS it is measured against are PER-USER
-- (composition_daily_progress, PK (user_id, project_id, chapter_id, snapshot_date)).
-- So Alice set a goal and Bob's panel measured Bob against it. That is CLAUDE.md's
-- User-Boundaries kinds-bug shape: "would two users want different values? yes ⇒ USER
-- SETTING." It is a tenancy defect, not a preference.
--   ⚠ NO book_id COLUMN — deliberately. Neither sibling (composition_daily_progress,
--   composition_progress_baseline) has one: the E0 book grant is enforced at the ROUTER
--   (_gate_book) BEFORE the repo, and this row is never read by book. A book_id here
--   would be WRITTEN AND NEVER READ — the write-only bug class this very spec exists to
--   kill. Do not add one "for symmetry".
-- 🔴 daily_goal IS NULLABLE, DELIBERATELY (Q-31-P2-CLEAR-SEMANTICS). The ROW'S EXISTENCE is
--    the per-user tier claim; its VALUE is the goal. NULL = the user explicitly CLEARED their
--    goal, and the row STILL SHADOWS work.settings.daily_goal.
--    ⚠ NEVER DELETE THE ROW ON CLEAR. A DELETE re-exposes the legacy per-book goal — so Bob
--      clearing HIS goal would resurrect ALICE'S shared book goal and measure Bob's counter
--      against it. That is the EXACT tenancy defect this table exists to kill, re-entered
--      through the clear path. (Postgres CHECK passes on NULL: `NULL > 0` → UNKNOWN → passes.
--      No NOT NULL, and `0` is NEVER stored — the route coerces 0 → NULL at the boundary.)
-- work.settings.daily_goal becomes READ-ONLY LEGACY: GET /progress falls back to it and
-- reports daily_goal_source='work_legacy'; the WRITER never touches it again. Closing the
-- legacy window IN THE WRITER (not by rewriting base schema) is deliberate — no user who
-- already set a goal silently loses it, and the migration TEST can still seed legacy shape.
CREATE TABLE IF NOT EXISTS composition_progress_goal (
  user_id     UUID NOT NULL,
  project_id  UUID NOT NULL,
  daily_goal  INT  CHECK (daily_goal > 0),        -- NULLABLE: NULL = explicitly cleared
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, project_id)
);
```

- **Additive. No backfill.** A legacy goal keeps being served via the read-through fallback.
- 🔴 **ANTI-INSTRUCTION — do NOT write a migration that deletes `daily_goal` from
  `composition_work.settings`.** That key **IS** the read-through fallback QC-6 relies on (*"no existing user
  loses a goal"*, `daily_goal_source: 'work_legacy'`). Dropping it is **data loss** and trips the plan's
  CRITICAL-blocker rule. Leave the stored key alone: close the window in the **WRITER**, hide it at the **MCP
  read** (BE-P4). Keep `tests/unit/test_progress_router.py:125-129,145-156` GREEN — they encode the legacy
  fallback BE-P1/P2 must preserve.
- **No partial index** ⇒ no `ON CONFLICT`-predicate hazard (the memory
  `postgres-partial-index-on-conflict-predicate-must-match` does not bite). The upsert is
  `ON CONFLICT (user_id, project_id) DO UPDATE`, matching the **full** PK. *(⚠ `DO UPDATE`, **not**
  `DO NOTHING` — do not copy `composition_progress_baseline`'s `ON CONFLICT DO NOTHING`; a goal is re-settable.)*
- **Test** (`test_migrate.py`): the table exists; PK is `(user_id, project_id)`; `daily_goal = 0` raises
  `asyncpg.CheckViolationError`; 🔴 **`daily_goal = NULL` INSERTs fine** (the clear path); **no `book_id`
  column** (assert the column list — a later agent will want to add one "for symmetry").

---

## 7 · THE SLICES — each slice is ONE commit

**TDD order in every slice: the failing test FIRST, then the implementation.**
Test commands (memorize them):

```bash
# composition-service (unit, no DB)
cd services/composition-service && python -m pytest tests/unit -q -n auto --dist loadgroup
# composition-service (FULL — the VERIFY gate)
cd services/composition-service && python -m pytest tests -q -n auto --dist loadgroup
# chat-service contract
cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
# frontend
cd frontend && npx vitest run src/features/studio src/features/composition
# the 4 drift-locks (run after EVERY registration slice)
cd frontend && npx vitest run \
  src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
  src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
  src/features/studio/palette/__tests__/useStudioCommands.test.ts \
  src/features/chat/nav/__tests__/frontendToolContract.test.ts
```

⚠ **Any NEW composition-service test that touches a real DB/port MUST carry
`pytestmark = pytest.mark.xdist_group("pg")`** (add it alongside the existing
`pytest.mark.skipif(TEST_COMPOSITION_DB_URL…)` in `tests/integration/db/*`), or parallel workers interleave
and the counts lie.

---

### `W1-00` — GATE: X-2 (`CATEGORY_ORDER`) + X-3 (`guideBodyKey`) [CONDITIONAL]

> **Run this slice ONLY if pre-flight checks 1 & 2 are RED.** If Wave 0 already landed them, **skip.**
> **dependsOn:** — · **kind:** FE

**Files**

🔴 **PATCH THE CAUSE, NOT THE SYMPTOM** (`X-31-2-CATEGORY-ORDER-QUALITY`). The union type and
`CATEGORY_ORDER` are **two hand-maintained lists of the same closed set — that is WHY they drifted** (F42).
Adding `'quality'` to the array fixes today's bug and leaves tomorrow's in place. **Make the order the SSOT,
and fix the i18n half the spec missed.** Four edits, in this order, ONE commit:

1. **`frontend/src/features/studio/panels/catalog.ts:81-91`** — replace the standalone union with a const
   array + a derived type (**keep the union's existing order** — `quality` sits between `knowledge` and
   `translation` in the type; the *display* order is `CATEGORY_ORDER`'s job and is unchanged by this):
   ```ts
   export const STUDIO_PANEL_CATEGORIES = [
     'editor', 'storyBible', 'knowledge', 'quality', 'translation',
     'enrichment', 'sharing', 'platform', 'discovery', 'jobs',
   ] as const;
   export type StudioPanelCategory = (typeof STUDIO_PANEL_CATEGORIES)[number];
   ```

2. **`frontend/src/features/studio/palette/useStudioCommands.ts:4,20-22`** — **DERIVE** `CATEGORY_ORDER`.
   Change the type-only import to a **value** import and **delete the hand-written array**:
   ```ts
   import { STUDIO_PANEL_CATEGORIES, type StudioPanelDef, type StudioPanelCategory } from '../panels/catalog';
   export const CATEGORY_ORDER: readonly StudioPanelCategory[] = STUDIO_PANEL_CATEGORIES;
   ```
   No import cycle (`useStudioCommands` already depends on `catalog`; `catalog` does not import it).
   `readonly` is safe for all three consumers: `.indexOf` (`:55-57`), `.filter`/`.includes` +
   `(typeof CATEGORY_ORDER)[number]` (`UserGuidePanel.tsx:24-25`).
   ⚠ **The failure modes are INVERTED**: a category *missing from the type* sorts LAST; a category *present
   in the type but absent from `CATEGORY_ORDER`* returns `indexOf → -1` and sorts **FIRST**. Today's shipped
   `quality` hub therefore already sorts **above `editor`**, while `UserGuidePanel`'s `rest` bucket appends it
   **LAST** — the two surfaces disagree. Deriving one from the other aligns both, permanently.

1b. 🔴 **i18n — THE HALF THE SPEC MISSED (F42).** `frontend/src/i18n/locales/en/studio.json` →
   `palette.group` holds **13** keys and has **no `quality`**, so the `group(p.category, p.category)`
   fallback (`useStudioCommands.ts:61-63`) renders the **five** quality panels under a raw lowercase
   `quality` header while every sibling gets a real label. **Add `"quality": "Quality"` under
   `palette.group`**, then propagate with `python scripts/i18n_translate.py`. (en-only is acceptable if the
   tool is unavailable — `i18n/index.ts:48` sets `fallbackLng: 'en'`.)

3. **`frontend/src/features/studio/panels/__tests__/panelCatalogContract.test.ts`** — the existing test
   (`:40-43`) asserts only that a category **EXISTS**, never that it is a **MEMBER** of the order — *exactly
   the hole this bug fell through.* Add **FOUR** assertions:
   ```ts
   import { CATEGORY_ORDER } from '../../palette/useStudioCommands';
   import { STUDIO_PANEL_CATEGORIES } from '../catalog';
   import { readFileSync } from 'fs'; import { resolve } from 'path';   // already imported at :1-2

   // X-2 — a category in the type but NOT in CATEGORY_ORDER sorts FIRST (indexOf -1), silently
   // jumping the whole group above `editor`.
   it('every palette-openable panel category is in CATEGORY_ORDER (else indexOf → -1 and it sorts ABOVE editor)', () => {
     const orphan = OPENABLE_STUDIO_PANELS.filter((p) => !CATEGORY_ORDER.includes(p.category!)).map((p) => p.id);
     expect(orphan).toEqual([]);
   });
   it('CATEGORY_ORDER covers the whole category set exactly once', () => {
     expect([...new Set(CATEGORY_ORDER)]).toEqual([...STUDIO_PANEL_CATEGORIES]);
   });

   // X-3 (part 1) — a missing guideBodyKey silently drops a panel from the User Guide.
   it('every palette-openable panel has a guideBodyKey (X-3)', () => {
     const missing = OPENABLE_STUDIO_PANELS.filter((p) => !p.guideBodyKey).map((p) => p.id);
     expect(missing).toEqual([]);
   });

   // 🔴 X-3 (part 2) — PRESENCE ALONE DOES NOT CLOSE THE BUG CLASS. UserGuidePanel.tsx:120 calls
   // t(key, { defaultValue: '' }) → a DANGLING key renders an empty string, silently. Resolve every
   // key against the en locale. (X-31-3-GUIDEBODYKEY: write BOTH, not just the field check.)
   it('every guideBodyKey resolves to non-empty copy in en/studio.json (X-3)', () => {
     const studio = JSON.parse(readFileSync(resolve(process.cwd(), 'src/i18n/locales/en/studio.json'), 'utf-8'));
     const lookup = (k: string) => k.split('.').reduce<unknown>((o, s) => (o as Record<string, unknown> | undefined)?.[s], studio);
     const dangling = OPENABLE_STUDIO_PANELS
       .filter((p) => typeof lookup(p.guideBodyKey!) !== 'string' || !(lookup(p.guideBodyKey!) as string).trim())
       .map((p) => p.id);
     expect(dangling).toEqual([]);
   });
   ```

4. 🔴 **FIX THE ONE PRE-EXISTING VIOLATOR — the X-3 assertion REDS ON MAIN, and that is the POINT.**
   Of 68 catalog rows, **12** lack `guideBodyKey`; **11** are `hiddenFromPalette: true` (correctly excluded —
   `OPENABLE_STUDIO_PANELS` filters them, `catalog.ts:279`). **Exactly ONE openable row is missing it:
   `agent-mode` at `catalog.ts:258`.** Add `guideBodyKey: 'panels.agent-mode.guideBody'` to that row **and**
   the matching `"guideBody"` string under `panels."agent-mode"` in `en/studio.json` (today `:472-475` has
   `title` + `desc` only). Copy: one plain sentence on what the panel does + one on when to open it — match
   the voice of `panels.compose.guideBody` (`studio.json:22`).
   ⚠ **KEEP `guideBodyKey?: string` OPTIONAL in `StudioPanelDef`** (`catalog.ts:105`) — making it required
   breaks the 11 legitimate `hiddenFromPalette` rows. **The mandate is enforced at the TEST layer, scoped to
   `OPENABLE_STUDIO_PANELS`** — exactly like the `category` assertion above it.

**TDD order.** Write the four tests first → the `CATEGORY_ORDER` membership one **REDS**
(`['quality-canon:quality', …]`) and the `guideBodyKey`-resolves one **REDS** on `agent-mode`. Then do edits
1/1b/2/4 → green.

**DoD evidence:** `cd frontend && npx vitest run src/features/studio/panels/__tests__/panelCatalogContract.test.ts`
green with 6 tests. 🔴 **PROVE THE GUARDS BITE:** revert edit (1)'s `'quality'` entry ⇒ the membership test
reds; revert the `agent-mode` `guideBodyKey` line ⇒ the resolve test reds. **Paste both red runs and the final
green.** *A guard that cannot fail is not a guard.*

---

### `W1-01` — GATE: X-1 — `AddModelCta` DOCK-7 (the dock-destroying button) [CONDITIONAL]

> **Run ONLY if pre-flight check 3 is RED.** **Hard gate on M3.** **dependsOn:** — · **kind:** FE

**File:** `frontend/src/components/shared/AddModelCta.tsx` — **fix at the SHARED component, NEVER at the
~8 call sites.**

**The change.** Today the component is a raw `<Link to="/settings/providers?return=…">`. Inside the studio
dock, a route hop **unmounts the whole `StudioFrame`** — every open panel, every in-flight edit, the chat
stream. Add an optional-host branch:

```tsx
import { useOptionalStudioHost } from '@/features/studio/host/StudioHostProvider';
// ...
export function AddModelCta({ returnTo, capability, label, variant = 'button', className }: Props) {
  const location = useLocation();
  // DOCK-7 — inside the studio, a <Link> route-hop TEARS DOWN the dock (every panel, every unsaved
  // edit, the chat stream). Open the settings PANEL instead, on the providers tab. Outside the studio
  // the hook returns null and the <Link> fallback is correct. Precedent: glossary-translate/StepConfig.
  const host = useOptionalStudioHost();
  // ... existing `to` / `text` derivation unchanged ...
  if (host) {
    return (
      <button
        type="button"
        data-testid="add-model-cta"
        onClick={() => host.openPanel('settings', { params: { tab: 'providers' } })}
        className={/* the SAME classes the <Link> variant uses, per `variant` */}
      >
        <Plus className="h-3.5 w-3.5" /> {text}
      </button>
    );
  }
  return (/* the existing <Link> — unchanged */);
}
```

**⚠ `useOptionalStudioHost` must exist and must NOT throw outside a provider.** Check
`frontend/src/features/studio/host/StudioHostProvider.tsx`. If only a throwing `useStudioHost` exists, add:
```ts
export function useOptionalStudioHost(): StudioHost | null { return useContext(StudioHostContext); }
```
(`useContext` of a context whose default is `null` — never a throw.)

**Also confirm `settings` panel honours `params.tab`.** Open
`frontend/src/features/studio/panels/SettingsPanel.tsx` — if it ignores `props.params`, wire
`params.tab === 'providers'` to select the Providers tab. **A CTA that opens the panel on the wrong tab is
the silent-no-op class again** — the button must land the user where a model is registered.

**Tests** — `frontend/src/components/shared/__tests__/AddModelCta.test.tsx` (exists):
- `renders a Link outside the studio (route hop is correct there)` — existing test, must stay green.
- **NEW** `inside a StudioHost, clicking calls host.openPanel('settings', {params:{tab:'providers'}}) and does NOT navigate`
  — render inside a mock `StudioHostProvider` with a spy `openPanel`; assert the spy call **and**
  `expect(screen.queryByRole('link')).toBeNull()`.

**DoD evidence:** `AddModelCta.test.tsx` N passed; plus the **DOCK-7 live-browser regression** in `W1-17`
(open `quality-heal` on a model-less account, click the CTA, assert the dock is still mounted).

---

### `W1-CONTRACT` — 🔴 FREEZE THE API CONTRACT (CLAUDE.md: *"Contract-first: API contract frozen before frontend flow"*)

> **dependsOn:** — · **kind:** CONTRACT
> **This slice MUST land before `W1-04` / `W1-08` (the FE slices that consume these routes).** It may run in
> parallel with `W1-02` / `W1-07` (the BE slices that implement them) — the contract is the agreement, the
> route is the implementation, and they are written from the same §5 table.

**File (verified — do NOT guess): `contracts/api/composition/v1/openapi.yaml`.**
It is a **live, maintained** spec (~17 paths) and it **already carries `/canon-rules/{rule_id}`** with
`patch` + `delete`. ⚠ **`contracts/api/composition-service/plan-forge.v1.yaml` is a SEPARATE file — it is
Wave 5's home. Do not write into it.** ⚠ There is **no** `contracts/api/book-service/` (that path is a
phantom other wave plans repeat; the real one is `contracts/api/books/v1/openapi.yaml`) — **this wave touches
neither.**

**The edits — one per §5 row:**

| # | Path | Change |
|---|---|---|
| 1 | `POST /canon-rules/{rule_id}/restore` | **NEW.** `tags: [canon]`, `summary: Un-archive a soft-archived rule (the inverse of DELETE)`. Params: `rule_id` (path, uuid). **No request body.** `'200'` → `$ref: '#/components/schemas/CanonRule'` (the FULL row — the FE's undo-toast needs `version` back to keep issuing If-Match PATCHes; follow `outline.py:648`'s restore, **not** `arc.py:528`'s `{id, archived}` stub). `'404'` → `$ref: NotFound` — **covers all three misses (missing · other project · NOT archived)**, per the no-enumeration-oracle discipline. `'403'` → under-tier. |
| 2 | `GET /works/{project_id}/canon-rules` | **WIDEN.** Add `- { name: include_archived, in: query, schema: { type: boolean, default: false } }` beside the existing `active_only`. **Document the precedence in the summary:** *"`active_only=true` WINS and ignores `include_archived` — 'enforceable only' and 'include archived' are contradictory; there is no combined 4th mode."* |
| 3 | `components.schemas.CanonRule` | **WIDEN.** Add `kind: { type: string, nullable: true }` and `is_archived: { type: boolean }`. **The backend has ALWAYS returned both** (`_SELECT_COLS`, `canon_rules.py:25-28`; `models.py:293`) — the contract and the TS type both dropped them (F31). `CanonRuleCreate` already has `kind`; **add `active: { type: boolean }`** there too if absent. |
| 4 | `GET /works/{project_id}/progress` | **NEW to the contract** (the route ships today, undocumented). Params: `ProjectId` + `- { name: today, in: query, required: true, schema: { type: string, format: date }, description: "the CLIENT'S LOCAL date (streaks honour the writer's midnight, not UTC) — BOUNDED server-side to ±1 day of the UTC date" }`. `'200'` → `$ref: ProgressStats`. **`'422'`** → `date outside the ±1-day window` (BE-P3). |
| 5 | `PUT /works/{project_id}/progress/goal` | **NEW.** Body `$ref: ProgressGoalBody` = `{ goal: { type: integer, minimum: 0, maximum: 1000000 } }`, `required: [goal]`, described: **"`0` CLEARS the goal (the row is upserted with a NULL value — it is never deleted, because a delete would re-expose the book's shared legacy goal)."** `'200'` → `$ref: ProgressGoalResolved`. `'422'` → `goal < 0`. `'404'` → NotFound. `'403'` → under-tier. |
| 6 | `POST /works/{project_id}/progress/report` | **NEW to the contract** (ships today; its error contract CHANGES this wave). Body `{ chapter_id: uuid, words: int, date: date }`. `'200'`. **`'422'`** → `date outside the ±1-day window` (BE-P3). |
| 7 | `GET /works/{project_id}/correction-stats` | **NEW to the contract** (ships today; it is `quality-corrections`' ONLY read). `'200'` → `$ref: CorrectionStats`. Document the denominator **in the schema description**: *"counts DRAFT generations only (`draft_scene`, `draft_chapter`, `stitch_chapter`, `adapt_scene`) — plan passes, quality reports, coverage runs and Polish proposals are NOT drafts and are excluded (BE-9c)."* |

**New `components.schemas` entries:**

```yaml
    ProgressStats:
      type: object
      properties:
        today:        { type: string, format: date }
        today_words:  { type: integer }
        book_total:   { type: integer }
        daily_goal:   { type: integer, nullable: true }
        # SET-1 — the EFFECTIVE value AND ITS SOURCE TIER. No silent hidden default.
        # CLOSED SET of 3. There is deliberately NO 4th value for "cleared": under SET-1 the
        # effective value of a cleared goal IS none, so 'none' is honest and the FE needs zero
        # new branching.
        daily_goal_source: { type: string, enum: [user, work_legacy, none] }
        # BE-P1 — words authored ON the anchor date, per chapter. words > 0 only, DESC.
        # No chapter TITLES: composition-service does not own chapters. The FE maps id → title.
        by_chapter:
          type: array
          items:
            type: object
            properties:
              chapter_id: { type: string, format: uuid }
              words:      { type: integer }
        current_streak: { type: integer }
        sparkline:      { type: array, items: { type: object } }
    ProgressGoalBody:
      type: object
      required: [goal]
      properties:
        goal: { type: integer, minimum: 0, maximum: 1000000, description: "0 clears (row upserted to NULL, NEVER deleted)" }
    ProgressGoalResolved:
      type: object
      description: >
        The RESOLVER's output, not an echo of the request. Clearing a user goal may fall through to a
        legacy per-book goal — the panel must be TOLD, not left to guess (no silent hidden default).
      properties:
        goal:   { type: integer, nullable: true }
        source: { type: string, enum: [user, work_legacy, none] }
    CorrectionStats:
      type: object
      additionalProperties:
        type: object
        properties:
          generations:        { type: integer }
          accept_rate:        { type: number, nullable: true }
          edit_rate:          { type: number, nullable: true }
          pick_different_rate:{ type: number, nullable: true }
          regenerate_rate:    { type: number, nullable: true }
          reject_rate:        { type: number, nullable: true }
          avg_edit_blocks:    { type: number, nullable: true }
```

**Tests / DoD.** This repo has no OpenAPI lint gate wired into CI, so the contract is enforced by **review +
one mechanical check**:
- `python -c "import yaml,sys; yaml.safe_load(open('contracts/api/composition/v1/openapi.yaml'))"` → parses.
- Every path added above appears in the file (`grep -n "progress/goal\|canon-rules/{rule_id}/restore\|correction-stats\|daily_goal_source\|by_chapter" contracts/api/composition/v1/openapi.yaml` → **6+ hits**).
- 🔴 **The route-table test from §5 (`every public router is under /v1/composition`) is this slice's real
  teeth** — it is what stops an implementation from drifting off the contracted prefix.

**DoD evidence:** *"contracts/api/composition/v1/openapi.yaml: +2 paths (canon-rule restore, progress/goal),
+3 documented (progress, progress/report, correction-stats), +4 schemas, CanonRule += kind/is_archived;
yaml parses; grep shows all 6 tokens."*

---

## M1 — CANON RULES (closes `G-CANON-RULE-CRUD`, P0) · enum `N` → `N+1`

### `W1-02` — BE-11a/b: canon-rule **restore** + **include_archived**

> **dependsOn:** — · **kind:** BE

**Files**

1. **`services/composition-service/app/db/repositories/canon_rules.py`**
   - **Widen `list_all`:**
     ```python
     async def list_all(self, project_id: UUID, *, include_archived: bool = False) -> list[CanonRule]:
         """Management list. Default: non-archived only (the shape every existing caller expects).
         include_archived=True also returns tombstones — F-Q5: the Studio ALREADY renders violations
         of archived rules ("A rule that no longer exists"), so the user can SEE an archived rule
         being broken and, without this, has no surface that lists it and no way to bring it back."""
         where = "project_id = $1" if include_archived else "project_id = $1 AND NOT is_archived"
         query = f"SELECT {_SELECT_COLS} FROM canon_rule WHERE {where} ORDER BY is_archived, created_at, id"
         ...
     ```
     ⚠ `ORDER BY is_archived, created_at, id` — active rows first, tombstones last, so the panel's
     "─ archived ─" divider is a simple partition, not a client-side re-sort.
   - **ADD `restore` — mirror `archive` exactly:**
     ```python
     async def restore(self, project_id: UUID, rule_id: UUID) -> CanonRule | None:
         """Un-archive (the inverse of `archive`). Returns the row, or None if missing /
         another project's / NOT archived (restoring a live rule is a no-op, not a success)."""
         query = f"""
         UPDATE canon_rule SET is_archived = false, updated_at = now()
         WHERE project_id = $1 AND id = $2 AND is_archived
         RETURNING {_SELECT_COLS}
         """
         async with self._pool.acquire() as c:
             row = await c.fetchrow(query, project_id, rule_id)
         return _row_to_rule(row) if row else None
     ```
     ⚠ **`AND is_archived` is load-bearing** (mirrors `archive`'s `AND NOT is_archived`): restoring a
     live rule must return None → 404, not a silent 200. Do **not** bump `version` — restore is not an
     OCC-guarded content edit, and bumping it would 412 an editor holding a valid version.

2. **`services/composition-service/app/routers/canon.py`**
   - `list_canon_rules`: add `include_archived: bool = False` and thread it:
     ```python
     rules = await (canon.list_active(project_id) if active_only
                    else canon.list_all(project_id, include_archived=include_archived))
     ```
     (`active_only` wins when both are set — it is the strictly narrower lens. Add that as a comment.)
   - **NEW route**, placed directly after `delete_canon_rule`:
     ```python
     @router.post("/canon-rules/{rule_id}/restore", status_code=200)
     async def restore_canon_rule(
         rule_id: UUID,
         user_id: UUID = Depends(get_current_user),
         works: WorksRepo = Depends(get_works_repo),
         canon: CanonRulesRepo = Depends(get_canon_rules_repo),
         grant: GrantClient = Depends(get_grant_client_dep),
     ) -> dict[str, Any]:
         """Un-archive a soft-deleted canon rule (BE-11a). The inverse of DELETE — a destructive
         action on the row that STEERS THE CRITIC gets an undo path, or it is not shipped."""
         # By-id route: resolve the rule's scope from the ROW ITSELF, gate on ITS book (H13 — the
         # gate can never check a different book than the row mutated).
         project_id = await _rule_project_id(rule_id)
         await _require_work(works, grant, user_id, project_id, GrantLevel.EDIT)
         rule = await canon.restore(project_id, rule_id)
         if rule is None:
             raise HTTPException(status_code=404, detail="canon rule not found")
         return rule.model_dump(mode="json")
     ```
     ⚠ **404 covers all three misses** (missing / other project / not archived) — the same
     `uniform_not_accessible` no-enumeration-oracle discipline `delete_canon_rule` uses.

**Tests**

- **NEW** `services/composition-service/tests/unit/test_canon_rules_router.py` (create if absent; else extend
  the existing canon router test). Mock repo + grant, as the sibling router tests do.
  - `test_restore_returns_row_and_clears_is_archived`
  - `test_restore_missing_rule_404`
  - `test_restore_not_archived_404` — repo returns `None` ⇒ 404, **not** 200.
  - `test_restore_requires_edit_grant_403` — `InsufficientGrant` → 403.
  - `test_list_include_archived_passes_flag_to_repo` — assert `list_all` called with `include_archived=True`.
  - `test_list_active_only_wins_over_include_archived` — both set ⇒ `list_active` is called.
- **EXTEND** `services/composition-service/tests/integration/db/test_repositories.py` (real PG — the file
  already carries the `skipif(TEST_COMPOSITION_DB_URL)` gate; **add `pytest.mark.xdist_group("pg")` to its
  `pytestmark` if it is not already there**):
  - `test_canon_rule_restore_roundtrip` — create → archive → `list_all()` excludes it →
    `list_all(include_archived=True)` **includes** it with `is_archived=True` → `restore()` returns the row
    with `is_archived=False` → `list_all()` includes it again.
  - `test_canon_rule_restore_on_live_rule_returns_none` — restore a never-archived rule ⇒ `None`.
  - `test_canon_rule_restore_cross_project_returns_none` — archive in project A, restore with project B ⇒ `None`.
  - `test_canon_rule_restore_does_not_bump_version` — version before == version after.

**DoD evidence:** `composition-service: <N> passed` on
`python -m pytest tests -q -n auto --dist loadgroup`, with the 6 new router tests + 4 new repo tests named in
the output. Paste the counts.

---

### `W1-03` — BE-11c: MCP `composition_canon_rule_restore` + `undo_hint` + 🔴 BE-11d `composition_dismiss_violation` + 🔴 BE-11e the public-edge policy rows

> **dependsOn:** `W1-02` · **kind:** BE
> **Why it is NOT optional:** the human gains restore in M1, so the agent must gain it **in the same
> milestone**. A one-sided restore is the **GG-2 inverse defect, immediately.**
> 🔴 **AND BE-11d ships HERE, not in a defer row** (§2 OQ-4). Spec 31's own rule — *"Do not ship the human
> half alone"* (31:521, 31:601) — applies to dismiss identically, and the logic **already exists in the REST
> handler**. Writing + carrying its defer row costs more than the tool.

**File:** `services/composition-service/app/mcp/server.py`

1. **NEW tool**, placed directly after `composition_canon_rule_delete` (~line 1200):
   ```python
   @mcp_server.tool(
       name="composition_canon_rule_restore",
       description=(
           "Un-archive a soft-deleted canon rule, putting it back in force for the critic. "
           "EDIT required (auto-applied; Undo re-archives the rule)."
       ),
       meta=require_meta(
           "A", "book",
           synonyms=["restore canon rule", "un-archive rule", "bring back invariant", "undelete rule"],
           tool_name="composition_canon_rule_restore",
       ),
   )
   async def composition_canon_rule_restore(
       ctx: MCPContext,
       project_id: Annotated[str, "The Work's project_id."],
       rule_id: Annotated[str, "The canon rule id."],
   ) -> dict:
       tc = _ctx(ctx)
       works = WorksRepo(get_pool())
       pid = UUID(project_id)
       await _book_or_deny(works, tc, pid, GrantLevel.EDIT)
       canon = CanonRulesRepo(get_pool())
       # Project-scope BEFORE mutating (canon.get is by-id): a rule from another Work must not be
       # restored under THIS book's gate. Same shape as _delete / node_update.
       prior = await canon.get(pid, UUID(rule_id))
       if prior is None or prior.project_id != pid:
           raise uniform_not_accessible()
       rule = await canon.restore(pid, UUID(rule_id))
       if rule is None:
           raise uniform_not_accessible()   # not archived → nothing to restore
       out = rule.model_dump(mode="json")
       out["_meta"] = {"undo_hint": _undo(
           "composition_canon_rule_delete", project_id=project_id, rule_id=rule_id,
       )}
       return out
   ```
2. **`composition_canon_rule_delete`** — replace the honest-`None` undo hint (and **delete the now-false
   comment** *"there is no un-archive repo method, so there is no verified reverse op"*):
   ```python
   out["_meta"] = {"undo_hint": _undo(
       "composition_canon_rule_restore", project_id=project_id, rule_id=rule_id,
   )}
   ```

🔴 **THE "3-SCHEMA-SOURCE FastMCP CAVEAT" DOES NOT APPLY HERE — DO NOT CHASE IT (F35).** That caveat is
**knowledge-service-specific** (it has a bespoke `tools/definitions.py` hand-schema *plus* a pydantic arg model
*plus* the FastMCP signature). `find services/composition-service -name definitions.py` → **nothing**. The
`@mcp_server.tool` decorator is the **single** schema source, and it derives the schema from the **signature** —
so keep the arg docs in the `Annotated[...]` params, never in a docstring. *(A builder hunting three schema
sources here will hunt two files that do not exist.)*

**3. 🔴 BE-11d — NEW TOOL `composition_dismiss_violation`** (§2 OQ-4). One pure helper first, so the two doors
cannot drift (the `css-var-duplicated-across-two-consumers` class):

- **NEW `services/composition-service/app/engine/critic_dismiss.py`:**
  ```python
  def apply_dismissal(critic: dict[str, Any] | None, rule_id: str) -> tuple[dict[str, Any], bool]:
      """Mark every violation for `rule_id` dismissed. Returns (new_critic, found).
      Copy-then-return (no mutation of the caller's dict) — the motif_conformance.py:221 convention."""
      out = dict(critic or {})
      violations = [dict(v) if isinstance(v, dict) else v for v in (out.get("violations") or [])]
      found = False
      for v in violations:
          if isinstance(v, dict) and str(v.get("rule_id")) == rule_id:
              v["dismissed"] = True
              found = True
      out["violations"] = violations
      return out, found
  ```
- **`app/routers/engine.py:1684-1709`** — replace the inline loop in `dismiss_violation` with
  `critic, found = apply_dismissal(job.critic, body.rule_id)`. **Keep the existing `_gate_work(EDIT)`, the
  `404 "violation not found"`, and the `{"critic": critic}` response byte-for-byte.** Behavior unchanged.
- **`app/mcp/server.py`** — the tool, in the Tier-A section immediately after `composition_canon_rule_delete`,
  copying that decorator shape. Args: `project_id`, `job_id`, `rule_id` (bare `Annotated[str, …]`).
  Body: `_book_or_deny(works, tc, pid, GrantLevel.EDIT)` → `job = await jobs.get(UUID(job_id))` →
  🔴 **project-scope BEFORE mutating** (`if job is None or job.project_id != pid: raise uniform_not_accessible()`
  — `jobs.get()` is by-id only, so a job from another Work must not be writable under this gate) →
  `critic, found = apply_dismissal(job.critic, rule_id)` → `if not found: raise uniform_not_accessible()` →
  `await jobs.update_status(UUID(job_id), job.status, critic=critic)` → return
  `{"critic": critic, "_meta": {"undo_hint": None}}`. **`undo_hint: None` is HONEST here — no un-dismiss
  exists at any layer** (the `canon_rule_delete` precedent, before restore existed). *Default (PO may veto):
  dismiss stays NOT reversible for **both** doors — an agent-only un-dismiss would open the inverse gap in the
  other direction, since the GUI has no un-dismiss control.*
- **`frontend/src/features/studio/agent/handlers/compositionEffects.ts`** (created in `W1-06`) — the
  `^composition_canon_rule_` pattern does **not** match `composition_dismiss_violation`. Add its own
  registration so an **agent** dismiss refreshes the **human's** `quality-canon` panel. *(Without it the panel
  shows a violation the agent just silenced.)*

**4. 🔴 BE-11e — THE SURFACE THE SPEC MISSED (F34): `services/mcp-public-gateway/src/scope/tool-policy.ts`.**
Add, beside `composition_canon_rule_delete` (`:236`):
```ts
composition_canon_rule_restore:  { tier: 'write_auto', domains: ['composition'] },
composition_dismiss_violation:   { tier: 'write_auto', domains: ['composition'] },
```
**This file is DEFAULT-DENY / fail-closed** (`:9`, `:340 isClassified`, `:368 filterTools` drops unclassified
tools). **Without a row, the tool is registered, unit-green, and SILENTLY UNREACHABLE at the public edge** —
the exact half-dark shape this wave exists to kill. **There is no parity test guarding this** (grepped — none
exists), so **nothing will catch the omission.** `composition_outline_node_restore` carries its row at `:231`.

**Tests** — `services/composition-service/tests/unit/test_mcp_canon_rules.py` (create if absent) +
`tests/unit/test_critic_dismiss.py` (NEW) + `tests/unit/test_mcp_actions.py` (extend):
- `test_canon_rule_restore_returns_row_and_undo_hint_to_delete`
- `test_canon_rule_restore_cross_project_uniform_not_accessible`
- `test_canon_rule_restore_on_live_rule_uniform_not_accessible`
- 🔴 `test_canon_rule_delete_now_returns_restore_undo_hint` — **the regression lock**: assert
  `_meta.undo_hint.tool == 'composition_canon_rule_restore'`. **AMEND the existing delete test** (which today
  asserts `undo_hint is None`, `test_mcp_server.py:789-791`) — a stale `assert undo_hint is None` would
  otherwise **lock the bug in**.
- 🔴 **`EXPECTED_TOOLS` DRIFT GUARD** (`services/composition-service/tests/unit/test_mcp_server.py:47-60`):
  add `"composition_canon_rule_restore"` **and** `"composition_dismiss_violation"` to the Tier-A block. **That
  set is the registration drift guard and will RED until the tools exist** — write it first (TDD).
- **BE-11d:** (a) the tool marks the matching violation `dismissed: true` and calls
  `update_status(job_id, job.status, critic=…)` with the status **unchanged**; (b) a job in ANOTHER project →
  `uniform_not_accessible()` **and NO write**; (c) an unknown `rule_id` → `uniform_not_accessible()` **and NO
  write**; (d) 🔴 **PARITY LOCK:** `apply_dismissal` fed the same critic produces the **identical dict** for the
  REST route and the MCP tool; (e) a VIEW-only grant → denied.
- ℹ️ `tool-liveness.json` (3 identical copies — `contracts/`, `chat-service/`, `agent-registry-service/`) is a
  **SWEEP-GENERATED artifact**, not a hand-authored schema. It picks the tools up on the next sweep —
  **do not hand-edit it.**

**DoD evidence:** `composition-service: <N> passed`, the restore + dismiss + parity tests named. Paste the
`tools/list` fragment showing both new tools with their args, **and** the `tool-policy.ts` diff (2 rows).

---

### `W1-04` — FE data layer: `kind` + `is_archived` + `restore` + `includeArchived` + the **412 that keeps the user's draft**

> **dependsOn:** `W1-02` · **kind:** FE
> This slice is **pure hooks/types/api + a row component**. It touches `features/composition/**` (the legacy
> page's components) **additively only** — every existing call site keeps compiling and its tests keep passing.

**Files**

1. **`frontend/src/features/composition/types.ts`** (~line 345) — `CanonRule` gains the two fields the
   backend has always returned and the TS type dropped (**F-Q10 / F31 — the agent can set `kind`, the human
   cannot; that is an INVERSE gap**):
   ```ts
   export type CanonRule = {
     id: string;
     text: string;
     scope: 'world' | 'entity' | 'reveal_gate';
     entity_id: string | null;
     from_order: number | null;
     until_order: number | null;
     kind: string | null;        // ← NEW. Column exists (migrate.py:254); routes accept it; only the GUI couldn't set it.
     active: boolean;
     is_archived: boolean;       // ← NEW. Needed for the archived section + the restore affordance.
     version: number;
   };
   ```
   ⚠ Making these **required** (not optional) will red any fixture that builds a `CanonRule` literal. **Fix
   the fixtures** — an optional field here is how `is_archived` silently defaults to `undefined` and the
   archived partition renders empty.

2. **`frontend/src/features/composition/api.ts`**
   - `listCanonRules(projectId, token, opts?: { includeArchived?: boolean; activeOnly?: boolean })` — build
     the query string; **default = today's behavior** (no params ⇒ identical URL ⇒ the legacy caller is
     byte-for-byte unchanged).
   - **NEW** `restoreCanonRule(ruleId, token): Promise<CanonRule>` → `POST ${BASE}/canon-rules/${ruleId}/restore`.
   - ⚠ **`patchCanonRule` must SURFACE the 412 body.** Check `apiJson`'s error shape: the 412 detail is
     `{code:'CANON_VERSION_CONFLICT', current: CanonRule}`. If `apiJson` throws an `Error` that drops
     `detail`, **thread it** (add `err.detail`/`err.code` to the thrown object — the pattern
     `booksApi.patchDraft` already uses for `CHAPTER_DRAFT_CONFLICT`, see `ManuscriptUnitProvider.tsx:225-229`
     reading `err.code`). **Without this the panel cannot render `current`, and QC's 412 requirement is
     unbuildable.** Verify by reading `frontend/src/lib/api.ts` (or wherever `apiJson` lives) FIRST.

3. **`frontend/src/features/composition/hooks/useCanonRules.ts`** — the controller. Rewrite (still ≤ ~80 lines):
   ```ts
   export function useCanonRules(
     projectId: string | undefined, token: string | null,
     opts?: { includeArchived?: boolean },
   ) {
     const qc = useQueryClient();
     const includeArchived = !!opts?.includeArchived;
     // The archived lens is a DIFFERENT result set ⇒ a different key. One key for two shapes is how a
     // cached non-archived list renders as "no archived rules" forever.
     const key = ['composition', 'canon', projectId, includeArchived] as const;
     // Both lenses invalidate together — a restore changes what BOTH lists contain.
     const invalidate = () => qc.invalidateQueries({ queryKey: ['composition', 'canon', projectId] });

     const list = useQuery({ queryKey: key, enabled: !!projectId && !!token,
       queryFn: () => compositionApi.listCanonRules(projectId!, token!, { includeArchived }),
       select: (d): CanonRule[] => d.rules });

     const create  = useMutation({ mutationFn: (p: Partial<CanonRule>) => compositionApi.createCanonRule(projectId!, p, token!), onSuccess: invalidate });
     const patch   = useMutation({ mutationFn: (v: {id: string; payload: Partial<CanonRule>; version: number}) =>
                                     compositionApi.patchCanonRule(v.id, v.payload, v.version, token!), onSuccess: invalidate });
     const remove  = useMutation({ mutationFn: (id: string) => compositionApi.deleteCanonRule(id, token!), onSuccess: invalidate });
     const restore = useMutation({ mutationFn: (id: string) => compositionApi.restoreCanonRule(id, token!), onSuccess: invalidate });

     // 🔴 EXPORT `invalidate`. Today useCanonRules invalidates onSuccess ONLY (:9) — so a 412 leaves a
     // STALE `version` in the cache and every retry 412s FOREVER. The conflict handler MUST be able to
     // force a refetch.
     return { list, create, patch, remove, restore, invalidate };
   }
   ```
   🔴 **NO INSTANT-COMMIT CHIPS. KILL THE RACE BY CONSTRUCTION — DO NOT CHAIN**
   (`Q-31-OCC-CHIP-SERIALIZATION`). An earlier draft of this plan mandated a `patchSerialized` write-chain for
   *"the `active` toggle and the `scope` select as chips over an OCC entity"*. **Those chips do not exist and
   are not being built.** The code already kills the race:
   - `scope` and `active` are **submit-gated form state** inside `CanonRuleForm` (`:37,41` `useState` →
     `:48-59` ONE full payload → **one PATCH per Save**);
   - `canSubmit = !!text.trim() && !windowInverted && !pending` (`CanonRuleForm.tsx:46`), fed by
     `pending={patch.isPending}` (`CanonRulesPanel.tsx:58`), **disables Save while its own write is in flight**;
   - `CanonRulesPanel.tsx:18` keeps a **single `editingId`** ⇒ **one form ⇒ one in-flight PATCH** at a time.
   - Panel A's own ASCII draws `scope` as a **read-only badge** and inactive as an **`(inactive)` label** — no chip.

   **Builder action: DELETE the ⚠ chips clause from spec 31 §Panel A (~:349-352) and §OCC (~:630).** It mandates
   a mitigation for a control the spec does not build — leaving it in makes the builder either **invent chips
   (scope creep)** or **hunt for phantom code**. *(If a future slice DOES add an instant-commit chip over a
   canon rule, the mandated pattern is the existing one at `useSceneInspector.ts:46,99-100` —
   `chainRef.current = chainRef.current.then(run, run)` + a `nodeRef` mirror read for the FRESH version. **Cite
   it; do not reinvent it.**) PO default: **no chips in v1.**

4. **`frontend/src/features/composition/components/CanonRuleForm.tsx`** — `CanonRulePayload` gains `kind`:
   ```ts
   export type CanonRulePayload = {
     text: string; scope: CanonRule['scope']; entity_id: string | null;
     from_order: number | null; until_order: number | null;
     kind: string | null;     // ← NEW (F-Q10)
     active: boolean;
   };
   ```
   Add a free-text `kind` input (F43 — it is a `TEXT` column with **NO CHECK**, nothing downstream reads it,
   so **do not invent a closed set**; a `<select>` would fabricate a taxonomy the backend does not have.
   `CLOSED_SET_ARGS` applies to *tool args*, and `kind` is not one). 🔴 **Add a `datalist` of the kinds already
   in use** — a *suggestion* list that does **not** restrict input; it costs nothing and stops label drift
   (`Q-31-F-Q10-KIND-INVERSE-GAP`):
   ```tsx
   <input data-testid="composition-canon-kind" type="text" list="composition-canon-kind-options"
          value={kind} maxLength={100}
          onChange={(e) => setKind(e.target.value)}
          placeholder={t('canonKind', { defaultValue: 'kind (optional, e.g. "power-system")' })}
          aria-label={t('canonKind', { defaultValue: 'Kind' })}
          className="w-40 rounded border border-neutral-300 bg-transparent px-2 py-1 text-xs dark:border-neutral-600" />
   <datalist id="composition-canon-kind-options">
     {knownKinds.map((k) => <option key={k} value={k} />)}
   </datalist>
   ```
   New prop `knownKinds: string[]` (default `[]`), supplied by `CanonRulesPanel` from the rules it **already
   has**: `Array.from(new Set(rules.map(r => r.kind).filter((k): k is string => !!k))).sort()`.
   Submit `kind: kind.trim() || null`. Seed from `initial?.kind ?? ''`.
   ⚠ **Sending `null` on edit is CORRECT and intentional:** `kind` is in `_NULLABLE_UPDATE_COLUMNS`
   (`canon_rules.py:33-35`), so an emptied field **CLEARS** the label rather than being ignored.

5. **NEW `frontend/src/features/composition/components/CanonRuleRow.tsx`** — extract the row so
   `CanonRulesPanel` stays ≤ ~100 lines (CLAUDE.md React MVC). It renders: the read view (scope chip, entity
   label, reveal window, `kind` chip, text, inactive marker), the edit view (`CanonRuleForm`), the ✎ / ✕
   buttons, the **↺ restore** button (archived only), the **⚠ N broken** badge, and the **412 conflict
   banner**. Props:
   ```ts
   interface Props {
     rule: CanonRule;
     editing: boolean;
     roster: RosterOption[]; rosterLoading: boolean;
     violationCount?: number;                    // from getRuleViolations, keyed by rule_id
     conflict?: CanonRule | null;                // the 412 body's `current` — render it, KEEP the draft
     onEdit: () => void; onCancel: () => void;
     onSave: (payload: CanonRulePayload) => void;
     onArchive: () => void; onRestore?: () => void;
     onOpenViolations?: () => void;              // → host.openPanel('quality-canon', {params:{focusRuleId}})
     pending: boolean;
   }
   ```
   🔴 **NO `onToggleActive` — there is no instant-commit chip.** `active` is a checkbox **inside the
   submit-gated form**; the row renders an `(inactive)` **label** and `scope` as a **read-only badge**. (See the
   chips clause above — it was deleted.)
   **The 412 banner (state ③ in the mock) — this is the thing being FIXED, so build it exactly:**
   ```tsx
   {conflict && (
     <div data-testid="canon-rule-conflict" className="rounded bg-amber-50 p-2 text-[11px] text-amber-800 dark:bg-amber-950 dark:text-amber-300">
       {t('canonConflict', { defaultValue: 'This rule changed elsewhere — showing the current version. Re-apply your edit?' })}
       <div className="mt-1 text-neutral-600 dark:text-neutral-400">“{conflict.text}”</div>
     </div>
   )}
   ```
   ⚠ **The form stays MOUNTED with the user's draft intact.** Today `CanonRulesPanel.tsx:20`'s
   `onError → toast.error` is **the thing being fixed** — a bare toast that loses the edit. **Never a silent
   overwrite, never a bare toast.**

   🔴 **THE 412 HANDLER — the exact shape (`Q-31-OCC-CHIP-SERIALIZATION` (2)).** Replace the bare
   `onError = (e) => toast.error((e as Error).message)` at `CanonRulesPanel.tsx:20`:
   - **The thrown error already carries what's needed** — `api.ts:159-163` does
     `Object.assign(new Error(...), { status, body })`, and `canon.py:167-169` raises
     `HTTPException(412, detail={"code":"CANON_VERSION_CONFLICT","current": <rule>})`. So read:
     `const err = e as { status?: number; body?: { detail?: { code?: string; current?: CanonRule } } }`.
   - On `err.status === 412 && err.body?.detail?.code === 'CANON_VERSION_CONFLICT'`:
     **(a)** `setConflict({ ruleId: id, current: err.body.detail.current })`;
     **(b)** 🔴 **call `invalidate()`** (the one now exported from `useCanonRules`) — *without this the cache
     keeps the STALE `version` and every retry 412s forever*;
     **(c)** 🔴 **do NOT call `setEditingId(null)` and do NOT change the form's `key`.** `saveEdit`
     (`:25-29`) only clears `editingId` **onSuccess** — that is right; keep it. `CanonRuleForm`'s draft lives
     in `useState` seeded from `initial` **at mount only** (`:36-41`), so **a remount silently destroys the
     user's draft — the exact thing this fix exists to prevent.**
   - The **Re-apply** button calls `saveEdit(r.id, r.version, draftPayload)` — `r` re-renders from the
     invalidated list, so `r.version` is **fresh** and the re-apply lands.
   - Everything else (non-412) keeps `toast.error`.

6. **`frontend/src/features/composition/components/CanonRulesPanel.tsx`** — refactor to map `CanonRuleRow`,
   and add **optional** props (so the legacy call site `CompositionPanel.tsx:836`, which passes none, is
   unchanged and its tests stay green):
   ```ts
   interface Props {
     projectId: string; bookId: string; token: string | null;
     showArchived?: boolean;                                   // ← NEW
     violationCounts?: Record<string, number>;                 // ← NEW
     onOpenViolations?: (ruleId: string) => void;              // ← NEW
     focusRuleId?: string | null;                              // ← NEW (deep-link IN)
   }
   ```
   - Pass `{ includeArchived: !!showArchived }` to `useCanonRules`.
   - Partition: `rules.filter(r => !r.is_archived)` then, **only when `showArchived`**, a
     `─ archived ─` divider (`data-testid="canon-rules-archived-divider"`) + the tombstones (dimmed,
     `↺ restore`).
   - **Archive gets a confirm + an Undo toast wired to `restore`** — a destructive action on the row that
     steers the critic gets an undo path or it is not shipped:
     ```tsx
     const archive = (r: CanonRule) => {
       if (!window.confirm(t('canonArchiveConfirm', { defaultValue: 'Archive this canon rule? The critic will stop enforcing it.' }))) return;
       remove.mutate(r.id, {
         onSuccess: () => toast.success(
           t('canonArchived', { defaultValue: 'Rule archived' }),
           { action: { label: t('undo', { defaultValue: 'Undo' }), onClick: () => restore.mutate(r.id) } },
         ),
         onError,
       });
     };
     ```
   - **Focus banner** (deep-link IN): when `focusRuleId` resolves to no rule in the (non-archived) list, render
     `data-testid="canon-rules-focus-archived"` → *"That rule was archived — [show archived]"* (a button that
     flips `showArchived`). When it resolves, hoist it to the top + `data-focused="true"`.
     **It never renders an empty list that reads as success** — the same honesty rule `QualityCanonPanel`'s
     `FocusBanner` already follows.
   - **No roster** (glossary empty) ⇒ `scope=entity` is **disabled with a reason**
     (`data-testid="canon-rule-no-roster"`), never silently broken. `CanonRuleForm` already receives
     `roster` + `rosterLoading`; add the empty-roster branch there.

**Tests** — `frontend/src/features/composition/components/__tests__/CanonRulesPanel.test.tsx` (extend) +
NEW `.../__tests__/CanonRuleRow.test.tsx` + NEW `.../hooks/__tests__/useCanonRules.test.tsx`:
- `renders the kind field and submits it` (F-Q10 closed).
- `archived rules are hidden by default and shown under the divider when showArchived`.
- `restore calls the restore mutation and the rule returns to the active list`.
- 🔴 **`a 412 renders the conflict banner with `current` AND KEEPS the user's draft in the form`** — mock
  `patchCanonRule` to reject with
  `Object.assign(new Error('...'), { status: 412, body: { detail: { code: 'CANON_VERSION_CONFLICT', current: { …id, version: 7, text: 'server text' } } } })`;
  assert **(a)** `canon-rule-conflict` renders `"server text"`, **(b)** the form is **still open** and its text
  input **still holds the user's typed draft** (NOT reset to `initial`), **(c)** the **second Save sends
  `If-Match: 7`** (i.e. the list was invalidated and the fresh version was picked up).
  *This is the load-bearing test of the slice — all three assertions, not just the banner.*
- `archive asks for confirmation and offers Undo` — spy `window.confirm` → false ⇒ no mutation; → true ⇒
  mutation + a toast carrying an action.
- 🔴 **`with showArchived/onRestore omitted, no archived UI renders and no restore call fires`** — the
  additive-only gate. *(Note `CanonRulesPanel.test.tsx:19` mocks `useCanonRules` with an **object literal**, so
  a component that unconditionally calls `canon.restore.mutate` **REDS the suite**. That mock is a genuine gate
  here — unlike `PolishPanel`'s, which mocks its hook away entirely, F41.)*
- ~~`two rapid active-toggles both land`~~ 🔴 **DELETED — there is no toggle chip** (see above). A test for a
  control that does not exist is how a builder ends up building the control.
- `an empty glossary roster disables scope=entity with a reason` (no silent break).
- `focusRuleId that resolves to an archived rule renders the "that rule was archived" affordance`.
- **REGRESSION:** the legacy `CanonRulesPanel` tests (6 existing) stay green with **no prop changes**.

**DoD evidence:** `frontend: <N> passed` on `npx vitest run src/features/composition`, with the 412 test and
the write-serialization test named.

---

### `W1-05` — `quality-canon-rules` PANEL + GG-8 registration + the two-way deep-link + QC-9 dismiss

> **dependsOn:** `W1-04`, `W1-00` · **kind:** FS (FE + the chat-service enum)
> **Enum: `N` → `N+1`.**

**Files**

1. **NEW `frontend/src/features/studio/panels/QualityCanonRulesPanel.tsx`** — a **thin wrapper**, exactly the
   shape of `QualityCriticPanel` / `QualityCoveragePanel` (≤ ~100 lines):
   ```tsx
   export function QualityCanonRulesPanel(props: IDockviewPanelProps) {
     useStudioPanel('quality-canon-rules', props.api);
     const { t } = useTranslation('studio');
     const host = useStudioHost();
     const { accessToken } = useAuth();
     const work = useQualityWork(host.bookId, accessToken);        // ONE gate, one name
     const [showArchived, setShowArchived] = useState(false);
     const focusRuleId = (props.params as { focusRuleId?: string } | undefined)?.focusRuleId ?? null;

     // The ⚠ N broken badge joins against the SAME read `useQualityCanon` already makes. One extra
     // query, ZERO new routes.
     const violationsQ = useQuery({
       queryKey: ['studio', 'quality-canon', 'rules', work.kind === 'ready' ? work.projectId : null],
       queryFn: () => compositionApi.getRuleViolations((work as {projectId:string}).projectId, accessToken!),
       enabled: work.kind === 'ready' && !!accessToken,
     });

     if (work.kind !== 'ready') return <QualityWorkGate state={work} testIdPrefix="quality-canon-rules" />;

     const counts: Record<string, number> = {};
     for (const v of violationsQ.data?.items ?? []) if (v.rule_id) counts[v.rule_id] = (counts[v.rule_id] ?? 0) + 1;

     return (
       <div data-testid="studio-quality-canon-rules-panel" className="flex h-full min-h-0 flex-col gap-2 overflow-auto p-3 text-sm">
         <label className="flex items-center gap-1 self-end text-[11px] text-neutral-500">
           <input type="checkbox" data-testid="canon-rules-show-archived"
                  checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
           {t('quality.canonShowArchived', { defaultValue: 'Show archived' })}
         </label>
         <CanonRulesPanel
           projectId={work.projectId} bookId={host.bookId} token={accessToken}
           showArchived={showArchived}
           violationCounts={counts}
           focusRuleId={focusRuleId}
           onOpenViolations={(ruleId) => host.openPanel('quality-canon', { params: { focusRuleId: ruleId } })}
         />
       </div>
     );
   }
   ```
   ⚠ **Reuse the EXACT query key `['studio','quality-canon','rules', projectId]`** that `useQualityCanon.ts:84`
   already uses — one key, one concept; the Lane-B handler (W1-06) invalidates it once and **both** panels refresh.
   ⚠ **REUSE the exported `CanonFocusParams` type from `useQualityCanon.ts:27`** — do **not** declare a second
   focus-param type or a second param name (one name, one concept). **Lift `hoist()` (`useQualityCanon.ts:64`)
   into a shared `panels/focus.ts`** and import it in both. **EXTEND the seam; do not rebuild it.**

   🔴 **THE `⚠ N broken` BADGE IS A PAGED JOIN — AND IT MUST NOT LIE (F44, `Q-31-DEEPLINK-EXTEND-NOT-REBUILD` S6).**
   `getRuleViolations` is **capped at 200** and its `count` is the **BOOK-WIDE** total, not per-rule ⇒ a
   per-rule count derived from a `capped: true` page is a **LOWER BOUND**. The honesty rule, exactly:
   | hits | `capped` | render |
   |---|---|---|
   | `> 0` | either | the **⚠ N broken** badge → deep-links to `quality-canon` |
   | `0` | **`true`** | a **MUTED** *"not in the shown {{shown}} of {{total}}"* chip that **still deep-links**. 🔴 **NEVER "0 broken". NEVER a green/clean affordance.** |
   | `0` | `false` | **render nothing** (genuinely clean) |
   | *(query errored, or `work.kind !== 'ready'`)* | — | **render nothing** — never a not-found/clean claim over an **unconsulted** list |
   *This is the `paged-join-mislabels-not-yet-loaded-as-absent` class, and the exact false-clean `QualityCanonPanel`
   was built to avoid.*

2. **`frontend/src/features/studio/panels/catalog.ts`** — one `STUDIO_PANELS` row (+ the import):
   ```ts
   { id: 'quality-canon-rules', component: QualityCanonRulesPanel,
     titleKey: 'panels.quality-canon-rules.title', descKey: 'panels.quality-canon-rules.desc',
     category: 'quality', guideBodyKey: 'panels.quality-canon-rules.guideBody' },
   ```
   Place it next to `quality-canon`. **`guideBodyKey` is MANDATORY** (X-3 now asserts it).

3. **`frontend/src/i18n/locales/en/studio.json`** — `panels.quality-canon-rules.{title,desc,guideBody}` +
   the `quality.canon*` strings the panel/row use (`canonShowArchived`, `canonConflict`, `canonArchiveConfirm`,
   `canonArchived`, `canonKind`, `canonBroken`, `canonRestore`, `canonRuleWasArchived`, `canonNoRoster`,
   `canonRulesEmpty`, `canonRulesEmptyHint`, `canonDismiss`, `canonDismissed`).
   ⚠ **NEVER edit an existing `en` string that already has 17 translations** — `scripts/i18n_translate.py`
   **gap-fills only**: it keeps a valid existing translation, so an edited `en` string leaves 17 locales
   permanently stale. **Add a new key instead.** (The warning is in-code at `QualityCanonPanel.tsx:52-55`.)

4. **17 locales** — `python scripts/i18n_translate.py`. **Never hand-write a translation.**

5. **`services/chat-service/app/services/frontend_tools.py`** — **TWO edits inside `UI_OPEN_STUDIO_PANEL_TOOL`:**
   - (a) append `"quality-canon-rules"` to the `panel_id` **enum** (~line 402);
   - (b) append a clause to the tool **description** (~403-481) — *that gloss is the model's ONLY hint the
     panel exists*:
     > `'quality-canon-rules' = author the canon rules the critic enforces (create/edit/archive/restore invariants);`

6. **`contracts/frontend-tools.contract.json`** — **NEVER hand-edit. REGENERATE:**
   ```bash
   cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py
   ```
   and **commit the regenerated JSON in the SAME commit** as `catalog.ts` + `frontend_tools.py`.

7. **`frontend/src/features/studio/panels/QualityHubPanel.tsx`** — `CARDS` 4 → **5**:
   ```ts
   { panelId: 'quality-canon-rules', icon: '⚖️', titleKey: 'canonRulesTitle', descKey: 'canonRulesDesc' },
   ```
   *(`quality-corrections` 📈 and `quality-heal` ✨ are added by their own slices → the hub ends at **7**.
   **`progress` is NOT a card** — QC-2.)*

8. **QC-9 — the Dismiss button on `quality-canon`'s `RuleRow`** (`QualityCanonPanel.tsx:164-182`).
   **Zero backend** — the row already carries `job_id` + `rule_id` (F30), and
   `compositionApi.dismissViolation(jobId, ruleId, token)` already exists (`api.ts:562`).
   ```tsx
   {r.rule_id && (
     <button type="button" data-testid="quality-canon-dismiss"
             onClick={() => onDismiss(r.job_id, r.rule_id!)}
             className="shrink-0 rounded border border-neutral-300 px-2 py-0.5 text-[10px] text-neutral-500">
       {t('quality.canonDismiss', { defaultValue: 'Dismiss' })}
     </button>
   )}
   ```
   Wire `dismissRule(jobId, ruleId)` / `dismissPending` / `dismissError` **in `useQualityCanon.ts`** as a
   `useMutation` calling `compositionApi.dismissViolation(jobId, ruleId, accessToken!)` (`api.ts:562` — it
   already exists), `onSuccess` → `queryClient.invalidateQueries({ queryKey: ['studio','quality-canon','rules', projectId] })`
   (the exact key at `useQualityCanon.ts:84`).
   🔴 **Do NOT reuse `useCritique`'s `dismiss`** (`features/composition/hooks/useCritique.ts:10`) — it is
   CriticPanel-scoped and **does not invalidate the studio key** (the
   `invalidateQueries-cannot-reach-hand-rolled-state` class).
   🔴 **NO optimistic row removal.** The backend marks **EVERY** violation in that job matching that `rule_id`
   (`engine.py:1700-1706`), while rows are flat per (scene × violation) — **one click can legitimately clear
   two rows.** Invalidate + refetch is the only correct refresh.
   🔴 **FAIL LOUD, NEVER SILENT.** The route **404s** `violation not found` when a newer critique overwrote
   `critic` (`engine.py:1707`) and **403s** a VIEW-only grantee. On error render an explicit banner
   (`data-testid="quality-canon-dismiss-error"`, reuse the existing `WARN` class) **and keep the row visible** —
   *a dismiss that appears to work but didn't is the `silent-success-is-a-bug` class.*
   ℹ️ Render the button only when `r.rule_id` is truthy — defensive: `critic._filter_violations`
   (`critic.py:85`) already drops any violation with an empty `rule_id`, so the `| null` in the TS type is
   belt-and-braces.
   ℹ️ **Backend needs no new test** — `test_engine_router.py:804` (200 + `dismissed:true`) and `:811` (404 on
   an unknown rule) already cover the route. **BE-11d (the agent's twin) ships in `W1-03`.**

9. **The deep-link, both directions** (this *completes* the chain `plan-hub → quality-canon → quality-canon-rules`
   whose first hop already ships at `PlanHubPanel.tsx:74`):
   - **IN** — `QualityCanonPanel`'s `RuleRow` gains **“Edit rule”** →
     `host.openPanel('quality-canon-rules', { params: { focusRuleId: r.rule_id } })`.
   - **OUT** — the ⚠ N broken badge on a `CanonRuleRow` →
     `host.openPanel('quality-canon', { params: { focusRuleId: rule.id } })` — the panel and the param that
     **already exist** (`useQualityCanon.ts:27` `CanonFocusParams`). **Do NOT rebuild that seam; extend it.**

**Tests**

- NEW `frontend/src/features/studio/panels/__tests__/QualityCanonRulesPanel.test.tsx`:
  - `renders the Work gate when work is loading / unavailable / no-work` (three cases,
    `testIdPrefix="quality-canon-rules"`).
  - `renders the ⚠ N broken badge from getRuleViolations, keyed by rule_id`.
  - `clicking the badge opens quality-canon with params.focusRuleId` (spy `host.openPanel`).
  - `params.focusRuleId hoists that rule to the top`.
  - `a focusRuleId that resolves to nothing renders the "that rule was archived — show archived" affordance`.
- EXTEND `QualityCanonPanel.test.tsx`:
  - `Edit rule opens quality-canon-rules with params.focusRuleId`.
  - `Dismiss calls dismissViolation and the row disappears after invalidation`.
  - `a dismiss 404 renders an inline error, never a silent success`.
- **The 4 drift-locks** (run them; the counts move by exactly **+1**):
  ```
  cd services/chat-service && python -m pytest tests/test_frontend_tools_contract.py tests/test_frontend_tools.py -q
  cd frontend && npx vitest run \
    src/features/studio/panels/__tests__/panelCatalogContract.test.ts \
    src/features/studio/panels/__tests__/UserGuidePanel.test.tsx \
    src/features/studio/palette/__tests__/useStudioCommands.test.ts \
    src/features/chat/nav/__tests__/frontendToolContract.test.ts
  ```

**DoD evidence:** *"panel enum N→N+1; py enum == contract enum == openable (three-way equality green);
frontend: `<N>` passed; chat-service contract: `<N>` passed"*.
**Do NOT touch:** `StudioDock.tsx`, `StudioFrame.tsx`, `UserGuidePanel.tsx` — all derive from `catalog.ts`.

---

### `W1-06` — Lane-B: **CREATE** `handlers/compositionEffects.ts` (X-4's composition home)

> **dependsOn:** `W1-05` · **kind:** FE
> **Plan 30 §8.0b: Wave 1 CREATES this file. Wave 6 EXTENDS it.** Two files for one domain **double-fire**.

**Files**

1. **NEW `frontend/src/features/studio/agent/handlers/compositionEffects.ts`**
   ```ts
   // Lane-B effect handlers for the composition domain (plan 30 §8.0b — ONE FILE PER DOMAIN).
   // Wave 1 creates it (canon rules + corrections). Wave 6 (spec 36) EXTENDS this file — it does NOT
   // register a second pattern in a second file: matchEffectHandlers returns EVERY match and
   // runEffectHandlers AWAITS ALL of them, so two files would DOUBLE-FIRE and give one concept two homes.
   import { registerEffectHandler, type EffectContext } from '../effectRegistry';

   // ⚠ registerEffectHandler's STRING branch is `tool === p || tool.startsWith(p)` — NOT a pattern match.
   // Anything with alternation MUST be a RegExp, or it matches NOTHING and ships a SILENT NO-OP handler
   // that no unit test (which registers and calls its own fake) could ever catch. (Spec 36's first cut
   // made exactly this mistake.)
   export const CANON_RULE_WRITE_PATTERN = /^composition_canon_rule_/;          // create|update|delete|restore
   export const DISMISS_VIOLATION_PATTERN = /^composition_dismiss_violation$/;   // BE-11d (W1-03)
   export const CORRECTION_WRITE_PATTERN = /^composition_record_correction$/;    // BE-9b (W1-15)

   // 🔴 NO projectId. EffectContext (effectRegistry.ts:9-24) carries bookId / host / queryClient and there
   // is NO composition projectId in it — projectId is resolved from bookId only INSIDE useQualityCanon via
   // useQualityWork. DO NOT plumb one in: a null-projectId race at mount would make the handler silently
   // NO-OP (the `silent-success-is-a-bug` class).
   // React-query partial-matches keys ELEMENT-WISE, so ['composition','canon'] matches
   // ['composition','canon',pid,includeArchived] and does NOT over-match ['composition','canon-at-chapter',…]
   // (useCanonAtChapter.ts:67) or ['composition','canon-draft',…] (useVsCanonDelta.ts:85) — element[1]
   // differs. Over-invalidating a second Work's cache is a HARMLESS refetch. This is exactly what
   // knowledgeEffects.ts:29 already does (a bare ['knowledge-projects']).
   export function canonRuleEffect({ queryClient }: EffectContext): void {
     queryClient.invalidateQueries({ queryKey: ['composition', 'canon'] });             // useCanonRules.ts:8
     queryClient.invalidateQueries({ queryKey: ['studio', 'quality-canon', 'rules'] }); // useQualityCanon.ts:84
   }
   export function correctionEffect({ queryClient }: EffectContext): void {
     queryClient.invalidateQueries({ queryKey: ['composition', 'correction-stats'] });  // useCorrectionStats.ts:11
   }

   let registered = false;
   export function registerCompositionEffectHandlers(): void {
     if (registered) return;                 // module guard — the reconciler's useEffect may re-run
     registered = true;
     registerEffectHandler(CANON_RULE_WRITE_PATTERN, canonRuleEffect);
     // An AGENT dismiss must refresh the HUMAN's quality-canon panel, or the panel shows a violation the
     // agent just silenced. Note ^composition_canon_rule_ does NOT match this tool — it needs its own row.
     registerEffectHandler(DISMISS_VIOLATION_PATTERN, canonRuleEffect);
     registerEffectHandler(CORRECTION_WRITE_PATTERN, correctionEffect);
   }
   export function _resetCompositionEffectHandlers(): void { registered = false; }   // test escape hatch
   ```
   ℹ️ **No `unwrapToolResult` needed** — both handlers are **result-agnostic pure invalidation**, so the
   `{ok,result}`-envelope / flat-mock trap that bit `glossaryEffects` cannot bite here.
   ℹ️ **Sequencing:** `composition_record_correction` does not exist until `W1-15`. If M4 slips, the handler is
   **inert-but-harmless** (the registry simply never matches) — **this slice is NOT blocked on it**, and its
   pattern test passes standalone. The canon-rule half delivers value **immediately**.

2. **`frontend/src/features/studio/agent/useStudioEffectReconciler.ts`**
   - `import { registerCompositionEffectHandlers } from './handlers/compositionEffects';`
   - call it in the registration `useEffect`.
   - 🔴 **DELETE the now-false comment at `:8-9`**: *"…and the two tool families it confirmed DON'T need a
     handler (… authoring_run has no MCP tools at all, REST-only, no Studio consumer to go stale)."*
     `composition_authoring_run_start` **is** an MCP tool and `agent-mode` **is** a Studio consumer (F25).
     Replace it with a one-liner naming `compositionEffects.ts` as the composition home.

**Tests** — NEW `frontend/src/features/studio/agent/handlers/__tests__/compositionEffects.test.ts`, mirroring
`knowledgeEffects.test.ts`. 🔴 **Drive through `runEffectHandlers({tool, …})` — NOT by calling the handler
directly** (`inject-at-chokepoint-proves-nothing`: injecting the handler proves the *mechanism*, not that it is
*wired*):
- `the canon pattern is a RegExp and matches create/update/delete/restore` — assert
  `CANON_RULE_WRITE_PATTERN.test('composition_canon_rule_restore')` etc. **AND** assert the READ tool fires
  NOTHING: `/^composition_canon_rule_/.test('composition_list_canon_rules') === false`. *(This test exists
  because the string-vs-RegExp mistake is invisible to a handler unit test that registers its own fake.)*
- `composition_canon_rule_create|update|delete each invalidate BOTH ['composition','canon'] AND ['studio','quality-canon','rules']`.
- `composition_dismiss_violation invalidates the rule-violations lens` (BE-11d).
- `a composition_record_correction result invalidates ['composition','correction-stats']`.
- **`the handlers are registered by useStudioEffectReconciler`** — the **wiring** test. Render the reconciler,
  `clearEffectHandlers()` first, then assert `matchEffectHandlers('composition_canon_rule_create').length === 1`.

**DoD evidence:** `frontend: <N> passed`, the 4 handler tests named + the RegExp assertion. Plus the
**live-browser** proof in `W1-17` (an agent `composition_canon_rule_create` → the open `quality-canon-rules`
tab shows the new rule **without a manual reload**).

---

## M2 — PROGRESS (closes `G-PROGRESS`) · enum `N+1` → `N+2`

> **This is a TENANCY FIX with a panel attached, not a panel with a tenancy fix attached.**
> `/review-impl` runs on this milestone (it crosses a tenancy boundary).

### `W1-07` — BE-P2 (per-user goal) + BE-P2′ (`daily_goal_source`) + BE-P1 (`by_chapter`)

> **dependsOn:** — · **kind:** BE

**Step 0 (MANDATORY, before any code) — resolve UNVERIFIED-2:**
```bash
grep -rn "daily_goal" --include=*.py --include=*.ts --include=*.tsx services/ frontend/src/ | grep -v test
```
Expect exactly: `progress.py::_coerce_goal`, `useProgress.ts` (`useSetDailyGoal`), `ProgressPanel.tsx`.
**If a third consumer appears, add a defer row naming it** — but proceed: the read-through fallback means a
missed consumer degrades to "reads a stale-but-valid legacy goal", never to a crash.

**Files**

1. **`app/db/migrate.py`** — migration **M-B** (§6). Verbatim.

2. **`app/db/repositories/daily_progress.py`**
   - **NEW** `ProgressAggregate.by_chapter: list[tuple[UUID, int]]` (BE-P1) — words authored **on the anchor
     date**, per chapter, `words > 0`, descending.
   - **Widen `read_aggregate`** with a third query (do **not** try to fold it into the existing
     `GROUP BY snapshot_date` — that query deliberately collapses the chapter dimension, F17):
     ```python
     # BE-P1 — the SAME snapshot-differencing as day_words, but grouped by CHAPTER and bounded to the
     # anchor date only. The dimension is in the PK and was collapsed away before the router could see
     # it (F-Q8). A chapter's FIRST snapshot diffs against its baseline, exactly as above.
     by_chapter_q = """
     WITH s AS (
       SELECT d.chapter_id, d.snapshot_date, d.words,
              COALESCE(
                LAG(d.words) OVER (PARTITION BY d.chapter_id ORDER BY d.snapshot_date),
                b.words
              ) AS prev_words
       FROM composition_daily_progress d
       LEFT JOIN composition_progress_baseline b
         ON b.user_id = d.user_id AND b.project_id = d.project_id AND b.chapter_id = d.chapter_id
       WHERE d.user_id = $1 AND d.project_id = $2 AND d.snapshot_date <= $3
     )
     SELECT chapter_id,
            SUM(CASE WHEN prev_words IS NULL THEN 0
                     ELSE GREATEST(words - prev_words, 0) END)::int AS words
     FROM s
     WHERE snapshot_date = $3          -- the anchor DAY only (the panel says "by chapter (today)")
     GROUP BY chapter_id
     HAVING SUM(CASE WHEN prev_words IS NULL THEN 0
                     ELSE GREATEST(words - prev_words, 0) END) > 0
     ORDER BY words DESC
     """
     ```
     ⚠ **The `WITH s` window must scan ALL history** (`snapshot_date <= $3`), not just the anchor day — `LAG`
     needs the *previous* snapshot to difference against. Filtering the day happens **after** the window
     (`WHERE snapshot_date = $3` in the outer select). Getting this backwards makes every chapter's day-words
     equal its total word count.
   - **NEW goal methods** (same repo — the goal is a progress fact, and a one-method repo is a smell).
     🔴 **THE TRI-STATE IS THE WHOLE POINT** (§2 P2-CLEAR): the read must distinguish **no row** from **a row
     whose value is NULL**. `fetchval` collapses both to `None` — **use `fetchrow`.**
     ```python
     async def get_goal_row(self, user_id: UUID, project_id: UUID) -> tuple[bool, int | None]:
         """Returns (row_exists, daily_goal). THE TRI-STATE:
              (False, None) → no per-user row      ⇒ fall through to the legacy work.settings goal
              (True,  None) → the user CLEARED it  ⇒ 'none'. DOES NOT fall through. This row SHADOWS
                              work.settings.daily_goal — that shadow is the entire point of BE-P2.
              (True,  N)    → the user's goal      ⇒ 'user'
         ⚠ NEVER collapse this with a COALESCE or an `or`. `row.daily_goal or legacy` silently
           re-introduces the DELETE bug: Bob clears HIS goal and inherits ALICE'S book-wide one."""
         async with self._pool.acquire() as c:
             row = await c.fetchrow(
                 "SELECT daily_goal FROM composition_progress_goal WHERE user_id=$1 AND project_id=$2",
                 user_id, project_id,
             )
         return (False, None) if row is None else (True, row["daily_goal"])

     async def set_goal(self, user_id: UUID, project_id: UUID, goal: int | None) -> None:
         """ONE statement for both set and clear. `goal is None` = the user cleared it — the ROW STAYS.
         🔴 NEVER DELETE. A delete re-exposes work.settings.daily_goal, so clearing your own goal would
            resurrect a collaborator's shared book goal and measure your counter against it — the exact
            tenancy defect this table exists to kill, re-entered through the clear path.
         PER-USER by construction: every read and write filters on user_id. A collaborator can never see
         or set another author's goal.
         ⚠ DO UPDATE, not DO NOTHING — do NOT copy composition_progress_baseline's ON CONFLICT DO NOTHING;
           a goal is re-settable."""
         async with self._pool.acquire() as c:
             await c.execute(
                 """
                 INSERT INTO composition_progress_goal (user_id, project_id, daily_goal, updated_at)
                 VALUES ($1, $2, $3, now())
                 ON CONFLICT (user_id, project_id)
                 DO UPDATE SET daily_goal = EXCLUDED.daily_goal, updated_at = now()
                 """,
                 user_id, project_id, goal,      # $3 is None on clear
             )
     ```
     ⚠ The `ON CONFLICT` target `(user_id, project_id)` **matches the full PK** — there is no partial index,
     so no predicate to repeat.

3. **`app/routers/progress.py`**
   - **NEW resolver** — the read-through fallback + the **SET-1 source tier**. 🔴 **GATE ON ROW PRESENCE, NOT
     ON `IS NOT NULL`:**
     ```python
     async def _resolve_goal(
         progress: DailyProgressRepo, user_id: UUID, project_id: UUID, settings: dict[str, Any],
     ) -> tuple[int | None, str]:
         """SET-1 — the EFFECTIVE value AND ITS SOURCE TIER. No silent hidden default.
         'user'        → composition_progress_goal, value NOT NULL (the per-user SSOT; SET-3: one home)
         'none'        → EITHER the user has a row whose goal is NULL (they CLEARED it — this SHADOWS the
                         legacy value and does NOT fall through), OR there is nothing anywhere
         'work_legacy' → NO per-user row at all, and work.settings.daily_goal is a positive int
                         (READ-ONLY legacy; the writer never touches it again, so nobody who already set a
                         goal silently loses it)
         🔴 The CLEARED case is why this is a tri-state and not a COALESCE. See get_goal_row's docstring."""
         exists, user_goal = await progress.get_goal_row(user_id, project_id)
         if exists:
             return (user_goal, "user") if user_goal is not None else (None, "none")
         legacy = _coerce_goal(settings or {})          # KEEP _coerce_goal — it is the fallback reader
         return (legacy, "work_legacy") if legacy is not None else (None, "none")
     ```
     ⚠ **The source enum stays CLOSED at 3.** Do **not** add a 4th value for "cleared": under SET-1 the
     effective value of a cleared goal **IS** none, so `'none'` is honest, and the FE needs **zero** new
     branching (`ProgressPanel.tsx:65,104` already gate on `goal != null`, so the bar and the `ReferenceLine`
     simply vanish).
   - `get_progress`: replace `"daily_goal": _coerce_goal(work.settings or {})` with the resolver, and add the
     two new fields:
     ```python
     goal, source = await _resolve_goal(progress, user_id, project_id, work.settings or {})
     return {
         "today": anchor.isoformat(),
         "today_words": by_date.get(anchor, 0),
         "book_total": agg.book_total,
         "daily_goal": goal,
         "daily_goal_source": source,                                    # BE-P2′ (SET-1)
         "by_chapter": [{"chapter_id": str(cid), "words": w} for cid, w in agg.by_chapter],  # BE-P1
         "current_streak": _current_streak(by_date, anchor),
         "sparkline": _sparkline(by_date, anchor),
     }
     ```
   - **NEW route:**
     ```python
     class ProgressGoalBody(BaseModel):
         # SET-5 — enum/range-validated on write. 0 clears (→ row deleted). Negative is a 422, never a
         # silently-coerced 0. The upper cap turns garbage into a 422 instead of a 500 on the INT column.
         goal: int = Field(ge=0, le=1_000_000)

     @router.put("/works/{project_id}/progress/goal")
     async def set_progress_goal(
         project_id: UUID,
         body: ProgressGoalBody,
         user_id: UUID = Depends(get_current_user),
         works: WorksRepo = Depends(get_works_repo),
         progress: DailyProgressRepo = Depends(get_daily_progress_repo),
         grant: GrantClient = Depends(get_grant_client_dep),
     ) -> dict[str, Any]:
         """The caller's OWN daily word goal (BE-P2). PER-USER, not per-book.
         It used to live in composition_work.settings — a SHARED row every EDIT grantee can write —
         while the words it is measured against are per-user. Alice's goal became Bob's target. That is
         a tenancy defect (CLAUDE.md User Boundaries), and this route is the fix.
         VIEW is the right tier: setting YOUR OWN goal on a book you can read is not an edit to the book."""
         work = await works.get(project_id)
         if work is None:
             raise HTTPException(status_code=404, detail="work not found")
         await _gate_book(grant, work.book_id, user_id, GrantLevel.VIEW)
         # 🔴 COERCE ONCE, AT THE ROUTE BOUNDARY. 0 is a SENTINEL for "clear", never a stored value
         # (the CHECK is `daily_goal > 0`; _coerce_goal already treats non-positive as absence).
         # Pass `stored` — NEVER body.goal — to the repo.
         stored: int | None = body.goal if body.goal > 0 else None
         await progress.set_goal(user_id, project_id, stored)
         # The response is the RESOLVER'S OUTPUT, not an echo. A clear must report the TRUTH the panel will
         # now render — no silent hidden default.
         eff, source = await _resolve_goal(progress, user_id, project_id, work.settings or {})
         return {"goal": eff, "source": source}
     ```
     ⚠ **`GrantLevel.VIEW`, deliberately.** The goal is the caller's own per-user stat, exactly like
     `report_progress` (`:157`) and `baseline_progress` (`:185`), which both gate on VIEW. Requiring EDIT would
     stop a read-only collaborator from setting their own writing target — which is nonsense.
     *(⚠ Spec 31 calls this gate `_require_work`; **the real helper in this file is `_gate_book`
     (`progress.py:38`)** — use it, do not invent a new name.)*
     ⚠ 🔴 **`PUT {goal: 0}` returns `{goal: null, source: 'none'}` and the ROW STILL EXISTS.** It does **not**
     return the legacy goal. That is the tenancy fix; a DELETE would undo it.
   - **`_coerce_goal` KEEPS its docstring but gains one line:** *"LEGACY READ ONLY (BE-P2). The writer is
     gone; do not add one back. This is NOT dead code — it is the read-through fallback QC-6 relies on."*
   - 🔴 **`useSetDailyGoal`'s `patchWork` caller is DELETED in W1-08.** That deletes this wave's exposure to
     **BE-18** without waiting on BE-18 itself. ⚠ **And BE-18's row text is WRONG — correct it, do not build
     it** (F40): server-side OCC on `PATCH /works` **already ships**. **Touch NOTHING in `PATCH /works/{pid}`
     this wave** — not the router, not `WorksRepo.update`, not `compositionApi.patchWork`. **Any If-Match /
     blob-merge edit appearing in a W1-07/W1-08 diff is scope creep and `/review-impl` should reject it at the
     wave gate.** BE-18's real, reduced scope (FE-only, `patchWork(…, ifMatch?)` + a 412 retry on the two
     surviving callers) belongs to **Wave 6** (spec 36, `G-WORK-SETTINGS`).

4. 🔴 **BE-P3 — CLAMP THE CLIENT-SUPPLIED LOCAL DATE (F38).** One file + its test, ~30 min, **do NOT defer.**
   Replace `_parse_local_date` (`progress.py:56-62`):
   ```python
   _MAX_LOCAL_SKEW_DAYS = 1  # real UTC offsets span UTC-12..UTC+14 ⇒ a genuine local date is ALWAYS
                             # within ±1 day of the current UTC date.

   def _parse_local_date(raw: str) -> date:
       """Parse + BOUND a client-supplied local date (YYYY-MM-DD). The client owns the date so streaks
       honour the writer's midnight (not UTC) — but an UNBOUNDED client date lets a hand-crafted
       `today`/`date` FABRICATE OR INFLATE A STREAK. Anything further out is a bad clock or a forged
       value → 422 (never silently written on a wrong day)."""
       try:
           d = date.fromisoformat(raw)
       except ValueError:
           raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD")
       utc_today = datetime.now(timezone.utc).date()
       if abs((d - utc_today).days) > _MAX_LOCAL_SKEW_DAYS:
           raise HTTPException(status_code=422, detail="date must be within 1 day of the server date (UTC)")
       return d
   ```
   **Both existing call sites already funnel through it** — `get_progress` (`:117`, the `today` query param)
   and `report_progress` (`:157`, `body.date`) — **so no other edit is needed.** `POST /progress/baseline`
   takes no date; leave it alone. **Frontend: NO change** (`api.ts:304,311` already send the device's local
   date, which by construction lands inside the window).
   ⚠ **422, not a silent clamp-to-nearest** — silently rewriting the date would write the snapshot to a day the
   user did not write on, which is worse than a loud reject the FE can ignore (the report is best-effort and
   never blocks editing). Update the router docstring (`:17-18`) to say so.

5. 🔴 **BE-P4 — REDACT THE LEGACY KEY AT THE MCP BOUNDARY (F39).** In `composition_get_work`
   (`app/mcp/server.py:333`), before returning:
   ```python
   out = work.model_dump(mode="json")
   # SET-3 (one home, one name): the daily goal lives in `composition_progress_goal` (per-user), NOT in
   # this shared per-book blob. A legacy `settings.daily_goal` is kept ONLY as the read-through fallback
   # in GET /works/{pid}/progress — never surfaced here, or an agent asked "what's my daily goal?" reports
   # a FROZEN goal that contradicts the real one.
   if isinstance(out.get("settings"), dict):
       out["settings"].pop("daily_goal", None)
   return out
   ```

6. 🔴 **QC-7 + the gateway rule, made MECHANICAL** (§2 QC-7 / §5 gateway rules). Two ~10-line introspection
   tests over `app.main:app.routes` — put them in **NEW** `tests/unit/test_route_table.py`:
   - `test_no_estimate_route_exists_under_v1_composition` — **no** route path contains `estimate`. *(Three
     invented per-action estimate routes already 404 in production, plan-30 §3.3. This test is what stops the
     fourth from being born at 3am.)*
   - `test_every_public_router_is_mounted_under_v1_composition` — the gateway matches the **literal** prefix; a
     `/v1/studio/*` route would 404 at the edge while every unit test stayed green.

**Tests**

- **NEW** `services/composition-service/tests/unit/test_progress_goal_router.py`:
  - `test_put_goal_writes_only_the_new_table` — spy the repo; assert `set_goal` called and **`patch`/`update`
    on WorksRepo is NEVER called**. *(SET-3: one home, one name.)*
  - `test_put_goal_zero_clears_and_returns_source_none` (with no legacy).
  - `test_put_goal_negative_422`.
  - `test_put_goal_requires_view_grant_404_on_no_grant_403_on_under_tier`.
  - `test_get_progress_returns_source_user_when_a_user_goal_exists`.
  - `test_get_progress_falls_back_to_work_settings_with_source_work_legacy` (**no per-user row at all**).
  - `test_get_progress_returns_source_none_and_goal_null_when_neither_exists`.
  - 🔴 **`test_clearing_a_user_goal_does_NOT_re_expose_the_legacy_goal`** — **THE regression test that a DELETE
    would fail.** Seed `work.settings.daily_goal = 2000` → `GET` returns `2000 / 'work_legacy'` →
    `PUT {goal: 500}` → `GET` returns `500 / 'user'` → **`PUT {goal: 0}`** → `GET` returns
    **`daily_goal: null, source: 'none'`** and explicitly **NOT** `2000 / 'work_legacy'`.
    *(An earlier draft of this plan specified a DELETE on clear and a test asserting the OPPOSITE of this. That
    was the tenancy defect re-entering through the clear path — §2 P2-CLEAR.)*
  - 🔴 `test_report_rejects_far_future_date` — `POST /progress/report` with `date = utc_today + 5d` ⇒ **422**,
    **and the repo's `report` was NOT called** (a forged row must never reach the table). Plus
    `test_report_rejects_far_past_date` and `test_get_progress_accepts_plus_and_minus_one_day` (the legitimate
    UTC+14 / UTC-12 writer must not be broken). **[BE-P3]**
  - 🔴 `test_composition_get_work_redacts_daily_goal` (in the MCP suite) — seed a Work with
    `settings={"daily_goal": 400, "voice": "wry"}`; call `composition_get_work`; assert
    `"daily_goal" not in result["settings"]` **AND** `result["settings"]["voice"] == "wry"` (**the redaction
    must not eat the blob**). **[BE-P4]**
- **NEW** `services/composition-service/tests/integration/db/test_progress_goal.py` — **real Postgres.**
  **MUST carry:**
  ```python
  pytestmark = [
      pytest.mark.skipif(not os.getenv("TEST_COMPOSITION_DB_URL"), reason="needs a throwaway test DB"),
      pytest.mark.xdist_group("pg"),
  ]
  ```
  - 🔴 **`test_two_users_on_one_book_have_independent_goals`** — **THE test of this milestone.** Seed ONE
    work; user A sets 2000; **user B reads → NOT 2000** (B sees its own row, or the legacy/none fallback);
    user B sets 500; **user A still reads 2000.** Then A's `GET /progress` reports 2000 while B's reports 500.
    **A MOCK CANNOT PROVE THIS — a mock would encode the bug.** (memory:
    `mocked-client-hides-server-side-default-filters`.) **Assert on the SQL predicate, not a mock.**
  - 🔴 **`test_goal_zero_NULLS_the_row_and_the_row_STILL_EXISTS`** (⚠ **not** "deletes the row") —
    `PUT {goal: 0}` returns **200** (not a 500 from `daily_goal_check`), `SELECT daily_goal` for that PK
    **IS NULL**, and `SELECT count(*) = 1` — **the row survives.**
  - `test_goal_check_constraint_rejects_zero_on_direct_insert` (and **accepts NULL**).
  - ⚠ **Register `composition_progress_goal` in the file's TRUNCATE list** (`test_repositories.py:46`).
  - `test_by_chapter_diffs_against_the_baseline_and_excludes_zero_word_chapters` — seed a baseline of 800 +
    a snapshot of 1000 for Ch-A on the anchor date, and a snapshot equal to its baseline for Ch-B ⇒
    `by_chapter == [(A, 200)]`; **B is absent, not `(B, 0)`**.
  - `test_by_chapter_windows_lag_over_ALL_history_not_just_the_anchor_day` — seed Ch-A snapshots on D-1
    (900) and D (1000) with baseline 800 ⇒ the anchor day reports **100**, not 200. *(This test catches the
    exact query-shape mistake flagged above.)*
- **EXTEND** `test_migrate.py`: `composition_progress_goal` exists, PK `(user_id, project_id)`,
  `daily_goal = 0` raises `CheckViolationError`, **and it has NO `book_id` column** (assert the column list —
  a later agent will want to add one "for symmetry").

**DoD evidence:** `composition-service: <N> passed` (full suite, `-n auto --dist loadgroup`), with
`test_two_users_on_one_book_have_independent_goals` **named in the output**. Paste it.

---

### `W1-08` — the `progress` PANEL: rewrite `useSetDailyGoal`, port `ProgressPanel`, register

> **dependsOn:** `W1-07`, `W1-00` · **kind:** FE · **Enum `N+1` → `N+2`.**

**Files**

1. **`frontend/src/features/composition/types.ts`** — `ProgressStats` gains:
   ```ts
   daily_goal_source: 'user' | 'work_legacy' | 'none';
   by_chapter: { chapter_id: string; words: number }[];
   ```

2. **`frontend/src/features/composition/api.ts`** — **NEW**
   ```ts
   setDailyGoal(projectId: string, goal: number, token: string): Promise<{ goal: number | null; source: 'user'|'work_legacy'|'none' }> {
     return apiJson(`${BASE}/works/${projectId}/progress/goal`, {
       method: 'PUT', body: JSON.stringify({ goal }), token,
     });
   }
   ```

3. **`frontend/src/features/composition/hooks/useProgress.ts`** — 🔴 **REWRITE `useSetDailyGoal`. DELETE the
   `patchWork` caller entirely.**
   ```ts
   /**
    * The author's OWN daily word goal (BE-P2). PER-USER, server-side (SET-2).
    *
    * It used to write work.settings.daily_goal through patchWork — a SHARED per-book row, with a
    * FULL-BLOB REPLACE and no If-Match (repositories/works.py:311). Two consequences, both gone now:
    *   • TENANCY: Alice's goal became Bob's target while Bob's word counts are per-user.
    *   • LOST UPDATE: two concurrent settings writes lost one.
    * The new signature takes NO `currentSettings` — there is nothing to hand-merge. If you find yourself
    * re-adding it, you are re-introducing the bug.
    */
   export function useSetDailyGoal(projectId: string | undefined, token: string | null) {
     const qc = useQueryClient();
     return useMutation({
       mutationFn: (goal: number) => compositionApi.setDailyGoal(projectId!, goal, token!),
       onSuccess: () => qc.invalidateQueries({ queryKey: ['composition', 'progress', projectId] }),
     });
   }
   ```
   ⚠ **The signature changes** (`(bookId, token)` + `{projectId, currentSettings, goal}` → `(projectId, token)`
   + `goal`). The **only** caller is `ProgressPanel.tsx:28,42`. Update it. **`grep -rn "useSetDailyGoal"` to
   be sure.**

4. **`frontend/src/features/composition/components/ProgressPanel.tsx`** — props change
   (`settings` and `bookId` are **gone**; QC-6):
   ```ts
   type Props = { projectId: string; token: string | null };
   ```
   - `saveGoal` → `setGoal.mutate(Math.max(0, Math.floor(Number(goalDraft) || 0)), { onSuccess: () => setGoalDraft('') })`.
   - **SET-1 — RENDER THE SOURCE TIER.** Below the goal input (mock state ⑤):
     ```tsx
     <span data-testid="progress-goal-source" className="text-[11px] text-muted-foreground">
       {data.daily_goal_source === 'user'
         ? t('progressPanel.goalYours', { defaultValue: 'your goal · not shared with collaborators' })
         : data.daily_goal_source === 'work_legacy'
           ? t('progressPanel.goalLegacy', { defaultValue: "This goal came from the book's shared settings. Setting it now makes it yours." })
           : t('progressPanel.goalNone', { defaultValue: 'No goal set' })}
     </span>
     ```
     **A stored-but-unread setting is a bug; an effective value with no visible source tier is the
     "grounding always-on / reasoning silently-off" bug class. This span IS the SET-1 compliance.**
   - **BE-P1 — the by-chapter breakdown** (mock state ⑤):
     ```tsx
     {data.by_chapter.length > 0 && (
       <div data-testid="progress-by-chapter" className="rounded-lg border bg-card px-3 py-2">
         <div className="mb-1 text-[11px] uppercase tracking-wide text-muted-foreground">
           {t('progressPanel.byChapter', { defaultValue: 'by chapter (today)' })}
         </div>
         {data.by_chapter.map((c) => (
           <div key={c.chapter_id} className="flex justify-between text-xs">
             <span className="truncate">{chapterTitle(c.chapter_id)}</span>
             <span className="tabular-nums">{c.words.toLocaleString()}</span>
           </div>
         ))}
       </div>
     )}
     ```
     `chapterTitle` resolves from `booksApi.listChapters` — **reuse the exact query
     `QualityCriticPanel.tsx:33-37` makes** (`['studio','quality-critic','chapters', bookId]` → **rename the
     key to `['studio','chapters', bookId]` and use it from BOTH**; one name, one concept). Unresolved id ⇒
     render the raw id, never blank.
   - **COLD START** (mock state ⑤): `book_total === 0 && sparkline.every(p => p.words === 0)` ⇒
     `data-testid="progress-coldstart"` → *"Save a chapter and your first day lands here"* — **not an error.**

5. **`frontend/src/pages/ChapterEditorPage.tsx` / `CompositionPanel.tsx:847`** — the legacy mount passes
   `settings={work.settings} bookId={bookId}`. **Remove those two props** (the component no longer takes
   them). This is a **required** edit — the legacy page must keep compiling. Its tests must stay green.

6. **NEW `frontend/src/features/studio/panels/StudioProgressPanel.tsx`** — the dock wrapper.
   ⚠ **File name vs panel id vs component name — get all three right:** the panel **id** is `progress`
   (§8.0 ledger row 4); the **component** must not collide with `features/composition/components/ProgressPanel`.
   Export `StudioProgressPanel`; root `data-testid="studio-progress-panel"`.
   ```tsx
   export function StudioProgressPanel(props: IDockviewPanelProps) {
     useStudioPanel('progress', props.api);
     const host = useStudioHost();
     const { accessToken } = useAuth();
     const work = useQualityWork(host.bookId, accessToken);   // QC-2: category `editor`, but the SAME gate
     if (work.kind !== 'ready') return <QualityWorkGate state={work} testIdPrefix="progress" />;
     return (
       <div data-testid="studio-progress-panel" className="h-full min-h-0 overflow-auto">
         <ProgressPanel projectId={work.projectId} token={accessToken} />
       </div>
     );
   }
   ```

7. **GG-8 registration** — `catalog.ts` row (**`category: 'editor'`**, QC-2 — *a word-count streak is not a
   quality judgment*), `en/studio.json` (`panels.progress.{title,desc,guideBody}` + the `progressPanel.*`
   keys), 17 locales via `scripts/i18n_translate.py`, `frontend_tools.py` enum + description clause
   (`'progress' = words written today, streak, daily goal, and the book total.`), **regenerate**
   `contracts/frontend-tools.contract.json`.
   **`progress` is NOT a QualityHubPanel card.** Do not add it.

**Tests**

- `frontend/src/features/composition/components/__tests__/ProgressPanel.test.tsx` (extend):
  - **SET-4 (consumed, proven by EFFECT):** `changing the goal moves the goal bar AND the ReferenceLine` —
    render with `daily_goal: 1000, today_words: 500` ⇒ bar width `50%`; re-render with `daily_goal: 500` ⇒
    `100%` and the `ReferenceLine` `y` prop is 500. *(A checklist item is DONE only when a test asserts its
    effect.)*
  - `renders "your goal · not shared with collaborators" when source==='user'`.
  - `renders the legacy note when source==='work_legacy'`.
  - `renders the by-chapter breakdown, resolving titles, and omits it when empty`.
  - `renders the cold-start copy (not an error) when nothing has ever been written`.
  - **`setting a goal calls compositionApi.setDailyGoal and NEVER compositionApi.patchWork`** — spy both.
    *This test is the regression lock on the tenancy fix.*
- NEW `frontend/src/features/studio/panels/__tests__/StudioProgressPanel.test.tsx`: the three Work-gate
  states + `renders studio-progress-panel when ready`.
- The 4 drift-locks: counts move by exactly **+1**.

**DoD evidence:** *"enum N+1→N+2, three-way equality green; `frontend: <N> passed`; the
`NEVER patchWork` spy test and the SET-4 goal-bar-effect test named."*

---

## M3 — SELF-HEAL + THE CRITIC LINK (closes `G-POLISH-SELFHEAL` + `D-QUALITY-CRITIC-HEAL-LINK`) · enum `N+2` → `N+3`

> 🔴 **BLOCKED ON `W1-01` (X-1).** Without it, `quality-heal`'s `ModelPicker` empty state renders
> `AddModelCta`, whose `<Link>` **tears down the whole dock.** Do not start M3 until `W1-01` is green.

### `W1-09` — the hoist chokepoint: `applyHealedDocument` on `ManuscriptUnitApi` (QC-4)

> **dependsOn:** — · **kind:** FE
> 🔴 **THE MOST DANGEROUS SLICE IN THE WAVE.** Read F18 twice before typing.

**File:** `frontend/src/features/studio/manuscript/unit/ManuscriptUnitProvider.tsx`

**The trap, restated.** `TiptapEditorHandle.setContent` sets `isExternalUpdate.current = true` around
`editor.commands.setContent(...)`, and `onUpdate` **early-returns on that flag** (`TiptapEditor.tsx:171-174,
252-257`). **A heal applied with `setContent` alone does NOT dirty the hoist** — `workingBody` stays `null`,
`isDirtyState()` stays `false`, the user hits ⌘S, `save()` early-returns (`:216`), and **the heal silently
vanishes on the next reload.** That is a *silent success*, which is a bug, not an environment quirk. The
legacy `ChapterEditorPage.handleApplyPolish` (`:591-602`) does exactly this.

**⇒ `applyHealedDocument` MUST push the doc into the editor AND call the hoist's own `setBody(doc, text)`.**

**The change** — add to `ManuscriptUnitApi` (after `applyProposedEdit`):

```tsx
/** The result of an AI whole-document write. NEVER a bare boolean — every failure mode has a
 *  DIFFERENT message the user must see, and a silent no-op here means the author believes their
 *  prose was fixed when it was not. */
export type ApplyHealedResult =
  | { kind: 'applied' }
  | { kind: 'no-editor' }
  | { kind: 'stale'; reason: 'chapter' | 'version' | 'dirty' };

/** #31 QC-4 — the ONE chokepoint for "an AI replaced this whole chapter".
 *  `applyProposedEdit` covers insert/replace-selection; NEITHER replaces the document, and the hoist's
 *  own doc-comment says this seam exists so bookkeeping has ONE chokepoint instead of every consumer
 *  reaching into a raw ref. quality-heal EXTENDS the chokepoint; it does not bypass it.
 *
 *  The three STALE guards are the whole point (F-Q6). `usePolishProposals` splices `healedText` out of a
 *  `sourceText` fetched AT PROPOSE TIME, and has carried `draftVersion` since it was written with NOBODY
 *  READING IT. On the legacy page the window was masked by `key={chapterId}` remount + co-location with
 *  the editor. In the dock, quality-heal is a PERSISTENT TAB that survives chapter switches, next to a
 *  live dirty editor. Applying a stale splice silently REVERTS everything typed since Polish ran. */
applyHealedDocument: (params: {
  text: string;
  chapterId: string;
  expectedDraftVersion: number | null;
}) => ApplyHealedResult;
```

🔴 **ONE PURE GUARD FUNCTION, CONSUMED TWICE** (`Q-31-F-Q6-STALE-DATA-LOSS` (1)) — *this is what makes
"rendered AND enforced" impossible to drift.* **NEW `frontend/src/features/studio/manuscript/unit/healGuard.ts`:**

```ts
export type HealGuard =
  | { kind: 'ok' }
  | { kind: 'stale'; reason: 'chapter' | 'version' | 'dirty' }
  | { kind: 'no-editor' };

/** PRECEDENCE IS FIXED — do not re-derive it.
 *  1. proposalChapterId == null OR unitChapterId !== proposalChapterId → stale/chapter
 *  2. unitIsDirty                                                      → stale/dirty
 *  3. proposalDraftVersion == null || unitVersion == null
 *     || unitVersion !== proposalDraftVersion                          → stale/version
 *     🔴 FAIL CLOSED: an UNVERIFIABLE version is STALE, never "probably fine".
 *  4. !hasEditor                                                       → no-editor
 *  else ok. */
export function evaluateHealGuard(args: {
  unitChapterId: string | null; unitVersion: number | undefined; unitIsDirty: boolean; hasEditor: boolean;
  proposalChapterId: string | null; proposalDraftVersion: number | null;
}): HealGuard;
```
Unit-test it **directly**, one case per branch **plus the two null/fail-closed cases**.

Implementation in the provider (place next to `applyProposedEdit`):

```tsx
// 🔴 EXTRACT the doc-builder into `@/lib/tiptap-utils` as `textToTiptapDoc(text)` and call it from BOTH
// sites — here AND the legacy ChapterEditorPage.tsx:593-598, whose paragraph/`_text` shape this is. One
// impl; the legacy page keeps working. (`setBody` re-runs addTextSnapshots, so `_text` is belt-and-braces.)
import { textToTiptapDoc } from '@/lib/tiptap-utils';
import { evaluateHealGuard, type HealGuard } from './healGuard';

const applyHealedDocument = useCallback((params: {
  text: string; chapterId: string; expectedDraftVersion: number | null;
}): HealGuard => {
  // Evaluate against stateRef.current, NOT the closed-over `state` — the hoist re-checks at CLICK time,
  // because the state can change between render and click. The guard is ENFORCED, not merely displayed.
  const s = stateRef.current;
  const g = evaluateHealGuard({
    unitChapterId: s.chapterId, unitVersion: s.version, unitIsDirty: isDirtyState(s),
    hasEditor: editorRef.current != null,
    proposalChapterId: params.chapterId, proposalDraftVersion: params.expectedDraftVersion,
  });
  if (g.kind !== 'ok') return g;

  const doc = textToTiptapDoc(params.text);
  editorRef.current!.setContent(doc);
  // 🔴🔴 setContent SUPPRESSES onUpdate (TiptapEditor.tsx:252-257 sets isExternalUpdate; onUpdate early-
  // returns on it at :171-174), and EditorPanel.tsx:394 is the ONLY caller of setBody. Without this line
  // the hoist NEVER goes dirty → workingBody stays null → ⌘S early-returns → THE HEAL IS SILENTLY
  // DISCARDED on the next chapter switch/reload. That is a SECOND data-loss path, inside the SUCCESS
  // branch. The heal never persists behind the author's back either: it dirties the doc and THE AUTHOR SAVES.
  setBody(doc, params.text);
  return { kind: 'ok' };
}, [setBody]);
```

Add `applyHealedDocument` to the `useMemo` api object **and its dependency array** (both, or it goes stale on
every keystroke).

🔴 **PROVENANCE — a deliberate deviation from the spec's table (PO may veto).** **Do NOT mark the doc.** A
whole-document replace can only mark the **ENTIRE** document as AI-written, which is **a lie about the ~99% of
prose the author wrote.** Instead **capture an undo checkpoint**, exactly as the legacy page does
(`ChapterEditorPage.tsx:592`): extend `useManuscriptCheckpoints.ts` — widen `ManuscriptCheckpoint.kind` to
`'insert' | 'replace' | 'heal'` (`:40`) and add an `applyHealedDocument` wrapper mirroring the existing
`applyProposedEdit` wrapper (capture the pre-revision restore point, **then** delegate; capture **only** when
the result is `{kind:'ok'}`). *Per-span provenance on a heal needs a per-edit transaction path — note it, do
not build it here.*

🔴 **FIX-NOW while you are here** (one line, cheaper than a defer row): `CompositionPanel.tsx:861` is
`onApply={onApplyPolish ?? (() => {})}` — **a literal silent no-op on the popout route.** Make
`PolishPanel.onApply` **optional** and, when absent, **disable Apply with the same no-editor banner.**
**Never a silent no-op.**

**Tests** — NEW `.../unit/__tests__/healGuard.test.ts` + `.../unit/__tests__/applyHealedDocument.test.tsx`
(render the provider with a fake `editorRef` handle):
- `healGuard.test.ts`: **5 branch cases + the 2 fail-closed null cases.**
- 🔴 **`an applied heal marks the hoist DIRTY (setContent alone does not — this is the bug)`** — after
  `applyHealedDocument` returns `ok`, `unit.isDirty === true` **and** `state.workingBody` contains the healed
  text. *THE test — the regression pin for the `setContent`-suppresses-`onUpdate` trap.*
- `chapter mismatch → {kind:'stale', reason:'chapter'} and setContent is NOT called`.
- `version mismatch → {kind:'stale', reason:'version'} and setContent is NOT called`.
- `a dirty hoist → {kind:'stale', reason:'dirty'} and setContent is NOT called`.
- `no live editor → {kind:'no-editor'}`.
- 🔴 **`expectedDraftVersion === null is STALE, not a skip`** — **fail closed.** *(An earlier draft of this plan
  said "`expectedDraftVersion === null` skips the version guard". **That is inverted**: an unverifiable version
  is exactly the case where the splice offsets cannot be trusted.)*
- `textToTiptapDoc splits on blank lines and never produces an empty doc` — **and the legacy
  `ChapterEditorPage` still renders** (it now imports the same helper).
- `a successful heal pushes a kind:'heal' checkpoint`.

**DoD evidence:** the 8 tests named; `frontend: <N> passed`.

---

### `W1-10` — `usePolishProposals` → the react-query cache (QC-8). **Return shape UNCHANGED.**

> **dependsOn:** — · **kind:** FE

**File:** `frontend/src/features/composition/hooks/usePolishProposals.ts` — **rewrite in place.**

> 🔴 **STEP 0, BEFORE YOU TOUCH THE HOOK — WRITE THE MISSING GATE** (`Q-31-LEGACY-POLISHPANEL-REGRESSION`).
> **`PolishPanel.test.tsx` CANNOT gate this rewrite: it MOCKS THE HOOK MODULE OUT ENTIRELY** (F41,
> `vi.mock('../../hooks/usePolishProposals')`, `:8-11`) — the suite is **structurally blind to any hook
> change**, and there is **no `usePolishProposals` test at all** today (27 hook tests in that dir; zero for it).
> **Create `frontend/src/features/composition/hooks/__tests__/usePolishProposals.test.tsx` as a
> CHARACTERIZATION test against the CURRENT `useState` impl** (`renderHook` + `vi.mock('../../api')` stubbing
> `compositionApi.proposeSelfHeal`; **keep `applySelfHealEdits` REAL — do not mock it**). Pin the full return
> shape and 5 behaviours: (a) `run()` populates proposals/sourceText/draftVersion/stats and flips `ran`;
> (b) `acceptedIds` is seeded from `p.recommended ?? p.tier === 'deterministic'`; (c) `toggle(id)` flips one id;
> (d) `bulk(on, tier?)` is tier-scoped; (e) **`healedText === sourceText` when `acceptedIds` is empty, and
> `healedText !== ''` whenever `sourceText !== ''`**. **Run it GREEN on the OLD impl. Commit. THEN rewrite.**
> The same file must be green after. **THAT is the regression gate** — not `PolishPanel.test.tsx`.
> *(~60 lines, and it is the only thing standing between this rewrite and a chapter-blanking bug — FIX-NOW.)*

> 🔴 **AND `PolishPanel.test.tsx` RENDERS BARE — no `QueryClientProvider`** (F41, `:32`, `:45`). **The instant
> the hook touches `useQuery`/`useMutation` those tests throw *"No QueryClient set"*.** Wrap both renders in
> `<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>` (the pattern
> already at `CompositionPanel.test.tsx:87`). **This edit is PART OF THE SLICE, not a surprise** — the spec's
> *"legacy PolishPanel still passes its own tests"* gate depends on it.

**Why:** `quality-critic` and `quality-heal` are **two sibling dock panels with no common React ancestor
other than the app root** (F-Q1). There is no prop to drill. The proposals need a **shared store**, and the
smallest one that already exists in the app is the react-query cache.

**The design (QC-8, verbatim):** key `['composition','self-heal', projectId, chapterId]`, `staleTime:
Infinity`, **NO `queryFn`** — the paid run is a `useMutation` that `setQueryData`s. A cache **miss ⇒ `[]` ⇒
no badge**. **A false badge is impossible by construction.**

🔴 **CACHE THE WHOLE RESPONSE AS ONE ATOM — proposals + sourceText + draftVersion + stats + acceptedIds.
NEVER proposals alone.** Two independent bugs, both fatal:
- **`sourceText` must ride WITH the proposals.** `applySelfHealEdits` bases its output on `sourceText`
  (`let out = sourceText`, `api.ts:706`). If proposals come from the cache while `sourceText` stays in
  `useState`, **a cache-hit remount yields `healedText === ''` → `onApply('')` → THE CHAPTER IS REPLACED WITH
  AN EMPTY DOCUMENT** — and QC-4's `expectedDraftVersion` does **not** catch it, because the cached
  `draft_version` still matches.
- **`acceptedIds` must ride with them too** (§2 QC-8(b)): otherwise a dock remount restores `proposals` +
  `ran:true` but **resets acceptance to empty** ⇒ `healedText === sourceText` ⇒ **Apply burns an OCC draft bump
  writing back unchanged prose.** *Half-cached state is a bug, not a smaller diff.*

```ts
export interface PolishCacheEntry {
  proposals: SelfHealProposal[];
  sourceText: string;
  draftVersion: number | null;
  stats: SelfHealProposalResponse['stats'] | undefined;
  acceptedIds: string[];          // 🔴 IN THE CACHE — see above
}
export const polishKey = (projectId: string | null, chapterId: string | null) =>
  ['composition', 'self-heal', projectId, chapterId] as const;

export function usePolishProposals(
  projectId: string | null, chapterId: string | null, token: string | null, modelRef: string,
) {
  const qc = useQueryClient();
  // No queryFn: the paid run is an explicit user action, never a background refetch. `enabled:false` +
  // staleTime:Infinity means this is a pure READ of whatever the mutation wrote — a cache MISS resolves
  // to undefined ⇒ [] ⇒ no badge, which is exactly right.
  const cached = useQuery<PolishCacheEntry>({
    queryKey: polishKey(projectId, chapterId),
    enabled: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  const entry = cached.data;

  // `rerank` STAYS useState — it is a per-panel INPUT toggle, not shared run OUTPUT.
  const [rerank, setRerank] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runM = useMutation({
    mutationFn: () => compositionApi.proposeSelfHeal(projectId!, { chapterId: chapterId!, modelRef, rerank }, token!),
    onSuccess: (r) => {
      const props = r.proposals ?? [];
      qc.setQueryData<PolishCacheEntry>(polishKey(projectId, chapterId), {
        proposals: props, sourceText: r.source_text ?? '', draftVersion: r.draft_version ?? null, stats: r.stats,
        acceptedIds: props.filter((p) => p.recommended ?? p.tier === 'deterministic').map((p) => p.id),
      });
      setError(null);
    },
    onError: (e) => setError((e as Error).message || 'Polish failed'),
  });
  // toggle / bulk become cache writes. Preserve the tier-scoped `bulk(on, tier?)` SIGNATURE exactly (:74-87).
  // No-op when `prev` is undefined.
  const toggle = (id: string) => qc.setQueryData<PolishCacheEntry>(polishKey(projectId, chapterId),
    (prev) => prev && { ...prev, acceptedIds: /* flip `id` */ … });
  const bulk = (on: boolean, tier?: string) => qc.setQueryData<PolishCacheEntry>(polishKey(projectId, chapterId),
    (prev) => prev && { ...prev, acceptedIds: /* tier-scoped set/clear */ … });

  const run = useCallback(async () => {
    if (!projectId || !chapterId || !token || !modelRef) return;   // the exact guard the old hook had
    await runM.mutateAsync().catch(() => {});                      // onError already surfaced it
  }, [projectId, chapterId, token, modelRef, runM]);

  // Derived — still a Set<string>, because PolishPanel calls .has().
  const acceptedIds = useMemo(() => new Set(entry?.acceptedIds ?? []), [entry]);
  const healedText = useMemo(
    () => applySelfHealEdits(entry?.sourceText ?? '', entry?.proposals ?? [], acceptedIds),
    [entry, acceptedIds],
  );

  // 🔴 THE RETURN SHAPE IS UNCHANGED (QC-1). The legacy PolishPanel destructures exactly these names.
  // `ran` = "a run has landed for THIS chapter" ⇒ derive it from the CACHE, not a useState (a useState
  // `ran` would survive a chapter switch and lie).
  return {
    proposals: entry?.proposals ?? [],
    sourceText: entry?.sourceText ?? '',
    draftVersion: entry?.draftVersion ?? null,
    stats: entry?.stats,
    acceptedIds, loading: runM.isPending, error, ran: entry !== undefined,
    rerank, setRerank, run, toggle, bulk, healedText,
    // What the guard compares against — PINNED to the run, never read from the live prop.
    proposalChapterId: entry ? chapterId : null,
    proposalDraftVersion: entry?.draftVersion ?? null,
  };
}
```
⚠ **`gcTime: Infinity` on BOTH observers is NOT optional** (§2 QC-8(a)) — `App.tsx:10` sets a global
`gcTime: 5 * 60 * 1000`, and `staleTime: Infinity` does **not** stop eviction. Declare it on the writer here
**and** on `quality-critic`'s reader (W1-12) — same value, one shared `polishKey()` helper so the key literal
exists **ONCE**.
⚠ **Memory is bounded and negligible:** one entry per `(projectId, chapterId)` the author actually ran Polish
on **in this browser session**; each is a handful of span/replacement strings. **No eviction policy needed.**
⚠ **The accepted boundary, WRITE IT INTO SPEC 31 §QC-8 as one line:** *"proposals live in the in-memory query
cache; a full page reload clears them, so the `violation-has-fix` badge is session-scoped. Cache miss ⇒ `[]` ⇒
no badge — **a FALSE badge remains impossible.**"* **No persistence layer, no localStorage** (the Data
Persistence Rules forbid it for user data anyway). *(PO veto hook: if bounding memory matters more than the
badge, use `gcTime: 24 * 60 * 60 * 1000` — same test, different constant.)*

**Tests** — `frontend/src/features/composition/hooks/__tests__/usePolishProposals.test.tsx` (the
**characterization** file from Step 0 — the same file must be green **before and after** the rewrite):
- `a run writes the whole atom into the query cache under ['composition','self-heal',projectId,chapterId]`.
- `a second hook instance on the SAME chapter reads the proposals from the cache without re-running` —
  **this is the whole point of the slice.**
- `a hook instance on a DIFFERENT chapter reads [] (cache miss ⇒ no badge, never a false one)`.
- `the return shape is unchanged` — assert the exact key set **and `acceptedIds instanceof Set`**.
- 🔴 **`a remount restores acceptedIds from the cache (not an empty set)`** — the paid-no-op-Apply footgun.
- 🔴 **`it('survives gc after both panels close (QC-8 gcTime: Infinity)')`** — build ONE `QueryClient` with the
  app's **real** defaults (`gcTime: 5*60*1000`) + `vi.useFakeTimers()`: render the writer → mutate → assert
  proposals present → **unmount BOTH observers** → `vi.advanceTimersByTime(6 * 60 * 1000)` → mount **only** the
  critic-side reader → assert `proposals.length > 0`. **Without `gcTime: Infinity` this test REDS.** *This is
  the assertion the "open both panels in one session" DoD test cannot make.*
- **REGRESSION: `PolishPanel.test.tsx` stays GREEN** — but ⚠ **it needs the `QueryClientProvider` wrap** (F41);
  that wrap is the **only** permitted edit to it. **It is NOT the gate** — the hook test is.

**DoD evidence:** `frontend: <N> passed`; the characterization file green on the OLD impl (paste that run too)
**and** on the new one; the `gcTime` gc-survival test named.

---

### `W1-11` — the `quality-heal` PANEL: the three stale guards, rendered · register

> **dependsOn:** `W1-09`, `W1-10`, `W1-01` · **kind:** FE · **Enum `N+2` → `N+3`.**

**Files**

0. 🔴 **NEW `frontend/src/features/studio/panels/ChapterPicker.tsx` — EXTRACT, do not copy-paste**
   (§2 QC-10 / `Q-31-QC10-CHAPTER-PICKER-CONVENTION`). Lift `QualityCriticPanel.tsx:20,33-70` **verbatim**:
   `const CHAPTER_PICKER_LIMIT = 500`, the `useQuery(['studio', <testIdPrefix>, 'chapters', bookId], () => booksApi.listChapters(token, bookId, { sort: 'sort_order', limit: CHAPTER_PICKER_LIMIT }), { enabled: !!token })`,
   the `<select>` (option label `c.title || c.original_filename || '#'+c.sort_order`), and the **truncation
   notice** (`typeof data.total === 'number' && data.total > items.length` → `t('quality.chaptersTruncated', …)`).
   Props `{ bookId, value, onChange, testIdPrefix }`; test-ids stay **parameterised**
   (`${testIdPrefix}-chapter-picker`, `${testIdPrefix}-chapters-truncated`) so the existing assertion
   `quality-critic-chapter-picker` (`QualityCriticPanel.test.tsx:81`) **keeps passing unchanged**. Reuse the
   **same** i18n keys (`quality.pickChapter`, `quality.chaptersTruncated`) — one name, one concept.
   ⚠ **`limit > 100` falls back to 20** in `parseLimitOffset` — **reuse `CHAPTER_PICKER_LIMIT`, do not invent a
   bigger number.**
   🔴 **BUILD THE HOIST DEFAULT INTO THE SHARED PICKER — and fix the spec's factual slip.** QC-10 claims the
   shape "defaults to the manuscript hoist's active chapter"; **`QualityCriticPanel.tsx:31` inits `useState('')`**
   and renders the `quality-critic-no-chapter` hint. Put the default **in ChapterPicker** (not in quality-heal
   alone — that is exactly the "two conventions" AN-8 forbids):
   `const busChapterId = useStudioBusSelector((s) => s.activeChapterId)` (`host/types.ts:36`) and **SEED ONCE** —
   when `value === ''` **and** the user has not yet picked (a `pickedRef` set in `onChange`) **and**
   `busChapterId` is in the loaded `items`, call `onChange(busChapterId)`. **After an explicit user pick the
   panel STOPS following the bus** (a picker that yanks itself every time the editor scrolls to another chapter
   is a bug, not a default). No bus chapter ⇒ today's empty state + `quality.pickChapterHint`.
   Then `QualityCriticPanel.tsx` becomes
   `<ChapterPicker bookId={host.bookId} value={chapterId} onChange={setChapterId} testIdPrefix="quality-critic" />`
   and `QualityHealPanel` uses the **identical** line with `testIdPrefix="quality-heal"`. **Invent nothing
   else — no per-panel picker variants.**
   **Tests** — NEW `panels/__tests__/ChapterPicker.test.tsx`: (a) seeds from bus `activeChapterId` when it is in
   the list; (b) **an explicit user selection is NOT overridden by a later bus change**; (c) the truncation
   notice renders when `total > items.length` and is absent otherwise; (d) no bus chapter ⇒ empty value.

1. **NEW `frontend/src/features/studio/panels/QualityHealPanel.tsx`** — the wrapper, consuming
   `<ChapterPicker testIdPrefix="quality-heal" />`.
   ```tsx
   export function QualityHealPanel(props: IDockviewPanelProps) {
     useStudioPanel('quality-heal', props.api);
     const { t } = useTranslation('studio');
     const host = useStudioHost();
     const { accessToken } = useAuth();
     const work = useQualityWork(host.bookId, accessToken);
     const unit = useManuscriptUnit();                    // may be null (no editor mounted) — guard
     const [modelRef, setModelRef] = useState('');
     // QC-10 — default to the hoist's active chapter, but the panel's OWN picker owns the choice.
     const [chapterId, setChapterId] = useState(unit?.state.chapterId ?? '');
     const chaptersQ = useQuery({ queryKey: ['studio', 'chapters', host.bookId], /* the SHARED key */ ... });
     const [applyResult, setApplyResult] = useState<ApplyHealedResult | null>(null);

     if (work.kind !== 'ready') return <QualityWorkGate state={work} testIdPrefix="quality-heal" />;

     const onApply = (healedText: string, draftVersion: number | null) => {
       if (!unit) { setApplyResult({ kind: 'no-editor' }); return; }
       const r = unit.applyHealedDocument({ text: healedText, chapterId, expectedDraftVersion: draftVersion });
       setApplyResult(r);
       if (r.kind === 'applied') toast.success(t('quality.healApplied', { defaultValue: 'Applied — press ⌘S to save.' }));
     };
     // ... render the picker row, the ModelPicker, <PolishPanel onApply={…}/>, and the StaleBanner ...
   }
   ```
   ⚠ **`PolishPanel`'s `onApply` signature is `(healedText: string) => void`** — it does not pass
   `draftVersion`. **Widen it additively:** `onApply: (healedText: string, draftVersion: number | null) => void`
   and change the call site to `onApply(p.healedText, p.draftVersion)`. The legacy caller
   (`CompositionPanel.tsx:861` → `handleApplyPolish`) **ignores the second arg** and keeps compiling — TS is
   contravariant-safe here. **This is the read that F-Q6 says nothing has ever made.**
   ⚠ **`PolishPanel` must be `key={chapterId}`-mounted** in the studio too — the same reason the legacy page
   does it (`CompositionPanel.tsx:852-859`: *"stale Ch-A edits would Apply onto Ch-B (corruption)"*).
   The stale guards are the safety net; the key is the first line of defence.

2. **The stale banner — mock state ⑧. Build ALL FOUR, each with its own message, each DISABLING Apply.**
   ```tsx
   function StaleBanner({ r, proposalChapterTitle, editorChapterTitle, onRerun, t }: {...}) {
     if (!r || r.kind === 'applied') return null;
     const msg =
       r.kind === 'no-editor'
         ? t('quality.healNoEditor', { defaultValue: 'Open the editor to apply.' })
       : r.reason === 'chapter'
         ? t('quality.healStaleChapter', { defaultValue: 'These fixes were proposed for {{a}}; the editor is on {{b}}. Open {{a}}, or re-run Polish.', a: proposalChapterTitle, b: editorChapterTitle })
       : r.reason === 'version'
         ? t('quality.healStaleVersion', { defaultValue: 'The chapter changed since Polish ran — these fixes are against an older draft and would revert your edits.' })
         : t('quality.healStaleDirty', { defaultValue: 'You have unsaved edits. They are not in the text Polish analysed — save or revert, then re-run Polish.' });
     return (
       <div data-testid={`quality-heal-stale-${r.kind === 'no-editor' ? 'no-editor' : r.reason}`}
            className="rounded bg-amber-50 p-2 text-[11px] text-amber-800 dark:bg-amber-950 dark:text-amber-300">
         {msg}
         {r.kind === 'stale' && (
           <button type="button" data-testid="quality-heal-rerun" className="ml-2 underline" onClick={onRerun}>
             {t('quality.healRerun', { defaultValue: 'Re-run Polish' })}
           </button>
         )}
       </div>
     );
   }
   ```
   🔴 **Apply must be DISABLED, not merely-fails — AND THE RENDER AND THE CLICK MUST USE THE SAME FUNCTION.**
   Compute the pre-click state with **`evaluateHealGuard(...)`** (the pure fn from `W1-09`), fed from the live
   unit state + the hook's **pinned** `proposalChapterId` / `proposalDraftVersion` — **never** from the live
   prop. Pass it down as ONE additive optional prop so `PolishPanel` stays legacy-compatible (QC-1):
   `applyGuard?: { guard: HealGuard; onRerun: () => void; onSaveAndRerun: () => void; onOpenProposalChapter: () => void }`.
   When `applyGuard.guard.kind !== 'ok'`: render the banner **AND** set Apply `disabled`. **Legacy passes no
   `applyGuard` ⇒ zero behavior change.**
   **The hoist re-checks at CLICK time anyway** (`unit.applyHealedDocument(...)` runs the same guard against
   `stateRef.current`) — *the state can change between render and click, so the guard is ENFORCED, not merely
   displayed.* **A button that is clickable and always fails is worse than one disabled with a reason** — and
   it is the difference between "rendered" and "guarded".
   **Per-reason ACTION, not just copy:** chapter → *[Open that chapter]* (`host.focusManuscriptUnit(proposalChapterId)`);
   dirty → *[Save & re-run Polish]* (`unit.save()` then `run()`); version → *[Re-run Polish]*; no-editor →
   *"Open the editor to apply."*

3. **GG-8 registration:** `catalog.ts` (`category: 'quality'`, `guideBodyKey`), `en/studio.json` +
   17 locales, `frontend_tools.py` enum + description clause
   (`'quality-heal' = run Polish on a chapter and accept/reject each proposed fix before it touches your prose;`),
   **regenerate** `contracts/frontend-tools.contract.json`, **`QualityHubPanel` `CARDS` → 6** (`✨`).

**Tests** — NEW `frontend/src/features/studio/panels/__tests__/QualityHealPanel.test.tsx`:
- the three Work-gate states.
- 🔴 **three stale tests, one per reason** — `chapter mismatch`, `version mismatch`, `dirty` — each asserts
  (a) the right `data-testid` banner renders, (b) **Apply is disabled**, and (c) `applyHealedDocument`
  either was not called or returned `stale` and **the document is unchanged**.
- `no live editor → the no-editor banner`.
- `a successful apply toasts "press ⌘S to save" and marks the hoist dirty`.
- `Run Polish is disabled with "Pick a model first" until a model is chosen`.
- `an empty proposal set renders "No issues found — the prose is clean." (not an error)`.
- **DOCK-7:** `the ModelPicker's empty state renders AddModelCta and clicking it does NOT unmount the panel`
  (unit-level; the real proof is the live browser smoke in W1-17).
- the 4 drift-locks: **+1**.

**DoD evidence:** `frontend: <N> passed`; the three stale tests named; enum `N+2 → N+3`, three-way equality green.

---

### `W1-12` — the critic link: `quality-critic` reads the proposals (closes `D-QUALITY-CRITIC-HEAL-LINK`)

> **dependsOn:** `W1-10`, `W1-11` · **kind:** FE · **Tiny slice, and it is the whole point of bug ④.**

**File:** `frontend/src/features/studio/panels/QualityCriticPanel.tsx` (line 80).

```tsx
// D-QUALITY-CRITIC-HEAL-LINK — the missing `proposals` prop. QualityReportSection defaults it to [], so
// _hasProposedFix() could NEVER return true and the `violation-has-fix` badge was unreachable dead code in
// the Studio (F-Q1/F21). quality-heal and quality-critic are SIBLING DOCK PANELS with no common ancestor:
// there is no prop to drill, so they share the react-query cache (QC-8). A cache MISS ⇒ [] ⇒ no badge —
// a FALSE badge is impossible by construction.
const healed = useQuery<PolishCacheEntry>({
  queryKey: polishKey(work.projectId, chapterId),
  enabled: false, staleTime: Infinity, gcTime: Infinity,
});
// ...
<QualityReportSection
  projectId={work.projectId} chapterId={chapterId} token={accessToken} modelRef={modelRef}
  proposals={healed.data?.proposals ?? []}
/>
```
⚠ `polishKey` + `PolishCacheEntry` are imported from
`@/features/composition/hooks/usePolishProposals` — **one name, one concept.** Do not re-declare the key
string here (a duplicated key that drifts is the `css-var-duplicated-across-two-consumers-drifts` class).

**Tests** — extend `QualityCriticPanel.test.tsx`:
- 🔴 **`the violation-has-fix badge APPEARS after quality-heal ran for the SAME chapter`** — seed the query
  cache at `polishKey(pid, 'ch-88')` with a proposal whose `before` overlaps a critic violation's `span`;
  render `quality-critic` on `ch-88`; assert `[data-testid="violation-has-fix"]` is visible.
  **This single assertion is `D-QUALITY-CRITIC-HEAL-LINK` closed, proven by EFFECT.**
- 🔴 **`…and does NOT appear for a DIFFERENT chapter`** — same cache, render on `ch-89` ⇒ no badge.
- `with an empty cache the report renders normally, with no badge`.

**DoD evidence:** the two badge tests named + green. Plus the **live browser** proof in W1-17
(run Polish in `quality-heal` → open `quality-critic` on the same chapter → the badge is visible).

---

## M4 — THE CORRECTION FLYWHEEL (closes `G-CORRECTION-FLYWHEEL`) · enum `N+3` → `N+4`

> **ORDER IS NON-NEGOTIABLE: the denominator fix (`W1-13`) ships FIRST, ALONE, with its own tests.**
> Shipping `quality-corrections` on top of today's query is **shipping a lie with a chart on it.**
> `/review-impl` runs on this milestone (a new cross-service write path + a DDL column).

### `W1-13` — 🔴 BE-9c + BE-9c′: the denominator. **Read F10/F11/F12 before typing.**

> **dependsOn:** — · **kind:** BE

**THE TRAP, STATED SO YOU CANNOT WALK INTO IT.** You will be tempted to write *"allowlist the draft ops
**and the cowrite ops**."* **There is no such thing as a cowrite op.** `mode` and `operation` are
**orthogonal**: `mode` is a **per-request** `Literal["cowrite","auto"]` on the *same* op
(`engine.py:98-99`). `draft_scene` + `mode='cowrite'` **IS** the panel's *Stream* column and is **already in
the allowlist**. The only *exclusively*-cowrite operations are `rewrite`/`expand`/`describe` — i.e.
**`SelectionEditBody`**, the exact jobs the existing `/review-impl` exclusion removes. **An agent told to
"enumerate the cowrite ops from engine.py" greps, finds that `Literal`, adds all three, and SILENTLY REVERTS
the documented fix — corrupting the very Stream column the panel charts.**

⇒ **`NOT selection_edit` STAYS. It is ADDED to, never replaced.** The two predicates are **defense in depth**:
the allowlist filters what the *server* writes today; the `selection_edit` flag survives a client that writes
an operation the allowlist happens to admit.

🔴 **AND THE ALLOWLIST IS FOUR OPS, NOT THREE — `adapt_scene` IS IN** (§2 9c-OPS / `BE-31-9c-DENOMINATOR-ALLOWLIST`).
`ComposeView.tsx:73` posts `operation:'adapt_scene'` on the **same `/generate` route**, and the **same capture
handlers fire on it** (`correct()` at `:107`; `cowriteCorrect()` at `:137`). With a 3-op allowlist the
correction ROWS still get written but their JOB rows are filtered out of the FROM side of the join ⇒ **both
numerator and denominator drop them** ⇒ **a derivative Work drafted via Adapt-from-source renders the
cold-start *"no generations"* panel for an author who drafted an entire branch**, while learning-service (fed by
the unfiltered outbox event) *has* the corrections. Same bug class, inverted.

**Files**

1. **`services/composition-service/app/db/repositories/generation_corrections.py`**
   ```python
   # The ONLY generation operations a human can CORRECT (BE-9c). ONE named constant — never a literal at
   # the call site, and never re-derived by grepping engine.py.
   #
   # correction_stats groups by j.mode over EVERY generation_job in the project, and mode='auto' is the
   # DEFAULT for almost every LLM operation composition owns: self_heal_propose, quality_report,
   # promise_coverage, decompose_preview, plan_pipeline, plan_forge_propose/_refine/plan_pass. NONE of
   # them is a draft a human accepts/edits/rejects. Every PlanForge pass and every Polish run inflated
   # the `auto` denominator, so accept_rate = (generations - corrected)/generations reported an author
   # DELIGHTED WITH EVERYTHING — a reassuring, false number, on the panel whose entire purpose is to BE
   # the quality signal.
   #
   # ⚠ `mode` and `operation` are ORTHOGONAL. draft_scene runs with mode='cowrite' (the Stream column)
   #   AND mode='auto' (Diverge). It covers BOTH columns. There is no such thing as "a cowrite op": the
   #   only exclusively-cowrite ops are rewrite/expand/describe = SELECTION EDITS, which the
   #   `NOT selection_edit` predicate below already removes and which MUST NOT be added here.
   #
   # ⚠ `adapt_scene` IS IN (BE-31-9c): ComposeView.tsx:73 posts it on the SAME /generate route and the
   #   SAME correction handlers fire on it (ComposeView.tsx:107/:137). Excluding it filters a derivative
   #   Work's ENTIRE drafting history out of the join — the panel would show cold-start "no generations"
   #   to an author who drafted a whole branch.
   # ⚠ `continue` is deliberately OUT: useInlineGhost.ts:60 sends it and the hook captures NO correction
   #   anywhere — an uncaptured ghost in the denominator is a false accept.
   CORRECTABLE_OPERATIONS: tuple[str, ...] = (
       "draft_scene", "draft_chapter", "stitch_chapter", "adapt_scene",
   )
   ```
   🔴 **THE ANTI-TRAP TRIPWIRE (a pure unit test — mandatory, not optional).** A behavior test alone stays
   green while the allowlist lies. `tests/unit/test_correctable_operations.py`:
   ```python
   assert set(CORRECTABLE_OPERATIONS) == {"draft_scene", "draft_chapter", "stitch_chapter", "adapt_scene"}
   assert not ({"rewrite", "expand", "describe"} & set(CORRECTABLE_OPERATIONS)), (
       "F-Q3a: mode and operation are orthogonal — rewrite/expand/describe are SELECTION EDITS, never "
       "draft ops. See spec 31 F-Q3a."
   )
   # Make the `continue`/`adapt_scene` in/out call VISIBLE, not accidental: any op added to a draft route
   # forces a conscious denominator decision here.
   assert (set(DRAFT_OPERATIONS) | set(CHAPTER_OPERATIONS)) - set(CORRECTABLE_OPERATIONS) == {"continue"}
   ```
   *A future agent enumerating "the cowrite ops from engine.py" reds this test **with the explanation
   attached.***
   In `correction_stats`, **ADD** one predicate and **KEEP** the existing one:
   ```python
   rows = await self._pool.fetch(
       """
       ...
       WHERE j.project_id = $1
         -- BE-9c: only DRAFT generations can be corrected. Plan passes, quality reports, coverage
         -- runs and Polish proposals are not drafts — they inflate the denominator and fake a high
         -- accept_rate. The repo already contained this bug, patched narrowly ONE ROW AT A TIME (the
         -- selection_edit flag below); NINE more operations walked through the hole afterwards.
         -- Fixed at the ROOT: an allowlist of the correctable ops, not a flag per offender.
         AND j.operation = ANY($2::text[])
         -- /review-impl (KEPT — ADDED TO, NOT REPLACED): T3.2 selection edits run mode='cowrite' but
         -- are NOT part of the draft flywheel. `operation` is an open str on both draft bodies until
         -- BE-9c' closes it, so the allowlist is a FILTER, not a guarantee. Two predicates = defense
         -- in depth.
         AND NOT coalesce((j.input->>'selection_edit')::boolean, false)
       GROUP BY j.mode
       """,
       project_id, list(CORRECTABLE_OPERATIONS),
   )
   ```
   ⚠ `$2::text[]` + `list(...)` — asyncpg binds a Python `list` to a Postgres array; a `tuple` will not bind.

2. 🔴 **BE-9c′ — AND THE CLOSED SET IS *NOT* ONE VALUE. `Literal["draft_scene"]` WOULD 422 TWO SHIPPED FE
   FEATURES** (§2 9c′-LITERAL / F32). The spec's own pre-flight ("check for a caller posting a non-standard
   operation **before** narrowing") is a **POSITIVE HIT**: `useInlineGhost.ts:60` posts `operation:'continue'`
   and `ComposeView.tsx:73` posts `operation:'adapt_scene'` — **both to `/works/{pid}/generate` = `GenerateBody`.**
   The correct closed set is **the drafter's own registry, partitioned by route.**

   **(a) `services/composition-service/app/engine/cowrite.py`** — after `_OPERATION_INSTRUCTIONS` (ends `:48`),
   the named constants (one home, one name — **no literals at call sites**):
   ```python
   DRAFT_OPERATIONS     = ("draft_scene", "continue", "adapt_scene")   # /works/{pid}/generate
   CHAPTER_OPERATIONS   = ("draft_chapter",)                            # /works/{pid}/chapters/{cid}/generate
   SELECTION_OPERATIONS = ("rewrite", "expand", "describe")             # /selection-edit (already Literal)
   ```
   **(b) `app/routers/engine.py:98`** → `operation: Literal["draft_scene", "continue", "adapt_scene"] = "draft_scene"`
   **(c) `app/routers/engine.py:141`** → `operation: Literal["draft_chapter"] = "draft_chapter"`
   *(Literal args must be literal — the tuples in (a) are the **drift-assertion target**, not the type source.)*
   **(d) 🔴 THE THIRD OPEN SURFACE THE SPEC NEVER NAMED (F33): `app/mcp/server.py:1356`,
   `_GenerateArgs.operation: str | None = None`.** It feeds these exact bodies at the **confirm-execute** seam
   (`actions.py:453` GenerateBody / `:462` GenerateChapterBody). Close it to the union:
   `operation: Literal["draft_scene","continue","adapt_scene","draft_chapter"] | None = None`, **and fix the
   comment at `:1351-1355`** — it already **CLAIMS** *"Literals mirror the engine's GenerateBody"*, which is
   **false for exactly this field.** *Leaving it open means a bad op survives propose **AND the user's PAID
   confirm**, then dies as a 400 at execute — the repo's paid-action-defect shape.*

   ⚠ **This is an API-CONTRACT NARROWING** — a previously-accepted body now **422s**. **BREAKING-CHANGE SURFACE
   = EMPTY IN PRACTICE, verified:** 10 eval scripts post `draft_scene`; `api.ts:406` defaults `draft_scene`;
   `api.ts:448` chapter defaults `draft_chapter`; `authoring_run_service.py:337`
   (`params.get("operation") or "draft_chapter"`) already wraps construction in a `try/except ValidationError`
   → a clean `DraftOutcome(ok=False, "invalid seam params")` — **no change needed there**; the two tests
   carrying `operation="x"` (`test_engine_router.py:371,381`) put it in a **FAKE DB row**, not a request body,
   and stay green. **The only client that 422s after this lands is one posting an op the drafter never
   recognized — which today silently falls back to the generic *"Write the next passage of the scene."*
   (`cowrite.py:101`), i.e. exactly the bug.** Grep to confirm before committing:
   ```bash
   grep -rn "operation:" frontend/src/features/composition | grep -v test
   grep -rn "\"operation\"\|'operation'" services/composition-service/app --include=*.py | grep -v test
   ```
   *(`stitch_chapter` is written **server-side** at `engine.py:1279,1307`, not from a body — it needs no `Literal`.)*

**Tests**

- **EXTEND** `services/composition-service/tests/integration/db/test_repositories.py` (real PG; the
  `xdist_group("pg")` mark applies):
  - 🔴 **`test_correction_stats_ignores_non_draft_operations`** — seed 2 completed `draft_scene` `auto` jobs
    with **1** correction, **plus** completed `auto` jobs for `plan_pass`, `quality_report`,
    `self_heal_propose`, `promise_coverage`, `plan_pipeline`. Assert `auto.generations == 2` and
    `auto.accept_rate == 0.5`. **Then assert the SAME numbers with the plan jobs removed** — i.e. a
    `plan_pass` job **cannot move `accept_rate`**. *THE test of the slice.*
  - 🔴 **`test_correction_stats_still_excludes_selection_edits_after_the_allowlist`** — a `rewrite` job with
    `input={"selection_edit": True}` **still** does not count. *(The `NOT selection_edit` predicate survived.
    This test is the tripwire on F-Q3a: an agent that "enumerates the cowrite ops" and adds
    rewrite/expand/describe to `CORRECTABLE_OPERATIONS` reds HERE.)*
  - 🔴 **`test_correction_stats_draft_scene_cowrite_lands_in_the_stream_column`** — a `draft_scene` job with
    `mode='cowrite'` **DOES** count toward `cowrite.generations`. *(The allowlist did not amputate the Stream
    column.)*
  - `test_correction_stats_counts_stitch_chapter_and_draft_chapter` — both allowlisted ops count.
  - 🔴 **`test_correction_stats_includes_adapt_scene`** — a completed `adapt_scene` **cowrite** job + a `reject`
    correction ⇒ `cowrite.generations == 1`, `reject_rate == 1.0`. *(The Adapt-from-source author is not
    invisible.)*
  - 🔴 **`test_correction_stats_excludes_inline_continue`** — a completed `continue` cowrite job (no correction;
    `useInlineGhost` never captures one) ⇒ it does **NOT** drag `cowrite.accept_rate`.
  - **REGRESSION:** the 5 existing `test_correction_stats_*` tests (`:2012-2100`) **stay green** — they seed
    `operation="draft_scene"` (and `"rewrite"` for the selection-edit case), so they are already
    allowlist-compatible (F13). **Verify; do not assume.**
- **NEW** `services/composition-service/tests/unit/test_engine_operation_literal.py` (mirror the existing
  `test_selection_edit_rejects_unknown_operation` at `:244-249`):
  - `test_generate_rejects_unknown_operation` — POST `/works/{pid}/generate` with `operation:"summarize"` ⇒ **422**.
  - 🔴 **`test_generate_accepts_continue_and_adapt_scene`** — **both 200.** *THE regression guard for the two
    live callers (F32). Without this test, `Literal["draft_scene"]` ships and the inline ghost + Adapt-from-source
    start 422-ing in production.*
  - `test_chapter_generate_rejects_unknown_operation` — `operation:"draft_scene"` on the **CHAPTER** route ⇒ 422.
  - `test_the_defaults_still_validate` — omitting `operation` yields `draft_scene` / `draft_chapter`.
  - 🔴 **drift guard (the LOOM-39 lesson made mechanical):**
    `set(get_args(GenerateBody.model_fields["operation"].annotation)) == set(DRAFT_OPERATIONS)` **and**
    `set(DRAFT_OPERATIONS)|set(CHAPTER_OPERATIONS)|set(SELECTION_OPERATIONS) <= set(_OPERATION_INSTRUCTIONS)`.
  - `test_mcp_generate_args_operation_is_closed` — `_GenerateArgs.operation` rejects `"summarize"` (F33).

**DoD evidence:** `composition-service: <N> passed`, with `test_correction_stats_ignores_non_draft_operations`,
`…still_excludes_selection_edits…` and `…draft_scene_cowrite_lands_in_the_stream_column` **all named**.
**Commit this slice ALONE.** It is independently revertable and it is the honesty of every number the panel
will render.

---

### `W1-14` — BE-9a: thread the generation job to the unit (the DDL + the seam)

> **dependsOn:** `W1-13` · **kind:** BE
> **Plan-30's BE-9 says "No schema change". It is WRONG (F4/F5). This slice is why the wave is L.**

**Files**

1. **`app/db/migrate.py`** — migration **M-A** (§6), verbatim, including the *never backfill a guess* comment.

2. **`app/db/models.py`** — `AuthoringRunUnit` gains `job_id: UUID | None = None`.

3. **`app/db/repositories/authoring_runs.py`** (`AuthoringRunUnitsRepo`, class at `:286`)
   - Add `u.job_id` to `_UNIT_SELECT` (`:39`).
   - `transition_unit` (`:388`) gains `job_id: UUID | None = None` and appends `job_id = $n` to `sets` when it
     is not None (**the same conditional-set pattern as `post_revision_id`**).
   - `mark_drafted` (`:329`) gains a keyword `job_id: UUID | None = None` and passes it through:
     `job_id = COALESCE($n, job_id)` — **COALESCE, not a bare assignment**: a late/retried mark must never
     null out an id that already landed.
   - 🔴 **`upsert_pending`'s `ON CONFLICT DO UPDATE` (`:316-320`) must ADD `job_id = NULL,`** alongside the
     existing `post_revision_id = NULL`. **A resumed / re-run unit must NOT inherit the previous attempt's
     `job_id`** — that would name **the wrong generation** in a correction, which is the same poisoning the
     never-backfill rule exists to prevent, arriving through the back door.

4. **`app/services/authoring_run_service.py`**
   - `DraftOutcome` gains `job_id: UUID | None = None`.
     ```python
     @dataclass
     class DraftOutcome:
         """What the drafting seam reports back per chapter unit."""
         ok: bool
         cost_usd: Decimal = Decimal("0")
         error: str | None = None
         # BE-9a — the generation_job this draft came from. The seam ALREADY reads it (payload["job_id"],
         # :377) to fetch the cost and then THROWS THE ID AWAY. generation_correction.job_id is NOT NULL,
         # so without carrying it there is literally nothing to attach the human's rejection to.
         job_id: UUID | None = None
     ```
   - `EngineDraftingSeam.draft_chapter` — **return the id it already has** on BOTH terminal paths:
     - the `status == "completed"` branch (`:385-391`): 🔴 **only set `job_id` when the job LOADED *and*
       `job.project_id == project_id`** — i.e. **inside the existing in-project guard at `:388`.** **NEVER
       return an unverified `job_id_raw`:** `generation_corrections.create` verifies job-in-project
       (`D-COMP-M2-XREF-OWNERSHIP`), so an out-of-partition id would only **strand BE-9b** (a capture that can
       never be written). *(`worker-loaded-id-needs-parent-scoping`.)*
     - `_poll_job` (`:395-411`): thread `job_id` through and return it on the `completed` branch (`:408`).
       ⚠ **The failure branches (`vanished` / `failed` / `cancelled` / `timed out`) return `job_id=None`** —
       a failed generation is not a draft anyone can correct.
     - Update the `DraftingSeam` **Protocol docstring** (`:205`): the seam reports the `generation_job` it
       drafted through (**None = the engine ran inline / no job**).
   - The driver (`run_driver`, ~`:1186`): `await self._units.mark_drafted(run_id, run.current_unit,
     post_revision_id=post_rev, cost_usd=cost, job_id=outcome.job_id, run_statuses=…, run_driver_id=…)`.

5. **`app/routers/authoring_runs.py`** — `_serialize_unit` (`:290`) adds `"job_id": str(unit.job_id) if unit.job_id else None`.

6. **`frontend/src/features/composition/authoringRuns/types.ts`** — the unit type gains `job_id: string | null`.

7. **`frontend/src/features/studio/panels/agentMode/DiffReviewPanel.tsx`** — the honesty note (spec DoD:
   *"a unit with `job_id IS NULL` records nothing and the run report SAYS SO"*). Next to the Accept/Reject
   buttons:
   ```tsx
   {unit.job_id === null && unit.status === 'drafted' && (
     <span data-testid="agent-mode-no-feedback-capture" className="text-[10px] text-neutral-400">
       {t('authoringRun.diff.noFeedbackCapture', {
         defaultValue: 'Drafted before feedback capture existed — your accept/reject is not recorded as a learning signal.',
       })}
     </span>
   )}
   ```
   **Never fabricate a job id. Never pretend the signal was captured.**

**Tests**

- `tests/unit/test_authoring_runs_service.py` (extend — it injects a fake `DraftingSeam`):
  - `test_draft_outcome_job_id_is_persisted_by_the_driver` — a fake seam returns
    `DraftOutcome(ok=True, job_id=J)`; assert `mark_drafted` was called with `job_id=J`.
  - `test_a_failed_outcome_carries_no_job_id`.
  - `test_mark_drafted_coalesces_and_never_nulls_an_existing_job_id`.
- `tests/unit/test_engine_drafting_seam.py` (NEW or extend): the `completed` payload path and the `_poll_job`
  path both **return** the job id (today both discard it); 🔴 **and a job whose `project_id != the run's
  project` yields `job_id=None`** (never an unverified id).
- `tests/integration/db/test_migrate.py`: `authoring_run_units.job_id` exists and is **nullable**.
- 🔴 `tests/integration/db/test_repositories.py`: **`upsert_pending` on an existing drafted row RESETS `job_id`
  to NULL** (the re-run must not inherit the previous attempt's generation).
- `tests/unit/test_authoring_runs_router.py`: `_serialize_unit` emits `job_id` (and `null`, not `"None"`).
- 🔴 **`unit_report` STATES THE GAP** (`authoring_run_service.py:878-893`): add
  `"job_id": str(u.job_id) if u and u.job_id else None` to the row dict, **alongside the identical
  `critic_verdict` None-means-absent precedent.** *A unit with no job is VISIBLE, not silently zero.*

🔴 **THE THREE MECHANICAL BACKFILL GUARDS** (`Q-31-JOBID-BACKFILL-TEMPTATION`) — *a comment is self-report; this
repo's own rule is "an item is DONE only when a test asserts its effect."* Add to composition-service's
migration tests:
- **`test_no_job_id_backfill_in_migrations`** — read `migrate.py` and assert **ZERO** regex matches for
  `UPDATE\s+authoring_run_units\s+SET[^;]*job_id` (case-insensitive). **A future agent's "helpful" backfill then
  cannot land silently — it REDS the suite.**
- **`test_job_id_ddl_carries_never_backfill_warning`** — assert the literal string **`NEVER BACKFILL A GUESS`**
  appears within the `job_id` ALTER block, **so a comment-stripping edit reds too.**
- **`test_reject_unit_with_null_job_id_records_no_correction`** — a `drafted` unit with `job_id IS NULL` ⇒
  `reject_unit` writes **NO** `generation_correction` row, emits **NO** `GENERATION_CORRECTED` event, and the
  report row shows `job_id: None`. *(BE-9b's "skip + report, never fabricate", asserted as behaviour.)*

**Builder rule, one line:** `job_id` is nullable, written **ONLY** by the driver from `DraftOutcome.job_id` at
`mark_drafted`, and is **NEVER** derived, inferred, or backfilled from any other column.

**DoD evidence:** `composition-service: <N> passed`, the 4 seam/driver tests **and the 3 backfill guards** named.

---

### `W1-15` — BE-9b: the CAPTURE SEAM (`accept_unit` / `reject_unit`) + MCP `composition_record_correction`

> **dependsOn:** `W1-14` · **kind:** BE
> **This is the load-bearing half of `G-CORRECTION-FLYWHEEL` — not the panel.**

**🔴 THE FACT THAT SHAPES THIS SLICE (F6): `AuthoringRun` has NO `project_id`** — only `book_id`. The
project is resolved *inside* the drafting seam. `GenerationCorrectionsRepo.create(project_id, job_id, …)`
needs one. **Resolve it from the JOB ROW** (`GenerationJobsRepo.get(job_id).project_id`) — the job is the
authority for its own project, and re-deriving the Work from the book would be a second source of truth.
*(Equivalently `WorksRepo.resolve_by_book(run.book_id)` — the precedent at `authoring_run_service.py:600` —
and then let the repo's in-txn "job in THIS project" check (`generation_corrections.py:88-95`) raise
`ReferenceViolationError` on a foreign job. **Either way: never trust a bare-id `jobs.get()` for scope.**)*

---

#### 🔴 THE FOUR THINGS THE ADJUDICATION CHANGED IN THIS SLICE — read before typing

1. **EDIT-DETECTION IS REVISION-TEXT vs REVISION-TEXT** (§2 ACCEPT-EDIT / F37). **NOT `job.result["text"]` vs
   the live chapter** — the round-trip is **not identity** (ATX `### ` scene markers are stripped by
   `text_to_tiptap_doc`/`_text`), so that compare reports **a phantom diff on every heading line of an
   untouched chapter** ⇒ **a false `kind='edit'` on every accept-as-is**, *bypassing* the `EDIT_NO_CHANGE`
   guard because `changed_blocks > 0`. **That is the self-reinforcement H2 forbids.**
2. **`revert_all` MUST CAPTURE** (§2 UNVERIFIED-1 / F36) — it **bypasses `reject_unit`**, so a capture written
   only in accept/reject records **nothing** on a Revert-All. The consumer copes with the burst (verified);
   **no throttle, no batch, no debounce.**
3. **NO SILENT SUCCESS** — the accept/reject **response** must surface the capture outcome
   (`Q-31-FIREFORGET-VS-SAME-TX` (5)).
4. **EXTRACT, DO NOT MIRROR** (BE-9e) — `engine.py:1712-1790`'s body becomes
   `app/services/correction_capture.py::capture_correction(...)`, called by **all three** consumers. *A mirrored
   copy is a guaranteed drift.*

**TRANSACTION TOPOLOGY (locked — `Q-31-FIREFORGET-VS-SAME-TX`):** **TXN-1 = the FSM transition** (a bare
autocommit UPDATE, `authoring_runs.py:427-429`). **TXN-2 = the correction INSERT + its outbox row, atomic with
each other, opened AFTER TXN-1 commits.** `GenerationCorrectionsRepo.create` **self-acquires** and opens its
**own** `conn.transaction()` (`generation_corrections.py:88-89, 137`) — **it takes no `conn=` param and must
not gain one.** *M4's DoD phrase "the outbox emits GENERATION_CORRECTED **in the same transaction**" means the
same transaction as **the correction row INSERT** — which is already true and already enforced. It does **NOT**
mean the accept/reject transaction.* **The outbox law is NOT violated by fire-and-forget:** if `outbox.emit`
raises, `conn.transaction()` **rolls back** and the correction row vanishes with it (no capture without an
event, no event without a capture); the caller then catches **a failed, already-rolled-back atomic unit** —
that is catching a *failed unit*, **not swallowing an *emit***. Both invariants hold. *(And `reject_unit` makes
a cross-service HTTP `restore` call mid-sequence — a wrapping DB txn is **impossible by design**.)*

**Files — `app/services/authoring_run_service.py`**

1. **Two new seams** (so the capture is unit-testable and the service stays httpx-free in tests — the exact
   shape `DraftingSeam` / `RevisionCapture` / `CriticSeam` already use):
   ```python
   class CorrectionSink(Protocol):
       """Records a human-gate correction on the generation a run unit produced.
       BEST-EFFORT TELEMETRY: it may raise; the caller SWALLOWS. The legacy FE's own rule
       (CandidatesView.tsx:9): 'Correction capture is fire-and-forget telemetry — it must never block.'
       A capture failure must NEVER fail the accept/reject the author is trying to do."""
       async def record(
           self, *, job_id: UUID, created_by: UUID, kind: str, edited_text: str | None = None,
       ) -> UUID | None: ...

   class RevisionText(Protocol):
       """🔴 The text OF A NAMED REVISION (book-service). BOTH sides of the edit-compare come through
       THIS ONE extractor, so they are in the SAME normal form (the mirror-producer rule). Comparing the
       job's raw LLM prose against the chapter's TipTap `_text` is the phantom-diff trap (F37)."""
       async def revision_text(
           self, *, book_id: UUID, chapter_id: UUID, revision_id: UUID,
       ) -> str | None: ...
   ```
   🔴 **`app/clients/book_client.py` — ADD `get_chapter_revision_text()`.** The route **EXISTS**
   (`book-service/server.go:3364-3405`: internal-token `GET /internal/books/{b}/chapters/{c}/revisions/{r}/text`
   → `text_content`, TipTap-extracted plain text) and composition's `BookClient` **already carries
   `_internal_token`** (`book_client.py:142`). **Mirror `knowledge-service/app/clients/book_client.py:602`
   verbatim.** *This is unbuilt work in composition, **NOT a blocker** — write it.*
   Real implementations (lazily defaulted in `__init__`, like `EngineCriticSeam()`). 🔴 **The sink delegates to
   the SHARED `capture_correction()` (BE-9e) — it does not re-implement the 422 rule, the opt-in-prose rule, or
   `winner_index`/`candidate_count`:**
   ```python
   class RepoCorrectionSink:
       async def record(self, *, job_id, created_by, kind, changed_blocks=None,
                        raw_before=None, raw_after=None) -> UUID | None:
           # app/services/correction_capture.py — THE ONE HOME, extracted from engine.py:1712-1790 and
           # called by the REST route, the MCP tool, AND this seam. A mirrored copy is guaranteed drift.
           from app.services.correction_capture import capture_correction
           return await capture_correction(
               job_id=job_id, created_by=created_by, kind=kind, changed_blocks=changed_blocks,
               raw_before=raw_before, raw_after=raw_after,
           )
           # capture_correction resolves the job, verifies job-in-project, applies the H2/EDIT_NO_CHANGE
           # rule, and honours work.settings["capture_correction_prose"] (engine.py:1766) for raw prose.
           # A dangling id degrades to SKIP (None), never to a 500.

   class BookRevisionText:
       async def revision_text(self, *, book_id, chapter_id, revision_id) -> str | None:
           # Same producer on BOTH sides of the compare (the mirror-producer / cross-service-normalization
           # rule). NEVER mix this with job.result["text"] — see F37.
           from app.clients.book_client import get_book_client
           return await get_book_client().get_chapter_revision_text(book_id, chapter_id, revision_id)
   ```
   ⚠ **RAW PROSE STAYS OPT-IN:** set `raw_before`/`raw_after` **only** when
   `work.settings.get("capture_correction_prose", False)` (mirror `engine.py:1766`). For a reject,
   `raw_before = <the drafted text>` only. **Structural fields (`kind`, `changed_blocks`) always.**

2. **`AuthoringRunService.__init__`** gains `corrections: CorrectionSink | None = None` and
   `chapter_text: ChapterText | None = None` (defaults → the real impls, lazily). `app/deps.py:95` needs **no
   change** (the defaults do the work) — but **add a comment there** naming the two new seams, so a reader
   of `deps.py` knows they exist.

3. **`reject_unit`** — after the guarded `transition_unit` succeeds, before computing the cascade:
   ```python
   # BE-9b — a rejection is a textbook kind='reject' correction, and today it is THROWN AWAY every
   # single time. The write rides INSIDE the FSM guard's success path — never on a lost race.
   await self._capture_correction(run, rejected, kind="reject", actor=actor)
   ```

4. **`accept_unit`** — after the guarded transition:
   ```python
   # H2 (INHERITED, NOT RE-DERIVED): accepting a draft AS-IS is NOT a correction. Only accept-AFTER-EDIT
   # is. The `accept` kind DOES NOT EXIST and must not be invented — the CHECK constraint is closed on
   # ('edit','pick_different','regenerate','reject').
   await self._capture_accept_correction(run, unit, actor=actor)
   ```

5. **The two helpers:**
   ```python
   async def _capture_correction(self, run, unit, *, kind: str, actor: UUID,
                                 edited_text: str | None = None) -> None:
       """Fire-and-forget. A capture failure LOGS and NEVER fails the review."""
       if unit.job_id is None:
           return   # pre-migration unit — record NOTHING. The Run Report says so. NEVER fabricate an id.
       try:
           await self._corrections.record(
               job_id=unit.job_id, created_by=actor, kind=kind, edited_text=edited_text,
           )
       except Exception:  # noqa: BLE001 — telemetry must never block the human's review
           logger.warning("correction capture failed for run %s unit %d",
                          run.run_id, unit.unit_index, exc_info=True)

   async def _capture_accept_correction(self, run, unit, *, actor: UUID) -> None:
       """accept-AFTER-EDIT ⇒ kind='edit'. accept-AS-IS ⇒ NOTHING (H2).

       🔴 DETECT BY REVISION-ID COMPARE, AND COMPARE REVISION TEXT TO REVISION TEXT (F37).
          The unit pinned `post_revision_id` = the revision the RUN's draft created. If the chapter's
          LATEST revision has moved, a human (or an agent) saved over it.
          ⚠ DO NOT fall back to comparing job.result["text"] against the live chapter text: the job
            result is LLM plain text (with ATX `### ` scene markers) and the chapter is TipTap `_text`
            (markers STRIPPED), so that fallback reports a PHANTOM DIFF ON EVERY ACCEPT — the exact
            "every accept records a spurious edit" failure this design exists to prevent, and it BYPASSES
            the EDIT_NO_CHANGE guard because changed_blocks > 0.
          Revision-id divergence is the TRIGGER; changed_blocks > 0 is the CONFIRMATION. BOTH required —
          a no-op autosave / whitespace-only PATCH still mints a revision (book server.go:2496), so a
          divergent revision id ALONE is not proof of an edit."""
       if unit.job_id is None:
           return   # pre-migration unit — record NOTHING, never fabricate. correction_skipped=no_job_id
       if unit.post_revision_id is None:
           return   # the POST capture is best-effort (:1165-1178) — no anchor ⇒ no honest diff.
                    # correction_skipped=no_post_revision_id
       try:
           # THE SAME RevisionCapture the driver used at :1169 to WRITE post_revision_id — same producer
           # on both sides (the mirror-producer rule).
           current_rev = await self._revisions.latest_revision_id(
               created_by=run.created_by, book_id=run.book_id, chapter_id=unit.chapter_id,
           )
           if current_rev is None or current_rev == unit.post_revision_id:
               return   # accept-AS-IS — H2: NO correction row (mirrors engine.py:1727)
           before = await self._revision_text.revision_text(
               book_id=run.book_id, chapter_id=unit.chapter_id, revision_id=unit.post_revision_id)
           after = await self._revision_text.revision_text(
               book_id=run.book_id, chapter_id=unit.chapter_id, revision_id=current_rev)
           if before is None or after is None:
               return   # never record an `edit` whose magnitude cannot be CONFIRMED.
                        # correction_skipped=revision_text_unavailable
           changed = count_changed_blocks(before, after)      # existing signature, UNCHANGED (:42)
           if changed == 0:
               return   # engine.py:1753's EDIT_NO_CHANGE, re-expressed as a SKIP (this path is
                        # fire-and-forget; it must NEVER 422 the accept). correction_skipped=no_change
           await self._corrections.record(
               job_id=unit.job_id, created_by=actor, kind="edit", changed_blocks=changed,
               raw_before=before, raw_after=after,          # the sink applies the opt-in-prose gate
           )
       except Exception:  # noqa: BLE001
           logger.warning("accept-edit capture failed for run %s unit %d",
                          run.run_id, unit.unit_index, exc_info=True)
   ```
   **DEFAULT THE PO MAY VETO:** *any* writer's divergence counts. If a self-heal apply or an agent
   `propose_edit` (not the human's keystrokes) changed the chapter between draft and accept, it **still**
   records `kind='edit'` — the signal being mined is *"the author did not take the draft as-is"*, and the
   before/after prose is honest regardless of who typed it. **Do NOT filter on
   `chapter_revisions.author_user_id`** — that adds an attribution axis the flywheel does not use.
   ⚠ **The bearer identity split is deliberate:** the book-service reads mint a service bearer for
   **`run.created_by`** (the existing headless pattern); the correction row is stamped with **`actor`** — the
   person whose taste it is. Thread `actor` in as a **keyword-only param with a default**:
   `async def accept_unit(self, run_id, unit_index, *, actor: UUID | None = None)` →
   `actor = actor or run.created_by`. **Keyword-only + default keeps every existing positional call site and
   test green** (memory: `positional-test-call-breaks-on-endpoint-param-reorder`). The router passes
   `actor=user_id`.

6. 🔴 **`revert_all` — IT *DOES* CAPTURE. THIS IS REVERSED FROM THE PRE-RECONCILE PLAN** (§2 UNVERIFIED-1 / F36).
   `revert_all` (`:960-1019`) **does NOT call `reject_unit`** — it calls `self._units.transition_unit(...)`
   **directly at `:1001`**. So a capture written only in accept/reject **captures nothing on a Revert-All**,
   *silently losing the single richest bulk-rejection signal the flywheel can get.*
   **ADD the capture inside `revert_all`'s existing per-unit loop, immediately after the successful
   `transition_unit` (inside the `if updated is not None:` branch at `:1005-1006`)** — one
   `kind="reject"` capture per reverted unit:
   ```python
   # BE-9b — a Revert-All rejects EVERY drafted unit. Each is a real per-draft taste signal and each gets
   # its own correction row. The consumer copes: learning-service reads a durable Redis Stream consumer
   # group (batched XREADGROUP, per-msg XACK, retry→DLQ, MAXLEN 10000) and does ONE
   # `INSERT … ON CONFLICT DO NOTHING` per event — no LLM, no HTTP, ZERO token spend. A burst is not
   # pressure; unconsumed events simply sit in the stream and drain at the consumer's pace.
   await self._capture_correction(run, u, kind="reject", actor=actor)   # fire-and-forget
   ```
   - **`job_id IS NULL` ⇒ skip** that unit's capture (never fabricate).
   - 🔴 **KEEP THE CAPTURES SEQUENTIAL inside the existing loop — do NOT `asyncio.gather` them.** Each
     `create()` opens its **own** `pool.acquire()` + transaction (row INSERT + outbox emit are txn-local
     together); **dozens of sequential acquisitions on an asyncpg pool is a non-issue, whereas a gather would
     burst the pool.** *This — not the consumer — is the only place the "transaction storm" phrasing has any
     bite, and sequential-in-loop already neutralizes it.*
   - Emission is **per-unit** and each outbox row gets its **own id**, so N units ⇒ **N distinct** `corrections`
     rows downstream (the ON CONFLICT key is `(origin_service, origin_event_id)`). **No collapse, no dedup hazard.**
   - **A capture failure must never abort the sweep**: `try/except → logger.warning → CONTINUE`. The restore
     already happened; the unit is already rejected.
   - ⚠ **NO throttle, NO batch, NO debounce — anywhere.** *(If the PO later wants Revert-All to record ONE
     aggregate "bulk_reject" instead of N per-unit rejects, that is a **signal-semantics** choice — it changes
     what the flywheel learns — **not** a throughput fix, and it is not needed to ship M4.)*
   **Tests:** `revert_all` over 3 drafted units emits **3** `composition.generation_corrected` outbox rows with
   `kind='reject'` (**assert on the outbox TABLE, not a spy** — the emit is txn-local); a capture that raises
   does **NOT** abort the sweep (all units still reach `rejected`, `revert_all` still returns `closed=True`);
   and in learning-service, **N events with distinct `outbox_id`s persist N `corrections` rows** (proves no
   burst-collapse).

7. **MCP `composition_record_correction`** — `app/mcp/server.py`, Tier A:
   ```python
   class _RecordCorrectionArgs(ForbidExtra):
       project_id: str
       job_id: str
       # CLOSED SET — the DB CHECK is closed on these four and `accept` DOES NOT EXIST (H2: accepting a
       # generation as-is is not a correction; recording one would train the reranker on its own pick).
       kind: Literal["edit", "pick_different", "regenerate", "reject"]
       guidance: str | None = None
       edited_text: str | None = None
       chosen_candidate_index: int | None = None

   @mcp_server.tool(
       name="composition_record_correction",
       description=(
           "Record the author's correction of an AI generation (edit / pick_different / regenerate / "
           "reject) — the human-gate signal the model learns taste from. Accepting a generation AS-IS is "
           "NOT a correction and must not be recorded. EDIT required (auto-applied; no undo — a "
           "correction is a historical fact, not a mutable row)."
       ),
       meta=require_meta("A", "book", synonyms=["record correction", "log a rejection", "capture feedback"],
                         tool_name="composition_record_correction"),
   )
   async def composition_record_correction(ctx: MCPContext, args: _RecordCorrectionArgs) -> dict:
       # _book_or_deny(EDIT) on the project → resolve the job → verify job.project_id == pid
       # (uniform_not_accessible otherwise — H13, no enumeration oracle) → call the SHARED
       # capture_correction() (BE-9e), which owns the validation (edit requires edited_text;
       # changed_blocks==0 ⇒ EDIT_NO_CHANGE; pick_different requires an in-range chosen_candidate_index)
       # → {"correction_id": str(corr.id), "_meta": {"undo_hint": None}}   # honestly None: no inverse exists
   ```
   ⚠ **Errors return MCP error payloads, not `HTTPException`s** (`server.py:1920-1924`): job not in project →
   `ReferenceViolationError` → `{"success": false, "error": …}`; `kind='edit'` with identical text → refuse with
   `EDIT_NO_CHANGE`. **An agent sending `kind="accept"` must get a schema rejection / `result.error`** (*"accept-as-is
   is not a correction — nothing is recorded"*) — **never a silent no-op and never a fabricated row.**
   ℹ️ **The 3-schema-source caveat DOES NOT apply here (F35)** — composition has no `definitions.py`; the
   decorator is the single schema source. **The real second surface is `tool-policy.ts` (F34):**
   🔴 **`services/mcp-public-gateway/src/scope/tool-policy.ts` — add
   `composition_record_correction: { tier: 'write_auto', domains: ['composition'] },`** or the tool is
   **registered, unit-green, and silently unreachable at the public edge.** **[BE-11e]**
   🔴 **Add `"composition_record_correction"` to `EXPECTED_TOOLS`** (`tests/unit/test_mcp_server.py:47-60`) —
   the registration drift guard. Write it FIRST; it reds until the tool exists.

8. 🔴 **NO SILENT SUCCESS — SURFACE THE CAPTURE OUTCOME** (`Q-31-FIREFORGET-VS-SAME-TX` (5); repo law
   `silent-success-is-a-bug`). The accept/reject payload (`routers/authoring_runs.py`'s `_serialize_unit` call
   sites **and** the MCP tool result) gains:
   ```json
   "correction": { "status": "captured" | "skipped_no_job_id" | "skipped_no_change"
                             | "skipped_no_post_revision_id" | "failed",
                   "correction_id": "<uuid|null>" }
   ```
   The FE shows **nothing** on `captured`, and a quiet *"not recorded"* note on `failed` / `skipped_*` — **the
   review itself still succeeded (200).** *Without this, a persistently-failing flywheel is undetectable from
   the product — the exact bug class this repo just shipped.* **(PO may veto and keep the response shape frozen
   — but then the log line is the only signal. Recommend keeping it.)**

**Tests**

- `tests/unit/test_authoring_runs_service.py` (extend — inject a fake `CorrectionSink` + a stubbed
  `RevisionCapture` + a stubbed `RevisionText`):
  - 🔴 `test_reject_unit_records_exactly_one_reject_correction_with_the_units_job_id`.
  - 🔴 **`test_accept_as_is_records_NOTHING`** — `latest_revision_id` returns `post_revision_id` ⇒ **the sink is
    NEVER called.** **(H2 — the test that stops the corrupted signal.)**
  - 🔴 `test_accept_after_edit_records_kind_edit_with_changed_blocks` — a NEW rev, texts `"a\nb"` vs `"a\nB"` ⇒
    `create` called **once** with `kind="edit"`, `changed_blocks=1`, `job_id=unit.job_id`.
  - 🔴 **`test_accept_new_revision_but_IDENTICAL_text_records_nothing`** — a no-op autosave mints a revision;
    revision-id divergence alone is **not** proof of an edit.
  - 🔴 **`test_accept_untouched_chapter_with_scene_headings_records_nothing`** — the drafted text contains
    `### Scene One`. **THIS TEST MUST FAIL against the naive `job.result["text"]` comparison** — it is the
    regression pin for the heading-stripping trap (F37). *Write it and watch it red against the naive impl
    before you write the real one.*
  - `test_post_revision_id_None_skips_capture` · `test_job_id_None_skips_capture` (never fabricate).
  - `test_book_client_raises_the_unit_is_STILL_accepted_and_create_is_never_called`.
  - 🔴 `test_a_capture_failure_NEVER_fails_the_reject` — the sink raises ⇒ `reject_unit` still returns the
    rejected unit; the restore still happened; the response carries `correction.status == "failed"`. **Read the
    unit row back from the DB — do NOT trust the return value.** **(fire-and-forget, proven)**
  - 🔴 **`test_revert_all_records_ONE_reject_correction_PER_UNIT`** (⚠ **not** "records no corrections") — the
    sink is called **once per reverted unit** across N units, and a raising capture does **not** abort the sweep.
  - `test_the_correction_is_stamped_with_the_ACTOR_not_the_run_creator` — pass `actor=U2`.
- `tests/integration/db/test_correction_capture.py` (**NEW, real PG**;
  `pytestmark = [skipif(TEST_COMPOSITION_DB_URL), pytest.mark.xdist_group("pg")]`):
  - 🔴 `test_reject_writes_a_row_AND_emits_GENERATION_CORRECTED_in_the_SAME_transaction` — assert **both**
    the `generation_correction` row **and** the `outbox_events` row exist after one `reject_unit`.
    *(A mock-only test proves the function was called, **not** that a row landed and an event will relay.)*
  - 🔴 **`test_outbox_law_no_half_state`** — patch `outbox.emit` to raise **inside** `create` ⇒
    `SELECT count(*) FROM generation_correction WHERE job_id=$1` is **0** (the INSERT rolled back with it) **and**
    `outbox_events` has no row. **No capture without an event; no event without a capture.**
  - `test_a_zero_change_edit_records_nothing` (H2, at the DB).
  - 🔴 **`test_insert_kind_accept_raises_a_CHECK_violation`** — the enum stays closed. *A drift-lock against a
    future builder "completing the enum".*
  - 🔴 **`test_revert_all_over_3_units_writes_3_outbox_rows`** (assert the **outbox table**, not a spy).
- `tests/unit/test_mcp_record_correction.py` (NEW): the 4-kind `Literal` is enforced; **`accept` is REJECTED**;
  a cross-project `job_id` → `uniform_not_accessible`; an `edit` with identical text → the `EDIT_NO_CHANGE`
  error shape; the tool's exported schema carries the `kind` enum; **`composition_record_correction` is in
  `EXPECTED_TOOLS`** and has a `tool-policy.ts` row.
- 🔴 **`tests/unit/test_correction_capture.py` (NEW — the anti-drift lock for BE-9e):** `capture_correction()`
  fed the same inputs produces the identical row for **all three** consumers (REST route · MCP tool · the
  accept/reject seam). **`grep -c "count_changed_blocks" services/composition-service/app` must not grow** — one
  home, one name.

**DoD evidence:** `composition-service: <N> passed`, with `test_accept_as_is_records_NOTHING`,
`test_a_capture_failure_NEVER_fails_the_reject` and
`test_reject_writes_a_row_AND_emits_GENERATION_CORRECTED_in_the_SAME_transaction` **named**.
Plus the **cross-service live-smoke** (§8.2).

---

### `W1-16` — the `quality-corrections` PANEL: extract `CorrectionStatsTable`, register, Lane-B

> **dependsOn:** `W1-13`, `W1-15`, `W1-06` · **kind:** FE · **Enum `N+3` → `N+4`.**

**Files**

1. **NEW `frontend/src/features/composition/components/CorrectionStatsTable.tsx`** — **extract** it out of
   `QualityPanel.tsx:37-95` **verbatim** (plus the `pct`/`num` helpers and the `composition-quality-coldstart`
   block). Export `CorrectionStatsTable({ stats })`.
   **QC-3 / F-Q11: do NOT mount `QualityPanel`.** It also renders `BookPromiseCoverageSection`, which the
   Studio **already ships as `quality-coverage`** — mounting it whole puts **a paid LLM action on screen
   twice, in two panels, with two buttons.** **Extract, don't mount.**

2. **`frontend/src/features/composition/components/QualityPanel.tsx`** — import the extracted component
   instead of declaring it. **Zero behavior change.** Its existing test
   (`__tests__/QualityPanel.test.tsx`) must stay green **unedited**.

3. **NEW `frontend/src/features/studio/panels/QualityCorrectionsPanel.tsx`** — the wrapper (≤ ~80 lines):
   `useStudioPanel('quality-corrections')` + `useQualityWork` gate + `useCorrectionStats(work.projectId, token)`
   + `<CorrectionStatsTable stats={...} />`. Root `data-testid="studio-quality-corrections-panel"`.
   **Writes: NONE.** **LLM calls: NONE.** It is free.
   - **BE-9c, stated IN THE UI** (mock state ⑥, the footnote under the table):
     ```tsx
     <p data-testid="quality-corrections-denominator-note" className="text-[11px] text-neutral-400">
       {t('quality.correctionsDenominator', {
         defaultValue: 'Counts DRAFT generations only — plan passes, quality reports and Polish runs are not corrections.',
       })}
     </p>
     ```
   - **one-mode-only** state: a Work that never used Diverge shows **`—`**, not `0%` (the extracted table
     already does this — `{m ? get(m) : '—'}`). **Verify it survived the extraction.**
   - **cold start**: `totalGens === 0` ⇒ the existing `composition-quality-coldstart` copy.

4. **GG-8 registration:** `catalog.ts` (`category: 'quality'`, `guideBodyKey`), `en/studio.json` +
   17 locales, `frontend_tools.py` enum + description clause
   (`'quality-corrections' = your accept/edit/regenerate/reject rates on AI drafts — the quality signal;`),
   **regenerate** the contract, **`QualityHubPanel` `CARDS` → 7** (`📈`). **The hub is now 4 → 7.**

5. **Lane-B** — the `CORRECTION_WRITE_PATTERN` handler already landed in `W1-06`. **Verify it fires**: an agent
   `composition_record_correction` must invalidate `['composition','correction-stats']`.

6. 🔴 **THE MAP FIX — DO IT WHILE YOU ARE HERE (one line each; `Q-31-F-Q11-DOUBLE-PAID-ACTION` BONUS FIX).**
   `docs/specs/2026-07-01-writing-studio/36_editor_craft_ports.md:653` maps **`flywheel: 'quality-corrections'`**
   in the `legacyParityContract` map. **That is WRONG by the code** — `CompositionPanel.tsx:850` puts
   `QualityPanel` under sub-tab **`quality`** and `:865` puts **`FlywheelPanel`** under sub-tab **`flywheel`**.
   They are two services, two datasets: `quality-corrections` = **CorrectionStatsTable** (composition correction
   RATES); `FlywheelPanel` = **knowledge-graph GROWTH** (`knowledgeApi.getFlywheel` — "+N entities / +N
   relations / +N events" the last extraction ADDED to canon). **The name collides; the thing does not.**
   **This is currently the single most dangerous line in the whole GG-4 retirement gate: it makes the
   machine-checked test GO GREEN on a feature that is about to be DELETED.**
   **Edits (all three):**
   - `36_editor_craft_ports.md:653` → change the row to **`quality: 'quality-corrections'`**, and give
     **`flywheel` its own row pointing at the KG wave** (spec 38 / **Wave 8** — a `canon-growth` / `kg-flywheel`
     panel; `getFlywheel` is a knowledge-service read and Wave 8 is already in those files).
   - `docs/plans/2026-07-13-studio-wave-6-editor-craft.md` — the same false row in `LEGACY_SUBTAB_HOME`
     (**`flywheel: 'quality-corrections'`**, ~`:1454`). ⚠ **Coordinate with the Wave-6 agent before editing that
     file** (shared checkout — a concurrent session may own it). If it is contended, **file the correction as a
     defer row naming the exact line** rather than racing the edit.
   - Same file, ~`:1457`: **`arc: 'arc-templates'` is ALSO wrong.** `arc-templates` (Wave 4) is the structure-
     TEMPLATE library; `arc-inspector` (Wave 2) is the narrative-arc SPEC tree. **Neither is `CharacterArcView`**
     (one character's events in `event_order` over the knowledge graph, spoiler-cut at the current chapter).
     Its home is a **`character-arc` panel in Wave 8**, beside `cast`.
   *(**Wave 1 does not port `FlywheelPanel` or `CharacterArcView`** — see §12. It **fixes the map rows that
   falsely claim it did**, because Wave 1 is the wave that owns `quality-corrections` and therefore knows the
   truth. If the PO instead rules either one won't-fix, that must become an explicit **DELETE_ON_PURPOSE** row in
   plan 30 §7's "Consciously OUT OF SCOPE" table — **NOT** a mislabelled map row.)*

**Tests** — NEW `frontend/src/features/studio/panels/__tests__/QualityCorrectionsPanel.test.tsx`:
- the three Work-gate states.
- `renders the Diverge and Stream columns from correction-stats`.
- `renders "—" (not 0%) for a mode with zero generations`.
- `renders the cold-start copy when there are no generations at all`.
- `renders the BE-9c denominator note` (the UI states what it counts).
- 🔴 **`does NOT render BookPromiseCoverageSection` AND `does NOT render a ModelPicker`** — mock
  `@/features/composition/components/BookPromiseCoverageSection`, assert its root testid is **null**, and assert
  **no model-picker** is rendered. **The F-Q11 regression lock: no paid button twice, no control wired to
  nothing.** *(`quality-corrections` triggers **no LLM call** — spec 31:637. The paid coverage pass stays solely
  in `quality-coverage`.)*
- 🔴 **`QualityPanel` never appears in `STUDIO_PANEL_COMPONENTS`** — a one-line guard in this test (or in
  `panelCatalogContract.test.ts`). *Mounting the parent puts a paid LLM action on screen twice.*
- **REGRESSION:** `QualityPanel.test.tsx` green, **unedited** — that is the extraction's proof for the legacy page.
- the 4 drift-locks: **+1** ⇒ the wave's final three-way equality (`N+4`, i.e. **61** if the baseline was 57).

**DoD evidence:** *"enum `N+3 → N+4`; py enum == contract enum == openable; `frontend: <N> passed`;
`QualityPanel.test.tsx` unedited and green."*

---

## 8 · THE CROSS-CUTTING WORK

### 8.1 · GG-8 registration checklist — the EXACT files, in order, per panel (plan 30 §8)

**Gate first — is the panel openable by a BARE id?** ✅ **All four are.** None needs a `node_id`/`rule_id` to
open — `focusRuleId` is an *optional* deep-link param with a defined no-param behavior (list everything).
⇒ **none is `hiddenFromPalette`**; all four enter the enum, the palette and the User Guide. **X-12 does not
bite this wave.**

| # | File | Edit | Done in |
|---|---|---|---|
| 0 | `frontend/src/features/studio/palette/useStudioCommands.ts` | **X-2 FIRST.** `'quality'` into `CATEGORY_ORDER` + the membership assertion. | `W1-00` |
| 1 | `frontend/src/features/studio/panels/{QualityCanonRulesPanel,StudioProgressPanel,QualityHealPanel,QualityCorrectionsPanel}.tsx` | The 4 components. Roots: `studio-quality-canon-rules-panel`, `studio-progress-panel`, `studio-quality-heal-panel`, `studio-quality-corrections-panel`. Each: `useStudioPanel(id, props.api)` + `useQualityWork(host.bookId, token)` + `if (work.kind !== 'ready') return <QualityWorkGate …/>`. | W1-05/08/11/16 |
| 2 | `frontend/src/features/studio/panels/catalog.ts` | 4 `STUDIO_PANELS` rows. `category: 'quality'` ×3; `category: 'editor'` ×1 (**`progress`** — QC-2). **`guideBodyKey` mandatory on all four** (X-3). | each panel slice |
| 3 | `frontend/src/i18n/locales/en/studio.json` | `panels.<id>.{title,desc,guideBody}` ×4 + the ~28 `quality.*` / `progressPanel.*` strings. | each panel slice |
| 4 | `frontend/src/i18n/locales/{ar,bn,de,es,fr,hi,id,ja,ko,ms,pt-BR,ru,th,tr,vi,zh-CN,zh-TW}/studio.json` | **`python scripts/i18n_translate.py`** — NEVER hand-written. ⚠ It **gap-fills only**: it keeps an existing translation, so **NEVER edit an `en` string that already has 17 translations** — **add a new key instead.** | each panel slice |
| 5 | `services/chat-service/app/services/frontend_tools.py` | **TWO edits** in `UI_OPEN_STUDIO_PANEL_TOOL`: (a) the id into the `panel_id` **enum** (~line 402); (b) a clause into the tool **description** (~403-481) — *that gloss is the model's ONLY hint the panel exists.* | each panel slice |
| 6 | `contracts/frontend-tools.contract.json` | **NEVER hand-edit — REGENERATE** and **commit it in the SAME commit** as steps 2 + 5:<br>`cd services/chat-service && WRITE_FRONTEND_CONTRACT=1 python -m pytest tests/test_frontend_tools_contract.py` | each panel slice |
| 7 | `frontend/src/features/studio/panels/QualityHubPanel.tsx` | `CARDS` 4 → **7**: `quality-canon-rules` ⚖️ · `quality-corrections` 📈 · `quality-heal` ✨. **`progress` is NOT a card** (QC-2). | W1-05/11/16 |
| 8 | `frontend/src/features/studio/agent/handlers/compositionEffects.ts` **(NEW)** + `useStudioEffectReconciler.ts` | `^composition_canon_rule_` and `^composition_record_correction$`. **Register it AND delete the false comment at `:8-9`.** | `W1-06` |
| 9 | `frontend/src/features/studio/host/studioLinks.ts` | **SKIP.** These panels are reached via `host.openPanel`, not a URL scheme. | — |
| 10 | `onboarding/tours.ts` | **SKIP.** Not a role-tour step in v1 (the `quality` hub's `tourAnchor` already covers the area). | — |

**Do NOT touch:** `StudioDock.tsx`, `StudioFrame.tsx`, `UserGuidePanel.tsx`, `useStudioCommands.ts` (beyond
X-2's `CATEGORY_ORDER`) — **all derive from `catalog.ts`.** Also `studioUiNav.ts` /
`useStudioUiToolExecutor.ts` (panel-id-agnostic).

**The running enum baseline (plan 30 §8.0):**

| After | added | `OPENABLE` == py enum == contract enum |
|---|---|---|
| HEAD `9262ed53e` | — | **57** |
| **Wave 1 (this)** | **4** | **61** |
| 2 (spec 32) | 1 | 62 |
| … | … | … |
| 8 (spec 38) | 2 | **71** |

⚠ **These are a PLANNING aid, not a test assertion.** A DoD asserts the **delta + the three-way equality**,
**never a literal** — if a wave is re-ordered or dropped, every literal below it is wrong and *"sends a
builder hunting a phantom regression."*

### 8.2 · `W1-17` — 🔴 THE LIVE BROWSER SMOKE (mandatory, not optional)

> **dependsOn:** `W1-05`, `W1-08`, `W1-12`, `W1-16` · **kind:** TEST
> **A green unit suite has repeatedly hidden *"the FE could not actually execute it"*
> (`agent-gui-loop-needs-live-browser-smoke-not-raw-stream`). This repo's `24_plan_hub_v2.md` named this exact
> DoD and then SHIPPED WITHOUT IT (H8.2). Not this time.**

**File:** NEW `frontend/tests/e2e/specs/studio-quality.spec.ts` (**note the path — `tests/e2e/specs/`, not
`e2e/`**; F28).

**Setup, non-negotiable:**
- 🔴 **REBUILD the image first.** `:5174` is the **BAKED nginx prod build** — a host `vite dev` **SHADOWS**
  it, and a stale image is a **false green** (`live-smoke-rebuild-stale-images-first`,
  `frontend-5174-is-baked-prod-nginx-not-vite`). Either rebuild the FE image, or run `vite dev` on `:5199`
  and point the spec at it. **Say which you did in the evidence.**
- Sign in as `claude-test@loreweave.dev` / `Claude@Test2026`.
- **Drive via `page.evaluate` + `data-testid`.** Playwright refs go stale in dockview
  (`playwright-live-dockview-automation-recipe`). Any drag uses `page.mouse` (trusted events).
- 🔴 **DO NOT DRIVE A LIVE MODEL FOR THE TOOL CALL — USE THE REPO'S SEALED INJECTION PATTERN**
  (`Q-31-DOD4-LIVE-BROWSER-SMOKE`). `frontend/tests/e2e/helpers/frontendToolInject.ts:11-21` states the rule
  this repo **already adopted**: *"We must NOT depend on a local model **choosing** to emit a given frontend
  tool (S06 showed that choice is non-deterministic). So this helper **INJECTS** a suspended frontend-tool
  call … The FE then runs its **REAL** executor/resolver/card … The only simulated part is the **trigger**;
  every line of FE execution under test is real."* **That preserves 100% of the property being protected** —
  the `panel_id`-enum bug shipped because `shown:true` was asserted **instead of the DOM**; injection still
  asserts the DOM. **Model-choice correctness** (the model can't invent `panel:"editor"`) is proven
  **deterministically** by the closed-set `enum` + the three-way contract guard already in DoD #2 — *that* is
  the right tool for that risk, **not a flaky LLM turn.**
  **Default set (PO may veto): the "$0 local lm_studio agent turn" is DROPPED as a hard prerequisite** —
  removing the *"lm_studio must be running"* dependency is precisely what makes this DoD **get run** instead of
  skipped for the third time. *(Where a real model turn IS still wanted — smoke #7's Lane-B sync — resolve the
  `model_ref` live: `SELECT user_model_id, alias, capability_flags FROM user_models WHERE owner_user_id='019d5e3c-7cc5-7e6a-8b27-1344e148bf7c' AND is_active;`
  ⚠ `user_default_models` is **EMPTY** for this account — pass an explicit `model_ref`.)*

**The seven assertions:**

1. 🔴 **VERIFY BY EFFECT, not by raw stream.** For **each of the 4 ids**:
   ```ts
   await installFrontendToolSuspend(page, { tool: 'ui_open_studio_panel', args: { panel_id: '<id>' } });
   await sendChat(page, 'open <name>');
   await expect(page.getByTestId('studio-<id>-panel')).toBeVisible({ timeout: 15000 });
   ```
   **A `shown:true` in the stream proves NOTHING** — the `panel_id`-enum bug shipped once already, exactly
   that way (gemma sent `panel:"editor"` → silent no-op → hallucinated success). Copy the spec template from
   `frontend/tests/e2e/specs/frontend-tools-liveness.spec.ts` (login, `createBook`/`createChapter`, the seeded
   session with the `last_message_at` bump — **the fresh-session-NULLS-LAST trap is already handled there at
   `:62-71`**). Testid convention confirmed at `QualityCriticPanel.tsx:44`
   (`data-testid="studio-quality-critic-panel"`) — **each of the 4 new panels MUST carry `studio-<panel-id>-panel`.**
2. **Canon round-trip:** palette → *Studio: Open Canon rules* → **add** a rule → it appears → **edit** it →
   **archive** it (confirm) → tick **Show archived** → **restore** → it is back in the active list.
3. **The deep-link chain:** `quality-canon` → a violation row's **Edit rule** → `quality-canon-rules` opens
   **focused on that rule id** (`[data-focused="true"]`).
4. 🔴 **The heal loop — the one that was dark:** `quality-heal` → pick a chapter + a **local** model →
   **Run Polish** → tick one edit → **Apply** → the editor's document changes → **⌘S saves it** (reload the
   chapter; the healed text is still there — *this is the F18 trap, proven closed*) → open `quality-critic`
   on the **SAME chapter** → assert **`[data-testid="violation-has-fix"]` is VISIBLE.**
   **This single assertion is `D-QUALITY-CRITIC-HEAL-LINK` closed, proven by effect.**
5. **The stale guard:** run Polish → **type in the editor** → click Apply → assert
   `[data-testid="quality-heal-stale-dirty"]` renders **and the document is UNCHANGED.**
6. **DOCK-7 regression — 🔴 NO SECOND ACCOUNT NEEDED.** Simulate zero models by **stubbing the ONE route**:
   `await page.route('**/v1/model-registry/user-models*', r => r.fulfill({ json: { items: [] } }))`
   (`useUserModels.ts:40` → `aiModelsApi.listUserModels` → `ai-models/api.ts:124`) **before** opening
   `quality-heal` → click the `AddModelCta` link (`ModelPicker.tsx:388`) → assert **`studio-dock` is still
   visible** and a `settings` panel opened with `tab=providers`. X-1's guard, on the panel that introduces the
   new `ModelPicker` call site.
7. **Lane-B live sync:** with `quality-canon-rules` **open**, have the agent call
   `composition_canon_rule_create` → the new rule appears in the panel **WITHOUT a manual reload.**

**8.2b — Cross-service live-smoke evidence (M4).**

🔴 **"book-service" IS A COPY-PASTE TYPO IN SPEC 31's M4 DoD — AND IT WAS COPIED INTO THIS PLAN**
(`Q-31-M4-LIVESMOKE-BOOK-SERVICE`). **book-service is not in the correction path at all**
(`grep -ri "generation_corrected" services/book-service` → **ZERO hits**); the word *"restore"* leaked in from
**M1's** canon-rule restore, which is a **composition** route. **M4's real seam crosses THREE processes:
composition-service → worker-infra's outbox relay → learning-service.**
**FIX THE SPEC** (`31_quality_completion.md:683-684` and `:720-721`) to say
*"composition-service → the worker-infra outbox relay → learning-service's `corrections`"* — **3 services.**

🔴 **AND THE GATE WILL NOT PROMPT YOU FOR THE TOKEN — TYPE IT ANYWAY** (`Q-31-DOD6-REVIEW-IMPL` (2)).
`workflow-gate.py::_check_live_smoke_evidence` only warns when `git diff --name-only HEAD` touches **≥2 distinct
`services/<name>/` prefixes**. **M4's diff touches ONLY `services/composition-service/`** (+ `frontend/`,
`contracts/` — which are **not counted**) ⇒ **the gate emits nothing, and a builder who trusts it ships M4
mock-only.** The `live smoke:` token is a **HAND-TYPED, HARD DoD item** here, not a gate output.

**The smoke the builder actually runs at M4 VERIFY** (rebuilt images — *a stale image is a false green*; signed
in as `claude-test@loreweave.dev`; composition-service + worker-infra + learning-service + Postgres + Redis all up):
```
a. Reject one unit of a real authoring run (or call MCP `composition_record_correction` with kind='reject').
b. Assert in loreweave_composition: exactly ONE `generation_correction` row (kind='reject', non-NULL job_id)
   AND ONE `outbox_events` row (event_type='composition.generation_corrected', aggregate_type='composition')
   written in the SAME transaction.
c. Assert the relay drained it → XRANGE loreweave:events:composition shows the message carrying an `outbox_id`.
d. Assert BY EFFECT AT AN API BOUNDARY, not by peeking at SQL:
   GET /v1/learning/corrections (as the same user) returns a row with target_type='generation',
   origin_service='composition', op='reject', target_id=<the job_id>.
   (Route exists: services/learning-service/app/routers/corrections.py:64.)
e. ALSO settle UNVERIFIED-1 by effect: run a Revert-All over ≥5 units in the same smoke and confirm the burst
   does NOT DLQ (the learning consumer retries→DLQ; it does not ack-on-error) and that N units ⇒ N rows.
```
**The evidence token to paste, filled with real ids:**
```
live smoke: reject_unit on run <run_id> → generation_correction(job_id=…) + outbox
composition.generation_corrected (same txn) → worker-infra relay XADD loreweave:events:composition
(outbox_id=…) → learning-service corrections row visible via GET /v1/learning/corrections
(target_type=generation, op=reject, target_id=<job_id>)
```
If (c)/(d) genuinely cannot be brought up at dev time, **the ONLY acceptable fallbacks** are the gate's other two
tokens — `LIVE-SMOKE deferred to D-31-M4-LIVE-SMOKE` (**with the row written**) or
`live infra unavailable: <reason>`. **A green mock test is not one of them.**

### 8.3 · `W1-18` — `/review-impl` + SESSION + the wave commit

> **dependsOn:** all · **kind:** DOC/TEST

1. 🔴 **`/review-impl` RUNS AT THE CLOSE OF *EVERY MILESTONE*, NOT ONLY AT THE WAVE'S END**
   (`Q-31-DOD6-REVIEW-IMPL` (1) — **the PO run policy is STRICTER than spec 31's DoD #6 and supersedes it**).
   Bake it in as a literal DoD line in **each of M1..M4**: *"`/review-impl` run at milestone close; every finding
   fixed or filed as a defer row before the milestone commits."* **M2** (BE-P2 — a tenancy boundary) and **M4**
   (a DDL column + a new cross-service write path) are **non-negotiable**; the other two get it per the run
   policy. **No PO checkpoint is added** — `/review-impl` is a self-run subagent gate, not a human stop.
   Then run it once more on the **wave's full diff** (it is also an API-contract narrowing, BE-9c′).
   **EVERY bug it finds is FIXED before the wave closes.** Fold its findings into the VERIFY evidence.
2. 🔴 **SESSION BOOKKEEPING IS PER-MILESTONE, NOT SAVED UP FOR M4** (`Q-31-DOD7-SESSION-BOOKKEEPING`). All of it
   in **`docs/sessions/SESSION_HANDOFF.md` only** — ⚠ `docs/deferred/DEFERRED.md` is the **AMAW-mode** file;
   **do not touch it** in default v2.2 mode.
   - **AT M1 SESSION** — flip the **00C Q-3** row (`00C_POST_ARCHITECTURE_QUEUE.md:35`) from *"📐 superseded by
     spec 31"* to **"✅ CLEARED"**, and add **Q-3(a)** (progress port) to *Recently cleared*.
     ⚠ **Q-3(a) clears at M2 (the `progress` panel), Q-3(b) only at M4 (the corrections port). File each when
     its milestone lands — not both early.**
   - **AT M3 SESSION** — 🔴 **CORRECT, don't just move, the `D-QUALITY-CRITIC-HEAL-LINK` row
     (`SESSION_HANDOFF.md:3371`). It is ALREADY struck as "RESOLVED 2026-07-01" — and that is FALSE:** the fix
     shipped on the **legacy** `PolishPanel` only; `QualityCriticPanel.tsx:80` mounts `<QualityReportSection>`
     with **no `proposals` prop**, so `_hasProposedFix()` **cannot fire for a Studio user** (F21). Rewrite it to:
     *"RESOLVED (legacy) 2026-07-01; **RESOLVED (Studio) at spec-31 M3** … Proven by effect: Playwright
     `studio-quality.spec.ts` asserts `[data-testid="violation-has-fix"]` visible after Apply."*
     🔴 **Do NOT write that line before the Playwright assertion actually passes** — *a second false RESOLVED on
     the same row is the bug this repo already shipped once.*
   - **AT M4 SESSION** — append the §9.4 rows to the **EXISTING** `### Deferred (from plan 30 …)` table at
     `SESSION_HANDOFF.md:95` (same `| ID | What | Gate |` shape; **no new section**).
   **The rule for all of it:** *no row is written before the thing it claims is true. A defer row states what is
   NOT done; a cleared row states what IS done **and names the test that proves it**. Work not recorded does not
   exist — and work **falsely** recorded as done is worse.*
3. **Commit.** Stage **only** the changed files — enumerate them; **never `git add -A`** (concurrent sessions
   share this checkout). Message names the phase + the review fixes + the test counts.

---

## 9 · WAVE DEFINITION OF DONE — a literal checklist

Tick every box. **A box you cannot tick with a pasted command output is not ticked.**

- [ ] **1 · Unit suites GREEN, with counts pasted.**
  - `cd services/composition-service && python -m pytest tests -q -n auto --dist loadgroup` → `<N> passed`
  - `cd services/chat-service && python -m pytest tests -q` → `<N> passed`
  - `cd frontend && npx vitest run` → `<N> passed`
  - **Every NEW composition test touching a real DB/port carries `pytestmark = pytest.mark.xdist_group("pg")`.**
    Grep to prove it: `grep -rn "xdist_group" services/composition-service/tests/integration/db/test_progress_goal.py services/composition-service/tests/integration/db/test_correction_capture.py`
- [ ] **2 · The two machine guards green, asserted as a DELTA + a three-way equality — NEVER a literal.**
  `py enum == contract enum == openable`, and `N_before + 4 == N_after` (**61** if the baseline was 57).
  The **regenerated** `contracts/frontend-tools.contract.json` is committed **in the same commit** as
  `catalog.ts` + `frontend_tools.py` for each panel.
- [ ] **3 · 17 locales generated by `python scripts/i18n_translate.py`.** No hand-written translation.
  **NO existing `en` string that already has 17 translations was edited** (prove it:
  `git diff frontend/src/i18n/locales/en/studio.json` shows **additions only**).
- [ ] **4 · 🔴 LIVE BROWSER SMOKE — `frontend/tests/e2e/specs/studio-quality.spec.ts` GREEN**, against a
  **REBUILT** image (or `vite dev :5199` — say which), signed in as `claude-test@loreweave.dev`. All seven
  assertions of §8.2, and in particular:
  - each of the 4 panels **mounts its dock tab** when opened by a real agent turn calling
    `ui_open_studio_panel` (**not** a `shown:true` in the stream),
  - the canon **create → edit → archive → show-archived → restore** round-trip,
  - the heal loop: **Apply → the doc changes → ⌘S PERSISTS it across a reload** → `quality-critic` shows
    **`[data-testid="violation-has-fix"]`**,
  - the **stale-dirty** guard renders and the document is **unchanged**,
  - the **DOCK-7** regression: the *Add a model* CTA does **not** unmount the dock.
- [ ] **5 · Cross-service live-smoke evidence for M4** — the VERIFY evidence string carries
  `live smoke: <one-liner>` for **composition-service → worker-infra's outbox relay → learning-service**
  (🔴 **NOT book-service — that was a copy-paste typo in spec 31's DoD; book-service has ZERO hits for
  `generation_corrected`**). A `generation_correction` row **AND** a `composition.generation_corrected` outbox
  row landed **in one txn** from a real reject, the relay XADDed it, and it is visible **by effect** at
  `GET /v1/learning/corrections`. ⚠ **The gate will NOT prompt you for this token** (M4's diff touches one
  `services/` prefix) — **type it by hand.**
  *(Or, honestly: `live infra unavailable: <reason>` / `LIVE-SMOKE deferred to D-31-M4-LIVE-SMOKE`.)*
- [ ] **6 · 🔴 `/review-impl` RUN AT EVERY MILESTONE CLOSE (M1..M4), and again on the wave's full diff — and
  EVERY bug it finds FIXED before that milestone commits.** Fold its findings into the VERIFY evidence string.
  (Tenancy boundary + a new cross-service write path + a DDL column + an API narrowing — all four proactive
  triggers, and the PO run policy makes it per-wave-completion regardless.)
- [ ] **6b · 🔴 The CONTRACT slice landed BEFORE the FE slices that consume its routes** (`W1-CONTRACT`).
  `git log --oneline` shows it preceding `W1-04` / `W1-08`. *CLAUDE.md: "Contract-first: API contract frozen
  before frontend flow."*
- [ ] **7 · SESSION** — `docs/sessions/SESSION_HANDOFF.md` ▶ NEXT SESSION block overwritten;
  **`D-QUALITY-CRITIC-HEAL-LINK`** and 00C **Q-3(a)(b)** moved to *Recently cleared*; the §9.4 defer rows filed.
- [ ] **8 · COMMIT** — files enumerated (**never `git add -A`**); `git diff --cached` checked before each
  commit; the message names the phase, the review fixes, and the test counts.
- [ ] **9 · The four gaps are actually CLOSED, proven by effect (not by checklist):**
  - `G-CANON-RULE-CRUD` — a Studio user can create/edit/archive/**restore** a canon rule. ✅ smoke #2
  - `G-PROGRESS` — a Studio panel READS the word-count snapshots the hoist has been writing on every save.
    ✅ `studio-progress-panel` renders `today_words` > 0 after a save.
  - `G-CORRECTION-FLYWHEEL` — rejecting a unit in `agent-mode` writes a `generation_correction`. ✅ live smoke
  - `G-POLISH-SELFHEAL` — the `violation-has-fix` badge, unreachable dead code for the whole life of the
    Studio, **renders**. ✅ smoke #4

---

## 9.4 · DEFER REGISTER — the starting rows (file these in `SESSION_HANDOFF.md` at `W1-18`)

| ID | Origin | What | Gate | Target / trigger |
|---|---|---|---|---|
| **D-31-PROPOSE-EDIT-CORRECTION** | spec 31 OQ-1 / F-Q4 | A Studio-Compose `propose_edit` Apply/Dismiss records **no** correction. It has no `job_id` and its prose came from a **chat-service** turn, not a composition `generation_job`. Options: (a) mint a job for a chat prose turn (cross-service, and it would need a `mode`/`operation` BE-9c's allowlist admits); (b) a nullable `chat_run_id` on `generation_correction` + relax the FK; (c) accept that the flywheel learns from **structured** generation only. **v1 = (c).** | **#2** (large/structural — needs a design) | When Compose's prose path is itself specced. |
| **D-31-HEAL-CORRECTION-KIND** | spec 31 OQ-2 / QC-5 | Accepting/rejecting a self-heal fix is a real human-gate signal and is **not** recorded. Adding `heal_accept`/`heal_reject` is a CHECK migration that trips `migration-check-constraint-must-backfill-all-historical-blocks`, and correcting a *fix* is a **different signal** from correcting a *draft*. | **#5** (conscious won't-fix) | Revisit only with a learning-side consumer for the new kind. |
| **D-31-SELFHEAL-COST-GATE** | spec 31 OQ-3 / QC-7 / BE-Q4 | **Run Polish**, **Analyze quality** and **Coverage** are paid LLM actions with **no cost estimate** — a genuine gap across **three already-shipped panels**, so not this wave's regression. The fix is a `composition.self_heal_propose` (+ `.quality_report`) descriptor on the **generic** `/actions/preview` → `/actions/confirm` spine. **Do NOT invent `/self-heal/estimate` — three such routes already 404 in production.** | **#2** | A dedicated cost-gate pass over the paid quality actions. |
| ~~**D-31-DISMISS-MCP**~~ | — | 🔴 **DELETED — NOT DEFERRED. `composition_dismiss_violation` is BUILT in `W1-03`** (§2 OQ-4 / BE-11d). It clears **none** of the 5 defer gates: the logic already exists in the REST handler, and *"a route you could write is unbuilt work, not a blocker."* | — | — |
| ~~**D-31-REVERTALL-CAPTURE**~~ | — | 🔴 **DELETED — NOT DEFERRED. `revert_all` DOES capture** (§2 UNVERIFIED-1 / F36). The "unmeasured burst" premise was **read and refuted**: a durable Redis Streams consumer group with batched reads, per-msg XACK, retry→DLQ and `MAXLEN 10000`, doing **one INSERT … ON CONFLICT DO NOTHING** per event with **zero token spend**. And the read exposed the **real** gap: `revert_all` bypasses `reject_unit`, so the capture would have silently missed the richest bulk-rejection signal. | — | — |
| **D-31-CORRECTION-DRILLDOWN** | spec 31 BE-9d | A per-row corrections drill-down. **NO CALLER** — Panel C's wireframe is a per-mode aggregate with no per-job row to click, so the route would ship with **zero consumers**. 🔴 **The "learning-service may already serve this" caveat is FALSE — grepped:** `GET /v1/learning/corrections` takes only `project_id/target_type/diff_class/limit/cursor`, **no `target_id`/`job_id` filter**, and it **must not be widened for this** (its copy is **redact-by-default** — `has_guidance`/`has_raw_prose` **booleans**, never prose). `list_for_job()` stays **test-only** — do not delete it, do not "wire it up for completeness". **If ever asked for, build it in COMPOSITION** (the author's own Work, full fidelity), never by adding a filter to learning's redacted training corpus. | **#1** | If/when the drill-down is actually asked for. |
| **D-31-BE-18-SETTINGS-OCC** | inherited from plan 30 | 🔴 **THE ROW TEXT IS WRONG — CORRECT IT** (F40). *"NO If-Match"* is **FALSE at HEAD**: server-side OCC already ships (`works.py:588,597,603-607` → 412 `WORK_VERSION_CONFLICT`; the repo gates `WHERE version = $n`). **BE-18 is FE-ONLY** — `patchWork(…, ifMatch?)` + a single 412 refetch-remerge-retry on the two surviving callers (`useWork.ts:135`, `useChapterAssembly.ts:33`). ⚠ **And do NOT "fix" it with a jsonb `\|\|` merge** — full-blob replace *under OCC* is the correct semantics; a merge would make key-**deletion** impossible. **BE-P2 removes THIS WAVE's exposure** (the `patchWork` goal caller is deleted). **Edit both `30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md:312` and `31_quality_completion.md:530`.** | **#1** | **Wave 6** (spec 36, `G-WORK-SETTINGS` — where the Composition-settings panel becomes the caller). |
| 🔴 **D-QUAL-WHATIF-DENOMINATOR** *(new — from the adjudication)* | `W1-13` / BE-9c | `useWhatIfTakes.ts:36` generates **ephemeral** takes as `operation:'draft_scene'`, `mode='auto'`, and deliberately captures **NO** correction — so those jobs **enter the `auto` denominator as false accepts**, and `operation` alone cannot distinguish them. This is the pre-existing H2 conflation the repo already documents (*"accepted as-is (or abandoned — conflated)"*, `generation_corrections.py:227`). **Do NOT widen BE-9c to chase it.** | **#2** (large/structural — needs an `input.ephemeral=true` flag written by the FE **+** a 3rd predicate = an FE+BE contract change) | The wave that touches the what-if / scene-graph surface. |
| 🔴 **D-STUDIO-CHAT-PROSE-OUT-OF-FLYWHEEL** *(new — the OQ-1 tracking row)* | `W1-15` / OQ-1 | Studio-Compose `propose_edit` prose is **not** captured as a `generation_correction` (decided (c)). **If a future track wants the signal, the ONLY sanctioned shape is:** route the Compose prose edit through the **EXISTING** composition selection-edit job path (`engine.py:703`, which mints a real `generation_job.id`), **then separately** decide whether selection-edit jobs enter the denominator — **never** a nullable-FK / `chat_run_id` hack (a job-less correction has **no denominator at all** and breaks the numerator ⊆ denominator invariant a prior `/review-impl` already had to fix). | **#5** (conscious won't-fix) | A spec for Compose's prose path. |
| **D-31-LEGACY-POLISH-DIRTY** *(new — found while reading)* | this plan, F18 | 🔴 **The LEGACY page has the same bug the Studio is fixing.** `ChapterEditorPage.handleApplyPolish` (`:591-602`) calls `tiptapEditorRef.current?.setContent(...)`, which **suppresses `onUpdate`** ⇒ the legacy Polish Apply may not dirty the page's doc either, so the author's ⌘S can save nothing. **Verify and fix, OR let spec-16's retirement delete the page.** Not fixed here because the Studio path is the one being shipped and the legacy page is slated for deletion in **Wave 6**. | **#1** (out of scope — different surface, being deleted) | Wave 6 (spec 16 retirement) — **or fix now if the retirement slips.** |
| **D-31-CANON-UPDATE-MCP-PARTIAL** *(new — found while reading)* | this plan, F3 | `composition_canon_rule_update` accepts only `text` + `active` — **not** `scope`, `entity_id`, `kind`, `from_order`, `until_order`, all of which the REST `PATCH` and the (now) GUI accept. After this wave the **human** can edit every field and the **agent** can edit two. A GG-2 inverse gap, in the direction nobody was watching. | **#1** (out of scope — a 10-line MCP widening, but it is a *new* asymmetry this wave *reveals*, not one it creates) | Next wave touching the composition MCP surface. **Cheap — take it opportunistically.** |

---

## 10 · RISKS — and the TELL that each has fired

| Risk | The tell | Mitigation |
|---|---|---|
| 🔴 **`quality-corrections` ships on a corrupted denominator** and the author trusts a false *"you accept 71% of drafts"*. | `accept_rate` is suspiciously high and `edit/regen/reject` are near zero on a book the author has been fighting with. **The panel is most convincing exactly when it is most wrong.** | **BE-9c ships in the SAME milestone as the panel (M4), FIRST, alone, with `test_correction_stats_ignores_non_draft_operations`.** Non-negotiable. |
| 🔴 **The allowlist is "helpfully" widened to the cowrite ops** and silently reverts the documented `selection_edit` fix — corrupting the very *Stream* column the panel charts. | `cowrite.generations` jumps; `cowrite.accept_rate` drops; the `test_correction_stats_still_excludes_selection_edits_after_the_allowlist` test **reds**. | That test is the tripwire, and F12 + the in-code comment on `CORRECTABLE_OPERATIONS` say the trap out loud. **`mode` and `operation` are orthogonal. There is no such thing as a cowrite op.** |
| 🔴🔴 **`quality-heal` applies the fix and the author's ⌘S saves NOTHING.** `setContent` suppresses `onUpdate` (F18); the hoist never goes dirty; `save()` early-returns; the heal vanishes on reload — **with a green "Applied" toast on screen.** | The e2e Apply→⌘S→reload assertion (smoke #4) fails. Or: users report "Polish doesn't stick." | `applyHealedDocument` calls **`setBody(doc, text)` itself**, and `an applied heal marks the hoist DIRTY` is the named unit test. **The live smoke reloads the chapter.** |
| 🔴 **`quality-heal` SILENTLY REVERTS the author's prose** by splicing a stale `sourceText`. The bug exists on the legacy page today, masked only by `key={chapterId}` + co-location; in the dock, `quality-heal` is a **persistent tab next to a live dirty editor.** | An author loses a paragraph they typed after running Polish, and never knows why. | The **three stale guards** (chapter / version / dirty), each **rendered**, each **disabling Apply**, each with **its own test** and its own e2e assertion. `draftVersion` has been captured and unread since the hook was written — **W1-11 is the first code that reads it.** |
| **BE-9a's `job_id` backfill temptation.** A later agent "fixes" the NULLs by guessing the unit's job from the timestamp. | Corrections attributed to the wrong generation; the learning store quietly poisoned; no test fails. | The column is **nullable by design**; the DDL comment says *"NEVER backfill a guess — a wrong job_id attributes the author's rejection to someone else's generation"*; the Run Report **states** when a unit has no job (`agent-mode-no-feedback-capture`). |
| **The Lane-B handler silently matches NOTHING.** `registerEffectHandler`'s **string** branch is `tool === p \|\| tool.startsWith(p)` — **not** a pattern match. A string with alternation matches nothing and ships a **silent no-op** handler that no unit test (which registers and calls its own fake) can catch. | Agent writes a canon rule; the open panel stays stale. Every test is green. | **Use a `RegExp`.** The `compositionEffects.test.ts` RegExp assertion + the **wiring** test (`matchEffectHandlers(...).length === 1` after the reconciler mounts) + the **live** Lane-B smoke (#7). |
| **Two `PolishPanel` consumers diverge** once `usePolishProposals` moves to the query cache. | `PolishPanel.test.tsx` reds. | **The hook's return shape is UNCHANGED (QC-1).** The legacy panel's tests are the regression gate and must stay green **unedited** — `git diff --stat` proves it. |
| **The i18n tool leaves 17 stale locales** because someone edited an existing `en` string. | 17 locales silently keep the OLD copy forever. **No test catches this.** | `scripts/i18n_translate.py` **gap-fills only.** **Add keys; never edit them.** The DoD asserts `git diff en/studio.json` is **additions only**. |
| 🔴 **A stale "GG-4 GATE" doc line sends someone hunting a retirement that is not scheduled.** | An agent reads plan 30 §7's *"🔴 GG-4 GATE … retirement may proceed"* and starts sequencing work around a deletion **spec 16 already decided not to do**. | **GG-4 is SATISFIED BY CONSTRUCTION** (§2 GG-4). Spec 16 is **CLOSED**; Phase 4b (2026-07-05, the user's call) **keeps `ChapterEditorPage.tsx` indefinitely** as an unlinked, banner-marked fallback. What this wave owes it is **one mechanical guard, not a prose banner**: `ProgressPanel.test.tsx` asserting the Studio panel **renders `today_words`/`daily_goal` from `GET /works/{pid}/progress`.** From the moment that is green, the save-time word-count loop **cannot be orphaned by any deletion.** **FIX the four stale doc lines at wave close** (plan 30 §7 + GG-3's row; 31:402 + 31:753). |
| 🔴 **`Literal["draft_scene"]` ships and 422s the inline ghost + Adapt-from-source.** | Users report *"the ghost text stopped working"* / *"Adapt from source is broken"* — **and every unit test is green**, because the two callers live in the FE. | **The closed set is per-route and comes from the drafter's own registry** (F32/§2 9c′-LITERAL): `GenerateBody → ["draft_scene","continue","adapt_scene"]`. **`test_generate_accepts_continue_and_adapt_scene` is the named lock**, plus the drift guard `set(get_args(...)) == set(DRAFT_OPERATIONS)`. |
| 🔴 **"Clear my goal" DELETEs the row and resurrects a collaborator's goal.** | Bob clears his goal and his panel starts measuring him against **Alice's** 2000-word book target. **The tenancy fix re-enters through the clear path.** | **UPSERT to NULL — the row's EXISTENCE is the tier claim** (§2 P2-CLEAR). The tri-state read (`get_goal_row`), and **`test_clearing_a_user_goal_does_NOT_re_expose_the_legacy_goal`** as the named lock. **Never `row.daily_goal or legacy`.** |
| 🔴 **Accept-as-is records a phantom `kind='edit'` on every accepted chapter with scene headings.** | `avg_edit_magnitude` and `edit_rate` climb on a book where the author accepted everything untouched. **The flywheel trains the reranker on its own picks (H2).** | **Compare revision TEXT to revision TEXT through ONE extractor** (F37) — never `job.result["text"]` (raw LLM prose with `### ` markers) against TipTap `_text` (markers stripped). **`test_accept_untouched_chapter_with_scene_headings_records_nothing` MUST FAIL against the naive compare** — that is the regression pin. |
| **The enum count is asserted as a LITERAL** (`expect(ids).toHaveLength(61)`). | A re-ordered or dropped wave sends the next builder hunting a phantom regression. | **Assert `N_before + k == N_after` and the three-way equality. NEVER a literal.** Six of eight specs got this wrong by each computing from 57. |
| **A concurrent session's staged changes ride into a commit.** Three tracks share this checkout. | An unrelated file appears in `git show --stat`. | `git diff --cached` **before every commit**; enumerate paths; **never `git add -A`**. Remember: `git commit -- <path>` commits the **WORKING TREE**, not the index. |
| **`accept_unit`'s edit-detection false-positives** — a whitespace-only save after the draft creates a new revision and looks like an edit. | `avg_edit_magnitude` creeps toward 1 with meaningless corrections. | The sink's **`changed_blocks == 0 ⇒ record NOTHING`** guard (H2, mirroring `engine.py:1756`'s `EDIT_NO_CHANGE`). Tested at the DB (`test_a_zero_change_edit_records_nothing`). |
| **A capture failure blocks the human's review.** | A reject 500s because learning telemetry hiccuped — the author cannot reject a bad chapter. | The capture is **fire-and-forget**, wrapped in `try/except` that **logs and continues**, and `test_a_capture_failure_NEVER_fails_the_reject` is the named lock. The legacy FE's own rule: *"Correction capture is fire-and-forget telemetry — it must never block."* |

---

## 11 · SLICE DEPENDENCY GRAPH (the build order at a glance)

```
W1-00 (X-2/X-3 gate) ─┬─────────────────────────────────────────────┐
W1-01 (X-1 gate) ─────┼──────────────────────────────┐              │
W1-CONTRACT (openapi) ┼──────┐ (must precede W1-04 + W1-08)         │
                      │      │                       │              │
M1: W1-02 (BE restore) ─▶ W1-03 (MCP restore + DISMISS + tool-policy)│
    W1-02 ──────────────▶ W1-04 (FE data layer) ◀────┘              │
                              │                                     │
                              └─────────────────────▶ W1-05 (panel + reg + deep-link + QC-9)
                                                     │       │
                                                     │       ▼
                                                     │   W1-06 (Lane-B compositionEffects.ts)
                                                     │
M2: W1-07 (BE-P2 + P1 + P3 + P4) ────────────────────┼─▶ W1-08 (progress panel + reg)
                                                     │
M3: W1-09 (healGuard + applyHealedDocument) ─┐       │
    W1-10 (usePolishProposals + charac. test)─┴──▶ W1-11 (ChapterPicker + quality-heal) ◀──┘ (needs X-1)
                                            │
                                            ▼
                                        W1-12 (critic link — the badge fires)
                                            │
M4: W1-13 (BE-9c/9c′ denominator) ─▶ W1-14 (BE-9a job_id) ─▶ W1-15 (BE-9b capture + revert_all + MCP)
                                                                     │
                                            W1-06 ──────────────────┴─▶ W1-16 (corrections panel + reg + MAP FIX)
                                                                              │
                          W1-05, W1-08, W1-12, W1-16 ─────────────────────────┴─▶ W1-17 (LIVE BROWSER SMOKE)
                                                                                        │
                                                                                        ▼
                                                                              W1-18 (/review-impl + SESSION + COMMIT)
```
🔴 **`W1-CONTRACT` is a HARD predecessor of the FE slices** (CLAUDE.md contract-first). It may run in **parallel**
with `W1-02`/`W1-07` (the BE implementations) — they are written from the same §5 table — but **no FE slice may
consume a route whose contract is not frozen.**

**Parallelism note.** M1, M2 and M4's backend slices touch **disjoint** files and may be built in parallel
(`fanout-independent-slices-parallel-build-serial-integrate`). **M3 must wait on `W1-01`.**
**Integration and VERIFY are SERIAL — ONE combined full-suite run before the wave commits.**

---

## 12 · WHAT THIS PLAN DELIBERATELY DOES *NOT* DO

Recorded so it stops re-surfacing (and so a reviewer does not "find" it as a gap):

- **No `/self-heal/estimate` route.** No per-action estimate route of any kind. (QC-7 / D-31-SELFHEAL-COST-GATE.)
- **No `composition_self_heal_propose` MCP tool.** It is a **paid** action and would need a Tier-W
  propose→confirm descriptor (BE-Q4) to be admissible at all.
- **No progress MCP tool.** *"Progress is a personal stat, not a capability the agent should write. Recording
  words on the user's behalf would corrupt the author's own signal. **This is a deliberate non-gap; do not
  'fix' it.**"* (spec 31, Agent surface.)
- **No `QualityPanel` mount.** Extract `CorrectionStatsTable`; never mount the parent (it would put a paid
  LLM action on screen twice — F-Q11).
- **No `FlywheelPanel` port.** It is knowledge-graph growth (`knowledgeApi.getFlywheel`), **not** the
  correction flywheel. **The name collides; the thing does not.**
  🔴 **BUT THAT IS *NOT* THE SAME AS "IT HAS NO HOME."** `FlywheelPanel` is a **live legacy sub-tab** that the
  **GG-4 retirement gate will DELETE** unless some wave ports it — and **two map rows currently LIE that Wave 1
  already did** (`36_editor_craft_ports.md:653` and wave-6's `LEGACY_SUBTAB_HOME`, both
  `flywheel: 'quality-corrections'`). **That makes a machine-checked gate go GREEN on a feature being deleted.**
  **`W1-16` step 6 FIXES those rows** (`quality: 'quality-corrections'`, and `flywheel` → **Wave 8**, a
  `canon-growth` / `kg-flywheel` panel — `getFlywheel` is a knowledge-service read and Wave 8 already owns those
  files). **Wave 1 corrects the map; Wave 8 builds the panel.** Same for **`arc`** (`CharacterArcView` — a
  character's events over the KG, spoiler-cut; **not** Wave 4's `arc-templates`, **not** Wave 2's
  `arc-inspector`): the false row is fixed here, the panel is homed in **Wave 8**.
  ⚠ **If the PO instead rules either one won't-fix, that must become an explicit `DELETE_ON_PURPOSE` row in plan
  30 §7's "Consciously OUT OF SCOPE" table — NEVER a mislabelled map row.**
- **No `ComposeView` / `ChapterAssembleView` / `CastCodexPanel` / `WorldMap` / `CanonAtChapterPanel` port.**
  None of them is quality-completion work. **They are NOT abandoned** — they are homed elsewhere and the homes
  are named so GG-4 cannot delete them silently: `compose` + `chapter-assemble` + `canonview` → **Wave 6**
  (editor-craft); `cast` + `place-graph` → **Wave 8** (KG/world). *(Wave 1 touches none of them; this bullet
  exists so a reviewer does not "find" them as a gap here.)*
- **No `by_chapter` in `progress`'s sparkline** — `by_chapter` is the **anchor day only**, as the mock says
  (*"by chapter (today)"*).
- **No new `quality` category.** `'quality'` already exists in `StudioPanelCategory`; X-2 only adds it to
  `CATEGORY_ORDER`. **Do not invent a `narrative` or `motif` category** — a category in the type but not in
  `CATEGORY_ORDER` sorts **FIRST** (`indexOf → -1`).
- **No gateway change.** `/v1/composition/*` is proxied generically with no rewrite (F27).

---

*End of plan. Written at BUILD DETAIL under the PO's once-only policy: after QC, implementation proceeds
autonomously. If something here is vague, that is a defect in this file — but do not stall on it: pick the
option this plan's own §2/§3 most nearly implies, record the choice in the RUN-STATE decisions register, and
KEEP GOING. Blocked ≠ stopped.*
