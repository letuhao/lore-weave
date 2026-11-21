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
| **AC-4** | Every full-suite run records a preflight (clock steps, schedulers due, models loaded, image provenance incl. dirty tree) and its results in one ledger, and a re-run cannot erase an earlier run's traces | `scripts/e2e/run-evidence-suite.py` output + `LEDGER.jsonl` + a deletion bite | T5, T6 | ✅ met — Cycle 2: preflight live (69 s), evidence survives a plain re-run, labels on a real image; 3 bites |
| **AC-5** | For any failed test, one command returns its trace, its service-log window, its `llm_jobs` rows and any clock steps in that window | `scripts/e2e/why-red.py` run on a deliberately broken test | T7 | ✅ met — Cycle 2: all four parts produced for a deliberate red; `llm_jobs` checked on run 4's window |
| **AC-6** | #288 (DEFERRED #165) is closed only after 5 consecutive clean full runs in the ledger, or diagnosed from a captured trace | `LEDGER.jsonl` entries quoted in the cycle | T8 | ❌ not met |
| **AC-7** | A provider credential can opt in to "serve one model at a time"; off by default; set through the API and the Settings UI | provider-registry handler tests + `ProvidersTab` vitest + live PATCH | T10, T14 | ✅ met — Cycle 3 (API, 2 bites) + Cycle 7 (UI, 3 bites; live PATCH through the BFF in Cycle 8) |
| **AC-8** | With the setting on, requests for different models on one endpoint wait for each other instead of colliding; same-model requests still run concurrently; with it off, behaviour is unchanged | lease unit tests (grant/wait/release/aging) + wiring tests on both the job and stream paths | T11, T12 | ✅ met — Cycle 4 (lease, 3 bites) + Cycle 5 (job and stream wiring, 2 bites) |
| **AC-9** | An LM Studio model-load abort is retried as contention and never counts toward the breaker, whatever the setting | `Guard`/classification unit tests + a bite | T9, T13 | ✅ met — Cycle 6: classified on run 4's verbatim body, retried, never counted; 3 bites |
| **AC-10** | Run 4's collision, replayed live with the setting on, ends with both jobs completed; with it off, it reproduces today's failure | live replay on `lw-iso`, `llm_jobs` + extraction status pasted | T15 | ✅ met — Cycle 8: off 1/6 completed (5 × `LLM_CIRCUIT_OPEN`), on 6/6 completed in 25.2 s; margin gap filed as #295 |
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

- [x] **T5** — **`scripts/e2e/run-evidence-suite.py`: preflight, run, ledger** (Cycle 2)
  - Named so it is **not** picked up as a gate. Loopback targets only, like `seed-evidence-account.py`.
  - **Preflight** (target ≤ 2 min; **warn and record**, never refuse — Q3):
    - a 60 s wall-vs-monotonic probe inside one `lw-iso` container;
    - each container's `StartedAt` against the scheduler delays table (knowledge-service: 300/600/900/1200/1500/1800/2100 s), listing jobs due within the expected run length;
    - `GET /api/v0/models`, read only (it never loads or unloads a model);
    - image provenance: the `org.loreweave.git_sha` / `build_time` labels and the dirty flag from T6, against the last commit touching each service.
  - **Run:** `npx playwright test --output frontend/tests/e2e/runs/<ts>/results --trace=retain-on-failure`, with the list reporter teed to `runs/<ts>/run.log`.
  - **Ledger:** append to `frontend/tests/e2e/runs/LEDGER.jsonl` one JSON line per test (run id, test id, status, duration), plus one line per run (preflight warnings, image ids, totals). Add `runs/` to `frontend/tests/e2e/.gitignore`, except `LEDGER.jsonl`, which is committed.
  - Log: INFO per preflight check with its measured number; WARN per trap.
