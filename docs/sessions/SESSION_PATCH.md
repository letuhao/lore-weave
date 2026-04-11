# SESSION_PATCH — LoreWeave Project Status

> **Source of truth for current project state.**
> Update this file at the end of every session AND at each phase/sub-phase transition.

---

## Document Metadata

- Last Updated: 2026-04-11 (session 32 — V2 redesign + cloud readiness audit)
- Updated By: Assistant (V2 architecture redesign, cloud/mobile audit — 46 issues found)
- Active Branch: `main`
- HEAD: `6e1d81e` (V2 streaming TTS doc)
- **Session Handoff:** `docs/sessions/SESSION_HANDOFF_V3.md` — full context for next agent

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

**Phase 9: COMPLETE (12/12).** All phases 8A-8H + Phase 9 done. No placeholder tabs remain.

**Translation Pipeline V2: IMPLEMENTED (P1-P8).** All 8 priorities from V2 design doc implemented. Proven with real Ollama gemma3:12b model calls.

**Glossary Extraction Pipeline: FULLY COMPLETE (BE + FE + TESTED).** 13 BE tasks + 7 FE tasks + 49 integration test assertions + browser smoke test. Tested with real Qwen 3.5 9B model via LM Studio. 90 entities extracted from 5 chapters.

**Voice Pipeline V2: DESIGN COMPLETE (v2.2 — chat-service integration).** Architecture redesigned in session 32. Implementation NOT started — blocked by cloud readiness work below.

**Cloud Readiness & Multi-Device Audit: HIGHEST PRIORITY.** Full codebase audit found 46 issues across 4 categories. Must fix before new feature work.

### Cloud Readiness Task List

**P0 — Security / Broken (fix immediately):**

| Task | Scope | Files |
|------|-------|-------|
| **CRA-01** | Remove hardcoded secret defaults in chat-service config | `services/chat-service/app/config.py` |
| **CRA-02** | Remove hardcoded `minioadmin` defaults in video-gen-service | `services/video-gen-service/app/routers/generate.py` |
| **CRA-03** | Make `MINIO_EXTERNAL_URL` env-only, no localhost default | `infra/docker-compose.yml` |
| **CRA-04** | Chat layout mobile — responsive sidebar (drawer/overlay on mobile) | `pages/ChatPage.tsx`, `SessionSidebar` |
| **CRA-05** | Settings panels — responsive width (max-w-full on mobile) | `SessionSettingsPanel.tsx`, `VoiceSettingsPanel.tsx` |

**P1 — Data Sync / Scalability / Usability:**

| Task | Scope | Files |
|------|-------|-------|
| **CRA-06** | Sync `lw_tts_prefs` to server via `/v1/me/preferences` | `components/reader/TTSSettings.tsx` |
| **CRA-07** | Sync `lw_voice_prefs` to server via `/v1/me/preferences` | `features/chat/voicePrefs.ts` |
| **CRA-08** | Sync `lw_language` to server via `/v1/me/preferences` | `features/settings/LanguageTab.tsx` |
| **CRA-09** | Sync `loreweave:media-prefs` to server via `/v1/me/preferences` | `features/settings/ReadingTab.tsx` |
| **CRA-10** | Migrate `lw_reader_theme` to ThemeProvider (which already syncs) | `providers/ReaderThemeProvider.tsx` |
| **CRA-11** | DB connection pool tuning — all Go services (set `pool_max_conns`) | All Go service `config.go` files |
| **CRA-12** | DB connection pool tuning — Python services (`pool_size`, `max_overflow`) | `chat-service`, `translation-service` |
| **CRA-13** | Hover-only buttons → visible on touch (long-press or always-visible on mobile) | `AssistantMessage`, `UserMessage`, `SessionSidebar`, `NotificationBell`, `GlossaryTab`, `KindEditor` |
| **CRA-14** | AudioContext autoplay fix — call `resume()` inside user-gesture handler | `lib/TTSPlaybackQueue.ts`, `BargeInDetector.ts` |
| **CRA-15** | Voice mode fallback message for unsupported browsers (Firefox, Samsung Internet) | `hooks/useSpeechRecognition.ts` |

**P2 — Deploy Config / Polish:**

| Task | Scope | Files |
|------|-------|-------|
| **CRA-16** | Add healthcheck blocks to docker-compose for all services | `infra/docker-compose.yml` |
| **CRA-17** | Service discovery — env-var override layer for ECS/Cloud Map | `infra/docker-compose.yml`, all service configs |
| **CRA-18** | Redis persistence — document ElastiCache AOF requirement | `infra/` docs |
| **CRA-19** | NestJS graceful shutdown — `app.enableShutdownHooks()` | `services/api-gateway-bff/src/main.ts` |
| **CRA-20** | Touch targets — increase button sizes to 44px minimum | `ChatHeader.tsx`, `ChatInputBar.tsx` |
| **CRA-21** | DataTable — `overflow-x-auto` instead of `overflow-hidden` | `components/data/DataTable.tsx` |
| **CRA-22** | VoiceModeOverlay — add tap-to-cancel, increase control sizes | `VoiceModeOverlay.tsx` |
| **CRA-23** | Format pills — flex-wrap or horizontal scroll on mobile | `ChatInputBar.tsx` |
| **CRA-24** | Remove localhost fallbacks from Go service configs (fail on missing env) | All Go service `config.go` files |
| **CRA-25** | Remove localhost fallbacks from gateway-bff config | `services/api-gateway-bff/src/main.ts` |
| **CRA-26** | MinIO SDK abstraction in book-service (swap to S3-compatible interface) | `services/book-service/internal/api/` |

**Total: 26 tasks (5 P0, 10 P1, 11 P2)**

### What was done in this session (2026-04-11, session 32):

