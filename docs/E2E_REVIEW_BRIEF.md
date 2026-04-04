# LoreWeave — E2E Review Brief

> **Purpose:** Single-document context dump for an external reviewer to assess project readiness.
> **Generated:** 2026-04-04 (session 19 end)
> **HEAD:** `7d2dcc8` on `main`

---

## 1. What This Project Is

LoreWeave is a **self-hosted multi-agent platform for multilingual novel workflows** — translation, analysis, knowledge building, and assisted creation. Docker Compose monorepo with 10 microservices + 1 React frontend.

**Target users:** Translators, novel readers, and authors working across languages (CJK focus).

---

## 2. Architecture

```
Browser → Vite+React (port 5173)
     ↓
API Gateway BFF (NestJS, port 3123) — reverse proxy, no business logic
     ↓ routes by prefix
┌──────────────┬──────────────┬──────────────┬──────────────┐
│ auth-service  │ book-service  │ glossary-svc  │ chat-service  │
│ Go/Chi        │ Go/Chi        │ Go/Chi        │ Python/Fast   │
│ :8081         │ :8082         │ :8088         │ :8090         │
├──────────────┼──────────────┼──────────────┼──────────────┤
│ sharing-svc   │ catalog-svc   │ provider-reg  │ usage-billing │
│ Go/Chi        │ Go/Chi        │ Go/Chi        │ Go/Chi        │
│ :8083         │ :8084         │ :8085         │ :8086         │
├──────────────┼──────────────┤              │              │
│ translation   │ video-gen     │              │              │
│ Python/Fast   │ Python/Fast   │              │              │
│ :8087         │ :8088         │              │              │
└──────────────┴──────────────┴──────────────┴──────────────┘
     ↓
Postgres (per-service DBs) · Redis Streams · MinIO (objects) · RabbitMQ (jobs)
```

**Key invariants:**
- Contract-first: OpenAPI specs before code
- All external traffic through gateway
- All AI calls through provider-registry adapter layer
- Go for domain services, Python for AI/LLM services, TypeScript for gateway
- Each service owns its own Postgres database

---

## 3. Services & Databases

| Service | Lang | DB | Tables | Port |
|---------|------|----|--------|------|
| auth-service | Go/Chi | loreweave_auth | 5 (users, sessions, verification, reset, security_prefs) | 8081 |
| book-service | Go/Chi | loreweave_books | 11 (books, chapters, drafts, revisions, blocks, cover, media_versions, quota, outbox) | 8082 |
| sharing-service | Go/Chi | loreweave_sharing | 1 (sharing_policies) | 8083 |
| catalog-service | Go/Chi | _(none — BFF aggregator)_ | 0 | 8084 |
| provider-registry-service | Go/Chi | loreweave_provider_registry | 5 (credentials, inventory_models, user_models, tags, platform_models) | 8085 |
| usage-billing-service | Go/Chi | loreweave_usage_billing | 5 (balances, logs, details, audits, reconciliation) | 8086 |
| translation-service | Python/FastAPI | loreweave_translation | 6 (preferences, settings, jobs, chapter_translations, chunks, active_versions) | 8087 |
| glossary-service | Go/Chi | loreweave_glossary | 10 (kinds, attrs, entities, links, values, translations, evidences, evidence_trans, genre_groups, snapshots) | 8088 |
| chat-service | Python/FastAPI | loreweave_chat | 3 (sessions, messages, outputs) | 8090 |
| video-gen-service | Python/FastAPI | _(none — stub)_ | 0 | 8088 |

**Total: 46 tables, 10 services, 8 databases.**

---

## 4. Module Status

| Module | Backend | Frontend | Tests | Status |
|--------|---------|----------|-------|--------|
| M01 Identity & Auth | Done | Done | Partial | Closed (smoke) |
| M02 Books & Sharing | Done | Done | Partial | Closed (smoke) |
| M03 Provider Registry | Done | Done | Partial | Closed (smoke) |
| M04 Translation Pipeline | Done | Done | Passing | Closed (smoke) |
| M05 Glossary & Lore | Done | Done | Partial | Closed (smoke) |
| P3-08 Genre Groups | Done | Done | 65 BE tests | **Closed (session 19)** |
| P3-21 Book SettingsTab | Done | Done | — | **Closed (session 19)** |
| Phase 6 Chat Enhancement | Done | Done | 28 tests | Closed (session 18) |
| Phase 7 Infra Hardening | — | — | — | Planned |

---

## 5. API Endpoint Summary (156 total)

