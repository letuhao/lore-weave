<!-- CHUNK-META
source: 01_OPEN_PROBLEMS.ARCHIVED.md
chunk: A_llm_reasoning.md
byte_range: 891-9939
sha256: 6585ee584ce8c3964166aa0bc4a3bc05de319f2ff22a2aefd8195ce901c6765c
generated_by: scripts/chunk_doc.py
-->

## A. LLM reasoning & grounding

### A1. NPC memory at scale — **PARTIAL**

**Problem (original):** In a multi-user persistent world, each NPC accumulates memory across many players and many sessions. A popular NPC in an active instance could have thousands of interactions logged. Stuffing this into context on every turn is infeasible; losing it breaks immersion.

**Why hard:** This is a multi-dimensional retrieval problem — must filter memory by (this PC's history, recent world events, canon facts, NPC's core beliefs) under a hard context budget. Existing "chat memory" solutions (Letta/MemGPT, mem0, Zep) are single-user and don't handle multi-PC identity isolation.

**Infrastructure resolved by R8** ([02 §12H](02_STORAGE_ARCHITECTURE.md#12h-npc-memory-aggregate-split-r8-mitigation-a1-foundation)):
- NPC split into core aggregate + per-pair `npc_pc_memory` aggregates
- Bounded growth (max 100 facts per pair, rolling summary every 50 events, LRU eviction)
- Lazy loading scoped by session (R7-L6: NPC in 1 session at a time)
- Cold decay: 30d drop facts / 90d drop embedding / 365d archive to MinIO
- Embedding stored separately (pgvector, not in snapshot)
- Size enforcement with auto-compaction
- Linear-growth problem broken: ~5MB steady per hot NPC vs ~75MB naive

**Semantic layer still `OPEN`:** infrastructure is plumbing, A1's hard parts remain:
- Retrieval quality: which facts from a pair to surface in prompt?
- Summary quality: LLM prompt for compaction
- Fact extraction: what from an interaction becomes a "fact"?
- Evaluation: measurable success on real book data

These require V1 prototype measurement before locking. A1 design deferred pending real data.

**Notes:**
- Hierarchical summarization (per-PC summary + per-region summary + NPC core) now tractable — R8 provides the per-pair substrate.
- LoreWeave's knowledge-service retrieval + timeline filter gives canon facts for free; the novel part is **session memory**, which is reality-local via R8 aggregates.
- Research references: MemGPT (arXiv:2310.08560), Generative Agents (arXiv:2304.03442, Park et al.) — the Stanford "Smallville" paper is the closest analogue. Their NPCs had memory streams + reflection + retrieval. They used 25 agents in a sandbox, not hundreds of real users.

### A2. Temporal consistency across parallel player conversations — **PARTIAL**

**Problem (original):** NPC Elena talks to Player A on Monday and to Player B on Tuesday. If A tells Elena about a murder, does B's Elena know? If yes, conversations get tangled. If no, it's not the same world.

**Resolved by multiverse model** (see [03_MULTIVERSE_MODEL.md](03_MULTIVERSE_MODEL.md)): A and B being in **different realities** see different Elenas — and this is **correct by construction**, not a bug. Each reality is a peer universe with its own NPC state. Cross-reality consistency is no longer a contradiction to resolve.

**What remains `OPEN`:** the sub-problem of **A and B in the *same* reality** interacting with the same NPC. This reduces to:
- Per-PC memory slot on NPC (A1's storage problem)
- Public vs private knowledge (what NPC said publicly in a crowded room vs privately)
- Gossip propagation within a reality

These are harder only within the scope of one reality, which bounds the population (typical cap: 100 PCs per reality).

**Notes:** The multiverse model reframes "same character, different contexts" from a consistency bug into a product feature. The residual within-reality problem is tractable because reality population is bounded.

### A3. Determinism & reproducibility — **PARTIAL**

**Problem:** Same question, different answer. World state requires stable facts. If a player asks an NPC "where is the treasure?" and gets "in the cave" today, "under the bridge" tomorrow, the world is not a world.

**Why hard:** LLMs are non-deterministic by default. Temperature=0 helps but doesn't eliminate drift across model versions/providers.

**Resolved by:** **World Oracle pattern** in [05 §4](05_LLM_SAFETY_LAYER.md) — `world-service` exposes deterministic `oracle.query(reality_id, pc_id, key, context_cutoff)` API; pre-computed fact categories (entity_location, entity_relation, L1_axiom, book_content, world_state_kv); cache invalidated on L3 events touching key; fact-question classifier routes to Oracle, miss → LLM fallback with audit flag; `context_cutoff` filters visibility per PC to prevent spoilers AND cross-PC leaks structurally. Decisions A3-D1..D4 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN` (blocks SOLVED):**
- Classifier accuracy (V1 prototype data on real sessions)
- Oracle key coverage — what fraction of fact questions hit pre-computed? (V1 measurement; missed keys added iteratively)
- Oracle cache hit rate (V1 metric feeds pre-warm strategy)
- Overlaps with [A4 retrieval quality](#a4-retrieval-quality-from-knowledge-service--partial) and [G3 canon-drift detection](#g3-canon-drift-detection-in-production--open)

### A4. Retrieval quality from knowledge-service — **PARTIAL**

**Problem:** Every turn, the system must retrieve relevant context (entities, events, timeline facts) for prompt assembly. Bad retrieval → NPC says canonically wrong things → canon drift → immersion break.

**Why hard:** Retrieval quality on a knowledge graph (vs. flat vector index) is itself an active research area. LoreWeave's knowledge-service is being built right now; retrieval quality has not been measured on real books.

**Known approaches:**
- Microsoft GraphRAG (arXiv:2404.16130) — graph + community summaries
- HippoRAG (arXiv:2405.14831) — personalized PageRank over knowledge graph
- Hybrid keyword + semantic (SillyTavern World Info + embedding fallback)

**Notes:** This is a gating problem. If retrieval doesn't work well enough, nothing else matters. Measurable by running: "show NPC response + top-5 retrieved facts + human grades if response is canon-faithful." Needs benchmark dataset from actual LoreWeave books.

### A5. Tool-use reliability for world actions — **PARTIAL**

**Problem:** Player says "/take the map." System must: (1) verify the map is here, (2) update player inventory, (3) update world state, (4) narrate the result. Requires LLM to reliably call structured tools, not just narrate.

**Why hard:** Tool-call reliability varies by model. Claude and GPT-4 are good; local/small models are not. Partial tool-call failures (half-updated state) corrupt world state.

**Resolved by:** **Structured-command dispatch** in [05 §3](05_LLM_SAFETY_LAYER.md) — 3-intent classifier (command / fact question / free narrative); `/verb target [args]` syntax handled deterministically by `world-service` (validates, writes L3 event, updates projection) BEFORE LLM narrates; LLM tool-calls restricted to non-mutating flavor actions (whisper, gesture, reveal emotion) — state-changing actions (take/drop/attack/heal/move) architecturally forbidden from LLM output; tool-call failure policy (revert + audit + narrator acknowledges distraction, no partial state). Decisions A5-D1..D4 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN` (blocks SOLVED):**
- Tool-call reliability per LLM provider (Claude, GPT-4, Qwen, Ollama) — V1 per-model benchmark
- Command UX polish (tab-complete, autosuggest, verb discovery) — DF5 Session implementation
- Classifier false-negative rate on command-like free-text

### A6. Prompt injection & jailbreak resistance — **PARTIAL**

**Problem:** Players can inject text to break NPC persona, expose system prompt, extract other players' private context, or force NPC to reveal canon spoilers the PC shouldn't know yet.

**Why hard:** No robust defense against prompt injection exists. Mitigations are layered and leaky.

**Resolved by:** **5-layer defense** in [05 §5](05_LLM_SAFETY_LAYER.md) — L1 input sanitization (normalize + pattern flagging + audit), L2 hard server-side delimiters never user-controlled, **L3 canon-scoped retrieval at DB layer** (the critical layer — forbidden facts structurally absent from LLM context; jailbreak cannot leak what isn't there), L4 output filter (persona-break / cross-PC leak / spoiler / NSFW checks with soft retry + hard block), L5 per-PC retrieval isolation enforced at DB layer (RLS or service-layer filter, not prompt discipline). Decisions A6-D1..D5 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN` (blocks SOLVED + ongoing):**
- Output filter calibration (false positive vs miss rate) — V1 adversarial red-team
- Novel jailbreak classes — ongoing ops, no framework can claim "solved"
- L1 input sanitization pattern list maintenance — ongoing

**Catastrophic failure mode addressed:** Private context leak between players is architecturally prevented via L3 + L5 (retrieval filtering BEFORE LLM + per-PC DB isolation). Persona breaks (L4 soft fail) remain acceptable-and-reportable.

---

