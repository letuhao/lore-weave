# LoreWeave Module 02 UI/UX Improvement Implementation Plan (Docs-Only Baseline)

## Document Metadata

- Document ID: LW-M02-36
- Version: 0.3.0
- Status: Approved
- Owner: Product Designer + Solution Architect
- Last Updated: 2026-03-21
- Approved By: Decision Authority
- Approved Date: 2026-03-21
- Summary: Docs-only implementation plan for upgrading Module 02 UX/UI to product-grade quality, defining full scope, phases, acceptance criteria, and backend-support requirements without changing source code in this step.

## Change History


| Version | Date       | Change                                                                 | Author    |
| ------- | ---------- | ---------------------------------------------------------------------- | --------- |
| 0.3.0   | 2026-03-21 | Approved by Decision Authority (status governance update) | Assistant |
| 0.2.0   | 2026-03-21 | Editor library decision updated: choose Lexical for Module 02 editor | Assistant |
| 0.1.0   | 2026-03-21 | Initial docs-only UI/UX improvement implementation plan               | Assistant |


## 1) Execution Boundary (Mandatory)

- This document is a **planning artifact only**.
- In this step, the team **must only create/update markdown documents**.
- No code implementation is performed in this step for:
  - `frontend/src/`*
  - `services/*`
  - `contracts/*`
  - `infra/*`
- Code execution starts in a separate, explicitly approved implementation step.

## 2) Problem Statement and Improvement Targets

Module 02 currently works as a technical MVP but not as a commercial-grade experience. The following gaps are in scope for the next execution step:

1. Sharing status is not visible in book list.
2. After changing sharing status, user is not redirected back to book detail.
3. Language selection is plain text only (missing dropdown with code+name and custom input).
4. Book creation misses description and cover input in UX flow.
5. Chapter browsing is missing pagination and product-level browsing UX.
6. User cannot create chapter directly in editor (upload-only path).
7. Raw download fails with unauthorized behavior in owner workflow.
8. History browsing experience is incomplete.
9. Navigation model is weak for owner/public/sharing areas.
10. Public books cannot be explored/read in a complete reader flow.

## 3) UX Strategy (Real-World Product Baseline)

This plan follows proven patterns seen in modern writing/publishing products (for example, Notion, Substack, Wattpad, GitBook):

- **Workspace-first IA:** split owner workflow and reader workflow clearly.
- **Predictable action outcomes:** each mutation has loading/success/error state and post-action navigation.
- **List-to-detail continuity:** every list screen supports fast context handoff (status, badges, quick actions).
- **Editor-first content creation:** creation and editing are first-class, uploads are optional path.
- **Progressive disclosure:** advanced controls (filters/history/metadata) stay accessible without cluttering base flow.

## 4) Information Architecture and Navigation Model

### 4.1 Global areas

- **Owner Workspace**
  - My Books
  - Book Detail
  - Chapter Browser
  - Chapter Editor
  - Recycle Bin
- **Sharing**
  - Sharing policy panel per book
- **Public Discovery**
  - Public Browse
  - Public Book Detail
  - Unlisted Access Detail

### 4.2 Navigation components

- Primary top navigation with grouped entries:
  - `Workspace`
  - `Recycle bin`
  - `Browse`
- Secondary navigation inside book detail:
  - `Overview`
  - `Chapters`
  - `History`
  - `Sharing`

## 5) Screen-Level Plan

### 5.1 My Books (`BooksPage`)

- Show cards/table rows with:
  - title
  - original language badge
  - chapter count
  - lifecycle status
  - sharing status badge (`private|unlisted|public`)
- Book creation form includes:
  - title (required)
  - description (optional)
  - original language picker (dropdown + custom)
  - cover upload

### 5.2 Book Detail (`BookDetailPage`)

- Add chapter browsing component with:
  - pagination
  - language filter
  - lifecycle filter (active/trashed)
  - sort controls
- Add quick actions:
  - create chapter (editor mode)
  - upload raw chapter
  - open sharing panel
  - recycle actions

### 5.3 Sharing (`SharingPage`)

- Keep visibility selector + unlisted URL block.
- On successful save, redirect to `/books/{bookId}` with success feedback.

### 5.4 Chapter Editor + Create

- Add separate create flow that starts with editor (no file upload required).
- Keep upload flow as optional import path.
- Include metadata panel:
  - chapter title
  - sort order
  - language picker

### 5.5 Chapter History Browsing

- Add dedicated history browse panel:
  - pagination for revisions
  - commit message / timestamp / author info
  - preview then restore action

### 5.6 Public Browse and Reader Detail

- Public browse becomes reader-grade list with search, pagination, and language cues.
- Public detail supports:
  - book metadata
  - chapter list reader navigation
  - stable rendering of public/unlisted paths

## 6) Component System Plan

Reusable UI components to be delivered in implementation step:

- `LanguagePicker` (preset + custom free input; display `name (code)`).
- `ShareVisibilityBadge`.
- `StatusBadge` for lifecycle.
- `ChapterTable` with filter/sort/pagination controls.
- `RevisionHistoryPanel`.
- `PaginationBar`.
- `EmptyState`, `ErrorState`, `LoadingSkeleton`.

## 7) Editor Library Decision (Locked)

Editor library is now fixed to **Lexical** for Module 02 implementation.

Rationale for selecting Lexical:

- strong multilingual input behavior and predictable IME handling
- flexible extension model for future rich-text requirements
- good performance profile for long chapter editing
- clear abstraction path for `ChapterRichEditor` to reduce vendor lock-in

Implementation guidance:

- create a `ChapterRichEditor` wrapper on top of Lexical
- keep draft storage contract unchanged (`body` as canonical text payload)
- keep upload-as-import path separate from editor-first creation path

## 8) Backend/Gateway Support Requirements (Planning Contract)

To support UX improvements, implementation step must validate/add:

- owner-visible sharing status in book list payload
- chapter list pagination metadata (`total`, `limit`, `offset`)
- chapter create by JSON/editor path (no file required)
- raw download auth behavior through gateway for owner flow
- public browse/detail consistency for `public` visibility
- unlisted/public lifecycle gating remains `404` for `trashed|purge_pending`

## 9) Test and Acceptance Plan for Implementation Step

- **Frontend UT/RTL**
  - list/detail/sharing/navigation/pagination/editor/history interactions
- **Backend integration**
  - chapter create paths (upload + editor)
  - raw download auth pass-through
  - sharing/public visibility behaviors
- **E2E smoke**
  - owner: create book -> create chapter -> edit/history -> share -> recycle
  - reader: browse public -> open detail -> open unlisted

## 10) Definition of Done (for future implementation step)

- All 10 improvement targets are implemented and verified.
- UX flows are coherent across owner and reader surfaces.
- No lifecycle/share visibility regressions.
- GC physical deletion remains out of scope.

## 11) Next Step Gate

- Decision Authority approves this docs-only plan.
- Execution Authority opens a separate implementation slice referencing this document.

