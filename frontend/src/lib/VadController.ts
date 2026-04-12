/**
 * VadController — manages microphone + Silero VAD for voice activity detection.
 * Persistent MediaStream: acquire mic once, pause/resume VAD analysis.
 *
 * Design ref: VOICE_PIPELINE_V2.md §5.2
 */

export interface VadControllerOptions {
  onSpeechStart?: () => void;
  onSpeechEnd: (audio: Float32Array) => void;
  onError?: (error: Error) => void;
  /** Silero VAD redemptionFrames — frames × ~96ms = silence duration before speech-end. Default 8 (~768ms). */
  silenceFrames?: number;
  /** Discard audio shorter than this (ms). Default 500. */
  minSpeechDurationMs?: number;
}

export class VadController {
  private mediaStream: MediaStream | null = null;
  private vad: any | null = null; // MicVAD from @ricky0123/vad-web
  private active = false;
  private opts: VadControllerOptions;

  constructor(opts: VadControllerOptions) {
    this.opts = opts;
  }

  /** Acquire mic + initialize VAD (call once on voice mode activation). */
  async activate(): Promise<void> {
    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      this.opts.onError?.(err as Error);
      return;
    }

    const minDurationMs = this.opts.minSpeechDurationMs ?? 500;
    const silenceFrames = this.opts.silenceFrames ?? 8;

    try {
      const stream = this.mediaStream;
      const { MicVAD } = await import('@ricky0123/vad-web');
      this.vad = await MicVAD.new({
        getStream: () => Promise.resolve(stream),
        baseAssetPath: '/vad/',
        onnxWASMBasePath: '/vad/',
        redemptionMs: silenceFrames * 96,
        onSpeechStart: () => {
          if (this.active) this.opts.onSpeechStart?.();
        },
        onSpeechEnd: (audio: Float32Array) => {
          if (!this.active) return;
          // Min-duration filter — discard very short audio (noise)
          const durationMs = (audio.length / 16000) * 1000;
          if (durationMs < minDurationMs) return;
          this.opts.onSpeechEnd(audio);
        },
      });
    } catch (err) {
      this.opts.onError?.(err as Error);
      return;
    }
  }

  /** Start VAD frame analysis (instant — stream already flowing). */
  resume(): void {
    this.active = true;
    this.vad?.start();
  }

  /** Stop VAD frame analysis (stream stays alive for fast resume). */
  pause(): void {
    this.active = false;
    this.vad?.pause();
  }

  /** Full cleanup — release mic, destroy VAD. */
  deactivate(): void {
    this.active = false;
    this.vad?.destroy();
    this.vad = null;
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((t) => t.stop());
      this.mediaStream = null;
    }
  }

  get isActive(): boolean {
    return this.active;
  }
}
