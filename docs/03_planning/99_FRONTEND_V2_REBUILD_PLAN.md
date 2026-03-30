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

## 5. Reuse Strategy

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

## 6. Implementation Phases

### Phase 1: Foundation (scaffold + layout + routing)

| Task | Output |
|---|---|
| Create `frontend-v2/` with Vite + React + TypeScript | Project skeleton |
| Install Tailwind CSS + shadcn/ui (fresh) | Design system base |
| Configure CSS variables (warm literary theme) | `index.css` |
| Build `Sidebar` component | Navigation shell |
| Build 3 layout components | `DashboardLayout`, `EditorLayout`, `FullBleedLayout` |
| Set up React Router with nested layouts | Route structure |
| Copy API layer + auth from `frontend/` | Data layer ready |
| Build `PageHeader` + `Breadcrumb` | Page chrome |
| Auth pages (Login, Register, Forgot, Reset) | First working pages |

**Exit criteria:** App runs, sidebar navigates, auth flow works.

### Phase 2: Core Screens

| Task | Output |
|---|---|
| Build shared components: `StatusBadge`, `ConfirmDialog`, `FormDialog`, `EmptyState`, `Skeleton` | Component library |
| Build `FilterToolbar` + `Pagination` | List infrastructure |
| BooksPage (list + search + create dialog) | Main workspace |
| BookDetailPage shell (tabs + header) | Book hub |
| Chapters tab (DataTable + create dialog) | Chapter management |
| ChapterEditorPage (EditorLayout + Lexical + revision sidebar) | Core editing experience |

**Exit criteria:** Can create books, add chapters, edit in the editor, navigate with breadcrumbs.

### Phase 3: Feature Screens

| Task | Output |
|---|---|
| Translation tab (matrix + floating bar + translate modal) | Translation workflow |
| Glossary tab (entity grid + detail panel + create modal) | Glossary management |
| Sharing tab (visibility selector + copy URL) | Sharing settings |
| Book Settings tab (rename, cover, delete with ConfirmDialog) | Book management |
| ChatPage (FullBleedLayout + session sidebar + message area) | Chat feature |
| RecycleBinPage (trashed books/chapters) | Trash management |

**Exit criteria:** All M01-M05 + Chat features working in v2.

### Phase 4: Secondary Screens + Polish

| Task | Output |
|---|---|
| SettingsPage (Account + Providers + Translation tabs) | User settings |
| UsageLogsPage + UsageDetailPage | Usage tracking |
| BrowsePage + PublicBookPage | Public catalog |
| UnlistedPage (shared access) | Share link target |
| Dark/light mode toggle | Theme switcher |
| Toast notifications on all mutations | User feedback |
| Keyboard shortcuts (Cmd+S in editor, Cmd+K search) | Power user features |
| Mobile responsive sidebar (hamburger menu) | Mobile support |

**Exit criteria:** Feature parity with `frontend/`, all screens working, responsive.

---

## 7. Tech Stack (unchanged from frontend v1)

| Layer | Technology |
|---|---|
| Build | Vite 5 |
| Framework | React 18 + TypeScript |
| Routing | React Router DOM 6 |
| Styling | Tailwind CSS 3 + CSS variables |
| Components | shadcn/ui (Radix primitives) |
| Forms | React Hook Form + Zod |
| Rich text | Lexical |
| Chat | @ai-sdk/react (useChat) |
| Markdown | react-markdown + rehype-highlight |
| Toasts | Sonner |
| Icons | Lucide React |
| Testing | Vitest + Testing Library |

---

## 8. Risk & Mitigation

| Risk | Mitigation |
|---|---|
| Rebuild takes too long | Reuse 40% of code; phase delivery so each phase is usable |
| Feature regression (missing edge cases) | Run v1 and v2 side by side during development; compare |
| Tailwind CDN issues (as seen in draft) | Use proper Vite build with PostCSS, not CDN |
| Design drift between screens | Shared component library built first in Phase 1 |
| API changes during rebuild | API layer is copied as-is; no backend changes needed |

---

## 9. Design Drafts Reference

| File | Contents |
|---|---|
| `design-drafts/components-v2.html` | Cold theme (zinc/slate) — rejected |
| `design-drafts/components-v2-warm.html` | Warm literary theme — **approved** |

Components covered in draft: Sidebar, PageHeader, Breadcrumb, Buttons, StatusBadges, Form Inputs, Book Cards, Data Table, Empty States, Skeletons, Dialogs, Toasts, Copy Button, Auth Layout, Floating Action Bar, Color Palette Reference.

Screens **not yet drafted** (will design during implementation):
- Chapter Editor (EditorLayout)
- Chat Interface (FullBleedLayout)
- Translation Matrix
