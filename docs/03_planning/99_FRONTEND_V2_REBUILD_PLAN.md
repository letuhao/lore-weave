# Frontend V2 Rebuild Plan

> **Goal:** Rebuild the LoreWeave frontend from scratch with proper design system, consistent components, and usable navigation. Keep existing API layer and business logic; replace the UI shell entirely.

---

## 1. Why Rebuild (not patch)

The current frontend (M01-M05) has structural issues that can't be fixed incrementally:

| Problem | Impact |
|---|---|
| Single `<Card>` wraps all pages in `AppLayout` | Chat, editor, dashboard all cramped into same box |
| Flat text-link navigation, no active state | Users can't tell where they are |
| Raw HTML inputs/buttons mixed with shadcn/ui | Inconsistent sizing, focus rings, hover states across pages |
| Creation forms permanently visible on list pages | List content pushed below the fold |
| No confirmation dialogs for destructive actions | One misclick trashes a book with no warning |
| No breadcrumbs on nested pages | Deep pages have no navigation context |
| Metadata shown as raw key=value dumps | Looks like debug output, not a product |

**Decision:** New `frontend-v2/` folder. Reuse ~40% (API, auth, hooks). Rebuild ~60% (layout, components, pages).

---

## 2. Design System

### 2.1 Color Theme: Warm Literary

Defined in `design-drafts/components-v2-warm.html` (approved visual draft).

| Token | Value | Purpose |
|---|---|---|
| `--background` | `#181412` | Page background (warm near-black) |
| `--card` | `#1e1a17` | Card/panel background |
| `--card-hover` | `#272220` | Interactive card hover |
| `--border` | `#332d28` | Default borders |
| `--foreground` | `#f5efe8` | Primary text (warm cream) |
| `--muted-fg` | `#9e9488` | Secondary text |
| `--primary` | `#e8a832` | Amber gold (buttons, active states) |
| `--accent` | `#3da692` | Teal (Chat feature, secondary CTA) |
| `--destructive` | `#dc4e4e` | Red (delete, errors) |
| `--success` | `#3dba6a` | Green (active, translated) |
| `--warning` | `#e8a832` | Amber (trashed, in-progress) |
| `--info` | `#5496e8` | Blue (unlisted, running jobs) |

### 2.2 Typography

| Usage | Font | Weight |
|---|---|---|
| Page titles, book titles | Lora (serif) | 500-600 |
| Body text, UI labels, nav | Inter (sans) | 400-600 |
| Language codes, IDs, mono | JetBrains Mono | 400 |

### 2.3 Shared Components (build first, use everywhere)

| Component | Variants | Used By |
|---|---|---|
| `PageHeader` | simple, with-breadcrumb, with-tabs | Every page |
| `Breadcrumb` | clickable path segments | Nested pages |
| `Sidebar` | expanded (240px), collapsed (icon-only) | App shell |
| `DataTable` | sortable columns, checkboxes, row actions | Chapters, Usage, Glossary |
| `DataList` | card-style list items with hover | Books list |
| `FilterToolbar` | search input + dropdown filters | Lists, tables |
| `EmptyState` | icon + description + CTA button | All list pages |
| `StatusBadge` | visibility, lifecycle, job, translation | Everywhere |
| `ConfirmDialog` | destructive (red) + neutral variants | Delete/trash actions |
| `FormDialog` | title + form fields + cancel/submit | Create book/chapter |
| `Drawer` | slide-in from right | Settings, Jobs, Revisions |
| `CopyButton` | copy-to-clipboard with feedback | Share URLs, tokens |
| `Pagination` | page numbers + prev/next | All lists |
| `Skeleton` | card, table, text line variants | All loading states |
| `Toast` | success, error, loading | Via Sonner |

---

## 3. Layout Architecture

### 3.1 Three Layout Types

```
DashboardLayout          EditorLayout              FullBleedLayout
[Sidebar][PageHeader]    [Sidebar][Toolbar+Save]   [Sidebar][Content 100%]
         [Content]                [Editor fill]              [no padding]
         [scrollable]             [Revision bar]
```

