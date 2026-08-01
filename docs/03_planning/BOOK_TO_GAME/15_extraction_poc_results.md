# 15 — POC results: the cost is removable, and the kind error is not what anyone thought

Seven arms over the frozen slice from [`14`](14_extraction_poc.md) — chapters 21–30 of 封神演義, a
frozen known-entity snapshot, Gemma-4 26B-A4B QAT resolved by role, concurrency 1, no database
writes. The instrument was repaired first ([`13`](13_extraction_cost_and_quality.md) §5.2).

The cost result is large and clean. The quality result is a different finding from the one the POC
was designed to look for, and it invalidates the way this project has been measuring extraction
quality all along.

---

## 1. The card

Per chapter, 10 chapters per arm. `lost` = chapters that produced **zero** entities.

| arm | in | out | calls | s | trunc | lost | ents | new | Q1 grounded | Q2 unmatched | Q3 foreign | Q4 strict | Q4 lenient | Q6 dup |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **A0** baseline | 22,614 | 6,189 | 3.0 | 65.5 | 0 | 0 | 20.1 | 9.7 | 80.1% | 9.5% | 0.5% | 59.3% | 98.1% | 40.8% |
| **A0b** rerun | 22,614 | 6,548 | 3.0 | 66.1 | 1 | 0 | 18.4 | 9.2 | 79.3% | 12.0% | 1.1% | 61.7% | 100% | 37.5% |
| **A1** one call | **8,603** | **3,282** | 1.0 | **31.1** | 0 | 0 | 17.6 | 8.1 | 80.1% | 10.8% | 0.0% | 62.2% | 100% | 40.3% |
| **A2** reordered | 21,889 | 6,646 | 3.0 | 71.3 | 1 | 0 | 17.9 | 7.3 | 77.7% | 11.7% | 0.6% | 65.4% | 100% | 46.4% |
| **A3** one call + reorder | 8,610 | 3,235 | 1.0 | 30.5 | **1** | 0 | 17.5 | 8.1 | 77.7% | 14.9% | 0.6% | 63.0% | 100% | 40.6% |
| **A4** + delta-only | 8,688 | 3,301 | 1.0 | 31.2 | 0 | 0 | 18.1 | 9.5 | 81.8% | 9.4% | 0.0% | **67.5%** | 100% | **35.4%** |
| **A5** two-stage (EDC) | 13,988 | 4,924 | 2.0 | 43.7 | 0 | **1** | **19.5** | 9.0 | **85.1%** | **7.2%** | 1.0% | 58.8% | 94.1% | 40.5% |

Against A0:

| arm | input | output | yield | grounded |
|---|---|---|---|---|
| A0b (variance floor) | +0.0% | +5.8% | **−8.5%** | −0.8pp |
| **A1** | **−62.0%** | **−47.0%** | −12.4% | +0.0pp |
| A2 | −3.2% | +7.4% | −10.9% | −2.4pp |
| A3 | −61.9% | −47.7% | −12.9% | −2.4pp |
| **A4** | −61.6% | −46.7% | **−10.0%** | +1.7pp |
| **A5** | −38.1% | −20.4% | **−3.0%** | **+5.0pp** |

## 2. Read A0b first — it sets what counts as a result

A0 and A0b are the same arm run twice. They differ by **8.5% in yield**, 5.8% in output tokens, and
0.8pp in groundedness, and A0b lost a chapter to a truncation A0 did not hit.

**The floor is per-axis, and quoting one number for all of them is wrong.** A first draft of this
document said "the variance floor is ~8.5%, so every quality delta is noise" — that took the *yield*
floor and applied it to axes with much tighter repeatability. From A0 vs A0b:

| axis | A0 | A0b | floor |
|---|---|---|---|
| entities/chapter | 20.1 | 18.4 | **8.5%** |
| output tokens | 6,189 | 6,548 | 5.8% |
| Q6 duplication | 40.8% | 37.5% | 3.3pp |
| Q2 unmatched | 9.5% | 12.0% | 2.5pp |
| Q4 strict | 59.3% | 61.7% | 2.4pp |
| Q4 lenient | 98.1% | 100% | 1.9pp |
| **Q1 grounded** | 80.1% | 79.3% | **0.8pp** |
| input tokens | 22,614 | 22,614 | 0.0% |

