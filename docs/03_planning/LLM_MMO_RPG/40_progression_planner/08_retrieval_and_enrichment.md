# 40.8 — Find and enrich: the two hard halves of a planner

> **Status:** DESIGN · **Date:** 2026-07-31 · **Prefix:** `ENR-`
> **Fills the two methods** [`40.7` §2](07_module_organisation.md) declared and did not specify:
> how an open decision **finds** its answer in the corpus, and what it proposes when the corpus is
> silent. **This is where POC-1's measured failure gets its fix.**

---

## 0 — The problem, named

> *"The hardest part of the planner is find-and-load, plus brainstorming what's missing. Find-and-load
> means using MCP search tools to find whether the book already says it, in order to propose. And if
> nothing is found at all because the book lacks it — **by what criteria** do we propose (enrichment)?
> And what it produces is what it must reason out from that pile of natural-language corpus."*

Three questions, and the middle one is the one nobody has answered anywhere in this track.

---

## 1 — `ENR-A1` — retrieve, do not stuff. This is POC-1's root cause, not a refinement.

POC-1 put `MAX_PROMPT_CHUNKS` of corpus into the prompt and asked the model to find and transcribe the
relevant passage. Four live runs, 3–5 of 11 answered, and the **dominant refusal was transcription**:
the model abridged the middle of long passages, reformatted lists, renumbered, and truncated its own
JSON. Eight fixes moved the count 4 → 4 → 3 → 5.

> **`ENR-A1`.** The planner **retrieves first and reads second.** The model never searches; it reads a
> handful of passages the retriever selected and answers about them. Prompt-stuffing is refused.

This changes the model's task from *"find it in 38 chunks and copy it out exactly"* to *"here are five
passages — what do they say?"*, and both halves shrink at once:

| | POC-1 (stuff) | with retrieval |
|---|---|---|
| model must locate the passage | yes, across the whole corpus | **no** — the retriever did |
| model must transcribe | a long span, exactly | a **4–15 char anchor** inside a short passage |
| failure mode | abridgement, renumbering, truncation | anchor not found → refused, cheaply |

The anchor mechanism built during POC-1 (`expand_to_sentence` + folded matching) is **kept whole**; it
just stops being asked to do a job it is bad at. Retrieval narrows the haystack; the anchor pins the
needle; the corpus's own bytes are what gets stored.

### 1.1 The tool this needs, and it does not exist yet

`knowledge-service` ships **`story_search`** as an MCP tool with exactly the right shape — *"hybrid
(default) = exact + semantic fused and reranked"*, `granularity: block` returning matching passages
with snippets. That is the proven primitive.

But it searches the **manuscript**, and the planner must search only **through the seal**
(`gamegen_corpus_seal`) — a citation to a chunk the seal does not attest is a citation to nothing, and
`run_interrogation`'s `_sealed_chunks` already enforces that on the read path.

> **Build `corpus_search` as an MCP tool on `lore-enrichment-service`**, modelled on `story_search`'s
> signature, scoped to a `seal_id`. Per the MCP-first invariant this is a tool-call through
> `ai-gateway`, on the domain service that owns the data — *"if the tool doesn't exist, create it."*
> Embeddings and rerank resolve through `provider-registry` as BYOK models; `bge-m3` and
> `bge-reranker-v2-m3` are already active on the test account, so the retrieve→rerank pipeline is
> buildable today.

---

## 2 — The probe: the query comes from the SLOT, not from the model

> **`ENR-A2`.** The search query is **derived from the slot shape and the open row**, by the planner
> kind. A model asked to invent its own query is a model choosing what evidence it will be judged on.

`PlannerKind` gains a fifth method:

```python
def probe(self, row: OpenDecision, slot: SlotShape, ctx: Context) -> list[Query]:
    """Derive the searches. Deterministic, inspectable, logged."""
```

Per kind, because the shapes want different queries:

| kind | what it searches for |
|---|---|
| `Enumeration` | the slot's concept + its known members as seeds (*"weapon · sword · blade · what else"*) |
| `Ladder` | **boundary probes** — the lowest and highest named members, plus ordering words. A ladder is found by its ends |
| `Profile` | the default set's member names, to see whether the source contradicts any |
| `Composite` | one query **per unresolved field**, seeded by the member being built |

