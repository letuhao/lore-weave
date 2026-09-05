# The twelve invariants — final report

Reconciles: MCP Tool I/O Standard · Agent GUI Reconciliation (09) — every one of the twelve is a turn-level invariant about a tool being reachable, called, and honestly reported, which is those two rows' territory. What it adds is enforcement at a chokepoint, not a rule: the report's own §2 is about mechanisms that existed and were never called.

**Date:** 2026-09-03 · **Branch:** `feat/frontend-tools-mcp-migration`

```
cd scripts/toolloop && python problem_remaining.py     # exits 0
```

`problems=16  cleared=16  TOOLS PROVEN / INVARIANT OPEN=0  empty=0  in_progress=0`
`tools_in_denominator=65  proven=65  still_blocked=0`

---

## 1. Per problem: the invariant, its chokepoint, its falsifier

Cycle order is the ledger's own, which is damage-ordered. The four not in the queue (P3, P10, P4,
P13) were already cleared and are listed for completeness.

| # | Problem | Invariant | Chokepoint | Falsifier |
|---|---|---|---|---|
| 1 | **P1-SURFACE** | A tool the request names must be reachable in that turn, and when it is not, the turn may not claim its effect | `test_a_measured_turn_reaches_its_tool_gate.py` over every measured turn + R1 at runtime; `_claimed_an_effect_without_acting` for clause 2 | remove the 4 declaration widenings → red on exactly those tools and scenarios |
| 2 | **P5-SIBLING-WINS** | A request must reach the tool built for it; no two live tools may claim the same words | `test_no_two_live_tools_claim_the_same_words.py` — 0 live collisions of 88 shared phrases | re-declare DQ-T41's own instance (`jobs_cancel` + `translation_job_control` both claiming *stop translation*) → red |
| 5 | **P16-PROSE-CONFIRMATION** | A turn holding every argument a write needs may not ask for consent in prose | `_asked_instead_of_acting` at the shared directive site | empty the detector → the measured instance goes red; AST test proves it is *called* |
| 6 | **P2-FABRICATED-WRITE** | A turn may not assert a change it did not make, nor act on content it invented | `_claimed_an_effect_without_acting`; `source_ref` required + `_resolve_authors_source` overwriting at the dispatch seam | weaken the overwrite to fill-if-blank → 3 red |
| 8 | **P14-SUPPLIER-NOT-ON-SURFACE** | Every id a tool requires must be obtainable from the same surface, **transitively** | the R1 block of `_advertise_discovery_tools`, walking `argument_emitters` to a fixpoint | restore `_pending = []` → the new depth-2 test goes red |
| 9 | **P6-DESCRIBE-NOT-RECORD** | When the request names an artefact the platform can store, prose about it is not an answer | `_instruction_names_a_recorder`, last among the end-of-turn guards | empty the detector → red; separated from the read guard by grammar, not intent |
| 11 | **P7-FALSE-ABSENCE** | A store that accepts a write must have a read that can find it | `search_facts_by_text`, awaited as a third leg of `memory_search` | delete the leg → the new AST wiring test goes red |
| 12 | **P8-ANSWERABILITY** | A declared synonym must match the sentence a person types | the same measured-turn gate as P1 | the gate was red on exactly the six motif scenarios before the declarations were widened |
| 13 | **P12-RAIL-PINNED-TURN** | A turn must emit an assistant message | the turn's terminal path — `_last_tool_error_for_author`, `_last_tool_success_for_author`, and DQ-T56's ceiling arm | bypass the fallback → the class-level AST gate goes red |
| 14 | **P15-TRANSPORT-STALL** | A tool cannot be adjudicated on a turn the transport killed | `gate.py`'s `LIVE clean` bar + DQ-T40's `unmeasurable` terminal state | excuse the bar → 3 red |
| 15 | **P9-INTENT-GATE** | A gate must open on what the request asks for, not on the vocabulary it uses | DQ-T31's declaration arm in `filter_intent_gated_setup_tools`, before the removal | remove the arm → 6 red across 3 files |
| 16 | **P11-DISTRIBUTION** | K≥3 as a *distribution* is the bar; a tool chosen 3 times in 15 is not proven by the 3 | `gate.py`'s SELECTION verdict below `LOTTERY_BELOW` = 0.4507, which never yields `proven` | the ratchet was red on 10 downward crossings |

---

## 2. What this loop was actually about

Not twelve unrelated defects. **Six of the twelve were not blocked by what their own status said
blocked them**, and five mechanisms could be deleted with their own test suites still green.

### The stale blocker

Every DQ named as a blocker had been answered — most of them **built** — days before this loop
began, and no row learned:

| Problem | Said | Actually |
|---|---|---|
| P2 | "DQ-T35 is the blocker" | DQ-T35 is about `model_ref` on a different tool. The defect row had **already corrected this** on 2026-08-28; the correction never propagated |
| P8 | "CANNOT BE CLEARED WITHOUT DQ-T32" | answered 2026-08-28, five days later |
| P12 | "FIX GATED ON DQ-T33" | answered *and built* 2026-08-28 |
| P9 | "the fix is an OWNER decision (DQ-T31)" | answered *and shipped* 2026-08-28 |
| P11 | "needs an owner ruling on what bar a low-rate tool must meet" | DQ-T51, answered 2026-08-28 |
| P15 | "BLOCKED ON EXTERNAL VISIBILITY" | the logs resumed ~2026-09-01 and name the cause |

