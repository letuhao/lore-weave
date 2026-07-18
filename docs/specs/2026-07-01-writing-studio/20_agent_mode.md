# #20 — Agent Mode / Mission Control

> **Status:** ✅ **SHIPPED** — the `agent-mode` panel is in
> [`catalog.ts`](../../../frontend/src/features/studio/panels/catalog.ts) **and** in the
> `ui_open_studio_panel` enum (verified by [30 §4](30_TOOL_GUI_GAP_AUDIT_AND_PLAN.md), 2026-07-12).
> **Unshipped tail** (each tracked, none of it blocking): no Lane-B effect handler for
> `composition_authoring_run_*` (→ fixed by Wave 0 `W0-S4`); a now-false comment at
> `useStudioEffectReconciler.ts:10` (→ `W0-S4`); a missing `guideBodyKey` (→ `W0-S2`); and **no
> `compaction_failed` breaker** for its L3/L4 autonomous runs ([07S](07S_studio_agent_standard.md) §3/§10
> makes it MANDATORY — P1 Deferred row in `SESSION_HANDOFF.md`).
> *(Un-staled 2026-07-13, X-8. This now agrees with `00_OVERVIEW.md:109` and `00C:34`, which already said
> shipped — the three files no longer contradict each other.)*
> **Register:** "Cursor-for-novels" gap #4 (memory `writing-studio-fragmented-not-underbuilt`) — the last
> remaining item; #1 COHERENCE, #2, #3 LIVE-SYNC are all closed.
> **Mockup:** [`screen-studio-agent-mode.html`](../../../design-drafts/screens/studio/screen-studio-agent-mode.html) (v2, live-verified via chrome-devtools at desktop + 390px mobile)
> **Backend:** fully built, 0 existing frontend/MCP consumers —
> `services/composition-service/app/services/authoring_run_service.py` (1346 lines) +
> `services/composition-service/app/routers/authoring_runs.py`

## What this is

