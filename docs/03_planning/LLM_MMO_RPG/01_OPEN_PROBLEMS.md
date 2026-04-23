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

### A3. Determinism & reproducibility — **OPEN**

**Problem:** Same question, different answer. World state requires stable facts. If a player asks an NPC "where is the treasure?" and gets "in the cave" today, "under the bridge" tomorrow, the world is not a world.

**Why hard:** LLMs are non-deterministic by default. Temperature=0 helps but doesn't eliminate drift across model versions/providers.

**Known partial approaches:**
- **Pre-compute canonical answers** on instance creation, cache them, NPC is just a voice for a lookup.
- **Oracle pattern** — a shared "world oracle" resolves fact questions deterministically; NPCs delegate to it.
- **Facts in tool-calls, not free-text** — when player asks about a fact, LLM emits a `query_world(key)` tool call, gets the fixed answer, then narrates it.

**Notes:** Combines with A4 and A5 to solve together.

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

**Notes:**
- For critical state changes, **bypass the LLM** — the client sends a structured action (`/take map`), world-service validates and applies deterministically, then the LLM narrates the result.
- LLM-driven tool calls only for discretionary/flavor actions.
- This is standard pattern but requires UX discipline (structured commands vs free-form text).

### A6. Prompt injection & jailbreak resistance — **PARTIAL**

**Problem:** Players can inject text to break NPC persona, expose system prompt, extract other players' private context, or force NPC to reveal canon spoilers the PC shouldn't know yet.

**Why hard:** No robust defense against prompt injection exists. Mitigations are layered and leaky.

**Known approaches:**
- Separate "persona prompt" and "user input" with strong delimiters
- Output filter that checks for persona-break (NPC referring to itself as "the AI", revealing system instructions)
- Canon-scoped retrieval: NPC literally doesn't see facts outside its timeline window, so it can't spoil them
- Output moderation pass (cheaper model) to catch obvious breaks

**Notes:** Acceptable failure mode = occasional persona break, user-reportable. Catastrophic failure mode = private context leak between players. Design must ensure the second is structurally impossible (per-PC isolation at retrieval layer, not just prompt layer).

---

## B. Distributed systems

### B1. World state concurrency — **KNOWN PATTERN**

**Problem:** Two players simultaneously `/take map`. Race condition.

**Why tractable:** Standard MMO/DB problem. Optimistic concurrency (version column), deterministic first-write-wins, narrate loser's failure ("the map is gone — someone grabbed it before you").

### B2. Real-time transport (WebSocket) — **KNOWN PATTERN**

**Problem:** Players need sub-second updates when other players act or NPCs speak. Scales to thousands of concurrent connections.

**Why tractable:** Standard pattern. LoreWeave already has a plan (`70_ASYNC_JOB_WEBSOCKET_ARCHITECTURE_PLAN.md`). Reuse.

### B3. World simulation tick — **OPEN**

**Problem:** Does the world do anything when no one is playing? If yes: NPCs age, events happen, rumors spread — compute cost grows unboundedly. If no: world is frozen in time between sessions, breaks immersion.

**Why hard:** Genuine product trade-off with cost implications. No universally right answer.

**Known compromises:**
- **Lazy simulation** — when a player enters a region, compute "what happened since last visit" on-demand (bounded by a cheap LLM summarization).
- **Scheduled tick** — nightly cron that ages NPC relationships, advances plotlines, costs predictable.
- **Frozen** — between sessions, time stops. Cheapest. Least immersive.

**Notes:** This is a product decision masquerading as a technical one. Decide the desired feel first.

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

### C1. Player voice vs narrative voice — **OPEN**

**Problem:** User types `/say I hate the king`. Does the AI narrator rewrite this as "You stand and declare, voice trembling with rage, that you despise the king"? Or keep it raw?

**Why hard:** Rewrite = novelistic feel but player loses their voice; raw = chat-bot feel, breaks immersion.

**Notes:** Per-player preference toggle is an easy cop-out but might be the right answer. Alternatively: "terse mode" vs "novel mode" per session.

### C2. Narrative pacing — **OPEN**

**Problem:** Unstructured LLM small-talk devolves into infinite low-stakes conversation. Real stories have beats, rising tension, payoff. LLMs alone don't do this.

**Why hard:** Requires an "AI GM" layer above NPCs that tracks narrative tension and injects events/complications. This is close to open research.

**Notes:** Generative Agents paper (Park et al.) used "reflection" + "planning" but didn't solve pacing for a human audience. Could cheat with scripted quest scaffolds and let LLM fill in, like tabletop modules.

### C3. Cold-start empty-world problem — **OPEN**

**Problem:** An MMO is no fun with 0 other players. Day 1 of launch: no one logs in twice.

**Why hard:** Product/marketing, not technical. Solution space includes: solo-first (Shape A) onboarding that doesn't feel empty; AI "populated" NPCs that substitute for players; scheduled "events" that pull people back.

**Notes:** Maybe V1/V2 being good enough as single/coop solves this — don't need MMO-scale populations.

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

### D2. Tier viability — **OPEN**