| Layout | Used By |
|---|---|
| `DashboardLayout` | Books, Book Detail (tabs), Settings, Usage, Browse, Glossary, Sharing |
| `EditorLayout` | Chapter Editor (full-height, toolbar, revision sidebar) |
| `FullBleedLayout` | Chat (sidebar + messages), Login/Register (centered card) |

### 3.2 Sidebar Navigation

```
MAIN
  Workspace (books)    /books
  Chat                 /chat
  Browse               /browse

MANAGE
  Usage                /usage
  Settings             /settings

FOOTER
  [User avatar + name]
  [Log out]
```

- Active state: amber tint background + amber text
- Collapsible to icon-only on small screens
- Mobile: hamburger menu overlay

### 3.3 Route Structure

```
/login                                    FullBleedLayout (centered)
/register                                 FullBleedLayout (centered)
/forgot                                   FullBleedLayout (centered)
/reset                                    FullBleedLayout (centered)

/books                                    DashboardLayout → BooksPage
/books/trash                              DashboardLayout → TrashPage
/books/:bookId                            DashboardLayout → BookDetailPage (Chapters tab)
/books/:bookId/translation                DashboardLayout → BookDetailPage (Translation tab)
/books/:bookId/glossary                   DashboardLayout → BookDetailPage (Glossary tab)
/books/:bookId/sharing                    DashboardLayout → BookDetailPage (Sharing tab)
/books/:bookId/settings                   DashboardLayout → BookDetailPage (Settings tab)
/books/:bookId/chapters/:chapterId/edit   EditorLayout → ChapterEditorPage

/chat                                     FullBleedLayout → ChatPage
/chat/:sessionId                          FullBleedLayout → ChatPage (active session)

/browse                                   DashboardLayout → BrowsePage
/browse/:bookId                           DashboardLayout → PublicBookPage

/usage                                    DashboardLayout → UsageLogsPage
/usage/:logId                             DashboardLayout → UsageDetailPage

/settings                                 DashboardLayout → SettingsPage (Account tab)
/settings/providers                       DashboardLayout → SettingsPage (Providers tab)
/settings/translation                     DashboardLayout → SettingsPage (Translation tab)

/s/:accessToken                           FullBleedLayout → UnlistedPage (no auth)
```

---

## 4. Screen Inventory

### 4.1 Key Design Changes from v1

| Screen | v1 Problem | v2 Solution |
|---|---|---|
| **Books list** | Create form always visible, takes 50% of screen | List-first; create behind "New Book" → dialog |
| **Book detail** | Sharing/Translation/Glossary are separate pages | Tab layout under Book Detail; user stays in context |
| **Chapter editor** | Inside card wrapper, no room | Full-height EditorLayout with revision sidebar |
| **Chat** | Inside card, can't fill viewport | FullBleedLayout, session sidebar + message area |
| **Settings** | Works fine | Keep tab layout, improve form consistency |
| **All pages** | Raw HTML buttons/inputs, no loading states | shadcn/ui components, skeletons, empty states |
| **All destructive actions** | Instant with no confirmation | ConfirmDialog for every trash/delete |
| **Navigation** | Flat text links, no context | Sidebar + breadcrumbs + active states |

### 4.2 Book Detail — Tab Architecture

```
BookDetailPage
  ├── PageHeader (title, metadata, breadcrumb)
  ├── Tabs
  │   ├── Chapters (default) — DataTable + "New Chapter" dialog
  │   ├── Translation — TranslationMatrix + FloatingActionBar
  │   ├── Glossary — Entity grid + detail panel
  │   ├── Sharing — Visibility selector + share URL
  │   └── Settings — Rename, cover upload, delete book
```

---

## 5. Internationalization (i18n)

### 5.1 Strategy

All GUI text goes through `react-i18next` from day one. No hardcoded strings.

| Decision | Choice |
|---|---|
| Library | `react-i18next` + `i18next` |
| Locale files | JSON, one file per namespace per locale (e.g. `en/common.json`, `ja/common.json`) |
| Namespaces | `common` (shared), `books`, `editor`, `chat`, `translation`, `glossary`, `settings`, `auth` |
| Fallback | English |
| Detection | Browser language → user preference (stored in settings) → fallback |
| Interpolation | `t('chapters_count', { count: 24 })` → "24 chapters" / "24 章" |

