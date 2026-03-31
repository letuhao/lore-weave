# Session Handoff — Data Re-Engineering Migration

> **Purpose:** Give the next agent complete context to continue Phase D1 (Data Re-Engineering).
> **Date:** 2026-04-01 (session 12 end)
> **Last commit:** `54a4d1f` — schema(D1-02): uuidv7 everywhere, JSONB body, drop pgcrypto
> **Previous focus:** Frontend V2 Phase 2.5 E1 (Tiptap editor) — DONE
> **Current focus:** Data Re-Engineering Phase D1 — IN PROGRESS

---

## 1. What Is This Project

LoreWeave is a multi-agent platform for multilingual novel workflows (writing, translation, analysis, glossary, AI chat). Self-hosted via Docker Compose, with plans for a hosted community platform.

**Key docs to read first:**
- `CLAUDE.md` — project rules, architecture, service map
- `docs/03_planning/99_FRONTEND_V2_REBUILD_PLAN.md` — full rebuild plan with design system, i18n, theme, deployment modes, phases
- `docs/03_planning/99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` — 75-task breakdown with acceptance criteria, dependency graph
- `docs/sessions/SESSION_PATCH.md` — project status

---

## 2. What Was Done (Phase 1 + Phase 2)

### Phase 1: Foundation (11/11 complete)

| Task | What Was Built | Key Files |
|---|---|---|
| P1-01 | Vite + React 18 + TypeScript scaffold | `frontend-v2/package.json`, `vite.config.ts`, `tsconfig.json` |
| P1-02 | Tailwind 3.4 + warm literary theme CSS variables | `tailwind.config.cjs`, `src/index.css` |
| P1-03 | react-i18next with en/vi/ja/zh-TW | `src/i18n/index.ts`, `src/i18n/locales/` |
| P1-04 | API client + auth context (copied from v1) | `src/api.ts`, `src/auth.tsx` |
| P1-05 | ModeProvider (workbench/platform, currently unused) | `src/providers/ModeProvider.tsx` |
| P1-06 | React Router with 3 layouts | `src/App.tsx`, `src/layouts/` |
| P1-07 | Sidebar with i18n, auth-gated nav items | `src/components/layout/Sidebar.tsx` |
| P1-08 | PageHeader + Breadcrumb | `src/components/layout/PageHeader.tsx` |
| P1-09 | LanguageDisplay (native name + code) | `src/components/shared/LanguageDisplay.tsx`, `src/lib/languages.ts` |
| P1-10 | Login, Register, Forgot, Reset pages | `src/pages/auth/` (4 pages + AuthCard) |
| P1-11 | Language selector (GUI switching) | `src/components/shared/LanguageSelector.tsx` |


### Session 11: LanguageTool + Mixed-Media Editor Design + Phase Planning

