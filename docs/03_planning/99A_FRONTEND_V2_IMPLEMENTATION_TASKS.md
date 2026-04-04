# Frontend V2 — Full-Stack Implementation Tasks

> Master task list for the Frontend V2 rebuild + required backend additions.
> Each task follows the 9-phase workflow. Tasks are ordered by dependency.
>
> **Parent plan:** `99_FRONTEND_V2_REBUILD_PLAN.md`

---

## Task Workflow (per task)

```
Phase     │ Role              │ What Happens
──────────┼───────────────────┼──────────────────────────────────────
1. PLAN   │ Architect + PO    │ Define scope, acceptance criteria, deps
2. DESIGN │ Lead              │ API contract / component API / data flow
3. REVIEW │ PO + Lead         │ Review design before coding
4. BUILD  │ Developer         │ Write code (backend then frontend)
5. TEST   │ Developer         │ Run locally, fix bugs, write unit tests
6. REVIEW │ Lead              │ Code review
7. QC     │ QA / PO           │ Test against acceptance criteria
8. SESSION│ Developer         │ Update SESSION_PATCH.md + task status
9. COMMIT │ Developer         │ Git commit + push
```

**Status:** `[ ]` not started · `[P]` plan · `[D]` design · `[B]` build · `[R]` review · `[Q]` QC · `[S]` session · `[✓]` done

**Task types:** `[FE]` frontend only · `[BE]` backend only · `[FS]` full-stack (backend + frontend)

---

## Backend Inventory: What Exists vs What's New

### Existing Services (no changes needed for Phase 1-2 frontend)
```
auth-service         │ Go/Chi   │ 5 tables, 14 routes  │ Login, register, profile
book-service         │ Go/Chi   │ 7 tables, 20+ routes │ Books, chapters, drafts, revisions
sharing-service      │ Go/Chi   │ 1 table, 8 routes    │ Visibility, unlisted access
catalog-service      │ Go/Chi   │ 1 table, 5 routes    │ Public book list
provider-registry    │ Go/Chi   │ 5 tables, 15 routes  │ BYOK providers, user models
usage-billing        │ Go/Chi   │ 5 tables, 7 routes   │ Usage logs, summary, balance
translation-service  │ Python   │ 6 tables, 14 routes  │ Jobs, translations, versions
glossary-service     │ Go/Chi   │ 8 tables, 20+ routes │ Kinds, entities, attributes
chat-service         │ Python   │ 3 tables, 14 routes  │ Sessions, messages, streaming
api-gateway-bff      │ TS/Nest  │ proxy only           │ Routes all traffic
```

### New Backend Work Needed (by phase)
```
Phase 2:  notification tables (auth-service extension)
          import .docx/.epub (book-service extension)
Phase 3:  ratings + reviews (new social-service OR catalog extension)
          comments (new social-service OR catalog extension)
          tags + votes (new social-service)
          wiki (new wiki-service OR glossary extension)
          follow system (auth-service extension)
          reading progress (new table in book-service)
          favorites + library (auth-service or book-service extension)
          genre groups (glossary-service extension)
          content reporting (new moderation table)
Phase 4:  leaderboard aggregation (computed endpoints)
          export .epub/.pdf (book-service extension)
          author analytics (usage-billing extension)
```

---

## Phase 1: Frontend Foundation (FE only — no backend changes)

All existing APIs work as-is. Pure frontend scaffold.

### P1-01: Project Scaffold [FE]
```
Status: [✓]
Deps:   None
Scope:  Create frontend-v2/ — Vite + React 18 + TypeScript
AC:
  - [ ] npm run dev starts on port 5174
  - [ ] TypeScript strict, path aliases (@/ → src/)
```

### P1-02: Tailwind + shadcn/ui + Theme [FE]
```
Status: [✓]
Deps:   P1-01
Scope:  CSS variables from warm literary theme, shadcn init, core components
AC:
  - [ ] CSS variables match design-drafts/components-v2-warm.html
  - [ ] Fonts: Inter, Lora, JetBrains Mono loaded
  - [ ] shadcn components: Button, Input, Label, Dialog, Card, Form, Select, Tabs
```

### P1-03: i18n Framework [FE]
```
Status: [✓]
Deps:   P1-01
Scope:  react-i18next with en/vi/ja/zh-TW, common namespace
AC:
  - [ ] t('key') works, language detection from browser
  - [ ] Only common namespace initially
```

### P1-04: Copy API Layer + Auth [FE]
```
Status: [✓]
Deps:   P1-01
Scope:  Copy api/, auth/, features/ (api+hooks+types), hooks/ from frontend/
AC:
  - [ ] No import errors on build
  - [ ] Auth flow works (login → token → protected routes)
```

### P1-05: Mode Detection [FE]
```
Status: [✓]
Deps:   P1-04
Scope:  ModeProvider context: workbench vs platform
AC:
  - [ ] useMode() returns current mode
  - [ ] Fallback to 'workbench'
```

### P1-06: Router + 3 Layouts [FE]
```
Status: [✓]
Deps:   P1-01, P1-04
Scope:  React Router with all routes, DashboardLayout, EditorLayout, FullBleedLayout
AC:
  - [ ] All routes from plan section 3.3 defined
  - [ ] RequireAuth on protected routes
  - [ ] 404 page
```

### P1-07: Sidebar [FE]
```
Status: [✓]
Deps:   P1-02, P1-03, P1-05, P1-06
Scope:  Nav sidebar (expanded + collapsed), user footer, bell placeholder
AC:
  - [ ] All labels use t()
  - [ ] Active state amber highlight
  - [ ] Platform-only items hidden in workbench mode
  - [ ] Collapsed mode (icon-only) for EditorLayout
```

### P1-08: PageHeader + Breadcrumb [FE]
```
Status: [✓]
Deps:   P1-02, P1-03
Scope:  Reusable header with breadcrumbs, title, action slots, tab variant
AC:
  - [ ] Auto-generates breadcrumb from route
  - [ ] Supports tabs variant
```

### P1-09: LanguageDisplay [FE]
```
Status: [✓]
Deps:   P1-02
Scope:  Language name + code component (compact + stacked)
AC:
  - [ ] "日本語 (ja)" inline, "日本語\n(ja)" stacked
  - [ ] Language code → native name map
```

### P1-10: Auth Pages [FE]
```
Status: [✓]
Deps:   P1-02, P1-03, P1-06
Scope:  Login, Register, Forgot, Reset (all use existing auth-service API)
AC:
  - [ ] Form validation with Zod
  - [ ] All 4 locale files for auth namespace
  - [ ] Loading + error states
```

### P1-11: Language Selector [FE]
```
Status: [✓]
Deps:   P1-03
Scope:  GUI language switcher (button group)
AC:
  - [ ] Saves to localStorage
  - [ ] Page updates without reload
```

---

## Phase 2: Core Screens (mostly FE, some BE extensions)

### P2-01: Shared UI Components [FE]
```
Status: [✓]
Deps:   P1-02
Scope:  StatusBadge, ConfirmDialog, FormDialog, EmptyState, Skeleton,
        CopyButton, FilterToolbar, Pagination
AC:
  - [ ] All 8 components built with design system tokens
  - [ ] Storybook-style test page (optional)
```

### P2-02: BooksPage [FE]
```
Status: [✓]
Deps:   P2-01, P1-07, P1-08
Scope:  Book list + search + filter + create dialog (uses existing booksApi)
AC:
  - [ ] Cover thumbnails, serif titles, translation dots
  - [ ] "New Book" → FormDialog
  - [ ] Empty state, loading skeleton, pagination
```

### P2-03: BookDetailPage Shell [FE]
```
Status: [✓]
Deps:   P2-02
Scope:  Tabs: Chapters, Translation, Glossary, Sharing, Settings (stubs)
AC:
  - [ ] Breadcrumb: Workspace > Book Title
  - [ ] Tab routing to nested URLs
```

### P2-04: Chapters Tab [FE]
```
Status: [✓]
Deps:   P2-03
Scope:  DataTable with chapters, create dialog (uses existing booksApi)
AC:
  - [ ] Checkboxes, row actions (edit, download, trash with confirm)
  - [ ] Translation dot indicators
```

### P2-05: Chapter Editor — Workbench [FE]
```
Status: [✓]
Deps:   P2-04
Sub-tasks (break into 4 tickets):

  P2-05a: Editor Core [FE]
    Scope: Center panel — Lexical chunk editor with line numbers
    AC:
      - [ ] Chunk-based paragraphs, numbered
      - [ ] Content editable, tracks dirty state
      - [ ] Save with version tracking (uses existing booksApi.patchDraft)

  P2-05b: Panel System [FE]
    Scope: Left + Right panels with tabs, resize, toggle
    AC:
      - [ ] Resize drag handles
      - [ ] Ctrl+B / Ctrl+J toggle
      - [ ] State persisted to localStorage

  P2-05c: Chunk Actions [FE]
    Scope: Per-chunk translate, send-to-AI, copy, selection
    AC:
      - [ ] Hover actions appear
      - [ ] Click/Shift+click selection
      - [ ] Bottom bar shows selection count + batch actions

  P2-05d: Revision History Panel [FE]
    Scope: Right panel "History" tab (uses existing booksApi.listRevisions)
    AC:
      - [ ] Revision list with timestamps + messages
      - [ ] Preview revision content
      - [ ] Restore button with confirm
```

### P2-06: Split-View Translation [FE]
```
Status: [ ] (deferred — needs translation API wired first, moved to P3)
Deps:   P2-05a
Scope:  Source + translation side-by-side, accept/reject per chunk
AC:
  - [ ] Chunk-aligned rows
  - [ ] Accept/Reject/Edit per chunk
  - [ ] Keyboard navigation
  - [ ] Progress badge "4/6 accepted"
```

### P2-07: Reading Mode [FE]
```
Status: [✓]
Deps:   P1-06
Scope:  Clean reader, chapter nav, TOC (uses existing booksApi)
AC:
  - [ ] Minimal chrome, progress bar
  - [ ] TOC sidebar with chapter list
  - [ ] Prev/Next chapter buttons
  - [ ] Language selector (switch between translations)
```

### P2-08: Reader Theme System [FE]
```
Status: [✓]
Deps:   P1-02
Scope:  ReaderThemeProvider, 6 presets, customizer panel
AC:
  - [ ] CSS variables scoped to .reader-content
  - [ ] Quick-toggle dropdown + full settings panel
  - [ ] Saved to localStorage (API persistence later)
```

### P2-09: Notification System — Frontend Shell [FE]
```
Status: [✓]
Deps:   P1-07
Scope:  Bell icon + notification center (mock data for now)
AC:
  - [ ] Bell with badge (3 states)
  - [ ] Dropdown with filter tabs
  - [ ] Notification items with icons + time
  - [ ] Mock data — real API in P2-09b
```

### P2-09b: Notification System — Backend [BE]
```
Status: [ ]
Deps:   P2-09 (frontend shell helps define API contract)
Scope:  Add notifications to auth-service (or new notification-service)

New DB tables (in loreweave_auth or new loreweave_notifications):
  - user_notifications (id, user_id, type, title, body, metadata jsonb,
                        read_at, created_at)
  - notification_preferences (user_id, event_type, email_enabled, in_app_enabled)

New endpoints:
  - GET    /v1/notifications?unread=true&type=translation&limit=20&offset=0
  - PATCH  /v1/notifications/{id}/read
  - POST   /v1/notifications/mark-all-read
  - GET    /v1/notifications/preferences
  - PATCH  /v1/notifications/preferences

Backend event producers (emit notifications):
  - translation-service: job_completed, job_failed
  - chat-service: (future) message received
  - social-service: (Phase 3) comment, review, follow, tag, wiki PR

AC:
  - [ ] DB migration creates tables
  - [ ] CRUD endpoints working
  - [ ] Mark read / mark all read
  - [ ] Preferences per event type
  - [ ] Gateway proxy configured
```

