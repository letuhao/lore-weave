# S6 — Canon, Quality & Progress — Detail Spec (build-ready)

> **Session:** S6 of the 8-session Writing-Studio completeness build.
> **Framework:** `docs/plans/2026-07-16-studio-completeness-8-session-orchestration.md` (§2 bar, §4 charter, §5 rules).
> **RUN-STATE:** `docs/plans/2026-07-16-studio-session-S6-RUN-STATE.md` (decisions/registers — re-read FIRST after compaction).
> **Reference (not truth):** `docs/specs/2026-07-01-writing-studio/31_quality_completion.md` covers 4/5 caps; this spec
> **reconciles it against verified HEAD `d3599d832`** and adds the 2 things it lacks (flywheel, the Work-creation CTA).
> **UI acceptance target:** `design-drafts/screens/studio/screen-quality-completion.html` (canon-rules · corrections · heal · progress)
> + `design-drafts/screens/studio/screen-flywheel.html` (flywheel — authored this session).

---

## 0 · The finding that shaped this spec (role-play → audit → verify)

A real web-novel author in the **Studio** today can operate only **2** of S6's capabilities: `quality-critic` (Analyze
button, on-demand) and `quality-canon` (read-only issues viewer). Everything else S6 owns — **author a canon rule, run
self-heal, see correction rates, track word-count progress, feel the canon-growth flywheel** — is reachable **only via the
legacy `ChapterEditorPage` (`/edit`, demoted but still routed) or by talking to the agent (MCP)**. That is the exact
*"cho có và rời rạc"* failure §2 exists to kill.

**Every S6 capability is a PORT, not a BUILD** — the FE components exist and pass tests, mounted on the legacy page; the
backend is ~fully built. What is missing is: **registration in the Studio dock**, a handful of **verified backend holes**,
**Lane-B agent-parity**, and — the prerequisite that gates all of them — a **GUI way to create a Work**.

### Reconciliation vs spec-31 / the HTML draft (VERIFIED against HEAD, do not re-trust the doc)

| Item | 31 / draft says | HEAD `d3599d832` (verified) | Action |
|---|---|---|---|
| BE-11a `POST /canon-rules/{id}/restore` | MUST-BUILD | ✅ **SHIPPED** (`canon.py:192-216`, `CanonRulesRepo.restore` `canon_rules.py:183`) | **DO NOT re-build** |
| BE-11b `GET /canon-rules?include_archived=true` | MUST-BUILD | ❌ absent (`canon_rules.py:92` filters `NOT is_archived`, no param) | build |
| BE-11c MCP `composition_canon_rule_restore` | MUST-BUILD | ❌ absent (`mcp/server.py` has create/update/delete only) | build |
| BE-9a `authoring_run_units.job_id` column | MUST-BUILD | ❌ absent | build (DDL + seam) |
| BE-9c `CORRECTABLE_OPERATIONS` allowlist | MUST-BUILD | ❌ absent | build |
| BE-P2 `composition_progress_goal` table + `PUT /progress/goal` | MUST-BUILD | ❌ absent (goal read from shared `work.settings.daily_goal`) | build |
| X-4 `handlers/compositionEffects.ts` (Lane-B) | MUST-BUILD | ❌ absent (only `authoringRunEffects.ts` registered) | build |

The draft is ~90% accurate; **only BE-11a shipped since it was written.** Everything else it flags is still real.

---

## 1 · Scope — 6 deliverables

| # | Deliverable | Verdict | New panel_id (category) |
|---|---|---|---|
| D0 | **Work-creation CTA** in the shared no-work gate | BUILD (reuse existing hooks) | — (extends `QualityWorkGate`) |
| D1 | **quality-canon-rules** — author the invariants the critic enforces | PORT + BUILD(Lane-B) + ENHANCE | `quality-canon-rules` (quality) |
| D2 | **quality-heal** — self-heal review gate (accept a subset, apply to prose) | PORT + BUILD(apply-seam) | `quality-heal` (quality) |
| D3 | **quality-corrections** — accept/edit/regen/reject rates | PORT + BUILD(BE-9a/9c) | `quality-corrections` (quality) |
| D4 | **progress** — words today/streak/goal/sparkline | PORT + BUILD(BE-P2) | `progress` (editor) |
| D5 | **flywheel** — the canon-growth reward home | PORT + retarget + contract-fix | `flywheel` (knowledge) |

