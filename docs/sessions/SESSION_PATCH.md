# SESSION_PATCH — LoreWeave Project Status

> **Source of truth for current project state.**
> Update this file at the end of every session AND at each phase/sub-phase transition.

---

## Document Metadata

- Last Updated: 2026-04-03 (session 17 in progress)
- Updated By: Assistant (MIG-03 Usage Monitor page — full-stack)
- Active Branch: `main`
- HEAD: pending commit — MIG-03 Usage Monitor
- **Session Handoff:** `docs/sessions/SESSION_HANDOFF_V2.md` — full context for next agent

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

**Phase:** V1→V2 Migration (MIG-03 in progress)

**What was done in this session (2026-04-03, session 17):**

MIG-03: Usage Monitor page — full-stack build from draft design.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| BE: `purpose` column added to `usage_logs` table | `migrate.go` | this session |
| BE: `recordInvocation` accepts `purpose` field | `server.go` | this session |
| BE: `listUsageLogs` — server-side filters (provider_kind, request_status, purpose, from, to) | `server.go` | this session |
| BE: `getUsageSummary` — error_rate, by_provider, by_purpose, daily breakdowns, last_30d/90d | `server.go` | this session |
| BE: test updated for `purpose` column in scanUsageLogRow | `server_test.go` | this session |
| FE: `features/usage/types.ts` — UsageLog, UsageSummary, AccountBalance, filter types | new file | this session |
| FE: `features/usage/api.ts` — usageApi (listLogs, getLogDetail, getSummary, getBalance) | new file | this session |
| FE: `features/usage/StatCards.tsx` — 4 stat cards (tokens, cost, calls, error rate) | new file | this session |
| FE: `features/usage/BreakdownPanels.tsx` — Tokens by Provider + Purpose bar charts | new file | this session |
| FE: `features/usage/DailyChart.tsx` — Recharts stacked bar chart (input/output tokens) | new file | this session |
| FE: `features/usage/RequestLogTable.tsx` — filterable table with expandable rows | new file | this session |
| FE: `features/usage/ExpandedRow.tsx` — lazy-fetch detail, Input/Output/Raw JSON tabs | new file | this session |
| FE: `pages/UsagePage.tsx` — page shell with period selector, CSV export | new file | this session |
| FE: App.tsx — replaced /usage placeholder with UsagePage, removed /usage/:logId | `App.tsx` | this session |
| FE: recharts dependency added | `package.json` | this session |
| M4-01 BE: previous period query in `getUsageSummary` — prev_request_count, prev_total_tokens, prev_total_cost_usd, prev_error_rate | `server.go` | this session |
| M4-02 FE: trend indicators on StatCards — ↑↓ % vs prev period, sentiment coloring (green/red/neutral) | `StatCards.tsx`, `types.ts` | this session |
| MIG-05: Settings page — 5 tabs (Account, Providers, Translation, Reading, Language) | 9 new files, `App.tsx`, `translation/api.ts` | this session |

**9-phase workflow followed:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-02, session 16):**

