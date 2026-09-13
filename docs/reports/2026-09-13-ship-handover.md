# Handover — the 51 failures, answered. Your GO/NO-GO is the only thing left.

**Written for: the PO.** Everything below is evidence and reasoning. **Nothing here is a
recommendation to ship.** The verdict is yours and no row in any plan can tick it.

---

## What you asked for, and what you are getting

You asked for a plan to *"investigate and fix bug or test stale case by case"*. Twenty-two
recorded cycles later, every one of the 51 failures from the full-suite run has a verdict, every
repaired test was broken on purpose to prove it still bites, and the suite was re-run and diffed
against a baseline written to disk **before** the run.

| | before | after |
|---|---|---|
| passed | 145 | **180** |
| failed | **51** | **16** |
| skipped | 4 | 4 — *unanswered, never folded into a pass* |
| newly red | — | **0** |

**Open the report:** `frontend/tests/e2e/allure-report/index.html` — 343 MB, 594 attachments,
video and trace for every test. It is git-ignored; it does not enter history.

---

## The headline: 41 of 51 were never about the product

| verdict | count |
|---|---|
| **environment** — the harness, the fixtures, or the stack | **41** |
| **product defects** — filed, with reproductions | **3** |
| undiagnosed, with a trace kept | 3 |
| other — test design, unreachable precondition, an unrecorded product decision, an untestable control | 4 |

Not one of the 51 failure messages said what was actually wrong. A missing "Compose" tab was a
missing **book**. A broken Send button was text typed into the sidebar's search box. "Built-in
structures not listed" was a badge word renamed from `system` to `built-in`.

**Twice, a test was actively defending a bug the product had already fixed.** One asserted the raw
enum `au` where the product had deliberately switched to human labels. One asserted a button stay
disabled, where the product had removed what its own source calls *"the worst of both — a promise
it never kept and couldn't."* Repointing those locators while keeping the assertions would have
re-pinned both bugs and the suite would have defended them from then on.

---

## What is actually wrong with the product

Four issues filed today, each with a reproduction someone else can run.

| # | what | why it matters to a user |
|---|---|---|
| **#262** | The reasoning/effort menu in Compose cannot be clicked — the what-if promote bar wins the hit test | On **any canon book**. The menu opens and nothing in it can be chosen. No error; the click lands on the bar behind |
| **#264** | The structure editor says *"unsaved changes"* after a successful save | A false warning offering only "Discard" and "Cancel" over work that is already stored. Verified the saves landed |
| **#263** | The API offers node kinds `arc` and `beat` that the database forbids | A client written against the schema gets a 400 it cannot act on. The 400 also returns the raw Postgres error |
| **#261** | The login throttle is keyed per IP at 60/min | Everyone behind one NAT shares the budget — an office, a school, a VPN. Not a defect so much as a design question I did not want to answer for you |

**#262 and #264 were invisible before today.** Both were hidden behind stale selectors — the tests
could not reach the controls, so nobody could see the controls were broken.

---

## The 16 that are still red, and why each one is

Every survivor is a row left open **on purpose**. None is unexplained and none is called flaky.

| tests | cause | status |
|---|---|---|
| 4 | blocked by **#262** | product defect, filed |
| 2 | blocked by **#264** | product defect, filed |
| 1 | blocked by **#263** | product defect, filed |
| 2 | the chat nav executor does not navigate | **undiagnosed**, trace kept |
| 1 | wiki articles never appear after Generate | **undiagnosed**, trace kept |
| 2 | need a seeded + extracted book; a fresh one would make the claims vacuous | fixture work |
| 1 | asserts an intermediate phase from a stream delivered in one chunk | test design |
| 1 | its precondition cannot occur on a one-model machine | **needs your constraint to change, or the test to** |
| 1 | `kg-overview-no-project` is rendered by nothing in the app | **a product decision I would not invent** |
| 1 | the Assistant reuses one session, blocked on last run's consent gates | fixture work |

---

## What I will not tell you

**Whether to ship.** That was never mine. Three things you should weigh yourself:

1. **#262 is on the common path.** A writer on an ordinary book cannot choose a reasoning level.
   Whether that blocks a release depends on how central Compose is to v0.1.0 — your call.
2. **Three failures are undiagnosed.** I stopped rather than guess. They are recorded as
   undiagnosed with their traces, not retried until green.
3. **One thing is measured but unproven.** The skip count is unchanged at 4 and all four are
   reported as unanswered — but I did not record the baseline skip *identities* before the run, so
   I cannot prove the set is the same. That is my omission and it is why AC-6 is partial, not met.

---

## What this run changed outside the tests

**One product change, and it is two `data-testid` attributes** — no behaviour, markup or logic.
The EPUB import button had no testid while its immediate sibling did; its only handle was a
translated label.

**One infrastructure change with a real safety story.** `helpers/db.ts` shelled out to
`infra-postgres-1` — **your long-running stack** — regardless of where the browser pointed. Running
the suite against the isolated stack still read and wrote your real database, and one helper does
`INSERT`. It now derives the target from the browser. I checked whether the earlier full run had
leaked into `infra`: it had not.

That defect also invalidated two verdicts. `composition-flywheel` had been recorded as *"publish
does not auto-drain"* — a product defect that **does not exist**. Re-measured on the correct stack
it passes untouched.

---

## How to check my work

- **The plan:** [`docs/plans/2026-09-13-red-by-red.md`](../plans/2026-09-13-red-by-red.md) — 22 cycles, each with
  Investigated / Issues / Fix / **Proof** / AC impact, gate-enforced.
- **The baseline:** [`docs/plans/evidence/z1-baseline-failures.txt`](../plans/evidence/z1-baseline-failures.txt) —
  written before the re-run so the diff could not be done from memory.
- **The commits:** 22, one per row, each carrying its bite output.
- **Six of my bites missed**, and all six are written down. A bite that leaves a test green means
  you broke the wrong thing — that is the signal working, and hiding it would make the other
  sixteen worth less.
- **I corrected my own measurement once at the end.** The first Z1 diff said "2 newly red". It was
  an artefact of abbreviating two names in my baseline file. The true figure is 0.

---

## The one thing I need from you

**A GO or a NO-GO, in your own words.** AC-7 in the red-by-red plan and AC-10 in the ship plan both
stay open until you write it. No agent ticks either.

If it is NO-GO, the most useful thing you can tell me is **which of the 16** would have to be green
first — several are one product decision away, and three of them are decisions only you can make.
