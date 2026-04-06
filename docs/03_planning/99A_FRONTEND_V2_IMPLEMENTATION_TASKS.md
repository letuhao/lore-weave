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
  Status: [✓] Done (96fd331 — 67/67 tests)
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
  Status: [✓] Done (eeafec7)
  Update: KindEditor.tsx — description textarea, entity count in sidebar + detail header
  AC:
    - [x] Description textarea in kind edit form (editable, saves via PATCH)
    - [x] Entity count shown in kind detail header (e.g. "12 attrs · 45 entities")
    - [x] Entity count shown in kind list sidebar items

FE-KE-02: Attribute inline edit modal [FE]
  Status: [✓] Done (6624e70)
  Update: KindEditor.tsx — pencil icon per attr row → inline edit form below row
  AC:
    - [x] Pencil icon on each attribute row (hover reveal)
    - [x] Click opens inline edit form (name, type, required, description, genre_tags)
    - [x] Save PATCHes the attribute, reloads kind
    - [x] System attributes editable (name customization allowed)

FE-KE-03: Attribute toggle on/off [FE]
  Status: [✓] Done (b28925d)
  Update: KindEditor.tsx — CSS toggle switch per attribute row
  AC:
    - [x] Toggle switch shown per attribute (green=active, muted=inactive)
    - [x] Toggle sends PATCH with is_active: true/false
    - [x] Inactive attributes shown with reduced opacity + strikethrough name

FE-KE-04: Drag-to-reorder kinds [FE]
  Status: [✓] Done (63d6b04)
  Update: KindEditor.tsx — native HTML drag-and-drop (no library needed)
  AC:
    - [x] GripVertical drag handles on kind list rows (hover reveal)
    - [x] Drag-and-drop reorders with drop indicator border
    - [x] On drop, calls PATCH /v1/glossary/kinds/reorder
    - [x] Optimistic UI update, revert on error

FE-KE-05: Drag-to-reorder attributes [FE]
  Status: [✓] Done (cb41f1e)
  Update: KindEditor.tsx — same native drag pattern on attr rows
  AC:
    - [x] GripVertical drag handles on attribute rows
    - [x] On drop, calls PATCH /v1/glossary/kinds/:kindId/attributes/reorder
    - [x] Reloads kind data after reorder

FE-KE-06: Genre-colored dots on tag pills [FE]
  Status: [✓] Done (88cfadf)
  Update: KindEditor.tsx — fetch genre_groups, build color map, colored dot + per-genre styling
  AC:
    - [x] Genre tag pills show small colored square/dot before genre name
    - [x] Color sourced from genre_groups API (fallback: default violet)
    - [x] Kind-level genre tags also use genre colors (review fix 042f4e1)