### auth-service (14 endpoints)
| Method | Path | Description |
|--------|------|-------------|
| POST | /v1/auth/register | Register user |
| POST | /v1/auth/login | Login, get tokens |
| POST | /v1/auth/refresh | Refresh access token |
| POST | /v1/auth/logout | Invalidate session |
| POST | /v1/auth/verify-email/request | Send verification email |
| POST | /v1/auth/verify-email/confirm | Confirm email |
| POST | /v1/auth/password-reset/request | Request password reset |
| POST | /v1/auth/password-reset/confirm | Confirm password reset |
| POST | /v1/auth/change-password | Change password (authed) |
| GET | /v1/account/profile | Get user profile |
| PATCH | /v1/account/profile | Update user profile |
| GET | /v1/account/security/preferences | Get security prefs |
| PATCH | /v1/account/security/preferences | Update security prefs |

### book-service (29 endpoints)
| Method | Path | Description |
|--------|------|-------------|
| POST | /v1/books | Create book |
| GET | /v1/books | List user's books |
| GET | /v1/books/{id} | Get book |
| PATCH | /v1/books/{id} | Update book (title, description, language, summary, genre_tags) |
| DELETE | /v1/books/{id} | Trash book |
| POST | /v1/books/{id}/restore | Restore trashed book |
| DELETE | /v1/books/{id}/purge | Permanently delete |
| GET/POST/DELETE | /v1/books/{id}/cover | Cover CRUD |
| GET/POST | /v1/books/{id}/chapters | Chapter list + create |
| GET/PATCH/DELETE | /v1/books/{id}/chapters/{cid} | Chapter CRUD |
| GET/PATCH | /v1/books/{id}/chapters/{cid}/draft | Draft read/write |
| GET | /v1/books/{id}/chapters/{cid}/revisions | Revision history |
| POST | /v1/books/{id}/chapters/{cid}/media | Upload media |
| POST | /v1/books/{id}/chapters/{cid}/media-generate | AI generate media |
| _Internal:_ GET | /internal/books/{id}/projection | Book projection for catalog |

### glossary-service (35 endpoints)
| Method | Path | Description |
|--------|------|-------------|
| GET/POST | /v1/glossary/kinds | Kind list + create |
| PATCH/DELETE | /v1/glossary/kinds/{id} | Kind update/delete |
| POST/PATCH/DELETE | /v1/glossary/kinds/{id}/attributes/{aid} | Attr def CRUD |
| GET/POST/PATCH/DELETE | /v1/glossary/books/{bid}/genres/{gid} | Genre group CRUD |
| GET/POST | /v1/glossary/books/{bid}/entities | Entity list + create |
| GET/PATCH/DELETE | /v1/glossary/books/{bid}/entities/{eid} | Entity CRUD |
| GET/POST/PATCH/DELETE | .../chapter-links/{lid} | Chapter link CRUD |
| PATCH | .../attributes/{avid} | Attribute value update |
| POST/PATCH/DELETE | .../translations/{tid} | Translation CRUD |
| POST/PATCH/DELETE | .../evidences/{evid} | Evidence CRUD |
| GET | .../export | Glossary export |
| GET/POST/DELETE | .../recycle-bin/{eid} | Soft-delete management |

### catalog-service (4 endpoints — no auth, public)
| Method | Path | Description |
|--------|------|-------------|
| GET | /v1/catalog/books | List public books (?language=&genre=&sort=&q=) |
| GET | /v1/catalog/books/{id} | Public book detail |
| GET | /v1/catalog/books/{id}/chapters | Public chapter list |
| GET | /v1/catalog/books/{id}/chapters/{cid} | Public chapter detail |

### sharing-service (9 endpoints)
| Method | Path | Description |
|--------|------|-------------|
| GET/PATCH | /v1/sharing/books/{bid} | Get/update sharing policy |
| GET | /v1/sharing/unlisted/{token} | Access unlisted book |
| GET | /v1/sharing/unlisted/{token}/chapters | Unlisted chapter list |
| _Internal:_ GET | /internal/sharing/public | List public book IDs |

### provider-registry-service (22 endpoints)
| Method | Path | Description |
|--------|------|-------------|
| GET/POST/PATCH/DELETE | /v1/model-registry/providers/{id} | Provider credential CRUD |
| POST | /v1/model-registry/providers/{id}/health | Test connectivity |
| GET | /v1/model-registry/providers/{id}/models | List provider models |
| GET/POST/PATCH/DELETE | /v1/model-registry/user-models/{id} | User model CRUD |
| PATCH | .../activation | Toggle active |
| PATCH | .../favorite | Toggle favorite |
| POST | .../verify | Test invocation |
| POST | /v1/model-registry/invoke | Invoke AI model |
| _Internal:_ GET | /internal/credentials/{source}/{ref} | Resolve credentials |

