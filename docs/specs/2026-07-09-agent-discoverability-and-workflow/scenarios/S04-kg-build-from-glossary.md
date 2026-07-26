# S04 · "Map out how everything in my world connects" — from lore to a queryable web

> Black-box scenario. The user has built up their world info and wants to see/query the connections;
> they've never heard "knowledge graph", "node", "edge", "schema", or "project".

| Field | Value |
|---|---|
| **Scenario id** | S04 |
| **Maps to umbrella workflow** | W4 (`kg-build`) — [`../2026-07-09-agent-discoverability-and-workflow-architecture.md`](../2026-07-09-agent-discoverability-and-workflow-architecture.md) §5 (builder hint only) |
| **Persona** | P2 Linh (worldbuilder) — near-zero platform knowledge |
| **Surface** | the chat, open next to my book |
| **Model under test** | `gemma-4-26b-a4b-qat` |
| **Fixture** | book Mị Đế with world info already recorded; chapters may have no prose yet |
| **Status** | ⬜ drafting |
| **Owner** | — |

## 1. Who I am (the unknown user)

- **Mental model:** I've recorded my characters, sects, techniques, and how they relate. Now I want the
  book to *understand the connections* — who's related to whom, who belongs to which sect — so I can ask
  things like "who is Lâm Uyên connected to?" I assume it can build this from what I already entered. I
  haven't written the actual chapters yet.
- **The words I use:** "map out the connections", "build the relationships", "who's connected to who",
  "use what I already entered".
- **Words I do NOT know:** *knowledge graph, node, edge, schema, template, project, extraction, benchmark.*

## 2. What I'm trying to get done

Turn the world info I already recorded into something that understands the connections, so I can ask the
book about relationships and it answers from my lore — **without me having written chapter prose yet.**

## 3. What I have / where I'm starting

- I'm in my book; it has recorded world info (characters, sects, techniques, relationships).
- My chapters are still empty (I'm planning before writing).

## 4. What I do and what I expect to see

| # | I say / do | I expect to see |
|---|---|---|
| 1 | "Use the world info I've entered to map out how everything connects." | It sets things up and tells me it's building the connections from my recorded world — in plain terms, and honestly if any part runs in the background. |
| 2 | "Go ahead." | It proceeds (confirming anything costly), and tells me what it built / that jobs are running. |
| 3 | "Who is Lâm Uyên connected to?" | It answers from my lore — her sect, relationships, etc. — or honestly says "still building, check back" if a job's not done. |

## 5. How I'll know it worked — and how I'll know it failed

- **Worked:** I can ask "who is X connected to" and get answers drawn from the world info I entered —
  **even though I haven't written any chapters.**
- **Failed:** it tells me it can only build connections **from written chapters** and mine are empty, so
  it can't (the reported dead-end — no way to use my structured lore) · it spins searching and never
  starts · it says "done, ask me anything" but every question returns nothing · it claims it finished
  while a background job is still running.

## 6. Acceptance (observable, from my chair)

- [ ] I can **ask about connections and get real answers from my recorded lore, with no chapter prose
      written** — verified by me asking a relationship question.
- [ ] I never had to know graph/schema/project jargon or supply an id.
- [ ] Costly/long steps were **flagged honestly** ("this runs in the background, I'll tell you when it's
      ready") — no false "done".
- [ ] No thrash; anything that couldn't be done was explained plainly with a real reason.

## 7. Baseline — NOT RUN 2026-07-10: **fixture must be built first** (scoped below)

Scenario JSON is authored (`scripts/eval/discoverability_scenarios/S04-kg-build-from-glossary.json`), but
running it on the wrong fixture would produce a **meaningless baseline**, so it was deliberately not run.

- **The crux:** can connections be built from **structured lore when no chapter prose exists**? A fixture
  *with* prose masks the crux entirely — the agent just extracts from chapters and the dead-end never
  surfaces.
- **Why no fixture exists (verified 2026-07-10):** every book in the dev DB with ACTIVE entities has prose
  (e.g. `019f0820` — 227 active entities, 1.5M chars). The prose-less candidates (`019e0000-…-cccc-*`) are
  synthetic seeds with **no row in `loreweave_book`** and NULL `cached_name`. The Dracula fixture used for
  S03 has 36k chars of prose and **0 active** entities (all 26 are untriaged drafts).
- **Fixture to build (buildable now — NOT an external blocker):** a fresh book (0 chapters) + adopted kinds
  (`POST /internal/books/{id}/ontology/adopt-kinds` on glossary-service :8211) + ~6 **active** entities
  incl. a `Lâm Uyên` with a sect + a relationship, so turn 3's question has a real answer. Entity creation
  goes through propose→confirm, so seed via the MCP/propose path (not raw SQL — `entity_snapshot`,
  `normalized_name` and `search_vector` are derived and easy to corrupt).
- **Note:** S04's precondition — *recorded, triaged world info* — is precisely what **S01 (❌ can't create
  categories) and S03 (❌ can't triage drafts to active)** just showed the product cannot produce. That
  chain failure is itself a finding: **today a user cannot reach S04's starting line through the product.**

## 8. Builder hint (NON-BINDING — not part of acceptance)

> Implementers only.

- "Connections" ≈ a knowledge graph built over a project with an adopted schema. Today nodes are born
  **only** from prose extraction (`kg_build_graph` over chapter text); there is **no manual/structured
  node path**, so a prose-less book can't seed a single node — the real blocker.
- **New backing capability REQUIRED (own sub-plan):** project glossary entities → graph nodes
  (e.g. `kg_project_entities_to_nodes` / `kg_place_node`), and make edge-proposal fail-fast on missing
  endpoints. Named in feedback (2026-07-09) + umbrella §5 W4 / §7 OQ4.
- Likely path once that exists: a `kg-build` workflow (project → adopt template → project-entities-to-
  nodes → build graph/wiki in background → benchmark → query), async-aware. Maps to umbrella Phase 2 +
  the new capability. Without the capability, this scenario **cannot pass** for a planning-first author —
  which is itself the finding.

## 9. Re-test gate

Re-run §4 as this user after the structured-node capability + workflow land; ✅ when relationship
questions answer from recorded lore with no prose, no jargon, honest async reporting. Save transcript.
