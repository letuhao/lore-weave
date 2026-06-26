# Frozen Contracts — Composition Debt-Clearing (parallel build)

- **Status:** FROZEN 2026-06-26 (DESIGN deliverable; unblocks parallel lanes per
  [`2026-06-26-composition-branch-clearing.md`](2026-06-26-composition-branch-clearing.md) §Parallelization Step 1).
- **Branch:** `feat/composition-debt`. **Grounded** by 4 read-only research passes over current code (line refs inline).
- **Rule:** lanes build against these shapes as stubs. A lane that needs to change a frozen shape STOPS and renegotiates here first.

> **Two plan assumptions corrected by grounding (binding):**
> 1. **M6** — knowledge has **no** `lore`/`canon-rules` windowed endpoints; only `timeline`, `entities/statuses`,
>    `entities/{id}/facts` (all public, `before_chapter_id`→`resolve_before_order` fail-closed). Glossary
>    `known-entities` is `/internal` only and there is **no chapter→entities** route. The **gateway is a pure
>    prefix proxy** (`/v1/glossary`, `/v1/knowledge` already proxied) → **no gateway change**; M6 adds **public**
>    glossary handlers gated by `requireUserID`+`requireGrant(GrantView)`.
> 2. **M7** — the per-chapter `chapter_links` producer is **translation-service** `extraction_worker.py:690-701`
>    (`_accept`), NOT knowledge `pass2_writer.py`. L-xsvc = glossary Go migration + **translation-service** producer.

---

## Contract 1 — M1 `adapt_scene` op (composition-service)

**No endpoint or schema change.** `GenerateBody.operation` is a free-form `str` (engine.py:89-112), and
`build_messages` falls back to a generic instruction for unknown ops without raising (cowrite.py:92). So:

- **New op key:** `adapt_scene` added to `_OPERATION_INSTRUCTIONS` (cowrite.py:28-39). Instruction:
  *"Adapt the SOURCE scene's prose to this branch: keep its structural function, but rewrite it to honour the
  divergence and entity overrides. Do not copy the source verbatim."*
- **Generate body (unchanged shape):** `{ outline_node_id, model_source, model_ref, operation: "adapt_scene",
  mode: "auto", model_kind, model_name, reasoning }`. Plan-free: does not require a derivative scene-plan.
- **FE call (additive, no api.ts shape change):**
  `compositionApi.generateAuto(projectId, { outlineNodeId, operation: 'adapt_scene', modelRef, modelSource, modelKind, modelName })`
  (api.ts:325-345 already passes `operation` through).
- **Internal wiring (L-be detail, not a public contract):** `pack()` must become op-aware so it fires the new
  `gather_source_scene` lens **only** for `adapt_scene` (the normal pack is untouched for every other op). Thread
  `operation` into `PackRequest`; in the `is_derivative` branch (pack.py:202-222, 327-368) call
  `gather_source_scene(book_id, source_chapter_id, branch_point)` reading `book.get_draft` on the **shared**
  `book_id`, spoiler-bounded to ≤ the scene's position. Overrides already flow via `DerivativeContext.overrides`
  (pack.py:118-166).