> **`BTG-A46`.** **Yield is the noisiest axis and groundedness the quietest — by 10×.** So a 3%
> yield difference is nothing while a 3pp groundedness difference is real, and the same percentage
> means opposite things depending on the column. Reading this card requires the floor for the axis
> you are reading, not a single headline number.
>
> Applying it: A1's −12.4% yield is barely outside the floor (weak). A2's −2.4pp groundedness is 3×
> its floor (probably real, and it is a *regression*). **A5's +5.0pp groundedness is 6× its floor —
> the one unambiguous quality result on the card.** A4's +1.7pp is 2× — suggestive, not settled.

## 3. The cost result: −62% input, −47% output, 2× faster, no measurable quality loss

One call per chapter instead of three. The chapter stops being sent three times, the boilerplate and
the known-entity block stop being sent three times, and the per-batch schema disappears.

The quality axes move by less than the variance floor. Groundedness is **identical** (80.1% both).
Foreign-character drift goes to **zero**. Yield falls 12.4%, which is just outside the floor and is
the one thing worth watching.

`BTG-A45` already predicted A3 would add nothing over A1, from string prefixes alone; the live arms
confirm it (8,610 vs 8,603 input, quality within noise). **Reordering is the fallback for the case
where batching cannot be given up, not a stacking win.**

**A4 is the arm to ship.** Same cost as A1, and it is the *best* arm on three quality axes —
groundedness 81.8%, unmatched 9.4%, duplication 35.4%, all better than the baseline — while
recovering yield to −10.0%. Asking for a delta rather than a re-description did not cost recall.

### The cost this does buy, and it is not in the tokens

> **`BTG-A47`.** **One call makes a parse failure all-or-nothing.** A3 lost chapter 30 entirely to a
> single malformed JSON response — 0 entities. With three batches a bad parse costs a third of a
> chapter; with one call it costs the chapter. Across the run, parse failures hit every shape (A0b 2,
> A2 3, A3 1), so this is not a defect of the one-call arm — it is a **blast-radius** change that the
> token numbers hide and the per-chapter yield average smooths over. Shipping A1/A4 means pairing it
> with a retry, which the shipped worker already has a place for.

## 4. The quality finding — and it invalidates `09`, `10` and this document's own Q4

Q4 needed an answer key, so all 162 `location`/`organization` entities in the live glossary were
labelled by hand. Two things fell out, and the second is the important one.

### 4.1 `BTG-A28` is falsified

Of 91 wrongly-typed entities: **16 collapsed pairs (17.6%)** against **58 plain misfiles (63.7%)**,
with 17 that are neither (persons, battle formations, a divine ox filed as an organization).

> **`BTG-A48`.** The pair rate is **17.6%**, and `11` §1 reported the metonymy literature's measured
> base rate as **~19%**. A number from English news-domain shared tasks transferred, near-exactly, to
> a Ming-dynasty novel. `BTG-A31` said the literature made `BTG-A28` less likely; it was right, and
> the fix is `10` levers ④+② (contrastive definitions, derive-the-kind), **not** lever ① (split the
> pair).

The morphology lint (`10` lever ③) scores **96.9% precision, 74.8% recall** — an excellent flagger.
Two entries prove it must never *rewrite*: **下虛門** is a **sect** and **黃門** is a **clan**, both
carrying 門 while meaning nothing like "gate".

### 4.2 The kind is decided once, at first sight, and never revisited

On the card, every arm scores **Q4 lenient ≈ 100%** — on the entities the key covers, no arm confused
a location with an organization. But the same key says the *live glossary* gets 58 of them wrong.
Same model, same prompt, same book.

Twelve of the 25 distinct matched names are filed `organization` in the glossary and typed `location`
by **every arm in this run** — and the arms are right in 11 of 12. Among them: **終南山**, the
flagship example of `09` §3 and `10` §1.

