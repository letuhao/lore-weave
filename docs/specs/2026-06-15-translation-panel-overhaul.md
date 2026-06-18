# Translation Panel Overhaul — Design Spec

> Status: **DESIGN COMPLETE — PARKED (3 review rounds; no open questions; build deferred by user)** · 2026-06-15 · branch `feat/auto-draft-factory-gaps`
> Scope: two deferred "big features" for the translation panel + two QoL folds. Design-only; BUILD is RAID-safe (translation code is **not** RAID-owned — §7) and can follow when prioritized.
>
> **Deferred tasks (tracked):**
> - `D-TRANSL-PANEL-T1-CORRECTION` — T1 per-block correction panel (the headline "split translation panel"); ships value first.
> - `D-TRANSL-PANEL-T2-SEGMENTS` — T2 persisted block-range segments (per-part status + dirty-only re-translate); optional, only if T1 isn't enough.

## 0. Origin & locked decisions

User flagged two deferred big-features around the "split translation panel" set aside during the RAID run. CLARIFY + two design-review rounds locked the following:

- **Anchor unit = `chapter_blocks` (block / block-range), NOT the `scenes` table.** Scenes are an **import-decomposer** artifact (written by `parse.go`/`worker-infra` via knowledge-service `/internal/parse`; composition-service does *not* write them — it owns `outline_nodes`). The user's corpus is **bulk-imported `.txt`** (`bulkCreateChapters`), which **skips the decomposer → has no scenes**. `chapter_blocks` is the only unit that exists for **every** chapter (trigger-extracted from any Tiptap draft, incl. bulk `.txt` and legacy). Anchoring on blocks also collapses the source↔translation axis to one, keeps re-edit stability local, and avoids all coupling to scenes/extraction/composition.
- **T1 edit model = (a):** one **human-version per chapter**; per-block corrections **patch in place** into that version's `translated_body_json` block **and** append a per-block **gold record** (source block + LLM text + human text) to the learning store. (Not: a new whole-chapter version per paragraph; not an override-compose layer.)
- **Scope/order:** **T1 first** (delivers the correction panel — most of the user value). **T2 only if needed** afterward (the V3 pipeline already chunks internally, so T2 adds per-part *status* + dirty-only re-translate, not context-window relief).
- **Build:** parked (design saved; build deferred until prioritized).

## 1. Current surface (build ON this, do not rebuild)

### 1.1 UI (all RAID-free)
| Piece | State |
|---|---|
| `features/translation/components/SplitCompareView` | original ↔ translation split, block- **and** text-aligned — **read-only** |
| `TranslationViewer` + full-version edit (M7c-2) → `versionsApi.saveEditedVersion` creates an `authored_by='human'` version, capturing LLM↔human diff as learning gold | shipped |
| `BlockAlignedReview` (per-block review, keyboard nav, empty-block detection) in `TranslationReviewPage` | shipped |
| `ConfirmNameDialog` (M6a glossary name correction → patches glossary + flags book translations stale) | shipped |
| `TranslationTab` coverage matrix + `coverageClassify` lib | shipped |
| `TranslateModal` job wizard (smart classify, paging, V3 verifier, force) | shipped |

### 1.2 Data model — verified
- **`chapter_blocks`** (book-service): one row per Tiptap block, **trigger-extracted** (`fn_extract_chapter_blocks`) from `chapter_drafts.body` on every draft INSERT/UPDATE. Columns incl. `id`, `chapter_id`, `block_index`, `block_type`, `text_content`, `content_hash` (SHA256 of text), `heading_context`. **Exists for every chapter**, including bulk-`.txt` (`bulkCreateChapters` → `plainTextToTiptapJSON` → blocks) and legacy. `block_index` is positional (drifts on insert/delete); `content_hash` is content-stable. Already read by raw-search.
- **`scenes`** (book-service): import-decomposer only (P1, ≥2026-05-23). **Absent** on bulk-`.txt` and pre-P1 chapters. **Not used** by this design.
- **`chapter_translations`** (translation-service): per-chapter version (`version_num`, `status`, `is_active`, `translated_body` V2 flat / `translated_body_json` V3 Tiptap + `translated_body_format`, `unresolved_high_count`, `is_glossary_stale`). V3 body is a **block array** already → per-block edit = editing element *i* of that array.
- **`chapter_translation_chunks`**: ephemeral token-bounded chunks per job (observability/recovery); not a persisted identity. Stays as the within-segment chunking unit.

