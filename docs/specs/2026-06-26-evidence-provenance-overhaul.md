# Evidence Provenance Overhaul — collection correctness, provenance surfacing, and a usable browser

**Date:** 2026-06-26
**Status:** Spec (CLARIFY → DESIGN handoff)
**Domain:** `glossary-service` (evidence) + `translation-service` (extraction worker/replay) + `frontend` (entity-editor evidence tab)
**Size:** XL (multi-service, schema-adjacent, FS) — phased M1–M5; subagent recommended per phase.

---

## 1. Problem

### 1.1 The user's symptoms (verbatim intent)

> - "Evidence provenance is **never collected** — quotes show up with no offsets and no trust marker."
> - "An evidence quote is labeled the **wrong chapter** (a chapter-50 quote on a major character shows as chapter 1)."
> - "The evidence browser **can't handle 10k+ rows** — it just shows a prev/next pager and chokes."
> - "I can't **open the source** of a quote — the chapter title is dead text, and reference URLs render as junk."

### 1.2 The calibrated reality

The investigation (root cause, §3) found the user's framing is partly mis-stated. The accurate picture is **narrower and cheaper to fix than "never collected" / "can't paginate"**:

1. **Provenance IS collected and stored — it's just never surfaced.** The translation worker already validates each quote against the real chapter text, computes char offsets + a block index, and assigns a trust status (`exact` / `resolved` / `ambiguous` / `unmatched`); the glossary writeback persists all of it into `evidences.char_start` / `char_end` / `provenance_status`. The list API and the FE simply **omit those columns**, so the GUI never sees offsets or trust. This is a *surfacing gap*, not a collection gap.
2. **There IS one real collection bug — the chapter pointer.** The bulk writeback stamps each evidence's `chapter_id` / `chapter_title` / `chapter_index` from the entity's **first** chapter link (`ChapterLinks[0]`), not the chapter the quote was actually validated against. So a quote extracted from chapter 50 of a major character (whose first appearance is chapter 1) is labeled chapter 1. The *offsets* are correct (validated against the right text upstream); only the **chapter label** is wrong.
3. **The API is already paginated — the pager is just crude, and deep OFFSET is slow.** `GET …/evidences` already does limit/offset (default 20, max 100), sort, filters, and returns `{items,total,limit,offset,available_*}`. It does **not** load all 10k rows at once. The real weaknesses are (a) a deep-`OFFSET` SQL plan that degrades on large sets, and (b) a prev/next-only FE pager with no jump-to-page / page-size / first-last.
4. **"Open source" was never wired.** Chapter title renders as plain text (no link to the reader), and `reference`-type evidence overloads `block_or_line` with the source URL as text — there's no real external link.

So this overhaul = **surface what's already collected + fix one genuine chapter-pointer bug + add open-source links + upgrade the pager (incl. keyset SQL) + heal historical rows.** Not "build provenance from scratch."

---

## 2. Scope decision

**FULL overhaul — all five parts (a–e), phased M1–M5.** Per user decision; no part deferred except glossary entity version-control FE (separate task, see Out-of-scope §7).

| Part | Summary |
|---|---|
| **(a) Surface + badge** | Add `char_start` / `char_end` / `provenance_status` to the list-API SELECT, the Go response struct, and the FE `EvidenceListItem` type; render a trust badge (verified/exact vs ambiguous vs unmatched) on the evidence card. |
| **(b) Chapter-pointer fix** | Derive each evidence's chapter ref from the chapter the worker actually validated the quote against — plumb a per-quote chapter ref through the extraction → glossary payload, replace `ChapterLinks[0]`. |
| **(c) Open-source links** | Chapter title → link into the book reader at that chapter, deep-linking to highlight `char_start`/`end` when present and provenance is `exact`/`resolved`; `reference` evidence renders its URL as a real external link instead of `block_or_line` text. |
| **(d) Large-set browser** | Real pager (jump-to-page, page-size selector, first/last) + switch the API to keyset/seek pagination to kill slow deep OFFSET on >10k rows. |
| **(e) Historical backfill** | A re-validation / backfill pass to heal existing rows (wrong chapter, `provenance_status='unverified'`) by reusing the existing replay path. |

---

## 3. Root cause (verified — file:line evidence)

All locations below were opened and confirmed during CLARIFY (2026-06-26).