Phase 3.5 media blocks: E4-06 completed.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Phase 3.5 plan update: E4 expanded to 8 tasks, resize handles + alt text added to E4-01, design decisions documented | `docs/03_planning/99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | this session |
| E4-06: Code block — CodeBlockLowlight + ReactNodeViewRenderer, language selector (13 langs), copy button, hljs theme, slash menu + toolbar integration | `components/editor/CodeBlockNode.tsx` (new), `TiptapEditor.tsx`, `SlashMenu.tsx`, `FormatToolbar.tsx`, `index.css` | this session |
| E4-01: Image block — atom node with ReactNodeViewRenderer, resize handles (pointer events, 10-100%), editable caption, collapsible alt text field (WCAG), selection ring, empty state placeholder, extractText returns alt | `components/editor/ImageBlockNode.tsx` (new), `TiptapEditor.tsx` | this session |
| E4-02: Image upload — BE: MinIO upload endpoint on book-service (auth, type/size validation, UUID key), FE: drag-drop/paste/file-picker with XHR progress, error handling | `book-service/internal/api/media.go` (new), `server.go`, `config.go`, `docker-compose.yml`, `ImageBlockNode.tsx`, `features/books/api.ts` | this session |
| E4-03: AI prompt field — reusable MediaPrompt component (collapsible, textarea auto-grow, saved/empty badge, copy, re-generate placeholder), ai_prompt attr on imageBlock | `components/editor/MediaPrompt.tsx` (new), `ImageBlockNode.tsx` | this session |
| E4-04: Classic mode guards — MediaGuardExtension (backspace/delete/selection protection), compact locked placeholders for image+code blocks, mode storage sync | `components/editor/MediaGuardExtension.ts` (new), `ImageBlockNode.tsx`, `CodeBlockNode.tsx`, `TiptapEditor.tsx` | this session |
| E4-05: Video block — player placeholder, upload (MP4/WebM, 100 MB), caption, AI prompt (coming soon), Classic mode placeholder, BE video MIME support | `components/editor/VideoBlockNode.tsx` (new), `TiptapEditor.tsx`, `book-service/media.go` | this session |
| E4-07: Slash menu + toolbar — Image/Video in slash menu (AI mode), Image/Video insert buttons in FormatToolbar (AI mode) | `SlashMenu.tsx`, `FormatToolbar.tsx` | this session |
| E4-08: Source view — read-only Block JSON viewer with syntax highlighting, Copy JSON, toggle via editor handle, _text snapshots stripped | `components/editor/SourceView.tsx` (new), `TiptapEditor.tsx` | this session |
| E4-review: Cross-cutting fixes — unified upload context, bucket race fix, streaming upload, SourceView colon fix | 4 files | this session |
| E5-01: Media version tracking BE — block_media_versions table, CRUD endpoints (list/create/delete), auto-version on upload, versioned MinIO paths, public-read bucket policy | `migrate.go`, `media.go`, `server.go` | this session |
| E5-02: Version history UI — split-panel layout, side-by-side image comparison, version timeline (dots, tags, timestamps), LCS-based prompt diff, restore/download/delete actions, History button on image blocks | `VersionHistoryPanel.tsx`, `VersionTimeline.tsx`, `PromptDiff.tsx` (new), `ImageBlockNode.tsx`, `features/books/api.ts` | this session |
| Video generation service skeleton — Python/FastAPI, health/generate/models endpoints, returns "not_implemented", gateway proxy, FE wired with Generate button | `services/video-gen-service/` (new, 6 files), `gateway-setup.ts`, `main.ts`, `docker-compose.yml`, `features/video-gen/api.ts` (new), `VideoBlockNode.tsx` | this session |
| M1: Version history button in Classic mode (image + video placeholders) | `ImageBlockNode.tsx`, `VideoBlockNode.tsx` | this session |
| M2+M3: Guard toast notification + paste protection in Classic mode | `MediaGuardExtension.ts` | this session |
| M4: Drag handles for block reordering (tiptap-extension-global-drag-handle) | `TiptapEditor.tsx`, `index.css` | this session |
| M5: Copy filename button on Classic placeholders | `ImageBlockNode.tsx`, `VideoBlockNode.tsx` | this session |
| M6: Unsaved-changes dialog on AI → Classic mode switch | `ChapterEditorPage.tsx` | this session |
| E5-03: AI image generation — BE endpoint (provider-registry → AI provider → MinIO), version record, FE generateImage() API client | `media.go`, `server.go`, `config.go`, `docker-compose.yml`, `features/books/api.ts` | this session |
| E5-04: Re-generate from prompt — wired Re-generate button, fetch user models, call generateImage, loading/error states, spinner in MediaPrompt | `ImageBlockNode.tsx`, `MediaPrompt.tsx` | this session |

**9-phase workflow followed for E4-06:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-02, session 15):**

Phase 3 feature screens: 4 tasks completed.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| P3-18: Chat Page v2 — full-bleed layout, custom SSE streaming, session CRUD | `features/chat-v2/` (17 new files), `pages/ChatPageV2.tsx`, `App.tsx`, `AppNav.tsx`, `tailwind.config.cjs` | `911c249` |
| P3-20: Sharing Tab — visibility selector, unlisted link, token rotation | `features/sharing/SharingTab.tsx`, `BookDetailPageV2.tsx` | `bf83808` |
| P3-21: Book Settings Tab — metadata editing, cover image management | `features/books/SettingsTab.tsx`, `features/books/api.ts`, `BookDetailPageV2.tsx` | `b8b96b6` |
| P3-22: Universal Recycle Bin — tabbed trash, bulk actions, expiry badges | `features/trash/` (4 new files), `pages/RecycleBinPageV2.tsx`, `design-drafts/screen-recycle-bin.html` | `08e294d` |
| P3-22a+b: Recycle Bin — Chapters + Chat Sessions tabs, unified restoreItem/purgeItem | `features/trash/`, `features/books/api.ts` | `59ef220` |
| P3-19: Chat Context Integration — context picker, pills, glossary filters, format+resolve | `features/chat-v2/context/` (6 new files), `ChatInputBar`, `ChatWindow`, `MessageBubble`, `ChatPageV2`, `design-drafts/screen-chat-context.html` | `78107a1` |
| BE-S1: Fix patchBook null clearing (COALESCE bug) + getBookByID *string scan | `book-service/server.go` | `bea76f9`, `eeee14c` |
| BE-C1: Chat context field — optional `context` in SendMessageRequest, injected as system msg | `chat-service/models.py`, `stream_service.py`, `messages.py` | `bea76f9` |
| BE-S2: Gateway book proxy selfHandleResponse for multipart | `api-gateway-bff/gateway-setup.ts` | `bea76f9` |
| Integration test: chat-service (27 scenarios, all pass) | `infra/test-chat.sh` | `911c249`, `eeee14c` |
| Integration test: sharing-service (19 scenarios, all pass) | `infra/test-sharing.sh` | `bf83808` |
| Integration test: book-settings (23 scenarios, all pass) | `infra/test-book-settings.sh` | `eeee14c` |
| Docker: rebuild translation-worker (PG18 volume fix + stale image) | — | — |

**9-phase workflow followed for each task:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

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
| Wire OutputCards into assistant MessageBubble (code block extraction) | `MessageBubble.tsx`, new `utils/extractCodeBlocks.ts` | `b7dcc4c` |
| Add session export button to ChatHeader | `ChatHeader.tsx` | `b7dcc4c` |
| Add "Paste to Editor" integration via custom DOM event | New `utils/pasteToEditor.ts`, `OutputCard.tsx`, `ChapterEditorPageV2.tsx` | `b7dcc4c` |
| MinIO storage client skeleton (upload, presigned URL, delete) | New `app/storage/minio_client.py`, `__init__.py` | `b7dcc4c` |
| Binary download via MinIO presigned URLs | `app/routers/outputs.py` | `b7dcc4c` |
| MinIO bucket auto-creation on startup | `app/main.py` | `b7dcc4c` |

**What was done in this session (2026-03-29, session 5):**

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Chat-service full unit test suite (68 tests) | `tests/` (7 new files), `pytest.ini`, `requirements-test.txt` | `6847a85` |
| Fix `ensure_bucket` bug — `run_in_executor` keyword arg misuse | `app/storage/minio_client.py` | `6847a85` |

**What was done in this session (2026-03-29, session 6):**

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Backend: wire `parent_message_id` on edit_from_sequence | `app/routers/messages.py`, `app/services/stream_service.py` | `b7dcc4c` |
| Frontend: `useStreamingEdit` hook — manual SSE for edit/regenerate | `hooks/useStreamingEdit.ts` (new) | `b7dcc4c` |
| Frontend: edit mode on user messages (pencil icon → inline textarea) | `UserMessage.tsx` | `b7dcc4c` |
| Frontend: regenerate button on assistant messages (RefreshCw icon) | `AssistantMessage.tsx` | `b7dcc4c` |
| Frontend: wire edit/regenerate through MessageBubble → MessageList → ChatWindow | `MessageBubble.tsx`, `MessageList.tsx`, `ChatWindow.tsx` | `b7dcc4c` |
| Backend: Phase 3 unit tests (3 new, total 71) | `test_messages_router.py`, `test_stream_service.py` | `b7dcc4c` |

**What was done in this session (2026-03-29, session 7):**

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Fix: `message_count` drift on edit (deleted msgs not decremented) | `app/routers/messages.py` | `b7dcc4c` |
| Fix: duplicate user message in LLM context (Phase 1 bug) | `app/services/stream_service.py` | `b7dcc4c` |
| Fix: wrap edit flow in DB transaction for atomicity | `app/routers/messages.py` | `b7dcc4c` |
| Fix: conftest mock_pool supports `pool.acquire()` + `conn.transaction()` | `tests/conftest.py` | `b7dcc4c` |
| Update tests for all 3 bugfixes | `test_messages_router.py`, `test_stream_service.py` | `b7dcc4c` |
| Backend: `POST /v1/translation/translate-text` sync endpoint | `translation-service/app/routers/translate.py` (new) | `b7dcc4c` |
| New model: `TranslateTextRequest` + `TranslateTextResponse` | `translation-service/app/models.py` | `b7dcc4c` |
| Register translate router in translation-service | `translation-service/app/main.py` | `b7dcc4c` |
| Backend: translate-text unit tests (6 tests) | `tests/test_translate.py` (new) | `b7dcc4c` |
| Frontend: `translateText()` in translation API client | `features/translation/api.ts` | `b7dcc4c` |
| Frontend: per-chunk translate button in ChunkItem hover bar | `components/chunk-editor/ChunkItem.tsx` | `b7dcc4c` |
| Frontend: "Translate N chunks" in ChunkEditor selection bar | `components/chunk-editor/ChunkEditor.tsx` | `b7dcc4c` |
| Frontend: translating overlay + loading state per-chunk | `ChunkItem.tsx`, `ChunkEditor.tsx` | `b7dcc4c` |
| Frontend: wire `onTranslateChunk` in ChapterEditorPageV2 | `pages/v2-drafts/ChapterEditorPageV2.tsx` | `b7dcc4c` |

**What was done in this session (2026-04-01, session 14):**

Data Re-Engineering Phase D1 continuation: book-service JSONB handler refactor (D1-06).

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| D1-06a: getDraft — body → json.RawMessage scan (inline JSON, not base64) | `services/book-service/internal/api/server.go` | this session |
| D1-06b: patchDraft — json.RawMessage body + body_format + json.Valid + outbox event | same file | this session |
| D1-06c: getRevision — body → json.RawMessage + body_format in response | same file | this session |
| D1-06d: restoreRevision — json.RawMessage both directions + body_format + outbox event | same file | this session |
| D1-06e: listRevisions — length(body) → octet_length(body::text) for JSONB | same file | this session |
| D1-06f: exportChapter — read plain text from chapter_blocks with draft fallback | same file | this session |
| D1-06g: getInternalBookChapter — json.RawMessage body + text_content from blocks | same file | this session |
| D1-06h: createChapterRecord — outbox event for chapter.created | same file | this session |
| D1-07a: plainTextToTiptapJSON converter (pure function, _text snapshots) | `services/book-service/internal/api/tiptap.go` (new) | this session |
| D1-07a: createChapterRecord stores Tiptap JSON body with draft_format='json' | `services/book-service/internal/api/server.go` | this session |
| D1-07a: 5 unit tests for plainTextToTiptapJSON | `services/book-service/internal/api/server_test.go` | this session |
| D1-08a: getDraft adds text_content from chapter_blocks | `services/book-service/internal/api/server.go` | this session |
| D1-08b: getRevision adds text_content extracted from JSONB _text fields | same file | this session |
| D1-08d: translation-service reads text_content instead of body (2 files) | `translation_runner.py`, `chapter_worker.py` | this session |
| D1-08e: translation tests updated with text_content mock responses | `test_chapter_worker.py`, `test_translation_runner.py` | this session |
| D1-05+D1-09: worker-infra Go service scaffold (config, registry, migrate, tasks) | `services/worker-infra/` (new, 10 files) | this session |
| D1-05a: loreweave_events schema (event_log, event_consumers, dead_letter_events) | `services/worker-infra/internal/migrate/migrate.go` | this session |
| D1-09b: config loader (WORKER_TASKS, OUTBOX_SOURCES, EVENTS_DB_URL, REDIS_URL) | `services/worker-infra/internal/config/config.go` + 3 tests | this session |
| D1-09c: task registry (interface, Register, RunSelected, graceful shutdown) | `services/worker-infra/internal/registry/` + 3 tests | this session |
| D1-10a+b: outbox-relay + outbox-cleanup task implementations | `services/worker-infra/internal/tasks/` | this session |
| D1-10c: worker-infra added to docker-compose | `infra/docker-compose.yml` | this session |
| D1-11a: API client types updated (body: any, text_content, body_format) | `frontend-v2/src/features/books/api.ts` | this session |
| D1-11b: TiptapEditor refactor: JSON content, addTextSnapshots, extractText | `frontend-v2/src/components/editor/TiptapEditor.tsx` | this session |
| D1-11c: ChapterEditorPage: JSONB save/load, dirty check, discard | `frontend-v2/src/pages/ChapterEditorPage.tsx` | this session |
| D1-11d: ReaderPage: read-only TiptapEditor replaces ChapterReadView | `frontend-v2/src/pages/ReaderPage.tsx` | this session |
| D1-11e: RevisionHistory: uses text_content from API | `frontend-v2/src/components/editor/RevisionHistory.tsx` | this session |
| D1-12a: Integration test script (T01-T16 scenarios) | `infra/test-integration-d1.sh` (new) | this session |
| D1-04d: transitionChapterLifecycle tx + outbox (trash/purge) | `services/book-service/internal/api/server.go` | this session |
| P3-01: Translation Matrix Tab + translation API module | `TranslationTab.tsx`, `features/translation/api.ts` | this session |
| P3-02: Translate Modal (AI batch) | `TranslateModal.tsx`, `features/ai-models/api.ts` | this session |
| P3-05: Glossary Tab (entity list, filters, CRUD) | `GlossaryTab.tsx`, `features/glossary/api.ts`, `types.ts` | this session |
| P3-06: Kind Editor (two-panel kind browser) | `KindEditor.tsx` | this session |
| P3-07: Entity Editor (dynamic attribute form, slide-over) | `EntityEditor.tsx` | this session |
| P3-06: Kind Editor backend (6 CRUD endpoints) + frontend (full editor) | `glossary-service/kinds_crud.go`, `KindEditor.tsx` | this session |
| P3-R1: GUI review fixes (S1-S11) — glow, covers, filters, EmptyState, auth, FloatingActionBar | 9 files | this session |
| P3-R1: Editor polish — saved badge, version, metadata stats, source line numbers, status bar | `ChapterEditorPage.tsx` | this session |
| P3-R1: TranslationTab polish — checkboxes, row numbers, column headers, cell labels, summary legend, floating action bar | `TranslationTab.tsx` | this session |
| P3-R1: Glossary polish — KindEditor section headers, EntityEditor SYS/USR badges + 2-col layout + footer | `KindEditor.tsx`, `EntityEditor.tsx`, `GlossaryTab.tsx` | this session |
| Entity Editor v2 — centered modal + attribute card system (8 card types, card registry) | `components/entity-editor/` (10 new files) | this session |
| P3-R1: Reader polish — gradient bars, TOC progress/labels, chapter header/footer, font/spacing, percentage | `ReaderPage.tsx`, `index.css` | this session |

**9-phase workflow followed for each task:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-01, session 13):**

Data Re-Engineering Phase D1 continuation: chapter_blocks trigger + outbox pattern.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| D1-03: chapter_blocks table DDL (uuidv7 PK, FK CASCADE, UNIQUE index) | `services/book-service/internal/migrate/migrate.go` | `599721a` |
| D1-03: fn_extract_chapter_blocks() trigger (UPSERT from JSON_TABLE, block shrink, heading_context) | same file | `599721a` |
| D1-03: trg_extract_chapter_blocks trigger (AFTER INSERT OR UPDATE OF body) | same file | `599721a` |
| D1-04: outbox_events table DDL (partial index on pending) | same file | `f76539e` |
| D1-04: fn_outbox_notify() + trg_outbox_notify (pg_notify on INSERT) | same file | `f76539e` |
| D1-04: insertOutboxEvent() Go helper (atomic outbox write within tx) | `services/book-service/internal/api/outbox.go` (new) | `f76539e` |

**9-phase workflow followed for each task:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-03-31 to 2026-04-01, session 12):**

Part 1: Phase 2.5 E1 Tiptap editor migration. Part 2: Data Re-Engineering architecture, planning, and initial migration.

**Part 2 — Data Re-Engineering (2026-04-01):**

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Data re-engineering plan (polyglot persistence, event pipeline) | `docs/03_planning/101_DATA_RE_ENGINEERING_PLAN.md` (new) | `7d25320` |
| Technology research: PG18 + Neo4j v2026.01, remove Qdrant | `101_DATA_RE_ENGINEERING_PLAN.md` | `c94c4e5` |
| Data engineer review: _text snapshots, UPSERT, outbox pattern | `101_DATA_RE_ENGINEERING_PLAN.md` | `ed20495` |
| Outbox pattern, uuidv7 everywhere, shared events DB | `101_DATA_RE_ENGINEERING_PLAN.md` | `66190da` |
| Phase D0, pre-flight concerns, expanded D1 tasks | `101_DATA_RE_ENGINEERING_PLAN.md` | `c078343` |
| Detailed task breakdown — 8 discovery cycles (58 sub-tasks) | `docs/03_planning/102_DATA_RE_ENGINEERING_DETAILED_TASKS.md` (new) | `f6b41a5` to `04b5e08` |
| Architecture presentation (pipeline, event flow, workers) | `design-drafts/data-pipeline-architecture.html` (new) | `cc9658c` |
| Architecture diagrams (C4, ERD, DFD, deployment) | `design-drafts/architecture-diagrams.html` (new) | `8abbbeb` |
| D0-01: PG18 uuidv7() + JSON_TABLE test | manual (psql) | `6dc6a09` |
| D0-02: All 9 service migrations on PG18 | manual (psql) | `e3cfd2e` |
| D0-03: JSON_TABLE trigger test (7 scenarios) | `infra/test-pg18-trigger.sql` (new) | `bb196b3` |
| D0-04: Go pgx JSONB + json.RawMessage test | `infra/pg18test-go/` (new) | `5907dce` |
| D1-01: Postgres 16→18, add Redis, add loreweave_events | `infra/docker-compose.yml`, `infra/db-ensure.sh` | `748a519` |
| D1-02: uuidv7 everywhere, JSONB body, drop pgcrypto | 8 migration files across all services | `54a4d1f` |

**Architecture decisions recorded (session 12):**
- Postgres 18 (JSON_TABLE, virtual columns, uuidv7, async I/O)
- Neo4j v2026.01 for knowledge graph + vector search (no Qdrant needed)
- Two-layer data stack: Postgres (source of truth) → Neo4j (knowledge + vectors)
- Transactional Outbox pattern for guaranteed event delivery
- Two-worker architecture: worker-infra (Go) + worker-ai (Python)
- _text snapshots per Tiptap block (frontend pre-computes, trigger reads trivially)
- UPSERT trigger for stable block IDs across saves
- Plain text → Tiptap JSON conversion at import (no dual-mode)
- Shared loreweave_events database for centralized event management
- Frontend V2 Phase 3 paused until data re-engineering complete

**Part 1 — Phase 2.5 E1 Tiptap editor migration (2026-03-31):**

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| E1-01: Install Tiptap + extensions, remove Lexical | `package.json` | this session |
| E1-02: TiptapEditor component + FormatToolbar | `components/editor/TiptapEditor.tsx` (new), `FormatToolbar.tsx` (new) | this session |
| E1-03: Remove chunk mode, add slash menu | `components/editor/SlashMenu.tsx` (new), `pages/ChapterEditorPage.tsx` (rewrite) | this session |
| E1-04: Callout custom node (author notes) | `components/editor/CalloutNode.tsx` (new) | this session |
| E1-05: Grammar as Tiptap DecorationPlugin | `components/editor/GrammarPlugin.ts` (new) | this session |
| E1-06+07: Mode toggle Classic/AI + classic constraints | `hooks/useEditorMode.ts` (new), `SlashMenu.tsx`, `FormatToolbar.tsx` | this session |
| E1-08: Wire auto-save (5m), Ctrl+S, dirty tracking, guards, revisions | `ChapterEditorPage.tsx` | this session |
| Tiptap editor styles | `index.css` | this session |
| Bug fixes: content prop reactivity, Windows line endings, stale doc guard | `TiptapEditor.tsx`, `GrammarPlugin.ts` | this session |
| CLAUDE.md: add 9-phase task workflow with roles | `CLAUDE.md` | this session |

**Design decisions recorded:**
- Tiptap replaces both textarea (source mode) and contentEditable chunks (chunk mode) — single editor
- Plain text round-trip: backend stores plain text, HTML ↔ text conversion on load/save (until E2 block JSON)
- Auto-save at 5 minutes (not 30s) — matches Word/Excel behavior
- Classic mode: text-only slash menu; AI mode: full features including callouts
- Chunk mode fully removed (useChunks, ChunkItem, ChunkInsertRow now dead code)

**What was done in this session (2026-03-31, session 11):**

LanguageTool grammar check integration, mixed-media editor design (4 HTML drafts), and phase planning (29 new tasks).

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| LanguageTool Docker container + proxy | `infra/docker-compose.yml`, `vite.config.ts`, `nginx.conf` | this session |
| Grammar API client + decoration utilities | `src/features/grammar/api.ts` (new) | this session |
| Grammar check hooks (chunk + source mode) | `src/hooks/useGrammarCheck.ts` (new) | this session |
| ChunkItem grammar decorations (wavy underlines) | `src/components/editor/ChunkItem.tsx` | this session |
| Grammar toggle + wiring in editor page | `src/pages/ChapterEditorPage.tsx`, `src/index.css` | this session |
| Design: AI Assistant mode editor | `design-drafts/screen-editor-mixed-media.html` (new) | this session |
| Design: Classic mode editor | `design-drafts/screen-editor-classic.html` (new) | this session |
| Design: Mode spec + guards + version model | `design-drafts/screen-editor-modes.html` (new) | this session |
| Design: Media version history UI | `design-drafts/screen-editor-version-history.html` (new) | this session |
| Phase 2.5/3.5/4.5 planning (29 new tasks) | `docs/03_planning/99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | this session |