FE-KE-07: Modified indicator + Revert to default [FE]
  Status: [✓] Done (c204d1a)
  New file: seedDefaults.ts — 12 seed kinds mirrored from Go DefaultKinds
  AC:
    - [x] "modified" badge on system kinds/attrs that differ from seed defaults
    - [x] "Revert to Default" button per kind (resets name, icon, color, attr names)
    - [x] Confirm dialog before revert
    - [x] Review fix: parallel attr PATCHes via Promise.allSettled (042f4e1)
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
P4-04: Reading & Theme Unification [FS] ⚠️ BIG REFACTOR — full-stack, BE-first
  Deps: P2-08 (ReaderThemeProvider), MIG-05 (ReadingTab)
  Design draft: screen-theme-customizer.html

  ── Problem Statement ─────────────────────────────────────────────────────

  Current state has 3 disconnected theme systems:
  1. index.css :root — warm literary theme (hardcoded, no toggle)
  2. ReaderThemeProvider — 6 reader presets (localStorage, no UI to select)
  3. ReadingTab (Settings) — 3 themes + 3 fonts (separate localStorage, not wired)

  Goal: Unified theme system where:
  - App UI supports dark/light/custom modes (affects sidebar, cards, all pages)
  - Reader has its own theme layer (presets + custom overrides)
  - Preferences persist to DB (not just localStorage)
  - Settings and Reader customizer are in sync
  - Existing warm theme = "Dark" preset (default)

  ── Strategy ──────────────────────────────────────────────────────────────

  Phase A: Backend (user_preferences table + API)
  Phase B: Theme provider refactor (unified state, CSS variable system)
  Phase C: Reader integration (toolbar customizer, preview)
  Phase D: Settings UI (ReadingTab rewrite with live preview)

  All backend first, then frontend in order B → C → D.

  ── Backend Tasks ─────────────────────────────────────────────────────────

  BE-TH-01: user_preferences table + CRUD API [BE]
    Status: [ ]
    Service: auth-service (owns user data)
    DB:
      CREATE TABLE IF NOT EXISTS user_preferences (
        user_id    UUID PRIMARY KEY REFERENCES users(id),
        prefs      JSONB NOT NULL DEFAULT '{}',
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
      );
    Endpoints:
      GET  /v1/me/preferences — returns { prefs: {...} }
      PATCH /v1/me/preferences — merge-patch prefs JSONB, returns updated
    JSONB structure (typed on FE, flexible on BE):
      {
        "app_theme": "dark" | "light" | "sepia" | "oled",
        "reader_preset": "dark" | "sepia" | "light" | "oled" | "parchment" | "forest",
        "reader_font": "Lora" | "Inter" | "Noto Serif JP" | "system-ui",
        "reader_font_size": 16,
        "reader_line_height": 1.8,
        "reader_max_width": 680,
        "reader_spacing": 1.2
      }
    AC:
      - [ ] GET returns {} for new users (empty = use defaults)
      - [ ] PATCH merges (not replaces) — can update one field without losing others
      - [ ] Auth required (JWT user_id)
      - [ ] Integration tests

  BE-TH-02: Gateway proxy for /v1/me/preferences [BE]
    Status: [ ]
    Service: api-gateway-bff
    Changes: Add proxy route for /v1/me/preferences → auth-service
    AC:
      - [ ] GET/PATCH /v1/me/preferences routed through gateway
      - [ ] Auth header forwarded

  ── Frontend Tasks ────────────────────────────────────────────────────────

  FE-TH-01: App theme system — CSS variable swapping [FE]
    Status: [ ]
    Scope: Support dark/light/sepia/oled modes for the ENTIRE app UI (not just reader)
    Changes:
      - index.css: define 4 theme presets as CSS variable sets
        :root (dark — current warm theme, default)
        [data-theme="light"] { --background: ...; --foreground: ...; ... }
        [data-theme="sepia"] { --background: ...; ... }
        [data-theme="oled"] { --background: ...; ... }
      - Add data-theme attribute to <html> element
      - All existing Tailwind classes (bg-background, text-foreground, etc.) automatically
        pick up the new values — NO component changes needed for basic theme support
    AC:
      - [ ] 4 app themes defined as CSS variable overrides
      - [ ] data-theme on <html> switches entire app appearance
      - [ ] All existing pages render correctly in all 4 themes
      - [ ] No component code changes needed (CSS variables do the work)

  FE-TH-02: Unified ThemeProvider — replace ReaderThemeProvider [FE]
    Status: [ ]
    Scope: New ThemeProvider that manages BOTH app theme + reader theme
    Changes:
      - New providers/ThemeProvider.tsx replaces ReaderThemeProvider.tsx
      - State shape: { appTheme, readerPreset, readerOverrides }
      - On mount: load from API (GET /v1/me/preferences), fallback to localStorage
      - On change: save to API (PATCH), update localStorage cache
      - Expose hooks: useAppTheme(), useReaderTheme()
      - useAppTheme() → sets data-theme on <html>
      - useReaderTheme() → returns CSS variables for reader content
    AC:
      - [ ] ThemeProvider replaces ReaderThemeProvider in App.tsx
      - [ ] App theme changes reflect instantly across all pages
      - [ ] Reader theme changes reflected in reader content
      - [ ] Preferences persisted to API on change
      - [ ] Graceful fallback when API unavailable (use localStorage)
      - [ ] Migration: read old lw_reader_theme + lw_reading_prefs localStorage keys

  FE-TH-03: Theme toggle in sidebar/navbar [FE]
    Status: [ ]
    Scope: Quick theme switcher accessible from main navigation
    Changes:
      - Add theme toggle button to AppNav/sidebar (sun/moon icon)
      - Click cycles: dark → light → sepia → dark
      - Long-press or dropdown for full theme list
    AC:
      - [ ] Theme toggle visible in sidebar
      - [ ] Instant visual feedback on click
      - [ ] Current theme persisted

  FE-TH-04: Reader toolbar theme customizer [FE]
    Status: [ ]
    Scope: Inline customizer panel in ReaderPage toolbar
    Design: screen-theme-customizer.html
    Changes:
      - ReaderPage.tsx: add toolbar button "Aa" that opens customizer panel
      - CustomizerPanel component: preset selector, font picker, size slider,
        line-height slider, width selector, spacing selector
      - Live preview: changes apply instantly to reader content below
      - Saves via ThemeProvider (auto-persists to API)
    AC:
      - [ ] "Aa" button in reader toolbar opens customizer
      - [ ] 6 reader presets with visual swatches
      - [ ] Font family picker (Lora, Inter, Noto Serif JP, Noto Serif TC, system)
      - [ ] Font size slider (12-28px)
      - [ ] Line height slider (1.4-2.2)
      - [ ] Max width selector (Narrow/Medium/Wide/Full)
      - [ ] Changes apply instantly to reader content
      - [ ] Panel dismissable (click outside, Esc)

  FE-TH-05: ReaderPage theme integration [FE]
    Status: [ ]
    Scope: Wire ReaderPage to use reader theme CSS variables
    Changes:
      - ReaderPage.tsx: apply --reader-* CSS variables to content area
      - Chapter content uses reader theme (bg, fg, font, size, spacing)
      - Toolbar and navigation keep app theme (sidebar colors)
      - Reader can have different theme from app (e.g., app=dark, reader=sepia)
    AC:
      - [ ] Reader content styled by reader theme variables
      - [ ] App chrome (toolbar, nav) unaffected by reader theme
      - [ ] Different app + reader theme combinations work correctly

  FE-TH-06: Settings ReadingTab rewrite [FE]
    Status: [ ]
    Scope: Replace current ReadingTab with unified theme settings
    Changes:
      - Remove old ReadingTab (standalone localStorage)
      - New ReadingTab sections:
        1. App Theme: 4 preset cards (dark/light/sepia/oled) with live preview
        2. Reader Theme: 6 preset cards + custom overrides
        3. Reader Typography: font family, size, line height, width, spacing
      - Live preview panel showing sample reader text with current settings
      - All changes go through ThemeProvider → API persistence
    AC:
      - [ ] App theme selector with 4 presets + instant preview
      - [ ] Reader theme selector with 6 presets
      - [ ] Typography controls with live preview
      - [ ] Changes sync with reader customizer (same ThemeProvider)
      - [ ] Old localStorage keys migrated on first load

  FE-TH-07: CSS cleanup + theme audit [FE]
    Status: [ ]
    Scope: Audit all pages for hardcoded colors, ensure theme compatibility
    Changes:
      - Grep for hardcoded hex colors in JSX (e.g., style={{ color: '#xxx' }})
      - Replace with CSS variables or Tailwind theme tokens
      - Verify all pages in light/sepia/oled modes (not just dark)
      - Fix any contrast or visibility issues
    AC:
      - [ ] No hardcoded colors in component styles (or documented exceptions)
      - [ ] All 4 app themes pass visual review on key pages
      - [ ] Chat, Editor, Browse, Usage pages verified

  ── Impact Areas (refactor scope) ─────────────────────────────────────────

  | Area | What changes |
  |------|-------------|
  | index.css | 4 theme presets as CSS variable overrides |
  | providers/ | ThemeProvider replaces ReaderThemeProvider |
  | App.tsx | ThemeProvider wrapping, remove old providers |
  | AppNav / Sidebar | Theme toggle button |
  | ReaderPage | Toolbar customizer, content theme variables |
  | Settings/ReadingTab | Full rewrite |
  | All pages | CSS audit for hardcoded colors |
  | auth-service | user_preferences table + CRUD |
  | gateway | Proxy route for preferences |

  ── Task Order ────────────────────────────────────────────────────────────

  BE-TH-01 → BE-TH-02 → FE-TH-01 → FE-TH-02 → FE-TH-03 → FE-TH-06 → FE-TH-07
  Then when reader page is refactored: FE-TH-05 → FE-TH-04

  BE first, then CSS presets, then provider, then sidebar toggle, then Settings UI, then audit.
  FE-TH-04 + FE-TH-05 (reader customizer + integration) deferred until reader page refactor.

  ── Future Theme Editor Improvements (deferred) ──────────────────────────

  These are enhancements to the theme system that aren't needed now but should be
  planned when the reader page is refactored or when user feedback demands them.

  App Theme Customization:
    [ ] TH-F01: Custom app theme — color pickers for background, foreground, primary, accent
         Currently: only 4 fixed presets. Future: "Custom" option with full color editor.
         Impact: index.css needs dynamic CSS variable injection, not just data-theme presets.
    [ ] TH-F02: App theme scheduling — auto-switch between light (day) and dark (night) by time
    [ ] TH-F03: System theme sync — follow OS dark/light preference via prefers-color-scheme

  Reader Theme Customization:
    [ ] TH-F04: Custom accent/link color in reader — highlight, selection, link colors
    [ ] TH-F05: Reader image brightness/contrast adjustment — dim images in dark themes
    [ ] TH-F06: Code block syntax theme — separate highlight.js theme per reader theme
    [ ] TH-F07: Reading progress bar color customization
    [ ] TH-F08: Custom CSS injection — power user textarea for arbitrary CSS overrides
    [ ] TH-F09: Per-book theme override — different books can have different reading themes
         Stored as book_preferences JSONB on book-service (separate from user_preferences)

  Typography:
    [ ] TH-F10: Google Fonts integration — paste URL to add custom web fonts
    [ ] TH-F11: Font weight selector (light/regular/medium/bold)
    [ ] TH-F12: Letter spacing control
    [ ] TH-F13: Text alignment (left/justify) toggle
    [ ] TH-F14: CJK-specific typography — ruby/furigana size, vertical text mode toggle
    [ ] TH-F15: RTL text direction support

  Preset Management:
    [ ] TH-F16: Theme import/export — download/upload custom preset as JSON file
    [ ] TH-F17: Theme sharing — share custom presets via shareable URL (needs social-service)
    [ ] TH-F18: Community theme gallery — browse and install presets from other users
    [ ] TH-F19: Preset preview on hover — show full live preview before applying

  Reader Integration (blocked on reader page refactor):
    [ ] FE-TH-04: Reader toolbar customizer — "Aa" button opens inline panel (deferred)
    [ ] FE-TH-05: Reader page theme wiring — apply --reader-* CSS vars to content (deferred)
    [ ] TH-F20: Scroll-based theme transition — gradual bg shift while reading (ambient mode)
    [ ] TH-F21: Focus mode — dim non-paragraph content, spotlight current paragraph
    [ ] TH-F22: Night shift — reduce blue light via CSS filter overlay

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
INF-01: Service-to-service authentication [BE]                  [✓] Done (03644b3)
  requireInternalToken chi middleware on all /internal/* routes (book, sharing,
  usage-billing, provider-registry). internalGet helper with token header on all
  callers (catalog 8 calls, sharing 3, book 2, glossary 2, provider-registry 1).
  InternalServiceToken added to all service configs + docker-compose.
  209/209 integration tests pass.

INF-02: Internal HTTP client with timeout + retry [BE]          [✓] Done (e02a1c9)
  var internalClient = &http.Client{Timeout: 10 * time.Second} in catalog,
  sharing, book services. 1 retry with 500ms backoff in internalGet helpers.
  Zero http.Get() and zero http.DefaultClient remaining in codebase.
  209/209 integration tests pass.

INF-03: Structured logging [BE]                                 [✓] Done (af1679d, da818cd)
  Replaced all 77 log.Printf/Println/Fatal with slog.Info/Error across 15 files
  in 8 Go services. JSON handler with "service" attribute in each main.go.
  Normalized "listening" messages across all services.
  209/209 integration tests pass.

INF-04: Health check deep mode [BE]                             [✓] Done (b670f7c)
  /health: pool.Ping (fast, Docker healthcheck). /health/ready: SELECT 1 (deep,
  returns JSON {"status":"ready"}). Both return 503 with error on failure.
  Nil-pool guard prevents panic in unit tests. 22 new integration tests.
  231/231 integration tests pass (209 existing + 22 new).
```

---

---

## Phase 8: Unified Content Viewer & Reader Rewrite

> **Problem:** Old ReaderPage uses TiptapEditor(editable=false) — loads full editor stack
> just to display content. ChapterReadView splits by \n\n — can't render structured data.
> Both are broken for mixed-media chapters (images, videos, code blocks, callouts).
>
> **Solution:** Lightweight display components (no Tiptap dependency) that render Tiptap JSON
> as pure React. Shared across reader, revision preview, translation review, and excerpts.
>
> **Design drafts:**
> - `design-drafts/screen-reader-v2-part1-renderer.html` — Block renderer + reader chrome
> - `design-drafts/screen-reader-v2-part2-audio-tts.html` — TTS / audio player
> - `design-drafts/screen-reader-v2-part3-review-modes.html` — Review modes
>
> **Phasing:**
>
> | Sub-phase | Scope | Deps |
> |-----------|-------|------|
> | **Phase 8A** | ContentRenderer + ReaderPage rewrite | None |
> | **Phase 8B** | Reader theme integration (FE-TH-04 + FE-TH-05) | 8A |
> | **Phase 8C** | RevisionHistory + ChapterReadView cleanup | 8A |
> | **Phase 8D** | Browser TTS (free, Web Speech API) | 8A |
> | **Phase 8E** | AI TTS with persisted audio (BE + FE) | 8D |
> | **Phase 8F** | Translation pipeline upgrade (TEXT → block JSONB) | 8A |
> | **Phase 8G** | Translation review mode (split-pane) | 8F |
>
> **Architecture decisions:**
> - Custom React display components, NOT Tiptap generateHTML() (avoids importing extensions)
> - Each block gets `data-block-id` for TTS sync, scroll targeting, click handling
> - ContentRenderer accepts `mode: 'full' | 'compact'` for reader vs embedded contexts
> - Reader theme via `--reader-*` CSS vars (already in ThemeProvider, just needs wiring)
> - AI TTS audio stored as persistent assets in DB + MinIO (not cache, never expires)
> - Audio segments store `source_text` (subtitle) + `source_text_hash` (change detection)
> - Translation review deferred until translation pipeline upgraded to block-level JSONB

---

### Phase 8A: ContentRenderer + ReaderPage Rewrite (12 tasks)

> **Goal:** Replace broken reader with lightweight display components.
> ReaderPage works for authenticated users with full structured content support.
> Public reader deferred (needs BE endpoints).

```
Task order:
  RD-00 → RD-01 → RD-02 → RD-03 → RD-04 → RD-05 → RD-06
  → RD-07 → RD-08 → RD-09 → RD-10 → RD-11 → RD-12
```

  RD-00: Install missing editor extensions [FE]
    Status: [✓]
    Size: S
    Scope: Add 5 Tiptap inline mark extensions to the editor
    Packages: @tiptap/extension-link, @tiptap/extension-underline,
      @tiptap/extension-highlight, @tiptap/extension-subscript,
      @tiptap/extension-superscript
    Files:
      frontend/package.json — add 5 deps
      frontend/src/components/editor/TiptapEditor.tsx — register extensions
      frontend/src/components/editor/FormatToolbar.tsx — add toolbar buttons
    Link config: openOnClick: false, HTMLAttributes: { target: '_blank', rel: 'noopener' }
    Toolbar: Link (chain icon, URL prompt), Underline (U), Highlight (highlighter),
      Subscript (X₂), Superscript (X²)
    AC:
      - [ ] All 5 extensions installed and registered in editor
      - [ ] Toolbar buttons toggle each mark
      - [ ] Link button prompts for URL, sets href + target + rel
      - [ ] Keyboard shortcuts: Ctrl+U (underline), Ctrl+Shift+H (highlight)
      - [ ] Existing content renders unchanged (marks are additive)
      - [ ] Build passes, no new warnings

  RD-01: InlineRenderer — text marks display [FE]
    Status: [✓]
    Size: S
    Deps: RD-00
    Scope: Component that renders Tiptap inline content (text nodes + marks)
    File: frontend/src/components/reader/InlineRenderer.tsx
    Input: TiptapNode[] (content array with type:"text", marks:[...])
    Handles 9 mark types (flat array, not nested — wrap in order):
      bold → <strong>, italic → <em>, strike → <s>, code → <code>,
      link → <a href target="_blank" rel="noopener">,
      underline → <u>, highlight → <mark>, subscript → <sub>, superscript → <sup>
    Also handles: hardBreak → <br />
    Unknown mark types → render text without mark (defensive, no crash)
    AC:
      - [ ] All 9 mark types render correctly
      - [ ] Stacked marks render (e.g., bold+italic = <strong><em>)
      - [ ] Links open in new tab with rel="noopener"
      - [ ] Inline code styled with monospace + subtle bg
      - [ ] Highlight styled with subtle background
      - [ ] Hard breaks (type:"hardBreak") render as <br>
      - [ ] Unknown mark types don't crash

  RD-02: Block display components — text types [FE]
    Status: [✓]
    Size: S
    Deps: RD-01
    Scope: Display components for text-based blocks
    Files:
      frontend/src/components/reader/blocks/ParagraphBlock.tsx
      frontend/src/components/reader/blocks/HeadingBlock.tsx
      frontend/src/components/reader/blocks/BlockquoteBlock.tsx
      frontend/src/components/reader/blocks/ListBlock.tsx
      frontend/src/components/reader/blocks/HorizontalRuleBlock.tsx
    Each takes TiptapNode props → renders HTML element + InlineRenderer for content
    HeadingBlock reads attrs.level for h1/h2/h3
    ListBlock handles bulletList + orderedList (recursive for nested lists)
    HorizontalRuleBlock renders three-dot scene break
    AC:
      - [ ] All 5 text block types render correctly
      - [ ] Heading levels produce correct h1/h2/h3 tags
      - [ ] Nested lists render properly
      - [ ] Styling uses --reader-* CSS variables

  RD-03: Block display components — media types [FE]
    Status: [✓]
    Size: S
    Deps: RD-01
    Scope: Display components for media blocks
    Files:
      frontend/src/components/reader/blocks/ImageBlock.tsx
      frontend/src/components/reader/blocks/VideoBlock.tsx
      frontend/src/components/reader/blocks/CodeBlock.tsx
      frontend/src/components/reader/blocks/CalloutBlock.tsx
    ImageBlock: <figure> with <img> + <figcaption>, zoom-hint overlay, lazy loading
    VideoBlock: <figure> with <video> + play button overlay + <figcaption>
    CodeBlock: language header + copy button + <pre> (no syntax highlighting — defer)
    CalloutBlock: colored left border + label + content (type from attrs)
    AC:
      - [ ] Images lazy-load with IntersectionObserver
      - [ ] Video shows poster/placeholder, plays on click
      - [ ] Code block copy button copies to clipboard
      - [ ] Callout types (info, warning, success, danger) show correct colors

  RD-04: ContentRenderer — block orchestrator [FE]
    Status: [✓]
    Size: S
    Deps: RD-02, RD-03
    Scope: Main component that maps Tiptap JSON blocks to display components
    File: frontend/src/components/reader/ContentRenderer.tsx
    Props:
      blocks: TiptapBlock[]         // doc.content array
      mode?: 'full' | 'compact'    // sizing mode
      ttsActiveBlock?: string      // highlight block (future TTS)
      showIndices?: boolean        // block numbers (translator mode)
      maxBlocks?: number           // limit for embedded preview
      onBlockClick?: (blockId: string) => void
      className?: string
    Renders each block wrapped in <div data-block-id="block-{index}">
    Switch on block.type → render appropriate display component
    Unknown block types → fallback <pre>{JSON.stringify(block)}</pre>
    AC:
      - [ ] All block types from RD-02 + RD-03 render correctly
      - [ ] data-block-id on every block wrapper
      - [ ] compact mode applies smaller sizing
      - [ ] maxBlocks truncates with gradient fade
      - [ ] ttsActiveBlock adds highlight class
      - [ ] Unknown block type shows debug fallback (not crash)

  RD-05: ContentRenderer CSS — reader styles [FE]
    Status: [✓]
    Size: S
    Deps: RD-04
    Scope: CSS for all block types in reader context
    File: frontend/src/components/reader/reader.css (or co-located)
    Styles from design draft: .content-block, .block-paragraph, .block-heading,
    .block-image, .block-video, .block-code, .block-callout, .block-hr, etc.
    All sizing via --reader-* CSS vars (font, size, line-height, width, spacing)
    Full mode: generous spacing, large images
    Compact mode: tighter spacing, thumbnail images, smaller text
    TTS active state: gold left border + subtle background
    AC:
      - [ ] Full mode matches design draft visual fidelity
      - [ ] Compact mode visually distinct (smaller, tighter)
      - [ ] All sizing responds to --reader-* CSS variable changes
      - [ ] TTS highlight class styled correctly
      - [ ] Dark theme + sepia theme both render well

  RD-06: ReaderPage rewrite — basic structure [FE]
    Status: [✓]
    Size: S
    Deps: RD-04, RD-05
    Scope: Rewrite ReaderPage.tsx to use ContentRenderer instead of TiptapEditor
    File: frontend/src/pages/ReaderPage.tsx (rewrite)
    Changes:
      - Remove TiptapEditor import and usage
      - Fetch chapter draft via booksApi.getDraft()
      - Extract body.content → pass to ContentRenderer
      - Keep existing: progress bar, top bar breadcrumb, loading state
      - Keep existing: chapter prev/next navigation (bottom bar)
      - Remove: tiptap-reader CSS class usage
    AC:
      - [ ] ReaderPage renders structured content (paragraphs, images, code, etc.)
      - [ ] No Tiptap dependency imported
      - [ ] Progress bar works
      - [ ] Chapter navigation (prev/next) works
      - [ ] Loading state shows correctly

  RD-07: ReaderPage — chapter header + end marker [FE]
    Status: [✓]
    Size: S
    Deps: RD-06
    Scope: Chapter header (number, title, metadata) and end-of-chapter marker
    Changes to ReaderPage.tsx:
      - Chapter header: number label, title, amber divider, word count, reading time, language
      - Reading time: character-based for CJK, word-based for Latin
      - End marker: "End of Chapter N" with top border
    AC:
      - [ ] Chapter header shows number, title, divider
      - [ ] Metadata shows word count + reading time + language
      - [ ] CJK chapters use character count for reading time
      - [ ] End marker visible after content

  RD-08: ReaderPage — TOC sidebar [FE]
    Status: [✓]
    Size: S
    Deps: RD-06
    Scope: Table of contents slide-in overlay (matches existing design)
    File: frontend/src/components/reader/TOCSidebar.tsx
    Features:
      - Hamburger button in top bar opens TOC
      - Chapter list with current chapter highlighted
      - Read chapters show checkmark
      - Reading progress bar in header
      - Book title + chapter count
      - Click chapter → navigate (close TOC)
      - Click overlay backdrop → close
    AC:
      - [ ] TOC opens/closes on hamburger click
      - [ ] Current chapter highlighted with gold left border
      - [ ] Read chapters show green checkmark
      - [ ] Progress bar shows reading position
      - [ ] Navigation to other chapters works

  RD-09: ReaderPage — language selector in TOC [FE]
    Status: [✓]
    Size: S
    Deps: RD-08
    Scope: Language pills in TOC footer for switching reading language
    Changes: TOCSidebar.tsx footer section
    Data flow:
      - Fetch available translations for this chapter
        (GET /v1/translation/chapters/{id}/translations → list of languages)
      - Show pill per language (original highlighted differently)
      - On select: reload content in that language
      - Currently translations are flat TEXT — ContentRenderer falls back to
        wrapping in a single paragraph block. This is intentional until Phase 8F
        upgrades translations to block-level JSONB.
    AC:
      - [ ] Language pills shown in TOC footer
      - [ ] Original language visually distinct (gold pill)
      - [ ] Clicking translation language reloads content
      - [ ] Flat text translations render as paragraphs (split by \n\n)
      - [ ] Graceful handling when no translations exist

  RD-10: ReaderPage — top bar actions [FE]
    Status: [✓]
    Size: S
    Deps: RD-06
    Scope: Top bar action buttons (theme, edit, close)
    Changes to ReaderPage.tsx top bar:
      - Theme button (placeholder — opens ThemeCustomizer in Phase 8B)
      - TTS button (placeholder — wired in Phase 8D)
      - Edit button (link to /edit, shown only if authenticated + owner)
      - Close button (back to book detail page)
    AC:
      - [ ] Theme + TTS buttons visible but inactive (placeholder for future phases)
      - [ ] Edit button shown only for authenticated book owner
      - [ ] Close button navigates back to book detail

  RD-11: ReaderPage — keyboard shortcuts [FE]
    Status: [✓]
    Size: S
    Deps: RD-06, RD-08
    Scope: Keyboard navigation for reader
    Shortcuts:
      - Left arrow / PageUp → previous chapter
      - Right arrow / PageDown → next chapter
      - T → toggle TOC sidebar
      - Escape → close TOC / close reader (back to book)
      - Home → scroll to top
      - End → scroll to bottom
    AC:
      - [ ] All shortcuts work in reader view
      - [ ] Shortcuts don't fire when TOC is open (except Escape to close)
      - [ ] No conflict with browser defaults

  RD-12: Integration test + cleanup [FE]
    Status: [✓]
    Size: S
    Deps: RD-06..RD-11
    Scope: Verify full reader flow, clean up old CSS
    Changes:
      - Remove .tiptap-reader CSS rules from index.css
      - Verify reader works with all block types (create test chapter with all types)
      - Verify chapter navigation cycle (first → last → first)
      - Verify reader loads without Tiptap in bundle (check import graph)
      - Browser test: dark theme renders correctly
    AC:
      - [ ] Old .tiptap-reader CSS removed
      - [ ] Reader renders chapter with all block types
      - [ ] Chapter navigation works end-to-end
      - [ ] No Tiptap imports in reader page bundle
      - [ ] Visual regression check passes

---

### Phase 8B: Reader Theme Integration (3 tasks)

> **Goal:** Wire FE-TH-04 + FE-TH-05 — reader uses theme CSS vars + toolbar customizer.
> **Deps:** Phase 8A complete

  RD-13: ReaderPage theme wiring (= FE-TH-05) [FE]
    Status: [ ]
    Size: S
    Deps: RD-06
    Scope: Apply --reader-* CSS vars to content area
    Changes:
      - Reading area container gets reader theme CSS vars from useReaderTheme()
      - Content uses reader theme (bg, fg, font, size, spacing)
      - Chrome (top bar, bottom bar) keeps app theme
      - Reader can have different theme from app (e.g., app=dark, reader=sepia)
    AC:
      - [ ] Reader content styled by reader theme
      - [ ] App chrome unaffected by reader theme
      - [ ] Theme changes from Settings reflect in reader

  RD-14: ThemeCustomizer slide-over (= FE-TH-04) [FE]
    Status: [ ]
    Size: M
    Deps: RD-13
    Scope: Slide-over panel opened from reader top bar theme button
    File: frontend/src/components/reader/ThemeCustomizer.tsx
    Sections: theme presets (5), font picker (5 fonts), font size slider,
    line height slider, text width slider, spacing slider
    Live preview: changes apply instantly to reader content
    Saves via ThemeProvider (persists to API)
    AC:
      - [ ] Opens from theme button in reader top bar
      - [ ] 5 presets with swatches (dark, light, sepia, oled, forest)
      - [ ] Font picker with sample text preview
      - [ ] Typography sliders with live preview
      - [ ] Changes persist via ThemeProvider
      - [ ] Dismissable (click outside, Escape)

  RD-15: Reading mode toggles [FE]
    Status: [ ]
    Size: S
    Deps: RD-14
    Scope: Additional settings in ThemeCustomizer
    Toggles:
      - Show block indices (translator mode) → sets showIndices on ContentRenderer
      - Auto-load next chapter (infinite scroll — placeholder, not wired)
    AC:
      - [ ] Block indices toggle works (shows/hides block numbers)
      - [ ] Settings persist in ThemeProvider

---

### Phase 8C: RevisionHistory + Cleanup (2 tasks)

> **Goal:** Update RevisionHistory to use ContentRenderer, delete ChapterReadView.
> **Deps:** Phase 8A complete

  RD-16: RevisionHistory — use ContentRenderer [FE]
    Status: [ ]
    Size: S
    Deps: RD-04
    Scope: Replace ChapterReadView in RevisionHistory with ContentRenderer(compact)
    File: frontend/src/components/editor/RevisionHistory.tsx
    Changes:
      - Import ContentRenderer instead of ChapterReadView
      - Revision body is Tiptap JSON → pass body.content to ContentRenderer
      - If revision body is plain text (old format) → wrap in paragraph blocks
      - mode="compact" for panel sizing
    AC:
      - [ ] Revision preview shows structured content (images, code, etc.)
      - [ ] Old plain-text revisions still render (wrapped in paragraphs)
      - [ ] Compact mode fits in editor right panel

  RD-17: Delete ChapterReadView [FE]
    Status: [ ]
    Size: S
    Deps: RD-16
    Scope: Remove dead code
    Delete: frontend/src/components/shared/ChapterReadView.tsx
    Remove all imports/references
    AC:
      - [ ] File deleted
      - [ ] No remaining imports
      - [ ] Build passes

---

### Phase 8D: Unified Audio System (24 tasks — replaces old 8D+8E)

> **Goal:** Complete audio system — audio attachments on text blocks, standalone
> audioBlock, unified playback engine with source priority, AI TTS generation.
> **Design draft:** `design-drafts/screen-reader-v2-part4-audio-blocks.html`
> **Strategy:** All BE first (no FE blockers), then editor, reader, playback, settings.
>
> **Task order:**
> ```
> BE: AU-01 → AU-02 → AU-03 → AU-04 → AU-05
> Editor: AU-06 → AU-07 → AU-08 → AU-09 → AU-10
> Reader display: AU-11 → AU-12 → AU-13
> Playback engine: AU-14 → AU-15 → AU-16 → AU-17
> Player UI: AU-18 → AU-19 → AU-20 → AU-21
> Settings: AU-22 → AU-23 → AU-24
> ```

  ── Backend (5 tasks) ────────────────────────────────────────────────────

  AU-01: BE — chapter_audio_segments table + CRUD [BE]
    Status: [✓]
    Size: S
    Service: book-service
    DB:
      CREATE TABLE chapter_audio_segments (
        segment_id UUID PRIMARY KEY,
        chapter_id UUID NOT NULL,
        block_index INT NOT NULL,
        source_text TEXT NOT NULL,
        source_text_hash VARCHAR(64) NOT NULL,
        voice TEXT NOT NULL,
        provider TEXT NOT NULL,
        language TEXT NOT NULL,
        media_key TEXT NOT NULL,
        duration_ms INT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
      );
      CREATE INDEX idx_audio_seg_lookup
        ON chapter_audio_segments(chapter_id, language, voice, block_index);
    Endpoints:
      GET  /v1/books/:bookId/chapters/:chapterId/audio?language=X&voice=Y
      GET  /v1/books/:bookId/chapters/:chapterId/audio/:segmentId
      DELETE /v1/books/:bookId/chapters/:chapterId/audio?language=X&voice=Y
    AC:
      - [ ] Table created via migration
      - [ ] GET list returns segments ordered by block_index (no source_text)
      - [ ] GET single includes source_text for subtitle display
      - [ ] DELETE removes DB rows + MinIO objects
      - [ ] Integration tests

  AU-02: BE — Audio upload endpoint (attach to block) [BE]
    Status: [✓]
    Size: S
    Deps: AU-01
    Service: book-service (reuses existing MinIO upload infrastructure)
    Endpoint:
      POST /v1/books/:bookId/chapters/:chapterId/block-audio
        multipart: file + block_index + subtitle (optional)
      → Upload to MinIO: audio/{chapterId}/attached/{block_index}_{uuid}.mp3
      → Return: { audio_url, media_key, duration_ms }
    Note: The FE writes audio_url/audio_key/audio_subtitle into block attrs
    and saves via normal patchDraft. No separate DB table for attached audio.
    AC:
      - [ ] File uploaded to MinIO with correct path
      - [ ] Duration extracted from audio file
      - [ ] Returns presigned URL for playback
      - [ ] Auth required (book owner)
      - [ ] Integration tests

  AU-03: BE — AI TTS generation endpoint [BE]
    Status: [✓]
    Size: M
    Deps: AU-01
    Service: book-service (calls provider-registry for AI credentials)
    Endpoint:
      POST /v1/books/:bookId/chapters/:chapterId/audio/generate
        { language, voice, provider, blocks: [{ index, text }] }
      Flow:
        1. Get provider credentials from provider-registry-service
        2. For each block: call AI TTS API (OpenAI / ElevenLabs)
        3. Upload each segment to MinIO
        4. Create chapter_audio_segments rows
        5. Track usage via usage-billing-service
        6. Return: { segments: [{ block_index, media_url, duration_ms }] }
    AC:
      - [ ] OpenAI TTS provider supported
      - [ ] Audio stored in MinIO with correct paths
      - [ ] DB rows created per segment
      - [ ] Usage recorded for billing
      - [ ] Partial failure: returns completed segments + errors
      - [ ] Integration tests

  AU-04: BE — Gateway proxy for audio endpoints [BE]
    Status: [✓]
    Size: S
    Deps: AU-01
    Service: api-gateway-bff
    Routes: /v1/books/:bookId/chapters/:chapterId/audio/* → book-service
            /v1/books/:bookId/chapters/:chapterId/block-audio → book-service
    AC:
      - [x] All audio endpoints proxied through gateway
      - [x] Auth header forwarded

  AU-05: BE — Audio integration tests [BE]
    Status: [✓]
    Size: S
    Deps: AU-01..AU-04
    File: infra/test-audio.sh
    Scenarios: upload, list, get single, delete, generate (mock or real provider),
    attach to block, verify MinIO objects exist/deleted
    AC:
      - [x] All endpoints tested (79 scenarios)
      - [x] All pass (79/79)

  ── Editor: audioBlock + audio attachment (5 tasks) ──────────────────────

  AU-06: audioBlock Tiptap extension [FE]
    Status: [✓]
    Size: M
    Scope: New Tiptap node type for standalone audio blocks
    File: frontend/src/components/editor/AudioBlockNode.tsx
    Attrs: src, media_key, subtitle, title, duration_ms, size_bytes
    Features:
      - Insert via slash menu (/audio)
      - NodeView: waveform player + subtitle input + upload/record buttons
      - Empty state: upload/record prompt
      - Plays audio in editor for preview
    AC:
      - [x] /audio in slash menu inserts audioBlock
      - [x] Upload stores file via AU-02 endpoint
      - [x] Player plays/pauses audio in editor
      - [x] Subtitle field editable
      - [x] Empty state shown when no src

  AU-07: Audio attachment attrs on text blocks [FE]
    Status: [✓]
    Size: S
    Deps: AU-06
    Scope: Extend paragraph/heading/blockquote/callout with audio attrs
    Changes:
      - Add attrs to StarterKit paragraph extension (or extension storage):
        audio_url, audio_key, audio_subtitle, audio_duration_ms, audio_source
      - Attrs are null by default (no visual change to existing blocks)
      - Saved normally via patchDraft (attrs persist in Tiptap JSON)
    AC:
      - [x] Audio attrs added to paragraph/heading nodes
      - [x] Null by default (existing content unaffected)
      - [x] Attrs survive save/load cycle

  AU-08: AudioAttachBar — mini player on text blocks [FE]
    Status: [✓]
    Size: S
    Deps: AU-07
    Scope: When a text block has audio_url, show mini player bar below text
    File: frontend/src/components/editor/AudioAttachBarExtension.ts
    Shows: play button, waveform, duration, source badge, mismatch indicator
    Replace/remove buttons
    AC:
      - [x] Bar appears when block has audio_url
      - [x] Play/pause audio
      - [x] Shows source badge (recorded/uploaded/AI)
      - [x] Mismatch warning when subtitle differs from text
      - [x] Replace and remove buttons work

  AU-09: AudioAttachActions — upload/record/generate [FE]
    Status: [✓]
    Size: M
    Deps: AU-07, AU-02
    Scope: Hover actions to attach audio to a text block
    File: frontend/src/components/editor/AudioAttachActionsExtension.ts
    Actions:
      - Upload: file picker → AU-02 endpoint → set audio attrs
      - Record: MediaRecorder API → AU-02 endpoint → set audio attrs
      - Generate AI: calls AU-03 → stores as attachment + segment
    AC:
      - [x] Upload button opens file picker, uploads, sets attrs
      - [x] Record button records via mic, uploads, sets attrs
      - [~] Generate button placeholder (full model selection in AU-22+)
      - [x] All update block attrs (audio_url, audio_subtitle, etc.)

  AU-10: Slash menu + FormatToolbar audio entries [FE]
    Status: [✓]
    Size: S
    Deps: AU-06
    Scope: Add audioBlock to slash menu and toolbar
    Changes:
      - SlashMenu.tsx: add /audio command (done in AU-06)
      - FormatToolbar.tsx: add audio insert button (AI mode only)
    AC:
      - [x] /audio in slash menu inserts audioBlock (AU-06)
      - [x] Audio button in toolbar (AI mode)

  ── Reader display (3 tasks) ─────────────────────────────────────────────

  AU-11: AudioBlock display component (reader) [FE]
    Status: [✓]
    Size: S
    Scope: Render standalone audioBlock in ContentRenderer
    File: frontend/src/components/reader/blocks/AudioBlock.tsx
    Renders: embedded player with waveform, play button, time, subtitle
    AC:
      - [x] Audio plays on click
      - [x] Subtitle shown below player
      - [x] Styled per design draft (purple accent)

  AU-12: Audio indicator on text blocks (reader) [FE]
    Status: [✓]
    Size: S
    Deps: AU-11
    Scope: Show play button on hover for text blocks with audio_url
    Changes to ContentRenderer.tsx:
      - Check block.attrs?.audio_url
      - Render inline play button on right side
      - Mismatch ⚠️ indicator when audio_subtitle differs from text
    AC:
      - [x] Play button appears on hover for blocks with audio
      - [x] Clicking plays attached audio
      - [x] Mismatch ⚠️ shown when subtitle differs
      - [x] No indicator on blocks without audio

  AU-13: Audio block + indicator CSS [FE]
    Status: [✓]
    Size: S
    Deps: AU-11, AU-12
    Scope: Reader CSS for audioBlock player, inline indicator, playing state
    File: frontend/src/components/reader/reader.css (extend)
    AC:
      - [x] AudioBlock styled with purple accent per design draft (AU-11)
      - [x] Inline play button positioned and styled
      - [x] Playing state highlight (purple left border)

  ── Playback engine (4 tasks) ────────────────────────────────────────────

  AU-14: TTSProvider context + playback interface [FE]
    Status: [✓]
    Size: M
    Scope: React context managing unified playback state
    File: frontend/src/hooks/useTTS.ts
    State: { status: idle|playing|paused, activeBlockId, source, speed, voice }
    Interface: play(), pause(), stop(), nextBlock(), prevBlock(), seekBlock(id)
    Source priority per block:
      1. block.attrs.audio_url → AudioFileEngine
      2. aiSegments[block_index] → AudioFileEngine
      3. text block → BrowserTTSEngine
      4. audioBlock → play inline, advance after
    AC:
      - [x] Context provides unified state + controls
      - [x] Source resolved per block based on priority
      - [x] Active block tracking works across source switches

  AU-15: AudioFileEngine — plays attached/AI audio [FE]
    Status: [✓]
    Size: S
    Deps: AU-14
    Scope: Engine that plays audio files via <audio> element
    File: frontend/src/hooks/engines/AudioFileEngine.ts
    Features:
      - Receives audio URL → creates <audio> element
      - Reports progress (currentTime / duration)
      - onEnd callback → advance to next block
      - Speed control via playbackRate
    AC:
      - [x] Plays audio URLs
      - [x] Reports progress
      - [x] Speed control works
      - [x] Calls onEnd when finished

  AU-16: BrowserTTSEngine — Web Speech API fallback [FE]
    Status: [✓]
    Size: S
    Deps: AU-14
    Scope: Engine that speaks text via SpeechSynthesisUtterance
    File: frontend/src/hooks/engines/BrowserTTSEngine.ts
    Features:
      - speak(text) → SpeechSynthesisUtterance
      - Voice selection from speechSynthesis.getVoices()
      - Speed control via rate property
      - onEnd callback → advance to next block
    AC:
      - [x] Speaks text blocks
      - [x] Voice list populated
      - [x] Speed control works
      - [x] Calls onEnd when finished

  AU-17: Block text extraction utility [FE]
    Status: [✓]
    Size: S
    Scope: Extract speakable text + audio source info per block
    File: frontend/src/lib/audio-utils.ts
    Functions:
      - extractSpeakableBlocks(blocks) → [{ blockId, text, audioUrl?, source }]
      - Skips: imageBlock, videoBlock, horizontalRule
      - audioBlock: returns { type: 'audio', src, subtitle }
      - Text blocks: returns { type: 'text', text, audioUrl?, audioSubtitle? }
    AC:
      - [x] Correctly categorizes all block types
      - [x] Extracts audio attachment info from attrs
      - [x] Returns ordered list for playback queue

  ── Player UI (4 tasks) ──────────────────────────────────────────────────

  AU-18: TTSBar floating player [FE]
    Status: [✓]
    Size: M
    Deps: AU-14
    Scope: Floating audio player bar above bottom navigation
    File: frontend/src/components/reader/TTSBar.tsx
    Shows: play/pause, block text preview, scrubber, time,
    prev/next block, speed button, source badge, close button
    Source-colored: purple (recorded), blue (AI), gray (browser)
    AC:
      - [x] Bar appears when playback activated
      - [x] Play/pause toggles correctly
      - [x] Source badge shows current audio source
      - [x] Block text updates with active block
      - [x] Scrubber shows progress (for audio file sources)
      - [x] Close button stops playback

  AU-19: Block scroll sync + highlight [FE]
    Status: [✓]
    Size: S
    Deps: AU-14
    Scope: Auto-scroll + highlight active block during playback
    File: frontend/src/hooks/useBlockScroll.ts
    Features:
      - scrollIntoView on block change
      - Purple left border highlight on playing block
      - Click any block → seekBlock(id)
    AC:
      - [x] Active block scrolls into view
      - [x] Active block highlighted (via tts-active class)
      - [x] Click-to-seek works

  AU-20: Playback keyboard shortcuts [FE]
    Status: [✓]
    Size: S
    Deps: AU-14, AU-18
    Shortcuts:
      - Space → play/pause (when playback active)
      - [ / ] → decrease/increase speed
      - Shift+Left / Shift+Right → prev/next block
      - Escape → close playback
    AC:
      - [x] All shortcuts work
      - [x] Space doesn't scroll page (preventDefault)
      - [x] Escape closes TTSBar

  AU-21: Wire into ReaderPage [FE]
    Status: [✓]
    Size: S
    Deps: AU-18, AU-19, AU-20
    Scope: Enable the Volume2 button, wrap reader in TTSProvider
    Changes to ReaderPage.tsx:
      - Volume2 button activates playback
      - Pass ttsActiveBlock to ContentRenderer
      - Pass onBlockClick for seek
      - Render TTSBar
    AC:
      - [x] Volume2 button starts playback
      - [x] TTSBar appears
      - [x] Block highlighting works
      - [x] Playback progresses through chapter

  ── Settings + Management (3 tasks) ──────────────────────────────────────

  AU-22: TTS settings panel [FE]
    Status: [✓]
    Size: S
    Deps: AU-18
    Scope: Settings panel opened from TTSBar gear icon
    File: frontend/src/components/reader/TTSSettings.tsx
    Sections: browser voice selector, speed/pitch sliders,
    behavior toggles (auto-scroll, highlight, pause on media),
    AI voice + provider selector, source priority display
    AC:
      - [x] Voice dropdown (browser voices)
      - [x] Speed buttons (6 presets)
      - [x] Behavior toggles persist to localStorage
      - [~] AI voice selector (placeholder — needs provider config)

  AU-23: Audio overview panel [FE]
    Status: [✓]
    Size: S
    Deps: AU-14
    Scope: Per-block audio status panel (accessible from ThemeCustomizer)
    File: frontend/src/components/reader/AudioOverview.tsx
    Shows: each block with status badge (recorded/AI/browser/none/mismatch)
    "Generate missing" bulk action button with cost estimate
    AC:
      - [x] Lists all blocks with audio status
      - [x] Badges match design draft (color-coded by source)
      - [x] "Generate missing" shows count + cost estimate

  AU-24: AI generation UI (progress + drift) [FE]
    Status: [✓]
    Size: M
    Deps: AU-22, AU-23
    Scope: Generation progress, cost estimate, saved audio card, drift detection
    Changes to TTSSettings + AudioOverview:
      - Generate button → progress bar with per-block dots
      - Saved audio card (green) when audio exists
      - Content drift warning (amber) when blocks changed since generation
      - Re-generate changed blocks only (partial update)
    AC:
      - [x] Cost estimate from block text lengths
      - [x] Generation progress with per-block dots (simulated)
      - [x] Saved audio card shows metadata
      - [~] Drift warning (placeholder — requires segment hash comparison)

---

### Phase 8E: AI Provider Capabilities + Media Generation (14 tasks)

> **Goal:** Add capability-based model classification (tts, image_gen, video_gen)
> to the provider registry, then wire image and video generation through the
> same BYOK provider pattern used by chat and TTS.
> **Design principle:** OpenAI-compatible API standards where they exist,
> provider adapter layer where they don't.
> **Deps:** Phase 8D (audio system provides the pattern), M03 (provider registry)

  ── Provider capability flags (3 tasks) ──────────────────────────────────

  PE-01: BE — Add capability flags to provider registry [BE]
    Status: [ ]
    Size: S
    Service: provider-registry-service
    Changes:
      - capability_flags JSONB already exists on user_models
      - Add migration: ensure known flags include tts, image_generation, video_generation
      - Expose capability_flags in list/get endpoints (already done)
      - Add ?capability=tts filter to listUserModels endpoint
    AC:
      - [ ] Filter by capability flag works
      - [ ] Existing models unaffected (flags default to {})

  PE-02: FE — Add media capabilities to CapabilityFlags UI [FE]
    Status: [ ]
    Size: S
    File: frontend/src/features/settings/CapabilityFlags.tsx
    Changes:
      - Add 'tts', 'image_generation', 'video_generation' to KNOWN_FLAGS
      - Model add/edit modal shows the new flags
    AC:
      - [ ] New flags visible in model editor
      - [ ] Flags persist on save

  PE-03: FE — Filter model selectors by capability [FE]
    Status: [ ]
    Size: S
    Changes:
      - TTSSettings: filter model dropdown to capability_flags.tts === true
      - Chat NewChatDialog: filter to models without media-only flags
      - Add capability_flags to aiModelsApi.UserModel type
    AC:
      - [ ] TTS settings only shows TTS-capable models
      - [ ] Chat model selector unchanged for non-media models

  ── Image generation (5 tasks) ───────────────────────────────────────────

  PE-04: BE — Image generation endpoint on book-service [BE]
    Status: [ ]
    Size: M
    Service: book-service
    Scope: OpenAI-compatible image generation via provider credentials
    Endpoint: POST /v1/books/{book_id}/chapters/{chapter_id}/generate-image
    Flow:
      1. Resolve provider creds via provider-registry (model_ref)
      2. Call {base_url}/v1/images/generations (OpenAI standard)
      3. Download result image → upload to MinIO
      4. Return { image_url, media_key, size_bytes }
      5. Record usage billing
    API standard: OpenAI /v1/images/generations
      - Request: { model, prompt, size, n, response_format }
      - Response: { data: [{ url }] } or { data: [{ b64_json }] }
    AC:
      - [ ] Resolves credentials from provider-registry
      - [ ] Calls OpenAI-compatible image API
      - [ ] Stores result in MinIO
      - [ ] Usage billing recorded
      - [ ] Returns image URL

  PE-05: BE — Image generation integration tests [BE]
    Status: [ ]
    Size: S
    File: infra/test-image-gen.sh
    AC:
      - [ ] Validation tests (missing fields, bad model)
      - [ ] Auth tests (401, 404 for other user)
      - [ ] All pass

  PE-06: FE — Wire image generation in editor [FE]
    Status: [ ]
    Size: S
    Deps: PE-04
    Changes:
      - ImageBlockNode MediaPrompt: call generate-image endpoint
      - Read image generation model from settings (new pref: imageModelId)
      - Replace current videoGenApi call pattern
    AC:
      - [ ] AI generate button calls real endpoint
      - [ ] Generated image appears in block
      - [ ] Model selected from TTS-style settings

  ── Video generation (4 tasks) ───────────────────────────────────────────

  PE-07: BE — Video generation provider adapter [BE]
    Status: [ ]
    Size: M
    Service: video-gen-service
    Scope: Connect skeleton to provider-registry + real provider APIs
    Changes:
      - Resolve provider credentials via provider-registry (same pattern as TTS)
      - Provider adapter layer:
        - OpenAI Sora: POST /v1/video/generations (if standardized)
        - Runway/Kling/Pika: per-provider adapter (async polling)
      - Store result in MinIO
      - Record usage billing
    AC:
      - [ ] Resolves credentials from provider-registry
      - [ ] At least one provider adapter works (OpenAI or mock)
      - [ ] Stores result in MinIO
      - [ ] Returns video URL

  PE-08: BE — Video generation integration tests [BE]
    Status: [ ]
    Size: S
    File: infra/test-video-gen.sh
    AC:
      - [ ] Validation + auth tests
      - [ ] All pass

  PE-09: FE — Wire video generation in editor [FE]
    Status: [ ]
    Size: S
    Deps: PE-07
    Changes:
      - VideoBlockNode: use provider-registry model instead of hardcoded
      - Add videoModelId to settings prefs
    AC:
      - [ ] AI generate button calls real endpoint with user's provider
      - [ ] Generated video appears in block

  ── Settings + preconfig (2 tasks) ───────────────────────────────────────

  PE-10: FE — Media generation settings in ReadingTab [FE]
    Status: [ ]
    Size: S
    Changes:
      - Add "AI Models" section to Settings > Reading tab (or new AI tab)
      - TTS model selector (from PE-03)
      - Image generation model selector
      - Video generation model selector
      - Default voice, image size, video duration prefs
    AC:
      - [ ] All three model selectors work
      - [ ] Prefs persist to localStorage or user_preferences

  PE-11: BE — Preconfig catalog for media models [BE]
    Status: [ ]
    Size: S
    Service: provider-registry-service
    Scope: Add TTS + image models to preconfig JSON catalogs
    Changes:
      - openai_models.json: add tts-1, tts-1-hd, dall-e-3, dall-e-2
      - Set capability_flags appropriately
    AC:
      - [ ] TTS and image models appear in Add Model autocomplete
      - [ ] Capability flags pre-set correctly

---

### Phase 8F: Translation Pipeline Upgrade (future — needs separate planning)

> **Goal:** Upgrade translation from flat TEXT to block-level JSONB.
> Preserves block structure, media references, and callout types.
> **Status:** Not broken down yet — needs its own planning session.
> **Key changes:**
> - translated_body: TEXT → JSONB (same Tiptap block structure)
> - Translation pipeline: chunk-based → block-by-block
> - Media blocks: translate caption only, keep asset references
> - Code blocks: keep as-is
> - Callouts: translate content, keep type

---

### Phase 8G: Translation Review Mode (future — needs Phase 8F)

> **Goal:** Split-pane block-aligned review mode for translations.
> **Status:** Not broken down yet — depends on Phase 8F data model.
> **Design draft:** screen-reader-v2-part3-review-modes.html

---

### Phase 8H: Reading Analytics & Progress Tracking (future)

> **Goal:** Backend-tracked reading progress, view counts, and reading time.
> Replaces the fake "read" checkmarks (index-based) with real per-user tracking.
> **Status:** Not broken down yet — needs its own planning session.
>
> **Backend (new table):**
> ```sql
> CREATE TABLE reading_progress (
>   user_id        UUID NOT NULL,
>   book_id        UUID NOT NULL,
>   chapter_id     UUID NOT NULL,
>   read_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
>   time_spent_ms  BIGINT DEFAULT 0,
>   scroll_depth   REAL DEFAULT 0,   -- 0.0 to 1.0
>   PRIMARY KEY (user_id, book_id, chapter_id)
> );
> CREATE TABLE book_views (
>   book_id     UUID NOT NULL,
>   user_id     UUID,               -- nullable for anonymous
>   viewed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
>   referrer    TEXT
> );
> ```
>
> **Key features:**
> - Track which chapters a user has actually read (not index-based guess)
> - Record time spent per chapter (for leaderboard, author analytics)
> - Record scroll depth (did they read the whole chapter or just the start?)
> - Book view counts (for catalog popularity, leaderboard)
> - Anonymous view tracking for public books
> - TOC sidebar shows real read/unread status per chapter
> - Author dashboard: reader engagement metrics
>
> **Deps:** None for backend. Frontend wiring depends on Phase 8A (reader).
> **Related:** Leaderboard page, Author analytics page, Browse page sorting by popularity.

---

### Phase 8 Summary

| Sub-phase | Tasks | FE | BE | Deps | Status |
|-----------|-------|----|----|------|--------|
| 8A: ContentRenderer + Reader | 13 | 13 | 0 | None | Done |
| 8B: Reader Theme | 3 | 3 | 0 | 8A | Done |
| 8C: RevisionHistory Cleanup | 2 | 2 | 0 | 8A | Done |
| 8D: Unified Audio System | 24 | 19 | 5 | 8A | Done |
| 8E: AI Provider + Media Gen | 11 | 4 | 7 | 8D, M03 | Planned |
| 8F: Translation Upgrade | TBD | — | — | 8A | Future |
| 8G: Translation Review | TBD | — | — | 8F | Future |
| 8H: Reading Analytics | TBD | — | — | 8A | Future |
| **Total (8A-8D)** | **42** | **37** | **5** | |

---

### Size Key: S = <1 session, M = 1-2 sessions, L = 2-4 sessions

### Updated Total: 202 tasks (was 172)

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
