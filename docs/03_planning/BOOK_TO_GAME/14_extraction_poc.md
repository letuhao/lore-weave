# 14 — The extraction POC: arms, controls, and a scorecard

`13` measured the shipped pipeline. This is the plan for changing it: a set of arms that each attack
one of the measured defects, run against a fixed corpus slice with everything else held still, scored
on one card.

The goal is **not** "make extraction faster". It is to find out which of the measured costs are real
and which are load-bearing — because `13` says 86% of the input is overhead, and if that is removable
without a quality loss then the PO's 5–10× problem is arithmetic rather than architecture.

---

## 1. The prerequisite: repair the instrument before running anything

`BTG-A38`: the pipeline's groundedness check reports 44.6% failure where the real rate is 2.4%. It is
about to become the primary quality axis for seven arms.

> **`BTG-A40`.** **An instrument whose noise floor is 18× the signal cannot rank arms.** If arm A
> improves true fabrication from 2.4% to 1.2% and the matcher reports 44.6% → 43.9%, the result is
> indistinguishable from run-to-run variance. **Repairing `validate_evidence` is step zero, and it is a
> measurement prerequisite, not a quality improvement.**

The repair is bounded and already specified by the classification in `13` §5.1:

1. **Unicode/punctuation fold** before search — NFKC, CJK punctuation and dash variants, trailing
   terminators. Recovers ~39% of the failures.
2. **Ellipsis-aware split** — `...`/`…` splits the quote into fragments; all fragments present, in
   order, is a legitimate abridged citation. New status `abridged`, with the span of the first and last
   fragment. Recovers ~19%.
3. **Near-match threshold** — a contiguous run covering ≥70% of the normalised quote is `partial`, not
   `unmatched`. Recovers ~20% into a *distinct, honest* bucket rather than into `resolved`.
4. Everything else stays `unmatched` — and *that* is now the fabrication number.

**Non-vacuity obligation (NV-2).** The repaired matcher must still fail on the 42. The bite test is
mechanical: feed it a quote known to be absent, assert `unmatched`; feed it a `resolved` quote with a
character deleted mid-string, assert it does not silently upgrade. A matcher tolerant enough to accept
everything is exactly the defect this project has recorded twenty-seven times — *a check that cannot
fail*. The tolerance must be tight enough that the 42 stay red, and that assertion goes in the test
suite, not in this document.

## 2. Controls — what is held still

The 57-chapter run cannot be used as a baseline for arm comparison, and the reason is a trap worth
naming:

> **`BTG-A41`.** **The known-entity context makes extraction runs path-dependent.** Chapter 40's prompt
> contains what chapters 1–39 produced, so an arm run after another arm inherits its predecessor's
> discoveries and scores higher for a reason that has nothing to do with the arm. **Every arm must
> start from the same frozen known-entity snapshot**, and the snapshot must not advance during the run,
> or the comparison measures ordering.

| control | value |
|---|---|
| corpus | the same **10 chapters** for every arm — chapters 21–30, mid-book, past the court-politics opening, entity-dense |
| known-entity context | **frozen snapshot**, identical for all arms, taken once and never advanced |
| model | Gemma-4 26B-A4B QAT, resolved by role via `scripts/dev-model.py` — never hardcoded |
| sampling | `reasoning_effort: none`, temperature fixed, same seed where the backend honours one |
| kinds / attributes | the same 8 kinds, 59 attributes, same profile |
| concurrency | **1**, so wall-clock measures the arm and not the scheduler |
| writes | **none at all** — see below |

**Revision, made while building the harness: there are no database writes.** The control above
originally called for a throwaway book. Scoring entirely in memory is strictly better — there is
nothing to contaminate, no cleanup to get wrong, and no path by which a stray write reaches the live
glossary. It is possible precisely *because* the known-entity snapshot is frozen: nothing an arm
discovers is allowed to reach the next chapter's prompt anyway, so there is nothing writeback would
be for. The harness imports the worker's own builders, parser and provenance validator and
reimplements only the **call loop**, which is the thing the arms vary; a harness that rebuilt the
prompt would be measuring itself.

> **`BTG-A44`.** **A0 is not a baseline, it is the harness's own correctness test.** If A0 does not
> reproduce the shipped pipeline's measured per-chapter cost (~21.8k in / 6.8k out over 3 calls,
> adjusted for this slice's shorter chapters), then the harness is not measuring the pipeline and
> **no other arm's number means anything**. This caught its first bug immediately: the harness passed
> the wrong third argument to `parse_and_validate_with_stats`, every batch returned zero entities, and
> the run reported *1 call and 7.6k input* — which is a plausible-looking number, and would have been
> read as a result rather than as a broken harness had A0 not had a figure to reproduce.

Run-to-run variance on a non-deterministic backend is itself unmeasured, so **arm A0 runs twice**. If
two identical runs differ by more than the gap between two arms, the gap is not a result. This has bitten
this project before (probe P15).

