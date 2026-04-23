# 00 — Vision: LLM-Driven Text-Based MMO RPG

> **Status:** Exploratory. Captured from a design conversation on 2026-04-23.
> **Purpose:** Preserve the intent so later sessions can resume from the same starting point.

---

## 1. The Dream (one sentence)

A text-based MMO RPG where the world is a LoreWeave book, NPCs are LLM-driven personas grounded in the glossary + knowledge graph, players share a persistent world, and every interaction is mediated through an extended chat GUI.

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

- **SillyTavern** — prompt composition, character cards, world info, macros, swipes, bookmarks, slash commands (see `../References/SillyTavern_Feature_Comparison.md`)
- **Classic MUDs** — text-as-interface discipline, regions, exits, NPC placement, command grammar
- **Tabletop RPG play patterns** — DM + players + dice + canon, applied to AI-mediated sessions

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
