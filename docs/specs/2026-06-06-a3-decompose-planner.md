# A3 — `decompose` planner + adaptive K (DESIGN SPEC)

> **Track:** LOOM · **Milestone:** Composition V1 Phase-A **A3** (the last Phase-A slice).
> **From:** [`2026-06-05-composition-v1-phase-a.md`](../plans/2026-06-05-composition-v1-phase-a.md) §A3 + [`2026-06-05-composition-v1-reasoning-engine.md`](2026-06-05-composition-v1-reasoning-engine.md) §3 (`decompose`), §8.3, **D3** (adaptive K), F5/F6.
> **Size:** XL · **Workflow:** v2.2 (NOT /amaw — composition-only, no cross-service writes).
> **Status:** DESIGN (this doc) + PLAN → /review-impl → design-checkpoint commit. BUILD deferred to a fresh session (XL-checkpoint pattern).

## Goal (one line)
Push complexity **upstream into the plan** (DOC/F5: +22.5% plot coherence): a `decompose` planner turns *premise + a structure template + the book's existing chapters + its cast* into **scene outline nodes** carrying `beat_role + tension + present_entities`; **adaptive K** then spends more diverge candidates on high-tension beats and fewer on connective ones — replacing A1's fixed `compose_diverge_k`.

## Locked CLARIFY decisions (2026-06-06)
1. **Single milestone** — planner + adaptive-K ship together, one eval-gate, one commit.
2. **Multi-level arc→chapter→scene**, top-down conditioned (F6).
3. **Beats = chapters** — a structure template's beats map onto **existing book chapters** (1 beat ↔ 1 chapter, in order); the planner then decomposes each chapter into scenes.
4. **Map onto EXISTING book chapters** — decompose does **NOT** create book chapters. The author creates chapters in the book UI first; A3 is **composition-only** (BookClient stays read-only). No `/amaw`.
5. **Planner LLM emits per-scene `tension`** (1–5) as structured output — not a static recipe curve.
6. **Preview → author commits** — the decompose POST returns a proposed tree WITHOUT persisting; a separate commit POST writes the accepted (possibly edited) nodes.

