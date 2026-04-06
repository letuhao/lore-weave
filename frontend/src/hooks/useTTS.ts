import { createContext, useContext, useCallback, useRef, useSyncExternalStore } from 'react';
import type { JSONContent } from '@tiptap/react';
import { AudioFileEngine } from './engines/AudioFileEngine';
import { BrowserTTSEngine } from './engines/BrowserTTSEngine';
import {
  extractSpeakableBlocks,
  resolveAudioSource,
  type SpeakableBlock,
  type AudioSource,
} from '@/lib/audio-utils';

// ── State ───────────────────────────────────────────────────────────────

export type TTSStatus = 'idle' | 'playing' | 'paused';

export interface TTSState {
  status: TTSStatus;
  activeBlockId: string | null;
  activeBlockIndex: number;
  source: AudioSource | null;
  speed: number;
  currentMs: number;
  durationMs: number;
}

const INITIAL_STATE: TTSState = {
  status: 'idle',
  activeBlockId: null,
  activeBlockIndex: -1,
  source: null,
  speed: 1,
  currentMs: 0,
  durationMs: 0,
};

// ── Store (external, non-React) ─────────────────────────────────────────

type Listener = () => void;

class TTSStore {
  private state: TTSState = { ...INITIAL_STATE };
  private listeners = new Set<Listener>();

  private audioEngine = new AudioFileEngine();
  private browserEngine = new BrowserTTSEngine();

  private queue: SpeakableBlock[] = [];
  private queueIndex = -1;
  private aiSegments = new Map<number, string>();

  getState(): TTSState {
    return this.state;
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private emit() {
    this.listeners.forEach((l) => l());
  }

  private update(patch: Partial<TTSState>) {
    this.state = { ...this.state, ...patch };
    this.emit();
  }

  // ── Public API ──────────────────────────────────────────────────────

  /** Load blocks and optional AI segments, then start playback from first block */
  start(blocks: JSONContent[], aiSegs?: Map<number, string>) {
    this.stop();
    this.queue = extractSpeakableBlocks(blocks);
    this.aiSegments = aiSegs || new Map();
    if (this.queue.length === 0) return;
    this.queueIndex = 0;
    this.playCurrentBlock();
  }

  /** Resume or start from a specific block */
  seekBlock(blockId: string) {
    const idx = this.queue.findIndex((b) => b.blockId === blockId);
    if (idx < 0) return;
    this.stopEngines();
    this.queueIndex = idx;
    this.playCurrentBlock();
  }

  play() {
    if (this.state.status === 'paused') {
      const src = this.state.source;
      if (src === 'browser') {
        this.browserEngine.resume();
      } else {
        this.audioEngine.resume();
      }
      this.update({ status: 'playing' });
    }
  }

  pause() {
    if (this.state.status === 'playing') {
      const src = this.state.source;
      if (src === 'browser') {
        this.browserEngine.pause();
      } else {
        this.audioEngine.pause();
      }
      this.update({ status: 'paused' });
    }
  }

  stop() {
    this.stopEngines();
    this.queue = [];
    this.queueIndex = -1;
    this.aiSegments.clear();
    this.update({ ...INITIAL_STATE });
  }

  nextBlock() {
    if (this.queueIndex < this.queue.length - 1) {
      this.stopEngines();
      this.queueIndex++;
      this.playCurrentBlock();
    } else {
      this.stop();
    }
  }

  prevBlock() {
    if (this.queueIndex > 0) {
      this.stopEngines();
      this.queueIndex--;
      this.playCurrentBlock();
    }
  }

  setSpeed(rate: number) {
    this.audioEngine.speed = rate;
    this.browserEngine.speed = rate;
    this.update({ speed: rate });
  }

  setVoice(voice: SpeechSynthesisVoice | null) {
    this.browserEngine.voice = voice;
  }

  // ── Internal ────────────────────────────────────────────────────────

  private playCurrentBlock() {
    const block = this.queue[this.queueIndex];
    if (!block) {
      this.stop();
      return;
    }

    const { source, url } = resolveAudioSource(block, this.aiSegments);

    this.update({
      status: 'playing',
      activeBlockId: block.blockId,
      activeBlockIndex: this.queueIndex,
      source,
      currentMs: 0,
      durationMs: 0,
    });

    const onEnd = () => this.nextBlock();

    if (source === 'browser') {
      this.browserEngine.speak(block.text, onEnd);
    } else if (url) {
      this.audioEngine.play(url, onEnd, (cur, dur) => {
        this.update({ currentMs: cur, durationMs: dur });
      });
      this.audioEngine.speed = this.state.speed;
    } else {
      // No audio and no text — skip
      onEnd();
    }
  }

  private stopEngines() {
    this.audioEngine.stop();
    this.browserEngine.stop();
  }

  destroy() {
    this.stop();
    this.audioEngine.destroy();
    this.browserEngine.destroy();
  }
}

// ── Singleton + React integration ────────────────────────────────────────

let _store: TTSStore | null = null;

function getStore(): TTSStore {
  if (!_store) _store = new TTSStore();
  return _store;
}

/** React hook — subscribe to TTS state changes */
export function useTTSState(): TTSState {
  const store = getStore();
  return useSyncExternalStore(
    (cb) => store.subscribe(cb),
    () => store.getState(),
  );
}

/** React hook — returns stable control functions */
export function useTTSControls() {
  const store = getStore();

  const start = useCallback((blocks: JSONContent[], aiSegs?: Map<number, string>) => {
    store.start(blocks, aiSegs);
  }, [store]);

  const seekBlock = useCallback((blockId: string) => {
    store.seekBlock(blockId);
  }, [store]);

  const play = useCallback(() => store.play(), [store]);
  const pause = useCallback(() => store.pause(), [store]);
  const stop = useCallback(() => store.stop(), [store]);
  const nextBlock = useCallback(() => store.nextBlock(), [store]);
  const prevBlock = useCallback(() => store.prevBlock(), [store]);
  const setSpeed = useCallback((rate: number) => store.setSpeed(rate), [store]);
  const setVoice = useCallback((voice: SpeechSynthesisVoice | null) => store.setVoice(voice), [store]);

  return { start, seekBlock, play, pause, stop, nextBlock, prevBlock, setSpeed, setVoice };
}

// Re-export types
export type { SpeakableBlock, AudioSource };