## 2. Goals & non-goals
**Goals**
- G1: Fix a translation **at paragraph (block) granularity** in a side-by-side panel — not only by re-editing the whole version.
- G2: Every human correction becomes **per-block** learning gold.
- G3 (T2, optional): track status + re-translate **per block-range segment** so long chapters are correctable/re-translatable in parts and re-translation skips clean parts.
- G4 (T2/QoL): matrix scales to 2000+ chapters (fix `limit:200`→100 clamp) with optional per-part drill-down.

**Non-goals**
- Online LLM-judge of fidelity (M7d) — out; the panel reserves an issue-badge slot but does not compute scores.
- Re-architecting the V3 pipeline's internal chunking.
- Touching composition / ChapterEditorPage / authoring, or the `scenes` table.

---

## 3. T1 — Per-block Correction Panel (the headline)

### 3.1 UX
- Promote the aligned view (`SplitCompareView`/`BlockAlignedReview`) from read-only to **editable per block**, source pane fixed (anchor), translation pane editable row-by-row (Tiptap for JSON, textarea for text format).
- Per-row affordances: **edit-in-place**, **glossary term highlight + quick-confirm** (reuse `ConfirmNameDialog`/`useConfirmName`), **dirty indicator**, **reserved issue-badge slot** (only the existing empty/missing detector lights it for now). **No** per-block "re-translate" button in T1 (that needs a block-scoped job — a later add, see §6).
- Save → applies the per-block patch + records gold (§3.3).
- Stateful-component rule: one mounted editable component with an internal `editing` branch (or CSS-hide) — never ternary-swap read/edit (would destroy editor state).

### 3.2 Reuse
`BlockAlignedReview` (row alignment + keyboard nav + empty detection) + `useEditTranslation` (format-aware edit state) + `ConfirmNameDialog`. T1 mostly wires edit affordances into the aligned view + the patch/gold path.

### 3.3 Edit model — **(a), locked**
- **One human-version per chapter** per target language. First correction on an LLM version `v_k`: create human-version `h` seeded from `v_k` (`edited_from_version_id = v_k.id`, `authored_by='human'`), set it active. Subsequent corrections **patch `h` in place**.
- A correction edits block *i* of `h.translated_body_json` directly → reader/`TranslationViewer` read `h` normally (no compose layer; B3 resolved).
- **Per-block gold record** appended on each save: `{ chapter_id, target_language, source_block_content_hash, llm_text (from base version block i), human_text }` → feeds the learning loop at block granularity (B2). The learning loop diffs human vs the LLM base block, not the whole version (avoids over-crediting).
- **Multi-device (B4):** patches are per-block → concurrent edits to *different* blocks merge; only same-block edits last-write-wins. (Whole-version save would clobber — another reason for (a).)
- **LLM never overwrites a human-version (locked).** A new full LLM (re-)translation **always lands as a new non-active version**; it must NOT auto-promote over an active human-version. This already matches the shipped auto-promote guard (`_PROMOTE_ACTIVE_SQL` skips `authored_by='human'`). When a newer LLM base exists, the panel surfaces a **"newer machine translation available"** affordance; adopting it (which discards the human edits, or re-applies them per-block onto the new base) requires an **explicit human confirm** — never automatic.
- Endpoint (translation-service): `PATCH /v1/chapters/{id}/translations/{lang}/blocks/{blockRef}` (or batch) — updates the human-version block + writes gold. `blockRef` keyed by `source_block_content_hash` (+ ordinal tiebreak for duplicate paragraphs), not `block_index` (A2).

### 3.4 Optional FE-only stopgap
If value is wanted before the BE patch endpoint exists: inline edits → `saveEditedVersion` (whole human-version, no per-block gold). Coarse (version-level gold, clobber-on-concurrent) — explicitly a stopgap, not the target.

---

## 4. T2 — Persisted block-range segments (optional, after T1)

Only build if per-part **status tracking** + **dirty-only re-translation** prove needed (the pipeline already chunks for context). Self-contained in translation-service + reads `chapter_blocks`; **no** book-service schema change for segmentation, **no** `scenes`.

### 4.1 Segment model
- `chapter_translation_segments` (translation-service): a **contiguous block-range** of a chapter: `{ id, chapter_id, target_language, start_block_index, end_block_index, block_hashes TEXT[] (content_hash of each member block, ordered), status, version_ref, source_block_hashes_at_translate TEXT[], created_at, updated_at }`.
- Segmentation = heuristic group of adjacent `chapter_blocks` up to a **~2000-token target** (aligns with the V3 chunk default), respecting heading boundaries (never split mid-heading-section if it fits). Deterministic, no LLM.
- **Dirty detection (A2):** compare current `chapter_blocks[start..end]` content_hashes vs `source_block_hashes_at_translate`. A draft edit to one paragraph → only the segment containing that block is dirty (local, no downstream cascade — H2 resolved). Re-translate re-does dirty segments only.

