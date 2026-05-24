import { useEffect, useRef } from 'react';
import { startGame } from '../game/main';
import { EventBus, type ValidationStatusEvent } from '../game/EventBus';

// React-Phaser bridge component. Owns the Phaser.Game lifecycle.
//
// StrictMode-safe: useEffect cleanup destroys the game so the double-mount
// in dev StrictMode doesn't leak two canvases. The mounted ref guards
// against the destroyed-then-re-init race.

interface PhaserGameProps {
  onStatus: (status: {
    webglOk: boolean | null;
    tilemapOk: boolean | null;
    spriteOk: boolean | null;
    fps: number | null;
    errors: string[];
  }) => void;
}

export function PhaserGame({ onStatus }: PhaserGameProps) {
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

    const errors: string[] = [];
    const status = {
      webglOk: null as boolean | null,
      tilemapOk: null as boolean | null,
      spriteOk: null as boolean | null,
      fps: null as number | null,
      errors,
    };

    const handleStatus = (evt: ValidationStatusEvent) => {
      if (evt.kind === 'webgl') status.webglOk = evt.ok;
      if (evt.kind === 'tilemap') status.tilemapOk = evt.ok;
      if (evt.kind === 'sprite') status.spriteOk = evt.ok;
      if (evt.kind === 'fps') status.fps = evt.value;
      if (evt.kind === 'error') errors.push(evt.message);
      onStatus({ ...status, errors: [...errors] });
    };
    EventBus.on('validation', handleStatus);

    return () => {
      EventBus.off('validation', handleStatus);
      gameRef.current?.destroy(true);
      gameRef.current = null;
    };
  }, [onStatus]);

  return (
    <div
      ref={containerRef}
      id="game-container"
      className="absolute inset-0"
      style={{ pointerEvents: 'auto' }}
    />
  );
}
