/**
 * TTSPlaybackQueue — FIFO audio playback with gapless AudioContext scheduling.
 * Plays audio chunks sequentially with a configurable silence pad between them.
 *
 * Design ref: REALTIME_VOICE_PIPELINE.md §6
 */

export interface TTSPlaybackQueueOptions {
  /** Silence padding between sentences in ms (default 80) */
  sentencePadMs?: number;
  /** Called when all enqueued audio has finished playing and close() was called */
  onAllPlayed?: () => void;
  /** Called when a chunk starts playing (index, total queued) */
  onChunkStart?: (index: number) => void;
}

export class TTSPlaybackQueue {
  private audioCtx: AudioContext | null = null;
  private nextStartTime = 0;
  private sources: AudioBufferSourceNode[] = [];
  private pendingCount = 0;
  private closed = false;
  private chunkIndex = 0;

  private readonly sentencePadMs: number;
  private readonly onAllPlayed?: () => void;
  private readonly onChunkStart?: (index: number) => void;

  constructor(options: TTSPlaybackQueueOptions = {}) {
    this.sentencePadMs = options.sentencePadMs ?? 80;
    this.onAllPlayed = options.onAllPlayed;
    this.onChunkStart = options.onChunkStart;
  }

  private getAudioContext(): AudioContext {
    if (!this.audioCtx || this.audioCtx.state === 'closed') {
      this.audioCtx = new AudioContext({ sampleRate: 24000 });
    }
    return this.audioCtx;
  }

  /** Enqueue audio data for playback. Schedules gaplessly after previous chunk. */
  async enqueue(audioData: ArrayBuffer): Promise<void> {
    const ctx = this.getAudioContext();

    // Resume if suspended (browser auto-suspend policy)
    if (ctx.state === 'suspended') {
      await ctx.resume();
    }

    const buffer = await ctx.decodeAudioData(audioData.slice(0)); // slice to avoid detached buffer
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);

    // Schedule at end of previous audio + silence pad
    const padSeconds = this.sentencePadMs / 1000;
    const startTime = Math.max(this.nextStartTime + padSeconds, ctx.currentTime);
    source.start(startTime);
    this.nextStartTime = startTime + buffer.duration;

    const idx = this.chunkIndex++;
    this.pendingCount++;
    this.onChunkStart?.(idx);

    source.onended = () => {
      this.pendingCount--;
      // Remove from sources list
      const i = this.sources.indexOf(source);
      if (i !== -1) this.sources.splice(i, 1);
      // Check if all done
      if (this.pendingCount === 0 && this.closed) {
        this.onAllPlayed?.();
      }
    };

    this.sources.push(source);
  }

  /** Mark that no more items will be enqueued */
  close(): void {
    this.closed = true;
    if (this.pendingCount === 0) {
      this.onAllPlayed?.();
    }
  }

  /** Stop all playback immediately and clear the queue */
  cancelAll(): void {
    for (const source of this.sources) {
      try { source.stop(); } catch { /* already stopped */ }
    }
    this.sources = [];
    this.pendingCount = 0;
    this.closed = false;
    this.chunkIndex = 0;
    if (this.audioCtx) {
      this.nextStartTime = this.audioCtx.currentTime;
    }
  }

  /** Whether audio is currently playing */
  get isPlaying(): boolean {
    return this.pendingCount > 0;
  }

  /** Clean up AudioContext */
  dispose(): void {
    this.cancelAll();
    if (this.audioCtx) {
      this.audioCtx.close().catch(() => {});
      this.audioCtx = null;
    }
  }
}
