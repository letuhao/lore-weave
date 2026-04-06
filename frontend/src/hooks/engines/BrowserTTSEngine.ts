/**
 * Speaks text via Web Speech API (SpeechSynthesisUtterance).
 * Free fallback when no attached/AI audio is available.
 */
export class BrowserTTSEngine {
  private utterance: SpeechSynthesisUtterance | null = null;
  private onEndCallback: (() => void) | null = null;
  private _speed = 1;
  private _voice: SpeechSynthesisVoice | null = null;

  /** Get available voices (may be empty until voiceschanged event fires) */
  static getVoices(): SpeechSynthesisVoice[] {
    return speechSynthesis.getVoices();
  }

  /** Wait for voices to be loaded (some browsers load async) */
  static waitForVoices(): Promise<SpeechSynthesisVoice[]> {
    return new Promise((resolve) => {
      const voices = speechSynthesis.getVoices();
      if (voices.length > 0) {
        resolve(voices);
        return;
      }
      speechSynthesis.addEventListener('voiceschanged', () => {
        resolve(speechSynthesis.getVoices());
      }, { once: true });
    });
  }

  speak(text: string, onEnd: () => void) {
    this.stop();
    this.onEndCallback = onEnd;

    this.utterance = new SpeechSynthesisUtterance(text);
    this.utterance.rate = this._speed;
    if (this._voice) {
      this.utterance.voice = this._voice;
    }

    this.utterance.onend = () => {
      this.onEndCallback?.();
      this.utterance = null;
    };
    this.utterance.onerror = () => {
      this.onEndCallback?.();
      this.utterance = null;
    };

    speechSynthesis.speak(this.utterance);
  }

  pause() {
    speechSynthesis.pause();
  }

  resume() {
    speechSynthesis.resume();
  }

  stop() {
    speechSynthesis.cancel();
    this.utterance = null;
    this.onEndCallback = null;
  }

  get paused(): boolean {
    return speechSynthesis.paused;
  }

  get speaking(): boolean {
    return speechSynthesis.speaking;
  }

  set speed(rate: number) {
    this._speed = rate;
    // Cannot change rate mid-utterance — applies to next speak()
  }

  set voice(v: SpeechSynthesisVoice | null) {
    this._voice = v;
  }

  destroy() {
    this.stop();
  }
}
