# Writer Persona — Use Cases & Scenarios (design-gap baseline)

**Date:** 2026-06-13
**Purpose:** Define what a **writer/author** actually does in LoreWeave, end to end, so we can
(a) **lock down missing design early** and (b) later **walk this doc as a UX/UI gap checklist**.
**Status:** BASELINE — to be reviewed/ratified, then used as the acceptance lens for writer-facing UX.

> How to use this doc: every use case has a **Status / gaps** field. "Status" is a *claim to verify*,
> not ground truth — FE components for composition exist under `frontend/src/features/composition`,
> but wiring/UX maturity is uneven. When reviewing UX/UI, walk each UC's main flow in the running app
> and confirm the flow + alternate flows actually work; log deltas against the **gaps** notes.

Related design sources (already in repo — this doc consolidates them into a writer journey, it does not replace them):
`docs/specs/2026-06-02-composition-service-vision.md`,
`docs/specs/2026-06-02-composition-requirements.md`,
`docs/specs/2026-06-02-composition-studio-ux.md`,
`docs/specs/composition-v1-design/` (T0–T5, 24 specs),
`docs/plans/2026-06-13-knowledge-fe-ux-qol-gaps.md` (the rerank/knowledge blockers found 2026-06-13).

---

## 1. Personas

### P1 — "Mai", the original-fiction author (PRIMARY)
Writes original serialized web-fiction (multi-arc, long-running). Plans loosely, drafts in flow,
hates losing continuity across hundreds of chapters. Wants AI as a **co-writer she controls**, not an
autopilot. Bilingual reach matters (publishes in one language, wants others). Mid AI-literacy: can pick
a model from a dropdown but won't read API docs or paste UUIDs.