**Part 1 — Voice Pipeline V2 architecture redesign (3 iterations):**
1. Original V2 (session 31): client-side `VoicePipelineController` state machine
2. V2.1: Vercel Workflow server-side orchestration → **rejected** (Vercel-only platform, doesn't run on AWS, wrong abstraction for voice)
3. V2.2: chat-service integration → **accepted** — voice is a new endpoint in existing chat-service, extends `stream_response()` with STT input + TTS output. No new service, no framework, ~70% code shared with text chat
4. 6-perspective review (architecture, cloud/infra, performance, security, data, UX) found 46 V2 issues → all resolved

**Part 2 — Cloud readiness & multi-device audit:**
- 4-perspective parallel audit: frontend local storage, backend cloud issues, multi-device compat, platform lock-in
- Found 46 issues across the codebase (separate from V2 issues)
- Created CRA-01..26 task list as highest priority work

| Work item | Files | Status |
| --------- | ----- | ------ |
| V2 architecture doc — 3 iterations + 46-issue review | `docs/03_planning/data_pipelines/VOICE_PIPELINE_V2.md` | Design complete |
| Cloud readiness audit — 4 perspectives, 46 issues | SESSION_PATCH.md (this section) | Audit complete, tasks created |
| Hosting direction decision | Memory: project_hosting_direction.md | Cloud (AWS), not local-only |

**Key decisions:**
- LoreWeave targets cloud hosting (AWS) — multi-device (PC, mobile, tablet)
- All user preferences must sync to server (DB), localStorage is cache only
- No platform lock-in (Vercel Workflow rejected, no Vercel dependencies found except 1 header string)
- Cloud readiness (CRA-01..26) is highest priority — before Voice Pipeline V2 implementation
- Voice Pipeline V2 (43 tasks) blocked until CRA work complete

**What was done in previous session (2026-04-10→11, session 31):**

Five major areas completed: GEP end-to-end, Voice Mode for chat, AI Service Readiness infrastructure, Real-Time Voice pipeline (RTV), Voice Pipeline V2 architecture design. 50+ commits total.

| Work item | Files | Commit |
| --------- | ----- | ------ |
| GEP BE fixes: 10 bugs from real AI model testing (worker wiring, internal invoke, reasoning model support, truncated JSON repair, adapter params) | 6 files across 3 services | `3c5202a` |
| GEP-BE-13: Integration test script (49 assertions: cancellation, multi-batch, concurrent, dedup, API validation) | `infra/test-gep-integration.sh` | `5b66021` |
| GEP-FE-01: Extraction types + API layer | `features/extraction/types.ts`, `api.ts` | `d6f2a14` |
| GEP-FE-02: Wizard shell + extraction profile step + i18n (4 languages) | `ExtractionWizard.tsx`, `StepProfile.tsx`, `useExtractionState.ts`, 4 locale files | `10ee995` |
| GEP-FE-03: Batch config step | `StepBatchConfig.tsx` | `5b11bfb` |
| GEP-FE-04: Estimate & confirm step | `StepConfirm.tsx` | `9693a7a` |
| GEP-FE-05: Progress + results steps | `StepProgress.tsx`, `StepResults.tsx`, `useExtractionPolling.ts` | `be7e7e1` |
| GEP-FE-06: Entry point wiring (GlossaryTab, ChaptersTab, TranslationTab) | 3 tab files | `8a4ce0b` |
| GEP-FE-07: Alive badge + toggle on entity list | `GlossaryTab.tsx`, `glossary/api.ts` | `90a7410` |
| Browser smoke test: 9 screens verified (Playwright MCP) | — | — |
| Session/plan audit: SESSION_PATCH + 99A planning doc markers updated | docs | `3f33d69`, `79264c4` |
| **Voice Mode (VM-01..VM-06):** | | |
| VM-01: useSpeechRecognition hook (Web Speech API, factory pattern) | `hooks/useSpeechRecognition.ts` | `077d97d` |
| VM-02: Voice settings panel + STT/TTS model selectors, i18n 4 langs | `VoiceSettingsPanel.tsx`, `voicePrefs.ts`, 4 locale files | `ba2242f` |
| VM-01+02 review: 4 issues (singleton→factory, stale closure, restart cap, backdrop) | 2 files | `b03ef0b` |
| VM-03+04: Voice mode orchestrator + push-to-talk mic button | `useVoiceMode.ts`, `ChatInputBar.tsx` | `eaac89f` |
| VM-05: Voice mode overlay (waveform, transcript, controls) | `VoiceModeOverlay.tsx`, `WaveformVisualizer.tsx` | `5f265ff` |
| VM-06: Integration wiring (ChatHeader + ChatWindow) | `ChatHeader.tsx`, `ChatWindow.tsx` | `1542208` |
| VM review: 13 issues (stale closures, session change, ARIA, dual STT) | 7 files | `0d7318a` |
| **External AI Service Integration Guide:** | | |
| Integration guide: 830 lines, 4 service types (TTS/STT/Image/Video) | `docs/04_integration/` | `d62c4c4` |
| Spec alignment: verified against OpenAI Python SDK (2025-12) | docs | `a37ff4e` |
| Streaming TTS/STT contracts + known limitations section | docs | `75e1b4f` |
| **AI Service Readiness (AISR-01..05):** | | |
| AISR-01: Gateway /v1/audio/* proxy routes (TTS, STT, voices) | `gateway-setup.ts`, `docker-compose.yml` | `89bfc74` |
| AISR-02: Mock audio service (Python/FastAPI, sine-wave TTS, mock STT) | `infra/mock-audio-service/` | `96b8b10`, `d17f7fd` |
| AISR-03: useBackendSTT hook (MediaRecorder → multipart upload) | `hooks/useBackendSTT.ts` | `114358b` |
| AISR-04: useStreamingTTS hook (fetch → AudioContext playback) | `hooks/useStreamingTTS.ts` | `14541fc` |
| AISR-05: Integration test script (19 assertions) | `infra/test-audio-service.sh` | `bdb2153` |
| AISR-03+04 review: 20 issues (AudioContext leaks, race conditions, Safari) | 3 files | `e54557e` |
| **Real-Time Voice Pipeline (RTV-01..04):** | | |
| RTV-01+02: SentenceBuffer + TTSPlaybackQueue (18 unit tests) | `lib/SentenceBuffer.ts`, `lib/TTSPlaybackQueue.ts` | (earlier commits) |
| RTV-03: Wire streaming TTS pipeline into voice mode + review (16 issues) | `useVoiceMode.ts`, `TTSConcurrencyPool.ts` | `b9beb86`, `4f8d50b` |
| RTV-04: Barge-in detection + review (16 issues) | `BargeInDetector.ts` | `02409b1`, `0098584` |
| Voice settings button in chat header + TTS voice selector | `ChatHeader.tsx`, `VoiceSettingsPanel.tsx` | `e425587`, `6b48cb3` |
| Fix: STT language region strip, live metrics overlay | `useBackendSTT.ts`, `VoiceModeOverlay.tsx` | `91edae5`, `8ff758c` |
| Fix: double-send (imperative pipeline), infinite loop (noise), generation counter | `useVoiceMode.ts` | `425b05d`, `eaa66e5`, `8827928` |
| Fix: Silero VAD integration (4 iterations: nginx MIME, CDN, vite-plugin-static-copy) | `useBackendSTT.ts`, `nginx.conf`, `vite.config.ts` | `e117db6` + 5 fix commits |
| **Voice Pipeline V2 Architecture (design-only):** | | |
| V2 architecture doc: strict state machine, audio persistence, text normalizer | `VOICE_PIPELINE_V2.md` | `ee77ac8`, `5fac900` |
| 5 review rounds (context/data/UX/security/performance): 39 issues addressed | `VOICE_PIPELINE_V2.md` | `5b666c8` |
| Phase E (voice assist mode), Phase D (metrics), streaming TTS | `VOICE_PIPELINE_V2.md` | `4a05419`, `2fa1f40`, `6e1d81e` |
| Competitor review (OpenAI Realtime, Pipecat, LiveKit, ElevenLabs) + 5 latency optimizations | `VOICE_PIPELINE_V2.md` | uncommitted |

**9-phase workflow followed for each FE task:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in previous session (2026-04-10, session 30):**

| Issue | Severity | Fix |
| ----- | -------- | --- |
| C1: Wrong config attr `provider_registry_url` | Critical | → `provider_registry_service_url` |
| C2: Silent `_, _` on 4 DB inserts in glossary upsert | Critical | → `slog.Warn` on all 4 |
| C3: Missing `json.RawMessage` cast in book-service | Critical | → Cast added in both GET responses |
| H1: No top-level try/except in extraction worker | High | → Split into handler + inner runner |
| H2: Silent batch failure in LLM invoke | High | → Log with batch index + kind codes |
| H3: Unbounded known_entities accumulation | High | → Capped at 200 |
| H4: `import json` inside function body | High | → Moved to top-level |
| M1: Hardcoded cost estimate without context | Medium | → Added design reference comment |
| M2: `ent.pop("relevance")` mutates parsed dict | Medium | → Changed to `ent.get()` |
| M3: No upper bound on queryInt limits | Medium | → Clamp recency≤1000, limit≤500 |

**Commits (session 30):**
- Prior commits: GEP-BE-01..12 (see git log for full list)
- `0a07766` fix: post-review fixes for GEP extraction pipeline (10 issues)

**What was done in previous session (2026-04-09, session 29):**

Translation Pipeline V2 — full implementation (9-phase workflow). PoC first (3 scripts with real AI model calls), then full implementation across 2 services.

| Work item | Files touched | Status |
| --------- | ------------- | ------ |
| P1: CJK-aware token estimation | `chunk_splitter.py` | Done |
| P1b: Expansion-ratio budget + 40-block cap | `block_batcher.py` | Done |
| P2: Output validation + retry (2 retries with correction prompt) | `session_translator.py` | Done |
| P3: Multi-provider token extraction (OpenAI/Anthropic/Ollama/LM Studio) | `session_translator.py` | Done |
| P4: Glossary context injection (tiered, scored, JSONL) | `glossary_client.py` (new), `session_translator.py` | Done |
| P4b: Internal glossary endpoint | `glossary-service/server.go` | Done |
| P5: Rolling context between batches | `session_translator.py` | Done |
| P6: Auto-correct post-processing (source term replacement) | `glossary_client.py` | Done |
| P7: Cross-chapter memo table + load/save | `migrate.py`, `chapter_worker.py` | Done |
| P8: Quality metrics columns (validation_errors, retry_count, etc.) | `migrate.py` | Done |
| Config: glossary-service URL | `config.py`, `docker-compose.yml` | Done |
| Tests: 31 new V2 tests (280 total pass) | 4 test files | Done |
| PoC: 3 real AI model scripts | `poc_v2_real.py`, `poc_v2_glossary.py` | Done |
| Fix: glossary endpoint Tier 2 fallback (no chapter_entity_links) | `glossary-service/server.go` | Done |
| Fix: provider-registry forward usage tokens in invoke response | `provider-registry-service/server.go` | Done |
| Fix: translated_body_json JSONB string parse in Pydantic model | `models.py` | Done |
| Docker integration test: 132-block chapter, glossary 12 entries, in=5223 out=3670 | real Ollama gemma3:12b | Pass |

**3 commits:**
- `662cbf7` feat: Translation Pipeline V2 — CJK fix, glossary injection, validation
- `1aa25b3` fix: glossary endpoint fallback when no chapter_entity_links exist
- `6db8553` fix: forward usage tokens in provider-registry, parse JSONB string in models

**Integration test results (Docker Compose, real Ollama gemma3:12b):**
- Chapter 1 (132 blocks): 4 batches (40+40+40+12), all valid first attempt, ~68s
- Chapter 2 (113 blocks): 3 batches (40+40+33), all valid first attempt, ~51s, in=5223 out=3670
- Glossary: 12 entries injected (~179 tokens), correction rules active
- Token counts: now flowing correctly from Ollama → provider-registry → translation-service → DB

**9-phase workflow followed:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in previous session (2026-04-09, session 28):**

P9-08a Wiki article CRUD + revisions — backend implementation in glossary-service. 2 tables (wiki_articles, wiki_revisions), 9 endpoints, wiki_handler.go (new), migration, routes. Review: 3 fixes (spoiler init, rows.Err checks). Integration tests: 75/75 pass.

| Work item | Files touched | Status |
| --------- | ------------- | ------ |
| Migration: wiki_articles + wiki_revisions tables | `glossary-service/internal/migrate/migrate.go` | Done |
| Wiki handler: 9 endpoints (list, create, get, patch, delete, list revisions, get revision, restore, generate) | `glossary-service/internal/api/wiki_handler.go` (new) | Done |
| Route registration | `glossary-service/internal/api/server.go` | Done |
| Migration call in main.go | `glossary-service/cmd/glossary-service/main.go` | Done |
| Review fixes: spoiler init, rows.Err checks (2 locations) | `wiki_handler.go` | Done |
| Integration tests: 75 scenarios | `infra/test-wiki.sh` (new) | Done |

**9-phase workflow followed for P9-08a:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

P9-08b Wiki settings + public reader API — cross-service. book-service: wiki_settings JSONB column, PATCH support, projection + getBookByID include field. glossary-service: 2 public endpoints (list + get), visibility gate, spoiler filtering. 21 new integration tests (96 total).

| Work item | Files touched | Status |
| --------- | ------------- | ------ |
| Migration: wiki_settings JSONB on books | `book-service/internal/migrate/migrate.go` | Done |
| PATCH + GET + projection: wiki_settings field | `book-service/internal/api/server.go` | Done |
| Glossary book_client: parse wiki_settings from projection | `glossary-service/internal/api/book_client.go` | Done |
| Public endpoints: publicListWikiArticles + publicGetWikiArticle | `glossary-service/internal/api/wiki_handler.go` | Done |
| Public routes: /wiki/public, /wiki/public/{article_id} | `glossary-service/internal/api/server.go` | Done |
| Integration tests: 21 new (T47-T62), 96 total | `infra/test-wiki.sh` | Done |

**9-phase workflow followed for P9-08b:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

P9-08c Community suggestions — glossary-service. 1 table (wiki_suggestions), 3 endpoints (submit, list, accept/reject). Auth gates: any user can suggest, only owner can review. Accept applies diff + creates community revision. community_mode gate. 26 new integration tests (122 total).

| Work item | Files touched | Status |
| --------- | ------------- | ------ |
| Migration: wiki_suggestions table | `glossary-service/internal/migrate/migrate.go` | Done |
| Migration call in main.go | `glossary-service/cmd/glossary-service/main.go` | Done |
| Suggestion handlers: submit, list, review (accept/reject) | `glossary-service/internal/api/wiki_handler.go` | Done |
| Routes: /suggestions at book + article level | `glossary-service/internal/api/server.go` | Done |
| Integration tests: 26 new (T63-T80), 122 total | `infra/test-wiki.sh` | Done |

**9-phase workflow followed for P9-08c:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

P9-08d Wiki FE reader tab — frontend. WikiTab component (3-column: sidebar + article + ToC), API client, types, i18n 4 languages. Wired into BookDetailPage tab system.

| Work item | Files touched | Status |
| --------- | ------------- | ------ |
| Types: WikiArticleListItem, WikiArticleDetail, WikiInfoboxAttr, etc. | `features/wiki/types.ts` (new) | Done |
| API client: listArticles, getArticle, listRevisions | `features/wiki/api.ts` (new) | Done |
| WikiTab: sidebar (grouped by kind, search, filter), article view (ContentRenderer + infobox), ToC | `pages/book-tabs/WikiTab.tsx` (new) | Done |
| i18n: 4 languages (en, vi, ja, zh-TW) | `i18n/locales/*/wiki.json` (4 new) | Done |
| i18n registration | `i18n/index.ts` | Done |
| BookDetailPage: wire WikiTab, remove placeholder | `pages/BookDetailPage.tsx` | Done |

**9-phase workflow followed for P9-08d:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

P9-08e Wiki FE editor — WikiEditorPage with TiptapEditor, save/publish, infobox sidebar, revision history, suggestion review. Full wiki API client (create, patch, delete, generate, revisions, suggestions). Route + edit button in WikiTab.

| Work item | Files touched | Status |
| --------- | ------------- | ------ |
| Wiki API extensions: create, patch, delete, generate, getRevision, restore, suggestions | `features/wiki/api.ts` | Done |
| Types: WikiRevisionDetail, WikiSuggestionResp, WikiSuggestionListResp | `features/wiki/types.ts` | Done |
| WikiEditorPage: TiptapEditor, save, publish toggle, infobox, revision history, suggestions | `pages/WikiEditorPage.tsx` (new) | Done |
| Route: /books/:bookId/wiki/:articleId/edit under EditorLayout | `App.tsx` | Done |
| WikiTab: Edit button navigating to editor | `pages/book-tabs/WikiTab.tsx` | Done |

**9-phase workflow followed for P9-08e:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in previous session (2026-04-08, session 27):**

P9-02 User Profile — full-stack implementation. Backend: bio/languages fields, public profile endpoint, follow system (table + 4 endpoints), favorites system (table + 3 endpoints), catalog author filter, translator stats endpoint. Frontend: 6 components (ProfileHeader, StatsRow, AchievementBar, BooksTab, TranslationsTab, StubTab), ProfilePage, i18n 4 languages. Review: 4 fixes (active user filter on followers/following/counts, achievement dedup). Gateway: `/v1/users` proxy added.

| Work item | Files touched | Status |
| --------- | ------------- | ------ |
| BE-01: bio + languages migration + profile CRUD | `auth-service/migrate.go`, `handlers.go` | Done |
| BE-02: public profile endpoint | `auth-service/handlers.go`, `server.go` | Done |
| BE-03: follow system (table + 4 endpoints) | `auth-service/migrate.go`, `handlers.go`, `server.go` | Done |
| BE-04: favorites system (table + 3 endpoints) | `book-service/migrate.go`, `favorites.go` (new), `server.go` | Done |
| BE-05: catalog author filter | `catalog-service/server.go` | Done |
| BE-06: translator stats by user endpoint | `statistics-service/server.go` | Done |
| Gateway: /v1/users proxy | `gateway-setup.ts` | Done |
| FE-01: API layer | `features/profile/api.ts` (new) | Done |
| FE-02: ProfileHeader | `features/profile/ProfileHeader.tsx` (new) | Done |
| FE-03: StatsRow + AchievementBar | `features/profile/StatsRow.tsx`, `AchievementBar.tsx` (new) | Done |
| FE-04: BooksTab | `features/profile/BooksTab.tsx` (new) | Done |
| FE-05: TranslationsTab + StubTab | `features/profile/TranslationsTab.tsx`, `StubTab.tsx` (new) | Done |
| FE-06: ProfilePage + route + i18n | `pages/ProfilePage.tsx` (new), `App.tsx`, `i18n/index.ts`, 4 locale files | Done |
| Review fixes: active user filter, achievement dedup | `handlers.go`, `AchievementBar.tsx` | Done |

**9-phase workflow followed for P9-02:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in previous session (2026-04-08, session 26):**

P9-01 Leaderboard — full-stack implementation. Backend gaps (display name denormalization, translation counts, trending sort, auth-service internal endpoint) + full frontend (12 components, i18n 4 languages, route). Then review pass fixing 6 issues. Committed at `c190e03`.

| Work item | Files touched | Status |
| --------- | ------------- | ------ |
| A1: Denormalize display names — auth-service internal endpoint + statistics-service consumer + migration + API responses | `auth-service/handlers.go`, `auth-service/server.go`, `statistics-service/migrate.go`, `consumer.go`, `api/server.go`, `config.go`, `docker-compose.yml` | Done |
| A2: translation_count on book_stats | `migrate.go`, `consumer.go`, `api/server.go` | Done |
| A3: Trending sort option | `api/server.go` | Done |
| B1: API layer (types + fetch) | `features/leaderboard/api.ts` | Done |
| B3: Components (RankMedal, TrendArrow, PeriodSelector, FilterChips, Podium, RankingList, AuthorList, TranslatorList, QuickStatsCards) | 9 new files in `features/leaderboard/` | Done |
| B2: LeaderboardPage | `pages/LeaderboardPage.tsx` | Done |
| B4: i18n (4 languages) | `i18n/locales/{en,ja,vi,zh-TW}/leaderboard.json`, `i18n/index.ts` | Done |
| B5: Route update | `App.tsx` | Done |
| Review fixes: statsBook fallback fields, translation count reset, translator name refresh, i18n Show more, quick-stats state overwrite, dead AbortController removal | `api/server.go`, `consumer.go`, `AuthorList.tsx`, `TranslatorList.tsx`, `LeaderboardPage.tsx` | Done |

**9-phase workflow followed for P9-01:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in previous session (2026-04-08, session 25):**

P9-07 .docx/.epub import — full-stack implementation via Pandoc sidecar + async worker-infra. 4 commits.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| P9-07 core: Pandoc sidecar, import_jobs table, book-service endpoints, worker-infra ImportProcessor, HTML→Tiptap converter, frontend ImportDialog rewrite | `docker-compose.yml`, `migrate.go`, `import.go` (new), `server.go`, `import_processor.go` (new), `html_to_tiptap.go` (new), `config.go`, `main.go`, `ImportDialog.tsx`, `api.ts` | `286eede` |
| P9-07 improvements: image extraction from data: URIs → MinIO, WebSocket push via RabbitMQ | `image_extractor.go` (new), `import_processor.go`, `useImportEvents.ts` (new), `ImportDialog.tsx` | `6648fa4` |
| Fix: go.sum missing checksums after adding minio-go + amqp091-go | `go.sum` | `63d6219` |
| Fix: Dockerfile Go version bump 1.22→1.25 (minio-go requires it) | `Dockerfile` | `e5cdc32` |

Unit tests: 20 tests in `html_to_tiptap_test.go` (all pass). Integration test script: `infra/test-import.sh`.

**9-phase workflow followed for P9-07:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-07→08, session 24):**

45 commits across 4 phases + cleanup + bugs + plan audit.

| Phase / Work | Tasks | Commits |
| ------------ | ----- | ------- |
| Phase 8E — AI Provider + Media Gen | 11 | 10 |
| Phase 8F — Block Translation Pipeline | 16 | 11 |
| Phase 8G — Translation Review Mode | 8 | 3 |
| Phase 8H — Reading Analytics (GA4) | 14 | 7 |
| P3-R1 Cleanup — dead code, mock data, ModeProvider | 5 | 2 |
| Bug fixes — public reader 404, Vite chunks | 2 | 1 |
| TF-10 — Editor translate button | 1 | 1 |
| Reviews (8E, 8F, 8G, 8H, deferred) | 5 rounds | 5 |
| Plan audit — 135 done, Phase 9 added | - | 1 |
| Translation fix — Ollama content_extractor | 1 | 1 |
| Test fixes — image gen endpoint path | 1 | 1 |
| Session/plan docs | - | 2 |

Phase 8H — reading analytics, GA4-style (4 commits).

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| TH-01+02: reading_progress + book_views tables, 4 endpoints | `migrate.go`, `analytics.go` (new), `server.go` | `48b08cd` |
| TH-04..07: useReadingTracker + useBookViewTracker hooks, page wiring | 5 FE files (2 new hooks) | `76cb8f9` |
| TH-08+09: TOC read status + book detail stats | `TOCSidebar.tsx`, `BookDetailPage.tsx`, `api.ts` | `fdf4d07` |
| TH-12: Integration tests (19/19 pass) + route/precision fixes | `test-reading-analytics.sh`, 3 BE files | `367494e` |

Phase 8G — translation review mode (2 commits).

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| TG-01..08: BlockAlignedReview, ReviewPage, route, toolbar, entry points, SplitCompareView upgrade | 6 files (2 new) | `df72b04` |
| Plan: Phase 8G (8 tasks) | planning doc | `4b80c82` |

Phase 8F — block-level translation pipeline (10 commits).

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| TF-01: Migration — translated_body_json JSONB + format column | `migrate.py`, `models.py` | `27ea2f2` |
| TF-02: Block classifier (translate/passthrough/caption_only + inline marks) | `block_classifier.py` (new) | `245b48e` |
| TF-03: Block-aware batch builder ([BLOCK N] markers, token budget) | `block_batcher.py` (new) | `3c7d63d` |
| TF-04+06: translate_chapter_blocks() pipeline + block translation prompts | `session_translator.py` | `16948ee` |
| TF-05: Chapter worker routes JSON→block pipeline, TEXT→legacy | `chapter_worker.py` | `de49e96` |
| TF-07: Sync translate-text endpoint block mode | `translate.py`, `models.py` | `5d880a8` |
| TF-08+12: ReaderPage renders JSONB translations + types update | `ReaderPage.tsx`, `api.ts` | `e42017c` |
| TF-09: TranslationViewer format badges + ContentRenderer | `TranslationViewer.tsx` | `ee4ba98` |
| TF-13+14: Unit tests (45 pass — classifier + batcher) | `test_block_classifier.py`, `test_block_batcher.py` | `9769d47` |
| TF-15+16: Integration tests (19 pass — e2e block translate + backward compat) | `test-translation-blocks.sh` | `40f2f98` |

Also done: Phase 8E (9 commits), 8E review fixes, translate-text Ollama fix.

Phase 8E — AI provider capabilities + media generation (9 commits).

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| PE-01: BE — capability filter (`?capability=tts`) on listUserModels | `provider-registry-service/server.go` | `a310e83` |
| PE-02: FE — media capabilities in CapabilityFlags (tts, stt, image_gen, video_gen, embedding, moderation) + capability param on API client | `CapabilityFlags.tsx`, `settings/api.ts` | `a6fd64c` |
| PE-03: FE — filter TTSSettings to tts models, ImageBlockNode to image_gen models + capability_flags on UserModel type | `TTSSettings.tsx`, `ImageBlockNode.tsx`, `ai-models/api.ts` | `e00cf57` |
| PE-04: BE — add usage billing (purpose=image_generation) to existing image gen endpoint | `media.go` | `7098e28` |
| PE-05: BE — integration tests (27 scenarios: validation, auth, upload, versions, capability filter) | `test-image-gen.sh` (new) | `78b9858` |
| PE-06: FE — wire image gen in editor (already done — verified) | — | — |
| PE-07: BE — video-gen-service provider adapter (resolve creds, call Sora-compatible API, MinIO storage, billing) | `generate.py`, `main.py`, `requirements.txt`, `docker-compose.yml` | `9d2b239` |
| PE-08: BE — video gen integration tests (13 scenarios) | `test-video-gen.sh` (new) | `0f9736f` |
| PE-09: FE — wire VideoBlockNode to provider-registry video_gen model | `VideoBlockNode.tsx` | `fb6cb47` |
| PE-10: FE — AI Models section in ReadingTab (TTS/image/video model selectors, voice picker, image size) | `ReadingTab.tsx` | `5dcab71` |
| PE-11: BE — preconfig catalog (already done — tts-1, dall-e-3, gpt-image-1 in openai_models.json) | — | — |

**9-phase workflow followed for each task:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-06, session 23):**

Phase 8D unified audio — AU-04..AU-07 + bug fixes.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| AU-04: Gateway audio route proxy test (5 assertions) + fix videoGenUrl compile error | `proxy-routing.spec.ts`, `health.spec.ts` | `d3ba6ff` |
| AU-05: Extended integration tests (12 new scenarios, 79/79 total) | `test-audio.sh` | `72a744d` |
| AU-06: audioBlock Tiptap extension — standalone audio node with upload, player, subtitle, slash menu, media guard | `AudioBlockNode.tsx` (new), `TiptapEditor.tsx`, `SlashMenu.tsx`, `MediaGuardExtension.ts`, `api.ts` | `a273190` |
| Fix: slash menu scroll positioning (fixed pos + max-height + flip) + sticky FormatToolbar | `SlashMenu.tsx`, `FormatToolbar.tsx` | `8d1462f` |
| AU-07: Audio attachment attrs on text blocks (paragraph, heading, blockquote, callout) | `AudioAttrsExtension.ts` (new), `TiptapEditor.tsx` | `fb072f8` |
| AU-08: AudioAttachBar — mini player widget decoration on text blocks with audio | `AudioAttachBarExtension.ts` (new), `TiptapEditor.tsx` | `2882ddf` |
| AU-09: AudioAttachActions — hover upload/record/generate buttons on text blocks | `AudioAttachActionsExtension.ts` (new), `TiptapEditor.tsx` | `77b6b99` |
| AU-10: FormatToolbar audio insert button (AI mode) — slash menu already in AU-06 | `FormatToolbar.tsx` | `4326b2a` |
| AU-11: AudioBlock reader display component + CSS (purple accent) | `AudioBlock.tsx` (new), `ContentRenderer.tsx`, `reader.css` | `6f4f400` |
| AU-12+13: Audio indicator on text blocks + CSS (hover play, mismatch, badges) | `ContentRenderer.tsx`, `reader.css` | `6def03b` |
| AU-14..17: Playback engine — TTSProvider, AudioFileEngine, BrowserTTSEngine, audio-utils | `useTTS.ts`, `AudioFileEngine.ts`, `BrowserTTSEngine.ts`, `audio-utils.ts` (all new) | `8512b0b` |
| AU-18..21: Player UI — TTSBar, block scroll sync, keyboard shortcuts, ReaderPage wiring | `TTSBar.tsx`, `useBlockScroll.ts`, `useTTSShortcuts.ts`, `ReaderPage.tsx` | `c64b986` |
| AU-22..24: Settings + management — TTSSettings, AudioOverview, AudioGenerationCard | `TTSSettings.tsx`, `AudioOverview.tsx`, `AudioGenerationCard.tsx`, `TTSBar.tsx`, `ReaderPage.tsx` | `dd130b5` |
| Wire AI TTS generation to model settings (generate buttons call real AU-03 endpoint) | `api.ts`, `TTSSettings.tsx`, `AudioOverview.tsx`, `AudioAttachActionsExtension.ts` | `5a8cf9c` |
| Plan: Phase 8E — AI Provider Capabilities + Media Generation (11 tasks: PE-01..PE-11) | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | pending |

**9-phase workflow followed for each task:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-06, session 22):**

Phase 8D unified audio — AU-01..AU-03 backend implementation.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| AU-01: chapter_audio_segments table + CRUD (3 endpoints) | `migrate.go`, `audio.go` (new), `server.go` | `770b123` |
| AU-01: integration tests (41 scenarios, all pass) | `infra/test-audio.sh` (new) | `2c24bbe` |
| AU-02: block audio upload endpoint + tests (59 total, all pass) | `audio.go`, `server.go`, `test-audio.sh` | `8644c16` |
| AU-03: AI TTS generation endpoint + tests (67 total, all pass) | `audio.go`, `server.go`, `config.go`, `docker-compose.yml`, `test-audio.sh` | `397e199` |

**9-phase workflow followed for AU-01..AU-03:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-05, session 21):**

Phase 8 design + planning + RD-00. Design review of reader architecture, 3 HTML design drafts created, 30-task breakdown across 7 sub-phases (8A-8G), design decisions finalized.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Design: reader-v2-part1 (block renderer + chrome) | `design-drafts/screen-reader-v2-part1-renderer.html` (new) | pending |
| Design: reader-v2-part2 (TTS/audio player) | `design-drafts/screen-reader-v2-part2-audio-tts.html` (new) | pending |
| Design: reader-v2-part3 (review modes) | `design-drafts/screen-reader-v2-part3-review-modes.html` (new) | pending |
| Planning: Phase 8 breakdown (30 tasks, 7 sub-phases) | `docs/03_planning/99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | pending |
| RD-00: Install 5 missing editor extensions (link, underline, highlight, sub, sup) | `TiptapEditor.tsx`, `FormatToolbar.tsx`, `package.json` | `544c047` |
| RD-01: InlineRenderer — text marks display (9 marks + hardBreak) | `InlineRenderer.tsx` (new) | `bdfd177` |
| RD-02: Text block display components (paragraph, heading, blockquote, list, hr) | `blocks/` (5 new files) | `1be9279` |
| RD-03: Media block display components (image, video, code, callout) | `blocks/` (4 new files) | `2d961f4` |
| RD-04: ContentRenderer orchestrator (block→component mapping) | `ContentRenderer.tsx` (new) | `cbc1113` |
| RD-05: Reader CSS — full + compact mode styles | `reader.css` (new) | `83d4227` |
| RD-06: ReaderPage rewrite — ContentRenderer replaces TiptapEditor | `ReaderPage.tsx` | `24d4b25` |
| RD-07: Chapter header + end marker — metadata, reading time, CJK | `ReaderPage.tsx`, `reader.css` | `4a06029` |
| RD-08: Extract TOCSidebar from ReaderPage | `TOCSidebar.tsx` (new) | `e62f25c` |
| RD-09: Language selector in TOC — switch reading language | `TOCSidebar.tsx`, `ReaderPage.tsx`, `reader.css` | `4f08f20` |
| RD-10: Top bar edit button — owner-only visibility | `ReaderPage.tsx` | `93b12b6` |
| RD-11: Keyboard shortcuts (arrows, T, Escape, Home/End) | `ReaderPage.tsx` | `6d35e16` |
| RD-12: Integration cleanup — remove old .tiptap-reader CSS, mark tasks done | `index.css`, planning doc | `1710bc4` |
| Review fixes: extractText shared util, useMemo, lang loading, Escape | `ReaderPage.tsx`, `tiptap-utils.ts` | `3ec3e55` |
| Smoke test fix: Home/End scroll targets reader container + test account | `ReaderPage.tsx`, `CLAUDE.md` | `ad1873e` |
| RD-13: Reader theme wiring — apply --reader-* CSS vars | `ReaderPage.tsx` | `a1b8d5c` |
| RD-14: ThemeCustomizer slide-over (presets, fonts, sliders) | `ThemeCustomizer.tsx` (new), `ReaderPage.tsx` | `240830f` |
| RD-15: Reading mode toggles (block indices, placeholders) | `ThemeCustomizer.tsx`, `ReaderPage.tsx` | `7dc3273` |
| 8B review fixes: Escape closes theme, mutual exclusion, top bar readability | `ReaderPage.tsx` | `2691880` |
| RD-16+17: RevisionHistory uses ContentRenderer, delete ChapterReadView | `RevisionHistory.tsx`, `ChapterReadView.tsx` (deleted) | `52556cb` |
| Bug fix: sharing status (SHARING_INTERNAL_URL), multi-file upload, fake read marks | `docker-compose.yml`, `ImportDialog.tsx`, `TOCSidebar.tsx`, planning | `a94a25b` |
| Bug fix: remove circular dependency book↔sharing | `docker-compose.yml` | `39d591a` |
| Design: Part 4 unified audio system (audio blocks + playback) | `screen-reader-v2-part4-audio-blocks.html` (new) | `01e021b` |
| Plan: Phase 8D unified audio — 24 tasks replacing old 8D+8E | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | `f667955` |

**9-phase workflow followed for each task:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-05, session 20):**

