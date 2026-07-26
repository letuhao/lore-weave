# Investigation: Persistent Memory & Long-Session Continuity (grounding the flagship's guards)

**Date:** 2026-07-09 · **Branch:** `feat/context-budget-law` · **Method:** 4 parallel code-investigation
agents (persistent-memory subsystem · hot-path tool seeding · continuity/retrieval · the F3/F7/F10
guards). **Purpose:** the flagship scenario [S06](../scenarios/S06-flagship-idea-to-arc.md) asserted a set
of "must-build" long-session guards (F3/F4/F7/F10) as *guesses*. This grounds each in the actual code so
[the umbrella spec](../2026-07-09-agent-discoverability-and-workflow-architecture.md) and S06 can replace
"we should build X" with "X is BUILT / PARTIAL / ABSENT — here's the real gap."

---

## 0. Executive verdict

The user's core question — *"do we have persistent memory, is it built, and is the memory tool on the hot
path yet?"* — answered:

| Question | Verdict | One-line |
|---|---|---|
| **Is persistent memory built?** | **BUILT** ✅ | Durable, Neo4j-backed, per-user/project, recallable in fresh sessions — but it **IS the knowledge graph re-branded** (`memory_*` = a facade over the derived KG), not a separate store. |
| **Is the memory tool on the hot path?** | **NO (not reliably)** ❌ | The `knowledge` domain auto-injects everywhere, but a **~4000-token read-first budget trim** structurally drops every **write** tool (`memory_remember`, glossary/KG writes) on the ≤200K windows mid-tier models run — forcing them through the `find_tools` loop. **This is a second, concrete root cause of the reported loop.** |
| **Is long-session continuity (canon) solved?** | **PARTIAL** ⚠️ | The **read** side is robust and always-on (per-turn retrieval + a persisted `story_state` safety net + compaction that preserves a canon summary). The **write** side is missing: **no auto-capture of conversation canon**; persistence is opt-in, rate-limited, and — critically — **excluded from auto-recall by a confidence gate**. |
| **F3 output-token floor** | **PARTIAL** | Only a binary "reasoning off" (which is the session default, and the real mitigation); no reserved content floor if reasoning is ON. |
| **F7 async-job honesty** | **PARTIAL (prompt-only)** | Taught in 6 skill prompts; **zero runtime enforcement** — a weak model can still hallucinate "done." |
| **F10 compaction preservation** | **BUILT** ✅ | Atom-safe tool-pair truncation + persisted canon summary + deterministic breadcrumb + server-side `permission_mode`/pins across resume. **Already done — remove from S06's must-build.** |

**The reframe:** the flagship does **not** need a new memory system — it's built. The genuine, narrow gaps
are (1) **write tools aren't on the hot path** (the budget trim), (2) **conversation canon isn't
auto-persisted into the store retrieval already reads**, and (3) **async-honesty has no structural guard**.
Everything else the flagship worried about (retrieval, compaction, story_state) already exists.

---

## 1. Persistent memory — BUILT (but = the knowledge graph)

- `memory_search`, `memory_recall_entity`, `memory_timeline`, `memory_remember`, `memory_forget` are thin
  FastMCP shims (`services/knowledge-service/app/mcp/server.py:409-547`) over real handlers in
  `app/tools/executor.py` that read/write the **derived KG**.
- **Storage:** a "memory" fact = a durable `:Fact` node in **Neo4j** (content-hash id, idempotent,
  temporally versioned `valid_from/until` + story-ordinals; `app/db/neo4j_repos/facts.py`,
  `app/db/neo4j_schema.cypher`). `:Entity`/`:Event`/`:Passage` back the recall/timeline tools. Postgres
  holds only the confirm queue (`knowledge_pending_facts`), summaries, and project metadata.
- **Scoping:** per-`(user_id, project_id)`, **owner-only** (stricter than the grant-aware `kg_*`; memory is
  not shared with collaborators). Recallable in a fresh session — the key is durable, `session_id` is only
  used for rate-limiting.
- **It is the same substrate as glossary+KG:** glossary (Postgres) = authored SSOT; knowledge-service KG
  (Neo4j, anchored via `glossary_entity_id`) = derived layer; `memory_*` read/write that derived KG. **Not
  a third store.** The executor shares one dispatch map for `memory_*` and `kg_*`.

