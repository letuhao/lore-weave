/**
 * VoicePipelineState — strict state machine for voice pipeline.
 * Single source of truth. All transitions guarded. No async races.
 *
 * States: IDLE → LISTENING → RECORDING → SENDING → TRANSCRIBING → THINKING → SPEAKING → LISTENING
 * Each state has a guard: what can happen next.
 */

export type PipelinePhase =
  | 'idle'          // Voice mode off
  | 'activating'    // Setting up VAD + AudioContext
  | 'listening'     // VAD active, waiting for speech (VAD records internally)
  | 'sending'       // Audio captured, sending to server
  | 'transcribing'  // Server doing STT
  | 'thinking'      // Server doing LLM (text streaming)
  | 'speaking'      // Playing TTS audio
  | 'error';        // Something failed — can retry

export interface PipelineStep {
  phase: PipelinePhase;
  label: string;
  startedAt: number | null;
  completedAt: number | null;
  error: string | null;
}

export type PipelineListener = (state: PipelineSnapshot) => void;

export interface PipelineSnapshot {
  phase: PipelinePhase;
  steps: PipelineStep[];
  canCancel: boolean;
  error: string | null;
  sttText: string;
  aiText: string;
  turnIndex: number;
}

// Allowed transitions — strict guard
const ALLOWED_TRANSITIONS: Record<PipelinePhase, PipelinePhase[]> = {
  idle:         ['activating'],
  activating:   ['listening', 'error', 'idle'],
  listening:    ['sending', 'idle'],              // VAD fires speech-end → sending
  sending:      ['transcribing', 'error', 'idle'],
  transcribing: ['thinking', 'listening', 'error', 'idle'],  // listening = empty transcript
  thinking:     ['speaking', 'listening', 'error', 'idle'],   // listening = no audio generated
  speaking:     ['listening', 'idle'],
  error:        ['listening', 'idle'],
};

const PHASE_LABELS: Record<PipelinePhase, string> = {
  idle: 'Idle',
  activating: 'Activating...',
  listening: 'Listening',
  sending: 'Sending audio',
  transcribing: 'Transcribing',
  thinking: 'AI thinking',
  speaking: 'Speaking',
  error: 'Error',
};

export class VoicePipelineState {
  private _phase: PipelinePhase = 'idle';
  private _steps: PipelineStep[] = [];
  private _error: string | null = null;
  private _sttText = '';
  private _aiText = '';
  private _turnIndex = 0;
  private _listeners: Set<PipelineListener> = new Set();

  get phase(): PipelinePhase { return this._phase; }
  get isActive(): boolean { return this._phase !== 'idle'; }
  get canCancel(): boolean {
    return ['sending', 'transcribing', 'thinking', 'speaking'].includes(this._phase);
  }

  subscribe(listener: PipelineListener): () => void {
    this._listeners.add(listener);
    listener(this.snapshot());
    return () => this._listeners.delete(listener);
  }

  snapshot(): PipelineSnapshot {
    return {
      phase: this._phase,
      steps: [...this._steps],
      canCancel: this.canCancel,
      error: this._error,
      sttText: this._sttText,
      aiText: this._aiText,
      turnIndex: this._turnIndex,
    };
  }

  /**
   * Transition to a new phase. Returns false if transition is not allowed.
   * This is the ONLY way to change state — no direct mutations.
   */
  transition(to: PipelinePhase, error?: string): boolean {
    const allowed = ALLOWED_TRANSITIONS[this._phase];
    if (!allowed?.includes(to)) {
      console.warn(`[Pipeline] INVALID: ${this._phase} → ${to}`);
      return false;
    }

    const prev = this._phase;
    console.log(`[Pipeline] ${prev} → ${to}`);

    // Complete previous step
    if (this._steps.length > 0) {
      const last = this._steps[this._steps.length - 1];
      if (!last.completedAt) {
        last.completedAt = Date.now();
      }
    }

    this._phase = to;
    this._error = error || null;

    // Start new step (except idle)
    if (to !== 'idle') {
      this._steps.push({
        phase: to,
        label: PHASE_LABELS[to],
        startedAt: Date.now(),
        completedAt: null,
        error: error || null,
      });
    }

    // Reset on new turn
    if (to === 'listening' && prev !== 'activating') {
      this._turnIndex++;
      this._steps = [];
      this._sttText = '';
      this._aiText = '';
    }

    // Reset everything on deactivation
    if (to === 'idle') {
      this._steps = [];
      this._sttText = '';
      this._aiText = '';
      this._error = null;
      this._turnIndex = 0;
    }

    this._notify();
    return true;
  }

  /** Set STT transcript (only valid in transcribing/thinking phase) */
  setSttText(text: string): void {
    this._sttText = text;
    this._notify();
  }

  /** Append AI text delta (only valid in thinking/speaking phase) */
  appendAiText(delta: string): void {
    this._aiText += delta;
    this._notify();
  }

  /** Force reset to idle (emergency escape) */
  forceIdle(): void {
    this._phase = 'idle';
    this._steps = [];
    this._sttText = '';
    this._aiText = '';
    this._error = null;
    this._turnIndex = 0;
    this._notify();
  }

  private _notify(): void {
    const snap = this.snapshot();
    for (const listener of this._listeners) {
      listener(snap);
    }
  }
}