### P2-09c: Notification System — Integration [FS]
```
Status: [ ]
Deps:   P2-09, P2-09b
Scope:  Wire frontend to real API, add translation event producers
AC:
  - [ ] Frontend fetches real notifications
  - [ ] Unread count updates on new notifications
  - [ ] translation-service emits notifications on job complete/fail
  - [ ] WebSocket or polling for real-time updates
```

### P2-10: Onboarding Wizard [FE]
```
Status: [✓]
Deps:   P2-02
Scope:  3-step first-time guide
AC:
  - [ ] Detects first login
  - [ ] Steps: Welcome → Configure AI → Create Book
  - [ ] Skip button, progress dots
```

### P2-11a: Import — Frontend [FE]
```
Status: [✓]
Deps:   P2-02
Scope:  Upload dialog with format detection, chapter preview
AC:
  - [ ] Supports .txt, .docx, .epub
  - [ ] Shows detected chapters before import
  - [ ] Progress indicator
```

### P2-11b: Import — Backend [BE]
```
Status: [ ]
Deps:   None (can start independently)
Scope:  Extend book-service to accept .docx/.epub upload

New endpoint:
  - POST /v1/books/{book_id}/chapters/import  (multipart: file + format hint)
    Response: { chapters_detected: [...], import_id: "..." }
  - POST /v1/books/{book_id}/chapters/import/{import_id}/confirm
    Creates all detected chapters

Dependencies: Go library for .docx parsing (e.g., unidoc) and .epub parsing

AC:
  - [ ] .docx: extract text, split by headings into chapters
  - [ ] .epub: extract XHTML content, split by spine items
  - [ ] .txt: split by blank line or markdown headings
  - [ ] Preview endpoint (don't create until confirmed)
  - [ ] Error handling for corrupt/unsupported files
```

---

## Phase 3: Feature Screens + Community Backend

### GUI Review Pass (all existing components)
```
P3-R1: GUI Review — compare all components against design drafts, fix inconsistencies

Review scope (65 files, ~6,800 lines):

LAYOUTS (3):
  - DashboardLayout.tsx (15 lines)
  - EditorLayout.tsx (153 lines)
  - FullBleedLayout.tsx (9 lines)

AUTH PAGES (5):
  - AuthCard.tsx (25 lines)
  - LoginPage.tsx (103 lines)
  - RegisterPage.tsx (110 lines)
  - ForgotPage.tsx (82 lines)
  - ResetPage.tsx (98 lines)

SHARED COMPONENTS (12):
  - Sidebar.tsx (219 lines)
  - PageHeader.tsx (84 lines)
  - ConfirmDialog.tsx (111 lines)
  - FormDialog.tsx (45 lines)
  - EmptyState.tsx (23 lines)
  - Skeleton.tsx (33 lines)
  - StatusBadge.tsx (54 lines)
  - CopyButton.tsx (33 lines)
  - FilterToolbar.tsx (59 lines)
  - Pagination.tsx (80 lines)
  - LanguageDisplay.tsx (28 lines)
  - LanguageSelector.tsx (33 lines)
  - UnsavedChangesDialog.tsx (28 lines)
  - ChapterReadView.tsx (42 lines)

CORE PAGES (6):
  - HomePage.tsx (14 lines)
  - BooksPage.tsx (235 lines)
  - BookDetailPage.tsx (168 lines)
  - ChapterEditorPage.tsx (546 lines)
  - ReaderPage.tsx (141 lines)
  - PlaceholderPage.tsx (27 lines)

EDITOR COMPONENTS (7):
  - TiptapEditor.tsx (125 lines)
  - FormatToolbar.tsx (165 lines)
  - SlashMenu.tsx (237 lines)
  - CalloutNode.tsx (83 lines)
  - RevisionHistory.tsx (180 lines)
  - ChunkItem.tsx (140 lines) — dead code? replaced by Tiptap
  - ChunkInsertRow.tsx (24 lines) — dead code? replaced by Tiptap

BOOK TAB COMPONENTS (6):
  - ChaptersTab.tsx (313 lines)
  - TranslationTab.tsx (285 lines)
  - TranslateModal.tsx (195 lines)
  - GlossaryTab.tsx (317 lines)
  - KindEditor.tsx (430 lines)
  - EntityEditor.tsx (325 lines)

OTHER (6):
  - ImportDialog.tsx (108 lines)
  - NotificationBell.tsx (90 lines) — mock data
  - OnboardingWizard.tsx (86 lines) — not wired
  - DataTable.tsx (59 lines)
  - EditorDirtyContext.tsx (55 lines)
  - ModeProvider.tsx (23 lines) — unused

PROVIDERS (2):
  - ReaderThemeProvider.tsx (83 lines)
  - SidebarProvider.tsx (38 lines)

Design drafts to compare against:
  - design-drafts/components-v2-warm.html (component catalog)
  - design-drafts/screen-glossary-management.html (kind/entity editor)
  - design-drafts/screen-translation-matrix.html (translation tab)
  - design-drafts/screen-chapter-editor.html (editor)
  - design-drafts/screen-editor-workbench.html (3-panel)
  - design-drafts/screen-chat.html (chat)
  - design-drafts/screen-reader.html (reader)
  - design-drafts/screen-settings.html (settings)
  - design-drafts/screen-browse-catalog.html (catalog)

Review checklist per component:
  [ ] Matches design draft visually
  [ ] Loading state exists
  [ ] Empty state exists
  [ ] Error state exists
  [ ] Responsive (doesn't break on narrow screens)
  [ ] Keyboard accessible (Tab, Enter, Esc where relevant)
  [ ] Dead code identified and marked for removal
  [ ] Unused imports cleaned

Deferred polish items (tracked here so they don't get lost):
  [✓] P3-R1-D1: Editor panel drag-to-resize handles — MOVED to E4-01 (image block resize handles)
  [ ] P3-R1-D2: Dead code cleanup — ChunkItem.tsx + ChunkInsertRow.tsx (replaced by Tiptap)
  [ ] P3-R1-D3: Wire OnboardingWizard into App (exists but not rendered)
  [ ] P3-R1-D4: Wire NotificationBell with real data (currently mock)
  [ ] P3-R1-D5: Remove or repurpose ModeProvider (currently unused)

Deferred glossary items — PROMOTED to P3-09 Kind Editor Enhancement (full-stack, BE-first):
  See P3-09 section below for detailed task breakdown.

  Covered by Genre Groups (FE-G3..G5) — already done:
  [✓] P3-R1-D11: Genre badge on attributes → FE-G4 (genre tag pills on attr rows)
  [✓] P3-R1-D12: Genre badge in entity editor header → FE-G5 (genre indicator)
  [—] P3-R1-D13: Attribute deactivation per genre → DROPPED (tag-based filtering replaces matrix deactivation)

Deferred reader items:
  [ ] P3-R1-D14: Reader theme toggle button — wire ReaderThemeProvider to top bar [FE]
  [ ] P3-R1-D15: Reader font size control — theme customizer panel [FE]
  [ ] P3-R1-D16: TOC language selector — read translated versions (needs translation workbench) [FE+BE]
```

### Translation (FE — uses existing translation-service)
```
P3-01: Translation Matrix Tab [FE]                    [✓] Done (session 14)
P3-02: Translate Modal (AI batch) [FE]                [✓] Done (session 14)
P3-03: Jobs Drawer [FE]                               [ ] (deferred — after workbench)
P3-04: Translation Settings Drawer [FE]               [ ] (deferred — after workbench)
```

### Translation Workbench (BLOCKED — needs media blocks from Phase 3.5)
```
Design draft: design-drafts/screen-translation-workbench.html

Architecture: Block-level translation, not chapter-level.
  - A translation IS a chapter version in a different language
  - Source blocks (read-only) linked 1:1 with translation blocks (editable)
  - Each block type has its own translation UX:
    · text (p, h, list, quote): manual textarea or AI suggest
    · image: attach/paste/AI regenerate with translated prompt
    · video: re-attach or AI regenerate
    · audio/TTS: auto-regenerate from translated text
    · code: copy as-is (editable)
    · callout (author note): skip by default, opt-in translate
    · divider: no translation needed

Requires:
  - Phase 3.5 media blocks (image, video, audio, code in editor)
  - New backend: block_translations table + CRUD endpoints
  - Translation-service extension: per-block AI translation

Tasks (to be broken down when unblocked):
  P3-T1: block_translations table + migration [BE]
  P3-T2: Block translation CRUD endpoints [BE]
  P3-T3: Translation Workbench page [FE]
  P3-T4: Per-block AI suggest integration [FS]
  P3-T5: Media block translation UX (attach, regenerate) [FE]
  P3-T6: AI Assist All (bulk fill empty blocks) [FS]
  P3-T7: Keyboard navigation (Tab/Shift+Tab/Ctrl+Enter) [FE]
  P3-T8: Glossary lookup in workbench (highlight known terms) [FE]
```

### Glossary (mostly FE — uses existing glossary-service)
```
P3-05: Glossary Tab [FE]
P3-06: Kind Editor [FE]
P3-07: Entity Editor [FE]
```

### Glossary — Genre Groups (tag-based, backend-first)

Design approach: tag-based genre scoping (NO activation matrix).
  - genre_groups table = available genre definitions per book (name, color, description)
  - kind.genre_tags[] = kind appears in entity forms when book has matching genre (empty/universal = always)
  - attr_def.genre_tags[] = attribute shows when book has matching genre (empty = always)
  - book.genre_tags[] = user-selected genres for the book
  - Entity form filters kinds/attrs by intersection of book.genre_tags with kind/attr genre_tags.

Design drafts:
  - design-drafts/screen-glossary-management.html (Sections 1-3: kind editor, genre overview, entity editor)
  - design-drafts/screen-genre-groups.html (genre modal, book settings, browse filter)

Existing backend state:
  - entity_kinds.genre_tags TEXT[] — already exists, CRUD wired, seed data has values
  - attribute_definitions.genre_tags — MISSING (needs migration + CRUD update)
  - books.genre_tags — MISSING (needs migration + CRUD update)
  - genre_groups table — MISSING (needs new table + CRUD)
  - catalog-service genre filter — MISSING

