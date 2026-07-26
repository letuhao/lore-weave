import { useUiStore } from '@/store/ui-store';
import type { ReactNode } from 'react';
import type { JSX } from 'react';

// Modal placeholder — Session D wires real Settings/Confirm/Dialog
// content per spec §3 modal/ namespace.

export function Modal({ children }: { children: ReactNode }): JSX.Element | null {
  const modal = useUiStore((s) => s.modal);
  const close = useUiStore((s) => s.closeModal);
  if (modal === null) return null;
  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
      onClick={close}
    >
      <div
        className="bg-slate-800 p-6 rounded shadow-xl max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}
