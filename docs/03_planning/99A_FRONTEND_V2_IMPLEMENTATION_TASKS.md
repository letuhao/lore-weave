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

Deferred glossary items (needs backend or P3-08):
  Backend required:
  [ ] P3-R1-D6: Attribute active toggle (is_active column, on/off per attr) [BE+FE]
  [ ] P3-R1-D7: Kind + attribute modified tracking (compare vs seed defaults, show "modified" badge) [BE+FE]
  [ ] P3-R1-D8: Revert to default — per-kind and per-attribute (restore to seed value) [BE+FE]
  [ ] P3-R1-D10: Relationship field type (entity references with role labels) [BE+FE]
  [ ] P3-R1-D17: Kind description field — add to EntityKind domain type + listKinds query [BE+FE]
  [ ] P3-R1-D18: Entity count per kind — aggregate in listKinds or separate endpoint [BE+FE]

  Frontend only:
  [ ] P3-R1-D9: Drag-to-reorder kinds + attributes (update sort_order via PATCH) [FE]
  [ ] P3-R1-D19: "System" / "Custom" badge on kind list items (currently only section headers) [FE]
  [ ] P3-R1-D20: Kind metadata row — show Display Name, Internal ID, Entities, Description [FE]
  [ ] P3-R1-D21: Inline edit button (pencil) per attribute row [FE]
  [ ] P3-R1-D22: "required" / "optional" text label per attribute (not just badge) [FE]

  Needs P3-08a (Genre Groups):
  [ ] P3-R1-D11: Genre badge on attributes ("Fantasy only")
  [ ] P3-R1-D12: Genre badge in entity editor header
  [ ] P3-R1-D13: Attribute deactivation per genre (dimmed + strikethrough)

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

### Glossary — Genre Groups (requires backend extension)
```
P3-08a: Genre Groups — Backend [BE]
  Scope: Extend glossary-service with genre group tables + endpoints
  New DB tables (in loreweave_glossary):
    - genre_groups (id, book_id, name, color, sort_order, is_active, created_at)
    - genre_attribute_activations (genre_group_id, attribute_definition_id, is_active)
  New endpoints:
    - GET    /v1/books/{book_id}/glossary/genres
    - POST   /v1/books/{book_id}/glossary/genres
    - PATCH  /v1/books/{book_id}/glossary/genres/{genre_id}
    - DELETE /v1/books/{book_id}/glossary/genres/{genre_id}
    - GET    /v1/books/{book_id}/glossary/genres/{genre_id}/activations
    - PUT    /v1/books/{book_id}/glossary/genres/{genre_id}/activations
  AC:
    - [ ] Genre CRUD with color + sort order
    - [ ] Activation matrix: toggle attributes per genre
    - [ ] Active genre filters entity form (hide inactive attributes)

P3-08b: Genre Group Editor — Frontend [FE]
  Deps: P3-08a
  AC:
    - [ ] Genre list panel + activation matrix table
    - [ ] Toggle switches per attribute per genre
    - [ ] Compare view across genres
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
P4-04: Settings — Reading Preferences [FE]
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
  P3-08a (genre backend) → P3-08b (genre FE)
  P3-01...P3-04 (translation FE — no backend needed)
  P3-05...P3-07 (glossary FE — no backend needed)
  P3-18, P3-19 (chat FE — no backend needed)
```

### Parallelizable Work

```
Can run simultaneously:
  Backend: P2-09b + P2-11b + P3-09 + P3-15a + P3-17a + P3-08a
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
6. P3-08a  Genre groups (blocks genre editor)
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

### Size Key: S = <1 session, M = 1-2 sessions, L = 2-4 sessions

### Updated Total: 135 tasks (was 123)

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
| **Video Gen** | **2** | **7** | **1** | **10** |
| **Media Versions** | **2** | **5** | **0** | **7** |
| **Version History Polish** | **10** | **0** | **2** | **12** |
