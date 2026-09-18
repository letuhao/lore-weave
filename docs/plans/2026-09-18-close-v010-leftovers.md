# Plan — Close the v0.1.0 leftovers

- **Date:** 2026-09-18
- **Branch:** `fix/v0.1.0-release-gaps` (no new branch — the PO chose to stay on it; uncommitted work lives here)
- **Spec:** [`docs/specs/2026-09-18-close-v010-leftovers.md`](../specs/2026-09-18-close-v010-leftovers.md) — options A–D
- **Idea:** [`docs/ideas/2026-09-18-close-v010-leftovers.md`](../ideas/2026-09-18-close-v010-leftovers.md) (IDEA-001)
- **Builds on:** [`2026-09-13-green-honestly.md`](2026-09-13-green-honestly.md) (201 passed · 0 failed · 0 skipped) and [`docs/reports/2026-09-13-ship-handover.md`](../reports/2026-09-13-ship-handover.md)
- **Size:** `workflow-gate.sh size L 16 8 3` → **L**, no phase may be skipped.

> Nothing here ships anything. The tag is still the PO's (AC-11).

## Original Request

Leftovers spec, this branch (Recommended)

## Settings

- **Testing:** yes — every product fix is proven by re-breaking it (Rule 1).
- **Logging:** verbose — DEBUG on every new branch, INFO on every outcome a person would ask about, WARN on every best-effort failure.
- **Docs:** yes — mandatory docs checkpoint at completion (T14).

## CLARIFY — the PO's answers (2026-09-18)

| # | Question | Answer | Effect on this plan |
|---|---|---|---|
| Q1 | Scope and branch | The leftovers spec, on this branch | Lanes A–E below |
| Q2 | MCP `book_create` has no user bearer | **Provision on open**, as today | No change to MCP; a Known issues entry (T14) |
| Q3 | L5, the duplicated critic | **Hide the inline critic** while the critic panel is on screen | Lane E (T13) |
| Q4 | The 298 half-provisioned books | **Backfill on the owner's next sign-in**, with their own bearer | Lane D (T10–T12) |
| Q5 | L6, ship | Still the PO's | AC-11, never ticked by a row |

## What the code says (reconnaissance, 2026-09-18)

These premises are re-verified before each lane starts (Rule 7), not trusted from this table.

- **L1 — the ladder cannot see truncation.** `chat()` raises `PlanForgeLLMError("LLM job unusable: truncated")`
  at `engine/plan_forge/llm.py:164-165` when `unusable()` returns `"truncated"` (`llm_budget.py:360-361`;
  `plan_forge_chat` is STRUCTURED 12000/12000, so truncation is always fatal). The first `client.chat()`
  in `_parse_with_repair` (`propose_llm_async.py:86-89`) sits **outside** the ladder loop (`:91`), and the
  ladder only triggers on `_is_degenerate` = ≥12000 **characters** after a parse failure. A real loop
  ends at `finish_reason == "length"` and throws before the ladder runs.
- **L1 — the test fake cannot express it.** `_MockLLMClient` (`tests/unit/test_plan_forge_llm.py:24-34`)
  returns no `finish_reason`, so no existing test can see this path.
- **L1 — wall time is unbounded, and the sweeper can double-run.** No deadline on a plan-forge step;
  `sweep_once` (`worker/job_consumer.py:440-463`) re-runs a `running` job whose `updated_at` is >900s old
  (`config.py:34-35`). Up to 3 attempts × 12k tokens on `analyze` and again on `materialize` can pass 900s.
- **L3 —** `CRITIQUE_TIMEOUT_MS = 240_000` at `frontend/src/features/composition/api.ts:96` (used at `:755`);
  the default ceiling is 20s (`API_REQUEST_TIMEOUT_MS`).
- **L4 —** REST `createBook` (`services/book-service/internal/api/server.go:731-797`) commits at `:792`
  and has the incoming `Authorization` on `r`, unread. `fetchStructureWork` (`book_structure.go:302-321`)
  forwards the raw header, but uses `http.DefaultClient` with **no timeout**. `POST /work`
  (`composition-service/app/routers/works.py:154-281`) is idempotent and concurrency-safe: knowledge
  dedupes under a per-(user, book) advisory lock, the Work insert catches `UniqueViolationError`, and pending
  rows are capped by a partial unique index.
- **L4 — OQ-1** (`works.py:221-225`): knowledge auto-provision stays owner-only; the caller's own bearer is
  forwarded; no owner-identity token is minted. Every lane here uses **only the caller's bearer**.
- **Backfill —** nothing runs on sign-in today (`LoginPage.tsx:56-77` only sets tokens and navigates); no
  endpoint lists a user's unprovisioned books; `useEnsureWork` runs only from `StudioFrame.tsx:52`.
- **L5 —** the same `CriticFlags` renders inline (`ComposeView.tsx:256`) and in `CriticPanel`
  (`CriticPanel.tsx:73-78`, docked via `CompositionPanel.tsx:850`). Placement comes from the generic
  workspace layout (`dock.ts` helpers, `slot(id)` at `CompositionPanel.tsx:423-439`). The inline copy
  carries the C26 override gate (`compose-override-gate`, `compose-override-regenerate`).

## Acceptance criteria