```
--- BACKEND PHASE (all done before FE starts) ---

BE-G1: Genre Groups table + CRUD [BE] (glossary-service)
  Migration: CREATE TABLE genre_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    book_id UUID NOT NULL,
    name TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT '#8b5cf6',
    description TEXT NOT NULL DEFAULT '',
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
  ) + UNIQUE(book_id, name)
  Endpoints (scoped under existing /v1/glossary prefix):
    - GET    /v1/glossary/books/{book_id}/genres       → list genres for a book
    - POST   /v1/glossary/books/{book_id}/genres       → create genre
    - PATCH  /v1/glossary/books/{book_id}/genres/{id}  → update name/color/description/sort_order
    - DELETE /v1/glossary/books/{book_id}/genres/{id}  → delete genre
  AC:
    - [ ] Table created with migration
    - [ ] CRUD endpoints work with auth
    - [ ] Unique constraint on (book_id, name)

BE-G2: Attribute genre_tags column [BE] (glossary-service)
  Migration: ALTER TABLE attribute_definitions ADD COLUMN IF NOT EXISTS genre_tags TEXT[] NOT NULL DEFAULT '{}'
  Update: createAttrDef, patchAttrDef, getKinds — accept/return genre_tags on attribute_definitions
  AC:
    - [ ] Column added
    - [ ] POST /v1/glossary/kinds/{kind_id}/attributes accepts genre_tags
    - [ ] PATCH /v1/glossary/kinds/{kind_id}/attributes/{id} accepts genre_tags
    - [ ] GET /v1/glossary/kinds returns genre_tags on each attribute_definition

BE-G3: Book genre_tags column [BE] (book-service)
  Migration: ALTER TABLE books ADD COLUMN IF NOT EXISTS genre_tags TEXT[] NOT NULL DEFAULT '{}'
  Update: createBook, patchBook, getBook — accept/return genre_tags
  AC:
    - [ ] Column added
    - [ ] POST /v1/books accepts genre_tags
    - [ ] PATCH /v1/books/{id} accepts genre_tags
    - [ ] GET /v1/books/{id} returns genre_tags

BE-G4: Catalog genre filter [BE] (catalog-service)
  Update: listPublicBooks — accept `genre` query param, filter by genre_tags array overlap
  Update: bookProjection — include genre_tags field
  AC:
    - [ ] GET /v1/catalog/books?genre=Fantasy filters correctly (array overlap)
    - [ ] Book projection includes genre_tags in response
    - [ ] Multiple genre params supported (OR logic)

BE-G5: Integration tests [BE] (infra/)
  New: infra/test-genre-groups.sh
  AC:
    - [ ] Genre CRUD (create, list, update, delete, duplicate name rejected)
    - [ ] Attr genre_tags (create with tags, patch tags, verify in GET)
    - [ ] Book genre_tags (patch, verify in GET)
    - [ ] Catalog genre filter (filter by genre, verify results)
    - [ ] All tests pass

--- FRONTEND PHASE (all BE endpoints ready, zero blockers) ---

FE-G1: Types + API client [FE]
  Update: glossary/types.ts — add GenreGroup type, genre_tags on AttributeDefinition
  Update: glossary/api.ts — add genre CRUD methods
  Update: books/api.ts — add genre_tags to Book type
  AC:
    - [ ] All new types defined
    - [ ] All API methods callable

FE-G2: Genre Groups tab + CRUD [FE]
  New: Genre Groups tab in GlossaryTab (3rd tab: Entities | Kinds & Attributes | Genre Groups)
  New: Genre list panel (left) + detail/overview panel (right)
  New: GenreCreateEditModal (name, color picker, description)
  AC:
    - [ ] Tab navigation works
    - [ ] Genre list shows all genres with color dot, counts
    - [ ] Create/Edit/Delete genre works
    - [ ] Detail panel shows tagged kinds + attributes summary

FE-G3: Kind Editor genre_tags [FE]
  Update: KindEditor.tsx — add genre_tags row below kind metadata
  Genre tag pills with "Add" dropdown (pick from book's genre_groups)
  AC:
    - [ ] Genre tags displayed on kind detail panel
    - [ ] Add/remove genre tags, saves via PATCH

FE-G4: Attribute genre_tags [FE]
  Update: KindEditor.tsx — genre tag pills on attribute rows
  Update: Add Attribute form — optional genre_tags multi-select
  AC:
    - [ ] Genre pills shown on attr rows (colored, per genre)
    - [ ] Create attr with genre_tags
    - [ ] Edit attr genre_tags

FE-G5: Entity Editor genre filter [FE]
  Update: EntityEditorModal.tsx — genre indicator in header (from kind.genre_tags)
  Update: AttrGrid — hide attributes whose genre_tags don't match book.genre_tags
  AC:
    - [ ] Genre badge shown in entity editor header
    - [ ] Attributes filtered: genre-scoped attrs hidden if book doesn't have that genre
    - [ ] Non-genre attrs (empty genre_tags) always shown

FE-G6: Book SettingsTab with genre selector [FE]
  New: book-tabs/SettingsTab.tsx (replaces placeholder in BookDetailPage)
  Includes: title, description, language, summary, cover image, genre selector, visibility
  Genre selector: multi-select dropdown with checkboxes, selected as colored pills
  AC:
    - [ ] Full settings tab implemented (P3-21 + genre selector)
    - [ ] Genre selector lists genres from glossary-service
    - [ ] Selected genres saved to book.genre_tags via PATCH

FE-G7: Browse genre filter [FE]
  Update: FilterBar.tsx — replace disabled dashed chips with enabled genre chips
  Update: BrowsePage — wire genre param to catalog API
  AC:
    - [ ] Genre chips loaded from available genres
    - [ ] Click to filter, active state with genre color
    - [ ] Book cards show genre tags on cover
```

Deferred items resolved:
  [x] P3-R1-D11: Genre badge on attributes → covered by FE-G4
  [x] P3-R1-D12: Genre badge in entity editor header → covered by FE-G5
  [—] P3-R1-D13: Attribute deactivation per genre → DROPPED (no matrix, tag-based instead)
  [→] P3-R1-D6..D22 (Kind Editor gaps) → PROMOTED to P3-KE Kind Editor Enhancement section

### Kind Editor Enhancement (full-stack, BE-first)

Design reference: `design-drafts/screen-glossary-management.html` (Section 1: Kind Editor)

Scope: Close the gap between the design draft and the current KindEditor implementation.
Strategy: All backend tasks first (BE-KE-01..06), then all frontend tasks (FE-KE-01..07).
Service: glossary-service (Go/Chi)

Existing DB state (already in schema):
  - `entity_kinds.description TEXT` — column EXISTS but not exposed in API or FE
  - `attribute_definitions.description TEXT` — column EXISTS but not exposed in API or FE
  - `attribute_definitions.is_system BOOLEAN` — EXISTS
  - `entity_kinds.is_default BOOLEAN` — EXISTS
  - `entity_kinds.sort_order INT` — EXISTS
  - `attribute_definitions.sort_order INT` — EXISTS

Missing DB columns:
  - `attribute_definitions.is_active BOOLEAN NOT NULL DEFAULT true` — toggle on/off without deleting

```
── Backend Tasks (BE-KE-01..06) ──────────────────────────────────────────────

BE-KE-01: Kind description field — expose in API [BE]
  Status: [✓] Done (b2f60d4, 67879aa — 24/24 tests)
  DB: column `entity_kinds.description` already exists
  Changes:
    - listKinds: include `description` in SELECT + response JSON
    - patchKind: accept `description` in PATCH body, persist to DB
    - Domain type: add Description field to EntityKind struct
  AC:
    - [ ] GET /v1/glossary/kinds returns description field (null if empty)
    - [ ] PATCH /v1/glossary/kinds/:id accepts description, persists correctly
    - [ ] Existing kinds with NULL description work without error

BE-KE-02: Entity count per kind [BE]
  Status: [✓] Done (731ab9d — 32/32 tests)
  DB: no schema change — aggregate query from glossary_entities
  Changes:
    - listKinds: add subquery `SELECT count(*) FROM glossary_entities WHERE kind_id = ek.kind_id AND deleted_at IS NULL` as entity_count
    - Domain type: add EntityCount field
  AC:
    - [ ] GET /v1/glossary/kinds returns entity_count per kind
    - [ ] Count excludes soft-deleted entities
    - [ ] Kinds with 0 entities return entity_count: 0

BE-KE-03: Attribute is_active toggle [BE]
  Status: [✓] Done (2a76891 — 42/42 tests)
  DB: ALTER TABLE attribute_definitions ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true
  Changes:
    - migrate.go: add migration SQL
    - listKinds: include is_active in attr response
    - patchAttrDef: accept is_active in PATCH body
    - Entity detail: optionally filter inactive attrs (or let FE decide)
  AC:
    - [ ] Migration adds is_active column (idempotent)
    - [ ] GET /v1/glossary/kinds returns is_active per attribute
    - [ ] PATCH /v1/glossary/kinds/:kindId/attributes/:attrId accepts is_active toggle
    - [ ] Existing attributes default to is_active=true

BE-KE-04: Attribute inline edit — PATCH name, field_type, is_required, options [BE]
  Status: [✓] Done (3da6932 — 60/60 tests)
  DB: no schema change — fields already exist
  Changes:
    - patchAttrDef: extend to accept name, field_type, is_required, options (currently only genre_tags)
    - Validation: field_type must be one of known types, name non-empty
  AC:
    - [ ] PATCH /v1/glossary/kinds/:kindId/attributes/:attrId accepts name, field_type, is_required
    - [ ] Invalid field_type returns 400
    - [ ] System attributes (is_system=true) can still be edited (name customization)

BE-KE-05: Attribute description — expose in API [BE]
  Status: [✓] Done — covered by BE-KE-01 (same commit exposed description on both kinds and attrs)
  DB: column `attribute_definitions.description` already exists
  Changes:
    - listKinds: include attr description in response
    - patchAttrDef: accept description in PATCH body
    - createAttrDef: accept description in POST body
  AC:
    - [ ] GET /v1/glossary/kinds returns description per attribute
    - [ ] PATCH/POST accept description field

BE-KE-06: Sort order PATCH endpoints [BE]
  Status: [ ]
  DB: sort_order columns already exist on both tables
  Changes:
    - New endpoint: PATCH /v1/glossary/kinds/reorder — accepts { kind_ids: string[] } ordered array
    - New endpoint: PATCH /v1/glossary/kinds/:kindId/attributes/reorder — accepts { attr_def_ids: string[] }
    - Both endpoints update sort_order = array index for each ID
  AC:
    - [ ] PATCH /v1/glossary/kinds/reorder updates sort_order for all provided kind IDs
    - [ ] PATCH /v1/glossary/kinds/:kindId/attributes/reorder updates attr sort_order
    - [ ] Missing IDs in array are left at their current sort_order
    - [ ] Returns 400 if any ID doesn't exist

── Frontend Tasks (FE-KE-01..07) — start after all BE-KE done ───────────────

FE-KE-01: Kind metadata panel [FE]
  Status: [ ]
  Update: KindEditor.tsx — add Description field to edit form, show entity count in detail header
  AC:
    - [ ] Description textarea in kind edit form (editable, saves via PATCH)
    - [ ] Entity count shown in kind detail header (e.g. "12 attributes · 45 entities")
    - [ ] Kind metadata row: Display Name, Internal ID, Entity count, Description

FE-KE-02: Attribute inline edit modal [FE]
  Status: [ ]
  Update: KindEditor.tsx — pencil icon per attribute row → opens edit popover/inline form
  Fields: name, field_type (dropdown), is_required (checkbox), description (textarea), genre_tags
  AC:
    - [ ] Pencil icon on each attribute row (hover reveal, like delete icon)
    - [ ] Click opens inline edit form or small modal
    - [ ] Save PATCHes the attribute, reloads kind
    - [ ] System attributes editable (name customization allowed)

FE-KE-03: Attribute toggle on/off [FE]
  Status: [ ]
  Update: KindEditor.tsx — toggle switch per attribute row (uses is_active from BE-KE-03)
  AC:
    - [ ] Toggle switch shown per attribute (green=active, muted=inactive)
    - [ ] Toggle sends PATCH with is_active: true/false
    - [ ] Inactive attributes shown with reduced opacity + strikethrough name
    - [ ] Entity editor filters out is_active=false attributes

FE-KE-04: Drag-to-reorder kinds [FE]
  Status: [ ]
  Update: KindEditor.tsx — drag handles on kind list items
  Library: @dnd-kit/core + @dnd-kit/sortable (or similar)
  AC:
    - [ ] Drag handles visible on kind list rows (grip dots icon)
    - [ ] Drag-and-drop reorders within System/User sections
    - [ ] On drop, calls PATCH /v1/glossary/kinds/reorder with new order
    - [ ] Optimistic UI update, revert on error

FE-KE-05: Drag-to-reorder attributes [FE]
  Status: [ ]
  Update: KindEditor.tsx — drag handles on attribute rows
  AC:
    - [ ] Drag handles on attribute rows (within System/User sections)
    - [ ] On drop, calls PATCH /v1/glossary/kinds/:kindId/attributes/reorder
    - [ ] Optimistic UI update

FE-KE-06: Genre-colored dots on tag pills [FE]
  Status: [ ]
  Update: KindEditor.tsx, AttrRow — genre tag pills show colored dot matching genre_group color
  Requires: fetch genre_groups for the current book to get color mapping
  AC:
    - [ ] Genre tag pills show small colored square/dot before genre name
    - [ ] Color sourced from genre_groups API (fallback: default violet)

FE-KE-07: Modified indicator + Revert to default [FE] ⚠️ STRETCH
  Status: [ ]
  Note: This is a stretch goal — requires comparing current kind/attr state vs seed defaults.
  Approach: Store seed defaults as a JSON constant in frontend, diff at render time.
  AC:
    - [ ] "modified" badge on system kinds/attrs that differ from seed defaults
    - [ ] "Revert to Default" button per kind (resets name, icon, color, attrs to seed)
    - [ ] Confirm dialog before revert
```

