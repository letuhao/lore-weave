import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/shared/Button';
import type { JSX } from 'react';

// World selection placeholder. Session E+ wires character list from
// character-service. For V0 smoke, just one "Play" button that
// advances to the play route.

export function WorldSelectRoute(): JSX.Element {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-slate-900 text-slate-100 gap-4">
      <h1 className="text-3xl font-bold">Select World (placeholder)</h1>
      <p className="text-slate-400">V0 has one shared world; Session E adds character/server selection.</p>
      <div className="flex gap-3">
        <Button onClick={() => navigate('/play')}>Enter world</Button>
        <Button onClick={() => navigate('/world-preview')}>World map (3D)</Button>
      </div>
    </div>
  );
}