| Work | What Was Built | Key Files |
|---|---|---|
| LanguageTool integration | Docker container (erikvl87/languagetool), Vite/nginx proxy, grammar API client | `docker-compose.yml`, `features/grammar/api.ts`, `hooks/useGrammarCheck.ts` |
| Grammar in chunk mode | Wavy underlines via ref injection on blur, strip on focus, tooltip via title attr | `components/editor/ChunkItem.tsx` |
| Grammar in source mode | Debounced check (1.5s), cursor-neighborhood detection (max 3 paragraphs), count badge | `hooks/useGrammarCheck.ts` (useSourceGrammarCheck) |
| Grammar toggle | SpellCheck icon, badge count, persisted localStorage, enabled by default | `pages/ChapterEditorPage.tsx` |
| Design: AI Assistant mode | Full block editor with all types, grammar, audio, AI prompts, format bar | `screen-editor-mixed-media.html` |
| Design: Classic mode | Pure writing, media as locked placeholders, minimal toolbar | `screen-editor-classic.html` |
| Design: Mode spec | Comparison table, guard behaviors, version data model, switching flow | `screen-editor-modes.html` |
| Design: Version history | Side-by-side comparison, prompt diff, image + audio timeline tabs | `screen-editor-version-history.html` |
| Phase planning | 29 new tasks in Phase 2.5 (12), Phase 3.5 (10), Phase 4.5 (7) | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` |

**Key decisions:**
- Tiptap replaces textarea + contentEditable chunks (unified editor)
- Two modes: Classic (text-only, media locked) / AI Assistant (full features)
- AI prompt on media: re-generation + AI context (saves tokens) + audit trail
- Audio/TTS per paragraph: hidden by default, narration mode toggle
- Phase 2.5 before Phase 3 to avoid double work on editor-dependent features

### Session 10: Chapter Editor Polish + Dialog + Toast System

Work done after Phase 2 was declared complete — UX hardening pass on the chapter editor.

| Work | What Was Built | Key Files |
|---|---|---|
| Chapter export bug fix | Backend `/export` handler returns `chapter_drafts.body` instead of raw file | `services/book-service/internal/api/server.go` |
| Comprehensive editor enhancement | Title saving via `patchChapter`, chunk insert/delete, auto-save (30s), Ctrl+S, word count | `ChapterEditorPage.tsx`, `useChunks.ts` |
| `ChunkItem` enhancements | `innerText` (not `textContent`) preserves newlines; always-visible border; delete button; auto-focus on insert | `src/components/editor/ChunkItem.tsx` |
| `ChunkInsertRow` | Invisible divider that reveals "+ insert" pill on hover, between every chunk pair | `src/components/editor/ChunkInsertRow.tsx` (new) |
| `ChapterReadView` | Shared reading component (serif, 17px, 1.85 line-height, 680px max) used by ReaderPage + RevisionHistory | `src/components/shared/ChapterReadView.tsx` (new) |
| Revision preview overlay | Full-screen `fixed inset-0 z-50` preview with `ChapterReadView`, restore from preview | `src/components/editor/RevisionHistory.tsx` |
| Source mode default | Writer-first: source textarea loads first, chunk mode is opt-in | `ChapterEditorPage.tsx` |
| Auto-chunk with preview | "Split into N paragraphs" — shows preview overlay, user confirms or cancels | `ChapterEditorPage.tsx` |
| Left sidebar | Chapters tab (navigate between chapters) + Original tab (lazy-loaded raw import) | `ChapterEditorPage.tsx` |
| `EditorLayout` sidebar | Full icon-only navigation (home, back-to-book, workspace, chat, settings, avatar, logout) | `src/layouts/EditorLayout.tsx` |
| `EditorDirtyContext` | Owns `isDirty`, `pendingNavigation`, `guardedNavigate`, `confirmNavigation`, `cancelNavigation` — shared between editor page and layout sidebar | `src/contexts/EditorDirtyContext.tsx` (new) |
| Universal `ConfirmDialog` | Extended: `icon` prop, `extraAction` (3rd stacked button), auto-stacks vertically when 3 actions | `src/components/shared/ConfirmDialog.tsx` |
| `UnsavedChangesDialog` | Thin wrapper around ConfirmDialog: Save & leave / Discard & leave / Stay | `src/components/shared/UnsavedChangesDialog.tsx` (new) |
| Navigation guard — all SPA routes | All `<Link>` in editor replaced with `guardedNavigate` buttons; logout uses `ConfirmDialog` | `ChapterEditorPage.tsx`, `EditorLayout.tsx` |
| Discard button | Appears in toolbar when `isDirty`; resets to last-saved state via `ConfirmDialog` | `ChapterEditorPage.tsx` |
| Toast system | Install `sonner`; `<Toaster>` at App root; replaces all inline save badges + error banners | `App.tsx`, all editor files |
| Eliminated `window.confirm/alert` | Zero remaining in frontend-v2; all replaced with modal dialogs or toasts | All editor/layout files |

### Phase 2: Core Screens (10/11 complete, P2-06 deferred)

| Task | What Was Built | Key Files |
|---|---|---|
| P2-01 | 8 shared components | `src/components/shared/` (StatusBadge, ConfirmDialog, FormDialog, EmptyState, Skeleton, CopyButton, FilterToolbar, Pagination) |
| P2-02 | BooksPage (workspace) | `src/pages/BooksPage.tsx`, `src/features/books/api.ts` |
| P2-03 | BookDetailPage with 6 tabs | `src/pages/BookDetailPage.tsx` |
| P2-04 | Chapters DataTable | `src/pages/book-tabs/ChaptersTab.tsx`, `src/components/data/DataTable.tsx` |
| P2-05 | Chapter Editor (3-panel workbench) | `src/pages/ChapterEditorPage.tsx`, `src/components/editor/`, `src/hooks/useChunks.ts`, `src/hooks/useEditorPanels.ts` |
| **P2-06** | **DEFERRED to P3** — Split-view translation needs translation API wired | — |
| P2-07 | Reading mode (TOC, chapter nav, progress) | `src/pages/ReaderPage.tsx` |
| P2-08 | Reader theme system (6 presets, customizable) | `src/providers/ReaderThemeProvider.tsx` |
| P2-09 | Notification bell (mock data) | `src/components/notifications/NotificationBell.tsx` |
| P2-10 | Onboarding wizard (3 steps) | `src/components/onboarding/OnboardingWizard.tsx` |
| P2-11a | Import dialog (.txt works, .docx/.epub placeholder) | `src/components/import/ImportDialog.tsx` |

### Infrastructure fixes done this session

| Fix | What | Files |
|---|---|---|
| DB bootstrap | healthcheck creates missing DBs on every start (replaces postgres-db-bootstrap container) | `infra/db-ensure.sh`, `infra/docker-compose.yml` |
| Docker builds | npm install flags to prevent hanging, .dockerignore | `frontend-v2/Dockerfile`, `frontend/Dockerfile` |
| Postgres | Downgraded 18 → 16 (data dir incompatibility) | `infra/docker-compose.yml` |
| API proxy | Vite proxy → localhost:3123 (gateway port) | `frontend-v2/vite.config.ts` |
| Auth guard | RequireAuth with return-to URL, 401 auto-logout, user profile fetch | `src/auth.tsx`, `src/api.ts` |
| Routing | / → /browse (public default), auth-gated sidebar items | `src/App.tsx`, `src/components/layout/Sidebar.tsx` |

---

## 3. Architecture of frontend-v2

### File Structure
```
frontend-v2/
├── src/
│   ├── api.ts                    # API client (apiJson utility, proxied via Vite)
│   ├── auth.tsx                  # AuthProvider, useAuth, RequireAuth
│   ├── App.tsx                   # Router with all routes
│   ├── main.tsx                  # Entry point (imports i18n)
│   ├── index.css                 # Tailwind + CSS variables (warm literary theme)
│   ├── components/
│   │   ├── layout/               # Sidebar, PageHeader
│   │   ├── shared/               # StatusBadge, ConfirmDialog (universal), UnsavedChangesDialog,
│   │   │                         # FormDialog, EmptyState, Skeleton, CopyButton, FilterToolbar,
│   │   │                         # Pagination, LanguageDisplay, LanguageSelector, ChapterReadView
│   │   ├── data/                 # DataTable (generic)
│   │   ├── editor/               # ChunkItem, ChunkInsertRow, RevisionHistory
│   │   ├── notifications/        # NotificationBell (mock)
│   │   ├── onboarding/           # OnboardingWizard
│   │   └── import/               # ImportDialog
│   ├── contexts/
│   │   └── EditorDirtyContext.tsx # isDirty, pendingNavigation, guardedNavigate — shared by
│   │                              # ChapterEditorPage + EditorLayout
│   ├── features/
│   │   └── books/api.ts          # booksApi (copied from v1, works with existing backend)
│   ├── hooks/
│   │   ├── useChunks.ts          # Chunk-based text editing (insert, delete, isDirty, reassemble)
│   │   └── useEditorPanels.ts    # Left/right panel toggle + localStorage persist
│   ├── i18n/
│   │   ├── index.ts              # i18next config
│   │   └── locales/{en,vi,ja,zh-TW}/{common,auth,books}.json
│   ├── layouts/
│   │   ├── DashboardLayout.tsx   # Sidebar + scrollable content
│   │   ├── EditorLayout.tsx      # Collapsed sidebar + full-height content
│   │   └── FullBleedLayout.tsx   # Centered content (auth pages)
│   ├── lib/
│   │   ├── utils.ts              # cn() utility (clsx + tailwind-merge)
│   │   └── languages.ts          # Language code → native name map
│   ├── pages/
│   │   ├── HomePage.tsx          # Redirects: logged in → /books, not logged in → /browse
│   │   ├── BooksPage.tsx         # Book list with search, create dialog
│   │   ├── BookDetailPage.tsx    # 6-tab detail page (Chapters active, others placeholder)
│   │   ├── ChapterEditorPage.tsx # 3-panel workbench
│   │   ├── ReaderPage.tsx        # Clean reading mode
│   │   ├── PlaceholderPage.tsx   # Generic placeholder for unbuilt pages
│   │   ├── auth/                 # Login, Register, Forgot, Reset
│   │   └── book-tabs/
│   │       └── ChaptersTab.tsx   # Chapter DataTable with create/trash/download
│   └── providers/
│       ├── ModeProvider.tsx      # workbench/platform mode (currently unused)
│       └── ReaderThemeProvider.tsx # 6 presets, customizable font/size/lineHeight/width
├── Dockerfile                    # Multi-stage: node build → nginx serve
├── nginx.conf                    # SPA fallback + /v1 proxy + /ws proxy
├── tailwind.config.cjs           # Full color system with HSL CSS variables
├── vite.config.ts                # Port 5174, proxy /v1 → localhost:3123
└── index.html                    # Google Fonts (Inter, Lora, JetBrains Mono)
```

### Route Map
```
PUBLIC (no auth):
  /                                → redirect to /browse (or /books if logged in)
  /login, /register, /forgot, /reset → auth pages (FullBleedLayout, centered)
  /browse                          → public catalog (DashboardLayout, sidebar)
  /browse/:bookId                  → public book detail
  /leaderboard                     → rankings
  /users/:userId                   → public profile
  /s/:accessToken                  → unlisted book access