## 3. The scorecard

One table, filled identically for every arm. No weighted composite — `MEM-A7`: a weighted score over a
small categorical rubric is a rubber stamp. The arms are read on the axes, and the trade is the human's.

**Cost**

| metric | how |
|---|---|
| input tokens / chapter | job telemetry |
| output tokens / chapter | job telemetry |
| LLM calls / chapter | job telemetry |
| cached-prefix share | provider usage fields where exposed; else prompt-prefix stability measured offline |

**Speed**

| metric | how |
|---|---|
| wall-clock s / chapter | at concurrency 1 |
| time-to-first-token | the part prefix caching actually moves |

**Quality** — all deterministic except Q4.

| id | metric | how | non-vacuity |
|---|---|---|---|
| **Q1** | groundedness | % evidence rows `exact`/`resolved`/`abridged` under the repaired matcher | varies 55%→? across arms; bite-tested per §1 |
| **Q2** | fabrication | % `unmatched` after repair | 2.4% today; must stay able to rise |
| **Q3** | charset fidelity | % rows with a character absent from the book (0.9% today) | already fires on 16 rows |
| **Q4** | kind conformance | vs a **frozen human answer key**, §4 | the only human-scored axis |
| **Q5** | yield | entities/chapter, and NEW entities/chapter | guards against an arm that gets cheap by extracting less |
| **Q6** | duplication | entities a normalising dedup would merge | guards against an arm that gets cheap by losing the known-entity context |

**Q5 and Q6 are the anti-gaming axes and they are not optional.** Every cost arm below can be "won" by
extracting fewer entities or by dropping cross-chapter awareness. Without yield and duplication on the
same card, a 4× cost reduction that quietly halves recall reads as a success.

## 4. The answer key — and it settles an open falsifier

Q4 needs ground truth, and the cheapest honest source is the one `10` §6 already asked for and never
got: **read all 41 place-suffix-flagged `organization` entities and label each**. Authoring the answer
key and running the falsifier are the same afternoon of work.

Its outcome decides more than a metric:

* **mostly collapsed pairs** → `BTG-A28` survives, the fix is `10` lever ① (split the pair, `SEAT_OF`).
* **mostly plain misfiles** → `BTG-A28` is wrong, `BTG-A31` was right that the literature's ~19%
  metonymy base rate makes it unlikely, and the fix is levers ④ + ② (contrastive definitions, derive
  the kind).

The key is frozen once and reused by every arm. It is small (55 entities), which is a real limit on
Q4's resolution and is stated on the card rather than hidden.

## 5. The arms

Ordered by cost-to-try. Each names the measured defect it attacks.

### A0 — baseline (control, run twice)
Current code, current template, 3 calls. Establishes the per-chapter numbers on *this* slice with the
frozen context, and establishes run-to-run variance.

### A1 — one call, all 8 kinds
**Attacks `BTG-A36`** — the 3× duplication of chapter text and boilerplate. Predicted −55% input chars.
**The risk is the reason `MAX_KINDS_PER_BATCH = 3` exists**: output truncation at `max_tokens`, which
returns unparseable JSON and silently loses a whole batch. So A1 must be run *with* the guard that makes
it survivable — raised `max_tokens` and the truncation-repair path — and `finish_reason=length` is a
recorded outcome, not a footnote. If A1 truncates, that is the result.

### A2 — cache-ordered template
**Attacks `BTG-A37`.** Reorder `SYSTEM_TEMPLATE` to `static boilerplate → known entities → schema →`
chapter text last, changing no content. Measures time-to-first-token and cached-prefix share. On a
local llama.cpp backend prefix caching is automatic; on a paid provider it needs explicit markers, and
whether the saving survives the switch is part of what this arm answers.

#### What A2 is worth, settled without an LLM

Prefix caching is a claim about **string prefixes**, so it can be measured exactly —
`prefix_cacheability.py`, no model, no timing noise. Per chapter, over the frozen slice:

| shape | sent | cacheable prefix | fresh after a perfect cache |
|---|---|---|---|
| A0 as shipped, 3 batches | 35,981 | 8,288 | 27,693 |
| **A1 one call** | 16,212 | 9,806 | **6,405** (−76.9%) |
| A2 3 batches, reordered | 36,092 | **15,918** | 20,174 (−27.1%) |
| A3 one call + reordered | 16,249 | 9,840 | 6,409 (−76.9%) |

> **`BTG-A45`.** **A1 subsumes A3 — reordering buys nothing once there is one call per
> chapter.** With a single call the entire system prompt is *already* byte-identical from
> chapter to chapter (only the user message changes), so there is no ordering left to fix.
> Reordering is worth 6× on the within-chapter shared prefix (1,506 → 9,102 chars) and is
> therefore the **fallback** for the case where batching cannot be given up — not a
> stacking improvement. `14` predicted A3 would be "the interesting one"; it is not.

