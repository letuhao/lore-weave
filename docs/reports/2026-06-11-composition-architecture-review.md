# Composition V1 — Architecture review (scenarios + edge cases)

**Branch:** `feat/composition-service` · **Date:** 2026-06-11 · **Scope:** the 24-spec V1 design set ([program](../plans/2026-06-10-composition-design-program.md)) reviewed as **one system** (not per-spec). Complements the per-spec [`/review-impl`](#) (HIGH-1 + MED-2/3/4/5 folded). **Method:** walk real author scenarios (happy / degraded / scale / multi-device / concurrent) + an edge-case matrix; surface cross-feature architecture risks the per-spec pass can't see.

> **Headline:** structure + UX are sound and the per-spec contracts are now verified. But two **systemic** issues surface only at the architecture level — **AH-1** (the co-writer is scene-node-coupled while the editor edits chapters) and **AH-2** (OS pop-out contradicts the no-unmount invariant). Both need a design decision before the features they touch are built. Plus a four-axis coherence risk (AH-3) that MED-3 was one instance of.

---

## Part 1 — Scenarios

### S1 · Cold start (new book, zero knowledge graph)
Author creates a work, opens the studio. **What's empty:** Cast codex (T2.1), Relationship Map (T2.2), Timeline (T2.3), Character Arc (T2.4), World Map (T2.5), Flywheel (T4.1), Grounding (existing) — all read knowledge, which is empty until the first extraction. **What works:** editor, outline (after decompose), canon rules, style, references, focus, manuscript writing. **Risk:** 7 panels show empty states simultaneously → "broken studio" feeling. **Need:** a consistent, encouraging empty-state story + the documented "run one extraction to bootstrap" path (the [extraction bootstrap](../../C:/Users/NeneScarlet/.claude/projects/d--Works-source-lore-weave/memory/project_composition_canon_flywheel_bootstrap.md) gotcha — fresh books don't auto-extract). **Verdict:** acceptable if empty states are coordinated (not 7 different "no data" messages). → rec **R1**.

### S2 · The write→learn loop (the core flywheel)
Inline AI draft (T3.3) → accept (provenance mark T5.3) → continuity critic → publish → **canonization → extraction** → Cast/Timeline/RelMap/Flywheel update. **This is the product's spine.** Strains: (a) the AI-draft path is `text → text_to_tiptap_doc → book PATCH` (engine.py:221) — **plain text, no marks** — so provenance (T5.3) is an FE-applied mark that must survive the book-service round-trip (T5.3 Q2 is load-bearing, not cosmetic); (b) extraction is **async** — the Flywheel "+N learned" lags publish by the extraction job; the panel must show "extracting…" then settle (T4.1 already notes this); (c) re-extraction **churns** entity_status/events/relations → see AH-6. **Verdict:** the loop is coherent but provenance-persistence + extraction-lag must be designed in, not assumed.

### S3 · Multi-device (PC ⇄ phone)
Per CLAUDE.md server-SSOT rules. **Server-persisted (consistent across devices):** outline, canon, style/voice, references, narrative threads, daily-progress/streak (T4.2), world-map positions+backdrop (T2.5), provenance (rides in content). **Per-device (localStorage, divergent by design):** windowing layout (T5.4), focus mode (T5.1), scene-graph local positions (T1.3), heatmap toggle (T5.2). **Risk:** the line is correct per the rules, but T5.4's *windowing layout* being per-device means "my studio looks different on each device" — acceptable (UI state) but document it. **Edge:** world-map positions are server-shared (T2.5 PO choice) while scene-graph positions are per-device (T1.3) — an inconsistency in the same "graph" UX family. → rec **R2** (decide one rule for graph-layout persistence).