**Out of S6 (owned elsewhere, do not build):** the correction *capture* seam (accept/reject → `generation_correction`) is
**S1's** — S6 only *reads* the stats (§4 seam ownership). The deep-link *targets* cast/kg-timeline/kg-graph are **S7's**.

---

## 2 · Sealed decisions (from CLARIFY — see RUN-STATE DECISIONS)

- **D-S6-BRANCH** — no branch switch; same-folder on `feat/context-budget-law` (§5 discipline).
- **D-S6-CANON-2-PANEL** — `quality-canon` (viewer, shipped) and `quality-canon-rules` (CRUD, new) are **two panels that
  deep-link each other by rule id**, not one merged panel.
- **D-S6-PROGRESS-CAT** — `progress` = category `editor` (a streak is not a quality judgment; QC-2).
- **D-S6-F1** — `flywheel` = category `knowledge` (sits with the kg-* panels it links into).
- **D-S6-F2** — publish-complete **auto-opens/flashes** the flywheel panel (reachable → *felt*).
- **D-S6-OQ1** — `propose_edit` Apply/Dismiss does **not** record a correction in v1 (no job_id; chat-service turn).
- **D-S6-OQ3** — self-heal cost preview = a descriptor on the **generic** `/actions/preview`+`/confirm` spine, no bespoke route.
- **D-S6-HEAL-APPLY-SEAM** — heal is chapter-scoped; apply via `applyHealedDocument(...)` (below), never the Chat buffer.
- **D-S6-WORK-CREATION-GUI** — **build** the Studio Work-creation CTA (D0), reusing existing hooks.

---

## 3 · D0 · Work-creation CTA (the prerequisite for everything else)

**Problem (verified):** `useCreateWork` / `usePendingWorkResolver` / `useGuidedFirstRun` are mounted **only** in legacy
`CompositionPanel.tsx`. In the Studio a Work is created only *implicitly* (PlanForge `_ensure_work`, import/decompose, agent
Chat-compose). A GUI-only user who opens any S6 panel on a fresh book hits `no-work` with **no self-service exit**.

**Design:** extend the shared `QualityWorkGate` (`QualityNoWorkState.tsx`) `no-work` branch with a **"Set up co-writer"**
action, reusing the **existing** `useCreateWork(bookId)` + `usePendingWorkResolver(bookId)` — including the knowledge-backfill
poll (`resolveWorkProject`, D-C16). No new backend; `POST /books/{book_id}/work` (`works.py:12`) already confirm-creates.

- **States:** idle → `useCreateWork.mutate()` → (a) project-backed Work returned → gate flips to `ready`; (b) pending
  null-project Work (knowledge outage) → `usePendingWorkResolver.start(work.id)` polls to backfill; (c) `failed` → retry.
- **No silent failure:** `onError → toast.error`; the `failed` poll state renders a retry, never a spinner-of-doom.
- **Reuse:** every S6 panel that gates on a Work renders this shared gate — one affordance, one name (SET-3). The
  `unavailable` branch (composition-service down) still shows the error state, never the CTA (would invite a duplicate Work).
- **Not in scope:** this is *create the Work*, not *the compose loop* (S1). It unblocks the prerequisite only.

**Tests:** gate renders CTA only on `no-work` (not `unavailable`/`loading`); click → `createWork` called; pending path drives
the resolver; error surfaces a toast. Live-smoke: fresh book → open `quality-canon-rules` → "Set up co-writer" → panel operable.

---

## 4 · D1 · quality-canon-rules  (PORT + Lane-B + ENHANCE)

**Port:** mount `CanonRulesPanel` + `CanonRuleForm` + `useCanonRules` (all exist, 6 tests) in a Studio dock panel behind
`QualityWorkGate`. Two additive props (`showArchived`, `onRestore`) + one new form field (`kind` — the inverse gap: the
agent can set it today, `types.ts:345` omits it for the human).