**A multi-modal sweep, not one query.** One search angle does not find everything, and the four
available angles are blind to different things:

| angle | finds | blind to |
|---|---|---|
| **exact** (lexical) | the term the book actually uses | synonyms, paraphrase |
| **semantic** (embedding) | the concept under another name | rare literal tokens |
| **KG** (`knowledge-service` relations) | *"what does X relate to"* | anything not extracted |
| **CANON** (glossary/wiki + genre pack) | what a human already authored | anything unauthored |

All four run; results are fused and reranked; the union is what the model reads.

---

## 3 — `ENR-A3` — a `not_stated` answer carries its SEARCH as evidence

`PGN-A4` already says *"the book does not say"* is a **complete** answer **and it is accountable**.
Nothing yet made it accountable. This does:

> **`ENR-A3`.** A `not_stated` answer is **refused without a query log**: which queries ran, over which
> `seal_id`, in which modes, returning what. Absence of evidence is only evidence of absence if
> someone looked, and the record of looking **is** the evidence.

Without it, `not_stated` is unfalsifiable and the two failure modes are indistinguishable — *the book
is silent* and *we searched badly* produce the same row. Doc 39's worst finding was that **an
all-`not_stated` run passed all eight trust properties**; `ENR-A3` is the mechanism that makes such a
run inspectable rather than merely refused.

```
answer { shape: not_stated
         searched: [ {q:"品階",   mode:exact,    seal:…, hits:0},
                     {q:"treasure grade", mode:semantic, seal:…, hits:3, used:0, why:"off-topic"} ]
       }
```

---

## 4 — `ENR-A4` — enrichment is a ranked CRITERIA LADDER, never a free proposal

The PO's real question: *by what criteria do we propose when the book is silent?* Answer: **six rungs,
tried top-down, and the first applicable one produces the proposal AND labels it.**

| # | criterion | the proposal is justified by | audit obligation | provenance |
|---|---|---|---|---|
| 1 | **Derivation from a cited pattern** | the book stated a rule; this is its expansion | the rule + the span it came from | ⑤ DERIVED |
| 2 | **Structural necessity** | the slot's own shape forces it (`arity ≥ 1`; an ordered set with one member) | the constraint, named | ④ but auto-approvable |
| 3 | **Closure demand** | `PPL-A2`: this variable has no gate, so one must exist | the closure rule that fired | ④ |
| 4 | **Genre convention** | the genre has a strong prior the book did not need to state | **the genre pack entry** — §5 | ② CANON |
| 5 | **Intra-reality coherence** | another slot in *this* reality already answered analogously | the sibling decision | ④ |
| 6 | **Bare invention** | nothing above applies | **loud** — flagged, never batch-approved | ④ |

**Recording *which rung* is the point.** A reviewer facing twenty proposals can approve the
structurally-necessary ones in seconds and spend their attention on rung 6. A proposal that does not
name its rung is refused — *"the model suggested it"* is not a criterion.

**Rungs 1–3 are not really invention at all.** They are consequences of decisions already made, and
they should carry most of the volume. If rung 6 dominates a run, that is a **signal the source is
wrong for this reality**, not a prompt-tuning problem — and it is now a number you can read off the
run instead of a feeling.

---

## 5 — `ENR-A5` — the genre pack: the reusable half of enrichment

Rung 4 needs somewhere honest to come from. Two options, and only one is auditable:

| source of the genre prior | auditable? |
|---|---|
| the model's own knowledge | **no** — it is a proposal wearing a convention's clothes |
| **an authored genre pack** | **yes** — a record id and a version |

> **`ENR-A5`.** Genre convention enters through an **authored genre pack**, never through the model's
> latent knowledge. A pack is written once per genre and reused across every book in it, and it enters
> as **provenance ② CANON** with a record id — not as ④ PROPOSED.

This is the PO's *"a human authors a pile of wiki/glossary/KG"* moved one level up: **the expensive
human work is per-genre, not per-book.** Write *xianxia* once — nine sub-levels by convention, realm
ladders of 5–12, treasure grades usually 5–9, spirit stones as dual-purpose currency — and every
xianxia book after it starts with rung 4 already stocked.