### S4 · Concurrent edits (two devices / tabs)
Outline node edits use `If-Match` → 412 (good). Chapter draft: book-service revisions. **Strains:** (a) two devices generating into the **same scene** → two ghost drafts, two `_persist_chapter_draft` PATCHes — last-write-wins on the draft revision (no merge); (b) provenance marks from two sessions on the same chapter — the mark lives in content, so it follows the surviving revision; (c) grounding-prefs / daily-progress upserts — idempotent-ish but need per-(work,…) keys. **Verdict:** the read/write SSOT is fine; the **co-writer has no concurrency story** (two-device same-scene generate). Likely acceptable for a single-author tool, but state it (AH-9, LOW).

### S5 · Degraded services (knowledge-service down)
The gateway 503s `/v1/knowledge/*` when knowledge is down. **~6 panels read knowledge directly** (Cast, RelMap, Timeline, Arc, World Map, Flywheel) → all fail at once. **The write surface stays up** (editor/generate/canon/outline = composition+book). **Risk:** without a shared degrade boundary, a knowledge outage could throw in 6 places and destabilize the studio shell. **Need:** every knowledge-reading panel degrades to a "knowledge unavailable" state (the GroundingPanel pattern), never crashes the shell. → AH-5 + rec **R3**.

### S6 · Scale (200 chapters, 500 entities, 50 scenes/chapter)
**N+1 reads:** Relationship Map (T2.2) and World Map (T2.5) build the graph by calling `/entities/{id}` per node (ego-network accretion) → tens of calls for a dense neighborhood. Mention heatmap (T5.2) recomputes per content change (needs debounce + memo). Timeline (T2.3) paginates (good). Outline tree (T1.1) renders the full committed tree (200×50 nodes → virtualization?). **Verdict:** the deferred "graph endpoint" (T2.2) and outline virtualization are real at scale; fine for V1 small books, flagged for the scale path. → AH-8.

### S7 · Spoiler-safety end-to-end
The cutoff (`before_order`) threads through Cast status, Timeline, Character Arc, and the grounding pack (existing). **All four must compute the same cutoff from the current chapter.** If any uses raw chapter order instead of `event_order = sort_order × EVENT_ORDER_CHAPTER_STRIDE` (MED-3), spoilers leak (future events shown) or content vanishes. **This is a correctness-critical invariant spread across 4+ features.** → AH-3 + rec **R4** (one shared cutoff helper).

---

## Part 2 — Systemic findings (ranked)

**🔴 AH-1 (HIGH) — the co-writer is scene-node-coupled, but the manuscript editor edits chapters.**
`GenerateBody.outline_node_id: UUID` is **required** (engine.py:71); generate loads a committed node (`_load_work_node`, :254). So T3.2 (selection rewrite/expand/describe), T3.3 (inline continue), and ComposeView all assume **a committed outline scene node is in focus**. But the editor edits a **chapter** (Tiptap doc) that may have **zero** decomposed scenes, or many. The mapping **cursor-position → `outline_node_id`** is unspecified and load-bearing. A chapter the author hasn't decomposed has no scene node → the co-writer (and selection tools) can't run. *Fix: define the cursor→scene resolution (which scene node owns the caret), OR add a chapter/selection-scoped generate path that doesn't require a scene node. Decide before building T3.2/T3.3.* **Touches T3.2, T3.3, ComposeView.**

**🔴 AH-2 (HIGH) — OS pop-out (T5.4) contradicts the no-unmount invariant for stateful panels.**
The PO chose **full OS pop-out** (`window.open`). But a React subtree **cannot move to another browsing context without remounting** — a portal into the popped window's document re-creates the tree there, re-initializing stateful hooks (the co-writer **stream**, chat **SSE**, the Tiptap **editor**, AudioContext). So "no-unmount when popped to an OS window" — the spec's central invariant — is **not achievable** for exactly the stateful panels that matter. *Fix: pick a strategy — (a) only stateless/cheap panels may OS-pop-out (stream/chat/editor stay docked or in-app-float only); (b) hoist the live state into a shared owner (SharedWorker / the main window) and make the popped window a thin synced view (large undertaking); (c) accept re-init on pop-out (drop the guarantee for popped panels). Decide before building T5.4.* **Touches T5.4.**

