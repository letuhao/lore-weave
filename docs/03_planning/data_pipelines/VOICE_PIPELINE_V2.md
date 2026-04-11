# Voice Pipeline V2 — Architecture Document

> **Status:** Design phase — 5 review rounds (context, data, UX, security, performance)
> **Session:** 31 (2026-04-11)
> **Reviews:** 39 total issues found across 5 reviews, all addressed below

---

## 1. Problems with V1

### 1.1 State Management is Broken

No strict phase locking. Multiple subsystems race:
- TTS playing → VAD captures speaker output → STT sends garbage → infinite loop
- LLM finishes fast → pipeline generation changes → TTS audio discarded
- React effects used for control flow → async batching causes double-sends

### 1.2 No Audio Persistence

TTS audio held in memory, discarded on any state change. No replay.

### 1.3 No Text Preprocessing

Raw LLM output (markdown, code blocks, JSON, emojis) sent directly to TTS.
Result: "asterisk asterisk bold asterisk asterisk" spoken aloud.

---

## 2. V2 Architecture

### 2.1 Design Principles

1. **Strict state machine** — imperative controller class, not React effects
2. **Phase locking** — SPEAKING phase has NO microphone access
3. **Audio persistence** — TTS audio stored in MinIO, replay anytime
4. **Play first, store later** — play from memory immediately, upload in background
5. **Text normalization** — clean markdown/code before TTS
6. **Error recovery** — every phase has a timeout and fallback path

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
          │    │  (keep ONNX     │                      │
          │    │   runtime alive)│                      │
          │    └────────┬────────┘                      │
          │             │ VAD: onSpeechEnd              │
          │             ▼                               │
          │    ┌─────────────────┐                      │
          │    │  TRANSCRIBING   │                      │
          │    │  VAD paused     │                      │
          │    │  (audio stream  │                      │
          │    │   stopped, ONNX │                      │
          │    │   runtime kept) │                      │
          │    └────────┬────────┘                      │
          │             │ STT returns text              │
          │             ▼                               │
          │    ┌─────────────────┐                      │
          │    │  PROCESSING     │                      │
          │    │  VAD stopped    │                      │
          │    │  LLM streaming  │                      │
          │    │  ┌────────────┐ │                      │
          │    │  │ Normalizer │ │                      │
          │    │  │ → TTS gen  │ │                      │
          │    │  └────────────┘ │                      │
          │    │  Timeout: 30s   │                      │
          │    └────────┬────────┘                      │
          │             │ First TTS audio ready         │
          │             ▼                               │
          │    ┌─────────────────┐                      │
          │    │   SPEAKING      │                      │
          │    │  VAD STOPPED    │                      │
          │    │  NO mic access  │                      │
          │    │  Playing audio  │                      │
          │    │  Queuing more   │                      │
          │    │  Upload to MinIO│                      │
          │    │  (background)   │                      │
          │    └───┬─────────┬───┘                      │
          │        │         │                          │
          │    cancel    LLM done                       │
          │    button    AND all                        │
          │        │     audio played                   │
          │        │         │                          │
          │        ▼         └──────────────────────────┘
          │  (back to LISTENING)
          │
     deactivate()
          │
          ▼
     ┌──────────┐
     │   IDLE   │
     └──────────┘
