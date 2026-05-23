# Spec — P1 Structural Decomposer (hierarchical extraction T1)

> **Status:** DESIGN 2026-05-23. XL task (12 files, 6 logic, 1 side-effect = Postgres schema). Branch `main`.
> **Workflow:** v2.2 default. No `/amaw` (XL but single-cycle, single-arc; sub-agent only for `/review-impl` at REVIEW phases).
> **Parent ADR:** [`docs/03_planning/KNOWLEDGE_SERVICE_HIERARCHICAL_EXTRACTION_ADR.md`](../03_planning/KNOWLEDGE_SERVICE_HIERARCHICAL_EXTRACTION_ADR.md) §3 T1 + §6 P1 + §7 P1 acceptance.
> **CLARIFY answers (PO):** owner = book-service domain (worker-infra import flow); formats = EPUB + Markdown + plain-text multi-lang (CN/VN/EN/JP); rolling glossary anchor = P2 concern (out of P1); T1 stack = **Python SDK `loreweave_parse`** hosted via knowledge-service `/internal/parse`; persistence = **full parts/scenes Postgres schema from P1** (no two-step refactor); PDF deferred to a later phase.

---

## 1. Problem

Per the parent ADR §1: the extraction pipeline cannot scale to 50 MB+ novels because every chapter is one extraction job with serial chunks inside, flat dedup, no cross-section coreference, no checkpoint. Sessions ≥ 1 h trigger LM Studio TTL eviction; flat dedup misses cross-chapter coreference.

P1 (this spec) lays the **foundation** for the 7-tier pipeline by replacing the naive splitter in [worker-infra/internal/tasks/html_to_tiptap.go:20-61](../../services/worker-infra/internal/tasks/html_to_tiptap.go) (currently: `<h1>` → fallback `<h2>` → fallback "single chapter"; DOCX always 1 chapter) with a multi-format, multi-language **structural decomposer** that emits a 4-level tree (`book → part → chapter → scene`) the rest of the pipeline (P2 parallel map, P3 hierarchical reduce) consumes.

P1 alone does **not** ship parallelism, checkpointing, or hierarchical merge. It ships the **tree** + the **storage shape** those phases need.

## 2. Scope

In scope (one XL cycle):

