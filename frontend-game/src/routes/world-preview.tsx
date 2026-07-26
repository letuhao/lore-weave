import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/shared/Button';
import { ErrorBoundary } from '@/components/shared/ErrorBoundary';
import { GlobeViewer } from '@/components/globe/GlobeViewer';
import { WORLDS, DEFAULT_WORLD, resolveWorld } from '@/components/globe/worlds';
import type { JSX } from 'react';

// World-preview route — a full-screen 3D globe of a generated world (the
// `world-gen` `.glb`), with a picker for the bundled worlds. V1 is static
// delivery (assets under public/worlds/); a live world-gen-service render is a
// later wiring step (see worlds.ts).

export function WorldPreviewRoute(): JSX.Element {
  const navigate = useNavigate();
  const [worldId, setWorldId] = useState<string>(DEFAULT_WORLD.id);
  const world = resolveWorld(worldId);

  return (
    <div className="min-h-screen flex flex-col bg-slate-950 text-slate-100">
      <header className="flex items-center gap-4 px-4 py-3 border-b border-slate-800">
        <h1 className="text-lg font-semibold">World preview</h1>
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <span>World</span>
          <select
            className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-sm"
            value={worldId}
            onChange={(e) => setWorldId(e.target.value)}
            aria-label="Select world"
          >
            {WORLDS.map((w) => (
              <option key={w.id} value={w.id}>
                {w.label}
              </option>
            ))}
          </select>
        </label>
        <span className="ml-auto" />
        <Button onClick={() => navigate('/world-select')}>Back</Button>
      </header>
      {/* The Canvas fills this flex-1 region (GlobeViewer needs a sized parent).
          `key` forces a fresh mount when the world changes so controls/camera
          reset cleanly. */}
      <main className="flex-1 relative">
        {/* A failed .glb load throws out of useGLTF — contain it so the header +
            picker survive (and switching world resets the boundary via resetKey)
            instead of white-screening the whole app. */}
        <ErrorBoundary
          resetKey={world.id}
          fallback={
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-slate-400">
              <p>Could not load the 3D model for this world.</p>
              <p className="text-xs text-slate-500">{world.src}</p>
            </div>
          }
        >
          <GlobeViewer key={world.id} src={world.src} className="absolute inset-0" />
        </ErrorBoundary>
      </main>
    </div>
  );
}
