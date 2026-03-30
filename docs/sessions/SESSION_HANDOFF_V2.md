# Session Handoff — Frontend V2 Rebuild

> **Purpose:** Give the next agent complete context to continue implementation from Phase 3 onward.
> **Date:** 2026-03-31
> **Last commit:** `63558eb` (Phase 2 bulk)

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
│   │   ├── shared/               # StatusBadge, ConfirmDialog, FormDialog, EmptyState, Skeleton, CopyButton, FilterToolbar, Pagination, LanguageDisplay, LanguageSelector
│   │   ├── data/                 # DataTable (generic)
│   │   ├── editor/               # ChunkItem, RevisionHistory
│   │   ├── notifications/        # NotificationBell (mock)
│   │   ├── onboarding/           # OnboardingWizard
│   │   └── import/               # ImportDialog
│   ├── features/
│   │   └── books/api.ts          # booksApi (copied from v1, works with existing backend)
│   ├── hooks/
│   │   ├── useChunks.ts          # Chunk-based text editing state
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

### Recommended start order for Phase 3

**Start with FE-only tasks** (no backend changes needed):
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

## 8. Key Decisions Made This Session

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

---

## 9. Known Issues / Incomplete Items

| Issue | Where | Notes |
|---|---|---|
| OnboardingWizard not wired into App | `src/App.tsx` | Component exists but isn't rendered anywhere yet. Wire into BooksPage on first login. |
| ImportDialog not wired into ChaptersTab | `src/pages/book-tabs/ChaptersTab.tsx` | Component exists, needs an "Import" button in the chapters toolbar. |
| ReaderThemeProvider not applied to ReaderPage | `src/pages/ReaderPage.tsx` | Provider wraps App but reader doesn't use CSS vars yet. Apply `style={cssVars}` to reading area. |
| LanguageSelector not shown anywhere | Component exists | Should appear in Settings → Language tab. |
| ModeProvider unused | `src/providers/ModeProvider.tsx` | Decision made to not split modes. Can be removed or kept for future feature gating. |
| Books i18n only in English | `src/i18n/locales/en/books.json` | vi/ja/zh-TW books.json files not created yet. |
| ChapterEditorPage title save | `src/pages/ChapterEditorPage.tsx` | Title input exists but changes aren't persisted (API uses body + commit_message only). |
| No tests written yet | — | Phase 2 focused on building screens. Unit tests should be added alongside Phase 3 work. |
