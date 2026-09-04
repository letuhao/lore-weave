# Fix plan — the six findings from the 2026-09-04 human-sim run

Reconciles: Chat-agent ↔ MCP wiring · MCP Tool I/O Standard — F1 and F2 are defects in how a turn
follows a tool's own refusal and how it targets a write, which those two rows govern. Nothing here
proposes a new rule; each item enforces one those rows already state.

Findings and evidence: [`2026-09-04-human-sim-regression-report.md`](2026-09-04-human-sim-regression-report.md).

**Smoke test status: INCOMPLETE — 1 chapter of 5, stopped deliberately.** F1 and F2 both prevent a
chapter reaching the manuscript, so chapters 2-5 would have reproduced them four times at ~an
hour's cost. The remaining four are owed once F1 and F2 are fixed; that re-run is the proof, not
this plan.

---

## The board

| # | finding | severity | root cause | state |
|---|---|---|---|---|
| **F1** | prose written, `save_draft` refused, prerequisite called, **never retried** — chapter left empty | **blocking** | **known** | ready to build |
| **F2** | "write Chapter Two" re-saved Chapter One | **blocking** | **NOT known** | investigate first |
| F6 | usage-billing retries a CHECK violation 50,529×/day | high, **pre-existing** | known shape, producer unidentified | investigate first |
| F3 | 10 min / 6 tools before a sentence of prose | quality | not investigated | defer |
| F4 | 1137 words against an 1800-2500 ask | quality | matches a ceiling already measured here | defer, see note |
| F5 | first draft contradicted its own synopsis | quality, minor | self-corrected on rewrite | defer |

---

## F1 — the invariant, and why the machinery is already half there

> **A tool refused for a stated precondition, whose precondition then SUCCEEDS in the same turn,
> must be retried — or the turn must say why it was not.**

**Root cause, located.** `_tools_named_in_refusal` already parses *"create one first with
`book_chapter_create`"* and **arms** the named tool onto the surface. That half works — the agent
called `book_chapter_create` unaided. What is missing is the other half: nothing brings the
**refused** tool back. `_resume_refused_tool` does exactly this, but only on the **suspend/resume**
path (a confirm gate). A plain turn that is refused, satisfies the precondition, and ends has no
equivalent, so the write is dropped and the turn closes on an intention.

None of the eight existing end-of-turn guards covers it: P2 asks whether the turn *claimed* an
effect (it did not — it was honest), P16 whether it asked in *prose* (it did not — it used the
card). **A turn that is silent about a write it abandoned is the case none of them see.**

**Build.**
1. Track, per turn, `{refused_tool → prerequisite named in its refusal}` at the dispatch seam that
   already computes the refusal — the same place `_tools_named_in_refusal` is called.
2. When a named prerequisite **succeeds**, re-arm the refused tool for the turn.
3. Add an eighth-and-ninth guard, `_refusal_precondition_met_but_never_retried`, wired at the
   shared end-of-turn site and added to `TURN_GUARDS` in
   `test_no_turn_guard_is_defined_and_never_called.py` so it cannot be defined-and-never-called.

**Bite.** Reproduce the original: a `save_draft` refused with "no chapters yet", then a successful
`book_chapter_create`, then turn end. The guard must go RED on that exact shape and stay silent when
the retry did happen, when the prerequisite failed, and when the refusal named nothing.

**Not this:** do not auto-execute the retry silently. It is a Tier-A write; it goes through the
approval card like every other write. The fix is that the turn *offers* it, not that it performs it.

---

## F2 — investigate before proposing anything

I do **not** know why "write Chapter Two" produced a `book_chapter_save_draft` against chapter 1,
and a plan built on a guess here would be worse than none. Three candidates, and the first step
distinguishes them:

1. The model chose `chapter: "1"` because the assembled context named chapter 1 and nothing named a
   second — a **steering/context** problem, not a code defect.
2. The tool resolved a missing/ambiguous chapter reference to "the only chapter" — a **tool
   argument-resolution** problem, and the more serious of the three.
3. `book_chapter_create` was never attempted for chapter 2 at all, so the save had nowhere else to
   go — an **ordering** problem, and a sibling of F1.

**First step:** re-read the recorded tool call for that turn — the exact `book_chapter_save_draft`
arguments and whether any `book_chapter_create` preceded it — from the chat transcript and
`collect_run_evidence.py --label`. That is one read and it eliminates at least two candidates.

---

## F6 — pre-existing, and the producer is the question

`CHECK (model_source = ANY (ARRAY['user_model','platform_model']))` is violated 50,529 times in 24
hours, first at `2026-09-03T04:06` — before this run and before the merge. Two separable defects:

- **The classification.** A CHECK violation is *permanent*: that row will never insert. Calling it
  `transient failure (will retry)` retries it forever and drops the usage silently. This repo
  already has the rule — a drain that skips must mark-processed on a permanent failure.
