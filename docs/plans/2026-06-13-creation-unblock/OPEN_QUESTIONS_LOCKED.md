# Creation-Unblock — Locked Design (CLARIFY complete)

> **Status: ALL design questions CLEARED 2026-06-13** (code-grounded). RAID cycles MUST honour these.
> Reopening any **[LOCKED]** item requires explicit user sign-off. There are **no remaining design gates** —
> only runtime infra checks remain (see PRE_FLIGHT L1–L4/L3), which are environment, not design.

## Scope (locked by PO 2026-06-13)
- **[LOCKED] Scope = writer + knowledge unblock + ALL net-new** (graph viz, world container, intent fork,
  dị bản/living world). 22 cycles, C0–C21.
- **[LOCKED] Diagnosis correction:** the build-graph blocker is **embedding model + golden-set benchmark**
  (C5), **not** rerank. Rerank (C1–C3) is optional grounding-quality.
- **[LOCKED] Writer path is not hard-blocked:** write/continue needs only a chat model; embedding/rerank/
  knowledge degrade gracefully (verified: packer FTS fallback, rerank→candidate[0], grounding advisory). C8–C10
  are signposting + resilience, not unblocking a wall.

## G1 — World-container boundary → **LOCKED: additive `world_id` grouping in book-service**
*Grounded:* `books` (book-service) has **no** existing grouping; `book_id` is referenced by glossary
(`glossary_entities.book_id`), knowledge (`knowledge_projects.book_id`), composition (`composition_work.book_id`)
as **app-validated cross-DB refs (no hard FK)**; sharing/grants are per-book.
- **Decision:** add a `worlds` table (`id, owner_user_id, name, description`) + a **nullable `world_id` FK on
  `books`** (default NULL = standalone book / its own world). No backfill. Books with `world_id=NULL` coexist
  unchanged — list/scoping queries are unaffected (verified `server.go` list filter).
- **A "world" groups books.** Lore (glossary/knowledge/composition) stays **book_id-keyed** — it rolls up to a
  world *via its books*. No `world_id` column added to glossary/knowledge/composition (avoids schema churn).
- **Prose-less worldbuilding (N-B):** a world's "bible" is a **book with zero chapters**; glossary entities are
  authored directly (verified: `createEntity` needs only `kind_id`+`book_id`, no chapter), knowledge project
  with `extraction_enabled=false`. The FE (C14) presents this as "a world," hiding the book mechanic.
- **[LOCKED] World-level sharing is deferred** — grants stay per-book (additive). Non-goal here.

## G2 — dị bản delta isolation → **LOCKED: derivative gets its own project_id = its own partition**
*Grounded:* `composition_work.project_id` **IS** a `knowledge_projects.project_id` (1:1; `works.py` creates the
knowledge project first, then the Work row with that PK). Neo4j partitions by `(user_id, project_id)`.
- **Decision:** a derivative Work is created with **its own new knowledge project_id** → it **automatically
  owns its own Neo4j partition** (the delta layer). The **base** = the source Work's `project_id`.
- **Packer (C18)** queries `base(source project_id, ≤ branch_point)` + applies overrides + merges
  `delta(derivative project_id)`. **No knowledge schema change; no shared-graph plumbing.** This is the COW
  design realized with zero new cross-service machinery.

## G3 — Branch-point granularity → **LOCKED: chapter-level for M0**
Canon `from_order`/`until_order` stride supports finer (chapter×scene) later, but M0 wizard + packer filter use
**chapter-level** branch points. Finer granularity is a post-MVP enhancement.

## G4 — Run posture → **LOCKED (PO 2026-06-13): FULL autonomy C0→C21 + Playwright UI smoke**
The Coordinator runs **all 22 cycles (C0→C21) in one invocation, no mid-run human gate** — halting only on
escalation / quota / cost / secret. **No hard stop at M-DEMO-1.**
- **[LOCKED] Live UI smoke = Playwright MCP screenshots.** For FE cycles and at each milestone, the Coordinator
  drives the running frontend via Playwright MCP (test account `claude-test@loreweave.dev`), performs the
  cycle's user action, and **captures a screenshot** as the VERIFY evidence — proving the UI actually works, not
  just that units pass. Screenshots are filed with the cycle brief and folded into the final report.
