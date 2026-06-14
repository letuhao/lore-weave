# Translation Panel Overhaul — Design Spec

> Status: **DESIGN PARKED (design-reviewed; build deferred by user 2026-06-15)** · branch `feat/auto-draft-factory-gaps`
> Scope: two deferred "big features" for the translation panel, plus two QoL folds. Design-only; BUILD is RAID-safe (translation code is **not** RAID-owned — see §7) and can follow when prioritized.
>
> **Deferred tasks (tracked):** `D-TRANSL-PANEL-T1-CORRECTION` (T1 — split correction panel, B-first), `D-TRANSL-PANEL-T2-SCENE-SPLIT` (T2 — persisted scene-split model, XL/cross-service/+amaw), `D-TRANSL-PANEL-T1A-PER-BLOCK` (T1-A per-block patch, after T2).

## 0. Origin

User flagged two deferred big-features around the "split translation panel" that were set aside during the RAID run. CLARIFY selected four capability areas and collapsed them into **two tasks**:

- **T1 — Split Correction Panel** = (split-view editor) + (inline correction → learning)
- **T2 — Persisted scene-split translation model** = (chapter split for translation) + (matrix redesign)

CLARIFY + design-review decisions (2026-06-15):
- **T1 edit model:** spec presents BOTH per-block-patch (BE) and reuse-full-version-save (FE-only); recommended sequence **T1-B → T2 → T1-A** (§3.3, §5).
- **T2:** **persisted scene-split model (BE)** — the real big feature, extends the existing `scenes` table.
- **Scene generation for `.txt`:** **heuristic split (S-a)** chosen — cheap, deterministic, persisted with `content_hash`, runs over the whole corpus without LLM cost (§4.2). LLM semantic split (S-b) reserved as a later quality upgrade.
- **Build:** **parked** — design reviewed, build deferred until prioritized.

## 1. Current surface (build ON this, do not rebuild)

### 1.1 UI (all RAID-free)
| Piece | State |
|---|---|
| `features/translation/components/SplitCompareView` | original ↔ translation split, block- **and** text-aligned — **read-only** |
| `TranslationViewer` + full-version edit (M7c-2 shipped) → `versionsApi.saveEditedVersion` creates an `authored_by='human'` version, capturing the LLM↔human diff as learning gold | shipped |
| `BlockAlignedReview` (per-block review, keyboard nav, empty-block detection) in `TranslationReviewPage` | shipped |
| `ConfirmNameDialog` (M6a glossary name correction → patches glossary + flags book translations stale) | shipped |
| `TranslationTab` coverage matrix + `coverageClassify` lib | shipped |
| `TranslateModal` job wizard (smart classify, paging, V3 verifier, force) | shipped |

### 1.2 Data model (the decisive finding)
- **`scenes` table already exists** (book-service, P1 structural decomposition): `id, chapter_id, sort_order, path, leaf_text, content_hash, parse_version, lifecycle_state`. Created at **import parse** for `.docx/.epub`. Exposed via `GET /internal/books/{book_id}/chapters/{chapter_id}/scenes`; consumed by knowledge-service P2/P3 extraction.
- **`chapter_blocks`** = trigger-extracted Tiptap block text-index (for raw-search); scene-agnostic.
- **`chapter_translation_chunks`** (translation-service) = **ephemeral** token-bounded chunks per translation job; no cross-job identity, not block-aligned.
- **Translated body**: V2 `translated_body` (flat text); V3 `translated_body_json` (Tiptap) + `translated_body_format`. **No persisted per-block identity** (Tiptap reconstructed client-side).