**Top jobs-to-be-done** (from `composition-studio-ux.md §1`, restated as the writer's voice):
1. *Never contradict my world.* (continuity)
2. *Show me what the AI is using, and let me control it.* (grounding transparency)
3. *Sound like me / like this character.* (voice)
4. *Don't spoil the future the AI shouldn't know yet.* (spoiler-safe context)
5. *Keep my story bible without me maintaining it.* (auto-knowledge flywheel)
6. *Keep me in flow* — no tab-juggling to a wiki.
7. *Help me when I'm stuck.* (brainstorm / selection tools / outline)
8. *Respect my plan, but surprise me within it.*
9. *I stay the author.* (accept / edit / regenerate — never silent autonomy)

### P2 — "Linh", the worldbuilder / loremaster (SECONDARY)
Cares more about the **world bible** than prose: characters, factions, timelines, relationships, canon
rules, wiki. May build lore for a book she's translating or co-authoring. Heavy user of glossary +
knowledge graph + wiki; light user of the prose editor. Her work *feeds* P1's grounding.

### Adjacent personas — full journey out of scope, but **Day-0 covered in §4A**
The deep author journey (UC groups C–F) centers on P1/P2. The following are distinct journeys we do **not**
fully spec here — **but their first-session (newcomer) expectations are now covered in §4A**, because a real
platform is judged by who it turns away in the first 10 minutes:
- **Translator** (adapts existing works) — overlaps via translation/glossary; Day-0 = archetype **N-T**.
- **Lore seeker / reader** — consumes & queries lore, doesn't create; Day-0 = archetype **N-L**.
- **Operator/admin** — BYOK credentials, billing, providers. Creators touch this only as *setup friction*
  (see UC-30); it should be minimal and out of their way.

---

## 2. Capability map (the surfaces a writer touches)

| Area | Route / surface | Persona | Notes |
|---|---|---|---|
| Books & chapters | `/books`, `/books/:id`, ChaptersTab | P1, P2 | workspace root |
| Chapter editor + co-writer | `/books/:id/chapters/:cid/edit` + CompositionPanel | P1 | the studio |
| Outline / planner / beats | CompositionPanel tabs (Planner, Beats, Graph) | P1, P2 | structure |
| Canon rules / critic / grounding | CompositionPanel (Canon, Grounding, Threads) | P1, P2 | continuity |
| Glossary (lore entities) | `/books/:id/glossary` | P2, P1 | world bible |
| Extraction (populate glossary/graph) | extraction wizard | P2, P1 | flywheel input |
| Knowledge project / graph | `/knowledge/*` | P2, P1 | RAG backbone |
| Enrichment (fill entity gaps) | `/books/:id/enrichment` | P2 | worldbuilding assist |
| Wiki (encyclopedia) | `/books/:id/wiki` | P2, reader | reading guide |
| Chat co-writer | `/chat`, embedded CoWriterChat | P1 | brainstorm |
| Search | `/books/:id/search` (raw-search) | P1, P2 | research |
| Translation | `/books/:id/translation` | P1 (reach) | localization |
| Campaigns (auto-draft factory) | `/campaigns/*` | P1 (power) | batch ops |
| Sharing / collaboration | sharing tab, grants | P1, P2 | multi-author |
| Models / BYOK | `/settings` providers, AI Models | all (setup) | should be minimal |
| Usage / budget | `/usage` | all | cost guardrails |

---

## 3. Use cases

**Template:** `UC-ID — name` · *Actor* · *Goal* · *Trigger* · *Main flow* · *Alternates/Exceptions* ·
*Postcondition* · **Status / gaps** (the design-completeness + UX-review hook).

### Group A — Onboarding & workspace

**UC-01 — Create / import a book**
- Actor: P1/P2 · Goal: get a manuscript into the platform · Trigger: "New book" or import.
- Main flow: create book → add metadata (title, language, synopsis) → add first chapter (blank or paste).
- Alternates: import existing text (per-chapter paste); structured zip import is **deferred** (roadmap).
- Postcondition: book exists with ≥1 chapter; appears in `/books`.
- **Status / gaps:** Books CRUD shipped. *Gap:* bulk/structured import deferred — a writer arriving with
  a finished draft (50 chapters in a doc) has no good ingest path. Decide V1 minimum ingest.

**UC-02 — Set up the AI co-writer for a book**
- Actor: P1 · Goal: enable composition on a book · Trigger: open Composition tab first time.
- Main flow: CompositionPanel shows "set up co-writer" → `createWork()` → panel re-renders ready.
- Exceptions: no model registered yet → blocked (see UC-30); knowledge project not linked → degraded grounding.
- Postcondition: a `Work` exists; outline/compose tabs usable.
- **Status / gaps:** FE flow present. *Gap:* the *precondition chain* (need a model, ideally a knowledge
  project + embeddings + optionally rerank) is implicit. First-run should **surface the checklist** and
  link to fix each — today the writer hits dead ends discovered only mid-flow (see UC-30, UC-12).

### Group B — Worldbuilding / lore (P2-led, feeds P1)

**UC-10 — Build the world bible from existing text (extraction flywheel)**
- Actor: P2/P1 · Goal: auto-populate characters/locations/factions from chapters · Trigger: run extraction.
- Main flow: pick chapters + profile → run extraction → entities land in glossary + knowledge graph → review.
- Alternates: manual entity creation in glossary; enrichment to fill missing attributes.
- Postcondition: glossary populated; graph queryable; grounding has material.
- **Status / gaps:** Extraction + glossary shipped. *Gap (verified 2026-06-13):* the knowledge-project
  prerequisite chain is **blocked at the UI** — rerank model can't be registered/discovered, project
  creation asks for a raw book UUID, and some wizards overflow the viewport. See
  `docs/plans/2026-06-13-knowledge-fe-ux-qol-gaps.md`. **This UC is currently not completable by a real user.**

**UC-11 — Author/curate a lore entity by hand**
- Actor: P2 · Goal: create/edit a character/location/item/faction with attributes + evidence · Trigger: glossary.
- Main flow: create entity → set kind, attributes, aliases → attach chapter evidence → save → (optional) translate.
- Alternates: merge duplicate entities; revision history; multilingual attributes.
- Postcondition: canonical entity in glossary, anchored for grounding/wiki.
- **Status / gaps:** Glossary shipped (entities, evidence, merge, translate). *Gap to verify:* discoverability
  of "evidence" and "merge" from the writer's mental model; entity-kind taxonomy completeness.

**UC-12 — Link a book to a knowledge project (RAG backbone)**
- Actor: P2/P1 · Goal: give the co-writer semantic memory of the book · Trigger: create knowledge project.
- Main flow: create project → (optionally) bind a book → choose embedding (+ optional rerank) → build graph.
- Exceptions: must pick an embedding model; rerank optional but currently unselectable (blocker).
- Postcondition: project READY; grounding + chat memory work.
- **Status / gaps:** **Blocked** — see UC-10 gap ref. *Design gap:* "book id (optional)" needs a **book picker**;
  the embedding/rerank prerequisites need first-class guidance, not error-on-submit.

**UC-13 — Generate/maintain the wiki (encyclopedia)**
- Actor: P2/reader · Goal: human-readable articles from the graph · Trigger: wiki generate.
- Main flow: generate articles from glossary/graph → review verify flags → edit infobox → publish.
- Alternates: staleness detection flags articles when knowledge changes → refresh.
- Postcondition: wiki articles available to readers; spoiler scoping respected.
- **Status / gaps:** Wiki shipped (soft rollout). *Gap to verify:* spoiler scoping in wiki vs reader progress;
  staleness UX clarity.

### Group C — Planning & structure (P1)

**UC-20 — Plan a story with a structure template (decompose)**
- Actor: P1 · Goal: turn a premise into an Arc→Chapter→Scene→Beat outline · Trigger: Planner tab.
- Main flow: pick template (Save the Cat / Three-Act / Hero's Journey / web-novel / Kishōtenketsu) → premise
  → generate preview → edit titles/intents/tensions → **commit**.
- Exceptions: chapters already planned → 409 → "Replace" path.
- Postcondition: persisted outline tree; scenes have status (empty/outline/drafting/done).
- **Status / gaps:** FE present (PlannerView, decompose preview/commit). *Gap to verify:* template coverage
  for non-Western structures; preview-edit ergonomics; conflict/replace clarity.

**UC-21 — Navigate & edit the outline tree**
- Actor: P1 · Goal: browse and lightly reorganize structure · Trigger: Outline tab.
- Main flow: expand Arc→Chapter→Scene → drag-reorder/reparent → rename → archive/restore → set scene status.
- Alternates: corkboard / index-card view (designed, maybe not built).
- Postcondition: structure reflects intent; ordering stable (rank-based, If-Match).
- **Status / gaps:** FE present (OutlineTree). *Gap:* corkboard (T1.4) likely not built; confirm reorder UX on touch.

**UC-22 — Map scene relationships (setup → payoff / threads)**
- Actor: P1 · Goal: track foreshadowing and narrative threads · Trigger: Graph/Threads tab.
- Main flow: add scene links (setup_payoff/custom) → view scene graph → maintain thread ledger
  (promise/foreshadow/question → open/progressing/paid/dropped).
- Postcondition: open threads visible; payoffs traceable.
- **Status / gaps:** FE present (SceneGraphCanvas, ThreadsPanel). *Gap to verify:* are open-thread warnings
  surfaced at the *right* moment (e.g., when marking a chapter done with unpaid promises)?

### Group D — Drafting with AI (P1, the core)

**UC-30 — Pick the model(s) the co-writer uses**
- Actor: P1 · Goal: choose which LLM drafts prose (+ optional distinct composer model) · Trigger: model dropdown.
- Main flow: pick from registered BYOK models → (advanced) set reasoning pref off/auto/low/med/high.
- Exceptions: **no models registered** → must go register a BYOK credential first.
- Postcondition: generation uses the chosen model; cost attributed.
- **Status / gaps:** Picker present. *Gap (verified 2026-06-13):* the *registration* side is rough — rerank
  capability missing from the register form, discovery silently empty, no rerank test. The writer is dumped
  into ops-land mid-creative-flow. **Setup should be a guided, one-time, writer-friendly checklist**, not a
  prerequisite they discover by hitting an empty dropdown.

**UC-31 — Inline streaming continuation (V0 cowrite)**
- Actor: P1 · Goal: "continue from here" with live prose · Trigger: Generate (Diverge off).
- Main flow: place cursor / set guide → Generate → tokens stream into a ghost buffer → **Accept** inserts
  (durable) + critique runs, or **Discard**.
- Alternates: Regenerate; edit before accept.
- Postcondition: prose in the manuscript; AI provenance marked until edited (designed).
- **Status / gaps:** FE present (ComposeView, stream). *Gap to verify:* provenance highlight (T5.3) actually
  rendered; accept/discard keyboard ergonomics; flow preservation (no jarring tab switches).

**UC-32 — Diverge/Converge auto-draft (V1, K candidates + reranker)**
- Actor: P1 · Goal: see K alternative drafts, pick/edit the best · Trigger: Generate (Diverge on).
- Main flow: Generate → K candidates returned, reranker winner badged → author picks / inline-edits /
  regenerates with new guidance / rejects all → correction captured (pick_different/edit/regenerate/reject).
- Postcondition: chosen text inserted; correction signal logged for quality stats.
- **Status / gaps:** FE present (CandidatesView, QualityPanel). *Gap:* rerank junk-rejection depends on a
  registered rerank model → currently blocked (UC-30/UC-12). *Gap to verify:* side-by-side candidate UX on
  small screens; clarity that "reject all inserts nothing."

**UC-33 — Selection tools (rewrite / expand / describe / tone)**
- Actor: P1 · Goal: transform a highlighted passage · Trigger: select text → toolbar.
- Main flow: highlight → choose op → streamed result inline → accept/discard.
- Postcondition: passage transformed; provenance marked.
- **Status / gaps:** FE present (InlineAiLayer, SelectionToolbar). *Gap to verify:* tone/voice op presence;
  undo integration with editor history.

**UC-34 — Brainstorm with the co-writer chat**
- Actor: P1 · Goal: think through a stuck scene conversationally · Trigger: CoWriter tab / `/chat`.
- Main flow: chat grounded in book memory → "use as guide" pushes a reply into the Compose guide → switch to Compose.
- Alternates: chat can `propose_edits` (pending approval).
- Postcondition: brainstorm captured; optionally seeded into drafting.
- **Status / gaps:** FE present (CoWriterChat). *Gap:* memory mode depends on a linked knowledge project
  (UC-12 blocker) → "grounded in book memory" may degrade to generic chat silently. Surface the memory state.

### Group E — Continuity safety (P1/P2, the differentiator)

**UC-40 — Author canon rules (declarative world invariants)**
- Actor: P1/P2 · Goal: encode "X is dead after ch.12", "magic can't revive" · Trigger: Canon tab.
- Main flow: create rule → scope (world/entity/reveal_gate) → optional order window (from/until).
- Postcondition: rules feed both the context packer and the critic.
- **Status / gaps:** FE present (CanonRulesPanel). *Gap to verify:* rule authoring ergonomics for non-technical
  writers (natural-language vs structured); reveal_gate (spoiler) authoring clarity.

**UC-41 — Continuity critic gate (catch violations before accept)**
- Actor: P1 · Goal: never insert canon-breaking prose · Trigger: auto-gen runs the CanonVerifier.
- Main flow: generated text checked → violations surface in CanonGatePanel → **Revise** pre-fills guide →
  Regenerate → re-check. False positives dismissible (kept in audit).
- Exceptions: critic degraded/skipped (e.g., no model/budget) → must be **visibly** degraded, not silently off.
- Postcondition: accepted prose is canon-consistent (or knowingly overridden).
- **Status / gaps:** FE present (CanonGatePanel). *Gap:* degraded-mode visibility (don't let "0 violations"
  mean "critic didn't run"); this mirrors the project's `nil-tolerant`/silent-no-op lesson — make the gate's
  *active vs skipped* state explicit.

**UC-42 — Grounding transparency (see & control what the AI sees)**
- Actor: P1 · Goal: inspect/pin/exclude the RAG context before generating · Trigger: Grounding tab.
- Main flow: view present cast/lore/active rules/timeline-cutoff blocks → pin must-include / exclude → generate.
- Postcondition: generation used exactly the shown context; spoiler cutoff respected.
- **Status / gaps:** FE present (GroundingPanel). *Gap (critical for trust):* if knowledge project is blocked
  (UC-12), grounding is empty/weak — the panel must say *why* ("no knowledge graph linked") rather than show
  a confusing empty state. Spoiler cutoff (`before_order`) correctness is a must-verify.

**UC-43 — Spoiler-safe timeline**
- Actor: P1 · Goal: ensure the AI never knows events after the current scene · Trigger: implicit in generation.
- Main flow: context packer cuts off at the scene's order; timeline view shows the cutoff.
- **Status / gaps:** Designed (T2.3). *Gap to verify:* is the cutoff actually enforced server-side, and is it
  visible to the writer so they trust it?

### Group F — Iteration, publishing, reach

**UC-50 — Mark scene done & publish-gate a chapter**
- Actor: P1 · Goal: freeze a finished chapter to canon · Trigger: mark scenes done → publish.
- Main flow: scene status → done → when all chapter scenes done, publish-gate evaluated → publish if no
  canon_blocked violations.
- Exceptions: open threads / unpaid setups → warn? (design question).
- Postcondition: chapter canonical; triggers flywheel (UC-51).
- **Status / gaps:** FE present (publishGate). *Gap:* should unpaid foreshadow threads (UC-22) block/warn at the
  gate? Decide the gate's checklist scope.

**UC-51 — Knowledge flywheel on chapter approval**
- Actor: system (writer-triggered) · Goal: graph self-updates so next chapter has richer context.
- Main flow: approve chapter → extraction → graph update → richer grounding for chapter N+1.
- **Status / gaps:** Pipeline shipped (extraction). *Gap:* the writer should *see* "world bible updated" feedback;
  the loop is invisible today. Tie to UC-13 staleness + a flywheel panel (T4.1).

**UC-52 — Stitch scenes into a seamless chapter**
- Actor: P1 · Goal: merge done scenes into one continuous chapter · Trigger: stitch.
- **Status / gaps:** API present (stitchChapter / generateChapter B2/B3). *Gap:* confirm UI is wired; this is a
  likely "API exists, UX missing" case.

**UC-53 — Translate / localize for reach**
- Actor: P1 · Goal: publish in additional languages · Trigger: translation tab.
- Main flow: run translation jobs → review/edit versions (save edited as gold) → language-per-chapter coverage.
- Postcondition: multilingual editions; glossary translations reused.
- **Status / gaps:** Translation shipped. *Gap to verify:* round-trip with glossary translations; the
  author-as-reviewer loop ergonomics.

**UC-54 — Share / collaborate (grants)**
- Actor: P1/P2 · Goal: invite a co-author/editor with a role · Trigger: sharing.
- Main flow: grant view/edit/manage/owner → collaborator sees the same book/lore.
- **Status / gaps:** Collaboration plans exist (E0). *Gap to verify:* which services have adopted grants;
  glossary/knowledge adoption status.

**UC-55 — Batch via campaigns (power user)**
- Actor: P1 (advanced) · Goal: run knowledge→translation→verify→eval across many chapters · Trigger: campaign wizard.
- **Status / gaps:** Experimental. *Gap:* writer-facing comprehensibility (this surfaces a lot of ops concepts —
  budget, stages, eval). Decide how much a *writer* (vs operator) should see.

### Group G — Cross-cutting ops the writer can't avoid

**UC-60 — Stay within budget / understand cost**
- Actor: all · Goal: not get surprised by spend · Trigger: usage page / guardrails.
- **Status / gaps:** Usage + guardrails shipped. *Gap to verify:* is cost visible *at the point of generation*
  (per-draft estimate) or only after the fact? Writers want pre-flight cost on auto/diverge.

**UC-61 — Manage models/credentials (BYOK)** — see UC-30.
- **Status / gaps:** The single biggest *non-creative* friction wall. Treat as a guided onboarding, not a settings
  scavenger hunt. Cross-ref `docs/plans/2026-06-13-knowledge-fe-ux-qol-gaps.md`.

---

## 4. Scenarios (end-to-end journeys — the gap-walks)

Scenarios traverse multiple UCs as a real session would. Each ends with **where it breaks today**.

### S1 — "Mai starts a brand-new original novel" (greenfield, P1)
1. Creates book + first chapter (UC-01).
2. Opens Composition → prompted to set up co-writer (UC-02) → needs a model → detours to register BYOK (UC-30).
3. Plans with a web-novel template (UC-20), edits the outline (UC-21).
4. Drafts scene 1 inline (UC-31), likes diverge so switches to K-candidates (UC-32).
5. Adds a canon rule ("the protagonist hides her power") (UC-40); critic gate catches a slip (UC-41).
6. Marks scenes done, publishes chapter 1 (UC-50) → flywheel updates the bible (UC-51).
- **Breaks today:** the **setup detour (step 2)** is a cliff — empty model dropdown, ops-land. And with no
  knowledge project yet, **grounding (UC-42) and critic (UC-41) are weak/empty** but don't *say so*. A
  greenfield author has no extracted lore, so the differentiators silently underperform. **Design need:**
  greenfield grounding strategy (rules-only + as-you-write extraction) + an explicit "co-writer readiness" meter.

### S2 — "Linh builds the world bible for an existing draft" (brownfield, P2)
1. Imports/has 20 chapters (UC-01).
2. Runs extraction to populate glossary + graph (UC-10), links a knowledge project (UC-12).
3. Curates entities, merges dupes, adds canon rules (UC-11, UC-40).
4. Generates the wiki for readers (UC-13).
- **Breaks today (verified):** step 2 is **hard-blocked** — rerank unregisterable, project wants a raw book
  UUID, wizards overflow the viewport (`docs/plans/2026-06-13-knowledge-fe-ux-qol-gaps.md`). **This is the
  scenario the user is currently stuck on.** Fixing those four QoL gaps unblocks S2, which unblocks S1's grounding.

### S3 — "Mai is stuck mid-chapter" (flow rescue, P1)
1. Brainstorms in co-writer chat grounded in the book (UC-34) → "use as guide".
2. Generates a continuation (UC-31/32), uses selection tools to tighten a paragraph (UC-33).
3. Checks grounding to confirm the AI isn't using a future reveal (UC-42/43).
- **Breaks today (verify):** chat "grounded in book memory" may silently fall back to generic if the knowledge
  link is missing (UC-34 gap). **Design need:** memory-state indicator in chat.

### S4 — "Mai goes multilingual" (reach, P1)
1. Finishes an arc, runs translation (UC-53), reviews/edits gold versions.
2. Glossary translations keep names consistent across languages (UC-11).
- **Breaks today (verify):** glossary-translation reuse in prose translation; reviewer loop ergonomics.

### S5 — "Two authors co-write" (collaboration, P1+P2)
1. Mai grants Linh edit access (UC-54); Linh maintains lore while Mai drafts.
- **Breaks today (verify):** grant adoption per service (glossary/knowledge); real-time vs eventual consistency
  of shared lore.

---

## 4A. Newcomer (Day-0) expectations & first-session scenarios

> This is the section that should have existed **before any code** — the expectation-first lens. The scenarios
> above (S1–S5) are *feature-driven* (they assume the user already wants what we built). The ones below are
> **expectation-driven**: a stranger arrives with a mental model formed by other tools and a reason to be here.
> The gap between *what they expect in the first 10 minutes* and *what the platform actually does* is the
> design debt we're paying down. All four are **non-professional ("không chuyên")** — low patience for setup,
> no tolerance for jargon (embedding / rerank / extraction / knowledge project mean nothing to them).

### The "Day-0 contract"
A newcomer doesn't read docs. In ~10 minutes they must (a) understand *what this is for them*, (b) reach
*one moment of value* ("aha"), and (c) never be blocked by machinery they didn't ask about. Every archetype
below currently fails at least one of these — usually (c), at the BYOK/knowledge wall.

### Four newcomer archetypes (Day-0 variants)

| ID | Who | Came from | Their one-line reason to be here |
|----|-----|-----------|----------------------------------|
| **N-W** | Amateur writer | ChatGPT, NovelAI, Google Docs | "Help me write my story and keep it consistent." |
| **N-B** | Amateur worldbuilder | World Anvil, Notion, Obsidian, D&D/TTRPG | "Hold my world — characters, places, lore, a map — and help me grow it." |
| **N-T** | Fan translator | Google Translate, DeepL, Sugoi/MTL tools | "Translate this novel I love, consistently, chapter by chapter." |
| **N-L** | Lore seeker / reader | Fandom wikis, asking ChatGPT about a series | "Let me explore a complex world and ask questions without getting spoiled." |

---

### N-W — Amateur writer, first session

**Expects (first 10 min):** sign up → land in something like a doc → start typing → an AI "continue / rewrite"
button that just works. Assumes a free/default model or trivial key paste. Does **not** expect to configure
embeddings, build a knowledge graph, or learn what "rerank" is.

**First-session scenario (N1):**
1. Signs up, looks for "Start writing" / "New story".
2. Creates a book + chapter (UC-01), opens the editor.
3. Wants the AI to continue from the cursor (UC-31) → prompted to set up the co-writer (UC-02).
4. Hits the **model wall** (UC-30): empty dropdown → "register a BYOK provider" → ops-land.
5. If they push through, grounding/critic are empty (no lore yet) and **silently underperform**.

**Expectation gap:** the value ("AI helps me write") is gated behind 2–3 setup chores a casual writer won't
do, and the differentiators are invisible on a greenfield book. **Design needs:** try-before-config (a default
or guest model, or a "bring one key" express path); a "co-writer readiness" meter; greenfield grounding that
works from rules + as-you-write extraction (ties to §6 #1, #2). **Verdict today: fails (c), likely abandons.**

---

### N-B — Amateur worldbuilder, first session

**Expects (first 10 min):** "Create a world" → add a character, a place, a faction → see them in a list/graph,
maybe a map → ask AI to flesh out or check consistency. Thinks in **entities and relationships, not chapters**.
May have **no manuscript at all** — the world *is* the project.

**First-session scenario (N2):**
1. Signs up, looks for "New world" / "Worldbuilding".
2. Finds only "New **book**". Confused — they don't have a book, they have a world.
3. Creates an empty book as a workaround → opens Glossary → can add entities (UC-11). OK so far.
4. Wants the knowledge **graph/relationship map/timeline/world-map** views → those live behind a
   **knowledge project + extraction**, and **extraction needs chapter text they don't have**.
5. Tries to create a knowledge project → **blocked** (rerank/book-UUID/viewport QoL gaps, UC-12).

**Expectation gap (severe):** the platform is **book/prose-centric**; a prose-less worldbuilder has no first-class
home. The graph/map/relationship features — their main draw — are reachable only via a manuscript-extraction
pipeline. **Design needs:** a **worldbuilding-first mode** (a "world" container where the bible, graph, map,
relationships, and canon rules are authored *directly*, with extraction as an optional enrichment, not a
prerequisite); manual graph/relationship authoring without text. **Verdict today: fails (a) and (c) — there's
no entry point for them at all.** This is the biggest *structural* expectation gap.

---

### N-T — Fan translator, first session

**Expects (first 10 min):** paste/import a raw chapter (or whole novel) in language A → pick target language B
→ get a clean translation → edit it → keep character/term names consistent across chapters automatically.
Mental model: "MTL + a names glossary," fast and per-chapter.

**First-session scenario (N3):**
1. Signs up, looks for "Translate a novel / import raw."
2. Has 80 raw chapters in one file → **no bulk/structured import** (deferred) → must paste chapter-by-chapter.
3. Creates book, pastes chapter 1, runs translation (UC-53) → gets output, can edit → OK, the core works.
4. Wants name/term consistency → learns it depends on a **glossary**, ideally populated by **extraction +
   knowledge** (UC-10/12) → that's the **blocked, heavy** path again, and it's framed as worldbuilding, not
   "a translation term list."
5. Worries about **ownership/copyright**: the book model assumes *they* own it; they're translating someone
   else's work. Unclear what's safe to share/publish.

**Expectation gap:** core MT works, but (i) ingest of a real raw novel is painful (no bulk import), (ii) the
consistency feature they want (a simple bilingual term glossary) is buried under the worldbuilding pipeline,
and (iii) the ownership/sharing model doesn't acknowledge derivative/translated works. **Design needs:** a
lightweight **translation-glossary** path (extract just names/terms, no full graph required); a bulk raw-import
ingest; an explicit **source-vs-translation ownership** stance. **Verdict today: partial — core value
reachable, but the consistency promise and ingest are rough.**

---

### N-L — Lore seeker / reader, first session

**Expects (first 10 min):** find a series they love (or import one) → **ask questions** ("who is X?", "how are
A and B related?", "what's happened so far?") → browse a wiki / character list / timeline → **without being
spoiled past where they've read**. They **consume and query; they never create.**

**First-session scenario (N4):**
1. Signs up, looks for "Explore / browse books with lore."
2. Opens `/browse` (public catalog) → **likely empty or sparse** (cold-start: no books with pre-built lore).
3. Tries importing a book themselves → but they're a *reader*, not a builder; building the knowledge graph
   (extraction/embedding/rerank) is far beyond what they signed up for — **and it's blocked anyway**.
4. Even if a book had lore, the **spoiler model** is authored by *scene order* (author-facing), not by **how
   far the reader has read** — the seeker needs a reading-progress cutoff.
5. Wants a "ask the book" chat (UC-34) and wiki/timeline/relationship views as **read-only, spoiler-bounded**.

**Expectation gap:** there is **no reader-facing lore-exploration experience**, and even the substrate (a book
with built lore) suffers a **content cold-start** — someone has to be a builder first. The spoiler model is
the wrong axis for a reader. **Design needs:** a **read-only "ask the lore" / wiki / timeline** surface with a
**reading-progress spoiler cutoff**; seeded/demo books with pre-built lore to solve cold-start; a clear
separation of *consume* vs *create* surfaces. **Verdict today: fails (a) — the persona has no product yet.**

---

### Cross-cutting newcomer findings (the design debt to lock now)

1. **Intent-branching onboarding is missing.** All four arrive with different intents but hit the *same*
   book-centric, setup-heavy funnel. **Design:** a first-run "**What do you want to do?**" fork —
   *Write a story · Build a world · Translate a novel · Explore a world* — that routes to a tailored path,
   hides irrelevant machinery, and sets the right default container (book vs world). Strengthens §6 #1.
2. **No try-before-configure.** Every archetype dead-ends at BYOK/knowledge setup before any value. **Design:**
   a default/guest model or a one-key express path so the "aha" precedes the chores. (N-W, N-T, all.)
3. **Book-centricity excludes worldbuilders and complicates readers/translators.** The "book" is assumed as the
   root object. **Design:** a **"world" as a first-class container** (lore/graph/map/canon authored directly),
   with books/chapters as *one* kind of content inside it, not the only entry. (N-B, N-L.)
4. **Content cold-start for consumers.** N-L (and any reader) needs *someone else's* built lore to have value.
   **Design:** seeded demo worlds/books with pre-built knowledge; a path from "I read this" → "explore its lore."
5. **The spoiler model has two axes, only one is designed.** Author = **scene/outline order** cutoff;
   reader/seeker = **reading-progress** cutoff. Both must exist and be distinct. (N-L vs UC-43.)
6. **Ownership covers originals, not derivatives.** Translators and fan-creators work on works they don't own.
   **Design:** an explicit source/derivative ownership + sharing stance. (N-T.)
7. **Jargon leakage.** "Knowledge project / extraction / embedding / rerank" are implementation words exposed to
   end users. **Design:** speak the user's language ("build your world bible," "name consistency"), hide the rest.

> These seven are the "should-have-done-before-code" items the user flagged. They don't invalidate the built
> surface — they reframe its *entry points*. Recommend ratifying #1 (intent fork) and #3 (world container)
> first, since they reshape navigation that everything else hangs off.

---

## 5. Gap matrix (the UX/UI review checklist)

Legend — **Status:** S=shipped/wired · F=FE present, maturity unverified · D=designed only · ✗=blocked/missing.
Walk each row in the app during UX review; flip Status to verified S or open a defect.

| UC | Capability | Status | Top gap to design/verify |
|----|------------|:------:|---------------------------|
| 01 | Book create/import | S/✗ | bulk/structured import path for arriving drafts |
| 02 | Co-writer setup | F | surface the full precondition checklist on first run |
| 10 | Extraction flywheel | ✗ | **blocked by knowledge FE QoL gaps (2026-06-13)** |
| 11 | Manual lore entity | S | evidence/merge discoverability; kind taxonomy |
| 12 | Link knowledge project | ✗ | **book picker; embedding/rerank guided prereqs** |
| 13 | Wiki generate/maintain | S | spoiler scoping vs reader progress; staleness UX |
| 20 | Template decompose | F | non-Western templates; preview-edit ergonomics |
| 21 | Outline tree | F | corkboard (likely missing); touch reorder |
| 22 | Scene graph / threads | F | unpaid-thread warning at the right moment |
| 30 | Model pick | F | **guided BYOK onboarding, not empty dropdown** |
| 31 | Inline streaming | F | provenance highlight; keyboard flow |
| 32 | Diverge/converge | F | rerank dependency (blocked); small-screen candidates |
| 33 | Selection tools | F | tone/voice op; undo integration |
| 34 | Co-writer chat | F | **memory-state indicator (grounded vs generic)** |
| 40 | Canon rules | F | NL vs structured authoring for non-tech writers |
| 41 | Continuity critic | F | **active-vs-skipped visibility (no silent off)** |
| 42 | Grounding transparency | F | empty-state reason when no graph; pin/exclude |
| 43 | Spoiler-safe timeline | D | server-side enforcement + visible cutoff |
| 50 | Publish gate | F | gate checklist scope (threads? canon?) |
| 51 | Flywheel feedback | S/✗ | "bible updated" feedback is invisible |
| 52 | Stitch chapter | D/✗ | likely API-without-UI |
| 53 | Translation | S | glossary-translation reuse; reviewer loop |
| 54 | Collaboration grants | D | per-service grant adoption status |
| 55 | Campaigns | F | writer-vs-operator comprehensibility |
| 60 | Budget/cost | S | **pre-flight per-draft cost at generation** |
| 61 | BYOK credentials | ✗ | see 2026-06-13 QoL plan |

---

## 5A. Blocked surfaces register (framed as *missing features*, not "built wrong")

The premise here is the user's: **the architecture is sound; the platform is missing features at the
entry/seams.** Each blocker below is phrased as the *capability that's absent*, with who it stops and the
unblock order. **B = hard block** (a core journey cannot complete) · **D = degraded-invisible** (limps, but
silently wrong → erodes trust) · **S = soft** (friction, not a wall).

| # | Missing capability (the feature to add) | Type | Who it stops | Evidence / ref |
|---|------------------------------------------|:----:|--------------|----------------|
| BL-1 | **Rerank as a registrable model capability** (register form has no rerank flag; `rerank` vs `reranker` string drift) | **B** | N-B, P2, P1 grounding | `CapabilityFlags.tsx:3`; QoL plan §2 |
| BL-2 | **Rerank model discovery** (inventory sync can't parse the Cohere-shape `/v1/models`; fails silently) | **B** | N-B, P2 | `adapters.go:665-684`; QoL plan §1 |
| BL-3 | **Book picker in knowledge-project create** (raw UUID textbox only) | **B** | N-B, P2, N-T | `ProjectFormModal.tsx:292-308`; QoL plan §3 |
| BL-4 | **Viewport-safe dialogs** (FormDialog has no max-h/scroll → action buttons below the fold) | **B** | all wizards | `FormDialog.tsx:19`; QoL plan §4 |
| BL-5 | **Try-before-configure** (no default/guest model or express key path; every newcomer hits BYOK first) | **B** | N-W, N-T, all Day-0 | §4A cross-cutting #2 |
| BL-6 | **Worldbuilding-first "world" container** (no prose-less entry; lore/graph/map locked behind a manuscript) | **B** | N-B | §4A N-B; §6 #3 |
| BL-7 | **Reader-facing lore exploration** (read-only ask-the-lore/wiki/timeline, reading-progress spoiler cutoff) | **B** | N-L | §4A N-L; §6 #5 |
| BL-8 | **Bulk / structured import** (arriving with a finished draft has no ingest path) | **B** | N-T, N-W, P1 | UC-01; roadmap deferral |
| BL-9 | **Derivative / variant (dị bản) creation** (fork-from-canon; raw material for the living world) | **B** | P1 (advanced) | designed V2, unbuilt — see `docs/specs/2026-06-13-derivative-works-living-world-plan.md` |
| BL-10 | **Rerank connection test** (no cross-encoder round-trip to confirm setup works) | S | P2 setup | QoL plan §2 |
| BL-11 | **Degraded-state visibility** (critic skipped / grounding empty / chat ungrounded look identical to "working") | **D** | P1, P2 | UC-41/42/34; §6 #3 |
| BL-12 | **Pre-flight cost at generation** (no per-draft estimate before auto/diverge spend) | S | all | UC-60 |
| BL-13 | **Chat memory-state indicator** (grounded-in-book vs generic fallback is invisible) | **D** | P1 | UC-34 |
| BL-14 | **Stitch-chapter UI** (B2/B3 API exists, likely no surface) | S | P1 | UC-52 |
| BL-15 | **Intent-branching onboarding** (one book-centric funnel for four intents) | **B** | all Day-0 | §4A #1; §6 #1 |
| BL-16 | **Build-graph gates need in-flow recovery + visible benchmark step** (embedding REQUIRED + golden-set benchmark REQUIRED — both dead-end with no link) | **B** | N-B, P2 | standalone review KN-1; `BuildGraphDialog.tsx:247-258` |
| BL-17 | **"Explore graph" path from a Ready project** (built graph → entities/timeline is a dead-end; stats not clickable) | **B** | N-B, P2 | standalone review KN-2; `CompleteCard.tsx:25-32` |
| BL-18 | **Visual graph / relationship view** (only flat in/out lists exist — no network viz) | **B** (feature) | N-B, P1 | standalone review KN-4; `EntityDetailPanel.tsx:311-355` |
| BL-19 | **Projects CRUD-browse + detail view** (no search/sort/real-pagination; filter=archived-toggle only; no project detail drill-in — state-dashboard, not a browser) | S/D | N-B, P2 (at scale) | standalone review KN-20; `ProjectsTab.tsx`, `useProjects.ts` |

> **Diagnosis correction (2026-06-13 standalone review):** **rerank (BL-1/BL-2) is NOT the build-graph blocker.**
> Rerank is optional and per-project (raw-search junk-rejection only); it isn't even in the build dialog. The
> real wall is **BL-16 — embedding model required + a passing golden-set benchmark required.** Full write-up:
> `docs/specs/2026-06-13-knowledge-service-standalone-ux-review.md`.

**Unblock order (recommended):** for the **writer** path, BL-1..BL-4 are NOT on the critical path — see the
core-writer P0 doc (write/continue needs only a chat model). For the **worldbuilder/knowledge** path, clear
**BL-16 → BL-17 → BL-3 → BL-4** (build gates + explore-graph + book picker + dialog scroll) — one FE pass that
lets you build *and then use* a graph — then **BL-1/BL-2** (rerank, for junk-rejection quality), then **BL-18**
(graph viz, the big feature). The *entry-point* structural ones — **BL-15, BL-6, BL-5** (intent fork + world
container + try-before-config) — reshape navigation. **BL-9 (dị bản)** sits on top of all of it.

---

## 6. Cross-cutting design questions to lock NOW (the point of this doc)

These are the "missing design" decisions that, if left open, will keep producing the kind of dead-ends the
user already hit. Resolve before deeper UX build.

1. **Onboarding contract.** What is the *minimum* a writer must configure before the co-writer is useful, and
   how do we make that a single guided flow (model → embedding → optional rerank → knowledge link) instead of
   four separate scavenger hunts? (Drives UC-02/12/30/61.)
2. **Greenfield grounding.** With no extracted lore yet, what does grounding/critic do? (rules-only? incremental
   extraction as chapters are approved?) A blank graph must degrade *visibly and gracefully*. (S1.)
3. **Degraded-mode visibility everywhere.** Critic skipped, grounding empty, chat ungrounded, rerank off — each
   must announce its degraded state. "0 violations / empty panel" must never be ambiguous with "didn't run."
   (UC-41/42/34 — same class as the repo's silent-no-op lessons.)
4. **Cost transparency timing.** Pre-flight estimate at generation, or post-hoc only? Writers fear runaway spend
   on auto/diverge. (UC-60.)
5. **Writer vs operator boundary.** How much ops (providers, campaigns, eval, budget) does a *writer* see vs an
   *operator* role? Today writers are forced through operator surfaces. (UC-30/55/61.)
6. **Viewport / responsive contract.** Wizards/dialogs must be viewport-safe (the knowledge dialogs already
   fail this). Set a rule: all modals `max-h` + scrollable body + pinned actions. (UC-10/12 + QoL plan.)
7. **Publish-gate scope.** Does the gate enforce only canon, or also unpaid threads / coverage? (UC-50.)
8. **Provenance & "I stay the author."** Is AI-written text visibly marked until edited, and is that consistent
   across inline/auto/selection paths? (UC-31/32/33, T5.3.)

> **Plus the 7 newcomer/Day-0 findings in §4A** — most importantly the **intent-branching onboarding fork**
> and the **"world" as a first-class container** (not everything hanging off "book"). These two reshape the
> platform's *entry points* and navigation, so ratify them before building more surface; the rest of §6 assumes
> the user already got in the door, which §4A shows they often can't.

---

## 7. How to drive a UX/UI review from this doc

1. **Start with the newcomer Day-0 scenarios (§4A: N1–N4)** — they expose the entry-point failures first.
   Then the feature-driven ones: **S2** (currently blocked), then **S1**.
2. Walk each UC in its flow in the running app with the right persona mindset (N-W/N-B/N-T/N-L for Day-0,
   P1/P2 for depth) and the JTBD in hand.
3. For every step, check: does it work? is the degraded state visible? is the writer ever dumped into ops-land?
   is anything below the fold / un-scrollable? is cost/continuity/grounding transparent?
4. Log deltas against the **gap matrix** Status column; open defects for ✗/F rows that fail.
5. Feed unresolved items in §6 back into design before building more surface.
