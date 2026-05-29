# Lore-Enrichment — Research Landscape (Pass 1)

> **Date:** 2026-05-29 · **Branch:** `lore-enrichment/foundation`
> **Method:** deep-research harness — 5 angles → 23 sources → 107 claims extracted → 25 verified (3-vote adversarial) → **22 confirmed / 3 refuted** → 11 synthesized findings.
> **Question:** Can any existing system enrich a sparse, culturally-dense classical source (concretely 封神演义 Fengshen Yanyi) into game-ready, canon-faithful worldbuilding? Cover (1) KG/RAG enrichment, (2) generative-agent emergent lore, (3) co-writing story-bible products. Evaluate four techniques: (a) template/entity scaffolding, (b) external cultural retrieval, (c) controlled canon-grounded fabrication, (d) re-cooking real history/myth.

---

## Headline

**No shipped product performs the full end-to-end task** — taking an under-described, culturally-dense classical source and expanding its off-page detail into game-ready, canon-faithful worldbuilding. **But every constituent technique exists separately** in research and (partly) in product form. → **White space confirmed.** The opportunity is the *composition* of all four techniques + cultural grounding, anchored to an authored-glossary SSOT + a fuzzy/semantic KG layer (the two-layer pattern already in `CLAUDE.md`).

---

## Approach 1 — KG / RAG enrichment (strongest technique base; mostly research)

| System | Mechanism | Maps to | Source | Confidence |
|---|---|---|---|---|
| **Microsoft GraphRAG** | LLM derives entity KG → pre-generates community summaries → map-reduce per-community for corpus-wide answers | (a) scaffolding + whole-world "off-page" synthesis | arXiv:2404.16130 | high (3-0) |
| **Inference-time KG construction** | ⭐ **seed-KG from hints → expand via LLM internal knowledge → selectively refine via external retrieval** to fix coverage/accuracy | (b)+(c) — closest mechanistic match to seed-driven grounded enrichment | arXiv:2509.03540 | high (3-0) |
| **KG-guided storytelling** | Per-scene subgraph query → generate → update/refine/extend nodes → cleanup | iterative anti-drift scaffolding | arXiv:2505.24803 | med (3-0 mechanism; 2-1 hallucination claim) |
| **G-KMS** | 5-stage: knowledge grounding → **schema-governed generation** → normalization repair → **engine-aligned admission** → application | (a)+(c); fixes "LLM output structurally invalid for game engine" | MDPI Systems 14(2):175 (2/2026) | high (3-0) |
| **Dependency-driven JSON pipeline** | World → NPC → PC → quest planning → quest expansion; each stage conditions on prior stages' JSON | staged schema-enforced worldgen, anti-drift | arXiv:2604.25482 | high (3-0) |
| **Competency-Questions-as-plan** | Repurpose design-time CQs into run-time executable narrative plans (plan-retrieve-generate) | controlled canon-grounded gen | arXiv:2604.02545 | med (3-0 on CQ claim; auditable framing refuted) |

Supporting: schema-repair corroborated by PANGeA (arXiv:2404.19721), SINE (68–86% playability = 14–32% raw failure), ScriptDoctor (arXiv:2506.06524).

## Approach 2 — Generative agents / society simulation (proves seed-driven; lore is generic)

| System | Result | Limitation | Source | Confidence |
|---|---|---|---|---|
| **Stanford Generative Agents (Smallville)** | Seed = 1 sparse bio paragraph → 25 agents autonomously emerge social lore (party invites, dating, election talk) via memory-stream architecture | Generic-life lore, **no authored canonical source**; real-world predictive validity critiqued (arXiv:2507.06310) | arXiv:2304.03442 | high (3-0) |
| **Project Sid (Altera)** | 10–1,000+ Minecraft agents; autonomous roles, rule change, cultural/religious transmission | Lore from agent society not authored source; not peer-reviewed (commercial lab); religion was researcher-seeded, only transmission emergent; 1000+ hit compute limits | arXiv:2411.00114 | med (2-1) |