```

### 2.3 Phase Transitions (Complete)

| From | To | Trigger | Actions |
|------|------|---------|---------|
| IDLE → LISTENING | `activate()` | Init VAD (ONNX runtime + audio stream), start monitoring |
| LISTENING → TRANSCRIBING | VAD `onSpeechEnd` | Stop VAD audio stream (keep ONNX runtime), send audio to STT |
| TRANSCRIBING → PROCESSING | STT returns text (≥2 chars) | Stop VAD fully, send to LLM, start normalizer + TTS pipeline |
| TRANSCRIBING → LISTENING | STT returns empty/garbage | Resume VAD audio stream |
| TRANSCRIBING → LISTENING | STT timeout (10s) | Resume VAD, log warning |
| TRANSCRIBING → LISTENING | STT error (network/500) | Resume VAD, show error toast |
| PROCESSING → SPEAKING | First TTS audio ready to play | Start audio playback |
| PROCESSING → LISTENING | Processing timeout (30s) | Cancel LLM + TTS, resume VAD, show warning |
| PROCESSING → LISTENING | LLM error / all TTS fail | Cancel pipeline, resume VAD, show error |
| SPEAKING → LISTENING | LLM done AND all audio played | Resume VAD |
| SPEAKING → LISTENING | User presses cancel button (Space key) | Stop playback, cancel pending TTS, resume VAD |
| SPEAKING → LISTENING | Headphone barge-in detected (if enabled) | Stop playback, resume VAD |
| ANY → IDLE | `deactivate()` | Destroy everything |
| ANY → IDLE | Session change | Destroy everything |

**Key rule for SPEAKING exit:** SPEAKING only transitions to LISTENING when BOTH conditions are met:
1. LLM stream is complete (no more sentences coming)
2. ALL enqueued audio has finished playing

If LLM is done but TTS is still generating/playing → stay in SPEAKING.
If TTS is done but LLM is still streaming → stay in SPEAKING (more sentences may come).

### 2.4 Barge-in Strategy

**Default:** Manual only — cancel button + Space key. No microphone during SPEAKING.

**Headphone auto-detection (P1):** When headphones are detected via `navigator.mediaDevices.enumerateDevices()`, enable lightweight VAD during SPEAKING. No echo risk with headphones.

**UX:** Don't bury in settings — surface as an inline prompt on first headphone detection:
> "🎧 Headphones detected. Enable hands-free interruption?"
> [Enable] [Not now]

This avoids the frustration of manual-only barge-in on mobile (where pressing Space is impossible) while preventing echo issues on speakers.

---

## 3. Text Normalizer (Preprocessing)

### 3.1 Problem

LLM output contains markdown, code, JSON, emojis that TTS can't speak naturally:

```
Input:  "Here's a **great** example:\n```python\nprint('hello')\n```\nTry it! 🚀"
Bad TTS: "Here's a asterisk asterisk great asterisk asterisk example colon
          backtick backtick backtick python print open paren quote hello..."
```

### 3.2 Layer 0: Voice Mode System Prompt (Proactive)

When voice mode activates, inject a system prompt that tells the LLM to respond in conversational speech style. This prevents most formatting at the source — the model simply won't generate markdown/code/tables when it knows the output goes to TTS.

```
Injected when voice mode is active:

"You are in a voice conversation. The user is speaking to you and will hear
your response as speech via text-to-speech.

