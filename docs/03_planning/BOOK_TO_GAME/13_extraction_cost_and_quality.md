# 13 — What extraction actually costs, and how good it actually is

The PO's case for reopening the pipeline is an economic one, and it is concrete: **24 hours and
~50M tokens to extract and build a KG for 700 chapters** of a 4,000-chapter, 50MB book, at *medium*
glossary detail. A game needs higher detail across three or four layers of extraction and enrichment,
so the same book plausibly costs **5–10× that** — and at that point the cost stops being a line item
and starts being an argument against the whole approach.

`12` recommended measuring before rebuilding. This is that measurement. Everything below comes from
the pipeline as shipped: the live job's own token telemetry, the worker's own prompt builders, and the
provenance status the pipeline already computes and stores.

The 100-chapter extraction was **cancelled at 57/100** to free the stack for this work. The 872
entities it had already produced are the sample.

---

## 1. The instrumented baseline

Job `019fbc4f`, 封神演義（原著）, Gemma-4 26B-A4B QAT via LM Studio, 8 kinds / 59 attributes,
`reasoning_effort: none`, concurrency 4.

| | per chapter | 57 chapters | extrapolated to 4,000 |
|---|---|---|---|
| input tokens | **21,834** | 1,244,548 | 87.3M |
| output tokens | **6,835** | 389,585 | 27.3M |
| total | **28,669** | 1,634,133 | **114.7M** |
| LLM calls | **3** | 171 | 12,000 |

The mean chapter is 17,905 bytes ≈ 5,970 characters of classical Chinese. So the pipeline spends
**~28.7k tokens to read ~6k characters.**

The PO's 700-chapter figure works out to ~71k tokens/chapter — higher, on longer chapters with a
different kind set, but the same shape. Nothing below depends on which number you use.

## 2. Where the input goes — and 86% of it is not the book

The worker's own builders (`plan_kind_batches`, `build_extraction_prompt`, `build_system_prompt`,
`build_user_prompt`) were called with this book's real profile, real known-entity context, and a real
chapter, then the assembled prompts were measured. Chapter 31, 4,747 source characters, the 8 kinds
batched as the worker batches them:

| call | kinds | schema | known-ents | boilerplate | chapter text | total |
|---|---|---|---|---|---|---|
| 1 | character, location, item | 2,965 | 2,958 | 1,905 | 4,802 | 12,630 |
| 2 | event, terminology, power_system | 1,979 | 2,958 | 1,905 | 4,802 | 11,644 |
| 3 | organization, species | 1,377 | 2,958 | 1,905 | 4,802 | 11,042 |
| **all** | | **6,321** | **8,874** | **5,715** | **14,406** | **35,316** |
| | | 17.9% | 25.1% | 16.2% | 40.8% | chars |

> **`BTG-A36`.** **The pipeline sends 7.4 characters of prompt for every 1 character of source it
> reads.** The chapter text itself, sent once, is **13.4%** of the input. Everything else is schema,
> boilerplate, a known-entity list — and three copies of all of it, including three copies of the
> chapter.

The duplication is structural, not incidental. `plan_kind_batches` splits 8 kinds into 3 batches
because of `MAX_KINDS_PER_BATCH = 3`, and that cap exists for a real reason — a fixed bug where 7+
kinds in one call blew past `max_tokens` and the JSON came back truncated and unparseable. The cap
solved an **output** problem by tripling the **input**. That trade was never measured; this is the
first time its price has been on paper.

Collapsing the three calls into one costs **55% fewer input characters** immediately, with no change
to what is asked.

## 3. The prompt is ordered so that nothing can be cached

`SYSTEM_TEMPLATE` interleaves its parts like this:

```
[ boilerplate ] {dynamic_schema} [ boilerplate ] {known_entities_context} [ boilerplate ]
```

`{dynamic_schema}` is the one part that **changes on every call** (it is per-batch), and it sits near
the front. Prefix caching — the mechanism every provider and llama.cpp itself uses to make a repeated
preamble nearly free — matches on a *common prefix*. Putting the most variable section first means the
shared prefix ends after ~1,100 characters, and the ~4,863 characters per call that are genuinely
identical across all three calls sit downstream of the break, where no cache can reach them.

> **`BTG-A37`.** **The most-variable section is placed before the most-stable one, so ~10k characters
> per chapter that are byte-identical across calls are re-encoded every time.** This is not a tuning
> parameter; it is a template ordering. Static boilerplate → slow-changing known-entities → per-call
> schema → per-chapter text is the same prompt with the same content, and it is cacheable.

