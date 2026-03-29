# SESSION_PATCH — LoreWeave Project Status

> **Source of truth for current project state.**
> Update this file at the end of every session AND at each phase/sub-phase transition.

---

## Document Metadata

- Last Updated: 2026-03-29 (session 5)
- Updated By: Assistant (Chat service unit tests)
- Active Branch: `main`
- HEAD: pending commit — chat-service unit tests + MinIO bugfix

---

## Module Status Matrix

| Module | Name                       | Backend | Frontend | Tests (unit) | Acceptance | Status        |
| ------ | -------------------------- | ------- | -------- | ------------ | ---------- | ------------- |
| M01    | Identity & Auth            | ✅ Done  | ✅ Done   | ✅ Partial    | ⚠️ Smoke only | **Closed (smoke)** |
| M02    | Books & Sharing            | ✅ Done  | ✅ Done   | ✅ Partial    | ⚠️ Smoke only | **Closed (smoke)** |
| M03    | Provider Registry          | ✅ Done  | ✅ Done   | ✅ Partial    | ⚠️ Smoke only | **Closed (smoke)** |
| M04    | Raw Translation Pipeline   | ✅ Done  | ✅ Done   | ✅ Passing    | ⚠️ Smoke only | **Closed (smoke)** |
| M05    | Glossary & Lore Management | ✅ Done  | ✅ Done   | ✅ Partial    | ⚠️ Smoke only | **Closed (smoke)** |

> **"Closed (smoke)"** = all code exists, smoke tests pass, formal acceptance evidence pack not yet produced.

---

## Current Active Work

**Phase:** Chat Service — Phase 2 (output portability + MinIO storage)

**What was done in this session (2026-03-29, session 1):**

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Fix book visibility always showing "private" on BookDetailPageV2 | `frontend/src/pages/v2-drafts/BookDetailPageV2.tsx` | `2f47c89` |
| Unified chapter editor: tabbed workspace (Draft / Published), dirty tracking | `frontend/src/pages/v2-drafts/ChapterEditorPageV2.tsx` | `2f47c89` |
| Redesign book/chapter browsing UI: cover images, view modes | Multiple v2 pages | `b32f415` |
| Build ChunkEditor system: paragraph-level editing + AI context copy | `frontend/src/components/chunk-editor/` (3 new files) | `3cb8e4c` |
| Chunk selection: visible numbers, range select (shift+click), bulk copy | Same chunk-editor files | `fd4a5ea` |

**What was done in this session (2026-03-29, session 2):**

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Chat service backend skeleton | `services/chat-service/` (new service, 15 files) | `23bad63` |
| DB migration (3 tables: chat_sessions, chat_messages, chat_outputs) | `app/db/migrate.py` | `23bad63` |
| Sessions CRUD, messages streaming (LiteLLM), outputs CRUD | `app/routers/` (3 routers) | `23bad63` |
| Stream service: LiteLLM + AI SDK data stream protocol v1 | `app/services/stream_service.py` | `23bad63` |
| Provider-registry: internal credentials endpoint | `services/provider-registry-service/internal/api/server.go` | `23bad63` |
| docker-compose: add chat-service + loreweave_chat DB + INTERNAL_SERVICE_TOKEN | `infra/docker-compose.yml` | `23bad63` |
| Gateway: proxy /v1/chat to chat-service | `services/api-gateway-bff/src/gateway-setup.ts`, `main.ts` | `23bad63` |
| Frontend: full chat feature (ChatPage, SessionSidebar, ChatWindow, all components) | `frontend/src/features/chat/`, `frontend/src/pages/ChatPage.tsx`, `App.tsx` | `23bad63` |
| Install @ai-sdk/react, ai, react-markdown, rehype-highlight, react-textarea-autosize, sonner | `frontend/package.json` | `23bad63` |

**What was done in this session (2026-03-29, session 3):**

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Run all M01-M04 unit tests across all services | — | — |
| Fix gateway tests: add missing service URLs + WsAdapter | `services/api-gateway-bff/test/health.spec.ts`, `proxy-routing.spec.ts` | `bf17136` |
| Fix frontend tests: install missing @testing-library/dom peer dep | `frontend/package.json` | `bf17136` |
| Add glossary + chat proxy route test coverage | `services/api-gateway-bff/test/proxy-routing.spec.ts` | `bf17136` |

**What was done in this session (2026-03-29, session 4):**

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Run M05 glossary-service tests — all 22 pass, 16 DB tests skip (expected) | — | — |
| Wire OutputCards into assistant MessageBubble (code block extraction) | `MessageBubble.tsx`, new `utils/extractCodeBlocks.ts` | pending |
| Add session export button to ChatHeader | `ChatHeader.tsx` | pending |
| Add "Paste to Editor" integration via custom DOM event | New `utils/pasteToEditor.ts`, `OutputCard.tsx`, `ChapterEditorPageV2.tsx` | pending |
| MinIO storage client skeleton (upload, presigned URL, delete) | New `app/storage/minio_client.py`, `__init__.py` | pending |
| Binary download via MinIO presigned URLs | `app/routers/outputs.py` | pending |
| MinIO bucket auto-creation on startup | `app/main.py` | pending |

**What was done in this session (2026-03-29, session 5):**

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Chat-service full unit test suite (68 tests) | `tests/` (7 new files), `pytest.ini`, `requirements-test.txt` | pending |
| Fix `ensure_bucket` bug — `run_in_executor` keyword arg misuse | `app/storage/minio_client.py` | pending |