Rules for voice mode responses:
- Respond in natural, conversational speech — as if talking to a friend
- Do NOT use markdown formatting (no **, *, #, ```, etc.)
- Do NOT output code blocks — describe what code does instead
- Do NOT use bullet points or numbered lists — use flowing sentences
- Do NOT use tables or JSON — describe data verbally
- Keep responses concise (2-4 sentences for simple questions)
- Use natural speech patterns: contractions, filler words are OK
- If the user asks about code, explain the concept verbally
- Pronounce abbreviations: 'API' as 'A P I', 'URL' as 'U R L'"
```

**Implementation (server-side — security requirement):**
The voice system prompt is injected **server-side in chat-service**, NOT client-side. When the frontend sends a message with `input_method: 'voice'`, the chat-service prepends the voice system prompt to the LLM request. This prevents prompt injection — users cannot override the system prompt via modified client requests.

The frontend sets `input_method: 'voice'` on the message payload. The chat-service checks this flag and injects the prompt. Stored conversation history does NOT include the voice prompt — it's transient per-request.

**Security:** The voice transcript is treated as **untrusted user input** — it goes through the same sanitization as typed messages. The system prompt cannot be overridden by the transcript content because it's injected server-side before the user message.

**Effectiveness:** This alone eliminates ~80% of formatting issues at zero cost. The rule-based normalizer (Layer 1) catches the remaining edge cases.

### 3.3 Hybrid Architecture (Option C — 3 Layers)

```
Layer 0: Voice system prompt → LLM generates speech-friendly text (~80% clean)
Layer 1: Rule-based normalizer → strips remaining formatting (~19% caught)
Layer 2: LLM rewriter (optional) → handles complex cases (~1%, user-enabled)

Pipeline:
  voice mode active → inject system prompt → LLM generates
  → SentenceBuffer emits sentence
    → TextNormalizer.normalize(sentence)      [Layer 1, ~0ms]
      → Clean? → TTS
      → Code/JSON? → skip TTS
      → Complex + rewriter enabled? → LLM rewriter [Layer 2, +500ms]
```

### 3.3 Rule-Based Normalizer (Default)

```typescript
class TextNormalizer {
  normalize(text: string): { speakable: string; skipped: boolean } {
    let result = text;

    // 1. Strip markdown formatting
    result = result.replace(/\*\*(.+?)\*\*/g, '$1');     // **bold** → bold
    result = result.replace(/\*(.+?)\*/g, '$1');          // *italic* → italic
    result = result.replace(/~~(.+?)~~/g, '$1');          // ~~strike~~ → strike
    result = result.replace(/`([^`]+)`/g, '$1');          // `code` → code
    result = result.replace(/#{1,6}\s*/g, '');             // ## heading → heading
    result = result.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1'); // [text](url) → text

    // 2. Handle code blocks — skip entirely
    if (/```[\s\S]*```/.test(text)) {
      return { speakable: '', skipped: true };
    }

    // 3. Handle JSON/tables — skip
    if (text.trim().startsWith('{') || text.trim().startsWith('|')) {
      return { speakable: '', skipped: true };
    }

    // 4. Convert common emojis to words (top 20)
    const emojiMap: Record<string, string> = {
      '😊': '', '🤖': '', '✨': '', '🚀': '',
      '👋': '', '❤️': '', '🎉': '', '💡': '',
      '⚡': '', '🔥': '', '✅': '', '❌': '',
    };
    for (const [emoji, word] of Object.entries(emojiMap)) {
      result = result.replaceAll(emoji, word);
    }

    // 5. Clean up remaining special chars
    result = result.replace(/[*_~`#>|]/g, '');
    result = result.replace(/\s{2,}/g, ' ').trim();

    // 6. Skip if nothing speakable remains
    if (result.length < 2) {
      return { speakable: '', skipped: true };
    }

    return { speakable: result, skipped: false };
  }
}
```

### 3.4 LLM Rewriter (Optional, User-Enabled)

For users who want code blocks and complex content explained:

```
System: "Rewrite this text for natural speech. Remove all formatting.
         For code blocks, briefly describe what the code does instead of
         reading it literally. Keep it concise."
User: [raw sentence]
→ LLM: [natural speech version]
```

- Enabled via Voice Settings toggle: "Explain code blocks with AI"
- Adds 500ms-2s latency + extra LLM cost per sentence
- Only used for sentences that the rule-based normalizer flags as "complex"
- Uses a small/fast model (not the main conversation model)

### 3.5 Pipeline Integration

```
LLM token → SentenceBuffer → sentence emitted
  → TextNormalizer.normalize(sentence)
    → skipped? → don't send to TTS (show text only in overlay)
    → speakable? → send normalized text to TTS pool
    → complex + LLM rewriter enabled? → send to rewriter LLM → then TTS
```

---

## 4. Audio Persistence Architecture

### 4.1 Flow (Play First, Store Later)

```
TTS returns audio ArrayBuffer
  → IMMEDIATELY enqueue for playback (from memory, zero storage latency)
  → CONCURRENTLY upload to MinIO in background
    → MinIO returns object_key
    → Patch message: add to audio_segments table
    → Replay now available via signed URL
```

**Critical:** Playback is NOT blocked by upload. User hears audio instantly.

### 4.2 Storage

```
Bucket: lw-chat (existing, separate from loreweave-media)
Path:   voice-audio/{session_id}/{message_id}/{index}_{timestamp}.mp3
Format: MP3 (consistent with book-service TTS, 10x smaller than WAV)

