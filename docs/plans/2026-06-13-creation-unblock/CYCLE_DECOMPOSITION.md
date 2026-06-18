# Creation-Unblock + Net-New — RAID Cycle Decomposition

> **Task:** `creation-unblock` · **Slug:** `2026-06-13-creation-unblock` · **Size:** XXL
> **Branch:** `feat/auto-draft-factory-gaps`
> **Sources:** the 2026-06-13 review set —
> [writer-persona-use-cases-scenarios](../../specs/2026-06-13-writer-persona-use-cases-scenarios.md) (§5A blocker register),
> [writer-core-flow-P0](../../specs/2026-06-13-writer-core-flow-P0.md) (WG-1..6),
> [knowledge-service-standalone-ux-review](../../specs/2026-06-13-knowledge-service-standalone-ux-review.md) (KN-1..20),
> [knowledge-fe-ux-qol-gaps](../../specs/2026-06-13-knowledge-fe-ux-qol-gaps.md) (BL-1..4),
> [knowledge-design-vs-impl-gap](../../specs/2026-06-13-knowledge-design-vs-impl-gap.md) (design-draft parity + backend audit),
> [derivative-works-living-world-plan](../../specs/2026-06-13-derivative-works-living-world-plan.md) (dị bản M0–M5).
> **Principle:** bottom-up, dependency-ordered, evidence-gated. Each cycle ships a verifiable slice. Cross-service cycles carry a live-smoke token (CLAUDE.md VERIFY rule).

## Goal
Take the platform from "creation flows blocked / design-incomplete" to a **usable, testable creation loop + the
knowledge-service's full curation flywheel (built to the 2026-04-13 design draft)**, then the net-new surfaces
(visual graph, world container, intent-fork onboarding, dị bản → living world). Scope: PO chose writer +
knowledge unblock + everything net-new + build-to-the-design-draft (2026-06-13). Knowledge cycles re-sized
against the draft after a backend audit; design fully cleared (see OPEN_QUESTIONS_LOCKED).

## Run posture (locked G4)
**FULL autonomy C0→C28, no mid-run human gate** (halts only on escalation/quota/cost/secret). **Live UI smoke =
Playwright MCP screenshots** (test account `claude-test@loreweave.dev`) at every FE cycle + milestone, filed
with the cycle brief and folded into the final report. Cross-service cycles additionally carry a real API
live-smoke call. Human touchpoints = pre-flight sign-off (before) + final report (after).

## Milestones (screenshot checkpoints)
- **M1 (C7):** build + browse a knowledge graph end-to-end.
- **M2 (C14):** knowledge service **design-complete** vs the draft — semantic entities (canonical/discovered/
  anchor), promote, gap report, proposals inbox, 3-step build wizard + target-typed extraction + glossary
  pinning, narrative timeline.
- **M3 (C17):** write-from-scratch / continue-writing works.
- **M4 (C19):** the graph is an explorable visual network.
- **M5 (C21):** a prose-less **world** container exists.
- **M6 (C28):** **dị bản** branches fork from canon → **living-world** timeline tree.

## Phases & cycles