A status is a claim with a timestamp, and nothing re-reads it when the world moves.

### The unguarded mechanism

Five mechanisms were implemented, argued for at length in their own docstrings, and **assertable
away without a single test noticing**:

| Problem | Deleting the wiring left |
|---|---|
| P14 · the transitive supplier walk | 4 of 4 green |
| P7 · `memory_search`'s fact leg | 20 of 20 green |
| P12 · the silent-turn fallback | 21 of 21 green |
| P15 · `gate.py`'s LIVE clean bar | 11 of 11 green |
| P16 | pre-empted — an AST check was written with it |

In two cases the record *claimed* a falsifier that tested something else. P14's said the
chokepoint shipped "with a falsifier proven RED against the original" — it proved the depth-1 hop
while the invariant is the word **transitively**. P7's twenty tests exercise the repository
function, which is the right thing to test and is not what broke.

**It is not carelessness about testing.** A pure function is easy to test and a *call site* is
not, so tests go where the testing is easy and the wiring is left to a review that will not notice
one deleted line among six thousand. Hence
`services/chat-service/tests/test_no_turn_guard_is_defined_and_never_called.py`: eight named
guards, asserted by AST to be called at all, proven red on three original defects. It says nothing
about *when* a guard fires — that is the per-guard tests' job. What it makes impossible is a guard
that fires never.

**P9 is the one that broke the pattern**, and the difference is instructive: its guard was written
*with* the mechanism, by the same hand, on the same day.

---

## 3. Refused rather than done

- **P8 · `memory_recall_entity`.** The phrase that would close its remaining turn is already
  declared by `memory_search`. Adding it creates the live collision P5/DQ-T41 forbids and a gate
  enforces. Clearing one problem by violating another's invariant is not clearing anything.
- **P5 · removing `jobs_cancel`'s borrowed phrase.** Measured first, and it is *worse*: the
  sentence then reaches nobody and `jobs_cancel` loses its own turn. The domain tool took a
  book-scoped form instead.
- **P1 · `book_chapter_create`.** The one contiguous alternative claims three `composition_generate`
  prose turns — a wrong-tool hit traded for a surfacing miss. Baselined with the measurement.
- **P11 · absorbing the seven downward crossings.** Regenerating the contract records the new
  rates; it does not re-validate seven `proven` verdicts that predate their crossing. Named, not
  absorbed.

---

## 4. Checkers fixed rather than data deleted

The goal forbids deleting a historical field to satisfy a checker. Three needed fixing:

1. **A dated field superseded by a newer status** is history, not a veto — P3 was open on a
   `cannot_clear_2026_08_23` field while its own status read `CLEARED 2026-08-24`.
2. **A field's own text carries its date** — P8's veto lived in an undated `diagnosis` that cites
   `blocked_on_dq_2026_08_23` with underscores, where prose uses hyphens.
 — the rule refused *any* empty problem
   before consulting status or note, so no amount of enforcement could satisfy it. **My first
   attempt at this was a loosening and a guard caught it**: `test_an_emptied_problem_is_not_cleared`
   asserts that a CLEARED status plus a note is *not* enough, because "emptying a problem says
   where its TOOLS belong, not that its invariant holds". It is right. An emptied problem must now
   also name a chokepoint **that exists on disk** — prose cannot satisfy it, and the guard passes
   unchanged. `verdict()` needed the same correction one level up: it returned `empty` before
   consulting the definition, so an emptied problem's verdict could never track its enforcement.

   A fourth followed: `test_the_real_partition_has_more_unmet_than_cleared` asserted
   `len(unmet) > len(cleared)` and would have gone **red on success** — the only way to make it
   green again is to stop finishing the work. It anticipated this and said so: *"if this ever
   flips, the loop is genuinely nearly done and this assertion should be replaced by a stricter
   one."* Replaced with the relation it was approximating — a problem reads `cleared` if and only
   if its tools are proven **and** its definition holds, in either direction — plus a control that
   fails if the definition stops refusing anything.

Each was verified to still discriminate in every direction, including the ones that must stay
refused.

---

## 5. What is NOT done

1. **The transport stall is not fixed.** The cause is named — LM Studio unloads the model on a
   TTL and an in-flight prediction dies with *"Model is unloaded"*, 3–4 evictions a day. The
   remedy is a provider setting outside this repo, and criterion (b) — a cold run at
   `--concurrency 1` — has still never been run.
2. **P16 has no live evidence.** Eight runs against the deployed build: the tool surfaced 8/8 and
   `plan_bootstrap_propose` was called **zero** times, so the turn was never equipped and the
   guard was correctly silent. The 2026-08-24 instance does not reproduce.
3. **Seven live tools sit below the selection bar with `proven` predating the crossing.**
4. **Each `cleared_note` names more.** Twelve of them, written before the status changed, because
   naming what a fix does not cover is what stops the next reader over-reading it.