### 5.2 Day-1 Languages

| Language | Code | Native Name | Status |
|---|---|---|---|
| English | `en` | English | Default / fallback |
| Vietnamese | `vi` | Tiếng Việt | Primary author language |
| Japanese | `ja` | 日本語 | Core content language |
| Chinese Traditional | `zh-TW` | 繁體中文 | Core content language |

### 5.3 Language Display Convention

Languages are always shown with their **native name** + ISO code:

| Context | Format | Example |
|---|---|---|
| Metadata (inline, space available) | `NativeName (code)` | 日本語 (ja) |
| Table headers (tight width) | Stacked: `NativeName` / `(code)` | 日本語<br>(ja) |
| Tags / badges | `NativeName (code)` | Tiếng Việt (vi) |
| Selector dropdowns | `NativeName — English Name (code)` | 日本語 — Japanese (ja) |

### 5.4 What Is / Is Not Translated

| Translated (GUI) | NOT translated (user content) |
|---|---|
| Sidebar labels, page titles | Book titles, chapter text |
| Button text, dialog messages | Glossary entity names |
| Empty states, error messages | Chat messages |
| Settings labels, toast text | User descriptions |
| Breadcrumb labels | Translation output |

---

## 6. Reader/Editor Theme Customization

### 6.1 Strategy

The **editor/reader content area** has its own theme system, independent from the app chrome. Users customize their reading experience without affecting navigation, sidebars, or toolbars.

### 6.2 Scope — What Is Themable

| Setting | Options | Default | Storage |
|---|---|---|---|
| **Background color** | Preset themes + custom hex | App dark (`#181412`) | User preference (API) |
| **Text color** | Tied to preset, or custom hex | Cream (`#f5efe8`) | User preference |
| **Font family** | Lora, Inter, Noto Serif JP, Noto Serif TC, System, Custom | Lora | User preference |
| **Font size** | 12px — 28px (slider) | 16px | User preference |
| **Line height** | 1.4 — 2.2 (slider) | 1.8 | User preference |
| **Text width** | Narrow (520px) / Medium (680px) / Wide (840px) / Full | Medium | User preference |
| **Paragraph spacing** | Compact / Normal / Relaxed | Normal | User preference |

### 6.3 Built-in Theme Presets

| Name | Background | Text | Font | Best For |
|---|---|---|---|---|
| **Dark (default)** | `#181412` | `#f5efe8` | Lora | Evening reading, OLED-friendly |
| **Sepia** | `#f4ecd8` | `#5b4636` | Lora | Comfortable long reading (like Kindle) |
| **Light** | `#ffffff` | `#1a1a1a` | Inter | Daytime, bright environments |
| **OLED Black** | `#000000` | `#cccccc` | System | Pure black for AMOLED screens |
| **Parchment** | `#e8dcc8` | `#3d3020` | Noto Serif JP | Japanese novel feel |
| **Forest** | `#1a2418` | `#c8d8c0` | Lora | Low-strain green tint |

### 6.4 Theme Application Boundary

```
┌──────────────────────────────────────────────────────────┐
│  App Chrome (always uses app theme — warm literary dark) │
│  ┌──────┬─────────────────────────────────┬────────────┐ │
│  │ Left │                                 │ Right      │ │
│  │Panel │   READER THEME APPLIES HERE     │ Panel      │ │
│  │(app) │   (user's chosen background,    │ (app)      │ │
│  │      │    font, size, colors)          │            │ │
│  │      │                                 │            │ │
│  └──────┴─────────────────────────────────┴────────────┘ │
│  Status bar (always app theme)                           │
└──────────────────────────────────────────────────────────┘
```

### 6.5 Theme Settings UI

Located in: Editor toolbar (quick toggle) + Settings page (full customization).

- **Quick toggle**: Dropdown in editor toolbar with preset thumbnails
- **Full settings**: Settings → Reading → sliders, color pickers, font selector, live preview
- **Per-book override**: Optional — user can set different themes per book

### 6.6 Technical Approach

- CSS custom properties scoped to `.reader-content` container
- `ReaderThemeProvider` context provides current theme values
- Theme stored in user preferences (API) + localStorage (offline fallback)
- Font loading via `next/font` or Google Fonts API (lazy load non-default fonts)

