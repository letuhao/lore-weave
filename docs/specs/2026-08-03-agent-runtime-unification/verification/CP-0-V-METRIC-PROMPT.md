# CP-0 · V-METRIC — verifier prompt

*Committed when CP-0 opened, before the code existed. Hand the contents below to a fresh agent verbatim.*

---

You are verifying a checkpoint in the LoreWeave repository (`d:\Works\source\lore-weave`). **Your
subject is the instrument, never the feature.** You are not asked whether the new runtime is a good
idea. You are asked whether the numbers it will produce can be believed.

Your standing question, and it outranks everything else here:

> **Would this number look good even if the thing being measured were broken?**

## The claim you are testing

> CP-0 freezes a baseline and installs an instrument such that, later, *"the new runtime beats the old
> one"* is a **computable and falsifiable** statement rather than an impression.

Four baseline classes are asserted, and the whole run is scored against them:

| class | asserted baseline |
|---|---|
| carry-forward — a failure on a declaration that already succeeded in the same session | **61.8%** of failures (2,477 / 4,010) |
| identifier resolution, as a share of real (non-breaker) errors | **≈57%** |
| our own prose counted as a tool error | **65.7%** of failures |
| turns ending `interrupted` | to be frozen at CP-0 |

## The four things you must decide

### 1 · Is each new field answerable — and unanswerable today?

For **each** field (`advertised_tools`, `withheld_tools`, `tool_calls[].source`, `latency_ms`, the
mandatory outcome, `runtime_variant`, declaration identity): name a question it answers, then **verify
against the live database that this question has no answer today**. A field that duplicates an existing
column is instrumentation debt, not instrumentation. Run the queries yourself and paste them.

### 2 · Is the baseline reproducible from the snapshot alone?

This is the item most likely to be quietly false. The A–E arm scripts were originally built against a
**live catalog** that has since changed, which means the published arm results **cannot be reproduced
today**. CP-0 claims to fix that by snapshotting into `contracts/`.

**Test it as an outsider would:** using only what is committed — the snapshot and the scripts, not the
running services — can the arms be re-run and do they reproduce? If re-running requires a live service
whose contents are not pinned, **the baseline is not frozen**, whatever the commit says. Say so.

### 3 · Is the sample contaminated, and are the four numbers recomputable?

Recompute all four baseline numbers yourself against `loreweave_chat` and state your denominators
explicitly. Known contamination in this corpus, which you must handle and report:

- a **37-session harness run** containing ~580 blank-argument calls;
- test-fixture content dominating naive content counts (one prior measurement of "duplicate books" was
  ~82 rows of fixtures such as `t` and `ATOM-EDIT F2 FIXTURE`);
- **one dogfooding user**, a shared dev database, and **three rows** in `message_feedback`.

For each of the four numbers report: the value you get, the denominator you used, whether it matches
the asserted figure, and **whether the population is the one the claim is about.** A denominator that
comes from what we built rather than from the source of truth always reads "done".

### 4 · What bound does the data actually support?

State, for the traffic rate this product really has (**~414 tool calls/week across the entire
product**), how long it takes to detect an improvement of the size being claimed. If the answer is
*"longer than the run"*, that is your most valuable finding and you must say it plainly.

Two arithmetic facts already established here, which you should check rather than accept:
`3/3` bounds a failure rate only at **≤63.2%** against a **54.2%** baseline, and **≤10% requires 29
consecutive successes**.

## The traps this project has already fallen into

Check each. They are not hypothetical; each is a recorded defect in this repository.

1. **Scoring on `ok=true`.** A tool here returns success while substituting a different object than the
   one requested. Does any CP-0 number rest, anywhere in its chain, on `ok=true` meaning success?
2. **A guard proven red over the wrong subject.** If a test demonstrates a check can fail, confirm it
   fails **over the field the claim is about**, not a neighbouring one.
3. **The self-derived denominator.** If a coverage or completeness percentage appears anywhere, trace
   its denominator to the source of truth. A total derived from what was built always reads 100%.
4. **The comparison that cannot be computed.** The run's stated comparison unit is the **declaration**,
   not the runtime — matched pairs of one declaration on the new runtime against the same capability in
   the frozen baseline. **Confirm that the recorded fields actually permit this join.** If they do not,
   no amount of accumulated traffic will answer the question, and this is a `FAIL` regardless of how
   complete the schema looks.

## Output

Write your verdict to `docs/specs/2026-08-03-agent-runtime-unification/verification/CP-0-v-metric.md`:

1. **Verdict**: `PASS` / `FAIL` / `CANNOT DETERMINE`, and separately for **each of the four decisions**.
2. **The falsifier** — *what you looked for that would have made this FAIL*. A `PASS` with no falsifier
   is recorded as `CANNOT DETERMINE`, which does not close the checkpoint.
3. **Every query you ran and its raw output.** Your verdict is worth exactly as much as its arithmetic
   is checkable.
4. **The bound table** — for each of the four classes: recomputed value, denominator, contamination
   handling, and the sample size needed to detect the claimed improvement.

You have one authority the other verifiers do not: **if you rule a number unsound, any PASS resting on
that number is void**, including one already given by another role. Use it if the evidence supports it.

Do not evaluate whether the architecture is a good design. Do not propose fixes.
