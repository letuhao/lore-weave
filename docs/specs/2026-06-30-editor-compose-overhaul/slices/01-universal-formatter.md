# Slice 01 — Universal content formatter (BE bug fix)

> **Mode:** incremental / validate-first. Small, self-contained, reversible. **PO tests the user story
> before we continue.** Branch `feat/editor-compose-overhaul`.

## Problem (POC-proven)
Chapter content must be canonical **Tiptap JSON blocks** for read mode (the `chapter_blocks` trigger
reads the doc via JSON_TABLE) + glossary extraction. But the draft-write handler
(`book-service server.go` PatchDraft) **validates JSON yet never normalizes** — a `plain`/`markdown`
body is stored verbatim, so the trigger/reader/extractor see a bare string → read mode blank +
extraction crash (`'NoneType'.strip()`). `plainTextToTiptapJSON` exists but is plain-only (paragraphs);
nothing parses markdown headings/scenes.

## Scope (small)
1. **`markdownToTiptapJSON(text)`** in `book-service/internal/api/tiptap.go` — parse lightweight
   markdown (ATX headings `#`/`##`/`###` → heading nodes; blank-line blocks → paragraphs; wrapped lines
   joined). Each node keeps the `_text` snapshot the trigger needs. Unknown markup degrades to
   paragraph text (never loses content).
2. **`normalizeBodyToTiptap(raw, format)`** — `json` → pass-through (already a doc); `markdown` → parse
   via markdownToTiptapJSON; `plain` → plainTextToTiptapJSON. Always returns a doc + stored format `json`.
3. **Wire into `PatchDraft`** (server.go) — normalize before the UPDATE/INSERT so EVERY draft-write
   stores real blocks regardless of input format.
4. **Go test** for markdownToTiptapJSON (heading levels, paragraphs, mixed, empty).

**Deferred fast-follow (not this slice):** swap chapter import (`import.go`) from
`plainTextToTiptapJSON` → `markdownToTiptapJSON`. Import already produces valid blocks (plain-only), so
it's not broken — changing it risks existing import tests. Do it after the draft path is validated.

## Out of scope
Lists/blockquotes/inline marks (bold/italic) — paragraphs+headings cover compose output; add later if
the test shows a need. Other `plainTextToTiptapJSON` callers (mcp seed, parse) left as-is for now.

## User-story test (PO runs)
- **Compose path:** persist a chapter via the harness with `body_format:'markdown'` (raw `### scene` +
  prose) → open the chapter in **read mode** → it renders headings + paragraphs (not raw `###`/one blob).
- **Import path:** import a `.txt`/markdown chapter → read mode renders blocks.
- **Extraction:** re-run `poc_harness.py extract` on a markdown-persisted chapter → entities > 0.
- **Pass = read mode renders structured blocks + extraction works.** If it doesn't feel better, we stop
  and rethink before any further slices.

## Verify
`go build ./...` + `go test ./internal/api/ -run Tiptap` in book-service; rebuild the container; harness
markdown-persist → read + extract.

## Status
- [x] `markdownToTiptapJSON` + `normalizeBodyToTiptap` (`book-service/internal/api/tiptap.go`)
- [x] wired into `PatchDraft` (`server.go`) — import swap deferred (fast-follow)
- [x] Go test (`tiptap_test.go`) — passes (`go test ./internal/api -run "Tiptap|Normalize"` → ok)
- [x] rebuilt book-service + verified server-side: markdown body → `draft_format=json`,
      blocks `[heading, paragraph, paragraph]` (harness `mdtest`)
- [ ] **PO user-story test** (read mode) — pending. NOT committed yet (validate-first).