### 4.2 Pipeline
- Translate per segment (join member blocks' text as the unit) → write segment status → chapter rollup (§4.3). Within a huge segment the existing chunk path still applies.
- Idempotency gate per segment (B1): skip a segment whose `block_hashes == source_block_hashes_at_translate` **and** has a fresh completed result (memory: gate on "fresh result EXISTS", not "is active").

### 4.3 Coverage rollup (A3)
- Denormalized **chapter-level** translation status counts (e.g. `segments_total`, `segments_done`, `is_stale`) maintained by trigger on segment writes (the glossary-counts pattern) → matrix cell renders "12/15" cheaply without aggregating tens of thousands of rows live.
- Matrix QoL (folds the old #2): expand a chapter row → segment rows w/ status + click-through to the panel; **fix `listChapters(limit:200)`→100 clamp** via loop-fetch (same fix as campaign/extraction).

### 4.4 Glossary-staleness — per-segment (L1, locked)
- When a glossary entity changes, mark **only the segments whose member blocks mention the changed term(s)** stale (match against `chapter_blocks.text_content`), not the whole chapter. Re-translate then touches just those segments → far cheaper on large books. The chapter-level `is_stale` rollup is the OR of its segments.

### 4.5 Migration / rollback / backfill
- Additive: new `chapter_translation_segments` table + trigger-maintained rollup counts. No change to `chapter_translations` (stays the published/active rollup).
- **Backfill = full, up front:** a one-time job segments every existing chapter from its `chapter_blocks` (the ~2000-token heuristic). Idempotent + resumable (skip chapters already segmented at the current heuristic version). Runs without LLM so the 4232-chapter corpus is cheap.
- Rollback = stop writing segments, fall back to whole-chapter path. DB migration is L+ → run via /amaw + rollback note at BUILD start.

---

## 5. T1 ↔ T2 dependency
- **T1 is independent and first.** It operates on the existing per-version block array; needs only the per-block patch endpoint + gold store.
- T2 adds persisted segments for per-part status + dirty-only re-translate; it consumes the same block anchor T1 uses. Build only if warranted.

## 6. Sizing (rough)
| Task | Size | Surface |
|---|---|---|
| T1 (per-block correction, model (a)) | M–L | translation-service (per-block patch endpoint + gold store) + FE (editable aligned panel) |
| T1 FE-only stopgap (§3.4) | S–M | FE only |
| per-block re-translate (block-scoped job) | M | translation-service job-scoping + FE button; after T1 |
| T2 (segments + dirty-retranslate + rollup + matrix) | L | translation-service (segments table, pipeline, trigger rollup) + FE matrix; cross-service live-smoke + /amaw |

## 7. RAID / boundaries
- Translation code is **RAID-free** (`ChapterEditorPage` = composition/authoring, separate). All of `features/translation/*`, `TranslationTab`, `ChapterTranslationsPage`, `TranslationReviewPage`, translation-service are RAID-free. Deferral was bandwidth, not file conflict.
- Avoid: `services/composition-service`, `frontend/src/features/composition`, `ChapterEditorPage`, **the `scenes` table** (decomposer/extraction territory).
- Reads `chapter_blocks` (book-service) — already a public/raw-search-served unit; no schema change needed there.
- Invariants: any model use resolves via provider-registry (no hardcoded models); any agentic step (none planned in T1/T2) would go through ai-gateway (MCP-first).

## 8. Open questions
**Resolved (design review 2026-06-15):**
- ~~Anchor unit~~ → `chapter_blocks` block-range (not scenes).
- ~~T1 edit model~~ → (a) one human-version/chapter, patch-in-place + per-block gold.
- ~~Scene generation~~ → moot (not using scenes).
- ~~B3 serving / B4 concurrency~~ → resolved by (a) (in-place patch into a real version; per-block merge).
- ~~Scope/order~~ → T1 first; T2 optional.

**Resolved (design review round 3, 2026-06-15):**
- ~~Segment granularity~~ → **~2000-token target**, heading-aware (§4.1).
- ~~Backfill vs lazy~~ → **full backfill up front**, idempotent/resumable, no LLM (§4.5).
- ~~Glossary-staleness granularity~~ → **per-segment** — only segments mentioning the changed term go stale (§4.4).
- ~~New-base reconciliation~~ → **LLM never overwrites a human-version**; new LLM translation lands non-active; adopting it requires **explicit human confirm** (§3.3).

**No open questions remain — design is complete for both T1 and T2.**