Combined with §2, the ceiling is worth stating plainly: with one call and a cache-ordered prompt, the
only part that must be freshly encoded per chapter is the chapter, and per-chapter input approaches
**~4,800 characters instead of 35,316**.

## 4. Output: 88% of entity writes are re-writes

Across the run, entity writes split roughly **336 created / 713 updated** — and the final redelivery
window reported 88% updates. An update costs the same output tokens as a creation: the model emits the
full record, every attribute, for an entity the glossary already holds.

The known-entity block is *supposed* to prevent this. It is 2,958 characters that say *"Previously
identified entities (use EXACT names below, do NOT create duplicates)"* — and the entities keep coming
back in full. So the block is paying input tokens **and** not buying the output saving it exists for.

It is also carrying noise. The list this book produced includes `人` — the common noun *person* — with
eight aliases (`凡夫`, `俗子`, `百姓`, `軍卒`, …) and a frequency of 48. That is not an entity; it is a
word. It occupies the context window of every call for the rest of the book.

## 5. Quality — the first deterministic number this project has had

`09` estimated a 64% kind-error rate on one kind by eyeballing 55 names, and `12` said the next step
was to score what exists. It turns out the pipeline **already computes a per-entity groundedness
check and stores it**: `extraction_provenance.validate_evidence` locates each model-supplied evidence
quote in the real chapter text and stamps `evidences.provenance_status`. Nobody had ever read it.

Over all 1,739 evidence rows for this book:

| provenance_status | n | % |
|---|---|---|
| resolved (found, unique location) | 956 | **55.0%** |
| unmatched (not found) | 776 | **44.6%** |
| ambiguous (found, several locations) | 7 | 0.4% |

**44.6% of evidence quotes cannot be found in the text they were quoted from.** Taken at face value
that is a catastrophic fabrication rate — and taken at face value it would be wrong.

### 5.1 Classifying the failures instead of counting them

Each of the 776 was re-tested against its real chapter with a set of deterministic checks — Unicode
normalisation, punctuation folding, ellipsis splitting, longest-contiguous-run:

| class | n | % of unmatched | avg quote len |
|---|---|---|---|
| punctuation / width variant only | 303 | **39.0%** | 19.3 |
| near-match, ≥70% contiguous | 155 | 20.0% | 21.9 |
| abridged with `...`, **every fragment present** | 147 | 18.9% | 29.6 |
| abridged, some fragments absent | 56 | 7.2% | 236.9 |
| partial only (6–28 char run survives) | 73 | 9.4% | ~18 |
| **NOT IN TEXT** | **42** | **5.4%** | 9.2 |

> **`BTG-A38`.** **The fully-absent rate is 42/1,739 = 2.4%, not 44.6%. The pipeline's own quality
> instrument overstates the defect by 18.5×** — because it asks for an exact substring, and a model
> that renders `──` as `——`, appends a full stop, or abridges a long quotation with `...` has told the
> truth in a shape the matcher cannot accept.
>
> 39% of the failures are a **punctuation table**. Another 19% are an **ellipsis split**. Both are free.

Two numbers, and they are not the same thing. **2.4%** is the *fully absent* floor — quotes with no
meaningful run in the chapter at all. **9.8%** (§5.2) is *not fully grounded*, which also counts the
partial matches and the abridgements with a missing fragment. The floor is the fabrication estimate;
the 9.8% is what the repaired instrument reports as unverified. Quoting the first where the second
belongs would understate the problem, which is the mirror of the mistake this section is about.

That matters far beyond the number. This validator is the instrument the whole POC is about to be
measured with, and an instrument that mislabels four out of every ten *good* quotes as defects cannot
distinguish one pipeline arm from another. **Fixing the matcher is a prerequisite for measuring
anything, not an improvement to be scheduled.**

The 42 genuine failures are also informative: they average **9.2 characters**, far shorter than the
corpus mean. One reads `弟子乃金庭山玉屋洞玉屋洞玉鼎真人門下弟子` — with `玉屋洞` emitted twice. These
look like short generative artifacts, not invented claims.

### 5.2 The repair, and what it did to the corpus

`validate_evidence` was extended with a punctuation/width fold (mapped back to real offsets, so it
still yields a *verifiable* span), an ellipsis-fragment path, and a near-match threshold. Two new
statuses carry the grounded-but-unlocatable cases; both persist with **NULL offsets**, because no
single span equals an abridged quote and claiming one would manufacture exactly the confidently-wrong
citation the module exists to prevent.

All 1,739 stored rows were then re-validated against their real chapters, through the shipped
function:

| status | before | after |
|---|---|---|
| resolved | 956 · 55.0% | **1,260 · 72.5%** |
| abridged | — | 137 · 7.9% |
| partial | — | 164 · 9.4% |
| ambiguous | 7 · 0.4% | 7 · 0.4% |
| **unmatched** | **776 · 44.6%** | **171 · 9.8%** |

Three properties make this a repair rather than a loosening, and each was checked rather than assumed:

* **Strictly monotone.** Every single reclassification is `unmatched → {resolved, partial, abridged}`.
  Nothing left `resolved`, and `ambiguous` did not move by one row — the fold did not swallow the
  repeated-phrase case it would have been easiest to swallow.
* **No fabricated citations.** Of the rows that gained an offset, **zero** have a span that fails to
  contain their quote.
* **Two independent implementations agree exactly.** The offline classifier in §5.1 and the shipped
  validator, written separately, both leave **171** rows unmatched — 56 abridgements with a genuinely
  missing fragment, ~73 partials below threshold, and the 42.

> **`BTG-A42`.** The instrument now reports **9.8% not-grounded against a 2.4% fully-absent floor**,
> where it previously reported 44.6% against the same floor. The signal-to-noise ratio for the POC went
> from 18.5:1 noise to **4:1 signal**. The tolerance was bite-tested three ways — the Go enum gate, the
> near-match threshold, and the fragment-ordering check — and each break turned the suite red, which is
> the only evidence that any of them is a check at all.

## 6. Character fidelity — measured, and small

The prompt says *"Extract names EXACTLY as written in the source text"*, and one failing quote read
`哪吒顷刻来到西岐，落了風火轮` — `顷`/`来`/`轮` are **Simplified** forms in a Traditional-Chinese
source. That is a silent rewrite, and it is detectable without any conversion table: build the
character set of the whole book (4,204 distinct characters over 100 chapters) and find quote characters
outside it.

| | with an out-of-corpus character |
|---|---|
| evidence quotes | 16 / 1,739 — **0.9%** |
| entity names | 8 / 872 — **0.9%** |
| …of `resolved` quotes | 0 / 956 — **0.0%** |
| …of `unmatched` quotes | 16 / 776 — 2.1% |

> **`BTG-A39`.** Character drift is **real but rare** (0.9%), and it is **entirely confined to quotes
> that already failed** — zero `resolved` quotes carry a foreign character. It is a marker of a bad
> extraction, not an independent defect class, and it is not a cost driver. Recorded so it is not
> re-litigated: the tell was vivid and the incidence is negligible.

The foreign characters themselves are worth one line: Latin letters, Simplified forms (`问 轮 顷`), and
— in a Ming novel — Korean hangul (`문 은 이 질`). The model occasionally leaves the language.

## 7. What this changes

1. **The cost problem is an input-shape problem, not a model problem.** 86% of every input token is
   overhead or duplication (`BTG-A36`), and the largest single fix is a template reordering plus a
   batching decision (`BTG-A37`). Neither requires a better model, a different framework, or more
   money — which is consistent with `12`'s finding that no framework sells accuracy.
2. **The quality instrument must be repaired before any arm is scored** (`BTG-A38`). This is the
   non-vacuity rule applied to a measurement: a check that fires on 44.6% of a corpus when the real
   rate is 2.4% cannot detect an improvement, because its noise floor is 18× the signal.
3. **Groundedness is now measurable deterministically, per entity, at zero marginal cost.** That is the
   scoring protocol `12` §7 went looking for in Text2KGBench — and it is stronger than adopting one,
   because it runs on our own corpus with no answer key to author.
4. **Kind accuracy still has no deterministic check.** `09`'s 64% remains an eyeball. Groundedness
   answers *"did the model make this up?"*; it does not answer *"is it the right kind?"*, which is
   `10`'s question and needs the second reader.

## 8. Honest limits

* **One book, one model, one setting.** 封神演義, Gemma-4 26B QAT, `reasoning_effort: none`. Classical
  Chinese is the hard case, so these are pessimistic on quality; whether a larger model changes the
  ratios is unmeasured.
* **§2 is one chapter.** The composition is structural (the batching and the template do not vary by
  chapter), but the exact percentages shift with chapter length — a longer chapter tilts toward text.
* **Characters, not tokens.** §2 measures characters, which is exact and tokenizer-independent; the
  token split will lean further toward the Chinese chapter text, since English boilerplate tokenises
  more cheaply. The *duplication* ratios are unaffected — three copies are three copies.
* **The 42 fabrication candidates were not read individually.** They are classified, not adjudicated.
* **`created/updated` counters reset** across the cancel redelivery, so §4's 88% is from the final
  window and 336/713 from the last clean read. The direction is not in doubt; the exact split is soft.
