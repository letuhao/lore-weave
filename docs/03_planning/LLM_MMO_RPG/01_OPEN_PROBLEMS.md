# 01 — Open Problems

> **Status:** Exploratory working list. Not exhaustive.
> **Gate:** No implementation of the MMO RPG direction is credible until a majority of `OPEN` items below have at least a `PARTIAL` answer.

This document is the honest counterweight to `00_VISION.md`. It lists the problems that would sink the project if left unsolved. Each entry has:

- **Problem:** what it is
- **Why hard:** what makes it non-trivial
- **Status:** `OPEN` (no known approach) · `PARTIAL` (approach exists but unvalidated) · `KNOWN PATTERN` (industry-standard solution, need to apply it) · `ACCEPTED` (conscious trade-off)
- **Notes:** known approaches, analogues, or references

Categories:

- A. LLM reasoning & grounding
- B. Distributed systems
- C. Product / UX
- D. Economics
- E. Moderation, safety, legal
- F. Content design
- G. Testing & operations

---

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

## B. Distributed systems

### B1. World state concurrency — **KNOWN PATTERN**

**Problem:** Two players simultaneously `/take map`. Race condition.

**Why tractable:** Standard MMO/DB problem. Optimistic concurrency (version column), deterministic first-write-wins, narrate loser's failure ("the map is gone — someone grabbed it before you").

### B2. Real-time transport (WebSocket) — **KNOWN PATTERN**

**Problem:** Players need sub-second updates when other players act or NPCs speak. Scales to thousands of concurrent connections.

**Why tractable:** Standard pattern. LoreWeave already has a plan (`70_ASYNC_JOB_WEBSOCKET_ARCHITECTURE_PLAN.md`). Reuse.

### B3. World simulation tick — **PARTIAL**

**Problem:** Does the world do anything when no one is playing? If yes: NPCs age, events happen, rumors spread — compute cost grows unboundedly. If no: world is frozen in time between sessions, breaks immersion.

**Why hard:** Genuine product trade-off with cost implications. No universally right answer.

**Resolved by:** 3-mode tiered framework, per-reality configurable via World Rules (DF4):

- **V1 default = frozen** (B3-D1) — no between-session activity; NPCs resume where last session ended. Cheapest; matches V1 solo RP scope.
- **V2+ opt-in lazy-when-visited** (B3-D2) — cheap LLM summary on first player entering region after gap > 24h (default). 1 LLM call per region visit = bounded cost.
- **V3+ opt-in scheduled tick** (B3-D3) — nightly/weekly cron per reality with daily cost budget cap (`multiverse.simulation.daily_budget_usd`). Advances: NPC relationship drift (within R8-L4 decay), plotline beats, rumor propagation. Skip if idle > N days.
- **Reality clock** (B3-D4) — `reality_registry.reality_time` advances during active sessions; between-session advancement depends on mode.
- **Platform-mode tier-aware budget** (B3-D5) — free tier = frozen only; paid tiers opt-in to tick.

Decisions B3-D1..D5 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN`:**
- Tick pacing (NPC drift rate, rumor frequency) — V2+ playtest
- Real-sec → in-world-sec ratio default — V1 UX feedback
- Generative plotline beat quality — V3 prototype

### B4. Multi-user turn arbitration — **PARTIAL**

**Problem:** Three players in a tavern all talk to Elena at once. Elena responds to whom, in what order?

**Known approaches:**
- Round-robin with merge ("Elena looks between you three and says...")
- Priority by speech-act type (question > statement > aside)
- Per-PC streams (Elena responds to each privately, world events broadcast separately)

**Notes:** Probably solvable by UX convention rather than algorithm.

### B5. Rollback / point-in-time recovery — **PARTIAL**

**Problem (original):** Bug corrupts world state across instances with N active players. How to revert without losing hours of player progress?

**Resolved by:** Full event sourcing ([02 §4](02_STORAGE_ARCHITECTURE.md)) + snapshot fork ([03 §6](03_MULTIVERSE_MODEL.md)) + DB-per-reality ([02 §7](02_STORAGE_ARCHITECTURE.md)). Rollback = replay events to chosen point; blast radius = one reality. Snapshot-fork semantics means rollback of parent does not affect forked children — each reality is its own recovery domain.

**Residual `OPEN` bits:** event schema evolution during replay (R3 in 02), projection rebuild time at scale (R2 in 02), and "did the bug write events that shouldn't exist" — compensating events pattern needed for logical rollback without history mutation.

**Why hard:** Standard DB backup isn't enough — player perception of "what happened" now diverges from DB state. Need event-sourced architecture from day one, or accept data loss as SLA.

**Notes:** Event sourcing (every change as an append-only event) allows replay to any point. Overkill for V1; mandatory for any real V3.

### B6. Sharding at scale — **KNOWN PATTERN**

**Problem:** 10K+ users on one world instance overwhelms any single DB.

**Why tractable:** Classic MMO sharding: split by instance/region, federate queries only where needed. Not a V1 problem.

---

## C. Product / UX

### C1. Player voice vs narrative voice — **PARTIAL**

**Problem:** User types `/say I hate the king`. Does the AI narrator rewrite this as "You stand and declare, voice trembling with rage, that you despise the king"? Or keep it raw?

**Why hard:** Rewrite = novelistic feel but player loses their voice; raw = chat-bot feel, breaks immersion.

**Resolved by:** 3-mode voice framework with inline override:

- **C1-D1** — 3 modes: **terse** (literal, minimal wrap), **novel** (full prose rewrite), **mixed** (auto-adapt: pivotal=novel, casual=terse). **V1 default = mixed.**
- **C1-D2** — inline per-turn override: `/verbatim` forces terse, `/prose` forces novel for current turn only.
- **C1-D3** — World-Rule override (DF4): author can force a mode per reality (e.g., literary canon → novel locked).
- **C1-D4** — persistence: user voice preference per book stored in auth-service user-preferences.
- **C1-D5** — LLM Safety Layer integration: voice mode is a prompt-template variable; output filter (A6-D4) enforces mode-consistency (terse must not produce 3-paragraph rewrite).

Decisions C1-D1..D5 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN`:**
- "Mixed" auto-adapt classifier (pivotal vs casual) — V1 tuning
- Which mode users prefer at scale — V1/V2 analytics
- Mode-specific prompt template quality — V1 copy refinement per `UI_COPY_STYLEGUIDE.md`