The mechanism is in the writeback, and it is deliberate. `findEntityCrossKind` resolves a name to an
existing entity *regardless of kind* and returns **the matched entity's kind**, which the caller then
merges into — `mergeKindID = crossKindID`. It exists to kill a real duplicate-explosion bug (#38/#39)
and it does. But nothing in the extraction path ever *changes* a kind: the only route that writes
`kind_id` is `reassignEntityKind`, a human curation endpoint.

The falsifiable prediction is that recurrence buys no accuracy. It does worse than that:

| | kind correct |
|---|---|
| entity seen in **one** chapter | 52/78 = **66.7%** |
| entity seen in **many** chapters | 35/84 = **41.7%** |

> **`BTG-A49`.** **An entity's kind is fixed by the first chapter that mentions it and is immune to
> every later chapter.** More evidence does not improve it — accuracy is *lower* for entities the
> book returns to. So the extractor's per-call accuracy and the glossary's accuracy are different
> quantities, and **every kind-quality number this project has produced measured the wrong one**:
> `09`'s 64%, `10`'s 75% suffix rate, and this document's own Q4 43.8% over the key are all
> properties of an accumulated, path-dependent store, not of the model.
>
> This is `BTG-A29` with a mechanism attached. The extraction call does sacrifice kind assignment —
> but the damage is permanent because the first sacrifice is the one that sticks.

**This also relocates the fix.** A better prompt improves per-call typing, which is already ~100% on
this evidence. What is missing is any way for chapter 40 to correct what chapter 3 decided — a
re-decide-on-merge path, with the conflict surfaced rather than silently resolved oldest-wins. That
is buildable here, and it is a smaller change than the EDC split A5 tests.

**Caveat, stated plainly:** the recurrence table is observational and confounded — entities the book
returns to are also the big political ones, which differ in kind-difficulty from one-off caves. The
code path is the strong evidence; the table is consistent with it, not proof of it.

## 5. What did not move

* **Charset drift** (`13` §6) stayed negligible on every arm, 0.0–1.1%, and was zero on both one-call
  arms. Confirmed as a non-issue, not a lever.
* **Duplication** is high everywhere (35–46%) and did not separate the arms. It is dominated by the
  same recurring entities appearing in many chapters, which is expected in a per-chapter extraction
  with no writeback.
* **Cache ordering** cost nothing in quality (A2 within the variance floor of A0), which is the
  question the live A2 arm existed to answer. Its *benefit* is `BTG-A45`'s prefix arithmetic, not
  anything on this card.

## 6. A5 (EDC) — it worked, and not for the advertised reason

Sweep for named mentions, then type and enrich. `11` §3 recommended it on the strength of three
independent lines of work, and `10` lever ② proposed it as the fix for **kind assignment**.

It is the best arm on the card for **grounding** and the best cost arm for **recall**:

* **Q1 grounded 85.1%** — +5.0pp, **6× its axis floor**, the one unambiguous quality result here.
* **Q2 unmatched 7.2%** — the lowest fabrication rate measured, though only at its floor.
* **Yield −3.0%** — it retains recall where every other cost arm loses 10–13%.
* At **−38.1% input / −20.4% output**, so roughly *half* the saving of A1/A4, over 2 calls.

> **`BTG-A51`.** **EDC improved grounding and recall — not typing.** Its Q4 is the *only* score below
> 100% lenient (94.1%) and its strict score is the lowest of any arm (58.8%). The literature's case
> for two-stage extraction is specifically about classification (`11` §3, `10` lever ②), and on this
> corpus that is the one thing it did not deliver, while delivering two things nobody claimed for it.
>
> The mechanism is legible: stage 1 asks only *"what names are here, and quote them"*, so the model
> spends its attention on finding and citing rather than on filling 59 attributes at the same time —
> which is `BTG-A29`'s prediction, but the sacrificed faculty turns out to be **evidence quality**,
> not kind. Stage 2 then types from a list it did not have to discover, and types no better.

Read against `BTG-A49`, this reframes A5 entirely: per-call typing was already ~100% lenient, so
there was no typing headroom for EDC to win. **The kind problem was never in the call.**

**Honest note on the first A5 run.** It was **mis-parameterised, not measured**: stage 1 was capped
at 4,000 output tokens and truncated mid-array on three chapters, yielding zero mentions and an empty
chapter each time. That scores as "EDC extracts nothing" when it means "the sweep budget was too small
for classical Chinese". Raised to the 8,000 the batched arms get and re-run; the numbers above are the
clean run. The discarded run is recorded rather than deleted because its headline — grounded +6.4pp —
survived into the clean run at +5.0pp, so the defect cost coverage, not direction.

A5 also **lost a chapter** to a parse failure (`BTG-A47` again — it is a 2-call arm, so the blast
radius is half a chapter's worth of kinds but the whole chapter's stage-2 output).

The same class of defect was caught three times in this POC, and it is worth naming because all three
looked like results:

> **`BTG-A50`.** **A harness bug reports a plausible number, not an error.** The wrong third argument
> to `parse_and_validate_with_stats` produced *1 call, 7.6k input, 0 entities*. Reading `kind` where
> the parser writes `kind_code` produced *Q4 = 0.0% over 54 entities*. Reading `source_kind_code`,
> NULL for all 1,060 rows, produced *"this book has no organizations"*. None raised. Each was caught
> only because a figure existed to reproduce (`BTG-A44`) or because the number was too extreme to be
> real. A POC without a self-test arm would have shipped all three as findings.

## 7. Recommendation

**There are two winners and they are not the same arm.** A4 is the cost arm; A5 is the quality arm.
A5 costs **63% more input than A4** and buys **+3.3pp grounding, +7.7% yield** — and gives back A4's
Q4 advantage. That is a real trade and it is the PO's, not a dominance the card can settle.

1. **Ship A4's shape as the default.** −62% input, −47% output, 2× faster, and no quality
   *regression* outside any axis floor. It needs the raised output ceiling and a **retry on parse
   failure** (`BTG-A47`), because the blast radius of a bad parse is now a whole chapter.
   **Then re-run A5 against A4** rather than against A0 — a 2-call EDC built on the one-call shape is
   an arm this POC never ran, and on these numbers it is the most promising one left: it would carry
   A5's grounding and recall at something much closer to A4's cost.
2. **Build re-decide-on-merge** (`BTG-A49`). This is the real kind fix and it is not a prompt change.
   Today a first-chapter mistake is permanent; the model already knows better by chapter 40 and has no
   way to say so. Surface the disagreement as a conflict rather than resolving it oldest-wins.
3. **Do not build lever ①** (split the pair). `BTG-A48` — the pairs are 17.6%, in line with the
   published base rate, and the misfiles outnumber them 3.6:1.
4. **Re-baseline every kind-quality claim** once (2) exists. Until then, `09`'s 64% and this
   document's Q4 describe the store, not the extractor, and should not be quoted as model accuracy.
5. **A6 (GLiNER) is still open** and is the only arm that can test whether a second reader helps —
   noting `BTG-A43`, that adopting it means a `local-ner-service` behind a BYOK credential, not a
   library import.

## 8. Honest limits

* **10 chapters, one book, one model, one setting.** The variance floor (`BTG-A46`) is measured from
  a single repeat; two runs establish that differences below ~8.5% are noise, not that differences
  above it are real.
* **Q4's matched subset is 40–54 entities per arm over 25 distinct names**, and it is biased toward
  recurring entities — which is exactly why `both` is 39% of it by occurrence but 12% by distinct
  name. The strict/lenient gap is almost entirely the schema's inability to say "both", not error.
* **The answer key was labelled by the agent**, at the PO's explicit instruction, not by the PO. The
  criteria are recorded in the labelling script and the key is small enough to audit.
* **No arm was scored against the *live* pipeline end-to-end.** The harness reproduces the worker's
  prompts and parser exactly and A0 matches the shipped per-chapter cost, but writeback, dedup and
  merge are out of scope — which is precisely where `BTG-A49` lives.