### Social Service — New Backend (required for community features)
```
P3-09: Social Service — Scaffold [BE]
  Scope: New Go/Chi service: social-service
  New DB: loreweave_social
  Tables:
    - book_ratings (id, book_id, user_id, score 1-5, created_at, updated_at)
    - book_reviews (id, book_id, user_id, rating_id, title, body, helpful_count, created_at)
    - review_helpful_votes (review_id, user_id)
    - chapter_comments (id, chapter_id, user_id, body, parent_comment_id, like_count, created_at)
    - comment_likes (comment_id, user_id)
    - book_tags (id, book_id, tag_name, created_by, agree_count, disagree_count)
    - tag_votes (tag_id, user_id, vote: agree/disagree)
    - user_favorites (user_id, book_id, created_at)
    - reading_lists (id, user_id, name, created_at)
    - reading_list_items (list_id, book_id, sort_order)
    - reading_progress (user_id, book_id, chapter_id, progress_pct, last_read_at)
    - content_reports (id, reporter_id, target_type, target_id, reason, status, created_at)
  Endpoints:
    Ratings:     POST/GET/PATCH /v1/books/{id}/rating
    Reviews:     CRUD /v1/books/{id}/reviews, POST /v1/reviews/{id}/helpful
    Comments:    CRUD /v1/chapters/{id}/comments, POST /v1/comments/{id}/like
    Tags:        POST /v1/books/{id}/tags, POST /v1/tags/{id}/vote
    Favorites:   POST/DELETE /v1/books/{id}/favorite, GET /v1/me/favorites
    Library:     CRUD /v1/me/reading-lists
    Progress:    PUT/GET /v1/books/{id}/reading-progress
    Reports:     POST /v1/reports, GET /v1/me/moderation-queue
  AC:
    - [ ] DB migration, all tables created
    - [ ] All endpoints with auth middleware
    - [ ] Gateway proxy routes configured
    - [ ] Unit tests for each endpoint group

P3-10: Ratings + Reviews — Frontend [FE]
  Deps: P3-09
  AC:
    - [ ] Star rating on book detail
    - [ ] Rating distribution chart
    - [ ] Review list with helpful votes
    - [ ] "Write a Review" dialog

P3-11: Chapter Comments — Frontend [FE]
  Deps: P3-09
  AC:
    - [ ] Comment list below reader
    - [ ] Reply threading (1 level)
    - [ ] Like button
    - [ ] Spoiler tag support
    - [ ] Report button

P3-12: Community Tags — Frontend [FE]
  Deps: P3-09
  AC:
    - [ ] Tag pills with vote percentages
    - [ ] Vote buttons (agree/disagree)
    - [ ] "Suggest Tag" form
    - [ ] Color-coded by confidence

P3-13: Favorites + Library — Frontend [FE]
  Deps: P3-09
  AC:
    - [ ] "Add to Favorites" heart button on book detail
    - [ ] "My Library" page with tabs (Favorites, Reading, History, Lists)
    - [ ] Reading progress bars per book
    - [ ] Custom reading list CRUD

P3-14: Reading Progress — Backend + Frontend [FS]
  Deps: P3-09 (tables), P2-07 (reader)
  AC:
    - [ ] Reader auto-saves progress on scroll/chapter change
    - [ ] Resume from last position on return
    - [ ] Progress shown in library + book cards
```

### Follow System + User Profiles
```
P3-15a: Follow System — Backend [BE]
  Scope: Extend auth-service
  New tables (in loreweave_auth):
    - user_follows (follower_id, followed_id, created_at)
    - user_public_profiles (user_id, display_name, bio, languages, avatar_url)
  New endpoints:
    - POST/DELETE /v1/users/{id}/follow
    - GET /v1/users/{id}/followers
    - GET /v1/users/{id}/following
    - GET /v1/users/{id}/profile (public)
    - PATCH /v1/account/public-profile
  AC:
    - [ ] Follow/unfollow with duplicate prevention
    - [ ] Follower/following counts
    - [ ] Public profile endpoint (no auth required)

P3-15b: User Profile Page — Frontend [FE]
  Deps: P3-15a
  AC:
    - [ ] Public profile: avatar, bio, stats, achievements
    - [ ] Tabs: Books, Translations, Wiki contributions, Reviews
    - [ ] Follow/unfollow button
    - [ ] Matches screen-user-profile.html design

P3-16: Content Reporting + Moderation Queue [FS]
  Deps: P3-09 (reports table), P3-10/P3-11 (content to report)
  AC:
    - [ ] Report button on comments, reviews, wiki edits
    - [ ] Moderation queue for book owners (their content only)
    - [ ] Accept/reject/delete reported content
```

### Wiki System
```
P3-17a: Wiki — Backend [BE]
  Scope: New wiki-service OR extend glossary-service
  New DB tables:
    - wiki_articles (id, book_id, entity_id nullable, title, slug, body_markdown,
                     source: 'author'|'community'|'ai', created_by, created_at, updated_at)
    - wiki_revisions (id, article_id, body_markdown, edit_summary, created_by, created_at)
    - wiki_suggestions (id, article_id nullable, book_id, suggested_by, title, body_diff,
                        reason, status: pending|accepted|rejected, reviewed_by, reviewed_at)
    - wiki_settings (book_id, wiki_visible, community_editing: off|suggest|open,
                     ai_assist_for_readers, glossary_exposure: names|partial|full,
                     auto_generate_from_glossary)
  Endpoints:
    - GET    /v1/books/{id}/wiki/articles
    - GET    /v1/books/{id}/wiki/articles/{slug}
    - POST   /v1/books/{id}/wiki/articles
    - PATCH  /v1/books/{id}/wiki/articles/{slug}
    - GET    /v1/books/{id}/wiki/articles/{slug}/revisions
    - POST   /v1/books/{id}/wiki/suggestions
    - GET    /v1/books/{id}/wiki/suggestions?status=pending
    - PATCH  /v1/books/{id}/wiki/suggestions/{id} (accept/reject)
    - GET    /v1/books/{id}/wiki/settings
    - PATCH  /v1/books/{id}/wiki/settings
  AC:
    - [ ] Article CRUD with markdown body
    - [ ] Revision history per article
    - [ ] Suggestion (PR) submit + review workflow
    - [ ] Settings per book
    - [ ] Auto-generate article stubs from glossary entities

P3-17b: Wiki Reader — Frontend [FE]
  Deps: P3-17a
  AC: [ ] 3-panel layout (sidebar, article, TOC), wiki links, infobox

P3-17c: Wiki Editor — Frontend [FE]
  Deps: P3-17a
  AC: [ ] Toolbar, [[wiki links]], AI assist, glossary insert

P3-17d: Wiki Settings + PR Review — Frontend [FE]
  Deps: P3-17a
  AC: [ ] Writer controls, pending suggestions queue, diff view

P3-17e: Wiki AI Assist + Cost Warning [FS]
  Deps: P3-17c, chat-service (for AI generation)
  AC: [ ] AI generate/improve, cost warning dialog, "Using YOUR API keys" for readers
```

### Chat + Other
```
P3-18: Chat Page [FE] (uses existing chat-service)          [✓] Done (session 15)
  Full-bleed layout, custom SSE streaming, session CRUD, model selector
  Dropped @ai-sdk/react — custom useChatMessages hook
  Integration test: 25/25 pass (infra/test-chat.sh)

P3-19: Chat Context Integration [FE]                       [✓] Done (session 15)
  Context picker (Books/Chapters/Glossary tabs), book+kind filters for glossary,
  context pills above input, resolve+prepend on send, context pills on messages,
  "Send to Chat" CustomEvent bridge for editor integration.
  Design draft: design-drafts/screen-chat-context.html

P3-20: Sharing Tab [FE] (uses existing sharing-service)     [✓] Done (session 15)
  Card-based visibility selector, unlisted URL copy, token rotation
  Integration test: 19/19 pass (infra/test-sharing.sh)

P3-21: Book Settings Tab [FE]                               [✓] Done (session 15)
  Metadata form (title, desc, lang, summary), cover upload/replace/delete

P3-22: Recycle Bin [FE] (uses existing booksApi)            [✓] Done (session 15)
  Universal design: TrashCard + FloatingTrashBar + category tabs
  Current tabs: Books, Glossary. Chapters tab ready to add (BE exists).
  Design draft: design-drafts/screen-recycle-bin.html

P3-22a: Recycle Bin — Chapters Tab [FE]                     [✓] Done (session 15)
  Unified restoreItem/purgeItem, chapterToTrashItem normalizer, teal icon

P3-22b: Recycle Bin — Chat Sessions Tab [FE]                [✓] Done (session 15)
  chatSessionToTrashItem normalizer, blue icon, restore=PATCH active, purge=DELETE

P3-22c: Recycle Bin — Translations Tab [FS]                 [ ] (future — after Translation Workbench)
  BE: needs trash lifecycle on chapter_translations table (soft delete + restore + purge)
  FE: add translation normalizer + tab
  Deps: P3-22, Translation Workbench (P3-T1..T8)

P3-22d: Recycle Bin — Wiki Pages Tab [FS]                   [ ] (future — after Wiki backend)
  BE: needs trash lifecycle on wiki_pages table
  FE: add wiki normalizer + tab
  Deps: P3-22, P3-17a (Wiki backend)
```

---

## Phase 4: Secondary Screens + Growth