- **Output:** ghost (`persist:false`) — same surface as a `draft_scene` what-if take.
- **Offer gating (FE):** only on a **derivative**, only on a scene **at/after `branch_point`** that has a **source
  counterpart**; a post-branch new scene with no source → fall back to `draft_scene` (don't offer adapt).

## Contract 2 — M3 scene-prose persist endpoint (composition-service)

**New route:** `POST /v1/composition/works/{project_id}/scenes/{node_id}/prose`

- **Grounding correction:** there is **no `scene_draft` table** and **no per-`(project_id, node_id)` write path**;
  scene prose lives only in `generation_job.result.text`, read back by `prior_scene_drafts` /
  `chapter_scene_drafts` (generation_jobs.py:368-427). The existing `POST /jobs/{id}/persist` is **chapter-only**
  (422 `JOB_NOT_PERSISTABLE` for a per-scene result, engine.py:1347-1354) → cannot be reused.
- **Storage mechanism (frozen decision):** the endpoint writes a **synthetic completed `generation_job` row** in
  the **derivative** project, keyed by `outline_node_id`, with `result = { text }` and an input marker
  `{ kind: "promoted_scene_prose" }`. This makes the prose visible to `gather_recent`'s fallback
  (lenses.py:262) and the studio's scene-draft reads **with no new table**. **Idempotent on `node_id`:** upsert
  (delete-existing-promoted-then-insert, or a partial unique index on `(project_id, outline_node_id)` where the
  marker is set) so a re-promote / double-submit overwrites, never duplicates.
- **Request:** `{ "text": string, "idempotency_key"?: string }` (`text` = ghost plain text; empty/whitespace →
  **422 `EMPTY_SCENE_PROSE`**, caller skips that scene).
- **Response 200:** `{ "node_id": UUID, "persisted": true, "version": int }`.
- **Auth/scope:** EDIT grant on the book; `project_id` must be a **derivative** owned by the caller. **Source-clobber
  guard (critical):** writes ONLY to the derivative project's synthetic-job store — NEVER `book.patch_draft`
  / `book.get_draft(shared_book_id, …)`. (Test: source chapter draft byte-identical after promote.)
- **Format:** ghost is plain text; persist as `result.text` (newline-paragraph form `prior_scene_drafts` already
  splits on). No Tiptap/JSON conversion needed for this store.

## Contract 3 — M6 canon-at-chapter read surface

**Reuse (already public, no change):**
- `GET /v1/knowledge/timeline?before_chapter_id={uuid}` (timeline.py:78)
- `GET /v1/knowledge/entities/statuses?before_chapter_id={uuid}` (entities.py:541)
- `GET /v1/knowledge/entities/{entity_id}/facts?before_chapter_id={uuid}` (entities.py:631)
  All resolve via `resolve_before_order` and surface `window_available` (fail-closed `-1` ceiling when the
  chapter is unresolvable — surface as "window unavailable", never an unwindowed whole-book leak).
- `GET /v1/composition/works/{project_id}/scenes/{node_id}/grounding` — existing public windowed pack (reuse for
  the derivative-branch-point case; it already handles the derivative branch).

**New public glossary handlers (added on glossary-service, gated `requireUserID` + `requireGrant(GrantView)`,
mirroring `listChapterLinks` chapter_link_handler.go:83-110 — NO gateway change, prefix already proxied):**

1. `GET /v1/glossary/books/{book_id}/known-entities?before_chapter_index={int}&min_frequency={int}&limit={int}`
   — public mirror of the internal handler (extraction_handler.go:203-360). Response (bare array):
   ```json
   [{ "entity_id": "uuid", "name": "str", "kind_code": "str", "aliases": ["str"], "frequency": int,
      "first_chapter_index": int|null, "last_chapter_index": int|null, "coverage_pct": float }]
   ```
   (first/last/coverage folded in from the `entities/stats` aggregate, entity_stats_handler.go:78-92.)
2. `GET /v1/glossary/books/{book_id}/chapter-entities?chapter_id={uuid}` — **new query direction** (chapter→entities,
   using `idx_cel_chapter`). Response (bare array):
   ```json
   [{ "entity_id": "uuid", "name": "str", "kind_code": "str", "relevance": "major|appears|mentioned",
      "chapter_index": int|null, "mention_count": int }]
   ```
   (`mention_count` is 0 until M7 lands; the field is present in the frozen shape so M6-FE doesn't re-break.)

**Tenancy:** both new routes filter by `book_id` + caller grant; under-grant → uniform `403 GLOSS_FORBIDDEN`
(no existence oracle). Label glossary-sourced **presence** vs knowledge-sourced **facts/statuses** distinctly in
the panel (two stores, may disagree — don't silently merge).

## Contract 4 — M7 `mention_count` (glossary + translation-service)

1. **glossary migration** (additive, forward-only — no down-migration, migrate.go):
   `ALTER TABLE chapter_entity_links ADD COLUMN mention_count INT NOT NULL DEFAULT 0;`
   Keep `UNIQUE(entity_id, chapter_id)` (count is *within* the chapter). The `trig_cel_snapshot` trigger will
   capture the new column — extend the snapshot JSONB builder only if surfacing in entity-detail (optional).
2. **`chapterLinkIn` struct** (glossary extraction_handler.go:437-442) gains:
   `MentionCount int \`json:"mention_count"\`` and the upsert (extraction_handler.go:783-790) adds it to the
   INSERT cols + `ON CONFLICT … DO UPDATE SET mention_count = EXCLUDED.mention_count`.
3. **`chapterLinkResp`** (entity_handler.go:29-38) gains `mention_count int` (so the per-entity chapter-links read
   and the M6 `chapter-entities` route expose per-chapter counts to the FE heatmap).
4. **producer** = **translation-service** `extraction_worker.py:690-701` (`_accept`): compute per-chapter
   `mention_count` with a **CJK-aware longest-match** over canonical + aliases, **presence-gated** (count only in
   chapters the entity is linked to), with **span-dedup** (longest-match so "Harker" inside "Jonathan Harker" is
   one mention). `_merge_window_entities` (extraction_worker.py:164-184): **SUM** `mention_count` across windows of
   the same `chapter_id`. **Canonical + alias surface forms only** (per CLARIFY; per-chapter alias breakdown stays
   out of scope).
5. **backfill:** deterministic recount job over existing books (no LLM), batched + idempotent, default 0.
6. **staleness:** a chapter edit recounts via the chapter-update path. **stats semantics unchanged** in M7
   (`entity_stats_handler` `mention_count` stays link-row/chapters-present count; the new per-chapter frequency is
   a distinct field on the chapter-link rows).
7. **FE:** `useMentionHeatmap` windows on per-chapter `mention_count` ≤ cutoff (replacing the whole-book scalar);
   guard cutoff resolution like M6; clear the `D-T5.2-WINDOWED-MENTIONS` note.

---

## SceneGraphCanvas extension points (single owner = L-canvas, sequenced M4→M3-FE→M6-mount→M5b)

`features/composition/components/SceneGraphCanvas.tsx` (382 lines). Plug-in sites (exact lines):

| Pt | Milestone | Site | Anchor / data already present |
|----|-----------|------|-------------------------------|
| (a) | **M4** judge badge | **363-367** (preview-strip `previewAlt.take.judge` span) + `WhatIfAltNode` render **337-344** | dims = `Critic.{coherence,voice_match,pacing,canon_consistency}` 0-5 ints \| null (types.ts:288-304); take ghost at 376 |
| (b) | **M3** promote-prose persist | **121-134** (the `createNode` seed loop; line **128**) | currently seeds scene *nodes* only — after each `createNode`, call Contract 2 with the chosen take's ghost (best-effort per scene, count toast) |
| (c) | **M5b** mobile-canvas wrapper | wrap `<GraphCanvas>` block **300-355** (root `data-testid="composition-graph"` opens **209**) | shared host `GraphCanvas.tsx` (add touch/pinch + `zoomable`); precedent `useIsMobile` + KnowledgePage 51-56 |
| (d) | **M6** branch-point inspector mount | after preview strip (**~378**) or the what-if bar **255-292** | `anchorScene` / `anchorChapterSort` precomputed **85-97**; L-m6panel provides `<CanonAtChapterPanel>` as a prop/slot, L-canvas wires the mount |

**Shared heavy-canvas host** (M5b): `GraphCanvas.tsx` (used by Scene Graph 300, Relationship Map 84, World Map 167;
**Timeline is a hand-rolled SVG**, TimelineView.tsx — its own mobile pass). `GraphCanvas` already has opt-in
`zoomable` (wheel-zoom/pan, ZOOM_MIN 0.3/MAX 2.5) but **no touch/pinch** — M5b adds `touch-action` + pinch + tap→
bottom-Sheet, gated on `useIsMobile` (hoist to `@/hooks/useIsMobile`).

## Lane / coordination corrections (supersede the plan's §Step 2 where noted)

- **L-xsvc (M7-BE)** = glossary Go migration + **translation-service** producer (`extraction_worker.py`) +
  glossary upsert/response. (NOT knowledge-service.)
- **L-m6panel (M6)** = new `CanonAtChapterPanel` (isolated new file) + **2 new public glossary handlers** +
  knowledge/grounding reuse. **No gateway change.** Panel registration in `CompositionPanel` (PANEL_IDS + DockSlot)
  is the one coordination edit with **L-mobileshell** (M5a) — m6 registers, mobileshell consumes the list.
- **L-be (M1/M3-BE)** = composition-service Python: `cowrite.py` (op), `lenses.py` (`gather_source_scene`),
  `pack.py` (op-aware wire), new scenes/prose endpoint + synthetic-job store. No FE overlap.
- **L-chat (M2)** = chat feature only; first extract a pure `runChatStream(args, token, cb, signal)` (the inline
  switch in `useChatMessages.streamPost:254-394` — 7 handled AG-UI cases + 9 framing no-ops + the resume/tool-result
  override path), then `chatStateHub` + worker shell + `useSharedChatStream` + `ChatLiveStateProvider`, mirroring
  `liveStateHub`/`useSharedCompositionStream`. Re-fire `onStreamEnd`/`onMemoryMode`/`onStreamDelta` closures in the
  consumer (worker can't hold them). New chat windowing selector (none exists yet).
- **L-i18n (M0)** = DONE (committed, parity 18/18).
