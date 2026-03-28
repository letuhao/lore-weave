# SESSION_PATCH — LoreWeave Project Status

> **Source of truth for current project state.**
> Update this file at the end of every session AND at each phase/sub-phase transition.

---

## Document Metadata

- Last Updated: 2026-03-29 (session 2)
- Updated By: Assistant (chat service implementation)
- Active Branch: `main`
- HEAD: `fd4a5ea` — feat: chunk selection (chat service implementation uncommitted)

---

## Module Status Matrix

| Module | Name                       | Backend | Frontend | Tests (unit) | Acceptance | Status        |
| ------ | -------------------------- | ------- | -------- | ------------ | ---------- | ------------- |
| M01    | Identity & Auth            | ✅ Done  | ✅ Done   | ✅ Partial    | ⚠️ Smoke only | **Closed (smoke)** |
| M02    | Books & Sharing            | ✅ Done  | ✅ Done   | ✅ Partial    | ⚠️ Smoke only | **Closed (smoke)** |
| M03    | Provider Registry          | ✅ Done  | ✅ Done   | ✅ Partial    | ⚠️ Smoke only | **Closed (smoke)** |
| M04    | Raw Translation Pipeline   | ✅ Done  | ✅ Done   | ✅ Partial    | ⚠️ Smoke only | **Closed (smoke)** |
| M05    | Glossary & Lore Management | ❌ Not started | ❌ Not started | — | — | **Planned** |

> **"Closed (smoke)"** = all code exists, smoke tests pass, formal acceptance evidence pack not yet produced.

---

## Current Active Work

**Phase:** Chat Service — Phase 1 (backend + frontend core)

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
| Chat service backend skeleton | `services/chat-service/` (new service, 15 files) | uncommitted |
| DB migration (3 tables: chat_sessions, chat_messages, chat_outputs) | `app/db/migrate.py` | uncommitted |
| Sessions CRUD, messages streaming (LiteLLM), outputs CRUD | `app/routers/` (3 routers) | uncommitted |
| Stream service: LiteLLM + AI SDK data stream protocol v1 | `app/services/stream_service.py` | uncommitted |
| Provider-registry: internal credentials endpoint | `services/provider-registry-service/internal/api/server.go` | uncommitted |
| docker-compose: add chat-service + loreweave_chat DB + INTERNAL_SERVICE_TOKEN | `infra/docker-compose.yml` | uncommitted |
| Gateway: proxy /v1/chat to chat-service | `services/api-gateway-bff/src/gateway-setup.ts`, `main.ts` | uncommitted |
| Frontend: full chat feature (ChatPage, SessionSidebar, ChatWindow, all components) | `frontend/src/features/chat/`, `frontend/src/pages/ChatPage.tsx`, `App.tsx` | uncommitted |
| Install @ai-sdk/react, ai, react-markdown, rehype-highlight, react-textarea-autosize, sonner | `frontend/package.json` | uncommitted |

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
| Phase 1 | chat-service skeleton + session CRUD + LiteLLM streaming + frontend chat UI | ✅ **Implemented** (uncommitted) |
| Phase 2 | Output storage (MinIO) + OutputCard portability + session export | ❌ Planned |
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

### Immediate candidates (UI polish continuation)

| Priority | Item | Notes |
| -------- | ---- | ----- |
| P1 | M05 SP-1 — glossary-service skeleton + kind enumeration | First sub-phase per `MODULE05_IMPLEMENTATION_SUBPHASE_PLAN.md` |
| P2 | ChunkEditor: AI agent integration | User noted "add later" — send chunk to AI model, receive edited text |
| P2 | ChunkEditor: per-chunk translation | Translate individual paragraphs via M04 translation API |
| P3 | Full acceptance evidence pack for M01–M04 | Currently smoke only; needed before any production release |

### M05 Sub-Phase Roadmap

| Sub-Phase | Goal | Status |
| --------- | ---- | ------ |
| SP-1 | glossary-service skeleton + kind enumeration (AT-01, AT-34) | ❌ Not started |
| SP-2 | Entity CRUD + filters (AT-02 to AT-15, AT-32 to AT-35) | ❌ Not started |
| SP-3 | Chapter link management (AT-16 to AT-20) | ❌ Not started |
| SP-4 | Attribute values + translations (AT-21 to AT-26) | ❌ Not started |
| SP-5 | Evidences + RAG export + smoke test (AT-27 to AT-31) | ❌ Not started |

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
| 2026-03-29 | Visibility fix, unified chapter editor, ChunkEditor system + selection | `fd4a5ea`, `3cb8e4c`, `2f47c89`, `b32f415` |
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
