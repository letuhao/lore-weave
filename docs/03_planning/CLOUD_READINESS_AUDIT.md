# Cloud Readiness & Multi-Device Audit

> **Status:** Audit complete, tasks created — HIGHEST PRIORITY
> **Session:** 32 (2026-04-11)
> **Scope:** Full codebase audit for AWS cloud deployment + multi-device support
> **Blocking:** Voice Pipeline V2 implementation (43 tasks) waits for this

---

## Context

LoreWeave is moving from Docker Compose development to AWS cloud production deployment. The app serves many users across PC, mobile, and tablet. This audit identified everything that breaks in that environment.

**4 audit perspectives (run in parallel):**
1. Frontend local storage — data that should be in DB/S3
2. Backend services — cloud deployment issues (pooling, secrets, service discovery)
3. Multi-device — mobile/tablet compatibility
4. Platform lock-in — Vercel or other vendor dependencies

**Result:** 46 issues found, consolidated into 26 actionable tasks.

---

## P0 — Security / Broken (5 tasks)

### CRA-01+02: Remove hardcoded secret defaults across all services [DONE]
- **Scope expanded:** Found in 5 services, not just chat-service. Fixed all in one pass.
- **Files changed:**
  - `services/chat-service/app/config.py` — `minio_secret_key`, `internal_service_token` (Pydantic required)
  - `services/chat-service/tests/conftest.py` — added test env vars
  - `services/translation-service/app/config.py` — `internal_service_token` (Pydantic required)
  - `services/video-gen-service/app/routers/generate.py` — `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` (`os.environ[]`)
  - `services/provider-registry-service/internal/config/config.go` — `InternalServiceToken` (`requireEnv()`)
  - `services/worker-infra/internal/config/config.go` — `InternalToken` (`requireEnv()`)
- **Behavior:** All services now fail to start if secret env vars are missing. Docker-compose already provides dev values.

### CRA-03: MINIO_EXTERNAL_URL must not default to localhost
- **File:** `infra/docker-compose.yml`
- **Problem:** `MINIO_EXTERNAL_URL: http://localhost:9123` — presigned URLs sent to browsers point to localhost in prod.
- **Fix:** Remove default. In prod, set to S3 bucket URL or CloudFront distribution.

### CRA-04: Chat layout — responsive sidebar for mobile
- **Files:** `frontend/src/pages/ChatPage.tsx`, `SessionSidebar`
- **Problem:** Two sidebars (270px + 240px) render at all viewport widths. On 375px phone = 0px for content.
- **Fix:** Mobile breakpoint: hide sidebars behind hamburger/drawer overlay. Show on `md:` and above.

### CRA-05: Settings panels — responsive width
- **Files:** `SessionSettingsPanel.tsx` (w-[380px]), `VoiceSettingsPanel.tsx` (w-72)
- **Problem:** Fixed-width panels wider than phone viewport. Content cut off.
- **Fix:** `max-w-full` or `w-full sm:w-[380px]` with full-screen drawer on mobile.

---

## P1 — Data Sync / Scalability / Usability (10 tasks)

### CRA-06..10: Sync localStorage preferences to server

All 5 share the same pattern — the existing `ThemeProvider` already syncs to `/v1/me/preferences`. These keys need the same treatment: read from server on login, write-through on change, localStorage as fast cache.

| Task | Key | File | Data |
|------|-----|------|------|
| CRA-06 | `lw_tts_prefs` | `components/reader/TTSSettings.tsx` | TTS voice, speed, model |
| CRA-07 | `lw_voice_prefs` | `features/chat/voicePrefs.ts` | Chat STT/TTS model selection |
| CRA-08 | `lw_language` | `features/settings/LanguageTab.tsx` | UI language |
| CRA-09 | `loreweave:media-prefs` | `features/settings/ReadingTab.tsx` | Image/video generation model IDs |
| CRA-10 | `lw_reader_theme` | `providers/ReaderThemeProvider.tsx` | Reader theme overrides (migrate into ThemeProvider) |

**Server endpoint:** `/v1/me/preferences` already exists. Add new preference keys to the schema.

### CRA-11: DB connection pool tuning — Go services
- **Files:** All Go service `config.go` / `main.go` files
- **Problem:** `pgxpool.New(ctx, url)` with no config. Default `pool_max_conns=4`. With 10 services × N instances → exhausts RDS `max_connections`.
- **Fix:** Set `pool_max_conns=10`, `pool_min_conns=2`, `pool_max_conn_lifetime=30m` via connection string or explicit `pgxpool.Config`.

### CRA-12: DB connection pool tuning — Python services
- **Files:** `services/chat-service/`, `services/translation-service/`
- **Problem:** asyncpg pool created without `min_size`, `max_size`, `max_inactive_connection_lifetime`.
- **Fix:** Set `min_size=2`, `max_size=10`, `max_inactive_connection_lifetime=300`.

