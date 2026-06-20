# 00 — Vision: LLM-Driven 2D / 2.5D MMO RPG

> **Status:** Exploratory. Captured from a design conversation on 2026-04-23.
> **Purpose:** Preserve the intent so later sessions can resume from the same starting point.

---

## 0. Medium & client (CANONICAL — added 2026-06-20, supersedes all "text-based" framing)

> **This is a rendered 2D / 2.5D MMO RPG — NOT a text/chat game.** Earlier drafts of this
> track (and ~47 docs) described a "text-based MMO" with an "extended chat GUI." That framing
> is **wrong and dangerous**: it leads a reader to build a SillyTavern-style chat client instead
> of a game client. The correct medium:
>
> - **World & movement** — a spatial **2D / 2.5D world** rendered in a game client. Players
>   control an on-screen avatar on a tilemap; other players and NPCs are visible and move in
>   **near-realtime** (server-authoritative position, client-predicted).
> - **Combat** — **turn-based**, resolved server-side deterministically (seeded RNG).
> - **LLM text is a SUB-LAYER, not the medium** — NPC dialogue, narration of outcomes, and
>   player↔player chat are *surfaces inside* the graphical client. The glossary / knowledge-graph
>   grounding drives dialogue & narration; it does **not** make this a text MUD.
> - **Inspirations split by layer** — the world / movement / combat layer draws on graphical
>   tile-based, turn-based MMORPGs; the dialogue & narration layer draws on SillyTavern-style
>   prompt composition and MUD text discipline. The latter are **narration-layer inspirations
>   only**, never the client medium.
>
> Any doc still saying "text-based MMO" / "chat GUI" as the *medium* is stale and must be read
> through this correction. The text/chat-shaped interaction decisions (voice modes C1, multi-stream
> UI C5, command grammar PL_002, session group-chat DF05) need a reconciliation pass — they survive
> only as the **dialogue/narration sub-layer**, not as the primary interface.

---

## 1. The Dream (one sentence)

A **rendered 2D / 2.5D MMO RPG** where the world is a LoreWeave book, NPCs are LLM-driven personas grounded in the glossary + knowledge graph, players share a persistent world rendered as an explorable map — moving their avatars in near-realtime and fighting in turn-based combat — with NPC dialogue and narration driven by the LLM as a **text sub-layer inside the game client** (not a chat-only interface).

## 2. What LoreWeave uniquely brings

None of the existing players in this space have what LoreWeave already has:

| LoreWeave asset | What it enables for an LLM MMO |
|---|---|
| Knowledge graph (`knowledge-service`, in progress) | World model backbone — relationships, events, causality |
| Glossary entities (`glossary-service`) | NPC pool, item pool, location pool with authored attributes + evidence |
| Timeline (`knowledge-service`, `K19e` landed) | "What does character X know as of point T" — timeline-scoped retrieval |
| Multi-lingual pipeline (`translation-service`) | Each region can speak a different language; translation becomes an in-world mechanic |
| Provider registry + LiteLLM (`provider-registry-service`, `chat-service`) | Flexible LLM backend, BYOK or platform-managed |
| Chat infrastructure (`chat-service`, planned) | Player client foundation |
| Book canon + chapter context (`book-service`) | Immutable reference the world is derived from |

## 3. Four shapes of role-play considered

From the prior discussion, four product shapes were on the table:

| Shape | Participants | World | Notes |
|---|---|---|---|
| **A. Solo play-inside-your-book** | 1 user + N NPCs | 1 scene from a book | Canon-grounded single-player RP. Lowest risk. |
| **B. AI Co-Author / DM** | 1 user (author) + AI narrator | Free-form scenes | Closer to continuation mode. Author-tool flavor. |
| **C. Simulation engine** | Multiple AI agents; user observes | 1 scenario | Emergent narrative. High wow, hard to control. |
| **D. Shared persistent world (MMO-lite)** | Many users + many NPCs | Persistent instance derived from a book | **The dream.** Highest risk, widest white space. |

None of A/B/C is actually an MMO. Shape D is the target; A and B are plausible V1/V2 stepping stones toward it.

## 4. Why Shape D is the white space

No project known at time of writing has delivered a persistent multi-user LLM-driven world:

- **AI Dungeon / NovelAI** — single-player story, no persistent shared world
- **Character.AI / SillyTavern** — 1:1 character chat, no world, no other users
- **Inworld AI** — NPC layer for game engines, not a platform
- **Classic MUDs (Achaea, Aardwolf)** — multi-user + persistent + text, but scripted NPCs (no LLM)
- **Replika** — persistent AI companion, single character, 1:1