- [x] **T6** — **Images built on this stack say where they came from** (Cycle 2)
  - `infra/iso.sh build` (or a sibling wrapper) exports `GIT_SHA` / `BUILD_TIME` as `scripts/build-stack.sh` does, and adds a `org.loreweave.git_dirty` label (`true` when the service's build context has uncommitted changes). The preflight (T5) reads it.
  - This catches the locale edits that leaked into the frontend image last plan.
- [x] **T7** — **`scripts/e2e/why-red.py <run-id> <test-id>`** (Cycle 2)
  - Output folder: the test's trace path; `collect_run_evidence.py --since` over the test's time window; the `llm_jobs` rows in that window (usage purpose, model, status, error code); any clock steps the preflight recorded near it.
  - Bite: break one assertion on purpose and run it; `why-red` must produce all four parts, and restore.
- [ ] **T8** — **#288 / DEFERRED #165 decided by the ledger**
  - Five consecutive clean full runs through the runner close #288 and mark DEFERRED #165 resolved, with the ledger lines quoted. A red of either test instead gets diagnosed from its captured trace with `why-red`.
  - These runs double as T17's evidence once Lane A lands. Runs before Lane A count only toward #288.

### Lane A — "serve one model at a time", a user setting (#286)

- [x] **T9** — **Re-verify what opened the breaker in run 4** (Cycle 3 — answered as far as the evidence goes; the rest is instrumented in T13)
  - The breaker counts only transient errors, and the load abort is permanent (`ErrUpstreamPermanent`). Read run 4's `llm_jobs` and provider-registry logs for 19:03:30–19:05:10 UTC 2026-09-18, and name the transient errors that tripped it (timeouts during model thrash? 5xx?).
  - T13's classification is designed from that answer, not from the spec's assumption.
- [x] **T10** — **The setting exists: `provider_credentials.serve_one_model_at_a_time`** (Cycle 3; the `ResolveConcurrency` extension moves to T12, where it is used)
  - `internal/migrate/migrate.go`: `ALTER TABLE provider_credentials ADD COLUMN IF NOT EXISTS serve_one_model_at_a_time BOOLEAN NOT NULL DEFAULT false`.
  - Accept and return the field on create, list, get and patch (`server.go:1172-1405`), with `*bool` absent-versus-set handling on patch.
  - Extend `Repo.ResolveConcurrency` (or a sibling) to return the flag, the normalized endpoint and the model name.
  - Handler tests: default false; patch true; absent leaves it unchanged.
- [x] **T11** — **A lease: one model at a time per endpoint, when opted in** (Cycle 4)
  - `internal/ratelimit/modellease.go`, in the governor's style (a Redis Lua script).
  - Key: the **normalized endpoint URL**, conservative: scheme, lowercased host, port, trailing slash stripped.
  - Holder = the model name, with a refcount. Same-model acquires share it; a different model **waits**. It is a FIFO with an aging bound so neither side starves; the bound is sized here and recorded.
  - Release on completion and on cancel; each holder has a TTL so a crashed caller cannot wedge the endpoint.
  - Fails **open** on a Redis error, like the governor.
  - Unit tests: behind a fake store interface, or add miniredis (decide and record).
- [x] **T12** — **The lease wraps every call path to an opted-in endpoint** (Cycle 5 — job + stream paths; vision recorded as not wired)
  - The job path: inside `Guard`'s closure, per attempt, so a retry re-acquires it.
  - The stream path: `stream_handler.go` around `:486`, which today bypasses `Guard`.
  - Other job kinds (audio/image/video/vision) only if they can target an LM Studio endpoint; record the decision.
  - Only when the credential's flag is on. With it off, the path is byte-for-byte today's.
  - Log: INFO on grant (endpoint, model, waited ms), DEBUG on queue position, WARN when the aging bound forces a switch.
- [x] **T13** — **A model-load abort is contention: retried, breaker-neutral** (Cycle 6)
  - `provider/errors.go`: recognise LM Studio's `Failed to load model … Engine protocol startup was aborted` as a typed contention error.
  - `Guard`: split its single predicate into *retryable* and *counts-against-health*. Contention is retryable with backoff (under the lease when on) and never counts. Fix the stale comment at `guard.go:53` while there.
  - The retry applies **whatever the setting**. It is a classification, not an enforcement, so it stays within Q2.
  - Bite: remove the classification → the abort fails permanently again.
- [x] **T14** — **The setting in the UI: Settings → Providers** (Cycle 7)
  - `features/settings/api.ts` gets the field. `ProvidersTab.tsx` gets a checkbox beside the concurrency field, "Serve one model at a time", with a one-line explanation (for a local server that can hold one model; turning it on makes requests for different models wait for each other). It appears in create and edit and is sent on patch only when changed.
  - i18n keys in all `settings.json` locales (English source; other locales get the English text marked for translation, following the repo's i18n parity gate).
  - Vitest: renders the current value, and a toggle sends `serve_one_model_at_a_time`.
- [x] **T15** — **Live: run 4's collision, replayed** (Cycle 8)
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

### Cycle 2 — T5, T6, T7: every run leaves evidence, and one command assembles it

**Investigated:** how Playwright, `iso.sh` and the build contexts behave today:
- **Playwright:** `outputDir` is `tests/e2e/test-results`, which each run clears; the JSON reporter carries each result's `startTime` and attachment paths.
- **`iso.sh`** exported no `GIT_SHA`, so every image it built was labelled `unknown`, and nothing recorded a dirty tree.
- **Build contexts:** many services build with the **repo root** as context, so the dirty check needs a narrower scope.
- **Two things met on the way:**
  - from Python on Windows, `bash` resolves to WSL's `bash.exe`, not Git Bash, so calling `iso.sh config` from the runner silently returned nothing;
  - a rebuild can remove the old image from the store while its container keeps running it.

**Issues:** none — tooling for #288 and the lane's own evidence; nothing product-facing

**Fix:** three pieces.
- **`scripts/e2e/run-evidence-suite.py`**
  - **Preflight**, which warns and records, never refuses (Q3):
    - a 60 s wall-vs-monotonic clock probe inside the composition container;
    - the schedulers due in the run window, from each container's `StartedAt` and the knowledge-service delay table;
    - the models LM Studio has loaded (a read);
    - image provenance **for the image the container runs** (by id, not tag): git sha against HEAD, commits since that touch the build scope, the dirty scope overlapping it, and "replaced by a rebuild".
  - **The run** uses `--output runs/<id>/results`, `--trace=retain-on-failure`, and list + JSON reporters.
  - **`LEDGER.jsonl`** gets one row per test (status, duration, start, attachments) and one per run (totals, warnings, image shas, clock steps).
  - It has a `--self-test` (13 checks). It is not named `*-gate`, is loopback-only, and writes to no database. `runs/*` is ignored, except `LEDGER.jsonl`, which is committed.
- **`infra/iso.sh` + `docker-compose.yml`**
  - They export `GIT_SHA`, `BUILD_TIME` and a new `GIT_DIRTY_SCOPE`: the top-two-level paths with uncommitted tracked changes, or `clean`.
  - A new `org.loreweave.git_dirty_scope` label.
  - For repo-root contexts, the runner scopes the dirty check to the Dockerfile's directory plus `sdks/`.
- **`scripts/e2e/why-red.py <run|latest> "<title part>"`** writes the test's trace paths, every `lw-iso` container's log lines in the test's window (±15 s) with a merged timeline, the `llm_jobs` rows started in that window, and the preflight's clock steps. It has a `--self-test` (4 checks) and is read-only.

**Proof:**

```
preflight (live, lw-iso)   69 s · WARN wall clock stepped BACK 2x in 60s (largest -1.867s)
                            34 image warnings: every running image predates T6 ("no git sha label")
dirty scope, live           'frontend/src,frontend/tests,infra/docker-compose.yml,infra/iso.sh'
                            — frontend/src is the uncommitted locale edits that leaked into a test image last plan
real image via iso.sh       lw-iso-auth-service: git_sha aeeb84a0f7…, build_time 2026-09-19T05:03:22Z, git_dirty_scope set
T6 BROKEN (export removed)  {'build_time': 'unknown', 'git_dirty_scope': 'unknown', 'git_sha': 'unknown'}
   restored byte-exact      labels populated again

rebuilt image, old container still running
   WARN auth-service: the container runs an image that was replaced by a rebuild — restart it
   after `iso.sh up -d --no-deps auth-service`: no warning

AC-4 BITE — a deliberately failing test through the runner, then a PLAIN Playwright re-run
   runner   1 failed · evidence runs/20260919T050112Z/results/…/{trace.zip,test-failed-1.png,video.webm,error-context.md}
   plain    1 passed · tests/e2e/test-results/ now EMPTY (cleared, as every plain run does)
   runner's evidence after that: still trace.zip, test-failed-1.png, video.webm, error-context.md
   ledger: {"kind": "test", … "status": "failed" …} + {"kind": "run", … "exit": 1, "totals": {"failed": 1} …}
   spec restored byte-exact (cmp)

T7 — why-red latest "bottom panel" on the deliberate red
   trace   …/runs/20260919T050235Z/results/writing-studio-…-chromium/trace.zip
   logs    594 line(s) from the stack in 05:02:32..05:03:09 UTC
   llm     0 job(s)       (that test makes no LLM call; the query checked on run 4's window returns
                           kg_summary / glossary_extraction … "Engine protocol startup was aborted")
   clock   []
self-tests   run-evidence-suite 13 ok · why-red 4 ok
```

The ledger keeps the two deliberate reds above as what they were: partial, spec-limited runs with a failure. T8 counts only full runs.

**AC impact:** AC-4 ✅, AC-5 ✅.

### Cycle 3 — T9, T10: what opened the breaker, and the setting exists

**Investigated:** run 4's `llm_jobs` in 19:04:15–19:04:40 UTC 2026-09-18, the breaker configuration, and provider-registry's logs.

```
19:04:24  01a09c79… (iso-evidence 12B)  glossary_extraction  completed
19:04:26  019ebb72… (other account 26B) kg_summary           failed  LLM_UPSTREAM_ERROR  HTTP 400 … "Failed to load model … gemma-4-26b … Engine protocol startup was aborted"
19:04:26  01a09c79…                     glossary_extraction  failed  LLM_UPSTREAM_ERROR  HTTP 400 … "Failed to load model … gemma-4-12b …"
19:04:30  019ebb72…                     kg_summary           failed  LLM_UPSTREAM_ERROR  (26B load abort)
19:04:31  01a09c79…                     glossary_extraction  failed  LLM_UPSTREAM_ERROR  (12B load abort)
19:04:32  019ebb72…                     kg_summary           completed
19:04:36  01a09c79…                     glossary_extraction  failed  LLM_CIRCUIT_OPEN    provider circuit open
breaker: BREAKER_THRESHOLD 5 in BREAKER_WINDOW_S 60, cooldown 30 s (config.go:214-222)
provider-registry log: 604 lines in total since 2026-09-13 — it logs no per-call or per-attempt line
```

**What this proves, and what it does not:**
- The 12B credential recorded only **two** failed jobs before its circuit opened, and both were the *permanent* 400. `Guard` does not count those. It counts only errors `IsTransientUpstreamError` accepts, and the breaker needs 5 within 60 s.
- So at least five **transient attempt failures** happened *inside* jobs, retried by `retryTransient`. They never reach `llm_jobs` and are not logged anywhere. The spec's claim ("the load abort opens the breaker") is wrong; this run corrects it.
- **Which** transient failure LM Studio returned during the swap cannot be recovered from what was kept. **Decision:** T13 adds a WARN line per failed attempt (status, error class, body excerpt) and designs its classification from the first live replay (T15), not from a guess.

**Issues:** #286

**Fix:** T10 only (T9 is the investigation above, and it changed T13's design).
- `internal/migrate/migrate.go`: `ALTER TABLE provider_credentials ADD COLUMN IF NOT EXISTS serve_one_model_at_a_time BOOLEAN NOT NULL DEFAULT false`, with the reason: a statement about the user's hardware, never assumed by the platform.
- `internal/api/server.go`:
  - create accepts `*bool` (absent → false);
  - list and get return the field;
  - patch uses `COALESCE($11, serve_one_model_at_a_time)`, so an absent field keeps the user's choice.
- New `internal/api/one_model_setting_test.go`, DB-gated like the other integration tests:
  1. default false;
  2. patch true;
  3. an unrelated patch keeps true;
  4. the list shows it;
  5. patch false.

**Proof:**

```
TestServeOneModelAtATime_IsOptIn_AndPatchKeepsWhatTheUserChose   PASS (throwaway loreweave_provider_registry_test)
BROKEN (default on)              one_model_setting_test.go:45: a new credential must default to false, got true
BROKEN (unrelated patch resets)  one_model_setting_test.go:60: an unrelated patch reset the setting: … serve_one_model_at_a_time:false …
restored byte-exact (cmp)        PASS
provider-registry go test ./...  api · billing · chunker · jobs · migrate · provider · ratelimit — all ok
```

**AC impact:** AC-7 🚧 (API side; the UI is T14). AC-9 re-scoped by T9 — its evidence comes from T13 + T15.

### Cycle 4 — T11: the lease — different models on one endpoint take turns

**Investigated:** the governor's shape (`governor.go`): a Redis Lua script with lease-scored tokens, fail-open on a Redis error, and a release func. No Redis test harness existed (the tests used fakes), and fakes would test a re-implementation, not the script. **Decision:** add `github.com/alicebob/miniredis/v2`, test-only in effect, which runs the real Lua script in-process.

**Issues:** #286

**Fix:** new `internal/ratelimit/modellease.go`.
- **`NormalizeEndpoint`**: scheme, lowercased host, explicit port, no path. It is conservative: `host.docker.internal` and `127.0.0.1` stay distinct.
- **The Redis state**, per endpoint: a holder model, lease-scored holder tokens, a FIFO wait queue with the model each waiter wants, and a waiter heartbeat.
- **One atomic Lua decision:**
  - expired holders are pruned, and so are waiters that stopped polling;
  - when free, the oldest waiter's model goes next;
  - the same model shares the lease, unless another model's oldest waiter has passed the **aging bound**;
  - a different model waits.
- **Defaults:** lease 15 min, wait 10 min (`ErrModelLeaseTimeout`, retryable), aging bound 2 min, poll 100 ms. It fails **open** on a Redis error.
- **Logging:** INFO on grant (with waited ms) and on the first wait; WARN on fail-open; DEBUG on release.
- It never loads or unloads a model; it only orders calls (Rule 9). Nothing uses it yet; T12 wires it behind the credential's opt-in.

**Proof:**

```
TestModelLease_SameModelCallsShareTheEndpoint               PASS
TestModelLease_ADifferentModelWaitsUntilTheHolderFinishes   PASS
TestModelLease_OtherEndpointsDoNotWait                      PASS
TestModelLease_AgingStopsTheHeldModelFromStarvingAWaiter    PASS
TestModelLease_ACrashedHolderFreesItself                    PASS
TestModelLease_TimesOutAsRetryable                          PASS
TestModelLease_FailsOpenWhenRedisIsDown                     PASS
TestNormalizeEndpoint                                       PASS

BROKEN (a different model granted while one is held)
  modellease_test.go:60: a call for a DIFFERENT model ran while another model held the endpoint — the collision #286 is about
BROKEN (no aging bound)
  modellease_test.go:103: a new call for the held model jumped a waiter that had passed the aging bound
BROKEN (expired holders never pruned)
  modellease_test.go:122: an expired holder must not wedge the endpoint: model lease: timed out waiting for another model to finish on this endpoint
restored byte-exact (cmp) — internal/ratelimit ok
```

**AC impact:** AC-8 🚧 — the lease rules are proven; the wiring on the job and stream paths is T12.

### Cycle 5 — T12: the lease on every chat call to an opted-in endpoint

**Investigated:** every provider-call path, and how error codes are consumed downstream:
- **The job path:** `Worker.Process` resolves the credentials, then `ResolveConcurrency`; `processChunks` and `streamWithRetry` wrap each attempt in `Guard` inside `retryTransient`.
- **The stream path:** `/v1/llm/stream`'s `streamChat` calls `adapter.Stream` directly, and its credential query is separate.
- **Existing error codes:** consumers special-case only `LLM_CIRCUIT_OPEN`, which auto-pauses campaigns. The Python SDK's `TRANSIENT_RETRY_CODES` is `{LLM_RATE_LIMITED, LLM_UPSTREAM_ERROR}`.
- **Other job kinds:** audio, image and video have no LM Studio route. Vision could reach an LM Studio multimodal model, but runs through its own adapter outside `Guard`.

**Issues:** #286

**Fix:** the lease on both chat paths, behind the credential's opt-in:
- **`jobs/repo.go`:** `ResolveServeOneModel` reads the credential's opt-in. It is false for platform models, because the setting describes the user's own hardware.
- **`jobs/worker.go`:**
  - a `ModelLeaser` interface and `WithModelLease`;
  - `Process` marks the job's context only when the credential opted in, and a failed lookup falls back to today's behaviour;
  - `callProvider` takes the lease **inside `Guard`, per attempt**, after the concurrency slot, so a retry re-acquires it. With no mark it is exactly `fn()`.
- **Error code:** a lease timeout is its own code, `LLM_MODEL_BUSY`, deliberately **not** added to the SDK's retry list. It means another model held the endpoint for the whole wait; the aging bound makes that rare, and an automatic resubmit would queue behind the same model again.
- **`api/server.go` + `config/config.go`:** the lease is built with the governor when `REDIS_URL` is set. Tunables: `MODEL_LEASE_TTL_S` 900, `MODEL_LEASE_WAIT_S` 600, `MODEL_LEASE_AGING_S` 120.
- **`api/stream_handler.go`:** the stream path reads `serve_one_model_at_a_time` with its credential, and takes the lease around `adapter.Stream`. A timeout emits an `LLM_MODEL_BUSY` error frame without calling the provider.
- **Vision, not wired (decision):** the gap is recorded for the user docs (T16).

**Proof:**

```
jobs   TestModelLease_HeldAroundTheCall_WhenTheCredentialOptedIn   PASS  (the fake provider fails unless the lease is held at call time)
       TestModelLease_NotTaken_WithoutTheOptIn                     PASS
       TestModelLease_ChunkedJobsTakeItPerChunk                    PASS  (3 chunks, 3 acquires, 3 releases)
       TestModelLease_TimeoutIsItsOwnErrorCode                     PASS  (LLM_MODEL_BUSY, provider never called)
api    TestStreamChat_OptedIn_WaitsForAnotherModel_ThenReportsBusy PASS
       TestStreamChat_OptedIn_SameModelRunsAlongside               PASS
       TestStreamChat_NotOptedIn_IsUntouched                       PASS
BROKEN (job path never takes the lease)
       model_lease_wiring_test.go:56: unexpected err provider called without the model lease held
BROKEN (stream path ignores the lease)
       stream_model_lease_test.go:51: … must wait and then say the model is busy; body="event: token … PROSE …"
restored byte-exact (cmp) · go test ./... (throwaway DB): api billing chunker jobs migrate provider ratelimit — all ok
```

`Process`'s own lookup (DB-backed) is proven live in T15 rather than by a unit test, because it needs a job row and a credential. That is recorded, not skipped.

**AC impact:** AC-8 ✅.

### Cycle 6 — T13: a model-load abort is contention; and the log that was never written

**Investigated:** why T9 found no trace of the failed attempts. `retryTransient` logs every retry at INFO, `JOB_MAX_RETRIES=3` and `REDIS_URL` are set on the running container, and `SetupLogging` writes JSON to stdout at INFO. Yet provider-registry's log ends at **2026-09-18 01:23**, although the container has run since 15:35 that day and has handled thousands of jobs.

```
docker inspect   restarts=0 started=2026-09-18T15:35:16Z logdriver=json-file ; /proc/1/fd/1 -> pipe
docker exec … echo "LOGPROBE-2026-09-19 marker" > /proc/1/fd/1   →   docker logs --since 2m | grep -c LOGPROBE   =  0
same probe window, composition-service                            →   158 lines
```

Docker was not capturing provider-registry's stdout at all. Every retry and error line of run 4 was lost, which is why T9 could only prove *that* transient attempts failed, not *which*. Postgres and rabbitmq, started in the same `up -d` at 15:35, show the same silence; the containers restarted since then log normally. This is an environment fault of the local Docker, not of any service. The runner now detects it before a run.

**Issues:** #286

**Fix:** four changes.
- **`provider/errors.go`:**
  - `ErrUpstreamModelContention`: a 4xx whose body contains **both** `Failed to load model` and `Engine protocol startup was aborted`, so a real bad model name stays permanent;
  - `IsRetryableUpstreamError` = transient **or** contention;
  - `ErrorClass` for logs.
- **`jobs/retry.go`:** `retryTransient` retries on `IsRetryableUpstreamError`, and logs **every** failed attempt at WARN with its class and whether it is retryable. `Guard` still counts only `IsTransientUpstreamError`, so contention never reaches the breaker, whatever the credential's setting. It is a classification, not an enforcement (Q2).
- **`ratelimit/guard.go`:** the stale comment that called a governor timeout "treated as transient" now says what happens.
- **`scripts/e2e/run-evidence-suite.py`:** a new **log-liveness** preflight check. It flags a container up for more than 10 minutes with zero log lines since it started, and says to recreate it before a run you need to explain.
- The stream path (`/v1/llm/stream`) does not retry; with the setting on, the lease keeps it from colliding at all.

**Proof:**

```
TestLoadAbort_IsContention_RetryableButNotAHealthFailure   PASS  (run 4's body, verbatim)
TestOtherModelLoadFailures_StayPermanent                   PASS
TestContention_IsRetried_ThenSucceeds                      PASS  (3 attempts)
TestContention_NeverCountsTowardTheBreaker                 PASS  (10 contentions, 0 breaker failures)
BROKEN (not classified)    contention_test.go:19: the load-abort 400 must classify as contention, got permanent
BROKEN (not retried)       contention_test.go:22: contention must be retried … · TestContention_IsRetried_ThenSucceeds FAIL
BROKEN (counted as health) contention_test.go:25: contention must NOT be a health failure … · TestContention_NeverCountsTowardTheBreaker FAIL
restored byte-exact (cmp) · go test ./… (throwaway DB): all 7 packages ok

preflight, live:  WARN lw-iso-provider-registry-service-1: up 831 min and NOTHING in its log since it started …
                  (also lw-iso-rabbitmq-1, lw-iso-postgres-1)
```

**AC impact:** AC-9 ✅. AC-4 is strengthened: the preflight now also reports lost logs.

### Cycle 7 — T14: the setting in Settings → Providers

**Investigated:** how the Providers tab edits a credential. The edit dialog already sends only the fields that changed (the `max_concurrency` pattern), and a source-scan test requires `autoComplete` on every input in the settings forms.

**Issues:** #286

**Fix:** the UI side of the setting.
- `features/settings/api.ts`: `serve_one_model_at_a_time` on the provider type and on the create and patch payloads.
- `ProvidersTab.tsx`: a checkbox in the add dialog (`provider-add-one-model`) and in the edit dialog (`provider-edit-one-model`), with a one-line hint. The edit dialog shows the stored value and sends the field only when the user changed it. Create sends it only when ticked. The checkbox always starts unticked, so the UI can never turn the setting on by itself (Q2).
- `en/settings.json`: `one_model` and `one_model_hint` in both dialogs. The other 17 locales were filled by `scripts/i18n_translate.py --ns settings` (4 keys each, 0 failed); both i18n gates pass.

**Proof:**

```
ProvidersTab.oneModel.test.tsx   3 passed · src/features/settings: 11 files, 69 tests passed
BROKEN (dialog ignores the stored value)  × an unrelated edit does not send the setting at all
BROKEN (field always sent on patch)       × an unrelated edit does not send the setting at all
BROKEN (add dialog defaults to on)        × a new provider is created with it OFF unless the user ticks it
restored byte-exact (cmp)
```

**AC impact:** AC-7 ✅ with Cycle 8's live PATCH through the BFF.

### Cycle 8 — T15: run 4's collision, replayed live

**Investigated:** whether the replay can use plain chat jobs. Every background caller (glossary extraction, resummarize, distill, the composition FSM) submits `operation="chat"` to `/v1/llm/jobs` (`jobs/repo.go:528`), so a chat job takes the same worker, `Guard`, retry and lease path as run 4's two jobs. The replay (a scratch script) logs in through the BFF, sets the credential's setting with a PATCH through the BFF, submits 3 × gemma 12B and 3 × gemma 26B at the same instant to one LM Studio on provider-registry directly (the BFF does not route `/v1/llm/jobs`), and resets the setting to off at the end. It never loads or unloads a model; each load is caused by the product's own job. provider-registry was rebuilt at 57e85e678 and recreated first, so its log is captured again (Cycle 6).

**Issues:** #286, #295 (new: found by this replay)

**Fix:** none in code; this cycle is the live proof. It found one gap. LM Studio answers a model swap not only with the 400 that T13 classifies, but also with **HTTP 500 `Internal Server Error`** (an HTML body). That is classified `transient` and counts toward the breaker. With the setting off, this is what opened the breaker. With it on, the swap still produced four 500s, and the retry recovered them only because 4 < the breaker threshold of 5. Filed as #295 with three options. Classifying every 500 as contention would blind the breaker to a real server fault, so it is a decision, not a fix to make inside this row.

**Proof:**

```
llm_jobs (usage_purpose=t15_replay), provider-registry DB on lw-iso:
05:36:10 solo-12b  completed  16.1 s      05:36:26 solo-26b  completed  14.9 s
--- setting OFF, 05:36:48 ---
off-12b-0 completed 13.9 s · off-12b-1/2, off-26b-0/1/2  failed LLM_CIRCUIT_OPEN (1.0-5.8 s)
log: 6 × "upstream attempt failed" class=transient HTTP 500, then "provider circuit open" × 5
--- setting ON, 05:37:33 ---
on-12b-0/1/2 completed 1.9 s · on-26b-0/1/2 completed 22.6-22.8 s   → 6/6, wall 25.2 s (drop bound: 2 × solo ≈ 64 s)
log: "model lease: granted" 12b × 3 (waited 0-1 ms) · "waiting for another model to finish" 26b × 3
     "model lease: granted" 26b × 3 waited_ms 1915-1917 · 4 × transient HTTP 500 during the swap, retried, circuit stayed closed
PATCH through the BFF: serve_one_model_at_a_time = True … = False (reset)
```

**AC impact:** AC-10 ✅: off reproduces the failure, on completes every job well inside the drop bound. AC-7 ✅ (the live PATCH). The margin under the breaker threshold is recorded as #295, not hidden.