### 3.1 Schema — the columns already exist
- Base `evidences` table: `services/glossary-service/internal/migrate/migrate.go:124-135` — `chapter_id`, `chapter_title`, `block_or_line`, `evidence_type`, `original_language`, `original_text`, `note`, `created_at`. No char offsets / status in the base.
- `chapter_index` added: `services/glossary-service/internal/migrate/migrate.go:803` (`UpEvidenceChapterIndex`).
- `char_start`, `char_end`, `provenance_status` (DEFAULT `'unverified'`) added: `services/glossary-service/internal/migrate/evidence_provenance.go:35-37` (`UpEvidenceProvenance`). The migration header documents the trust taxonomy: `exact` / `resolved` / `ambiguous` / `unmatched` / `unverified` (default).

### 3.2 Provenance IS validated upstream and persisted
- Worker stamps validated provenance per-chapter: `services/translation-service/app/workers/extraction_worker.py:1091` calls `stamp_entity_provenance(all_entities, chapter_text)` (impl in `extraction_provenance.py`), locating each quote in the **real prepared chapter text** and recording chapter-relative char offsets + block index + trust status. The worker processes **one chapter per call** (`chapter_id` / `chapter_text` in scope), so the chapter the quote is validated against IS the chapter being processed.
- Replay re-stamps against current text: `services/translation-service/app/workers/extraction_replay.py:157` (same `stamp_entity_provenance`), sound because the `content_hash` matched.
- Extraction payload already carries the per-quote provenance fields: `extraction_handler.go:420-423` — `evidence_provenance_status`, `evidence_char_start`, `evidence_char_end`, `evidence_block_or_line`.
- Glossary persists them: `extraction_handler.go:489-507` (`evidenceProvenanceFields` clamps + enum-gates — `exact`/`resolved` keep offsets only when valid, else degrade to `unverified`; `ambiguous`/`unmatched` keep status, NULL offsets) and the INSERT at `extraction_handler.go:846-859` writes `char_start`, `char_end`, `provenance_status`, `block_or_line`.

### 3.3 COLLECTION BUG — chapter pointer uses `ChapterLinks[0]`
- `extraction_handler.go:822-826` derives `evChapterTitle` / `evChapterIndex` from `ent.ChapterLinks[0]`; `:857` passes `s.firstChapterID(ent.ChapterLinks)` as `chapter_id`. The code comment even labels it "the entity's first chapter link." So the **chapter label** is the entity's first chapter, not the quote's source chapter. (The *offsets* are correct because they were validated against the right chapter text upstream — only the chapter triple is wrong.)
- Note the payload's `chapterLinkIn` carries `chapter_id` / `chapter_title` / `chapter_index` per link (`extraction_handler.go:411`, `:773`), but there is **no per-quote/per-evidence chapter ref** — that's the plumbing gap part (b) fills.

### 3.4 SURFACING GAP — list API omits the provenance columns
- Route: `server.go:446` (`r.Get("/evidences", s.listEntityEvidences)`) → `evidence_handler.go:60`.
- The list SELECT at `evidence_handler.go:194-203` returns `evidence_id`, `attr_value_id`, `name`/`code`, `chapter_id`/`chapter_title`/`chapter_index`, `block_or_line`, `evidence_type`, `original_language`/`original_text`, `display_text`/`display_language`, `note`, `created_at` — but **omits `char_start`, `char_end`, `provenance_status`**. So the GUI never receives offsets or trust.
- `createEvidenceCore` INSERT also omits these columns (`evidence_handler.go:395-397`) — manual/MCP-created evidence cannot carry offsets/status. (Acceptable for now; see §5a.)

### 3.5 Pagination is real but weak
- The handler is paginated: limit default 20 / max 100, offset, `sort_by` ∈ {created_at, chapter_index, block_or_line, attribute_name}, filters {type, attr, chapter, language}, returns `{items,total,limit,offset,available_attributes,available_chapters,available_languages}` (struct at `evidence_handler.go:50-57`, SQL `LIMIT $ OFFSET $` at `:210`). It does NOT load all rows — "can't handle 10k" really = deep-`OFFSET` slowdown + a crude FE pager.

### 3.6 FE — under `components/entity-editor/`, NOT `features/glossary/`
- `EvidenceCard.tsx:103-107` renders `chapter_title` + `block_or_line` as **plain text** (no link).
- `EvidenceTab.tsx:111-141` is a **prev/next-only** pager (`ev.offset ± PAGE_SIZE`, current/total page label).
- `useEvidenceList.ts:15` hardcodes `PAGE_SIZE = 20`; pagination is offset-based (`:56-67`, `:88`).
- `EvidenceListItem` type at `frontend/src/features/glossary/types.ts:268-284` has **no** `char_start` / `char_end` / `provenance_status` fields.
- Filter UI: `EvidenceFilterBar.tsx:90-101` (chapter `<select>` from `available_chapters`).
- Reader route exists: `/books/:bookId/chapters/:chapterId/read` (`frontend/src/App.tsx:100`).

