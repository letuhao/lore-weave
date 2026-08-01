# 16 — The book-scale A/B, and the recommendation it reverses

[`15`](15_extraction_poc_results.md) recommended shipping the one-call shape as the default, on a
10-chapter POC that measured its recall cost at **2.1%, inside the noise floor**. This ran the same
comparison at book scale, through the **real pipeline** — the shipped worker, writeback, dedup and
merge, not the harness.

The cost result got **better**. The coverage result is a reversal, and the POC could not have seen it.

---

## 1. Design

30 chapters of 封神演義, **interleaved**: `single_call_delta` takes the even `sort_order`s 58–86,
`batched` the odd 59–87. Fifteen each, no chapter shared.

Three deliberate choices, each answering a trap measured earlier:

* **Chapters 58+ only.** 1–57 already ran under `batched`, so the extraction cache would have served
  them at **zero tokens** while `single_call_delta` (a different cache key) paid full price. That is
  not a comparison; it is a cache measurement.
* **Interleaved, not split halves.** `BTG-A41` — whichever arm runs second inherits what the first
  wrote, so the same chapters cannot go to both. Alternating keeps both arms in one stretch of
  narrative.
* **The cheap arm runs first**, so the residual path-dependence (arm two starts from a slightly
  larger glossary) runs *against* the arm being promoted.

Chapter sizes came out within **4.5%** (18,589 vs 19,423 mean bytes), so content volume does not
explain anything below.

## 2. Cost — better than the POC

| | chapters | in/ch | out/ch | tok/ch | s/ch |
|---|---|---|---|---|---|
| `batched` | 15 | 30,687 | 9,773 | 40,460 | 96.5 |
| `single_call_delta` | 15 | **9,866** | **4,107** | **13,972** | **42.7** |
| | | **−67.9%** | **−58.0%** | **−65.5%** | **−55.8%** |

Extrapolated to one pass over the 100-chapter book: **4.05M tokens / 2.7 h → 1.40M / 1.2 h.**

The POC measured −62% input; the real pipeline gives −67.9%. The direction and magnitude hold.

## 3. Coverage — the reversal

Distinct entities linked to each arm's own chapters:

| kind | `batched` | `single_call_delta` | |
|---|---|---|---|
| character | 127 | 98 | −22.8% |
| location | 23 | 19 | −17.4% |
| item | 61 | 51 | −16.4% |
| event | 74 | 47 | −36.5% |
| **organization** | 35 | 17 | **−51.4%** |
| **species** | 68 | 26 | **−61.8%** |
| **power_system** | 22 | 7 | **−68.2%** |
| **terminology** | 30 | 6 | **−80.0%** |
| **total** | **440** | **271** | **−38.4%** |

> **`BTG-A57`.** **The one-call shape loses coverage on EVERY kind, and the loss scales with how rare
> the kind is.** −16% on the commonest, −80% on the rarest, −38.4% overall. One call carrying eight
> kinds spends its attention budget where the chapter is densest, and the long tail is what pays. So
> `MAX_KINDS_PER_BATCH = 3` was buying something nobody had named: not just protection from output
> truncation, but **attention per kind**. Removing it trades 38% of the glossary for 65% of the cost.
>
> **That is a decision, not a default.** `15` §8 recommended shipping this shape as the default; on
> this evidence that recommendation is **withdrawn**.

## 4. Why the POC missed it, and what the scorecard still lacks

The POC put yield on the card precisely so an arm could not get cheap by extracting less
(`14` §3), then measured it three ways and none of them caught this:

1. **Aggregate yield** said A4 was −10.0% — `BTG-A53`, the axis that cannot see a redistribution.
2. **New-entity yield** said −2.1%, inside the noise floor — `BTG-A54`. That axis was *right about
   what it measured* (A4 was suppressing repeats) and still missed this, because on 10 chapters with
   a 50-entity frozen context there was little to suppress.
3. **`kinds_zero`**, added after A7 dropped `event`, reports **0 for both arms here**. Nothing hit
   zero. Everything shrank.

> **`BTG-A58`.** **A zero-check is not a coverage check.** `kinds_zero` catches an abandoned kind and
> is blind to a kind that merely halves — which is the failure that actually happens at scale. The
> axis has to be the **per-kind ratio against a baseline**, and it has to be run at a scale where the
> known-entity context is saturated. Ten chapters with a frozen 50-entity snapshot is a regime in
> which the defect cannot appear.

The POC was not wrong about what it measured. It was measuring in a regime where the thing that
matters could not show up — which is the more expensive kind of mistake, because every axis was green.

## 5. What this does not separate

