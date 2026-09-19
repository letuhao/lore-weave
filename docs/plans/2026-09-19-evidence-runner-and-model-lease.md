# Plan — An evidence-first suite runner, then "one model at a time" as a user setting

- **Date:** 2026-09-19
- **Branch:** `fix/v0.1.0-release-gaps` (PO: stay on this branch)
- **Spec:** [`docs/specs/2026-09-19-evidence-runner-and-local-model-lease.md`](../specs/2026-09-19-evidence-runner-and-local-model-lease.md)
- **Idea:** [`docs/ideas/2026-09-19-leftovers-after-v010-plan.md`](../ideas/2026-09-19-leftovers-after-v010-plan.md) (IDEA-002)
- **Builds on:** [`2026-09-18-close-v010-leftovers.md`](2026-09-18-close-v010-leftovers.md) Cycles 7–10
- **Issues:** #286 (local model collision), #288 (two unexplained reds), #289 (stale unit test), #290 (unit test needs git), #291 (`go test` deadlock), #292 (e2e not type-checked); context #260, #274
- **Size:** L. Three services (provider-registry, composition tests, frontend), a DB column, and new tooling.

> Nothing here ships anything. The v0.1.0 tag is still the PO's (the previous plan's AC-11).

## Original Request

/aif-plan full (no description; the topic is the IDEA-002 spec, promoted immediately before)

## Settings

- **Testing:** yes. Every product fix is proven by re-breaking it.
- **Logging:** verbose. DEBUG on new branches; INFO on lease grant/wait/release and on preflight results; WARN on every contention retry and preflight warning.
- **Docs:** yes. Mandatory docs checkpoint (T16).

## CLARIFY — the PO's answers (2026-09-19)

| # | Question | Answer | Effect |
|---|---|---|---|
| Q1 | Order and branch | **B then A, this branch** | Lanes D (debt) → B (runner) → A (setting) |
| Q2 | Default for "one model at a time" | *"need explicit config on user setting, this problem is our hardware limit, so we cannot enforce apply it, so add setting is better"* | A becomes an **opt-in, per-provider-credential user setting**, default **off**, editable in Settings → Providers. No platform-wide default, no enforcement |
| Q3 | Preflight finds a trap | **Warn and record** | The run always proceeds; every warning is written to the ledger beside the results |
| Q4 | #165 and the two old unit reds | **Close #165 after N clean runs; fix the unit reds here.** Also: *"post all issues we found to github, we forgot this step"* | N = 5 consecutive clean runs recorded by the runner (T8). Issues filed 2026-09-19: #278–#285 (found and fixed, closed with their commit), #286–#294 (open); #274 given its proof as a comment |

## What the code says (reconnaissance, 2026-09-19)

Premises are re-verified before each lane starts.

**provider-registry:**
- **Concurrency governor** (`internal/ratelimit/governor.go`): a Redis ZSET with a per-call `limit`, keyed per **credential** (`gov:conc:<class>`).
- **Circuit breaker** (`breaker.go`): keyed per credential.
- **`Guard`** (`guard.go:35-69`): wraps the chat-shaped job path (`worker.go:623-633`, `:674-680`). **The breaker records only errors that `IsTransientUpstreamError` accepts**, and one predicate drives both retrying and breaker counting.
- **The load abort** comes back as `ErrUpstreamPermanent` (`provider/errors.go:98-119`, a 4xx other than 429), so it is **not** retried and **not** counted.
  - **Consequence:** the spec's claim that the load abort opened the breaker is wrong. Something *transient* opened it in run 4, and T9 finds out what before A is built.