### 3.7 Reference-type evidence overloads `block_or_line` with the URL
- `pipeline_deep_research.go:221` calls `createEvidenceCore(ctx, attrValueID, "reference", snippet, "und", "", nil, nil, safeURL, &note)` — `safeURL` is passed in the **`blockOrLine`** positional slot (`createEvidenceCore` signature at `evidence_handler.go:371`). So a `reference` row stores its source URL in `block_or_line`, which the card then renders as line-number-style text.

---

## 4. Design

Grouped per part. Each names concrete file changes.

### (a) Surface offsets + trust, render badge

**API SELECT + struct (glossary-service)**
- Extend the list SELECT (`evidence_handler.go:194-203`) to add `ev.char_start, ev.char_end, ev.provenance_status`.
- Extend the per-row response struct (the `evidence list item` type backing `items`) to carry `CharStart *int`, `CharEnd *int`, `ProvenanceStatus string` (JSON: `char_start`, `char_end`, `provenance_status`). Update the row `Scan` to match the new column order.
- Keep `provenance_status` non-null (`unverified` default) so older rows render as "unverified" rather than missing.

**FE type + card (frontend)**
- Add to `EvidenceListItem` (`features/glossary/types.ts:268-284`): `char_start: number | null; char_end: number | null; provenance_status: 'exact' | 'resolved' | 'ambiguous' | 'unmatched' | 'unverified';`.
- In `EvidenceCard.tsx` header row (near `:96-107`) render a **trust badge**:
  - `exact` / `resolved` → "verified" (success tint),
  - `ambiguous` → "ambiguous" (warning tint),
  - `unmatched` → "unmatched" (destructive tint),
  - `unverified` → muted/neutral ("unverified", no claim).
- Add i18n keys (`entityEditor` namespace) `evidence.provenance.{verified,ambiguous,unmatched,unverified}` + a tooltip explaining each.

### (b) Fix the chapter-pointer collection bug

The worker already knows the correct chapter per quote (it validated against `chapter_text` for the current `chapter_id`). Plumb that chapter ref onto each emitted evidence instead of relying on `ChapterLinks[0]` at writeback.

**Translation payload (translation-service)**
- Where the worker assembles the per-entity evidence payload (the entity dicts posted via `post_extracted_entities`, `extraction_worker.py:1094`; replay assembles `chapter_links` at `extraction_replay.py:140-145`), stamp the **evidence's** source chapter alongside the provenance fields — i.e. add `evidence_chapter_id` / `evidence_chapter_title` / `evidence_chapter_index` carrying the chapter currently being processed (the same `chapter_id`/title/index the worker holds). These sit next to `evidence_char_start`/`end`/`block_or_line` already emitted (`extraction_handler.go:420-423` consumes those).
- `stamp_entity_provenance` already runs per-chapter; extend it (or the caller) to also record the evidence chapter ref so it can't diverge from the validated offsets.

**Payload struct + writeback (glossary-service)**
- Add to `extractedEntity` (`extraction_handler.go` near `:411-423`): `EvidenceChapterID *string`, `EvidenceChapterTitle *string`, `EvidenceChapterIndex *int` (JSON `evidence_chapter_id` etc.).
- At the INSERT (`extraction_handler.go:822-826`, `:857`), **prefer the evidence chapter ref**; fall back to `ChapterLinks[0]` only when the per-evidence ref is absent (legacy / manual). The `ON CONFLICT … DO UPDATE` (`:852-856`) currently refreshes only the validated offset columns — extend it to also refresh the chapter triple **when the new ref is present**, so re-extraction heals a previously-wrong chapter label (latest-validated-wins, consistent with the existing offset-refresh rationale).

**Backward-compat:** old payloads (no `evidence_chapter_*`) keep the `ChapterLinks[0]` behavior; backfill (part e) re-emits with correct refs.

### (c) "Open source" affordances

**Chapter link → reader deep-link (frontend)**
- In `EvidenceCard.tsx` (`:103-107`), when `evidence_type !== 'reference'` and `chapter_id` is present, render `chapter_title` as a link to `/books/:bookId/chapters/:chapterId/read`.
- When `char_start`/`char_end` are present **and** `provenance_status ∈ {exact, resolved}`, append a highlight deep-link param (e.g. `?hl=<start>-<end>` or `#h=<start>-<end>`) consumed by `ReaderPage` to scroll-to + highlight that span. For `ambiguous`/`unmatched`/`unverified` (NULL offsets) link to the chapter only — no fabricated highlight.
- Reader side: `ReaderPage` reads the highlight param and, if the offsets are in-range for the loaded chapter text, renders a transient highlight (defensive: clamp to text length; ignore if out of range — text may have been edited).