- **[LOCKED] Cross-service cycles still carry a real live-smoke call** (API round-trip on a stacked-up service)
  *in addition to* the Playwright screenshot where a UI surface exists.
- **Human touchpoints = pre-flight sign-off (before) + final report with screenshots (after).** That's it.

## G5 — Visual-graph scope → **LOCKED: read-only navigable MVP, reuse `GraphCanvas`, build a subgraph endpoint**
*Grounded:* `GraphCanvas.tsx` is a generic hand-rolled SVG layer; `RelationshipMap.tsx` already renders an entity
ego-network on it; **no graph library is installed**; **no project-wide subgraph endpoint exists** (only
per-entity 1-hop `GET /entities/{id}`).
- **Decision:** **no new graph library.** C11 builds `GET /v1/knowledge/projects/{id}/subgraph` (Neo4j, n-hop,
  node-capped). C12 reuses `GraphCanvas` + generalizes the `RelationshipMap` pattern to render the project
  subgraph (pan/zoom/click→detail/expand-hop). **Read-only**; editing reuses the existing entity/relation
  dialogs. Node cap with "expand"/"load more" (MVP; force/radial layout hand-rolled).

## G6 — Knowledge IA → **LOCKED (PO 2026-06-13): book-workspace pattern (project-detail home), cross-project demoted to secondary search**
*Grounded:* `KnowledgePage.tsx` is a **flat 8-tab shell** (`/knowledge/:tab`); Entities/Timeline/Raw each carry
their **own project `<select>`** (`EntitiesTab.tsx:79`, `TimelineTab.tsx:78`, `RawDrawersTab.tsx:106`) over a
single 100-row `useProjects` page — **breaks at thousands of projects**. The 2026-04-13 draft itself uses this
flat-tabs + "All projects" select model; **G6 is a correction TO the draft**, not derived from it.
- **Decision:** restructure to the platform's **book-workspace pattern** (`/books/:id/...`):
  - **`/knowledge/projects` = HOME** — the project **browser** (grid/list, search/sort/filter/paginate — C7).
  - **`/knowledge/projects/:projectId/:section` = PROJECT DETAIL shell** (C6 grows into this) — hosts the
    project-scoped sub-tabs: **Overview** (state+stats+config) · **Entities · Timeline · Evidence · Proposals ·
    Gap · Insights · Build/Explore-graph**. `projectId` comes from the **route**; the per-tab project
    `<select>` is **removed** when scoped.
  - **`/knowledge/jobs · /global · /privacy`** stay top-level (legitimately cross-project).
