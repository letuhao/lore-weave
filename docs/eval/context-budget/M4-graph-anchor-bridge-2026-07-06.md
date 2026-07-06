# M4 measurement — the M1a "passage→graph anchor bridge" gap

**Date:** 2026-07-06 · **Branch:** `feat/context-budget-law` · **Corpus:** Dracula
(project `019f2be0-d145-7691-8182-5e17cf87e2c0`, book `019eeb09`, owner = test account) ·
**Embedding:** bge-m3 local (1024-dim) · **Harness:** `scratchpad/m1a_gap.py` (in-container,
live Neo4j + provider-registry embed).

Gates the go/no-go on plan `docs/plans/2026-07-06-context-retrieval-improvements.md` **M1a**.

---

## Why this measurement (the reframed question)

Reading the code overturned the plan's premise. The plan said "retrieval never traverses the
graph" — but that is true only for the **passage** selector (`passages.py`). The **facts** selector
already traverses:
- `select_l2_facts` runs **1-hop `find_relations_for_entity` every turn** (`facts.py:189`),
- **2-hop `find_relations_2hop` on relational intent** (`facts.py:211`),
- plus a **widened 2-hop retry on an empty 1-hop miss** (`full.py:733`, P4/R-T4-06).

So "add graph expansion" as framed would **duplicate facts.py**. The genuine residual is narrower:
graph expansion is anchored **only on `intent_obj.entities`** — the entities the intent classifier
pulls from the *message text*. It is **not** anchored on entities surfaced by semantic passage
retrieval. The real M1a, if justified, is a **passage→graph anchor bridge**.

**Measured metric (coverage-gap, needs no golden answers):** per query, the set of project entities
that (a) appear in the top-K retrieved passages, (b) are **not** already in the facts-anchor set, and
(c) **carry ≥1 graph relation**. That set is exactly what the bridge would newly graph-expand. If it
is usually empty, M1a is redundant; if frequently non-empty, M1a has value.

12 queries in 3 classes: `named` (message names the entity), `relational` (2 entities + relation
keyword), `implicit` (natural question naming no proper entity — where the answer entities must
surface via passages).

---

## Result

```json
{
  "queries": 12,
  "queries_with_bridge_gap": 12,            // 100% — every query
  "avg_bridge_entities_with_relations": 11.83,
  "queries_with_proper_noun_bridge_gap": 12, // 100% after removing anaphoric "the X" noise
  "avg_proper_noun_bridge_entities": 9.33,
  "queries_empty_anchor": 6,                 // all 6 `implicit` queries
  "queries_empty_anchor_but_bridge_would_help": 6
}
```

**Two decisive findings:**

1. **100% of queries** have proper-noun, relation-bearing entities surfaced by passages that facts.py
   never expands — **avg 9.33/query**. Even on `named` queries: "Tell me about Count Dracula" anchors
   only *Dracula*, but passages surface *Mina, Whitby, Transylvania, Szgany, Bistritz…* (all with
   relations) that the 1-hop/2-hop walk from *Dracula* alone doesn't reach.

2. **Anchor starvation on natural queries — the stronger framing.** All **6/6 `implicit`** queries
   ("What happened at the castle that night?", "Who did the narrator meet at the inn?") produce an
   **empty anchor set** — the classifier extracts no proper entity — so **facts.py contributes ZERO
   graph facts today**, even though the retrieved passages richly name *Count Dracula, Jonathan
   Harker, Mina, Mr. Hawkins, Borgo Pass, Golden Krone Hotel*, every one relation-bearing. For this
   whole query class the L2 graph-fact layer is dark purely because anchoring depends on the
   message-text classifier.

Full per-query rows: `scratchpad/m1a_result.txt` (543 lines).

---

## Verdict: **conditional GO for M1a**, with an honest ceiling on what's proven

The coverage gap is real, large, and 100% consistent — the bridge would add relation-bearing context
on every query and **rescue the entire L2 fact layer from empty-anchor starvation on ~half of natural
queries**. That is a concrete, measured defect in the current pipeline, not a hypothetical.

**But three caveats bound the claim — do NOT overstate:**

1. **Coverage-gap ≠ answer-quality gain.** This proves the bridge *would surface more relation-bearing
   entities*; it does **not** prove those relations improve answer correctness. That needs a
   golden-answer, LLM-judged A/B — necessary next step before calling M1a a "win," not just "wired."
2. **One small book.** Dracula (64 entities / 110 relations / 116 passages) is the **only** registered
   knowledge_project in the dev DB with entities + relations + passages together. N=12. The signal is
   strong and consistent but single-corpus.
