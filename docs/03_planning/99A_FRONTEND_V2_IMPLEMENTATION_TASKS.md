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
Status: [ ]
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
Status: [ ]
Deps:   P1-02
Scope:  StatusBadge, ConfirmDialog, FormDialog, EmptyState, Skeleton,
        CopyButton, FilterToolbar, Pagination
AC:
  - [ ] All 8 components built with design system tokens
  - [ ] Storybook-style test page (optional)
```

### P2-02: BooksPage [FE]
```
Status: [ ]
Deps:   P2-01, P1-07, P1-08
Scope:  Book list + search + filter + create dialog (uses existing booksApi)
AC:
  - [ ] Cover thumbnails, serif titles, translation dots
  - [ ] "New Book" → FormDialog
  - [ ] Empty state, loading skeleton, pagination
```

### P2-03: BookDetailPage Shell [FE]
```
Status: [ ]
Deps:   P2-02
Scope:  Tabs: Chapters, Translation, Glossary, Sharing, Settings (stubs)
AC:
  - [ ] Breadcrumb: Workspace > Book Title
  - [ ] Tab routing to nested URLs
```

### P2-04: Chapters Tab [FE]
```
Status: [ ]
Deps:   P2-03
Scope:  DataTable with chapters, create dialog (uses existing booksApi)
AC:
  - [ ] Checkboxes, row actions (edit, download, trash with confirm)
  - [ ] Translation dot indicators
```

### P2-05: Chapter Editor — Workbench [FE]
```
Status: [ ]
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
Status: [ ]
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
Status: [ ]
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
Status: [ ]
Deps:   P1-02
Scope:  ReaderThemeProvider, 6 presets, customizer panel
AC:
  - [ ] CSS variables scoped to .reader-content
  - [ ] Quick-toggle dropdown + full settings panel
  - [ ] Saved to localStorage (API persistence later)
```

### P2-09: Notification System — Frontend Shell [FE]
```
Status: [ ]
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
Status: [ ]
Deps:   P2-02
Scope:  3-step first-time guide
AC:
  - [ ] Detects first login
  - [ ] Steps: Welcome → Configure AI → Create Book
  - [ ] Skip button, progress dots
```

### P2-11a: Import — Frontend [FE]
```
Status: [ ]
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

### Translation (FE — uses existing translation-service)
```
P3-01: Translation Matrix Tab [FE]
P3-02: Translate Modal [FE]
P3-03: Jobs Drawer [FE]
P3-04: Translation Settings Drawer [FE]
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
P3-18: Chat Page [FE] (uses existing chat-service)
  AC: [ ] Session sidebar, message area, streaming, model selector

P3-19: Chat Context Integration [FE]
  AC: [ ] Book/chapter/glossary context selector, "Send chunk to AI"

P3-20: Sharing Tab [FE] (uses existing sharing-service)
P3-21: Book Settings Tab [FE]
P3-22: Recycle Bin [FE] (uses existing booksApi)
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
P5-05: Text-to-Speech [FE]
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