This must be read as an **upper bound on what caching could buy**, not a realised saving:
it assumes a perfect prefix cache, and `usage.input_tokens` cannot corroborate it, because
LM Studio caches server-side and reports no cache tokens on the OpenAI-compatible chat
endpoint. A hit shows up only in wall-clock here, and in the bill on a provider that does
report reads (typically ~90% cheaper than a fresh input token).

So the **live** A2 arm answers a different question from the table: *does reordering cost
any quality?* The content is identical and only the order changes, so if extraction gets
worse, section order carries meaning and the caching win has a price.

### A3 — A1 + A2
Kept as a **control**, not as a candidate. The measurement above already shows it lands on top of A1
(6,409 vs 6,405 fresh chars per chapter), so its job is now to confirm that combining the two changes
does not *degrade* anything — if A3's quality differs from A1's, the reordering is doing something the
prefix arithmetic does not see.

### A4 — delta-only output
**Attacks `13` §4** — 88% of entity writes are re-writes of entities the glossary already holds. Ask
for a delta (new entities in full; known entities only when the chapter adds something) and measure
whether output collapses **and whether Q5/Q6 hold**. This arm is the most likely to look brilliant and
be wrong: an arm that stops re-describing known entities also stops *correcting* them.

### A5 — two-stage, extract then type (EDC)
**Attacks `09`'s kind error and `BTG-A29`.** Stage 1: a cheap open sweep for named mentions, small
output, no attributes. Stage 2: type and enrich, but only for mentions that are not already known.
This is `11` §3's citation-backed shape and `10` lever ②, and it is the only arm that can move Q4
substantially. It is also the only arm that changes the *platform* pipeline's contract rather than its
prompt, so it is the expensive one — and it should not be built until A1–A4 have shown how much of the
cost problem is already solved without it.

### A6 — GLiNER as a second reader
**Attacks the fact that nothing disagrees with the extractor** (`10` §3, `12` §4②). Not on the cost
path at all: run the encoder over the same 10 chapters and measure **agreement with the LLM's kinds**
against the same answer key. It answers one question — *is a second reader worth wiring in?* — and
`12` §5 already warns the honest answer may be no, because its published numbers are English
benchmarks and 文言文 is unmeasured.

> **`BTG-A43`.** **A6 has a shape constraint the other arms do not, and it is worth knowing before
> the measurement rather than after.** `import gliner` inside a service is a direct model-SDK import,
> which the provider-gateway invariant forbids — and the invariant explicitly covers local backends
> (`D-RERANK-NOT-BYOK` is the recorded case of getting this exactly wrong: rerank was first wired as
> per-service `RERANK_URL`/`MODEL`/`TOKEN` config instead of resolving through provider-registry).
> This repo already runs `local-rerank-service`, `local-stt-service` and `local-tts-service` on that
> pattern, so if A6 wins, the production shape is **a sibling `local-ner-service` registered as a BYOK
> provider credential with a `user_models` row**, reached through an `/internal/*` provider-registry
> route — not a library call. The POC may import the library directly because a spike is not a
> service, but the cost of adopting A6 is *a service*, and that belongs on the card next to its
> accuracy.

## 6. What would make this POC a failure

Stated up front, so the result is not narrated afterwards:

* **A0's two runs disagree more than the arms do.** Then the corpus slice is too small or the backend
  too non-deterministic, and every ranking below is noise. This is the first thing to check and the
  most likely way the exercise dies.
* **The cost arms win on cost and lose on Q5/Q6.** A cheaper pipeline that extracts less is not a
  cheaper pipeline; it is a smaller one. If A3 halves cost and drops yield 30%, the correct report is
  that the overhead was doing something.
* **Q4 does not move on any arm.** Then the kind problem is not a prompt-shape problem, `10`'s levers
  ① and ② are both wrong, and the answer is the second reader or a better model — which is a finding,
  and a more expensive one.
* **The repaired matcher accepts everything.** §1's bite test exists for exactly this, and if the 42
  stop being red the instrument is worse than before it was touched.

## 7. Sequencing

```
0. repair validate_evidence + bite tests          ← prerequisite, blocks everything
1. freeze the corpus slice, context snapshot,
   throwaway book, answer key (= 10 §6 falsifier)
2. A0 ×2  → variance floor
3. A1, A2, A3, A4                                  ← prompt/shape arms, cheap, no contract change
4. read the card; decide whether A5 is still needed
5. A6 independently — it blocks nothing
```

Steps 0–3 are one continuous effort and cost nothing but local GPU time. **Step 4 is a real decision
point**, and the point of ordering it this way is that A5 — the expensive, contract-changing arm the
literature endorses — should be justified by a measured residue rather than by its citations.
