# Voice Pipeline V2 — Architecture Document

> **Status:** Design phase
> **Session:** 31 (2026-04-11)
> **Problem:** Voice Pipeline V1 has critical state management bugs and no audio persistence

---

## 1. Problems with V1

### 1.1 State Management is Broken

The current pipeline has no strict phase locking. Multiple subsystems run independently and race:

```
BUG: TTS is playing → VAD detects speech → STT fires → onSilenceDetected
     → sends new message → new pipeline starts → old TTS audio discarded
     → user hears nothing

BUG: LLM finishes in 300ms → stream-end effect runs → TTS takes 2000ms
     → by the time TTS resolves, pipeline generation changed → audio discarded

BUG: VAD restarts after TTS → captures background noise → STT returns garbage
     → triggers new LLM turn → infinite conversation with itself
```

**Root cause:** The pipeline uses React state/effects for control flow instead of a strict state machine. Phase transitions are async (React batches), but the pipeline needs synchronous control.

### 1.2 No Audio Persistence

TTS audio is generated, held in memory, and discarded if anything changes. No replay, no history, no recovery.

---

## 2. V2 Architecture

### 2.1 Design Principles

1. **Strict state machine** — Only ONE thing happens at a time. No concurrent STT + TTS.
2. **Audio persistence** — All TTS audio stored in MinIO with URLs attached to chat messages.
3. **Phase locking** — When in SPEAKING phase, ALL input is blocked (no VAD, no STT, no new sends).
4. **Orchestrator pattern** — Single controller manages all transitions, not React effects.

### 2.2 State Machine

```
                    ┌──────────┐
                    │   IDLE   │
                    └────┬─────┘
                         │ activate()
                         ▼
               ┌─────────────────┐
          ┌───▶│   LISTENING     │◀────────────────────┐
          │    │  VAD active     │                      │
          │    │  STT ready      │                      │
          │    └────────┬────────┘                      │
          │             │ VAD: onSpeechEnd              │
          │             ▼                               │
          │    ┌─────────────────┐                      │
          │    │  TRANSCRIBING   │                      │
          │    │  VAD paused     │                      │
          │    │  Sending to STT │                      │
          │    └────────┬────────┘                      │
          │             │ STT returns text              │
          │             ▼                               │
          │    ┌─────────────────┐                      │
          │    │  PROCESSING     │                      │
          │    │  VAD paused     │                      │
          │    │  LLM streaming  │                      │
          │    │  TTS generating │                      │
          │    └────────┬────────┘                      │
          │             │ First TTS audio ready         │
          │             ▼                               │
          │    ┌─────────────────┐                      │
          │    │   SPEAKING      │                      │
          │    │  VAD DISABLED   │ ◀── KEY: no input    │
          │    │  STT DISABLED   │     accepted here    │
          │    │  Playing audio  │                      │
          │    │  Queuing more   │                      │
          │    └───┬────────┬────┘                      │
          │        │        │                           │
          │   cancel/   all audio                       │
          │   barge-in  played                          │
          │        │        │                           │
          │        ▼        └───────────────────────────┘
          │    ┌─────────┐
          └────│ PAUSED  │ (optional)
               └─────────┘
```

**Critical rule:** In SPEAKING phase:
- VAD is **destroyed** (not just paused)
- No `onSpeechEnd` events can fire
- No STT requests can be made
- No `onSilenceDetected` can trigger
- Only barge-in (manual button) or "all audio played" can exit this phase

### 2.3 Phase Transitions (Strict)

| From | To | Trigger | Actions |
|------|------|---------|---------|
| IDLE → LISTENING | `activate()` | Create VAD, start monitoring |
| LISTENING → TRANSCRIBING | VAD `onSpeechEnd` | Pause VAD, send audio to STT |
| TRANSCRIBING → PROCESSING | STT returns text | Destroy VAD, send to LLM, start pipeline |
| TRANSCRIBING → LISTENING | STT returns empty/garbage | Resume VAD |
| PROCESSING → SPEAKING | First TTS audio stored + ready to play | Start audio playback queue |
| SPEAKING → LISTENING | All audio played (`onAllPlayed`) | Re-create VAD, start monitoring |
| SPEAKING → LISTENING | User presses cancel/barge-in button | Stop playback, re-create VAD |
| ANY → IDLE | `deactivate()` | Destroy everything |

