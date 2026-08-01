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
| **A5** two-stage (EDC) | 13,988 | 4,924 | 2.0 | 43.7 | 0 | **1** | 19.5 | 9.0 | 85.1% | 7.2% | 1.0% | 58.8% | 94.1% | 40.5% |
| **A7** EDC on citations | 9,663 | 5,266 | 2.0 | 46.0 | 0 | 0 | **23.2** | 12.5 | **92.7%** | **1.7%** | 0.4% | **77.1%** | 97.9% | 36.2% |
| A8 A7 + enumerated sweep | 11,687 | 9,061 | 2.0 | 74.5 | **5** | 1 | 24.0 | 13.5 | 92.9% | 1.7% | 0.0% | 74.5% | 100% | 35.0% |
| **A9** A8 + composed event names | 10,330 | 6,316 | 2.0 | 55.2 | 0 | 0 | **27.1** | **15.8** | 92.6% | 1.8% | 0.0% | 70.0% | 95.0% | **33.6%** |

⚠ **A7's row is green on every axis and it dropped an entire kind.** Read §6b before using it.
⚠ **A8 tried to fix that with a prompt and could not** — §6c, and the reason is structural.

Against A0:

| arm | input | output | yield | grounded |
|---|---|---|---|---|
| A0b (variance floor) | +0.0% | +5.8% | **−8.5%** | −0.8pp |
| **A1** | **−62.0%** | **−47.0%** | −12.4% | +0.0pp |
| A2 | −3.2% | +7.4% | −10.9% | −2.4pp |
| A3 | −61.9% | −47.7% | −12.9% | −2.4pp |
| **A4** | −61.6% | −46.7% | **−10.0%** | +1.7pp |
| **A5** | −38.1% | −20.4% | **−3.0%** | **+5.0pp** |
| **A7** | −57.3% | −14.9% | +15.4% ⚠ | **+12.6pp** |

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

## 6b. A7 — EDC that reads its own citations, and the axis that failed to catch it

A5's entire cost premium over A4 is that the chapter is sent **twice** — 13,988 − 8,688 = 5,300
tokens, almost exactly one chapter of classical Chinese. A7 asks whether stage 2 needs the chapter at
all: stage 1 returns a name **and a characterising quote**, and stage 2 is given only that list.

On the card it looks like a dominant win:

| | A0 | A4 | A5 | **A7** |
|---|---|---|---|---|
| input | 22,614 | 8,688 | 13,988 | **9,663 (−57.3%)** |
| entities/chapter | 20.1 | 18.1 | 19.5 | **23.2 (+15.4%)** |
| Q1 grounded | 80.1% | 81.8% | 85.1% | **92.7% (+12.6pp)** |
| Q2 unmatched | 9.5% | 9.4% | 7.2% | **1.7%** |
| Q4 strict | 59.3% | 67.5% | 58.8% | **77.1%** |
| chapters lost | 0 | 0 | 1 | **0** |

It is the only arm that *beats the baseline on yield*, its groundedness is 16× its axis floor, and its
strict typing is +17.8pp over A0 — the typing improvement EDC was supposed to deliver and A5 did not.
The mechanism is legible and slightly counter-intuitive: **giving the typing step less context made it
type better.** Stage 2 sees a name and one focused sentence instead of 5,300 characters of narrative.

**And then the kind mix:**

| arm | character | location | event | item | power | org | species | total |
|---|---|---|---|---|---|---|---|---|
| A0 | 79 | 40 | **34** | 19 | 5 | 19 | 5 | 201 |
| A4 | 91 | 43 | 24 | 15 | 3 | 1 | 4 | 181 |
| A5 | 95 | 48 | 11 | 18 | 0 | 12 | 11 | 195 |
| **A7** | **160** | 54 | **0** | **7** | 1 | 7 | 3 | **232** |

A7 extracted **zero events** where the baseline found 34, and **7 items** where it found 19. Its
"+15.4% yield" is **double the characters**, not broader coverage. A named-mention sweep finds names;
an event is not a name, so stage 1 never proposes one and stage 2 cannot recover it.