**Test coverage:**
- `test_output_extractor.py` — 8 tests (pure function, code block extraction)
- `test_auth.py` — 5 tests (JWT validation, expiry, wrong secret)
- `test_sessions_router.py` — 10 tests (CRUD, 404s, validation)
- `test_outputs_router.py` — 14 tests (CRUD, download, export, MinIO redirect)
- `test_messages_router.py` — 5 tests (list, send, streaming, archived, provider 404)
- `test_stream_service.py` — 6 tests (text deltas, persistence, artifacts, errors, model strings, history)
- `test_minio_client.py` — 5 tests (upload, presigned, delete, bucket create/noop)
- `test_clients.py` — 4 tests (provider resolve, billing log, error swallowing)

**ChunkEditor component system (created this session):**
```
frontend/src/components/chunk-editor/
  useChunks.ts      — splits text, tracks edits, reassembles, avoids circular updates
  ChunkItem.tsx     — single paragraph chunk: view / edit / copy / reset
  ChunkEditor.tsx   — container: selection state, dirty bar, selection bar, hint bar
  index.ts          — public exports
```

---

## What Is Next

### Chat Service

Design document: `docs/03_planning/98_CHAT_SERVICE_DESIGN.md`

| Phase | Scope | Status |
| ----- | ----- | ------ |
| Phase 1 | chat-service skeleton + session CRUD + LiteLLM streaming + frontend chat UI | ✅ **Committed** (`23bad63`) |
| Phase 2 | Output storage (MinIO) + OutputCard portability + session export | ✅ **Implemented** (pending commit) |
| Phase 3 | Message editing + branch history | ❌ Planned |
| Phase 4 | File attachments + multi-modal | ❌ Planned |

**Phase 1 notes:**
- Backend route: `POST /v1/chat/sessions/{id}/messages` → StreamingResponse (AI SDK data stream v1)
- Frontend uses `@ai-sdk/react` v3 `useChat` with `DefaultChatTransport` (v5 API)
- Provider credentials resolved via `GET /internal/credentials/{source}/{ref}?user_id=...` on provider-registry (X-Internal-Token auth)
- New DB: `loreweave_chat` (3 tables). MinIO bucket `lw-chat` is pre-configured in docker-compose
- Chat route: `/chat` (protected, requires auth)

**Key technology decisions (locked):**
- Backend: Python/FastAPI + **LiteLLM** (unified provider streaming)
- Frontend SSE: `@microsoft/fetch-event-source` (POST + auth headers)
- Markdown rendering: `react-markdown` + `rehype-highlight`
- File storage: MinIO (S3-compatible, self-hosted)
- New DB: `loreweave_chat` (chat_sessions, chat_messages, chat_outputs)
- New service port: 8090; provider-registry internal port: 8082

**Open questions (see doc §13):** MinIO as new dep (Q1), "Paste to Editor" mechanism (Q2), chat route location (Q3)

### Immediate candidates

| Priority | Item | Notes |
| -------- | ---- | ----- |
| P1 | Chat Phase 3 — Message editing + branch history | Next chat service phase |
| ~~P1~~ | ~~Chat service unit tests~~ | ✅ **Done** — 68 tests, all passing |
| P2 | ChunkEditor: AI agent integration | User noted "add later" — send chunk to AI model, receive edited text |
| P2 | ChunkEditor: per-chunk translation | Translate individual paragraphs via M04 translation API |
| P3 | Full acceptance evidence pack for M01–M05 | Currently smoke only; needed before any production release |

### M05 Sub-Phase Roadmap (all complete)

| Sub-Phase | Goal | Status |
| --------- | ---- | ------ |
| SP-1 | glossary-service skeleton + kind enumeration (AT-01, AT-34) | ✅ Done |
| SP-2 | Entity CRUD + filters (AT-02 to AT-15, AT-32 to AT-35) | ✅ Done |
| SP-3 | Chapter link management (AT-16 to AT-20) | ✅ Done |
| SP-4 | Attribute values + translations (AT-21 to AT-26) | ✅ Done |
| SP-5 | Evidences + RAG export + smoke test (AT-27 to AT-31) | ✅ Done |

---

## Open Blockers

| ID | Blocker | Severity | Owner |
| -- | ------- | -------- | ----- |
| BLK-01 | Formal acceptance evidence packs not produced for M01–M04 | Medium | QA |
| BLK-02 | M05 not started — glossary-service Go project doesn't exist yet | Low (planned) | Tech Lead |

---

## Session History (recent)

| Date       | What happened | Key commits |
| ---------- | ------------- | ----------- |
| 2026-03-29 | Visibility fix, unified chapter editor, ChunkEditor system + selection, chat service, test fixes | `bf17136`, `e9d1c29`, `23bad63`, `fd4a5ea`, `3cb8e4c`, `2f47c89`, `b32f415` |
| 2026-03-23 | M04 translation pipeline implementation (backend + frontend) | — |
| 2026-03-22 | M03 provider registry implementation (backend + frontend) | — |
| 2026-03-21 | M02 UI/UX wave (BookDetailPageV2, reader pages, responsive) | — |

---

## Deferred Items (cross-module)

| Item | Status | Planned direction |
| ---- | ------ | ----------------- |
| Physical garbage collector for purge_pending objects | Not implemented | Background GC worker |
| Gitea integration for chapter version control | Not implemented | ADR needed first |
| Non-text chapter formats (pdf, docx, html, OCR) | Not implemented | Future MIME extension wave |
| Paid storage tiers / billing integration | Not implemented | Future monetization wave |
| AI-generated summaries / covers | Not implemented | Future AI feature wave |
| Production rollout hardening (SRE, security sign-off) | Not done | Pre-release gate wave |
| SSE / WebSocket streaming progress for translation jobs | Not implemented | Currently polling |
