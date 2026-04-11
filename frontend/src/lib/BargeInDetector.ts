/**
 * BargeInDetector — monitors microphone volume during TTS playback
 * to detect when the user starts speaking (barge-in).
 *
 * Echo prevention:
 * - Raised volume threshold (3-4x normal VAD threshold)
 * - Cooldown period after each audio chunk ends
 * - Relies on browser AEC (echoCancellation: true on getUserMedia)
 *
 * Design ref: REALTIME_VOICE_PIPELINE.md §3.3-3.4
 */

export interface BargeInDetectorOptions {
  /** Volume threshold to trigger barge-in (0-255, default 40) */
  threshold?: number;
  /** Minimum sustained duration above threshold in ms (default 200) */
  sustainedMs?: number;
  /** Cooldown after TTS audio chunk ends in ms — ignore triggers (default 300) */
  cooldownMs?: number;
  /** Called when barge-in is confirmed */
  onBargeIn: () => void;
}

export class BargeInDetector {
  private audioCtx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private animFrame: number | null = null;
  private stream: MediaStream | null = null;
  private active = false;
  private sustainedStart: number | null = null;
  private cooldownUntil = 0;

  private readonly threshold: number;
  private readonly sustainedMs: number;
  private readonly cooldownMs: number;
  private readonly onBargeIn: () => void;

  constructor(options: BargeInDetectorOptions) {
    this.threshold = options.threshold ?? 40;
    this.sustainedMs = options.sustainedMs ?? 200;
    this.cooldownMs = options.cooldownMs ?? 300;
    this.onBargeIn = options.onBargeIn;
  }

  /** Start monitoring the given media stream for barge-in */
  start(stream: MediaStream): void {
    this.stop(); // Clean up any previous instance

    try {
      this.audioCtx = new AudioContext();
      const source = this.audioCtx.createMediaStreamSource(stream);
      this.analyser = this.audioCtx.createAnalyser();
      this.analyser.fftSize = 512;
      source.connect(this.analyser);
      this.stream = stream;
      this.active = true;
      this.sustainedStart = null;

      const dataArray = new Uint8Array(this.analyser.frequencyBinCount);

      const check = () => {
        if (!this.active || !this.analyser) return;

        this.analyser.getByteFrequencyData(dataArray);
        const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;

        const now = Date.now();

        // Cooldown — ignore triggers shortly after TTS audio chunk ends
        if (now < this.cooldownUntil) {
          this.sustainedStart = null;
          this.animFrame = requestAnimationFrame(check);
          return;
        }

        if (avg > this.threshold) {
          // Volume above threshold — start/continue sustain timer
          if (this.sustainedStart === null) {
            this.sustainedStart = now;
          } else if (now - this.sustainedStart >= this.sustainedMs) {
            // Sustained speech detected — barge-in!
            this.active = false;
            this.onBargeIn();
            return; // Stop monitoring
          }
        } else {
          // Volume dropped — reset sustain timer
          this.sustainedStart = null;
        }

        this.animFrame = requestAnimationFrame(check);
      };

      this.animFrame = requestAnimationFrame(check);
    } catch {
      // AudioContext unavailable — silently disable barge-in
      this.active = false;
    }
  }

  /** Signal that a TTS audio chunk just finished playing — enter cooldown */
  notifyChunkEnd(): void {
    this.cooldownUntil = Date.now() + this.cooldownMs;
    this.sustainedStart = null;
  }

  /** Stop monitoring */
  stop(): void {
    this.active = false;
    if (this.animFrame !== null) {
      cancelAnimationFrame(this.animFrame);
      this.animFrame = null;
    }
    this.analyser = null;
    if (this.audioCtx) {
      this.audioCtx.close().catch(() => {});
      this.audioCtx = null;
    }
    this.stream = null;
    this.sustainedStart = null;
  }
}