- **[LOCKED] Cross-project view = KEEP as a demoted secondary search** (PO choice). Retain **one** global
  "Search across all projects" surface (the draft's "find the god across all my books" semantic case) — NOT
  the default landing for entities/timeline. The select-box survives **only** there.
- **Plan impact:** **C6 absorbs the project-detail shell** (the IA backbone — nested route + sub-tab nav);
  **C7 browser is the home** whose rows route into C6; **C8 (entities) / C14 (timeline) / Raw** render *inside*
  the detail shell scoped by route. Mostly **re-composition** — the tabs already accept a `projectFilter`; feed
  it from the route and hide the dropdown when scoped. No new BE.

## dị bản — remaining design, locked
- **[LOCKED] Architecture = copy-on-write** (reaffirmed): new composition-only tables (`source_work_id`+
  `branch_point` on `composition_work`; `divergence_spec`; `entity_override`); base inherited by reference;
  override-at-retrieve; delta = derivative's own project (per G2). No book/glossary/knowledge migration.
- **[LOCKED] Override scope (M0) = entity fields + added canon rules.** Relationship/event overrides deferred.
- **[LOCKED] Divergence taxonomy = UX §7.1** (POV shift · character transform · AU) — all reduce to
  `branch_point` + optional `pov_anchor` + `entity_override[]` + added `canon_rule[]`.
- **[LOCKED] Reference spine = original chapters available read-only** as adaptable reference (not auto-inserted;
  writer adapts manually) — avoids copy-paste derivatives.
- **[LOCKED] Ownership = derivative owned by its creator;** a derivative of a shared/collaborative work follows
  the source's per-book grant. Cross-tenant derivative publishing deferred.

## World container — remaining design, locked
- **[LOCKED] A world is created empty;** the worldbuilder adds a chapterless "bible" book implicitly (C14 hides
  it). Books can be moved into/out of a world (set `world_id`).
- **[LOCKED] Living-world view (C21)** = a world surfaces its canon Work + dị bản branches (Works whose
  `source_work_id` chains into books in the world) as a timeline tree. Reuses `GraphCanvas`/tree rendering.

## Knowledge design-parity (LOCKED 2026-06-13 — PO: build to the 2026-04-13 draft; backend-audited)
- **[LOCKED] Build to the design draft** `design-drafts/screen-knowledge-service.html`. The implemented UI is
  incomplete; the missing curation flywheel + semantic-entity layer + 3-step build wizard are in-scope
  (cycles C8–C13). See `docs/specs/2026-06-13-knowledge-design-vs-impl-gap.md`.
- **[LOCKED] Curation flywheel = INTEGRATE, don't duplicate.** Backend audit: the flywheel already exists,
  split across **lore-enrichment-service** (proposals/promote/gap-detection) + **glossary-service** (drafts/wiki
  stubs). C9–C11 aggregate over + deep-link to those review queues (the draft says so). No new review system.
- **[LOCKED] Two distinct "gap" concepts — keep separate.** lore-enrichment `detect-gaps` = *attribute-dimension*
  gaps (entity missing `history`); the design's **Gap Report (C10)** = *entity* gaps (high-mention discovered
  entity, **no** glossary entry) → knowledge-service `find_gap_candidates()`. Different queries; don't merge.
- **[LOCKED] Entity anchor model already in the data** (`anchor_score`, `glossary_entity_id`, `archived_at` on
  the Neo4j Entity; `find_gap_candidates()` ready) — C8/C9/C10 are mostly **thin BE endpoint-wiring + FE**, not
  greenfield BE. Explicit `status` enum may be added or inferred FE-side.
- **[LOCKED] Build wizard (C12) is the one genuine full-stack heavy lift.** Extraction is monolithic today (no
  target-typed builds, no pinned-entity injection, no concurrency) — C12 builds all three in worker-ai + packer
  + the start contract. Split into sub-cycles at brief time if it grows. Pinning is the design's scale centerpiece.

## Knowledge cycle design — CLARIFY complete, ALL LOCKED 2026-06-13
Decisions for C8–C14 (knowledge built to the 2026-04-13 draft). No open questions remain.

- **[LOCKED] C8 entity status** → API returns a **derived `status` field** (`canonical` = `glossary_entity_id`
  set · `discovered` = unanchored · `archived` = `archived_at` set), computed server-side from existing columns
  (no new column). **Semantic search** = new `semantic_query` param → vector search; plain `search` stays FTS.
  Add `status` filter + `sort_by ∈ {anchor_score, mention_count}`.
- **[LOCKED] C9 promote flow** → FE orchestrates two calls: (1) create a **glossary draft** entity
  (`status=draft`, tag `ai-suggested`) from the discovered entity's name/kind/aliases via glossary's
  extract-entities/create; (2) knowledge `POST /entities/{id}/link-to-glossary` to anchor (`anchor_score=1.0`).
  Promote creates a **draft**, not active — human reviews in glossary. **Provenance MVP** = facts list (existing
  endpoint) + `source_chapter`; full passage-trail deferred. **Unpin** toggles `is_pinned_for_context`.
- **[LOCKED] C10 Gap Report** = knowledge `find_gap_candidates()` (entity gaps: high-mention, no glossary
  entry) wired as `GET /projects/{id}/gaps?min_mentions=&limit=`. **Bulk-promote = sequential C9 calls** with a
  progress indicator (no batch endpoint). Distinct from lore-enrichment's attribute-dimension `detect-gaps`.
- **[LOCKED] C11 Proposals inbox** aggregates exactly 3 sources (glossary ai-suggested drafts · AI wiki stubs ·
  lore-enrichment proposals) **read-only + deep-link**; no in-knowledge review system.