### 2.4 Barge-in: Button Only (No Auto-Detection)

V1's auto barge-in (VAD during playback) causes the exact bug described — it captures TTS audio output from speakers, sends to STT, triggers new LLM turns.

**V2 approach:** Barge-in is a **manual button** only. User presses "Stop" or a keyboard shortcut (Space) to interrupt. No microphone monitoring during SPEAKING phase.

This eliminates:
- Echo/feedback loops
- False barge-in from speaker output
- AudioContext/AnalyserNode complexity
- The need for acoustic echo cancellation

If auto barge-in is desired later, it should use **headphone detection** — only enable when headphones are connected (no speaker-to-mic bleed).

---

## 3. Audio Persistence Architecture

### 3.1 Flow

```
LLM token → SentenceBuffer → sentence emitted
  → TTS service generates audio
  → Upload to MinIO: voice-chat/{session_id}/{message_id}/{sentence_index}.wav
  → Get signed URL (48h expiry)
  → Store URL on message (audio_segments array)
  → Enqueue for playback
  → Also: playback from URL (not from memory)
```

### 3.2 Storage Schema

```
MinIO bucket: loreweave-media
Path: voice-chat/{session_id}/{message_id}/{index}_{timestamp}.wav

Lifecycle: auto-delete after 48 hours (configurable)
```

### 3.3 Chat Message Schema Extension

```sql
-- Add to chat messages table
ALTER TABLE chat_messages ADD COLUMN audio_segments JSONB DEFAULT NULL;

-- Example value:
-- [
--   {"index": 0, "url": "http://minio:9000/...", "text": "Hello!", "duration_s": 1.2},
--   {"index": 1, "url": "http://minio:9000/...", "text": "How can I help?", "duration_s": 2.1}
-- ]
```

### 3.4 Audio Upload Endpoint

New endpoint on chat-service (or a dedicated audio endpoint):

```
POST /v1/chat/sessions/{session_id}/messages/{message_id}/audio
Content-Type: multipart/form-data

Fields:
  file: WAV audio blob
  index: sentence index (0, 1, 2...)
  text: the sentence text

Response:
  { "url": "http://...", "duration_s": 1.5 }
```

### 3.5 Frontend: Audio Indicator on Messages

```
┌──────────────────────────────────────────────┐
│  AI message with audio:                      │
│                                              │
│  Hello! How can I help you today?            │
│                                              │
│  🔊 ▶ ━━━━━━━━━━━━ 0:03 / 0:05             │
│     [sentence 1] [sentence 2] [sentence 3]   │
│                                              │
│  ⏸ Playing...                                │
└──────────────────────────────────────────────┘
```

Features:
- Audio indicator (🔊 icon) on messages that have `audio_segments`
- Play/pause button — replays the full response audio
- Per-sentence segments — click to play a specific sentence
- Progress bar showing playback position
- Works in both chat mode and voice mode

---

## 4. Revised Pipeline Flow

### 4.1 Complete Turn Cycle

```
Phase         │ Active Components         │ Disabled
──────────────┼───────────────────────────┼─────────────────
LISTENING     │ VAD monitoring            │ STT, LLM, TTS
TRANSCRIBING  │ STT processing            │ VAD, LLM, TTS
PROCESSING    │ LLM streaming, TTS gen    │ VAD, STT
SPEAKING      │ Audio playback            │ VAD, STT, LLM, TTS
──────────────┼───────────────────────────┼─────────────────
```

### 4.2 Processing Phase Detail