E2E browser review fixes (8 issues) + P3-KE Kind Editor Enhancement COMPLETE (13 tasks: 6 BE + 7 FE). 17 commits, 67/67 BE integration tests.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| B1: Fix raw \u2026 in trash search placeholder | `TrashPage.tsx` | `b2f60d4` |
| B2: Genre tags on public book detail page | `PublicBookDetailPage.tsx` | `b2f60d4` |
| B3: "Back to Workspace" link on 404 page | `PlaceholderPage.tsx` | `b2f60d4` |
| B4: Recharts negative dimension warning | `DailyChart.tsx` | `b2f60d4` |
| U1: Display Name field on registration | `RegisterPage.tsx` | `b2f60d4` |
| U3: Lazy-load BookDetailPage tabs (mount on first visit) | `BookDetailPage.tsx` | `b2f60d4` |
| U4: Genre tags on workspace book cards | `BooksPage.tsx` | `b2f60d4` |
| Critical fix: null-guard genre_tags (11 access sites, 5 files) | `EntityEditorModal.tsx`, `GenreGroupsPanel.tsx`, `GlossaryTab.tsx`, `KindEditor.tsx`, `SettingsTab.tsx` | `b2f60d4` |
| P3-KE plan added to 99A (13 tasks, BE-first strategy) | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | `b2f60d4` |
| BE-KE-01: Kind + attr description field — expose existing columns | `domain/kinds.go`, `kinds_handler.go`, `kinds_crud.go` | `b2f60d4`, `67879aa` |
| BE-KE-02: Entity count per kind — correlated subquery in listKinds | `domain/kinds.go`, `kinds_handler.go` | `731ab9d` |
| BE-KE-03: Attribute is_active toggle — migration + CRUD | `migrate.go`, `domain/kinds.go`, `kinds_handler.go`, `kinds_crud.go` | `2a76891` |
| BE-KE-04: Attribute inline edit validation — field_type allowlist, empty name rejection | `kinds_crud.go` | `3da6932` |
| BE-KE-05: Attr description — already covered by BE-KE-01 | — | — |
| BE-KE-06: Sort order reorder endpoints (kinds + attrs) | `server.go`, `kinds_crud.go` | `96fd331` |
| Review fix: patchKind re-fetch missing entity_count subquery | `kinds_crud.go` | `88da9b4` |
| Integration test suite: 67 scenarios, all pass | `infra/test-kind-editor-enhance.sh` | `67879aa`..`96fd331` |
| FE-KE-01: Kind metadata panel — description textarea + entity count | `KindEditor.tsx`, `glossary/types.ts` | `eeafec7` |
| FE-KE-02: Attribute inline edit form (pencil icon, name/type/required/desc/genre) | `KindEditor.tsx` | `6624e70` |
| FE-KE-03: Attribute toggle on/off (CSS switch, is_active PATCH) | `KindEditor.tsx` | `b28925d` |
| FE-KE-04: Drag-to-reorder kinds (native HTML DnD, GripVertical, optimistic UI) | `KindEditor.tsx`, `glossary/api.ts` | `63d6b04` |
| FE-KE-05: Drag-to-reorder attributes | `KindEditor.tsx` | `cb41f1e` |
| FE-KE-06: Genre-colored dots on tag pills (genreColorMap from genre_groups) | `KindEditor.tsx`, `GlossaryTab.tsx` | `88cfadf` |
| FE-KE-07: Modified indicator + Revert to default (seedDefaults.ts, confirm dialog) | `KindEditor.tsx`, `seedDefaults.ts` (new) | `c204d1a` |
| FE-KE review: parallel revert + genre-colored kind tags | `KindEditor.tsx` | `042f4e1` |