> **`BTG-A53`.** **Aggregate yield is not an anti-gaming axis — per-kind yield is.** `14` §3 put Q5 on
> the card precisely so that an arm could not get cheap by extracting less, and A7 defeated it by
> extracting *more of the easy kind*. The total went up 15% while an entire kind went to zero, and
> every axis on the card stayed green: groundedness rose, fabrication fell, typing improved, no
> chapters were lost. **The scorecard would have shipped this as the best arm.** It was caught by
> printing the distribution, which nothing required.
>
> This is the same shape as `BTG-A27` one level up — a kind error is invisible to the question that
> would have found it — and the same shape as the non-vacuity rule generally: a check whose subject
> cannot vary in the direction of the defect is not a check.

**Wiring the axis in found three more, immediately.** Once `kinds_zero` and the distribution were
printed unconditionally, the card flagged that **A2, A3 and A5 had each abandoned `power_system`**
— all three sat green on the aggregate card and none of them was noticed:

| arm | character | location | item | event | terminology | power_system | organization | species |
|---|---|---|---|---|---|---|---|---|
| A0 | 79 | 40 | 19 | 34 | **0** | 5 | 19 | 5 |
| A0b | 71 | 37 | 17 | 32 | **0** | 7 | 15 | 5 |
| A1 | 83 | 38 | 15 | 21 | **0** | 1 | 9 | 9 |
| A2 | 86 | 38 | 16 | 19 | **0** | **0** | 15 | 5 |
| A3 | 76 | 44 | 18 | 17 | **0** | **0** | 7 | 13 |
| A4 | 91 | 43 | 15 | 24 | **0** | 3 | 1 | 4 |
| A5 | 95 | 48 | 18 | 11 | **0** | **0** | 12 | 11 |
| A7 | 160 | 54 | 7 | **0** | **0** | 1 | 7 | 3 |

So the defect was **wider than the arm that exposed it**, which is the usual shape: the axis was
missing, so nobody could see any instance of it.

### The counts mislead for a delta arm — read `new/ch`, not `ents/ch`

A4's `organization` count is **1** against a baseline **19**, which looks like a 95% collapse. It is
not. A0's nineteen are **商 ten times and 西岐 eight times** — the same two entities re-extracted in
every chapter that mentions them, plus one misfiled palace and one clan. A4 emits 商 once because the
delta instruction told it to omit a known entity that adds nothing. **That is the arm working.**

> **`BTG-A54`.** **Total yield and *new*-entity yield say opposite things about a delta arm, and the
> fair one is `new/ch`.** A0 discovers 9.7 new entities per chapter and A4 discovers **9.5 — a 2.1%
> difference, inside the noise floor**, while their totals differ by 10.0%. So A4's apparent recall
> cost is almost entirely **suppressed repeats, not lost discoveries**, and the case for shipping it
> is stronger than §1's table suggests. By the same column A7 finds **12.5 new per chapter, +29% over
> the baseline** — its discovery gain is real even though its kind mix is broken.

The per-kind zero-check stays right regardless (an abandoned kind is a defect however you count), but
comparing raw per-kind *counts* between a delta arm and a non-delta arm conflates suppression with
coverage.

**Also caught by the same table:** `terminology` is **0 for every arm including the baseline**. The
kind is adopted, its 4 attributes are in the profile, it is in every prompt, and nothing has ever come
back under it. That is a pre-existing pipeline defect this POC did not cause and would not have found
without the distribution.

**Verdict on A7: promising, not shippable as-is.** It needs the sweep prompt to solicit events and
items explicitly — a prompt fix on a two-stage shape whose grounding and typing numbers are the best
measured. Re-run before adopting, and score per-kind.

**Grounding caveat.** A7 carries stage 1's quote through verbatim, so its 92.7% measures how faithfully
the *sweep* quoted, not the typing step. The citation genuinely is grounded, but it is not the same
claim A0–A4's Q1 makes and the two should not be compared without saying so (§9).

## 6c. A8 — the prompt fix worked for two kinds, failed for the third, and the failure is structural

