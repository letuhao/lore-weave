import { useState } from 'react';
import { PhaserGame } from './components/PhaserGame';

// Validation gate harness — minimal React shell to host the Phaser
// canvas and surface gate-pass evidence in the DOM. After gate passes
// (spec §11.1), this app gets expanded per spec §3 directory structure.

interface ValidationStatus {
  webglOk: boolean | null;
  tilemapOk: boolean | null;
  spriteOk: boolean | null;
  fps: number | null;
  errors: string[];
}

export default function App() {
  const [status, setStatus] = useState<ValidationStatus>({
    webglOk: null,
    tilemapOk: null,
    spriteOk: null,
    fps: null,
    errors: [],
  });

  return (
    <div className="relative w-screen h-screen">
      {/* Phaser canvas underneath */}
      <PhaserGame onStatus={setStatus} />

      {/* React DOM overlay — gate results */}
      <div className="absolute top-4 left-4 bg-slate-800/90 text-slate-100 p-4 rounded shadow-lg font-mono text-sm pointer-events-auto">
        <h1 className="text-base font-bold mb-2">Phaser 4 Validation Gate (spec §11.1)</h1>
        <ul className="space-y-1">
          <li>
            <Check value={status.webglOk} label="WebGL renderer + WebGL2-equiv extensions" />
          </li>
          <li>
            <Check value={status.tilemapOk} label="TilemapLayer renders 64×64 (GPU-layer N/A for iso)" />
          </li>
          <li>
            <Check value={status.spriteOk} label="SpriteGPULayer renders 100 sprites" />
          </li>
          <li>
            <span className="text-slate-400">FPS:</span>{' '}
            <span className={status.fps != null && status.fps >= 30 ? 'text-emerald-400' : 'text-amber-400'}>
              {status.fps?.toFixed(0) ?? '—'}
            </span>
          </li>
        </ul>
        {status.errors.length > 0 && (
          <details className="mt-3 text-red-300">
            <summary className="cursor-pointer">{status.errors.length} error(s)</summary>
            <ul className="mt-2 space-y-1 text-xs">
              {status.errors.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          </details>
        )}
        <p className="mt-3 text-xs text-slate-400">
          HMR check: edit <code>src/game/scenes/ValidationScene.ts</code> — should reload cleanly.
        </p>
      </div>
    </div>
  );
}

function Check({ value, label }: { value: boolean | null; label: string }) {
  const symbol = value === null ? '…' : value ? '✓' : '✗';
  const color = value === null ? 'text-slate-400' : value ? 'text-emerald-400' : 'text-red-400';
  return (
    <span>
      <span className={`${color} font-bold`}>{symbol}</span> <span className="text-slate-200">{label}</span>
    </span>
  );
}