| INF-01: Service-to-service auth — requireInternalToken middleware + internalGet | 11 files across 6 services, `docker-compose.yml` | `03644b3` |
| INF-02: Internal HTTP client — 10s timeout + 1 retry, zero http.Get remaining | `catalog/server.go`, `sharing/server.go`, `book/server.go`, `book/media.go` | `e02a1c9` |
| INF-03: Structured JSON logging — 77 log.Printf→slog across 8 Go services | 15 files across 8 services | `af1679d`, `da818cd` |
| INF-04: Health check deep mode — /health (ping) + /health/ready (SELECT 1) | 7 service server.go files, `test-infra-health.sh` (new) | `b670f7c` |
| Attr Editor: design draft (2 variants — system + user attr, AI sections) | `screen-attr-editor-modal.html` (new), `screen-glossary-management.html` | `cfd1f38` |
| Attr Editor BE: auto_fill_prompt + translation_hint columns (79/79 pass) | `migrate.go`, `domain/kinds.go`, `kinds_handler.go`, `kinds_crud.go` | `b59ef13` |
| Attr Editor FE: AttrEditorModal — floating modal replaces inline form | `AttrEditorModal.tsx` (new), `KindEditor.tsx`, `glossary/types.ts` | `8463b80` |
| Attr Editor FE: create mode — "Add Attribute" opens modal too | `AttrEditorModal.tsx`, `KindEditor.tsx`, `glossary/api.ts` | `6c82a86` |
| P4-04 plan: detailed 9-task breakdown (2 BE + 7 FE) | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | `043c990` |
| BE-TH-01+02: user_preferences JSONB table + gateway proxy (14/14 pass) | auth-service, gateway | `bc4e67f` |
| FE-TH-01: 4 app theme presets via CSS variable overrides | `index.css` | `775035b` |
| FE-TH-02: unified ThemeProvider replaces ReaderThemeProvider | `ThemeProvider.tsx` (new), `App.tsx` | `c9bf5eb` |
| FE-TH-03: theme toggle in sidebar (cycles dark/light/sepia/oled) | `Sidebar.tsx` | `b751192` |
| FE-TH-06: Settings ReadingTab rewrite (app theme + reader theme + typography) | `ReadingTab.tsx` | `b2efad4` |
| FE-TH-07: CSS audit — hardcoded colors → theme tokens | `SourceView.tsx`, `DailyChart.tsx` | `9eb24f0` |
| Custom theme editor: color pickers, paragraph spacing, save/load custom presets | `ThemeProvider.tsx`, `ReadingTab.tsx` | `5a7367d` |
| Future theme improvements plan: 22 deferred items across 5 categories | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | `54f1de3` |

