<!-- CHUNK-META
source: 01_OPEN_PROBLEMS.ARCHIVED.md
chunk: F_content_design.md
byte_range: 23936-28604
sha256: 2216af9d945befb9c7d68f9e28f4b378a9e672828c19af77f9721e6217d133eb
generated_by: scripts/chunk_doc.py
-->

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

