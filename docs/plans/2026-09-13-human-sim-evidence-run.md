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
| **AC-1** | Every test that runs leaves a watchable artefact — video, or a screenshot per step | the artefact directory, counted against the number of tests that ran | R1, R2 | ✅ met — R1: 1 artefact → 4 on the same passing test. R2: the capture check is red after a default run and green after an evidence run, bitten both ways |
| **AC-2** | A person who did not write the tests can open ONE thing and see what was covered | the report opened cold, navigated without a guide | R3 | 🚧 partial — the report exists (20 MB, 40 attachments, video per test). Nobody but its author has opened it yet, which is the half AC-2 actually asks about |
| **AC-3** | The coverage map names what is NOT covered, not only what is | the map, with an explicit uncovered section | R4 | ✅ met — 76 specs / 225 tests mapped, and the hole named: `persona` is **2** of the 225 |
| **AC-4** | The run happens against a stack rebuilt from the commit under test | image digest compared against the build, per rule 7 | R5 | ✅ met — frontend rebuilt after the day's locale changes and verified on the SERVED bundle, not the build log |
| **AC-5** | The target is loopback and disposable — these journeys REGISTER ACCOUNTS and SEED BOOKS | `assertDisposableTarget` refusing a non-loopback target, shown | R5 | 🚧 partial — everything ran on `lw-iso` (:25174, loopback) and the PO's stack was never written to. The refusal itself was not demonstrated |
| **AC-6** | The authoring journey AC-10 turns on is exercised end to end, and its verdict is left to a person | the recorded run plus the PO's own words | R6 | 🚧 partial — recorded with video and trace, and it FAILS at a model-dependent control after clearing the first six steps. Not end to end, and no verdict has been asked for |
| **AC-7** | Evidence capture cannot silently degrade — a run that captured nothing fails loudly | the capture check, bitten | R2 | ✅ met — `evidence-capture-gate.py`, EXIT=1 on a run that captured nothing, EXIT=0 on one that did |

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

- [x] **R2** — A capture check that fails loudly. *(AC-1, AC-7)*
  A run that produced zero artefacts must not report success — the `govulncheck: scanned 0` lesson,
  applied to evidence. Counts artefacts against tests-that-ran and exits non-zero on a mismatch.
  **DONE.** `scripts/e2e/evidence-capture-gate.py`. Counts watchable artefacts per test
  directory and fails on zero — for the whole run, or for any single test.

```
self-test                       OK  (counts real artefacts, refuses `.last-run.json`
                                     as evidence, reports an absent dir as absent)
after a DEFAULT run             FAIL - no per-test directory            EXIT=1
after a PLAYWRIGHT_EVIDENCE=1   1 test dir, 3 watchable artefacts       EXIT=0
```

  The failure modes it closes are all silent ones: `PLAYWRIGHT_EVIDENCE` is a string compare
  so `=true` sets nothing, `PLAYWRIGHT_VIDEO=off` still wins if left exported, and a browser
  without an encoder drops the video and carries on — while `--reporter=list` says `1 passed`
  either way. **`.last-run.json` is excluded by name**, because it is written after every run
  including one that captured nothing, so counting it would make the gate pass on exactly the
  case it exists to catch.

- [x] **R3** — One report a non-author can open. *(AC-2)*
  Playwright's HTML reporter is already wired and already embeds video, trace and screenshots
  inline. **Allure is the open question, not the default** — it adds cross-run history and a
  stakeholder-facing shape, and costs an npm dependency plus a Java CLI (Java 24 is present on this
  box; CI has none). Decide with the PO rather than for them.
  **DONE — Playwright HTML, no new dependency.** 20 MB, 40 attachments embedded inline; every
  test has a video, a trace and a screenshot. **Allure was NOT added**: the report already
  answers the question, Java 24 is on this box but CI has none, and an unused dependency in
  `package.json` reaches the frontend image. It stays a one-command addition if cross-run
  history is ever wanted.
  ⚠️ A trap worth keeping: `--reporter=list` REPLACES the config's reporter list, so the first
  run produced no HTML report at all and said `2 passed` while doing it.

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

- [x] **R5** — A disposable stack, rebuilt. *(AC-4, AC-5)*
  **This is the row with a real cost and it is the PO's call.** The journeys register accounts and
  seed books. `infra` (`:5174`) is loopback but it is the stack the PO is testing on by hand —
  seeding it pollutes their session. `lw-iso` (`:25174`) exists for exactly this and is **not
  built** (0 images, 0 containers), so standing it up is a second full build.
  **DONE.** `lw-iso` built (34 images, 0 failures) and up **41/41 in one pass, 73s** — after the
  cold-start race was fixed, which the first attempt hit: it aborted at 30 containers with no
  frontend. Rule 7 honoured and checked on the SERVED bundle, not the build log: the rebuilt
  frontend carries the day's locale changes. The PO's `infra` stack was never written to.