---

## 7. Editor Workbench (VS Code-style 3-Panel)

### 7.1 Layout

The Chapter Editor uses a resizable 3-panel workbench layout:

```
┌──────┬────────────────┬─ drag ─┬──────────────────┬─ drag ─┬──────────────────┐
│ Nav  │ LEFT PANEL     │        │ CENTER (EDITOR)  │        │ RIGHT PANEL      │
│ Rail │ Tabs:          │  ←→    │ Chunk-based text │  ←→    │ Tabs:            │
│ 48px │ · Source       │resize  │ editor (always   │resize  │ · AI Chat        │
│      │ · Chapters     │        │  visible)        │        │ · History        │
│      │ · Glossary     │        │                  │        │ · Translation    │
│      │                │        │                  │        │ · Glossary       │
├──────┴────────────────┴────────┴──────────────────┴────────┴──────────────────┤
│ Status bar: connection · selection · keyboard shortcuts                        │
└───────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Panel Modes

**Left panel:**
| Mode | Content | Use Case |
|---|---|---|
| Source | Original text (read-only, synced scroll) | Translation: see original while editing |
| Chapters | Book chapter list for navigation | Jump between chapters without leaving editor |
| Glossary | Searchable glossary terms | Look up character names while writing |

**Right panel:**
| Mode | Content | Use Case |
|---|---|---|
| AI Chat | Chat with AI about selected chunks | Improve, translate, explain text |
| History | Revision list + diff preview | Review/restore old versions |
| Translation | Side-by-side translated version | Review translation quality |
| Glossary Detail | Entity details + references | Deep-dive on a character/term |

### 7.3 Panel Behavior

- Panels toggle via toolbar buttons or keyboard: `Ctrl+B` (left), `Ctrl+J` (right)
- Drag handles between panels for resizing
- Panel widths + open/close state saved to localStorage
- Sidebar collapses to icon-only rail (48px) in editor mode
- "Send to AI" button on each chunk opens right panel in AI Chat mode with chunk as context

Design draft: `design-drafts/screen-editor-workbench.html`

---

## 8. Deployment Modes

LoreWeave supports two deployment modes. The frontend must work in both.

### 8.1 Self-Hosted Workbench (solo / team)

- Docker Compose on user's own machine or server
- All data stays local — full privacy
- No community features (leaderboard, browse catalog, public ratings hidden)
- Wiki is private by default (team knowledge base)
- Focus: writing, translation, glossary, AI tools

### 8.2 Hosted Platform (community)

- Managed SaaS version with shared community
- Community features enabled: browse, leaderboard, ratings, comments, wiki PRs, tags, follow
- Public author/translator profiles
- Content moderation and reporting tools

### 8.3 How the Frontend Handles Both

```
if (instance.mode === 'self-hosted') {
  // Hide: Browse, Leaderboard, public profiles, community tags
  // Show: Workspace, Chat, Editor, Translation, Glossary, Wiki (private), Settings, Usage
  // Sidebar: no "Browse" or "Leaderboard" links
}