### usage-billing-service (8 endpoints)
| Method | Path | Description |
|--------|------|-------------|
| GET | /v1/model-billing/usage-logs | List usage logs |
| GET | /v1/model-billing/usage-logs/{id} | Detail with decrypted payloads |
| GET | /v1/model-billing/usage-summary | Aggregated stats |
| GET | /v1/model-billing/account-balance | Quota/credits |
| _Internal:_ POST | /internal/model-billing/record | Record invocation |

### translation-service (17 endpoints)
| Method | Path | Description |
|--------|------|-------------|
| POST | /v1/translation/translate-text | Sync text translation |
| GET/PUT | /v1/translation/preferences | Global translation prefs |
| GET/PUT | /v1/translation/books/{bid}/settings | Per-book settings |
| POST/GET | /v1/translation/books/{bid}/jobs | Job create + list |
| GET | /v1/translation/books/{bid}/coverage | Coverage matrix |
| GET | /v1/translation/jobs/{jid} | Job detail |
| POST | /v1/translation/jobs/{jid}/cancel | Cancel job |
| GET | /v1/translation/chapters/{cid}/versions | Translation versions |
| PUT | .../versions/{vid}/active | Set active version |

### chat-service (16 endpoints)
| Method | Path | Description |
|--------|------|-------------|
| POST/GET | /v1/chat/sessions | Session create + list |
| GET | /v1/chat/sessions/search | FTS message search |
| GET/PATCH/DELETE | /v1/chat/sessions/{sid} | Session CRUD |
| GET/POST | /v1/chat/sessions/{sid}/messages | Message list + send (SSE stream) |
| DELETE | .../messages/{mid} | Delete message |
| GET | .../branches | List branch IDs |
| GET | .../outputs | List outputs |
| GET | .../export | Export session |

### video-gen-service (2 endpoints — stub)
| Method | Path | Description |
|--------|------|-------------|
| POST | /v1/video-gen/generate | Submit request (not implemented) |
| GET | /v1/video-gen/models | List models (empty) |

---

## 6. Frontend Pages (27 routes)

| Route | Component | Status |
|-------|-----------|--------|
| `/` | HomePage | Implemented (redirect to /books if authed) |
| `/login` | LoginPage | Implemented |
| `/register` | RegisterPage | Implemented |
| `/forgot` | ForgotPage | Implemented |
| `/reset` | ResetPage | Implemented |
| `/browse` | BrowsePage | Implemented (genre filter, language filter, search) |
| `/browse/:bookId` | PublicBookDetailPage | Implemented |
| `/books` | BooksPage | Implemented (workspace library) |
| `/books/:bookId` | BookDetailPage | Implemented (tabbed: Chapters, Translation, Glossary, Settings) |
| `/books/:bookId/chapters/:cid/edit` | ChapterEditorPage | Implemented (Tiptap rich text, media blocks) |
| `/books/:bookId/chapters/:cid/read` | ReaderPage | Implemented |
| `/books/:bookId/chapters/:cid/translations` | ChapterTranslationsPage | Implemented |
| `/chat` | ChatPage | Implemented (SSE streaming, thinking mode, branching) |
| `/trash` | TrashPage | Implemented (books + chapters + chat sessions) |
| `/usage` | UsagePage | Implemented (charts, logs, filters) |
| `/settings/:tab` | SettingsPage | Implemented (account, providers, translation, reading, language) |
| `/s/:token` | SharedBookPage | Implemented (unlisted access) |
| `/leaderboard` | PlaceholderPage | Not implemented |
| `/users/:userId` | PlaceholderPage | Not implemented |
| `/notifications` | PlaceholderPage | Not implemented |

### BookDetailPage Tabs
| Tab | Status |
|-----|--------|
| Chapters | **Implemented** |
| Translation | **Implemented** |
| Glossary | **Implemented** (entities, kinds, genres — 3 sub-views) |
| Settings | **Implemented** (basic info, cover, genre selector, visibility) |
| Wiki | Placeholder |
| Sharing | Placeholder |

---

## 7. Data Flow — Key Paths

### Auth Flow
```
Login → auth-service → JWT (access + refresh) → stored in React context
All API calls: Authorization: Bearer {access_token} → gateway forwards to services
```

### Book Creation + Genre
```
Create book (book-service) → genre_groups per book (glossary-service)
Book.genre_tags = user-selected genres → filters which kinds/attrs show in entity editor
```

### Translation Pipeline
```
User selects chapters + target language → translation-service creates job
→ translation-worker (RabbitMQ consumer) calls provider-registry/invoke
→ provider-registry resolves credentials → calls AI provider
→ usage-billing records tokens/cost
→ chunks stored in chapter_translations table
```