**9-phase workflow followed for each task:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-04, session 19):**

P3-08 Genre Groups — Full backend + frontend implementation (tag-based, no activation matrix). 26 commits.

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Design: replaced activation matrix with tag-based genre scoping | `design-drafts/screen-glossary-management.html`, `design-drafts/screen-genre-groups.html` (new) | this session |
| Planning: rewrote P3-08a/b/c → BE-G1..G5 + FE-G1..G7 (12 tasks, backend-first) | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | this session |
| BE-G1: `genre_groups` table + CRUD (4 endpoints, 24/24 tests) | glossary-service: `migrate.go`, `genres_handler.go`, `genres_crud.go`, `domain/genres.go`, `server.go`, `main.go` | `ada8dcf` |
| BE-G1 review: UUID validation, cross-book re-fetch, length limits | `genres_crud.go`, `genres_handler.go` | `d3d7e6d` |
| BE-G2: `attribute_definitions.genre_tags` column + CRUD (12/12 tests) | `migrate.go`, `kinds_crud.go`, `kinds_handler.go`, `domain/kinds.go` | `981a9ea` |
| BE-G2 review: patchAttrDef re-fetch add kind_id + error check | `kinds_crud.go` | `7f93c5a` |
| BE-G3: `books.genre_tags` column + CRUD (11/11 tests) | book-service `migrate.go`, `server.go` | `46f1df2` |
| BE-G4: Catalog genre filter + projection (12/12 tests) | book-service `server.go`, catalog-service `server.go` | `853a1b0` |
| BE-G4 review: nil guard + pre-existing title scan bug fix | book-service `server.go` | `152f19a`, `e01e6d6` |
| BE-G5: Integration test script (65 scenarios, all pass) | `infra/test-genre-groups.sh` (new) | `401ab60` |
| H2+H3 fix: uuidv7 for genre_groups, skip hidden kinds in attr query | glossary-service `migrate.go`, `kinds_handler.go` | `7e8340c` |
| FE-G1: Types + API client (GenreGroup, genre_tags on all types) | `glossary/types.ts`, `glossary/api.ts`, `books/api.ts`, `BrowsePage.tsx` | `08d70e2` |
| FE-G2: Genre Groups tab + CRUD + detail panel | `GlossaryTab.tsx`, `GenreGroupsPanel.tsx` (new), `GenreFormModal.tsx` (new) | `213e48a` |
| FE-G2 review: dead imports, escape guard, auto-select, rename cascade | `GenreGroupsPanel.tsx`, `GenreFormModal.tsx` | `36c5ab7`, `fe9ee3d` |
| FE-G3: Kind Editor genre_tags row | `KindEditor.tsx` | `c3e662b`, `b7a3245` |
| FE-G4: Attr genre_tags pills + create form | `KindEditor.tsx` | `7e41867`, `b11bc15` |
| FE-G5: Entity Editor genre filter + kind dropdown filter | `BookDetailPage.tsx`, `GlossaryTab.tsx`, `EntityEditorModal.tsx` | `085cb61`, `c900c41` |
| FE-G6: Book SettingsTab (P3-21 + genre selector, cover, visibility) | `SettingsTab.tsx` (new), `BookDetailPage.tsx` | `1596013`, `4fbb672` |
| FE-G7: Browse genre filter chips + book card genre pills (multi-select) | `BrowsePage.tsx`, `FilterBar.tsx`, `BookCard.tsx` | `36299a4`, `64799f8` |