## Schema constraints this design MUST respect (from `migrate.py`)
- `outline_node.kind IN ('arc','chapter','scene','beat')`.
- `CHECK (kind NOT IN ('chapter','scene') OR chapter_id IS NOT NULL)` — **chapter + scene nodes require a real book `chapter_id`.** (Why decision #4 is composition-only: we reuse existing book chapter ids, never mint them.)
- `CHECK (beat_role IS NULL OR kind = 'scene')` — **`beat_role` is scene-only.** The beat identity therefore lives on the **scenes** (each scene carries its parent beat's role), and on the optional `chapter`-kind grouping node it lives in `title`/`goal`, not `beat_role`.
- `tension SMALLINT` — scene tension; we use **1–5**.
- `present_entity_ids UUID[]` — must be resolved glossary entity ids (unmatched names dropped + logged; we cache the stable glossary `entity_id`, never the rename-sensitive knowledge canonical_id).

## Committed tree shape
```
arc      (kind='arc', one per decompose run; chapter_id NULL ok; title=structure name)
└─ chapter (kind='chapter', chapter_id=<existing book chapter>, beat_role NULL,
            title/goal carry the beat label+intent)        ← one per mapped beat/chapter
   └─ scene  (kind='scene', chapter_id=<same book chapter>, beat_role=<beat key>,
              tension=1..5, goal+synopsis=intent, present_entity_ids=[glossary ids],
              status='outline', rank, story_order)          ← N per chapter (LLM)
```
`beat_role` on the **scene** = its chapter's beat key (the constraint forbids it on `chapter`). The `arc` and `chapter` nodes are the navigational spine; the `scene` nodes are what `/generate` consumes.

## The `decompose` primitive (`engine/plan.py`, new)
Two LLM levels, top-down (each grounds the next). Reuses the extraction/critic **tolerant structured-output** pattern (fence-strip + first-balanced-object + filter; `extract_judge_content` for the gateway `messages[0].content` shape — the gateway-response lesson).

**Inputs gathered (all reads, composition already wired except one new BookClient method):**
- Book chapters in order — **NEW `BookClient.list_chapters(book_id, bearer) → [{chapter_id, title, sort_order}]`** (wraps the existing gateway `GET /v1/books/{book}/chapters`; `get_chapter_sort_orders` is insufficient — it needs ids first).
- Cast roster — `GlossaryClient.list_entities(book_id, …) → [{entity_id, name, kind}]` (existing). Passed into the scene prompt as the allowed cast; the planner emits names, we map back to ids.
- Structure template — `StructureTemplatesRepo.get(template_id)` → ordered beats `[{key,label,purpose,order}]` (existing 6 seeds).

**Level 1 — arc→chapter mapping (1 LLM call, structured):**
Align the template's `B` beats to the book's `C` existing chapters in order, and write a chapter-level **intent** per chapter grounded in the premise + beat purpose. Reconciliation when `B ≠ C` (see Risks): the LLM is given both lists and asked to assign each existing chapter exactly one `beat_role` (the closest beat by position/role) + a 1-line chapter intent. Output: `[{chapter_id, beat_role, intent}]` for every existing chapter (never drops a chapter — the no-silent-drop rule).

**Level 2 — chapter→scenes (1 LLM call per chapter, or batched; structured):**
For each chapter, conditioned on its intent + beat purpose + premise + cast roster, emit `S` scenes: `{title, intent (synopsis), tension(1-5), present_entities:[names]}`. `S` is LLM-chosen within `[plan_min_scenes_per_chapter, plan_max_scenes_per_chapter]` (config). Tolerant per-scene parse: a malformed scene is dropped, the chapter keeps its good scenes (the LLM-schema-tolerate-filter lesson).

**Cost/limits:** Level-2 is `C` calls (one per chapter). Bound `C ≤ plan_max_chapters` (config; refuse/clamp larger books with a clear error) and run Level-2 with bounded concurrency (`asyncio.gather` like `diverge`, but capped — don't fan out 200 calls). Budget pre-check covers the planner spend.

## Adaptive K (`engine/adaptive_k.py` or a fn in `plan.py`)
```
adaptive_k(beat_role, tension, *, k_ceiling=compose_diverge_k) -> int
```
- Primary signal = **tension** (the planner's per-scene 1–5): `tension >= plan_high_tension_threshold` (default 4) → `k_ceiling`; mid (3) → `min(2, k_ceiling)`; low (1–2) → `1`.
- Secondary = **beat_role class**: a small set of high-weight beat keys (climax/midpoint/crisis/finale/ordeal/all_is_lost/ten/setback/payoff…) bumps a mid-tension scene up one. A closed `HIGH_WEIGHT_BEATS` set, documented; unknown keys contribute nothing (no guess).
- Always clamp to `[1, k_ceiling]`. K=1 degenerates to the V0 single-draft loop (free).
- **Wiring:** [engine.py:227](../../services/composition-service/app/routers/engine.py#L227) replaces `k=settings.compose_diverge_k` with the adaptive value. When a node has no `beat_role`/`tension` (hand-authored, pre-A3) → fall back to `compose_diverge_k` (unchanged behavior — no regression for existing outlines). Co-write path unchanged; auto path uses the adaptive schedule (D3).
- **⚠ ORDERING (REVIEW design HIGH#1):** K now *varies per scene*, and the auto path runs a **budget pre-check that reserves for K candidates up front** (§5 / A1 cost-guard). So `adaptive_k(...)` MUST be computed **right after the outline node is loaded, BEFORE the budget reservation**, and the SAME value threaded into both the budget check and `select_draft(k=…)`. Computing it at the old fixed-K call site (after the reservation) would reserve the wrong amount → over/under-spend. BUILD: hoist the K computation above the budget pre-check; assert in a test that the reserved K == the K passed to `diverge`.

## API contract (composition-service, gateway-proxied under `/v1/composition`)
1. **`POST /works/{project_id}/outline/decompose`** — body `{structure_template_id, premise, scenes_per_chapter_hint?}`. Gathers inputs, runs Level 1 + Level 2, returns the **preview tree** (NOT persisted): `{arc_title, chapters:[{chapter_id, title, beat_role, intent, scenes:[{title, synopsis, tension, present_entity_ids, present_entity_names_unresolved:[], suggested_k}]}]}`. `suggested_k` previews adaptive K so the author sees the spend. Degrade: a chapter whose Level-2 call fails returns `scenes: []` + a `warning` (never 500 the whole plan).
2. **`POST /works/{project_id}/outline/decompose/commit`** — body = the accepted tree (the author may have edited titles/tension/cast/scene set). Persists arc + chapter + scene nodes in rank order (reuse `OutlineRepo.create_node` + `rank.py` between-ranks; consider a `create_nodes_bulk` for one round-trip). **Idempotency/safety:** refuse to commit scenes onto a chapter that already has outline scenes unless `replace=true` (avoid double-planning); validate every `chapter_id` belongs to the book (IDOR) and every `present_entity_id` is a real glossary id for the book. Returns created node ids.

Both require the Work (M2 `_require_work`) + JWT ownership (the gateway forwards it; book/glossary reads are user-scoped server-side).

## Eval-gate (ship only if A3 ≥ A1 on coherence)
`scripts/eval_a3_decompose.py` (host-orchestrated, mirrors `eval_a1_diverge.py`): for a fixed premise + a book with N existing chapters, compare **A3** (decompose → commit → `/generate auto` per scene, adaptive K) vs **A1** (bare hand-outline scene → `/generate auto`, fixed K=3) on the disjoint-judge **coherence** median (+ a cheap **outline-relevance** dim — does the scene serve its beat intent?). The DOC result predicts a coherence lift from tighter upstream constraints. Report wall-clock + total K spend (adaptive should spend *less* than fixed-K×scenes while holding coherence — the efficiency win). **Honest-finding stance (A1 lesson):** if coherence saturates on short scenes, report it; the discriminating signal may be outline-relevance, not coherence-median.

## Files (≈11)
**New:** `engine/plan.py` (decompose L1+L2 + prompts) · `engine/adaptive_k.py` (or fold into plan.py) · `routers/plan.py` (or add to `routers/outline.py`) decompose + commit endpoints + request/response models · `scripts/eval_a3_decompose.py`.
**Changed:** `clients/book_client.py` (`list_chapters`) · `routers/engine.py` (adaptive-K wire) · `config.py` (`plan_max_chapters`, `plan_*_scenes_per_chapter`, `plan_high_tension_threshold`) · `db/repositories/outline.py` (optional `create_nodes_bulk`) · `deps.py` (wire the planner deps) · gateway `pathFilter` (confirm `/v1/composition/works/*/outline/*` already proxies — likely yes) · tests (planner parse/reconcile, adaptive-K table, endpoint preview+commit+IDOR, engine fallback).
**No schema migration** (all fields exist). **No knowledge-service, no book-service writes, no lore-enrichment.**

## Risks / open
- **B≠C beat↔chapter reconciliation** (BOTH directions) — every EXISTING chapter gets exactly one `beat_role` (closest by normalized position); never drop/invent a chapter.
  - **B>C** (15-beat Save-the-Cat onto a 6-chapter book): surplus beats unused → surfaced in the preview as `unmapped_beats` (author splits chapters then re-decomposes).
  - **C>B** (more chapters than beats): legitimate — **multiple consecutive chapters share the same `beat_role`** (a beat spans several chapters). Not an error; the planner distributes beats across the chapter run.
- **REVIEW design MED#1 — `chapter`-kind node materialization.** Today scenes attach to `chapter_id` directly with no `chapter`-kind parent (A1/A2 created scenes with `chapter_id` + null parent). The packer/spoiler/canon paths key on **`chapter_id` + `story_order`, NOT the parent chain** (pack.py) — so the arc/chapter nodes are **navigational only**, nothing downstream depends on them. BUILD: materialize a `chapter`-kind node per mapped book chapter for the tree spine, but **guard against duplicates** (existence check on `(project_id, chapter_id, kind='chapter')` — there's no DB unique) and confirm setting `scene.parent_id = chapter-node.id` doesn't break any sibling-rank/query assumption. If materializing chapter nodes proves fiddly, the fallback is arc + scenes-grouped-by-`chapter_id` (chapter nodes omitted) — still satisfies the author-facing arc→chapter→scene view since scenes group by their book chapter.
- **REVIEW design LOW#1 — glossary auth.** Confirm at BUILD whether `GlossaryClient.list_entities` on the composition side authenticates via the **internal service token** or the forwarded **JWT** (the decompose endpoint holds the JWT; the existing `select_for_context` path may use the internal token). Use whichever the existing client method already does — don't introduce a second auth mode.
- **Planner cost** — `C` Level-2 calls; bound + cap concurrency; measure wall-clock in the eval (the local-LLM cost risk from §A3 open).
- **present_entities resolution** — planner emits names; fold via the glossary roster (case/canonical match). Unmatched → dropped + surfaced as `present_entity_names_unresolved` so the author can fix, not silently lost.
- **Commit re-run** — guarded by `replace` flag; default refuses to double-plan a chapter.
- **Adaptive-K table is a heuristic** — the eval validates the *schedule* (does spending K on high-tension beats actually lift coherence there?), not just the planner. If adaptive ≈ fixed, that's a real finding.