if (instance.mode === 'platform') {
  // Show everything
  // Enable: notifications, follow, ratings, comments, moderation
}
```

The mode is determined by a server-side config flag (`LOREWEAVE_MODE=workbench|platform`). The frontend reads this at startup and conditionally renders community features.

**Design rule:** Every screen must work without community features. Community features are additive, never required.

---

## 9. Reuse Strategy

### 5.1 Copy from `frontend/` (works as-is)

| Directory/File | What | Notes |
|---|---|---|
| `src/api/` | API client (`apiJson`, error utils) | Core HTTP layer |
| `src/auth/` | AuthProvider, useAuth, RequireAuth | Token management |
| `src/features/books/api.ts` | booksApi module | All book/chapter API calls |
| `src/features/translation/` | translationApi, versionsApi | Translation pipeline API |
| `src/features/glossary/api.ts` | glossaryApi | Glossary CRUD |
| `src/features/ai-models/api.ts` | aiModelsApi | Model listing |
| `src/features/chat/hooks/` | useSessions | Chat session management |
| `src/features/chat/types.ts` | Type definitions | Chat types |
| `src/features/glossary/hooks/` | useEntityKinds, useGlossaryEntities, useEntityDetail | Glossary data hooks |
| `src/hooks/useJobEvents.ts` | WebSocket job event listener | Translation live updates |
| `src/lib/utils.ts` | cn() utility | Class merging |

### 5.2 Rebuild (new code)

| What | Why |
|---|---|
| All page components | New layout structure, new component patterns |
| Layout components | New 3-layout architecture |
| All shared UI components | Consistent shadcn/ui based design system |
| Router setup | New route structure with nested layouts |
| CSS/theme | New warm literary color system |

---

## 9. Implementation Phases

### Phase 1: Foundation (scaffold + layout + routing + i18n)

| Task | Output |
|---|---|
| Create `frontend-v2/` with Vite + React + TypeScript | Project skeleton |
| Install Tailwind CSS + shadcn/ui (fresh) | Design system base |
| Configure CSS variables (warm literary theme) | `index.css` |
| Set up `react-i18next` + locale file structure (en, vi, ja, zh-TW) | i18n framework |
| Build `Sidebar` component (all labels via `t()`) | Navigation shell |
| Build 3 layout components | `DashboardLayout`, `EditorLayout`, `FullBleedLayout` |
| Set up React Router with nested layouts | Route structure |
| Copy API layer + auth from `frontend/` | Data layer ready |
| Build `PageHeader` + `Breadcrumb` | Page chrome |
| Build `LanguageDisplay` component (native name + code) | Consistent language rendering |
| Auth pages (Login, Register, Forgot, Reset) | First working pages |
| Language selector in Settings | GUI language switching |

**Exit criteria:** App runs, sidebar navigates, auth flow works, language switching works, mode detection (workbench/platform) works.

### Phase 2: Core Screens + Essentials

| Task | Output |
|---|---|
| Build shared components: `StatusBadge`, `ConfirmDialog`, `FormDialog`, `EmptyState`, `Skeleton` | Component library |
| Build `FilterToolbar` + `Pagination` | List infrastructure |
| BooksPage (list + search + create dialog) | Main workspace |
| BookDetailPage shell (tabs + header) | Book hub |
| Chapters tab (DataTable + create dialog) | Chapter management |
| ChapterEditorPage — 3-panel workbench (EditorLayout + Lexical + AI panel) | Core editing experience |
| Split-view translation editing (source + translation side-by-side, accept/reject per chunk) | Translation review |
| Reading mode (clean reader + chapter nav + TOC + language selector) | Reader experience |
| `ReaderThemeProvider` + theme presets (Dark, Sepia, Light, OLED, Parchment, Forest) | Reader theme system |
| Theme quick-toggle in editor toolbar + reader top bar | Theme switching |
| Reader theme settings UI (font, size, line-height, width, paragraph spacing) | Full customization |
| **Notification system** (bell icon, notification center, unread count) | Critical user feedback |
| **Onboarding wizard** (first-time: add API key → create book → upload chapter) | First-time user experience |
| **Import .docx / .epub / .txt** with chapter detection | User acquisition unblock |

**Exit criteria:** Can create books (or import), edit in workbench, read chapters, switch themes, receive notifications.

### Phase 3: Feature Screens + Community (platform mode)

| Task | Output |
|---|---|
| Translation tab (matrix + floating bar + translate modal) | Translation workflow |
| Glossary tab (entity grid + detail panel + create modal) | Glossary management |
| Glossary Kind editor (system/user kinds, attributes, revert to default) | Kind & attribute schema management |
| Genre Group editor (activation matrix — toggle attrs per genre) | Genre-based attribute control |
| Glossary Entity editor (dynamic form based on active genre + kind) | Entity CRUD with genre-aware fields |
| Wiki system (reader view, editor view, AI assist with cost warning) | Wiki |
| Wiki settings (visibility, community editing mode, glossary exposure) | Writer wiki control |
| Wiki community suggestions / PR review queue | Fork + PR model |
| Sharing tab (visibility selector + copy URL) | Sharing settings |
| Book Settings tab (rename, cover, delete with ConfirmDialog) | Book management |
| ChatPage (FullBleedLayout + session sidebar + message area) | Chat feature |
| Chat context integration (book selector, chapter context, glossary context) | Novel-aware AI |
| RecycleBinPage (trashed books/chapters) | Trash management |
| **User profile page** (public: bio, books, translations, stats, follow button) | Community identity |
| **Ratings + reviews** on book detail page | Social proof |
| **Chapter comments** (below reader, with spoiler tags) | Reader engagement |
| **Community tags with voting** | Crowdsourced classification |
| **Content reporting + moderation queue** (for book owners) | Safety |
| **Follow author** + notification on new chapter | Retention loop |

**Exit criteria:** All M01-M05 + Chat + Wiki + Community features working in v2. Platform mode fully functional.

### Phase 4: Secondary Screens + Growth

| Task | Output |
|---|---|
| SettingsPage (Account + Providers + Translation + Reading + Language tabs) | User settings |
| AI Usage Monitor — dashboard (stat cards, model/purpose breakdown, daily chart) | Usage overview |
| AI Usage Monitor — request log table (filter, sort, paginate, expand for input/output) | Detailed log |
| **Author analytics dashboard** (readers, engagement, rating trends, chapter drop-off) | Author retention |
| BrowsePage (trending, recently updated, staff picks, complete/ongoing filter) | Public catalog |
| PublicBookPage (cover, rating summary, reviews, translations, read button) | Book discovery |
| **Leaderboard** (top books, authors, translators with period selector + genre filter) | Community engagement |
| **My Library** (favorites, currently reading, reading history, custom lists) | Reader retention |
| UnlistedPage (shared access) | Share link target |
| **Export .epub / .pdf** | Read on other devices |
| Toast notifications on all mutations | User feedback |
| **Email notification preferences** (per-event toggle) | Notification control |
| Keyboard shortcuts (Cmd+S, Cmd+K, Cmd+B/J, arrow keys in split-view) | Power user features |
| Mobile responsive sidebar (hamburger menu) | Mobile support |
| Custom theme creator (color picker, font upload) | Advanced customization |
| Per-book theme override | Book-specific reading preferences |
| Community translations for additional GUI languages | i18n expansion |

### Phase 5: Advanced Features (future)

| Task | Output |
|---|---|
| Translation memory (TM) — consistent terms across chapters | Translation quality |
| Collaborative translation (assign chapters, reviewer workflow) | Team translation |
| Bookmark + highlight + notes in reader | Reading depth |
| Dictionary lookup (tap word for definition, especially CJK) | Multilingual UX |
| Text-to-speech in reader | Accessibility |
| Estimated reading time per chapter | Reader convenience |
| Character relationship graph (visual) | Glossary visualization |
| Plot hole / consistency checker (AI) | Writing quality tool |
| Monetization hooks (author tipping, premium tiers) | Business model |
| Platform admin moderation dashboard | Platform-level safety |
| Federated discovery (self-hosted instances share public catalogs) | Network growth |

**Exit criteria:** Full-featured novel platform with author tools, reader experience, and community engagement.

---

## 10. Tech Stack

| Layer | Technology |
|---|---|
| Build | Vite 5 |
| Framework | React 18 + TypeScript |
| Routing | React Router DOM 6 |
| Styling | Tailwind CSS 3 + CSS variables |
| Components | shadcn/ui (Radix primitives) |
| Forms | React Hook Form + Zod |
| i18n | react-i18next + i18next + i18next-browser-languagedetector |
| Rich text | Lexical |
| Chat | @ai-sdk/react (useChat) |
| Markdown | react-markdown + rehype-highlight |
| Toasts | Sonner |
| Icons | Lucide React |
| Fonts | Google Fonts (Inter, Lora, JetBrains Mono, Noto Serif JP, Noto Serif TC) |
| Testing | Vitest + Testing Library |

---

## 11. Risk & Mitigation

| Risk | Mitigation |
|---|---|
| Rebuild takes too long | Reuse 40% of code; phase delivery so each phase is usable |
| Feature regression (missing edge cases) | Run v1 and v2 side by side during development; compare |
| Tailwind CDN issues (as seen in draft) | Use proper Vite build with PostCSS, not CDN |
| Design drift between screens | Shared component library built first in Phase 1 |
| API changes during rebuild | API layer is copied as-is; no backend changes needed |
| Community features bloat scope | Mode flag gates community features; Phase 2 works without them |
| Content moderation at scale | Start with report + queue (Phase 3); auto-mod in Phase 5 |
| Self-hosted users miss community | Design every screen to work standalone; community is additive |
| Import/export format complexity | Start with .txt + .docx (Phase 2); .epub in Phase 4 |
| Notification spam | Per-event email toggles (Phase 4); smart batching later |
| New backend services needed (ratings, comments, wiki, notifications) | Plan API contracts before frontend; can stub with local state initially |

---

## 12. Design Drafts Reference

| # | File | Contents | Status |
|---|---|---|---|
| 1 | `components-v2.html` | Cold theme (zinc/slate) | Rejected |
| 2 | `components-v2-warm.html` | Warm literary theme — shared component catalog | **Approved** |
| 3 | `screen-chapter-editor.html` | Simple editor — collapsed sidebar, toolbar, chunks, revision sidebar | **Approved** |
| 4 | `screen-editor-workbench.html` | 3-panel workbench — source panel, editor, AI chat panel | **Approved** |
| 5 | `screen-editor-splitview.html` | Split-view translation review — source + translation, accept/reject per chunk | **Approved** |
| 6 | `screen-chat.html` | Chat page — nav sidebar + session sidebar + message area | **Approved** |
| 7 | `screen-translation-matrix.html` | Translation tab — matrix table, cell states, floating bar | **Approved** |
| 8 | `screen-theme-customizer.html` | Reader theme customizer — presets, colors, font, sliders, live preview | **Approved** |
| 9 | `screen-glossary-management.html` | Kind editor, attribute editor, genre activation matrix, entity editor | **Approved** |
| 10 | `screen-usage-monitor.html` | AI usage dashboard — stat cards, breakdown, daily chart, request log | **Approved** |
| 11 | `screen-reader.html` | Clean reading mode — minimal chrome, TOC sidebar, chapter nav, language selector | **Approved** |
| 12 | `screen-browse-catalog.html` | Public book catalog — search, genre/language filters, cover card grid | **Approved** |
| 13 | `screen-settings.html` | Settings — provider management (BYOK), account, i18n, translation defaults | **Approved** |
| 14 | `screen-reader-social.html` | Book detail (public), ratings/reviews, chapter comments, translation vote, community tags, library | **Approved** |
| 15 | `screen-leaderboard.html` | Leaderboard — podium, full rankings, top authors, top translators, period + genre filters | **Approved** |
| 16 | `screen-wiki.html` | Wiki reader/editor, AI assist (cost warning), writer settings, community PR review | **Approved** |
| 17 | `screen-notifications.html` | Bell icon (3 states), notification center, filter tabs, email preferences | **Approved** |
| 18 | `screen-user-profile.html` | Public profile — bio, stats, achievements, books, translations, follow button | **Approved** |

All files in `design-drafts/` directory. Total: **17 approved drafts** (1 rejected cold theme).

**Components covered:** Sidebar, PageHeader, Breadcrumb, Buttons, StatusBadges, Form Inputs, Book Cards, Data Table, Empty States, Skeletons, Dialogs, Toasts, Copy Button, Auth Layout, Floating Action Bar, Language Display, Color Palette, Toggle Switch, Slider, Filter Chips, Pagination, Stat Cards, Bar Charts, Expandable Table Rows, Star Rating, Comment Thread, Review Card, Tag Voting Pill, Progress Bar, Notification Item, Achievement Badge, Podium, Rank Medal, Wiki Infobox, Wiki Link, Diff View, Cost Warning Dialog, Cover Card, Reading Progress.

**Screens covered:** Chapter Editor (simple + workbench + split-view), Chat Interface, Translation Matrix, Theme Customizer, Glossary Management (kind/attribute/genre/entity), AI Usage Monitor, Reader Mode, Browse Catalog, Settings, Reader Social (ratings/reviews/comments/tags/library), Leaderboard, Wiki (reader/editor/settings/PR review), Notifications, User Profile.

All design drafts use the warm literary theme with native language names (e.g. "日本語 (ja)").