Lifecycle: MinIO prefix-based TTL, 48h default
Encryption: SSE-S3 at rest (MinIO server-side encryption)
```

**Security requirements:**
- SSE-S3 encryption at rest for all voice audio (voice is biometric data)
- User consent notice on first voice mode activation ("Audio will be stored for 48h for replay")
- GDPR erasure endpoint: `DELETE /v1/chat/voice-data` — deletes all user's voice audio + DB references
- `input_method: 'voice'` flag excluded from exports and public/shared views

### 4.3 Database Schema

**Separate table** (not JSONB on chat_messages):

```sql
CREATE TABLE message_audio_segments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id UUID NOT NULL REFERENCES chat_messages(message_id) ON DELETE CASCADE,
  session_id UUID NOT NULL,
  segment_index INT NOT NULL,
  object_key TEXT NOT NULL,         -- MinIO key (NOT a signed URL)
  sentence_text TEXT NOT NULL,
  duration_s REAL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_mas_message ON message_audio_segments(message_id);
CREATE INDEX idx_mas_cleanup ON message_audio_segments(created_at);
```

**On DELETE CASCADE:** When a message is deleted, audio segments are automatically cleaned.

**Signed URLs:** Generated lazily on read (not stored). Signed per-playback request (not embedded in message list). Expiry: 15 minutes (not 1 hour — reduces leak window). Scoped: URLs are generated only for the authenticated user's own messages.

### 4.4 Audio Upload Endpoint

```
POST /v1/chat/sessions/{session_id}/messages/{message_id}/audio-segments
Content-Type: multipart/form-data
Authorization: Bearer {jwt}

Fields:
  file: MP3 audio blob
  index: segment index (0, 1, 2...)
  text: sentence text
  duration_s: audio duration in seconds

Response:
  { "id": "...", "object_key": "voice-audio/..." }
```

### 4.5 Cleanup

**Two-layer cleanup:**

1. **MinIO lifecycle policy:** Prefix `voice-audio/` → expire after 48h (safety net)
2. **DB cleanup task:** Periodic (every 4 hours) in chat-service:

```python
# ~20 lines — no separate worker needed
async def cleanup_expired_audio(pool, minio):
    rows = await pool.fetch("""
        DELETE FROM message_audio_segments
        WHERE created_at < now() - interval '48 hours'
        RETURNING object_key
    """)
    for row in rows:
        try:
            minio.remove_object('lw-chat', row['object_key'])
        except:
            pass  # MinIO lifecycle will catch it
```

---

## 5. Frontend: Audio on Messages

### 5.1 Audio Indicator

```
┌──────────────────────────────────────────────┐
│  AI message:                                 │
│                                              │
│  Hello! How can I help you today?            │
│                                              │
│  🔊 ▶ ━━━━━━━━━━━━ 0:03 / 0:05             │
│     [S1 ▶] [S2 ▶] [S3 ▶]                    │
│                                              │
└──────────────────────────────────────────────┘
```

- 🔊 icon appears on messages with audio segments
- Play/pause button — plays all segments sequentially
- Per-segment buttons — click to play a specific sentence
- Progress bar — shows playback position
- Works in both chat mode and voice mode

### 5.2 Voice Mode Overlay

```
┌─────────────────────────────────────────┐
│  🎤 Voice Mode                    ⚙️ ✕ │
│                                         │
│  [waveform / status indicator]          │
│                                         │
│  You: "How are you today?"              │
│                                         │
│  AI: "I'm doing great, thank you!"     │
│       ▶ ━━━━━━━ 0:02 / 0:03           │
│       [code block skipped]              │  ← normalizer skipped
│       "Let me know if you need help."   │
│       ▶ ━━━━━━━ 0:02 / 0:04           │
│                                         │
│  STT    96KB → 342ms                    │
│  LLM    45 tokens in 1.2s              │
│  TTS    3 sentences · 289KB · avg 2.1s  │
│  Skip   1 code block                    │  ← normalizer stats
│                                         │
│  [Cancel (Space)]  [Exit Voice Mode]    │
└─────────────────────────────────────────┘
```

---

## 6. VoicePipelineController

### 6.1 Imperative, Not React Effects

```typescript
class VoicePipelineController {
  private phase: VoicePhase = 'idle';
  private vad: MicVAD | null = null;
  private vadOnnxRuntime: any = null;     // Keep alive across phases
  private normalizer = new TextNormalizer();
  private sentenceBuffer: SentenceBuffer | null = null;
  private ttsPool: TTSConcurrencyPool | null = null;
  private ttsQueue: TTSPlaybackQueue | null = null;
  private processingTimeout: ReturnType<typeof setTimeout> | null = null;
  private sttTimeout: ReturnType<typeof setTimeout> | null = null;
  private llmComplete = false;
  private allAudioPlayed = false;

