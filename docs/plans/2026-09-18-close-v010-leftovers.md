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
| **AC-2** | On 30 real plan runs, final failures are fewer than today's 2 of 31 | `llm_jobs` query pasted in the cycle (`job_meta.extractor`, `finish_reason`) on rebuilt images | T4 | ❌ not met |
| **AC-3** | A long ladder never lets the sweeper start a second copy of the same plan job | unit test on the heartbeat + `generation_job` row history from T4 | T3, T4 | 🚧 partial — unit proof and bite in Cycle 1; live row history owed by T4 |
| **AC-4** | The 240s critic ceiling is proven by re-breaking it on a real cold model load | `composition-generate.spec.ts` run pasted twice: 20s ceiling red, 240s green | T5 | ❌ not met |
| **AC-5** | A book created through REST has its knowledge project within 5s without anyone opening it, and a provisioning failure never fails the create | Go handler tests with an `httptest` composition fake + live T9 query | T6, T7, T9 | ✅ met — Cycle 2: 4 bites; live project 0.7s after create, owner-matched |
| **AC-6** | Creating a book and opening it at once yields exactly one Work and one knowledge project | live race run on `lw-iso` with row counts pasted | T8 | ✅ met — Cycle 2: 10/10 books, three racing callers each, exactly 1 Work + 1 project |
| **AC-7** | After an owner signs in, every book they own has a knowledge project; no other user's book is touched; only the owner's bearer is used | Go endpoint tests + vitest trigger test + live T12 counts | T10, T11, T12 | 🚧 partial — T10 proven in Cycle 2 (3 bites); T11, T12 open |
| **AC-8** | The critic result appears once on screen, and the override gate stays reachable | `ComposeView.test.tsx` layout cases + `composition-generate.spec.ts` | T13 | ❌ not met |
| **AC-9** | Every item left open ships with a Known issues entry: what, who, workaround | `scripts/changelog-gate.py` + the `[0.1.0]` section text | T14 | ❌ not met |
| **AC-10** | The whole suite is green on rebuilt images: 0 failed, 0 skipped | full Playwright + unit run pasted, image ids listed | T15 | ❌ not met |
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
- [ ] **T4** — **Measure on real runs**
  - Rebuild **both** composition images (`composition-service` and `composition-worker`, Rule 4) on `lw-iso`.
  - 30 real plan runs through the API. Count final failures, regenerations and their `finish_reason`
    from `llm_jobs`, and check `generation_job` for any job that started twice.
  - Drop condition (from the spec): more than half the regenerations also truncate, or final failures do
    not fall below 2 of 31. Then A goes to Known issues and the soak (IDEA-001 idea 11) is proposed.

### Lane B — prove the critic ceiling (L3)

- [ ] **T5** — **Re-break the 240s critic ceiling on a real cold load**
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
- [ ] **T11** — **The frontend fires it once per sign-in**
  - Files: `frontend/src/` — an app-level effect keyed on a **new sign-in** (not on every token refresh),
    fire-and-forget, never blocking navigation or onboarding. Once per sign-in, latched.
  - Vitest: one call after sign-in; none on refresh; a failed call shows nothing to the user.
  - Log: `console.debug` only, behind the existing debug flag.
- [ ] **T12** — **Live: a sign-in provisions the owner's books and nobody else's**
  - On `lw-iso` after rebuilding `book-service` and `frontend`: an account with unprovisioned books signs
    in; afterwards all its books have projects; a second account's unprovisioned books are unchanged.

### Lane E — show the critic once (L5, Q3)