### Chat with AI
```
User sends message → chat-service SSE stream
→ chat-service calls provider-registry/internal/credentials
→ streams directly via OpenAI SDK (bypasses LiteLLM for reasoning)
→ usage-billing records via billing_client
→ SSE events: content-delta, reasoning-delta, usage, done
```

### Public Catalog
```
catalog-service → sharing-service/internal/public (get public book IDs)
→ book-service/internal/projection (get book details per ID)
→ filter by language, genre (OR logic), sort
→ no auth required
```

---

## 8. Genre System (Session 19 — tag-based)

```
genre_groups table (per-book): {id, book_id, name, color, description}
  ↓ genres defined here
entity_kinds.genre_tags[]: "kind shows for these genres" (empty = universal)
attribute_definitions.genre_tags[]: "attr shows for these genres" (empty = always)
books.genre_tags[]: user-selected genres from genre_groups
  ↓ filtering
Entity editor: hides attrs where attr.genre_tags doesn't intersect book.genre_tags
Kind dropdown: hides kinds where kind.genre_tags doesn't intersect book.genre_tags
Browse page: ?genre= filter with OR logic (comma-separated)
```

---

## 9. Known Issues / Tech Debt

| Issue | Severity | Where |
|-------|----------|-------|
| **Internal endpoints have no auth** | High | All /internal/ routes — Phase 7 INF-01 |
| Internal HTTP calls have no timeout/retry | Medium | All service-to-service calls — Phase 7 INF-02 |
| No structured JSON logging | Medium | All services — Phase 7 INF-03 |
| Export endpoint missing genre_tags | Medium | glossary-service export |
| Genre rename not atomic (FE cascade) | Medium | GenreGroupsPanel.tsx |
| Vite build fails (recharts not installed) | Low | Usage charts only |
| `patchKind`/`patchAttrDef` string-based duplicate detection | Low | Should use SQLSTATE 23505 |
| Browse genre chips from page results only | Low | Misses genres not in first 200 books |
| ReadingTab and ReaderThemeProvider not unified | Medium | P4-04 planned |
| ContextPicker loads all data on open | Medium | Could paginate |
| Wiki tab placeholder | — | P3-17 planned |
| Sharing tab placeholder | — | P3-20 planned |

---

## 10. Integration Tests

| Script | Service | Scenarios |
|--------|---------|-----------|
| `infra/test-genre-groups.sh` | glossary + book + catalog | 65 pass |
| `infra/test-chat.sh` | chat-service | 27 pass |
| `infra/test-chat-enhanced.sh` | chat-service (Phase 6) | 28 pass |
| `infra/test-sharing.sh` | sharing-service | 19 pass |
| `infra/test-book-settings.sh` | book-service | 23 pass |
| `infra/test-mig07-public-book.sh` | catalog + sharing | 19 pass |

---

## 11. How to Run

```bash
cd infra
docker compose up -d          # starts all services + postgres + redis + minio
# Frontend (dev): cd ../frontend && npm run dev
# Gateway: http://localhost:3123
# Frontend: http://localhost:5173
# Run tests: bash infra/test-genre-groups.sh
```

---

## 12. What to E2E Test

### Critical Paths
1. **Register → Login → Create Book → Add Chapters → Read Chapter**
2. **Create Book → Settings → Set Genre Tags → Glossary → Create Genre → Tag Kind → Create Entity → Verify filtered attrs**
3. **Set Book Public → Browse Page → Genre Filter → Click Book → Read**
4. **Chat → New Session → Send Message → Receive Stream → Think Mode**
5. **Translation → Select Chapter → Translate → View Translation Versions**

### Genre-Specific Flows (new in session 19)
6. **Book Settings → Genre Selector → Select from dropdown → Save → Verify genre_tags persists**
7. **Glossary → Genre Groups tab → Create genre → Edit → Rename (cascade) → Delete**
8. **Glossary → Kinds tab → Add genre_tags to kind → Save → Verify in entity form**
9. **Glossary → Create Attribute with genre_tags → Verify it shows/hides based on book genres**
10. **Browse → Genre chips → Click to filter → Multi-select → Verify OR logic**
11. **Book Card → Verify genre pills appear on cover**

### Edge Cases
12. Book with no genre_tags → all kinds/attrs visible (universal default)
13. Kind with `genre_tags: ["universal"]` → always visible
14. Attribute with `genre_tags: []` → always visible
15. Genre rename → verify kinds/attrs/book tags updated
16. Duplicate genre name → 409 error
17. Cross-book genre isolation → genres from book A don't appear in book B