PROTECTED (RequireAuth):
  /books                           → BooksPage (workspace)
  /books/trash                     → recycle bin
  /books/:bookId                   → BookDetailPage (Chapters tab default)
  /books/:bookId/translation       → BookDetailPage (Translation tab)
  /books/:bookId/glossary          → BookDetailPage (Glossary tab)
  /books/:bookId/wiki              → BookDetailPage (Wiki tab)
  /books/:bookId/sharing           → BookDetailPage (Sharing tab)
  /books/:bookId/settings          → BookDetailPage (Settings tab)
  /books/:bookId/chapters/:id/edit → ChapterEditorPage (EditorLayout)
  /books/:bookId/chapters/:id/read → ReaderPage (full screen, no sidebar)
  /chat                            → placeholder
  /usage                           → placeholder
  /settings/:tab                   → placeholder
  /notifications                   → placeholder
```

### Design System

**Theme:** Warm literary (amber primary, teal accent, dark warm background)
- CSS variables in `src/index.css` using HSL format
- `tailwind.config.cjs` maps all colors to `hsl(var(--color-name))`
- Fonts: Inter (sans), Lora (serif for titles/headings), JetBrains Mono
- Design drafts: `design-drafts/` (18 HTML files, all approved)

**i18n:** 4 locales (en, vi, ja, zh-TW), namespaces: common, auth, books
- All sidebar labels, auth pages, and books page are translated
- Pattern: `const { t } = useTranslation('namespace')` → `t('key')`
- New pages should add their namespace JSON files to all 4 locale directories

**Component patterns:**
- Shared components: `import { X } from '@/components/shared'`
- Form validation: react-hook-form + zod + zodResolver
- API calls: `apiJson<ResponseType>('/v1/path', { method, body, token })`
- Auth: `const { accessToken, user } = useAuth()` — pass `token: accessToken` to API calls
- Dialogs: `<ConfirmDialog>` for destructive, `<FormDialog>` for create/edit
- Loading: `<SkeletonCard />` or `<Skeleton className="h-4 w-32" />`
- Empty: `<EmptyState icon={X} title="..." description="..." action={<button>} />`

---

## 4. What's Next (Phase 3)

### Task list from `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md`:

**Translation (FE only — uses existing translation-service)**
```
P3-01: Translation Matrix Tab          → translation coverage grid in BookDetailPage
P3-02: Translate Modal                 → model selector, target language, chapter selection
P3-03: Jobs Drawer                     → running/completed/failed jobs, cancel
P3-04: Translation Settings Drawer     → per-book defaults
P2-06: Split-View Translation (deferred) → source + translation side-by-side, accept/reject per chunk
```

**Glossary (FE only — uses existing glossary-service)**
```
P3-05: Glossary Tab                    → entity grid + detail panel in BookDetailPage
P3-06: Kind Editor                     → system/user kinds, attributes, revert to default
P3-07: Entity Editor                   → dynamic form based on genre
```

**Genre Groups (needs backend extension)**
```
P3-08a: Genre Groups Backend           → new tables + endpoints in glossary-service
P3-08b: Genre Group Editor Frontend    → activation matrix toggle per genre
```

**Social Service (NEW backend service)**
```
P3-09: Social Service Scaffold         → Go/Chi, 12 tables, ratings/reviews/comments/tags/etc
P3-10: Ratings + Reviews FE
P3-11: Chapter Comments FE
P3-12: Community Tags FE
P3-13: Favorites + Library FE
P3-14: Reading Progress FE+BE
```

**Follow + Profiles**
```
P3-15a: Follow System Backend          → extend auth-service
P3-15b: User Profile Page FE
P3-16: Content Reporting + Moderation
```

**Wiki**
```
P3-17a: Wiki Backend                   → new tables, article CRUD, suggestions/PRs
P3-17b: Wiki Reader FE
P3-17c: Wiki Editor FE
P3-17d: Wiki Settings + PR Review FE
P3-17e: Wiki AI Assist FE
```

**Chat + Other**
```
P3-18: Chat Page FE                    → uses existing chat-service
P3-19: Chat Context Integration FE
P3-20: Sharing Tab FE                  → uses existing sharing-service
P3-21: Book Settings Tab FE
P3-22: Recycle Bin FE
```

### Recommended start order

**Phase 2.5 first (Editor Engine)** -- must complete before Phase 3:
1. E1-01 + E1-02 (install Tiptap, replace textarea)
2. E1-03 (replace chunks with Tiptap nodes + slash menu)
3. E1-05 (grammar as Tiptap decoration plugin)
4. E1-06 + E1-07 (mode toggle: Classic/AI)
5. E1-08 (wire auto-save, Ctrl+S, dirty tracking) -- GATE: editor production-ready

**Then Phase 3 FE-only tasks** (no backend changes needed):
1. P3-01 → P3-04 (Translation) — translation-service API exists
2. P3-05 → P3-07 (Glossary) — glossary-service API exists
3. P3-18 → P3-19 (Chat) — chat-service API exists
4. P3-20 → P3-22 (Sharing, Settings, Trash) — all APIs exist

**Then backend work** (can be done in parallel by another agent):
5. P3-09 (Social Service) — blocks P3-10 through P3-14, P3-16
6. P3-15a (Follow) — blocks P3-15b
7. P3-17a (Wiki) — blocks P3-17b through P3-17e
8. P3-08a (Genre Groups) — blocks P3-08b

### API modules that need to be copied from frontend v1

These feature API modules exist in `frontend/src/features/` and need to be copied to `frontend-v2/src/features/`:
```
features/translation/api.ts          → translationApi (jobs, settings, translate-text)
features/translation/versionsApi.ts  → versionsApi (coverage, chapter versions)
features/glossary/api.ts             → glossaryApi (entities, kinds, attributes)
features/glossary/hooks/             → useEntityKinds, useGlossaryEntities, useEntityDetail
features/ai-models/api.ts            → aiModelsApi (list user models)
features/chat/api.ts                 → chatApi (if exists separately from hooks)
features/chat/hooks/useSessions.ts   → session management
features/chat/types.ts               → ChatSession, etc.
hooks/useJobEvents.ts                → WebSocket job event listener
```

---

## 5. Backend Service Map (for reference)

| Service | Port | DB | Language | Key Endpoints |
|---|---|---|---|---|
| auth-service | 8204 | loreweave_auth | Go/Chi | /auth/*, /account/* |
| book-service | 8201 | loreweave_book | Go/Chi | /books/*, /chapters/* |
| sharing-service | 8202 | loreweave_sharing | Go/Chi | /books/{id}/visibility |
| catalog-service | 8203 | loreweave_catalog | Go/Chi | /catalog/books |
| provider-registry | 8205 | loreweave_provider_registry | Go/Chi | /providers/*, /user-models/* |
| usage-billing | 8206 | loreweave_usage_billing | Go/Chi | /usage-logs/*, /usage-summary |
| translation-service | 8080 | loreweave_translation | Python | /translate-text, /jobs/*, /books/{id}/coverage |
| glossary-service | 8207 | loreweave_glossary | Go/Chi | /kinds, /books/{id}/glossary/* |
| chat-service | 8090 | loreweave_chat | Python | /sessions/*, /messages/* |
| api-gateway-bff | 3000→3123 | — | TS/NestJS | Proxy to all services |

**All frontend API calls go through the gateway** (proxied via Vite in dev, nginx in Docker).

---

## 6. Task Workflow (9 phases per task)

```
1. PLAN    → Define scope, acceptance criteria, dependencies
2. DESIGN  → Component API, data flow, file structure
3. REVIEW  → PO reviews design before coding
4. BUILD   → Write code (backend first if FS task)
5. TEST    → Run locally, fix bugs, write unit tests
6. REVIEW  → Code review (patterns, security, a11y)
7. QC      → Test against acceptance criteria
8. SESSION → Update SESSION_PATCH.md + task status in 99A file
9. COMMIT  → Git commit with clear message, push
```

---

## 7. Design Drafts Reference

18 HTML files in `design-drafts/` — open in browser for visual reference:

| File | What It Shows |
|---|---|
| `components-v2-warm.html` | Full component catalog (shared theme) |
| `screen-chapter-editor.html` | Simple editor |
| `screen-editor-workbench.html` | 3-panel workbench |
| `screen-editor-splitview.html` | Split-view translation review |
| `screen-chat.html` | Chat interface |
| `screen-translation-matrix.html` | Translation matrix |
| `screen-theme-customizer.html` | Reader theme customizer |
| `screen-glossary-management.html` | Kind/attribute/genre/entity editors |
| `screen-usage-monitor.html` | AI usage dashboard + logs |
| `screen-reader.html` | Clean reading mode |
| `screen-browse-catalog.html` | Public book catalog |
| `screen-settings.html` | Settings (providers, account) |
| `screen-reader-social.html` | Ratings, reviews, comments, tags, library |
| `screen-leaderboard.html` | Leaderboard & rankings |
| `screen-wiki.html` | Wiki reader/editor/settings/PR review |
| `screen-notifications.html` | Notification system |
| `screen-user-profile.html` | Public user profile |

---

## 8. Key Decisions Made

| Decision | Reasoning |
|---|---|
| No mode split (workbench/platform) | Every user is both reader and writer. ModeProvider exists but is unused. |
| / defaults to /browse | No login wall. Users see content first, sign up when they want to write. |
| Auth-gated sidebar items | Workspace, Chat, Usage, Settings hidden when not logged in. Browse, Leaderboard always visible. |
| P2-06 (split-view) deferred to P3 | Needs translation API module copied + wired. Not a Phase 2 blocker. |
| Tailwind v3 (not v4) | v4 had breaking changes with Tailwind CDN and config format. v3 is stable and matches v1. |
| Postgres 16 (not 18) | Postgres 18 changed data directory format, incompatible with existing volumes. |
| npm install (not npm ci) | No package-lock.json committed. Docker builds use `npm install --no-audit --no-fund --loglevel=warn`. |
| i18n from day 1 | All UI strings go through `t()`. English is fallback. Only en has all namespaces; vi/ja/zh-TW have common + auth. |
| Reader theme scoped to content area | App chrome stays dark. Only the reader content area changes with theme presets. |
| NotificationBell uses mock data | Real API (P2-09b) is a backend task. Frontend shell is ready to wire. |
| Source mode as default in editor | Writers prefer typing raw text over chunked editing. Chunk mode is opt-in via toggle. |
| No error/warning dialog component | Inline errors for form context (login, import), toast for transient feedback. Error *dialogs* block the screen for something that doesn't need a user decision. |
| `sonner` as toast library | Matches what was already in use in the v1 chat frontend. Lightweight, works out of the box with shadcn design system. |
| `ConfirmDialog` is the single dialog primitive | Handles 2-button (default) and 3-button (`extraAction`) cases. `UnsavedChangesDialog` is just a pre-configured wrapper. No separate error/warning dialog needed. |
| `EditorDirtyContext` owns navigation guard logic | Both `ChapterEditorPage` (breadcrumbs, prev/next) and `EditorLayout` (sidebar links, logout) need to intercept navigation. Sharing via context avoids prop drilling and keeps `navigate()` in one place. |
| `window.confirm/alert` fully eliminated | Replaced with `ConfirmDialog` (blocking) or `toast.error` (non-blocking). Browser default dialogs are unstyled and block the thread. |

---

## 9. Known Issues / Incomplete Items

| Issue | Where | Notes |
|---|---|---|
| Grammar: source mode has no inline underlines (textarea limit) | useSourceGrammarCheck | Fixed by Tiptap migration (E1-05) |
| LanguageTool container heavy (~1.5 GB RAM) | docker-compose.yml | Optional, grammar degrades gracefully |
| useChunks/ChunkItem/ChunkInsertRow to be deleted | hooks/, components/editor/ | Replaced by Tiptap in E1-03 |
| OnboardingWizard not wired into App | `src/App.tsx` | Component exists but isn't rendered anywhere yet. Wire into BooksPage on first login. |
| ReaderThemeProvider not applied to ReaderPage | `src/pages/ReaderPage.tsx` | Provider wraps App but reader doesn't use CSS vars yet. Apply `style={cssVars}` to reading area. |
| LanguageSelector not shown anywhere | Component exists | Should appear in Settings → Language tab. |
| ModeProvider unused | `src/providers/ModeProvider.tsx` | Decision made to not split modes. Can be removed or kept for future feature gating. |
| Books i18n only in English | `src/i18n/locales/en/books.json` | vi/ja/zh-TW books.json files not created yet. |
| BooksPage create-book error uses inline banner | `src/pages/BooksPage.tsx` | Create-book error should probably be `toast.error` instead of inline. Low priority. |
| Glossary tab in editor left sidebar disabled | `ChapterEditorPage.tsx` | Tab exists as placeholder; needs glossary-service wired (P3-05). |
| AI Chat tab in editor right panel disabled | `ChapterEditorPage.tsx` | Tab exists as placeholder; needs chat-service wired (P3-18/19). |
| No tests written for frontend-v2 | — | Phase 2 + polish focused on building screens. Unit tests should be added alongside Phase 3 work. |

**Items resolved since last handoff:**
- ✅ Chapter title now saves via `patchChapter` in `save()`
- ✅ ImportDialog wired into ChaptersTab (Import button + state present)
- ✅ Chapter export bug fixed (returns edited draft body, not original file)
- ✅ `window.confirm/alert` fully eliminated
- ✅ Phase 2.5 E1 (Tiptap editor) complete — editor is production-ready for text
- ✅ Postgres 16 (not 18) decision **REVERSED** — now using Postgres 18

---

## 10. Current Focus: Data Re-Engineering Phase D1

> **IMPORTANT:** Frontend V2 Phase 3 is PAUSED. The next agent should continue D1 (data migration), NOT frontend work.

### Key Documents to Read First

1. `docs/03_planning/101_DATA_RE_ENGINEERING_PLAN.md` — full architecture, schema, decisions (#1-#26)
2. `docs/03_planning/102_DATA_RE_ENGINEERING_DETAILED_TASKS.md` — 58 sub-tasks, 8 discovery cycles
3. `docs/sessions/SESSION_PATCH.md` — current project status

### Architecture Summary (Two-Layer Data Stack)

```
PostgreSQL 18 (source of truth)          Neo4j v2026.01 (knowledge + vectors)
├── JSONB chapter content                ├── Entities, Events, Relations
├── chapter_blocks (trigger-extracted)   ├── Vector indexes (HNSW)
├── outbox_events (transactional)        └── Populated by AI pipeline (future)
├── event_log (permanent event store)
└── All relational data (10 databases)