- **The producer.** Something emits a third `model_source`. Find it before changing either side:
  widening the constraint to admit whatever is arriving would encode the bug in the schema.

**First step:** capture one offending payload from the outbox rather than inferring the value.

---

## F4 — a note, because "fix" is the wrong verb

1137 against 1800-2500 matches a ceiling this repo has already measured: one draft call holds to
~1500 words and then inverts. So the defect is not the length — it is that **the request was
accepted without a word about it.** The honest fix is for the turn to say it will deliver in parts,
or to deliver in parts. That is a product decision, not a bug fix, and it is yours to make.

---

## Order, and why

**F1 first** — root cause known, invariant statable in one sentence, machinery half-built, and it
is the one that loses an author's work.

**F2 second, as a read** — one investigation eliminates two of three candidates, and candidate 3
would make it a sibling of F1 that the same fix may already cover.

**F6 third** — real and expensive, but pre-existing and orthogonal to the merge; it drops billing
rows, not an author's chapter.

**Then re-run the smoke test to five chapters**, which is the only thing that proves F1 and F2 are
actually fixed.

---

## Board

- [ ] **F1** — track `{refused_tool → prerequisite named in its refusal}` at the dispatch seam that
  already calls `_tools_named_in_refusal`, and re-arm the refused tool when that prerequisite
  SUCCEEDS in the same turn. Half exists (`_resume_refused_tool`) but only on suspend/resume.
- [ ] **G1** — the guard `_refusal_precondition_met_but_never_retried`, wired at the shared
  end-of-turn site and added to `TURN_GUARDS` so it cannot be defined-and-never-called. **Bite it
  RED on the original shape** — save_draft refused, chapter_create succeeded, turn ended — and
  silent on the three negatives (retry happened / prerequisite failed / refusal named nothing).
- [ ] **F2R** — READ ONLY. The recorded `book_chapter_save_draft` arguments for the "Chapter Two"
  turn, and whether any `book_chapter_create` preceded it. One read; it eliminates two of the three
  candidates in §F2. **Decide from it before writing anything.**
- [ ] **F2** — the fix the read points at. If candidate 3 (ordering), check whether F1 already
  covers it and say so rather than building twice.
- [ ] **F6R** — READ ONLY. Capture one offending outbox payload and name the producer emitting a
  third `model_source`. **Do not widen the CHECK to admit it.**
- [ ] **F6** — a CHECK violation is PERMANENT: stop the infinite retry and mark it processed with a
  reason, so the drop is recorded rather than repeated 50,529 times a day.
- [ ] **V** — re-run the human-sim to **five chapters**, every one persisted in the manuscript, on a
  freshly rebuilt image and a NEW throwaway book. This is the proof; the plan is not.
- [ ] **D1** — **STOP CONDITION** — F4 is a product decision, not a bug: a single draft call holds
  ~1500 words, so an 1800-2500 ask cannot be met in one call. Deliver in parts, or say so up front?
  Owner's call.

```goal-prompt
goal: an author's chapter reaches the manuscript, and a five-chapter run proves it
po_decisions: [D1]
rules: |
  1 $0. Every model must resolve to lm_studio/local. Check user_default_models BEFORE a run and say the expected call count out loud; a PAID run needs the owner's yes first.
  2 Content-creating runs use a NEW throwaway book, never the dogfood book, never an existing one.
  3 Verify the DEPLOYED IMAGE before believing any live result — a green build log is not a rebuilt container.
  4 A guard must be bitten RED on the ORIGINAL recorded shape, then restored byte-exact. A guard added to TURN_GUARDS that is never called is the defect this whole family exists to stop.
  5 The retry is OFFERED, never performed silently. It is a Tier-A write and goes through the approval card like every other one.
  6 F2R and F6R are READS. Decide from what they return; a fix built on a guess is worse than no fix.
  7 Do NOT widen the usage_logs CHECK to admit the value that is arriving — that encodes the bug in the schema. Find the producer.
  8 A ratchet or baseline moves in the SAME COMMIT as the code that moved it, with the reason written in.
  9 Attribute a red thing before fixing it: F6 predates this merge, and fixing it on the wrong branch helps nobody.
discipline: |
  NO "BLOCKED" meaning "I would have to build it". Decide it, write the decision down, keep going.
  Commit every row, and tick the box in the commit that does the work.
  Record near-misses as they happen. An empty drift log is dishonest, not clean.
stop: |
  a fix would need a product decision neither the report nor the plan answers
  a run would call a model that is not local
  the CHECK constraint would have to be widened to admit the arriving value
note: |
  F1's cause is LOCATED and half the machinery exists: the refusal's named prerequisite is already
  armed and called. Nothing brings the REFUSED tool back outside suspend/resume.
```

**RESUME: F1 — re-arm the refused tool when its named prerequisite succeeds in the same turn**