```
P4-01: Settings — Account Tab [FE]
P4-02: Settings — Model Providers [FE] (uses existing provider-registry)
P4-03: Settings — Translation Defaults [FE] (uses existing translation-service prefs)
P4-04: Settings — Reading & Theme Unification [FS] ⚠️ BIG REFACTOR
  Deps: P2-08 (ReaderThemeProvider), MIG-05 (ReadingTab)
  NOTE: This is a significant refactoring task. ReadingTab in Settings
        currently uses standalone localStorage (font size, spacing, 3
        themes, 3 fonts). ReaderThemeProvider has 6 presets with CSS
        variables scoped to .reader-content. These must be unified.
        Design draft: screen-theme-customizer.html (detailed design).

  Sub-tasks:
    - [ ] P4-04a: BE — reading_preferences table (persist to DB, not just localStorage)
    - [ ] P4-04b: Merge ReadingTab → ReaderThemeProvider
          - Unify font size, line-height, font family, theme presets
          - ReadingTab becomes the UI for ReaderThemeProvider settings
          - Remove standalone localStorage approach in ReadingTab
          - Support 6 theme presets (not 3) matching ReaderThemeProvider
    - [ ] P4-04c: Theme customizer panel in Reader (inline, not in Settings)
          - Quick-toggle dropdown in reader toolbar (P3-R1-D14)
          - Font size control in reader (P3-R1-D15)
          - Full customizer panel matching screen-theme-customizer.html
    - [ ] P4-04d: Live preview in Settings ReadingTab
          - Show reader-like preview with actual theme applied
    - [ ] P4-04e: API persistence — save/load from BE instead of localStorage
    - [ ] P4-04f: Sync — changes in reader customizer reflect in Settings and vice versa

  Impact areas (refactor scope):
    - providers/ReaderThemeProvider.tsx — core theme logic
    - features/settings/ReadingTab.tsx — Settings UI
    - pages/ReaderPage.tsx — reader toolbar integration
    - CSS variables — unify .reader-content scoping
    - localStorage migration — existing users' saved prefs

P4-05: Settings — Language + Notification Prefs [FE]

P4-06: Usage Monitor — Dashboard [FE] (uses existing usage-billing)
P4-07: Usage Monitor — Request Log [FE]

P4-08a: Author Analytics — Backend [BE]
  Scope: Extend usage-billing or catalog with aggregate endpoints
  New endpoints:
    - GET /v1/me/analytics/overview (total readers, favorites, rating trend)
    - GET /v1/me/analytics/books/{id} (per-chapter: readers, drop-off, comments)
    - GET /v1/me/analytics/readers (referral sources, geography)
  AC: [ ] Aggregate queries, period filtering

P4-08b: Author Analytics — Frontend [FE]
  Deps: P4-08a

P4-09: Browse Catalog [FE] (uses existing catalog-service + social-service for ratings)
  AC: [ ] Trending, recently updated, featured, complete/ongoing filter

P4-10: Public Book Page [FE]
  AC: [ ] Cover, rating summary, reviews, translations, read button

P4-11: Leaderboard [FE]
  AC: [ ] Podium, rankings (computed from social-service data)

P4-12: My Library [FE] (uses social-service favorites + progress)

P4-13a: Export — Backend [BE]
  Scope: Extend book-service
  New endpoint: GET /v1/books/{id}/export?format=epub|pdf|json
  AC: [ ] Generate .epub with cover + chapters, .pdf, or full JSON backup

P4-13b: Export — Frontend [FE]
  Deps: P4-13a
  AC: [ ] Export button on book detail, format selector, download

P4-14: Email Notifications [BE]
  Scope: Email sending integration in notification backend
  AC: [ ] Email templates, per-event email toggle, SMTP integration

P4-15: Keyboard Shortcuts [FE]
P4-16: Mobile Responsive [FE]
```

---

## Phase 5: Advanced (outline)

```
P5-01: Translation Memory [BE + FE]
P5-02: Collaborative Translation [BE + FE]
P5-03: Bookmarks + Highlights [BE + FE]
P5-04: Dictionary Lookup [FE]
P5-05: Text-to-Speech [FE]  <-- SUPERSEDED by Phase 4.5 (E6/E7)
P5-06: Character Relationship Graph [FE]
P5-07: AI Consistency Checker [BE + FE]
P5-08: Monetization Hooks [BE + FE]
P5-09: Platform Admin Dashboard [BE + FE]
P5-10: Federated Discovery [BE]
```

---

## Dependency Graph

```
PHASE 1 (FE foundation — no backend)
  P1-01 → P1-02 → P2-01 (shared components)
  P1-01 → P1-03 (i18n)
  P1-01 → P1-04 → P1-05 (API + mode)
  P1-01 → P1-06 → P1-07 (router + sidebar)

PHASE 2 (core screens — minimal backend)
  P2-01 → P2-02 → P2-03 → P2-04 → P2-05 (books → editor chain)
  P2-05 → P2-06 (split-view)
  P1-06 → P2-07 → P2-08 (reader + theme)
  P1-07 → P2-09 → P2-09b → P2-09c (notifications: FE → BE → wire)
  P2-02 → P2-10 (onboarding)
  P2-11b ──────→ P2-11a (import: BE first, then FE)

PHASE 3 (features — new backend services)
  P3-09 (social-service scaffold) → P3-10, P3-11, P3-12, P3-13, P3-14, P3-16
  P3-15a (follow backend) → P3-15b (profile FE)
  P3-17a (wiki backend) → P3-17b, P3-17c, P3-17d → P3-17e
  BE-G1..G5 (genre backend) → FE-G1..G7 (genre FE, zero blockers)
  P3-01...P3-04 (translation FE — no backend needed)
  P3-05...P3-07 (glossary FE — no backend needed)
  P3-18, P3-19 (chat FE — no backend needed)
```

### Parallelizable Work

```
Can run simultaneously:
  Backend: P2-09b + P2-11b + P3-09 + P3-15a + P3-17a + BE-G1..G5
  Frontend: P2-01...P2-08 (all Phase 2 FE tasks)

This means backend work for Phase 3 can start while Phase 2 frontend is building.
```

---

## Summary

| Phase | FE Tasks | BE Tasks | FS Tasks | Total |
|---|---|---|---|---|
| Phase 1 | 11 | 0 | 0 | 11 |
| Phase 2 | 13 | 2 | 1 | 16 |
| Phase 3 | 16 | 5 | 3 | 24 |
| Phase 4 | 11 | 3 | 0 | 14 |
| Phase 5 | 4 | 1 | 5 | 10 |
| **Total** | **55** | **11** | **9** | **75** |

### Critical Path
```
P1-01 → P1-02 → P2-01 → P2-02 → P2-03 → P2-04 → P2-05 (longest FE chain)
P3-09 (social-service) blocks all community features
P3-17a (wiki backend) blocks all wiki features
```

### Backend Priority Order
```
1. P2-09b  Notifications (needed for Phase 2 completion)
2. P2-11b  Import .docx/.epub (user acquisition)
3. P3-09   Social Service scaffold (blocks most of Phase 3)
4. P3-15a  Follow system (blocks profiles)
5. P3-17a  Wiki backend (blocks wiki)
6. BE-G1..G5  Genre groups backend (unblocks all genre FE)
7. P4-08a  Author analytics
8. P4-13a  Export
9. P4-14   Email notifications
```


---

## Phase 2.5: Editor Engine -- Tiptap Migration (before Phase 3)

> **Why before Phase 3:** Translation split-view (P2-06), Glossary in editor (P3-05),
> and Chat context (P3-19) all interact with the editor. Building on Tiptap avoids double work.
>
> **Design drafts:**
> - `design-drafts/screen-editor-mixed-media.html` -- AI Assistant mode (full features)
> - `design-drafts/screen-editor-classic.html` -- Classic mode (pure writing)
> - `design-drafts/screen-editor-modes.html` -- Mode spec, guards, version data model
> - `design-drafts/screen-editor-version-history.html` -- Media version tracking UI

### E1: Tiptap Foundation + Text Blocks

| Task | Type | Scope | Deps | Est |
|---|---|---|---|---|
| E1-01 [✓] | FE | Install Tiptap + extensions (StarterKit, Placeholder, CodeBlockLowlight, Typography) | None | S |
| E1-02 [✓] | FE | Replace textarea source mode with Tiptap editor (paragraph, heading, divider) | E1-01 | M |
| E1-03 [✓] | FE | Replace ChunkItem/ChunkInsertRow with Tiptap block nodes + slash menu (/) | E1-02 | M |
| E1-04 [✓] | FE | Callout custom node (author notes) | E1-02 | S |
| E1-05 [✓] | FE | Grammar check as Tiptap DecorationPlugin (LanguageTool wavy underlines) | E1-02 | M |
| E1-06 [✓] | FE | Mode toggle: Classic / AI Assistant (localStorage, toolbar) | E1-02 | S |
| E1-07 [✓] | FE | Classic mode: minimal toolbar, text-only slash menu | E1-06 | S |
| E1-08 [✓] | FE | Wire existing features: auto-save (5m), Ctrl+S, dirty tracking, unsaved guard, revisions | E1-03 | M |

### E2: Block JSON Storage

| Task | Type | Scope | Deps | Est |
|---|---|---|---|---|
| E2-01 | FS | Block JSON storage format (body_format column on chapter_drafts) | E1-03 | M |
| E2-02 | FS | Auto-migration: plain text to block JSON on first save | E2-01 | S |
| E2-03 | FE | Source view tab: read-only JSON inspector | E2-01 | S |

### E3: Grammar Panel

| Task | Type | Scope | Deps | Est |
|---|---|---|---|---|
| E3-01 | FE | Grammar issues panel in right sidebar (click to scroll to block) | E1-05 | S |

**GATE:** After E1-08, editor is production-ready for text. Phase 3 can begin.

---

## Phase 3.5: Media Blocks (after Phase 3 FE-only tasks)

> Design drafts: `screen-editor-mixed-media.html`, `screen-editor-version-history.html`, `screen-editor-modes.html`
>
> Current editor state: TiptapEditor with StarterKit (heading 1-3, horizontalRule, no codeBlock),
> Placeholder, Typography, CalloutExtension (ReactNodeViewRenderer), GrammarExtension,
> SlashMenuExtension. Mode toggle (`classic`/`ai`) filters slash menu items. No media blocks yet.

### E4: Image + Video + Code Blocks

| Task | Type | Scope | Deps | Est |
|---|---|---|---|---|
| E4-01 | FE | Image block Tiptap node — ReactNodeViewRenderer with: preview, editable caption, **alt text field** (accessibility, EPUB export), **resize handles** (corner drag, constrained aspect ratio, width stored in block attrs), selection outline, block menu (⋯) | — | M |
| E4-02 | FE | Image upload: drag-drop zone, clipboard paste (Ctrl+V), file picker — upload to MinIO via gateway, progress indicator, max 10 MB, formats: PNG/JPG/GIF/WebP | E4-01 | M |
| E4-03 | FE | AI prompt field on media blocks — collapsible `<details>` per image/video block, prompt textarea stored in block JSON `ai_prompt` attr, "Re-generate" + "Copy prompt" buttons, `prompt-badge` (saved/empty) | E4-01 | S |
| E4-04 | FE | Classic mode guards — media blocks render as compact locked placeholders (`NodeView` with `editable: false`), `handleKeyDown` extension intercepts backspace/delete at media boundaries, guard overlay on attempted deletion with "Switch to AI mode" action, Select-all+delete protects media blocks, drag handle hidden on media in classic mode | E4-01 | S |
| E4-05 | FE | Video block — ReactNodeViewRenderer: player placeholder (play button overlay, duration, file size), editable caption, upload to MinIO, AI prompt field (generation marked "coming soon"), formats: MP4/WebM, max 100 MB | E4-02 | M |
| E4-06 | FE | Code block — Tiptap CodeBlockLowlight extension: syntax highlighting (lowlight/highlight.js), language selector dropdown in header bar, copy button, line numbers optional | — | S |
| E4-07 | FE | Slash menu + FormatToolbar media integration — add Image/Video/Code/Callout insert buttons to FormatToolbar (AI mode only), add Image/Video/Code items to slash menu with `modes: ['ai']`, add Translate/Send-to-AI buttons to toolbar (AI mode) | E4-01, E4-05, E4-06 | S |
| E4-08 | FE | Source view tab — read-only Block JSON viewer (toggle Visual/Source in toolbar), syntax-highlighted JSON of chapter structure, Copy JSON button | E4-01 | S |

### E5: Media Version Tracking + AI Generation

| Task | Type | Scope | Deps | Est |
|---|---|---|---|---|
| E5-01 | FS | Media version tracking backend — `block_media_versions` table in loreweave_books (block_id, version, action, changes[], prompt_snapshot, media_ref, caption_snapshot, ai_model, created_at), CRUD endpoints on book-service, MinIO path pattern `chapters/{chapterId}/blocks/{blockId}/v{N}.{ext}`, retention policy config (keep last 10 versions) | E4-01 | M |
| E5-02 | FE | Version history UI — split-panel layout (left: side-by-side image comparison with version labels, right: dot timeline with tags), prompt diff (git-style red/green lines), Image/Audio tabs, Restore/Download/Delete actions, storage stats in bottom bar | E5-01 | L |
| E5-03 | FS | AI image generation — prompt from block `ai_prompt` attr, routed through provider-registry to AI provider, response stored in MinIO, new version created in block_media_versions, provider/model recorded | E4-03 | L |
| E5-04 | FE | Re-generate from prompt — "Re-generate" button triggers E5-03, creates version snapshot (prompt + old media preserved), progress indicator during generation, error handling (402 no credits, 502 provider error) | E5-01, E5-03 | M |