A8 is A7 with a sweep that enumerates every category and says of events, in capitals, that the
category is routinely missed and must not come back empty. It recovered two of the three:

| kind | A0 | A7 | **A8** |
|---|---|---|---|
| item | 19 | 7 | **20** ✓ |
| power_system | 5 | 1 | **4** ✓ |
| **event** | **34** | **0** | **2** ✗ |

Two attempts — implicit then explicit and emphatic — produced 0 and 2 against a baseline of 34. Look
at what the two sets actually contain:

```
A0  文王逃離朝歌 · 費仲與尤渾密謀 · 雷震子食仙杏變形 · 比干剖心 · 武吉打死王相 · 漁樵問答 …
A8  九龍宴 · 弒君
```

A0's events are **composed noun phrases** — *"King Wen flees Chaoge"*, *"Bigan cuts out his heart"*,
*"Leizhenzi eats the immortal apricot and transforms"*. None of them is a string that appears in the
chapter. A8's two are actual lexical items: 九龍宴 *the Nine Dragon Banquet*, 弒君 *regicide*.

> **`BTG-A55`.** **The `event` kind is not extraction — it is authoring, and a citation-constrained
> sweep structurally cannot do it.** A7/A8's stage 1 demands a name *exactly as written* plus a
> verbatim quote. An event like *"King Wen flees Chaoge"* is nowhere written as a phrase; the model
> must **compose a label** for a happening spread across paragraphs. The two events A8 did find are
> precisely the two that happen to be words. No prompt fixes this, because the constraint that makes
> EDC grounded (quote it verbatim) is the same constraint that forbids naming an event.
>
> Seven of the eight kinds are *find the name in the text*. One of them is *invent a label for
> something the text does*. They were never the same operation, and `03_two_jobs.md` is this
> distinction one level up — here it turns out to be living **inside** the extractor, unnoticed,
> because the schema lists all eight kinds side by side as though they were alike.

**This matters beyond cost.** Events are what a game most needs — a quest is an event with
preconditions — and this says the game tier cannot expect to *extract* them. It has to author them,
which is exactly what [`03`](03_two_jobs.md) and [`01`](01_the_missing_tier.md) argue the tier is for.
The extractor's 34 events were always a small authoring step wearing an extractor's costume.

**And A8's cost is bad.** Output **+46.4%** against the baseline, **5 of 10 chapters truncated**, one
lost entirely, and 74.5 s/chapter — *slower than the 3-call baseline*. Enumerating the categories made
stage 1 emit far more, and the truncations cluster in the entity-dense later chapters (24, 26, 28, 29,
30) where output hit 11.9k–15.4k tokens. A8 is not shippable and is not a tuning problem.

### A9 — the constraint was the blocker, not the enumeration, and one sentence proves it

A8 tested the *enumeration* and never tested the *constraint*. Re-read its sweep: it lists events in
capitals and then says to name each thing **"as the text names it, or with the exact phrase the text
uses for it"** — a verbatim rule, applied to the one category that by `BTG-A55` cannot satisfy it.

A9 changes exactly that, and nothing else: the rule is **split by category**. A name must be verbatim
for things that *have* names; for events it may be **composed**, while the evidence stays verbatim
either way — so grounding is untouched by construction.

| | A0 | A7 | A8 | **A9** |
|---|---|---|---|---|
| event | 34 | 0 | 2 | **8** |
| terminology | **0** | **0** | **0** | **6** |
| kinds at zero | 1 | 2 | 1 | **0** |
| entities/ch | 20.1 | 23.2 | 24.0 | **27.1** |
| **new**/ch | 9.7 | 12.5 | 13.5 | **15.8 (+63%)** |
| input | 22,614 | 9,663 | 11,687 | **10,330 (−54.3%)** |
| grounded | 80.1% | 92.7% | 92.9% | 92.6% |
| truncations / lost | 0 / 0 | 0 / 0 | 5 / 1 | **0 / 0** |

And the events it returns are unmistakably the composed kind the baseline produces:

```
九龍宴 · 鹿臺宴 · 燒毀軒轅墳狐狸 · 比干之死 · 夏招之死 · 聞太師上奏十條 ·
聞太師與費仲尤渾之爭 · 聞太師出征東海
```