- **Paths outside `Guard`:** `/v1/llm/stream` (`stream_handler.go:486`) and the audio, image, video and vision job paths bypass both governor and breaker.
- **Credential storage:** `provider_credentials` (`migrate/migrate.go:11-22`, `max_concurrency` at `:85`) has no JSON settings column. Migrations are idempotent replays, so a new column is `ADD COLUMN IF NOT EXISTS`.
- **Handlers:** create/list/patch/get in `internal/api/server.go:1172-1405`, which use anonymous structs. The patch pattern to copy is `optionalInt` + `CASE WHEN`.
- **Tests:** no miniredis; the tests use fakes behind interfaces (`guard_test.go`).
- **`ErrGovernorTimeout`** is not treated as transient, although a comment at `guard.go:53` says it is.

**Frontend:**
- Provider editing lives in `features/settings/ProvidersTab.tsx`: the concurrency field is at `:607-618`, the patch payload at `:158-159`.
- The API types are in `features/settings/api.ts:73`; the i18n keys are `providers.edit_dialog.*` in about 18 `settings.json` locales.

**E2E tooling:**
- `playwright.config.ts`: `outputDir tests/e2e/test-results`; `PLAYWRIGHT_EVIDENCE=1` turns on all capture.
- `collect_run_evidence.py` (`--trace/--label/--since`, `--out`) and `evidence-capture-gate.py` (`scan()`) are reusable.
- Image `org.loreweave.git_sha` labels are set only by `scripts/build-stack.sh`; `iso.sh build` leaves them `unknown`. Nothing records a dirty tree.
- Knowledge-service schedulers start after fixed delays: anchor 300 s, summary 600/900 s, retention 1200 s, reconcile 1500 s, quarantine 1800 s, mirror drift 2100 s.
- A script named `*-gate`/`*-lint` is pulled into `gate-wiring-gate --run-all` in CI, so the runner must not use such a name. `frontend/tests/e2e/runs/` is not git-ignored yet.

**Debt:**
- **#289:** the test posts `kind: "arc"`, which `a996750d7` removed from `NodeKind`, so the test is stale.
- **#290:** the test runs `git grep`, which is unavailable in the image.
- **#291:** no workflow runs `internal/migrate`'s DB tests, and none uses `-p 1`.

## Acceptance criteria

| AC | Must be true | Verified by | Rows | Status |
|---|---|---|---|---|
| **AC-1** | The composition unit suite has no red that predates this plan | composition unit suite run in its image + bite of each fix | T1, T2 | ✅ met — Cycle 1: 4014 passed, 0 failed; both fixes bitten |
| **AC-2** | book-service's DB-backed packages, `internal/migrate` included, run green in CI without a deadlock | `.github/workflows/domain-db-smoke.yml` step + local `go test -p 1 ./...` on a throwaway DB | T3 | ✅ met — Cycle 1: the CI command green locally; without `-p 1` it deadlocks |
| **AC-3** | The E2E folder is type-checked, and a type error there fails a check | `tsc -p frontend/tests/e2e/tsconfig.json` in `package.json` + a bite | T4 | ✅ met — Cycle 1: 10 errors fixed, `typecheck:e2e` clean, pre-commit wired, bitten |
| **AC-4** | Every full-suite run records a preflight (clock steps, schedulers due, models loaded, image provenance incl. dirty tree) and its results in one ledger, and a re-run cannot erase an earlier run's traces | `scripts/e2e/run-evidence-suite.py` output + `LEDGER.jsonl` + a deletion bite | T5, T6 | ❌ not met |
| **AC-5** | For any failed test, one command returns its trace, its service-log window, its `llm_jobs` rows and any clock steps in that window | `scripts/e2e/why-red.py` run on a deliberately broken test | T7 | ❌ not met |
| **AC-6** | #288 (DEFERRED #165) is closed only after 5 consecutive clean full runs in the ledger, or diagnosed from a captured trace | `LEDGER.jsonl` entries quoted in the cycle | T8 | ❌ not met |
| **AC-7** | A provider credential can opt in to "serve one model at a time"; off by default; set through the API and the Settings UI | provider-registry handler tests + `ProvidersTab` vitest + live PATCH | T10, T14 | ❌ not met |
| **AC-8** | With the setting on, requests for different models on one endpoint wait for each other instead of colliding; same-model requests still run concurrently; with it off, behaviour is unchanged | lease unit tests (grant/wait/release/aging) + wiring tests on both the job and stream paths | T11, T12 | ❌ not met |
| **AC-9** | An LM Studio model-load abort is retried as contention and never counts toward the breaker, whatever the setting | `Guard`/classification unit tests + a bite | T9, T13 | ❌ not met |
| **AC-10** | Run 4's collision, replayed live with the setting on, ends with both jobs completed; with it off, it reproduces today's failure | live replay on `lw-iso`, `llm_jobs` + extraction status pasted | T15 | ❌ not met |
| **AC-11** | The changelog and the user docs describe the setting, and every issue this plan resolves is closed with its evidence | `CHANGELOG.md`, `changelog-gate.py`, the GitHub issue states | T16 | ❌ not met |
| **AC-12** | The full suite is green through the new runner on rebuilt images | the runner's ledger line for the final run | T17 | ❌ not met |

