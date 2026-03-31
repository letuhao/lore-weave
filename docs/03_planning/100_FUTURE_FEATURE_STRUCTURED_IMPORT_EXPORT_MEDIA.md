# Future Feature: Structured Import/Export & Media-Rich Chapters

## Document Metadata

- Document ID: LW-100
- Version: 1.0.0
- Status: **Deferred — Marker Only** (do not implement until planned phase)
- Owner: Product Manager + Solution Architect
- Created: 2026-03-31
- Created By: Product Owner decision
- Summary: Forward-looking specification markers for structured book/chapter import-export (zip bundles) and media-enriched chapter content (images, video — visual novel style). Not in scope for V1. Recorded here to prevent accidental design decisions that would block this capability later.

---

## Purpose

This document serves as an **architectural intent marker**. Its job is not to specify full implementation detail, but to:

1. Record the product owner's confirmed intent to support these features in a future phase.
2. Prevent current design decisions from painting us into a corner (e.g., schema choices, file storage layout, API shape).
3. Give future engineers and planners a starting context when the time comes to plan these features.

---

## Feature 1: Structured Import / Export (Zip Bundle)

### Summary

Users should be able to export a single chapter or an entire book as a structured `.zip` archive, and later re-import that archive into any LoreWeave instance. This enables portability, backup, and cross-instance migration.

### Motivation

- Current export (`GET /export`) returns plain text of the current draft — good for quick copy, but loses structure.
- Current import (`POST /chapters/import`) accepts a raw text file — good for initial ingestion, but cannot carry metadata, translations, glossary links, or media assets.
- A zip-based format makes the book a portable, self-describing artifact.

### Intended Scope (when planned)

**Chapter-level zip export:**
- `chapter.json` — metadata (title, language, sort_order, lifecycle_state, draft_format)
- `draft.txt` / `draft.md` — current draft body
- `original.txt` — original imported body (immutable, for reference)
- `revisions/` — numbered revision snapshots (optional, configurable)
- `media/` — any embedded media assets referenced in the chapter body (see Feature 2)

**Book-level zip export:**
- `book.json` — book metadata (title, description, language, cover info)
- `cover.<ext>` — cover image (if present)
- `chapters/<sort_order>_<chapter_id>/` — one sub-directory per chapter, same structure as chapter zip
- `glossary/` — glossary entities and attributes export (JSON)
- `translations/` — all translation results per chapter (optional, configurable)

**Import:**
- Accepts the same zip format and reconstructs the book/chapter in the target instance.
- Handles collision policy: skip, overwrite, or create-new.
- Validates manifest version for forward/backward compatibility.

### Key Design Constraints to Honor Now

| Constraint | Reason |
|---|---|
| `chapter_drafts.body` stores plain text or markdown (not binary blobs) | Zip export can extract body as a file; never store media inline in body text |
| Media assets must be referenced by stable content-addressable keys | Zip bundles reference assets by key, not embedded data URIs |
| chapter `original_filename` must remain stable | Zip manifest uses it for asset naming |
| Book and chapter UUIDs should be exportable and importable as metadata, not used as surrogate keys in zip filenames | Zip dirs use human-readable sort_order + title slug |

### Placeholder API Routes (reserve these paths now, do not implement yet)

```
POST /v1/books/{bookId}/export-zip          → Export full book as zip download
POST /v1/books/{bookId}/import-zip          → Import full book from zip upload
GET  /v1/books/{bookId}/chapters/{chapterId}/export-zip  → Export single chapter as zip
POST /v1/books/{bookId}/chapters/import-zip              → Import single chapter from zip
```

> **Note:** Do not reuse `/export` (plain text) for the zip endpoint — they are different features with different content types.

---

## Feature 2: Media-Rich Chapters (Visual Novel Support)

### Summary

Chapters should be capable of embedding or referencing media assets — images and video — to support visual-novel-style storytelling. This is a significant content model expansion and is **explicitly out of scope for V1**.

### Motivation