**🟠 AH-3 (HIGH→MED) — four-axis coherence.** `story_order` (composition scene) · `event_order` = `sort_order × EVENT_ORDER_CHAPTER_STRIDE` (knowledge) · chapter `sort_order` (book) · `block_index` (chapter content / jump-to-source). Many features convert between them; MED-3 (spoiler cutoff) was one instance. Getting any conversion wrong is a silent correctness bug (the timeline-axis bug class). *Fix: a single shared axis-conversion module (FE + a documented BE contract) + unit tests; every cross-axis feature uses it.* → R4.

**🟠 AH-4 (MED) — id-space split: glossary `entity_id` vs knowledge `entity_id`.** Two-layer is confirmed (`glossary_entity_id` anchor, KSA §3.4.E). But: `present_entity_ids` / cast roster / suggest-cast use **glossary** ids; Cast codex relations+status / Relationship Map / grounding-prefs use **knowledge** ids. A knowledge entity may be **unanchored** (no glossary link) and a glossary entry may have **no knowledge entity**. So "the cast of a scene" (glossary ids) and "the codex/relations" (knowledge) can disagree, and a grounding-pref keyed by one id-space won't match the other. *Fix: pick the canonical id for composition (lean: glossary `entity_id` as the authored key; resolve to knowledge via `glossary_entity_id` for codex/relations); define behavior for unanchored/unlinked entities.* **Touches T2.1, T2.2, T3.4, T0.2.**

**🟠 AH-5 (MED) — knowledge-direct coupling needs a shared degrade boundary.** ~6 panels read `/v1/knowledge` directly; a knowledge outage hits all at once (S5). *Fix: a `useKnowledgeQuery` wrapper / error boundary that renders a uniform "knowledge unavailable" state and never destabilizes the shell; the write surface stays fully usable.* → R3.

**🟠 AH-6 (MED) — re-extraction churn orphans refs.** Publishing re-runs extraction → entity merge/rename/split, status transitions, new/changed events. Anything keyed by knowledge `entity_id` (grounding-prefs pins T3.4, Cast/RelMap selections) or by `event_order` (timeline positions) can **dangle or shift** after a re-extract. *Fix: ref reconciliation (resolve through the merge/canonical id) + tolerate-missing on every stored ref; never hard-fail on a vanished ref.* **Touches T3.4, T2.x.**

**🟠 AH-7 (MED) — deletion/archival cascades into the new stores.** Archive a scene node that is a scene-link endpoint (T1.3), beat-mapped (T1.2), in `present_entity_ids`, or has grounding-prefs (T3.4 `grounding_prefs(node_id,…)`). Scene-links have FK guards; the **new** stores (grounding_prefs, world-map positions by entity_id) need cleanup-on-delete or tolerate-orphan reads. *Fix: define cascade/cleanup for each new store; default to tolerate-orphan + lazy GC.*

**🟡 AH-8 (LOW) — scale + cross-pipeline + media-shape.** (a) RelMap/WorldMap N+1 entity-detail reads + outline virtualization at 200-chapter scale (deferred graph endpoint). (b) Provenance marks ride in chapter content consumed by raw-search / translation / wiki — confirm they tolerate an unknown mark (raw-search extracts text, fine; verify translation/pandoc). (c) World-map backdrop reuses **chapter**-keyed book media (`uploadChapterMedia`) but a backdrop is **book/work**-level — needs a book-level media slot or a sentinel-chapter convention. **Touches T5.3, T2.5, T2.2.**

**🟡 AH-9 (LOW) — no co-writer concurrency story.** Two devices generating into the same scene → two drafts, last-write-wins (S4). Acceptable for single-author; document it.

---

## Part 3 — Edge-case matrix

