import { useGameStore } from '@/store/game-store';
import type { JSX } from 'react';

export function ManaBar(): JSX.Element {
  const mp = useGameStore((s) => s.mp);
  const maxMp = useGameStore((s) => s.maxMp);
  const pct = Math.max(0, Math.min(100, (mp / maxMp) * 100));
  return (
    <div className="w-40 h-3 bg-slate-700 rounded overflow-hidden">
      <div className="h-full bg-sky-500 transition-all" style={{ width: `${pct}%` }} />
      <div className="text-xs text-slate-300 mt-1">
        MP {mp} / {maxMp}
      </div>
    </div>
  );
}