  // React state setters (UI updates only)
  private setPhase: (phase: VoicePhase) => void;

  /** Strict phase transition with validation */
  private transition(to: VoicePhase): boolean {
    const allowed: Record<string, string[]> = {
      idle: ['listening'],
      listening: ['transcribing', 'idle'],
      transcribing: ['processing', 'listening', 'idle'],
      processing: ['speaking', 'listening', 'idle'],
      speaking: ['listening', 'idle'],
    };
    if (!allowed[this.phase]?.includes(to)) {
      console.warn(`[Pipeline] Invalid: ${this.phase} → ${to}`);
      return false;
    }
    console.log(`[Pipeline] ${this.phase} → ${to}`);
    const prev = this.phase;
    this.phase = to;
    this.setPhase(to);
    this.onExit(prev);
    this.onEnter(to);
    return true;
  }

  private onExit(phase: VoicePhase) {
    if (phase === 'processing') {
      this.clearTimeout(this.processingTimeout);
    }
    if (phase === 'transcribing') {
      this.clearTimeout(this.sttTimeout);
    }
  }

  private onEnter(phase: VoicePhase) {
    switch (phase) {
      case 'listening':
        this.llmComplete = false;
        this.allAudioPlayed = false;
        this.startVADAudioStream();
        break;
      case 'transcribing':
        this.stopVADAudioStream();  // Keep ONNX runtime, stop mic
        this.sttTimeout = setTimeout(() => {
          console.warn('[Pipeline] STT timeout');
          this.transition('listening');
        }, 10_000);
        break;
      case 'processing':
        this.stopVADFully();  // No mic during LLM+TTS
        this.startPipeline();
        this.processingTimeout = setTimeout(() => {
          console.warn('[Pipeline] Processing timeout (30s)');
          this.cancelPipeline();
          this.transition('listening');
        }, 30_000);
        break;
      case 'speaking':
        // No mic access — no VAD, no STT
        break;
      case 'idle':
        this.destroyEverything();
        break;
    }
  }

  /** SPEAKING exit condition — both must be true */
  private checkSpeakingComplete() {
    if (this.phase !== 'speaking') return;
    if (this.llmComplete && this.allAudioPlayed) {
      this.transition('listening');
    }
  }

  onLLMStreamComplete() {
    this.llmComplete = true;
    this.sentenceBuffer?.markStreamComplete();
    this.ttsQueue?.close();
    this.checkSpeakingComplete();
  }

  onAllAudioPlayed() {
    this.allAudioPlayed = true;
    this.checkSpeakingComplete();
  }

  /** VAD lifecycle — keep ONNX runtime alive, only manage audio stream */
  private async startVADAudioStream() {
    // Reuse existing ONNX runtime if available (avoids 300-800ms cold start)
    if (this.vad) {
      this.vad.start();
    } else {
      const { MicVAD } = await import('@ricky0123/vad-web');
      this.vad = await MicVAD.new({
        onSpeechEnd: (audio) => this.onSpeechEnd(audio),
        onSpeechStart: () => this.onSpeechStart(),
      });
      this.vad.start();
    }
  }

  private stopVADAudioStream() {
    this.vad?.pause();  // Stop mic but keep ONNX runtime
  }

  private stopVADFully() {
    this.vad?.pause();
    // Keep this.vad instance for reuse — don't destroy
  }

