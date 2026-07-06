# Spec — PDF Book Import (text + image/chart, page-chunking)

- **Date:** 2026-07-06 · **Branch:** TBD (current branch `feat/context-budget-law` is unrelated — cut a new branch before BUILD) · **Phase:** CLARIFY (design locked this session; edge-case review in progress).
- **Size:** **XL** — new operation in `provider-registry-service`, new shared SDK module, new endpoint in `knowledge-service`, new DB tables/columns across `book-service`, new async worker branch in `worker-infra`, new frontend wizard. Cross-service contract change (5 services).

---

## 1. Problem (verified 2026-07-06)

Book-content import (`POST /v1/books/{book_id}/import`) accepts only `.docx/.epub/.txt/.md` (`services/book-service/internal/api/import.go:25-30`) — a PDF is rejected with `415` before any parsing. Audited separately (see project memory `pdf-ingestion-novel-only-gap`): the only PDF-capable code path in the repo is `lore-enrichment-service`'s `/uploads` (OCR-only, feeds an ephemeral RAG grounding corpus for chat, never becomes book chapters, no image/chart handling at all).

The user wants to import **lore/technical reference books** (not just novels) as PDFs, specifically:
1. PDF accepted as a first-class book-import format.
2. Embedded images/charts extracted and captioned by a vision LLM, with the caption text inlined into chapter content so glossary/KG extraction can "see" chart contents (this is the actual point of the exercise — testing whether glossary/KG works on a technical book).
3. A frontend step letting the user set "pages per chunk" (e.g. 5) so a long PDF (tested case: 500 pages / 4MB) splits into predictable chapters, since technical/reference PDFs frequently lack "Chapter N" heading markers the existing structural decomposer relies on (`sdks/python/loreweave_parse/plaintext_parser.py:47-92`).

The user explicitly does NOT want general non-fiction document modeling (tables/footnotes/code-listings as first-class structure) — this is scoped narrowly to: accept the format, chunk predictably by page count, extract+caption images.

## 2. CLARIFY locks (this session, via AskUserQuestion)

