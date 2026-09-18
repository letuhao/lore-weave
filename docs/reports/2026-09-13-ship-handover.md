# Handover — the 51 failures, answered. Your GO/NO-GO is the only thing left.

**Written for: the PO.** Everything below is evidence and reasoning. **Nothing here is a
recommendation to ship.** The verdict is yours and no row in any plan can tick it.

---

## What you asked for, and what you are getting

You asked for a plan to *"investigate and fix bug or test stale case by case"*. Twenty-two
recorded cycles later, every one of the 51 failures from the full-suite run has a verdict, every
repaired test was broken on purpose to prove it still bites, and the suite was re-run and diffed
against a baseline written to disk **before** the run.

| | before | after Z1 | now |
|---|---|---|---|
| passed | 145 | **180** | **180** |
| failed | **51** | **16** | **18** |
| skipped | 4 | 4 | **2** |
| newly red | — | **0** | 0 |

**The count went UP after Z1, on purpose.** Two tests had been skipping *permanently* because
`findGemma()` asked `GET /v1/ai/models`, which answers **404** — so it returned `null` every time
and both skipped with *"needs the local gemma model"* on a machine where gemma is the one active
model. Repaired, they run for 2.4 minutes against a real model and **fail on real assertions**
(#265, #266). A skip is unanswered; two silent unknowns are now answered.

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
| **#265** | Approving the cast checkpoint does not advance `pass_cursor` | The writer approves, nothing moves, and the later passes stay blocked behind a decision already made |
| **#266** | The grounded-run affirmation never renders in the planner | A grounded run looks identical to a blind one at the surface built to tell them apart |
| **#267** | The chat UI-tool executor does not navigate | `ui_open_book` / `ui_show_panel` resolve their round-trip and never move. **Undiagnosed** |
| **#268** | Wiki articles never appear after Generate | On a book whose extraction just succeeded. **Undiagnosed** |
| **#269** | `kg-overview-no-project` is rendered by nothing — and a unit test guards it anyway | A question for you, plus a check that cannot fail for the reason it was written |

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

---

## Update — 2026-09-14, after the green-honestly plan

| | the 51 | red-by-red | green-honestly Z1 |
|---|---|---|---|
| passed | 145 | 180 | **192** |
| failed | **51** | 18 | **7** |
| skipped | 4 | 2 | **1** |
| newly red | — | 0 | **0** |

Verified by reading `allure-report/widgets/summary.json` by content, not by exit code —
`{'failed': 7, 'skipped': 1, 'passed': 192, 'total': 200}`, 29.0 min. Eleven went green, each for
the reason its row claimed. Nothing went red that was not already red, which was the thing worth
checking: this plan changed product code in three places.

**The one remaining SKIP is unanswered, not passed.**

### What the 7 are

| test | why |
|---|---|
| `composition-telemetry` | **F2 / #263** — your decision |
| `kg-panels` | **H1 / #269** — your decision |
| `composition-engine B4.1` | D13 — a test asserting a state the product exists to prevent |
| `assistant-endofday` | **#270** — needs a `distill` role with no settings row |
| `composition-journey` | F6 — scene count, open |
| `studio-structure-templates` archive | F7 — archive ConfirmDialog, open |
| `plan-forge-pass-rail` | #265, open |

### One correction to what I told you earlier

I reported that `assistant-endofday` and the `composition-generate` skip were blocked by the
one-strong-model constraint. **That was wrong.** Both need a model ROLE — `critic`, `distill` —
and neither role has a settings row, so the resolver falls back to `chat` and returns the same
reasoning model. Loading a second model would have hidden a settings gap behind a hardware story.

Filed as **#270**. The product already knows: `evaluate.py:180` refuses to score and instructs the
user to *"Set a critic model in Settings › Chat & AI › default models"* — a row that does not exist.

---

## Update — 2026-09-14, final run: 201 passed · 0 failed · 0 skipped

Read by content from `allure-report/widgets/summary.json`:
`{'failed': 0, 'broken': 0, 'skipped': 0, 'passed': 201, 'total': 201}`, 26.9 min. The evidence gate
passed: every one of the 202 test directories left something watchable. The suite has 201 tests,
not 200, because one was added (F15, below).

**One green run is not a guarantee** for the model-dependent paths. Where a residual failure rate
was measured, it is stated below rather than hidden by that green run.

### What changed since the 192 / 7 / 1 run

Every product fix below was proven the same way: the test that found it goes green, the defect is
put back and that same test goes red for the same reason, then the fix is restored.

| row | what it was | proof |
|---|---|---|
| F12 · #273 | **The co-writer produced no prose on any book without a knowledge graph.** The 14 most recent drafts on the test stack were all the model asking for context, accepted into the manuscript as prose. Tests passed because they only checked that the draft was more than 20 characters. | Prompt A/B on captured requests: 6/6 requests → 6/6 prose; no invented names or canon breaks on a grounded context. Re-broken. |
| F13 | The same failure on "continue from cursor" for a scene with no prose yet. | 6/6 requests → 6/6 prose. Re-broken. |
| F14 | Once suggestions were real prose, the inline suggestion card ran off the bottom of the screen, and **a full-length suggestion could not be accepted at all** (nothing accepts from the keyboard). | Re-broken. |
| F15 | **Every page load hung behind Google Fonts when the font CDN stalled** — the recurring `page.goto` timeout. I had blamed host starvation; a CPU/memory sampler disproved that. | New spec makes the CDN hang on purpose; re-broken. |
| F9 | The diary distiller never asked the model to stop thinking, so a reasoning model returned blanks. | Re-broken through a rebuilt worker. |
| F10 | The cast-planning step was never shown the cast the author wrote. | Re-broken. |
| F8 | Plan analysis ran away inside a JSON string until the token cap. | Real pipeline, same day: **54% → 6.5% truncated** (p < 0.001). Re-broken. |
| D13 | The "pick a model" gate was masked by the account's default chat model, not by the model count. | Re-broken. |
| F2 · #271 · #272 | The API offered node kinds the database refuses; the outline tree showed a dead "Add beat" button. | Re-broken. |
| #270 | Critic and distill roles were resolvable by the backend and settable nowhere. | Re-broken. |
| #274 | The inline critic call died at the browser's 20s ceiling. | **Not re-broken.** See below. |

### Stated limits — not rounded up

- **F8 is reduced, not eliminated.** The remaining 6.5% is a different mode: the model repeats a whole list item. String caps can't bound that. The likely fix is `maxItems`, which is exactly what `schemas.py` records as rejected once already on uncontrolled evidence. It needs roughly 50+ real runs per arm to measure.
- **F11 ships as a guardrail, not a proven fix.** The same caps on the second plan step: 0/10 truncated vs 3/17 (p ≈ 0.27), with no cost observed.
- **#274 is not re-broken.** The original failure needed a cold model load, and recreating one means unloading a model in LM Studio by hand, which is off limits. What's proven: the cause (a 20s browser limit, with nginx at 300s and the gateway unlimited) and the change itself (a unit test that fails without it).
- The test account now has a **second, small active model** (`gemma-4-12b-qat`), added through the seeder's own opt-in `--allow-second-model`. Two tests need two active models, and memory stayed healthy (at least 15 GB free).

### Decisions only you can make

1. **AC-7 — GO or NO-GO on v0.1.0.**
2. **H1 — creating a book should provision the Work and knowledge project together.** That reverses a decision the code marks as ratified: `OQ-1` says only the owner triggers creation of a knowledge project, and rules out minting a token on their behalf. Options are in Cycle 20. **A** (a new internal route trusting `owner_user_id`) is recommended, but only with your explicit yes, because it's a security decision. Today 298 books sit half-provisioned until someone opens them.
3. **The same critic result shows twice on one screen**: inline in the compose view, and in the standing critic panel (the one pop-out reads). That's by design, but it's a product question.

### Not done, on purpose

Nothing is pushed. The commits sit on `fix/v0.1.0-release-gaps` locally. Nothing is tagged or published.

## Update — 2026-09-19, after the v0.1.0 leftovers plan

The leftovers plan ([`docs/plans/2026-09-18-close-v010-leftovers.md`](../plans/2026-09-18-close-v010-leftovers.md)) closed or bounded every open item, and the full suite is green on images that carry all of it: **201 passed · 0 failed · 0 skipped** (run 6).

What changed for a user:
- **Plan runs no longer die** when the model repeats itself to the token limit. Measured on 30 real runs: 0 failures, previously 2 of 31.
- **A new book gets its knowledge project when it is created.** Signing in sets up any of your books that are still missing one.
- **The critic waits 240 s**, not 20.
- **The legacy chapter editor is retired.** Its address opens the same chapter in the Writing Studio.

Found and fixed while getting there:
- **Some books could never be provisioned.** Composition returned `409 WORK_CREATE_CONFLICT` for a book that had both an unmarked knowledge project and a pending Work.
- **Python services rejected valid tokens** whenever their clock ran a moment behind auth-service's. Go services never did.
- **A first-time visitor's page reloaded itself** about a second after loading, wiping whatever they had typed.

Six full runs were needed to get there, and every red is accounted for in the plan's Cycles 7–10. Two single failures have no proven cause yet. They are tracked, not dismissed: `DEFERRED.md` #165.

The dev Docker VM's clock steps back 1.4 s every 30 s. That is the host's time sync, and it is worth fixing on the machine: it makes time-ordered data and token checks misbehave in local runs (`DEFERRED.md` #164).

**Still yours: the ship decision (AC-11).**

