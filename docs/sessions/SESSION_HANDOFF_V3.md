# Session Handoff — Session 31 (Extended)

> **Purpose:** Give the next agent complete context to continue.
> **Date:** 2026-04-10→11 (session 31, 3 context windows)
> **Last commit:** `6e1d81e` — docs(V2): add streaming TTS playback
> **Uncommitted work:** V2 pipeline doc updates (competitor review + 5 latency optimizations + plan fixes)
> **Previous focus:** GEP backend (session 30), Translation Pipeline V2 (session 29)
> **Current focus:** Voice Pipeline V2 architecture COMPLETE (design), ready for implementation

---

## 1. What Was Done This Session (50+ commits across 3 context windows)

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

### Real-Time Voice Pipeline (RTV-01..04) — COMPLETE (V1, superseded by V2)
- RTV-01+02: SentenceBuffer + TTSPlaybackQueue (18 unit tests)
- RTV-03: Wire streaming TTS pipeline into voice mode + review (16 issues)
- RTV-04: Barge-in detection with echo prevention + review (16 issues)
- Multiple bug fix iterations: double-send, infinite loop (noise), TTS audio discarded
- Silero VAD integration (4 attempts: nginx MIME, CDN CORS, vite-plugin-static-copy)
- V1 pipeline works but has state management races → V2 redesign addresses them

### Voice Pipeline V2 Architecture — DESIGN COMPLETE
- Complete redesign doc: 900+ lines, 45 tasks across 6 phases (A-F)
- Strict state machine (VoicePipelineController class, not React effects)
- Audio persistence (MinIO + message_audio_segments table)
- Text normalizer (3-layer: voice prompt → rule-based → optional LLM rewriter)
- 6 review rounds: context engineer, data engineer, UX designer, security engineer, performance engineer, competitor review
- 44 total issues found and addressed
- Competitor analysis: vs OpenAI Realtime API, Pipecat, LiveKit, ElevenLabs
- 5 latency optimizations: clause-level splits, filler TTS, persistent MediaStream, adaptive threshold, TTS pre-warm
- Estimated ~800ms time-to-first-audio (competitive with LiveKit)

### Documentation
- External AI Service Integration Guide (1096 lines) — TTS/STT/Image/Video contracts
- Verified against OpenAI Python SDK (2025-12 spec)
- Streaming TTS/STT contracts + known limitations
- Real-Time Voice Pipeline design doc (633 lines, V1 reference)
- Voice Pipeline V2 design doc (900+ lines, implementation-ready)

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
| `docs/03_planning/data_pipelines/VOICE_PIPELINE_V2.md` | V2 pipeline design (45 tasks, 6 phases) |
| `docs/03_planning/data_pipelines/REALTIME_VOICE_PIPELINE.md` | V1 pipeline design (reference only) |
| `frontend/src/lib/SentenceBuffer.ts` | Sentence boundary detection (18 unit tests) |
| `frontend/src/lib/TTSPlaybackQueue.ts` | FIFO audio playback queue |
| `frontend/src/lib/TTSConcurrencyPool.ts` | Bounded TTS request pool (max 3) |
| `frontend/src/lib/BargeInDetector.ts` | Echo-safe barge-in (V1, to be removed in V2) |

---

## 4. What's Next (Priority Order)

| Priority | Item | Notes |
|----------|------|-------|
| **P0** | **Voice Pipeline V2 — Phase A** (VP2-01..04, 36, 42-45) | 9 tasks: state machine, streaming TTS, latency opts. Design doc at `docs/03_planning/data_pipelines/VOICE_PIPELINE_V2.md` |
| **P1** | **Voice Pipeline V2 — Phase B-F** (VP2-05..41) | Text normalizer, audio persistence, chat UI, voice assist, security |
| **P1** | **Translation Workbench** (P3-T1..T8) | 8 tasks, block-level translation. Design draft exists. |
| **P1** | **Build external TTS/STT services** | Separate repos. Integration guide + mock service ready. |
| P2 | GUI Review deferred (D1-D22) | Editor/glossary/reader polish |
| P2 | Chat Service Phase 4 | File attachments + multi-modal |
| P2 | Platform Mode (35 tasks) | Multi-tenant SaaS features |
| P2 | Onboarding Wizard (P2-10) | New user experience |

### Voice Pipeline V2 — Phase A Critical Path
```
VP2-01 (controller) → VP2-42 (persistent stream) → VP2-02 (phase lock)
                    → VP2-03 (exit condition)
                    → VP2-04 (remove barge-in)
VP2-36 (streaming TTS) → VP2-43 (pre-warm + filler)
VP2-45 (clause-level buffer) — independent
VP2-44 (adaptive threshold) — after VP2-02
```

---

## 5. Environment

- Docker Compose: 23 services + optional `mock-audio-service` (profile: audio)
- Frontend: Vite + React + Tailwind (port 5174)
- Gateway: NestJS BFF (port 3123)
- Test account: `letuhao1994@gmail.com` / `Ab.0914113903`
- LM Studio model: `qwen3.5-9b-uncensored-hauhaucs-aggressive` (user_model_id: `019d56b5-e398-77d1-b036-21807e57ecf3`)
- Planning doc: `docs/03_planning/99A_FRONTEND_V2_IMPLEMENTATION_TASKS.md` (640/712 done)
- Voice V2 pipeline: `docs/03_planning/data_pipelines/VOICE_PIPELINE_V2.md` (45 tasks, design-complete)
- Known V1 bugs: TTS audio discarded in some cases, STT+TTS state races → V2 pipeline fixes all