### C2. Narrative pacing — **ACCEPTED (research frontier)**

**Problem:** Unstructured LLM small-talk devolves into infinite low-stakes conversation. Real stories have beats, rising tension, payoff. LLMs alone don't do this.

**Why hard:** Requires an "AI GM" layer above NPCs that tracks narrative tension and injects events/complications. Open research (closely linked to F2).

**Accepted stance (2026-04-23):** A proper AI-driven narrative pacing layer is open research. **V1 pragmatic workaround**: author-authored quest scaffolds (F3-D1/D2) provide structural pacing — beats, rising action, outcomes — at scene level. Narrator fills in prose within those beats but does NOT drive tension at story level. Small-talk is allowed to drift; players self-regulate or close session.

**Revisit trigger:** V2+ prototype data on session-length drift rates + public research progress (Generative Agents successors, multi-agent narrative planners). If small-talk sessions empirically feel "dead" and F3 scaffolds can't be authored fast enough to cover it, reopen with concrete V1 data.

**Residual — no longer blocks design:** pacing is a product-quality concern, not a structural blocker. V1 can ship without it.

**Notes:** Generative Agents paper (Park et al.) used "reflection" + "planning" but didn't solve pacing for a human audience. Could cheat with scripted quest scaffolds and let LLM fill in, like tabletop modules.

### C3. Cold-start empty-world problem — **PARTIAL**

**Problem:** An MMO is no fun with 0 other players. Day 1 of launch: no one logs in twice.

**Why hard:** Product/marketing, not technical. Solution space includes: solo-first (Shape A) onboarding that doesn't feel empty; AI "populated" NPCs that substitute for players; scheduled "events" that pull people back.

**Resolved by:** Product strategy that reframes the problem — C3 is largely dissolved by earlier decisions (multiverse NPCs as world-fillers, M1 discovery defaults, staged V1/V2/V3 scoping). Explicit locks:

- **C3-D1** V1 = **solo-first MVP**. Single-player RP is the first shipping experience. MMO population is NOT a V1 requirement.
- **C3-D2** NPC-populated world is the primary immersion mechanism (LLM-driven NPCs, not other players). Matches multiverse §1 philosophy. MMO is additive, not foundational.
- **C3-D3** Staged launch funnel: Reader (M7-D2) → single-player → discover other timelines (M1-D1) → (V2) coop scenes → (V3) MMO persistence. Each step self-sufficient.
- **C3-D4** Scheduled events (V2+) create predictable synchronous play windows without always-on population. Full UX spec deferred to DF5.
- **C3-D5** Friend-follow (reuses M1-D3) = primary organic MMO concentration mechanic.
- **C3-D6** Anti-dispersion defaults (reuses M1-D2 composite ranking + M1-D6 create-new gating) prevent fork-spam creating lonely realities at launch.