**9-phase workflow followed:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

**What was done in this session (2026-04-03, session 18):**

Phase 6 Chat Enhancement — Backend implementation + integration tests (28/28 pass).

| Work item | Files touched | Commit |
| --------- | ------------- | ------ |
| Phase 6 planning: competitive analysis, 16 tasks (C6-01..C6-16), BE-first strategy | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | this session |
| Design draft: enhanced chat GUI (thinking block, session settings, format pills, branch nav) | `design-drafts/screen-chat-enhanced.html` (new) | this session |
| BE-C6-01: `generation_params` JSONB column + `is_pinned` BOOLEAN on chat_sessions | `migrate.py`, `models.py`, `sessions.py` | this session |
| BE-C6-02: stream_service reads generation_params → passes temperature/top_p/max_tokens to LLM | `stream_service.py` | this session |
| BE-C6-03: system_prompt injection — prepend session system_prompt as system message | `stream_service.py` | this session |
| BE-C6-04: thinking mode — parse `reasoning_content`, emit `reasoning-delta` SSE events | `stream_service.py`, `messages.py`, `models.py` | this session |
| BE-C6-05: message search endpoint — FTS with `ts_headline` snippets | `sessions.py`, `models.py`, `migrate.py` | this session |
| BE-C6-06: session pin — `is_pinned` field, pinned-first sort in list | `sessions.py`, `models.py`, `migrate.py` | this session |
| BE-C6-07: auto-title generation — async LLM call after first exchange, reasoning fallback | `stream_service.py` | this session |
| Critical fix: bypass LiteLLM for streaming (strips `reasoning_content`), use OpenAI SDK directly | `stream_service.py` | this session |
| Route fix: move `/search` before `/{session_id}` to prevent path conflict | `sessions.py` | this session |
| Test setup: LM Studio provider + qwen3-1.7b model insertion script | `infra/setup-chat-test-model.sh` (new) | this session |
| Integration test: 28 scenarios (T20-T33), all pass, covers CRUD + streaming + thinking + search | `infra/test-chat-enhanced.sh` (new) | this session |
| FE-C6-01: SessionSettingsPanel slide-over (model, system prompt, gen params, info) | `SessionSettingsPanel.tsx` (new), `ChatHeader.tsx`, `ChatWindow.tsx`, `ChatPage.tsx` | `d16f54b` |
| FE-C6-02: Thinking mode UI (Think/Fast toggle, ThinkingBlock, reasoning-delta parsing) | `ThinkingBlock.tsx` (new), `ChatInputBar.tsx`, `AssistantMessage.tsx`, `MessageBubble.tsx`, `MessageList.tsx`, `useChatMessages.ts` | `d16f54b` |
| FE-C6-03: Token display per-message (thinking/input/output counts, Fast/Think badge) | `AssistantMessage.tsx` | `d16f54b` |
| FE-C6-04: Sidebar search + temporal groups (Pinned/Today/Yesterday/Week/Older) + pin/unpin | `SessionSidebar.tsx`, `useSessions.ts`, `ChatPage.tsx` | `7a1c2a6` |
| FE-C6-05: Enhanced NewChatDialog (model search, presets, badges, system prompt) | `NewChatDialog.tsx`, `ChatPage.tsx` | `8b3fdec` |
| FE-C6-06: Keyboard shortcuts (Ctrl+N new, Esc stop, Ctrl+Shift+Enter think) | `ChatPage.tsx`, `ChatInputBar.tsx` | `502abbe` |
| FE-C6-07: FTS message search in sidebar (debounced, snippet highlights) | `api.ts`, `SessionSidebar.tsx` | `502abbe` |
| Types updated: GenerationParams, is_pinned, thinking field, SearchResult | `types.ts` | `d16f54b` |
| Code review: 4 critical + 5 high fixes (tautology, client leak, validation, XSS, timers) | 7 files | `d87931c` |
| C6-12: Format pills (Auto/Concise/Detailed/Bullets/Table) | `ChatInputBar.tsx` | `7f06c22` |
| C6-14: Message actions dropdown (Copy Markdown, Send to Editor) | `AssistantMessage.tsx` | `7f06c22` |
| C6-16: Prompt template library ("/" trigger, 8 templates, arrow key nav) | `PromptTemplates.tsx` (new), `ChatInputBar.tsx` | `7f06c22` |
| M1: gen_params PATCH clear to null + "Reset to Defaults" button | `sessions.py`, `SessionSettingsPanel.tsx` | `7f06c22` |
| M3: NewChatDialog auto-focus + error toast | `NewChatDialog.tsx` | `7f06c22` |
| M4: ChatPage loading spinner on session switch | `ChatPage.tsx` | `7f06c22` |
| Fix: Send to Editor event name mismatch (paste-to-editor → loreweave:paste-to-editor) | `AssistantMessage.tsx` | `c2d1840` |
| Fix: Context resolution warning toast | `ChatPage.tsx` | `c2d1840` |
| FE-C6-08 BE: branch_id column, edit-as-branch (UPDATE not DELETE), branches endpoint | `migrate.py`, `messages.py`, `stream_service.py` | `7a74be9` |
| FE-C6-08 FE: BranchNavigator component, branch switching, listBranches API | `BranchNavigator.tsx` (new), `MessageBubble.tsx`, `MessageList.tsx`, `ChatWindow.tsx`, `api.ts`, `types.ts` | `7a74be9` |
| Branching review: 3 critical + 2 high (refreshBranch, listMessages branch_id, fallback) | 6 files | `5ad82af` |