- [ ] **T13** — **Hide the inline critic while the critic panel is on screen**
  - Files: `ComposeView.tsx`, possibly a small selector in `workspace/dock.ts`, `ComposeView.test.tsx`.
  - First verify which layouts actually show both at once (a tabbed dock shows one tab at a time; floated
    and popped-out panels can sit beside Compose). Hide the inline `CriticFlags` only in those layouts.
  - **Before hiding anything, confirm `CriticPanel` exposes the C26 override gate.** If it does not, the
    inline gate controls stay, and only the duplicate verdict text is hidden.
  - Vitest: panel on screen → inline hidden and gate still reachable; panel hidden or absent → inline shown.
  - E2E: `ChapterComposePanel.critic` (`pages/ChapterComposePanel.ts:93-98`) may need to follow the verdict to
    wherever it now renders. That is a PO-ordered behaviour change, recorded as such in the cycle — not a
    test edited to accommodate a fix (Rule 2).

### Lane Z — close

- [ ] **T14** — **Known issues in the release notes**
  - File: `CHANGELOG.md`, the `[0.1.0]` section, a `### Known issues` subsection. First confirm
    `scripts/changelog-gate.py` accepts that subsection.
  - Entries: MCP-created books provision on first open (Q2); the `materialize` string bounds are a
    guardrail not yet measured (L2); anything T4 or T5 leaves open. Each says what, who, workaround.
- [ ] **T15** — **The whole suite, on rebuilt images**
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

**Investigated.** Every premise in the reconnaissance table for L1 held on re-read:
- `chat()` raised the base `PlanForgeLLMError` for `"truncated"`.
- The first `client.chat()` sat above the ladder loop.
- `_MockLLMClient` returned no `finish_reason`.
- `run_job` skips only completed/failed/cancelled jobs, so it re-runs a `running` row.
- Nothing wrote `generation_job.updated_at` between `update_status("running")` and the end of the job.

Found on the way: `chat()`'s schema-rejected fallback called itself **without** `frequency_penalty`.
So an escalated regeneration (1.2, 1.6) silently dropped back to 0.8 whenever the provider refused the schema.

**Fix.**
- `llm.py`: new `PlanForgeTruncated(PlanForgeLLMError)`, raised only for `"truncated"`. It carries no response text. The schema fallback now forwards `frequency_penalty`.
- `propose_llm_async.py`: the first call moved inside the ladder. `PlanForgeTruncated` takes the regenerate branch on every attempt. The final error names the last reason. The repair call is reachable only from a small, non-truncated parse failure.
- `job_consumer.py` + `generation_jobs.py`: `run_job`'s `cancel_check` touches `updated_at` at most once per 60s through `touch_running`, which only touches a `running` row. The LLM SDK already polls `cancel_check` through every wait, so this covers every worker op and every long single generation, not only the ladder. The 900s sweep timeout is unchanged.

**Proof** (unit suites run inside the composition image; the host's `mcp` 2.x cannot import the service):

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

**AC impact.** AC-1 ✅. AC-3 🚧: the unit proof is here, and the live `generation_job` history comes with T4.

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

**Investigated.** Re-read before building:
- `createBook` commits, then answers 201. It never read `Authorization`, although the header reaches it.
- `fetchStructureWork` forwards the raw header, through `http.DefaultClient` (no timeout).
- composition's `POST /work` dedupes the knowledge project under a per-(user, book) advisory lock. It catches the Work insert's unique violation, and it caps pending rows with a partial unique index.
- `countActiveBooks` defines the library's scope: active, not the bible, never `kind='diary'`.

**Decisions this cycle** (the plan left them to DESIGN):
- **The create-time call is asynchronous**, not synchronous with a short timeout. It runs after commit on a context detached from cancellation. Creation gains no latency and cannot fail because of it, whatever composition does.
- **Timeout 10s**, on its own `http.Client`. It bounds goroutines, not users.
- **Backfill route `POST /v1/books/provision-missing`.** It uses the library's scope. For each book it sends one cheap `GET /work`, and a `POST` only when the Work is missing or pending. Concurrency 4, overall deadline 90s. It is also detached from the client, because the frontend fires it and does not wait.

**Fix.**
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

**AC impact.** AC-5 ✅, AC-6 ✅, AC-7 🚧 (T11, T12 open).
