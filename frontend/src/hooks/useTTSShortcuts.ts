import { useEffect } from 'react';
import { useTTSState, useTTSControls } from './useTTS';

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];

/**
 * Keyboard shortcuts for TTS playback (active only when status !== 'idle').
 * - Space: play/pause
 * - [ / ]: decrease/increase speed
 * - Shift+Left / Shift+Right: prev/next block
 * - Escape: stop playback
 */
export function useTTSShortcuts() {
  const { status, speed } = useTTSState();
  const controls = useTTSControls();

  useEffect(() => {
    if (status === 'idle') return;

    const handler = (e: KeyboardEvent) => {
      // Don't capture if user is typing in an input/textarea
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

      if (e.key === ' ') {
        e.preventDefault();
        if (status === 'playing') controls.pause();
        else controls.play();
        return;
      }

      if (e.key === 'Escape') {
        e.preventDefault();
        controls.stop();
        return;
      }

      if (e.key === '[') {
        e.preventDefault();
        const idx = SPEEDS.indexOf(speed);
        if (idx > 0) controls.setSpeed(SPEEDS[idx - 1]);
        return;
      }

      if (e.key === ']') {
        e.preventDefault();
        const idx = SPEEDS.indexOf(speed);
        if (idx < SPEEDS.length - 1) controls.setSpeed(SPEEDS[idx + 1]);
        return;
      }

      if (e.shiftKey && e.key === 'ArrowLeft') {
        e.preventDefault();
        controls.prevBlock();
        return;
      }

      if (e.shiftKey && e.key === 'ArrowRight') {
        e.preventDefault();
        controls.nextBlock();
        return;
      }
    };

    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [status, speed, controls]);
}