**9-phase workflow followed:** PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

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
| MIG-06 BE: catalog-service — sort (recent/chapters/alpha) + language filter, over-fetch+paginate | `catalog-service/server.go` | this session |
| MIG-06 FE: Browse page — hero, search (debounced), language chips, genre chips (disabled), sort, 4-col grid, BookCard, pagination | 3 new files, `App.tsx` | this session |
| P3-08c: Genre tag + browse filter task added to planning doc | `99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` | this session |
| Provider enhancement BE: embed preconfig JSON (26 OpenAI + 10 Anthropic), replace hardcoded 2-3 models | `adapters.go`, 2 JSON files | this session |
| Provider enhancement FE: AddModelModal (autocomplete, capability types, tags, notes) + EditModelModal (toggles, verify, delete) | 2 new files, `ProvidersTab.tsx`, `api.ts` | this session |
| Model management fix: complete data flow (API sends all fields), shared TagEditor + CapabilityFlags, delete icon on rows | 6 files | this session |
| Notes field full-stack: BE migration + create/patch/read, FE send on create + load on edit | 5 files | this session |
| TranslationTab fix: model picker dropdown grouped by provider, fix save error (missing model_source/ref) | `TranslationTab.tsx` | this session |
| Email verification flow: request + confirm in AccountTab | `api.ts`, `AccountTab.tsx` | this session |
| Sidebar display name: updateUser() in AuthProvider, instant update after profile save | `auth.tsx`, `AccountTab.tsx` | this session |
| Chat layout fix: new ChatLayout (Sidebar + full-bleed), move from FullBleedLayout | `ChatLayout.tsx`, `App.tsx` | this session |
| Chat model display: resolve model_ref UUID → display name in header + sidebar | 4 chat files | this session |
| Unicode fix: replace literal \u00B7 in JSX text with &middot; | 2 chat files | this session |
| Context picker: floating modal instead of inline absolute (no layout shift) | `ContextBar.tsx`, `ContextPicker.tsx` | this session |
| Custom providers: drop CHECK constraint, add api_standard column, accept any provider_kind | BE 5 files, FE 2 files | this session |
| LiteLLM auth fix: dummy API key for local providers (LM Studio/Ollama) | `stream_service.py` | this session |
| Planning: P3-08c genre filter task, P4-04 Reading/Theme unification plan (6 sub-tasks) | 2 planning docs | this session |
| Design draft: model editor modal (Add/Edit) + preconfig catalogs JSON | 3 new files | this session |

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