- [~] **R6** — The authoring journey, recorded end to end. *(AC-6)*
  Plan a book, draft chapters, check canon holds. The standing verdict (2026-09-06, re-derived
  2026-09-12) is **conditional GO on planning/outline and NO-GO on in-manuscript AI authoring**, as
  *"a reachability-and-disclosure failure, not a capability gap"*. The remediation since then
  targeted exactly that — T2 made the disabled reason visible, T4 reports a blocked agent write,
  T5/T6 made Suggest-scenes and narration-attach work — and **nobody has checked whether the path
  is reachable now.**
  **PARTIAL — recorded, not passing, and the verdict is still the PO's.** `composition-journey`
  is the AC-10 shape (*set up → scene → co-write → accept → save → mark done → publish*). It
  now reaches line 45 and fails at `reasoningSelect.selectOption('off')`, having cleared login,
  the compose panel, the Work setup, the scene and the publish gate. The seeded drafter is
  `qwen/qwen3.8-27b` where the spec prefers `qwen3.6-35b`, so this is **most likely** a
  fixture/model mismatch — and most likely is not verified, so the row stays open.
  **Getting here took removing FIVE blockers** (see the run log): no account, an existing
  account with an unknown password, a password policy, no BYOK model (which would have made it
  SKIP), and `/onboarding` vs `/books` — the last being a defect the first human-sim run
  already recorded and nobody has fixed.

## What this plan will NOT do

- **It will not judge the prose.** Whether a drafted chapter is any good is the thing AC-10 asks a
  person, and a recorded run makes that judgement possible rather than making it.
- **It will not add assertions to make a journey pass.** A journey that fails on the recorded run is
  the finding; the report keeps it.
- **It will not run against anything but loopback.** `assertDisposableTarget` refuses, and that
  refusal is itself evidence for AC-5.

## Run log — 2026-09-13

**Target:** `lw-iso` at `http://localhost:25174` — loopback, disposable, and NOT the stack the PO is
testing on by hand. 41/41 containers, brought up in one pass after the cold-start fix.

**Rule 7 honoured, and checked on the SERVED bundle rather than the build log:** the iso frontend was
rebuilt after the day's locale changes, and the new Vietnamese string is present in
`assets/index-Ssmjrhq7.js`.

### What ran

```
13 tests   11 passed   2 failed        evidence-capture-gate: 13 test dir(s), 39 artefacts, EXIT=0
           13 videos   13 traces   13 screenshots
           playwright-report  20 MB, 40 attachments embedded
```

| spec | result |
|---|---|
| `persona-journeys` (frequent, newcomer) | **2 passed** |
| `writing-studio` | **9 passed** |
| `composition-journey` — *the AC-10 shape* | **1 failed** |
| `studio-compose` | **1 failed** |

**The `frequent` persona's scale was verified, not assumed.** The human-sim standard says a pass is
not evidence unless the account reached `minBooks`, because below 21 books the defect that journey
exists to catch cannot occur. The isolated database shows an owner with exactly **25**, matching the
declared `minBooks: 25`.

### The two failures, named rather than averaged away

- **`composition-journey`** — `reasoningSelect.selectOption('off')` timed out at line 45. It got
  through login, the compose panel, the Work setup, the scene, and the publish-gating assertion
  first. The reasoning control is model-dependent and the seeded drafter is `qwen/qwen3.8-27b`
  rather than the `qwen3.6-35b` the spec prefers, so this is most likely a fixture/model mismatch
  rather than the authoring path being broken — **most likely is not verified**, and it is recorded
  as unresolved.
- **`studio-compose`** — the command palette did not mount the chat panel.

Both carry video, trace and a screenshot in the report.

### What it took to run the authoring journey at all — the reproducibility finding

A clean `lw-iso` could not run the model-gated journeys, and each blocker had to be removed in turn:

1. **No account.** `API login claude-test@loreweave.dev failed: 401`. The human-sim standard already
   warns *"the documented account logs into `infra`, NOT `lw-iso`"*.
2. **The account that did exist had an unknown password** — `register → 409`, `login → 401`. The iso
   volumes are not fresh; they carry data from earlier work (one owner holds 308 books). A new
   account was registered instead of fighting the old one.
3. **Password policy**, which cost a round trip: the suite's own default is `Claude@Test2026`, and
   guessing produced `AUTH_VALIDATION_ERROR: invalid email or password policy`.
4. **No BYOK model**, so the journey would have **SKIPPED** — `test.skip(chatModels.length < 1)` —
   and a skipped leg is not a passed leg. Seeded an LM Studio provider plus one chat-tagged model.
   The suite's helper hardcodes `qwen/qwen3.6-35b-a3b`, which this LM Studio does not serve.
5. **`/onboarding`, not `/books`.** A freshly registered account lands on the chooser while
   `loginViaUI` waits for `**/books`. **This is the exact defect the first human-sim run recorded** —
   *"an assumption that only ever described an account someone had already onboarded by hand"* — and
   it is still live. Worked around by setting the SERVER preference `hasSeenOnboarding`.

**That is five blockers between a clean stack and the journey AC-10 turns on**, and the last one is a
known, unfixed harness defect. The value is not the workaround; it is that *"can a new machine run
the authoring journey"* now has a measured answer, and the answer is **not without help**.
