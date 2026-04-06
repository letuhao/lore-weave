/**
 * Plays audio files (attached audio or AI TTS segments) via HTMLAudioElement.
 * Reports progress and calls onEnd when finished.
 */
export class AudioFileEngine {
  private audio: HTMLAudioElement;
  private onEndCallback: (() => void) | null = null;
  private onProgressCallback: ((currentMs: number, durationMs: number) => void) | null = null;
  private progressTimer: ReturnType<typeof setInterval> | null = null;

  constructor() {
    this.audio = new Audio();
    this.audio.addEventListener('ended', () => {
      this.stopProgressTimer();
      this.onEndCallback?.();
    });
    this.audio.addEventListener('error', () => {
      this.stopProgressTimer();
      this.onEndCallback?.();
    });
  }

  play(url: string, onEnd: () => void, onProgress?: (currentMs: number, durationMs: number) => void) {
    this.stop();
    this.onEndCallback = onEnd;
    this.onProgressCallback = onProgress || null;
    this.audio.src = url;
    this.audio.play();
    this.startProgressTimer();
  }

  pause() {
    this.audio.pause();
    this.stopProgressTimer();
  }

  resume() {
    this.audio.play();
    this.startProgressTimer();
  }

  stop() {
    this.audio.pause();
    this.audio.src = '';
    this.stopProgressTimer();
    this.onEndCallback = null;
    this.onProgressCallback = null;
  }

  get paused(): boolean {
    return this.audio.paused;
  }

  get currentTimeMs(): number {
    return Math.round(this.audio.currentTime * 1000);
  }

  get durationMs(): number {
    const d = this.audio.duration;
    return isFinite(d) ? Math.round(d * 1000) : 0;
  }

  set speed(rate: number) {
    this.audio.playbackRate = rate;
  }

  seekTo(ms: number) {
    this.audio.currentTime = ms / 1000;
  }

  private startProgressTimer() {
    this.stopProgressTimer();
    if (!this.onProgressCallback) return;
    this.progressTimer = setInterval(() => {
      this.onProgressCallback?.(this.currentTimeMs, this.durationMs);
    }, 200);
  }

  private stopProgressTimer() {
    if (this.progressTimer) {
      clearInterval(this.progressTimer);
      this.progressTimer = null;
    }
  }

  destroy() {
    this.stop();
  }
}
