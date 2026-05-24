import { useEffect, useRef } from 'react';
import { startGame } from '@game/main';

// React-Phaser bridge. Owns the Phaser.Game lifecycle.
//
// StrictMode-safe: useEffect cleanup destroys the game so the double-mount
// in dev StrictMode doesn't leak two canvases. Per spec §1 #3 (hybrid
// React + Phaser), this component is the SINGLE point where React owns
// the Phaser instance — every other piece of game code lives inside the
// Phaser scenes.

export function PhaserGame(): JSX.Element {
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
    gameRef.current = startGame(container);

    return () => {
      gameRef.current?.destroy(true);
      gameRef.current = null;
    };
  }, []);

  return (
    <div
      ref={containerRef}
      id="game-container"
      className="absolute inset-0"
      style={{ pointerEvents: 'auto' }}
    />
  );
}