A human starts a bounded, multi-chapter autonomous drafting run. A server-side driver drafts chapters
one at a time against an approved plan, a critic scores each draft, and a human reviews + accepts/rejects
before closing the run. This spec covers the **first frontend surface** for it (a new Studio dock panel)
and a **new MCP tool surface** (per this session's CLARIFY decision — see D5).

## Ground truth (do not re-derive — cite this table)

| Fact | Source |
|---|---|
| Run FSM: `draft → gated → running → (paused ⇄ running) → report_ready → closed`; `running → failed` on unit failure | DB CHECK, `migrate.py:1000-1002`; `AuthoringRunStatus` Literal, `models.py:518-520` |
| Unit FSM: `pending → drafted → (accepted \| rejected)`; `pending → failed` | `models.py:552-554` |
| A unit = **one chapter**. No scene/beat sub-granularity server-side. | `authoring_run_service.py:1027-1052` |
| Only one run may be `gated`/`running`/`paused` per book at a time | partial unique index, `migrate.py:1024-1025`; `ActiveRunOverlapError`, `authoring_run_service.py:157-158` |
| **The driver does NOT wait for accept/reject.** It drafts every unit back-to-back, advancing unconditionally after each successful draft, until scope ends, budget is exhausted, or the critic returns `severe`. There is no `max_unreviewed_units` config. | `run_driver`, `authoring_run_service.py:1016-1175`, esp. 1120-1124 (advance), 1036-1051 (budget stop), 1172-1189 (critic stop) |
| **Accept/reject/revert-all are server-gated to `report_ready`/`failed`/`paused` only** (`_REVIEWABLE_STATUSES`, line 148, enforced at 830/859/897 in the router). Reviewing "as you go" requires the human (or the FE, see D4) to actively pause — confirmed this is the documented intended usage (class docstring, lines 59-87). | `authoring_run_service.py:148,830,859,897` |
| Pause takes effect **at the next unit boundary**, not mid-draft (re-claim check before each seam call, not during) | `authoring_run_service.py:1017-1026` |
| Rejecting a unit does **not** auto-fix/re-draft later units already drafted using its (rejected) content as context — only returns `downstream_unit_indexes` as an advisory warning | `authoring_run_service.py:85-87, 818-821, 847-885` |
| No retry endpoint. A `failed`/`report_ready` run can only `close` or `revert-all` (rejects every drafted/accepted unit in reverse order, auto-closes on full success) | router endpoint list, `authoring_runs.py` |
| REST-only today — **zero MCP tools exist** for authoring_run (empty grep of `app/mcp/`) | confirmed 2026-07-05, also noted in `frontend/src/features/studio/agent/useStudioEffectReconciler.ts:10` |
| Poll-only — no WebSocket/SSE for run progress | no `StreamingResponse` in `authoring_runs.py` |
| `plan_run_id` comes from the existing Plan-Forge subsystem (`plan_forge_service.py`, `plan_runs.py` repo). `GET /books/{book_id}/plan/runs` **already exists** and is book-scoped — no new BE endpoint needed for the plan picker. | `services/composition-service/app/routers/plan_forge.py:92-102` |
| A full revision diff viewer **already exists** (inline + side-by-side word-level diff) at the legacy `/books/:bookId/chapters/:chapterId/compare` route | `frontend/src/features/books/components/RevisionCompareView.tsx`, `RevisionDiff.tsx`, `wordDiff.ts` |
| `AuthoringRun` model fields (full list) | `models.py:523-547` — includes `breaker_state`, `driver_id`, `driver_heartbeat_at` (surfaced in mockup v2, dropped by nobody before this) |
| `AuthoringRunUnit` model fields (full list) | `models.py:557-571` — `critic_verdict` shape: `{severity: ok\|warn\|severe, summary, cost_usd[, detail]}` |

## Locked decisions

| # | Decision | Why |
|---|---|---|
| D1 | **One Studio dock panel**, id `agent-mode`, with 3 internal views (Runs list / New run / Mission control) exactly matching the mockup's nav-tabs | Same "one panel, tabbed views" shape as `ExtensionsPage`/`TranslationPanel` — avoids a 3-panel catalog footprint for one coherent flow. |
| D2 | **Diff viewer is panel-wrapped, not reinvented.** New thin Studio panel `chapter-revision-compare` wraps the existing `RevisionCompareView`/`RevisionDiff` (same pattern as `TranslationPanel.tsx` wrapping `TranslationTab` AS-IS) | A complete diff renderer (inline + side-by-side, word-level) already exists; the only gap is it's not Studio-dockable yet. Reinventing it would violate DOCK-7 (route-coupling) risk this track has flagged repeatedly (#14's 3 DOCK-7 findings). |
| D3 | **Plan picker reuses `GET /books/{book_id}/plan/runs` as-is** — no new BE endpoint. FE lists the book's plan runs, client-filters to ones with a usable/compiled artifact | Endpoint is already book-scoped; confirm the status vocabulary supports a clean client-side filter at BUILD — if not, a `status=` query param is a small, in-scope BE addition, not a new endpoint. |
| D4 | **"Auto-pause after each unit," default ON, moved SERVER-SIDE** (revised 2026-07-05 — the original client-poll design was found to silently no-op for any run started/resumed via MCP with no Studio panel open). New `authoring_runs.pause_after_each_unit` boolean column, default `true`; `run_driver`'s existing unit-boundary re-claim check (`authoring_run_service.py:1017-1026`) additionally checks this flag and pauses there (same code path as the existing budget/critic stops, D11) instead of continuing to the next unit. FE (D4a) and MCP `_start`/`_resume` (D4b) both read/set this flag; a run-header toggle flips it mid-run via `/pause`+flag-update or a small dedicated PATCH. The FE no longer does its own poll-and-pause race — it just reflects the server-enforced `paused` state | User's explicit CLARIFY choice 2026-07-05, revised same day after a follow-up edge-case pass found the client-only version didn't protect chat/MCP-started runs (the exact scenario D5 exists for). A poll-driven client mechanism cannot gate a run nobody is watching; moving the gate server-side makes "default ON" true regardless of entry point (UI or MCP). |
| D4a | FE: run-header toggle for `pause_after_each_unit`, set at New Run creation and flippable mid-run | Small UI addition once D4's server flag exists — no client polling logic needed anymore. |
| D4b | MCP: `composition_authoring_run_create`/`_start`/`_resume` all take an explicit `pause_after_each_unit: bool` arg (no default — matches D6's "no silent defaults on spend-adjacent tools") | Keeps chat-driven runs honest about whether they'll draft unattended; an agent asked to "run and keep going without asking me each time" must pass `false` explicitly, not rely on an assumed default. |
| D5 | **New MCP tool surface**, prefixed `composition_authoring_run_*` (matches this service's existing `composition_*` convention) | User's explicit CLARIFY choice 2026-07-05 — build MCP tools in v1, not deferred. Per the MCP-first invariant, agent-driven control of a multi-step process belongs behind MCP, not a bespoke path. |
| D6 | **Spend-triggering MCP tools (`_create`, `_gate`, `_start`, `_resume`) follow the propose→confirm pattern** (mint a `confirm_token`, actual effect fires through `confirm_action`) — same shape as `composition_generate`. Non-spend or halting tools (`_list`, `_get`, `_pause`, `_close`, `_accept_unit`, `_reject_unit`) execute directly. `_revert_all` also confirm-gates (destructive + irreversible from the UI, even though it's not itself a new spend) | Mirrors this repo's existing cost-gated-tool pattern (memory `cost-gated-mcp-tool-confirm-runs-engine`); an LLM agent must never autonomously commit new spend or an irreversible action without a confirm step, matching CLAUDE.md's risky-action posture. |
| D7 | **All MCP tool args take explicit `book_id`/`run_id`**, never inferred from ambient header context | Lesson from memory `gateway-drops-xprojectid-envelope` — ai-gateway MCP federation drops `X-Project-Id`; agent tools must take scoping ids as explicit args. |
| D8 | **FE hard-disables Accept/Reject outside `report_ready`/`failed`/`paused`**, with an inline reason (not just a disabled button) | Backend already 403s outside `_REVIEWABLE_STATUSES` — the UI must not let a user discover this via a failed request. Mockup v2 already implements this (fixed a v2-draft-1 bug where it didn't). |
| D9 | **Revert-all requires a confirmation modal** listing exactly which units will be reverted and to what. **The result renders a partial-failure state**, not just success — `revert_all` stops at the first restore failure, does not auto-close, and returns `reverted_unit_indexes`/`failed_unit_index`/`error` (`authoring_run_service.py:887-943`) | Destructive, irreversible from this UI — CLAUDE.md's risky-action posture. Mockup demonstrates the happy path only; a v3 pass or BUILD must add the partial-failure rendering — real, not hypothetical, since the service explicitly designs for this case. |
| D10 | **Keyboard triage in v1**: with the diff panel focused, `a` = accept, `r` = reject, `→`/`n` = next unit, `←`/`p` = prev unit; disabled (no-op) when the current unit isn't in a reviewable state | User's explicit CLARIFY choice 2026-07-05 — cheap, real UX win when reviewing several chapters in one sitting. |
| D11 | **Budget bar turns red at ≥85% spent**; `breaker_state`/`driver_heartbeat_at` surfaced as two health chips in the run header, colored by state (danger when breaker is `open` or heartbeat is stale) | This project has shipped the "worker died silently, status never updated" bug class before (see `sweeper-live-smoke-strand-recipe`, `worker-loop-under-one-amqp-message-cancel-clobber`) — mission control must not hide driver liveness. Exact staleness threshold (seconds since `driver_heartbeat_at`) is a BUILD-time detail — derive from the driver's actual heartbeat-write cadence in code, don't invent a number here. |

## Open items intentionally deferred (gate-checked, not silently dropped)

| ID | Item | Gate reason | Trigger to build |
|---|---|---|---|
| `D-AGENT-MODE-NOTIFY` | Cross-Studio notification when a backgrounded run finishes/pauses/fails while the panel isn't open | **Naturally-next-phase** — depends on whether a general Studio notification/badge system exists; if a general mechanism doesn't exist yet, building one just for this panel is out of proportion. Check at BUILD start whether Jobs panel (or elsewhere) already has a reusable badge/toast pattern — if yes, this may not even need deferring. | BUILD kickoff: audit for an existing notification primitive first; only defer if none exists. |

## Frontend panel plan

- **`agent-mode`** (new) — Runs list / New run / Mission control, per D1. Registers in `catalog.ts` like every other Phase 11-19 panel (palette + agent-openable, per D8/#00_OVERVIEW).
- **`chapter-revision-compare`** (new, small) — thin wrapper panel per D2, resolves `chapterId`/`fromRevisionId`/`toRevisionId` from `openPanel` params (same params-retargeting pattern as `wiki-editor`, #15), body = existing `RevisionCompareView`.
- Reuses existing: `planner` panel (D3, no new plan-creation UI), book chapters list endpoint (existing, book-service) for the New Run scope checklist.

## New MCP tools (backend scope, composition-service)

| Tool | Effect | Gating (D6) |
|---|---|---|
| `composition_authoring_run_list` | List runs for a book | direct |
| `composition_authoring_run_get` | Full run + unit report | direct |
| `composition_authoring_run_create` | Create a `draft` run (plan, scope, budget, level, allowlist, **`pause_after_each_unit`**) | confirm (explicit `budget_usd` AND `pause_after_each_unit` required, no defaults — D4b) |
| `composition_authoring_run_gate` | `draft → gated` | confirm |
| `composition_authoring_run_start` | `gated → running`; optional explicit `pause_after_each_unit` override | confirm |
| `composition_authoring_run_pause` | `running → paused` | direct |
| `composition_authoring_run_resume` | `paused → running`; optional explicit `pause_after_each_unit` override | confirm |
| `composition_authoring_run_close` | terminal close | direct |
| `composition_authoring_run_accept_unit` | `drafted → accepted` | direct |
| `composition_authoring_run_reject_unit` | `drafted → rejected`, restores pre-revision | direct |
| `composition_authoring_run_revert_all` | reject all drafted/accepted, reverse order | confirm |

All args include explicit `book_id` (D7). Exact JSON Schemas, response shapes, and the
`contracts/frontend-tools.contract.json`-equivalent for MCP (if this repo tracks one for
composition MCP tools — verify at BUILD) are a PLAN-phase detail, not decided here.

---

## Element-level GUI checklist (anti-omission control)

**Source of truth:** [`design-drafts/screens/studio/screen-studio-agent-mode.html`](../../../design-drafts/screens/studio/screen-studio-agent-mode.html) (v2). Every distinct behavior demonstrated there = one line below, grouped by **screen/interaction, not by React component** (per explicit instruction — a component boundary is an implementation detail chosen at BUILD, the mockup's behaviors are the contract).

**Rule (per memory `checklist-is-self-report-enforce-by-tests`):** a line is `[x]` only when a passing unit test and/or a live browser smoke proves its **effect**. Self-report ("I built the button") does not tick a line. This file gets re-walked against the running app at VERIFY, not rubber-stamped.

**Checklist walked 2026-07-05 via `/review-impl`** (3 parallel adversarial audits: standards gate, dockable-panel gate, exhaustive item-by-item cross-check against the mockup + this checklist) after BUILD. Ticks below are evidence-backed, not self-reported — file:line citations in the audit, summarized per line. One audit finding (keyboard no-op "untested") was itself verified WRONG on re-check (the test already existed, `MissionControlView.test.tsx:209-220`) — even an adversarial audit needs its own claims re-verified, not trusted blind.

### 1. Runs list view
- [x] Table lists runs for the current book: run id, scope label, status badge, spent/budget, created-at — `RunsListView.tsx:69-104`
- [x] Clicking a row opens Mission control at that run's actual current state — live `useAuthoringRun` fetch, not a fixture
- [x] "+ New run" button navigates to New Run config — `RunsListView.tsx:27-36`
- [x] "+ New run" is **blocked** with an explanatory banner when the book already has a `gated`/`running`/`paused` run — `RunsListView.tsx:39-50`, `useActiveAuthoringRun` pre-empts client-side (not relying on the create call's 409 alone)
- [x] Empty state (book has zero runs ever) — `RunsListView.tsx:62-66`, proven by `AgentModePanel.test.tsx:100-103`

**BE implied:** `GET /v1/composition/authoring-runs?book_id=` must support listing (confirm query param name at BUILD); FE must independently detect an active run to pre-empt the blocked-create case (don't rely on the create call's error alone — the button should already be disabled).

### 2. New run config
- [x] Plan picker lists the book's existing plan runs (via `GET /books/{book_id}/plan/runs`, D3) — `useNewRunForm.ts:19-27`
- [x] Plan picker has an empty state / CTA when the book has zero plan runs yet (link to the `planner` panel) — **fixed during `/review-impl`**: v1 build had the empty-state text but no CTA link; added `host.openPanel('planner')` button, `NewRunView.tsx`
- [x] Chapter checklist lists the real book TOC (not a hardcoded 8) — `useNewRunForm.ts:29-36`
- [x] Checking/unchecking a chapter updates the derived ordered "run order" list live — `useNewRunForm.ts:66-70`
- [x] Run order is actually reorderable — real move-up/down controls (documented substitute for the mockup's cosmetic drag handle, no new DnD dependency), `NewRunView.tsx:99-118`
- [x] Budget input accepts and validates a USD amount — `NewRunView.tsx:130-138`, `gateChecks.ts:35`
- [x] Level select persists the chosen value into the created run — `useNewRunForm.ts:112-121`
- [x] Tool allowlist is configurable — add/remove chips, `NewRunView.tsx:160-186`
- [x] "Run gate check" calls the real create+gate endpoints — `useNewRunForm.ts:108-133`, `AgentModePanel.test.tsx:141-153`
- [x] Gate-check failure rendered per-check and blocks submission — `GateChecklist.tsx` + `useNewRunForm.ts:101`, `AgentModePanel.test.tsx:155-165`

### 3. Run header (Mission control)
- [x] Ids (run_id/book_id) are real, both now carry a combined hover tooltip (`RunHeader.tsx`, fixed during `/review-impl` — book_id previously had none); level is real. No separate run "title" exists — the model has no such field (mockup's "Ch.1–6 revision pass" was illustrative, not a real field); documented, not a gap.
- [x] Status badge matches the 7 real states with correct color coding — `statusBadge.ts`
- [x] Action buttons are exactly the FSM-legal set for the current state — `fsm.ts:actionsForRunStatus`, `fsm.test.ts:8-21`
- [x] `breaker_state` chip reflects the real field, colored by severity, with friendly per-reason copy (fixed during self-review — was showing the raw DB string) — `RunHeader.tsx`, `fsm.ts:breakerSeverity`
- [x] `driver_heartbeat_at` chip reflects real staleness — `RunHeader.tsx`, `fsm.ts:isHeartbeatStale` (30s placeholder threshold, documented as tunable)
- [x] Budget bar reflects real `spent_usd`/`budget_usd`, turns red at ≥85% — `RunHeader.tsx`, `fsm.test.ts:42-47`
- [x] Error banner shows the real `error_message` when `failed` — `RunHeader.tsx`
- [x] Poll indicator — **fixed during `/review-impl`**: the exhaustive gap-check found this ENTIRELY MISSING from the v1 build despite the 5s poll already being real (`hooks.ts:39`); added a live "polling every Ns / last refreshed Ns ago / suspended" line to `RunHeader.tsx` reading `dataUpdatedAt`/`isFetching` off the query

### 4. Gate check panel
- [x] Renders only in `gated` state — `MissionControlView.tsx:51`
- [x] All 4 checks reflect live-recomputed real data (plan/scope/budget/allowlist) — `useMissionControl.ts:52-60` (client-side recompute from currently-fetched data, since backend `gate()` doesn't persist a structured result to replay — a reasoned, documented substitute, not a hardcoded pass)
- [x] A failing check disables Start with inline reason — `useMissionControl.ts:62-64`, `RunHeader.tsx`

### 5. Unit queue
- [x] Lists real units in real scope order with real status/cost/severity — `useMissionControl.ts:71-92`
- [x] "Current" unit distinguished — `UnitQueue.tsx:42,50-52`
- [x] Row click opens the diff/review panel — `UnitQueue.tsx:49`, `useMissionControl.ts:95-98`
- [x] Not-reached styling — `UnitQueue.tsx:52`, `useMissionControl.ts:80`

### 6. Diff / review panel
- [x] Shows the **actual chapter prose diff** via the same real diff data source as the classic compare route, not a summary-only view — `DiffReviewPanel.tsx:53-58,117-124`
- [x] "Open full editor diff" opens the real `chapter-revision-compare` panel with the correct `pre_revision_id`/`post_revision_id` — `DiffReviewPanel.tsx:134-142`, genuinely wired, not a stub
- [x] Critic verdict card + detail toggle — `DiffReviewPanel.tsx:145-167`
- [x] Cascade warning renders only when non-empty, advisory-only wording — `DiffReviewPanel.tsx:169-177`
- [x] Accept/Reject call real endpoints — `useMissionControl.ts:152-153`
- [x] D8 hard-disable with inline reason outside reviewable states — `DiffReviewPanel.tsx:180-192`, `fsm.ts:canReviewUnit`
- [x] Prev/Next navigate the real unit list incl. not-drafted/failed — `DiffReviewPanel.tsx:96-101`, `useMissionControl.ts:99-102`
- [x] Keyboard shortcuts incl. the no-op-on-illegal-state branch — `DiffReviewPanel.tsx:70-79`, `fsm.ts:keyToUnitReviewAction`, proven end-to-end by `MissionControlView.test.tsx:183-220` (all 3 cases: fire when reviewable, navigate, no-op + no API call when not reviewable)

### 7. Revert-all
- [x] Confirmation modal before calling the endpoint — `RevertAllModal.tsx`, `useMissionControl.ts:134-136`
- [x] Modal lists real affected units + from→to status — `useMissionControl.ts:130-132`, `RevertAllModal.tsx:56-68`
- [x] Confirm calls the real endpoint; Cancel is a plain `Dialog.Close`, no side effect
- [x] **Partial-failure path renders distinctly from full success** — `RevertAllModal.tsx:71-96` (`failed_unit_index`/`error`/`reverted_unit_indexes` shown separately), `api.ts:81-93` normalizes the 502 `REVERT_ALL_PARTIAL` body into the same shape

### 8. Auto-pause (D4, server-side)
- [x] `authoring_runs.pause_after_each_unit` column exists, defaults `true`, set at creation and updatable mid-run — `authoring_run_service.py:633,656-670`, `NewRunView.tsx:189-197`
- [x] `run_driver`'s unit-boundary check honors the flag, same code path as budget/critic stops, never fires after the last unit — `authoring_run_service.py:1206-1219`
- [ ] **Live-smoke across both entry points NOT executed** — deliberate, documented tradeoff (see SESSION_HANDOFF 2026-07-05): no compiled plan run existed on the dev DB to drive a full paid LLM round trip through either the Studio-UI or MCP-headless path; the mechanism itself is a pure state-machine check already covered by 12 targeted unit tests against the real code path. Tracked, not silently skipped.
- [x] FE run-header toggle reflects/flips the flag mid-run, no leftover client-poll-and-pause logic (confirmed removed, not just superseded on paper) — `RunHeader.tsx`

### 9. MCP tools (D5/D6/D7/D4b)
- [x] All 11 tools exist, registered in the live composition-service MCP server (confirmed via `mcp_server.list_tools()` inside the running container, not just a unit-test mock) — `server.py`
- [x] Spend-triggering tools + `_revert_all` mint a `confirm_token`; effect only via `confirm_action` — verified `mint_confirm_token` call sites
- [x] `_create` has no default `budget_usd` (now also bounded `gt=0`, added during `/review-impl`'s IN-4 finding) — `server.py`, `test_mcp_authoring_runs.py`
- [x] `_create` requires `pause_after_each_unit` explicitly; `_start`/`_resume` take it as an OPTIONAL override — matches the table (this line's own wording used to contradict the table until this pass corrected it)
- [x] All tool args take explicit `book_id`/`run_id` — confirmed throughout `server.py`
- [ ] **Chat-driven "pause my run" live smoke NOT executed** — same documented tradeoff as §8; covered instead by `test_mcp_authoring_runs.py`'s confirm-token-flow tests
- [ ] **Chat-driven unattended-drafting live smoke NOT executed** — same tradeoff

**Also fixed during this `/review-impl` pass, not part of the original checklist:** IN-4 (mcp-tool-io.md) bounds added to `budget_usd`/`limit`/`unit_index` (were previously unconstrained in the schema); OUT-5 `_list` now reports `has_more` instead of silently truncating at `limit`.

**Follow-up (2026-07-05, same day) — the 2 items above initially deferred were designed and fixed, not left open:**
- **IN-3 `tool_allowlist` is now a closed-set enum.** Defined `ALLOWLISTABLE_TOOLS` (`authoring_run_service.py`) — the 14 prose/outline-adjacent `composition_*` tools a drafting seam could plausibly invoke (admin/motif/canon-rule/authoring-run-control tools deliberately excluded). Single source of truth: both the REST (`AuthoringRunCreate.tool_allowlist`) and MCP (`_AuthoringRunCreateArgs.tool_allowlist`) schemas use `list[Literal[ALLOWLISTABLE_TOOLS]]`; `gate()` re-validates the same set as the shared backstop (the ONE chokepoint both entry points funnel through). Investigated first whether a live-registry validation precedent existed anywhere (chat-service's `enabled_tools`/`enabled_skills`) — it doesn't; every similar field in this repo accepts arbitrary strings today, so this is a genuinely new pattern, not a port of an existing one. 4 new tests (2 service-level `gate()`, 2 MCP-schema-level).
- **IN-5 has a real Python primitive now: `TolerantArgs`** (`sdks/python/loreweave_mcp/errors.py`), a sibling to `ForbidExtra` — `extra="ignore"` instead of `extra="forbid"`, same never-declare-identity guarantee either way. Ported the Go kit's `relaxAdditionalProps` *intent* (not its mechanism — Pydantic has no schema-level `additionalProperties` knob to relax). Migrated this feature's 7 arg models (list/get/create/gate-id/start/resume/unit) from `ForbidExtra` to `TolerantArgs` — the first real adopter. Deliberately did NOT touch `ForbidExtra`'s existing behavior or migrate any of the other ~15 pre-existing composition tools (`_WriteProseArgs`, `_GenerateArgs`, etc.) or the 3 other services using it (jobs/lore-enrichment/translation) — out of proportion for this pass; they keep their current strict behavior unless/until each is deliberately reconsidered. 3 new tests (2 SDK-level, 1 end-to-end through the real MCP tool). `docs/standards/mcp-tool-io.md` updated with a pointer so the next new Python MCP tool knows this primitive exists.
