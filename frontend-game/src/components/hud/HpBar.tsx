import { useGameStore } from '@/store/game-store';
import type { JSX } from 'react';

// HP bar — reads from game-store (Zustand). Re-renders only when
// hp/maxHp actually change. Session D wires real HP from server.

export function HpBar(): JSX.Element {
  const hp = useGameStore((s) => s.hp);
  const maxHp = useGameStore((s) => s.maxHp);
  const pct = Math.max(0, Math.min(100, (hp / maxHp) * 100));
  return (
    <div className="w-40 h-3 bg-slate-700 rounded overflow-hidden">
      <div className="h-full bg-rose-500 transition-all" style={{ width: `${pct}%` }} />
      <div className="text-xs text-slate-300 mt-1">
        HP {hp} / {maxHp}
      </div>
    </div>
  );
}
