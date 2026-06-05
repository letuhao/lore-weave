# Plan — Compose Slice 3 (mode F, attach files + OCR) · 2026-06-04

Spec [docs/specs/2026-06-03-enrichment-compose.md](../specs/2026-06-03-enrichment-compose.md) §2.4 (uploads), §2.3 (files branch), §4, §5 slice 3. Branch `lore-enrichment/foundation`. Type **XL FS** (BE + DB + Docker/OCR + MinIO + FE + i18n×4 + tests).

## Goal
`input_source="files"`: upload `.txt/.md/.pdf/.docx/.epub` → extract text (+OCR for scanned PDFs) → per file `ingest_corpus` → then identical to mode C (retrieval/recook grounded on the ingested corpus). Upload is **async/poll** (F10): `POST /uploads` returns `upload_id` immediately, extraction runs in the background, `GET /uploads/{id}` polls status.

## Acceptance (spec §5 slice 3)
- live: upload .pdf + .docx + scanned-pdf → extract(+OCR) → ingest → proposal.

## DB — `enrichment_upload` (new table, UP+DOWN)
`upload_id, user_id, book_id, project_id, filename, mime, size_bytes, pages, extracted_text, extracted_chars, ocr_used, license_asserted, status (processing|ready|failed), error_message, storage_key, created_at, updated_at`. Per-user/book scope; no FK (cross-DB ids). `status` drives the F10 poll.

## Config / storage
- `config.py` += `minio_endpoint/access_key/secret_key/bucket (lore-enrichment-uploads)/use_ssl` (compose already provides MINIO_* for the python services).
- `app/storage/minio_client.py` — boto3 `ensure_bucket`/`upload_file` (copy chat-service pattern; `run_in_executor`).

## Extraction — `app/files/extract.py`
`extract_text(filename, data: bytes, *, max_pages) -> ExtractResult(text, pages, ocr_used)`. Dispatch by extension:
- `.txt/.md` — decode utf-8 (errors=replace).
- `.pdf` — `pypdf` text layer; if a page has ~no text AND OCR is available → `pytesseract` over the rasterised page (chi_sim+chi_tra+eng). **OCR import-guarded**: if pytesseract/Tesseract absent → skip OCR, `ocr_used=False` (text-layer only) — never crash.
- `.docx` — `python-docx` paragraphs.
- `.epub` — `ebooklib` + `beautifulsoup4` (strip HTML).
- unknown ext → 415.

## Endpoints — `app/api/uploads.py`
- `POST /v1/lore-enrichment/uploads` (multipart: `file`, `book_id`, `project_id`, `license_asserted`): validate ext + size cap (25 MB); default-deny license (copyrighted/unknown→403 — reuse the mode-C map); store raw in MinIO; INSERT `enrichment_upload` status=`processing`; schedule background extraction (`asyncio.create_task` → `run_in_executor` for the blocking extract → UPDATE status=`ready`/`failed` + extracted_text/pages/chars/ocr_used). Return `{upload_id, filename, status:'processing'}`.
- `GET /v1/lore-enrichment/uploads/{upload_id}` — poll → `{upload_id, filename, mime, pages, extracted_chars, ocr_used, status, error?}` (owner-scoped; never returns the full text).

## `/compose` files branch (compose.py)
`input_source="files"`: require `upload_ids`; for each → load the upload (owner-scoped, status=`ready`, else 409/404) → `ingest_corpus` (reuse the mode-C `_ingest_context` text path with the upload's `license_asserted`) → collect corpus_ids → create the retrieval/recook job on the target (same as context). `files` moves future→supported.

## Infra
- `requirements.txt` += `python-multipart`, `boto3`, `pypdf`, `python-docx`, `ebooklib`, `beautifulsoup4`, `pytesseract`, `Pillow`, `pdf2image` (rasterise for OCR). OCR libs import-guarded in code.
- `Dockerfile` (service only — extraction is service-side, the worker re-drives the already-ingested corpus): `apt-get install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra poppler-utils`. (Documented deviation from the spec's "service+worker" — the worker does not extract.)
- freshness guard: the new apt deps are covered by the image SHA label (build-stack.sh).

## FE — `features/enrichment/`
- `components/compose/ComposeFilesForm.tsx` + `FileDropzone.tsx` (drag/drop, per-file upload→poll status (processing/ready/failed + pages/chars/ocr_used badge), license `<select>` + responsibility checkbox; remove file).
- `hooks/useCompose.ts` += `uploadFiles(files, {book_id, license}) -> upload results` (POST multipart + poll each to ready) — or a dedicated `useUploads` hook.
- `ModeSelector` enables `files`; `ComposePanel` wires the files form + run body (`input_source:'files'`, `upload_ids`); `api.ts`/`types.ts` `uploadFile`/`getUpload` + `UploadResult`; i18n `compose.files.*` ×4.

## Tests
- **BE pytest:** extract.py per format (txt/md/docx/epub with tiny fixtures; pdf text-layer; OCR mocked → ocr_used flag; unknown ext → error; page/size cap); `/uploads` (multipart accept + reject bad ext/oversize + license-deny + async status row); `/uploads/{id}` poll (owner scope); `/compose` files branch (ready upload → ingest called + job; not-ready → 409; copyrighted → 403).
- **FE vitest:** FileDropzone (add/remove, status render, license-required), ComposeFilesForm, ComposePanel files-mode run body, useCompose.uploadFiles.

## Live-smoke (cross-service)
Rebuild service (Tesseract) + run: upload .docx + a text .pdf + (if available) a scanned .pdf → extract(+OCR) → /compose files → grounded quarantined proposal. Defer if the Tesseract image rebuild / scanned fixture isn't available → D-COMPOSE-S3-LIVE-SMOKE.

## Risks
- OCR infra weight (Tesseract+CJK+poppler ~200 MB) — service image only; import-guarded so unit tests + a no-OCR image still work.
- Background extraction in-process: a service restart mid-extract leaves status=processing (acceptable v1; a reaper is a follow-up).
- redis-py 8 worker hot-loop (D-REDIS8) is pre-existing, unrelated.