### 1.3 ⚠️ The legacy gap that shapes T2
`scenes` are populated **only** for parsed `.docx/.epub` imports. Plain `.txt` bulk-imported chapters (the user's 4232-file CJK novel, via the new `bulkCreateChapters` path) have `structural_path = NULL` → **zero scenes**. So a scene-split translation model is useless for the primary corpus unless we add **scene generation for plain-text chapters** (§4.2). This is the single biggest scope driver in T2.

## 2. Goals & non-goals

**Goals**
- G1: Let a user fix a translation **at paragraph/scene granularity** in a side-by-side panel, not only by re-editing the whole version.
- G2: Every human correction becomes learning gold (extend the M7b/M7c signal wiring).
- G3: Translate & track status **per scene** so long chapters (13K+ tokens) are reviewable/correctable/re-translatable in parts.
- G4: Matrix scales to 2000+ chapters (fix the `limit:200`→100 clamp) and exposes per-scene drill-down.

**Non-goals**
- Online LLM-judge of fidelity (M7d) — out of scope; the panel reserves slots for issue badges but does not compute them.
- Re-architecting the V3 pipeline's internal chunking; we change the **unit boundary** (scene), not the agent loop.
- Touching composition / ChapterEditorPage / authoring.

---

## 3. T1 — Split Correction Panel

### 3.1 UX
- Promote `SplitCompareView` from read-only to an **editable correction surface** (or a sibling `SplitCorrectionView` so the read-only compare stays for pure reading — see §3.4).
- Left pane = source (read-only, the anchor). Right pane = translation, **per-block/scene editable** (Tiptap for JSON format, textarea for text format), aligned row-by-row with the source like `BlockAlignedReview`.
- Per-row affordances: **edit-in-place**, **re-translate just this block/scene** (small job), **glossary term highlight + quick-confirm** (reuse `ConfirmNameDialog`/`useConfirmName`), and **reserved issue-badge slot** (populated later by M7d; for now only the existing empty/missing-block detector lights it).
- Save → produces a human-authored result wired to learning (§3.5). A dirty-row indicator + single "Save corrections" action.

### 3.2 Reuse
`BlockAlignedReview` already gives row alignment + keyboard nav + empty detection; `useEditTranslation` already owns edit state + format-aware editors; `saveEditedVersion` already persists human gold. T1 is mostly **wiring edit affordances into the aligned view** + the save granularity decision below.

### 3.3 Edit-model options (decision at design review)
**Option A — per-block/scene patch (needs BE).**
- New endpoint, e.g. `POST /v1/chapters/{id}/versions/{vid}/blocks/{blockOrSceneRef}` (or a batch patch), updating just the targeted unit and recomputing the version body.
- Learning gold captured **per block/scene** (finer signal: "this paragraph, LLM said X, human said Y").
- Requires persisted per-unit identity → strongly favors landing **after** T2's scene model (scene_id is the stable patch key); without scenes, block_index is the key but block_index drifts if the source is re-blocked.
- Bigger scope (BE+FE), truest "correction panel".

**Option B — reuse full-version save (FE-only).**
- Inline edits accumulate client-side; "Save corrections" calls the existing `saveEditedVersion` with the whole edited body → one new `authored_by='human'` version.
- Zero BE work; learning gold at version granularity (already working).
- Loses per-paragraph diff signal and per-block re-translate-and-keep-rest.

**Recommendation:** ship **B first** (fast, FE-only, immediately useful), then **A as a follow-up once T2 lands** (scene_id gives a stable patch key and per-scene learning gold for free). Sequencing A after T2 avoids the block_index-drift fragility.

### 3.4 Stateful-component rule
Do **not** ternary-swap between read view and edit view (destroys editor state). Use one mounted editable component with an internal `editing` branch, or CSS-hide — per the project's "never conditionally unmount stateful components" rule.

### 3.5 Learning wiring
Per `2026-06-08-translation-feedback-to-learning.md`: human corrections emit `source=human` gold. Option B already does this via `saveEditedVersion`. Option A adds per-block gold. Glossary quick-confirm continues to flow through `useConfirmName` (glossary patch + stale flag). No new learning subsystem — just feed the existing one.

---

## 4. T2 — Persisted scene-split translation model

### 4.1 Principle: extend `scenes`, don't duplicate
Scenes are already the structural SSOT (P1) and already consumed by extraction (P2/P3). Translation joins the same unit.

### 4.2 Scene generation for plain-text chapters (the legacy gap, §1.3)
Make scenes exist for `.txt` chapters so the model is universal. **Chosen: S-a (heuristic split).**
- **S-a: heuristic split (CHOSEN)** — paragraph/heading/length-bounded split of the draft text (cheap, deterministic, mirrors the chunk_splitter boundary logic but **persisted** as scenes with `content_hash`). Runs over the whole 4232-chapter corpus without LLM cost.
- **S-b: LLM semantic split** — an MCP/agentic scene-segmentation tool (narrative-aware). Higher quality, costs tokens, must go through ai-gateway per the MCP-first invariant. **Reserved as a later quality upgrade**, not in the first build.
- **S-c: on-demand** — generate scenes lazily the first time a chapter is opened in the panel / translated, not for all up front. (Can layer on top of S-a if up-front backfill is too heavy.)
- Must be **idempotent + re-runnable** (re-import / draft edit → re-split dirty chapters via `content_hash`), and **additive** (legacy `structural_path=NULL` chapters keep working until split).

### 4.3 `scene_translations` table (new, translation-service)
```
scene_translations (
  id UUID PK,
  scene_id UUID,                    -- FK-by-value to book-service scenes(id)
  chapter_id UUID,                  -- denormalized for chapter-level queries
  target_language TEXT,
  version_num INT,
  status TEXT,                      -- pending|running|completed|failed|...
  translated_text TEXT,            -- V2 flat
  translated_body_json JSONB,      -- V3 Tiptap (if applicable)
  authored_by TEXT,                -- 'llm' | 'human'
  source_content_hash TEXT,        -- scene.content_hash at translate time → staleness
  input_tokens INT, output_tokens INT,
  provider_job_id TEXT,            -- V3 event-driven
  created_at, updated_at
)
UNIQUE (scene_id, target_language, version_num)
```
- Chapter-level translation/version becomes an **aggregate** of its scene_translations (join in sort_order). Keep `chapter_translations` as the published/active rollup for backward-compatible reading; scene rows are the working units.
- Re-translation re-does only **dirty scenes** (`source_content_hash != scene.content_hash`) — big cost saving on large books.

### 4.4 Pipeline change
- When `chapter.structural_path IS NOT NULL` (scenes exist): translate **per scene** (`scene.leaf_text` as the unit) → write `scene_translations` → reconstruct the chapter body by joining scenes in `sort_order`.
- Else (legacy, pre-split): fall back to today's whole-chapter chunk path (no behavior change).
- The existing V3 verify/correct loop runs per scene; `chapter_translation_chunks` stays as the ephemeral within-scene observability unit (a scene may still chunk internally if huge).

### 4.5 Coverage & matrix redesign (folds #2)
- `getBookCoverage` gains optional per-scene granularity; chapter cell = aggregate (e.g. "12/15 scenes done"). Expanding a chapter row reveals scene rows with per-scene status + click-through to the correction panel.
- **Fix the `limit:200`→100 clamp** (matrix loads chapters via `listChapters` → loop-fetch like the campaign/extraction fixes) so 2000+ chapters paginate honestly.
- Better filters (status, stale, language) + per-cell quick actions (translate this scene/chapter, open panel).

### 4.6 Migration / rollback
- Additive: new `scene_translations` table + a `scenes` generation path for `.txt`. No destructive change to `chapter_translations` (kept as rollup). Rollback = stop writing scene rows, fall back to whole-chapter path; legacy chapters already on that path. DB migration is L+ (run via /amaw + rollback note when BUILD starts).

---

## 5. T1 ↔ T2 dependency
- T1 **Option B** is independent (ship anytime, FE-only).
- T1 **Option A** (per-block patch) is cleanest **after** T2 (scene_id = stable patch key + per-scene learning gold).
- Recommended order: **T1-B → T2 → T1-A**, so users get inline correction immediately, then granular scene status, then per-scene patch+learning.

## 6. Sizing (rough)
| Task | Size | Surface |
|---|---|---|
| T1-B (inline correction, full-version save) | M | FE only (translation feature) |
| T2 (scene model + generation + pipeline + matrix) | XL | book-service (schema + scene-gen) + translation-service (scene_translations + pipeline) + FE matrix/panel; cross-service → live-smoke + /amaw |
| T1-A (per-block patch + per-scene learning) | M–L | translation-service endpoint + FE; depends on T2 |

## 7. RAID / boundaries
- **Translation code is NOT RAID-owned** (verified: `ChapterEditorPage` = composition/authoring, separate). All of `features/translation/*`, `TranslationTab`, `ChapterTranslationsPage`, `TranslationReviewPage`, translation-service are RAID-free. The deferral reason was bandwidth, not file conflict.
- Still avoid: `services/composition-service`, `frontend/src/features/composition`, `ChapterEditorPage`.
- T2 touches book-service (scenes) — confirm no concurrent RAID cycle is editing book-service scene code before BUILD.
- Invariants: scene-generation via LLM (S-b) must be an **MCP tool through ai-gateway** (MCP-first); any model use resolves through provider-registry (no hardcoded models).

## 8. Open questions
**Resolved at design review (2026-06-15):**
- ~~T1 edit model~~ → **B-first then A** (§3.3, §5).
- ~~Scene generation for `.txt`~~ → **heuristic S-a** (§4.2).
- ~~Build trigger~~ → **parked** (design saved, build deferred).

**Still open — decide when T2 build starts:**
1. **Scene granularity**: target scene size (tokens) — align with the V3 chunk default (~2000) or narrative-driven (variable)?
2. **Rollup semantics**: keep `chapter_translations` as the published rollup (recommended) vs make scenes the only unit and synthesize chapter view on read?
3. **Re-split on draft edit**: auto re-split dirty chapters on draft update, or only at translate time?
4. **Backfill vs lazy**: heuristic-split all chapters up front, or S-c lazy on first open/translate?