Decisions C3-D1..D6 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN`:**
- Scheduled-event UX spec (DF5 detail)
- Launch marketing strategy (product/growth scope, not design-doc scope)
- First-week funnel metric targets — V1 prototype data

### C4. Author canon vs player-emergent narrative — **PARTIAL**

**Problem (original):** A book's author has a canonical story. Players in the world create emergent stories. How do these relate? Is player narrative throwaway, or can it feed back into canon?

**Resolved by:** Four-layer canon model in [03 §3](03_MULTIVERSE_MODEL.md). Author canon lives at L1 (axiomatic) and L2 (seeded). Emergent narrative lives at L3 (reality-local, immutable within its reality). Player stories are **not throwaway** — they are permanent L3 canon of their reality. **Canonization** (L3 → L2 promotion) is an explicit author-gated flow.

**Residual `OPEN`:** IP ownership of canonized content (E3), UI/diff tooling for author review, bright lines for what kinds of L3 events are canonization-eligible.

### C5. Multi-stream UI — **PARTIAL**

**Problem:** User sees simultaneously: other players' chat, NPC narrative responses (slow, streaming), system action results (fast), world event broadcasts. One chat window is too noisy.

**Known approaches:**
- Tabbed streams (say / narration / system / whisper)
- Inline with visual differentiation (color, icon, font)
- Classic MUD pattern: everything in one scrolling log with prefixes

**Notes:** Mostly a UI design problem. Solvable but important to prototype early.

---

## D. Economics

### D1. LLM cost per user-hour — **OPEN**

**Problem:** Back-of-envelope: 100 concurrent users × 3 turns/min × $0.003/turn (Claude Sonnet input-heavy) = ~$54/hour. 24/7 = ~$1,300/day for 100 concurrent. Not sustainable for a hobby or low-tier product.

**Why hard:** Real economics, not solvable by engineering alone.

**Known mitigations:**
- Tier the quality: cheap/local model for small-talk, premium for quest moments
- Aggressive caching (identical NPC greeting, cached)
- BYOK tier (users pay their own LLM costs)
- Prompt-caching on providers that support it (Anthropic, OpenAI)

**Notes:** Bring this into alignment with `103_PLATFORM_MODE_PLAN.md` tier model before any implementation decision.

### D2. Tier viability — **PARTIAL**

**Problem:** At what tier price do the numbers work? Free tier cost per user must be near zero; paid tiers must cover their LLM spend plus margin.

**Resolved by:** Tier SHAPE + feature gating + measurement protocol locked now; exact prices and budget caps pending D1 measurement data.

- **D2-D1** 3-tier shape: **Free / Paid / Premium** aligned with `103_PLATFORM_MODE_PLAN`. Self-hosted is exempt (user controls infra + keys).
- **D2-D2** Free tier = **BYOK-only** (user supplies LLM keys). Zero platform marginal LLM cost for free users.
- **D2-D3** Unit economics target: `tier_price/month ≥ 1.5 × (cost_per_user_hour × avg_hours_played/month)`. Below 1.0x → insolvent; 1.0-1.5x → review.
- **D2-D4** Feature gating per tier (Free: frozen tick B3-D1 / manual fork MV4-b / Reader UX M7-D2; Paid: platform-LLM budget + lazy-when-visited B3-D2 + multi-device sync + Player UX + drift SLO <2%; Premium: scheduled tick B3-D3 + premium models + 5+ PC slots PC-C1 + Author UX + drift SLO <0.5%).
- **D2-D5** V1 measurement protocol: solo-RP prototype instruments cost per session / hour by G2-D4 script mix; output feeds D1 → break-even math.
- **D2-D6** Exact pricing + monthly budget caps **deferred to post-V1 data**. D2 locks framework; numbers require D1 + market research.

Decisions D2-D1..D6 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN`:**
- Exact monthly prices per tier (depends D1)
- Monthly budget cap values per tier (depends D1 + session-volume projection)
- Tier renaming / positioning per market research

### D3. Self-hosted vs platform — **ACCEPTED**

**Decision:** LoreWeave supports both. Self-hosted = user's own LLM keys, no cost to platform. Platform = tier-bounded usage.

**Notes:** MMO only makes sense in platform mode (requires shared server). Self-hosted MMO is a contradiction — one user.

---

## E. Moderation, safety, legal

### E1. Prompt-injection filtering — see A6.

### E2. NSFW / abuse control — **PARTIAL**

**Problem:** Users will attempt NSFW content, harassment, coordinated abuse.

**Known approaches:** Content filter at input + output, user reporting, shadow-ban, opt-in NSFW mode with age verification (platform dependent).

**Notes:** Industry standard. Expensive to operate but not technically novel.

### E3. IP ownership — **OPEN**

**Problem:** Book IP belongs to author. Players in the world create stories. Who owns:
- The transcript of a player's session?
- A character a player created within someone else's book?
- Stories where two players' characters interact?

**Why hard:** Genuine legal uncertainty, varies by jurisdiction, no settled precedent for LLM-mediated collaborative fiction.

**Notes:** Needs explicit ToS + licensing model before platform-mode launch. Fanfic-platform case law (Archive of Our Own, Wattpad) is the closest precedent.

### E4. DMCA / takedown workflow — **KNOWN PATTERN**

**Problem:** Standard platform obligation.