| AC | Must be true | Verified by | Rows | Status |
|---|---|---|---|---|
| **AC-1** | A plan-forge step whose output is truncated is regenerated through the ladder, and truncated text never reaches the repair path | `test_plan_forge_llm.py` truncation cases + Cycle bite (break: restore the raise-before-ladder; the cases go red) | T1, T2 | ✅ met — Cycle 1: 3 bites, each red for the right reason and green on restore |
| **AC-2** | On 30 real plan runs, final failures are fewer than today's 2 of 31 | `llm_jobs` query pasted in the cycle (`job_meta.extractor`, `finish_reason`) on rebuilt images | T4 | ✅ met — Cycle 4: 30/30 proposed, 0 final failures; the one truncation regenerated live |
| **AC-3** | A long ladder never lets the sweeper start a second copy of the same plan job | unit test on the heartbeat + `generation_job` row history from T4 | T3, T4 | ✅ met — Cycle 1 bite; Cycle 4: 30 runs, 30 `generation_job` rows, none started twice |
| **AC-4** | The 240s critic ceiling is proven by re-breaking it on a real cold model load | `composition-generate.spec.ts` run pasted twice: 20s ceiling red, 240s green | T5 | ✅ met — Cycle 4, through the stand-in slow provider (the real cold load finished under 20s) |
| **AC-5** | A book created through REST has its knowledge project within 5s without anyone opening it, and a provisioning failure never fails the create | Go handler tests with an `httptest` composition fake + live T9 query | T6, T7, T9 | ✅ met — Cycle 2: 4 bites; live project 0.7s after create, owner-matched |
| **AC-6** | Creating a book and opening it at once yields exactly one Work and one knowledge project | live race run on `lw-iso` with row counts pasted | T8 | ✅ met — Cycle 2: 10/10 books, three racing callers each, exactly 1 Work + 1 project |
| **AC-7** | After an owner signs in, every book they own has a knowledge project; no other user's book is touched; only the owner's bearer is used | Go endpoint tests + vitest trigger test + live T12 counts | T10, T11, T12 | ✅ met — Cycle 4: 105/105 of the owner's books after sign-in; another owner's 65/77 untouched |
| **AC-8** | The critic result appears once on screen, and the override gate stays reachable | `ComposeView.test.tsx` layout cases + `composition-generate.spec.ts` | T13 | ✅ met — Cycle 3 (unit, 3 bites) + Cycle 7 (`composition-generate` green in the full run, through the Studio) |
| **AC-9** | Every item left open ships with a Known issues entry: what, who, workaround | `scripts/changelog-gate.py` + the `[0.1.0]` section text | T14 | ✅ met — Cycle 5: three Known issues entries (what, who, workaround); both gate modes green, release mode bitten |
| **AC-10** | The whole suite is green on rebuilt images: 0 failed, 0 skipped | full Playwright + unit run pasted, image ids listed | T15 | 🚧 partial — Cycle 7: run 3 **201 passed, 0 failed, 0 skipped**, but runs 1–2 had 4 failures that pass alone and whose cause is not confirmed |
| **AC-12** | No route or link reaches the retired chapter editor; an old URL lands on the same chapter in the Writing Studio | `RetiredChapterEditorRedirect.test.tsx` (redirect + a source scan) + the 5 re-pointed view tests | T16, T17 | ✅ met — Cycle 4 (app, bitten) + Cycle 6 (all 8 migrated specs green through the Studio) |
| **AC-11** | The PO has decided GO or NO-GO for v0.1.0 | the PO's own words quoted in this plan | | ❓ unknown |

## Board

### Lane A — plan-generation truncation (L1)

