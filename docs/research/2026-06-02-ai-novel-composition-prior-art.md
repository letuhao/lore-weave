# Prior Art — AI-assisted / Autonomous Novel Composition (as a *system*)

> **Date:** 2026-06-02 · **For:** [`docs/specs/2026-06-02-composition-service-vision.md`](../specs/2026-06-02-composition-service-vision.md) (COMP-* / `composition-service`).
> **Question:** Is anyone building "treat literature as a system → backend + GUI for author + AI co-creation, grounded on a strong knowledge foundation"? How far have they gotten?
> **Method:** web sweep (commercial products · open-source · academic SOTA · worldbuilding/diagram GUI tools · maturity/limitations). Snippet-level unless a source was fetched (the two KG papers were fetched).
> **Confidence note:** product feature claims are vendor/review-sourced; treat as directional, verify before depending on a specific feature.

---

## §0 Bottom line

**Yes — every individual piece of the vision exists in the wild, and the field is moving fast (a dozen multi-agent / KG-grounded papers in 2024–2026). But no one ships the *combination* LoreWeave is positioned for**, and our existing foundation is exactly the part everyone else hand-rolls or fakes:

- **Story-bible / codex / lorebook** (the "knowledge" layer) → every serious product has one, but it's **manually authored wiki text**. Ours is a **production knowledge graph auto-extracted from real novels** + an authored glossary SSOT. That is the "editable KG at scale" the research prototypes wish they had.
- **Multi-agent generation + generate→critique→revise loop** → heavily validated in academia and a few OSS tools. We can adopt the proven shape.
- **A real quality gate** (LLM-as-judge, calibrated, anti-self-reinforcement) → **almost nobody has this**; it's the single best antidote to "AI slop", and we already run it in production (learning-service + `loreweave_eval`).
- **Author-facing diagrams** (relationship/timeline/beat) → mature in worldbuilding tools (Campfire, World Anvil, Plottr) but **disconnected from AI generation and from a graph DB**. We can fuse them.
- **The flywheel** (generate → extract back into the graph → retrieve for the next chapter) → **not seen in any product**; it's a genuine architectural edge.

**The frontier nobody has closed:** novel-length (100k+ word) coherence + quality without heavy human steering. The consensus "what works" is **hybrid / assisted** writing. → validates **COMP-Q1 lean = build the shared spine, ship co-writing first.**

---

## §1 Commercial products (the consumer landscape)