**Design decisions recorded:**
- Tiptap (ProseMirror) chosen as editor engine -- replaces textarea + contentEditable chunks
- Two editor modes: Classic (pure writing, media locked) / AI Assistant (full features)
- Block types: paragraph, heading, divider, callout, image, video, code
- AI prompt stored on every media block (re-generation + AI context + audit trail)
- Audio/TTS per paragraph -- AI generate or manual upload, hidden by default
- Media version tracking with prompt snapshots + versioned MinIO paths
- Classic mode guards protect media blocks from accidental deletion
- Phase 2.5 (Tiptap migration) must complete before Phase 3

**What was done in this session (2026-03-31, session 10):**

Chapter editor unsaved-changes guard, universal dialog system, and toast infrastructure.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| `EditorDirtyContext` — owns `pendingNavigation`, `guardedNavigate`, `confirmNavigation` | `src/contexts/EditorDirtyContext.tsx` (new) | this session |
| Universal `ConfirmDialog` — icon, `extraAction` (3rd button), auto-stacked layout | `src/components/shared/ConfirmDialog.tsx` | this session |
| `UnsavedChangesDialog` — thin wrapper: Save & leave / Discard & leave / Stay | `src/components/shared/UnsavedChangesDialog.tsx` (new) | this session |
| `EditorLayout` — all nav links guarded via context `guardedNavigate`; logout uses `ConfirmDialog` | `src/layouts/EditorLayout.tsx` | this session |
| `ChapterEditorPage` — breadcrumb + prev/next guard; Discard button; in-place `ConfirmDialog`; navigation `UnsavedChangesDialog` | `src/pages/ChapterEditorPage.tsx` | this session |
| Install `sonner`; wire `<Toaster>` in `App.tsx` | `src/App.tsx`, `package.json` | this session |
| Replace save badge + error banner with `toast.success/error` in editor | `ChapterEditorPage.tsx` | this session |
| `RevisionHistory` — restore success/error now uses toast | `src/components/editor/RevisionHistory.tsx` | this session |
| `ChaptersTab` — download success, download/trash/create errors now use toast (were silently swallowed) | `src/pages/book-tabs/ChaptersTab.tsx` | this session |