**Operability / CRUD (bar #1/#2):** create · edit (OCC `If-Match`) · archive · **restore** · list — every read has its write.
- **Restore is now REST-shipped** (BE-11a done) → wire `restoreCanonRule` in `api.ts` + a **"Rule deleted · Undo"** toast on
  delete success (delete returns the archived row id). Add the **archived section** (needs **BE-11b** `include_archived`).
- **412 OCC conflict (bar #4):** replace `onError → toast.error` with the conflict UI — show `current`, **keep the user's
  draft**, offer *re-apply onto v8 / keep theirs / discard mine*. Never a silent overwrite, never a bare toast.
- **ENHANCE (silent-failure fixes, verified):** `CanonRulesPanel.tsx:88` delete `remove.mutate(r.id)` has **no `onError`** →
  add one (mirror create/patch `:20-29`). Restore/undo closes the "A rule that no longer exists" dead-end (`QualityCanonPanel.tsx:174`).

**Deep-links (bar #6):** IN — `quality-canon` RuleRow "Edit rule" → `openPanel('quality-canon-rules', {focusRuleId})`.
OUT — the "⚠ N broken" badge → `openPanel('quality-canon', {focusRuleId})` (panel + param already exist). A focused id that
resolves to nothing says "anchored here, nothing broken"; to no rule at all says "that rule was archived — [show archived]".

**Backend build:** BE-11b (`include_archived` on list + repo), BE-11c (MCP `composition_canon_rule_restore` + `undo_hint` on
`composition_canon_rule_delete`). **Note the 3-schema-source FastMCP caveat** for the new MCP tool.

**Agent parity (bar #5):** see §9 (compositionEffects handles `^composition_canon_rule_`).

---

## 5 · D2 · quality-heal  (PORT + apply-seam)

**Port:** the M6 Polish review gate — `PolishPanel` + `usePolishProposals` (exist) in a dock panel behind `QualityWorkGate`,
mirroring `QualityCriticPanel`'s chapter-picker (keyset page + `chaptersTruncated` no-silent-cap, QC-10) + `ModelPicker`.
Backend fully built: `POST /works/{pid}/self-heal/propose` (202 + poll), engine `self_heal.py`.

**The one real integration — the apply-seam (D-S6-HEAL-APPLY-SEAM):** legacy `PolishPanel.onApply` is a **whole-document
replace** via `ChapterEditorPage.handleApplyPolish`; the Studio Compose is Chat-based and `ManuscriptUnitApi` has no
chokepoint for a full replace (`applyProposedEdit` only does insert/replace-selection). So **extend the chokepoint**:
`applyHealedDocument({ text, chapterId, expectedDraftVersion })` returning a **discriminated** `applied` / `no-editor` /
`stale` — **never a bare `false`** (silent-success is a bug). Replaces through the hoist → marks dirty → waits for ⌘S; the
heal never persists behind the author's back.

**Stale guards (data-loss class, bar #4):** `usePolishProposals` has carried `draftVersion` since day one and **nothing reads
it**. In a persistent dock tab beside a live dirty editor, applying stale proposals silently reverts newer typing. Render all
three guards, each **disabling Apply**: `stale·chapter` (proposals for ch.88, editor on ch.89) · `stale·version` (proposal
v12 < editor v14) · `stale·dirty` (unsaved edits) · plus `no-editor` (Rich/Raw panel closed).

**The critic↔heal link, closed (QC-8):** `QualityCriticPanel.tsx:80` mounts `QualityReportSection` **without `proposals`**, so
the `violation-has-fix` badge is unreachable dead code. Fix: `usePolishProposals` stores proposals in the **react-query cache**
`['composition','self-heal',pid,chapterId]` (`staleTime: Infinity`, mutation `setQueryData`s); `quality-critic` reads the same
key `enabled:false`. Cache-miss ⇒ `[]` ⇒ no badge — a false badge is impossible by construction; legacy return shape unchanged.

**ENHANCE:** remove the `onApply ?? (() => {})` no-op fallback (`CompositionPanel.tsx:861`) — make `onApply` required or disable
Apply when unwired, so the gate can never silently discard accepted edits.

**Cost (D-S6-OQ3):** paid action; cost preview is a descriptor on the generic `/actions/preview`+`/confirm` spine, not a 4th
`/self-heal/estimate` route. **X-1 dependency:** `quality-heal` mounts `ModelPicker` whose empty state renders `AddModelCta` —
must use `followStudioLink` (Wave-0 X-1), not a raw `<Link>` that tears down the dock. This is the DOCK-7 regression panel.

**Not in v1:** self-heal accept/reject is **not** a `generation_correction` (its job `operation='self_heal_propose'` is outside
BE-9c's allowlist; correcting *a fix* ≠ correcting *a draft*). QC-5/OQ-2.

---

## 6 · D3 · quality-corrections  (PORT + BE-9a/9c)

**Port:** extract `CorrectionStatsTable` from `QualityPanel` into its own file and mount it (do **not** mount `QualityPanel`
whole — its other half `BookPromiseCoverageSection` already ships as `quality-coverage`, a paid pass; mounting whole = one
paid button twice, F-Q11). Display-only per charter; the capture seam stays S1's. `GET /works/{pid}/correction-stats` exists.

**The number is wrong today (BE-9c) — ship the fix in the SAME milestone or ship a lie with a chart on it:**
`correction_stats` groups by `j.mode` over **every** `generation_job`; `mode='auto'` is the default for `self_heal_propose`,
`quality_report`, `promise_coverage`, `plan_*`, etc. — none correctable — so the accept-rate reads falsely high. Fix:
- **BE-9c** — an **operation allowlist** on the denominator: `CORRECTABLE_OPERATIONS = ("draft_scene","draft_chapter",
  "stitch_chapter")`; `j.operation = ANY(CORRECTABLE_OPERATIONS) AND NOT selection_edit`. ⚠ **F-Q3a — the allowlist is exactly
  these three.** `mode` is a per-request `Literal["cowrite","auto"]` over the *same* op, so `draft_scene`+cowrite IS already
  listed; the only exclusively-cowrite ops are rewrite/expand/describe = selection edits, which the `NOT selection_edit`
  exclusion already removes. An agent told to "enumerate the cowrite ops from engine.py" will grep, find that Literal, add all
  three, and **silently revert this fix**. Do not. The list is three ops; `NOT selection_edit` **stays** (added-to, never replaced).
- **BE-9c′** — close `operation` to a `Literal` on both draft bodies (`engine.py:98,141` — today a client-settable free string);
  until closed the allowlist is a filter, not a guarantee.

**The load-bearing half is the capture, not this panel (BE-9a):** `…/units/{i}/reject` already restores the pre-run revision
(a textbook `kind='reject'`) and `…/accept` after a human edit is a `kind='edit'` — **thrown away every time** because
`generation_correction.job_id` is `NOT NULL` and `authoring_run_units` has **no job_id column** (`EngineDraftingSeam` reads
`payload["job_id"]` at `:377`, discards at `:391/:408`). BE-9a = **`ALTER TABLE authoring_run_units ADD COLUMN job_id UUID`
(nullable, never backfill a guess)** + `DraftOutcome.job_id` + the driver persist + BE-9b (`composition_record_correction`
MCP + a fire-and-forget write inside accept/reject). This is what makes the wave **L, not M**.

**States:** cold-start ("No AI drafts yet"); one-mode-only renders `—` not `0%` (a zero is a measurement, a dash an absence —
same lie class as the denominator). **Ownership:** the `authoring_run_units` DDL/seam touches S1's producer — coordinate; if S1
owns that seam, S6 files the correction-capture as a cross-charter row and ships the *display* + BE-9c now.

---

## 7 · D4 · progress  (PORT + BE-P2)  — category `editor`

**Port:** `ProgressPanel` (most-complete of the three) — today/streak/book-total, editable daily-goal, 7/30 sparkline with
goal line, by-chapter (BE-P1, droppable). Backend `GET/POST …/progress*` exists (`progress.py`). Gate on `useQualityWork`.

**BE-P2 — the tenancy fix (a real defect, not a preference):** the goal is read from `work.settings["daily_goal"]` — a
**shared per-book row every EDIT grantee can write** — while word counts are **per-user** (`composition_daily_progress` PK
`(user_id, project_id, chapter_id, snapshot_date)`). ⇒ *Alice sets 2,000; Bob's panel shows Alice's goal and measures Bob
against it.* "Would two users want different values? yes ⇒ user setting" (CLAUDE.md User Boundaries). Fix:
- New per-user table **`composition_progress_goal(user_id, project_id, daily_goal, updated_at, PK(user_id, project_id))`** —
  **no `book_id`** (neither sibling has one; the grant is gated at the router by `_require_work` before the repo; a `book_id`
  here would be written-and-never-read). `PUT …/progress/goal`.
- **SET-1:** `GET /progress` returns `daily_goal_source: 'user' | 'work_legacy' | 'none'` and the panel **renders it** (the
  effective value AND its tier). Read-through fallback to `work.settings.daily_goal` so no existing user loses a goal; the
  **writer only ever writes the new table** (close the legacy window in the writer, not by rewriting base schema).
- This **deletes** the current `useSetDailyGoal` full-blob `patchWork` caller (which replaces the whole settings blob with no
  If-Match, `works.py:311` — a lost-update window) — BE-P2 closes it without waiting on BE-18.
- **No new env flag** — a per-user choice behind a global `*_ENABLED` is the exact abuse CLAUDE.md names.

**States:** legacy-goal (came from shared settings; "setting it now makes it yours"); cold-start ("No words yet"); no-goal
(bar + goal line simply absent, `ProgressPanel.tsx:65,104` — no fabricated 2,000 default, `source:"none"`).

**No MCP tool for progress, and none proposed** — progress is a *personal stat*; the agent recording words on the user's behalf
would corrupt their own signal. A deliberate non-gap; do not "fix" it.

---

## 8 · D5 · flywheel  (PORT + retarget + contract-fix)  — category `knowledge`

Full design: `design-drafts/screens/studio/screen-flywheel.html`. **Zero backend build.**

**Port:** `FlywheelPanel` + `useFlywheel` (exist). Read `GET /projects/{id}/flywheel` (knowledge-service, `FlywheelDeltaResponse`);
the write side (publish → extraction → delta) is composition `approve.py` + `engine/delta_flywheel.py` — so "+N added" is real.

**The one real porting decision — deep-link retarget:** Lane-A wires `onOpenCast/Timeline/Relations` to
`CompositionPanel.selectTab(...)`; the dock has **panels, not tabs**. Retarget:

| callback | Studio port |
|---|---|
| `onOpenCast(name?)` | `host.openPanel('cast', { focusName })` |
| `onOpenRelations()` | `host.openPanel('kg-graph')` (OQ-F4 — vs a relations view; resolve against S7) |
| `onOpenTimeline()` | `host.openPanel('kg-timeline')` |

Porting the render without retargeting ships **3 dead chips**. Targets are **S7's panels** — **cross-session dependency**: if a
target isn't registered yet, that chip is **disabled with a reason**, never silently inert; track the tail.

**Contract-row fix:** `legacyParityContract.test.ts:44` maps `flywheel → 'quality-corrections'` (conflation — different data
source, different question). The port gives flywheel its **own id** and rewrites the row `flywheel → 'flywheel'`.

**F2 hand-off (refined by E2/E3):** the reward fires on **extraction-complete** (delta ready), not on publish-confirm (delta
not produced yet). And it distinguishes *who published*: an **FE-initiated** publish (the human pressed Publish in the Studio)
→ **auto-open** the flywheel; an **agent/background** publish → **flash/toast-with-link** ("canon grew +12 →"), never force-open
a dock panel and hijack the human's focus. So F2 is: on extraction-complete, if the last publish was FE-initiated → open;
else notify-with-link.

**Error≠empty (QC-F3):** today `isError || !has_delta` collapses into one empty message. Distinguish "we could not look"
(knowledge down) from "nothing grew", like the quality panels' `unavailable ≠ empty` gate.

**Agent parity:** `^composition_publish$` → invalidate `['composition','flywheel',pid]` (a predicate on the shared handler, §9).

---

## 9 · X-4 · compositionEffects — the shared Lane-B handler (BUILD)

One new `frontend/src/features/studio/agent/handlers/compositionEffects.ts`, registered in the barrel, several predicates:

- `^composition_canon_rule_` → invalidate `['composition','canon',pid]` + the violations key (D1).
- `^composition_record_correction$` → invalidate `['composition','correction-stats',pid]` (D3, once BE-9b lands).
- **flywheel refresh keys on EXTRACTION-COMPLETE, NOT `composition_publish` (E2).** For a normal book, publish enqueues an
  async knowledge-service extraction; the delta lands *after* the publish tool returns. Invalidating on `composition_publish`
  would refetch an empty/stale delta. The predicate must match the **extraction-done** signal (the knowledge extraction job
  completion notification / effect). The derivative path (`approve.py`) is synchronous — its own effect can invalidate directly.
  Exact signal wiring is an M5 design detail; the invariant is: **never key flywheel on the publish confirm.**

Delete the stale `useStudioEffectReconciler` comment ("authoring_run has no MCP tools … no Studio consumer to go stale" — it
has both). Removes the PENDING rows in `effectCoverage.contract.test.ts:113`. This is the agent-parity leg (bar #5) for the
whole session — an agent write refreshes the human's open panel.

---

## 10 · Reachability / registry plan (bar #3 — every panel, all four places)

For each new id (`quality-canon-rules`, `quality-heal`, `quality-corrections`, `progress`, `flywheel`):
1. **`catalog.ts`** — a row in the **S6 block** (`// ── S6 · …`, line ~314), each with `guideBodyKey` + correct `category`.
2. **`frontend_tools.py`** `ui_open_studio_panel` `panel_id` **enum** entry.
3. **`contracts/frontend-tools.contract.json`** — regen with `WRITE_FRONTEND_CONTRACT=1 pytest`.
4. **i18n** `en/studio.json` — title/desc/guideBody keys (+ the 18-locale stubs; parity is a convergence gate).
5. Command palette is automatic from `catalog.ts` (non-hidden). Add the 3 quality ids as cards to `QualityHubPanel` `CARDS`
   (`progress` is **not** a card — category editor; `flywheel` is a knowledge-hub concern, not a quality card).

`panelCatalogContract.test.ts` asserts **enum == palette-openable == contract**; all move together. `CATEGORY_ORDER` already
includes `quality` (X-2 done) and `knowledge`/`editor` — no category work.

---

## 11 · Milestone / slice plan (self-driven; `/review-impl` at each panel close)

Ordered by value + dependency. Each slice: build → scoped tests → `/review-impl` → live-browser smoke → commit small.

| M | Slice | Ships |
|---|---|---|
| M0 | **X-4 compositionEffects** + **D0 Work-CTA** | the two shared unblockers (stale-guard for all; operable-for-fresh-book) |
| M1 | **D1 quality-canon-rules** (+ BE-11b/11c, ENHANCE, 412 UI) | the highest-value read↔write closure |
| M2 | **D3 quality-corrections** (+ BE-9c/9c′ now; BE-9a/9b coordinated w/ S1) | the true number |
| M3 | **D2 quality-heal** (+ apply-seam, stale guards, QC-8 critic link, X-1 dep) | the apply gate |
| M4 | **D4 progress** (+ BE-P2 tenancy goal) | the write-only loop closes |
| M5 | **D5 flywheel** (+ retarget, contract-fix, F2 hand-off) | the loop reward (paced after S7 registers targets) |

**Cross-charter coordination (file rows, don't block):** BE-9a `authoring_run_units.job_id` touches **S1's** producer seam;
D5 deep-link targets are **S7's** panels. Decompose: ship the buildable-now slice + track the genuinely-external tail (repo
law — "missing infrastructure is not blocked").

---

## 12 · Test + evidence plan (bar #7)

- **Unit:** each panel's port keeps its existing tests green + new tests for the added surface (412 UI, restore/undo, apply-seam
  discriminated result, stale guards, BE-9c allowlist denominator, BE-P2 source-tier, Work-CTA states, compositionEffects
  invalidations, flywheel retarget + error≠empty).
- **Backend:** BE-9a/9c/11b/11c/P2 each with repo + router tests; the allowlist test asserts a PlanForge pass does **not** inflate
  the denominator (checklist ⇒ test the effect).
- **Contract:** `panelCatalogContract` + `frontend-tools.contract.json` regen green; `effectCoverage.contract.test` PENDING rows
  removed; `legacyParityContract` flywheel row = `'flywheel'`.
- **Cross-service live-smoke (≥2 services):** fresh book → **Set up co-writer** → author a canon rule → agent updates it (panel
  refreshes via Lane-B) → run self-heal on a chapter → apply a subset → publish → **flywheel auto-opens with +N**. Paste the run.
  This is also the S6 slice of the loop-③ smoke.

---

## 13 · Deferred / non-goals (tracked, not dropped)

- `propose_edit` correction capture (OQ-1, cross-service, chat-service turn has no composition job_id) → later.
- Self-heal accept/reject as a correction signal (OQ-2) → different signal from a draft correction; not v1.
- Agent `dismiss-violation` parity (OQ-4) → inverse gap, filed.
- Flywheel range/"this arc" delta (OQ-F3) → BE ask; v1 = last-publish (matches the route).
- BE-P1 by-chapter progress → droppable.

---

## 14 · Edge cases (design REVIEW pass — verified against HEAD)

| # | Edge | Verdict / resolution |
|---|---|---|
| **E1** | **Heal stale·version guard needs the live editor's draft version.** | ✅ CLEARED — `ManuscriptUnitProvider` exposes `version` (`draft_version`, `:47/:167`). `applyHealedDocument` compares `expectedDraftVersion` (captured when Polish ran) vs live `version`; `version === undefined` (no editor) → the `no-editor` result, not `stale`. The save leg already carries `expected_draft_version` OCC (`:222`). |
| **E2** | **Flywheel delta is produced by async extraction AFTER publish.** Keying refresh/F2 on `composition_publish` shows an empty delta. | ✅ RESOLVED in §8/§9 — key on **extraction-complete**, never the publish confirm. Derivative path (`approve.py`) is synchronous; normal path is an async knowledge job. Exact signal = M5. |
| **E3** | **Auto-opening flywheel on an AGENT/background publish hijacks the human's focus.** | ✅ RESOLVED in §8 — FE-initiated publish → auto-open; agent/background → flash/toast-with-link. |
| **E4** | **Canon 412 "re-apply my edit onto v8" implies a 3-way merge the UI can't do** for a single text field. | Wording precision: it is **resend-with-acknowledged-version** (POST my full draft with `If-Match: 8` = last-writer-wins, but the user has *seen* v8), not a merge. UI copy must not promise a merge. Options stay: *re-apply mine (as v9) · keep theirs · discard mine · cancel*. |
| **E5** | **Ambiguous multi-Work book** (`candidates` with >1): `useQualityWork` takes the FIRST candidate. Quality panels might bind the wrong Work (e.g. a what-if branch Work vs the canon Work). | Pre-existing convention across ALL consumers (`useSceneBrowser`, `CompositionPanel`, `usePublishGate` all take first). **Non-gap for S6** — S6 inherits it; changing it is a cross-cutting decision, not this session's. Note filed. The D0 CTA only appears when there are ZERO works, so it never creates a duplicate against `candidates`. |
| **E6** | **BE-9a null-job units** (pre-migration `authoring_run_units.job_id IS NULL`) record no correction; the run report must say so, not silently drop. | The honest "N units couldn't capture a correction" surface belongs to **S1's authoring-run report** (S1 owns the producer seam). Cross-charter row — S6 ships the display + BE-9c; the capture + its skip-reporting coordinate with S1. Never backfill a guess (a wrong job_id attributes the author's rejection to someone else's generation). |
| **E7** | **Deep-link params `focusRuleId` / `focusName` on `ui_open_studio_panel`** — if not contract-declared, the resolver can silently no-op an unknown param (the `panel_id="editor"` silent-no-op bug class). | Design note: the deep-link params must be part of the frontend-tools contract (IN-* rules) and the resolver must **surface** an unresolvable focus (the panel opens + says "anchored here, nothing broken" / "that rule was archived"), **never silently no-op**. `panel_id` stays enum-closed; the focus param is optional with a defined no-param behavior (so each id is palette-openable bare, not `hiddenFromPalette`). |
| **E8** | **i18n 18-locale parity** reds until the new keys are stubbed in all locales. | Known — en authored + 18-locale stubs; parity is a **convergence** gate, not a per-slice blocker (§12). |
| **E9** | **BE-P2 goal source change mid-week** — a user on a legacy shared goal who "makes it yours": the copied value is identical, so no streak/hit-rate discontinuity; a `source:'none'` user has no goal line and the sparkline renders neutral (no hit/miss coloring) — already handled (`ProgressPanel.tsx:65,104`). | ✅ No new work. Read-through fallback + writer-only-new-table (close the legacy window in the writer, not base schema). |

**REVIEW verdict:** no blocker found; two real corrections folded in (E2 flywheel timing, E3 F2 intrusiveness). Three cross-charter
coordination rows (E5 take-first, E6 null-job report, D5 S7 deep-link targets) are filed, not blocking. Spec is build-ready.