It lives where authored SSOT lives: `glossary-service` (entities + wiki), scoped **System-tier**
(admin-authored, user-readable, cloned-not-edited per User Boundaries). A user may narrow a pack for
their book; they may not mutate the shared one.

**And it is a falsifiable claim about the product, not just a mechanism:** if genre packs work, the
second xianxia reality costs far less human time than the first. That is measurable, and it should be
measured.

---

## 6 — What the human actually does — and it is not "answer questions"

The loop's design assumes the human's job is answering. Watching POC-1 fail suggests the higher-value
action is different:

> **The human knows the source. The retriever does not.** Their most valuable single action is
> **re-querying** — *"look for 品階"* — which is ten seconds for them and impossible for the model,
> because the model does not know the book exists in those words.

So the gate must expose the **search**, not only the question. Three actions, ranked by leverage:

1. **re-query** — supply the term the retriever missed. Cheapest, highest value.
2. **answer directly** — provenance ① DECLARED. For decisions like the roster, this is *correct*, not a fallback (`PPL-A4`).
3. **approve / reject a proposal** — with the rung visible.

---

## 7 — What the reviewer sees

The gate's whole surface, and it is deliberately one screen per decision:

```
SLOT   item_grade  (Ladder · SHARED · arity 2..=16 · ordered)
ASK    How many grades of treasure does this reality distinguish, and what are they called?

SEARCHED  through seal 0191f2a0…
  exact    "品階"          → 0 hits
  exact    "階"            → 41 hits, 3 relevant
  semantic "treasure rank" → 5 hits, 2 relevant
  canon    genre:xianxia   → 1 entry

FOUND     ch7 §2  "…凡器、靈器、寶器、道器、仙器五等…"        ← anchor 五等, sentence expanded
PROPOSE   5 grades: 凡器 · 靈器 · 寶器 · 道器 · 仙器          [③ CITED]
          ordinals 1..5 assigned, monotonic                   [QTY-A5]

[ approve ]   [ re-query: ______ ]   [ answer directly ]   [ not applicable ]
```

Everything a reviewer needs to distrust the answer is on the screen: what was searched, what was
found, what was not, and which rung produced anything unfound.

---

## 8 — What the model is actually asked to reason about

The PO's third point — *what it produces is what it must reason out from that pile of natural language*
— with the bound `PGN-A5` already places on it:

| the model MAY reason to | the model may NEVER produce |
|---|---|
| **cardinality** — how many the passages imply | any **magnitude** |
| **order** — which comes before which | any rate, cost, threshold or price |
| **names** — the terms the book uses | a name the corpus does not contain, except at rung 4–6 and labelled |
| **which retrieved passages are relevant, and which are not** | its own search queries (`ENR-A2`) |

That fourth row is new and is worth stating: **judging relevance is real reasoning and it is safe** —
a wrong relevance judgement produces a refusal or a bad proposal that a human sees, never a silent
fabrication, because the citation still has to anchor into sealed bytes.

---

## 9 — Open

1. **Does a negative result need a recall check?** `ENR-A3` records that we looked. It does not prove
   we looked well. A cheap adversarial probe — re-run the query set with a paraphrase and compare — is
   possible; whether it is worth the tokens is unknown until measured.
2. **Who writes the first genre pack, and how big is it?** `ENR-A5` claims the second xianxia reality
   is much cheaper than the first. Unproven. The pack for one genre should be authored and *sized*
   before the claim is repeated.
3. **Rung 2 auto-approval.** Structural necessity is the one rung where a human gate may be pure
   friction. Tempting to auto-approve — and auto-approval is exactly how doc 39's policy file ended up
   authoring a manifest nobody reviewed. **Default to gating; revisit with data.**
4. **`corpus_search` vs `story_search` — one tool or two?** If the sealed corpus and the manuscript are
   the same bytes, a `seal_id` filter on `story_search` is cheaper than a second tool. Needs a look at
   whether `source_corpus_chunk` and the manuscript blocks are the same rows.
5. **What happens when retrieval finds a CONTRADICTION?** Two passages, two different grade lists. The
   current design has no verdict for it — and refusing is probably right, but "refuse and show both"
   needs a shape.
