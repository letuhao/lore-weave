# Composition Service — Vision & Concept Capture

> **Working name:** `composition-service` (provisional — renameable; avoids clashing with RAP's "authoring" which means *book → game data*).
> **Status:** CLARIFY capture — 2026-06-02. Branch `feat/composition-service`. This is **NOT a locked design**; it records the vision, the conceptual framework, the architecture direction, and the open decisions. Next phase = DESIGN spec.
> **Stable-ID prefix:** `COMP-*` (`COMP-A*` axioms · `COMP-D*` deferrals · `COMP-Q*` open questions · `AC-COMP-*` acceptance scenarios).
> **Companion research:** [`docs/research/2026-06-02-ai-novel-composition-prior-art.md`](../research/2026-06-02-ai-novel-composition-prior-art.md)
> **Companion UX + GUI draft:** [`2026-06-02-composition-studio-ux.md`](2026-06-02-composition-studio-ux.md) + [`composition-studio-mockup.html`](composition-studio-mockup.html) (open in a browser)
> **Builds on:** glossary-service (authored SSOT) · knowledge-service (graph + RAG retrieval, production) · learning-service + `loreweave_eval` SDK (judge/eval) · provider-registry + `loreweave_llm` Client (provider gateway) · the RAP isolation precedent (`docs/03_planning/REALITY_AUTHORING_PIPELINE.md`).

---

## §0 One-liner

A backend service **+ GUI** that treats a literary work as a **structured system**, and lets the **author and the AI co-create** (assisted) **and auto-generate** (autonomous) prose — grounded on LoreWeave's existing knowledge foundation (glossary + knowledge graph), gated by the existing eval/judge track, and calling LLMs only through the provider gateway.

This is the **"assisted creation"** pillar named in the platform's purpose (CLAUDE.md line 1) that has not yet been designed or built.

---

## §1 Vision (author's words, 2026-06-02)

- Treat **literature as a system** and apply systems thinking to it.
- Build **backend + GUI** for end users, on top of LoreWeave's **strong existing foundation**.
- The GUI exposes, as first-class objects, things like:
  - **diagram** (story structure / relationship / timeline views),
  - **writing style** (phong cách sáng tác),
  - **prose voice** (văn phong),
  - **genre** (thể loại),
  - **reference sources** (nguồn tham khảo),
  - … and more.
- Both the **author and the AI exploit** these structures to **continue writing**.
- This is a **very large task** → strong lean toward a **dedicated service**.

---

## §2 Conceptual framework — "is a chapter/story like code/architecture, or does literature already have a standard outline?"

**Both are true, and they are the same thing seen from two sides.** This is the founding premise of the service.

### §2.1 Literature already has "design patterns"
Centuries of craft give us reusable structural templates — these become our domain **schema/templates**:
- **Snowflake Method** (Ingermanson) — literally *top-down stepwise refinement*: 1 sentence → 1 paragraph → character sheets → expand each line to a page → scene list → prose. This is "architecture-first" applied to fiction and is the natural backbone of a generation pipeline.
- **Story Circle** (Harmon, 8 steps), **Save the Cat** (15 beats), **Seven-Point** (Dan Wells), **Hero's Journey** (Campbell) — genre-fiction frameworks.
- **Kishōtenketsu** (起承転結, 4-act East Asian) and **web-novel conventions** (cultivation / power-progression, "golden three chapters" hook, per-chapter cliffhanger) — relevant if we target serialized web-novel formats (the MMO-RPG track's cultivation realms suggest this audience exists).

### §2.2 Software gives us process discipline — and it maps ~1:1 onto the literary methods

| Software concept | Narrative equivalent |
|---|---|
| Architecture decomposition (System→Module→Class→Func) | Story → Arc → Chapter → Scene → Beat |
| Top-down stepwise refinement | Snowflake Method (1 sentence → scene list → prose) |
| Global state / database | Knowledge graph (characters, world, timeline) — **we already have this** |
| Invariant / assertion / type constraint | Canon rules ("X is dead after ch.12", "magic cannot revive") |
| Interface contract | Character voice + motivation must stay consistent |
| Declaration→use / dead code / unfulfilled promise | Chekhov's gun, setup→payoff, dangling foreshadowing |
| Unit / integration / CI gate | Beat- / scene- / arc-level quality judge — **our eval track** |
| Code review | Editor pass / continuity pass |
| Refactor | Revision: change quality, preserve "behavior" (plot) |

### §2.3 Where the analogy BREAKS (the load-bearing caveat)
Code optimizes for **correctness + determinism**. Fiction optimizes for **emotional effect + controlled surprise + subtext**. A chapter that is "perfectly correct" — mechanically hitting every beat — reads as **soulless AI slop**. That is the classic failure mode of treating fiction purely as code.

"Correctness" in fiction is multi-dimensional and partly subjective (pacing, voice, theme, emotional resonance). You cannot `assert()` these — you must **judge** them. Therefore the **eval/LLM-judge layer is not optional here; it is the core quality gate.** The architecture must constrain *continuity and structure* while leaving *prose and surprise* loose.

### §2.4 Synthesis (the system in one sentence)
- **Literary structures = schema/templates** (the "what")
- **Software decomposition = pipeline control-flow** (the "how")
- **Knowledge graph = state layer / source of truth** (continuity)
- **Eval/judge track = test suite** (quality gate)

We already own layers 1, 3, 4. The genuinely new work is layer 2 + the template library + the generation loop + the GUI.

---

## §3 Architecture direction

### §3.1 Generation is the *reverse* of extraction — and the loop closes (the flywheel)
- Existing pipeline: **`text → knowledge graph`** (extraction).
- New pipeline: **`knowledge graph → text`** (generation).
- The loop **closes**: generated chapter → extracted back into the graph → chapter N+1 can retrieve facts established in chapter N. This reuses almost the entire existing extraction + eval infrastructure.

### §3.2 Reuse map (what we do NOT rebuild)
| Capability | Reused from | Note |
|---|---|---|
| Canon retrieval (RAG) | glossary-service + knowledge-service | Read via their public/internal APIs + events — never reach into their DBs |
| LLM access | `loreweave_llm` Client → provider-registry | **Provider-gateway invariant**: no direct SDK. BYOK cloud key OR local LM Studio — same code path |
| Quality judging | `loreweave_eval` SDK + learning-service | Reuse the harness (JudgePanel, EvalSink, calibration, online consumer). **New: prose-quality judge dimensions** (coherence, voice, pacing, canon-consistency) — `judge_precision` only scores extraction today |
| Async jobs / events | outbox → worker-infra relay → Redis Streams | Long generation runs are jobs, same as translation/extraction |
| Gateway | api-gateway-bff | New `/v1` routes; FE talks relative `/v1` |

### §3.3 Multi-agent loop (generator–critic–RAG)
Roles (may be one orchestrator playing roles, not necessarily N processes):
1. **Planner / Architect** — outline + beat sheet from a chosen story-structure template (top-down).
2. **Retriever / Lore-keeper (RAG)** — pulls relevant canon from glossary + knowledge for the current scene. *(Core RAG.)*
3. **Drafter** — generates prose for one scene from beat + retrieved context.
4. **Continuity-Critic** — validates the draft against canon (= invariant check). *(Eval/judge plugs in here.)*
5. **Editor** — voice + pacing + polish.
6. **State-updater** — writes newly-established canonical facts back to the graph (closes the flywheel).

Same shape as the extraction pipeline, reversed, reusing the judge as critic.

### §3.4 Service & data
- **Dedicated service**, Python/FastAPI (language rule: Python for AI/LLM services).
- **Owns its own DB** — story plans, outlines, beat sheets, drafts/revisions, style+voice profiles, reference sources, generation-job state. Anchors to glossary entities via FK/ID, never duplicates canon content.
- Own Redis-stream / queue namespace; own `COMP-*` ID prefix.

---

## §4 No-conflict strategy (vs the MVP branches finishing in parallel)

**The codebase already has a proven isolation pattern — RAP is the living precedent** (`REALITY_AUTHORING_PIPELINE.md`): RAP-A1 = new module in a service / new bounded area, one DB, no shared-file edits; RAP-A2 = reuse chunking + LLM client + retry/cost; explicit "Does not block Phase 1–5 work"; own `RAP-*` ID prefix.

Applied here, "no conflict" has four axes:

| Axis | How we avoid it |
|---|---|
| **Git / merge** (MVP branches editing shared files) | New files + new DB; **do not edit** shared files. Only *additive* touch-points: 1 gateway route block, 1 new contract file, 1 compose service block |
| **Architecture** (invariant violations) | Honor: gateway invariant, **provider-gateway invariant** (LLM via `loreweave_llm`), Python for AI services, one-DB-per-service |
| **Data** | Read canon from glossary + knowledge via API/event; do not touch their DBs |
| **Runtime** | Own ports / queues / Redis-stream namespace + own `COMP-*` ID prefix |

---

## §5 GUI direction (high level — DESIGN will detail)

Follows the repo's **React MVC** rules (hooks=controllers, context=services, components=views; server is source of truth; no localStorage for user data).

- **Diagram views:** beat-board for the chosen story structure; character-relationship graph; timeline; **plot-thread tracker** (setup→payoff = "unfulfilled-promise" detection, the literary form of dead-code/dangling-reference analysis).
- **Config panels:** genre/structure template picker; **style + voice profile** editor; **reference sources** (comps / influences / canon docs); explicit **canon-rule / constraint** editor (the "invariants").
- **Co-writing surface:** scene drafting with a retrieved-canon side panel; accept / edit / regenerate (reuse the chat feedback + regenerate pattern already shipped in chat-service/FE).

---

## §6 Decisions & open forks

### §6.1 Resolved — 2026-06-02 architecture deep-dive (grounded in code)

| ID | Axiom |
|---|---|
| **COMP-A1** (placement) | Dedicated `composition-service` (Python/FastAPI, own DB). FE = a new **Composition tab** in `BookDetailPage` at `/books/:bookId/composition` + `features/composition/`, mirroring the glossary-tab MVC ([BookDetailPage.tsx](../../frontend/src/pages/BookDetailPage.tsx), [features/glossary/](../../frontend/src/features/glossary/)). *Resolves COMP-Q2 = dedicated service.* |
| **COMP-A2** (Work anchor) | A **Work is book-scoped** (workspace identity = `book_id`, matching `/books/:bookId`) and anchored to the **book-typed knowledge `project_id`** (`project_type='book' ∧ book_id NOT NULL`; 1:1-with-book in practice though the schema allows N:1). Composition owns ALL its own tables and **never writes `knowledge_projects`**. "Is this book a Work?" = **presence** of composition rows (marker-by-presence) — no flag on the project. |
| **COMP-A3** (no book provisioning) | **Book-first is the existing book-creation UX.** Composition never provisions books. BOTH V0 modes attach to a pre-existing book: *continue-existing* (book has content + graph) and *write-from-scratch* (= an empty book created via the normal flow). |
| **COMP-A4** (GUI) | Composition is a **workspace tab, internally a studio** (editor + diagram views + config panels). Book context via `bookId` URL param + inline React Query + `useAuth` (no new global store, matches existing tabs). Stateful sub-panels never conditionally unmounted (CSS `hidden`), per CLAUDE.md. |
| **COMP-A5** (project resolution) | Project↔book is N:1 with **unguarded creation** ([`ProjectsRepo.create`](../../services/knowledge-service/app/db/repositories/projects.py) has no dedup); the platform copes by resolving book→project via `WHERE book_id=$1 LIMIT 1` ([handlers.py](../../services/knowledge-service/app/events/handlers.py)) — *one-knowledge-project-per-book by convention, NOT enforcement*. Composition **never silently auto-creates**: (1) resolve the book's existing book-typed project **deterministically** (`ORDER BY created_at`); (2) none → **user confirm-to-create** (reuse knowledge `createProject`); (3) >1 → **select GUI** (post-V0; V0 = deterministic-pick + warn). Composition never creates a project competing with the platform's. *Supersedes COMP-Q5.* |
| *(obs)* | The platform's `LIMIT 1` book→project resolver is non-deterministic if a book ever has >1 book-typed project. Real enforcement = a partial unique index `(user_id, book_id) WHERE project_type='book' AND NOT is_archived` — **knowledge-service's call, NOT composition's** (no-touch). Logged as an optional hardening note only. |
| **COMP-A6** (context-packer) | **COMP self-packs (option b)** — verified cheaper AND cleaner, not a trade-off. `context/build`/[`full.py`](../../services/knowledge-service/app/context/modes/full.py) (~670 LOC) is chat/question-shaped (driven by `classify(message)`, renders chat `<memory>`, Q&A-tuned budget) → not reusable wholesale. The heavy retrieval is ALREADY HTTP-exposed: semantic passages via `GET /v1/knowledge/drawers/search` (K18.3 vector, [drawers.py](../../services/knowledge-service/app/routers/public/drawers.py)), spoiler-safe temporal via `GET /v1/knowledge/timeline?before_order=`, entity/relations reads, glossary `select-for-context`, summaries. **`canon_rule` lives in COMP** → the budget policy (canon-rule > present-entity state > recent prose > semantic refs > summaries) MUST live in COMP regardless. ⇒ (a) extend-knowledge = ALL of (b)'s new code **+** cross-service modify (touches the F1=0.869 chat selectors) + contract + tests + redeploy, subtracting nothing. **Resolves COMP-fork#2 = (b), zero knowledge-service change.** New code in COMP ≈ thin retrieval client (S) + the context packer/budget machine (M, the irreducible RAG core) + scene-scope selection (S–M). |

### §6.2 Still open

| ID | Decision | Options | Lean |
|---|---|---|---|
| **COMP-Q1** | Autonomy first | (a) assisted co-writing · (b) autonomous chapter gen · (c) shared spine, both on top | **(c)** shared spine, co-writing first (research-backed) |
| **COMP-Q3** | Genre/format | (a) genre-agnostic engine w/ pluggable structure templates · (b) web-novel-serial-first | **(a)** (web-novel = one template pack) || **COMP-Q4** | V0 scope | both modes (A3) + one template + RAG packer + drafter + continuity-critic + studio tab | refine at DESIGN |

---

## §7 Task sizing & workflow

- **Size: XL** (new service, new DB, new GUI, multi-system contracts, security-relevant boundary). Per CLAUDE.md: write **spec + plan**; **`/amaw` recommended** (new service boundary + multi-system contracts).
- **Phase now: CLARIFY** (this doc). **Next: DESIGN** spec → numbered planning doc once BUILD is imminent.
- LM-Studio-on-laptop constraint does **not** affect architecture or DESIGN: register a BYOK cloud key in provider-registry; the pipeline is provider-agnostic by design.

---

## §8 Next actions
1. Resolve COMP-Q1..Q4 with the author.
2. Read companion research (§ companion link) for prior-art positioning + differentiation.
3. Promote to a DESIGN spec: service skeleton, DB schema, API contract, agent-loop sequencing, glossary/knowledge/eval integration points, GUI flow.
