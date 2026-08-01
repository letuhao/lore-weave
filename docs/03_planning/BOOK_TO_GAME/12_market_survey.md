# 12 — Is there a library for this? A 2026 survey, read for QUALITY

The PO's constraint is explicit: *the current pipeline costs a lot of effort and is slow — but slowness
is not the concern, **quality is**.* So this survey is read for the things that decide quality —
ontology governance, entity resolution, type control, and whether anyone publishes an accuracy number
— not for throughput or ergonomics.

---

## 1. The finding that decides most of it

> **A 2026 market review of KG-from-documents tools ends with this line: "No tools report accuracy
> benchmarks, language support details, or long-document handling specifications."**

> **`BTG-A34`.** **The frameworks cannot be chosen on quality grounds, because none of them publish
> quality.** Every comparison available is about ontology auto-generation, incremental updates, and
> which graph databases are supported — architecture, not accuracy. A team that picks one *for
> quality* is picking on vibes, and would then have to measure it themselves, which is the work they
> were trying to avoid.

## 2. What is actually on the market

**Orchestration frameworks — build a KG from documents:**

| tool | what it is for | ontology | entity resolution | notes |
|---|---|---|---|---|
| **Cognee** | ECL (Extract–Cognify–Load) | **auto-generated and continuously updating**, Pydantic-defined | **cross-document dedup in the Cognify stage** | closest in intent to what we need; young, quality "depends on LLM choice" |
| **GraphRAG** (Microsoft) | community summaries for global questions over a static corpus | fixed | clustering, not resolution | expensive indexing, an LLM call per chunk, slow on real corpora |
| **LightRAG** | GraphRAG's cost answer | fixed | limited | ~10× token reduction, dual-level retrieval |
| **Graphiti** (Zep) | **bi-temporal** graph memory — every edge carries a validity interval | limited, episodic | out of scope by design | explicitly **not** for bulk document ingestion |
| **LlamaIndex** `PropertyGraphIndex` | general RAG with a graph module | manual | custom | mature, graph is secondary |
| **LangChain** `LLMGraphTransformer` | extraction utility | via prompt | entirely custom | experimental module; "quality sensitive to prompt design" |
| **neo4j-graphrag** | RDF-ontology-guided extraction | RDF | — | the schema-based end of the axis |

**Extraction models — where quality actually lives:**

* **GLiNER** — an *encoder* (not an LLM) for zero-shot NER, given the type labels at inference.
  Reported to **outperform ChatGPT and fine-tuned LLMs in zero-shot NER**, at ~0.3B parameters.
* **GLiNER2** — schema-driven multi-task information extraction.
* **GLiREL** — the same idea for zero-shot relation extraction. **GLiNER-Relex** unifies both.
* Domain variants exist (BioMed, French document-level), which is evidence the fine-tune path works.

**Benchmarks — the thing nobody in category one uses:**

* **Text2KGBench** — ontology-driven KG generation. Two datasets (Wikidata-TekGen: 10 ontologies /
  13,474 sentences; DBpedia-WebNLG: 19 / 4,860) and **seven metrics covering fact extraction,
  ontology conformance, and hallucination**. **Text2KGBench-LettrIA** is a 2025 refinement addressing
  its data-quality and ontological-consistency problems.
* **Text2KG @ ESWC 2026** — an active workshop, so this is a live field rather than a settled one.
* For the specific problem of `10`: SemEval-2007 T8, ReLocaR, WiMCor, ConMeC.

## 3. Reading it against what we have

Our pipeline already owns everything the frameworks sell:

| what a framework provides | we already have |
|---|---|
| chunking, jobs, workers, retries | `extraction_worker`, the job control plane |
| provider abstraction | `provider-registry` (and an invariant forbidding anything else) |
| storage, incremental updates | glossary EAV + `entity_alias_map` + merge journal |
| ontology definition | `book_kinds` / `book_genres`, per-book, adoptable |
| entity resolution | alias map, merge candidates, dedup-name-variants |
| temporal validity | `spoiler_window.resolve_before_order`, `before_chapter_id` |

