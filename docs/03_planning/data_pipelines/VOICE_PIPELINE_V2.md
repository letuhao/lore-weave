# Voice Pipeline V2 — Architecture Document

> **Status:** Design phase — reviewed by context engineer + data engineer
> **Session:** 31 (2026-04-11)
> **Reviews:** 21 issues found (2 critical, 9 high, 8 medium, 2 low), all addressed below

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

**Optional (headphone mode):** When headphones are detected via `navigator.mediaDevices.enumerateDevices()`, enable lightweight VAD during SPEAKING. No echo risk with headphones. User enables this in Voice Settings.

Promoted from P3 to P1 per reviewer recommendation.

---

## 3. Text Normalizer (Preprocessing)

### 3.1 Problem

LLM output contains markdown, code, JSON, emojis that TTS can't speak naturally:

```
Input:  "Here's a **great** example:\n```python\nprint('hello')\n```\nTry it! 🚀"
Bad TTS: "Here's a asterisk asterisk great asterisk asterisk example colon
          backtick backtick backtick python print open paren quote hello..."
```

### 3.2 Hybrid Architecture (Option C)

```
SentenceBuffer emits sentence
  → Rule-based normalizer (instant, ~0ms, handles 90% of cases)
    → Clean text? → send to TTS
    → Mild formatting? → strip and send to TTS
    → Code block / JSON / table? → skip TTS, show text only
    → Complex (formulas, mixed)? → LLM rewriter (optional, user-enabled)
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
```

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

**Signed URLs:** Generated lazily on read (not stored). The endpoint that returns messages generates short-lived signed URLs (1 hour) for each segment's `object_key`.

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

### Phase B: Text Normalizer + Barge-in (P1)

| Task | Scope |
|------|-------|
| **VP2-05** | `TextNormalizer` class — rule-based markdown/code/emoji stripping |
| **VP2-06** | Wire normalizer into pipeline between SentenceBuffer and TTS pool |
| **VP2-07** | Normalizer stats in metrics (sentences skipped, code blocks, etc.) |
| **VP2-08** | Headphone detection — enable auto barge-in when headphones connected |
| **VP2-09** | "Thinking..." indicator during PROCESSING when LLM first token > 2s |

### Phase C: Audio Persistence (P1)

| Task | Scope |
|------|-------|
| **VP2-10** | `message_audio_segments` table migration in chat-service |
| **VP2-11** | Audio upload endpoint `POST /v1/chat/.../audio-segments` (MinIO + DB) |
| **VP2-12** | Pipeline: upload TTS audio to MinIO in background (fire-and-forget, non-blocking) |
| **VP2-13** | Message API: return segments with lazily-signed URLs |
| **VP2-14** | Cleanup task: periodic delete expired segments from DB + MinIO |

### Phase D: Chat UI Audio (P1)

| Task | Scope |
|------|-------|
| **VP2-15** | Audio indicator (🔊) on assistant messages with segments |
| **VP2-16** | Audio replay player — play/pause, progress bar, per-sentence segments |
| **VP2-17** | Normalizer skip indicator in overlay ("1 code block skipped") |

### Phase E: Polish (P2)

| Task | Scope |
|------|-------|
| **VP2-18** | LLM rewriter option — "Explain code blocks with AI" in Voice Settings |
| **VP2-19** | Configurable audio retention in settings (48h default) |
| **VP2-20** | Audio download button on messages |
| **VP2-21** | Mode switch guard — disable text input during voice PROCESSING/SPEAKING |

---

## 8. Open Questions (Resolved)

| Question | Resolution |
|----------|-----------|
| WAV vs MP3? | **MP3** — consistent with book-service, 10x smaller |
| JSONB vs separate table? | **Separate `message_audio_segments` table** — cleaner queries, CASCADE delete |
| Signed URL in DB? | **No — store `object_key`, sign lazily on read** |
| Block upload before play? | **No — play from memory, upload in background** |
| Destroy/recreate VAD? | **Keep ONNX runtime alive, only stop/start audio stream** |
| Auto barge-in? | **Manual default, headphone-gated auto barge-in (P1 not P3)** |
| PAUSED state? | **Removed from state machine** — not needed with manual cancel |

---

*Created: 2026-04-11 — LoreWeave session 31*
*Reviewed by: context engineer (13 issues), data engineer (8 issues) — all addressed*