  private destroyEverything() {
    this.vad?.destroy();
    this.vad = null;
    this.cancelPipeline();
  }
}
```

### 6.2 Key Difference: SPEAKING Exit

V1 bug: SPEAKING exits when `onAllPlayed` fires, even if LLM is still streaming.

V2 fix: SPEAKING only exits when `llmComplete && allAudioPlayed`:

```
Timeline:
  LLM streams:     [tok][tok][.][tok][tok][!][tok][.]
  TTS:                        [S1 gen]     [S2 gen]  [S3 gen]
  Audio:                       [▶ S1]       [▶ S2]    [▶ S3]
  llmComplete:                                              ✓ (after last token)
  allAudioPlayed:                                                  ✓ (after S3 plays)
  → SPEAKING exits:                                                ✓ (both true)
```

---

## 7. Implementation Tasks

### Phase A: Fix Pipeline (P0)

| Task | Scope |
|------|-------|
| **VP2-01** | `VoicePipelineController` class — strict state machine with transition validation, timeout guards, error recovery |
| **VP2-02** | Phase locking — VAD audio stream stopped in PROCESSING/SPEAKING, ONNX runtime kept alive for fast restart |
| **VP2-03** | SPEAKING exit condition — requires BOTH `llmComplete` AND `allAudioPlayed` |
| **VP2-04** | Remove BargeInDetector — manual cancel button only (Space key) |

### Phase B: Text Preprocessing + Barge-in (P1)

| Task | Scope |
|------|-------|
| **VP2-05** | Voice mode system prompt injection — prepend speech-style instructions to LLM request when voice mode is active (Layer 0) |
| **VP2-06** | `TextNormalizer` class — rule-based markdown/code/emoji stripping (Layer 1) |
| **VP2-07** | Wire normalizer into pipeline between SentenceBuffer and TTS pool |
| **VP2-08** | Normalizer stats in metrics (sentences skipped, code blocks, etc.) |
| **VP2-09** | Optional LLM rewriter — "Explain code blocks with AI" setting (Layer 2) |
| **VP2-10** | Headphone detection — enable auto barge-in when headphones connected |
| **VP2-11** | "Thinking..." indicator during PROCESSING when LLM first token > 2s |

### Phase C: Audio Persistence (P1)

| Task | Scope |
|------|-------|
| **VP2-12** | `message_audio_segments` table migration in chat-service |
| **VP2-13** | Audio upload endpoint `POST /v1/chat/.../audio-segments` (MinIO + DB) |
| **VP2-14** | Pipeline: upload TTS audio to MinIO in background (fire-and-forget, non-blocking) |
| **VP2-15** | Message API: return segments with lazily-signed URLs |
| **VP2-16** | Cleanup task: periodic delete expired segments from DB + MinIO |

### Phase D: Chat UI Audio + Metrics (P1)

| Task | Scope |
|------|-------|
| **VP2-17** | Audio indicator (🔊) on assistant messages with segments |
| **VP2-18** | Audio replay player — play/pause, progress bar, per-sentence segments |
| **VP2-19** | TTS metrics on assistant messages — generation time, audio size, token count per segment. Shown as subtle tooltip or expandable detail row under audio player |
| **VP2-20** | STT metrics on user messages — transcription time, audio size, model used. Shown when message was sent via voice (not typed) |
| **VP2-21** | Flag voice-originated messages — `input_method: 'voice' | 'text'` on user messages so UI can distinguish typed vs spoken |
| **VP2-22** | Normalizer skip indicator — "Code shown above, not read aloud" (not "skipped" — less confusing). Visually connected to the code block in chat UI |

**Audio replay (simplified per UX review):**
```
┌─────────────────────────────────────────────────┐
│  AI: Hello! How can I help you today?           │
│                                                 │
│  🔊 ▶ ━━━━━━━━━━ 0:03 / 0:05                  │
│     ▸ 3 segments                        ← collapsed by default
│                                                 │
└─────────────────────────────────────────────────┘

Expanded (on click "3 segments"):
│     [S1 ▶ 1.2s] [S2 ▶ 2.1s] [S3 ▶ 0.8s]       │
```

Per-sentence buttons hidden by default — collapsed behind disclosure. Play/pause + progress bar always visible.

**Metrics (behind debug toggle per UX review):**
- Default: subtle colored dot (🟢 green = fast, 🟡 yellow = slow, 🔴 red = error)
- Debug mode (Voice Settings toggle): full metrics shown

```
Debug ON:
┌─────────────────────────────────────────────────┐
│  AI: Hello! How can I help you today?           │
│  🔊 ▶ ━━━━━━━━━━ 0:03 / 0:05          🟢      │
│  ⚡ TTS: 3 sentences · 289KB · 2.1s avg         │
│     Kokoro v1 · af_heart · 1x                   │
└─────────────────────────────────────────────────┘

