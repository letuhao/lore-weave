# Human-simulation regression run — the merged stack, 2026-09-04

Reconciles: MCP Tool I/O Standard · Chat-agent ↔ MCP wiring · Agent GUI Reconciliation (09) — this
is a report of driving those surfaces as a user, not a new rule. It measures whether the tools
those rows govern can be reached, called and trusted through the real UI after the
`feat/frontend-tools-mcp-migration` merge; every finding names the tool or the turn that produced it.

**Persona:** an author starting a novel. **Target:** the `infra` stack at `:5174`, rebuilt from the
merged tree (frontend, chat-service, ai-gateway, knowledge, glossary, composition, book-service) and
**verified in the running image** — `agentruntime` 20 modules, `stream_service.py` 14503 lines,
`app/db/graph.py` present, `x-trace-id` in the served bundle.

**Book:** `ZZ Regression — The Lamplighters of Vurn (2026-09-04)`, id
`01a06a7f-a8ae-7986-b5e3-85e379213f43`. A **throwaway**, created for this run.

**Cost: $0.** Every default model resolves to `lm_studio` on `localhost:1234`; the studio's own
readout showed `$0.00` and the chat panel named `Gemma-4 26B-A4B QAT · lm_studio · 195K ctx`.

**Scope achieved: 1 chapter of 5.** Stopped deliberately — see §4.

---

## 1. What worked, and it is not a short list

- **Login → create book → Studio → Co-writer Chat** is clean. Book creation is two fields and a
  submit; the studio opens on a Welcome panel that offers the three panels a writer wants.
- **The Tier-A approval card is the consent mechanism, and it is used.** Every write asked through
  the card — `composition_create_work`, `composition_outline_node_edit`, `plan_propose_spec`,
  `glossary_extract_entities_from_doc`, `plan_run_pass`, `book_chapter_create`,
  `book_chapter_save_draft`. **Not once did the assistant ask for consent in prose**, which is
  exactly P16's invariant, exercised live.
- **Two honesty guards fired, unprompted and correctly:**
  - *"I did not make any changes to your story or the plan. I only started an asynchronous job… and
    I cannot confirm it is finished until the tool returns a result."* — P2, refusing to claim an
    effect it had not made.
  - *"I did not re-read the book this turn, so my answer may be stale."* — the read-side guard.
- **Self-correcting errors are real and they work.** Two fired, and the agent recovered from both
  without help:
  - `book_chapter_save_draft — this book has no chapters yet — create one first with
    book_chapter_create`
  - `composition_outline_node_edit — 'parent_id' and 'project_id' were both set to <id> — they
    identify DIFFERENT things and can never be the same id… Look the missing one up and call again
    with both ids distinct.`
- **The prose is decent.** *"the lamp, cold and dead, standing like a tombstone in the fog"*;
  closing on *"the darkness had arrived, and it hadn't even bothered to knock."*

---

## 2. Findings

### F1 — prose is written, the save is refused, and the retry never happens (BLOCKING)

The first request produced ~2000 words in chat. `book_chapter_save_draft` was then refused
(correctly — no chapter existed). The agent created the chapter… **and ended the turn**, closing
with *"I am now creating the scene node and triggering the generation."*

Measured in the book database immediately after:

```
chapters: 1   title='Chapter One: The Absence'   word_count=0   byte_size=0
chapter_revisions: 1 row, 64 bytes:
  {"type":"doc","content":[{"type":"paragraph","_text":""}]}   message='seed from assistant'
```

**The author is left with an empty chapter and their novel in a chat bubble.** `draft_revision_count`
reads `1`, which looks like a save and is the empty seed `book_chapter_create` writes.

It recovered only when I told it the chapter was empty — and then it asked properly and saved
**1137 words**. So the capability is there; the turn ends one call short of using it. This is the
P6/P16 family in a new place: not prose-instead-of-a-tool, but *a refusal absorbed and never
retried after the precondition it named was satisfied*.

### F2 — "write Chapter Two" re-saved Chapter One (BLOCKING)

Asked for a new chapter with its own synopsis, the assistant produced a `book_chapter_save_draft`
against **chapter 1** and reported back describing Chapter One's content. `draft_revision_count`
on chapter 1 went 3 → 5; the book still holds **one** chapter. The book's chapter *count* never
moved, so nothing in the UI signals that the request was misrouted.

### F3 — ten minutes of planning before a single sentence (QUALITY)

The plain request *"Please write Chapter One… 1800-2500 words… not a summary or an outline"*
produced, over ~10 minutes: `composition_create_work`, `composition_outline_node_edit`,
`plan_propose_spec` ×2, `glossary_extract_entities_from_doc`, `plan_run_pass(motifs)` — and **zero
prose**. It began writing only after I said *"Stop the planning… I need pages I can read."*

The scaffolding is not wrong in itself; the ordering is. An author who asked for a chapter has no
way to know the first ten minutes are working toward one.

### F4 — length lands at ~45% of the ask (QUALITY)

Asked for 1800-2500 words, twice. Delivered **1137**. This matches a ceiling already measured in
this repo: a single draft call holds up to ~1500 words and then inverts. The request is accepted
without a word about the shortfall.

### F5 — a continuity error the model then fixed by itself (QUALITY, minor)

First draft: *"The glass was clear. There was no soot on the pane… the wick was pristine,
unburnt"* — contradicting both the premise and **the synopsis the assistant had written minutes
earlier** (*"based on the soot accumulation"*). The rewrite corrected it to *"a thick, undisturbed
layer of soot… The lamp had been out for at least a week."* Worth noting because the contradiction
was with its **own** stored outline, which is what the canon machinery exists to prevent.

### F6 — usage-billing retries a permanent error ~50,000 times a day (PRE-EXISTING, not this merge)

```
WARN usage consumer transient failure (will retry)
  insert usage log: ERROR: new row for relation "usage_logs"
  violates check constraint "usage_logs_model_source_check" (SQLSTATE 23514)
```

`CHECK (model_source = ANY (ARRAY['user_model','platform_model']))` — a producer is emitting a
third value. **50,529 occurrences in 24 hours**, first at `2026-09-03T04:06`, which predates both
this run and the merge. A CHECK violation is *permanent*: the row will never insert, and calling it
transient means the consumer retries it forever. Usage for those calls is being dropped.

---

## 3. Evidence

- Chat transcript and approval cards: the run's own screenshots.
- Database reads quoted above, against `loreweave_book` and `loreweave_usage_billing`.
- Logs: `python scripts/e2e/collect_run_evidence.py --since 30m --project infra --out <dir>` —
  12,975 lines from 18 of 45 containers.

---

## 4. Why this stopped at one chapter of five

F1 and F2 both mean a chapter does not reliably reach the manuscript, and each one costs ~10-15
minutes of local generation. Writing chapters 2-5 would have reproduced the same two faults four
more times at ~an hour's cost, and would not have told us anything the first two did not.

**What is NOT concluded here:** that the assistant cannot write five chapters. It was not tried.
The claim is narrower and checkable — *on this build, an author asking for a chapter gets prose in
chat and an empty chapter in the book unless they notice and say so.*
