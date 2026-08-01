# 13 — STOPPED: what was built, what was not, and what the pivot supersedes

**Status: this track is STOPPED, deliberately, on 2026-08-01.** Work moves to
[`BOOK_TO_GAME`](../../BOOK_TO_GAME/_index.md).

This document exists for one reason: **so the next session does not drift.** A stop with no record
becomes a half-remembered "we were doing something with pools", and the parts that were measured get
re-derived or, worse, re-argued. Everything below is an inventory, not a summary.

---

## 1. Why it stopped

Not because it failed. It works — 5 slots, 4 planner kinds, 2 consumers, a real freeze, 72 tests, and
live runs that produce usable content.

It stopped because **it was doing three tiers' jobs at once, and the middle two do not exist yet.**

A professional game pipeline has four document layers: Lore Bible → Narrative/Game Design → Data Spec →
compiled data. This track built the **fourth** layer (the slot registry and its compiler) and then, in
the absence of the first three, tried to reach all the way back to the novel for its material.

Two measurements made that untenable:

1. **The evidence was cooked by hand and the hand was not counted.** Every quality result rested on
   eleven bullet lines the author extracted — `a gold ring-shaped implement, resizable, thrown` is not
   in 封神演義; the novel has 乾坤圈 inside a battle scene. The planners did well because they were fed
   an *analysis*, produced by a step nobody had modelled.
2. **Substituting the raw source failed at the noise floor.** Slot-id queries against classical Chinese
   returned a lesson on playing the zither. Model-written queries in the work's register fixed the
   direction but not the problem, and the scraped wiki out-scored the novel while being less useful.

And the PO named the reason both of those happen: *the book is not a specification of the game.*
A line like *the ancient dragon roared and the whole mountain shook* tells a human reader Boss ·
huge · earthquake skill · fear aura · spawn location · drop table · faction · AI behaviour.
A generator cannot know which of those the author **wanted**. The missing tier is design, and no
amount of better retrieval substitutes for it.

## 2. Built, works, and survives the pivot

These become the **compiler** — the fourth layer, which is where they always belonged.

| artifact | what it is | state |
|---|---|---|
| `contracts/pool/registry.json` | 5 slots (`instrument_tag`, `item_archetype`, `equip_slot`, `progression_kind`, `progression_stage`), 2 owning modules, `engine_enums` | hand-authored; `"generated": false` and a test asserts it |
| `app/pool/registry.py` (213 L) | typed loader + three load-time refusals: identifier shape (an ASP-variable guard), CONFIRM-without-`default`, and SHARED-may-not-reference-PRIVATE | works |
| `app/pool/register.py` (135 L) | the open-decision register as clingo abduction; model text is quoted, never compiled as solver source | works |
| `app/pool/criteria.py` (265 L) | per-operation criteria, HARD/SCORED split, shared member-shape checks | works — **semantics change, see §4** |
| `app/pool/kinds.py` (329 L) | 4 planner kinds keyed by OPERATION, never by slot | works — **superseded, see §4** |
| `app/pool/loop.py` (231 L) | state machine in code, heal round carrying the previous answer, settle-then-stamp, per-consumer freeze | works |
| `app/pool/freeze.py` (241 L) | the artifact: digest + verify, `closure_for`, `consumers_of`, PRIVATE withholding, unmet demands carried forward | works |
| `app/pool/consume.py` (117 L) | `PoolView` — the only surface a generator gets; no method can return another module's L2 | works |
| `app/generators/item_l2.py`, `loot_l2.py` (303 L) | two consumers, one of which owns no slot | works |
| `tests/test_pool_cycle.py` + `test_generator_boundary.py` | 72 tests, no network | green |
| `tests/fixtures/fengshen/` | 4 book + 4 wiki files, **12 designed teeth**, answer key outside the corpus | green, 29 assertions |
| `scripts/doc-language-gate.py` | persisted artifacts are English; added-lines-only | wired pre-commit |
| `design-lint` spec-enum source | a count claim checked against an enum the doc itself declares | wired, `--selftest` 7/7 |

**Findings that survive and must not be re-derived** — each cost a live run to learn:

* a check nothing consumes is decoration, and it happened **twice** in one loop — once ignoring the
  verdict, once **laundering** it (recorded correctly, then read from a place that did not carry it)
