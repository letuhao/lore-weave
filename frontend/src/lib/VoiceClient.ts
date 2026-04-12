/**
 * VoiceClient — thin client for the server-side voice pipeline.
 * POSTs audio to /voice-message, parses SSE stream, dispatches typed callbacks.
 *
 * Design ref: VOICE_PIPELINE_V2.md §6.1
 */

export interface AudioChunkEvent {
  sentenceIndex: number;
  chunkIndex: number;
  data: string; // base64-encoded MP3
  final: boolean;
}

export interface AudioSkipEvent {
  sentenceIndex: number;
  reason: string;
  text: string;
}

export interface VoiceFinishEvent {
  finishReason: string;
  usage: { promptTokens: number; completionTokens: number };
  timing: {
    responseTimeMs: number;
    timeToFirstTokenMs: number | null;
    sttMs: number;
  };
}

export interface VoiceCallbacks {
  onTranscript: (text: string, durationMs: number, audioSizeKB: number) => void;
  onTextDelta: (delta: string) => void;
  onReasoningDelta?: (delta: string) => void;
  onAudioChunk: (event: AudioChunkEvent) => void;
  onAudioSkip?: (event: AudioSkipEvent) => void;
  onFinish: (event: VoiceFinishEvent) => void;
  onVoiceData?: (messageId: string, segmentCount: number) => void;
  onError: (errorText: string) => void;
}

export interface VoiceConfig {
  stt_model_source?: string;
  stt_model_ref?: string;
  tts_model_source?: string;
  tts_model_ref?: string;
  tts_voice?: string;
}

export class VoiceClient {
  private abortController: AbortController | null = null;

  constructor(
    private apiBase: string,
    private token: string,
  ) {}

  /** Abort any in-flight voice request. */
  abort(): void {
    this.abortController?.abort();
    this.abortController = null;
  }

  /**
   * Send voice audio to the server, receive SSE stream of events.
   * Returns when the stream is complete or an error occurs.
   */
  async sendVoiceMessage(
    sessionId: string,
    audioBlob: Blob,
    voiceConfig: VoiceConfig,
    callbacks: VoiceCallbacks,
  ): Promise<void> {
    const formData = new FormData();
    const ext = audioBlob.type.includes('wav') ? 'wav' : audioBlob.type.includes('webm') ? 'webm' : 'ogg';
    formData.append('audio', audioBlob, `audio.${ext}`);
    formData.append('config', JSON.stringify(voiceConfig));

    this.abortController?.abort();
    this.abortController = new AbortController();

    let resp: Response;
    try {
      resp = await fetch(
        `${this.apiBase}/v1/chat/sessions/${sessionId}/voice-message`,
        {
          method: 'POST',
          headers: { Authorization: `Bearer ${this.token}` },
          body: formData,
          signal: this.abortController.signal,
        },
      );
    } catch (err) {
      if ((err as Error).name === 'AbortError') return; // Intentional cancel
      callbacks.onError(`Connection failed: ${(err as Error).message}`);
      return;
    }

    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      callbacks.onError(`Server error ${resp.status}: ${text.slice(0, 200)}`);
      return;
    }

    if (!resp.body) {
      callbacks.onError('No response stream');
      return;
    }

    await this._consumeStream(resp.body, callbacks);
  }

  private async _consumeStream(
    body: ReadableStream<Uint8Array>,
    callbacks: VoiceCallbacks,
  ): Promise<void> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Process complete SSE lines
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? ''; // Keep incomplete line in buffer

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6);
          if (payload === '[DONE]') return;

          try {
            const event = JSON.parse(payload);
            this._dispatch(event, callbacks);
          } catch {
            // Malformed JSON line — skip
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  }

  private _dispatch(
    event: { type: string; [key: string]: unknown },
    cb: VoiceCallbacks,
  ): void {
    switch (event.type) {
      case 'stt-transcript':
        cb.onTranscript(
          event.text as string,
          event.durationMs as number,
          event.audioSizeKB as number,
        );
        break;
      case 'text-delta':
        cb.onTextDelta(event.delta as string);
        break;
      case 'reasoning-delta':
        cb.onReasoningDelta?.(event.delta as string);
        break;
      case 'audio-chunk':
        cb.onAudioChunk(event as unknown as AudioChunkEvent);
        break;
      case 'audio-skip':
        cb.onAudioSkip?.(event as unknown as AudioSkipEvent);
        break;
      case 'voice-data':
        cb.onVoiceData?.(event.messageId as string, event.segmentCount as number);
        break;
      case 'finish-message':
        cb.onFinish(event as unknown as VoiceFinishEvent);
        break;
      case 'error':
        cb.onError(event.errorText as string);
        break;
    }
  }
}
