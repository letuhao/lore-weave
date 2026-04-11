# Real-Time Voice Pipeline — Design Document

> **Status:** Design complete, ready for implementation
> **Session:** 31 (2026-04-11)
> **Prerequisite:** Voice Mode (VM-01..06) ✅, AI Service Readiness (AISR-01..05) ✅
> **External services:** Whisper STT (port 18001) ✅, Kokoro TTS (port 9880) ✅

---

## 1. Problem Statement

The current voice mode uses a **cascading batch architecture**:

```
Record full audio → upload WAV → Whisper STT (17s) → wait
→ send text to LLM → stream response → wait for full text
→ send to TTS → wait for full audio → play
```

**Total latency per turn: 5-20 seconds.** Human conversation requires **<1 second** response time.

### Industry Benchmarks (2026)

| Architecture | Time-to-first-audio | Provider examples |
|-------------|--------------------|--------------------|
| Cascading (current) | 5-20s | Our current implementation |
| Streaming pipeline | 0.7-1.5s | Pipecat, LiveKit, Retell |
| Native speech-to-speech | ~500ms | OpenAI Realtime API, Gemini 2.5 Flash |

**Target: Tier 2 — Streaming Pipeline (~1s to first audio)**

---

## 2. Architecture: Streaming Pipeline

### 2.1 High-Level Flow

```
                    ┌──────────────────────────────────────────────┐
                    │            CONCURRENT PIPELINE               │
                    │                                              │
  🎤 Mic ──▶ VAD ──▶ STT (streaming) ──▶ LLM (SSE tokens)       │
                    │                         │                    │
                    │                    Sentence Buffer           │
                    │                    "Hello." ──▶ TTS ──▶ 🔊  │
                    │                    "How are" (accumulating)  │
                    │                    "How are you?" ──▶ TTS ──▶ 🔊
                    │                         │                    │
                    │              ◀── pause mic during playback   │
                    │              ──▶ resume mic after playback   │
                    └──────────────────────────────────────────────┘
```

### 2.2 Component Breakdown

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌──────────┐
│    VAD      │──▶│  Streaming   │──▶│   LLM       │──▶│  Sentence   │──▶│ Streaming│──▶🔊
│  (client)   │   │  STT         │   │   (SSE)     │   │  Buffer     │   │  TTS     │
│             │   │  (WebSocket) │   │             │   │  + Chunker  │   │  (queue) │
└─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘   └──────────┘
       │                                                                       │
       │◀──────────────── Barge-in Detection ──────────────────────────────────│
       │           (if user speaks during TTS → cancel everything)             │
```

---

## 3. Detailed Algorithm

### 3.1 Phase: Listening

```
LOOP:
  1. VAD monitors microphone audio level
  2. On speech detected (volume > threshold):
     - Transition to RECORDING
     - Start streaming audio chunks to STT (WebSocket or chunked HTTP)
  3. Display partial STT results in real-time (interim transcripts)
  4. On silence detected (volume < threshold for N ms):
     - Finalize transcript
     - Transition to PROCESSING
