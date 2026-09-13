# Ship proof — clear the leftovers, then record the whole product for a person to judge

Reconciles: Plan Acceptance Criteria · Non-Vacuity · Remediation Cycle — this plan adds no rule.
It APPLIES them to the last question in front of v0.1.0, and NV-6 is the reason its output is a
recording rather than a summary: a report a person cannot disagree with is not evidence.

> **NOT APPROVED — a draft for the PO.** It exists because of a direct instruction:
>
> > *"make new plan to clear overleft problems / then do a full human simulation testing and store
> > video/image evidence / i need them to build allure report or something / so i can review and
> > prove this platform really to ship / this is long term task / do this seriously"*
>
> **Nothing here ships anything.** The tag is the PO's. This plan's job is to leave them looking at
> the product, not at a claim about the product.

## The state this starts from, measured 2026-09-13

Twenty recorded cycles closed T1–T10 of
[the ship plan](2026-09-13-v0.1.0-ship-acceptance.md). What is left is smaller than the issue list
suggests, and saying which is the first job:

| Open issue | Actually |
|---|---|
| #248 `datasets`, #249 react-router, #250 `rsa`, #251 changelog, #253 DefaultModelsCard, #254 lockfile, #255 pgvector, #256 skip-as-green, #258 beat purposes, #259 Campaigns terminology | **fixed and unclosed** — #253's five tests pass, #250 is out of the build graph, #259's word is gone from the tree |
| #257 seven untranslated strings | **1 fixed, 6 adjudicated** by `--retry-echoed` and left as baseline |
| #247 gateway NestJS 12 | **genuinely open** — a CommonJS→ESM migration of four request-path services, not v0.1.0 work |

**Ten stale issues is not housekeeping.** An issue list where most entries are already done is a
list nobody reads, and the next real defect files into it and disappears. That is the same failure
mode as a gate that goes red and stays red.

### The leftovers that are real

1. **Two recorded journeys fail.** `composition-journey` — the AC-10 shape — stops at a
   model-dependent reasoning control after clearing six steps. `studio-compose` does not mount the
   chat panel from the command palette.
2. **A clean machine cannot run the model-gated journeys.** Five blockers were removed by hand to
   record one run; one of them (`/onboarding` vs `/books`) is a harness defect **the first
   human-sim run already reported and nobody fixed**.
3. **Only 13 of 225 tests have ever been recorded.** The rest pass invisibly.
4. **Sixteen locales have never been read by a person**, and no reader is available for them.
5. **T17 is partial** — three toolloop seed assertions were corrected but the scenarios were never
   re-run, because they need a stack, a book, a Work and a minted token.
6. **AC-4's MinIO leg has never been observed**; it is scope-guarded to main-targeted PRs.
7. **AC-12 exercised rollback on one service of 33**, with no data written across the boundary.

## Acceptance criteria

| AC | Must be true | Verified by | Rows | Status |
|---|---|---|---|---|
| **AC-1** | The issue list contains only open problems | every issue closed with the commit that fixed it, or left open with a reason | S1 | ✅ met — 12 open → 2, each closure carrying its evidence; both survivors have a named blocker |
| **AC-2** | A clean machine can run the whole suite without hand-holding | the seed script run against a stack with **fresh volumes** — not a reused one — and the pass rate after | S2, S8 | ❓ unknown |
| **AC-3** | Every test is recorded, and every test that did NOT run is counted — a SKIP is reported as unanswered, never folded into a pass | `evidence-capture-gate.py` plus an explicit skip count | S3 | ❓ unknown |
| **AC-4** | A person can open one report and see every journey, and watch any of them | Allure, opened cold and navigated without a guide | S4 | ❓ unknown |
| **AC-5** | Every failure is CLASSIFIED — a product defect, or an environment/fixture gap — and every product defect has an issue | the failure table, each row carrying its evidence | S5, S8 | ❓ unknown |
| **AC-6** | The report says what is NOT covered as plainly as what is | the coverage map, with its holes | S6 | ❓ unknown |
| **AC-7** | The PO can reach a GO or NO-GO from the report alone | their own words, recorded | S7 | ❓ unknown |
| **AC-8** | A red result is reproducible — the same test fails the same way twice | the same suite run twice, the diff between them | S8 | ❓ unknown |
| **AC-9** | The evidence does not enter git history | the artefact directories ignored, and the report's size stated | S9 | 🚧 partial — all four directories now ignored (`allure-*` were not, and would have committed thousands of files). The run's measured size is still owed |

**AC-7 is not something this plan can tick.** It is the condition under which the plan is finished,
and only the PO closes it.

## Board

- [x] **S1** — Close what is done; leave what is not. *(AC-1)*
  Ten issues are fixed and open. Each gets closed against the commit that fixed it, or a comment
  saying why it stays. #247 stays open with its measured scope.
  **DONE.** Ten closed against the evidence that fixed them; **two remain and both are real** —
  #257 (six strings needing `ru`/`bn`/`ja`/`th` readers) and #247 (the ESM migration).