> **`BTG-A56`.** **A9 is the only arm with no abandoned kind**, and the fix was a single sentence of
> permission rather than any new machinery. It is also the only arm that ever produced `terminology`
> — which was **0 for every other arm including the baseline**, a defect older than this POC. So the
> shipped extractor has been silently losing a whole kind for its entire life, and the cause was a
> prompt that only ever asked for names.
>
> Two honest caveats. Events reach **8 against a baseline of 34** — the permission recovers the
> *category*, not the *volume*. And `terminology`'s six are mostly `resolved`, i.e. they do occur
> verbatim, so that recovery is likelier a prompt-attention effect than the `BTG-A55` mechanism, on
> an n of 6.

**A9 supersedes A7 as the shape to wire.** It costs 7% more input and buys the kind coverage A7 was
disqualified for, plus 26% more new entities, with no truncations and no lost chapters.

## 7. A6 (GLiNER) — the second reader does not read this language

`12` §7 step 2 asked for exactly this measurement, and `12` §5 warned the honest answer might be no.
It is no, and not marginally.

`urchade/gliner_multi-v2.1` over the same 10 chapters: **191 spans, 19.1/chapter, 42 seconds total,
on CPU, zero tokens.** The throughput is superb — 4.2s per chapter against 31–66s for the LLM arms —
and the yield looks comparable to A1's 17.6. Both of those numbers are meaningless, because:

| | |
|---|---|
| found by **both** GLiNER and A4 | **3** |
| only the LLM | 177 |
| only the encoder | 188 |

Three. Looking at what it actually produced explains it:

* **182 of 191 spans mapped to `character`.** The type space collapsed almost entirely to "person".
* Its longest "person" spans are **whole clauses** — `宜生在馬上看那挑柴的好像猾民武吉` ("Yisheng,
  on horseback, saw that the firewood-carrier resembled the rogue Wu Ji") is a sentence, not a name.
  `堯崩` ("Yao died") is a verb phrase tagged as a person.
* Its shortest are **common nouns**: 劍 sword, 戟 halberd, 鞭 whip, 斧 axe as "weapon"; 父王 "royal
  father" and 將軍 "general" as persons.

> **`BTG-A52`.** **GLiNER has no span-boundary sense in classical Chinese, so it is not a second
> reader — it is a different task.** Unsegmented text with no spaces gives it nothing to anchor on,
> and it returns arbitrary substrings. The 3-entity overlap is not a scoring artifact to be tuned
> around; there is almost no shared subject to disagree *about*, and disagreement was the entire
> product (`12` §4②).
>
> `12` §5 said adopting it on faith would be a mistake because its published numbers are English
> benchmarks and 文言文 is unmeasured. That was the right call, and the measurement cost an afternoon
> and no tokens. **The negative result is the deliverable**: the "add a second reader" half of `12`'s
> recommendation is closed for this corpus, and `BTG-A43`'s service-shaped adoption cost never has to
> be paid.

What survives is the *idea*, not the tool. The three signals `10` §4 wanted still exist — the LLM, the
morphology lint at 96.9% precision, and now the KG's own typed edges — and two of those are free.

> ⚠ **§8's first recommendation is WITHDRAWN by [`16`](16_book_scale_ab.md).** At book scale on the
> real pipeline, `single_call_delta` loses **38.4% of entity coverage**, concentrated in the rare
> kinds (`terminology` −80%, `power_system` −68%, `species` −62%). This document's 2.1% recall figure
> was measured in a regime — 10 chapters, a frozen 50-entity context — where the defect could not
> appear, and all three of its yield axes reported green. Read `16` before acting on §8.

## 8. Recommendation

1. **Ship A4's shape as the default now.** −62% input, −47% output, 2× faster, no quality regression
   outside any axis floor, and — once read on `new/ch` rather than `ents/ch` (`BTG-A54`) — a recall
   cost of **2.1%, inside the noise floor**, not the 10% the totals suggest. It needs the raised
   output ceiling and a **retry on parse failure** (`BTG-A47`), because the blast radius of a bad
   parse is now a whole chapter.
2. **Wire A9 as `edc_cited`.** −54.3% input, **+63% new-entity discovery**, grounded 92.6%,
   fabrication 1.8%, **the only arm that abandons no kind**, no truncations, no lost chapters. It
   supersedes A7 (which dropped `event`) and A8 (which truncated half the chapters); the difference
   from both is one sentence of permission, not new machinery (`BTG-A56`). Superseded advice, kept
   because it was wrong in an instructive way: `14` and an earlier draft of this section said to take
   `event` *out* of the EDC shape and give it its own path. That was the right diagnosis
   (`BTG-A55` — an event must be *labelled*, not quoted) and the wrong remedy: the constraint could
   simply be relaxed for that category, and A8 never tested that because it kept the verbatim rule
   while adding the enumeration.
3. **Per-kind yield is now on the card** (`kinds_zero` + the distribution, printed unconditionally).
   Wiring it in immediately surfaced three more zeroed kinds nobody had seen. Keep it.
4. **Investigate `terminology` = 0 across every arm including the baseline** — a pre-existing defect
   the distribution surfaced, unrelated to any arm. Given `BTG-A55`, check first whether it is the
   same failure: is a "term" nameable in the text, or does it also have to be composed?
5. **Build re-decide-on-merge** (`BTG-A49`). This is the real kind fix and it is not a prompt change.
   Today a first-chapter mistake is permanent; the model already knows better by chapter 40 and has no
   way to say so. Surface the disagreement as a conflict rather than resolving it oldest-wins.
6. **Do not build lever ①** (split the pair). `BTG-A48` — the pairs are 17.6%, in line with the
   published base rate, and the misfiles outnumber them 3.6:1.
7. **Re-baseline every kind-quality claim** once (5) exists. Until then, `09`'s 64% and this
   document's Q4 describe the store, not the extractor, and should not be quoted as model accuracy.
8. **Do not adopt GLiNER** (`BTG-A52`). The second-reader slot is better filled by the morphology
   lint (free, 96.9% precision, already written) plus the KG's typed edges once they exist.

## 9. Honest limits

* **10 chapters, one book, one model, one setting.** The variance floor (`BTG-A46`) is measured from
  a single repeat; two runs establish that differences below ~8.5% are noise, not that differences
  above it are real.
* **Q4's matched subset is 40–54 entities per arm over 25 distinct names**, and it is biased toward
  recurring entities — which is exactly why `both` is 39% of it by occurrence but 12% by distinct
  name. The strict/lenient gap is almost entirely the schema's inability to say "both", not error.
* **The answer key was labelled by the agent**, at the PO's explicit instruction, not by the PO. The
  criteria are recorded in the labelling script and the key is small enough to audit.
* **Q1 and Q2 measure the EVIDENCE QUOTE, not the attribute values.** An entity whose quote is a
  perfect verbatim citation but whose `description`, `affiliation` and `role` are invented scores
  100% grounded. Nothing on this card detects a fabricated *attribute* — and attributes are 59 of the
  ~62 fields an entity carries. The groundedness axis is real and deterministic, and it is also much
  narrower than "is this entity true". Labelling the answer key surfaced three attribute defects by
  eye that no axis caught: a throne hall described as "an organization with members", an island whose
  description is an empty `members/leader/headquarters` template, and a palace described as the
  residence of **楊貴妃** — a *Tang* figure hallucinated into a novel about the Shang.
* **A two-stage arm inherits its grounding from stage 1.** Where stage 2 carries stage 1's quote
  through verbatim, Q1 measures how faithfully the *sweep* quoted, not how faithfully the typing step
  did. That is not cheating — the citation genuinely is grounded — but it is a different claim from
  the one A0–A4's Q1 makes, and the two should not be compared without saying so.
* **No arm was scored against the *live* pipeline end-to-end.** The harness reproduces the worker's
  prompts and parser exactly and A0 matches the shipped per-chapter cost, but writeback, dedup and
  merge are out of scope — which is precisely where `BTG-A49` lives.