| # | Edge case | Affected | Expected behavior | Status |
|---|---|---|---|---|
| E1 | No entities / no events / no outline / no canon | all read-panels | coordinated empty states + bootstrap hint | R1 |
| E2 | Chapter with **no decomposed scenes** | co-writer, T3.2/T3.3 | must still write/continue (AH-1) | **AH-1** |
| E3 | Spoiler cutoff at chapter 1 (no prior) / last chapter (all visible) | T2.1/2.3/2.4 | empty-before / full timeline; no off-by-stride | R4 |
| E4 | Entity merged/renamed after a pin set | T3.4, T2.x | resolve through canonical id, tolerate missing | AH-6 |
| E5 | Archive a scene that's a scene-link endpoint / beat-mapped / pinned | T1.2/1.3/3.4 | cascade cleanup or tolerate-orphan | AH-7 |
| E6 | Knowledge-service down mid-session | 6 panels | uniform degrade, shell survives, writing works | AH-5/R3 |
| E7 | Pop a streaming co-writer / chat panel to an OS window | T5.4 | stream survives OR explicit re-init | **AH-2** |
| E8 | Very long selection for rewrite | T3.2 | cap + message; doesn't blow the token budget | spec'd |
| E9 | Unanchored knowledge entity / glossary entry with no KG entity | T2.1/2.2 | render gracefully; id-space resolution | AH-4 |
| E10 | AI text edited by human, then re-AI'd over it | T5.3 | provenance split/keep rule (spec'd: keep-AI-until-reviewed) | spec'd |
| E11 | Two devices: same outline node edit | T1.1 | 412 → refetch + toast | spec'd |
| E12 | Backdrop image deleted from book media; location entity deleted | T2.5 | broken-image fallback; drop the place node | AH-7/8 |
| E13 | Re-extraction shifts event_order while a Timeline is open | T2.3 | refetch/settle; positions are not cached stale | AH-6 |
| E14 | Generate into a scene while the inline ghost from a prior gen is unaccepted | T3.3 | one active ghost per scene; replace or block | add to T3.3 |

---

## Part 4 — Recommendations

- **R1 — Coordinated empty/bootstrap state.** One shared "knowledge not ready" component + the "run an extraction" CTA, reused by all read-panels (S1, E1).
- **R2 — One graph-layout-persistence rule.** Decide per-device vs server for Scene-Graph **and** World-Map positions (currently split) (S3).
- **R3 — Shared knowledge-degrade boundary** (`useKnowledgeQuery` + error boundary) (S5, AH-5).
- **R4 — One axis-conversion module** (story_order ↔ event_order×STRIDE ↔ sort_order ↔ block_index) + tests; every cross-axis feature consumes it (S7, AH-3, MED-3).
- **R5 — Canonical entity id for composition** = glossary `entity_id`, resolved to knowledge via `glossary_entity_id`; define unanchored/unlinked behavior (AH-4).
- **R6 — Decide AH-1 + AH-2 before building T3.2/T3.3/T5.4** (the two HIGHs need a design call, not a build-time discovery).
- **R7 — Tolerate-orphan everywhere** for stored refs (grounding-prefs, world-map, cast selections) + lazy GC on delete (AH-6/7).

## Part 5 — Verdict & sign-off readiness

The V1 design is **architecturally sound for the write-surface + structure + canon core**, and the world/knowledge panels are well-specced **once** the four systemic items are addressed. **Two HIGHs (AH-1 co-writer scene-coupling, AH-2 pop-out vs no-unmount) are genuine design decisions** that should be made now — building T3.2/T3.3/T5.4 without them risks a build-time dead-end. The MEDs are mitigations to fold into the relevant specs; the LOWs are documented for the build.

**Decisions made (2026-06-11):** AH-1 → a selection-scoped endpoint (T3.2) + a cursor→scene/chapter resolver (T3.3); AH-2 → hoist live state to a shared owner, OS-popped windows are thin synced views (T5.4). R1–R7 folded into the program's cross-cutting + architecture-review decisions. **The design set is build-ready** (pending PO sign-off).
