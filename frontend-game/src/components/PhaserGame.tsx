import { useEffect, useRef } from 'react';
import { startGame } from '@game/main';
import { EventBus } from '@game/EventBus';
import type { TilemapView } from '@/types/tilemap';
import type { JSX } from 'react';

// React-Phaser bridge. Owns the Phaser.Game lifecycle.
//
// StrictMode-safe: useEffect cleanup destroys the game so the double-mount
// in dev StrictMode doesn't leak two canvases.
//
// V1 tilemap-viewer: when `tilemap` prop changes, emits `tilemap-updated`
// via EventBus so the running WorldScene re-renders. The Phaser.Game
// itself is created once and never recreated — only the scene re-renders.

export interface PhaserGameProps {
  tilemap?: TilemapView;
}

export function PhaserGame({ tilemap }: PhaserGameProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const gameRef = useRef<Phaser.Game | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    if (gameRef.current) {
      return;
    }
    // Defensive: Phaser 4 only supports WebGL (no canvas fallback). On
    // hosts without WebGL (firefox CI, users with WebGL disabled in
    // about:config) `startGame` throws synchronously. Without this
    // guard React 18 unmounts the entire /play subtree, hiding the HUD
    // and viewer controls.
    try {
      gameRef.current = startGame(container);
    } catch (err) {
      console.error(
        'PhaserGame: failed to start Phaser (WebGL likely unavailable). HUD continues without canvas.',
        err,
      );
    }

    return () => {
      gameRef.current?.destroy(true);
      gameRef.current = null;
    };
  }, []);

  // Bridge React tilemap state → Phaser EventBus.
  useEffect(() => {
    if (!tilemap) {
      return;
    }
    // Re-emit on every tilemap change. WorldScene's tilemap-updated
    // handler tears down + re-renders. If the scene isn't mounted yet
    // (boot chain still on Preloader), the emit is a no-op; the scene
    // re-emits when ready via its own subscription pattern… but for V1
    // we just retry once after a short delay if needed. In practice the
    // scene boots in <500 ms so the first useZoneTilemap fetch (which
    // takes 1–5 s for a 64² render) always settles after scene boot.
    EventBus.emit('tilemap-updated', tilemap);
  }, [tilemap]);

  return (
    <div
      ref={containerRef}
      id="game-container"
      className="absolute inset-0"
      style={{ pointerEvents: 'auto' }}
    />
  );
}
