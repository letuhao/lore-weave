/**
 * TTSPlaybackQueue — FIFO audio playback with gapless AudioContext scheduling.
 * Plays audio chunks sequentially with a configurable silence pad between them.
 *
 * Design ref: REALTIME_VOICE_PIPELINE.md §6
 */

export interface TTSPlaybackQueueOptions {
  /** Silence padding between sentences in ms (default 80, 0 for first chunk) */
  sentencePadMs?: number;
  /** Pre-created AudioContext (resumed in user gesture for iOS compatibility) */
  audioContext?: AudioContext;
  /** Called when all enqueued audio has finished playing and close() was called */
  onAllPlayed?: () => void;
  /** Called when a chunk starts playing (index) */
  onChunkStart?: (index: number) => void;
  /** Called when a chunk finishes playing (index) — used for barge-in cooldown */
  onChunkEnd?: (index: number) => void;
  /** Called when a chunk fails to decode/play (index, error) */
  onChunkError?: (index: number, error: Error) => void;
}

export class TTSPlaybackQueue {
  private audioCtx: AudioContext | null = null;
  private ownsAudioCtx: boolean; // true if we created it, false if shared
  private nextStartTime = 0;
  private sources: AudioBufferSourceNode[] = [];
  private pendingCount = 0;
  private closed = false;
  private allPlayedFired = false; // PQ-07: prevent double-fire
  private chunkIndex = 0;
  private generation = 0; // PQ-02: cancel-safety for in-flight decodes
  private isFirstChunk = true; // PQ-05: no pad on first chunk

  private readonly sentencePadMs: number;
  private readonly onAllPlayed?: () => void;
  private readonly onChunkStart?: (index: number) => void;
  private readonly onChunkEnd?: (index: number) => void;
  private readonly onChunkError?: (index: number, error: Error) => void;

  constructor(options: TTSPlaybackQueueOptions = {}) {
    this.sentencePadMs = options.sentencePadMs ?? 80;
    this.audioCtx = options.audioContext ?? null;
    this.ownsAudioCtx = !options.audioContext; // Only close if we created it
    this.onAllPlayed = options.onAllPlayed;
    this.onChunkStart = options.onChunkStart;
    this.onChunkEnd = options.onChunkEnd;
    this.onChunkError = options.onChunkError;
  }

  private getAudioContext(): AudioContext {
    if (!this.audioCtx || this.audioCtx.state === 'closed') {
      this.audioCtx = new AudioContext({ sampleRate: 24000 });
    }
    return this.audioCtx;
  }

  /** Enqueue audio data for playback. Schedules gaplessly after previous chunk. */
  async enqueue(audioData: ArrayBuffer): Promise<void> {
    const gen = this.generation; // PQ-02: capture generation
    const idx = this.chunkIndex++;
    this.pendingCount++; // Increment BEFORE async decode to prevent premature onAllPlayed
    const ctx = this.getAudioContext();

    // Resume if suspended (browser auto-suspend policy)
    try {
      if (ctx.state === 'suspended') {
        console.log('[TTSQueue] AudioContext suspended — attempting resume...');
        await ctx.resume();
        console.log('[TTSQueue] AudioContext resumed:', ctx.state);
      }
    } catch (e) {
      console.error('[TTSQueue] AudioContext resume failed:', (e as Error).message);
    }

    // PQ-02: bail if cancelled during resume
    if (gen !== this.generation) { this.pendingCount--; this.checkAllPlayed(); return; }

    let buffer: AudioBuffer;
    try {
      buffer = await ctx.decodeAudioData(audioData.slice(0)); // PQ-03: try/catch
    } catch (err) {
      console.error(`[TTSQueue] Decode failed for chunk ${idx}:`, (err as Error).message);
      this.pendingCount--;
      this.onChunkError?.(idx, err as Error);
      this.checkAllPlayed();
      return;
    }

    // PQ-02: bail if cancelled during decode
    if (gen !== this.generation) { this.pendingCount--; this.checkAllPlayed(); return; }

    console.log(`[TTSQueue] Decoded chunk ${idx}: ${buffer.duration.toFixed(1)}s, ctx.state=${ctx.state}`);

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);

    // PQ-05: no pad on first chunk of a sequence
    const padSeconds = this.isFirstChunk ? 0 : this.sentencePadMs / 1000;
    this.isFirstChunk = false;

    const startTime = Math.max(this.nextStartTime + padSeconds, ctx.currentTime);
    source.start(startTime);
    this.nextStartTime = startTime + buffer.duration;

    this.onChunkStart?.(idx);

    source.onended = () => {
      // PQ-01: only decrement if this source belongs to current generation
      if (gen !== this.generation) return;
      this.pendingCount--;
      const i = this.sources.indexOf(source);
      if (i !== -1) this.sources.splice(i, 1);
      this.onChunkEnd?.(idx);
      this.checkAllPlayed();
    };

    this.sources.push(source);
  }

  /** Enqueue a base64-encoded audio chunk (from SSE voice pipeline). */
  async enqueueBase64(base64Data: string): Promise<void> {
    if (!base64Data) return;
    const binary = Uint8Array.from(atob(base64Data), (c) => c.charCodeAt(0));
    await this.enqueue(binary.buffer);
  }

  /** Mark that no more items will be enqueued */
  close(): void {
    this.closed = true;
    this.checkAllPlayed();
  }

  /** Stop all playback immediately and clear the queue */
  cancelAll(): void {
    this.generation++; // PQ-01 + PQ-02: invalidate in-flight decodes and stale onended
    for (const source of this.sources) {
      source.onended = null; // PQ-01: prevent stale onended from decrementing
      try { source.stop(); } catch { /* already stopped */ }
    }
    this.sources = [];
    this.pendingCount = 0;
    this.closed = false;
    this.allPlayedFired = false; // PQ-07: reset guard
    this.chunkIndex = 0;
    this.isFirstChunk = true; // PQ-05: reset for next sequence
    this.nextStartTime = 0; // PQ-05: let Math.max pick ctx.currentTime
  }

  /** Whether audio is currently playing */
  get isPlaying(): boolean {
    return this.pendingCount > 0;
  }

  /** Clean up AudioContext (only closes if we created it — shared contexts are owned by caller) */
  dispose(): void {
    this.cancelAll();
    if (this.audioCtx && this.ownsAudioCtx) {
      this.audioCtx.close().catch(() => {});
    }
    this.audioCtx = null;
  }

  // PQ-07: centralized check prevents double-fire
  private checkAllPlayed(): void {
    if (this.pendingCount === 0 && this.closed && !this.allPlayedFired) {
      this.allPlayedFired = true;
      this.onAllPlayed?.();
    }
  }
}
