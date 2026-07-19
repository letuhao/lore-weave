// Virtual gamepad placeholder. Session D wires touch zones with d-pad
// + action buttons that emit canonical PlayerActionEvent via EventBus.
// Per spec §1 #8: scaffolded from V0 day 1; concrete wiring in D.

import type { JSX } from 'react';
export function VirtualGamepad(): JSX.Element {
  return (
    <div className="fixed bottom-4 left-0 right-0 flex justify-between px-6 pointer-events-none md:hidden">
      <div className="w-24 h-24 rounded-full bg-slate-700/60 pointer-events-auto" />
      <div className="flex gap-2">
        <button
          type="button"
          className="w-16 h-16 rounded-full bg-rose-700/60 text-slate-100 pointer-events-auto"
        >
          A
        </button>
        <button
          type="button"
          className="w-16 h-16 rounded-full bg-sky-700/60 text-slate-100 pointer-events-auto"
        >
          B
        </button>
      </div>
    </div>
  );
}