**Notes:** Not novel. Defer to platform-mode phase.

---

## F. Content design

### F1. Locked beliefs vs flexible behaviors — **PARTIAL**

**Problem (original):** Author wants "Elena is the villain of act 3." But in play, if a player charms Elena she might become an ally. Canon is violated.

**Resolved by:** Four-layer canon model in [03 §3](03_MULTIVERSE_MODEL.md). Author tags each belief/attribute with a `canon_lock_level`:
- **L1 (axiomatic)** — never drifts in any reality; globally enforced. Use for cosmic truths ("magic exists"), not personality.
- **L2 (seeded)** — default. Starts true, can drift per reality. Use for "Elena is the villain" — true in canon-faithful realities, free to diverge in "what-if" realities.
- **L3/L4** — emergent, per-reality. Not author-tagged; emerges from play.

Players "bending" Elena happens naturally in a divergent reality; canon-faithful realities keep her villainous. Both are valid.

**Residual `OPEN`:** runtime enforcement mechanism for L1 (prompt discipline + output filter), UI for authors to set lock levels per attribute, combat against prompt injection that tries to bend L1 facts (see A6).

### F2. AI GM layer — **ACCEPTED (research frontier)**

**Problem:** A good tabletop GM tracks tension, throws complications, calls for skill checks, rewards clever play. LLM NPCs alone don't do this — they just respond.

**Why hard:** Open research area. Generative Agents (Park et al., arXiv:2304.03442) came closest with "reflection + planning" but for simulation, not for human-paced narrative.

**Accepted stance (2026-04-23):** A dedicated "GM agent" that watches the story and nudges pacing + complications is open research. No productive design can happen without prototype data. **V1 pragmatic workaround**: F3 quest scaffolds (author-authored beats) + NPC-driven scenes + canon-scoped retrieval (A6-D3) cover the "game needs structure" need at the scaffold layer; there is no dedicated GM agent in V1-V2.

**Revisit trigger:** V3+ roadmap review, OR if public research delivers a validated multi-agent narrative planner. Track: Generative Agents successors, tabletop-RPG-LLM research, agent orchestration frameworks.

**Residual — no longer blocks design:** GM agent is an "aspirational feature layer"; V1-V2 will ship without it, using scaffolds (F3) for structure. Closely linked to C2 narrative pacing; they'll likely be solved together if at all.

### F3. Quest design — emergent or scripted — **PARTIAL**

**Problem:** Quests can be (a) scripted (author writes them, LLM colors them in), (b) emergent (LLM invents quests from world state), or (c) hybrid.

**Why hard:** Scripted = consistent but not novel; emergent = novel but often nonsensical. Hybrid is the goal but the seam is subtle.

**Resolved by:** Hybrid scaffold + LLM fill-in framework, with emergent deferred to V3+ for quality control:

- **F3-D1** — quest scaffold schema (V1-V2): structured `trigger` + `beats` (typed: player_choice / location_visit / skill_check / dialogue / combat) + `outcomes` (success/failure branches with rewards + world_effect). Author-authored via `world-service` admin UI.
- **F3-D2** — LLM fill-in at runtime: scene descriptions, NPC dialogue (persona-constrained), player-choice text reflecting world state. Combat mechanics deterministic (R7 + world-service); LLM narrates outcome.
- **F3-D3** — quest sources V1/V2: (a) author-authored scaffolds, (b) book-canon extraction (V2 — knowledge-service surfaces unresolved tensions as candidates for author review).
- **F3-D4** — emergent quest generation = **V3+ opt-in**. LLM drafts scaffold from timeline tensions; **author/admin review before surfacing to players** (anti-quality-drift). Feeds DF1 Daily Life.
- **F3-D5** — discovery mechanisms: proximity (NPC triggers in player region), rumor propagation, explicit quest board (V2+ MMO). All 3 opt-in per World Rule.
- **F3-D6** — player-created quests = **V3+** with canon-lock constraints (L1 axioms unchangeable); author opts-in per book.

Decisions F3-D1..D6 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN`:**
- Scaffold schema evolution — beat types (do we need more? are some unused?) — V1-V2 playtest
- Emergent quest generation prompt quality — V3 prototype
- Author review tooling for emergent quests — DF4-adjacent detail

### F4. Progression system — **ACCEPTED SCOPE**

**Stance:** Minimal RPG mechanics. Inventory + relationships + optional simple stats. No complex combat, no skill tree. The game is the conversation, not the mechanics.

**Notes:** Scope discipline. Resist pressure to add D&D-style systems.

---

## G. Testing & operations

### G1. CI for non-deterministic LLM flows — **PARTIAL**

**Problem:** Unit tests assume determinism. LLM output varies. Regression test suites become flaky or meaningless.

**Resolved by:** 3-tier testing framework in [`05_qa/LLM_MMO_TESTING_STRATEGY.md §2`](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#2-g1--ci-for-non-deterministic-llm-flows):

- Tier 1 (G1-D1) — unit tests with frozen mock LLM (prompt-hash keyed fixtures; <1s; per-PR)
- Tier 2 (G1-D2) — nightly integration on cheap real LLM (~30 scenarios, 85% pass-rate threshold)
- Tier 3 (G1-D3) — weekly LLM-as-judge scorecard (Sonnet/GPT-4.1 grading rubric dimensions vs baseline)
- Fixture maintenance via `admin-cli regen-fixtures` with mandatory human review (G1-D4)
- Canonical scenario library at `docs/05_qa/LLM_TEST_SCENARIOS.md` (G1-D5)

Decisions G1-D1..D5 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN`:** rubric dimension weights, judge-model bias calibration — V1 tuning.

