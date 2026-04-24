<!-- CHUNK-META
source: FEATURE_CATALOG.ARCHIVED.md
chunk: cat_04_PL_play_loop.md
byte_range: 44878-50053
sha256: 08d60efe18703c026c9ce863d818f575866602d0c820d23d476bc99d29ebceb4
generated_by: scripts/chunk_doc.py
-->

## PL — Play Loop (core runtime)

| ID | Feature | Status | Tier | Dep | Design ref |
|---|---|---|---|---|---|
| PL-1 | Session lifecycle (create, join, leave, dissolve) | 📦 | V1 | IF-1, IF-5 | **DF5 — Session feature** |
| PL-2 | Player command grammar (`/verb target [args]` MUD pattern) — deterministic dispatch, LLM narrates post-commit | ✅ | V1 | PL-1, PL-15 | [05 §3](05_LLM_SAFETY_LAYER.md#3-command-dispatch-a5), A5-D2 |
| PL-3 | Turn submission + validation | 🟡 | V1 | PL-1 | Depends on DF5 |
| PL-4 | Prompt assembly (system + canon-scoped retrieval + persona + history + sanitized user input with hard delimiters) | ✅ | V1 | NPC-2, NPC-4, PL-18, PL-19 | [05 §5.2](05_LLM_SAFETY_LAYER.md#52-layer-2--hard-delimiters-in-prompt-a6-d2), A6-D2 |
| PL-5 | LLM streaming inference | ✅ | V1 | IF-15 | Reuse [98 §6](../98_CHAT_SERVICE_DESIGN.md) |
| PL-6 | LLM tool-call allowlist (flavor-only; state mutations forbidden from LLM output) | ✅ | V1 | PL-5 | [05 §3.3](05_LLM_SAFETY_LAYER.md#33-llm-tool-calls--allowed-vs-forbidden-a5-d3), A5-D3/D4 |
| PL-15 | 3-intent classifier (command / fact question / free narrative) | ✅ | V1 | — | [05 §2](05_LLM_SAFETY_LAYER.md#2-three-intent-classifier-a5-d1), A5-D1 |
| PL-16 | World Oracle API (`oracle.query()` deterministic fact lookup) | ✅ | V1 | IF-1 | [05 §4](05_LLM_SAFETY_LAYER.md#4-world-oracle-a3), A3-D1..D4 |
| PL-17 | Oracle fact pre-computation (entity_location, entity_relation, L1_axiom, book_content, world_state_kv) + cache invalidation | ✅ | V1 | PL-16 | [05 §4.2](05_LLM_SAFETY_LAYER.md#42-pre-computed-fact-categories-a3-d2), A3-D2 |
| PL-18 | Canon-scoped retrieval (primary structural injection defense) — filter by pc_id + timeline_cutoff + reality_id BEFORE LLM | ✅ | V1 | IF-1, knowledge-service | [05 §5.3](05_LLM_SAFETY_LAYER.md#53-layer-3--canon-scoped-retrieval-a6-d3--critical), A6-D3 |
| PL-19 | Input sanitization + jailbreak-pattern detection | ✅ | V1 | — | [05 §5.1](05_LLM_SAFETY_LAYER.md#51-layer-1--input-sanitization-a6-d1), A6-D1 |
| PL-20 | Output filter (persona-break / cross-PC leak / spoiler / NSFW with soft-retry + hard-block) | ✅ | V1 | PL-5 | [05 §5.4](05_LLM_SAFETY_LAYER.md#54-layer-4--output-filter-a6-d4), A6-D4 |
| PL-21 | Per-PC retrieval isolation at DB layer (service-layer filter V1; RLS V2+) | ✅ | V1 | IF-1, knowledge-service | [05 §5.5](05_LLM_SAFETY_LAYER.md#55-layer-5--per-pc-retrieval-isolation-at-db-layer-a6-d5), A6-D5 |
| PL-22 | Player voice mode — 3 modes (terse / novel / mixed), V1 default = mixed, persisted per-book in user prefs | ✅ | V1 | PL-4, auth prefs | [01 C1](01_OPEN_PROBLEMS.md#c1-player-voice-vs-narrative-voice--partial), C1-D1/D4 |
| PL-23 | Inline voice override (`/verbatim`, `/prose`) for single turn | ✅ | V1 | PL-15, PL-22 | C1-D2 |
| PL-24 | World-Rule voice mode lock (per-reality override by author via DF4) | 📦 | V2 | PL-22, DF4 | C1-D3 |
| PL-25 | Voice mode consistency check in output filter (soft retry if terse→prose mismatch) | ✅ | V1 | PL-20, PL-22 | C1-D5; [05 §5.4](05_LLM_SAFETY_LAYER.md#54-layer-4--output-filter-a6-d4) |
| Q-1 | Quest scaffold schema (trigger / beats typed list / outcomes with rewards + world_effect) | ✅ | V1 | IF-1 | [01 F3](01_OPEN_PROBLEMS.md#f3-quest-design--emergent-or-scripted--partial), F3-D1 |
| Q-2 | Author-authored quest scaffolds via world-service admin UI | ✅ | V1 | Q-1, WA-3 | F3-D1 |
| Q-3 | LLM fill-in at runtime (scene, NPC dialogue, choice text; deterministic combat per R7/A5) | ✅ | V1 | Q-1, PL-4, PL-5 | F3-D2 |
| Q-4 | Book-canon quest seed extraction (knowledge-service surfaces tensions as candidates) | 📦 | V2 | Q-1, knowledge-service | F3-D3 |
| Q-5 | Emergent quest generation (LLM drafts from timeline) with author-review gate | 📦 | V3 | Q-1, Q-4, DF4 | F3-D4 |
| Q-6 | Quest discovery — proximity trigger (NPC in player region) | ✅ | V1 | Q-1, NPC-1 | F3-D5 |
| Q-7 | Quest discovery — rumor propagation (NPC gossip) | 📦 | V2 | Q-6, NPC-3 | F3-D5 |
| Q-8 | Quest discovery — explicit quest board (V2+ MMO) | 📦 | V2 | Q-1 | F3-D5 |
| Q-9 | Player-created quest scaffolds with canon-lock constraints (author opt-in per book) | 📦 | V3 | Q-1, DF4 | F3-D6 |
| PL-7 | Event emission + outbox publish | ✅ | V1 | IF-1, IF-6 | [02 §4.4](02_STORAGE_ARCHITECTURE.md) |
| PL-8 | Projection update (in-transaction sync) | ✅ | V1 | IF-1 | [02 §4.6](02_STORAGE_ARCHITECTURE.md) |
| PL-9 | Realtime broadcast (region subscribers see event) | 🟡 | V1 | IF-5, PL-7 | [02 §9](02_STORAGE_ARCHITECTURE.md) |
| PL-10 | Session history load (initial + pagination) | 🟡 | V1 | IF-1 | [02 §5](02_STORAGE_ARCHITECTURE.md) |
| PL-11 | Session replay (re-render past events) | 📦 | V2 | IF-1 | Available via event log; UI TBD |
| PL-12 | Swipe / regenerate variants (SillyTavern pattern) | 📦 | V2 | PL-5 | Feature comparison doc |
| PL-13 | Bookmarks / branch a session (SillyTavern pattern) | 📦 | V3 | PL-1 | Feature comparison doc |
| PL-14 | Reasoning pass-through (Claude extended thinking etc.) | 📦 | V2 | PL-5 | Feature comparison doc |