3. **Noise gate is mandatory in the build.** The raw gap includes anaphoric/generic entities ("the
   driver", "the castle", "the Pass"). A naïve bridge that expands *all* passage entities per turn
   would be noisy and could blow the grounding budget. The bridge **must** gate anchor quality (proper
   / salient entities via the existing salience score, a per-anchor degree cap, and a few-hundred-token
   total budget) — the same invariants the plan's resolution #4 already specified.

## Corpus blocker (records the real state, refutes plan resolution #5)

The plan assumed **万古神帝 (4233ch/308 entities)** as the eval corpus. **It is not usable:** that 308
count is **glossary-only** (glossary-service Postgres). In the KG (Neo4j), the two entity-rich graphs
(3172 and 1814 entities) have **zero passages** and are **not registered knowledge_projects** —
orphaned test/deleted data. No large book has the passages+relations KG a full A/B needs. Building
that corpus = running a large book through **full passage + relation extraction** — genuine unbuilt
work (the real `D-EVAL-BOOK`), *not* "unblocked by the summaries fix" (summaries ≠ passages/relations).

## Answer-quality A/B (added — the gain the coverage-gap could not prove)

Per the "build corpus first, prove answer-quality gain" decision, an LLM-judged A/B was run on the
Dracula corpus (harness `scratchpad/m1a_ab.py`): **15 golden multi-hop questions** from the live
relation graph — 10 "bridge-sensitive" (a character referenced by ROLE, e.g. "the solicitor", "the
master of the castle", so the classifier anchors nothing) + 5 "control" (entity named). Baseline vs
+bridge facts → grounded answer → 0/1/2 LLM-judge vs golden.

**This section went through a `/review-impl` pass that overturned the first result.** Three fixes
were required before the numbers were trustworthy:
1. **[HIGH] baseline must include the L3 passages.** Production Mode 3 renders `<passages>` **and**
   `<facts>` (full.py:397). The first A/B put passages in **neither** arm, so it measured
   *facts vs facts+bridge* — an artificially weak baseline. Fixed: passage text in **both** arms;
   the only arm-difference is the bridge's added relations (== the real production delta).
2. **[bias] reasoning-truncation asymmetrically penalized the bridge.** gemma emits
   `reasoning_content`; the bridge arm has more facts → more reasoning → likelier to truncate to
   empty → false "regression". Fixed: **exclude** any question where either arm truncated from the
   paired comparison (rather than scoring the truncation 0).
3. **[infra] no independent judge is reliably servable.** lm_studio thrashes ("Operation canceled"
   on model load) when a two-model config alternates per call, so answerer==judge (gemma-26b) is a
   documented caveat, not a choice.

**Final, most-rigorous run** (passages both arms · truncation-excluded · single model):

| Class | scored / total | mean base | mean +bridge | better / worse |
|---|---|---|---|---|
| Overall | 11 / 15 | 0.636 | **0.727** (+14%) | 1 / **0** |
| Bridge-sensitive | 7 / 10 | 0.286 | **0.429** (+50%) | 1 / **0** |
| Control / named | 4 / 5 | 1.25 | 1.25 (unchanged) | 0 / **0** |

**What is run-stable across every fair run: the bridge NEVER regresses a question** (0 worse in all
runs) and produces occasional clean wins where a graph relation beats the passage text — the stable
example: *"guidebooks the master of the castle kept"* → **"reads Bradshaw's Guide"** vs base "not
enough info". Earlier runs also won on the 2-hop *"the lawyer's employer → Exeter"* (Harker→Hawkins→
Exeter) and *"works for → Mr. Hawkins"*.

**What is NOT stable — honest deflation of the first headline:** the *magnitude* and *which* questions
win vary run-to-run (+14% to +36% overall; 1–3 wins). Causes: (a) N=15 on one small book with a local
answerer; (b) the answer model often can't resolve a role-phrase ("the solicitor") to its entity even
with the fact present; (c) a harness flaw — `bridge_anchor_ids[:6]` caps an **unordered set**, so
which anchors (hence facts) are included is non-deterministic (this *understates* the bridge — a real
M1a ranks anchors by salience deterministically). Absolute quality is low (bridge-class 0.43/2.0).

**Net:** the A/B gives a **weak-but-positive, zero-regression** answer-quality signal — the bridge is
*safe* (never harms) and helps a subset, but does **not** show a large gain on this corpus. The
strongest evidence for M1a remains the *mechanism* legs (100% coverage gap + 6/6 empty-anchor
rescue), not the answer-quality magnitude.

## Verdict & recommended next steps

**Evidence stack for M1a (honestly weighted after `/review-impl`):**
- **Strong — mechanism:** (1) 100% coverage gap; (2) **6/6 empty-anchor rescue** — natural questions
  that name no entity get ZERO graph facts today, a concrete current defect the bridge fixes.
- **Weak-but-positive — answer quality:** (3) on a passage-inclusive baseline with truncation
  excluded, +14% overall / +50% bridge-class, **0 regressions across every fair run**, but only ~1
  stable win and a magnitude too small/noisy (N=15, one small book, local model) to call large.

**Verdict: GO, but a measured one** — justified primarily by the empty-anchor rescue + the
zero-regression safety (the bridge never harms), not by a dramatic answer-quality lift. The build is
low-risk *because* it never regressed; the upside is real but modest on current evidence.

1. **Build M1a** (quality-gated passage→graph anchor bridge) per plan resolutions #2–#4: inject into
   the L2 facts block; anchors = proper/salient passage-surfaced entities not already expanded; degree
   + token capped; degrade-safe. The empty-anchor-rescue alone justifies it, and the A/B shows no
   regression risk.
2. **Corpus caveat carried forward:** the answer-quality magnitude is bounded by (a) one small book
   and (b) the local model's role→entity resolution limit. A larger multilingual corpus (real
   `D-EVAL-BOOK` — a full passage+relation extraction of a big book) remains the follow-on robustness
   check; it was **not** buildable cheaply this session (only Dracula is a wired test-account project;
   the extension chapters are unpublished drafts / trashed).