### Completion Summary (as of session 31)

| Area | Status |
| ---- | ------ |
| Frontend V2 Phase 1 (Foundation) | ✅ Done |
| Frontend V2 Phase 2 (Core Screens) | ✅ Done |
| Frontend V2 Phase 2.5 (Tiptap Editor) | ✅ Done |
| Frontend V2 Phase 3 (Features: Translation, Glossary, Chat, Wiki) | ✅ Done |
| Frontend V2 Phase 3.5 (Media Blocks) | ✅ Done |
| Frontend V2 Phase 4 (Settings, Usage, Browse) | ✅ Done |
| Phase 4.5 / 8D (Audio/TTS system) | ✅ Done |
| P4-04 Reading/Theme Unification (9 tasks) | ✅ Done |
| Phase 8A-8H (Reader v2, Translation Pipeline, Review Mode, Analytics) | ✅ Done |
| Phase 9 (Leaderboard, Profile, Wiki, Import, Audio, Account) | ✅ Done |
| MIG-03..MIG-10 (V1→V2 page migrations + old frontend deleted) | ✅ Done |
| P3-08 Genre Groups (BE+FE) | ✅ Done |
| P3-KE Kind Editor Enhancement (13 tasks) | ✅ Done |
| Data Re-Engineering D1 (JSONB, blocks, events, worker-infra) | ✅ Done |
| Translation Pipeline V2 (CJK fix, glossary, validation, memo) | ✅ Done |
| Chat Service Phase 1-3 | ✅ Done |
| Glossary Extraction Pipeline — BE (13 tasks) | ✅ Done |
| Glossary Extraction Pipeline — FE (7 tasks) | ✅ Done |
| GEP Integration Test (49 assertions) | ✅ Done |
| GEP Browser Smoke Test | ✅ Done |
| INF-01..03 (Service auth, HTTP client, structured logging) | ✅ Done |
| Voice Mode — Chat (VM-01..VM-06) | ✅ Done |
| AI Service Readiness — Gateway + Mock + FE hooks (AISR-01..05) | ✅ Done |
| External AI Service Integration Guide (1096 lines) | ✅ Done |

### Remaining Work

| Priority | Item | Scope | Notes |
| -------- | ---- | ----- | ----- |
| **P1** | **Translation Workbench** (P3-T1..T8) | 8 tasks (BE+FE) | Block-level translation UI. Design draft exists. Blocker removed (media blocks done). |
| **P1** | **Build external TTS/STT services** (separate repos) | New repos | Integration guide ready. Gateway proxy + frontend hooks done. Need: Whisper STT service, Coqui/XTTS TTS service. |
| P2 | GUI Review deferred (D1-D22) | FE polish | Editor, glossary, reader polish items |
| P2 | Chat Service Phase 4 | BE+FE | File attachments + multi-modal |
| P2 | Platform Mode | 35 tasks | `103_PLATFORM_MODE_PLAN.md` — multi-tenant SaaS features |
| P2 | Onboarding Wizard (P2-10) | FE | New user first-run experience |
| P3 | Phase 5: Advanced | Wishlist | Ambient mode, focus mode, night shift, knowledge graph |
| P3 | Formal acceptance evidence packs (M01-M05) | QA | Currently smoke-only |

> **Note:** The 99A planning doc (`99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md`) task markers are stale — 176/712 marked `[✓]` but ~640+ are actually done. The planning doc should be treated as historical reference, not active tracker.

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
| 2026-04-10→11 | Session 31: Three features. **GEP** — 10 BE fixes from real AI testing, integration test (49 assertions), 7 FE tasks (extraction wizard), smoke test. **Voice Mode** — 6 tasks (useSpeechRecognition, VoiceSettingsPanel with STT/TTS model selectors, useVoiceMode orchestrator, push-to-talk mic, overlay UI, integration wiring), 2 review passes (17 issues fixed). **AI Service Readiness** — gateway audio proxy, mock audio service, useBackendSTT, useStreamingTTS, integration test (19 assertions), review (20 issues fixed). **Docs** — integration guide (1096 lines), 99A bulk update (464 markers), session audit. | `3c5202a`..`e54557e` (29 commits) |
| 2026-04-10 | Session 30: Glossary Extraction Pipeline — full design doc (1500+ lines), 4 review rounds (context/data, security, cost → 22 issues found and fixed), UI draft HTML (7 interactive screens), implementation task plan (13 BE + 7 FE tasks). Design artifacts: `GLOSSARY_EXTRACTION_PIPELINE.md`, `glossary_extraction_ui_draft.html`. Key decisions: source language SSOT, alive flag for entities, 3-layer known entities filtering, extraction_audit_log table, prompt injection mitigation, cost estimation. | `ee6d64e` |
| 2026-04-09→10 | Session 29: Translation Pipeline V2 — full implementation (P1-P8). CJK token fix (2.29x), glossary injection (1/6→6/6), output validation+retry, multi-provider tokens, rolling context, auto-correct, chapter memo, quality metrics. 3 services touched (translation, glossary, provider-registry). PoC with real Ollama gemma3:12b. Docker integration test: 132+113 blocks, all valid. 3 commits. | `662cbf7`..`6db8553` |
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