```

### 3.2 Phase: Processing (LLM + TTS Pipeline)

```
CONCURRENT:
  1. Send finalized transcript to LLM via SSE stream
  2. Initialize SentenceBuffer (empty)
  3. Initialize TTSQueue (FIFO)
  
  FOR EACH LLM token:
    a. Append token to SentenceBuffer
    b. Check for sentence boundary:
       - Boundaries: . ! ? 。！？ \n (and ." !" ?" for quoted speech)
       - Minimum sentence length: 10 chars (avoid single-word fragments)
    c. If boundary detected:
       - Extract completed sentence from buffer
       - Submit sentence to TTS (async, non-blocking)
       - TTS result goes into TTSQueue
       - If first sentence: transition to SPEAKING as soon as audio ready
  
  4. On LLM stream complete:
     - Flush remaining buffer to TTS (last partial sentence)
     - Mark queue as "no more items coming"
```

### 3.3 Phase: Speaking (Concurrent TTS Playback)

```
CONCURRENT WITH PROCESSING:
  1. TTSQueue consumer:
     - Take next audio chunk from queue
     - Play via AudioContext (schedule at end of previous chunk)
     - Track playback position for interruption
  
  2. Barge-in detection:
     - Keep VAD active during playback (but don't send to STT yet)
     - If user speaks (volume > barge_threshold for > 200ms):
       a. Stop current TTS playback immediately
       b. Cancel remaining TTS requests in queue
       c. Cancel LLM generation (abort SSE stream)
       d. Transition to LISTENING (user's speech becomes next turn)
  
  3. On queue empty + all audio played:
     - Transition to LISTENING
     - Resume STT streaming
```

### 3.4 Interruption Handling (Barge-in)

```
User speaks while AI is talking:
  
  ┌─ AI speaking ─────────────────────────┐
  │  "The castle stood on a hill over—"   │  ← STOP HERE
  │                                        │
  │  User: "Wait, what castle?"           │  ← New input
  └────────────────────────────────────────┘
  
  Actions:
  1. audioContext.suspend() or source.stop() — immediate silence
  2. abortController.abort() — cancel in-flight TTS requests
  3. chat.stop() — cancel LLM SSE stream
  4. Clear TTSQueue
  5. STT starts processing user's barge-in speech
  6. New LLM turn begins with interrupted context
```

---

## 4. STT Strategy: Hybrid Approach

### 4.1 Option A: WebSocket Streaming STT (Lowest Latency)

```
Client                          STT Service (WebSocket)
  │                                    │
  │ ──── audio chunk (250ms) ─────▶   │
  │ ◀──── partial: "The cas"  ────    │
  │ ──── audio chunk (250ms) ─────▶   │
  │ ◀──── partial: "The castle" ──    │
  │ ──── audio chunk (250ms) ─────▶   │
  │ ◀──── partial: "The castle st"    │
  │ ──── [flush] ─────────────────▶   │
  │ ◀──── final: "The castle stood"   │
  │                                    │
```

**Requires:** WebSocket endpoint on STT service (`/v1/audio/transcriptions/ws`)
**Latency:** ~200-500ms for partial, ~500ms-1s for final

### 4.2 Option B: VAD + Chunked HTTP (Works with Current Whisper)

```
Client                          STT Service (HTTP POST)
  │                                    │
  │ VAD: speech detected               │
  │ ... recording ...                  │
  │ VAD: silence detected              │
  │                                    │
  │ ──── POST full audio (1-5s) ──▶   │
  │ ◀──── {"text": "The castle..."} ──│
  │                                    │
```

**Requires:** Nothing new — current `/v1/audio/transcriptions` works
**Latency:** Recording time + STT processing (1-17s depending on model/length)
**Optimization:** Use smaller Whisper model (tiny/base) for faster transcription

### 4.3 Option C: Browser STT + Server STT Hybrid (Recommended MVP)

```
Browser Web Speech API          Server Whisper (background)
  │                                    │
  │ ◀── instant partial ──            │
  │ ◀── instant final ────            │ (used for real-time display + send)
  │                                    │
  │ ──── same audio (async) ──────▶   │
  │                         ◀────── higher-accuracy transcript
  │                                    │ (used for history correction)
```

**Best of both worlds:**
- Browser STT for instant response (drive the conversation loop)
- Server Whisper runs in background for higher accuracy transcription
- Correct the chat history after Whisper returns (if different from browser)

---

## 5. Sentence Buffer Algorithm

### 5.1 Core Logic

```typescript
class SentenceBuffer {
  private buffer = '';
  private onSentence: (sentence: string) => void;
  
  // Sentence-ending patterns
  private BOUNDARIES = /([.!?。！？\n][\s"'」）)]*)/;
  private MIN_LENGTH = 10; // Avoid fragments like "Hi."
  
  addToken(token: string) {
    this.buffer += token;
    this.tryFlush();
  }
  
  private tryFlush() {
    const match = this.buffer.match(this.BOUNDARIES);
    if (!match) return;
    
    const boundaryIndex = match.index! + match[0].length;
    const sentence = this.buffer.slice(0, boundaryIndex).trim();
    this.buffer = this.buffer.slice(boundaryIndex);
    
    if (sentence.length >= this.MIN_LENGTH) {
      this.onSentence(sentence);
    } else {
      // Too short — keep accumulating
      this.buffer = sentence + this.buffer;
    }
  }
  
  flush() {
    // Called when LLM stream ends — send remaining text
    const remaining = this.buffer.trim();
    if (remaining.length > 0) {
      this.onSentence(remaining);
    }
    this.buffer = '';
  }
}
```

### 5.2 Edge Cases

| Case | Handling |
|------|----------|
| Very long sentence (>500 chars, no boundary) | Force-split at nearest comma or space after 300 chars |
| Code blocks or lists | Don't split inside ``` fences or numbered lists |
| Quoted speech ("Hello," she said.) | Treat `."` `!"` `?"` as boundaries, not `"` alone |
| Ellipsis (...) | Not a boundary — keep accumulating |
| Abbreviations (Mr. Dr. etc.) | Heuristic: skip if followed by uppercase letter |
| Multi-language (CJK) | 。！？ are boundaries. CJK text without punctuation: split at ~50 chars |

---

## 6. TTS Queue System

### 6.1 Architecture

```
                    ┌─────────────────────┐
 Sentence 1 ──────▶│                     │──────▶ AudioContext
 Sentence 2 ──────▶│   TTS Queue         │       schedule at
 Sentence 3 ──────▶│   (FIFO + prefetch) │       end of prev
                    │                     │
                    └─────────────────────┘
```

### 6.2 Prefetch Strategy

```
Queue State:
  [Sentence 1] → TTS requested → audio received → PLAYING
  [Sentence 2] → TTS requested → audio received → READY (prefetched)
  [Sentence 3] → TTS requested → waiting...     → PENDING
  [Sentence 4] → not yet received from LLM      → EMPTY

Prefetch depth: 2 sentences ahead
  - While Sentence 1 plays, Sentences 2 and 3 are being synthesized
  - When Sentence 1 ends, Sentence 2 starts instantly (no gap)
```

### 6.3 AudioContext Scheduling

```typescript
class TTSPlaybackQueue {
  private audioCtx: AudioContext;
  private nextStartTime: number;
  private sources: AudioBufferSourceNode[] = [];
  
  async enqueue(audioData: ArrayBuffer) {
    const buffer = await this.audioCtx.decodeAudioData(audioData);
    const source = this.audioCtx.createBufferSource();
    source.buffer = buffer;
    source.connect(this.audioCtx.destination);
    
    // Schedule at end of previous audio (gapless playback)
    const startTime = Math.max(this.nextStartTime, this.audioCtx.currentTime);
    source.start(startTime);
    this.nextStartTime = startTime + buffer.duration;
    
    this.sources.push(source);
  }
  
  cancelAll() {
    for (const source of this.sources) {
      try { source.stop(); } catch {}
    }
    this.sources = [];
    this.nextStartTime = this.audioCtx.currentTime;
  }
}
```

---

## 7. Latency Budget

### 7.1 Target: <1.5s to first audio

```
Component               Target      Current     Notes
─────────────────────────────────────────────────────────────
VAD silence detection   200ms       1500ms      Reduce threshold
STT (browser)           100ms       instant     Web Speech API
STT (Whisper)           1-3s        17s         Use tiny/base model or streaming
LLM first token         300-500ms   300ms       Already fast (SSE)
Sentence buffer fill    200-500ms   N/A         First sentence ~5-15 tokens
TTS first sentence      200-300ms   228ms       Kokoro is fast!
Audio decode + play     50ms        50ms        AudioContext
─────────────────────────────────────────────────────────────
TOTAL (browser STT)     ~0.9s       N/A         ✅ Under 1s
TOTAL (Whisper STT)     ~2.0s       17s+        Need streaming Whisper
```

### 7.2 What Dominates Latency

```
Current (cascading):     STT(17s) + LLM(2s) + TTS(0.2s) = 19.2s
                         ▲▲▲▲▲▲▲▲ STT is 89% of latency

Tier 2 (browser STT):   VAD(0.2s) + STT(0.1s) + LLM_first(0.3s) + Buffer(0.3s) + TTS(0.2s) = 1.1s
                                                  ▲▲▲▲▲▲ LLM is now the bottleneck

Tier 2 (Whisper stream): VAD(0.2s) + STT(0.5s) + LLM_first(0.3s) + Buffer(0.3s) + TTS(0.2s) = 1.5s
```

---

## 8. Implementation Tasks

### Phase A: Sentence-Level TTS Pipelining (Biggest Win)

| Task | Scope | Deps |
|------|-------|------|
| **RTV-01** | `SentenceBuffer` class — accumulates LLM tokens, emits on sentence boundary | None |
| **RTV-02** | `TTSPlaybackQueue` — FIFO audio queue with gapless AudioContext scheduling | None |
| **RTV-03** | Wire into `useVoiceMode` — tap SSE token stream, feed through SentenceBuffer → TTS → Queue | RTV-01, RTV-02 |
| **RTV-04** | Barge-in detection — VAD during playback, cancel on speech | RTV-03 |

### Phase B: Optimized STT

| Task | Scope | Deps |
|------|-------|------|
| **RTV-05** | Reduce VAD silence threshold to 500ms (configurable) | None |
| **RTV-06** | Hybrid STT — browser for speed, Whisper for accuracy correction | None |
| **RTV-07** | WebSocket streaming STT endpoint in Whisper service (future, separate repo) | External |

### Phase C: Advanced

| Task | Scope | Deps |
|------|-------|------|
| **RTV-08** | TTS prefetch — start synthesizing sentence N+1 while N plays | RTV-02 |
| **RTV-09** | Adaptive silence threshold — shorter when conversation is rapid, longer for thinking | RTV-05 |
| **RTV-10** | Conversation context — include last N turns in LLM prompt for continuity | RTV-03 |

### Suggested Build Order

```
1. RTV-01 + RTV-02 (parallel — pure logic, no integration)
2. RTV-03 (wire into voice mode — biggest latency improvement)
3. RTV-04 (barge-in — UX polish)
4. RTV-05 (quick win — reduce silence threshold)
5. RTV-06 (hybrid STT)
6. RTV-08 (prefetch — remove gaps between sentences)
```

**Phase A alone (RTV-01..04) should bring latency from 5-20s down to ~1-1.5s** when using browser STT + Kokoro TTS.

---

## 9. Data Flow Diagram

### 9.1 Current (Cascading)

```
Time ─────────────────────────────────────────────────────────▶

User:    [====speaking====]
STT:                        [==========transcribing==========]
LLM:                                                           [===streaming===]
TTS:                                                                             [==generating==]
Audio:                                                                                            [==playing==]

Total: ████████████████████████████████████████████████████████████████████████████████████████████ 19s
```

### 9.2 Target (Streaming Pipeline)

```
Time ───────────────────────────────────────▶

User:    [====speaking====]
STT:     [===partial===][final]
LLM:                         [tok][tok][.][tok][tok][!][tok][.]
Buffer:                      [accumulate ][S1][accum][S2][S3]
TTS:                                      [S1]      [S2][S3]
Audio:                                     [▶S1]     [▶S2][▶S3]

Total: ████████████████████████████████████ 1.1s to first audio
```

---

## 10. References

### Industry Architecture
- [Real-Time vs Turn-Based Voice Agent Architecture](https://softcery.com/lab/ai-voice-agents-real-time-vs-turn-based-tts-stt-architecture)
- [Voice AI Pipeline: STT, LLM, TTS and the 300ms Budget](https://www.channel.tel/blog/voice-ai-pipeline-stt-tts-latency-budget)
- [Voice Agent Architecture: STT, LLM, TTS Pipelines (LiveKit)](https://livekit.com/blog/voice-agent-architecture-stt-llm-tts-pipelines-explained)
- [Sequential Pipeline Architecture (LiveKit)](https://livekit.com/blog/sequential-pipeline-architecture-voice-agents)

### Frameworks
- [Pipecat — Open Source Voice Agent Framework](https://github.com/pipecat-ai/pipecat)
- [One-Second Voice-to-Voice Latency with Pipecat](https://modal.com/blog/low-latency-voice-bot)

### STT Streaming
- [Whisper Streaming (GitHub)](https://github.com/ufal/whisper_streaming)
- [whisper.cpp (GitHub)](https://github.com/ggml-org/whisper.cpp)

### Research
- [Low-Latency End-to-End Voice Agents (arXiv 2025)](https://arxiv.org/html/2508.04721v1)
- [Building Enterprise Realtime Voice Agents (arXiv 2026)](https://arxiv.org/html/2603.05413v1)

### Cloud APIs
- [OpenAI Realtime API](https://developers.openai.com/api/docs/guides/realtime)
- [Best TTS APIs for Real-Time Voice Agents (2026 Benchmarks)](https://inworld.ai/resources/best-voice-ai-tts-apis-for-real-time-voice-agents-2026-benchmarks)

---

*Last updated: 2026-04-11 — LoreWeave session 31*