## Board

### Lane D — debt first (#289, #290, #291, #292)

- [x] **T1** — **#289: `test_create_node_201_and_bad_reference_400` tests the API that exists** (Cycle 1)
  - `services/composition-service/tests/unit/test_outline_canon_routers.py:268-274` posts `kind: "arc"`, removed from `NodeKind` by `a996750d7` ("the API offered two node kinds the database refuses"). Change the payload to `"chapter"`, keeping both claims: 201 on create, and 400 `BAD_REFERENCE` on a bad parent.
  - This is a stale test brought up to date with an earlier, deliberate API change. It is not a test edited to accommodate this plan.
  - Bite: point the create at a kind the DB refuses → 422 again.
  - Log: none (test only).
- [x] **T2** — **#290: `test_nothing_in_the_engine_computes_from_the_undirected_yield` needs no git** (Cycle 1)
  - Replace `git grep` with a Python walk of `services/` (the same file set: tracked sources, skipping caches and virtualenvs), asserting the same three files.
  - Bite: add a reference to `MEASURED_UNDIRECTED_YIELD_WORDS` in a temp file under `services/` → red.
- [x] **T3** — **#291: book-service DB tests run without deadlocking, in CI too** (Cycle 1)
  - `.github/workflows/domain-db-smoke.yml`: also run `internal/migrate`, with `-p 1`. Add a short note on `-p 1` to `services/book-service/README.md`.
  - Verify locally on a throwaway `postgres:18` DB.
- [x] **T4** — **#292: the E2E folder is type-checked** (Cycle 1)
  - Add `frontend/tests/e2e/tsconfig.json` and a `typecheck:e2e` script, wired where the existing `tsc` check runs. Fix `helpers/provider.ts:84` (`is_active`) and `studio-scene-compose.spec.ts:23` (`alias`) by typing the rows correctly, not with `any`.
  - Bite: introduce a type error in a spec → the script fails.

### Lane B — the evidence runner

- [ ] **T5** — **`scripts/e2e/run-evidence-suite.py`: preflight, run, ledger**
  - Named so it is **not** picked up as a gate. Loopback targets only, like `seed-evidence-account.py`.
  - **Preflight** (target ≤ 2 min; **warn and record**, never refuse — Q3):
    - a 60 s wall-vs-monotonic probe inside one `lw-iso` container;
    - each container's `StartedAt` against the scheduler delays table (knowledge-service: 300/600/900/1200/1500/1800/2100 s), listing jobs due within the expected run length;
    - `GET /api/v0/models`, read only (it never loads or unloads a model);
    - image provenance: the `org.loreweave.git_sha` / `build_time` labels and the dirty flag from T6, against the last commit touching each service.
  - **Run:** `npx playwright test --output frontend/tests/e2e/runs/<ts>/results --trace=retain-on-failure`, with the list reporter teed to `runs/<ts>/run.log`.
  - **Ledger:** append to `frontend/tests/e2e/runs/LEDGER.jsonl` one JSON line per test (run id, test id, status, duration), plus one line per run (preflight warnings, image ids, totals). Add `runs/` to `frontend/tests/e2e/.gitignore`, except `LEDGER.jsonl`, which is committed.
  - Log: INFO per preflight check with its measured number; WARN per trap.