- **[LOCKED] C12 target taxonomy** = `entities · relations · events(timeline) · lore(wiki) · summaries`; each
  maps to an existing worker-ai pass; `targets:[]` (default all) gates which passes run. `concurrency_level`
  added to StartJobRequest.
- **[LOCKED] C13 pinning** = `pinned_glossary_entity_ids:[]` on StartJobRequest; the packer injects those
  entities' context at the **top of every extraction window** regardless of chapter content. **Auto-pin
  heuristic** = sparse-but-long-reaching (low `mention_count`, wide `first→last` span). Pinned-injection cost
  (`pinned_tokens × windows`) shown as its own line in the estimate.
- **[LOCKED] C14 timeline** = add event **importance (major/pivotal)** + narrative-order sort; thin BE + the rail UI.
- **[LOCKED] Out of this knowledge boundary:** the chat memory indicator (a chat-feature) is deferred; mobile
  entities/timeline stay desktop-only (design-conformant). The whole-platform design-draft audit (editor/wiki/
  reader/translation/social/etc.) is **explicitly out of scope** for this task.

## Architecture-review locks (2026-06-13 — adversarial review, before run)
The plan survived an adversarial architecture review. Invariants pass (provider-gate green; rerank via
provider-registry BYOK; no hardcoded models; composition has no AI imports). Three fixes + one guard locked:

- **[LOCKED] C12 = L (DESIGNED, de-risked from XL).** Detailed design in `DESIGN_C12_C13.md`. The SDK already
  dispatches separable extractors via `asyncio.gather`, so target-typed extraction is a **conditional task-list
  at ~4 sites** (SDK `pass2.py`, orchestrator gather, summaries gate, decoupled trio) + additive threading —
  NOT an extractor rewrite. Locks: `targets=None`⇒all (back-compat); dependent targets auto-include `entities`;
  recovery/filter auto-disable when entities skipped; `targets` stored `TEXT[]`; SDK change stays
  backward-compatible for other consumers (translation-service).
- **[LOCKED] C13 = M–L (DESIGNED).** `DESIGN_C12_C13.md`. Knowledge path additive (prepend pinned names to
  `known_entities`); **worker-ai gets a `fetch_entities_by_ids` method** (GlossaryClient already wired — only a
  batch-fetch is new); **auto-pin ships in C13** via a NEW glossary `GET /internal/books/{id}/entities/stats`
  (span+coverage GROUP-BY over `chapter_entity_links`); pinning = name-prefix injection; cost line added.
- **[LOCKED] Prose-less world = an auto-created "world bible" chapter (sort_order 0).** The "chapterless book"
  story BROKE: glossary `chapter_entity_links.chapter_id` is NOT NULL, knowledge extraction is chapter-keyed,
  composition outline forbids scenes without a chapter. **Fix:** C20 auto-creates a hidden bible chapter on
  world creation; all lore links to it. Preserves additivity — **no schema change to glossary/knowledge/
  composition.** (Supersedes the earlier "chapterless bible book" wording under G1.)
- **[LOCKED] GUARD: derivative Work `project_id` NOT NULL.** The knowledge timeline endpoint widens to ALL of a
  user's projects when `project_id` is null → silent cross-project grounding leak. C23 enforces NOT NULL +
  the packer asserts project-scoping for derivatives.
- **[CONFIRMED] dị bản partition + override-at-retrieve are sound.** `composition.project_id == knowledge.
  project_id` (1:1), Neo4j is `(user_id, project_id)`-partitioned (new id = clean delta), `before_order`
  branch-filter + the packer override seam already exist; C25 wires the two-project merge on top. Override is
  re-applied every pack (self-syncing, no stale cache). C28's `source_work_id` join is provided by C23.
- **[LOCKED] Derivative write-order:** derivatives are written **forward from the branch_point**; out-of-order
  authoring just yields a thinner delta (grounding degrades gracefully, not a correctness break).

## Non-goals (this task)
- Translator-specific flow beyond intent-fork routing · reader/lore-seeker product beyond read-only graph/wiki ·
  full-clone "hard fork" (distinct from COW dị bản) · bulk/structured import (BL-8) · world-level sharing.