### CRA-13: Hover-only buttons → touch-accessible
- **Files:** `AssistantMessage.tsx`, `UserMessage.tsx`, `SessionSidebar.tsx`, `NotificationBell.tsx`, `GlossaryTab.tsx`, `KindEditor.tsx`
- **Problem:** Action buttons use `group-hover:opacity-100` — permanently invisible on touch devices.
- **Fix:** Options: (a) always visible on `md:` below, hover on `lg:` above. (b) Long-press to reveal. (c) Swipe to reveal (like iOS mail). Option (a) is simplest.

### CRA-14: AudioContext autoplay fix for iOS
- **Files:** `frontend/src/lib/TTSPlaybackQueue.ts`, `BargeInDetector.ts`
- **Problem:** `AudioContext.resume()` called in async callback chain, not in user-gesture handler. iOS Safari suspends the context and `resume()` silently fails.
- **Fix:** Create and resume `AudioContext` inside the click/tap handler that activates voice mode. Pass the resumed context to TTS queue.

### CRA-15: Voice mode fallback for unsupported browsers
- **File:** `frontend/src/hooks/useSpeechRecognition.ts`
- **Problem:** Voice mode silently disappears on Firefox/Samsung Internet (~30% of Android). Mic button hidden, no explanation.
- **Fix:** Show a message: "Voice mode requires Chrome or Safari. [Learn more]" when `SPEECH_RECOGNITION_SUPPORTED` is false. Also: V2 uses backend STT (useBackendSTT), which works everywhere — this becomes the default path.

---

## P2 — Deploy Config / Polish (11 tasks)

### CRA-16: Docker-compose healthchecks
- **File:** `infra/docker-compose.yml`
- **Problem:** Most services have `/health` endpoint in code but no `healthcheck:` in compose.
- **Fix:** Add healthcheck for each service. Required for ALB target group health on ECS.

### CRA-17: Service discovery — env-var override layer
- **File:** `infra/docker-compose.yml`, all service configs
- **Problem:** Inter-service URLs use container names (`http://book-service:8082`). Won't resolve on ECS.
- **Fix:** Already uses env vars with Docker Compose defaults. Document the env vars needed for ECS (Cloud Map DNS or internal ALB).

### CRA-18: Redis persistence
- **Problem:** Redis Streams used for durable job processing (statistics, imports). Data lost on restart without persistence.
- **Fix:** Document requirement: ElastiCache with AOF persistence enabled. Or migrate job queue to SQS.

### CRA-19: NestJS graceful shutdown
- **File:** `services/api-gateway-bff/src/main.ts`
- **Problem:** No `app.enableShutdownHooks()`. Container killed mid-request on ECS task stop.
- **Fix:** Add `app.enableShutdownHooks()` after app creation.

### CRA-20: Touch targets — 44px minimum
- **Files:** `ChatHeader.tsx`, `ChatInputBar.tsx`
- **Problem:** Buttons ~27-34px, below WCAG 44px minimum.
- **Fix:** Increase padding/size. `min-h-[44px] min-w-[44px]`.

### CRA-21: DataTable overflow fix
- **File:** `components/data/DataTable.tsx`
- **Problem:** `overflow-hidden` clips tables on narrow screens.
- **Fix:** `overflow-x-auto`.

### CRA-22: VoiceModeOverlay touch controls
- **File:** `VoiceModeOverlay.tsx`
- **Problem:** "Space to pause" with no touch alternative. Buttons below 44px.
- **Fix:** Tap waveform area to cancel. Increase button sizes.

### CRA-23: Format pills responsive
- **File:** `ChatInputBar.tsx`
- **Problem:** Pills overflow on 320px screens.
- **Fix:** `flex-wrap` or `overflow-x-auto` with touch scroll.

### CRA-24: Remove localhost fallbacks — Go services
- **Files:** All Go service `config.go`
- **Problem:** `getEnv("URL", "http://localhost:PORT")` — silently routes to nothing in prod.
- **Fix:** Remove defaults for service URLs. Fail on missing.

### CRA-25: Remove localhost fallbacks — gateway-bff
- **File:** `services/api-gateway-bff/src/main.ts`
- **Problem:** 12 upstream URLs fall back to localhost.
- **Fix:** Same — required env vars, no defaults.

### CRA-26: MinIO SDK abstraction in book-service
- **File:** `services/book-service/internal/api/`
- **Problem:** Uses `minio-go` SDK directly. Swapping to S3 requires library change.
- **Fix:** The MinIO Go SDK is S3-compatible — just needs endpoint + credentials config via env vars. No code change needed, just document the config.

---

## Execution Order

```
Phase 1 (P0 — security + broken):     CRA-01..05    (5 tasks)
Phase 2 (P1 — sync + scale + mobile): CRA-06..15   (10 tasks)
Phase 3 (P2 — deploy + polish):       CRA-16..26   (11 tasks)
```

Each task follows the 9-phase workflow: PLAN → DESIGN → REVIEW → BUILD → TEST → REVIEW → QC → SESSION → COMMIT

---

*Created: 2026-04-11 — LoreWeave session 32*
*4 audit perspectives: frontend storage, backend cloud, multi-device, platform lock-in*
