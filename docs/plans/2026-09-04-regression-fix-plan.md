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

## Evidence

### F6R + F6 — 2026-09-04

**Rule 7 is why the diagnosis is right.** Forbidding the constraint widening forced the read, and
the read found the **producer is already correct**: `usage_outbox` holds 4 rows, all
`model_source='user_model'`, with `provider_kind` in its OWN column. The bad value — `"openai"`, a
provider kind in a source-category field — is historical. Widening the CHECK would have admitted a
wrong value into the schema permanently *and* left the real mechanism untouched.

`XINFO GROUPS` gave the true shape: `lag: 0`, `pending: 3`, retrying **the same two ids** — 177 in
5 minutes, 2100 in an hour. The stream had moved on; the group was spinning on its own Pending
Entries List.

**The consumer's design was already right** — `permanent` acks and drops, transient retries. Only
the CLASSIFICATION was wrong: `writeUsageLog`'s error was returned unconditionally transient, so a
violated CHECK — a property of the ROW, not the database — was retried forever.

| bite | result |
|---|---|
| `23514` removed from the permanent set | **RED**, with the measured message |
| restored | green; all 4 packages `ok` |
| the transient arm (blips, `40001`, `57P01`, `53300`) | stays green — dropping a row that was never wrong is the more expensive defect |

**Proven live, on the rebuilt image:**

```
pending: 3 -> 0      lag: 0      retries in 45s: 0   (was ~35/min, 50,529/day)
usage consumer dropping unprocessable event  id=1781773507908-0
usage consumer dropping unprocessable event  id=1781773507909-0
usage consumer dropping unprocessable event  id=1781773545897-0
```

**The usage IS lost** — that is what a violated CHECK means, and the code says so rather than
implying recovery. What changed is that the loss is recorded once and the group moves on.
`23505` is deliberately excluded: `ON CONFLICT DO NOTHING` makes a duplicate a success, so it can
never reach that branch, and listing it would be a classification for a case that cannot occur.

### F2R + F2 — 2026-09-04

**The read answered it, and it eliminated two of the three candidates.** The recorded `tool_calls`
for the "Chapter Two" turn were exactly two, both FAILED:

```
04:01:07  composition_outline_node_edit  ok=false  title='Chapter Two: The Bureaucracy of Silence'
04:01:07  composition_outline_node_edit  ok=false  title="The Warden's Office"
   error: 'parent_id' and 'project_id' were both set to 01a06a7f-abcb-… — they identify
          DIFFERENT things and can never be the same id.
```

No `book_chapter_create` for a second chapter was ever attempted. So it is **candidate 3
(ordering)** — with a specific blocker: the model was building Chapter Two as a composition
OUTLINE node, both attempts died on the id conflation, and it then fell back to re-saving Chapter
One. The revision timestamps corroborate: the identical 14,970-byte body was written twice,
`03:59:32` and `04:02:17`.

**F1's guard does NOT cover this**, and it should not: the prerequisite never succeeded, and F1 is
deliberately silent then, because nagging for a retry that would fail again buries the real error.

**The fix, and what it is careful NOT to be.** The duplicate-identifier check is a well-measured
refusal — 135 calls, 7 tools, 19 sessions, **zero successes** — and deliberately not a repair,
because the runtime does not know which of the two is wrong. That stands. What was wrong is the
ADVICE: `parent_id` is **optional** on `op=create` and a chapter's parent IS the project root, so
*"look the missing one up"* named an action with no referent. The model obeyed it and failed
again. Now, and only when the tool's own schema says a colliding param is droppable, the refusal
says to OMIT it.

| bite | result |
|---|---|
| the optional-advice branch disabled | **2 RED** — exactly the two asserting the new advice |
| the four arms protecting the REQUIRED case (`book_id`/`chapter_id`, 38 measured calls) | stayed GREEN |
| restored | 6 green |

### F1 + G1 — 2026-09-04