**Reference URL as a real link (glossary-service + frontend)**
- Stop overloading `block_or_line` with the URL. Preferred: persist the reference URL in a dedicated place. Minimal viable: the deep-research path already stores `title`/snippet in `note`/`original_text`; route the URL into `note` as a structured field or add a `source_url` column. Decision for DESIGN: add `evidences.source_url TEXT` (additive migration, idempotent like `evidence_provenance.go`) and have `pipeline_deep_research.go:221` pass the URL there instead of the `blockOrLine` slot. Surface `source_url` in the list SELECT + struct + `EvidenceListItem`.
- FE: for `reference` rows, `EvidenceCard` renders `source_url` as a real external link (`target=_blank rel=noopener`), not as `block_or_line` text.
- Migration of existing reference rows: backfill (part e) or a one-shot copy `block_or_line → source_url` for `evidence_type='reference'` rows whose `block_or_line` looks like a URL.

### (d) Large-set browser — real pager + keyset pagination

**Keyset/seek pagination (glossary-service)**
- Replace the deep-`OFFSET` plan (`evidence_handler.go:210`) with keyset/seek pagination for forward/backward paging, keyed on the active sort column + a tiebreaker (`evidence_id`, which is uuidv7 → time-ordered). Request gains an opaque `cursor` (encodes `(sort_value, evidence_id)` + direction); response returns `next_cursor` / `prev_cursor`.
- **Jump-to-page** can't be pure keyset. Keep `total` (cheap count) and support **page jumps via a bounded OFFSET fallback** only for explicit page jumps, while normal next/prev/first/last use keyset. First = no cursor; last = reverse-order keyset with no cursor. This keeps the common path (sequential paging through 10k rows) O(log n)+index-scan, and reserves the slow path for the rare explicit jump.
- Preserve the existing response contract additively (`items`, `total`, `limit`, `available_*`) + add `next_cursor`/`prev_cursor`. Keep `offset` accepted for the jump path / backward-compat.
- Ensure an index supports each `sort_by` (created_at, chapter_index, block_or_line, attribute_name) with `evidence_id` tiebreaker; add composite indexes where missing (additive migration).

**Real pager (frontend)**
- `useEvidenceList.ts`: make `PAGE_SIZE` state (page-size selector: 20/50/100, capped at API max 100); track `cursor`/`next_cursor`/`prev_cursor`; expose `firstPage`, `lastPage`, `nextPage`, `prevPage`, `goToPage(n)` (page jump via offset fallback).
- `EvidenceTab.tsx:111-141`: replace prev/next-only with first / prev / page-input (jump-to-page) / next / last + page-size `<select>` + "N–M of T" label. Keep it a controller-driven view (logic stays in the hook per MVC rules).

### (e) Historical backfill

**Reuse the replay path (translation-service)**
- Drive an admin/internal backfill that re-runs the existing replay (`extraction_replay.py`, which already re-stamps validated provenance against current text and posts via `post_extracted_entities`) over chapters whose evidences are stale: `provenance_status='unverified'` OR a wrong chapter label.
- Targeting: select distinct `(book_id, chapter_id)` from extraction audit / evidences needing repair; for each, replay with `confirm=True`. The replay's `content_hash` guard ensures offsets index the text that backs the writeback; the part-(b) chapter-ref plumbing means the replay now writes the **correct** chapter triple, and the extended `ON CONFLICT … DO UPDATE` heals the existing row in place (dedup key is `(attr_value_id, evidence_type, md5(original_text))`, so no duplicate rows).
- For `reference` rows (not extraction-sourced), a separate one-shot SQL backfill copies URL `block_or_line → source_url` (part c).
- Job shape: internal endpoint or CLI on translation-service that enumerates and replays in bounded batches; idempotent (re-running is safe via writeback_key + ON CONFLICT). Report counts (chapters replayed, rows healed, rows still unmatched).

---

## 5. Per-part notes