**Design decisions recorded:**
- Error/warning *dialogs* are NOT added — toast covers transient feedback; inline errors stay for form context (login, register, import dialog, page-load errors)
- `ConfirmDialog` is the single universal primitive: 2-button (default) or 3-button (when `extraAction` passed) — buttons auto-stack vertically on 3-button layout
- `window.confirm/alert` fully eliminated from frontend-v2

**What was done in this session (2026-03-30, session 9):**

Frontend V2 planning + CI cleanup + branch hygiene.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Remove stale Module 01 CI workflow (was spamming email on every push) | `.github/workflows/loreweave-module01.yml` (deleted) | `6f14c26` (PR #2) |
| Review all git branches — all local branches merged into main, safe to clean | — | — |
| Full GUI audit: identified 10 structural issues (layout, nav, components, forms) | — | — |
| Design navigation architecture: sidebar, 3 layout types, breadcrumbs, route map | — | — |
| Create component catalog HTML draft (cold zinc theme) | `design-drafts/components-v2.html` | — |
| Create warm literary theme draft (amber/teal, Lora serif, approved) | `design-drafts/components-v2-warm.html` | — |
| Fix Tailwind CDN color rendering (HSL → CSS variables + hex) | `design-drafts/components-v2-warm.html` | — |
| Write Frontend V2 Rebuild Plan (full planning doc) | `docs/03_planning/99_FRONTEND_V2_REBUILD_PLAN.md` | — |

**What was done in this session (2026-03-30, session 8):**

Code review + hardening pass across chat-service, translation-service, and frontend.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Fix: entire edit flow (DELETE + INSERT + UPDATE) in single transaction | `chat-service/app/routers/messages.py` | `b7dcc4c` |
| Fix: safe format_map — unknown `{placeholders}` pass through unchanged | `translation-service/app/routers/translate.py` | `b7dcc4c` |
| Fix: add `min_length=1, max_length=30000` to TranslateTextRequest.text | `translation-service/app/models.py` | `b7dcc4c` |
| Fix: "auto" source_language now returns "auto-detect" (better prompt text) | `translation-service/app/routers/translate.py` | `b7dcc4c` |
| Fix: handle malformed provider response (JSON parse + missing keys → 502) | `translation-service/app/routers/translate.py` | `b7dcc4c` |
| Fix: use user's `invoke_timeout_secs` preference instead of hard-coded 120 | `translation-service/app/routers/translate.py` | `b7dcc4c` |
| Add: structured logging in translate endpoint | `translation-service/app/routers/translate.py` | `b7dcc4c` |
| Fix: stale closure in ChunkEditor translateChunk (remove translatingIndices dep) | `frontend/src/components/chunk-editor/ChunkEditor.tsx` | `b7dcc4c` |
| Fix: bulk translate shows toast on partial failures | `frontend/src/components/chunk-editor/ChunkEditor.tsx` | `b7dcc4c` |
| Fix: per-chunk translate passes book's target_language to API | `frontend/src/pages/v2-drafts/ChapterEditorPageV2.tsx` | `b7dcc4c` |
| Test: malformed provider response → 502 | `translation-service/tests/test_translate.py` | `b7dcc4c` |
| Test: user timeout preference used in httpx client | `translation-service/tests/test_translate.py` | `b7dcc4c` |
| Update: chat-service tests for new transaction boundary | `chat-service/tests/test_messages_router.py` | `b7dcc4c` |

**Test coverage:**
- `test_output_extractor.py` — 8 tests (pure function, code block extraction)
- `test_auth.py` — 5 tests (JWT validation, expiry, wrong secret)
- `test_sessions_router.py` — 10 tests (CRUD, 404s, validation)
- `test_outputs_router.py` — 14 tests (CRUD, download, export, MinIO redirect)
- `test_messages_router.py` — 11 tests (list, send, streaming, archived, provider 404, edit, normal parent)
- `test_stream_service.py` — 7 tests (text deltas, persistence, artifacts, errors, model strings, history, parent_message_id)
- `test_minio_client.py` — 5 tests (upload, presigned, delete, bucket create/noop)
- `test_clients.py` — 4 tests (provider resolve, billing log, error swallowing)
- `test_translate.py` — 8 tests (success, override lang, 402, 500→502, no model, missing text, malformed response, user timeout)

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

### Frontend V2 Rebuild

Design document: `docs/03_planning/99_FRONTEND_V2_REBUILD_PLAN.md`
Visual drafts: `design-drafts/components-v2-warm.html` (approved)

| Phase | Scope | Status |
| ----- | ----- | ------ |
| Phase 1 | Scaffold, layout shell, sidebar, routing, auth pages, copy API layer | **Done** |
| Phase 2 | Core screens: Books list, Book Detail (tabs), Chapter Editor | **Done** |
| **Phase 2.5** | **Editor Engine: Tiptap migration, block JSON, grammar, mode toggle** | **E1 Done (GATE passed), E2+E3 → moved to Data Re-Engineering** |
| Phase 3 | Feature screens: Translation, Glossary, Chat, Sharing | **Done** |
| **Phase 3.5** | **Media Blocks: image/video/code, AI prompt, version tracking** | **Done (E4: 8 tasks + E5: 4 tasks = 12 tasks, session 16)** |
| Phase 4 | Secondary: Settings, Usage, Browse + polish | Planned |
| **Phase 4.5** | **Audio/TTS: per-paragraph narration, bulk generate, audiobook export** | After Phase 4 |

### Chat Service (paused — frontend rebuild takes priority)

Design document: `docs/03_planning/98_CHAT_SERVICE_DESIGN.md`

| Phase | Scope | Status |
| ----- | ----- | ------ |
| Phase 1-3 | Backend + frontend chat (sessions, streaming, editing) | ✅ Done |
| Phase 4 | File attachments + multi-modal | Planned (after frontend-v2 Phase 3) |

### Immediate candidates

| Priority | Item | Notes |
| -------- | ---- | ----- |
| **P0** | **MIG-03..MIG-09: Remaining V1→V2 page migrations** | 7 pages: Usage, Settings, Browse, Public Book, Unlisted, Chapter Translations |
| **P0** | **MIG-10: Delete old `frontend/` directory** | After all migrations complete |
| **P1** | **P3-08a/b: Genre Groups [BE+FE]** | Needs new backend tables, unblocks glossary polish |
| P1 | Translation Workbench | Block-level translation (design draft exists), Phase 3.5 done |
| P1 | Phase 4: Settings, Usage, Browse + polish | Overlaps with MIG-03..08 |
| P2 | GUI Review deferred items (D1-D22) | Editor polish, glossary polish, reader polish |
| P2 | Platform Mode (103_PLATFORM_MODE_PLAN.md) | 35 tasks, deferred |
| P2 | Phase 4.5: Audio/TTS | Per-paragraph narration (design draft exists) |
| P3 | Full acceptance evidence pack for M01-M05 | Currently smoke only |

> **Architecture decision (session 12):** Frontend V2 Phase 3 paused. The glossary/wiki/chat features
> depend on a knowledge layer that doesn't exist yet. Building GUI against the current schema would be
> throwaway work. Data re-engineering plan executes first:
> - Postgres JSONB for chapter content (replaces TEXT body)
> - Event-driven pipeline (Redis Streams) for extensible processing
> - chapter_blocks table for RAG-ready denormalized text
> - Neo4j knowledge graph for entities/events/relations (future knowledge-service)
> - Qdrant vector DB for embeddings (future RAG pipeline)
> See `docs/03_planning/101_DATA_RE_ENGINEERING_PLAN.md` for full plan.

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
| BLK-01 | Formal acceptance evidence packs not produced for M01-M05 | Medium | QA |
| ~~BLK-02~~ | ~~M05 not started~~ | ~~Resolved~~ | ~~Tech Lead~~ |

> BLK-02 resolved: M05 Glossary & Lore Management is complete (closed smoke).

---

## Session History (recent)

| Date       | What happened | Key commits |
| ---------- | ------------- | ----------- |
| 2026-04-03 | Session 16: Phase 3.5 (E4+E5, 12 tasks), video-gen-service skeleton, M1-M6 (design draft gaps), MIG-01 (Trash page), MIG-02 (Chat page), code block fixes (5 iterations), image block fixes (upload wiring, MinIO URL, mode switch, hover overlay), removed localStorage cache persistence, planning docs (VG, MV, VH, TR, MIG). 53 commits. | `40bb7b1`..`bec9eef` |
| 2026-04-02 | Session 15: Phase 3 FE complete (P3-18/19/20/21/22/22a+b), BE fixes (patchBook null, chat context field, gateway proxy), 5 integration test scripts (120 total scenarios), Docker fix | `911c249`..`eeee14c` |
| 2026-04-02 | Session 14: D1 complete (D1-06→D1-12), Phase 3 FE (P3-01→P3-07), GUI review (5 drafts, 41 fixes), React Query, entity editor v2, Platform Mode plan | session 14 |
| 2026-04-01 | Data re-engineering D1-06→D1-12: JSONB handlers, Tiptap import, text_content, worker-infra, frontend JSONB, integration tests | session 14 |
| 2026-04-01 | Data re-engineering D1-03 (chapter_blocks + trigger) + D1-04 (outbox_events + pg_notify + helper) | `599721a`, `f76539e` |
| 2026-04-01 | Data re-engineering: D0 pre-flight (4/4 pass), D1-01 (PG18+Redis), D1-02 (uuidv7+JSONB) | `54a4d1f` |
| 2026-03-31 | Phase 2.5 E1: Tiptap editor migration (8 tasks), bug fixes, workflow update | `4f39cf7` |
| 2026-03-31 | LanguageTool integration, mixed-media editor design (4 drafts), Phase 2.5/3.5/4.5 planning | session 11 |
| 2026-03-31 | Unsaved-changes guard (EditorDirtyContext, UnsavedChangesDialog), universal ConfirmDialog, toast system (sonner) | this session |
| 2026-03-30 | Frontend V2 planning: GUI audit, design drafts (warm literary theme), rebuild plan, CI cleanup | `6f14c26` (PR #2) |
| 2026-03-30 | Code review hardening: transaction fix, safe format_map, response validation, stale closure fix, bulk error UX | `b7dcc4c` |
| 2026-03-29 | Visibility fix, unified chapter editor, ChunkEditor system + selection, chat service, test fixes | `bf17136`, `e9d1c29`, `23bad63`, `fd4a5ea`, `3cb8e4c`, `2f47c89`, `b32f415` |
| 2026-03-23 | M04 translation pipeline implementation (backend + frontend) | — |
| 2026-03-22 | M03 provider registry implementation (backend + frontend) | — |
| 2026-03-21 | M02 UI/UX wave (BookDetailPageV2, reader pages, responsive) | — |

---

## Deferred Items (cross-module)

| Item | Status | Planned direction | Marker doc |
| ---- | ------ | ----------------- | ---------- |
| Physical garbage collector for purge_pending objects | Not implemented | Background GC worker | — |
| Gitea integration for chapter version control | Not implemented | ADR needed first | — |
| Non-text chapter formats (pdf, docx, html, OCR) | Not implemented | Future MIME extension wave | — |
| Paid storage tiers / billing integration | Not implemented | Future monetization wave | — |
| AI-generated summaries / covers | Not implemented | Future AI feature wave | — |
| Production rollout hardening (SRE, security sign-off) | Not done | Pre-release gate wave | — |
| SSE / WebSocket streaming progress for translation jobs | Not implemented | Currently polling | — |
| **Structured book/chapter zip import-export** (portable bundles with metadata, revisions, assets) | Not implemented | Post-V1 feature wave | `100_FUTURE_FEATURE_STRUCTURED_IMPORT_EXPORT_MEDIA.md` |
| **Media-rich chapters** — images and video for visual novel-style storytelling | **Phase 3.5 Done** | E4+E5 complete, image/video/code blocks | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` |
| **Video generation provider integration** — connect video-gen-service to real providers (Sora, Veo, etc.) | Skeleton deployed | 10 tasks planned (VG-01..VG-10) | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` |
| **Media version retention** — auto-delete old versions, retention policy, MinIO GC, storage usage UI | Planned | 7 tasks (MV-01..MV-07) | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` |