**The row was wrong and reading the seam caught it.** "Re-arm the refused tool" is work that does
not exist: the refused tool is never de-armed (it was called this turn, so it is already active —
observed in the run itself, where `save_draft` was called again later with nothing re-arming it),
and the seam already injects *"Call them to clear this, then retry."* **The whole gap was
detection.** F1 shrank to one dict; G1 is the work.

**Then the first draft of the guard could never have fired.** It took `attempted_after` and the
call site passed `turn_attempted`, which contains the refused tool's own FIRST call — so
`refused not in retried` was False on exactly the shape the guard exists for. Caught by reasoning
through the call order before the bite; the parameter is gone and the docstring says why. "Not
retried" IS the dict: `refusal_pending` is popped the moment the tool is called again.

| bite | result |
|---|---|
| detector emptied (`return []`) | **4 RED**, restored → 8 green |
| call site deleted | **2 RED** — this file's AST test AND the `TURN_GUARDS` parametrised case — and only those two |
| `TURN_GUARDS` | 9 → **10**; the guard cannot become defined-and-never-called |
| chat-service suite | **3920 passed, 7 skipped, 0 failed** (baseline 3911 + 7) |

**Rule 5 held:** the directive OFFERS the retry, it does not perform it. It is a Tier-A write and
goes through the approval card like every other one. The fix is that the turn stops being silent,
not that it starts writing unasked.

**Not yet proven live.** These are unit-level. Row V — five chapters through the real UI — is what
shows the author actually keeps their chapter.

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

**🔴 CORRECTED 2026-09-04, BEFORE BUILDING, BY READING THE SEAM THIS ROW CITES.** Step 2 below
was *"re-arm the refused tool"*, and that work does not exist to be done:

- The refused tool is **never de-armed**. It was called this turn, so it is in `active_tool_names`.
  Observed in the run itself — `book_chapter_save_draft` was called again in a later turn without
  anything re-arming it.
- The seam **already tells the model to retry**. Its injected system message reads: *"… are now
  available to you on this turn — no tool_load needed. Call them to clear this, **then retry**."*

So the arming works, the instruction is present, and the model ignored it. **The whole gap is
DETECTION** — nothing notices the retry did not happen, so the author is never told. Building a
re-arm would have been a mechanism with no defect to catch, and this file's own family of bugs is
mechanisms that fire and do not matter.

**Build, as corrected.**
1. Track, per turn, `{refused_tool → prerequisite named in its refusal}` at that same seam. This is
   the only new state, and it exists solely so the guard can ask its question.
2. `_refusal_precondition_met_but_never_retried`, wired at the shared end-of-turn site and added to
   `TURN_GUARDS` in `test_no_turn_guard_is_defined_and_never_called.py` so it cannot be
   defined-and-never-called.

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

- [x] **F1** — track `{refused_tool → prerequisite named in its refusal}` at the dispatch seam that
  already calls `_tools_named_in_refusal`. **Re-arming is NOT part of this** — see §F1: the refused
  tool is never de-armed and the seam already says "then retry". The tracking exists only so G1 can
  ask whether the retry happened.
- [x] **G1** — the guard `_refusal_precondition_met_but_never_retried`, wired at the shared
  end-of-turn site and added to `TURN_GUARDS` so it cannot be defined-and-never-called. **Bite it
  RED on the original shape** — save_draft refused, chapter_create succeeded, turn ended — and
  silent on the three negatives (retry happened / prerequisite failed / refusal named nothing).
- [x] **F2R** — READ ONLY. The recorded `book_chapter_save_draft` arguments for the "Chapter Two"
  turn, and whether any `book_chapter_create` preceded it. One read; it eliminates two of the three
  candidates in §F2. **Decide from it before writing anything.**
- [x] **F2** — the fix the read points at. If candidate 3 (ordering), check whether F1 already
  covers it and say so rather than building twice.
- [x] **F6R** — READ ONLY. Capture one offending outbox payload and name the producer emitting a
  third `model_source`. **Do not widen the CHECK to admit it.**
- [x] **F6** — a CHECK violation is PERMANENT: stop the infinite retry and mark it processed with a
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