The combination "LLM-driven NPCs + persistent state + shared multi-user world + grounded in an authored canon" is genuinely novel. That novelty is also why it is hard — most of the interesting problems are unsolved (see `01_OPEN_PROBLEMS.md`).

## 5. Architecture sketch (for orientation only, not a design)

```
┌─────────────────────────────────────────────────────────────────┐
│  IMMUTABLE LAYER (exists / being built)                         │
│  book-service │ glossary-service │ knowledge-service            │
│  → canonical facts, entities, timeline, chapters                │
└──────────────────────────┬──────────────────────────────────────┘
                           │ read-only derivation
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  MUTABLE LAYER (new — would need 1 or 2 new services)           │
│                                                                 │
│  world-service (Go) — realtime state, regions, event bus        │
│    • world_instances  (1 book can spawn N instances)            │
│    • player_characters (user's PC in an instance)               │
│    • npc_proxies (instance-local NPC state, derived from        │
│      glossary, drifts during play)                              │
│    • world_events (log + broadcast)                             │
│    • regions (mapped from book chapters or locations)           │
│                                                                 │
│  roleplay-service (Python) — LLM orchestration                  │
│    • Prompt assembly (SillyTavern-style block composition)      │
│    • Retrieval from knowledge-service + timeline filter         │
│    • Canon-drift linter (output vs glossary)                    │
│    • NPC turn streaming                                         │
└─────────────────────────────────────────────────────────────────┘
```

Key invariant: **canon is immutable**. Players cannot corrupt `glossary-service` or `knowledge-service` through play. Any emergent story lives in `world_events` on a per-instance basis; promotion to canon is an explicit separate flow (the author decides).

## 6. Staged delivery (the only way this is credible)

Jumping straight to Shape D is not credible. A staged path:

| Stage | Target | What it proves |
|---|---|---|
| **V1 — Solo RP** | 1 user, 1 scene, N NPCs, timeline-scoped retrieval, canon-drift lint | The core LLM+knowledge+grounding loop actually works |
| **V2 — Coop scene** | 2–4 users in 1 shared scene, shared NPCs, WebSocket broadcast | Multi-user coordination, shared NPC context isolation per PC |
| **V3 — Persistent world (MMO-lite)** | Many users, regions, travel, world state persistence | Full Shape D. Requires `world-service` + distributed-systems rigor |

Each stage is a release with standalone value. V1 might be sufficient for most users; V2 might be enough to prove the social loop; V3 is the moonshot.

**Shape B (AI Co-Author)** can likely share the V1 codebase with different UI framing — essentially the same backend with a different prompt strategy.

## 7. Inspirations

> Split by layer (see §0). The world/client layer is graphical; the narration layer is text.

**World / movement / combat layer (the client medium):**
- **Graphical tile-based MMORPGs** — 2D / 2.5D rendered world, avatar movement on a tilemap, near-realtime presence of other players
- **Turn-based tactical RPGs** — discrete, server-resolved combat encounters with seeded RNG

**Dialogue & narration layer (a text sub-surface *inside* the graphical client — NOT the medium):**
- **SillyTavern** — prompt composition, character cards, world info, macros (see `../References/SillyTavern_Feature_Comparison.md`). Applies to NPC dialogue/narration only, not the primary UI.
- **Classic MUDs** — regions, exits, NPC placement, command grammar. Borrow the *world-model discipline*, not the "text-as-interface" medium.
- **Tabletop RPG play patterns** — DM + players + dice + canon, applied to AI-mediated encounters

## 8. Why this is not on the roadmap

- The open problems in `01_OPEN_PROBLEMS.md` include research-level unknowns (NPC memory at scale, temporal consistency across parallel sessions, cost economics)
- LoreWeave V1 goal is a novel-workflow platform, not a game platform — this would be a product pivot, not an extension
- Platform-mode infrastructure (`103_PLATFORM_MODE_PLAN.md`) needs to land first for any hosted multi-user product
- The failure mode of committing too early is severe: half-built MMO that poisons focus on the core novel workflow

## 9. When to revisit

Credible triggers to move from "exploratory" to "design":

- Knowledge-service is operational and retrieval quality has been measured on real books
- Platform mode (tiers, quotas, billing) is live
- A clear majority of the problems in `01_OPEN_PROBLEMS.md` have credible approaches (not full solutions, but plausible paths)
- User demand signal: existing LoreWeave users asking for interactive play with their books
- Cost-per-user-hour for LLM calls has fallen materially, or a local-model quality threshold has been crossed
