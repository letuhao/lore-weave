# Human-simulation evidence run — what was tested, shown so a person can sign it off

Reconciles: Plan Acceptance Criteria · Non-Vacuity · Multilingual — this plan adds no rule. It
APPLIES the AC-1..7 shape to one question the PO asked directly, and NV-6 is why "we tested it"
is not the deliverable: the deliverable is something a person can *watch* and disagree with.

> **NOT APPROVED — this is a draft for the PO.** It exists because of a direct instruction:
>
> > *"you should make new plan to play human simulation testing and collect video/image and make a
> > complete report … i need to review what did you already test and cover by my eyes then i will
> > sign off"*
>
> **Nothing here signs anything off.** The verdict on AC-10 — whether an author can plan a book,
> draft it and keep canon intact — is the PO's, and this plan's whole job is to put the evidence
> in front of them in a form they can actually review.

## Why this is needed, stated as a defect rather than a preference

**The suite already covers far more than anyone can see.** Measured 2026-09-13:

```
frontend/tests/e2e/specs/    76 spec files
                            225 test() blocks
                             82 describe() blocks
personas                      2 (newcomer, frequent)
```

225 tests run, go green, and **leave nothing behind**. That is not an oversight, it is the
configured behaviour:

```ts
// frontend/playwright.config.ts
trace:      'retain-on-failure',
screenshot: 'only-on-failure',
video:      'retain-on-failure',
```

Right for a red/green suite. **Wrong for the question being asked.** The PO is not asking whether
the tests passed — CI already answers that. They are asking *what the product looked like while
they passed*, and under this configuration a passing run produces no artefact at all. The one
existing exception is `tests/e2e/helpers/humanRun.ts`, which takes a full-page snapshot per step
precisely because "the defaults were not enough" — it covers the persona journeys and nothing else.

So the gap is not coverage. **The gap is that the coverage is invisible**, and an invisible test is
indistinguishable from one that was never written — the same shape as every other finding in the
v0.1.0 work: a claim nobody can check.

## Acceptance criteria

| AC | Must be true | Verified by | Rows | Status |
|---|---|---|---|---|
| **AC-1** | Every test that runs leaves a watchable artefact — video, or a screenshot per step | the artefact directory, counted against the number of tests that ran | R1, R2 | 🚧 partial — R1 done: 1 artefact → 4 on the same passing test. R2 (the check that a run captured anything) is open |
| **AC-2** | A person who did not write the tests can open ONE thing and see what was covered | the report opened cold, navigated without a guide | R3 | ❓ unknown |
| **AC-3** | The coverage map names what is NOT covered, not only what is | the map, with an explicit uncovered section | R4 | ✅ met — 76 specs / 225 tests mapped, and the hole named: `persona` is **2** of the 225 |
| **AC-4** | The run happens against a stack rebuilt from the commit under test | image digest compared against the build, per rule 7 | R5 | ❓ unknown |
| **AC-5** | The target is loopback and disposable — these journeys REGISTER ACCOUNTS and SEED BOOKS | `assertDisposableTarget` refusing a non-loopback target, shown | R5 | ❓ unknown |
| **AC-6** | The authoring journey AC-10 turns on is exercised end to end, and its verdict is left to a person | the recorded run plus the PO's own words | R6 | ❓ unknown |
| **AC-7** | Evidence capture cannot silently degrade — a run that captured nothing fails loudly | the capture check, bitten | R2 | ❓ unknown |

**AC-6 is deliberately not "the product works".** No agent settles AC-10. This plan reaches the
point where a person can watch a book being planned and drafted and say yes or no.

## Board

- [x] **R1** — Capture on PASS, behind a switch. *(AC-1)*
  `PLAYWRIGHT_EVIDENCE=1` flips `video`, `screenshot` and `trace` to `on` for the whole run. A
  switch rather than a default, because 225 tests × video is minutes and gigabytes, and making the
  normal suite pay that is how the switch gets turned back off by someone in a hurry.
  **DONE.** `PLAYWRIGHT_EVIDENCE=1` flips all three to `on`; `PLAYWRIGHT_VIDEO=off` still wins.
  Proved on one passing navigation-only spec (no account, no seeding), run both ways:

```
DEFAULT           1 passed    artefacts: 1   -> .last-run.json           (nothing watchable)
EVIDENCE=1        1 passed    artefacts: 4   -> video.webm
                                                test-finished-1.png
                                                trace.zip
```

  Same test, same result, and only one of them leaves something a person can watch.

- [ ] **R2** — A capture check that fails loudly. *(AC-1, AC-7)*
  A run that produced zero artefacts must not report success — the `govulncheck: scanned 0` lesson,
  applied to evidence. Counts artefacts against tests-that-ran and exits non-zero on a mismatch.
  Evidence: the check red on a deliberately empty run, green on a real one, restored byte-exact.

- [ ] **R3** — One report a non-author can open. *(AC-2)*
  Playwright's HTML reporter is already wired and already embeds video, trace and screenshots
  inline. **Allure is the open question, not the default** — it adds cross-run history and a
  stakeholder-facing shape, and costs an npm dependency plus a Java CLI (Java 24 is present on this
  box; CI has none). Decide with the PO rather than for them.
  Evidence: the report opened from a clean directory, with a named journey watched start to finish.

- [x] **R4** — The coverage map, including its holes. *(AC-3)*
  225 tests grouped by product area, each area carrying what it does NOT check. The suite's own
  names are the input (`studio-*`, `composition-*`, `assistant-*`, `persona-journeys`, …).
  **DONE — 76 specs / 225 tests, grouped:**

```
area                  specs  tests      area                  specs  tests
studio                   26     75      kg                        1      5
composition              10     25      frontend-tools            1      4
assistant                 9     17      manuscript                1      4
campaign                  1     15      wiki                      1      4
other                     1      9      demo-pipeline             3      3
agent                     1      8      persona                   1      2   <-- the human sim
plan-forge                2      8      s5                        1      2
revision                  2      8      epub                      1      1
context                   1      7      s11                       1      1
creation-unblock          5      7      smoke                     1      1
s6                        2      7      TOTAL                    76    225
enrichment                2      6
s2                        2      6
```

  **The hole is the point of this plan.** `studio` carries 75 tests and `persona` carries
  **two** — and the persona journeys are the only ones that behave like a user rather than
  like a feature test. AC-9 of the ship plan already records that suite as *"only TWO
  journeys"*; this is the same fact with the rest of the suite next to it for scale. The
  225 are not a substitute: they assert that a control works, not that a person can finish
  a book.

- [ ] **R5** — A disposable stack, rebuilt. *(AC-4, AC-5)*
  **This is the row with a real cost and it is the PO's call.** The journeys register accounts and
  seed books. `infra` (`:5174`) is loopback but it is the stack the PO is testing on by hand —
  seeding it pollutes their session. `lw-iso` (`:25174`) exists for exactly this and is **not
  built** (0 images, 0 containers), so standing it up is a second full build.
  Evidence: the image digest of the frontend under test, and `assertDisposableTarget` shown refusing
  a non-loopback URL.

- [ ] **R6** — The authoring journey, recorded end to end. *(AC-6)*
  Plan a book, draft chapters, check canon holds. The standing verdict (2026-09-06, re-derived
  2026-09-12) is **conditional GO on planning/outline and NO-GO on in-manuscript AI authoring**, as
  *"a reachability-and-disclosure failure, not a capability gap"*. The remediation since then
  targeted exactly that — T2 made the disabled reason visible, T4 reports a blocked agent write,
  T5/T6 made Suggest-scenes and narration-attach work — and **nobody has checked whether the path
  is reachable now.**
  Evidence: the recorded run. **The verdict is the PO's and no row ticks it.**

## What this plan will NOT do

- **It will not judge the prose.** Whether a drafted chapter is any good is the thing AC-10 asks a
  person, and a recorded run makes that judgement possible rather than making it.
- **It will not add assertions to make a journey pass.** A journey that fails on the recorded run is
  the finding; the report keeps it.
- **It will not run against anything but loopback.** `assertDisposableTarget` refuses, and that
  refusal is itself evidence for AC-5.
