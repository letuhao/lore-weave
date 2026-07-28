# Intent collection as a state machine

**Status:** DESIGN (CLARIFY/DESIGN phase) · 2026-07-28
**Origin:** the author dogfood run of 2026-07-28. See also `docs/sessions/SESSION_HANDOFF.md`.

---

## 1 · The problem, stated correctly

I got this wrong first, and the correction is the whole design.

I asked the author *"what do you want chapter 1 to be about?"* — treating intent as **one large
answer available up front**. It is not. The PO's correction:

> ý định của tác giả là thứ tác giả phải cung cấp cho agent, nó đâu đoán được. với lại cái gọi là ý
> định mơ hồ lắm, vì nó phải là của **mỗi chương, mỗi scene**. và nó chính là thứ **hoàn thiện dần
> dựa trên trao đổi của 2 bên** — việc tạo glossary, KG, tạo plan, thêm beat, scene, motif,
> template, etc là mấy cái công việc đó.

Two claims, both load-bearing:

1. **Intent is per-chapter and per-scene**, not per-book. There is no single statement of it.
2. **The artifacts ARE the intent.** glossary, KG, plan, beats, scenes, motifs, templates are not
   *prerequisites that need* intent — they are **the medium in which intent is expressed and
   refined**. Every time the author edits a beat or adds an entity, intent has been said more
   precisely.

So a flow that demands intent before building artifacts is backwards. It is the same shape as the
onboarding hole fixed in `17d4826ae` / `8bbfb6c23`: **requiring the author to already know
something that only the work itself produces.** There it was "what a Work is"; here it is "what my
story is".

**Corollary.** The agent cannot guess intent, and must not. Its job is to make intent *cheap to
say*: propose, and let the author correct. For an author, **correcting a wrong proposal is far
cheaper than writing from a blank page** — but only if the proposal is grounded, small, and
reversible.

---

## 2 · What already exists (surveyed, not assumed)

Nothing here needs inventing. The three pieces are shipped and proven:

| piece | where | what it gives us |
|---|---|---|
| **The slots** | `outline_node` columns | `goal · conflict · outcome · value_shift · stakes · exit_state · tension · beat_role · pov_entity_id · present_entity_ids · location_entity_id · story_time · target_words` |
| **The FSM shape** | `app/services/glossary_build/service.py` | `transition(run_id, owner, from_status: list[str], to_status, **fields)` — an **optimistic** DB transition returning `None` (→409) when the run is not in `from_status` |
| **The propose→apply gate** | `plan_bootstrap_proposal` | `{status, diff, applied_results, error_detail}` — propose a diff, review, apply, record per-item results |

And the constraint that makes a weak model usable, already written at the top of
`glossary_build/engine.py`:

> every step is ONE call; invalid JSON gets ONE retry (with the parse error fed back), then the
> item/section is SKIPPED with a record. **No step can loop.**

**So this design adds one thing: the elicitation machine** — what to ask, in what order, and what
to do with the answer.

---

## 3 · The unit: one run per target node

An `intent_run` is scoped to **one `outline_node`** (a chapter or a scene) — never the book. That
follows directly from claim 1. A book-level run would be the upfront-intent mistake again.

State is `(status, slot_cursor)`:

- `status` — the phase the run is in
- `slot_cursor` — which slot the phase is about

Both live in Postgres; every move goes through the optimistic `transition` above, so a duplicate
click, a double-delivered event, or two devices cannot advance the same run twice.

---

## 4 · The state machine

```
                    ┌──────────────────────────────────────────┐
                    ▼                                          │
  opened ──▶ proposing ──▶ awaiting_author ──▶ applying ──▶ advanced
    │            │               │                 │            │
    │            │               ├── declined ─────┤            │
    │            ▼               │                 ▼            │
    │        proposal_failed     └── revised ─▶ applying     (next slot)
    │            │                                              │
    └────────────┴──────────────────────────────────────────▶ done
```