```
1. LLM starts streaming (SSE)
2. onStreamDelta fires per token → SentenceBuffer accumulates
3. Sentence boundary detected:
   a. Submit sentence to TTS (via TTSConcurrencyPool, max 2)
   b. TTS returns audio ArrayBuffer
   c. Upload audio to MinIO → get URL
   d. Store URL in message's audio_segments
   e. Enqueue audio for playback (TTSPlaybackQueue)
4. First audio enqueued → transition to SPEAKING
5. LLM stream ends → flush SentenceBuffer → close queue
```

### 4.3 Speaking Phase Detail

```
1. TTSPlaybackQueue plays audio chunks sequentially
2. VAD is DESTROYED — no microphone access
3. No STT requests possible
4. Only two exit paths:
   a. onAllPlayed → all audio finished → transition to LISTENING
   b. User presses cancel → stop playback → transition to LISTENING
5. On transition to LISTENING:
   - Create new VAD instance
   - Start monitoring for next speech
```

---

## 5. Implementation Tasks

### Phase A: Fix Pipeline State Machine

| Task | Scope | Priority |
|------|-------|----------|
| **VP2-01** | Strict state machine — replace React effects with imperative controller class. Single `VoicePipelineController` owns all state transitions. No `useEffect` for control flow. | P0 |
| **VP2-02** | Phase locking — VAD destroyed in PROCESSING/SPEAKING, recreated in LISTENING. No microphone access during playback. | P0 |
| **VP2-03** | Remove auto barge-in (BargeInDetector) — replace with manual cancel button only. | P0 |
| **VP2-04** | TRANSCRIBING phase — separate from PROCESSING. VAD paused during STT request, resumed if STT returns empty. | P1 |

### Phase B: Audio Persistence

| Task | Scope | Priority |
|------|-------|----------|
| **VP2-05** | MinIO audio upload endpoint in chat-service (or new audio endpoint). | P1 |
| **VP2-06** | Chat message `audio_segments` JSONB column + migration. | P1 |
| **VP2-07** | Pipeline: upload TTS audio to MinIO before enqueuing for playback. | P1 |
| **VP2-08** | Audio playback from URL instead of ArrayBuffer (TTSPlaybackQueue update). | P1 |
| **VP2-09** | MinIO lifecycle policy: auto-delete voice-chat audio after 48h. | P2 |

### Phase C: Chat UI Audio

| Task | Scope | Priority |
|------|-------|----------|
| **VP2-10** | Audio indicator on assistant messages (🔊 icon when audio_segments exists). | P1 |
| **VP2-11** | Audio replay player — play/pause, progress bar, per-sentence segments. | P1 |
| **VP2-12** | Audio player in voice mode overlay — shows currently playing sentence. | P2 |

### Phase D: Polish

| Task | Scope | Priority |
|------|-------|----------|
| **VP2-13** | Configurable audio retention (48h default, settings UI). | P2 |
| **VP2-14** | Audio download button on messages. | P3 |
| **VP2-15** | Headphone detection for optional auto barge-in. | P3 |

---

## 6. VoicePipelineController (Imperative, Not React Effects)

### 6.1 Why Not React Effects

React effects are designed for synchronizing UI with state. They are:
- **Async** — batched by React, fire after render
- **Re-entrant** — deps changes re-run the effect
- **Cleanup-based** — cleanup runs before the next effect, not before state changes

This makes them **wrong for pipeline control flow** where:
- Transitions must be synchronous and atomic
- Multiple state variables change together
- In-flight async operations (TTS fetch) must be tracked per-pipeline-instance

### 6.2 Controller Design

