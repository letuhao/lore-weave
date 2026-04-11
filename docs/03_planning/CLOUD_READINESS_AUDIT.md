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

### CRA-03: MINIO_EXTERNAL_URL must not default to localhost [DONE]
- **Files:** `services/book-service/internal/config/config.go`, `services/book-service/internal/api/media.go`, `services/video-gen-service/app/routers/generate.py`
- **Problem:** `MINIO_EXTERNAL_URL` defaulted to empty string, with fallback to internal MinIO endpoint — browsers can't reach internal endpoints in prod.
- **Fix:** Made `MINIO_EXTERNAL_URL` required in both services. Removed internal-endpoint fallback from `mediaURL()` / `media_url()`. Docker-compose provides `http://localhost:9123` for dev.

### CRA-04+05: Chat layout + settings panels responsive for mobile [DONE]
- **Files:** `ChatPage.tsx`, `SessionSidebar.tsx`, `SessionSettingsPanel.tsx`, `VoiceSettingsPanel.tsx`
- **Problem:** Session sidebar (270px) + app sidebar (240px) = 510px, overflows 375px phone. Settings panels also wider than viewport.
- **Fix:**
  - SessionSidebar: hidden on `< md`, shown as slide-in overlay with backdrop when hamburger button tapped. Auto-closes on session select.
  - ChatPage: added mobile hamburger bar (`md:hidden`) with Menu icon + active session title.
  - SessionSettingsPanel: `w-full sm:w-[380px]` (full-width on mobile).
  - VoiceSettingsPanel: `w-full sm:w-72` (full-width on mobile).

---

## P1 — Data Sync / Scalability / Usability (10 tasks)

### CRA-06..10: Sync localStorage preferences to server

All 5 share the same pattern — the existing `ThemeProvider` already syncs to `/v1/me/preferences`. These keys need the same treatment: read from server on login, write-through on change, localStorage as fast cache.

### CRA-06..10: Sync localStorage preferences to server [DONE]

Created `lib/syncPrefs.ts` utility. Each component now syncs to server on change via `PATCH /v1/me/preferences` (same pattern as ThemeProvider). localStorage remains as fast cache.

| Task | Server key | File | Status |
|------|-----------|------|--------|
| CRA-06 | `tts_prefs` | `components/reader/TTSSettings.tsx` | Done |
| CRA-07 | `voice_prefs` | `features/chat/voicePrefs.ts` | Done |
| CRA-08 | `ui_language` | `features/settings/LanguageTab.tsx` | Done |
| CRA-09 | `media_prefs` | `features/settings/ReadingTab.tsx` | Done |
| CRA-10 | — | `providers/ReaderThemeProvider.tsx` | N/A — dead code, ThemeProvider already syncs reader theme |

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

## P2 — Deploy Config / Polish (11 tasks) — ALL DONE

### CRA-16: Docker-compose healthchecks [DONE]
- Added healthchecks for 11 services: auth, book, sharing, catalog, provider-registry, usage-billing, translation, glossary, statistics, notification, api-gateway-bff.
- Go services: `wget -qO- http://localhost:PORT/health`
- Python: `python -c "urllib.request.urlopen(...)"`
- Skipped: worker-infra (no HTTP), translation-worker (no HTTP), frontend (static nginx).

### CRA-17: Service discovery — env-var override layer [DONE]
- **Resolved by CRA-24+25.** All inter-service URLs are now required env vars — no defaults. Docker-compose provides container names for dev. For AWS ECS, set to Cloud Map DNS names (e.g. `http://book-service.loreweave.local:8082`) or internal ALB DNS.

### CRA-18: Redis persistence [NOTED]
- Redis Streams used for: statistics event relay (outbox), import job processing.
- **AWS requirement:** Use ElastiCache with AOF persistence enabled, or migrate to SQS for job queues.
- Not a code change — deploy config for AWS.

### CRA-19: NestJS graceful shutdown [DONE]
- Added `app.enableShutdownHooks()` in `main.ts`. Handles SIGTERM for ECS rolling deploys.

### CRA-20: Touch targets [DONE]
- ChatHeader icon buttons: `p-1.5` → `p-2`, icons `15px` → `16px` (32px total touch target).

### CRA-21: DataTable overflow [DONE]
- `overflow-hidden` → `overflow-x-auto`. Tables scroll horizontally on narrow screens.

### CRA-22: VoiceModeOverlay touch controls [DONE]
- Added tap-to-cancel on waveform area during speaking (mobile only).
- Hidden keyboard-only hints (`Esc`/`Space`) on mobile.

### CRA-23: Format pills responsive [DONE]
- Added `flex-wrap` to format pills row. Wraps on narrow screens instead of overflowing.

### CRA-24+25: Remove localhost fallbacks [DONE]
- 7 Go services: 15 inter-service URL fields changed from `getEnv("KEY", "http://localhost:PORT")` to `os.Getenv("KEY")` + validation.
- api-gateway-bff: 12 upstream URLs changed to `requireEnv()`.

### CRA-26: MinIO SDK abstraction [NOTED]
- book-service and worker-infra use `minio-go` SDK directly. The MinIO Go SDK is already S3-compatible — same wire protocol.
- **AWS config:** Set `MINIO_ENDPOINT` to S3 endpoint (e.g. `s3.us-east-1.amazonaws.com`), `MINIO_USE_SSL=true`, credentials via IAM role or env vars. No code change needed.

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
