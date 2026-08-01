# 11 — Prior art: the industry solved most of this, under other names

Searched while the 100-chapter extraction ran. The short answer is **yes, and for twenty years** — the
place/organization problem has a name, a shared task, labelled datasets, a public repo, and a
standard ontological answer. And someone has published a pipeline that is nearly this tier.

Reading it changes two things in this folder, and one of them is a hypothesis of mine getting *less*
likely rather than more.

---

## 1. The problem has a name: **metonymy resolution**

**SemEval-2007 Task 8** was literally *Metonymy Resolution*, and its two target classes were
**location and organization names** — the exact pair `09` and `10` are about.

| | |
|---|---|
| base rate | **15–20% of place mentions are metonymic** — measured, not estimated. The SemEval set is 167 metonymic against 721 literal (~19%). |
| SOTA 2007 | ~86% accuracy on location metonyms |
| since | a fine-tuned BERT beat the prior best by **5.1%** on SemEval, 12.2% on ReLocaR, 4.8% on WiMCor |
| now | LLM approaches, and the strongest reported is a **two-step CoT pipeline** (`Llama-70B-CoT-2S`) |
| datasets | SemEval-2007 T8 · ReLocaR · WiMCor · ConMeC (common nouns, 2025) |
| repo | [`milangritta/Minimalist-Location-Metonymy-Resolution`](https://github.com/milangritta/Minimalist-Location-Metonymy-Resolution) — carries the SemEval data |

> **`BTG-A30`.** There is **labelled data and a scoring protocol** for this. Every judgement in
> `09` and `10` was eyeballed over 28 and then 55 names; the field has had a benchmark since 2007.
> Any fix we build should be scored the way the field scores it, or it is a preference with a
> percentage attached.

**And the base rate cuts against my own hypothesis.** `BTG-A28` argued the misfiles are *collapsed
pairs* — the cave that is also the school. If only ~19% of place mentions are metonymic in general
prose, then a **75%** place-suffix rate among our `organization` entities is far too high for metonymy
to be the main cause. A cultivation novel plausibly runs hotter than general prose — a master's cave
genuinely *is* the sect — but not four times hotter.

> **`BTG-A31`.** The literature makes `BTG-A28` **less** likely, not more. The plain reading — *the
> model simply typed them wrong, amplified by genre priors* — now has a prior behind it. The falsifier
> `10` §6 already stated (read all 41 flags and see whether they are pairs or misfiles) is no longer a
> formality; it is the thing that decides which fix to build, and the odds have moved against the more
> interesting answer.

## 2. The ontological answer already exists: **ACE's GPE**

ACE (Automatic Content Extraction, LDC) defines seven entity types — Person, Organization, Location,
Facility, Weapon, Vehicle, and **Geo-Political Entity**. GPE exists *precisely because* a country or
city is inherently both a place and a polity, and forcing a choice was unworkable.

Two mechanisms come with it:

* **Role per mention.** For a GPE mention the annotator selects the **Role** matching that mention's
  function — ORG, LOC, PER, or GPE. *"France changed the law"* is ORG-role; *"flew to France"* is
  LOC-role. **The entity has one type; each mention carries a role.**
* **Metonymy is annotated explicitly**, as *the name of one entity used to refer to another entity
  related to it*.

The guidelines are public: English EDT v4.2.6, **Chinese entities v5.5** (directly relevant to this
corpus), and a Phase-1 EDT + Metonymy guideline.

### How this revises `BTG-A28`

ACE says **one entity, many mention-roles**. `10` §4 lever ① says **two entities joined by
`SEAT_OF`**. Both are defensible, and the useful realisation is that they are **right at different
tiers**:

| tier | model | why |
|---|---|---|
| **glossary / extraction** | ACE's — one entity, roles per mention | do not invent an entity the text never separated; the cave and the school are one word in the source and splitting them is an interpretation, not a reading |
| **game concept** | the split — a place you can enter, a faction you can join | they have different affordances, different attributes, different gameplay verbs. A game needs both to exist as things |

> **`BTG-A32`.** The split belongs to the **design tier**, not the extraction tier — which is
> `03_two_jobs.md` again, arrived at from a completely different direction. Extraction records what the
> text says; **authoring decides that a game needs two objects here.** Pushing the split upstream would
> make the glossary assert a distinction the novel never made.

## 3. Modern LLM-KG practice already separates the jobs

* **EDC — Extract → Define → Canonicalize.** A three-stage pipeline: open extraction, then semantic
  definition, then schema normalisation. Typing is **not** done during extraction.
* **Schema-based vs schema-free** is the standing axis in the LLM-KG literature; ontology-guided
  extraction (e.g. `neo4j-graphrag` passing an RDF ontology to the model) is the schema-based end.
* The strongest metonymy result is **two-step**, not one-step.

Three independent lines of work arriving at *do not ask one call to extract and to type*. That is
`BTG-A29` with citations, and it strengthens `10`'s lever ② considerably — it is not an idea, it is
the field's default.

## 4. Someone has published almost exactly this tier

**G-KMS — *Game Knowledge Management System: Schema-Governed LLM Pipeline for Executable Narrative
Generation in RPGs*** (Systems, Feb 2026). Its five components:

```
knowledge grounding · schema-governed generation · normalization-based repair ·
ENGINE-ALIGNED KNOWLEDGE ADMISSION · application
```

Mapped onto what this repo already has:

| G-KMS | here |
|---|---|
| knowledge grounding | the corpus, glossary, KG |
| schema-governed generation | `contracts/pool/registry.json` + the planner kinds |
| normalization-based repair | the heal round |
| **engine-aligned knowledge admission** | **`item_l2.accept()`** — built yesterday, under a different name |
| application | the game tier |

They report *"high reliability in knowledge admission"* as a **headline metric**, alongside stable
procedural structure and alignment between system metrics and player-perceived quality. Their framing
of the problem is ours: LLM output that is *"structurally invalid or incompatible with real-time game
engines"*, and generative models lacking *"systematic mechanisms for managing executable game
knowledge rather than merely producing free-form narrative texts."*

Adjacent and also relevant:

* **From World-Gen to Quest-Line** (arXiv 2604.25482) — a **dependency-driven** prompt pipeline where
  earlier outputs constrain later stages. That is our closure/register idea, and it is **fully
  automated with no human in the loop**; its stated limits are long-range coherence, scaling, and
  *"validation of creative quality beyond automatic metrics"*.
* **RPGAgent** (CHI 2026) — multi-agent story-to-play.
* [`NousResearch/autonovel`](https://github.com/NousResearch/autonovel) — an autonomous novel pipeline
  whose components include **world bible templates, character registries and a canon database**.

> **`BTG-A33`.** The convergent vocabulary is a good sign and a warning. *Admission*, *schema-governed*,
> *normalization repair*, *dependency-driven* — the field arrived at the same joints, which suggests
> the joints are real. What none of the surveyed work carries is the thing this folder was opened for:
> **a human deciding how far from the source to sit, with the distance recorded**
> ([`04_fidelity.md`](04_fidelity.md)). The dependency pipeline is explicitly fully automated and lists
> creative-quality validation as unsolved. That is the gap, and it is where this tier should spend its
> originality rather than on re-deriving admission.

## 5. What to take, and what to build

**Take:**

1. **ACE's Chinese entity guidelines** as the source of contrastive kind definitions — `10` lever ④
   stops being *"write something better"* and becomes *"adopt a published, battle-tested wording"*.
2. **The metonymy benchmark and repo** as the way to score any typing fix — `BTG-A30`.
3. **EDC's three-stage shape** as the argument for `10` lever ②, now with citations.
4. **G-KMS's vocabulary** — "knowledge admission" is a better name than `accept()` and it connects this
   work to a literature.

**Do not take:** their automation. Every surveyed pipeline removes the human; this tier exists because
the fidelity decision is the human's ([`04`](04_fidelity.md) §1).

**Build ourselves** — the parts nobody surveyed has:

* the **fidelity charter** and its distance measurement
* the **sweep** as the spine, with a countable denominator ([`07`](07_lore_bible.md))
* **foreclosure detection** — *the source says this does not exist* — which no metonymy or KG work
  addresses, because a novel that denies a ranking is not a problem general NLP has

## 6. What was NOT found

Stated so the gaps are not mistaken for coverage:

* **No library for place/organization typing in classical Chinese fiction.** The metonymy datasets are
  English news. The Chinese ACE guidelines exist, but the models and benchmarks do not transfer without
  measurement.
* **No prior art on the collapsed-pair split.** ACE's answer is roles-per-mention; nobody surveyed
  materialises the second entity. If `BTG-A32` is right that this belongs to the design tier, that is
  unsurprising — no surveyed pipeline *has* a design tier.
* **No published number for extraction kind-accuracy on long-form fiction.** G-KMS reports admission
  reliability, not typing accuracy, so `09`'s error rate has nothing external to be compared against.