### G2. Multi-user load/simulation testing — **PARTIAL**

**Problem:** How to load-test an MMO with LLM in the loop? Real LLM costs real money; mocked LLM doesn't exercise real latency/failure modes.

**Resolved by:** Tiered load matrix in [`05_qa/LLM_MMO_TESTING_STRATEGY.md §3`](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#3-g2--multi-user-load--simulation-testing):

- Tier 1 (G2-D1) — mocked LLM at 1000 concurrency for pipeline stress, hourly
- Tier 2 (G2-D2) — real LLM at 10-20 concurrency for latency/throughput, daily on staging
- Tier 3 (G2-D3) — full-stack pre-production (V1 50/$50, V2 200/$200, V3 1000/$1000), weekly
- New service `loadtest-service` with script library (casual / combat / fact / jailbreak) (G2-D4)
- Admin auth + hard budget kill-switch for real LLM runs (G2-D5)

Decisions G2-D1..D5 locked 2026-04-23.

**Residual `OPEN`:** script library coverage breadth, target-scale rebalancing — V1 playtest.

### G3. Canon-drift detection in production — **PARTIAL**

**Problem:** In live play, NPC may say things that contradict canon. How to detect and alert?

**Resolved by:** 5-layer detection + feedback loop in [`05_qa/LLM_MMO_TESTING_STRATEGY.md §4`](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#4-g3--canon-drift-detection-in-production):

- Layer 1 (G3-D1) — async post-response lint against knowledge-service oracle, logs to `canon_drift_log`
- Layer 2 (G3-D2) — user "that's not right" button with categorized reports + per-NPC aggregation
- Layer 3 (G3-D3) — per-reality drift dashboard in DF9 with alert thresholds
- Layer 4 (G3-D4) — auto-remediation (memory regen, persona rotation, temporary NPC suspension on severe drift)
- Layer 5 (G3-D5) — feedback loop: production drifts → G1 adversarial fixtures (human-curated promotion)
- Per-tier SLOs (G3-D6): free <5%, paid <2%, premium <0.5%

Decisions G3-D1..D6 locked 2026-04-23.

**Residual `OPEN`:** drift-detection LLM overhead cost per session, adversarial fixture auto-generation quality — V1 measurement.

---

---

## M. Multiverse-model-specific risks

New category introduced by the multiverse model in [03_MULTIVERSE_MODEL.md §11](03_MULTIVERSE_MODEL.md). These are trade-offs created by adopting peer realities + snapshot fork; they are the price of the benefits elsewhere.

### M1. Reality discovery problem — **PARTIAL**

**Problem:** Many realities per book → which does a new player join? Poor discovery = every reality is lonely. Related to C3 cold-start.

**Resolved by:** 7-layer design in [03 §9.1](03_MULTIVERSE_MODEL.md#91-reality-discovery) — smart-funnel entry flow, composite ranking (friend presence / density / locale / canonicality / recency / near-cap penalty), friend-follow via auth-service, creator-declared canonicality hint, flat browse UI with filters, create-new gated behind "Advanced" tab, metrics feedback loop for weight tuning. Decisions M1-D1..D7 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN` (blocks SOLVED):**
- Actual weight values — V1 defaults are starting guesses; tune from real data
- Notable-event preview format (raw L3 headline vs AI 1-line summary) — needs engagement measurement
- First-week cold-start interaction with C3 (seeded AI populations?)
- Preview-content caching freshness policy

### M2. Storage cost of inactive realities — **PARTIAL**

**Problem:** Users fork freely, abandon 30 minutes later → DB rows accumulate across thousands of inactive realities.

**Resolved by:** All mitigation layers locked — MV10 (30d auto-freeze), MV11 (90d auto-archive), R9-L6 (soft-delete via rename with 90d hold), MV4-b (V1 no fork quota; platform-mode tier quota deferred), M1-D5 (hibernated/frozen hidden from discovery). Status **MITIGATED in [03 §11.M2](03_MULTIVERSE_MODEL.md#m2-storage-cost-of-many-inactive-realities--mitigated)**; kept `PARTIAL` in 01 for residual platform-mode tier detail.

**Residual `OPEN`:**
- Platform-mode fork-quota tier specifics — deferred to `103_PLATFORM_MODE_PLAN.md`
- Compression thresholds for long-term archived events — V3+ tuning

### M3. Canonization contamination — **PARTIAL**

**Problem:** Canonization (L3 → L2, author-gated per MV2) opens a path for emergent player narrative to influence canon. Risks: pollution, social pressure on author, accidental breaks, IP uncertainty, low-quality promotions, player consent, system gaming. Related to E3 IP ownership and gated by DF3 for full implementation.

**Resolved by:** 8-layer safeguard framework in [03 §9.7](03_MULTIVERSE_MODEL.md#97-canonization-safeguards--m3-resolution) — author-only trigger, mandatory diff view with cascade impact, event eligibility + per-PC consent gates, harder L2 → L1 promotion gate (R9 pattern), 90-day undo window, attribution metadata, distinguishability in book content, explicit scope fence with DF3 and E3. Decisions M3-D1..D8 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN` (blocks SOLVED):**
- "Significant event" category definitions per World Rule (DF4 + V1 data)
- >90-day compensating-write mechanism (DF3 implementation detail)
- Export attribution UI format (strip / footnote / appendix) — DF3 detail
- Edge cases: deleted PC / banned user / retroactive opt-out — DF3 policy
- **E3 (IP ownership)** — independent legal blocker for platform-mode launch; self-hosted mode exempt

### M4. Inconsistent L1/L2 updates across reality lifetimes — **PARTIAL**

**Problem:** Author edits L2 after realities exist. Cascade rule says overriding realities' L3 events win → author's change doesn't apply there. Confuses authors expecting "my change applies everywhere."

**Resolved by:** 6-layer author-safety UX in [03 §9.8](03_MULTIVERSE_MODEL.md#98-canon-update-propagation--m4-resolution) — cascade-impact preview before edit, default passive read-through, optional force-propagate with 3-gate consent (opt-in + owner consent + R13 audit), louder L1 warnings with conflict listing, reuse of locked R5-L2 xreality channels, glossary entity change timeline. Decisions M4-D1..D6 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN` (blocks SOLVED):**
- Compensating L3 event schema specifics — DF3-adjacent
- Notification copy per M7 `UI_COPY_STYLEGUIDE.md`
- Consent mechanism for ownerless / abandoned realities — governance policy
- Runtime canon-guardrail prompt discipline for L1 enforcement — A6-adjacent

### M5. Fork depth explosion — **PARTIAL**

**Problem:** Snapshot fork allows forks of forks of forks → deep ancestry chains → cascading read across N reality_ids at load time.

**Resolved by:** MV9 auto-rebase at depth N=5 (flatten ancestor chain into fresh-seeded reality with inherited snapshot), projection-table cascade flattening at read ([03 §7](03_MULTIVERSE_MODEL.md)), ops metrics per shard including ancestry depth (R4-L5). Status **MITIGATED in [03 §11.M5](03_MULTIVERSE_MODEL.md#m5-fork-explosion-depth--mitigated)**; kept `PARTIAL` in 01 for threshold tuning.

**Residual `OPEN`:**
- N=5 depth threshold — V1 starting value, tune from ops data on real chain behavior

### M6. Cross-reality analytics — **KNOWN PATTERN**
"Alice is alive in how many realities?" requires scan across reality_registry + projection rows. ETL to ClickHouse for analytics. Pattern is standard; cost is real but predictable.

### M7. Concept complexity for users — **PARTIAL**

**Problem:** Multiverse is sophisticated. New users may not understand "realities" on first contact → churn.

**Resolved by:** 5-layer progressive disclosure in [03 §9.6](03_MULTIVERSE_MODEL.md#96-progressive-disclosure--m7-resolution) — user-facing terminology map (reality → timeline, NPC → character, L1 → "world law", etc.), 3-tier user model (Reader / Player / Author) with soft upgrade triggers, 4-step onboarding tutorial, copy style guide at [`docs/02_governance/UI_COPY_STYLEGUIDE.md`](../../02_governance/UI_COPY_STYLEGUIDE.md), contextual tooltips on canonicality/fork/hibernated/friend/forked-from. Decisions M7-D1..D5 locked 2026-04-23 in [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Residual `OPEN` (blocks SOLVED):**
- Tutorial copy A/B testing — which phrasing reduces bounce rate on real users
- Tier-upgrade trigger thresholds (3 sessions default, may tune per intent signal)
- Word choice at Reader tier: "world" vs "book" vs "story" for source material
- Tooltip wording refinement per locale

---

## Status summary

| Category | OPEN | PARTIAL | KNOWN PATTERN | ACCEPTED |
|---|---|---|---|---|
| A. LLM reasoning & grounding | 0 | 6 | 0 | 0 |
| B. Distributed systems | 0 | 3 | 3 | 0 |
| C. Product / UX | 0 | 4 | 0 | 1 |
| D. Economics | 1 | 1 | 0 | 1 |
| E. Moderation & legal | 1 | 1 | 1 | 0 |
| F. Content design | 0 | 2 | 0 | 2 |
| G. Testing & ops | 0 | 3 | 0 | 0 |
| **M. Multiverse-specific** | **0** | **6** | **1** | **0** |
| **Total** | **2** | **26** | **5** | **4** |

> **Note:** Counts accurate as of 2026-04-23. Reconciled pre-existing off-by-one baseline miscounts discovered during M and A batch resolutions (the M OPEN baseline was 4 not 3; the A OPEN baseline included A2 which had already moved to PARTIAL via the multiverse reframe). M1/M2/M3/M4/M5/M7 all `PARTIAL` in 01; M6 `KNOWN PATTERN`. M2/M3/M4/M5 additionally marked **MITIGATED in [03 §11](03_MULTIVERSE_MODEL.md)**; stay `PARTIAL` in 01 due to residual sub-items pending V1 data or external input. All A1–A6 now `PARTIAL` after the LLM Safety Layer ([05](05_LLM_SAFETY_LAYER.md)) resolution.

**Deltas across design rounds:**
- A1 `OPEN` → `PARTIAL` (R8 [§12H](02_STORAGE_ARCHITECTURE.md) resolves infrastructure; semantic layer still open)
- A2 `OPEN` → `PARTIAL` (multiverse reframes cross-player consistency as a feature)
- B5 `OPEN` → `PARTIAL` (event sourcing + snapshot fork + DB-per-reality give rollback)
- C4 `OPEN` → `PARTIAL` (four-layer canon resolves the tension)
- F1 `OPEN` → `PARTIAL` (canon_lock_level per attribute)
- New category M added with 7 multiverse-specific risks
- **M1 `OPEN` → `PARTIAL`** (2026-04-23 — 7-layer discovery design in [03 §9.1](03_MULTIVERSE_MODEL.md#91-reality-discovery); weight tuning + preview format pending V1 data; M1-D1..D7 locked in [OPEN_DECISIONS.md](OPEN_DECISIONS.md))
- **M7 `OPEN` → `PARTIAL`** (2026-04-23 — 5-layer progressive disclosure in [03 §9.6](03_MULTIVERSE_MODEL.md#96-progressive-disclosure--m7-resolution); tutorial A/B + tier thresholds pending V1 data; M7-D1..D5 locked + new governance doc `UI_COPY_STYLEGUIDE.md`)
- **M3 `OPEN` → `PARTIAL`** (2026-04-23 — 8-layer canonization safeguards in [03 §9.7](03_MULTIVERSE_MODEL.md#97-canonization-safeguards--m3-resolution); M3-D1..D8 locked. Framework-level TECHNICAL + UX safeguards; DF3 implements; E3 legal review remains an independent platform-mode launch gate — self-hosted exempt)
- **M4 `OPEN` → `PARTIAL`** (2026-04-23 — 6-layer author-safety UX in [03 §9.8](03_MULTIVERSE_MODEL.md#98-canon-update-propagation--m4-resolution) reusing locked R5-L2 xreality infrastructure; M4-D1..D6 locked)
- **M2 `PARTIAL` → `MITIGATED`** in 03 only (2026-04-23 — all mitigation layers locked: MV10/MV11/R9-L6/MV4-b/M1-D5 cohesive)
- **M5 `PARTIAL` → `MITIGATED`** in 03 only (2026-04-23 — MV9 auto-rebase + projection flattening + ops metrics cohesive)
- **M category batch fully closed** (2026-04-23 — M1/M7/M3/M4 all moved to `PARTIAL`; M2/M5 confirmed MITIGATED in 03; M6 KNOWN PATTERN unchanged)
- **A3 `OPEN` → `PARTIAL`** (2026-04-23 — World Oracle pattern in [05 §4](05_LLM_SAFETY_LAYER.md); A3-D1..D4 locked. Deterministic fact-question routing via `oracle.query()` with pre-computed categories + PC timeline-cutoff; miss → LLM fallback + audit flag)
- **A5 + A6 framework formalized** (2026-04-23 — A5 / A6 remain `PARTIAL` status-wise but their architecture is now locked via [05 §3 command dispatch + §5 5-layer injection defense](05_LLM_SAFETY_LAYER.md); A5-D1..D4 + A6-D1..D5 locked)
- **A category batch fully closed** (2026-04-23 — A1/A2/A3/A4/A5/A6 all `PARTIAL`; no fully OPEN items remain in A)
- **B3 `OPEN` → `PARTIAL`** (2026-04-23 — 3-mode tick framework (frozen V1 / lazy-when-visited V2 / scheduled V3), per-reality configurable, budget-capped; B3-D1..D5 locked)
- **C1 `OPEN` → `PARTIAL`** (2026-04-23 — 3-voice modes (terse / novel / mixed) with inline override + world-rule override + persistence; V1 default = mixed; C1-D1..D5 locked)
- **F3 `OPEN` → `PARTIAL`** (2026-04-23 — hybrid scaffold + LLM fill-in; emergent deferred to V3+ with author review; F3-D1..D6 locked)
- **B category batch fully closed** (2026-04-23 — B3 moves to PARTIAL; no fully OPEN items remain in B)
- **G1 `OPEN` → `PARTIAL`** (2026-04-23 — 3-tier CI framework in new [`05_qa/LLM_MMO_TESTING_STRATEGY.md §2`](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#2-g1--ci-for-non-deterministic-llm-flows); G1-D1..D5 locked)
- **G2 `OPEN` → `PARTIAL`** (2026-04-23 — tiered load matrix + `loadtest-service` + budget kill-switch in [`05_qa §3`](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#3-g2--multi-user-load--simulation-testing); G2-D1..D5 locked)
- **G3 `OPEN` → `PARTIAL`** (2026-04-23 — 5-layer drift detection + per-tier SLOs in [`05_qa §4`](../../05_qa/LLM_MMO_TESTING_STRATEGY.md#4-g3--canon-drift-detection-in-production); G3-D1..D6 locked)
- **G category batch fully closed** (2026-04-23 — G1/G2/G3 all PARTIAL; no OPEN remaining)
- **C3 `OPEN` → `PARTIAL`** (2026-04-23 — product strategy locked: V1 solo-first, NPC-populated world, staged funnel, scheduled events V2+, friend-follow organic concentration; C3-D1..D6 locked. Largely dissolved by earlier multiverse + M1 + M7 decisions.)
- **D2 `OPEN` → `PARTIAL`** (2026-04-23 — 3-tier shape (Free BYOK / Paid / Premium) + 1.5x margin target + per-tier feature gating mapped to B3/M1/M7/PC-C1 + V1 measurement protocol locked; D2-D1..D6 locked. Exact prices pending D1 data.)
- **C2 `OPEN` → `ACCEPTED` (research frontier)** (2026-04-23 — AI-driven narrative pacing is open research. V1 pragmatic workaround via F3 quest scaffolds for structural pacing at scene level; small-talk allowed to drift. Revisit V2+ with prototype data or public research progress.)
- **F2 `OPEN` → `ACCEPTED` (research frontier)** (2026-04-23 — dedicated AI GM agent is open research (Generative Agents partial). V1-V2 ships without GM agent; F3 scaffolds + NPCs + A6 retrieval cover the structural need. Revisit V3+ or on research delivery.)

**Final interpretation (2026-04-23 session close):** Systematic design resolutions have compressed the OPEN set from 18 → **2**. Every multiverse-specific, LLM reasoning, distributed-systems, testing/ops, and most product / economics / content-design risk now has either a PARTIAL answer or an explicit ACCEPTED stance. The design track has reached **steady state**:

- **Remaining 2 OPEN** (critical-path external blockers):
  - **D1** cost per user-hour — V1 prototype measurement
  - **E3** IP ownership — legal review (platform-mode launch gate; self-hosted exempt)
- **Also critical-path but already PARTIAL:** A4 retrieval quality — V1 measurement on real LoreWeave books
- **ACCEPTED research frontier (2):** C2 narrative pacing, F2 AI GM layer — V1-V2 ship without these; revisit on research or prototype trigger

Categories fully closed: **M · A · B · G**. **No productive design batches remain.** Next meaningful movement requires: (a) V1 prototype build + instrumented measurement (for A4 / D1 and tier pricing fill-in), (b) legal counsel engagement (for E3 and canonization launch gate), or (c) upstream research results (for C2 / F2 revisit). See [SESSION_HANDOFF.md](SESSION_HANDOFF.md) for the detailed closure brief and external-dependency action list.

## What "ready to implement" would look like

Before converting this into a real design doc with governance sign-off:

- **A1 (NPC memory)** has a concrete plan with a bounded per-reality memory budget
- **A4 (retrieval quality)** moves to `PARTIAL` with measurable evaluation on a real LoreWeave book
- **D1 (cost)** has real numbers from V1 prototype — cost per user-hour is measured, not estimated
- **E3 (IP)** has legal review of a proposed ToS model (canonization flow makes this more urgent)
- **M1–M7** have default policies confirmed (currently defaults are applied but pending user confirmation — see [OPEN_DECISIONS.md](OPEN_DECISIONS.md))

Until A1/A4/D1/E3 move off `OPEN`, Shape D (persistent MMO) is not ready for design. Shape A (solo RP within a single reality) sidesteps A2/C4/F1 entirely and could ship earlier — its critical-path `OPEN` list is **A1 + A4 + D1**.