**Answer to "have we built persist memory or not":** **yes, fully — but understand it as "the KG is the
memory," reached either via `kg_*` (graph-flavored) or `memory_*` (memory-flavored) tools.**

## 2. Memory on the hot path — NO, the budget trim excludes writes

The transport: every agui turn ships only **`ALWAYS_ON_CORE`** (7 tools — `find_tools`, `ui_*`,
`propose_record_edit`, `confirm_action`; **no memory/kg/glossary tool is core**,
`tool_discovery.py:147-155`) **+ the surface's hot seed**. Everything else is lazy behind `find_tools`.

- **Domain auto-injection IS wired (honest):** `resolve_skills_to_inject([])` appends `"knowledge"` on every
  non-admin surface (`skill_registry.py:319-320`); `knowledge` SkillDef has `hot_domains={"knowledge"}`;
  `surface_hot_domains()` derives hot domains from injected skills (`tool_discovery.py:232-252`); `_domain_of`
  aliases `kg`/`memory`→`knowledge` (`:512-520`). So all ~45 `kg_*`/`memory_*` tools are **candidates**.
- **The trim is the failure point:** `discovery_seed_for_surface` budgets candidates at
  `HOT_SEED_TOKEN_BUDGET = 4000` tokens (`tool_surface.py:34,143-146`), **read tools first** (verb regex
  `search|list|get|read|find|…`), then writes ascending by schema size, cut at first overflow
  (`:54-83`). On a book-scoped turn the candidate set is ~90–100 tools (knowledge + glossary + story); ~4000
  tokens fits only ~10–25; **reads exhaust the budget before any write is reached.**
