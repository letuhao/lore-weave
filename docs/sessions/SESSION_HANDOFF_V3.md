# Session Handoff — Session 31

> **Purpose:** Give the next agent complete context to continue.
> **Date:** 2026-04-10→11 (session 31)
> **Last commit:** `e54557e` — fix(AISR-03+04): post-review — 20 issues resolved
> **Uncommitted work:** None
> **Previous focus:** GEP backend (session 30), Translation Pipeline V2 (session 29)
> **Current focus:** GEP complete, Voice Mode complete, AI Service Readiness complete

---

## 1. What Was Done This Session (29 commits)

### GEP (Glossary Extraction Pipeline) — FULLY COMPLETE
- 10 BE bug fixes from real AI model testing (Qwen 3.5 9B, LM Studio)
- GEP-BE-13 integration test: 49 assertions (cancellation, multi-batch, concurrent, dedup)
- 7 FE tasks: extraction wizard (profile/batch/confirm/progress/results), entry points (3 tabs), alive badge
- Browser smoke test: 9 screens verified via Playwright MCP

### Voice Mode for Chat — 6 tasks COMPLETE
- VM-01: `useSpeechRecognition` hook (Web Speech API, factory pattern, silence detection)
- VM-02: `VoiceSettingsPanel` (STT/TTS model selectors, i18n 4 languages)
- VM-03: `useVoiceMode` orchestrator (state machine: idle→listening→processing→speaking)
- VM-04: Push-to-talk mic button in ChatInputBar
- VM-05: Voice mode overlay (waveform, transcript, controls)
- VM-06: Integration wiring (ChatHeader toggle, ChatWindow orchestration)
- 2 review passes: 17 issues found and fixed (stale closures, ARIA, dual STT conflict, session change)

### AI Service Readiness (AISR) — 5 tasks COMPLETE
- AISR-01: Gateway `/v1/audio/*` proxy routes (TTS, STT, voices) with 503 fallback
- AISR-02: Mock audio service (Python/FastAPI) for testing
- AISR-03: `useBackendSTT` hook (MediaRecorder → multipart upload → transcript)
- AISR-04: `useStreamingTTS` hook (fetch → AudioContext playback)
- AISR-05: Integration test script (19 assertions)
- Review: 20 issues fixed (AudioContext leaks, race conditions, Safari compat)

### Documentation
- External AI Service Integration Guide (1096 lines) — TTS/STT/Image/Video contracts
- Verified against OpenAI Python SDK (2025-12 spec)
- Streaming TTS/STT contracts + known limitations
- 99A planning doc: 464 task markers bulk-updated (640/712 done)
- SESSION_PATCH rewritten with actual completion status

---

## 2. Architecture: Voice Mode + Audio Services

```
┌─────────────┐     ┌──────────────┐     ┌───────────────────┐
│ Chat UI     │     │ API Gateway  │     │ External Audio    │
│ VoiceMode   │────▶│ /v1/audio/*  │────▶│ Service (TTS/STT) │
│ Overlay     │◀────│ proxy        │◀────│ (separate repo)   │
└─────────────┘     └──────────────┘     └───────────────────┘
       │
       ▼ (fallback)
 Browser Web Speech API
```

- Frontend switches between browser and backend STT/TTS based on `voicePrefs.sttSource/ttsSource`
- Gateway returns 503 when `AUDIO_SERVICE_URL` is not set
- Mock audio service available via `docker compose --profile audio up`
- Integration guide at `docs/04_integration/EXTERNAL_AI_SERVICE_INTEGRATION_GUIDE.md`

---

## 3. Key New Files

| File | Purpose |
|------|---------|
| `frontend/src/hooks/useSpeechRecognition.ts` | Browser STT (Web Speech API, factory pattern) |
| `frontend/src/hooks/useBackendSTT.ts` | Backend STT (MediaRecorder → /v1/audio/transcriptions) |
| `frontend/src/hooks/useStreamingTTS.ts` | Backend TTS (fetch → AudioContext playback) |
| `frontend/src/features/chat/hooks/useVoiceMode.ts` | Voice conversation orchestrator |
| `frontend/src/features/chat/voicePrefs.ts` | Voice settings (localStorage) |
| `frontend/src/features/chat/components/VoiceModeOverlay.tsx` | Full-screen voice UI |
| `frontend/src/features/chat/components/VoiceSettingsPanel.tsx` | Settings slide-over |
| `frontend/src/features/chat/components/WaveformVisualizer.tsx` | CSS waveform animation |
| `frontend/src/features/extraction/ExtractionWizard.tsx` | GEP wizard shell |
| `frontend/src/features/extraction/StepProfile.tsx` | Kind/attribute selection |
| `frontend/src/features/extraction/StepBatchConfig.tsx` | Chapter selection |
| `frontend/src/features/extraction/StepConfirm.tsx` | Cost estimate + confirm |
| `frontend/src/features/extraction/StepProgress.tsx` | Live progress polling |
| `frontend/src/features/extraction/StepResults.tsx` | Results summary |
| `infra/mock-audio-service/main.py` | Mock TTS/STT for testing |
| `infra/test-gep-integration.sh` | GEP integration test (49 assertions) |
| `infra/test-audio-service.sh` | Audio service test (19 assertions) |
| `docs/04_integration/EXTERNAL_AI_SERVICE_INTEGRATION_GUIDE.md` | External dev guide |

---

## 4. What's Next (Priority Order)

| Priority | Item | Notes |
|----------|------|-------|
| **P1** | **Translation Workbench** (P3-T1..T8) | 8 tasks, block-level translation. Design draft exists. |
| **P1** | **Build external TTS/STT services** | Separate repos. Integration guide + mock service ready. |
| P2 | GUI Review deferred (D1-D22) | Editor/glossary/reader polish |
| P2 | Chat Service Phase 4 | File attachments + multi-modal |
| P2 | Platform Mode (35 tasks) | Multi-tenant SaaS features |
| P2 | Onboarding Wizard (P2-10) | New user experience |

---

## 5. Environment

- Docker Compose: 23 services + optional `mock-audio-service` (profile: audio)
- Frontend: Vite + React + Tailwind (port 5174)
- Gateway: NestJS BFF (port 3123)
- Test account: `letuhao1994@gmail.com` / `Ab.0914113903`
- LM Studio model: `qwen3.5-9b-uncensored-hauhaucs-aggressive` (user_model_id: `019d56b5-e398-77d1-b036-21807e57ecf3`)
- Planning doc: `docs/03_planning/99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` (640/712 done)