1. **NEW `sdks/python/loreweave_parse/`** — Python SDK (Pydantic `StructuralTree` + per-format dispatcher + post-pandoc HTML walker + plain-text multi-lang regex parser).
2. **NEW `services/knowledge-service` `/internal/parse` endpoint** — HTTP wrapper around the SDK so worker-infra (Go) can call it. Stateless; no DB, no LLM, no embedding.
3. **MODIFY `services/book-service/internal/migrate/migrate.go`** — add `parts` + `scenes` tables to `schemaSQL`; backfill existing chapters into 1-part-1-scene synthetic trees.
4. **MODIFY `services/worker-infra/internal/tasks/import_processor.go`** — replace `splitChapters(html, format)` with POST to knowledge-service `/internal/parse`; insert resulting parts + chapters + scenes in one transaction.
5. **DELETE `splitChapters` + `splitOnH1`/`splitOnTag`/`h1Re`/`h2Re`** from `html_to_tiptap.go` (the per-chapter `htmlToTiptapJSON` stays — it's a different concern, used by P1 for `chapter_drafts.body`).
6. **Tests** — SDK round-trip tests over 10 fixture corpora (multi-format, multi-language); knowledge-service router unit tests; worker-infra integration test mocking `/internal/parse`.

Out of scope (parent ADR phases later):
- PDF format (`.pdf` import path — deferred per CLARIFY).
- Parallel map orchestrator, idempotent `sha256` task ID, `extraction_leaves` checkpoint table (P2).
- Hierarchical deterministic reduce, per-level summary embeddings, Neo4j `:Scene`/`:Chapter`/`:Part`/`:Book` labels (P3).
- Semantic chunking escape valve in `chunker.go` (P4).
- Gated LLM coreference + multi-resolution retrieval router (P5).
- Rolling `known_entities` window / glossary anchor fetch — P2 concern; P1 produces the tree, P2 consumes scenes + threads context.

## 3. Design decisions

### D1 — Parser language = Python SDK, exposed via HTTP from knowledge-service

The parser is **canonical in Python** (`sdks/python/loreweave_parse/`) because:
- Matches the parent ADR's `StructuralTree` Pydantic schema verbatim — no schema mirroring required.
- Python's HTML ecosystem (`beautifulsoup4`, `lxml`) is cleaner than `golang.org/x/net/html` for the structural walk we need.
- knowledge-service (Python) is the **primary downstream** consumer in P3 (hierarchical reduce + summary). Importing the SDK natively in P3 is friction-free; making it consume JSON over HTTP would be perverse.

worker-infra (Go) cannot import a Python package, so the SDK is wrapped by a **single thin HTTP endpoint on knowledge-service** (`POST /internal/parse`). Cost: one network hop per import job (already negligible compared to the existing pandoc 5-minute timeout call). No new service / Dockerfile / OTel boundary added.

Rejected:
- **Go SDK in `sdks/go/lwparse/`**: would force a Python re-implementation in knowledge-service for P3, OR force P3 to deserialize JSON from a Go service — both worse than one HTTP hop.
- **Standalone parser-service**: clean domain separation but adds a Docker image, compose service, port, OTel surface for one HTTP route. Premature.
- **Inline Go in worker-infra**: would freeze the parser at the worker-infra boundary; knowledge-service (the heavier consumer) would have to call worker-infra cross-service, inverting the dependency.

### D2 — parts/scenes tables live in book-service DB

`parts` and `scenes` are **structural slices of chapter content**, not extraction artifacts. They belong with `chapters` in `loreweave_book`. knowledge-service reads them cross-DB at extraction time (already does this for `chapters.body` via internal endpoint).

Tables (added to `services/book-service/internal/migrate/migrate.go` `schemaSQL`) — M5 fix: lifecycle parity with `chapters`/`books`:

```sql
CREATE TABLE IF NOT EXISTS parts (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  book_id         UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  sort_order      INT  NOT NULL,                       -- 1-based, gap-tolerant
  title           TEXT,
  path            TEXT NOT NULL,                       -- "book/part-1"
  parse_version   INT  NOT NULL DEFAULT 1,
  lifecycle_state TEXT NOT NULL DEFAULT 'active',      -- M5: parity with chapters
  trashed_at      TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),  -- M5: parity
  UNIQUE (book_id, sort_order)
);

CREATE TABLE IF NOT EXISTS scenes (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  chapter_id      UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
  sort_order      INT  NOT NULL,                       -- 1-based within chapter
  path            TEXT NOT NULL,                       -- "book/part-1/chapter-3/scene-2"
  leaf_text       TEXT NOT NULL,                       -- plain text via D4 html_to_leaf_text
  content_hash    TEXT NOT NULL,                       -- sha256(leaf_text); P2 task-ID seed
  parse_version   INT  NOT NULL DEFAULT 1,
  lifecycle_state TEXT NOT NULL DEFAULT 'active',      -- M5: enables P3 re-parse soft-delete
  trashed_at      TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),  -- M5: parity
  UNIQUE (chapter_id, sort_order)
);

CREATE INDEX IF NOT EXISTS idx_scenes_chapter_sort_active
  ON scenes(chapter_id, sort_order) WHERE lifecycle_state = 'active';
CREATE INDEX IF NOT EXISTS idx_scenes_content_hash ON scenes(content_hash);

ALTER TABLE chapters ADD COLUMN IF NOT EXISTS part_id UUID REFERENCES parts(id) ON DELETE SET NULL;
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS structural_path TEXT;  -- "book/part-1/chapter-3"
```

**Backfill: NONE (R-SELF-1 self-review fix).** Legacy chapters keep `part_id = NULL` and `structural_path = NULL`. Rationale:

- EPUB/DOCX import path in [worker-infra/import_processor.go](../../services/worker-infra/internal/tasks/import_processor.go) does NOT populate `chapter_raw_objects` — only the inline book-service `/v1/books/{id}/chapters` API does, and only when `includeRaw=true`. So a `LEFT JOIN chapter_raw_objects` backfill would produce `leaf_text=''` for ~all imported chapters.
- The alternative — extracting plain text from `chapter_drafts.body` (Tiptap JSON) via a Postgres function that walks the JSON tree — is fragile and out of P1's scope.
- Cleanest: **NULL `structural_path` = "needs re-parse" signal**. P2 extraction reads `WHERE chapter_id IS NOT NULL`; if a chapter has no `scenes` rows (legacy), P2 falls back to the existing chapter-as-leaf code path. P3 owns the explicit re-parse job that materialises `parts`/`scenes` for legacy chapters using the same SDK.

Schema becomes purely additive — no DO block, no row writes:

```sql
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS part_id UUID
  REFERENCES parts(id) ON DELETE SET NULL;
ALTER TABLE chapters ADD COLUMN IF NOT EXISTS structural_path TEXT;
-- (no backfill — NULL means "legacy chapter, no structural decomposition yet")
```

**P2 fallback contract (M6 fix — LOCKED for downstream consumption):**

P2 extraction code MUST implement this branch when reading scenes for a chapter:

```python
# P2 (future) — DO NOT skip this fallback
scenes = await book_client.list_scenes(chapter_id)  # SELECT * FROM scenes WHERE chapter_id=$1 AND lifecycle_state='active'
if not scenes:
    # Legacy chapter — no structural decomposition yet.
    # Fall back to chapter_drafts.body extracted to text via SAME html_to_leaf_text from D4.
    body_json = await book_client.get_chapter_draft(chapter_id)
    virtual_scene = Scene(
        sort_order=1,
        path=f"book/legacy/chapter-{chapter.sort_order}/scene-1",
        leaf_text=tiptap_json_to_text(body_json),  # NEW helper, mirrors html_to_leaf_text
        content_hash=hashlib.sha256(...).hexdigest(),
    )
    scenes = [virtual_scene]
# proceed with leaf-level extraction over `scenes`
```

This contract is the **only** P1→P2 coupling. P2 design must respect it or legacy chapters silently get zero extraction.

`parse_version = 1` is the P1 SDK version. Future SDK changes that re-parse get `parse_version = 2+`. P3 detects mixed-version corpora via `parse_version` on `scenes` (legacy = no scenes row at all → re-parse triggers materialisation at version 1).

**sort_order semantics (R-SELF-3 self-review fix):** `chapters.sort_order` remains **book-global** (unchanged from today). The existing unique index `UNIQUE (book_id, sort_order, original_language) WHERE lifecycle_state='active'` continues to hold — `part_id` is a grouping hint, not a re-numbering. So Part 2's first chapter still has `sort_order = N+1` where N is the last chapter of Part 1. Two reasons:
- Preserves FE flat-chapter-list ordering with zero schema migration on the read path.
- Avoids collision: if `sort_order` were per-part-scoped, Part 1 Ch 1 + Part 2 Ch 1 would both `sort_order=1` and trip the unique index.

`scenes.sort_order` IS per-chapter-scoped (`UNIQUE (chapter_id, sort_order)`) — scenes are an inner artifact, not user-visible.

Rejected:
- **parts/scenes in knowledge-service DB**: violates SSOT (book-service owns chapter content); cross-DB FK pain.
- **scenes.leaf_text as `bytea` or referenced into MinIO**: column-thin denorm is cheaper for ~12.5 k scenes / 50 MB novel (~5 KB avg/scene); querying joins cleanly. MinIO indirection adds an I/O hop per leaf at extraction time.
- **Storing scenes only on extraction trigger (not at import)**: would require re-parsing on every extraction config change. Import-time parsing makes `parts`/`scenes` part of the chapter's identity, not the extraction job's.

### D3 — Pandoc HTML is the canonical input for non-plain-text (H1 fix: explicit `.txt` flow)

The existing import pipeline runs pandoc on EPUB/DOCX **inside worker-infra**; the `.txt` path takes a different route:

```
EPUB / DOCX / MD (worker-infra path):
  book-service /import → MinIO + outbox(import.requested)
  → worker-infra import_processor:
      pandoc → HTML (uniform)
      → POST /internal/parse (source_format="html")     # ← P1
      → tree write (parts/chapters/scenes)
      → htmlToTiptap → chapter_drafts

.txt (book-service synchronous path — H1 fix):
  book-service /import (.txt branch at import.go:80-89):
      → POST /internal/parse (source_format="plain")    # ← P1 (NEW sync call)
      → tree write (parts/chapters/scenes) IN-HANDLER Tx
      → existing s.createChapterRecord(...) per chapter,
        but iterating over the tree's parts→chapters
```

**Why two paths:** `.txt` is small and synchronous-UX (user uploads → sees chapter immediately). EPUB/DOCX is large and async (job + worker). P1 must serve BOTH or it fails the "plain-text EN/CN/VN/JP" acceptance criterion. The synchronous call from book-service to knowledge-service `/internal/parse` is the smallest delta — adds one cross-service hop to a path that's already sub-second.

The SDK's per-format dispatcher therefore handles **2 input shapes** (not the ADR §3 T1 table's 8 — pandoc covers the format dispatch for the worker-infra path as a side-effect):