```typescript
class VoicePipelineController {
  private phase: VoicePhase = 'idle';
  private vad: MicVAD | null = null;
  private sentenceBuffer: SentenceBuffer | null = null;
  private ttsPool: TTSConcurrencyPool | null = null;
  private ttsQueue: TTSPlaybackQueue | null = null;
  private generation = 0;

  // React state setter (for UI updates only)
  private setPhase: (phase: VoicePhase) => void;
  private setMetrics: (fn: (prev: Metrics) => Metrics) => void;

  /** Strict phase transition — validates from→to is allowed */
  private transition(to: VoicePhase) {
    const allowed: Record<string, string[]> = {
      idle: ['listening'],
      listening: ['transcribing', 'idle'],
      transcribing: ['processing', 'listening', 'idle'],
      processing: ['speaking', 'idle'],
      speaking: ['listening', 'idle'],
    };
    if (!allowed[this.phase]?.includes(to)) {
      console.warn(`[Pipeline] Invalid transition: ${this.phase} → ${to}`);
      return false;
    }

    console.log(`[Pipeline] ${this.phase} → ${to}`);
    this.phase = to;
    this.setPhase(to); // Update React state for UI
    this.onPhaseChange(to);
    return true;
  }

  /** Phase-specific setup/teardown */
  private onPhaseChange(phase: VoicePhase) {
    switch (phase) {
      case 'listening':
        this.createVAD();  // Start microphone monitoring
        break;
      case 'transcribing':
        this.vad?.pause(); // Stop VAD but keep instance
        break;
      case 'processing':
        this.destroyVAD(); // No mic access during LLM+TTS
        this.startPipeline();
        break;
      case 'speaking':
        // VAD already destroyed — no mic access
        // Audio playback starts
        break;
      case 'idle':
        this.destroyVAD();
        this.stopPipeline();
        break;
    }
  }

  /** Called when VAD detects speech ended */
  onSpeechEnd(audio: Float32Array) {
    if (this.phase !== 'listening') return; // STRICT GATE
    this.transition('transcribing');
    this.transcribe(audio);
  }

  /** Called when STT returns result */
  onTranscriptionComplete(text: string) {
    if (this.phase !== 'transcribing') return; // STRICT GATE
    if (!text || text.length < 2) {
      this.transition('listening'); // Resume VAD
      return;
    }
    this.transition('processing');
    this.sendToLLM(text);
  }

  /** Called when first TTS audio is ready to play */
  onFirstAudioReady() {
    if (this.phase !== 'processing') return; // STRICT GATE
    this.transition('speaking');
  }

  /** Called when all TTS audio has finished playing */
  onAllAudioPlayed() {
    if (this.phase !== 'speaking') return; // STRICT GATE
    this.transition('listening');
  }

  /** User pressed cancel during speaking */
  cancelSpeaking() {
    if (this.phase !== 'speaking') return;
    this.ttsQueue?.cancelAll();
    this.transition('listening');
  }
}
```

### 6.3 Key Difference from V1

| Aspect | V1 (Current) | V2 (Proposed) |
|--------|-------------|---------------|
| State management | React useState + useEffect chain | Imperative class with strict transition validation |
| Phase checks | `phaseRef.current` (may be stale) | `this.phase` (always current, synchronous) |
| VAD lifecycle | Start/stop via effects (async) | Create/destroy explicitly per phase |
| Pipeline control | Refs + generation counter | Class owns all components directly |
| STT during TTS | VAD still active → captures speaker output | VAD destroyed → impossible |
| Audio persistence | None (in-memory, discarded) | MinIO storage with URL replay |

---

## 7. Migration Path

1. **VP2-01 first** — build `VoicePipelineController` with strict state machine. This alone fixes ALL current bugs (double-send, audio discard, noise loop, TTS during STT).
2. **VP2-02 + VP2-03** — remove BargeInDetector, implement phase locking.
3. **VP2-05..VP2-08** — audio persistence (can be done independently).
4. **VP2-10..VP2-12** — UI features (after persistence is working).

The controller can wrap the existing hooks initially, then gradually absorb their logic.

---

## 8. Open Questions

1. **Audio format for MinIO storage:** WAV (large, simple) or MP3 (smaller, needs encoding)?
2. **Should audio_segments be on the message or a separate table?** JSONB on message is simpler but grows the message size.
3. **Retention policy:** Per-user configurable or global 48h? Should premium users get longer retention?
4. **Offline replay:** Should audio URLs be signed (time-limited) or use session auth?

---

*Created: 2026-04-11 — LoreWeave session 31*