`single_call_delta` is two changes at once: **one call** and **delta-only output**. This A/B ran only
the combination, so it cannot say which one costs the coverage. The POC's per-kind table hints that
both contribute — A1 (one call, no delta) already fell to `organization` 9 against a baseline 19, and
A4 (with delta) fell further to 1 — but that is a 10-chapter signal on the axis this document has just
finished distrusting.

**The next run is `single_call` without the delta instruction, at this scale.** If the coverage
recovers, the delta instruction is the culprit and the one-call saving can be kept. If it does not,
the loss is intrinsic to packing eight kinds into one call and the shape is only usable with fewer
kinds per call — which is `batched` with a larger batch size, a knob that already exists.

## 5b. The attribution, measured

`single_call` was then run over the **same 15 even chapters** `single_call_delta` had used —
legal only because the cache key now separates the shapes (it did not, and that was its own
bug: `batched` batch 0 is three kinds and `single_call` batch 0 is eight, so they collided
and a strategy switch served the other shape's parse). Distinct entities linked to those
chapters, before and after:

| kind | `batched` (odd) | `delta` alone | `+single_call` |
|---|---|---|---|
| character | 127 | 98 | 101 |
| location | 23 | 19 | **23** |
| item | 61 | 51 | 55 |
| **event** | 74 | 47 | **71** |
| **terminology** | 30 | 6 | **16** |
| power_system | 22 | 7 | 7 |
| organization | 35 | 17 | 18 |
| species | 68 | 26 | 29 |
| **total** | **440** | **271 (−38.4%)** | **320 (−27.3%)** |

> **`BTG-A60`.** **The delta instruction accounts for about a third of the loss; the rest is
> intrinsic to the one-call shape.** Dropping it recovers **49 distinct entities** — almost
> all of them `event` (47→71) and `terminology` (6→16), the two kinds a "report only what is
> new" instruction suppresses hardest because they recur in paraphrase rather than by name.
> But the gap only closes from −38.4% to **−27.3%**. **You cannot buy the coverage back by
> removing the delta instruction**, which is what `16` §5 set out to test.
>
> That confirms `BTG-A57`'s mechanism rather than the prompt: eight kinds competing inside
> one response starve the long tail, and no wording fixes an attention budget. The shape
> that *does* fix it is the one that gives each kind a dedicated pass — `edc_cited`.

**Caveat, and it matters:** 320 is the **union** of what the two one-call runs found on
those chapters, not what `single_call` alone would find. `single_call` also ran second, from
a larger glossary. So −27.3% is the *best case* for the one-call family, not a measurement
of one arm — which only strengthens the conclusion, since even the union falls short.

## 5c. `edc_cited`, wired and measured live

Wired into the worker as a sweep pre-pass, then run over 5 chapters (88–92) never extracted
with this profile. Per chapter, against the two arms above:

| shape | in/ch | out/ch | entities/ch | vs `batched` |
|---|---|---|---|---|
| `batched` | 30,687 | 9,773 | **29.3** | — |
| `single_call_delta` | 9,866 | 4,107 | 18.1 | **−38%** coverage |
| `single_call` | 10,446 | 4,324 | — | union with delta −27% |
| **`edc_cited`** | **13,397** | 8,989 | **27.2** | **−7%** coverage at **−56%** input |

> **`BTG-A61`.** **The two-stage shape recovers almost all the coverage the one-call shapes
> lose, and keeps most of the saving.** −7% entities per chapter against −38% for
> `single_call_delta`, at −56% input rather than −68%. That is `BTG-A57`'s mechanism
> answered directly: the tail starves when eight kinds compete inside one response, and a
> dedicated sweep pass is what stops them competing. The extra cost is one cheap call per
> window, and its output — a name and a quote — is small.

### ~~The `power_system` zero is a TYPING failure, not a coverage one~~ — RETRACTED 2026-08-02

<details>
<summary>The original claim, kept because the correction is the point</summary>

> `power_system` came back **ZERO**. The first draft of this section guessed that might be
> what chapters 88–92 contain. Reading them says otherwise — every one carries power-system
> material, 9 to 20 markers each:
>
> ```
> ch 88  變化 1 · 陣 6 · 符 2
> ch 89  遁 1 · 陣 7 · 符 1 · 丹 1 · 妖術 1
> ch 90  道術 1 · 變化 1 · 遁 2 · 陣 10 · 符 6
> ch 91  法寶 1 · 變化 1 · 遁 5 · 陣 4 · 玄功 1 · 妖術 1
> ch 92  道術 2 · 神通 2 · 變化 8 · 遁 1 · 陣 7
> ```

</details>

**The marker count was real and it measured the wrong thing.** 變化 (transformation), 陣
(formation), 符 (talisman), 遁 (escape-art), 神通 (a power used), 玄功 (an inner art) are
**individual arts**. Not one of them is a *tier*. A `power_system` — as the phrase is used in
this genre and as any model trained on it will read the token — is a **graded ladder** a
character climbs: 練氣 → 築基 → 金丹, or 大羅金仙 above 太乙金仙 above 天仙. Its mark is that
two of its members can be **compared**. Counting arts and calling them power-system material
assumes the answer.

Re-scanned for the ladder itself, across the same five chapters:

```
境界 0 · 修為 0 · 品階 0 · 等級 0 · 階級 0 · 層次 0 · 果位 0
金仙 0 · 大羅 0 · 天仙 0 · 太乙 0            道行 1 · 煉氣 1 (in 煉氣士, a role)
```

**封神演義 has no tier ladder.** It is a Ming-dynasty *shenmo* novel, not a xianxia
progression fantasy; its beings are ranked by title and lineage, never by a stated scheme
anyone advances through. So on chapters 88–92, `power_system = 0` is not a failure of any
kind — **it is the correct answer**, and reading it as a miss was an inference about a corpus
that had not been examined for the thing being claimed.

> **`BTG-A63`.** **A zero is only evidence once you have shown the thing could have been
> there.** Two full sections of this document treated `power_system: 0` as a defect to
> explain — first as a coverage gap, then as a typing failure — and produced a plausible
> mechanism for each. Neither was ever tested against the only question that mattered: *does
> the text contain a power system?* The marker count that seemed to settle it was a count of
> a **different concept wearing the same word**, which is the failure mode a well-chosen
> query is least likely to expose and most likely to dress up as evidence.

**What survives, re-labelled.** The material *was* extracted and it *did* land under the wrong
kinds — that finding stands, and it is now sharper, because the destination it should have had
did not exist:

| entity | filed as | actually |
|---|---|---|
| **崑崙之妙術** "the wondrous art of Kunlun" | `terminology` | **technique** |
| 五行方位 · 八卦方位 (five-phase / eight-trigram array positions) | `terminology` | a formation → **technique** |
| 山河社稷圖 | `terminology` | a magic artifact |
| **梅山七怪** "the Seven Monsters of Meishan" | `terminology` | a **group** → organization/species |
| **哮天犬** Yang Jian's divine hound | `item` | **species** |
| 雲霞獸 · 逍遙馬 (a divine beast, a horse) | `item` | species |
| **狼牙棒** a wolf-tooth club | `terminology` | **item** |

> **`BTG-A62`.** **`edc_cited` finds the material and misfiles it.** The −7% coverage figure
> stands — the entities are there — but the kind distribution is not trustworthy. The
> misfiling runs in both directions: arts and groups drift into `terminology`, creatures and
> treasures drift into `item`, and a plain weapon drifts *out* of `item`.
>
> This is the axis catching what the POC's Q4 could not. That answer key covered only
> `location`/`organization`, so a shape could score 70% strict on it while shuffling
> techniques, creatures and objects freely — which is exactly what happened. **A kind-typing
> claim is only as wide as the key behind it.**

> **`BTG-A64`.** **Some of the misfiling had nowhere else to go.** 崑崙之妙術 is an art. The
> catalogue's only home for an art was a kind named `power_system` — whose own description
> conceded the mismatch in as many words (*"the name says system but one art is enough"*).
> A model reading a name and a definition that disagree will follow the name, and the name
> said *ladder*. So the art went to `terminology`, which at least did not claim to be
> something it wasn't. **A misfile can be a missing-category error rather than a judgement
> error** — the same shape as `BTG-A28`'s place-vs-organization finding, one level up: not
> "the model picked wrong", but "the right box did not exist."
>
> Fixed 2026-08-02: `technique` split out of `power_system` at the System tier (glossary
> migrations `0056`/`0057`), and `power_system` rewritten to mean the graded ladder its name
> always implied — including an explicit licence to return **none**, so a story without a
> ladder is not pressured into filling the kind with whatever is nearest.

### The split did NOT change the extraction, and the reason is structural

Re-run on chapters 88–89 with the corrected catalogue adopted through G5 sync: **zero
`technique`, zero `power_system`.** The split, on its own, changed nothing.

Reading the cached stage-1 output says why. The sweep cited **95 mentions** across the two
chapters, and exactly one art-like string among them (`三賢遠遁`). 縱地行之術, 陰符之術 and
崑崙之妙術 are all in that text and **none of them reached stage 2**. Stage 2 types what
stage 1 cites; it never sees the chapter. So no kind definition, however good, could have
filed them — the material was gone one call earlier.

> **`BTG-A65`.** **Under `edc_cited`, the ontology cannot affect RECALL — only TYPING.** The
> sweep is deliberately kind-blind (it is handed no kinds, no attributes, no profile; that is
> what makes it cheap, and what lets its cache survive a definition edit). The consequence is
> that adding a kind, redefining one, or writing a better description can change how a found
> thing is *labelled* and can change nothing at all about what is *found*. A user who adds a
> kind and re-extracts under this shape will see the ontology change and the results not, and
> will reasonably conclude the feature is broken.
>
> This cuts against `BTG-A61` (edc recovers coverage): it recovers coverage of the things its
> sweep is good at naming — people, places, groups — and is structurally blind to the rest.
> Combined with `BTG-A55` (it cannot name events, which have no name to quote), the shape's
> real profile is: **excellent on named nouns, blind by construction on everything else.**
>
> The batched shape does not have this property — every kind gets its own call against the
> chapter text, so a new kind is a new chance to find something. That is a large part of what
> the 7.4× input cost is buying, and it was not priced in when the cheap shapes were ranked.

**So `edc_cited` is not promotable on this evidence.** Its discovery is excellent and its
typing is unverified outside two kinds. Before promoting it: re-run at 15 chapters, and
extend the answer key past `location`/`organization` — the material for that already exists
in the misfiles above.

**Also 5 chapters against 15**, on a different stretch of the book. Nothing here is
variance-controlled.

The live run also confirms the flow does what it claims: the worker logged
`sweep found 51 mention(s)` / `9 mention(s)` for the two windows, then a stage-2 call with
`in=5652` on a 6,063-character chapter — smaller than the chapter itself, because it read
the citation list rather than the text.

## 6. Where this leaves each shape

| shape | cost | coverage | verdict |
|---|---|---|---|
| `batched` | baseline | baseline | **remains the default** |
| `single_call` | −66% in (10,446/ch) | union with delta still **−27.3%** | the delta instruction is not the culprit (`BTG-A60`) |
| `single_call_delta` | **−65.5%** | **−38.4%** | not a default; a deliberate trade for a cheap first pass |
| **`edc_cited`** (A9) | **−56% in** | **−7% entities/ch** (5 chapters) | **wired and live.** Keeps the coverage and most of the saving — but MISFILES kinds (`BTG-A62`): `power_system` read zero because its material went to `terminology` and `item`. Not promotable until typing is checked against a wider key. |

A9 is the interesting one against this result: at POC scale it was the only shape that *increased*
coverage on every axis while cutting cost, and its two-stage sweep gives each kind a dedicated pass at
the chapter rather than making them compete inside one response — which is exactly the mechanism
`BTG-A57` says the one-call shape lacks. It is also still unwired.

## 7. A defect found on the way

Building the per-kind attribution required mapping entities to the chapters each arm processed, and
`chapter_entity_links.chapter_index` turned out not to mean what its consumer thinks.

The worker sets `chapter_index=idx`, the index **within the job's chapter list**, and says so in a
comment. glossary-service's `known-entities` endpoint documents `before_chapter_index` as *"only count
links strictly before this chapter"* — a position in the **book** — and windows on it.

Measured on this book: **index 0 maps to 6 different chapters, indices 1–14 to 3 each**, and 87
distinct chapters carry links whose index never exceeds 56.

> **`BTG-A59`.** **The producer writes a job-relative ordinal; the consumer reads it as a book
> position.** Any book extracted in more than one job — a resume, an incremental pass, this A/B —
> gets colliding indices, so `before_chapter_index` windowing and anything else keyed on chapter order
> (spoiler windows, timeline cutoffs) is reading a number that does not mean what it says. Existing
> data is already affected; a fix needs the chapter's real `sort_order` at write time **and** a
> backfill. Not fixed here — recorded with its evidence.

## 8. Honest limits

* **15 chapters per arm, one book, one model.** The cost delta (−65.5%) is far outside anything
  variance could produce; the coverage delta (−38.4%) is large but rests on a single pairing of
  interleaved chapter sets.
* **Different chapters.** Interleaving controls for narrative drift and chapter size matched within
  4.5%, but the two arms did not read the same words.
* **Path-dependence is mitigated, not eliminated.** The second arm began from a glossary the first had
  added 164 entities to. That biases *against* `single_call_delta`'s created-count only if the
  overlap is high; here `batched` still created more (248 vs 164) while running second, so the
  ordering does not explain the gap — if anything it understates it.
* **Coverage is counted, not judged.** More entities is not automatically better: `batched`'s extra
  169 include whatever noise it also produces, and nothing here scores their quality. The POC's
  grounding axes are per-entity rates and would not distinguish "found more real things" from "found
  more things".