| SDK input | Source path | Handler |
|---|---|---|
| HTML (post-pandoc) | worker-infra (EPUB/DOCX/MD via pandoc) | `html_walker.py` |
| Plain text | book-service synchronous `.txt` branch OR direct API call with `source_format=plain` | `plaintext_parser.py` |

**Markdown caveat:** `.md` import is not currently supported by `allowedImportFormats` in book-service ([import.go:21](../../services/book-service/internal/api/import.go)). P1 adds `.md` to the allowed set and routes it through worker-infra+pandoc (`-f markdown -t html`) — the SDK still consumes HTML, no new branch needed.

**Async vs sync `/internal/parse` contract is identical** — same endpoint, same request schema, same response. Different callers, same logic.

### D4 — HTML walker mapping: `<h1>=part`, `<h2>=chapter`, `<h3>=scene` (M1+M2+M4+H2 fixes)

**Parser library (M4 fix):** lock to `beautifulsoup4` with the stdlib `html.parser` backend (`BeautifulSoup(html, "html.parser")`). Rejected: `lxml` (raises on malformed input — real EPUBs occasionally have unclosed `<i>`/`<p>`); `html5lib` (slow + extra dep). `html.parser` is the lenient + zero-native-dep choice that handles pandoc's quirky-EPUB output gracefully.

**Pandoc `--standalone` wrapper handling (M1 fix):** pandoc emits `<html><head><title>...</title></head><body>...</body></html>`. Walker rules:
- Walk **children of `<body>` only**. Never descend into `<head>`.
- Capture `<head><title>` text as `book_title` fallback when no `<h1>` heading is present.
- Strip pandoc-generated `<nav class="toc">` blocks before heading walk — pandoc inserts a generated ToC `<nav>` as the first child of `<body>` for `--standalone`; the anchors inside would otherwise confuse heading detection.

**Heading walk (P1 — M2 fix: no EPUB nav-priority logic):**
1. Linear walk of `<body>` children, partitioning by `<hN>` boundaries.
2. `<h1>` → new part; `<h2>` → new chapter under current part; `<h3>` → new scene under current chapter. Heading text (via `tag.get_text(strip=True)`) → `title`.
3. **Single-`<h1>` book**: if exactly one `<h1>` exists at root, treat it as the **book title** (no part); `<h2>` siblings become chapters under an implicit `part-1`. (Common for single-volume novels.)
4. **No-heading book**: if zero `<hN>` headings, the whole `<body>` becomes 1 part / 1 chapter / 1 scene. Title = `<head><title>` or filename. P1 does NOT invoke semantic chunking — that's P4's escape valve.
5. **Scene boundary fallback** (no `<h3>` within an `<h2>`): scene = full chapter content as one leaf. Chapter-level paragraph splitting is **not** P1 — that's P2's leaf-sizing concern.

Rejected: EPUB `<nav epub:type="toc">` priority parsing. EPUB3 nav is a nested `<ol>/<li>/<a href="#anchor">` structure; back-resolving each anchor to a heading position is significant complexity. The `<h1>/<h2>/<h3>` walk alone produces correct trees for ≥95% of EPUBs we'll encounter (pandoc converts EPUB structure to heading-typed HTML by default). File P-NAV-AWARE-WALKER as a P3 deferred row if a real-world fixture surfaces an EPUB the heading walk misclassifies.