* model text became **solver source**; `Blade` parses as an ASP *variable*, which is worse than a crash
* a requirement belongs in the artifact that states the contract, not in the checker that reads it
* a heal round that does not carry the previous answer is a re-roll wearing a repair's name
* a truthiness test on model text is not a test — the model produced the **string** `"null"`
* the boundary must be crossed to be tested; the pool-wide freeze passed every unit test for two cycles
  because no consumer existed, and broke within three live runs of one existing
* two of the author's own assertions could not fail (`hasattr` on a field the class lacks; a `|` inside
  an equality that papered over a real disagreement)
* **encyclopaedic text out-scores narrative while being less useful** — so cosine score is not a proxy
  for usefulness here, and a relevance floor tuned on score would keep exactly the wrong chunks

## 3. Built and measured BROKEN

| thing | measurement | tracked as |
|---|---|---|
| `probe()` — the retrieval query | returns slot ids and consumer path segments; **noise floor on every slot**, not one on-topic top-3 hit | `D-POOL-PROBE-IS-NOT-A-QUERY` |
| `evidence_n` | undefined against a real corpus; `m < n` needs a denominator that retrieved spans do not carry, and asking the model hands it the denominator of its own gate | `D-POOL-EVIDENCE-N-UNDEFINED-ON-A-REAL-CORPUS` |

## 4. Built, works, and is SUPERSEDED by the pivot

This section is the point of the document. These pieces are not wrong; they are **in the wrong tier**,
and resuming them as they stand would rebuild the mistake.

| piece | what it does today | what the pivot makes it |
|---|---|---|
| `kinds.py` — the four planner kinds | **ask a model to INVENT** the members (abstract, partition, confirm, classify) from evidence | invention moves to the design tier. The kinds become **readers of a design document**, not inventors. The operations survive; the prompts do not. |
| the evidence parameter + `EVIDENCE_N` | a hand-written block passed into the loop | the design document, with a table of contents. `n` becomes countable by construction. |
| `probe()` | retrieval from the novel | the compiler reads the design document; retrieval over raw narrative stops being on the critical path |
| the heal round | make the model produce better content | **the document is ambiguous — ask the author.** Same loop, different meaning, and it needs a return channel that does not exist |
| `criteria.py` | did the model invent well? | did the document **decide** this? A failure becomes a finding for a human, not a re-prompt |

> **`BLD-A20`.** The compiler must **invent nothing**. Everything in `kinds.py` that asks a model to
> choose is the design tier's work living in the wrong file. What survives is the *operation* taxonomy
> (`PARTITION` · `ABSTRACT` · `CONFIRM` · `CLASSIFY_LINK`) — because those describe what a **structure**
> is, not how it was decided, and a design document will still produce ladders, categories, confirmed
> defaults and classified links.

## 5. Never built

| | tracked as |
|---|---|
| Rust `declare_pool_slot!` + export + drift test — the registry is still hand-authored | `D-POOL-REGISTRY-NOT-GENERATED` |
| `REOPENED` is declared and unreachable; its trigger was measured (downstream under-coverage needs an upstream slot that already settled) | `D-POOL-REOPEN-UNREACHABLE` |
| the refusal channel carries two meanings in one `owner` field | `D-POOL-REFUSAL-CHANNEL-HAS-TWO-MEANINGS` |
| no L2 store, so *no module reads another module's L2* has no subject to violate | — |
| `EPL-A7` PRIVATE has **no production subject**, and structurally may never get one: a slot any SHARED slot references cannot be private | — |
| `lex_tag` unregistered — `WA_001` owns it; the last subject the `EPL-A8` demand channel has | — |
| the `BLD-A4` re-probe (no `rule_sentence`, hard `m ≤ n/2`) | — |
| **two PO decisions**: how many of the 19 competency questions must be answerable to ship; whether `PPB-A6` is adopted pipeline-wide (needs doc 38's 7 element-roster entries walked first) | — |

## 6. The anti-drift mechanism

Prose rots. A stop recorded only here would be re-argued in six weeks, so the pause is also
**mechanical**: `test_the_track_is_stopped_and_says_what_supersedes_it` pins the planner-kind count and
the slot count and reds the moment either grows.

That red is **not a prohibition** — it is a prompt to come here first. Extending the contract generator
before the design tier exists is the specific drift this document exists to prevent, and the test makes
the decision explicit instead of accidental.

## 7. What would restart this track

Not a date. A condition: **a game design document exists for one element family**, and the question
becomes *can the compiler read it*. That is `BOOK_TO_GAME` POC-C. Until then this track has nothing to
compile except a novel, and §1 is the record of how that goes.