Event pipeline: Outbox → worker-infra → Redis Streams + event_log
Two workers: worker-infra (Go, I/O) + worker-ai (Python, LLM)
```

### D1 Progress (2 of 12 done)

| Task | Status | Scope |
|------|--------|-------|
| D1-01 | **DONE** | Postgres 18 + Redis in docker-compose |
| D1-02 | **DONE** | uuidv7 everywhere (30 tables), JSONB body, drop pgcrypto |
| **D1-03** | **NEXT** | chapter_blocks table + UPSERT trigger (JSON_TABLE + _text) |
| D1-04 | pending | outbox_events table + pg_notify trigger |
| D1-05 | pending | loreweave_events schema (event_log, consumers, dead_letter) |
| D1-06 | pending | book-service JSONB refactor (7 handlers + test rewrites) — L size |
| D1-07 | pending | createChapter: plain text → Tiptap JSON at import |
| D1-08 | pending | Internal API text_content + translation-service fix (2 lines) |
| D1-09 | pending | worker-infra service scaffold (new Go service, 10 files) |
| D1-10 | pending | outbox-relay + cleanup tasks |
| D1-11 | pending | Frontend: save Tiptap JSON with _text, load JSONB, read-only reader |
| D1-12 | pending | Integration test (16 scenarios) |

### Key Things the Next Agent Must Know

1. **Strict 9-phase workflow** — each task goes through PLAN→DESIGN→REVIEW→BUILD→TEST→REVIEW→QC→SESSION→COMMIT individually. See CLAUDE.md and `memory/feedback_follow_task_workflow.md`.

2. **D0 pre-flight validated** — PG18 uuidv7(), JSON_TABLE, trigger+UPSERT, pgx json.RawMessage all tested and confirmed working. Test scripts in `infra/test-pg18-trigger.sql` and `infra/pg18test-go/`.

3. **Docker state** — Postgres volume was deleted (clean break). Next startup creates fresh PG18 databases. All services need to rebuild against new schema.

4. **book-service body column is now JSONB** — but the Go handler code still reads/writes it as `string`. D1-06 refactors all 7 handlers to use `json.RawMessage`. Until D1-06, the book-service will NOT start correctly because INSERT/UPDATE expect JSONB but pass strings.

5. **Detailed sub-task specifications** in `102_DATA_RE_ENGINEERING_DETAILED_TASKS.md` — Cycle 2 has the trigger SQL, Cycle 4 has handler-by-handler changes with line numbers, Cycle 5 has translation-service impact, Cycle 6 has worker-infra project structure, Cycle 7 has frontend changes.

6. **_text snapshots** — frontend adds `_text` field to each Tiptap block on save. Trigger reads `$._text` via JSON_TABLE. This eliminates complex server-side JSON parsing. See plan §3.2.1.

7. **getInternalBookChapter** must add `text_content` field — translation-service reads it instead of `body` (which is now JSONB). 2 one-line Python changes in D1-08.