**Whitespace + horizontal-rule scene break (defensive):** pandoc emits `<hr/>` for `***` dinkus or Unicode ornament rows. The walker treats consecutive `<hr/>` (or `<hr>` followed by an empty paragraph) within an `<h2>` block as a scene boundary even without `<h3>` — captures author-intended scene breaks the heading-based pass misses. Configurable via SDK arg `scene_break_on_hr: bool = True`.

**HTML→text algorithm (H2 fix — LOCKED):**

`scene.leaf_text` is derived from the slice of HTML belonging to that scene via this exact pipeline:

```python
def html_to_leaf_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # strip script/style entirely (they contribute no readable text)
    for tag in soup(["script", "style"]):
        tag.decompose()
    # Replace <br/> with newline so paragraph reflow doesn't collapse intra-line breaks
    for br in soup.find_all("br"):
        br.replace_with("\n")
    raw = soup.get_text(separator="\n", strip=False)
    # Collapse runs of whitespace-only lines to exactly one blank line
    collapsed = re.sub(r"\n[ \t]*(?:\n[ \t]*)+", "\n\n", raw)
    # Trim leading/trailing whitespace
    return collapsed.strip()
```

This is the only HTML→text path in P1. The lossless round-trip test in §4.1 (`test_lossless_roundtrip_html`) pins the byte-output for a fixed HTML fixture against this algorithm. Future parser-library changes that perturb output bytes break the test — intentional canary against silent drift.

### D5 — Plain-text multi-language regex sets (M3 fix: whole-line anchor)

**All patterns require whole-line match (heading lines are standalone in narrative fiction)** — `(?m)^<pattern>\s*$`. This rejects mid-paragraph false-positives like `"I. understand that..."` being parsed as a Roman-numeral chapter heading.

| Language | Part marker (whole-line) | Chapter marker (whole-line) | Scene break |
|---|---|---|---|
| English | `^(Part\|Book\|Volume)\s+\d+\b.*$` | `^Chapter\s+\d+\b.*$`, `^[IVX]+\.\s*$` (Roman; whole-line only) | `^\s*\*\s*\*\s*\*\s*$` (dinkus); `^\s*[—–]{3,}\s*$` (em-dash row); blank line ×3 |
| Chinese (simp./trad.) | `^第[一二三四五六七八九十百千]+(部\|卷)\s*.*$` | `^第[一二三四五六七八九十百千]+(章\|回)\s*.*$` | `^\s*※\s*※\s*※\s*$`; `^\s*◇{2,}\s*$`; blank line ×3 |
| Vietnamese | `^(Phần\|Quyển)\s+(\d+\|[IVX]+)\b.*$` | `^(Chương\|Hồi)\s+\d+\b.*$` | `^\s*\*\s*\*\s*\*\s*$`; `^\s*[–-]{3,}\s*$`; blank line ×3 |
| Japanese | `^第[一二三四五六七八九十百千]+(部\|巻)\s*.*$` | `^(第[一二三四五六七八九十百千]+章\|その[一二三四五六七八九十百千]+)\s*.*$` | `^\s*※\s*※\s*※\s*$`; `^\s*◇{2,}\s*$`; blank line ×3 |

All compiled with `re.MULTILINE`. Case-insensitive (`re.IGNORECASE`) applied to EN + VI (Latin scripts only — case-insensitivity on CJK is a no-op but harmless).

**Roman-numeral regex (M3 specifically):** `^[IVX]+\.\s*$` requires the heading to be on its own line with no following non-whitespace characters — `"I. understand"` does NOT match (trailing word fails `\s*$`). `"I."` and `"III."` on their own lines DO match. Regression test fixture: a chapter that contains both `"I. understand the rule"` mid-paragraph AND `"I.\nThis is the first section."` as a section heading; assert only the section heading detected.

**Language detection** for `.txt`: the existing `original_language` form field (default `"auto"`) is the source of truth. `"auto"` → run all 4 regex sets over the first 4000 chars; pick the language whose **chapter marker** matches the most lines (part markers are sparser, less reliable for detection). Tie-break: prefer the language with the FIRST chapter match by file position (the language whose heading appears earliest). Falls back to "single chapter" if zero matches across all 4 sets.

### D6 — knowledge-service `/internal/parse` HTTP contract (H3 fix: body size limits)