| # | Cycle | Goal / key deliverables | BE/FE | Verify / live-smoke | Depends on |
|---|---|---|---|---|---|
| **C0** | Bootstrap — shared FE foundation | `FormDialog` `max-h`+scroll+pinned-footer (BL-4/KN-3); reusable **`AddModelCta`** (deep-link to model registration + return); reconcile **`rerank`/`reranker`** + wiring test. | FE | smoke: tall dialog scrolls + action reachable; `AddModelCta` round-trips; picker filter matches flag (unit) | — |
| **C1** | Rerank registration (FE) | Add **rerank** to the register form (`CapabilityFlags`); `RerankModelPicker` matches; per-capability "0 found" feedback. (BL-1) | FE | verify: hand-register a rerank model → appears in picker + campaign role | C0 |
| **C2** | Rerank discovery (BE+FE) | provider-registry inventory sync parses **Cohere-shape `/v1/models`** for rerank + tags `capability_flags.rerank`; FE setup guidance. (BL-2) | BE+FE | **live smoke:** add local-rerank credential → Refresh → model under "Reranker" | C0, C1 |
| **C3** | Rerank connection test (BE+FE) | Rerank-aware **verify** (real `/v1/rerank` round-trip) in `EditModelModal`. (BL-10) | BE+FE | **live smoke:** Test a rerank model → ranked scores / latency | C2 |
| **C4** | Book picker (FE) | Reusable **`BookPicker`** (search `booksApi.listBooks`) replacing the raw-UUID field in `ProjectFormModal` (+ campaign step). (BL-3) | FE | verify: search by title → stored `book_id`; empty stays valid | C0 |
| **C5** | Build-graph gates unblock (FE) | `BuildGraphDialog`: in-flow **`AddModelCta`** when embedding/LLM empty; promote **golden-set benchmark** to a visible inline gate. (KN-1/BL-16) | FE | verify: no-embedding → CTA; unbenchmarked → run-benchmark → Confirm enables | C0 |
| **C6** | Project **detail SHELL** (FE — IA backbone, **G6**) | **Book-workspace restructure (G6):** nested route `/knowledge/projects/:projectId/:section` + project-detail shell hosting **Overview** (state+stats+config) and project-scoped sub-tab nav (Entities · Timeline · Evidence · Proposals · Gap · Insights · Build/Explore-graph). `projectId` from **route**, not a select-box. `complete`-card "Explore graph" CTA + clickable stats deep-link into the shell. (KN-2/BL-17 + KN-20 + **G6**) | FE | verify: click project → detail shell → sub-tabs scoped to that project (no project dropdown); Explore-graph routes in | C0 |
| **C7** | Projects **browser = HOME** + build polish (FE) | `/knowledge/projects` becomes the **landing browser**: list **search/sort/filter-by-state/real pagination** (wire BE cursor); rows route into the **C6 detail shell**. Plus post-submit feedback, destructive copy, raise-cap inline, retry-in-error, label/ETA. (KN-20 + KN-5..12 + **G6**) — **▶ M1** | FE | verify: search/sort/filter narrow; >100 paginate; click row → C6 detail; submit→visible job | C5, C6 |
| **C8** | Entities **semantic layer** (BE+FE) | API: add derived **`status` (canonical/discovered/archived)** + **`semantic_query`** (vector) + **status filter** + **`sort_by=anchor_score`** (entity already has `anchor_score`/`glossary_entity_id`/`archived_at`). FE: ⭐/💭/📦 rows + anchor badge + legend + semantic search box, **rendered inside the C6 project-detail shell scoped by route (project `<select>` removed when scoped; survives only on the optional cross-project search surface — G6)**. (design §3) | BE+FE | **live smoke:** semantic query + status filter return correct entities on a built graph | C7 |
| **C9** | **Promote** + entity detail (BE+FE) | Wire `POST /entities/{id}/link-to-glossary`; **promote flow** = create glossary **draft** (tag `ai-suggested`) from the discovered entity → anchor (`anchor_score=1.0`). Entity detail: **facts list** (existing endpoint) + relations + **unpin** (`is_pinned_for_context`) + promote. (design entity-detail) | BE+FE | **live smoke:** promote a discovered entity → glossary draft created + entity anchored (canonical) | C8 |
| **C10** | **Glossary Gap Report** (BE+FE) | Wire `GET /projects/{id}/gaps?min_mentions=&limit=` over `find_gap_candidates()` (entity gaps — high-mention, no glossary entry; distinct from lore-enrichment attribute gaps). FE: summary cards + threshold + **bulk-promote** (sequential, reuses C9). (design §4) | BE(thin)+FE | verify: report lists high-value gaps; bulk-promote moves them to glossary drafts | C9 |
| **C11** | **Pending Proposals** inbox (FE) | **Aggregate** 3 sources: glossary drafts (`?status=draft&tags=ai-suggested`) + AI wiki stubs + lore-enrichment proposals (`/proposals?review_status=proposed|author_reviewing`), with **deep-links** to each review UI. **Integrate, do not duplicate.** (design §4) | FE | verify: inbox unifies 3 sources; each row deep-links to its existing review UI | C8 |
| **C12** | Build wizard — **target-typed extraction + concurrency** (BE+FE — **L · DESIGNED**) | 3-step wizard shell + **Step-1 target picker**. **De-risked by [DESIGN_C12_C13](DESIGN_C12_C13.md):** the SDK already dispatches separable extractors via `asyncio.gather` → selective invocation is a **conditional task-list at ~4 sites** (SDK `pass2.py`, orchestrator gather, summaries gate, decoupled trio), not a rewrite. `targets:[]`+`concurrency_level` threaded; `targets=None`⇒all (back-compat). Validation: dependent targets auto-include entities; recovery/filter auto-disable when entities skipped. | BE+FE | **live smoke:** `targets=["events"]` → only the event pass runs (relations/facts untouched) | C5 |
| **C13** | Build wizard — **glossary pinning** (BE+FE — **M–L · DESIGNED**) | Step-2 **dual-list pinning**: `pinned_glossary_entity_ids:[]` prepended to `known_entities` in **every** window. Per [DESIGN_C12_C13](DESIGN_C12_C13.md): knowledge path additive; **worker-ai gets a `fetch_entities_by_ids` method** (client already wired, just no batch-fetch); **auto-pin** needs a NEW glossary `GET /internal/books/{id}/entities/stats` (span+coverage GROUP-BY); pinned-injection cost line. | BE+FE | **live smoke:** build with 2 pinned entities absent from chapter N → both appear in chapter N's extraction prompt | C12 |
| **C14** | Timeline narrative-order + importance (BE+FE) | Event **importance (major/pivotal)** + narrative-order sort + the timeline rail UI, **rendered inside the C6 project-detail shell scoped by route (project `<select>` removed when scoped — G6)**. (design timeline) — **▶ M2** | BE(thin)+FE | verify: timeline renders narrative order with importance badges | C8 |
| **C15** | Writer unblock (FE) | Empty chat-model **`AddModelCta`** in Compose; **"Ready to draft"** messaging (knowledge optional); plain-editor→AI **bridge**. (WG-1/2/6) | FE | verify: greenfield + one chat model → write + Generate (empty grounding advisory) | C0 |
| **C16** | Work-setup resilience (BE composition) | `POST /work` must **not 502** when `knowledge.create_project` fails — lazy/null `project_id`; grounding degrades. (WG-3) | BE | **live smoke:** knowledge down → "Set up co-writer" still succeeds → Generate returns prose | — |
| **C17** | Writer flow polish (FE) | Guided first-run (auto first scene + auto-pick sole model + cue); **"Continue from cursor"** first-class action. (WG-4/5) — **▶ M3** | FE | verify: fresh book → guided to first draft ≤2 clicks; continue-from-cursor streams | C15, C16 |
| **C18** | Graph subgraph endpoint (BE knowledge) | **BUILD** `GET /v1/knowledge/projects/{id}/subgraph` (Neo4j n-hop, node-capped) — none exists (only per-entity 1-hop). | BE | **live smoke:** query a built project → capped subgraph (nodes+edges) | C5 |
| **C19** | Graph canvas (FE) | **Visual network** reusing `GraphCanvas` + generalizing `RelationshipMap` (pan/zoom/click→detail/expand-hop, node cap). No new graph library. Read-only. (BL-18/KN-4) — **▶ M4** | FE | verify: built graph renders as navigable network | C18 |
| **C20** | World container — model + API (book-service) | `worlds` table + nullable `world_id` FK on `books` (default NULL = standalone); CRUD + move-book-into-world. **ARCH-REVIEW FIX: on world creation auto-create a hidden "world bible" chapter (sort_order 0)** so the chapter-keyed lore machinery works prose-less (glossary `chapter_entity_links.chapter_id`, knowledge extraction, composition outline all require a chapter). Keeps additivity — **no schema change to the 3 lore services.** (BL-6 / G1) | BE | **live smoke:** create world → bible chapter exists → attach book → world lists books; null-world books unaffected | C0 |
| **C21** | World container — FE | Prose-less **worldbuilding entry**: create a world → author entities/graph/timeline/canon **linked to the world-bible chapter** (extraction optional; the bible chapter is the anchor). (BL-6 / §4A N-B) — **▶ M5** | FE | verify: worldbuilder creates a world with no manuscript and authors lore against the bible chapter | C20, C19 |
| **C22** | Intent-branching onboarding (FE) | First-run **"What do you want to do?"** → Write / Build a world / Translate / Explore → routes to the tailored path + right container. (BL-15 / §6 #1) | FE | verify: each of 4 intents lands in the correct surface | C20, C21 |
| **C23** | Derivative schema + API (composition) | `source_work_id`+`branch_point` on `composition_work`; `divergence_spec`, `entity_override` tables; **`POST /works/{id}/derive`** (spec only, no clone). **ARCH-REVIEW GUARD: derivative Work `project_id` is NOT-NULL enforced** (the knowledge timeline endpoint widens to ALL projects on null project_id → cross-project grounding leak). This is also the `source_work_id` field C28 joins on. (dị bản M0) | BE | verify: derive a Work linked to a source + spec; null project_id rejected; migration up/down clean | C0 |
| **C24** | Divergence wizard + derivative studio (FE) | 4-step wizard (source/branch → type → overrides preview → name) + studio banner + 2-layer INHERITED/OVERRIDDEN grounding badges. (dị bản M1) | FE | verify: spawn a genderbend dị bản from the UI | C23 |
| **C25** | Packer override-merge (composition) | Packer: `base(source project_id ≤ branch)` → **apply entity_overrides** → merge `delta(derivative project_id)` (G2: derivative owns its own knowledge partition). **ARCH-REVIEW: the `before_order` branch-filter + the override-application seam (packer `assemble`) already exist** — this cycle adds the two-project (source+delta) merge + override mutation on top. Override-at-retrieve is self-syncing (re-read + re-apply every pack — no stale cache). | BE | **live smoke:** generate in a derivative → overridden entity stays overridden across chapters | C23, C8/C13 |
| **C26** | Critic override enforcement (composition) | Derivative critic dimension: enforce overrides + internal consistency. (dị bản M3) | BE | verify: critic flags an override slip | C25 |
| **C27** | Flywheel on delta + what-if→derivative promotion | Approved derivative chapters extract into the **delta** graph; promote a what-if to a persistent derivative. (dị bản M4) | BE+FE | **live smoke:** approve a dị bản chapter → delta enriches next-scene grounding | C25, C26 |
| **C28** | Living-world view (FE) | The world container surfaces canon Work + dị bản branches as a navigable **timeline tree** (reuses `GraphCanvas`). (dị bản M5 / living world) — **▶ M6** | FE | verify: one world shows canon + ≥2 derivative branches | C21, C27 |

## Notes
- **Cycle count = 29 (C0–C28);** first_cycle=0, last_cycle=28, bootstrap_cycle=0. (C12 split into C12 target-typed + C13 pinning per the 2026-06-13 CLARIFY.)
- **Knowledge built to the 2026-04-13 draft.** All draft surfaces map to a cycle or are already built (Global bio, Evidence/Raw, Extraction Jobs, Privacy, State legend = built; mobile entities/timeline are *intentionally* desktop-only per the draft; the chat memory indicator is a chat-feature, out of this boundary). Design fully cleared in OPEN_QUESTIONS_LOCKED §Knowledge cycle design.
- **Knowledge IA = book-workspace pattern (G6, PO 2026-06-13).** Current `KnowledgePage` is a flat 8-tab shell
  where Entities/Timeline/Raw each carry their own project `<select>` (breaks at thousands of projects). C6
  restructures to project-detail-as-home (`/knowledge/projects/:projectId/:section`); C7 browser is the landing;
  C8/C14 render scoped inside the shell. **The already-built `RawDrawersTab` also moves into the shell and loses
  its project dropdown when scoped** (small edit, fold into C6). The draft's cross-project "All projects" view is
  **kept as a demoted secondary search surface only** — not the default. This is a *correction to the 2026-04-13
  draft*, which itself uses the flat-tabs+select model. (Mostly re-composition; no new BE.)
- **Curation flywheel = INTEGRATE, don't duplicate.** C9–C11 aggregate over + deep-link to lore-enrichment + glossary review queues. The design's Gap Report (C10, entity gaps via `find_gap_candidates`) is distinct from lore-enrichment's attribute-dimension `detect-gaps` — keep separate.
- **Build wizard is C12+C13 (split).** Extraction is monolithic today (no target-typed builds, no pinned injection, no concurrency); C12 builds target-gating + concurrency, C13 builds the pinning injection + dual-list — the design's scale centerpiece.
- **Cross-service / live-smoke cycles:** **C2, C3, C8, C9, C12, C13, C16, C18, C20, C25, C27** — each carries a real API live-smoke (+ a Playwright shot where a UI exists). Rebuild touched service images first.
- **Parallelism:** after C0 — rerank {C1–C3} ∥ knowledge build {C4–C7} ∥ writer {C15–C17}. Knowledge flywheel {C8–C14} is serial-ish on C8. Net-new serial: C18→C19; C20→C21→C22; C23→C24→C25→C26→C27→C28.
- **dị bản = copy-on-write** (composition-only schema; derivative owns its own project_id = delta, per G2). World container (C20) is the shared substrate for the living-world view (C28).
- **No rerank confusion:** rerank (C1–C3) is grounding/junk-rejection quality; not required to write (C15) or build a graph (embedding+benchmark are — C5).
- **Architecture review (2026-06-13, adversarial):** invariants all pass (provider-gate green, rerank via provider-registry, no hardcoded models, composition has no AI imports). World schema additive; dị bản partition model + branch-filter + override seam confirmed real. **Three plan fixes applied:** (1) C12 re-sized L/XL — target-typed extraction is a `loreweave_extraction` SDK refactor, not a param; (2) C13 expanded — worker-ai needs a new glossary_client for pinning; (3) C20/C21 — prose-less world needs an auto-created "world bible" chapter (the chapterless story broke glossary/knowledge/composition). Guard: C23 enforces derivative `project_id` NOT NULL (timeline null-project leak). See OPEN_QUESTIONS_LOCKED §Architecture-review locks.