- **(a)** Manual/MCP-created evidence still inserts with no offsets (`createEvidenceCore`, `:395-397`) → renders `unverified`. That's correct (a human-typed quote has no validated offset). No change required unless we later add manual offset entry.
- **(b)** The fix is backward-compatible: absent `evidence_chapter_*` → legacy `ChapterLinks[0]`. Live extraction starts writing correct refs immediately on deploy; old rows healed by (e).
- **(c)** `source_url` is the clean fix for the `block_or_line`-overload; do NOT keep parsing URLs out of `block_or_line` at render time (that's the smell we're removing).
- **(d)** uuidv7 `evidence_id` gives a stable, time-ordered tiebreaker — exploit it for the keyset cursor.
- **(e)** Replay is the single source of truth for re-stamping — do NOT write a second offset-validation routine in glossary (would diverge from the worker, per the existing "single source of truth" note at `extraction_replay.py:147-150`).

---

## 6. Phasing

| Milestone | Deliverable | Touches |
|---|---|---|
| **M1 — Surface + badge** | List SELECT + struct + `EvidenceListItem` carry `char_start`/`char_end`/`provenance_status`; trust badge on the card. | glossary `evidence_handler.go`; FE `types.ts`, `EvidenceCard.tsx`, i18n |
| **M2 — Chapter-pointer fix** | Per-quote chapter ref plumbed through the extraction + replay payload; writeback prefers it over `ChapterLinks[0]`; `ON CONFLICT` heals chapter triple. | translation `extraction_worker.py` / `extraction_replay.py` / `extraction_provenance.py`; glossary `extraction_handler.go` |
| **M3 — Open-source links** | Chapter title → reader deep-link w/ highlight when `exact`/`resolved`; `source_url` column + `reference` external link; reader honors highlight param. | glossary migration + `pipeline_deep_research.go` + SELECT; FE `EvidenceCard.tsx`, `ReaderPage` |
| **M4 — Keyset pager** | Keyset/seek pagination + cursors in API; real FE pager (first/last/jump/page-size). | glossary `evidence_handler.go` + indexes; FE `useEvidenceList.ts`, `EvidenceTab.tsx` |
| **M5 — Backfill** | Replay-driven backfill heals wrong-chapter + `unverified` rows; one-shot `reference` URL copy. | translation backfill job; glossary one-shot SQL |

Each milestone is independently shippable; M1 has no dependency, M3/M4 depend only on M1's surfaced fields, M5 depends on M2's chapter-ref plumbing. Per the budget-driven cadence, checkpoint/commit at each milestone boundary (each is a real risk boundary: a migration, a cross-service payload change, or a shippable FE).

**Cross-service live-smoke** (≥2 services touched in M2/M3/M5): real extraction→glossary writeback on a stack-up confirming the correct chapter triple + surfaced offsets, or an explicit `live infra unavailable` / `LIVE-SMOKE deferred` token.

---

## 7. Acceptance criteria

**M1**
- `GET …/evidences` response items include `char_start`, `char_end`, `provenance_status` for every row.
- An extraction-sourced quote with validated offsets shows a "verified" badge; an `unmatched` quote shows "unmatched"; a manual quote shows "unverified".

**M2**
- A quote extracted from chapter 50 of an entity whose first appearance is chapter 1 is labeled **chapter 50** (chapter_id/title/index), not chapter 1.
- The offsets remain correct (still validated against the right chapter text).
- Re-extraction of a previously-mislabeled quote heals the chapter triple in place (no duplicate row).

**M3**
- Clicking a non-reference evidence's chapter title opens the reader at that chapter; when provenance is `exact`/`resolved`, the quote span is highlighted; otherwise the chapter loads with no fabricated highlight.
- A `reference` evidence renders its source URL as a real external link (new tab, `rel=noopener`), not as `block_or_line` text.
- Out-of-range / edited-text offsets degrade gracefully (chapter loads, no crash, no wrong highlight).

**M4**
- Sequential next/prev/first/last paging through a >10k-row evidence set stays fast (index/keyset scan, no full deep-OFFSET scan); page-size selector (20/50/100) and jump-to-page work.
- Existing filters + sort still apply; `total` still reported.

**M5**
- After backfill, rows previously `unverified` (but extraction-sourced and re-validatable) carry a real status + offsets; previously wrong chapter labels are corrected; counts reported.
- Backfill is idempotent (re-running changes nothing); rows that genuinely can't be matched stay `unmatched` (no fabrication).

---

## 8. Out-of-scope

- **Glossary entity version-control FE** (the `revisions` / restore surface at `server.go:447-449`) — a separate task; this overhaul does not touch entity revision history UI.
- **Manual offset entry** for human-typed evidence (manual evidence stays `unverified`; no UI to type offsets).
- **Re-extraction quality / model changes** — this overhaul surfaces and heals provenance; it does not change how the worker extracts or validates.
- **Knowledge-service / Neo4j projection** of evidence provenance — out of this track.
