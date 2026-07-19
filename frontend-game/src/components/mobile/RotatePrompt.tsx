// Per spec §7.3 + MED-4 from /review-impl: V0 ships landscape-lock on
// mobile because 375px portrait + 128×64 HD tiles = ~3×6 visible tiles
// (unplayable). When portrait orientation detected, overlay this prompt
// asking the user to rotate. Portrait support deferred to V2+ with a
// separate 64×32 asset set.

import { useEffect, useState } from 'react';
import type { JSX } from 'react';

export function RotatePrompt(): JSX.Element | null {
  const [isPortrait, setIsPortrait] = useState(false);

  useEffect(() => {
    const check = (): void => {
      const w = window.innerWidth;
      const h = window.innerHeight;
      setIsPortrait(w < 700 && h > w);
    };
    check();
    window.addEventListener('resize', check);
    return () => window.removeEventListener('resize', check);
  }, []);

  if (!isPortrait) return null;

  return (
    <div className="fixed inset-0 bg-slate-900/95 text-slate-100 flex flex-col items-center justify-center z-[100] p-8 text-center">
      <div className="text-6xl mb-4">↻</div>
      <h2 className="text-xl font-bold mb-2">Please rotate your device</h2>
      <p className="text-sm text-slate-400">
        LoreWeave requires landscape orientation on mobile.
      </p>
    </div>
  );
}