│  You: How are you today?        🎤 voice  🟢    │
│  ⚡ STT: 96KB · 342ms · Whisper v3-turbo        │
└─────────────────────────────────────────────────┘

Debug OFF (default):
┌─────────────────────────────────────────────────┐
│  AI: Hello! How can I help you today?           │
│  🔊 ▶ ━━━━━━━━━━ 0:03 / 0:05          🟢      │
└─────────────────────────────────────────────────┘

│  You: How are you today?        🎤 voice  🟢    │
└─────────────────────────────────────────────────┘
```

### Phase E: Voice Assist Mode (P1)

A simpler alternative to full Voice Mode — uses the regular chat UI with voice input/output.
No overlay, no state machine, no auto-send. User has full control.

**UX note (per review):** Don't present as two separate "modes" — users don't think in modes. Instead, present as a single "Voice" toggle with a preference:
- **"Auto-send when I stop talking"** = ON → full Voice Mode (overlay, auto-send, hands-free)
- **"Auto-send when I stop talking"** = OFF → Voice Assist (chat UI, dictation, manual send)

The technical distinction (overlay vs inline, state machine vs simple) follows from this single preference.

```
┌──────────────────────────────────────────────────────┐
│  Chat UI (normal — no overlay)                       │
│                                                      │
│  ┌─ AI message ─────────────────────────────────┐   │
│  │ Hello! How can I help you today?              │   │
│  │ 🔊 ▶ ━━━━━━ 0:03                             │   │
│  └───────────────────────────────────────────────┘   │
│                                                      │
│  ┌─ Input bar ───────────────────────────────────┐   │
│  │ Tell me about Python| ← cursor (dictated)     │   │
│  │                                               │   │
│  │ 📎 🎤(ON) [Append|Replace] Think Fast    ➤   │   │
│  │      ↑                          ↑             │   │
│  │   always                   user presses       │   │
│  │   listening                enter to send      │   │
│  └───────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

**How it works:**

| Step | Voice Mode (Full) | Voice Assist (New) |
|------|------------------|--------------------|
| Activate | Opens overlay, takes over UI | Toggles mic icon ON in chat input bar |
| Listen | VAD → auto-record → auto-STT | VAD → auto-record → STT → insert text in textarea |
| Send | Auto-send on silence | User presses Enter (or edits text first) |
| AI response | Plays in overlay, blocks input | Appears in chat, auto-TTS plays alongside |
| Interrupt | Cancel button / Space | Just keep typing or click stop audio |
| Text editing | Not possible | Full editing before send |

**Key differences:**
- No state machine needed (just STT + TTS as independent services)
- No phase locking (user can type, edit, scroll while TTS plays)
- No overlay (uses normal chat UI)
- STT → inserts into textarea (append or replace mode, user toggle)
- TTS → plays automatically on AI responses (can be stopped independently)
- Much simpler to implement — reuses existing `ChatInputBar` + `useBackendSTT` + `TTSPlaybackQueue`

| Task | Scope |
|------|-------|
| **VP2-23** | Fix push-to-talk mic button — respect Voice Settings STT source (browser or AI model provider), not hardcoded to browser Web Speech API |
| **VP2-24** | Mic button visual states — 4-state design: idle (gray mic), recording (red pulse + "Recording..."), transcribing (spinner + "Transcribing..."), error (red X + brief message). Transition animations: 100-150ms fade between states |
| **VP2-25** | Voice Assist toggle in chat input bar — always-on VAD mic that inserts transcribed text into textarea |
| **VP2-26** | Append/Replace mode toggle — "Add to text" / "Replace text" (plain language labels). Auto-switches to append when textarea has existing content (prevents silent discard). Shows brief confirmation before replacing non-empty text |
| **VP2-27** | Auto-TTS on AI response — when Voice Assist is ON, auto-play TTS for new assistant messages (using sentence pipeline) |
| **VP2-28** | Audio stop button on messages — independent of voice input, user can stop TTS anytime |
| **VP2-29** | Voice Assist preferences — persist on/off state, append/replace default, auto-TTS toggle |