- [x] **T1** — **A truncated plan-forge job raises its own error type** (Cycle 1)
  - Files: `services/composition-service/app/engine/plan_forge/llm.py`, `tests/unit/test_plan_forge_llm.py`.
  - Add `PlanForgeTruncated(PlanForgeLLMError)`. `chat()` raises it when `unusable()` returns `"truncated"`;
    every other unusable reason keeps raising `PlanForgeLLMError`. The exception carries **no content** —
    that is what keeps the no-repair guard true by construction. Keep the guard comment, updated.
  - Callers outside the ladder (`plan_forge_service.py:1445` interpret, the worker's `_BUSINESS_ERRORS`)
    see a subclass and behave exactly as today.
  - Extend `_MockLLMClient` to script a `finish_reason` per response, so truncation is expressible.
  - Log: WARN `plan_forge.truncated step=<step> job_id=<id> tokens=<n>`.
- [x] **T2** — **The ladder treats truncation as degenerate: regenerate, never repair** (Cycle 1)
  - Files: `engine/plan_forge/propose_llm_async.py`, `tests/unit/test_plan_forge_llm.py`.
  - Move the first `client.chat()` inside the attempt loop. Catch `PlanForgeTruncated` on every attempt
    and route it to the existing regenerate branch (escalated `frequency_penalty`, raised temperature,
    `<step>_retryN`). On the last attempt raise the existing actionable error, naming truncation.
    The repair call is unreachable from truncation.
  - Tests: truncated→ok gives steps `[analyze, analyze_retry1]`; truncated×3 raises with **no** `_repair`
    step; a small unparseable response still goes to repair (existing case stays green).
  - Bite: restore the raise-before-ladder; the truncated→ok case goes red. Restore; green.
  - Log: INFO `plan_forge.regenerate step=<step> attempt=<n> reason=truncated|degenerate penalty=<p>`.
- [x] **T3** — **The sweeper cannot double-run a job that is still regenerating** (Cycle 1)
  - Files: `worker/job_consumer.py` and/or `propose_llm_async.py`, a unit test.
  - First verify the premise: what touches `generation_job.updated_at` while a plan job runs. If nothing
    does between attempts, touch it (heartbeat) before each ladder attempt, through the `cancel_check`
    seam or an equivalent callback. Do not raise the 900s sweep timeout — that trades one bug for slower
    recovery of real crashes.
  - Test: a fake ladder with 3 attempts updates the heartbeat 3 times; a job with a fresh heartbeat is
    not picked by `sweep_once`.
  - Log: DEBUG `plan_forge.heartbeat job_id=<id> attempt=<n>`.
- [x] **T4** — **Measure on real runs** (Cycle 4)
  - Rebuild **both** composition images (`composition-service` and `composition-worker`, Rule 4) on `lw-iso`.
  - 30 real plan runs through the API. Count final failures, regenerations and their `finish_reason`
    from `llm_jobs`, and check `generation_job` for any job that started twice.
  - Drop condition (from the spec): more than half the regenerations also truncate, or final failures do
    not fall below 2 of 31. Then A goes to Known issues and the soak (IDEA-001 idea 11) is proposed.

### Lane B — prove the critic ceiling (L3)

- [x] **T5** — **Re-break the 240s critic ceiling on a real cold load** (Cycle 4 — via the stand-in provider)
  - No product change. Register a second chat model that is **not loaded**, set it as the Work's critic
    (`setWorkCriticModel`, `helpers/api.ts:479`), run `composition-generate.spec.ts`.
  - Break: `CRITIQUE_TIMEOUT_MS` removed (20s default) → the critic card fails with `Request timed out`.
    Restore: 240s → it renders. Rebuild the frontend image both times.
  - Constraints: one strong model at a time; never control LM Studio by hand — the product's own
    request causes the load, and LM Studio unloads the other model itself.
  - If the cold load finishes under 20s, this cannot bite: switch to a deliberately slow stand-in provider
    on the throwaway stack (IDEA-001 idea 16) and say so in the cycle.

### Lane C — provision at creation (L4)

- [x] **T6** — **One best-effort helper that asks composition for the Work, with the caller's bearer** (Cycle 2)
  - Files: `services/book-service/internal/api/` (new `composition_provision.go` + `_test.go`).
  - `provisionCompositionWork(ctx, bookID, bearer)`: `POST {COMPOSITION_SERVICE_URL}/v1/composition/books/{id}/work`
    with the raw `Authorization` value. Its **own** `http.Client` with a short timeout (the value is a
    DESIGN decision; default proposal 3s). Empty bearer or base URL → no call. Never returns an error the
    caller must handle.
  - Tests (`httptest.NewServer`, as in `parts_import_test.go:26-34`): 200/201 ok; 500 logged, no error;
    timeout honoured; empty bearer makes no request; the bearer arrives unchanged.
  - Log: INFO `book.provision ok book_id=<id> status=<code> ms=<n>`; WARN on failure with status/error.
- [x] **T7** — **REST create calls the helper after commit** (Cycle 2)
  - File: `server.go` `createBook`, between `tx.Commit` (`:792`) and `getBookByID` (`:796`).
  - Pass `r.Header.Get("Authorization")`. The response stays 201 whatever the helper does.
    MCP `book_create` is **not** changed (Q2).
  - Tests: a `dbTestServer` create with a composition fake receives exactly one `POST /work` with the
    caller's bearer; with the fake returning 500 or hanging, the create still returns 201 within budget.
  - Bite: remove the call; the "receives one POST" case goes red.
  - Log: DEBUG `book.create provision=attempted book_id=<id>`.
- [x] **T8** — **The create/open race makes one Work and one project** (Cycle 2)
  - Live on `lw-iso` after rebuilding `book-service`: create via REST and open in Studio immediately,
    10 times. Count Work rows and knowledge projects per book; each must be exactly 1.
- [x] **T9** — **Live: a book nobody opened has its project** (Cycle 2)
  - Create one book via REST, never open it; its knowledge project exists within 5s. Paste the query.
  - Drop condition (from the spec): the handler does not have the caller's bearer → fall back to the UI
    calling `/work` after create.

### Lane D — backfill on sign-in (Q4)

- [x] **T10** — **An owner-only endpoint that provisions the caller's own books** (Cycle 2)
  - Files: `services/book-service/internal/api/` (route under `/v1/books`, which the BFF already proxies).
    Name proposed: `POST /v1/books/provision-missing` — final name in DESIGN.
  - Lists **only books where `owner_user_id` = caller**, active ones. For each, a cheap `GET /work`
    (the `fetchStructureWork` pattern) and a `POST /work` through T6's helper only when the Work is
    missing or pending. Bounded concurrency (proposal 4) and an overall deadline; returns
    `{checked, provisioned, failed}`.
  - DESIGN decides whether per-book GETs are cheap enough for an owner with ~80 books, or whether
    composition needs one batch "which of these lack a ready Work" call.
  - Tests: another user's books are never requested; the caller's bearer is the only one sent;
    counts are right with mixed 200/500 fakes; the deadline stops the loop.
  - Log: INFO `book.provision_missing user_id=<id> checked=<n> provisioned=<n> failed=<n> ms=<n>`.
- [x] **T11** — **The frontend fires it once per sign-in** (Cycle 3)
  - Files: `frontend/src/` — an app-level effect keyed on a **new sign-in** (not on every token refresh),
    fire-and-forget, never blocking navigation or onboarding. Once per sign-in, latched.
  - Vitest: one call after sign-in; none on refresh; a failed call shows nothing to the user.
  - Log: `console.debug` only, behind the existing debug flag.
- [x] **T12** — **Live: a sign-in provisions the owner's books and nobody else's** (Cycle 4)
  - On `lw-iso` after rebuilding `book-service` and `frontend`: an account with unprovisioned books signs
    in; afterwards all its books have projects; a second account's unprovisioned books are unchanged.

### Lane E — show the critic once (L5, Q3)

- [x] **T13** — **Hide the inline critic while the critic panel is on screen** (Cycle 3)
  - Files: `ComposeView.tsx`, possibly a small selector in `workspace/dock.ts`, `ComposeView.test.tsx`.
  - First verify which layouts actually show both at once (a tabbed dock shows one tab at a time; floated
    and popped-out panels can sit beside Compose). Hide the inline `CriticFlags` only in those layouts.
  - **Before hiding anything, confirm `CriticPanel` exposes the C26 override gate.** If it does not, the
    inline gate controls stay, and only the duplicate verdict text is hidden.
  - Vitest: panel on screen → inline hidden and gate still reachable; panel hidden or absent → inline shown.
  - E2E: `ChapterComposePanel.critic` (`pages/ChapterComposePanel.ts:93-98`) may need to follow the verdict to
    wherever it now renders. That is a PO-ordered behaviour change, recorded as such in the cycle — not a
    test edited to accommodate a fix (Rule 2).

### Lane F — retire the legacy chapter editor (PO, 2026-09-18, mid-run)

- [x] **T16** — **The retired chapter editor has no route and no links** (Cycle 4)
  - PO: *"help me retire the routing, so no one can go to that page anymore … we only have writing studio now"*.
  - `/books/:bookId/chapters/:chapterId/edit` now only redirects to `/books/:bookId/studio?chapter=:chapterId`.
    Every in-app link goes to the Studio via `lib/studioRoutes.ts`. `ChapterEditorPage.tsx` and its own unit test are deleted.
- [x] **T17** — **The E2E specs that drove the retired page run in the Writing Studio** (Cycle 6)
  - 8 specs reach the old page through `ChapterComposePanel.gotoEditor` or `ChaptersTab`. After T16 they land in the Studio, so each must drive the Studio's surfaces. The claim each one makes stays the same; only the page it drives changes.

### Lane Z — close

- [x] **T14** — **Known issues in the release notes** (Cycle 5)
  - File: `CHANGELOG.md`, the `[0.1.0]` section, a `### Known issues` subsection. First confirm
    `scripts/changelog-gate.py` accepts that subsection.
  - Entries: MCP-created books provision on first open (Q2); the `materialize` string bounds are a
    guardrail not yet measured (L2); anything T4 or T5 leaves open. Each says what, who, workaround.
- [~] **T15** — **The whole suite, on rebuilt images** (Cycle 7 — run 3 green; 4 intermittent reds from runs 1–2 unexplained)
  - Rebuild every image touched (composition ×2, book-service, frontend). Run the full Playwright suite and
    the unit suites. 0 failed, 0 skipped; any skip is answered (Rule 6). Update the handover report.

## Commit Plan

Checkpoints sit at risk boundaries, not file counts. Run `scripts/doc-language-gate.py --staged` before each.

1. After T1–T3: `fix(composition): truncated plan output is regenerated, not fatal`
2. After T4: `docs(plan): real-run measurement for plan-forge truncation`
3. After T6–T7: `feat(book-service): provision the knowledge project at book creation`
4. After T10–T11: `feat(books): provision an owner's books on sign-in`
5. After T13: `fix(frontend): show the critic verdict once`
6. After T5, T8, T9, T12, T14, T15: `docs(plan): close the v0.1.0 leftovers against the final run`

## Rules

1. A fix is proven by re-breaking it: break, watch it go red, restore, watch it go green.
2. Never edit a test to accommodate a fix.
3. Never delete, skip or `fixme` a test to close a row.
4. Rebuild the image before any E2E run; the composition worker is a separate image.
5. "Flaky" is not a verdict.
6. A skip is not a pass; every skip is answered.
7. Re-verify every cited premise before building on it.
8. `scripts/doc-language-gate.py --staged` before every commit.

## What this plan will NOT do

- Reverse OQ-1 or mint any token for a user.
- Make critique asynchronous (202 + poll), or add sampler controls (DRY, wider penalty window).
- Change MCP `book_create` (Q2).
- Raise the 900s sweep timeout.
- Ship. That is AC-11, and it is the PO's.

## Cycles

### Cycle 1 — T1, T2, T3: truncation reaches the ladder; a slow job is not started twice

**Investigated:** every premise in the reconnaissance table for L1, re-read. All of them held:
- `chat()` raised the base `PlanForgeLLMError` for `"truncated"`.
- The first `client.chat()` sat above the ladder loop.
- `_MockLLMClient` returned no `finish_reason`.
- `run_job` skips only completed/failed/cancelled jobs, so it re-runs a `running` row.
- Nothing wrote `generation_job.updated_at` between `update_status("running")` and the end of the job.

Found on the way: `chat()`'s schema-rejected fallback called itself **without** `frequency_penalty`.
So an escalated regeneration (1.2, 1.6) silently dropped back to 0.8 whenever the provider refused the schema.

**Issues:** none — every defect found here is fixed in this cycle and recorded in it and in `CHANGELOG.md`; opening a public tracker entry is the PO's call, not this run's

**Fix:** in three places:
- `llm.py`: new `PlanForgeTruncated(PlanForgeLLMError)`, raised only for `"truncated"`. It carries no response text. The schema fallback now forwards `frequency_penalty`.
- `propose_llm_async.py`: the first call moved inside the ladder. `PlanForgeTruncated` takes the regenerate branch on every attempt. The final error names the last reason. The repair call is reachable only from a small, non-truncated parse failure.
- `job_consumer.py` + `generation_jobs.py`: `run_job`'s `cancel_check` touches `updated_at` at most once per 60s through `touch_running`, which only touches a `running` row. The LLM SDK already polls `cancel_check` through every wait, so this covers every worker op and every long single generation, not only the ladder. The 900s sweep timeout is unchanged.

**Proof:** unit suites run inside the composition image; the host's `mcp` 2.x cannot import the service.

```
T1 BROKEN  (chat raises the base type for truncation)
E   app.engine.plan_forge.llm.PlanForgeLLMError: LLM job unusable: truncated
FAILED test_plan_forge_llm.py::test_a_TRUNCATED_job_raises_its_own_type_carrying_no_text
1 failed, 15 passed
T1 RESTORED  16 passed

T2 BROKEN  (ladder no longer catches PlanForgeTruncated)
E   app.engine.plan_forge.llm.PlanForgeTruncated: LLM job unusable: truncated
FAILED ...::test_a_TRUNCATED_first_attempt_is_REGENERATED_through_the_ladder
FAILED ...::test_truncation_on_EVERY_attempt_fails_actionably_and_is_NEVER_repaired
2 failed, 17 passed
T2b BROKEN (schema fallback drops the penalty)
E   assert [1.6, 0.8] == [1.6, 1.6]
FAILED ...::test_a_schema_fallback_keeps_the_ESCALATED_penalty
RESTORED (byte-exact, cmp)  19 passed

T3 BROKEN  (heartbeat write removed)
E   AssertionError: only 0 heartbeat(s) in 1200s — the sweeper would re-drive
FAILED test_job_heartbeat.py::test_a_LONG_wait_touches_updated_at_well_inside_the_sweep_window
RESTORED (byte-exact, cmp)  3 passed

Full composition unit suite: 4011 passed, 2 failed
```

**The 2 unit failures are not this cycle's.** Both fail identically with the three changed files stashed (`2 failed, 52 passed` on the two files alone):
- `test_scene_beats.py::test_nothing_in_the_engine_computes_from_the_undirected_yield` shells out to `git`, which the image does not have. It is an environment gap of this test-runner, not a product defect.
- `test_outline_canon_routers.py::test_create_node_201_and_bad_reference_400` gets `422` where it expects `201`. That is a real red. It predates this plan, and it is recorded here so it cannot be forgotten. It is not in this plan's scope, and nothing here depends on it.

**AC impact:** AC-1 ✅. AC-3 🚧: the unit proof is here, and the live `generation_job` history comes with T4.

```goal-prompt
goal: the v0.1.0 leftovers are closed or honestly bounded, each fix proven by re-breaking it, and the suite is green on rebuilt images
po_decisions: [AC-11]
rules: |
  1 A fix is proven by re-breaking it.
  2 Never edit a test to accommodate a fix.
  3 Never delete, skip or fixme a test to close a row.
  4 Rebuild the image before any E2E run; the composition worker is a separate image.
  5 "Flaky" is not a verdict.
  6 A skip is not a pass.
  7 Re-verify every cited premise.
  8 doc-language-gate --staged before every commit.
note: |
  Only the caller's own bearer is ever forwarded (OQ-1). Never control LM Studio by hand.
stop: |
  a change would mint a token or forward anyone's bearer but the caller's
  a write would touch a non-throwaway database
  the ship decision
```

### Cycle 2 — T6–T10: a new book is provisioned at creation, and the backfill is owner-only

**Investigated:** re-read before building:
- `createBook` commits, then answers 201. It never read `Authorization`, although the header reaches it.
- `fetchStructureWork` forwards the raw header, through `http.DefaultClient` (no timeout).
- composition's `POST /work` dedupes the knowledge project under a per-(user, book) advisory lock. It catches the Work insert's unique violation, and it caps pending rows with a partial unique index.
- `countActiveBooks` defines the library's scope: active, not the bible, never `kind='diary'`.

**Decisions this cycle** (the plan left them to DESIGN):
- **The create-time call is asynchronous**, not synchronous with a short timeout. It runs after commit on a context detached from cancellation. Creation gains no latency and cannot fail because of it, whatever composition does.
- **Timeout 10s**, on its own `http.Client`. It bounds goroutines, not users.
- **Backfill route `POST /v1/books/provision-missing`.** It uses the library's scope. For each book it sends one cheap `GET /work`, and a `POST` only when the Work is missing or pending. Concurrency 4, overall deadline 90s. It is also detached from the client, because the frontend fires it and does not wait.

**Issues:** none — every defect found here is fixed in this cycle and recorded in it and in `CHANGELOG.md`; opening a public tracker entry is the PO's call, not this run's

**Fix:** in three files:
- `composition_provision.go`: `provisionCompositionWork` and its async wrapper.
- `server.go`: `createBook` calls the wrapper after commit. The route is registered.
- `provision_missing.go`: the backfill.

MCP `book_create` is untouched (Q2). No token is minted anywhere, and the only identity sent is the caller's own bearer.

**A test defect fixed on the way.** `internal/migrate` `TestBackfillScenesBookID_AcrossBatchBoundaries` counted **every scene in the database** whose book differed from its own seed. It went red whenever `internal/api` ran first on the shared test DB: `26 scenes got a book_id that is not their chapter's book`. That happened on a fresh DB **with or without any change from this plan**, and it went green when the test ran alone. The check now tests the claim it states, "each seeded scene got its chapter's book", with a join on `chapters`. Bitten: a backfill that writes another book's id turns it red (`1201 scenes got a book_id that is not their chapter's book`). This fixes a wrong test, not a change made so that a fix would pass.

**Proof:**

```
T6 BROKEN (bearer not forwarded)
    composition_provision_test.go:38: Authorization "" — the caller's own bearer must arrive unchanged
T6 BROKEN (http.DefaultClient)
    composition_provision_test.go:78: the provision client must carry its own timeout; http.DefaultClient has none
T7 BROKEN (call removed)
    create_book_provision_db_test.go:65: no POST /work within 5s of creating the book — its knowledge project waits for someone to open it
T7 BROKEN (made synchronous)
    create_book_provision_db_test.go:98: create took 10.0394677s while composition hung — provisioning must stay off the request path
T10 BROKEN (owner filter dropped)
    result {Checked:11 Ready:1 Provisioned:9 Failed:1}, want {Checked:4 Ready:1 Provisioned:2 Failed:1}
T10 BROKEN (ready books re-provisioned)
    result {Checked:4 Ready:0 Provisioned:3 Failed:1}, want {Checked:4 Ready:1 Provisioned:2 Failed:1}
T10 BROKEN (sweep bound to the client)
    provision_missing_db_test.go:158: posts [] — a fire-and-forget caller hanging up must not stop the sweep
every bite RESTORED byte-exact (cmp) and green
book-service Go suite, fresh throwaway DB (postgres:18), -p 1: api ok · config ok · migrate ok · testsafe ok · textdiff ok
```

`go test ./...` without `-p 1` deadlocks in `migrate.Up`, because several packages migrate one shared DB concurrently. That is how this suite has to be run, not a product defect: run it with `-p 1`.

```
T9 LIVE (lw-iso, book-service rebuilt 2026-09-18T15:34Z, account iso-evidence@loreweave.dev)
  create 201 in 21 ms            book 01a0b52a-e7cd-7de2-93ee-0b2b51e50e27  (never opened)
  after 0.7 s   composition_work project_id=01a0b52a-e7ec-77a1-b7bb-c3a126b471c2 pending=false
  knowledge_projects: owner=01a09a04-... = books.owner_user_id
  book-service log: "book.provision ok" status=201 ms=54   (the T4 runner's book, same path)

T8 LIVE — 10 books; each: REST create (its own POST /work) + two concurrent Studio-style POST /work
  10/10: "1 works, projects=1, pending=0 knowledge_projects=1"   ALL EXACTLY ONE: True
```

T8 is a verification row. The guards it exercises are composition's, and they predate this plan. This cycle added nothing there that a bite could remove. T9's "before" is the measured state the plan starts from: 298 books with no project until someone opened them. The live check repeats the bitten T7 behaviour on the real stack.

**AC impact:** AC-5 ✅, AC-6 ✅, AC-7 🚧 (T11, T12 open).

### Cycle 3 — T11, T13: the backfill fires once per sign-in; one screen shows the critic once

**Investigated:** the sign-in seam, and where the critic renders:
- `AuthProvider.setTokens` is called only by `LoginPage` and `RegisterPage`. A silent refresh writes storage and fires `lw-auth-refreshed`, and a page reload reads storage. Neither goes through `setTokens`, so it is the exact "new sign-in" seam.
- `apiJson` counts every request in the global operation tracker, which drives `GlobalOperationProgress`. A 90s background sweep would light the progress bar for work the author never asked for.
- The dock shows one tab at a time. Compose and the critic panel are on screen together only when the critic is floated, popped out, or the active tab while Compose is floated.
- `CriticPanel` renders the verdict **without** `onRegenerate`. So the C26 override gate's Regenerate action exists only in the inline copy, and removing the inline copy outright would have removed it.

**Issues:** none — every defect found here is fixed in this cycle and recorded in it and in `CHANGELOG.md`; opening a public tracker entry is the PO's call, not this run's

**Fix:** in four places:
- `lib/provisionOnSignIn.ts`: a raw `fetch` with `keepalive`, marked `X-LW-Operation-Tracked: 1` so the tracker ignores it. Failures go to `console.debug` in dev only. `setTokens` calls it when it receives an access token.
- `workspace/dock.ts` `criticPanelShowing(layout, activeTab)`: floated or popped out and not hidden, or docked as the active tab.
- `CriticFlags` `gateOnly`: render only the override gate, or nothing when it is not raised.
- `CompositionPanel` passes `criticShownElsewhere` to `ComposeView` on desktop dock layouts only. Mobile and the popout shell mount one panel at a time, and the flag-off strip shows one tab.

The E2E locator (`ChapterComposePanel.critic`, scoped to `dock-slot-compose`) needed **no change**. In the default layout the critic panel is a background tab, so the full inline verdict still renders there.

**Proof:**

```
T11 BROKEN (trigger removed)
  × fires ONE provision-missing request with the new bearer on sign-in
  AssertionError: expected [] to have a length of 1 but got +0
T11 BROKEN (also fired on refresh)
  × does NOT fire on a silent token refresh, a page reload, or a logout
  AssertionError: expected [ [ …(2) ] ] to have a length of +0 but got 1
RESTORED byte-exact   3 passed

T13 BROKEN (gateOnly ignored — the duplicate returns)
  × panel ON screen: no inline verdict copy
  × panel ON screen with the gate raised: the gate and its Regenerate stay reachable
T13 BROKEN (gate dropped along with the verdict)
  × panel ON screen with the gate raised: the gate and its Regenerate stay reachable
T13 BROKEN (a background dock tab counted as on screen)
  × docked: showing only as the active tab
RESTORED byte-exact   composition suite 1093 passed · tsc --noEmit clean
```

**AC impact:** AC-7 🚧: only the live T12 run remains. AC-8 🚧: unit-proven here; the E2E leg runs in T15.

### Cycle 4 — T4, T5, T12, T16: measured live, a stuck-forever 409 found and fixed, the old editor retired

**Investigated:** T4, T5 and T12 live on `lw-iso`; the root cause of the 9 stuck books in `routers/works.py`; every caller of the retired editor route.

**Issues:** none — every defect found here is fixed in this cycle and recorded in it and in `CHANGELOG.md`; opening a public tracker entry is the PO's call, not this run's

**Fix:** `routers/works.py` (the pending-Work step for every branch that reaches a project); T16's redirect, `lib/studioRoutes.ts` and 7 re-pointed callers. T4 and T5 changed no product code.

**Proof:** the fenced blocks below, one per row.

**T4 — real runs.** Both composition images were rebuilt and marker-grepped in the running containers (`PlanForgeTruncated` 3, `touch_running` 1). 30 real plan runs went through the API on `lw-iso` (account `iso-evidence@loreweave.dev`, gemma-4-26b-a4b-qat, the pass-rail premise).

```
runs: 30   proposed 30 (29 × 3 arcs, 1 × 4 arcs)   final failures 0   mean 38 s
llm_jobs (usage_purpose=plan_forge, since 15:36:56Z):
  analyze        | length | completed |  1 | 109 s | 12941 tokens   <- a loop ran to the cap
  analyze_retry1 | stop   | completed |  1 |   8 s |  1672 tokens   <- the ladder regenerated it
  analyze        | stop   | completed | 29 |  13 s
  materialize    | stop   | completed | 30 |  12 s
generation_job (plan_forge*, same window): completed 30 — one row per run, none started twice
```

Before this plan, that one run would have died on `LLM job unusable: truncated`: the measured baseline was 2 truncated of 31. The drop condition (more than half the regenerations also truncating, or no improvement on 2/31) did not fire. For L2 the 30 bounded `materialize` calls add to the record: **0/40 truncated bounded vs 3/17 unbounded, Fisher p ≈ 0.023** (was 0.27 on 0/10). The two arms were run on different days and builds, so this is strong evidence, not a controlled A/B. No run came near 900s, so the heartbeat itself was not exercised live. Its proof is Cycle 1's bite; here the evidence is only that nothing ran twice.

**T5 — the critic ceiling, re-broken.** The plain cold load could not bite. With the 20s ceiling, `composition-generate` passed: LM Studio evicted and reloaded the 26B critic on its own (nobody touched LM Studio), and the critic job took 18s, just under 20. Per the plan's own fallback, a deliberately slow stand-in replaced it: a pass-through proxy on the host (`:1299`) holding every chat POST 45s. The account's LM Studio provider was pointed at it for the two runs, then pointed back to `:1234`. Nothing about LM Studio was controlled.

```
BROKEN  frontend rebuilt with the critique call's timeoutMs removed (bundle: `token:n})` — no timeoutMs)
  Error: expect(locator).toBeVisible() failed
  Locator: getByTestId('dock-slot-compose').getByTestId('compose-critic')   element(s) not found
  llm_jobs: prose_critic | completed | 61 s   <- the server finished; the browser had given up at 20 s
RESTORED api.ts byte-identical to HEAD, frontend rebuilt (bundle: `token:n,timeoutMs:Daa`)
  ok 1 composition-generate … runs the distinct-model critic on accept (2.2m)
  llm_jobs: prose_critic | completed | 63 s
```

This E2E drove the chapter-editor page that the PO has now retired (T16). The critique call is `compositionApi.critique` in `ComposeView`, and the Writing Studio mounts the same `ComposeView` (`SceneComposePanel` → `CompositionPanel` in solo mode). So the proof covers the code the Studio runs. T17 moves the spec itself onto the Studio.

**T12 — sign-in backfill, live, and the defect it found.** A real browser sign-in (Playwright, `:25174`) fired `POST /v1/books/provision-missing` once. A reload fired it 0 more times.

```
before     iso-evidence: 105 books, 51 ready, 54 missing      other owner: 77 books, 65 ready, 12 missing
sign-in 1  200 {"checked":105,"ready":51,"provisioned":45,"failed":9}    (566 ms)
after 1    iso-evidence: 105 / 96 / 9                          other owner: 77 / 65 / 12  (untouched)
```

All 9 failures were `409` from composition `POST /work`, and they were not caused by this plan. Each of those books had an **unmarked knowledge project** plus a **pending Work**. `create_work` ran the C16 backfill step only in its `none` branch. `unmarked_*` fell through to `works.create`, which hit a `UniqueViolation`; the re-get by project found nothing, and it returned `409 WORK_CREATE_CONFLICT` on every attempt. Opening the book in the Studio calls the same `POST /work`, so these books could never have been provisioned by any path.

- **Fix** (`routers/works.py`): the pending-Work step now runs for every branch that reaches a project.
- **Unit test** `test_post_work_backfills_a_PENDING_work_onto_an_existing_UNMARKED_project`. Bite, with the step moved back inside the `none` branch: `AssertionError: {'detail': {'code': 'WORK_CREATE_CONFLICT'}} / assert 409 == 201`, the live failure word for word. Restored: green. Composition unit suite: 4012 passed, 2 failed (the same two as Cycle 1).
- **Live**, after rebuilding both composition images:

```
sign-in 2  200 {"checked":105,"ready":96,"provisioned":9,"failed":0}
after 2    iso-evidence: 105 / 105 / 0                         other owner: 77 / 65 / 12  (untouched)
stuck book 01a09bf9-2b4f-…: 1 work, project=01a09bf9-2b82-… (its existing knowledge project), pending=false
```

**T16 — the legacy chapter editor retired (PO instruction mid-run).**
- `App.tsx`: the route renders `RetiredChapterEditorRedirect`, which sends the old path to `studioChapterPath(bookId, chapterId)` with `replace`.
- Re-pointed to the Studio: 7 call sites (`RevisionCompareView`, `BeatSheetView`, `CastEntityRow`, `CharacterArcView`, `SceneGraphCanvas`, `TimelineView`, `ReaderPage`).
- Deleted: `ChapterEditorPage.tsx` (1404 lines, imported only by `App.tsx`) and its own unit test.
- Five view tests pinned the old destination. Their expectation now names the Studio deep link. That is a destination change the PO ordered, and each test still asserts that clicking opens that chapter.

This also settles T13's scope. The duplicated critic existed on the retired page's dock. The Studio mounts `CompositionPanel` in solo mode, where `criticShownElsewhere` is false by construction, so T13's change is dormant in the Studio.

```
BROKEN (TimelineView links to the old path again)
  × no source file builds a link to the retired editor path
  × clicking an event opens its chapter
BROKEN (the redirect drops the chapter)
  AssertionError: expected '/books/b-1/studio' to be '/books/b-1/studio?chapter=c-9'
RESTORED byte-exact · tsc --noEmit clean · vitest 869 files, 6527 passed
```

**AC impact:** AC-2 ✅, AC-3 ✅, AC-4 ✅ (stand-in, as the plan allowed), AC-7 ✅, AC-12 🚧 (T17 open). AC-8 stays 🚧 because its E2E leg runs in T15, after T17.

### Cycle 5 — T14: the release notes say what changed and what is still open

**Investigated:** what the changelog gate checks, and what `[0.1.0]` says today:
- `changelog-gate.py` checks structure, and in release mode that `[0.1.0]` has real entries. It does not restrict subsection names, so `### Known issues` is legal.
- `[0.1.0]` is dated 2026-09-13 but is **untagged**: the tag is the PO's (AC-11). This branch is that release's gap-closure branch, so its user-facing changes are recorded in `[0.1.0]` itself. `/oss-publish` sets the final date at cut time.
- `### Removed` said "Nothing", which T16 made false.

**Issues:** none — every defect found here is fixed in this cycle and recorded in it and in `CHANGELOG.md`; opening a public tracker entry is the PO's call, not this run's

**Fix:** `CHANGELOG.md` `[0.1.0]`:
- **Changed:** books are provisioned at creation; the sign-in backfill; the Studio is the only writing surface.
- **Fixed:** truncation regenerates; the double-run sweeper; the stuck-409 books; the 240s critic ceiling; the critic shown once.
- **Removed:** the legacy chapter editor, with its redirect.
- **Known issues** (what, who, workaround for each):
  - MCP-created books are provisioned later, because OQ-1 forbids a minted identity.
  - A plan run can still fail when the model loops on all three attempts.
  - The critic waits at most 240s.

L2, the `materialize` string bounds, is **not** listed as a known issue: Cycle 4 measured it at 0/40 bounded vs 3/17 unbounded (Fisher p ≈ 0.023), with that cycle's caveat about uncontrolled arms. The remaining open row, T17, is test-only and not user-facing.

**Proof:**

```
changelog-gate: structure OK (3 section(s)).
changelog-gate: structure + release 0.1.0 OK (3 section(s)).
BROKEN (every entry removed from [0.1.0])
  RELEASE MODE: `## [0.1.0] - 2026-09-13` exists but has no entries under it. ...
RESTORED byte-exact (cmp) — structure + release 0.1.0 OK
```

**AC impact:** AC-9 ✅.

### Cycle 6 — T17: the specs that drove the retired page now drive the Writing Studio

**Investigated:** the 8 specs (16 tests) that reached the retired page through `ChapterComposePanel`. The Studio's own page objects (`StudioPage`, `StudioComposePanels`) and panel catalog. Which legacy testids survive in the Studio: `compose-*`, `composition-*`, `publish-button` and `editorial-badge` do. `chapter-save-button` and `composition-subtab-*` existed only on the deleted page.

**Issues:** none — test-only migration; the one product consequence it surfaced is recorded as a decision below

**Fix:** `ChapterComposePanel` was rewritten to drive the Studio, with the same property names, so no `expect` needed renaming:
- `gotoStudio` opens `?chapter=`. `openComposeTab` opens `scene-compose` from the command palette, and `showEditor` switches to the editor tab.
- New helpers: grounding through the scene inspector, canon through `quality-canon-rules`, and body edits in place of the title field the Studio does not have.
- `markStudioOnboarded` for B4.1's brand-new account, which otherwise meets the Studio's first-run role picker.
- `creation-unblock-world` routes its what-if through the canon picker (see below).

**Decisions this cycle.** These are written down because a claim had to change shape. None was loosened.
- **U1 ("set up the co-writer")**: in the Studio the co-writer is ready with no setup step. `useEnsureWork` in `StudioFrame` creates the Work on open, and it predates this plan; T7 now also creates it at book creation. The Studio's form of the claim is therefore: no setup button, and the scene controls are present. That applies in `composition-gate` and `composition-journey`.
- **U2**: the guided "Opening scene" seed fires only from the setup click (`useGuidedFirstRun.runGuided`), so "+ Scene" now yields exactly **1** scene, not 2. The count is deterministic: nothing else creates a scene.
- **B7.3 ("no Work → Publish ungated")**: the Studio can no longer show a book without a Work, so the state is unreachable from the UI. The fail-open behaviour is still pinned where it can still be reached: `usePublishGate.test.tsx`, "no composition Work → ungated (blocked:false)". **This is the one E2E assertion removed, and it is flagged for the PO.**
- **B1.\* setup** (`composition-publish-lifecycle`): these tests started from "no Work, so the gate is off". They now start from "gate satisfied" (one scene, done). The lifecycle claims are unchanged, and B7.2 still tests the gate itself.
- **`creation-unblock-world`, G1**: every book created through REST now has a Work (T7), so the world held **two** canon trunks. By the component's own decision ⑦, that opens the "Branch from…" picker instead of routing straight away. The spec picks the seeded book and asserts the same route, `**/books/<id>?work=*`. The spec's premise changed, not the claim.

**Proof:**

```
composition-correction-gate 1 passed · composition-engine 3 passed · composition-generate 1 passed
composition-grounding-canon 2 passed · composition-publish-lifecycle 6 passed · creation-unblock-divergence 1 passed
composition-gate      BEFORE the decision:  expect(panel.publishButton).toBeEnabled() — received disabled
                      AFTER:                ok 1 … U1+U2+B7: co-writer ready, add a scene, Publish gated … (4.1s)
composition-journey   BEFORE the decision:  expect(panel.setupButton).toBeVisible() — element not found
                      AFTER:                ok 1 … set up → scene → co-write → accept → save → mark done → publish (15.0s)
creation-unblock-world BEFORE: page.waitForURL: Timeout 15000ms exceeded (the canon picker was open)
                       AFTER:  2 passed (8.7s)
```

**AC impact:** AC-12 ✅.

### Cycle 7 — T15: three full runs on rebuilt images

**Investigated:** three full Playwright runs on `lw-iso` with the evidence account. Every image carries this branch, checked in the running containers:
- composition-service and composition-worker: the seam-fix marker and `PlanForgeTruncated`;
- book-service: `/v1/books/provision-missing` answers 401 unauthenticated;
- frontend: the bundle has `provision-missing` and the critique call's `timeoutMs`.

Every failure was re-run alone, and the full-run artifacts were kept for runs 2 and 3.

**Issues:** none — the one real cause found is fixed in Cycle 6; the four unexplained failures are listed below with their evidence, and filing them publicly is the PO's call

**Fix:** none in product code this cycle. `creation-unblock-world`'s premise fix is Cycle 6's.

**Proof:**

```
images   composition-service 38feebb75728 · composition-worker 0dde64eb4014 · book-service eb4d2cff50a6 · frontend cac385fb3f31
run 1    198 passed, 3 failed (24.7m)
           creation-unblock-world G1   waitForURL timeout      -> REAL: T7 made both world books canon; picker opens (fixed, Cycle 6)
           revision-compare-remainder B8.5  equal rows 0 (>=10) -> passes alone, 15/15 repeated, and in runs 2-3
           studio-inline-correction Discard  inline-discard not found -> passes alone, and in runs 2-3
run 2    199 passed, 2 failed (25.4m)
           composition-flywheel U8     no drain job within 60s -> passes in run 3
           studio-publish S1-B4        PATCH outline/nodes -> 401 {"detail":"invalid token"} in the test body,
                                       with a token its own beforeAll had just used successfully -> 5/5 alone, and in run 3
run 3    201 passed, 0 failed, 0 skipped (23.3m)
unit     composition 4012 passed + the 2 pre-existing reds (Cycle 1) · book-service Go -p 1 all ok · frontend vitest 869 files / 6527 passed
gates    gate-wiring-gate --run-all: all static gates green after the plan-format fix (85d9f84ab); 28 live gates skipped (no stack on :25556)
```

**What is known about the four unexplained failures, and what is not:**
- None reproduces alone, and none failed twice across the three runs. So "flaky" is not the verdict here: the verdict is "cause not found".
- **B8.5**: the server diff's perf guard is size-based (`maxCells`), not time-based, and cannot trip on 12 lines. Revision order is deterministic (`created_at DESC, id DESC`). So `equal = 0` means a different pair of revisions was compared, and nothing yet explains why. Run 1's artifacts were lost to a solo re-run.
- **studio-publish 401**: token TTL is 7200s. `loreweave_authn` folds every verification failure, expiry included, into one "invalid token", so the log cannot say which check failed.
- **flywheel**: worker-ai was busy with other tests' distill LLM jobs at the time. That is the likely reason no drain arrived within 60s, but it is not proven.
- **New since the 2026-09-13 baseline**, and relevant to load: every UI sign-in now fires the T11 backfill, about 130 `GET /work` in 100ms for this 105-book account. It did not cause the failures observed here, and it is noted as a cost for review.

**AC impact:** AC-8 ✅ (its E2E leg is green through the Studio); AC-10 🚧 — green once, not yet shown to be reliably green.

### Cycle 8 — T15: the intermittent reds have a cause — the dev VM's clock steps back every 30 s

**Investigated:** run 2's kept trace for `studio-publish`. Every API request is decoded from `*-trace.network`. The same token (`iat` 1789754823 = 18:07:03 UTC, `exp` +2h) was accepted by `POST /outline/nodes` and then rejected by `PATCH /outline/nodes/{id}` with `401 invalid token`. In composition's log, docker's own receive timestamps go **backwards** 16 times during run 2. One is exactly `18:07:03.106 -> 18:07:01.902`, the 401. Measured inside the container, wall clock against monotonic, three times over 65 s:

```
+  0.5s  wall moved -1.393s while monotonic moved +0.020s
+  0.8s  wall moved +4.162s while monotonic moved +0.020s
+ 30.5s  wall moved -1.396s while monotonic moved +0.020s
+ 30.8s  wall moved +4.161s while monotonic moved +0.020s
+ 60.5s  wall moved -1.395s while monotonic moved +0.020s
+ 60.7s  wall moved +4.173s while monotonic moved +0.020s
```

The Docker VM's wall clock steps back 1.39 s, then forward 4.16 s about 0.25 s later, every 30 s. That is the host's time sync, and nothing in this repo causes it.

- **A token issued in the 1.39 s before a step has an `iat` in the future inside the window.** PyJWT 2.13 rejects that with zero leeway (`ImmatureSignatureError: The token is not yet valid (iat)`), and `loreweave_authn` reports every failure as "invalid token".
- **Go's `contracts/platformjwt.Verify` never checks `iat`**: golang-jwt v5 checks it only under `WithIssuedAt()`, which is not passed. So the Python services rejected tokens the Go services accepted. That is a real parity defect. The verifier's own comment says "keep the two verifiers identical", and ordinary skew between production hosts triggers it too.

**Issues:** none — the parity defect is fixed in this cycle; the revision-ordering fragility is recorded as `DEFERRED.md` #164; the VM clock is the host's, outside this repo

**Fix:** `sdks/python/loreweave_authn/_verify.py` passes `verify_iat: False`, matching Go. `exp` stays required and enforced, and the signature is checked as before. All 13 Python images that use the SDK were rebuilt. **No token was minted anywhere.** Every probe used real login tokens issued by auth-service.

**The other three reds, against this cause:**
- **B8.5 (revision compare), mechanism proven.** A probe saved 260 revisions over 70 s and listed them newest-first: `order inversions: 1 [(166, 171)]`. Saves 167–171 landed after a backward step, so they sort as older than save 166. B8.5's seed runs in about 100 ms. If a step falls inside it, "newest two" pairs the chapter's empty first revision with the last save, which gives `equal = 0`, the observed failure. Revision order depends on the database's wall clock (`now()`, `uuidv7()`). This is **not** changed here: a production database host with NTP slewing does not step back. It is recorded as `DEFERRED.md` #164 with the fix recipe (a per-chapter sequence).
- **composition-flywheel and studio-inline-correction: cause not proven.** The flywheel's selection query compares no timestamps for its own project. The inline-correction trace was lost to a re-run. Both passed in runs 3 and 4, and they stay listed as unexplained rather than blamed on the clock.

**Proof:**

```
unit    loreweave_authn: 28 passed (new: test_accepts_token_whose_iat_is_in_the_future_go_parity)
BROKEN  verify_iat removed:  E  jwt.exceptions.ImmatureSignatureError: The token is not yet valid (iat)
RESTORED byte-exact (cmp):   28 passed
LIVE BEFORE (old images) — real login every 0.5 s, GET composition every 10 ms, 70 s:
        requests: 3552  200: 3538  401: 14  other: 0      (all 14 inside one clock step, "invalid token")
LIVE AFTER (13 Python images rebuilt; verify_iat present in each container's SDK):
        requests: 3603  200: 3603  401: 0   other: 0
```

**AC impact:** AC-10 🚧 — one of the four unexplained reds is now explained and fixed, and one is explained and deferred with evidence. The next full run is recorded in Cycle 9.
