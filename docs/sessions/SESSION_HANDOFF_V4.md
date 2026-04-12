# Session Handoff — Session 33

> **Purpose:** Give the next agent complete context to continue.
> **Date:** 2026-04-12 (session 33)
> **Last commit:** `236727c` — VP2-32+33 review fix
> **Previous focus:** Cloud Readiness Audit (session 32), Voice Pipeline V2 (session 33)

---

## 1. What Was Done This Session (29 commits)

### Voice Pipeline V2 — COMPLETE (48/48 tasks)

Server-side voice pipeline: browser captures audio via VAD → POST to chat-service → STT → LLM → TTS → SSE stream back with text + audio chunks.

**Phase A: Core Pipeline (11 tasks)**
- Backend: `TextNormalizer` (24 tests), `SentenceBuffer` (31 tests), `voice_stream_response()` async generator, `POST /voice-message` endpoint (7 tests), voice system prompt injection
- Frontend: `VoiceClient`, `VadController`, `TTSPlaybackQueue.enqueueBase64`, `useVoiceChat` hook, `VoiceChatOverlay`
- Fixed 14 pre-existing chat-service test failures
- 137 total chat-service tests pass

**Phase B: Audio Persistence (8 tasks)**
- `message_audio_segments` table, S3 upload (fire-and-forget), audio segments GET endpoint with signed URLs, `AudioReplayPlayer` component, cleanup endpoint, GDPR erasure endpoint

**Phase C: UX Polish (8 tasks)**
- Mic badge on voice messages, health dot (TTFT-based), "Thinking..." indicator, error recovery with consecutive fail tracking, VAD presets (Fast/Normal/Patient/Learner) + manual sliders

**Phase D: Voice Assist (7 tasks)**
- Push-to-talk with backend STT (Safari MIME fallback), 4-state mic button, auto-TTS on AI response (`useAutoTTS` hook), "Stop Audio" button

**Phase E: Security (9 tasks)**
- Voice consent dialog (localStorage + server sync), textarea disabled during voice mode, `showVoiceMetrics` debug pref, headphone detection utility

**Voice Analytics Pipeline (5 bonus tasks)**
- `voice.turn` events emitted to Redis Stream from chat-service
- `voice_turn_events` table in statistics-service (lean schema: 6 fields, all drive decisions)
- Redis consumer stores raw events, no per-turn aggregation
- `GET /internal/voice-stats/{user_id}` with correlation query (misfire rate per threshold level)
- `GET /v1/chat/voice/recommended-settings` endpoint for UI suggestions

### Integration fixes during testing
- `python-multipart` dependency for FastAPI File/Form
- VAD asset paths (`/vad/` for ONNX model)
- STT model validation on frontend (require model configured)
- STT `model` field in multipart request (resolved from provider-registry)
- Clause-mode splitting disabled (full sentences for natural TTS prosody)

---

## 2. Current State

### What's Working
- Voice Mode: VAD → audio capture → server-side STT → LLM → text streaming → audio replay
- Audio persistence: segments stored in S3, replay via signed URLs
- Voice Assist: push-to-talk mic in chat input bar, auto-TTS on AI responses
- Voice analytics: events collected, recommendations computed
- All 137 chat-service tests pass
- Frontend TypeScript compiles clean

### Known Issues (To Debug Next)
- **TTS audio quality** — choppy/weird quality when tested with local TTS service. May be TTS model quality, audio format, or playback gaps. Needs investigation with a production-quality TTS provider.
- **V1 voice code still exists** — `useVoiceMode.ts` (631 lines), `VoiceModeOverlay.tsx`, related V1 hooks are still in the codebase. They're not imported by ChatWindow anymore (switched to V2) but should be cleaned up.

### Test Account
```
email:    claude-test@loreweave.dev
password: Claude@Test2026
```

---

## 3. Architecture Decisions Made This Session

1. **Voice pipeline is server-side** — chat-service orchestrates STT → LLM → TTS, not the browser. Gains: crash recovery, server-side normalization, audio persistence. Cost: ~200ms latency vs client-side.

2. **No Vercel Workflow** — rejected (Vercel-only platform). Voice is a regular HTTP endpoint in chat-service.

3. **Full sentences for TTS** — clause-mode splitting (commas at 40+ chars) produced choppy speech. All competitors use full-sentence TTS.

4. **Model names from provider-registry** — no hardcoded model names. Chat-service resolves `provider_model_name` from user's registered credentials.

5. **Lean analytics schema** — only 6 fields per voice event, all drive decisions. Dropped TTS metrics (separate concern). No pre-aggregated table (query raw events directly).

6. **VAD stays in browser** — Silero ONNX model runs client-side (~2MB, loads once). Only completed speech segments sent to server. Saves bandwidth + server cost.

---

## 4. What's Next

- **TTS quality debugging** — test with OpenAI TTS, ElevenLabs, or Kokoro to isolate whether the issue is the local TTS model or the playback pipeline
- **V1 code cleanup** — remove `useVoiceMode.ts`, old `VoiceModeOverlay.tsx`, and V1-only hooks
- **Voice Settings UI** — wire the new preferences (Voice Assist toggle, auto-TTS, debug metrics) into VoiceSettingsPanel
- **Recommended settings UI** — show analytics recommendation in Voice Settings ("Based on your usage, we suggest: Patient mode")

---

*Session 33: 29 commits, Voice Pipeline V2 complete (48 tasks + 5 analytics tasks)*