### Phase F: Security + Performance + Polish (P2)

| Task | Scope |
|------|-------|
| **VP2-30** | Persistent mic-active indicator in main UI chrome (not just overlay) when pipeline != IDLE |
| **VP2-31** | Voice consent notice — first-time activation: "Audio stored for 48h for replay. [Continue] [Settings]" |
| **VP2-32** | GDPR erasure endpoint: `DELETE /v1/chat/voice-data` — deletes all user's voice audio + DB refs |
| **VP2-33** | SSE-S3 encryption on lw-chat MinIO bucket for voice audio at rest |
| **VP2-34** | STT transcript sanitization — length/content checks before LLM submission (treat as untrusted) |
| **VP2-35** | TTS pool raise maxConcurrent from 2 to 3 (prevents audio gaps on 5+ sentence responses) |
| **VP2-36** | Stagger MinIO uploads by segment index (index * 50ms delay, reduces concurrent fetches) |
| **VP2-37** | Configurable audio retention in settings (48h default) |
| **VP2-38** | Audio download button on messages |
| **VP2-39** | Mode switch guard — disable text input during voice PROCESSING/SPEAKING |
| **VP2-40** | Debug toggle in Voice Settings — show/hide STT/TTS metrics on messages |

---

## 8. Open Questions (Resolved)

| Question | Resolution |
|----------|-----------|
| WAV vs MP3? | **MP3** — consistent with book-service, 10x smaller |
| JSONB vs separate table? | **Separate `message_audio_segments` table** — cleaner queries, CASCADE delete |
| Signed URL in DB? | **No — store `object_key`, sign lazily per-playback (15min expiry)** |
| Block upload before play? | **No — play from memory, upload in background** |
| Destroy/recreate VAD? | **Keep ONNX runtime alive, only stop/start audio stream** |
| Auto barge-in? | **Manual default, headphone-gated auto barge-in (P1), surface on first detection** |
| PAUSED state? | **Removed from state machine** — not needed with manual cancel |
| Voice system prompt client vs server? | **Server-side in chat-service** — prevents prompt injection |
| TTS max concurrent? | **3** (raised from 2) — prevents audio gaps on longer responses |
| Two modes vs one? | **Single "Voice" toggle** — auto-send pref determines overlay vs inline |
| Metrics visible to all? | **Debug toggle** — default shows only health dot (🟢/🟡/🔴) |
| Mic button states? | **4 states** — idle, recording, transcribing, error |
| Per-sentence buttons? | **Collapsed by default** — only play/pause + progress visible |
| "Code skipped" label? | **"Code shown above, not read aloud"** — less confusing |
| Append/Replace silent discard? | **Auto-append when textarea non-empty** — confirmation for replace |
| Voice audio encryption? | **SSE-S3 at rest** — voice is biometric data |
| GDPR erasure? | **DELETE endpoint** — removes all user voice audio + DB refs |
| STT transcript trust? | **Untrusted input** — sanitized before LLM submission |

---

## 9. Review History

| Round | Reviewer | Issues | Key Fixes |
|-------|----------|--------|-----------|
| 1 | Context Engineer | 13 | Error recovery, SPEAKING exit, VAD lifecycle |
| 2 | Data Engineer | 8 | MP3 format, separate table, lazy signing, background upload |
| 3 | UX Designer | 7 | Mode merge, 4-state mic, collapsed segments, debug metrics |
| 4 | Security Engineer | 7 | Server-side prompt, encryption, GDPR, signed URL scope |
| 5 | Performance Engineer | 4 | TTS pool=3, stagger uploads, ONNX worker verification |

Total: 39 issues found, all addressed. 40 implementation tasks across 6 phases.

---

*Created: 2026-04-11 — LoreWeave session 31*
*5 review rounds: context engineer, data engineer, UX designer, security engineer, performance engineer*