### Design decisions (Phase 3.5)

- **Resize handles on E4-01** (not deferred): image blocks without resize are unusable — users need layout control from day one. Stores `width` (percentage or px) in block attrs; aspect ratio locked by default.
- **Alt text on E4-01** (not deferred): required for WCAG 2.1 AA compliance and EPUB export. Separate from caption — caption is visible to readers, alt is for screen readers and broken images. Rendered as a secondary input or collapsible field in the image block UI.
- **Audio/TTS remains Phase 4.5**: the mixed-media draft designs audio slots on text blocks, but audio is a separate concern from visual media. Build visual media first.
- **Version data model**: versions stored as `media_versions` array in block JSON (lightweight metadata) + actual media files in MinIO with versioned paths. Old prompts are always kept (cheap text). Media files subject to retention policy.
- **Classic mode guards**: Tiptap `NodeView` with `editable: false` + `handleKeyDown` at media boundaries. No data deleted on mode switch — media blocks collapse to compact locked placeholders.
- **Video generation service**: `video-gen-service` (Python/FastAPI) created as skeleton. Returns `status: "not_implemented"` until a real provider is connected. FE Generate button wired and ready.

### Media Version Retention (future enhancement)

> Current state: versions are created on upload/replace/generate but never deleted automatically.
> Users can manually delete individual versions via the VersionHistoryPanel.

| Task | Type | Scope | Deps | Est |
|---|---|---|---|---|
| MV-01 | BE | Auto-create version on every replace (currently only when blockId is passed) | E5-01 | S |
| MV-02 | BE | Retention policy config — keep last N versions per block (default 10) | E5-01 | S |
| MV-03 | BE | Auto-delete oldest versions exceeding retention limit (trigger on new version insert) | MV-02 | S |
| MV-04 | BE | MinIO garbage collection — delete orphaned media files when version records are purged | MV-03 | S |
| MV-05 | FE | Retention settings UI — per-book or global setting for max versions | MV-02 | S |
| MV-06 | FE | Storage usage display — total version storage per chapter/book | E5-01 | S |
| MV-07 | BE | Bulk version cleanup endpoint — purge all versions older than N days | MV-04 | S |

**How it should work:**
1. Every replace/upload/generate creates a new version (keeps old media in MinIO)
2. Retention policy checks on insert: if block exceeds max versions, delete oldest
3. Deleted version records trigger MinIO object cleanup (best-effort)
4. User can always manually delete specific versions from the history panel
5. Storage usage visible per chapter and per book

### V1 → V2 Migration (pages not yet ported from old `frontend/`)

> The old `frontend/` directory contains pages and features that were never migrated to `frontend-v2/`.
> These are currently PlaceholderPages in v2. After all are migrated, delete `frontend/` entirely.

**Pages to migrate (10 pages, all FE):**

| Task | Route | Source | Lines | Est |
|---|---|---|---|---|
| MIG-01 | `/trash` | `RecycleBinPageV2.tsx` + `features/trash/` (4 files) | 618 | M |
| MIG-02 | `/chat` | `ChatPageV2.tsx` + `features/chat-v2/` (23 files) | 900 | L |
| MIG-03 | `/usage` | `UsageLogsPage.tsx` | 81 | S |
| MIG-04 | `/usage/:logId` | `UsageDetailPage.tsx` | 59 | S |
| MIG-05 | `/settings/:tab` | `UserSettingsPage.tsx` + `components/settings/` | 54+ | M |
| MIG-06 | `/browse` | `BrowsePage.tsx` | 45 | S |
| MIG-07 | `/browse/:bookId` | `PublicBookDetailPage.tsx` | 287 | S | [✓] Done (session 18) |
| MIG-08 | `/s/:accessToken` | `SharedBookPage.tsx` | 332 | S | [✓] Done (session 18) |
| MIG-09 | Chapter translations view | 5 sub-tasks below | 500+ | L | [ ] |
| MIG-10 | Delete old `frontend/` directory | — | — | S | [ ] blocked by MIG-09 |

**MIG-09 Detailed Breakdown (BE first, then FE):**

> **Design draft:** `design-drafts/screen-chapter-translations.html`
> **Route:** `/books/:bookId/chapters/:chapterId/translations`
> **BE APIs exist:** list versions, get version, set active (translation-service)

```
BE-MIG09-01: versionsApi in FE translation/api.ts              [ ]
  - listChapterVersions(token, chapterId)
    → GET /v1/translation/chapters/:id/versions
  - getChapterVersion(token, chapterId, versionId)
    → GET /v1/translation/chapters/:id/versions/:vid
  - setActiveVersion(token, chapterId, versionId)
    → PUT /v1/translation/chapters/:id/versions/:vid/active
  Note: BE endpoints exist — this is FE API client only
  Size: S

FE-MIG09-02: VersionSidebar component                          [ ]
  - Language tabs: Original + target languages with version counts
  - Version list per language: v1/v2/v3 with model name, status, time
  - Active badge on active version
  - Status colors: completed (green), running (blue), failed (red)
  - Re-translate button → opens TranslateModal
  - Compare Mode toggle button
  Size: M

FE-MIG09-03: TranslationViewer component                       [ ]
  - Toolbar: version name, status badges, token counts, model name
  - Actions: Copy text, Set Active (if completed + not already active)
  - Content: translated body (serif font, reading-optimized)
  - Loading state for version content fetch
  Size: S

FE-MIG09-04: SplitCompareView component                        [ ]
  - Two panes: Original (left) + Translation (right)
  - Header labels: language + version
  - Center divider with "ja → en" label
  - Both panes scroll independently
  - Exit compare button
  Size: S

FE-MIG09-05: ChapterTranslationsPage + route                   [ ]
  - Full-height layout: VersionSidebar (left) + content (right)
  - URL-driven: ?lang=en&vid=xxx
  - Auto-select: most-translated language + active version
  - Empty state: no translations → "Translate" CTA
  - Breadcrumb: Back to book link
  - Route: /books/:bookId/chapters/:chapterId/translations
  - Navigation from TranslationTab matrix (click cell → this page)
  Size: M
  Deps: FE-MIG09-02, 03, 04
```

**Migration strategy:**
- Rebuild from scratch matching v2 design system (not copy from old frontend)
- BE-first: verify API contract with test script before FE
- Reuse existing v2 API clients + TranslateModal
- Replace PlaceholderPage routes with real pages
- After MIG-01..MIG-09 complete, MIG-10 deletes old frontend/

**Already migrated (no action needed):**
- BooksPage, BookDetailPage, ChapterEditorPage, ReaderPage
- Auth pages (Login, Register, Forgot, Reset)
- BookDetail tabs (Chapters, Translation, Glossary, Sharing, Settings)
- MIG-01..MIG-08: all done (session 15-18)

**Dead code in old frontend/ (delete with MIG-10):**
- `chunk-editor/` — replaced by Tiptap
- `chat/` (v1) — replaced by chat-v2
- `RecycleBinPage.tsx` (v1) — replaced by RecycleBinPageV2
- All test files for migrated pages

### Version History Panel Enhancements (future polish)

> Current state: Basic version history works — timeline, side-by-side comparison, prompt diff, restore/download/delete.
> Compared to design draft `screen-editor-version-history.html`, the following features are missing.

| Task | Type | Scope | Deps | Est | Priority |
|---|---|---|---|---|---|
| VH-01 | FE | Image/Audio tabs in history panel (switch between media + audio versions) | Phase 4.5 (Audio/TTS) | M | P2 |
| VH-02 | FE | Image dimensions + file size on each comparison side | — | S | P2 |
| VH-03 | FE | Version detail/description text (not just truncated prompt) | — | S | P2 |
| VH-04 | FE+BE | Auto-create "prompt written" version when AI prompt is saved (no media yet) | — | S | P3 |
| VH-05 | FE+BE | Auto-create "block created" version on block insert | — | S | P3 |
| VH-06 | FE | Retention policy display in bottom bar ("keep last 10 versions") | MV-02 | S | P2 |
| VH-07 | FE | MinIO path display in bottom bar (debug info) | — | S | P3 |
| VH-08 | FE | Delete button on audio versions tab | Phase 4.5 | S | P2 |
| VH-09 | FE | Voice tag display for TTS voice changes | Phase 4.5 | S | P3 |
| VH-10 | FE | Caption change inline preview in timeline items ("old" → "new") | — | S | P2 |
| VH-11 | FE | Git-branch icon in Versions header | — | S | P3 |
| VH-12 | FE | Per-side comparison metadata (filename, dimensions, size below each image) | — | S | P2 |

**Non-blocked (can do now):** VH-02, VH-03, VH-10, VH-11, VH-12
**Blocked by Phase 4.5 (Audio/TTS):** VH-01, VH-08, VH-09
**Blocked by MV retention tasks:** VH-06

### Video Generation Service — Provider Integration (future)

> Service: `services/video-gen-service/` — Python/FastAPI, port 8088 (host: 8213)
> Gateway: `/v1/video-gen` proxied via `api-gateway-bff`
> Status: **Skeleton deployed** — interface stable, no provider connected

| Task | Type | Scope | Deps | Est |
|---|---|---|---|---|
| VG-01 | BE | Provider adapter: OpenAI Sora (text-to-video) | video-gen-service, provider-registry | M |
| VG-02 | BE | Provider adapter: Google Veo (text-to-video) | video-gen-service, provider-registry | M |
| VG-03 | BE | Provider adapter: Stability AI Stable Video (image-to-video) | video-gen-service, provider-registry | M |
| VG-04 | BE | Provider adapter: RunwayML Gen-3 (text/image-to-video) | video-gen-service, provider-registry | M |
| VG-05 | BE | MinIO storage integration (store generated videos) | video-gen-service, MinIO | S |
| VG-06 | BE | Async generation with status polling (pending → completed) | video-gen-service, Redis | M |
| VG-07 | FE | Generation progress UI (polling, status badge, cancel) | VG-06 | M |
| VG-08 | FE | Model selector in video block (pick from available models) | VG-01..04 | S |
| VG-09 | BE | JWT validation + user ownership check | video-gen-service | S |
| VG-10 | BE | Version record creation on generate (reuse block_media_versions) | VG-05, E5-01 | S |

**Implementation order:** VG-09 (auth) → VG-05 (MinIO) → VG-01 (first provider) → VG-06 (async) → VG-07 (progress UI) → VG-10 (versioning) → VG-08 (model selector) → VG-02..04 (more providers)

**Provider API formats (for adapter development):**
- OpenAI Sora: `POST /v1/video/generations` (OpenAI-compatible, similar to images)
- Google Veo: Vertex AI endpoint, different auth + format
- Stability AI: `POST /v2beta/image-to-video` (REST, different response format)
- RunwayML: GraphQL API, webhook-based async

Each adapter translates to the `GenerateResponse` schema defined in `app/models.py`.

---

## Phase 4.5: Audio / TTS (after Phase 4)

> Replaces P5-05 (Text-to-Speech) with per-paragraph narration system.

| Task | Type | Scope | Deps | Est |
|---|---|---|---|---|
| E6-01 | FE | Audio attachment slot on text blocks (empty state + upload) | E4-02 | S |
| E6-02 | FE | Audio player: waveform, play/pause, speed control | E6-01 | M |
| E6-03 | FS | AI TTS generation (text to provider-registry to MinIO) | E6-01 | M |
| E6-04 | FE | Audio visibility: hidden default, shown in AI mode or narration mode | E6-01, E1-06 | S |
| E6-05 | FS | Audio version tracking (reuse E5-01 table) | E5-01, E6-03 | S |
| E7-01 | FE | Bulk TTS: "Generate all narration" per chapter | E6-03 | M |
| E7-02 | FS | Audiobook export: concatenate chapter audio to single file | E7-01, P4-13a | L |