| # | Decision | Locked |
|---|---|---|
| **L1** | Extraction owner | `knowledge-service` (already owns `/internal/parse` for `.txt`; Python/AI per the repo's Language rule; natural home for the vision-caption call). |
| **L2** | Image handling depth | Extract images **and** AI-caption them (not asset-only) — captions inline into chapter text for KG/glossary visibility. |
| **L3** | Chunk semantics | A chunk of N pages = **exactly one chapter**. No heading-regex fallback for PDF — this is what solves the "no Chapter N markers" problem for lore/technical books. |
| **L4** | Import mode | **Async** (`import_jobs` + outbox + worker), same as docx/epub today — not sync like `.txt`, because vision-captioning is slow. |
| **L5** | Vision transport | Build a real, first-class `"vision"` job **operation** in `provider-registry-service` (typed enum + schema + contract + adapter wiring) rather than smuggling an image content-block through the existing untyped `"chat"` op. Chosen knowingly — pushes this from L to XL. |
| **L6** | knowledge-service call shape | **Per-chunk, not per-book.** Worker loops chunks itself, calling `/internal/parse/pdf-chunk` once per N-page window (one chapter + its images per call), not one whole-book request. Locked after adversarial review found the whole-book single-call design breaks worker's 5-min HTTP timeout once a book has more than ~5 images needing captioning (60s/vision-call budget) — see §6.1. |
| **L7** | `caption_images=false` behavior | Still extract + store images (as `chapter_page_images` rows with `caption=NULL`), just skip the vision call. Keeps state consistent regardless of the toggle; user can caption later without re-importing. |
| **L8** | Per-import caps | No hard cap on chapters/images per import — soft warning only (see §6.3) if the computed count is unusually high. User accepted the runaway-cost/duration risk for genuinely huge books rather than a hard ceiling. |
| **L9** | Idempotency | Add a basic dedup safeguard this session (not deferred) — `UNIQUE(book_id, import_job_id, structural_path)` + `ON CONFLICT DO NOTHING` on chapter insert — cheap now that L6 bounds the crash blast-radius to one chunk. |
| **L10** | Vision adapter coverage | **Revised at `/review-impl` (2026-07-06)** from "OpenAI-only v1" to real Anthropic + Ollama + LM-Studio implementations. The original stub posture was based on a mistaken assumption that local-backend vision support was uncertain — it wasn't: LM Studio's own model-inventory parsing (`parseLMStudioNativeModels`) already detected+flagged `capability_flags.vision` for a loaded vision model, and Ollama/LM-Studio already serve chat over the identical OpenAI-compatible `/v1/chat/completions` endpoint OpenAI itself uses. Anthropic's Messages API supports vision via a structurally different (but well-documented) image content-block shape. Live-verified end-to-end against LM Studio's `google/gemma-4-26b-a4b-qat` ($0 local cost) through the FULL real import pipeline — see §7. |

## 3. Architecture

```
FE wizard (features/pdf-import/)
  → POST /v1/books/{id}/import/pdf-peek        (NEW, sync, fast — opens the
        PDF just far enough to return {page_count}, and rejects encrypted/
        corrupted files immediately with a typed error — see §6.2)
  → POST /v1/books/{id}/import  (file=pdf, pages_per_chunk, caption_images)
        [book-service, Go] — adds .pdf to allowedImportFormats, same
        import_jobs + outbox("import.requested") path as docx/epub,
        carrying the two new params. Validates pages_per_chunk >= 1
        server-side (defense in depth, not just a UI clamp).
  → worker-infra ImportProcessor (Go) — NEW branch for file_format=="pdf":
        skip pandoc. Opens the PDF once (page count + chunk boundaries),
        then LOOPS chunks — one HTTP call to knowledge-service PER CHUNK
        (L6), not one whole-book call:
          for each chunk (pages [start,end]):
            POST /internal/parse/pdf-chunk {book_id, pdf_bytes_b64,
                page_start, page_end, chunk_index, caption_images, language}
            → get back ONE Chapter + that chunk's images
            → upload images to MinIO (extends image_extractor.go's
              upload pattern with a raw-bytes variant), one
              chapter_page_images row per image (caption=NULL if
              caption_images=false, per L7)
            → insert chapter+scene(s) in one Tx, ON CONFLICT DO NOTHING
              on (book_id, import_job_id, structural_path) per L9
            → emit incremental WS progress ("chapter 45/100") via the
              existing publishWSEvent path
        This bounds each HTTP call's duration/payload to one chunk's
        worth of images (fixes §6.1's timeout blocker) and means a
        worker crash mid-book only loses the in-flight chunk (L9).
  → knowledge-service /internal/parse/pdf-chunk (Python) — NEW endpoint,
        processes exactly ONE chunk per call:
        - sdks/python/loreweave_parse/pdf_walker.py (NEW, shared SDK module):
            PyMuPDF-based per-page text + embedded-image extraction for the
            given page range, OCR fallback (ported from lore-enrichment-
            service's extract.py, INCLUDING tesseract_lang_for's language-
            pack resolution — see §6.9 — so both services share one
            implementation instead of duplicating pypdf/pytesseract logic).
        - Builds exactly 1 Chapter for the given page range (title
          "Pages {start}-{end}", optionally suffixed with a best-effort
          heading-line guess — see §6.10) — bypasses the heading-regex
          walker entirely for this path (L3).
        - Extracted images are deduped by content hash within the call
          (repeat logos/watermarks caption once, reused for repeats —
          §6.3), filtered by minimum dimension (skip decorative/tracking
          pixels), and downscaled before the vision call if oversized.
        - If caption_images: for each deduped image, calls the new
          "vision" op via provider-registry (LLMClient.submit_and_wait,
          same pattern as thread_tag.py:129-135) to get a caption, appends
          "[Image (page N): <caption>]" into the chapter's scene text.
          A per-image caption failure (guardrail rejection, model error,
          timeout) is caught and degrades to "image stored, caption=NULL"
          — never fails the whole chunk (mirrors motif_tag.py/thread_tag.py's
          existing "advisory, never raises" discipline in this codebase).
        - Returns {chapter: Chapter, images: [{page_number, image_bytes_b64,
          caption, model_ref}]} — one chapter's worth, not the whole book.
  → provider-registry-service — NEW "vision" job operation:
        jobs_handler.go validJobOperations enum, request/result schema,
        cost-estimation function wired into the existing guardrail
        preflight (§6.4 — a required part of "adapter wiring", not
        implicit), openapi contract, adapter wiring (at minimum OpenAI
        gpt-4o path, since the test account has BYOK access to it) —
        degrade clearly (explicit error, not silent failure) when the
        resolved model lacks capability_flags.vision.
```

## 4. Component design

### 4.1 `provider-registry-service` — new `"vision"` operation
- `internal/api/jobs_handler.go:50-59` — add `"vision"` to `validJobOperations`.
- New result shape mirroring `ImageGenResult` structurally but inverted (input=image+prompt, output=caption text) — Python mirror alongside `sdks/python/loreweave_llm/models.py:414-531`, Go-side counterpart wherever that's mirrored.
- `contracts/api/llm-gateway/v1/openapi.yaml` — document input/result, consistent with `chat`/`completion` docs around line 903-912.
- Adapter wiring (L10, revised at `/review-impl`): **OpenAI** (`openai_vision.go`), **Ollama + LM-Studio** (`local_vision.go`, sharing `openai_compat_vision.go`'s request builder/parser — both serve the identical OpenAI-compatible `/v1/chat/completions` multimodal shape OpenAI itself uses), and **Anthropic** (`anthropic_vision.go`, its own Messages-API image-content-block shape). No capability_flags pre-flight gate (no such gate exists anywhere else in this package either — GenerateImage/GenerateVideo don't pre-check either); an unsupported/text-only model's rejection classifies to `LLM_UPSTREAM_ERROR` like any other bad request.
- Build and live-prove this FIRST (one real BYOK call captioning a test image) before anything else depends on it — first real multimodal wire-up in this codebase. Live-verified against OpenAI gpt-4o AND against LM Studio's local `google/gemma-4-26b-a4b-qat` ($0 cost) — see §7.
- **Live-caught bug (reasoning-model token budget)**: a reasoning-capable local vision model (gemma-4-26b-a4b-qat) writes its chain-of-thought into a separate `reasoning_content` field and can exhaust `max_tokens` before ever writing the real answer into `content` — at `max_tokens=150` the model correctly identified the test chart in its reasoning but got cut off (`finish_reason="length"`) before emitting a caption, so the caption came back empty. Fixed by raising `_CAPTION_MAX_TOKENS` (`internal_parse_pdf.py`) from 150 to 700 — confirmed live at 600 the same model completes reasoning (~440 tokens) and emits a correct caption.

### 4.2 `sdks/python/loreweave_parse/pdf_walker.py` — new shared SDK module
- Add `pymupdf` (imports as `fitz`) to `services/knowledge-service/requirements.txt`; leave `lore-enrichment-service`'s `pypdf`/`pytesseract`/`pdf2image` in place (separate grounding-corpus path, unaffected).
- Port `lore-enrichment-service/app/files/extract.py`'s `_extract_pdf`/`_ocr_pdf_pages` into this shared module (parameterized per-page), same lazy-import/graceful-degradation discipline (`extract.py:8-13`).
- New: embedded image extraction via `page.get_images(full=True)` + `doc.extract_image(xref)`. **Known v1 limitation**: vector-drawn charts with no embedded raster image aren't captured this way (full-page rasterization fallback is a follow-up, not v1).
- Shape: `walk_pdf_pages(data: bytes, *, max_pages: int) -> list[PageContent]`, `PageContent = {page_number, text, ocr_used, images: list[bytes]}`.

### 4.3 `knowledge-service` — new `/internal/parse/pdf-chunk` endpoint
- New router, separate from `/internal/parse` (whose `ParseRequest.content: str` single-text-blob contract stays untouched — both existing callers depend on it as-is).
- Request: `{book_id, pdf_bytes_b64, page_start, page_end, chunk_index, caption_images, language}` — **one chunk per call** (L6), not the whole book. `pdf_bytes_b64` is re-sent per call (simplest; the worker already holds the full bytes from its one MinIO download) — the endpoint only walks pages `[page_start, page_end]` of it.
- `walk_pdf_pages(data, page_start, page_end)` → exactly one `Chapter` (title `"Pages {start}-{end}"`, one `Scene` with joined page text + inline `[Image (page N): caption]` markers) — no `Part`/tree wrapping here, the worker assembles the book-level part/sort_order (§4.5/4.6 fix for the sort_order-collision issue found in review, §6.11).
- Image handling before captioning: dedupe by content hash (repeat logo → caption once, §6.3), drop images under a minimum-dimension threshold (§6.3), downscale oversized images before the vision call (original full-res bytes still go to MinIO for display).
- Captioning via `LLMClient.submit_and_wait(operation="vision", ...)`, same pattern as `thread_tag.py:129-135`. Per-image failure degrades to `caption=None` (never fails the chunk, §6.4/§6.7) — only relevant when `caption_images=true`; when `false`, images are still extracted and returned uncaptioned (L7).
- Response: `{chapter: Chapter, images: [{page_number, image_bytes_b64, caption, model_ref}]}` — Python doesn't touch MinIO in this codebase; that stays in Go (worker uploads and inserts `chapter_page_images` rows).
- `language` threads through to the ported `tesseract_lang_for` mapping for the OCR fallback path (§6.9) — not just carried in the request shape but actually consumed by `walk_pdf_pages`'s OCR branch.

### 4.4 New table: `chapter_page_images` + `import_jobs` columns
```sql
CREATE TABLE IF NOT EXISTS chapter_page_images (
  id UUID PRIMARY KEY DEFAULT uuidv7(),
  chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
  page_number INT NOT NULL,
  storage_key TEXT NOT NULL,
  caption TEXT,               -- NULL when caption_images=false (L7) or a
                               -- per-image caption call failed (§6.4/§6.7)
  model_ref TEXT,              -- populated from the vision job's result
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
`import_jobs` (`migrate.go:219-234`) gains `pages_per_chunk INT`, `caption_images BOOLEAN NOT NULL DEFAULT false`.

`chapters` gains a new idempotency constraint (L9): confirmed via grep that `chapters` has **no `import_job_id` column today** — add it (`UUID NULL REFERENCES import_jobs(id)`, nullable so pre-existing non-import and pre-PDF rows are unaffected), plus a partial unique index `UNIQUE(book_id, import_job_id, structural_path) WHERE import_job_id IS NOT NULL`. The per-chunk insert (§4.6) uses `ON CONFLICT (book_id, import_job_id, structural_path) DO NOTHING` so a redelivered chunk after a worker crash doesn't create a duplicate chapter. Scoped to the PDF path only (`import_job_id` set on insert) — doesn't change behavior for existing docx/epub/txt imports which leave it NULL.

### 4.5 `book-service` — wire `.pdf` into the existing async import path
- `allowedImportFormats` (`import.go:25-30`) gains `.pdf: "pdf"`.
- `startImport` reads two new multipart fields (`pages_per_chunk`, `caption_images`) for the pdf format, stores on `import_jobs`, includes in the `import.requested` outbox payload.
- New `POST /v1/books/{book_id}/import/pdf-peek` (sync, fast page-count only) for the FE configure step's live preview.

### 4.6 `worker-infra` — `ImportProcessor` PDF branch
- New branch in `processImport` for `file_format=="pdf"`: skip `callPandoc`. Open the PDF once to get page count, compute chunk boundaries from `pages_per_chunk`, compute one `Part` up front using the SAME "next available sort_order" logic already used for chapters (`chapterGlobalSort`, `import_processor.go:185-191`) instead of a hardcoded `sort_order=1` — fixes the part-collision-on-re-import bug found in review (§6.11).
- **Loop chunks** (L6): for each chunk, POST to knowledge-service's `/internal/parse/pdf-chunk` with that chunk's page range; get back one chapter + its images.
- Per chunk, in one Tx: insert the chapter (`INSERT ... ON CONFLICT (book_id, import_job_id, structural_path) DO NOTHING`, the new dedup safeguard from L9/§6.7), insert its scene(s), upload each returned image to MinIO (extend `image_extractor.go`'s upload logic with a raw-bytes variant, since PDF images arrive as bytes not `data:` URIs) and insert a `chapter_page_images` row per image, then emit an incremental WS progress event via the existing `publishWSEvent` path (e.g. `{completed_chapters: N, total_chapters: M}`) so the FE progress step (§4.7) can show real per-chapter progress instead of one opaque "processing" state.
- If the computed total chapter/expected-image count is unusually high (soft warning only, L8 — no hard cap), log it; no job-level rejection.

### 4.7 Frontend — `features/pdf-import/` wizard
Mirror `features/extraction/`'s hook/component split (NOT `components/import/ImportDialog.tsx`, which already violates this repo's MVC rules and shouldn't be extended): `usePdfImportState.ts` (step machine), `usePdfImportPolling.ts` (mirrors `useExtractionPolling.ts`), `StepUpload/StepConfigure/StepConfirm/StepProgress/StepResults.tsx`. Configure step: numeric "pages per chunk" (default 5) + live `Math.ceil(page_count/pagesPerChunk)` chapter-count preview + "Caption images with AI (uses LLM credits)" toggle.

## 5. Build order

1. **Vision op in provider-registry** — prove live first (one real BYOK gpt-4o call captioning a test image). Includes wiring the guardrail preflight's cost-estimation function for `vision` as part of this step, not an afterthought (§6.4) — a job must not be either silently under-priced or rejected as "unpriced."
2. **`pdf_walker.py` SDK module** — pure, unit-testable standalone. Covers: per-page-range text+image extraction, OCR fallback with `tesseract_lang_for` language plumbing (§6.9), image dedup-by-hash + min-dimension filter + downscale (§6.3), and explicit handling of `fitz.open()` failure / `doc.needs_pass` (encrypted) as distinguishable, non-silent outcomes (§6.2).
3. **`knowledge-service /internal/parse/pdf-chunk`** wired to both — one chunk in, one chapter+images out, per-image caption failure degrades to `caption=None` without failing the chunk (§6.4/§6.7).
4. **DB migrations** (`chapter_page_images`, `import_jobs` new columns, `chapters.import_job_id` + partial unique index) + **book-service** `.pdf` allowlist + server-side `pages_per_chunk >= 1` validation + `pdf-peek` (page count, encrypted/corrupted rejection at this step — §6.2).
5. **worker-infra** PDF branch — chunk loop, per-chunk Tx with `ON CONFLICT DO NOTHING`, part sort_order fix (§6.11), incremental WS progress.
6. **Frontend wizard** — mirrors `features/extraction/`; configure step shows chapter-count preview and a soft high-count warning (§6.3/L8), not a hard block.
7. **Cross-service live smoke + explicit failure-path tests** (§6.8) — not just the happy path:
   - Happy path: real multi-chapter PDF with ≥1 chart, `pages_per_chunk=5`, `caption_images=true` → chapters split correctly, ≥1 image captioned, glossary/KG extraction (run separately, unchanged) picks up terms from the captioned chart text.
   - `caption_images=false` → images stored with `caption=NULL`, chapter text has no `[Image: ...]` markers.
   - Encrypted/password-protected PDF → rejected at `pdf-peek`, clear error, no job created.
   - A PDF with a repeated logo across many pages → confirm only one vision call for that image (dedup working), reused caption on repeats.
   - Simulated guardrail rejection mid-batch (e.g. temporarily lower a spend cap) → chunk still completes, affected image(s) end up `caption=NULL`, job doesn't fail.
   - Re-running the same `import.requested` event (simulated redelivery) → no duplicate chapters (`ON CONFLICT DO NOTHING` holds).

## 6. Open questions / edge cases (adversarial review — resolved 2026-07-06)

An independent design review (fresh-context Plan agent, read-only, cross-checked against `extract.py`, `import_processor.go`, `parse_client.go`, `internal_parse.py`, `config.py`, `jobs_handler.go`, `adapters.go`, `StepConfirm.tsx`) surfaced 17 concerns before BUILD. Resolutions below; items marked **(user decision)** were escalated via AskUserQuestion this session, the rest were resolved by applying existing codebase conventions.

1. **Chunk math edge cases** — no validation existed anywhere for `pages_per_chunk`. **Resolved**: floor of `>= 1` enforced both client-side (FE clamp) and server-side (book-service field validation + `/internal/parse/pdf-chunk` request validation — defense in depth across the 3-hop chain). `pages_per_chunk >= page_count` → 1 chapter (expected, not a bug). 0-page/corrupted PDF → rejected at `pdf-peek` (§6.2), not a silently-empty "completed" job. No hard cap on resulting chapter count **(user decision: L8 — soft warning only, no hard block)**.

2. **PDF pathologies (encrypted/corrupted, fitz vs pypdf failure modes)** — fitz's failure mode for encryption is silent (empty text, no exception) unlike pypdf's catchable exceptions; the spec originally didn't reconcile the two libraries' different degradation surfaces. **Resolved**: `pdf-peek` explicitly checks `fitz.open()` for exceptions AND `doc.needs_pass` before returning a page count — an encrypted or corrupted PDF is rejected there with a typed, user-visible error, before the user even reaches the configure step. This is cheaper than discovering it only after the async job starts.

3. **Image extraction pathologies (repeated images, huge images, dense pages, decorative/trivial images)** — none of dedup, size limits, or per-page caps existed in the original design. **Resolved**: dedupe by content hash within a chunk call (a repeated logo/watermark captions once, cached for repeats — direct cost avoidance); minimum-dimension filter skips decorative/tracking-pixel images; oversized images are downscaled before the vision call (original full-res bytes still uploaded to MinIO for display). No hard per-page/per-chunk image cap **(user decision: L8 — same soft-warning posture as chapter count)**.

4. **Cost / spend-guardrail integration** — the biggest real gap: no pre-flight cost estimate, no stated behavior when the guardrail rejects an in-progress batch, no vision-specific cost-estimation function mentioned. **Resolved**: (a) per-image caption failure (including guardrail rejection) degrades to `caption=None`, never fails the chunk/job — mirrors this codebase's existing `motif_tag.py`/`thread_tag.py` "advisory, never raises" discipline; (b) the vision op's cost-estimation function is an explicit Build Order sub-step (§5.1), not an implicit side effect of adapter wiring; (c) exact pre-import cost estimate isn't feasible (image count is unknowable without opening every page), so the FE configure step shows a chapter-count preview plus a soft "cost shown as processing proceeds" framing rather than a false-precision number.

5. **Payload size over internal HTTP** — base64 inflates the request ~33% (a PDF near book-service's 200MB ceiling could exceed knowledge-service's `max_parse_body_bytes` once wrapped), and the original whole-book-response design had an uncapped, potentially multi-hundred-MB response. **Resolved by L6** (per-chunk calls): each request/response now carries only one chunk's PDF-bytes-resend + that chunk's images, bounding both sides to a small, predictable size — the whole-book base64/response-size risk is eliminated by the architecture change, not just mitigated.

6. **Frontend double file transmission** (`pdf-peek` then the real upload) — accepted as-is for now: the spec's test case is 4MB, and `pdf-peek`'s multipart POST is stateless/throwaway (nothing persisted, nothing to clean up if the user abandons after peek). Worth revisiting if this format later needs to handle much larger technical-reference PDFs (50-200MB), but out of scope for this pass.

7. **Idempotency / crash recovery** — a worker crash mid-book previously risked N duplicate chapters on outbox redelivery (no dedup check existed, unlike `bulkCreateChapters`'s explicit filename dedup). **Resolved (user decision: fix now, not deferred)**: `chapters.import_job_id` (new column) + partial unique index `(book_id, import_job_id, structural_path) WHERE import_job_id IS NOT NULL`, `ON CONFLICT DO NOTHING` on the per-chunk insert. Combined with L6 (per-chunk calls), a crash now loses at most the one in-flight chunk, and redelivery is a safe no-op for already-committed chunks.

8. **Duration/timeout assumptions tuned for fast formats** — the single highest-priority finding: the original whole-book single-HTTP-call design would time out on the worker's existing 5-minute `ParseClient` timeout for any book needing more than ~5 vision-captioned images (60s/call budget per `config.py:167-169`'s documented "extractors that need longer should split their work" rule) — meaning it would fail on this spec's own worked example. **Resolved by L6** — per-chunk calls bound each individual HTTP call's duration to one chunk's images, not the whole book, directly satisfying the codebase's own stated design principle instead of violating it.

9. **Language/OCR plumbing** — `language` was present in the request shape but the spec didn't confirm `tesseract_lang_for`'s pack-resolution logic (vs. just the raw Tesseract invocation) was actually part of the port. **Resolved**: explicitly locked in §4.3/Build Order step 2 — `pdf_walker.py` ports `tesseract_lang_for` itself, not just `_ocr_pdf_pages`'s mechanics, and `/internal/parse/pdf-chunk` threads `language` through to it.

10. **Chapter title quality** ("Pages N-M" only) — **(user-facing judgment call, not escalated further since it's low-stakes and reversible)**: keep the page-range as the always-present, authoritative part of the title, and add a best-effort heading-line heuristic (short first non-empty line, title-cased/no terminal punctuation) as a supplementary suffix when one looks plausible — never depended on downstream. Cheap, matches the codebase's existing "nice-to-have that degrades gracefully" pattern (OCR-only-if-available, caption-only-if-flagged).

11. **Part sort_order collision on re-import** — the original design's "single synthetic Part" would hardcode `sort_order=1`, silently colliding with `ON CONFLICT (book_id, sort_order) DO UPDATE` if the book already has a part 1 from a prior docx/txt import (overwriting its title/path). **Resolved**: worker computes the new part's `sort_order` using the same "next available" logic already used for `chapterGlobalSort` (`import_processor.go:185-191`), not a hardcoded 1 — see §4.6.

12. **No rollback/cleanup for orphaned MinIO blobs on partial failure** — pre-existing gap for docx/epub (the source file isn't cleaned up on failure either), compounded by the new per-image blobs. **Not fixing in this pass** — out of scope per the repo's defer-eligibility gate (pre-existing pattern shared across all import formats, not introduced by this feature); tracked as a Deferred item in `docs/sessions/SESSION_HANDOFF.md` at BUILD completion rather than silently carried forward unrecorded.

13. **`caption_images=false` path was ambiguous** (extract-and-store-uncaptioned vs. skip-extraction-entirely) — **(user decision: L7)** — still extract and store images with `caption=NULL`, so toggling captioning on later doesn't require re-importing.

14. **`model_ref` provenance** — needed to actually be populated from the vision job's result, not just exist as a column. Locked as part of the `chapter_page_images` schema note (§4.4) and the endpoint's response shape (§4.3).

15. **Test coverage for failure paths** — the original Build Order only listed a happy-path smoke test. **Resolved**: §5 step 7 now explicitly enumerates encrypted-PDF, `caption_images=false`, repeated-image dedup, guardrail-rejection-mid-batch, and redelivery/duplicate-prevention as required verification scenarios, not just the successful multi-chapter case.

16-17. Minor items (max-batch-size numeric defaults, exact warning thresholds for §6.1/§6.3's soft-warning posture) are left as implementation-time judgment calls within the locked L6-L9 decisions above, not further escalated.