**Problem:** At what tier price do the numbers work? Free tier cost per user must be near zero; paid tiers must cover their LLM spend plus margin.

**Notes:** Needs: measured cost per user-hour at realistic play patterns, then price modeling. V1 (solo RP) lets us measure before committing to multi-user economics.

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

### F2. AI GM layer — **OPEN**

**Problem:** A good tabletop GM tracks tension, throws complications, calls for skill checks, rewards clever play. LLM NPCs alone don't do this — they just respond.

**Why hard:** Open research area. Generative Agents came closest with "reflection + planning" but for simulation, not for human-paced narrative.

**Notes:** Possibly a separate "GM agent" above the NPCs, watching the story and nudging. Unvalidated.

### F3. Quest design — emergent or scripted — **OPEN**

**Problem:** Quests can be (a) scripted (author writes them, LLM colors them in), (b) emergent (LLM invents quests from world state), or (c) hybrid.

**Why hard:** Scripted = consistent but not novel; emergent = novel but often nonsensical. Hybrid is the goal but the seam is subtle.

### F4. Progression system — **ACCEPTED SCOPE**

**Stance:** Minimal RPG mechanics. Inventory + relationships + optional simple stats. No complex combat, no skill tree. The game is the conversation, not the mechanics.

**Notes:** Scope discipline. Resist pressure to add D&D-style systems.

---

## G. Testing & operations

### G1. CI for non-deterministic LLM flows — **OPEN**

**Problem:** Unit tests assume determinism. LLM output varies. Regression test suites become flaky or meaningless.

**Known approaches:**
- Frozen mock LLM responses for unit tests (tests the wiring, not the prompting).
- Separate "prompt regression" suite that runs against real LLM at lower cadence, flags statistical drift.
- Rubric-based LLM-as-judge evaluations of output quality over test scenarios.

**Notes:** Industry is still figuring this out. Acceptable to start pragmatic.

### G2. Multi-user load/simulation testing — **OPEN**

**Problem:** How to load-test an MMO with LLM in the loop? Real LLM costs real money; mocked LLM doesn't exercise real latency/failure modes.

**Notes:** Tiered approach — low-concurrency integration tests on real LLM (cheap), high-concurrency tests with mocked LLM (fast), periodic full-stack pre-production run at target scale.

### G3. Canon-drift detection in production — **OPEN**

**Problem:** In live play, NPC may say things that contradict canon. How to detect and alert?

**Known approaches:**
- Post-response lint pass using knowledge-service as oracle (adds latency and LLM cost)
- Async lint (non-blocking, logs drift for review, doesn't fix in-session)
- User-reportable "that's not right" button + human review

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
| A. LLM reasoning & grounding | 2 | 5 | 0 | 0 |
| B. Distributed systems | 1 | 2 | 3 | 0 |
| C. Product / UX | 3 | 2 | 0 | 0 |
| D. Economics | 2 | 0 | 0 | 1 |
| E. Moderation & legal | 1 | 1 | 1 | 0 |
| F. Content design | 2 | 1 | 0 | 1 |
| G. Testing & ops | 3 | 0 | 0 | 0 |
| **M. Multiverse-specific** | **0** | **6** | **1** | **0** |
| **Total** | **14** | **17** | **5** | **2** |

> **Note:** M batch fully closed 2026-04-23. M3 resolution reconciled a pre-existing off-by-one in the M baseline count (originally documented as 3 OPEN but actual was 4 before M1 resolution). Current counts accurately reflect: M1/M2/M3/M4/M5/M7 all `PARTIAL`, M6 `KNOWN PATTERN`. M2/M3/M4/M5 additionally marked **MITIGATED in [03 §11](03_MULTIVERSE_MODEL.md)**; they remain `PARTIAL` in 01 due to residual sub-items pending V1 data or external input.

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

**Interpretation:** Systematic design resolutions have compressed the OPEN set from 18 → 17 → 16 → 15 → 14, with every multiverse-specific risk now having at least a PARTIAL answer. Remaining single-problem-kills-product severity items: **A4** (retrieval quality — needs measurement), **D1** (cost per user-hour — needs prototype), **E3** (IP — needs legal). Critical-path list: still 3. M-category batch is **complete** — no fully OPEN items remain in M.

## What "ready to implement" would look like

Before converting this into a real design doc with governance sign-off:

- **A1 (NPC memory)** has a concrete plan with a bounded per-reality memory budget
- **A4 (retrieval quality)** moves to `PARTIAL` with measurable evaluation on a real LoreWeave book
- **D1 (cost)** has real numbers from V1 prototype — cost per user-hour is measured, not estimated
- **E3 (IP)** has legal review of a proposed ToS model (canonization flow makes this more urgent)
- **M1–M7** have default policies confirmed (currently defaults are applied but pending user confirmation — see [OPEN_DECISIONS.md](OPEN_DECISIONS.md))

Until A1/A4/D1/E3 move off `OPEN`, Shape D (persistent MMO) is not ready for design. Shape A (solo RP within a single reality) sidesteps A2/C4/F1 entirely and could ship earlier — its critical-path `OPEN` list is **A1 + A4 + D1**.