---

## Phase 6: Chat Enhancement — Competitive Parity & Beyond

> **Goal:** Bring LoreWeave chat to feature parity with Claude, ChatGPT, LM Studio, Gemini —
> then surpass them with novel-workflow-specific features (context attach, paste to editor, etc.).
>
> **Principle:** Extend, don't remake. Current GUI is solid — add capabilities, not new layouts.
>
> **Design draft:** `design-drafts/screen-chat-enhanced.html`

### Competitive Reference

| Feature | Claude | ChatGPT | LM Studio | Gemini | LoreWeave (now) | LoreWeave (target) |
|---------|--------|---------|-----------|--------|-----------------|-------------------|
| Streaming response | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Thinking mode toggle | ✅ Extended | ✅ Reasoning | ✅ Checkbox | ✅ Deep Think | ❌ | ✅ C6-01 |
| Thinking output display | ✅ Collapsible | ✅ Collapsible | ✅ Raw block | ✅ Collapsible | ❌ | ✅ C6-01 |
| System prompt per session | ✅ Projects | ✅ Custom instr | ✅ Per-chat | ✅ Gems | ❌ (DB has field) | ✅ C6-02 |
| Max tokens control | ❌ | ❌ | ✅ Slider | ❌ | ❌ | ✅ C6-03 |
| Temperature control | ❌ | ❌ | ✅ Slider | ❌ | ❌ | ✅ C6-03 |
| Top P control | ❌ | ❌ | ✅ Slider | ❌ | ❌ | ✅ C6-03 |
| Model switch mid-session | ✅ | ✅ Dropdown | ✅ Dropdown | ✅ | ❌ (create new) | ✅ C6-04 |
| Token usage on messages | ❌ | ❌ | ✅ Per-msg | ❌ | ❌ (BE has data) | ✅ C6-05 |
| Message branching | ✅ Fork | ✅ < > arrows | ❌ | ❌ | ❌ (truncate) | ✅ C6-10 |
| Search messages | ❌ | ✅ | ❌ | ❌ | ❌ | ✅ C6-11 |
| Keyboard shortcuts | ✅ | ✅ | ✅ | ✅ | Enter only | ✅ C6-08 |
| Session folders/pins | ❌ | ✅ | ❌ | ❌ | ❌ | ✅ C6-09 |
| Context attach (stories) | ❌ | ❌ | ❌ | ❌ | ✅ Unique! | ✅ Enhance |
| Paste to Editor | ❌ | ❌ | ❌ | ❌ | ✅ Unique! | ✅ Keep |
| Output card extraction | ❌ | ✅ Artifacts | ❌ | ❌ | ✅ | ✅ Enhance |

### Priority 1 — Critical (thinking support + session settings)

```
C6-01: Thinking Mode + Reasoning Display [FS]                 [ ]
  Scope: Backend stream reasoning_content, FE toggle + collapsible thinking block.
  BE changes:
    - stream_service.py: parse delta.reasoning_content (Qwen3, DeepSeek-R1)
    - Emit SSE event type "reasoning-delta" separate from "text-delta"
    - Track thinking_tokens separately in usage
    - SendMessageRequest: add generation_params.thinking (bool)
    - acompletion(): pass thinking param when supported
  FE changes:
    - ChatInputBar: [💭 Think / ⚡ Fast] toggle button (only if model capability_flags.thinking)
    - AssistantMessage: collapsible ThinkingBlock component
      - Animated "Thinking..." with elapsed time during stream
      - Collapsed by default after completion, expandable
      - Monospace font, muted text color
    - useChatMessages: parse "reasoning-delta" events, track thinkingText separately
    - MessageBubble: show thinking_tokens + output_tokens footer
  Acceptance:
    - Qwen3 thinking tokens stream in real-time (no blank wait)
    - Toggle switches between thinking/fast mode per-message
    - Thinking block collapsible, shows duration
    - Non-thinking models hide toggle
  Size: M
  Deps: existing chat-service, provider-registry capability_flags

C6-02: System Prompt Editor [FE]                               [ ]
  Scope: Expose existing system_prompt field in UI.
  FE changes:
    - NewChatDialog: add expandable "System Prompt" textarea
    - ChatHeader: pencil icon → Session Settings popover/slide-over
    - SessionSettings panel: edit system_prompt + save via PATCH
    - System prompt template presets (Novelist, Translator, Worldbuilder, Custom)
  Acceptance:
    - System prompt visible in new chat dialog
    - Editable from header settings
    - Persists across page reload
    - Preset templates work
  Size: S
  Deps: PatchSessionRequest already supports system_prompt

C6-03: Generation Parameters [FS]                              [ ]
  Scope: max_tokens, temperature, top_p per-session.
  BE changes:
    - chat_sessions: add generation_params JSONB column (default {})
    - PatchSession: accept generation_params
    - stream_service.py: read params from session, pass to acompletion()
    - Validate ranges: temperature 0-2, top_p 0-1, max_tokens 1-128000
  FE changes:
    - SessionSettings panel: sliders for temperature, top_p, max_tokens
    - max_tokens: number input + "Unlimited" toggle (∞)
    - temperature: slider 0-2 with 0.1 steps, default 0.7
    - top_p: slider 0-1 with 0.05 steps, default 0.9
    - Show "Advanced" accordion (collapsed by default)
    - Save to session via PATCH
  Acceptance:
    - Parameters affect model output (lower temp = more deterministic)
    - Unlimited mode sends no max_tokens to provider
    - Settings persist per-session
  Size: M
  Deps: C6-02 (shares SessionSettings panel)
```

### Priority 2 — High (UX parity with Claude/ChatGPT)

```
C6-04: Model Switch Mid-Session [FE]                           [ ]
  Scope: Change model without creating new session.
  FE changes:
    - ChatHeader or SessionSettings: model dropdown (from user_models)
    - PATCH session with new model_ref + model_source
    - Divider in message list: "Switched to {model}" annotation
  Acceptance:
    - Model switchable mid-conversation
    - New messages use new model
    - Visual indicator of model switch in history
  Size: S
  Deps: PatchSessionRequest already supports model_source + model_ref

C6-05: Token Usage Display [FE]                                [ ]
  Scope: Show token counts already stored in ChatMessage.
  FE changes:
    - AssistantMessage footer: "↑ 1,234 in · ↓ 567 out" subtle text
    - Show on hover or always (user preference)
    - Thinking messages: "💭 890 thinking · ↑ 1,234 in · ↓ 567 out"
    - Session total in ChatHeader: "Total: 12.4K tokens"
  Acceptance:
    - Token counts visible per-message
    - Session total accurate
    - No layout shift
  Size: S
  Deps: data already in ChatMessage.input_tokens/output_tokens

C6-06: Enhanced New Chat Dialog [FE]                           [ ]
  Scope: Upgrade dialog to match competitor onboarding.
  FE changes:
    - Model selector with grouped list (by provider), search filter
    - System prompt textarea with template presets dropdown
    - Quick-start tiles: "Novel Assistant", "Translator", "Worldbuilder"
    - Recent model pill (last used model pre-selected)
    - Model capability badges (🧠 thinking, 🎨 vision, 📝 128K context)
  Acceptance:
    - Models grouped by provider, searchable
    - Presets fill system prompt
    - Last used model pre-selected
  Size: M
  Deps: C6-02

C6-07: Session Settings Slide-Over [FE]                        [ ]
  Scope: Unified settings panel accessible from ChatHeader.
  FE changes:
    - Slide-over panel (right side, 360px wide)
    - Sections: Model, System Prompt, Parameters, Info
    - Info section: created date, message count, total tokens, model history
    - "Reset to Defaults" button
  Acceptance:
    - Accessible from ⚙️ icon in ChatHeader
    - All settings editable without leaving chat
    - Changes apply immediately
  Size: S
  Deps: C6-02, C6-03, C6-04
```

### Priority 3 — Competitive advantage

```
C6-08: Keyboard Shortcuts [FE]                                 [ ]
  Scope: Power user shortcuts for chat.
  FE changes:
    - Ctrl+Shift+Enter: send with thinking mode ON
    - Ctrl+Enter: send with thinking mode OFF (fast)
    - Ctrl+/: focus input bar
    - Escape: stop streaming
    - Ctrl+Shift+C: copy last assistant message
    - Ctrl+N: new chat
    - Ctrl+Shift+S: open session settings
    - Show shortcut hints in tooltip/footer
  Acceptance:
    - All shortcuts work, no conflicts with browser
    - Hints visible in footer text
  Size: S

C6-09: Session Organization [FE]                               [ ]
  Scope: Pin and group sessions in sidebar.
  FE changes:
    - Pin/unpin sessions (pinned always at top)
    - Group by: "Today", "Yesterday", "This week", "Older" (auto)
    - Search/filter sessions by title
    - Collapse groups
  Acceptance:
    - Pinned sessions stick to top
    - Temporal grouping automatic
    - Search filters in real-time
  Size: M

C6-10: Message Branching [FS]                                  [ ]
  Scope: Edit creates a branch, navigate between branches.
  BE changes:
    - New table: message_branches (branch_id, session_id, parent_sequence, created_at)
    - Edit: create branch instead of deleting messages
    - API: list branches for a sequence point
  FE changes:
    - After edit: show "< 1/2 >" branch navigator on the edited message
    - Navigate between alternative responses
    - Branch tree view (optional, in session settings)
  Acceptance:
    - Edit preserves original messages in a branch
    - User can navigate between branches
    - Branch count visible
  Size: L
  Deps: requires schema change + significant logic

C6-11: Message Search [FE]                                     [ ]
  Scope: Search within current session and across all sessions.
  FE changes:
    - Ctrl+F: search within current session (highlight matches)
    - Sidebar search: filter sessions by message content
    - Search results: show matched message snippet, click to jump
  BE changes (optional):
    - Full-text search index on chat_messages.content
    - GET /v1/chat/search?q=...&user_id=...
  Acceptance:
    - In-session search highlights matches and scrolls to them
    - Cross-session search shows relevant sessions
  Size: M

C6-12: Response Format Options [FE]                            [ ]
  Scope: Let user request specific output format.
  FE changes:
    - Dropdown or pills in input bar: "Auto", "Concise", "Detailed", "Bullet Points", "Table"
    - Appends format instruction to system prompt dynamically
  Acceptance:
    - Format selection affects response style
    - Persists per-session
  Size: S
```

### Priority 4 — Polish & delight

```
C6-13: Streaming Indicators [FE]                               [ ]
  Scope: Better visual feedback during streaming.
  FE changes:
    - Thinking phase: pulsing brain icon + "Thinking..." + elapsed seconds timer
    - Response phase: streaming speed indicator (tokens/sec)
    - Complete: subtle checkmark + total time
  Size: S

C6-14: Message Actions Menu [FE]                               [ ]
  Scope: Context menu on messages (right-click or ··· button).
  FE changes:
    - Copy text, Copy as markdown, Copy code blocks
    - Share message (future)
    - Pin message (bookmarks within session)
    - "Send to Editor" (existing paste-to-editor enhanced)
  Size: S

C6-15: Auto-Title Generation [FS]                              [ ]
  Scope: Auto-generate session title from first exchange.
  BE changes:
    - After first assistant response, call LLM with "Summarize in 5 words"
    - Update session title automatically
  FE changes:
    - Show "New Chat" initially, animate title change
    - User can still manually rename
  Size: S

C6-16: Chat Prompt Library [FE]                                [ ]
  Scope: Saved prompt templates accessible from input bar.
  FE changes:
    - "/" command in input: shows template picker
    - Templates: user-created + built-in (translate, analyze, summarize...)
    - Template variables: {{selected_text}}, {{chapter_title}}, etc.
  Size: M
```

