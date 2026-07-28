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

---

## 9 · Out of scope here

- The **conversational surface** (how the checkpoint renders in the co-writer chat) — a later slice.
- **Multi-author** intent (two collaborators disagreeing on a slot) — the grant model already
  scopes writes; concurrent intent is a separate design.
- Auto-advancing without an author — deliberately never.

---

## 10 · Open questions for the PO

1. **Slot scope per run.** All slots of a chapter, or only the ones the author asks about? Defaulting
   to "all" risks a 12-question interrogation before a single word is written.
2. **Scene slots.** Does a scene get its own run, or inherit the chapter's and only fill deltas?
3. **Re-opening a settled slot.** Free (any time, any slot) or gated (only while the chapter is
   unwritten)? Free is friendlier; gated keeps the written prose and its spec from silently diverging.