- [ ] **S2** — A seed path a clean machine can follow. *(AC-2)*
  Recording one run took removing five blockers by hand. That is not reproducible and it is not
  written down. This turns it into something checked in and runnable — account, BYOK model,
  onboarding flag — and the `/onboarding` vs `/books` harness defect gets fixed rather than
  worked around, because the next person will hit it too.
  **The audit tightened what "clean" means.** The seeder was first proved against a stack that
  already had the account (`register -> 409`), which proves the idempotent path and NOT the
  first-run path. `lw-iso`'s volumes are not fresh either — one owner holds 308 books. So the bar is
  a stack with **fresh volumes** (`iso.sh down -v`), which is destructive and therefore the PO's
  call to authorise.
  Evidence: the seed run against fresh volumes, and the suite's pass rate on the far side of it.

- [ ] **S3** — Record the WHOLE suite, not a sample. *(AC-3)*
  225 tests across 76 specs, with `PLAYWRIGHT_EVIDENCE=1`. Expect this to be slow and expect
  failures; both are information. `evidence-capture-gate.py` must pass over the result, so a run
  that captured nothing cannot be reported as a run.

  **The audit caught this row excusing exactly what this repo spent the day fixing.** It originally
  said *"every test that RUNS is recorded"*, which silently forgives a skip — and **19 of the 76
  specs contain `test.skip()`**, almost all of them model- or stack-gated. A suite that skips eighty
  tests and records the rest would satisfy that wording while answering nothing, which is the
  `GATE_SKIP_RC` lesson arriving from the other direction. **A skip is reported as UNANSWERED and
  counted in its own column**, never folded into a pass.
  Evidence: the capture gate's artefact count, AND passed / failed / skipped stated separately.

- [ ] **S4** — Allure. *(AC-4)*
  The PO asked for it by name. `allure-playwright` as an opt-in reporter plus the CLI (Java 24 is
  present; **CI has none**, so it must not become a required dependency of the normal run).
  Evidence: the generated report opened, with a named journey watched start to finish.

- [ ] **S5** — Every red diagnosed or named. *(AC-5)*
  A failure list with a cause each. **"Flaky" is not a cause.** Anything undiagnosed is recorded as
  undiagnosed, with its trace, rather than being retried until it passes.
  Evidence: one line per failure; a defect that is the product's gets its own issue.

- [ ] **S6** — What is not covered. *(AC-6)*
  The 76 specs mapped to product areas with the holes named — `persona` is 2 of 225, and the other
  223 assert that a control works, not that a person can finish a book.
  Evidence: the map, in the report the PO opens.

- [ ] **S7** — Hand it over. *(AC-7)*
  The report, the coverage map, the failure list, and the standing AC-10 verdict in one place.
  Evidence: **the PO's own words.** No row ticks this.

- [ ] **S8** — The differential: two runs, and the delta is the answer. *(AC-2, AC-5, AC-8)*
  **This row exists because the audit found the plan would have misled the PO.** A first pass of the
  full suite, with a MINIMAL seed, came back **40 passed / 23 failed / 2 skipped** over its first 65
  tests — a ~35% failure rate. Handing that to someone as "the product" would say the wrong thing,
  because the failures were not the product:

```
TimeoutError: locator.click: waiting for getByTitle('Send')
  locator resolved to <button DISABLED data-testid="chat-send-button" ...>
```

  A disabled send button, because the account had a model REGISTERED but none SELECTED.
  `docs/dev/LOCAL_TEST_ENV.example.md` says it outright — *"user_default_models is typically empty
  on a fresh account"*. The seeder now sets the `chat` and `composer` defaults.

  So the method is a **differential, not a single number**: run the suite under the minimal seed and
  again under the full seed, on the same commit and the same stack. A test that fails BOTH times is
  a candidate product defect. A test that fails only under the minimal seed is an
  environment-dependency — which is a finding about *portability*, not about the product, and the
  two must never be added together.
  Evidence: both result sets and the diff between them, with every test named in exactly one column.

- [x] **S9** — Where the evidence lives. *(AC-9)*
  225 tests × video is large. `test-results/` and `playwright-report/` are already ignored in
  `frontend/tests/e2e/.gitignore`; **`allure-results/` and `allure-report/` are NOT**, so the first
  Allure run would commit thousands of files into history, where they cannot be removed later
  without a rewrite. Ignore them, and state the report's real size so the PO knows what they are
  opening.
  **DONE for the ignore half.**

```
test-results         IGNORED      allure-results       IGNORED   <- was NOT
playwright-report    IGNORED      allure-report        IGNORED   <- was NOT
```

  The size half is owed until a full run finishes; the 13-test sample was 20 MB, so 225 will
  not be small.

## What this plan will NOT do

- **It will not make a red test green by relaxing it.** A journey that fails is the finding.
- **It will not judge the prose, the translations, or the product.** It puts them on a screen.
- **It will not run against anything but loopback**, and never against the stack the PO is using.
- **It will not tag, build or publish anything.**