- LoreWeave's long-term vision includes supporting diverse novel formats beyond plain prose.
- Visual novels interleave text with character sprites, backgrounds, CG (event illustrations), and sometimes short video clips.
- The current `chapter_drafts.body` plain-text model cannot express this without a structured content format.

### Intended Scope (when planned)

**Content model evolution:**
- Introduce a `rich` draft format alongside the existing `plain` format (already tracked in `chapter_drafts.draft_format`).
- `rich` format: a structured document format (e.g., a lightweight JSON or Markdown-with-directives) where text blocks, image references, and video references are first-class nodes.
- Example node types: `paragraph`, `image`, `video`, `character_sprite`, `background`, `choice` (for interactive branches — very future).

**Asset storage:**
- Media assets stored in MinIO under a new bucket or prefix: `loreweave-media/<bookId>/<chapterId>/`.
- Assets referenced in the chapter body by a stable content key (not a full URL — URLs are resolved at read time via the API).
- Supported MIME types (initial): `image/jpeg`, `image/png`, `image/webp`, `image/gif`, `video/mp4`, `video/webm`.

**API additions (future):**
```
POST /v1/books/{bookId}/chapters/{chapterId}/assets       → Upload media asset
GET  /v1/books/{bookId}/chapters/{chapterId}/assets       → List assets
DELETE /v1/books/{bookId}/chapters/{chapterId}/assets/{assetId}
GET  /v1/books/{bookId}/chapters/{chapterId}/assets/{assetId}/url  → Presigned download URL
```

**Reader evolution:**
- The ReaderPage must gain a `rich` rendering mode alongside the current plain-text layout.
- Rich reader: renders paragraphs with inline images, full-bleed backgrounds, character sprites positioned via metadata.

**Editor evolution:**
- ChapterEditorPage must gain a rich-format toolbar (insert image, insert background, etc.).
- Drag-and-drop asset upload from editor.

### Key Design Constraints to Honor Now

| Constraint | Reason |
|---|---|
| `chapter_drafts.draft_format` column already exists and is populated (`plain`) | Adding `rich` later is a backward-compatible enum extension — do not remove this column |
| MinIO is already in the stack for chat attachments and book covers | Media assets follow the same pattern — do not bypass MinIO with filesystem storage |
| ReaderPage is currently a standalone route with its own layout | Keep it isolated so it can be upgraded to support rich rendering without touching the dashboard layout |
| Chapter editor is `EditorLayout` — already isolated from dashboard | Good — keep editor and dashboard layouts separate to allow editor to evolve independently |
| Avoid embedding base64 media data in `chapter_drafts.body` | Performance and diff-ability would degrade; always use asset references |

---

## Current State (as of 2026-03-31)

| Capability | State |
|---|---|
| Plain text chapter import (single file upload) | ✅ Implemented |
| Plain text chapter export (current draft, `GET /export`) | ✅ Implemented (fixed this session) |
| Chapter-level zip import/export | ❌ Not implemented — deferred |
| Book-level zip import/export | ❌ Not implemented — deferred |
| Media asset storage per chapter | ❌ Not implemented — deferred |
| Rich (visual novel) chapter format | ❌ Not implemented — deferred |
| `draft_format` column in `chapter_drafts` | ✅ Exists (value: `plain`) — ready for extension |

---

## Planning Gate

Before implementing either feature, the following must be completed:

1. A full execution pack and API contract doc (following the standard doc numbering: `LW-10X`).
2. A governance readiness gate doc.
3. Decision on rich format spec (custom JSON vs. a community standard like Ink, Ren'Py script dialect, or MDX).
4. Storage quota and billing policy for media assets.
5. Reader/editor UX wireframes for rich format.

---

## References

- `25_MODULE02_API_CONTRACT_DRAFT.md` — current book and chapter API shape
- `31_MODULE02_BACKEND_DETAILED_DESIGN.md` — book-service DB schema
- `99_FRONTEND_V2_REBUILD_PLAN.md` — frontend rebuild plan (ReaderPage and EditorLayout are defined here)
- `infra/docker-compose.yml` — MinIO service config