- [ ] **T6** — **Images built on this stack say where they came from**
  - `infra/iso.sh build` (or a sibling wrapper) exports `GIT_SHA` / `BUILD_TIME` as `scripts/build-stack.sh` does, and adds a `org.loreweave.git_dirty` label (`true` when the service's build context has uncommitted changes). The preflight (T5) reads it.
  - This catches the locale edits that leaked into the frontend image last plan.
- [ ] **T7** — **`scripts/e2e/why-red.py <run-id> <test-id>`**
  - Output folder: the test's trace path; `collect_run_evidence.py --since` over the test's time window; the `llm_jobs` rows in that window (usage purpose, model, status, error code); any clock steps the preflight recorded near it.
  - Bite: break one assertion on purpose and run it; `why-red` must produce all four parts, and restore.
- [ ] **T8** — **#288 / DEFERRED #165 decided by the ledger**
  - Five consecutive clean full runs through the runner close #288 and mark DEFERRED #165 resolved, with the ledger lines quoted. A red of either test instead gets diagnosed from its captured trace with `why-red`.
  - These runs double as T17's evidence once Lane A lands. Runs before Lane A count only toward #288.

### Lane A — "serve one model at a time", a user setting (#286)

- [ ] **T9** — **Re-verify what opened the breaker in run 4**
  - The breaker counts only transient errors, and the load abort is permanent (`ErrUpstreamPermanent`). Read run 4's `llm_jobs` and provider-registry logs for 19:03:30–19:05:10 UTC 2026-09-18, and name the transient errors that tripped it (timeouts during model thrash? 5xx?).
  - T13's classification is designed from that answer, not from the spec's assumption.
- [ ] **T10** — **The setting exists: `provider_credentials.serve_one_model_at_a_time`**
  - `internal/migrate/migrate.go`: `ALTER TABLE provider_credentials ADD COLUMN IF NOT EXISTS serve_one_model_at_a_time BOOLEAN NOT NULL DEFAULT false`.
  - Accept and return the field on create, list, get and patch (`server.go:1172-1405`), with `*bool` absent-versus-set handling on patch.
  - Extend `Repo.ResolveConcurrency` (or a sibling) to return the flag, the normalized endpoint and the model name.
  - Handler tests: default false; patch true; absent leaves it unchanged.
- [ ] **T11** — **A lease: one model at a time per endpoint, when opted in**
  - `internal/ratelimit/modellease.go`, in the governor's style (a Redis Lua script).
  - Key: the **normalized endpoint URL**, conservative: scheme, lowercased host, port, trailing slash stripped.
  - Holder = the model name, with a refcount. Same-model acquires share it; a different model **waits**. It is a FIFO with an aging bound so neither side starves; the bound is sized here and recorded.
  - Release on completion and on cancel; each holder has a TTL so a crashed caller cannot wedge the endpoint.
  - Fails **open** on a Redis error, like the governor.
  - Unit tests: behind a fake store interface, or add miniredis (decide and record).
- [ ] **T12** — **The lease wraps every call path to an opted-in endpoint**
  - The job path: inside `Guard`'s closure, per attempt, so a retry re-acquires it.
  - The stream path: `stream_handler.go` around `:486`, which today bypasses `Guard`.
  - Other job kinds (audio/image/video/vision) only if they can target an LM Studio endpoint; record the decision.
  - Only when the credential's flag is on. With it off, the path is byte-for-byte today's.
  - Log: INFO on grant (endpoint, model, waited ms), DEBUG on queue position, WARN when the aging bound forces a switch.
- [ ] **T13** — **A model-load abort is contention: retried, breaker-neutral**
  - `provider/errors.go`: recognise LM Studio's `Failed to load model … Engine protocol startup was aborted` as a typed contention error.
  - `Guard`: split its single predicate into *retryable* and *counts-against-health*. Contention is retryable with backoff (under the lease when on) and never counts. Fix the stale comment at `guard.go:53` while there.
  - The retry applies **whatever the setting**. It is a classification, not an enforcement, so it stays within Q2.
  - Bite: remove the classification → the abort fails permanently again.
- [ ] **T14** — **The setting in the UI: Settings → Providers**
  - `features/settings/api.ts` gets the field. `ProvidersTab.tsx` gets a checkbox beside the concurrency field, "Serve one model at a time", with a one-line explanation (for a local server that can hold one model; turning it on makes requests for different models wait for each other). It appears in create and edit and is sent on patch only when changed.
  - i18n keys in all `settings.json` locales (English source; other locales get the English text marked for translation, following the repo's i18n parity gate).
  - Vitest: renders the current value, and a toggle sends `serve_one_model_at_a_time`.
- [ ] **T15** — **Live: run 4's collision, replayed**
  - On `lw-iso`, rebuild provider-registry and the frontend, and confirm the markers in the running containers. Fire a 26B `kg_summary`-style call and a 12B glossary extraction at the same moment on one LM Studio.
  - Once with the setting off: expected today's failure, with the error codes pasted. Once with it on for the credentials involved: both complete.
  - Drop condition (from the spec): the "on" run still ends `completed_with_errors`, or its wall time is more than 2× the two jobs run alone.

### Lane Z — close

- [ ] **T16** — **Docs, changelog, issues**
  - `CHANGELOG.md` `[Unreleased]`:
    - Added: the setting, the evidence runner;
    - Fixed: the load-abort retry and #289–#292.
  - User docs for the setting, in the provider settings help or docs page (path decided here), explaining that it is a hardware choice for a local server.
  - Close #286 and #289–#292 with evidence comments. #288 closes per T8.
- [ ] **T17** — **The full suite through the runner, on rebuilt images**
  - Rebuild every touched image, check nothing was restarted inside a scheduler window (the preflight reports it), and run the full suite through `run-evidence-suite.py`. 0 failed, 0 skipped; any warning is recorded next to the result.

## Commit Plan

Commit at risk boundaries. Run `scripts/doc-language-gate.py --staged` before each.

1. After T1–T4: `test: close the known test debt (#289, #290, #291, #292)`
2. After T5–T7: `feat(e2e): an evidence-first suite runner with a preflight and a ledger`
3. After T9–T10: `feat(provider-registry): the "serve one model at a time" setting`
4. After T11–T13: `feat(provider-registry): sequence models per opted-in endpoint; load aborts are contention`
5. After T14: `feat(frontend): the one-model setting in Settings → Providers`
6. After T8, T15–T17: `docs(plan): replayed live, ledgered, issues closed`

## Rules

1. A fix is proven by re-breaking it.
2. Never edit a test to accommodate a fix. A stale test is brought up to date only with the earlier change that made it stale, named in the cycle.
3. Never delete, skip or `fixme` a test to close a row.
4. Rebuild the image before any E2E run; the composition worker is a separate image. Check the preflight's scheduler window before a full run.
5. "Flaky" is not a verdict.
6. A skip is not a pass.
7. Re-verify every cited premise.
8. `scripts/doc-language-gate.py --staged` before every commit.
9. The platform never loads or unloads a model in LM Studio. The lease only orders requests (PO standing rule).
10. The setting is opt-in and off by default. Nothing enforces one model at a time without the user choosing it (Q2).

## What this plan will NOT do

- Load, unload or pre-warm models in LM Studio.
- Turn "one model at a time" on by default or platform-wide.
- A per-chapter revision sequence (DEFERRED #164, #287); fixing the host's WSL2 clock.
- Quarantine or auto-retry tests into a pass.
- Asynchronous critique (202 + poll).

## Cycles

### Cycle 1 — T1–T4: the known test debt, closed

**Investigated:** each premise from the reconnaissance, re-read:
- **#289:** `a996750d7` narrowed `NodeKind` to `Literal["chapter", "scene"]` (`app/db/models.py:44`); the test still posted `arc`.
- **#290:** the test shelled out to `git grep`, which the image lacks.
- **#291:** `domain-db-smoke.yml` ran only `internal/api`, without `-p 1`.
- **#292:** `frontend/tsconfig.json` includes only `src`.

Once the e2e project was type-checked it showed **10** errors, not the 2 seen before:
- `UserModel` lacked `is_active`;
- `ChatModel` lacked `alias`, read by three specs;
- a self-referencing loop in `manuscript-navigator`;
- `waitProposed`'s result typed as `{status, job_status}` only, so `.arcs` and `.grounded_on` were errors.

**Issues:** #289, #290, #291, #292

**Fix:** one change per row:
- **T1:** the payload is `chapter`, with a comment naming `a996750d7`. Both claims (201; 400 `BAD_REFERENCE`) are tested again, where before validation answered 422 before the handler ran.
- **T2:** a Python walk over `services/` (source extensions; skipping `.git`, `node_modules`, caches, virtualenvs, `dist`, `build`, `target`) makes the same assertion. It takes 12.6 s on the Windows bind mount, recorded.
- **T3:** the CI step runs `internal/api` and `internal/migrate` with `-p 1`, and the reason is in the workflow comment. book-service has no README, so the workflow comment is the documentation (decision).
- **T4:** `frontend/tests/e2e/tsconfig.json` extends the app config with node types; the `typecheck:e2e` script; a pre-commit block that runs it when an e2e file or `playwright.config.ts` is staged. The frontend has no CI type-check job (its `tsc` runs in the image build and in pre-commit for `src`), so pre-commit is where this belongs. The 10 errors were fixed with real types: a `PlanRun` read model and the missing registry fields. No `any` was used.

**Proof:**

```
T1 BROKEN (post `arc` again)            E  assert 422 == 201
T2 BROKEN (a new file references it)    E  AssertionError: a new consumer appeared: [..., 'services/composition-service/app/engine/_bite_probe.py', ...]
restored byte-exact / probe removed     54 passed
composition unit suite, in its image    4014 passed, 45 warnings   (was 4012 passed + 2 failed)

T3 CI command, fresh postgres:18 throwaway DB
   go test -p 1 ./internal/api/... ./internal/migrate/...   ok internal/api 431.379s · ok internal/migrate 33.182s
   BROKEN (no -p 1)   seed draft: ERROR: deadlock detected (SQLSTATE 40P01) · FAIL internal/api

T4 npm run typecheck:e2e             exit 0   (was 10 errors)
   BROKEN (ChatModel without alias)  studio-chapter-assemble / studio-inline-correction / studio-scene-compose: TS2339 'alias'
   restored byte-exact               exit 0
```

`internal/api` took 431 s here, against 41 s on 2026-09-18. That is noted, not investigated; the CI job has its own timeout.

**AC impact:** AC-1 ✅, AC-2 ✅, AC-3 ✅.

```goal-prompt
goal: the known test debt is closed, every full run leaves replayable evidence in one ledger, and "serve one model at a time" is an opt-in user setting proven on a live collision
rules: |
  1 A fix is proven by re-breaking it.
  2 Never edit a test to accommodate a fix; a stale test is updated only with the earlier change that made it stale, named.
  3 Never delete, skip or fixme a test to close a row.
  4 Rebuild images before E2E; check the scheduler window before a full run.
  5 "Flaky" is not a verdict.
  6 A skip is not a pass.
  7 Re-verify every cited premise.
  8 doc-language-gate --staged before every commit.
note: |
  The platform never loads or unloads LM Studio models; the lease only orders requests. The setting is opt-in, default off.
stop: |
  a change would load, unload or pre-warm a model in LM Studio
  a change would make "one model at a time" default-on or enforced
  a write would touch a non-throwaway database
  the ship decision
```