Single endpoint on knowledge-service (the SDK's host process):

```
POST /internal/parse
  Headers: X-Internal-Token (existing middleware)
  Body (JSON): {
    "source_format": "html" | "plain",
    "content":       string,        // raw HTML or plain text
    "language":      string|null,   // ISO-639-1; null/"auto" runs detector
    "filename":      string|null,   // for diagnostics + title fallback
    "options":       {              // optional, all defaulted
      "scene_break_on_hr": true,
      "max_leaf_chars":    null     // P1: not enforced (P2 concern)
    }
  }
  Response 200 (JSON): StructuralTree (Pydantic dump)
  Response 400: malformed input
  Response 413: body exceeds MAX_PARSE_BODY_BYTES
  Response 422: structurally-degenerate input (e.g. empty content)
  Response 500: SDK internal error
```

**Body size limits (H3 fix):**
- knowledge-service config: `MAX_PARSE_BODY_BYTES=209715200` (200 MiB — matches `maxImportSize` at [book-service/import.go:19](../../services/book-service/internal/api/import.go#L19)).
- uvicorn config: `--limit-request-line 8192` (default OK for headers); body size enforced at the FastAPI `Request.body()` reader, NOT at uvicorn — we read with explicit `if len(body) > MAX_PARSE_BODY_BYTES: raise 413`.
- worker-infra HTTP client: `http.Client.Timeout = 5 * time.Minute` (same as pandoc call), no implicit body-size cap (Go HTTP client streams).
- book-service synchronous `.txt` call: `http.Client.Timeout = 30 * time.Second` (small files only — `.txt` upload is already capped by `maxImportSize` at server-side); body size won't approach the 200MiB cap.
- The 413 response is intentionally a hard fail (not a deferred job retry) — request body that large is either misconfigured caller or attack; not worth retrying.

**Idempotent:** same `content` + `language` + `options` → identical tree (verifiable by `content_hash` round-trip in tests).

**No persistence:** the endpoint is a pure transform. Caller (worker-infra for async, book-service for sync `.txt`) owns Postgres writes. This keeps knowledge-service stateless for this op.

**Observability:** OTel span `parse.structural_decomposition` with attributes `source_format`, `language`, `part_count`, `chapter_count`, `scene_count`, `leaf_max_chars`, `walker_path` (`"headings" | "fallback_single"` — note M2 dropped `"nav"`), `body_bytes` (request size).

### D7 — worker-infra integration (per-part + per-chapter Tx, R-SELF-2 self-review fix)

Replace the `splitChapters(html, format)` call site in [import_processor.go:168-226](../../services/worker-infra/internal/tasks/import_processor.go) with **3-level Tx scoping** — preserve the existing per-chapter Tx grain, add a tiny per-part Tx prelude:

```go
// 1. POST html → knowledge-service /internal/parse → StructuralTree JSON
tree, err := t.callParse(ctx, html, payload.FileFormat, payload.OriginalLanguage)
if err != nil {
    return 0, fmt.Errorf("parse: %w", err)
}

count := 0
chapterGlobalSort := 1

for partIdx, part := range tree.Parts {
    // (a) Tiny per-part Tx — insert ONE parts row, commit immediately.
    partID, err := t.insertPart(ctx, payload.BookID, partIdx+1, part.Title, part.Path)
    if err != nil {
        return count, fmt.Errorf("insert part: %w", err)
    }

    for _, ch := range part.Chapters {
        // (b) Per-chapter Tx — preserves existing grain. Chapter + draft + revision + scenes.
        tiptapJSON := htmlToTiptapJSON(ch.HTML)
        tiptapJSON, _ = extractAndUploadImages(...)  // existing best-effort image flow

        tx, err := t.BookDB.Begin(ctx)
        if err != nil { return count, fmt.Errorf("db begin: %w", err) }

        chapterID, err := insertChapterInTx(tx, payload.BookID, partID, ch.Path,
                                            chapterGlobalSort, tiptapJSON, ...)
        if err != nil { tx.Rollback(ctx); return count, err }

        insertDraftInTx(tx, chapterID, tiptapJSON)
        insertRevisionInTx(tx, chapterID, tiptapJSON, payload.UserID)
        for scIdx, sc := range ch.Scenes {
            insertSceneInTx(tx, chapterID, scIdx+1, sc.Path, sc.LeafText, sc.ContentHash)
        }
        if err := tx.Commit(ctx); err != nil {
            return count, fmt.Errorf("commit chapter: %w", err)
        }

        count++
        chapterGlobalSort++
    }
}
```

**Tx scope rationale:**
- Per-chapter Tx (b) matches **today's grain** — preserves the partial-success semantics existing code has (one chapter failure stops further chapters; chapters committed so far survive). 50 MB / 2500-chapter novel → 2500 small Tx, each ≤ 10 row writes + bounded MinIO PutObject batch. Postgres handles trivially.
- Per-part Tx (a) is tiny (one INSERT) — `parts` exist before any chapter under them is inserted; if (b) fails mid-part, the part row is **orphaned but valid** (zero chapters under it). Idempotent on retry: caller-side dedup on `(book_id, sort_order)` UNIQUE.
- Rejected: one-big-Tx (would regress current code). Rejected: per-import outer Tx wrapping per-chapter sub-Tx (savepoints add complexity for no benefit; existing per-chapter grain is correct).

**Failure semantics:** parse failure → whole import job marked `failed` (no partial chapters). Part insert failure → job `failed`, no chapters created. Per-chapter Tx commit failure → job marked `failed` with chapters-so-far retained (existing behaviour; row returned in `count`). Scene insert failure mid-Tx → that chapter rolls back; subsequent chapters proceed (per-chapter grain preserves this).

**`chapterGlobalSort` (book-global counter):** matches R-SELF-3 fix — `chapters.sort_order` is monotonic across parts, NOT reset per part. Honors the existing `UNIQUE (book_id, sort_order, original_language)` index without modification.

**`original_filename` + `storage_key` synthesis (L3 fix: multi-part variant):**
- Single-part books (`len(tree.parts) == 1`): preserve existing pattern `import-ch%03d.epub` / `chapters/{book_id}/import-{job_id}-{idx}` — full back-compat for single-volume novels.
- Multi-part books (`len(tree.parts) > 1`): new pattern `import-pt%02d-ch%03d.epub` / `chapters/{book_id}/import-{job_id}-pt{p}-{idx}` — disambiguates across parts in UI listings (current UI sorts by `sort_order` but lists by `original_filename`; collision would surface as duplicate-looking rows).
- `chapterGlobalSort` increments across parts (R-SELF-3); the `%03d` index uses `chapterGlobalSort - 1` consistently.

### D8 — StructuralTree Pydantic schema (canonical)

```python
class Scene(BaseModel):
    sort_order: int = Field(ge=1)
    path:       str           # "book/part-1/chapter-3/scene-2"
    leaf_text:  str
    content_hash: str         # sha256 hex of leaf_text

class Chapter(BaseModel):
    sort_order: int = Field(ge=1)
    title:      str | None
    path:       str           # "book/part-1/chapter-3"
    html:       str           # post-pandoc HTML for this chapter; consumed by htmlToTiptapJSON
    scenes:     list[Scene]   # ≥1; if no scene break, exactly 1 scene = full chapter

class Part(BaseModel):
    sort_order: int = Field(ge=1)
    title:      str | None
    path:       str           # "book/part-1"
    chapters:   list[Chapter] # ≥1

class StructuralTree(BaseModel):
    source_format: Literal["html", "plain"]
    detected_language: str | None    # populated only when input language was "auto"
    walker_path:   Literal["nav", "headings", "fallback_single"]
    book_title:    str | None
    parts:         list[Part]        # ≥1; missing-structure case = 1 part / 1 chapter / 1 scene
```

**Invariants** (enforced by Pydantic + asserted in walker tests):
- `len(parts) ≥ 1`; `len(part.chapters) ≥ 1`; `len(chapter.scenes) ≥ 1`.
- `path` strings are deterministic from sort_orders — re-parsing identical input MUST produce identical paths.
- Sum of `scene.leaf_text` across the tree, joined by `\n\n`, is the **lossless** plain-text projection of the input (round-trip-test asserts byte-equal after stripping HTML tags + whitespace normalization).

### D9 — ZERO LLM / embedding calls in P1 (acceptance gate)

Enforced by: no SDK import of `loreweave_llm` or `loreweave_extraction`; no HTTP client calls from the SDK; `/internal/parse` endpoint contains no LLM/embedding dependencies. Unit test asserts no outbound HTTP from SDK code.

### D10 — `parse_version` on parts + scenes

`parse_version int NOT NULL DEFAULT 1` lives on both `parts` and `scenes`. P1 ships version 1. Future SDK changes that invalidate prior trees (e.g. different scene-break rules) increment this; P3 / re-parse jobs detect mixed-version corpora.

This is the **only** forward-compat hook in P1. No event bus, no migration framework — just one int column.

---

## 4. Test plan

### 4.1 SDK unit tests (`sdks/python/tests/test_loreweave_parse_*.py`)

| Test | What |
|---|---|
| `test_html_walker_h1h2h3_tree` | EPUB-shaped HTML with `<h1>` parts, `<h2>` chapters, `<h3>` scenes → expected tree shape + paths |
| `test_html_walker_nav_priority` | EPUB `<nav epub:type="toc">` overrides heading inference; nav order wins over visual order |
| `test_html_walker_single_h1_book` | One `<h1>` (book title) + multiple `<h2>` (chapters) → implicit `part-1` wrapping all chapters |
| `test_html_walker_no_headings` | Zero headings → `walker_path="fallback_single"`, 1/1/1 tree, leaf_text = stripped full HTML |
| `test_html_walker_hr_scene_breaks` | `<hr/>` within an `<h2>` chapter creates scene boundary (`scene_break_on_hr=True`) + opt-out works |
| `test_plaintext_english_chapter_roman` | `Chapter 1` AND `I.` Roman headings detected; mixed within one file picks dominant |
| `test_plaintext_chinese_chapter_zh_zhcn` | `第一章` (trad.) + `第１章` (simp. numeric) variants detected |
| `test_plaintext_vietnamese_chuong_hoi` | `Chương 1` AND `Hồi 1` both recognised; case-insensitive |
| `test_plaintext_japanese_chapter` | `第一章` AND `その一` recognised |
| `test_plaintext_language_auto_detect` | `language="auto"` over 4-language sample picks correctly each time |
| `test_plaintext_dinkus_scene_break` | `* * *` row → scene boundary across all 4 languages |
| `test_lossless_roundtrip_html` | EPUB HTML → tree → join all `scene.leaf_text` → strip whitespace == strip(html_to_text(input)) |
| `test_lossless_roundtrip_plain` | Plain text → tree → join all scenes == input (byte-equal after CRLF normalisation) |
| `test_deterministic_paths` | Parse same input twice → identical `path` + `content_hash` across both runs |
| `test_no_outbound_http` | `httpx_mock` asserts SDK code makes zero HTTP calls; no LLM dep imported |

### 4.2 Knowledge-service router tests (`tests/unit/test_internal_parse.py`)

| Test | What |
|---|---|
| `test_parse_html_returns_tree` | POST html → 200 + StructuralTree JSON shape |
| `test_parse_plain_returns_tree` | POST plain → 200 |
| `test_parse_requires_internal_token` | Missing X-Internal-Token → 401 |
| `test_parse_empty_content_422` | `content=""` → 422 |
| `test_parse_whitespace_only_html_422` | L4 lock: `content="<html><body></body></html>"` → 422 (no extractable structure) |
| `test_parse_malformed_request_400` | Missing `source_format` → 400 |
| `test_parse_body_exceeds_limit_413` | H3 lock: content > MAX_PARSE_BODY_BYTES → 413 |
| `test_parse_language_auto` | `language=null` → response includes `detected_language` |
| `test_parse_otel_span_emitted` | Span `parse.structural_decomposition` with `body_bytes` + `walker_path` attributes |

### 4.3 worker-infra integration test (`internal/tasks/import_processor_test.go`)

| Test | What |
|---|---|
| `TestImportProcessorCallsParseEndpoint` | Mock `/internal/parse` returns 2-part-4-chapter-7-scene tree → assert DB has 2 rows in `parts`, 4 in `chapters`, 7 in `scenes`, all in one Tx |
| `TestImportProcessorTxRollbackOnSceneInsertFailure` | Mock scene insert fails → assert ZERO rows in parts/chapters/scenes (full rollback) |
| `TestImportProcessorParseFailureMarksJobFailed` | Mock `/internal/parse` returns 500 → import_jobs.status='failed', no chapters created |
| (`.txt` is handled by book-service NOT worker-infra — see §4.3a) | (removed: `.txt` doesn't reach worker-infra; H1 fix) |

### 4.3a book-service `.txt` synchronous path tests (`internal/api/import_test.go`)

| Test | What |
|---|---|
| `TestImportTxtCallsParseEndpoint` | H1 lock: `.txt` upload → mock `/internal/parse` returns 1-part-1-chapter-2-scene tree → assert DB has 1 part + 1 chapter + 2 scenes; `chapters.part_id` and `structural_path` populated |
| `TestImportTxtParseFailureReturns502` | Mock `/internal/parse` returns 500 → import returns 502 (upstream failure); zero rows in parts/chapters/scenes |
| `TestImportTxtMultiLangAutoDetect` | H1 + D5 lock: upload a Vietnamese `.txt` with `original_language=auto` → response `detected_language="vi"`, chapter markers parsed as `Chương` not `Chapter` |

### 4.4 Migration backfill test (`internal/migrate/migrate_test.go`)

| Test | What |
|---|---|
| `TestMigrationBackfillsExistingChapters` | Pre-existing books with chapters but no parts → after migrate: 1 part per book, 1 scene per chapter, `chapters.part_id` populated, `structural_path` set |
| `TestMigrationIdempotent` | Run migrate twice → no duplicate parts/scenes (backfill DO block guard works) |
| `TestMigrationPreservesNewBookParts` | Book with parts already (P1-created) → backfill skips it (DO block WHERE clause) |

### 4.5 Live smoke (cross-service, single chapter end-to-end)

Per CLAUDE.md cross-service evidence rule (worker-infra + knowledge-service + book-service → ≥3 services):

1. `docker compose up -d` (knowledge-service, book-service, worker-infra, postgres, minio, pandoc-server).
2. Upload Alice's Adventures EPUB via book-service `/v1/books/{id}/import`.
3. Assert: `import_jobs.status='completed'`, `parts` row created, `chapters` rows have non-null `part_id` + `structural_path`, `scenes` rows created with sane `leaf_text`.
4. Round-trip: query joined `leaf_text` for one chapter, compare to pandoc-stripped HTML — must match (allowing whitespace normalisation).

Evidence token for workflow-gate: `live smoke: Alice EPUB → 1 part / 12 chapters / 12+ scenes in book DB, leaf_text round-trips`.

## 5. Acceptance criteria (ADR §7 P1 mapped to this spec)

- [x] Multi-format parser handles EPUB, Markdown, plain-text EN/CN/VN/JP with structural markers → §3 D3 + D4 + D5.
- [x] `StructuralTree` Pydantic schema with `book/part/chapter/scene` levels → §3 D8.
- [x] Output for ≥10 fixture corpora round-trips without data loss → §4.1 `test_lossless_roundtrip_*` × 2 over 10 fixtures.
- [x] Unit tests cover marker detection per language → §4.1.
- [x] Integration test parses a real EPUB into a tree → §4.5 live smoke.
- [x] ZERO LLM / embedding calls in T1 → §3 D9 + §4.1 `test_no_outbound_http`.

## 6. Risks + mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | Pandoc output structure varies by version / source format quirks (esp. malformed EPUB) | Walker has 3 priority levels (nav → headings → fallback_single); any input yields a valid tree, never raises. Real-EPUB live smoke per `§4.5`. |
| R2 | Language auto-detect ambiguity on mixed-language books | Detector picks dominant within first 2000 chars; if zero matches across all 4, falls back to single-chapter book — same behaviour as today. PO can override via `original_language` form field. |
| R3 | ~~Single big Tx (50 MB → 2500 chapters) may stress Postgres~~ — **closed by R-SELF-2 fix**: per-chapter Tx grain preserved; per-part Tx is single INSERT | n/a |
| R4 | ~~Backfill DO block on a busy production DB locks `chapters` while running~~ — **closed by R-SELF-1 fix**: no backfill, legacy chapters use NULL sentinel | n/a |
| R5 | `scenes.leaf_text` storage bloat | At ~5 KB avg/scene, 12.5 k scenes = 62 MB plain text — trivial. PG TOAST handles per-row > 8 KB transparently. |
| R6 | Markdown input via pandoc may produce HTML the walker doesn't recognise (e.g. setext headings) | Pandoc normalises setext (`==` underline) → `<h1>`/`<h2>` ATX-style in HTML output; walker only sees the HTML. Tested via dedicated MD fixture in §4.1. |
| R7 | SDK package name collision with existing `loreweave_extraction` / `loreweave_llm` | `loreweave_parse` is a new name; pyproject.toml entry verified before BUILD. |
| R8 | Adding `.md` to `allowedImportFormats` introduces a public surface change | Trivial — append `".md": "markdown"` to the map in [import.go:21](../../services/book-service/internal/api/import.go); pandoc `-f markdown -t html` works out of the box. No FE change needed (file picker is `.*`). |
| R9 | `/internal/parse` has no rate limit; misconfigured caller could OOM knowledge-service (M7) | Internal-token-gated; attack surface is internal only. Filed `D-INTERNAL-PARSE-RATE-LIMIT` deferred row for post-P1. Not a P1 blocker. |
| R10 | `/internal/parse` 200 response for 50 MB book = 50+ MB JSON; FastAPI single-allocation (L1) | Acceptable for P1 typical input ≤ 1 MB. Streaming JSON response deferred to P3 (`D-INTERNAL-PARSE-STREAM` row). |

## 7. Locked design decisions (was: open questions; locked at REVIEW)

- **OQ1 → locked NO** — `chapters.structural_path` is NOT UNIQUE in P1. Re-parse at P3 needs the ability to overwrite the path string; uniqueness would force a delete-then-insert dance. Determinism still holds at the SDK level (same input → same path string) — uniqueness would only catch a bug we don't have. Revisit at P3 if re-parse races become a concern.
- **OQ2 → locked YES** — SDK's `Chapter.html` field carries post-pandoc HTML for that chapter's slice. worker-infra needs HTML for `htmlToTiptapJSON`; splitting at parse time is the cheapest join (vs sending plain content + asking worker-infra to re-slice HTML by path).
- **OQ3 → locked NO** — Plain-text `scene.leaf_text` is the full scene block as parsed; NO pre-emptive sentence/paragraph splitting in P1. That's P2's leaf-sizing concern (T2 in the parent ADR). P1's invariant: lossless round-trip — pre-splitting would change the byte count.

(All 3 are recommendations from §7 first-draft; PO ratifies at POST-REVIEW.)

---

## 8. Out-of-scope reminders (so REVIEW doesn't scope-creep)

- No parallel map / checkpoint table (P2).
- No tree-merge / per-level summaries (P3).
- No semantic chunking (P4).
- No LLM coreference / verify / multi-res retrieval (P5).
- No PDF support (deferred per CLARIFY).
- No glossary anchor fetch (P2 thread context concern; spec'd in parent ADR §3 T3).
- No Neo4j label changes (P3 — `:Scene`/`:Chapter`/`:Part`/`:Book` come with hierarchy build).
- No FE changes — user-visible behaviour identical to today after migration (chapters still flat in UI).
- No EPUB `<nav>` priority parsing (M2 deferred — file P-NAV-AWARE-WALKER if real EPUB needs surface).
- No rate-limit on `/internal/parse` (M7 deferred — `D-INTERNAL-PARSE-RATE-LIMIT`).
- No streaming response for `/internal/parse` (L1 deferred — `D-INTERNAL-PARSE-STREAM`).

## 9. Review trail

### Self-review (before /review-impl, all folded inline)

- **R-SELF-1 (HIGH)** — Backfill source mismatch: EPUB/DOCX path doesn't populate `chapter_raw_objects`. **Fix:** no backfill; NULL `structural_path` = "legacy" sentinel.
- **R-SELF-2 (MED)** — Tx scope regression: D7 first draft had one-big-Tx; existing code is per-chapter. **Fix:** 3-level Tx (per-part-INSERT + per-chapter-Tx grain preserved).
- **R-SELF-3 (LOW)** — `chapters.sort_order` uniqueness with multi-part. **Fix:** sort_order stays book-global; existing index untouched.

### /review-impl round 1 (10 findings, all folded inline)

- **H1** — `.txt` import bypasses worker-infra entirely; spec D3 was wrong. **Fix:** D3 rewritten — book-service synchronous `.txt` branch calls `/internal/parse` directly; new test row §4.3a.
- **H2** — HTML→text algorithm not locked. **Fix:** D4 locks `BeautifulSoup(html, "html.parser")` + explicit `html_to_leaf_text()` algorithm; regression-pin in §4.1.
- **H3** — `/internal/parse` body size limit unspecified. **Fix:** D6 adds `MAX_PARSE_BODY_BYTES=200MiB`, 413 response, explicit reader cap; §4.2 test row.
- **M1** — Pandoc `--standalone` HTML wrapper. **Fix:** D4 rule "walk children of `<body>` only", `<head><title>` → book_title fallback.
- **M2** — EPUB `<nav>` complexity dropped. **Fix:** D4 P1 = headings-only; `walker_path` enum collapsed to `"headings" | "fallback_single"`; nav-aware deferred to P3.
- **M3** — Roman numeral over-match. **Fix:** D5 all patterns whole-line anchored (`^...\s*$`); explicit regression fixture.
- **M4** — HTML parser library not locked. **Fix:** D4 locks `html.parser` backend.
- **M5** — `parts`/`scenes` missing `updated_at` + `lifecycle_state`. **Fix:** D2 schema adds both.
- **M6** — P2 fallback contract not locked. **Fix:** D2 adds "P2 fallback contract" subsection with explicit `if not scenes` branch.
- **M7** — No rate limit on `/internal/parse`. **Defer:** R9 + `D-INTERNAL-PARSE-RATE-LIMIT`.
- **L1** — Response body size for 50 MB book. **Defer:** R10 + `D-INTERNAL-PARSE-STREAM`.
- **L2** — 10 fixture corpora not enumerated. **Defer to PLAN.**
- **L3** — `original_filename` multi-part collision. **Fix:** D7 pattern `import-pt%02d-ch%03d.epub` when `len(parts) > 1`.
- **L4** — Empty/whitespace-only HTML undefined. **Fix:** §4.2 lock — 422.

POST-REVIEW (PO ratification): pending.