| Product | "Knowledge" layer | Generation | Notable |
|---|---|---|---|
| **Sudowrite** | **Story Bible** (consistency of characters/details) | Brainstorm + Write + "Story Engine" | Shipped **Muse 1.5** (June 2025), a proprietary fiction model fine-tuned on published novels; positions on **prose quality** |
| **Novelcrafter** | **Codex** — wiki-style DB of characters/locations/lore/**relationships** | Scene-by-scene drafting | **BYOK** (≈$4/mo, you pay providers directly) — *same model LoreWeave already uses* |
| **NovelAI** | **Lorebook** (define entities the AI references) | Continuation-style | **Privacy-first**, client-side encryption ("never reads your work") |

**Read-through:** the market has converged on "(authored knowledge base) + (LLM generation that references it)". LoreWeave's differentiator is that the knowledge base is **auto-built and a real graph**, not a hand-maintained wiki — and that we can **gate output with a judge**, which none of these expose.

Sources: [11 tools tested 2026 (mylifenote)](https://blog.mylifenote.ai/the-11-best-ai-tools-for-writing-fiction-in-2026/) · [Laterpress: best AI fiction tools 2026](https://www.laterpress.com/craft-of-writing/best-ai-writing-tools-for-fiction/) · [Kindlepreneur: 15 best AI writing tools](https://kindlepreneur.com/best-ai-writing-tools/) · [Sudowrite vs Novelcrafter (Medium)](https://ilampadmanabhan.medium.com/sudowrite-vs-novelcrafter-bdc3f33ba95f) · [inkfluenceai: 8 tools, same 30k-word manuscript](https://www.inkfluenceai.com/best-ai-novel-writer-2026)

---

## §2 Open-source frameworks

- **ai-book-writer** (adamwlarson) — AutoGen multi-agent, "can an entire book be written by agents?". [repo](https://github.com/adamwlarson/ai-book-writer)
- **gemini-writer** (Doriandarko) — autonomous novel agent, **automatic context compression** near token limits. [repo](https://github.com/Doriandarko/gemini-writer)
- **302_novel_writing** (302.AI) — manual + AI chapter gen, multiple **style** presets (modern/ancient/fantasy…). [repo](https://github.com/302ai/302_novel_writing)
- **InkOS** (surfaced via the `novel-generation` GitHub topic) — CLI agent orchestrating ~10 specialized agents with a **33-dimension continuity audit**, **anti-AI-slop filter**, and **style cloning**. *URL unverified — listed, not inspected.*
- General agent stacks adaptable to writing: **MassGen** (multi-agent orchestration). [repo](https://github.com/massgen/MassGen)

Sources: [GitHub topic: novel-generation](https://github.com/topics/novel-generation) · [GitHub topic: novel-ai](https://github.com/topics/novel-ai)

**Read-through:** the OSS frontier is "orchestrate N role-agents + fight context limits + filter slop". Confirms our **generator–critic–RAG** role split; InkOS's "continuity audit + anti-slop" is exactly our **eval/judge critic** done ad hoc — we can do it with a *calibrated* judge.

---

## §3 Academic state of the art

### §3.1 The canonical lineage (hierarchical + memory + revision)
- **Dramatron** (DeepMind, 2022) — hierarchical prompt-chaining: log-line → title → characters → scene summaries → locations → dialogue. The original "architecture-first" generation. [arxiv 2209.14958](https://arxiv.org/pdf/2209.14958)
- **Re³** (Berkeley, 2022) — *Recursive Reprompting & Revision*: structured plan → inject plan+state per passage → **rerank** for coherence → **edit** for factual consistency. [arxiv 2210.06774](https://arxiv.org/abs/2210.06774) · [code](https://github.com/yangkevin2/emnlp22-re3-story-generation)
- **DOC** — *Detailed Outline Control* for long-story coherence (outline-driven).
- **Agents' Room** (DeepMind) — Planning + Writing agents under an **Orchestrator** (≈1–2k words).
- **TreeWriter** (Jan 2026) — hierarchical planning + writing for long-form documents. [arxiv 2601.12740](https://arxiv.org/html/2601.12740v1)
- **Dynamic Hierarchical Outlining w/ Memory-Enhancement** (Dec 2024). [arxiv 2412.13575](https://arxiv.org/pdf/2412.13575)

### §3.2 Multi-agent (2024–2026 — very active)
- **StoryWriter** — modular **open-source** multi-agent framework for controllable, scalable long-story gen (ACM CIKM 2025). [doi](https://dl.acm.org/doi/10.1145/3746252.3761616)
- **StoryBox** — collaborative multi-agent *simulation*, **bottom-up** long-form (characters as agents → emergent plot). [arxiv 2510.11618](https://arxiv.org/html/2510.11618v3)
- **Plug-and-Play Dramaturge** — divide-and-conquer **iterative script refinement** via collaborating agents (a dedicated *reviser/editor* loop). [arxiv 2510.05188](https://arxiv.org/html/2510.05188v3)
- **Constella** — LLM multi-agents for **interconnected character creation** (ACM TOCHI). [doi](https://dl.acm.org/doi/10.1145/3796234)
- **A Multi-Agent Framework for Long Story Generation** [arxiv 2506.16445](https://arxiv.org/pdf/2506.16445) · **CreAgentive** (agent-workflow creative engine) [arxiv 2509.26461](https://arxiv.org/pdf/2509.26461)
- Survey: **A Survey on LLMs for Story Generation** (EMNLP Findings 2025). [pdf](https://aclanthology.org/2025.findings-emnlp.750.pdf)

### §3.3 Knowledge-graph–grounded generation (the closest analog to us — **fetched**)
- **Guiding Generative Storytelling with Knowledge Graphs** ([arxiv 2505.24803](https://arxiv.org/abs/2505.24803)) — a **KG-assisted pipeline** with an **editable KG** the user can modify to shape the narrative. 15-person user study: **"strong sense of control," "engaging, interactive, playful."** Crucial honest finding: **benefits concentrate in action-oriented, structurally-explicit narratives, NOT introspective ones.** → KG-grounding helps plot/continuity, not interiority. Design accordingly.
- **Long Story Generation via Knowledge Graph and Literary Theory** ([arxiv 2508.03137](https://arxiv.org/pdf/2508.03137)) — multi-agent + **dual memory** (long-term = theme/critical plot elements to stop **theme drift**; short-term = recent outlines) + a **"story-theme-obstacle" framework grounded in narratology** that injects unpredictability, with KG nodes for new content + writer↔reader dialogue for revision. *Claims higher quality; abstract gives no quantitative benchmark — treat as directional.*
- **GraphRAG** (Microsoft) — graph-structured RAG over **narrative private data** (already cited in our `CLAUDE.md` knowledge-service rationale). [blog](https://www.microsoft.com/en-us/research/blog/graphrag-unlocking-llm-discovery-on-narrative-private-data/)

**Read-through:** academia has *independently arrived at LoreWeave's thesis* — graph + literary structure + multi-agent + revision loop. Two things they lack that we have: (1) a **production-scale** auto-extracted graph (theirs are small/toy or manually editable); (2) a **calibrated judge** as the quality gate (they use ad-hoc metrics or small user studies).

---

## §4 Worldbuilding & diagram GUIs (the "diagram / style / genre" part of the vision)

| Tool | Visual strength | Gap vs our vision |
|---|---|---|
| **World Anvil** | Wiki + **maps, timelines, family trees, charts**, interlinked world bible | Manual; not graph-DB; no integrated AI generation loop |
| **Campfire** | Modular (characters, locations, magic systems, languages, species, maps); strong **maps/timelines** | Manual; pre-prose worldbuilding, not generation-coupled |
| **Plottr** | **Timeline view**, scene cards, color-coded arcs/subplots (pure structure) | Plotting only; no knowledge base, no AI |
| **Storyflow** | **Canvas + AI** alongside story bibles | Closest hybrid; still not graph-DB-backed or judge-gated |

Sources: [Campfire vs World Anvil (Kindlepreneur)](https://kindlepreneur.com/campfire-vs-world-anvil/) · [Storyflow: 12 best worldbuilding tools 2026](https://storyflow.so/blog/best-tools-worldbuilding-2026) · [Plottr worldbuilding](https://plottr.com/worldbuilding-software/)

**Read-through:** the diagram UX is a **solved, well-understood design space** — we can borrow patterns (relationship graph, timeline, beat/scene cards, plot-thread tracker). The novelty is wiring those diagrams to a **live graph that the AI also reads/writes**, so the diagram *is* the AI's working memory, editable by the author.

---

## §5 Maturity — what's solved vs not

**Solved / reliable today:**
- Short coherent passages, brainstorming, outline expansion, style/voice transfer, scene-level drafting.
- Hierarchical decomposition + outline control for multi-thousand-word stories.
- Authored knowledge bases that the LLM references for local consistency.

**NOT solved (the frontier = our opportunity):**
- **Novel-length coherence (100k+ words).** Context windows force chunked generation; repeated calls weaken coherence; **theme drift** and contradictory character behavior accumulate. Everyone fights this with hierarchy + memory + revision; nobody has *won*.
- **Autonomous quality.** Unsupervised AI prose is "**cliché or flat**" — the dreaded *AI slop*. The community consensus best practice is **hybrid/assisted**, where AI assists but doesn't dominate.
- **Genre transfer.** Most systems are genre-locked; transferring the same story across genres is hard.
- **Interiority.** KG-grounding helps action/plot, **not introspective narrative** (per the 2505.24803 user study).

Sources: [Reddit writers: what works/fails 2025](https://resizemyimg.com/blog/writing-a-novel-with-ai-in-2025-what-works-what-fails-and-real-reddit-writers-feedback-on-using-chatgpt-or-similar-models/) · [Vibe-writing research report](https://christophersilvestri.com/research-reports/vibe-writing/) · [Aliventures: will AI write novels?](https://www.aliventures.com/will-ai-write-novels/)

---

## §6 Where LoreWeave already stands vs the field

| Capability the field hand-rolls | LoreWeave already has (production) |
|---|---|
| Manually-authored story bible / wiki | **Auto-extracted knowledge graph** (knowledge-service) + authored glossary SSOT + wiki |
| Toy / small editable KG (research) | **Production graph at corpus scale**, with correction-capture + outbox events |
| Ad-hoc continuity audit / "anti-slop" | **Calibrated LLM-as-judge** (`loreweave_eval`, F1=0.869 of record, anti-self-reinforcement, online eval flywheel) |
| BYOK provider plumbing | provider-registry + `loreweave_llm` Client (gateway invariant) — **done** |
| English-centric generation | **Multi-locale** heritage (translation platform) → multi-language generation is a free differentiator |
| No feedback loop | **Generate → extract → graph → retrieve** flywheel reuses the *entire* extraction + eval stack |

**Net:** competitors build *one* of {knowledge base, multi-agent gen, quality gate, diagram GUI}. LoreWeave can build the **integrated loop** because layers 1/3/4 (graph, eval, provider) already exist and are production-ready. The new work is the **generation layer + template library + GUI**.

---

## §7 Design lessons to adopt (folded into the DESIGN spec)

1. **Hierarchical + dual memory** (Re3/DOC/TreeWriter/2508.03137 all converge): Planner produces structure; keep **long-term theme memory** (anti-drift) + **short-term recent-context memory**. → our Planner + retrieval design.
2. **Generate → critique → revise** as a first-class loop (Re3 revision, Dramaturge, InkOS audit). → our **Continuity-Critic = the eval judge**, with **new prose-quality dimensions** (coherence, voice, pacing, canon-consistency) added to `loreweave_eval`.
3. **Editable, author-controllable graph in the GUI** = "strong sense of control" (2505.24803). → the diagram *is* the AI's working memory; author edits write through to the graph.
4. **KG-grounding targets plot/continuity, not interiority** (2505.24803). → don't over-promise auto-introspection; keep the human in the loop for interior/voice-heavy passages.
5. **Genre as pluggable template packs** (counter the genre-lock limitation). → confirms **COMP-Q3 = genre-agnostic engine**; web-novel is one pack.
6. **Ship assisted/hybrid first** (universal "what works"). → confirms **COMP-Q1 = shared spine, co-writing first**, autonomous as an opt-in mode behind the same loop + a stricter judge gate.
7. **Anti-slop is a quality-gate problem, not a prompt problem** — our calibrated judge is the differentiator; lean on it hard.

---

## §8 Full source list

**Products/landscape:** mylifenote, Laterpress, Kindlepreneur, inkfluenceai, Sudowrite/Novelcrafter (Medium) — see §1.
**OSS:** ai-book-writer, gemini-writer, 302_novel_writing, MassGen, GitHub topics novel-generation / novel-ai — see §2.
**Academia:** Survey (EMNLP'25 Findings); Dramatron (2209.14958); Re3 (2210.06774); TreeWriter (2601.12740); Dyn. Hierarchical Outlining (2412.13575); StoryWriter (CIKM'25); StoryBox (2510.11618); Dramaturge (2510.05188); Constella (TOCHI); Multi-Agent Long Story (2506.16445); CreAgentive (2509.26461); **KG+Literary Theory (2508.03137)**; **Guiding Storytelling w/ KG (2505.24803)**; GraphRAG (Microsoft) — see §3.
**Worldbuilding GUI:** Kindlepreneur (Campfire vs World Anvil), Storyflow, Plottr — see §4.
**Limitations:** resizemyimg (Reddit), christophersilvestri (vibe-writing), Aliventures — see §5.