| state | who acts | what happens |
|---|---|---|
| `opened` | — | the run exists; nothing asked yet |
| `proposing` | agent | **one** LLM call: N candidates for `slot_cursor`, grounded (§5) |
| `proposal_failed` | — | one retry consumed, still unusable → the slot is left **unasked** and SAID SO. Never a silent skip |
| `awaiting_author` | **author** | blocking checkpoint: accept · revise · decline |
| `applying` | agent | write the accepted value to the node (atom edit) |
| `advanced` | — | cursor moves to the next slot |
| `done` | — | no slots left in scope |

**Every author-facing state is blocking.** There is no "the agent finished the chapter spec while
you were away". That is deliberate: an unattended fill loop is exactly how a model invents canon.

---

## 5 · Slot order: closed sets first

The order is **by constraint, not by narrative convention**.

1. **Closed-set slots first** (`beat_role`, `value_shift` direction, POV from the book's cast).
   A weak model is good at *picking from a set* and bad at *open invention* — so the cheapest,
   most reliable questions come first.
2. **Each answered slot narrows the next.** Once `beat_role='midpoint'` and POV are fixed, the
   candidate space for `goal` and `conflict` is far smaller, and the proposal quality rises for
   free — without changing the model.
3. **Open slots last**, and never from a blank prompt: the call carries the canon in scope (the
   entities present, via the glossary/KG grounding fixed earlier today) plus every slot already
   filled. The model **transforms**, it does not invent.

This is the same lever that took extraction from 4/7 to 7/7 on the live Mị Đế passage: the model
was never the limit, the missing context was.

---

## 6 · Three slot states, not two

Reusing the distinction built this morning for attribute fill (`absent` vs `missing` vs `extra`):

| slot state | meaning | machine behaviour |
|---|---|---|
| `unasked` | the FSM has not reached it (or a proposal failed) | may be asked later |
| `absent` | **the author said the story has not decided this** | **never re-asked, never auto-filled** |
| filled | has a value | editable, re-openable on request |

Collapsing `absent` into `unasked` is what makes an auto-fill loop dangerous: it re-asks things the
story genuinely has no answer to, and the model obliges by inventing. `absent` is an **authored
statement**, not a gap.

---

## 7 · Why a state machine at all

A plain chat loop with a weak model fails in ways an FSM makes impossible:

| failure without rails | what the FSM does |
|---|---|
| the model answers three slots at once, badly | one slot per call |
| it drifts back to a slot already settled | the cursor only advances; a settled slot needs an explicit re-open |
| it re-asks something the author declined | `absent` is terminal for that slot |
| a bad JSON reply wedges the run | one retry, then `proposal_failed` — recorded and surfaced |
| two devices/double-click double-apply | optimistic `transition` 409s the loser |
| it "finishes" while the author is away | every author state is blocking |

The FSM is not ceremony. **It is what converts a weak model from an unreliable collaborator into a
reliable component**, by shrinking every decision it makes to one the size it can actually handle.

---

## 8 · The POC — and the two failure modes it must separate

The PO's question:

> gemma (model yếu) + state machine có khả năng hiểu và khai thác, gợi ý cho tác giả không? hoặc là
> làm đúng theo ý muốn của tác giả không?

That is **two different questions with two different fixes**, and they must be measured separately:

**A · Suggestion quality** — given canon + filled slots, are the N candidates usable?
Metric, per slot: of N candidates, how many would the author *accept* or *lightly edit*, vs
*discard outright*. Scored by the author (PO), not by a judge model — the whole point is authorial
taste.

**B · Apply fidelity** — given the answer the author accepted or rewrote, does the artifact end up
saying exactly that?
Metric: `exact` / `drifted` (meaning changed) / `dropped` (silently lost). This is the same bug
class as the frontend-tool contract: a weak model that quietly rewrites the author's own words is
worse than one that suggests badly, because the author will not re-read what they just approved.

**Hypothesis to falsify:** *a weak model scores far better on B than on A, and A rises sharply with
slot constraint (closed-set > canon-grounded open > blank open).*

If it holds, the response is **not a bigger model** — it is more constraint: more closed sets, more
canon in scope, smaller slots. If it fails on B, the design is in trouble and needs a verifier step
before apply, because the author's own words being altered is not a quality issue but a trust one.

**Run shape:** Mị Đế, real canon (14 entities), one chapter node, all slots, N=3 candidates,
gemma local (\$0). Compare against the same run with the slot order reversed (open slots first) to
isolate the constraint effect from the model.

### What every slot must record — the instrument, not a demo

The POC is a **measuring instrument**. If it only answers "did it work?", it has failed, because the
three parameters in §10 are settled from this same data. One row per slot:

| field | why it is needed |
|---|---|
| `slot`, `position` (1…N) | Q1 — decay of acceptance across the run |
| `constraint_class` (`closed` · `canon_open` · `blank_open`) | separates §5's effect from fatigue; the reversed arm needs it to be readable |
| `arm` (`constrained_first` · `reversed`) | the controlled comparison |
| `verdict` (`accept` · `light_edit` · `discard`) per candidate | metric A, scored by the author |
| `author_value` and `applied_value` | metric B is `exact` / `drifted` / `dropped` — computed, not judged |
| `outcome` (`applied` · `absent` · `proposal_failed`) | keeps a declined slot distinguishable from a broken one (§6) |
| `llm_calls`, `retried` | proves the "one call, one retry, no loop" bound actually held |

Two rules learned the hard way today:

- **Score A by the author, compute B mechanically.** B is a string comparison; letting a model judge
  it would be asking the thing under test to grade itself.
- **A `proposal_failed` slot must never be silently dropped from the tally.** A run that quietly
  omits its failures reports a better acceptance rate than it earned — the same shape as the
  `empty`-counted-as-degrade bug fixed in `d5a9bae14`.

---

## 9 · Out of scope here

- The **conversational surface** (how the checkpoint renders in the co-writer chat) — a later slice.
- **Multi-author** intent (two collaborators disagreeing on a slot) — the grant model already
  scopes writes; concurrent intent is a separate design.
- Auto-advancing without an author — deliberately never.

---

## 10 · The three design parameters — settled by MEASUREMENT, not by argument

These were first written as "open questions for the PO". That was the wrong frame, and the PO said
so: **cái này phải đo mới biết.** Each one has a defensible answer on both sides, which is exactly
the signature of a question that opinion cannot close. So they become **variables of the
experiment**, and §8's instrumentation has to be rich enough to settle them.

This matters beyond these three: every inference made during the 2026-07-28 run that was not
measured turned out wrong — duplicates blamed on the missing index (they were legacy kind-forks),
`_text` blamed for a false-dirty (it was the empty mount doc), a cross-book leak that was a plan
outline, a `tsc` failure that was a stale `npx`. **The pattern is not bad luck; it is that plausible
mechanism is not evidence.**

### Q1 · Slot scope per run — how many questions before the author is spent?

*All 12 chapter slots, or only what the author asks about?* "All" risks a 12-question interrogation
before a single word is written; "asked-only" risks a spec too thin to draft from.

**Measured by:** acceptance rate as a function of **slot position in the run**. Every slot already
records accept / light-edit / discard (§8 A), so plot that against position 1…N.
**Reads as:** a clear decay after position *k* ⇒ cap a run at *k* and let the rest be asked later.
Flat ⇒ scope is not the constraint and "all" is safe.
**Confound to control:** position is entangled with constraint class (§5 puts closed sets first, so
early slots are also the easy ones). The reversed-order arm already in §8 separates them — if the
decay follows *position* in both arms it is fatigue; if it follows *constraint* it is §5 working.

### Q2 · Scene runs — own run, or inherit the chapter and fill deltas?

**Measured by:** for each scene, how many of its slots end up **differing** from the chapter's
value. Run both arms on the same chapter: a full scene run vs a delta-only run seeded from the
chapter.
**Reads as:** most slots inherited unchanged ⇒ deltas win, and a full scene run is asking the author
to re-answer what they already said. High divergence ⇒ scenes carry their own intent and deserve
their own run.

**~~Cheap signal available first from existing outline nodes.~~ Measured 2026-07-28 — there is
nothing to read.** Across the WHOLE database:

| kind | nodes | goal | conflict | outcome | stakes | value_shift | beat_role | tension | synopsis |
|---|---|---|---|---|---|---|---|---|---|
| chapter | **95** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| scene | 79 | 2 | 0 | 0 | 0 | 0 | 6 | 33 | 29 |

**Not one of 95 chapter nodes carries a single intent slot.** A first pass on the one book with a
full 10-chapter / 27-scene outline read as "27 of 27 scenes match their chapter" — an artifact of
both sides being empty, not inheritance. The corrected read is the table above.

Two consequences:

1. **The slots are effectively dead columns.** The schema has modelled chapter intent all along and
   nothing has ever written to it. So this FSM is not an enhancement to an existing flow — it is
   the missing mechanism, and §2's "nothing needs inventing" is true of the *storage* only.
2. **Q2 cannot be answered from history; it needs the POC.** The delta-vs-own-run arms have to be
   run, not mined.

### Why chapter intent is empty — traced 2026-07-28

The earlier cycle's "10/10 chapters now carry a beat role" was **true, about the plan artifact**.
`plan_artifact(kind='beat_plan')` holds the full curve — hook · establishment ×2 · rising_conflict
×3 · setback ×2 · **climax = "The Void"** · resolution. `outline_node.beat_role` holds none of it.
Two representations, diverged. Tracing why turned up two distinct causes, and my first two readings
of it were both wrong:

**1 · The chapter node is never given its beat role — justified by a stale comment.**
`_insert_decomposed_tree` creates the chapter node WITHOUT `beat_role`, then passes the *chapter's*
`beat_role` to each of its **scenes**. Its docstring explains why: *"beat_role is stamped on the
SCENES (DB CHECK forbids it on chapter)"*. **The constraint no longer says that:**

```sql
outline_beatrole_kind CHECK (beat_role IS NULL OR kind = ANY (ARRAY['scene','chapter']))
```

`'chapter'` is explicitly allowed. The check was widened; the comment and the code never followed.
This is the exact bug class CLAUDE.md names — *verify the claim against code, a doc note goes stale*
— and it cost me two wrong reads in a row: first "found the bug", then "not a bug, the CHECK
forbids it", before actually querying `pg_constraint`.

**2 · The planner emits an empty chapter intent.**
The chapter node is supposed to carry the beat intent in `goal`, set from `ch["intent"]`. Measured
across the three newest `scene_plan` artifacts: **0 of 30 chapter entries have a non-empty
`intent`.** So `goal` is written as `""` every time.

**Net:** a chapter node ends up with no intent by EITHER route — the role is dropped on the floor
and the intent field arrives empty. That is the whole explanation for the 0/95 table above, and it
is the strongest argument for this spec: chapter-level intent has no producer today.

**Consequence for the design — which store is the SSOT?** Not settled here, and it must be before
the FSM writes anything, or the FSM adds a *third* representation to two that already disagree.
The candidates are the outline node (queryable, joins to prose, what the rail reads) and the plan
artifact (versioned, what the planner emits). Whichever wins, the other has to become derived —
that is the point of the two-layer pattern the glossary/knowledge split already uses.

### Q3 · Re-opening a settled slot — free or gated?

**Not answerable yet, and saying so is the point.** The risk being weighed — a re-opened slot
silently diverging from prose already written — cannot occur until prose exists. Measuring it now
would produce a number about nothing.

**Measured by (later, once a chapter is drafted):** re-open a settled slot, then check whether the
written prose still satisfies it. Frequency of divergence is the answer: rare ⇒ free re-open;
common ⇒ gate it, or make the divergence loud (the `chapter_error_block` machinery already exists
for exactly that kind of marking).
**Sequencing:** Q1 and Q2 run in the first POC; Q3 is a second pass **after** the first chapter is
written. A design that claims to have settled Q3 before then is guessing.