- **Window scaling doesn't save mid-tier models:** `scale_by_window` = `max(4000, 4000/200000 ×
  context_length)` (`budget.py:35-46`) → a ≤200K model (incl. **gemma-4-26b**) stays at the flat 4000; only
  ~1M-context models get enough headroom for writes.
- **A classifier quirk compounds it:** only `memory_search` contains a read-verb; `memory_recall_entity`
  and `memory_timeline` are *semantically* reads but fall into the deprioritized **write** bucket.

**Verdict per family (typical ≤200K window):**

| Family | On hot path? |
|---|---|
| `memory_search` | **Conditionally** (read-priority; crowded out on book/studio by the big glossary domain) |
| `memory_remember` / `memory_forget` / `memory_recall_entity` / `memory_timeline` | **MUST-DISCOVER** → `find_tools(group="knowledge")` |
| `kg_*` reads | **Conditionally** (compete with glossary reads) |
| `kg_*` writes, **glossary write tools** | **MUST-DISCOVER** |

**This is a distinct root cause of the tool-search loop, separate from `find_tools` non-determinism:** even a
correctly auto-injected domain loses its *write* tools to the trim, so the one thing a long story-building
session must do — **persist** something — always routes through the discovery dance mid-tier models loop on.

**Cheap levers (investigation only, not applied):** (a) a small **always-hot allowlist** for the handful of
write tools the co-writer needs (e.g. `glossary_propose_entities`) that bypasses the read-first trim; (b) fix
the read-verb classifier so `recall`/`timeline` count as reads; (c) give the memory/write family a **reserved
sub-budget** so ≥1 write always survives. All three are small and independent of the big Phase-2 work — and
the umbrella's `tool_list`/`tool_load` (Phase 1) is the deterministic backstop.

## 3. Long-session continuity (F4) — PARTIAL: read side built, write side missing

**Read side — EXISTS, robust, always-on:**
- Every turn, chat-service calls `build_context` unconditionally (`stream_service.py:2507` →
  knowledge-service `context/builder.py`). A project with `extraction_enabled` gets **full mode**: L1 glossary
  entities + **L2 KG facts** (intent-anchored graph walk, ≥0.8 confidence, `selectors/facts.py:158`) + **L3
  semantic passages** + rolling summaries + a passage→graph bridge, budget-trimmed, injected as the memory
  block.
- A persisted **`story_state`** safety net (`story_state.py`, `chat_session_blocks`, OCC) — a bounded
  (≤1200-tok) deterministic distillation of the grounding prefix — **survives the whole session** and projects
  when live grounding is empty.
- Compaction preserves a canon summary (see §5/F10). So **re-reading the glossary/KG each turn already
  provides durable continuity** — for facts that live in the glossary/KG.

**Write side — MISSING (the actual gap):**
- **No auto-extraction/auto-persist of conversation facts.** The only chat→store write is the explicit
  `memory_remember` tool: its own description says *"use sparingly"*, it's **rate-limited per session**, and if
  the project has `memory_remember_confirm` on it doesn't write at all — it **queues for human confirmation**
  (`executor.py:596-666`, `definitions.py:345`). Extraction pipelines run over **book chapters, not chat**.
- **The confidence gate makes even remembered facts invisible to auto-recall:** `memory_remember` writes at
  `TOOL_FACT_CONFIDENCE = 0.7`, but the automatic L2 loader defaults to `min_confidence = 0.8` and the code
  comment states tool-written facts *"never silently enter the L2 RAG loader"* (`executor.py:89-91`,
  `facts.py:435-438`). So a fact the model chose to remember is retrievable **only** via an explicit
  `memory_search` — it is **not** auto-injected next turn.
- **The recovery net is dead for local models:** evicted turns are recoverable via `conversation_search`, but a
  measured A/B found **gemma-4-26b never called it across 4 compacted runs**, so the hint is default-OFF
  (`config.py:119-128`).

**Concretely — a fact stated turn 3, needed turn 40, survives only if:** (a) it was persisted to glossary/KG
(pre-existing lore, or the model explicitly `memory_remember`'d it — and even then only auto-recalls if it
cleared the confidence gate, which tool-facts don't), (b) it's still in the un-compacted window (fragile), or
(c) it landed in the lossy compact summary (weak-model-dependent). **The durable path that actually
auto-recalls is: persist canon as GLOSSARY entities/attributes** (authored SSOT, ≥0.8, injected via L1/L2 every
turn).

**Implication for the flagship (important):** F4's guard is **not** "build persistent memory" (built) — it's
**"the co-writer persists established canon as glossary entities as the conversation establishes them."** That
is *the same action* as the flagship's cast-capture beat (Beat D, `glossary_propose_entities`). Continuity and
cast-capture are one mechanism, not two. The residual choices: whether to also **auto-capture** conversational
facts (so the model needn't remember to), and whether to **let tool-written facts into L2 auto-injection**
(lower the gate for `source_type="llm_tool_call"`).

## 4. F3 output-token floor — PARTIAL

- No reservation splitting reasoning vs content within one `max_tokens`. The only lever is **binary**:
  `reasoning_effort="none"` disables hidden thinking (`sdks/python/loreweave_llm/reasoning.py:132-138`), and the
  **session default is reasoning OFF** (`ai_settings.py:37`) — which is the real mitigation.
- `max_tokens` passes through with no floor; `token_budget.py:74` reserves window room for output (an *input*
  guard), not content-vs-reasoning.
- **Gap:** if a session turns reasoning ON with a set `max_tokens`, gemma can spend the whole cap on `<think>`
  and emit 0 chars. Low priority *because* the default is off — only matters if reasoning-on co-writer sessions
  are in scope; then add a reserved content floor / reasoning cap.

## 5. F7 async-honesty — PARTIAL (prompt-only) · F10 compaction — BUILT

**F7 — prompt-only, no enforcement.** The "started, not done" rule is taught in 6 skills (translation, jobs,
workflow, plan_forge, universal, glossary). The tool-result funnel (`tool_result_wire.py:50-58`) just
serializes whatever the tool returns; the job_id + non-terminal status *are* present in the wire, but reading
them back before claiming completion is **entirely model discretion**. No post-turn verifier, no resolver that
annotates/blocks a "done" claim against a non-terminal job. **Gap:** add a structural guard (resolver flags a
non-terminal start-job result and blocks/annotates "done", and/or forces a `jobs_get`/`*_job_status` re-read).

**F10 — BUILT, all three sub-parts** (`sdks/python/loreweave_context/compaction.py`):
- (a) tool-call/result **atoms kept whole** (`_atoms`, `_hard_truncate` drop whole atoms only) — never orphans
  a pair.
- (b) canon summary **persisted** (`chat_sessions.compact_summary`, `compact_service.py`) with a deterministic
  verbatim **breadcrumb** of numbers + proper nouns computed before the lossy summary (`extract_breadcrumb`).
- (c) `permission_mode` + pins **survive resume server-side** (`suspended_runs.py`, `_is_pinned`).
- **No fix required.** S06 §12 listing "compaction preservation" as must-build was wrong.

---

## 6. Cleared open questions & decisions

Mapped to [umbrella §7 OQ](../2026-07-09-agent-discoverability-and-workflow-architecture.md) and
[S06 §12](../scenarios/S06-flagship-idea-to-arc.md):

- **D1 — Do NOT build a new persistent-memory subsystem.** It's built (§1). The flagship's continuity uses the
  existing KG/glossary + always-on retrieval.
- **D2 — The durable continuity mechanism = persist canon as GLOSSARY entities/attributes** (auto-injected
  every turn), *not* `memory_remember` (0.7-confidence, excluded from auto-recall, rate-limited/confirm-gated).
  The flagship's F4 guard collapses into its existing Beat D (cast-capture) — continuity is a *byproduct* of
  persisting canon to the glossary, not a separate build. **Optional add-ons (new OQ):** auto-capture of
  conversation facts; and/or letting `llm_tool_call` facts into L2 auto-injection (lower the 0.8 gate for that
  source).
- **D3 — The hot-path budget trim is a first-class root cause of the loop.** Fix belongs in umbrella **Phase 0/1**
  plus a cheap immediate lever: an always-hot allowlist / reserved write sub-budget so `glossary_propose_entities`
  (and the other canon-writes the co-writer needs) survive the ≤4000-token trim on mid-tier windows; fix the
  read-verb classifier. This is independent of, and cheaper than, the Phase-2 workflow work.
- **D4 — F10 is done; drop it from the flagship must-build.**
- **D5 — F3 is adequately mitigated by the reasoning-off default**; add a reserved content floor only if
  reasoning-on co-writer sessions become in scope.
- **D6 — F7 needs a structural guard** (small): a resolver/post-turn check that blocks or annotates a "done"
  claim against a non-terminal job status. Prompt-only across 6 skills is not enough for a mid-tier model.

**Net effect on the flagship's "what must be built" (S06 §12):** shrinks materially. Of the four guards S06
flagged as new builds, **F10 is already done**, **F3 is default-mitigated**, **F4 is a read-side that already
works + a write-side that is the *same* glossary-persist the design already does** (plus two optional add-ons),
and **F7 is a small structural guard**. The dominant remaining lever is **D3 (get the write tools onto the hot
path)** — which is squarely the umbrella's discovery work, now with a concrete, measured root cause.

## 7. Key file anchors

- Memory tools/store: `services/knowledge-service/app/mcp/server.py`, `app/tools/executor.py`,
  `app/db/neo4j_repos/facts.py`, `app/db/neo4j_schema.cypher`, `app/tools/definitions.py:260-381`.
- Hot-path seeding/trim: `services/chat-service/app/services/tool_surface.py:34-83,126-246`,
  `tool_discovery.py:147-269,512-520`, `skill_registry.py:127-145,296-329`,
  `sdks/python/loreweave_context/budget.py:35-46`.
- Continuity/retrieval: `services/chat-service/app/services/stream_service.py:2429-2575`,
  `services/knowledge-service/app/context/builder.py`, `app/context/selectors/facts.py`,
  `services/chat-service/app/services/story_state.py`, `app/db/session_blocks.py`,
  `app/db/conversation_search.py`, `app/config.py:60-151`, `docs/specs/2026-07-03-context-budget-law.md`.
- Guards: `sdks/python/loreweave_llm/reasoning.py:132-138`, `app/routers/ai_settings.py:37`,
  `app/services/tool_result_wire.py:50-58`, `sdks/python/loreweave_context/compaction.py`,
  `app/services/compact_service.py`.