### Dependency Graph (Chat Enhancement)

```
C6-01 (thinking) ──→ C6-08 (shortcuts: Ctrl+Shift+Enter)
                  ──→ C6-13 (thinking indicators)
C6-02 (system prompt) ──→ C6-06 (enhanced new chat)
                       ──→ C6-07 (session settings panel)
C6-03 (gen params) ──→ C6-07 (session settings panel)
C6-04 (model switch) ──→ C6-07 (session settings panel)
C6-05 (token display) — standalone
C6-09 (organization) — standalone
C6-10 (branching) — standalone (complex, can defer)
C6-11 (search) — standalone
C6-12 (format) — standalone
C6-14 (actions menu) — standalone
C6-15 (auto-title) — standalone
C6-16 (prompt library) — standalone
```

### Implementation Order — BE First, Verify, Then FE

**Strategy:** All backend changes first, verified with integration test scripts,
then FE in a second pass. This ensures the API contract is stable before building UI.

**Test model:** Qwen3-1.7B on LM Studio (host.docker.internal:1234)
Must insert provider + user_model into DB before testing.

```
────────────────────────────────────────────────────────────────────────
PHASE A: BACKEND (all BE tasks, verified with test scripts)
────────────────────────────────────────────────────────────────────────

BE-C6-01: generation_params column + migration                  [ ]
  - ALTER TABLE chat_sessions ADD COLUMN generation_params JSONB DEFAULT '{}'
  - Update migrate.py DDL
  - PatchSessionRequest: add generation_params field
  - patch_session: COALESCE merge generation_params
  - create_session: accept generation_params
  - Test: create session with params, PATCH params, verify persisted
  Size: S

BE-C6-02: stream_service reads generation_params               [ ]
  - Load session.generation_params before streaming
  - Pass to acompletion(): max_tokens, temperature, top_p
  - Validate ranges (temperature 0-2, top_p 0-1, max_tokens 1-128000)
  - If generation_params.max_tokens is null/0 → omit (unlimited)
  - Test: create session with temperature=0.1, send message, verify lower randomness
  Size: S
  Deps: BE-C6-01

BE-C6-03: system_prompt injection in streaming                  [ ]
  - stream_service.py: read session.system_prompt from DB
  - Prepend as {"role":"system","content":...} to messages array
  - System prompt + per-message context coexist (system prompt first)
  - Test: create session with system_prompt="Answer only in rhymes",
    send "What is your favorite color?", verify rhyming response
  Size: S

BE-C6-04: thinking mode — reasoning_content parsing             [ ]
  - SendMessageRequest: add thinking field (bool, default false)
  - stream_service.py: when thinking=true, pass extra param to acompletion
    - For Qwen3/DeepSeek: reasoning via delta.reasoning_content
    - For others: graceful fallback (ignore thinking flag)
  - Emit SSE events: {"type":"reasoning-delta","delta":"..."} for thinking
  - Continue emitting {"type":"text-delta","delta":"..."} for content
  - Track thinking_tokens in finish event
  - Persist thinking_tokens in chat_messages (new column or content_parts JSONB)
  - Test: send with thinking=true to Qwen3, verify reasoning-delta events appear
  Size: M
  Deps: BE-C6-02

BE-C6-05: message search endpoint                               [ ]
  - GET /v1/chat/sessions/search?q=...
  - Full-text search on chat_messages.content + chat_sessions.title
  - Returns: [{session_id, title, message_id, role, snippet, created_at}]
  - CREATE INDEX idx_chat_messages_search ON chat_messages USING gin(to_tsvector('english', content))
  - Test: create sessions with messages, search by keyword, verify results
  Size: S

BE-C6-06: session pin field                                     [ ]
  - ALTER TABLE chat_sessions ADD COLUMN is_pinned BOOLEAN DEFAULT false
  - Update DDL, _row_to_session, ChatSession model
  - PatchSessionRequest: add is_pinned field
  - list_sessions: ORDER BY is_pinned DESC, last_message_at DESC
  - Test: pin session, list → pinned first
  Size: S

BE-C6-07: auto-title generation                                 [ ]
  - After first assistant message, generate title via LLM
  - Use same model, short prompt: "Summarize this conversation in 5 words"
  - Non-blocking: asyncio.create_task (like billing log)
  - Update session title in DB
  - Test: send first message, verify title changes from "New Chat"
  Size: S
  Deps: BE-C6-02

────────────────────────────────────────────────────────────────────────
PHASE B: INTEGRATION TEST SCRIPT
────────────────────────────────────────────────────────────────────────

TEST-C6: infra/test-chat-enhanced.sh                            [ ]
  Scenarios (extends existing test-chat.sh pattern):
  - T20: Create session with generation_params (temp=0.1, max_tokens=256)
  - T21: PATCH generation_params (change temperature)
  - T22: Create session with system_prompt, verify field persisted
  - T23: PATCH system_prompt
  - T24: Send message with system_prompt → verify response follows instruction
  - T25: Send message with thinking=true → verify reasoning-delta SSE events
  - T26: Send message with thinking=false → verify no reasoning-delta events
  - T27: Verify generation_params affect response (low temp → deterministic)
  - T28: Pin session, list → pinned session first
  - T29: Unpin session, list → normal order
  - T30: Search messages → returns matching sessions
  - T31: Auto-title after first message (title != "New Chat")
  - T32: Send with max_tokens=50 → response truncated
  - T33: Send with context + system_prompt → both present in LLM input
  Size: M
  Deps: BE-C6-01..07

────────────────────────────────────────────────────────────────────────
PHASE C: TEST DATA SETUP (run before integration tests)
────────────────────────────────────────────────────────────────────────

SETUP-C6: Insert LM Studio test provider + model                [ ]
  Docker host: host.docker.internal:1234
  Provider: lm_studio, api_standard: lm_studio
  Model: qwen/qwen3-1.7b
  Insert into: provider_credentials, user_models tables
  Script: infra/setup-chat-test-model.sh

────────────────────────────────────────────────────────────────────────
PHASE D: FRONTEND (after all BE verified)
────────────────────────────────────────────────────────────────────────

FE-C6-01: Session Settings slide-over                           [ ]
  - System prompt editor + preset templates
  - Generation params sliders (temperature, top_p, max_tokens)
  - Model selector dropdown (grouped by provider)
  - Session info cards (messages, tokens, cost)
  Deps: BE-C6-01, BE-C6-02, BE-C6-03

FE-C6-02: Thinking mode UI                                      [ ]
  - Think/Fast toggle in ChatInputBar
  - ThinkingBlock component (collapsible, purple, timer)
  - useChatMessages: parse reasoning-delta events
  - Keyboard: Ctrl+Shift+Enter = Think, Ctrl+Enter = Fast
  Deps: BE-C6-04

FE-C6-03: Token display + model badge                           [ ]
  - Token counts per-message footer
  - Session total in ChatHeader
  - Model badge (clickable → model switch)
  - Model switch annotation in message list
  Deps: BE-C6-01

FE-C6-04: Session sidebar enhancements                          [ ]
  - Search bar
  - Temporal groups (Today/Yesterday/This Week/Older)
  - Pin/unpin
  Deps: BE-C6-06

FE-C6-05: Enhanced NewChatDialog                                [ ]
  - Grouped model selector with search
  - System prompt textarea + presets
  - Quick-start tiles
  - Capability badges
  Deps: BE-C6-01

FE-C6-06: Keyboard shortcuts + format pills                     [ ]
  - All shortcuts from C6-08 spec
  - Format pills in input bar
  - Footer hints
  Deps: FE-C6-01, FE-C6-02

FE-C6-07: Message search UI                                     [ ]
  - Ctrl+F: in-session search with highlight
  - Sidebar cross-session search
  Deps: BE-C6-05

FE-C6-08: Message branching (if time permits)                   [ ]
  - Edit → branch instead of truncate
  - < 1/2 > navigator
  Deps: needs separate BE branch table (deferred)
```

---

## Phase 7: Infrastructure Hardening

> **Goal:** Cross-cutting security and reliability improvements.
> These are systemic issues that should be fixed across ALL services at once,
> not piecemeal per-feature.

```
INF-01: Service-to-service authentication [BE]                  [ ]
  Scope: Standardize internal endpoint auth across all services.
  Current state:
    - provider-registry + chat-service: have X-Internal-Token check (partial)
    - book-service, sharing-service, catalog-service, translation-service:
      /internal/* endpoints have NO auth — rely on Docker network isolation
  Plan:
    - Design shared middleware: validate X-Internal-Token header
    - Go services: chi middleware that checks header against config
    - Python services: FastAPI dependency that checks header
    - Apply to ALL /internal/* endpoints across 6 services
    - Update all internal HTTP callers to send token
  Acceptance:
    - All /internal/* endpoints reject requests without valid token
    - All service-to-service calls include X-Internal-Token header
    - Existing integration tests still pass
  Size: M

INF-02: Internal HTTP client with timeout + retry [BE]          [ ]
  Scope: Replace raw http.Get() with shared client across all Go services.
  Current state:
    - 20+ http.Get() calls with no timeout across catalog, book, sharing services
    - If downstream service hangs, caller blocks indefinitely
  Plan:
    - Create shared httputil package (or per-service helper):
      - Default timeout: 10s
      - 1 retry with 500ms backoff
      - Response body size limit (10MB)
      - Context propagation from request
    - Replace all http.Get() calls in:
      catalog-service (5 calls), book-service (2 calls),
      translation-service (3 calls), provider-registry (adapter calls)
  Acceptance:
    - All internal HTTP calls have 10s timeout
    - Hanging downstream returns error within 10s, not indefinitely
    - Logs include caller context on timeout
  Size: M

INF-03: Structured logging [BE]                                 [ ]
  Scope: Replace log.Printf with structured JSON logging.
  Current state: plain text logs, inconsistent format across services.
  Plan:
    - Go: slog (stdlib) with JSON handler
    - Python: structlog or standard logging with JSON formatter
    - Common fields: service, request_id, user_id, duration
  Size: M

INF-04: Health check deep mode [BE]                             [ ]
  Scope: /health endpoints check DB connectivity, not just "process alive".
  Current state: all /health return "ok" without checking dependencies.
  Plan:
    - /health: basic (for Docker healthcheck, fast)
    - /health/ready: deep (checks DB pool, Redis, downstream services)
  Size: S
```

---

### Size Key: S = <1 session, M = 1-2 sessions, L = 2-4 sessions

### Updated Total: 172 tasks (was 168)

| Phase | FE | BE | FS | Total |
|---|---|---|---|---|
| Phase 1 | 11 | 0 | 0 | 11 |
| Phase 2 | 13 | 2 | 1 | 16 |
| **Phase 2.5** | **9** | **0** | **3** | **12** |
| Phase 3 | 16 | 5 | 3 | 24 |
| **Phase 3.5** | **8** | **0** | **4** | **12** |
| Phase 4 | 11 | 3 | 0 | 14 |
| **Phase 4.5** | **4** | **0** | **3** | **7** |
| Phase 5 | 4 | 1 | 5 | 10 |
| **Phase 6 (Chat)** | **11** | **0** | **5** | **16** |
| **Phase 7 (Infra)** | **0** | **4** | **0** | **4** |
| **Video Gen** | **2** | **7** | **1** | **10** |
| **Media Versions** | **2** | **5** | **0** | **7** |
| **V1→V2 Migration** | **10** | **0** | **0** | **10** |
| **Version History Polish** | **10** | **0** | **2** | **12** |
