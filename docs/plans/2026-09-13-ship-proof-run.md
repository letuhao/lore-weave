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
| **AC-1** | The issue list contains only open problems | every issue closed with the commit that fixed it, or left open with a reason | S1 | ❓ unknown |
| **AC-2** | A clean machine can run the whole suite without hand-holding | the documented setup run start to finish on a stack that has never seen it | S2 | ❓ unknown |
| **AC-3** | Every test that runs is recorded — video and screenshot, pass or fail | `evidence-capture-gate.py` over the full run | S3 | ❓ unknown |
| **AC-4** | A person can open one report and see every journey, and watch any of them | Allure, opened cold and navigated without a guide | S4 | ❓ unknown |
| **AC-5** | Every failure in that run is diagnosed to a cause, or named as undiagnosed | one line per failure, with its trace | S5 | ❓ unknown |
| **AC-6** | The report says what is NOT covered as plainly as what is | the coverage map, with its holes | S6 | ❓ unknown |
| **AC-7** | The PO can reach a GO or NO-GO from the report alone | their own words, recorded | S7 | ❓ unknown |

**AC-7 is not something this plan can tick.** It is the condition under which the plan is finished,
and only the PO closes it.

## Board

- [ ] **S1** — Close what is done; leave what is not. *(AC-1)*
  Ten issues are fixed and open. Each gets closed against the commit that fixed it, or a comment
  saying why it stays. #247 stays open with its measured scope.
  Evidence: the issue list before and after, and the reason on anything still open.

- [ ] **S2** — A seed path a clean machine can follow. *(AC-2)*
  Recording one run took removing five blockers by hand. That is not reproducible and it is not
  written down. This turns it into something checked in and runnable — account, BYOK model,
  onboarding flag — and the `/onboarding` vs `/books` harness defect gets fixed rather than
  worked around, because the next person will hit it too.
  Evidence: the seed run on a stack that has never seen it, and the journeys passing login after.

- [ ] **S3** — Record the WHOLE suite, not a sample. *(AC-3)*
  225 tests across 76 specs, with `PLAYWRIGHT_EVIDENCE=1`. Expect this to be slow and expect
  failures; both are information. `evidence-capture-gate.py` must pass over the result, so a run
  that captured nothing cannot be reported as a run.
  Evidence: the capture gate's count against the number of tests that ran.

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

## What this plan will NOT do

- **It will not make a red test green by relaxing it.** A journey that fails is the finding.
- **It will not judge the prose, the translations, or the product.** It puts them on a screen.
- **It will not run against anything but loopback**, and never against the stack the PO is using.
- **It will not tag, build or publish anything.**