## Approach 3 — Co-writing / story-bible products (shipped, but thin verified coverage)

| Product | Mechanism | Source | Confidence |
|---|---|---|---|
| **NovelAI Lorebook + Lore Generator** ⭐ | Key-triggered context injection (activation keys auto-insert entry text); built-in Lore Generator creates lore for any character/object/location/concept from seed + tags, pulling existing canon (Memory, Author's Note, recent story, other entries) | docs.novelai.net/en/text/lorebook | high (3-0) |
| World Anvil AI, Sudowrite Story Bible, Novelcrafter Codex, Campfire, LoreForge, Kanka, AI Dungeon, Hidden Door | **Named in question but produced NO independently-verified surviving claims in this run** — commercial landscape under-documented | — | — (gap → Pass 2) |

## Cultural-grounding gap (the Fengshen Yanyi heart of the case)

- **CHisAgent** (arXiv:2601.05520, 1/2026): documents that **LLMs have limited historical/cultural reasoning in non-English contexts, especially Chinese history.** 3-stage: Inducer (extract hierarchy from raw corpora) → Expander (add intermediate concepts via LLM world knowledge) → **evidence-guided Enricher (integrate external structured historical resources for faithfulness)** — architecturally ≈ techniques (b) + (d). **BUT** targets factual event-taxonomy over the Twenty-Four Histories, **not fictional/mythological lore** → the Fengshen case is an explicitly unmet need. Confidence high (3-0).

---

## Refuted claims (excluded — do not rely on)

1. "Live editable KG strongly preferred for story editing (13/14 users)" — **1-2** (arXiv:2505.24803).
2. "2509.03540 fuses internal+external KG = exactly the enrichment pattern" — overreach, **1-2**.
3. "Neuro-symbolic RAG makes story generation 'evidence-closed and fully auditable'" — **1-2** (arXiv:2604.02545).

## Caveats

- Fast-moving field; several sources are 2026 preprints (2604.25482, 2604.02545, 2601.05520) + one Feb-2026 MDPI article — current as of May 2026, likely superseded soon.
- Strongest mechanistic matches (2509.03540, CHisAgent) target **factual QA / historical taxonomy, not fiction** — transfer to canon-faithful fictional enrichment is a reasonable but **unproven** analogy.
- G-KMS read via search snippets (direct fetch 403); MDPI variable rigor.
- Commercial-product mapping is thin → **Pass 2 scheduled** to scan shipped tools.
- White-space finding is an inference composed across individually-verified component techniques (medium confidence on the composition itself).

## Open questions (carried forward)

1. Do any commercial co-writing/worldbuilding products implement the **authored-SSOT + semantic-KG two-layer** pattern, and how do their canon-consistency mechanisms compare to NovelAI's key-triggered injection?
2. Has any research system been evaluated on expanding a **sparse culturally-dense classical source** (vs. user prompts / factual corpora) into game-ready worldbuilding, with a canon-fidelity / cultural-faithfulness metric?
3. Reliability of schema-governed repair (G-KMS, SINE) for **cultural** correctness (anachronism/canon-violation), not just JSON validity?
4. Can GraphRAG community summaries + CHisAgent external-resource integration jointly ground off-page details (geography, economy, daily life) in real Shang–Zhou history / Shan Hai Jing while preserving the book's tone — and what evaluation framework validates non-English mythological grounding?

---

## Implication for the service design

Best-fit architecture to compose: **seed-KG → expand → external-refine** (2509.03540) **+** GraphRAG community-summary corpus synthesis (2404.16130) **+** schema-governed generation / engine-aligned admission (G-KMS, 2604.25482) **+** CHisAgent-style external cultural retrieval (Shan Hai Jing, Shang–Zhou history) — all anchored to **glossary-SSOT + fuzzy/semantic KG layer**. Differentiator = the composition + cultural grounding for an under-described classical source, which no current system delivers end-to-end.

*Full verified findings, votes, evidence quotes, and the source list are preserved in the deep-research task output (run `wf_8128febc-39a`).*

---

# Pass 2 — Commercial Product Scan (2026-05-29)

> **Method:** deep-research — 5 angles → 22 sources → 95 claims → 25 verified → **19 confirmed / 6 refuted** → 9 synthesized findings. (run `wf_e507be00-d9d`)
> **Goal:** competitive positioning — which shipped products do seed-driven enrichment, and how they maintain canon-consistency.

## Comparison table (verified)

| Product | Seed-driven enrichment? | Canon-consistency mechanism | Two-layer (SSOT + semantic KG)? | Cultural grounding? |
|---|---|---|---|---|
| **NovelAI** Lorebook + Lore Generator | ✅ create new entry + expand in place from short prompt | **Keyword** (activation key) + opt-in context-stuffing (~2500 chars) | ❌ SSOT + keyword, no KG | ❌ |
| **Sudowrite** Story Bible | ✅ Generate/Rewrite **grounded** in existing fields (strongest co-writing example) | internals undetermined ("keyword-only" claim refuted 0-3) | ❌ SSOT yes; semantic layer unconfirmed | ❌ |
| **Sudowrite** Brainstorm | ⚠️ seed-driven but **NOT grounded** — cannot see Story Bible | (anti-pattern: isolated ideation) | ❌ | ❌ |
| **Novelcrafter** Codex | ⚠️ marketing claims it; "Contextual Expansion constrained" claim **refuted 0-3** → unconfirmed | **Keyword/name/alias** match (docs: explicitly "not embedding/semantic"); related-entry cascade (graph-of-keywords, still lexical) | ❌ structured SSOT + keyword | ❌ |
| **AI Dungeon** | ❌ Memory Bank only **reactively summarizes** gameplay; no seed→new-canon | Story Cards = **keyword**; Memory Bank = **embedding** (over gameplay, NOT over authored store) | ⚠️ embedding exists but over gameplay, not entity store | ❌ |
| **World Anvil** | ❌ **deliberately declined AI** ("not within scope"); "generators" = weighted-random selectors | static authored wiki | ❌ | ❌ |

## Key findings

1. **Keyword injection dominates** — nearly every tool maintains canon by literal keyword/mention matching, NOT RAG/embeddings/KG.
2. **Embeddings rare and mis-placed** — only AI Dungeon uses embeddings, and over gameplay summaries, not an authored entity store; it does not enrich a seed into canon.
3. **Vendor-acknowledged failure mode:** when info falls out of context the model fabricates (drift/hallucination); AI Dungeon docs state its Memory System is "not guaranteed 100%." → direct evidence that keyword-injection alone does NOT solve canon-consistency.
4. **White space confirmed (2nd time):** no product fuses `authored SSOT + semantic KG + schema-governed canon-anchoring + cultural grounding`. Existing tools split the two layers across separate products.

## Refuted (6)
- Sudowrite "grounding = field-injection, no embedding" (0-3) → Sudowrite internals remain undetermined.
- Novelcrafter "Contextual Expansion = constrained enrichment" (0-3) → existence as true constrained enrichment unconfirmed.
- 4 AI Dungeon Story-Card / context-window claims (mis-interpretation).

## Coverage gap / open questions
- **Not covered (no verified claims):** Campfire (Blaze AI), LegendKeeper, Kanka, Fantasia Archive, Obsidian, Scrivener, Plottr, Inworld AI, Charisma.ai, Ludo.ai, Scenario, Layer AI, Hidden Door, and any 2025-26 "knowledge graph for fiction" entrant → absence of evidence, not evidence of absence.
- Sudowrite's actual retrieval mechanism (keyword vs embeddings vs hybrid) undetermined.
- Cultural-grounding / non-English negative is **inferred from silence**, not a tested failure.
- Pricing / maturity / user-base signals not captured.

## Net competitive conclusion
Seed-driven enrichment exists only in **shallow keyword-injected** forms. The two-layer (authored-SSOT + semantic-KG) pattern, schema-governed canon-anchoring, and cultural grounding for an under-described classical source are **all absent from the verified commercial set** — the same white space Pass 1 found in research, now confirmed on the product side.