> **`BTG-A35`.** **Adopting a framework would replace working infrastructure to gain infrastructure.**
> The quality problem measured in `09` is not orchestration — it is that *one call was asked to extract
> and to type at once*, and nothing disagreed with it afterwards. No framework in §2 fixes that; most
> have the same shape, and `LangChain`'s own listed weakness is that extraction quality is "sensitive
> to prompt design".

What the survey **does** offer is two things the pipeline genuinely lacks, and neither is a framework.

## 4. Take: a benchmark, and a second reader

**① Text2KGBench's metric set, as our own scoring protocol.** Its three axes are exactly our open
questions: fact extraction, **ontology conformance** (is the type legal and right — `09`'s 64%), and
**hallucination**. Adopting the metrics costs nothing and turns *"I read 55 names and about 41 looked
like places"* into a number that can be compared across runs and models. `BTG-A30` said any fix should
be scored the way the field scores it; this is that protocol.

**② GLiNER as a DISAGREEING reader, not a replacement.** An encoder that takes the type labels at
inference and is reported to beat zero-shot LLMs at exactly the task our LLM is failing — typing. It is
small enough to run on CPU beside the pipeline.

The value is not that it is better. It is that it is **independently wrong**:

> `09` and `10` both ended at the same place — *this needs a second source before it can be trusted*.
> An encoder disagreeing with a generative model about whether 終南山 is an organization is a
> **conflict**, and conflicts are the one thing this tier already knows what to do with
> (`BTG-A20`: surface, rank, let a human decide).

Two independent readers plus the deterministic morphology lint from `10` lever ③ gives **three** signals
on a question where we currently have one and no way to know when it is wrong.

**③ Cognee's "continuously updating ontology"** is worth stealing as an idea rather than a dependency:
our `book_kinds.description` is NULL, and an ontology that *learns its own discriminating definitions
from the corpus it is extracting* is a direct answer to `10` lever ④.

## 5. Do not take

* **Any framework, wholesale.** §3.
* **Their automation posture.** Every tool in §2 is built to run unattended; this tier exists because a
  human decides ([`04`](04_fidelity.md), `BTG-A33`).
* **GLiNER on faith.** Its published numbers are English benchmarks. Classical Chinese is unmeasured,
  and a multilingual encoder that has never seen 文言文 may be worse than the LLM it is auditing. That
  is a measurement, and it is cheap: the ~896 entities extracted so far are a ready-made test set.

## 6. What the market does NOT have

Stated so absence is not mistaken for oversight:

* **No accuracy numbers from any framework.** §1.
* **No classical-Chinese entity-typing model or benchmark.** ACE's Chinese guidelines exist; the models
  and evaluations do not.
* **Nothing for long-form fiction at book scale.** Every benchmark is sentence-level or news-domain.
  A 100-chapter novel where an entity accumulates across 40 chapters is nobody's evaluation setting.
* **No human-in-the-loop review surface** in any surveyed tool — not one lists it as a feature. The
  conflict-review channel this tier needs would be built from scratch anywhere.

## 7. The recommendation

**Do not adopt a framework. Adopt a benchmark and add a second reader.**

Concretely, and in cost order:

1. **Score what we already have.** 896 entities and rising; take Text2KGBench's conformance and
   hallucination axes and produce the first real number for `09`'s error rate — which is currently an
   eyeball over 55 names.
2. **Run GLiNER over the same entities** and measure agreement with the LLM's kinds. Cheap, CPU, and it
   answers whether a second reader is worth wiring in at all.
3. **Then** decide about lever ② (split extract-from-type, the EDC shape), because by then there will be
   a number to move rather than an intuition to satisfy.

The one thing to avoid is the tempting order: rebuilding the pipeline first and measuring afterwards.
`09` produced a 64% error estimate in an hour, for free, because the pipeline already ran. **The
cheapest quality work available is measuring the pipeline we have.**
